"""The FIRST-HOUR-BAR entry walk — pure math shared by two recorders (#482, 2026-10-27).

Lifted out of `book_geometry_arms.py` (where it was written 2026-10-26) so that BOTH its callers
sit on one copy that the deploy gate can see:

  * `book_geometry_arms.run_book_geometry_arms` (market-agent, 18:04 ET) — the hour arms on the
    fills we TOOK;
  * `broker/shadow_orb_tracker.run_shadow_hour_pass` (apollo-execution, 16:50 ET) — the hour entry
    on EVERY ORB alert the 5-minute shadow lane saw (`bar_size_minutes = 60`).

WHY IT LIVES UNDER broker/. `scripts/preflight_exec_deploy_scope.py` derives the execution deploy
scope from BOOT-time imports plus the definitional rule "every `broker/*.py` runs on
apollo-execution". The shadow tracker is imported lazily inside its scheduler jobs, so nothing it
imports — at top level or not — ever enters the derived list; a copy of these walks anywhere outside
`broker/` would be deployed to the execution container only by accident (#456 silent-dark). Under
`broker/` the routing is by definition. Like `broker/exit_logic.py` this module is PURE: no Alpaca
client, no DB, no trade state — it may be imported from the intelligence side with the
`exec-boundary-ok` marker exactly as `exit_logic` is.

THE DAY-0 GAP RULE (`classify_hour_entry`). A walk whose stored minutes never crossed the hour high
but have holes after 10:30 is NOT abstained on sight: the day-0 DAILY bar decides first. A session
high strictly BELOW the stored hour high proves no later print reached it → `no_entry` with the
suffix ':proven_by_daily_high'. A daily high EQUAL to the hour high proves nothing (a stop triggers
AT its price, and the re-touch may sit in a minute that is not stored) — it stays pending with the
rest: a higher session high, or no stored daily bar, defers the verdict to the caller's retry rule.
(Strict since 2026-10-27, review F6; the 2026-10-26 build read equality as proven.)
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time
from typing import Optional

from shared.dates import _ET

logger = logging.getLogger(__name__)

FIRST_HOUR_START = time(9, 30)
FIRST_HOUR_END = time(10, 30)        # exclusive: the first 60-minute bar is 09:30-10:29
MIN_HOUR_BARS = 50                   # of 60 minutes stored; below this the bar's high/low is not trusted
REGULAR_CLOSE = time(16, 0)
NO_ENTRY_HOUR = "no_entry:never_crossed_hour_high"


def stop_limit_buy_price(stop_price: float) -> float:
    """The LIMIT of a stop-limit BUY — mirrors broker.order_manager.stop_limit_buy_price (0.5% or
    $0.02 above the stop, whichever is larger). Inlined: order_manager pulls the Alpaca stack, which
    a recorder must never import (sustain_reject_replay's precedent; parity pinned by test)."""
    return round(max(stop_price * 1.005, stop_price + 0.02), 2)


def entry_walk(bars: list[dict], level: float, submit: time, cancel: Optional[time]) -> dict:
    """Mirror of sustain_reject_replay.entry_walk (parity pinned by test): the stop-limit buy
    (stop = `level`, limit = stop_limit_buy_price) over the minute bars in [submit, cancel). Bars
    carry `m` as an ET-aware datetime. 'no_entry' only on a fully covered window, else ABSTAIN."""
    limit = stop_limit_buy_price(level)
    limit_armed = False
    window = [b for b in bars
              if b["m"].time() >= submit and (cancel is None or b["m"].time() < cancel)]
    for b in window:
        if limit_armed:
            if b["l"] <= limit:
                return {"status": "filled", "px": limit, "minute": b["m"]}
            continue
        if b["o"] >= level:
            if b["o"] <= limit:
                return {"status": "filled", "px": b["o"], "minute": b["m"]}
            limit_armed = True
            if b["l"] <= limit:
                return {"status": "filled", "px": limit, "minute": b["m"]}
        elif b["h"] >= level:
            return {"status": "filled", "px": level, "minute": b["m"]}
    if limit_armed:
        return {"status": "no_entry", "reason": "triggered_above_limit_never_filled"}
    end = cancel if cancel is not None else time(16, 0)
    expected = int((datetime.combine(date.min, end) -
                    datetime.combine(date.min, max(submit, time(9, 30)))).total_seconds() // 60)
    if len(window) < expected:
        return {"status": "abstain", "reason": f"entry_window_gaps:{expected - len(window)}_of_{expected}"}
    return {"status": "no_entry", "reason": "never_crossed_orb_high"}


def first_hour_frame(bars: list[dict]) -> dict:
    """The first 60-minute bar from ET-aware 1-minute bars: {'high', 'low', 'n'} or
    {'abstain': reason}. Fewer than MIN_HOUR_BARS stored minutes of the 60 → abstain with the count
    named (a stored-bar hole could hide the true high or low)."""
    hour = [b for b in bars if FIRST_HOUR_START <= b["m"].time() < FIRST_HOUR_END]
    if len(hour) < MIN_HOUR_BARS:
        return {"abstain": f"first_hour_bars:{len(hour)}_of_60"}
    hi, lo = max(b["h"] for b in hour), min(b["l"] for b in hour)
    if hi <= lo:
        return {"abstain": "first_hour_zero_range"}
    return {"high": hi, "low": lo, "n": len(hour)}


def session_close_et(d: date) -> time:
    """The regular session's close on `d` in ET (13:00 on an NYSE half day), from the same
    exchange_calendars ruleset the trading calendar uses. Falls back to 16:00 on a calendar error —
    the walk then reads a half day as gappy and the arm waits / abstains, never invents a fill."""
    try:
        from agents.market_intelligence.trading_calendar import _get_nyse_calendar
        return _get_nyse_calendar().session_close(d.isoformat()).tz_convert(_ET).time()
    except Exception as e:  # loud-ok: logged; the fallback can only make an arm wait, never fabricate
        logger.warning(f"hour-bar walk: session close for {d} unreadable ({e}); using 16:00")
        return REGULAR_CLOSE


def classify_hour_entry(bars: list[dict], session_close: time,
                        day0_daily_high: Optional[float] = None) -> dict:
    """The hour-bar ENTRY both recorders share, computed once per alert. Returns one of
      {'kind': 'filled', 'high', 'low', 'px', 'minute'}
      {'kind': 'no_entry', 'high', 'low', 'reason'}   — reason starts 'no_entry:'
      {'kind': 'pending', 'reason', 'high'?, 'low'?}  — a data gap: retried, abstained when stale
      {'kind': 'needs_daily_high', 'high', 'low', 'walk_reason'} — only when `day0_daily_high` is
                                                       not supplied and the walk saw gaps
    A walk that saw gaps is decided by the day-0 daily high (module docstring, DAY-0 GAP RULE)."""
    frame = first_hour_frame(bars)
    if "abstain" in frame:
        return {"kind": "pending", "reason": frame["abstain"]}
    hi, lo = frame["high"], frame["low"]
    walk = entry_walk(bars, hi, FIRST_HOUR_END, session_close)
    if walk["status"] == "filled":
        return {"kind": "filled", "high": hi, "low": lo, "px": float(walk["px"]), "minute": walk["minute"]}
    if walk["status"] == "no_entry":
        # the mirrored walk names the level 'orb_high'; here the level is the hour bar's
        return {"kind": "no_entry", "high": hi, "low": lo,
                "reason": "no_entry:" + walk["reason"].replace("orb_high", "hour_high")}
    # abstain: the stored minutes after 10:30 have holes and none of them crossed the hour high
    if day0_daily_high is None:
        return {"kind": "needs_daily_high", "high": hi, "low": lo, "walk_reason": walk["reason"]}
    if day0_daily_high < hi - 1e-9:
        return {"kind": "no_entry", "high": hi, "low": lo, "reason": f"{NO_ENTRY_HOUR}:proven_by_daily_high"}
    return {"kind": "pending", "high": hi, "low": lo,
            "reason": f"{walk['reason']}:session_high_at_or_above_hour_high"}
