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
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

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
    get_rs_recovery,
    get_crypto_vs_market_pulse,
    get_overnight_watchlist,
    get_fundamental_flags,
    get_rs_for_tickers,
    get_prior_theme_scores,
    get_pool,
    log_audit_event,
)
from agents.market_intelligence.data_quality import get_quality_warnings
from agents.market_intelligence.constants import trimmed_mean as _trimmed_mean, REGIME_EMOJI, TIER_RANK
from agents.market_intelligence.theme_engine import get_today_themes

logger = logging.getLogger(__name__)


# Filler patterns Perplexity returns when it has no info on a ticker.
# Without sanitization, the operator sees content like
# "I cannot find information about XYZ, but the nearest match is..."
# in the catalyst field, which is misleading. Item #12 (2026-05-19).
_PERPLEXITY_FILLER_PATTERNS = [
    # "no info found" / "cannot find" prefixes
    r"^(?:I (?:could not|cannot|can't|couldn't|do not have|don't have|am unable to find|was unable to find|don't have any|don't have specific|don't have current)[^.]*\.\s*)",
    r"^(?:Sorry,?\s+(?:but\s+)?I (?:could not|cannot|can't|couldn't)[^.]*\.\s*)",
    r"^(?:Based on (?:available|the) (?:information|data)[^.]*(?:no|cannot|unable|don't have)[^.]*\.\s*)",
    # "nearest match" hedges — these are pure hallucination fuel; always strip
    r"(?:The|A)?\s*nearest match(?:\s+(?:I (?:found|could find)|to your query|appears to be|is))?[^.]*\.\s*",
    r"(?:Closest|Most similar) (?:match|ticker|company)[^.]*\.\s*",
    # "as of my knowledge cutoff" disclaimers
    r"(?:As of my (?:knowledge|training) (?:cutoff|date)|My information (?:may be|is) (?:outdated|limited))[^.]*\.\s*",
    # "for the most current information" tail boilerplate
    r"For (?:the )?(?:most )?(?:current|latest|up-to-date|accurate) (?:information|data|news)[^.]*\.\s*$",
    r"(?:Please|I (?:recommend|suggest)) (?:check|consult|visit|refer to)[^.]*\.\s*$",
]

# Phrases that signal Perplexity's ENTIRE response is unreliable (#130, 2026-05-27).
# CRSR/DY case: Perplexity returns a disclaimer ("I don't have reliable data" /
# "is likely a ticker mismatch") followed by speculative prose ("Given that,
# here's how I'd approach it as an analyst", "If you meant DIDIY..."). The
# per-sentence stripping above removes the disclaimer but lets the
# speculative prose through. When any of these signals appear, replace the
# whole catalyst block with "See news" — hypothetical analysis is worse than
# none.
_PERPLEXITY_WHOLESALE_DISCARD_PATTERNS = [
    r"is likely a ticker mismatch",
    r"don'?t have any reliable",
    r"don'?t have (?:reliable|up[ -]?to[ -]?date|specific|current)\s+(?:news|data|information)",
    r"none of the (?:results|sources|search results) (?:shown |found |returned )?are about (?:the |this )?(?:stock|ticker|company)",
    r"here'?s how I'?d approach it as an analyst",
    # 3+ char minimum: real US tickers start at 3 chars (rare 1-2 char
    # legacy listings aside). Q1/Q2/Q3/Q4 would false-positive at 2-char
    # ("If you meant Q1, the comparison..." is legit analyst prose).
    r"If you meant [A-Z]{3,6}\b",
    r"the search results point to [A-Z][a-zA-Z]+ (?:Global|Inc|Corp)",
]
_PERPLEXITY_WHOLESALE_DISCARD_RE = re.compile(
    "|".join(_PERPLEXITY_WHOLESALE_DISCARD_PATTERNS), re.IGNORECASE
)


def _sanitize_perplexity_filler(text: str) -> str:
    """Strip Perplexity hedge/filler patterns from operator-visible text.

    Returns sanitized text; if everything gets stripped (text was 100%
    filler) OR a wholesale-discard pattern matched anywhere, returns
    "See news" as a clean fallback so the alert line still renders
    meaningfully.

    Examples (input → output):
      "I cannot find specific info on XYZ. The nearest match is ABC..."
        → "" → "See news"
      "AGYS reported Q4 earnings up 12%. As of my knowledge cutoff..."
        → "AGYS reported Q4 earnings up 12%."
      "DY is likely a ticker mismatch here: the search results point to
        DiDi Global..." → "See news"
    """
    if not text:
        return text
    # Wholesale-discard if the text contains any signal that Perplexity
    # didn't actually find the ticker / is speculating (#130).
    if _PERPLEXITY_WHOLESALE_DISCARD_RE.search(text):
        return "See news"
    cleaned = text
    for pattern in _PERPLEXITY_FILLER_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    # If sanitization removed everything (or near-everything), fall back
    if len(cleaned) < 15:
        return "See news"
    return cleaned


def _truncate_sentence(text: str, max_len: int) -> str:
    """Truncate at last sentence/word boundary within max_len — never mid-word."""
    if not text or len(text) <= max_len:
        return text
    cut = text[:max_len]
    # Prefer last sentence terminator
    for sep in (". ", "! ", "? "):
        idx = cut.rfind(sep)
        if idx >= max_len * 0.5:
            return cut[: idx + 1]
    # Else fall back to last word boundary
    idx = cut.rfind(" ")
    if idx >= max_len * 0.5:
        return cut[:idx].rstrip(",;:") + "…"
    return cut.rstrip(",;:") + "…"

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
    """Return conviction display suffix, e.g. '  d14 🔥×3 brd42%' or ''."""
    days = theme.get("days_active") or 0
    consec = theme.get("consecutive_accelerating") or 0
    breadth = theme.get("pct_above_20sma")
    parts = []
    if days > 1:
        parts.append(f"d{days}")
    if consec >= 2:
        parts.append(f"🔥×{consec}")
    if breadth is not None:
        parts.append(f"brd{int(breadth * 100)}%")
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
    # Bands match the LIVE regime thresholds (regime.py: Bull 65 · Choppy 70 · Correcting 75 ·
    # Crisis 80). The old 90/85/80 cutoffs tracked a stale docstring and mislabelled every
    # non-Bull regime as "standard" (operator 6/26: the brief printed "CORRECTING … standard").
    if thresh >= 80:
        return f"≥{thresh} — crisis, very selective"
    elif thresh >= 75:
        return f"≥{thresh} — correcting, exceptional only"
    elif thresh >= 70:
        return f"≥{thresh} — choppy, raise your bar"
    else:
        return f"≥{thresh} — standard (bull)"


# ── Section formatters ─────────────────────────────────────────────────────────

def _format_regime_section(regime: dict, section_num: int = 1) -> str:
    """Compact regime block (#479 2026-07-17: was ~20 lines with every metric
    stated TWICE — the grouped 'why' description AND a full raw re-dump of the
    same breadth numbers, all of which live on `/regime`). Now: verdict + net-
    score summary + the cluster deterioration alert (only when it FIRES) + one
    trading-actionable EP line. The full breadth matrix is `/regime`."""
    label = regime.get("regime", "Unknown")
    emoji = REGIME_EMOJI.get(label, "⚫")
    vix = regime.get("vix")
    ep_thresh = regime.get("ep_threshold", 70)

    lines = [f"*{section_num}. MARKET CONDITION* {emoji} *{label.upper()}*"]

    # Net-score summary line only (the grouped 'why' header from regime.py,
    # operator asked 6/24). The per-driver 🟢/🔴 enumeration + raw matrix → /regime.
    _desc = (regime.get("description") or "").strip()
    _desc_lines = [dl.strip() for dl in _desc.splitlines()[1:] if dl.strip()]
    if _desc_lines:
        lines.append(f"  {_desc_lines[0]}")   # "Net score -1 (3 bullish · 4 bearish)"

    # Cluster deterioration — surfaced ONLY when it fires (the actionable signal);
    # the no-fire status line is dropped (it was pure reassurance noise).
    from agents.market_intelligence.breadth_color_rules import (
        cluster_fires, red_count_in_window, CLUSTER_WINDOW,
    )
    history = regime.get("breadth_history_5d") or []
    if len(history) >= CLUSTER_WINDOW and cluster_fires(history):
        red_n = red_count_in_window(history)
        lines.append(f"  ⚠️ Cluster {red_n}/{CLUSTER_WINDOW} red — deterioration")

    # One trading-actionable line: VIX + EP filter + EP size.
    ep_bits = []
    if vix is not None:
        ep_bits.append(f"VIX {vix:.1f}")
    ep_bits.append(f"filter {_ep_threshold_context(ep_thresh)}")
    if vix is not None:
        from agents.market_intelligence.constants import vix_scaled_risk_pct, RISK_PCT
        _mult = vix_scaled_risk_pct(vix) / RISK_PCT
        if regime.get("qqq_ema_bullish") is False:
            _mult *= 0.5
        ep_bits.append(f"size ≈{_mult:.2f}×")
    lines.append("  " + " · ".join(ep_bits) + "  ·  `/regime` full matrix")
    return "\n".join(lines)


def _catalyst_type_mark(ct: str | None) -> str:
    """Marker emoji for the catalyst-TYPE 'fire' (Pradeep hierarchy): 🎯 high-
    conviction (theme/policy/shortage) · ❓ unknown (coverage gap) · ▫️ rest;
    "" when unclassified. (NOT 🔥 — that's the HIGH-tier emoji; avoid a double-🔥.)
    SSoT for the high-conviction set is catalyst_type_classifier.HIGH_CONVICTION_TYPES,
    so both EP surfaces (the immediate alert + the /ep block) share one mapping and
    can't drift."""
    if not ct:
        return ""
    from agents.market_intelligence.catalyst_type_classifier import HIGH_CONVICTION_TYPES
    return "🎯" if ct in HIGH_CONVICTION_TYPES else "❓" if ct == "unknown" else "▫️"


def _resolve_ep_rvol(ep: dict) -> tuple[str, bool]:
    """Displayable RVOL string + whether it's the pre-market anchor — SINGLE SOURCE for the
    brief/HUD line (_format_ep_ticker_block) AND the live EP-alert line. Pre-market alerts have
    rel_volume ≈ 0 (today_volume/ADV, the day's barely started), so prefer pm_rvol (pre-market
    relative volume) when rel_volume is tiny/absent. Operator 6/25: SNX/MU showed "rv 0.01x/0.03x"
    pre-market when pm_rvol was 12x/1.5x — the brief got the fix but the alert kept reading raw
    rel_volume. Returns ("12.0x", True) pre-market, ("3x", False) intraday-session."""
    _rel_v = ep.get("rel_volume")
    _pm_v = ep.get("pm_rvol")
    if _pm_v and (_rel_v is None or _rel_v < 1.0):
        return (f"{_pm_v:.1f}x", True)
    return (f"{_rel_v or '?'}x", False)


