"""#624 small-cap PAPER lane — the 10-10 review's fixes, each pinned by behaviour.

His ruling (PLAN.md #624): the lane grades "after live grading has finished, in the background,
NEVER slowing the 09:30–09:45 entry window". Each test below is RED on the pre-fix code
(mutation named in its docstring):
  1. the lane's model calls take the lane's OWN slots (1 grader, 1 judge), never a live one;
  2. the lane cooldown's window is inclusive at today − 60, like live's;
  3. a lane name never feeds the cross-strategy allocator;
  4. the lane grades a COPY of the live candidate — the live dict is never written by the lane;
  5. the daily heartbeat: one audit row per scan day, and a quiet day reads differently from a
     broken lane.
"""
from __future__ import annotations

import asyncio
import re
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from agents.market_intelligence import db
from agents.market_intelligence import ep_detector
from agents.market_intelligence import lowcap_paper_lane as plane
from tests.conftest import make_mock_pool
from tests.test_624_paper_lane import _cand, _wire_lane

_ET = ZoneInfo("America/New_York")
TODAY = date(2026, 10, 12)


# ── 1. the lane's own model-call slots ──────────────────────────────────────────────────────


_GRADE = {"quality": "strong", "deal_role": "none", "deal_status": "none",
          "deal_consideration": "none", "deal_counterparty": "none",
          "quality_if_no_deal": "strong", "analysis": "Concrete FDA approval for the lead asset."}


@pytest.mark.asyncio
async def test_a_lane_grader_call_never_takes_a_live_slot(monkeypatch):
    """A busy live tick holds all five live grader slots. A lane tick grading at the same moment
    must still complete — on its own single slot — and leave every live slot untouched. The
    grade runs the REAL `_classify_catalyst_claude` (fake model client only).
    MUTATION: route the lane through the live semaphore (`_grader_semaphore()` → always
    `_ANTHROPIC_SEMAPHORE`, or drop the override in `run_paper_lane_tick`) — the lane call
    then waits on a live slot and the tick times out."""
    live = asyncio.Semaphore(5)
    lane_sem = asyncio.Semaphore(1)
    monkeypatch.setattr(ep_detector, "_ANTHROPIC_SEMAPHORE", live)
    monkeypatch.setattr(ep_detector, "_LANE_GRADER_SEMAPHORE", lane_sem)
    _wire_lane(monkeypatch)
    seen = {}

    async def create(**kw):
        seen["lane_slot_held"] = lane_sem.locked()
        seen["live_free_slots"] = live._value
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=dict(_GRADE))],
                               stop_reason="tool_use")

    async def _grade(c, ticker, rel_volume, **kw):
        q, _ = await ep_detector._classify_catalyst_claude(
            ticker, [], {"companyName": "Small Co", "sector": "Healthcare", "marketCap": 1.3e8},
            grounded_text="Small Co received FDA approval.")
        seen["quality"] = q

    for _ in range(5):                      # the live tick holds every live slot
        await live.acquire()
    try:
        with patch.object(ep_detector._get_claude(), "messages") as m, \
             patch("agents.market_intelligence.spend_tracker.log_anthropic_call_safe",
                   new=AsyncMock(return_value=None)):
            m.create = create
            out = await asyncio.wait_for(plane.run_paper_lane_tick(
                [_cand()], grade=_grade, judge=None, scan_row=lambda *a, **k: {}, today=TODAY,
                now_et=datetime(2026, 10, 12, 9, 36, tzinfo=_ET), regime_label=None,
                judge_timeout_s=5), timeout=3)
    finally:
        for _ in range(5):
            live.release()
    assert out["graded"] == 1 and out["errors"] == 0 and seen["quality"] == "strong"
    assert seen["lane_slot_held"] is True          # the lane used ITS slot
    assert seen["live_free_slots"] == 0            # and never touched a live one
    # the override lives only in the lane task — the caller's (live) context is unchanged
    assert ep_detector._grader_semaphore() is live


