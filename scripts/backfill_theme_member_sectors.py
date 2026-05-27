"""Backfill missing sector data for active theme members (#126 root cause).

The nightly sector enrichment in rs_engine._enrich_sectors only runs on
the top 300 RS-ranked tickers. Tickers outside that band that get
assigned to themes (typically via description-driven assignment) never
get their sector populated in mi_ticker_overrides.

Cost of the gap: downstream coherence checks (and potential future
coherence guards) have no signal to compare against. SWBI in the
"Firearms & Personal Defense Manufacturing" theme was visible because
it's a firearms name in a firearms theme — but LINC (Lincoln
Educational Services) sat in the same theme with no sector to flag the
mismatch.

This script bulk-fetches FMP profiles for any current active-theme
member with empty sector and upserts them. Safe to re-run.

Run: docker exec apollo-market python -m scripts.backfill_theme_member_sectors
"""
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backfill_sectors")


async def main():
    from agents.market_intelligence.db import (
        get_pool, upsert_ticker_sectors_batch,
    )
    from agents.market_intelligence.collector import get_fmp_profile

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            WITH theme_members AS (
                SELECT DISTINCT unnest(tickers) AS ticker
                FROM mi_themes
                WHERE theme_date > CURRENT_DATE - INTERVAL '14 days'
                  AND stage != 'Retired'
            )
            SELECT tm.ticker
            FROM theme_members tm
            LEFT JOIN mi_ticker_overrides o ON o.ticker = tm.ticker
            WHERE o.sector IS NULL OR o.sector = ''
            ORDER BY tm.ticker
        """)
    tickers = [r["ticker"] for r in rows]
    logger.info(f"Found {len(tickers)} active-theme members missing sector data")
    if not tickers:
        return

    sem = asyncio.Semaphore(10)

    async def _fetch_one(ticker: str):
        async with sem:
            try:
                profile = await get_fmp_profile(ticker)
                return ticker, profile
            except Exception as e:
                logger.warning(f"FMP fetch failed for {ticker}: {e}")
                return ticker, None

    results = await asyncio.gather(*[_fetch_one(t) for t in tickers])

    new_sectors: dict[str, dict] = {}
    no_data: list[str] = []
    for ticker, profile in results:
        if not profile:
            no_data.append(ticker)
            continue
        sector = profile.get("sector", "")
        industry = profile.get("industry", "")
        if sector:
            new_sectors[ticker] = {"sector": sector, "industry": industry}
            logger.info(f"  {ticker:<6} → {sector} / {industry}")
        else:
            no_data.append(ticker)

    if new_sectors:
        n = await upsert_ticker_sectors_batch(new_sectors)
        logger.info(f"Upserted sector data for {n} tickers")
    if no_data:
        logger.info(f"No FMP sector data for {len(no_data)} tickers: {no_data}")


if __name__ == "__main__":
    asyncio.run(main())
