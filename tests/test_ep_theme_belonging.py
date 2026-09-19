"""Theme BELONGING for the EP score (2026-09-13/14, operator-directed BUG FIX) — behaviour pins.

The +10 theme bonus keys on whether the alerting stock BELONGS to a live theme at alert time:
listed, OR correlation-SHORTLISTED against THEME_BONUS_STAGES baskets (sessions strictly
before the scan date) AND then CONFIRMED by the nightly assignment pass's own fit judgement
(theme_engine.judge_theme_fit). Correlation alone never pays — the 2026-09-13 replay showed
best-of-many correlation admitting a utility into a fracking theme. Module:
ep_theme_belonging.py; wiring: ep_detector.run_ep_scan; SSoT: docs/setups/magna53_ep.md
change log 2026-09-13 + 2026-09-14.

Pinned here, all through the REAL functions (no source-text assertions):
  1. stage 1 — an unlisted co-mover is SHORTLISTED (pending), not belonging; noise is not
     shortlisted; a listed member is listed; Nascent baskets go to the unjudged Nascent
     shortlist; Fading never builds a basket;
  2. NO LOOKAHEAD — the window ends strictly before the scan date even when the fetch
     returns later rows, and the fetch itself is asked for `< scan date`;
  3. "cannot judge" -> today's behaviour (thin history, 1-2 member baskets, no baskets);
  4. stage 2 — confirmed belongs, rejected does not, and failed / timeout / error / budget /
     toggle-off / post-open-uncached all leave list membership deciding; a verdict is judged
     ONCE a day (cached), a failure is not cached; the shortlist alone reaches the judgement;
  5. the seam: toggle OFF is list membership for every input; ON is the verdict;
  6. the toggle's default on a fresh deploy (ON, even with the DB unreachable) and the
     revert row (state 'off') — through the real db.get_runtime_toggle;
  7. the shadow record's contract, pinned at the REAL producer (score_belonging -> with_fit ->
     build_belonging_shadow_row -> shadow_row_params -> the upsert's placeholders) — the
     #649 lesson: a fixture that invents the recorder's input is a claim about the caller;
  8. the recorder is registered for the deploy-time prepare gate and never raises;
  9. THE WIRING — run_ep_scan end to end (the test_624 harness): an unlisted co-mover on the
     graded shortlist gets theme_bonus 10 when the judgement CONFIRMS it and 0 when it
     REJECTS it (correlation identical both times), 0 with the toggle OFF (and no call), the
     alert row's `in_active_theme` keeps its list-membership meaning either way, the shadow
     row records the verdict, and toggle OFF is byte-identical to a scan with no belonging.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from agents.market_intelligence import ep_theme_belonging as etb
from agents.market_intelligence import market_adjusted_correlation as mac
from agents.market_intelligence.ep_detector import _score_ep
from agents.market_intelligence.ep_rubric import SCORE_WEIGHTS
from tests.conftest import make_mock_pool

_ET = ZoneInfo("America/New_York")
TS = datetime(2026, 9, 3, 9, 31, 12, tzinfo=_ET)
BEFORE = date(2026, 9, 3)

THEMES = [
    {"name": "Grid", "stage": "Accelerating", "tickers": ["A", "B", "C"], "description": "grid equipment"},
    {"name": "Nas", "stage": "Nascent", "tickers": ["A", "B", "C"], "description": "nascent grid"},
    {"name": "Fade", "stage": "Fading", "tickers": ["A", "B", "C"], "description": "old grid"},
]


def _tape(seed: int = 0, n: int = 100, start: date = date(2026, 5, 20), comover: str = "X"):
    """A synthetic tape: SPY, three members sharing one factor, one unlisted stock on the
    same factor (`comover`), one unlisted noise stock N. Calendar days are fine — the session
    index is whatever dates SPY has."""
    rng = np.random.default_rng(seed)
    days = [start + timedelta(days=i) for i in range(n)]
    mkt = rng.normal(0, 0.01, n)
    fac = rng.normal(0, 0.02, n)

    def closes(sig):
        return dict(zip(days, (100.0 * np.exp(np.cumsum(sig))).tolist()))

    return days, {
        "SPY": closes(mkt),
        "A": closes(mkt + fac + rng.normal(0, 0.01, n)),
        "B": closes(mkt + fac + rng.normal(0, 0.01, n)),
        "C": closes(mkt + fac + rng.normal(0, 0.01, n)),
        comover: closes(mkt + fac + rng.normal(0, 0.01, n)),
        "N": closes(mkt + rng.normal(0, 0.02, n)),
    }


def _pure_reads(tape, before=BEFORE):
    cs = etb.session_index(tape["SPY"], before)
    mk = etb.log_returns(tape["SPY"], cs)
    ex = etb.excess_returns(tape, cs, mk)
    baskets = etb.build_baskets(THEMES, ex)
    listed = etb.listed_paying_set(THEMES)
    return cs, ex, baskets, listed


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


def _fake_judge(monkeypatch, verdicts):
    """`etb.judge_theme_fit` scripted per ticker: verdicts[ticker] is a (status, theme,
    rationale) tuple, a callable, or an exception instance to raise. Records every call."""
    calls: list = []

    async def _judge(ticker, **kw):
        calls.append((ticker, kw))
        v = verdicts[ticker]
        if isinstance(v, BaseException):
            raise v
        return await v(ticker, **kw) if callable(v) else v

    monkeypatch.setattr(etb, "judge_theme_fit", _judge)
    return calls


# ── 1. stage 1: the shortlist ──────────────────────────────────────────────────────────────

def test_unlisted_co_mover_is_shortlisted_not_belonging_noise_is_not_listed_is_listed():
    _, tape = _tape()
    cs, ex, baskets, listed = _pure_reads(tape)
    assert len(cs) == etb.BELONGING_LOOKBACK_SESSIONS + 1
    # Fading never builds a basket; Nascent does (shadow read) — one paying, one Nascent
    assert sorted((b.name, b.stage) for b in baskets) == [("Grid", "Accelerating"), ("Nas", "Nascent")]

    x = etb.score_belonging("X", ex["X"], baskets, listed)
    assert x.listed is False and x.belongs_paying is False        # correlation alone never pays
    assert x.fit_status == etb.FIT_PENDING and x.reason == "fit_unjudged"
    assert x.shortlist == (("Grid", "Accelerating", x.best_corr),) and x.shortlisted
    assert x.best_theme == "Grid" and x.best_stage == "Accelerating"
    assert x.best_corr >= etb.BELONGING_SHORTLIST_CORR_BAR and x.n_sessions == etb.BELONGING_LOOKBACK_SESSIONS
    assert x.basket_n == 3
    assert x.nascent_shortlist and x.nascent_shortlist[0][:2] == ("Nas", "Nascent")

    n = etb.score_belonging("N", ex["N"], baskets, listed)
    assert n.belongs_paying is False and n.reason == "below_bar" and n.fit_status == etb.FIT_NOT_SHORTLISTED
    assert n.shortlist == () and n.nascent_shortlist == ()
    assert n.best_corr is not None and n.best_corr < etb.BELONGING_SHORTLIST_CORR_BAR

    a = etb.score_belonging("A", ex["A"], baskets, listed)
    assert a.listed is True and a.belongs_paying is True and a.reason == "listed" and a.fit_status == etb.FIT_LISTED


def test_nascent_basket_never_reaches_the_paying_shortlist():
    """A stock that co-moves ONLY with a Nascent theme: on the Nascent (unjudged) shortlist,
    never pending, never acting — the stage question is the operator's, kept separate."""
    _, tape = _tape()
    cs, ex, _, _ = _pure_reads(tape)
    only_nascent = [{"name": "Nas", "stage": "Nascent", "tickers": ["A", "B", "C"]}]
    baskets = etb.build_baskets(only_nascent, ex)
    x = etb.score_belonging("X", ex["X"], baskets, set())
    assert x.belongs_paying is False and x.shortlist == () and x.fit_status == etb.FIT_NOT_SHORTLISTED
    assert x.best_theme is None and x.nascent_shortlist[0][0] == "Nas"
    assert x.reason == "below_bar"


