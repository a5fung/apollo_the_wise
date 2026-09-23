"""alert_rank_shadow_out_of_sample — RUNNING READ scorer + renderer (2026-08-18).

`data_gated_reviews.yaml`'s `alert_rank_shadow_out_of_sample` review used to fire ONCE,
gated on 25 out-of-sample sessions, earliest 2026-10-15. Per the operator's BIAS FOR
ACTION rule (`docs/roadmap/ep_profitability_program.md` GOAL section, 2026-08-18):

    "unless there's no reason to take action or risk is too high, we should bias for
    action" — a gated read that stays silent until October, on a ranking rule we
    already suspect may not survive out-of-sample, is exactly the wrong shape.

This module is modelled on `stop_2r_running_comparison`'s shape (deliberately
UNGATED, read from the first closed trade). Converted here: report from the FIRST
out-of-sample session, with n and a confidence label stated every time so a thin
read can never be mistaken for a verdict. 25 sessions remains the DECISION-GRADE
mark — a maturity label carried in the text, never the gate that makes the review
surface.

SELECTION RULE (same GOAL section, 2026-08-18): "SELECTION IS BROADER THAN 'DO WE
FIND THEM'" — a read must score BOTH winners admitted and losers excluded. A change
that surfaces the SAME winners while admitting FEWER losers is a real gain and a
numerator-only ("how many winners did we catch") measure scores it as zero. Every
render here reports both directions; `score_both_directions` is the mechanised form
of that rule so it cannot silently regress to a numerator-only comparison.

THE LINE: this is a pure, DB-free reporting/scoring module. It takes numbers in
(already pulled by a read-only query — see the 2026-08-18 rehearsal artifacts:
`scripts/probes/_rehearsal_rank_shadow_join_2026-08-18.sql` +
`_rehearsal_rank_shadow_analysis_2026-08-18.py`, which proved the join from
`mi_alert_rank_shadow` to a forward outcome executes and produces a number) and
returns a formatted verdict out. No DB access, no writes, and nothing in any
grading/entry/sizing/ordering path reads this module or its output.
"""
from __future__ import annotations

from dataclasses import dataclass

# Matches the shadow's original one-shot gate (25 sessions) — now a maturity LABEL
# on the running read, never the condition that makes it surface at all.
DECISION_GRADE_SESSIONS = 25


def confidence_label(n_sessions: int, decision_grade_sessions: int = DECISION_GRADE_SESSIONS) -> str:
    """A thin read must never read as a verdict — n and confidence stated EVERY time.
    `n_sessions` = COUNT(DISTINCT alert_date) WHERE alert_date > 2026-08-16 (the
    shadow's live date) — the same population the review's own predicate_sql counts,
    so this label and the registry's surfacing gate always agree on what "n" means.
    """
    if n_sessions <= 0:
        return "NO DATA YET"
    if n_sessions < decision_grade_sessions:
        pct = round(100 * n_sessions / decision_grade_sessions)
        return (
            f"THIN (n={n_sessions} of {decision_grade_sessions} decision-grade sessions, "
            f"{pct}%) -- directional only, NOT a verdict"
        )
    return f"DECISION-GRADE (n={n_sessions} >= {decision_grade_sessions} sessions)"


@dataclass(frozen=True)
class CohortRead:
    """One side of a both-directions comparison (e.g. the top-quartile-by-composite-
    rank cohort vs the rest of the pool). n=0 is a legal, distinct state from n>0 with
    zero winners — callers must not coerce it to a rate silently (see
    `score_both_directions`'s explicit n==0 guard).
    """
    n: int
    winners_admitted: int   # count reaching the tail bar (>=10R / >=8xADR — whichever the caller scored)
    losers_admitted: int    # count that breached the loser bar (e.g. broke the EP-day low) — the complement of "excluded"


def score_both_directions(candidate: CohortRead, baseline: CohortRead) -> str:
    """Mechanises the SELECTION rule: never scores on winners alone. A candidate that
    holds or improves winners AND admits losers at a LOWER rate than baseline is a
    GAIN — including when winners are UNCHANGED, which a numerator-only ("how many
    winners did we surface") comparison would score as a wash or worse.
    """
    if candidate.n == 0 or baseline.n == 0:
        return "INSUFFICIENT N ON ONE SIDE -- cannot score either direction yet"
    cand_loser_rate = candidate.losers_admitted / candidate.n
    base_loser_rate = baseline.losers_admitted / baseline.n
    winners_delta = candidate.winners_admitted - baseline.winners_admitted
    # Explicit 3x3 over (winners direction, loser-RATE direction) — every cell named.
    # The cascade this replaces (simplify review 2026-08-18) left the both-unchanged
    # cell falling into a MIXED branch whose text claimed "winners and losers moved in
    # opposite directions" when in fact NOTHING had moved. A running read that speaks
    # from n=1 must never mislabel "no change" as a directional finding.
    w = (winners_delta > 0) - (winners_delta < 0)          # +1 / 0 / -1
    l = (cand_loser_rate > base_loser_rate) - (cand_loser_rate < base_loser_rate)
    return {
        (+1, -1): "GAIN -- more winners AND losers admitted at a lower rate",
        (+1, 0): "GAIN -- more winners, losers admitted at the same rate",
        (+1, +1): "MIXED -- more winners but also more losers; report both numbers, "
                  "do not net them into one verdict",
        (0, -1): "GAIN -- same winners, FEWER losers admitted. This is a real gain and "
                 "a winners-only comparison would score it as a wash (SELECTION rule)",
        (0, 0): "NO CHANGE -- winners and loser rate both unchanged",
        (0, +1): "LOSS -- same winners but MORE losers admitted",
        (-1, -1): "MIXED -- fewer winners but fewer losers too; report both numbers, "
                  "do not net them into one verdict",
        (-1, 0): "LOSS -- fewer winners, losers admitted at the same rate",
        (-1, +1): "LOSS -- fewer winners AND more losers admitted",
    }[(w, l)]


def render_running_read(
    n_sessions: int,
    top_quartile: CohortRead,
    rest_of_pool: CohortRead,
    decision_grade_sessions: int = DECISION_GRADE_SESSIONS,
) -> str:
    """The line `action_when_ready` on `alert_rank_shadow_out_of_sample` points at.
    n + confidence ALWAYS stated first; both directions always reported against the
    rest-of-pool baseline (never a numerator-only winner count).
    """
    conf = confidence_label(n_sessions, decision_grade_sessions)
    verdict = score_both_directions(top_quartile, rest_of_pool)
    return (
        f"alert_rank_shadow running read: n={n_sessions} out-of-sample session(s) -- {conf}. "
        f"Top-quartile: n={top_quartile.n}, winners={top_quartile.winners_admitted}, "
        f"losers-admitted={top_quartile.losers_admitted}/{top_quartile.n}. "
        f"Rest-of-pool: n={rest_of_pool.n}, winners={rest_of_pool.winners_admitted}, "
        f"losers-admitted={rest_of_pool.losers_admitted}/{rest_of_pool.n}. "
        f"Verdict vs rest-of-pool: {verdict}"
    )
