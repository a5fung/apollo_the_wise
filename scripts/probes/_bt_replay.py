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

    def walk(bars, is_daily: bool):
        """Sequential first-touch walk. Returns 'stop' (terminal, full or breakeven) or None
        (exhausted this bar list without a stop touch — caller decides what that means)."""
        sessions = 0
        for bar in bars:
            if is_daily:
                sessions += 1
                if sessions > horizon_sessions:
                    return None
            lo, hi = bar["low"], bar["high"]
            stop_level = entry if state["partial_taken"] else hard_stop
            hit_stop = lo <= stop_level
            hit_target = (not state["partial_taken"]) and hi >= target
            state["last_price"] = bar["close"]
            if hit_stop:
                # stop-first tie-break on a bar spanning both (spec §5)
                return "stop"
            if hit_target:
                state["partial_taken"] = True
                continue
        return None

    remaining_day0 = entry_bars[fill_idx + 1:]
    result = walk(remaining_day0, is_daily=False)
    ran_out_of_daily_data = False
    if result is None:
        result = walk(daily_bars, is_daily=True)
        if result is None and len(daily_bars) < horizon_sessions:
            # exhausted every daily bar we were given, short of the horizon cap
            ran_out_of_daily_data = True

    if result == "stop":
        if state["partial_taken"]:
            r = PARTIAL_FRACTION * 1.0 + (1 - PARTIAL_FRACTION) * 0.0
            return TradeResult(ticker, date, "target", r, r_orb, entry, orb_high, orb_low,
                                hard_stop, target, detail="breakeven_stop_after_partial")
        return TradeResult(ticker, date, "stopped", -1.0, r_orb, entry, orb_high, orb_low,
                            hard_stop, target)

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
    print("\nAll self-tests pass; both mutations were caught.")
