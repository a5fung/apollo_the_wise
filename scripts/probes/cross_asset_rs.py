"""P21 — Cross-asset thematic RS track for commodity/futures ETFs.

Parallel RS rank for commodity ETFs (CPER copper, URA uranium, GLD gold,
SLV silver, USO oil, UNG natgas, DBA agriculture, DBB base metals, KSA Saudi,
EWZ Brazil, etc). When an equity theme's RS surge aligns with a commodity
ETF's RS surge, boost theme conviction × 1.2 (V2 — wiring deferred).

Commodity ETFs are in SKIP_TICKERS for the main RS pipeline (which is
equity-only). This module computes RS over the commodity universe
separately by pulling N grouped-daily snapshots and extracting the
universe's closes.

V1 scope (this file): standalone leaderboard print. Run as:
  docker exec apollo-market python -m scripts.cross_asset_rs
"""
import asyncio
from datetime import date, timedelta

from agents.market_intelligence.collector import get_grouped_daily, last_trading_day


COMMODITY_UNIVERSE: list[tuple[str, str]] = [
    # (ticker, descriptive_label)
    ("CPER", "Copper"),
    ("URA",  "Uranium"),
    ("URNM", "Uranium miners"),
    ("GLD",  "Gold"),
    ("GDX",  "Gold miners"),
    ("SLV",  "Silver"),
    ("SIL",  "Silver miners"),
    ("USO",  "Oil (WTI)"),
    ("XLE",  "Energy sector"),
    ("UNG",  "Natural gas"),
    ("DBA",  "Agriculture"),
    ("DBB",  "Base metals"),
    ("REMX", "Rare earth metals"),
    ("LIT",  "Lithium"),
    ("KSA",  "Saudi Arabia"),
    ("EWZ",  "Brazil"),
    ("ARGT", "Argentina"),
    ("EWJ",  "Japan"),
    ("EEM",  "Emerging markets"),
    ("PAVE", "Infrastructure"),
]


async def _walk_back_to_trading_day(start: date, calendar_days_back: int) -> date:
    """Polygon's grouped-daily endpoint 404s on weekends/holidays. Walk back
    one calendar day at a time until we land on a trading day with data.
    Caps at 14 attempts to avoid infinite loops on long holiday gaps."""
    target = start - timedelta(days=calendar_days_back)
    for _ in range(14):
        snap = await get_grouped_daily(target.isoformat())
        if snap:
            return target
        target -= timedelta(days=1)
    return target  # best-effort fallback


async def compute_cross_asset_rs() -> list[dict]:
    """Return list of {ticker, label, close, return_5d, return_21d, return_63d,
    return_126d, rank_1m} for the commodity universe. Ranked by 21d return
    (1-month) — sufficient signal for V1."""
    today_d = last_trading_day(date.today())
    today_snap = await get_grouped_daily(today_d.isoformat())
    if not today_snap:
        print(f"No data for {today_d}")
        return []

    # Approximate N-trading-day-back dates (calendar days × 7/5 buffer).
    # _walk_back_to_trading_day handles weekend/holiday landings.
    snapshots: dict[int, dict[str, dict]] = {0: today_snap}
    for days in (5, 21, 63, 126):
        d = await _walk_back_to_trading_day(today_d, days * 7 // 5)
        snapshots[days] = await get_grouped_daily(d.isoformat())

    results: list[dict] = []
    for ticker, label in COMMODITY_UNIVERSE:
        today_bar = today_snap.get(ticker)
        if not today_bar or not today_bar.get("c"):
            continue
        today_close = today_bar["c"]
        row: dict = {"ticker": ticker, "label": label, "close": today_close}
        for days in (5, 21, 63, 126):
            past = snapshots[days].get(ticker)
            if past and past.get("c"):
                row[f"return_{days}d"] = (today_close - past["c"]) / past["c"] * 100
        results.append(row)

    # Rank by 21d (1-month) return.
    results.sort(key=lambda r: r.get("return_21d", -999), reverse=True)
    for i, r in enumerate(results):
        r["rank_1m"] = i + 1
    return results


async def print_leaderboard() -> None:
    rows = await compute_cross_asset_rs()
    if not rows:
        print("No data fetched.")
        return
    print(f"\n{'#':>3} {'Tkr':6s} {'Label':22s} {'5d%':>7s} {'21d%':>7s} {'63d%':>7s} {'126d%':>7s}")
    print("-" * 70)
    for r in rows:
        rank = r.get("rank_1m", "")
        d5 = f"{r['return_5d']:+.1f}" if "return_5d" in r else "—"
        d21 = f"{r['return_21d']:+.1f}" if "return_21d" in r else "—"
        d63 = f"{r['return_63d']:+.1f}" if "return_63d" in r else "—"
        d126 = f"{r['return_126d']:+.1f}" if "return_126d" in r else "—"
        print(f"{rank:>3} {r['ticker']:6s} {r['label']:22s} {d5:>7s} {d21:>7s} {d63:>7s} {d126:>7s}")


if __name__ == "__main__":
    asyncio.run(print_leaderboard())
