"""The sector cap may not move a member into a theme it never passed the membership test for.

The 2026-09-24 defect (verified on prod): 'Regulated Natural Gas Distribution Utilities' (SR, ATO)
was the THIRD oil_gas-keyword theme of the night ("gas" matches the group), so Pass 2 of
`_merge_overlapping_themes` blind-unioned its roster into the top theme of the keyword group,
'Crude & Product Tanker Shipping' ("crude"). No ticker overlap was required, no co-movement verdict
was read (SR 0.105, ATO 0.2665 against the tanker basket — the admission bar is 0.35), no validator
ran, and no audit row was written, so the retired source pointed at parent '(unknown)'.

The fix: a member the cap moves passes the SAME membership test any other admission passes — the
tape (`_comove_verdict`) where it can judge the pair, `_validate_theme_membership` otherwise — and
is otherwise not moved. The cap itself (keep the top N per keyword group, absorb the rest into the
top theme) is unchanged; only WHAT is absorbed is now judged.

Run: pytest tests/test_theme_sector_cap_rehome.py -v
"""
from __future__ import annotations

import json
from datetime import date

import numpy as np
import pytest

from agents.market_intelligence import market_adjusted_correlation as mac
from agents.market_intelligence import theme_engine as te

TANKER = "Crude & Product Tanker Shipping"
REFINERS = "Oil Refining & Marketing"
GAS_UTILITIES = "Regulated Natural Gas Distribution Utilities"
TANKER_MEMBERS = ["TNK", "FRO", "INSW", "TRMD", "NAT", "STNG"]
N_SESSIONS = mac.BELONGING_LOOKBACK_SESSIONS


def _synthetic_ctx() -> te.ComoveContext:
    """60 sessions of excess returns: the six tanker names ride one common factor (pairwise
    ~0.9), SR and ATO are independent noise (~0 against the basket), and XCO — the control —
    rides the tanker factor, so the tape admits it. Deterministic seed."""
    rng = np.random.default_rng(20260925)
    factor = rng.normal(size=N_SESSIONS)
    excess: dict[str, np.ndarray] = {}
    for tk in TANKER_MEMBERS:
        excess[tk] = factor + 0.3 * rng.normal(size=N_SESSIONS)
    excess["XCO"] = factor + 0.3 * rng.normal(size=N_SESSIONS)
    excess["SR"] = rng.normal(size=N_SESSIONS)
    excess["ATO"] = rng.normal(size=N_SESSIONS)
    return te.ComoveContext(before_date=date(2026, 9, 24), excess=excess,
                            n_sessions=N_SESSIONS, n_rows=0)


def _themes() -> list[dict]:
    """The 09-24 shape: three oil_gas-keyword themes against a cap of 2. The rosters are
    disjoint (Pass 1 never fires) and each has > 1 unique ticker (Pass 1.5 never fires), so the
    ONLY path that can move SR/ATO/XCO is the Pass-2 absorb-into-top branch."""
    assert te._sector_group(TANKER) == ("oil_gas", 2)
    assert te._sector_group(REFINERS) == ("oil_gas", 2)
    assert te._sector_group(GAS_UTILITIES) == ("oil_gas", 2)
    return [
        {"name": TANKER, "tickers": list(TANKER_MEMBERS), "score": 90.0, "stage": "Mainstream"},
        {"name": REFINERS, "tickers": ["VLO", "MPC", "PSX"], "score": 80.0, "stage": "Nascent"},
        {"name": GAS_UTILITIES, "tickers": ["SR", "ATO", "XCO"], "score": 70.0, "stage": "Nascent"},
    ]


@pytest.fixture
def audit(monkeypatch):
    from unittest.mock import AsyncMock
    mock = AsyncMock()
    monkeypatch.setattr(te, "log_audit_event", mock)
    return mock


@pytest.fixture
def validator_admits_all(monkeypatch):
    """The LLM validator, patched to keep every member — isolates the TAPE in the tests below."""
    calls: list[tuple[str, list[str]]] = []

    async def fake(theme_name, tickers, changelog, protected=None, **kw):
        calls.append((theme_name, list(tickers)))
        return list(tickers)

    monkeypatch.setattr(te, "_validate_theme_membership", fake)
    return calls


def test_fixture_exercises_the_tape():
    """Guard against a vacuous fixture: the pair must be JUDGEABLE (not thin_basket / no_history)
    and read the way the prod pair read — SR/ATO below the bar, the control above it."""
    ctx = _synthetic_ctx()
    for tk in ("SR", "ATO"):
        cv = te._comove_verdict(tk, TANKER_MEMBERS, ctx)
        assert cv is not None and cv.admit is False, cv
        assert cv.reason == "below_bar" and cv.corr < te.ASSIGN_COMOVE_BAR, cv
        assert cv.overlap >= mac.BELONGING_MIN_OVERLAP_SESSIONS, cv
    cv = te._comove_verdict("XCO", TANKER_MEMBERS, ctx)
    assert cv is not None and cv.admit is True and cv.corr >= te.ASSIGN_COMOVE_BAR, cv


