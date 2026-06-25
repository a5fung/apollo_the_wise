"""
Trade confirmation via Telegram inline keyboards.

Sends trade proposals with [Confirm] [Skip] buttons.
Uses Telegram Bot API directly via httpx (same pattern as send_telegram_message).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx

from agents.market_intelligence.db import get_pool

logger = logging.getLogger(__name__)

VALID_ACTIONS = frozenset({"trade_confirm", "trade_skip"})


async def send_trade_proposal(
    alert: dict,
    order_spec: dict,
    trade_id: int,
    *,
    live_real_enabled: bool = False,
) -> bool:
    """
    Send a trade proposal to Telegram with inline Confirm/Skip buttons.
    Returns True if message was sent successfully.

    When account_mode='live' AND live_real_enabled=False, the header swaps
    to a STAGED-PAPER ramp banner so the user can distinguish strategies
    that haven't been promoted to real-$ yet (manual Confirm tap is the
    actual safety gate; the banner is decision-support).
    """
    ticker = order_spec["ticker"]
    entry = order_spec["entry_price"]
    stop = order_spec["stop_loss_price"]
    risk = order_spec["risk_dollars"]
    shares = order_spec["shares"]
    score = order_spec.get("ep_score", 0)
    # Sanitize the rubric grade: "game_changer" etc. carry "_" which Markdown reads as italic →
    # an unclosed entity → Telegram 400 (the parse-fragility class; SNX 6/25 trade #234).
    catalyst = (alert.get("catalyst_quality") or "N/A").replace("_", " ")
    gap = alert.get("gap_pct", 0)
    regime = order_spec.get("regime", "Unknown")
    # Show risk as % only — don't leak account equity
    equity = order_spec.get("equity", 0)
    risk_pct = (risk / equity * 100) if equity else 0

    from agents.market_intelligence.constants import current_account_mode, mode_prefix
    if current_account_mode() == "live" and not live_real_enabled:
        header = f"🟡 *STAGED-PAPER ramp — confirm to enter REAL-$:* {ticker}"
    else:
        header = f"{mode_prefix()}📊 *TRADE PROPOSAL: {ticker}*"
    # Theme membership (C8, 2026-05-19) — surface for live-real trade proposals.
    # Pradeep #1 catalyst type, helps inform manual Confirm/Skip decision.
    theme_line = ""
    try:
        from agents.market_intelligence.catalyst_rubric_runtime import (
            get_theme_membership, format_theme_for_telegram,
        )
        _theme = await get_theme_membership(ticker)
        theme_line = "\n" + format_theme_for_telegram(_theme)
    except Exception as _te:
        logger.debug(f"trade proposal theme lookup failed for {ticker}: {_te}")

    text = (
        f"{header}\n"
        f"Entry: ${entry:.2f} (ORB high)\n"
        f"Stop: ${stop:.2f} (ORB low)\n"
        f"Risk: ${risk:.0f} ({risk_pct:.1f}% of account)\n"
        f"Shares: {shares}\n"
        f"Score: {score:.0f} | Catalyst: {catalyst}\n"
        f"Gap: {gap:.1f}% | Regime: {regime}"
        f"{theme_line}"
    )

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Confirm", "callback_data": f"trade_confirm:{trade_id}"},
                {"text": "❌ Skip", "callback_data": f"trade_skip:{trade_id}"},
            ]
        ]
    }

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    allowed = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
    chat_id = int(allowed.split(",")[0].strip())

    async def _post(parse_mode: "str | None") -> None:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
            "reply_markup": keyboard,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage", json=payload
            )
            resp.raise_for_status()

    try:
        await _post("Markdown")
        logger.info(f"Trade proposal sent: {ticker} (trade_id={trade_id})")
        return True
    except Exception as e:
        # Markdown can 400 on an unescaped char in a dynamic field (SNX 6/25 trade #234 —
        # "game_changer" underscore → "can't find end of entity"). A live-trade proposal MUST
        # reach the operator, so retry PLAIN TEXT (keeps the Confirm/Skip buttons) before giving up.
        logger.warning(f"Trade proposal Markdown send failed for {ticker} ({e}) — retrying plain text")
        try:
            await _post(None)
            logger.info(f"Trade proposal sent (plain-text fallback): {ticker} (trade_id={trade_id})")
            return True
        except Exception as e2:
            logger.error(f"Failed to send trade proposal for {ticker} (markdown + plain): {e2}")
            return False


async def handle_callback(callback_data: str, user_id: int | None = None) -> dict:
    """
    Handle a callback from Telegram inline button press.
    Format: 'trade_confirm:{id}' or 'trade_skip:{id}'

    Security checks:
    - LIVE_TRADING_ENABLED must be true
    - User must be in allowed list
    - Confirmation must be within timeout window
    - Atomic status update prevents duplicate orders
    """
    from agents.market_intelligence.constants import (
        LIVE_TRADING_ENABLED,
        CONFIRMATION_TIMEOUT_SEC,
    )

    logger.info(f"Callback received: {callback_data} user_id={user_id}")

    # Kill switch check
    if not LIVE_TRADING_ENABLED:
        logger.warning("Callback rejected: live trading disabled")
        return {"error": "live trading is disabled"}

    # Validate callback format
    parts = callback_data.split(":")
    if len(parts) != 2:
        return {"error": "invalid callback format"}

    action, trade_id_str = parts
    if action not in VALID_ACTIONS:
        return {"error": "invalid action"}

    try:
        trade_id = int(trade_id_str)
    except ValueError:
        return {"error": "invalid trade_id"}

    # Validate user is authorized
    if user_id is not None:
        allowed_raw = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
        allowed_ids = {int(uid.strip()) for uid in allowed_raw.split(",") if uid.strip()}
        if user_id not in allowed_ids:
            logger.warning(f"Unauthorized callback attempt: user_id={user_id}")
            return {"error": "unauthorized"}

    pool = await get_pool()

    if action == "trade_confirm":
        # Atomic: only update if still pending — prevents duplicate orders
        async with pool.acquire() as conn:
            trade = await conn.fetchrow("""
                UPDATE mi_live_trades SET
                    status = 'confirmed',
                    confirmed_at = NOW()
                WHERE id = $1 AND status = 'pending_confirmation'
                RETURNING *
            """, trade_id)

        if not trade:
            logger.warning(f"Trade {trade_id} not available for confirmation (already processed or not found)")
            return {"error": "trade not available (already processed or not found)"}

        # Timeout check: reject if proposal is stale
        proposed_at = trade.get("proposed_at")
        if proposed_at:
            if proposed_at.tzinfo is None:
                proposed_at = proposed_at.replace(tzinfo=timezone.utc)
            age_seconds = (datetime.now(timezone.utc) - proposed_at).total_seconds()
            if age_seconds > CONFIRMATION_TIMEOUT_SEC:
                # Roll back to expired
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE mi_live_trades SET status = 'expired' WHERE id = $1",
                        trade_id,
                    )
                logger.warning(f"Trade {trade_id} expired: {age_seconds:.0f}s old")
                return {"error": f"proposal expired ({age_seconds:.0f}s > {CONFIRMATION_TIMEOUT_SEC}s)"}

        # Submit order
        from agents.market_intelligence.broker.order_manager import submit_entry
        order = await submit_entry(trade_id)

        if order:
            logger.info(f"Trade {trade_id} confirmed → order_id={order['id']}")
            return {"action": "confirmed", "trade_id": trade_id, "order_id": order["id"]}
        else:
            logger.error(f"Trade {trade_id} confirmed but order submission failed")
            return {"action": "confirmed_but_order_failed", "trade_id": trade_id}

    elif action == "trade_skip":
        async with pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE mi_live_trades SET
                    status = 'skipped',
                    skip_reason = 'user_skipped'
                WHERE id = $1 AND status = 'pending_confirmation'
            """, trade_id)

        from agents.market_intelligence.briefing import send_telegram_message
        from agents.market_intelligence.constants import mode_prefix
        async with pool.acquire() as conn:
            ticker_row = await conn.fetchval(
                "SELECT ticker FROM mi_live_trades WHERE id = $1", trade_id,
            )
        logger.info(f"Trade {trade_id} ({ticker_row}) skipped by user")
        await send_telegram_message(f"{mode_prefix()}⏭ Skipped trade: {ticker_row or trade_id}")
        return {"action": "skipped", "trade_id": trade_id}

    return {"error": "invalid action"}