@pytest.mark.asyncio
async def test_the_lane_judge_call_takes_the_lanes_own_slot_and_live_keeps_its_three(monkeypatch):
    """Through the REAL run_ep_scan: the lane's judge call carries the lane's judge semaphore
    (size 1), the live judge call carries the live one (size 3). MUTATION: pass
    `_JUDGE_SEMAPHORE` in `_judge_shadow`'s lane branch."""
    from tests.test_624_lowcap_lane import _run_scan_once
    from agents.market_intelligence import ep_grade_judge
    await _run_scan_once(monkeypatch, lane_mode="off", admit=True, lowcap_admit="BIG05",
                         paper_mode="on", paper_sink={})
    sems = {c.kwargs.get("log_caller"): c.kwargs.get("semaphore")
            for c in ep_grade_judge.grade_holistic.await_args_list}
    assert set(sems) == {"ep_grade_judge", "lowcap_paper_lane_judge"}
    assert sems["lowcap_paper_lane_judge"] is ep_detector._LANE_JUDGE_SEMAPHORE
    assert sems["ep_grade_judge"] is ep_detector._JUDGE_SEMAPHORE
    assert ep_detector._LANE_JUDGE_SEMAPHORE is not ep_detector._JUDGE_SEMAPHORE
    assert ep_detector._LANE_JUDGE_SEMAPHORE._value == 1 and ep_detector._LANE_GRADER_SEMAPHORE._value == 1


# ── 2. the lane cooldown window ─────────────────────────────────────────────────────────────


_PRED = re.compile(r"alert_date\s*(>=|<=|>|<|=)\s*(\$1::date(?:\s*-\s*\$2::int)?)")
_OPS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b,
        "<": lambda a, b: a < b, "=": lambda a, b: a == b}


def _run_window(sql: str, rows: list[dict], today: date, days: int) -> list[dict]:
    """Evaluates the lane query's WHERE clause as written (its `alert_date <op> <bound>` terms
    and `score_tier IS NOT NULL`) over fixture rows — there is no Postgres in the test env. An
    unrecognised predicate shape fails loudly rather than passing."""
    preds = _PRED.findall(sql)
    assert len(preds) == 2, f"unrecognised window predicates in {sql!r}"
    assert "score_tier IS NOT NULL" in sql
    out = []
    for r in rows:
        if r["score_tier"] is None:
            continue
        ok = True
        for op, rhs in preds:
            bound = today - timedelta(days=days) if "$2" in rhs else today
            ok = ok and _OPS[op](r["alert_date"], bound)
        if ok:
            out.append(r)
    return out


@pytest.mark.asyncio
async def test_a_name_the_lane_alerted_exactly_60_days_ago_is_still_on_the_lane_cooldown(monkeypatch):
    """Live's cooldown is `alert_date >= today - EP_COOLDOWN_DAYS` (run_ep_scan); the lane's
    twin must use the same inclusive bound. MUTATION: `>=` back to `>` in
    `_LOWCAP_PAPER_LANE_TIERED_SQL` — the 60-days-ago name drops out of the cooldown."""
    days = ep_detector.EP_COOLDOWN_DAYS
    rows = [{"ticker": "D60", "alert_date": TODAY - timedelta(days=days), "score_tier": "HIGH"},
            {"ticker": "D61", "alert_date": TODAY - timedelta(days=days + 1), "score_tier": "HIGH"},
            {"ticker": "D59", "alert_date": TODAY - timedelta(days=days - 1), "score_tier": "MODERATE"},
            {"ticker": "NOTIER", "alert_date": TODAY - timedelta(days=5), "score_tier": None},
            {"ticker": "TODAY", "alert_date": TODAY, "score_tier": "HIGH"}]
    pool, conn = make_mock_pool()

    async def _fetch(sql, today, n):
        return _run_window(sql, rows, today, n)
    conn.fetch = _fetch
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    got = await db.get_lowcap_paper_lane_tiered(TODAY, days)
    assert set(got) == {"D60", "D59", "TODAY"}
    assert got["D60"] == TODAY - timedelta(days=days)


# ── 3 + 4. the live scan's allocator and candidate dicts, through the real run_ep_scan ───────


@pytest.mark.asyncio
async def test_a_lane_name_never_feeds_the_cross_strategy_allocator(monkeypatch):
    """BIG00 (live HIGH) is enqueued for the allocator; BIG05 (lane HIGH, same grade) is not.
    MUTATION: drop `lane is None and` from the allocator guard in `_grade_admitted`."""
    from tests.test_624_lowcap_lane import _run_scan_once, ADMIT_TICKER
    enq = []

    async def _enqueue(**kw):
        enq.append(kw["ticker"])
    monkeypatch.setattr(ep_detector, "enqueue_pending_allocation", _enqueue)
    sink: dict = {}
    await _run_scan_once(monkeypatch, lane_mode="off", admit=True, lowcap_admit="BIG05",
                         paper_mode="on", paper_sink=sink)
    assert any(r["ticker"] == "BIG05" and r["score_tier"] == "HIGH" for r in sink["rows"])
    assert enq == [ADMIT_TICKER]


