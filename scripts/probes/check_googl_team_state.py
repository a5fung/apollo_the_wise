"""One-off diagnostic: query Alpaca for GOOGL/TEAM positions and open orders."""
import asyncio
from agents.market_intelligence.broker import alpaca_client as alpaca


async def main():
    pos = await alpaca.get_all_positions()
    print("=== POSITIONS ===")
    for p in pos:
        sym = p.get("symbol")
        if sym in ("GOOGL", "TEAM"):
            print(f"{sym}: qty={p.get('qty')} avg_entry={p.get('avg_entry_price')} unrealized=${p.get('unrealized_pl')}")

    print("=== OPEN ORDERS ===")
    for sym in ("GOOGL", "TEAM"):
        orders = await alpaca.get_open_orders(sym)
        for o in orders:
            print(f"{sym}: id={str(o.get('id'))[:8]} type={o.get('type')} side={o.get('side')} qty={o.get('qty')} stop=${o.get('stop_price')} status={o.get('status')}")


asyncio.run(main())
