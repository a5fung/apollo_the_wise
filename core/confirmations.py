"""
Confirmation gate — blocks irreversible actions until the user replies YES/NO via Telegram.

Flow:
1. Agent/orchestrator calls request_confirmation() — stores pending confirmation in Redis + DB
2. User receives a Telegram message: "Confirm: [action]. Reply YES or NO"
3. Telegram handler calls resolve_confirmation() when user replies
4. The original awaiting coroutine is unblocked and proceeds or cancels
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

import redis.asyncio as redis

from shared.audit import log_action
from shared.models import AgentName, ConfirmationStatus
from shared.secrets import get_secrets

logger = logging.getLogger(__name__)

# Confirmations expire after this many minutes if not answered
CONFIRMATION_TIMEOUT_MINUTES = 15

# In-memory futures: confirmation_id -> asyncio.Future
_pending_futures: dict[str, asyncio.Future] = {}

_redis_client: Optional[redis.Redis] = None


def _redis_key(confirmation_id: str) -> str:
    return f"apollo:confirm:{confirmation_id}"


async def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            get_secrets().redis_url,
            decode_responses=True,
        )
    return _redis_client


async def request_confirmation(
    user_id: int,
    conversation_id: str,
    agent: AgentName,
    action_description: str,
    action_payload: dict[str, Any],
    send_telegram_message: Callable[[int, str], Any],
) -> bool:
    """
    Request confirmation from the user for a pending action.

    - Sends a Telegram message asking for YES/NO
    - Waits (up to CONFIRMATION_TIMEOUT_MINUTES) for the user to respond
    - Returns True if confirmed, False if rejected/timed out

    `send_telegram_message` is a coroutine that takes (user_id, text) and sends to Telegram.
    """
    confirmation_id = str(uuid.uuid4())
    short_id = confirmation_id[:8]

    # Store in Redis for persistence across restarts
    r = await get_redis()
    payload = {
        "confirmation_id": confirmation_id,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "agent": agent.value,
        "action_description": action_description,
        "action_payload": action_payload,
        "status": ConfirmationStatus.PENDING.value,
        "created_at": datetime.utcnow().isoformat(),
    }
    await r.setex(
        _redis_key(confirmation_id),
        int(CONFIRMATION_TIMEOUT_MINUTES * 60),
        json.dumps(payload),
    )

    # Register in-memory future for this process
    loop = asyncio.get_event_loop()
    future: asyncio.Future[bool] = loop.create_future()
    _pending_futures[confirmation_id] = future

    # Send Telegram message
    message = (
        f"⚠️ *Confirmation required* \\[`{short_id}`\\]\n\n"
        f"**{action_description}**\n\n"
        f"Reply *YES* to confirm or *NO* to cancel\\."
    )
    await send_telegram_message(user_id, message)

    await log_action(
        user_id=user_id,
        agent=agent,
        action="confirmation_requested",
        details={"confirmation_id": confirmation_id, "action": action_description},
    )

    # Wait for resolution
    try:
        confirmed = await asyncio.wait_for(
            future,
            timeout=CONFIRMATION_TIMEOUT_MINUTES * 60,
        )
    except asyncio.TimeoutError:
        _pending_futures.pop(confirmation_id, None)
        await r.delete(_redis_key(confirmation_id))
        logger.info(f"Confirmation {short_id} expired")
        await send_telegram_message(
            user_id,
            f"⏰ Confirmation `{short_id}` expired\\. Action was not taken\\."
        )
        await log_action(
            user_id=user_id,
            agent=agent,
            action="confirmation_expired",
            details={"confirmation_id": confirmation_id},
            confirmed_by_user=False,
        )
        return False

    # Clean up
    _pending_futures.pop(confirmation_id, None)
    await r.delete(_redis_key(confirmation_id))

    status_str = "approved" if confirmed else "rejected"
    await log_action(
        user_id=user_id,
        agent=agent,
        action=f"confirmation_{status_str}",
        details={"confirmation_id": confirmation_id, "action": action_description},
        confirmed_by_user=confirmed,
        confirmation_id=confirmation_id,
    )

    return confirmed


async def resolve_confirmation(confirmation_id: str, approved: bool) -> bool:
    """
    Called by the Telegram handler when the user replies YES or NO.
    Resolves the in-memory future so the waiting coroutine is unblocked.
    Returns True if a matching pending confirmation was found and resolved.
    """
    future = _pending_futures.get(confirmation_id)
    if future and not future.done():
        future.set_result(approved)
        logger.info(f"Confirmation {confirmation_id[:8]} resolved: {'approved' if approved else 'rejected'}")
        return True

    # Future not in memory — maybe restart happened. Update Redis status.
    r = await get_redis()
    raw = await r.get(_redis_key(confirmation_id))
    if raw:
        data = json.loads(raw)
        data["status"] = ConfirmationStatus.APPROVED.value if approved else ConfirmationStatus.REJECTED.value
        # Keep in Redis briefly so caller can check
        await r.setex(_redis_key(confirmation_id), 60, json.dumps(data))
        return True

    return False


async def get_pending_confirmation_ids_for_user(user_id: int) -> list[str]:
    """Return all pending confirmation IDs for a user (from Redis)."""
    r = await get_redis()
    # We'd need to scan — for simplicity store a set per user
    key = f"apollo:confirm:user:{user_id}"
    ids = await r.smembers(key)
    return list(ids)


def parse_confirmation_reply(text: str) -> Optional[bool]:
    """
    Parse a user's reply as YES/NO.
    Returns True (yes), False (no), or None (not a confirmation reply).
    """
    normalized = text.strip().upper()
    if normalized in {"YES", "Y", "CONFIRM", "OK", "APPROVE", "APPROVED", "✅"}:
        return True
    if normalized in {"NO", "N", "CANCEL", "DENY", "REJECT", "REJECTED", "❌"}:
        return False
    return None
