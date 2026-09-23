"""ORB-window-extension impact — multi-day TRADE-lifecycle simulation.

Scope (narrow, by user request): only existing rows where the ORB stop-limit
order WAS placed in the normal 9:31-9:35 window and CANCELLED unfilled
(at 10:00 ET via the ORB cleanup cron, OR at 4:05 PM via the EOD cleanup).
NOT looking at out-of-orb skips, alert-time questions, or filter rejections.

For each row + each candidate cutoff in {10:00, 11:00, 12:00, 13:00, 14:00,
16:00}:
  Day 1 (alert day):
    - Find first 1-min bar in [proposed_at, cutoff] where high >= limit.
    - If no cross → trade stays cancelled, P&L = 0.
    - If cross → enter at `limit`. Check intraday minute bars for stop
      hit (low <= stop). On stop hit, attempt same-day re-entry (max 2
      total attempts, mirroring `attempt_day1_reentry`).
    - End-of-day: if still in position, hand off to daily lifecycle.

  Day 2+ (multi-day):
    - Use `apply_daily_exit_step` from production exit_logic.py — same
      function that runs live: hard_stop, SMA10/20 trail, Day-3-5 partial
      (1/3 shares), breakeven activation.
    - Run forward from alert_date+1 through today's last close.
    - Closed → realized P&L. Still open → realized + unrealized at last close.

This is the *trade* P&L over its full lifetime, not a single-day P&L.

Output:
  - Per-trade x cutoff matrix (final P&L)
  - Total / mean / median per cutoff
  - Hold-day distribution per cutoff
  - Sample-size warning if N < 20
"""
from __future__ import annotations
import asyncio
import sys
from datetime import datetime as _dt, date as _date, timedelta as _td
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agents.market_intelligence.collector import (
    get_minute_bars, get_index_history, et_today,
)
from agents.market_intelligence.broker.exit_logic import apply_daily_exit_step
from agents.market_intelligence.db import get_pool

_ET = ZoneInfo("America/New_York")
MAX_ATTEMPTS = 2  # same as production MAX_ENTRY_ATTEMPTS
CUTOFFS = [(10, 0), (11, 0), (12, 0), (13, 0), (14, 0), (16, 0)]


def _hhmm(t: _dt) -> int:
    return t.hour * 100 + t.minute


async def _fetch_rth_minute(ticker: str, d: _date) -> list[tuple]:
    bars = await get_minute_bars(ticker, d.isoformat(), d.isoformat())
    out = []
    for b in bars:
        t = _dt.fromtimestamp(b["t"] / 1000, tz=_ET)
        if 931 <= _hhmm(t) <= 1600:
            out.append((t, float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])))
    return sorted(out)


async def _fetch_daily(ticker: str, start: _date, end: _date) -> list[dict]:
    """Daily OHLC bars over [start, end] inclusive. Returns dicts with l/c
    (the keys apply_daily_exit_step uses)."""
    raw = await get_index_history(ticker, start.isoformat(), end.isoformat())
    out = []
    for b in raw:
        ts = _dt.fromtimestamp(b["t"] / 1000, tz=_ET)
        out.append({
            "date": ts.date(),
            "l": float(b["l"]),
            "c": float(b["c"]),
            "h": float(b["h"]),
            "o": float(b["o"]),
        })
    return sorted(out, key=lambda x: x["date"])


def _next_business_day(d: _date) -> _date:
    nd = d + _td(days=1)
    while nd.weekday() >= 5:
        nd += _td(days=1)
    return nd


