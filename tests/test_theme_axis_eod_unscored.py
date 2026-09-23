"""Theme-correctness programme Step 4 (THE INSTRUMENT, 2026-09-07) — the EOD-unscored
NULL-CONTROL population writer for `mi_theme_axis_shadow`.

Covers: the HIGH-row-wins conflict case (a name that was score_bar at 9:35 and HIGH at
9:50 must keep its HIGH row); the as-of anchor excluding the same-day theme row (the
18:03 job runs AFTER the 17:07 theme save, so trade_date's own mi_themes row already
exists and must be excluded); attribution columns tagged not-computable (the false-zero
guard); the SPY-adjusted co-movement opt-in; the population's stage-set derivation; and
the historical backfill runner's era split.

SHADOW ONLY — none of this touches the live grade / judge output / trade state.
"""
from __future__ import annotations

import asyncio
from datetime import date

from unittest.mock import AsyncMock

from tests.conftest import make_mock_pool


def _run(coro):
    return asyncio.run(coro)


# ─── db.UNSCORED_THEME_AXIS_REJECT_STAGES ──────────────────────────────────────────────

def test_unscored_reject_stages_excludes_pre_gap_floor_and_duplicate():
    """The population is derived from ep_decision_vector.GATE_VECTOR minus the three
    stages that must NOT appear: 'universe_floor'/'gap_floor' (BEFORE the gap floor — this
    population is explicitly PAST it) and 'duplicate' (means "already has a real
    mi_ep_alerts row today" — that ticker's true state lives on the live-scan row).

    MUTATION TARGET: including any of the three excluded stages, or dropping a real one,
    silently changes what "past the gap floor" means without a single visible symptom."""
    from agents.market_intelligence.db import UNSCORED_THEME_AXIS_REJECT_STAGES
    assert set(UNSCORED_THEME_AXIS_REJECT_STAGES) == {
        "score_bar", "shortlist_cap", "rvol_gate", "cooldown",
        "extension", "quality_filter", "post_grade_filter",
    }
    assert "universe_floor" not in UNSCORED_THEME_AXIS_REJECT_STAGES
    assert "gap_floor" not in UNSCORED_THEME_AXIS_REJECT_STAGES
    assert "duplicate" not in UNSCORED_THEME_AXIS_REJECT_STAGES


def test_unscored_reject_stages_derived_from_gate_vector_not_hand_copied():
    """The stage set must be DERIVED from the GATE_VECTOR registry, not a hand-maintained
    literal list — so a future gate addition/removal is reflected automatically instead of
    silently rotting this population's definition (the exact class of drift #605 exists to
    prevent for the scoring inputs; this is the same discipline for the population read)."""
    import inspect
    from agents.market_intelligence import db as db_module
    src = inspect.getsource(db_module)
    assert "set(GATE_VECTOR)" in src


# ─── db.get_unscored_theme_axis_population ─────────────────────────────────────────────

def test_population_query_dedupes_to_last_state_per_ticker_per_day():
    """The population SELECT must collapse to the LAST scan-log state per (scan_date,
    ticker) — the canonical DISTINCT ON ... ORDER BY ... scan_time_et DESC NULLS LAST,
    id DESC collapse used everywhere else mi_ep_scan_log is read (get_ep_scanned_day).
    This is WHY a ticker that was score_bar at 9:35 and alerted HIGH at 9:50 never
    appears: its last row that day has reject_stage NULL, which the stage filter below
    then excludes.

    MUTATION TARGET: dropping DISTINCT ON, or ordering by scan_time_et ASC (oldest wins)
    instead of DESC, would surface the STALE early-morning state instead of the final one
    — exactly the HIGH-row-wins property this population must hold."""
    import inspect
    from agents.market_intelligence.db import get_unscored_theme_axis_population
    src = inspect.getsource(get_unscored_theme_axis_population)
    assert "SELECT DISTINCT ON (scan_date, ticker)" in src
    assert "ORDER BY scan_date, ticker, scan_time_et DESC NULLS LAST, id DESC" in src
    assert "WHERE reject_stage = ANY($3)" in src


