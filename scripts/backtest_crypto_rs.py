"""End-to-end RS backtest — pulls live history for ~12 representative coins,
computes RS-vs-BTC scores, prints rankings.

Use this to validate the full data + RS pipeline against a normal network.
The smoke-test script (verify_crypto_sources.py) only proves the APIs respond;
this script proves the WHOLE pipeline produces sensible rankings.

Run from repo root:
    PYTHONPATH=. python3 scripts/backtest_crypto_rs.py

What "good" looks like:
- BTC ranks near 50-70 (it's the denominator, so its RS-vs-BTC composite hovers
  around the median; outliers shouldn't dominate it).
- Strong-trend coins (e.g., recent SOL/RENDER/HYPE rips) should rank in top-5
  with rs_overall > 80.
- Beaten-down legacy alts should land in bottom-5 with rs_overall < 30.
- Within each mcap bucket, rs_in_bucket should NOT just mirror rs_overall —
  the bucket adjustment is the whole point.

If the output looks insane (everything 50, or BTC at 100, or 0 scores
everywhere), something is wrong with the bar pull or the BTC denominator.
"""
from __future__ import annotations

import asyncio
import logging
import sys

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from datetime import datetime
from zoneinfo import ZoneInfo

from agents.market_intelligence.crypto import (
    coingecko_client as cg,
    rs_engine,
)

_ET = ZoneInfo("America/New_York")

# Representative spread: large/mid/micro buckets, AI/L1/DeFi/meme themes,
# spot pairs likely to exist on CG free tier. ~12 coins keeps total CG calls
# modest (12 history fetches × ~2.1s throttle ≈ 25 seconds).
COINS = [
    # (cg_id, expected_bucket_hint)
    ("bitcoin", "mega"),
    ("ethereum", "mega"),
    ("solana", "large"),
    ("binancecoin", "large"),
    ("chainlink", "large"),
    ("hyperliquid", "large"),
    ("avalanche-2", "mid"),
    ("render-token", "mid"),
    ("fetch-ai", "mid"),         # ASI Alliance
    ("dogecoin", "large"),
    ("pepe", "mid"),
    ("akash-network", "micro"),
]


async def main() -> int:
    print(f"Backtest run at {datetime.now(_ET).isoformat()}\n")
    print(f"Pulling 200d history for {len(COINS)} coins from CoinGecko...\n")

    # Fetch all bars sequentially (CG throttle handles rate limits).
    coins_data: list[dict] = []
    btc_closes: dict = {}

    for coin_id, hint in COINS:
        try:
            chart = await cg.get_market_chart(coin_id, days=200)
            bars = cg.market_chart_to_daily_bars(chart)
        except Exception as e:
            print(f"  FAIL {coin_id}: {type(e).__name__}: {e}")
            continue

        if not bars:
            print(f"  EMPTY {coin_id}")
            continue

        # Last bar mcap — best proxy without a separate /coins/markets call.
        latest = bars[-1]
        mcap = latest.get("mcap_usd") or 0.0
        symbol = coin_id.split("-")[0].upper()[:6]

        if coin_id == "bitcoin":
            for b in bars:
                if b.get("close_usd"):
                    btc_closes[b["date"]] = b["close_usd"]

        coins_data.append({
            "coin_id": coin_id,
            "symbol": symbol,
            "mcap_usd": mcap,
            "daily_closes": bars,
        })
        bucket = rs_engine.assign_mcap_bucket(mcap)
        marker = "✓" if bucket == hint else f"≠{hint}"
        print(f"  ok   {symbol:<8} bars={len(bars):3d}  mcap=${mcap:>15,.0f}  bucket={bucket} {marker}")

    if not btc_closes:
        print("\nFAIL: no BTC history; cannot compute RS-vs-BTC.")
        return 1

    score_date = max(btc_closes.keys())
    print(f"\nScoring as of {score_date} ({len(btc_closes)}d BTC history)\n")

    scores = rs_engine.compute_rs_scores(coins_data, btc_closes, score_date)

    # Sort by rs_overall desc.
    scores.sort(key=lambda s: (s.get("rs_overall") or -1), reverse=True)

    print(f"{'#':<3}{'COIN':<10}{'BUCKET':<14}{'RS_1M':>7}{'RS_3M':>7}{'RS_6M':>7}{'COMP':>7}{'OVR':>6}{'BUCK':>6}")
    print("-" * 76)
    for i, s in enumerate(scores, 1):
        coin = s["coin_id"][:9]
        rs_1m = s.get("rs_1m"); rs_3m = s.get("rs_3m"); rs_6m = s.get("rs_6m")
        comp = s.get("rs_composite"); ovr = s.get("rs_overall"); buck = s.get("rs_in_bucket")
        def f(v): return f"{v:>6.1f}" if v is not None else "    --"
        print(f"{i:<3}{coin:<10}{s['mcap_bucket']:<14}{f(rs_1m)}{f(rs_3m)}{f(rs_6m)}{f(comp)}{f(ovr)}{f(buck)}")

    # Sanity assertions.
    print("\n=== Sanity checks ===")
    btc_score = next((s for s in scores if s["coin_id"] == "bitcoin"), None)
    if btc_score and btc_score.get("rs_overall") is not None:
        # BTC's RS-vs-BTC composite should be near the median (~50) — it's the
        # denominator so it can't outperform itself; ranking comes from
        # tied-zero returns vs other coins' actual returns.
        rs = btc_score["rs_overall"]
        print(f"  BTC rs_overall = {rs:.1f}  (expect ~30-70 range; far outside = bug)")
    none_count = sum(1 for s in scores if s.get("rs_overall") is None)
    print(f"  Coins with None rs_overall: {none_count}/{len(scores)}  (expect 0; >0 means insufficient history)")
    buckets = {s["mcap_bucket"] for s in scores}
    print(f"  Buckets observed: {sorted(buckets)}  (expect mix of mega/large/mid/micro)")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
