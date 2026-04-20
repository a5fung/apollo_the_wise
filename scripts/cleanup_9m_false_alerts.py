#!/usr/bin/env python3
"""
Identify and optionally remove false-positive 9M EP alerts logged before
the ETF/non-stock filter was added (2026-04-20 session 6).

A false positive is any ticker the current ninem_detector.py would now reject:
  1. In SKIP_TICKERS     — hardcoded leveraged/ETF exclusion list
  2. Non-CS/ADRC type    — ETFs, warrants, etc. per mi_security_types
  3. Bad ticker format   — length > 5 chars or contains "." (ETF share classes)

Also removes derived mi_9m_sugar_babies rows for the same tickers.

Usage:
  python scripts/cleanup_9m_false_alerts.py           # dry run — preview only
  python scripts/cleanup_9m_false_alerts.py --delete  # commit the deletes
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.market_intelligence.constants import SKIP_TICKERS
from agents.market_intelligence.db import get_pool


async def main(delete: bool) -> None:
    pool = await get_pool()

    skip_list = list(SKIP_TICKERS)

    async with pool.acquire() as conn:

        # 1. Hardcoded SKIP_TICKERS (leveraged ETFs, index ETFs, commodity ETFs)
        skip_rows = await conn.fetch("""
            SELECT ticker, alert_date, today_volume, current_price
            FROM mi_9m_ep_alerts
            WHERE ticker = ANY($1::text[])
            ORDER BY alert_date, ticker
        """, skip_list)

        # 2. Anything classified as non-CS/ADRC in mi_security_types
        #    (ETFs, closed-end funds, warrants, rights, structured products)
        non_stock_rows = await conn.fetch("""
            SELECT a.ticker, a.alert_date, a.today_volume, a.current_price,
                   st.security_type
            FROM mi_9m_ep_alerts a
            JOIN mi_security_types st ON st.ticker = a.ticker
            WHERE st.security_type NOT IN ('CS', 'ADRC')
              AND a.ticker != ALL($1::text[])
            ORDER BY a.alert_date, a.ticker
        """, skip_list)

        # 3. Bad ticker format — ETF share classes often have dots or long names
        format_rows = await conn.fetch("""
            SELECT ticker, alert_date, today_volume, current_price
            FROM mi_9m_ep_alerts
            WHERE (length(ticker) > 5 OR ticker LIKE '%.%')
              AND ticker != ALL($1::text[])
            ORDER BY alert_date, ticker
        """, skip_list)

        all_false = (
            {r["ticker"] for r in skip_rows}
            | {r["ticker"] for r in non_stock_rows}
            | {r["ticker"] for r in format_rows}
        )

        # Sugar babies derived from false alert tickers
        sugar_rows = await conn.fetch("""
            SELECT ticker, alert_date, day2_status
            FROM mi_9m_sugar_babies
            WHERE ticker = ANY($1::text[])
            ORDER BY alert_date, ticker
        """, list(all_false))

    # ── Report ────────────────────────────────────────────────────────────────
    print(f"\n{'DRY RUN — no changes made' if not delete else '*** DELETING ***'}")
    print("=" * 65)

    sections = [
        ("1. SKIP_TICKERS (ETFs / leveraged products)", skip_rows, None),
        ("2. Non-CS/ADRC in mi_security_types", non_stock_rows, "security_type"),
        ("3. Bad ticker format (>5 chars or contains '.')", format_rows, None),
    ]
    for label, rows, extra_col in sections:
        print(f"\n{label}:  {len(rows)} alerts")
        for r in rows:
            extra = f"  [{r[extra_col]}]" if extra_col else ""
            print(f"  {r['ticker']:<8}  {r['alert_date']}  "
                  f"vol={r['today_volume']:>12,.0f}  ${r['current_price']:.2f}{extra}")

    print(f"\n4. Sugar babies from false tickers:  {len(sugar_rows)}")
    for r in sugar_rows:
        print(f"  {r['ticker']:<8}  {r['alert_date']}  status={r['day2_status']}")

    total = len(skip_rows) + len(non_stock_rows) + len(format_rows)
    print(f"\nSummary: {total} false EP alerts + {len(sugar_rows)} sugar babies")
    print(f"Unique false tickers: {len(all_false)}")

    if not delete:
        print("\nRe-run with --delete to remove them.")
        await pool.close()
        return

    if not all_false:
        print("\nNothing to delete.")
        await pool.close()
        return

    false_list = list(all_false)
    async with pool.acquire() as conn:
        n_sb = await conn.fetchval(
            "WITH d AS (DELETE FROM mi_9m_sugar_babies WHERE ticker = ANY($1::text[]) RETURNING 1)"
            " SELECT count(*) FROM d",
            false_list,
        )
        n_alerts = await conn.fetchval(
            "WITH d AS (DELETE FROM mi_9m_ep_alerts WHERE ticker = ANY($1::text[]) RETURNING 1)"
            " SELECT count(*) FROM d",
            false_list,
        )

    print(f"\nDeleted {n_alerts} rows from mi_9m_ep_alerts")
    print(f"Deleted {n_sb} rows from mi_9m_sugar_babies")
    await pool.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean up false-positive 9M EP alerts")
    parser.add_argument("--delete", action="store_true",
                        help="Commit deletes (default: dry run)")
    args = parser.parse_args()
    asyncio.run(main(args.delete))
