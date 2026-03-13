"""
FastAPI app — webhook receiver.
Handles:
  1. Telegram webhook (POST /telegram/webhook)
  2. TradingView alert webhooks (POST /tradingview/alert)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from telegram import Update

from shared.models import TradingViewAlert
from shared.secrets import get_secrets

logger = logging.getLogger(__name__)

app = FastAPI(title="Apollo Webhooks", docs_url=None, redoc_url=None)

# These are set at startup by main.py
_telegram_app = None
_apollo = None


def configure(telegram_app, apollo_instance) -> None:
    """Called from main.py to inject dependencies."""
    global _telegram_app, _apollo
    _telegram_app = telegram_app
    _apollo = apollo_instance


# ── Health check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ── Telegram webhook ──────────────────────────────────────────────────────────

@app.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> JSONResponse:
    """Receive Telegram updates via webhook."""
    if _telegram_app is None:
        raise HTTPException(status_code=503, detail="Not initialized")

    try:
        body = await request.body()
        data = json.loads(body)
        update = Update.de_json(data, _telegram_app.bot)
        await _telegram_app.process_update(update)
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.exception(f"Error processing Telegram update: {e}")
        # Always return 200 to Telegram (prevents retries for bad messages)
        return JSONResponse({"ok": False, "error": str(e)})


# ── TradingView webhook ───────────────────────────────────────────────────────

@app.post("/tradingview/alert")
async def tradingview_alert(request: Request) -> JSONResponse:
    """
    Receive TradingView price alert webhooks.

    TradingView sends a POST with JSON body. We verify the token,
    parse the alert, and forward to the Finance Agent / Telegram.

    Secure your TradingView webhook URL by appending:
      ?token=YOUR_TRADINGVIEW_WEBHOOK_SECRET
    """
    secrets = get_secrets()

    # Token verification
    token = request.query_params.get("token") or request.headers.get("X-TV-Token")
    if not token or not hmac.compare_digest(token, secrets.tradingview_webhook_secret):
        logger.warning("TradingView webhook received with invalid token")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    try:
        body = await request.body()
        raw_data: dict[str, Any] = json.loads(body) if body else {}
    except json.JSONDecodeError:
        # TradingView sometimes sends plain text
        body_text = body.decode("utf-8", errors="replace")
        raw_data = {"message": body_text}

    alert = _parse_tradingview_alert(raw_data)

    logger.info(
        f"TradingView alert: ticker={alert.ticker} "
        f"price={alert.price} name={alert.alert_name}"
    )

    # Forward to Finance Agent and notify user via Telegram
    if _apollo and _telegram_app:
        await _handle_tradingview_alert(alert)

    return JSONResponse({"ok": True})


def _parse_tradingview_alert(data: dict[str, Any]) -> TradingViewAlert:
    """Parse various TradingView webhook payload formats into a normalized alert."""
    return TradingViewAlert(
        ticker=data.get("ticker") or data.get("symbol") or "UNKNOWN",
        exchange=data.get("exchange"),
        price=_safe_float(data.get("price") or data.get("close")),
        alert_name=data.get("alert_name") or data.get("alertName"),
        message=data.get("message") or data.get("text"),
        time=data.get("time") or data.get("timenow"),
        raw=data,
    )


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


async def _handle_tradingview_alert(alert: TradingViewAlert) -> None:
    """Route TradingView alert to Finance Agent and notify via Telegram."""
    secrets = get_secrets()

    if not secrets.telegram_allowed_user_ids:
        logger.error("No allowed Telegram user IDs configured — cannot forward alert")
        return

    # Notify all allowed users (typically just one — the owner)
    for user_id in secrets.telegram_allowed_user_ids:
        # Build a context-rich notification
        price_str = f"${alert.price:,.2f}" if alert.price else "N/A"
        notification = (
            f"🔔 *TradingView Alert*\n\n"
            f"📈 *{alert.ticker}*"
            + (f" ({alert.exchange})" if alert.exchange else "")
            + f"\n💵 Price: `{price_str}`"
            + (f"\n📋 {alert.alert_name}" if alert.alert_name else "")
            + (f"\n💬 {alert.message}" if alert.message else "")
        )

        # Use Apollo to provide richer context (will call Finance Agent)
        if _apollo:
            try:
                # Quick enrichment via orchestrator
                enrichment_query = (
                    f"I just received a TradingView alert for {alert.ticker} "
                    f"at price {price_str}. Alert: '{alert.alert_name or alert.message}'. "
                    f"Briefly summarize what's relevant about this alert and the current "
                    f"chart situation if you have data."
                )
                enriched = await _apollo.handle_message(
                    user_id=user_id,
                    text=enrichment_query,
                    conversation_id=f"tv_alert_{alert.ticker}",
                )
                notification += f"\n\n{enriched}"
            except Exception as e:
                logger.error(f"Failed to enrich TradingView alert: {e}")

        from channels.telegram import TelegramChannel
        # We need to send via the telegram app directly
        try:
            await _telegram_app.bot.send_message(
                chat_id=user_id,
                text=notification,
                parse_mode="MarkdownV2",
            )
        except Exception as e:
            logger.error(f"Failed to send TV alert to {user_id}: {e}")
