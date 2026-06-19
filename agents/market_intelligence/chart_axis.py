"""Chart-vision judge axis (#267 / #343) — SINGLE SOURCE for the candidate technical-structure
axis note + the B/C (text-only vs +chart) grade-compare core.

Both the offline eval (`scripts/eval_chart_judge.py`) and the live EOD shadow recorder
(`scheduler._chart_axis_shadow_job`) import the note constants + the compare core FROM HERE so
they can never drift — the operator labels the SAME instruction text in both surfaces (mirrors
the `is_entry_tight` single-source discipline / `feedback_single_source_of_truth`). The eval's
existing 2/2 operator labels were rendered against the EXACT strings below; the shadow's future
deltas are only comparable to that result because they re-use these same bytes.

NOTHING here touches the LIVE 9:45 grade path. `grade_holistic` defaults `chart_note`/`image_png`
to None, so the live judge prompt is byte-identical; this module only supplies the candidate note
+ a shadow-grading wrapper that passes them. Promoting the axis into `_build_judge_prompt` is the
separate operator sign-off step (ADR 0011 — the judge is load-bearing).
"""
from __future__ import annotations

import asyncio
from collections import Counter
from datetime import date, timedelta

from agents.market_intelligence.chart_render import bars_to_df, render_daily_chart_png
from agents.market_intelligence.ep_grade_judge import grade_holistic

# CANDIDATE chart-axis instruction. The 5-factor body is BYTE-IDENTICAL across the text-only (B)
# and with-chart (C) arms; the ONLY difference is the framing sentence + whether a PNG is attached,
# so a B/C verdict delta isolates the chart's MARGINAL visual contribution from the free text
# instruction. Per momentum/EP methodology (Qullamaggie / Pradeep / Stamatoudis).
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


def modal_stable(verdicts: list):
    """(modal_tier|None, stable_bool, tiers_list) — stable iff every replicate returned the same
    non-None tier (mirrors eval_tape_judge). The judge is non-deterministic (adaptive thinking, no
    temperature); a "chart changed the verdict" claim is credible ONLY when each arm is stable."""
    tiers = [v["tier"] if v else None for v in verdicts]
    stable = len(set(tiers)) == 1 and tiers[0] is not None
    c = Counter(t for t in tiers if t).most_common(1)
    return (c[0][0] if c else None), stable, tiers


async def render_prior_day_chart(ticker: str, alert_date: date):
    """(png_bytes|None, n_daily) — render the point-in-time daily chart (≤ prior trading day) for
    `ticker`/`alert_date`. ONE source for the whole render pipeline (fetch → df → PNG); both the
    eval and the shadow call it so the chart the operator labels is exactly the chart the judge
    saw. None png = too few bars / render dep missing (caller treats as "no chart this row")."""
    from agents.market_intelligence.db import get_prior_daily_ohlcv
    daily = await get_prior_daily_ohlcv(ticker, alert_date)
    df = bars_to_df(daily)
    png = render_daily_chart_png(df, ticker, as_of=alert_date - timedelta(days=1))
    return png, len(daily)


async def _grade(client, sem, payload, image_png, chart_note):
    async with sem:
        return await grade_holistic(client, payload, timeout=40,
                                    image_png=image_png, chart_note=chart_note)


async def grade_b_c(client, sem, payload, png, replicates: int) -> dict:
    """Grade arm B (text-only axis note, NO image) + arm C (note + chart) FRESH ×`replicates` each,
    in ONE run, and return the modal-stability comparison. `visual_changed` (the chart's marginal
    effect = the labelable delta) is True ONLY when BOTH arms are modal-stable across replicates AND
    the two modals differ — an arm that itself flips is noise, not a chart effect. SHADOW only; the
    live grade path never calls this (it grades once, no note/image)."""
    b = await asyncio.gather(
        *[_grade(client, sem, payload, None, CHART_AXIS_NOTE_TEXT_ONLY) for _ in range(replicates)])
    c = await asyncio.gather(
        *[_grade(client, sem, payload, png, CHART_AXIS_NOTE) for _ in range(replicates)])
    b_modal, b_stable, b_tiers = modal_stable(b)
    c_modal, c_stable, c_tiers = modal_stable(c)
    return {
        "b_modal": b_modal, "b_stable": b_stable, "b_tiers": b_tiers,
        "c_modal": c_modal, "c_stable": c_stable, "c_tiers": c_tiers,
        "b_verdict": next((v for v in b if v), None),
        "c_verdict": next((v for v in c if v), None),
        # the chart's MARGINAL visual effect (C vs B) — the real "does vision help" signal.
        "visual_changed": (b_stable and c_stable and b_modal != c_modal),
        "both_stable": b_stable and c_stable,
    }
