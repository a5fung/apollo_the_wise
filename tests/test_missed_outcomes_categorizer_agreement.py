"""#570 follow-up (2026-08-25) — the SQL-side and Python-side skip_category
categorizers must agree.

Card: the D-1 universe-floor logging half of #570 shipped (`ep_detector.py`'s
two silent floors now write a `filter:universe_prev_close_too_low` /
`filter:universe_prev_day_illiquid` skip_reason), but the downstream half
that keeps those rows out of the default `/missed` view did not: #570 added
a `d1_universe_floor` branch to `_categorize_skip_reason` (Python) and never
added the matching `WHEN` clause to `_SKIP_CATEGORY_CASE_SQL` (the SQL-side
mapping `refresh_missed_outcomes` actually INSERTs with). In prod, 213/222
floor rows on 08-24 landed in `filter_other` instead of `d1_universe_floor`
— exactly the catch-all bucket the fix existed to keep them out of.

This file:
  1. Pins the fix — a floor reason now categorises to `d1_universe_floor` on
     BOTH paths, regardless of the embedded price/volume numbers (the reason
     text is `"filter:universe_prev_close_too_low: prior close $X < $5.00
     floor"` — matching must be on the PREFIX, never the whole string, or
     every distinct price becomes its own bucket).
  2. Pins that non-floor reasons are unchanged by the edit.
  3. Is the "two categorizers, one concept" guard the fix's own code comment
     promises (P15-B, `docs/roadmap/ep_profitability_program.md`): it
     evaluates the REAL `_SKIP_CATEGORY_CASE_SQL` string (not a
     reimplementation of it — ILIKE has no sqlite equivalent, so the only
     substitution is ILIKE -> LIKE; sqlite's LIKE is ASCII case-insensitive
     and uses the same %/_ wildcards as Postgres ILIKE, so this executes the
     production CASE expression byte-for-byte) against a named vocabulary
     built from `broker/skip_reasons.py`'s bounded prefix list plus the
     free-form substrings both sides parse, and fails if the two disagree on
     any of it.
  4. Is mutation-proof: deleting the new WHEN clause from the SQL flips the
     floor-reason result, proving the sqlite harness actually exercises the
     added clause rather than passing vacuously.

Why NOT a single generated source of truth (the first option the #570
follow-up card asked to evaluate): `_SKIP_CATEGORY_CASE_SQL`'s
session_rvol_low/pm_rvol_low arms already match a handful of legacy
substrings ("pm volume", "rel volume", "rel_vol", "low volume", "projected")
that `_categorize_skip_reason` does not — a divergence that predates and is
unrelated to #570 (discovered while writing this test). A generated CASE
would force resolving those in this commit: narrowing SQL recategorizes
already-stored prod rows on the next reconcile; widening Python changes
`/scanned`'s funnel-stage assignment (`scanned_report._stage_for`), a
surface that shipped 2026-08-24 and isn't part of this fix. Per P15-B
("if one genuinely must differ, that is a finding to surface with its
reason, never a silent exception — pin the invariant with a test that fails
if a second path reappears"), the two stay hand-mirrored and this file is
that pin. The known divergences are named in `_KNOWN_DIVERGENT_REASONS`
below and excluded from the agreement loop with their reason; anything else
disagreeing fails the test.
"""
from __future__ import annotations

import re
import sqlite3

import pytest

from agents.market_intelligence import missed_outcomes
from agents.market_intelligence.broker import skip_reasons as sr


# ── SQL-side evaluator: executes the REAL production CASE expression ────────

def _eval_sql_category(source: str, skip_reason: str | None) -> str:
    """Run `_SKIP_CATEGORY_CASE_SQL` — the literal string production uses —
    through sqlite. Only textual change: ILIKE -> LIKE (sqlite has no ILIKE
    keyword, but its LIKE is already ASCII case-insensitive by default and
    uses the same %/_ wildcards, so this is a syntax substitution, not a
    semantic one)."""
    sql = missed_outcomes._SKIP_CATEGORY_CASE_SQL.replace("ILIKE", "LIKE")
    query = f"SELECT ({sql}) FROM (SELECT ? AS source, ? AS skip_reason)"
    conn = sqlite3.connect(":memory:")
    try:
        row = conn.execute(query, (source, skip_reason)).fetchone()
    finally:
        conn.close()
    return row[0]


def _eval_py_category(source: str, skip_reason: str | None) -> str:
    return missed_outcomes._categorize_skip_reason(source, skip_reason)


# ── 1. The fix itself ────────────────────────────────────────────────────────

