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
from collections import defaultdict
from datetime import date
from typing import Any

import httpx

from agents.market_intelligence.collector import (
    get_premarket_futures,
    get_overnight_snapshot,
    search_news_perplexity,
)
from agents.market_intelligence.db import (
    get_today_ep_alerts,
    get_rs_leaders,
    get_latest_regime,
    get_ma_pullbacks,
    get_rs_velocity,
    get_rs_turners,
    get_overnight_watchlist,
    get_fundamental_flags,
    get_rs_for_tickers,
    get_prior_theme_scores,
)
from agents.market_intelligence.constants import trimmed_mean as _trimmed_mean
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
    pct4_5d = regime.get("bo_bd_ratio_5d")
    pct4_10d = regime.get("pct4_ratio_10d")
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
    # Show 10d ratio if available, else 5d
    if pct4_10d is not None:
        mkt_parts.append(f"+/-4% 10d {pct4_10d:.1f}x")
    elif pct4_5d is not None:
        mkt_parts.append(f"+/-4% 5d {pct4_5d:.1f}x")
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
        gem = " ✓Pplx" if ep.get("gemini_validation") == ep.get("catalyst_quality") else ""
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


def _eps_flag(ticker: str, fund_flags: dict[str, dict]) -> str:
    """
    Compact EPS flag for briefing display. Informational only — never filters stocks.

    EPS++67%  = accelerating, latest qtr YoY growth shown (strong O'Neil signal)
    EPS+22%   = accelerating, smaller magnitude
    eps+12%   = decelerating (growth rate slowing)
    eps-5%    = decelerating, negative growth
    """
    f = fund_flags.get(ticker)
    if not f:
        return ""
    latest = f.get("eps_yoy_latest")
    if latest is None:
        return ""
    acc = f.get("eps_accelerating")
    pct = f"{latest:+.0f}%"
    arrow = "⬆" if acc is True else ""
    return f" EPS{pct}{arrow}"


def _earnings_flag(ticker: str, fund_flags: dict[str, dict], today: date) -> str:
    """Show earnings proximity flag: 📅 if reporting within 5 trading days."""
    f = fund_flags.get(ticker)
    if not f or not f.get("next_earnings_date"):
        return ""
    ed = f["next_earnings_date"]
    delta = (ed - today).days
    if delta < 0:
        return ""  # already reported
    if delta <= 7:  # ~5 trading days
        return " 📅"
    return ""


def _format_rs_section(
    rs_leaders: list[dict],
    section_num: int = 2,
    fund_flags: dict[str, dict] | None = None,
) -> str:
    if not rs_leaders:
        return f"*{section_num}. RS LEADERS* — No data yet (run data refresh first)"

    fund_flags = fund_flags or {}
    today = date.today()
    top = rs_leaders[:20]
    header = f"*{section_num}. RS LEADERS* — Top {len(top)} by RS composite"

    # If we have fundamental flags, use single-column format for readability
    if fund_flags:
        rows = []
        for s in top:
            ticker = s["ticker"]
            rs = int(s.get("rs_composite") or 0)
            eps = _eps_flag(ticker, fund_flags)
            earn = _earnings_flag(ticker, fund_flags, today)
            rows.append(f"`{ticker:<6} RS {rs:>3}`{eps}{earn}")
        footer = "_EPS % = latest qtr YoY | ⬆ = accelerating_"
        return header + "\n" + "\n".join(rows) + "\n" + footer

    # Fallback: compact 3-per-row format (no fundamental data cached yet)
    rows = []
    for i in range(0, len(top), 3):
        group = top[i:i + 3]
        parts = [f"{s['ticker']:<5} {int(s.get('rs_composite') or 0):>3}" for s in group]
        rows.append("`" + "   ".join(parts) + "`")

    return header + "\n" + "\n".join(rows)


def _format_theme_section(themes: list[dict], section_num: int = 3) -> str:
    """Legacy theme section — used when theme_rs_data is not available."""
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



