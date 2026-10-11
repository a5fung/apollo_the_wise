"""#415 — legacy-eligibility flag correctness (allocator real-contest filter).

The `legacy_eligible` flag on `unified_allocation_decided` feeds the eventual
allocator-vs-FCFS routing decision (it filters "real contests" out of the
inflated raw contested-day count). A wrong value would poison that evidence, so
this freezes the criterion:

- MAGNA53 HIGH-tier (ep_score >= the regime EP threshold) -> 'eligible'
- MAGNA53 below the threshold                            -> 'ineligible'
- every non-MAGNA53 strategy                             -> 'unclassified'
  (the legacy entry gate isn't a simple field on those candidates; we mark it
  unknown rather than guess — a tri-state string so 'unknown' can never be
  silently read as 'ineligible').
"""
from datetime import date

from agents.market_intelligence.cross_strategy_allocator import (
    RankableCandidate,
    _legacy_eligibility,
    score_magna53,
)


def _magna(ep_score):
    return score_magna53(
        ticker="TEST", alert_date=date(2026, 7, 20), ep_score=ep_score,
        catalyst_quality="strong", pm_rvol=3.0, gap_pct=5.0, regime_label="Bull",
    )


def test_magna53_high_tier_is_eligible():
    assert _legacy_eligibility(_magna(75), ep_threshold=70) == "eligible"
    # boundary is inclusive — a score exactly at the threshold grades HIGH
    assert _legacy_eligibility(_magna(70), ep_threshold=70) == "eligible"


def test_magna53_below_threshold_is_ineligible():
    assert _legacy_eligibility(_magna(69), ep_threshold=70) == "ineligible"
    assert _legacy_eligibility(_magna(50), ep_threshold=70) == "ineligible"


def test_threshold_is_regime_relative():
    # Same score, stricter regime threshold flips the flag — the cutoff must
    # track the regime (ep_threshold ranges 65..80), not a hardcoded 70.
    c = _magna(72)
    assert _legacy_eligibility(c, ep_threshold=70) == "eligible"
    assert _legacy_eligibility(c, ep_threshold=75) == "ineligible"


def _other(strategy="flag_continuation"):
    """A non-MAGNA53 candidate, built DIRECTLY rather than through a strategy scorer.

    It used to be built by `score_9m_day2`, which was deleted with the Day-2 entry (#515,
    2026-08-02). Constructing the candidate here is the more honest fixture anyway: these two
    tests are about the DEPRECATION GATE, which is generic over strategy names — binding them to
    one strategy's scorer made a retired strategy load-bearing for unrelated coverage."""
    return RankableCandidate(
        ticker="SUGR", alert_date=date(2026, 7, 20), strategy=strategy,
        setup_quality=80.0, catalyst=100.0, volume=60.0, regime=100.0, composite=85.0,
    )


def test_deprecated_strategy_is_ineligible():
    # A deprecated strategy can never be a real legacy auto-entry, so it must be 'ineligible',
    # not counted as a contender. (9m_day2 was the original case — deprecated as a standalone
    # ENTRY 2026-07-05, deleted outright 2026-08-02; the gate itself is unchanged and generic.)
    assert _legacy_eligibility(_other(), 70,
                               deprecated_strategies={"flag_continuation"}) == "ineligible"


def test_non_deprecated_non_magna_stays_unclassified():
    # A non-deprecated, non-MAGNA53 strategy (e.g. a shadow strategy under
    # evaluation) is genuinely unknown -> 'unclassified', never guessed.
    assert _legacy_eligibility(_other(), 70, deprecated_strategies=frozenset()) == "unclassified"


# ─── #312 Step A (2026-10-10) — the ranking reads the PRE-ENTRY live book, at 09:28 ET ────
# The shadow job ran at 09:35 for five months, four minutes AFTER the 09:31 ORB submits, and
# read `get_open_position_count()` live — so a candidate that had already filled was counted
# once as an open position (consuming a slot) and again as the winner of a slot that remained
# (6 of 7 winners, docs/analysis/unified_allocator_phase_1b_2026-09-14.md §2). These pin the
# two halves of the fix: slots come from positions whose alert_date PRECEDES the target day,
# on the live book only; and the job is registered before the open. Extends this file per
# docs/testing/test_discipline.md (the module's existing test file, not a task-numbered one).
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from tests.conftest import make_mock_pool

