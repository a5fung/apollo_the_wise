"""#655 rule B + bug E (theme_engine, 2026-10-04, operator "aligned": rule 1 YES, rule 2 WAIT, E fix).

RULE B — a theme whose emitted row tonight is WEAK-Fading (stage 'Fading' AND rs_avg None — the row
only `_rescore_existing_theme`'s weak branch writes; the scored path always carries a number) with
FEWER THAN 3 members is retired tonight instead of after FADING_RETIRE_AFTER (5) weak nights. It is a
separate pass sited right AFTER Step 2a.5 (#491 re-homing) because the stage decision runs in Step 1,
before the pools are built; the dropped theme takes the SAME engine-drop path a 5-night retirement
takes (tombstone + `theme_auto_retired`, the `theme_retired` changelog line). Toggle
`theme_small_fading_retire`, DEFAULT ON; OFF = nothing retired here.

BUG E — the promote lane read "has a prior mi_themes row" as "maintenance of a live theme", but the
immediately-prior row by name is frequently an auto-retire TOMBSTONE (stage 'Retired'); a cohort
retired one night and re-promoted the next skipped the birth gate, so the dedup_only join arm could
never fire on it. A tombstone prior is now a first crossing for the gate; a live prior stays
maintenance; days_active continuity is untouched.

Red-without / mutation record (run on this commit, stated in the commit message): the two
behaviour-introducing tests (2-member weak retires; tombstone prior consults the gate) are RED on
origin/main's theme_engine.py. The preservation tests stay green on revert by construction and were
each turned red by one mutation: drop `rs_avg is None` → the scored/elite test; `<` → `<=` → the
3-member grace test; ignore the toggle → the OFF test; `_first_crossing = True` → the live-prior test.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from tests.conftest import make_mock_pool
from tests.test_theme_birth_gate import _BOARD_THEME, _FRI, _MON, _drive_engine, _wire_promote

from agents.market_intelligence import audit_events as ae
from agents.market_intelligence import db as dbmod
from agents.market_intelligence import theme_correctness as tc
from agents.market_intelligence import theme_engine as te

CRUISE = "Cruise & Expedition Travel Operators"      # the #368 guard's case: a healthy pair shown Fading, RS 81
COAL = "Coal Mining Producers"                        # a 2-member weak-Fading shell on the 10-02 board
PIVOT = "Bitcoin Miners Pivoting to AI/HPC Data Center Hosting"
AI = "Emerging AI Compute & Cloud Infrastructure Platforms"


def _row(name, tickers, stage="Fading", rs_avg=None, **kw):
    """One emitted row in the shape `_rescore_existing_theme` returns."""
    return {"theme_date": _MON, "name": name, "stage": stage, "score": 20.0, "rs_avg": rs_avg,
            "description": "d", "tickers": list(tickers), "pct_above_20sma": None,
            "parent_theme": None, "renamed_from": None, **kw}


def _wire_pass(monkeypatch, toggle=True, audit=None):
    events: list[tuple] = []

    async def _audit(event_type, summary="", detail="", **kw):
        events.append((event_type, summary, detail))

    monkeypatch.setattr(te, "log_audit_event", audit or _audit)
    read = AsyncMock(return_value=toggle)
    monkeypatch.setattr(te, "_read_small_fading_retire_toggle", read, raising=False)
    return events, read


def _run(themes, changelog):
    return asyncio.run(te._retire_small_fading_themes(themes, changelog))


# ═══════════════════════════════ rule B — the pass ═══════════════════════════════════════════


def test_a_two_member_weak_fading_theme_retires_tonight(monkeypatch):
    """RED without the change (the pass does not exist on origin/main)."""
    events, _read = _wire_pass(monkeypatch)
    healthy = _row("Healthy Four", ["A", "B", "C", "D"], stage="Mainstream", rs_avg=85.0)
    themes = [_row(COAL, ["BTU", "CEIX"]), healthy, _row("Remnant", ["X"])]   # 2 members, and the 1-member remnant a #491 move leaves
    changelog: list[dict] = []
    out = _run(themes, changelog)
    assert [t["name"] for t in out] == ["Healthy Four"]
    # ONE named audit row per retirement, summary in the live check's wording
    assert [e[0] for e in events] == [ae.THEME_RETIRED_SMALL_FADING] * 2
    assert events[0][1] == f"{COAL}: retired — weak Fading at 2 members (< 3), #655"
    assert events[1][1] == "Remnant: retired — weak Fading at 1 members (< 3), #655"
    detail = json.loads(events[0][2])
    assert detail["members"] == 2 and detail["tickers"] == ["BTU", "CEIX"]
    # the 5-night path's own changelog line — the nightly message, the funnel count and the
    # `theme_retired` audit row all come off it
    assert changelog == [
        {"type": "theme_retired", "theme": COAL, "tickers": ["BTU", "CEIX"], "via": "small_fading"},
        {"type": "theme_retired", "theme": "Remnant", "tickers": ["X"], "via": "small_fading"},
    ]


def test_a_scored_or_elite_two_member_theme_is_never_touched(monkeypatch):
    """The #368 guard: a Fading row WITH rs_avg is the scored path (a healthy pair the score-delta or
    hysteresis shows Fading) — not retired, and no toggle read without a weak candidate.
    Mutation: drop `rs_avg is None` from the predicate → red."""
    events, read = _wire_pass(monkeypatch)
    themes = [_row(CRUISE, ["LIND", "VIK"], stage="Fading", rs_avg=81.0),
              _row("Elite Pair", ["P1", "P2"], stage="Mainstream", rs_avg=83.0),
              _row("Weak but Nascent", ["N1", "N2"], stage="Nascent", rs_avg=55.0)]
    changelog: list[dict] = []
    out = _run(themes, changelog)
    assert out == themes and events == [] and changelog == []
    assert read.await_count == 0


def test_three_members_keep_the_five_night_grace(monkeypatch):
    """Mutation: `<` → `<=` → red."""
    events, read = _wire_pass(monkeypatch)
    themes = [_row("Weak Trio", ["A", "B", "C"]), _row("Weak Five", ["A", "B", "C", "D", "E"])]
    out = _run(themes, [])
    assert out == themes and events == [] and read.await_count == 0
    # the boundary is G4's and the coverage floor's: under 3 members
    assert te.SMALL_FADING_RETIRE_MIN_MEMBERS == te.THEME_COVERAGE_MIN == 3
    assert tc.compute_g4([{"name": "x", "tickers": ["A", "B"]}])["small"] == 1
    assert tc.compute_g4([{"name": "x", "tickers": ["A", "B", "C"]}])["small"] == 0
    assert te._is_weak_fading_small(_row("x", ["A", "B"])) is True
    assert te._is_weak_fading_small(_row("x", ["A", "B", "C"])) is False


def test_toggle_off_is_the_old_behaviour(monkeypatch):
    """Mutation: ignore the toggle → red."""
    events, read = _wire_pass(monkeypatch, toggle=False)
    themes = [_row(COAL, ["BTU", "CEIX"]), _row("Healthy", ["A", "B", "C"], stage="Mainstream", rs_avg=80.0)]
    changelog: list[dict] = []
    out = _run(themes, changelog)
    assert out == themes and events == [] and changelog == []
    assert read.await_count == 1          # a candidate existed, so the toggle WAS consulted


def test_a_theme_renamed_this_run_gets_one_night(monkeypatch):
    """Its old name is already tombstoned with the new name as successor; retiring the new name the
    same night would point that lineage at a theme that never got a row."""
    events, _read = _wire_pass(monkeypatch)
    themes = [_row("New Name", ["A", "B"], renamed_from="Old Name")]
    assert _run(themes, []) == themes and events == []


def test_an_audit_row_that_cannot_be_written_keeps_the_theme(monkeypatch):
    """The row IS the live check's evidence — no row, no retirement for that theme tonight."""
    async def _boom(event_type, summary="", detail="", **kw):
        raise RuntimeError("audit down")

    _events, _read = _wire_pass(monkeypatch, audit=_boom)
    themes = [_row(COAL, ["BTU", "CEIX"])]
    changelog: list[dict] = []
    assert _run(themes, changelog) == themes and changelog == []


