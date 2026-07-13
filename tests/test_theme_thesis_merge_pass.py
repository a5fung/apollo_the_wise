"""ADR 0025 Arm B (#274) — the mechanical merge executor (C3), behind THEME_MERGE_ARM.

Covers the C3 card's test list: toggle-OFF no-op · distinct-writes-cooldown ·
merge-executes (union into higher-scoring winner + synthetic Retired row with
parent_theme=successor + post-merge validation) · nightly merge cap ·
parent-child-routes-to-subtheme · gutted-union dissolves (Arm A composition) ·
adjudication-error fail-open · F1 adjudicator-proposed name (+ collision guard).
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


def _wire(monkeypatch, verdicts_by_other: dict, validate=None):
    """Standard harness: fake adjudicator (keyed by the non-anchor theme name),
    captured audits/cooldowns, identity post-merge validation by default."""
    events: list[tuple[str, str]] = []
    distinct_cooldowns: list[tuple[str, str]] = []

    async def fake_audit(event_type, summary, detail=None):
        events.append((event_type, summary))

    async def fake_get_pairs():
        return set()

    async def fake_add_distinct(a, b, reason="", days=30):
        distinct_cooldowns.append(tuple(sorted((a, b))))

    async def fake_adjudicate(anchor, other, **kw):
        return verdicts_by_other[other["name"]]

    async def fake_validate(name, tickers, changelog, protected=None, dissolve_flagged_pair=False):
        return list(tickers) if validate is None else await validate(name, tickers)

    monkeypatch.setenv("THEME_MERGE_ARM", "1")
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