_ET_OFFSETS = (timedelta(hours=-4), timedelta(hours=-5))   # EDT / EST — what an ET-aware stamp parses to


def _queue_rows(target_date):
    """Three MAGNA53 queue rows in composite order AAA > BBB > CCC (ids 11, 12, 13)."""
    def row(i, ticker, ep):
        return {"id": i, "ticker": ticker, "alert_date": target_date, "strategy": "magna53",
                "composite_score": 0, "status": "pending",
                "raw_dimensions": {"ep_score": ep, "catalyst_quality": "strong",
                                   "pm_rvol": 3.0, "gap_pct": 12.0, "regime": "Bull"}}
    return [row(11, "AAA", 95), row(12, "BBB", 85), row(13, "CCC", 75)]


async def _run_with_book(monkeypatch, target_date, *, pre_entry_live=3, live_now=5, queue=None):
    """Run the shadow allocation against a book that holds `live_now` open live rows at the
    tick, of which only `pre_entry_live` predate the target day — the rest are that morning's
    09:31 fills (the HUM 2026-10-09 shape: the one candidate being ranked had already filled,
    and the 09:35 run read slots=0 against it). Returns (result, count_calls, audit_mock)."""
    from agents.market_intelligence import db, regime
    from agents.market_intelligence import cross_strategy_allocator as alloc
    count_calls = []

    async def _count(**kw):
        count_calls.append(kw)
        if kw.get("account_mode") == "live" and kw.get("before_alert_date") == target_date:
            return pre_entry_live
        return live_now  # the unfiltered read: today's fills included (the pre-Step-A bug)

    rows = _queue_rows(target_date) if queue is None else queue
    monkeypatch.setattr(db, "get_pending_allocations_for_date", AsyncMock(return_value=rows))
    monkeypatch.setattr(db, "get_open_position_count", _count)
    monkeypatch.setattr(db, "get_deprecated_strategy_signal_types", AsyncMock(return_value=set()))
    monkeypatch.setattr(db, "mark_pending_allocations_evaluated", AsyncMock())
    audit = AsyncMock()
    monkeypatch.setattr(db, "log_audit_event", audit)
    monkeypatch.setattr(regime, "get_current_regime",
                        AsyncMock(return_value={"regime": "Bull", "ep_threshold": 70}))
    result = await alloc.run_shadow_allocation(target_date)
    return result, count_calls, audit


@pytest.mark.asyncio
async def test_slots_come_from_the_pre_entry_live_book_not_the_live_count(monkeypatch):
    """MUTATION (the pre-Step-A code): `db.get_open_position_count()` with no filters. The
    count then includes the morning's two 09:31 fills, slots read 0 and the ranking names no
    winner — while the pre-entry book had two free slots and AAA/BBB should have won them."""
    target = date(2026, 10, 9)
    result, count_calls, _ = await _run_with_book(monkeypatch, target, pre_entry_live=3, live_now=5)
    assert count_calls == [{"account_mode": "live", "before_alert_date": target}]
    assert (result["open_positions"], result["slots"]) == (3, 2)
    assert result["top_picks"] == ["AAA", "BBB"] and result["lower_ranked"] == ["CCC"]


@pytest.mark.asyncio
async def test_audit_row_says_when_it_ranked_and_which_queue_rows_it_saw(monkeypatch):
    """The Step B bar ("names arriving after 09:28 outrank the 09:28 winners on more than a
    third of 15 contested days") needs two facts the row did not carry: WHEN the ranking was
    taken and WHICH queue rows it saw. `created_at` on the queue is last-write (the UPSERT
    refreshes it), so neither is derivable without these."""
    target = date(2026, 10, 9)
    _, _, audit = await _run_with_book(monkeypatch, target)
    (event, _summary), kw = audit.call_args.args, audit.call_args.kwargs
    assert event == "unified_allocation_decided"
    detail = json.loads(kw["detail"])
    assert detail["ranked_ids"] == [11, 12, 13]        # rank order, every row the ranking saw
    ranked_at = datetime.fromisoformat(detail["ranked_at_et"])
    assert ranked_at.utcoffset() in _ET_OFFSETS         # ET-aware, never a naive container clock
    assert (detail["open_positions"], detail["slots_available"]) == (3, 2)
    assert [w["ticker"] for w in detail["winners"]] == ["AAA", "BBB"]


