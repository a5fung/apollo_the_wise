"""#697 item 5 (2026-10-11) — the hysteresis holds a downgrade ONE night, as documented.

`flag_continuation.md` ("Hysteresis") and the `compute_flag_metrics` docstring say a single-day downward
stage flip is "held one day". The code fed the STORED (already held) stage back in as `yesterday_stage`,
so the hold re-armed every night until INVALIDATED or a pivot reset: in the 60 days to 2026-10-09, 21 of 40
COILED rows, 12 of 16 TRIGGERED rows and 11 of 102 TIGHTENING rows were holds (htf_scope G4,
`scripts/probes/_697/item5_replay_hold.out`). The fix: hold only when yesterday's stored row was itself NOT a
hold (`held_from_stage IS NULL`).

Every test below fails on the pre-item-5 branch (no `stage_after_hold`, no `yesterday_was_held`, no
`get_yesterday_flag_holds`). No threshold, window, floor or stage rule moves: the raw reading is unchanged.
"""
from __future__ import annotations

import itertools
import logging
from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import briefing, db, ma_filter
from agents.market_intelligence import flag_detector as fd
from tests.conftest import make_mock_pool

RAW_STAGES = ("WATCH", "TIGHTENING", "COILED", "TRIGGERED")   # what reaches the hysteresis step
RANK = {s: i for i, s in enumerate(fd._STAGE_ORDER)}


# ── the rule, pure ──────────────────────────────────────────────────────────

def test_a_downgrade_is_held_one_night_when_yesterday_was_a_normal_reading():
    assert fd.stage_after_hold("TIGHTENING", "COILED", False) == ("COILED", "TIGHTENING")
    assert fd.stage_after_hold("WATCH", "TRIGGERED", False) == ("TRIGGERED", "WATCH")
    # the default is "yesterday was not a hold": the FIRST night is still held (the documented day)
    assert fd.stage_after_hold("TIGHTENING", "COILED") == ("COILED", "TIGHTENING")


def test_a_hold_is_never_followed_by_a_hold():
    """The bug: yesterday's stored stage was itself a hold, and it was held again."""
    assert fd.stage_after_hold("TIGHTENING", "COILED", True) == ("TIGHTENING", None)
    assert fd.stage_after_hold("WATCH", "TRIGGERED", True) == ("WATCH", None)


def test_the_rejected_variant_is_not_what_ships():
    """Compare against yesterday's RAW read instead of yesterday's stored stage and a second-step
    downgrade is held again: COILED stored, raw TIGHTENING (held COILED), then raw WATCH would hold at
    TIGHTENING. The rule here is a hold of exactly one night — the reading stands."""
    assert fd.stage_after_hold("WATCH", "COILED", True) == ("WATCH", None)


@pytest.mark.parametrize("proposed,yesterday", [
    ("COILED", "TIGHTENING"),        # upgrade
    ("COILED", "COILED"),            # equal
    ("TRIGGERED", "WATCH"),          # upgrade
    ("WATCH", None),                 # no yesterday
    ("WATCH", "INVALIDATED"),        # INVALIDATED is not in the stage order: never held against
    ("TIGHTENING", "unqualified"),
])
@pytest.mark.parametrize("was_held", [False, True])
def test_everything_but_a_downgrade_is_untouched(proposed, yesterday, was_held):
    assert fd.stage_after_hold(proposed, yesterday, was_held) == (proposed, None)


def test_exhaustive_chains_never_hold_twice_and_only_differ_after_a_double_hold():
    """Every raw-reading sequence of length 1..5 over the four stages (1,364 chains), threaded the way
    prod stores them. New rule: no two consecutive holds; an un-held night shows the raw reading; a held
    night shows yesterday's stage. Against the old rule the output differs ONLY from the first night a
    second consecutive hold would have been written."""
    n_chains = 0
    for length in range(1, 6):
        for raw in itertools.product(RAW_STAGES, repeat=length):
            n_chains += 1
            old, new = [], []
            for i, r in enumerate(raw):
                if i == 0:
                    old.append((r, None))
                    new.append((r, None))
                    continue
                old.append(fd.stage_after_hold(r, old[-1][0], False))
                new.append(fd.stage_after_hold(r, new[-1][0], new[-1][1] is not None))
            for i, (st, hf) in enumerate(new):
                if hf is None:
                    assert st == raw[i]
                else:
                    assert st == new[i - 1][0] and RANK[st] > RANK[raw[i]] and hf == raw[i]
                    assert new[i - 1][1] is None, f"two consecutive holds in {raw}"
            first_double = next((i for i in range(1, length) if old[i][1] and old[i - 1][1]), None)
            for i in range(length):
                if first_double is None or i < first_double:
                    assert old[i] == new[i], f"{raw}: diverged before any double hold"
            if first_double is not None:
                assert old[first_double] != new[first_double]
    assert n_chains == sum(4 ** k for k in range(1, 6))


