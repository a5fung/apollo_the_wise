"""#533 — the SEPARATION score record (2026-08-22, operator-signed): both sides of
the ep_score_separation flip, per scored candidate per day.

The operator's explicit condition on the sign-off: *"ok, let's go, similar to
before, we have fixing EPs so bias for action but keep tracking existing if we
make changes."* This module IS the "keep tracking existing": for every candidate
`run_ep_scan` scores, BOTH rubric sides are computed by the same `_score_ep`
(never a reimplementation) and recorded here — a reader can see, per name per
day, what the OLD rubric would have scored and tiered it, alongside the new one.

COLUMN SEMANTICS ARE CONSTANT ACROSS THE FLIP (the catalyst-tier shadow
record's contract — see catalyst_tier_shadow.py):
  sep_score_* / sep_tier_*       = ALWAYS the separation side (flat gap credit +
                                   branch-4-only conviction floor, tiered at the
                                   uniform bar — ep_rubric.SCORE_WEIGHTS /
                                   SEPARATION_BAR). Since the #533 RESCALE
                                   (2026-08-22) these are on the PRESENTED
                                   scale (1.25 x raw + 15, bar 65); the row's
                                   own sep_bar column stamps which scale a row
                                   used (40 = pre-rescale raw, 65 = presented).
  legacy_score_* / legacy_tier_* = ALWAYS the pre-2026-08-22 rubric
                                   (SCORE_WEIGHTS_LEGACY), tiered at the
                                   per-regime bar (65/70/75/80) — old raw
                                   scale, untouched by the rescale.
  live_side                      = 'separation' | 'legacy' — which side ACTED on
                                   this row's latest tick. Explicit BY DESIGN:
                                   a reader must never infer the acting side
                                   from a date (that is how this data becomes
                                   useless later).

Tiers are the PRE-override read (HIGH >= that side's bar; MODERATE >= that
side's cutline — legacy 50; the separation side has NO cutline since the #533
rescale, so its non-HIGHs are NULL) — the earnings override and the holistic
judge can still move the ACTING tier downstream, same caveat as the
catalyst-tier record.

$0 AT RUNTIME — pure arithmetic on numbers the scan already computed; no LLM,
no API call. Fail direction: the recorder is fail-open (log only, returns 0) —
telemetry must never jeopardize the scan (the tape_quality / vol_profile /
catalyst_tier_shadow contract). Read by NO grading / entry / sizing / ordering /
safeguard path.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Module-level for test patchability (the catalyst_tier_shadow convention —
# tests patch `ess.get_pool` directly).
from agents.market_intelligence.db import get_pool  # noqa: E402


async def record_ep_score_shadow(
    inputs: list[dict[str, Any]],
    scan_date: date,
    now_et: datetime,
) -> int:
    """Batch writer — called fire-and-forget after the scan loop (next to the
    catalyst-tier batch write, same contract: never raises, never blocks the
    scan). Returns rows written (0 on any failure).

    Each item carries both sides precomputed at the flip point in `run_ep_scan`
    (recorded verbatim — the acting score and the recorded one can never
    drift): sep_score/sep_tier, legacy_score/legacy_tier, sep_bar/legacy_bar,
    live_side, gap_pct, catalyst_quality."""
    if not inputs:
        return 0
    try:
        pool = await get_pool()
        written = 0
        async with pool.acquire() as conn:
            for item in inputs:
                try:
                    await conn.execute(
                        _UPSERT_SQL,
                        scan_date, item["ticker"], now_et,
                        item.get("sep_score"), item.get("sep_tier"),
                        item.get("legacy_score"), item.get("legacy_tier"),
                        item.get("sep_bar"), item.get("legacy_bar"),
                        item.get("live_side") or "separation",
                        item.get("gap_pct"), item.get("catalyst_quality"),
                    )
                    written += 1
                except Exception as e:
                    logger.warning(f"score shadow: row failed for {item.get('ticker')}: {e}")
        return written
    except Exception as e:
        logger.warning(f"score shadow: batch write failed — {e}")
        return 0


# first_* columns are written once (INSERT); last_* refresh every tick —
# intraday drift (the gap read moving, a catalyst regrade) stays observable on
# both sides, the same first/last idiom as the catalyst-tier shadow record.
_UPSERT_SQL = """
    INSERT INTO mi_ep_score_shadow (
        scan_date, ticker, first_seen_et, last_seen_et,
        sep_score_first, sep_score_last, sep_tier_first, sep_tier_last,
        legacy_score_first, legacy_score_last, legacy_tier_first, legacy_tier_last,
        sep_bar, legacy_bar, live_side,
        gap_pct_first, gap_pct_last, catalyst_quality_last
    ) VALUES (
        $1,$2,$3,$3, $4,$4,$5,$5, $6,$6,$7,$7, $8,$9,$10, $11,$11,$12
    )
    ON CONFLICT (scan_date, ticker) DO UPDATE SET
        last_seen_et          = EXCLUDED.last_seen_et,
        sep_score_last        = EXCLUDED.sep_score_last,
        sep_tier_last         = EXCLUDED.sep_tier_last,
        legacy_score_last     = EXCLUDED.legacy_score_last,
        legacy_tier_last      = EXCLUDED.legacy_tier_last,
        sep_bar               = EXCLUDED.sep_bar,
        legacy_bar            = EXCLUDED.legacy_bar,
        live_side             = EXCLUDED.live_side,
        gap_pct_last          = EXCLUDED.gap_pct_last,
        catalyst_quality_last = EXCLUDED.catalyst_quality_last
"""
