"""#267 (W4) — CHART-VISION judge eval: with-vs-without-chart delta surface for OPERATOR labeling.

READ-ONLY. No DB writes, no trade-state. Re-grades a cohort of historical mi_ep_alerts through the
holistic judge TWICE per row — once text-only (today's behavior) and once with a point-in-time daily
chart attached (candles + 10/20/50 MA stack + volume pane) — and surfaces the rows whose verdict
CHANGED, for the operator to label. The agent NEVER self-scores promote/demote (ADR 0011: the judge
is load-bearing; the operator owns the flip gate, and the live rubric-axis change is sign-off-gated).

DISCIPLINE (advisor 2026-06-17):
  • POINT-IN-TIME / NO LOOKAHEAD — the chart is rendered through the **prior trading day** only
    (mi_daily_closes WHERE trade_date < alert_date). The alert-day daily candle contains the
    breakout-day range — the very outcome the judge predicts — so it must NOT appear. (Alert-day
    intraday is the tape-features domain, #299, separate.) The text payload's catalyst/score are the
    stored alert-time values (already as-of-alert); the chart is therefore not a lone fresh input.
  • TWO-SIDED COHORT — deadcat_cohort.csv is an adversarial REJECT set (a chart axis that rejects
    everything scores perfectly on it). Pass a KEEP set too (known-good clean breakouts, e.g. from
    build_clean_breakout_cohort.py) so the eval also catches the chart causing false REJECTIONS.
    Each --cohort carries a LABEL (reject/keep/...) shown next to every delta.
  • JUDGE NOISE FLOOR — both arms are non-deterministic (adaptive thinking, no temperature). BOTH
    arms run K replicates; a "chart changed the verdict" delta is credible ONLY when each arm's modal
    is STABLE across K AND the two modals differ. An arm that itself flips is noise, reported apart.
  • EMIT THE IMAGES — every rendered chart PNG is saved to --outdir keyed by ticker_date so the
    operator labels seeing the SAME chart the judge saw (a text delta alone is unlabelable).
  • SMOKE (small --limit) validates MACHINERY + render rate, NOT efficacy. Only the operator-labeled
    full run can say the chart helps.

Run (read-only, on the server — needs prod DB + the mplfinance dep in the image):
  # smoke (machinery):
  docker exec apollo-market python /app/scripts/eval_chart_judge.py \
      --cohort /app/deadcat_cohort.csv:reject --limit 4 --replicates 3 --outdir /app/_chart_eval
  # full two-sided run (operator-triggered — costs ~2K Opus judge calls, WITH arm carries image tokens):
  docker exec apollo-market python /app/scripts/eval_chart_judge.py \
      --cohort /app/deadcat_cohort.csv:reject --cohort /app/clean_breakout_cohort.csv:keep \
      --replicates 3 --outdir /app/_chart_eval
"""
import argparse
import asyncio
import csv
import os
from collections import Counter
from datetime import date

from agents.market_intelligence.chart_axis import (  # SINGLE SOURCE — see chart_axis.py
    grade_b_c, grade_one, modal_stable, render_prior_day_chart,
)
from agents.market_intelligence.db import EP_JUDGE_PAYLOAD_COLS, get_pool
from agents.market_intelligence.ep_grade_judge import format_tier_transition
from scripts._judge_replay_common import (
    build_judge_payload, fetch_profile, resolve_grounded_text,
)

# Per-(ticker, alert_date) fetch of the SAME columns REPLAY_SQL exposes (db.EP_JUDGE_PAYLOAD_COLS,
# the one source) — the cohort is explicit (ticker, date) pairs from a CSV, not a recency window.
_ALERT_ROW_SQL = f"""
SELECT {EP_JUDGE_PAYLOAD_COLS}
FROM mi_ep_alerts
WHERE ticker = $1 AND alert_date = $2
ORDER BY detected_at DESC
LIMIT 1
"""

# Approx Opus pricing for the cost line (input/output $ per 1M tok). A rendered daily chart is
# ~1.0–1.5K image tokens; text payload dominates either way. Rough — for an estimate, not billing.
_OPUS_IN_PER_M = 5.0
_OPUS_OUT_PER_M = 25.0

# THREE-ARM ABLATION (advisor 2026-06-17): the eval isolates the VISION contribution from the free
# TEXT instruction, because the W4 decision is whether to ship a vision pipeline:
#   A baseline    = no note, no image (today's behaviour)
#   B instruction = the candidate 5-factor note, framed "from the data you have", NO image
#   C note+image  = the SAME note, framed "a chart is attached", + the rendered chart
# B−A = what the text instruction buys (shippable WITHOUT vision). C−B = the chart's MARGINAL visual
# contribution = the actual "does vision help" number. The candidate notes (CHART_AXIS_NOTE /
# CHART_AXIS_NOTE_TEXT_ONLY) + the B/C grade-compare core live in agents.market_intelligence.
# chart_axis — the SINGLE SOURCE shared with the live EOD shadow (#343), so the operator labels the
# byte-identical instruction in both. Promoting any of this into the LIVE _build_judge_prompt is the
# separate sign-off step (load-bearing judge).