def test_shortlist_is_capped_and_best_first():
    _, tape = _tape()
    _, ex, _, _ = _pure_reads(tape)
    many = [{"name": f"G{i}", "stage": "Accelerating", "tickers": ["A", "B", "C"]} for i in range(6)]
    baskets = etb.build_baskets(many, ex)
    x = etb.score_belonging("X", ex["X"], baskets, set())
    assert len(x.shortlist) == etb.BELONGING_SHORTLIST_THEMES
    corrs = [c for _, _, c in x.shortlist]
    assert corrs == sorted(corrs, reverse=True) and all(c >= etb.BELONGING_SHORTLIST_CORR_BAR for c in corrs)


def test_correlate_is_leave_one_out_and_a_two_name_basket_is_not_a_group():
    _, tape = _tape()
    _, ex, baskets, _ = _pure_reads(tape)
    grid = next(b for b in baskets if b.name == "Grid")
    corr_in, n, used = etb.correlate(ex["A"], grid, exclude=None)
    assert used == 3 and corr_in is not None and corr_in > 0.9   # A is IN the basket mean
    corr_loo, n2, used2 = etb.correlate(ex["A"], grid, exclude="A")
    assert used2 == 2 and corr_loo is None                        # 2 names left: cannot judge


# ── 2. no lookahead ────────────────────────────────────────────────────────────────────────

def test_session_index_ends_strictly_before_the_scan_date_even_when_later_rows_exist():
    _, tape = _tape(start=date(2026, 8, 1), n=60)  # runs to 2026-09-29, PAST the scan date
    cs = etb.session_index(tape["SPY"], BEFORE)
    assert cs and max(cs) < BEFORE and BEFORE in tape["SPY"]
    assert len(cs) == len([d for d in tape["SPY"] if d < BEFORE])


