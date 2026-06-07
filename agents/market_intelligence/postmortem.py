"""
Trade postmortem: joined narrative of a single closed trade.

Merges EP alert, trade execution, forward returns, theme context, and regime
into one LLM-synthesized recap. Falls back to structured text if Sonnet is
unreachable so the command always returns something usable.

Entry points:
  build_postmortem_context(ticker, alert_date) -> dict | None
  generate_postmortem_narrative(ticker, alert_date) -> str
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date
from typing import Any

import anthropic

from agents.market_intelligence.db import get_pool

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 800

_SYSTEM_PROMPT = """You review a single closed momentum/EP trade for Apollo the Wise, a trader who follows Qullamaggie/Pradeep Bonde methodology.

Output exactly 4 sections with these exact Markdown headers, in this order:

*Setup*
One short paragraph: was the alert legitimate at trigger time? Cite catalyst quality, gap %, regime fit, and theme context if any.

*Execution*
One short paragraph: did the ORB entry, stop, and partial rules fire correctly? Any skips, timing issues, or broker friction?

*Outcome*
One short paragraph: what happened? Cite realized P&L vs forward 1d/1w/1m returns. Did price follow through or fade? Compare to SPY where relevant.

*Lesson*
One sentence. Actionable. No hedging.

Rules: 350 words max total. Plain prose, no bullets except where listed above. Telegram Markdown (*bold*, `code`). No filler, no restating the data blob verbatim — interpret it.
"""


async def build_postmortem_context(
    ticker: str, alert_date: date | None = None
) -> dict[str, Any] | None:
    """
    Join EP alert, trade, forward outcomes, themes, and regime for a single trade.

    If alert_date is None, uses the most recent closed trade for ticker.
    Returns None if no trade data exists.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        if alert_date is None:
            trade = await conn.fetchrow("""
                SELECT * FROM mi_live_trades
                WHERE ticker = $1 AND status IN ('closed', 'filled')
                ORDER BY alert_date DESC LIMIT 1
            """, ticker)
            if not trade:
                trade = await conn.fetchrow("""
                    SELECT * FROM mi_paper_trades
                    WHERE ticker = $1 AND status = 'closed'
                    ORDER BY alert_date DESC LIMIT 1
                """, ticker)
        else:
            trade = await conn.fetchrow("""
                SELECT * FROM mi_live_trades
                WHERE ticker = $1 AND alert_date = $2
            """, ticker, alert_date)
            if not trade:
                trade = await conn.fetchrow("""
                    SELECT * FROM mi_paper_trades
                    WHERE ticker = $1 AND alert_date = $2
                """, ticker, alert_date)

        if not trade:
            return None

        ad = trade["alert_date"]

        alert = await conn.fetchrow("""
            SELECT catalyst, catalyst_quality, ep_score, score_tier,
                   gap_pct, rel_volume, claude_analysis, gemini_validation,
                   vol_percentile
            FROM mi_ep_alerts
            WHERE ticker = $1 AND alert_date = $2
            ORDER BY ep_score DESC
            LIMIT 1
        """, ticker, ad)

        outcome = await conn.fetchrow("""
            SELECT fwd_1d_pct, fwd_1w_pct, fwd_1m_pct, spy_fwd_1m_pct
            FROM mi_signal_outcomes
            WHERE signal_type = 'ep_alert'
              AND identifier = $1
              AND signal_date = $2
        """, ticker, ad)

        themes = await conn.fetch("""
            SELECT name, stage, rs_avg
            FROM mi_themes
            WHERE theme_date = $1 AND $2 = ANY(tickers)
        """, ad, ticker)

        regime = await conn.fetchrow("""
            SELECT regime, ep_threshold, qqq_ema_bullish, spy_vs_50ma,
                   breadth_pct_above_40ma, vix, description
            FROM mi_market_regime
            WHERE regime_date <= $1
            ORDER BY regime_date DESC
            LIMIT 1
        """, ad)

    return {
        "ticker": ticker,
        "alert_date": ad.isoformat() if hasattr(ad, "isoformat") else str(ad),
        "trade": _clean(trade),
        "alert": _clean(alert),
        "outcome": _clean(outcome),
        "themes": [_clean(t) for t in themes] if themes else [],
        "regime": _clean(regime),
    }


def _clean(row: Any) -> dict[str, Any] | None:
    """Convert asyncpg Record → JSON-serializable dict."""
    if row is None:
        return None
    out: dict[str, Any] = {}
    for k, v in dict(row).items():
        if v is None or isinstance(v, (str, int, float, bool)):
            out[k] = v
        elif hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, (list, dict)):
            out[k] = v
        else:
            out[k] = str(v)
    return out


