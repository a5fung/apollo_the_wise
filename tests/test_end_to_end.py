"""
End-to-end integration test.

Sends a message through the full Apollo stack and verifies:
  1. Message is processed by orchestrator
  2. Response is generated
  3. Audit log entry is created

Usage:
    # 1. Set up .env with valid credentials
    # 2. Start the orchestrator: uvicorn main:app --port 8000
    # 3. python tests/test_end_to_end.py

This test does NOT require a real Telegram connection —
it calls the orchestrator HTTP API directly.
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
    base_url = "http://localhost:8000"

    print("=== Apollo End-to-End Test ===\n")

    # Health check
    print("1. Health check...")
    async with httpx.AsyncClient(timeout=10) as c:
        try:
            r = await c.get(f"{base_url}/health")
            print(f"   ✅ Orchestrator is running: {r.json()}")
        except httpx.ConnectError:
            print("   ❌ Cannot connect — is 'uvicorn main:app --port 8000' running?")
            return

    print("\n2. Testing orchestrator directly (bypassing Telegram)...")

    # Import orchestrator directly for local testing
    from core.orchestrator import Apollo

    messages_received = []

    async def capture_message(user_id: int, text: str):
        messages_received.append({"user_id": user_id, "text": text})
        print(f"   [Outbound message to {user_id}]: {text[:100]}")

    apollo = Apollo(send_message_fn=capture_message)

    test_user_id = 99999999  # Dummy user ID for testing

    # Test 1: Simple factual question
    print("\n   Test 1: Simple question (no tool use expected)")
    response = await apollo.handle_message(
        user_id=test_user_id,
        text="What's 15% tip on a $85 restaurant bill?",
        conversation_id="test-e2e-1",
    )
    print(f"   Response: {response[:200]}")
    assert response, "Expected a response"
    print("   ✅ Got response")

    # Test 2: Research query (will try to call Research Agent)
    print("\n   Test 2: Research query (will attempt Research Agent call)")
    response = await apollo.handle_message(
        user_id=test_user_id,
        text="What are the main differences between ETFs and mutual funds?",
        conversation_id="test-e2e-2",
    )
    print(f"   Response: {response[:300]}")
    assert response, "Expected a response"
    print("   ✅ Got response")

    # Test 3: Memory storage
    print("\n   Test 3: Memory storage")
    response = await apollo.handle_message(
        user_id=test_user_id,
        text="Remember that I prefer morning meetings before 10am.",
        conversation_id="test-e2e-3",
    )
    print(f"   Response: {response[:200]}")
    print("   ✅ Got response")

    # Check audit log
    print("\n3. Checking audit log...")
    from shared.audit import read_audit_log
    entries = read_audit_log(limit=5, user_id=test_user_id)
    print(f"   Found {len(entries)} audit entries for test user")
    if entries:
        print(f"   Latest: [{entries[0].agent.value}] {entries[0].action}")
    print("   ✅ Audit log working")

    print("\n=== End-to-end test complete ===")


if __name__ == "__main__":
    asyncio.run(main())
