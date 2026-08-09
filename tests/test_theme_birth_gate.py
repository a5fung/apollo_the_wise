"""Theme BIRTH GATE (consolidation Phase 1, operator-ruled 2026-07-27) — 3-state pins.

Toggle `theme_birth_gate` ∈ db.BIRTH_GATE_MODES = ("off", "observe", "on") —
the broker_order_ingest 3-state idiom, fail-closed 'off'.

The load-bearing contracts:
1. Mode 'off' ⇒ byte-identical to today: no a/a2 selector fetch, no gate
   consult, no ledger write, full auto-promote allowlist (incl. shadow_v2),
   coverage_probe job runs. Fail-closed: a DB error or an unrecognized state
   string selects 'off'.
2. Mode 'observe' (the DEPLOY state) ⇒ ZERO behavioural difference from 'off'
   — every theme born exactly as today, promote untouched, retirements
   inactive, allowlist unchanged — while the gate's verdict IS computed and
   RECORDED per candidate (outcome + deciding lever + member-avg RS +
   pre-birth Δ5-session + IoS overlaps + mode) in the ledger + audit rows, so
   the observe period is judgeable later from stored rows without a re-run.
   The ledger populates in observe (join-or-new — the biggest lever, 50/106 —
   is exercised, not starved).
3. Derived thresholds at their exact boundaries: RS 70.0 passes the level arm;
   Δ5-session 0.0 passes the rising arm; sightings 2 passes the bar; join
   fires at exactly 0.5 intersection-over-smaller.
4. Two-sighting bar counts DISTINCT DAYS and survives a weekend.
5. EXISTING LIVE THEMES ARE UNTOUCHED: prior-row re-promotions bypass the
   gate; Lane-1 re-emissions pass ungated; a `join` verdict only ever
   suppresses an INSERT (and only in mode 'on').
6. The a/a2 port: in mode 'on', Lane-1 discovery receives the accelerator +
   recovery-slope selections that previously existed only in the retired
   shadow_v2 pass.

GRADE-AFFECTING + AUTO-PROMOTE reach: theme output feeds the judge's
active_narratives and auto-promotes into live mi_themes — the off/observe
parity pins are money-path-adjacent safety, not style.
"""
from __future__ import annotations

import datetime as _dt
from unittest.mock import AsyncMock

import pytest

from tests.conftest import make_mock_pool

from agents.market_intelligence import db as dbmod
from agents.market_intelligence import theme_birth_gate as tbg
from agents.market_intelligence import theme_engine as te

_FRI = _dt.date(2026, 7, 24)
_MON = _dt.date(2026, 7, 27)


# ════════════════════════════════════════════════════════════════════════════
# 1. Pure decision logic — every derived threshold at its boundary
# ════════════════════════════════════════════════════════════════════════════

def test_derived_cell_constants_are_the_signed_values():
    # The operator signs THIS cell (CHANGE_PROCESS): drift here is a criterion
    # change and must show up as a failing pin, not a silent renumber.
    assert tbg.BIRTH_GATE_RS_FLOOR == 70.0
    assert tbg.BIRTH_GATE_TRAJ_MIN == 0.0
    assert tbg.BIRTH_GATE_MIN_SIGHTINGS == 2
    assert tbg.BIRTH_GATE_JOIN_OVERLAP == 0.5
    assert tbg.BIRTH_GATE_LEDGER_DAYS == 14
    assert tbg.BIRTH_GATE_TRAJ_SESSIONS == 5
    assert dbmod.BIRTH_GATE_MODES == ("off", "observe", "on")


def test_gate_decision_boundaries():
    # Two-sighting bar first: even RS 99 waits on sighting 1.
    assert tbg.gate_decision(99.0, 10.0, 1) == (False, "await_second_sighting")
    # Level arm at the boundary: exactly 70.0 passes on sighting 2.
    assert tbg.gate_decision(70.0, -50.0, 2) == (True, "pass_rs_level")
    # Just below the level with a FALLING trajectory: held.
    assert tbg.gate_decision(69.99, -0.01, 2) == (False, "held_floor")
    # The rising arm at ITS boundary: Δ exactly 0.0 rescues a weak level —
    # THE derivation finding (weak-born maturers are rising pre-birth).
    assert tbg.gate_decision(40.0, 0.0, 2) == (True, "pass_rs_rising")
    # Unknown never satisfies an arm (fail-closed per arm).
    assert tbg.gate_decision(None, None, 2) == (False, "held_no_rs")
    assert tbg.gate_decision(69.99, None, 2) == (False, "held_floor")
    # Unknown level + known rising trajectory: the rising arm may still pass.
    assert tbg.gate_decision(None, 3.0, 2) == (True, "pass_rs_rising")
    # Extra sightings never relax the floor.
    assert tbg.gate_decision(40.0, -5.0, 7) == (False, "held_floor")


def test_join_overlap_boundary_and_retired_skip():
    live = [
        {"name": "Crypto Asset Recovery", "stage": "Nascent",
         "tickers": ["MARA", "RIOT", "CLSK", "HUT"]},
        {"name": "Dead Theme", "stage": "Retired", "tickers": ["AAA", "BBB"]},
    ]
    # 2 of min(4,4) = 2/4 = 0.5 exactly → joins (intersection-over-smaller),
    # and the overlap VALUE is returned (observe-review input).
    assert tbg.find_join_target(["MARA", "RIOT", "XX", "YY"], live) == \
        ("Crypto Asset Recovery", 0.5)
    # Below the boundary (1/4 = 0.25) → no join.
    assert tbg.find_join_target(["MARA", "XX", "YY", "ZZ"], live) == (None, None)
    # A Retired board row can never be a join target.
    assert tbg.find_join_target(["AAA", "BBB"], live[1:]) == (None, None)
    # Case-insensitive on members.
    assert tbg.find_join_target(["mara", "riot"], live)[0] == "Crypto Asset Recovery"