def _format_ep_ticker_block(ep: dict, lead: str = "") -> list[str]:
    """Format ONE EP alert as a list of lines — the single source of truth for
    EP per-ticker rendering, shared by the morning-briefing section AND the HUD
    `/ep` command so they can't drift. The 2026-05-29 wall-of-text was the HUD
    path rendering a raw headline + full untruncated catalyst; this gives both
    paths the code-ticker / bold-gap headline + a truncated italic catalyst
    sub-line. `lead` is the per-line indent prefix (briefing nests under a
    section; the standalone /ep view uses none)."""
    tier = ep.get("score_tier", "")
    tier_e = TIER_EMOJI.get(tier, "")
    cat_e = CATALYST_EMOJI.get(ep.get("catalyst_quality", ""), "")
    # Rubric grade (the catalyst_quality the operator wants visible). Sanitize
    # the underscore so 'game_changer' can't break Markdown italics → 400 →
    # plaintext fallback (the parse-fragility class). cat_e keeps a quick visual.
    quality = (ep.get("catalyst_quality") or "?").replace("_", " ")
    # gemini_validation is a MISNOMER — it holds the Perplexity cross-check (#186A).
    gem = " ✓Pplx" if ep.get("gemini_validation") == ep.get("catalyst_quality") else ""
    conf = f" {ep['confidence_multiplier']:.1f}x" if ep.get("confidence_multiplier", 1.0) > 1.0 else ""
    # North Star C1: catalyst TYPE — the "fire" (Pradeep). ADVISORY, shown only
    # when classified. Marker via the shared _catalyst_type_mark helper.
    _ct = ep.get("catalyst_type")
    ct_suffix = f" {_catalyst_type_mark(_ct)}{_ct.replace('_', ' ')}" if _ct else ""
    # Volume display: prefer pre-market pm_rvol when session rel_volume reads ~0 (_resolve_ep_rvol).
    _rv_str, _rv_pm = _resolve_ep_rvol(ep)
    vol_str = f"pm rvol {_rv_str}" if _rv_pm else f"rv {_rv_str}"
    out: list[str] = []
    # Tier WORD on the line (not just the emoji) + a "catalyst" label on the grade, so HIGH (the
    # tier) and game-changer (the catalyst — already a scored COMPONENT of ep_score, not a rival
    # verdict) read as two facets of one call. Operator 6/25: the brief showed only "game changer"
    # per-name, so it looked like a competing classification vs the alert's "HIGH".
    if tier == "HIGH":
        out.append(
            f"{lead}{tier_e} *{tier}* `{ep['ticker']}` gap *{ep['gap_pct']:.1f}%* "
            f"{vol_str} "
            f"score *{ep['ep_score']:.0f}* {cat_e} {quality} catalyst{gem}{conf}{ct_suffix}"
        )
    else:
        out.append(
            f"{lead}{tier_e} {tier} `{ep['ticker']}` gap {ep['gap_pct']:.1f}%  "
            f"{vol_str}  score {ep['ep_score']:.0f} {cat_e} {quality} catalyst{ct_suffix}"
        )
    if ep.get("claude_analysis"):
        out.append(f"{lead}  _{_truncate_sentence(ep['claude_analysis'], 180)}_")
    return out


def format_ep_message(header: str, eps: list[dict]) -> str:
    """Assemble a full EP message: header + one shared block per ticker,
    blank-line separated. Single source for the HUD `/ep`, the `/eps_detail`
    drill-down, and any other full-list EP view so they can't drift."""
    blocks = ["\n".join(_format_ep_ticker_block(ep)) for ep in eps]
    return header + "\n\n" + "\n\n".join(blocks)


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
        # Shared per-ticker formatter (lead="  " preserves this section's nesting).
        lines.extend(_format_ep_ticker_block(ep, lead="  "))

    # Near-miss line — compact, one per line max 5, skip top-20-cap noise
    near_misses = [
        r for r in filtered
        if "top-20" not in (r.get("filter_reason") or "")
    ][:5]
    if near_misses:
        parts = []
        for r in near_misses:
            reason = r.get("filter_reason", "")
            # Shorten common reasons — keep full words, never cut mid-token
            if "price" in reason and "<" in reason:
                short = reason.split("—")[0].strip() if "—" in reason else reason
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
            elif reason.startswith("score ") and "catalyst=" in reason:
                # "score 48 < 50 (catalyst=speculative)" → "s48 cat=spec"
                import re as _re
                m = _re.match(r"score (\d+) < 50 \(catalyst=(\w+)\)", reason)
                short = f"s{m.group(1)} cat={m.group(2)[:4]}" if m else reason
            else:
                short = reason
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
    eco_map: dict[str, str] | None = None,
) -> str:
    """
    Theme RS Scorecard. With a theme→ecosystem mapping (#473, ADR 0032):
    compact ECOSYSTEM-grouped view — the same grouping/scoring seam as
    /themes (format_ecosystem_board), sized for the brief. Fail-safe: empty
    mapping / render error → the legacy stage-grouped scorecard below (the
    brief must never break on the ecosystem layer).
    """
    if not themes:
        return f"*{section_num}. THEME SCORECARD* — No data yet"

    scored_themes, fading = _compute_scored_themes(themes, theme_rs_data, prior_scores)

    if eco_map:
        try:
            # Function-level import — briefing must NOT import theme_ecosystems
            # at module scope (theme_ecosystems imports STAGE_EMOJI from here).
            from agents.market_intelligence.theme_ecosystems import (
                format_ecosystem_scorecard_compact,
            )
            body = format_ecosystem_scorecard_compact(
                scored_themes, fading, theme_rs_data, eco_map)
            if body:   # [] = nothing renderable (e.g. all unmapped) → legacy view
                header = (f"*{section_num}. THEME SCORECARD* — "
                          f"{len(scored_themes)} active · by ecosystem")
                return "\n".join([header] + body)
        except Exception as e:
            logger.warning(
                f"Ecosystem scorecard render failed — legacy stage view: {e}")

    # Legacy view — group by stage
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


def _format_recovery_section(recovery: list[dict], section_num: int = 5) -> str:
    """Fast V-recovery — strong 1M RS still climbing out of a weak base (the crypto-
    proxy case the RISING ≥40 floor deliberately hides). Empty -> omitted (#492)."""
    if not recovery:
        return ""
    lines = [f"*{section_num}. RECOVERY* — Strong 1M RS off a weak base (V-turn)"]
    for s in recovery[:10]:
        ticker = s.get("ticker", "?")
        r1 = s.get("rs_1m")
        r3 = s.get("rs_3m")
        rc = s.get("rs_composite")
        sec = s.get("sector") or ""
        r1s = int(r1) if r1 is not None else "?"
        r3s = int(r3) if r3 is not None else "?"
        rcs = int(rc) if rc is not None else "?"
        tail = f" — {sec}" if sec else ""
        lines.append(f"  `{ticker}` 1M {r1s} · 3M {r3s} · comp {rcs}{tail}")
    lines.append("  _1M RS leading a still-low composite = turning up from the bottom_")
    return "\n".join(lines)


def _format_crypto_pulse_section(pulse: dict) -> str:
    """CRYPTO vs MARKET — cross-asset strength (#493, slice 1 of the Market Strength Map #494):
    trailing 4wk/2wk return, crypto (BTC/ETH/SOL) vs the equity market (QQQ/SPY/IWM), with a
    one-line verdict answering 'is crypto holding up while the market corrects?'. Empty -> omitted."""
    if not pulse or not pulse.get("crypto"):
        return ""

    def _r(v):
        return f"{v:+.1f}" if v is not None else "n/a"

    verdict = pulse.get("verdict", "MIXED")
    emoji = {"LEADING": "🟢", "LAGGING": "🔴"}.get(verdict, "⚪")   # IN LINE / MIXED fall through to ⚪
    eth = next((a for a in pulse["crypto"] if a["sym"] == "ETH"), None)
    btc = next((a for a in pulse["crypto"] if a["sym"] == "BTC"), None)
    qqq = next((m for m in pulse["market"] if m["sym"] == "QQQ"), None)
    bits = [f"{a['sym']} {_r(a['r4'])}" for a in (eth, btc) if a and a.get("r4") is not None]
    tail = f" vs QQQ {_r(qqq['r4'])}" if qqq and qqq.get("r4") is not None else ""
    head = f"*CRYPTO vs MARKET* — {emoji} Crypto {verdict}"
    if bits:
        head += f" ({' / '.join(bits)}{tail}, 4wk)"
    lines = [head,
             "  crypto  " + "  ".join(f"`{a['sym']}` {_r(a['r4'])}/{_r(a['r2'])}" for a in pulse["crypto"]),
             "  market  " + "  ".join(f"`{m['sym']}` {_r(m['r4'])}/{_r(m['r2'])}" for m in pulse["market"]),
             "  _4wk/2wk trailing return_"]
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
        # warnings are free text and can carry snake_case ({step}/{metric}
        # fallbacks in data_quality.py) — one bare `_` flips the entity parity
        # of the WHOLE chunk (#477 class, 2026-07-16). _md_escape is the
        # canonical #148 escaper, defined below.
        lines.append(f"  {_md_escape(w)}")
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


def _format_ep_outcomes_section(outcomes: list[dict], section_num: int = 6) -> str:
    """
    Summary of today's EP alerts and their terminal states.

    outcomes: rows from get_ep_outcomes(days_back=1, ...) filtered to today.
    Shows HIGH breakdown (entered vs missed with skip-reason prefix) and a
    compact MODERATE tally. Omits the section entirely if no EPs today.
    """
    if not outcomes:
        return ""

    high = [o for o in outcomes if o.get("score_tier") == "HIGH"]
    moderate = [o for o in outcomes if o.get("score_tier") == "MODERATE"]

    if not high and not moderate:
        return ""

    entered_states = {"filled", "closed", "order_placed", "pending_confirmation", "confirmed", "submitting"}

    def _bucket(row: dict) -> str:
        st = row.get("trade_status")
        pt = row.get("pt_status")
        if st == "traded" and pt in entered_states:
            return "entered"
        if st == "filtered":
            return "missed"
        if st == "no_attempt":
            return "no_attempt"
        return "missed"

    lines = [f"*{section_num}. 📊 EP OUTCOMES TODAY*"]

    if high:
        entered = [o for o in high if _bucket(o) == "entered"]
        missed = [o for o in high if _bucket(o) != "entered"]
        lines.append(f"HIGH: {len(high)} detected → {len(entered)} entered · {len(missed)} missed")
        for o in entered[:5]:
            entry = o.get("last_entry_price")
            fwd = o.get("fwd_1d_pct")
            entry_str = f"@${float(entry):.2f}" if entry else "entered"
            fwd_str = f" {float(fwd):+.1f}%" if fwd is not None else ""
            lines.append(f"  • `{o['ticker']}` ({entry_str}{fwd_str})")
        from agents.market_intelligence.broker.skip_reasons import humanize
        for o in missed[:8]:
            label = humanize(o.get("skip_reason"))
            lines.append(f"  • `{o['ticker']}` — {label}")
        dropped = max(0, len(missed) - 8)
        if dropped:
            lines.append(f"  • …{dropped} more missed")

    if moderate:
        entered = [o for o in moderate if _bucket(o) == "entered"]
        lines.append(
            f"MODERATE: {len(moderate)} detected · {len(entered)} auto-entered (manual only)"
        )

    return "\n".join(lines)


