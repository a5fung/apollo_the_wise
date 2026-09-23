"""
Readiness check for the LIVE_TRADING_ENABLED flip.

Encodes the explicit gating criteria from the 2026-04-23 paper-validation plan
as concrete SQL. Run any time during the validation window to see where the
system stands; run it deliberately at the cutover decision point (~2026-05-23)
as the final go/no-go.

Implementation note: invariant SQL is owned by
`agents/market_intelligence/audit_invariants.py` so the CLI here and the
scheduled `system_audit.py` scanner cannot drift apart. The "Closed paper
trades" check is local — it's a sample-size threshold, not a correctness
invariant, so it doesn't belong in the shared library.

Checks (every check prints ✅ / ❌ and a number):
  1. Naked positions          — filled rows with no stop_order_id past 60s.
  2. Reason-coverage invariant — every row has a status or skip_reason.
  3. Silent audit errors       — '*_error' events in the window.
  4. Paper trade sample size   — closed rows in the window.
  5. Regime check              — current regime must not be Crisis.
  6. Feed health               — orb_subscribe_failed count in last 24h.

Usage:
    python scripts/readiness_check.py                  # default 30-day window
    python scripts/readiness_check.py --days 14
    python scripts/readiness_check.py --verbose        # dump offending rows
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta

from agents.market_intelligence.audit_invariants import (
    check_audit_error_window,
    check_feed_health_24h,
    check_naked_position,
    check_reason_coverage,
    check_regime_stuck_crisis,
)
from agents.market_intelligence.collector import et_today
from agents.market_intelligence.db import get_pool


GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def _fmt(ok: bool, label: str, detail: str) -> str:
    mark = f"{GREEN}✅{RESET}" if ok else f"{RED}❌{RESET}"
    return f"  {mark} {label:<32} {detail}"


def _print_invariant(ok: bool, label: str, body: dict, verbose: bool) -> None:
    print(_fmt(ok, label, body.get("summary", "")))
    if verbose and body.get("offending"):
        for line in body["offending"]:
            print(f"      • {line}")


async def _check_closed_trade_sample(conn, since) -> bool:
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


async def main(days: int, verbose: bool) -> int:
    since = et_today() - timedelta(days=days)
    since_dt = datetime.combine(since, datetime.min.time())
    print(f"\n── Readiness check · window: {days}d (since {since}) ──\n")

    pool = await get_pool()
    async with pool.acquire() as conn:
        ok_naked, body_naked = await check_naked_position(conn)
        _print_invariant(ok_naked, "Naked positions", body_naked, verbose)

        ok_reason, body_reason = await check_reason_coverage(conn, since=since)
        _print_invariant(ok_reason, "Reason-coverage invariant", body_reason, verbose)

        ok_errors, body_errors = await check_audit_error_window(conn, since=since_dt)
        _print_invariant(ok_errors, "Silent audit errors", body_errors, verbose)

        ok_sample = await _check_closed_trade_sample(conn, since)

        _, body_regime = await check_regime_stuck_crisis(conn)
        # Readiness CLI uses a stricter "must not be Crisis right now" gate
        # than the 30-day stuck check; the invariant body exposes the latest
        # regime as a structured field.
        latest_regime = body_regime.get("latest_regime", "Unknown")
        ok_regime = latest_regime.lower() != "crisis"
        print(_fmt(ok_regime, "Market regime", latest_regime))

        ok_feed, body_feed = await check_feed_health_24h(conn)
        _print_invariant(ok_feed, "Feed health (24h)", body_feed, verbose=False)

    print()
    results = [ok_naked, ok_reason, ok_errors, ok_sample, ok_regime, ok_feed]
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
