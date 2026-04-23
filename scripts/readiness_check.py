"""
Readiness check for the LIVE_TRADING_ENABLED flip.

Encodes the explicit gating criteria from the 2026-04-23 paper-validation plan
as concrete SQL. Run any time during the validation window to see where the
system stands; run it deliberately at the cutover decision point (~2026-05-23)
as the final go/no-go.

Checks (every check prints ✅ / ❌ and a number):
  1. Naked positions          — mi_live_trades filled rows with no stop_order_id
                                outside a 60s placement grace window.
  2. Reason-coverage invariant — every mi_live_trades row has a terminal status
                                 or a bounded skip_reason.
  3. Silent audit errors       — mi_audit_log '*_error' events in the window.
  4. Paper trade sample size   — closed mi_live_trades rows in the window.
  5. Regime check              — current mi_market_regime must not be Crisis.
  6. Feed health               — orb_subscribe_failed count in the last 24h.

Usage:
    python scripts/readiness_check.py                  # default 30-day window
    python scripts/readiness_check.py --days 14
    python scripts/readiness_check.py --verbose        # dump offending rows
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import timedelta

from agents.market_intelligence.collector import et_today
from agents.market_intelligence.db import get_pool


GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def _fmt(ok: bool, label: str, detail: str) -> str:
    mark = f"{GREEN}✅{RESET}" if ok else f"{RED}❌{RESET}"
    return f"  {mark} {label:<32} {detail}"


async def check_naked_positions(conn, verbose: bool) -> bool:
    # Any row in a live state with no protective stop is a naked position.
    # The 60s grace accounts for the brief window between entry fill and the
    # stop-placement response from Alpaca.
    rows = await conn.fetch(
        """
        SELECT ticker, alert_date, status, stop_order_id, filled_at
        FROM mi_live_trades
        WHERE status = 'filled'
          AND stop_order_id IS NULL
          AND (filled_at IS NULL OR filled_at < NOW() - INTERVAL '60 seconds')
        ORDER BY alert_date DESC
        """
    )
    ok = len(rows) == 0
    print(_fmt(ok, "Naked positions", f"{len(rows)} filled rows w/o stop"))
    if verbose and rows:
        for r in rows:
            print(f"      • {r['ticker']} {r['alert_date']} filled_at={r['filled_at']}")
    return ok


async def check_reason_coverage(conn, since, verbose: bool) -> bool:
    # Reason-coverage invariant: every row either has a terminal status or a
    # bounded skip_reason. A row with both NULL is a silent drop.
    rows = await conn.fetch(
        """
        SELECT ticker, alert_date, status, skip_reason
        FROM mi_live_trades
        WHERE alert_date >= $1
          AND status IS NULL
          AND skip_reason IS NULL
        ORDER BY alert_date DESC
        """,
        since,
    )
    ok = len(rows) == 0
    print(_fmt(ok, "Reason-coverage invariant", f"{len(rows)} silent-drop rows"))
    if verbose and rows:
        for r in rows:
            print(f"      • {r['ticker']} {r['alert_date']}")
    return ok


async def check_audit_errors(conn, since, verbose: bool) -> bool:
    # Any error bucket in the window is a reason to investigate before flipping.
    # This check is lenient on count but strict on 0-known failures at cutover.
    rows = await conn.fetch(
        """
        SELECT event_type, COUNT(*) AS n
        FROM mi_audit_log
        WHERE event_type LIKE '%_error'
          AND created_at >= $1
        GROUP BY event_type
        ORDER BY n DESC
        """,
        since,
    )
    total = sum(int(r["n"]) for r in rows)
    ok = total == 0
    detail = f"{total} events" if total else "clean"
    print(_fmt(ok, "Silent audit errors", detail))
    if verbose and rows:
        for r in rows:
            print(f"      • {r['event_type']}: {r['n']}")
    return ok


async def check_closed_trade_sample(conn, since) -> bool:
    row = await conn.fetchrow(
        """
        SELECT COUNT(*) AS n
        FROM mi_live_trades
        WHERE status = 'closed'
          AND alert_date >= $1
          AND stop_price IS NOT NULL
        """,
        since,
    )
    n = int(row["n"] or 0)
    ok = n >= 10
    print(_fmt(ok, "Closed paper trades", f"{n}/10 needed"))
    return ok


async def check_regime(conn) -> bool:
    row = await conn.fetchrow(
        """
        SELECT regime
        FROM mi_market_regime
        ORDER BY regime_date DESC
        LIMIT 1
        """
    )
    regime = (row["regime"] if row else "Unknown") or "Unknown"
    ok = regime.lower() != "crisis"
    print(_fmt(ok, "Market regime", f"{regime}"))
    return ok


async def check_feed_health(conn) -> bool:
    # Rolling 24h subscribe failures — the most actionable feed-health signal.
    # A subscribe failure means the SDK couldn't even register the ticker;
    # zero-range is informational on IEX and only meaningful on SIP.
    row = await conn.fetchrow(
        """
        SELECT
          COUNT(*) FILTER (WHERE event_type = 'orb_subscribe_failed') AS subscribe_fail,
          COUNT(*) FILTER (WHERE event_type = 'bar_stream_disconnect') AS disconnect
        FROM mi_audit_log
        WHERE created_at >= NOW() - INTERVAL '24 hours'
        """
    )
    fails = int(row["subscribe_fail"] or 0)
    drops = int(row["disconnect"] or 0)
    ok = fails == 0
    print(_fmt(ok, "Feed health (24h)", f"{fails} subscribe-fail · {drops} disconnect"))
    return ok


async def main(days: int, verbose: bool) -> int:
    since = et_today() - timedelta(days=days)
    print(f"\n── Readiness check · window: {days}d (since {since}) ──\n")

    pool = await get_pool()
    async with pool.acquire() as conn:
        results = [
            await check_naked_positions(conn, verbose),
            await check_reason_coverage(conn, since, verbose),
            await check_audit_errors(conn, since, verbose),
            await check_closed_trade_sample(conn, since),
            await check_regime(conn),
            await check_feed_health(conn),
        ]

    print()
    passed = sum(1 for r in results if r)
    total = len(results)
    if passed == total:
        print(f"{GREEN}✅ All {total} checks passed — safe to flip LIVE_TRADING_ENABLED=true{RESET}")
        return 0
    print(f"{RED}❌ {total - passed}/{total} checks failed — DO NOT flip yet{RESET}")
    print(f"{YELLOW}   Rerun with --verbose for offending rows.{RESET}")
    return 1


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=30, help="validation window in days (default 30)")
    p.add_argument("--verbose", "-v", action="store_true", help="dump offending rows")
    args = p.parse_args()
    sys.exit(asyncio.run(main(args.days, args.verbose)))