@pytest.mark.asyncio
async def test_prepare_asks_for_closes_strictly_before_the_scan_date_and_caches_per_day(monkeypatch):
    _, tape = _tape()
    fetch = _fake_fetch(tape)
    monkeypatch.setattr(etb, "fetch_closes", fetch)
    etb._reset_cache()
    ctx = await etb.prepare_basket_context(THEMES, BEFORE)
    assert ctx.cached is False and len(ctx.baskets) == 2 and set(ctx.excess) == {"A", "B", "C"}
    assert ctx.listed_paying == {"A", "B", "C"}
    assert set(ctx.themes_by_name) == {"Grid", "Nas"}         # Fading is not a fit target
    syms, start, end = fetch.calls[0]
    assert end == BEFORE and start < BEFORE and "SPY" in syms and set(syms) >= {"A", "B", "C"}
    assert all(d < BEFORE for d in ctx.close_sessions)

    again = await etb.prepare_basket_context(THEMES, BEFORE)
    assert again is ctx and again.cached is True and len(fetch.calls) == 1   # one query per day

    # a changed board (new member) invalidates the cache; a new day does too
    themes2 = [dict(THEMES[0], tickers=["A", "B", "C", "N"])] + THEMES[1:]
    ctx2 = await etb.prepare_basket_context(themes2, BEFORE)
    assert ctx2 is not ctx and len(fetch.calls) == 2
    ctx3 = await etb.prepare_basket_context(themes2, BEFORE + timedelta(days=1))
    assert ctx3 is not ctx2 and len(fetch.calls) == 3
    etb._reset_cache()


@pytest.mark.asyncio
async def test_score_candidates_fetches_only_the_missing_names_over_the_contexts_window(monkeypatch):
    _, tape = _tape()
    fetch = _fake_fetch(tape)
    monkeypatch.setattr(etb, "fetch_closes", fetch)
    etb._reset_cache()
    ctx = await etb.prepare_basket_context(THEMES, BEFORE)
    reads = await etb.score_candidates(ctx, ["X", "N", "A", "ZZZZ"])
    syms, start, end = fetch.calls[-1]
    assert syms == ["N", "X", "ZZZZ"] and start == ctx.close_sessions[0] and end == BEFORE
    assert reads["X"].fit_status == etb.FIT_PENDING and reads["X"].belongs_paying is False
    assert reads["N"].belongs_paying is False and reads["N"].fit_status == etb.FIT_NOT_SHORTLISTED
    assert reads["A"].reason == "listed"
    assert reads["ZZZZ"].reason == "no_history" and reads["ZZZZ"].belongs_paying is False
    etb._reset_cache()


# ── 3. cannot judge -> today's behaviour ───────────────────────────────────────────────────

def test_thin_history_and_small_baskets_cannot_judge():
    _, tape = _tape()
    cs, ex, baskets, listed = _pure_reads(tape)
    thin = ex["X"].copy()
    thin[:-10] = np.nan                                   # 10 usable sessions only
    r = etb.score_belonging("X", thin, baskets, listed)
    assert r.belongs_paying is False and r.reason == "no_history" and r.best_corr is None
    r2 = etb.score_belonging("X", None, baskets, listed)
    assert r2.reason == "no_history" and r2.belongs_paying is False
    r3 = etb.score_belonging("X", ex["X"], [], listed)
    assert r3.reason == "no_baskets" and r3.belongs_paying is False
    tiny = etb.build_baskets([{"name": "T", "stage": "Accelerating", "tickers": ["A", "B"]}], ex)
    assert tiny == []


# ── 4. stage 2: the fit judgement decides ──────────────────────────────────────────────────

async def _ctx_and_read(monkeypatch, ticker="XQZT"):   # not a universe ticker (X is US Steel)
    _, tape = _tape(comover=ticker)
    monkeypatch.setattr(etb, "fetch_closes", _fake_fetch(tape))
    etb._reset_cache()
    ctx = await etb.prepare_basket_context(THEMES, BEFORE)
    read = (await etb.score_candidates(ctx, [ticker]))[ticker]
    assert read.fit_status == etb.FIT_PENDING
    return ctx, read


PROFILE = {"sector": "Utilities", "description": "Regulated electric utility " * 20}


@pytest.mark.asyncio
async def test_confirmed_belongs_rejected_does_not_and_the_shortlist_alone_is_offered(monkeypatch):
    ctx, read = await _ctx_and_read(monkeypatch)
    calls = _fake_judge(monkeypatch, {"XQZT": (etb.FIT_CONFIRMED, "Grid", "grid gear")})
    budget = etb.FitBudget()
    out = await etb.resolve_fit(read, ctx=ctx, profile=PROFILE, budget=budget, live=True,
                                in_window=True, scan_date=BEFORE)
    assert out.belongs_paying is True and out.reason == "fit"
    assert (out.fit_status, out.fit_theme, out.fit_stage, out.fit_rationale) == \
        (etb.FIT_CONFIRMED, "Grid", "Accelerating", "grid gear")
    assert out.shortlist == read.shortlist and out.listed is False
    ticker, kw = calls[0]
    assert ticker == "XQZT" and [t["name"] for t in kw["themes"]] == ["Grid"]   # never Nas, never Fade
    assert kw["sector"] == "Utilities" and kw["description"].startswith("Regulated electric utility")
    assert len(kw["description"]) <= 300
    assert budget.calls == 1 and budget.confirmed == 1

    etb._reset_cache()
    ctx, read = await _ctx_and_read(monkeypatch)
    _fake_judge(monkeypatch, {"XQZT": (etb.FIT_REJECTED, None, "XQZT: a utility — no fit")})
    out = await etb.resolve_fit(read, ctx=ctx, profile=PROFILE, budget=etb.FitBudget(), live=True,
                                in_window=True, scan_date=BEFORE)
    assert out.belongs_paying is False and out.reason == "shortlisted_rejected"
    assert out.fit_status == etb.FIT_REJECTED and out.fit_theme is None
    assert out.fit_rationale == "XQZT: a utility — no fit"
    etb._reset_cache()


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["failed", "timeout", "error", "budget_tick", "budget_day",
                                      "off", "window", "no_description"])
