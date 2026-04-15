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
from datetime import date, timedelta
from typing import Any

import httpx

from agents.market_intelligence.collector import (
    et_today as _et_today,
    get_premarket_snapshot,
    get_overnight_snapshot,
    search_news_perplexity,
)
from agents.market_intelligence.db import (
    get_today_ep_alerts,
    get_ep_scan_log,
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
from agents.market_intelligence.data_quality import get_quality_warnings
from agents.market_intelligence.constants import trimmed_mean as _trimmed_mean, REGIME_EMOJI
from agents.market_intelligence.theme_engine import get_today_themes

logger = logging.getLogger(__name__)

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


def _conviction_suffix(theme: dict) -> str:
    """Return conviction display suffix, e.g. '  d14 🔥×3' or ''."""
    days = theme.get("days_active") or 0
    consec = theme.get("consecutive_accelerating") or 0
    parts = []
    if days > 1:
        parts.append(f"d{days}")
    if consec >= 2:
        parts.append(f"🔥×{consec}")
    return ("  " + " ".join(parts)) if parts else ""


# Sentence-split regex: split on "./?/! " followed by uppercase.
# Requires 2+ lowercase/digit chars before the punctuation, which naturally
# avoids splitting after abbreviations like U.S., a.m., Dr., St., etc.
_SENTENCE_SPLIT_RE = re.compile(r'(?<=[a-z0-9][a-z0-9][.!?])\s+(?=[A-Z])')


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

    # Stockbee Market Monitor — asyncpg may return JSONB as string
    bm = regime.get("breadth_monitor") or {}
    if isinstance(bm, str):
        import json
        try:
            bm = json.loads(bm)
        except (json.JSONDecodeError, TypeError):
            bm = {}

    # Primary: daily 4% counts (colored) + ratios (raw numbers)
    r5 = bm.get("ratio_5d") or pct4_5d
    r10 = bm.get("ratio_10d") or pct4_10d
    up4 = bm.get("today_up4", regime.get("full_up4_count"))
    down4 = bm.get("today_down4", regime.get("full_down4_count"))

    primary_parts = ["Primary"]
    if up4 is not None and down4 is not None:
        count_emoji = "🟢" if up4 > down4 else "🔴"
        primary_parts.append(f"{count_emoji} {up4}↑ {down4}↓")
    ratio_parts = []
    if r5 is not None:
        ratio_parts.append(f"5d {r5:.2f}x")
    if r10 is not None:
        ratio_parts.append(f"10d {r10:.2f}x")
    if ratio_parts:
        primary_parts.append("  ".join(ratio_parts))
    lines.append("  " + "  |  ".join(primary_parts))

    # Secondary: T2108 (contrarian — green when oversold <20) + momentum counts (colored)
    t2108 = bm.get("t2108") or regime.get("t2108")
    consec_bd = bm.get("consec_breakdown_days") or regime.get("consec_breakdown_days") or 0

    secondary_parts = ["Secondary"]
    if t2108 is not None:
        t_emoji = "🟢" if t2108 < 20 else ""
        secondary_parts.append(f"T2108 {t_emoji}{t2108:.0f}%")
    up50 = bm.get("up_50_1m", regime.get("pradeep_1m_50"))
    down50 = bm.get("down_50_1m")
    if up50 is not None and down50 is not None:
        m_emoji = "🟢" if up50 > down50 else "🔴"
        secondary_parts.append(f"50%/M {m_emoji}{up50}↑/{down50}↓")
    elif up50 is not None:
        secondary_parts.append(f"50%/M {up50}↑")
    up25q = bm.get("up_25_3m", regime.get("pradeep_3m_25"))
    down25q = bm.get("down_25_3m")
    if up25q is not None and down25q is not None:
        q_emoji = "🟢" if up25q > down25q else "🔴"
        secondary_parts.append(f"25%/Q {q_emoji}{up25q}↑/{down25q}↓")
    elif up25q is not None:
        secondary_parts.append(f"25%/Q {up25q}↑")
    lines.append("  " + "  |  ".join(secondary_parts))

    if consec_bd > 0:
        lines.append(f"  ⚠️ {consec_bd} consecutive breakdown days (700+ stocks down 4%+)")

    lines.append(f"  EP filter: {_ep_threshold_context(ep_thresh)}")
    return "\n".join(lines)


def _format_ep_section(
    ep_alerts: list[dict],
    section_num: int = 1,
    scan_log: list[dict] | None = None,
) -> str:
    filtered = [r for r in (scan_log or []) if r.get("filter_reason")]
    total_scanned = len(ep_alerts) + len(filtered)
    # Also count candidates beyond the top-20 cap
    beyond_cap = [r for r in filtered if "top-20" in (r.get("filter_reason") or "")]
    total_scanned += len(beyond_cap)  # already counted in filtered, just for clarity

    scan_count_str = f"  ({total_scanned} gap candidates scanned)" if total_scanned > 0 else ""

    if not ep_alerts:
        header = f"*{section_num}. EP ALERTS* — None this morning{scan_count_str}"
    else:
        high = [e for e in ep_alerts if e.get("score_tier") == "HIGH"]
        moderate = [e for e in ep_alerts if e.get("score_tier") == "MODERATE"]
        header = (
            f"*{section_num}. EP ALERTS* — "
            f"{len(high)} HIGH  {len(moderate)} MODERATE{scan_count_str}"
        )

    lines = [header]

    for ep in ep_alerts:
        tier = ep.get("score_tier", "")
        tier_e = TIER_EMOJI.get(tier, "")
        cat_e = CATALYST_EMOJI.get(ep.get("catalyst_quality", ""), "")
        gem = " ✓verified" if ep.get("gemini_validation") == ep.get("catalyst_quality") else ""
        conf = f" {ep['confidence_multiplier']:.1f}x" if ep.get("confidence_multiplier", 1.0) > 1.0 else ""
        if tier == "HIGH":
            lines.append(
                f"  {tier_e} `{ep['ticker']}` gap *{ep['gap_pct']:.1f}%* "
                f"rv {ep.get('rel_volume') or '?'}x "
                f"score *{ep['ep_score']:.0f}* {cat_e}{gem}{conf}"
            )
            if ep.get("claude_analysis"):
                lines.append(f"    _{ep['claude_analysis'][:120]}_")
        else:
            lines.append(
                f"  {tier_e} `{ep['ticker']}` gap {ep['gap_pct']:.1f}%  "
                f"score {ep['ep_score']:.0f} — verify catalyst"
            )

    # Near-miss line — compact, one per line max 5, skip top-20-cap noise
    near_misses = [
        r for r in filtered
        if "top-20" not in (r.get("filter_reason") or "")
    ][:5]
    if near_misses:
        parts = []
        for r in near_misses:
            reason = r.get("filter_reason", "")
            # Shorten common reasons
            if "price" in reason and "<" in reason:
                short = reason.split("—")[0].strip() if "—" in reason else reason[:30]
            elif "cooldown" in reason:
                short = "cooldown"
            elif "extended" in reason:
                short = "extended"
            elif "quality" in reason:
                short = "quality filter"
            elif "routine" in reason:
                short = "routine catalyst"
            elif "low rel volume" in reason:
                short = "low rel vol"
            else:
                short = reason[:25]
            parts.append(f"`{r['ticker']}` {short}")
        lines.append(f"  _Near misses: {',  '.join(parts)}_")

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
    today = _et_today()
    top = rs_leaders[:20]
    header = f"*{section_num}. RS LEADERS* — Top {len(top)} by RS composite"

    from agents.market_intelligence.universe import get_description

    # If we have fundamental flags, use single-column format for readability
    if fund_flags:
        rows = []
        for s in top:
            ticker = s["ticker"]
            rs = int(s.get("rs_composite") or 0)
            eps = _eps_flag(ticker, fund_flags)
            earn = _earnings_flag(ticker, fund_flags, today)
            # Short description: universe desc > sector fallback
            desc = get_description(ticker) or s.get("sector") or ""
            desc_part = f" — {desc}" if desc else ""
            rows.append(f"`{ticker:<6} RS {rs:>3}{eps}{earn}{desc_part}`")
        footer = "_EPS % = latest qtr YoY | ⬆ = accelerating_"
        return header + "\n" + "\n".join(rows) + "\n" + footer

    # Fallback: single-column with description (no fundamental data cached yet)
    rows = []
    for s in top:
        ticker = s["ticker"]
        rs = int(s.get("rs_composite") or 0)
        desc = get_description(ticker) or s.get("sector") or ""
        desc_part = f" — {desc}" if desc else ""
        rows.append(f"`{ticker:<6} RS {rs:>3}{desc_part}`")

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
        conviction = _conviction_suffix(t)
        lines.append("")
        lines.append(f"{emoji} *{t['name']}*{conviction}  _{stage}_ · {score:.0f}")
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



def _compute_scored_themes(
    themes: list[dict],
    theme_rs_data: dict[str, dict],
    prior_scores: dict[str, float],
) -> tuple[list[dict], list[dict]]:
    """
    Compute per-theme RS averages from constituent stock data.
    Returns (scored_themes sorted by composite RS desc, fading themes).
    Uses trimmed mean — drops bottom 20% to resist outlier drag.
    """
    active = [t for t in themes if t.get("stage") != "Fading"]
    fading = [t for t in themes if t.get("stage") == "Fading"]

    scored_themes = []
    for t in active:
        name = t["name"]
        tickers = t.get("tickers") or []
        if not tickers:
            continue

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

    scored_themes.sort(key=lambda x: -x["comp"])
    return scored_themes, fading


def _format_theme_scorecard(
    themes: list[dict],
    theme_rs_data: dict[str, dict],
    prior_scores: dict[str, float],
    section_num: int = 3,
) -> str:
    """
    Theme RS Scorecard — all active themes with RS composite (1M|3M|6M),
    delta, and top constituents. Fading collapsed.
    """
    if not themes:
        return f"*{section_num}. THEME SCORECARD* — No data yet"

    scored_themes, fading = _compute_scored_themes(themes, theme_rs_data, prior_scores)

    # Group by stage
    stage_order = ["Accelerating", "Mainstream", "Nascent"]
    stage_groups: dict[str, list] = {s: [] for s in stage_order}
    for st in scored_themes:
        stage_groups.setdefault(st.get("stage", "Nascent"), []).append(st)

    lines = [f"*{section_num}. THEME SCORECARD* — {len(scored_themes)} active"]

    for stage in stage_order:
        group = stage_groups.get(stage, [])
        if not group:
            continue
        emoji = STAGE_EMOJI.get(stage, "")
        lines.append(f"\n{emoji} *{stage.upper()}* ({len(group)})")

        for st in group:
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

            conviction = _conviction_suffix(st)
            lines.append("")
            lines.append(f"*{name}*{conviction}")
            lines.append(f"  RS {int(st['comp'])} (1M {int(st['rs_1m'])} | 3M {int(st['rs_3m'])} | 6M {int(st['rs_6m'])}){delta_str}")
            if top_tickers:
                lines.append(f"  {top_tickers}")

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

    # Filter: at least 2 consecutive positive weeks (v1w > 0 AND v2w > 0)
    active = [s for s in velocity
              if (s.get("v1w") or 0) > 0 and (s.get("v2w") or 0) > 0]
    if not active:
        return ""

    lines = [f"*{section_num}. RISING* — Sustained RS acceleration (early signal)"]

    for s in active[:6]:
        ticker = s["ticker"]
        rs = int(s.get("rs_now") or 0)

        weeks = []
        for key in ["v1w", "v2w", "v3w", "v4w"]:
            v = s.get(key)
            if v is not None:
                weeks.append(f"{'+' if v >= 0 else ''}{v:.0f}")

        weeks_str = " ← ".join(weeks)

        # Sustained flag: all available weekly deltas positive
        all_positive = all(
            s.get(k, 0) >= 0 for k in ["v1w", "v2w", "v3w", "v4w"] if s.get(k) is not None
        )
        flag = " ↑" if all_positive else ""

        lines.append(f"  `{ticker}` RS {rs}  [{weeks_str}]{flag}")

    lines.append("  _weekly RS Δ (recent←old). ↑ = every week positive_")
    return "\n".join(lines)


def _format_unanchored_section(
    rs_leaders: list[dict],
    themes: list[dict],
    section_num: int = 4,
) -> str:
    """Flag RS 80+ stocks not belonging to any active theme — potential undiscovered themes."""
    # Build set of all tickers in ANY theme (including Fading — still "anchored")
    themed_tickers: set[str] = set()
    for t in themes:
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

    from agents.market_intelligence.universe import get_description
    for s in unanchored[:10]:
        ticker = s["ticker"]
        rs = int(s.get("rs_composite") or 0)
        desc = get_description(ticker) or s.get("sector") or ""
        desc_part = f" — {desc}" if desc else ""
        lines.append(f"`{ticker:<6} RS {rs:>3}{desc_part}`")

    return "\n".join(lines)


def _format_turners_section(turners: list[dict], section_num: int = 5) -> str:
    """Sector clusters turning from weak to strengthening — rotation watch."""
    if not turners:
        return ""

    # Group by sector (skip stocks with no sector data)
    by_sector: dict[str, list[dict]] = defaultdict(list)
    for s in turners:
        sector = s.get("sector")
        if not sector:
            continue
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


def _format_quality_warnings(warnings: list[str]) -> str:
    """Format data quality warnings for prepending to briefings."""
    if not warnings:
        return ""
    lines = ["⚠️ *DATA QUALITY*"]
    for w in warnings:
        lines.append(f"  {w}")
    return "\n".join(lines)


def _format_signal_quality_section(summary: dict, section_num: int = 6) -> str:
    """Format weekly signal quality report (shown on Fridays)."""
    has_rs = summary.get("rs_avg_1m") is not None
    has_ep = summary.get("ep_total", 0) > 0

    # Skip entire section if no data yet (early deployment)
    if not has_rs and not has_ep:
        return ""

    lines = [f"*{section_num}. SIGNAL QUALITY (30d)*"]

    rs_avg = summary.get("rs_avg_1m")
    spy_avg = summary.get("spy_avg_1m")
    rs_alpha = summary.get("rs_alpha")
    if rs_avg is not None and spy_avg is not None:
        lines.append(
            f"  RS Top 20: avg {'+' if rs_avg >= 0 else ''}{rs_avg:.1f}% "
            f"vs SPY {'+' if spy_avg >= 0 else ''}{spy_avg:.1f}% "
            f"(alpha {'+' if rs_alpha >= 0 else ''}{rs_alpha:.1f}%)"
        )

    ep_total = summary.get("ep_total", 0)
    ep_profitable = summary.get("ep_profitable", 0)
    ep_hit = summary.get("ep_hit_rate")
    if ep_total > 0:
        lines.append(f"  EP alerts: {ep_profitable}/{ep_total} profitable at 1M ({ep_hit:.0f}%)")

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
    quality_warnings: list[str] | None = None,
    signal_quality_summary: dict | None = None,
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
    ]

    # Data quality warnings (prepended before section 1 if any)
    if quality_warnings:
        sections.append(_format_quality_warnings(quality_warnings))
        sections.append("")

    sections += [
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
    ]

    # Weekly signal quality section (Fridays only)
    if signal_quality_summary:
        next_num += 1
        sections += [
            _format_signal_quality_section(signal_quality_summary, section_num=next_num),
            "",
        ]

    sections.append("_Do your review. Pull up charts. Apply your judgment._")
    return "\n".join(sections)


