"""#624 SMALL-CAP PAPER LANE — the grading side (2026-10-10, operator "Ok to recs").

HIS RULINGS (PLAN.md #624, quoted there): names turned away ONLY by the $500M market-cap floor
are graded by the SAME live EP score, unchanged, AFTER live grading has finished (background,
never slowing the 09:30–09:45 entry window); a lane HIGH goes to the lane's OWN alerts table and a
PAPER-ONLY order step — never the live alert table, never the live order step; a NEW strategy row
(`magna53_smallcap`) routed to PAPER at size 1.0 carrying MAGNA53's exits; same gates, entry and
stop as MAGNA53. Docs: docs/setups/magna53_ep.md "Small-cap paper lane".

HOW "THE SAME SCORE" IS TRUE BY CONSTRUCTION. `ep_detector.run_ep_scan` collects, inside the
FILTER_MCAP_TOO_SMALL branch of its graded loop, a COPY of every candidate the loop turned away
ONLY on the cap (check_filters reads the cap LAST, so volume pace, cooldown, already-scored,
extension, $1M ADV$ and ATR all passed). At the very END of the scan — after the live judge and
the tape annotation — it calls `schedule_paper_lane_tick` with those copies and its own two
closures: `_grade_admitted` (the live loop's graded tail: volume conviction, catalyst grade,
post-grade filters, score, earnings override) and `_judge_shadow` (the live holistic judge +
authority). This module never restates a gate or a weight; it supplies only SINKS:
  - its own grade cache + re-poll state (never the live `_catalyst_cache`),
  - its own scan rows / results / alert writer → mi_lowcap_paper_lane_alerts,
  - a judge-result writer on the same table,
  - throwaway lists for the live shadow-table inputs, and NO theme-fit budget (the per-day fit
    counter is the live scan's — a name pending a fit judgement keeps list membership),
  - the 'shared' M&A headline-question budget pool (the EP reserve stays the live scan's).
Audit rows the graded path writes stay EXACTLY as live writes them (decisions downstream read some
of them back, e.g. the revenue-weak downgrade the earnings override respects); a study of the
live population excludes lane names by joining (ticker, alert_date) to this lane's table.

ADDED (the lane's own, not live's): a lane cooldown on the lane's OWN tiered alerts (60 days, the
live constant, with live's fresh-earnings bypass) and the lane's own "already scored today".

WHERE IT RUNS. A DETACHED task (strong ref in the scan's `_WATCHDOG_BG_TASKS`); one lane tick at a
time (an asyncio lock — a slow tick never overlaps the next). After grading, inside 09:31–10:00 ET
with at least one lane HIGH today, it hands off to the PAPER-ONLY order step through the execution
facade (`execution_client.trigger_lowcap_paper_entry` → broker/lowcap_paper_entry.py).

TELEGRAM: none for an alert, a grade, a skip or an order (audit rows only — "an alert that says no
action is noise"). A lane FAILURE pages, paper-prefixed, once per failure kind per ET day.
HEARTBEAT: one `lowcap_paper_lane_heartbeat` audit row per scan day (the 18:15 ET job) — screened /
cap-only / graded / HIGH / ordered + a verdict — so a quiet day and a broken lane read differently;
a cap-only name that never reached the lane pages (`write_paper_lane_heartbeat`, below).
MODEL-CALL SLOTS: the lane's own (1 grader, 1 judge — ep_detector._LANE_*_SEMAPHORE), never the
live scan's 5 / 3, so a lane call can never hold a slot a live call waits for.
STOP SWITCH: runtime toggle `lowcap_paper_lane` (default ON, PENDING HIS CONFIRMATION) or
`mi_strategies.enabled` on `magna53_smallcap`.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime
from typing import Any, Callable, Optional

from shared.dates import _ET

from agents.market_intelligence.db import (
    LOWCAP_PAPER_LANE_ACCOUNT_MODE,
    LOWCAP_PAPER_LANE_STRATEGY_ID,
    LOWCAP_PAPER_LANE_TOGGLE,
    LOWCAP_PAPER_LANE_TOGGLE_ENV,
    _f,
    get_lowcap_paper_lane_day,
    get_lowcap_paper_lane_highs,
    get_lowcap_paper_lane_tiered,
    get_runtime_toggle,
    log_audit_event,
    update_lowcap_paper_lane_judge_result,
    upsert_lowcap_paper_lane_row,
)
from agents.market_intelligence.strategies.registry import should_run

logger = logging.getLogger(__name__)

STRATEGY_ID = LOWCAP_PAPER_LANE_STRATEGY_ID
TOGGLE = LOWCAP_PAPER_LANE_TOGGLE
TOGGLE_ENV = LOWCAP_PAPER_LANE_TOGGLE_ENV
LANE_RULE_VERSION = "paper_v1"
LANE_TICK_TIMEOUT_S = 240          # a lane tick that has not finished grading in 4 minutes is cut
                                   # (the next scan tick is 5 minutes away)
_TIERS = ("HIGH", "MODERATE")
# The two reject_stage values the LANE itself writes (every other stage is a live-funnel stage
# `_grade_admitted` passes through). The heartbeat's "graded" count excludes exactly these.
STAGE_COOLDOWN = "cooldown"
STAGE_GRADE_ERROR = "grade_error"

# Lane-owned per-day state (never the live scan's module state).
_grade_cache_date: Optional[date] = None
_grade_cache: dict = {}
_repoll_date: Optional[date] = None
_repoll_state: dict = {}
_paged: set[tuple[str, date]] = set()
_lock: Optional[asyncio.Lock] = None


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


class LaneSink:
    """What `_grade_admitted(..., lane=sink)` and `_judge_shadow(r, lane=sink)` write into."""

    def __init__(self, *, today: date, now_et: datetime, regime_label: Optional[str],
                 scan_row: Callable[..., dict]):
        self.today, self.now_et, self.regime_label = today, now_et, regime_label
        self._scan_row = scan_row
        self.scan_rows: list[dict] = []        # the live scan_log row shape, one per evaluated name
        self.results: list[dict] = []          # the live result shape, one per tiered name
        self.alert_records: dict[str, dict] = {}
        self.candidates: dict[str, dict] = {}  # ticker -> the candidate copy being graded

    # ── the five lane seams `_grade_admitted` reads ──
    def grade_cache(self, today: date) -> dict:
        global _grade_cache_date, _grade_cache
        if _grade_cache_date != today:
            _grade_cache_date, _grade_cache = today, {}
        return _grade_cache

    def repoll_state(self, today: date) -> dict:
        global _repoll_date, _repoll_state
        if _repoll_date != today:
            _repoll_date, _repoll_state = today, {}
        return _repoll_state

    def log_filtered(self, c: dict, reason: str, stage: Optional[str] = None) -> None:
        self.scan_rows.append(self._scan_row(
            c, reason=reason, ep_score=None, tier=None,
            catalyst_quality=c.get("acting_catalyst_quality"), stage=stage))

    async def insert_alert(self, record: dict) -> None:
        """The lane's twin of `insert_ep_alert` — DB first (the judge then updates the row), to
        the LANE table. Raises on a DB error, like the live writer (the lane task counts it)."""
        self.alert_records[record["ticker"]] = record
        c = self.candidates.get(record["ticker"], {})
        await upsert_lowcap_paper_lane_row(self.row_for(c, record=record))

    async def update_judge_result(self, ticker: str, alert_date: date, **kw: Any) -> None:
        r = next((x for x in self.results if x.get("ticker") == ticker), {})
        await update_lowcap_paper_lane_judge_result(
            ticker, alert_date, setup_class=r.get("setup_class"), **kw)

    # ── row assembly ──
    def row_for(self, c: dict, *, record: Optional[dict] = None,
                scan: Optional[dict] = None, stage: Optional[str] = None,
                reason: Optional[str] = None) -> dict:
        scan = scan or {}
        rec = record or {}
        return {
            "ticker": c.get("ticker") or rec.get("ticker") or scan.get("ticker"),
            "alert_date": self.today,
            "strategy_id": STRATEGY_ID,
            "first_graded_at": self.now_et,
            "last_graded_at": self.now_et,
            "detected_at": rec.get("detected_at"),
            "score_tier": rec.get("score_tier"),
            "ep_score": _f(rec.get("ep_score") if record else scan.get("ep_score")),
            "baseline_floor_tier": rec.get("baseline_floor_tier"),
            "grade_engine_authority": rec.get("grade_engine_authority"),
            "reject_stage": None if record else (stage or scan.get("reject_stage")),
            "reject_reason": None if record else (reason or scan.get("filter_reason")),
            "catalyst_quality": (rec.get("catalyst_quality") if record
                                 else scan.get("catalyst_quality") or c.get("acting_catalyst_quality")),
            "llm_catalyst_quality": c.get("llm_catalyst_quality"),
            "catalyst": rec.get("catalyst"),
            "claude_analysis": rec.get("claude_analysis"),
            "gemini_validation": rec.get("gemini_validation"),
            "gap_pct": _f(c.get("gap_pct")),
            "rel_volume": _f(rec.get("rel_volume") if record else c.get("rel_volume")),
            "vol_percentile": _f(c.get("vol_percentile")),
            "pm_rvol": _f(c.get("pm_rvol")),
            "pm_rvol_baseline_n": c.get("pm_rvol_baseline_n"),
            "prev_close": _f(c.get("prev_close")),
            "current_price": _f(c.get("current_price")),
            "market_cap": _f(c.get("market_cap")),
            "quality_adv_dollar": _f(c.get("quality_adv_dollar")),
            "atr_pct": _f(c.get("atr_pct")),
            "score_breakdown": c.get("score_breakdown"),
            "in_active_theme": (rec.get("in_active_theme") if record
                                else scan.get("in_active_theme")),
            "regime": self.regime_label,
            "lane_rule_version": LANE_RULE_VERSION,
        }


async def _page_once(kind: str, today: date, text: str) -> None:
    """A FAILURE page, paper-prefixed, at most once per (kind, ET day). Never raises."""
    if (kind, today) in _paged:
        return
    _paged.add((kind, today))
    try:
        from agents.market_intelligence.briefing import send_telegram_message
        from agents.market_intelligence.constants import mode_prefix
        await send_telegram_message(f"{mode_prefix(LOWCAP_PAPER_LANE_ACCOUNT_MODE)}{text}")
    except Exception as e:  # loud-ok: the audit row the caller wrote is the durable record
        logger.error(f"#624 paper lane page failed: {e}")


def _in_order_window(now: datetime) -> bool:
    """09:31 ≤ now < 10:00 ET — the order step itself decides 09:31–09:45 (submit) vs after
    09:45 (a durable out-of-window skip row)."""
    return now.hour == 9 and now.minute >= 31


async def _lane_cooldown_bypass(c: dict, ticker: str, today: date) -> bool:
    """Live's cooldown bypass, applied to the lane's own cooldown: a fresh earnings day with a
    gap >= 15% is a new event. Same fail-soft direction as live (lookup error → bypass)."""
    if (c.get("gap_pct") or 0) < 15.0:
        return False
    try:
        from agents.market_intelligence.earnings_calendar import is_earnings_day
        match, _ = await is_earnings_day(ticker, today)
        return bool(match)
    except Exception as e:  # loud-ok: fail-soft exactly as live's cooldown bypass
        logger.warning(f"#624 paper lane cooldown: is_earnings_day failed for {ticker} — bypassed: {e}")
        return True


async def _grade_tick(cands: list, *, grade: Callable, judge: Optional[Callable], sink: LaneSink,
                      today: date, judge_timeout_s: float, out: dict) -> None:
    from agents.market_intelligence.ep_detector import EP_COOLDOWN_DAYS
    tiered = await get_lowcap_paper_lane_tiered(today, EP_COOLDOWN_DAYS)
    seen: set[str] = set()
    for c, ticker, rel_volume in cands:
        if ticker in seen:
            continue
        seen.add(ticker)
        last = tiered.get(ticker)
        if last == today:
            out["already_today"] += 1          # live's "already scored earlier today"
            continue
        if last is not None and not await _lane_cooldown_bypass(c, ticker, today):
            out["cooldown"] += 1
            await upsert_lowcap_paper_lane_row(sink.row_for(
                c, stage=STAGE_COOLDOWN,
                reason=f"lane cooldown — the lane alerted it {last.isoformat()}, within "
                       f"{EP_COOLDOWN_DAYS} days"))
            continue
        sink.candidates[ticker] = c
        n_rows, n_res = len(sink.scan_rows), len(sink.results)
        try:
            await grade(c, ticker, rel_volume, lane=sink)
            out["graded"] += 1
        except Exception as e:  # loud-ok: one name's failure is counted, audited and recorded; the rest proceed
            out["errors"] += 1
            del sink.scan_rows[n_rows:]
            del sink.results[n_res:]
            await log_audit_event("lowcap_paper_lane_error",
                                  f"{ticker} {today.isoformat()}: grade failed — {type(e).__name__}: {e}")
            await upsert_lowcap_paper_lane_row(sink.row_for(
                c, stage=STAGE_GRADE_ERROR, reason=f"{type(e).__name__}: {str(e)[:200]}"))

    alerted = [r for r in sink.results if r.get("score_tier") in _TIERS]
    if judge is not None and alerted:
        try:
            await asyncio.wait_for(asyncio.gather(*[judge(r, lane=sink) for r in alerted]),
                                   timeout=judge_timeout_s)
        except Exception as e:  # loud-ok: the floor tiers stand, exactly as live when its judge block fails
            out["errors"] += 1
            await log_audit_event("lowcap_paper_lane_error",
                                  f"{today.isoformat()}: judge pass failed — floor tiers stand: "
                                  f"{type(e).__name__}: {e}")

    # Every evaluated name WITHOUT a tier gets (or refreshes) its row; tiered rows were written
    # DB-first by insert_alert and are frozen against this upsert.
    tiered_now = set(sink.alert_records)
    for row in sink.scan_rows:
        tkr = row.get("ticker")
        if tkr in tiered_now:
            continue
        await upsert_lowcap_paper_lane_row(sink.row_for(sink.candidates.get(tkr, {}), scan=row))
    for r in alerted:
        out["tiered"] += 1
        await log_audit_event(
            "lowcap_paper_lane_alert",
            f"{r['ticker']} {r.get('score_tier')} score={_f(r.get('ep_score'))} "
            f"catalyst={r.get('catalyst_quality')} (PAPER lane, record only)",
            json.dumps({k: r.get(k) for k in ("ticker", "score_tier", "ep_score", "catalyst_quality",
                                              "gap_pct", "market_cap", "grade_engine_authority")},
                       default=str))


async def run_paper_lane_tick(cands: list, *, grade: Callable, judge: Optional[Callable],
                              scan_row: Callable, today: date, now_et: datetime,
                              regime_label: Optional[str], judge_timeout_s: float) -> dict:
    """The detached task body. NEVER raises."""
    out: dict[str, Any] = {"candidates": len(cands), "graded": 0, "tiered": 0, "cooldown": 0,
                           "already_today": 0, "errors": 0, "order_step": None}
    # The lane's OWN model-call slots (10-10 review): every catalyst-grader call made from this
    # task — and from the tasks it spawns — takes the lane's single grader slot, never one of the
    # live scan's five; the judge call takes the lane's own slot (`_judge_shadow(lane=...)`).
    from agents.market_intelligence import ep_detector as _epd
    _slot_token = _epd._GRADER_SEMAPHORE_OVERRIDE.set(_epd._LANE_GRADER_SEMAPHORE)
    try:
        async with _get_lock():
            if not await get_runtime_toggle(TOGGLE, TOGGLE_ENV, default=True):
                out["skipped"] = "toggle_off"
                return out
            if not await should_run(STRATEGY_ID):
                out["skipped"] = "disabled"
                return out
            if cands:
                sink = LaneSink(today=today, now_et=now_et, regime_label=regime_label,
                                scan_row=scan_row)
                await asyncio.wait_for(
                    _grade_tick(cands, grade=grade, judge=judge, sink=sink, today=today,
                                judge_timeout_s=judge_timeout_s, out=out),
                    timeout=LANE_TICK_TIMEOUT_S)
            now = datetime.now(_ET)
            if _in_order_window(now) and await get_lowcap_paper_lane_highs(today):
                from agents.market_intelligence.execution_client import trigger_lowcap_paper_entry
                res = await trigger_lowcap_paper_entry(trigger="lane_tick")
                out["order_step"] = len(res or [])
            if cands:
                await log_audit_event(
                    "lowcap_paper_lane_tick",
                    f"{now_et.strftime('%H:%M')} ET: {out['candidates']} cap-only name(s), "  # recovery-clock-ok: the tick's own wall-clock label
                    f"{out['graded']} graded, {out['tiered']} tiered, {out['cooldown']} on lane "
                    f"cooldown, {out['already_today']} already scored, {out['errors']} error(s)",
                    json.dumps(out, default=str))
    except Exception as e:  # loud-ok: paper-only lane — counted, audited, paged once a day, never reaches the scan
        out["errors"] += 1
        logger.warning(f"#624 paper lane tick failed: {e}")
        try:
            await log_audit_event("lowcap_paper_lane_error",
                                  f"tick {now_et.isoformat()}: {type(e).__name__}: {e}")
        except Exception:  # loud-ok: the warning above already spoke
            pass
        await _page_once("tick_failed", today,
                         f"🚨 Small-cap paper lane tick failed — {type(e).__name__}: {str(e)[:160]} "
                         f"(paper only; the live scan is unaffected)")
    finally:
        _epd._GRADER_SEMAPHORE_OVERRIDE.reset(_slot_token)
    return out


def schedule_paper_lane_tick(cands: list, *, grade: Callable, judge: Optional[Callable],
                             scan_row: Callable, today: date, now_et: datetime,
                             regime_label: Optional[str], judge_timeout_s: float,
                             bg_tasks: set) -> Optional["asyncio.Task"]:
    """The SYNCHRONOUS entry `run_ep_scan` calls LAST: copy the list, detach the task, return it
    (None when there is nothing to grade and no order window to serve). Never awaits."""
    if not cands and not _in_order_window(now_et):
        return None
    task = asyncio.create_task(run_paper_lane_tick(
        list(cands), grade=grade, judge=judge, scan_row=scan_row, today=today, now_et=now_et,
        regime_label=regime_label, judge_timeout_s=judge_timeout_s))
    bg_tasks.add(task)
    task.add_done_callback(bg_tasks.discard)
    return task


# ── DAILY HEARTBEAT (10-10 silent-lane check) ───────────────────────────────────────────────
# The tick writes nothing on a day with no cap-only names, so before this a quiet market and a
# broken lane read the same (no rows). ONE audit row per scan day, read from BOTH sides — the live
# scan's own log (screened / turned away ONLY on the $500M floor) against the lane's own table and
# the paper book — so the two cases differ:
#   quiet       the live scan screened names, none was turned away only on the cap
#   ran         every cap-only name reached the lane (graded, on lane cooldown or a grade error)
#   broken      a cap-only name the live scan turned away NEVER reached the lane → PAGES (paper)
#   off         the toggle / mi_strategies.enabled is off (the lane is meant to be silent)
#   scan_silent the live scan logged nothing today (holiday, or the scan itself) — not the lane's
# Run by the 18:15 ET replay job (scheduler._lowcap_lane_replay_job). A failed read pages.
HEARTBEAT_EVENT = "lowcap_paper_lane_heartbeat"
_LANE_BOOK = LOWCAP_PAPER_LANE_ACCOUNT_MODE   # the lane's one book — the heartbeat counts its paper orders only
_NOT_GRADED_STAGES = (STAGE_COOLDOWN, STAGE_GRADE_ERROR)


async def write_paper_lane_heartbeat(today: date) -> dict:
    """Write today's heartbeat row (once per day — a re-run finds it and writes nothing). Returns
    the counts + verdict. NEVER raises."""
    from agents.market_intelligence.broker.skip_reasons import FILTER_MCAP_TOO_SMALL
    out: dict[str, Any] = {"date": today.isoformat(), "verdict": None}
    try:
        day = await get_lowcap_paper_lane_day(
            today, mcap_reason=FILTER_MCAP_TOO_SMALL, strategy_id=STRATEGY_ID,
            account_mode=_LANE_BOOK, heartbeat_event=HEARTBEAT_EVENT)
        if day["already_written"]:
            out["verdict"] = "already_written"
            return out
        enabled = (await get_runtime_toggle(TOGGLE, TOGGLE_ENV, default=True)
                   and await should_run(STRATEGY_ID))
        rows = day["lane_rows"]
        reached = {r["ticker"] for r in rows}
        missing = [t for t in day["cap_only"] if t not in reached]
        out.update({
            "screened": day["screened"],
            "cap_only_eligible": len(day["cap_only"]),
            "reached_lane": len(reached),
            "graded": len({r["ticker"] for r in rows
                           if r.get("reject_stage") not in _NOT_GRADED_STAGES}),
            "high": len({r["ticker"] for r in rows if r.get("score_tier") == "HIGH"}),
            "ordered": day["ordered"],
            "missing": missing,
            "lane_enabled": bool(enabled),
        })
        if day["screened"] == 0:
            out["verdict"] = "scan_silent"
        elif not enabled:
            out["verdict"] = "off"
        elif missing:
            out["verdict"] = "broken"
        elif not day["cap_only"]:
            out["verdict"] = "quiet"
        else:
            out["verdict"] = "ran"
        summary = (f"{today.isoformat()} {out['verdict']}: {out['screened']} screened by the live "
                   f"scan, {out['cap_only_eligible']} turned away only by the $500M floor, "
                   f"{out['graded']} graded by the lane, {out['high']} HIGH, "
                   f"{out['ordered']} paper order(s)"
                   + (f"; NEVER reached the lane: {', '.join(missing)}" if missing else ""))
        await log_audit_event(HEARTBEAT_EVENT, summary, json.dumps(out, default=str))
        if out["verdict"] == "broken":
            await _page_once("heartbeat_broken", today,
                             f"🚨 Small-cap paper lane looked BROKEN today: {len(missing)} name(s) "
                             f"the live scan turned away only on the $500M floor never reached the "
                             f"lane ({', '.join(missing[:8])}). Paper only; the live scan is "
                             f"unaffected.")
    except Exception as e:  # loud-ok: audited + paged once a day; the heartbeat never raises into the job
        out["verdict"] = "read_failed"
        logger.warning(f"#624 paper lane heartbeat failed: {e}")
        try:
            await log_audit_event("lowcap_paper_lane_error",
                                  f"heartbeat {today.isoformat()}: {type(e).__name__}: {e}")
        except Exception:  # loud-ok: the warning above already spoke
            pass
        await _page_once("heartbeat_failed", today,
                         f"🚨 Small-cap paper lane heartbeat could not read the day — "
                         f"{type(e).__name__}: {str(e)[:160]} (paper only)")
    return out
