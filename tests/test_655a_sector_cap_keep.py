"""#655 (a) — the Pass-2 sector cap KEEPS a theme that provably does not move with its group's top
theme, and a capped theme is never tested against itself.

KEEP RULE (operator ruling 2026-10-05, "yes" 2026-10-09; replay `scripts/probes/_655a/replay.py`):
when the cap would move a theme's members into the group's top theme and AT LEAST 3 of them were
JUDGED by the co-movement test (path "tape") and NONE reached the 0.35 bar and none already sits in
the top theme, the theme is kept as its own theme tonight. It does not count against the group's cap;
ONE `theme_sector_cap_kept_distinct` row replaces the `not_absorbed` row. A partly-passing theme keeps
the absorb path; < 3 judged (or unjudgeable) keeps today's drop.

THE BUG (2026-10-07, prod): discovery re-minted an EXISTING protected name ('Global Oil & Gas
Producers and Refiners', 8 stocks). Pass 1's protect-strip emptied the newcomer (fewer members than
the protected namesake) but left the empty shell in the list; as the higher-scored oil_gas theme it
took a cap slot and became the group's "top theme", and the real 19-member namesake was then capped
and tested against that empty basket: 19 of 19 `thin_basket`, source == target.

Run: pytest tests/test_655a_sector_cap_keep.py -v
"""
from __future__ import annotations

import json
from datetime import date

import numpy as np
import pytest

from agents.market_intelligence import market_adjusted_correlation as mac
from agents.market_intelligence import theme_engine as te
from agents.market_intelligence.audit_events import THEME_SECTOR_CAP_KEPT_DISTINCT

TANKER = "Crude & Product Tanker Shipping"
REFINERS = "Oil Refining & Marketing"
UTILITIES = "Regulated Natural Gas Distribution Utilities"
TANKER_MEMBERS = ["TNK", "FRO", "INSW", "TRMD", "NAT", "STNG"]
N_SESSIONS = mac.BELONGING_LOOKBACK_SESSIONS
KEPT_EVENT = "theme_sector_cap_kept_distinct"


def _ctx(noise: list[str], riders: list[str] = ()) -> te.ComoveContext:
    """Tanker names ride one factor; every name in `noise` is independent noise (reads ~0 against
    the tanker basket, below the 0.35 bar); every name in `riders` rides the tanker factor (passes)."""
    rng = np.random.default_rng(20261009)
    factor = rng.normal(size=N_SESSIONS)
    excess = {tk: factor + 0.3 * rng.normal(size=N_SESSIONS) for tk in TANKER_MEMBERS}
    for tk in riders:
        excess[tk] = factor + 0.3 * rng.normal(size=N_SESSIONS)
    for tk in noise:
        excess[tk] = rng.normal(size=N_SESSIONS)
    return te.ComoveContext(before_date=date(2026, 10, 8), excess=excess,
                            n_sessions=N_SESSIONS, n_rows=0)


def _themes(third: list[str]) -> list[dict]:
    assert te._sector_group(TANKER) == ("oil_gas", 2)
    assert te._sector_group(UTILITIES) == ("oil_gas", 2)
    return [
        {"name": TANKER, "tickers": list(TANKER_MEMBERS), "score": 90.0, "stage": "Mainstream"},
        {"name": REFINERS, "tickers": ["VLO", "MPC", "PSX", "DINO"], "score": 80.0, "stage": "Nascent"},
        {"name": UTILITIES, "tickers": list(third), "score": 70.0, "stage": "Nascent"},
    ]


@pytest.fixture
def audit(monkeypatch):
    from unittest.mock import AsyncMock
    mock = AsyncMock()
    monkeypatch.setattr(te, "log_audit_event", mock)
    return mock


@pytest.fixture(autouse=True)
def _validator_must_not_run(monkeypatch):
    async def fake(*a, **kw):
        raise AssertionError("the cap never hands a pair to the LLM validator (fail closed)")
    monkeypatch.setattr(te, "_validate_theme_membership", fake)


