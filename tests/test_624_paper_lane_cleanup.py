"""#624 small-cap PAPER lane — the 2026-10-10 quality pass (reuse / simplification), pinned.

Every change in the pass is behaviour-preserving, so each test here states the OLD value or
behaviour and proves the new code still produces it:
  - the lane's identity constants (stop switch, account, strategy id) have ONE definition (db.py)
    and the same values the two lane modules used to spell out separately;
  - the order step's refusal page follows the funnel's own constant, not a copy of its string;
  - the judge-result / replay / existing-row SQL built from one definition is byte-identical to
    the statements that were written out by hand;
  - the tiered-name read hands back the same ticker -> latest-date map.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import db
from agents.market_intelligence import lowcap_paper_lane as plane
from agents.market_intelligence.broker import entry_pipeline as ep
from agents.market_intelligence.broker import lowcap_paper_entry as lpe
from agents.market_intelligence.broker import skip_reasons
from agents.market_intelligence.strategies import adapters
from tests.conftest import make_mock_pool
from tests.test_624_paper_lane import _wire_order_step


# ── identity constants: one definition, the values both modules used to hard-code ─────────


def test_the_lane_identity_constants_keep_their_values_and_have_one_definition():
    assert db.LOWCAP_PAPER_LANE_TOGGLE == "lowcap_paper_lane"
    assert db.LOWCAP_PAPER_LANE_TOGGLE_ENV == "LOWCAP_PAPER_LANE_ENABLED"
    assert db.LOWCAP_PAPER_LANE_ACCOUNT_MODE == "paper"
    assert db.LOWCAP_PAPER_LANE_STRATEGY_ID == "magna53_smallcap"
    # the grading side and the order side read the SAME objects — a stop switch that can only
    # stop half the lane is the failure this prevents
    assert (lpe.TOGGLE, lpe.TOGGLE_ENV) == (plane.TOGGLE, plane.TOGGLE_ENV) \
        == (db.LOWCAP_PAPER_LANE_TOGGLE, db.LOWCAP_PAPER_LANE_TOGGLE_ENV)
    assert lpe.LANE_ACCOUNT_MODE == plane._LANE_BOOK == db.LOWCAP_PAPER_LANE_ACCOUNT_MODE
    assert lpe.STRATEGY_ID == plane.STRATEGY_ID == db.LOWCAP_PAPER_LANE_STRATEGY_ID


def test_the_registry_adapter_is_keyed_and_bound_by_the_strategy_id_constant():
    fn = adapters._ADAPTERS[db.LOWCAP_PAPER_LANE_STRATEGY_ID]
    assert fn.keywords == {"signal_type": db.LOWCAP_PAPER_LANE_STRATEGY_ID}


def test_the_lane_uses_the_one_none_safe_float_coercion():
    assert plane._f is db._f
    assert plane._f("3.5") == 3.5 and plane._f(None) is None and plane._f("x") is None


# ── the refusal page follows the funnel's constant ────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_funnel_account_mode_refusal_pages_the_lane_and_other_blocks_do_not(monkeypatch):
    w = _wire_order_step(monkeypatch)
    w.submit.return_value = {"ticker": "SMLL", "action": ep.ACTION_BLOCKED,
                             "reason": f"{skip_reasons.BLOCK_ACCOUNT_MODE_MISMATCH}: magna53_smallcap "
                                       f"resolves to 'live'"}
    out = await lpe.process_lowcap_paper_alerts(today=date(2026, 10, 12))
    assert out[0]["action"] == ep.ACTION_BLOCKED
    assert len(w.pages) == 1 and w.pages[0].startswith("📄 PAPER") and "REFUSED" in w.pages[0]

    w = _wire_order_step(monkeypatch)       # a different block is an audit row, never a page
    w.submit.return_value = {"ticker": "SMLL", "action": ep.ACTION_BLOCKED,
                             "reason": skip_reasons.BLOCK_TICKER_OPEN_POSITION}
    await lpe.process_lowcap_paper_alerts(today=date(2026, 10, 12))
    assert w.pages == []


@pytest.mark.asyncio
async def test_the_refusal_page_matches_the_funnels_constant_not_a_copy_of_its_text(monkeypatch):
    """If the funnel's reason were ever reworded, the page must follow it (it reads the imported
    constant). MUTATION: put the literal "block:account_mode_mismatch" back — this goes RED."""
    w = _wire_order_step(monkeypatch)
    monkeypatch.setattr(lpe, "BLOCK_ACCOUNT_MODE_MISMATCH", "block:reworded_mismatch")
    w.submit.return_value = {"ticker": "SMLL", "action": ep.ACTION_BLOCKED,
                             "reason": "block:reworded_mismatch: x"}
    await lpe.process_lowcap_paper_alerts(today=date(2026, 10, 12))
    assert len(w.pages) == 1 and "REFUSED" in w.pages[0]
    assert skip_reasons.BLOCK_ACCOUNT_MODE_MISMATCH == "block:account_mode_mismatch"   # the wire value did not move


# ── SQL built from one definition == the statements that were written out by hand ─────────

# The live statement exactly as it was written out in db.py before it was built from the shared
# column list. Frozen here: a drift in the builder (or a column added to one table only) fails.
_LIVE_JUDGE_SQL_AS_WRITTEN = """
    UPDATE mi_ep_alerts SET
        judge_tier = COALESCE($3, judge_tier),
        judge_direction = COALESCE($4, judge_direction),
        judge_rationale = COALESCE($5, judge_rationale),
        judge_materiality_tier = COALESCE($6, judge_materiality_tier),
        fire_axes = COALESCE($7, fire_axes),
        score_tier = COALESCE($8, score_tier),
        grade_engine_authority = COALESCE($9, grade_engine_authority),
        rubric_version = COALESCE($10, rubric_version),
        judge_grade = COALESCE($11, judge_grade),
        judge_grade_reason = COALESCE($12, judge_grade_reason),
        judge_tier_reason = COALESCE($13, judge_tier_reason)
    WHERE ticker = $1 AND alert_date = $2