def test_population_query_passes_the_derived_stage_list(monkeypatch):
    """The query must be parameterized with UNSCORED_THEME_AXIS_REJECT_STAGES itself (not
    a re-typed literal that could drift from it)."""
    from agents.market_intelligence.db import (
        UNSCORED_THEME_AXIS_REJECT_STAGES, get_unscored_theme_axis_population,
    )
    pool, conn = make_mock_pool()
    captured = {}

    async def _fake_fetch(sql, *params):
        captured["params"] = params
        return []
    conn.fetch = _fake_fetch

    _run(get_unscored_theme_axis_population(conn, date(2026, 6, 1)))
    assert captured["params"][0] == date(2026, 6, 1)
    assert captured["params"][1] is None  # until_date defaults to None (single-day case)
    assert set(captured["params"][2]) == set(UNSCORED_THEME_AXIS_REJECT_STAGES)


def test_population_query_single_day_call_passes_same_date_twice():
    """The EOD writer calls get_unscored_theme_axis_population(conn, trade_date,
    trade_date) — since_date == until_date collapses the range to one day."""
    from agents.market_intelligence.db import get_unscored_theme_axis_population
    pool, conn = make_mock_pool()
    captured = {}

    async def _fake_fetch(sql, *params):
        captured["params"] = params
        return []
    conn.fetch = _fake_fetch

    d = date(2026, 6, 1)
    _run(get_unscored_theme_axis_population(conn, d, d))
    assert captured["params"][0] == d and captured["params"][1] == d


# ─── The write side: db.EOD_UNSCORED_THEME_AXIS_INSERT_SQL / write_unscored_theme_axis_row ──

def test_insert_sql_has_on_conflict_do_nothing():
    """The second, belt-and-suspenders line of defense for HIGH-row-wins: even if the
    population SELECT ever regressed and returned an already-alerted ticker, the INSERT
    itself must refuse to clobber an existing (ticker, alert_date) row.

    MUTATION TARGET: swapping DO NOTHING for DO UPDATE would let an eod_unscored write
    silently overwrite a real live_scan HIGH row's grade/theme columns."""
    from agents.market_intelligence.db import EOD_UNSCORED_THEME_AXIS_INSERT_SQL as sql
    assert "ON CONFLICT (ticker, alert_date) DO NOTHING" in sql
    assert "'eod_unscored'" in sql
    assert "FALSE" in sql  # attribution_computable literal


def test_insert_sql_omits_attribution_columns_relies_on_schema_defaults():
    """structural_attribution_score/name_attribution_score/matched_terms/matched_names/
    *_attributable must NOT appear in this INSERT's column list — there is no
    grounded_text for an unscored candidate, so the schema's own defaults (0/FALSE/'{}')
    apply, and attribution_computable=FALSE is the marker a reader must check before
    treating those defaults as real measured zeros.

    MUTATION TARGET: adding an explicit `structural_attribution_score = 0` (or similar)
    to this INSERT would look harmless but removes the distinction this column exists
    to preserve if attribution_computable were ever dropped from the column list instead."""
    from agents.market_intelligence.db import EOD_UNSCORED_THEME_AXIS_INSERT_SQL as sql
    cols_block = sql[sql.index("(") + 1: sql.index(") VALUES")]
    for forbidden in (
        "structural_attribution_score", "structural_attributable", "matched_terms",
        "name_attribution_score", "name_attributable", "matched_names", "grade",
    ):
        assert forbidden not in cols_block, f"{forbidden} must not be written by this INSERT"
    assert "attribution_computable" in cols_block


def test_write_helper_returns_the_actual_insert_count_conflict_case():
    """THE explicit conflict test (task requirement): a name that was score_bar at 9:35
    and HIGH at 9:50 must keep its HIGH row. Simulated at the DB-return level exactly like
    write_theme_axis_shadow_bounded_backfill's own conflict test — 'INSERT 0 0' means the
    ON CONFLICT DO NOTHING guard fired (a live_scan row already occupies that key) and the
    caller must be able to tell it was NOT written, not silently assume success.

    MUTATION TARGET: hardcoding a return of 1 regardless of the INSERT status string
    flips this — a guard-blocked no-op must not be reported as written."""
    from agents.market_intelligence.db import write_unscored_theme_axis_row
    pool, conn = make_mock_pool()

    conn.execute = AsyncMock(return_value="INSERT 0 1")
    n = _run(write_unscored_theme_axis_row(
        conn, "TICK", date(2026, 6, 1), None, None, None, True,
        None, None, None, None, None, None, "score_bar", 42.0,
    ))
    assert n == 1

    conn.execute = AsyncMock(return_value="INSERT 0 0")
    n2 = _run(write_unscored_theme_axis_row(
        conn, "TICK", date(2026, 6, 1), None, None, None, True,
        None, None, None, None, None, None, "score_bar", 42.0,
    ))
    assert n2 == 0, "a conflict (the HIGH row already there) must report 0, not 1"


