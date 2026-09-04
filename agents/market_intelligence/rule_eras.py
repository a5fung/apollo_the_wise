"""Dated rule-era switch tables — the ONE place that answers "which rules were live on date d".

WHY ONE MODULE (2026-09-03, #482). Three copies of the same exit-era boundaries already
existed: `scripts/ep_replay.py`'s switch table, `system_review.py`'s two `_*_ERA_START`
pins, and the SQL literal in `data_gated_reviews.yaml`. P15 (ep_profitability_program.md):
a value that changes meaning must move every consumer together, and a second copy is a
fork. The YAML literal cannot import Python and stays a documented duplicate; the other
two now read from here. The #482 live-fill counterfactual recorder stamps every row it
writes from these tables, so a later reader can SEGMENT by era instead of pooling — the
exact defect that produced the 08-16-vs-Phase-3 stop flip-flop (two populations, nothing
said so).

TWO TABLES, TWO QUESTIONS:
  EXIT / GEOMETRY  — which stop, partial, trail and breakeven rule governed a fill's exit.
                     `exit_rules_as_of(d)` composes the stack; `exit_era_label(d)` is the
                     coarse A/B/C label the weekly review and exit_tune gate already use.
  ADMISSION        — which selection stack ADMITTED the name. The operator's own
                     requirement for #482: "we'll be updating our filters as we observe
                     live EPs ... if I see we miss one I'd suggest it so we can update to
                     catch it" — so the admitted population WILL move under any forward
                     recorder, and every row must say which filter set produced it.
                     `admission_era_as_of(d)` returns a label naming the latest switch.

MAINTENANCE RULE (same-commit, like P15's "adding a criterion means adding the sentence"):
an admission-criterion change lands as a `### <date>` change-log entry in
`docs/setups/magna53_ep.md` AND a row in ADMISSION_SWITCHES below, in the same commit.
`tests/test_live_fill_counterfactuals.py` pins the forward direction (every row here must
cite a dated heading that exists in that change log); the reverse — a new admission change
with no row here — is NOT mechanically decidable and is the one thing a reader must still
check by eye (the row's `description` says what changed so a missing later switch is
visible as "the label stopped moving").

Pure: dates and string composition only. No DB, no I/O, no imports beyond the stdlib.
"""
from __future__ import annotations

from datetime import date
from typing import Any

# ── EXIT / GEOMETRY switches (moved verbatim from scripts/ep_replay.py, 2026-09-03) ──
# Provenance for every line:
#   score separation + rescale   2026-08-22  (#533, operator-signed; magna53_ep.md change log)
#   protective stop entry−2R     2026-08-16  (operator-signed; order_manager ~L481)
#   +2R intraday partial live    2026-08-01  (#508, constants.PROFIT_TRIGGER_R)
#   trail uses stock's own MA    2026-08-08  (#548, prior_closes)
#   breakeven AT the broker      2026-08-08  (#548 ships the partial's breakeven move at the
#                                             broker — FIGS 08-07 stopped at the ORIGINAL stop
#                                             after its partial (pre), ETON 08-14 / CRWD 08-28
#                                             stopped at BREAKEVEN (post))
SEP_SCORE_DATE = date(2026, 8, 22)
STOP_2R_DATE = date(2026, 8, 16)
PARTIAL_LIVE_DATE = date(2026, 8, 1)
TRAIL_PRIOR_CLOSES_DATE = date(2026, 8, 8)
BREAKEVEN_AT_PARTIAL_DATE = date(2026, 8, 8)


def exit_rules_as_of(d: date) -> dict[str, Any]:
    """The exit/geometry stack live on date d, as plain fields (the same composition
    `scripts/ep_replay.ruleset_as_of` builds its RuleSet from). Stored verbatim on every
    #482 row so a reader never has to re-derive the acting rule from a date."""
    return {
        "stop_mode": "entry_minus_2r" if d >= STOP_2R_DATE else "orb_low",
        "intraday_partial_r": 2.0 if d >= PARTIAL_LIVE_DATE else None,
        "trail_prior_closes": d >= TRAIL_PRIOR_CLOSES_DATE,
        "breakeven_at_partial": d >= BREAKEVEN_AT_PARTIAL_DATE,
        "ladder_partial": d < PARTIAL_LIVE_DATE,
        "score_separation": d >= SEP_SCORE_DATE,
    }


def exit_era_label(d: date) -> str:
    """Coarse exit era: A = no executable partial (< 2026-08-01) · B = partial live, ORB-low
    stop (< 2026-08-16) · C = partial live, entry−2R stop (the current stack). The same
    taxonomy docs/analysis/exit_tune_cohort_review_2026-08-22.md and system_review's
    era-scoped setup review use."""
    if d < PARTIAL_LIVE_DATE:
        return "era_a"
    if d < STOP_2R_DATE:
        return "era_b"
    return "era_c"


