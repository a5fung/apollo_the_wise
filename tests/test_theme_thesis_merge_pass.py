"""ADR 0025 Arm B (#274) — the mechanical merge executor (C3), behind THEME_MERGE_ARM.

Covers the C3 card's test list: toggle-OFF no-op · distinct-writes-cooldown ·
merge-executes (union into higher-scoring winner + synthetic Retired row with
parent_theme=successor + post-merge validation) · nightly merge cap ·
parent-child-routes-to-subtheme · gutted-union dissolves (Arm A composition) ·
adjudication-error fail-open · F1 adjudicator-proposed name (+ collision guard).

#655 (d), 2026-10-17: the post-merge validation judges the union against the MERGED name
(decided first), not the winner's old one - see the `test_655d_*` block at the bottom.
His 2026-10-17 "Yes" (stored merged description + the Arm B #601 lineage row) is covered in
tests/test_655d_merged_description_and_lineage.py, which reuses this module's helpers.
"""
from __future__ import annotations

from datetime import date

import pytest

from agents.market_intelligence import theme_engine

TODAY = date(2026, 7, 14)


def _t(name, tickers, score, stage="Nascent", parent=None):
    return {"name": name, "tickers": list(tickers), "score": score, "stage": stage,
            "parent_theme": parent, "description": f"{name} description",
            "theme_date": TODAY}


def _quantum_cohort():
    """One stem family (quantum) → deterministic Stage-A pairs vs the anchor."""
    return [
        _t("Quantum Hardware Leaders", ["QBTS", "IONQ", "RGTI", "QUBT", "ARQQ"], 80),
        _t("Quantum Annealing Systems", ["ANNA", "ANNB"], 50),
        _t("Quantum Networking", ["NETA", "NETB"], 40),
    ]


def _wire(monkeypatch, verdicts_by_other: dict, validate=None, calls=None, details=None):
    """Standard harness: fake adjudicator (keyed by the non-anchor theme name),
    captured audits/cooldowns, identity post-merge validation by default.
    `calls` (optional list) records every post-merge validation call as a dict of what it was
    asked to judge; `details` (optional list) records (event_type, detail) for every audit row."""
    events: list[tuple[str, str]] = []
    distinct_cooldowns: list[tuple[str, str]] = []

    async def fake_audit(event_type, summary, detail=None):
        events.append((event_type, summary))
        if details is not None:
            details.append((event_type, detail))

    async def fake_get_pairs():
        return set()

    async def fake_add_distinct(a, b, reason="", days=30):
        distinct_cooldowns.append(tuple(sorted((a, b))))

    async def fake_adjudicate(anchor, other, **kw):
        return verdicts_by_other[other["name"]]

    async def fake_validate(name, tickers, changelog, protected=None, dissolve_flagged_pair=False,
                            thesis=None):
        if calls is not None:
            calls.append({"name": name, "tickers": list(tickers), "protected": protected,
                          "thesis": thesis})
        return list(tickers) if validate is None else await validate(name, tickers)

    async def fake_protected():  # a renamed merge may fetch the protected set (#655 d): never the real DB
        return set()

    monkeypatch.setenv("THEME_MERGE_ARM", "1")
    monkeypatch.setattr(theme_engine, "get_operator_protected_set", fake_protected)
    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)
    monkeypatch.setattr(theme_engine, "get_merge_distinct_pairs", fake_get_pairs)
    monkeypatch.setattr(theme_engine, "add_merge_distinct_cooldown", fake_add_distinct)
    monkeypatch.setattr(theme_engine, "adjudicate_merge_pair", fake_adjudicate)
    monkeypatch.setattr(theme_engine, "_validate_theme_membership", fake_validate)
    monkeypatch.setattr(theme_engine, "_get_anthropic_client", lambda: object())
    return events, distinct_cooldowns


@pytest.mark.asyncio
async def test_toggle_off_is_a_no_op(monkeypatch):
    monkeypatch.delenv("THEME_MERGE_ARM", raising=False)

    async def boom(*a, **kw):  # any I/O when off = failure
        raise AssertionError("merge pass touched I/O with the toggle off")

    monkeypatch.setattr(theme_engine, "get_merge_distinct_pairs", boom)
    monkeypatch.setattr(theme_engine, "adjudicate_merge_pair", boom)
    themes = _quantum_cohort()
    out = await theme_engine._run_thesis_merge_pass(themes, set(), [], None, TODAY)
    assert out is themes                       # identical object, untouched


