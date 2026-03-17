"""
Briefing formatters + Telegram delivery.

Two daily briefings:
- Evening briefing (8 PM ET / 5 PM PT): regime + RS leaders + themes + MA pullbacks
  Delivered after market close for EOD stock review.
- Morning briefing (9 AM ET / 6 AM PT): EP alerts + quick regime context
  Delivered 30 min before open. Thin now, designed to grow.

Both send directly via Telegram Bot API (no dependency on Apollo orchestrator).
"""
from __future__ import annotations

import asyncio
import logging
import re
import os
from datetime import date
from typing import Any

import httpx

from agents.market_intelligence.collector import get_premarket_futures
from agents.market_intelligence.db import (
    get_today_ep_alerts,
    get_rs_leaders,
    get_latest_regime,
    get_ma_pullbacks,
    get_rs_velocity,
)
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


# ── Section formatters ─────────────────────────────────────────────────────────

def _format_regime_section(regime: dict, section_num: int = 1) -> str:
    label = regime.get("regime", "Unknown")
    emoji = REGIME_EMOJI.get(label, "⚫")

    spy_vs_50 = regime.get("spy_vs_50ma")
    spy_vs_200 = regime.get("spy_vs_200ma")
    qqq_vs_50 = regime.get("qqq_vs_50ma")
    vix = regime.get("vix")
    breadth = regime.get("breadth_pct_above_40ma")
    bo_bd = regime.get("bo_bd_ratio_5d")
    ep_thresh = regime.get("ep_threshold", 70)

    lines = [f"*{section_num}. MARKET CONDITION* {emoji} *{label.upper()}*"]

    ma_parts = []
    if spy_vs_50 is not None:
        ma_parts.append(f"SPY/50MA {_fmt_sign(spy_vs_50)}")
    if qqq_vs_50 is not None:
        ma_parts.append(f"QQQ/50MA {_fmt_sign(qqq_vs_50)}")
    if spy_vs_200 is not None:
        ma_parts.append(f"SPY/200MA {_fmt_sign(spy_vs_200)}")
    if ma_parts:
        lines.append("  " + "  |  ".join(ma_parts))

    if vix is not None:
        lines.append(f"  VIX {vix:.1f} — {_vix_context(vix)}")

    mkt_parts = []
    if breadth is not None:
        mkt_parts.append(f"Breadth {breadth:.0f}% above 40MA")
    if bo_bd is not None:
        mkt_parts.append(f"B/O:B/D {bo_bd:.1f}x")
    if mkt_parts:
        lines.append("  " + "  |  ".join(mkt_parts))

    lines.append(f"  EP filter: {_ep_threshold_context(ep_thresh)}")
    return "\n".join(lines)


def _format_ep_section(ep_alerts: list[dict], section_num: int = 1) -> str:
    if not ep_alerts:
        return f"*{section_num}. EP ALERTS* — None this morning"

    high = [e for e in ep_alerts if e.get("score_tier") == "HIGH"]
    moderate = [e for e in ep_alerts if e.get("score_tier") == "MODERATE"]

    lines = [f"*{section_num}. EP ALERTS* — {len(ep_alerts)} candidate(s)"]

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


def _format_rs_section(rs_leaders: list[dict], section_num: int = 2) -> str:
    if not rs_leaders:
        return f"*{section_num}. RS LEADERS* — No data yet (run data refresh first)"

    top = rs_leaders[:20]
    header = f"*{section_num}. RS LEADERS* — Top {len(top)} by RS composite"

    rows = []
    for i in range(0, len(top), 3):
        group = top[i:i + 3]
        parts = [f"{s['ticker']:<5} {int(s.get('rs_composite') or 0):>3}" for s in group]
        rows.append("`" + "   ".join(parts) + "`")

    return header + "\n" + "\n".join(rows)


def _format_theme_section(themes: list[dict], section_num: int = 3) -> str:
    if not themes:
        return f"*{section_num}. THEME HEALTH* — No theme data yet (run data refresh first)"

    # Prioritize Accelerating/Mainstream over Nascent for display order
    _stage_order = {"Accelerating": 0, "Mainstream": 1, "Nascent": 2}
    active = sorted(
        [t for t in themes if t.get("stage") != "Fading"],
        key=lambda t: (_stage_order.get(t.get("stage", ""), 3), -(t.get("score") or 0)),
    )
    fading = [t for t in themes if t.get("stage") == "Fading"]

    lines = [f"*{section_num}. THEME HEALTH* — {len(active)} active"]

    for t in active[:6]:
        stage = t.get("stage", "")
        emoji = STAGE_EMOJI.get(stage, "")
        score = t.get("score", 0)
        tickers = (t.get("tickers") or [])[:6]  # cap at 6 tickers shown
        tickers_str = "  ".join(f"`{tk}`" for tk in tickers)
        lines.append("")
        lines.append(f"{emoji} *{t['name']}*  _{stage}_ · {score:.0f}")
        lines.append(f"  {tickers_str}")
        if t.get("description"):
            # Strip any residual markdown chars that would break Telegram's parser
            desc = re.sub(r"\*+", "", t["description"]).strip()
            lines.append(f"  _{desc}_")

    if fading:
        lines.append("")
        fading_names = "  ·  ".join(t.get("name", "?") for t in fading[:5])
        lines.append(f"🔻 _Fading:_ {fading_names}")

    return "\n".join(lines)


