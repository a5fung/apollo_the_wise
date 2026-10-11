"""#697 item 2 (2026-10-11) — the HTF universe CARRY keeps a name on the board while its base lives.

WHAT WAS BROKEN (docs/analysis/htf_scope_2026-10-10.md §5, gap G1). `get_flag_universe` path (e) — the
05-19 RVMD-class carry — kept a name only if its last stored stage was COILED / TIGHTENING, and only
for 5 CALENDAR days:
  * a WATCH name fell off the board mid-base on any one-day RS percentile dip (19 of 304 WATCH rows /
    18 names in 60 days had no row the next scan day; GH's flat June base, HPE);
  * a name last stored TRIGGERED was skipped outright — WDAY, TRIGGERED 08-28/09-02, had NO row 09-03 -> 09-16,
    so its 09-08 close under the base low never stamped `failed_at` (#654 failure telemetry: 0 stamps ever);
  * "5 days" were calendar days (a Friday's rows are 3 calendar days old on Monday, a holiday week 5).

THE RULE NOW (read-only on admission criteria: it only decides which already-vetted names the scan SCORES;
every stage still comes from `compute_flag_metrics`, whose gates are untouched):
  * stored WATCH / TIGHTENING / COILED / TRIGGERED in the last 5 SCAN SESSIONS  -> tag `flag_stage_carryforward`;
  * else stored TIGHTENING / COILED / TRIGGERED in the last 25 scan sessions (the pivot lookback)
                                                                       -> tag `flag_pivot_window_carryforward`.
A scan SESSION is a scan date that was a market session (a `mi_daily_closes` row exists for it) — the
09-07 Labor Day partial scan (87 names, no bars) is not one.

Admit-count replay on stored rows: scripts/probes/_697/q1_admit_replay.out (summary: summarize_q1.out).
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import db as db_mod
from agents.market_intelligence import flag_detector as fd
from tests.conftest import make_mock_pool

SHORT_TAG = "flag_stage_carryforward"
LONG_TAG = "flag_pivot_window_carryforward"


def _carry(rows):
    return db_mod.flag_carry_sources(rows)


# ── the RULE (pure) ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("stage", ["WATCH", "TIGHTENING", "COILED", "TRIGGERED"])
@pytest.mark.parametrize("lag", [1, 3, 5])
def test_every_active_stage_is_carried_for_five_scan_sessions(stage, lag):
    assert _carry([{"ticker": "AAA", "stage": stage, "lag": lag}]) == {"AAA": [SHORT_TAG]}


def test_a_watch_name_is_not_carried_past_five_sessions():
    """WATCH memory is the short window only: a WATCH row 6+ sessions old has lapsed."""
    for lag in (6, 10, 25):
        assert _carry([{"ticker": "AAA", "stage": "WATCH", "lag": lag}]) == {}


@pytest.mark.parametrize("stage", ["TIGHTENING", "COILED", "TRIGGERED"])
def test_tightening_or_better_is_remembered_for_the_pivot_lookback(stage):
    """A name that reached TIGHTENING-or-better stays scored for 25 sessions, so post-breakout rows keep
    being written and #654 can stamp a failure that lands days later."""
    for lag in (6, 7, 25):
        assert _carry([{"ticker": "AAA", "stage": stage, "lag": lag}]) == {"AAA": [LONG_TAG]}
    assert _carry([{"ticker": "AAA", "stage": stage, "lag": 26}]) == {}


@pytest.mark.parametrize("stage", ["INVALIDATED", "unqualified", "", None])
def test_a_dead_or_unqualified_row_never_carries(stage):
    for lag in (1, 5, 10):
        assert _carry([{"ticker": "AAA", "stage": stage, "lag": lag}]) == {}


def test_the_short_tag_wins_and_the_long_tag_means_only_the_long_window_admits_it():
    """`flag_pivot_window_carryforward` is exclusive of the short tag: its presence says only the 25-session
    window admits the name; a name the short window also admits carries only the short tag. (Neither tag says
    no organic path admitted it too - 'kept only by the carry' is a carry tag AND no organic tag.)"""
    rows = [
        {"ticker": "BOTH", "stage": "WATCH", "lag": 2}, {"ticker": "BOTH", "stage": "TRIGGERED", "lag": 12},
        {"ticker": "LONG", "stage": "COILED", "lag": 14}, {"ticker": "LONG", "stage": "WATCH", "lag": 9},
        {"ticker": "GONE", "stage": "WATCH", "lag": 8},
    ]
    assert _carry(rows) == {"BOTH": [SHORT_TAG], "LONG": [LONG_TAG]}


def test_wday_the_triggered_name_that_never_stamped_is_now_carried():
    """WDAY: TRIGGERED 08-28, held TRIGGERED 08-31 / 09-01 / 09-02, then NO row 09-03 -> 09-16 (prod). The
    carry query used to skip stored TRIGGERED, so 09-08 (close under the base low) never stamped."""
    assert _carry([{"ticker": "WDAY", "stage": "TRIGGERED", "lag": 1}]) == {"WDAY": [SHORT_TAG]}
    # still remembered on the 09-08 scan: sessions back are 09-04 (1), 09-03 (2), 09-02 (3) - the 09-07
    # Labor Day scan is not a session - so its last TRIGGERED row is lag 3, inside the window
    assert _carry([{"ticker": "WDAY", "stage": "TRIGGERED", "lag": 3}]) == {"WDAY": [SHORT_TAG]}