def read_cohort(spec: str) -> tuple[str, list[tuple[str, date]]]:
    """`PATH:LABEL` → (label, [(ticker, alert_date), ...]). CSV uses cols 0,1 (ticker, ISO date);
    extra columns (tier/verdict in deadcat_cohort.csv) are ignored. A `:LABEL` is optional."""
    if ":" in spec and not spec[1:3] == ":\\":  # tolerate Windows drive letters in paths
        path, label = spec.rsplit(":", 1)
    else:
        path, label = spec, "cohort"
    rows: list[tuple[str, date]] = []
    with open(path, newline="") as f:
        for rec in csv.reader(f):
            if len(rec) < 2 or not rec[0].strip():
                continue
            try:
                rows.append((rec[0].strip().upper(), date.fromisoformat(rec[1].strip())))
            except ValueError:
                continue  # header or malformed line
    return label, rows


async def eval_one(client, sem, conn, ticker, alert_date, label, replicates, outdir):
    """Re-grade one cohort row across the THREE ablation arms, each ×K replicates (advisor 2026-06-17):
      A baseline    = existing prompt, no note, no image
      B instruction = existing prompt + the text-only axis note, NO image  ┐ grade_b_c (chart_axis,
      C note+image  = existing prompt + the chart-framed axis note + chart  ┘ shared with #343 shadow)
    Renders + saves the point-in-time chart PNG. Read-only. Returns the per-row record or a skip."""
    row = await conn.fetchrow(_ALERT_ROW_SQL, ticker, alert_date)
    if row is None:
        return {"skip": "no_alert_row", "ticker": ticker, "alert_date": alert_date, "label": label}

    png, n_daily = await render_prior_day_chart(ticker, alert_date)
    if png is None:
        return {"skip": "no_chart", "ticker": ticker, "alert_date": alert_date, "label": label,
                "n_daily": n_daily}
    png_path = os.path.join(outdir, f"{ticker}_{alert_date.isoformat()}.png")
    with open(png_path, "wb") as f:
        f.write(png)

    mc, sector, company = await fetch_profile(ticker)
    grounded_text, _ = await resolve_grounded_text(dict(row), company, grounded=False)
    payload, _ = build_judge_payload(dict(row), grounded_text, mc, sector)  # SAME text payload, all arms

    # Arm A is eval-only (the live baseline = no note/no image); B + C come from the shared core.
    a = await asyncio.gather(*[grade_one(client, sem, payload, None, None) for _ in range(replicates)])
    a_modal, a_stable, a_tiers = modal_stable(a)
    bc = await grade_b_c(client, sem, payload, png, replicates)
    return {
        "ticker": ticker, "alert_date": alert_date, "label": label, "floor": row["floor_tier"],
        "png_path": png_path, "n_daily": n_daily,
        "a_modal": a_modal, "a_stable": a_stable, "a_tiers": a_tiers,
        **bc,
        # instruction effect (B vs A) — credible only when both arms stable.
        "instruction_changed": (a_stable and bc["b_stable"] and a_modal != bc["b_modal"]),
        # bc already carries visual_changed (C vs B) — the real "does vision help" signal.
        "all_stable": a_stable and bc["both_stable"],
    }


def _format_instruction_delta(r) -> list:
    """B vs A — what the free TEXT instruction buys (shippable WITHOUT vision)."""
    v = r.get("b_verdict") or {}
    return [
        f"\n  {r['ticker']:6} {r['alert_date']}  [{r['label']}]  (floor={r['floor']})",
        f"     A baseline={r['a_modal']}  →  B instruction-only="
        f"{format_tier_transition(r['a_modal'], r['b_modal'])}",
        f"     judge: {(v.get('rationale') or '')[:240]}",
    ]


def _format_visual_delta(r) -> list:
    """C vs B — the chart's MARGINAL visual contribution beyond the same instruction (the actual
    'does vision help' signal). Includes the PNG so the operator labels seeing the judge's chart."""
    v = r.get("c_verdict") or {}
    return [
        f"\n  {r['ticker']:6} {r['alert_date']}  [{r['label']}]  (floor={r['floor']})",
        f"     B instruction-only={r['b_modal']}  →  C +chart="
        f"{format_tier_transition(r['b_modal'], r['c_modal'])}  "
        f"(A baseline was {r['a_modal']})",
        f"     chart: {r['png_path']}",
        f"     judge: {(v.get('rationale') or '')[:240]}",
    ]


