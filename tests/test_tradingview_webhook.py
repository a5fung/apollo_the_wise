"""
TradingView Webhook — end-to-end test.

Simulates a TradingView alert being fired and verifies:
  1. Webhook is received
  2. Alert is parsed correctly
  3. Telegram notification is sent

Usage:
    # 1. Start the orchestrator: uvicorn main:app --port 8000
    # 2. Run this script: python tests/test_tradingview_webhook.py

Or simulate with curl:
    curl -X POST "http://localhost:8000/tradingview/alert?token=YOUR_TV_SECRET" \
         -H "Content-Type: application/json" \
         -d '{"ticker": "AAPL", "exchange": "NASDAQ", "price": "185.50", "alert_name": "Price crossed above 185", "message": "Strong breakout signal"}'
"""
import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv()

from shared.secrets import get_secrets


async def main():
    secrets = get_secrets()

    print("=== TradingView Webhook Test ===\n")

    base_url = "http://localhost:8000"
    tv_secret = secrets.tradingview_webhook_secret

    # Sample TradingView alert payload
    alert_payload = {
        "ticker": "AAPL",
        "exchange": "NASDAQ",
        "price": "185.50",
        "alert_name": "Price crossed above 185",
        "message": "Strong breakout signal on daily chart",
        "time": "2026-03-12T14:30:00Z",
    }

    print(f"Sending test alert to {base_url}/tradingview/alert")
    print(f"Payload: {json.dumps(alert_payload, indent=2)}\n")

    async with httpx.AsyncClient(timeout=30) as client:
        # Test 1: Valid token
        print("1. Testing with valid token...")
        try:
            r = await client.post(
                f"{base_url}/tradingview/alert?token={tv_secret}",
                json=alert_payload,
            )
            if r.status_code == 200:
                print(f"   ✅ Alert accepted (HTTP {r.status_code})")
                print(f"   Response: {r.json()}")
            else:
                print(f"   ❌ Unexpected status: {r.status_code}")
                print(f"   Response: {r.text}")
        except httpx.ConnectError:
            print("   ❌ Could not connect — is the orchestrator running?")
            return

        # Test 2: Invalid token (should be rejected)
        print("\n2. Testing with invalid token (should be rejected)...")
        r = await client.post(
            f"{base_url}/tradingview/alert?token=wrong_token",
            json=alert_payload,
        )
        if r.status_code == 401:
            print(f"   ✅ Correctly rejected invalid token (HTTP 401)")
        else:
            print(f"   ⚠️  Expected 401, got {r.status_code}")

        # Test 3: Health check
        print("\n3. Health check...")
        r = await client.get(f"{base_url}/health")
        print(f"   Status: {r.status_code} — {r.json()}")

    print("\n=== Test complete — check your Telegram for the notification ===")


if __name__ == "__main__":
    asyncio.run(main())