async def test_every_non_verdict_leaves_list_membership_deciding(monkeypatch, scenario):
    ctx, read = await _ctx_and_read(monkeypatch)
    live, in_window, profile = True, True, PROFILE
    budget = etb.FitBudget()
    if scenario == "failed":
        calls = _fake_judge(monkeypatch, {"XQZT": (etb.FIT_FAILED, None, "no verdict (truncated)")})
    elif scenario == "timeout":
        async def _slow(ticker, **kw):
            await asyncio.sleep(0.2)
            return etb.FIT_CONFIRMED, "Grid", "late"
        calls = _fake_judge(monkeypatch, {"XQZT": _slow})
    elif scenario == "error":
        calls = _fake_judge(monkeypatch, {"XQZT": RuntimeError("api down")})
    elif scenario == "budget_tick":
        calls = _fake_judge(monkeypatch, {"XQZT": (etb.FIT_CONFIRMED, "Grid", "x")})
        budget = etb.FitBudget(per_tick=0)
    elif scenario == "budget_day":
        calls = _fake_judge(monkeypatch, {"XQZT": (etb.FIT_CONFIRMED, "Grid", "x")})
        etb._fit_day["date"], etb._fit_day["calls"] = BEFORE, etb.BELONGING_FIT_CALLS_PER_DAY
    elif scenario == "off":
        calls = _fake_judge(monkeypatch, {"XQZT": (etb.FIT_CONFIRMED, "Grid", "x")})
        live = False
    elif scenario == "window":
        calls = _fake_judge(monkeypatch, {"XQZT": (etb.FIT_CONFIRMED, "Grid", "x")})
        in_window = False
    else:
        calls = _fake_judge(monkeypatch, {"XQZT": (etb.FIT_CONFIRMED, "Grid", "x")})
        profile = {"sector": "Utilities"}          # no one-liner, no FMP text
    out = await etb.resolve_fit(read, ctx=ctx, profile=profile, budget=budget, live=live,
                                in_window=in_window, scan_date=BEFORE, timeout_s=0.02)
    assert out.belongs_paying is False and out.reason == "fit_unjudged"
    assert out.fit_status == {"failed": etb.FIT_FAILED, "timeout": etb.FIT_TIMEOUT,
                              "error": etb.FIT_ERROR, "budget_tick": etb.FIT_BUDGET,
                              "budget_day": etb.FIT_BUDGET, "off": etb.FIT_OFF,
                              "window": etb.FIT_WINDOW,
                              "no_description": etb.FIT_NO_DESCRIPTION}[scenario]
    assert out.fit_theme is None
    spent = scenario in ("failed", "timeout", "error")
    assert (len(calls) == 1) is spent, "a call was spent (or not) when it should not (should) have been"
    assert etb.resolve_theme_bonus_input(False, out, live=True) is False
    assert etb.resolve_theme_bonus_input(True, out, live=True) is True      # listed is listed
    # a non-verdict is never remembered as one: the next tick may judge again
    assert not etb._fit_cache
    etb._reset_cache()


@pytest.mark.asyncio
async def test_a_verdict_is_judged_once_a_day_and_survives_the_post_open_window(monkeypatch):
    ctx, read = await _ctx_and_read(monkeypatch)
    calls = _fake_judge(monkeypatch, {"XQZT": (etb.FIT_CONFIRMED, "Grid", "grid gear")})
    first = await etb.resolve_fit(read, ctx=ctx, profile=PROFILE, budget=etb.FitBudget(), live=True,
                                  in_window=True, scan_date=BEFORE)
    assert first.belongs_paying is True and len(calls) == 1
    # second tick, same day: cached, no call — even at 9:31 with the window shut
    again = await etb.resolve_fit(read, ctx=ctx, profile=PROFILE, budget=etb.FitBudget(per_tick=0),
                                  live=True, in_window=False, scan_date=BEFORE)
    assert again.belongs_paying is True and again.fit_theme == "Grid" and len(calls) == 1
    # a new day forgets yesterday's verdict
    tomorrow = await etb.resolve_fit(read, ctx=ctx, profile=PROFILE, budget=etb.FitBudget(), live=True,
                                     in_window=True, scan_date=BEFORE + timedelta(days=1))
    assert tomorrow.belongs_paying is True and len(calls) == 2
    # a different shortlist is a different question
    other = etb.replace(read, shortlist=(("Other", "Mainstream", 0.5),))
    assert etb._fit_cache and (BEFORE + timedelta(days=1), "XQZT", ("Grid",)) in etb._fit_cache
    assert (BEFORE + timedelta(days=1), "XQZT", ("Other",)) not in etb._fit_cache
    _ = other
    etb._reset_cache()


