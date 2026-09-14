"""Theme BELONGING for the EP score (2026-09-13, operator-directed BUG FIX) — behaviour pins.

The +10 theme bonus keys on whether the alerting stock BELONGS to a live theme at alert time
(listed OR co-moving with a THEME_BONUS_STAGES basket over the sessions strictly before the
scan date), not on last night's ticker list alone. Module: ep_theme_belonging.py; wiring:
ep_detector.run_ep_scan; SSoT: docs/setups/magna53_ep.md change log 2026-09-13.

Pinned here, all through the REAL functions (no source-text assertions):
  1. the belonging math — an unlisted co-mover belongs, noise does not, a listed member is
     listed, Nascent baskets are read but never pay, Fading never builds a basket;
  2. NO LOOKAHEAD — the window ends strictly before the scan date even when the fetch
     returns later rows, and the fetch itself is asked for `< scan date`;
  3. "cannot judge" -> today's behaviour (thin history, 1-2 member baskets, no baskets);
  4. the seam: toggle OFF is list membership for every input; ON is the verdict;
  5. the toggle's default on a fresh deploy (ON, even with the DB unreachable) and the
     revert row (state 'off') — through the real db.get_runtime_toggle;
  6. the shadow record's contract, pinned at the REAL producer (score_belonging ->
     build_belonging_shadow_row -> shadow_row_params -> the upsert's placeholders) — the
     #649 lesson: a fixture that invents the recorder's input is a claim about the caller;
  7. the recorder is registered for the deploy-time prepare gate and never raises;
  8. THE WIRING — run_ep_scan end to end (the test_624 harness): an unlisted co-mover on the
     graded shortlist gets theme_bonus 10 with the toggle ON and 0 with it OFF, the alert
     row's `in_active_theme` keeps its list-membership meaning either way, the shadow row
     records both, and toggle OFF is byte-identical to a scan with no belonging at all.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from agents.market_intelligence import ep_theme_belonging as etb
from agents.market_intelligence.ep_detector import _score_ep
from agents.market_intelligence.ep_rubric import SCORE_WEIGHTS
from tests.conftest import make_mock_pool

_ET = ZoneInfo("America/New_York")
TS = datetime(2026, 9, 3, 9, 31, 12, tzinfo=_ET)
BEFORE = date(2026, 9, 3)

THEMES = [
    {"name": "Grid", "stage": "Accelerating", "tickers": ["A", "B", "C"]},
    {"name": "Nas", "stage": "Nascent", "tickers": ["A", "B", "C"]},
    {"name": "Fade", "stage": "Fading", "tickers": ["A", "B", "C"]},
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


# ── 1. the belonging math ──────────────────────────────────────────────────────────────────

def test_unlisted_co_mover_belongs_noise_does_not_listed_is_listed():
    _, tape = _tape()
    cs, ex, baskets, listed = _pure_reads(tape)
    assert len(cs) == etb.BELONGING_LOOKBACK_SESSIONS + 1
    # Fading never builds a basket; Nascent does (shadow read) — one paying, one Nascent
    assert sorted((b.name, b.stage) for b in baskets) == [("Grid", "Accelerating"), ("Nas", "Nascent")]

    x = etb.score_belonging("X", ex["X"], baskets, listed)
    assert x.listed is False and x.belongs_paying is True and x.reason == "comoves"
    assert x.best_theme == "Grid" and x.best_stage == "Accelerating"
    assert x.best_corr >= etb.BELONGING_CORR_BAR and x.n_sessions == etb.BELONGING_LOOKBACK_SESSIONS
    assert x.basket_n == 3
    assert x.belongs_incl_nascent is True and x.best_nascent_theme == "Nas"

    n = etb.score_belonging("N", ex["N"], baskets, listed)
    assert n.belongs_paying is False and n.belongs_incl_nascent is False and n.reason == "below_bar"
    assert n.best_corr is not None and n.best_corr < etb.BELONGING_CORR_BAR

    a = etb.score_belonging("A", ex["A"], baskets, listed)
    assert a.listed is True and a.belongs_paying is True and a.reason == "listed"


def test_nascent_basket_never_pays_on_its_own():
    """A stock that co-moves ONLY with a Nascent theme: recorded in the shadow read, never
    acting — the stage question is the operator's, kept separate by construction."""
    _, tape = _tape()
    cs, ex, _, _ = _pure_reads(tape)
    only_nascent = [{"name": "Nas", "stage": "Nascent", "tickers": ["A", "B", "C"]}]
    baskets = etb.build_baskets(only_nascent, ex)
    x = etb.score_belonging("X", ex["X"], baskets, set())
    assert x.belongs_paying is False and x.belongs_incl_nascent is True
    assert x.best_theme is None and x.best_nascent_theme == "Nas"
    assert x.reason == "below_bar"


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
    assert reads["X"].belongs_paying is True and reads["X"].reason == "comoves"
    assert reads["N"].belongs_paying is False
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


