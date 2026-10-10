"""#624 small-cap PAPER lane (operator "Ok to recs" 2026-10-10) — the build's pins.

His rulings (PLAN.md #624): names turned away ONLY by the $500M floor are graded by the SAME live
EP score, AFTER live grading, in the background; a lane HIGH goes to the lane's OWN alerts table
and a PAPER-ONLY order step; a NEW strategy row routed to PAPER at size 1.0 with MAGNA53's exits;
live MAGNA53's "already traded today" check made account-aware.

Every piece below is RED on the pre-build code (the lane, its table, its order step, the funnel
guard, the literal rulings and the live_tracker filter did not exist). Parts:
  1. the real run_ep_scan, end to end: the lane grades a cap-only name with the LIVE code (same
     score as an identical live name), the live outputs are byte-identical lane on/off/raising,
     and the lane name never reaches insert_ep_alert;
  2. the paper-only order step: reads only the lane table, binds every order to 'paper',
     refuses any other phase, pre-flights the paper account;
  3. the entry funnel's account binding (fails closed before any row or order);
  4. the order id a lane trade carries;
  5. live_tracker: a lane paper trade never makes live MAGNA53 skip a name; the live order step
     never sees a lane alert;
  6. the strategy row, the exit literal rulings, the M&A budget pool, the lane task, the replay.
"""
from __future__ import annotations

import inspect
import re
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from agents.market_intelligence import db
from agents.market_intelligence import ep_detector
from agents.market_intelligence import lowcap_paper_lane as plane
from agents.market_intelligence.broker import entry_pipeline as ep
from agents.market_intelligence.broker import live_tracker as lt
from agents.market_intelligence.broker import lowcap_paper_entry as lpe
from agents.market_intelligence.strategies.registry import Strategy
from tests.conftest import make_mock_pool

_ET = ZoneInfo("America/New_York")
_REPO = Path(__file__).resolve().parent.parent
LANE = "magna53_smallcap"


# ── 1. run_ep_scan end to end ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lane_grades_a_cap_only_name_with_the_live_code_and_live_is_byte_identical(monkeypatch):
    """BIG05 clears every live gate and is then turned away ONLY by the $500M floor. With the
    lane ON it is graded by the SAME `_grade_admitted` + `_judge_shadow` and lands — HIGH — in
    the lane's own table, scored IDENTICALLY to BIG00 (same snapshot, same grade) on the live
    path. The live scan's outputs do not move with the lane on, off or raising, and BIG05 never
    reaches insert_ep_alert (the table the live order step reads) in any mode.

    MUTATION TARGETS: drop the FILTER_MCAP_TOO_SMALL append (no lane row); route the lane alert
    through insert_ep_alert (BIG05 in `alerts`); give the lane a different scorer (score drift)."""
    from tests.test_624_lowcap_lane import _run_scan_once, ADMIT_TICKER
    from tests._byte_identity import assert_byte_identical
    from agents.market_intelligence import ep_grade_judge

    sinks = {m: {} for m in ("on", "off", "raising")}
    runs, judge_callers = {}, {}
    for m in ("on", "off", "raising"):
        runs[m] = await _run_scan_once(monkeypatch, lane_mode="off", admit=True,
                                       lowcap_admit="BIG05", paper_mode=m, paper_sink=sinks[m])
        # the harness installs a fresh judge stub per run — read this run's calls now
        judge_callers[m] = [c.kwargs.get("log_caller")
                            for c in ep_grade_judge.grade_holistic.await_args_list]

    for other in ("off", "raising"):
        assert_byte_identical(runs["on"][0], runs[other][0], f"results (on vs {other})")
        assert_byte_identical(runs["on"][1], runs[other][1], f"scan_log rows (on vs {other})")
        assert_byte_identical(runs["on"][2], runs[other][2], f"alert inserts (on vs {other})")

    results, scan_log, alerts, _ = runs["on"]
    by_ticker = {r["ticker"]: r for r in scan_log}
    # live: BIG05 died at the quality filter on the cap, exactly as before the lane existed
    assert by_ticker["BIG05"]["reject_stage"] == "quality_filter"
    assert "mcap_too_small" in by_ticker["BIG05"]["filter_reason"]
    for m in runs:
        assert all(a["ticker"] != "BIG05" for a in runs[m][2]), "a lane name reached insert_ep_alert"
        assert all(r["ticker"] != "BIG05" for r in runs[m][0])

    # the lane, ON: one row, HIGH, its own strategy, the live check_filters cap read
    rows = [r for r in sinks["on"]["rows"] if r["ticker"] == "BIG05"]
    assert rows and rows[0]["score_tier"] == "HIGH", sinks["on"]["rows"]
    lane_row = rows[0]
    assert lane_row["strategy_id"] == LANE and lane_row["market_cap"] == 134_000_000.0
    assert lane_row["catalyst_quality"] == "game_changer" and lane_row["detected_at"] is not None
    # THE SAME SCORE: BIG00 (live) and BIG05 (lane) share snapshot, ADV and grade
    live_big00 = next(r for r in results if r["ticker"] == ADMIT_TICKER)
    assert lane_row["ep_score"] == pytest.approx(float(live_big00["ep_score"]))
    # the lane ran the SAME judge call, billed to its own bucket
    assert sorted(judge_callers["on"]) == ["ep_grade_judge", "lowcap_paper_lane_judge"]
    assert judge_callers["off"] == judge_callers["raising"] == ["ep_grade_judge"]
    # off / raising: the lane wrote nothing
    assert sinks["off"]["rows"] == [] and sinks["raising"].get("rows", []) == []


