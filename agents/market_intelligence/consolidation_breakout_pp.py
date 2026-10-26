"""#705 (c) - the Consolidation Breakout forward recorder's `pp` and `A` exit arms (PURE, no I/O, no order path).

`pp` is HIS carried exit (operator ruling 2026-10-19, `docs/setups/consolidation_breakout.md` change log): sell a third at
+2R on the breakout day or later, OR at the close of session 3 ONLY WHEN THAT CLOSE IS ABOVE THE FILL; after a third the stop
moves to the fill (cost); the rest trails the first close under the 20-day average, filled at the next open; the stall cut
(no +1R by the close of session 3 -> everything sold at that close) stays. `A` is the control it replaced: the same walk with
the session-3 third taken whatever the close (it IS `cb.CUT_EXIT_ARMS["c3_p33_t20_cut3"]`, proved equal event for event).

WHY THIS IS A SEPARATE MODULE. `pp` is not expressible with the `cb.Arm` flags (`partial_if_profit` is forbidden with a
combo partial, and the pp trail is live from session 3 whether or not the third sold), and `consolidation_breakout.py` is
HARD-PINNED by sha256 (`runner.EXITPB_MODULE_SHA`, `pp`'s own registration): editing it would make the registered exit read
refuse to open. So the walk lives here, as a faithful port of the runner's `exitpb_walk` / `exitpb_walk_arms` restricted to
the two arms the recorder writes. `tests/test_cb_pp_recorder.py` proves the port equal to the RUNNER's registered walk (the
definition of `pp`) and to `cb.walk_exit` on `A`, on random paths, so the recorder cannot drift from what was registered.

DAY 0. `pp` and `A` need the breakout day on the MINUTES (a +2R touch before the stop, the highest minute high for the stall
cut). The shadow's exit step has no minutes, so the entry step computes the day-0 facts ONCE, from the minutes it already
holds for the fill, and stores them on the entry row (`day0_pp`, JSONB; `day0_facts`). Both arms use the entry-price stop
rule, so ONE day-0 walk (breakeven on) serves both - exactly as `exitpb_walk_arms` keys it.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from agents.market_intelligence import consolidation_breakout as cb

A_ARM = "A"
PP_ARM = "pp"
PP_ARMS = (A_ARM, PP_ARM)                       # the names written to `mi_consolidation_breakout_exit.arm`
DAY0_FACTS_VERSION = 1
LEG_FIRST = 3                                   # the session leg's session (and the session the pp trail goes live)

# The mechanics both arms share = the P5 primary (1/3; the +2R leg; the session-3 leg; the 20-day trail at the next open;
# the +1R-by-session-3 cut). Read from the module's own arm so a change there cannot leave this port on stale numbers.
_BASE = cb.CUT_EXIT_ARMS[cb.P5_PRIMARY_ARM]

# session rule per arm: `always` = the session-3 close whatever the price (A); `profit_only` = only on a close ABOVE the fill (pp)
SESSION_RULE = {A_ARM: "always", PP_ARM: "profit_only"}

_DAY0_KEYS = ("stopped", "exit_price", "exit_minute", "partial_price", "partial_minute", "stop_in_force")


def session_leg(rule: str, j: int, close_j: float, fill: float) -> bool:
    """Does the session leg sell the third at the close of session j?"""
    if rule == "always":
        return j == LEG_FIRST
    if rule == "profit_only":
        return j == LEG_FIRST and close_j > fill
    raise ValueError(f"session_leg: unknown session rule {rule!r}")


# ── day 0 ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def no_day0_facts() -> dict:
    """The day-0 facts of a fill that has NO minutes after it (the daily `close` variant: the entry IS the session's close).
    Nothing was stopped, nothing sold, nothing reached on day 0."""
    return {"v": DAY0_FACTS_VERSION, "stopped": False, "exit_price": None, "exit_minute": None,
            "partial_price": None, "partial_minute": None, "stop_in_force": None, "peak": None}


def day0_facts(minutes: "cb.MinuteBars", *, fill: float, stop: float, fill_minute: int) -> dict:
    """The breakout day of a filled minute entry for the pp family, as plain JSON: `cb.day0_walk_target` (the minutes after the
    fill against the stop AND the +2R target, breakeven on - both arms use the entry-price stop rule) and `cb.day0_peak_high`
    (the highest minute high after the fill; None when no minute follows it)."""
    target = float(fill) + float(_BASE.partial_r) * (float(fill) - float(stop))
    d0 = cb.day0_walk_target(minutes, fill=float(fill), fill_minute=int(fill_minute), stop=float(stop), target=target,
                             partial_frac=float(_BASE.partial_frac), breakeven=True)
    peak = cb.day0_peak_high(minutes, int(fill_minute))
    out = {"v": DAY0_FACTS_VERSION, "stopped": bool(d0["stopped"]), "peak": float(peak) if math.isfinite(peak) else None}
    for k in _DAY0_KEYS[1:]:
        v = d0.get(k)
        out[k] = None if v is None else (int(v) if k.endswith("minute") else float(v))
    return out


def _d0_from_facts(facts: dict) -> dict:
    if not isinstance(facts, dict) or facts.get("v") != DAY0_FACTS_VERSION or "stopped" not in facts:
        raise ValueError(f"day0_pp facts are not a version-{DAY0_FACTS_VERSION} record: {facts!r}")
    return {k: facts.get(k) for k in _DAY0_KEYS}


# ── the walk ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _stop_after_third(stop_now: float, fill: float) -> float:
    """Both arms: the stop rests at the fill (cost) from the NEXT session after any third (max with the stop in force)."""
    return max(stop_now, fill)


def walk_pp(*, fill: float, stop: float, closes_before, fwd: "cb.DailyBars", arm_name: str, adr20: float,
            horizon: int = cb.EXIT_HORIZON, day0_partial_px: Optional[float] = None, day0_peak: Optional[float] = None) -> dict:
    """The daily walk of `A` / `pp` from E+1, a faithful port of the runner's `exitpb_walk` for the entry-price stop rule. Per
    session the order is: the gap partial, the stop in force BEFORE the session, the +2R leg, the reach / cut test, the
    session leg (`session_leg`), the trail. After ANY third the stop rests at the fill from the next session, and the walk emits
    `(j, "stop_to", level, 0.0)` (and `(j, "be_above_close", close, 0.0)` when that level sits above the session's close).
    The trail: `A` = live once a third sold (the module's own expression); `pp` = live from session 3 whether or not the third
    sold, so the session-3 close is itself tested against the 20-day and a signal sells EVERYTHING left at the next open.
    `closes_before[-1]` MUST be E's close (the module's caller contract). `day0_partial_px` = the day-0 +2R third already taken;
    `day0_peak` = day 0's highest minute high after the fill (-inf when none)."""
    rule = SESSION_RULE[arm_name]
    profit_gated = rule != "always"
    adr20 = cb._check_adr(adr20)
    risk = float(fill) - float(stop)
    if not risk > 0:
        raise ValueError(f"walk_pp: stop {stop} must be below fill {fill}")
    base = _BASE
    fill, stop0 = float(fill), float(stop)
    o, h, l, c = fwd.o, fwd.h, fwd.l, fwd.c
    n = len(c)
    events: list = []
    pnl = 0.0
    last_before = float(np.asarray(closes_before, dtype=float)[-1]) if len(closes_before) else None
    cb_arr = np.asarray(closes_before, dtype=float)
    trail_n = int(base.trail_sma)
    tail = cb_arr[-trail_n:]
    n_before = len(tail)
    cs = np.concatenate(([0.0], np.cumsum(np.concatenate((tail, c)))))
    remaining = 1.0
    stop_now = stop0
    partial_done = False
    frac = base.partial_frac
    target = fill + float(base.partial_r) * risk

    def _after_third(j: int, close_j: float) -> None:
        nonlocal stop_now
        stop_now = _stop_after_third(stop_now, fill)
        events.append((j, "stop_to", stop_now, 0.0))
        if stop_now > close_j:                  # the session closed under the resting stop: tomorrow's open takes it
            events.append((j, "be_above_close", close_j, 0.0))

    def _book_r_partial(j: int, px: float, close_j: float) -> None:
        nonlocal pnl, remaining, partial_done
        events.append((j, "partial_r", px, frac))
        pnl += (px - fill) * frac
        remaining -= frac
        partial_done = True
        _after_third(j, close_j)

    if day0_partial_px is not None:
        if last_before is None:
            raise ValueError("walk_pp: day0_partial_px needs E's close in closes_before")
        _book_r_partial(0, float(day0_partial_px), last_before)
    cut_level = fill + float(base.stall_cut_r) * risk
    reached = day0_partial_px is not None and float(day0_partial_px) >= cut_level
    if not reached:
        if day0_peak is None:
            raise ValueError("walk_pp: the stall cut needs day0_peak (day 0's highest minute high after the fill)")
        reached = float(day0_peak) >= cut_level
    cut_session = int(base.stall_cut_session)
    for j in range(1, min(int(horizon), n) + 1):
        oj, lj, cj = float(o[j - 1]), float(l[j - 1]), float(c[j - 1])
        stop_j = stop_now                       # the stop this session is judged against (a third today moves it from tomorrow)
        gap_px = oj if (not partial_done and oj >= target) else None
        if oj <= stop_j or lj <= stop_j:        # 1. the stop (a gap-open third first: its open came before the low)
            if gap_px is not None:
                events.append((j, "partial_r", gap_px, frac))
                pnl += (gap_px - fill) * frac
                remaining -= frac
            px = oj if oj <= stop_j else stop_j
            events.append((j, "stop_gap" if oj < stop_j else "stop", px, remaining))
            pnl += (px - fill) * remaining
            return cb._outcome("stopped", pnl, risk, fill, adr20, j, events)
        if gap_px is not None:                  # 1b. the +2R leg: at the open when it gapped above, else AT the target
            _book_r_partial(j, gap_px, cj)
        elif not partial_done and float(h[j - 1]) >= target:
            _book_r_partial(j, target, cj)
        if not reached and j <= cut_session and float(h[j - 1]) >= cut_level:    # 1c. the reach test, then the cut
            reached = True
        if not reached and j == cut_session:
            events.append((j, "cut", cj, remaining))
            pnl += (cj - fill) * remaining
            return cb._outcome("time_exit", pnl, risk, fill, adr20, j, events)
        if not partial_done and session_leg(rule, j, cj, fill):      # 2. the session leg, at the close
            events.append((j, "partial", cj, frac))
            pnl += (cj - fill) * frac
            remaining -= frac
            partial_done = True
            _after_third(j, cj)
        trail_live = partial_done if not profit_gated else (partial_done or j >= LEG_FIRST)   # 3. the trail
        if trail_live:
            pos = n_before + j
            if pos - trail_n >= 0:
                sma = (cs[pos] - cs[pos - trail_n]) / trail_n
                if cj < sma and j < n:          # the remainder sells at the next open; no next open falls through to the mark
                    opx = float(o[j])
                    events.append((j + 1, "trail", opx, remaining))
                    pnl += (opx - fill) * remaining
                    return cb._outcome("censored" if j == int(horizon) else "trailed", pnl, risk, fill, adr20, j + 1, events)
        if j == int(horizon):                   # 4. the horizon
            events.append((j, "mark", cj, remaining))
            pnl += (cj - fill) * remaining
            return cb._outcome("censored", pnl, risk, fill, adr20, j, events)
    return cb._degraded(c, n, remaining, pnl, fill, risk, adr20, events, last_before)


def walk_pp_arms(entry: dict, facts: dict, *, closes_before, fwd: "cb.DailyBars", adr20: float,
                 horizon: int = cb.EXIT_HORIZON, arms=PP_ARMS) -> dict:
    """{arm name: `walk_exit`-shaped result} for ONE filled entry {fill, stop} over `arms` (default both), from the stored day-0
    `facts` (`day0_facts` / `no_day0_facts`) - the same dispatch as the runner's `exitpb_walk_arms`: a day 0 that left nothing
    (`stopped`) is booked once by `cb.day0_target_to_outcome` (a day-0 third then carries its `stop_to` event), otherwise the
    daily walk starts from the day-0 third (if any) and the day-0 peak."""
    adr20 = cb._check_adr(adr20)
    d0 = _d0_from_facts(facts)
    base = _BASE
    out = {}
    for name in arms:
        if d0["stopped"]:
            res = cb.day0_target_to_outcome(entry, d0, adr20, base.partial_frac)
            if d0.get("partial_price") is not None:
                res["events"] = res["events"][:1] + [(0, "stop_to", float(d0["stop_in_force"]), 0.0)] + res["events"][1:]
            out[name] = res
            continue
        peak = facts.get("peak")
        out[name] = walk_pp(fill=float(entry["fill"]), stop=float(entry["stop"]), closes_before=closes_before, fwd=fwd,
                            arm_name=name, adr20=adr20, horizon=horizon, day0_partial_px=d0["partial_price"],
                            day0_peak=(float("-inf") if peak is None else float(peak)))
    return out