def test_orchestrator_does_not_inflate_written_count_on_conflict(monkeypatch):
    """End-to-end: log_unscored_theme_axis_for_date must report `written` truthfully even
    when the writer reports a guard-blocked no-op (the HIGH-row-wins scenario) — mirrors
    test_backfill_orchestrator_sums_writer_returned_count_not_a_blind_increment for the
    #486 backfill."""
    from agents.market_intelligence import theme_axis_shadow as tas

    async def _fake_population(_conn, since_date, until_date=None):
        return [{"scan_date": date(2026, 6, 1), "ticker": "TICK",
                  "reject_stage": "score_bar", "ep_score": 39.0}]
    monkeypatch.setattr(tas, "get_unscored_theme_axis_population", _fake_population)

    async def _fake_compute(_conn, ticker, trade_date):
        return {
            "theme_name": None, "theme_stage": None, "theme_score": None,
            "themeless_flag": True, "theme_name_7d": None, "theme_stage_7d": None,
            "bounded_matches_unbounded": True, "cohort_move": None, "ticker_move": None,
            "co_moving": None,
        }
    monkeypatch.setattr(tas, "compute_unscored_theme_axis_row", _fake_compute)

    async def _fake_write(*args, **kwargs):
        return 0  # a live_scan row already occupies this key — conflict, not written
    monkeypatch.setattr(tas, "write_unscored_theme_axis_row", _fake_write)
    monkeypatch.setattr(tas, "log_audit_event", AsyncMock())

    pool, conn = make_mock_pool()
    result = _run(tas.log_unscored_theme_axis_for_date(conn, date(2026, 6, 1)))
    assert result["candidates"] == 1
    assert result["written"] == 0, "a conflict-blocked write must not count as written"
    assert result["themeless"] == 1


# ─── The as-of anchor: same-day theme row exclusion ────────────────────────────────────

def test_compute_row_anchors_both_reads_at_trade_date_minus_one(monkeypatch):
    """The 18:03 EOD job runs AFTER the 17:07 theme save has already landed trade_date's
    OWN mi_themes row — both theme reads (unbounded AND 7d-bounded) must be anchored at
    trade_date-1, exactly bounded_backfill_anchor(trade_date, same_day_write=True), or
    every candidate would trivially match a theme born from today's own move.

    MUTATION TARGET: anchoring at bare `trade_date` (the live shadow writer's own anchor,
    which is safe ONLY because it runs before the theme save) would silently include
    today's own snapshot here."""
    from agents.market_intelligence.theme_axis_shadow import compute_unscored_theme_axis_row
    calls = []

    async def _fake_heat(_conn, ticker, alert_date, recency_days=None):
        calls.append((alert_date, recency_days))
        return None
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_theme_heat_asof", _fake_heat)

    pool, conn = make_mock_pool()
    trade_date = date(2026, 9, 4)
    _run(compute_unscored_theme_axis_row(conn, "TICK", trade_date))

    expected_anchor = date(2026, 9, 3)  # trade_date - 1
    assert calls[0] == (expected_anchor, None), "unbounded read must anchor at trade_date-1"
    assert calls[1] == (expected_anchor, 6), "bounded read must anchor at trade_date-1, floor 6"


def test_compute_row_themeless_when_unbounded_heat_is_none(monkeypatch):
    from agents.market_intelligence.theme_axis_shadow import compute_unscored_theme_axis_row

    async def _no_heat(_conn, ticker, alert_date, recency_days=None):
        return None
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_theme_heat_asof", _no_heat)

    pool, conn = make_mock_pool()
    fields = _run(compute_unscored_theme_axis_row(conn, "LONE", date(2026, 9, 4)))
    assert fields["themeless_flag"] is True
    assert fields["theme_name"] is None
    assert fields["co_moving"] is None, "no cohort to co-move with when themeless"