@pytest.mark.asyncio
async def test_an_authoritative_judge_moves_the_lane_tier_through_the_lanes_own_writer(monkeypatch):
    """Prod runs the holistic judge AUTHORITATIVE. The lane's names must get the SAME judge
    decision, written to the LANE's table — never to mi_ep_alerts. MUTATION TARGET: a kwarg
    mismatch between `_judge_shadow`'s writer call and `update_lowcap_paper_lane_judge_result`
    (the except would quietly leave the lane on floor tiers while live ran judge tiers)."""
    from tests.test_624_lowcap_lane import _run_scan_once, ADMIT_TICKER
    verdict = {"tier": "MODERATE", "direction_vs_floor": "demote", "rationale": "thin",
               "materiality_tier": None, "grade": "strong", "grade_reason": "g",
               "tier_reason": "t", "fire_axes": ["catalyst"], "confidence": 0.7}
    live_writes = []

    async def _live_writer(ticker, alert_date, **kw):
        live_writes.append((ticker, kw))
    monkeypatch.setattr(db, "update_ep_alert_judge_result", _live_writer)
    sink: dict = {}
    results, _, _, _ = await _run_scan_once(monkeypatch, lane_mode="off", admit=True,
                                            lowcap_admit="BIG05", paper_mode="on",
                                            paper_sink=sink, judge_verdict=verdict)
    # live: BIG00 demoted by the judge, written to the live table only
    assert [t for t, _ in live_writes] == [ADMIT_TICKER]
    assert next(r for r in results if r["ticker"] == ADMIT_TICKER)["score_tier"] == "MODERATE"
    # lane: the SAME decision, through the lane's writer
    assert [t for t, _ in sink["judge"]] == ["BIG05"]
    kw = sink["judge"][0][1]
    assert kw["score_tier"] == "MODERATE" and kw["grade_engine_authority"] == "judge"
    assert kw["judge_tier"] == "MODERATE" and kw["fire_axes"] == ["catalyst"]


def test_dispatch_is_last_wrapped_and_lazily_imported():
    """The lane is scheduled AFTER every live decision of the tick (judge + tape annotation) and
    can never raise into the scan; ep_detector is execution-loaded, the lane module stays lazy."""
    # source-pin-ok: WHERE the dispatch textually sits inside run_ep_scan (after the post-scan
    # judge block, before `return results`) is the "after live grading has finished" ruling —
    # the end-to-end test above proves the outcomes, this pins the placement.
    src = inspect.getsource(ep_detector.run_ep_scan)
    dispatch = src.index("schedule_paper_lane_tick(")
    assert dispatch > src.index("annotate_ep_alerts_tape_quality(results)")
    assert dispatch > src.index("_alerted = high + moderate")
    assert src.rindex("return results") > dispatch
    head = (_REPO / "agents/market_intelligence/ep_detector.py").read_text().split("async def run_ep_scan")[0]
    assert "lowcap_paper_lane" not in head


# ── 2. the paper-only order step ────────────────────────────────────────────────────────


def _strategy(phase="paper", enabled=True, live_real_enabled=False) -> Strategy:
    return Strategy(strategy_id=LANE, name="lane", family="orb_long", phase=phase, enabled=enabled,
                    signal_type=LANE, outcomes_table="mi_live_trades", promotion_model="unpaired_r",
                    live_real_enabled=live_real_enabled)


class _At(datetime):
    """datetime with a pinned now() — set `_At.pinned` per test."""
    pinned = datetime(2026, 10, 12, 9, 33, tzinfo=_ET)

    @classmethod
    def now(cls, tz=None):
        return cls.pinned.astimezone(tz) if tz else cls.pinned.replace(tzinfo=None)


_HIGH = {"ticker": "SMLL", "alert_date": date(2026, 10, 12), "gap_pct": 22.0, "rel_volume": 3.0,
         "ep_score": 90.0, "score_tier": "HIGH", "catalyst": "x", "catalyst_quality": "game_changer",
         "vol_percentile": 95.0, "detected_at": None}