def _format_theme_scorecard(
    themes: list[dict],
    theme_rs_data: dict[str, dict],
    prior_scores: dict[str, float],
    section_num: int = 3,
) -> str:
    """
    Two-tier Theme RS Scorecard.

    Tier 1 (top 5): detailed — name, RS composite (1M|3M|6M), delta, top constituents
    Tier 2 (rest):  compact — one line per theme
    Fading:         collapsed list

    Uses trimmed mean for composite RS — drops bottom 20% to resist outlier drag.
    """
    if not themes:
        return f"*{section_num}. THEME SCORECARD* — No data yet"

    active = [t for t in themes if t.get("stage") != "Fading"]
    fading = [t for t in themes if t.get("stage") == "Fading"]

    # Compute per-theme RS averages from constituent stock data
    scored_themes = []
    for t in active:
        name = t["name"]
        tickers = t.get("tickers") or []
        if not tickers:
            continue

        # Gather RS values for this theme's constituents
        comps, rs1m, rs3m, rs6m = [], [], [], []
        for tk in tickers:
            rs = theme_rs_data.get(tk)
            if not rs:
                continue
            if rs.get("rs_composite") is not None:
                comps.append(rs["rs_composite"])
            if rs.get("rs_1m") is not None:
                rs1m.append(rs["rs_1m"])
            if rs.get("rs_3m") is not None:
                rs3m.append(rs["rs_3m"])
            if rs.get("rs_6m") is not None:
                rs6m.append(rs["rs_6m"])

        if not comps:
            continue

        avg_comp = _trimmed_mean(comps)
        avg_1m = _trimmed_mean(rs1m) if rs1m else 0
        avg_3m = _trimmed_mean(rs3m) if rs3m else 0
        avg_6m = _trimmed_mean(rs6m) if rs6m else 0

        # Delta vs prior day
        prior = prior_scores.get(name)
        delta = avg_comp - prior if prior is not None else None

        scored_themes.append({
            "name": name,
            "stage": t.get("stage", ""),
            "comp": avg_comp,
            "rs_1m": avg_1m,
            "rs_3m": avg_3m,
            "rs_6m": avg_6m,
            "delta": delta,
            "tickers": tickers,
            "n_stocks": len(tickers),
            "n_scored": len(comps),
        })

    # Sort by composite RS descending
    scored_themes.sort(key=lambda x: -x["comp"])

    lines = [f"*{section_num}. THEME SCORECARD* — {len(scored_themes)} active"]

    # Tier 1: Top 10 themes — detailed (3 lines each)
    for st in scored_themes[:10]:
        emoji = STAGE_EMOJI.get(st["stage"], " ")
        name = st["name"]
        delta_str = f"  Δ{st['delta']:+.1f}" if st["delta"] is not None else ""

        # Top tickers by RS (only RS 50+) for display
        ticker_rs_pairs = []
        for tk in st["tickers"]:
            rs = theme_rs_data.get(tk)
            if rs and rs.get("rs_composite") is not None and rs["rs_composite"] >= 50:
                ticker_rs_pairs.append((tk, rs["rs_composite"]))
        ticker_rs_pairs.sort(key=lambda x: -x[1])
        top_tickers = " · ".join(f"{tk} {int(rs)}" for tk, rs in ticker_rs_pairs[:5])

        lines.append("")
        lines.append(f"{emoji}*{name}*")
        lines.append(f"  RS {st['comp']:.0f} (1M {st['rs_1m']:.0f} | 3M {st['rs_3m']:.0f} | 6M {st['rs_6m']:.0f}){delta_str}")
        if top_tickers:
            lines.append(f"  {top_tickers}")

    # Tier 2: Remaining themes — compact (1 line each)
    if len(scored_themes) > 10:
        lines.append("")
        for st in scored_themes[10:]:
            emoji = STAGE_EMOJI.get(st["stage"], " ")
            delta_str = f"  Δ{st['delta']:+.1f}" if st["delta"] is not None else ""
            lines.append(f"{emoji}{st['name']}  RS {st['comp']:.0f}{delta_str}")

    # Fading: collapsed
    if fading:
        lines.append("")
        fading_names = " · ".join(t.get("name", "?") for t in fading[:5])
        lines.append(f"🔻 _Fading: {fading_names}_")

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