# ── Evening briefing ───────────────────────────────────────────────────────────

_COOLDOWN_FOOTER_CAP = 3  # #479: was 8 → a long run-on line; top-3 highest-signal, rest via `show cooldowns`


def _format_cooldown_footer(cooldowns: list[dict]) -> str:
    """Compact cooldown footer: chronic (≥3 removals) + soonest-to-expire.
    `get_active_cooldowns()` already orders by removal_count DESC, cooldown_until ASC,
    so the top _COOLDOWN_FOOTER_CAP entries are the highest-signal ones. Overflow
    collapses to '+N more' — use `show cooldowns` for the full list.
    """
    if not cooldowns:
        return ""
    from datetime import datetime, timezone
    now = datetime.now(tz=timezone.utc)
    visible = cooldowns[:_COOLDOWN_FOOTER_CAP]
    overflow = len(cooldowns) - len(visible)
    parts = []
    for c in visible:
        days_left = max(0, (c["cooldown_until"] - now).days)
        chronic = " ⚠️" if c["removal_count"] >= 3 else ""
        parts.append(f"`{c['ticker']}` → {c['theme_name']} {days_left}d{chronic}")
    footer = "🧊 *Cooldowns:* " + "  •  ".join(parts)
    if overflow > 0:
        footer += f"  •  +{overflow} more (`show cooldowns`)"
    return footer


def _format_evening_briefing(
    regime: dict,
    rs_leaders: list[dict],
    themes: list[dict],
    velocity: list[dict],
    pullbacks: list[dict],
    turners: list[dict] | None = None,
    recovery: list[dict] | None = None,
    crypto_pulse: dict | None = None,
    briefing_date: str = "",
    fund_flags: dict[str, dict] | None = None,
    theme_rs_data: dict[str, dict] | None = None,
    prior_theme_scores: dict[str, float] | None = None,
    quality_warnings: list[str] | None = None,
    signal_quality_summary: dict | None = None,
    cooldowns: list[dict] | None = None,
    sugar_babies: list[dict] | None = None,
    ninem_anticipations: list[dict] | None = None,
    ep_outcomes: list[dict] | None = None,
    wick_today_count: int = 0,
    wick_today_tickers: list[str] | None = None,
    wick_fill_rate_30d: float | None = None,
    wick_settled_30d: int = 0,
    cohort_babies: list[dict] | None = None,
    undercut_rallies: list[dict] | None = None,
    v1_closeout_line: str | None = None,
    eco_map: dict[str, str] | None = None,
) -> str:
    # Theme section: use scorecard if RS data available, else legacy format
    if theme_rs_data:
        theme_section = _format_theme_scorecard(
            themes, theme_rs_data, prior_theme_scores or {}, section_num=3,
            eco_map=eco_map,
        )
    else:
        theme_section = _format_theme_section(themes, section_num=3)

    # #492 (operator 2026-07-20): RESTORE the RS-acceleration + rotation-recovery
    # signals — #479 ORPHANED them (built but never appended; the /watch-all
    # destination its comment named renders a different board). RISING (sustained
    # accel) + RECOVERY (fast 1M V-turn off a weak base — the crypto-proxy case the
    # velocity ≥40 floor deliberately hides) + ROTATION WATCH (sectors turning from
    # weak). Unanchored/pullbacks stay off the brief; the on-demand footer is dropped
    # (those commands were culled from the menu the same day).
    velocity_section = _format_velocity_section(velocity, section_num=4)
    recovery_section = _format_recovery_section(recovery or [], section_num=5)
    turners_section = _format_turners_section(turners or [], section_num=6)

    sections = [
        f"*Apollo Evening Briefing — {briefing_date}*",
        "",
    ]

    # v1.0 close-out countdown (#426, #418 §5) — the anti-idle driving surface.
    if v1_closeout_line:
        sections.append(v1_closeout_line)
        sections.append("")

    # Data quality warnings (prepended before section 1 if any)
    if quality_warnings:
        sections.append(_format_quality_warnings(quality_warnings))
        sections.append("")

    sections += [
        _format_regime_section(regime, section_num=1),
        "",
    ]
    # #493 slice-1 of the Market Strength Map: CRYPTO vs MARKET cross-asset pulse, placed
    # right under regime (it's a macro "where's the money" read that pairs with the regime).
    crypto_pulse_section = _format_crypto_pulse_section(crypto_pulse or {})
    if crypto_pulse_section:
        sections.append(crypto_pulse_section)
        sections.append("")
    sections += [
        _format_rs_section(rs_leaders[:10], section_num=2, fund_flags=fund_flags),  # top-10 (#479)
        "",
        theme_section,
        "",
    ]
    # RS acceleration / recovery / rotation — restored to the brief (#492).
    for _sec in (velocity_section, recovery_section, turners_section):
        if _sec:
            sections.append(_sec)
            sections.append("")

    cooldown_footer = _format_cooldown_footer(cooldowns or [])
    if cooldown_footer:
        sections.append(cooldown_footer)
        sections.append("")
    sections.append("_Do your review. Pull up charts. Apply your judgment._")
    return "\n".join(sections)