@pytest.mark.asyncio
async def test_resolve_fit_is_a_no_op_for_anything_not_pending(monkeypatch):
    _, tape = _tape()
    _, ex, baskets, listed = _pure_reads(tape)
    calls = _fake_judge(monkeypatch, {})
    ctx = etb.BasketContext(BEFORE, [], np.zeros(0), {}, baskets, listed, {}, 0.0, 0)
    for read in (etb.score_belonging("A", ex["A"], baskets, listed),     # listed
                 etb.score_belonging("N", ex["N"], baskets, listed)):    # below bar
        assert await etb.resolve_fit(read, ctx=ctx, profile=PROFILE, budget=etb.FitBudget(),
                                     live=True, in_window=True, scan_date=BEFORE) is read
    assert calls == []


def test_with_fit_is_the_one_derivation_and_rejects_unknown_statuses():
    _, tape = _tape()
    _, ex, baskets, listed = _pure_reads(tape)
    x = etb.score_belonging("X", ex["X"], baskets, listed)
    assert etb.with_fit(x, etb.FIT_CONFIRMED, "Grid", "Accelerating", "r").belongs_paying is True
    assert etb.with_fit(x, etb.FIT_REJECTED, rationale="r").reason == "shortlisted_rejected"
    assert etb.with_fit(x, etb.FIT_BUDGET).reason == "fit_unjudged"
    with pytest.raises(ValueError):
        etb.with_fit(x, "maybe")
    a = etb.score_belonging("A", ex["A"], baskets, listed)
    assert etb.with_fit(a, etb.FIT_REJECTED) is a           # listed is listed


def test_candidate_description_prefers_the_nightly_one_liner_then_the_profile():
    from agents.market_intelligence import universe
    universe.TICKER_DESC["ZZTEST"] = "widget maker"
    try:
        assert etb.candidate_description("zztest", {"description": "long", "sector": "Tech"}) == ("widget maker", "Tech")
    finally:
        universe.TICKER_DESC.pop("ZZTEST", None)
    desc, sector = etb.candidate_description("ZZTEST", {"description": "p" * 500})
    assert desc == "p" * 300 and sector is None
    assert etb.candidate_description("ZZTEST", None) == ("", None)


# ── 5. the seam ────────────────────────────────────────────────────────────────────────────

def test_resolve_theme_bonus_input_off_is_list_membership_on_is_the_verdict():
    _, tape = _tape()
    _, ex, baskets, listed = _pure_reads(tape)
    x = etb.with_fit(etb.score_belonging("X", ex["X"], baskets, listed), etb.FIT_CONFIRMED, "Grid",
                     "Accelerating", "r")                       # unlisted, belongs by fit
    n = etb.score_belonging("N", ex["N"], baskets, listed)     # unlisted, does not
    for read in (x, n, None):
        for listed_flag in (True, False):
            assert etb.resolve_theme_bonus_input(listed_flag, read, live=False) is listed_flag
    assert etb.resolve_theme_bonus_input(False, x, live=True) is True
    assert etb.resolve_theme_bonus_input(False, n, live=True) is False
    assert etb.resolve_theme_bonus_input(True, n, live=True) is True      # listed is listed
    assert etb.resolve_theme_bonus_input(False, None, live=True) is False  # no read: unchanged
    assert etb.resolve_theme_bonus_input(True, None, live=True) is True


def test_the_scorer_moves_by_the_existing_ten_raw_points_and_nothing_else():
    kw = dict(gap_pct=12.0, rel_volume=3.0, catalyst_quality="strong", profile={"floatShares": 80_000_000},
              regime_multiplier=1.0, vol_percentile=50.0, adv_dollar=300_000_000.0, weights=SCORE_WEIGHTS)
    s0, b0 = _score_ep(in_active_theme=False, **kw)
    s1, b1 = _score_ep(in_active_theme=True, **kw)
    assert b0["theme_bonus"] == 0 and b1["theme_bonus"] == SCORE_WEIGHTS["theme_bonus"]["points"] == 10
    assert {k: v for k, v in b0.items() if k != "theme_bonus"} == {k: v for k, v in b1.items() if k != "theme_bonus"}
    assert s1 > s0


