"""#301 P1 ensemble-divergence SHADOW — judge_divergence.py.

Pins:
  1. divergence logged on AGREE and on DISAGREE (agree flag + full 2nd verdict persisted).
  2. a 2nd-model failure (grade_holistic -> None, its own fail-open contract) leaves the
     module fail-open too: no telemetry row, one COUNTED audit event, and — critically —
     the background task never raises, since nothing is waiting to catch it.
  3. a DB write failure is likewise swallowed to a COUNTED audit event, never raised.
  4. launch_divergence_check is genuinely fire-and-forget: it returns synchronously without
     awaiting the background task, and retains a strong module-level reference to it (the
     GC-safety contract) until the task self-removes on completion.
  5. the primary verdict is copied defensively at launch time — a caller mutating its dict
     after calling launch_divergence_check cannot corrupt the logged row.
  6. the 2nd-model call uses a DIFFERENT model than the primary judge, and a distinct
     `log_caller` so its spend is separately attributable (#377 cost meter).
  7. the ep_detector.py trigger site is genuinely off the critical path (never awaited) and
     gated on both the HIGH-tier verdict and the once-per-ticker-per-day dedupe guard.
"""
import asyncio
from datetime import date
from unittest.mock import AsyncMock

from tests.conftest import make_mock_pool

from agents.market_intelligence import audit_events, db, ep_grade_judge
from agents.market_intelligence import judge_divergence as jd
from shared.llm_models import JUDGE_DIVERGENCE_MODEL, JUDGE_MODEL


def _run(coro):
    return asyncio.run(coro)


_PAYLOAD = {"ticker": "TICK", "gap_pct": 12.0}
_PRIMARY = {
    "tier": "HIGH", "grade": "strong", "direction_vs_floor": "hold",
    "confidence": 0.8, "rationale": "primary rationale",
}


def _mock_db(monkeypatch):
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    audit_mock = AsyncMock()
    monkeypatch.setattr(db, "log_audit_event", audit_mock)
    return conn, audit_mock


# ─── Divergence logged on agree / disagree ─────────────────────────────────────────────────


def test_divergence_logged_on_agree(monkeypatch):
    conn, audit_mock = _mock_db(monkeypatch)
    secondary = {
        "tier": "HIGH", "grade": "strong", "direction_vs_floor": "hold",
        "confidence": 0.7, "rationale": "secondary agrees",
    }
    monkeypatch.setattr(ep_grade_judge, "grade_holistic", AsyncMock(return_value=secondary))

    _run(jd._run("TICK", date(2026, 7, 26), _PAYLOAD, dict(_PRIMARY)))

    assert conn.execute.await_count == 1
    args = conn.execute.await_args.args
    # positional: sql, ticker, alert_date, primary_model, primary_tier, primary_grade,
    # primary_direction, primary_confidence, secondary_model, secondary_tier, secondary_grade,
    # secondary_direction, secondary_confidence, secondary_rationale, agree
    assert args[1] == "TICK"
    assert args[2] == date(2026, 7, 26)
    assert args[3] == JUDGE_MODEL
    assert args[4] == "HIGH"                    # primary_tier
    assert args[8] == JUDGE_DIVERGENCE_MODEL
    assert args[9] == "HIGH"                    # secondary_tier
    assert args[13] == "secondary agrees"        # secondary_rationale
    assert args[14] is True                      # agree

    fired = [c.args[0] for c in audit_mock.await_args_list]
    assert audit_events.JUDGE_DIVERGENCE_DETECTED not in fired


def test_divergence_logged_on_disagree(monkeypatch):
    conn, audit_mock = _mock_db(monkeypatch)
    secondary = {
        "tier": "MODERATE", "grade": "routine", "direction_vs_floor": "demote",
        "confidence": 0.6, "rationale": "secondary disagrees",
    }
    monkeypatch.setattr(ep_grade_judge, "grade_holistic", AsyncMock(return_value=secondary))

    _run(jd._run("DIVR", date(2026, 7, 26), _PAYLOAD, dict(_PRIMARY)))

    assert conn.execute.await_count == 1
    args = conn.execute.await_args.args
    assert args[4] == "HIGH"        # primary_tier unchanged
    assert args[9] == "MODERATE"    # secondary_tier
    assert args[14] is False        # agree

    fired = [c.args[0] for c in audit_mock.await_args_list]
    assert audit_events.JUDGE_DIVERGENCE_DETECTED in fired


