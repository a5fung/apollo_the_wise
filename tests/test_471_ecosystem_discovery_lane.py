"""#471 — ADR 0032 Phase 3: the ecosystem auto-discovery + auto-promote/veto lane.

The task's DoD, quoted: "the fixture replay is green; a SYNTHETIC unassigned cluster
demonstrably FIRES the veto alert; and a cluster with no veto is promoted at grace-end.
WOULD-FAIL-IF: the synthetic cluster produces no alert row, or a vetoed cluster
promotes anyway."

Clause 1 (the Phase-2 fixture replay) lives in tests/test_theme_subtheme_routing.py and
is not re-proven here. Clauses 2 + 3 are the two synthetic end-to-end tests in section
H below; everything else pins the pieces they stand on.

How the DB is stood in for: `agents/market_intelligence/db.py`'s Phase-3 accessors are
replaced by ONE in-memory `_FakeStore` whose methods mirror each accessor's SQL
predicate (the status guards included). The SQL text of the three status-guarded
statements is pinned separately (section G) because a fake cannot execute it.
No network: the Sonnet proposer is injected; Telegram is a recording stub.

Every discriminating test names the MUTATION that turns it red in its docstring.
"""
from __future__ import annotations

import inspect
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from agents.market_intelligence import db as dbmod
from agents.market_intelligence import ecosystem_discovery as ed
from agents.market_intelligence import theme_ecosystems as te
from agents.market_intelligence.ecosystem_discovery import (
    COOLDOWN_DAYS, GRACE_HOURS, MAX_LLM_CLUSTERS_PER_RUN, RESIGHT_MIN_DAYS,
    SUSTAIN_MIN_AGE_DAYS, VETO_COMMAND, cluster_age_days, cluster_unassigned_themes,
    format_veto_alert, render_veto_result, run_ecosystem_discovery,
    sweep_ecosystem_grace, validate_proposal, veto_ecosystem,
)
from agents.market_intelligence.theme_ecosystems import E_UNASSIGNED

_ET = ZoneInfo("America/New_York")
REPO = Path(__file__).resolve().parent.parent

# Sunday 2026-09-13 09:30 ET — the weekly slot.
T0 = datetime(2026, 9, 13, 9, 30, tzinfo=_ET)
DAY = timedelta(days=1)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures — the in-memory store + the synthetic cluster
# ═══════════════════════════════════════════════════════════════════════════

def _theme(name, tickers, assigned_at=T0 - 15 * DAY, e_code=E_UNASSIGNED, stage="Nascent"):
    return {"name": name, "tickers": list(tickers), "description": f"{name} thesis",
            "stage": stage, "_assigned_at": assigned_at, "_e_code": e_code}


def synthetic_cluster():
    """Three unassigned themes chained by shared tickers, 15 days old — exactly the
    design's §2.5 acceptance seed (overlapping tickers, assigned_at backdated 15d)."""
    return [
        _theme("Drone Airframe Makers", ["AAA", "BBB", "CCC"]),
        _theme("Unmanned Systems Sensors", ["CCC", "DDD"]),
        _theme("UAS Defense Integrators", ["DDD", "EEE", "FFF"]),
    ]


class _FakeStore:
    """Mirrors the Phase-3 db.py accessors over dicts. Each method's predicate is
    the SQL's WHERE clause, so the state machine is exercised as production runs it."""

    def __init__(self, themes: list[dict]):
        self.themes = themes
        self.mapping = {t["name"]: {"theme_name": t["name"], "e_code": t["_e_code"],
                                    "method": "keyword", "assigned_at": t["_assigned_at"]}
                        for t in themes if t.get("_e_code") is not None}
        self.proposals: dict[int, dict] = {}
        self.dynamic: dict[str, dict] = {}
        self.audit: list[tuple[str, str, str]] = []
        self._seq = 0
        self.dynamic_inserts = 0

    # ── reads ──
    async def get_active_themes(self, stale_after_days: int = 7):
        return [dict(t) for t in self.themes if t.get("stage") != "Retired"]

    async def get_theme_ecosystem_rows(self):
        return [dict(r) for r in self.mapping.values()]

    async def get_ecosystem_proposals(self, statuses):
        return [dict(p) for p in self.proposals.values() if p["status"] in statuses]

    async def get_dynamic_ecosystems(self, active_only=True):
        return [dict(d) for d in self.dynamic.values()
                if not active_only or d["status"] == "active"]

    async def get_theme_names_in_ecosystem(self, e_code):
        return [n for n, r in self.mapping.items() if r["e_code"] == e_code]

    async def get_all_theme_ecosystems(self):
        return {n: r["e_code"] for n, r in self.mapping.items()}

    # ── writes ──
    async def insert_ecosystem_proposal(self, *, e_code, name, description, keyword_stems,
                                        exemplars, member_themes, evidence, status, sighted_at):
        self._seq += 1
        self.proposals[self._seq] = {
            "id": self._seq, "e_code": e_code, "name": name, "description": description,
            "keyword_stems": list(keyword_stems), "exemplars": list(exemplars),
            "member_themes": list(member_themes), "evidence": evidence, "status": status,
            "first_sighted_at": sighted_at, "last_sighted_at": sighted_at, "sightings": 1,
            "pending_at": None, "grace_ends_at": None, "decided_at": None,
            "cooldown_until": None, "veto_snapshot": None,
        }
        return self._seq

    async def touch_ecosystem_proposal_sighting(self, proposal_id, member_themes, sighted_at):
        p = self.proposals[proposal_id]
        p["last_sighted_at"] = sighted_at
        p["sightings"] += 1
        p["member_themes"] = list(member_themes)

    async def mark_ecosystem_proposal_pending(self, proposal_id, *, e_code, name, description,
                                              keyword_stems, exemplars, member_themes, evidence,
                                              pending_at, grace_ends_at):
        p = self.proposals[proposal_id]
        if p["status"] != "sighted":          # WHERE id=$1 AND status='sighted'
            return False
        p.update(status="pending", e_code=e_code, name=name, description=description,
                 keyword_stems=list(keyword_stems), exemplars=list(exemplars),
                 member_themes=list(member_themes), evidence=evidence,
                 pending_at=pending_at, grace_ends_at=grace_ends_at,
                 last_sighted_at=pending_at, sightings=p["sightings"] + 1)
        return True

    async def claim_due_ecosystem_proposals(self, now):
        out = []
        for p in self.proposals.values():
            # WHERE status='pending' AND grace_ends_at <= $1
            if p["status"] == "pending" and p["grace_ends_at"] <= now:
                p["status"] = "live"
                p["decided_at"] = now
                out.append(dict(p))
        return out

    async def mark_ecosystem_proposal_vetoed(self, proposal_id, *, now, cooldown_until,
                                             snapshot, new_status="vetoed"):
        p = self.proposals[proposal_id]
        from_status = "pending" if new_status == "vetoed" else "live"
        if p["status"] != from_status:        # WHERE id=$1 AND status=$6
            return False
        p.update(status=new_status, decided_at=now, cooldown_until=cooldown_until,
                 veto_snapshot=snapshot)
        return True

    async def insert_dynamic_ecosystem(self, *, e_code, name, description, keyword_stems,
                                       exemplars, source, proposal_id, created_at):
        self.dynamic_inserts += 1
        if e_code in self.dynamic:            # ON CONFLICT (e_code) DO NOTHING
            return
        self.dynamic[e_code] = {"e_code": e_code, "name": name, "description": description,
                                "keyword_stems": list(keyword_stems),
                                "exemplars": list(exemplars), "source": source,
                                "status": "active", "proposal_id": proposal_id,
                                "created_at": created_at, "retired_at": None}

    async def retire_dynamic_ecosystem(self, e_code, retired_at):
        d = self.dynamic.get(e_code)
        if not d or d["status"] != "active":
            return False
        d["status"] = "retired"
        d["retired_at"] = retired_at
        return True

    async def remap_theme_ecosystems(self, theme_names, e_code, method):
        n = 0
        for name in theme_names:
            r = self.mapping.get(name)
            if r is not None:                  # WHERE theme_name = ANY($1)
                r["e_code"] = e_code
                r["method"] = method
                n += 1
        return n

    async def log_audit_event(self, event_type, summary, detail=""):
        self.audit.append((event_type, summary, detail))

    # ── helpers for assertions ──
    def events(self, name):
        return [a for a in self.audit if a[0] == name]

    def only_proposal(self):
        assert len(self.proposals) == 1, self.proposals
        return next(iter(self.proposals.values()))