def _format_velocity_section(velocity: list[dict], section_num: int = 4) -> str:
    """Stocks with sustained multi-week RS acceleration — the early signal."""
    if not velocity:
        return ""

    lines = [f"*{section_num}. RISING* — Sustained RS acceleration (early signal)"]

    for s in velocity[:6]:
        ticker = s["ticker"]
        rs = int(s.get("rs_now") or 0)

        weeks = []
        for key in ["v1w", "v2w", "v3w", "v4w"]:
            v = s.get(key)
            if v is not None:
                weeks.append(f"{'+' if v >= 0 else ''}{v:.0f}")

        weeks_str = " → ".join(weeks)  # wk1 → wk2 → wk3 → wk4 (most recent first)

        # Sustained flag: all available weekly deltas positive
        all_positive = all(
            s.get(k, 0) >= 0 for k in ["v1w", "v2w", "v3w", "v4w"] if s.get(k) is not None
        )
        flag = " ↑" if all_positive else ""

        lines.append(f"  `{ticker}` RS {rs}  [{weeks_str}]{flag}")

    lines.append("  _wk1→wk2→wk3→wk4 RS change. ↑ = rising all weeks_")
    return "\n".join(lines)


def _format_pullbacks_section(pullbacks: list[dict], section_num: int = 5) -> str:
    if not pullbacks:
        return f"*{section_num}. MA PULLBACKS* — None in range today"

    header = f"*{section_num}. MA PULLBACKS* — Stocks near key MAs"

    lines = [header]
    for s in pullbacks[:12]:
        ticker = s["ticker"]
        close = s.get("close", 0)
        rs = int(s.get("rs_composite") or 0)
        near = s.get("near_mas", [])

        ma_10 = next((m for m in near if m["ma"] == "10MA"), None)
        ma_20 = next((m for m in near if m["ma"] == "20MA"), None)

        def _pct(m: dict) -> str:
            v = m["pct_from_ma"]
            return f"{'+' if v >= 0 else ''}{v:.1f}%"

        ma_parts = []
        if ma_10:
            ma_parts.append(f"10MA {_pct(ma_10)}")
        if ma_20:
            ma_parts.append(f"20MA {_pct(ma_20)}")

        line = f"{ticker:<5} RS {rs:<3} {close:>8.2f}  —  {' | '.join(ma_parts)}"
        lines.append(f"`{line}`")

    return "\n".join(lines)


# ── Evening briefing ───────────────────────────────────────────────────────────

def _format_evening_briefing(
    regime: dict,
    rs_leaders: list[dict],
    themes: list[dict],
    velocity: list[dict],
    pullbacks: list[dict],
    briefing_date: str,
) -> str:
    velocity_section = _format_velocity_section(velocity, section_num=4)
    sections = [
        f"*Apollo Evening Briefing — {briefing_date}*",
        "",
        _format_regime_section(regime, section_num=1),
        "",
        _format_rs_section(rs_leaders, section_num=2),
        "",
        _format_theme_section(themes, section_num=3),
        "",
    ]
    if velocity_section:
        sections += [velocity_section, ""]
    sections += [
        _format_pullbacks_section(pullbacks, section_num=5 if velocity_section else 4),
        "",
        "_Do your review. Pull up charts. Apply your judgment._",
    ]
    return "\n".join(sections)


async def send_evening_briefing(chat_id: int | None = None) -> str:
    """
    Assemble and send the evening briefing (regime + RS + themes + velocity + pullbacks).
    Returns the briefing text.
    """
    today_str = date.today().strftime("%Y-%m-%d")

    regime, rs_leaders, themes, velocity, pullbacks = await asyncio.gather(
        get_latest_regime(),
        get_rs_leaders(today_str, limit=30),
        get_today_themes(today_str),
        get_rs_velocity(today_str, min_rs=40.0, limit=15),
        get_ma_pullbacks(today_str),
    )
    regime = regime or {"regime": "Unknown", "ep_threshold": 70}

    text = _format_evening_briefing(
        regime=regime,
        rs_leaders=rs_leaders,
        themes=themes,
        velocity=velocity,
        pullbacks=pullbacks,
        briefing_date=today_str,
    )

    success = await send_telegram_message(text, chat_id)
    if success:
        logger.info(f"Evening briefing sent for {today_str}")
    else:
        logger.error("Failed to send evening briefing")

    return text