@pytest.mark.asyncio
async def test_distinct_writes_pair_cooldown(monkeypatch):
    verdicts = {
        "Quantum Annealing Systems": {"verdict": "DISTINCT", "driver_a": "x", "driver_b": "y", "reason": "different drivers"},
        "Quantum Networking": {"verdict": "DISTINCT", "driver_a": "x", "driver_b": "z", "reason": "different drivers"},
    }
    events, distinct_cooldowns = _wire(monkeypatch, verdicts)
    themes = _quantum_cohort()
    out = await theme_engine._run_thesis_merge_pass(themes, set(), [], None, TODAY)

    assert sorted(t["name"] for t in out) == sorted(t["name"] for t in themes)  # nothing merged
    assert ("Quantum Annealing Systems", "Quantum Hardware Leaders") in distinct_cooldowns
    assert ("Quantum Hardware Leaders", "Quantum Networking") in distinct_cooldowns
    assert sum(1 for e in events if e[0] == "theme_merge_distinct") == 2


@pytest.mark.asyncio
async def test_merge_executes_union_retired_row_and_audit(monkeypatch):
    verdicts = {
        "Quantum Annealing Systems": {"verdict": "MERGE", "driver_a": "q", "driver_b": "q",
                                      "reason": "same trade", "merged_name": ""},
        "Quantum Networking": {"verdict": "DISTINCT", "driver_a": "q", "driver_b": "net", "reason": "r"},
    }
    events, _cd = _wire(monkeypatch, verdicts)
    themes = _quantum_cohort()
    changelog: list[dict] = []
    out = await theme_engine._run_thesis_merge_pass(
        themes, {"Quantum Annealing Systems", "Quantum Hardware Leaders"}, changelog, None, TODAY)

    names = {t["name"]: t for t in out}
    assert "Quantum Annealing Systems" in names            # as a Retired row
    retired = names["Quantum Annealing Systems"]
    assert retired["stage"] == "Retired"
    assert retired["parent_theme"] == "Quantum Hardware Leaders"   # successor pointer
    assert retired["tickers"] == []
    winner = names["Quantum Hardware Leaders"]
    assert set(winner["tickers"]) == {"QBTS", "IONQ", "RGTI", "QUBT", "ARQQ", "ANNA", "ANNB"}
    assert any(e[0] == "theme_thesis_merged" for e in events)
    assert any(c["type"] == "theme_thesis_merged" and c["into"] == "Quantum Hardware Leaders"
               for c in changelog)


@pytest.mark.asyncio
async def test_merge_cap_defers_fourth_merge(monkeypatch):
    themes = [_t("Quantum Anchor Theme", ["Q0", "Q1", "Q2", "Q3", "Q4", "Q5"], 90)] + [
        _t(f"Quantum Sub {i}", [f"S{i}A", f"S{i}B"], 10 + i) for i in range(4)
    ]
    verdicts = {f"Quantum Sub {i}": {"verdict": "MERGE", "driver_a": "q", "driver_b": "q",
                                     "reason": "same"} for i in range(4)}
    events, _cd = _wire(monkeypatch, verdicts)
    out = await theme_engine._run_thesis_merge_pass(themes, set(), [], None, TODAY)

    live_names = {t["name"] for t in out if t["stage"] != "Retired"}
    merged_away = {f"Quantum Sub {i}" for i in range(4)} - live_names
    assert len(merged_away) == theme_engine.MAX_MERGES_PER_NIGHT == 3
    assert sum(1 for e in events if e[0] == "theme_merge_cap_deferred") == 1


@pytest.mark.asyncio
async def test_parent_child_routes_to_subtheme_machinery(monkeypatch):
    verdicts = {
        "Quantum Annealing Systems": {"verdict": "PARENT_CHILD", "child": "B",
                                      "driver_a": "q", "driver_b": "q", "reason": "narrower slice"},
        "Quantum Networking": {"verdict": "DISTINCT", "driver_a": "q", "driver_b": "n", "reason": "r"},
    }
    events, _cd = _wire(monkeypatch, verdicts)
    themes = _quantum_cohort()
    out = await theme_engine._run_thesis_merge_pass(themes, set(), [], None, TODAY)

    child = next(t for t in out if t["name"] == "Quantum Annealing Systems")
    assert child["parent_theme"] == "Quantum Hardware Leaders"    # wired, not dissolved
    assert child["stage"] != "Retired"
    assert any(e[0] == "theme_merge_parent_child" for e in events)