async def send_evening_briefing(chat_id: int | None = None) -> str:
    """
    Assemble and send the evening briefing (regime + RS + themes + velocity + pullbacks).
    Returns the briefing text.
    """
    today = _et_today()
    today_str = today.strftime("%Y-%m-%d")

    regime, rs_leaders, themes, velocity, pullbacks, turners, fund_flags, prior_theme_scores, warnings = (
        await asyncio.gather(
            get_latest_regime(),
            get_rs_leaders(today_str, limit=30),
            get_today_themes(today_str),
            get_rs_velocity(today_str, min_rs=40.0, limit=15),
            get_ma_pullbacks(today_str),
            get_rs_turners(today_str),
            get_fundamental_flags(today_str),
            get_prior_theme_scores(today_str),
            get_quality_warnings(today),
        )
    )
    regime = regime or {"regime": "Unknown", "ep_threshold": 70}

    # Refresh description overrides so newly enriched tickers show industry names
    try:
        from agents.market_intelligence.db import get_ticker_overrides
        from agents.market_intelligence.universe import apply_overrides
        overrides = await get_ticker_overrides()
        if overrides:
            apply_overrides(overrides)
    except Exception:
        pass

    # Collect all theme constituent tickers and fetch their RS data in one query
    all_theme_tickers = []
    for t in themes:
        all_theme_tickers.extend(t.get("tickers") or [])
    all_theme_tickers = list(set(all_theme_tickers))
    theme_rs_data = await get_rs_for_tickers(today_str, all_theme_tickers) if all_theme_tickers else {}

    # Weekly signal quality section (Fridays only: weekday 4)
    signal_quality_summary = None
    if today.weekday() == 4:
        try:
            from agents.market_intelligence.outcome_tracker import get_weekly_signal_summary
            signal_quality_summary = await get_weekly_signal_summary()
        except Exception as e:
            logger.warning(f"Signal quality summary failed: {e}")

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
        quality_warnings=warnings,
        signal_quality_summary=signal_quality_summary,
    )

    success = await send_telegram_message(text, chat_id)
    if success:
        logger.info(f"Evening briefing sent for {today_str}")
    else:
        logger.error("Failed to send evening briefing")

    # Compute scored themes for Twitter theme tweet
    scored_themes = []
    if theme_rs_data and themes:
        scored_themes, _ = _compute_scored_themes(themes, theme_rs_data, prior_theme_scores or {})

    # Send RS leaders chart mosaic + theme table image + post to Twitter/X
    mosaic_bytes = None
    try:
        from agents.market_intelligence.charts import (
            build_chart_mosaic, send_chart_mosaic, build_theme_table_image,
        )
        from agents.market_intelligence.twitter import post_to_twitter, post_theme_tweet
        chart_tickers = [s["ticker"] for s in rs_leaders[:20]]

        # Build theme table image (pass theme_rs_data for constituent ticker RS)
        theme_img = build_theme_table_image(scored_themes, today_str, theme_rs_data=theme_rs_data) if scored_themes else None

        if chart_tickers:
            mosaic_bytes, _url = await build_chart_mosaic(chart_tickers)
            twitter_tasks = [post_to_twitter(rs_leaders, regime, today_str, mosaic_bytes=mosaic_bytes)]
            if scored_themes:
                twitter_tasks.append(post_theme_tweet(scored_themes, today_str, image_bytes=theme_img))

            telegram_tasks = []
            if mosaic_bytes:
                telegram_tasks.append(send_chart_mosaic(chart_tickers, chat_id, mosaic_bytes=mosaic_bytes))

            results = await asyncio.gather(*telegram_tasks, *twitter_tasks, return_exceptions=True)
            # Log any failures — return_exceptions=True silently swallows them otherwise
            twitter_names = ["rs_leaders_tweet"]
            if scored_themes:
                twitter_names.append("theme_tweet")
            task_names = ["chart_mosaic"] * len(telegram_tasks) + twitter_names
            for name, result in zip(task_names, results):
                if isinstance(result, Exception):
                    logger.error(f"Twitter/chart task '{name}' failed: {result}")
                elif result is False:
                    logger.warning(f"Twitter/chart task '{name}' returned False (check credentials or rate limits)")
                else:
                    logger.info(f"Twitter/chart task '{name}' OK")
    except Exception as e:
        logger.warning(f"Chart mosaic / Twitter failed (non-critical): {e}")

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

    # Price line: SPY -1.8% | QQQ -2.3% | VIX 34 (+18%) | CL $112 (+4.2%)
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
        # Negative lookbehind avoids splitting after common abbreviations
        # (U.S., a.m., p.m., e.g., i.e., vs., etc., Dr., Mr., Mrs., St., Corp., Inc.)
        # and after single uppercase letters (initials like "J. Powell").
        sentences = _SENTENCE_SPLIT_RE.split(news)
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
    today = _et_today()
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
            sentences = _SENTENCE_SPLIT_RE.split(text)
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