_ACCESSORS = (
    "get_active_themes", "get_theme_ecosystem_rows", "get_ecosystem_proposals",
    "get_dynamic_ecosystems", "get_theme_names_in_ecosystem", "get_all_theme_ecosystems",
    "insert_ecosystem_proposal", "touch_ecosystem_proposal_sighting",
    "mark_ecosystem_proposal_pending", "claim_due_ecosystem_proposals",
    "mark_ecosystem_proposal_vetoed", "insert_dynamic_ecosystem",
    "retire_dynamic_ecosystem", "remap_theme_ecosystems", "log_audit_event",
)


@pytest.fixture(autouse=True)
def _fresh_caches():
    te.reset_taxonomy_cache()
    yield
    te.reset_taxonomy_cache()


@pytest.fixture
def store(monkeypatch):
    s = _FakeStore(synthetic_cluster())
    for name in _ACCESSORS:
        monkeypatch.setattr(dbmod, name, getattr(s, name))
    return s


@pytest.fixture
def sent(monkeypatch):
    """Recording Telegram stub — the veto alert + the promote confirm land here."""
    rec = AsyncMock(return_value=True)
    monkeypatch.setattr(ed, "_send_html", rec)
    return rec


def _proposal_for(cluster, code="E-DRONE"):
    return {"e_code": code, "name": "Drones & unmanned systems",
            "description": "Airframes, sensors and integrators for unmanned aircraft.",
            "keyword_stems": ["drone", "unmanned", "uas"], "exemplars": ["CCC", "DDD"],
            "member_themes": [t["name"] for t in cluster],
            "evidence": "All three theses are the same UAS build-out."}


@pytest.fixture
def proposer():
    """Injected stand-in for the Sonnet call — records every invocation."""
    calls = []

    async def _p(cluster, taxonomy):
        calls.append((cluster, taxonomy))
        return _proposal_for(cluster)

    _p.calls = calls
    return _p


async def _two_sightings(store, proposer, *, second_at=T0 + RESIGHT_MIN_DAYS * DAY):
    """Pass 1 (sighted) then pass 2 (pending). Returns the pass-2 result."""
    await run_ecosystem_discovery(now=T0, proposer=proposer)
    return await run_ecosystem_discovery(now=second_at, proposer=proposer)


# ═══════════════════════════════════════════════════════════════════════════
# A. Deterministic pre-cluster — pure
# ═══════════════════════════════════════════════════════════════════════════

