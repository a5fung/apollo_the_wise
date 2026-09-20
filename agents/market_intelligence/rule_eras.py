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
#   partial +2R -> +8R           2026-09-06  (#545, operator-signed — mi_strategies.profit_trigger_r)
#   breakeven ARMS ON PRICE      2026-09-06  (#545 — mi_strategies.breakeven_arm_r; the stop moves
#                                             to entry at +3 ORB-R whether or not a partial fired,
#                                             which was impossible before: breakeven only existed
#                                             inside execute_partial_exit)
# ⚠ FIRST ACTING SESSION IS **TUE 2026-09-08**, not Monday: 09-06 is a Sunday AND Mon 09-07 is
# Labor Day (NYSE closed — `trading_calendar.get_market_status` confirms it). `>=` still gives
# the right answer because no fill can occur on either day, which is the same reason the four
# dates above need no adjustment. Recorded explicitly because the ADMISSION note below exists
# precisely to stop a switch being dated to a day that admitted nothing (operator caught the
# holiday 2026-09-06; the original comment here said "Mon 09-07" and was wrong).
# ⚠⚠ THIS SWITCH IS PER-STRATEGY, WHICH IS NEW. The flip set mi_strategies.profit_trigger_r /
# breakeven_arm_r on `magna53` ONLY; every other strategy still runs the global +2R with no price
# arm. So these two functions now take `signal_type`, and it DEFAULTS to the global stack — a
# caller that does not know its strategy gets exactly today's pre-flip answer, unchanged.
PARTIAL_8R_DATE = date(2026, 9, 6)
PARTIAL_8R_VALUE = 8.0
BREAKEVEN_ARM_R_DATE = date(2026, 9, 6)
BREAKEVEN_ARM_R_VALUE = 3.0
# The strategies the 2026-09-06 flip actually touched. Adding one here is the same
# same-commit duty as the change-log entry (see MAINTENANCE RULE above).
PARTIAL_8R_SIGNAL_TYPES = frozenset({"magna53"})


def _flipped_8r(d: date, signal_type: str | None) -> bool:
    """True when the 2026-09-06 per-strategy flip governs (d, signal_type). `signal_type`
    None (the default everywhere) = the GLOBAL stack, i.e. NOT flipped — so every caller
    that does not know its strategy keeps the pre-flip answer."""
    return d >= PARTIAL_8R_DATE and signal_type in PARTIAL_8R_SIGNAL_TYPES


def exit_rules_as_of(d: date, signal_type: str | None = None) -> dict[str, Any]:
    """The exit/geometry stack live on date d for `signal_type`, as plain fields (the same
    composition `scripts/ep_replay.ruleset_as_of` builds its RuleSet from). Stored verbatim
    on every #482 row so a reader never has to re-derive the acting rule from a date.

    `signal_type` (2026-09-06, #545): the partial multiple and the breakeven arm became
    PER-STRATEGY, so a date alone no longer answers the question. Omitting it returns the
    global stack — correct for every strategy the flip did not touch, and byte-identical to
    this function's pre-2026-09-06 output for ALL dates."""
    flipped = _flipped_8r(d, signal_type)
    return {
        "stop_mode": "entry_minus_2r" if d >= STOP_2R_DATE else "orb_low",
        "intraday_partial_r": (PARTIAL_8R_VALUE if flipped
                               else (2.0 if d >= PARTIAL_LIVE_DATE else None)),
        # None = no price-armed breakeven; the stop reaches entry only at the partial.
        "breakeven_at_r": (BREAKEVEN_ARM_R_VALUE
                           if (d >= BREAKEVEN_ARM_R_DATE and flipped) else None),
        "trail_prior_closes": d >= TRAIL_PRIOR_CLOSES_DATE,
        "breakeven_at_partial": d >= BREAKEVEN_AT_PARTIAL_DATE,
        "ladder_partial": d < PARTIAL_LIVE_DATE,
        "score_separation": d >= SEP_SCORE_DATE,
    }


def exit_era_label(d: date, signal_type: str | None = None) -> str:
    """Coarse exit era: A = no executable partial (< 2026-08-01) · B = partial live, ORB-low
    stop (< 2026-08-16) · C = partial live at +2R, entry−2R stop · D = the 2026-09-06 flip
    (+8R partial, breakeven armed on price at +3R). The same taxonomy
    docs/analysis/exit_tune_cohort_review_2026-08-22.md and system_review's era-scoped setup
    review use.

    ⚠ era D is PER-STRATEGY. Without `signal_type` this returns era_c for any post-flip date,
    which is correct for every strategy the flip did not touch and is what every pre-existing
    caller already assumed. A caller stamping MAGNA53 rows MUST pass it — otherwise post-flip
    fills join the era_c cohort and pool two different exit rules, the exact defect this
    module exists to prevent."""
    if d < PARTIAL_LIVE_DATE:
        return "era_a"
    if d < STOP_2R_DATE:
        return "era_b"
    if _flipped_8r(d, signal_type):
        return "era_d"
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