# ── compute_flag_metrics: the kwarg reaches the rule ────────────────────────

def _rows():
    """base -> pole -> flag; today reads WATCH (runup 128%, 12% under the pivot)."""
    rows, d0 = [], date(2026, 1, 1)
    di = 0

    def add(o, h, l, c, v):
        nonlocal di
        rows.append({"trade_date": d0 + timedelta(days=di), "open_price": o, "high_price": h,
                     "low_price": l, "close": c, "volume": v})
        di += 1
    for _ in range(42):
        add(10.0, 10.1, 9.9, 10.0, 1_000_000)
    for j in range(20):
        p = 10.0 + 12.0 * ((j + 1) / 20)
        add(p * 0.99, p * 1.025, p * 0.975, p, 3_000_000 if j == 10 else 1_000_000)
    fp = 22.0 * 0.9
    for _ in range(8):
        add(fp, fp * 1.025, fp * 0.975, fp, 800_000)
    return rows


def test_compute_flag_metrics_holds_the_first_night_and_releases_the_second():
    rows = _rows()
    raw = fd.compute_flag_metrics(rows, ticker="TST", recent_stages=[])
    assert raw["stage"] == "WATCH" and raw["held_from_stage"] is None

    night1 = fd.compute_flag_metrics(rows, ticker="TST", recent_stages=[], yesterday_stage="COILED")
    assert (night1["stage"], night1["held_from_stage"]) == ("COILED", "WATCH")        # the documented day

    night2 = fd.compute_flag_metrics(rows, ticker="TST", recent_stages=[],
                                     yesterday_stage=night1["stage"],
                                     yesterday_was_held=night1["held_from_stage"] is not None)
    assert (night2["stage"], night2["held_from_stage"]) == ("WATCH", None)            # the reading stands
    # nothing else about the row moved
    for k in ("score", "reason", "base_high", "base_age", "pivot_high_price", "runup_pct"):
        assert night2[k] == raw[k] == night1[k]


# ── the db readers: one query, one row, both answers ────────────────────────

@pytest.mark.asyncio
async def test_the_stage_and_the_hold_flag_come_from_the_same_row(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[
        {"ticker": "AAA", "stage": "COILED", "held_from_stage": "TIGHTENING"},
        {"ticker": "BBB", "stage": "COILED", "held_from_stage": None},
        {"ticker": "CCC", "stage": "WATCH", "held_from_stage": None},
    ])
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))

    stages = await db.get_yesterday_flag_stages(date(2026, 10, 12))
    holds = await db.get_yesterday_flag_holds(date(2026, 10, 12))

    assert stages == {"AAA": "COILED", "BBB": "COILED", "CCC": "WATCH"}
    assert holds == {"AAA"}
    sqls = [c.args[0] for c in conn.fetch.await_args_list]
    assert len(sqls) == 2 and sqls[0] == sqls[1]                                      # literally the same statement
    sql = " ".join(sqls[0].split())
    assert "DISTINCT ON (ticker)" in sql and "held_from_stage" in sql
    assert "scan_date >= $1 - INTERVAL '5 days'" in sql and "ORDER BY ticker, scan_date DESC" in sql


@pytest.mark.asyncio
async def test_a_failed_hold_read_is_loud_not_an_empty_set(monkeypatch):
    """An empty set on error would hold every downgrade night after night again — silently."""
    monkeypatch.setattr(db, "get_pool", AsyncMock(side_effect=RuntimeError("pool down")))
    with pytest.raises(RuntimeError):
        await db.get_yesterday_flag_holds(date(2026, 10, 12))


# ── the wiring: run_flag_scan, several nights, in-memory table ──────────────

class _Table:
    """mi_flag_candidates in memory: what insert_flag_candidate writes, read back the way the two db
    readers do (most recent prior row within 5 calendar days)."""

    def __init__(self):
        self.rows: list[dict] = []
        self.sent: list[str] = []
        self.kwargs: list[dict] = []
        self.night = 0

    def prior(self, scan_date):
        best = {}
        for r in sorted(self.rows, key=lambda r: r["scan_date"]):
            if r["scan_date"] < scan_date and (scan_date - r["scan_date"]).days <= 5:
                best[r["ticker"]] = r
        return best