def test_join_refinement_carveout_majority_covered_skips_join():
    # A sub-theme proposal (member-majority already covered) is the existing
    # merge/Route-A machinery's job — the gate must NOT join-suppress it, or
    # the live elite-split path regresses.
    live = [{"name": "Big Theme", "stage": "Mainstream",
             "tickers": ["A", "B", "C", "D", "E"]}]
    covered = {"A", "B", "C", "D", "E"}
    # 3/3 covered (share 1.0 > 0.5) → carve-out: no join.
    assert tbg.find_join_target(["A", "B", "C"], live, covered_tickers=covered) == (None, None)
    # Exactly half covered (share 0.5, NOT > 0.5) → still a net-new cohort →
    # full join check applies (overlap 2/4 = 0.5 → join fires).
    assert tbg.find_join_target(["A", "B", "X", "Y"], live, covered_tickers=covered) == \
        ("Big Theme", 0.5)


def test_find_ledger_match_picks_best_overlap():
    ledger = [
        {"id": 1, "name": "Cohort One", "tickers": ["A", "B", "X", "Y"], "sightings": 1},
        {"id": 2, "name": "Cohort Two", "tickers": ["A", "B", "C"], "sightings": 1},
    ]
    m, ov = tbg.find_ledger_match(["A", "B", "C"], ledger)
    assert m["id"] == 2 and ov == 1.0    # 3/3 = 1.0 beats 2/3 ≈ 0.67
    assert tbg.find_ledger_match(["Q", "W"], ledger) == (None, None)
    assert tbg.find_ledger_match([], ledger) == (None, None)


# ════════════════════════════════════════════════════════════════════════════
# 2. evaluate_birth — ledger mechanics incl. the weekend two-sighting bar
# ════════════════════════════════════════════════════════════════════════════

def _wire_gate(monkeypatch, *, ledger_rows, rs_snapshot, record_id=77):
    """Patch the gate's db surface; returns the record mock (call args carry
    the persisted verdict + lever + inputs)."""
    monkeypatch.setattr(dbmod, "get_recent_birth_candidates",
                        AsyncMock(return_value=ledger_rows))
    monkeypatch.setattr(dbmod, "get_cohort_rs_snapshot",
                        AsyncMock(return_value=rs_snapshot))
    rec = AsyncMock(return_value=record_id)
    monkeypatch.setattr(dbmod, "record_birth_candidate_sighting", rec)
    # P3 annotation is evidence-only — stub it out of these decision tests.
    monkeypatch.setattr(tbg, "_p3_annotation", AsyncMock(return_value=(None, None)))
    return rec


@pytest.mark.asyncio
async def test_two_sighting_bar_across_a_weekend(monkeypatch):
    # Friday first sighting → Monday re-sighting is the 2nd DISTINCT day even
    # though 3 calendar days passed — the cohort births (floor passing).
    ledger = [{"id": 5, "name": "Uranium Enrichers", "first_seen": _FRI,
               "last_seen": _FRI, "sightings": 1,
               "tickers": ["UUUU", "LEU", "SMR"], "status": "watching"}]
    rec = _wire_gate(monkeypatch, ledger_rows=ledger, rs_snapshot=(72.0, 70.0))
    res = await tbg.evaluate_birth(
        "Uranium Enrichment & SMR Fuel", ["UUUU", "LEU", "SMR"], "live", _MON, [])
    assert res["outcome"] == "birth" and res["sightings"] == 2
    # The ledger row was updated (existing id), not a new candidate; the
    # deciding lever + mode are persisted with it.
    assert rec.await_args.args[0] == 5
    assert rec.await_args.kwargs["outcome"] == "birth"
    assert rec.await_args.kwargs["reason"] == "pass_rs_level"
    assert rec.await_args.kwargs["mode"] == "on"       # default acting mode
    assert rec.await_args.kwargs["ledger_overlap"] == 1.0


@pytest.mark.asyncio
async def test_first_sighting_waits_even_with_elite_rs(monkeypatch):
    rec = _wire_gate(monkeypatch, ledger_rows=[], rs_snapshot=(95.0, 90.0))
    res = await tbg.evaluate_birth("Brand New Cohort", ["AA", "BB", "CC"],
                                   "live", _MON, [])
    assert res["outcome"] == "await_second_sighting" and res["sightings"] == 1
    # First sighting recorded as a NEW ledger candidate (id None).
    assert rec.await_args.args[0] is None
    assert rec.await_args.kwargs["outcome"] == "await_second_sighting"
    assert rec.await_args.kwargs["reason"] == "await_second_sighting"


@pytest.mark.asyncio
async def test_same_day_repropose_is_one_sighting(monkeypatch):
    # Two proposals of one cohort in ONE run must not fake the second sighting.
    ledger = [{"id": 9, "name": "Cohort", "first_seen": _MON, "last_seen": _MON,
               "sightings": 1, "tickers": ["AA", "BB", "CC"], "status": "watching"}]
    _wire_gate(monkeypatch, ledger_rows=ledger, rs_snapshot=(95.0, 90.0))
    res = await tbg.evaluate_birth("Cohort", ["AA", "BB", "CC"], "live", _MON, [])
    assert res["sightings"] == 1 and res["outcome"] == "await_second_sighting"