def _wire_order_step(monkeypatch, *, phase="paper", account=None, at=(9, 33), highs=None):
    from agents.market_intelligence.strategies import registry
    _At.pinned = datetime(2026, 10, 12, *at, tzinfo=_ET)
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=False)
    monkeypatch.setattr(lpe, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(lpe, "datetime", _At)
    monkeypatch.setattr(lpe, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setattr(lpe, "get_runtime_toggle", AsyncMock(return_value=True))
    monkeypatch.setattr(lpe, "get_lowcap_paper_lane_highs",
                        AsyncMock(return_value=[dict(_HIGH)] if highs is None else highs))
    monkeypatch.setattr(registry, "get_strategy", AsyncMock(return_value=_strategy(phase=phase)))
    monkeypatch.setattr(lpe, "_preflight_ok_date", None)
    get_account = AsyncMock(return_value=account if account is not None
                            else {"equity": 100_000.0, "trading_blocked": False, "account_blocked": False})
    monkeypatch.setattr(lpe.alpaca, "get_account", get_account)
    cf = AsyncMock(return_value=(True, None))
    monkeypatch.setattr(lpe, "check_filters", cf)
    monkeypatch.setattr(lpe, "compute_atr_14", AsyncMock(return_value=(0.5, 5.0)))
    submit = AsyncMock(return_value={"ticker": "SMLL", "action": ep.ACTION_AUTO_ENTERED, "trade_id": 1})
    monkeypatch.setattr(lpe, "submit_trade_entry", submit)
    audits: list = []

    async def _audit(ev, summary, detail=""):
        audits.append((ev, summary))
    monkeypatch.setattr(lpe, "log_audit_event", _audit)
    pages: list = []

    async def _tg(msg, *a, **k):
        pages.append(msg)
        return True
    from agents.market_intelligence import briefing
    monkeypatch.setattr(briefing, "send_telegram_message", _tg)
    return SimpleNamespace(conn=conn, submit=submit, check_filters=cf, get_account=get_account,
                           audits=audits, pages=pages)


@pytest.mark.asyncio
async def test_order_step_submits_lane_highs_bound_to_paper_with_magna53_order(monkeypatch):
    w = _wire_order_step(monkeypatch)
    out = await lpe.process_lowcap_paper_alerts(today=date(2026, 10, 12))
    assert [r["action"] for r in out] == [ep.ACTION_AUTO_ENTERED]
    kw = w.submit.await_args.kwargs
    assert kw["signal_type"] == LANE
    assert kw["require_account_mode"] == "paper"          # wall 3: the funnel's own binding
    assert kw["page_cap_plus_one"] is False               # no live CAP+1 manual-trade prompt
    assert kw["rt_gap_floor_pct"] == ep_detector.MIN_GAP_PCT   # MAGNA53's own gap re-check
    assert kw["fade_midpoint_ratio"] is None and kw["aggregate_skips"] is True
    assert kw["alert_context"]["ticker"] == "SMLL"
    # order-time ADV$/ATR re-check WITHOUT the cap (the one filter the lane inverts)
    assert w.check_filters.await_args.kwargs.get("skip_mcap") is True
    # no Telegram on a placed paper order
    assert w.pages == []


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["live", "shadow"])
async def test_order_step_refuses_any_phase_but_paper_and_pages(monkeypatch, phase):
    """MUTATION TARGET: drop the phase check in _strategy_paper_or_refuse — a lane row moved to
    'live' would otherwise reach the funnel (wall 3 would still stop it; this is wall 2)."""
    w = _wire_order_step(monkeypatch, phase=phase)
    out = await lpe.process_lowcap_paper_alerts(today=date(2026, 10, 12))
    assert out == [] and not w.submit.await_count and not w.get_account.await_count
    assert any(ev == "lowcap_paper_lane_refused" for ev, _ in w.audits)
    assert len(w.pages) == 1 and w.pages[0].startswith("📄 PAPER")


@pytest.mark.asyncio
async def test_preflight_failure_submits_nothing_pages_and_retries_next_call(monkeypatch):
    w = _wire_order_step(monkeypatch)
    w.get_account.side_effect = RuntimeError("paper account 401")
    out = await lpe.process_lowcap_paper_alerts(today=date(2026, 10, 12))
    assert out == [] and not w.submit.await_count
    assert any(ev == "lowcap_paper_lane_preflight_failed" for ev, _ in w.audits)
    assert len(w.pages) == 1 and w.pages[0].startswith("📄 PAPER")
    # a failure is never cached as a pass: the next call asks again and, answered, submits
    w.get_account.side_effect = None
    w.get_account.return_value = {"equity": 100_000.0, "trading_blocked": False, "account_blocked": False}
    out = await lpe.process_lowcap_paper_alerts(today=date(2026, 10, 12))
    assert w.submit.await_count == 1 and w.get_account.await_count == 2


@pytest.mark.asyncio
async def test_blocked_paper_account_fails_the_preflight(monkeypatch):
    w = _wire_order_step(monkeypatch, account={"equity": 100_000.0, "trading_blocked": True,
                                               "account_blocked": False})
    assert await lpe.process_lowcap_paper_alerts(today=date(2026, 10, 12)) == []
    assert not w.submit.await_count and w.pages


@pytest.mark.asyncio
async def test_preflight_runs_once_per_day(monkeypatch):
    w = _wire_order_step(monkeypatch)
    await lpe.process_lowcap_paper_alerts(today=date(2026, 10, 12))
    await lpe.process_lowcap_paper_alerts(today=date(2026, 10, 12))
    assert w.get_account.await_count == 1 and w.submit.await_count == 2


@pytest.mark.asyncio
async def test_after_0945_a_lane_high_gets_a_durable_out_of_window_skip_and_no_order(monkeypatch):
    w = _wire_order_step(monkeypatch, at=(9, 50))
    ins = AsyncMock()
    monkeypatch.setattr(lt, "_insert_skipped_trade", ins)
    out = await lpe.process_lowcap_paper_alerts(today=date(2026, 10, 12))
    assert not w.submit.await_count and out and out[0]["reason"].startswith("window:out_of_orb")
    a, k = ins.await_args.args, ins.await_args.kwargs
    assert a[0] == "SMLL" and k["signal_type"] == LANE and k["account_mode"] == "paper"


@pytest.mark.asyncio
async def test_toggle_off_stops_the_order_step(monkeypatch):
    w = _wire_order_step(monkeypatch)
    monkeypatch.setattr(lpe, "get_runtime_toggle", AsyncMock(return_value=False))
    assert await lpe.process_lowcap_paper_alerts(today=date(2026, 10, 12)) == []
    assert not w.submit.await_count


def test_order_step_never_reads_the_live_alert_table():
    # source-pin-ok: ABSENCE of the live alert table from the paper order step's code is the
    # wall-1 claim itself (what it never reads); the behavioural tests above drive it only
    # through stubs, which cannot show a read that is not there.
    code = re.sub(r'"""(.*?)"""', "", (_REPO / "agents/market_intelligence/broker/lowcap_paper_entry.py").read_text(), flags=re.S)
    code = "\n".join(l.split("#")[0] for l in code.splitlines())
    assert "mi_ep_alerts" not in code and "_HIGH_ALERT_SELECT_SQL" not in code
    assert "process_new_alerts_live" not in code
    assert "FROM mi_lowcap_paper_lane_alerts" in db._LOWCAP_PAPER_LANE_HIGHS_SQL
    assert "mi_ep_alerts" not in db.LOWCAP_PAPER_LANE_UPSERT_SQL
    assert "FROM mi_ep_alerts" in lt._HIGH_ALERT_SELECT_SQL      # the live step reads only its own


# ── 3. the entry funnel's account binding ─────────────────────────────────────────────


async def _funnel(**extra):
    from tests.test_461_cap_toctou_race import _TODAY, _spec_builder
    return await ep.submit_trade_entry(
        alert_context={"ticker": "SMLL", "ep_score": 90, "catalyst_quality": "game_changer",
                       "gap_pct": 22.0},
        spec_builder=_spec_builder, regime_record=None, strategy_label="ORB small-cap lane (paper)",
        signal_type=LANE, today=_TODAY, atr_14=1.0, fade_midpoint_ratio=None, **extra)


@pytest.mark.asyncio
async def test_funnel_refuses_a_lane_row_that_resolves_to_live_before_the_trade_row_or_order(monkeypatch):
    """Wall 3. A lane strategy whose phase became 'live' (live_real_enabled True — the worst
    case) must not insert a trade row or place an order, and 1c itself writes no skip row.
    (Steps 1 / 1b / 1a run BEFORE 1c and can write a skip row of their own — this fixture has no
    duplicate and no open position, so they pass; 10-10 review.) MUTATION TARGET: remove 1c."""
    from tests.test_461_cap_toctou_race import FakeDB, _wire
    import agents.market_intelligence.broker.order_manager as om
    fdb = FakeDB()
    _wire(monkeypatch, fdb, phase="live", live_real_enabled=True)
    res = await _funnel(require_account_mode="paper")
    assert res["action"] == ep.ACTION_BLOCKED and res["reason"].startswith("block:account_mode_mismatch")
    assert fdb.rows == []
    assert not om.submit_entry.await_count
    assert not lt._insert_skipped_trade.await_count


@pytest.mark.asyncio
async def test_funnel_admits_a_paper_lane_row_into_the_paper_book(monkeypatch):
    from tests.test_461_cap_toctou_race import FakeDB, _wire
    fdb = FakeDB()
    _wire(monkeypatch, fdb, phase="paper")
    res = await _funnel(require_account_mode="paper")
    assert res["action"] == ep.ACTION_AUTO_ENTERED, res
    row = fdb.rows[-1]
    assert row["account_mode"] == "paper" and row["signal_type"] == LANE


@pytest.mark.asyncio
async def test_existing_callers_without_the_binding_are_unchanged(monkeypatch):
    from tests.test_461_cap_toctou_race import FakeDB, _wire
    fdb = FakeDB()
    _wire(monkeypatch, fdb, phase="live", live_real_enabled=True)
    res = await _funnel()                      # no require_account_mode = today's behaviour
    assert res["action"] == ep.ACTION_AUTO_ENTERED
    assert fdb.rows[-1]["account_mode"] == "live"


@pytest.mark.asyncio
@pytest.mark.parametrize("flag,expect_page", [(True, True), (False, False)])
async def test_cap_plus_one_page_is_off_for_the_lane(monkeypatch, flag, expect_page):
    """The #197 CAP+1 page asks the operator to consider a MANUAL real-money trade — never for a
    paper small-cap. Default (True) keeps it for every existing caller."""
    from tests.test_461_cap_toctou_race import FakeDB, _wire
    fdb = FakeDB()
    fdb.seed(5, mode="paper")                  # the paper account's global cap is full
    sent, _ = _wire(monkeypatch, fdb, phase="paper")
    res = await _funnel(page_cap_plus_one=flag)
    assert res["action"] == ep.ACTION_BLOCKED
    assert any("CAP+1" in m for m in sent) is expect_page


# ── 4. the order id a lane trade carries ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_lane_trade_row_submits_with_a_paper_bound_client_order_id(monkeypatch):
    """Invariant 1: `order_manager.submit_entry` builds the id from the ROW's account_mode +
    signal_type — for a lane row that is make_client_order_id('paper', 'magna53_smallcap', t),
    and the order goes to the paper client."""
    from tests.test_500_price_aware_entry import _TRADE, _wire_submit_entry
    from agents.market_intelligence.broker import alpaca_client as alp
    import agents.market_intelligence.broker.order_manager as om
    trade = {**_TRADE, "signal_type": LANE, "account_mode": "paper"}
    fake, _conn, _ = _wire_submit_entry(monkeypatch, {"price": 10.40}, trade=trade)
    fake.make_client_order_id = MagicMock(side_effect=alp.make_client_order_id)
    assert await om.submit_entry(7) is not None
    fake.make_client_order_id.assert_called_with("paper", LANE, "TSTX")
    kw = fake.place_bracket_order.await_args.kwargs
    assert kw["account_mode"] == "paper"
    assert kw["client_order_id"].startswith(f"apollo_paper_{LANE}_TSTX_")


# ── 5. live_tracker: account-aware "already traded today"; never sees a lane alert ──────


def _wire_live_step(monkeypatch, *, magna_mode, paper_row_exists=True, alerts=None):
    pool, conn = make_mock_pool()

    async def _fetch(sql, *args):
        if "FROM mi_ep_alerts" in sql:
            return list(alerts if alerts is not None else
                        [{"ticker": "SMLL", "alert_date": date(2026, 10, 12), "gap_pct": 22.0,
                          "rel_volume": 3.0, "ep_score": 90.0, "score_tier": "HIGH",
                          "catalyst": "x", "catalyst_quality": "strong", "vol_percentile": 95.0}])
        return []

    async def _fetchval(sql, *args):
        if "SELECT EXISTS(SELECT 1 FROM mi_live_trades" in sql:
            # the ONLY trade row today is the lane's PAPER row
            if "account_mode = $3" in sql:
                return paper_row_exists and args[2] == "paper"
            return paper_row_exists
        return None

    conn.fetch = AsyncMock(side_effect=_fetch)
    conn.fetchval = AsyncMock(side_effect=_fetchval)
    conn.fetchrow = AsyncMock(return_value=None)
    conn.executemany = AsyncMock(return_value=None)
    monkeypatch.setattr(lt, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(lt, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setattr(lt, "get_runtime_toggle", AsyncMock(return_value=False))
    monkeypatch.setattr(lt, "resolve_strategy_mode_nonfatal", AsyncMock(return_value=magna_mode))
    cf = AsyncMock(return_value=(False, "filter:adv_too_low: test"))
    monkeypatch.setattr(lt, "check_filters", cf)
    monkeypatch.setattr(lt, "_insert_skipped_trade", AsyncMock())
    monkeypatch.setattr(lt, "send_telegram_message", AsyncMock(return_value=True))
    monkeypatch.setattr(db, "log_audit_event", AsyncMock())
    submit = AsyncMock()
    monkeypatch.setattr(lt, "submit_trade_entry", submit)
    return cf, submit


@pytest.mark.asyncio
async def test_a_lane_paper_trade_never_makes_live_magna53_skip_the_name(monkeypatch):
    """RED on the pre-build code: the unfiltered EXISTS saw the lane's PAPER row and the live
    step returned before check_filters — a live MAGNA53 HIGH silently dropped."""
    cf, _ = _wire_live_step(monkeypatch, magna_mode="live")
    await lt.process_new_alerts_live(today=date(2026, 10, 12))
    assert cf.await_count == 1 and cf.await_args.args[0] == "SMLL"


@pytest.mark.asyncio
async def test_mode_resolve_failure_keeps_the_unfiltered_check(monkeypatch):
    """Fail direction: None (the resolve failed) runs today's UNFILTERED check — never
    `account_mode = NULL`, which matches nothing and would re-process a name already held."""
    cf, _ = _wire_live_step(monkeypatch, magna_mode=None)
    await lt.process_new_alerts_live(today=date(2026, 10, 12))
    assert cf.await_count == 0


@pytest.mark.asyncio
async def test_a_same_account_row_still_dedupes(monkeypatch):
    cf, _ = _wire_live_step(monkeypatch, magna_mode="paper")    # MAGNA53 on the paper book
    await lt.process_new_alerts_live(today=date(2026, 10, 12))
    assert cf.await_count == 0


@pytest.mark.asyncio
async def test_the_live_order_step_sees_nothing_when_only_the_lane_has_a_high(monkeypatch):
    """A lane HIGH lives only in mi_lowcap_paper_lane_alerts; the live step reads mi_ep_alerts —
    empty — so it submits nothing."""
    cf, submit = _wire_live_step(monkeypatch, magna_mode="live", alerts=[])
    assert await lt.process_new_alerts_live(today=date(2026, 10, 12)) == []
    assert not submit.await_count and not cf.await_count


# ── 6. the row, the literal rulings, the M&A pool, the lane task, the replay ──────────


def test_the_strategy_row_is_paper_size_one_with_magna53_exits_and_its_own_cap():
    from tests.test_strategy_deprecation_424 import _run_seed
    from agents.market_intelligence.constants import resolve_account_mode_for_strategy
    conn = _run_seed()
    lane_calls = [(q, a) for q, a in conn.execute_calls if "INSERT INTO mi_strategies" in q]
    assert len(lane_calls) == 1
    q, args = lane_calls[0]
    assert args[0] == LANE and args[2] == db.LOWCAP_PAPER_LANE_POSITION_CAP == 5
    assert "'paper'" in q and "1.0, $3, 8.0, 3.0" in q and "ON CONFLICT (strategy_id) DO NOTHING" in q
    assert "live_real_enabled" not in q            # column default FALSE — never set here
    assert resolve_account_mode_for_strategy(SimpleNamespace(phase="paper")) == "paper"


def test_exit_literal_rulings_put_the_lane_on_magna53s_frame_and_era():
    from agents.market_intelligence.broker.order_manager import profit_target_r_per_share
    from agents.market_intelligence.rule_eras import exit_era_label, exit_rules_as_of
    from agents.market_intelligence.strategies.adapters import _ADAPTERS
    # ORB frame: R = entry − ORB low (1.0), not entry − 2R stop (2.0)
    assert profit_target_r_per_share(LANE, 10.5, 8.5, 9.5) == pytest.approx(1.0)
    d = date(2026, 10, 12)
    assert exit_era_label(d, LANE) == "era_d" == exit_era_label(d, "magna53")
    assert exit_rules_as_of(d, LANE) == exit_rules_as_of(d, "magna53")
    assert LANE in _ADAPTERS
    from agents.market_intelligence.sell_discipline import _SIGNAL_DISPLAY
    assert "_" not in _SIGNAL_DISPLAY[LANE]       # never a raw underscore in a Markdown label


@pytest.mark.asyncio
@pytest.mark.parametrize("pool_kw,expected", [({}, "ep"), ({"ma_budget_pool": "shared"}, "shared")])
async def test_the_lane_spends_the_shared_ma_budget_never_the_ep_reserve(monkeypatch, pool_kw, expected):
    seen = {}

    async def _ma(ticker, **kw):
        seen.update(kw)
        return False, {}
    monkeypatch.setattr(ep_detector, "is_likely_ma", _ma)
    await ep_detector._post_grade_filters(
        "SMLL", "strong", "analysis", "news", 22.0, 5_000_000, 3.0, date(2026, 10, 12),
        lattice_acting=False, **pool_kw)
    assert seen["budget_pool"] == expected


def _sink(today=date(2026, 10, 12), now=datetime(2026, 10, 12, 9, 20, tzinfo=_ET)):
    rows = []

    def _scan_row(c, *, reason, ep_score, tier, catalyst_quality, stage=None):
        return {"ticker": c["ticker"], "filter_reason": reason, "ep_score": ep_score,
                "score_tier": tier, "catalyst_quality": catalyst_quality, "reject_stage": stage}
    return plane.LaneSink(today=today, now_et=now, regime_label="Bull", scan_row=_scan_row), rows


def _wire_lane(monkeypatch, *, tiered=None, toggle=True, highs=None):
    rows, audits, pages = [], [], []

    async def _row(fields):
        rows.append(dict(fields))
        return True

    async def _audit(ev, summary, detail=""):
        audits.append(ev)

    async def _tg(msg, *a, **k):
        pages.append(msg)
    monkeypatch.setattr(plane, "upsert_lowcap_paper_lane_row", _row)
    monkeypatch.setattr(plane, "get_lowcap_paper_lane_tiered", AsyncMock(return_value=tiered or {}))
    monkeypatch.setattr(plane, "get_runtime_toggle", AsyncMock(return_value=toggle))
    monkeypatch.setattr(plane, "should_run", AsyncMock(return_value=True))
    monkeypatch.setattr(plane, "get_lowcap_paper_lane_highs", AsyncMock(return_value=highs or []))
    monkeypatch.setattr(plane, "log_audit_event", _audit)
    from agents.market_intelligence import briefing
    monkeypatch.setattr(briefing, "send_telegram_message", _tg)
    monkeypatch.setattr(plane, "_lock", None)
    monkeypatch.setattr(plane, "_paged", set())
    return rows, audits, pages


def _cand(t="SMLL", gap=22.0):
    return ({"ticker": t, "gap_pct": gap, "prev_close": 8.0, "market_cap": 134e6}, t, 3.0)


async def _grade_high(c, ticker, rel_volume, *, lane, results, scan_log, **kw):
    """Stands in for ep_detector._grade_admitted — writes what the real one writes on a HIGH."""
    r = {**c, "ticker": ticker, "score_tier": "HIGH", "ep_score": 90.0,
         "catalyst_quality": "game_changer"}
    results.append(r)
    scan_log.append({"ticker": ticker, "score_tier": "HIGH", "ep_score": 90.0})
    await lane.insert_alert({"ticker": ticker, "alert_date": lane.today, "score_tier": "HIGH",
                             "ep_score": 90.0, "catalyst_quality": "game_changer",
                             "detected_at": lane.now_et, "baseline_floor_tier": "HIGH",
                             "grade_engine_authority": "floor"})


@pytest.mark.asyncio
async def test_a_lane_high_is_written_judged_and_sends_no_telegram(monkeypatch):
    rows, audits, pages = _wire_lane(monkeypatch)
    judged = []

    async def _judge(r, lane=None):
        judged.append((r["ticker"], lane is not None))
    out = await plane.run_paper_lane_tick(
        [_cand()], grade=_grade_high, judge=_judge, scan_row=lambda *a, **k: {},
        today=date(2026, 10, 12), now_et=datetime(2026, 10, 12, 9, 20, tzinfo=_ET),
        regime_label="Bull", judge_timeout_s=5)
    assert out["tiered"] == 1 and judged == [("SMLL", True)]
    assert rows and rows[0]["score_tier"] == "HIGH" and rows[0]["strategy_id"] == LANE
    assert "lowcap_paper_lane_alert" in audits
    assert pages == []                         # an alert that says no action is noise


@pytest.mark.asyncio
async def test_lane_cooldown_and_already_scored_today_are_the_lanes_own(monkeypatch):
    today = date(2026, 10, 12)
    rows, _, _ = _wire_lane(monkeypatch, tiered={"OLD": date(2026, 9, 1), "TODY": today})
    graded = []

    async def _grade(c, ticker, rel_volume, **kw):
        graded.append(ticker)
    out = await plane.run_paper_lane_tick(
        [_cand("OLD", gap=8.0), _cand("TODY"), _cand("NEW")], grade=_grade, judge=None,
        scan_row=lambda *a, **k: {}, today=today, now_et=datetime(2026, 10, 12, 9, 20, tzinfo=_ET),
        regime_label=None, judge_timeout_s=5)
    assert graded == ["NEW"] and out["cooldown"] == 1 and out["already_today"] == 1
    assert [(r["ticker"], r["reject_stage"]) for r in rows] == [("OLD", "cooldown")]


@pytest.mark.asyncio
async def test_toggle_off_grades_nothing(monkeypatch):
    _wire_lane(monkeypatch, toggle=False)
    grade = AsyncMock()
    out = await plane.run_paper_lane_tick(
        [_cand()], grade=grade, judge=None, scan_row=lambda *a, **k: {}, today=date(2026, 10, 12),
        now_et=datetime(2026, 10, 12, 9, 20, tzinfo=_ET), regime_label=None, judge_timeout_s=5)
    assert out["skipped"] == "toggle_off" and not grade.await_count


@pytest.mark.asyncio
async def test_a_failing_lane_tick_pages_once_a_day_paper_prefixed_and_never_raises(monkeypatch):
    _wire_lane(monkeypatch)
    monkeypatch.setattr(plane, "get_lowcap_paper_lane_tiered", AsyncMock(side_effect=RuntimeError("db down")))
    pages = []

    async def _tg(msg, *a, **k):
        pages.append(msg)
    from agents.market_intelligence import briefing
    monkeypatch.setattr(briefing, "send_telegram_message", _tg)
    for _ in range(3):
        out = await plane.run_paper_lane_tick(
            [_cand()], grade=AsyncMock(), judge=None, scan_row=lambda *a, **k: {},
            today=date(2026, 10, 12), now_et=datetime(2026, 10, 12, 9, 20, tzinfo=_ET),
            regime_label=None, judge_timeout_s=5)
        assert out["errors"] == 1
    assert len(pages) == 1 and pages[0].startswith("📄 PAPER")


@pytest.mark.asyncio
async def test_inside_the_window_a_lane_high_hands_off_to_the_paper_order_step(monkeypatch):
    _wire_lane(monkeypatch, highs=[dict(_HIGH)])

    class _Now(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 12, 9, 33, tzinfo=_ET)
    monkeypatch.setattr(plane, "datetime", _Now)
    from agents.market_intelligence import execution_client as ec
    trig = AsyncMock(return_value=[{"ticker": "SMLL", "action": "auto_entered"}])
    monkeypatch.setattr(ec, "trigger_lowcap_paper_entry", trig)
    live_trig = AsyncMock()
    monkeypatch.setattr(ec, "trigger_orb_entry", live_trig)
    out = await plane.run_paper_lane_tick(
        [], grade=AsyncMock(), judge=None, scan_row=lambda *a, **k: {}, today=date(2026, 10, 12),
        now_et=datetime(2026, 10, 12, 9, 31, tzinfo=_ET), regime_label=None, judge_timeout_s=5)
    assert trig.await_count == 1 and out["order_step"] == 1
    assert not live_trig.await_count            # never the live order step


def test_the_lane_handoff_is_its_own_cross_function():
    from agents.market_intelligence import execution_client as ec
    from agents.market_intelligence import execution_routes as er
    assert "trigger_lowcap_paper_entry" in ec._CROSS_FNS and "trigger_lowcap_paper_entry" in ec._SLOW_COMMAND_FNS
    assert er._EXEC_HANDLERS["trigger_lowcap_paper_entry"] is ec._trigger_lowcap_paper_entry_inprocess


@pytest.mark.asyncio
async def test_paper_replay_walks_the_lane_population_into_its_own_table(monkeypatch):
    from agents.market_intelligence import lowcap_lane_replay as lcl
    pop = [{"signal_id": 1, "ticker": "SMLL", "scan_date": date(2026, 10, 12),
            "tick_wallclock_et": datetime(2026, 10, 12, 9, 33, tzinfo=_ET)}]
    monkeypatch.setattr(db, "get_lowcap_paper_lane_population", AsyncMock(return_value=pop))
    monkeypatch.setattr(db, "get_lowcap_paper_lane_replay_existing", AsyncMock(return_value={}))
    shadow_pop = AsyncMock(return_value=[])
    monkeypatch.setattr(lcl, "get_lowcap_lane_population", shadow_pop)
    pool, _ = make_mock_pool()
    monkeypatch.setattr(lcl, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(lcl, "log_audit_event", AsyncMock())
    seen = []

    async def _rec(conn, sig, last_session, run_date, out, **kw):
        seen.append((sig["ticker"], kw["upsert"], kw["error_event"]))
    monkeypatch.setattr(lcl, "_record_one_signal", _rec)
    out = await lcl.run_paper_lane_replay(date(2026, 10, 13),
                                          now_et=datetime(2026, 10, 13, 18, 15, tzinfo=_ET))
    assert out["population"] == 1 and not shadow_pop.await_count
    assert seen == [("SMLL", db.upsert_lowcap_paper_lane_replay, "lowcap_paper_lane_replay_error")]


def test_the_paper_replay_upsert_targets_only_its_own_table():
    sql = db.LOWCAP_PAPER_LANE_REPLAY_UPSERT_SQL
    assert sql.startswith("INSERT INTO mi_lowcap_paper_lane_replays")
    assert "mi_lowcap_lane_replays" not in sql
    assert "WHERE mi_lowcap_paper_lane_replays.outcome = 'open'" in sql