@pytest.mark.asyncio
async def test_sector_cap_absorb_passes_the_tape(audit, validator_admits_all):
    """The SR/ATO shape. With a context, the tape judges every member the cap would move: the two
    gas utilities read below the bar against the tanker basket and are NOT moved; the control that
    co-moves is. The cap itself still holds (two oil_gas themes survive, the third is gone)."""
    out = await te._merge_overlapping_themes(
        _themes(), {}, protected_names=set(), comove_ctx=_synthetic_ctx(),
    )
    surviving = {t["name"] for t in out}
    assert surviving == {TANKER, REFINERS}, surviving
    tanker = next(t for t in out if t["name"] == TANKER)
    assert "SR" not in tanker["tickers"], tanker["tickers"]
    assert "ATO" not in tanker["tickers"], tanker["tickers"]
    assert "XCO" in tanker["tickers"], tanker["tickers"]
    assert set(TANKER_MEMBERS) <= set(tanker["tickers"])
    # every member the tape could judge was judged by the tape — the validator was not consulted
    assert validator_admits_all == []


@pytest.mark.asyncio
async def test_sector_cap_absorb_falls_to_the_validator_without_a_context(audit, monkeypatch):
    """No context (toggle OFF / closes read failed): the membership validator decides, exactly as
    it does for a net-new assignment. It is asked about the TARGET theme with the union roster;
    what it rejects is not moved, what it keeps is."""
    calls: list[tuple[str, list[str]]] = []

    async def fake(theme_name, tickers, changelog, protected=None, **kw):
        calls.append((theme_name, list(tickers)))
        return [tk for tk in tickers if tk not in ("SR", "ATO")]

    monkeypatch.setattr(te, "_validate_theme_membership", fake)
    out = await te._merge_overlapping_themes(_themes(), {}, protected_names=set(), comove_ctx=None)
    tanker = next(t for t in out if t["name"] == TANKER)
    assert "SR" not in tanker["tickers"] and "ATO" not in tanker["tickers"], tanker["tickers"]
    assert "XCO" in tanker["tickers"]
    assert len(calls) == 1
    name, roster = calls[0]
    assert name == TANKER
    assert set(roster) == set(TANKER_MEMBERS) | {"SR", "ATO", "XCO"}


@pytest.mark.asyncio
async def test_sector_cap_unjudgeable_pair_goes_to_the_validator_not_a_silent_admit(audit, monkeypatch):
    """A pair the tape cannot judge (no price history) is never admitted on the None — it goes to
    the validator, the same fail direction every other membership site has."""
    ctx = _synthetic_ctx()
    del ctx.excess["ATO"]  # ATO: no_history → unjudgeable
    seen: list[list[str]] = []

    async def fake(theme_name, tickers, changelog, protected=None, **kw):
        seen.append(list(tickers))
        return [tk for tk in tickers if tk != "ATO"]

    monkeypatch.setattr(te, "_validate_theme_membership", fake)
    out = await te._merge_overlapping_themes(_themes(), {}, protected_names=set(), comove_ctx=ctx)
    tanker = next(t for t in out if t["name"] == TANKER)
    assert "ATO" not in tanker["tickers"]
    assert "SR" not in tanker["tickers"]      # tape: below bar
    assert "XCO" in tanker["tickers"]         # tape: admitted
    assert seen == [TANKER_MEMBERS + ["ATO"]]  # only the unjudged name reached the validator


@pytest.mark.asyncio
async def test_sector_cap_absorb_honours_cooldown_and_exclusion(audit, validator_admits_all):
    """The two guards the assignment funnel applies before any admit apply here too: a name
    validation-removed from the target within 14d, and an operator ban, are not moved even when
    the tape says yes."""
    out = await te._merge_overlapping_themes(
        _themes(), {}, protected_names=set(), comove_ctx=_synthetic_ctx(),
        cooldown_set={("XCO", TANKER)},
    )
    tanker = next(t for t in out if t["name"] == TANKER)
    assert "XCO" not in tanker["tickers"]
    out = await te._merge_overlapping_themes(
        _themes(), {}, protected_names=set(), comove_ctx=_synthetic_ctx(),
        theme_exclusions={TANKER: {"XCO"}},
    )
    tanker = next(t for t in out if t["name"] == TANKER)
    assert "XCO" not in tanker["tickers"]