@pytest.mark.asyncio
async def test_join_suppresses_even_elite_rs_and_records_target(monkeypatch):
    rec = _wire_gate(monkeypatch, ledger_rows=[], rs_snapshot=(96.0, 92.0))
    live = [{"name": "Bitcoin Miners", "stage": "Accelerating",
             "tickers": ["MARA", "RIOT", "CLSK"]}]
    res = await tbg.evaluate_birth(
        "Crypto Mining Infrastructure", ["MARA", "RIOT", "XX"], "live", _MON, live)
    assert res["outcome"] == "join" and res["join_target"] == "Bitcoin Miners"
    assert res["join_overlap"] == pytest.approx(2 / 3)
    assert rec.await_args.kwargs["join_target"] == "Bitcoin Miners"
    assert rec.await_args.kwargs["join_overlap"] == pytest.approx(2 / 3)


@pytest.mark.asyncio
async def test_floor_holds_weak_falling_cohort_but_rising_rescues(monkeypatch):
    ledger = [{"id": 3, "name": "Weak Cohort", "first_seen": _FRI, "last_seen": _FRI,
               "sightings": 1, "tickers": ["QQ", "WW", "EE"], "status": "watching"}]
    # Weak AND falling (the RS-38.7 hospital class): held.
    _wire_gate(monkeypatch, ledger_rows=[dict(r) for r in ledger],
               rs_snapshot=(38.7, 45.0))
    res = await tbg.evaluate_birth("Weak Cohort", ["QQ", "WW", "EE"], "promote:shadow_v2",
                                   _MON, [])
    assert res["outcome"] == "held_floor"
    # Weak but RISING (the north-star early-theme class the operator named —
    # Domestic Steel 27.8→matured): the trajectory arm births it.
    _wire_gate(monkeypatch, ledger_rows=[dict(r) for r in ledger],
               rs_snapshot=(52.0, 47.0))
    res = await tbg.evaluate_birth("Weak Cohort", ["QQ", "WW", "EE"], "promote:shadow_v2",
                                   _MON, [])
    assert res["outcome"] == "birth" and res["reason"] == "pass_rs_rising"


@pytest.mark.asyncio
async def test_unknown_rs_holds_not_births(monkeypatch):
    ledger = [{"id": 4, "name": "NoData", "first_seen": _FRI, "last_seen": _FRI,
               "sightings": 1, "tickers": ["N1", "N2"], "status": "watching"}]
    _wire_gate(monkeypatch, ledger_rows=ledger, rs_snapshot=(None, None))
    res = await tbg.evaluate_birth("NoData", ["N1", "N2"], "live", _MON, [])
    assert res["outcome"] == "held_no_rs"


@pytest.mark.asyncio
async def test_observe_mode_verdict_identical_and_mode_recorded(monkeypatch):
    # mode='observe' changes RECORD-KEEPING only — the verdict math is
    # identical to 'on'; the caller decides whether to act.
    ledger = [{"id": 8, "name": "W", "first_seen": _FRI, "last_seen": _FRI,
               "sightings": 1, "tickers": ["W1", "W2", "W3"], "status": "watching"}]
    rec = _wire_gate(monkeypatch, ledger_rows=[dict(r) for r in ledger],
                     rs_snapshot=(38.7, 45.0))
    res = await tbg.evaluate_birth("W", ["W1", "W2", "W3"], "live", _MON, [],
                                   mode="observe")
    assert res["outcome"] == "held_floor" and res["mode"] == "observe"
    assert rec.await_args.kwargs["mode"] == "observe"
    assert rec.await_args.kwargs["reason"] == "held_floor"
    assert rec.await_args.kwargs["rs_avg"] == 38.7
    assert rec.await_args.kwargs["rs_traj5"] == pytest.approx(-6.3)


@pytest.mark.asyncio
async def test_p3_annotation_failure_never_blocks_a_birth(monkeypatch):
    # The kept coverage_probe primitive is EVIDENCE ONLY: its failure must not
    # change the decision (annotation returns (None, None) internally).
    ledger = [{"id": 6, "name": "C", "first_seen": _FRI, "last_seen": _FRI,
               "sightings": 1, "tickers": ["A1", "A2", "A3"], "status": "watching"}]
    monkeypatch.setattr(dbmod, "get_recent_birth_candidates", AsyncMock(return_value=ledger))
    monkeypatch.setattr(dbmod, "get_cohort_rs_snapshot", AsyncMock(return_value=(88.0, 80.0)))
    rec = AsyncMock(return_value=6)
    monkeypatch.setattr(dbmod, "record_birth_candidate_sighting", rec)
    monkeypatch.setattr(dbmod, "get_pool", AsyncMock(side_effect=RuntimeError("db down")))
    res = await tbg.evaluate_birth("C", ["A1", "A2", "A3"], "live", _MON, [])
    assert res["outcome"] == "birth"
    assert rec.await_args.kwargs["p3_co_moving"] is None


# ════════════════════════════════════════════════════════════════════════════
# 3. The 3-state toggle — fail-closed reads, validated writes, allowlist walls
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_mode_fail_closed_on_db_error(monkeypatch):
    monkeypatch.setattr(dbmod, "get_pool", AsyncMock(side_effect=RuntimeError("db down")))
    assert await dbmod.get_theme_birth_gate_mode() == "off"


@pytest.mark.asyncio
async def test_mode_unrecognized_state_reads_off_and_set_validates(monkeypatch):
    # An unrecognized row value fails closed to 'off' (the order_ingest idiom)…
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value={"state": "dry_run"})   # not a birth-gate mode
    monkeypatch.setattr(dbmod, "get_pool", AsyncMock(return_value=pool))
    assert await dbmod.get_theme_birth_gate_mode() == "off"
    conn.fetchrow = AsyncMock(return_value={"state": "observe"})
    assert await dbmod.get_theme_birth_gate_mode() == "observe"
    conn.fetchrow = AsyncMock(return_value=None)                   # no row → off
    assert await dbmod.get_theme_birth_gate_mode() == "off"
    # …and the setter refuses to WRITE a state every reader would discard.
    with pytest.raises(ValueError):
        await dbmod.set_theme_birth_gate_mode("enabled")