class TestClustering:
    def test_shared_ticker_chains_into_one_cluster(self):
        """Mutation: drop the ticker edge → three singletons, no cluster."""
        out = cluster_unassigned_themes(synthetic_cluster())
        assert len(out) == 1 and len(out[0]) == 3

    def test_shared_name_token_links_without_ticker_overlap(self):
        """Mutation: drop the name-token edge → no cluster."""
        themes = [_theme("Drone Airframes", ["A"]), _theme("Drone Sensors", ["B"]),
                  _theme("Drone Software", ["C"])]
        out = cluster_unassigned_themes(themes)
        assert len(out) == 1 and len(out[0]) == 3

    def test_stopword_or_short_token_does_not_link(self):
        """Mutation: empty _NAME_STOPWORDS (or NAME_TOKEN_MIN_LEN=1) → these three
        'platforms' / 'AI' names would cluster on noise."""
        themes = [_theme("AI Data Platforms", ["A"]), _theme("Insurance Platforms", ["B"]),
                  _theme("AI Retail Platforms", ["C"])]
        assert cluster_unassigned_themes(themes) == []

    def test_pairs_never_form_a_cluster(self):
        """Mutation: MIN_CLUSTER_THEMES=2 → the pair reaches the LLM."""
        themes = [_theme("Drone A", ["A", "B"]), _theme("Drone B", ["B", "C"]),
                  _theme("Unrelated Banks", ["ZZZ"])]
        assert cluster_unassigned_themes(themes) == []

    def test_disjoint_components_are_separate_and_ordered_by_size(self):
        big = [_theme(f"Drone {i}", [f"D{i}", f"D{i + 1}"]) for i in range(4)]
        small = [_theme(f"Solar {i}", [f"S{i}", f"S{i + 1}"]) for i in range(3)]
        out = cluster_unassigned_themes(small + big)
        assert [len(c) for c in out] == [4, 3]

    def test_cluster_age_is_days_since_earliest_assigned_at(self):
        """Mutation: use max() instead of min() → 3, not 15."""
        # run_ecosystem_discovery attaches `assigned_at` from the mapping row —
        # the pure helper reads that key, so build the substrate shape directly.
        c = [{"name": "a", "assigned_at": T0 - 15 * DAY},
             {"name": "b", "assigned_at": T0 - 3 * DAY},
             {"name": "c", "assigned_at": None}]
        assert cluster_age_days(c, T0) == 15
        assert cluster_age_days([{"name": "x", "assigned_at": None}], T0) == 0


class TestValidateProposal:
    def _ok(self):
        return _proposal_for(synthetic_cluster()) | {"decision": "propose"}

    def test_valid_proposal_passes_through_normalized(self):
        out = validate_proposal(self._ok(), synthetic_cluster(), te.get_ecosystems())
        assert out["e_code"] == "E-DRONE" and len(out["member_themes"]) == 3
        assert out["exemplars"] == ["CCC", "DDD"]

    @pytest.mark.parametrize("mutation", [
        {"decision": "abstain"},
        {"e_code": "DRONE"},                    # missing E- prefix
        {"e_code": "E-CYBR"},                   # collides with a YAML bucket
        {"e_code": E_UNASSIGNED},
        {"name": ""},
        {"member_themes": ["Drone Airframe Makers", "Unmanned Systems Sensors"]},   # <3
        {"member_themes": ["Drone Airframe Makers", "Not In Cluster", "Also Not"]},
        {"keyword_stems": ["drone", "uas"]},    # <3 stems
    ], ids=["abstain", "bad-code", "yaml-collision", "unassigned-code", "no-name",
            "two-members", "members-outside-cluster", "two-stems"])
    def test_each_invalid_shape_is_rejected(self, mutation):
        """Mutation: remove the matching check in validate_proposal → that case passes."""
        data = self._ok() | mutation
        assert validate_proposal(data, synthetic_cluster(), te.get_ecosystems()) is None

    def test_collision_with_a_live_dynamic_bucket_is_rejected(self):
        te._DYNAMIC_CACHE = [{"e_code": "E-DRONE", "name": "x", "description": "",
                              "keyword_stems": [], "exemplars": [], "dynamic": True,
                              "created_at": T0}]
        assert validate_proposal(self._ok(), synthetic_cluster(), te.get_ecosystems()) is None


# ═══════════════════════════════════════════════════════════════════════════
# B. The weekly pass — state machine
# ═══════════════════════════════════════════════════════════════════════════

