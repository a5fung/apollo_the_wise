"""#256 W2 — scheduler job partition (2026-06-13).

The partition decides which jobs each split service runs. A bug here drops a
stop-refresh or runs a broker job in the intelligence service — so the removal
pass fails LOUD in both directions. combined must stay byte-identical (no-op).
"""
import pytest

from agents.market_intelligence import scheduler as sched


class _FakeJob:
    def __init__(self, jid):
        self.id = jid


class _FakeScheduler:
    def __init__(self, ids):
        self._jobs = {i: _FakeJob(i) for i in ids}

    def get_jobs(self):
        return list(self._jobs.values())

    def remove_job(self, jid):
        del self._jobs[jid]

    def ids(self):
        return set(self._jobs)


# A realistic mix: all execution-owned ids + a few intelligence ids.
_INTEL = {"ep_scan", "ep_scan_open", "theme_synthesis", "morning_briefing",
          "judge_delta_digest", "9m_ep_scan", "hud_refresh"}
_ALL = set(sched.EXECUTION_OWNED_JOB_IDS) | _INTEL


def test_combined_is_noop():
    s = _FakeScheduler(_ALL)
    out = sched._apply_role_partition(s, "combined")
    assert s.ids() == _ALL  # nothing removed — byte-identical
    assert out["removed"] == []


def test_execution_keeps_only_owned():
    s = _FakeScheduler(_ALL)
    sched._apply_role_partition(s, "execution")
    assert s.ids() == set(sched.EXECUTION_OWNED_JOB_IDS)
    assert _INTEL.isdisjoint(s.ids())


def test_intelligence_drops_all_execution_jobs():
    s = _FakeScheduler(_ALL)
    sched._apply_role_partition(s, "intelligence")
    assert s.ids() == _INTEL
    assert set(sched.EXECUTION_OWNED_JOB_IDS).isdisjoint(s.ids())


def test_partition_is_a_clean_disjoint_cover():
    # exec ∪ intel == all, exec ∩ intel == ∅ over the realistic set
    se = _FakeScheduler(_ALL); sched._apply_role_partition(se, "execution")
    si = _FakeScheduler(_ALL); sched._apply_role_partition(si, "intelligence")
    assert se.ids() | si.ids() == _ALL
    assert se.ids() & si.ids() == set()


def test_execution_missing_expected_job_fails_loud():
    # An execution-owned id is NOT registered (a typo/rename) → must refuse boot
    # rather than silently drop the trade/safeguard job.
    partial = _ALL - {"morning_stop_refresh"}
    s = _FakeScheduler(partial)
    with pytest.raises(RuntimeError, match="expected execution jobs not registered"):
        sched._apply_role_partition(s, "execution")


def test_intelligence_leak_guard_fires(monkeypatch):
    # Simulate a buggy belongs-to-role that lets an execution job survive in
    # intelligence — the leak guard must catch it and refuse boot.
    monkeypatch.setattr(sched, "_job_belongs_to_role", lambda jid, role: True)
    s = _FakeScheduler(_ALL)
    with pytest.raises(RuntimeError, match="execution-owned jobs survived"):
        sched._apply_role_partition(s, "intelligence")
