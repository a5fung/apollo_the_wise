"""Make a silent recorder that fails on everything look different from a quiet week (#593,
2026-09-04).

WHY THIS EXISTS. `sustain_reject_replay`'s first nightly pass (#593, 2026-09-03) hit
`KeyError: 'volume'` on ALL 95 of its candidates, wrote 0 rows, and the job reported success.
Its counters read {"population": 95, "candidates": 95, "written": 0, "errors": 95} and nothing
anywhere raised that as different from a legitimately quiet night (population=0, nothing to
write). The root-cause bug is fixed elsewhere; this is the missing detection.

`_DETECTOR_LIVENESS_TABLES` (health_checks.py) cannot catch this: it judges a table's row
history over many nights, tolerant of long legitimate silences, and both a quiet night and a
100%-failed night leave the identical zero-new-rows footprint. This module's
`evaluate_recorder_failure_rate` / `check_recorder_failure_rate` instead reads the run's OWN
counters, in hand the moment the job returns — same night, no calendar delay.
"""
import asyncio

import agents.market_intelligence.health_checks as hc


# ── evaluate_recorder_failure_rate: the pure decision (mock-free) ───────────────────────────


def test_tonights_exact_incident_fires():
    """The reproduction: population=95, candidates=95, written=0, errors=95 — 100% of a
    non-trivial batch errored. This is the case that must never again read as 'no signal'.
    written==0 with real errors present is caught by the granularity-independent
    'nothing_produced' branch (checked ahead of the plain rate branch)."""
    counters = {"population": 95, "candidates": 95, "written": 0, "errors": 95}
    flag = hc.evaluate_recorder_failure_rate(counters, "candidates")
    assert flag is not None
    assert flag["kind"] == "nothing_produced"
    assert flag["attempted"] == 95 and flag["errors"] == 95
    assert flag["rate"] == 1.0


def test_legitimately_quiet_night_stays_silent():
    """population=0, candidates=0, errors=0 — nothing to write. Must NOT fire; this is the
    'quiet week' state the whole card exists to keep looking different from a failure."""
    counters = {"population": 0, "candidates": 0, "written": 0, "errors": 0}
    assert hc.evaluate_recorder_failure_rate(counters, "candidates") is None


def test_ordinary_partial_failure_on_a_large_population_stays_silent():
    """A handful of isolated per-ticker errors among many successes is BY DESIGN in every one
    of these recorders (each names its own per-item try/except 'loud-ok'). 3 errors out of 50
    attempted (6%) is nowhere near 'failed on essentially everything' and must not alarm."""
    counters = {"population": 50, "candidates": 50, "written": 40, "errors": 3}
    assert hc.evaluate_recorder_failure_rate(counters, "candidates") is None


def test_a_single_bad_ticker_in_a_tiny_batch_does_not_cry_wolf():
    """1 error out of 1 or 2 candidates is a 100% RATE but a trivial sample — the minimum-
    attempted floor exists exactly to keep this from reading as a systemic failure."""
    assert hc.evaluate_recorder_failure_rate(
        {"population": 1, "candidates": 1, "written": 0, "errors": 1}, "candidates") is None
    assert hc.evaluate_recorder_failure_rate(
        {"population": 2, "candidates": 2, "written": 0, "errors": 2}, "candidates") is None


def test_high_but_not_essentially_total_error_rate_stays_silent():
    """60% errored (a bad night, not a broken one) must stay under the >=90% bar — a systemic
    bug like tonight's dropped column fails at ~100%, not 60%."""
    counters = {"population": 20, "candidates": 20, "written": 6, "errors": 12}
    assert hc.evaluate_recorder_failure_rate(counters, "candidates") is None


def test_right_at_the_rate_floor_fires():
    """Exactly 90% (18/20) must fire — '>=' not '>'."""
    counters = {"population": 20, "candidates": 20, "written": 2, "errors": 18}
    flag = hc.evaluate_recorder_failure_rate(counters, "candidates")
    assert flag is not None and flag["rate"] == 0.9


def test_just_below_the_minimum_attempted_floor_stays_silent():
    """4 attempted (one below the floor of 5), all erroring — still too small a sample."""
    counters = {"population": 4, "candidates": 4, "written": 0, "errors": 4}
    assert hc.evaluate_recorder_failure_rate(counters, "candidates") is None


def test_the_minimum_attempted_count_fires():
    """Exactly at the floor (5), all erroring, must fire."""
    counters = {"population": 5, "candidates": 5, "written": 0, "errors": 5}
    flag = hc.evaluate_recorder_failure_rate(counters, "candidates")
    assert flag is not None


