"""#702 P6 - the Consolidation Breakout shadow's SQL, run for REAL.

`tests/test_cb_shadow.py` runs the job against an in-memory store that reproduces the SQL's write guards. This file
is the proof that the reproduction is faithful: the DDL, the four upserts, the three guarded `ON CONFLICT ... WHERE`
clauses, the SQL universe prefilter and the read helpers are executed against a REAL Postgres, and the whole job is
run on both stores over the same market with the results compared row for row.

SKIPPED unless `CB_SHADOW_TEST_PG_DSN` names a throwaway Postgres (each run works in its own schema, dropped at the
end). The suite runs on a Python without an embedded Postgres, so this is a deliberate opt-in:

    # any scratch server works; e.g. the pip-installable `pgserver` in a separate venv
    CB_SHADOW_TEST_PG_DSN='postgresql://postgres:@/postgres?host=/path/to/socket' python -m pytest tests/test_cb_shadow_pg.py
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import uuid

import pytest

from agents.market_intelligence import consolidation_breakout as cb
from agents.market_intelligence import consolidation_breakout_shadow as sh
from agents.market_intelligence import db
from tests.cb_shadow_support import (BREAK_DAY, WATCH_NIGHT, FakeCollector, FakeStore, build_market,
                                     synth_minutes)

PG_DSN = os.environ.get("CB_SHADOW_TEST_PG_DSN")
pytestmark = pytest.mark.skipif(not PG_DSN, reason="set CB_SHADOW_TEST_PG_DSN to a throwaway Postgres to run the SQL for real")

asyncpg = pytest.importorskip("asyncpg")
D = dt.date

# The three tables the shadow READS from (columns it uses; types as in db.initialize_schema) + the audit table.
BASE_DDL = """
CREATE TABLE mi_daily_closes (trade_date DATE NOT NULL, ticker TEXT NOT NULL, close FLOAT NOT NULL, volume BIGINT,
    open_price FLOAT, high_price FLOAT, low_price FLOAT, PRIMARY KEY (trade_date, ticker));
CREATE TABLE mi_splits (ticker TEXT NOT NULL, execution_date DATE NOT NULL, split_from INT NOT NULL,
    split_to INT NOT NULL, polygon_id TEXT, fetched_at TIMESTAMPTZ DEFAULT NOW(), applied_at TIMESTAMPTZ,
    adjustment_applied BOOLEAN NOT NULL DEFAULT FALSE, PRIMARY KEY (ticker, execution_date));
