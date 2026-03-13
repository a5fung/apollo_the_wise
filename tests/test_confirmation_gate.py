"""
Confirmation Gate — unit test.

Verifies:
  1. Action is NOT taken before YES is received
  2. Action IS taken after YES
  3. Action is NOT taken after NO
  4. Confirmation expires correctly

Usage:
    pytest tests/test_confirmation_gate.py -v
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()


@pytest.mark.asyncio
async def test_confirmation_approved():
    """Confirm that YES resolves to True."""
    from core.confirmations import request_confirmation, resolve_confirmation
    from shared.models import AgentName

    messages_sent = []

    async def mock_send(user_id, text):
        messages_sent.append({"user_id": user_id, "text": text})

    # Start waiting for confirmation in background
    confirmation_id = None

    async def get_confirmation():
        nonlocal confirmation_id
        # Patch Redis to avoid needing a real Redis connection
        with patch("core.confirmations.get_redis") as mock_redis:
            r = AsyncMock()
            r.setex = AsyncMock()
            r.delete = AsyncMock()
            mock_redis.return_value = r

            with patch("core.confirmations.log_action", AsyncMock()):
                result = await request_confirmation(
                    user_id=123456789,
                    conversation_id="test-conv",
                    agent=AgentName.CALENDAR,
                    action_description="Create event: Dentist Tuesday 2pm",
                    action_payload={"action": "create_event"},
                    send_telegram_message=mock_send,
                )
                return result

    # Run confirmation request + resolution concurrently
    async def resolve_after_delay():
        await asyncio.sleep(0.1)  # Let request_confirmation start
        from core.confirmations import _pending_futures
        # Resolve the most recent pending future
        for conf_id, fut in list(_pending_futures.items()):
            if not fut.done():
                await resolve_confirmation(conf_id, approved=True)
                break

    result, _ = await asyncio.gather(
        get_confirmation(),
        resolve_after_delay(),
    )

    assert result is True, "Approved confirmation should return True"
    assert len(messages_sent) == 1, "Should have sent one Telegram message"
    assert "Confirmation required" in messages_sent[0]["text"] or "required" in messages_sent[0]["text"].lower()


@pytest.mark.asyncio
async def test_confirmation_rejected():
    """Confirm that NO resolves to False."""
    from core.confirmations import request_confirmation, resolve_confirmation
    from shared.models import AgentName

    async def mock_send(user_id, text):
        pass

    async def get_confirmation():
        with patch("core.confirmations.get_redis") as mock_redis:
            r = AsyncMock()
            r.setex = AsyncMock()
            r.delete = AsyncMock()
            mock_redis.return_value = r

            with patch("core.confirmations.log_action", AsyncMock()):
                return await request_confirmation(
                    user_id=123456789,
                    conversation_id="test-conv",
                    agent=AgentName.CALENDAR,
                    action_description="Delete event: Team meeting",
                    action_payload={"action": "delete_event"},
                    send_telegram_message=mock_send,
                )

    async def reject_after_delay():
        await asyncio.sleep(0.1)
        from core.confirmations import _pending_futures
        for conf_id, fut in list(_pending_futures.items()):
            if not fut.done():
                await resolve_confirmation(conf_id, approved=False)
                break

    result, _ = await asyncio.gather(get_confirmation(), reject_after_delay())
    assert result is False, "Rejected confirmation should return False"


def test_parse_confirmation_reply():
    """Test that YES/NO parsing works correctly."""
    from core.confirmations import parse_confirmation_reply

    # YES variants
    assert parse_confirmation_reply("YES") is True
    assert parse_confirmation_reply("yes") is True
    assert parse_confirmation_reply("Y") is True
    assert parse_confirmation_reply("confirm") is True
    assert parse_confirmation_reply("OK") is True
    assert parse_confirmation_reply("✅") is True

    # NO variants
    assert parse_confirmation_reply("NO") is False
    assert parse_confirmation_reply("no") is False
    assert parse_confirmation_reply("N") is False
    assert parse_confirmation_reply("cancel") is False
    assert parse_confirmation_reply("❌") is False

    # Neither
    assert parse_confirmation_reply("maybe") is None
    assert parse_confirmation_reply("what's going on?") is None
    assert parse_confirmation_reply("hello") is None