def test_compute_row_co_movement_only_attempted_when_bounded_cohort_exists(monkeypatch):
    """Co-movement is computed against the BOUNDED (7d) cohort specifically — if the
    bounded read finds nothing (heat_7d is None) even though the unbounded read found a
    stale theme, there is no bounded cohort to co-move against."""
    from agents.market_intelligence.theme_axis_shadow import compute_unscored_theme_axis_row

    _stale = {"name": "Old", "stage": "Mainstream", "score": 10.0,
              "tickers": ["TICK"], "description": ""}

    async def _fake_heat(_conn, ticker, alert_date, recency_days=None):
        return None if recency_days else _stale
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_theme_heat_asof", _fake_heat)

    cohort_called = []

    async def _fake_cohort(*args, **kwargs):
        cohort_called.append((args, kwargs))
        return None, None, None
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow._cohort_co_movement", _fake_cohort)

    pool, conn = make_mock_pool()
    fields = _run(compute_unscored_theme_axis_row(conn, "TICK", date(2026, 9, 4)))
    assert fields["theme_name"] == "Old"           # unbounded found something
    assert fields["theme_name_7d"] is None          # bounded found nothing
    assert not cohort_called, "no bounded cohort -> co-movement must not be attempted"


def test_compute_row_requests_spy_adjusted_co_movement(monkeypatch):
    """Co-movement must be requested with spy_adjust=True against the BOUNDED cohort —
    matching coverage_probe's birth-gate copy, not the un-adjusted live shadow writer."""
    from agents.market_intelligence.theme_axis_shadow import compute_unscored_theme_axis_row

    _theme = {"name": "T", "stage": "Accelerating", "score": 50.0,
              "tickers": ["TICK", "PEER"], "description": ""}

    async def _fake_heat(_conn, ticker, alert_date, recency_days=None):
        return _theme
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_theme_heat_asof", _fake_heat)

    captured = {}

    async def _fake_cohort(_conn, ticker, alert_date, cohort_tickers, spy_adjust=False):
        captured["cohort_tickers"] = cohort_tickers
        captured["spy_adjust"] = spy_adjust
        return 1.0, 2.0, True
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow._cohort_co_movement", _fake_cohort)

    pool, conn = make_mock_pool()
    fields = _run(compute_unscored_theme_axis_row(conn, "TICK", date(2026, 9, 4)))
    assert captured["spy_adjust"] is True
    assert captured["cohort_tickers"] == ["TICK", "PEER"]  # the BOUNDED cohort
    assert fields["co_moving"] is True


# ─── _cohort_co_movement's spy_adjust opt-in ────────────────────────────────────────────

def test_cohort_co_movement_default_unchanged_no_spy_adjust(monkeypatch):
    """Default (spy_adjust=False) must stay byte-identical to today's behavior — every
    existing caller (compute_step1_signals, refresh_co_movement_for_date, the #367/#369
    backfill scripts) must see no behavior change."""
    from agents.market_intelligence.theme_axis_shadow import _cohort_co_movement

    async def _fake_moves(_conn, _date, tickers):
        assert "SPY" not in tickers, "SPY must not be fetched when spy_adjust=False"
        return {"TICK": 10.0, "PEER": 8.0}
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_daily_moves", _fake_moves)

    pool, conn = make_mock_pool()
    ticker_move, cohort_move, co_moving = _run(
        _cohort_co_movement(conn, "TICK", date(2026, 9, 4), ["TICK", "PEER"]))
    assert ticker_move == 10.0 and cohort_move == 8.0 and co_moving is True


