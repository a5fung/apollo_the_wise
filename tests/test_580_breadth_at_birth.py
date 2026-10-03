"""#580 (2026-10-03) — a theme is BORN with breadth, on every birth path, from one arithmetic.

Newborn themes carried NULL `pct_above_20sma` until their first nightly rescore (7 of 122
non-Retired rows on 2026-09-29; 420 since 08-01, 410 of them births) — exactly the newest,
hottest themes. NULL also means the breadth-decay rule has no prior reading the next night.

The first attempt (0c9660f2, reverted b51ea5b9) was failed by review on two points this file pins:
  1. an intraday /promotetheme read breadth on `today` — UNCHECKED: there is no complete score run
     for today before the nightly, at most a stray on-demand row or two, so the number could be a
     one-stock reading. Now the promote paths read breadth on the rows of their OWN RS query, whose
     date is the completeness-checked `latest_complete_score_date_sql()` — the date rs_avg uses.
  2. it acquired a SECOND pool connection while holding one. Now no extra acquire, no extra query.

Birth paths: `_score_new_theme` (discovery + fat-theme split; the SAME call the nightly rescore
makes, the engine's own date), `promote_shadow_themes` (nightly), `promote_candidate_by_name`
(operator /promotetheme), `db.seed_theme` (/teach). Retired rows stay NULL by design (no members).
No DB, no network.
"""
from __future__ import annotations

import datetime as _dt
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import db as dbmod
from agents.market_intelligence import theme_engine as te
from tests.conftest import make_mock_pool

_TODAY = _dt.date(2026, 9, 30)
_STOCKS = {"AAA": {"rs_composite": 90.0}, "BBB": {"rs_composite": 80.0},
           "CCC": {"rs_composite": 70.0}}


def _row(tk, rs, close, sma):
    return {"ticker": tk, "rs_composite": rs, "close": close, "sma_20": sma}


# ─── the ONE arithmetic ─────────────────────────────────────────────────────────

def test_580_breadth_arithmetic_matches_the_old_sql_aggregate():
    """`COUNT(*) FILTER (WHERE close > sma_20)` / `COUNT(*) FILTER (both NOT NULL)`, rounded 3."""
    f = dbmod.breadth_above_sma20
    assert f([]) is None                                            # nothing measured
    assert f([{"close": None, "sma_20": 10.0}, {"close": 5.0, "sma_20": None}]) is None
    assert f([{"close": 9.0, "sma_20": 10.0}, {"close": 8.0, "sma_20": 10.0}]) == 0.0   # 0% ≠ None
    assert f([{"close": 10.0, "sma_20": 10.0}]) == 0.0              # equal is NOT above
    assert f([{"close": 11.0, "sma_20": 10.0}, {"close": 9.0, "sma_20": 10.0},
              {"close": 12.0, "sma_20": 10.0}]) == 0.667
    # a row missing one side is excluded from BOTH counts (not counted as below)
    assert f([{"close": 11.0, "sma_20": 10.0}, {"close": None, "sma_20": 10.0}]) == 1.0


@pytest.mark.asyncio
async def test_580_nightly_function_uses_the_shared_arithmetic(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[_row("AAA", 90, 11.0, 10.0), _row("BBB", 80, 9.0, 10.0)])
    monkeypatch.setattr(dbmod, "get_pool", AsyncMock(return_value=pool))
    assert await dbmod.get_ticker_breadth_above_sma20(["AAA", "BBB"], _TODAY) == 0.5
    sql, tickers, d = conn.fetch.await_args.args
    assert tickers == ["AAA", "BBB"] and d == _TODAY            # the run's own date, as before
    assert await dbmod.get_ticker_breadth_above_sma20([], _TODAY) is None


# ─── engine births (discovery / split) ─────────────────────────────────────────

@pytest.fixture
def _no_news(monkeypatch):
    monkeypatch.setattr(te, "_news_check", AsyncMock(return_value=(20, "fresh description", False)))


