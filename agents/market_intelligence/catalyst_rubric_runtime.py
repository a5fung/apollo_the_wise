"""Runtime adapter wiring the 6-axis catalyst rubric into ep_detector.

Bridges the fresh multi-source extraction (mi_ep_catalyst_metrics) into
the rubric scorer's expected input shape (deltas + beat + guidance dicts).

Hybrid sourcing (intentional, named in function for honesty):
- q0 (latest quarter, just-announced): FROM fresh extraction. Catalyst-day
  data that yfinance lags by 24-72h.
- q1, q2, q3 (older quarters): from yfinance (settled data, reliable).
- margins: from yfinance (settled, reliable).
- beat: from fresh extraction's q_eps.beat_vs_est_pct (revenue beat not
  yet in extraction schema — would need prompt update for full Axis 4
  coverage; current state scores Axis 4 as None when rev_beat missing).
- guidance: from fresh extraction's guidance_fy_revenue_usd.midpoint_yoy_pct.

Failure modes (per advisor 2026-05-19 plan):
- Both succeed: full 6-axis rubric runs, gate on composite_scaled
- Fresh OK + yfinance fails: rubric runs on q0-only data (accel-unknown
  branches in rubric handle this). Composite scaled by available axes.
- Fresh fails: caller's safety-net Q-rev threshold gate takes over.

The gate is composite-based (CATALYST_RUBRIC_MIN_COMPOSITE, env-tunable).
Labels are calibrated against operator labels from the weekend's labeling
work — fixtures may need re-validation post-ship.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


def _extracted_to_q0_deltas(extracted: dict[str, Any]) -> dict[str, Any]:
    """Convert mi_ep_catalyst_metrics extraction to rubric's q0 deltas.

    Extraction stores yoy_pct as PERCENT (11.7 = 11.7%). Rubric expects
    FRACTION (0.117). Convert here.

    Sources the q0 margins block from extraction's q_margins (already in
    decimal fraction form per the prompt schema).
    """
    deltas: dict[str, Any] = {
        "rev_yoy_q0": None,
        "rev_yoy_q1": None, "rev_yoy_q2": None, "rev_yoy_q3": None,
        "eps_yoy_q0": None,
        "eps_yoy_q1": None, "eps_yoy_q2": None,
        "rev_qoq_q0": None,
        "rev_accel": None, "rev_accel_streak": 0,
        "eps_accel": None,
        "rev_yoy_max_prior_7q": None,
        "eps_qm4": None,
        "margins_q0": {}, "margins_q1": {}, "margins_q2": {},
        "data_quality_flag": "fresh_q0_only",
    }
    qr = extracted.get("q_revenue_usd") or {}
    if isinstance(qr, dict):
        yoy = qr.get("yoy_pct")
        if isinstance(yoy, (int, float)):
            deltas["rev_yoy_q0"] = yoy / 100.0

    qe = extracted.get("q_eps") or {}
    if isinstance(qe, dict):
        yoy = qe.get("yoy_pct")
        if isinstance(yoy, (int, float)):
            deltas["eps_yoy_q0"] = yoy / 100.0

    # q0 margins from extraction (prompt returns decimal fractions 0-1).
    # Filter out None entries to keep the dict clean for Axis 3 scoring.
    qm = extracted.get("q_margins") or {}
    if isinstance(qm, dict):
        m0 = {}
        for k in ("gross_margin", "op_margin", "net_margin"):
            v = qm.get(k)
            if isinstance(v, (int, float)):
                m0[k] = float(v)
        if m0:
            deltas["margins_q0"] = m0
    return deltas


def _augment_with_yfinance_historical(ticker: str, deltas: dict[str, Any]) -> dict[str, Any]:
    """Best-effort augmentation: pull yfinance quarterlies for older quarters.

    yfinance lags announcements by 24-72h, so its latest row is q1 (the
    quarter BEFORE the just-announced one). We use yfinance rows for
    q1/q2/q3 YoY + margins. If yfinance is fresh enough that q0 is
    available there too, we ignore it — extraction is authoritative for q0.

    Failure: returns deltas unchanged (rubric handles missing axes).
    """
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        qf = t.quarterly_financials
        if qf is None or qf.empty:
            return deltas

        # quarterly_financials returns most-recent-first columns
        cols = list(qf.columns)
        if len(cols) < 5:
            return deltas

        # yfinance line names use SPACES ("Total Revenue" not "TotalRevenue") —
        # debugged 2026-05-19 for AGYS. Both forms tried for cross-version
        # compatibility, but space-form is the modern shape.
        rev_row = None
        for line in ("Total Revenue", "Revenue", "Operating Revenue",
                     "TotalRevenue", "OperatingRevenue"):
            if line in qf.index:
                rev_row = qf.loc[line]
                break
        if rev_row is None:
            return deltas

        # The most-recent yfinance column may or may not be q0. If announced
        # within the last 48h, it likely hasn't been picked up yet — yfinance
        # row 0 = q1 from our perspective. If announced longer ago, yfinance
        # may have it. We're conservative: use yfinance rows for q1+ only
        # (skip index 0 to be safe; treat row 0 as q1).
        # YoY math: row[i] vs row[i+4] (same fiscal quarter year ago).
        def _yoy(i: int) -> float | None:
            if i + 4 >= len(cols):
                return None
            new = rev_row.iloc[i]
            old = rev_row.iloc[i + 4]
            if new and old and old > 0:
                return (new - old) / old
            return None

        deltas["rev_yoy_q1"] = _yoy(0)  # yfinance row 0 = q1 (last quarter)
        deltas["rev_yoy_q2"] = _yoy(1)
        deltas["rev_yoy_q3"] = _yoy(2)

        # Acceleration: q0 (from extraction) vs q1 (from yfinance)
        if deltas["rev_yoy_q0"] is not None and deltas["rev_yoy_q1"] is not None:
            deltas["rev_accel"] = deltas["rev_yoy_q0"] - deltas["rev_yoy_q1"]

        # prior_max for milestone axis (use yfinance q1-q7 since q0 is the catalyst)
        prior_yoys = []
        for i in range(0, min(7, len(cols) - 4)):
            v = _yoy(i)
            if v is not None:
                prior_yoys.append(v)
        if prior_yoys:
            deltas["rev_yoy_max_prior_7q"] = max(prior_yoys)

        # Margins from yfinance (gross/op/net). yfinance line names use
        # spaces ("Gross Profit"). Try modern form first, fall back to
        # concatenated for older yfinance versions.
        def _safe_div_any(num_lines: tuple[str, ...], den_lines: tuple[str, ...], idx: int) -> float | None:
            try:
                num_val = None
                for ln in num_lines:
                    if ln in qf.index:
                        num_val = qf.loc[ln].iloc[idx]
                        break
                den_val = None
                for ln in den_lines:
                    if ln in qf.index:
                        den_val = qf.loc[ln].iloc[idx]
                        break
                if num_val is not None and den_val and den_val > 0:
                    return float(num_val) / float(den_val)
            except Exception:
                return None
            return None

        # yfinance shape for AGYS Q3 FY26 (confirmed 2026-05-19):
        #   Gross Profit / Total Revenue → ~62%
        #   Operating Income / Total Revenue → ~14%
        #   Net Income / Total Revenue → ~12%
        _rev_lines = ("Total Revenue", "TotalRevenue", "Operating Revenue")
        _gp_lines = ("Gross Profit", "GrossProfit")
        _oi_lines = ("Operating Income", "OperatingIncome")
        _ni_lines = ("Net Income", "NetIncome", "Net Income Common Stockholders")

        # margins_q1 / q2 = the 2 most-recent yfinance quarters (which are
        # q1, q2 from our perspective since q0 is the just-announced
        # catalyst not yet in yfinance). The rubric's score_axis_3 will
        # use these to compute QoQ deltas.
        for q_key, idx in (("margins_q1", 0), ("margins_q2", 1)):
            deltas[q_key] = {
                "gross_margin": _safe_div_any(_gp_lines, _rev_lines, idx),
                "op_margin": _safe_div_any(_oi_lines, _rev_lines, idx),
                "net_margin": _safe_div_any(_ni_lines, _rev_lines, idx),
            }
        # margins_q0 (just-announced quarter) deliberately left EMPTY here —
        # would lie to the rubric about margin acceleration if we copied q1
        # values. Extraction prompt is being expanded to capture margin
        # numbers from the press release directly; when present, set this
        # from `extracted["q_margins"]` in _extracted_to_q0_deltas.
        # Rubric handles missing margins_q0 gracefully (Axis 3 returns
        # score=None → composite_scaled shrinks max_available).

        deltas["data_quality_flag"] = "fresh_q0_plus_yfinance_historical"

    except Exception as e:
        logger.warning(f"yfinance augmentation failed for {ticker}: {e}")
    return deltas


def _extracted_to_beat(extracted: dict[str, Any]) -> dict[str, Any] | None:
    """Build the beat dict for Axis 4 from extraction.

    Both q_revenue.beat_vs_est_pct and q_eps.beat_vs_est_pct are now captured
    by the expanded extraction prompt (2026-05-19). Return None if BOTH are
    missing; rubric returns 'partial_consensus_data' (score=None) if only
    one is present.
    """
    qr = extracted.get("q_revenue_usd") or {}
    qe = extracted.get("q_eps") or {}
    rev_beat = qr.get("beat_vs_est_pct") if isinstance(qr, dict) else None
    eps_beat = qe.get("beat_vs_est_pct") if isinstance(qe, dict) else None
    if rev_beat is None and eps_beat is None:
        return None
    return {
        "rev_beat_pct": rev_beat / 100.0 if isinstance(rev_beat, (int, float)) else None,
        "eps_beat_pct": eps_beat / 100.0 if isinstance(eps_beat, (int, float)) else None,
    }


def _extracted_to_guidance(extracted: dict[str, Any]) -> dict[str, Any] | None:
    """Build the guidance dict for Axis 5 from extraction.

    Primary source: extracted["guidance_change"] (new 2026-05-19 field with
    explicit direction + raise_pct_vs_consensus).

    Fallback: extracted["guidance_fy_revenue_usd"].midpoint_yoy_pct as a
    proxy when guidance_change is missing but FY guidance midpoint is.
    """
    gc = extracted.get("guidance_change")
    if isinstance(gc, dict) and gc.get("direction"):
        direction = gc.get("direction")
        raise_pct = gc.get("raise_pct_vs_consensus")
        return {
            "direction": direction,
            "raise_pct_vs_consensus": (
                raise_pct / 100.0
                if isinstance(raise_pct, (int, float))
                else None
            ),
        }

    # Fallback to midpoint_yoy_pct proxy
    gf = extracted.get("guidance_fy_revenue_usd")
    if not isinstance(gf, dict):
        return None
    midpoint_yoy = gf.get("midpoint_yoy_pct")
    if not isinstance(midpoint_yoy, (int, float)):
        return None
    direction = "raised" if midpoint_yoy > 0 else "lowered"
    return {
        "direction": direction,
        "raise_pct_vs_consensus": midpoint_yoy / 100.0 if midpoint_yoy > 0 else None,
    }


def build_rubric_inputs_hybrid(
    ticker: str,
    extracted: dict[str, Any],
    today: date,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    """Build (fund, beat, guidance) inputs for catalyst_rubric.score_ticker.

    Honestly-named hybrid: q0 from fresh extraction, q1+ and margins from
    yfinance. See module docstring for rationale.
    """
    deltas = _extracted_to_q0_deltas(extracted)
    deltas = _augment_with_yfinance_historical(ticker, deltas)

    fund = {
        "ticker": ticker,
        "deltas": deltas,
        "source_chain": "extraction_q0+yfinance_historical",
        "n_quarters_with_revenue": (
            4 if deltas.get("rev_yoy_q3") is not None
            else 3 if deltas.get("rev_yoy_q2") is not None
            else 2 if deltas.get("rev_yoy_q1") is not None
            else 1 if deltas.get("rev_yoy_q0") is not None
            else 0
        ),
    }
    beat = _extracted_to_beat(extracted)
    guidance = _extracted_to_guidance(extracted)
    return fund, beat, guidance


def score_ep_with_rubric(
    ticker: str,
    extracted: dict[str, Any],
    today: date,
) -> dict[str, Any] | None:
    """Run the 6-axis rubric on the fresh-extracted catalyst.

    Returns the rubric output dict (composite_raw, composite_scaled,
    max_available, label, caps_applied, per-axis details) OR None if
    inputs can't be built (no q_revenue_yoy_pct extracted).
    """
    qr = extracted.get("q_revenue_usd")
    if not isinstance(qr, dict) or qr.get("yoy_pct") is None:
        # Can't score without q0 revenue YoY
        return None
    try:
        from agents.market_intelligence.catalyst_rubric import score_ticker
        fund, beat, guidance = build_rubric_inputs_hybrid(ticker, extracted, today)
        return score_ticker(fund, beat=beat, guidance=guidance)
    except Exception as e:
        logger.warning(f"Rubric scoring failed for {ticker}: {e}")
        return None