def test_cohort_co_movement_spy_adjust_kills_the_everything_rallies_confound(monkeypatch):
    """spy_adjust=True must fetch SPY alongside the cohort and subtract its move from
    every leg BEFORE computing co-movement. TICK +9%, PEER +8.5% on an SPY +8% day reads
    as trivially co-moving RAW (both up, cohort clears the floor) — the exact confound the
    plan calls out ('makes it trivially true on a broad up day'). Market-adjusted, the
    cohort's real edge over the tape is only +0.5%, which does NOT clear the co-movement
    floor, so the adjusted read correctly says NOT co-moving."""
    from agents.market_intelligence.theme_axis_shadow import _cohort_co_movement, CO_MOVEMENT_FLOOR_PCT

    # get_daily_moves returns whatever rows exist for the requested tickers — SPY is only
    # ever in the result when spy_adjust=True actually asked for it (asserted below).
    _all_moves = {"TICK": 9.0, "PEER": 8.5, "SPY": 8.0}

    async def _fake_moves(_conn, _date, tickers):
        return {t: _all_moves[t] for t in tickers if t in _all_moves}
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_daily_moves", _fake_moves)

    pool, conn = make_mock_pool()
    # RAW (spy_adjust=False): trivially co-moving — the confound.
    raw_ticker, raw_cohort, raw_co_moving = _run(
        _cohort_co_movement(conn, "TICK", date(2026, 9, 4), ["TICK", "PEER"]))
    assert raw_co_moving is True

    # Market-adjusted: the real signal is much smaller than the floor.
    ticker_move, cohort_move, co_moving = _run(
        _cohort_co_movement(conn, "TICK", date(2026, 9, 4), ["TICK", "PEER"], spy_adjust=True))
    assert ticker_move == 1.0    # 9.0 - 8.0
    assert cohort_move == 0.5    # 8.5 - 8.0
    assert abs(cohort_move) < CO_MOVEMENT_FLOOR_PCT
    assert co_moving is False, "market-adjusted, the cohort barely cleared the tape at all"


def test_cohort_co_movement_spy_adjust_missing_spy_degrades_to_raw(monkeypatch):
    """A missing SPY row (spy_move None) must pass RAW moves through unchanged — a
    degraded-but-honest read, mirroring coverage_probe.market_adjust_moves' own contract."""
    from agents.market_intelligence.theme_axis_shadow import _cohort_co_movement

    async def _fake_moves(_conn, _date, tickers):
        return {"TICK": 10.0, "PEER": 8.0}  # no SPY row
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_daily_moves", _fake_moves)

    pool, conn = make_mock_pool()
    ticker_move, cohort_move, co_moving = _run(
        _cohort_co_movement(conn, "TICK", date(2026, 9, 4), ["TICK", "PEER"], spy_adjust=True))
    assert ticker_move == 10.0 and cohort_move == 8.0  # unchanged, no SPY to subtract


# ─── Attribution not-computable guard ──────────────────────────────────────────────────

def test_schema_attribution_computable_defaults_true_preserving_existing_rows():
    """Existing rows (live-captured + the #369 mass backfill, which DID have
    grounded_text) must keep their current meaning: attribution_computable defaults TRUE.
    Only the new eod_unscored writer sets it FALSE. Checked in BOTH the CREATE and the
    ALTER (test_schema_alter_create_parity separately pins the two columns together)."""
    import inspect
    from agents.market_intelligence import db as db_module
    src = inspect.getsource(db_module.initialize_schema)
    assert src.count("attribution_computable BOOLEAN NOT NULL DEFAULT TRUE") == 2


def test_health_read_excludes_eod_unscored_rows():
    """scripts/probes/_367_theme_axis_health_read.py is the one production attribution
    READER over mi_theme_axis_shadow — it must exclude source='eod_unscored' or its
    themed/themeless counts and attribution percentages silently absorb false zeros from
    rows that were never graded."""
    import io
    src = io.open(
        "scripts/probes/_367_theme_axis_health_read.py", encoding="utf-8").read()
    assert "source != 'eod_unscored'" in src


def test_refined_signals_backfill_excludes_eod_unscored_rows():
    """scripts/backfill_theme_axis_refined_signals.py joins mi_ep_alerts (which
    structurally excludes eod_unscored rows, since they were never alerted) — pin the
    explicit belt-and-suspenders filter too, so a future loosened join doesn't silently
    reintroduce them."""
    import io
    src = io.open(
        "scripts/backfill_theme_axis_refined_signals.py", encoding="utf-8").read()
    assert "s.source != 'eod_unscored'" in src


