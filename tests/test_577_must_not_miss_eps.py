"""#577 — RULE 0 / P1 made mechanical: "A REAL EP MUST NEVER BE MISSED."

`docs/roadmap/ep_profitability_program.md` § THE PRINCIPLES, P1 (operator 2026-08-19):
    "regardless of conclusions, EPs like MRNA cannot be missed, that's the first thing; it may not
    work every time, that's the low winrate / rarity, but it should not miss a real EP which is the
    true test."

A false EXCLUSION leaves no row, no skip_reason, no trace; a false inclusion is a -1R loss we can
see. The measurable error is the harmless one — which is exactly why recall has to be a mechanical
gate, not a judgement call re-asked every time a filter changes.

WHAT THIS TESTS: `tests/fixtures/must_not_miss_eps.py` is a labelled set of REAL EPs (operator-named
or evidence-sourced — see that file's docstring for the label-source discipline). This module
replays each member's recorded metrics through the CURRENT selection stack's threshold constants —
imported live from source, never hand-copied — and fails, naming the ticker/date and the exact gate,
if any member would be excluded today. Extending the fixture is a one-line data edit in that file;
this test file does not need to change.

SCOPE, STATED HONESTLY: this covers the OBJECTIVE, deterministic pre-alert gates that decide
universe admission with no time-of-day dependence — gap floor, price floor, prior-day volume floor,
ticker-shape filter, pre-gap extension ceiling, ADV-dollar floor, ATR% ceiling, market-cap floor.
It deliberately does NOT cover: the real-time RVOL@T gate (`FILTER_PM_RVOL_TOO_LOW` /
`FILTER_SESSION_RVOL_TOO_LOW`) — inherently time-of-day-dependent and not reconstructable from daily
bars; the LLM catalyst-quality judge — costs money per call and is non-deterministic, out of scope
for a $0 suite test; and any SHADOW/candidate axis not yet wired into the live composite (e.g.
#569's pregap base-days axis) — by construction those cannot exclude anything TODAY, and P1 already
says this exact fixture is what must run against a shadow axis BEFORE it is ever promoted.
"""
from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import pytest

from agents.market_intelligence import ep_detector  # unstubbed — plain module constants
from tests.fixtures import must_not_miss_eps as fx

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FILTERS_PATH = _REPO_ROOT / "agents" / "market_intelligence" / "backtester" / "filters.py"


