"""Breakout v1 PAPER — the `pp` exit's decisions for the live jobs (phase 2 part B, build 2026-10-30). PURE: no I/O.

THE RULE (his, `docs/setups/consolidation_breakout.md` 2026-10-19 ruling, "exit = the pp arm" 2026-10-28; the definition
is `consolidation_breakout_pp.walk_pp`, arm `pp`, and this module is held equal to it event for event by
`tests/test_breakout_pp_exit.py`):
  * sell a third at +2R (fill + 2 x (fill - stop)) from the breakout day on — AT the target, or at the open when a session
    opened above it;
  * else sell a third at the close of session 3 ONLY WHEN THAT CLOSE IS ABOVE THE FILL;
  * after any third the stop rests at the fill (cost);
  * the rest sells at the next open after the first close under the 20-day simple average — live from session 3 whether or
    not a third sold, and from the session of a +2R third before that;
  * the stall cut: no high at fill + 1R by the close of session 3 -> everything sold at that close.
  "A third sold" is what ACTUALLY FILLED (his ruling 2026-10-29, `third_sold`): the row's `partial_taken`, never a high at
  +2R — a +2R touch whose resting limit did not fill starts no trail and leaves the session-3 third in place (never sold
  beside a still-resting +2R third: `session3_decision`'s 'third_resting').

WHO DOES WHAT LIVE (the mapping; `breakout_pp_exit.py` is the I/O half):
  * the +2R third, any session incl. the breakout day -> `order_manager.scan_profit_triggers` (5-minute poll of the minute
    highs since the fill; R = entry - hard_stop because `breakout_v1` is not ORB-framed; the global multiple 2.0), which
    sells through `execute_partial_exit` (the stop moves to breakeven = the fill in the same call);
  * the stall cut and the session-3 third -> `live_tracker.run_partial_exits` (15:45 ET, on session 3: `session3_decision`);
  * the 20-day trail -> `live_tracker.update_open_positions_live` (16:45 ET, on the settled close: `trail_decision`), which
    MARKS the trade; `order_manager.run_breakout_pp_open_sales` (19:02 ET) sends the PAPER DAY market sale that fills at
    the next open (#687 option (c)'s vehicle);
  * the stop -> the broker's resting stop leg (the day's low at the fill, then the fill after a third).

WHY THE NUMBERS ARE COPIES, NOT IMPORTS: this module is loaded by the EXECUTION container (live_tracker imports it), and
`consolidation_breakout` / `consolidation_breakout_pp` must stay out of that container (`tests/test_cb_shadow.py` pins it;
the deploy-scope gate derives the list). So the five numbers and the day-0 walk are ported here and the test pins each to
`consolidation_breakout_pp._BASE` / `LEG_FIRST` / `day0_facts` on random inputs. A change there fails that test.
"""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

# ── the pp arm's numbers (copies of consolidation_breakout_pp._BASE = cb.CUT_EXIT_ARMS["c3_p33_t20_cut3"]; test-pinned) ──
PARTIAL_FRAC = 1 / 3          # the third
PARTIAL_R = 2.0               # +2R
STALL_CUT_R = 1.0             # the stall cut's reach level: fill + 1R
STALL_CUT_SESSION = 3         # ... by the close of session 3
LEG_SESSION = 3               # the session-3 third (only on a close above the fill); the trail is live from here
TRAIL_SMA = 20                # the 20-day simple average; a close under it sells the rest at the next open
DAY0_FACTS_VERSION = 1        # = consolidation_breakout_pp.DAY0_FACTS_VERSION

_DAY0_KEYS = ("stopped", "exit_price", "exit_minute", "partial_price", "partial_minute", "stop_in_force")


# ── levels ────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def target_price(fill: float, stop: float) -> float:
    """+2R: fill + 2 x (fill - stop) — the same expression `consolidation_breakout_pp.day0_facts` / `walk_pp` use."""
    return float(fill) + float(PARTIAL_R) * (float(fill) - float(stop))


def cut_level(fill: float, stop: float) -> float:
    """The stall cut's reach level, fill + 1R (`walk_pp`'s `cut_level`)."""
    fill, stop = float(fill), float(stop)
    return fill + float(STALL_CUT_R) * (fill - stop)


def stop_after_third(stop_now: float, fill: float) -> float:
    """After ANY third the stop rests at the fill (cost): max with the stop in force."""
    return max(float(stop_now), float(fill))


