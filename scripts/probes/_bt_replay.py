"""#482 — reusable EP backtest replay harness (Stage 3: entries/exits from bars).

Read FIRST, do not redesign:
  docs/design/ep_backtest_spec_2026-08-29.md  (Stage 3 = §5, scoring = §6 — the sections
  this file is scoped to)
  docs/setups/magna53_ep.md                   (the bracket SSoT, operator-signed 2026-08-16)

WHAT THIS IS. Given a candidate (ticker, date), its 09:30 ET ORB bar, its subsequent day-0
minute bars, and its subsequent daily bars, replays TODAY's live magna53 bracket and returns
a scored R outcome + a reason. Pure functions, no DB — a separate fetch layer (bottom of the
file, gated behind __main__) pulls real bars over the read-only ssh+psql path and feeds them
in. Importable: `from scripts.probes._bt_replay import replay_trade`.

THE BRACKET (operator-signed 2026-08-16 — see magna53_ep.md's change log entry of that date;
this is a summary for orientation, the SSoT is the file, not this comment):
  - Entry: stop-limit buy at the ORB high (09:30 ET bar's high). Fill model (spec §5): first
    bar in 09:31-09:59 whose high >= orb_high fills at max(bar_open, orb_high); a bar that
    OPENS above orb_high (gap-through) does not fill that bar. Unfilled by 10:00 ->
    never_triggered. (Under this mechanical fill model, entry always equals orb_high exactly
    whenever a fill occurs, because a fill only happens when bar_open <= orb_high, in which
    case max(bar_open, orb_high) == orb_high. Real broker fills can slip above orb_high —
    the SSoT's own AMLX example shows entry_price=30.211219 against orb_high=30.07 — but
    matching that slippage is explicitly out of scope (design spec §9: "the fill model is
    mechanical"). Stop and target are still computed from separate formulas below rather than
    hard-coding this equivalence, per review.)
  - R_orb = entry - orb_low. R_orb DEFINES the bracket geometry (both the stop and the target
    derive from it) but is NOT the unit trades are scored in — see R_actual below.
  - Hard stop = entry - 2*R_orb, equivalently 2*orb_low - orb_high. ORB-anchored (2026-08-16
    change: the ORB low stopped being the exit and started only defining R).
  - Profit target = entry + 2*R_orb. Entry-anchored, pinned to the ORIGINAL R_orb — does NOT
    re-anchor to the wider stop distance (magna53_ep.md 2026-08-16: "The +2R partial target
    does NOT move... `scan_profit_triggers` previously framed the target off entry-hard_stop
    — with the new stop that silently becomes +4R, never tested, never approved"). 1/3 of the
    position exits there (`execute_partial_exit`, hardcoded 1/3 — same fraction confirmed in
    `broker/exit_logic.py`'s Day3-5 partial); the stop on the remaining 2/3 moves to breakeven
    (`max(stop, entry)` == entry here since entry > hard_stop always).
  - R_actual = entry - hard_stop = 2*R_orb (exactly, under this fill model). This is the
    SCORED unit — design spec §5: "all outcomes in R = planned dollar risk (entry - hard_stop
    per share x shares — invariant across the 08-16 change by construction)". Cross-checked
    against the SSoT's own signed evidence: the 2R arm's median outcome is quoted as +0.33 —
    only reachable if R = R_actual (a stop is exactly -1.0R; the +2R target, expressed in
    R_actual units, is exactly +1.0R, because 2*R_orb / R_actual == 1.0 by construction; +0.33
    is "1/3 came off at +1.0R and the runner gave back everything to breakeven [0.0R]", i.e.
    (1/3)*1.0 + (2/3)*0.0 = 0.333). Under R_orb the stop/target would be +-2.0R and the
    quoted +0.33 median would be unreachable — this is what pins the unit choice.

EXIT MODEL — WHAT IS AND ISN'T REUSED FROM THE LIVE SYSTEM. `broker/exit_logic.py`'s
`apply_daily_exit_step` is the live/backtest-shared SSoT for the SMA10/20 trail + a
time-based Day3-5 partial + breakeven + giveback floor. It is NOT wired into this harness.
That is a deliberate scope cut, not an oversight — design spec §5/D7 says "reuse, don't
re-implement" for the FULL backtest assembly, but that ladder needs `prior_closes`, a trail
indicator, and a 40-session state carry that this scoped 5-reason harness does not attempt.
Its Day3-5 partial is not a second, contradictory partial rule — it is gated on
`not partial_taken`, and `scan_profit_triggers` (the live +2R trigger) sets that same flag,
so in the live system only one of the two ever fires for a given trade. This harness models
only the +2R trigger (the one that actually fires first in every observed live trade so far)
and the hard stop; a name that survives past +2R without the +2R trigger having fired subject
to a Day3-5 close-based partial is NOT modeled here. Flagged, not silently substituted.

Exit walk, first touch decides, in sequence:
  1. Day-0 minute bars from the fill bar forward, then daily OHLC for day 1+ (design spec
     §5's own convention for subsequent days: "stop fires when bar_low <= hard_stop").
  2. Hard stop touched before any partial -> reason='stopped', R=-1.0. Terminal.
  3. Target touched before the hard stop -> 1/3 leg locks exactly +1.0R; stop on the
     remaining 2/3 becomes breakeven (entry). The walk continues over the SAME bar stream,
     now watching only for a low/close <= entry (breakeven exit, 0.0R leg) or exhaustion
     (runner held at last known price). Reason='target' either way — the partial firing is
     what defines the trade, not what the runner does afterward.
  4. Never stopped, never targeted, bars/horizon exhausted with the full position still open
     -> reason='held_to_close', R = (last_price - entry) / R_actual.
  5. Missing coverage for the entry day itself (no 09:30 bar, or nothing to walk after it)
     -> reason='no_bars', R=None. Counted, never dropped, never fabricated (method req #4).
  6. Entry never fills by 09:59 -> reason='never_triggered', R=None.

A single bar (minute or daily) whose range spans BOTH the live stop and the target resolves
stop-first (conservative — design spec §5's explicit tie-break, applied uniformly to daily
bars too for consistency, since the spec does not carve out a different rule for them).

Horizon: 40 sessions after day 0 (design spec §5), force-marked at the 40th day's close if
still open by then.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date

PARTIAL_FRACTION = 1.0 / 3.0
HORIZON_SESSIONS = 40

REASONS = frozenset({"stopped", "target", "held_to_close", "never_triggered", "no_bars"})

# ── Runner-rule sweep extension (2026-08-29, read-only evidence run) ─────────────────────
# Everything UPSTREAM of the +2R partial is identical for every rule: population, entry,
# the entry−2R hard stop, the +2R partial itself. A rule governs ONLY the remaining 2/3
# after the partial fires. "breakeven" (the default) is byte-identical to the pre-extension
# behavior — the original self-tests below run against the default and stay green, and the
# sweep driver additionally diffs all 295 Run-U rows against run 1's stored outcomes.
#   breakeven      stop to entry after the partial (touch) — THE CONTROL (live bracket).
#   hard           no breakeven move: the original entry−2R stop stays (touch).
#   sma10 / sma20  daily close below the stock's real SMA10/SMA20 → exit at that close
#                  (live exit_logic.py semantics: close-below, SMA includes today's close;
#                  prior_closes end the day before entry, #548). Hard stop stays as the
#                  touch floor.
#   live_trail_be  what the live exit ladder composes post-partial: breakeven touch floor
#                  PLUS close below max(SMA10, SMA20) → exit at that close.
#   atr1 / atr2    chandelier: touch of (peak close so far − k×ATR14@entry), ratcheting,
#                  floored at the hard stop; peak through the PRIOR session (no same-bar
#                  peak-then-stop lookahead at daily granularity). Exit at the level.
#   gb25 / gb50    give back 25%/50% of the peak-close gain: floor = entry + keep×(peak −
#                  entry), close-below → exit at that close (live giveback_floor semantics).
#   t3/t5/t10/t20  hold N sessions after the partial day, exit at that session's close;
#                  hard stop stays as the touch floor until then.
#   sma10_touch / sma20_touch   granularity sensitivity only: intraday LOW below the
#                  prior-session SMA triggers at the SMA level (what a minute-level trail
#                  would approximate). Not a candidate rule; an error bar on sma10/sma20.
# runner_ctx supplies what the daily rules need: prior_closes (closes strictly before the
# entry date, oldest-first), atr14 (absolute, computed through D−1 exactly as the admission
# filter computes it), day0_close (the entry day's official daily close). Missing inputs
# degrade loudly-conservatively: no atr14 → chandelier never rises off the hard stop; too
# few closes → no SMA → no trail exit (the live None-guard).
# gap_fill_at_open=True is a sensitivity pricing: a daily bar that OPENS below a touch
# level fills at the open, not the level (the control convention prices all touch exits at
# the level — optimistic on overnight gaps, for every rule alike).
RUNNER_RULES = frozenset({
    "breakeven", "hard", "sma10", "sma20", "live_trail_be", "atr1", "atr2",
    "gb25", "gb50", "t3", "t5", "t10", "t20", "sma10_touch", "sma20_touch",
})


@dataclass
class TradeResult:
    ticker: str
    date: object
    reason: str
    r_multiple: float | None       # scored R — unit is R_actual = entry - hard_stop
    r_orb: float | None            # entry - orb_low — reported, NOT the scoring unit
    entry: float | None = None
    orb_high: float | None = None
    orb_low: float | None = None
    hard_stop: float | None = None
    target: float | None = None
    detail: str | None = None      # diagnostic sub-reason; not part of the 5-value contract

    def __post_init__(self):
        assert self.reason in REASONS, f"unknown reason {self.reason!r}"
        if self.reason in ("never_triggered", "no_bars"):
            assert self.r_multiple is None, "unscoreable/never-filled trades must not carry an R"


def _fill_entry(orb_high: float, entry_bars: list[dict]):
    """First bar (ascending, 09:31 onward) whose high >= orb_high AND open <= orb_high fills
    at orb_high — a bar that opens above the limit gaps through and does not fill that bar
    (spec §5). Returns (index_into_entry_bars, fill_price) or (None, None)."""
    for i, b in enumerate(entry_bars):
        if b["open"] > orb_high:
            continue
        if b["high"] >= orb_high:
            return i, orb_high
    return None, None


def replay_trade(
    ticker: str,
    date: _date | str,
    orb_bar: dict | None,
    entry_bars: list[dict] | None,
    daily_bars: list[dict] | None,
    *,
    horizon_sessions: int = HORIZON_SESSIONS,
    coverage_ok: bool = True,
    runner_rule: str = "breakeven",
    runner_ctx: dict | None = None,
    gap_fill_at_open: bool = False,
) -> TradeResult:
    """Replay one candidate through today's live magna53 bracket.

    orb_bar: {'high', 'low'} for the 09:30 ET bar, or None if missing.
    entry_bars: minute bars 09:31 onward for the SAME day, ascending, each with
      open/high/low/close. Only bars up to and including ~09:59 matter for the fill decision;
      bars after that (up through the close) are used for the day-0 stop/target walk once
      filled. Pass None/[] if genuinely no bars exist after the ORB bar.
    daily_bars: daily OHLC dicts for trade_date > date, ascending, each with low/high/close
      (any key names — normalize before calling; this module doesn't touch the DB).
    coverage_ok: True (default) asserts daily_bars is complete to either the horizon or the
      real end of available trading history (not delisted mid-window, no missing days a
      calendar check would expect). False means the caller detected a genuine gap — any
      outcome that would otherwise rely on "we ran out of data" (held_to_close, or a target
      leg whose runner never resolved) is downgraded to no_bars instead of reported, per
      method requirement #4 (never fabricate a bar / never silently treat a coverage gap as
      a real close). A trade that reaches a confirmed 'stopped' close is unaffected — that
      determination doesn't depend on data past the point of the touch.
    """
    entry_bars = entry_bars or []
    daily_bars = daily_bars or []

    if not orb_bar or orb_bar.get("high") is None or orb_bar.get("low") is None:
        return TradeResult(ticker, date, "no_bars", None, None, detail="missing_orb_bar")

    orb_high = float(orb_bar["high"])
    orb_low = float(orb_bar["low"])
    if orb_high <= orb_low:
        return TradeResult(ticker, date, "no_bars", None, None, orb_high=orb_high,
                            orb_low=orb_low, detail="degenerate_orb_range")

    if not entry_bars:
        return TradeResult(ticker, date, "no_bars", None, None, orb_high=orb_high,
                            orb_low=orb_low, detail="no_bars_after_orb")

    fill_idx, entry = _fill_entry(orb_high, entry_bars)
    if fill_idx is None:
        return TradeResult(ticker, date, "never_triggered", None, None, orb_high=orb_high,
                            orb_low=orb_low, detail="orb_high_not_touched_by_0959")

    r_orb = entry - orb_low
    if r_orb <= 0:
        return TradeResult(ticker, date, "no_bars", None, None, entry=entry,
                            orb_high=orb_high, orb_low=orb_low, detail="degenerate_r_orb")

    hard_stop = 2 * orb_low - orb_high      # ORB-anchored (2026-08-16 change)
    target = entry + 2 * r_orb              # entry-anchored, pinned to the ORIGINAL r_orb
    r_actual = entry - hard_stop            # scored R unit

    fill_bar = entry_bars[fill_idx]
    state = {"partial_taken": False, "last_price": fill_bar["close"]}

    if runner_rule not in RUNNER_RULES:
        raise ValueError(f"replay_trade: unknown runner_rule {runner_rule!r}")
    ctx = runner_ctx or {}
    prior_closes = [float(c) for c in (ctx.get("prior_closes") or [])]
    atr14 = ctx.get("atr14")
    # held-period daily closes (day-0 close onward, appended as walked) + peak of them —
    # the inputs the daily runner rules read. Untouched by the default rule.
    held = {"closes": [], "peak": None}
    rs = {"post_sessions": 0, "exit_price": None, "exit_kind": None, "exit_gap_open": None}
    _floor = entry if runner_rule in ("breakeven", "live_trail_be") else hard_stop

    def _sma(closes, w):
        return sum(closes[-w:]) / w if len(closes) >= w else None

    def _held_append(close):
        held["closes"].append(close)
        held["peak"] = close if held["peak"] is None else max(held["peak"], close)

    def _touch_level(is_daily: bool) -> float:
        lvl = _floor
        if not is_daily:
            return lvl          # day-0 minutes: only the resting stop order acts intraday
        if runner_rule in ("atr1", "atr2") and atr14 and held["peak"] is not None:
            k = 1.0 if runner_rule == "atr1" else 2.0
            lvl = max(lvl, held["peak"] - k * atr14)   # peak through the PRIOR session
        if runner_rule in ("sma10_touch", "sma20_touch"):
            w = 10 if runner_rule == "sma10_touch" else 20
            s = _sma(prior_closes + held["closes"], w)  # through the PRIOR session
            if s is not None:
                lvl = max(lvl, s)
        return lvl

    def walk(bars, is_daily: bool, sess: dict):
        """Sequential first-touch walk. Returns 'stop' (full stop pre-partial),
        'runner_exit' (post-partial exit, price in rs), or None (exhausted)."""
        for bar in bars:
            if is_daily:
                sess["n"] += 1
                if sess["n"] > horizon_sessions:
                    return None
            lo, hi = bar["low"], bar["high"]
            if not state["partial_taken"]:
                state["last_price"] = bar["close"]
                if lo <= hard_stop:
                    # stop-first tie-break on a bar spanning both (spec §5)
                    return "stop"
                if hi >= target:
                    state["partial_taken"] = True
                    rs["post_sessions"] = 0     # the partial bar is session 0
                if is_daily:
                    _held_append(bar["close"])
                continue
            # ── post-partial: the runner rule governs ──
            if is_daily:
                rs["post_sessions"] += 1
            state["last_price"] = bar["close"]
            lvl = _touch_level(is_daily)
            if lo <= lvl:
                px = lvl
                if (gap_fill_at_open and is_daily and bar.get("open") is not None
                        and bar["open"] < lvl):
                    px = bar["open"]
                rs["exit_price"], rs["exit_kind"] = px, "touch"
                if is_daily and bar.get("open") is not None and bar["open"] < lvl:
                    rs["exit_gap_open"] = bar["open"]
                return "runner_exit"
            if not is_daily:
                continue
            _held_append(bar["close"])
            c = bar["close"]
            if runner_rule in ("sma10", "sma20", "live_trail_be"):
                tc = prior_closes + held["closes"]   # includes today (live append-then-check)
                if runner_rule == "sma10":
                    s = _sma(tc, 10)
                elif runner_rule == "sma20":
                    s = _sma(tc, 20)
                else:
                    s10, s20 = _sma(tc, 10), _sma(tc, 20)
                    if s20 is not None:
                        s = s10 if (s10 is not None and s10 > s20) else s20
                    else:
                        s = s10
                if s is not None and c < s:
                    rs["exit_price"], rs["exit_kind"] = c, "close_trail"
                    return "runner_exit"
            elif runner_rule in ("gb25", "gb50"):
                keep = 0.75 if runner_rule == "gb25" else 0.50
                if held["peak"] is not None and held["peak"] > entry:
                    gbf = entry + keep * (held["peak"] - entry)
                    if c < gbf:
                        rs["exit_price"], rs["exit_kind"] = c, "close_giveback"
                        return "runner_exit"
            elif runner_rule in ("t3", "t5", "t10", "t20"):
                if rs["post_sessions"] >= int(runner_rule[1:]):
                    rs["exit_price"], rs["exit_kind"] = c, "time_close"
                    return "runner_exit"
        return None

    sess = {"n": 0}
    remaining_day0 = entry_bars[fill_idx + 1:]
    result = walk(remaining_day0, is_daily=False, sess=sess)
    ran_out_of_daily_data = False
    if result is None:
        # day-0 → daily seam: the entry day's official close joins the held-close series
        # (the stock's SMA/peak exist regardless of which bar stream we walked it on).
        d0c = ctx.get("day0_close")
        _held_append(float(d0c) if d0c is not None else state["last_price"])
        result = walk(daily_bars, is_daily=True, sess=sess)
        if result is None and len(daily_bars) < horizon_sessions:
            # exhausted every daily bar we were given, short of the horizon cap
            ran_out_of_daily_data = True

    if result == "stop":
        return TradeResult(ticker, date, "stopped", -1.0, r_orb, entry, orb_high, orb_low,
                            hard_stop, target)

    if result == "runner_exit":
        runner_r = (rs["exit_price"] - entry) / r_actual
        r = PARTIAL_FRACTION * 1.0 + (1 - PARTIAL_FRACTION) * runner_r
        detail = ("breakeven_stop_after_partial"
                  if runner_rule == "breakeven" and rs["exit_kind"] == "touch"
                  else f"runner_{rs['exit_kind']}")
        if rs["exit_gap_open"] is not None:
            detail += "|gap_open"
        return TradeResult(ticker, date, "target", r, r_orb, entry, orb_high, orb_low,
                            hard_stop, target, detail=detail)

    if not coverage_ok and ran_out_of_daily_data:
        return TradeResult(ticker, date, "no_bars", None, r_orb, entry, orb_high, orb_low,
                            hard_stop, target, detail="coverage_gap_before_resolution")

    if state["partial_taken"]:
        runner_r = (state["last_price"] - entry) / r_actual
        r = PARTIAL_FRACTION * 1.0 + (1 - PARTIAL_FRACTION) * runner_r
        return TradeResult(ticker, date, "target", r, r_orb, entry, orb_high, orb_low,
                            hard_stop, target, detail="held_to_close_after_partial")

    r = (state["last_price"] - entry) / r_actual
    return TradeResult(ticker, date, "held_to_close", r, r_orb, entry, orb_high, orb_low,
                        hard_stop, target)


# ═══════════════════════════════════════════════════════════════════════════════════════
# SELF-TESTS — synthetic bars, no DB. These are the correctness proof; run directly:
#   python scripts/probes/_bt_replay.py
# ═══════════════════════════════════════════════════════════════════════════════════════

def _bar(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c}


# Fixed geometry used by every synthetic test: orb_high=100, orb_low=90 -> R_orb=10,
# entry=100 (fill model), hard_stop=80, target=120, r_actual=20.
_ORB = {"high": 100.0, "low": 90.0}
_FILL_BAR = _bar(98, 102, 97, 99)   # open<=100, high>=100 -> fills at 100


def _approx(a, b, tol=1e-9):
    return abs(a - b) <= tol


def _run_self_tests(replay=replay_trade):
    results = {}

    # 1. stop-first: fills, then stops, target never in play.
    bars = [_FILL_BAR, _bar(85, 90, 75, 80)]
    r = replay("T1", "2026-01-01", _ORB, bars, [])
    results["stop_first"] = (r.reason == "stopped" and _approx(r.r_multiple, -1.0))

    # 2. target-first, no further bars: partial fires, runner marked at same bar's close.
    bars = [_FILL_BAR, _bar(115, 122, 110, 120)]
    r = replay("T2", "2026-01-01", _ORB, bars, [])
    expected = PARTIAL_FRACTION * 1.0 + (1 - PARTIAL_FRACTION) * ((120 - 100) / 20)
    results["target_first"] = (r.reason == "target" and _approx(r.r_multiple, expected))

    # 3. never-triggered: orb_high (100) never touched.
    bars = [_bar(95, 99, 90, 97), _bar(96, 98.5, 94, 96)]
    r = replay("T3", "2026-01-01", _ORB, bars, [])
    results["never_triggered"] = (r.reason == "never_triggered" and r.r_multiple is None)

    # 4. order matters — SAME two bars, reordered. bar_up touches target (low stays well
    # above the hard stop); bar_down breaches the hard stop deeply (75 < 80).
    bar_up = _bar(115, 125, 113, 120)
    bar_down = _bar(95, 99, 75, 80)
    # 4a. stop-before-target: full stop, target never considered.
    r_a = replay("T4a", "2026-01-01", _ORB, [_FILL_BAR, bar_down, bar_up], [])
    ok_a = (r_a.reason == "stopped" and _approx(r_a.r_multiple, -1.0))
    # 4b. target-before-stop: partial fires, stop moves to breakeven (100); the SAME
    # bar_down (low=75) then breaches breakeven (75<=100), not the original hard stop.
    r_b = replay("T4b", "2026-01-01", _ORB, [_FILL_BAR, bar_up, bar_down], [])
    expected_b = PARTIAL_FRACTION * 1.0 + (1 - PARTIAL_FRACTION) * 0.0
    ok_b = (r_b.reason == "target" and _approx(r_b.r_multiple, expected_b))
    results["order_matters_same_bars_reordered"] = (ok_a and ok_b)

    # 5. breakeven persistence, isolated from the deep stop: after target, price dips to 90
    # (BELOW breakeven=100 but ABOVE hard_stop=80). Only a live breakeven check catches it.
    bars = [_FILL_BAR, _bar(115, 125, 118, 122), _bar(97, 99, 90, 91)]
    r = replay("T5", "2026-01-01", _ORB, bars, [])
    expected = PARTIAL_FRACTION * 1.0 + (1 - PARTIAL_FRACTION) * 0.0
    results["breakeven_persists_after_partial"] = (r.reason == "target" and _approx(r.r_multiple, expected))

    # 6. held_to_close: never stopped, never targeted, bars exhaust.
    bars = [_FILL_BAR, _bar(101, 104, 99, 105)]
    r = replay("T6", "2026-01-01", _ORB, bars, [])
    expected = (105 - 100) / 20
    results["held_to_close"] = (r.reason == "held_to_close" and _approx(r.r_multiple, expected))

    # 7. stop stays live past day 0 — day-0 ends flat, day 2's daily bar breaches the hard
    # stop (day 1 does not). Confirms the stop isn't only checked intraday on the entry day.
    bars = [_FILL_BAR]
    daily = [
        {"low": 95, "high": 105, "close": 100},   # day 1 — no touch
        {"low": 78, "high": 95, "close": 92},      # day 2 — breaches hard_stop (80)
    ]
    r = replay("T7", "2026-01-01", _ORB, bars, daily)
    results["stop_persists_past_day0"] = (r.reason == "stopped" and _approx(r.r_multiple, -1.0))

    # 8. no_bars — missing ORB bar.
    r = replay("T8", "2026-01-01", None, [_FILL_BAR], [])
    results["no_bars_missing_orb"] = (r.reason == "no_bars" and r.r_multiple is None)

    # 9. no_bars — ORB exists, nothing after it.
    r = replay("T9", "2026-01-01", _ORB, [], [])
    results["no_bars_nothing_after_orb"] = (r.reason == "no_bars" and r.r_multiple is None)

    # 10. coverage_ok=False downgrades an inconclusive multi-day hold to no_bars instead of
    # fabricating held_to_close off a gap.
    bars = [_FILL_BAR]
    daily = [{"low": 95, "high": 105, "close": 100}]   # 1 day, well short of the 40 horizon
    r = replay("T10", "2026-01-01", _ORB, bars, daily, coverage_ok=False)
    results["coverage_gap_downgrades_to_no_bars"] = (r.reason == "no_bars" and r.r_multiple is None)

    return results


def _run_runner_rule_tests():
    """Synthetic proofs for the runner-rule extension. Geometry: orb 100/90 → entry 100,
    hard_stop 80, target 120, r_actual 20. All rules share the identical pre-partial walk."""
    results = {}
    up = _bar(115, 122, 113, 118)                     # fires the +2R partial (hi>=120)
    third = PARTIAL_FRACTION
    two3 = 1 - PARTIAL_FRACTION

    # A. default equivalence — the ENTIRE original battery, runner_rule passed explicitly.
    eq = _run_self_tests(lambda *a, **k: replay_trade(*a, runner_rule="breakeven", **k))
    results["default_rule_reproduces_original_battery"] = all(eq.values())

    # B. hard vs breakeven on the same bars: dip to 90 (below entry, above hard stop).
    daily = [{"low": 90, "high": 110, "close": 95, "open": 105},
             {"low": 79, "high": 96, "close": 85, "open": 95}]
    r_be = replay_trade("B", "2026-01-01", _ORB, [_FILL_BAR, up], daily)
    r_hd = replay_trade("B", "2026-01-01", _ORB, [_FILL_BAR, up], daily, runner_rule="hard")
    results["hard_holds_through_be_touch_then_stops_at_hard"] = (
        _approx(r_be.r_multiple, third) and
        _approx(r_hd.r_multiple, third + two3 * ((80 - 100) / 20)))   # 1/3 - 2/3 = -1/3

    # C. sma10 close-below exits at the close; prior closes make the SMA real from day 1.
    ctx = {"prior_closes": [100.0] * 9, "day0_close": 110.0}
    daily = [{"low": 103, "high": 112, "close": 105, "open": 108},    # sma10=101.5, hold
             {"low": 95, "high": 106, "close": 96, "open": 105}]      # sma10=101.1 → exit @96
    r = replay_trade("C", "2026-01-01", _ORB, [_FILL_BAR, up], daily, runner_rule="sma10",
                     runner_ctx=ctx)
    results["sma10_exits_at_close_below_sma"] = _approx(
        r.r_multiple, third + two3 * ((96 - 100) / 20))

    # D. atr1 chandelier: peak(day0)=110, atr=5 → level 105; day1 low 104 touches → exit @105.
    ctx = {"day0_close": 110.0, "atr14": 5.0}
    daily = [{"low": 104, "high": 112, "close": 111, "open": 108}]
    r = replay_trade("D", "2026-01-01", _ORB, [_FILL_BAR, up], daily, runner_rule="atr1",
                     runner_ctx=ctx)
    results["atr1_touch_exits_at_level"] = _approx(
        r.r_multiple, third + two3 * ((105 - 100) / 20))

    # E. gb50: peak close 120 → floor 110; close 108 < 110 → exit @108.
    ctx = {"day0_close": 120.0}
    daily = [{"low": 107, "high": 121, "close": 108, "open": 118}]
    r = replay_trade("E", "2026-01-01", _ORB, [_FILL_BAR, up], daily, runner_rule="gb50",
                     runner_ctx=ctx)
    results["gb50_exits_at_close_below_floor"] = _approx(
        r.r_multiple, third + two3 * ((108 - 100) / 20))

    # F. t3: exits at the 3rd post-partial session's close (104), floor never touched.
    daily = [{"low": 100.5, "high": 106, "close": 101, "open": 101},
             {"low": 100.5, "high": 106, "close": 102, "open": 102},
             {"low": 100.5, "high": 106, "close": 104, "open": 103},
             {"low": 100.5, "high": 200, "close": 190, "open": 104}]
    r = replay_trade("F", "2026-01-01", _ORB, [_FILL_BAR, up], daily, runner_rule="t3")
    results["t3_exits_at_third_session_close"] = _approx(
        r.r_multiple, third + two3 * ((104 - 100) / 20))

    # G. gap_fill_at_open: hard rule, bar OPENS at 70 below the 80 stop → fills at 70.
    daily = [{"low": 65, "high": 75, "close": 72, "open": 70}]
    r = replay_trade("G", "2026-01-01", _ORB, [_FILL_BAR, up], daily, runner_rule="hard",
                     gap_fill_at_open=True)
    results["gap_open_prices_touch_exit_at_open"] = _approx(
        r.r_multiple, third + two3 * ((70 - 100) / 20))

    # H. live_trail_be: BE floor touch beats the trail when both are in play intraday…
    ctx = {"prior_closes": [100.0] * 19, "day0_close": 110.0}
    daily = [{"low": 99, "high": 112, "close": 108, "open": 108}]     # lo 99 <= entry 100
    r = replay_trade("H", "2026-01-01", _ORB, [_FILL_BAR, up], daily,
                     runner_rule="live_trail_be", runner_ctx=ctx)
    ok_h1 = _approx(r.r_multiple, third)                              # exit at entry, runner 0
    # …and the trail close-exit fires on a close below max(SMA10,SMA20) that stays above BE.
    daily = [{"low": 101, "high": 112, "close": 101.2, "open": 108}]  # sma10≈101.62 > close
    r = replay_trade("H2", "2026-01-01", _ORB, [_FILL_BAR, up], daily,
                     runner_rule="live_trail_be", runner_ctx=ctx)
    ok_h2 = _approx(r.r_multiple, third + two3 * ((101.2 - 100) / 20))
    results["live_trail_be_composes_floor_and_trail"] = ok_h1 and ok_h2

    return results


def _replay_mutated_no_sequence(ticker, date, orb_bar, entry_bars, daily_bars, **kw):
    """MUTATION 1 — breaks the sequential first-touch walk. Reproduces the exact bug named
    in the task brief: `any(low <= stop)` over the whole bar set, ignoring order and ignoring
    whether a partial already moved the stop to breakeven. Should NOT be able to distinguish
    T4a from T4b (same two bars, different order) and should misclassify T5/T4b as 'stopped'."""
    entry_bars = entry_bars or []
    daily_bars = daily_bars or []
    if not orb_bar or not entry_bars:
        return replay_trade(ticker, date, orb_bar, entry_bars, daily_bars, **kw)
    orb_high, orb_low = float(orb_bar["high"]), float(orb_bar["low"])
    fill_idx, entry = _fill_entry(orb_high, entry_bars)
    if fill_idx is None:
        return replay_trade(ticker, date, orb_bar, entry_bars, daily_bars, **kw)
    hard_stop = 2 * orb_low - orb_high
    rest = entry_bars[fill_idx + 1:]
    all_bars = rest + list(daily_bars)
    if any(b["low"] <= hard_stop for b in all_bars):     # <-- the mutation: no order, no breakeven
        return TradeResult(ticker, date, "stopped", -1.0, entry - orb_low, entry, orb_high, orb_low,
                            hard_stop, entry + 2 * (entry - orb_low))
    return replay_trade(ticker, date, orb_bar, entry_bars, daily_bars, **kw)


def _replay_mutated_no_stop_persistence(ticker, date, orb_bar, entry_bars, daily_bars, **kw):
    """MUTATION 2 — breaks breakeven persistence: the stop level used post-partial never
    rises off hard_stop (it "lapses" to the original level instead of tracking breakeven).
    A monkeypatched copy of replay_trade's walk() with `stop_level = hard_stop` hardcoded."""
    entry_bars = entry_bars or []
    daily_bars = daily_bars or []
    if not orb_bar or not entry_bars:
        return replay_trade(ticker, date, orb_bar, entry_bars, daily_bars, **kw)
    orb_high, orb_low = float(orb_bar["high"]), float(orb_bar["low"])
    fill_idx, entry = _fill_entry(orb_high, entry_bars)
    if fill_idx is None:
        return replay_trade(ticker, date, orb_bar, entry_bars, daily_bars, **kw)
    r_orb = entry - orb_low
    hard_stop = 2 * orb_low - orb_high
    target = entry + 2 * r_orb
    r_actual = entry - hard_stop
    state = {"partial_taken": False, "last_price": entry_bars[fill_idx]["close"]}

    def walk(bars, is_daily):
        sessions = 0
        for bar in bars:
            if is_daily:
                sessions += 1
                if sessions > kw.get("horizon_sessions", HORIZON_SESSIONS):
                    return None
            lo, hi = bar["low"], bar["high"]
            stop_level = hard_stop                       # <-- the mutation: never rises to breakeven
            hit_stop = lo <= stop_level
            hit_target = (not state["partial_taken"]) and hi >= target
            state["last_price"] = bar["close"]
            if hit_stop:
                return "stop"
            if hit_target:
                state["partial_taken"] = True
                continue
        return None

    result = walk(entry_bars[fill_idx + 1:], False)
    if result is None:
        result = walk(daily_bars, True)
    if result == "stop":
        if state["partial_taken"]:
            r = PARTIAL_FRACTION * 1.0
            return TradeResult(ticker, date, "target", r, r_orb, entry, orb_high, orb_low, hard_stop, target)
        return TradeResult(ticker, date, "stopped", -1.0, r_orb, entry, orb_high, orb_low, hard_stop, target)
    if state["partial_taken"]:
        runner_r = (state["last_price"] - entry) / r_actual
        r = PARTIAL_FRACTION * 1.0 + (1 - PARTIAL_FRACTION) * runner_r
        return TradeResult(ticker, date, "target", r, r_orb, entry, orb_high, orb_low, hard_stop, target)
    r = (state["last_price"] - entry) / r_actual
    return TradeResult(ticker, date, "held_to_close", r, r_orb, entry, orb_high, orb_low, hard_stop, target)