# ── Morning briefing ───────────────────────────────────────────────────────────

# Theme bonus for EP composite sort (sort-only — displayed score unchanged)
_THEME_BONUS = {"Accelerating": 15, "Mainstream": 10, "Nascent": 5}


def _ep_composite_key(ep: dict, theme_stage_by_ticker: dict[str, str]) -> float:
    """
    Composite priority score for sorting EP alerts in the morning briefing.
    = EP score + theme bonus + RS rank bonus (capped at 10).

    Theme bonus: Accelerating=15, Mainstream=10, Nascent=5, none=0.
    RS bonus: rs_composite / 10, capped at 10 (RS 100 → +10, RS 50 → +5).

    The displayed ep_score is never modified — this is sort-order only.
    """
    theme_stage = theme_stage_by_ticker.get(ep["ticker"], "")
    theme_bonus = _THEME_BONUS.get(theme_stage, 0)
    rs_bonus = min((ep.get("rs_composite") or 0) / 10, 10)
    return ep["ep_score"] + theme_bonus + rs_bonus


def _format_morning_briefing(
    regime: dict,
    ep_alerts: list[dict],
    briefing_date: str,
    futures: dict[str, float] | None = None,
    themes: list[dict] | None = None,
) -> str:
    label = regime.get("regime", "Unknown")
    emoji = REGIME_EMOJI.get(label, "⚫")
    vix = regime.get("vix")
    ep_thresh = regime.get("ep_threshold", 70)

    vix_str = f"VIX {vix:.1f}" if vix is not None else ""
    regime_line = f"Market: {emoji} *{label}*"
    if vix_str:
        regime_line += f"  |  {vix_str}"
    regime_line += f"  |  EP filter {_ep_threshold_context(ep_thresh)}"

    sections = [f"*Apollo Morning Briefing — {briefing_date}*", regime_line]

    if futures:
        parts = []
        if "es_pct" in futures:
            parts.append(f"ES *{_fmt_sign(futures['es_pct'])}*")
        if "nq_pct" in futures:
            parts.append(f"NQ *{_fmt_sign(futures['nq_pct'])}*")
        if parts:
            sections.append("Futures: " + "  |  ".join(parts))

    # Build ticker → theme stage map for composite sort (keep strongest stage per ticker)
    theme_stage_by_ticker: dict[str, str] = {}
    for t in (themes or []):
        stage = t.get("stage", "")
        for ticker in (t.get("tickers") or []):
            existing = theme_stage_by_ticker.get(ticker, "")
            if _THEME_BONUS.get(stage, 0) > _THEME_BONUS.get(existing, 0):
                theme_stage_by_ticker[ticker] = stage

    sorted_eps = sorted(
        ep_alerts,
        key=lambda ep: _ep_composite_key(ep, theme_stage_by_ticker),
        reverse=True,
    )

    sections += [
        "",
        _format_ep_section(sorted_eps, section_num=1),
        "",
        "_EP scan: 4–6:30 AM PT. HIGH alerts sent in real-time._",
    ]
    return "\n".join(sections)


async def send_morning_briefing(chat_id: int | None = None) -> str:
    """
    Assemble and send the morning briefing (EP alerts + regime context).
    Returns the briefing text.
    """
    today_str = date.today().strftime("%Y-%m-%d")

    regime, ep_alerts, futures, themes = await asyncio.gather(
        get_latest_regime(),
        get_today_ep_alerts(today_str),
        get_premarket_futures(),
        get_today_themes(today_str),
    )
    regime = regime or {"regime": "Unknown", "ep_threshold": 70}

    text = _format_morning_briefing(
        regime=regime,
        ep_alerts=ep_alerts,
        briefing_date=today_str,
        futures=futures,
        themes=themes,
    )

    success = await send_telegram_message(text, chat_id)
    if success:
        logger.info(f"Morning briefing sent for {today_str}")
    else:
        logger.error("Failed to send morning briefing")

    return text


# ── Telegram delivery ──────────────────────────────────────────────────────────

async def send_telegram_message(text: str, chat_id: int | None = None) -> bool:
    """Send a message directly via Telegram Bot API. Splits if over 4000 chars."""
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

    # Split into chunks if over Telegram's 4096-char limit
    chunks: list[str] = []
    if len(text) <= 4000:
        chunks = [text]
    else:
        # Split at double-newline (section boundaries) to keep sections intact
        remaining = text
        while len(remaining) > 4000:
            split_at = remaining.rfind("\n\n", 0, 4000)
            if split_at == -1:
                split_at = 4000
            chunks.append(remaining[:split_at].strip())
            remaining = remaining[split_at:].strip()
        if remaining:
            chunks.append(remaining)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            for chunk in chunks:
                r = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": chunk,
                        "parse_mode": "Markdown",
                        "disable_web_page_preview": True,
                    },
                )
                r.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


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
