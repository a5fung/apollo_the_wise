"""THE CHART-RULING FIXTURE — operator verdicts on SPECIFIC (ticker, DATE) pairs.

The mirror image of `must_not_miss_eps.py`. Where that file records charts the system must
never MISS, this file records the operator's verdicts on charts he was shown and asked to
judge — including the ones he ruled must never be TRADED. Both halves are needed: a filter
judged only on what it admits cannot be judged at all, and a filter judged only on what it
rejects will reject everything.

RULE 0 / P1 still applies and still dominates. A false EXCLUSION leaves no row, no
skip_reason and no trace, so the asymmetry is unchanged: rejecting one of the 26 real EPs in
`must_not_miss_eps.py` is a worse error than admitting one of the eleven BAD_CHART members
below. Nothing in this file may be used to justify a rejection that costs a
`must_not_miss_eps.py` member.

──────────────────────────────────────────────────────────────────────────────────────────
🔴 THE CENTRAL FINDING THIS FILE'S SHAPE ENCODES: HE IS JUDGING THE DATE, NOT THE TICKER.

Across every ruling he has given, the same name is a good setup on one day and a bad one a
week later — and the tradeable day is frequently NOT the day our system evaluated:

    CAR   — the 04-22 chart is horrendous, but "ok'ish if the EP alert day was earlier,
             e.g. CAR on 4/1"          → the right day is EARLIER than the one we scanned.
    MXL   — 04-21 "looks better for delayed entry, there's 3 tight days prior to the big
             gap on 4/24"              → the right day is LATER than the one we scanned.
    ARQQ  — "arqq is decent, but still within bottoming base"
                                        → right chart, wrong STAGE. Not a bad chart.
    AEHR  — a labelled REAL EP on 2026-03-31 (`must_not_miss_eps.py`) and a labelled
             horrendous chart on 2026-08-14, here. Same ticker, opposite verdicts.

Our system evaluates a name on the day it gaps. His judgement says the tradeable day is
often a different one. **So every member below is keyed on (ticker, date), every verdict is
a verdict about that DATE, and `better_date` points at the day he thinks WAS right whenever
he named one — because that pointer, not the reject flag, is the signal worth training on.**

──────────────────────────────────────────────────────────────────────────────────────────
THE VERDICT VOCABULARY — four distinct labels. ⚠ NEVER COLLAPSE THEM. "Bad chart", "right
chart wrong stage" and "right chart wrong day" are three different failures with three
different fixes, and treating them as one reject bucket throws away the whole signal.

  BAD_CHART              — "these are horrendous charts". Do not trade this date. (11)
  OKISH_EARLIER          — the earlier, acceptable version of a move he condemned later. He
                           does NOT want this one filtered out. A must-NOT-reject anchor
                           that is not strong enough to be a `must_not_miss_eps.py` member. (1)
  WRONG_STAGE            — the chart is fine, the name is not ready. Not a buy, not junk. (1)
  WRONG_DAY              — right chart, wrong date; the setup is elsewhere. `better_date`
                           carries the date he named, and THAT date is a must-NOT-reject
                           anchor in its own right. (1)
  NO_SETUP_ON_THIS_DATE  — the date carries no setup at all, so any outcome attributed to it
                           is a measurement artifact rather than a chart judgement. (1)

🔴 `NO_SETUP_ON_THIS_DATE` RECORDS A MEASUREMENT DEFECT, NOT A CHART OPINION. VEEE
2026-07-08 was shown in a "we rejected this and it ran +354%" sample. It gapped **+4.1%**
(prior close 5.63, open 5.86) — under our own 9% floor — and CLOSED that day at 4.64, down
21% from its own open. The +354% belongs to 2026-07-13, when it opened at 12.24 against a
4.82 close, an unrelated event five sessions later. Our missed-outcome numbers measure
forward returns from a date's OPEN over the following sessions, so a later, separate
explosion is attributed to a date that had no setup — which inflates every "we missed this"
claim built on them. Verified from `mi_daily_closes` bars, 2026-08-25. **Recorded here, NOT
fixed here — it needs its own task and it is not a chart-reading problem.**

──────────────────────────────────────────────────────────────────────────────────────────
WHERE THESE LABELS CAME FROM — operator, in conversation, 2026-08-25.

He was shown the worst calls made by the v2 supply-ladder read
(`docs/analysis/structure_read_backtest_2026-08-25.md` §6 — name-days the read scored as
clean that then fell 18-98%, and name-days it scored as buried that then ran). His verdict
on the first list, verbatim:

    "these are horrendous charts"

and then the qualification that names the actual mechanism, verbatim:

    "some of them are ok'ish if the EP alert day was earlier, e.g. CAR on 4/1"

The same restatement of the objective was given the same day, verbatim:

    "The first bar I want it to clear is to filter out the bad charts, like CAPR. I want to
     make sure we don't trade these poor charts, that's the first objective."

──────────────────────────────────────────────────────────────────────────────────────────
🛑 WHAT THIS FILE IS NOT. It is NOT a rule, a gate, a cutline or a policy, and the test that
reads it asserts nothing about admission. Detection criteria are the operator's sole
authority (THE LINE). `live_stack_exclusion` below records, as DATA, which gate actually
rejected each name-day at the time — because the first thing anyone must know before
proposing a new filter is that **the live stack already rejected all eleven BAD_CHART
members**. That field is a measurement of the past, not a requirement on the future: if the
operator later loosens a gate and one of these becomes admissible, that is his call and this
file records the fact rather than blocking it.

⚠ LABELS MUST BE OPERATOR-SOURCED, NEVER INFERENCE — the same rule as `must_not_miss_eps.py`.
Every member carries `label_source`, and for this file every member is "operator". No member
here was added by an agent's own judgement of what a bad chart is. Numeric fields ARE
agent-computed and are labelled as such; only the VERDICT is his.

HOW TO ADD A MEMBER — one line, no code change: append a `ChartRuling(...)` to
`CHART_RULINGS`. Record his words in `operator_words` whenever he said something specific
about that name, and set `better_date` whenever he named a date he thinks was right.
──────────────────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from typing import NamedTuple, Optional

RULING_DATE = "2026-08-25"          # session 1 — the original eleven
# 2026-09-06: rulings now arrive in SESSIONS, so a single RULING_DATE no longer describes
# the file. Session 1 is the eleven horrendous charts he was first shown; session 2 is
# review sample #1 (ten names where our score and the outcome disagreed). Every member
# carries its own `ruling_date`; this set is what a test may check membership against, so
# a typo cannot invent a session that never happened.
RULING_SESSIONS = frozenset({"2026-08-25", "2026-09-06"})
# The eleven BAD_CHART members of session 1 are the population the v3 backtest measured.
# Later BAD_CHART rulings are NOT in it — the doc's numbers are against these only.
V3_MEASURED_POPULATION_SIZE = 11

OPERATOR_VERDICT_ON_THE_LIST = "these are horrendous charts"
OPERATOR_QUALIFICATION = (
    "some of them are ok'ish if the EP alert day was earlier, e.g. CAR on 4/1"
)
OPERATOR_OBJECTIVE = (
    "The first bar I want it to clear is to filter out the bad charts, like CAPR. "
    "I want to make sure we don't trade these poor charts, that's the first objective."
)

# The verdict vocabulary — see the module docstring. Never collapse these into one bucket.
BAD_CHART = "BAD_CHART"
OKISH_EARLIER = "OKISH_EARLIER"
WRONG_STAGE = "WRONG_STAGE"
WRONG_DAY = "WRONG_DAY"
NO_SETUP_ON_THIS_DATE = "NO_SETUP_ON_THIS_DATE"
# 2026-09-06: the vocabulary had NO positive label. Every verdict above is a way of saying
# no, because until review sample #1 he had only ever been shown charts to reject. On that
# sample he called RNG 2026-07-24 "looks great" and OMER 2026-07-27 "ok'ish" — the first
# times he has approved a surfaced DATE outright. Forcing those into OKISH_EARLIER would
# have been wrong twice over: that label means "the earlier version of a move condemned
# later", and neither is that. A file that can only record rejections trains a filter that
# only knows how to reject.
GOOD_CHART = "GOOD_CHART"        # he approved THIS date. The strongest must-not-reject.
OKISH_CHART = "OKISH_CHART"      # approved with a named reservation ("ok'ish, but…").

VERDICTS = frozenset({BAD_CHART, OKISH_EARLIER, WRONG_STAGE, WRONG_DAY,
                      NO_SETUP_ON_THIS_DATE, GOOD_CHART, OKISH_CHART})

# Verdicts that mean "he does NOT want this date filtered out" — the must-NOT-reject side
# contributed by this file, over and above the 26 members of `must_not_miss_eps.py`.
# ⚠ WRONG_DAY's own date IS rejectable (he said the setup is elsewhere); it is the
# `better_date` it points at that must not be rejected. That asymmetry is deliberate.
MUST_NOT_REJECT_VERDICTS = frozenset({OKISH_EARLIER, GOOD_CHART, OKISH_CHART})

# `better_date` provenance — see ChartRuling.better_date_provenance.
STATED = "STATED"            # he said this date was good
POINTED_AT = "POINTED_AT"    # he referred to it; he did NOT rule it tradeable


class ChartRuling(NamedTuple):
    ticker: str
    alert_date: str              # ISO "YYYY-MM-DD" — the DATE being judged, not the ticker
    verdict: str                 # one of VERDICTS
    label_source: str            # "operator" — never inference
    ruling_date: str             # the day the operator gave the label
    operator_words: Optional[str]  # verbatim, whatever he said about THIS name

    # The date he named as the one that WAS right, when he named one. This is the pointer
    # worth training on: for CAR he pointed earlier, for MXL later.
    better_date: Optional[str] = None
    better_date_note: Optional[str] = None
    # ⚠ Is `better_date` a date he said was TRADEABLE, or only a date he POINTED AT?
    # "STATED" = he called it good. "POINTED_AT" = he referred to it while explaining why
    # the scanned date was wrong, without ruling on it. Treating POINTED_AT as an operator
    # must-not-reject label would be agent inference wearing his name — the exact thing
    # this file forbids — so the two are kept apart and only STATED feeds
    # MUST_NOT_REJECT_DATES.
    better_date_provenance: Optional[str] = None

    # ── What the chart did. Agent-computed from mi_ep_missed_outcomes / mi_daily_closes,
    #    NOT operator-supplied. ──────────────────────────────────────────────────────────
    gap_open_pct: Optional[float] = None    # session open vs prior close, the fixture basis
    ret_5d: Optional[float] = None          # 5-session close vs the gap-day OPEN (a fraction)
    prior_runup_note: Optional[str] = None  # what the scan log said it had already done

    # ── The read's verdict AT LABEL TIME, so agreement and disagreement stay recoverable
    #    later (the shape `must_not_miss_eps.py` uses for its own gate metrics). ─────────
    v2_label: Optional[str] = None
    v2_overhead_vol_frac: Optional[float] = None
    v2_zones_remaining: Optional[int] = None

    # ── Which live gate ACTUALLY rejected this name-day, as recorded in mi_ep_scan_log.
    #    Data, not a requirement. `None` means the live stack did not reject it here. ────
    live_stack_exclusion: Optional[str] = None
    # The live extension gate's own value, recomputed point-in-time on the live basis
    # (MIN close over [alert_date - 10 calendar days, alert_date), vs prior close).
    # `MAX_EXTENSION_PCT` is 75.0 since 2026-08-22 (operator-signed), 50.0 before.
    extension_live_pct: Optional[float] = None


# ══════════════════════════════════════════════════════════════════════════════════════
# THE RULINGS. BAD_CHART members are ordered worst-first by 5-session return, as they were
# shown to him; the other verdicts follow.
#
# gap_open_pct / ret_5d / v2_* / live_stack_exclusion are read from
# scripts/probes/_srbt_review_sample.psv (the file he was shown); extension_live_pct and
# every other number are recomputed from mi_daily_closes bars by
# scripts/probes/_structure_read_v3.py.
# ══════════════════════════════════════════════════════════════════════════════════════
CHART_RULINGS: list[ChartRuling] = [
    # ══════════════════════════════════════════════════════════════════════════════════
    # REVIEW SAMPLE #1 — 2026-09-06. Ten (ticker, date) pairs surfaced because our SCORE
    # and the OUTCOME disagreed; he ruled on all ten. Verbatim words are in
    # docs/methodology/operator_shared_notes.md § "EIGHT CHART RULINGS".
    #
    # 🔑 HIS OWN READ OF THE SET: "looks like our chart vision is spotting the opposite
    # thing." All FIVE names our scorer graded HIGH and which then collapsed are, by his
    # eye, bad charts — 5 of 5. He would have rejected every one on sight.
    # ⚠ The reverse is NOT symmetric and must not be reported as an inversion: of the five
    # we scored BELOW the bar that then ran, he approves only RNG (+39%) and OMER (+70%)
    # and calls ABVX (+60%), CGEM (+39%) and AVAH (+37%) garbage. So his eye is strong at
    # refusing losers and mixed at catching winners — exactly the asymmetry RULE 0 assumes.
    # ══════════════════════════════════════════════════════════════════════════════════
    ChartRuling(
        ticker="NVTX", alert_date="2026-06-03", verdict=BAD_CHART,
        label_source="operator", ruling_date="2026-09-06",
        operator_words=("chart is ok but there's a double top from Oct 2025 that it didn't "
                        "clear, in fact, that probably played out as resistance and it failed"),
        gap_open_pct=37.7, ret_5d=None,
        prior_runup_note=("our score: 62.4 HIGH, catalyst=routine. Settled -81% at 20 sessions. "
                          "⚠ THE BINDING LEVEL IS EIGHT MONTHS OLD — an Oct-2025 double top. No "
                          "lookback we currently compute reaches it."),
    ),
    ChartRuling(
        ticker="NVTS", alert_date="2026-06-03", verdict=BAD_CHART,
        label_source="operator", ruling_date="2026-09-06",
        operator_words=("looked good for one day but it failed to make new highs and quickly "
                        "dropped lower, closed on bottom of range on EP day. It was still ok "
                        "until 3rd day it opened and dropped all day to close at lows."),
        gap_open_pct=15.4, ret_5d=None,
        prior_runup_note=("our score: 84 HIGH, catalyst=strong. Settled -53%. THE SAME-DAY TELL "
                          "IS CLOSE-WITHIN-RANGE: 'closed on bottom of range on EP day' — a "
                          "computable day-0 fact we do not score."),
    ),
    ChartRuling(
        ticker="MRLN", alert_date="2026-06-05", verdict=BAD_CHART,
        label_source="operator", ruling_date="2026-09-06",
        operator_words=("garbage chart, in downtrend, gapped didn't clear anothing, clear "
                        "resistance and chop in the area, poor chart"),
        gap_open_pct=28.0, ret_5d=None,
        prior_runup_note="our score: 80 HIGH, catalyst=strong. Settled -49%. Prior TREND is the first cut.",
    ),
    ChartRuling(
        ticker="AVGU", alert_date="2026-06-02", verdict=BAD_CHART,
        label_source="operator", ruling_date="2026-09-06",
        operator_words="avgu and crwg, missed those but they look like garbage as well",
        gap_open_pct=13.1, ret_5d=None,
        prior_runup_note="our score: 42 HIGH-tier alert, catalyst=routine. Settled -44%.",
    ),
    ChartRuling(
        ticker="CRWG", alert_date="2026-06-01", verdict=BAD_CHART,
        label_source="operator", ruling_date="2026-09-06",
        operator_words="avgu and crwg, missed those but they look like garbage as well",
        gap_open_pct=10.3, ret_5d=None,
        prior_runup_note="our score: 44.4 HIGH-tier alert, catalyst=routine. Settled -40%.",
    ),
    ChartRuling(
        ticker="ABVX", alert_date="2026-06-03", verdict=BAD_CHART,
        label_source="operator", ruling_date="2026-09-06",
        operator_words="absolute garbage",
        gap_open_pct=13.8, ret_5d=None,
        prior_runup_note=("⚠ THIS ONE RAN: +60% at 20 sessions, and we had ALREADY rejected it "
                          "(score 43 < 50). He still calls the chart garbage. A profitable "
                          "outcome does NOT make it a chart he wants — do not treat this row as "
                          "a miss."),
    ),
    ChartRuling(
        ticker="CGEM", alert_date="2026-06-08", verdict=WRONG_DAY,
        label_source="operator", ruling_date="2026-09-06",
        operator_words="cgem on 6/8 is garbage, possible EP day is 6/22",
        better_date="2026-06-22", better_date_provenance=POINTED_AT,
        better_date_note=("he says 'POSSIBLE EP day' — a pointer, not a ruling, so it does NOT "
                          "enter MUST_NOT_REJECT_DATES."),
        gap_open_pct=10.6, ret_5d=None,
        prior_runup_note="our score: 42, catalyst=strong, rejected. Settled +39% — but on the wrong date.",
    ),
    ChartRuling(
        ticker="AVAH", alert_date="2026-06-02", verdict=WRONG_DAY,
        label_source="operator", ruling_date="2026-09-06",
        operator_words=("Avah - 6/2 day looks like garbage, gap on 8/13 looks excellent, cleared "
                        "everything and into new highs, sitll holding up"),
        better_date="2026-08-13", better_date_provenance=STATED,
        better_date_note=("STATED, not pointed at: 'looks excellent… cleared everything and into "
                          "new highs'. 08-13 is a must-not-reject date."),
        gap_open_pct=12.1, ret_5d=None,
        prior_runup_note="our score: 33.1, rejected. The scanned date settled +37% — still the wrong day.",
    ),
    ChartRuling(
        ticker="OMER", alert_date="2026-07-27", verdict=OKISH_CHART,
        label_source="operator", ruling_date="2026-09-06",
        operator_words=("ok'ish, didn't clear level and still in base but did clear all key "
                        "moving averages 10/20/50 and 200 day. Another good gap up on 8/13 "
                        "which held"),
        better_date="2026-08-13", better_date_provenance=STATED,
        better_date_note="'Another good gap up on 8/13 which held' — a second approved date on the same name.",
        gap_open_pct=16.8, ret_5d=None,
        prior_runup_note=("WE REJECTED IT: score 38 < 50, catalyst=routine. Settled +70% — the "
                          "biggest winner in the sample. CLEARING THE 10/20/50/200 MAs is what "
                          "lifts it from garbage to ok'ish DESPITE failing his first criterion."),
    ),
    ChartRuling(
        ticker="RNG", alert_date="2026-07-24", verdict=GOOD_CHART,
        label_source="operator", ruling_date="2026-09-06",
        operator_words=("looks good, stock been in a long base since 2022 and this gap cleared "
                        "most of it into top of previous range highs over multiple years, closed "
                        "near high of day and just kept going, moved above all moving averages "
                        "on gap day, looks great"),
        gap_open_pct=20.7, ret_5d=None,
        prior_runup_note=("⚠ WE REJECTED IT — score 37 < 50, catalyst=routine — and it settled "
                          "+39%. THE FIRST DATE HE HAS EVER CALLED OUTRIGHT GOOD, and our scorer "
                          "put it below the bar. His four reasons are all structural and none is "
                          "in our score: a base since 2022, the gap clearing MOST of it into "
                          "multi-year range highs, a close near the day's high, and above every "
                          "moving average on the gap day."),
    ),
    # ── BAD_CHART — "these are horrendous charts" (11) ────────────────────────────────
    ChartRuling(
        ticker="GDC", alert_date="2026-05-06", verdict=BAD_CHART,
        label_source="operator", ruling_date=RULING_DATE, operator_words=None,
        gap_open_pct=25.21, ret_5d=-0.9793,
        prior_runup_note="already up 77% in the prior 5 sessions",
        v2_label="CLEAR_AIR", v2_overhead_vol_frac=0.0000, v2_zones_remaining=0,
        live_stack_exclusion="already up 77% in prior 5 days (extended)",
        extension_live_pct=76.7,
    ),
    ChartRuling(
        ticker="CAR", alert_date="2026-04-22", verdict=BAD_CHART,
        label_source="operator", ruling_date=RULING_DATE,
        operator_words=OPERATOR_QUALIFICATION,
        better_date="2026-04-01", better_date_provenance=STATED,
        better_date_note=("He named CAR on 4/1 as the ok'ish earlier version of this move. "
                          "STATED — it has its own OKISH_EARLIER ruling below."),
        gap_open_pct=8.55, ret_5d=-0.7663,
        prior_runup_note="already up 92% in the prior 5 sessions",
        v2_label="CLEAR_AIR", v2_overhead_vol_frac=0.0000, v2_zones_remaining=0,
        live_stack_exclusion="already up 92% in prior 5 days (extended)",
        extension_live_pct=92.4,
    ),
    ChartRuling(
        ticker="CAR", alert_date="2026-04-21", verdict=BAD_CHART,
        label_source="operator", ruling_date=RULING_DATE,
        operator_words=OPERATOR_QUALIFICATION,
        better_date="2026-04-01", better_date_provenance=STATED,
        better_date_note=("Same move as the 04-22 row; the same earlier date is the good "
                          "one. STATED — it has its own OKISH_EARLIER ruling below."),
        gap_open_pct=2.50, ret_5d=-0.7083,
        prior_runup_note="up 64% in the prior 5 sessions on the live gate's own basis",
        v2_label="CLEAR_AIR", v2_overhead_vol_frac=0.0000, v2_zones_remaining=0,
        live_stack_exclusion="low volume rel_vol 0.1x < 2.0x (post-open)",
        extension_live_pct=64.1,
    ),
    ChartRuling(
        ticker="ADVB", alert_date="2026-07-24", verdict=BAD_CHART,
        label_source="operator", ruling_date=RULING_DATE, operator_words=None,
        gap_open_pct=37.60, ret_5d=-0.6535,
        prior_runup_note="already up 242% in the prior 5 sessions",
        v2_label="CLEAR_AIR", v2_overhead_vol_frac=0.0000, v2_zones_remaining=0,
        live_stack_exclusion="already up 242% in prior 5 days (extended)",
        extension_live_pct=242.4,
    ),
    ChartRuling(
        ticker="JLHL", alert_date="2026-06-08", verdict=BAD_CHART,
        label_source="operator", ruling_date=RULING_DATE, operator_words=None,
        gap_open_pct=24.00, ret_5d=-0.6182,
        prior_runup_note="already up 137% in the prior 5 sessions",
        v2_label="CLEAR_AIR", v2_overhead_vol_frac=0.0000, v2_zones_remaining=0,
        live_stack_exclusion="already up 137% in prior 5 days (extended)",
        extension_live_pct=137.0,
    ),
    ChartRuling(
        ticker="IPCX", alert_date="2026-07-29", verdict=BAD_CHART,
        label_source="operator", ruling_date=RULING_DATE, operator_words=None,
        gap_open_pct=10.35, ret_5d=-0.5312,
        prior_runup_note="no prior run-up at all — this one is not an extension case",
        v2_label="CLEAR_AIR", v2_overhead_vol_frac=0.9959, v2_zones_remaining=0,
        live_stack_exclusion="quality filter: filter:adv_too_low: $522,205",
        extension_live_pct=0.0,
    ),
    ChartRuling(
        ticker="QH", alert_date="2026-06-18", verdict=BAD_CHART,
        label_source="operator", ruling_date=RULING_DATE, operator_words=None,
        gap_open_pct=5.13, ret_5d=-0.5018,
        prior_runup_note="already up 224% in the prior 5 sessions",
        v2_label="CLEAR_AIR", v2_overhead_vol_frac=0.0000, v2_zones_remaining=0,
        live_stack_exclusion="already up 224% in prior 5 days (extended)",
        extension_live_pct=223.7,
    ),
    ChartRuling(
        ticker="MRAM", alert_date="2026-05-13", verdict=BAD_CHART,
        label_source="operator", ruling_date=RULING_DATE, operator_words=None,
        gap_open_pct=14.09, ret_5d=-0.4236,
        prior_runup_note="up 135% in the prior 5 sessions on the live gate's own basis",
        v2_label="CLEAR_AIR", v2_overhead_vol_frac=0.0000, v2_zones_remaining=0,
        live_stack_exclusion="EP cooldown — alerted within last 60 days",
        extension_live_pct=134.7,
    ),
    ChartRuling(
        ticker="YOU", alert_date="2026-08-05", verdict=BAD_CHART,
        label_source="operator", ruling_date=RULING_DATE, operator_words=None,
        gap_open_pct=16.22, ret_5d=-0.2873,
        prior_runup_note="no prior run-up at all — this one is not an extension case",
        v2_label="CLEAR_AIR", v2_overhead_vol_frac=0.0000, v2_zones_remaining=0,
        live_stack_exclusion="score 36 < 50 (catalyst=strong)",
        extension_live_pct=4.7,
    ),
    ChartRuling(
        ticker="AEHR", alert_date="2026-08-14", verdict=BAD_CHART,
        label_source="operator", ruling_date=RULING_DATE, operator_words=None,
        gap_open_pct=8.36, ret_5d=-0.2386,
        prior_runup_note=("up 25% in the prior 5 sessions and 89% over 20 — well short of "
                          "the 75% extension cap. ⚠ THE SAME TICKER IS A LABELLED REAL EP "
                          "on 2026-03-31 in must_not_miss_eps.py, where its prior 5- and "
                          "20-session run-up is 0%. This pair is the operator's "
                          "where-in-the-move point with the ticker held constant."),
        v2_label="CLEAR_AIR", v2_overhead_vol_frac=0.0000, v2_zones_remaining=0,
        live_stack_exclusion="EP cooldown — alerted within last 60 days",
        extension_live_pct=24.8,
    ),
    ChartRuling(
        ticker="QTTB", alert_date="2026-07-13", verdict=BAD_CHART,
        label_source="operator", ruling_date=RULING_DATE, operator_words=None,
        gap_open_pct=63.34, ret_5d=-0.1786,
        prior_runup_note="no prior run-up at all — this one is not an extension case",
        v2_label="CLEAR_AIR", v2_overhead_vol_frac=0.0000, v2_zones_remaining=0,
        live_stack_exclusion="quality filter: filter:mcap_too_small: $190M < $500M",
        extension_live_pct=0.0,
    ),

    # ── OKISH_EARLIER — the named earlier version he does NOT want filtered out ───────
    # ⚠ NOT a `must_not_miss_eps.py` member: "ok'ish" is not "a real EP", so it does not
    # earn a place on the must-not-miss side. It IS a must-NOT-reject anchor: any measure
    # that rejects CAR 2026-04-22 must be checked against this date before it is believed.
    ChartRuling(
        ticker="CAR", alert_date="2026-04-01", verdict=OKISH_EARLIER,
        label_source="operator", ruling_date=RULING_DATE,
        operator_words=OPERATOR_QUALIFICATION,
        better_date=None, better_date_provenance=STATED,
        better_date_note=("This IS the date he named as the good one — 'ok'ish', his word, "
                          "about this date. STATED, not inferred."),
        gap_open_pct=1.34, ret_5d=None,
        prior_runup_note=("up 36% in the prior 5 sessions — against 64% on 04-21 and 92% on "
                          "04-22. The supply read separates the three dates more sharply "
                          "than the run-up does: on 04-01 CAR still had 43% of its traded "
                          "volume overhead and 13 qualified congestion zones above the "
                          "open; by 04-21 and 04-22 both are zero."),
        v2_label="IFFY_AT_FIRST_ZONE", v2_overhead_vol_frac=0.429, v2_zones_remaining=13,
        live_stack_exclusion=None,
        extension_live_pct=35.8,
    ),

    # ── WRONG_STAGE — right chart, not ready. Not junk, not a buy. ───────────────────
    ChartRuling(
        ticker="ARQQ", alert_date="2026-06-15", verdict=WRONG_STAGE,
        label_source="operator", ruling_date=RULING_DATE,
        operator_words="arqq is decent, but still within bottoming base",
        gap_open_pct=5.66, ret_5d=1.0209,
        prior_runup_note=("up 12% in the prior 5 sessions. The chart quality is not the "
                          "objection — the STAGE is. It ran +102% in 5 sessions anyway, "
                          "which is why 'wrong stage' must not be scored as 'bad chart': "
                          "the outcome says the move was real and his objection stands "
                          "regardless, because a bottoming base is not a buy point."),
        v2_label="IFFY_AT_FIRST_ZONE", v2_overhead_vol_frac=0.892, v2_zones_remaining=21,
        live_stack_exclusion="quality filter: filter:mcap_too_small: $304M < $500M",
        extension_live_pct=12.0,
    ),

    # ── WRONG_DAY — right chart, the setup is on another date ────────────────────────
    ChartRuling(
        ticker="MXL", alert_date="2026-04-21", verdict=WRONG_DAY,
        label_source="operator", ruling_date=RULING_DATE,
        operator_words=("looks better for delayed entry, there's 3 tight days prior to the "
                        "big gap on 4/24"),
        better_date="2026-04-24", better_date_provenance=POINTED_AT,
        better_date_note=("Verified from mi_daily_closes: 04-21/04-22/04-23 closed 33.70, "
                          "33.89, 34.25 — a 1.6% spread across three closes, with daily "
                          "ranges narrowing 14.3% -> 8.0% -> 7.4%. 04-24 then opened 54.00 "
                          "against the 34.25 close, a 57.7% gap. His three tight days and "
                          "his big gap are both exactly where he said they were. "
                          "⚠ PROVENANCE: he POINTED AT 04-24 while explaining why 04-21 was "
                          "the wrong date — 'looks better for delayed entry'. He did NOT say "
                          "04-24 was tradeable, so it is NOT an operator-stated "
                          "must-not-reject date and does not appear in "
                          "MUST_NOT_REJECT_DATES. Any measure that rejects it is worth "
                          "flagging as a possible cost, not scoring as a proven miss."),
        gap_open_pct=5.64, ret_5d=0.5516,
        prior_runup_note=("up 47% in the prior 5 sessions on 04-21 against 30% on 04-24 — "
                          "so a run-up filter ordered these two dates BACKWARDS relative "
                          "to his judgement only above a 30% cutline, and rejects the day "
                          "he wants below it."),
        v2_label="CLEAR_AIR", v2_overhead_vol_frac=0.0000, v2_zones_remaining=0,
        live_stack_exclusion="score 18 < 50 (catalyst=routine)",
        extension_live_pct=48.9,
    ),

    # ── NO_SETUP_ON_THIS_DATE — a measurement defect, not a chart opinion ────────────
    ChartRuling(
        ticker="VEEE", alert_date="2026-07-08", verdict=NO_SETUP_ON_THIS_DATE,
        label_source="operator", ruling_date=RULING_DATE,
        operator_words="i don't see gap on 7/8",
        better_date="2026-07-13", better_date_provenance=POINTED_AT,
        better_date_note=("The move the +354% belongs to. 07-13 opened 12.24 against a 4.82 "
                          "close on 07-10 — a 154% gap, five sessions after the date the "
                          "outcome table credits. Recorded, NOT fixed here."),
        gap_open_pct=4.09, ret_5d=3.5375,
        prior_runup_note=("⚠ THE RULING IS ABOUT OUR DATA, NOT HIS CHART READ. Verified "
                          "from mi_daily_closes 2026-08-25: prior close 5.63, open 5.86 = "
                          "a 4.09% gap, under our own 9% floor, and the session CLOSED at "
                          "4.64, down 21% from its own open. The +354% 5-session return is "
                          "measured from the 07-08 open to the 07-15 close and belongs "
                          "entirely to the unrelated 07-13 event. Every 'we missed this' "
                          "claim built on mi_ep_missed_outcomes carries this defect."),
        v2_label="INTO_SUPPLY", v2_overhead_vol_frac=0.923, v2_zones_remaining=30,
        live_stack_exclusion="quality filter: filter:adv_too_low: $182,622",
        extension_live_pct=13.1,
    ),
]


# ── Derived views. `MUST_NOT_TRADE` is the eleven-member population the two headline
#    counts in docs/analysis/structure_read_v3_2026-08-25.md are measured against. ──────
MUST_NOT_TRADE: list[ChartRuling] = [r for r in CHART_RULINGS if r.verdict == BAD_CHART]

# Dates he explicitly does not want filtered out, contributed by THIS file. Two sources:
# an OKISH_EARLIER ruling's own date, and any `better_date` a WRONG_DAY ruling points at.
# ⚠ A NO_SETUP_ON_THIS_DATE better_date is NOT included — 07-13 is where the move was, but
# he never said it was tradeable, and inferring that would be exactly the agent judgement
# this file forbids.
MUST_NOT_REJECT_DATES: list[tuple[str, str, str]] = [
    (r.ticker, r.alert_date, r.verdict) for r in CHART_RULINGS
    if r.verdict in MUST_NOT_REJECT_VERDICTS
]

# Dates he POINTED AT but never ruled on. ⚠ NOT operator must-not-reject labels — a measure
# that rejects one of these is a FLAG worth reporting, not a proven miss. Kept separate on
# purpose: collapsing them into MUST_NOT_REJECT_DATES would put an agent's inference behind
# the operator's name.
POINTED_AT_DATES: list[tuple[str, str, str]] = [
    (r.ticker, r.better_date, r.verdict) for r in CHART_RULINGS
    if r.better_date and r.better_date_provenance == POINTED_AT
]
