"""EP Selectivity Phase 1 — retrospective shadow simulation (Block 2.5).

Applies R1-R5 recommendations from the ADR to the historic cohort and
reports the projected delta on WR / avg-ret / alert volume.

  R1 — Drop MODERATE auto-actions
  R2 — Lift gap floor 8% → 10%
  R3 — Drop Day-1 re-entry (attempt > 1)
  R4 — In-theme scoring bonus (admit MODERATE→HIGH-equivalent if in-theme)
  R5 — Loosen session_rvol_low 1.0× → 0.5× in 9:30-9:45 only

Reads:
  analysis/2026-05-16/ep_cohort_alerts_60d.csv
  analysis/2026-05-16/ep_cohort_skipped_60d.csv

Writes:
  analysis/2026-05-16/shadow_sim.md  (markdown report for ADR §8)
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from statistics import mean, median

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path("analysis/2026-05-16")
ALERTS_CSV = DATA_DIR / "ep_cohort_alerts_60d.csv"
SKIPPED_CSV = DATA_DIR / "ep_cohort_skipped_60d.csv"
OUT_MD = DATA_DIR / "shadow_sim.md"


def num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


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


def summarize(rows: list[dict], label: str) -> dict:
    """Returns dict with n, win_rate, avg_ret, median_ret."""
    outcomes = []
    pending = 0
    for r in rows:
        state, ret = derive_outcome(r)
        if state == "pending":
            pending += 1
        else:
            outcomes.append((state, ret))
    n_eval = len(outcomes)
    wins = sum(1 for o, _ in outcomes if o == "win")
    rets = [r for _, r in outcomes if r is not None]
    return {
        "label": label,
        "n_total": len(rows),
        "n_eval": n_eval,
        "n_pending": pending,
        "win_rate": wins / n_eval if n_eval else 0.0,
        "wins": wins,
        "losses": n_eval - wins,
        "avg_ret": mean(rets) if rets else None,
        "median_ret": median(rets) if rets else None,
        "rows": rows,  # keep for chained filters
    }


def fmt_pct(v):
    return f"{v * 100:+.1f}%" if v is not None else "—"


def fmt_wr(v):
    return f"{v * 100:.1f}%" if v else "—"


# ── Filter predicates ──────────────────────────────────────────────────────

def passes_R1(row: dict) -> bool:
    """R1: keep HIGH only; drop MODERATE auto-actions."""
    return row.get("score_tier") == "HIGH"


def passes_R2(row: dict) -> bool:
    """R2: lift gap floor 8% → 10%."""
    g = num(row.get("gap_pct"))
    return g is not None and g >= 10.0


def passes_R3(row: dict) -> bool:
    """R3: drop Day-1 re-entries (entry_attempt > 1)."""
    ea = num(row.get("entry_attempt"))
    if ea is None:
        return True  # MODERATE / unentered rows have no entry_attempt
    return ea <= 1


def passes_R4_boost(row: dict) -> bool:
    """R4: in-theme = score promotion. MODERATE alerts in Accelerating
    or Mainstream theme treated as if they had score ≥ 60 (admittable
    after R1 drops MODERATE)."""
    stage = (row.get("theme_stage") or "").strip()
    return stage in ("Accelerating", "Mainstream")


def applies_R5(row: dict) -> bool:
    """R5: filtered candidates that would have been admitted by a
    loosened session_rvol gate (0.5× in 9:30-9:45 window).
    Operates on SKIPPED rows, not ALERTS."""
    skip_cat = row.get("skip_category", "")
    minutes_since_open = num(row.get("minutes_since_open"))
    if skip_cat != "session_rvol_low":
        return False
    # Only loosen during 9:30-9:45 window (minutes_since_open 0-14)
    if minutes_since_open is None or minutes_since_open > 14:
        return False
    return True


def main() -> None:
    with ALERTS_CSV.open("r", encoding="utf-8") as f:
        alerts = list(csv.DictReader(f))
    with SKIPPED_CSV.open("r", encoding="utf-8") as f:
        skipped = list(csv.DictReader(f))

    logger.info("loaded %d alerts, %d skipped", len(alerts), len(skipped))

    # ── Current baseline (all alerts, no filters applied) ─────────────────
    baseline_all = summarize(alerts, "Baseline — all 165 alerts")
    baseline_traded = summarize([r for r in alerts if r.get("trade_id")
                                 and r.get("trade_status") == "closed"],
                                "Baseline — TRADED only (closed paper)")

    # ── R1: HIGH only ─────────────────────────────────────────────────────
    r1_keep = [r for r in alerts if passes_R1(r)]
    r1_drop = [r for r in alerts if not passes_R1(r)]
    r1 = summarize(r1_keep, "R1 — HIGH only (MODERATE dropped)")
    r1_dropped = summarize(r1_drop, "R1 — DROPPED MODERATE cohort")

    # ── R2: gap floor 10% (applied on top of R1) ──────────────────────────
    r2_keep = [r for r in r1_keep if passes_R2(r)]
    r2_drop = [r for r in r1_keep if not passes_R2(r)]
    r2 = summarize(r2_keep, "R1+R2 — HIGH AND gap≥10%")
    r2_dropped = summarize(r2_drop, "R2 — DROPPED gap<10% (HIGH only)")

    # ── R3: drop entry_attempt>1 (downstream effect on traded subset) ──────
    # Only operates on rows that have entry_attempt populated (= traded rows)
    r3_keep = [r for r in r2_keep if passes_R3(r)]
    r3_drop = [r for r in r2_keep if not passes_R3(r)]
    r3 = summarize(r3_keep, "R1+R2+R3 — drop re-entries")
    r3_dropped = summarize(r3_drop, "R3 — DROPPED Day-1 re-entry attempts")

    # ── R4: in-theme bonus (RE-ADMIT MODERATE that's in active theme) ─────
    # R4 adds back MODERATE alerts that R1 dropped, IF they're in an
    # Accelerating or Mainstream theme. Net effect: keep R1's MODERATE
    # cut but make an exception for in-theme.
    r4_readmit = [r for r in r1_drop if passes_R4_boost(r)]
    r4_keep = r3_keep + [r for r in r4_readmit if passes_R2(r)]
    r4 = summarize(r4_keep, "R1+R2+R3+R4 — plus in-theme re-admits")
    r4_added = summarize(r4_readmit, "R4 — RE-ADMITTED in-theme MODERATE")

    # ── R5: loosen session_rvol gate during 9:30-9:45 ─────────────────────
    # R5 admits SKIPPED rows (filter-rejected) that match the loosened
    # criteria. Joins to the post-R4 cohort additively.
    r5_admit = [r for r in skipped if applies_R5(r)]
    r5_admit_sum = summarize(r5_admit, "R5 — ADMITTED by loosened session_rvol")

    # Final composite: R1+R2+R3+R4+R5 (R5 adds, others filter)
    # Note: R5 outcomes use ret_5d directly (from missed_outcomes), not
    # entry-pnl since these were never entered.
    final = summarize(r4_keep + r5_admit,
                       "FINAL — R1+R2+R3+R4+R5 composite cohort")

    # ── Compose report ────────────────────────────────────────────────────
    sections = [
        "# EP Selectivity — Shadow Simulation",
        "",
        "_Retrospective application of ADR §8 recommendations R1-R5 "
        "to the 60d historic cohort. Estimates the projected cohort "
        "outcome IF these filters had been live during the 60d window._",
        "",
        "## Methodology",
        "",
        "- Baseline: every `mi_ep_alerts` row in 60d, joined to forward "
        "returns (trade pnl > missed_outcomes > scan_outcomes priority).",
        "- Win definition: `total_pnl > 0` (traded) or `ret_5d > +5%` "
        "(gap-day open → +5d close).",
        "- Each rule cumulatively filters or admits rows; final is "
        "composite of all five.",
        "- R5 *adds* historically-rejected candidates back to the cohort, "
        "using their settled `ret_5d` from `mi_ep_missed_outcomes`.",
        "",
        "## Per-filter breakdown",
        "",
        "| Stage | N alerts | N eval | Win rate | Avg ret | Median ret |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for s in [baseline_all, baseline_traded, r1, r2, r3, r4, final]:
        sections.append(
            f"| {s['label']} | {s['n_total']} | {s['n_eval']} | "
            f"{fmt_wr(s['win_rate'])} | "
            f"{fmt_pct(s['avg_ret'])} | "
            f"{fmt_pct(s['median_ret'])} |"
        )
    sections.append("")

    sections.append("## What each rule dropped or added")
    sections.append("")
    sections.append("| Rule | Action | N | Win rate of dropped | "
                    "Avg ret of dropped | Interpretation |")
    sections.append("|---|---|---:|---:|---:|---|")
    sections.append(
        f"| R1 | dropped MODERATE | {r1_dropped['n_total']} | "
        f"{fmt_wr(r1_dropped['win_rate'])} | "
        f"{fmt_pct(r1_dropped['avg_ret'])} | "
        f"{'lost some winners' if r1_dropped['win_rate'] > 0.4 else 'mostly losers'} |"
    )
    sections.append(
        f"| R2 | dropped HIGH gap<10% | {r2_dropped['n_total']} | "
        f"{fmt_wr(r2_dropped['win_rate'])} | "
        f"{fmt_pct(r2_dropped['avg_ret'])} | "
        f"{'fine cut' if r2_dropped['win_rate'] < 0.3 else 'lost winners'} |"
    )
    sections.append(
        f"| R3 | dropped Day-1 re-entry | {r3_dropped['n_total']} | "
        f"{fmt_wr(r3_dropped['win_rate'])} | "
        f"{fmt_pct(r3_dropped['avg_ret'])} | "
        f"{'clean cut' if r3_dropped['win_rate'] < 0.3 else 'reconsider'} |"
    )
    sections.append(
        f"| R4 | re-admitted in-theme MODERATE | "
        f"{r4_added['n_total']} | {fmt_wr(r4_added['win_rate'])} | "
        f"{fmt_pct(r4_added['avg_ret'])} | "
        f"{'good admit' if r4_added['win_rate'] > 0.5 else 'mixed'} |"
    )
    sections.append(
        f"| R5 | admitted session_rvol_low (9:30-9:45) | "
        f"{r5_admit_sum['n_total']} | "
        f"{fmt_wr(r5_admit_sum['win_rate'])} | "
        f"{fmt_pct(r5_admit_sum['avg_ret'])} | "
        f"{'+R signal' if r5_admit_sum['avg_ret'] and r5_admit_sum['avg_ret'] > 0 else 'noise'} |"
    )
    sections.append("")

    # ── Headline projection ──────────────────────────────────────────────
    baseline_wr = baseline_all["win_rate"]
    baseline_n = baseline_all["n_total"]
    baseline_avg = baseline_all["avg_ret"]
    final_wr = final["win_rate"]
    final_n = final["n_total"]
    final_avg = final["avg_ret"]
    wr_delta = (final_wr - baseline_wr) * 100
    vol_delta_pct = (final_n - baseline_n) / baseline_n * 100

    sections.append("## Headline projection")
    sections.append("")
    sections.append(f"- **Cohort win rate**: {fmt_wr(baseline_wr)} → "
                    f"**{fmt_wr(final_wr)}** "
                    f"({'+'  if wr_delta >= 0 else ''}{wr_delta:.1f}pp)")
    sections.append(f"- **Cohort avg return**: {fmt_pct(baseline_avg)} → "
                    f"**{fmt_pct(final_avg)}**")
    sections.append(f"- **Alert volume**: {baseline_n} → **{final_n}** "
                    f"({'+'  if vol_delta_pct >= 0 else ''}{vol_delta_pct:.1f}%)")
    sections.append("")

    # ── Caveats ───────────────────────────────────────────────────────────
    sections.append("## Caveats (read before believing the numbers)")
    sections.append("")
    sections.append(
        "1. **Retrospective**: applying filters to data they didn't "
        "shape. Real Phase 2 shadow telemetry over 30d in production "
        "is the actual test."
    )
    sections.append(
        "2. **R3 effect underweighted**: only 6 historic re-entries "
        "in cohort; the structural lever is small. Future cohort "
        "may differ."
    )
    sections.append(
        "3. **R5 admits unentered candidates**: assumes ORB-high "
        "entry + ORB-low stop would have fired cleanly. Real "
        "execution slippage (gap fills, fade guards, dead-zone) "
        "would reduce R5 win rate vs the raw `ret_5d` proxy."
    )
    sections.append(
        "4. **Sample size**: 165 total alerts is below most "
        "feedback's N≥30 ship gate per dimension. Treat each rule's "
        "outcome as directional, not definitive."
    )
    sections.append(
        "5. **Outcome mixing**: traded rows use entry-pnl R; "
        "unentered use 5d open-to-close. Magnitudes are not perfectly "
        "comparable. WR direction is comparable; avg-ret only as "
        "rough indicator."
    )
    sections.append("")

    OUT_MD.write_text("\n".join(sections), encoding="utf-8")
    logger.info("wrote %s", OUT_MD)
    logger.info("Baseline WR %.1f%% (n=%d) → Final WR %.1f%% (n=%d)",
                baseline_wr * 100, baseline_n,
                final_wr * 100, final_n)


if __name__ == "__main__":
    main()