class TestWeeklyPass:
    @pytest.mark.asyncio
    async def test_first_sighting_records_sighted_no_llm_no_alert(self, store, sent, proposer):
        """Mutation: call the proposer on the first sighting → calls == 1."""
        out = await run_ecosystem_discovery(now=T0, proposer=proposer)
        p = store.only_proposal()
        assert p["status"] == "sighted" and p["e_code"] is None
        assert sorted(p["member_themes"]) == sorted(t["name"] for t in synthetic_cluster())
        assert out["substrate_n"] == 3 and out["clusters"] == 1 and out["sighted"] == [1]
        assert proposer.calls == [] and sent.await_count == 0
        assert store.events("ecosystem_cluster_sighted")
        assert store.events("ecosystem_discovery_ran")

    @pytest.mark.asyncio
    async def test_resighting_too_soon_stays_sighted(self, store, sent, proposer):
        """Mutation: RESIGHT_MIN_DAYS=0 → goes pending on day 3."""
        await _two_sightings(store, proposer, second_at=T0 + 3 * DAY)
        p = store.only_proposal()
        assert p["status"] == "sighted" and p["sightings"] == 2
        assert proposer.calls == [] and sent.await_count == 0

    @pytest.mark.asyncio
    async def test_young_cluster_never_goes_pending(self, store, sent, proposer):
        """Mutation: SUSTAIN_MIN_AGE_DAYS=0 → a 5-day-old cluster goes pending."""
        for t in store.themes:
            t["_assigned_at"] = T0 - 5 * DAY
        for r in store.mapping.values():
            r["assigned_at"] = T0 - 5 * DAY
        await _two_sightings(store, proposer)
        assert store.only_proposal()["status"] == "sighted"
        assert proposer.calls == []

    @pytest.mark.asyncio
    async def test_qualifying_resighting_goes_pending_and_fires_the_veto_alert(
            self, store, sent, proposer):
        """DoD clause 2 at unit level. Mutation A: delete the `_send_html(...)` call in
        run_ecosystem_discovery → no alert. Mutation B: delete the
        `mark_ecosystem_proposal_pending` call → status stays sighted."""
        out = await _two_sightings(store, proposer)
        p = store.only_proposal()
        assert p["status"] == "pending" and p["e_code"] == "E-DRONE"
        assert p["grace_ends_at"] == T0 + RESIGHT_MIN_DAYS * DAY + timedelta(hours=GRACE_HOURS)
        assert out["pending"] == ["E-DRONE"]
        assert len(proposer.calls) == 1
        # the alert row …
        (ev,) = store.events("ecosystem_proposed_pending")
        assert "E-DRONE" in ev[1]
        # … AND the alert itself, carrying the action
        assert sent.await_count == 1
        text = sent.await_args.args[0]
        assert VETO_COMMAND in text and "E-DRONE" in text and "48h" in text

    @pytest.mark.asyncio
    async def test_alert_send_failure_is_audited_loudly(self, store, sent, proposer):
        """Mutation: drop the `if not sent:` branch → a pending row nobody was told
        about leaves no trace."""
        sent.return_value = False
        await _two_sightings(store, proposer)
        (err,) = store.events("ecosystem_promotion_error")
        assert "NOT delivered" in err[1]

    @pytest.mark.asyncio
    async def test_llm_abstain_keeps_sighted(self, store, sent, proposer):
        async def abstain(cluster, taxonomy):
            return None
        out = await _two_sightings(store, abstain)
        assert store.only_proposal()["status"] == "sighted"
        assert out["abstained"] == [1] and sent.await_count == 0

    @pytest.mark.asyncio
    async def test_llm_error_is_audited_and_keeps_sighted(self, store, sent, proposer):
        """Mutation: let the proposer exception propagate → the pass raises."""
        async def boom(cluster, taxonomy):
            raise RuntimeError("rate limited")
        out = await _two_sightings(store, boom)
        assert store.only_proposal()["status"] == "sighted"
        assert out["errors"] and store.events("ecosystem_promotion_error")
        assert store.events("ecosystem_discovery_ran")   # heartbeat survives the error

    @pytest.mark.asyncio
    async def test_llm_budget_caps_calls_per_run(self, monkeypatch, sent, proposer):
        """Mutation: MAX_LLM_CLUSTERS_PER_RUN unbounded → 3 calls."""
        themes = []
        for k in ("Drone", "Solar", "Rail"):
            themes += [_theme(f"{k} A", [f"{k}1", f"{k}2"]), _theme(f"{k} B", [f"{k}2", f"{k}3"]),
                       _theme(f"{k} C", [f"{k}3", f"{k}4"])]
        s = _FakeStore(themes)
        for name in _ACCESSORS:
            monkeypatch.setattr(dbmod, name, getattr(s, name))
        seq = iter(["E-AAA", "E-BBB", "E-CCC"])

        async def p(cluster, taxonomy):
            proposer.calls.append(cluster)
            return _proposal_for(cluster, code=next(seq))
        await run_ecosystem_discovery(now=T0, proposer=p)
        assert len(s.proposals) == 3
        await run_ecosystem_discovery(now=T0 + RESIGHT_MIN_DAYS * DAY, proposer=p)
        assert len(proposer.calls) == MAX_LLM_CLUSTERS_PER_RUN == 2
        assert sum(1 for x in s.proposals.values() if x["status"] == "pending") == 2

    @pytest.mark.asyncio
    async def test_idle_run_still_writes_the_heartbeat(self, monkeypatch, sent, proposer):
        """G8: the substrate is ~1 theme today. Mutation: early-return before the
        heartbeat when substrate < 3 → an idle Sunday is indistinguishable from a
        dead job."""
        s = _FakeStore([_theme("Life Science Tools", ["LST"])])
        for name in _ACCESSORS:
            monkeypatch.setattr(dbmod, name, getattr(s, name))
        out = await run_ecosystem_discovery(now=T0, proposer=proposer)
        assert out["substrate_n"] == 1 and out["clusters"] == 0
        (hb,) = s.events("ecosystem_discovery_ran")
        assert "substrate=1" in hb[1]

    @pytest.mark.asyncio
    async def test_mapped_themes_are_not_substrate(self, store, sent, proposer):
        """Mutation: drop the E-UNASSIGNED filter → curated themes cluster too."""
        store.mapping["Drone Airframe Makers"]["e_code"] = "E-DEF"
        out = await run_ecosystem_discovery(now=T0, proposer=proposer)
        assert out["substrate_n"] == 2 and out["clusters"] == 0

    @pytest.mark.asyncio
    async def test_substrate_read_failure_is_a_heartbeat_not_a_raise(self, store, sent,
                                                                     proposer, monkeypatch):
        monkeypatch.setattr(dbmod, "get_active_themes",
                            AsyncMock(side_effect=RuntimeError("db down")))
        out = await run_ecosystem_discovery(now=T0, proposer=proposer)
        assert out["errors"] and store.events("ecosystem_discovery_ran")


# ═══════════════════════════════════════════════════════════════════════════
# C. The grace sweep — pending → live
# ═══════════════════════════════════════════════════════════════════════════