@pytest.fixture
def table(monkeypatch):
    t = _Table()

    async def _send(text, chat_id=None, parse_mode=None, reply_markup=None):
        t.sent.append(text)
        return True

    async def _insert(m):
        t.rows.append({"ticker": m["ticker"], "scan_date": m["scan_date"], "stage": m["stage"],
                       "held_from_stage": m.get("held_from_stage")})

    async def _stages(scan_date):
        return {k: r["stage"] for k, r in t.prior(scan_date).items()}

    async def _holds(scan_date):
        return {k for k, r in t.prior(scan_date).items() if r["held_from_stage"]}

    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(briefing, "send_telegram_message", _send)
    monkeypatch.setattr(db, "log_audit_event", AsyncMock())
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(db, "insert_flag_candidate", _insert)
    monkeypatch.setattr(db, "get_yesterday_flag_stages", _stages)
    monkeypatch.setattr(db, "get_yesterday_flag_holds", _holds)
    monkeypatch.setattr(db, "get_recent_flag_stages", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_rs_for_tickers", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_sectors_batch", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_yesterday_flag_pivots", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_flag_failure_carry", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_recent_daily_history", AsyncMock(return_value=[{}] * 80))
    monkeypatch.setattr(fd, "_check_deal_pin_signatures_batch", AsyncMock(return_value={}))
    monkeypatch.setattr(fd, "reconcile_flag_state_post_eod", AsyncMock())
    monkeypatch.setattr(ma_filter, "is_likely_ma", AsyncMock(return_value=(False, {})))
    monkeypatch.setattr(ma_filter, "should_log_mna_filter_fired", AsyncMock(return_value=False))
    return t


def _install_raw(monkeypatch, table, raw_by_night):
    """compute_flag_metrics replaced by: the night's RAW reading, then the REAL hysteresis step fed with
    exactly what run_flag_scan handed over. raw_by_night: {scan_date: {ticker: raw stage}}."""
    def _metrics(history, ticker=None, **kw):
        table.kwargs.append({"ticker": ticker, **kw})
        # the scan stamps scan_date AFTER this returns, so the night comes from the test's own counter
        night = sorted(raw_by_night)[table.night]
        raw = raw_by_night[night][ticker]
        stage, held = fd.stage_after_hold(raw, kw.get("yesterday_stage"), kw.get("yesterday_was_held", False))
        return {"ticker": ticker, "stage": stage, "held_from_stage": held, "reason": "x",
                "runup_pct": 1.3, "pivot_high_price": 50.0, "base_age": 10,
                "range_contraction_ratio": 0.9, "vol_contraction_ratio": 0.9, "fresh_tight_fires": False}
    monkeypatch.setattr(fd, "compute_flag_metrics", _metrics)


@pytest.mark.asyncio
async def test_run_flag_scan_holds_exactly_one_night_end_to_end(table, monkeypatch, caplog):
    """AAA reads COILED then TIGHTENING for three nights; BBB reads COILED then WATCH; CCC climbs.
    Night 1 stores the reading, night 2 holds (the documented day), night 3 stores what was read."""
    nights = [date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)]
    raw = {
        nights[0]: {"AAA": "COILED", "BBB": "COILED", "CCC": "WATCH"},
        nights[1]: {"AAA": "TIGHTENING", "BBB": "WATCH", "CCC": "TIGHTENING"},
        nights[2]: {"AAA": "TIGHTENING", "BBB": "WATCH", "CCC": "COILED"},
    }
    _install_raw(monkeypatch, table, raw)
    caplog.set_level(logging.INFO, logger=fd.logger.name)
    for i, d in enumerate(nights):
        table.night = i
        monkeypatch.setattr(db, "get_flag_universe",
                            AsyncMock(return_value={t: ["rs_top200"] for t in raw[d]}))
        await fd.run_flag_scan(d)

    # the every-night wiring proof the live verify reads: how many names' yesterday was a hold
    carried = {r.getMessage().split(":")[0]: r.getMessage().rsplit("holds_carried=", 1)[1]
               for r in caplog.records if "holds_carried=" in r.getMessage()}
    assert carried == {f"flag_scan {nights[0]}": "0", f"flag_scan {nights[1]}": "0", f"flag_scan {nights[2]}": "2"}

    got = {(r["scan_date"], r["ticker"]): (r["stage"], r["held_from_stage"]) for r in table.rows}
    assert got[(nights[0], "AAA")] == ("COILED", None)
    assert got[(nights[1], "AAA")] == ("COILED", "TIGHTENING")          # night 1 of the downgrade: held
    assert got[(nights[2], "AAA")] == ("TIGHTENING", None)              # night 2: the reading stands
    assert got[(nights[1], "BBB")] == ("COILED", "WATCH")
    assert got[(nights[2], "BBB")] == ("WATCH", None)
    assert got[(nights[2], "CCC")] == ("COILED", None)                  # upgrades fire at once

    # what run_flag_scan handed compute_flag_metrics on night 3
    n3 = {k["ticker"]: k for k in table.kwargs[-3:]}
    assert n3["AAA"]["yesterday_stage"] == "COILED" and n3["AAA"]["yesterday_was_held"] is True
    assert n3["CCC"]["yesterday_stage"] == "TIGHTENING" and n3["CCC"]["yesterday_was_held"] is False