def _format_unanchored_section(
    rs_leaders: list[dict],
    themes: list[dict],
    section_num: int = 4,
) -> str:
    """Flag RS 80+ stocks not belonging to any active theme — potential undiscovered themes."""
    # Build set of all tickers in active (non-Fading) themes
    themed_tickers: set[str] = set()
    for t in themes:
        if t.get("stage") != "Fading":
            themed_tickers.update(t.get("tickers") or [])

    # Find RS 80+ leaders not in any theme
    unanchored = [
        s for s in rs_leaders
        if s.get("rs_composite", 0) >= 80
        and s["ticker"] not in themed_tickers
        and not s["ticker"].startswith("X")  # skip ETFs (XLK, XLE, etc.)
        and s["ticker"] not in ("SPY", "QQQ", "IWM")
    ]

    if not unanchored:
        return ""

    lines = [f"*{section_num}. ⚠️ UNANCHORED LEADERS* — RS 80+ with no theme"]
    lines.append("  _These stocks are outperforming without an assigned theme._")
    lines.append("  _Investigate — a new theme may be forming._")

    from agents.market_intelligence.universe import get_description
    for s in unanchored[:10]:
        ticker = s["ticker"]
        rs = int(s.get("rs_composite") or 0)
        sector = s.get("sector", "")
        desc = get_description(ticker)
        desc_part = f" — {desc}" if desc else ""
        lines.append(f"  `{ticker}` RS {rs}  ({sector}{desc_part})")

    return "\n".join(lines)