class TestGraceSweep:
    @pytest.mark.asyncio
    async def test_sweep_before_grace_end_does_nothing(self, store, sent, proposer):
        """Mutation: claim `grace_ends_at <= now` → `<= now + 1h` → promotes early."""
        await _two_sightings(store, proposer)
        p = store.only_proposal()
        out = await sweep_ecosystem_grace(now=p["grace_ends_at"] - timedelta(minutes=1))
        assert out["promoted"] == [] and p["status"] == "pending"
        assert store.dynamic == {}

    @pytest.mark.asyncio
    async def test_sweep_at_grace_end_promotes(self, store, sent, proposer):
        """DoD clause 3 at unit level. Mutation A: skip insert_dynamic_ecosystem → no
        bucket. Mutation B: skip remap_theme_ecosystems → themes stay E-UNASSIGNED."""
        await _two_sightings(store, proposer)
        p = store.only_proposal()
        out = await sweep_ecosystem_grace(now=p["grace_ends_at"])
        assert out["promoted"] == ["E-DRONE"] and p["status"] == "live"
        d = store.dynamic["E-DRONE"]
        assert d["source"] == "auto" and d["proposal_id"] == p["id"] and d["status"] == "active"
        for t in synthetic_cluster():
            r = store.mapping[t["name"]]
            assert r["e_code"] == "E-DRONE" and r["method"] == "ecosystem_discovery"
        (ev,) = store.events("ecosystem_auto_promoted")
        assert "3 theme(s) remapped" in ev[1]
        # the loader sees it, before E-UNASSIGNED
        codes = te.get_ecosystem_codes()
        assert "E-DRONE" in codes and codes[-1] == E_UNASSIGNED
        # the confirm went out (alert + confirm = 2 sends)
        assert sent.await_count == 2 and "Ecosystem live" in sent.await_args.args[0]

    @pytest.mark.asyncio
    async def test_double_sweep_promotes_once(self, store, sent, proposer):
        """Hourly + boot catch-up can both run. Mutation: have the sweep re-read
        `live` rows too → a second bucket insert / remap / confirm."""
        await _two_sightings(store, proposer)
        p = store.only_proposal()
        first = await sweep_ecosystem_grace(now=p["grace_ends_at"])
        second = await sweep_ecosystem_grace(now=p["grace_ends_at"] + timedelta(hours=1))
        assert first["promoted"] == ["E-DRONE"] and second["promoted"] == []
        assert store.dynamic_inserts == 1 and len(store.events("ecosystem_auto_promoted")) == 1

    @pytest.mark.asyncio
    async def test_promote_failure_is_audited_not_raised(self, store, sent, proposer,
                                                         monkeypatch):
        await _two_sightings(store, proposer)
        p = store.only_proposal()
        monkeypatch.setattr(dbmod, "insert_dynamic_ecosystem",
                            AsyncMock(side_effect=RuntimeError("disk full")))
        out = await sweep_ecosystem_grace(now=p["grace_ends_at"])
        assert out["errors"] and store.events("ecosystem_promotion_error")

    @pytest.mark.asyncio
    async def test_promotion_changes_no_theme_membership(self, store, sent, proposer):
        """THE LINE pin: a promotion re-points mapping rows and nothing else — every
        theme's ticker list is byte-identical after the sweep."""
        before = {t["name"]: list(t["tickers"]) for t in store.themes}
        await _two_sightings(store, proposer)
        await sweep_ecosystem_grace(now=store.only_proposal()["grace_ends_at"])
        assert {t["name"]: list(t["tickers"]) for t in store.themes} == before


# ═══════════════════════════════════════════════════════════════════════════
# D. The veto — /vetoecosystem [E-CODE]
# ═══════════════════════════════════════════════════════════════════════════

class TestVeto:
    @pytest.mark.asyncio
    async def test_bare_veto_with_one_pending_vetoes_it(self, store, sent, proposer):
        """The one-tap. Mutation: require a code (drop the len(pending)==1 branch)."""
        await _two_sightings(store, proposer)
        now = T0 + 8 * DAY
        res = await veto_ecosystem(None, now=now)
        p = store.only_proposal()
        assert res["status"] == "vetoed" and p["status"] == "vetoed"
        assert p["cooldown_until"] == now + timedelta(days=COOLDOWN_DAYS)
        assert p["veto_snapshot"]["member_theme_count"] == 3
        assert store.events("ecosystem_vetoed")
        # themes stay unassigned
        assert all(r["e_code"] == E_UNASSIGNED for r in store.mapping.values())

    @pytest.mark.asyncio
    async def test_bare_veto_with_none_pending_is_usage(self, store):
        res = await veto_ecosystem("", now=T0)
        assert res["status"] == "none_pending"

    @pytest.mark.asyncio
    async def test_bare_veto_with_two_pending_is_ambiguous(self, store, sent, proposer):
        await _two_sightings(store, proposer)
        store.proposals[99] = dict(store.proposals[1], id=99, e_code="E-OTHER")
        res = await veto_ecosystem(None, now=T0 + 8 * DAY)
        assert res["status"] == "ambiguous" and set(res["pending"]) == {"E-DRONE", "E-OTHER"}

    @pytest.mark.asyncio
    async def test_veto_by_code_and_case_insensitive(self, store, sent, proposer):
        await _two_sightings(store, proposer)
        res = await veto_ecosystem(" e-drone ", now=T0 + 8 * DAY)
        assert res["status"] == "vetoed" and res["e_code"] == "E-DRONE"

    @pytest.mark.asyncio
    async def test_yaml_bucket_is_refused(self, store):
        """Mutation: drop the YAML check → E-CYBR falls to not_found (or worse)."""
        res = await veto_ecosystem("E-CYBR", now=T0)
        assert res["status"] == "yaml_refused"

    @pytest.mark.asyncio
    async def test_unknown_code_is_not_found(self, store):
        res = await veto_ecosystem("E-NOPE", now=T0)
        assert res["status"] == "not_found" and res["e_code"] == "E-NOPE"

    @pytest.mark.asyncio
    async def test_veto_that_races_the_sweep_loses_cleanly(self, store, sent, proposer):
        """Mutation: drop the from-status guard on mark_ecosystem_proposal_vetoed →
        a live bucket's row flips to vetoed while the bucket stays live."""
        await _two_sightings(store, proposer)
        p = store.only_proposal()
        store.proposals[99] = dict(p, id=99, e_code="E-OTHER")     # keep one pending
        await sweep_ecosystem_grace(now=p["grace_ends_at"])         # E-DRONE went live
        # simulate a stale tap that still names the now-live proposal id as pending:
        p["status"] = "pending"; store.dynamic["E-DRONE"]["status"] = "active"
        store.proposals[1]["status"] = "live"
        res = await veto_ecosystem("E-DRONE", now=p["grace_ends_at"])
        assert res["status"] == "retired"   # resolved as a live-bucket retire, not a veto

    @pytest.mark.asyncio
    async def test_retro_retire_live_auto_bucket_is_reversible(self, store, sent, proposer):
        """Reversibility (ADR: mutations audited + reversible). Mutation: skip the
        remap in _retro_retire → themes keep pointing at a retired bucket."""
        await _two_sightings(store, proposer)
        p = store.only_proposal()
        await sweep_ecosystem_grace(now=p["grace_ends_at"])
        now = p["grace_ends_at"] + 3 * DAY
        res = await veto_ecosystem("E-DRONE", now=now)
        assert res["status"] == "retired" and res["n_remapped"] == 3
        assert store.dynamic["E-DRONE"]["status"] == "retired"
        for r in store.mapping.values():
            assert r["e_code"] == E_UNASSIGNED and r["method"] == "ecosystem_retired"
        assert p["status"] == "retired" and p["cooldown_until"] == now + timedelta(days=COOLDOWN_DAYS)
        assert store.events("ecosystem_retired")
        assert "E-DRONE" not in te.get_ecosystem_codes()

    def test_render_covers_every_status(self):
        cd = T0 + 30 * DAY
        cases = [
            ({"status": "vetoed", "e_code": "E-X", "name": "n", "cooldown_until": cd,
              "member_themes": ["a"]}, "Vetoed"),
            ({"status": "retired", "e_code": "E-X", "name": "n", "n_remapped": 2,
              "cooldown_until": cd}, "Retired"),
            ({"status": "none_pending", "live_auto": ["E-Y"]}, "E-Y"),
            ({"status": "none_pending", "live_auto": []}, "Nothing is pending"),
            ({"status": "ambiguous", "pending": ["E-A", "E-B"]}, "/vetoecosystem E-B"),
            ({"status": "yaml_refused", "e_code": "E-CYBR"}, "curated"),
            ({"status": "raced", "e_code": "E-X"}, "already went live"),
            ({"status": "not_found", "e_code": "E-Q", "pending": ["E-A"], "live_auto": []},
             "E-A"),
        ]
        for res, needle in cases:
            assert needle in render_veto_result(res), res["status"]


