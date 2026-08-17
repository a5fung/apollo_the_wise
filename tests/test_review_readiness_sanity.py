"""#517 (2026-08-17) — tighten what the data-gated review registry surfaces.

Two real, MEASURED failure classes drove this:
  (1) Already-answered reviews kept re-surfacing because nothing marked them answered
      (`consolidation_anticipate_signflip_watch`, `consolidation_unification_review`,
      `theme_engine_narrative_blindness` — all fixed in the registry before this file existed;
      the schema (status=done/deferred + closed_on/outcome) already does the job. What was
      MISSING was a way to record "ran, but could not be answered" without pretending it's
      either untouched (pending, no note) or decided (done) — `last_run_inconclusive_on` /
      `last_run_note`.
  (2) READY-but-unanswerable predicates: `exposure_family_cap_promotion` (a date check dressed
      as SQL — threshold=1, satisfiable by the calendar alone) and `stop_too_wide_outcome_cohort`
      (counted 9M Day 2's `setup:stop_too_wide` rejections into a MAGNA53-only question because
      the predicate never filtered `signal_type`). Both are fixed in the registry now; this file
      pins the DETECTORS that would catch the next one before a full review runs on the wrong
      cohort.

Behavioural coverage required by #517:
  - an answered entry stops surfacing (regression pin — status=done already does this)
  - an unanswered one still does (regression pin)
  - a ran-but-inconclusive entry surfaces differently from a never-run one (NEW)
  - a date-fire threshold renders differently from a real evidence gate (NEW)
  - a predicate with no discriminating filter on a table that has one is flagged (NEW)
  - one that correctly filters is NOT flagged (NEW)
"""
import asyncio

import agents.market_intelligence.data_gated_reviews as dgr
import agents.market_intelligence.system_review as sr

T = None  # today is irrelevant to these entries — no earliest_review_date gate


# ── static detectors (pure, no DB) ──────────────────────────────────────────────────────────

def test_no_from_clause_is_flagged_date_fire():
    """exposure_family_cap_promotion's actual shape (#517 case 4) — a date check written as
    SQL, satisfiable purely by the calendar, never reading a table."""
    sql = "SELECT CASE WHEN CURRENT_DATE >= DATE '2026-07-27' THEN 1 ELSE 0 END"
    assert dgr.is_date_fire_predicate(sql) is True


def test_predicate_less_null_is_NOT_date_fire():
    """`predicate_sql: null` is the documented, HONEST way to say a review is date-only —
    it never claimed to read data. Only a predicate dressed up as SQL that secretly can't read
    data should be flagged; the honest case must not get the same warning."""
    assert dgr.is_date_fire_predicate(None) is False


def test_a_real_table_read_is_NOT_date_fire():
    sql = "SELECT COUNT(*) FROM mi_live_trades WHERE signal_type = 'magna53'"
    assert dgr.is_date_fire_predicate(sql) is False


def test_unfiltered_discriminating_column_is_flagged():
    """stop_too_wide_outcome_cohort's original bug (#517 case 5): mi_live_trades has
    `signal_type` and the predicate never filtered on it, so MAGNA53's and 9M Day 2's rejections
    both counted toward one MAGNA53 question."""
    sql = "SELECT COUNT(*) FROM mi_live_trades WHERE skip_reason LIKE 'setup:stop_too_wide%'"
    mismatch = dgr.find_population_mismatch(sql)
    assert "mi_live_trades.signal_type" in mismatch
    assert "mi_live_trades.account_mode" in mismatch


def test_filtered_discriminating_column_is_NOT_flagged():
    """The corrected predicate (signal_type filtered) must not re-flag on that column."""
    sql = ("SELECT COUNT(*) FROM mi_live_trades WHERE skip_reason LIKE 'setup:stop_too_wide%' "
           "AND signal_type = 'magna53'")
    mismatch = dgr.find_population_mismatch(sql)
    assert "mi_live_trades.signal_type" not in mismatch
    # account_mode is still unfiltered — the rule flags per-column, not per-table
    assert "mi_live_trades.account_mode" in mismatch


def test_a_table_with_no_discriminating_column_is_never_flagged():
    sql = "SELECT COUNT(*) FROM mi_audit_log WHERE event_type = 'entry_order_rejected'"
    assert dgr.find_population_mismatch(sql) == []


