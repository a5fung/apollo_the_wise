"""#624 backfill — PRE-REGISTRATION sizing read #2 (2026-10-06). READ-ONLY, INPUTS ONLY.

The minute-pull budget after the no-lookahead superset prefilter: daily high >= 1.15 x prior
close AND the day's FULL volume beats >= 90% of the rolling-20-session-mean history ending in
the 60 calendar days before D (a tick's cumulative volume cannot exceed the day's — the
prefilter only removes rows the rule could never admit; checked again on the calibration set).
Raw floors here use mi_splits (coverage starts 2026-03-02, so 2024-25 raw values are
APPROXIMATE — the real run re-pulls Polygon splits since 2024-01-02). No outcome table is read.
"""
import asyncio

from agents.market_intelligence.db import get_pool

W0, W1 = "2024-01-02", "2026-09-03"


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        await c.execute("SET statement_timeout = '900s'")
        rows = await c.fetch(f"""
            WITH d AS (
              SELECT ticker, trade_date, open_price o, high_price h, volume v,
                     lag(close)  OVER w pc, lag(volume) OVER w pv,
                     avg(volume) OVER (PARTITION BY ticker ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) m20,
                     count(*)    OVER (PARTITION BY ticker ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) n20
              FROM mi_daily_closes WHERE trade_date >= '2023-08-01'
              WINDOW w AS (PARTITION BY ticker ORDER BY trade_date)),
            cand AS (
              SELECT d.*, COALESCE((SELECT exp(sum(ln(s.split_to::float / s.split_from)))
                                    FROM mi_splits s WHERE s.ticker = d.ticker
                                      AND s.execution_date >= d.trade_date
                                      AND s.adjustment_applied), 1.0) fac
              FROM d
              WHERE d.trade_date BETWEEN '{W0}' AND '{W1}' AND d.pc > 0 AND d.h >= d.pc * 1.15
                AND d.ticker ~ '^[A-Z]{{1,5}}$'),
            cand2 AS (
              SELECT * FROM cand WHERE pc * fac >= 5 AND pv / fac >= 50000),
            hist AS (
              SELECT c2.ticker, c2.trade_date,
                     count(r.m20) n_hist,
                     count(r.m20) FILTER (WHERE c2.v > r.m20) n_below
              FROM cand2 c2 JOIN d r ON r.ticker = c2.ticker
                AND r.trade_date < c2.trade_date AND r.trade_date >= c2.trade_date - 60 AND r.n20 = 20
              GROUP BY 1, 2)
            SELECT extract(year FROM c2.trade_date)::int yr,
                   count(*) superset_high15,
                   count(*) FILTER (WHERE c2.o >= c2.pc * 1.15) open15,
                   count(*) FILTER (WHERE h.n_hist > 0 AND h.n_below::float / h.n_hist >= 0.9) day_vol_p90,
                   count(*) FILTER (WHERE h.n_hist > 0 AND h.n_below::float / h.n_hist >= 0.9
                                    AND c2.o >= c2.pc * 1.15) day_vol_p90_open15,
                   count(*) FILTER (WHERE h.n_hist > 0 AND h.n_below::float / h.n_hist >= 0.9
                                    AND c2.ticker NOT IN (SELECT ticker FROM mi_security_types)) day_vol_p90_untyped,
                   count(*) FILTER (WHERE h.n_hist > 0 AND h.n_below::float / h.n_hist >= 0.9
                                    AND c2.ticker IN (SELECT ticker FROM mi_security_types
                                                      WHERE security_type IN ('CS','ADRC'))) day_vol_p90_cs_adrc,
                   count(*) FILTER (WHERE h.n_hist IS NULL OR h.n_hist = 0) no_history,
                   count(DISTINCT c2.ticker) FILTER (WHERE h.n_hist > 0 AND h.n_below::float / h.n_hist >= 0.9) names_p90
            FROM cand2 c2 LEFT JOIN hist h USING (ticker, trade_date)
            GROUP BY 1 ORDER BY 1""")
        for r in rows:
            print(dict(r))
        print("=== distinct untyped tickers in the p90 superset (Polygon type lookups needed)")
        # same superset, distinct untyped names
        print(await c.fetchval(f"""
            SELECT count(DISTINCT ticker) FROM mi_daily_closes x
            WHERE trade_date BETWEEN '{W0}' AND '{W1}' AND ticker ~ '^[A-Z]{{1,5}}$'
              AND ticker NOT IN (SELECT ticker FROM mi_security_types)"""))


asyncio.run(main())
