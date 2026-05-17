"""EP Selectivity Phase 1 — Theme Context input (meta-rubric component).

PROTOTYPE — not a production filter. Scores theme context as a separate
input to the meta-rubric per user 2026-05-16 architecture lock:

    catalyst_rubric_score → fundamentals_grade ┐
    theme_context_score                       ─┼→ meta_rubric → final EP
    technical_structure_score (future)        ─┤
    gap_alignment_score (future)              ─┘

This script computes a theme_context_score (0-10) per labeled alert
based on:
  - In-theme vs uncovered (5 points)
  - Theme stage (Accelerating > Mainstream > Nascent > Fading)
  - Theme size proxy (number of co-members at alert_date)

Output:
  analysis/2026-05-16/theme_context_scores.csv
  analysis/2026-05-16/theme_context_validation.md

Empirical anchor (Block 2 + catalyst-label crosstab §4):
  - in-theme alerts have +27pp WR over uncovered
  - operator-strong: 30% in-theme
  - operator-routine_mislabeled: 7.1% in-theme
  - theme heat is the load-bearing meta-rubric input

Phase 2 idea (NOT shipped here): wire `theme_context_score` into the
audit trail alongside `catalyst_rubric_score`, accumulate paired
outcomes, then build a learned meta-classifier on top.
"""
from __future__ import annotations

import csv
import json
import logging
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path("analysis/2026-05-16")
LABELS_CSV = DATA_DIR / "catalyst_labels.csv"
COHORT_CSV = DATA_DIR / "ep_cohort_alerts_60d.csv"
OUT_CSV = DATA_DIR / "theme_context_scores.csv"
OUT_MD = DATA_DIR / "theme_context_validation.md"

# Theme stage → score (0-3)
STAGE_SCORE = {
    "Accelerating": 3,
    "Mainstream": 2,
    "Nascent": 1,
    "Fading": 0,
    "Retired": 0,
}


def num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def score_theme_context(in_theme: bool, theme_stage: str | None,
                         theme_size: int | None) -> tuple[int, dict]:
    """Returns (score 0-10, breakdown dict).

    Decomposition:
      - Membership bonus: +5 if in_theme, else 0
      - Stage bonus: +0-3 (Accelerating=3 → Fading=0)
      - Size bonus: +0-2 (3+ co-members=2, 2=1, 1=0, uncovered=0)
    """
    breakdown = {
        "membership": 5 if in_theme else 0,
        "stage": STAGE_SCORE.get(theme_stage or "", 0) if in_theme else 0,
        "size": 0,
    }
    if in_theme and theme_size is not None:
        if theme_size >= 3:
            breakdown["size"] = 2
        elif theme_size >= 2:
            breakdown["size"] = 1
    return sum(breakdown.values()), breakdown


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def derive_outcome(row: dict) -> tuple[str, float | None]:
    if row.get("trade_id") and row.get("trade_status") == "closed":
        pnl = num(row.get("total_pnl"))
        entry_px = num(row.get("entry_price"))
        shares = num(row.get("entry_shares"))
        if pnl is not None and entry_px and shares:
            return ("win" if pnl > 0 else "loss", pnl / (entry_px * shares))
        if pnl is not None:
            return ("win" if pnl > 0 else "loss", None)
    r5 = num(row.get("ret_5d"))
    if r5 is not None:
        return ("win" if r5 > 0.05 else "loss", r5)
    fwd = num(row.get("fwd_5d_pct"))
    if fwd is not None:
        return ("win" if fwd / 100.0 > 0.05 else "loss", fwd / 100.0)
    return ("pending", None)


def fmt_pct(v):
    return f"{v * 100:+.1f}%" if v is not None else "—"


