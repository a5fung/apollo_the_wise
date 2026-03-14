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


def _format_regime_section(regime: dict) -> str:
    label = regime.get("regime", "Unknown")
    emoji = REGIME_EMOJI.get(label, "⚫")
    description = regime.get("description", "No data.")

    lines = [f"*1. MARKET CONDITION* {emoji} {label.upper()}"]

    spy_vs_50 = regime.get("spy_vs_50ma")
    spy_vs_200 = regime.get("spy_vs_200ma")
    qqq_vs_50 = regime.get("qqq_vs_50ma")
    vix = regime.get("vix")
    breadth = regime.get("breadth_pct_above_40ma")
    bo_bd = regime.get("bo_bd_ratio_5d")
    ep_thresh = regime.get("ep_threshold", 70)

    def _vix_context(v: float) -> str:
        if v >= 35:
            return "crisis fear"
        elif v >= 25:
            return "elevated fear, risk-off"
        elif v >= 20:
            return "above-average vol, caution"
        else:
            return "low fear, risk-on"

    def _ep_threshold_context(thresh: int) -> str:
        if thresh >= 90:
            return f"score ≥{thresh} — crisis mode, stay very selective"
        elif thresh >= 85:
            return f"score ≥{thresh} — correcting, exceptional setups only"
        elif thresh >= 80:
            return f"score ≥{thresh} — choppy, raise your bar"
        else:
            return f"score ≥{thresh} — standard criteria"

    indicators = []
    if spy_vs_50 is not None:
        sign = "+" if spy_vs_50 >= 0 else ""
        indicators.append(f"SPY vs 50MA: {sign}{spy_vs_50:.1f}%")
    if qqq_vs_50 is not None:
        sign = "+" if qqq_vs_50 >= 0 else ""
        indicators.append(f"QQQ vs 50MA: {sign}{qqq_vs_50:.1f}%")
    if spy_vs_200 is not None:
        sign = "+" if spy_vs_200 >= 0 else ""
        indicators.append(f"SPY vs 200MA: {sign}{spy_vs_200:.1f}%")
    if vix is not None:
        indicators.append(f"VIX: {vix:.1f} ({_vix_context(vix)})")
    if breadth is not None:
        indicators.append(f"Breadth: {breadth:.0f}% above 40MA")
    if bo_bd is not None:
        indicators.append(f"B/O:B/D: {bo_bd:.1f}x")

    if indicators:
        lines.append("  " + " | ".join(indicators))

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
        conf = f" {ep['confidence_multiplier']:.1f}x" if ep.get("confidence_multiplier", 1.0) > 1.0 else ""
        lines.append(
            f"  {tier_e} *{ep['ticker']}* gap {ep['gap_pct']:.1f}% "
            f"rv {ep.get('rel_volume') or '?'}x "
            f"score {ep['ep_score']:.0f} {cat_e}{gem}{conf}"
        )
        if ep.get("claude_analysis"):
            lines.append(f"    _{ep['claude_analysis'][:120]}_")

    for ep in moderate:
        tier_e = TIER_EMOJI.get("MODERATE", "")
        lines.append(
            f"  {tier_e} {ep['ticker']} gap {ep['gap_pct']:.1f}% "
            f"score {ep['ep_score']:.0f} (MODERATE — verify catalyst)"
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
            tickers_str = ", ".join(
                f"{s['ticker']} ({s.get('rs_composite', 0):.0f})"
                for s in top
            )
            lines.append(f"  *{sector}*: {tickers_str}")
    else:
        # No sector data — just list top stocks
        top = no_sector[:10]
        for s in top:
            rank = s.get("rs_rank", "?")
            rs = s.get("rs_composite", 0)
            lines.append(f"  #{rank} {s['ticker']} — RS {rs:.0f}")

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
        tickers_str = ", ".join(t.get("tickers") or [])
        score = t.get("score", 0)
        lines.append(f"  {emoji} *{t['name']}* ({score:.0f}) — {tickers_str}")
        if t.get("description"):
            lines.append(f"    _{t['description'][:120]}_")

    if fading:
        fading_names = ", ".join(t["name"] for t in fading)
        lines.append(f"  🔻 Fading: {fading_names}")

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