# ─── Fail-open: 2nd-model failure and DB-write failure ─────────────────────────────────────


def test_second_model_failure_leaves_primary_path_untouched(monkeypatch):
    """grade_holistic's own contract: None on any error/timeout. The divergence module must
    not write a row (there's no verdict to compare) and must not raise — it is a background
    task nobody awaits, so an uncaught exception here would only surface as an "exception was
    never retrieved" warning at GC time, silently losing the signal."""
    conn, audit_mock = _mock_db(monkeypatch)
    monkeypatch.setattr(ep_grade_judge, "grade_holistic", AsyncMock(return_value=None))

    _run(jd._run("FAIL", date(2026, 7, 26), _PAYLOAD, dict(_PRIMARY)))  # must not raise

    assert conn.execute.await_count == 0
    fired = [c.args[0] for c in audit_mock.await_args_list]
    assert audit_events.JUDGE_DIVERGENCE_CHECK_FAILED in fired
    assert audit_events.JUDGE_DIVERGENCE_DETECTED not in fired


def test_db_write_failure_is_swallowed_to_an_audit_event(monkeypatch):
    conn, audit_mock = _mock_db(monkeypatch)
    conn.execute = AsyncMock(side_effect=RuntimeError("db down"))
    secondary = {"tier": "HIGH", "grade": "strong", "direction_vs_floor": "hold",
                 "confidence": 0.7, "rationale": "secondary agrees"}
    monkeypatch.setattr(ep_grade_judge, "grade_holistic", AsyncMock(return_value=secondary))

    _run(jd._run("WERR", date(2026, 7, 26), _PAYLOAD, dict(_PRIMARY)))  # must not raise

    fired = [c.args[0] for c in audit_mock.await_args_list]
    assert audit_events.JUDGE_DIVERGENCE_CHECK_FAILED in fired


# ─── launch_divergence_check: fire-and-forget + GC-safety + defensive copy ─────────────────


def test_launch_returns_synchronously_and_retains_then_releases_task_ref(monkeypatch):
    conn, audit_mock = _mock_db(monkeypatch)
    secondary = {"tier": "HIGH", "grade": "strong", "direction_vs_floor": "hold",
                 "confidence": 0.7, "rationale": "secondary agrees"}
    monkeypatch.setattr(ep_grade_judge, "grade_holistic", AsyncMock(return_value=secondary))

    async def _scenario():
        assert len(jd._BACKGROUND_TASKS) == 0
        jd.launch_divergence_check("TASKREF", date(2026, 7, 26), _PAYLOAD, dict(_PRIMARY))
        # Scheduled but the caller never awaited it — a strong reference must be retained
        # (the GC-safety contract) or the task could vanish mid-run.
        assert len(jd._BACKGROUND_TASKS) == 1
        task = next(iter(jd._BACKGROUND_TASKS))
        await task  # let it run to completion
        # Self-removed via the done-callback once finished.
        assert len(jd._BACKGROUND_TASKS) == 0

    _run(_scenario())
    assert conn.execute.await_count == 1


def test_launch_does_not_block_the_caller(monkeypatch):
    """The primary judge path must proceed byte-identically regardless of how slow/failed
    the 2nd-model call is — pin this by making grade_holistic hang, and asserting
    launch_divergence_check still returns immediately."""
    conn, audit_mock = _mock_db(monkeypatch)

    async def _hang(*a, **kw):
        await asyncio.sleep(10)
        return None
    monkeypatch.setattr(ep_grade_judge, "grade_holistic", _hang)

    async def _scenario():
        loop = asyncio.get_event_loop()
        t0 = loop.time()
        jd.launch_divergence_check("SLOW", date(2026, 7, 26), _PAYLOAD, dict(_PRIMARY))
        elapsed = loop.time() - t0
        assert elapsed < 0.05  # returned immediately, did not wait on the hanging call
        # Cancel the still-hanging background task so the test doesn't itself hang, and
        # await the cancellation cleanly so the loop doesn't close over a pending task.
        for task in list(jd._BACKGROUND_TASKS):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    _run(_scenario())


