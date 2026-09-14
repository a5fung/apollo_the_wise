"""The theme membership test asks the TAPE, not the vendor's sector label (2026-09-13,
OPERATOR-SIGNED) — behaviour pins, all through the REAL functions (no source-text assertions).

What is pinned:
  1. `_comove_verdict` — a cross-sector co-mover is admitted, same-sector noise is rejected, and
     every "cannot judge" case (no history, a 2-member basket, no context) returns None/admit=None,
     never an admit;
  2. `_load_comove_context` — asks for closes STRICTLY before the run date and the session index
     ends there even when the tape carries later rows (no lookahead); any failure -> None + an
     audit row (fail SAFE to the sector test);
  3. the ASSIGNMENT gate end to end (`_assign_uncovered_to_themes`, the test_theme_batching
     harness): with a context, a cross-sector co-mover is admitted over the sector label (and the
     audit row says so), same-sector noise is rejected with the counterfactual on the row, a
     candidate with NO history falls to the sector test in BOTH directions (cross-sector rejected,
     same-sector admitted), and with `comove_ctx=None` the run emits exactly today's events;
  4. the ordered second pass — a co-mover proposed BEFORE the same-sector name that brings a
     2-member theme to three is judged against the full basket (IREN/BTDR 2026-09-08);
  5. the carryforward strip and the birth strip keep a singleton-sector member that co-moves and
     drop one that does not, and drop an unjudgeable one exactly as before;
  6. the toggle — fresh deploy is ON even with the DB unreachable; a row 'off' reverts — through
     the real db.get_runtime_toggle;
  7. the bar is registered in the provenance registry at its live value.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from unittest.mock import AsyncMock

import numpy as np
import pytest

from agents.market_intelligence import ep_theme_belonging as etb
from agents.market_intelligence import theme_engine as te
from tests.test_theme_batching import _assign_tool_resp, _fake_client, _quiet_infra

BEFORE = date(2026, 9, 8)


def _tape(seed: int = 0, n: int = 110, start: date = date(2026, 5, 10)):
    """SPY, three Technology members on one factor, one Financial-Services co-mover on the same
    factor (IREN's shape), one same-sector noise stock, one stock with no history at all."""
    rng = np.random.default_rng(seed)
    days = [start + timedelta(days=i) for i in range(n)]
    mkt = rng.normal(0, 0.01, n)
    fac = rng.normal(0, 0.02, n)

    def closes(sig):
        return dict(zip(days, (100.0 * np.exp(np.cumsum(sig))).tolist()))

    return {
        "SPY": closes(mkt),
        "CIFR": closes(mkt + fac + rng.normal(0, 0.01, n)),
        "CORZ": closes(mkt + fac + rng.normal(0, 0.01, n)),
        "BTDR": closes(mkt + fac + rng.normal(0, 0.01, n)),
        "IREN": closes(mkt + fac + rng.normal(0, 0.01, n)),
        "NOIS": closes(mkt + rng.normal(0, 0.02, n)),
    }


def _ctx(tape, before=BEFORE) -> te.ComoveContext:
    cs = etb.session_index(tape["SPY"], before, etb.BELONGING_LOOKBACK_SESSIONS)
    mk = etb.log_returns(tape["SPY"], cs)
    ex = etb.excess_returns(tape, cs, mk)
    return te.ComoveContext(before_date=before, excess=ex, n_sessions=len(cs) - 1, n_rows=0)


def _fake_fetch(tape):
    calls: list = []

    async def _fetch(tickers, start, end_exclusive):
        syms = sorted((t or "").upper() for t in tickers if t)
        calls.append((syms, start, end_exclusive))
        out = {}
        for t in syms:
            if t in tape:
                sel = {d: c for d, c in tape[t].items() if start <= d < end_exclusive}
                if sel:
                    out[t] = sel
        return out, sum(len(v) for v in out.values())

    _fetch.calls = calls
    return _fetch


# ── 1. the per-pair verdict ────────────────────────────────────────────────────────────────

def test_verdict_admits_a_cross_sector_comover_and_rejects_noise_and_never_admits_on_missing_data():
    ctx = _ctx(_tape())
    members = ["CIFR", "CORZ", "BTDR"]

    v = te._comove_verdict("IREN", members, ctx)
    assert v.admit is True and v.reason == "comoves" and v.corr >= te.ASSIGN_COMOVE_BAR
    assert v.basket_n == 3 and v.overlap == etb.BELONGING_LOOKBACK_SESSIONS

    n = te._comove_verdict("NOIS", members, ctx)
    assert n.admit is False and n.reason == "below_bar" and n.corr < te.ASSIGN_COMOVE_BAR

    # leave-one-out: a member is judged against the OTHERS — two others is a thin basket, three
    # others (once IREN is in) is a group and the member is admitted against it
    m = te._comove_verdict("CIFR", members, ctx)
    assert m.admit is None and m.reason == "thin_basket" and m.basket_n == 2
    loo = te._comove_verdict("CIFR", members + ["IREN"], ctx)
    assert loo.admit is True and loo.basket_n == 3

    # cannot judge -> admit is None, never True
    assert te._comove_verdict("GHOST", members, ctx).admit is None
    assert te._comove_verdict("GHOST", members, ctx).reason == "no_history"
    thin = te._comove_verdict("IREN", ["CIFR", "CORZ"], ctx)
    assert thin.admit is None and thin.reason == "thin_basket"
    assert te._comove_verdict("IREN", members, None) is None


def test_the_bar_is_the_named_constant_and_is_registered_at_its_live_value():
    from scripts.gate_provenance_registry import GATE_REGISTRY
    entry = next(e for e in GATE_REGISTRY if e["id"] == "theme_engine.ASSIGN_COMOVE_BAR")
    assert entry["value"] == te.ASSIGN_COMOVE_BAR == 0.35
    # the toggle the docs name is the toggle the drift check can see (literal call, default ON)
    from scripts.live_rules import discover_runtime_toggles
    fact = discover_runtime_toggles()[te.ASSIGN_COMOVE_TOGGLE[0]]
    assert fact.env_var == te.ASSIGN_COMOVE_TOGGLE[1] and fact.default is True
    assert fact.where.startswith("agents/market_intelligence/theme_engine.py:")
    # a verdict exactly at the bar admits (>=), one hair under rejects — the bar binds, not a copy
    ctx = _ctx(_tape())
    v = te._comove_verdict("IREN", ["CIFR", "CORZ", "BTDR"], ctx)
    assert (v.corr >= te.ASSIGN_COMOVE_BAR) == v.admit


# ── 2. the context: no lookahead, fail SAFE ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_context_is_built_strictly_before_the_run_date_and_asks_the_fetch_for_that(monkeypatch):
    tape = _tape(n=140)  # carries rows AFTER the run date
    fetch = _fake_fetch(tape)
    monkeypatch.setattr(etb, "fetch_closes", fetch)
    audits: list = []

    async def _audit(*a, **kw):
        audits.append(a)

    monkeypatch.setattr(te, "log_audit_event", _audit)

    ctx = await te._load_comove_context({"IREN", "CIFR", "CORZ", "BTDR"}, BEFORE)
    assert ctx is not None and ctx.n_sessions == etb.BELONGING_LOOKBACK_SESSIONS
    (syms, start, end_exclusive), = fetch.calls
    assert end_exclusive == BEFORE and "SPY" in syms and "IREN" in syms
    # the window ends strictly before the run date even though later closes exist on the tape
    assert max(d for d in tape["SPY"]) > BEFORE
    cs = etb.session_index(tape["SPY"], BEFORE, etb.BELONGING_LOOKBACK_SESSIONS)
    assert cs[-1] < BEFORE and len(cs) - 1 == ctx.n_sessions
    assert audits == []


@pytest.mark.asyncio
async def test_context_failure_is_none_and_audited(monkeypatch):
    async def _boom(*a, **kw):
        raise RuntimeError("db down")

    monkeypatch.setattr(etb, "fetch_closes", _boom)
    audits: list = []

    async def _audit(event_type, summary="", detail="", **kw):
        audits.append((event_type, summary, detail))

    monkeypatch.setattr(te, "log_audit_event", _audit)
    assert await te._load_comove_context({"IREN"}, BEFORE) is None
    assert [a[0] for a in audits] == ["theme_comove_context_failed"]
    assert "db down" in audits[0][2]


# ── 3. the assignment gate, end to end ────────────────────────────────────────────────────

def _theme(members, description="bitcoin miners converting to AI hosting"):
    return {"name": "Miners", "stage": "Nascent", "tickers": list(members), "description": description}


def _stock(tk, sector, monkeypatch, desc="a bitcoin miner"):
    from agents.market_intelligence import universe
    monkeypatch.setitem(universe.TICKER_DESC, tk, desc)
    return {"ticker": tk, "rs_composite": 90, "sector": sector}


def _run(stocks, themes, sbt, monkeypatch, proposals, comove_ctx):
    events = _quiet_infra(monkeypatch)

    async def _validate_ok(name, tickers, changelog, protected=None):
        return tickers

    monkeypatch.setattr(te, "_validate_theme_membership", _validate_ok)
    client, _calls = _fake_client(lambda i: _assign_tool_resp(proposals))
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)
    full_sbt = {**sbt, **{s["ticker"]: s for s in stocks}}
    remaining, changelog = asyncio.run(te._assign_uncovered_to_themes(
        stocks, themes, full_sbt, theme_exclusions=None, globally_banned=None,
        cooldown_set=set(), protected=None, comove_ctx=comove_ctx))
    return remaining, changelog, events


