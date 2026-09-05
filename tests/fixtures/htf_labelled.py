"""HTF labelled corpus — trader-shared high-tight-flags the operator brought in as
labelled examples for the detector (memory `htf-tweets-are-a-tuning-corpus`, operator
2026-08-25: *"the main reason I'm sharing these tweets is to help tune our htf detection"*).

`tests/test_htf_labelled_corpus.py` replays every member through the SHIPPED
`compute_flag_metrics` (state threaded day by day exactly as `flag_scan` threads it) and
asserts the RECORDED verdict — so a silent detector change flips the test loudly in
either direction. Bars: `tests/fixtures/htf_labelled_bars.psv` (mi_daily_closes, pulled
2026-09-04). CDNA/HNGE/ATAI/NCI/OUST/REPL 2025-07-28 → 2026-09-04; SHAZ only from
2026-02-18 (no earlier `mi_daily_closes` rows exist for it — coverage gap, not a bug;
irrelevant to SHAZ's own flag_low rejection which needs no 200d SMA).

⚠ **`expected` is either `"actionable"` (must be in `_ACTIONABLE`) or `"rejected:<prefix>"`
(stage must NOT be in `_ACTIONABLE` AND `reason` must start with `<prefix>`) — generalised
2026-09-04 from a runup-only check so members rejected by stage2 / flag-depth / base-age
gates (not just runup) can be encoded honestly. See `test_htf_labelled_corpus.py`.

⚠ LABELS ARE OPERATOR-SOURCED, NEVER INFERENCE. Each member names where its label came
from. A member's `expected` is what the detector DOES today under the signed spec, which
is not always what the trader's label says — HNGE is the recorded example: a labelled
positive that the SOURCED 4–8-week pole definition rejects (pole 10–13 weeks). That
mismatch is the operator's methodology fork (docs/setups/htf.md § Known limitations), and
the test pins the current verdict rather than pretending the fork is settled.

HOW TO ADD A MEMBER — one line: append an `HTFLabelledMember(...)`, and append that
ticker's bars to the .psv (same pull SQL as the grid replay; see
`scripts/probes/_592_610_htf_grid_replay.py`). Check what the detector said on the label
date FIRST (`mi_flag_candidates`) and record THAT as `expected` with the reason.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class HTFLabelledMember:
    ticker: str
    label_date: date                 # the day the trader acted / called it
    label_source: str                # where the "this is an HTF" label comes from
    trader_read: str
    # what the SHIPPED detector is expected to say on `assert_dates` — RECORDED, not wished
    assert_dates: tuple[date, ...]
    expected: str                    # "actionable" | "rejected:runup"
    note: str


HTF_LABELLED: tuple[HTFLabelledMember, ...] = (
    HTFLabelledMember(
        ticker="CDNA",
        label_date=date(2026, 8, 19),
        label_source=("operator-shared trader post 2026-08-25 (bought 08-19); recorded in "
                      "docs/analysis/htf_surfacing_gap_2026-08-25.md"),
        trader_read="one of the more textbook High Tight Flags I've seen",
        assert_dates=(date(2026, 8, 18), date(2026, 8, 19)),
        expected="actionable",
        note=("MUST-NOT-MISS. Pole 06-22 $25.05 → 08-03 $49.76 (+99% in 30 bars) fits the 40-session "
              "window; we had it TIGHTENING the day before he bought. Every criteria variant must keep it."),
    ),
    HTFLabelledMember(
        ticker="HNGE",
        label_date=date(2026, 8, 24),
        label_source=("operator-shared trader post 2026-08-24/25; recorded in "
                      "docs/analysis/htf_surfacing_gap_2026-08-25.md and PLAN #592"),
        trader_read="high tight flag",
        assert_dates=(date(2026, 8, 21), date(2026, 8, 24)),
        expected="rejected:runup_",
        note=("RECORDED GAP, not an accepted state. Pole 05-04 $45.01 → 07-13 $91.50 = +103% over 49 "
              "sessions (10 weeks); the sourced spec is 90%+ in 4–8 weeks and its own scanner forms "
              "reject it on 08-24 (C/C40 1.14, High40/Low40 1.30 vs 1.90). Admitting it on the trader's "
              "date needs BOTH retired n=1 knobs (1.50 ratio AND a 60-session window) — the operator's "
              "call, filed in docs/setups/htf.md § Known limitations. Runup reads 41% on these dates."),
    ),
    HTFLabelledMember(
        ticker="NCI",
        label_date=date(2026, 6, 27),
        label_source=("operator /flags eyeball 2026-06-27, verbatim in commit e91f8f74 and "
                      "docs/setups/htf.md change-log (2026-06-27 entry): \"NCI is not valid\""),
        trader_read="NCI is not valid",
        assert_dates=(date(2026, 6, 26),),
        expected="rejected:adv_",
        note=("NEGATIVE label. NCI spiked $110 → crashed $4 → bounced to $11 (−90% from its high, "
              "10% of the $110.48 52-week high) — a dead-cat bounce that a pure 10/20/50 trend "
              "filter read as a \"221% flagpole,\" caught live on the operator's own /flags eyeball. "
              "The Stage-2 near-high gate built FROM this catch (same day, `pole_..._not_stage2`) is "
              "the PURPOSE-BUILT reason his verdict is now correct — but it is NOT what this replay "
              "observes: `_HTF_MIN_ADV_SHARES` (shipped 2 days later, 2026-06-28) is an EARLIER-return "
              "check and rejects NCI first on every date in this window (`adv_151k_below_500k_shares` "
              "on 06-26; its 20-session median volume never re-clears 500k while the $110 pole is "
              "still inside the 40-session lookback). Both gates reject it — the operator's verdict "
              "holds — but the mechanism this replay can actually exercise is a coincidental liquidity "
              "floor, not the crash-recovery logic built for this case; that logic is confirmed "
              "separately by `test_crash_recovery_rejected_stage2` (tests/test_htf_criteria.py), which "
              "constructs bars where ADV isn't the binding constraint. Confirmed unaffected by the "
              "#592 anchor fix either way (byte-identical pre/post-fix replay, since ADV returns "
              "before the pivot-walk code runs)."),
    ),
    HTFLabelledMember(
        ticker="ATAI",
        label_date=date(2026, 7, 24),
        label_source=("operator, 2026-07-24, verbatim in docs/analysis/htf_deal_pin_fresh_2026-07-24.md: "
                      "\"ATAI is a buyout so the HTF is invalid.\""),
        trader_read="ATAI is a buyout so the HTF is invalid.",
        assert_dates=(date(2026, 7, 24),),
        expected="actionable",
        note=("NEGATIVE label, recorded the HNGE way: `compute_flag_metrics` ALONE reproduces the "
              "exact incident — COILED on 07-24 (`fresh_2bar 0.7%/atr 5.4% bodies_0.03/0.03`), the "
              "same row the operator was shown. Pure flag geometry cannot distinguish a cash-deal "
              "weld from a real coil (docs/setups/htf.md § M&A suppression) — his verdict is "
              "implemented one layer up, in `flag_scan`'s M&A suppression (layer 3, "
              "`mna_filter:deal_pin_fresh`, shipped 2026-07-24, `test_flag_fresh_deal_pin_502`), NOT "
              "in this function. The #592 anchor fix is unrelated to either layer and changes nothing "
              "here (byte-identical pre/post-fix replay). Do not read `expected=actionable` as the "
              "system disagreeing with him — it is what the tested FUNCTION returns; the SYSTEM "
              "(function + M&A layer) agrees."),
    ),
    HTFLabelledMember(
        ticker="OUST",
        label_date=date(2026, 9, 4),
        label_source=("operator sign-off 2026-09-04 on the #592 anchor-fix's removed-names ledger "
                      "(docs/analysis/htf_pole_window_grid_2026-09-04.md), verbatim in commit "
                      "451c477d: \"i don't see HTF in those 3 names at all\" (OUST, SHAZ, REPL)"),
        trader_read="i don't see HTF in those 3 names at all",
        assert_dates=(date(2026, 6, 29),),
        expected="rejected:flag_low_",
        note=("NEGATIVE label (removal-list sign-off, not a chart read). Pre-fix, the pivot walked "
              "forward to 06-22 $51.50 and 06-29 read WATCH (`runup_118% base_4d close_vs_pivot_+5.0%`). "
              "The #592 fix holds the OLDER 06-04 $48.83 pivot instead (no bar closed above it), so "
              "the same 06-29 base now reads `flag_low_35.30_below_75%_of_pole_48.83` — deeper than "
              "the 25% flag-depth gate allows. Exactly 1 ACTIONABLE row changes (06-29 WATCH→rejected); "
              "06-24/06-25 also diverge (unqualified↔INVALIDATED) but both are non-actionable either "
              "way. OUST reconverges with the pre-fix code on 06-30 once a genuine new pivot forms."),
    ),
    HTFLabelledMember(
        ticker="SHAZ",
        label_date=date(2026, 9, 4),
        label_source=("operator sign-off 2026-09-04 on the #592 anchor-fix's removed-names ledger "
                      "(docs/analysis/htf_pole_window_grid_2026-09-04.md), verbatim in commit "
                      "451c477d: \"i don't see HTF in those 3 names at all\" (OUST, SHAZ, REPL)"),
        trader_read="i don't see HTF in those 3 names at all",
        assert_dates=(date(2026, 6, 29), date(2026, 6, 30)),
        expected="rejected:flag_low_",
        note=("NEGATIVE label (removal-list sign-off, not a chart read). Pre-fix, the pivot walked to "
              "06-17 $97.48 and both dates read WATCH. The #592 fix holds the OLDER 06-02 $86.00 pivot "
              "(no bar closed above it in between), so both dates now read "
              "`flag_low_56.63_below_75%_of_pole_86.00`. SHAZ's own bars only run from 2026-02-18 "
              "(no earlier mi_daily_closes rows) — irrelevant here since flag_low needs no 200d SMA."),
    ),
    HTFLabelledMember(
        ticker="REPL",
        label_date=date(2026, 9, 4),
        label_source=("operator sign-off 2026-09-04 on the #592 anchor-fix's removed-names ledger "
                      "(docs/analysis/htf_pole_window_grid_2026-09-04.md), verbatim in commit "
                      "451c477d: \"i don't see HTF in those 3 names at all\" (OUST, SHAZ, REPL)"),
        trader_read="i don't see HTF in those 3 names at all",
        assert_dates=(date(2026, 8, 10), date(2026, 8, 11)),
        expected="rejected:base_age_",
        note=("NEGATIVE label, but ⚠ INCOMPLETE COVERAGE, not a clean confirmation like OUST/SHAZ. "
              "The removal his sign-off covers: pre-fix the pivot walked to 08-04 $13.86, giving WATCH "
              "on 08-10/08-11 (`runup_191%...`); the #592 fix instead sets a NEW pivot two days later "
              "at 08-06 $13.90, so the base is still too young (`base_age_1_below_3` / `base_age_2_below_3`) "
              "on those exact dates — different MECHANISM than OUST/SHAZ's flag-depth rejection, same "
              "net effect (removed). BOTH sides reconverge to WATCH by 08-12. "
              "⚠ UNRESOLVED FINDING, not asserted here: the SAME fix separately makes REPL newly "
              "actionable on an EARLIER, different pivot (2026-06-23 $12.23 held instead of walking "
              "to 2026-06-30 $12.50) — WATCH 07-01/07-02/07-06 and TIGHTENING 07-07 through 07-09, "
              "where the pre-fix code INVALIDATED it. That July episode was NOT part of the ledger "
              "the operator signed off on (his words were about the removed rows), so his \"not HTF "
              "at all\" verdict should NOT be read as covering it — it is a genuinely new admission "
              "the fix creates that no one has judged. Left unasserted deliberately; flagged for his "
              "eyeball, not inferred either way."),
    ),
)