# ── ADMISSION switches — what changed WHO gets admitted (magna53_ep.md change log) ──
# ⚠ THE DATE IS THE FIRST SESSION WHOSE ORB ADMISSION RAN UNDER THE RULE — not the day the
# change was signed or deployed. Every MAGNA53 fill happens 09:31–09:45 ET; a rule that
# flipped at 11:02 ET (08-25), 13:55 ET (08-27) or shipped in the 12:00 window (08-19,
# commit 15:37 ET) admitted NOTHING that day — the fills of that day were admitted by the
# OLD stack. Labelling them with the new rule is exactly the mislabel this stamp exists to
# prevent (caught in review 2026-09-03). Weekend deploys (08-22 Sat, 08-29 Sat, 08-30 Sun)
# act on the following Monday; the two weekend changes before 08-31 share one row because
# no fill can tell them apart. Contrast the EXIT switches above: 08-01 / 08-08 / 08-16 /
# 08-22 are all weekend dates, so `>=` there already equals first-acting-session — do not
# "fix" them.
# Tuple: (first acting session, short name, what changed + when it flipped (one plain
#         sentence, P15-A), the `### <date>` change-log heading in magna53_ep.md that records it)
ADMISSION_SWITCHES: tuple[tuple[date, str, str, date], ...] = (
    (date(2026, 8, 20), "gap_floor_9",
     "MIN_GAP_PCT lowered 10% -> 9% (operator-signed; committed 2026-08-19 15:37 ET, after "
     "that day's ORB window)", date(2026, 8, 19)),
    (date(2026, 8, 24), "lattice_separation_shortlist",
     "catalyst tier flipped to the corrected lattice; separation score with a uniform HIGH "
     "bar; grading shortlist ranked by pre-score; extension cap 50% -> 75% (#533/#577A; "
     "deployed Sat 2026-08-22)", date(2026, 8, 22)),
    (date(2026, 8, 26), "rt_universe_authoritative",
     "ep_rt_universe_authoritative went live 2026-08-25 11:02 ET (real-time universe "
     "membership) — recorded under the 08-28 status record", date(2026, 8, 28)),
    (date(2026, 8, 28), "rubric_v4_rt_gap_authority",
     "judge rubric v3 -> v4; real-time gap decides the 9% floor both ways (13:55 ET); "
     "real-time volume authoritative (11:19 ET); Perplexity agreement boost retired — all "
     "2026-08-27, after that day's ORB window (#602/#559/#233)", date(2026, 8, 27)),
    (date(2026, 8, 31), "extension_cap_50_slot_rank_rs",
     "MAX_EXTENSION_PCT reverted 75% -> 50% (Sat 2026-08-29) and within-day slot ranking "
     "flipped from alphabetical to prior-day RS (Sun 2026-08-30, #533) — one acting session",
     date(2026, 8, 29)),
)
# ⚠ #624 (2026-09-04) — the LOW-CAP LANE SHADOW deliberately has NO row here, and this is
# the "check by eye" note the maintenance rule above asks for. Its magna53_ep.md change-log
# entry (### 2026-09-04) records a RECORDER, not an admission change: the lane writes
# mi_lowcap_lane_signals / mi_lowcap_lane_replays and admits nothing — MAGNA53's filter set
# is byte-identical with the hook on or off (test-pinned). A row here would relabel every
# MAGNA53 fill from that session as a new era with an identical stack, splitting the
# #482/#593/#617 `admission_era` segmentation for nothing. The lane's own rows stamp
# admission_era_as_of(session_date) so they segment on MAGNA53's real switches. The row
# LANDS WITH THE PAPER FLIP (`/strategy magna53_lowcap promote`) — that IS a change to who
# gets admitted, and needs its own dated change-log entry + a row on the same commit.
PRE_SWITCH_ADMISSION_ERA = "adm_pre_2026-08-20"


def admission_era_as_of(d: date) -> str:
    """Label of the LATEST admission switch whose first acting session is on or before d —
    e.g. a fill on 2026-08-27 reads `adm_2026-08-26_rt_universe_authoritative` (the rubric-v4
    stack flipped at 13:55 ET that day, after the fill), a fill on 2026-08-28 reads
    `adm_2026-08-28_rubric_v4_rt_gap_authority`. Two rows with different labels were
    admitted by different filter sets and must not be pooled without saying so."""
    label = PRE_SWITCH_ADMISSION_ERA
    for first_session, name, _desc, _recorded_under in ADMISSION_SWITCHES:
        if d >= first_session:
            label = f"adm_{first_session.isoformat()}_{name}"
    return label
