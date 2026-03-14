"""
Morning Briefing Formatter + Telegram Delivery.

Briefing structure:
1. MARKET CONDITION — regime, SPY/QQQ trend, breadth, risk-on/off
2. EP ALERTS — time-sensitive, shown first if any
3. RS LEADERS — top stocks by RS composite score (by sector when sector data available)
4. THEME HEALTH — placeholder for Phase 2 theme engine

Sends directly to Telegram via Bot API (no dependency on Apollo orchestrator).
"""
from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any

import httpx

from agents.market_intelligence.db import get_today_ep_alerts, get_rs_leaders, get_latest_regime
from agents.market_intelligence.theme_engine import get_today_themes

logger = logging.getLogger(__name__)

REGIME_EMOJI = {
    "Bull": "🟢",
    "Choppy": "🟡",
    "Correcting": "🔴",
    "Crisis": "🚨",
    "Unknown": "⚫",
}

TIER_EMOJI = {
    "HIGH": "🔥",
    "MODERATE": "⚡",
}

CATALYST_EMOJI = {
    "game_changer": "💎",
    "strong": "✅",
    "routine": "📋",
}

STAGE_EMOJI = {
    "Nascent": "🌱",
    "Accelerating": "⚡",
    "Mainstream": "📊",
    "Fading": "🔻",
}


def _fmt_sign(v: float) -> str:
    return f"+{v:.1f}%" if v >= 0 else f"{v:.1f}%"


def _vix_context(v: float) -> str:
    if v >= 35:
        return "crisis fear 🚨"
    elif v >= 25:
        return "elevated fear, risk-off"
    elif v >= 20:
        return "above-avg vol, caution"
    else:
        return "low fear, risk-on ✓"


def _ep_threshold_context(thresh: int) -> str:
    if thresh >= 90:
        return f"≥{thresh} — crisis, very selective"
    elif thresh >= 85:
        return f"≥{thresh} — correcting, exceptional only"
    elif thresh >= 80:
        return f"≥{thresh} — choppy, raise your bar"
    else:
        return f"≥{thresh} — standard"


def _format_regime_section(regime: dict) -> str:
    label = regime.get("regime", "Unknown")
    emoji = REGIME_EMOJI.get(label, "⚫")

    spy_vs_50 = regime.get("spy_vs_50ma")
    spy_vs_200 = regime.get("spy_vs_200ma")
    qqq_vs_50 = regime.get("qqq_vs_50ma")
    vix = regime.get("vix")
    breadth = regime.get("breadth_pct_above_40ma")
    bo_bd = regime.get("bo_bd_ratio_5d")
    ep_thresh = regime.get("ep_threshold", 70)

    lines = [f"*1. MARKET CONDITION* {emoji} *{label.upper()}*"]

    # MAs on one line
    ma_parts = []
    if spy_vs_50 is not None:
        ma_parts.append(f"SPY/50MA {_fmt_sign(spy_vs_50)}")
    if qqq_vs_50 is not None:
        ma_parts.append(f"QQQ/50MA {_fmt_sign(qqq_vs_50)}")
    if spy_vs_200 is not None:
        ma_parts.append(f"SPY/200MA {_fmt_sign(spy_vs_200)}")
    if ma_parts:
        lines.append("  " + "  |  ".join(ma_parts))

    # VIX on its own line
    if vix is not None:
        lines.append(f"  VIX {vix:.1f} — {_vix_context(vix)}")

    # Breadth + B/O:B/D on one line
    mkt_parts = []
    if breadth is not None:
        mkt_parts.append(f"Breadth {breadth:.0f}% above 40MA")
    if bo_bd is not None:
        mkt_parts.append(f"B/O:B/D {bo_bd:.1f}x")
    if mkt_parts:
        lines.append("  " + "  |  ".join(mkt_parts))

    lines.append(f"  EP filter: {_ep_threshold_context(ep_thresh)}")
    return "\n".join(lines)


def _format_ep_section(ep_alerts: list[dict]) -> str:
    if not ep_alerts:
        return "*2. EP ALERTS* — None today"

    high = [e for e in ep_alerts if e.get("score_tier") == "HIGH"]
    moderate = [e for e in ep_alerts if e.get("score_tier") == "MODERATE"]

    lines = [f"*2. EP ALERTS* — {len(ep_alerts)} candidate(s)"]

    for ep in high:
        tier_e = TIER_EMOJI.get("HIGH", "")
        cat_e = CATALYST_EMOJI.get(ep.get("catalyst_quality", ""), "")
        gem = " ✓Gemini" if ep.get("gemini_validation") == ep.get("catalyst_quality") else ""
        conf = f" {ep['confidence_multiplier']:.1f}x conf" if ep.get("confidence_multiplier", 1.0) > 1.0 else ""
        lines.append(
            f"  {tier_e} `{ep['ticker']}` gap *{ep['gap_pct']:.1f}%* "
            f"rv {ep.get('rel_volume') or '?'}x "
            f"score *{ep['ep_score']:.0f}* {cat_e}{gem}{conf}"
        )
        if ep.get("claude_analysis"):
            lines.append(f"    _{ep['claude_analysis'][:120]}_")

    for ep in moderate:
        tier_e = TIER_EMOJI.get("MODERATE", "")
        lines.append(
            f"  {tier_e} `{ep['ticker']}` gap {ep['gap_pct']:.1f}%  "
            f"score {ep['ep_score']:.0f} — verify catalyst"
        )

    return "\n".join(lines)


