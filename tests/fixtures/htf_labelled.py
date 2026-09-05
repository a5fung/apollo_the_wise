"""HTF labelled corpus — trader-shared high-tight-flags the operator brought in as
labelled examples for the detector (memory `htf-tweets-are-a-tuning-corpus`, operator
2026-08-25: *"the main reason I'm sharing these tweets is to help tune our htf detection"*).

`tests/test_htf_labelled_corpus.py` replays every member through the SHIPPED
`compute_flag_metrics` (state threaded day by day exactly as `flag_scan` threads it) and
asserts the RECORDED verdict — so a silent detector change flips the test loudly in
either direction. Bars: `tests/fixtures/htf_labelled_bars.psv` (mi_daily_closes,
2025-07-28 → 2026-09-04, pulled 2026-09-04).

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
        expected="rejected:runup",
        note=("RECORDED GAP, not an accepted state. Pole 05-04 $45.01 → 07-13 $91.50 = +103% over 49 "
              "sessions (10 weeks); the sourced spec is 90%+ in 4–8 weeks and its own scanner forms "
              "reject it on 08-24 (C/C40 1.14, High40/Low40 1.30 vs 1.90). Admitting it on the trader's "
              "date needs BOTH retired n=1 knobs (1.50 ratio AND a 60-session window) — the operator's "
              "call, filed in docs/setups/htf.md § Known limitations. Runup reads 41% on these dates."),
    ),
)