# ── day 0: a port of consolidation_breakout_pp.day0_facts (cb.day0_walk_target + cb.day0_peak_high) ─────────────────────
def day0_facts(minutes: Sequence[tuple], *, fill: float, stop: float, fill_minute: int) -> dict:
    """The breakout day's facts, as plain JSON, from the day's minute bars `minutes` = [(minute, open, high, low), ...]
    (minute = minutes since 09:30 ET, oldest first). The minutes AFTER the fill minute are walked against the stop AND the
    +2R target, breakeven on: per minute a minute that OPENS at or above the target sells the third at its open; a low at
    the stop (or an open under it) ends the trade (at the open when it gapped under) — so a minute touching both books the
    third at its open only when it OPENED above the target, else the stop; else a high at the target sells the third AT
    the target; after the third the stop is max(stop, fill) from the NEXT minute. `peak` = the highest minute high after
    the fill minute (None when no minute follows it). Equal to `consolidation_breakout_pp.day0_facts` (test-pinned)."""
    stop_now, fill = float(stop), float(fill)
    target = target_price(fill, stop)
    if not stop_now < fill < target:
        raise ValueError(f"day0_walk_target: need stop {stop} < fill {fill} < target {target}")
    fm = int(fill_minute)
    after = [(int(m), float(o), float(h), float(lo)) for (m, o, h, lo) in minutes if int(m) > fm]
    res = {"stopped": False, "exit_price": None, "exit_minute": None, "partial_price": None, "partial_minute": None,
           "stop_in_force": None}
    partial_done = False
    for m, op, hi, lo in after:
        gap_px = op if (not partial_done and op >= target) else None
        if lo <= stop_now or op < stop_now:
            if gap_px is not None:
                res.update(partial_price=gap_px, partial_minute=m)
            res.update(stopped=True, exit_price=(op if op < stop_now else stop_now), exit_minute=m, stop_in_force=stop_now)
            break
        if gap_px is not None or (not partial_done and hi >= target):
            res.update(partial_price=(gap_px if gap_px is not None else target), partial_minute=m)
            partial_done = True
            stop_now = max(stop_now, fill)
    peak = max((h for _m, _o, h, _l in after), default=float("-inf"))
    out = {"v": DAY0_FACTS_VERSION, "stopped": bool(res["stopped"]), "peak": float(peak) if math.isfinite(peak) else None}
    for k in _DAY0_KEYS[1:]:
        v = res.get(k)
        out[k] = None if v is None else (int(v) if k.endswith("minute") else float(v))
    return out


def valid_day0_facts(facts) -> bool:
    return isinstance(facts, dict) and facts.get("v") == DAY0_FACTS_VERSION and "stopped" in facts


# ── the sessions ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def bar_et_date(bar: dict) -> Optional[date]:
    """The ET date of a Polygon daily aggregate (`t` = ms epoch)."""
    ts = bar.get("t")
    if ts is None:
        return None
    return datetime.fromtimestamp(float(ts) / 1000.0, tz=_ET).date()


def _ohlc(bar: dict) -> dict:
    return {"o": float(bar["o"]), "h": float(bar["h"]), "l": float(bar["l"]), "c": float(bar["c"])}


def split_sessions(history: Sequence[dict], *, alert_date: date, today: date,
                   today_bar: Optional[dict]) -> tuple[list[float], list[dict]]:
    """(closes_before, fwd) as `walk_pp` reads them: `closes_before` = the stock's daily closes up to AND INCLUDING the
    breakout day (E's close last — the walk's caller contract); `fwd` = the sessions after it through today, oldest first,
    each {o, h, l, c}. `history` = daily bars from before the breakout day through (at most) today; any bar dated today is
    replaced by `today_bar` (the 15:45 forming bar, or the settled 16:45 bar) so both jobs read the same today. Bars with a
    missing o/h/l/c or no date are dropped. Session j (1-based) = fwd[j - 1]."""
    closes_before: list[float] = []
    fwd: list[dict] = []
    for b in history or []:
        d = bar_et_date(b)
        if d is None or d >= today or any(b.get(k) is None for k in ("o", "h", "l", "c")):
            continue
        if d <= alert_date:
            closes_before.append(float(b["c"]))
        else:
            fwd.append(_ohlc(b))
    if today > alert_date and today_bar and all(today_bar.get(k) is not None for k in ("o", "h", "l", "c")):
        fwd.append(_ohlc(today_bar))
    return closes_before, fwd