async def _get_overnight_news(snapshot: list[dict] | None = None) -> str | None:
    """
    Query Perplexity for overnight market news.
    If snapshot has triggered movers, asks about specific moves.
    Otherwise asks for general pre-market headlines.
    Returns concise news string or None.
    """
    triggered = [i for i in (snapshot or []) if i.get("triggered")]

    if triggered:
        # Build a contextual query based on what moved
        movers = []
        for item in triggered:
            sign = "up" if item["pct_change"] > 0 else "down"
            movers.append(f"{item['name']} {sign} {abs(item['pct_change']):.1f}%")
        movers_str = ", ".join(movers)
        query = (
            f"Why are {movers_str} today? "
            f"What specific event or announcement caused this move?"
        )
    else:
        today = _et_today()
        day_str = today.strftime("%A, %B %d, %Y")
        query = (
            f"What are the top US stock market headlines for {day_str}? "
            f"Focus on overnight developments, earnings, macro events, geopolitical news "
            f"that will affect today's trading session. Be specific and direct."
        )

    _OVERNIGHT_SYSTEM = (
        "You are a financial market analyst. Identify the SPECIFIC catalyst — "
        "name the person, policy, deal, or event. Mention social media posts, "
        "presidential statements, or diplomatic developments by name if relevant. "
        "Be direct and specific. No citation numbers. "
        "Do NOT restate index prices or percentage moves — the reader already sees those. "
        "Focus only on the WHY: what news, event, or development drove the move."
    )

    from agents.market_intelligence.theme_engine import _is_garbage
    answer = await search_news_perplexity(query, recency="week", system_prompt=_OVERNIGHT_SYSTEM)
    if not answer:
        logger.warning("Overnight news: Perplexity returned empty response")
        return None
    if _is_garbage(answer):
        logger.warning(f"Overnight news: filtered as garbage: {answer[:120]}")
        return None

    # Clean up
    clean = re.sub(r"\[\d+\]", "", answer)
    clean = re.sub(r"\*+", "", clean).replace("#", "").replace("\n", " ")
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _format_earnings_calendar(
    fundamental_flags: dict[str, dict],
    themes: list[dict] | None,
    rs_scores: dict[str, dict],
    today: date,
) -> str | None:
    """Format earnings-this-week section for morning briefing.

    Returns formatted text block or None if no earnings this week.
    """
    # Determine Mon–Fri of current week
    weekday = today.weekday()  # 0=Mon
    week_start = today - timedelta(days=weekday)
    week_end = week_start + timedelta(days=4)

    # Build ticker → theme name map from themes data
    ticker_theme: dict[str, str] = {}
    for t in (themes or []):
        for tk in (t.get("tickers") or []):
            if tk not in ticker_theme:
                ticker_theme[tk] = t.get("name", "")

    # Filter tickers with earnings this week
    earnings: list[dict] = []
    for ticker, flags in fundamental_flags.items():
        ed = flags.get("next_earnings_date")
        if ed is None:
            continue
        if isinstance(ed, str):
            try:
                ed = date.fromisoformat(ed)
            except (ValueError, TypeError):
                continue
        if week_start <= ed <= week_end:
            rs = rs_scores.get(ticker, {})
            rs_comp = rs.get("rs_composite")
            earnings.append({
                "ticker": ticker,
                "date": ed,
                "rs": round(rs_comp) if rs_comp is not None else None,
                "theme": ticker_theme.get(ticker, ""),
            })

    if not earnings:
        return None

    # Sort by date, then RS descending
    earnings.sort(key=lambda e: (e["date"], -(e["rs"] or 0)))

    # Group by date
    DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    by_date: dict[date, list[dict]] = {}
    for e in earnings:
        by_date.setdefault(e["date"], []).append(e)

    lines = ["📅 *EARNINGS THIS WEEK*"]
    for d in sorted(by_date):
        entries = by_date[d]
        parts = []
        for e in entries:
            label = e["ticker"]
            if e["rs"] is not None:
                label += f" (RS {e['rs']}"
                if e["theme"]:
                    label += f", {e['theme']}"
                label += ")"
            elif e["theme"]:
                label += f" ({e['theme']})"
            parts.append(label)

        ticker_str = " · ".join(parts)
        if d == today:
            lines.append(f"  ⚠️ TODAY: {ticker_str}")
        else:
            lines.append(f"  {DAY_NAMES[d.weekday()]}: {ticker_str}")

    return "\n".join(lines)