def test_count_distinct_is_exempted():
    """Verified against 3 real entries 2026-08-17 (drawdown_breaker_promotion,
    live_cutover_decision, rt_admission_recut_post_2r_exits): COUNT(DISTINCT <date>) already
    collapses across whatever category would otherwise fan the count out, so an unfiltered
    signal_type/account_mode there is not a real mismatch."""
    sql = "SELECT COUNT(DISTINCT alert_date) FROM mi_live_trades WHERE account_mode = 'live'"
    assert dgr.find_population_mismatch(sql) == []


def test_breakdown_sql_matches_the_common_shape():
    sql = "SELECT COUNT(*) FROM mi_live_trades WHERE signal_type = 'magna53'"
    out = dgr.build_population_breakdown_sql(sql, "account_mode")
    assert out is not None
    assert "SELECT account_mode, COUNT(*) AS n FROM mi_live_trades" in out
    assert "GROUP BY account_mode" in out


def test_breakdown_sql_survives_leading_comments_and_trailing_semicolon_comment():
    """The real stop_too_wide_outcome_cohort predicate: multi-line leading `--` comments before
    the SELECT, and a trailing `-- ...` comment after the closing `;`. A naive `^SELECT` match
    fails on this exact text — this is the worked example the rewrite must handle."""
    sql = (
        "-- Count distinct mi_live_trades rows with skip_reason starting\n"
        "-- `setup:stop_too_wide`.\n"
        "SELECT COUNT(*) FROM mi_live_trades\n"
        "WHERE skip_reason LIKE 'setup:stop_too_wide%'\n"
        "  AND signal_type = 'magna53';\n"
        "  -- 25-day lag = 20d forward outcome settled + buffer\n"
    )
    out = dgr.build_population_breakdown_sql(sql, "account_mode")
    assert out is not None
    assert "GROUP BY account_mode" in out
    assert "-- " not in out                 # comments must not leak into the rewritten query


def test_breakdown_sql_falls_back_gracefully_on_a_non_count_star_shape():
    """CASE-wrapped and LEAST()-wrapped predicates (pivot_stop_shadow_review,
    exit_tune_cohort_review) are real registry shapes that a naive rewrite would mangle into
    broken SQL. Best-effort means None here, not a guess."""
    sql = ("SELECT CASE WHEN to_regclass('mi_pivot_stop_shadow') IS NULL THEN 0 "
           "ELSE (SELECT COUNT(*) FROM mi_pivot_stop_shadow WHERE NOT abstained) END")
    assert dgr.build_population_breakdown_sql(sql, "account_mode") is None


# ── check_pending_reviews wiring: the payload must carry what it detects ──────────────────────

def _entry(**kw):
    base = {
        "review_id": "x", "title": "T", "status": "pending",
        "predicate_sql": "SELECT COUNT(*) FROM mi_live_trades WHERE status='closed'",
        "threshold": 0, "action_when_ready": "Act.",
    }
    base.update(kw)
    return base


def _run(monkeypatch, entries, breakdown_rows=None):
    monkeypatch.setattr(dgr, "_load_registry", lambda: entries)

    async def fake_eval(sql):
        return 999  # always "ready" — threshold is 0 in _entry()

    async def fake_breakdown(sql):
        return breakdown_rows or []

    monkeypatch.setattr(dgr, "_evaluate_predicate", fake_eval)
    monkeypatch.setattr(dgr, "_evaluate_breakdown", fake_breakdown)
    return asyncio.run(dgr.check_pending_reviews())


def test_an_answered_entry_stops_surfacing(monkeypatch):
    """Regression pin, not new behaviour — status=done has always been skipped. Included
    because #517's whole premise is that this half of the schema already works; the NEW
    surface (last_run_inconclusive_on) must not accidentally break it."""
    res = _run(monkeypatch, [_entry(status="done", closed_on="2026-08-09",
                                     outcome="ruled — no action")])
    assert res["ready"] == []
    assert res["pending_summary"] == []


def test_an_unanswered_entry_still_surfaces(monkeypatch):
    """Regression pin — status=pending with predicate met must still reach `ready`."""
    res = _run(monkeypatch, [_entry(status="pending")])
    assert [r["review_id"] for r in res["ready"]] == ["x"]


def test_a_ran_but_inconclusive_entry_is_flagged_in_the_payload(monkeypatch):
    res = _run(monkeypatch, [_entry(
        status="pending",
        last_run_inconclusive_on="2026-08-17",
        last_run_note="cohort too thin after the predicate was corrected",
    )])
    r = res["ready"][0]
    assert r["last_run_inconclusive_on"] == "2026-08-17"
    assert "too thin" in r["last_run_note"]


