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

THE FOUR PATTERNS (v2) — each states its buy and its stop, or it is not a setup:
  ep_low_reclaim    price drops below the EP day's LOW, then a 5-min bar closes back
                    above it. Buy = that close. Stop = the lowest low since the undercut.
  ep_close_reclaim  price never reaches the EP-day low, but dips under the EP day's
                    CLOSE and a 5-min bar closes back above it. Buy = that close.
                    Stop = the lowest low of the dip.
  ep_high_break     price never pulls back — it pushes above the EP day's HIGH.
                    Buy = that high (stop-buy at the level). Stop = the prior session's
                    low.
  ep_close_620_prox the proximity fallback (v2, 2026-08-30): the stock approaches the
                    EP-day close without needing to touch anything. Buy = the first
                    qualified 620 turn (MACD 6/20 on 5-min closes, EMA-9 signal; cross
                    with MACD < 0; basing range of the prior 8 buckets <= 0.4xADR$; the
                    MACD hook) whose cross bar closes within 0.5xADR$ of the EP-day
                    close — #562's frozen instrument, reused VERBATIM so results
                    transfer. Stop = low of day so far (the operator's TEAM stop basis).
                    ⚠ THE LABEL IS MANDATORY: the operator ruled 2026-08-29 that "near"
                    is a BEHAVIOUR (approach -> deceleration -> cessation ->
                    consolidation -> turn), and named this exact +-0.5xADR band "the
                    rigid instrument this ruling replaces". Behavioural detection is its
                    own modelling task (external review, 2026-08-30) — so the band ships,
                    but EVERY rung-4 row stamps near_definition =
                    NEAR_DEFINITION_PLACEHOLDER (schema-CHECK-enforced): a rung-4 null
                    result falsifies THE BAND ONLY, never the behavioural definition.
Every trigger row records buy, stop, and **stop width as % of entry as a first-class
column** — stop width explained the entire measured difference between patterns (same
move captured, 2.68% vs 8.75% risk) and must never be derive-it-later. Each row stamps
`pattern_version` — a reader must never infer the acting definition from a date.

RE-ENTRY RECORDING (v2, 2026-08-30 — record what each shape would have done; NO policy
decided, the review rules). Every attempt is its OWN trigger row, identified by
reentry_shape ('first' vs a re-entry shape) + prior_attempt_id + fire_date, so a
campaign (first entry, stop-out, re-entry, outcome) reconstructs from rows — TEAM is the
case: every first attempt stopped at 82-92, the re-entry at 149.49 on strength made
+5.56R, and the first-fire-only shadow would have quit after one stop. There is
deliberately NO attempt-number column (dropped, 2026-08-30 simplify review): the two
re-entry shapes are PARALLEL bounded replays of the same stop-out — both can fire on
one campaign — so any ordinal would misorder or double-count a campaign query. After a
FIRST attempt settles outcome='stop' (only a stop frees a name — a trail/time exit is a
harvest that ends the campaign), the nightly pass replays BOTH bounded shapes from the
session AFTER the stop-out, each writing at most one row of its shape:
  same_pattern    the rung's own pattern re-armed FRESH (for ep_high_break: a re-touch
                  of the EP-day high, buy at the level, stop = prior session's low —
                  the clean-never-pulled-back precondition is an attempt-1 partitioning
                  rule, structurally impossible after a stop and so not re-applied).
                  Campaign-study net: +4.2R once, +0.6R unlimited.
  new_high_break  a break above MAX(EP-day high, every session high through the
                  stop-out) — proof of strength before re-entering (the R3 shape,
                  +12.9R; the TEAM move). Buy at the level, stop = prior session's low.
