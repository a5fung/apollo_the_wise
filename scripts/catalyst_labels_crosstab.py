"""EP Selectivity Phase 1 — Catalyst labels cross-tab analysis (Block C continued).

Joins user-labeled catalyst sheet to:
  - rubric score output (`catalyst_rubric_scores.csv`)
  - cohort outcomes (`ep_cohort_alerts_60d.csv`) — theme, forward returns
  - classifier output (`classifier.csv`) — Class A/B/C shape

Produces:
  - User label × actual outcome (does the user's grading predict returns?)
  - User label × rubric output (where the rubric disagrees, why?)
  - User label × theme membership (validates meta-rubric architecture)
  - routine_mislabeled deep dive — what's common across the 56 cases?
  - Notes thematic aggregation — what context dimensions appear in notes
  - Followup items surfaced from notes

Output: analysis/2026-05-16/catalyst_labels_crosstab.md
"""
from __future__ import annotations

import csv
import logging
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path("analysis/2026-05-16")
LABELS_CSV = DATA_DIR / "catalyst_labels.csv"
COHORT_CSV = DATA_DIR / "ep_cohort_alerts_60d.csv"
RUBRIC_CSV = DATA_DIR / "catalyst_rubric_scores.csv"
CLASSIFIER_CSV = DATA_DIR / "classifier.csv"
OUT_MD = DATA_DIR / "catalyst_labels_crosstab.md"


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def normalize_label(raw: str) -> str:
    """Collapse to canonical buckets while preserving delayed_EP flag."""
    s = (raw or "").strip().lower()
    if not s:
        return ""
    if "delayed" in s:
        if "game_changer" in s:
            return "game_changer_delayed"
        if "strong" in s:
            return "strong_delayed"
    if "game_changer" in s:
        return "game_changer"
    if "routine_mislabeled" in s:
        return "routine_mislabeled"
    if "routine_correct" in s:
        return "routine_correct"
    if s == "strong":
        return "strong"
    if s in ("other", "n/a", "no ep"):
        return s.lower().replace("/", "_").replace(" ", "_")
    return s


def derive_outcome(row: dict) -> tuple[str, float | None]:
    """Same logic as breakdowns.py — trade pnl > ret_5d > fwd_5d_pct."""
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


def max_high_pct(cohort_row: dict) -> float | None:
    """Forward max-favorable from gap-day open."""
    open_d0 = num(cohort_row.get("d0_open"))
    mh = num(cohort_row.get("max_high_20d")) or num(cohort_row.get("max_high_5d"))
    if open_d0 and mh:
        return mh / open_d0 - 1
    return None


def fmt_pct(v):
    return f"{v * 100:+.1f}%" if v is not None else "—"


def fmt_wr(n_win, n_total):
    if n_total == 0:
        return "—"
    return f"{n_win / n_total * 100:.1f}%"


# ── Theme keyword detection in notes ───────────────────────────────────────

NOTE_DIMENSIONS = {
    "theme_aligned": re.compile(r"(theme|themes|ai|sector|hot theme|"
                                 r"aligned with|key themes|industry|"
                                 r"in line with)", re.I),
    "technical": re.compile(r"(uptrend|breakout|base|sma|moving average|"
                            r"ma\b|52w|consolidation|chart|technical|"
                            r"trend|stage 2|cup|flag|tight)", re.I),
    "delayed_ep": re.compile(r"(delayed.{0,2}ep|delayed entry|"
                              r"didn't work|monitoring|wait)", re.I),
    "guidance_raise": re.compile(r"(guidance.{0,20}rais|raised guidance|"
                                  r"raised guide|raised outlook|"
                                  r"increased guidance)", re.I),
    "rev_strong": re.compile(r"(strong rev|rev acc|revenue growth|"
                              r"top.{0,3}line|sales growth|"
                              r"revenue accel|hyper.?growth)", re.I),
    "eps_suspect": re.compile(r"(eps.{0,10}(?:gam|one.?time|barely|"
                               r"poor|weak|low rev)|"
                               r"single.?digit|in.line)", re.I),
    "data_quality_issue": re.compile(r"(catalyst missed|date wrong|"
                                      r"detail.{0,5}missing|wrong date|"
                                      r"didn't catch|missed catalyst|"
                                      r"hard to tell|need to dig)", re.I),
}