@pytest.mark.asyncio
async def test_resolve_auto_promote_sources_only_on_retires_shadow_v2():
    off = await dbmod.resolve_auto_promote_sources("off")
    assert off is dbmod.AUTO_PROMOTE_THEME_SOURCES          # identity: byte-identical
    observe = await dbmod.resolve_auto_promote_sources("observe")
    assert observe is dbmod.AUTO_PROMOTE_THEME_SOURCES      # observe acts on NOTHING
    on = await dbmod.resolve_auto_promote_sources("on")
    assert on == dbmod.AUTO_PROMOTE_THEME_SOURCES - {"shadow_v2"}
    assert "narrative_cogap" in on and "rs_slope_synthesis" in on
    # The frozen master list itself is UNCHANGED (dedup with the #469 pins).
    assert dbmod.AUTO_PROMOTE_THEME_SOURCES == {
        "shadow_v2", "narrative_cogap", "rs_slope_synthesis"}


@pytest.mark.asyncio
async def test_auto_promote_reader_drops_shadow_v2_only_in_mode_on(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(dbmod, "get_pool", AsyncMock(return_value=pool))

    for mode in ("off", "observe"):
        monkeypatch.setattr(dbmod, "get_theme_birth_gate_mode",
                            AsyncMock(return_value=mode))
        await dbmod.get_shadow_theme_candidates(days=7)
        allow = [a for a in conn.fetch.await_args.args[1:] if isinstance(a, list)][0]
        assert set(allow) == dbmod.AUTO_PROMOTE_THEME_SOURCES, mode  # full allowlist

    monkeypatch.setattr(dbmod, "get_theme_birth_gate_mode", AsyncMock(return_value="on"))
    await dbmod.get_shadow_theme_candidates(days=7)
    allow_on = [a for a in conn.fetch.await_args.args[1:] if isinstance(a, list)][0]
    assert "shadow_v2" not in allow_on
    assert set(allow_on) == {"narrative_cogap", "rs_slope_synthesis"}

    # Operator surface (include_probe=True) is UNGATED in every mode.
    await dbmod.get_shadow_theme_candidates(days=7, include_probe=True)
    assert conn.fetch.await_args.args[2] is True


# ── promote path ─────────────────────────────────────────────────────────────

def _wire_promote(monkeypatch, cands, *, mode, prior_rows=None, rs_rows=None, prior_desc_rows=None):
    pool, conn = make_mock_pool()
    # #530: promote_shadow_themes now issues THREE conn.fetch calls — prior_rows
    # (days_active), prior_desc_rows (tombstone-skipping description lookup, empty by
    # default here since none of these gate tests exercise thesis preservation), RS rows.
    conn.fetch = AsyncMock(side_effect=[prior_rows or [], prior_desc_rows or [], rs_rows or []])
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(te, "_canonicalize_theme_names", AsyncMock(return_value=0))
    monkeypatch.setattr(te, "log_audit_event", AsyncMock())
    monkeypatch.setattr(te, "get_theme_birth_gate_mode", AsyncMock(return_value=mode))
    monkeypatch.setattr(te, "get_active_themes", AsyncMock(return_value=[]))
    monkeypatch.setattr(te, "_map_ecosystems_nonfatal", AsyncMock())
    from agents.market_intelligence import briefing as _brief
    tele = AsyncMock()
    monkeypatch.setattr(_brief, "send_telegram_message", tele)
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=cands))
    ledger_reader = AsyncMock(return_value=[])
    monkeypatch.setattr(dbmod, "get_recent_birth_candidates", ledger_reader)
    monkeypatch.setattr(dbmod, "get_cohort_rs_snapshot", AsyncMock(return_value=(40.0, 45.0)))
    monkeypatch.setattr(dbmod, "record_birth_candidate_sighting", AsyncMock(return_value=1))
    monkeypatch.setattr(dbmod, "log_audit_event", AsyncMock())
    monkeypatch.setattr(tbg, "_p3_annotation", AsyncMock(return_value=(None, None)))
    return conn, tele, ledger_reader


@pytest.mark.asyncio
async def test_mode_off_promote_is_byte_identical_no_gate_no_ledger(monkeypatch):
    # A weak first-crossing cohort STILL graduates today (the documented
    # pre-gate behavior — no RS floor on this path), and the gate surface is
    # never touched: that IS the off-parity contract.
    conn, _, ledger_reader = _wire_promote(
        monkeypatch,
        [{"name": "Weak Utilities", "tickers": ["U1", "U2", "U3"],
          "thesis": "t", "source": "shadow_v2"}],
        mode="off")
    n = await te.promote_shadow_themes(_MON)
    assert n == 1
    written = [c.args[2] for c in conn.execute.await_args_list
               if "INSERT INTO mi_themes" in c.args[0]]
    assert written == ["Weak Utilities"]
    ledger_reader.assert_not_awaited()
    dbmod.record_birth_candidate_sighting.assert_not_awaited()