# ── the decisions ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def third_sold(*, partial_taken: bool) -> bool:
    """Has a third ACTUALLY been sold? The row's truth only (`mi_live_trades.partial_taken`, which flips TRUE when a partial
    exit FILLS — `order_manager.finalize_partial_exit`), never a price touching +2R.

    HIS RULING 2026-10-29 ("Go with rec", the first third at +2R): follow what actually filled. On the paper book the +2R
    third is a resting limit (an OCO) at the target placed by the 5-minute poll AFTER a minute high touched it, so a touch
    the limit does not fill is NOT a third sold — the 20-day trail does not start early and the session-3 third still
    applies. `walk_pp` (daily bars) books the third at the touch; on a path where the limit filled at the touch the two
    agree event for event, on a path where it did not, live departs from the walk by design
    (`tests/test_breakout_pp_exit.py`, the defined divergence; `docs/setups/consolidation_breakout.md` difference 10).
    The day-0 facts' `partial_price` is the minute walk's MODELLED third — it no longer counts as a sale either."""
    return bool(partial_taken)


def reached_plus_1r(*, fill: float, stop: float, day0: dict, fwd: Sequence[dict]) -> bool:
    """The stall cut's reach test through session `len(fwd)` (capped at session 3): a high at fill + 1R on the breakout day
    after the fill (`day0.peak`, or a day-0 third at or above it) or on sessions 1..3."""
    lvl = cut_level(fill, stop)
    pp = day0.get("partial_price")
    if pp is not None and float(pp) >= lvl:
        return True
    peak = day0.get("peak")
    if peak is not None and float(peak) >= lvl:
        return True
    return any(float(b["h"]) >= lvl for b in list(fwd)[:STALL_CUT_SESSION])


def session3_decision(*, fill: float, stop: float, day0: dict, fwd: Sequence[dict], partial_taken: bool,
                      third_resting: bool = False) -> Optional[str]:
    """The 15:45 ET decision on session 3 (`len(fwd) == 3`, today's bar last). In the walk's order after the stop and the
    +2R leg: 'cut' (no high at +1R by now -> everything sold at the close) | None (a third already SOLD — `third_sold`) |
    'third_resting' (no third sold yet, but the +2R third is still RESTING at the broker: no second third is sold beside it
    — his ruling 2026-10-29) | 'session_third' (no third yet, none resting, and the close is above the fill) | None. Any
    other session -> None."""
    if len(fwd) != LEG_SESSION:
        return None
    if not reached_plus_1r(fill=fill, stop=stop, day0=day0, fwd=fwd):
        return "cut"
    if third_sold(partial_taken=partial_taken):
        return None
    if float(fwd[-1]["c"]) > float(fill):
        return "third_resting" if third_resting else "session_third"
    return None


def sma_at_last(closes_before: Sequence[float], fwd: Sequence[dict]) -> Optional[float]:
    """The 20-day simple average of the closes ending at the last session in `fwd`, computed EXACTLY as `walk_pp` does
    (the last 20 closes before the entry incl. E's, then the forward closes; a running sum, the difference of two
    prefix sums, / 20) so the comparison with the close is bit-for-bit the walk's. None with fewer than 20 closes."""
    n = int(TRAIL_SMA)
    tail = [float(x) for x in list(closes_before)[-n:]]
    seq = tail + [float(b["c"]) for b in fwd]
    pos = len(seq)
    if pos - n < 0:
        return None
    cs = [0.0]
    acc = 0.0
    for i, x in enumerate(seq):
        acc = x if i == 0 else acc + x          # numpy cumsum: sequential, seeded with the first element
        cs.append(acc)
    return (cs[pos] - cs[pos - n]) / n


def trail_decision(*, closes_before: Sequence[float], fwd: Sequence[dict], partial_taken: bool) -> dict:
    """The 16:45 ET decision on the settled close of session j = len(fwd) >= 1: is the trail live (session 3 on, or a third
    ACTUALLY sold — `third_sold`, the row's `partial_taken`), and did the close settle under the 20-day? ->
    {"j", "trail_live", "sma20", "close", "sell"}. `sell` = the rest sells at the next open."""
    j = len(fwd)
    out = {"j": j, "trail_live": False, "sma20": None, "close": (float(fwd[-1]["c"]) if fwd else None), "sell": False}
    if j < 1:
        return out
    live = j >= LEG_SESSION or third_sold(partial_taken=partial_taken)
    sma = sma_at_last(closes_before, fwd)
    out.update(trail_live=live, sma20=sma, sell=bool(live and sma is not None and float(fwd[-1]["c"]) < sma))
    return out
