"""Prong B (#54 RMV-miss mitigation) — escalate_overdue_reviews grace/dedup/error logic.

A data-gated review that's been READY (or whose predicate is ERRORING — the #54 silently-broken
locked-query class) beyond a grace window must escalate exactly once, then re-fire only on the
reescalate cadence, and clear state when it resolves. DB + check_pending_reviews are mocked with an
in-memory store so the pure date logic is pinned without a live DB.
"""
import asyncio
from datetime import date, timedelta

import agents.market_intelligence.data_gated_reviews as dgr
import agents.market_intelligence.db as db

T = date(2026, 6, 16)


def _wire(monkeypatch, ready, errored, state):
    async def fake_check(today=None):
        return {"ready": ready, "errored": errored, "pending_count": 0, "pending_summary": []}
    monkeypatch.setattr(dgr, "check_pending_reviews", fake_check)

    store = {k: dict(v) for k, v in state.items()}

    async def fake_get():
        return {k: dict(v) for k, v in store.items()}

    async def fake_upsert(rid, fr, fe, le):
        store[rid] = {"first_ready_date": fr, "first_error_date": fe, "last_escalated_date": le}

    async def fake_clear(rids):
        for r in rids:
            store.pop(r, None)

    monkeypatch.setattr(db, "get_review_escalation_state", fake_get)
    monkeypatch.setattr(db, "upsert_review_escalation_state", fake_upsert)
    monkeypatch.setattr(db, "clear_review_escalation_state", fake_clear)
    return store


def _ready(rid="r1"):
    return [{"review_id": rid, "title": "t", "current_count": 9, "threshold": 5}]


def _err(rid="r1"):
    return [{"review_id": rid, "title": "t", "blocked_by": "predicate_error: UndefinedColumn"}]


def _run(monkeypatch, ready, errored, state, **kw):
    store = _wire(monkeypatch, ready, errored, state)
    esc = asyncio.run(dgr.escalate_overdue_reviews(today=T, **kw))
    return esc, store


def test_ready_under_grace_no_escalation(monkeypatch):
    esc, store = _run(monkeypatch, _ready(), [], {})
    assert esc == []                                  # age 0 < grace 7
    assert store["r1"]["first_ready_date"] == T       # but first-ready stamped
    assert store["r1"]["last_escalated_date"] is None


def test_ready_past_grace_escalates_once(monkeypatch):
    state = {"r1": {"first_ready_date": T - timedelta(days=7), "first_error_date": None,
                    "last_escalated_date": None}}
    esc, store = _run(monkeypatch, _ready(), [], state)
    assert len(esc) == 1 and esc[0]["kind"] == "ready" and esc[0]["age_days"] == 7
    assert store["r1"]["last_escalated_date"] == T    # dedup stamp set


def test_dedup_within_reescalate_window(monkeypatch):
    state = {"r1": {"first_ready_date": T - timedelta(days=9), "first_error_date": None,
                    "last_escalated_date": T - timedelta(days=1)}}
    esc, _ = _run(monkeypatch, _ready(), [], state)
    assert esc == []                                  # ready 9d but escalated 1d ago < reescalate 7


def test_reescalates_after_cadence(monkeypatch):
    state = {"r1": {"first_ready_date": T - timedelta(days=20), "first_error_date": None,
                    "last_escalated_date": T - timedelta(days=7)}}
    esc, _ = _run(monkeypatch, _ready(), [], state)
    assert len(esc) == 1                              # last escalated exactly reescalate_days ago


def test_erroring_predicate_escalates(monkeypatch):
    state = {"r1": {"first_ready_date": None, "first_error_date": T - timedelta(days=8),
                    "last_escalated_date": None}}
    esc, _ = _run(monkeypatch, [], _err(), state)
    assert len(esc) == 1 and esc[0]["kind"] == "error" and esc[0]["age_days"] == 8


def test_resolved_review_state_cleared(monkeypatch):
    # r1 no longer ready/erroring → its stale state row is dropped.
    state = {"r1": {"first_ready_date": T - timedelta(days=3), "first_error_date": None,
                    "last_escalated_date": None}}
    esc, store = _run(monkeypatch, [], [], state)
    assert esc == [] and "r1" not in store


def test_ready_clears_stale_error_flag(monkeypatch):
    # a review that was erroring but is now ready: first_error_date wiped, first_ready stamped.
    state = {"r1": {"first_ready_date": None, "first_error_date": T - timedelta(days=4),
                    "last_escalated_date": None}}
    esc, store = _run(monkeypatch, _ready(), [], state)
    assert esc == []                                  # ready age 0 (fresh) < grace
    assert store["r1"]["first_error_date"] is None and store["r1"]["first_ready_date"] == T
