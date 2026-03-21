"""
Chart mosaic generator for RS leaders.

Fetches individual stock chart images from Finviz and stitches them
into a grid mosaic. Sent as a Telegram photo alongside the evening briefing.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Finviz chart URL pattern — daily chart with technicals
_FINVIZ_CHART_URL = "https://finviz.com/chart.ashx?t={ticker}&ty=c&ta=1&p=d&s=l"

# Finviz screener URL for tiled view (link sent alongside image)
_FINVIZ_SCREENER_URL = "https://finviz.com/screener.ashx?v=210&t={tickers}"

# Grid layout
_COLS = 2
_MAX_CHARTS = 20


async def _fetch_chart_image(
    client: httpx.AsyncClient,
    ticker: str,
    semaphore: asyncio.Semaphore,
) -> tuple[str, bytes | None]:
    """Fetch a single Finviz chart PNG. Returns (ticker, image_bytes)."""
    async with semaphore:
        try:
            url = _FINVIZ_CHART_URL.format(ticker=ticker)
            r = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                },
            )
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                return ticker, r.content
            logger.warning(f"Finviz chart fetch failed for {ticker}: HTTP {r.status_code}")
            return ticker, None
        except Exception as e:
            logger.warning(f"Finviz chart fetch error for {ticker}: {e}")
            return ticker, None


async def build_chart_mosaic(tickers: list[str]) -> tuple[bytes | None, str]:
    """
    Build a chart mosaic image from a list of tickers.

    Returns:
        (mosaic_png_bytes, finviz_screener_url)
        mosaic_png_bytes is None if insufficient charts were fetched.
    """
    tickers = tickers[:_MAX_CHARTS]
    screener_url = _FINVIZ_SCREENER_URL.format(tickers=",".join(tickers))

    # Fetch all chart images concurrently (limit concurrency to avoid rate limits)
    semaphore = asyncio.Semaphore(5)
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        tasks = [_fetch_chart_image(client, t, semaphore) for t in tickers]
        results = await asyncio.gather(*tasks)

    # Filter successful fetches, preserve order
    chart_data: list[tuple[str, bytes]] = []
    for ticker, img_bytes in results:
        if img_bytes:
            chart_data.append((ticker, img_bytes))

    if len(chart_data) < 2:
        logger.warning(f"Only {len(chart_data)} charts fetched, skipping mosaic")
        return None, screener_url

    # Stitch into grid using Pillow
    try:
        from PIL import Image

        images = []
        for ticker, img_bytes in chart_data:
            img = Image.open(io.BytesIO(img_bytes))
            images.append((ticker, img))

        # Use first image dimensions as reference
        cell_w, cell_h = images[0][1].size
        cols = min(_COLS, len(images))
        rows = (len(images) + cols - 1) // cols

        mosaic = Image.new("RGB", (cols * cell_w, rows * cell_h), (0, 0, 0))

        for idx, (ticker, img) in enumerate(images):
            row, col = divmod(idx, cols)
            # Resize if dimensions don't match (shouldn't happen with Finviz)
            if img.size != (cell_w, cell_h):
                img = img.resize((cell_w, cell_h))
            mosaic.paste(img, (col * cell_w, row * cell_h))

        # Export to PNG bytes
        buf = io.BytesIO()
        mosaic.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        return buf.getvalue(), screener_url

    except ImportError:
        logger.error("Pillow not installed — cannot build chart mosaic")
        return None, screener_url
    except Exception as e:
        logger.error(f"Chart mosaic build failed: {e}")
        return None, screener_url


async def send_chart_mosaic(
    tickers: list[str],
    chat_id: int | None = None,
) -> bool:
    """
    Build and send RS leaders chart mosaic to Telegram.
    Sends as a photo with Finviz screener link as caption.
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not chat_id:
        allowed = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
        ids = [x.strip() for x in allowed.split(",") if x.strip()]
        if not ids:
            logger.error("No TELEGRAM_ALLOWED_USER_IDS for chart mosaic")
            return False
        chat_id = int(ids[0])

    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return False

    mosaic_bytes, screener_url = await build_chart_mosaic(tickers)
    if not mosaic_bytes:
        # Fallback: just send the link
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": f"📊 [RS Leaders Charts]({screener_url})",
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": False,
                },
            )
        return True

    caption = f"📊 RS Leaders — Top {len(tickers)} by momentum\n{screener_url}"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendPhoto",
                data={
                    "chat_id": str(chat_id),
                    "caption": caption,
                },
                files={
                    "photo": ("rs_leaders.png", mosaic_bytes, "image/png"),
                },
            )
            r.raise_for_status()
            logger.info(f"Chart mosaic sent ({len(tickers)} charts)")
            return True
    except Exception as e:
        logger.error(f"Chart mosaic send failed: {e}")
        return False