async def main(cohorts: list[str], limit: int | None, replicates: int, outdir: str):
    os.makedirs(outdir, exist_ok=True)
    pairs: list[tuple[str, str, date]] = []  # (label, ticker, alert_date)
    for spec in cohorts:
        label, rows = read_cohort(spec)
        for t, d in rows:
            pairs.append((label, t, d))
    if limit:
        pairs = pairs[:limit]

    by_label = Counter(p[0] for p in pairs)
    print("=" * 80)
    print(f"#267 CHART-VISION JUDGE EVAL — {len(pairs)} row(s) "
          f"[{', '.join(f'{k}:{v}' for k, v in by_label.items())}], 3-ARM ablation, {replicates}× per arm")
    print("  arms: A baseline · B instruction-only (no image) · C instruction+chart")
    print(f"  scope: {len(pairs)} rows × 3 arms × {replicates} repl = "
          f"~{len(pairs) * 3 * replicates} Opus judge calls (arm C carries ~1.2K image tok/call)")
    # rough cost: A + B = ~2.5K in each; C = ~2.5K + ~1.2K image; ~250 out per call.
    in_tok = len(pairs) * replicates * (2500 + 2500 + (2500 + 1200))
    out_tok = len(pairs) * 3 * replicates * 250
    est = in_tok / 1e6 * _OPUS_IN_PER_M + out_tok / 1e6 * _OPUS_OUT_PER_M
    print(f"  est cost ~${est:.2f} (rough; Opus ${_OPUS_IN_PER_M}/{_OPUS_OUT_PER_M} per Mtok)")
    print(f"  charts → {outdir}/  ·  READ-ONLY · operator labels the deltas · NO self-certify")
    print("  ATTRIBUTION: B−A = what the TEXT instruction buys (no vision needed); C−B = the chart's")
    print("              MARGINAL visual lift = the actual 'does VISION help' number for the W4 call.")
    print("  TWO-SIDED check: a reject-only cohort can't catch the chart causing FALSE rejections.")
    print("=" * 80)
    if not pairs:
        print("  Empty cohort — nothing to eval.")
        return

    client = None
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
    sem = asyncio.Semaphore(3)

    pool = await get_pool()
    results = []
    try:
        async with pool.acquire() as conn:
            for label, t, d in pairs:  # sequential per-row (each fans out its own 2K judge calls)
                results.append(await eval_one(client, sem, conn, t, d, label, replicates, outdir))
    finally:
        if client is not None:
            try:
                await client.close()
            except Exception:
                pass

    graded = [r for r in results if "skip" not in r]
    skipped = [r for r in results if "skip" in r]
    n = len(graded)
    print(f"\nRENDERED + GRADED: {n}/{len(results)}  ·  SKIPPED: {len(skipped)}")
    for s in skipped:
        print(f"    ~ {s['ticker']:6} {s['alert_date']}  skip={s['skip']}"
              + (f" (n_daily={s.get('n_daily')})" if s.get("n_daily") is not None else ""))
    if not graded:
        print("  Nothing graded — check the cohort dates exist in mi_ep_alerts / mi_daily_closes.")
        return

    unstable = [r for r in graded if not r["all_stable"]]
    print(f"\nJUDGE NOISE FLOOR ({replicates}× per arm): {n - len(unstable)}/{n} STABLE on all 3 arms, "
          f"{len(unstable)} unstable on ≥1 arm (excluded from the delta reads).")
    for r in unstable:
        print(f"    ~ {r['ticker']:6} {r['alert_date']} [{r['label']}]  "
              f"A={r['a_tiers']} B={r['b_tiers']} C={r['c_tiers']}")

    def _section(title, key, fmt):
        deltas = [r for r in graded if r[key]]
        print(f"\n{title}: {len(deltas)}")
        for lbl in sorted({r["label"] for r in deltas}):  # split reject vs keep side
            side = [r for r in deltas if r["label"] == lbl]
            print(f"\n  ── {lbl} ({len(side)}) ──")
            for r in side:
                print("\n".join(fmt(r)))

    # B−A: the free TEXT instruction effect (shippable without any vision pipeline).
    _section("INSTRUCTION DELTAS  (B vs A — text instruction alone, A&B stable, modals differ)",
             "instruction_changed", _format_instruction_delta)
    # C−B: the chart's MARGINAL visual lift — THE number the vision-pipeline decision rides on.
    _section("VISUAL DELTAS  (C vs B — chart's marginal lift over the same instruction; B&C stable)",
             "visual_changed", _format_visual_delta)

    print("\n" + "-" * 80)
    print("HARD gate (ADR 0011): the OPERATOR labels each delta right/wrong — the agent does NOT "
          "self-certify. THE VISION DECISION rides on the VISUAL deltas (C−B): if they are few or "
          "the instruction (B−A) already captured the lift, the chart axis ships as TEXT, not a "
          "vision pipeline. KEEP-side downgrade = false rejection; REJECT-side = correct catch. A "
          "smoke proves render+flow only, not efficacy.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", action="append", default=[],
                    help="PATH:LABEL (repeatable). LABEL ∈ reject/keep/... shown next to deltas.")
    ap.add_argument("--limit", type=int, default=0, help="cap rows (0 = no cap / full run)")
    ap.add_argument("--replicates", type=int, default=3,
                    help="judge runs PER ARM for the noise floor (>=2; both arms replicated)")
    ap.add_argument("--outdir", type=str, default="_chart_eval",
                    help="folder for the emitted chart PNGs the operator labels against")
    args = ap.parse_args()
    if not args.cohort:
        ap.error("at least one --cohort PATH:LABEL required (e.g. deadcat_cohort.csv:reject)")
    asyncio.run(main(args.cohort, args.limit or None, args.replicates, args.outdir))
