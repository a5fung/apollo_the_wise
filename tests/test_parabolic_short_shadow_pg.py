"""#314 - the parabolic-short shadow's SQL, run for REAL.

`tests/test_parabolic_short_shadow.py` runs the nightly step against an in-memory store that reproduces the INSERT-ONCE
write guard and the two readers' joins. This file is the proof that the reproduction is faithful: the DDL, the insert
(`ON CONFLICT DO NOTHING ... RETURNING id`, a jsonb parameter beside plain ones), the candidate anti-join and the
open-episode join are executed against a REAL Postgres, and the whole step is run on both stores over the same bars
with the rows compared one by one.

SKIPPED unless `PS_SHADOW_TEST_PG_DSN` names a throwaway Postgres (each run works in its own schema, dropped at the end):

    PS_SHADOW_TEST_PG_DSN='postgresql://postgres:@/postgres?host=/path/to/socket' python -m pytest tests/test_parabolic_short_shadow_pg.py
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import timedelta

import pytest

from agents.market_intelligence import db
from agents.market_intelligence import parabolic_short_shadow as psh
from tests.test_parabolic_short_shadow import (D, ETB, HTB, TRIGGER_THEN_TIME_STOP, Env, _Facade, _never_earnings,
                                               market)

PG_DSN = os.environ.get("PS_SHADOW_TEST_PG_DSN")
pytestmark = pytest.mark.skipif(not PG_DSN, reason="set PS_SHADOW_TEST_PG_DSN to a throwaway Postgres to run the SQL for real")

asyncpg = pytest.importorskip("asyncpg")

# The two tables the shadow READS (only the columns it uses; types as in db.initialize_schema).
BASE_DDL = """
CREATE TABLE mi_daily_closes (trade_date DATE NOT NULL, ticker TEXT NOT NULL, close FLOAT NOT NULL, volume BIGINT,
    open_price FLOAT, high_price FLOAT, low_price FLOAT, PRIMARY KEY (trade_date, ticker));
CREATE TABLE mi_parabolic_candidates (id SERIAL PRIMARY KEY, ticker TEXT NOT NULL, scan_date DATE NOT NULL,
    market_cap BIGINT, cap_tier TEXT, stage TEXT NOT NULL, excluded_reason TEXT, UNIQUE (ticker, scan_date));