# ── 6. the toggle: default ON, the revert row ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fresh_deploy_is_on_even_with_the_db_unreachable_and_a_row_off_reverts(monkeypatch):
    from agents.market_intelligence import db
    monkeypatch.delenv("EP_THEME_BELONGING_ENABLED", raising=False)
    name = etb.BELONGING_TOGGLE[0]
    db._runtime_toggle_cache.pop(name, None)
    monkeypatch.setattr(db, "get_safeguard_state", AsyncMock(side_effect=RuntimeError("db down")))
    assert await etb.read_belonging_toggle() is True
    db._runtime_toggle_cache.pop(name, None)
    monkeypatch.setattr(db, "get_safeguard_state", AsyncMock(return_value={"state": "off"}))
    assert await etb.read_belonging_toggle() is False
    db._runtime_toggle_cache.pop(name, None)
    monkeypatch.setattr(db, "get_safeguard_state", AsyncMock(return_value=None))
    assert await etb.read_belonging_toggle() is True
    db._runtime_toggle_cache.pop(name, None)


# ── 7/8. the shadow record ─────────────────────────────────────────────────────────────────

def _real_row(**over):
    _, tape = _tape()
    _, ex, baskets, listed = _pure_reads(tape)
    read = etb.with_fit(etb.score_belonging("X", ex["X"], baskets, listed),
                        etb.FIT_CONFIRMED, "Grid", "Accelerating", "grid gear")
    kw = dict(ticker="X", listed=False, acting_in_theme=True, ep_score_acting=70.0,
              ep_score_listed_only=57.5, ep_score_with_belonging=70.0, ep_bar=65.0, toggle_on=True)
    kw.update(over)
    return read, etb.build_belonging_shadow_row(read, **kw)


def test_shadow_row_contract_is_pinned_at_the_real_producer():
    read, row = _real_row()
    sql = etb.EP_THEME_BELONGING_SHADOW_UPSERT_SQL
    params = etb.shadow_row_params(row, BEFORE, TS)
    max_placeholder = max(int(m) for m in re.findall(r"\$(\d+)", sql))
    assert len(params) == max_placeholder == 3 + len(etb.SHADOW_ROW_PARAM_KEYS)
    cols = [c.strip() for c in sql.split("mi_ep_theme_belonging_shadow (", 1)[1].split(") VALUES", 1)[0].split(",")]
    binds = [v.strip() for v in sql.split("VALUES (", 1)[1].split("\n    )", 1)[0].split(",")]
    assert len(cols) == len(binds) == 31
    assert row["best_theme"] == read.best_theme == "Grid" and row["best_corr"] == read.best_corr
    assert row["reason"] == "fit" and row["belongs_paying"] is True and row["listed"] is False
    assert (row["fit_status"], row["fit_theme"], row["fit_stage"], row["fit_rationale"]) == \
        ("confirmed", "Grid", "Accelerating", "grid gear")
    assert json.loads(row["shortlist"]) == [{"theme": "Grid", "stage": "Accelerating", "corr": read.best_corr}]
    assert json.loads(row["nascent_shortlist"])[0]["theme"] == "Nas"
    assert row["crossed_bar"] is True                     # 57.5 < 65 <= 70
    assert row["stage_set"] == "Accelerating+Mainstream" and row["shortlist_bar"] == etb.BELONGING_SHORTLIST_CORR_BAR
    _, same_side = _real_row(ep_score_listed_only=70.0)
    assert same_side["crossed_bar"] is False
    none_row = etb.build_belonging_shadow_row(None, ticker="Q", listed=True, acting_in_theme=True,
                                              ep_score_acting=80.0, ep_score_listed_only=80.0,
                                              ep_score_with_belonging=80.0, ep_bar=65.0, toggle_on=True)
    assert none_row["reason"] == "no_read" and none_row["fit_status"] == "no_read"
    assert none_row["belongs_paying"] is True and none_row["listed"] is True and none_row["shortlist"] is None


@pytest.mark.asyncio
async def test_recorder_binds_the_producer_row_positionally_and_never_raises(monkeypatch):
    _, row = _real_row()
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(etb, "get_pool", AsyncMock(return_value=pool))
    assert await etb.record_ep_theme_belonging_shadow([row, dict(row, ticker="Y")], BEFORE, TS) == 2
    sql, *params = conn.execute.call_args_list[0].args
    assert sql is etb.EP_THEME_BELONGING_SHADOW_UPSERT_SQL
    assert params[0] == BEFORE and params[1] == "X" and params[2] == TS
    off = 3
    keys = etb.SHADOW_ROW_PARAM_KEYS
    assert params[off + keys.index("best_corr")] == row["best_corr"]
    assert params[off + keys.index("fit_theme")] == "Grid"
    assert params[off + keys.index("ep_score_with_belonging")] == 70.0
    assert params[off + keys.index("crossed_bar")] is True
    assert params[off + keys.index("stage_set")] == "Accelerating+Mainstream"
    assert await etb.record_ep_theme_belonging_shadow([], BEFORE, TS) == 0

    conn.execute = AsyncMock(side_effect=RuntimeError("type deduction"))
    assert await etb.record_ep_theme_belonging_shadow([row], BEFORE, TS) == 0
    monkeypatch.setattr(etb, "get_pool", AsyncMock(side_effect=RuntimeError("no db")))
    assert await etb.record_ep_theme_belonging_shadow([row], BEFORE, TS) == 0