@pytest.mark.asyncio
async def test_mode_observe_promote_writes_identical_but_verdict_recorded(monkeypatch):
    # THE observe contract on the promote path: the weak shadow_v2 first
    # crossing is promoted EXACTLY as in 'off' (same mi_themes write, full
    # allowlist — shadow_v2 still promotes, no held-count), while the gate's
    # verdict + lever + inputs are recorded and the audit row is tagged
    # /observe. This is also requirement 2: the ledger POPULATES in observe.
    conn, tele, _ = _wire_promote(
        monkeypatch,
        [{"name": "Weak Utilities", "tickers": ["U1", "U2", "U3"],
          "thesis": "t", "source": "shadow_v2"}],
        mode="observe")
    n = await te.promote_shadow_themes(_MON)
    assert n == 1                                        # promoted anyway
    written = [c.args[2] for c in conn.execute.await_args_list
               if "INSERT INTO mi_themes" in c.args[0]]
    assert written == ["Weak Utilities"]                 # byte-identical write
    # …but the verdict was computed and persisted with lever + inputs.
    rec = dbmod.record_birth_candidate_sighting
    assert rec.await_args.kwargs["mode"] == "observe"
    assert rec.await_args.kwargs["outcome"] == "await_second_sighting"
    assert rec.await_args.kwargs["rs_avg"] == 40.0
    gate_rows = [c for c in dbmod.log_audit_event.await_args_list
                 if c.args and c.args[0] == "theme_birth_gate"]
    assert len(gate_rows) == 1
    assert "[promote/observe]" in (gate_rows[0].kwargs.get("summary") or gate_rows[0].args[1])
    # The promote audit row carries NO held-at-gate wording (nothing was held).
    promo_rows = [c for c in te.log_audit_event.await_args_list
                  if c.args and c.args[0] == "shadow_themes_promoted"]
    assert "held at the birth gate" not in promo_rows[0].kwargs["summary"]


@pytest.mark.asyncio
async def test_mode_observe_promote_telegram_parity_with_off(monkeypatch):
    # Zero behavioural difference includes the operator surface: the NEW-grad
    # Telegram fires identically in observe and off for the same input.
    msgs = {}
    for mode in ("off", "observe"):
        conn, tele, _ = _wire_promote(
            monkeypatch,
            [{"name": "New Cohort", "tickers": ["N1", "N2", "N3"],
              "thesis": "t", "source": "narrative_cogap"}],
            mode=mode)
        await te.promote_shadow_themes(_MON)
        msgs[mode] = [c.args[0] for c in tele.await_args_list]
    assert msgs["off"] == msgs["observe"] and len(msgs["off"]) == 1


@pytest.mark.asyncio
async def test_mode_observe_keeps_evaluating_watching_cohort_despite_promotion(monkeypatch):
    # Observe fidelity carve-out: night 2 — the cohort was promoted last night
    # (prior row EXISTS) but its ledger row is still 'watching', so the gate
    # keeps evaluating (that's how the two-sighting progression accrues real
    # forward evidence on this lane). Verdict now: 2nd sighting + weak level
    # but rising → birth verdict recorded; promotion proceeds as normal
    # maintenance either way.
    conn, _, _ = _wire_promote(
        monkeypatch,
        [{"name": "Watched Cohort", "tickers": ["W1", "W2", "W3"],
          "thesis": "t", "source": "narrative_cogap"}],
        mode="observe",
        prior_rows=[{"name": "Watched Cohort", "days_active": 1}])
    monkeypatch.setattr(dbmod, "get_recent_birth_candidates", AsyncMock(return_value=[
        {"id": 31, "name": "Watched Cohort", "first_seen": _FRI, "last_seen": _FRI,
         "sightings": 1, "tickers": ["W1", "W2", "W3"], "status": "watching"}]))
    monkeypatch.setattr(dbmod, "get_cohort_rs_snapshot", AsyncMock(return_value=(52.0, 47.0)))
    n = await te.promote_shadow_themes(_MON)
    assert n == 1                                        # still promotes (maintenance)
    rec = dbmod.record_birth_candidate_sighting
    assert rec.await_args.args[0] == 31                  # the watching row was updated
    assert rec.await_args.kwargs["outcome"] == "birth"   # 2nd sighting + rising arm
    assert rec.await_args.kwargs["reason"] == "pass_rs_rising"


@pytest.mark.asyncio
async def test_mode_on_first_crossing_weak_cohort_held_at_gate(monkeypatch):
    # THE previously-ungated bypass: a first-ever crossing (no prior mi_themes
    # row) must clear the gate when ACTING. First sighting + weak-falling RS →
    # held, 0 writes — and the zero-writes SILENT-FAILURE alarm must NOT fire
    # (a deliberate hold is not a failure).
    conn, tele, _ = _wire_promote(
        monkeypatch,
        [{"name": "Hospital Recovery", "tickers": ["H1", "H2", "H3"],
          "thesis": "t", "source": "rs_slope_synthesis"}],
        mode="on")
    n = await te.promote_shadow_themes(_MON)
    assert n == 0
    assert not [c for c in conn.execute.await_args_list
                if "INSERT INTO mi_themes" in c.args[0]]
    # Ledger sighting recorded (the hold is remembered, not discarded).
    assert dbmod.record_birth_candidate_sighting.await_args.kwargs["outcome"] in (
        "await_second_sighting", "held_floor")
    tele.assert_not_awaited()   # no 🎓 ping AND no ⚠️ silent-failure ping
    # The silent-failure audit row must not exist either.
    assert not [c for c in te.log_audit_event.await_args_list
                if c.args and c.args[0] == "shadow_promotion_silent_failure"]


@pytest.mark.asyncio
async def test_mode_on_repromotion_of_live_theme_is_untouched_maintenance(monkeypatch):
    # EXISTING LIVE THEMES ARE UNTOUCHED: a cohort whose name already has a
    # prior mi_themes row bypasses the gate entirely — weak RS and all.
    conn, _, _ = _wire_promote(
        monkeypatch,
        [{"name": "Established Theme", "tickers": ["E1", "E2", "E3"],
          "thesis": "t", "source": "narrative_cogap"}],
        mode="on",
        prior_rows=[{"name": "Established Theme", "days_active": 9}])
    n = await te.promote_shadow_themes(_MON)
    assert n == 1
    written = [c.args[2] for c in conn.execute.await_args_list
               if "INSERT INTO mi_themes" in c.args[0]]
    assert written == ["Established Theme"]
    # In mode 'on' a prior-row cohort with no watching ledger entry is pure
    # maintenance — never evaluated, never recorded.
    dbmod.record_birth_candidate_sighting.assert_not_awaited()