@pytest.mark.asyncio
async def test_gutted_union_dissolves_arms_compose(monkeypatch):
    """Post-merge validation guts the union (<2 survivors) → the merged theme
    auto-dissolves via Arm A instead of persisting a bad union."""
    verdicts = {
        "Quantum Annealing Systems": {"verdict": "MERGE", "driver_a": "q", "driver_b": "q", "reason": "same"},
        "Quantum Networking": {"verdict": "DISTINCT", "driver_a": "q", "driver_b": "n", "reason": "r"},
    }

    async def gutting_validate(name, tickers):
        return tickers[:1]      # validation strips the union to 1 survivor

    events, _cd = _wire(monkeypatch, verdicts, validate=gutting_validate)
    themes = _quantum_cohort()
    out = await theme_engine._run_thesis_merge_pass(
        themes, {t["name"] for t in themes}, [], None, TODAY)

    by_name = {t["name"]: t for t in out}
    assert by_name["Quantum Hardware Leaders"]["stage"] == "Retired"     # both dissolved
    assert by_name["Quantum Annealing Systems"]["stage"] == "Retired"
    assert by_name["Quantum Hardware Leaders"]["parent_theme"] is None   # no successor
    assert any(e[0] == "theme_merge_dissolved_post_validation" for e in events)


@pytest.mark.asyncio
async def test_adjudication_error_fails_open(monkeypatch):
    verdicts = {
        "Quantum Annealing Systems": {"verdict": "ERROR", "reason": "transport"},
        "Quantum Networking": {"verdict": "ERROR", "reason": "transport"},
    }
    events, distinct_cooldowns = _wire(monkeypatch, verdicts)
    themes = _quantum_cohort()
    out = await theme_engine._run_thesis_merge_pass(themes, set(), [], None, TODAY)

    assert sorted(t["name"] for t in out) == sorted(t["name"] for t in themes)  # untouched
    assert distinct_cooldowns == []                       # ERROR ≠ DISTINCT — no cooldown
    assert sum(1 for e in events if e[0] == "theme_merge_adjudication_error") == 2


@pytest.mark.asyncio
async def test_f1_adjudicator_proposed_name_adopted_with_collision_guard(monkeypatch):
    verdicts = {
        "Quantum Annealing Systems": {"verdict": "MERGE", "driver_a": "q", "driver_b": "q",
                                      "reason": "same", "merged_name": "Quantum Computing Hardware"},
        "Quantum Networking": {"verdict": "MERGE", "driver_a": "q", "driver_b": "q",
                               "reason": "same", "merged_name": "Quantum Networking"},  # collides
    }
    events, _cd = _wire(monkeypatch, verdicts)
    themes = _quantum_cohort()
    out = await theme_engine._run_thesis_merge_pass(
        themes, {t["name"] for t in themes}, [], None, TODAY)

    live = {t["name"] for t in out if t["stage"] != "Retired"}
    retired = {t["name"]: t for t in out if t["stage"] == "Retired"}
    # merge 1: adjudicator name adopted; old winner name retired with successor pointer
    assert "Quantum Computing Hardware" in live
    assert retired["Quantum Hardware Leaders"]["parent_theme"] == "Quantum Computing Hardware"
    assert retired["Quantum Annealing Systems"]["parent_theme"] == "Quantum Computing Hardware"
    # merge 2: proposed name collides with an existing theme name → winner keeps its name
    assert retired["Quantum Networking"]["parent_theme"] == "Quantum Computing Hardware"


# ═════════════════════════════════════════════════════════════════════════════════════════
# #655 (d), his ruling 2026-10-17 ("go with rec"): an Arm B merge validates the union against
# the MERGED name, decided first - not the winner's old narrower one. The 10-15 shape: an
# apparel theme (U.S. Apparel & Fashion Recovery, 16 names) merged into a furniture theme; the
# union was judged against 'Commercial, Office & Home Furniture ...', 17 apparel names were
# stripped, and only then was the survivor renamed 'Consumer Discretionary Cyclical Rebound:
# Apparel & Home Furnishings'. q4 D2: strips at 17:07:17.679-.745, merge row .748.
# ═════════════════════════════════════════════════════════════════════════════════════════