def test_population_query_failure_fires_regardless_of_the_attempted_floor():
    """The run never reached its candidate loop at all (candidates=0) but logged an error —
    unambiguous: there is no partial-failure population to reason about, so the minimum-
    attempted floor (built to protect against tiny-sample noise) does not apply here."""
    counters = {"population": 0, "candidates": 0, "written": 0, "errors": 1}
    flag = hc.evaluate_recorder_failure_rate(counters, "candidates")
    assert flag is not None
    assert flag["kind"] == "no_candidates_reached"


def test_the_key_name_is_not_assumed_to_be_candidates():
    """live_fill_counterfactuals uses 'arms_considered', not 'candidates' — the right key
    must be read correctly (this is why the caller passes it explicitly rather than the
    function guessing)."""
    counters = {"population": 3, "fills_considered": 3, "arms_considered": 18,
                "written": 0, "errors": 18}
    flag = hc.evaluate_recorder_failure_rate(counters, "arms_considered")
    assert flag is not None and flag["attempted"] == 18


def test_a_wrong_or_absent_attempted_key_still_fails_loud_not_silent():
    """If a future caller ever passes the wrong key name (absent from this recorder's
    counters, reading as 0-attempted) while real errors exist, this must NOT go silent —
    it degrades to the unambiguous 'no_candidates_reached' shape rather than swallowing a
    real failure. Erring toward firing (with a slightly less precise label) is the safe
    failure mode for a guard whose whole purpose is not missing things."""
    counters = {"population": 3, "fills_considered": 3, "arms_considered": 18,
                "written": 0, "errors": 18}
    flag = hc.evaluate_recorder_failure_rate(counters, "candidates")
    assert flag is not None


def test_missing_errors_key_defaults_to_zero_not_a_crash():
    counters = {"population": 10, "candidates": 10, "written": 10}
    assert hc.evaluate_recorder_failure_rate(counters, "candidates") is None


def test_a_pending_dominated_batch_with_a_few_unrelated_errors_stays_silent():
    """16 arms, 14 legitimately still pending (unresolved gap, waiting on more sessions), 2
    unrelated errors: 'wrote nothing' here is explained by pending, not by errors eating
    everything — the nothing_produced branch must not fire on this."""
    counters = {"population": 2, "fills_considered": 2, "arms_considered": 16,
                "written": 0, "pending": 14, "errors": 2}
    assert hc.evaluate_recorder_failure_rate(counters, "arms_considered") is None


def test_a_fill_level_error_that_eats_a_whole_batch_fires_even_at_a_low_arm_rate():
    """live_fill_counterfactuals counts `errors` per FILL (one exception aborts every arm for
    that fill) while `arms_considered` counts per ARM — several arms per fill. A helper called
    once per fill, before the arm loop starts (e.g. a dropped column tonight's bug's shape),
    raises once per fill and gives a LOW arms-level rate (2/16 = 12.5%) that the plain rate rule
    would wave through even though it ate the entire batch: 0 written, 0 pending. This is the
    coverage gap the granularity-independent branch exists to close."""
    counters = {"population": 2, "fills_considered": 2, "arms_considered": 16,
                "written": 0, "pending": 0, "errors": 2}
    flag = hc.evaluate_recorder_failure_rate(counters, "arms_considered")
    assert flag is not None
    assert flag["kind"] == "nothing_produced"


# ── check_recorder_failure_rate: the side-effecting wrapper ──────────────────────────────────


def _wire(monkeypatch):
    logged, notified = [], []

    async def _log(event_type, summary, detail=""):
        logged.append((event_type, summary, detail))
    monkeypatch.setattr(hc, "log_audit_event", _log)

    import core.notifications as notifications

    async def _notify(job_name, error):
        notified.append((job_name, error))
    monkeypatch.setattr(notifications, "notify_job_failure", _notify)
    return logged, notified


def test_fires_writes_an_audit_row_and_notifies(monkeypatch):
    logged, notified = _wire(monkeypatch)
    counters = {"population": 95, "candidates": 95, "written": 0, "errors": 95}
    fired = asyncio.run(hc.check_recorder_failure_rate(
        "sustain_reject_replay", counters, "candidates"))
    assert fired is True
    assert len(logged) == 1 and logged[0][0] == "recorder_failure_rate"
    assert "95" in logged[0][1] and "sustain_reject_replay" in logged[0][1]
    assert len(notified) == 1
    assert notified[0][0] == "sustain_reject_replay"
    assert "95" in notified[0][1]
    # 2026-07-05 lesson (scheduler.py _check_nightly_silent_errors): notify_job_failure wraps
    # its `error` arg in bare Markdown `_..._`. The job name (with its own underscores) must
    # NOT be inside that wrapped body, or an odd underscore count 400s the Telegram send and
    # the whole alert is silently dropped by notify_owner's own try/except.
    assert "_" not in notified[0][1]