@pytest.mark.asyncio
async def test_mode_on_shadow_v2_candidates_no_longer_auto_promote(monkeypatch):
    # Decision 1, wall 2: even if the reader leaks stale shadow_v2 rows, the
    # promote re-filter (resolve_auto_promote_sources) drops them when acting.
    conn, _, _ = _wire_promote(
        monkeypatch,
        [{"name": "Stale Shadow Cohort", "tickers": ["S1", "S2", "S3", "S4"],
          "thesis": "t", "source": "shadow_v2"}],
        mode="on")
    n = await te.promote_shadow_themes(_MON)
    assert n == 0
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_mode_on_second_sighting_strong_cohort_births_via_promote(monkeypatch):
    conn, _, _ = _wire_promote(
        monkeypatch,
        [{"name": "Real New Theme", "tickers": ["R1", "R2", "R3"],
          "thesis": "t", "source": "narrative_cogap"}],
        mode="on")
    # Prior-day ledger sighting + passing floor.
    monkeypatch.setattr(dbmod, "get_recent_birth_candidates", AsyncMock(return_value=[
        {"id": 11, "name": "Real New Theme", "first_seen": _FRI, "last_seen": _FRI,
         "sightings": 1, "tickers": ["R1", "R2", "R3"], "status": "watching"}]))
    monkeypatch.setattr(dbmod, "get_cohort_rs_snapshot", AsyncMock(return_value=(84.0, 80.0)))
    n = await te.promote_shadow_themes(_MON)
    assert n == 1
    written = [c.args[2] for c in conn.execute.await_args_list
               if "INSERT INTO mi_themes" in c.args[0]]
    assert written == ["Real New Theme"]


# ── coverage_probe job retirement ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_coverage_probe_job_runs_in_off_and_observe_retires_in_on(monkeypatch):
    from agents.market_intelligence import coverage_probe as cp
    from agents.market_intelligence import scheduler as sched
    probe = AsyncMock(return_value={})
    audit = AsyncMock()
    monkeypatch.setattr(cp, "run_coverage_probe", probe)
    monkeypatch.setattr(sched, "log_audit_event", audit)

    for mode in ("off", "observe"):
        probe.reset_mock()
        monkeypatch.setattr(dbmod, "get_theme_birth_gate_mode",
                            AsyncMock(return_value=mode))
        await sched._coverage_probe_job()
        probe.assert_awaited_once()      # off AND observe: the probe runs
    assert not [c for c in audit.await_args_list
                if c.args and c.args[0] == "coverage_probe_retired"]

    probe.reset_mock()
    monkeypatch.setattr(dbmod, "get_theme_birth_gate_mode", AsyncMock(return_value="on"))
    await sched._coverage_probe_job()
    probe.assert_not_awaited()           # on: retired
    retired = [c for c in audit.await_args_list
               if c.args and c.args[0] == "coverage_probe_retired"]
    assert len(retired) == 1             # audited, never silent


# ════════════════════════════════════════════════════════════════════════════
# 4. run_theme_engine — off-parity, observe-parity, the a/a2 port, the gate
# ════════════════════════════════════════════════════════════════════════════

_EX_THEME = {
    "name": "Existing Live Theme", "stage": "Accelerating", "score": 60.0,
    "tickers": ["EX1", "EX2"], "description": "d", "rs_avg": 88.0,
}


def _leader(tk, rs=95.0):
    return {"ticker": tk, "rs_composite": rs, "rs_rank": 10, "sector": "Tech"}