OLD_NAME = "Commercial, Office & Home Furniture Retailers and Manufacturers"
ABSORBED_NAME = "U.S. Apparel & Fashion Recovery"
MERGED_NAME = "Consumer Discretionary Cyclical Rebound: Apparel & Home Furnishings"
FURNITURE = ["F1", "F2", "F3", "F4", "F5"]
APPAREL = ["A1", "A2", "A3", "A4"]


def _furniture_and_apparel(extra_apparel=()):
    winner = _t(OLD_NAME, FURNITURE, 80)
    winner["description"] = "Office, home and commercial furniture demand tied to housing and office fit-outs"
    absorbed = _t(ABSORBED_NAME, APPAREL + list(extra_apparel), 50)
    absorbed["description"] = "Mall-based apparel and footwear retailers recovering on consumer spending"
    return [winner, absorbed]


def _pair_them(monkeypatch):
    """Stage A is not under test here (it is the pure theme_merge_arm logic): hand the pass the
    one pair, winner first."""
    monkeypatch.setattr(theme_engine, "propose_merge_pairs",
                        lambda cands, **kw: [(cands[0], cands[1])])


def _name_aware_validator():
    """The judge the model is: a member fits the name it is asked about or it does not.
    The OLD name is furniture only; the MERGED name covers furniture and apparel; X* fits nothing."""
    fits = {
        OLD_NAME: set(FURNITURE),
        MERGED_NAME: set(FURNITURE) | set(APPAREL),
    }

    async def validate(name, tickers):
        return [t for t in tickers if t in fits.get(name, set())]
    return validate


def _merge_verdict(merged_name):
    return {ABSORBED_NAME: {"verdict": "MERGE", "driver_a": "consumer", "driver_b": "consumer",
                            "reason": "same consumer-cyclical rebound trade",
                            "merged_name": merged_name}}


@pytest.mark.asyncio
async def test_655d_a_renamed_merge_keeps_the_apparel_names(monkeypatch):
    """The 10-15 shape. Judged against the merged name every apparel name survives; the old
    name is never what the union is judged against."""
    calls: list[dict] = []
    _wire(monkeypatch, _merge_verdict(MERGED_NAME), validate=_name_aware_validator(), calls=calls)
    _pair_them(monkeypatch)
    themes = _furniture_and_apparel()
    out = await theme_engine._run_thesis_merge_pass(
        themes, {t["name"] for t in themes}, [], None, TODAY)

    assert [c["name"] for c in calls] == [MERGED_NAME]            # asked once, about the merged name
    live = {t["name"]: t for t in out if t["stage"] != "Retired"}
    assert set(live) == {MERGED_NAME}
    assert set(live[MERGED_NAME]["tickers"]) == set(FURNITURE + APPAREL)   # nothing stripped
    # the rename still lands exactly as before: old winner and absorbed get tombstones -> successor
    retired = {t["name"]: t for t in out if t["stage"] == "Retired"}
    assert retired[OLD_NAME]["parent_theme"] == MERGED_NAME
    assert retired[ABSORBED_NAME]["parent_theme"] == MERGED_NAME


@pytest.mark.asyncio
async def test_655d_the_old_name_would_have_stripped_them():
    """Control: the same union judged by the same validator against the OLD name loses all four
    apparel names - this is what 10-15 did, and what the fallback case still does."""
    validated = await _name_aware_validator()(OLD_NAME, FURNITURE + APPAREL)
    assert validated == FURNITURE


@pytest.mark.asyncio
async def test_655d_a_member_that_fits_neither_name_is_still_stripped(monkeypatch):
    calls: list[dict] = []
    _wire(monkeypatch, _merge_verdict(MERGED_NAME), validate=_name_aware_validator(), calls=calls)
    _pair_them(monkeypatch)
    themes = _furniture_and_apparel(extra_apparel=["X1"])         # X1: a bank - fits neither name
    out = await theme_engine._run_thesis_merge_pass(
        themes, {t["name"] for t in themes}, [], None, TODAY)

    assert calls[0]["name"] == MERGED_NAME and "X1" in calls[0]["tickers"]
    merged = next(t for t in out if t["name"] == MERGED_NAME)
    assert "X1" not in merged["tickers"]                          # the strip itself is unchanged
    assert set(merged["tickers"]) == set(FURNITURE + APPAREL)


