"""Structure-axis SHADOW recorder — meta-rubric ADR 0016 (#330), #329 child axis 2 of 3
(theme #328 · **structure #330** · gap-alignment #331). Sibling of `theme_axis_shadow.py`
(ADR 0015 / #328) — mirrors its shape (pure compute, upsert-guarded shadow writer, never
raises, never mutates the caller's `r`).

PURPOSE (SHADOW ONLY — drives NOTHING). For each scored EP HIGH or MODERATE, compute — AS OF
strictly PRIOR to alert_date (no lookahead) — the structure the stock brought INTO the
catalyst day, per the ADR's signed 3-component table:

  (a) Stage-2 long-term trend — prior_close > 200-session SMA AND prior_close >= 75% of the
      trailing high. Mirrors `flag_detector.py`'s #356 HTF Stage-2 gate predicate EXACTLY
      (`_STAGE2_NEAR_HIGH_MIN`, `_SMA200_WINDOW`) — the NCI dead-cat lesson: short MAs catch
      up fast on a crash-recovery, so the long-term trend is the real filter. The trailing
      high is computed over WHATEVER history is loaded (no hard 252-bar floor) — this
      mirrors how flag_detector.py's OWN live gate actually computes it, and is also what the
      ADR 0016 STEP-0 calibration (docs/analysis/structure_axis_step0_2026-07-04.md) found to
      be the only adequately-powered read (N=386): the strict 252-session variant was
      coverage-starved (14%) given mi_daily_closes' ~13-month retained history.
  (b) Base tightness — RMV-15 (`flag_detector._compute_rmv`, the SSoT tightness primitive)
      over the prior ~15 sessions, compared against the ALREADY-ESTABLISHED "tight" cutline
      for this exact metric: `anticipation.ENTRY_RMV_MAX` (30.0, #327's signed-off
      rmv_15d<=30 "getting tight" gate — reused, not reinvented). NOTE (documented, not
      silently reconciled): the STEP-0 doc's own cross-tab used a cohort-median RMV cutline
      (~53.5) for its exploratory bucket split — a data-derived, cohort-relative number that
      can't serve a live per-ticker decision (it would drift with cohort composition day to
      day). ENTRY_RMV_MAX is the nearest EXISTING, already-signed, deterministic threshold on
      the same rmv_15d metric, so it is reused here as the live tightness cutline; a future
      data-sized pass (per #329's composition checkpoint) can re-tune it specifically for
      this axis if warranted — same "PROVISIONAL, calibratable" status ENTRY_RMV_MAX already
      carries in anticipation.py.
  (c) Extension state — prior_close / 10-session SMA (`parabolic_detector._sma`). TELEMETRY
      ONLY in v1: the ADR's own STEP-0 bucket spec cuts the cross-tab on Stage-2 x tightness
      only, and the ADR's "v1 mapping" paragraph names only those two in the credit decision
      — extension rides along in `axis_reads` for traceability/future calibration, exactly as
      STEP-0 disclosed ("not part of the bucket split... rides along as backfilled telemetry
      for the eventual shadow").

This module owns ONLY the pure compute (`compute_structure_features` /
`structure_axis_credit`) + the shadow-table writer (`log_structure_axis_shadow`). It reads
`conn` (read-only, via `get_daily_bars_asof`) and writes ONLY `mi_structure_axis_shadow` (+
`mi_audit_log` on failure). It never mutates trade state, never touches the live
grade/judge output (no import of anything from ep_detector's judge-building path), and never
raises into the caller — the writer swallows every error to an audit event, pure telemetry
throughout (mirrors theme_axis_shadow.py's discipline exactly).

Boost-only per the shared #328/6/5 guardrail: `structure_axis_credit` NEVER returns
`credit_steps < 0`. The Stage-2-only ("near-miss") bucket is recorded with its own marker
for visibility but is credited 0 in v1 — the STEP-0 SUPPLEMENTARY read (the only
adequately-powered variant, N=386) showed Stage2-only was NOT clearly better than no-Stage2
on win-rate (53% vs 56%); only Stage2+tight cleanly separated (64% vs 56%). This is a
documented v1 implementation call (the ADR names the "near-miss band" concept but not an
exact credited value for structure, unlike theme's Nascent near-miss which DOES carry +1 in
its own ADR) — flagged here for the record, not silently invented, mirroring the STEP-0
doc's own honesty-first disclosure style. Future calibration (#329 composition checkpoint)
may promote it once data supports it.
"""
from __future__ import annotations

import logging
from typing import Any

