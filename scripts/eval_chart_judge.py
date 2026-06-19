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
from datetime import date, datetime, timedelta

from agents.market_intelligence.chart_render import bars_to_df, render_daily_chart_png
from agents.market_intelligence.db import get_pool
from agents.market_intelligence.ep_grade_judge import format_tier_transition, grade_holistic
from scripts._judge_replay_common import (
    build_judge_payload, fetch_profile, resolve_grounded_text,
)

# Per-(ticker, alert_date) fetch of the same columns REPLAY_SQL exposes — the cohort is explicit
# (ticker, date) pairs from a CSV, not a recency window.
_ALERT_ROW_SQL = """
SELECT ticker, alert_date, detected_at,
       COALESCE(baseline_floor_tier, score_tier) AS floor_tier,
       score_tier, catalyst_quality, catalyst, claude_analysis,
       in_active_theme, in_narrative_cohort, gap_pct, pm_rvol, vol_percentile,
       ep_score, grounded_text
FROM mi_ep_alerts
WHERE ticker = $1 AND alert_date = $2
ORDER BY detected_at DESC
LIMIT 1
"""

# Approx Opus pricing for the cost line (input/output $ per 1M tok). A rendered daily chart is
# ~1.0–1.5K image tokens; text payload dominates either way. Rough — for an estimate, not billing.
_OPUS_IN_PER_M = 5.0
_OPUS_OUT_PER_M = 25.0

# CANDIDATE chart-axis instruction. THREE-ARM ABLATION (advisor 2026-06-17): the eval must isolate
# the VISION contribution from the free TEXT instruction, because the W4 decision is whether to ship
# a vision pipeline. So the instruction body is shared and the ONLY difference between arms B and C
# is whether an image is attached + the one framing sentence:
#   A baseline       = no note, no image (today's behaviour)
#   B instruction    = the 5-factor note, framed "from the data you have", NO image
#   C note+image     = the 5-factor note, framed "a chart is attached", + the rendered chart
# B−A = what the text instruction buys (shippable WITHOUT vision). C−B = the chart's MARGINAL visual
# contribution = the actual "does vision help" number. Promoting any of this into the LIVE
# _build_judge_prompt is the separate sign-off step (load-bearing judge).
# The 5-factor body + closing — BYTE-IDENTICAL across arms B and C so only the modality differs.
_AXIS_LEAD = ("As ONE additional axis in your holistic grade (it informs, it does not override a "
              "strong catalyst), weigh the name's recent daily technical structure, per momentum/EP "
              "methodology (Qullamaggie / Pradeep / Stamatoudis):")
_CHART_FACTORS = """  • Prior trend & leadership — is there a real prior advance to pivot from (the
    "post a runup"), or is this a low/basing name with no thrust?
  • Base quality — a tight, orderly consolidation / contraction near the highs is constructive; a
    wide, sloppy, or broken-down structure is a negative.
  • Volume — dry-up through the base (quiet right side) is constructive; persistent heavy selling is
    a negative.
  • Location vs the MA stack — riding above a rising 10/20/50 stack is constructive; far extended
    above it invites exhaustion; below a falling stack is a broken structure.
  • Over-extension / climax — a parabolic, far-from-trend move is lower-quality entry even on good news.
Let this technical read nudge the tier up or down within your existing rubric; cite the decisive
technical feature in your rationale."""

# Arm C — the ONLY difference from B is the "a chart is attached / read the chart" framing + the PNG.
CHART_AXIS_NOTE = f"""
--- ATTACHED: DAILY CHART (technical-structure axis — candidate) ---
A daily candlestick chart is attached (10/20/50 SMAs + volume pane), rendered through the PRIOR
trading day — it does NOT show the alert-day move, by design. Read the chart. {_AXIS_LEAD}
{_CHART_FACTORS}"""

# Arm B — same lead + factors, framed to reason from the numeric context; NO image, no dangling
# "attached chart" reference (which would be a lie with no PNG sent).
CHART_AXIS_NOTE_TEXT_ONLY = f"""
--- TECHNICAL-STRUCTURE AXIS (candidate, from the data provided — no chart attached) ---
{_AXIS_LEAD}
{_CHART_FACTORS}"""


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


