"""One-shot read-only diagnostic for IBM broker state after the failed
manual partial trigger. Bootstraps creds first then dumps open orders +
position."""
import asyncio


async def main():
    from agents.market_intelligence.agent import _bootstrap_alpaca_credentials
    status, fallback = _bootstrap_alpaca_credentials()
    print(f"creds: {status} (fallback={fallback})")

    from agents.market_intelligence.broker import alpaca_client as alpaca

    print("\n=== IBM open orders ===")
    orders = await alpaca.get_open_orders(ticker="IBM", account_mode="paper")
    for o in orders:
        print(f"  id={o['id']} side={o['side']} type={o['type']} "
              f"qty={o['qty']} filled={o['filled_qty']} "
              f"status={o['status']} stop_price={o['stop_price']}")

    print("\n=== IBM position ===")
    pos = await alpaca.get_position("IBM", account_mode="paper")
    print(f"  {pos}")


if __name__ == "__main__":
    asyncio.run(main())
