"""#452 — exposure-family shadow counter (premortem R1: one theme in five costumes).

SHADOW / observe-only (sitting-ruled 2026-07-12 B3): when a would-be entry would lift
same-family exposure above the threshold, EMIT (audit + Telegram) — never block. The
promote-to-BLOCKING flip is the operator fork after ~2 clean weeks
(`exposure_family_cap_promotion` gated review) — the drawdown-breaker promotion pattern.

Register R5 constraints (cross-ADR sweep 7/11): the grouping key is named
`exposure_family` (NEVER bare "family" — 0025's merge-arm "family" is a different object);
v1 family key = ACTIVE-THEME membership (post-0025-merge canonical themes make this
higher-quality when the arm ships); open positions are counted via `db.OPEN_POSITION_STATUSES`
(fork B) — never a hand-rolled vocabulary.
"""
from __future__ import annotations

import json
import logging

from agents.market_intelligence.db import get_pool, log_audit_event, OPEN_POSITION_STATUSES

logger = logging.getLogger(__name__)

# The candidate would become the (N+1)th same-family position; emit when the EXISTING
# same-family count is already >= this (i.e. the entry lifts exposure above it).
EXPOSURE_FAMILY_SHADOW_THRESHOLD = 2


async def check_family_exposure(ticker: str, account_mode: str) -> dict | None:
    """Count open positions sharing an ACTIVE theme with `ticker`. Returns
    {candidate_themes, open_positions, same_family, breach} or None on no-data.
    READ-ONLY — the caller decides what to do (the shadow hook only emits)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        opens = await conn.fetch(
            """
            SELECT ticker FROM mi_live_trades
            WHERE status = ANY($2) AND account_mode = $1 AND ticker != $3
            """,
            account_mode, list(OPEN_POSITION_STATUSES), ticker,
        )
        themes = await conn.fetch(
            """
            SELECT DISTINCT ON (name) name, tickers
            FROM mi_themes
            WHERE stage != 'Retired'
              AND theme_date >= CURRENT_DATE - INTERVAL '7 days'
            ORDER BY name, theme_date DESC
            """
        )
    open_tickers = [r["ticker"] for r in opens]
    membership: dict[str, set] = {}
    for t in themes:
        members = set(t["tickers"] or [])
        for tk in [ticker] + open_tickers:
            if tk in members:
                membership.setdefault(tk, set()).add(t["name"])
    cand_themes = membership.get(ticker, set())
    same_family = sorted(
        tk for tk in open_tickers if membership.get(tk, set()) & cand_themes
    )
    return {
        "candidate_themes": sorted(cand_themes),
        "open_positions": open_tickers,
        "same_family": same_family,
        "breach": len(same_family) >= EXPOSURE_FAMILY_SHADOW_THRESHOLD,
    }


async def shadow_check_and_emit(ticker: str, account_mode: str, strategy_label: str) -> None:
    """The entry-pipeline SHADOW hook: observe-only, error-isolated by the CALLER's
    try/except (the #94-hook pattern) — this function may raise freely; it must never
    be called un-wrapped on the entry path."""
    info = await check_family_exposure(ticker, account_mode)
    if not info or not info["breach"]:
        if info and info["candidate_themes"]:
            logger.info(
                f"exposure_family [{account_mode}] {ticker}: "
                f"{len(info['same_family'])} same-family open(s) — under threshold"
            )
        return
    await log_audit_event(
        "exposure_family_breach",
        f"{ticker} ({account_mode}/{strategy_label}): entry would lift same-family "
        f"exposure to {len(info['same_family']) + 1} "
        f"(threshold {EXPOSURE_FAMILY_SHADOW_THRESHOLD} + the candidate)",
        json.dumps({
            "ticker": ticker, "account_mode": account_mode,
            "candidate_themes": info["candidate_themes"],
            "same_family_opens": info["same_family"],
            "shadow": True,
        }),
    )
    from agents.market_intelligence.briefing import send_telegram_message
    from agents.market_intelligence.constants import mode_prefix
    fam = ", ".join(info["candidate_themes"][:3]) or "?"
    await send_telegram_message(
        f"{mode_prefix(account_mode)}👪 *EXPOSURE-FAMILY (shadow):* {ticker} would be the "
        f"{len(info['same_family']) + 1}th same-family position "
        f"({', '.join(info['same_family'])}) — theme(s): {fam}\n"
        f"_Observe-only (#452); no entry was blocked. Blocking = the operator fork after "
        f"~2 clean weeks._"
    )