def test_the_toggle_is_discoverable_by_the_drift_check_and_defaults_on():
    from scripts.live_rules import discover_runtime_toggles
    fact = discover_runtime_toggles()[te.SMALL_FADING_RETIRE_TOGGLE[0]]
    assert fact.env_var == te.SMALL_FADING_RETIRE_TOGGLE[1] and fact.default is True
    assert fact.where.startswith("agents/market_intelligence/theme_engine.py:")


def test_the_audit_events_are_registered():
    assert ae.THEME_RETIRED_SMALL_FADING == "theme_retired_small_fading"
    assert ae.THEME_SMALL_FADING_RETIRE_ERROR == "theme_small_fading_retire_error"


# ═══════════════════════════════ rule B — siting in run_theme_engine ═════════════════════════


def _drive_with_rehome(monkeypatch, *, small_fading_on: bool):
    """Drive the REAL run_theme_engine with a 3-member weak-Fading pivot theme on the board and a
    re-homing pass that moves CIFR out of it (3 → 2). Returns (saved rows, audits mock, order)."""
    saved, _discover, _accel, audits = _drive_engine(monkeypatch, mode="off", discovered=[])
    weak = {"name": PIVOT, "stage": "Fading", "score": 20.0, "rs_avg": None,
            "tickers": ["CIFR", "HUT", "WULF"], "description": "d"}
    target = {"name": AI, "stage": "Mainstream", "score": 70.0, "rs_avg": 90.0,
              "tickers": ["CRWV", "NBIS", "ALAB"], "description": "d"}
    monkeypatch.setattr(te, "get_active_themes", AsyncMock(return_value=[dict(weak), dict(target)]))
    # members off the leaders list are RS-fetched by name — stub the two DB reads
    monkeypatch.setattr(dbmod, "get_rs_for_tickers", AsyncMock(return_value={
        tk: {"rs_composite": 60.0} for tk in weak["tickers"] + target["tickers"]}))
    monkeypatch.setattr(dbmod, "get_sectors_batch", AsyncMock(return_value={}))
    # the tape context exists and re-homing is ON, so Step 2a.5 runs
    monkeypatch.setattr(te, "_read_assign_comove_toggle", AsyncMock(return_value=True))
    monkeypatch.setattr(te, "_load_comove_context", AsyncMock(return_value=te.ComoveContext(
        before_date=_MON, excess={}, n_sessions=0, n_rows=0)))
    monkeypatch.setattr(te, "_read_rehome_toggle", AsyncMock(return_value=True))
    order: list[str] = []

    async def _rehome(themes, sbt, ctx, **kw):
        order.append("rehome")
        by = {t["name"]: t for t in themes}
        by[PIVOT]["tickers"] = [tk for tk in by[PIVOT]["tickers"] if tk != "CIFR"]
        by[AI]["tickers"] = by[AI]["tickers"] + ["CIFR"]
        kw["changelog"].append({"type": "ticker_rehomed", "ticker": "CIFR", "from": [PIVOT], "theme": AI})
        return {"moved": 1}

    monkeypatch.setattr(te, "_run_rehome_pass", _rehome)
    real = te._retire_small_fading_themes

    async def _recorded(themes, changelog):
        order.append("small_fading")
        return await real(themes, changelog)

    monkeypatch.setattr(te, "_retire_small_fading_themes", _recorded, raising=False)
    monkeypatch.setattr(te, "_read_small_fading_retire_toggle",
                        AsyncMock(return_value=small_fading_on), raising=False)
    # the engine-drop block reads today's successor pointers from mi_audit_log
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    asyncio.run(te.run_theme_engine(trade_date=_MON))
    return saved, audits, order