def _rows(audit, event):
    return [c for c in audit.await_args_list if c.args and c.args[0] == event]


def _detail(call):
    return json.loads(call.kwargs.get("detail") or call.args[2])


def _summary(call):
    return call.kwargs.get("summary") or call.args[1]


async def _run(themes, ctx, **kw):
    return await te._merge_overlapping_themes(themes, {}, protected_names=kw.pop("protected_names", set()),
                                              comove_ctx=ctx, **kw)


# ── the keep rule ────────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_kept_when_three_judged_and_none_passed(audit):
    """3 members judged against the top theme, none at the bar -> the theme SURVIVES with its own
    roster, the top theme is untouched, and exactly one kept_distinct row is written (and no
    not_absorbed row)."""
    third = ["QA", "QB", "QC"]
    out = await _run(_themes(third), _ctx(noise=third))
    by_name = {t["name"]: t for t in out}
    assert set(by_name) == {TANKER, REFINERS, UTILITIES}, set(by_name)
    assert set(by_name[UTILITIES]["tickers"]) == set(third)
    assert set(by_name[TANKER]["tickers"]) == set(TANKER_MEMBERS)      # nothing moved
    kept = _rows(audit, KEPT_EVENT)
    assert len(kept) == 1, [c.args[0] for c in audit.await_args_list]
    d = _detail(kept[0])
    assert (d["source"], d["group"], d["target"]) == (UTILITIES, "oil_gas", TANKER)
    assert d["judged"] == 3 and d["passed"] == 0
    assert "kept" in _summary(kept[0]) and "->" not in _summary(kept[0])   # never read as a successor pointer
    assert _rows(audit, "theme_sector_cap_not_absorbed") == []
    assert _rows(audit, "theme_sector_cap_absorbed") == []


@pytest.mark.asyncio
async def test_event_name_is_the_registered_constant():
    assert THEME_SECTOR_CAP_KEPT_DISTINCT == KEPT_EVENT


@pytest.mark.asyncio
async def test_guard_members_do_not_block_the_keep(audit):
    """Cooldown / exclusion members are not JUDGED (they neither count toward the 3 nor block):
    3 judged noise + 1 operator-excluded -> still kept, judged == 3."""
    third = ["QA", "QB", "QC", "QX"]
    out = await _run(_themes(third), _ctx(noise=third), theme_exclusions={TANKER: {"QX"}})
    assert UTILITIES in {t["name"] for t in out}
    d = _detail(_rows(audit, KEPT_EVENT)[0])
    assert d["judged"] == 3 and d["passed"] == 0


@pytest.mark.asyncio
async def test_one_passing_member_keeps_todays_absorb_path(audit):
    """A theme with a member that co-moves with the top theme is NOT kept: the passer is absorbed,
    the theme is capped away, and no kept row exists."""
    third = ["QA", "QB", "XCO"]
    out = await _run(_themes(third), _ctx(noise=["QA", "QB"], riders=["XCO"]))
    names = {t["name"] for t in out}
    assert names == {TANKER, REFINERS}
    assert "XCO" in next(t for t in out if t["name"] == TANKER)["tickers"]
    assert _rows(audit, KEPT_EVENT) == []
    assert len(_rows(audit, "theme_sector_cap_absorbed")) == 1


@pytest.mark.asyncio
async def test_fewer_than_three_judged_is_dropped_as_today(audit):
    third = ["QA", "QB"]
    out = await _run(_themes(third), _ctx(noise=third))
    assert {t["name"] for t in out} == {TANKER, REFINERS}
    assert _rows(audit, KEPT_EVENT) == []
    assert len(_rows(audit, "theme_sector_cap_not_absorbed")) == 1


@pytest.mark.asyncio
async def test_unjudgeable_members_are_dropped_as_today(audit):
    """No price history for the members -> unjudgeable -> judged == 0 -> today's drop, not a keep."""
    third = ["QA", "QB", "QC"]
    out = await _run(_themes(third), _ctx(noise=[]))
    assert {t["name"] for t in out} == {TANKER, REFINERS}
    assert _rows(audit, KEPT_EVENT) == []
    assert len(_rows(audit, "theme_sector_cap_not_absorbed")) == 1