def analyze_notes(note: str) -> set[str]:
    """Return which dimensions appear in the note text."""
    dims = set()
    if not note:
        return dims
    for name, pattern in NOTE_DIMENSIONS.items():
        if pattern.search(note):
            dims.add(name)
    return dims


def main() -> None:
    labels = load_rows(LABELS_CSV)
    cohort = load_rows(COHORT_CSV)
    rubric = load_rows(RUBRIC_CSV)
    classifier = load_rows(CLASSIFIER_CSV)

    # Index by (ticker, alert_date) for joining
    cohort_idx = {(r["ticker"], r["alert_date"]): r for r in cohort}
    rubric_idx = {r["ticker"]: r for r in rubric}
    classifier_idx = {(r["ticker"], r["alert_date"]): r for r in classifier}

    # Enrich labels with joined data
    enriched = []
    for lbl_row in labels:
        if not lbl_row.get("user_label", "").strip():
            continue
        key = (lbl_row["ticker"], lbl_row["alert_date"])
        cohort_row = cohort_idx.get(key, {})
        rubric_row = rubric_idx.get(lbl_row["ticker"], {})
        cls_row = classifier_idx.get(key, {})
        outcome_state, ret = derive_outcome(cohort_row)
        mfe = max_high_pct(cohort_row)
        enriched.append({
            "ticker": lbl_row["ticker"],
            "alert_date": lbl_row["alert_date"],
            "user_label_raw": lbl_row["user_label"].strip(),
            "user_label": normalize_label(lbl_row["user_label"]),
            "user_notes": lbl_row.get("user_notes", "").strip(),
            "gap_pct": num(lbl_row.get("gap_pct")),
            "ep_score": num(lbl_row.get("ep_score")),
            "catalyst_quality_llm": lbl_row.get("catalyst_quality", "").strip(),
            "theme_name": cohort_row.get("theme_name") or "",
            "theme_stage": cohort_row.get("theme_stage") or "",
            "ret_5d_or_pnl": ret,
            "outcome": outcome_state,
            "mfe_21d": mfe,
            "rubric_label": rubric_row.get("label") if rubric_row else None,
            "rubric_composite": num(rubric_row.get("composite_scaled"))
                                 if rubric_row else None,
            "shape_class": cls_row.get("shape_class") if cls_row else None,
            "note_dims": analyze_notes(lbl_row.get("user_notes", "")),
        })

    logger.info("enriched %d labeled rows", len(enriched))

    # ─── Section 1: User label × outcome ────────────────────────────────
    by_label_outcome = defaultdict(lambda: {"win": 0, "loss": 0, "pending": 0,
                                             "rets": [], "mfes": []})
    for e in enriched:
        b = by_label_outcome[e["user_label"]]
        b[e["outcome"]] += 1
        if e["ret_5d_or_pnl"] is not None:
            b["rets"].append(e["ret_5d_or_pnl"])
        if e["mfe_21d"] is not None:
            b["mfes"].append(e["mfe_21d"])

    lines = [
        "# Catalyst labels cross-tab analysis",
        "",
        f"_N={len(enriched)} hand-labeled alerts joined to cohort + rubric + classifier outputs._",
        "",
        "## §1 — User label × forward outcomes",
        "",
        "Does the operator's grading actually predict returns?",
        "",
        "| User label | N | Wins | Losses | Pending | Win rate | Avg ret 5d | Median MFE 21d |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    LABEL_ORDER = ["game_changer", "game_changer_delayed", "strong",
                   "strong_delayed", "routine_correct", "routine_mislabeled",
                   "other", "no_ep", "n_a"]
    for lbl in LABEL_ORDER:
        b = by_label_outcome.get(lbl)
        if not b:
            continue
        n = b["win"] + b["loss"] + b["pending"]
        evaluated = b["win"] + b["loss"]
        wr = fmt_wr(b["win"], evaluated)
        avg_r = mean(b["rets"]) if b["rets"] else None
        med_mfe = median(b["mfes"]) if b["mfes"] else None
        lines.append(
            f"| {lbl} | {n} | {b['win']} | {b['loss']} | {b['pending']} | "
            f"{wr} | {fmt_pct(avg_r)} | {fmt_pct(med_mfe)} |"
        )
    lines.append("")

    # ─── Section 2: User label × current LLM grade ──────────────────────
    by_label_llm = defaultdict(Counter)
    for e in enriched:
        by_label_llm[e["user_label"]][e["catalyst_quality_llm"] or "(blank)"] += 1
    lines.append("## §2 — User label × current LLM catalyst grade")
    lines.append("")
    lines.append("Where the existing grader is wrong. `routine_mislabeled` × "
                 "`strong` is the failure-mode count we care about.")
    lines.append("")
    llm_grades = sorted({g for c in by_label_llm.values() for g in c.keys()})
    lines.append("| User label | " + " | ".join(llm_grades) + " | total |")
    lines.append("|---|" + "---|" * (len(llm_grades) + 1))
    for lbl in LABEL_ORDER:
        c = by_label_llm.get(lbl)
        if not c:
            continue
        row_total = sum(c.values())
        lines.append(f"| {lbl} | "
                     + " | ".join(str(c[g]) for g in llm_grades)
                     + f" | {row_total} |")
    lines.append("")
    lines.append("**Headline**: every row in `routine_mislabeled × strong` "
                 "= one place the LLM grader incorrectly labeled a routine "
                 "earnings beat as 'strong' and admitted it to the system.")
    lines.append("")

    # ─── Section 3: User label × rubric output ──────────────────────────
    by_label_rubric = defaultdict(Counter)
    rubric_scores_by_label = defaultdict(list)
    for e in enriched:
        if e["rubric_label"]:
            by_label_rubric[e["user_label"]][e["rubric_label"]] += 1
            if e["rubric_composite"] is not None:
                rubric_scores_by_label[e["user_label"]].append(e["rubric_composite"])

    lines.append("## §3 — User label × catalyst rubric output (subset with rubric scored)")
    lines.append("")
    lines.append("Only the 50 rubric-sampled tickers (or fewer that overlap "
                 "the label sheet) appear here. Diagnoses where the rubric "
                 "diverges from operator grading.")
    lines.append("")
    rubric_labels = ["game_changer", "strong", "routine_correct", "weak"]
    lines.append("| User label | "
                 + " | ".join(rubric_labels)
                 + " | N (with rubric) | Median rubric composite |")
    lines.append("|---|" + "---|" * (len(rubric_labels) + 2))
    for lbl in LABEL_ORDER:
        c = by_label_rubric.get(lbl)
        if not c:
            continue
        row_total = sum(c.values())
        scores = rubric_scores_by_label.get(lbl, [])
        med_s = f"{median(scores):.1f}" if scores else "—"
        lines.append(f"| {lbl} | "
                     + " | ".join(str(c[r]) for r in rubric_labels)
                     + f" | {row_total} | {med_s} |")
    lines.append("")

    # ─── Section 4: User label × theme membership ───────────────────────
    by_label_theme = defaultdict(lambda: {"in_theme": 0, "uncovered": 0,
                                           "stages": Counter()})
    for e in enriched:
        b = by_label_theme[e["user_label"]]
        if e["theme_name"]:
            b["in_theme"] += 1
            if e["theme_stage"]:
                b["stages"][e["theme_stage"]] += 1
        else:
            b["uncovered"] += 1
    lines.append("## §4 — User label × theme membership (validates meta-rubric architecture)")
    lines.append("")
    lines.append("If theme alignment correlates with `strong` / "
                 "`game_changer` labels, that confirms theme heat as a "
                 "separate meta-rubric input.")
    lines.append("")
    lines.append("| User label | In theme | Uncovered | Theme rate | "
                 "Stage breakdown |")
    lines.append("|---|---:|---:|---:|---|")
    for lbl in LABEL_ORDER:
        b = by_label_theme.get(lbl)
        if not b:
            continue
        total = b["in_theme"] + b["uncovered"]
        if total == 0:
            continue
        theme_rate = b["in_theme"] / total * 100
        stages = ", ".join(f"{s}={n}" for s, n in b["stages"].most_common())
        lines.append(f"| {lbl} | {b['in_theme']} | {b['uncovered']} | "
                     f"{theme_rate:.1f}% | {stages or '—'} |")
    lines.append("")

    # ─── Section 5: User label × Class A/B/C shape ──────────────────────
    by_label_shape = defaultdict(Counter)
    for e in enriched:
        if e["shape_class"]:
            by_label_shape[e["user_label"]][e["shape_class"]] += 1
    lines.append("## §5 — User label × intraday shape (A/B/C/Chop)")
    lines.append("")
    shape_keys = ["CLASS_A", "CLASS_B", "CLASS_C", "AMBIGUOUS_CHOP", "AMBIGUOUS_DEAD"]
    lines.append("| User label | " + " | ".join(s.replace("_", "&nbsp;") for s in shape_keys) + " | total |")
    lines.append("|---|" + "---|" * (len(shape_keys) + 1))
    for lbl in LABEL_ORDER:
        c = by_label_shape.get(lbl)
        if not c:
            continue
        total = sum(c.values())
        lines.append(f"| {lbl} | "
                     + " | ".join(str(c[s]) for s in shape_keys)
                     + f" | {total} |")
    lines.append("")

    # ─── Section 6: routine_mislabeled deep-dive ─────────────────────────
    mislabeled = [e for e in enriched if e["user_label"] == "routine_mislabeled"]
    lines.append("## §6 — `routine_mislabeled` deep-dive (N=" + str(len(mislabeled)) + ")")
    lines.append("")
    lines.append("These are alerts the LLM graded 'strong' that operator says "
                 "are actually routine. They are the prime targets for the "
                 "magnitude-aware rubric.")
    lines.append("")
    # Distribution by gap %
    gap_buckets = {"8-10%": 0, "10-15%": 0, "15-25%": 0, "25%+": 0}
    for e in mislabeled:
        g = e["gap_pct"]
        if g is None:
            continue
        if g >= 25:
            gap_buckets["25%+"] += 1
        elif g >= 15:
            gap_buckets["15-25%"] += 1
        elif g >= 10:
            gap_buckets["10-15%"] += 1
        else:
            gap_buckets["8-10%"] += 1
    lines.append("### Gap distribution of mislabeled cases")
    lines.append("")
    lines.append("| Gap | N |")
    lines.append("|---|---:|")
    for k, v in gap_buckets.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")
    # Outcome
    wins = sum(1 for e in mislabeled if e["outcome"] == "win")
    losses = sum(1 for e in mislabeled if e["outcome"] == "loss")
    pending = sum(1 for e in mislabeled if e["outcome"] == "pending")
    evaluated = wins + losses
    rets = [e["ret_5d_or_pnl"] for e in mislabeled if e["ret_5d_or_pnl"] is not None]
    lines.append("### Outcome of mislabeled cases")
    lines.append("")
    lines.append(f"- Wins: {wins} / {evaluated} ({fmt_wr(wins, evaluated)})")
    lines.append(f"- Losses: {losses}")
    lines.append(f"- Pending: {pending}")
    lines.append(f"- Median ret 5d: {fmt_pct(median(rets) if rets else None)}")
    lines.append(f"- Avg ret 5d: {fmt_pct(mean(rets) if rets else None)}")
    lines.append("")
    # Theme membership
    in_theme = sum(1 for e in mislabeled if e["theme_name"])
    uncovered = sum(1 for e in mislabeled if not e["theme_name"])
    lines.append(f"- In theme: {in_theme} / {len(mislabeled)} "
                 f"({in_theme / len(mislabeled) * 100:.1f}%)")
    lines.append("")

    # ─── Section 7: Notes thematic aggregation ────────────────────────────
    dim_counter = Counter()
    dim_by_label = defaultdict(Counter)
    for e in enriched:
        for d in e["note_dims"]:
            dim_counter[d] += 1
            dim_by_label[e["user_label"]][d] += 1
    lines.append("## §7 — Notes thematic aggregation")
    lines.append("")
    lines.append("Keyword-scan of operator notes — which context dimensions "
                 "appear most. Validates which meta-rubric inputs are "
                 "load-bearing.")
    lines.append("")
    lines.append("| Dimension | N notes mentioning |")
    lines.append("|---|---:|")
    for d, n in dim_counter.most_common():
        lines.append(f"| {d} | {n} |")
    lines.append("")
    lines.append("### Dimension co-occurrence by label")
    lines.append("")
    dims = list(NOTE_DIMENSIONS.keys())
    lines.append("| User label | " + " | ".join(dims) + " |")
    lines.append("|---|" + "---|" * len(dims))
    for lbl in LABEL_ORDER:
        c = dim_by_label.get(lbl)
        if not c:
            continue
        lines.append(f"| {lbl} | "
                     + " | ".join(str(c.get(d, 0)) for d in dims)
                     + " |")
    lines.append("")

    # ─── Section 8: Followups surfaced from notes ────────────────────────
    lines.append("## §8 — Followups surfaced from operator notes")
    lines.append("")
    lines.append("Specific actionable items extracted from operator labels + notes.")
    lines.append("")
    # Pull out specific named callouts
    callouts = []
    leveraged_etfs = [e for e in enriched if "etf" in e["user_notes"].lower() or e["user_label"] == "n_a"]
    if leveraged_etfs:
        callouts.append(
            f"**Leveraged ETFs upstream filter gap** ({len(leveraged_etfs)} cases): "
            + ", ".join(f"{e['ticker']} {e['alert_date']}" for e in leveraged_etfs)
            + " — shouldn't be admitted as EP candidates at all. Filter at universe selection."
        )
    ma_slipped = [e for e in enriched if e["user_label"] == "other"
                  and "m&a" in e["user_notes"].lower() or "buyout" in e["user_notes"].lower()]
    if ma_slipped:
        callouts.append(
            f"**M&A buyouts slipped past direction-aware filter** ({len(ma_slipped)} cases): "
            + ", ".join(f"{e['ticker']} {e['alert_date']}" for e in ma_slipped)
            + " — investigate why ma_filter.is_likely_ma missed."
        )
    catalyst_data = [e for e in enriched
                      if "catalyst missed" in e["user_notes"].lower()
                      or "catalyst is missed" in e["user_notes"].lower()
                      or "didn't catch" in e["user_notes"].lower()]
    if catalyst_data:
        callouts.append(
            f"**Catalyst extraction misses** ({len(catalyst_data)} cases): "
            + ", ".join(f"{e['ticker']} {e['alert_date']}" for e in catalyst_data)
            + " — catalyst column doesn't capture the real news. Data extraction "
              "issue, not just grading. Affects every downstream consumer."
        )
    date_mismatch = [e for e in enriched
                     if "date" in e["user_notes"].lower()
                     and ("wrong" in e["user_notes"].lower()
                          or "all wrong" in e["user_notes"].lower())]
    if date_mismatch:
        callouts.append(
            f"**Catalyst date mismatch** ({len(date_mismatch)} cases): "
            + ", ".join(f"{e['ticker']} {e['alert_date']}" for e in date_mismatch)
            + " — system assigned catalyst date doesn't match actual news date. "
              "Investigate detector-day-of-news pipeline."
        )
    no_ep_class = [e for e in enriched if e["user_label"] == "no_ep"]
    if no_ep_class:
        callouts.append(
            f"**Methodological mismatch — not actually EP setup** ({len(no_ep_class)} cases): "
            + ", ".join(f"{e['ticker']} {e['alert_date']}" for e in no_ep_class)
            + " — operator says these are trend-continuation, not EP. Suggests "
              "MAGNA53 sometimes admits non-EP shapes."
        )
    for c in callouts:
        lines.append(f"- {c}")
        lines.append("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    logger.info("wrote %s", OUT_MD)


if __name__ == "__main__":
    main()