def test_runs_after_rehoming_so_a_rehomed_member_is_not_double_handled(monkeypatch):
    """RED without the change: the pivot theme stays on the board as a 2-member Fading row."""
    saved, audits, order = _drive_with_rehome(monkeypatch, small_fading_on=True)
    assert order == ["rehome", "small_fading"]
    rows = {(r["name"], r["stage"]): r for r in saved}
    # CIFR landed in its new home BEFORE the retire read the pivot theme
    assert "CIFR" in rows[(AI, "Mainstream")]["tickers"]
    # the pivot theme is on tonight's board ONLY as the engine-drop tombstone
    assert (PIVOT, "Fading") not in rows
    tomb = rows[(PIVOT, "Retired")]
    assert tomb["tickers"] == [] and tomb["parent_theme"] is None
    names = [c.args[0] for c in audits.await_args_list]
    # the named row counts 2 members (HUT, WULF) — the moved name is not double-handled
    small = next(c for c in audits.await_args_list if c.args[0] == ae.THEME_RETIRED_SMALL_FADING)
    assert small.kwargs["summary"] == f"{PIVOT}: retired — weak Fading at 2 members (< 3), #655"
    assert json.loads(small.kwargs["detail"])["tickers"] == ["HUT", "WULF"]
    # the 5-night path's rows fire for it too: the tombstone's and the retirement's
    assert "theme_auto_retired" in names and "theme_retired" in names
    retired_row = next(c for c in audits.await_args_list if c.args[0] == "theme_retired")
    assert retired_row.kwargs["summary"] == f"Retired: {PIVOT}"