@pytest.mark.asyncio
async def test_no_context_is_dropped_as_today(audit):
    third = ["QA", "QB", "QC"]
    out = await _run(_themes(third), None)
    assert {t["name"] for t in out} == {TANKER, REFINERS}
    assert _rows(audit, KEPT_EVENT) == []


@pytest.mark.asyncio
async def test_member_already_in_the_top_theme_is_not_kept(audit):
    """Replay condition: a theme with a member already in the top theme has that theme as its
    successor (today's pointer) — never kept."""
    third = ["QA", "QB", "QC", TANKER_MEMBERS[0]]
    out = await _run(_themes(third), _ctx(noise=third[:3]))
    assert UTILITIES not in {t["name"] for t in out}
    assert _rows(audit, KEPT_EVENT) == []
    assert len(_rows(audit, "theme_sector_cap_absorbed")) == 1


@pytest.mark.asyncio
async def test_kept_theme_takes_no_cap_slot_and_other_themes_are_unchanged(audit):
    """Cap order is unchanged: the two top-scored themes hold the two slots, a kept theme sits
    after them without taking a slot (a later capped theme is still capped), the kept theme is
    never a later theme's target, and the output order is the score order as today."""
    kept_members = ["QA", "QB", "QC"]
    drop_members = ["QD", "QE"]                      # 2 judged -> dropped as today
    themes = _themes(kept_members) + [
        {"name": "Upstream Oil & Gas Royalty Holdings", "tickers": list(drop_members), "score": 60.0,
         "stage": "Nascent"},
    ]
    out = await _run(themes, _ctx(noise=kept_members + drop_members))
    assert [t["name"] for t in out] == [TANKER, REFINERS, UTILITIES]
    kept = _rows(audit, KEPT_EVENT)
    dropped = _rows(audit, "theme_sector_cap_not_absorbed")
    assert len(kept) == 1 and len(dropped) == 1
    # the later capped theme was tested against the group's real top, not the kept theme
    assert _detail(dropped[0])["target"] == TANKER
    assert _detail(kept[0])["target"] == TANKER
    assert set(next(t for t in out if t["name"] == TANKER)["tickers"]) == set(TANKER_MEMBERS)


# ── the self-comparison bug ──────────────────────────────────────────────────────────────────────

INCUMBENT = "Global Oil & Gas Producers and Refiners"
INCUMBENT_MEMBERS = [f"G{i:02d}" for i in range(19)]
FUEL = "Fuel Cell & Gas Power Generation Equipment"
FUEL_MEMBERS = ["FC1", "FC2", "FC3", "FC4"]
APPALACHIAN = "Appalachian Natural Gas Producers"


def _oct7_themes() -> list[dict]:
    return [
        # the re-minted newcomer: SAME NAME as the protected incumbent, higher score, 8 of its members
        {"name": INCUMBENT, "tickers": list(INCUMBENT_MEMBERS[:8]), "score": 85.0, "stage": "Nascent"},
        {"name": FUEL, "tickers": list(FUEL_MEMBERS), "score": 80.0, "stage": "Nascent"},
        {"name": INCUMBENT, "tickers": list(INCUMBENT_MEMBERS), "score": 70.0, "stage": "Mainstream"},
        {"name": APPALACHIAN, "tickers": ["AP1", "AP2", "AP3", "AP4"], "score": 60.0, "stage": "Nascent"},
    ]


def _oct7_ctx() -> te.ComoveContext:
    rng = np.random.default_rng(20261007)
    factor = rng.normal(size=N_SESSIONS)
    excess = {tk: factor + 0.3 * rng.normal(size=N_SESSIONS) for tk in FUEL_MEMBERS}
    for tk in INCUMBENT_MEMBERS + ["AP1", "AP2", "AP3", "AP4"]:
        excess[tk] = rng.normal(size=N_SESSIONS)
    return te.ComoveContext(before_date=date(2026, 10, 6), excess=excess,
                            n_sessions=N_SESSIONS, n_rows=0)