def _drive_engine(monkeypatch, *, mode, discovered, accel=(), recov=(),
                  gate_ledger=(), rs_snapshot=(85.0, 80.0)):
    """Drive te.run_theme_engine with every side-effecting boundary mocked.
    Returns (saved_themes_capture, discover_mock, accel_mock, audits)."""
    leaders = [_leader(f"L{i:02d}", 99.0 - i) for i in range(6)] + \
              [_leader("EX1", 90.0), _leader("EX2", 89.0)]
    monkeypatch.setattr(te, "_preflight_perplexity", AsyncMock())
    monkeypatch.setattr(te, "get_rs_leaders", AsyncMock(return_value=leaders))
    monkeypatch.setattr(te, "get_rs_velocity", AsyncMock(return_value=[]))
    monkeypatch.setattr(te, "get_rs_turners", AsyncMock(return_value=[]))
    monkeypatch.setattr(te, "get_theme_birth_gate_mode", AsyncMock(return_value=mode))
    accel_mock = AsyncMock(return_value=list(accel))
    monkeypatch.setattr(dbmod, "get_rs_accelerators", accel_mock)
    monkeypatch.setattr(dbmod, "get_rs_recovery_slope", AsyncMock(return_value=list(recov)))
    monkeypatch.setattr(te, "_ensure_descriptions", AsyncMock())
    monkeypatch.setattr(te, "get_active_themes", AsyncMock(return_value=[dict(_EX_THEME)]))
    monkeypatch.setattr(te, "_emit_load_diagnostic", AsyncMock())
    monkeypatch.setattr(te, "get_all_theme_exclusions", AsyncMock(return_value={}))
    monkeypatch.setattr(te, "get_operator_protected_set", AsyncMock(return_value=set()))
    monkeypatch.setattr(te, "_rescore_existing_theme",
                        AsyncMock(side_effect=lambda t, *a, **k: (dict(t), [])))
    monkeypatch.setattr(te, "_retro_sweep_flagged_pairs",
                        AsyncMock(side_effect=lambda themes, changelog: themes))
    monkeypatch.setattr(te, "get_globally_banned_tickers", AsyncMock(return_value={}))
    monkeypatch.setattr(te, "get_cooldown_set", AsyncMock(return_value=set()))
    monkeypatch.setattr(te, "_apply_carryforward_deterministic_filter", AsyncMock())
    monkeypatch.setattr(te, "_assign_uncovered_to_themes", AsyncMock(return_value=([], [])))
    discover = AsyncMock(return_value=[dict(d) for d in discovered])
    monkeypatch.setattr(te, "_discover_new_themes", discover)

    async def _score(raw, stocks_by_ticker, today):
        return {"theme_date": today, "name": raw["name"], "stage": "Nascent",
                "score": 50.0, "rs_avg": raw.get("_rs", 85.0),
                "description": raw.get("thesis", ""), "tickers": list(raw["tickers"])}
    monkeypatch.setattr(te, "_score_new_theme", AsyncMock(side_effect=_score))
    monkeypatch.setattr(te, "_get_theme_history", AsyncMock(return_value=[]))
    monkeypatch.setattr(te, "_validate_new_themes_at_birth", AsyncMock())
    audits = AsyncMock()
    monkeypatch.setattr(te, "log_audit_event", audits)
    monkeypatch.setattr(te, "get_theme_subtheme_arm_enabled", AsyncMock(return_value=False))
    monkeypatch.setattr(te, "_merge_overlapping_themes",
                        AsyncMock(side_effect=lambda themes, *a, **k: themes))
    monkeypatch.setattr(te, "_emit_pipeline_diagnostic", AsyncMock())
    monkeypatch.setattr(te, "_enforce_max_themes_per_stock",
                        AsyncMock(side_effect=lambda themes: themes))
    monkeypatch.setattr(te, "_nominate_dominant_split_themes", AsyncMock(return_value=[]))
    monkeypatch.setattr(te, "_run_thesis_merge_pass",
                        AsyncMock(side_effect=lambda themes, *a, **k: themes))
    saved: list = []

    async def _save(themes):
        saved.extend(themes)
    monkeypatch.setattr(te, "_save_themes", AsyncMock(side_effect=_save))
    monkeypatch.setattr(te, "_map_ecosystems_nonfatal", AsyncMock())
    monkeypatch.setattr(te, "_detect_theme_constituent_churn", AsyncMock())
    # Gate db surface (only consulted in observe|on):
    monkeypatch.setattr(dbmod, "get_recent_birth_candidates",
                        AsyncMock(return_value=[dict(r) for r in gate_ledger]))
    monkeypatch.setattr(dbmod, "get_cohort_rs_snapshot", AsyncMock(return_value=rs_snapshot))
    monkeypatch.setattr(dbmod, "record_birth_candidate_sighting", AsyncMock(return_value=1))
    monkeypatch.setattr(tbg, "_p3_annotation", AsyncMock(return_value=(None, None)))
    # audit_gate_outcomes writes via db.log_audit_event (its own namespace).
    monkeypatch.setattr(dbmod, "log_audit_event", AsyncMock())
    return saved, discover, accel_mock, audits


@pytest.mark.asyncio
async def test_mode_off_engine_no_selector_fetch_no_gate_and_newborn_saved(monkeypatch):
    saved, discover, accel_mock, _ = _drive_engine(
        monkeypatch, mode="off",
        discovered=[{"name": "Ungated Newborn", "tickers": ["L00", "L01"], "thesis": "t"}])
    themes, changelog = await te.run_theme_engine(trade_date=_MON)
    # off: the a/a2 selectors are NEVER fetched, the gate surface never touched.
    accel_mock.assert_not_awaited()
    dbmod.get_recent_birth_candidates.assert_not_awaited()
    dbmod.record_birth_candidate_sighting.assert_not_awaited()
    # off: a first-sighting newborn persists exactly as today (ungated).
    assert "Ungated Newborn" in [t["name"] for t in saved]
    assert not [e for e in changelog if e.get("type") == "theme_birth_gated"]
    # Discovery pool = the plain top-40 build — no folded selector names.
    unc_arg = discover.await_args.args[0]
    assert {s["ticker"] for s in unc_arg} <= {f"L{i:02d}" for i in range(6)}


@pytest.mark.asyncio
async def test_mode_observe_engine_births_everything_but_records_verdicts(monkeypatch):
    # THE observe contract on Lane 1: the engine's OUTPUT is identical to
    # 'off' (newborn saved on first sighting, no a/a2 fold changing the
    # discovery input, no changelog gating entries) while the verdict is
    # recorded per candidate and the audit row is tagged /observe.
    accel = [{"ticker": "ACC1", "rs_composite": 62.0, "sector": "Industrials"}]
    saved, discover, accel_mock, _ = _drive_engine(
        monkeypatch, mode="observe", accel=accel,
        discovered=[{"name": "First Sighting", "tickers": ["L02", "L03"], "thesis": "t"}])
    themes, changelog = await te.run_theme_engine(trade_date=_MON)
    # Observe acts on NOTHING: no selector fetch (an a/a2 fold would change
    # what gets discovered — an ACT), theme born exactly as today.
    accel_mock.assert_not_awaited()
    unc_arg = discover.await_args.args[0]
    assert "ACC1" not in {s["ticker"] for s in unc_arg}
    assert "First Sighting" in [t["name"] for t in saved]          # born anyway
    assert not [e for e in changelog if e.get("type") == "theme_birth_gated"]
    # …while the verdict + lever + inputs were recorded for the later review.
    rec = dbmod.record_birth_candidate_sighting
    assert rec.await_args.kwargs["mode"] == "observe"
    assert rec.await_args.kwargs["outcome"] == "await_second_sighting"
    assert rec.await_args.kwargs["rs_avg"] == 85.0
    gate_rows = [c for c in dbmod.log_audit_event.await_args_list
                 if c.args and c.args[0] == "theme_birth_gate"]
    assert len(gate_rows) == 1
    assert "[lane1/observe]" in (gate_rows[0].kwargs.get("summary") or gate_rows[0].args[1])