def test_label_cohort_seeder_excludes_eod_unscored_rows():
    """scripts/seed_theme_relevance_cohort.py feeds the operator's #368 labeling queue
    directly (classify_label_stratum enrols themeless_flag=False rows as 'themed'
    regardless of grade) — an eod_unscored row was never alerted/graded at all, so without
    this filter a themed eod_unscored row would silently land in his labeling queue as if
    it were a real judged alert."""
    import io
    src = io.open("scripts/seed_theme_relevance_cohort.py", encoding="utf-8").read()
    assert "s.source != 'eod_unscored'" in src


# ─── Legacy filter_reason -> reject_stage classifier (2026-09-08 unblock) ──────────────
# Every pattern here is a REAL string pulled from prod (verified 2026-09-07) or the exact
# literal ep_detector.py builds for that stage — never invented, per the coordinator's
# "derive the stage, do not guess it" instruction.

def test_legacy_classifier_maps_every_real_prod_pattern():
    """One assertion per pattern actually observed in mi_ep_scan_log (pre-2026-08-31),
    sourced from the exact ep_detector.py string literal for that stage. A currently-dead
    (superseded) wording is included deliberately — the message changed under this same
    check more than once and the classifier must still recognize the old ones."""
    from agents.market_intelligence.theme_axis_shadow import classify_legacy_filter_reason as c

    # shortlist_cap — ep_detector.py:3670/3674
    assert c("outside top-20 gap cap (gap 8.2%)") == "shortlist_cap"
    assert c("outside top-20 shortlist (prescore rank 25, gap 9.1%)") == "shortlist_cap"
    # rvol_gate — CURRENT (ep_detector.py:3781) and three dead legacy wordings found only
    # in the actual pre-08-31 data
    assert c("filter:pm_rvol_too_low: pm_rvol=0.30x (today 100 / baseline 500 n=20) < 2.0x") == "rvol_gate"
    assert c("filter:session_rvol_too_low: session_rvol=0.5x (today 1,000 / baseline 5,000 n=20) < 2.0x") == "rvol_gate"
    assert c("low rel volume 0.1x < 2.0x") == "rvol_gate"
    assert c("low volume rel_vol 0.1x < 2.0x") == "rvol_gate"
    assert c("low volume projected 1.4x < 2.0x (post-open)") == "rvol_gate"
    # cooldown — ep_detector.py:3918
    assert c("EP cooldown — alerted within last 60 days") == "cooldown"
    # extension — ep_detector.py:3934
    assert c("already up 166% in prior 5 days (extended)") == "extension"
    # quality_filter — ep_detector.py:3950 (sub-reason after the colon varies)
    assert c("quality filter: filter:adv_too_low: $ADV $1.2M < $2M floor") == "quality_filter"
    assert c("quality filter: filter:mcap_too_small: mcap $50M < $75M floor") == "quality_filter"
    assert c("quality filter: filter:atr_too_high: ATR 8.5% > 6% cap") == "quality_filter"
    # post_grade_filter — THREE reasons, all ep_detector.py:1785/1809/1846
    assert c("M&A/buyout catalyst — no momentum trade") == "post_grade_filter"
    assert c("routine catalyst, gap 10.3%") == "post_grade_filter"
    assert c("pre-mkt volume 100 < 25,000 shares") == "post_grade_filter"
    # score_bar — pre-#533 legacy form AND post-#533 form, ep_detector.py:5427/5430
    assert c("score 30 < 50 (catalyst=routine)") == "score_bar"
    assert c("score -12 < 50 (catalyst=routine)") == "score_bar"
    assert c("score 60 < bar 65 (catalyst=routine)") == "score_bar"
    # excluded stages (must classify, but are NOT in UNSCORED_THEME_AXIS_REJECT_STAGES)
    assert c("filter:universe_prev_close_too_low: prior close $3.61 < $5.00 floor") == "universe_floor"
    assert c("filter:universe_prev_day_illiquid: prior-day volume 30,063 < 50,000 shares floor") == "universe_floor"
    assert c("already scored earlier today") == "duplicate"


def test_legacy_classifier_returns_none_for_falsy_input():
    from agents.market_intelligence.theme_axis_shadow import classify_legacy_filter_reason as c
    assert c(None) is None
    assert c("") is None


def test_legacy_classifier_unmatched_text_returns_none_too():
    """A truly novel wording returns None, same as falsy input — the CALLER (via
    get_legacy_classification_unmatched) is what distinguishes 'nothing to classify' from
    'classification failed', by checking whether filter_reason was truthy."""
    from agents.market_intelligence.theme_axis_shadow import classify_legacy_filter_reason as c
    assert c("some brand new reason nobody has ever seen") is None


