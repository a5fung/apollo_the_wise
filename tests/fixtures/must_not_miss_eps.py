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

**UPDATED 2026-09-03** (`docs/analysis/617_universe_admission_recall_jun_aug_2026-09-03.md` flagged
this banner as a possible false alarm post-08-27; re-measured PER NAME, not by assumption, per that
doc's own instruction "measure it per name, do not assume the aggregate"). Method: `gap_pct` above
is the SESSION-OPEN print (the psv basis, unchanged, still provenance-checked below) — but that is
NOT what `_apply_realtime_pass2`/`_apply_rt_universe_overlay` (ep_detector.py) actually compare to
`MIN_GAP_PCT`: the live gate reads whatever price the scan tick sees (`scheduler.py`: `ep_scan`
every 5 min 7:00-9:55 ET, plus a dedicated `ep_scan_open` tick at 09:31), re-checked in real time.
Measured from stored/fetched minute bars (a_ref = Alpaca's own raw D-1 close, cross-checked against
`prev_close` for a phantom-split gap per #617's LGCL lesson — none found, RAW==SPLIT for all 6
tickers below), NOT reconstructed from memory:
  - **STRL 2026-04-08 — ADMITTED.** prev_close $382.22 confirmed (Alpaca raw D-1 close matches
    exactly). Floor price $416.62. 09:30 bar close $415.555 (8.72%) and the 09:31 tick's read (the
    09:30 bar, "first complete bar just closed" per `scheduler.py`'s `ep_scan_open` job) still falls
    short — but by the 9:35 tick the price the scan reads (the just-closed 09:34 bar) is $419.385 =
    **9.72%**, and it holds through 09:44: 09:35 close $419.44 (9.74%), 09:39 close $422.22 (10.47%),
    09:40 close $424.00 (10.93%) — not a one-tick flicker. `scripts/probes/_620_bars.psv`.
  - **HUT 2026-04-08 — ADMITTED.** prev_close $52.66 confirmed. Floor price $57.40. The very first
    completed minute bar (09:30, close $59.08) already reads **12.19%** — the 09:31 `ep_scan_open`
    tick (which reads that just-closed bar per its own docstring) admits it immediately, no boundary
    ambiguity. `scripts/probes/_620_bars.psv`.
  - **QCOM 2026-04-24 — RECLASSIFIED, not an 08-27 fix.** This one is not a reconstruction: a REAL
    `mi_ep_scan_log` row exists for it (id=4679, `scan_time` 2026-04-24 09:30:10 ET) recording
    `gap_pct=10.27`, `prev_close=133.95` — QCOM cleared the THEN-10.0% floor (before the 08-19 change
    even existed) on the plain delayed Pass-1 read, which evidently already reflected a few seconds
    of post-open trading, not the literal open print (open $145.61 = 8.70%, but the accepted read
    ~10 seconds later was already ~$147.7). It entered the funnel, scored 32.4, and was excluded by
    `score 32 < 50 (catalyst=routine)` — the LLM catalyst-quality judge, which this test's own SCOPE
    note excludes ("costs money per call and is non-deterministic, out of scope for a $0 suite
    test"). **QCOM was never a MIN_GAP_PCT exclusion — BASELINE_DEBT mischaracterized it since
    2026-08-19.** Fixed here to match the actual scan_log row; it still does not get traded (a
    downstream score-gate question, #545 Phase 2's territory, not this fixture's). `scripts/probes/
    _620_qcom.sql` / `_620_qcom_out.txt`.
  - **ASX / NBIS / IREN / SMTC 2026-04-08 / 04-08 / 04-08 / 03-30 — STILL EXCLUDED, margins measured.**
    None of the four ever reaches the floor, at ANY point in the regular session (checked at both
    daily-bar-high and minute-bar-high resolution, not just the open): ASX day high $24.16 = 8.88%
    (floor $24.187, short by 2.7¢); NBIS day high $127.75 = 8.82% (floor $127.97, short by 22¢);
    IREN RTH day high $38.90 = 8.84% (floor $38.957, short by 5.7¢ — one thin PRE-MARKET print at
    09:25 touched $39.01 = 9.15% on 12,416 shares, but the regular session never did, and bars before
    09:25 were not captured this session to resolve whether a 09:25 scan tick would have read that
    print or an earlier, lower one — left UNDECIDED and kept in debt per "if in doubt, keep it");
    SMTC day high $78.50 = 8.79% (floor $78.654, short by 15¢). `scripts/probes/_620_bars.psv` +
    `_620_bar_coverage_out.txt`.
  - **Data note**: `mi_intraday_bars` retention starts 2026-04-13 (confirmed via
    `scripts/probes/_620_bar_coverage.sql`) — STRL/ASX/NBIS/HUT/IREN (04-08) and SMTC (03-30) have
    ZERO stored bars, so the 6 above were measured from a fresh Alpaca SIP capture
    (`scripts/probes/_620_fetch_bars.py`, RAW adjustment, read-only, $0), matching the same feed the
    live overlay reads. QCOM (04-24) has full stored coverage AND a real scan_log row — the strongest
    possible evidence, used instead.
  - **Net: 3 of 7 fixed (STRL, HUT — genuinely admitted today; QCOM — reclassified to a different,
    already-out-of-scope gate). 4 remain: ASX, NBIS, IREN, SMTC — all within 0.03-0.22pp of the
    floor, none proven to cross it.** `gap_pct` (the psv session-open figure, provenance-checked
    below) is UNCHANGED for all 7 — only `gap_pct_admitted` (new field, MIN_GAP_PCT gate input only,
    evidence required inline) reflects this finding for STRL/HUT/QCOM.

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

    # #620, 2026-09-03 — the gap the CURRENT live admission path (ep_detector.py's real-time
    # overlay, `_apply_realtime_pass2` / `_apply_rt_universe_overlay`) actually decides at scan-tick
    # time, when it differs from and is HIGHER than `gap_pct` (the session-open print above) and
    # clears MIN_GAP_PCT. `gap_pct` stays the raw open-basis measurement (still provenance-checked
    # against _552_cohort.psv for psv-sourced members — never edited to "fix" a debt); this field is
    # consulted ONLY for the MIN_GAP_PCT gate in `_check_member`, and ONLY when set. Same evidence
    # discipline as label_source: never inferred — `gap_pct_admitted_basis` must name the exact bar/
    # tick/scan_log row it came from (test_gap_pct_admitted_requires_a_basis enforces non-empty).
    gap_pct_admitted: Optional[float] = None
    gap_pct_admitted_basis: Optional[str] = None

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
        # #620, 2026-09-03: MIN_GAP_PCT (open basis) is genuinely fixed by the live real-time
        # overlay. prev_close $382.22 confirmed against Alpaca's raw D-1 close (exact match, no
        # split). At the 09:35 scan tick (scheduler.py: ep_scan every 5 min 7:00-9:55 ET) the price
        # the scan reads is the just-closed 09:34 minute bar, close $419.385 -> (419.385-382.22)/
        # 382.22*100 = 9.72%, above the 9.0% floor, and it holds: 09:35 close $419.44 (9.74%), 09:39
        # close $422.22 (10.47%), 09:40 close $424.00 (10.93%) -- not a one-tick flicker. Measured
        # from a fresh Alpaca SIP capture (mi_intraday_bars has no coverage before 2026-04-13):
        # scripts/probes/_620_fetch_bars.py -> scripts/probes/_620_bars.psv.
        gap_pct_admitted=9.72,
        gap_pct_admitted_basis=(
            "STRL 2026-04-08 09:34 ET minute bar close $419.385 vs prev_close $382.22 = 9.72%, "
            "the price read at the 09:35 ep_scan tick; held through 09:44 (09:39 close $422.22 = "
            "10.47%, 09:40 close $424.00 = 10.93%). scripts/probes/_620_bars.psv."
        ),
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
        # #620, 2026-09-03: STILL EXCLUDED -- confirmed at minute-bar resolution, not just the open.
        # The session HIGH all day (09:30 bar, $24.16, matching mi_daily_closes' high_price exactly)
        # gives (24.16-22.19)/22.19*100 = 8.88%, short of the $24.187 floor by 2.7 cents (0.12pp).
        # No point in the regular session ever reaches MIN_GAP_PCT. scripts/probes/_620_bars.psv +
        # _620_bar_coverage_out.txt (mi_daily_closes cross-check).
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
        # #620, 2026-09-03: STILL EXCLUDED -- confirmed at minute-bar resolution, not just the open.
        # The session HIGH all day (09:30 bar, $127.75, matching mi_daily_closes' high_price exactly)
        # gives (127.75-117.40)/117.40*100 = 8.82%, short of the $127.966 floor by 22 cents (0.18pp)
        # -- the closest miss of the four. No point in the regular session ever reaches MIN_GAP_PCT.
        # scripts/probes/_620_bars.psv + _620_bar_coverage_out.txt.
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
        # #620, 2026-09-03: RECLASSIFIED, not a real-time-overlay fix -- a REAL mi_ep_scan_log row
        # exists for this exact ticker/date (id=4679, scan_time 2026-04-24 09:30:10 ET): gap_pct
        # 10.27%, prev_close $133.95. QCOM cleared the THEN-10.0% floor (before 08-19 existed, and
        # before any RT toggle existed) on the plain delayed Pass-1 read, which by 10 seconds
        # after the open already reflected trading past the literal open print (open $145.61 =
        # 8.70%; the accepted read was already ~$147.7). It entered the funnel, scored 32.4, and was
        # excluded by `score 32 < 50 (catalyst=routine)` -- a DIFFERENT gate (the LLM catalyst
        # judge), out of this test's own stated scope. QCOM was NEVER a MIN_GAP_PCT exclusion;
        # BASELINE_DEBT mischaracterized it since 2026-08-19. It still does not get traded -- that
        # is a downstream score-gate question (#545 Phase 2's territory), not this fixture's.
        # scripts/probes/_620_qcom.sql -> scripts/probes/_620_qcom_out.txt.
        gap_pct_admitted=10.27,
        gap_pct_admitted_basis=(
            "QCOM 2026-04-24: real mi_ep_scan_log row id=4679, scan_time 09:30:10 ET, gap_pct=10.27 "
            "vs prev_close=133.95 -- the ACTUAL historical admission, not a reconstruction. Excluded "
            "downstream by score 32.4 < 50 (catalyst=routine), not by MIN_GAP_PCT. scripts/probes/"
            "_620_qcom_out.txt."
        ),
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
        # #620, 2026-09-03: MIN_GAP_PCT (open basis) is genuinely fixed. prev_close $52.66 confirmed
        # against Alpaca's raw D-1 close (exact match, no split). The very first COMPLETED minute
        # bar (09:30, close $59.08) already reads (59.08-52.66)/52.66*100 = 12.19% -- the 09:31
        # `ep_scan_open` tick (scheduler.py: "first complete bar just closed") reads exactly that
        # bar, so there is no boundary ambiguity: admitted at the first possible post-open tick.
        # Measured from a fresh Alpaca SIP capture (mi_intraday_bars has no coverage before
        # 2026-04-13): scripts/probes/_620_fetch_bars.py -> scripts/probes/_620_bars.psv.
        gap_pct_admitted=12.19,
        gap_pct_admitted_basis=(
            "HUT 2026-04-08 09:30 ET minute bar close $59.08 vs prev_close $52.66 = 12.19%, read "
            "at the 09:31 ep_scan_open tick (the just-closed first bar). scripts/probes/"
            "_620_bars.psv."
        ),
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
        # #620, 2026-09-03: STILL EXCLUDED -- confirmed at minute-bar resolution, not just the open.
        # The session HIGH all day (09:32 bar, $78.50, matching mi_daily_closes' high_price exactly)
        # gives (78.50-72.16)/72.16*100 = 8.79%, short of the $78.654 floor by 15 cents (0.21pp).
        # (This is also the day SMTC closed BELOW its prior close -- a gap-and-fade -- so its listed
        # >=10R comes from a later move, per winner_r_available's 60-session horizon, not this day.)
        # No point in the regular session ever reaches MIN_GAP_PCT. scripts/probes/_620_bars.psv +
        # _620_bar_coverage_out.txt.
    ),
    EPFixtureMember(
        ticker="IREN", alert_date="2026-04-08", label_source="evidence:winner_r_available_2026-08-16",
        label_note="10-20R tradeable winner (EP-day-low stop geometry).",
        gap_pct=8.28, gap_basis="session open (_552_cohort.psv)", prev_close=35.74,
        unverified_gates=_UNVERIFIED_STANDARD,
        # #620, 2026-09-03: STILL EXCLUDED (kept in debt, not resolved either way on the pre-market
        # wrinkle below -- "if in doubt, keep it"). RTH session HIGH all day (09:30 bar, $38.90,
        # matching mi_daily_closes' high_price exactly) gives (38.90-35.74)/35.74*100 = 8.84%, short
        # of the $38.957 floor by 5.7 cents (0.16pp) -- never crosses during the regular session.
        # ⚠ One thin PRE-MARKET print at 09:25 touched $39.01 on 12,416 shares = 9.15%, ABOVE the
        # floor -- but `scheduler.py`'s ep_scan runs 7:00-9:55 ET (a real tick could land at 09:25),
        # and bars before 09:25 were not captured this session, so whether that specific tick would
        # have read this print (vs. an earlier, lower one) is UNDECIDABLE from what was fetched here
        # -- not resolved either way, kept in debt per the fixture's own "if in doubt, keep it" rule.
        # scripts/probes/_620_bars.psv + _620_bar_coverage_out.txt.
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
# BASELINE_DEBT — see the module docstring above for the full rationale. Recorded 2026-08-19,
# last revised 2026-09-03.
#
# Key: (ticker, alert_date). Value: the frozenset of gate keys CURRENTLY tolerated as pre-existing
# exclusions for that member — the exact strings `_check_member` in the test file emits as its
# first element of each (gate_key, message) result. Nothing outside this exact set is tolerated;
# a member hitting one more gate than what's recorded here is a regression, not debt.
#
# ⚠ NEVER add an operator-named member's key here — `label_source == "operator"` members must
# clear every gate unconditionally, checked by `test_operator_named_members_never_carry_baseline_
# tolerance` in the test file.
BASELINE_RECORDED_DATE = "2026-09-03"

# 2026-08-19: MU, MRVL, SNOW, ALGM, AMKR, UMC(2026-05-06), BE, USAR removed — all clear
# MIN_GAP_PCT at the new 9.0% floor (gap 9.03-9.94%). The remaining 7 all gap 8.1-8.7%, still
# below 9.0%.
#
# 2026-09-03 (#620, see the module docstring's "UPDATED 2026-09-03" section for full evidence):
# STRL and HUT removed — the CURRENT live real-time overlay genuinely admits both (measured from
# fresh Alpaca minute bars, gap_pct_admitted on each member). QCOM removed — RECLASSIFIED, not a
# real-time fix: a real mi_ep_scan_log row (id=4679) proves it was never a MIN_GAP_PCT exclusion at
# all, then or now; its actual exclusion is the score/catalyst gate, out of this fixture's scope.
# ASX, NBIS, IREN, SMTC remain — none reaches the floor at any point in the regular session, even
# at minute-bar-high resolution (margins 0.12-0.21pp; IREN also carries an undecided pre-market
# wrinkle, see its member comment — kept in debt, not resolved either way).
BASELINE_DEBT: Dict[Tuple[str, str], FrozenSet[str]] = {
    ("ASX", "2026-04-08"): frozenset({"MIN_GAP_PCT"}),
    ("NBIS", "2026-04-08"): frozenset({"MIN_GAP_PCT"}),
    ("SMTC", "2026-03-30"): frozenset({"MIN_GAP_PCT"}),
    ("IREN", "2026-04-08"): frozenset({"MIN_GAP_PCT"}),
}
