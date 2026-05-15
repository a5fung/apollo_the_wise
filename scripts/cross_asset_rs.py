"""P21 — Cross-asset thematic RS track for commodity/futures ETFs.

Parallel RS rank for commodity ETFs (CPER copper, URA uranium, GLD gold,
SLV silver, USO oil, UNG natgas, DBA agriculture, DBB base metals, KSA Saudi,
EWZ Brazil, etc). When an equity theme's RS surge aligns with a commodity
ETF's RS surge, boost theme conviction × 1.2.

Commodity ETFs are in SKIP_TICKERS for the main RS pipeline (which is
equity-only). This module computes RS over the commodity universe
separately and surfaces it via `cross asset rs` Telegram command.

V1 scope (this file): build the parallel RS pipeline + Telegram surface.
V2 (deferred): wire conviction boost into theme_engine when commodity ETF
RS aligns with equity theme — needs theme-to-commodity mapping table.
"""
import asyncio
from datetime import date, timedelta

from agents.market_intelligence.collector import get_polygon_daily_bar
from agents.market_intelligence.db import get_pool


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


async def compute_cross_asset_rs() -> list[dict]:
    """Return list of {ticker, label, rs_composite, raw_1m, raw_3m, raw_6m}
    for the commodity universe. Same RS formula as the equity pipeline:
    40% × 1M + 30% × 3M + 30% × 6M, ranked within this universe.
    """
    today = date.today()
    results = []
    for ticker, label in COMMODITY_UNIVERSE:
        try:
            # 6m back
            bars = []
            for days_back in (5, 21, 63, 126):  # 1w, 1m, 3m, 6m
                d = today - timedelta(days=days_back * 7 // 5)  # roughly N trading days
                try:
                    bar = await get_polygon_daily_bar(ticker, d)
                except Exception:
                    bar = None
                bars.append((days_back, bar))
            today_bar = await get_polygon_daily_bar(ticker, today)
            if not today_bar:
                continue
            today_close = today_bar["c"]
            row = {"ticker": ticker, "label": label, "close": today_close}
            for days, bar in bars:
                if bar and bar.get("c"):
                    row[f"return_{days}d"] = (today_close - bar["c"]) / bar["c"] * 100
            results.append(row)
        except Exception as e:
            print(f"  {ticker} skipped: {e}")

    # Rank by raw_1m (1m return) — sufficient for V1 spike.
    results.sort(key=lambda r: r.get("return_21d", -999), reverse=True)
    for i, r in enumerate(results):
        r["rank_1m"] = i + 1
    return results


async def print_leaderboard() -> None:
    rows = await compute_cross_asset_rs()
    if not rows:
        print("No data fetched.")
        return
    print(f"{'Rank':>4} {'Tkr':6s} {'Label':22s} {'5d%':>7s} {'21d%':>7s} {'63d%':>7s} {'126d%':>7s}")
    print("-" * 70)
    for r in rows:
        rank = r.get("rank_1m", "")
        d5 = f"{r['return_5d']:+.1f}" if "return_5d" in r else "—"
        d21 = f"{r['return_21d']:+.1f}" if "return_21d" in r else "—"
        d63 = f"{r['return_63d']:+.1f}" if "return_63d" in r else "—"
        d126 = f"{r['return_126d']:+.1f}" if "return_126d" in r else "—"
        print(f"{rank:>4} {r['ticker']:6s} {r['label']:22s} {d5:>7s} {d21:>7s} {d63:>7s} {d126:>7s}")


if __name__ == "__main__":
    asyncio.run(print_leaderboard())