def _members_sbt():
    return {tk: {"ticker": tk, "sector": "Technology"} for tk in ["CIFR", "CORZ", "BTDR"]}


def test_assignment_admits_the_cross_sector_comover_over_the_label_and_says_so(monkeypatch):
    ctx = _ctx(_tape())
    themes = [_theme(["CIFR", "CORZ", "BTDR"])]
    stocks = [_stock("IREN", "Financial Services", monkeypatch)]
    _, changelog, events = _run(stocks, themes, _members_sbt(), monkeypatch,
                                [{"ticker": "IREN", "theme": "Miners", "rationale": "converting miner"}], ctx)
    assert "IREN" in themes[0]["tickers"]
    assert [c["ticker"] for c in changelog if c["type"] == "ticker_assigned"] == ["IREN"]
    kinds = [e[0] for e in events]
    assert "assignment_comove_admitted_over_sector" in kinds
    assert "assignment_skipped_sector_outlier" not in kinds
    detail = json.loads(next(e[2] for e in events if e[0] == "assignment_comove_admitted_over_sector"))
    assert detail["sector_verdict"] == "reject" and detail["corr"] >= te.ASSIGN_COMOVE_BAR
    assert detail["bar"] == te.ASSIGN_COMOVE_BAR and detail["basket_n"] == 3
    summary = json.loads(next(e[2] for e in events if e[0] == "assignment_comove_summary"))
    assert summary["admitted"] == 1 and summary["admitted_over_sector"] == 1 and summary["rejected"] == 0


