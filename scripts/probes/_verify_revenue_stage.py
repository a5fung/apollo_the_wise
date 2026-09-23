"""Verify post-#63 revenue-stage behavior on common tickers."""
import asyncio
import os


async def main():
    print(f"env: REVENUE_STAGE_MIN_USD={os.environ.get('REVENUE_STAGE_MIN_USD', 'NOT SET')}")
    from agents.market_intelligence.earnings_calendar import is_revenue_stage, _REVENUE_STAGE_MIN_USD
    print(f"loaded _REVENUE_STAGE_MIN_USD: ${_REVENUE_STAGE_MIN_USD}")
    print()
    import yfinance as yf
    for t in ["IMVT", "ROIV", "CAVA", "NVDA", "AAPL"]:
        cal = yf.Ticker(t).calendar
        rev = cal.get("Revenue Average") if isinstance(cal, dict) else None
        rs = await is_revenue_stage(t)
        print(f"  {t}: Revenue Average={rev!r}  revenue_stage={rs}")


if __name__ == "__main__":
    asyncio.run(main())
