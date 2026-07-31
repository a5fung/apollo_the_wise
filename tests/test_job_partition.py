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
    se = _FakeScheduler(_ALL)
    sched._apply_role_partition(se, "execution")
    si = _FakeScheduler(_ALL)
    sched._apply_role_partition(si, "intelligence")
    assert se.ids() | si.ids() == _ALL
    assert se.ids() & si.ids() == set()


def test_fallback_fill_checkers_are_execution_owned():
    # Regression for the 2026-06-13 W2 audit catch: the check_fills_* fallback
    # fill-pollers call broker.order_manager.check_fills (Alpaca). They MUST be
    # execution-owned, or the split drops the broker fallback from execution AND
    # hands it to the credential-less intelligence service. They derive from the
    # _FILL_CHECK_TIMES SSoT shared with registration, so a new fire time can't
    # register without joining the execution set.
    assert sched._CHECK_FILLS_JOB_IDS, "fallback fill-check ids must be non-empty"
    assert sched._CHECK_FILLS_JOB_IDS <= sched.EXECUTION_OWNED_JOB_IDS
    for jid in sched._CHECK_FILLS_JOB_IDS:
        assert sched._job_belongs_to_role(jid, "execution")
        assert not sched._job_belongs_to_role(jid, "intelligence")


def test_unclassified_job_fails_loud_in_split_roles():
    # The omission class the 6/13 audit caught: a NEW execution job registered
    # but added to NEITHER manifest would silently route to intelligence. The
    # omission guard must refuse boot in BOTH split roles (but NOT combined,
    # which can never break production).
    rogue = _ALL | {"brand_new_unclassified_job"}
    for role in ("execution", "intelligence"):
        s = _FakeScheduler(rogue)
        with pytest.raises(RuntimeError, match="unclassified registered jobs"):
            sched._apply_role_partition(s, role)
    # combined never fails on an unclassified id (no new prod failure mode).
    s = _FakeScheduler(rogue)
    out = sched._apply_role_partition(s, "combined")
    assert out["removed"] == []
    assert s.ids() == rogue


def test_manifests_are_disjoint():
    assert sched.EXECUTION_OWNED_JOB_IDS.isdisjoint(sched.INTELLIGENCE_OWNED_JOB_IDS)


def test_stale_execution_entry_fails_loud_in_both_split_roles():
    # An execution-owned id that is NOT registered (a typo/rename that left the
    # partition entry stale) must refuse boot in BOTH split roles (#279 — was
    # execution-only), as loudly as an unpartitioned job: in execution it would
    # silently DROP a trade/safeguard job; in intelligence it's a dangling
    # manifest entry that must not wait for the next execution deploy to surface.
    partial = _ALL - {"morning_stop_refresh"}
    for role in ("execution", "intelligence"):
        s = _FakeScheduler(partial)
        with pytest.raises(RuntimeError,
                           match="expected execution jobs not registered"):
            sched._apply_role_partition(s, role)
    # combined stays a strict no-op — never a new production failure mode.
    s = _FakeScheduler(partial)
    out = sched._apply_role_partition(s, "combined")
    assert out["removed"] == []
    assert s.ids() == partial


def test_intelligence_leak_guard_fires(monkeypatch):
    # Simulate a buggy belongs-to-role that lets an execution job survive in
    # intelligence — the leak guard must catch it and refuse boot.
    monkeypatch.setattr(sched, "_job_belongs_to_role", lambda jid, role: True)
    s = _FakeScheduler(_ALL)
    with pytest.raises(RuntimeError, match="execution-owned jobs survived"):
        sched._apply_role_partition(s, "intelligence")


# ─── The gap the 2026-07-31 boot failure exposed ─────────────────────────────
# Every test above feeds the guard a SYNTHETIC job set, so the whole file stayed
# green while two really-registered jobs (model_resolution_refresh,
# judge_eval_divergence_check) were in NEITHER manifest — apollo-market then
# refused to boot in production. The guard was right; nothing tested it against
# the REAL registration. Static parsing can't close this either: only 61 of the
# 90 ids are literal `id="..."` kwargs, the rest come from constants and loops —
# and model_resolution_refresh was one of the 29 a source scan misses.