def test_effective_reject_stage_prefers_the_real_column():
    """When #605 already captured reject_stage (>= 2026-08-31), use it verbatim — never
    re-derive from filter_reason even if it would also match (the column is ground truth
    once it exists; the legacy path is a fallback for when it doesn't)."""
    from agents.market_intelligence.theme_axis_shadow import effective_reject_stage
    assert effective_reject_stage("score_bar", "quality filter: filter:adv_too_low") == "score_bar"


def test_effective_reject_stage_falls_back_to_legacy_classification():
    from agents.market_intelligence.theme_axis_shadow import effective_reject_stage
    assert effective_reject_stage(None, "EP cooldown — alerted within last 60 days") == "cooldown"


def test_unmatched_helper_excludes_already_tagged_and_passed_rows():
    """get_legacy_classification_unmatched must report ONLY rows with a real, unmatchable
    filter_reason — never a row #605 already tagged (reject_stage present) and never a
    real alert (filter_reason NULL, nothing to classify)."""
    from agents.market_intelligence.theme_axis_shadow import get_legacy_classification_unmatched
    rows = [
        {"reject_stage": "score_bar", "filter_reason": "score 30 < 50 (catalyst=routine)"},
        {"reject_stage": None, "filter_reason": None},  # a real alert — nothing to classify
        {"reject_stage": None, "filter_reason": "EP cooldown — alerted within last 60 days"},
        {"reject_stage": None, "filter_reason": "a brand new wording nobody mapped yet"},
    ]
    unmatched = get_legacy_classification_unmatched(rows)
    assert len(unmatched) == 1
    assert unmatched[0]["filter_reason"] == "a brand new wording nobody mapped yet"


def test_legacy_classifier_full_prod_population_has_zero_unmatched():
    """Regression pin for the coordinator's exact finding (2026-09-07/08, verified on prod
    directly): classifying the REAL top prod patterns (with real counts, not fabricated)
    leaves nothing unmatched. If a future edit to the pattern list breaks recognition of
    ANY of these real observed strings, this must go red."""
    from agents.market_intelligence.theme_axis_shadow import get_legacy_classification_unmatched
    real_prod_samples = [
        {"reject_stage": None, "filter_reason": "filter:universe_prev_close_too_low: prior close $3.61 < $5.00 floor"},
        {"reject_stage": None, "filter_reason": "already scored earlier today"},
        {"reject_stage": None, "filter_reason": "quality filter: filter:mcap_too_small: mcap $50M < $75M floor"},
        {"reject_stage": None, "filter_reason": "quality filter: filter:adv_too_low: $ADV $1.2M < $2M floor"},
        {"reject_stage": None, "filter_reason": "outside top-20 gap cap (gap 8.2%)"},
        {"reject_stage": None, "filter_reason": "M&A/buyout catalyst — no momentum trade"},
        {"reject_stage": None, "filter_reason": "quality filter: filter:atr_too_high: ATR 8.5% > 6% cap"},
        {"reject_stage": None, "filter_reason": "EP cooldown — alerted within last 60 days"},
        {"reject_stage": None, "filter_reason": "filter:universe_prev_day_illiquid: prior-day volume 30,063 < 50,000 shares floor"},
        {"reject_stage": None, "filter_reason": "filter:pm_rvol_too_low: pm_rvol=0.30x (today 100 / baseline 500 n=20) < 2.0x"},
        {"reject_stage": None, "filter_reason": "filter:session_rvol_too_low: session_rvol=0.5x (today 1,000 / baseline 5,000 n=20) < 2.0x"},
        {"reject_stage": None, "filter_reason": "score 30 < 50 (catalyst=routine)"},
        {"reject_stage": None, "filter_reason": "routine catalyst, gap 10.3%"},
        {"reject_stage": None, "filter_reason": "low volume rel_vol 0.1x < 2.0x"},
        {"reject_stage": None, "filter_reason": "already up 166% in prior 5 days (extended)"},
        {"reject_stage": None, "filter_reason": "low rel volume 0.6x < 2.0x"},
        {"reject_stage": None, "filter_reason": "low volume projected 1.4x < 2.0x (post-open)"},
        {"reject_stage": None, "filter_reason": "pre-mkt volume 100 < 25,000 shares"},
        {"reject_stage": None, "filter_reason": None},  # real alerts
    ]
    assert get_legacy_classification_unmatched(real_prod_samples) == []