def test_assignment_rejects_same_sector_noise_and_records_that_the_label_would_have_admitted(monkeypatch):
    ctx = _ctx(_tape())
    themes = [_theme(["CIFR", "CORZ", "BTDR"])]
    stocks = [_stock("NOIS", "Technology", monkeypatch)]
    _, changelog, events = _run(stocks, themes, _members_sbt(), monkeypatch,
                                [{"ticker": "NOIS", "theme": "Miners", "rationale": "same sector"}], ctx)
    assert "NOIS" not in themes[0]["tickers"] and changelog == []
    detail = json.loads(next(e[2] for e in events if e[0] == "assignment_skipped_comove_below_bar"))
    assert detail["sector_verdict"] == "admit" and detail["corr"] < te.ASSIGN_COMOVE_BAR
    assert "assignment_skipped_sector_outlier" not in [e[0] for e in events]


def test_a_candidate_with_no_history_falls_to_the_sector_test_in_both_directions(monkeypatch):
    ctx = _ctx(_tape())
    themes = [_theme(["CIFR", "CORZ", "BTDR"])]
    # GHOST has no closes on the tape: cross-sector -> the sector test REJECTS (never a silent admit)
    stocks = [_stock("GHOST", "Financial Services", monkeypatch)]
    _, changelog, events = _run(stocks, themes, _members_sbt(), monkeypatch,
                                [{"ticker": "GHOST", "theme": "Miners", "rationale": "x"}], ctx)
    assert "GHOST" not in themes[0]["tickers"] and changelog == []
    assert "assignment_skipped_sector_outlier" in [e[0] for e in events]
    assert not any(e[0].startswith("assignment_comove") and e[0] != "assignment_comove_summary" for e in events)
    summary = json.loads(next(e[2] for e in events if e[0] == "assignment_comove_summary"))
    assert summary["unjudgeable"] == 1 and summary["judged"] == 0
    # same-sector no-history -> the sector test ADMITS, exactly as today
    themes = [_theme(["CIFR", "CORZ", "BTDR"])]
    stocks = [_stock("GHOST", "Technology", monkeypatch)]
    _, changelog, events = _run(stocks, themes, _members_sbt(), monkeypatch,
                                [{"ticker": "GHOST", "theme": "Miners", "rationale": "x"}], ctx)
    assert "GHOST" in themes[0]["tickers"]