def _run_mutation_tests():
    baseline = _run_self_tests(replay_trade)
    print("baseline (correct implementation):")
    for name, ok in baseline.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    assert all(baseline.values()), "self-tests must be green before mutation testing means anything"

    print("\nmutation 1 — sequence walk replaced with any(low<=hard_stop), order/breakeven ignored:")
    mutated = _run_self_tests(_replay_mutated_no_sequence)
    caught = [n for n in ("order_matters_same_bars_reordered", "breakeven_persists_after_partial",
                           "target_first")
              if mutated.get(n) is False]
    for name, ok in mutated.items():
        flag = "still green (unaffected)" if ok else "RED — mutation caught here"
        print(f"  {name}: {flag}")
    assert caught, "mutation 1 should have reddened at least one order/persistence test"

    print("\nmutation 2 — post-partial stop hardcoded to hard_stop, never rises to breakeven:")
    mutated = _run_self_tests(_replay_mutated_no_stop_persistence)
    caught2 = [n for n in ("breakeven_persists_after_partial", "order_matters_same_bars_reordered")
               if mutated.get(n) is False]
    for name, ok in mutated.items():
        flag = "still green (unaffected)" if ok else "RED — mutation caught here"
        print(f"  {name}: {flag}")
    assert caught2, "mutation 2 should have reddened the breakeven-persistence test"

    print(f"\nmutation 1 caught by: {caught}")
    print(f"mutation 2 caught by: {caught2}")


if __name__ == "__main__":
    _run_mutation_tests()
    print("\nrunner-rule extension tests:")
    rr = _run_runner_rule_tests()
    for name, ok in rr.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    assert all(rr.values()), "runner-rule tests must be green"
    print("\nAll self-tests pass; both mutations were caught; runner-rule tests green.")