Failed re-entries settle at -1R through the same machinery as any row — their cost IS
the whole risk of re-entering, and is never dropped. Bounded x1 per shape (the
abandon-after-2 rule measured as losing nothing); the (ticker, ep_date, rung,
reentry_shape) unique index makes the bound and the never-overwrite mechanical.
⚠ KNOWN LIMITATION — DAY-2+ ONLY (ruled 2026-08-30): same-day re-entry needs tick-level
state and would break the shadow/live-execution boundary, so it is OUT OF SCOPE — every
re-entry figure this lane produces understates same-day re-entry by construction.

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
    after blind sessions stamps `prior_missing_sessions > 0` — ONE definition on both
    write paths (2026-08-30 simplify review): blind (unscoreable) sessions inside THIS
    attempt's own watch window, strictly before its fire. The window opens at the EP
    day for a first attempt and at the session AFTER the stop-out for a re-entry row,
    so >0 always means THIS attempt's true first fire may be up to that many sessions
    earlier — sessions outside the row's own window are never counted.
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
    interpolate. Every path resolves a session's bar through ONE helper,
    `_resolve_session_bar` (ranged read, then the single-day fallback), so the same
    hole can never be backfilled on one path and silently dropped on another
    (2026-08-30 simplify review — the re-entry replays had diverged). Day 0 of a
    minute-grade fire whose daily low touched the stop (for a
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

#616 ADR-STOP VARIANTS (2026-09-02, operator-authorised 09-01 — RECORDING ONLY, beside
the incumbent and never instead of it). The 09-01 stop grid found ONE shape across all
four rungs: the working stop is VOLATILITY-PROPORTIONAL (every incumbent sits outside
the 0.75-1.25xADR band). So every trigger row also records what a stop at
entry − 0.75×ADR$ and entry − 1.00×ADR$ (EP-anchored ADR$, compute_ep_adr_dollar — the
grid's exact basis) would have produced, settled through the SAME compute_settlement
walk under both arms (*_075 / *_100 columns; settle_v3).
  - Fire time: the ADR basis + both counterfactual stops stamp EX ANTE on the trigger
    row. A missing ADR records NULL and is COUNTED — never substituted, never defaulted
    (ep_adr20_n stays NOT NULL on every post-#616 row; pre-#616 rows keep every variant
    column NULL forever — their stored adr20_pct is a pre-FIRE basis, a different
    quantity).
  - Settlement: each variant settles through its OWN guarded write (its outcome IS
    NULL). A wider stop resolves LATER than the incumbent by construction, so the
    incumbent settles exactly as before (same columns, same write, same timing) and
    settle_open_variant_triggers finishes the stragglers on later runs from stored
    daily bars. NO minute refetch, ever (the #616 no-per-fire-fetch rule): the day-0
    post-fire excursion (min low / max high) is cached once, the first time the fire
    day's 5-min bars are in scope, and a variant still pending at cache time provably
    never touched its stop on day 0 — so the cached pair reconstructs its day-0 walk
    exactly. A variant that needs day-0 minutes that were NEVER in scope (the fire
    day's low reached the variant stop but not the incumbent's, so the incumbent never
    fetched them) abstains until the orphan horizon closes it unscoreable, counted —
    the censored class is recorded, never silently leapt.
  - A variant failure of any kind degrades to NULL + a counted, audited error and can
    never block or alter the incumbent path. Nothing live reads any variant column.
"""
from __future__ import annotations

import logging
from bisect import insort
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from shared.dates import _ET

# The ONE mirrored copy of the live broker/exit_logic.py SMA trail formula, pinned
# byte-for-byte by test_exit_path_shadow.py::test_trail_matches_exit_logic_formula.
# Same-directory shadow import — this module still imports NOTHING from broker/.
from agents.market_intelligence.exit_path_shadow import _sma_trail

from agents.market_intelligence.db import (
    _f,
    count_delayed_entry_unscoreable,
    get_delayed_entry_daily_bar,
    get_delayed_entry_daily_window,
    get_delayed_entry_open_lane,
    get_delayed_entry_open_triggers,
    get_delayed_entry_reentry_candidates,
    get_delayed_entry_seed_candidates,
    get_delayed_entry_variant_pending,
    get_delayed_entry_watch_row,
    insert_delayed_entry_trigger,
    log_audit_event,
    record_delayed_entry_trigger_day0,
    settle_delayed_entry_trigger,
    settle_delayed_entry_trigger_variant,
    upsert_delayed_entry_watch,
)

logger = logging.getLogger(__name__)

PATTERN_VERSION = "v2"            # v2 (2026-08-30): + ep_close_620_prox rung + re-entry attempts
SCREEN_VERSION = "screen_v1"      # gap>=8, prev_close>=5, $vol>=50M, ext<=50, grade>=strong
SETTLE_VERSION = "settle_v3"      # settle_v3: + #616 ADR-stop variant counterfactuals
                                  # (each variant settles via its own guarded write);
                                  # settle_v2: + stop_hit_date recorded on stop outcomes
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

# ── #616 ADR-stop variants (2026-09-02): column suffix ↔ stop multiplier. The stop is
# entry − mult × EP-anchored ADR$ — the 09-01 stop grid's exact basis. RECORDING ONLY.
ADR_STOP_VARIANTS = (("075", 0.75), ("100", 1.00))

_RTH_OPEN_MIN = 9 * 60 + 30
_RTH_CLOSE_MIN = 16 * 60

# Grades counting as ">= strong" for the screen stamp (ep_rubric's catalyst points
# vocabulary: only game_changer/strong score above default).
_SCREEN_STRONG_GRADES = frozenset({"strong", "game_changer"})

RUNG_EP_LOW = "ep_low_reclaim"
RUNG_EP_CLOSE = "ep_close_reclaim"
RUNG_EP_HIGH = "ep_high_break"
RUNG_620_PROX = "ep_close_620_prox"

# ── rung-4 constants: #562's frozen 620-turn instrument, verbatim (327s2 reconstruction,
# nine anchor trades reproduced exactly). Do NOT redesign — the ruled decision.
NEAR_DEFINITION_PLACEHOLDER = "proximity_band_0p5adr_v1"  # the MANDATORY rung-4 label:
#   the PLACEHOLDER +-0.5xADR$ DISTANCE band, NOT the operator's 2026-08-29 behavioural
#   "near" ruling (unimplemented anywhere). Stamped on EVERY rung-4 row so a null result
#   falsifies the band, never the behavioural idea.
MACD_FAST, MACD_SLOW, MACD_SIG = 6, 20, 9   # MACD(6,20) on 5-min closes, EMA-9 signal
HOOK_SHORT, HOOK_LONG = 6, 12     # hook: macd 6-bucket min <= 12-bucket min (TEAM-pinned)
BASING_BARS = 8                   # basing window: the prior 8 five-min buckets (40 min)
BASING_BAND_ADR = 0.4             # basing range <= 0.4 x ADR$
PROX_BAND_ADR = 0.5               # cross-bar close within 0.5 x ADR$ of the EP-day close
MIN_CROSS_IDX = 12                # frozen warm-up guard: no cross before global bucket 12
WARMUP_SESSIONS_620 = 2           # prior sessions of 5-min bars prepended to seed the EMAs
#   (~156 bars: the EMA-20 seed influence is < 1e-6 — numerically the continuous series;
#   a missing warm-up day shortens the seed, and MIN_CROSS_IDX stays the binding guard —
#   #562's own day-one crosses had exactly that warm-up)

# ── re-entry shapes (piece 2 — recording only, both bounded x1 per rung)
SHAPE_FIRST = "first"
SHAPE_SAME = "same_pattern"
SHAPE_NEWHIGH = "new_high_break"
REENTRY_WATCH_SESSIONS = 20       # re-entry patterns watched 20 sessions from the stop-out
REENTRY_MAX_CAL_DAYS = 45         # candidates age out of the nightly pass past this

_STATE_KEYS = (
    "undercut_seen", "low_since_undercut",
    "dipped_below_close_seen", "low_of_dip", "gap_high_exceeded",
    "fired_ep_low_reclaim", "fired_ep_close_reclaim", "fired_ep_high_break",
    "fired_ep_close_620_prox",
)


def new_state() -> dict[str, Any]:
    """Clean per-member pattern state (as of the end of the EP day itself)."""
    return {
        "undercut_seen": False, "low_since_undercut": None,
        "dipped_below_close_seen": False, "low_of_dip": None,
        "gap_high_exceeded": False,
        "fired_ep_low_reclaim": False, "fired_ep_close_reclaim": False,
        "fired_ep_high_break": False, "fired_ep_close_620_prox": False,
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


# ── Pure rung-4 core: the 620 proximity fallback (#562 frozen instrument, verbatim) ────


def compute_ep_adr_dollar(daily_bars: list[dict], ep_date: date,
                          gap_close: Optional[float]) -> tuple[Optional[float], int]:
    """EP-day-anchored ADR$ = mean (high-low)/close over the <=20 sessions strictly
    BEFORE ep_date, x the EP-day close — fixed per campaign (#562: the band must not
    drift session to session). Recomputed from raw bars every run, never trusted from a
    stored value. (None, n) with no usable pre-EP bars — such names can never arm the
    620 rung, visible via the NULL ep_adr20_dollar on their watch rows."""
    pre = [b for b in daily_bars if b.get("trade_date") and b["trade_date"] < ep_date]
    pct, n = compute_adr20(pre)
    if pct is None or not gap_close:
        return None, n
    return pct / 100.0 * float(gap_close), n


def adr_variant_stop(entry: Optional[float], adr_dollar: Optional[float],
                     mult: float) -> Optional[float]:
    """entry − mult×ADR$ (#616). None when either input is missing or degenerate —
    the missing-ADR rule: NULL and counted, never substituted."""
    if not entry or entry <= 0 or adr_dollar is None or adr_dollar <= 0:
        return None
    return entry - mult * adr_dollar


def variant_stop_cols(entry: float, adr_dollar: Optional[float],
                      adr_n: Optional[int]) -> dict:
    """The #616 fire-time columns: the EP-anchored ADR basis + both counterfactual
    stops (+ widths — the lane's first-class rule applies to a counterfactual stop
    too). ep_adr20_n is ALWAYS an int on a post-#616 row: it is the marker separating
    'recorded, ADR unavailable' (n present, stops NULL) from a pre-#616 row
    (everything NULL). Pure."""
    cols: dict[str, Any] = {"ep_adr20_dollar": adr_dollar, "ep_adr20_n": int(adr_n or 0)}
    for sfx, mult in ADR_STOP_VARIANTS:
        s = adr_variant_stop(entry, adr_dollar, mult)
        cols[f"stop_price_{sfx}"] = s
        cols[f"stop_width_pct_{sfx}"] = stop_width_pct(entry, s) if s is not None else None
    return cols


_VARIANT_SETTLE_KEYS = ("outcome", "realized_r", "outcome_trail", "realized_r_trail",
                        "mfe_r", "mae_r", "reached_4r")


def variant_settle_fields(res: dict) -> dict:
    """Map one compute_settlement result onto the unsuffixed #616 variant write
    fields. Checkpoints and stop_session_idx are deliberately dropped — no re-entry
    replay and no checkpoint read hangs off a counterfactual. Pure."""
    return {k: res.get(k) for k in _VARIANT_SETTLE_KEYS}


def variant_unscoreable_fields() -> dict:
    """The #616 variant close-out for a variant that can NEVER settle honestly (no
    ADR at fire, degenerate geometry, or bars that never came within the orphan
    horizon). Every R column stays NULL — recorded, never interpolated. Pure."""
    return {"outcome": "unscoreable", "outcome_trail": "unscoreable"}


def day0_pseudo_bars(day0_resolved, post_low, post_high) -> Optional[list]:
    """Reconstruct a day-0 post-fire series from the cached excursion (#616 — the
    no-per-fire-fetch rule's stand-in for a minute refetch). None = never cached (a
    walk that needs day-0 minutes must ABSTAIN); [] = cached, the fire bar was the
    session's last; else ONE synthetic bar carrying (min low, max high). EXACT for any
    variant still PENDING when the cache was written: pending ⇒ no post-fire bar
    touched its stop ⇒ the per-bar pess ordering collapses to the pair. (A variant
    that reached the cache through the exception-recovery path may under-credit
    reached_4r on a day-0 stop — the pess direction, never an over-credit.) Pure."""
    if not day0_resolved:
        return None
    lo, hi = _f(post_low), _f(post_high)
    if lo is None or hi is None:
        return []
    return [{"m": None, "o": lo, "h": hi, "l": lo, "c": hi}]


def _ema_series(vals: list[float], n: int) -> list[float]:
    a, out, e = 2.0 / (n + 1), [], None
    for v in vals:
        e = v if e is None else e + a * (v - e)
        out.append(e)
    return out


def macd_620(closes: list[float]) -> tuple[list[float], list[float]]:
    """(MACD(6,20), EMA-9 signal) over 5-min closes — the frozen instrument's lines."""
    macd = [f - s for f, s in zip(_ema_series(closes, MACD_FAST),
                                  _ema_series(closes, MACD_SLOW))]
    return macd, _ema_series(macd, MACD_SIG)


def qualified_620_crosses(series: list[dict], adr_dollar: float,
                          start_idx: int) -> list[tuple[int, float]]:
    """Qualified bullish 620 crosses at global indices >= start_idx, #562's frozen
    guards VERBATIM (327s2 reconstruction): cross above the signal with MACD < 0;
    global index >= MIN_CROSS_IDX; basing — high-low range of the prior BASING_BARS
    buckets <= BASING_BAND_ADR x ADR$; hook — the MACD's HOOK_SHORT-bucket min <= its
    HOOK_LONG-bucket min (+1e-9). Returns [(index, cross-bar close)]. Pure."""
    out: list[tuple[int, float]] = []
    if not series or adr_dollar is None or adr_dollar <= 0:
        return out
    closes = [b["c"] for b in series]
    macd, sig = macd_620(closes)
    for i in range(max(1, start_idx), len(series)):
        if i < MIN_CROSS_IDX:
            continue
        if not (macd[i - 1] <= sig[i - 1] and macd[i] > sig[i] and macd[i] < 0):
            continue
        w = series[i - BASING_BARS:i]
        if (max(b["h"] for b in w) - min(b["l"] for b in w)) > BASING_BAND_ADR * adr_dollar:
            continue
        if not (min(macd[i - HOOK_SHORT:i]) <= min(macd[i - HOOK_LONG:i]) + 1e-9):
            continue
        out.append((i, closes[i]))
    return out


def session_needs_minutes_620(day_high: float, day_low: float, *, gap_close: float,
                              adr_dollar: Optional[float], state: dict) -> bool:
    """Daily pre-filter for rung 4: could a proximate cross exist this session? True
    when the rung is unfired, the band exists, and the session's range intersects the
    +-0.5xADR$ band around the EP-day close. Cheap and conservative — never decides a
    fire itself."""
    if state["fired_ep_close_620_prox"] or adr_dollar is None or adr_dollar <= 0:
        return False
    band = PROX_BAND_ADR * adr_dollar
    return day_low <= gap_close + band and day_high >= gap_close - band


def evaluate_session_620(warm_bars5: list[dict], session_bars5: list[dict], *,
                         gap_close: float, adr_dollar: Optional[float],
                         state: dict) -> dict:
    """Rung-4 evaluation for one session. The series = warm-up sessions' completed
    5-min bars + this session's (continuous EMAs); crosses are taken only from THIS
    session's buckets. Fire = the first qualified cross whose close sits within
    0.5xADR$ of the EP-day close; entry = that cross bar's 5-min close (#562 filled at
    the next 1-min open — a sub-bar difference inside the study's own +-1-bucket
    reconstruction tolerance); stop = low of day SO FAR (min low of this session's
    buckets through the cross bar — the operator's TEAM stop basis). A cross closing at
    the day low (entry <= stop) is skipped and the NEXT cross tried — the frozen
    fill-sanity rule. Fires at most once per campaign; the fire carries its MANDATORY
    placeholder near-definition label and the band input. Pure."""
    st = dict(state)
    fires: list[dict] = []
    if st["fired_ep_close_620_prox"] or adr_dollar is None or adr_dollar <= 0:
        return {"fires": fires, "state": st}
    series = list(warm_bars5) + list(session_bars5)
    start = len(warm_bars5)
    band = PROX_BAND_ADR * adr_dollar
    for i, close in qualified_620_crosses(series, adr_dollar, start):
        if abs(close - gap_close) > band:
            continue
        stop = min(b["l"] for b in session_bars5[:i - start + 1])
        if close <= stop or close <= 0:
            continue                      # frozen: an unfillable cross tries the next one
        fires.append({"rung": RUNG_620_PROX, "entry": close, "stop": stop,
                      "fire_minute": series[i]["m"],
                      "near_definition": NEAR_DEFINITION_PLACEHOLDER,
                      "band_adr_dollar": adr_dollar})
        st["fired_ep_close_620_prox"] = True
        break
    return {"fires": fires, "state": st}


def replay_level_break(sessions: list[date], bars_by_day: dict, level: float,
                       seed_prior_low: Optional[float]) -> dict:
    """Re-entry level-touch replay (pure): the first session whose daily HIGH reaches
    `level` — a resting stop-buy AT the level (the ep_high_break daily convention: a
    touch is provable from the daily bar; buy = the LEVEL, stop = the prior session's
    low). Missing sessions are COUNTED, never leapt silently — a fire recorded after
    missing sessions may be later than the true first touch (the caller stamps it). A
    fire whose prior-session low is unknown ABSTAINS (fire_date None, abstained True):
    the row cannot state its stop, so it is retried next run, never guessed."""
    missing = 0
    prior_low = seed_prior_low
    for d in sessions:
        b = bars_by_day.get(d) or {}
        hi, lo = _f(b.get("high_price")), _f(b.get("low_price"))
        if hi is None or lo is None:
            missing += 1
            prior_low = None              # the NEXT session's stop basis is now unknown
            continue
        if hi >= level:
            if prior_low is None or prior_low <= 0:
                return {"fire_date": None, "prior_low": None, "missing": missing,
                        "abstained": True}
            return {"fire_date": d, "prior_low": prior_low, "missing": missing,
                    "abstained": False}
        prior_low = lo
    return {"fire_date": None, "prior_low": None, "missing": missing, "abstained": False}


# ── Pure settlement core (fixture-testable, no IO) ─────────────────────────────────────


def sma_trail_line(closes: list[float]) -> Optional[float]:
    """The M-trail exit line: MAX(SMA10, SMA20) with the live exit_logic.py 'sma' mode
    semantics VERBATIM — the SMA includes the session's own close (running_closes), <20
    closes falls back to SMA10 alone, <10 closes -> None (no line yet, no trail exit —
    the live None-guard). Delegates to exit_path_shadow._sma_trail — the ONE mirrored
    copy of the live formula, pinned against broker/exit_logic.py by its byte-parity
    test — rather than re-deriving it a third time (2026-08-30 simplify review: a
    hand-rolled copy here could never notice the live formula changing)."""
    return _sma_trail(closes)[2]


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
        # 0 = the fire day, i>=1 = sessions[i-1]; the caller maps it to stop_hit_date.
        # Recorded so the re-entry pass can start the session AFTER the stop (day-2+).
        "stop_session_idx": none_exit if none_outcome == "stop" else None,
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


async def _fetch_620_warmup(ticker: str, session_date: date, ordered_days: list,
                            cache: dict) -> list[dict]:
    """Up to WARMUP_SESSIONS_620 prior sessions' completed 5-min bars, ascending — the
    EMA seed for the continuous 620 series. Best-effort by design: a missing warm-up
    day shortens the seed and MIN_CROSS_IDX stays the binding guard (#562's own
    day-one crosses had exactly that warm-up). Cached per member per run."""
    warm: list[dict] = []
    prior = [d for d in ordered_days if d < session_date][-WARMUP_SESSIONS_620:]
    for d in prior:
        if d not in cache:
            cache[d] = await _fetch_minute_5(ticker, d)
        warm.extend(cache[d])
    return warm


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
        # rung-4 band context — overwritten by the walker's fresh recompute every run
        "ep_adr20_dollar": _f(seed_row.get("ep_adr20_dollar")),
        "ep_adr20_n": seed_row.get("ep_adr20_n"),
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
                "fired_ep_high_break": False, "fired_ep_close_620_prox": False,
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


async def _resolve_session_bar(ticker: str, d: date, bars_by_day: dict,
                               ordered_days: Optional[list] = None) -> Optional[dict]:
    """THE one session-resolution path — the never-leap-a-gap invariant's single home
    (2026-08-30 simplify review: the walker and settlement backfilled a ranged-read
    hole via the single-day fallback while the re-entry replays silently dropped the
    SAME session, so one path scored a day another path pretended never happened).
    Returns the day's bar (high/low/close all present) from the ranged read, else ONE
    get_delayed_entry_daily_bar fallback fetch (mi_daily_closes + Polygon). A
    recovered bar is cached into bars_by_day (and ordered_days, kept ascending, when
    given) so prior-session-low lookups and settlement retries see it too. None = the
    session is GENUINELY missing everywhere — the caller abstains or counts it as
    blind, never leaps it silently."""
    b = bars_by_day.get(d)
    if (b is not None and b.get("high_price") is not None
            and b.get("low_price") is not None and b.get("close") is not None):
        return b
    o, h, l, c, src = await get_delayed_entry_daily_bar(ticker, d)
    if h is None or l is None or c is None:
        return None
    bar = {"trade_date": d, "open_price": o, "high_price": h, "low_price": l,
           "close": c, "volume": (b or {}).get("volume"), "_src": src}
    if ordered_days is not None and d not in ordered_days:
        insort(ordered_days, d)
    bars_by_day[d] = bar
    return bar


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

    # rung-4 band input: EP-day-anchored ADR$, recomputed FRESH from the same ranged
    # read every run (stored values are context, never trusted for the rule)
    adr_dollar, adr_n = compute_ep_adr_dollar(daily, ep_date, gap_close)
    ctx["ep_adr20_dollar"], ctx["ep_adr20_n"] = adr_dollar, adr_n
    warm_cache: dict[date, list] = {}

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

        b = await _resolve_session_bar(ticker, session_date, bars_by_day, ordered_days)
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
        needs_620 = session_needs_minutes_620(
            day_high, day_low, gap_close=gap_close, adr_dollar=adr_dollar, state=state)

        bars5: list[dict] = []
        if needs_minutes or needs_620:
            bars5 = await _fetch_minute_5(ticker, session_date)

        if (needs_minutes or needs_620) and not bars5:
            # ABSTAIN: fold the raw daily facts (facts are facts), fire no minute-grade
            # pattern, retry on later runs while the name is in the lane. When ONLY the
            # rung-4 band needed minutes, patterns 1-3 keep full daily fidelity
            # (prior_low passes through, so an unambiguous ep_high_break may still fire
            # and is recorded below); when patterns 1-3 needed them, no fire can slip
            # through: needs_minutes=True precludes the daily path's unambiguous-P3
            # condition (clean state + whole bar at/above the EP close), and
            # prior_session_low=None blocks P3 regardless.
            res = evaluate_session_daily(
                day_high, day_low, gap_low=gap_low, gap_close=gap_close,
                gap_high=gap_high,
                prior_session_low=(None if needs_minutes else prior_low), state=state)
            state = res["state"]
            row.update(_state_cols(state))
            row.update({"eval_status": "unscoreable",
                        "unscoreable_reason": "missing_minute_bars"})
            for fire in res["fires"]:
                wrote = await _record_trigger(
                    ticker=ticker, ep_date=ep_date, session_date=session_date,
                    session_idx=session_idx, fire=fire, ctx=ctx, state=state,
                    day_bar=(day_open, day_high, day_low, day_close, day_volume),
                    prior_low=prior_low, ordered_days=ordered_days,
                    bars_by_day=bars_by_day, resolution="daily", out=out)
                if wrote:
                    out["triggers"] += 1
            await upsert_delayed_entry_watch(row)
            out["watch_rows"] += 1
            out["unscoreable"] += 1
            continue

        if needs_minutes:
            res = evaluate_session_minute(
                bars5, gap_low=gap_low, gap_close=gap_close, gap_high=gap_high,
                prior_session_low=prior_low, state=state)
        else:
            res = evaluate_session_daily(
                day_high, day_low, gap_low=gap_low, gap_close=gap_close,
                gap_high=gap_high, prior_session_low=prior_low, state=state)

        if needs_620:
            warm = await _fetch_620_warmup(ticker, session_date, ordered_days, warm_cache)
            r620 = evaluate_session_620(
                warm, bars5, gap_close=gap_close, adr_dollar=adr_dollar,
                state=res["state"])
            res = {"fires": res["fires"] + r620["fires"], "state": r620["state"],
                   "p3_needs_prior_low": res.get("p3_needs_prior_low", False)}

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
                resolution="minute_5" if fire.get("fire_minute") is not None else "daily",
                out=out)
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
        "ep_adr20_dollar": ctx.get("ep_adr20_dollar"), "ep_adr20_n": ctx.get("ep_adr20_n"),
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


def _variant_fire_cols(entry: float, adr_dollar, adr_n, out: dict) -> dict:
    """The #616 fire-time variant columns, failure-isolated: a variant-side problem
    degrades to NULLs + a counted error and can never block the incumbent trigger
    insert. A genuinely missing ADR is NOT an error — it records NULL; the CALLER
    counts it (out['variant_missing_adr']) only when the insert actually wrote a row,
    so a re-walked no-op re-fire never double-counts."""
    vcols: dict = {"ep_adr20_dollar": None, "ep_adr20_n": None,
                   "stop_price_075": None, "stop_width_pct_075": None,
                   "stop_price_100": None, "stop_width_pct_100": None}
    try:
        vcols = variant_stop_cols(entry, adr_dollar, adr_n)
    except Exception as e:  # pure arithmetic — belt-and-braces per the #616 hard rule
        out["errors"] += 1
        logger.error(f"delayed_entry_shadow: variant fire cols failed: {e}")
    return vcols


async def _record_trigger(*, ticker, ep_date, session_date, session_idx, fire, ctx, state,
                          day_bar, prior_low, ordered_days, bars_by_day, resolution,
                          out) -> bool:
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
    vcols = _variant_fire_cols(entry, ctx.get("ep_adr20_dollar"), ctx.get("ep_adr20_n"),
                               out)
    missing_before = await count_delayed_entry_unscoreable(ticker, ep_date, session_date)
    day_open, day_high, day_low, day_close, day_volume = day_bar
    wrote = await insert_delayed_entry_trigger({
        **vcols,
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
        # ONE definition (db.py schema comment): blind sessions inside THIS attempt's
        # window — for a first attempt, unscoreable watch rows since the EP day
        "prior_missing_sessions": missing_before,
        "reentry_shape": SHAPE_FIRST, "prior_attempt_id": None,
        # the rung-4 placeholder label + band travel WITH the fire from the definition
        # site (evaluate_session_620) — None on every other rung
        "near_definition": fire.get("near_definition"),
        "band_adr_dollar": fire.get("band_adr_dollar"),
    })
    if wrote and vcols["stop_price_075"] is None:
        out["variant_missing_adr"] += 1      # NULL recorded, counted — never defaulted
    return wrote


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


async def _settle_trigger_variants(trig: dict, today: date, out: dict, *,
                                   sessions: list, bars_by_day: dict,
                                   closes_before: list, fire_day_bar: dict,
                                   post5: Optional[list], cache_day0: bool,
                                   gap_fill_ticker: Optional[str] = None) -> None:
    """Settle the #616 ADR-variant counterfactuals for ONE trigger — beside the
    incumbent, never instead of it (callers invoke this only AFTER the incumbent
    write). Each variant lands through its OWN guarded write (its outcome IS NULL) the
    moment it is definitive; a wider stop resolves later than the incumbent, so the
    pair usually completes across different runs. Reuses ONLY bars already in scope
    (the no-per-fire-fetch rule): `gap_fill_ticker` enables the incumbent's own
    bounded single-day daily-bar fills (the standalone pass), never a minute fetch. A
    per-variant exception degrades to audit + retry-next-run. When a variant stays
    pending and the fire day's post-fire 5-min bars are in scope, their (min low,
    max high) is cached once so later runs can finish day 0 without a refetch."""
    if trig.get("ep_adr20_n") is None:
        return                            # pre-#616 row — no variant record exists
    entry = _f(trig.get("entry_price"))
    fire_minute = trig.get("fire_minute_et")
    orphan = trig["fire_date"] <= today - timedelta(days=SETTLE_ORPHAN_CAL_DAYS)
    abstained = False
    for sfx, _mult in ADR_STOP_VARIANTS:
        if trig.get(f"outcome_{sfx}") is not None:
            continue                      # this variant already settled on a prior run
        vstop = _f(trig.get(f"stop_price_{sfx}"))
        if vstop is None:
            # no ADR at fire — recorded NULL, counted then; closes unscoreable now
            fields = variant_unscoreable_fields()
        else:
            try:
                res = {"status": "abstain", "reason": "window_open"}
                for _ in range(6):  # bounded single-day gap fills (standalone only)
                    res = compute_settlement(
                        entry=entry, stop=vstop, fire_minute=fire_minute,
                        fire_day_bar=fire_day_bar, post_fire_bars5=post5,
                        sessions=sessions, bars_by_day=bars_by_day,
                        closes_before_fire=closes_before)
                    reason = res.get("reason", "")
                    if (gap_fill_ticker is not None and res["status"] == "abstain"
                            and reason.startswith("missing_session:")):
                        d = date.fromisoformat(reason.split(":", 1)[1])
                        if await _resolve_session_bar(gap_fill_ticker, d,
                                                      bars_by_day) is None:
                            break         # genuinely missing — the abstain stands
                        continue
                    break
            except Exception as e:
                out["errors"] += 1
                logger.error(
                    f"delayed_entry_shadow: variant {sfx} settle {trig.get('ticker')} "
                    f"{trig.get('fire_date')} failed: {e}")
                await log_audit_event(
                    "delayed_entry_shadow_error",
                    f"variant {sfx} {trig.get('ticker')} {trig.get('rung')} "
                    f"{trig.get('fire_date')}: {type(e).__name__}: {e}")
                abstained = True          # retry next run; orphan horizon backstops
                continue
            if res["status"] == "settled":
                fields = variant_settle_fields(res)
            elif res["status"] == "unscoreable" or orphan:
                fields = variant_unscoreable_fields()
            else:
                abstained = True
                out["variant_abstained"] += 1
                continue
        fields["settle_version"] = SETTLE_VERSION
        if await settle_delayed_entry_trigger_variant(trig["id"], sfx, fields):
            if fields["outcome"] == "unscoreable":
                out["variant_unscoreable"] += 1
            else:
                out["variant_settled"] += 1
        # False = a concurrent run already settled this variant — the no-op is the point
    if (abstained and cache_day0 and post5 is not None
            and not trig.get("day0_resolved")):
        lo = min((b["l"] for b in post5), default=None)
        hi = max((b["h"] for b in post5), default=None)
        await record_delayed_entry_trigger_day0(trig["id"], lo, hi)


async def _try_settle_variants_inline(trig: dict, today: date, out: dict,
                                      **ctx) -> None:
    """Attempt the #616 variant settlements with the bars already in scope, AFTER the
    incumbent write. An exception here is counted and audited but can never undo or
    block the incumbent settlement — the one hard #616 rule."""
    try:
        await _settle_trigger_variants(trig, today, out, cache_day0=True, **ctx)
    except Exception as e:
        out["errors"] += 1
        logger.error(
            f"delayed_entry_shadow: inline variant settle {trig.get('ticker')} "
            f"{trig.get('fire_date')} failed: {e}")
        try:
            await log_audit_event(
                "delayed_entry_shadow_error",
                f"variant inline {trig.get('ticker')} {trig.get('rung')} "
                f"{trig.get('fire_date')}: {type(e).__name__}: {e}")
        except Exception:  # loud-ok: log_audit_event self-catches; logger fired above
            pass


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
            if await _resolve_session_bar(ticker, d, bars_by_day) is None:
                break  # genuinely missing (halt/delist/hole) — the abstain stands
            continue
        break

    if res["status"] == "settled":
        fields = {k: v for k, v in res.items() if k != "status"}
        idx = fields.pop("stop_session_idx", None)
        if idx is not None:
            # the SHARED stop's touch day (raw fact): day 0 = the fire day itself
            fields["stop_hit_date"] = fire_date if idx == 0 else sessions[idx - 1]
        fields["settle_version"] = SETTLE_VERSION
        if await settle_delayed_entry_trigger(trig["id"], fields):
            out["settle_settled"] += 1
        # False = a concurrent run already settled it — the no-op is the point
        await _try_settle_variants_inline(
            trig, today, out, sessions=sessions, bars_by_day=bars_by_day,
            closes_before=closes_before, fire_day_bar=fire_day_bar, post5=post5)
        return
    if res["status"] == "unscoreable":
        await _close_unscoreable(trig, out, res.get("reason", "unscoreable"))
        await _try_settle_variants_inline(
            trig, today, out, sessions=sessions, bars_by_day=bars_by_day,
            closes_before=closes_before, fire_day_bar=fire_day_bar, post5=post5)
        return
    # abstain: honest retry — unless the row is past the orphan horizon, where the
    # 20-session window has long elapsed and the bars are never coming
    if fire_date <= today - timedelta(days=SETTLE_ORPHAN_CAL_DAYS):
        await _close_unscoreable(
            trig, out,
            f"still blocked ({res.get('reason')}) {SETTLE_ORPHAN_CAL_DAYS}+ calendar days "
            f"after the fire — bars are not coming (halt/delist/hole)")
        await _try_settle_variants_inline(
            trig, today, out, sessions=sessions, bars_by_day=bars_by_day,
            closes_before=closes_before, fire_day_bar=fire_day_bar, post5=post5)
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


async def _settle_variant_one(trig: dict, today: date, out: dict) -> None:
    """Finish ONE incumbent-settled trigger's #616 variant settlements from stored
    daily bars. Mirrors _settle_one_trigger's assembly (same window read, same bounded
    single-day gap fills through _resolve_session_bar) with ONE deliberate difference:
    day-0 minutes are NEVER refetched — the day0_post_low/high cache stands in when it
    was written, and a variant that needs day-0 minutes that were never in scope
    abstains until the orphan horizon closes it unscoreable, counted (the #616
    no-per-fire-fetch rule; the censored class is recorded, never silently leapt)."""
    ticker, fire_date = trig["ticker"], trig["fire_date"]
    if (_f(trig.get("stop_price_075")) is None
            and _f(trig.get("stop_price_100")) is None):
        # ADR was missing at fire (counted then): closeable without any bars
        await _settle_trigger_variants(
            trig, today, out, sessions=[], bars_by_day={}, closes_before=[],
            fire_day_bar={}, post5=None, cache_day0=False)
        return
    sessions = _trading_days(fire_date + timedelta(days=1), today)
    daily = await get_delayed_entry_daily_window(
        ticker, fire_date - timedelta(days=_SETTLE_SMA_FETCH_CAL_DAYS), today)
    bars_by_day = {b["trade_date"]: b for b in daily}
    closes_before = [_f(b.get("close")) for b in daily
                     if b["trade_date"] < fire_date and b.get("close") is not None]
    fb = bars_by_day.get(fire_date) or {}
    fire_day_bar = {
        "h": _f(trig.get("day_high")) if trig.get("day_high") is not None else _f(fb.get("high_price")),
        "l": _f(trig.get("day_low")) if trig.get("day_low") is not None else _f(fb.get("low_price")),
        "c": _f(trig.get("day_close")) if trig.get("day_close") is not None else _f(fb.get("close")),
    }
    post5 = day0_pseudo_bars(trig.get("day0_resolved"), trig.get("day0_post_low"),
                             trig.get("day0_post_high"))
    await _settle_trigger_variants(
        trig, today, out, sessions=sessions, bars_by_day=bars_by_day,
        closes_before=closes_before, fire_day_bar=fire_day_bar, post5=post5,
        cache_day0=False, gap_fill_ticker=ticker)


async def settle_open_variant_triggers(today: date, out: dict) -> None:
    """The #616 variant-completion pass — rides the same evening run, AFTER the
    incumbent settlement pass (a variant only pends once its incumbent has settled; a
    wider stop resolves later by construction, so this pass is where most variants
    finish). Per-row failures degrade to mi_audit_log and the pass continues. Cost
    profile: one mi_daily_closes ranged read per pending row per run (the same class
    as the incumbent pass) and NO minute fetches, ever."""
    try:
        rows = await get_delayed_entry_variant_pending()
    except Exception as e:
        out["errors"] += 1
        logger.error(f"delayed_entry_shadow: variant-pending read failed: {e}",
                     exc_info=True)
        await log_audit_event("delayed_entry_shadow_error",
                              f"variant-pending read: {type(e).__name__}: {e}")
        return
    for trig in rows:
        out["variant_considered"] += 1
        try:
            await _settle_variant_one(trig, today, out)
        except Exception as e:
            out["errors"] += 1
            logger.error(
                f"delayed_entry_shadow: variant settle {trig.get('ticker')} "
                f"{trig.get('fire_date')} failed: {e}")
            try:
                await log_audit_event(
                    "delayed_entry_shadow_error",
                    f"variant {trig.get('ticker')} {trig.get('rung')} "
                    f"{trig.get('fire_date')}: {type(e).__name__}: {e}")
            except Exception:  # loud-ok: log_audit_event self-catches; logger fired above
                pass


# ── Re-entry recording (piece 2 — RECORDING only; the review rules, never this code) ───


async def _replay_same_pattern_reclaim(cand: dict, sessions: list[date], bars_by_day: dict,
                                       ordered_days: list) -> Optional[dict]:
    """Fresh-state walk of the rung's OWN pattern over the re-entry window (same
    evaluators, same pivots — the definition is reused, not redesigned). Only THIS
    rung's fire is taken; other rungs' fires in the fresh walk are ignored (this is a
    per-rung campaign replay, not a second lane). Sessions resolve through
    _resolve_session_bar (ranged read, then the single-day fallback — the ONE
    never-leap-a-gap path); only a session missing EVERYWHERE counts into the
    prior_missing_sessions stamp, and is never leapt silently."""
    rung = cand["rung"]
    gap_low, gap_close, gap_high = (_f(cand.get("gap_day_low")),
                                    _f(cand.get("gap_day_close")),
                                    _f(cand.get("gap_day_high")))
    if gap_low is None or gap_close is None or gap_high is None:
        return None
    state = new_state()
    missing = 0
    for d in sessions:
        b = await _resolve_session_bar(cand["ticker"], d, bars_by_day, ordered_days)
        if b is None:
            missing += 1                  # genuinely missing everywhere — blind session
            continue
        day_high, day_low = _f(b.get("high_price")), _f(b.get("low_price"))
        prior_low = _prior_session_low(ordered_days, bars_by_day, d)
        if session_needs_minutes(day_high, day_low, gap_low=gap_low,
                                 gap_close=gap_close, gap_high=gap_high, state=state):
            bars5 = await _fetch_minute_5(cand["ticker"], d)
            if not bars5:
                missing += 1              # ABSTAIN this session; facts still fold
                res = evaluate_session_daily(
                    day_high, day_low, gap_low=gap_low, gap_close=gap_close,
                    gap_high=gap_high, prior_session_low=None, state=state)
                state = res["state"]
                continue
            res = evaluate_session_minute(
                bars5, gap_low=gap_low, gap_close=gap_close, gap_high=gap_high,
                prior_session_low=prior_low, state=state)
        else:
            res = evaluate_session_daily(
                day_high, day_low, gap_low=gap_low, gap_close=gap_close,
                gap_high=gap_high, prior_session_low=prior_low, state=state)
        state = res["state"]
        for fire in res["fires"]:
            if fire["rung"] == rung:
                return {"fire": fire, "fire_date": d, "prior_low": prior_low,
                        "missing": missing}
    return None


async def _replay_same_pattern_620(cand: dict, sessions: list[date], bars_by_day: dict,
                                   ordered_days: list) -> Optional[dict]:
    """Fresh 620 replay for a stopped rung-4 campaign: the next qualified proximate
    turn after the stop-out, same frozen instrument, band recomputed from raw bars."""
    gap_close = _f(cand.get("gap_day_close"))
    if gap_close is None:
        return None
    daily = [bars_by_day[d] for d in ordered_days]
    adr_dollar, _n = compute_ep_adr_dollar(daily, cand["ep_date"], gap_close)
    if adr_dollar is None or adr_dollar <= 0:
        return None
    state = new_state()
    missing = 0
    warm_cache: dict[date, list] = {}
    for d in sessions:
        b = await _resolve_session_bar(cand["ticker"], d, bars_by_day, ordered_days)
        if b is None:
            missing += 1                  # genuinely missing everywhere — blind session
            continue
        day_high, day_low = _f(b.get("high_price")), _f(b.get("low_price"))
        if not session_needs_minutes_620(day_high, day_low, gap_close=gap_close,
                                         adr_dollar=adr_dollar, state=state):
            continue
        bars5 = await _fetch_minute_5(cand["ticker"], d)
        if not bars5:
            missing += 1                  # ABSTAIN this session, retry next run
            continue
        warm = await _fetch_620_warmup(cand["ticker"], d, ordered_days, warm_cache)
        res = evaluate_session_620(warm, bars5, gap_close=gap_close,
                                   adr_dollar=adr_dollar, state=state)
        state = res["state"]
        if res["fires"]:
            return {"fire": res["fires"][0], "fire_date": d,
                    "prior_low": _prior_session_low(ordered_days, bars_by_day, d),
                    "missing": missing}
    return None


async def _record_attempt_trigger(cand: dict, shape: str, *, fire: dict, fire_date: date,
                                  prior_low: Optional[float], bars_by_day: dict,
                                  ordered_days: list, missing: int, out: dict) -> bool:
    """Assemble + insert one re-entry row, identified by its reentry_shape and linked
    to the stopped attempt via prior_attempt_id — it can never overwrite attempt 1
    (different reentry_shape = different row under the unique index). `missing` = blind
    sessions inside THIS attempt's replay window (since the stop-out), the re-entry
    half of the one prior_missing_sessions definition. Settled later by the same
    machinery as any trigger, so a FAILED re-entry lands as -1R, counted."""
    ticker, ep_date = cand["ticker"], cand["ep_date"]
    entry, stop = float(fire["entry"]), float(fire["stop"])
    width = stop_width_pct(entry, stop)
    if width is None:
        await log_audit_event(
            "delayed_entry_shadow_error",
            f"{ticker} {ep_date} {cand['rung']}/{shape}: non-positive entry {entry} — "
            f"re-entry fire dropped")
        return False
    b = bars_by_day.get(fire_date) or {}
    pre_fire_days = [d for d in ordered_days if d < fire_date]
    adr, adr_n = compute_adr20([bars_by_day[d] for d in pre_fire_days])
    # #616: the EP-anchored ADR$ recomputed from the bars already in scope (the
    # re-entry window read spans min(ep_date, stop_day) − 60d, so the pre-EP window is
    # covered) — same basis, same compute, as a first attempt's stamp. No fetch.
    ep_adr_dollar, ep_adr_n = compute_ep_adr_dollar(
        [bars_by_day[d] for d in ordered_days], ep_date, _f(cand.get("gap_day_close")))
    vcols = _variant_fire_cols(entry, ep_adr_dollar, ep_adr_n, out)
    gap_high = _f(cand.get("gap_day_high"))
    ghe = None
    if gap_high is not None:
        highs = [_f(bars_by_day[d].get("high_price")) for d in pre_fire_days
                 if d > ep_date]
        ghe = any(h is not None and h >= gap_high for h in highs)
    wrote = await insert_delayed_entry_trigger({
        **vcols,
        "ticker": ticker, "ep_date": ep_date, "rung": cand["rung"],
        "pattern_version": PATTERN_VERSION, "fire_date": fire_date,
        "fire_minute_et": fire.get("fire_minute"),
        "resolution": "minute_5" if fire.get("fire_minute") is not None else "daily",
        "sessions_since_ep": max(0, len(_trading_days(ep_date, fire_date)) - 1),
        "entry_price": entry, "stop_price": stop, "stop_width_pct": width,
        "gap_day_low": _f(cand.get("gap_day_low")),
        "gap_day_close": _f(cand.get("gap_day_close")),
        "gap_day_high": gap_high, "gap_day_volume": cand.get("gap_day_volume"),
        "prior_session_low": prior_low,
        "day_open": _f(b.get("open_price")), "day_high": _f(b.get("high_price")),
        "day_low": _f(b.get("low_price")), "day_close": _f(b.get("close")),
        "day_volume": b.get("volume"),
        "adr20_pct": adr, "adr20_n": adr_n,
        "gap_high_exceeded_before": ghe,
        "in_active_theme": cand.get("in_active_theme"),
        "ep_score": _f(cand.get("ep_score")),
        "catalyst_grade": cand.get("catalyst_grade"),
        "screen_member": cand.get("screen_member"),
        "screen_version": cand.get("screen_version") or SCREEN_VERSION,
        "prior_missing_sessions": missing,
        "reentry_shape": shape, "prior_attempt_id": cand["id"],
        # EVERY row of a rung-4 campaign carries the placeholder label (its rung-4
        # result rests on the band no matter which shape fired) — CHECK-enforced
        "near_definition": (NEAR_DEFINITION_PLACEHOLDER
                            if cand["rung"] == RUNG_620_PROX
                            else fire.get("near_definition")),
        "band_adr_dollar": fire.get("band_adr_dollar"),
    })
    if wrote and vcols["stop_price_075"] is None:
        out["variant_missing_adr"] += 1      # NULL recorded, counted — never defaulted
    return wrote


async def _record_reentries_for(cand: dict, today: date, out: dict) -> None:
    """Replay BOTH bounded re-entry shapes for one settled-stop first attempt, writing
    at most one row per shape. The window is REENTRY_WATCH_SESSIONS
    trading sessions starting the session AFTER the stop-out — the day-2+ boundary is
    structural, not a filter (same-day re-entry is out of scope, ruled 2026-08-30)."""
    ticker, ep_date, rung = cand["ticker"], cand["ep_date"], cand["rung"]
    stop_day = cand["stop_hit_date"]
    sessions = _trading_days(stop_day + timedelta(days=1), today)[:REENTRY_WATCH_SESSIONS]
    if not sessions:
        return                            # the stop settled tonight — window opens tomorrow
    window = await get_delayed_entry_daily_window(
        ticker, min(ep_date, stop_day) - timedelta(days=_ADR_FETCH_CAL_DAYS), today)
    bars_by_day = {b["trade_date"]: b for b in window}
    ordered_days = [b["trade_date"] for b in window]
    gap_high = _f(cand.get("gap_day_high"))

    shapes = []
    if not cand.get("has_same_pattern"):
        shapes.append(SHAPE_SAME)
    if not cand.get("has_new_high_break"):
        shapes.append(SHAPE_NEWHIGH)
    for shape in shapes:
        if shape == SHAPE_SAME and rung in (RUNG_EP_LOW, RUNG_EP_CLOSE):
            hit = await _replay_same_pattern_reclaim(cand, sessions, bars_by_day,
                                                     ordered_days)
        elif shape == SHAPE_SAME and rung == RUNG_620_PROX:
            hit = await _replay_same_pattern_620(cand, sessions, bars_by_day,
                                                 ordered_days)
        else:
            # level-touch shapes, daily-provable (a touch of a resting stop-buy level):
            #   same_pattern of ep_high_break = a re-touch of the EP-day high
            #   new_high_break (any rung)     = a break above MAX(EP-day high, every
            #     session high through the stop-out) — proof of strength (the R3 shape)
            if gap_high is None:
                continue
            level = gap_high
            if shape == SHAPE_NEWHIGH:
                ref_days = _trading_days(ep_date + timedelta(days=1), stop_day)
                highs = [_f((bars_by_day.get(d) or {}).get("high_price"))
                         for d in ref_days]
                # a hole in the level-reference window can only UNDERSTATE the level;
                # it is NOT a blind session of THIS attempt's replay window and never
                # counts into prior_missing_sessions (the one-definition rule,
                # 2026-08-30 simplify review)
                level = max([gap_high] + [h for h in highs if h is not None])
            # the replay window resolves through the ONE shared path before the pure
            # level walk, so a ranged-read hole is backfilled here exactly as on every
            # other path and replay_level_break's `missing` counts only sessions that
            # are genuinely missing everywhere
            for d in sessions:
                await _resolve_session_bar(ticker, d, bars_by_day, ordered_days)
            seed = bars_by_day.get(stop_day) or {}
            lb = replay_level_break(sessions, bars_by_day, level,
                                    seed_prior_low=_f(seed.get("low_price")))
            if lb["abstained"] or lb["fire_date"] is None:
                continue                  # abstain-and-retry next run / nothing yet
            hit = {"fire": {"rung": rung, "entry": level, "stop": lb["prior_low"],
                            "fire_minute": None},
                   "fire_date": lb["fire_date"], "prior_low": lb["prior_low"],
                   "missing": lb["missing"]}
        if hit is None:
            continue
        wrote = await _record_attempt_trigger(
            cand, shape, fire=hit["fire"], fire_date=hit["fire_date"],
            prior_low=hit["prior_low"], bars_by_day=bars_by_day,
            ordered_days=ordered_days, missing=hit["missing"], out=out)
        if wrote:
            out["reentry_recorded"] += 1


async def record_reentry_attempts(today: date, out: dict) -> None:
    """The re-entry recording pass — rides the same evening run, AFTER settlement, so a
    stop settled tonight enters the pass immediately (its replay window simply starts
    tomorrow). RECORDING ONLY: no policy decided, nothing traded, nothing alerted.
    Per-candidate failures degrade to mi_audit_log and the pass continues."""
    try:
        cands = await get_delayed_entry_reentry_candidates(
            today - timedelta(days=REENTRY_MAX_CAL_DAYS))
    except Exception as e:
        out["errors"] += 1
        logger.error(f"delayed_entry_shadow: re-entry candidate read failed: {e}",
                     exc_info=True)
        await log_audit_event("delayed_entry_shadow_error",
                              f"re-entry read: {type(e).__name__}: {e}")
        return
    for cand in cands:
        out["reentry_considered"] += 1
        try:
            await _record_reentries_for(cand, today, out)
        except Exception as e:
            out["errors"] += 1
            logger.error(
                f"delayed_entry_shadow: re-entry {cand.get('ticker')} "
                f"{cand.get('rung')} failed: {e}")
            try:
                await log_audit_event(
                    "delayed_entry_shadow_error",
                    f"re-entry {cand.get('ticker')} {cand.get('rung')} "
                    f"{cand.get('ep_date')}: {type(e).__name__}: {e}")
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
           "settle_unscoreable": 0, "reentry_considered": 0, "reentry_recorded": 0,
           "variant_considered": 0, "variant_settled": 0, "variant_abstained": 0,
           "variant_unscoreable": 0, "variant_missing_adr": 0}
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

    # #616 variant completion AFTER the incumbent pass: a variant only pends once its
    # incumbent settled (wider stop -> later resolution). Self-catches per row.
    await settle_open_variant_triggers(today, out)

    # re-entry recording runs AFTER settlement so tonight's settled stops enter the
    # pass immediately (their replay window starts the next session — day-2+)
    await record_reentry_attempts(today, out)

    try:
        await log_audit_event(
            "delayed_entry_shadow_recorded",
            f"{out['watch_rows']} watch row(s), {out['triggers']} trigger(s) across "
            f"{out['members']} lane member(s) for {today} "
            f"({out['enrolled']} enrolled, {out['unscoreable']} unscoreable, "
            f"{out['errors']} error(s)); settlement: {out['settle_considered']} open "
            f"trigger(s) considered, {out['settle_settled']} settled, "
            f"{out['settle_abstained']} abstained (still open — retry), "
            f"{out['settle_unscoreable']} closed unscoreable; re-entry: "
            f"{out['reentry_considered']} stopped campaign(s) considered, "
            f"{out['reentry_recorded']} attempt row(s) recorded; ADR-stop variants "
            f"(#616): {out['variant_considered']} pending considered, "
            f"{out['variant_settled']} settled, {out['variant_abstained']} abstained, "
            f"{out['variant_unscoreable']} closed unscoreable, "
            f"{out['variant_missing_adr']} fire(s) with no ADR")
    except Exception as _e:  # loud-ok: telemetry-of-telemetry; the rows are already durable
        logger.warning(f"delayed_entry_shadow audit emit failed (non-fatal): {_e}")
    return out
