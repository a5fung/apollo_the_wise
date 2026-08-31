"""2026-08-30 — #327 DELAYED-ENTRY WATCH LANE (Stage 0 verdict: REBUILD, not re-seed).

Every name the EP scan sees joins the lane on its EP day and is watched for 20 trading
sessions. Each evening the lane records the name's state (raw facts about the path —
never computed points) and checks whether any of three entry patterns fired, writing the
ex-ante decision vector at the moment of each fire. The single question this exists to
answer: **the real-tail rate `p` of a live, non-outcome-conditioned watch lane** — the
historical studies' fatal flaw was that names were in them *because they worked*
(plan of record: ~/.claude/plans/crystalline-waddling-charm.md; Stage 0 diagnosis:
docs/analysis/327_stage0_anticipation_diagnosis_2026-08-30.md).

THE LINE — read this before touching anything here. This module is a passive OBSERVER:
  - It has EXACTLY TWO write targets: `mi_delayed_entry_watch` and
    `mi_delayed_entry_trigger` (plus `mi_audit_log` via the shared `log_audit_event`
    telemetry helper — never a trade-state table).
  - It NEVER writes to `mi_live_trades`, `mi_live_orders`, or any column any live
    decision reads. It never calls the Alpaca client, `order_manager`, or
    `live_tracker`, and imports NOTHING from `broker/`.
  - It reads `mi_ep_scan_log`, `mi_daily_closes` (+ the Polygon daily/minute fallbacks
    already used elsewhere for telemetry) — all read-only.
  - It is read by NO grading / entry / sizing / ordering / safeguard path — comparison
    telemetry only (the ep_shortlist_shadow / catalyst_tier_shadow contract).
  - **SILENT.** No Telegram, ever, while evidence accrues (operator ruling 2026-08-30:
    an unproven signal in his notifications becomes a de-facto trade signal). Errors
    degrade to `mi_audit_log` + logs; the detector-liveness registry
    (health_checks._DETECTOR_LIVENESS_TABLES) is the watchdog for a silently-dead
    writer.
  - It does NOT import from `anticipation.py`'s frozen Family-B machine (`replay()` is
    pinned by ADR 0013 + the golden test; Stage 0 D1-D13). This lane is the separate
    record-everything path that verdict called for.

THE THREE PATTERNS (v1) — each states its buy and its stop, or it is not a setup:
  ep_low_reclaim    price drops below the EP day's LOW, then a 5-min bar closes back
                    above it. Buy = that close. Stop = the lowest low since the undercut.
  ep_close_reclaim  price never reaches the EP-day low, but dips under the EP day's
                    CLOSE and a 5-min bar closes back above it. Buy = that close.
                    Stop = the lowest low of the dip.
  ep_high_break     price never pulls back — it pushes above the EP day's HIGH.
                    Buy = that high (stop-buy at the level). Stop = the prior session's
                    low.
Every trigger row records buy, stop, and **stop width as % of entry as a first-class
column** — stop width explained the entire measured difference between patterns (same
move captured, 2.68% vs 8.75% risk) and must never be derive-it-later. Each row stamps
`pattern_version` — a reader must never infer the acting definition from a date.

MEASUREMENT CONVENTIONS:
  - Within a 5-min bar the LOW is processed before the close/high (stop-first, "pess" —
    the scripts/probes/_bt_replay.py convention). A bar that both undercuts a pivot and
    closes back above it IS a reclaim of that pivot; a bar that both dips below the
    EP-day close and touches the EP-day high does NOT fire the breakout (the pullback
    is presumed first). Conservative by construction: never fabricates a
    never-pulled-back fire.
  - THE ABSTAIN RULE (db.py mi_anticipation_lifecycle header; anticipation.py:447-457):
    a minute-resolution check whose bars are missing ABSTAINS — the session's row says
    `eval_status='unscoreable'` and the walker RETRIES it (re-walking forward from the
    first unscoreable session) on every run while the name is in the lane. Never a
    daily-bar fallback for a minute tactic, never a fabricated fill. A fire recorded
    after unscoreable sessions stamps `prior_missing_sessions > 0` so the review can
    see the observed fire may be later than the true first one.
  - Minute bars come from Polygon 1-min aggs, converted to ET via ZoneInfo (never a
    hard-coded UTC offset — Stage 0 D11) and aggregated to completed RTH 5-min bars.
  - Screen membership (open gap >=8%, prior close >=$5, day-0 dollar volume >=$50M,
    extension <=50%, catalyst grade >= strong) is stamped per row from EP-day facts —
    computable ex ante, NOT an outcome label; a missing component leaves it NULL,
    never guessed. Raw components are stored so any variant can be re-cut.
  - Day-2+ only: same-day re-entry is explicitly out of scope (tick-level state would
    break the shadow/live-execution boundary).

SETTLEMENT (2026-08-30, same-day follow-on — settle_open_triggers, driven inline by the
same 17:57 job; one job -> one digest). Every open trigger is followed forward for 20
trading sessions FROM ITS FIRE and settled under TWO arms on one row, in one write:
  M-none   hard stop only — no partial, no breakeven, no trail. Stop touch (low <= stop,
           pess stop-first) -> -1.0R at the stop level (the _bt_replay/house convention;
           mae_r still records the raw low, so a gap-through stays visible). Never
           stopped -> exit at the 20th session's close. `realized_r` = THIS arm's
           HARVESTED R — the accrual-gate column — never MFE (db.py:2167 discipline).
  M-trail  the same hard stop stays live, AND exit on a daily close below
           MAX(SMA10, SMA20) — live exit_logic semantics verbatim: SMA includes the
           session's own close, <20 closes falls back to SMA10 alone, <10 closes -> no
           trail line yet, so no trail exit (the live None-guard). Whichever comes first;
           still open at session 20 -> time exit at that close.
  ⚠ The live day-1 shape (+2R partial -> breakeven) is deliberately NOT an arm
    (operator 08-30) — it belongs to a different setup.
  - SETTLE AS SOON AS DEFINITIVE (the anticipation.settle_entry_shadow semantics,
    re-implemented for these arms — that frozen core settles a +1R/+3R harvest, D8): a
    day-3 stop-out settles on day 3, never waits for day 20. The single write happens
    when the M-none arm resolves (the longest hold — a shared-stop hit ends both arms,
    and a trail exit can only be earlier), guarded on `outcome IS NULL` so a
    double-settle is a no-op.
  - THE ABSTAIN RULE applies with full force: a session with no daily bar (stored OR
    single-day fallback) blocks the walk AT that session — never leap a gap, never
    interpolate. Day 0 of a minute-grade fire whose daily low touched the stop (for a
    reclaim the pre-fire undercut low often IS the stop) can only be ordered by the
    post-fire 5-min bars — missing minutes ABSTAIN and retry next run. A daily-grade
    fire's day-0 spanning bar reads stop-first (pess — the documented house bound).
  - Rows that can NEVER become definitive are not orphaned: after
    SETTLE_ORPHAN_CAL_DAYS (well past the 20-session window) a still-abstaining row is
    CLOSED as outcome='unscoreable' with every R column NULL — recorded, never
    interpolated, and never counted by the accrual gate (realized_r IS NOT NULL).
    Degenerate geometry (stop >= entry, recorded-never-dropped at fire time) closes as
    unscoreable immediately — R is undefined there.
  - mfe_r/mae_r are EXCURSION TELEMETRY over the M-none hold (ceiling/floor: the exit
    session's high/low fold in, the entry_bet_outcome convention) — never the result.
    reached_4r is pess: a session that touches the stop credits no 4R that day, and a
    minute-fire's own day-0 daily high is never credited (pre-fire highs are
    indistinguishable at daily grade).
  - An open row is distinguishable at a glance: outcome IS NULL + settled_at IS NULL;
    the digest logs considered-vs-settled-vs-abstained so a silent zero is
    distinguishable from "nothing ripe yet". SILENT — no Telegram on any path.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from shared.dates import _ET

from agents.market_intelligence.db import (
    _f,
    count_delayed_entry_unscoreable,
    get_delayed_entry_daily_bar,
    get_delayed_entry_daily_window,
    get_delayed_entry_open_lane,
    get_delayed_entry_open_triggers,
    get_delayed_entry_seed_candidates,
    get_delayed_entry_watch_row,
    insert_delayed_entry_trigger,
    log_audit_event,
    settle_delayed_entry_trigger,
    upsert_delayed_entry_watch,
)

logger = logging.getLogger(__name__)

PATTERN_VERSION = "v1"
SCREEN_VERSION = "screen_v1"      # gap>=8, prev_close>=5, $vol>=50M, ext<=50, grade>=strong
SETTLE_VERSION = "settle_v1"      # M-none / M-trail, 20 sessions from the fire, pess
LANE_SESSIONS = 20                # forward trading sessions a name stays in the lane
SETTLE_HOLD_SESSIONS = 20         # forward trading sessions a TRIGGER is followed (from its fire)
SETTLE_TAIL_R = 4.0               # the reached_4r threshold (P3 — the tail is the objective)
SETTLE_ORPHAN_CAL_DAYS = 45       # abstaining past this age (well beyond 20 sessions + holidays)
                                  # closes as outcome='unscoreable' — recorded, never interpolated
_SETTLE_SMA_FETCH_CAL_DAYS = 60   # calendar days pre-fire fetched to seed the SMA20 trail
ENROLL_LOOKBACK_DAYS = 7          # calendar days enrollment scans back (self-healing)
_LANE_MAX_CAL_DAYS = 45           # calendar bound covering 20 sessions + holidays
_ADR_WINDOW = 20                  # sessions in the ADR mean
_ADR_FETCH_CAL_DAYS = 60          # calendar days fetched to cover the ADR window

_RTH_OPEN_MIN = 9 * 60 + 30
_RTH_CLOSE_MIN = 16 * 60

# Grades counting as ">= strong" for the screen stamp (ep_rubric's catalyst points
# vocabulary: only game_changer/strong score above default).
_SCREEN_STRONG_GRADES = frozenset({"strong", "game_changer"})

RUNG_EP_LOW = "ep_low_reclaim"
RUNG_EP_CLOSE = "ep_close_reclaim"
RUNG_EP_HIGH = "ep_high_break"

_STATE_KEYS = (
    "undercut_seen", "low_since_undercut",
    "dipped_below_close_seen", "low_of_dip", "gap_high_exceeded",
    "fired_ep_low_reclaim", "fired_ep_close_reclaim", "fired_ep_high_break",
)


def new_state() -> dict[str, Any]:
    """Clean per-member pattern state (as of the end of the EP day itself)."""
    return {
        "undercut_seen": False, "low_since_undercut": None,
        "dipped_below_close_seen": False, "low_of_dip": None,
        "gap_high_exceeded": False,
        "fired_ep_low_reclaim": False, "fired_ep_close_reclaim": False,
        "fired_ep_high_break": False,
    }


def state_from_row(row: dict) -> dict[str, Any]:
    """Extract the carried pattern state from a stored watch row (the walk seed)."""
    st = new_state()
    for k in _STATE_KEYS:
        v = row.get(k)
        if v is not None:
            st[k] = _f(v) if k in ("low_since_undercut", "low_of_dip") else bool(v)
    return st


def _min(a: Optional[float], b: float) -> float:
    return b if a is None else min(a, b)


# ── Pure compute (fixture-testable, no IO) ─────────────────────────────────────────────


def to_rth_5min(raw: list[dict], session_day: date) -> list[dict]:
    """Polygon 1-min aggs ({t: epoch_ms, o,h,l,c,v}) → ascending completed RTH 5-min bars
    {m, o, h, l, c} for `session_day`. ET conversion via ZoneInfo — never a hard-coded
    UTC offset (the Stage 0 D11 class: UTC−4 silently shifts one hour every EST winter)."""
    buckets: dict[int, dict] = {}
    for b in raw or []:
        try:
            et = datetime.fromtimestamp(int(b["t"]) / 1000, tz=timezone.utc).astimezone(_ET)
            o, h, l, c = float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])
        except (KeyError, TypeError, ValueError, OSError):
            continue
        if et.date() != session_day:
            continue
        m = et.hour * 60 + et.minute
        if not (_RTH_OPEN_MIN <= m < _RTH_CLOSE_MIN):
            continue
        b5 = m - ((m - _RTH_OPEN_MIN) % 5)
        cur = buckets.get(b5)
        if cur is None:
            buckets[b5] = {"m": b5, "o": o, "h": h, "l": l, "c": c, "_last": m}
        else:
            cur["h"] = max(cur["h"], h)
            cur["l"] = min(cur["l"], l)
            if m >= cur["_last"]:
                cur["c"] = c
                cur["_last"] = m
    out = []
    for b in sorted(buckets.values(), key=lambda x: x["m"]):
        b.pop("_last", None)
        out.append(b)
    return out


def session_needs_minutes(day_high: float, day_low: float, *, gap_low: float,
                          gap_close: float, gap_high: float, state: dict) -> bool:
    """Could a minute-resolution check change this session's record? True → the walker
    must fetch 5-min bars (and ABSTAIN if they are missing). Daily pre-filter only —
    never decides a fire itself."""
    p1 = (not state["fired_ep_low_reclaim"]
          and (state["undercut_seen"] or day_low < gap_low)
          and day_high > gap_low)
    p2 = (not state["fired_ep_close_reclaim"] and not state["undercut_seen"]
          and (state["dipped_below_close_seen"] or day_low < gap_close)
          and day_high > gap_close)
    clean_before = not state["undercut_seen"] and not state["dipped_below_close_seen"]
    p3_ambiguous = (not state["fired_ep_high_break"] and clean_before
                    and day_high >= gap_high and day_low < gap_close)
    return p1 or p2 or p3_ambiguous


def evaluate_session_minute(bars5: list[dict], *, gap_low: float, gap_close: float,
                            gap_high: float, prior_session_low: Optional[float],
                            state: dict) -> dict:
    """One chronological pass over a session's completed 5-min bars. Pure.

    Per-bar order (pess, stop-first — see module docstring): the bar's LOW folds into
    the excursion state FIRST, then fires are evaluated against its close/high. So a
    same-bar undercut-of-the-EP-low kills an ep_close_reclaim before that bar's close
    can fire it, and a same-bar dip below the EP close blocks the ep_high_break.

    Returns {"fires": [{rung, entry, stop, fire_minute}...], "state": new_state,
    "p3_needs_prior_low": bool} — the flag is True when an ep_high_break would have
    fired but prior_session_low was None (caller marks the session unscoreable so the
    fire is retried, never guessed)."""
    st = dict(state)
    fires: list[dict] = []
    p3_needs_prior_low = False
    for b in bars5:
        lo, hi, close = b["l"], b["h"], b["c"]
        # ── stop-first fold: this bar's low updates the raw excursion facts ──
        if lo < gap_low and not st["undercut_seen"]:
            st["undercut_seen"] = True
            st["low_since_undercut"] = lo
        if st["undercut_seen"]:
            st["low_since_undercut"] = _min(st["low_since_undercut"], lo)
        if lo < gap_close and not st["dipped_below_close_seen"]:
            st["dipped_below_close_seen"] = True
            st["low_of_dip"] = lo
        if st["dipped_below_close_seen"]:
            st["low_of_dip"] = _min(st["low_of_dip"], lo)
        # ── fires, against this bar's close/high ──
        if (not st["fired_ep_low_reclaim"] and st["undercut_seen"] and close > gap_low
                and st["low_since_undercut"] is not None and st["low_since_undercut"] > 0):
            fires.append({"rung": RUNG_EP_LOW, "entry": close,
                          "stop": st["low_since_undercut"], "fire_minute": b["m"]})
            st["fired_ep_low_reclaim"] = True
        if (not st["fired_ep_close_reclaim"] and not st["undercut_seen"]
                and st["dipped_below_close_seen"] and close > gap_close
                and st["low_of_dip"] is not None and st["low_of_dip"] > 0):
            fires.append({"rung": RUNG_EP_CLOSE, "entry": close,
                          "stop": st["low_of_dip"], "fire_minute": b["m"]})
            st["fired_ep_close_reclaim"] = True
        if (not st["fired_ep_high_break"] and not st["undercut_seen"]
                and not st["dipped_below_close_seen"] and hi >= gap_high):
            if prior_session_low is not None and prior_session_low > 0:
                fires.append({"rung": RUNG_EP_HIGH, "entry": gap_high,
                              "stop": prior_session_low, "fire_minute": b["m"]})
                st["fired_ep_high_break"] = True
            else:
                p3_needs_prior_low = True
        if hi >= gap_high:
            st["gap_high_exceeded"] = True
    return {"fires": fires, "state": st, "p3_needs_prior_low": p3_needs_prior_low}


def evaluate_session_daily(day_high: float, day_low: float, *, gap_low: float,
                           gap_close: float, gap_high: float,
                           prior_session_low: Optional[float], state: dict) -> dict:
    """Daily-grade path for a session `session_needs_minutes` said needs no minute check.
    Pure. Only the UNAMBIGUOUS ep_high_break can fire here (the whole bar stayed at or
    above the EP-day close — no pullback today, none before); its buy is the LEVEL
    (gap_high, a stop-buy first touch), so a daily bar proves it without minute bars.
    Then the raw state facts fold from the day's low/high.

    Returns {"fires": [...], "state": ..., "p3_needs_prior_low": bool}."""
    st = dict(state)
    fires: list[dict] = []
    p3_needs_prior_low = False
    clean_before = not st["undercut_seen"] and not st["dipped_below_close_seen"]
    if (not st["fired_ep_high_break"] and clean_before and day_high >= gap_high
            and day_low >= gap_close):
        if prior_session_low is not None and prior_session_low > 0:
            fires.append({"rung": RUNG_EP_HIGH, "entry": gap_high,
                          "stop": prior_session_low, "fire_minute": None})
            st["fired_ep_high_break"] = True
        else:
            p3_needs_prior_low = True
    # raw fact fold (order irrelevant here — no minute-grade fire reads it)
    if day_low < gap_low and not st["undercut_seen"]:
        st["undercut_seen"] = True
        st["low_since_undercut"] = day_low
    if st["undercut_seen"]:
        st["low_since_undercut"] = _min(st["low_since_undercut"], day_low)
    if day_low < gap_close and not st["dipped_below_close_seen"]:
        st["dipped_below_close_seen"] = True
        st["low_of_dip"] = day_low
    if st["dipped_below_close_seen"]:
        st["low_of_dip"] = _min(st["low_of_dip"], day_low)
    if day_high >= gap_high:
        st["gap_high_exceeded"] = True
    return {"fires": fires, "state": st, "p3_needs_prior_low": p3_needs_prior_low}


def stop_width_pct(entry: float, stop: float) -> Optional[float]:
    """Stop width as a percent of entry — the FIRST-CLASS column (it explained the whole
    U&R-vs-breakout gap). None only when entry is non-positive (a data bug, audited by
    the caller); a degenerate ep_high_break geometry (stop above entry) yields a
    NEGATIVE width — recorded, never dropped (dropping it would survivorship-filter the
    fire population on geometry)."""
    if not entry or entry <= 0 or stop is None:
        return None
    return (entry - stop) / entry * 100.0


def compute_screen_member(*, gap_pct, prev_close, ep_dollar_volume, extension_pct,
                          catalyst_grade) -> Optional[bool]:
    """Ex-ante SCREEN membership (SCREEN_VERSION) from EP-day facts. Any missing
    component → None (unknown), never guessed — raw components are stored per row so any
    variant can be re-cut later."""
    if (gap_pct is None or prev_close is None or ep_dollar_volume is None
            or extension_pct is None or catalyst_grade is None):
        return None
    return (float(gap_pct) >= 8.0 and float(prev_close) >= 5.0
            and float(ep_dollar_volume) >= 50_000_000.0
            and float(extension_pct) <= 50.0
            and str(catalyst_grade) in _SCREEN_STRONG_GRADES)


def compute_adr20(daily_bars: list[dict]) -> tuple[Optional[float], int]:
    """(mean daily range % over the last <=_ADR_WINDOW bars, n actually used). Bars are
    ascending dicts with high_price/low_price/close; incomplete bars are skipped. A
    measured input recorded at fire time (like rmv telemetry), not a rule output."""
    vals = []
    for b in daily_bars[-_ADR_WINDOW:]:
        h, l, c = _f(b.get("high_price")), _f(b.get("low_price")), _f(b.get("close"))
        if h is None or l is None or not c:
            continue
        vals.append((h - l) / c * 100.0)
    if not vals:
        return None, 0
    return sum(vals) / len(vals), len(vals)


# ── Pure settlement core (fixture-testable, no IO) ─────────────────────────────────────


def sma_trail_line(closes: list[float]) -> Optional[float]:
    """The M-trail exit line: MAX(SMA10, SMA20) with the live exit_logic.py 'sma' mode
    semantics VERBATIM — the SMA includes the session's own close (running_closes), <20
    closes falls back to SMA10 alone, <10 closes -> None (no line yet, no trail exit —
    the live None-guard). Mirrored, not imported: exit_logic walks a live position
    ladder; this settles a shadow row."""
    sma10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else None
    sma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
    if sma20 is not None:
        return sma10 if sma10 > sma20 else sma20
    return sma10


def day0_needs_minutes(fire_minute: Optional[int], fire_day_low: Optional[float],
                       stop: float) -> bool:
    """True when the fire day's daily bar cannot ORDER the post-fire stop test: a
    minute-grade fire whose day low touched the stop. For a reclaim the pre-fire
    undercut low often IS the stop, so the daily low proves nothing about what happened
    AFTER the fire — only the post-fire 5-min bars can (missing -> ABSTAIN). A
    daily-grade fire (fire_minute None) never needs minutes: its spanning day reads
    stop-first (pess), the documented house bound."""
    return (fire_minute is not None and fire_day_low is not None
            and fire_day_low <= stop)


def compute_settlement(*, entry: float, stop: float, fire_minute: Optional[int],
                       fire_day_bar: dict, post_fire_bars5: Optional[list],
                       sessions: list[date], bars_by_day: dict,
                       closes_before_fire: list[float]) -> dict:
    """Settle one trigger's TWO arms from its bars, or ABSTAIN. Pure.

    Returns one of:
      {"status": "settled", <the settlement columns>}   — everything is DEFINITIVE
      {"status": "abstain", "reason": ...}              — retry next run, row stays open
      {"status": "unscoreable", "reason": ...}          — can NEVER be scored (geometry)

    Inputs: `sessions` = expected trading sessions strictly after the fire date,
    ascending; `bars_by_day` day->daily bar (holes = missing); `post_fire_bars5` =
    day-0 5-min bars with m > fire_minute, or None when the fetch failed/was missing
    (an EMPTY list means fetched-fine-but-fire-was-last-bar, which is not missing);
    `closes_before_fire` = stored closes strictly before the fire date, ascending (the
    SMA seed).

    The walk (first touch decides, stop live across the hold — _bt_replay conventions):
      per session, pess stop-first: the low folds and tests the stop BEFORE the close
      can trail-exit or the high can credit 4R. A stop settles BOTH arms at -1.0R (exit
      at the stop level — the house convention; mae_r keeps the raw low so a
      gap-through stays visible). Else a close below sma_trail_line exits M-trail at
      that close; session SETTLE_HOLD_SESSIONS time-exits whatever is still open at its
      close. The first expected session with no bar ABSTAINS the whole row — never leap
      a gap. Settlement completes when M-none resolves (stop or time exit) — the
      longest hold, so every other column is computable from the same bars."""
    risk = (entry - stop) if (entry is not None and stop is not None) else None
    if not entry or entry <= 0 or risk is None or risk <= 0:
        return {"status": "unscoreable", "reason": "degenerate_geometry"}
    f_hi, f_lo, f_c = (_f(fire_day_bar.get("h")), _f(fire_day_bar.get("l")),
                       _f(fire_day_bar.get("c")))
    if f_hi is None or f_lo is None or f_c is None:
        return {"status": "abstain", "reason": "missing_fire_day_bar"}

    tail_target = entry + SETTLE_TAIL_R * risk
    none_open = trail_open = True
    none_outcome = none_r = none_exit = None
    trail_outcome = trail_r = trail_exit_s = None
    mfe = mae = None
    reached4 = False
    marks: dict[int, float] = {}

    def _stop_both(sess_idx: int) -> None:
        nonlocal none_open, trail_open, none_outcome, none_r, none_exit
        nonlocal trail_outcome, trail_r, trail_exit_s
        none_open = False
        none_outcome, none_r, none_exit = "stop", -1.0, sess_idx
        if trail_open:
            trail_open = False
            trail_outcome, trail_r, trail_exit_s = "stop", -1.0, sess_idx

    # ── day 0: the fire day itself, from the fire forward ──
    if day0_needs_minutes(fire_minute, f_lo, stop):
        if post_fire_bars5 is None:
            return {"status": "abstain", "reason": "missing_day0_minutes"}
        for b in post_fire_bars5:
            lo, hi = b["l"], b["h"]
            mfe = hi if mfe is None else max(mfe, hi)
            mae = lo if mae is None else min(mae, lo)
            if lo <= stop:              # pess stop-first: no 4R credit from this bar
                _stop_both(0)
                break
            if hi >= tail_target:
                reached4 = True
    else:
        # daily grade: fold the whole-day excursion (ceiling/floor telemetry — pre-fire
        # range is indistinguishable at this grade and mfe/mae are never the result)
        mfe, mae = f_hi, f_lo
        if fire_minute is None and f_lo <= stop:
            _stop_both(0)               # daily-grade fire, spanning day: pess stop-first
        elif fire_minute is None and f_hi >= tail_target:
            # only a LEVEL entry may credit its own day-0 high: price passed the entry
            # level on the way there. A minute fire's day-0 daily high is ambiguous
            # (it may predate the fire) and is never credited.
            reached4 = True
    closes = [c for c in closes_before_fire if c is not None] + [f_c]
    if trail_open:
        line = sma_trail_line(closes)
        if line is not None and f_c < line:
            trail_open = False
            trail_outcome, trail_exit_s = "trail_exit", 0
            trail_r = (f_c - entry) / risk

    # ── sessions 1..SETTLE_HOLD_SESSIONS after the fire ──
    for i, d in enumerate(sessions, start=1):
        if not none_open or i > SETTLE_HOLD_SESSIONS:
            break
        b = bars_by_day.get(d) or {}
        hi, lo, c = _f(b.get("high_price")), _f(b.get("low_price")), _f(b.get("close"))
        if hi is None or lo is None or c is None:
            # THE ABSTAIN RULE: never leap a gap — a stop could hide inside it
            return {"status": "abstain", "reason": f"missing_session:{d.isoformat()}"}
        closes.append(c)
        mfe = max(mfe, hi) if mfe is not None else hi
        mae = min(mae, lo) if mae is not None else lo
        if lo <= stop:                  # pess stop-first: no 4R credit this session
            _stop_both(i)
            marks[i] = c
            break
        if hi >= tail_target:
            reached4 = True
        if trail_open:
            line = sma_trail_line(closes)
            if line is not None and c < line:
                trail_open = False
                trail_outcome, trail_exit_s = "trail_exit", i
                trail_r = (c - entry) / risk
        if i == SETTLE_HOLD_SESSIONS:   # time exit at this session's close
            none_open = False
            none_outcome, none_exit = "time_exit", i
            none_r = (c - entry) / risk
            if trail_open:
                trail_open = False
                trail_outcome, trail_exit_s = "time_exit", i
                trail_r = (c - entry) / risk
        marks[i] = c

    if none_open:
        return {"status": "abstain", "reason": "window_open"}

    def _ckpt(exit_s: Optional[int], exit_r: Optional[float], n: int) -> Optional[float]:
        """Arm-R at checkpoint session n: realized once exited, else mark-to-market at
        that session's close. Every needed mark exists by construction — the walk
        reached the M-none exit, the latest of the two."""
        if exit_s is not None and exit_s <= n:
            return round(exit_r, 4)
        m = marks.get(n)
        return round((m - entry) / risk, 4) if m is not None else None

    return {
        "status": "settled",
        "outcome": none_outcome, "realized_r": round(none_r, 4),
        "outcome_trail": trail_outcome, "realized_r_trail": round(trail_r, 4),
        "r_none_s1": _ckpt(none_exit, none_r, 1),
        "r_none_s5": _ckpt(none_exit, none_r, 5),
        "r_none_s10": _ckpt(none_exit, none_r, 10),
        "r_none_s20": _ckpt(none_exit, none_r, 20),
        "r_trail_s1": _ckpt(trail_exit_s, trail_r, 1),
        "r_trail_s5": _ckpt(trail_exit_s, trail_r, 5),
        "r_trail_s10": _ckpt(trail_exit_s, trail_r, 10),
        "r_trail_s20": _ckpt(trail_exit_s, trail_r, 20),
        "mfe_r": round((mfe - entry) / risk, 4) if mfe is not None else None,
        "mae_r": round((mae - entry) / risk, 4) if mae is not None else None,
        "reached_4r": reached4,
    }


def _trading_days(start: date, end: date) -> list[date]:
    from agents.market_intelligence.trading_calendar import get_market_status
    out = []
    d = start
    while d <= end:
        if get_market_status(d).is_trading_day:
            out.append(d)
        d += timedelta(days=1)
    return out


# ── Orchestration (DB + Polygon reads; writes only the two lane tables + audit) ────────


async def _fetch_minute_5(ticker: str, session_day: date) -> list[dict]:
    """Polygon 1-min → completed RTH 5-min bars for one session. Empty list = missing
    (the caller ABSTAINS — never a daily-bar fallback for a minute check)."""
    from agents.market_intelligence.collector import get_minute_bars
    iso = session_day.isoformat()
    raw = await get_minute_bars(ticker, iso, iso)
    return to_rth_5min(raw, session_day)


def _member_context(seed_row: dict) -> dict:
    """The EP-day context stamped on every row, carried from the walk-seed row."""
    return {
        "ep_score": _f(seed_row.get("ep_score")),
        "catalyst_grade": seed_row.get("catalyst_grade"),
        "in_active_theme": seed_row.get("in_active_theme"),
        "gap_pct": _f(seed_row.get("gap_pct")),
        "prev_close": _f(seed_row.get("prev_close")),
        "ep_dollar_volume": _f(seed_row.get("ep_dollar_volume")),
        "extension_pct": _f(seed_row.get("extension_pct")),
        "screen_member": seed_row.get("screen_member"),
        "screen_version": seed_row.get("screen_version"),
        "gap_day_low": _f(seed_row.get("gap_day_low")),
        "gap_day_close": _f(seed_row.get("gap_day_close")),
        "gap_day_high": _f(seed_row.get("gap_day_high")),
        "gap_day_volume": seed_row.get("gap_day_volume"),
    }


async def enroll_new_members(today: date) -> int:
    """Enroll every EP-scan name from the last ENROLL_LOOKBACK_DAYS not yet in the lane —
    one session_idx=0 row per (ticker, ep_date) with pivots from the EP day's daily bar
    and the ex-ante screen stamp. Record everything: no admission gate beyond having
    been seen by the scan (the operator's population ruling)."""
    since = today - timedelta(days=ENROLL_LOOKBACK_DAYS)
    candidates = await get_delayed_entry_seed_candidates(since, today)
    enrolled = 0
    for c in candidates:
        ticker, ep_date = c["ticker"], c["scan_date"]
        try:
            o, h, l, close, bar_source = await get_delayed_entry_daily_bar(ticker, ep_date)
            volume = None
            if close is not None:
                window = await get_delayed_entry_daily_window(ticker, ep_date, ep_date)
                if window:
                    volume = window[0].get("volume")
            ep_dollar_volume = (float(volume) * close) if (volume and close) else None
            grade = c.get("catalyst_quality")
            screen = compute_screen_member(
                gap_pct=c.get("gap_pct"), prev_close=c.get("prev_close"),
                ep_dollar_volume=ep_dollar_volume, extension_pct=c.get("extension_pct"),
                catalyst_grade=grade)
            row = {
                "ticker": ticker, "ep_date": ep_date, "session_date": ep_date,
                "session_idx": 0, "pattern_version": PATTERN_VERSION,
                "gap_day_low": l, "gap_day_close": close, "gap_day_high": h,
                "gap_day_volume": volume,
                "day_open": o, "day_high": h, "day_low": l, "day_close": close,
                "day_volume": volume,
                "bar_source": bar_source if close is not None else "missing",
                "undercut_seen": False, "low_since_undercut": None,
                "dipped_below_close_seen": False, "low_of_dip": None,
                "gap_high_exceeded": False,
                "fired_ep_low_reclaim": False, "fired_ep_close_reclaim": False,
                "fired_ep_high_break": False,
                "eval_status": "complete" if close is not None else "unscoreable",
                "unscoreable_reason": None if close is not None else "missing_daily_bar",
                "ep_score": _f(c.get("ep_score")), "catalyst_grade": grade,
                "in_active_theme": c.get("in_active_theme"),
                "gap_pct": _f(c.get("gap_pct")), "prev_close": _f(c.get("prev_close")),
                "ep_dollar_volume": ep_dollar_volume,
                "extension_pct": _f(c.get("extension_pct")),
                "screen_member": screen, "screen_version": SCREEN_VERSION,
            }
            await upsert_delayed_entry_watch(row)
            enrolled += 1
        except Exception as e:
            logger.error(f"delayed_entry_shadow: enroll {ticker} {ep_date} failed: {e}")
            await log_audit_event(
                "delayed_entry_shadow_error",
                f"enroll {ticker} {ep_date}: {type(e).__name__}: {e}")
    return enrolled


async def _walk_one_member(member: dict, today: date, out: dict) -> None:
    """Advance one lane member from its last fully-scored session through today —
    re-walking from the FIRST unscoreable session when one exists (the retry half of
    the abstain rule; the UPSERT makes re-walked rows idempotent and the trigger
    insert's open-dedup makes re-fires no-ops)."""
    ticker, ep_date = member["ticker"], member["ep_date"]

    # ── choose the walk start + the state seed row ──
    seed_row = member
    walk_from = member["session_date"]          # walk starts AFTER this row's session
    first_unsc = member.get("first_unscoreable")
    if first_unsc is not None and first_unsc <= walk_from:
        prior = [d for d in _trading_days(first_unsc - timedelta(days=10), first_unsc)
                 if d < first_unsc]
        seed = None
        if prior:
            seed = await get_delayed_entry_watch_row(ticker, ep_date, prior[-1])
        if seed is not None:
            seed_row = seed
            walk_from = seed["session_date"]
        # else: the unscoreable row IS the enrollment row — re-walk from enrollment
        elif first_unsc == ep_date:
            seed_row = member  # pivots may be NULL; refreshed below
            walk_from = ep_date - timedelta(days=1)

    ctx = _member_context(seed_row)
    state = state_from_row(seed_row)
    session_idx = int(seed_row.get("session_idx") or 0)
    if walk_from < ep_date:
        session_idx = -1  # enrollment re-walk: the ep_date row itself is idx 0

    # ── pivots: refetch if the enrollment bar was missing (bounded by lane life) ──
    if ctx["gap_day_close"] is None:
        o, h, l, close, _src = await get_delayed_entry_daily_bar(ticker, ep_date)
        if close is None:
            out["unscoreable"] += 1
            return  # still no EP-day bar — nothing can be evaluated yet
        window = await get_delayed_entry_daily_window(ticker, ep_date, ep_date)
        volume = window[0].get("volume") if window else None
        ctx.update({"gap_day_low": l, "gap_day_close": close, "gap_day_high": h,
                    "gap_day_volume": volume,
                    "ep_dollar_volume": (float(volume) * close) if (volume and close) else None})
        # the screen stamp may have been NULL only because these components were —
        # recompute now that they exist (still ex-ante EP-day facts, no outcome touched)
        ctx["screen_member"] = compute_screen_member(
            gap_pct=ctx["gap_pct"], prev_close=ctx["prev_close"],
            ep_dollar_volume=ctx["ep_dollar_volume"],
            extension_pct=ctx["extension_pct"], catalyst_grade=ctx["catalyst_grade"])

    gap_low, gap_close, gap_high = ctx["gap_day_low"], ctx["gap_day_close"], ctx["gap_day_high"]
    if gap_low is None or gap_close is None or gap_high is None:
        out["unscoreable"] += 1
        return

    sessions = [d for d in _trading_days(walk_from, today) if d > walk_from]
    if walk_from < ep_date:
        sessions = [d for d in _trading_days(ep_date, today)]
    if not sessions:
        return

    # ONE ranged daily read per member: session bars + prior-session lows + ADR window
    window_start = sessions[0] - timedelta(days=_ADR_FETCH_CAL_DAYS)
    daily = await get_delayed_entry_daily_window(ticker, window_start, today)
    bars_by_day = {b["trade_date"]: b for b in daily}
    ordered_days = [b["trade_date"] for b in daily]

    for session_date in sessions:
        if session_idx >= LANE_SESSIONS:
            break
        if session_date == ep_date:
            session_idx = 0
            # enrollment re-walk target: refresh the idx-0 row with the now-present bar
            b = bars_by_day.get(session_date)
            row = _base_watch_row(ticker, ep_date, session_date, 0, ctx, new_state())
            if b is not None and b.get("close") is not None:
                row.update({"day_open": _f(b.get("open_price")), "day_high": _f(b.get("high_price")),
                            "day_low": _f(b.get("low_price")), "day_close": _f(b.get("close")),
                            "day_volume": b.get("volume"), "bar_source": "daily",
                            "eval_status": "complete", "unscoreable_reason": None})
            else:
                row.update({"bar_source": "missing", "eval_status": "unscoreable",
                            "unscoreable_reason": "missing_daily_bar"})
            await upsert_delayed_entry_watch(row)
            out["watch_rows"] += 1
            continue
        session_idx += 1

        b = bars_by_day.get(session_date)
        if b is None:
            o, h, l, c, src = await get_delayed_entry_daily_bar(ticker, session_date)
            if c is not None:
                b = {"trade_date": session_date, "open_price": o, "high_price": h,
                     "low_price": l, "close": c, "volume": None, "_src": src}
        day_open = _f(b.get("open_price")) if b else None
        day_high = _f(b.get("high_price")) if b else None
        day_low = _f(b.get("low_price")) if b else None
        day_close = _f(b.get("close")) if b else None
        day_volume = b.get("volume") if b else None
        bar_source = (b.get("_src") or "daily") if b else "missing"

        row = _base_watch_row(ticker, ep_date, session_date, session_idx, ctx, state)
        row.update({"day_open": day_open, "day_high": day_high, "day_low": day_low,
                    "day_close": day_close, "day_volume": day_volume,
                    "bar_source": bar_source})

        if day_close is None or day_high is None or day_low is None:
            # no daily bar → we know nothing about this session; state carries unchanged
            row.update({"eval_status": "unscoreable",
                        "unscoreable_reason": "missing_daily_bar"})
            await upsert_delayed_entry_watch(row)
            out["watch_rows"] += 1
            out["unscoreable"] += 1
            continue

        prior_low = _prior_session_low(ordered_days, bars_by_day, session_date)
        needs_minutes = session_needs_minutes(
            day_high, day_low, gap_low=gap_low, gap_close=gap_close,
            gap_high=gap_high, state=state)

        if needs_minutes:
            bars5 = await _fetch_minute_5(ticker, session_date)
            if not bars5:
                # ABSTAIN: fold the raw daily facts (facts are facts), fire nothing,
                # retry on later runs while the name is in the lane. No fire can slip
                # through this call: needs_minutes=True precludes the daily path's
                # unambiguous-P3 condition (clean state + whole bar at/above the EP
                # close), and prior_session_low=None blocks P3 regardless.
                res = evaluate_session_daily(
                    day_high, day_low, gap_low=gap_low, gap_close=gap_close,
                    gap_high=gap_high, prior_session_low=None, state=state)
                state = res["state"]
                row.update(_state_cols(state))
                row.update({"eval_status": "unscoreable",
                            "unscoreable_reason": "missing_minute_bars"})
                await upsert_delayed_entry_watch(row)
                out["watch_rows"] += 1
                out["unscoreable"] += 1
                continue
            res = evaluate_session_minute(
                bars5, gap_low=gap_low, gap_close=gap_close, gap_high=gap_high,
                prior_session_low=prior_low, state=state)
        else:
            res = evaluate_session_daily(
                day_high, day_low, gap_low=gap_low, gap_close=gap_close,
                gap_high=gap_high, prior_session_low=prior_low, state=state)

        state = res["state"]
        row.update(_state_cols(state))
        if res.get("p3_needs_prior_low"):
            row.update({"eval_status": "unscoreable",
                        "unscoreable_reason": "missing_prior_low"})
            out["unscoreable"] += 1

        for fire in res["fires"]:
            wrote = await _record_trigger(
                ticker=ticker, ep_date=ep_date, session_date=session_date,
                session_idx=session_idx, fire=fire, ctx=ctx, state=state,
                day_bar=(day_open, day_high, day_low, day_close, day_volume),
                prior_low=prior_low, ordered_days=ordered_days, bars_by_day=bars_by_day,
                resolution="minute_5" if fire.get("fire_minute") is not None else "daily")
            if wrote:
                out["triggers"] += 1

        await upsert_delayed_entry_watch(row)
        out["watch_rows"] += 1


def _base_watch_row(ticker, ep_date, session_date, session_idx, ctx, state) -> dict:
    row = {
        "ticker": ticker, "ep_date": ep_date, "session_date": session_date,
        "session_idx": session_idx, "pattern_version": PATTERN_VERSION,
        "gap_day_low": ctx["gap_day_low"], "gap_day_close": ctx["gap_day_close"],
        "gap_day_high": ctx["gap_day_high"], "gap_day_volume": ctx["gap_day_volume"],
        "day_open": None, "day_high": None, "day_low": None, "day_close": None,
        "day_volume": None, "bar_source": "missing",
        "eval_status": "complete", "unscoreable_reason": None,
        "ep_score": ctx["ep_score"], "catalyst_grade": ctx["catalyst_grade"],
        "in_active_theme": ctx["in_active_theme"], "gap_pct": ctx["gap_pct"],
        "prev_close": ctx["prev_close"], "ep_dollar_volume": ctx["ep_dollar_volume"],
        "extension_pct": ctx["extension_pct"], "screen_member": ctx["screen_member"],
        "screen_version": ctx["screen_version"] or SCREEN_VERSION,
    }
    row.update(_state_cols(state))
    return row


def _state_cols(state: dict) -> dict:
    return {k: state[k] for k in _STATE_KEYS}


def _prior_session_low(ordered_days, bars_by_day, session_date) -> Optional[float]:
    prior = [d for d in ordered_days if d < session_date]
    if not prior:
        return None
    return _f(bars_by_day[prior[-1]].get("low_price"))


async def _record_trigger(*, ticker, ep_date, session_date, session_idx, fire, ctx, state,
                          day_bar, prior_low, ordered_days, bars_by_day, resolution) -> bool:
    """Assemble + insert one trigger row (idempotent open-dedup). The ex-ante decision
    vector is captured HERE, at the fire — never reconstructed later."""
    entry, stop = float(fire["entry"]), float(fire["stop"])
    width = stop_width_pct(entry, stop)
    if width is None:
        await log_audit_event(
            "delayed_entry_shadow_error",
            f"{ticker} {ep_date} {fire['rung']}: non-positive entry {entry} — fire dropped")
        return False
    pre_fire_days = [d for d in ordered_days if d < session_date]
    adr, adr_n = compute_adr20([bars_by_day[d] for d in pre_fire_days])
    missing_before = await count_delayed_entry_unscoreable(ticker, ep_date, session_date)
    day_open, day_high, day_low, day_close, day_volume = day_bar
    return await insert_delayed_entry_trigger({
        "ticker": ticker, "ep_date": ep_date, "rung": fire["rung"],
        "pattern_version": PATTERN_VERSION, "fire_date": session_date,
        "fire_minute_et": fire.get("fire_minute"), "resolution": resolution,
        "sessions_since_ep": session_idx,
        "entry_price": entry, "stop_price": stop, "stop_width_pct": width,
        "gap_day_low": ctx["gap_day_low"], "gap_day_close": ctx["gap_day_close"],
        "gap_day_high": ctx["gap_day_high"], "gap_day_volume": ctx["gap_day_volume"],
        "prior_session_low": prior_low,
        "day_open": day_open, "day_high": day_high, "day_low": day_low,
        "day_close": day_close, "day_volume": day_volume,
        "adr20_pct": adr, "adr20_n": adr_n,
        "gap_high_exceeded_before": bool(state.get("gap_high_exceeded")),
        "in_active_theme": ctx["in_active_theme"], "ep_score": ctx["ep_score"],
        "catalyst_grade": ctx["catalyst_grade"], "screen_member": ctx["screen_member"],
        "screen_version": ctx["screen_version"] or SCREEN_VERSION,
        "prior_missing_sessions": missing_before,
    })


async def _close_unscoreable(trig: dict, out: dict, reason: str) -> None:
    """Definitively close one trigger that can NEVER settle honestly (degenerate
    geometry, or bars still missing past the orphan horizon). Every R column stays
    NULL — recorded, never interpolated; the accrual gate (realized_r IS NOT NULL)
    never counts it. Loud in the audit log, silent everywhere else."""
    flipped = await settle_delayed_entry_trigger(
        trig["id"], {"outcome": "unscoreable", "outcome_trail": "unscoreable",
                     "settle_version": SETTLE_VERSION})
    if flipped:
        out["settle_unscoreable"] += 1
        await log_audit_event(
            "delayed_entry_shadow_unscoreable",
            f"{trig['ticker']} {trig['ep_date']} {trig['rung']} fired {trig['fire_date']}: "
            f"closed unscoreable — {reason}")


async def _settle_one_trigger(trig: dict, today: date, out: dict) -> None:
    """Try to settle ONE open trigger. Definitive -> one write (double-settle-guarded);
    not yet definitive -> abstain, row stays open, retried next run; past the orphan
    horizon and still blocked -> closed unscoreable."""
    ticker, fire_date = trig["ticker"], trig["fire_date"]
    fire_minute = trig.get("fire_minute_et")
    entry, stop = _f(trig.get("entry_price")), _f(trig.get("stop_price"))

    if entry is None or stop is None or entry <= 0 or (entry - stop) <= 0:
        await _close_unscoreable(
            trig, out, "degenerate geometry (stop >= entry) — R is undefined")
        return

    sessions = _trading_days(fire_date + timedelta(days=1), today)
    daily = await get_delayed_entry_daily_window(
        ticker, fire_date - timedelta(days=_SETTLE_SMA_FETCH_CAL_DAYS), today)
    bars_by_day = {b["trade_date"]: b for b in daily}
    closes_before = [_f(b.get("close")) for b in daily
                     if b["trade_date"] < fire_date and b.get("close") is not None]
    # the fire day's bar: the trigger row's own record first (captured at fire time),
    # the stored daily window as the per-field fallback
    fb = bars_by_day.get(fire_date) or {}
    fire_day_bar = {
        "h": _f(trig.get("day_high")) if trig.get("day_high") is not None else _f(fb.get("high_price")),
        "l": _f(trig.get("day_low")) if trig.get("day_low") is not None else _f(fb.get("low_price")),
        "c": _f(trig.get("day_close")) if trig.get("day_close") is not None else _f(fb.get("close")),
    }

    post5 = None
    if day0_needs_minutes(fire_minute, fire_day_bar["l"], stop):
        bars5 = await _fetch_minute_5(ticker, fire_date)
        if bars5:
            post5 = [b for b in bars5 if b["m"] > fire_minute]
        # empty fetch -> post5 stays None -> the pure core ABSTAINS (retry next run)

    res = {"status": "abstain", "reason": "window_open"}
    for _ in range(6):  # bounded single-day gap fills: fetch the one missing bar, retry
        res = compute_settlement(
            entry=entry, stop=stop, fire_minute=fire_minute, fire_day_bar=fire_day_bar,
            post_fire_bars5=post5, sessions=sessions, bars_by_day=bars_by_day,
            closes_before_fire=closes_before)
        reason = res.get("reason", "")
        if res["status"] == "abstain" and reason.startswith("missing_session:"):
            d = date.fromisoformat(reason.split(":", 1)[1])
            o, h, l, c, _src = await get_delayed_entry_daily_bar(ticker, d)
            if c is None:
                break  # genuinely missing (halt/delist/hole) — the abstain stands
            bars_by_day[d] = {"trade_date": d, "open_price": o, "high_price": h,
                              "low_price": l, "close": c}
            continue
        break

    if res["status"] == "settled":
        fields = {k: v for k, v in res.items() if k != "status"}
        fields["settle_version"] = SETTLE_VERSION
        if await settle_delayed_entry_trigger(trig["id"], fields):
            out["settle_settled"] += 1
        # False = a concurrent run already settled it — the no-op is the point
        return
    if res["status"] == "unscoreable":
        await _close_unscoreable(trig, out, res.get("reason", "unscoreable"))
        return
    # abstain: honest retry — unless the row is past the orphan horizon, where the
    # 20-session window has long elapsed and the bars are never coming
    if fire_date <= today - timedelta(days=SETTLE_ORPHAN_CAL_DAYS):
        await _close_unscoreable(
            trig, out,
            f"still blocked ({res.get('reason')}) {SETTLE_ORPHAN_CAL_DAYS}+ calendar days "
            f"after the fire — bars are not coming (halt/delist/hole)")
        return
    out["settle_abstained"] += 1


async def settle_open_triggers(today: date, out: dict) -> None:
    """The settlement pass, driven inline by the same evening run (one job -> one
    digest). Considers EVERY open trigger every run — settle-as-soon-as-definitive
    means a day-3 stop settles on day 3 — and counts considered / settled / abstained /
    unscoreable separately so a silent zero is distinguishable from 'nothing ripe
    yet'. Per-trigger failures degrade to mi_audit_log and the pass continues."""
    try:
        open_rows = await get_delayed_entry_open_triggers()
    except Exception as e:
        out["errors"] += 1
        logger.error(f"delayed_entry_shadow: open-trigger read failed: {e}", exc_info=True)
        await log_audit_event("delayed_entry_shadow_error",
                              f"settlement read: {type(e).__name__}: {e}")
        return
    for trig in open_rows:
        out["settle_considered"] += 1
        try:
            await _settle_one_trigger(trig, today, out)
        except Exception as e:
            out["errors"] += 1
            logger.error(
                f"delayed_entry_shadow: settle {trig.get('ticker')} "
                f"{trig.get('fire_date')} failed: {e}")
            try:
                await log_audit_event(
                    "delayed_entry_shadow_error",
                    f"settle {trig.get('ticker')} {trig.get('rung')} "
                    f"{trig.get('fire_date')}: {type(e).__name__}: {e}")
            except Exception:  # loud-ok: log_audit_event self-catches; logger fired above
                pass


async def run_delayed_entry_shadow(today: Optional[date] = None) -> dict[str, int]:
    """The evening job: enroll today's EP-scan names, advance every lane member through
    today, then SETTLE every open trigger that has become definitive (inline — one job,
    one digest). NEVER raises into the caller — per-member and per-trigger failures
    degrade to `mi_audit_log` + logs and the run continues (pinned by test). The
    summary audit event fires UNCONDITIONALLY so '0 of N' is distinguishable from
    '0 of 0'. SILENT: no Telegram anywhere on this path."""
    if today is None:
        from agents.market_intelligence.collector import et_today
        today = et_today()

    out = {"enrolled": 0, "members": 0, "watch_rows": 0, "triggers": 0,
           "unscoreable": 0, "errors": 0,
           "settle_considered": 0, "settle_settled": 0, "settle_abstained": 0,
           "settle_unscoreable": 0}
    try:
        out["enrolled"] = await enroll_new_members(today)
    except Exception as e:
        out["errors"] += 1
        logger.error(f"delayed_entry_shadow: enrollment pass failed: {e}", exc_info=True)
        await log_audit_event("delayed_entry_shadow_error",
                              f"enrollment pass: {type(e).__name__}: {e}")

    try:
        members = await get_delayed_entry_open_lane(
            today - timedelta(days=_LANE_MAX_CAL_DAYS), LANE_SESSIONS)
    except Exception as e:
        members = []
        out["errors"] += 1
        logger.error(f"delayed_entry_shadow: lane read failed: {e}", exc_info=True)
        await log_audit_event("delayed_entry_shadow_error",
                              f"lane read: {type(e).__name__}: {e}")

    out["members"] = len(members)
    for m in members:
        try:
            await _walk_one_member(m, today, out)
        except Exception as e:
            out["errors"] += 1
            logger.error(
                f"delayed_entry_shadow: {m.get('ticker')} {m.get('ep_date')} failed: {e}")
            try:
                await log_audit_event(
                    "delayed_entry_shadow_error",
                    f"{m.get('ticker')} {m.get('ep_date')}: {type(e).__name__}: {e}")
            except Exception:  # loud-ok: log_audit_event self-catches; logger fired above
                pass

    # settlement rides the SAME run (one job -> one digest); it self-catches per trigger
    await settle_open_triggers(today, out)

    try:
        await log_audit_event(
            "delayed_entry_shadow_recorded",
            f"{out['watch_rows']} watch row(s), {out['triggers']} trigger(s) across "
            f"{out['members']} lane member(s) for {today} "
            f"({out['enrolled']} enrolled, {out['unscoreable']} unscoreable, "
            f"{out['errors']} error(s)); settlement: {out['settle_considered']} open "
            f"trigger(s) considered, {out['settle_settled']} settled, "
            f"{out['settle_abstained']} abstained (still open — retry), "
            f"{out['settle_unscoreable']} closed unscoreable")
    except Exception as _e:  # loud-ok: telemetry-of-telemetry; the rows are already durable
        logger.warning(f"delayed_entry_shadow audit emit failed (non-fatal): {_e}")
    return out
