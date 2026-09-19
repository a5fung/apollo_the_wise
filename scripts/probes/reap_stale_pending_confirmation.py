#!/usr/bin/env python3
"""Reap stale `pending_confirmation` phantom trades (#287, 2026-07-06).

Surfaced by the #184a coverage-drift detector on its first live day: 4 rows
(ABSI 6/24, FCEL 6/24, SNX 6/25, ACAD 6/26) stuck in `pending_confirmation` on
the LIVE account with `entry_order_id IS NULL`, 0 shares, never filled — signals
that created a trade row but whose order never got submitted/confirmed, and were
never reaped. Because `pending_confirmation` counts toward
MAX_CONCURRENT_LIVE_POSITIONS (get_open_position_count), they silently consume
live position-cap slots (4 of 5 on 2026-07-06 — a 2nd live HIGH would be blocked).

SAFETY (this MUTATES live trade state — ADR 0008 / feedback_no_docker_exec_for_trade_state):
  - Dry-run by DEFAULT. `--commit` required to write.
  - BROKER-CONFIRMED per row: reaps ONLY rows the broker positively confirms have
    NO position AND NO open order for that ticker+mode. A candidate that DOES have
    a broker position/order is NOT a phantom — it is surfaced LOUD and skipped
    (that would be a real D1/D2 mirror gap, not this cleanup's job).
  - DEGRADED-READ GUARD (#137): the broker reads use raise_on_error=True; if any
    read fails, the run ABORTS for that mode — never reap on an ambiguous read.
  - CONSERVATIVE age floor: only rows older than --min-age-days (default 2) so no
    current/prior-trading-day in-flight entry is ever touched.
  - Narrow predicate: status='pending_confirmation' AND entry_order_id IS NULL.
    A filled/order-bearing row is out of scope by construction.

Run (inside the market-agent container, which holds the Alpaca creds):
  docker exec apollo-market python scripts/reap_stale_pending_confirmation.py            # dry-run
  docker exec apollo-market python scripts/reap_stale_pending_confirmation.py --commit   # execute
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys


async def _run(commit: bool, min_age_days: int) -> int:
    from agents.market_intelligence.db import get_pool, log_audit_event
    from agents.market_intelligence.broker import alpaca_client

    pool = await get_pool()
    async with pool.acquire() as conn:
        candidates = await conn.fetch(
            """
            SELECT id, ticker, account_mode, signal_type, entry_shares,
                   (created_at AT TIME ZONE 'America/New_York')::timestamp(0) AS created_et,
                   alert_date
            FROM mi_live_trades
            WHERE status = 'pending_confirmation'
              AND entry_order_id IS NULL
              AND created_at < NOW() - ($1 || ' days')::interval
            ORDER BY created_at
            """,
            str(min_age_days),
        )

    if not candidates:
        print(f"No stale pending_confirmation phantoms older than {min_age_days}d. Nothing to do.")
        return 0

    modes = sorted({r["account_mode"] for r in candidates})
    print(f"Found {len(candidates)} candidate(s) across modes: {modes}\n")

    # Broker ground truth per mode — degraded-read guard: abort the whole mode on failure.
    broker: dict[str, dict] = {}
    for mode in modes:
        try:
            positions = await alpaca_client.get_all_positions(account_mode=mode, raise_on_error=True)
            open_orders = await alpaca_client.get_open_orders(account_mode=mode, raise_on_error=True)
        except Exception as e:
            print(f"  ⛔ BROKER READ FAILED for mode={mode} ({e!r}) — ABORTING (never reap on an "
                  f"ambiguous broker state). Re-run when the broker is reachable.")
            return 2
        broker[mode] = {
            "position_tickers": {p.get("symbol") for p in positions},
            "order_tickers": {o.get("symbol") for o in open_orders},
        }

    to_reap: list[dict] = []
    mirror_gaps: list[dict] = []
    for r in candidates:
        mode = r["account_mode"]
        tk = r["ticker"]
        b = broker[mode]
        has_broker_presence = tk in b["position_tickers"] or tk in b["order_tickers"]
        row = {
            "id": r["id"], "ticker": tk, "mode": mode, "created": str(r["created_et"]),
            "shares": r["entry_shares"], "signal": r["signal_type"],
        }
        (mirror_gaps if has_broker_presence else to_reap).append(row)

    # Report — always printed (dry-run and commit).
    print("=== PHANTOMS to reap (broker confirms NO position + NO open order) ===")
    for r in to_reap:
        print(f"  id={r['id']:>5}  {r['ticker']:<6} {r['mode']:<5} created {r['created']}  "
              f"shares={r['shares']}  signal={r['signal']}")
    if not to_reap:
        print("  (none)")
    if mirror_gaps:
        print("\n=== ⚠ NOT reaping — broker HAS a position/order (real mirror gap, investigate) ===")
        for r in mirror_gaps:
            print(f"  id={r['id']:>5}  {r['ticker']:<6} {r['mode']:<5} — broker presence found; SKIPPED")

    if not commit:
        print(f"\nDRY-RUN. {len(to_reap)} row(s) would be reaped. Re-run with --commit to execute.")
        return 0

    if not to_reap:
        print("\nNothing to reap after broker confirmation.")
        return 0

    # Commit: reap the broker-confirmed phantoms.
    reaped = 0
    async with pool.acquire() as conn:
        for r in to_reap:
            # Re-assert the predicate in the UPDATE so a row that changed since the
            # read (e.g. just got an order) is NOT touched (belt-and-suspenders).
            res = await conn.execute(
                """
                UPDATE mi_live_trades
                SET status = 'cancelled',
                    closed_at = NOW(),
                    pnl_attribution = 'phantom_reap_287'
                WHERE id = $1
                  AND status = 'pending_confirmation'
                  AND entry_order_id IS NULL
                """,
                r["id"],
            )
            if res.endswith("1"):
                reaped += 1
                await log_audit_event(
                    "phantom_pending_confirmation_reaped",
                    f"{r['ticker']} (id={r['id']}, {r['mode']}) reaped — stale pending_confirmation, "
                    f"broker-confirmed absent (#287)",
                    json.dumps(r),
                )
            else:
                print(f"  (id={r['id']} {r['ticker']} changed since read — skipped, not reaped)")

    print(f"\n✅ Reaped {reaped} phantom row(s). They no longer consume position-cap slots.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Reap stale pending_confirmation phantom trades (#287)")
    ap.add_argument("--commit", action="store_true", help="Execute the reap (default: dry-run)")
    ap.add_argument("--min-age-days", type=int, default=2,
                    help="Only reap rows older than this many days (default: 2)")
    args = ap.parse_args()
    return asyncio.run(_run(commit=args.commit, min_age_days=args.min_age_days))


if __name__ == "__main__":
    sys.exit(main())