def test_a_never_run_entry_carries_no_inconclusive_marker(monkeypatch):
    res = _run(monkeypatch, [_entry(status="pending")])
    r = res["ready"][0]
    assert r["last_run_inconclusive_on"] is None


def test_date_fire_predicate_is_flagged_in_the_payload(monkeypatch):
    res = _run(monkeypatch, [_entry(
        predicate_sql="SELECT CASE WHEN CURRENT_DATE >= DATE '2026-01-01' THEN 1 ELSE 0 END")])
    assert res["ready"][0]["evidence_flags"]["date_fire"] is True


def test_real_evidence_predicate_is_not_flagged_date_fire(monkeypatch):
    res = _run(monkeypatch, [_entry()])
    assert res["ready"][0]["evidence_flags"]["date_fire"] is False


def test_population_mismatch_surfaces_with_a_breakdown(monkeypatch):
    res = _run(
        monkeypatch,
        [_entry(predicate_sql="SELECT COUNT(*) FROM mi_live_trades WHERE status='closed'")],
        breakdown_rows=[("magna53", 9), ("9m_day2", 8)],
    )
    r = res["ready"][0]
    assert "mi_live_trades.signal_type" in r["evidence_flags"]["population_mismatch"]
    assert r["population_breakdown"]["mi_live_trades.signal_type"] == [("magna53", 9), ("9m_day2", 8)]


def test_a_correctly_filtered_predicate_carries_no_breakdown(monkeypatch):
    res = _run(monkeypatch, [_entry(
        predicate_sql="SELECT COUNT(*) FROM mi_live_trades WHERE signal_type='magna53' "
                      "AND account_mode='live'")])
    r = res["ready"][0]
    assert r["evidence_flags"]["population_mismatch"] == []
    assert "population_breakdown" not in r


# ── renderer: the three surfaces must look visibly different ──────────────────────────────────

def _ready_row(**kw):
    row = {"review_id": "x", "title": "Some review", "kind": "accrual",
           "current_count": 10, "threshold": 5, "earliest_review_date": "2026-01-01",
           "action_when_ready": "Act.",
           "evidence_flags": {"date_fire": False, "population_mismatch": []}}
    row.update(kw)
    return row


def test_date_fire_renders_differently_from_a_real_ripe_tag(monkeypatch):
    monkeypatch.setattr("agents.market_intelligence.collector.et_today",
                         lambda: __import__("datetime").date(2026, 8, 17))
    out = sr._format_pending_reviews_section({"ready": [
        _ready_row(evidence_flags={"date_fire": True, "population_mismatch": []})]})
    assert "date-only" in out
    assert "ripe" not in out


def test_a_real_evidence_gate_still_shows_ripe(monkeypatch):
    from datetime import date as _d
    monkeypatch.setattr("agents.market_intelligence.collector.et_today", lambda: _d(2026, 8, 17))
    out = sr._format_pending_reviews_section({"ready": [_ready_row(
        earliest_review_date="2026-01-01")]})
    assert "ripe" in out
    assert "date-only" not in out


def test_ran_but_inconclusive_looks_different_from_never_run(monkeypatch):
    from datetime import date as _d
    monkeypatch.setattr("agents.market_intelligence.collector.et_today", lambda: _d(2026, 8, 17))
    fresh = sr._format_pending_reviews_section({"ready": [_ready_row(rid_marker="fresh")]})
    inconclusive = sr._format_pending_reviews_section({"ready": [_ready_row(
        last_run_inconclusive_on="2026-08-10")]})
    assert "already ran" not in fresh
    assert "already ran 2026-08-10" in inconclusive


def test_population_mismatch_renders_with_its_breakdown(monkeypatch):
    from datetime import date as _d
    monkeypatch.setattr("agents.market_intelligence.collector.et_today", lambda: _d(2026, 8, 17))
    out = sr._format_pending_reviews_section({"ready": [_ready_row(
        evidence_flags={"date_fire": False, "population_mismatch": ["mi_live_trades.signal_type"]},
        population_breakdown={"mi_live_trades.signal_type": [("magna53", 9), ("9m_day2", 8)]},
    )]})
    assert "pop-check" in out
    assert "mi_live_trades.signal_type" in out
    assert "magna53=9" in out and "9m_day2=8" in out


def test_no_population_mismatch_means_no_pop_check_line(monkeypatch):
    from datetime import date as _d
    monkeypatch.setattr("agents.market_intelligence.collector.et_today", lambda: _d(2026, 8, 17))
    out = sr._format_pending_reviews_section({"ready": [_ready_row()]})
    assert "pop-check" not in out
