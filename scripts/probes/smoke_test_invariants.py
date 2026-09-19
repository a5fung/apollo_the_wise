"""
Smoke-test the 11 invariants in `audit_invariants.all_invariants(...)` against
the current DB. Calls each function and prints `(name, passed, summary)` for
every one. Surfaces SQL errors and signature mismatches before the scheduled
scanner has a chance to swallow them.

Usage:
    python scripts/smoke_test_invariants.py
    python scripts/smoke_test_invariants.py --days 30
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import traceback
from datetime import datetime, timedelta

from agents.market_intelligence.audit_invariants import all_invariants
from agents.market_intelligence.collector import et_today
from agents.market_intelligence.db import get_pool


GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"


async def main(days: int) -> int:
    since = et_today() - timedelta(days=days)
    since_dt = datetime.combine(since, datetime.min.time())
    now_et = datetime.now()
    print(f"\n── Invariant smoke test · window: {days}d (since {since}) ──\n")

    pool = await get_pool()
    failures = 0
    errors = 0
    async with pool.acquire() as conn:
        for name, fn, kwargs in all_invariants(since=since, since_dt=since_dt, now_et=now_et):
            try:
                ok, body = await fn(conn, **kwargs)
            except Exception as e:
                errors += 1
                print(f"  {RED}✖ ERROR{RESET} {name:<32} {type(e).__name__}: {e}")
                traceback.print_exc()
                continue
            mark = f"{GREEN}✅{RESET}" if ok else f"{YELLOW}⚠️{RESET}"
            if not ok:
                failures += 1
            summary = body.get("summary", "")
            print(f"  {mark} {name:<32} {summary}")

    print()
    if errors:
        print(f"{RED}❌ {errors} invariants raised exceptions — fix before deploying{RESET}")
        return 2
    print(f"{GREEN}✓ all 11 invariants executed cleanly{RESET} ({failures} currently breaching)")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=30)
    args = p.parse_args()
    sys.exit(asyncio.run(main(args.days)))