@pytest.mark.asyncio
async def test_oct7_shape_a_capped_theme_is_never_tested_against_itself(audit):
    """The 10-07 shape, through the real Pass 1 (protect-strip empties the newcomer): the incumbent
    keeps its slot with its 19 members, no audit row has source == target, and the capped theme is
    judged against the group's real kept top (the 4-member Fuel Cell theme), not the empty shell."""
    out = await _run(_oct7_themes(), _oct7_ctx(), protected_names={INCUMBENT})
    real = [t for t in out if t["name"] == INCUMBENT and t.get("tickers")]
    assert len(real) == 1 and set(real[0]["tickers"]) == set(INCUMBENT_MEMBERS), [
        (t["name"], len(t.get("tickers") or [])) for t in out]
    cap_rows = [c for c in audit.await_args_list
                if c.args and c.args[0] in ("theme_sector_cap_absorbed", "theme_sector_cap_not_absorbed",
                                            KEPT_EVENT)]
    assert cap_rows, "the fixture must reach the cap (Appalachian is the third non-empty group theme)"
    for c in cap_rows:
        d = _detail(c)
        target, source = d["target"], d["source"]
        assert source != target, d
        assert target == FUEL, d


@pytest.mark.asyncio
async def test_an_empty_shell_is_never_a_target_and_takes_no_slot(audit):
    """Direct form of the same defect without Pass 1: an empty-roster theme that out-scores the
    group is neither a cap slot nor the top theme."""
    themes = [
        {"name": "Oil Services Shell", "tickers": [], "score": 95.0, "stage": "Nascent"},
        *_themes(["QA", "QB", "QC"]),
    ]
    out = await _run(themes, _ctx(noise=["QA", "QB", "QC"]))
    names = [t["name"] for t in out]
    assert TANKER in names and REFINERS in names and UTILITIES in names, names
    d = _detail(_rows(audit, KEPT_EVENT)[0])
    assert d["target"] == TANKER


@pytest.mark.asyncio
async def test_an_empty_shell_past_the_cap_is_capped_as_today(audit):
    """Unchanged: an emptied theme that lands past the cap still gets today's 'empty at the cap'
    row and is not passed through."""
    themes = _themes(["QA", "QB", "QC"])
    themes[2]["tickers"] = []
    out = await _run(themes, _ctx(noise=["QA"]))
    assert {t["name"] for t in out} == {TANKER, REFINERS}
    rows = _rows(audit, "theme_sector_cap_not_absorbed")
    assert len(rows) == 1 and "empty at the cap" in _summary(rows[0])


@pytest.mark.asyncio
async def test_a_same_named_theme_with_members_is_never_the_target(audit):
    """Review 2026-10-09: the empty-roster guard covers the 10-07 / 10-08 re-mints, but a same-named
    theme that still HAS members after Pass 1 (disjoint rosters, nothing protected) must not become
    its namesake's target either — the capped theme is judged against the group's other kept top."""
    themes = [
        {"name": TANKER, "tickers": list(TANKER_MEMBERS), "score": 95.0, "stage": "Mainstream"},
        {"name": REFINERS, "tickers": ["VLO", "MPC", "PSX", "DINO"], "score": 90.0, "stage": "Nascent"},
        {"name": TANKER, "tickers": ["QA", "QB", "QC"], "score": 60.0, "stage": "Nascent"},
    ]
    await _run(themes, _ctx(noise=["QA", "QB", "QC"]))
    cap_rows = [c for c in audit.await_args_list
                if c.args and c.args[0] in ("theme_sector_cap_absorbed", "theme_sector_cap_not_absorbed",
                                            KEPT_EVENT)]
    assert cap_rows, "the fixture must reach the cap (the second Tanker-named theme is the third)"
    for c in cap_rows:
        d = _detail(c)
        target = d["target"]
        assert target == REFINERS, d