"""
_LANE_JUDGE_SQL_AS_WRITTEN = """
    UPDATE mi_lowcap_paper_lane_alerts SET
        judge_tier = COALESCE($3, judge_tier),
        judge_direction = COALESCE($4, judge_direction),
        judge_rationale = COALESCE($5, judge_rationale),
        judge_materiality_tier = COALESCE($6, judge_materiality_tier),
        fire_axes = COALESCE($7, fire_axes),
        score_tier = COALESCE($8, score_tier),
        grade_engine_authority = COALESCE($9, grade_engine_authority),
        rubric_version = COALESCE($10, rubric_version),
        judge_grade = COALESCE($11, judge_grade),
        judge_grade_reason = COALESCE($12, judge_grade_reason),
        judge_tier_reason = COALESCE($13, judge_tier_reason),
        setup_class = COALESCE($14, setup_class),
        updated_at = NOW()
    WHERE ticker = $1 AND alert_date = $2
"""


def test_the_live_judge_statement_is_byte_identical_to_the_hand_written_one():
    """The deploy gate prepares THIS constant and production executes it — it must not move."""
    assert db.EP_ALERT_JUDGE_RESULT_UPDATE_SQL == _LIVE_JUDGE_SQL_AS_WRITTEN


def test_the_lane_judge_statement_is_the_live_one_on_the_lanes_table_plus_two_clauses():
    assert db.LOWCAP_PAPER_LANE_JUDGE_UPDATE_SQL == _LANE_JUDGE_SQL_AS_WRITTEN
    # the lane's statement can only ever name its own table (wall 1: never the live alert row)
    assert "mi_ep_alerts" not in db.LOWCAP_PAPER_LANE_JUDGE_UPDATE_SQL
    # one column list: every judge column the live statement writes, the lane writes too
    live_sets = {ln.split("=")[0].strip() for ln in db.EP_ALERT_JUDGE_RESULT_UPDATE_SQL.splitlines()
                 if "COALESCE" in ln}
    lane_sets = {ln.split("=")[0].strip() for ln in db.LOWCAP_PAPER_LANE_JUDGE_UPDATE_SQL.splitlines()
                 if "COALESCE" in ln or "NOW()" in ln}
    assert lane_sets == live_sets | {"setup_class", "updated_at"}
    assert live_sets == set(db._JUDGE_RESULT_COLS)


def test_a_new_judge_column_reaches_both_tables_by_construction(monkeypatch):
    monkeypatch.setattr(db, "_JUDGE_RESULT_COLS", db._JUDGE_RESULT_COLS + ("judge_new_axis",))
    live = db._judge_result_update_sql("mi_ep_alerts")
    lane = db._judge_result_update_sql("mi_lowcap_paper_lane_alerts")
    assert "judge_new_axis = COALESCE($14, judge_new_axis)" in live and "judge_new_axis" in lane


def test_the_two_replay_tables_share_one_upsert_and_one_existing_read():
    shadow, paper = db.LOWCAP_LANE_REPLAY_UPSERT_SQL, db.LOWCAP_PAPER_LANE_REPLAY_UPSERT_SQL
    assert paper == shadow.replace("mi_lowcap_lane_replays", "mi_lowcap_paper_lane_replays")
    assert shadow.startswith("INSERT INTO mi_lowcap_lane_replays (ticker, session_date, ")
    assert shadow.endswith("WHERE mi_lowcap_lane_replays.outcome = 'open'")
    assert db._LOWCAP_PAPER_LANE_REPLAY_EXISTING_SQL == db._LOWCAP_LANE_REPLAY_EXISTING_SQL.replace(
        "mi_lowcap_lane_replays", "mi_lowcap_paper_lane_replays")
    assert "FROM mi_lowcap_lane_replays" in db._LOWCAP_LANE_REPLAY_EXISTING_SQL


@pytest.mark.asyncio
@pytest.mark.parametrize("reader,table", [
    (db.get_lowcap_lane_replay_existing, "mi_lowcap_lane_replays"),
    (db.get_lowcap_paper_lane_replay_existing, "mi_lowcap_paper_lane_replays"),
])
async def test_each_existing_row_reader_reads_its_own_table_and_keys_by_ticker_and_session(
        monkeypatch, reader, table):
    pool, conn = make_mock_pool()
    seen = []

    async def _fetch(sql, window_start):
        seen.append((sql, window_start))
        return [{"ticker": "AAA", "session_date": date(2026, 10, 9), "outcome": "open"},
                {"ticker": "BBB", "session_date": date(2026, 10, 9), "outcome": "settled"}]
    conn.fetch = _fetch
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    got = await reader("2026-09-01")
    assert got == {("AAA", date(2026, 10, 9)): "open", ("BBB", date(2026, 10, 9)): "settled"}
    (sql, ws), = seen
    assert f"FROM {table}\n" in sql and ws == date(2026, 9, 1)     # ISO string coerced to a date


@pytest.mark.asyncio
async def test_the_tiered_read_returns_each_tickers_latest_alert_date(monkeypatch):
    """The database now takes the per-ticker MAX (the old code shipped every tiered row in the
    cooldown window and reduced in Python). Same answer: ticker -> its latest tiered date."""
    from tests.test_624_paper_lane_review_fixes import _run_window
    today = date(2026, 10, 12)
    stored = [{"ticker": "AAA", "alert_date": date(2026, 9, 1), "score_tier": "HIGH"},
              {"ticker": "AAA", "alert_date": date(2026, 9, 20), "score_tier": "MODERATE"},
              {"ticker": "AAA", "alert_date": date(2026, 9, 10), "score_tier": "HIGH"},
              {"ticker": "BBB", "alert_date": date(2026, 10, 12), "score_tier": "HIGH"},
              {"ticker": "CCC", "alert_date": date(2026, 9, 15), "score_tier": None}]
    pool, conn = make_mock_pool()

    async def _fetch(sql, t, n):
        # evaluate what the statement says: WHERE as written, then GROUP BY ticker / MAX(alert_date)
        assert "GROUP BY ticker" in sql and "MAX(alert_date) AS alert_date" in sql
        best: dict = {}
        for r in _run_window(sql, stored, t, n):
            best[r["ticker"]] = max(best.get(r["ticker"], r["alert_date"]), r["alert_date"])
        return [{"ticker": k, "alert_date": v} for k, v in best.items()]
    conn.fetch = _fetch
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    got = await db.get_lowcap_paper_lane_tiered(today, 60)
    assert got == {"AAA": date(2026, 9, 20), "BBB": date(2026, 10, 12)}


# ── the replay walker binds its writer ONCE per signal ────────────────────────────────────

_NO_TICK_SIGNAL = {"signal_id": 7, "ticker": "SMLL", "scan_date": date(2026, 10, 9),
                   "tick_wallclock_et": None}      # the walker's first, no-IO write path


def _tally() -> dict:
    return {"population": 0, "candidates": 0, "written": 0, "settled": 0, "no_trade": 0,
            "unscoreable": 0, "open": 0, "horizon": 0, "pending": 0, "errors": 0}


@pytest.mark.asyncio
async def test_the_walker_writes_through_the_shadow_upsert_by_default(monkeypatch):
    from agents.market_intelligence import lowcap_lane_replay as lcl
    shadow = AsyncMock(return_value=True)
    paper = AsyncMock(return_value=True)
    monkeypatch.setattr(lcl, "upsert_lowcap_lane_replay", shadow)
    monkeypatch.setattr(db, "upsert_lowcap_paper_lane_replay", paper)
    out = _tally()
    await lcl._record_one_signal(None, dict(_NO_TICK_SIGNAL), date(2026, 10, 9), date(2026, 10, 12), out)
    assert shadow.await_count == 1 and not paper.await_count
    assert shadow.await_args.args[0]["entry_status"] == "no_tick_wallclock"
    assert out["written"] == 1 and out["unscoreable"] == 1


@pytest.mark.asyncio
async def test_a_paper_population_writes_only_to_its_own_upsert_and_audits_its_own_event(monkeypatch):
    from agents.market_intelligence import lowcap_lane_replay as lcl
    from agents.market_intelligence import live_fill_counterfactuals as lfc
    shadow = AsyncMock(return_value=True)
    monkeypatch.setattr(lcl, "upsert_lowcap_lane_replay", shadow)
    paper = AsyncMock(return_value=True)
    out = _tally()
    await lcl._record_one_signal(None, dict(_NO_TICK_SIGNAL), date(2026, 10, 9), date(2026, 10, 12), out,
                                 upsert=paper, error_event="lowcap_paper_lane_replay_error")
    assert paper.await_count == 1 and not shadow.await_count and out["written"] == 1
    # a failing write is tallied and audited under the PAPER lane's event name, not the shadow's
    audits = []

    async def _audit(ev, summary, *a, **k):
        audits.append(ev)
    monkeypatch.setattr(lfc, "log_audit_event", _audit)
    boom = AsyncMock(side_effect=RuntimeError("db down"))
    out = _tally()
    await lcl._record_one_signal(None, dict(_NO_TICK_SIGNAL), date(2026, 10, 9), date(2026, 10, 12), out,
                                 upsert=boom, error_event="lowcap_paper_lane_replay_error")
    assert out["errors"] == 1 and audits == ["lowcap_paper_lane_replay_error"]
    assert not shadow.await_count


@pytest.mark.asyncio
async def test_run_paper_lane_replay_end_to_end_never_touches_the_shadow_table_writer(monkeypatch):
    from datetime import datetime
    from agents.market_intelligence import lowcap_lane_replay as lcl
    from shared.dates import _ET
    pop = [dict(_NO_TICK_SIGNAL)]
    monkeypatch.setattr(db, "get_lowcap_paper_lane_population", AsyncMock(return_value=pop))
    monkeypatch.setattr(db, "get_lowcap_paper_lane_replay_existing", AsyncMock(return_value={}))
    paper = AsyncMock(return_value=True)
    monkeypatch.setattr(db, "upsert_lowcap_paper_lane_replay", paper)
    shadow = AsyncMock(return_value=True)
    monkeypatch.setattr(lcl, "upsert_lowcap_lane_replay", shadow)
    pool, _ = make_mock_pool()
    monkeypatch.setattr(lcl, "get_pool", AsyncMock(return_value=pool))
    audits = []

    async def _audit(ev, summary, *a, **k):
        audits.append(ev)
    monkeypatch.setattr(lcl, "log_audit_event", _audit)
    out = await lcl.run_paper_lane_replay(date(2026, 10, 12),
                                          now_et=datetime(2026, 10, 12, 18, 15, tzinfo=_ET))
    assert out["population"] == 1 and out["written"] == 1 and out["errors"] == 0
    assert paper.await_count == 1 and not shadow.await_count
    assert audits == ["lowcap_paper_lane_replay_recorded"]