def _load_real_backtester_filters():
    """Load backtester/filters.py fresh, by file path, under a private module name.

    `tests/conftest.py` permanently stubs `agents.market_intelligence.backtester.filters` in
    sys.modules with 3 mocked FUNCTIONS ONLY (validate_orb_entry, check_filters, compute_atr_14) —
    no constants — so dev environments without asyncpg/FMP installed can still import ep_detector.
    That stub is installed unconditionally at pytest-session start, before any test module loads,
    so `import agents.market_intelligence.backtester.filters` inside a normal test always returns
    the stub, never the real MIN_MARKET_CAP / MAX_ATR_PCT / MIN_ADV_DOLLAR_VOLUME values.

    Loading by file path bypasses that stub entirely (different sys.modules key) and leaves it
    untouched for every other test in the suite — verified: this does not mutate
    sys.modules["agents.market_intelligence.backtester.filters"]. The thresholds below are read
    straight from source every run, so a future threshold edit is picked up automatically without
    editing this test.
    """
    spec = importlib.util.spec_from_file_location("_ep577_real_backtester_filters", _FILTERS_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_real_filters = _load_real_backtester_filters()

THRESHOLDS = dict(
    MIN_GAP_PCT=ep_detector.MIN_GAP_PCT,
    MIN_PREV_CLOSE=ep_detector.MIN_PREV_CLOSE,
    MIN_PREV_DAY_VOLUME=ep_detector.MIN_PREV_DAY_VOLUME,
    MAX_TICKER_LEN=ep_detector.MAX_TICKER_LEN,
    MAX_EXTENSION_PCT=ep_detector.MAX_EXTENSION_PCT,
    MIN_ADV_DOLLAR_VOLUME=_real_filters.MIN_ADV_DOLLAR_VOLUME,
    MAX_ATR_PCT=_real_filters.MAX_ATR_PCT,
    MIN_MARKET_CAP=_real_filters.MIN_MARKET_CAP,
)

# Every gate this fixture tracks — used by the coverage test to make sure no member silently
# omits a metric without declaring it unverified.
GATE_KEYS = (
    "prev_close", "prev_day_volume", "gap_pct", "extension_pct_pregap5d",
    "adv_dollar_20d", "atr_pct_14d", "market_cap",
)


def _member_id(member: "fx.EPFixtureMember") -> str:
    return f"{member.ticker}_{member.alert_date}"


def _check_member(member: "fx.EPFixtureMember", thresholds: dict) -> list[tuple[str, str]]:
    """Replay one fixture member through every gate it has a recorded value for.

    Returns a list of (gate_key, message) pairs, one per gate that would EXCLUDE the member —
    empty means the member clears every gate it has data for. A gate with no recorded value
    (None) is skipped here — the coverage test elsewhere enforces that skip was DECLARED, not
    silent. `gate_key` is the exact string `BASELINE_DEBT` (tests/fixtures/must_not_miss_eps.py)
    keys its tolerated-gate sets with — changing a key here without updating that dict is a
    self-detecting mistake: the regression test would then treat the (renamed) gate as brand new.
    """
    failures: list[tuple[str, str]] = []
    who = f"{member.ticker} {member.alert_date}"

    if len(member.ticker) > thresholds["MAX_TICKER_LEN"]:
        failures.append((
            "MAX_TICKER_LEN",
            f"{who} excluded by MAX_TICKER_LEN: ticker length {len(member.ticker)} > "
            f"{thresholds['MAX_TICKER_LEN']} (warrant/unit-shaped symbol filter)",
        ))

    if member.prev_close is not None and member.prev_close < thresholds["MIN_PREV_CLOSE"]:
        failures.append((
            "MIN_PREV_CLOSE",
            f"{who} excluded by MIN_PREV_CLOSE: prior close ${member.prev_close:.2f} < "
            f"${thresholds['MIN_PREV_CLOSE']:.2f} floor",
        ))

    if member.prev_day_volume is not None and member.prev_day_volume < thresholds["MIN_PREV_DAY_VOLUME"]:
        failures.append((
            "MIN_PREV_DAY_VOLUME",
            f"{who} excluded by MIN_PREV_DAY_VOLUME: prior-day volume "
            f"{member.prev_day_volume:,.0f} < {thresholds['MIN_PREV_DAY_VOLUME']:,.0f} floor",
        ))

    if member.gap_pct is not None and member.gap_pct < thresholds["MIN_GAP_PCT"]:
        basis = f" [gap basis: {member.gap_basis}]" if member.gap_basis else ""
        failures.append((
            "MIN_GAP_PCT",
            f"{who} excluded by MIN_GAP_PCT at the default {thresholds['MIN_GAP_PCT']:.1f}% floor "
            f"(env-overridable via EP_MIN_GAP_PCT; universe admission — leaves no mi_ep_scan_log "
            f"row): gap {member.gap_pct:.2f}% < {thresholds['MIN_GAP_PCT']:.1f}%{basis}. "
            f"NOTE: ADMISSION may still recover — ep_profitability_program.md records 78% of "
            f"tradeable missed winners gapping under 10% at the open crossed 10% intraday. ENTRY "
            f"cannot recover the same way once 9:45 ET passes: the ORB submission window is "
            f"09:30-09:44 ET, a HIGH arriving 09:45-09:59 gets WINDOW_OUT_OF_ORB, and the 10:00 ET "
            f"cleanup job cancels any unfilled order (CLAUDE.md, magna53_ep.md). So a sub-floor gap "
            f"at the open is not proof the whole live stack would have missed this name, but it IS "
            f"proof the trade would have been missed unless the cross landed inside that ~15-minute "
            f"window.",
        ))

    if (member.extension_pct_pregap5d is not None
            and member.extension_pct_pregap5d >= thresholds["MAX_EXTENSION_PCT"]):
        failures.append((
            "MAX_EXTENSION_PCT",
            f"{who} excluded by MAX_EXTENSION_PCT: pre-gap 5-day extension "
            f"{member.extension_pct_pregap5d:.1f}% >= {thresholds['MAX_EXTENSION_PCT']:.1f}% "
            f"ceiling",
        ))

    if member.adv_dollar_20d is not None and member.adv_dollar_20d < thresholds["MIN_ADV_DOLLAR_VOLUME"]:
        failures.append((
            "FILTER_ADV_TOO_LOW",
            f"{who} excluded by FILTER_ADV_TOO_LOW: median $ volume ${member.adv_dollar_20d:,.0f} "
            f"< ${thresholds['MIN_ADV_DOLLAR_VOLUME']:,.0f} floor",
        ))

    if member.atr_pct_14d is not None and member.atr_pct_14d > thresholds["MAX_ATR_PCT"]:
        failures.append((
            "FILTER_ATR_TOO_HIGH",
            f"{who} excluded by FILTER_ATR_TOO_HIGH: ATR% {member.atr_pct_14d:.1f}% > "
            f"{thresholds['MAX_ATR_PCT']:.1f}% ceiling",
        ))

    if member.market_cap is not None and member.market_cap < thresholds["MIN_MARKET_CAP"]:
        failures.append((
            "FILTER_MCAP_TOO_SMALL",
            f"{who} excluded by FILTER_MCAP_TOO_SMALL: market cap ${member.market_cap:,.0f} < "
            f"${thresholds['MIN_MARKET_CAP']:,.0f} floor",
        ))

    return failures


# ── The must-not-miss replay, tolerating ONLY today's recorded baseline debt ───────────────────
# The 2026-08-19 finding — 15 of 25 evidence-sourced tradeable >=10R winners excluded by
# MIN_GAP_PCT — is real, stays visible every run (pytest_terminal_summary, tests/conftest.py), and
# is pinned by exact gate in fx.BASELINE_DEBT. This test tolerates ONLY that exact recorded set.
# It goes RED, hard, no exceptions, for: (a) any member excluded by a gate not already recorded for
# it — a brand-new miss or the debt getting worse; (b) any operator-named member excluded by
# anything at all (operator-named keys can never enter BASELINE_DEBT — see the guard test below).
# No xfail, no skip, no threshold change — selection criteria are THE LINE, the operator's call.

_ASSERTED_MEMBERS = [m for m in fx.MUST_NOT_MISS if not m.excluded]


@pytest.mark.parametrize("member", _ASSERTED_MEMBERS, ids=_member_id)
def test_no_regression_beyond_the_recorded_baseline(member: "fx.EPFixtureMember"):
    results = _check_member(member, THRESHOLDS)
    actual_gates = {gate_key for gate_key, _ in results}
    tolerated = fx.BASELINE_DEBT.get((member.ticker, member.alert_date), frozenset())
    unexpected_gates = actual_gates - tolerated

    assert not unexpected_gates, (
        f"REGRESSION — {member.ticker} {member.alert_date} ({member.label_source}) is now excluded "
        f"by a gate NOT already recorded as debt (tolerated today: {sorted(tolerated) or 'none'}): "
        + " | ".join(msg for gate_key, msg in results if gate_key in unexpected_gates)
    )


def test_operator_named_members_never_carry_baseline_tolerance():
    """Structural guard for DoD requirement 4: an operator-named member gets NO baseline debt
    tolerance, ever. This does not rely on anyone remembering the rule — it fails the moment an
    operator-named (ticker, alert_date) key is added to BASELINE_DEBT, regardless of why."""
    operator_keys = {
        (m.ticker, m.alert_date) for m in fx.MUST_NOT_MISS if m.label_source == "operator"
    }
    overlap = operator_keys & set(fx.BASELINE_DEBT.keys())
    assert not overlap, (
        f"operator-named member(s) {overlap} must never carry baseline-debt tolerance — remove "
        f"from BASELINE_DEBT; an operator-named EP is a hard failure if excluded, no exceptions."
    )


# ── Coverage: no metric may be silently absent ───────────────────────────────────────────────

@pytest.mark.parametrize("member", fx.MUST_NOT_MISS, ids=_member_id)
def test_coverage_is_declared_for_every_member(member: "fx.EPFixtureMember"):
    """Every tracked gate must be either a recorded value or explicitly declared unverified.

    A bare `None` with no declaration would silently read as "not applicable" — this is the same
    invisibility P1 warns about, just moved into the fixture itself. Force every gap to be visible.
    """
    for key in GATE_KEYS:
        value = getattr(member, key)
        declared = key in member.unverified_gates
        assert value is not None or declared, (
            f"{member.ticker} {member.alert_date}: gate '{key}' is neither recorded nor listed in "
            f"unverified_gates — a silent gap. Record a real value or add '{key}' to "
            f"unverified_gates."
        )

    assert member.label_source, f"{member.ticker} {member.alert_date}: missing label_source"
    if member.excluded:
        assert member.exclude_reason, (
            f"{member.ticker} {member.alert_date}: excluded=True but no exclude_reason — a silent "
            f"drop, exactly what the DoD forbids."
        )


def test_thresholds_loaded_are_the_real_ones_not_the_stub():
    """Sanity: confirm the file-path loader actually returned real values, not a leftover mock.

    A MagicMock compares unequal to any float, so if the stub ever leaked through here this
    assertion goes red immediately rather than silently comparing member metrics to a mock.
    """
    assert THRESHOLDS["MIN_MARKET_CAP"] == 500_000_000
    assert THRESHOLDS["MAX_ATR_PCT"] == 15.0
    assert THRESHOLDS["MIN_ADV_DOLLAR_VOLUME"] == 1_000_000
    assert THRESHOLDS["MIN_GAP_PCT"] >= 1.0  # env-overridable; sanity floor, not the exact value
    assert THRESHOLDS["MAX_EXTENSION_PCT"] == 75.0   # 2026-08-22 operator-signed loosening (#577A)


def test_loading_real_filters_does_not_contaminate_sys_modules():
    """The file-path loader must leave the rest of the suite's stub untouched (see docstring on
    `_load_real_backtester_filters`). If this ever starts failing, some other test that relies on
    `backtester.filters.check_filters` being a harmless mock could start hitting real DB/network
    code instead."""
    import sys
    stub = sys.modules.get("agents.market_intelligence.backtester.filters")
    assert stub is not None
    assert stub is not _real_filters
    assert not hasattr(stub, "MIN_MARKET_CAP")  # the stub only ever carries 3 mocked functions


# ── Mutation proof: the fixture must actually be able to go red, and to come back clean ───────
# Per the task's own instruction: "a test that passes with AND without the change is not a test."
# Mutate a known-CLEAN member (MRNA — corroborated independently: it was actually entered live on
# 2026-08-19, see the fixture file's comment), confirm the check function reports it excluded and
# NAMES the ticker/date/gate, then confirm the original recorded value is clean again — proving
# both directions, not just the red one.

def test_mutation_proof_gap_gate_catches_and_names_the_drop():
    mrna = next(m for m in fx.MUST_NOT_MISS if m.ticker == "MRNA")
    assert not _check_member(mrna, THRESHOLDS), "precondition: MRNA must be clean before mutating"

    mutated = mrna._replace(gap_pct=5.0)  # below the 10% floor — local copy, fixture untouched
    failures = _check_member(mutated, THRESHOLDS)
    assert failures, "mutation did not produce a failure — the gate check is not wired correctly"
    assert any(gk == "MIN_GAP_PCT" and "MRNA" in msg for gk, msg in failures), (
        f"failure doesn't name MRNA + the dropping gate: {failures}"
    )

    # Revert (fx.MUST_NOT_MISS was never touched — `mutated` was a separate NamedTuple copy — this
    # re-check proves the ORIGINAL recorded value is still the clean one, i.e. the "revert" half).
    reverted = next(m for m in fx.MUST_NOT_MISS if m.ticker == "MRNA")
    assert reverted.gap_pct == 84.25
    assert not _check_member(reverted, THRESHOLDS), "MRNA should be clean again after revert"


# ── Mutation proof for the REGRESSION mechanism itself (this session's addition) ───────────────
# Requested explicitly: prove a 16th exclusion goes red, prove an operator-named exclusion goes
# red regardless of any baseline entry, and prove both revert cleanly. Neither test below mutates
# fx.MUST_NOT_MISS or fx.BASELINE_DEBT — every mutated object is a local `._replace()` copy.

def test_mutation_proof_a_16th_exclusion_is_a_regression():
    """Take a member that is CLEAN today (not in BASELINE_DEBT) and push it below the gap floor.
    The no-regression check must flag it as unexpected — a 16th exclusion is news, not debt."""
    clean = next(
        m for m in fx.MUST_NOT_MISS
        if not m.excluded and m.label_source != "operator"
        and (m.ticker, m.alert_date) not in fx.BASELINE_DEBT
    )
    tolerated = fx.BASELINE_DEBT.get((clean.ticker, clean.alert_date), frozenset())
    assert tolerated == frozenset(), "precondition: chosen member must start with zero tolerance"

    mutated = clean._replace(gap_pct=5.0)
    actual_gates = {gk for gk, _ in _check_member(mutated, THRESHOLDS)}
    unexpected = actual_gates - tolerated
    assert unexpected == {"MIN_GAP_PCT"}, (
        f"a 16th exclusion on {clean.ticker} {clean.alert_date} did not register as an unexpected "
        f"regression — the no-regression gate is not wired correctly (got {unexpected})"
    )

    # Revert: the original fixture entry is untouched and still clears every recorded-baseline gate.
    reverted = next(
        m for m in fx.MUST_NOT_MISS if m.ticker == clean.ticker and m.alert_date == clean.alert_date
    )
    reverted_actual = {gk for gk, _ in _check_member(reverted, THRESHOLDS)}
    assert not (reverted_actual - fx.BASELINE_DEBT.get((reverted.ticker, reverted.alert_date), frozenset()))


def test_mutation_proof_operator_named_exclusion_is_always_a_regression():
    """MRNA carries zero baseline tolerance by construction (guarded separately above). Confirm
    that pushing it below the gap floor registers as unexpected REGARDLESS of any baseline entry
    — i.e. an operator-named member gets no free pass even in principle, not just by omission."""
    mrna = next(m for m in fx.MUST_NOT_MISS if m.ticker == "MRNA")
    tolerated = fx.BASELINE_DEBT.get((mrna.ticker, mrna.alert_date), frozenset())
    assert tolerated == frozenset(), "MRNA must never carry baseline tolerance"

    mutated = mrna._replace(gap_pct=5.0)
    actual_gates = {gk for gk, _ in _check_member(mutated, THRESHOLDS)}
    unexpected = actual_gates - tolerated
    assert "MIN_GAP_PCT" in unexpected, (
        "an operator-named member's exclusion did not register as a regression — this must never "
        "be tolerable, by any mechanism"
    )

    # Revert.
    reverted = next(m for m in fx.MUST_NOT_MISS if m.ticker == "MRNA")
    assert not _check_member(reverted, THRESHOLDS), "MRNA should be clean again after revert"


# ── Provenance guard: the recorded gap_pct/prev_close must still match the source file ────────
# Closes two holes at once: (a) the psv could drift from the fixture silently; (b) a future edit
# could null out gap_pct and add it to unverified_gates to make a red disappear — the coverage
# test alone permits null+declared, which is exactly the exemption backdoor the DoD forbids. Any
# member whose gap_basis cites _552_cohort.psv is re-checked against that file on every run.

_COHORT_PSV = _REPO_ROOT / "scripts" / "probes" / "_552_cohort.psv"


def _load_cohort_psv_rows() -> dict:
    rows = {}
    with open(_COHORT_PSV, newline="") as f:
        for row in csv.reader(f, delimiter="|"):
            if len(row) < 12:
                continue
            rows[(row[0], row[1])] = row
    return rows


_PSV_SOURCED = [
    m for m in fx.MUST_NOT_MISS
    if m.gap_basis and "_552_cohort.psv" in m.gap_basis
]


@pytest.mark.parametrize("member", _PSV_SOURCED, ids=_member_id)
def test_psv_sourced_members_match_the_source_file(member: "fx.EPFixtureMember"):
    rows = _load_cohort_psv_rows()
    key = (member.ticker, member.alert_date)
    assert key in rows, (
        f"{member.ticker} {member.alert_date} claims provenance from _552_cohort.psv but is not "
        f"present in that file — the fixture's citation is stale or wrong."
    )
    row = rows[key]
    psv_gap = float(row[2])
    psv_prev_close = float(row[5])
    assert member.gap_pct == pytest.approx(psv_gap, abs=0.01), (
        f"{member.ticker} {member.alert_date}: fixture gap_pct={member.gap_pct} does not match "
        f"_552_cohort.psv col[2]={psv_gap} — the fixture has drifted from its cited source."
    )
    assert member.prev_close == pytest.approx(psv_prev_close, abs=0.01), (
        f"{member.ticker} {member.alert_date}: fixture prev_close={member.prev_close} does not "
        f"match _552_cohort.psv col[5]={psv_prev_close} — the fixture has drifted from its cited "
        f"source."
    )


# The exact 26 (ticker, alert_date) pairs from winner_r_available_2026-08-16.txt GEOMETRY 1
# (>=10R bucket) — pinned as a fixed identity, NOT derived from whatever happens to cite the psv
# in gap_basis today. This keeps the median check scoped to the cohort it was actually verified
# against; a future member added to _PSV_SOURCED for an unrelated reason must not be able to shift
# this median and produce a red that has nothing to do with the column mapping.
_ORIGINAL_26_WINNER_COHORT = frozenset({
    ("MU", "2026-04-08"), ("UMC", "2026-04-17"), ("STRL", "2026-04-08"), ("MRVL", "2026-03-31"),
    ("ASX", "2026-04-08"), ("SNDK", "2026-04-08"), ("SNOW", "2026-05-07"), ("ALGM", "2026-04-08"),
    ("NBIS", "2026-04-08"), ("AMKR", "2026-04-08"), ("AEHR", "2026-03-31"), ("TDIC", "2026-05-12"),
    ("UMC", "2026-05-06"), ("FLY", "2026-03-12"), ("BE", "2026-04-08"), ("USAR", "2026-04-08"),
    ("QCOM", "2026-04-24"), ("QBTS", "2026-04-08"), ("AMD", "2026-04-24"), ("HUT", "2026-04-08"),
    ("QURE", "2026-05-29"), ("ARM", "2026-05-06"), ("SMTC", "2026-03-30"), ("IREN", "2026-04-08"),
    ("APLD", "2026-04-08"), ("INTC", "2026-04-24"),
})


def test_psv_cohort_median_gap_matches_the_programme_docs_independent_figure():
    """Second, independent confirmation of the column mapping (col[2]=gap%, col[5]=prev_close):
    the median gap of the 25 asserted (non-excluded, i.e. ex-TDIC) members of the fixed 26-winner
    cohort should land at the 9.9% the programme doc states independently for this exact cohort
    (ep_profitability_program.md: "The winner profile inverts our grading logic"). Scoped to
    `_ORIGINAL_26_WINNER_COHORT` specifically — see that constant's comment for why."""
    import statistics
    gaps = [
        m.gap_pct for m in fx.MUST_NOT_MISS
        if not m.excluded and m.gap_pct is not None
        and (m.ticker, m.alert_date) in _ORIGINAL_26_WINNER_COHORT
    ]
    assert len(gaps) == 25, f"expected all 25 non-excluded cohort members present, got {len(gaps)}"
    median = statistics.median(gaps)
    assert median == pytest.approx(9.9, abs=0.1), (
        f"median gap {median:.3f}% does not match the programme doc's independently-stated 9.9% — "
        f"re-derive the column mapping before trusting any value from _552_cohort.psv."
    )


def test_mutation_proof_market_cap_gate_catches_and_names_the_drop():
    """Second axis for the same proof, on a gate this fixture currently leaves unverified for
    every member — confirms the gate machinery works even for a metric no real member currently
    exercises, so adding a verified market_cap later is guaranteed to be checked correctly."""
    mrna = next(m for m in fx.MUST_NOT_MISS if m.ticker == "MRNA")
    mutated = mrna._replace(market_cap=100_000_000.0)  # below the $500M floor
    failures = _check_member(mutated, THRESHOLDS)
    assert failures
    assert any(gk == "FILTER_MCAP_TOO_SMALL" and "MRNA" in msg for gk, msg in failures)
