"""
Apollo Assistant — main entry point.

Starts:
- FastAPI app (Telegram webhook + TradingView webhook receiver)
- Telegram bot (webhook mode)
- PostgreSQL schema initialization

Usage:
  uvicorn main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI

# Load .env before importing anything that reads env vars
load_dotenv()

from channels.telegram import TelegramChannel
from channels.webhooks import app as webhook_app, configure as configure_webhooks
from core.memory import initialize_schema
from core.notifications import notify_startup
from core.orchestrator import Apollo
from core.router import health_check_all_agents
from shared.secrets import get_secrets

# ── Logging ───────────────────────────────────────────────────────────────────

def setup_logging() -> None:
    secrets = get_secrets()
    level = getattr(logging, secrets.log_level, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )
    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


setup_logging()
logger = logging.getLogger(__name__)


# ── App lifecycle ─────────────────────────────────────────────────────────────

_telegram_channel: TelegramChannel | None = None
_apollo: Apollo | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    global _telegram_channel, _apollo

    logger.info("Apollo starting up...")

    # Initialize database
    try:
        await initialize_schema()
        logger.info("Database ready")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        logger.warning("Continuing without persistent memory — check PostgreSQL connection")

    # Build Telegram bot
    secrets = get_secrets()

    # Create orchestrator
    _apollo = Apollo(send_message_fn=lambda uid, text: _telegram_channel.send_message(uid, text))

    # Create and configure Telegram channel
    _telegram_channel = TelegramChannel(_apollo)
    tg_app = _telegram_channel.build_application()

    # Wire up webhook app
    configure_webhooks(tg_app, _apollo)

    # Initialize Telegram application
    await tg_app.initialize()
    await tg_app.start()

    # Set webhook URL if configured
    webhook_url = os.environ.get("WEBHOOK_BASE_URL")
    if webhook_url:
        full_url = f"{webhook_url.rstrip('/')}/telegram/webhook"
        try:
            await _telegram_channel.set_webhook(full_url)
        except Exception as e:
            logger.error(f"Failed to set Telegram webhook: {e}")
    else:
        logger.warning(
            "WEBHOOK_BASE_URL not set — Telegram webhook not configured. "
            "Set this env var to your public URL (e.g. https://your-vps.example.com)"
        )

    logger.info("Apollo ready")

    # Send startup notification with agent health check
    # Retry until all enabled agents are up (or give up after 30s)
    try:
        import asyncio
        for attempt in range(6):
            await asyncio.sleep(5)
            statuses = await health_check_all_agents()
            if all(ok for ok, _ in statuses.values()):
                break  # All healthy — no need to wait longer
            if attempt < 5:
                logger.info(f"Startup check: some agents not ready yet, retrying ({attempt+1}/6)...")
        await notify_startup(statuses)
    except Exception as e:
        logger.warning(f"Startup notification failed: {e}")

    yield  # Application is running

    # Shutdown
    logger.info("Apollo shutting down...")
    if tg_app:
        await tg_app.stop()
        await tg_app.shutdown()


# ── Mount everything on one ASGI app ─────────────────────────────────────────

app = FastAPI(title="Apollo", lifespan=lifespan)

# Mount webhook routes
app.mount("/", webhook_app)


# ── Development server ────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=os.environ.get("ENVIRONMENT", "development") == "development",
        log_level="info",
    )