# ═══════════════════════════════════════════════════════════════════════════
# E. Cooldown — a vetoed cluster is not re-proposed
# ═══════════════════════════════════════════════════════════════════════════

class TestCooldown:
    @pytest.mark.asyncio
    async def test_vetoed_cluster_resighted_is_skipped_during_cooldown(self, store, sent,
                                                                      proposer):
        """The second half of the WOULD-FAIL-IF. Mutation: delete the cooldown match
        block (a) in run_ecosystem_discovery → the vetoed cluster is inserted as a
        NEW sighted row and is back on the promote track."""
        await _two_sightings(store, proposer)
        await veto_ecosystem(None, now=T0 + 8 * DAY)
        out = await run_ecosystem_discovery(now=T0 + 14 * DAY, proposer=proposer)
        assert len(store.proposals) == 1                 # no new sighted row
        assert out["cooldown_skips"] == ["E-DRONE"] and out["sighted"] == []
        assert store.events("ecosystem_cooldown_skip")
        assert len(proposer.calls) == 1 and sent.await_count == 1   # nothing new fired

    @pytest.mark.asyncio
    async def test_after_cooldown_the_cluster_can_be_sighted_again(self, store, sent,
                                                                   proposer):
        await _two_sightings(store, proposer)
        await veto_ecosystem(None, now=T0 + 8 * DAY)
        out = await run_ecosystem_discovery(now=T0 + 8 * DAY + (COOLDOWN_DAYS + 1) * DAY,
                                            proposer=proposer)
        assert out["sighted"] == [2] and len(store.proposals) == 2

    @pytest.mark.asyncio
    async def test_retired_bucket_cluster_is_also_cooled(self, store, sent, proposer):
        await _two_sightings(store, proposer)
        p = store.only_proposal()
        await sweep_ecosystem_grace(now=p["grace_ends_at"])
        await veto_ecosystem("E-DRONE", now=p["grace_ends_at"] + DAY)   # retro-retire
        out = await run_ecosystem_discovery(now=p["grace_ends_at"] + 8 * DAY, proposer=proposer)
        assert out["cooldown_skips"] == ["E-DRONE"] and len(store.proposals) == 1


# ═══════════════════════════════════════════════════════════════════════════
# F. Loader — YAML ∪ dynamic, YAML wins, fail-safe
# ═══════════════════════════════════════════════════════════════════════════

class TestDynamicTaxonomy:
    def _dyn(self, code, name="Dyn"):
        return {"e_code": code, "name": name, "description": "", "keyword_stems": [],
                "exemplars": [], "dynamic": True, "created_at": T0}

    def test_dynamic_sits_before_unassigned_and_yaml_wins_on_collision(self):
        """Mutation: append after E-UNASSIGNED → codes[-1] != E-UNASSIGNED; drop the
        yaml_codes filter → E-CYBR's name becomes 'Dyn'."""
        te._DYNAMIC_CACHE = [self._dyn("E-CYBR", "Dyn"), self._dyn("E-TEST")]
        codes = te.get_ecosystem_codes()
        assert codes[-1] == E_UNASSIGNED and "E-TEST" in codes
        assert codes.count("E-CYBR") == 1
        assert te.get_ecosystem_map()["E-CYBR"]["name"] == "Cybersecurity"
        assert len(te.get_ecosystems()) == 22

    @pytest.mark.asyncio
    async def test_refresh_reads_active_rows_only(self, monkeypatch):
        rows = [{"e_code": "E-TEST", "name": "T", "status": "active", "created_at": T0}]
        monkeypatch.setattr(dbmod, "get_dynamic_ecosystems", AsyncMock(return_value=rows))
        assert await te.refresh_dynamic_taxonomy() == 1
        assert te.get_ecosystem_map()["E-TEST"]["dynamic"] is True

    @pytest.mark.asyncio
    async def test_db_down_keeps_the_previous_cache(self, monkeypatch):
        """Mutation: set _DYNAMIC_CACHE = [] in the except branch → the bucket vanishes
        from /themes for the duration of a DB hiccup."""
        te._DYNAMIC_CACHE = [self._dyn("E-TEST")]
        monkeypatch.setattr(dbmod, "get_dynamic_ecosystems",
                            AsyncMock(side_effect=RuntimeError("down")))
        assert await te.refresh_dynamic_taxonomy() == 1
        assert "E-TEST" in te.get_ecosystem_codes()

    @pytest.mark.asyncio
    async def test_load_ecosystem_assignments_refreshes_the_dynamic_cache(self, monkeypatch):
        """Every render surface funnels through this — mutation: drop the refresh call
        → an auto-promoted bucket never reaches /themes."""
        rows = [{"e_code": "E-TEST", "name": "T", "status": "active", "created_at": T0}]
        monkeypatch.setattr(dbmod, "get_dynamic_ecosystems", AsyncMock(return_value=rows))
        monkeypatch.setattr(dbmod, "get_all_theme_ecosystems", AsyncMock(return_value={"a": "E-TEST"}))
        assert await te.load_ecosystem_assignments() == {"a": "E-TEST"}
        assert "E-TEST" in te.get_ecosystem_codes()

    def test_reset_clears_the_dynamic_cache_too(self):
        te._DYNAMIC_CACHE = [self._dyn("E-TEST")]
        te.reset_taxonomy_cache()
        assert te._DYNAMIC_CACHE is None and "E-TEST" not in te.get_ecosystem_codes()

    def test_board_renders_a_dynamic_bucket_header(self):
        te._DYNAMIC_CACHE = [self._dyn("E-TEST", "Test bucket")]
        scored = [{"name": "t1", "tickers": ["A", "B", "C"], "stage": "Nascent", "comp": 90.0,
                   "delta": None}]
        rs = {k: {"rs_composite": 95.0} for k in "ABC"}
        lines = te.format_ecosystem_board(scored, [], rs, {"t1": "E-TEST"})
        assert any("E-TEST Test bucket" in ln for ln in lines)