def _format_morning_briefing(
    regime: dict,
    ep_alerts: list[dict],
    briefing_date: str,
    premarket: dict[str, float] | None = None,
    themes: list[dict] | None = None,
    overnight_section: str | None = None,
    econ_calendar: str | None = None,
    quality_warnings: list[str] | None = None,
    earnings_calendar: str | None = None,
    ep_scan_log: list[dict] | None = None,
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

    sections = [f"*Apollo Morning Briefing — {briefing_date}*"]

    # Data quality warnings
    if quality_warnings:
        sections.append(_format_quality_warnings(quality_warnings))

    sections.append(regime_line)

    # Overnight section (market moves + news) — replaces old futures line
    if overnight_section:
        sections.append("")
        sections.append(overnight_section)
    elif premarket:
        parts = []
        if "spy_pct" in premarket:
            parts.append(f"SPY *{_fmt_sign(premarket['spy_pct'])}*")
        if "qqq_pct" in premarket:
            parts.append(f"QQQ *{_fmt_sign(premarket['qqq_pct'])}*")
        if parts:
            sections.append("Pre-market: " + "  |  ".join(parts))

    # Economic calendar
    if econ_calendar:
        sections.append("")
        sections.append(f"*CALENDAR*\n{econ_calendar}")

    # Earnings this week
    if earnings_calendar:
        sections.append("")
        sections.append(earnings_calendar)

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
        _format_ep_section(sorted_eps, section_num=1, scan_log=ep_scan_log),
        "",
        "_EP scan: 4–7 AM PT. HIGH alerts sent in real-time._",
    ]
    return "\n".join(sections)