@pytest.mark.parametrize("prev_close", [0.68, 4.99, 1.23, 3.00])
def test_prev_close_floor_categorizes_both_paths_regardless_of_number(prev_close):
    reason = f"{sr.FILTER_UNIVERSE_PREV_CLOSE_TOO_LOW}: prior close ${prev_close:.2f} < $5.00 floor"
    assert _eval_py_category("scan_filter", reason) == "d1_universe_floor"
    assert _eval_sql_category("scan_filter", reason) == "d1_universe_floor"


@pytest.mark.parametrize("prev_volume", [100, 49_999, 0, 12_345])
def test_prev_volume_floor_categorizes_both_paths_regardless_of_number(prev_volume):
    reason = (f"{sr.FILTER_UNIVERSE_PREV_DAY_ILLIQUID}: prior-day volume "
              f"{prev_volume:,} < 50,000 shares floor")
    assert _eval_py_category("scan_filter", reason) == "d1_universe_floor"
    assert _eval_sql_category("scan_filter", reason) == "d1_universe_floor"


def test_d1_universe_floor_stays_structural_and_hidden_from_default_missed():
    """The categorization alone only delivers the ship-note claim if the
    category is ALSO wired into the untradeable/structural sets — confirm
    both are still true after this edit (regression guard on #570's own
    wiring, not something this fix touched)."""
    assert "d1_universe_floor" in missed_outcomes._UNTRADEABLE_CATEGORIES
    assert missed_outcomes._CATEGORY_KIND["d1_universe_floor"] == "structural"
    assert "d1_universe_floor" not in missed_outcomes._SHOULDVE_ENTERED_CATEGORIES


# ── 2. Non-floor reasons unchanged ──────────────────────────────────────────

@pytest.mark.parametrize("source,reason,expected", [
    ("moderate_alert", None, "moderate_tier"),
    ("high_unentered", None, "high_unentered"),
    ("high_unentered", f"{sr.BLOCK_MAX_POSITIONS}: 5 of 5 slots full", "cap_blocked"),
    ("high_unentered", f"{sr.BLOCK_CIRCUIT_BREAKER}: 24h cooldown active", "breaker_blocked"),
    ("high_unentered", f"{sr.SETUP_STOP_TOO_WIDE}: ORB $1.24 vs 1.5x ATR $0.83", "stop_too_wide"),
    ("scan_filter", "EP cooldown — alerted within last 60 days", "cooldown"),
    ("scan_filter", "score 42 < 50 (routine catalyst)", "score_below_50"),
    ("scan_filter", "score 55 < bar 65 (some catalyst)", "score_below_50"),
    ("scan_filter", f"{sr.FILTER_MCAP_TOO_SMALL}: $80M < $150M floor", "mcap_low"),
    ("scan_filter", "some totally unrecognized filter text", "filter_other"),
    ("scan_filter", None, "filter_other"),
])
def test_non_floor_reasons_unchanged(source, reason, expected):
    assert _eval_py_category(source, reason) == expected
    assert _eval_sql_category(source, reason) == expected


def test_moderate_alert_ignores_skip_reason_on_both_paths():
    """source == 'moderate_alert' short-circuits BEFORE the reason is ever
    inspected on both sides — pin this explicitly since it's the kind of
    ordering an edit could break on one side and not the other."""
    reason = f"{sr.FILTER_ATR_TOO_HIGH}: this text must be ignored"
    assert _eval_py_category("moderate_alert", reason) == "moderate_tier"
    assert _eval_sql_category("moderate_alert", reason) == "moderate_tier"


# ── 3. Full-vocabulary agreement guard ──────────────────────────────────────