async def send_evening_briefing(chat_id: int | None = None) -> str:
    """
    Assemble and send the evening briefing (regime + RS + themes + velocity + pullbacks).
    Returns the briefing text.
    """
    today = _et_today()
    today_str = today.strftime("%Y-%m-%d")

    from agents.market_intelligence.db import get_active_cooldowns as _get_active_cooldowns

    regime, rs_leaders, themes, velocity, pullbacks, turners, recovery, crypto_pulse, fund_flags, prior_theme_scores, warnings, cooldowns = (
        await asyncio.gather(
            get_latest_regime(include_breadth_history=True),
            get_rs_leaders(today_str, limit=30),
            get_today_themes(today_str),
            get_rs_velocity(today_str, min_rs=40.0, limit=15),
            get_ma_pullbacks(today_str),
            get_rs_turners(today_str),
            get_rs_recovery(today_str),
            get_crypto_vs_market_pulse(),
            get_fundamental_flags(today_str),
            get_prior_theme_scores(today_str),
            get_quality_warnings(today),
            _get_active_cooldowns(),
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
    except Exception as e:
        # Advisory-only (briefing proceeds with stale/no overrides), but a
        # DB outage here should be visible, not invisible — #381.
        logger.warning(f"Ticker overrides refresh failed: {e}")

    # Collect all theme constituent tickers and fetch their RS data in one query
    all_theme_tickers = []
    for t in themes:
        all_theme_tickers.extend(t.get("tickers") or [])
    all_theme_tickers = list(set(all_theme_tickers))
    theme_rs_data = await get_rs_for_tickers(today_str, all_theme_tickers) if all_theme_tickers else {}

    # ADR 0032 (#473): theme → ecosystem mapping for the compact ecosystem
    # scorecard. Tonight's mappings are written by run_theme_engine (nightly
    # pull, 5 PM ET) before this job (8 PM ET); unmapped names degrade to the
    # ❔ footnote. load_ecosystem_assignments itself degrades to {} on any DB
    # failure → _format_theme_scorecard falls back to the legacy stage view.
    from agents.market_intelligence.theme_ecosystems import load_ecosystem_assignments
    eco_map = await load_ecosystem_assignments()

    # Weekly signal quality section (Fridays only: weekday 4)
    signal_quality_summary = None
    if today.weekday() == 4:
        try:
            from agents.market_intelligence.outcome_tracker import get_weekly_signal_summary
            signal_quality_summary = await get_weekly_signal_summary()
        except Exception as e:
            logger.warning(f"Signal quality summary failed: {e}")

    # 9M Sugar Babies — fetched separately to avoid disrupting the positional gather tuple
    sugar_babies: list[dict] = []
    try:
        from agents.market_intelligence.db import get_eod_9m_sugar_babies
        sugar_babies = await get_eod_9m_sugar_babies(today_str)
    except Exception as e:
        logger.warning(f"9M sugar babies fetch failed: {e}")

    # Persistent Sugar Babies cohort (Pradeep-class — ≥3 9M EOD prints / 180d)
    cohort_babies: list[dict] = []
    try:
        from agents.market_intelligence.db import get_sugar_babies_cohort_latest
        cohort_babies = await get_sugar_babies_cohort_latest(limit=10)
    except Exception as e:
        logger.warning(f"Sugar babies cohort fetch failed: {e}")

    # U&R (Undercut & Rally, #98) — today's detections for the quiet roundup
    # (separate fetch like sugar_babies to avoid disrupting the positional gather)
    undercut_rallies: list[dict] = []
    try:
        from agents.market_intelligence.db import get_undercut_rallies
        undercut_rallies = await get_undercut_rallies(today_str)
    except Exception as e:
        logger.warning(f"U&R fetch failed: {e}")

    # 9M anticipation-only alerts — surface silent pace-projected alerts so nothing goes unseen
    ninem_anticipations: list[dict] = []
    try:
        from agents.market_intelligence.db import get_today_9m_ep_alerts
        all_9m = await get_today_9m_ep_alerts(today_str)
        ninem_anticipations = [a for a in all_9m if a.get("is_anticipation")]
    except Exception as e:
        logger.warning(f"9M anticipation fetch failed: {e}")

    # EP outcomes for today — every HIGH detected should have a terminal state
    ep_outcomes: list[dict] = []
    try:
        from agents.market_intelligence.db import get_ep_outcomes
        all_outcomes = await get_ep_outcomes(days_back=1)
        ep_outcomes = [o for o in all_outcomes if str(o.get("alert_date")) == today_str]
    except Exception as e:
        logger.warning(f"EP outcomes fetch failed: {e}")

    # Wick Watch (P22) — today's count + 30d fill rate
    wick_today_count = 0
    wick_today_tickers: list[str] = []
    wick_fill_rate_30d: float | None = None
    wick_settled_30d = 0
    try:
        from agents.market_intelligence.db import get_wick_candidates_window
        wick_30d = await get_wick_candidates_window(30)
        today_rows = [r for r in wick_30d if str(r.get("alert_date")) == today_str]
        wick_today_count = len(today_rows)
        wick_today_tickers = [r["ticker"] for r in today_rows if r.get("ticker")]
        settled = [r for r in wick_30d if r.get("filled_wick") is not None]
        wick_settled_30d = len(settled)
        if settled:
            filled_n = sum(1 for r in settled if r["filled_wick"])
            wick_fill_rate_30d = filled_n / wick_settled_30d
    except Exception as e:
        logger.warning(f"Wick candidates fetch failed: {e}")

    # v1.0 close-out countdown (#426, #418 §5) — one line, computed from DB
    # ground truth. Guarded: a failure here must NEVER break the briefing.
    v1_closeout_line: str | None = None
    try:
        from scripts.v1_closeout_status import compute_and_render
        _pool = await get_pool()
        async with _pool.acquire() as _conn:
            v1_closeout_line = await compute_and_render(_conn, today=today)
    except Exception as e:
        logger.warning(f"v1.0 closeout status failed: {e}")

    text = _format_evening_briefing(
        regime=regime,
        rs_leaders=rs_leaders,
        themes=themes,
        velocity=velocity,
        pullbacks=pullbacks,
        turners=turners,
        recovery=recovery,
        crypto_pulse=crypto_pulse,
        briefing_date=today_str,
        fund_flags=fund_flags,
        theme_rs_data=theme_rs_data,
        prior_theme_scores=prior_theme_scores,
        quality_warnings=warnings,
        signal_quality_summary=signal_quality_summary,
        cooldowns=cooldowns,
        sugar_babies=sugar_babies,
        ninem_anticipations=ninem_anticipations,
        ep_outcomes=ep_outcomes,
        wick_today_count=wick_today_count,
        wick_today_tickers=wick_today_tickers,
        wick_fill_rate_30d=wick_fill_rate_30d,
        wick_settled_30d=wick_settled_30d,
        cohort_babies=cohort_babies,
        undercut_rallies=undercut_rallies,
        v1_closeout_line=v1_closeout_line,
        eco_map=eco_map,
    )

    success = await send_telegram_message(text, chat_id)
    if success:
        logger.info(f"Evening briefing sent for {today_str}")
        # #495: durable send-confirmation — so "did tonight's brief actually send?" is answerable
        # from the DB after a restart (the 2026-07-20 false-alarm gap: send success/failure was
        # log-only, so a same-day restart erased the only record).
        await log_audit_event("evening_brief_sent", f"evening brief sent for {today_str} ({len(text)} chars)",
                              f'{{"date": "{today_str}", "chars": {len(text)}}}')
    else:
        logger.error("Failed to send evening briefing")
        # #495: a silent brief-miss must not be invisible — durable audit row + a best-effort alert
        # (send_telegram_message already strips markup to plain on a 400, so a False return is a real
        # send failure, not a formatting one — worth flagging).
        await log_audit_event("evening_brief_send_failed", f"evening brief FAILED to send for {today_str}",
                              f'{{"date": "{today_str}"}}')
        try:
            await send_telegram_message(f"⚠️ Evening brief FAILED to send for {today_str} — it did not reach you; check logs.")
        except Exception:  # loud-ok: the alert is best-effort; the evening_brief_send_failed audit row is durable
            pass

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
    rs = ep.get("rs_composite")
    if rs is None:
        # NULL indicates the ticker dropped from the RS universe (delisted,
        # sub-$10, non-CS) between scoring and EP detection. Log as a
        # universe-drift signal and use a neutral bonus so we neither promote
        # nor bury the alert purely because of the missing score.
        logger.warning(
            "EP alert with no RS score — universe drift: ticker=%s alert_date=%s",
            ep.get("ticker"), ep.get("alert_date"),
        )
        rs_bonus = 5.0
    else:
        rs_bonus = min(rs / 10, 10)
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
        # Cap at 2 bullets — the prompt asks for ≤2 sentences; this is the safety net
        # that stops a non-compliant Perplexity essay from becoming a wall of text
        # (2026-06-08: "no catalyst" days produced 6 bullets enumerating non-events).
        sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(news) if s.strip()]
        for s in sentences[:2]:
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
        f"List up to 5 key scheduled US economic events, data releases, or Fed speeches for {day_str}. "
        f"Format EACH on one line as '<time> ET — <event name>', e.g. '8:30 AM ET — Initial Jobless "
        f"Claims'. EVERY line MUST contain the event NAME — never output a time with no event. "
        f"Give all times in US Eastern Time (convert any UTC/GMT to ET; NEVER output UTC/GMT). No preamble."
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

        # A line that is ONLY a time (no event name) is content-less — drop it. Guards the
        # 2026-06-18 "bare-times" regression: better to show fewer/no items than meaningless
        # times. Iterate all lines (not [:5]) so dropped bare-time lines don't starve the cap.
        time_only = re.compile(r"^\d{1,2}:\d{2}\s*(?:AM|PM)?\s*ET\b[\s—\-–:.]*$", re.IGNORECASE)
        bullets = []
        for line in raw_lines:
            # Strip leading numbering (1. 2. etc) or bullet chars
            line = re.sub(r"^[\d]+[.)]\s*", "", line)
            line = re.sub(r"^[-•]\s*", "", line).strip()
            if not line or time_only.match(line):
                continue
            bullets.append(f"• {line}")
            if len(bullets) >= 5:
                break
        return "\n".join(bullets) if bullets else None
    except Exception as e:
        logger.warning(f"Economic calendar fetch failed: {e}")
        return None


# ── Fix-2b (2026-07-14) — already-printed scheduled-release signal ────────────
# 2026-07 miss: CPI printed 8:30 AM ET and moved the market, but a Perplexity
# timeout blanked the overnight summary → the brief said "no clear catalyst"
# WHILE its own CALENDAR section showed "8:30 AM ET — CPI". The calendar is
# already-fetched data; this derives a deterministic "this release ALREADY
# printed today" driver signal from it, independent of Perplexity health. It is
# (a) threaded into the overnight-news prompt as context and (b) appended to
# the OVERNIGHT section as a determined-from-data line even when Perplexity
# fully degrades. Happy path with no printed high-impact release: no-op.

# "8:30 AM ET" — the exact shape _get_economic_calendar prompts Perplexity for.
_CAL_TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\s*(AM|PM)\s*ET\b", re.IGNORECASE)

# High-impact scheduled US releases/events that plausibly move the whole tape.
# Deliberately curated — a minor weekly print shouldn't add a driver line.
_HIGH_IMPACT_RELEASE_RE = re.compile(
    r"\b(cpi|ppi|pce|fomc|gdp|nonfarm|non-farm|payrolls?|jobs report"
    r"|unemployment rate|jobless claims|retail sales|ism|jolts"
    r"|consumer (?:price|confidence|sentiment)|producer price|michigan"
    r"|rate decision|fed (?:funds|chair|minutes|rate)|powell)\b",
    re.IGNORECASE,
)


def _already_printed_releases(
    econ_calendar: str | None, now_et: datetime | None = None,
) -> list[str]:
    """From the brief's economic-calendar text, return the HIGH-IMPACT lines
    whose ET release time is already in the past (i.e. the data has PRINTED
    before the brief went out). Lines without a parseable '<H>:<MM> AM/PM ET'
    time or without a high-impact keyword are skipped (conservative). Capped
    at 3 lines to keep the brief tight."""
    if not econ_calendar:
        return []
    now_et = now_et or datetime.now(_ET)
    printed: list[str] = []
    for raw in econ_calendar.split("\n"):
        line = raw.lstrip("•").strip()
        if not line:
            continue
        m = _CAL_TIME_RE.search(line)
        if not m or not _HIGH_IMPACT_RELEASE_RE.search(line):
            continue
        hour, minute, ampm = int(m.group(1)), int(m.group(2)), m.group(3).upper()
        if not (1 <= hour <= 12 and 0 <= minute <= 59):
            continue
        hour24 = (hour % 12) + (12 if ampm == "PM" else 0)
        release_dt = now_et.replace(hour=hour24, minute=minute, second=0, microsecond=0)
        if release_dt <= now_et:
            printed.append(line)
        if len(printed) >= 3:
            break
    return printed


def _append_printed_release_line(
    overnight_section: str | None, printed_releases: list[str],
) -> str | None:
    """Append the determined-from-data 'already printed' driver line to the
    OVERNIGHT section — creating the section when Perplexity degradation left
    it empty. No printed releases → section returned unchanged (happy path)."""
    if not printed_releases:
        return overnight_section
    release_line = ("  📊 _Data printed: " + "; ".join(printed_releases)
                    + " — likely market driver._")
    if overnight_section:
        return overnight_section + "\n" + release_line
    return "*OVERNIGHT*\n" + release_line


async def _get_overnight_news(
    snapshot: list[dict] | None = None,
    printed_releases: list[str] | None = None,
) -> str | None:
    """
    Query Perplexity for overnight market news.
    If snapshot has triggered movers, asks about specific moves.
    Otherwise asks for general pre-market headlines.
    printed_releases (Fix-2b): scheduled releases that already printed today —
    threaded into the query so the LLM weighs them as candidate drivers.
    Returns concise news string or None.
    """
    triggered = [i for i in (snapshot or []) if i.get("triggered")]

    release_note = ""
    if printed_releases:
        release_note = (
            " Note: the following scheduled US economic releases have ALREADY "
            "printed today, before this brief: " + "; ".join(printed_releases)
            + ". Weigh them as candidate drivers of the market move."
        )

    if triggered:
        # Build a contextual query based on what moved
        movers = []
        for item in triggered:
            sign = "up" if item["pct_change"] > 0 else "down"
            movers.append(f"{item['name']} {sign} {abs(item['pct_change']):.1f}%")
        movers_str = ", ".join(movers)
        query = (
            f"In one or two sentences, what is the most likely driver of today's move "
            f"({movers_str})? If there is no single fresh news catalyst, say so plainly and "
            f"state whether it looks like a technical bounce / reversion from the prior "
            f"session, plus the single most relevant macro or geopolitical headline if one "
            f"exists. Be concise — do not list everything that did not happen."
            f"{release_note}"
        )
    else:
        today = _et_today()
        day_str = today.strftime("%A, %B %d, %Y")
        query = (
            f"What are the top US stock market headlines for {day_str}? "
            f"Focus on overnight developments, earnings, macro events, geopolitical news "
            f"that will affect today's trading session. Be specific and direct."
            f"{release_note}"
        )

    _OVERNIGHT_SYSTEM = (
        "You are a terse market-desk analyst writing ONE line for a trader's morning brief. "
        "Answer in AT MOST 2 short sentences (≤40 words total). State the single most likely "
        "driver of the move. "
        "A technical bounce or mean-reversion after the prior session's move IS a complete, "
        "valid answer — say it plainly (e.g. 'Bounce after Friday's selloff; no fresh catalyst'). "
        "If a real macro/geopolitical headline is relevant, name it in a few words (the person, "
        "policy, or event). "
        "HARD RULES — do NOT break these: "
        "Do NOT enumerate what did NOT happen (no lists of absent Fed/CPI/data/ceasefire items). "
        "Do NOT speculate about dealer flows, options positioning, or generic 'ongoing AI/tech "
        "optimism' unless that is the specific, sourced reason. "
        "Do NOT give advice on communicating to clients. "
        "No citation numbers. Do NOT restate index prices or percentages — the reader sees those. "
        "Only use news from the last 24 hours; if there is none, the one-line technical read is "
        "the correct and complete answer — do not pad it."
    )

    from agents.market_intelligence.theme_engine import _is_garbage
    answer = await search_news_perplexity(query, recency="day", system_prompt=_OVERNIGHT_SYSTEM)
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
    overnight_errors: list[dict] | None = None,
    wick_pending: list[dict] | None = None,
    tinycap_observed: list[dict] | None = None,
    theme_merges: list[dict] | None = None,
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

    # Class B (#271): pre-open breadth-extreme flag — only when amber/green (suppress neutral
    # so the morning brief stays tight). The exhaustion/washout read is pre-open-useful.
    from agents.market_intelligence.breadth_color_rules import (
        coerce_breadth_monitor, class_b_color, CAUTION, BULL,
    )
    _bm = coerce_breadth_monitor(regime.get("breadth_monitor"))
    _b = class_b_color(_bm.get("up_20_5d_pct"), _bm.get("down_20_5d_pct"))
    if _b == CAUTION:
        sections.append(f"{CAUTION} *Breadth*: 5d up-thrust extreme ({_bm.get('up_20_5d_pct')}%) — exhaustion watch")
    elif _b == BULL:
        sections.append(f"{BULL} *Breadth*: 5d washout extreme ({_bm.get('down_20_5d_pct')}%) — oversold / rally-watch")

    # Engine errors from overnight run — shown prominently so nothing is missed
    if overnight_errors:
        # Bucket into rate-limited / transient API / parse / other so a flood
        # of one category (e.g. Anthropic 5xx burst) collapses to a single line.
        rate_limited_types  = {"validation_rate_limited", "anthropic_rate_limited",
                                "assignment_rate_limited", "discovery_rate_limited"}
        api_failure_types   = {"validation_api_failure", "assignment_api_failure",
                                "discovery_api_failure"}
        parse_error_types   = {"validation_error"}
        # Fix-1 (2026-07-14): data/broker-API failure rows (api_failure_<provider>)
        # whose class is TRANSIENT/self-healing (timeout / connect / transport /
        # per-symbol 402) no longer Telegram at failure time — here in the brief
        # they collapse to ONE quiet 🔵 line instead of per-row 🔴 entries.
        # ACTIONABLE api_failure rows (auth 401/403, 5xx, sustained escalations)
        # keep the loud 🔴 treatment via other_errs below.
        from agents.market_intelligence.llm_health import is_transient_api_failure_row

        def _is_quiet_api_row(r: dict) -> bool:
            return (str(r.get("event_type") or "").startswith("api_failure_")
                    and is_transient_api_failure_row(r))

        rate_limited = [r for r in overnight_errors if r.get("event_type") in rate_limited_types]
        api_failures = [r for r in overnight_errors if r.get("event_type") in api_failure_types]
        validation_errs = [r for r in overnight_errors if r.get("event_type") in parse_error_types]
        transient_api_rows = [r for r in overnight_errors if _is_quiet_api_row(r)]
        other_errs = [r for r in overnight_errors if r.get("event_type") not in
                      (rate_limited_types | api_failure_types | parse_error_types)
                      and not _is_quiet_api_row(r)]
        err_lines = [f"⚠️ *{len(overnight_errors)} engine event(s) overnight* — type 'show errors' for detail"]
        if rate_limited:
            err_lines.append(
                f"  🟠 {len(rate_limited)} Anthropic rate-limited call(s) — tickers unchanged"
            )
        if api_failures:
            err_lines.append(
                f"  🔵 {len(api_failures)} transient Anthropic API failure(s) "
                f"— will retry next run"
            )
        if validation_errs:
            err_lines.append(
                f"  🟡 {len(validation_errs)} theme validation parse error(s) "
                f"— tickers unchanged"
            )
        if transient_api_rows:
            err_lines.append(
                f"  🔵 {len(transient_api_rows)} transient data-API blip(s) "
                f"(timeout/connect/per-symbol 4xx) — self-healing, audit-only"
            )
        for r in other_errs[:3]:
            err_lines.append(f"  🔴 {r['summary']}")
        if len(other_errs) > 3:
            err_lines.append(f"  ... and {len(other_errs) - 3} more")
        sections.append("\n".join(err_lines))

    # Data quality warnings
    if quality_warnings:
        sections.append(_format_quality_warnings(quality_warnings))

    # ADR 0025 Arm B rail (#274): every overnight thesis merge surfaces here.
    # Empty (and absent) unless THEME_MERGE_ARM executed merges overnight.
    if theme_merges:
        merge_lines = [f"🔀 *{len(theme_merges)} theme merge(s) overnight* — thesis-coherence arm"]
        for r in theme_merges[:3]:
            merge_lines.append(f"  • {r.get('summary', '')}")
        if len(theme_merges) > 3:
            merge_lines.append(f"  … and {len(theme_merges) - 3} more")
        sections.append("\n".join(merge_lines))

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
    ]

    # Wick Pending — forward-looking wick fills (prior_high not yet broken,
    # 5:45 PM sweep hasn't closed the row). Actionable for today's session.
    if wick_pending:
        wp_lines = [f"🪝 *Wick Pending* ({len(wick_pending)}) — break-of-prior-high candidates"]
        for r in wick_pending[:5]:
            d = r.get("alert_date")
            ds = d.strftime("%b %d") if hasattr(d, "strftime") else str(d)
            prior_high = float(r.get("prior_high") or 0)
            wp_lines.append(f"  • *{r['ticker']}* — {ds}: break > ${prior_high:.2f}")
        if len(wick_pending) > 5:
            wp_lines.append(f"  …{len(wick_pending) - 5} more")
        sections += ["", "\n".join(wp_lines)]

    # Tiny-cap observe lane (operator-approved 2026-06-11, the MNTS $74M case):
    # movers that passed every gap/RVOL gate but sit under the $500M auto-trade
    # floor. Eyes-only — the fast-runner class where one pays for ten losers.
    if tinycap_observed:
        tc_lines = [f"🔬 *Tiny-cap movers* ({len(tinycap_observed)}) — observe-only, auto-trade excluded"]
        for t in sorted(tinycap_observed, key=lambda x: -(x.get("gap_pct") or 0))[:6]:
            gap = float(t.get("gap_pct") or 0)
            # skip_reason tail carries the cap: "filter:mcap_too_small: $74M < $500M"
            cap = (t.get("skip_reason") or "").rsplit(":", 1)[-1].strip()
            tc_lines.append(f"  • *{t.get('ticker')}* +{gap:.0f}%  ({cap})")
        if len(tinycap_observed) > 6:
            tc_lines.append(f"  …{len(tinycap_observed) - 6} more")
        sections += ["", "\n".join(tc_lines)]

    sections += [
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

    from agents.market_intelligence.db import get_audit_log as _get_audit_log
    regime, ep_alerts, premarket, themes, watchlist, warnings, fund_flags, ep_scan_log, overnight_err_rows, overnight_api_rows, overnight_rate_rows, theme_merge_rows = await asyncio.gather(
        get_latest_regime(),
        get_today_ep_alerts(today_str),
        get_premarket_snapshot(),
        get_today_themes(today_str),
        get_overnight_watchlist(),
        get_quality_warnings(today),
        get_fundamental_flags(today_str),
        get_ep_scan_log(today_str),
        _get_audit_log(limit=10, event_type_like="%error%", since_hours=18),
        _get_audit_log(limit=10, event_type_like="%api_failure%", since_hours=18),
        _get_audit_log(limit=10, event_type_like="%rate_limited%", since_hours=18),
        # ADR 0025 Arm B rail: overnight thesis merges → info banner. Rows only
        # exist when THEME_MERGE_ARM is on and merges executed; empty otherwise.
        _get_audit_log(limit=6, event_type="theme_thesis_merged", since_hours=18),
    )
    # Merge + dedup by id — pattern overlap (e.g. validation_error matches both
    # %error%) won't double-count.
    seen: set = set()
    overnight_errors: list[dict] = []
    for r in (overnight_err_rows or []) + (overnight_api_rows or []) + (overnight_rate_rows or []):
        rid = r.get("id")
        if rid is not None and rid in seen:
            continue
        if rid is not None:
            seen.add(rid)
        overnight_errors.append(r)
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

    # Fix-2b: deterministic already-printed-release driver signal, derived from
    # the calendar we ALREADY have — independent of Perplexity health.
    printed_releases = _already_printed_releases(econ_calendar)

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
        news = await _get_overnight_news(snapshot or None, printed_releases=printed_releases)
        cache["overnight_news"] = news
        logger.info(f"Morning briefing: overnight news={'yes' if news else 'none'} ({len(news) if news else 0} chars)")

    if snapshot:
        overnight_section = _format_overnight_section(snapshot, news)
    elif news:
        # No watchlist/snapshot, but we have news — show it standalone
        lines = ["*OVERNIGHT*"]
        # Cap at 2 bullets — the prompt asks for ≤2 sentences; this is the safety net
        # that stops a non-compliant Perplexity essay from becoming a wall of text
        # (2026-06-08: "no catalyst" days produced 6 bullets enumerating non-events).
        sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(news) if s.strip()]
        for s in sentences[:2]:
            lines.append(f"  • _{s}_")
        overnight_section = "\n".join(lines)

    # Fix-2b: determined-from-data driver line — survives Perplexity degrading
    # (creates the OVERNIGHT section if the news/snapshot paths produced none).
    overnight_section = _append_printed_release_line(overnight_section, printed_releases)

    # Store cache for this day
    _perplexity_cache.clear()
    _perplexity_cache[today_str] = cache

    # Wick Pending — forward-looking wicks not yet filled, sweep hasn't closed
    # them yet. Sibling of evening Wick Watch (settled outcomes).
    wick_pending: list[dict] = []
    try:
        from agents.market_intelligence.db import get_wick_pending_candidates
        from agents.market_intelligence.strategies.registry import should_run as _should_run
        if await _should_run("wick_fill"):
            wick_pending = await get_wick_pending_candidates(lookback_sessions=3)
    except Exception as e:
        logger.warning(f"Wick pending fetch failed: {e}")

    # Tiny-cap observe lane (operator-approved 2026-06-11, MNTS case): movers
    # the $500M floor excluded from auto-trading, surfaced for eyes-only.
    tinycap_observed: list[dict] = []
    try:
        import json as _json
        from agents.market_intelligence.db import get_pool as _gp
        _pool = await _gp()
        async with _pool.acquire() as conn:
            _tc = await conn.fetch("""
                SELECT DISTINCT ON ((detail::jsonb)->>'ticker') detail
                FROM mi_audit_log
                WHERE event_type = 'ep_tinycap_observed' AND created_at > current_date
                ORDER BY (detail::jsonb)->>'ticker', created_at DESC
            """)
        tinycap_observed = [_json.loads(r["detail"]) for r in _tc]
    except Exception as e:
        logger.warning(f"tinycap observe fetch failed: {e}")

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
        overnight_errors=overnight_errors,
        wick_pending=wick_pending,
        tinycap_observed=tinycap_observed,
        theme_merges=theme_merge_rows,
    )

    success = await send_telegram_message(text, chat_id)
    if success:
        logger.info(f"Morning briefing sent for {today_str}")
    else:
        logger.error("Failed to send morning briefing")

    return text


