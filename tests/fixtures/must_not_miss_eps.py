"""#577 — THE MUST-NOT-MISS FIXTURE.

RULE 0 / P1 (`docs/roadmap/ep_profitability_program.md` § THE PRINCIPLES, operator 2026-08-19):
*"regardless of conclusions, EPs like MRNA cannot be missed, that's the first thing... it should not
miss a real EP which is the true test."* A false EXCLUSION leaves no row, no skip_reason, no trace —
the measurable error is the harmless one. This file is the labelled ground truth that
`tests/test_577_must_not_miss_eps.py` replays through the CURRENT selection stack every suite run.

⚠ LABELS MUST BE OPERATOR-SOURCED OR EVIDENCE-SOURCED, NEVER INFERENCE. Every member below carries
a `label_source` naming exactly where its "this is a real EP" status comes from. Two kinds appear:
  - "operator" — the operator has explicitly called this name an EP (e.g. MRNA,
    `docs/methodology/ep_reference_mrna_2026-08-19.md`).
  - "evidence:<citation>" — a quantitative, pre-existing screen already used across the programme,
    e.g. the 26 tradeable >=10R winners (`docs/analysis/winner_r_available_2026-08-16.txt`
    GEOMETRY 1: stop = EP-day low, the geometry that matches our live day-1 stop).

HOW TO ADD A MEMBER — one line, no code change: append an `EPFixtureMember(...)` to
`MUST_NOT_MISS` below. If a metric hasn't been independently verified this session, leave it `None`
and list its gate key in `unverified_gates` (the coverage test enforces this — a bare `None` with no
declaration fails loudly rather than silently reading as a pass).

WHY SOME METRICS ARE `None` HERE, NOT GUESSED: this fixture was built offline, $0, with no live DB
or FMP access in-session (`shared/secrets.py` raised `POSTGRES_PASSWORD not set` when checked, and
SSH to the prod host is blocked from this sandbox). Filling a metric with a plausible-looking number
instead of a verified one would be exactly the "my own inference" the DoD forbids — a public company
being obviously large-cap is not evidence, it is a guess dressed as evidence. `gap_pct` and
`prev_close` ARE independently verified below (see the provenance note on `_552_cohort.psv`);
`adv_dollar_20d`, `atr_pct_14d`, `market_cap`, `prev_day_volume` and `extension_pct_pregap5d` are not
and are declared unverified uniformly across every member, MRNA included — no member gets a metric
for free just because its overall case is strong by other means.

──────────────────────────────────────────────────────────────────────────────────────────────
🔴 BASELINE_DEBT — a RECORDED DEBT AGAINST P1, NOT AN ACCEPTED STATE.

Recorded 2026-08-19, first run of this fixture: 15 of the 25 evidence-sourced tradeable >=10R
winners were excluded by `MIN_GAP_PCT` at its then-value (gap at the open < the 10.0% floor,
universe admission — leaves no `mi_ep_scan_log` row). That is P1's own asymmetry made visible: a
real, evidence-sourced EP the current stack would silently drop. See
`docs/roadmap/ep_profitability_program.md` § THE PRINCIPLES, P1.

**UPDATED same day, 2026-08-19**: the operator ruled `MIN_GAP_PCT` 10.0% → 9.0%
(`docs/setups/magna53_ep.md` 2026-08-19 change log; priced in
`docs/analysis/gap_floor_decision_table_2026-08-19.md`). 8 of the original 15 now clear the floor
(MU, MRVL, SNOW, ALGM, AMKR, UMC 2026-05-06, BE, USAR) and are removed from `BASELINE_DEBT` below —
per this docstring's own rule, the only way to shrink the dict is to fix the actual exclusion, which
this operator-ruled threshold change did. **7 remain excluded** at the new 9.0% floor: STRL, ASX,
NBIS, QCOM, HUT, SMTC, IREN (all gap 8.1-8.7%, below even the new floor). ⚠ AMKR clears by 0.03pp
(9.03% vs 9.0%, session-open psv basis) — basis-marginal, not a clean clear like the other 7.

WHY A BASELINE AND NOT A HARD FAIL EVERY RUN: an always-red suite blocks every `git push` (the
pre-push hook runs the full suite) and destroys the signal for the other ~5,600 tests — the same
"a guard that always fires is not a guard" failure this repo has hit before. So each KNOWN
exclusion is pinned here, by name and by gate, and `tests/test_577_must_not_miss_eps.py`'s
regression test tolerates ONLY the exact gate recorded — nothing more. The exclusions stay loud
via `pytest_terminal_summary` (`tests/conftest.py`), printed on every `pytest` run with no `-v`
needed.

WHAT STILL FAILS THE BUILD, HARD, NO TOLERANCE:
  - A member NOT in this dict gets excluded by ANY gate (a brand-new miss).
  - A member IN this dict gets excluded by a gate OTHER than the one recorded here (the debt got
    WORSE, not just persisted).
  - ANY operator-named member (`label_source == "operator"`) is excluded by anything at all —
    enforced structurally: `test_operator_named_members_never_carry_baseline_tolerance` fails if an
    operator-named key ever appears in this dict, so an operator-named member can never be entered
    into the tolerance list in the first place, by design or by accident.

THE ONLY WAY TO SHRINK THIS DICT: fix the actual exclusion (an operator-ruled threshold change —
selection criteria are THE LINE), then remove the line. Removing a line WITHOUT the underlying gate
clearing does nothing to hide the debt — the member falls back to zero tolerance and the regression
test goes red immediately, since it is still actually excluded. And a `gap_pct`/`prev_close` value
can't be quietly edited to fake a pass either: `test_psv_sourced_members_match_the_source_file`
re-derives every psv-sourced member's recorded numbers from `_552_cohort.psv` on every run and fails
if the fixture ever drifts from that source file.
──────────────────────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from typing import Dict, FrozenSet, NamedTuple, Optional, Tuple


class EPFixtureMember(NamedTuple):
    ticker: str
    alert_date: str            # ISO date "YYYY-MM-DD" — the EP/gap day
    label_source: str          # "operator" | "evidence:<citation>"
    label_note: str            # short human note on why this is a real EP

    # ── Metrics fed to the CURRENT selection stack's gates. None = not verified this session. ──
    gap_pct: Optional[float] = None            # vs MIN_GAP_PCT (ep_detector.py)
    gap_basis: Optional[str] = None            # how gap_pct was measured (matters for the message)
    prev_close: Optional[float] = None         # vs MIN_PREV_CLOSE (ep_detector.py)
    prev_day_volume: Optional[float] = None    # vs MIN_PREV_DAY_VOLUME (ep_detector.py)
    extension_pct_pregap5d: Optional[float] = None  # vs MAX_EXTENSION_PCT (ep_detector.py)
    adv_dollar_20d: Optional[float] = None     # vs MIN_ADV_DOLLAR_VOLUME (backtester/filters.py)
    atr_pct_14d: Optional[float] = None        # vs MAX_ATR_PCT (backtester/filters.py)
    market_cap: Optional[float] = None         # vs MIN_MARKET_CAP (backtester/filters.py)

    # Gate keys (see GATE_KEYS in the test) that are deliberately NOT verified this session.
    # Every tracked gate for every member must appear either as a recorded value above OR here —
    # enforced by test_577_must_not_miss_eps.py::test_coverage_is_declared_for_every_member.
    unverified_gates: Tuple[str, ...] = ()

    # A member can be present (for the record, evidence cited) but excluded from the pass/fail
    # replay — e.g. the source data itself flags the print as an artifact. Never a silent drop:
    # exclude_reason is mandatory whenever excluded=True (coverage test enforces this too).
    excluded: bool = False
    exclude_reason: Optional[str] = None


_UNVERIFIED_STANDARD = (
    "prev_day_volume", "extension_pct_pregap5d", "adv_dollar_20d", "atr_pct_14d", "market_cap",
)
# ^ Not independently computed this session (needs a live DB read of mi_daily_closes / an FMP
#   market-cap call, neither reachable from this sandbox). Declared, not silently omitted.


MUST_NOT_MISS: list[EPFixtureMember] = [
    # ── Member 1 — OPERATOR-NAMED ─────────────────────────────────────────────────────────────
    EPFixtureMember(
        ticker="MRNA", alert_date="2026-08-19",
        label_source="operator",
        label_note=(
            "Operator, 2026-08-19: \"MRNA is a textbook EP... the news is truly gamechanging, the "
            "move, etc. is textbook.\" Two independent traders called it the same thing the same "
            "morning. Source: docs/methodology/ep_reference_mrna_2026-08-19.md."
        ),
        # Gap day: O 116.02, PDC 62.97 (ep_reference_mrna_2026-08-19.md "the gap day" table).
        # (116.02 - 62.97) / 62.97 * 100 = 84.25% — OPEN vs prior-close, the same basis used for
        # every other member below (so all fixture gaps are comparable on one basis). The doc's own
        # headline figures (+121-125%) are a later/different snapshot (intraday high, not the open)
        # — not used here to avoid mixing bases within one fixture; the verdict is unaffected either
        # way (8x the floor vs 12x).
        gap_pct=84.25,
        gap_basis="session open vs prior close, computed from ep_reference_mrna_2026-08-19.md's "
                   "own O 116.02 / PDC 62.97 ('the gap day' table) — NOT independently re-derived "
                   "from mi_daily_closes this session",
        prev_close=62.97,
        unverified_gates=_UNVERIFIED_STANDARD,
        # Corroborating (not fed to any gate assertion, kept here for context only): the same doc
        # records MRNA was actually ENTERED live at 09:31:09 @120.75 and hit +2R same day — direct
        # proof the system's FULL live stack (every gate, not just the ones this fixture checks
        # mechanically) admitted it that morning.
    ),

    # ── Evidence-sourced: the 26 tradeable >=10R winners ─────────────────────────────────────
    # Source: docs/analysis/winner_r_available_2026-08-16.txt, GEOMETRY 1 (stop = EP-day low — the
    # geometry matching our live day-1 stop), ">=10R" bucket (26 of the 78 tier-A tail winners).
    # gap_pct / prev_close verified from scripts/probes/_552_cohort.psv (col[2]=gap%, col[5]=prior
    # close) — column mapping confirmed two ways: (a) BATL 2026-03-03 arithmetic
    # (24.76-11.80)/11.80*100 = 109.83 = its own col[2]; (b) the median gap of these 26 rows comes
    # out to 9.865%, matching the programme doc's independently-stated "gap % ... 9.9%" for this
    # exact cohort (ep_profitability_program.md, "The winner profile inverts our grading logic").
    # gap_basis = SESSION OPEN (col[3] vs col[5] in the psv) — NOT the live 09:31 real-time cross.
    # The live path re-checks the gap in real time and can admit a name that was <10% at the open
    # but crossed it intraday (ep_profitability_program.md: "78% of tradeable missed winners that
    # gapped under 10% AT THE OPEN went on to cross 10% during [the session]") — so an at-the-open
    # red here is NOT proof the live system would have missed the name outright, only that universe
    # ADMISSION at the open would have dropped it with no scan_log row. State this basis in every
    # failure message; do not let the open-vs-intraday distinction get lost.
    EPFixtureMember(
        ticker="MU", alert_date="2026-04-08", label_source="evidence:winner_r_available_2026-08-16",
        label_note=">=20R tradeable winner (EP-day-low stop geometry).",
        gap_pct=9.94, gap_basis="session open (_552_cohort.psv)", prev_close=377.58,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
    EPFixtureMember(
        ticker="UMC", alert_date="2026-04-17", label_source="evidence:winner_r_available_2026-08-16",
        label_note=">=20R tradeable winner (EP-day-low stop geometry).",
        gap_pct=11.58, gap_basis="session open (_552_cohort.psv)", prev_close=10.62,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
    EPFixtureMember(
        ticker="STRL", alert_date="2026-04-08", label_source="evidence:winner_r_available_2026-08-16",
        label_note=">=20R tradeable winner (EP-day-low stop geometry).",
        gap_pct=8.20, gap_basis="session open (_552_cohort.psv)", prev_close=382.22,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
    EPFixtureMember(
        ticker="MRVL", alert_date="2026-03-31", label_source="evidence:winner_r_available_2026-08-16",
        label_note=">=20R tradeable winner (EP-day-low stop geometry).",
        gap_pct=9.78, gap_basis="session open (_552_cohort.psv)", prev_close=87.81,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
    EPFixtureMember(
        ticker="ASX", alert_date="2026-04-08", label_source="evidence:winner_r_available_2026-08-16",
        label_note=">=20R tradeable winner (EP-day-low stop geometry).",
        gap_pct=8.16, gap_basis="session open (_552_cohort.psv)", prev_close=22.19,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
    EPFixtureMember(
        ticker="SNDK", alert_date="2026-04-08", label_source="evidence:winner_r_available_2026-08-16",
        label_note=">=20R tradeable winner (EP-day-low stop geometry).",
        gap_pct=10.30, gap_basis="session open (_552_cohort.psv)", prev_close=710.80,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
    EPFixtureMember(
        ticker="SNOW", alert_date="2026-05-07", label_source="evidence:winner_r_available_2026-08-16",
        label_note=">=20R tradeable winner (EP-day-low stop geometry).",
        gap_pct=9.80, gap_basis="session open (_552_cohort.psv)", prev_close=139.74,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
    EPFixtureMember(
        ticker="ALGM", alert_date="2026-04-08", label_source="evidence:winner_r_available_2026-08-16",
        label_note=">=20R tradeable winner (EP-day-low stop geometry).",
        gap_pct=9.16, gap_basis="session open (_552_cohort.psv)", prev_close=33.28,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
    EPFixtureMember(
        ticker="NBIS", alert_date="2026-04-08", label_source="evidence:winner_r_available_2026-08-16",
        label_note=">=20R tradeable winner (EP-day-low stop geometry).",
        gap_pct=8.07, gap_basis="session open (_552_cohort.psv)", prev_close=117.40,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
    EPFixtureMember(
        ticker="AMKR", alert_date="2026-04-08", label_source="evidence:winner_r_available_2026-08-16",
        label_note="10-20R tradeable winner (EP-day-low stop geometry).",
        gap_pct=9.03, gap_basis="session open (_552_cohort.psv)", prev_close=47.62,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
    EPFixtureMember(
        ticker="AEHR", alert_date="2026-03-31", label_source="evidence:winner_r_available_2026-08-16",
        label_note="10-20R tradeable winner (EP-day-low stop geometry).",
        gap_pct=11.27, gap_basis="session open (_552_cohort.psv)", prev_close=30.12,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
    EPFixtureMember(
        ticker="TDIC", alert_date="2026-05-12", label_source="evidence:winner_r_available_2026-08-16",
        label_note="10-20R by the R-table, but excluded from the pass/fail replay (see exclude_reason).",
        gap_pct=73.56, gap_basis="session open (_552_cohort.psv)", prev_close=26.00,
        unverified_gates=_UNVERIFIED_STANDARD,
        excluded=True,
        exclude_reason=(
            "The source file itself flags this print as an artifact, not a real tradeable EP: "
            "'Named data anomaly: TDIC 2026-05-12 -- next-day high $750 (close $576) then a full "
            "round-trip to $20 the following session. A halt-prone squeeze where the peak print was "
            "almost certainly not capturable; its 18.6R (geo-1) should be read as an artifact of the "
            "definition, not a tradeable opportunity.' (docs/analysis/winner_r_available_2026-08-16.txt) "
            "Excluding on the SOURCE's own flag, not my judgement of what counts as a real EP."
        ),
    ),
    EPFixtureMember(
        ticker="UMC", alert_date="2026-05-06", label_source="evidence:winner_r_available_2026-08-16",
        label_note="10-20R tradeable winner (EP-day-low stop geometry) — second, distinct UMC event.",
        gap_pct=9.14, gap_basis="session open (_552_cohort.psv)", prev_close=14.01,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
    EPFixtureMember(
        ticker="FLY", alert_date="2026-03-12", label_source="evidence:winner_r_available_2026-08-16",
        label_note="10-20R tradeable winner (EP-day-low stop geometry).",
        gap_pct=15.05, gap_basis="session open (_552_cohort.psv)", prev_close=20.60,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
    EPFixtureMember(
        ticker="BE", alert_date="2026-04-08", label_source="evidence:winner_r_available_2026-08-16",
        label_note="10-20R tradeable winner (EP-day-low stop geometry).",
        gap_pct=9.93, gap_basis="session open (_552_cohort.psv)", prev_close=135.91,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
    EPFixtureMember(
        ticker="USAR", alert_date="2026-04-08", label_source="evidence:winner_r_available_2026-08-16",
        label_note="10-20R tradeable winner (EP-day-low stop geometry).",
        gap_pct=9.36, gap_basis="session open (_552_cohort.psv)", prev_close=14.64,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
    EPFixtureMember(
        ticker="QCOM", alert_date="2026-04-24", label_source="evidence:winner_r_available_2026-08-16",
        label_note="10-20R tradeable winner (EP-day-low stop geometry).",
        gap_pct=8.70, gap_basis="session open (_552_cohort.psv)", prev_close=133.95,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
    EPFixtureMember(
        ticker="QBTS", alert_date="2026-04-08", label_source="evidence:winner_r_available_2026-08-16",
        label_note="10-20R tradeable winner (EP-day-low stop geometry).",
        gap_pct=10.99, gap_basis="session open (_552_cohort.psv)", prev_close=13.74,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
    EPFixtureMember(
        ticker="AMD", alert_date="2026-04-24", label_source="evidence:winner_r_available_2026-08-16",
        label_note="10-20R tradeable winner (EP-day-low stop geometry).",
        gap_pct=10.29, gap_basis="session open (_552_cohort.psv)", prev_close=305.33,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
    EPFixtureMember(
        ticker="HUT", alert_date="2026-04-08", label_source="evidence:winner_r_available_2026-08-16",
        label_note="10-20R tradeable winner (EP-day-low stop geometry).",
        gap_pct=8.40, gap_basis="session open (_552_cohort.psv)", prev_close=52.66,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
    EPFixtureMember(
        ticker="QURE", alert_date="2026-05-29", label_source="evidence:winner_r_available_2026-08-16",
        label_note="10-20R tradeable winner (EP-day-low stop geometry).",
        gap_pct=15.69, gap_basis="session open (_552_cohort.psv)", prev_close=24.85,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
    EPFixtureMember(
        ticker="ARM", alert_date="2026-05-06", label_source="evidence:winner_r_available_2026-08-16",
        label_note="10-20R tradeable winner (EP-day-low stop geometry).",
        gap_pct=11.09, gap_basis="session open (_552_cohort.psv)", prev_close=208.84,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
    EPFixtureMember(
        ticker="SMTC", alert_date="2026-03-30", label_source="evidence:winner_r_available_2026-08-16",
        label_note="10-20R tradeable winner (EP-day-low stop geometry).",
        gap_pct=8.12, gap_basis="session open (_552_cohort.psv)", prev_close=72.16,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
    EPFixtureMember(
        ticker="IREN", alert_date="2026-04-08", label_source="evidence:winner_r_available_2026-08-16",
        label_note="10-20R tradeable winner (EP-day-low stop geometry).",
        gap_pct=8.28, gap_basis="session open (_552_cohort.psv)", prev_close=35.74,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
    EPFixtureMember(
        ticker="APLD", alert_date="2026-04-08", label_source="evidence:winner_r_available_2026-08-16",
        label_note="10-20R tradeable winner (EP-day-low stop geometry).",
        gap_pct=12.97, gap_basis="session open (_552_cohort.psv)", prev_close=25.18,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
    EPFixtureMember(
        ticker="INTC", alert_date="2026-04-24", label_source="evidence:winner_r_available_2026-08-16",
        label_note="10-20R tradeable winner (EP-day-low stop geometry). Also the pivot-ladder / "
                    "delayed-entry reference case (docs/setups/delayed_ep_reentry.md).",
        gap_pct=23.09, gap_basis="session open (_552_cohort.psv)", prev_close=66.78,
        unverified_gates=_UNVERIFIED_STANDARD,
    ),
]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# BASELINE_DEBT — see the module docstring above for the full rationale. Recorded 2026-08-19.
#
# Key: (ticker, alert_date). Value: the frozenset of gate keys CURRENTLY tolerated as pre-existing
# exclusions for that member — the exact strings `_check_member` in the test file emits as its
# first element of each (gate_key, message) result. Nothing outside this exact set is tolerated;
# a member hitting one more gate than what's recorded here is a regression, not debt.
#
# ⚠ NEVER add an operator-named member's key here — `label_source == "operator"` members must
# clear every gate unconditionally, checked by `test_operator_named_members_never_carry_baseline_
# tolerance` in the test file.
BASELINE_RECORDED_DATE = "2026-08-19"

# 2026-08-19: MU, MRVL, SNOW, ALGM, AMKR, UMC(2026-05-06), BE, USAR removed — all clear
# MIN_GAP_PCT at the new 9.0% floor (gap 9.03-9.94%). The remaining 7 all gap 8.1-8.7%, still
# below 9.0%.
BASELINE_DEBT: Dict[Tuple[str, str], FrozenSet[str]] = {
    ("STRL", "2026-04-08"): frozenset({"MIN_GAP_PCT"}),
    ("ASX", "2026-04-08"): frozenset({"MIN_GAP_PCT"}),
    ("NBIS", "2026-04-08"): frozenset({"MIN_GAP_PCT"}),
    ("QCOM", "2026-04-24"): frozenset({"MIN_GAP_PCT"}),
    ("HUT", "2026-04-08"): frozenset({"MIN_GAP_PCT"}),
    ("SMTC", "2026-03-30"): frozenset({"MIN_GAP_PCT"}),
    ("IREN", "2026-04-08"): frozenset({"MIN_GAP_PCT"}),
}