@pytest.mark.asyncio
async def test_655d_a_renamed_merge_is_judged_on_both_themes_own_descriptions(monkeypatch):
    """The adjudicator returns a name, not a description, so the thesis the validator reads is the
    two themes' own descriptions - the winner's alone was written for the OLD narrow name."""
    calls: list[dict] = []
    _wire(monkeypatch, _merge_verdict(MERGED_NAME), validate=_name_aware_validator(), calls=calls)
    _pair_them(monkeypatch)
    themes = _furniture_and_apparel()
    winner_desc, absorbed_desc = themes[0]["description"], themes[1]["description"]
    await theme_engine._run_thesis_merge_pass(themes, {t["name"] for t in themes}, [], None, TODAY)

    thesis = calls[0]["thesis"]
    assert winner_desc[:148] in thesis and absorbed_desc[:148] in thesis
    assert len(thesis) <= 300                                     # the validator shows thesis[:300]


def test_655d_validation_thesis_drops_a_garbage_half_and_caps_each_half():
    ok = {"description": "x" * 400}
    bad = {"description": "No specific news found for this theme"}
    t = theme_engine._merged_validation_thesis(ok, ok)
    assert len(t) == 148 + len(" | ") + 148 <= 300
    assert theme_engine._merged_validation_thesis(bad, ok) == "x" * 148      # garbage never shields
    assert theme_engine._merged_validation_thesis(bad, bad) is None
    assert theme_engine._merged_validation_thesis({}, {"description": None}) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("merged_name, why", [
    ("", "adjudicator proposed no merged name"),
    (OLD_NAME, "merged name is the winner's own"),
    (ABSORBED_NAME, "merged name collides with an existing theme"),
])
async def test_655d_with_no_usable_merged_name_today_s_behaviour_stands(monkeypatch, merged_name, why):
    """Missing / unchanged / colliding merged name: validated against the winner's old name with the
    winner's own description and the very same protected set, exactly as before - and the audit
    row says which fallback it was."""
    calls: list[dict] = []
    details: list[tuple] = []
    _wire(monkeypatch, _merge_verdict(merged_name), validate=_name_aware_validator(),
          calls=calls, details=details)
    _pair_them(monkeypatch)
    themes = _furniture_and_apparel()
    winner_desc = themes[0]["description"]
    protected = {("F1", OLD_NAME)}
    out = await theme_engine._run_thesis_merge_pass(
        themes, {t["name"] for t in themes}, [], protected, TODAY)

    assert [c["name"] for c in calls] == [OLD_NAME]
    assert calls[0]["thesis"] == winner_desc                      # not the joined thesis
    assert calls[0]["protected"] is protected                     # not copied, not extended
    merged = next(t for t in out if t["name"] == OLD_NAME and t["stage"] != "Retired")
    assert set(merged["tickers"]) == set(FURNITURE)               # the old-name strip, as today
    detail = next(d for e, d in details if e == "theme_thesis_merged")
    assert "validated_against=" + repr(OLD_NAME) in detail and why in detail


@pytest.mark.asyncio
async def test_655d_a_renamed_merge_carries_the_operators_rulings_to_the_merged_name(monkeypatch):
    """A /bypass filed under the winner's old name must still shield under the merged name for THIS
    night's validation call: the Arm B rename's #601 lineage row is only written by `_save_themes`
    when the merged theme's row lands, which is after this call. From the next night the lineage row
    carries the ruling (his 2026-10-17 ruling; tests/test_655d_merged_description_and_lineage.py)."""
    calls: list[dict] = []
    _wire(monkeypatch, _merge_verdict(MERGED_NAME), validate=_name_aware_validator(), calls=calls)
    _pair_them(monkeypatch)
    themes = _furniture_and_apparel()
    protected = {("F2", OLD_NAME), ("ZZ", "Some Other Theme")}
    await theme_engine._run_thesis_merge_pass(
        themes, {t["name"] for t in themes}, [], protected, TODAY)

    sent = calls[0]["protected"]
    assert ("F2", MERGED_NAME) in sent                            # carried to the merged name
    assert ("F2", OLD_NAME) in sent and ("ZZ", "Some Other Theme") in sent   # nothing lost
    assert ("ZZ", MERGED_NAME) not in sent                        # only the winner's own rulings move
    assert protected == {("F2", OLD_NAME), ("ZZ", "Some Other Theme")}       # caller's set untouched


