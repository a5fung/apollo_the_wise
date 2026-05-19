"""EP Selectivity catalyst rubric — RUNTIME (2026-05-19).

Pure scoring functions used by `catalyst_rubric_runtime.py` to gate
earnings-day EP catalysts. Originally `scripts/score_catalyst_rubric.py`
for offline analysis; moved to runtime location when wired into
ep_detector.py. CLI/main logic for offline backtests + fixture
verification remains in `scripts/score_catalyst_rubric.py` (which
should be updated to re-import from here in a followup).

Integration shape:
  fund_dict = build_rubric_inputs_hybrid(ticker, extracted_metrics, today)
  result = score_ticker(fund_dict, beat=..., guidance=...)
  → result["composite_scaled"] (0-39); < CATALYST_RUBRIC_MIN_COMPOSITE → downgrade
  → result["label"] in {game_changer, strong, routine_correct, weak}

============================================================================

ORIGINAL DOCSTRING (offline mode):

EP Selectivity Phase 1 — Block C — Catalyst rubric scorer.

Reads per-ticker fundamentals JSON from analysis/2026-05-16/fundamentals/
and applies the 6-axis rubric per design doc.

Weighting (Gemini-locked 2026-05-16):
  Axis 1 (Revenue) × 2
  Axis 2 (EPS) × 1 (manipulable; not load-bearing)
  Axis 3 (Margin) × 1
  Axis 4 (Beat) × 1
  Axis 5 (Guidance) × 2  (institutional repositioning trigger)
  Axis 6 (Milestone bonus) × 1 (max +4 bonus)
  Max composite = 39

Hard caps:
  1. growth_milestone=False AND rev_yoy_q0 < 25% → cap at 'strong'
  2. Axis 1 score = 0 (rev contracting) → cap at 'routine_correct'
  3. Axis 3 score = 0 (all margins contracting) → cap at 'routine_correct'
  4. Axis 5 score = 0 (guidance LOWERED, not missing) → cap at 'routine_correct'

Missing-data: scale composite by axes available.
  composite_scaled = sum_available × 39 / max_available

Output:
  analysis/2026-05-16/catalyst_rubric_scores.csv
  analysis/2026-05-16/catalyst_rubric_verification.md

Run on prod (or locally; reads JSON files):
  docker exec apollo-market python -m scripts.score_catalyst_rubric
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path("analysis/2026-05-16")
FUND_DIR = DATA_DIR / "fundamentals"
OUT_CSV = DATA_DIR / "catalyst_rubric_scores.csv"
OUT_MD = DATA_DIR / "catalyst_rubric_verification.md"

# Axis max scores (per axis, before 2x weights)
AXIS_MAX = {"a1": 5, "a2": 5, "a3": 5, "a4": 5, "a5": 5, "a6": 4}
AXIS_WEIGHT = {"a1": 2, "a2": 1, "a3": 1, "a4": 1, "a5": 2, "a6": 1}
MAX_COMPOSITE = sum(AXIS_MAX[k] * AXIS_WEIGHT[k] for k in AXIS_MAX)  # = 39

LABEL_BANDS = [
    (30, "game_changer"),
    (22, "strong"),
    (14, "routine_correct"),
    (0, "weak"),
]


def score_axis_1_revenue(deltas: dict) -> dict:
    """Axis 1 — Revenue trajectory (0-5)."""
    yoy = deltas.get("rev_yoy_q0")
    accel = deltas.get("rev_accel")
    if yoy is None:
        return {"score": None, "reason": "no_rev_yoy_data"}
    if yoy <= 0:
        return {"score": 0, "reason": f"contracting yoy={yoy:.1%}"}
    # Cases where accel is None (single-quarter data) — fall back to YoY-only
    if accel is None:
        if yoy >= 0.50:
            return {"score": 4, "reason": f"yoy={yoy:.1%} (accel unknown)"}
        if yoy >= 0.25:
            return {"score": 3, "reason": f"yoy={yoy:.1%} (accel unknown)"}
        if yoy >= 0.15:
            return {"score": 2, "reason": f"yoy={yoy:.1%} (accel unknown)"}
        if yoy >= 0.10:
            return {"score": 1, "reason": f"yoy={yoy:.1%} (accel unknown)"}
        return {"score": 1, "reason": f"yoy={yoy:.1%} (accel unknown)"}
    if yoy >= 0.50 and accel >= 0.10:
        return {"score": 5, "reason": f"yoy={yoy:.1%} accel={accel:+.1%}"}
    if yoy >= 0.25 and accel >= 0.05:
        return {"score": 4, "reason": f"yoy={yoy:.1%} accel={accel:+.1%}"}
    if yoy >= 0.15 and accel >= 0:
        return {"score": 3, "reason": f"yoy={yoy:.1%} accel={accel:+.1%}"}
    if yoy >= 0.10 and accel < 0:
        return {"score": 2, "reason": f"yoy={yoy:.1%} accel={accel:+.1%} decelerating"}
    if yoy > 0:
        return {"score": 1, "reason": f"yoy={yoy:.1%} (low growth)"}
    return {"score": 0, "reason": "fallthrough"}


def score_axis_2_eps(deltas: dict) -> dict:
    """Axis 2 — EPS trajectory (0-5) with small-base guardrail."""
    yoy = deltas.get("eps_yoy_q0")
    accel = deltas.get("eps_accel")
    qm4 = deltas.get("eps_qm4")
    small_base = qm4 is not None and abs(qm4) < 0.10

    if yoy is None:
        return {"score": None, "reason": "no_eps_data", "small_base_capped": False}

    if yoy < 0:
        return {"score": 0, "reason": f"eps_yoy={yoy:.1%}",
                "small_base_capped": False}

    if accel is None:
        # Fall back to YoY-only
        if yoy >= 1.00:
            score = 4
        elif yoy >= 0.50:
            score = 3
        elif yoy >= 0.25:
            score = 3
        elif yoy >= 0.15:
            score = 2
        else:
            score = 1
    else:
        if yoy >= 1.00 and accel >= 0.20:
            score = 5
        elif yoy >= 0.50 and accel >= 0.10:
            score = 4
        elif yoy >= 0.25 and accel >= 0:
            score = 3
        elif yoy >= 0.15 and accel < 0:
            score = 2
        elif yoy >= 0:
            score = 1
        else:
            score = 0

    # Small-base cap
    if small_base and score > 3:
        return {"score": 3, "reason": f"eps_yoy={yoy:.1%} small_base_capped (qm4={qm4:.3f})",
                "small_base_capped": True}
    return {"score": score, "reason": f"eps_yoy={yoy:.1%} accel={accel}",
            "small_base_capped": False}


def score_axis_3_margin(deltas: dict) -> dict:
    """Axis 3 — Margin trajectory (0-5). +100bps = expanding."""
    m0 = deltas.get("margins_q0", {}) or {}
    m1 = deltas.get("margins_q1", {}) or {}
    m2 = deltas.get("margins_q2", {}) or {}

    tiers = ["gross_margin", "op_margin", "net_margin"]
    deltas_qoq = {}
    for t in tiers:
        a = m0.get(t)
        b = m1.get(t)
        if a is not None and b is not None:
            deltas_qoq[t] = a - b
    if not deltas_qoq:
        return {"score": None, "reason": "no_margin_data"}

    expanding = sum(1 for d in deltas_qoq.values() if d >= 0.01)
    contracting = sum(1 for d in deltas_qoq.values() if d <= -0.01)
    flat = sum(1 for d in deltas_qoq.values() if abs(d) < 0.01)

    # 2-consecutive-quarter expansion check
    deltas_qoq_prior = {}
    for t in tiers:
        a = m1.get(t)
        b = m2.get(t)
        if a is not None and b is not None:
            deltas_qoq_prior[t] = a - b
    all_expanding_2q = (
        len(deltas_qoq) == 3 and
        all(d >= 0.01 for d in deltas_qoq.values()) and
        len(deltas_qoq_prior) == 3 and
        all(d >= 0.01 for d in deltas_qoq_prior.values())
    )

    if all_expanding_2q:
        return {"score": 5, "reason": "all 3 margins expanding ≥2 quarters"}
    if expanding >= 2 and m0.get("op_margin", 0) > m1.get("op_margin", -1):
        return {"score": 4, "reason": f"op+net expanding (qoq deltas {deltas_qoq})"}
    if expanding >= 1 and contracting == 0:
        return {"score": 3, "reason": f"{expanding} expanding, others flat"}
    if flat == len(deltas_qoq):
        return {"score": 2, "reason": "all margins flat"}
    if contracting >= len(deltas_qoq):
        return {"score": 0, "reason": "all margins contracting"}
    return {"score": 1, "reason": f"{contracting} contracting"}


def score_axis_4_beat(beat: dict | None) -> dict:
    """Axis 4 — Beat vs consensus. beat dict can be None (missing data)."""
    if not beat:
        return {"score": None, "reason": "no_consensus_data"}
    rev_beat = beat.get("rev_beat_pct")
    eps_beat = beat.get("eps_beat_pct")
    if rev_beat is None or eps_beat is None:
        return {"score": None, "reason": "partial_consensus_data"}
    if rev_beat >= 0.10 and eps_beat >= 0.30:
        return {"score": 5, "reason": f"rev={rev_beat:+.1%} eps={eps_beat:+.1%}"}
    if rev_beat >= 0.05 and eps_beat >= 0.15:
        return {"score": 4, "reason": f"rev={rev_beat:+.1%} eps={eps_beat:+.1%}"}
    if rev_beat >= 0.02 and eps_beat >= 0.05:
        return {"score": 3, "reason": f"rev={rev_beat:+.1%} eps={eps_beat:+.1%}"}
    if rev_beat < 0 or eps_beat < 0:
        return {"score": 0, "reason": f"miss rev={rev_beat:+.1%} eps={eps_beat:+.1%}"}
    if abs(rev_beat) < 0.02 and abs(eps_beat) < 0.02:
        return {"score": 1, "reason": "in-line"}
    return {"score": 2, "reason": "mixed"}


def score_axis_5_guidance(guidance: dict | None) -> dict:
    """Axis 5 — Guidance change. None = missing (≠ lowered)."""
    if not guidance:
        return {"score": None, "reason": "no_guidance_data"}
    raise_pct = guidance.get("raise_pct_vs_consensus")
    direction = guidance.get("direction")
    if direction == "lowered":
        return {"score": 0, "reason": "guidance lowered"}
    if direction == "raised":
        if raise_pct is None:
            return {"score": 3, "reason": "raised (magnitude unknown)"}
        if raise_pct >= 0.20:
            return {"score": 5, "reason": f"raised {raise_pct:+.1%}"}
        if raise_pct >= 0.10:
            return {"score": 4, "reason": f"raised {raise_pct:+.1%}"}
        if raise_pct >= 0.05:
            return {"score": 3, "reason": f"raised {raise_pct:+.1%}"}
        return {"score": 3, "reason": f"raised {raise_pct:+.1%} (small)"}
    if direction in ("reaffirmed", "unchanged"):
        return {"score": 2, "reason": "reaffirmed"}
    return {"score": None, "reason": f"unknown direction: {direction}"}


def score_axis_6_milestone(deltas: dict) -> dict:
    """Axis 6 — Magnitude inflection bonus (0-4 bonus points)."""
    flags = []
    score = 0

    # growth_milestone: crossed 25%/50%/100% by ≥5pp AND beat prior 7q max by ≥5pp
    rev_yoy = deltas.get("rev_yoy_q0")
    prior_max = deltas.get("rev_yoy_max_prior_7q")
    if rev_yoy is not None:
        for threshold in (0.25, 0.50, 1.00):
            if rev_yoy >= threshold + 0.05:
                if prior_max is None or prior_max < threshold + 0.05:
                    # Crossed for first time in available history
                    # Persistence buffer: also require prior_max not yet at this level
                    if prior_max is None or rev_yoy - prior_max >= 0.05:
                        flags.append(f"growth_milestone_{int(threshold * 100)}%")
                        score += 1
                        break  # only credit highest milestone once
    # sustained_acceleration: rev_accel_streak ≥ 3
    streak = deltas.get("rev_accel_streak", 0) or 0
    if streak >= 3:
        flags.append("sustained_acceleration")
        score += 1

    # first_profitable_quarter: q0 EPS positive, q-4 EPS negative
    eps_q0 = (deltas.get("eps_yoy_q0") is not None and
              deltas.get("eps_qm4") is not None and
              deltas.get("eps_qm4") < 0)
    # need to check if q0 actually positive too; we have eps_yoy_q0 ratio
    # but not q0 itself. Approximate: yoy growth + qm4 negative implies q0 positive
    # if yoy >= 1 (50%+ growth from negative base)
    if deltas.get("eps_qm4") is not None and deltas["eps_qm4"] < 0:
        yoy = deltas.get("eps_yoy_q0")
        if yoy is not None and yoy > 0:
            # eps_q0 = (1 + yoy) * eps_qm4. If yoy > 1, q0 might be positive
            # only if eps_qm4 was small negative
            # Approximate flag — leave detail to manual review
            flags.append("first_profitable_quarter_candidate")
            score += 1

    # structural_inflection from headline — skip (LLM required, optional)
    return {"score": min(score, 4), "reason": ",".join(flags) or "none"}


def composite_with_scaling(axes: dict, raw_axis_scores: dict) -> dict:
    """Apply weights + missing-data scaling. Returns composite,
    composite_scaled, label, hard_caps_applied."""
    available_keys = [k for k, v in raw_axis_scores.items() if v is not None]
    if not available_keys:
        return {
            "composite_raw": 0, "composite_scaled": 0,
            "max_available": 0, "label": "weak",
            "caps_applied": [],
        }

    weighted_sum = sum(
        raw_axis_scores[k] * AXIS_WEIGHT[k]
        for k in available_keys
    )
    max_available = sum(
        AXIS_MAX[k] * AXIS_WEIGHT[k]
        for k in available_keys
    )
    composite_raw = weighted_sum
    composite_scaled = weighted_sum * MAX_COMPOSITE / max(1, max_available)

    # Hard caps
    caps = []
    if raw_axis_scores.get("a1") == 0:
        caps.append("rev_contracting")
    if raw_axis_scores.get("a3") == 0:
        caps.append("all_margins_contracting")
    if raw_axis_scores.get("a5") == 0:
        caps.append("guidance_lowered")
    has_milestone = "growth_milestone" in (axes.get("a6", {}).get("reason") or "")
    rev_yoy = axes.get("_deltas", {}).get("rev_yoy_q0")
    if not has_milestone and (rev_yoy is None or rev_yoy < 0.25):
        caps.append("no_milestone_low_growth")

    # Apply caps to label band
    label = None
    for band_min, band_label in LABEL_BANDS:
        if composite_scaled >= band_min:
            label = band_label
            break
    if label is None:
        label = "weak"

    # Caps that floor to routine_correct
    routine_caps = {"rev_contracting", "all_margins_contracting", "guidance_lowered"}
    if any(c in routine_caps for c in caps):
        if label in ("game_changer", "strong"):
            label = "routine_correct"
    # Cap that floors to strong
    if "no_milestone_low_growth" in caps and label == "game_changer":
        label = "strong"

    return {
        "composite_raw": round(composite_raw, 2),
        "composite_scaled": round(composite_scaled, 2),
        "max_available": max_available,
        "label": label,
        "caps_applied": caps,
    }


def score_ticker(fund: dict, beat: dict | None = None,
                 guidance: dict | None = None) -> dict:
    """Score one ticker. `beat` and `guidance` are optional dicts
    that, when missing, leave Axes 4 and 5 unscored (None)."""
    deltas = fund.get("deltas", {})
    a1 = score_axis_1_revenue(deltas)
    a2 = score_axis_2_eps(deltas)
    a3 = score_axis_3_margin(deltas)
    a4 = score_axis_4_beat(beat)
    a5 = score_axis_5_guidance(guidance)
    a6 = score_axis_6_milestone(deltas)

    raw_axis_scores = {
        "a1": a1["score"], "a2": a2["score"], "a3": a3["score"],
        "a4": a4["score"], "a5": a5["score"], "a6": a6["score"],
    }
    composite = composite_with_scaling(
        {"a1": a1, "a2": a2, "a3": a3, "a4": a4, "a5": a5, "a6": a6,
         "_deltas": deltas},
        raw_axis_scores,
    )
    return {
        "ticker": fund.get("ticker"),
        "source_chain": fund.get("source_chain"),
        "n_quarters": fund.get("n_quarters_with_revenue"),
        **{f"a1_{k}": v for k, v in a1.items()},
        **{f"a2_{k}": v for k, v in a2.items()},
        **{f"a3_{k}": v for k, v in a3.items()},
        **{f"a4_{k}": v for k, v in a4.items()},
        **{f"a5_{k}": v for k, v in a5.items()},
        **{f"a6_{k}": v for k, v in a6.items()},
        **composite,
    }


# Expected fixture labels (per design doc)
FIXTURES = {
    "NBIS": "game_changer",
    "CSCO": "routine_correct",
    "KLAR": "routine_correct",
    "TRT": "strong",     # delayed-EP, real catalyst
    "ONDS": "strong",    # moved on real catalyst even if filtered
    "CPA": "strong",     # we expect at least strong; actual cohort label tbd
}


def main() -> None:
    rows = []
    for path in sorted(FUND_DIR.glob("*.json")):
        try:
            fund = json.loads(path.read_text())
        except Exception as e:
            logger.warning("failed to read %s: %s", path, e)
            continue
        # For now Axes 4-5 are unscored (no consensus data fetched yet)
        # Phase 1 deliverable; Axes 1-3 + 6 prove the rubric shape
        score = score_ticker(fund, beat=None, guidance=None)
        rows.append(score)

    if not rows:
        logger.warning("no fundamentals files found in %s", FUND_DIR)
        return

    # Write CSV
    cols = list(rows[0].keys())
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            # Convert lists/dicts to strings for CSV
            row_out = {k: (str(v) if isinstance(v, (list, dict)) else v)
                       for k, v in r.items()}
            w.writerow(row_out)
    logger.info("wrote %s (%d rows)", OUT_CSV, len(rows))

    # Verification md
    fixture_rows = {r["ticker"]: r for r in rows if r["ticker"] in FIXTURES}

    lines = [
        "# Catalyst rubric — Phase 1 verification",
        "",
        f"_Applied to {len(rows)} tickers. Axes 1-3 + 6 scored "
        f"(structured financials); Axes 4-5 still unscored (consensus "
        f"+ guidance data not fetched yet — future work)._",
        "",
        "## Fixture verification",
        "",
        "| Ticker | Expected | Got | Composite (scaled) | Match | Caps |",
        "|---|---|---|---:|:---:|---|",
    ]
    for ticker, expected in FIXTURES.items():
        if ticker not in fixture_rows:
            lines.append(f"| {ticker} | {expected} | NOT_FETCHED | — | ✗ | — |")
            continue
        r = fixture_rows[ticker]
        match = "✓" if r["label"] == expected else "✗"
        caps = ",".join(r["caps_applied"]) or "—"
        lines.append(
            f"| {ticker} | {expected} | {r['label']} | "
            f"{r['composite_scaled']} / 39 | {match} | {caps} |"
        )
    lines.append("")

    # Label distribution
    from collections import Counter
    label_dist = Counter(r["label"] for r in rows)
    lines.append("## Label distribution across sample")
    lines.append("")
    lines.append("| Label | N | Share |")
    lines.append("|---|---:|---:|")
    for label in ["game_changer", "strong", "routine_correct", "weak"]:
        n = label_dist.get(label, 0)
        lines.append(f"| {label} | {n} | {n / len(rows) * 100:.1f}% |")
    lines.append("")

    # Top scorers
    lines.append("## Top 15 by composite score")
    lines.append("")
    lines.append("| Ticker | Label | Composite | A1 | A2 | A3 | A6 | "
                 "n_quarters | source |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---|")
    sorted_rows = sorted(rows, key=lambda r: -(r["composite_scaled"] or 0))
    for r in sorted_rows[:15]:
        lines.append(
            f"| {r['ticker']} | {r['label']} | {r['composite_scaled']} | "
            f"{r.get('a1_score')} | {r.get('a2_score')} | "
            f"{r.get('a3_score')} | {r.get('a6_score')} | "
            f"{r['n_quarters']} | "
            f"{(r.get('source_chain') or ['?'])[0] if isinstance(r.get('source_chain'), list) else r.get('source_chain')} |"
        )
    lines.append("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    logger.info("wrote %s", OUT_MD)


if __name__ == "__main__":
    main()
