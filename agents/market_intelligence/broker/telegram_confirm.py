"""
Trade confirmation via Telegram inline keyboards.

Sends trade proposals with [Confirm] [Skip] buttons.
Uses Telegram Bot API directly via httpx (same pattern as send_telegram_message).
"""
from __future__ import annotations

import json
import logging
import os

import httpx

from agents.market_intelligence.db import get_pool

logger = logging.getLogger(__name__)


async def send_trade_proposal(alert: dict, order_spec: dict, trade_id: int) -> bool:
    """
    Send a trade proposal to Telegram with inline Confirm/Skip buttons.
    Returns True if message was sent successfully.
    """
    ticker = order_spec["ticker"]
    entry = order_spec["entry_price"]
    stop = order_spec["stop_loss_price"]
    risk = order_spec["risk_dollars"]
    equity = order_spec["equity"]
    shares = order_spec["shares"]
    score = order_spec.get("ep_score", 0)
    catalyst = alert.get("catalyst_quality", "N/A")
    gap = alert.get("gap_pct", 0)
    regime = order_spec.get("regime", "Unknown")
    risk_pct = (risk / equity * 100) if equity else 0

    text = (
        f"📊 *TRADE PROPOSAL: {ticker}*\n"
        f"Entry: ${entry:.2f} (ORB high)\n"
        f"Stop: ${stop:.2f} (ORB low)\n"
        f"Risk: ${risk:.0f} ({risk_pct:.1f}% of ${equity:,.0f})\n"
        f"Shares: {shares}\n"
        f"Score: {score:.0f} | Catalyst: {catalyst}\n"
        f"Gap: {gap:.1f}% | Regime: {regime}"
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

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                    "reply_markup": keyboard,
                },
            )
            resp.raise_for_status()
        logger.info(f"Trade proposal sent: {ticker} (trade_id={trade_id})")
        return True
    except Exception as e:
        logger.error(f"Failed to send trade proposal for {ticker}: {e}")
        return False


async def handle_callback(callback_data: str) -> dict:
    """
    Handle a callback from Telegram inline button press.
    Format: 'trade_confirm:{id}' or 'trade_skip:{id}'
    Returns dict with action taken.
    """
    parts = callback_data.split(":")
    if len(parts) != 2:
        return {"error": "invalid callback format"}

    action, trade_id_str = parts
    try:
        trade_id = int(trade_id_str)
    except ValueError:
        return {"error": "invalid trade_id"}

    pool = await get_pool()

    if action == "trade_confirm":
        async with pool.acquire() as conn:
            trade = await conn.fetchrow(
                "SELECT * FROM mi_live_trades WHERE id = $1", trade_id,
            )
        if not trade:
            return {"error": "trade not found"}
        if trade["status"] != "pending_confirmation":
            return {"error": f"trade already {trade['status']}"}

        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE mi_live_trades SET
                    status = 'confirmed',
                    confirmed_at = NOW()
                WHERE id = $1
            """, trade_id)

        # Submit order
        from agents.market_intelligence.broker.order_manager import submit_entry
        order = await submit_entry(trade_id)

        if order:
            return {"action": "confirmed", "trade_id": trade_id, "order_id": order["id"]}
        else:
            return {"action": "confirmed_but_order_failed", "trade_id": trade_id}

    elif action == "trade_skip":
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE mi_live_trades SET
                    status = 'skipped',
                    skip_reason = 'user_skipped'
                WHERE id = $1 AND status = 'pending_confirmation'
            """, trade_id)

        from agents.market_intelligence.briefing import send_telegram_message
        ticker_row = await pool.fetchval(
            "SELECT ticker FROM mi_live_trades WHERE id = $1", trade_id,
        )
        await send_telegram_message(f"⏭ Skipped trade: {ticker_row or trade_id}")
        return {"action": "skipped", "trade_id": trade_id}

    return {"error": f"unknown action: {action}"}
