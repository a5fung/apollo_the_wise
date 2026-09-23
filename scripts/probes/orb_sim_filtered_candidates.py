"""
ORB intraday simulation for 6 MAGNA53-filtered candidates (gap≥10% + strong catalyst).

Per advisor: forward stock returns ≠ ORB strategy outcome. EL closed +3.4% but if
the ORB-low stop fired intraday, the trade lost regardless. This sim asks: did
ORB-high trigger an entry, and if so did ORB-low stop fire intraday?

Strategy mechanics (matches MAGNA53 paper-trade pipeline):
- ORB = first 1-min bar of session (9:30-9:31 ET)
- Submission window 9:30-9:45 ET (entry stop-limit BUY @ ORB_high)
- After entry: stop = ORB_low (intraday); EOD close otherwise

Usage on prod:
    docker compose -f docker/docker-compose.prod.yml exec market-agent \
        python -m scripts.orb_sim_filtered_candidates
"""
from __future__ import annotations

import asyncio
from datetime import date

from agents.market_intelligence.backtester.intraday import get_intraday_bars

CANDIDATES = [
    ("EL",   date(2026, 5, 1),  76.71),
    ("ROKU", date(2026, 5, 1),  116.56),
    ("PWR",  date(2026, 4, 30), 628.60),
    ("ELVR", date(2026, 4, 28), 88.04),
    ("ARM",  date(2026, 4, 24), 204.61),
    ("DFTX", date(2026, 4, 20), 22.68),
]

SUBMISSION_END_MINUTE = 45  # 9:45 ET — matches live ORB submission window


def simulate_orb(bars: list[dict], prev_close: float) -> dict:
    if len(bars) < 2:
        return {"error": "no bars"}

    orb = bars[0]
    orb_high = float(orb["high"])
    orb_low = float(orb["low"])
    orb_open = float(orb["open"])
    eod_close = float(bars[-1]["close"])

    entry_bar = None
    entry_idx = None
    for i, b in enumerate(bars[1:], start=1):
        bt = b["bar_time"].time()
        if bt.hour == 9 and bt.minute >= SUBMISSION_END_MINUTE:
            break
        if bt.hour > 9:
            break
        if float(b["high"]) >= orb_high:
            entry_bar = b
            entry_idx = i
            break

    if entry_bar is None:
        return {
            "outcome": "never_triggered",
            "orb_high": orb_high,
            "orb_low": orb_low,
            "orb_open": orb_open,
            "eod_close": eod_close,
            "high_after_orb": max(float(b["high"]) for b in bars[1:]),
            "stock_return_pct": (eod_close - prev_close) / prev_close * 100,
        }

    entry_price = orb_high  # stop-limit BUY fills at trigger
    stop_price = orb_low

    stop_fired = None
    final_exit = eod_close
    final_exit_reason = "eod_close"
    for b in bars[entry_idx + 1:]:
        if float(b["low"]) <= stop_price:
            stop_fired = b
            final_exit = stop_price
            final_exit_reason = "stop_fired"
            break

    pnl_pct = (final_exit - entry_price) / entry_price * 100
    risk_pct = (entry_price - stop_price) / entry_price * 100
    r_multiple = (final_exit - entry_price) / (entry_price - stop_price) if entry_price != stop_price else 0

    return {
        "outcome": "filled_stopped" if stop_fired else "filled_held",
        "orb_high": orb_high,
        "orb_low": orb_low,
        "orb_open": orb_open,
        "entry_time": entry_bar["bar_time"].strftime("%H:%M"),
        "entry_price": entry_price,
        "stop_price": stop_price,
        "stop_fired_at": stop_fired["bar_time"].strftime("%H:%M") if stop_fired else None,
        "final_exit": final_exit,
        "final_exit_reason": final_exit_reason,
        "risk_pct": risk_pct,
        "pnl_pct": pnl_pct,
        "r_multiple": r_multiple,
        "eod_close": eod_close,
        "stock_return_pct": (eod_close - prev_close) / prev_close * 100,
    }


async def main():
    print(f"{'TICKER':<6} {'DATE':<11} {'ORB_H':>8} {'ORB_L':>8} {'OUTCOME':<18} {'ENTRY':>6} {'STOP@':>6} {'PNL%':>7} {'R':>6} {'STK%':>7}")
    print("-" * 100)
    for ticker, d, prev_close in CANDIDATES:
        bars = await get_intraday_bars(ticker, d)
        result = simulate_orb(bars, prev_close)
        if "error" in result:
            print(f"{ticker:<6} {d.isoformat():<11} ERROR: {result['error']}")
            continue
        outcome = result["outcome"]
        entry = result.get("entry_time", "-")
        stop_at = result.get("stop_fired_at") or "-"
        pnl = result.get("pnl_pct", 0)
        r = result.get("r_multiple", 0)
        stk = result.get("stock_return_pct", 0)
        print(
            f"{ticker:<6} {d.isoformat():<11} "
            f"{result['orb_high']:>8.2f} {result['orb_low']:>8.2f} "
            f"{outcome:<18} {entry:>6} {stop_at:>6} "
            f"{pnl:>+7.2f} {r:>+6.2f} {stk:>+7.2f}"
        )

    print()
    print("Legend:")
    print("  filled_stopped  — entry triggered, ORB-low stop fired intraday")
    print("  filled_held     — entry triggered, no stop, exited at 4:00 close")
    print("  never_triggered — price never reached ORB-high in submission window")
    print("  R = (exit - entry) / (entry - stop)   PNL% based on entry price")


if __name__ == "__main__":
    asyncio.run(main())