# ── Telegram delivery ──────────────────────────────────────────────────────────

def _md_escape(s: str) -> str:
    """Escape Telegram Markdown V1 control chars (`_`, `*`) in dynamic content.

    Filed as #148, 2026-05-28: the downgrade digest's reason strings
    (e.g. `news_corpus_sparse_no_q_rev`) and `from_quality` values
    (e.g. `game_changer`) contain `_` which Markdown V1 reads as italic
    delimiters. Unbalanced `_` count → Telegram 400. send_telegram_message
    has a plain-text fallback but the cosmetic gap is visible.

    Backticks deliberately NOT escaped — code spans are useful and
    they're already escaped at template time when present.

    Re-homed off scheduler.py into briefing.py (#121, 2026-06-23): a scheduler
    shouldn't own message formatting, and this lives beside send_telegram_message
    and its Markdown-V1 sibling _strip_markdown_markers. Behavior unchanged.
    """
    if not s:
        return ""
    return s.replace("_", r"\_").replace("*", r"\*")


# Machine reason → human prose map (#143/#148 2026-05-28). Used by the
# downgrade digest so operator-facing lines read as English instead of
# `rubric_composite_11.0_below_22_label_weak`.
_DOWNGRADE_REASON_STATIC = {
    "q_rev_yoy_missing_no_prior_year_comparable": "Q-rev YoY missing (no prior-year comparable)",
    "news_corpus_sparse_no_q_rev": "news corpus sparse, no Q-rev data",
    "extraction_quality_low": "catalyst extraction confidence low",
}

