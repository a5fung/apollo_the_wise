"""#655 fail-only fold of small themes (operator "ok" 2026-10-10; scope
docs/analysis/655_scope_small_themes_churn_2026-10-10.md, option (iii) with #505's minimum).

A 2-3-member theme that FAILS G3 tonight is dissolved; members that pass the membership test
(already in the home, or co-move >= 0.35 with its basket) with the CLOSEST same-ecosystem 4+-member
theme (#505's closeness key + minimum) move there, the rest are released. It folds only when at
least half the members pass (1 of 2, 2 of 3). Passing small themes and 4+-member themes never fold.

Run: pytest tests/test_655_small_theme_fold.py -v
"""
from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock

import numpy as np
import pytest

from agents.market_intelligence import market_adjusted_correlation as mac
from agents.market_intelligence import theme_engine as te
from agents.market_intelligence.audit_events import (
    THEME_SMALL_FOLDED, THEME_SMALL_FOLD_RAN,
)

N = mac.BELONGING_LOOKBACK_SESSIONS
ECO = "E-ENERGY"
HOME = ["H1", "H2", "H3", "H4", "H5"]          # rides factor A
OTHER = ["O1", "O2", "O3", "O4", "O5", "O6", "O7", "O8"]   # rides factor A too (a second candidate)
TODAY = date(2026, 10, 12)


def _excess(riders=(), noise=(), seed=655):
    rng = np.random.default_rng(seed)
    fa = rng.normal(size=N)
    ex = {tk: fa + 0.3 * rng.normal(size=N) for tk in HOME + OTHER + list(riders)}
    for tk in noise:
        ex[tk] = rng.normal(size=N)
    return ex


def _ctx(ex):
    return te.ComoveContext(before_date=TODAY, excess=ex, n_sessions=N, n_rows=0)


def _plan(board, g3_fail, ex, eco=None, industries=None, **kw):
    eco = eco if eco is not None else {t["name"]: ECO for t in board}
    return te.plan_small_theme_folds(board, set(g3_fail), _ctx(ex), set(ex), eco,
                                     industries or {}, **kw)


def _home(name="Gas Producers", tickers=HOME, desc=""):
    return {"name": name, "stage": "Accelerating", "tickers": list(tickers), "description": desc}


# ── the pure decision ─────────────────────────────────────────────────────────────────────────────

def test_failing_pair_with_one_comoving_member_folds_into_the_home():
    small = {"name": "Appalachian Gas Pair", "stage": "Nascent", "tickers": ["RIDE", "NOIS"]}
    folds, counts = _plan([_home(), small], {small["name"]}, _excess(["RIDE"], ["NOIS"]),
                          industries={"RIDE": "gas", "NOIS": "gas", **{h: "gas" for h in HOME}})
    assert len(folds) == 1
    f = folds[0]
    assert (f.theme, f.home) == ("Appalachian Gas Pair", "Gas Producers")
    assert f.moved == ["RIDE"] and f.released == ["NOIS"]
    assert counts["folded"] == 1 and counts["g3_fail"] == 1


def test_a_passing_small_theme_is_untouched():
    small = {"name": "Appalachian Gas Pair", "stage": "Nascent", "tickers": ["RIDE", "NOIS"]}
    folds, counts = _plan([_home(), small], set(), _excess(["RIDE"], ["NOIS"]),
                          industries={"RIDE": "gas", **{h: "gas" for h in HOME}})
    assert folds == []
    assert counts["small"] == 1 and counts["g3_fail"] == 0


def test_fewer_than_half_passing_does_not_fold():
    small = {"name": "Gas Trio", "stage": "Nascent", "tickers": ["RIDE", "NO1", "NO2"]}
    folds, counts = _plan([_home(), small], {small["name"]}, _excess(["RIDE"], ["NO1", "NO2"]),
                          industries={tk: "gas" for tk in ["RIDE", "NO1", "NO2"] + HOME})
    assert folds == []                        # 1 of 3 passes; 2 are needed
    assert counts["members_fail_test"] == 1


def test_two_of_three_passing_folds_and_releases_the_third():
    small = {"name": "Gas Trio", "stage": "Nascent", "tickers": ["R1", "R2", "NO1"]}
    folds, _ = _plan([_home(), small], {small["name"]}, _excess(["R1", "R2"], ["NO1"]),
                     industries={tk: "gas" for tk in ["R1", "R2", "NO1"] + HOME})
    assert [(f.moved, f.released) for f in folds] == [(["R1", "R2"], ["NO1"])]


