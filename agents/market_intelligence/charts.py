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


def build_theme_table_image(
    scored_themes: list[dict],
    briefing_date: str,
    theme_rs_data: dict[str, dict] | None = None,
) -> bytes | None:
    """
    Render top 10 themes as a table image (PNG).
    Row 1: Theme name + RS / 1M / 3M / 6M
    Row 2: Top constituent tickers with individual RS
    Returns PNG bytes or None on error.
    """
    top = scored_themes[:10]
    if not top:
        return None

    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.error("Pillow not installed — cannot build theme table image")
        return None

    # Load fonts
    font_size = 17
    ticker_size = 14
    header_size = 18
    title_size = 22
    try:
        font = ImageFont.truetype("consola.ttf", font_size)
        ticker_font = ImageFont.truetype("consola.ttf", ticker_size)
        header_font = ImageFont.truetype("consolab.ttf", header_size)
        title_font = ImageFont.truetype("consolab.ttf", title_size)
    except (OSError, IOError):
        try:
            font = ImageFont.truetype("cour.ttf", font_size)
            ticker_font = ImageFont.truetype("cour.ttf", ticker_size)
            header_font = ImageFont.truetype("courbd.ttf", header_size)
            title_font = ImageFont.truetype("courbd.ttf", title_size)
        except (OSError, IOError):
            font = ImageFont.load_default()
            ticker_font = font
            header_font = font
            title_font = font

    # Measure the longest theme name to auto-size column
    dummy_img = Image.new("RGB", (1, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)
    max_name_w = max(
        dummy_draw.textlength(st["name"], font=font) for st in top
    )
    theme_col_w = int(max_name_w) + 20  # pad

    # Layout
    pad_x, pad_y = 24, 16
    name_row_h = 26
    ticker_row_h = 20
    row_h = name_row_h + ticker_row_h + 6  # theme name + tickers + gap
    num_col_w = 44
    col_widths = [theme_col_w, num_col_w, num_col_w, num_col_w, num_col_w]
    total_w = sum(col_widths) + 2 * pad_x
    # title + header + rows + bottom pad
    total_h = pad_y + 30 + 28 + len(top) * row_h + pad_y

    # Colors
    bg_color = (25, 25, 35)
    header_color = (180, 180, 200)
    text_color = (230, 230, 240)
    ticker_color = (140, 150, 170)
    title_color = (255, 255, 255)
    line_color = (60, 60, 80)
    hot_color = (100, 220, 100)    # RS 80+
    warm_color = (220, 200, 80)    # RS 50-79
    cool_color = (180, 100, 100)   # RS <50

    img = Image.new("RGB", (total_w, total_h), bg_color)
    draw = ImageDraw.Draw(img)

    # Short date
    parts = briefing_date.split("-")
    short_date = f"{int(parts[1])}/{int(parts[2])}" if len(parts) == 3 else briefing_date

    # Title
    y = pad_y
    draw.text((pad_x, y), f"Theme RS — {short_date}", fill=title_color, font=title_font)
    y += 30

    # Header row
    headers = ["Theme", "RS", "1M", "3M", "6M"]
    x = pad_x
    for i, hdr in enumerate(headers):
        draw.text((x, y), hdr, fill=header_color, font=header_font)
        x += col_widths[i]
    y += 28
    draw.line([(pad_x, y - 4), (total_w - pad_x, y - 4)], fill=line_color, width=1)

    def _rs_color(val: float) -> tuple:
        if val >= 80:
            return hot_color
        if val >= 50:
            return warm_color
        return cool_color

    theme_rs_data = theme_rs_data or {}

    for st in top:
        # Row 1: theme name + RS values
        x = pad_x
        draw.text((x, y), st["name"], fill=text_color, font=font)
        x += col_widths[0]
        for val_key, col_w in zip(["comp", "rs_1m", "rs_3m", "rs_6m"], col_widths[1:]):
            val = st[val_key]
            draw.text((x, y), f"{val:.0f}", fill=_rs_color(val), font=font)
            x += col_w
        y += name_row_h

        # Row 2: top constituent tickers with RS
        ticker_parts = []
        for tk in st.get("tickers") or []:
            rs = theme_rs_data.get(tk)
            if rs and rs.get("rs_composite") is not None and rs["rs_composite"] >= 50:
                ticker_parts.append((tk, rs["rs_composite"]))
        ticker_parts.sort(key=lambda x: -x[1])
        ticker_str = "  ".join(f"${tk} {int(rs)}" for tk, rs in ticker_parts[:6])
        if ticker_str:
            draw.text((pad_x + 8, y), ticker_str, fill=ticker_color, font=ticker_font)
        y += ticker_row_h + 6
        # Subtle separator
        draw.line([(pad_x, y - 3), (total_w - pad_x, y - 3)], fill=line_color, width=1)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


async def send_chart_mosaic(
    tickers: list[str],
    chat_id: int | None = None,
    mosaic_bytes: bytes | None = None,
) -> bool:
    """
    Send RS leaders chart mosaic to Telegram.
    Accepts pre-built mosaic_bytes to avoid double-fetching.
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

    screener_url = _FINVIZ_SCREENER_URL.format(tickers=",".join(tickers[:_MAX_CHARTS]))
    if not mosaic_bytes:
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