# ═══════════════════════════════════════════════════════════════════════════
# G. Wiring pins — command (3 places), jobs, audit vocabulary, ceiling, preflight, SQL guards
# ═══════════════════════════════════════════════════════════════════════════

def _src(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def test_botcommand_registered():
    assert 'BotCommand("vetoecosystem"' in _src("channels/telegram.py")


def test_commandhandler_registered():
    src = _src("channels/telegram.py")
    start = src.index("for _cmd in (")
    end = src.index("app.add_handler(CommandHandler(_cmd", start)
    assert '"vetoecosystem"' in src[start:end]


@pytest.mark.asyncio
async def test_agent_slash_dispatch_reaches_handler():
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    fake = MagicMock()
    fake._handle_vetoecosystem = AsyncMock(return_value="rendered")
    req = MagicMock(); req.task = "/vetoecosystem E-DRONE"
    assert await MarketIntelligenceAgent._handle_slash_command(fake, req) == "rendered"
    fake._handle_vetoecosystem.assert_awaited_once_with(req)


@pytest.mark.asyncio
async def test_handler_strips_the_command_and_renders(monkeypatch):
    """Mutation: pass request.task unstripped → veto_ecosystem sees '/vetoecosystem E-DRONE'."""
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    seen = {}

    async def fake_veto(arg, *, now=None):
        seen["arg"] = arg
        return {"status": "vetoed", "e_code": "E-DRONE", "name": "n",
                "cooldown_until": T0 + 30 * DAY, "member_themes": ["a"]}
    monkeypatch.setattr(ed, "veto_ecosystem", fake_veto)
    fake = MagicMock()
    fake._ok = lambda request, *, result: result
    req = MagicMock(); req.task = "/vetoecosystem@ApolloBot  e-drone"
    out = await MarketIntelligenceAgent._handle_vetoecosystem(fake, req)
    assert seen["arg"] == "e-drone" and "Vetoed" in out
    req.task = "/vetoecosystem"
    await MarketIntelligenceAgent._handle_vetoecosystem(fake, req)
    assert seen["arg"] is None


def test_jobs_are_intelligence_owned_and_registered():
    from agents.market_intelligence import scheduler as sched
    for jid in ("ecosystem_discovery", "ecosystem_grace_sweep"):
        assert jid in sched.INTELLIGENCE_OWNED_JOB_IDS
        assert jid not in sched.EXECUTION_OWNED_JOB_IDS
    src = _src("agents/market_intelligence/scheduler.py")
    i = src.index('id="ecosystem_discovery"')
    block = src[i - 400:i]
    assert 'day_of_week="sun", hour=9, minute=30' in block, "Sunday 09:30 ET slot (design §2.1)"
    j = src.index('id="ecosystem_grace_sweep"')
    assert "CronTrigger(minute=12" in src[j - 300:j], "hourly at :12 (design §2.2)"
    assert "asyncio.create_task(_ecosystem_grace_sweep_boot())" in src


@pytest.mark.asyncio
async def test_job_functions_return_none_not_a_count(monkeypatch):
    """audit_wrap reads an int return as rows_written and arms the empty-result
    invariant — fatal for a lane that idles for weeks by design (G8)."""
    from agents.market_intelligence import scheduler as sched
    monkeypatch.setattr(ed, "run_ecosystem_discovery", AsyncMock(return_value={"clusters": 0}))
    monkeypatch.setattr(ed, "sweep_ecosystem_grace", AsyncMock(return_value={"promoted": [], "errors": []}))
    assert await sched._ecosystem_discovery_job() is None
    assert await sched._ecosystem_grace_sweep_job() is None
    assert await sched._ecosystem_grace_sweep_boot() is None


def test_audit_vocabulary_is_registered():
    from agents.market_intelligence import audit_events as ae
    for c in ("ECOSYSTEM_DISCOVERY_RAN", "ECOSYSTEM_CLUSTER_SIGHTED", "ECOSYSTEM_PROPOSED_PENDING",
              "ECOSYSTEM_AUTO_PROMOTED", "ECOSYSTEM_VETOED", "ECOSYSTEM_COOLDOWN_SKIP",
              "ECOSYSTEM_RETIRED", "ECOSYSTEM_PROMOTION_ERROR"):
        assert getattr(ae, c).startswith("ecosystem_")


def test_ceiling_registered_and_bound():
    from shared import output_ceilings as oc
    assert oc.max_tokens_for("ecosystem_discovery_proposal") >= 1750
    assert 'max_tokens_for("ecosystem_discovery_proposal")' in _src(
        "agents/market_intelligence/ecosystem_discovery.py")


def test_writer_sql_registered_in_preflight():
    src = _src("scripts/preflight_db_updates.py")
    assert "ECOSYSTEM_PROPOSAL_INSERT_SQL" in src and "ECOSYSTEM_DYNAMIC_INSERT_SQL" in src
    assert "RETURNING id" in dbmod.ECOSYSTEM_PROPOSAL_INSERT_SQL
    assert "ON CONFLICT (e_code) DO NOTHING" in dbmod.ECOSYSTEM_DYNAMIC_INSERT_SQL


def test_status_guarded_sql_is_pinned():
    """The fake store mirrors these predicates; the real SQL cannot run here, so pin
    its text. Mutation: drop `status = 'pending'` from the claim → a vetoed row would
    be promoted by the sweep (the WOULD-FAIL-IF)."""
    claim = inspect.getsource(dbmod.claim_due_ecosystem_proposals)
    assert "WHERE status = 'pending' AND grace_ends_at <= $1" in claim
    assert "SET status = 'live'" in claim
    pend = inspect.getsource(dbmod.mark_ecosystem_proposal_pending)
    assert "WHERE id = $1 AND status = 'sighted'" in pend
    veto = inspect.getsource(dbmod.mark_ecosystem_proposal_vetoed)
    assert "WHERE id = $1 AND status = $6" in veto


def test_module_touches_no_trade_or_broker_surface():
    """THE LINE, textually: the lane imports nothing from broker/ and names no trade table."""
    src = _src("agents/market_intelligence/ecosystem_discovery.py")
    for needle in ("from broker", "import broker", "mi_live_trades", "mi_paper_trades",
                   "alpaca", "order_manager", "entry_pipeline"):
        assert needle not in src, needle


def test_alert_text_carries_the_action():
    """Mutation: drop VETO_COMMAND from format_veto_alert → the alert is a notice, not
    a decision surface."""
    p = _proposal_for(synthetic_cluster())
    one = format_veto_alert(p, T0 + timedelta(hours=48), n_pending=1)
    assert f"Tap {VETO_COMMAND}" in one and "E-DRONE" in one and "48h" in one
    many = format_veto_alert(p, T0 + timedelta(hours=48), n_pending=2)
    assert f"{VETO_COMMAND} E-DRONE" in many and "2 pending" in many
    # HTML surface: an & in a theme name must be escaped, never break the parse
    p2 = dict(p, member_themes=["R&D Drones"])
    assert "R&amp;D" in format_veto_alert(p2, T0, n_pending=1)


# ═══════════════════════════════════════════════════════════════════════════
# H. The DoD — synthetic end-to-end, both branches
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_e2e_synthetic_cluster_fires_veto_alert_then_promotes_at_grace_end(
        store, sent, proposer):
    """DoD clauses 2 + 3, no-veto branch. Seed: 3 fake E-UNASSIGNED themes, overlapping
    tickers, 15d old. Sunday 1 → sighted (silent). Sunday 2 → pending + THE ALERT.
    +47h → still pending. +48h → LIVE: bucket row, themes remapped, confirm sent.
    What the BROKEN system produces: no `_send_html` await / no
    `ecosystem_proposed_pending` row after Sunday 2, or a row still `pending` after +48h."""
    await run_ecosystem_discovery(now=T0, proposer=proposer)
    assert sent.await_count == 0
    sunday2 = T0 + 7 * DAY
    await run_ecosystem_discovery(now=sunday2, proposer=proposer)
    p = store.only_proposal()
    assert p["status"] == "pending"
    assert store.events("ecosystem_proposed_pending"), "no alert row"
    assert sent.await_count == 1 and VETO_COMMAND in sent.await_args.args[0], "no alert"

    assert (await sweep_ecosystem_grace(now=sunday2 + timedelta(hours=47)))["promoted"] == []
    assert p["status"] == "pending"
    out = await sweep_ecosystem_grace(now=sunday2 + timedelta(hours=48))
    assert out["promoted"] == ["E-DRONE"] and p["status"] == "live"
    assert store.dynamic["E-DRONE"]["status"] == "active"
    assert {r["e_code"] for r in store.mapping.values()} == {"E-DRONE"}
    assert store.events("ecosystem_auto_promoted")
    assert "E-DRONE" in te.get_ecosystem_codes()


@pytest.mark.asyncio
async def test_e2e_synthetic_cluster_vetoed_never_promotes(store, sent, proposer):
    """DoD WOULD-FAIL-IF: 'a vetoed cluster promotes anyway'. Same seed; the operator
    taps the bare command inside the grace window; the sweep at +48h (and +7d) promotes
    nothing; the next Sunday's pass skips the cluster on cooldown.
    What the BROKEN system produces: a dynamic row / a remapped theme / an
    `ecosystem_auto_promoted` row after the veto."""
    await run_ecosystem_discovery(now=T0, proposer=proposer)
    sunday2 = T0 + 7 * DAY
    await run_ecosystem_discovery(now=sunday2, proposer=proposer)
    p = store.only_proposal()
    assert p["status"] == "pending"

    res = await veto_ecosystem(None, now=sunday2 + timedelta(hours=5))     # the one-tap
    assert res["status"] == "vetoed" and p["status"] == "vetoed"

    for at in (timedelta(hours=48), timedelta(days=7)):
        assert (await sweep_ecosystem_grace(now=sunday2 + at))["promoted"] == []
    assert p["status"] == "vetoed"
    assert store.dynamic == {} and store.dynamic_inserts == 0
    assert all(r["e_code"] == E_UNASSIGNED for r in store.mapping.values())
    assert not store.events("ecosystem_auto_promoted")
    assert "E-DRONE" not in te.get_ecosystem_codes()

    out = await run_ecosystem_discovery(now=sunday2 + 7 * DAY, proposer=proposer)
    assert out["cooldown_skips"] == ["E-DRONE"] and out["pending"] == []
    assert sent.await_count == 1                                            # only the one alert