class _CapturingScheduler:
    """Stands in for AsyncIOScheduler: records what start_scheduler registers."""
    def __init__(self, *a, **k):
        self._jobs = []

    def add_job(self, func, trigger=None, *a, id=None, **k):
        self._jobs.append(_FakeJob(id))

    def get_jobs(self):
        return list(self._jobs)

    def remove_job(self, jid):
        self._jobs = [j for j in self._jobs if j.id != jid]

    def start(self):
        pass

    def shutdown(self, *a, **k):
        pass


def _really_registered_job_ids(monkeypatch) -> set:
    """The job ids start_scheduler ACTUALLY registers, captured at the moment
    the partition guard runs — i.e. exactly the set the guard sees at boot.

    Read at partition time, not after start(), because order_status_reconcile_boot
    is registered AFTER the partition pass on purpose (it is conditional).
    """
    seen = {}
    real_partition = sched._apply_role_partition

    def _spy(scheduler, role):
        seen["ids"] = {j.id for j in scheduler.get_jobs()}
        return real_partition(scheduler, role)

    monkeypatch.setattr(sched, "AsyncIOScheduler", _CapturingScheduler)
    monkeypatch.setattr(sched, "_apply_role_partition", _spy)
    import asyncio
    asyncio.run(_start(sched))
    assert seen.get("ids"), "start_scheduler registered nothing — the spy never ran"
    return seen["ids"]


async def _start(mod):
    # inside a loop: start_scheduler fires a create_task for the stale-run reaper
    mod.start_scheduler()


def test_every_REALLY_registered_job_is_classified(monkeypatch):
    """The one that would have caught the 2026-07-31 outage.

    A registered-but-unclassified job silently routes to intelligence (the
    check_fills omission class), so the guard refuses to boot — meaning this is
    not a style rule: an unclassified job takes the market agent DOWN.
    """
    registered = _really_registered_job_ids(monkeypatch)
    assert len(registered) > 80, f"only {len(registered)} jobs captured — spy is wrong"
    unclassified = registered - sched.EXECUTION_OWNED_JOB_IDS - sched.INTELLIGENCE_OWNED_JOB_IDS
    assert not unclassified, (
        f"registered but in NEITHER manifest: {sorted(unclassified)} — apollo-market "
        f"and apollo-execution will BOTH refuse to boot. Classify each in "
        f"EXECUTION_OWNED_JOB_IDS or INTELLIGENCE_OWNED_JOB_IDS."
    )


def test_no_manifest_entry_is_a_ghost(monkeypatch):
    """The other direction: an id in a manifest that nothing registers any more.

    The boot guard only checks this for the EXECUTION set, so a renamed or
    deleted intelligence job leaves a ghost entry that nothing catches — and the
    next reader trusts the manifest as the job list.
    """
    registered = _really_registered_job_ids(monkeypatch)
    allowed_absent = {
        # registered AFTER the partition pass, conditionally — by design
        "order_status_reconcile_boot",
        # DELIBERATELY unregistered, parked for #297 to reclaim (see db.py:8729 —
        # the Family-B lifecycle writers; the board's last reader was repointed to
        # Family-A). Kept in the manifest on purpose, so they are not ghosts.
        "anticipation_readiness", "anticipation_3b",
    }
    ghosts = (sched.EXECUTION_OWNED_JOB_IDS | sched.INTELLIGENCE_OWNED_JOB_IDS) - registered - allowed_absent
    assert not ghosts, (
        f"manifest lists job(s) nothing registers: {sorted(ghosts)} — either the job was "
        f"renamed/deleted and the entry went stale, or it is parked on purpose (then add it "
        f"to allowed_absent WITH the reason)."
    )