_DOWNGRADE_REASON_RUBRIC_RE = re.compile(
    r"^rubric_composite_(?P<score>[\d.]+)_below_(?P<thresh>\d+)_label_(?P<label>\w+)$"
)


def _humanize_downgrade_reason(reason: str) -> str:
    """Convert machine reason code to operator-facing prose.

    Examples:
    - `rubric_composite_11.0_below_22_label_weak` → `rubric 11/39 below 22 floor (weak)`
    - `q_rev_yoy_missing_no_prior_year_comparable` → `Q-rev YoY missing (no prior-year comparable)`
    - unrecognized → reason verbatim with underscores spaced

    Re-homed off scheduler.py (#121, 2026-06-23); behavior unchanged.
    """
    if not reason:
        return ""
    if reason in _DOWNGRADE_REASON_STATIC:
        return _DOWNGRADE_REASON_STATIC[reason]
    m = _DOWNGRADE_REASON_RUBRIC_RE.match(reason)
    if m:
        score = m.group("score").rstrip("0").rstrip(".") or m.group("score")
        return f"rubric {score}/39 below {m.group('thresh')} floor ({m.group('label')})"
    # Fallback: replace underscores with spaces so the raw reason is at
    # least readable, even if we don't have a templated translation.
    return reason.replace("_", " ")


def _build_judge_delta_message(rows, authority_on: bool, date_str: str) -> str:
    """Pure formatter for the judge-delta digest (testable without a DB). `rows`
    are mi_ep_alerts rows (promote/demote, judge_tier non-null) already ordered
    promotes-first. The subtitle reflects whether the deltas were load-bearing.

    Re-homed off scheduler.py (#121, 2026-06-23); behavior unchanged.
    """
    n_promote = sum(1 for r in rows if r["judge_direction"] == "promote")
    n_demote = len(rows) - n_promote
    subtitle = ("_Load-bearing: these DROVE the paper grade/entry._" if authority_on
                else "_Shadow: judge vs floor grade · drives nothing while toggle OFF._")
    parts = [
        f"🧑‍⚖️ *EP Judge deltas — EOD {date_str} (▲{n_promote} ▼{n_demote})*",
        subtitle,
    ]
    from agents.market_intelligence.ep_grade_judge import format_tier_transition
    # Row cap 12 × ~330 chars stays under Telegram's 4096 even on a heavy day.
    for r in rows[:12]:
        arrow = "▲" if r["judge_direction"] == "promote" else "▼"
        mat = r["judge_materiality_tier"] or "n/a"
        tier_part = format_tier_transition(r["baseline_floor_tier"], r["judge_tier"])
        parts.append(
            f"{arrow} `{r['ticker']}` {tier_part}  "
            f"materiality={mat}  +{(r['gap_pct'] or 0):.1f}%"
        )
        if r["judge_rationale"]:
            # Free-text judge rationale → escape Markdown actives (#148 class) so a
            # stray _/* in the prose doesn't break the legacy-Markdown parse.
            # Truncate at a WORD boundary with an ellipsis (operator 6/12: a hard
            # slice cut the AKTS rationale mid-word with no signal it was cut).
            rationale = r["judge_rationale"]
            if len(rationale) > 280:
                rationale = rationale[:280].rsplit(" ", 1)[0] + " …"
            parts.append(f"   _{_md_escape(rationale)}_")
    if len(rows) > 12:
        parts.append(f"…+{len(rows) - 12} more — full list: /audit judge")
    return "\n".join(parts)


def _strip_markdown_markers(text: str) -> str:
    """Strip Telegram-Markdown control chars so a parse-failure plain-text
    fallback doesn't show literal *Foo* / _bar_ / `code` to the user.

    Preserves the content INSIDE markers (drops only the markers themselves).
    Triple-backtick code blocks are kept as-is (the content inside is
    typically tabular/monospace data the user wants verbatim — we drop the
    fences but leave the body).
    """
    import re as _re
    # Drop triple-backtick fences (keep body)
    text = _re.sub(r"```[a-zA-Z]*\n?", "", text)
    text = text.replace("```", "")
    # Drop inline `code` markers (keep body)
    text = _re.sub(r"`([^`]+)`", r"\1", text)
    # Drop bold/italic markers (keep body). Use a regex so we only strip
    # what looks like paired markers — avoid stripping a stray * or _ inside
    # a word like "/foo_bar_baz".
    text = _re.sub(r"\*(?=\S)([^*\n]*?)(?<=\S)\*", r"\1", text)
    text = _re.sub(r"_(?=\S)([^_\n]*?)(?<=\S)_", r"\1", text)
    return text


async def send_telegram_message(
    text: str, chat_id: int | None = None, parse_mode: str = "Markdown"
) -> bool:
    """Send a message directly via Telegram Bot API. Splits if over 4000 chars.

    parse_mode defaults to legacy "Markdown" (every existing caller). Pass
    parse_mode="HTML" for surfaces migrated to the shared HTML layer
    (shared/telegram_format, #121) — HTML has a total escape so dynamic values
    can't break the parse. On a 400 the message still lands as plain text (markup
    stripped for the active mode)."""
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

    def _to_plain(chunk: str) -> str:
        # Plain-text fallback strips the active mode's markup so users don't see
        # literal *Foo*/_bar_ (Markdown) or <b> tags (HTML) all over the message.
        # Caught 2026-05-25: 400 ("Can't find end of entity") fell back to plain
        # text without stripping the markers.
        if parse_mode == "HTML":
            import re as _re
            import html as _html
            # Strip tags, then unescape ALL entities (html.unescape covers &quot;,
            # numeric refs, etc — the manual 3-entity replace missed those).
            return _html.unescape(_re.sub(r"<[^>]+>", "", chunk))
        return _strip_markdown_markers(chunk)

    async def _post(client: httpx.AsyncClient, chunk: str, formatted: bool) -> httpx.Response:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": chunk if formatted else _to_plain(chunk),
            "disable_web_page_preview": True,
        }
        if formatted:
            payload["parse_mode"] = parse_mode
        return await client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage", json=payload
        )

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            for chunk in chunks:
                r = await _post(client, chunk, formatted=True)
                if r.status_code == 400:
                    # Likely malformed markup — retry as plain text so the alert
                    # still lands. Parse failures otherwise vanish silently.
                    body = r.text[:500]
                    # Telegram's error names a "byte offset" for the entity opener
                    # it couldn't close. Its API entity offsets are UTF-16 units
                    # (see scripts/probes/_diag_brief_markdown.py) while the error
                    # string reads as UTF-8 bytes — and the two diverge by 2-3
                    # bytes per emoji, so on an emoji-heavy brief a single-
                    # interpretation window can miss the culprit entirely. Log the
                    # window under BOTH interpretations so the audit row always
                    # pinpoints it (2026-07-16: an evening-brief break at byte
                    # 4205 was undiagnosable from chunk[:300] alone).
                    snippet = ""
                    _m = re.search(r"byte offset (\d+)", body)
                    if _m:
                        _off = int(_m.group(1))
                        _u8 = chunk.encode("utf-8")[
                            max(0, _off - 120):_off + 80].decode(
                            "utf-8", errors="replace")
                        _u16 = chunk.encode("utf-16-le")[
                            max(0, (_off - 120) * 2):(_off + 80) * 2].decode(
                            "utf-16-le", errors="replace")
                        snippet = f"u8⟨{_u8}⟩ u16⟨{_u16}⟩"
                    logger.warning(
                        f"Telegram 400 with {parse_mode} — retrying plain text. "
                        f"body={body} offset_snippet={snippet!r}"
                    )
                    r2 = await _post(client, chunk, formatted=False)
                    if r2.status_code >= 400:
                        await log_audit_event(
                            "telegram_send_failed",
                            "Telegram send failed after plain-text retry",
                            f"md_body={body} | plain_status={r2.status_code} | plain_body={r2.text[:400]} | offset_snippet={snippet!r} | chunk={chunk[:300]}",
                        )
                        r2.raise_for_status()
                    else:
                        await log_audit_event(
                            "telegram_markdown_fallback",
                            "Markdown parse failed — delivered as plain text",
                            f"md_body={body} | offset_snippet={snippet!r} | chunk={chunk[:300]}",
                        )
                else:
                    r.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        try:
            await log_audit_event(
                "telegram_send_failed",
                "Telegram send exception",
                f"{type(e).__name__}: {e} | chat={chat_id} | first_chunk={chunks[0][:300] if chunks else ''}",
            )
        except Exception:  # loud-ok: fallback-of-the-fallback — the primary
            pass          # failure is already logger.error'd above; the audit
                          # layer may share the same outage (e.g. DB down).
        return False