@pytest.mark.asyncio
async def test_empty_queue_row_still_says_when_it_ranked(monkeypatch):
    """The empty-queue row must stay parseable and carry the timestamp, or a quiet day is
    indistinguishable from a job that never ran at its new time. It also carries `ranked_ids`
    (empty): 18 of the last 31 mornings had an empty queue, and a row without the key reads as
    NULL to the Step B join and to the day-one `ranked_ids` check. Its keys are a subset of the
    full row's - the only link between the two branches, so it is pinned here."""
    target = date(2026, 10, 9)
    _, count_calls, audit = await _run_with_book(monkeypatch, target, queue=[])
    assert count_calls == []                          # nothing to rank -> no book read
    raw = audit.call_args.kwargs["detail"]
    detail = json.loads(raw)
    assert detail["n_candidates"] == 0
    assert detail["ranked_ids"] == []                 # same keys as the full row, never absent
    assert datetime.fromisoformat(detail["ranked_at_et"]).utcoffset() in _ET_OFFSETS
    # the stored text is the compact form it has always been (the same row, not a reformatting)
    assert raw.startswith('{"target_date":"2026-10-09","n_candidates":0,"ranked_at_et":"')
    assert raw.endswith('","ranked_ids":[]}')
    _, _, full_audit = await _run_with_book(monkeypatch, target)
    assert set(detail) <= set(json.loads(full_audit.call_args.kwargs["detail"]))


@pytest.mark.asyncio
async def test_get_open_position_count_binds_the_live_book_and_the_pre_entry_cutoff(monkeypatch):
    """The two filters are bound as parameters (never a SQL mode literal — the mode-literal
    gate) on top of the UNCHANGED shared open-status vocabulary; the unfiltered call keeps its
    old meaning for any other caller."""
    from agents.market_intelligence import db
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value={"n": 2})
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))

    n = await db.get_open_position_count(account_mode="live", before_alert_date=date(2026, 10, 9))

    assert n == 2
    query, statuses, mode, cutoff = conn.fetchrow.call_args.args
    assert set(statuses) == set(db.OPEN_POSITION_STATUSES) and "pending_confirmation" not in statuses
    assert (mode, cutoff) == ("live", date(2026, 10, 9))
    assert "account_mode = $2" in query and "alert_date < $3" in query
    assert "'live'" not in query and "'paper'" not in query

    await db.get_open_position_count()
    assert conn.fetchrow.call_args.args[2:] == (None, None)


def test_shadow_job_is_registered_at_0928_ET_before_the_orb_submits(monkeypatch):
    """Read off the job start_scheduler REALLY registers (the capturing-scheduler pattern of
    tests/test_job_partition.py), not the source text. MUTATION: minute=35 — the registration
    this replaced — fails the minute check; dropping misfire_grace_time fails the bound."""
    from agents.market_intelligence import scheduler as sched
    from tests.test_job_partition import _CapturingScheduler
    captured = {}

    class _Spy(_CapturingScheduler):
        def start(self):
            captured["jobs"] = {j.id: j for j in self.get_jobs()}

    monkeypatch.setattr(sched, "AsyncIOScheduler", _Spy)

    async def _start():
        sched.start_scheduler()
    asyncio.run(_start())

    job = captured["jobs"]["unified_allocator_shadow"]
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert (fields["hour"], fields["minute"], fields["day_of_week"]) == ("9", "28", "mon-fri")
    assert str(job.trigger.timezone) == "America/New_York"
    # The pre-open bound: a stalled loop may start it as late as 09:29:30, never at 09:30.
    assert job.misfire_grace_time == 90
    assert 9 * 3600 + 28 * 60 + job.misfire_grace_time < 9 * 3600 + 30 * 60
    # Execution-owned: it reads the live book, and the #672 recovery sweep excludes this set,
    # so a missed 09:28 run is never re-run after the fills.
    assert "unified_allocator_shadow" in sched.EXECUTION_OWNED_JOB_IDS