async def simulate_lifecycle(
    ticker: str,
    alert_date: _date,
    proposed_at: _dt,
    limit: float,
    stop: float,
    shares: int,
    cutoff_t: _dt,
) -> dict:
    """Full multi-day lifecycle from hypothetical fill to current state.

    Returns dict with: would_fill, pnl, hold_days, final_status, exits.
    """
    rth1 = await _fetch_rth_minute(ticker, alert_date)
    if not rth1:
        return {"would_fill": False, "pnl": 0, "reason": "no_d1_bars"}

    # Day 1: entry attempts
    fill_t = None
    cur_t = proposed_at
    attempts = 0
    exits: list[dict] = []
    remaining = shares
    entry_price = limit
    final_d1_status = "no_fill"

    while attempts < MAX_ATTEMPTS:
        cross = next(((t, h) for t, _o, h, _l, _c in rth1
                      if cur_t <= t <= cutoff_t and h >= limit), None)
        if not cross:
            break
        attempts += 1
        fill_t = cross[0]
        # Check for stop-out anywhere from fill_t to EOD on day 1
        stop_hit = next(((t, l) for t, _o, _h, l, _c in rth1
                         if t > fill_t and l <= stop), None)
        if not stop_hit:
            final_d1_status = "open_eod"
            break
        # Stopped intraday — record exit, optionally re-enter
        pnl_leg = (stop - entry_price) * remaining
        exits.append({
            "day": 1, "time": stop_hit[0].isoformat(),
            "price": stop, "shares": remaining,
            "reason": "intraday_stop", "pnl": pnl_leg,
        })
        if attempts >= MAX_ATTEMPTS:
            final_d1_status = "max_attempts_stopped"
            break
        # Re-entry: must cross again before cutoff
        cur_t = stop_hit[0]
        # loop continues — will look for next cross in [cur_t, cutoff_t]

    if fill_t is None:
        return {"would_fill": False, "pnl": 0, "reason": "no_cross_by_cutoff"}

    # If we ended Day 1 stopped out (max attempts or no re-cross by cutoff),
    # there's no open position to carry to Day 2. Realised P&L only.
    realised_d1 = sum(e["pnl"] for e in exits)
    if final_d1_status != "open_eod":
        return {
            "would_fill": True,
            "pnl": realised_d1,
            "hold_days": 0,
            "final_status": final_d1_status,
            "exits": exits,
            "attempts": attempts,
        }

    # Day 1 ended with open position — hand off to daily lifecycle
    day1_close = rth1[-1][4]
    today = et_today()
    daily = await _fetch_daily(ticker, alert_date + _td(days=1), today)
    state = {
        "alert_date": alert_date,
        "remaining_shares": remaining,
        "entry_price": entry_price,
        "hard_stop": stop,
        "partial_taken": False,
        "breakeven_active": False,
        "exits": exits,
        "running_closes": [day1_close],
    }
    closed_status = None
    closed_date = None
    for bar in daily:
        d = bar["date"]
        if d <= alert_date:
            continue
        step = apply_daily_exit_step(state, bar, d, integer_partial_shares=True)
        # update state
        state["remaining_shares"] = step.new_remaining
        state["partial_taken"] = step.new_partial_taken
        state["breakeven_active"] = step.new_breakeven_active
        state["running_closes"] = step.new_running_closes
        state["exits"] = step.new_exits
        if step.closed:
            closed_status = step.close_reason
            closed_date = d
            break

    realised = sum(e.get("pnl", 0) for e in state["exits"])
    if closed_status:
        return {
            "would_fill": True,
            "pnl": realised,
            "hold_days": (closed_date - alert_date).days,
            "final_status": closed_status,
            "exits": state["exits"],
            "attempts": attempts,
        }
    # Still open — mark to market
    last_close = state["running_closes"][-1] if state["running_closes"] else day1_close
    unrealised = (last_close - entry_price) * state["remaining_shares"]
    return {
        "would_fill": True,
        "pnl": realised + unrealised,
        "hold_days": (today - alert_date).days,
        "final_status": "still_open",
        "last_close": last_close,
        "remaining_shares": state["remaining_shares"],
        "exits": state["exits"],
        "attempts": attempts,
    }