def test_no_context_is_todays_gate_event_for_event(monkeypatch):
    themes = [_theme(["CIFR", "CORZ", "BTDR"])]
    stocks = [_stock("IREN", "Financial Services", monkeypatch), _stock("NOIS", "Technology", monkeypatch)]
    _, changelog, events = _run(stocks, themes, _members_sbt(), monkeypatch,
                                [{"ticker": "IREN", "theme": "Miners", "rationale": "x"},
                                 {"ticker": "NOIS", "theme": "Miners", "rationale": "y"}], None)
    # the label decides: the co-mover is out, the noise is in — and no co-movement event exists
    assert "IREN" not in themes[0]["tickers"] and "NOIS" in themes[0]["tickers"]
    kinds = [e[0] for e in events]
    assert "assignment_skipped_sector_outlier" in kinds
    assert not any(k.startswith("assignment_comove") or k == "assignment_skipped_comove_below_bar" for k in kinds)


def test_second_pass_judges_a_comover_proposed_before_the_name_that_makes_the_theme_three(monkeypatch):
    """IREN/BTDR 2026-09-08: the theme had CIFR+CORZ; the batch listed IREN BEFORE BTDR. On a
    single pass IREN meets a 2-name basket, cannot be judged, and the label rejects it."""
    ctx = _ctx(_tape())
    themes = [_theme(["CIFR", "CORZ"])]
    sbt = {tk: {"ticker": tk, "sector": "Technology"} for tk in ["CIFR", "CORZ"]}
    stocks = [_stock("IREN", "Financial Services", monkeypatch), _stock("BTDR", "Technology", monkeypatch)]
    _, changelog, events = _run(stocks, themes, sbt, monkeypatch,
                                [{"ticker": "IREN", "theme": "Miners", "rationale": "x"},
                                 {"ticker": "BTDR", "theme": "Miners", "rationale": "y"}], ctx)
    assert themes[0]["tickers"] == ["CIFR", "CORZ", "BTDR", "IREN"], themes[0]["tickers"]
    assert {c["ticker"] for c in changelog if c["type"] == "ticker_assigned"} == {"IREN", "BTDR"}
    assert "assignment_comove_admitted_over_sector" in [e[0] for e in events]
    assert "assignment_skipped_sector_outlier" not in [e[0] for e in events]