# Every bounded skip_reason prefix from broker/skip_reasons.py (the
# documented SoT for mi_live_trades.skip_reason), realized with a
# representative ": detail" suffix, paired with the source lineage it
# actually appears under in mi_ep_missed_outcomes (see missed_outcomes.py's
# module docstring: block:/window:/setup:/infra:/broker: reasons come from
# mi_live_trades via the high_unentered lineage; filter:/free-form reasons
# come from mi_ep_scan_log via the scan_filter lineage).
_HIGH_UNENTERED_VOCAB = [
    sr.BLOCK_MAX_POSITIONS, sr.BLOCK_DAILY_LOSS, sr.BLOCK_CIRCUIT_BREAKER,
    sr.BLOCK_DRAWDOWN_BREAKER, sr.BLOCK_STRATEGY_DISABLED, sr.BLOCK_STRATEGY_IN_SHADOW,
    sr.BLOCK_STRATEGY_DEPRECATED, sr.BLOCK_PAPER_STRATEGY_ON_LIVE,
    sr.BLOCK_TICKER_OPEN_POSITION, sr.BLOCK_PDT_LOCKOUT_IMMINENT,
    sr.BLOCK_PDT_LOCKOUT_ACTIVE, sr.BLOCK_STRATEGY_POSITION_CAP,
    sr.BLOCK_REENTRY_GAP_THROUGH, sr.BLOCK_TRADING_PAUSED,
    sr.SETUP_STOP_TOO_WIDE, sr.SETUP_ZERO_RANGE, sr.SETUP_SIZE_TOO_SMALL,
    sr.SETUP_PRICE_EXCEEDS_CAP, sr.SETUP_ACCOUNT_FETCH_FAILED,
    sr.SETUP_FADED_FROM_ORB, sr.SETUP_CHASE_CAP_EXCEEDED, sr.SETUP_GAP_BELOW_FLOOR,
    sr.INFRA_NO_BAR, sr.INFRA_SUBSCRIBE_TIMEOUT, sr.INFRA_SUBSCRIBE_FAILED,
    sr.INFRA_ORDER_SUBMIT_FAILED, sr.INFRA_HALT_STATE_UNREADABLE,
    sr.WINDOW_OUT_OF_ORB, sr.WINDOW_DUPLICATE, sr.WINDOW_PROPOSAL_EXPIRED,
    sr.BROKER_ENTRY_CANCELLED, sr.BROKER_ENTRY_REJECTED, sr.BROKER_ENTRY_EXPIRED,
]

_SCAN_FILTER_VOCAB = [
    sr.FILTER_ADV_NO_DATA, sr.FILTER_ADV_TOO_LOW, sr.FILTER_ATR_TOO_HIGH,
    sr.FILTER_MCAP_TOO_SMALL, sr.FILTER_PM_RVOL_TOO_LOW,
    sr.FILTER_SESSION_RVOL_TOO_LOW, sr.FILTER_UNIVERSE_PREV_CLOSE_TOO_LOW,
    sr.FILTER_UNIVERSE_PREV_DAY_ILLIQUID,
]

# Free-form legacy scan_filter strings (predate the bounded-vocabulary
# constants above; still live in older scan_log rows) parsed by substring,
# not prefix — one representative string per branch in BOTH categorizers.
_SCAN_FILTER_FREEFORM_VOCAB = [
    "EP cooldown — alerted within last 60 days",
    "M&A target — deal-pinned, no organic momentum",
    "buyout pending — structural, not a real EP",
    "merger arb spread, not a momentum name",
    "already scored today — duplicate scan tick",
    "duplicate ticker this session",
    "outside top-20 gap rank for today",
    "top-20 gap cap exceeded",
    "score 38 < 50 (routine catalyst)",
    "score 55 < bar 65 (moderate catalyst)",
    "pm_rvol 1.2x below the pre-market floor",
    "pre-market rvol too light",
    "pre-mkt volume thin vs ADV",
    "session_rvol 1.4x below the 2.0x floor",
    "session rvol weak post-open",
    "catalyst downgrade — analyst cut",
    "catalyst routine — no real news",
    "extension gate — already extended 25% off base",
    "already extended past the entry window",
]

# Known, PRE-EXISTING divergences between the SQL CASE and the Python
# categorizer — unrelated to #570, discovered while building this test. The
# SQL session_rvol_low/pm_rvol_low arms match additional legacy substrings
# that _categorize_skip_reason does not (see this file's module docstring
# for why resolving either direction is out of scope here). Excluded from
# the agreement loop below WITH their reason so a NEW divergence can never
# hide behind this list — remove an entry only when the two sides are
# actually made to agree on it.
_KNOWN_DIVERGENT_REASONS = [
    "pm volume too light vs ADV",          # SQL: pm_rvol_low   / Python: filter_other
    "rel volume 0.4x below the 2.0x floor", # SQL: session_rvol_low / Python: filter_other
    "rel_vol 0.3 well below threshold",     # SQL: session_rvol_low / Python: filter_other
    "low volume today, skipping",           # SQL: session_rvol_low / Python: filter_other
    "projected volume insufficient",        # SQL: session_rvol_low / Python: filter_other
]


def test_known_divergences_are_still_named_and_still_diverge():
    """Guards the allow-list itself: if a future edit accidentally makes one
    of these agree, this test fails so the entry gets DELETED from the
    allow-list (a closed divergence) instead of silently staying excluded
    from the agreement loop below for no reason."""
    for reason in _KNOWN_DIVERGENT_REASONS:
        py_cat = _eval_py_category("scan_filter", reason)
        sql_cat = _eval_sql_category("scan_filter", reason)
        assert py_cat != sql_cat, (
            f"{reason!r} no longer diverges (py={py_cat}, sql={sql_cat}) — "
            "remove it from _KNOWN_DIVERGENT_REASONS, it's not a documented "
            "exception anymore, it's just agreement."
        )