from agents.market_intelligence.anticipation import ENTRY_RMV_MAX
from agents.market_intelligence.db import get_daily_bars_asof, log_audit_event
from agents.market_intelligence.flag_detector import _compute_rmv
from agents.market_intelligence.parabolic_detector import _sma

logger = logging.getLogger(__name__)

# ── Thresholds — REUSED from existing, already-signed primitives (search-before-build) ─────
_SMA200_WINDOW = 200          # flag_detector.py's #356 Stage-2 long-term trend window
_SMA10_WINDOW = 10            # 9M detector's extension-gate MA (ninem_detector._MAX_EXTENSION_FROM_MA10)
_STAGE2_NEAR_HIGH_MIN = 0.75  # flag_detector.py's #356 Stage-2 gate — pole/prior_close >= 75% of the trailing high
_RMV_LOOKBACK = 15            # ADR 0016: "RMV over the prior ~15 sessions"
_TIGHT_RMV_MAX = ENTRY_RMV_MAX  # #327's signed-off rmv_15d "tight" cutline — reused, see module docstring (b)

# Allowed marker values (mirrors theme axis's pinned-vocabulary convention) — one of these
# EXACTLY, never a bespoke string:
#   'stage2_tight' | 'stage2_only_near_miss' | 'no_stage2' | 'unknown'


def compute_structure_features(bars: list[dict], alert_date: Any) -> dict[str, Any]:
    """AS-OF (strictly prior to alert_date) structure features from an ascending OHLCV bar
    list already filtered to trade_date < alert_date by the caller (`get_daily_bars_asof`) —
    `bars[-1]` is "today" (the prior close). Mirrors
    `scripts/probes/_330_structure_step0.py::compute_structure_features`'s relaxed
    (SUPPLEMENTARY) variant exactly on shape/thresholds — see module docstring (a) for why
    relaxed, not strict-252, is the live shape.

    Every field is None when not computable (insufficient history) — NEVER a guessed value.
    Returns: prior_close, stage2 (bool|None), sma_200, trailing_high, rmv_15, rmv_tight
    (bool|None), extension_ratio, sma_10.
    """
    out: dict[str, Any] = {
        "prior_close": None, "stage2": None, "sma_200": None, "trailing_high": None,
        "rmv_15": None, "rmv_tight": None, "extension_ratio": None, "sma_10": None,
    }
    if not bars:
        return out
    idx = len(bars) - 1
    prior_close = float(bars[idx]["close"])
    out["prior_close"] = prior_close

    sma_200 = _sma(bars, idx, _SMA200_WINDOW)
    highs = [float(b["high_price"]) for b in bars if b.get("high_price") is not None]
    hi = max(highs) if highs else None
    out["sma_200"] = sma_200
    out["trailing_high"] = hi
    if sma_200 is not None and hi:
        out["stage2"] = (prior_close > sma_200) and (prior_close >= _STAGE2_NEAR_HIGH_MIN * hi)

    if idx >= _RMV_LOOKBACK:
        rmv = _compute_rmv(bars, idx, lookback=_RMV_LOOKBACK)
        out["rmv_15"] = rmv
        if rmv is not None:
            out["rmv_tight"] = rmv <= _TIGHT_RMV_MAX

    sma_10 = _sma(bars, idx, _SMA10_WINDOW)
    out["sma_10"] = sma_10
    if sma_10:
        out["extension_ratio"] = prior_close / sma_10

    return out