@pytest.mark.asyncio
async def test_the_lane_grades_a_copy_and_never_writes_the_live_candidate(monkeypatch):
    """The lane's grade writes into the candidate (acting_catalyst_quality, score_breakdown, …).
    It must write into a COPY: the live candidate dict the scan built is byte-for-byte what it
    was when the lane was dispatched, after the lane has graded it to HIGH. MUTATION:
    `dict(c)` → `c` at the FILTER_MCAP_TOO_SMALL append."""
    import copy
    from tests.test_624_lowcap_lane import _run_scan_once
    born: dict[str, list] = {}
    real_snap = ep_detector._snap_candidate

    def _rec(ticker, *a, **k):
        d = real_snap(ticker, *a, **k)
        born.setdefault(ticker, []).append(d)
        return d
    monkeypatch.setattr(ep_detector, "_snap_candidate", _rec)
    at_dispatch = {}
    real_sched = plane.schedule_paper_lane_tick

    def _sched(cands, **kw):
        for c, t, _ in cands:
            live = born[t][-1]
            at_dispatch[t] = (c, live, copy.deepcopy(live))
        return real_sched(cands, **kw)
    sink: dict = {}
    # the harness patches schedule_paper_lane_tick only in 'raising' mode, so this wrapper stays
    monkeypatch.setattr(plane, "schedule_paper_lane_tick", _sched)
    await _run_scan_once(monkeypatch, lane_mode="off", admit=True, lowcap_admit="BIG05",
                         paper_mode="on", paper_sink=sink)
    assert any(r["ticker"] == "BIG05" and r["score_tier"] == "HIGH" for r in sink["rows"])
    lane_c, live_c, live_before = at_dispatch["BIG05"]
    assert lane_c is not live_c
    assert lane_c.get("acting_catalyst_quality") == "game_changer"   # the lane graded its copy
    assert live_c == live_before                                     # the live dict was not written


# ── 5. the daily heartbeat ──────────────────────────────────────────────────────────────────


def _wire_heartbeat(monkeypatch, *, screened=40, cap_only=(), lane_rows=(), ordered=0,
                    written=False, toggle=True, raise_read=False):
    audits, pages, calls = [], [], []
    pool, conn = make_mock_pool()

    async def _fetchrow(sql, *args):
        if raise_read:
            raise RuntimeError("db down")
        calls.append(("screened", args))
        return {"screened": screened, "cap_only": list(cap_only)}

    async def _fetch(sql, *args):
        calls.append(("rows", args))
        return [dict(r) for r in lane_rows]

    async def _fetchval(sql, *args):
        calls.append(("val", args))
        if "mi_live_trades" in sql:
            return ordered
        if "mi_audit_log" in sql:
            return written
        raise AssertionError(sql)
    conn.fetchrow, conn.fetch, conn.fetchval = _fetchrow, _fetch, _fetchval
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))

    async def _audit(ev, summary, detail=""):
        audits.append((ev, summary, detail))

    async def _tg(msg, *a, **k):
        pages.append(msg)
    monkeypatch.setattr(plane, "log_audit_event", _audit)
    monkeypatch.setattr(plane, "get_runtime_toggle", AsyncMock(return_value=toggle))
    monkeypatch.setattr(plane, "should_run", AsyncMock(return_value=True))
    monkeypatch.setattr(plane, "_paged", set())
    from agents.market_intelligence import briefing
    monkeypatch.setattr(briefing, "send_telegram_message", _tg)
    return audits, pages, calls


