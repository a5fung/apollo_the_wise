"""#655 theme move paths (his rulings 2026-10-20 "yes" and 2026-10-21 "Yes" / "Ok"; built 2026-10-24).

Two rules, both in `agents/market_intelligence/theme_engine.py`:

1. DIRECTION — "a sub-theme sits under its parent in the sector cap": a theme is NEVER absorbed into
   its own sub-theme. In Pass 2 a child whose parent is in the same keyword group is processed after
   its parent, holds no cap slot while the parent is kept, and is never a capped theme's target; Pass
   1.5 never absorbs a parent into its child. The 10-19 case: the newborn 4-stock 'Petroleum Refiners'
   was routed PARENT_CHILD under 'Oil & Gas Price Rally…' (containment 1.00), out-scored its parent in
   the cap's slot race, and the PARENT was absorbed into its child; drillers / E&Ps / tankers followed
   on tape co-movement and Wednesday's description check removed 18 of them.
2. DESCRIPTION CHECK ON EVERY MOVED STOCK, both move paths (the Pass-2 sector cap and the fail-only
   fold): the same `_validate_theme_membership` an ordinary new member gets, in its moved-stock mode
   (`removable` = the tape's admits; one batched call per target / home); a stock the check refuses is
   not moved (it keeps its home / goes back to the pool as a tape reject does) and carries the ordinary
   14-day cooldown — but no eviction record (it was never a member).

The replay tests (10-19 / 10-20 refiners nights, the 10-15 apparel fragment) are RED on the parent
commit; the "unchanged" tests are regression guards.

Run: pytest tests/test_655_move_paths.py -v
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
    THEME_MOVE_REJECTED_BY_DESCRIPTION, THEME_SECTOR_CAP_CHILD_UNDER_PARENT,
    THEME_SECTOR_CAP_KEPT_DISTINCT, THEME_SMALL_FOLDED, THEME_SMALL_FOLD_RAN,
)

N = mac.BELONGING_LOOKBACK_SESSIONS
ABSORBED = "theme_sector_cap_absorbed"
NOT_ABSORBED = "theme_sector_cap_not_absorbed"
CHILD_UNDER = "theme_sector_cap_child_under_parent"
MOVE_REJECTED = "theme_move_rejected_by_description"


@pytest.fixture
def audit(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr(te, "log_audit_event", mock)
    return mock


def _rows(audit, event):
    return [c for c in audit.await_args_list if c.args and c.args[0] == event]


def _detail(call):
    return json.loads(call.kwargs.get("detail") or call.args[2])


def _summary(call):
    return call.kwargs.get("summary") or call.args[1]


def _ctx(factors: dict[str, list[str]], noise: list[str] = (), seed: int = 20261024, before=date(2026, 10, 19)):
    """Excess returns: every name under a factor key rides that factor (pairwise ~0.9); `noise` names
    are independent (~0 against any basket, below the 0.35 bar)."""
    rng = np.random.default_rng(seed)
    excess = {}
    for _key, names in factors.items():
        f = rng.normal(size=N)
        for tk in names:
            excess[tk] = f + 0.3 * rng.normal(size=N)
    for tk in noise:
        excess[tk] = rng.normal(size=N)
    return te.ComoveContext(before_date=before, excess=excess, n_sessions=N, n_rows=0)


def _fake_client(remove_list, captured: list | None = None):
    """Async Anthropic client stub for the REAL `_validate_theme_membership`: returns {"remove": [...]}
    and records each prompt (the roster the model was shown)."""
    class _Block:
        type = "text"
        text = json.dumps({"remove": remove_list})

    class _Resp:
        content = [_Block()]
        stop_reason = "end_turn"

    class _Messages:
        async def create(self, *a, **kw):
            if captured is not None:
                captured.append(kw["messages"][0]["content"])
            return _Resp()

    class _Client:
        messages = _Messages()

    return _Client()


def _wire_real_validator(monkeypatch, remove_list):
    """The real validator with its I/O patched: the LLM, the cooldown writer, the protected set.
    Returns (prompts, cooldowns)."""
    prompts: list[str] = []
    cooldowns: list[tuple[str, str]] = []

    async def fake_cooldown(ticker, theme_name, reason=""):
        cooldowns.append((ticker, theme_name))
        return 1

    monkeypatch.setattr(te, "_get_anthropic_client", lambda: _fake_client(remove_list, prompts))
    monkeypatch.setattr(te, "add_validation_cooldown", fake_cooldown)
    monkeypatch.setattr(te, "get_operator_protected_set", AsyncMock(return_value=set()))
    return prompts, cooldowns


# ═══════════════════════════ 1. DIRECTION — the pure ordering helper ═══════════════════════════════

PARENT = "Oil & Gas Price Rally: Integrated Majors, Producers & Refiners"
CHILD = "Petroleum Refiners (Independent Refining & Marketing)"
DRILLERS = "Offshore Drilling Rig Contractors"
EPS = "Natural Gas-Weighted E&P Producers"
PARENT_MEMBERS = ["CVI", "DINO", "MPC", "PSX", "XOM", "CVX", "COP", "OXY"]
CHILD_MEMBERS = ["CVI", "DINO", "MPC", "PSX"]           # containment 1.00 in the parent
DRILLER_MEMBERS = ["RIG", "SDRL", "VAL", "NE"]
EP_MEMBERS = ["CRK", "CNX", "EQT", "AR"]


def _t(name, tickers, score, stage="Nascent"):
    return {"name": name, "tickers": list(tickers), "score": float(score), "stage": stage}


def test_fixture_names_are_all_in_the_oil_gas_group():
    for name in (PARENT, CHILD, DRILLERS, EPS):
        assert te._sector_group(name) == ("oil_gas", 2), name


def test_order_pulls_a_later_parent_up_to_its_child_with_the_child_directly_after():
    """The parent takes the rank the family earned (the child's), the child right behind it — the
    unrelated themes keep their relative order behind the family."""
    themes = [_t(CHILD, CHILD_MEMBERS, 80), _t(DRILLERS, DRILLER_MEMBERS, 75), _t(PARENT, PARENT_MEMBERS, 70),
              _t(EPS, EP_MEMBERS, 60)]
    out = te._cap_order_children_after_parents(themes, {CHILD: PARENT})
    assert [t["name"] for t in out] == [PARENT, CHILD, DRILLERS, EPS]


def test_order_is_the_input_order_when_the_parent_is_absent_in_another_group_or_already_ahead():
    themes = [_t(CHILD, CHILD_MEMBERS, 80), _t(DRILLERS, DRILLER_MEMBERS, 75), _t(EPS, EP_MEMBERS, 60)]
    assert [t["name"] for t in te._cap_order_children_after_parents(themes, {CHILD: PARENT})] == \
        [CHILD, DRILLERS, EPS]                                       # parent not in the list
    assert [t["name"] for t in te._cap_order_children_after_parents(themes, {CHILD: "Satellite Broadband"})] == \
        [CHILD, DRILLERS, EPS]                                       # parent in another keyword group
    assert [t["name"] for t in te._cap_order_children_after_parents(themes, None)] == [CHILD, DRILLERS, EPS]
    ahead = [_t(PARENT, PARENT_MEMBERS, 90), _t(DRILLERS, DRILLER_MEMBERS, 75), _t(CHILD, CHILD_MEMBERS, 70)]
    assert [t["name"] for t in te._cap_order_children_after_parents(ahead, {CHILD: PARENT})] == \
        [PARENT, DRILLERS, CHILD]                                    # already after its parent: unmoved


def test_order_emits_every_theme_exactly_once_even_on_a_link_cycle_and_a_chain():
    a, b, c = _t(PARENT, PARENT_MEMBERS, 80), _t(CHILD, CHILD_MEMBERS, 70), _t(EPS, EP_MEMBERS, 60)
    out = te._cap_order_children_after_parents([a, b, c], {PARENT: CHILD, CHILD: PARENT})
    assert sorted(t["name"] for t in out) == sorted([PARENT, CHILD, EPS]) and len(out) == 3
    # chain: EPS is a child of CHILD, CHILD a child of PARENT, both listed ahead of their parent
    out = te._cap_order_children_after_parents([c, b, a], {EPS: CHILD, CHILD: PARENT})
    assert [t["name"] for t in out] == [PARENT, CHILD, EPS]


def test_order_a_grandparent_ranked_between_the_grandchild_and_the_parent_still_comes_first():
    """2026-10-22 review: a three-level family in one keyword group, ranked grandchild > peer > grandparent >
    parent. Every ancestor listed after the theme being placed is pulled ahead of it, so the family stays in
    family order and the middle theme never takes a slot ahead of its own parent (on a6521c17 the order was
    [CHILD, EPS, DRILLERS, PARENT])."""
    themes = [_t(EPS, EP_MEMBERS, 80), _t(DRILLERS, DRILLER_MEMBERS, 78), _t(PARENT, PARENT_MEMBERS, 75),
              _t(CHILD, CHILD_MEMBERS, 70)]
    out = te._cap_order_children_after_parents(themes, {EPS: CHILD, CHILD: PARENT})
    assert [t["name"] for t in out] == [PARENT, CHILD, EPS, DRILLERS]


def test_order_a_child_waits_for_the_first_occurrence_of_a_duplicated_parent_name():
    """The 10-07 shape: a re-minted namesake. Index-based, so a same-name shell ahead of the child
    counts as the parent being ahead (the child keeps its place)."""
    shell = _t(PARENT, [], 95)
    themes = [shell, _t(CHILD, CHILD_MEMBERS, 80), _t(PARENT, PARENT_MEMBERS, 70)]
    assert [t.get("score") for t in te._cap_order_children_after_parents(themes, {CHILD: PARENT})] == [95, 80, 70]


def test_cap_parent_in_group_is_keyed_on_the_same_keyword_group():
    assert te._cap_parent_in_group(CHILD, "oil_gas", {CHILD: PARENT}) == PARENT
    assert te._cap_parent_in_group(CHILD, "oil_gas", {CHILD: "Satellite Broadband"}) is None
    assert te._cap_parent_in_group(CHILD, "oil_gas", {}) is None and te._cap_parent_in_group(CHILD, "oil_gas", None) is None
    assert te._cap_parent_in_group(CHILD, "oil_gas", {CHILD: CHILD}) is None


# ═══════════════════ 1. DIRECTION — the 10-19 / 10-20 refiners nights through the real merge ═══════════

def _parent_child_adjudicator(calls: list):
    """Route A's test seam (mirrors tests/test_theme_subtheme_routing.py): PARENT_CHILD, child = B."""
    async def adj(theme_a, theme_b, *, client=None, semaphore=None, sectors_by_ticker=None, log_spend=False):
        calls.append((theme_a["name"], theme_b["name"]))
        return {"verdict": "PARENT_CHILD", "child": "B", "reason": "refiners are a slice of the oil rally"}
    return adj


@pytest.fixture
def validator_admits_all(monkeypatch):
    calls: list[dict] = []

    async def fake(theme_name, tickers, changelog, protected=None, removable=None, **kw):
        calls.append({"theme": theme_name, "tickers": list(tickers), "removable": set(removable or ())})
        return list(tickers)
    monkeypatch.setattr(te, "_validate_theme_membership", fake)
    return calls


async def _merge_1019(themes, ctx, *, sub_parents=None, route_a=True, cooldown_set=None):
    """Merge 1 of the night as it ran on 10-19: the parent is the protected incumbent, the child a
    this-run newborn; Route A (THEME_SUBTHEME_ARM on, as in prod) routes the pair PARENT_CHILD in Pass
    1 of the SAME call, so Pass 2 sees the link only through the live `sub_theme_parents` dict."""
    calls: list = []
    sub_parents = {} if sub_parents is None else sub_parents
    sctx = te.make_subtheme_route_ctx(True, adjudicate=_parent_child_adjudicator(calls)) if route_a else None
    out = await te._merge_overlapping_themes(
        themes, {}, protected_names={PARENT}, sub_theme_parents=sub_parents, subtheme_ctx=sctx,
        comove_ctx=ctx, changelog=[], cooldown_set=cooldown_set,
    )
    return out, sub_parents, calls


@pytest.mark.asyncio
async def test_1019_replay_the_parent_is_never_absorbed_into_its_own_child(audit, validator_admits_all):
    """10-19 (`theme_sector_cap_absorbed` source = the parent, target = its newborn child): child 80 >
    drillers 75 > parent 70 > E&Ps 60, oil_gas cap 2. Before: child slot 1, drillers slot 2, the
    PARENT capped and absorbed into the child, the E&Ps judged against the child. After: the parent
    holds the slot the child earned (slot 1), the child sits under it with no slot, the drillers are
    slot 2, and the E&Ps — the third real theme — are judged against the group's real kept top (the
    parent, which they co-move with, so they join IT), never the child."""
    themes = [_t(CHILD, CHILD_MEMBERS, 80), _t(DRILLERS, DRILLER_MEMBERS, 75),
              _t(PARENT, PARENT_MEMBERS, 70, "Mainstream"), _t(EPS, EP_MEMBERS, 60)]
    ctx = _ctx({"oil": PARENT_MEMBERS + EP_MEMBERS, "rigs": DRILLER_MEMBERS})
    out, sub_parents, calls = await _merge_1019(themes, ctx)
    assert calls == [(PARENT, CHILD)] and sub_parents == {CHILD: PARENT}       # Route A fired, as on 10-19
    by_name = {t["name"]: t for t in out}
    assert PARENT in by_name and set(by_name[PARENT]["tickers"]) == set(PARENT_MEMBERS + EP_MEMBERS), [t["name"] for t in out]
    assert CHILD in by_name and set(by_name[CHILD]["tickers"]) == set(CHILD_MEMBERS)
    assert by_name[CHILD]["parent_theme"] == PARENT
    # parent slot 1 (the family's rank), the child under it, drillers slot 2, the E&Ps absorbed into the parent
    assert [t["name"] for t in out] == [PARENT, CHILD, DRILLERS]
    # the positive observable: one child-under-parent row naming both
    under = _rows(audit, CHILD_UNDER)
    assert len(under) == 1 and (_detail(under[0])["child"], _detail(under[0])["parent"]) == (CHILD, PARENT)
    assert "->" not in _summary(under[0])                 # never read as a successor pointer
    # no cap row has the parent or the child as a source, or the child as a target
    rows = _rows(audit, ABSORBED) + _rows(audit, NOT_ABSORBED) + _rows(audit, THEME_SECTOR_CAP_KEPT_DISTINCT)
    assert [(_detail(c)["source"], _detail(c)["target"]) for c in rows] == [(EPS, PARENT)]
    assert not (set(EP_MEMBERS) & set(by_name[CHILD]["tickers"]))


@pytest.mark.asyncio
async def test_1020_replay_the_eps_land_in_the_parent_not_the_child(audit, validator_admits_all):
    """10-20 (`theme_sector_cap_absorbed` CRK/CNX/… -> the child): child 80 > parent 70 > drillers 65 >
    E&Ps 60. Before: child slot 1, parent slot 2, the drillers and E&Ps judged against the CHILD and
    the E&Ps (co-moving with the oil rally) admitted INTO it. After: the parent is slot 1, the child
    under it, the drillers slot 2, and the E&Ps are judged against the parent and join IT."""
    themes = [_t(CHILD, CHILD_MEMBERS, 80), _t(PARENT, PARENT_MEMBERS, 70, "Mainstream"),
              _t(DRILLERS, DRILLER_MEMBERS, 65), _t(EPS, EP_MEMBERS, 60)]
    ctx = _ctx({"oil": PARENT_MEMBERS + EP_MEMBERS, "rigs": DRILLER_MEMBERS})
    out, _sp, _calls = await _merge_1019(themes, ctx)
    by_name = {t["name"]: t for t in out}
    assert set(by_name) == {PARENT, CHILD, DRILLERS}
    assert set(EP_MEMBERS) <= set(by_name[PARENT]["tickers"])
    assert not (set(EP_MEMBERS) & set(by_name[CHILD]["tickers"]))
    absorbed = _rows(audit, ABSORBED)
    assert len(absorbed) == 1 and (_detail(absorbed[0])["source"], _detail(absorbed[0])["target"]) == (EPS, PARENT)
    assert [c["removable"] for c in validator_admits_all] == [set(EP_MEMBERS)]   # the description check saw the movers once
    assert validator_admits_all[0]["theme"] == PARENT


@pytest.mark.asyncio
async def test_a_prior_night_child_link_sits_under_its_parent_too(audit, validator_admits_all):
    """The same rule for a link loaded from yesterday's board (`prior_sub_parents`), with no Route A
    this run: Pass 1 coexists the pair, Pass 2 keeps the child under its parent."""
    themes = [_t(CHILD, CHILD_MEMBERS, 80), _t(DRILLERS, DRILLER_MEMBERS, 75),
              _t(PARENT, PARENT_MEMBERS, 70, "Mainstream")]
    ctx = _ctx({"oil": PARENT_MEMBERS, "rigs": DRILLER_MEMBERS})
    out, _sp, calls = await _merge_1019(themes, ctx, sub_parents={CHILD: PARENT}, route_a=False)
    assert calls == []
    assert [t["name"] for t in out] == [PARENT, CHILD, DRILLERS]
    assert len(_rows(audit, CHILD_UNDER)) == 1 and _rows(audit, ABSORBED) == []


@pytest.mark.asyncio
async def test_a_child_whose_parent_was_capped_away_is_an_ordinary_theme(audit, validator_admits_all):
    """The family's best rank is past the cap (two unrelated themes above the child, the parent below
    it): the parent is pulled up to the child's rank, capped there, and — its members do not co-move
    with the top — kept distinct; a kept-distinct parent still has a roster in `final`, so the child
    sits under it. Then the empty-shell case: a parent emptied upstream is no roof — the child goes
    through the cap on its own and is judged against the real top like any other theme."""
    themes = [_t(DRILLERS, DRILLER_MEMBERS, 90), _t("Oilfield Services", ["A", "B", "C"], 85),
              _t(CHILD, CHILD_MEMBERS, 80), _t(PARENT, PARENT_MEMBERS, 70, "Mainstream")]
    ctx = _ctx({"oil": PARENT_MEMBERS, "rigs": DRILLER_MEMBERS, "svc": ["A", "B", "C"]})
    out, _sp, _c = await _merge_1019(themes, ctx, sub_parents={CHILD: PARENT}, route_a=False)
    names = [t["name"] for t in out]
    assert names == [DRILLERS, "Oilfield Services", PARENT, CHILD], names
    assert len(_rows(audit, THEME_SECTOR_CAP_KEPT_DISTINCT)) == 1 and len(_rows(audit, CHILD_UNDER)) == 1

    audit.reset_mock()
    shell = [_t(DRILLERS, DRILLER_MEMBERS, 78), _t("Oilfield Services", ["A", "B", "C"], 76),
             _t(PARENT, [], 70, "Mainstream"), _t(CHILD, CHILD_MEMBERS, 60)]
    out = await te._merge_overlapping_themes(shell, {}, protected_names=set(), sub_theme_parents={CHILD: PARENT},
                                             comove_ctx=_ctx({"rigs": DRILLER_MEMBERS, "svc": ["A", "B", "C"]},
                                                             noise=CHILD_MEMBERS))
    assert _rows(audit, CHILD_UNDER) == []
    kept = _rows(audit, THEME_SECTOR_CAP_KEPT_DISTINCT)
    assert len(kept) == 1 and _detail(kept[0])["source"] == CHILD and _detail(kept[0])["target"] == DRILLERS


@pytest.mark.asyncio
async def test_pass_1_5_never_absorbs_a_small_parent_into_its_own_child(audit):
    """A 3-member parent with no unique member and a higher-scored child that holds all three: Pass
    1.5's score-direction guard would pick the child as the absorber. The direction rule skips it
    (`theme_pass1_5_skip`, reason `direction:target_is_own_subtheme`); the parent survives. Names
    carry no sector keyword, so Pass 2 is not involved."""
    parent, child = "Wealth Management Platforms", "RIA Aggregators & Custody"
    themes = [{"name": child, "tickers": ["A", "B", "C", "D"], "score": 60.0, "stage": "Nascent"},
              {"name": parent, "tickers": ["A", "B", "C"], "score": 50.0, "stage": "Mainstream"}]
    assert te._sector_group(parent) is None and te._sector_group(child) is None
    # both incumbents (a prior-night child), so the protection guard does not already skip the pair
    out = await te._merge_overlapping_themes(themes, {}, protected_names={parent, child}, sub_theme_parents={child: parent})
    assert {t["name"] for t in out} == {parent, child}
    assert set(next(t for t in out if t["name"] == parent)["tickers"]) == {"A", "B", "C"}
    assert _rows(audit, "theme_pass1_5_absorption") == []
    skips = _rows(audit, "theme_pass1_5_skip")
    assert len(skips) == 1 and "direction:target_is_own_subtheme" in (skips[0].kwargs.get("detail") or skips[0].args[2])


@pytest.mark.asyncio
async def test_unchanged_a_child_in_another_group_and_an_unlinked_theme_race_for_slots_as_today(audit, validator_admits_all):
    """Regression guard: with no same-group link, the cap is the pre-change cap — score order, two
    slots, the third absorbed into the top when its members co-move."""
    themes = [_t(DRILLERS, DRILLER_MEMBERS, 80), _t(EPS, EP_MEMBERS, 75), _t(PARENT, PARENT_MEMBERS, 70)]
    ctx = _ctx({"rigs": DRILLER_MEMBERS + PARENT_MEMBERS, "gas": EP_MEMBERS})
    out = await te._merge_overlapping_themes(themes, {}, protected_names=set(), comove_ctx=ctx,
                                             sub_theme_parents={PARENT: "Satellite Broadband"})
    assert [t["name"] for t in out] == [DRILLERS, EPS]
    assert set(PARENT_MEMBERS) <= set(out[0]["tickers"])
    assert _rows(audit, CHILD_UNDER) == []


def test_child_under_parent_row_is_never_a_successor_pointer():
    successors, cap_rejected = te._successor_pointers_from_audit_rows([
        {"event_type": CHILD_UNDER, "summary": f"Pass2: '{CHILD}' sits under its parent '{PARENT}' (sector group 'oil_gas') — no cap slot, never a target", "detail": ""},
    ])
    assert successors == {} and cap_rejected == {}
    assert THEME_SECTOR_CAP_CHILD_UNDER_PARENT == CHILD_UNDER


# ═══════════════════════ 2. DESCRIPTION CHECK — the sector-cap move path ═══════════════════════════

TANKER = "Crude & Product Tanker Shipping"
REFINERS = "Oil Refining & Marketing"
UTILITIES = "Regulated Natural Gas Distribution Utilities"
TANKER_MEMBERS = ["TNK", "FRO", "INSW", "TRMD", "NAT", "STNG"]


def _cap_themes(third: list[str]) -> list[dict]:
    return [
        {"name": TANKER, "tickers": list(TANKER_MEMBERS), "score": 90.0, "stage": "Mainstream",
         "description": "Crude and product tanker owners riding firm charter rates."},
        {"name": REFINERS, "tickers": ["VLO", "MPC", "PSX", "DINO"], "score": 80.0, "stage": "Nascent"},
        {"name": UTILITIES, "tickers": list(third), "score": 70.0, "stage": "Nascent"},
    ]


async def _cap(themes, ctx, **kw):
    return await te._merge_overlapping_themes(themes, {}, protected_names=set(), comove_ctx=ctx, **kw)


@pytest.mark.asyncio
async def test_cap_a_mover_the_description_check_refuses_is_not_moved(audit, monkeypatch):
    """The real validator in its moved-stock mode. The tape admits XCO and YCO into the tanker theme
    (they ride the tanker factor); the model refuses YCO — and also flags TNK, an EXISTING tanker
    member, which is context, not a removal. XCO moves, YCO does not, TNK stays; the refusal is
    recorded as a refused mover (no eviction record), it gets the ordinary 14-day cooldown on the
    target (in the DB and in the run's cooldown set), the roster the model saw was the target's plus
    the movers, and it was ONE call."""
    prompts, cooldowns = _wire_real_validator(monkeypatch, ["YCO", "TNK"])
    third = ["QA", "QB", "XCO", "YCO"]
    changelog: list[dict] = []
    cooldown_set: set = set()
    out = await _cap(_cap_themes(third), _ctx({"tank": TANKER_MEMBERS + ["XCO", "YCO"]}, noise=["QA", "QB"]),
                     changelog=changelog, cooldown_set=cooldown_set, protected=set())
    tanker = next(t for t in out if t["name"] == TANKER)
    assert "XCO" in tanker["tickers"] and "YCO" not in tanker["tickers"]
    assert set(TANKER_MEMBERS) <= set(tanker["tickers"])                   # TNK untouched
    assert UTILITIES not in {t["name"] for t in out}                       # absorbed (XCO moved)
    assert len(prompts) == 1
    for tk in TANKER_MEMBERS + ["XCO", "YCO"]:
        assert f"- {tk}:" in prompts[0]
    assert "- QA:" not in prompts[0]                                       # tape rejects never reach it
    assert cooldowns == [("YCO", TANKER)] and cooldown_set == {("YCO", TANKER)}
    d = _detail(_rows(audit, ABSORBED)[0])
    assert d["admitted"] == ["XCO"] and d["tape_admitted"] == ["XCO", "YCO"] and d["description_rejected"] == ["YCO"]
    assert d["members"]["YCO"] == {**d["members"]["YCO"], "path": "tape", "verdict": "reject", "description": "reject"}
    assert d["members"]["XCO"]["description"] == "admit" and d["members"]["XCO"]["verdict"] == "admit"
    assert "description" not in d["members"]["QA"]
    refused = _rows(audit, MOVE_REJECTED)
    assert len(refused) == 1 and _summary(refused[0]).startswith("YCO not moved into")
    assert _rows(audit, "ticker_revalidated_out") == [] and _rows(audit, "validation_mass_removal_name_suspect") == []
    assert [e["type"] for e in changelog] == ["theme_move_rejected"] and changelog[0]["ticker"] == "YCO"


@pytest.mark.asyncio
async def test_cap_every_mover_refused_keeps_the_theme_distinct_instead_of_homeless(audit, monkeypatch):
    """The 10-15 apparel shape on the cap path: a cohort the tape would glue into a narrower theme
    (they co-move) but whose descriptions do not fit it. Before 2026-10-24 it was absorbed and the
    next rescore stripped it out, leaving the names homeless. Now every mover is refused -> none
    admitted with >= 3 judged -> the theme is KEPT as its own (it keeps its home), the top theme is
    untouched, the kept row says why."""
    prompts, cooldowns = _wire_real_validator(monkeypatch, ["QA", "QB", "QC"])
    third = ["QA", "QB", "QC"]
    out = await _cap(_cap_themes(third), _ctx({"tank": TANKER_MEMBERS + third}), protected=set(), changelog=[])
    by_name = {t["name"]: t for t in out}
    assert set(by_name) == {TANKER, REFINERS, UTILITIES}
    assert set(by_name[UTILITIES]["tickers"]) == set(third)
    assert set(by_name[TANKER]["tickers"]) == set(TANKER_MEMBERS)
    kept = _rows(audit, THEME_SECTOR_CAP_KEPT_DISTINCT)
    assert len(kept) == 1 and _rows(audit, ABSORBED) == [] and _rows(audit, NOT_ABSORBED) == []
    d = _detail(kept[0])
    assert d["judged"] == 3 and d["passed"] == 0 and d["tape_admitted"] == third and d["description_rejected"] == third
    assert "description check refused 3" in _summary(kept[0]) and "->" not in _summary(kept[0])
    assert sorted(cooldowns) == sorted((tk, TANKER) for tk in third)
    assert len(_rows(audit, MOVE_REJECTED)) == 3 and _rows(audit, "validation_mass_removal_name_suspect") == []


@pytest.mark.asyncio
async def test_cap_validator_is_called_once_with_the_roster_the_admits_and_the_target_thesis(audit, monkeypatch):
    calls: list[dict] = []

    async def fake(theme_name, tickers, changelog, protected=None, removable=None, thesis=None, **kw):
        calls.append({"theme": theme_name, "tickers": list(tickers), "removable": set(removable), "thesis": thesis})
        return list(tickers)
    monkeypatch.setattr(te, "_validate_theme_membership", fake)
    third = ["QA", "XCO", "YCO"]
    await _cap(_cap_themes(third), _ctx({"tank": TANKER_MEMBERS + ["XCO", "YCO"]}, noise=["QA"]))
    assert calls == [{"theme": TANKER, "tickers": TANKER_MEMBERS + ["XCO", "YCO"], "removable": {"XCO", "YCO"},
                      "thesis": "Crude and product tanker owners riding firm charter rates."}]


@pytest.mark.asyncio
async def test_cap_unchanged_no_tape_admit_means_no_validator_call(audit, monkeypatch):
    """Tape rejects and unjudgeable pairs never reach the validator (the 09-25 contract holds)."""
    async def fake(*a, **kw):
        raise AssertionError("no tape admit -> the validator must not be called")
    monkeypatch.setattr(te, "_validate_theme_membership", fake)
    out = await _cap(_cap_themes(["QA", "QB", "QC"]), _ctx({"tank": TANKER_MEMBERS}, noise=["QA", "QB"]))
    # QA/QB: tape rejects; QC: no history -> unjudgeable; 2 judged < 3 -> today's drop, no call
    assert {t["name"] for t in out} == {TANKER, REFINERS}
    assert len(_rows(audit, NOT_ABSORBED)) == 1


# ═══════════════════════ 2. DESCRIPTION CHECK — the fail-only fold move path ═══════════════════════

from tests.test_655_small_theme_fold import HOME, N as _N, TODAY, _excess, _home, _wire  # noqa: E402

assert _N == N
_REAL_VALIDATE = te._validate_theme_membership      # captured at import, before any test patches it


def _excess_multi(riders: dict[str, str], noise=(), contras=(), n_factors: int = 2, home=HOME, seed: int = 655):
    """Excess returns where the HOME rides the SUM of `n_factors` independent factors (A, B, C) and
    each rider rides ONE of them: a rider correlates with the home basket (~0.68 with two factors,
    ~0.55 with three — above the 0.35 bar) while two riders on different factors are UNCORRELATED
    with each other, so a small theme made of them fails the random-basket test (G3) even though
    every member passes the tape against the home. `_excess` (one factor) cannot produce that shape.
    `contras` move AGAINST the home (−0.5 × its factors): a tape reject whose pull on the small
    theme's cohesion is negative, so the fragment's G3 verdict does not sit on the random p95 edge
    (an independent third name can land there by chance — 0.129 vs p95 0.115 on seed 655)."""
    rng = np.random.default_rng(seed)
    # exactly orthogonal factors (QR), so two riders on different factors read ~0 against each other
    # whatever the seed — a 60-session random pair can land at 0.3 by chance (seed 655 did)
    q = np.linalg.qr(rng.normal(size=(N, n_factors)))[0] * np.sqrt(N)
    factors = {k: q[:, i] for i, k in enumerate("ABC"[:n_factors])}
    home_f = sum(factors.values())
    ex = {tk: home_f + 0.3 * rng.normal(size=N) for tk in home}
    for tk, k in riders.items():
        ex[tk] = factors[k] + 0.3 * rng.normal(size=N)
    for tk in noise:
        ex[tk] = rng.normal(size=N)
    for tk in contras:
        ex[tk] = -0.5 * home_f + 0.5 * rng.normal(size=N)
    return ex


def _wire_fold(monkeypatch, ex, remove_list, eco: dict | None = None):
    """The fold's I/O patched (its context read, toggle, industries, ecosystems) + the REAL validator
    with a fake LLM that refuses `remove_list`."""
    _wire(monkeypatch, ex)
    monkeypatch.setattr(te, "_validate_theme_membership", _REAL_VALIDATE)   # `_wire` stubs it admit-all
    prompts, cooldowns = _wire_real_validator(monkeypatch, remove_list)
    if eco is not None:
        from agents.market_intelligence import theme_ecosystems
        monkeypatch.setattr(theme_ecosystems, "load_ecosystem_assignments", AsyncMock(return_value=eco))
    return prompts, cooldowns


def test_fixture_riders_pass_the_tape_and_the_trio_fails_g3():
    """Guard against a vacuous fixture: each rider clears the 0.35 bar against the home basket, and
    the trio of riders on three different factors is below the bar pairwise."""
    ex = _excess_multi({"R1": "A", "R2": "B", "R3": "C"}, n_factors=3)
    ctx = te.ComoveContext(before_date=TODAY, excess=ex, n_sessions=N, n_rows=0)
    for tk in ("R1", "R2", "R3"):
        cv = te._comove_verdict(tk, HOME, ctx)
        assert cv is not None and cv.admit is True and cv.corr >= 0.45, (tk, cv)
    for a, b in (("R1", "R2"), ("R1", "R3"), ("R2", "R3")):
        assert abs(float(np.corrcoef(ex[a], ex[b])[0, 1])) < 0.25, (a, b)


async def _fold(themes, persisted, changelog=None, cooldown_set=None):
    return await te._fold_small_failing_themes(
        themes, persisted, [] if changelog is None else changelog, TODAY,
        theme_exclusions=None, cooldown_set=cooldown_set, protected=set())


@pytest.mark.asyncio
async def test_fold_a_refused_mover_is_released_and_the_fold_still_happens_above_the_bar(audit, monkeypatch):
    """A failing trio whose three members each co-move with the home (on three different factors,
    so the trio itself fails G3); the description check refuses R3. Two of three still pass both
    tests (the bar is 2), so the theme folds: R1, R2 move, R3 is RELEASED with the ordinary 14-day
    cooldown on the home; the rows and the tombstone say so."""
    ex = _excess_multi({"R1": "A", "R2": "B", "R3": "C"}, n_factors=3)
    prompts, cooldowns = _wire_fold(monkeypatch, ex, ["R3"], eco={"Gas Producers": "E-ENERGY", "Gas Trio": "E-ENERGY"})
    small = {"name": "Gas Trio", "stage": "Nascent", "tickers": ["R1", "R2", "R3"]}
    changelog: list[dict] = []
    cooldown_set: set = set()
    out = await _fold([_home(), small], {"Gas Producers", "Gas Trio"}, changelog, cooldown_set)
    live = {t["name"]: t for t in out if t["stage"] != "Retired"}
    assert set(live) == {"Gas Producers"} and live["Gas Producers"]["tickers"] == HOME + ["R1", "R2"]
    tomb = next(t for t in out if t["stage"] == "Retired")
    assert tomb["parent_theme"] == "Gas Producers" and "description check refused: R3" in tomb["description"]
    assert len(prompts) == 1 and all(f"- {tk}:" in prompts[0] for tk in HOME + ["R1", "R2", "R3"])
    assert cooldowns == [("R3", "Gas Producers")] and cooldown_set == {("R3", "Gas Producers")}
    d = _detail(_rows(audit, THEME_SMALL_FOLDED)[0])
    assert (d["moved"], d["released"], d["description_refused"]) == (["R1", "R2"], ["R3"], ["R3"])
    assert d["verdicts"]["R3"]["description"] == "reject" and d["verdicts"]["R3"]["pass"] is False
    assert d["verdicts"]["R1"]["description"] == "admit"
    ran = _detail(_rows(audit, THEME_SMALL_FOLD_RAN)[0])["counts"]
    assert (ran["folded"], ran["desc_checked"], ran["desc_refused"], ran["desc_check_unfolded"]) == (1, 3, 1, 0)
    assert [e for e in changelog if e["type"] == "theme_move_rejected"][0]["ticker"] == "R3"
    assert [e for e in changelog if e["type"] == "theme_retired"][0]["released"] == ["R3"]
    assert _rows(audit, "ticker_revalidated_out") == []


@pytest.mark.asyncio
async def test_1015_apparel_replay_a_fragment_keeps_its_home_when_the_check_refuses_its_movers(audit, monkeypatch):
    """The 10-15 outcome as a fold: the apparel rotation ended as 3-member fragments that fail the
    random-basket test; two of this one's members co-move with the furniture home (the consumer
    rally), so the fold WOULD move them — and the description check refuses both (apparel is not
    furniture). Under the bar after the check -> NOT folded: the fragment keeps its home with all
    three members, the furniture home is unchanged, no FOLDED row, the RAN row counts it, and the
    two refused pairs carry the 14-day cooldown so tomorrow's tape does not re-propose them."""
    furniture = ["MLKN", "HNI", "SCS", "LZB", "FLXS"]
    ex = _excess_multi({"AS": "A", "SHOE": "B"}, contras=["BBWI"], home=furniture)   # BBWI: the tape reject
    home = _home("Commercial, Office & Home Furniture", furniture, "Office and home furniture makers.")
    fragment = {"name": "Specialty Apparel & Footwear Fragment", "stage": "Nascent", "tickers": ["AS", "SHOE", "BBWI"]}
    eco = {home["name"]: "E-CONS", fragment["name"]: "E-CONS"}
    prompts, cooldowns = _wire_fold(monkeypatch, ex, ["AS", "SHOE"], eco=eco)
    monkeypatch.setattr(te, "_read_parent_pass_industries", AsyncMock(return_value={tk: "consumer" for tk in ex}))
    out = await _fold([home, fragment], {home["name"], fragment["name"]})
    assert [(t["name"], t["stage"]) for t in out] == [(home["name"], "Accelerating"), (fragment["name"], "Nascent")]
    assert set(next(t for t in out if t["name"] == fragment["name"])["tickers"]) == {"AS", "SHOE", "BBWI"}
    assert next(t for t in out if t["name"] == home["name"])["tickers"] == furniture
    assert _rows(audit, THEME_SMALL_FOLDED) == []
    ran = _detail(_rows(audit, THEME_SMALL_FOLD_RAN)[0])["counts"]
    assert (ran["g3_fail"], ran["folded"], ran["desc_checked"], ran["desc_refused"], ran["desc_check_unfolded"]) == (1, 0, 2, 2, 1)
    assert sorted(cooldowns) == [("AS", home["name"]), ("SHOE", home["name"])]
    assert len(prompts) == 1 and "Office and home furniture makers." in prompts[0]
    assert len(_rows(audit, MOVE_REJECTED)) == 2


@pytest.mark.asyncio
async def test_fold_one_validator_call_per_home_for_two_folds(audit, monkeypatch):
    """Two failing pairs bound for the same home: ONE call, both movers in `removable`."""
    _wire(monkeypatch, _excess(["RA", "RB"], ["NA", "NB"]))
    calls: list[dict] = []

    async def fake(theme_name, tickers, changelog, protected=None, removable=None, **kw):
        calls.append({"theme": theme_name, "tickers": list(tickers), "removable": set(removable)})
        return list(tickers)
    monkeypatch.setattr(te, "_validate_theme_membership", fake)
    from agents.market_intelligence import theme_ecosystems
    monkeypatch.setattr(theme_ecosystems, "load_ecosystem_assignments", AsyncMock(return_value={
        "Gas Producers": "E-ENERGY", "Gas Pair A": "E-ENERGY", "Gas Pair B": "E-ENERGY"}))
    a = {"name": "Gas Pair A", "stage": "Nascent", "tickers": ["RA", "NA"]}
    b = {"name": "Gas Pair B", "stage": "Nascent", "tickers": ["RB", "NB"]}
    out = await _fold([_home(), a, b], {"Gas Producers", "Gas Pair A", "Gas Pair B"})
    assert {t["name"] for t in out if t["stage"] != "Retired"} == {"Gas Producers"}
    assert calls == [{"theme": "Gas Producers", "tickers": HOME + ["RA", "RB"], "removable": {"RA", "RB"}}]


@pytest.mark.asyncio
async def test_fold_unchanged_no_mover_means_no_validator_call(audit, monkeypatch):
    """A fold whose passers already sit in the home moves nothing -> nothing to check."""
    _wire(monkeypatch, _excess([], ["NOIS"]))

    async def fake(*a, **kw):
        raise AssertionError("nothing moves -> the validator must not be called")
    monkeypatch.setattr(te, "_validate_theme_membership", fake)
    small = {"name": "Gas Pair", "stage": "Nascent", "tickers": ["H1", "NOIS"]}
    out = await _fold([_home(), small], {"Gas Producers", "Gas Pair"})
    assert {t["name"] for t in out if t["stage"] != "Retired"} == {"Gas Producers"}
    d = _detail(_rows(audit, THEME_SMALL_FOLDED)[0])
    assert d["moved"] == [] and d["already_in_home"] == ["H1"] and d["description_refused"] == []


# ═══════════════════════ `_validate_theme_membership` — the moved-stock mode itself ════════════════

@pytest.mark.asyncio
async def test_removable_mode_refuses_only_the_movers_and_writes_refusal_records(audit, monkeypatch):
    prompts, cooldowns = _wire_real_validator(monkeypatch, ["SNDK", "X1"])
    changelog: list[dict] = []
    out = await te._validate_theme_membership("AI Memory & Storage", ["MU", "SNDK", "WDC", "X1", "X2"], changelog,
                                              protected=set(), removable={"X1", "X2"})
    assert out == ["MU", "SNDK", "WDC", "X2"]                               # SNDK (existing) is context, not a removal
    assert cooldowns == [("X1", "AI Memory & Storage")]
    assert [c.args[0] for c in audit.await_args_list] == [MOVE_REJECTED, "validation_cooldown_triggered"]
    assert _summary(_rows(audit, MOVE_REJECTED)[0]) == te._MOVE_REJECTED_SUMMARY_FMT.format(tk="X1", theme="AI Memory & Storage")
    assert changelog == [{"type": "theme_move_rejected", "theme": "AI Memory & Storage", "ticker": "X1",
                          "reason": "description inconsistent with theme 'AI Memory & Storage'"}]
    assert THEME_MOVE_REJECTED_BY_DESCRIPTION == MOVE_REJECTED


@pytest.mark.asyncio
async def test_removable_mode_never_trips_the_mass_removal_tripwire_or_the_name_guard(audit, monkeypatch):
    """8 movers refused into a 4-member target: in the plain mode 8 >= max(3, 12 // 2) would write
    `validation_mass_removal_name_suspect` for the TARGET's name (a 30-day block on that name in
    `_name_recently_mass_evicted`), and 8 `ticker_revalidated_out` rows would trip its second
    pattern. The moved-stock mode writes neither — the refused cohort says nothing about the name."""
    movers = [f"M{i}" for i in range(8)]
    _wire_real_validator(monkeypatch, movers)
    out = await te._validate_theme_membership("Petroleum Refiners", ["CVI", "DINO", "MPC", "PSX"] + movers, [],
                                              protected=set(), removable=set(movers))
    assert out == ["CVI", "DINO", "MPC", "PSX"]
    assert _rows(audit, "validation_mass_removal_name_suspect") == [] and _rows(audit, "ticker_revalidated_out") == []
    assert len(_rows(audit, MOVE_REJECTED)) == 8
    # the refusal summary can never match the #214 matcher's eviction pattern
    _tripwire_pat, removal_pat = te._mass_evicted_patterns("Petroleum Refiners")
    assert removal_pat == "% removed from 'Petroleum Refiners' by validation"
    assert "removed from" not in te._MOVE_REJECTED_SUMMARY_FMT


@pytest.mark.asyncio
async def test_plain_mode_is_byte_identical(audit, monkeypatch):
    prompts, cooldowns = _wire_real_validator(monkeypatch, ["SNDK"])
    changelog: list[dict] = []
    out = await te._validate_theme_membership("AI Memory & Storage", ["MU", "SNDK", "WDC"], changelog, protected=set())
    assert out == ["MU", "WDC"] and cooldowns == [("SNDK", "AI Memory & Storage")]
    assert [c.args[0] for c in audit.await_args_list] == ["ticker_revalidated_out", "validation_cooldown_triggered"]
    assert changelog[0]["type"] == "ticker_revalidated_out"


# ═══════════════ REVIEW FIXES 2026-10-24 (adversarial review of ecf479d3 — each RED on that commit) ═══════════════

from agents.market_intelligence.theme_merge_arm import family_of  # noqa: E402

SVC = "Oilfield Services & Equipment"
SVC_MEMBERS = ["SLB", "HAL", "BKR"]


def test_order_pulls_a_later_parent_up_to_its_childs_index_the_child_directly_after():
    """F4/F6 — 'the parent keeps the group slot': the slot the FAMILY earned (its best member's rank).
    A parent listed after its same-group child is pulled UP to the child's index, the child right
    behind it — never the child pushed DOWN to the parent's rank (which let two unrelated themes take
    both slots and the whole family be absorbed into a peer)."""
    themes = [_t(CHILD, CHILD_MEMBERS, 80), _t(DRILLERS, DRILLER_MEMBERS, 78), _t(SVC, SVC_MEMBERS, 76),
              _t(PARENT, PARENT_MEMBERS, 70)]
    assert [t["name"] for t in te._cap_order_children_after_parents(themes, {CHILD: PARENT})] == \
        [PARENT, CHILD, DRILLERS, SVC]
    # two children ahead of the parent: the parent takes the BEST child's index, both children follow
    two = [_t(CHILD, CHILD_MEMBERS, 80), _t(EPS, EP_MEMBERS, 79), _t(DRILLERS, DRILLER_MEMBERS, 78),
           _t(PARENT, PARENT_MEMBERS, 70)]
    assert [t["name"] for t in te._cap_order_children_after_parents(two, {CHILD: PARENT, EPS: PARENT})] == \
        [PARENT, CHILD, EPS, DRILLERS]


@pytest.mark.asyncio
async def test_1019_replay_with_two_themes_between_child_and_parent_the_family_keeps_its_slot(audit, validator_admits_all):
    """F4/F6 — the 10-19 shape with the parent's real rank unknown: child 80 > drillers 78 > services
    76 > parent 70 (oil_gas, cap 2), Route A firing in the same call, everything co-moving (an oil
    rally) and the description check admitting all (its fail-open on an LLM error). On ecf479d3 the
    child was pushed down to rank 4: drillers + services took both slots, the PARENT was absorbed into
    the drillers (majors and refiners inside a rig theme) and the child followed. Now the parent holds
    the slot the child earned, the child sits under it, and the services are judged against the parent."""
    themes = [_t(CHILD, CHILD_MEMBERS, 80), _t(DRILLERS, DRILLER_MEMBERS, 78), _t(SVC, SVC_MEMBERS, 76),
              _t(PARENT, PARENT_MEMBERS, 70, "Mainstream")]
    ctx = _ctx({"oil": PARENT_MEMBERS + DRILLER_MEMBERS + SVC_MEMBERS})
    out, sub_parents, calls = await _merge_1019(themes, ctx)
    assert calls == [(PARENT, CHILD)] and sub_parents == {CHILD: PARENT}
    names = [t["name"] for t in out]
    assert names == [PARENT, CHILD, DRILLERS], names                       # parent slot 1, child under, drillers slot 2
    by_name = {t["name"]: t for t in out}
    assert set(PARENT_MEMBERS) <= set(by_name[PARENT]["tickers"]) and set(SVC_MEMBERS) <= set(by_name[PARENT]["tickers"])
    assert set(by_name[CHILD]["tickers"]) == set(CHILD_MEMBERS) and by_name[CHILD]["parent_theme"] == PARENT
    under = _rows(audit, CHILD_UNDER)
    assert len(under) == 1 and _detail(under[0])["child"] == CHILD
    absorbed = _rows(audit, ABSORBED)
    assert [(_detail(c)["source"], _detail(c)["target"]) for c in absorbed] == [(SVC, PARENT)]
    for c in absorbed + _rows(audit, NOT_ABSORBED) + _rows(audit, THEME_SECTOR_CAP_KEPT_DISTINCT):
        assert _detail(c)["source"] not in (PARENT, CHILD) and _detail(c)["target"] != CHILD


@pytest.mark.asyncio
async def test_a_child_ranked_past_the_cap_sits_under_its_kept_parent_instead_of_folding_into_the_top(audit, validator_admits_all):
    """F8 — DECLARED behaviour (the ruling: 'sits under its parent or folds into it'): a same-group child
    ranked PAST the cap behind a kept parent sits under it with no slot, where the pre-change cap
    absorbed it into the group's TOP theme (its parent only when the parent happened to be the top).
    A cap-2 group can therefore carry its two kept themes plus their sub-themes — the cap counts
    families, not slices. The observable: `theme_sector_cap_child_under_parent` rows on ordinary nights."""
    themes = [_t(PARENT, PARENT_MEMBERS, 90, "Mainstream"), _t(DRILLERS, DRILLER_MEMBERS, 80), _t(CHILD, CHILD_MEMBERS, 70)]
    ctx = _ctx({"oil": PARENT_MEMBERS, "rigs": DRILLER_MEMBERS})
    out = await te._merge_overlapping_themes(themes, {}, protected_names={PARENT, CHILD}, sub_theme_parents={CHILD: PARENT},
                                             comove_ctx=ctx, changelog=[])
    assert [t["name"] for t in out] == [PARENT, DRILLERS, CHILD]
    assert len(_rows(audit, CHILD_UNDER)) == 1 and _rows(audit, ABSORBED) == [] and validator_admits_all == []


@pytest.mark.asyncio
async def test_cap_kept_distinct_survives_the_next_pass_on_the_refusals_cooldown(audit, monkeypatch):
    """F1 — merge 2 of a split night, and every night for the next 14 days: the three refused pairs
    now sit in `cooldown_set` (the DB row `get_cooldown_set` reloads), so `_membership_path` routes
    them 'cooldown' and the tape never sees them. On ecf479d3 only tape-judged members counted, so
    judged fell to 0 and the theme was DROPPED homeless on pass 2 — the 10-15 outcome one night late.
    A refusal on record counts as judged: the theme is kept distinct again, with no validator call."""
    prompts, cooldowns = _wire_real_validator(monkeypatch, ["QA", "QB", "QC"])
    third = ["QA", "QB", "QC"]
    ctx = _ctx({"tank": TANKER_MEMBERS + third})
    cooldown_set: set = set()
    out1 = await _cap(_cap_themes(third), ctx, protected=set(), changelog=[], cooldown_set=cooldown_set)
    assert UTILITIES in {t["name"] for t in out1} and cooldown_set == {(tk, TANKER) for tk in third}
    audit.reset_mock()
    out2 = await _cap(_cap_themes(third), ctx, protected=set(), changelog=[], cooldown_set=cooldown_set)
    by_name = {t["name"]: t for t in out2}
    assert set(by_name) == {TANKER, REFINERS, UTILITIES}, sorted(by_name)
    assert set(by_name[UTILITIES]["tickers"]) == set(third) and set(by_name[TANKER]["tickers"]) == set(TANKER_MEMBERS)
    kept = _rows(audit, THEME_SECTOR_CAP_KEPT_DISTINCT)
    assert len(kept) == 1 and _rows(audit, NOT_ABSORBED) == [] and _rows(audit, ABSORBED) == []
    d = _detail(kept[0])
    assert (d["judged"], d["judged_tape"], d["judged_cooldown"], d["passed"]) == (3, 0, 3, 0)
    assert all(d["members"][tk]["path"] == "cooldown" for tk in third)
    assert "on cooldown 3" in _summary(kept[0])
    assert len(prompts) == 1 and len(cooldowns) == 3                       # pass 1 only; a pair on cooldown never reaches the validator


@pytest.mark.asyncio
async def test_unchanged_biotech_per_family_branch_keeps_pure_score_order_for_a_parent_child_pair(audit):
    """F2/F7 — the per-family (biotech) branch is byte-identical: it has no absorption target, so the
    direction rule has nothing to protect there and the ruling did not cover it. A same-family child
    that out-scores its parent keeps the family slot and the parent is dropped, as on the parent commit
    (`_cap_parent_in_group` returns None for a per-family group, so no reorder and no sits-under)."""
    parent = "Oncology Biotech: Clinical-Stage Cancer Therapeutics"
    child = "Oncology Biotech: ADC Cancer Drug Developers"
    assert te._sector_group(parent) == te._sector_group(child) == ("biotech", te.PER_FAMILY_CAP)
    assert family_of(parent) == family_of(child) == "oncology"
    assert te._cap_parent_in_group(child, "biotech", {child: parent}) is None
    themes = [_t(child, ["A1", "A2", "A3"], 90), _t(parent, ["B1", "B2", "B3", "B4", "B5", "B6", "B7"], 80, "Mainstream")]
    out = await te._merge_overlapping_themes(themes, {}, protected_names={parent, child}, sub_theme_parents={child: parent})
    assert [t["name"] for t in out] == [child]
    dropped = _rows(audit, "theme_sector_cap_dropped")
    assert len(dropped) == 1 and _summary(dropped[0]).startswith(f"'{parent}' dropped") and "slot taken" in _summary(dropped[0])
    assert _rows(audit, CHILD_UNDER) == []


@pytest.mark.asyncio
async def test_fold_never_dissolves_a_parent_into_its_own_sub_theme(audit, monkeypatch):
    """F3 — the fail-only fold is a move path too: a 3-member parent failing the random-basket test,
    whose only ecosystem home is its own sub-theme (holding the parent's two riders, so it ranks first
    by shared members). The link is `sub_theme_parents` — a prior-night child does NOT carry
    `parent_theme` mid-pipeline (#471). On ecf479d3 the parent was folded into its child and retired
    with the child as its successor. Now: not folded, counted under its own reason."""
    ex = _excess_multi({"R1": "A", "R2": "B"}, contras=["C1"], n_factors=2)
    _wire(monkeypatch, ex)
    from agents.market_intelligence import theme_ecosystems
    child = {"name": "Gas Producers Child", "stage": "Accelerating", "tickers": HOME + ["R1", "R2"], "description": ""}
    parent = {"name": "Gas Parent", "stage": "Mainstream", "tickers": ["R1", "R2", "C1"]}
    monkeypatch.setattr(theme_ecosystems, "load_ecosystem_assignments",
                        AsyncMock(return_value={child["name"]: "E-ENERGY", parent["name"]: "E-ENERGY"}))
    out = await te._fold_small_failing_themes([child, parent], {child["name"], parent["name"]}, [], TODAY,
                                              theme_exclusions=None, cooldown_set=set(), protected=set(),
                                              sub_theme_parents={child["name"]: parent["name"]})
    assert [(t["name"], t["stage"]) for t in out] == [(child["name"], "Accelerating"), (parent["name"], "Mainstream")]
    assert next(t for t in out if t["name"] == parent["name"])["tickers"] == ["R1", "R2", "C1"]
    assert _rows(audit, THEME_SMALL_FOLDED) == []
    ran = _detail(_rows(audit, THEME_SMALL_FOLD_RAN)[0])["counts"]
    assert (ran["g3_fail"], ran["folded"], ran["no_home_own_subtheme"], ran["no_home"]) == (1, 0, 1, 0)


@pytest.mark.asyncio
async def test_fold_a_child_still_folds_into_its_own_parent(audit, monkeypatch):
    """The other direction is a ruled outcome ('sits under its parent OR folds into it'): a failing
    2-member child whose parent is its home folds into the parent as before."""
    _wire(monkeypatch, _excess(["RIDE"], ["NOIS"]))
    small = {"name": "Gas Pair", "stage": "Nascent", "tickers": ["RIDE", "NOIS"]}
    out = await te._fold_small_failing_themes([_home(), small], {"Gas Producers", "Gas Pair"}, [], TODAY,
                                              theme_exclusions=None, cooldown_set=set(), protected=set(),
                                              sub_theme_parents={"Gas Pair": "Gas Producers"})
    assert {t["name"] for t in out if t["stage"] != "Retired"} == {"Gas Producers"}
    assert len(_rows(audit, THEME_SMALL_FOLDED)) == 1


@pytest.mark.asyncio
async def test_removable_mode_refuses_a_mover_even_when_the_target_has_one_member(audit, monkeypatch):
    """F9 — the validator's minimum-survivor guard is for the REMOVAL mode (never prune a theme below
    2). In the moved-stock mode a refusal never shrinks the target's roster, so the guard must not
    admit a refused mover into a 1-member target (on ecf479d3 it did: no cooldown, no refusal record)."""
    prompts, cooldowns = _wire_real_validator(monkeypatch, ["XCO"])
    out = await te._validate_theme_membership("Crude Tanker Shipping", ["FRO", "XCO"], [], protected=set(), removable={"XCO"})
    assert out == ["FRO"] and cooldowns == [("XCO", "Crude Tanker Shipping")]
    assert len(_rows(audit, MOVE_REJECTED)) == 1 and len(prompts) == 1