CREATE TABLE mi_security_types (ticker TEXT PRIMARY KEY, security_type TEXT NOT NULL, exchange TEXT DEFAULT '',
    updated_at TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE mi_audit_log (id SERIAL PRIMARY KEY, created_at TIMESTAMPTZ DEFAULT NOW(), event_type TEXT NOT NULL,
    summary TEXT NOT NULL, detail TEXT DEFAULT '');
"""


class Env:
    def __init__(self, pool, schema):
        self.pool, self.schema = pool, schema

    async def load(self, market):
        async with self.pool.acquire() as c:
            await c.executemany(
                "INSERT INTO mi_daily_closes (trade_date, ticker, open_price, high_price, low_price, close, volume) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7)",
                [(r[0], t, r[1], r[2], r[3], r[4], int(r[5])) for t, rows in market.bars.items() for r in rows])
            await c.executemany("INSERT INTO mi_security_types (ticker, security_type) VALUES ($1,$2)",
                                list(market.sectypes.items()))


@pytest.fixture
def env(monkeypatch):
    holder = {}

    async def setup():
        admin = await asyncpg.connect(PG_DSN)
        schema = "cbt_" + uuid.uuid4().hex[:10]
        await admin.execute(f"CREATE SCHEMA {schema}")

        async def init(conn):
            await conn.set_type_codec("jsonb", encoder=db._json_encoder, decoder=db._json_decoder,
                                      schema="pg_catalog")
        # search_path as a STARTUP parameter: asyncpg's pool runs RESET ALL when a connection is released, which
        # would silently drop a `SET search_path` and send later statements to `public`
        pool = await asyncpg.create_pool(PG_DSN, init=init, min_size=1, max_size=4,
                                         server_settings={"search_path": schema})
        async with pool.acquire() as c:
            await c.execute(BASE_DDL)
            await c.execute(db._CB_SHADOW_DDL)
        holder.update(admin=admin, schema=schema, pool=pool)
        return Env(pool, schema)

    loop = asyncio.new_event_loop()
    e = loop.run_until_complete(setup())

    async def gp():
        return e.pool
    monkeypatch.setattr(db, "get_pool", gp)
    e.loop = loop
    yield e

    async def teardown():
        await holder["pool"].close()
        await holder["admin"].execute(f"DROP SCHEMA {holder['schema']} CASCADE")
        await holder["admin"].close()
    loop.run_until_complete(teardown())
    loop.close()


def arun(e, coro):
    return e.loop.run_until_complete(coro)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
class TestDdlAndStatements:
    def test_the_ddl_runs_again_without_error_and_creates_every_table(self, env):
        async def go():
            async with env.pool.acquire() as c:
                for _ in range(2):                                   # twice more: idempotent
                    await c.execute(db._CB_SHADOW_DDL)
                got = {r["table_name"] for r in await c.fetch(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = $1", env.schema)}
                idx = {r["indexname"] for r in await c.fetch(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = $1", env.schema)}
            return got, idx
        got, idx = arun(env, go())
        assert {"mi_consolidation_breakout_watch", "mi_consolidation_breakout_entry",
                "mi_consolidation_breakout_exit", "mi_consolidation_breakout_sic"} <= got
        assert {"idx_cb_watch_scan_date", "idx_cb_entry_break_date", "idx_cb_entry_ticker_base",
                "idx_cb_exit_arm_mature"} <= idx

    def test_every_write_statement_prepares_against_the_real_schema_with_the_right_parameter_count(self, env):
        async def go():
            out = {}
            async with env.pool.acquire() as c:
                for name, cols in (("CB_WATCH_UPSERT_SQL", db.CB_WATCH_COLS), ("CB_ENTRY_UPSERT_SQL", db.CB_ENTRY_COLS),
                                   ("CB_EXIT_UPSERT_SQL", db.CB_EXIT_COLS), ("CB_SIC_UPSERT_SQL", db.CB_SIC_COLS)):
                    st = await c.prepare(getattr(db, name))
                    out[name] = (len(st.get_parameters()), len(cols))
            return out
        for name, (got, want) in arun(env, go()).items():
            assert got == want, name

    def test_the_account_mode_invariant_has_nothing_to_hold_these_are_not_trade_tables(self, env):
        async def go():
            async with env.pool.acquire() as c:
                return await c.fetch(
                    "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = $1 "
                    "AND table_name LIKE 'mi_consolidation_breakout_%' AND column_name = 'account_mode'", env.schema)
        assert arun(env, go()) == []


class TestWriteGuards:
    def _entry(self, **kw):
        row = {"ticker": "AAA", "watch_date": D(2026, 9, 16), "break_date": BREAK_DAY, "k": "k5",
               "pole_date": D(2026, 8, 19), "entry_variant": "orh5", "status": "abstain", "reason": "no_minutes",
               "pivot": 10.0, "level": None, "fill": None, "stop": None, "width_pct": None, "adr20": 0.05,
               "gap_pct": 0.01, "gap_over_1adr": False, "fill_minute": None, "day0_stopped": None,
               "day0_exit_price": None, "day0_exit_minute": None, "retrigger": 0, "retrigger_chain": 0,
               "base_id": "AAA|2026-08-19", "cells": {"C0": True}, "first_cells": {"C0": 1},
               "first_chain_cells": {"C0": 1}, "minutes_state": "no_minutes", "feed": "iex"}
        row.update(kw)
        return row

    async def _entries(self, env):
        async with env.pool.acquire() as c:
            return [dict(r) for r in await c.fetch("SELECT * FROM mi_consolidation_breakout_entry ORDER BY id")]

    def test_a_no_minutes_abstain_is_overwritten_by_a_fill_and_a_fill_is_never_overwritten(self, env):
        async def go():
            await db.cb_upsert_entry_rows([self._entry()])
            await db.cb_upsert_entry_rows([self._entry(status="filled", reason=None, fill=10.5, stop=10.0,
                                                       width_pct=0.047, fill_minute=7, day0_stopped=False,
                                                       minutes_state="ok")])
            first = await self._entries(env)
            await db.cb_upsert_entry_rows([self._entry(status="filled", reason=None, fill=99.0, stop=1.0,
                                                       fill_minute=1, minutes_state="ok")])
            await db.cb_upsert_entry_rows([self._entry(status="abstain", reason="no_minutes")])
            return first, await self._entries(env)
        first, second = arun(env, go())
        assert len(first) == 1 and first[0]["status"] == "filled" and first[0]["fill"] == 10.5
        assert second == first                                          # the later rows changed nothing, id included
        assert first[0]["cells"] == {"C0": True} and isinstance(first[0]["first_cells"], dict)   # jsonb, not a string

    def test_other_abstains_are_final_too(self, env):
        async def go():
            await db.cb_upsert_entry_rows([self._entry(status="abstain", reason="minute_daily_mismatch")])
            await db.cb_upsert_entry_rows([self._entry(status="filled", reason=None, fill=5.0, stop=4.0)])
            return await self._entries(env)
        rows = arun(env, go())
        assert rows[0]["reason"] == "minute_daily_mismatch" and rows[0]["fill"] is None

    def test_a_mature_exit_row_is_final_and_an_open_one_is_refreshed(self, env):
        async def go():
            await db.cb_upsert_entry_rows([self._entry(status="filled", reason=None, fill=10.5, stop=10.0)])
            eid = (await self._entries(env))[0]["id"]
            ex = lambda **kw: {"entry_id": eid, "arm": "p33_s3_t10", "status": "degraded", "realized_r": 0.5,
                               "pnl_adr": 0.1, "sessions_held": 3, "events": [[1, "mark", 10.9, 1.0]], "n_fwd": 3,
                               "mature": False, "reason": None, "last_bar_date": D(2026, 9, 21)} | kw
            await db.cb_upsert_exit_rows([ex()])
            await db.cb_upsert_exit_rows([ex(realized_r=1.5, n_fwd=4)])                     # open: refreshed
            mid = await self._read_exit(env)
            await db.cb_upsert_exit_rows([ex(status="stopped", realized_r=-1.0, mature=True)])  # becomes mature
            await db.cb_upsert_exit_rows([ex(status="trailed", realized_r=9.0, mature=True)])   # final: ignored
            return mid, await self._read_exit(env)
        mid, last = arun(env, go())
        assert mid["realized_r"] == 1.5 and mid["n_fwd"] == 4 and mid["mature"] is False
        assert last["status"] == "stopped" and last["realized_r"] == -1.0 and last["mature"] is True
        assert last["events"] == [[1, "mark", 10.9, 1.0]]                    # jsonb list round-trips as a list

    async def _read_exit(self, env):
        async with env.pool.acquire() as c:
            return dict(await c.fetchrow("SELECT * FROM mi_consolidation_breakout_exit"))

    def test_the_exit_rows_follow_their_entry_when_it_is_deleted(self, env):
        async def go():
            await db.cb_upsert_entry_rows([self._entry(status="filled", reason=None, fill=10.5, stop=10.0)])
            eid = (await self._entries(env))[0]["id"]
            await db.cb_upsert_exit_rows([{"entry_id": eid, "arm": "stop_only", "status": "degraded",
                                           "realized_r": 0.0, "pnl_adr": 0.0, "sessions_held": 0, "events": [],
                                           "n_fwd": 0, "mature": False, "reason": None, "last_bar_date": BREAK_DAY}])
            async with env.pool.acquire() as c:
                await c.execute("DELETE FROM mi_consolidation_breakout_entry")
                return await c.fetchval("SELECT count(*) FROM mi_consolidation_breakout_exit")
        assert arun(env, go()) == 0

    def test_a_watch_row_is_an_upsert_on_ticker_and_night(self, env):
        row = {"ticker": "AAA", "scan_date": WATCH_NIGHT, "pole_date": D(2026, 8, 19), "pole_high": 12.0,
               "pivot_k5": 11.0, "pivot_k5_date": D(2026, 9, 11), "pivot_k10": 11.5, "pivot_k10_date": D(2026, 9, 2),
               "pivot_full": 11.9, "pivot_full_date": D(2026, 8, 25), "pivot_tl": None, "pivot_tl_date": None,
               "adr20": 0.05, "close": 10.5, "rs_best": 99.0, "rs_all": 98.0, "grp_pct": None,
               "phase_qqq_10_20": True, "phase_qqq_10_20_s5": False, "phase_spy_qqq_50": True, "universe_n": 2000,
               "features": {"a": 1, "when": "2026-09-16"}, "cells": {"k5": {"C0": True}}}

        async def go():
            await db.cb_upsert_watch_rows([row])
            await db.cb_upsert_watch_rows([row | {"rs_best": 97.5, "pivot_tl": 11.1}])
            got = await db.cb_get_watch_rows(WATCH_NIGHT)
            return got, await db.cb_get_watch_poles(["AAA"], WATCH_NIGHT)
        got, poles = arun(env, go())
        assert len(got) == 1 and got[0]["rs_best"] == 97.5 and got[0]["pivot_tl"] == 11.1
        assert got[0]["features"] == {"a": 1, "when": "2026-09-16"} and got[0]["cells"] == {"k5": {"C0": True}}
        assert poles == [("AAA", D(2026, 8, 19))]

    def test_a_sic_row_is_an_upsert_on_ticker(self, env):
        async def go():
            await db.cb_upsert_sic_rows([{"ticker": "AAA", "sic_code": "2836", "sic2": "28", "sic_description": "x",
                                          "ticker_type": "CS", "status": "ok"}])
            await db.cb_upsert_sic_rows([{"ticker": "AAA", "sic_code": None, "sic2": None, "sic_description": None,
                                          "ticker_type": "CS", "status": "none"}])
            return await db.cb_get_sic(["AAA", "ZZZ"])
        got = arun(env, go())
        assert set(got) == {"AAA"} and got["AAA"]["status"] == "none" and got["AAA"]["fetched_at"] is not None


class TestReadHelpers:
    def test_the_universe_prefilter_is_a_superset_of_the_modules_universe(self, env):
        m = build_market(n_filler=5)
        arun(env, env.load(m))

        async def go():
            cal = await db.cb_get_calendar(WATCH_NIGHT)
            n = len(cal)
            rows = await db.cb_get_universe_bars(WATCH_NIGHT, cal[n - 150], cal[n - 20], min_price=cb.MIN_PRICE,
                                                 prefilter_dollar_vol=sh.PREFILTER_DOLLAR_VOL)
            return cal, rows
        cal, rows = arun(env, go())
        got = {r[0] for r in rows}
        ci_of = {d: i for i, d in enumerate(cal)}
        series, _ = sh.build_series(rows, ci_of)
        for t, (bars, _c) in series.items():                              # the module is the authority
            ok = cb.universe_ok(bars, len(bars) - 1, raw_factor=1.0, ticker=t, security_type=m.sectypes.get(t, ""))
            assert (not ok) or t in got
        assert {"MRNA"} <= got and all(len(series[t][0]) == 150 for t in series)
        assert cal[-1] == WATCH_NIGHT and len(cal) == len([d for d in m.cal if d <= WATCH_NIGHT])

    def test_the_accrual_predicate_does_not_count_a_split_voided_primary_arm(self, env):
        """`unbookable` is MATURE (final) but carries no R: a base whose primary arm a split voided is not a settled
        base. Three first-break C1 orh5 fills: one stopped (counts), one trailed (counts), one voided (does not),
        plus a settled retrigger and a settled non-C1 entry that must not count either."""
        import yaml
        from pathlib import Path
        reg = yaml.safe_load((Path(__file__).resolve().parent.parent / "data_gated_reviews.yaml").read_text())
        entries = reg["reviews"] if isinstance(reg, dict) else reg
        review = next(r for r in entries if r["review_id"] == "consolidation_breakout_forward_read")

        async def go():
            base = TestWriteGuards()._entry
            c1 = {"C0": True, "C1": True}
            fill = dict(status="filled", reason=None, fill=10.5, stop=10.0, cells=c1)
            await db.cb_upsert_entry_rows([
                base(ticker="AAA", base_id="AAA|x", **fill), base(ticker="BBB", base_id="BBB|x", **fill),
                base(ticker="CCC", base_id="CCC|x", **fill), base(ticker="DDD", base_id="DDD|x", **fill | {"retrigger": 1}),
                base(ticker="EEE", base_id="EEE|x", **fill | {"cells": {"C0": True}})])
            ids = {r["ticker"]: r["id"] for r in await TestWriteGuards()._entries(env)}
            ex = lambda t, **kw: {"entry_id": ids[t], "arm": cb.PRIMARY_ARM, "status": "stopped", "realized_r": -1.0,
                                  "pnl_adr": -0.1, "sessions_held": 2, "events": [], "n_fwd": 3, "mature": True,
                                  "reason": None, "last_bar_date": D(2026, 9, 21)} | kw
            await db.cb_upsert_exit_rows([
                ex("AAA"), ex("BBB", status="trailed", realized_r=2.5),
                ex("CCC", status="unbookable", realized_r=None, pnl_adr=None, sessions_held=None, n_fwd=0),
                ex("DDD"), ex("EEE")])
            return await _scalar(env, review["predicate_sql"])
        assert arun(env, go()) == 2                                     # AAA and BBB; not CCC (voided), DDD, EEE

    def test_the_open_entry_work_list_drops_an_entry_only_when_every_arm_is_mature(self, env):
        async def go():
            base = TestWriteGuards()._entry
            await db.cb_upsert_entry_rows([
                base(ticker="AAA", status="filled", reason=None, fill=10.5, stop=10.0),
                base(ticker="BBB", status="filled", reason=None, fill=10.5, stop=10.0),
                base(ticker="CCC", status="abstain", reason="too_wide")])
            ids = {r["ticker"]: r["id"] for r in await TestWriteGuards()._entries(env)}
            mk = lambda eid, arm, mature: {"entry_id": eid, "arm": arm, "status": "stopped" if mature else "degraded",
                                           "realized_r": 0.0, "pnl_adr": 0.0, "sessions_held": 1, "events": [],
                                           "n_fwd": 1, "mature": mature, "reason": None, "last_bar_date": BREAK_DAY}
            await db.cb_upsert_exit_rows([mk(ids["AAA"], a, True) for a in cb.ARMS]                       # all mature
                                         + [mk(ids["BBB"], a, a != "stop_only") for a in cb.ARMS])        # one open arm
            work = await db.cb_get_open_entries(len(cb.ARMS), D(2000, 1, 1))
            after = await db.cb_get_open_entries(len(cb.ARMS), BREAK_DAY + dt.timedelta(days=1))     # BBB now older
            stale = await db.cb_count_stale_open_entries(len(cb.ARMS), BREAK_DAY + dt.timedelta(days=1))
            fresh = await db.cb_count_stale_open_entries(len(cb.ARMS), D(2000, 1, 1))
            return ids, work, after, stale, fresh
        ids, work, after, stale, fresh = arun(env, go())
        assert [w["ticker"] for w in work] == ["BBB"]              # AAA is final, CCC never filled
        assert sorted(work[0]["mature_arms"]) == sorted(a for a in cb.ARMS if a != "stop_only")   # the walk skips these
        assert after == [] and stale == 1 and fresh == 0           # the bound moves BBB from the work list to the stale count

    def test_the_split_helpers_honour_both_bounds(self, env):
        async def go():
            async with env.pool.acquire() as c:
                await c.executemany("INSERT INTO mi_splits (ticker, execution_date, split_from, split_to, "
                                    "adjustment_applied) VALUES ($1,$2,$3,$4,$5)",
                                    [("AAA", D(2026, 9, 17), 1, 4, False), ("BBB", D(2026, 12, 1), 1, 4, False),
                                     ("CCC", D(2026, 9, 17), 1, 4, True), ("DDD", D(2026, 1, 5), 1, 2, False),
                                     ("EEE", D(2099, 1, 1), 1, 4, False)])
            unapplied = {s["ticker"] for s in await db.get_unapplied_splits(D(2026, 2, 1), upto=D(2026, 9, 17))}
            default_bound = {s["ticker"] for s in await db.get_unapplied_splits(D(2026, 2, 1))}     # upto=None: CURRENT_DATE
            explicit_far = {s["ticker"] for s in await db.get_unapplied_splits(D(2026, 2, 1), upto=D(2099, 6, 1))}
            after = await db.cb_get_splits_after(["AAA", "BBB", "CCC", "DDD"], D(2026, 9, 16), D(2026, 9, 18))
            return unapplied, default_bound, explicit_far, after
        unapplied, default_bound, explicit_far, after = arun(env, go())
        assert unapplied == {"AAA"}                                       # BBB is announced only; CCC applied; DDD outside
        assert "EEE" not in default_bound and "AAA" in default_bound      # the original CURRENT_DATE bound still holds
        assert explicit_far == {"AAA", "BBB", "EEE"}                      # an explicit `upto` replaces it, not adds to it
        assert set(after) == {"AAA", "CCC"} and after["AAA"][0]["split_to"] == 4


# ═══════════════════════════════════════════════════════════════════════════════════════════════
async def _scalar(env, sql):
    async with env.pool.acquire() as c:
        return await c.fetchval(sql)


def _norm_entries(rows):
    out = {}
    for r in rows:
        key = (r["ticker"], r["pole_date"], r["k"], r["entry_variant"], r["break_date"])
        out[key] = (r["status"], r["reason"], r["fill"], r["stop"], r["fill_minute"], r["width_pct"], r["level"],
                    r["day0_stopped"], r["day0_exit_price"], r["day0_exit_minute"], r["retrigger"],
                    r["retrigger_chain"], r["base_id"], dict(r["cells"]), dict(r["first_cells"]),
                    dict(r["first_chain_cells"]), r["minutes_state"], r["feed"], r["gap_pct"])
    return out


class TestTheJobOnRealSql:
    def test_the_job_writes_the_same_rows_on_postgres_as_on_the_in_memory_store(self, env, monkeypatch):
        market = build_market(future=24, clone_mrna=True)
        r = {x[0]: x for x in market.bars["MRNA"]}[BREAK_DAY]
        r2 = {x[0]: x for x in market.bars["MRNB"]}[BREAK_DAY]
        minutes = {("MRNA", BREAK_DAY): synth_minutes(BREAK_DAY, *r[1:5]),
                   ("MRNB", BREAK_DAY): synth_minutes(BREAK_DAY, *r2[1:5], dip_after=45)}
        nights = market.cal[market.cal.index(WATCH_NIGHT):market.cal.index(BREAK_DAY) + 12]

        # 1. the in-memory store
        store = FakeStore(market)
        store.install(monkeypatch, sh)
        FakeCollector(market, minutes_for=minutes, polygon=lambda p: {"results": {"sic_code": "2836", "type": "CS"}}
                      ).install(monkeypatch)
        for d in nights:
            asyncio.run(sh.run_consolidation_breakout_shadow(d))
        fake = {"watch": store.watch, "entry": store.entry, "exit": store.exit, "sic": store.sic}

        # 2. real Postgres, the real db functions
        monkeypatch.undo()
        monkeypatch.setattr(db, "get_pool", lambda: asyncio.sleep(0, result=env.pool))
        FakeCollector(market, minutes_for=minutes, polygon=lambda p: {"results": {"sic_code": "2836", "type": "CS"}}
                      ).install(monkeypatch)
        arun(env, env.load(market))

        async def go():
            for d in nights:
                await sh.run_consolidation_breakout_shadow(d)
            async with env.pool.acquire() as c:
                return ([dict(x) for x in await c.fetch("SELECT * FROM mi_consolidation_breakout_watch")],
                        [dict(x) for x in await c.fetch("SELECT * FROM mi_consolidation_breakout_entry")],
                        [dict(x) for x in await c.fetch(
                            "SELECT e.ticker, e.pole_date, e.k, e.entry_variant, e.break_date, x.* "
                            "FROM mi_consolidation_breakout_exit x JOIN mi_consolidation_breakout_entry e "
                            "ON e.id = x.entry_id")],
                        [dict(x) for x in await c.fetch("SELECT * FROM mi_consolidation_breakout_sic")],
                        [dict(x) for x in await c.fetch("SELECT event_type, summary FROM mi_audit_log")])
        watch, entry, exits, sic, audit = arun(env, go())

        # watch rows
        assert {(w["ticker"], w["scan_date"]) for w in watch} == set(fake["watch"])
        for w in watch:
            f = fake["watch"][(w["ticker"], w["scan_date"])]
            for col in ("pole_date", "pivot_k5", "pivot_k10", "pivot_full", "pivot_tl", "adr20", "rs_best",
                        "grp_pct", "phase_qqq_10_20", "universe_n"):
                assert w[col] == f[col], col
            assert w["cells"] == f["cells"] and w["features"] == f["features"]
        # entries (the natural key carries everything; ids differ by design)
        got = _norm_entries(entry)
        want = _norm_entries(fake["entry"].values())
        assert got.keys() == want.keys() and len(got) > 40
        for key in want:
            assert got[key] == want[key], key
        assert any(v[7] is True for v in got.values()) and any(v[0] == "abstain" for v in got.values())
        # exits
        by_id = {v["id"]: k for k, v in fake["entry"].items()}
        want_x = {(by_id[eid], arm): x for (eid, arm), x in fake["exit"].items()}
        got_x = {((x["ticker"], x["pole_date"], x["k"], x["entry_variant"], x["break_date"]), x["arm"]): x for x in exits}
        assert got_x.keys() == want_x.keys() and len(got_x) >= 15 * 30
        for key, x in got_x.items():
            w = want_x[key]
            assert (x["status"], x["mature"], x["sessions_held"], x["n_fwd"], x["last_bar_date"]) == \
                (w["status"], w["mature"], w["sessions_held"], w["n_fwd"], w["last_bar_date"]), key
            assert (x["realized_r"] is None) == (w["realized_r"] is None)
            if w["realized_r"] is not None:
                assert x["realized_r"] == pytest.approx(w["realized_r"], abs=1e-12)
        assert {s["ticker"] for s in sic} == set(fake["sic"])
        assert sum(1 for a in audit if a["event_type"] == sh.AUDIT_RUN_EVENT) == len(nights)

        # the accrual review's predicate (data_gated_reviews.yaml) EXECUTES on the real tables and counts what the
        # in-memory run says it should: distinct bases with a mature primary-arm exit on a first-break C1 orh5 fill
        import yaml
        from pathlib import Path
        reg = yaml.safe_load((Path(__file__).resolve().parent.parent / "data_gated_reviews.yaml").read_text())
        entries = reg["reviews"] if isinstance(reg, dict) else reg
        review = next(r for r in entries if r["review_id"] == "consolidation_breakout_forward_read")
        n = arun(env, _scalar(env, review["predicate_sql"]))
        by_id2 = {v["id"]: v for v in fake["entry"].values()}
        want_bases = {(by_id2[eid]["ticker"], by_id2[eid]["pole_date"]) for (eid, arm), x in fake["exit"].items()
                      if arm == cb.PRIMARY_ARM and x["mature"] and x["realized_r"] is not None
                      and by_id2[eid]["entry_variant"] == "orh5"
                      and by_id2[eid]["status"] == "filled" and by_id2[eid]["retrigger"] == 0
                      and by_id2[eid]["cells"].get("C1")}
        assert n == len(want_bases) and n >= 1 and review["threshold"] == 30


class TestASplitNightOnRealSql:
    @pytest.mark.parametrize("split_from,split_to,ratio", [(1, 4, 4.0), (4, 1, 0.25)],
                             ids=["forward_1_for_4", "reverse_4_for_1"])
    def test_a_split_between_the_watch_night_and_the_break_day_writes_the_named_rows(
            self, env, monkeypatch, split_from, split_to, ratio):
        """The split guard's reads (splits after D, the unapplied set, D's stored bar) and the watch row's `close`
        run for real: the stored bars are put on the post-split scale in SQL, the pivot is still raw from night D."""
        market = build_market(future=3)
        r = {x[0]: x for x in market.bars["MRNA"]}[BREAK_DAY]
        coll = FakeCollector(market, minutes_for={("MRNA", BREAK_DAY): synth_minutes(BREAK_DAY, *r[1:5])},
                             polygon=lambda p: {"results": {"sic_code": "2836", "type": "CS"}})
        coll.install(monkeypatch)
        arun(env, env.load(market))

        async def go():
            await sh.run_consolidation_breakout_shadow(WATCH_NIGHT)
            async with env.pool.acquire() as c:
                w = dict(await c.fetchrow("SELECT * FROM mi_consolidation_breakout_watch WHERE ticker = 'MRNA'"))
                await c.execute("UPDATE mi_daily_closes SET open_price = open_price / $1, high_price = high_price / $1, "
                                "low_price = low_price / $1, close = close / $1, volume = (volume * $1)::bigint "
                                "WHERE ticker = 'MRNA'", ratio)
                await c.execute("INSERT INTO mi_splits (ticker, execution_date, split_from, split_to, "
                                "adjustment_applied) VALUES ('MRNA', $1, $2, $3, TRUE)", BREAK_DAY, split_from, split_to)
            out = await sh.run_consolidation_breakout_shadow(BREAK_DAY)
            async with env.pool.acquire() as c:
                rows = [dict(x) for x in await c.fetch("SELECT * FROM mi_consolidation_breakout_entry "
                                                       "WHERE break_date = $1", BREAK_DAY)]
            return w, out, rows
        w, out, rows = arun(env, go())
        assert len(rows) == 20 and {(x["status"], x["reason"]) for x in rows} == {("abstain", sh.SPLIT_REASON)}
        assert out["entry_split_rescaled"] == 1 and out["entry_split_unresolved"] == 0 and not coll.minute_calls
        for x in rows:
            assert x["pivot"] == pytest.approx(w[f"pivot_{x['k']}"] / ratio)
