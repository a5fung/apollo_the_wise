"""#332 (ADR 0028 C1) — the 3 new as-of DB primitives + the tag-visibility writer that
`setup_class_classifier.compute_setup_class_fields` / `ep_detector._judge_shadow` call:

  - get_9m_alert_same_day            (mi_9m_ep_alerts, SAME-day exact match)
  - get_sugar_baby_cohort_member_asof (mi_sugar_babies_cohort, AS-OF latest cohort_date <= alert_date)
  - get_adv_20_dollar_asof            (mi_daily_closes, ticker-scoped, STRICTLY PRIOR to alert_date)
  - update_ep_alert_setup_class       (mi_ep_alerts.setup_class UPDATE — P0 visibility only)

Mirrors test_theme_axis_shadow.py's `test_asof_query_uses_no_lookahead` pattern: capture the
SQL + params via a fake conn/pool rather than hitting a real database.
"""
from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock

from tests.conftest import make_mock_pool

from agents.market_intelligence.db import (
    get_9m_alert_same_day,
    get_adv_20_dollar_asof,
    get_sugar_baby_cohort_member_asof,
    update_ep_alert_setup_class,
)


def _run(coro):
    return asyncio.run(coro)


# ─── get_9m_alert_same_day ──────────────────────────────────────────────────────────────────

def test_9m_same_day_true_when_row_exists():
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value={"?column?": 1})
    assert _run(get_9m_alert_same_day(conn, "TICK", date(2026, 7, 18))) is True


def test_9m_same_day_false_when_no_row():
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=None)
    assert _run(get_9m_alert_same_day(conn, "TICK", date(2026, 7, 18))) is False


def test_9m_same_day_queries_exact_date_not_a_window():
    pool, conn = make_mock_pool()
    captured = {}

    async def _capture(sql, *params):
        captured["sql"], captured["params"] = sql, params
        return None
    conn.fetchrow = _capture
    _run(get_9m_alert_same_day(conn, "TICK", date(2026, 7, 18)))
    assert "mi_9m_ep_alerts" in captured["sql"]
    assert "alert_date = $2" in captured["sql"]
    assert captured["params"] == ("TICK", date(2026, 7, 18))


# ─── get_sugar_baby_cohort_member_asof ──────────────────────────────────────────────────────

def test_sugar_baby_member_true_when_row_exists():
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value={"?column?": 1})
    assert _run(get_sugar_baby_cohort_member_asof(conn, "TICK", date(2026, 7, 18))) is True


def test_sugar_baby_member_false_when_not_in_cohort():
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=None)
    assert _run(get_sugar_baby_cohort_member_asof(conn, "TICK", date(2026, 7, 18))) is False


def test_sugar_baby_query_uses_no_lookahead_asof_pattern():
    pool, conn = make_mock_pool()
    captured = {}

    async def _capture(sql, *params):
        captured["sql"], captured["params"] = sql, params
        return None
    conn.fetchrow = _capture
    _run(get_sugar_baby_cohort_member_asof(conn, "TICK", date(2026, 7, 18)))
    assert "mi_sugar_babies_cohort" in captured["sql"]
    assert "cohort_date <= $2" in captured["sql"]
    assert "MAX(cohort_date)" in captured["sql"]
    assert captured["params"] == ("TICK", date(2026, 7, 18))


# ─── get_adv_20_dollar_asof ─────────────────────────────────────────────────────────────────

def test_adv_20_dollar_multiplies_share_median_by_price():
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value={"adv": 500_000.0})
    result = _run(get_adv_20_dollar_asof(conn, "TICK", date(2026, 7, 18), price=20.0))
    assert result == 10_000_000.0


def test_adv_20_dollar_none_when_no_history():
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=None)
    assert _run(get_adv_20_dollar_asof(conn, "TICK", date(2026, 7, 18), price=20.0)) is None


def test_adv_20_dollar_none_when_price_missing_or_zero():
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(side_effect=AssertionError("must not query with no usable price"))
    assert _run(get_adv_20_dollar_asof(conn, "TICK", date(2026, 7, 18), price=None)) is None
    assert _run(get_adv_20_dollar_asof(conn, "TICK", date(2026, 7, 18), price=0)) is None


def test_adv_20_dollar_query_is_strictly_prior_no_lookahead():
    pool, conn = make_mock_pool()
    captured = {}

    async def _capture(sql, *params):
        captured["sql"], captured["params"] = sql, params
        return {"adv": 1.0}
    conn.fetchrow = _capture
    _run(get_adv_20_dollar_asof(conn, "TICK", date(2026, 7, 18), price=10.0))
    assert "mi_daily_closes" in captured["sql"]
    assert "trade_date < $2" in captured["sql"]           # strictly prior, not <=
    assert "PERCENTILE_CONT(0.5)" in captured["sql"]        # same median primitive
    assert captured["params"] == ("TICK", date(2026, 7, 18), 20)


# ─── update_ep_alert_setup_class ────────────────────────────────────────────────────────────

def test_update_setup_class_writes_the_tag(monkeypatch):
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()

    async def _fake_pool():
        return pool
    monkeypatch.setattr("agents.market_intelligence.db.get_pool", _fake_pool)

    _run(update_ep_alert_setup_class("TICK", date(2026, 7, 18), "pradeep_explosive"))
    assert conn.execute.await_count == 1
    args = conn.execute.await_args.args
    assert "UPDATE mi_ep_alerts SET setup_class" in args[0]
    assert args[1:] == ("TICK", date(2026, 7, 18), "pradeep_explosive")


def test_update_setup_class_never_touches_score_tier_column(monkeypatch):
    """THE LINE, behavioral pin: the SQL statement actually executed must never mention
    score_tier/grade_engine_authority or any other grading column — it can only ever touch
    setup_class."""
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()

    async def _fake_pool():
        return pool
    monkeypatch.setattr("agents.market_intelligence.db.get_pool", _fake_pool)

    _run(update_ep_alert_setup_class("TICK", date(2026, 7, 18), "unclassified"))
    sql = conn.execute.await_args.args[0]
    assert "score_tier" not in sql
    assert "grade_engine_authority" not in sql
    assert sql.count("SET") == 1  # exactly one column set, no multi-column atomic write