# Cache Perplexity-sourced content per day to avoid non-deterministic re-rolls
_perplexity_cache: dict[str, dict] = {}  # {date_str: {"overnight_news": str, "econ_calendar": str}}


async def send_morning_briefing(chat_id: int | None = None) -> str:
    """
    Assemble and send the morning briefing.
    Includes overnight market moves + headline news, EP alerts, regime context.
    Perplexity-sourced content (overnight news, calendar) is cached per day.
    """
    today = _et_today()
    today_str = today.strftime("%Y-%m-%d")
    cache = _perplexity_cache.get(today_str, {})

    regime, ep_alerts, premarket, themes, watchlist, warnings, fund_flags, ep_scan_log = await asyncio.gather(
        get_latest_regime(),
        get_today_ep_alerts(today_str),
        get_premarket_snapshot(),
        get_today_themes(today_str),
        get_overnight_watchlist(),
        get_quality_warnings(today),
        get_fundamental_flags(today_str),
        get_ep_scan_log(today_str),
    )
    regime = regime or {"regime": "Unknown", "ep_threshold": 70}

    # Earnings calendar — get RS scores for tickers with earnings data
    earnings_calendar_text = None
    if fund_flags:
        earnings_tickers = list(fund_flags.keys())
        rs_scores = await get_rs_for_tickers(today_str, earnings_tickers)
        earnings_calendar_text = _format_earnings_calendar(
            fund_flags, themes, rs_scores, today,
        )

    # Economic calendar — use cache if available
    if "econ_calendar" in cache:
        econ_calendar = cache["econ_calendar"]
    else:
        econ_calendar = await _get_economic_calendar()
        cache["econ_calendar"] = econ_calendar

    # Fetch overnight snapshot + news (news always fetched, even without watchlist)
    overnight_section = None
    snapshot = []
    if watchlist:
        snapshot = await get_overnight_snapshot(watchlist)
        # Override SPY/QQQ with reliable Polygon data (yfinance is stale pre-market)
        polygon_map = {"SPY": premarket.get("spy_pct"), "QQQ": premarket.get("qqq_pct")}
        for item in snapshot:
            pct = polygon_map.get(item["symbol"])
            if pct is not None:
                item["pct_change"] = round(pct, 2)
                item["triggered"] = abs(pct) >= item["threshold"]
    logger.info(f"Morning briefing: watchlist={len(watchlist)} items, snapshot={len(snapshot)} items")

    if "overnight_news" in cache:
        news = cache["overnight_news"]
        logger.info("Morning briefing: overnight news from cache")
    else:
        news = await _get_overnight_news(snapshot or None)
        cache["overnight_news"] = news
        logger.info(f"Morning briefing: overnight news={'yes' if news else 'none'} ({len(news) if news else 0} chars)")

    if snapshot:
        overnight_section = _format_overnight_section(snapshot, news)
    elif news:
        # No watchlist/snapshot, but we have news — show it standalone
        lines = ["*OVERNIGHT*"]
        sentences = _SENTENCE_SPLIT_RE.split(news)
        for s in sentences:
            s = s.strip()
            if s:
                lines.append(f"  • _{s}_")
        overnight_section = "\n".join(lines)

    # Store cache for this day
    _perplexity_cache.clear()
    _perplexity_cache[today_str] = cache

    text = _format_morning_briefing(
        regime=regime,
        ep_alerts=ep_alerts,
        briefing_date=today_str,
        premarket=premarket,
        themes=themes,
        overnight_section=overnight_section,
        econ_calendar=econ_calendar,
        quality_warnings=warnings,
        earnings_calendar=earnings_calendar_text,
        ep_scan_log=ep_scan_log,
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

    # Strip conflicting gap% from catalyst text (Perplexity may say "18%" while actual gap is 27%)
    catalyst_text = ep.get("catalyst", "See news")[:300]
    catalyst_text = re.sub(r"gapped (?:up |down )?[\d.]+%", "gapped up", catalyst_text)

    text = (
        f"*EP ALERT {tier_e}*\n\n"
        f"*{ep['ticker']}* {cat_e} {ep.get('catalyst_quality', '').replace('_', ' ').title()}\n"
        f"Gap: *{ep['gap_pct']:.1f}%* | RVOL: *{ep.get('rel_volume') or '?'}x*"
        + (f" (intensity *{ep['projected_vol_multiple']:.0f}x*)" if ep.get('projected_vol_multiple') else "")
        + f" | Score: *{ep['ep_score']:.0f}*\n\n"
        f"_{ep.get('claude_analysis', '')}_\n\n"
        f"Catalyst: {catalyst_text}"
    )
    if ep.get("confidence_multiplier", 1.0) > 1.0:
        text += f"\n\n_Claude + Perplexity agree — {ep['confidence_multiplier']:.1f}x confidence_"

    await send_telegram_message(text, chat_id)

    # Post to Twitter/X
    try:
        from agents.market_intelligence.twitter import post_ep_tweet
        await post_ep_tweet(ep)
    except Exception as e:
        logger.warning(f"EP tweet failed (non-critical): {e}")