def structure_axis_credit(features: dict[str, Any]) -> dict[str, Any]:
    """ADR 0016 (#330) v1 stage2 x tightness -> credit decision — PURE, BOOST-ONLY, SHADOW
    ONLY. Mirrors `catalyst_rubric_runtime.theme_axis_credit`'s return shape
    ({credit_steps, marker, reason}) — the ADR 0015 sibling pattern.

    v1 mapping (ADR 0016, literal): "Stage-2 + tight base = +1 tier-step eligibility;
    partial (Stage-2 only) = near-miss band; absent/unknown = 0, never negative."
    `features['extension_ratio']` is TELEMETRY ONLY in v1 (see module docstring (c)) — it
    does not affect credit_steps; it is still recorded on the shadow row for traceability.

    NEVER returns credit_steps < 0 — boost-only is a hard guardrail (shared #328 6/5
    evidence: a naive structure-GATE would risk the same false-negative class the theme gate
    was refuted for; this axis can only ADD conviction).
    """
    stage2 = features.get("stage2")
    rmv_tight = features.get("rmv_tight")

    if stage2 is None:
        return {
            "credit_steps": 0,
            "marker": "unknown",
            "reason": (
                "Stage-2 not computable (insufficient prior daily-close history for the "
                "200d SMA / trailing high) — zero credit (safe default, never guesses a boost)"
            ),
        }
    if stage2 is True:
        if rmv_tight is True:
            return {
                "credit_steps": 1,
                "marker": "stage2_tight",
                "reason": (
                    "Stage-2 long-term trend (prior_close > 200d SMA AND within 25% of the "
                    f"trailing high) AND tight base (RMV-15 <= {_TIGHT_RMV_MAX:.0f}) — "
                    "+1 tier-step (ADR 0016 full boost)"
                ),
            }
        return {
            "credit_steps": 0,
            "marker": "stage2_only_near_miss",
            "reason": (
                "Stage-2 long-term trend present but the base is not tight "
                f"(RMV-15 above {_TIGHT_RMV_MAX:.0f}, or unknown) — near-miss band, no credit "
                "yet (ADR 0016 STEP-0: Stage2-only was not clearly better than no-Stage2 on "
                "win-rate at the only adequately-powered N)"
            ),
        }
    return {
        "credit_steps": 0,
        "marker": "no_stage2",
        "reason": (
            "Not a Stage-2 long-term trend (prior_close below the 200d SMA, or more than "
            "25% off the trailing high) — zero credit, never a penalty"
        ),
    }


async def log_structure_axis_shadow(conn: Any, r: dict[str, Any]) -> None:
    """SHADOW writer (#330 shadow build, ADR 0016). For one scored EP candidate, compute the
    3 AS-OF structure components + the boost-only credit decision and upsert to
    `mi_structure_axis_shadow`. Upserts latest-scan-wins (the EP scan re-runs every 5 min) —
    mirrors `theme_axis_shadow.log_theme_axis_shadow`'s STEP-0 writer discipline exactly
    (idempotent on (ticker, alert_date), no additional dedupe guard needed since the upsert
    itself collapses re-runs). NEVER raises — every error is swallowed to an audit event so a
    telemetry failure can't disturb the grade path.

    Caller gates on whatever final, post-override score_tier it settled on (this function is
    tier-agnostic — logs whatever grade it's handed, like its theme-axis sibling). Read-only
    on `r` — never mutates it or any grade column (THE LINE).
    """
    try:
        ticker = r.get("ticker")
        alert_date = r.get("alert_date")
        if not ticker or not alert_date:
            return
        grade = r.get("score_tier")

        bars = await get_daily_bars_asof(conn, ticker, alert_date)
        feats = compute_structure_features(bars, alert_date)
        credit = structure_axis_credit(feats)

        await conn.execute("""
            INSERT INTO mi_structure_axis_shadow (
                ticker, alert_date, grade, prior_close, stage2, sma_200, trailing_high,
                rmv_15, rmv_tight, extension_ratio, sma_10, credit_steps, marker, reason
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
            ON CONFLICT (ticker, alert_date) DO UPDATE SET
                grade = EXCLUDED.grade,
                prior_close = EXCLUDED.prior_close,
                stage2 = EXCLUDED.stage2,
                sma_200 = EXCLUDED.sma_200,
                trailing_high = EXCLUDED.trailing_high,
                rmv_15 = EXCLUDED.rmv_15,
                rmv_tight = EXCLUDED.rmv_tight,
                extension_ratio = EXCLUDED.extension_ratio,
                sma_10 = EXCLUDED.sma_10,
                credit_steps = EXCLUDED.credit_steps,
                marker = EXCLUDED.marker,
                reason = EXCLUDED.reason,
                created_at = NOW()
        """, ticker, alert_date, grade, feats["prior_close"], feats["stage2"], feats["sma_200"],
             feats["trailing_high"], feats["rmv_15"], feats["rmv_tight"],
             feats["extension_ratio"], feats["sma_10"],
             credit["credit_steps"], credit["marker"], credit["reason"])
    except Exception as _e:  # SHADOW: never disturb the grade path
        logger.warning(f"structure-axis shadow log failed for {r.get('ticker')}: {_e}")
        try:
            await log_audit_event(
                "structure_axis_shadow_failed",
                f"{r.get('ticker')} {r.get('alert_date')}: {type(_e).__name__}: {_e}",
            )
        except Exception:  # loud-ok: fallback-of-the-fallback — the audit call itself
            pass            # may share the same DB outage; already logger.warning'd
                             # above; nothing more can be done and the scan must
                             # still proceed (SHADOW). Mirrors catalyst_rubric_runtime
                             # .log_theme_axis_adjusted_shadow's identical inner guard.