# ── the QUERY (what get_flag_universe actually asks the database) ───────────────────────────────

async def _universe(e_rows, monkeypatch=None, enabled=True):
    pool, conn = make_mock_pool()
    organic, r3, nine_m = [], [], []
    seq = [organic, r3, nine_m] + ([e_rows] if enabled else [])
    conn.fetch = AsyncMock(side_effect=seq)
    from unittest.mock import patch
    with patch.object(db_mod, "get_pool", new=AsyncMock(return_value=pool)):
        out = await db_mod.get_flag_universe("2026-09-03")
    return out, conn


@pytest.mark.asyncio
async def test_the_carry_is_one_query_and_it_asks_for_all_four_active_stages():
    out, conn = await _universe([])
    assert out == {}
    sqls = [c.args[0] for c in conn.fetch.await_args_list]
    assert len(sqls) == 4, "path (e) must stay ONE query (the fixed-order mocks in the neighbouring tests)"
    sql = sqls[3]
    for stage in ("WATCH", "TIGHTENING", "COILED", "TRIGGERED"):
        assert f"'{stage}'" in sql, f"the carry query does not select stored {stage}"


@pytest.mark.asyncio
async def test_the_window_is_scan_sessions_not_calendar_days():
    _, conn = await _universe([])
    sql = conn.fetch.await_args_list[3].args[0]
    assert "INTERVAL '5 days'" not in sql, "the carry window must not be 5 CALENDAR days"
    # a scan SESSION = a scan date that was a market session (bars exist), ranked newest-first
    assert "mi_daily_closes" in sql and "ROW_NUMBER()" in sql


@pytest.mark.asyncio
async def test_a_carried_name_must_have_a_bar_on_the_scan_date():
    """Review fix (2026-10-11): the carry used to admit a name with NO bar on the scan date, and `_score` then
    rated it on frozen history (FBRX: last bar 08-26, carried on 12 scans 08-27 -> 09-14; the next market
    holiday would have re-scored ~26-30 carried names on the prior day's bars). The organic path already
    requires `INNER JOIN mi_daily_closes d ... d.trade_date = $1`; the carry now asks the same, per ticker,
    on the SCAN date ($1) - not on the session dates the lag ranking uses."""
    _, conn = await _universe([])
    sql = " ".join(conn.fetch.await_args_list[3].args[0].split())
    assert "EXISTS (SELECT 1 FROM mi_daily_closes dc WHERE dc.ticker = c.ticker AND dc.trade_date = $1::date)" in sql, (
        "the carry query does not require the carried ticker to have a bar on the scan date")
    # ...and the query still binds the scan date as $1 (the guard is on D, not on a stored session date)
    assert conn.fetch.await_args_list[3].args[1] == date(2026, 9, 3)


@pytest.mark.asyncio
async def test_the_long_memory_is_the_detectors_own_pivot_lookback():
    """25 is not a second number: it IS `flag_detector._PIVOT_LOOKBACK_DAYS`, the horizon after which the
    pivot anchor itself re-chooses. Pinned so the two cannot drift apart."""
    assert db_mod._FLAG_CARRY_PIVOT_SESSIONS == fd._PIVOT_LOOKBACK_DAYS == 25
    assert db_mod._FLAG_CARRY_SCAN_SESSIONS == 5
    _, conn = await _universe([])
    args = conn.fetch.await_args_list[3].args[1:]
    assert db_mod._FLAG_CARRY_PIVOT_SESSIONS in args


@pytest.mark.asyncio
async def test_carried_names_get_their_tag_alongside_any_organic_tag():
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[
        [{"ticker": "ORG", "is_rs_top200": True, "is_rs_1m_80": False, "is_momentum_25pct": False}],
        [], [],
        [{"ticker": "ORG", "stage": "TIGHTENING", "lag": 1},
         {"ticker": "WATCHY", "stage": "WATCH", "lag": 3},
         {"ticker": "WDAY", "stage": "TRIGGERED", "lag": 1},
         {"ticker": "OLDBASE", "stage": "COILED", "lag": 11}],
    ])
    from unittest.mock import patch
    with patch.object(db_mod, "get_pool", new=AsyncMock(return_value=pool)):
        out = await db_mod.get_flag_universe("2026-09-03")
    assert out["ORG"] == ["rs_top200", SHORT_TAG]
    assert out["WATCHY"] == [SHORT_TAG]
    assert out["WDAY"] == [SHORT_TAG]
    assert out["OLDBASE"] == [LONG_TAG]


@pytest.mark.asyncio
async def test_the_kill_switch_still_turns_the_whole_carry_off(monkeypatch):
    monkeypatch.setenv("FLAG_STAGE_CARRYFORWARD_ENABLED", "false")
    out, conn = await _universe([], enabled=False)
    assert out == {}
    assert len(conn.fetch.await_args_list) == 3      # (a+b), (c), (d) only
