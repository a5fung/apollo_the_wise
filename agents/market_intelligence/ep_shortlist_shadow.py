"""SHORTLIST PRE-SCORE — ranking + counterfactual record (2026-08-22, operator-directed).

`run_ep_scan` grades only the top `SHORTLIST_SIZE` candidates per tick, and until
2026-08-22 that shortlist was ordered by GAP SIZE — the measure the same-day
separation change deleted from the score for running BACKWARDS on real EPs
(AUC 0.34). Operator: "how are we still using it after all this work… that's like
saying this is completely wrong for weeks and fixing it for weeks and then say we
still use it." This module computes the three-term pre-score ranking
(`ep_rubric.SHORTLIST_WEIGHTS` — liquidity 15×3 / flat gap 10×1 / theme 10×1,
composite 0..65) for EVERY candidate and records the gap-vs-prescore
counterfactual per candidate per tick in `mi_ep_shortlist_shadow`.

🔁 THE REVERT FLAG — `ep_shortlist_prescore` runtime toggle /
`EP_SHORTLIST_PRESCORE_ENABLED` env, default ON, read once per scan tick in
`run_ep_scan` (the catalyst_tier_lattice pattern; instant no-redeploy revert,
~60s cache lag). OFF → the shortlist reverts to gap ordering EXACTLY (the sort
at the top of the ranking block is untouched; the prescore re-sort simply never
runs) — pinned by tests/test_ep_shortlist_prescore.py. Revert SQL:
    INSERT INTO mi_safeguard_state (safeguard, account_mode, state, last_transition_at, updated_at)
    VALUES ('ep_shortlist_prescore', 'global', 'off', NOW(), NOW())
    ON CONFLICT (safeguard, account_mode) DO UPDATE SET state = EXCLUDED.state, updated_at = NOW();
Fail direction on ANY error in the ranking block: gap ordering acts (the
pre-change behaviour), loudly — never a dead scan.

⚠ THE RECORD STORES RAW INPUTS ONLY — NEVER COMPUTED POINTS. Points are a
function of the weight table; the moment a weight is swept, stored points are
stale and a replay silently scores the old rubric (the #583 stale-derived-value
class, fixed the same day this shipped). `catalyst_tier_shadow` set the
convention — raw inputs "so any variant can be replayed against outcomes later
without new data". The ranks + would-be-shortlisted flags ARE stored: they are
the acting DECISION record (what the sort did that tick under each key), not a
derived value to be recomputed. `acting_key` stamps which ordering ACTED per
row — a reader must never infer the acting side from a date.

$0 AT RUNTIME — pure arithmetic on numbers the scan already holds; no LLM, no
API call. The recorder is fail-open (log only, returns 0) and is read by NO
grading / entry / sizing / ordering / safeguard path — comparison telemetry
only (the catalyst_tier_shadow / ep_score_shadow contract).
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from agents.market_intelligence.ep_rubric import (
    SHORTLIST_SIZE, shortlist_prescore, shortlist_sort_key)

logger = logging.getLogger(__name__)

# Module-level for test patchability (the catalyst_tier_shadow convention —
# tests patch `esls.get_pool` directly).
from agents.market_intelligence.db import get_pool  # noqa: E402

# adv values with a REAL 20-day basis. "pending" means the candidate dict holds
# the prevDay.v placeholder (_snap_candidate) — one day's volume is not
# liquidity evidence, so the liquidity axis is treated as MISSING and the
# composite rescales (P1: a data gap must never silently sink a candidate).
_REAL_ADV_SOURCES = ("rs_universe", "polygon_20d")


def compute_shortlist_ranking(
    candidates: list[dict], in_active_theme_set: set[str],
) -> tuple[list[dict], dict[str, int]]:
    """Pre-score EVERY candidate and rank by `shortlist_sort_key` (composite
    desc → continuous ADV$ desc → ticker asc; the tie-break policy and its
    justification live on that function). Pure — no I/O, no mutation of
    `candidates`.

    Returns `(entries, rank_by_prescore)`:
    - `entries`: one dict per candidate, RAW INPUTS snapshotted at this moment
      (gap_pct / prev_close / adv / adv_source / in_active_theme) plus the
      computed composite + adv_dollar for the sort — callers must persist only
      the raw inputs (see module docstring).
    - `rank_by_prescore`: ticker → 1-based rank under the pre-score key.
    """
    entries: list[dict] = []
    for c in candidates:
        prev_close = c.get("prev_close")
        adv = c.get("adv")
        adv_source = c.get("adv_source")
        adv_dollar = (
            float(adv) * float(prev_close)
            if adv and prev_close and adv_source in _REAL_ADV_SOURCES
            else None
        )
        in_theme = c["ticker"] in in_active_theme_set
        pre = shortlist_prescore(
            adv_dollar=adv_dollar, gap_pct=c.get("gap_pct"),
            in_active_theme=in_theme)
        entries.append({
            "ticker": c["ticker"],
            # raw inputs (the persisted record):
            "gap_pct": c.get("gap_pct"),
            "prev_close": prev_close,
            "adv": adv,
            "adv_source": adv_source,
            "in_active_theme": in_theme,
            # sort artifacts (composite is NOT persisted — #583 class):
            "composite": pre["composite"],
            "adv_dollar": adv_dollar,
        })
    entries.sort(key=lambda e: shortlist_sort_key(
        e["ticker"], e["composite"], e["adv_dollar"]))
    rank_by_prescore = {e["ticker"]: i + 1 for i, e in enumerate(entries)}
    return entries, rank_by_prescore


def build_shortlist_shadow_rows(
    entries: list[dict],
    rank_by_prescore: dict[str, int],
    rank_by_gap: dict[str, int],
    acting_key: str,
    minutes_since_open: "int | None",
    shortlist_size: int = SHORTLIST_SIZE,
) -> list[dict]:
    """Assemble the per-candidate-per-tick counterfactual rows from a
    `compute_shortlist_ranking` result. RAW INPUTS + both ranks + the
    would-be-shortlisted flag under each key + which key ACTED. Pure."""
    board_n = len(entries)
    rows = []
    for e in entries:
        rp = rank_by_prescore.get(e["ticker"])
        rg = rank_by_gap.get(e["ticker"])
        rows.append({
            "ticker": e["ticker"],
            "gap_pct": e["gap_pct"],
            "prev_close": e["prev_close"],
            "adv": e["adv"],
            "adv_source": e["adv_source"],
            "in_active_theme": e["in_active_theme"],
            "rank_by_prescore": rp,
            "rank_by_gap": rg,
            "shortlisted_by_prescore": rp is not None and rp <= shortlist_size,
            "shortlisted_by_gap": rg is not None and rg <= shortlist_size,
            "acting_key": acting_key,
            "board_n": board_n,
            "minutes_since_open": minutes_since_open,
        })
    return rows


async def record_ep_shortlist_shadow(
    rows: list[dict[str, Any]],
    scan_date: date,
    now_et: datetime,
) -> int:
    """Batch writer — called fire-and-forget after the scan loop (next to the
    catalyst-tier and score-shadow batch writes, same contract: never raises,
    never blocks the scan). One INSERT per (tick, ticker) — append-only, no
    upsert: the per-tick history is the point (board membership and gap move
    intraday; ADV$ does not, which the record lets a reader verify). Returns
    rows written (0 on any failure)."""
    if not rows:
        return 0
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.executemany(_INSERT_SQL, [
                (
                    scan_date, r["ticker"], now_et,
                    r.get("minutes_since_open"),
                    r.get("gap_pct"), r.get("prev_close"),
                    r.get("adv"), r.get("adv_source"),
                    r.get("in_active_theme"),
                    r.get("rank_by_prescore"), r.get("rank_by_gap"),
                    r.get("shortlisted_by_prescore"),
                    r.get("shortlisted_by_gap"),
                    r.get("acting_key") or "prescore",
                    r.get("board_n"),
                )
                for r in rows
            ])
        return len(rows)
    except Exception as e:
        logger.warning(f"shortlist shadow: batch write failed — {e}")
        return 0


_INSERT_SQL = """
    INSERT INTO mi_ep_shortlist_shadow (
        scan_date, ticker, scan_time_et, minutes_since_open,
        gap_pct, prev_close, adv, adv_source, in_active_theme,
        rank_by_prescore, rank_by_gap,
        shortlisted_by_prescore, shortlisted_by_gap,
        acting_key, board_n
    ) VALUES ($1,$2,$3,$4, $5,$6,$7,$8,$9, $10,$11, $12,$13, $14,$15)
"""
