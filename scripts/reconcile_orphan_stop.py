"""Reconcile a `mi_live_trades` row whose stop_order_id is NULL but Alpaca
has a live stop order for the position.

Origin: TEAM 5/01 surfaced 2026-05-04 — entry's child stop_loss leg was
never captured into DB (same shape as the original 4/24 INTC OTO bug).
The L1 `naked_position` invariant correctly flagged the DB-vs-broker
mismatch; the actual position was protected the whole time.

Usage on prod (paper or live, both supported):
    docker compose -f docker/docker-compose.prod.yml exec market-agent \
        python -m scripts.reconcile_orphan_stop --ticker TEAM --alert-date 2026-05-01

By default this runs in DRY-RUN mode — prints what it would do without
writing. Pass --apply to execute.

The script:
  1. Reads the (ticker, alert_date) row from mi_live_trades.
  2. Queries Alpaca for open orders on the ticker.
  3. Picks the matching stop order via `extract_stop_leg_id`-style logic
     (stop_price set OR type contains "stop"), validating qty matches
     `remaining_shares` (or, on partial holds, ≤ remaining_shares).
  4. UPDATEs `stop_order_id` (and `stop_price` if missing) on that row.
  5. Logs audit event `naked_position_reconciled` so the post-EOD audit
     scan picks it up in the next L2 metric sample.

Idempotent: re-running on an already-fixed row is a no-op.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date


async def _main(ticker: str, alert_date: date, apply: bool) -> int:
    # Local imports — module wires up env via package init
    from agents.market_intelligence.db import get_pool, log_audit_event
    from agents.market_intelligence.broker import alpaca_client as alpaca

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, ticker, alert_date, status, remaining_shares,
                   stop_order_id, stop_price, hard_stop, entry_price, filled_at
            FROM mi_live_trades
            WHERE ticker = $1 AND alert_date = $2
            """,
            ticker, alert_date,
        )

    if not row:
        print(f"[ABORT] no mi_live_trades row for {ticker} {alert_date}")
        return 2
    trade = dict(row)

    print("DB row:")
    print(f"  id={trade['id']} status={trade['status']} "
          f"remaining_shares={trade['remaining_shares']} "
          f"stop_order_id={trade['stop_order_id']} stop_price={trade['stop_price']} "
          f"hard_stop={trade['hard_stop']} entry_price={trade['entry_price']}")

    if trade["status"] != "filled":
        print(f"[ABORT] expected status='filled', got '{trade['status']}'")
        return 2
    if trade["stop_order_id"]:
        print(f"[NO-OP] stop_order_id already set ({trade['stop_order_id']}) — nothing to reconcile")
        return 0
    if not trade["remaining_shares"] or trade["remaining_shares"] <= 0:
        print(f"[ABORT] remaining_shares={trade['remaining_shares']}; nothing to protect")
        return 2

    # Query Alpaca for open orders on this ticker.
    open_orders = await alpaca.get_open_orders(ticker=ticker)
    print(f"\nAlpaca open orders for {ticker}: {len(open_orders)}")
    for o in open_orders:
        print(f"  id={o.get('id')} side={o.get('side')} type={o.get('order_type')} "
              f"qty={o.get('qty')} stop={o.get('stop_price')} status={o.get('status')}")

    # Pick the live stop. Same heuristic as extract_stop_leg_id but on top-level orders.
    candidates = []
    for o in open_orders:
        # Use substring `in` rather than equality — Python 3.11+ stringifies
        # alpaca-py enums as `OrderSide.SELL` / `OrderType.STOP` (not `sell`/`stop`).
        side_str = str(o.get("side", "")).lower()
        if "sell" not in side_str:
            continue
        type_str = str(o.get("order_type") or o.get("type") or "").lower()
        has_stop_price = o.get("stop_price") not in (None, "", 0, "0")
        if has_stop_price or "stop" in type_str:
            candidates.append(o)

    if not candidates:
        print(f"\n[ABORT] no open SELL stop order found for {ticker} on Alpaca side. "
              f"Position may genuinely be naked — investigate before reconciling.")
        return 3

    # Prefer a candidate whose qty matches remaining_shares exactly.
    rem = float(trade["remaining_shares"])
    exact = next((c for c in candidates if abs(float(c.get("qty") or 0) - rem) < 0.5), None)
    chosen = exact or candidates[0]

    if len(candidates) > 1 and exact is None:
        print(f"\n[WARN] {len(candidates)} stop candidates and none match qty={rem} exactly. "
              f"Using first ({chosen.get('id')}). Verify manually before applying.")
    if exact is None:
        chosen_qty = float(chosen.get("qty") or 0)
        if chosen_qty > rem + 0.5:
            print(f"\n[ABORT] chosen stop qty {chosen_qty} > DB remaining_shares {rem}. "
                  f"Likely a stale stop on a different lot — manual review required.")
            return 4

    new_stop_id = str(chosen["id"])
    new_stop_price = float(chosen.get("stop_price") or 0) or trade["stop_price"]

    print(f"\nReconcile plan:")
    print(f"  trade_id={trade['id']} ({ticker} {alert_date})")
    print(f"  set stop_order_id = {new_stop_id}")
    print(f"  set stop_price    = {new_stop_price}")

    if not apply:
        print("\n[DRY-RUN] no changes written. Re-run with --apply to commit.")
        return 0

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE mi_live_trades
            SET stop_order_id = $2, stop_price = COALESCE(stop_price, $3)
            WHERE id = $1
            """,
            trade["id"], new_stop_id, new_stop_price,
        )

    await log_audit_event(
        "naked_position_reconciled",
        f"{ticker} {alert_date}: stop_order_id ← {new_stop_id} via manual recon",
        json.dumps({
            "ticker": ticker,
            "alert_date": str(alert_date),
            "trade_id": trade["id"],
            "new_stop_order_id": new_stop_id,
            "new_stop_price": new_stop_price,
            "remaining_shares": float(trade["remaining_shares"]),
            "candidates_count": len(candidates),
            "qty_match": exact is not None,
        }),
    )

    # Verify
    async with pool.acquire() as conn:
        after = await conn.fetchrow(
            "SELECT stop_order_id, stop_price FROM mi_live_trades WHERE id = $1",
            trade["id"],
        )
    print("\n[OK] write committed.")
    print(f"  stop_order_id = {after['stop_order_id']}")
    print(f"  stop_price    = {after['stop_price']}")
    return 0


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--ticker", required=True, help="Symbol (e.g. TEAM)")
    parser.add_argument("--alert-date", required=True, type=_parse_date,
                        help="ISO date, e.g. 2026-05-01")
    parser.add_argument("--apply", action="store_true",
                        help="Execute the UPDATE (default: dry-run)")
    args = parser.parse_args()
    sys.exit(asyncio.run(_main(args.ticker, args.alert_date, args.apply)))