def test_recorder_is_registered_for_the_deploy_prepare_gate():
    from scripts import preflight_db_updates as pf
    assert any(sql is etb.EP_THEME_BELONGING_SHADOW_UPSERT_SQL for _, sql in pf.SHADOW_WRITER_STATEMENTS)


def test_the_stage_set_is_one_name_shared_with_the_detector():
    from agents.market_intelligence import ep_detector
    assert ep_detector.THEME_BONUS_STAGES is etb.THEME_BONUS_STAGES == ("Accelerating", "Mainstream")


# ── 9. THE WIRING — run_ep_scan end to end ─────────────────────────────────────────────────

def _canon(obj):
    return json.dumps(obj, sort_keys=True, default=str)


_PRISTINE_PREPARE_BASKET_CONTEXT = etb.prepare_basket_context


async def _scan_with_belonging(monkeypatch, *, toggle_on: bool, themes, verdict=None,
                               premarket: bool = True, seed=None):
    """One real run_ep_scan on the test_624 fixture board (ADMIT_TICKER rides the graded path
    to a HIGH alert), with the theme board substituted (the harness mocks get_active_themes to
    []), the closes fetch served from a synthetic tape where ADMIT_TICKER co-moves with the
    theme's members, the fit judgement scripted (`verdict`), and the recorder captured.
    The harness freezes the clock at 9:31:12 ET — INSIDE the ORB window — so `premarket=True`
    patches the guard's own predicate (`ep_detector._is_premarket`) to exercise the call path;
    `premarket=False` is the real 9:31 tick, where only a `seed`ed (earlier, cached) verdict
    may pay. Returns (results, scan_log, alerts, rows, judge_calls)."""
    from agents.market_intelligence import ep_detector
    from tests.test_624_lowcap_lane import ADMIT_TICKER, SESSION_DATE, _run_scan_once
    _, tape = _tape(comover=ADMIT_TICKER)
    etb._reset_cache()
    if seed is not None:
        etb._fit_day["date"], etb._fit_day["calls"] = SESSION_DATE, 1
        etb._fit_cache[(SESSION_DATE, ADMIT_TICKER, ("Grid",))] = seed
    if premarket:
        monkeypatch.setattr(ep_detector, "_is_premarket", lambda now_et: True)
    # the fixture's FMP profile carries no description; the universe one-liner is the
    # description path the judgement prefers anyway
    from agents.market_intelligence import universe
    monkeypatch.setitem(universe.TICKER_DESC, ADMIT_TICKER, "Grid transformers & switchgear")
    # The PRISTINE function, captured at import. Reading `etb.prepare_basket_context` here
    # re-captures whatever a PREVIOUS call to this harness already patched in, so a second
    # call would chain into the first call's closure and silently reuse the FIRST board —
    # which is exactly how the "toggle OFF is not the pre-fix scan" failure was manufactured:
    # the themes=[] scan was still being served THEMES.
    real_prep = _PRISTINE_PREPARE_BASKET_CONTEXT

    async def _prep(_themes, before_date, **kw):
        return await real_prep(themes, before_date, **kw)

    rows: list = []

    async def _rec(batch, scan_date, now_et):
        rows.extend(batch)
        return len(batch)

    monkeypatch.setattr(etb, "prepare_basket_context", _prep)
    monkeypatch.setattr(etb, "fetch_closes", _fake_fetch(tape))
    monkeypatch.setattr(etb, "get_runtime_toggle", AsyncMock(return_value=toggle_on))
    monkeypatch.setattr(etb, "record_ep_theme_belonging_shadow", _rec)
    judge_calls = _fake_judge(monkeypatch, {ADMIT_TICKER: verdict or (etb.FIT_CONFIRMED, "Grid", "grid gear")})
    results, scan_log, alerts, _ = await _run_scan_once(monkeypatch, lane_mode="off", admit=True)
    etb._reset_cache()
    return results, scan_log, alerts, rows, judge_calls


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["confirmed", "rejected", "off", "open_uncached", "open_cached"])
async def test_run_ep_scan_pays_a_confirmed_fit_not_a_rejected_one_and_the_toggle_reverts_it(monkeypatch, case):
    from tests.test_624_lowcap_lane import ADMIT_TICKER
    verdict = (etb.FIT_REJECTED, None, "no fit") if case == "rejected" else (etb.FIT_CONFIRMED, "Grid", "grid gear")
    results, scan_log, alerts, rows, judge_calls = await _scan_with_belonging(
        monkeypatch, toggle_on=(case != "off"), themes=THEMES, verdict=verdict,
        premarket=case in ("confirmed", "rejected", "off"),
        seed=(etb.FIT_CONFIRMED, "Grid", "Accelerating", "judged at 8:05") if case == "open_cached" else None)
    pays = case in ("confirmed", "open_cached")
    assert [r["ticker"] for r in results] == [ADMIT_TICKER] and len(alerts) == 1
    assert results[0]["score_breakdown"]["theme_bonus"] == (10 if pays else 0)
    # the row/payload column keeps its LIST-MEMBERSHIP meaning either way (the judge, the
    # theme-gap feed and every historical analysis read it that way)
    assert alerts[0]["in_active_theme"] is False and results[0]["in_active_theme"] is False
    row = next(r for r in rows if r["ticker"] == ADMIT_TICKER)
    assert row["listed"] is False and json.loads(row["shortlist"])[0]["theme"] == "Grid"
    assert json.loads(row["shortlist"])[0]["corr"] >= etb.BELONGING_SHORTLIST_CORR_BAR
    assert row["best_theme"] == "Grid" and row["best_stage"] == "Accelerating"
    assert row["belongs_paying"] is pays and row["acting_in_theme"] is pays
    if case == "confirmed":
        assert (row["reason"], row["fit_status"], row["fit_theme"]) == ("fit", "confirmed", "Grid")
        assert len(judge_calls) == 1 and [t["name"] for t in judge_calls[0][1]["themes"]] == ["Grid"]
    elif case == "rejected":
        assert (row["reason"], row["fit_status"], row["fit_theme"]) == ("shortlisted_rejected", "rejected", None)
        assert len(judge_calls) == 1
    elif case == "off":
        assert (row["reason"], row["fit_status"]) == ("fit_unjudged", "off")
        assert judge_calls == [], "a reverted fix must not spend a fit call"
    elif case == "open_uncached":
        # the real 9:31 tick with nothing judged earlier: NO call on the ORB entry path,
        # list membership decides — the #344 posture
        assert (row["reason"], row["fit_status"]) == ("fit_unjudged", "window")
        assert judge_calls == [], "a fit call was spent inside the ORB window"
    else:
        # the real 9:31 tick with a verdict judged premarket: it pays, still no call
        assert (row["reason"], row["fit_status"], row["fit_rationale"]) == ("fit", "confirmed", "judged at 8:05")
        assert judge_calls == []
    assert row["toggle_on"] is (case != "off")
    assert row["ep_score_acting"] == results[0]["ep_score"]
    assert row["ep_bar"] == 65.0 and row["stage_set"] == "Accelerating+Mainstream"
    # the fixture's game_changer + 20% gap sits ON the branch-4 conviction floor, so the +10
    # is absorbed by the floor here (breakdown moves, final does not) — the record says so
    assert row["ep_score_listed_only"] == row["ep_score_with_belonging"] and row["crossed_bar"] is False
    assert len(rows) == 1   # every other filler dies at the RVOL gate before scoring