# ── 4. the seam ────────────────────────────────────────────────────────────────────────────

def test_resolve_theme_bonus_input_off_is_list_membership_on_is_the_verdict():
    _, tape = _tape()
    _, ex, baskets, listed = _pure_reads(tape)
    x = etb.score_belonging("X", ex["X"], baskets, listed)     # unlisted, belongs
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


# ── 5. the toggle: default ON, the revert row ──────────────────────────────────────────────

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


# ── 6/7. the shadow record ─────────────────────────────────────────────────────────────────

def _real_row(**over):
    _, tape = _tape()
    _, ex, baskets, listed = _pure_reads(tape)
    read = etb.score_belonging("X", ex["X"], baskets, listed)
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
    assert len(cols) == len(binds) == 28
    assert row["best_theme"] == read.best_theme == "Grid" and row["best_corr"] == read.best_corr
    assert row["reason"] == "comoves" and row["belongs_paying"] is True and row["listed"] is False
    assert row["crossed_bar"] is True                     # 57.5 < 65 <= 70
    assert row["stage_set"] == "Accelerating+Mainstream" and row["corr_bar"] == etb.BELONGING_CORR_BAR
    _, same_side = _real_row(ep_score_listed_only=70.0)
    assert same_side["crossed_bar"] is False
    _, no_read = _real_row()
    none_row = etb.build_belonging_shadow_row(None, ticker="Q", listed=True, acting_in_theme=True,
                                              ep_score_acting=80.0, ep_score_listed_only=80.0,
                                              ep_score_with_belonging=80.0, ep_bar=65.0, toggle_on=True)
    assert none_row["reason"] == "no_read" and none_row["belongs_paying"] is True and none_row["listed"] is True


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


# ── 8. THE WIRING — run_ep_scan end to end ─────────────────────────────────────────────────

def _canon(obj):
    return json.dumps(obj, sort_keys=True, default=str)


async def _scan_with_belonging(monkeypatch, *, toggle_on: bool, themes):
    """One real run_ep_scan on the test_624 fixture board (ADMIT_TICKER rides the graded path
    to a HIGH alert), with the theme board substituted (the harness mocks get_active_themes to
    []), the closes fetch served from a synthetic tape where ADMIT_TICKER co-moves with the
    theme's members, and the recorder captured. Returns (results, scan_log, alerts, rows)."""
    from tests.test_624_lowcap_lane import ADMIT_TICKER, _run_scan_once
    _, tape = _tape(comover=ADMIT_TICKER)
    etb._reset_cache()
    real_prep = etb.prepare_basket_context

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
    results, scan_log, alerts, _ = await _run_scan_once(monkeypatch, lane_mode="off", admit=True)
    etb._reset_cache()
    return results, scan_log, alerts, rows


@pytest.mark.asyncio
@pytest.mark.parametrize("toggle_on", [True, False])
async def test_run_ep_scan_pays_an_unlisted_co_mover_when_on_and_the_toggle_reverts_it(monkeypatch, toggle_on):
    from tests.test_624_lowcap_lane import ADMIT_TICKER
    results, scan_log, alerts, rows = await _scan_with_belonging(monkeypatch, toggle_on=toggle_on, themes=THEMES)
    assert [r["ticker"] for r in results] == [ADMIT_TICKER] and len(alerts) == 1
    assert results[0]["score_breakdown"]["theme_bonus"] == (10 if toggle_on else 0)
    # the row/payload column keeps its LIST-MEMBERSHIP meaning either way (the judge, the
    # theme-gap feed and every historical analysis read it that way)
    assert alerts[0]["in_active_theme"] is False and results[0]["in_active_theme"] is False
    row = next(r for r in rows if r["ticker"] == ADMIT_TICKER)
    assert row["listed"] is False and row["reason"] == "comoves" and row["belongs_paying"] is True
    assert row["best_theme"] == "Grid" and row["best_stage"] == "Accelerating"
    assert row["best_corr"] >= etb.BELONGING_CORR_BAR
    assert row["acting_in_theme"] is toggle_on and row["toggle_on"] is toggle_on
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