# ─── db.get_ep_scan_log_raw_population ─────────────────────────────────────────────────

def test_raw_population_query_dedupes_and_is_unfiltered_on_stage():
    """Unlike get_unscored_theme_axis_population, this accessor must NOT filter on
    reject_stage — the whole point is to hand back every row (including reject_stage IS
    NULL ones) so the caller can classify them via the legacy path."""
    import inspect
    from agents.market_intelligence.db import get_ep_scan_log_raw_population
    src = inspect.getsource(get_ep_scan_log_raw_population)
    assert "SELECT DISTINCT ON (scan_date, ticker)" in src
    assert "ORDER BY scan_date, ticker, scan_time_et DESC NULLS LAST, id DESC" in src
    assert "reject_stage = ANY" not in src
    assert "filter_reason" in src


# ─── Historical backfill runner: build_population + era split ─────────────────────────

def test_build_population_uses_effective_stage_and_filters_to_target_stages():
    from datetime import date as _date
    from scripts.probes.theme_axis_eod_unscored_backfill import build_population
    raw_rows = [
        # already tagged by #605 -> kept, effective stage = the column
        {"scan_date": _date(2026, 9, 1), "ticker": "AAA", "reject_stage": "score_bar",
         "filter_reason": "score 40 < bar 65 (catalyst=routine)", "ep_score": 40.0},
        # legacy-classified into a target stage -> kept
        {"scan_date": _date(2026, 5, 1), "ticker": "BBB", "reject_stage": None,
         "filter_reason": "EP cooldown — alerted within last 60 days", "ep_score": None},
        # legacy-classified into an EXCLUDED stage -> dropped
        {"scan_date": _date(2026, 5, 1), "ticker": "CCC", "reject_stage": None,
         "filter_reason": "already scored earlier today", "ep_score": None},
        # real alert (nothing to classify) -> dropped
        {"scan_date": _date(2026, 5, 1), "ticker": "DDD", "reject_stage": None,
         "filter_reason": None, "ep_score": 80.0},
        # unmatched -> dropped (reported separately, not silently included)
        {"scan_date": _date(2026, 5, 1), "ticker": "EEE", "reject_stage": None,
         "filter_reason": "a brand new wording", "ep_score": None},
    ]
    candidates = build_population(raw_rows)
    tickers = {c["ticker"] for c in candidates}
    assert tickers == {"AAA", "BBB"}
    aaa = next(c for c in candidates if c["ticker"] == "AAA")
    assert aaa["reject_stage"] == "score_bar"
    bbb = next(c for c in candidates if c["ticker"] == "BBB")
    assert bbb["reject_stage"] == "cooldown"


def test_era_split_before_cutline_excludes_cutline_day():
    from datetime import date as _date
    from scripts.probes.theme_axis_eod_unscored_backfill import _ERA_CUTLINE, split_by_era
    rows = [
        {"scan_date": _date(2026, 8, 21), "ticker": "PRE"},
        {"scan_date": _date(2026, 8, 22), "ticker": "ON_CUTLINE"},
        {"scan_date": _date(2026, 8, 23), "ticker": "POST"},
    ]
    before, after = split_by_era(rows)
    assert _ERA_CUTLINE == _date(2026, 8, 22)
    assert [r["ticker"] for r in before] == ["PRE"]
    assert [r["ticker"] for r in after] == ["ON_CUTLINE", "POST"]


def test_era_split_reports_full_split_not_a_single_blended_count():
    """377 (the scored-under-bar figure from one era) must never be reported as 'the
    whole missing population' — the split must partition every row, not drop any."""
    from datetime import date as _date
    from scripts.probes.theme_axis_eod_unscored_backfill import split_by_era
    rows = [{"scan_date": _date(2026, 4, 13 + i), "ticker": f"T{i}"} for i in range(10)]
    before, after = split_by_era(rows)
    assert len(before) + len(after) == len(rows)