def _format_rs_section(rs_leaders: list[dict]) -> str:
    if not rs_leaders:
        return "*3. RS LEADERS* — No data yet (run nightly engine first)"

    lines = ["*3. RS LEADERS* — Top momentum stocks"]

    # Group by sector if available
    by_sector: dict[str, list] = {}
    no_sector = []
    for stock in rs_leaders[:30]:
        sector = stock.get("sector")
        if sector:
            by_sector.setdefault(sector, []).append(stock)
        else:
            no_sector.append(stock)

    if by_sector:
        for sector, stocks in list(by_sector.items())[:5]:
            top = stocks[:3]
            tickers_str = "  ".join(
                f"`{s['ticker']}` {s.get('rs_composite', 0):.0f}"
                for s in top
            )
            lines.append(f"  *{sector}*")
            lines.append(f"  {tickers_str}")
    else:
        # No sector data — 3 per row
        top = no_sector[:15]
        row = []
        for s in top:
            row.append(f"`{s['ticker']}` {s.get('rs_composite', 0):.0f}")
            if len(row) == 3:
                lines.append("  " + "   ".join(row))
                row = []
        if row:
            lines.append("  " + "   ".join(row))

    return "\n".join(lines)


def _format_theme_section(themes: list[dict]) -> str:
    if not themes:
        return "*4. THEME HEALTH* — No theme data yet (run nightly engine first)"

    active = [t for t in themes if t.get("stage") != "Fading"]
    fading = [t for t in themes if t.get("stage") == "Fading"]

    lines = [f"*4. THEME HEALTH* — {len(themes)} theme(s) tracked"]

    for t in active[:5]:
        stage = t.get("stage", "")
        emoji = STAGE_EMOJI.get(stage, "")
        score = t.get("score", 0)
        tickers_str = "  ".join(f"`{tk}`" for tk in (t.get("tickers") or []))
        lines.append("")  # blank line between themes
        lines.append(f"{emoji} *{t['name']}*  _{stage}_ · {score:.0f}")
        lines.append(f"  {tickers_str}")
        if t.get("description"):
            lines.append(f"  _{t['description'][:140]}_")

    if fading:
        lines.append("")
        fading_str = "  ".join(f"`{t['name']}`" for t in fading)
        lines.append(f"🔻 _Fading:_ {fading_str}")

    return "\n".join(lines)


def _format_briefing(
    regime: dict,
    ep_alerts: list[dict],
    rs_leaders: list[dict],
    themes: list[dict],
    briefing_date: str,
) -> str:
    sections = [
        f"*Apollo Market Briefing — {briefing_date}*",
        "",
        _format_regime_section(regime),
        "",
        _format_ep_section(ep_alerts),
        "",
        _format_rs_section(rs_leaders),
        "",
        _format_theme_section(themes),
        "",
        "_Pull up charts. Apply your judgment. Trade._",
    ]
    return "\n".join(sections)


async def send_telegram_message(text: str, chat_id: int | None = None) -> bool:
    """Send a message directly via Telegram Bot API."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not chat_id:
        allowed = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
        ids = [x.strip() for x in allowed.split(",") if x.strip()]
        if not ids:
            logger.error("No TELEGRAM_ALLOWED_USER_IDS configured for briefing delivery")
            return False
        chat_id = int(ids[0])

    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return False

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
            )
            r.raise_for_status()
            return True
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


async def send_morning_briefing(chat_id: int | None = None) -> str:
    """
    Assemble and send the morning briefing.
    Returns the briefing text.
    """
    today_str = date.today().strftime("%Y-%m-%d")

    regime = await get_latest_regime() or {"regime": "Unknown", "ep_threshold": 70}
    ep_alerts = await get_today_ep_alerts(today_str)
    rs_leaders = await get_rs_leaders(today_str, limit=30)
    themes = await get_today_themes(today_str)

    text = _format_briefing(
        regime=regime,
        ep_alerts=ep_alerts,
        rs_leaders=rs_leaders,
        themes=themes,
        briefing_date=today_str,
    )

    success = await send_telegram_message(text, chat_id)
    if success:
        logger.info(f"Morning briefing sent for {today_str}")
    else:
        logger.error("Failed to send morning briefing")

    return text


async def send_ep_alert(ep: dict, chat_id: int | None = None) -> None:
    """Send an immediate EP alert to Telegram."""
    tier_e = TIER_EMOJI.get(ep.get("score_tier", ""), "")
    cat_e = CATALYST_EMOJI.get(ep.get("catalyst_quality", ""), "")
    gem = " ✓Gemini" if ep.get("gemini_validation") == ep.get("catalyst_quality") else ""

    text = (
        f"*EP ALERT {tier_e}*\n\n"
        f"*{ep['ticker']}* {cat_e} {ep.get('catalyst_quality', '').replace('_', ' ').title()}\n"
        f"Gap: *{ep['gap_pct']:.1f}%* | Rel Vol: *{ep.get('rel_volume') or '?'}x* | Score: *{ep['ep_score']:.0f}*\n\n"
        f"_{ep.get('claude_analysis', '')}_\n\n"
        f"Catalyst: {ep.get('catalyst', 'See news')[:300]}"
    )
    if ep.get("confidence_multiplier", 1.0) > 1.0:
        text += f"\n\n_Claude + Gemini agree — {ep['confidence_multiplier']:.1f}x confidence_"

    await send_telegram_message(text, chat_id)