@pytest.mark.asyncio
async def test_the_digest_still_gets_the_stored_stage_map(table, monkeypatch):
    """`stage_transitions` reads {ticker: stage}: the shape db.get_yesterday_flag_stages returns is unchanged."""
    d = date(2026, 10, 6)
    table.rows.append({"ticker": "AAA", "scan_date": date(2026, 10, 5), "stage": "WATCH", "held_from_stage": None})
    monkeypatch.setattr(db, "get_flag_universe", AsyncMock(return_value={"AAA": ["rs_top200"]}))
    _install_raw(monkeypatch, table, {d: {"AAA": "TIGHTENING"}})
    seen = {}
    real = fd.send_flag_digest

    async def _spy(by_stage, scan_date, yesterday_map=None, **kw):
        seen["map"] = yesterday_map
        return await real(by_stage, scan_date, yesterday_map=yesterday_map, **kw)
    monkeypatch.setattr(fd, "send_flag_digest", _spy)
    await fd.run_flag_scan(d)
    assert seen["map"] == {"AAA": "WATCH"}


# ── the stored-row replay behind the numbers in the SSoT ────────────────────

def _replay_module():
    import importlib.util
    import pathlib
    path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "probes" / "_697" / "item5_replay_hold.py"
    spec = importlib.util.spec_from_file_location("_item5_replay_hold", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_replay_on_prods_stored_rows_reproduces_the_old_chain_and_ends_every_double_hold():
    """`item5_q1_hold_rows.out` is one read-only prod pull (92 tickers, 70 scan dates to 2026-10-09). The OLD
    rule re-threaded from each row's raw reading must reproduce what prod stored (else the replay measures
    nothing); the NEW rule must write no hold after a hold, change only rows downstream of one, and leave
    every real (un-held) TRIGGERED read alone."""
    m = _replay_module()
    rows = m.load()
    all_dates = sorted({r["d"] for rs in rows.values() for r in rs})
    window = set(all_dates[-m.REPORT_DAYS:])

    n = ok = held_old = held_new = changed = consec_old = consec_new = real = real_same = 0
    for rs in rows.values():
        old, new = m.thread(rs, False), m.thread(rs, True)
        for i, r in enumerate(rs):
            if r["d"] not in window:
                continue
            n += 1
            ok += old[i] == (r["stage"], r["held"])
            held_old += bool(old[i][1])
            held_new += bool(new[i][1])
            changed += old[i] != new[i]
            if i and (r["d"] - rs[i - 1]["d"]).days <= m.LOOKBACK:
                consec_old += bool(old[i][1] and old[i - 1][1])
                consec_new += bool(new[i][1] and new[i - 1][1])
            if r["stage"] == "TRIGGERED" and not r["held"]:
                real += 1
                real_same += new[i] == (r["stage"], r["held"])

    assert ok == n == 2707                         # the old rule reproduces prod's stored chain on every row
    assert held_old == 44                          # 21 COILED + 12 TRIGGERED + 11 TIGHTENING (htf_scope G4)
    assert held_new == 21 and changed == 24        # the first night of each hold stays; 24 rows stop being one
    assert consec_old == 24 and consec_new == 0    # every changed row is a hold that followed a hold
    assert real == 4 and real_same == 4            # CHYM, IOVA, WDAY, XHLD: no real TRIGGERED read moves
