"""READ-ONLY: is FPS still naked on the (paper) broker since the 6/4 partial failure?
Compares the live Alpaca position vs open protective stops, and the DB's view (trade 183).
No mutation — get_open_position / get_orders only.
"""
import asyncio

from agents.market_intelligence import db
from agents.market_intelligence.broker import alpaca_client as ac


async def main():
    print("══ FPS broker-state check (paper) — READ-ONLY ══\n")

    pos = await ac.get_position("FPS", "paper")
    if not pos:
        print("POSITION: none (FPS is flat on the broker — not naked, position closed).")
    else:
        print(f"POSITION: qty={pos.get('qty')} avg=${pos.get('avg_entry_price')} "
              f"mkt_val=${pos.get('market_value')} uPL=${pos.get('unrealized_pl')}")

    orders = await ac.get_open_orders("FPS", "paper")
    print(f"\nOPEN ORDERS ({len(orders)}):")
    stop_cover = 0
    for o in orders:
        is_stop = o.get("stop_price") is not None or "stop" in str(o.get("order_type", "")).lower()
        if is_stop and str(o.get("side", "")).lower().endswith("sell"):
            try:
                stop_cover += int(float(o.get("qty") or 0))
            except Exception:
                pass
        print(f"   {o.get('side')} {o.get('order_type')} qty={o.get('qty')} "
              f"stop=${o.get('stop_price')} status={o.get('status')} id={str(o.get('id'))[:8]}")

    # DB view (SELECT * → robust to column naming)
    async with (await db.get_pool()).acquire() as c:
        row = await c.fetchrow("""
            SELECT * FROM mi_live_trades
            WHERE ticker='FPS' AND account_mode='paper'
            ORDER BY created_at DESC LIMIT 1
        """)
    print("\nDB VIEW (mi_live_trades latest FPS/paper):")
    if row:
        d = dict(row)
        for k in ("id", "status", "remaining_shares", "shares", "position_size",
                  "stop_order_id", "stop_price", "partial_taken", "closed_at"):
            if k in d:
                print(f"   {k}={d[k]}")
    else:
        print("   (no FPS/paper row)")

    # Verdict
    held = 0
    if pos:
        try:
            held = int(float(pos.get("qty") or 0))
        except Exception:
            held = 0
    print("\n── VERDICT ──")
    if held == 0:
        print("   ✅ FPS flat on broker — NOT naked (position closed since 6/4).")
    elif stop_cover >= held:
        print(f"   ✅ FPS holds {held} sh, covered by stop(s) for {stop_cover} sh — NOT naked.")
    else:
        print(f"   🔴 FPS holds {held} sh but stops cover only {stop_cover} sh — NAKED/UNDER-COVERED.")


asyncio.run(main())
