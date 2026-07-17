"""#452 R1 Stage 1 — correlated-book concentration TELEMETRY (premortem TOP risk).

The entry path has no theme/family/correlation gate: five same-family EP HIGHs
can fill all five slots — one bet at ~100% deployment — and the theme axis
STEERS selection toward exactly that (docs/analysis/premortem_450_2026-07-11.md
§R1). Stage 1 (this module) is visibility-before-authority per house
discipline: an EOD audit row every run + a Telegram line ONLY when ≥2 open
positions share a family. Stage 2 (the family-slot cap at entry) is
CHANGE_PROCESS + operator sign-off gated — design in
docs/analysis/452_r1_stage2_design_2026-07-17.md; NOTHING here touches entry
submission, sizing, safeguards, or any live trade path (THE LINE).

Family notion = ADR 0025 Stage-A name-stem families (`theme_merge_arm.family_of`)
over the ACTIVE themes each open ticker belongs to — one mechanism, reused
(premortem's explicit rec). A ticker in multiple families counts in each
(concentration should over-warn, not under-warn). Overnight notional is
ENTRY-BASIS (remaining_shares × entry_price) — no quote fetch at 16:18; the
approximation is stated in the audit detail.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict

from agents.market_intelligence.db import get_pool, log_audit_event
from agents.market_intelligence.theme_merge_arm import family_of

logger = logging.getLogger(__name__)

CONCENTRATION_FLAG_MIN = 2   # ≥2 open positions in one family = flagged


def compute_concentration(
    positions: list[dict],
    active_themes: list[dict],
    equity: float | None,
) -> dict:
    """PURE core — no I/O. positions: [{ticker, remaining_shares, entry_price}];
    active_themes: mi_themes dicts (name + tickers) already filtered to
    non-Fading/non-Retired; equity: latest snapshot dollars or None.

    Returns {n_open, notional, pct_equity, families: {fam: [tickers]},
    flagged: [(fam, [tickers])], unthemed: [tickers]}.
    """
    ticker_families: dict[str, set[str]] = defaultdict(set)
    for t in active_themes:
        fam = family_of(t.get("name") or "")
        if not fam:
            continue
        for tk in t.get("tickers") or []:
            ticker_families[tk].add(fam)

    families: dict[str, list[str]] = defaultdict(list)
    unthemed: list[str] = []
    notional = 0.0
    for p in positions:
        tk = p["ticker"]
        shares = float(p.get("remaining_shares") or 0)
        px = float(p.get("entry_price") or 0)
        notional += shares * px
        fams = ticker_families.get(tk)
        if fams:
            for fam in sorted(fams):
                families[fam].append(tk)
        else:
            unthemed.append(tk)

    flagged = sorted(
        ((fam, tks) for fam, tks in families.items()
         if len(tks) >= CONCENTRATION_FLAG_MIN),
        key=lambda x: -len(x[1]))
    pct = (notional / equity * 100.0) if equity and equity > 0 else None
    return {
        "n_open": len(positions),
        "notional": round(notional, 2),
        "pct_equity": round(pct, 1) if pct is not None else None,
        "families": {f: sorted(tks) for f, tks in families.items()},
        "flagged": [(f, sorted(tks)) for f, tks in flagged],
        "unthemed": sorted(unthemed),
    }


def format_concentration_line(res: dict) -> str:
    """One operator-facing line — only rendered when something is flagged.
    Telegram-safe (review 7/17): 4 of the 13 Stage-A family stems carry
    underscores (payments_fintech, gene_cell_therapy, defense_aero,
    energy_downstream) — a bare `_` in Markdown V1 flips the whole chunk's
    entity parity (the #477 class), so the dynamic family+tickers segment
    lives inside a CODE SPAN, which neutralizes every entity char."""
    worst_fam, worst_tks = res["flagged"][0]
    pct = (f" · overnight {res['pct_equity']:.0f}% of equity"
           if res["pct_equity"] is not None else
           f" · overnight ${res['notional']:,.0f}")
    more = (f" (+{len(res['flagged']) - 1} more family)"
            if len(res["flagged"]) > 1 else "")
    return (f"⚠️ Book concentration: {len(worst_tks)}/{res['n_open']} open "
            f"positions share family `{worst_fam} — {' '.join(worst_tks)}`"
            f"{more}{pct} — no gate exists (#452 Stage 2)")


async def run_book_concentration_snapshot(account_mode: str = "live") -> dict | None:
    """16:18 ET job body. Reads the open book + active themes + latest equity,
    writes ONE `book_concentration_snapshot` audit row (always, so the series
    is graphable), Telegrams ONLY when flagged (actionable-only, house rule).
    Read-only on trade state. RAISES on DB failure — callers must wrap (the
    scheduler job does, via notify_job_failure; review 7/17 fixed a docstring
    that promised never-raises the body didn't implement)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        positions = [dict(r) for r in await conn.fetch("""
            SELECT ticker, remaining_shares, entry_price
            FROM mi_live_trades
            WHERE account_mode = $1 AND status = 'filled'
              AND COALESCE(remaining_shares, 0) > 0
        """, account_mode)]
        themes = [dict(r) for r in await conn.fetch("""
            SELECT name, tickers FROM mi_themes
            WHERE theme_date = (SELECT MAX(theme_date) FROM mi_themes)
              AND stage NOT IN ('Fading', 'Retired')
        """)]
        eq_row = await conn.fetchrow("""
            SELECT equity FROM mi_account_equity_snapshots
            WHERE account_mode = $1 ORDER BY snapshot_date DESC LIMIT 1
        """, account_mode)
    equity = float(eq_row["equity"]) if eq_row and eq_row["equity"] else None

    res = compute_concentration(positions, themes, equity)
    await log_audit_event(
        "book_concentration_snapshot",
        summary=(f"{account_mode} book: {res['n_open']} open, "
                 f"{len(res['flagged'])} flagged famil(ies), "
                 f"notional ${res['notional']:,.0f}"
                 + (f" ({res['pct_equity']:.0f}% eq)" if res["pct_equity"] is not None else "")),
        detail=json.dumps({**res, "account_mode": account_mode,
                           "basis": "entry_price×remaining_shares (no quote fetch)"}),
    )
    if res["flagged"]:
        from agents.market_intelligence.briefing import send_telegram_message
        from agents.market_intelligence.constants import mode_prefix
        # mode-labeled (review 7/17): the operator runs two books — a real-money
        # concentration warning must not be dismissible as paper noise (#444 class).
        await send_telegram_message(
            f"{mode_prefix(account_mode)}{format_concentration_line(res)}")
    return res