@pytest.mark.asyncio
async def test_a_quiet_day_and_a_broken_lane_write_different_heartbeats(monkeypatch):
    """THE point of the heartbeat. Quiet: the live scan screened names, none was turned away
    only on the cap → one `quiet` row, no page. Broken: RNA was turned away only on the cap and
    never reached the lane → one `broken` row naming RNA, and a PAPER page. Before the fix both
    days left NO row (the tick writes only when it has candidates)."""
    audits, pages, _ = _wire_heartbeat(monkeypatch, cap_only=())
    q = await plane.write_paper_lane_heartbeat(TODAY)
    assert q["verdict"] == "quiet" and q["screened"] == 40 and q["cap_only_eligible"] == 0
    assert [a[0] for a in audits] == ["lowcap_paper_lane_heartbeat"] and pages == []
    assert audits[0][1].startswith("2026-10-12 quiet:")

    audits, pages, calls = _wire_heartbeat(monkeypatch, cap_only=("RNA",))
    b = await plane.write_paper_lane_heartbeat(TODAY)
    assert b["verdict"] == "broken" and b["missing"] == ["RNA"]
    assert [a[0] for a in audits] == ["lowcap_paper_lane_heartbeat"] and "RNA" in audits[0][1]
    assert len(pages) == 1 and pages[0].startswith("📄 PAPER") and "RNA" in pages[0]
    # the read is the live scan's own cap reason, the lane's strategy and the PAPER book only
    assert calls[0][1][1] == "filter:mcap_too_small"
    assert ("val", (TODAY, "magna53_smallcap", "paper")) in calls


@pytest.mark.asyncio
async def test_a_day_the_lane_ran_counts_graded_high_and_orders(monkeypatch):
    rows = [{"ticker": "RNA", "score_tier": "HIGH", "reject_stage": None},
            {"ticker": "OLD", "score_tier": None, "reject_stage": "cooldown"},
            {"ticker": "LOW", "score_tier": None, "reject_stage": "score_bar"}]
    audits, pages, _ = _wire_heartbeat(monkeypatch, cap_only=("LOW", "OLD", "RNA"),
                                       lane_rows=rows, ordered=1)
    out = await plane.write_paper_lane_heartbeat(TODAY)
    assert out["verdict"] == "ran" and out["missing"] == []
    assert (out["cap_only_eligible"], out["reached_lane"], out["graded"], out["high"],
            out["ordered"]) == (3, 3, 2, 1, 1)
    assert len(audits) == 1 and pages == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kw,verdict", [
    ({"screened": 0, "cap_only": ()}, "scan_silent"),
    ({"cap_only": ("RNA",), "toggle": False}, "off"),
])
async def test_off_and_a_silent_scan_are_their_own_verdicts_and_never_page(monkeypatch, kw, verdict):
    audits, pages, _ = _wire_heartbeat(monkeypatch, **kw)
    out = await plane.write_paper_lane_heartbeat(TODAY)
    assert out["verdict"] == verdict and len(audits) == 1 and pages == []


@pytest.mark.asyncio
async def test_the_heartbeat_is_written_once_per_day(monkeypatch):
    audits, pages, _ = _wire_heartbeat(monkeypatch, cap_only=("RNA",), written=True)
    out = await plane.write_paper_lane_heartbeat(TODAY)
    assert out["verdict"] == "already_written" and audits == [] and pages == []


@pytest.mark.asyncio
async def test_a_failed_heartbeat_read_pages_and_never_raises(monkeypatch):
    audits, pages, _ = _wire_heartbeat(monkeypatch, raise_read=True)
    out = await plane.write_paper_lane_heartbeat(TODAY)
    assert out["verdict"] == "read_failed"
    assert [a[0] for a in audits] == ["lowcap_paper_lane_error"]
    assert len(pages) == 1 and pages[0].startswith("📄 PAPER")


@pytest.mark.asyncio
async def test_the_1815_job_writes_the_heartbeat_even_when_both_walkers_fail(monkeypatch):
    from agents.market_intelligence import lowcap_lane_replay as lcl
    from agents.market_intelligence import scheduler
    monkeypatch.setattr(lcl, "run_lowcap_lane_replay", AsyncMock(side_effect=RuntimeError("a")))
    monkeypatch.setattr(lcl, "run_paper_lane_replay", AsyncMock(side_effect=RuntimeError("b")))
    monkeypatch.setattr(scheduler, "notify_job_failure", AsyncMock())
    hb = AsyncMock(return_value={"verdict": "quiet"})
    monkeypatch.setattr(plane, "write_paper_lane_heartbeat", hb)
    await scheduler._lowcap_lane_replay_job()
    assert hb.await_count == 1