@pytest.mark.asyncio
async def test_toggle_off_is_byte_identical_to_a_scan_with_no_belonging_at_all(monkeypatch):
    off = await _scan_with_belonging(monkeypatch, toggle_on=False, themes=THEMES)
    none = await _scan_with_belonging(monkeypatch, toggle_on=True, themes=[])   # no board -> no baskets
    for a, b, what in ((off[0], none[0], "results"), (off[1], none[1], "scan_log"), (off[2], none[2], "alerts")):
        assert _canon(a) == _canon(b), f"{what} differ: toggle OFF is not the pre-fix scan"
    assert none[3][0]["reason"] == "no_baskets" and none[3][0]["acting_in_theme"] is False
    assert off[4] == [] and none[4] == []


def test_the_cached_basket_mean_is_used_only_when_nothing_is_excluded():
    """The all-members mean is computed once at build (it depends on the BASKET, not the
    candidate) — but a candidate that is ITSELF a member must still get the leave-one-out
    recompute, or it would be correlated against a mean containing its own returns.

    Mutation that proves this test: make `correlate` always read `basket.mean_all` (drop the
    `len(keep) == len(basket.members)` guard) and the excluded/included correlations become
    equal, failing the last assertion while the rest of the file still passes.
    """
    import numpy as np
    ex = {
        "A": np.array([0.01, 0.02, -0.01, 0.03, 0.02, -0.02, 0.01, 0.02, 0.03, -0.01, 0.02, 0.01]),
        "B": np.array([0.011, 0.021, -0.009, 0.031, 0.019, -0.021, 0.011, 0.019, 0.029, -0.011, 0.021, 0.009]),
        "C": np.array([-0.02, 0.03, 0.01, -0.03, 0.02, 0.01, -0.01, 0.03, -0.02, 0.01, 0.02, -0.03]),
        "D": np.array([0.005, 0.015, -0.005, 0.02, 0.01, -0.01, 0.005, 0.012, 0.02, -0.005, 0.015, 0.004]),
    }
    bk = etb.build_baskets([{"name": "T", "stage": "Mainstream", "tickers": ["A", "B", "C", "D"]}],
                           ex, stages=("Mainstream",), min_members=3, min_overlap=5)[0]

    # the cache is the honest full recompute, not a different number
    assert np.allclose(bk.mean_all, mac._basket_mean(bk.matrix, 3), equal_nan=True)

    corr_excl, _, n_excl = etb.correlate(ex["A"], bk, exclude="A", min_members=3, min_overlap=5)
    corr_incl, _, n_incl = etb.correlate(ex["A"], bk, min_members=3, min_overlap=5)
    assert n_excl == 3 and n_incl == 4                 # leave-one-out really drops a row
    assert abs(corr_excl - corr_incl) > 1e-9           # and it is NOT reading the cached mean