def test_primary_verdict_copied_defensively(monkeypatch):
    """Mutating the caller's verdict dict AFTER launch must not corrupt the logged row —
    ep_detector's `v` dict is a live object the caller's loop may keep touching."""
    conn, audit_mock = _mock_db(monkeypatch)
    secondary = {"tier": "HIGH", "grade": "strong", "direction_vs_floor": "hold",
                 "confidence": 0.7, "rationale": "secondary agrees"}
    monkeypatch.setattr(ep_grade_judge, "grade_holistic", AsyncMock(return_value=secondary))

    async def _scenario():
        primary = dict(_PRIMARY)
        jd.launch_divergence_check("COPY", date(2026, 7, 26), _PAYLOAD, primary)
        primary["tier"] = "MUTATED-AFTER-LAUNCH"  # caller mutates its own dict post-launch
        task = next(iter(jd._BACKGROUND_TASKS))
        await task

    _run(_scenario())
    args = conn.execute.await_args.args
    assert args[4] == "HIGH"  # logged the value AT LAUNCH TIME, not the later mutation


# ─── Model choice + spend attribution ──────────────────────────────────────────────────────


def test_uses_a_different_model_than_the_primary_judge_and_distinct_log_caller(monkeypatch):
    _mock_db(monkeypatch)
    gh = AsyncMock(return_value={"tier": "HIGH", "grade": "strong",
                                  "direction_vs_floor": "hold", "confidence": 0.7,
                                  "rationale": "r"})
    monkeypatch.setattr(ep_grade_judge, "grade_holistic", gh)

    _run(jd._run("MODEL", date(2026, 7, 26), _PAYLOAD, dict(_PRIMARY)))

    assert gh.await_count == 1
    _, kwargs = gh.await_args
    assert kwargs["model"] == JUDGE_DIVERGENCE_MODEL
    assert kwargs["model"] != JUDGE_MODEL
    assert kwargs["log_caller"] == "judge_divergence"
    # The SAME payload the primary judge saw — identical, not rebuilt.
    assert gh.await_args.args[1] is _PAYLOAD


# ─── ep_detector.py wiring: off the critical path, correctly gated ─────────────────────────


def test_ep_detector_trigger_is_never_awaited_and_is_gated():
    import agents.market_intelligence.ep_detector as ep
    src = open(ep.__file__).read()
    assert "launch_divergence_check(" in src
    assert "await launch_divergence_check" not in src
    assert 'v.get("tier") == "HIGH"' in src
    assert '"judge_divergence_check"' in src


# ─── db.get_judge_divergence_stats — the weekly-digest aggregate ───────────────────────────


def test_get_judge_divergence_stats_shape(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value={"n": 12, "n_disagree": 4, "secondary_model": JUDGE_DIVERGENCE_MODEL})
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))

    stats = _run(db.get_judge_divergence_stats(date(2026, 7, 20)))
    assert stats == {"n": 12, "n_disagree": 4, "secondary_model": JUDGE_DIVERGENCE_MODEL}


def test_get_judge_divergence_stats_no_rows(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value={"n": 0, "n_disagree": 0, "secondary_model": None})
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))

    stats = _run(db.get_judge_divergence_stats(date(2026, 7, 20)))
    assert stats["n"] == 0


# ─── system_review._judge_divergence_section — the ONE weekly-review line ──────────────────


def test_digest_line_is_a_noop_when_no_data(monkeypatch):
    from agents.market_intelligence import system_review

    monkeypatch.setattr(
        db, "get_judge_divergence_stats", AsyncMock(return_value={"n": 0, "n_disagree": 0, "secondary_model": None}),
    )
    line = _run(system_review._judge_divergence_section(date(2026, 7, 20)))
    assert line == ""


def test_digest_line_renders_and_flags_above_25_pct(monkeypatch):
    from agents.market_intelligence import system_review

    monkeypatch.setattr(
        db, "get_judge_divergence_stats",
        AsyncMock(return_value={"n": 10, "n_disagree": 3, "secondary_model": JUDGE_DIVERGENCE_MODEL}),
    )
    line = _run(system_review._judge_divergence_section(date(2026, 7, 20)))
    assert "3/10" in line
    assert "30%" in line
    assert JUDGE_DIVERGENCE_MODEL in line
    assert "⚠" in line


def test_digest_line_renders_without_flag_under_25_pct(monkeypatch):
    from agents.market_intelligence import system_review

    monkeypatch.setattr(
        db, "get_judge_divergence_stats",
        AsyncMock(return_value={"n": 10, "n_disagree": 1, "secondary_model": JUDGE_DIVERGENCE_MODEL}),
    )
    line = _run(system_review._judge_divergence_section(date(2026, 7, 20)))
    assert "1/10" in line
    assert "10%" in line
    assert "⚠" not in line