# ── #662 — the weekly review's era vocabulary (plain words for the operator) ──────────────────
# The review may not print a trailing-window number without saying which rules its trades ran
# under and how many there are (PLAN #662, operator 2026-09-14). These helpers are the ONE place
# that turns the switch tables above into that sentence, so a new switch changes every consumer
# at once (the same P15 reason this module exists). `EXIT_SWITCHES` is derived from the
# constants above, never a second copy of the dates.
EXIT_SWITCHES: tuple[tuple[date, str], ...] = (
    (PARTIAL_LIVE_DATE, "the +2R intraday partial went live (#508)"),
    (TRAIL_PRIOR_CLOSES_DATE, "the trail moved to the stock's own MA and breakeven to the broker (#548)"),
    (STOP_2R_DATE, "the protective stop moved to entry−2R"),
    (SEP_SCORE_DATE, "score separation + rescale (#533)"),
    (PARTIAL_8R_DATE, "the partial moved +2R→+8R and breakeven arms at +3R, magna53 only (#545)"),
)

# One line the weekly review's fold prints once, so the A/B/C/D letters the setup review uses
# are readable without opening this file.
EXIT_ERA_KEY = (
    f"era key — A: before {PARTIAL_LIVE_DATE} (no executable partial) · "
    f"B: before {STOP_2R_DATE} (partial live, ORB-low stop) · "
    f"C: partial +2R, entry−2R stop · "
    f"D: since {PARTIAL_8R_DATE} (magna53: partial +8R, breakeven at +3R)"
)


def rule_switches_since(d: date) -> list[tuple[date, str]]:
    """Every dated rule switch — exit AND admission — that acted strictly after `d`, oldest
    first. Printed next to a data-gated review as "written <d>, N rule changes since": a ripe
    review is only actionable if its question still matches the live rule (the extension-cap
    review surfaced 'ripe 5d' on 2026-09-20 asking about a cap reverted three weeks earlier)."""
    out = [(sd, f"exit: {desc}") for sd, desc in EXIT_SWITCHES if sd > d]
    out += [(fs, f"admission: {desc}") for fs, _name, desc, _rec in ADMISSION_SWITCHES if fs > d]
    return sorted(out)


def exit_era_start(label: str) -> date | None:
    """First date of an exit-era label; None for era_a (nothing precedes it)."""
    return {"era_b": PARTIAL_LIVE_DATE, "era_c": STOP_2R_DATE, "era_d": PARTIAL_8R_DATE}.get(label)


def split_current_vs_older(values: list, meta: list[dict], today: date) -> dict[str, Any]:
    """Partition `values` (one per trade, parallel to `meta`) into the trades that ran under the
    rules live TODAY for their own strategy and those that ran under an older rule.

    `meta[i]` = {"alert_date": date, "signal_type": str | None}. "Current" is decided per trade
    as `exit_era_label(alert_date, signal_type) == exit_era_label(today, signal_type)`, so a
    strategy still on the global +2R stack is judged against ITS current rule, not magna53's.
    Returns {"current": [...], "older": [...], "current_since": date | None, "by_era": {label:
    n}}; `current_since` is the start of today's era for the strategy the cohort is mostly made
    of (None while that strategy is still on era_a)."""
    current, older = [], []
    by_era: dict[str, int] = {}
    sig_counts: dict[str | None, int] = {}
    for v, m in zip(values, meta):
        d, sig = m.get("alert_date"), m.get("signal_type")
        label = exit_era_label(d, sig)
        by_era[label] = by_era.get(label, 0) + 1
        sig_counts[sig] = sig_counts.get(sig, 0) + 1
        (current if label == exit_era_label(today, sig) else older).append(v)
    main_sig = max(sig_counts, key=sig_counts.get) if sig_counts else None
    return {"current": current, "older": older,
            "current_since": exit_era_start(exit_era_label(today, main_sig)),
            "by_era": dict(sorted(by_era.items()))}


def era_split_sentence(split: dict[str, Any], *, noun: str = "trades") -> str:
    """The plain-words clause every trailing-window line carries: `under the current rules
    (since 2026-09-06): 2 trades · older rules: 28 trades`."""
    since = split.get("current_since")
    since_s = f" (since {since})" if since else ""
    return (f"under the current rules{since_s}: {len(split['current'])} {noun} · "
            f"older rules: {len(split['older'])} {noun}")