@pytest.mark.asyncio
async def test_580_newborn_birth_row_carries_breadth(monkeypatch, _no_news):
    """THE named test: a newborn's row is non-NULL — from the SAME call the rescore makes
    (`get_ticker_breadth_above_sma20(tickers, today)`), and `_save_themes` persists it."""
    breadth = AsyncMock(return_value=0.0)    # all three below their 20-day avg: 0%, not NULL
    monkeypatch.setattr(te, "get_ticker_breadth_above_sma20", breadth)
    born = await te._score_new_theme(
        {"name": "Fresh Cohort", "tickers": ["AAA", "BBB", "CCC"], "thesis": "t"}, _STOCKS, _TODAY)
    assert born["pct_above_20sma"] == 0.0
    breadth.assert_awaited_once_with(["AAA", "BBB", "CCC"], _TODAY)
    assert born["stage"] == "Nascent" and born["description"] == "fresh description"

    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    for helper in ("_emit_cross_run_dup_probe", "_canonicalize_theme_names", "log_audit_event"):
        monkeypatch.setattr(te, helper, AsyncMock(return_value=0))
    await te._save_themes([born])
    inserts = [c for c in conn.execute.call_args_list if "INSERT INTO mi_themes" in str(c.args[0])]
    assert inserts, "the newborn was never written"
    assert inserts[0].args[-1] == 0.0          # the birth row's pct_above_20sma bind


@pytest.mark.asyncio
async def test_580_birth_breadth_failure_never_aborts_the_birth(monkeypatch, _no_news):
    """Discovery scores every survivor inside one asyncio.gather — a raise would lose the
    night's births. A failed lookup stores NULL (= today's behaviour: 'unknown')."""
    monkeypatch.setattr(te, "get_ticker_breadth_above_sma20",
                        AsyncMock(side_effect=RuntimeError("pool closed")))
    born = await te._score_new_theme(
        {"name": "Fresh Cohort", "tickers": ["AAA", "BBB"], "thesis": "t"}, _STOCKS, _TODAY)
    assert born["pct_above_20sma"] is None and born["score"] > 0


# ─── promote paths: the checked date, the held connection ─────────────────────

def _wire_operator_promote(monkeypatch, rows, members):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=rows)
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(te, "get_theme_birth_gate_mode", AsyncMock(return_value="off"))
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[
        {"name": "Offshore Drilling Rig Contractors", "tickers": members, "thesis": "t",
         "source": "coverage_probe"}]))
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(te, "_canonicalize_theme_names", AsyncMock(return_value=0))
    monkeypatch.setattr(te, "log_audit_event", AsyncMock())
    monkeypatch.setattr(te, "_map_ecosystems_nonfatal", AsyncMock())

    async def _today_bound_read_is_forbidden(*a, **k):
        raise AssertionError("the promote path read breadth on an unchecked `today`")
    monkeypatch.setattr(te, "get_ticker_breadth_above_sma20", _today_bound_read_is_forbidden)
    return pool, conn


@pytest.mark.asyncio
async def test_580_promotetheme_reads_breadth_on_the_checked_score_date(monkeypatch):
    """THE named test for review finding 1. An intraday /promotetheme (`today` has no complete
    score run) must take breadth from the completeness-checked run its rs_avg comes from — never
    a `today`-bound read (patched to raise). The INSERT carries the arithmetic over exactly the
    rows that query returned, and that query binds no date at all: its date is the #554
    completeness subquery."""
    members = ["RIG", "VAL", "NE", "DO"]
    rows = [_row("RIG", 70, 4.0, 5.0), _row("VAL", 65, 40.0, 45.0),
            _row("NE", 60, 25.0, 30.0), _row("DO", 72, 12.0, 11.0)]     # 1 of 4 above → 0.25
    pool, conn = _wire_operator_promote(monkeypatch, rows, members)

    res = await te.promote_candidate_by_name("offshore drilling", _TODAY)

    assert res["status"] == "promoted"
    insert = conn.execute.call_args
    assert "pct_above_20sma" in insert.args[0]
    assert insert.args[-1] == 0.25
    (rs_call,) = conn.fetch.await_args_list            # ONE score read on this path
    sql = rs_call.args[0]
    assert dbmod.latest_complete_score_date_sql() in sql
    assert "close" in sql and "sma_20" in sql          # breadth rides on the RS rows
    assert rs_call.args[1:] == (members,)              # no `today` bound into the score read