def test_toggle_off_in_the_engine_keeps_the_two_member_theme_on_the_board(monkeypatch):
    saved, audits, order = _drive_with_rehome(monkeypatch, small_fading_on=False)
    assert order == ["rehome", "small_fading"]
    rows = {(r["name"], r["stage"]): r for r in saved}
    assert rows[(PIVOT, "Fading")]["tickers"] == ["HUT", "WULF"]
    assert (PIVOT, "Retired") not in rows
    names = [c.args[0] for c in audits.await_args_list]
    assert ae.THEME_RETIRED_SMALL_FADING not in names and "theme_auto_retired" not in names


# ═══════════════════════════════ bug E — the promote lane ════════════════════════════════════


@pytest.mark.asyncio
async def test_a_tombstone_prior_is_a_first_crossing_so_the_join_arm_fires(monkeypatch):
    """RED without the change: the tombstone read as a live prior, the gate was never consulted and
    the duplicate cohort was re-minted over its live twin (the 10-02 'Defense & Space…' shape)."""
    conn, tele, _ = _wire_promote(
        monkeypatch,
        [{"name": "Dup Cohort", "tickers": ["J1", "J2", "J3"], "thesis": "t", "source": "narrative_cogap"}],
        mode="dedup_only",
        prior_rows=[{"name": "Dup Cohort", "days_active": 4, "stage": "Retired"}])
    monkeypatch.setattr(te, "get_active_themes", AsyncMock(return_value=[dict(_BOARD_THEME)]))
    n = await te.promote_shadow_themes(_MON)
    assert n == 0
    assert not [c for c in conn.execute.await_args_list if "INSERT INTO mi_themes" in c.args[0]]
    rec = dbmod.record_birth_candidate_sighting
    assert rec.await_args.kwargs["outcome"] == "join" and rec.await_args.kwargs["join_target"] == "Board Name"
    tele.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_tombstone_prior_that_passes_the_gate_keeps_days_active_continuity(monkeypatch):
    """Continuity is NOT part of the defect: a returning cohort the gate births resumes its counter."""
    conn, _, _ = _wire_promote(
        monkeypatch,
        [{"name": "Returning Theme", "tickers": ["R1", "R2", "R3"], "thesis": "t", "source": "narrative_cogap"}],
        mode="dedup_only",
        prior_rows=[{"name": "Returning Theme", "days_active": 4, "stage": "Retired"}])
    monkeypatch.setattr(dbmod, "get_recent_birth_candidates", AsyncMock(return_value=[
        {"id": 11, "name": "Returning Theme", "first_seen": _FRI, "last_seen": _FRI,
         "sightings": 1, "tickers": ["R1", "R2", "R3"], "status": "watching"}]))
    monkeypatch.setattr(dbmod, "get_cohort_rs_snapshot", AsyncMock(return_value=(84.0, 80.0)))
    n = await te.promote_shadow_themes(_MON)
    assert n == 1
    dbmod.record_birth_candidate_sighting.assert_awaited()          # the gate WAS consulted
    ins = next(c for c in conn.execute.await_args_list if "INSERT INTO mi_themes" in c.args[0])
    assert ins.args[2] == "Returning Theme" and ins.args[6] == 5    # days_active = prior 4 + 1


@pytest.mark.asyncio
async def test_a_live_prior_is_maintenance_and_the_gate_is_not_consulted(monkeypatch):
    """Mutation: `_first_crossing = True` → red."""
    conn, _, _ = _wire_promote(
        monkeypatch,
        [{"name": "Established Theme", "tickers": ["J1", "J2", "J3"], "thesis": "t", "source": "narrative_cogap"}],
        mode="dedup_only",
        prior_rows=[{"name": "Established Theme", "days_active": 9, "stage": "Fading"}])
    monkeypatch.setattr(te, "get_active_themes", AsyncMock(return_value=[dict(_BOARD_THEME)]))
    n = await te.promote_shadow_themes(_MON)
    assert n == 1
    assert [c.args[2] for c in conn.execute.await_args_list
            if "INSERT INTO mi_themes" in c.args[0]] == ["Established Theme"]
    dbmod.record_birth_candidate_sighting.assert_not_awaited()