def test_the_home_is_the_closest_by_the_505_key_not_the_biggest():
    small = {"name": "Gas Pair", "stage": "Nascent", "tickers": ["RIDE", "NOIS"]}
    big = _home("Broad Energy Basket", OTHER)          # 8 members, all 'gas' -> overlap 0.5 (RIDE only)
    close = _home("Gas Producers", HOME)               # 5 members, gas + pipes -> overlap 1.0
    ind = {"RIDE": "gas", "NOIS": "pipes", **{o: "gas" for o in OTHER},
           **{h: ("gas" if i % 2 else "pipes") for i, h in enumerate(HOME)}}
    folds, _ = _plan([big, close, small], {small["name"]}, _excess(["RIDE"], ["NOIS"]), industries=ind)
    assert [f.home for f in folds] == ["Gas Producers"]
    assert folds[0].industry_overlap == 1.0


def test_a_shared_member_outranks_size_and_industry():
    small = {"name": "Gas Pair", "stage": "Nascent", "tickers": ["H1", "NOIS"]}   # H1 sits in HOME
    folds, _ = _plan([_home("Broad Energy Basket", OTHER), _home(), small], {small["name"]},
                     _excess([], ["NOIS"]), industries={})
    assert [f.home for f in folds] == ["Gas Producers"]
    assert folds[0].moved == [] and folds[0].already_in_home == ["H1"] and folds[0].released == ["NOIS"]


def test_505_minimum_nothing_shared_and_industries_do_not_line_up_no_fold():
    small = {"name": "Gas Pair", "stage": "Nascent", "tickers": ["RIDE", "NOIS"]}
    ind = {"RIDE": "software", "NOIS": "software", **{h: "gas" for h in HOME}}
    folds, _ = _plan([_home(), small], {small["name"]}, _excess(["RIDE"], ["NOIS"]), industries=ind)
    assert folds == []


def test_four_member_themes_never_fold():
    four = {"name": "Gas Four", "stage": "Nascent", "tickers": ["R1", "R2", "R3", "NOIS"]}
    folds, counts = _plan([_home(), four], {four["name"]}, _excess(["R1", "R2", "R3"], ["NOIS"]),
                          industries={tk: "gas" for tk in ["R1", "R2", "R3", "NOIS"] + HOME})
    assert folds == [] and counts["small"] == 0


def test_other_ecosystem_or_unassigned_is_never_a_home():
    small = {"name": "Gas Pair", "stage": "Nascent", "tickers": ["RIDE", "NOIS"]}
    board = [_home(), small]
    ex = _excess(["RIDE"], ["NOIS"])
    ind = {tk: "gas" for tk in ["RIDE", "NOIS"] + HOME}
    f1, c1 = _plan(board, {small["name"]}, ex, eco={"Gas Producers": "E-OTHER", "Gas Pair": ECO},
                   industries=ind)
    f2, c2 = _plan(board, {small["name"]}, ex, eco={"Gas Producers": "E-UNASSIGNED",
                                                    "Gas Pair": "E-UNASSIGNED"}, industries=ind)
    assert f1 == [] and c1["no_home"] == 1
    assert f2 == [] and c2["no_ecosystem"] == 1


def test_operator_exclusion_and_cooldown_bar_a_member_and_protected_themes_never_fold():
    small = {"name": "Gas Pair", "stage": "Nascent", "tickers": ["RIDE", "NOIS"]}
    ex = _excess(["RIDE"], ["NOIS"])
    ind = {tk: "gas" for tk in ["RIDE", "NOIS"] + HOME}
    board = [_home(), small]
    assert _plan(board, {small["name"]}, ex, industries=ind,
                 theme_exclusions={"Gas Producers": {"RIDE"}})[0] == []
    assert _plan(board, {small["name"]}, ex, industries=ind,
                 cooldown_set={("RIDE", "Gas Producers")})[0] == []
    folds, counts = _plan(board, {small["name"]}, ex, industries=ind,
                          protected={("NOIS", "Gas Pair")})
    assert folds == [] and counts["skipped_protected"] == 1


# ── the engine pass (real compute_g3, I/O mocked) ─────────────────────────────────────────────────