@pytest.mark.asyncio
async def test_580_promotetheme_holds_one_connection(monkeypatch):
    """Review finding 2: no second pool connection is acquired while the promote holds one."""
    pool, _conn = _wire_operator_promote(
        monkeypatch, [_row("RIG", 70, 6.0, 5.0)], ["RIG", "VAL", "NE", "DO"])
    await te.promote_candidate_by_name("offshore drilling", _TODAY)
    assert pool.acquire.call_count == 1


@pytest.mark.asyncio
async def test_580_promotetheme_no_scored_member_stores_null(monkeypatch):
    """No member carries close + sma_20 on the checked date → NULL (unknown), never 0.0."""
    _pool, conn = _wire_operator_promote(
        monkeypatch, [{"ticker": "RIG", "rs_composite": 70.0, "close": None, "sma_20": None}],
        ["RIG", "VAL", "NE", "DO"])
    await te.promote_candidate_by_name("offshore drilling", _TODAY)
    assert conn.execute.call_args.args[-1] is None


@pytest.mark.asyncio
async def test_580_nightly_promote_breadth_per_cohort_from_the_batched_rows(monkeypatch):
    """The nightly promote reads ONE batched score query for all cohorts; each cohort's breadth
    counts only its own members' rows."""
    pool, conn = make_mock_pool()
    cohort_a = ["CIFR", "CORZ", "HUT", "IREN", "WULF"]
    cohort_b = ["RIG", "VAL", "NE", "DO", "BORR"]
    batched = ([_row(tk, 80, 9.0, 10.0) for tk in cohort_a]                 # A: 0 of 5 above
               + [_row(tk, 70, 11.0, 10.0) for tk in cohort_b[:3]]          # B: 3 of 4 above
               + [_row("DO", 70, 9.0, 10.0)])                               # BORR unscored
    conn.fetch = AsyncMock(side_effect=[[], [], batched])
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(te, "get_theme_birth_gate_mode", AsyncMock(return_value="off"))
    monkeypatch.setattr(dbmod, "resolve_auto_promote_sources", AsyncMock(return_value={"shadow_v2"}))
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[
        {"name": "Bitcoin Miners Pivoting to AI/HPC", "tickers": cohort_a, "thesis": "t",
         "source": "shadow_v2"},
        {"name": "Offshore Drilling Rig Contractors", "tickers": cohort_b, "thesis": "t",
         "source": "shadow_v2"}]))
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(te, "_canonicalize_theme_names", AsyncMock(return_value=0))
    monkeypatch.setattr(te, "log_audit_event", AsyncMock())
    monkeypatch.setattr(te, "_map_ecosystems_nonfatal", AsyncMock())
    from agents.market_intelligence import briefing as _brief
    monkeypatch.setattr(_brief, "send_telegram_message", AsyncMock())

    async def _forbidden(*a, **k):
        raise AssertionError("nightly promote read breadth on an unchecked `today`")
    monkeypatch.setattr(te, "get_ticker_breadth_above_sma20", _forbidden)

    assert await te.promote_shadow_themes(_TODAY) == 2
    written = {c.args[2]: c.args[-1] for c in conn.execute.call_args_list
               if "INSERT INTO mi_themes" in str(c.args[0])}
    assert written == {"Bitcoin Miners Pivoting to AI/HPC": 0.0,
                       "Offshore Drilling Rig Contractors": 0.75}
    rs_sql = conn.fetch.await_args_list[2].args[0]
    assert dbmod.latest_complete_score_date_sql() in rs_sql and "sma_20" in rs_sql
    assert pool.acquire.call_count == 1


# ─── /teach seed ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_580_seeded_theme_born_with_breadth_on_the_checked_date(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=None)        # no same-day / same-name row
    conn.fetch = AsyncMock(return_value=[_row("AAA", 90, 11.0, 10.0), _row("BBB", 80, 9.0, 10.0)])
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(dbmod, "get_pool", AsyncMock(return_value=pool))
    await dbmod.seed_theme("Taught Theme", "thesis", ["aaa", "bbb"], _TODAY)
    sql, tickers = conn.fetch.await_args.args
    assert dbmod.latest_complete_score_date_sql() in sql and tickers == ["AAA", "BBB"]
    ins = conn.execute.call_args.args
    assert "pct_above_20sma" in ins[0] and ins[-1] == 0.5
    assert pool.acquire.call_count == 1