async def send_telegram_photo(
    photo_bytes: bytes, caption: str = "", chat_id: int | None = None,
    filename: str = "chart.png",
) -> bool:
    """Send a PNG inline via Telegram sendPhoto. Same token/chat-id resolution as
    send_telegram_message; returns False on any failure, never raises. Used by the #343 chart-axis
    weekly digest so the operator labels a delta seeing the SAME chart the judge saw (a path alone
    is unlabelable). Caption is capped at Telegram's 1024-char sendPhoto limit."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not chat_id:
        ids = [x.strip() for x in os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if x.strip()]
        if not ids:
            logger.error("No TELEGRAM_ALLOWED_USER_IDS configured for photo delivery")
            return False
        chat_id = int(ids[0])
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return False
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendPhoto",
                data={"chat_id": str(chat_id), "caption": caption[:1024]},
                files={"photo": (filename, photo_bytes, "image/png")},
            )
            r.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Telegram photo send failed: {e}")
        return False


async def edit_telegram_message(
    chat_id: int, message_id: int, text: str, parse_mode: str = "Markdown"
) -> bool:
    """Edit an existing Telegram message in-place. Returns False if the message was deleted."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{bot_token}/editMessageText",
                json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": text[:4096],
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True,
                },
            )
            # "Message is not modified" means content identical — not an error
            if r.status_code == 400 and "not modified" in r.text.lower():
                return True
            r.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Telegram edit failed (chat={chat_id} msg={message_id}): {e}")
        return False


_TIER_RANK = TIER_RANK  # SSoT: constants.TIER_RANK (ADR 0024 §3 lattice)


def _judge_direction(score_tier, floor_tier) -> "str | None":
    """promote / hold / demote of the judge's authoritative tier vs the floor tier (None if
    either is unknown). The judge is load-bearing (#249), so this reconstructs the direction the
    delta-digest persists, but from the in-memory alert dict (judge_direction isn't on it)."""
    a, b = _TIER_RANK.get(score_tier), _TIER_RANK.get(floor_tier)
    if a is None or b is None:
        return None
    return "promote" if a > b else ("demote" if a < b else "hold")


def _judge_authoritative(ep: dict) -> bool:
    """The judge's tier is load-bearing for this alert (grade_engine_authority='judge'). Extracted
    from three briefing helpers that shared the bare predicate (#338-F). NOT the same as the
    compound scheduler check (judge AND HIGH) or agent.py's truthy-existence check — those stay."""
    return ep.get("grade_engine_authority") == "judge"


def resolve_headline_grade(ep: dict) -> tuple:
    """(emoji, label) for the alert's ticker line. RESOLVES TO THE JUDGE when the judge is
    load-bearing (grade_engine_authority='judge') — so a judge-promoted HIGH never headlines the
    contradicted floor grade (LZB: floor 'routine' under a judge HIGH). Floor/fallback authority →
    the Claude catalyst grade, as before."""
    if _judge_authoritative(ep):
        d = _judge_direction(ep.get("score_tier"), ep.get("baseline_floor_tier"))
        dtxt = f" ({d})" if d else ""
        return TIER_EMOJI.get(ep.get("score_tier", ""), ""), f"Judge: {ep.get('score_tier')}{dtxt}"
    cq = (ep.get("catalyst_quality") or "").replace("_", " ").title()
    return CATALYST_EMOJI.get(ep.get("catalyst_quality", ""), ""), cq


def format_grade_provenance(ep: dict) -> str:
    """ONE coherent line showing HOW the grade was reached — the operator-requested clarity on
    where Perplexity comes in. Floor catalyst grade (Claude) · Perplexity's independent
    second-opinion grade (agree/differs — a cross-check on the floor, NOT a judge input) · the
    judge's authoritative tier verdict when load-bearing. Replaces the old confidence-multiplier
    'Claude + Perplexity agree' line, which went STALE when a catalyst was downgraded AFTER the
    agreement boost was set (LZB 6/17: printed 'agree' on routine-vs-strong)."""
    cq = (ep.get("catalyst_quality") or "").replace("_", " ")
    parts = [f"Floor: {cq or 'n/a'} (Claude)"]
    pplx = (ep.get("gemini_validation") or "").replace("_", " ")
    if pplx:
        agree = "✓agree" if ep.get("gemini_validation") == ep.get("catalyst_quality") else "✗differs"
        parts.append(f"Perplexity: {pplx} ({agree})")
    if _judge_authoritative(ep):
        d = _judge_direction(ep.get("score_tier"), ep.get("baseline_floor_tier"))
        parts.append(f"*Judge: {ep.get('score_tier')}{f' {d}' if d else ''}* ← authoritative")
    return "🔎 " + " · ".join(parts)


def resolve_why_text(ep: dict) -> str:
    """#329-trace: the alert's italic "why" leads with the JUDGE's OWN rationale when the judge is
    authoritative — it was showing the FLOOR's analysis (claude_analysis) under an authoritative
    judge, the same coherence gap #319 fixed for the headline. Floor/fallback authority (or a judge
    that rendered no rationale) → the floor analysis, as before."""
    if _judge_authoritative(ep):
        jr = (ep.get("judge_rationale") or "").strip()
        if jr:
            return jr
    return ep.get("claude_analysis") or ""


def format_judge_trace_suffix(ep: dict) -> str:
    """#329-trace: the judge's DIVERGENCE signals folded onto the fire line (NOT a new block) —
    materiality tier + whether a DIRECT primary source backed the grade. These are the at-a-glance
    "does this rating align with expectation?" cues alongside the lit fire axes. Empty string when
    neither is present (byte-identical to the pre-change fire line)."""
    bits = []
    mat = ep.get("judge_materiality_tier")
    if mat:
        bits.append(f"materiality {mat}")
    if ep.get("has_direct_source"):
        bits.append("direct-source present")
    return (" · " + " · ".join(bits)) if bits else ""