@pytest.mark.asyncio
async def test_sector_cap_absorb_is_audited_with_a_successor_pointer(audit, validator_admits_all):
    """The absorb writes ONE audit row whose summary the engine-drop retire path parses for the
    successor pointer (the 09-24 row read parent='(unknown)' because the branch wrote nothing),
    with the per-member verdicts in the detail."""
    await te._merge_overlapping_themes(_themes(), {}, protected_names=set(), comove_ctx=_synthetic_ctx())
    rows = [c for c in audit.await_args_list if c.args and c.args[0] == "theme_sector_cap_absorbed"]
    assert len(rows) == 1, [c.args[0] for c in audit.await_args_list]
    summary = rows[0].kwargs.get("summary") or rows[0].args[1]
    detail = json.loads(rows[0].kwargs.get("detail") or rows[0].args[2])
    assert f"'{GAS_UTILITIES}' -> '{TANKER}'" in summary
    assert detail["members"]["SR"]["verdict"] == "reject" and detail["members"]["SR"]["path"] == "tape"
    assert detail["members"]["ATO"]["verdict"] == "reject"
    assert detail["members"]["XCO"]["verdict"] == "admit"
    assert detail["members"]["SR"]["corr"] < te.ASSIGN_COMOVE_BAR
    # the retire path reads the pointer off this row
    successors, _ = te._successor_pointers_from_audit_rows([
        {"event_type": "theme_sector_cap_absorbed", "summary": summary, "detail": ""},
    ])
    assert successors == {GAS_UTILITIES: TANKER}


@pytest.mark.asyncio
async def test_sector_cap_source_with_no_admitted_member_has_no_successor(audit, monkeypatch):
    """Every member rejected → the source was not absorbed BY anything: a distinct row, no
    successor pointer, and the retire note can say why it was dropped."""
    ctx = _synthetic_ctx()
    themes = _themes()
    themes[2]["tickers"] = ["SR", "ATO"]

    async def fake(theme_name, tickers, changelog, protected=None, **kw):
        raise AssertionError("both pairs are judgeable — the validator must not be called")

    monkeypatch.setattr(te, "_validate_theme_membership", fake)
    out = await te._merge_overlapping_themes(themes, {}, protected_names=set(), comove_ctx=ctx)
    tanker = next(t for t in out if t["name"] == TANKER)
    assert set(tanker["tickers"]) == set(TANKER_MEMBERS)
    absorbed = [c for c in audit.await_args_list if c.args and c.args[0] == "theme_sector_cap_absorbed"]
    rejected = [c for c in audit.await_args_list if c.args and c.args[0] == "theme_sector_cap_not_absorbed"]
    assert absorbed == [] and len(rejected) == 1
    summary = rejected[0].kwargs.get("summary") or rejected[0].args[1]
    successors, cap_rejected = te._successor_pointers_from_audit_rows([
        {"event_type": "theme_sector_cap_not_absorbed", "summary": summary, "detail": ""},
    ])
    assert successors == {}
    assert cap_rejected == {GAS_UTILITIES: TANKER}


@pytest.mark.asyncio
async def test_sector_cap_empty_source_is_not_a_rejection(audit, monkeypatch):
    """A source stripped empty upstream (the 09-24 'Small Launch Vehicle…' line: "0 tickers
    absorbed") has nothing to judge: no validator call, no "0 of 0 passed" row, and the retire
    note must not claim its members failed the test. A source whose members ALL already sit in
    the target gets the successor pointer — the target is where its members live."""
    async def fake(theme_name, tickers, changelog, protected=None, **kw):
        raise AssertionError("nothing to judge — the validator must not be called")

    monkeypatch.setattr(te, "_validate_theme_membership", fake)
    themes = _themes()
    themes[2]["tickers"] = []
    out = await te._merge_overlapping_themes(themes, {}, protected_names=set(), comove_ctx=_synthetic_ctx())
    tanker = next(t for t in out if t["name"] == TANKER)
    assert set(tanker["tickers"]) == set(TANKER_MEMBERS)
    rows = [c for c in audit.await_args_list if c.args and c.args[0] == "theme_sector_cap_not_absorbed"]
    assert len(rows) == 1
    summary = rows[0].kwargs.get("summary") or rows[0].args[1]
    assert "empty at the cap" in summary and "0 of 0" not in summary
    successors, cap_rejected = te._successor_pointers_from_audit_rows([
        {"event_type": "theme_sector_cap_not_absorbed", "summary": summary, "detail": ""},
    ])
    assert successors == {} and cap_rejected == {}

    # All members already in the target. Through the merge function Pass 1 / 1.5 fold such a
    # source first (full containment), so the branch is exercised on the helper directly.
    audit.reset_mock()
    target = {"name": TANKER, "tickers": list(TANKER_MEMBERS)}
    source = {"name": GAS_UTILITIES, "tickers": ["TNK", "FRO"]}
    admitted = await te._admit_rehomed_members(
        target, source, "oil_gas", comove_ctx=_synthetic_ctx(), changelog=None, protected=None,
        cooldown_set=None, theme_exclusions=None,
    )
    assert admitted == [] and target["tickers"] == list(TANKER_MEMBERS)
    rows = [c for c in audit.await_args_list if c.args and c.args[0] == "theme_sector_cap_absorbed"]
    assert len(rows) == 1
    summary = rows[0].kwargs.get("summary") or rows[0].args[1]
    assert "already in the target" in summary
    successors, _ = te._successor_pointers_from_audit_rows([
        {"event_type": "theme_sector_cap_absorbed", "summary": summary, "detail": ""},
    ])
    assert successors == {GAS_UTILITIES: TANKER}
