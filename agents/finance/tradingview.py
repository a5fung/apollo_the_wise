"""
TradingView alert processor.
Parses incoming webhook alerts and formats them for user delivery.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from shared.models import TradingViewAlert

logger = logging.getLogger(__name__)


def parse_alert(raw: dict[str, Any]) -> TradingViewAlert:
    """Parse a raw TradingView webhook payload into a TradingViewAlert."""
    ticker = (
        raw.get("ticker")
        or raw.get("symbol")
        or _extract_ticker_from_message(raw.get("message", ""))
        or "UNKNOWN"
    )

    return TradingViewAlert(
        ticker=ticker.upper(),
        exchange=raw.get("exchange"),
        price=_safe_float(raw.get("price") or raw.get("close") or raw.get("last")),
        alert_name=raw.get("alert_name") or raw.get("alertName") or raw.get("name"),
        message=raw.get("message") or raw.get("text") or raw.get("comment"),
        time=raw.get("time") or raw.get("timenow") or raw.get("timestamp"),
        raw=raw,
    )


def format_alert_message(alert: TradingViewAlert) -> str:
    """Format an alert into a Telegram-ready Markdown message."""
    price_str = f"${alert.price:,.2f}" if alert.price else "N/A"

    lines = [
        f"🔔 *TradingView Alert*",
        "",
        f"📈 *{_escape_md(alert.ticker)}*"
        + (f" \\({_escape_md(alert.exchange)}\\)" if alert.exchange else ""),
        f"💵 Price: `{price_str}`",
    ]

    if alert.alert_name:
        lines.append(f"📋 {_escape_md(alert.alert_name)}")

    if alert.message:
        lines.append(f"💬 {_escape_md(alert.message)}")

    if alert.time:
        lines.append(f"🕐 {_escape_md(str(alert.time))}")

    return "\n".join(lines)


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _extract_ticker_from_message(message: str) -> Optional[str]:
    """Try to extract a ticker symbol from a free-form message."""
    if not message:
        return None
    # Common patterns: "AAPL crossed 150", "Alert: TSLA"
    import re
    match = re.search(r"\b([A-Z]{1,5})\b", message)
    return match.group(1) if match else None


def _escape_md(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in str(text))
