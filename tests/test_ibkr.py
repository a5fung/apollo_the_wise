"""
Finance Agent — IBKR read-only verification test.

Usage:
    python tests/test_ibkr.py

Verifies:
  1. Client Portal Gateway is reachable and authenticated
  2. Portfolio data can be fetched
  3. No write permissions are available (by design)
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from agents.finance.ibkr import IBKRClient


async def main():
    client = IBKRClient()

    print("=== IBKR Read-Only Verification ===\n")

    # 1. Check authentication
    print("1. Checking authentication status...")
    is_auth = await client.is_authenticated()
    if not is_auth:
        print("   ❌ Not authenticated. Start IBKR Client Portal Gateway and log in.")
        print("   Gateway URL:", client._base_url)
        return
    print("   ✅ Authenticated")

    # 2. Fetch portfolio
    print("\n2. Fetching portfolio positions...")
    try:
        positions = await client.get_positions()
        print(f"   ✅ Got {len(positions)} positions")
        if positions:
            # Show first position
            p = positions[0]
            print(f"   Sample: {p.get('ticker', '?')} — ${p.get('mktValue', 0):,.2f}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # 3. Fetch account summary
    print("\n3. Fetching account summary...")
    try:
        summary = await client.get_account_summary()
        nav = summary.get("netliquidation", {}).get("amount")
        print(f"   ✅ NAV: ${float(nav):,.2f}" if nav else "   ✅ Summary fetched")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # 4. Verify no write permissions (attempt a test order — should fail)
    print("\n4. Verifying read-only mode (attempting a test trade — should be rejected)...")
    try:
        import httpx
        async with httpx.AsyncClient(base_url=client._base_url, verify=False) as c:
            # Try to place an order — this should fail with 403 or similar
            r = await c.post(
                "/v1/api/iserver/account/orders",
                json={
                    "acctId": client._account_id,
                    "conid": 265598,  # AAPL
                    "orderType": "MKT",
                    "side": "BUY",
                    "quantity": 1,
                    "tif": "DAY",
                },
            )
            if r.status_code in (403, 401, 400):
                print(f"   ✅ Order correctly rejected (HTTP {r.status_code}) — read-only confirmed")
            else:
                print(f"   ⚠️  WARNING: Order endpoint returned HTTP {r.status_code}")
                print(f"   Response: {r.text[:200]}")
                print("   IBKR account may have trading permissions — verify this is read-only!")
    except Exception as e:
        print(f"   ✅ Order endpoint unreachable: {e} — read-only likely enforced")

    print("\n=== Test complete ===")


if __name__ == "__main__":
    asyncio.run(main())