def test_a_pair_still_thin_on_the_second_pass_takes_the_sector_test_and_is_rejected(monkeypatch):
    """IREN minus BTDR: a 2-member theme, one cross-sector co-mover, nobody else lands. Both passes
    meet a 2-name basket; the label decides and REJECTS. Never a silent admit."""
    ctx = _ctx(_tape())
    themes = [_theme(["CIFR", "CORZ"])]
    sbt = {tk: {"ticker": tk, "sector": "Technology"} for tk in ["CIFR", "CORZ"]}
    stocks = [_stock("IREN", "Financial Services", monkeypatch)]
    _, changelog, events = _run(stocks, themes, sbt, monkeypatch,
                                [{"ticker": "IREN", "theme": "Miners", "rationale": "x"}], ctx)
    assert themes[0]["tickers"] == ["CIFR", "CORZ"] and changelog == []
    kinds = [e[0] for e in events]
    assert "assignment_skipped_sector_outlier" in kinds
    assert "assignment_comove_admitted_over_sector" not in kinds
    assert "assignment_skipped_comove_below_bar" not in kinds
    summary = json.loads(next(e[2] for e in events if e[0] == "assignment_comove_summary"))
    assert summary["unjudgeable"] == 1 and summary["judged"] == 0


# ── 5. the two strips ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_carryforward_strip_keeps_the_comoving_singleton_and_drops_the_rest(monkeypatch):
    audits: list = []

    async def _audit(event_type, summary="", detail="", **kw):
        audits.append((event_type, summary, detail))

    monkeypatch.setattr(te, "log_audit_event", _audit)
    ctx = _ctx(_tape())
    sbt = {**_members_sbt(), "IREN": {"sector": "Financial Services"},
           "NOIS": {"sector": "Energy"}, "GHOST": {"sector": "Utilities"}}
    themes = [{"name": "Miners", "tickers": ["CIFR", "CORZ", "BTDR", "IREN", "NOIS", "GHOST"], "stage": "Nascent"}]
    stripped = await te._apply_carryforward_deterministic_filter(themes, set(), set(), sbt, comove_ctx=ctx)
    assert themes[0]["tickers"] == ["CIFR", "CORZ", "BTDR", "IREN"]   # IREN kept by the tape
    assert stripped == 2                                              # NOIS below bar, GHOST unjudgeable
    detail = audits[0][2]
    assert "comove_below_bar=['NOIS']" in detail and "sector_outlier=['GHOST']" in detail
    assert "comove_kept=['IREN']" in detail
    # without a context the same theme loses all three singletons — today's filter
    themes = [{"name": "Miners", "tickers": ["CIFR", "CORZ", "BTDR", "IREN", "NOIS", "GHOST"], "stage": "Nascent"}]
    assert await te._apply_carryforward_deterministic_filter(themes, set(), set(), sbt) == 3
    assert themes[0]["tickers"] == ["CIFR", "CORZ", "BTDR"]


def test_birth_strip_keeps_the_comoving_singleton_and_is_unchanged_without_a_context():
    ctx = _ctx(_tape())
    sbt = {**_members_sbt(), "IREN": {"sector": "Financial Services"}, "NOIS": {"sector": "Energy"}}
    theme = {"name": "Miners", "tickers": ["CIFR", "CORZ", "BTDR", "IREN", "NOIS"], "renamed_from": "x"}
    out = te._strip_sector_outliers(theme, sbt, comove_ctx=ctx)
    assert out["tickers"] == ["CIFR", "CORZ", "BTDR", "IREN"] and out["renamed_from"] == "x"
    assert te._strip_sector_outliers(theme, sbt)["tickers"] == ["CIFR", "CORZ", "BTDR"]


# ── 6. the toggle, through the real reader ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fresh_deploy_is_on_even_with_the_db_unreachable_and_a_row_off_reverts(monkeypatch):
    from agents.market_intelligence import db
    monkeypatch.delenv(te.ASSIGN_COMOVE_TOGGLE[1], raising=False)
    db._runtime_toggle_cache.pop(te.ASSIGN_COMOVE_TOGGLE[0], None)
    monkeypatch.setattr(db, "get_safeguard_state", AsyncMock(side_effect=RuntimeError("no db")))
    assert await te._read_assign_comove_toggle() is True
    db._runtime_toggle_cache.pop(te.ASSIGN_COMOVE_TOGGLE[0], None)
    monkeypatch.setattr(db, "get_safeguard_state", AsyncMock(return_value={"state": "off"}))
    assert await te._read_assign_comove_toggle() is False
    db._runtime_toggle_cache.pop(te.ASSIGN_COMOVE_TOGGLE[0], None)
