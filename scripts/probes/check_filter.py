import asyncio, sys
sys.path.insert(0, '/app')
from datetime import date

async def check():
    from agents.market_intelligence.db import get_correlation_clusters
    clusters = await get_correlation_clusters(date(2026, 4, 17))
    print(f"Today: {len(clusters)} clusters persisted")
    top = sorted(clusters, key=lambda x: -x['mean_corr'])[:12]
    for i, c in enumerate(top):
        tickers = " ".join(c['tickers'])
        print(f"  {chr(65+i)} corr={c['mean_corr']:.2f} RS={c['avg_rs']:.0f}: {tickers}")

asyncio.run(check())
