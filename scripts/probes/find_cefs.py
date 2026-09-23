"""One-time script: find CEFs/trusts hiding as EQUITY in top RS stocks."""
import asyncio

async def find_cefs():
    from agents.market_intelligence.db import get_pool, initialize_schema, latest_complete_score_date_sql
    await initialize_schema()
    pool = await get_pool()

    async with pool.acquire() as conn:
        # #554: was raw MAX(score_date) — could pick a stray single-row day.
        rows = await conn.fetch(f"""
            SELECT s.ticker, s.rs_composite, s.close
            FROM mi_stock_scores s
            JOIN mi_tracked_stocks t ON t.ticker = s.ticker
            WHERE s.score_date = {latest_complete_score_date_sql()}
            AND t.active = TRUE AND t.quote_type = 'EQUITY'
            AND s.rs_composite >= 50
            ORDER BY s.rs_composite DESC
            LIMIT 100
        """)
        tickers = [r["ticker"] for r in rows]

    import yfinance as yf
    cefs = []
    for i, tk in enumerate(tickers):
        try:
            info = yf.Ticker(tk).info
            name = info.get("longName", "")
            name_lower = name.lower()
            is_cef = any(kw in name_lower for kw in [
                "trust", " fund", "income", "closed-end",
                "preferred", "warrant", "debenture", "notes",
                "capital acquisition",
            ])
            if is_cef:
                rs = next((r["rs_composite"] for r in rows if r["ticker"] == tk), 0)
                cefs.append((tk, rs, name))
                print(f"  CEF: {tk:8s} RS {rs:5.1f}  {name}")
        except Exception:
            pass
        if (i + 1) % 25 == 0:
            print(f"  ...checked {i+1}/{len(tickers)}")

    print(f"\nFound {len(cefs)} CEFs/trusts in top 100 RS equities")

    # Reclassify them
    if cefs:
        async with pool.acquire() as conn:
            for tk, rs, name in cefs:
                await conn.execute(
                    "UPDATE mi_tracked_stocks SET quote_type = 'CEF' WHERE ticker = $1",
                    tk,
                )
        print(f"Reclassified {len(cefs)} tickers as CEF — now excluded from RS leaders and alerts")

asyncio.run(find_cefs())
