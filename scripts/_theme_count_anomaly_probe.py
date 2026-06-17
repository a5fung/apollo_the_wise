"""Read-only diagnostic for the theme_count_active decline (#325, 2026-06-17).

Findings it produced: active themes 42(6/8)→15(6/17) monotonic; NOT regime (28/40 top RS-100
leaders uncovered, ALL with descriptions once DB overrides are merged), NOT the description-filter,
NOT cooldown-flood (only ~24 cooled tickers). The collapse is in discovery-LLM → score →
birth-validate, which `theme_engine.theme_engine_funnel` (#325 telemetry) now makes visible per run.
Run: ssh ... "docker exec -i apollo-market python -" < scripts/_theme_count_anomaly_probe.py
"""
import asyncio
from agents.market_intelligence.db import (
    get_active_themes, get_cooldown_set, get_pool, get_ticker_overrides)
from agents.market_intelligence import universe


async def main():
    universe.apply_overrides(await get_ticker_overrides())  # replicate agent startup desc-merge
    TD = universe.TICKER_DESC
    themes = await get_active_themes()
    covered = {tk.upper() for t in themes for tk in (t.get("tickers") or [])}
    cd_tickers = {t for t, _ in await get_cooldown_set()}
    print(f"active themes={len(themes)}  covered tickers={len(covered)}  active cooldowns={len(cd_tickers)}")

    pool = await get_pool()
    async with pool.acquire() as c:
        d = await c.fetchval("SELECT MAX(score_date) FROM mi_stock_scores")
        leaders = await c.fetch("""
            SELECT ticker, rs_composite, rs_rank, sector FROM mi_stock_scores
            WHERE score_date = $1 ORDER BY rs_composite DESC NULLS LAST LIMIT 40
        """, d)
        births = await c.fetch("""
            SELECT first_seen, COUNT(*) n FROM (
                SELECT name, MIN(theme_date) first_seen FROM mi_themes GROUP BY name
            ) f WHERE first_seen >= CURRENT_DATE - INTERVAL '16 days'
            GROUP BY first_seen ORDER BY first_seen DESC
        """)
    print(f"\nNEW theme births last 16d: {'NONE' if not births else ''}")
    for r in births:
        print(f"  {r['first_seen']}  {r['n']}")

    uncovered = [r for r in leaders if r["ticker"].upper() not in covered]
    print(f"\ntop-40 RS leaders: {len(leaders)-len(uncovered)} covered, {len(uncovered)} UNCOVERED")
    for r in uncovered:
        tk = r["ticker"].upper()
        flags = []
        if not TD.get(tk):
            flags.append("NO-DESC")
        if tk in cd_tickers:
            flags.append("COOLDOWN")
        print(f"  {tk:6} RS{r['rs_composite']:5.0f} #{r['rs_rank']:<4} "
              f"{(TD.get(tk) or '(no desc)')[:50]:50} {' '.join(flags)}")


asyncio.run(main())