@pytest.mark.parametrize("reason", _HIGH_UNENTERED_VOCAB)
def test_high_unentered_vocabulary_agrees(reason):
    detail = f"{reason}: representative detail text with $1.23 and 4,567"
    py_cat = _eval_py_category("high_unentered", detail)
    sql_cat = _eval_sql_category("high_unentered", detail)
    assert py_cat == sql_cat, f"{detail!r} -> python={py_cat!r} sql={sql_cat!r}"


@pytest.mark.parametrize("reason", _SCAN_FILTER_VOCAB)
def test_scan_filter_bounded_vocabulary_agrees(reason):
    detail = f"{reason}: representative detail text with $1.23 and 4,567"
    py_cat = _eval_py_category("scan_filter", detail)
    sql_cat = _eval_sql_category("scan_filter", detail)
    assert py_cat == sql_cat, f"{detail!r} -> python={py_cat!r} sql={sql_cat!r}"


@pytest.mark.parametrize("reason", _SCAN_FILTER_FREEFORM_VOCAB)
def test_scan_filter_freeform_vocabulary_agrees(reason):
    py_cat = _eval_py_category("scan_filter", reason)
    sql_cat = _eval_sql_category("scan_filter", reason)
    assert py_cat == sql_cat, f"{reason!r} -> python={py_cat!r} sql={sql_cat!r}"


def test_full_vocabulary_has_no_undocumented_disagreement():
    """The umbrella assertion the #570 follow-up card asked for: 'the two
    categorizers agree across the full reason vocabulary.' Walks every
    vocabulary list above (bounded + free-form + known-divergent) and
    requires agreement everywhere EXCEPT the named, reasoned exceptions —
    any other disagreement fails here even if a more specific test above
    doesn't happen to cover it."""
    disagreements = []
    for source, vocab in (("high_unentered", _HIGH_UNENTERED_VOCAB),
                           ("scan_filter", _SCAN_FILTER_VOCAB)):
        for prefix in vocab:
            reason = f"{prefix}: detail"
            py_cat = _eval_py_category(source, reason)
            sql_cat = _eval_sql_category(source, reason)
            if py_cat != sql_cat:
                disagreements.append((source, reason, py_cat, sql_cat))
    for reason in _SCAN_FILTER_FREEFORM_VOCAB:
        py_cat = _eval_py_category("scan_filter", reason)
        sql_cat = _eval_sql_category("scan_filter", reason)
        if py_cat != sql_cat:
            disagreements.append(("scan_filter", reason, py_cat, sql_cat))
    assert not disagreements, (
        f"undocumented categorizer disagreement(s): {disagreements} — "
        "either fix the mismatch or add it to _KNOWN_DIVERGENT_REASONS with a reason"
    )


# ── 4. Mutation-proof: the new SQL clause is actually exercised ────────────

_D1_WHEN_CLAUSE_RE = re.compile(
    r"WHEN skip_reason ILIKE 'filter:universe_prev_close_too_low%'"
    r".*?THEN 'd1_universe_floor'\s*",
    re.DOTALL,
)


def test_mutation_proof_removing_the_d1_when_clause_flips_the_result():
    """Proves the sqlite harness in this file actually exercises the WHEN
    clause added by this fix, not just returning 'd1_universe_floor' by
    some unrelated accident (e.g. a fallthrough that happens to match)."""
    stripped_sql, n = _D1_WHEN_CLAUSE_RE.subn("", missed_outcomes._SKIP_CATEGORY_CASE_SQL)
    assert n == 1, "expected to find and strip exactly one d1_universe_floor WHEN clause"

    reason = f"{sr.FILTER_UNIVERSE_PREV_CLOSE_TOO_LOW}: prior close $0.68 < $5.00 floor"
    sql = stripped_sql.replace("ILIKE", "LIKE")
    query = f"SELECT ({sql}) FROM (SELECT ? AS source, ? AS skip_reason)"
    conn = sqlite3.connect(":memory:")
    try:
        without_clause = conn.execute(query, ("scan_filter", reason)).fetchone()[0]
    finally:
        conn.close()

    assert without_clause != "d1_universe_floor"
    assert _eval_sql_category("scan_filter", reason) == "d1_universe_floor"