async def send_ep_alert(ep: dict, chat_id: int | None = None) -> None:
    """Send an immediate EP alert to Telegram."""
    tier_e = TIER_EMOJI.get(ep.get("score_tier", ""), "")
    cat_e = CATALYST_EMOJI.get(ep.get("catalyst_quality", ""), "")
    gem = " ✓Pplx" if ep.get("gemini_validation") == ep.get("catalyst_quality") else ""

    # Sanitize before truncation — disclaimer detection works on full text;
    # truncating first risks cutting before a signal phrase (#130).
    catalyst_text = ep.get("catalyst", "See news") or "See news"
    catalyst_text = re.sub(r"gapped (?:up |down )?[\d.]+%", "gapped up", catalyst_text)
    catalyst_text = _sanitize_perplexity_filler(catalyst_text)
    catalyst_text = _truncate_sentence(catalyst_text, 300)

    # #317 (A) — catalyst-display coherence on the load-bearing alert. ep["catalyst"] is the
    # Perplexity DISCOVERY narrative (news_summary), a different text from claude_analysis (the
    # judge's grounded rationale shown in italics above). When the grade rests on a DIRECT source
    # (SEC filing / press wire → has_direct_source), the grounded catalyst IS the italic, and the
    # discovery line is redundant — and sometimes CONTRADICTS the grade (SWBI 6/18: "positioning/
    # flow move, no clean catalyst" while the judge graded HIGH on the 8-K). Suppress it then.
    # Keep it when there is NO direct source (it's the only catalyst info) or when claude_analysis
    # is empty (never leave the alert with zero catalyst).
    _analysis_stripped = (ep.get("claude_analysis") or "").strip()
    _judge_grounded = bool(ep.get("has_direct_source")) and bool(_analysis_stripped)
    catalyst_block = "" if _judge_grounded else f"Catalyst: {catalyst_text}\n\n"
    if _judge_grounded:
        # #405 fold / #317-verify (2026-07-07): the suppression is DISPLAY-only and has_direct_source
        # is never persisted, so it was un-verifiable post-hoc. Emit an audit row → the next
        # direct-source HIGH verifies the suppress from the log (closes #317's verifiability gap).
        # Observability only — a DB failure here MUST NEVER break the alert (mirror the convergence guard).
        try:
            await log_audit_event(
                "ep_catalyst_suppressed",
                summary=f"{ep.get('ticker')} catalyst discovery line suppressed (grounded direct-source grade)",
                detail=(f"ticker={ep.get('ticker')} tier={ep.get('score_tier')} "
                        f"cat_len={len(ep.get('catalyst') or '')} "
                        f"analysis_len={len(_analysis_stripped)}"))
        except Exception as _se:
            logger.warning("ep_catalyst_suppressed audit emit failed (non-fatal): %s", _se)

    # Sugar Baby Convergence tag — operator escalation cue. Pure telemetry:
    # DB failure here MUST NEVER break the underlying EP alert (the trading
    # signal). Default to no-tag on any exception, log loud audit, proceed.
    conv: dict | None = None
    try:
        from agents.market_intelligence.db import check_sugar_baby_convergence
        conv = await check_sugar_baby_convergence(ep["ticker"])
    except Exception as _ce:
        try:
            await log_audit_event(
                "sugar_baby_convergence_check_failed",
                f"{ep['ticker']}: {type(_ce).__name__}: {str(_ce)[:200]}"
            )
        except Exception:  # loud-ok: fallback-of-the-fallback — the audit call
            pass          # itself may share the same DB outage; nothing above
                          # can handle it and the EP alert must still proceed.
    conv_tag = ""
    if conv:
        if conv["convergence_class"] == "breakout":
            conv_tag = (
                f"🎯🎯 *BREAKOUT CONVERGENCE* — "
                f"cohort {conv['cohort_n']}× · "
                f"TRIGGERED {conv['days_since_stage']}d ago\n\n"
            )
        else:
            conv_tag = (
                f"🍬🌀🎯 *SUGAR BABY CONVERGENCE* — "
                f"cohort {conv['cohort_n']}× · "
                f"{conv['flag_stage']} {conv['days_since_stage']}d ago\n\n"
            )
        # Same-trading-day audit dedup — EP scans tick every 5 min and
        # re-fire HIGH alerts as ep_score evolves over the 3-hour scan
        # window. The original 1h dedup (copied from
        # catalyst_earnings_revenue_weak_downgrade) was wrong shape for
        # convergence telemetry: a ticker firing at 7:00, 8:05, 9:10 over
        # the scan window generates 3 audit rows instead of 1, inflating
        # backtest N denominator ~3x. Trading-day check (ET) gives
        # exactly-once-per-converging-ticker semantics. Advisor flagged
        # 2026-05-22 PM (#85, shipped 2026-05-23).
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                prior = await conn.fetchrow("""
                    SELECT 1 FROM mi_audit_log
                    WHERE event_type = 'sugar_baby_convergence_alert'
                      AND summary LIKE $1
                      AND (created_at AT TIME ZONE 'America/New_York')::date
                          = (NOW() AT TIME ZONE 'America/New_York')::date
                    LIMIT 1
                """, f"{ep['ticker']} MAGNA53_HIGH%")
                if prior is None:
                    await log_audit_event(
                        "sugar_baby_convergence_alert",
                        f"{ep['ticker']} MAGNA53_HIGH — "
                        f"class={conv['convergence_class']} "
                        f"cohort={conv['cohort_n']}x stage={conv['flag_stage']}"
                    )
        except Exception as _ae:
            # Audit dedup/insert failure is also telemetry — don't block alert
            logger.debug(f"Convergence audit log failed (non-critical): {_ae}")

    # North Star C1 (2026-05-30): surface catalyst TYPE — the "fire" (Pradeep
    # hierarchy: theme > policy > shortage > operational). ADVISORY — does not
    # gate; complements the magnitude grade (catalyst_quality) above.
    _ct = ep.get("catalyst_type")
    ct_line = f"{_catalyst_type_mark(_ct)} Type: *{_ct.replace('_', ' ').title()}*\n" if _ct else ""

    # Fire axes — JUDGE-owned since #249 (2026-06-10; the #200 theme-gated
    # advisory line retired with it — the judge weighs the theme axis in the
    # grade itself): the holistic judge's verdict names which axes lit
    # (catalyst/theme/narrative). Absent key = judge fail-open (no verdict) →
    # no line; empty list = judge saw no fire.
    # #329-trace (display-only): fold the judge's divergence signals (materiality + direct-source)
    # onto the fire line so the operator can eyeball "does this rating align?" without a new block.
    _trace_suffix = format_judge_trace_suffix(ep)
    fire_line = ""
    _axes = ep.get("fire_axes")
    if _axes:
        fire_line = f"🔥 Fire (judge): {', '.join(_axes)}{_trace_suffix}\n"
    elif _axes is not None:
        fire_line = f"🔥 Fire (judge): *⚠️ none seen* — no axis lit{_trace_suffix}\n"

    # The italic "why" leads with the judge's own rationale when authoritative (see resolve_why_text).
    _why_text = resolve_why_text(ep)

    head_e, head_label = resolve_headline_grade(ep)
    _rv_str, _rv_pm = _resolve_ep_rvol(ep)  # pm_rvol pre-market — same SSoT as the brief/HUD line
    text = (
        conv_tag +
        f"*EP ALERT {tier_e}*\n\n"
        f"*{ep['ticker']}* {head_e} {head_label}\n"
        f"{ct_line}"
        f"Gap: *{ep['gap_pct']:.1f}%* | {'pm RVOL' if _rv_pm else 'RVOL'}: *{_rv_str}*"
        + (f" (intensity *{ep['projected_vol_multiple']:.0f}x*)" if ep.get('projected_vol_multiple') else "")
        + f" | Score: *{ep['ep_score']:.0f}*\n"
        + fire_line + "\n"
        f"_{_why_text}_\n\n"
        # Catalyst line: shown unless the grade rests on a direct source (#317 — then the italic
        # claude_analysis above already carries the grounded catalyst; the discovery line is
        # suppressed to avoid the contradiction/redundancy).
        + catalyst_block
        # Grade provenance — floor (Claude) · Perplexity cross-check · judge verdict. Always
        # shown so the operator sees how the final tier was reached + where Perplexity fits.
        + format_grade_provenance(ep)
    )

    # Rubric snapshot (2026-05-19 Phase 5): if we have a structured-metrics
    # extraction + rubric score, append a readable summary so the operator
    # sees the methodology assessment alongside the alert. Theme membership
    # (Pradeep #1 catalyst type) surfaced separately as metadata.
    try:
        from agents.market_intelligence.catalyst_metrics_extractor import (
            lookup_cached_metrics,
        )
        from agents.market_intelligence.catalyst_rubric_runtime import (
            score_ep_with_rubric, format_rubric_for_telegram,
            get_theme_membership, format_theme_for_telegram,
        )
        from agents.market_intelligence.collector import et_today as _et_today
        _today = ep.get("alert_date") or _et_today()
        if isinstance(_today, str):
            from datetime import datetime as _dt
            _today = _dt.fromisoformat(_today).date()
        _extracted = await lookup_cached_metrics(ep["ticker"], _today)
        if _extracted:
            _rubric_text = format_rubric_for_telegram(ep["ticker"], _extracted, _today)
            if _rubric_text:
                text += "\n\n" + _rubric_text
            else:
                # Metrics WERE extracted but the rubric couldn't score: its anchor revenue axis
                # needs a prior-year comparable, and the LLM got the quarter but not the YoY
                # (JBL/LZB 6/17 — q_revenue_usd.yoy_pct is None). Surface WHY rather than silently
                # dropping the block. (The deterministic-yfinance-YoY fix is grade-affecting → #149.)
                text += "\n\n🧪 Rubric: not scored (no prior-year revenue comparable extracted)"
        # Theme membership — surface for EVERY EP alert (independent of rubric)
        try:
            _theme = await get_theme_membership(ep["ticker"])
            if _theme:
                # In a tracked engine cohort — the strongest, unambiguous case.
                text += "\n" + format_theme_for_telegram(_theme)
            elif _axes and any(a in ("theme", "narrative") for a in _axes):
                # BLIND-SPOT case (operator 6/18): the judge lit the theme/narrative axis but the
                # ticker is in NO tracked engine cluster (JBL 6/17: judge-inferred AI-infra theme,
                # in_active_theme=False). This is NOT "no theme" — it's "a theme our engine isn't
                # tracking." Pradeep ranks theme as the #1 catalyst, so a COVERAGE blind spot here
                # is materially worse than a true standalone and must be called out as such, not
                # hidden behind a bare "Theme: —". Verify whether a real cohort exists (#325).
                text += (
                    "\nTheme: ⚠️ none tracked — possible BLIND SPOT "
                    "(judge inferred a theme/narrative but the engine has no cohort — verify; #325)"
                )
            elif _axes is not None:
                # STANDS-ALONE case (operator 6/18): the judge DID render a verdict and lit no
                # theme/narrative axis (empty list, or another axis only like catalyst — SWBI).
                # Combined with no engine cohort, the stock is genuinely on its own — a single-name
                # move. Explicitly distinguished from the blind-spot case above so the operator
                # never confuses "we missed the theme" with "there is no theme."
                text += "\nTheme: — none (stock stands alone — no engine cohort, judge lit no theme)"
            else:
                # JUDGE-SILENT case: _axes is None = judge fail-open (no verdict). We only know the
                # engine tracks no cohort; we CANNOT claim "stands alone" because the judge never
                # weighed in. Report the honest unknown rather than overclaiming either way.
                text += "\nTheme: — none tracked (engine has no cohort; judge rendered no verdict)"
        except Exception as _te:
            logger.debug(f"Theme membership lookup failed (non-critical): {_te}")
    except Exception as _e:
        logger.debug(f"Rubric snapshot in EP alert failed (non-critical): {_e}")

    await send_telegram_message(text, chat_id)

    # Post to Twitter/X
    try:
        from agents.market_intelligence.twitter import post_ep_tweet
        await post_ep_tweet(ep)
    except Exception as e:
        logger.warning(f"EP tweet failed (non-critical): {e}")


async def premarket_gap_risk_scan() -> int:
    """ADR 0023 Card 5 — 9:00 ET pre-market gap-risk heads-up (telemetry, READ-ONLY).

    For each OPEN position, if the pre-market price is already BELOW its live stop, the
    stop will likely fill WORSE than intended at the open (an overnight gap-THROUGH, the
    SYRE −4.57R / DELL −1.43R class — the stop fires, it's just a market gap). This
    Telegrams a heads-up BEFORE the open so the operator can decide. It changes NOTHING —
    no order action, the stop stands (exit discipline = THE LINE). Per-account (dual-account
    #66): iterates active modes, labels each alert with the owning account. Returns the count
    of at-risk positions alerted."""
    from agents.market_intelligence.constants import active_account_modes, mode_prefix
    from agents.market_intelligence.collector import get_premarket_prices
    pool = await get_pool()
    alerted = 0
    for mode in active_account_modes():
        async with pool.acquire() as conn:
            opens = await conn.fetch("""
                SELECT ticker, entry_price, stop_price, remaining_shares, hold_days
                FROM mi_live_trades
                WHERE status = 'filled' AND remaining_shares > 0
                  AND account_mode = $1 AND stop_price IS NOT NULL
            """, mode)
        if not opens:
            continue
        prices = await get_premarket_prices([o["ticker"] for o in opens])
        for o in opens:
            px, stop = prices.get(o["ticker"]), o["stop_price"]
            if px is None or stop is None or px >= stop:
                continue  # no quote, or holding above the stop → no gap-through risk
            under = (stop - px) / stop * 100
            entry = o["entry_price"]
            from_entry = f", {((px - entry) / entry * 100):+.1f}% vs entry" if entry else ""
            await send_telegram_message(
                f"{mode_prefix(mode)}⚠️ *Gap-risk:* `{o['ticker']}` pre-market "
                f"${px:.2f} is BELOW stop ${stop:.2f} ({under:.1f}% under{from_entry}) — "
                f"may gap THROUGH the stop at the open ({o['hold_days']}d hold). "
                f"Heads-up only; the stop stands."
            )
            try:
                await log_audit_event(
                    "premarket_gap_risk",
                    summary=f"{o['ticker']} pre-market ${px:.2f} < stop ${stop:.2f} ({mode})",
                    detail=f"ticker={o['ticker']} mode={mode} premarket={px:.4f} "
                           f"stop={stop:.4f} under_pct={under:.2f} hold_days={o['hold_days']}",
                )
            except Exception as _e:  # loud-ok: audit is telemetry-of-telemetry; the Telegram above already fired
                logger.warning("premarket_gap_risk audit emit failed (non-fatal): %s", _e)
            alerted += 1
    return alerted