async def main():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker, alert_date, proposed_at, entry_price, stop_price,
                   entry_shares, skip_reason
            FROM mi_live_trades
            WHERE status IN ('cancelled', 'expired')
              AND entry_price IS NOT NULL
              AND stop_price IS NOT NULL
              AND entry_shares > 0
              AND proposed_at IS NOT NULL
              AND EXTRACT(HOUR  FROM proposed_at AT TIME ZONE 'America/New_York') = 9
              AND EXTRACT(MINUTE FROM proposed_at AT TIME ZONE 'America/New_York') BETWEEN 31 AND 35
            ORDER BY alert_date ASC
        """)

    print(f"\nUniverse: {len(rows)} cancelled-ORB-window trades "
          f"(proposed 9:31–9:35 ET, no fill)\n")
    if len(rows) < 20:
        print(f"⚠  N={len(rows)} is BELOW the 20-trade significance threshold. "
              f"Treat results as directional, not decisional.\n")

    results = {c: [] for c in CUTOFFS}
    for r in rows:
        ticker = r["ticker"]
        d = r["alert_date"]
        proposed = r["proposed_at"].astimezone(_ET)
        limit = float(r["entry_price"])
        stop = float(r["stop_price"])
        shares = int(r["entry_shares"])

        for ch, cm in CUTOFFS:
            cutoff_t = _dt.combine(d, _dt.min.time(), tzinfo=_ET).replace(hour=ch, minute=cm)
            res = await simulate_lifecycle(
                ticker, d, proposed, limit, stop, shares, cutoff_t,
            )
            res["ticker"] = ticker
            res["date"] = d
            res["limit"] = limit
            res["stop"] = stop
            res["shares"] = shares
            results[(ch, cm)].append(res)

    # ---- Aggregate ----
    print(f"{'cutoff':<8} {'fills':>6} {'wins':>5} {'losses':>7} "
          f"{'still open':>11} {'total $':>10} {'mean $':>9} {'median $':>10} "
          f"{'avg hold':>9}")
    print("-" * 88)
    for ch, cm in CUTOFFS:
        rs = results[(ch, cm)]
        filled = [r for r in rs if r.get("would_fill")]
        wins = sum(1 for r in filled if r["pnl"] > 0)
        losses = sum(1 for r in filled if r["pnl"] < 0)
        open_n = sum(1 for r in filled if r.get("final_status") == "still_open")
        total = sum(r["pnl"] for r in rs)
        mean_v = total / len(filled) if filled else 0
        if filled:
            sorted_pnl = sorted(r["pnl"] for r in filled)
            mid = len(sorted_pnl) // 2
            median_v = sorted_pnl[mid] if len(sorted_pnl) % 2 else (sorted_pnl[mid - 1] + sorted_pnl[mid]) / 2
        else:
            median_v = 0
        avg_hold = (sum(r.get("hold_days", 0) for r in filled) / len(filled)) if filled else 0
        print(f"{ch:02d}:{cm:02d}    {len(filled):>6} {wins:>5} {losses:>7} "
              f"{open_n:>11} {total:>+10.0f} {mean_v:>+9.0f} {median_v:>+10.0f} "
              f"{avg_hold:>9.1f}d")

    # ---- Per-trade matrix (full lifecycle P&L) ----
    print(f"\nPer-trade lifecycle P&L by cutoff:")
    print(f"{'ticker':<7}{'date':<12}{'limit':>9}{'stop':>9}{'sh':>5}", end="")
    for ch, cm in CUTOFFS:
        print(f"{ch:02d}:{cm:02d}".rjust(10), end="")
    print(f"  {'final (16:00)':<25}")
    print("-" * (42 + 10 * len(CUTOFFS) + 27))

    for i, r in enumerate(rows):
        ticker = r["ticker"]; d = r["alert_date"]
        print(f"{ticker:<7}{str(d):<12}{float(r['entry_price']):>9.2f}"
              f"{float(r['stop_price']):>9.2f}{int(r['entry_shares']):>5}", end="")
        last_status = ""
        for ch, cm in CUTOFFS:
            res = results[(ch, cm)][i]
            cell = f"{res['pnl']:+.0f}" if res.get("would_fill") else "—"
            print(cell.rjust(10), end="")
            if (ch, cm) == (16, 0):
                hd = res.get("hold_days", 0)
                last_status = f"{res.get('final_status','-')} ({hd}d)"
        print(f"  {last_status:<25}")

    print(f"\nMethod notes:")
    print(f"- Production exit logic: hard_stop + SMA10/20 trail + Day3-5 partial(1/3) + breakeven.")
    print(f"- Same-day re-entry: up to {MAX_ATTEMPTS} attempts (mirrors attempt_day1_reentry).")
    print(f"- Lifecycle runs from alert_date+1 through today; open positions marked-to-market at last close.")
    print(f"- Sim assumes fills exactly at limit (real stop-limit BUY can miss on gap-through — overstates fills).")


if __name__ == "__main__":
    asyncio.run(main())