async def generate_postmortem_narrative(
    ticker: str, alert_date: date | None = None
) -> str:
    """Build context + synthesize via Sonnet. Falls back to structured text on failure."""
    ctx = await build_postmortem_context(ticker, alert_date)
    if ctx is None:
        return f"No trade data found for *{ticker}*."

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning(f"Postmortem: no ANTHROPIC_API_KEY — using fallback for {ticker}")
        return _fallback_narrative(ctx)

    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        user_prompt = f"TRADE CONTEXT:\n{json.dumps(ctx, default=str, indent=2)}"
        resp = await client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        narrative = "".join(
            b.text for b in resp.content if hasattr(b, "text")
        ).strip()
        header = f"📋 *Postmortem — {ctx['ticker']} {ctx['alert_date']}*"
        return f"{header}\n\n{narrative}"
    except Exception as e:
        logger.warning(f"Postmortem LLM failed for {ticker}: {e} — using fallback")
        return _fallback_narrative(ctx)


def _fmt(v: Any, prec: int = 2, suffix: str = "") -> str:
    if v is None:
        return "n/a"
    if isinstance(v, (int, float)):
        return f"{v:.{prec}f}{suffix}"
    return f"{v}{suffix}"


def _fallback_narrative(ctx: dict) -> str:
    trade = ctx.get("trade") or {}
    alert = ctx.get("alert") or {}
    outcome = ctx.get("outcome") or {}
    themes = ctx.get("themes") or []
    regime = ctx.get("regime") or {}

    lines = [
        f"📋 *Postmortem — {ctx['ticker']} {ctx['alert_date']}*",
        "",
        "*Setup*",
        f"• Catalyst: {alert.get('catalyst') or 'n/a'} ({alert.get('catalyst_quality') or '—'})",
        f"• Score: {_fmt(alert.get('ep_score'), 0)} ({alert.get('score_tier') or '—'}) · "
        f"Gap {_fmt(alert.get('gap_pct'), 1, '%')} · RVOL {_fmt(alert.get('rel_volume'), 1, 'x')}",
        f"• Regime: {regime.get('regime') or 'n/a'} (EP bar {regime.get('ep_threshold')}, "
        f"QQQ bullish={regime.get('qqq_ema_bullish')})",
    ]
    if themes:
        theme_strs = [f"{t['name']} ({t.get('stage')})" for t in themes]
        lines.append(f"• Themes: {', '.join(theme_strs)}")

    lines += [
        "",
        "*Execution*",
        f"• Status: `{trade.get('status') or '—'}` · entry ${_fmt(trade.get('entry_price'))} "
        f"stop ${_fmt(trade.get('stop_price'))} · {_fmt(trade.get('entry_shares'), 0)} sh",
        f"• ORB H=${_fmt(trade.get('orb_high'))} L=${_fmt(trade.get('orb_low'))} · "
        f"ATR14 ${_fmt(trade.get('atr_14'))}",
        f"• Partial: {trade.get('partial_taken')} · Breakeven: {trade.get('breakeven_active')} · "
        f"Held {_fmt(trade.get('hold_days'), 0)}d",
    ]
    if trade.get("skip_reason"):
        from agents.market_intelligence.broker.skip_reasons import humanize
        # #228: a CLOSED/FILLED trade entered and exited — so a skip_reason on it is
        # necessarily a LATER re-entry block (e.g. block:r3_reentry_disabled), NOT the
        # entry gate. Labelling it bare "Skip reason: re-entry disabled" made the
        # weekly-review narrator infer "blocked signal traded through" (a recurring
        # false postmortem inference — RLAY/DY/DELL/RUM, verified false on RUM 6/4:
        # original entry filled 9:44 → stopped out → re-entry correctly blocked 9:49).
        # Relabel deterministically so the narrator can't make the causal error.
        _entered = (trade.get("status") in ("filled", "closed")
                    or trade.get("entry_price") is not None)
        if _entered:
            lines.append(
                f"• Post-entry note: the original entry FILLED; a LATER re-entry was "
                f"correctly blocked ({humanize(trade['skip_reason'])}). This is enforcement "
                f"working as designed — NOT a blocked signal trading through.")
        else:
            lines.append(f"• Skip reason: {humanize(trade['skip_reason'])}")

    pnl = trade.get("total_pnl")
    pnl_str = f"${pnl:+,.2f}" if isinstance(pnl, (int, float)) else "n/a"
    lines += [
        "",
        "*Outcome*",
        f"• Realized P&L: {pnl_str}",
        f"• Fwd returns — 1d: {_fmt(outcome.get('fwd_1d_pct'), 2, '%')} · "
        f"1w: {_fmt(outcome.get('fwd_1w_pct'), 2, '%')} · "
        f"1m: {_fmt(outcome.get('fwd_1m_pct'), 2, '%')} "
        f"(SPY 1m {_fmt(outcome.get('spy_fwd_1m_pct'), 2, '%')})",
        "",
        "*Lesson*",
        "— (LLM synthesis unavailable; review data above)",
    ]
    return "\n".join(lines)