def test_gap_near_miss_replay_job_name_does_not_break_the_telegram_wrapper(monkeypatch):
    """gap_near_miss_replay has 3 underscores in its own name — combined with the `_..._`
    Markdown wrapper that would be 5 (odd, unbalanced) if the job name ever leaked into the
    wrapped body. Regression pin for the exact job name that would have 400'd."""
    _logged, notified = _wire(monkeypatch)
    counters = {"population": 40, "candidates": 40, "written": 0, "errors": 40}
    fired = asyncio.run(hc.check_recorder_failure_rate(
        "gap_near_miss_replay", counters, "candidates"))
    assert fired is True
    assert "_" not in notified[0][1]


def test_nothing_produced_message_is_also_underscore_free(monkeypatch):
    _logged, notified = _wire(monkeypatch)
    counters = {"population": 2, "fills_considered": 2, "arms_considered": 16,
                "written": 0, "pending": 0, "errors": 2}
    fired = asyncio.run(hc.check_recorder_failure_rate(
        "live_fill_counterfactuals", counters, "arms_considered"))
    assert fired is True
    assert "_" not in notified[0][1]
    assert "2" in notified[0][1] and "16" in notified[0][1]


def test_healthy_run_is_silent_no_audit_row_no_notify(monkeypatch):
    logged, notified = _wire(monkeypatch)
    counters = {"population": 40, "candidates": 40, "written": 38, "errors": 1}
    fired = asyncio.run(hc.check_recorder_failure_rate(
        "sustain_reject_replay", counters, "candidates"))
    assert fired is False
    assert logged == [] and notified == []


def test_never_raises_even_if_the_audit_write_breaks(monkeypatch):
    """A health guard that dies silently is the failure it exists to prevent."""
    async def _boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(hc, "log_audit_event", _boom)
    counters = {"population": 95, "candidates": 95, "written": 0, "errors": 95}
    fired = asyncio.run(hc.check_recorder_failure_rate(
        "sustain_reject_replay", counters, "candidates"))
    assert fired is False  # swallowed, not raised


# ── wiring: every one of the four nightly recorders must actually call this ──────────────────


def test_all_four_recorder_jobs_call_the_check():
    sched = open("agents/market_intelligence/scheduler.py").read()
    for job_fn, job_name in [
        ("_live_fill_counterfactuals_job", "live_fill_counterfactuals"),
        ("_sustain_reject_replay_job", "sustain_reject_replay"),
        ("_gap_near_miss_replay_job", "gap_near_miss_replay"),
        ("_lowcap_lane_replay_job", "lowcap_lane_replay"),
    ]:
        i = sched.index(f"async def {job_fn}")
        j = sched.index("\nasync def ", i + 10)
        block = sched[i:j]
        assert "check_recorder_failure_rate" in block, f"{job_fn} does not call the check"
        assert f'"{job_name}"' in block


def test_live_fill_counterfactuals_job_uses_the_arms_considered_key():
    """The one recorder whose attempted-work counter is NOT 'candidates' — pinning this
    guards against a copy-paste that silently defaults every job to the wrong key."""
    sched = open("agents/market_intelligence/scheduler.py").read()
    i = sched.index("async def _live_fill_counterfactuals_job")
    j = sched.index("\nasync def ", i + 10)
    block = sched[i:j]
    assert 'attempted_key="arms_considered"' in block


def test_the_other_three_jobs_use_the_candidates_key():
    sched = open("agents/market_intelligence/scheduler.py").read()
    for job_fn in ["_sustain_reject_replay_job", "_gap_near_miss_replay_job",
                   "_lowcap_lane_replay_job"]:
        i = sched.index(f"async def {job_fn}")
        j = sched.index("\nasync def ", i + 10)
        block = sched[i:j]
        assert 'attempted_key="candidates"' in block, f"{job_fn} uses the wrong key"


def test_the_check_reuses_notify_job_failure_not_a_new_alert_channel():
    """Extend the established terminal/actionable channel — do not invent a second one."""
    import inspect
    src = inspect.getsource(hc.check_recorder_failure_rate)
    assert "notify_job_failure" in src
    assert "log_audit_event" in src