def main() -> None:
    labels = load_rows(LABELS_CSV)
    cohort = load_rows(COHORT_CSV)
    cohort_idx = {(r["ticker"], r["alert_date"]): r for r in cohort}

    # For "theme size" we'd need to count theme members. Cohort CSV
    # already carries theme_name (via the lateral subquery). Build a
    # quick per-theme member-counter from cohort itself; this is a
    # rough proxy — production version would query mi_themes directly.
    theme_member_counts = Counter()
    for c in cohort:
        if c.get("theme_name"):
            theme_member_counts[c["theme_name"]] += 1

    enriched = []
    for lbl in labels:
        if not lbl.get("user_label", "").strip():
            continue
        key = (lbl["ticker"], lbl["alert_date"])
        cohort_row = cohort_idx.get(key, {})
        theme_name = cohort_row.get("theme_name") or ""
        theme_stage = cohort_row.get("theme_stage") or ""
        in_theme = bool(theme_name)
        theme_size = theme_member_counts.get(theme_name, 0) if theme_name else 0

        score, breakdown = score_theme_context(in_theme, theme_stage, theme_size)
        outcome, ret = derive_outcome(cohort_row)

        enriched.append({
            "ticker": lbl["ticker"],
            "alert_date": lbl["alert_date"],
            "user_label": lbl["user_label"].strip(),
            "in_theme": in_theme,
            "theme_name": theme_name,
            "theme_stage": theme_stage,
            "theme_size": theme_size,
            "theme_context_score": score,
            "score_membership": breakdown["membership"],
            "score_stage": breakdown["stage"],
            "score_size": breakdown["size"],
            "outcome": outcome,
            "ret_5d": ret,
        })

    # Write CSV
    if enriched:
        with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(enriched[0].keys()))
            w.writeheader()
            w.writerows(enriched)
    logger.info("wrote %s (%d rows)", OUT_CSV, len(enriched))

    # Validation md
    lines = [
        "# Theme Context Score — Phase 1 prototype validation",
        "",
        "_Computes a theme_context_score (0-10) per labeled alert. "
        "Score = membership (0/5) + stage bonus (0-3) + size bonus "
        "(0-2). This is ONE INPUT to the eventual meta-rubric — NOT "
        "shipped as a filter._",
        "",
        "## Score distribution by user label",
        "",
        "| User label | N | Median score | Avg score | Range |",
        "|---|---:|---:|---:|---|",
    ]
    by_lbl = defaultdict(list)
    for e in enriched:
        by_lbl[e["user_label"]].append(e["theme_context_score"])
    LABEL_ORDER = ["game_changer", "game_changer, but Delayed EP",
                   "strong", "strong, delayed EP", "routine_correct",
                   "routine_mislabeled", "other", "No EP", "N/A"]
    for lbl in LABEL_ORDER:
        scores = by_lbl.get(lbl, [])
        if not scores:
            continue
        lines.append(f"| {lbl} | {len(scores)} | {median(scores):.1f} | "
                     f"{mean(scores):.2f} | {min(scores)}-{max(scores)} |")
    lines.append("")
    lines.append("Higher median = operator labeled those names higher AND "
                 "they had stronger theme context. If `strong` and "
                 "`game_changer` have meaningfully higher median scores "
                 "than `routine_mislabeled`, the theme_context input is "
                 "a useful discriminator.")
    lines.append("")

    # Score × outcome
    lines.append("## Theme context score × forward outcome")
    lines.append("")
    score_buckets = {"0 (uncovered)": 0, "5-7 (in fading/nascent)": 0,
                     "8-10 (strong theme)": 0}
    score_outcomes = defaultdict(lambda: {"win": 0, "loss": 0,
                                            "pending": 0, "rets": []})
    for e in enriched:
        s = e["theme_context_score"]
        if s == 0:
            bk = "0 (uncovered)"
        elif s < 8:
            bk = "5-7 (in fading/nascent)"
        else:
            bk = "8-10 (strong theme)"
        score_buckets[bk] += 1
        score_outcomes[bk][e["outcome"]] += 1
        if e["ret_5d"] is not None:
            score_outcomes[bk]["rets"].append(e["ret_5d"])
    lines.append("| Theme score bucket | N | Wins | Losses | Pending | "
                 "Win rate | Median ret 5d |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for bk in ["0 (uncovered)", "5-7 (in fading/nascent)",
               "8-10 (strong theme)"]:
        s = score_outcomes[bk]
        n = score_buckets[bk]
        eval_n = s["win"] + s["loss"]
        wr = f"{s['win'] / eval_n * 100:.1f}%" if eval_n else "—"
        med = median(s["rets"]) if s["rets"] else None
        lines.append(f"| {bk} | {n} | {s['win']} | {s['loss']} | "
                     f"{s['pending']} | {wr} | {fmt_pct(med)} |")
    lines.append("")

    # Headline composite preview
    lines.append("## Hypothetical meta-rubric composition (just an illustration)")
    lines.append("")
    lines.append("If we combined catalyst_rubric_score (0-39) + "
                 "theme_context_score (0-10) at 4:1 weighting, alerts "
                 "would score 0-49. Final label thresholds would need "
                 "calibration against operator labels — that's a Phase 2 "
                 "exercise.")
    lines.append("")
    lines.append("**Critical**: this is a sketch. The meta-rubric also "
                 "needs technical_structure_score (gap-through-MAs, "
                 "base shape, distance from 52w high) and "
                 "gap_alignment_score before it's complete. Those build "
                 "in a future session.")
    lines.append("")

    # Score breakdown — what drove each bucket
    lines.append("## Score component breakdown by user label")
    lines.append("")
    lines.append("| User label | Median membership | Median stage | Median size | "
                 "Total median |")
    lines.append("|---|---:|---:|---:|---:|")
    for lbl in LABEL_ORDER:
        subset = [e for e in enriched if e["user_label"] == lbl]
        if not subset:
            continue
        med_m = median([e["score_membership"] for e in subset])
        med_st = median([e["score_stage"] for e in subset])
        med_sz = median([e["score_size"] for e in subset])
        med_t = median([e["theme_context_score"] for e in subset])
        lines.append(f"| {lbl} | {med_m:.1f} | {med_st:.1f} | "
                     f"{med_sz:.1f} | {med_t:.1f} |")
    lines.append("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    logger.info("wrote %s", OUT_MD)


if __name__ == "__main__":
    main()