async def fetch_prior_daily_ohlcv(conn, ticker: str, alert_date: date, lookback: int = 160):
    """Daily OHLCV STRICTLY before alert_date (the prior-trading-day cut — no alert-day candle),
    ascending, as dicts bars_to_df accepts. lookback>render window so the MA-50 has its runway."""
    rows = await conn.fetch(
        # mi_daily_closes' column is `close`; bars_to_df expects the key `close_price`
        # (chart_render._OHLCV_KEYS) → alias. (Latent bug: never hit before because every prior
        # cohort row skipped at the alert-row lookup; surfaced 2026-06-18 on the rebuilt 2026 cohort.)
        """SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume
           FROM mi_daily_closes
           WHERE ticker = $1 AND trade_date < $2
           ORDER BY trade_date DESC LIMIT $3""",
        ticker, alert_date, lookback)
    return [dict(r) for r in reversed(rows)]


def _modal_stable(verdicts: list):
    """(modal_tier|None, stable_bool, tiers_list) — stable iff every replicate returned the same
    non-None tier (mirrors eval_tape_judge)."""
    tiers = [v["tier"] if v else None for v in verdicts]
    stable = len(set(tiers)) == 1 and tiers[0] is not None
    c = Counter(t for t in tiers if t).most_common(1)
    return (c[0][0] if c else None), stable, tiers


async def _grade(client, sem, payload, image_png, chart_note):
    async with sem:
        return await grade_holistic(client, payload, timeout=40,
                                    image_png=image_png, chart_note=chart_note)


async def eval_one(client, sem, conn, ticker, alert_date, label, replicates, outdir):
    """Re-grade one cohort row across the THREE ablation arms, each ×K replicates (advisor 2026-06-17):
      A baseline    = existing prompt, no note, no image
      B instruction = existing prompt + the text-only axis note, NO image
      C note+image  = existing prompt + the chart-framed axis note + the rendered chart
    Renders + saves the point-in-time chart PNG. Read-only. Returns the per-row record or a skip."""
    row = await conn.fetchrow(_ALERT_ROW_SQL, ticker, alert_date)
    if row is None:
        return {"skip": "no_alert_row", "ticker": ticker, "alert_date": alert_date, "label": label}

    daily = await fetch_prior_daily_ohlcv(conn, ticker, alert_date)
    df = bars_to_df(daily)
    png = render_daily_chart_png(df, ticker, as_of=alert_date - timedelta(days=1))
    if png is None:
        return {"skip": "no_chart", "ticker": ticker, "alert_date": alert_date, "label": label,
                "n_daily": len(daily)}
    png_path = os.path.join(outdir, f"{ticker}_{alert_date.isoformat()}.png")
    with open(png_path, "wb") as f:
        f.write(png)

    mc, sector, company = await fetch_profile(ticker)
    grounded_text, _ = await resolve_grounded_text(dict(row), company, grounded=False)
    payload, _ = build_judge_payload(dict(row), grounded_text, mc, sector)  # SAME text payload, all arms

    a = await asyncio.gather(*[_grade(client, sem, payload, None, None) for _ in range(replicates)])
    b = await asyncio.gather(
        *[_grade(client, sem, payload, None, CHART_AXIS_NOTE_TEXT_ONLY) for _ in range(replicates)])
    c = await asyncio.gather(
        *[_grade(client, sem, payload, png, CHART_AXIS_NOTE) for _ in range(replicates)])
    a_modal, a_stable, a_tiers = _modal_stable(a)
    b_modal, b_stable, b_tiers = _modal_stable(b)
    c_modal, c_stable, c_tiers = _modal_stable(c)
    return {
        "ticker": ticker, "alert_date": alert_date, "label": label, "floor": row["floor_tier"],
        "png_path": png_path, "n_daily": len(daily),
        "a_modal": a_modal, "a_stable": a_stable, "a_tiers": a_tiers,
        "b_modal": b_modal, "b_stable": b_stable, "b_tiers": b_tiers,
        "c_modal": c_modal, "c_stable": c_stable, "c_tiers": c_tiers,
        "b_verdict": next((v for v in b if v), None),
        "c_verdict": next((v for v in c if v), None),
        # instruction effect (B vs A) — credible only when both arms stable.
        "instruction_changed": (a_stable and b_stable and a_modal != b_modal),
        # MARGINAL VISUAL effect (C vs B) — the real "does vision help" signal.
        "visual_changed": (b_stable and c_stable and b_modal != c_modal),
        "all_stable": a_stable and b_stable and c_stable,
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