@pytest.fixture
def audit(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr(te, "log_audit_event", mock)
    return mock


def _rows(audit, event):
    return [c for c in audit.await_args_list if c.args and c.args[0] == event]


def _wire(monkeypatch, ex, *, toggle=True):
    rng = np.random.default_rng(1)
    for i in range(400):                      # the random-basket control's universe (independent names)
        ex.setdefault(f"U{i:03d}", rng.normal(size=N))
    scores = {tk: {"rs": float(50 + (i % 50)), "sector": None} for i, tk in enumerate(ex)}
    load = AsyncMock(return_value=(_ctx(ex), scores, {}))
    monkeypatch.setattr(te, "_load_small_fold_g3_context", load)
    monkeypatch.setattr(te, "_read_small_fold_toggle", AsyncMock(return_value=toggle))
    monkeypatch.setattr(te, "_read_parent_pass_industries",
                        AsyncMock(return_value={tk: "gas" for tk in ex}))
    from agents.market_intelligence import theme_ecosystems
    monkeypatch.setattr(theme_ecosystems, "load_ecosystem_assignments",
                        AsyncMock(return_value={"Gas Producers": ECO, "Gas Pair": ECO,
                                                "Gas Four": ECO}))
    return load


@pytest.mark.asyncio
async def test_engine_pass_folds_the_failing_pair_and_tombstones_it(monkeypatch, audit):
    ex = _excess(["RIDE"], ["NOIS"])
    _wire(monkeypatch, ex)
    home = _home()
    small = {"name": "Gas Pair", "stage": "Nascent", "tickers": ["RIDE", "NOIS"]}
    changelog: list[dict] = []
    out = await te._fold_small_failing_themes(
        [home, small], {"Gas Producers", "Gas Pair"}, changelog, TODAY,
        theme_exclusions=None, cooldown_set=None, protected=set())
    live = {t["name"]: t for t in out if t["stage"] != "Retired"}
    assert set(live) == {"Gas Producers"}
    assert live["Gas Producers"]["tickers"] == HOME + ["RIDE"]
    tomb = [t for t in out if t["stage"] == "Retired"]
    assert [(t["name"], t["parent_theme"], t["tickers"]) for t in tomb] == [("Gas Pair", "Gas Producers", [])]
    folded = _rows(audit, THEME_SMALL_FOLDED)
    assert len(folded) == 1
    d = json.loads(folded[0].kwargs["detail"])
    assert (d["theme"], d["home"], d["moved"], d["released"]) == ("Gas Pair", "Gas Producers", ["RIDE"], ["NOIS"])
    assert d["g3"]["pass_g3"] is False
    ran = json.loads(_rows(audit, THEME_SMALL_FOLD_RAN)[0].kwargs["detail"])
    assert ran["counts"]["folded"] == 1
    assert changelog == [{"type": "theme_retired", "theme": "Gas Pair", "tickers": ["RIDE", "NOIS"],
                          "via": "small_fold", "into": "Gas Producers", "moved": ["RIDE"],
                          "released": ["NOIS"]}]


@pytest.mark.asyncio
async def test_engine_pass_leaves_a_cohesive_pair_alone(monkeypatch, audit):
    ex = _excess(["R1", "R2"])               # both ride the factor -> the pair beats the random basket
    _wire(monkeypatch, ex)
    small = {"name": "Gas Pair", "stage": "Nascent", "tickers": ["R1", "R2"]}
    out = await te._fold_small_failing_themes(
        [_home(), small], {"Gas Producers", "Gas Pair"}, [], TODAY,
        theme_exclusions=None, cooldown_set=None, protected=set())
    assert [t["name"] for t in out] == ["Gas Producers", "Gas Pair"]
    assert _rows(audit, THEME_SMALL_FOLDED) == []
    assert json.loads(_rows(audit, THEME_SMALL_FOLD_RAN)[0].kwargs["detail"])["counts"]["g3_fail"] == 0


@pytest.mark.asyncio
async def test_engine_pass_newborn_fold_writes_no_tombstone(monkeypatch, audit):
    _wire(monkeypatch, _excess(["RIDE"], ["NOIS"]))
    small = {"name": "Gas Pair", "stage": "Nascent", "tickers": ["RIDE", "NOIS"]}
    out = await te._fold_small_failing_themes(
        [_home(), small], {"Gas Producers"}, [], TODAY,
        theme_exclusions=None, cooldown_set=None, protected=set())
    assert [t["name"] for t in out] == ["Gas Producers"]


@pytest.mark.asyncio
async def test_toggle_off_or_no_small_theme_reads_nothing(monkeypatch, audit):
    load = _wire(monkeypatch, _excess(["RIDE"], ["NOIS"]), toggle=False)
    small = {"name": "Gas Pair", "stage": "Nascent", "tickers": ["RIDE", "NOIS"]}
    themes = [_home(), small]
    assert await te._fold_small_failing_themes(themes, set(), [], TODAY, theme_exclusions=None,
                                                cooldown_set=None, protected=set()) is themes
    load.assert_not_awaited()
    assert audit.await_args_list == []
    te._read_small_fold_toggle.reset_mock()
    only_big = [_home()]
    assert await te._fold_small_failing_themes(only_big, set(), [], TODAY, theme_exclusions=None,
                                                cooldown_set=None, protected=set()) is only_big
    te._read_small_fold_toggle.assert_not_awaited()


def test_toggle_is_discoverable_by_the_drift_check_and_defaults_on():
    from scripts.live_rules import discover_runtime_toggles
    fact = discover_runtime_toggles()[te.SMALL_FOLD_TOGGLE[0]]
    assert fact.env_var == te.SMALL_FOLD_TOGGLE[1] and fact.default is True
    assert fact.where.startswith("agents/market_intelligence/theme_engine.py:")


@pytest.mark.asyncio
async def test_through_the_real_engine_the_fold_tombstones_once_and_the_home_is_saved_bigger(monkeypatch):
    """Drive the REAL run_theme_engine (the shared harness) with the fold un-stubbed: the folded
    incumbent is saved as ONE Retired row pointing at its home (the engine-drop block does not add a
    second), and the home is saved with the moved member."""
    from tests.test_theme_birth_gate import _drive_engine, _FRI, _MON
    real = te._fold_small_failing_themes
    saved, _d, _a, audits = _drive_engine(monkeypatch, mode="off", discovered=[])
    _wire(monkeypatch, _excess(["RIDE"], ["NOIS"]))
    home = {**_home(), "score": 70.0, "rs_avg": 88.0, "theme_date": _FRI}
    small = {"name": "Gas Pair", "stage": "Nascent", "score": 40.0, "rs_avg": 85.0,
             "theme_date": _FRI, "tickers": ["RIDE", "NOIS"], "description": "d"}
    monkeypatch.setattr(te, "get_active_themes", AsyncMock(return_value=[dict(home), dict(small)]))
    from agents.market_intelligence import db as dbmod
    from tests.conftest import make_mock_pool
    monkeypatch.setattr(dbmod, "get_rs_for_tickers", AsyncMock(return_value={
        tk: {"rs_composite": 60.0} for tk in HOME + ["RIDE", "NOIS"]}))
    monkeypatch.setattr(dbmod, "get_sectors_batch", AsyncMock(return_value={}))
    monkeypatch.setattr(te, "_read_assign_comove_toggle", AsyncMock(return_value=False))
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    order: list[str] = []

    async def _arm_b(themes, *a, **k):
        order.append("arm_b")
        return themes

    async def _fold(themes, *a, **k):
        order.append("fold")
        return await real(themes, *a, **k)

    async def _parent(all_themes, *a, **k):
        order.append("parent_pass")
        return []
    save = te._save_themes

    async def _save(themes):
        order.append("save")
        return await save(themes)
    monkeypatch.setattr(te, "_run_thesis_merge_pass", _arm_b)
    monkeypatch.setattr(te, "_fold_small_failing_themes", _fold)
    monkeypatch.setattr(te, "_run_parent_pass", _parent)
    monkeypatch.setattr(te, "_save_themes", _save)
    await te.run_theme_engine(trade_date=_MON)
    assert order == ["arm_b", "fold", "parent_pass", "save"]   # after Arm B, before #505 and the save
    rows = [(t["name"], t["stage"], t.get("parent_theme"), list(t.get("tickers") or [])) for t in saved]
    assert [r for r in rows if r[0] == "Gas Pair"] == [("Gas Pair", "Retired", "Gas Producers", [])]
    assert [r[3] for r in rows if r[0] == "Gas Producers"] == [HOME + ["RIDE"]]
    assert len([c for c in audits.await_args_list if c.args and c.args[0] == THEME_SMALL_FOLDED]) == 1


@pytest.mark.asyncio
async def test_a_failed_fold_read_skips_the_fold_and_never_claims_the_membership_test_fell_back(monkeypatch, audit):
    """The fold's own second read failing must not write `theme_comove_context_failed` ("sector test
    used tonight") — the membership-test sites loaded their own context and did not fall back."""
    from tests.conftest import make_mock_pool
    from agents.market_intelligence import ep_theme_belonging as etb
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[{"ticker": "H1", "rs_composite": 80.0, "sector": "Energy"}])
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(etb, "fetch_closes", AsyncMock(side_effect=RuntimeError("closes read timed out")))
    monkeypatch.setattr(te, "_read_small_fold_toggle", AsyncMock(return_value=True))
    from agents.market_intelligence import theme_ecosystems
    monkeypatch.setattr(theme_ecosystems, "load_ecosystem_assignments",
                        AsyncMock(return_value={"Gas Producers": ECO, "Gas Pair": ECO}))
    themes = [_home(), {"name": "Gas Pair", "stage": "Nascent", "tickers": ["RIDE", "NOIS"]}]
    out = await te._fold_small_failing_themes(themes, {"Gas Pair"}, [], TODAY, theme_exclusions=None,
                                              cooldown_set=None, protected=set())
    assert out is themes
    assert [c.args[0] for c in audit.await_args_list] == [THEME_SMALL_FOLD_RAN]
    assert json.loads(audit.await_args_list[0].kwargs["detail"])["status"] == \
        "skipped: price/score context unavailable"