@pytest.mark.asyncio
async def test_mode_on_a2_port_feeds_discovery_and_gate_filters_births(monkeypatch):
    accel = [{"ticker": "ACC1", "rs_composite": 62.0, "sector": "Industrials"}]
    recov = [{"ticker": "REC1", "rs_now": 55.0, "sector": "Health"}]
    # Two discovered themes: one on its 2nd sighting + passing floor (births),
    # one first-sighted (awaits) — the gate decides, not the LLM.
    saved, discover, accel_mock, audits = _drive_engine(
        monkeypatch, mode="on",
        discovered=[
            {"name": "Twice Sighted Strong", "tickers": ["L00", "L01"], "thesis": "t"},
            {"name": "First Sighting", "tickers": ["L02", "L03"], "thesis": "t"},
        ],
        accel=accel, recov=recov,
        gate_ledger=[{"id": 21, "name": "Twice Sighted Strong", "first_seen": _FRI,
                      "last_seen": _FRI, "sightings": 1,
                      "tickers": ["L00", "L01"], "status": "watching"}],
        rs_snapshot=(85.0, 80.0))
    themes, changelog = await te.run_theme_engine(trade_date=_MON)
    # The a/a2 port: selector names entered the discovery pool (ACC1 at RS 62
    # >= THEME_RS_MIN 50; REC1 via rs_now fallback — the shadow's own filter).
    accel_mock.assert_awaited_once()
    unc_tickers = {s["ticker"] for s in discover.await_args.args[0]}
    assert "ACC1" in unc_tickers and "REC1" in unc_tickers
    # Gate outcomes: the twice-sighted cohort birthed; the first-sighting held.
    saved_names = [t["name"] for t in saved]
    assert "Twice Sighted Strong" in saved_names
    assert "First Sighting" not in saved_names
    gated = [e for e in changelog if e.get("type") == "theme_birth_gated"]
    assert [g["theme"] for g in gated] == ["First Sighting"]
    assert gated[0]["outcome"] == "await_second_sighting"
    # EXISTING LIVE THEMES UNTOUCHED: the pre-existing board theme still saved.
    assert "Existing Live Theme" in saved_names
    # Counter-only observability: ONE theme_birth_gate audit row for the run
    # (emitted via db.log_audit_event from audit_gate_outcomes), mode-tagged.
    gate_rows = [c for c in dbmod.log_audit_event.await_args_list
                 if c.args and c.args[0] == "theme_birth_gate"]
    assert len(gate_rows) == 1
    _summary = gate_rows[0].kwargs.get("summary") or gate_rows[0].args[1]
    assert "[lane1/on]" in _summary
    assert "1 birth" in _summary and "1 awaiting-2nd-sighting" in _summary


@pytest.mark.asyncio
async def test_mode_on_existing_theme_reemission_is_never_gated(monkeypatch):
    # A discovery proposal that lands on a name ALREADY live on the board is a
    # re-emission — it must pass through ungated (merge owns it), leaving the
    # board theme intact. (Leg 3 of existing-live-themes-untouched.)
    saved, _, _, _ = _drive_engine(
        monkeypatch, mode="on",
        discovered=[{"name": "Existing Live Theme", "tickers": ["EX1", "EX2"],
                     "thesis": "t"}])
    themes, changelog = await te.run_theme_engine(trade_date=_MON)
    dbmod.record_birth_candidate_sighting.assert_not_awaited()
    assert not [e for e in changelog if e.get("type") == "theme_birth_gated"]
    assert "Existing Live Theme" in [t["name"] for t in saved]


# ── the forward false-negative signal (operator 2026-08-03) ──────────────────────────────────

def test_the_gate_reports_previously_held_candidates_that_later_passed():
    """The operator asked what would monitor a bad flip. A held candidate that LATER re-presents
    and passes is a theme this gate DELAYED — the only forward measure of the cost he cares about,
    because his north star is spotting a theme EARLY.

    The risk is not hypothetical: the 2026-08-03 replay found 21 of 44 sub-70 births matured, and
    Domestic Steel was born at RS 27.8 and reached 92. The data was already captured in
    mi_theme_birth_candidates and rendered NOWHERE — you had to know to ask."""
    src = open("agents/market_intelligence/theme_birth_gate.py").read()
    assert "_count_delayed_births" in src
    assert "previously-held later PASSED" in src, "it must reach the line the operator reads"


def test_the_counter_cannot_break_the_run_it_observes():
    """This gate already took the entire nightly theme pull down once (2026-07-28). An
    observability counter must never be able to repeat that."""
    import ast
    tree = ast.parse(open("agents/market_intelligence/theme_birth_gate.py").read())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "_count_delayed_births")
    handlers = [h for n in ast.walk(fn) if isinstance(n, ast.Try) for h in n.handlers]
    assert handlers, "the counter must catch its own failure"
    # the except arm must RETURN a value, not re-raise into the caller
    assert any(isinstance(x, ast.Return) for h in handlers for x in ast.walk(h)), \
        "the handler must return a fallback count rather than propagate"


def test_a_zero_count_is_silent():
    """Zero is the healthy reading and must not add noise to every nightly line."""
    src = open("agents/market_intelligence/theme_birth_gate.py").read()
    assert 'if delayed else ""' in src