def _format_turners_section(turners: list[dict], section_num: int = 5) -> str:
    """Sector clusters turning from weak to strengthening — rotation watch."""
    if not turners:
        return ""

    # Group by sector
    by_sector: dict[str, list[dict]] = defaultdict(list)
    for s in turners:
        sector = s.get("sector") or "Unknown"
        by_sector[sector].append(s)

    # Only show sectors with 2+ stocks turning together (cluster signal)
    clusters = {k: v for k, v in by_sector.items() if len(v) >= 2}
    if not clusters:
        return ""

    lines = [f"*{section_num}. ROTATION WATCH* — Sectors turning from weak to improving"]

    for sector, stocks in sorted(clusters.items(), key=lambda x: -len(x[1])):
        # Sector header with avg RS gain
        avg_gain = sum(s.get("rs_gain", 0) for s in stocks) / len(stocks)
        avg_now = sum(s.get("rs_now", 0) for s in stocks) / len(stocks)
        weeks = max(s.get("consecutive_up_weeks", 0) for s in stocks)
        tickers = ", ".join(s["ticker"] for s in stocks[:6])
        lines.append(
            f"  *{sector}* ({len(stocks)} names, {weeks}wk streak)"
            f" — RS avg {avg_now:.0f}, was {avg_now - avg_gain:.0f}"
        )
        lines.append(f"    {tickers}")

    lines.append("  _Groups rising from weak RS for 3+ consecutive weeks_")
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
    turners: list[dict] | None = None,
    briefing_date: str = "",
    fund_flags: dict[str, dict] | None = None,
    theme_rs_data: dict[str, dict] | None = None,
    prior_theme_scores: dict[str, float] | None = None,
) -> str:
    next_num = 4

    # Theme section: use scorecard if RS data available, else legacy format
    if theme_rs_data:
        theme_section = _format_theme_scorecard(
            themes, theme_rs_data, prior_theme_scores or {}, section_num=3,
        )
    else:
        theme_section = _format_theme_section(themes, section_num=3)

    # Unanchored: RS 80+ stocks not in any theme
    unanchored_section = _format_unanchored_section(rs_leaders, themes, section_num=next_num)
    if unanchored_section:
        next_num += 1

    velocity_section = _format_velocity_section(velocity, section_num=next_num)
    if velocity_section:
        next_num += 1

    turners_section = _format_turners_section(turners or [], section_num=next_num)
    if turners_section:
        next_num += 1

    sections = [
        f"*Apollo Evening Briefing — {briefing_date}*",
        "",
        _format_regime_section(regime, section_num=1),
        "",
        _format_rs_section(rs_leaders, section_num=2, fund_flags=fund_flags),
        "",
        theme_section,
        "",
    ]
    if unanchored_section:
        sections += [unanchored_section, ""]
    if velocity_section:
        sections += [velocity_section, ""]
    if turners_section:
        sections += [turners_section, ""]
    sections += [
        _format_pullbacks_section(pullbacks, section_num=next_num),
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

    regime, rs_leaders, themes, velocity, pullbacks, turners, fund_flags, prior_theme_scores = (
        await asyncio.gather(
            get_latest_regime(),
            get_rs_leaders(today_str, limit=30),
            get_today_themes(today_str),
            get_rs_velocity(today_str, min_rs=40.0, limit=15),
            get_ma_pullbacks(today_str),
            get_rs_turners(today_str),
            get_fundamental_flags(today_str),
            get_prior_theme_scores(today_str),
        )
    )
    regime = regime or {"regime": "Unknown", "ep_threshold": 70}

    # Collect all theme constituent tickers and fetch their RS data in one query
    all_theme_tickers = []
    for t in themes:
        all_theme_tickers.extend(t.get("tickers") or [])
    all_theme_tickers = list(set(all_theme_tickers))
    theme_rs_data = await get_rs_for_tickers(today_str, all_theme_tickers) if all_theme_tickers else {}

    text = _format_evening_briefing(
        regime=regime,
        rs_leaders=rs_leaders,
        themes=themes,
        velocity=velocity,
        pullbacks=pullbacks,
        turners=turners,
        briefing_date=today_str,
        fund_flags=fund_flags,
        theme_rs_data=theme_rs_data,
        prior_theme_scores=prior_theme_scores,
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


def _format_overnight_section(
    snapshot: list[dict],
    news: str | None = None,
) -> str:
    """Format the overnight market moves + headline news section."""
    if not snapshot:
        return ""

    lines = ["*OVERNIGHT*"]

    # Price line: ES -1.8% | NQ -2.3% | VIX 34 (+18%) | CL $112 (+4.2%)
    parts = []
    for item in snapshot:
        name = item["name"]
        pct = item["pct_change"]
        price = item["price"]
        sign = "+" if pct >= 0 else ""
        if item["category"] == "volatility":
            parts.append(f"{name} {price:.0f} ({sign}{pct:.1f}%)")
        elif item["category"] == "commodity":
            parts.append(f"{name} ${price:.0f} ({sign}{pct:.1f}%)")
        else:
            parts.append(f"{name} *{sign}{pct:.1f}%*")
    lines.append("  " + "  |  ".join(parts))

    # News or no-news signal
    if news:
        # Split into bullet points by sentence.
        # Only split on ". " followed by uppercase (avoids "U.S. ", "S&P ", "0.7% ")
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', news)
        for s in sentences:
            s = s.strip()
            if s:
                lines.append(f"  • _{s}_")
    else:
        # Check if any index moved significantly
        index_moves = [i for i in snapshot if i["category"] == "index" and i["triggered"]]
        if index_moves:
            lines.append("  _No clear headline catalyst. Gap in a news vacuum — watch for institutional flow._")

    return "\n".join(lines)


async def _get_economic_calendar() -> str | None:
    """
    Fetch today's key economic events via Perplexity.
    Returns a concise string of events or None.
    """
    today = date.today()
    day_str = today.strftime("%A, %B %d, %Y")
    query = (
        f"What are the key US economic events, data releases, and Fed speeches scheduled for {day_str}? "
        f"Include times (Eastern). One item per line, maximum 5 items. No preamble."
    )
    try:
        from agents.market_intelligence.theme_engine import _is_garbage
        answer = await search_news_perplexity(query, recency="day")
        if not answer or _is_garbage(answer):
            return None
        # Clean up citation markers and markdown
        clean = re.sub(r"\[\d+\]", "", answer)
        clean = re.sub(r"\*+", "", clean).replace("#", "")

        # Try splitting by newlines first (if Perplexity returned line-separated)
        raw_lines = [l.strip() for l in clean.split("\n") if l.strip()]

        # If single paragraph, split by sentence boundaries
        if len(raw_lines) <= 1 and raw_lines:
            text = raw_lines[0]
            sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
            raw_lines = [s.strip() for s in sentences if s.strip()]

        bullets = []
        for line in raw_lines[:5]:
            # Strip leading numbering (1. 2. etc) or bullet chars
            line = re.sub(r"^[\d]+[.)]\s*", "", line)
            line = re.sub(r"^[-•]\s*", "", line).strip()
            if line:
                bullets.append(f"• {line}")
        return "\n".join(bullets) if bullets else None
    except Exception as e:
        logger.warning(f"Economic calendar fetch failed: {e}")
        return None


async def _get_overnight_news(snapshot: list[dict]) -> str | None:
    """
    Query Perplexity for overnight market news if any instrument breached its threshold.
    Returns concise news string or None.
    """
    triggered = [i for i in snapshot if i["triggered"]]
    if not triggered:
        return None

    # Build a contextual query based on what moved
    movers = []
    for item in triggered:
        sign = "up" if item["pct_change"] > 0 else "down"
        movers.append(f"{item['name']} {sign} {abs(item['pct_change']):.1f}%")
    movers_str = ", ".join(movers)

    query = (
        f"What major market-moving news happened since yesterday's market close? "
        f"Context: {movers_str}. Be concise, maximum 3 sentences."
    )

    from agents.market_intelligence.theme_engine import _is_garbage
    answer = await search_news_perplexity(query, recency="day")
    if not answer or _is_garbage(answer):
        return None

    # Clean up
    clean = re.sub(r"\[\d+\]", "", answer)
    clean = re.sub(r"\*+", "", clean).replace("#", "").replace("\n", " ")
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _format_morning_briefing(
    regime: dict,
    ep_alerts: list[dict],
    briefing_date: str,
    futures: dict[str, float] | None = None,
    themes: list[dict] | None = None,
    overnight_section: str | None = None,
    econ_calendar: str | None = None,
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

    # Overnight section (market moves + news) — replaces old futures line
    if overnight_section:
        sections.append("")
        sections.append(overnight_section)
    elif futures:
        parts = []
        if "es_pct" in futures:
            parts.append(f"ES *{_fmt_sign(futures['es_pct'])}*")
        if "nq_pct" in futures:
            parts.append(f"NQ *{_fmt_sign(futures['nq_pct'])}*")
        if parts:
            sections.append("Futures: " + "  |  ".join(parts))

    # Economic calendar
    if econ_calendar:
        sections.append("")
        sections.append(f"*CALENDAR*\n{econ_calendar}")

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
        "_EP scan: 4–7 AM PT. HIGH alerts sent in real-time._",
    ]
    return "\n".join(sections)


async def send_morning_briefing(chat_id: int | None = None) -> str:
    """
    Assemble and send the morning briefing.
    Includes overnight market moves + headline news, EP alerts, regime context.
    """
    today_str = date.today().strftime("%Y-%m-%d")

    regime, ep_alerts, futures, themes, watchlist, econ_calendar = await asyncio.gather(
        get_latest_regime(),
        get_today_ep_alerts(today_str),
        get_premarket_futures(),
        get_today_themes(today_str),
        get_overnight_watchlist(),
        _get_economic_calendar(),
    )
    regime = regime or {"regime": "Unknown", "ep_threshold": 70}

    # Fetch overnight snapshot from watchlist instruments
    overnight_section = None
    if watchlist:
        snapshot = await get_overnight_snapshot(watchlist)
        if snapshot:
            news = await _get_overnight_news(snapshot)
            overnight_section = _format_overnight_section(snapshot, news)

    text = _format_morning_briefing(
        regime=regime,
        ep_alerts=ep_alerts,
        briefing_date=today_str,
        futures=futures,
        themes=themes,
        overnight_section=overnight_section,
        econ_calendar=econ_calendar,
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
    gem = " ✓Pplx" if ep.get("gemini_validation") == ep.get("catalyst_quality") else ""

    text = (
        f"*EP ALERT {tier_e}*\n\n"
        f"*{ep['ticker']}* {cat_e} {ep.get('catalyst_quality', '').replace('_', ' ').title()}\n"
        f"Gap: *{ep['gap_pct']:.1f}%* | Rel Vol: *{ep.get('rel_volume') or '?'}x* | Score: *{ep['ep_score']:.0f}*\n\n"
        f"_{ep.get('claude_analysis', '')}_\n\n"
        f"Catalyst: {ep.get('catalyst', 'See news')[:300]}"
    )
    if ep.get("confidence_multiplier", 1.0) > 1.0:
        text += f"\n\n_Claude + Perplexity agree — {ep['confidence_multiplier']:.1f}x confidence_"

    await send_telegram_message(text, chat_id)