@pytest.mark.asyncio
async def test_655d_an_unreadable_run_prefetch_is_refetched_for_the_merged_name(monkeypatch):
    """`protected=None` (the run-level prefetch failed): fetched once here for a renamed merge;
    if that fails too the validator gets None and falls back to its own lookup, as it always has."""
    calls: list[dict] = []
    _wire(monkeypatch, _merge_verdict(MERGED_NAME), validate=_name_aware_validator(), calls=calls)
    _pair_them(monkeypatch)

    async def fetch():
        return {("F2", OLD_NAME)}
    monkeypatch.setattr(theme_engine, "get_operator_protected_set", fetch)
    themes = _furniture_and_apparel()
    await theme_engine._run_thesis_merge_pass(themes, {t["name"] for t in themes}, [], None, TODAY)
    assert ("F2", MERGED_NAME) in calls[0]["protected"]

    async def broken():
        raise RuntimeError("db down")
    monkeypatch.setattr(theme_engine, "get_operator_protected_set", broken)
    calls.clear()
    themes = _furniture_and_apparel()
    await theme_engine._run_thesis_merge_pass(themes, {t["name"] for t in themes}, [], None, TODAY)
    assert calls[0]["protected"] is None and calls[0]["name"] == MERGED_NAME


@pytest.mark.asyncio
async def test_655d_the_real_validator_shield_matches_a_ruling_filed_under_the_old_name(monkeypatch):
    """End to end through the REAL `_validate_theme_membership` (LLM stubbed to flag A1 and A2):
    A1 has an operator /bypass under the winner's OLD name -> kept; A2 has none -> stripped, and its
    14-day cooldown is filed under the MERGED name (the name the theme carries if the merge
    survives; on a gutted renamed merge that name never exists)."""
    from tests.test_theme_validation_shield import _fake_client

    events: list[tuple[str, str]] = []
    cooldowns: list[tuple[str, str]] = []

    async def fake_audit(event_type, summary, detail=None):
        events.append((event_type, summary))

    async def fake_cooldown(ticker, theme_name, reason=""):
        cooldowns.append((ticker, theme_name))
        return 1

    async def fake_adjudicate(anchor, other, **kw):
        return _merge_verdict(MERGED_NAME)[other["name"]]

    async def fake_get_pairs():
        return set()

    monkeypatch.setenv("THEME_MERGE_ARM", "1")
    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)
    monkeypatch.setattr(theme_engine, "get_merge_distinct_pairs", fake_get_pairs)
    monkeypatch.setattr(theme_engine, "adjudicate_merge_pair", fake_adjudicate)
    monkeypatch.setattr(theme_engine, "add_validation_cooldown", fake_cooldown)
    monkeypatch.setattr(theme_engine, "_get_anthropic_client", lambda: _fake_client(["A1", "A2"]))
    _pair_them(monkeypatch)
    themes = _furniture_and_apparel()
    out = await theme_engine._run_thesis_merge_pass(
        themes, {t["name"] for t in themes}, [], {("A1", OLD_NAME)}, TODAY)

    merged = next(t for t in out if t["name"] == MERGED_NAME)
    assert "A1" in merged["tickers"] and "A2" not in merged["tickers"]
    assert cooldowns == [("A2", MERGED_NAME)]
    assert any(e[0] == "validation_removal_shielded" for e in events)


@pytest.mark.asyncio
async def test_655d_a_gutted_renamed_merge_dissolves_the_two_themes_by_their_own_names(monkeypatch):
    """The merged name is only a local until the gutted-union check has passed: when validation
    leaves <2 members, both ORIGINAL themes are retired and the merged name never appears."""
    async def gut(name, tickers):
        return tickers[:1]

    details: list[tuple] = []
    _wire(monkeypatch, _merge_verdict(MERGED_NAME), validate=gut, details=details)
    _pair_them(monkeypatch)
    themes = _furniture_and_apparel()
    out = await theme_engine._run_thesis_merge_pass(
        themes, {t["name"] for t in themes}, [], None, TODAY)

    by_name = {t["name"]: t for t in out}
    assert MERGED_NAME not in by_name
    assert by_name[OLD_NAME]["stage"] == "Retired" and by_name[ABSORBED_NAME]["stage"] == "Retired"
    assert by_name[OLD_NAME]["parent_theme"] is None
    detail = next(d for e, d in details if e == "theme_merge_dissolved_post_validation")
    assert "validated_against=" + repr(MERGED_NAME) in detail
