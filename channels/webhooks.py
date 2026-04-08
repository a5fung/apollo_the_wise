"""
FastAPI app — webhook receiver.
Handles:
  1. Telegram webhook (POST /telegram/webhook)
  2. TradingView alert webhooks (POST /tradingview/alert)
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import re
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
        # Process in background — return 200 immediately so Telegram never retries
        asyncio.create_task(_telegram_app.process_update(update))
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.exception(f"Error processing Telegram update: {e}")
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
    logger.info(f"TradingView webhook hit: method={request.method} client={request.client}")
    secrets = get_secrets()

    # Token verification
    token = request.query_params.get("token") or request.headers.get("X-TV-Token")
    if not token or not hmac.compare_digest(token, secrets.tradingview_webhook_secret):
        logger.warning(f"TradingView webhook: invalid/missing token (got: {token!r:.20})")
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
    else:
        logger.error(f"TradingView alert dropped — not initialized: _apollo={_apollo is not None} _telegram_app={_telegram_app is not None}")

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

    def _esc(s: str) -> str:
        """Strip Markdown special chars from dynamic TradingView strings."""
        return re.sub(r"[*_`\[\]]", "", s) if s else s

    for user_id in secrets.telegram_allowed_user_ids:
        price_str = f"${alert.price:,.2f}" if alert.price else "N/A"

        # Escape dynamic fields — TradingView names often contain underscores
        ticker   = _esc(alert.ticker or "UNKNOWN")
        exch     = _esc(alert.exchange or "")
        name     = _esc(alert.alert_name or "")
        message  = _esc(alert.message or "")

        notification = (
            f"🔔 *TradingView Alert*\n\n"
            f"📈 *{ticker}*"
            + (f" ({exch})" if exch else "")
            + f"\n💵 Price: `{price_str}`"
            + (f"\n📋 {name}" if name else "")
            + (f"\n💬 {message}" if message else "")
        )

        # Send the base notification immediately — don't wait for enrichment
        try:
            await _telegram_app.bot.send_message(
                chat_id=user_id,
                text=notification,
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Failed to send TV alert to {user_id}: {e}")
            # Try again without Markdown in case of parse error
            try:
                plain = notification.replace("*", "").replace("`", "")
                await _telegram_app.bot.send_message(chat_id=user_id, text=plain)
            except Exception as e2:
                logger.error(f"Failed plain-text fallback TV alert to {user_id}: {e2}")
            return

        # Enrich asynchronously — won't block or delay the notification above
        if _apollo:
            async def _enrich(uid=user_id):
                try:
                    enrichment_query = (
                        f"TradingView alert for {alert.ticker} at {price_str}. "
                        f"Alert: '{alert.alert_name or alert.message}'. "
                        f"One or two sentences on what's relevant."
                    )
                    enriched = await _apollo.handle_message(
                        user_id=uid,
                        text=enrichment_query,
                        conversation_id=f"tv_alert_{alert.ticker}",
                    )
                    if enriched:
                        await _telegram_app.bot.send_message(
                            chat_id=uid, text=enriched
                        )
                except Exception as e:
                    logger.error(f"TV alert enrichment failed: {e}")

            asyncio.create_task(_enrich())
