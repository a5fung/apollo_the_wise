"""Smoke-test all four crypto data sources end-to-end.

Run from repo root:
    PYTHONPATH=. python3 scripts/verify_crypto_sources.py

Exits non-zero on any source failure. Used as the readiness check before
flipping CRYPTO_RS_ENABLED=true; also useful after deploys to confirm no
breaking API changes from upstream providers.
"""
from __future__ import annotations

import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("verify_crypto")

from agents.market_intelligence.crypto import (
    coingecko_client as cg,
    defillama_client as llama,
    dexscreener_client as ds,
    kraken_client as kraken,
)


async def check_kraken() -> bool:
    print("\n=== Kraken ===")
    try:
        pairs = await kraken.list_supported_pairs(quote="USD")
        print(f"  USD pairs available: {len(pairs)}")
        if "BTC" not in pairs or "ETH" not in pairs:
            print("  FAIL: BTC or ETH missing from supported pairs")
            return False
        bars = await kraken.get_daily_ohlc("BTC", "USD")
        if not bars:
            print("  FAIL: no BTC daily bars returned")
            return False
        last = bars[-1]
        print(f"  BTC bars returned: {len(bars)}; latest: {last['date']} close={last['close']:,.0f}")
        if last["close"] < 1000:
            print("  FAIL: BTC close looks wrong (< $1000)")
            return False
        return True
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
        return False


async def check_coingecko() -> bool:
    print("\n=== CoinGecko ===")
    try:
        universe = await cg.get_top_universe(per_page=10)
        if not universe or len(universe) < 5:
            print(f"  FAIL: universe came back too small ({len(universe)})")
            return False
        print(f"  Top 10 fetched; #1 = {universe[0]['symbol'].upper()} (${universe[0].get('market_cap'):,.0f})")

        macro = await cg.get_global_macro()
        btc_d = macro.get("btc_dominance_pct") or 0
        total3 = macro.get("total3_mcap_usd") or 0
        if btc_d < 30 or btc_d > 80:
            print(f"  FAIL: BTC.D outside reasonable range: {btc_d}")
            return False
        if total3 <= 0:
            print(f"  FAIL: TOTAL3 derived = {total3}")
            return False
        print(f"  Macro: BTC.D={btc_d:.1f}%  TOTAL3=${total3:,.0f}")

        chart = await cg.get_market_chart("bitcoin", days=90)
        bars = cg.market_chart_to_daily_bars(chart)
        if len(bars) < 60:
            print(f"  FAIL: only {len(bars)} BTC bars (expected ~90)")
            return False
        print(f"  BTC market_chart 90d bars: {len(bars)}")
        return True
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
        return False


async def check_defillama() -> bool:
    print("\n=== DefiLlama ===")
    try:
        current = await llama.get_current_stablecoin_supply()
        total = current.get("major_stables_mcap") or 0
        if total < 100_000_000_000:  # < $100B = something broke
            print(f"  FAIL: stable mcap looks wrong: ${total:,.0f}")
            return False
        print(
            f"  Current stable mcap: ${total:,.0f} "
            f"(USDT=${current.get('usdt_mcap', 0):,.0f}, "
            f"USDC=${current.get('usdc_mcap', 0):,.0f})"
        )

        history = await llama.get_stablecoin_history(days=30)
        if len(history) < 20:
            print(f"  FAIL: only {len(history)} history days (expected ≥ 30)")
            return False
        latest_h = history[-1]
        print(f"  History 30d: {len(history)} rows; latest {latest_h['date']} = ${latest_h['total_stable_mcap']:,.0f}")
        return True
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
        return False


async def check_dexscreener() -> bool:
    print("\n=== DexScreener ===")
    # Solana SOL native — not a token, won't have a contract. Use a known
    # ETH USDC contract instead — should always resolve.
    USDC_ETH = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    try:
        quote = await ds.get_token_quote("ethereum", USDC_ETH)
        if not quote:
            print("  FAIL: USDC quote came back None")
            return False
        price = quote.get("price_usd")
        if price is None or abs(price - 1.0) > 0.05:
            print(f"  FAIL: USDC price = {price}, expected ~$1")
            return False
        print(f"  USDC@ETH price=${price:.4f} liq=${quote.get('liquidity_usd', 0):,.0f}")
        return True
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
        return False


async def main() -> int:
    results = await asyncio.gather(
        check_kraken(),
        check_coingecko(),
        check_defillama(),
        check_dexscreener(),
    )
    print("\n=== Summary ===")
    names = ["Kraken", "CoinGecko", "DefiLlama", "DexScreener"]
    for n, ok in zip(names, results):
        print(f"  {n}: {'PASS' if ok else 'FAIL'}")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