"""

COMPARED = ("ticker", "climax_date", "row_kind", "event_date", "status", "reason", "climax_high", "climax_low",
            "prior_day_low", "limit_price", "atr_14", "stop_buffer", "stop_price", "risk_per_share", "risk_fraction",
            "market_cap", "borrow_acct", "shortable", "easy_to_borrow", "asset_status", "entry_price", "exit_price",
            "exit_date", "sessions_held", "flush_taken", "flush_price", "realized_r", "exit_leg_r", "mfe_r", "mae_r")


class PgEnv:
    def __init__(self, pool, schema, loop):
        self.pool, self.schema, self.loop = pool, schema, loop
        self.plan: dict = {}
        self.borrow_calls: list = []

    def run(self, coro):
        return self.loop.run_until_complete(coro)

    async def load(self, ticker, post, *, mcap=1_000_000_000, scan_date=None, excluded=None, stage="climax"):
        async with self.pool.acquire() as c:
            await c.executemany(
                "INSERT INTO mi_daily_closes (trade_date, ticker, open_price, high_price, low_price, close, volume) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7)",
                [(b["trade_date"], ticker, b["open_price"], b["high_price"], b["low_price"], b["close"], b["volume"])
                 for b in market(post)])
            await c.execute(
                "INSERT INTO mi_parabolic_candidates (ticker, scan_date, market_cap, cap_tier, stage, excluded_reason) "
                "VALUES ($1,$2,$3,'small',$4,$5)", ticker, scan_date or D[0], mcap, stage, excluded)

    async def rows(self):
        async with self.pool.acquire() as c:
            return [dict(r) for r in await c.fetch(
                "SELECT * FROM mi_parabolic_short_shadow ORDER BY ticker, climax_date, "
                "CASE row_kind WHEN 'arm' THEN 0 WHEN 'trigger' THEN 1 ELSE 2 END")]

    async def night(self, k):
        return await psh.run_parabolic_short_shadow(D[k], earnings_checker=_never_earnings)


@pytest.fixture
def pg(monkeypatch):
    holder = {}

    async def setup():
        admin = await asyncpg.connect(PG_DSN)
        schema = "pst_" + uuid.uuid4().hex[:10]
        await admin.execute(f"CREATE SCHEMA {schema}")

        async def init(conn):
            await conn.set_type_codec("jsonb", encoder=db._json_encoder, decoder=db._json_decoder, schema="pg_catalog")
        # search_path as a STARTUP parameter: asyncpg's pool runs RESET ALL on release, which would silently drop a SET
        pool = await asyncpg.create_pool(PG_DSN, init=init, min_size=1, max_size=4, server_settings={"search_path": schema})
        async with pool.acquire() as c:
            await c.execute(BASE_DDL)
            await c.execute(db._PARABOLIC_SHORT_SHADOW_DDL)
        holder.update(admin=admin, schema=schema, pool=pool)
        return pool, schema

    loop = asyncio.new_event_loop()
    pool, schema = loop.run_until_complete(setup())

    async def gp():
        return pool
    monkeypatch.setattr(db, "get_pool", gp)
    e = PgEnv(pool, schema, loop)
    audit: list = []

    async def _audit(event_type, summary, detail=""):
        audit.append((event_type, summary))

    async def _enabled(_strategy_id):
        return True
    monkeypatch.setattr(db, "log_audit_event", _audit)
    monkeypatch.setattr("agents.market_intelligence.strategies.registry.should_run", _enabled)
    monkeypatch.setattr(psh, "execution_client", _Facade(e))
    e.audit = audit
    yield e

    async def teardown():
        await holder["pool"].close()
        await holder["admin"].execute(f"DROP SCHEMA {holder['schema']} CASCADE")
        await holder["admin"].close()
    loop.run_until_complete(teardown())
    loop.close()


def _same(a, b):
    assert len(a) == len(b), (len(a), len(b))
    for x, y in zip(a, b):
        for col in COMPARED:
            xv, yv = x.get(col), y.get(col)
            if isinstance(xv, float) or isinstance(yv, float):
                assert xv == pytest.approx(yv), (x["row_kind"], col, xv, yv)
            else:
                assert xv == yv, (x["row_kind"], col, xv, yv)


class TestStatements:
    def test_the_ddl_is_idempotent_and_the_insert_prepares_with_one_parameter_per_column(self, pg):
        async def go():
            async with pg.pool.acquire() as c:
                for _ in range(2):
                    await c.execute(db._PARABOLIC_SHORT_SHADOW_DDL)
                st = await c.prepare(db.PS_SHADOW_INSERT_SQL)
                idx = {r["indexname"] for r in await c.fetch(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = $1", pg.schema)}
                return len(st.get_parameters()), idx
        n, idx = pg.run(go())
        assert n == len(db.PS_SHADOW_COLS) and "idx_parabolic_short_shadow_kind_date" in idx

    def test_every_written_column_exists_in_the_real_table(self, pg):
        async def go():
            async with pg.pool.acquire() as c:
                return {r["column_name"] for r in await c.fetch(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema = $1 "
                    "AND table_name = 'mi_parabolic_short_shadow'", pg.schema)}
        assert set(db.PS_SHADOW_COLS) <= pg.run(go())

    def test_insert_once_returns_new_then_existing_and_never_overwrites(self, pg):
        row = {"ticker": "ZZZ", "climax_date": D[0], "row_kind": "arm", "event_date": D[0], "status": "armed",
               "stop_price": 163.07, "detail": {"d": D[0], "n": 1}}

        async def go():
            first = await db.insert_parabolic_short_shadow_row(row)
            second = await db.insert_parabolic_short_shadow_row({**row, "status": "rejected", "stop_price": 1.0})
            async with pg.pool.acquire() as c:
                got = await c.fetchrow("SELECT status, stop_price, jsonb_typeof(detail) AS t, detail "
                                       "FROM mi_parabolic_short_shadow")
            return first, second, dict(got)
        first, second, got = pg.run(go())
        assert (first, second) == (True, False)
        assert got["status"] == "armed" and got["stop_price"] == 163.07
        assert got["t"] == "object" and got["detail"]["n"] == 1            # a jsonb object, not a double-encoded string

    def test_the_row_kind_check_constraint_refuses_a_made_up_kind(self, pg):
        async def go():
            return await db.insert_parabolic_short_shadow_row(
                {"ticker": "ZZZ", "climax_date": D[0], "row_kind": "bogus", "event_date": D[0], "status": "x"})
        with pytest.raises(asyncpg.CheckViolationError):
            pg.run(go())

    def test_the_audit_and_trade_tables_are_not_touched_the_schema_holds_only_the_three_tables(self, pg):
        async def go():
            async with pg.pool.acquire() as c:
                return {r["table_name"] for r in await c.fetch(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = $1", pg.schema)}
        assert pg.run(go()) == {"mi_daily_closes", "mi_parabolic_candidates", "mi_parabolic_short_shadow"}


class TestReaders:
    def test_new_candidates_are_climax_unexcluded_in_window_and_without_an_arm_row(self, pg):
        async def go():
            await pg.load("OKK", TRIGGER_THEN_TIME_STOP)
            await pg.load("EXC", TRIGGER_THEN_TIME_STOP, excluded="acquisition: buyout")
            await pg.load("ANT", TRIGGER_THEN_TIME_STOP, stage="anticipation")
            await pg.load("OLD", TRIGGER_THEN_TIME_STOP, scan_date=D[0] - timedelta(days=30))
            await pg.load("DUN", TRIGGER_THEN_TIME_STOP)
            await db.insert_parabolic_short_shadow_row(
                {"ticker": "DUN", "climax_date": D[0], "row_kind": "arm", "event_date": D[0], "status": "rejected"})
            return [c["ticker"] for c in await db.get_parabolic_short_new_candidates(D[1])]
        assert pg.run(go()) == ["OKK"]

    def test_open_episodes_are_armed_without_an_outcome_and_carry_the_trigger_row(self, pg):
        async def go():
            for t in ("ARM", "TRG", "DON", "REJ"):
                await db.insert_parabolic_short_shadow_row(
                    {"ticker": t, "climax_date": D[0], "row_kind": "arm", "event_date": D[0],
                     "status": "rejected" if t == "REJ" else "armed", "stop_price": 163.07, "climax_high": 160.0})
            await db.insert_parabolic_short_shadow_row(
                {"ticker": "TRG", "climax_date": D[0], "row_kind": "trigger", "event_date": D[1], "status": "triggered",
                 "entry_price": 140.0})
            for t in ("DON",):
                await db.insert_parabolic_short_shadow_row(
                    {"ticker": t, "climax_date": D[0], "row_kind": "outcome", "event_date": D[2], "status": "settled"})
            return {e["ticker"]: e for e in await db.get_parabolic_short_open_episodes()}
        eps = pg.run(go())
        assert set(eps) == {"ARM", "TRG"}
        assert (eps["ARM"]["trigger_status"], eps["ARM"]["armed_on"], eps["ARM"]["stop_price"]) == (None, D[0], 163.07)
        assert (eps["TRG"]["trigger_status"], eps["TRG"]["trigger_date"], eps["TRG"]["trigger_entry"]) == ("triggered", D[1], 140.0)


class TestWholeStepOnRealSql:
    @pytest.mark.parametrize("plan,post,nights", [
        ([ETB], TRIGGER_THEN_TIME_STOP, (0, 1, 2, 3, 4, 5, 6)),                        # arm -> trigger -> time stop
        ([ETB], [(150, 153, 138, 139), (141, 155, 139, 150)], (0, 1, 2)),              # arm -> trigger -> trailing stop
        ([ETB], [(150, 152, 141, 148), (150, 153, 142, 149), (150, 154, 143, 150)], (0, 1, 2, 3)),   # expiry
        ([ETB], [(150, 162, 141, 161)], (0, 1)),                                       # invalidation
        ([HTB], TRIGGER_THEN_TIME_STOP, (0, 1)),                                       # rejected at the arm
        ([ETB, HTB], TRIGGER_THEN_TIME_STOP, (0, 1, 2)),                               # borrow flips by the trigger
    ])
    def test_the_real_sql_store_and_the_in_memory_store_write_the_same_rows(self, pg, monkeypatch, plan, post, nights):
        # in-memory run (patches db.* with the fake, so do it FIRST on its own monkeypatch scope)
        with monkeypatch.context() as mp:
            mem = Env(mp)
            mem.load("ZZZ", post)
            mem.plan["ZZZ"] = list(plan)

            async def drive_mem():
                for k in nights:
                    await mem.night(k)
            asyncio.run(drive_mem())
            expected = sorted(mem.rows, key=lambda r: ("arm", "trigger", "outcome").index(r["row_kind"]))

        pg.plan["ZZZ"] = list(plan)

        async def drive_pg():
            await pg.load("ZZZ", post)
            for k in nights:
                await pg.night(k)
            return await pg.rows()
        got = pg.run(drive_pg())
        _same(expected, got)
        assert len(pg.audit) == len(nights) and all(a[0] == "parabolic_short_shadow_run" for a in pg.audit)

    def test_a_second_run_of_the_same_night_adds_nothing(self, pg):
        pg.plan["ZZZ"] = [ETB]

        async def go():
            await pg.load("ZZZ", TRIGGER_THEN_TIME_STOP)
            for k in (0, 1, 5):
                await pg.night(k)
            before = await pg.rows()
            for k in (5, 5, 6):
                s = await pg.night(k)
                assert not (s["armed"] or s["triggered"] or s["settled"] or s["closed"] or s["errors"])
            return before, await pg.rows()
        before, after = pg.run(go())
        assert len(before) == len(after) == 3
