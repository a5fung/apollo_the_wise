"""#705 (c) - the Consolidation Breakout forward shadow records `pp` (his carried exit) beside `A`.

What is pinned, and against what:

  1. THE WALK (`consolidation_breakout_pp`): the port equals the RUNNER's registered `exitpb_walk_arms` (the definition of
     `pp`, hard-pinned) event for event on scenario tails and on a fuzz of random daily + minute days, and `A` equals the
     module's own `cb.walk_his_arms` on `c3_p33_t20_cut3`. Nothing here may drift from what was registered.
  2. THE DAY-0 FACTS: computed once at entry time from the minutes the entry step holds, JSON round-trip safe; a fill with
     no minute after it (the daily `close` variant) is "nothing happened on day 0".
  3. THE JOB (in-memory store with the SQL's guards): a filled entry gets a `pp` and an `A` row the night it is recorded,
     each equal to the registered walk fed the real minutes; no minute is fetched by the exit step; a pre-change fill (no
     facts) is not walked; restart-safe; split handling as the registered arms'; a failure in the pp step cannot touch the
     fifteen registered arms.
  4. THE FIFTEEN ARE UNTOUCHED: their rows (and the entry rows' existing columns) are byte-identical to what the code
     produced before this change on the same fixtures (a frozen digest taken from the pre-change code), and the registered
     work list never counts a `pp` / `A` row.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json

import numpy as np
import pytest

from agents.market_intelligence import consolidation_breakout as cb
from agents.market_intelligence import consolidation_breakout_pp as ppx
from agents.market_intelligence import consolidation_breakout_shadow as sh
from agents.market_intelligence import db
from scripts.probes._cb_backtest import runner as rn
from tests.cb_shadow_support import (BREAK_DAY, WATCH_NIGHT, FakeCollector, FakeStore, build_market, make_world,
                                     synth_minutes)
from tests.cb_shadow_support import mrna_bars as _mrna_bars
from tests.cb_shadow_support import polygon_cs as _polygon
from tests.cb_shadow_support import run_shadow as run
from tests.test_cb_backtest_runner import (STALL_TAIL, XP_FILL, XP_GOLDEN_TAIL, XP_PROFIT_TAIL, XP_STOP, _mb,
                                           _stall_minutes, _weekdays, _xp_bars)

D = dt.date


def _roundtrip(facts: dict) -> dict:
    """What the JSONB column does to the facts: dumped and loaded."""
    return json.loads(json.dumps(facts))


def _same(a: dict, b: dict) -> None:
    assert a["status"] == b["status"]
    assert a["sessions_held"] == b["sessions_held"]
    assert a["realized_r"] == b["realized_r"] and a["pnl_adr"] == b["pnl_adr"]
    assert [tuple(e) for e in a["events"]] == [tuple(e) for e in b["events"]]


def _both(bars, e, mb, *, fill, stop, fill_minute=7, adr20=0.10):
    fwd, _cut = cb.forward_window(bars, np.arange(len(bars)), e, rn.HORIZON)
    entry = {"fill": fill, "stop": stop, "fill_minute": fill_minute}
    want = rn.exitpb_walk_arms(entry, closes_before=bars.c[:e + 1], fwd=fwd, adr20=adr20, minutes=mb, horizon=rn.HORIZON,
                               arms={n: rn.EXITPB_ARMS[n] for n in ppx.PP_ARMS})
    facts = _roundtrip(ppx.day0_facts(mb, fill=fill, stop=stop, fill_minute=fill_minute))
    got = ppx.walk_pp_arms(entry, facts, closes_before=bars.c[:e + 1], fwd=fwd, adr20=adr20)
    return want, got, fwd


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 1. the walk
# ═══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheWalkEqualsTheRegisteredDefinition:
    def test_the_arm_names_and_the_shared_mechanics_are_the_registered_ones(self):
        assert ppx.PP_ARMS == ("A", "pp") == (rn.EXITPB_CONTROL, rn.EXITPB_RULED)
        assert set(ppx.PP_ARMS).isdisjoint(cb.ARMS)   # the exit upsert key is (entry_id, arm): a registered arm named A / pp would be overwritten
        assert ppx._BASE is rn.EXITPB_BASE is cb.CUT_EXIT_ARMS[cb.P5_PRIMARY_ARM]
        assert ppx.LEG_FIRST == rn.EXITPB_LEG_FIRST == 3
        for name in ppx.PP_ARMS:
            assert ppx.SESSION_RULE[name] == rn.EXITPB_ARMS[name].session_rule and rn.EXITPB_ARMS[name].stop_rule == "entry"
            assert rn.EXITPB_ARMS[name].day0_breakeven          # ONE day-0 walk (breakeven on) serves both arms
        assert db.CB_OPEN_ENTRIES_SQL.count("NOT IN ('A', 'pp')") == 1 and db.CB_STALE_OPEN_COUNT_SQL.count("NOT IN ('A', 'pp')") == 1

    def test_scenario_tails_equal_the_runner_event_for_event(self):
        seen = set()
        for name, tail in {"golden": XP_GOLDEN_TAIL, "profit": XP_PROFIT_TAIL, "staller": STALL_TAIL,
                           "gap_under": [(10.60, 10.85, 10.50, 10.80), (10.70, 10.75, 10.25, 10.70), (9.50, 9.60, 9.40, 9.50)]}.items():
            for hist in (10.0, 10.5):
                for minutes in (None, _stall_minutes()):
                    bars, e = _xp_bars(tail, hist=hist)
                    want, got, _ = _both(bars, e, _mb(minutes), fill=XP_FILL, stop=XP_STOP)
                    for arm in ppx.PP_ARMS:
                        _same(want[arm], got[arm])
                        seen.add((arm, got[arm]["status"]))
        assert {("A", "stopped"), ("pp", "stopped"), ("A", "time_exit"), ("pp", "trailed")} <= seen

    def test_the_golden_tail_is_where_pp_and_A_part_ways(self):
        """d3 closes at 10.25, under the 10.30 fill: A sells its third there whatever the price, pp does not (and the trail is
        live from session 3 for pp whether or not the third sold)."""
        bars, e = _xp_bars(XP_GOLDEN_TAIL, hist=10.5)
        _want, got, _ = _both(bars, e, _mb(None), fill=XP_FILL, stop=XP_STOP)
        a_sess = [ev for ev in got["A"]["events"] if ev[1] == "partial"]
        pp_sess = [ev for ev in got["pp"]["events"] if ev[1] == "partial"]
        assert len(a_sess) == 1 and a_sess[0][0] == 3 and a_sess[0][2] < XP_FILL
        assert pp_sess == []
        assert got["A"]["realized_r"] != got["pp"]["realized_r"]

    def test_pp_equals_A_when_the_third_sells_above_the_fill(self):
        """A +2R third (or an above-fill session third) is the same on both arms; the arms differ only where A sold at or
        under the fill."""
        bars, e = _xp_bars(XP_PROFIT_TAIL, hist=10.0)
        _want, got, _ = _both(bars, e, _mb(None), fill=XP_FILL, stop=XP_STOP)
        part = [ev for ev in got["pp"]["events"] if ev[1] in ("partial", "partial_r")]
        a_part = [ev for ev in got["A"]["events"] if ev[1] in ("partial", "partial_r")]
        assert part and all(ev[2] > XP_FILL for ev in part) and a_part[0][2] > XP_FILL      # the precondition, by construction
        _same(got["A"], got["pp"])

    def test_a_fuzz_of_random_days_equals_the_runner_and_A_equals_the_module(self):
        rng = np.random.default_rng(705)
        seen, partial_kinds, differ = set(), set(), 0
        for seed in range(400):
            n, e = 200, 150
            sig = float(rng.choice([0.015, 0.03, 0.05]))
            fade = seed % 2 == 1                           # half the days: reach +1R early, then roll over through the fill
            steps = rng.normal(0.002, sig, n)
            if fade:
                steps[e + 1:] = rng.normal(-0.012, 0.012, n - e - 1)
            c = 10.0 * np.exp(np.cumsum(steps))
            o = c * (1 + rng.normal(0, 0.01, n))
            h = np.maximum(o, c) * (1 + rng.uniform(0, 0.03, n))
            l = np.minimum(o, c) * (1 - rng.uniform(0, 0.03, n))
            bars = cb.daily_bars_from_arrays(_weekdays(n), o, h, l, c, np.full(n, 1e6))
            fill = float(o[e]) * 1.01
            stop = fill * (1 - rng.uniform(0.01, 0.06))
            # minute day: a drift that sometimes reaches +2R, sometimes dips through the stop
            px, mins = fill, []
            drift = float(rng.choice([-0.0004, 0.0, 0.00005, 0.0002, 0.0012]))
            for m in range(390):
                px *= 1 + rng.normal(drift, 0.002)
                mo, mc = px, px * (1 + rng.normal(0, 0.001))
                mins.append((m, mo, max(mo, mc) * (1 + rng.uniform(0, 0.002)), min(mo, mc) * (1 - rng.uniform(0, 0.002)), mc))
            mb = _mb(mins)
            want, got, fwd = _both(bars, e, mb, fill=fill, stop=stop, adr20=0.05)
            for arm in ppx.PP_ARMS:
                _same(want[arm], got[arm])
                seen.add(got[arm]["status"])
                partial_kinds.update(ev[1] for ev in got[arm]["events"])
            # A is the module's own walk of c3_p33_t20_cut3 (the registered control), the `stop_to` events aside
            entry2 = {"status": "filled", "reason": None, "fill": fill, "stop": stop, "width_pct": (fill - stop) / fill,
                      "fill_minute": 7, "day0": cb.day0_walk(mb, fill_minute=7, stop=stop)}
            ref = cb.walk_his_arms(entry2, closes_before=bars.c[:e + 1], fwd=fwd, adr20=0.05, minutes=mb, horizon=rn.HORIZON,
                                   arms={cb.P5_PRIMARY_ARM: cb.CUT_EXIT_ARMS[cb.P5_PRIMARY_ARM]})[cb.P5_PRIMARY_ARM]
            assert rn.exitpb_compare_module(f"seed{seed}", ref, got["A"]) == []
            differ += int(got["A"]["realized_r"] != got["pp"]["realized_r"])
        # the fuzz reaches the interesting places
        assert {"stopped", "stopped_day0", "trailed", "time_exit"} <= seen
        assert {"partial_r", "partial", "cut", "trail", "stop_to"} <= partial_kinds
        assert differ > 0

    def test_a_pp_session_third_is_always_above_the_fill_and_every_third_moves_the_stop_to_cost(self):
        rng = np.random.default_rng(7051)
        n_thirds = 0
        for seed in range(120):
            n, e = 200, 150
            c = 10.0 * np.exp(np.cumsum(rng.normal(0.002, 0.03, n)))
            o = c * (1 + rng.normal(0, 0.01, n))
            h = np.maximum(o, c) * (1 + rng.uniform(0, 0.03, n))
            l = np.minimum(o, c) * (1 - rng.uniform(0, 0.03, n))
            bars = cb.daily_bars_from_arrays(_weekdays(n), o, h, l, c, np.full(n, 1e6))
            fill = float(o[e]) * 1.01
            stop = fill * (1 - rng.uniform(0.02, 0.06))
            mb = _mb([(m, fill, fill * 1.001, fill * 0.999, fill) for m in range(390)])
            _w, got, _ = _both(bars, e, mb, fill=fill, stop=stop, adr20=0.05)
            for ev in got["pp"]["events"]:
                if ev[1] == "partial":
                    assert ev[2] > fill
                if ev[1] == "stop_to":
                    assert ev[2] == max(stop, fill)
                    n_thirds += 1
        assert n_thirds > 0


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 2. the day-0 facts
# ═══════════════════════════════════════════════════════════════════════════════════════════════
class TestDay0Facts:
    def test_a_quiet_day_has_a_peak_and_nothing_else(self):
        f = ppx.day0_facts(_mb(None), fill=XP_FILL, stop=XP_STOP, fill_minute=7)
        assert f["v"] == 1 and f["stopped"] is False and f["partial_price"] is None and f["exit_price"] is None
        assert f["peak"] == pytest.approx(10.60)                      # the default day's high after the fill
        assert _roundtrip(f) == f                                     # plain JSON: no numpy scalar, no NaN, no inf

    def test_a_plus_2r_touch_before_the_stop_is_a_day0_third_and_the_stop_moves_to_cost(self):
        rows = [(m, 10.30, 10.32, 10.25, 10.30) for m in range(390)]
        rows[20] = (20, 10.30, 10.72, 10.28, 10.70)                   # +2R = 10.70
        rows[40] = (40, 10.50, 10.52, 10.29, 10.40)                   # then under the fill: stopped at COST, not at 10.10
        f = ppx.day0_facts(_mb(rows), fill=XP_FILL, stop=XP_STOP, fill_minute=7)
        assert f["partial_price"] == pytest.approx(10.70) and f["partial_minute"] == 20
        assert f["stopped"] is True and f["exit_price"] == pytest.approx(10.30) and f["stop_in_force"] == pytest.approx(10.30)

    def test_a_day0_stop_out_with_no_third(self):
        rows = [(m, 10.30, 10.32, 10.25, 10.30) for m in range(390)]
        rows[30] = (30, 10.25, 10.26, 10.05, 10.10)
        f = ppx.day0_facts(_mb(rows), fill=XP_FILL, stop=XP_STOP, fill_minute=7)
        assert f["stopped"] is True and f["partial_price"] is None and f["exit_price"] == pytest.approx(XP_STOP)
        bars, e = _xp_bars(XP_PROFIT_TAIL)
        fwd, _ = cb.forward_window(bars, np.arange(len(bars)), e, rn.HORIZON)
        got = ppx.walk_pp_arms({"fill": XP_FILL, "stop": XP_STOP}, f, closes_before=bars.c[:e + 1], fwd=fwd, adr20=0.10)
        assert {r["status"] for r in got.values()} == {"stopped_day0"} and got["pp"]["sessions_held"] == 0

    def test_no_minute_after_the_fill_leaves_a_none_peak_that_means_nothing_was_reached(self):
        rows = [(m, 10.30, 10.31, 10.29, 10.30) for m in range(8)]
        f = ppx.day0_facts(_mb(rows), fill=XP_FILL, stop=XP_STOP, fill_minute=7)
        assert f["peak"] is None and f["stopped"] is False and _roundtrip(f) == f
        bars, e = _xp_bars(XP_PROFIT_TAIL)
        fwd, _ = cb.forward_window(bars, np.arange(len(bars)), e, rn.HORIZON)
        got = ppx.walk_pp_arms({"fill": XP_FILL, "stop": XP_STOP}, f, closes_before=bars.c[:e + 1], fwd=fwd, adr20=0.10)
        want = rn.exitpb_walk(fill=XP_FILL, stop=XP_STOP, closes_before=bars.c[:e + 1], fwd=fwd, arm=rn.EXITPB_ARMS["pp"], adr20=0.10,
                              day0_partial_px=None, day0_peak=float("-inf"))
        _same(want, got["pp"])

    def test_the_close_variant_has_no_day0(self):
        f = ppx.no_day0_facts()
        assert f["stopped"] is False and f["partial_price"] is None and f["peak"] is None and _roundtrip(f) == f

    def test_a_record_that_is_not_the_facts_is_refused_not_guessed(self):
        bars, e = _xp_bars(XP_PROFIT_TAIL)
        fwd, _ = cb.forward_window(bars, np.arange(len(bars)), e, rn.HORIZON)
        for bad in ({}, {"v": 2, "stopped": False}, None):
            with pytest.raises(ValueError):
                ppx.walk_pp_arms({"fill": XP_FILL, "stop": XP_STOP}, bad, closes_before=bars.c[:e + 1], fwd=fwd, adr20=0.10)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 3. the job
# ═══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def world(monkeypatch):
    return make_world(monkeypatch, sh)


def _pp_rows(store):
    return {k: v for k, v in store.exit.items() if k[1] in ppx.PP_ARMS}


class TestTheJob:
    def test_every_filled_entry_gets_a_pp_and_an_A_row_the_night_it_is_recorded(self, world):
        m, store, _ = world
        run(WATCH_NIGHT)
        out = run(BREAK_DAY)
        filled = [r for r in store.entry.values() if r["status"] == "filled"]
        assert len(filled) == 19
        assert len(_pp_rows(store)) == 19 * 2 == out["pp_exit_rows"]
        assert {a for (_e, a) in _pp_rows(store)} == {"A", "pp"}
        assert len(store.exit_registered()) == 19 * len(cb.ARMS) == out["exit_rows"]       # the fifteen: as before
        assert out["pp_day0_recorded"] == 19 and out["pp_day0_missing"] == 0 and out["pp_exit_errors"] == 0
        assert out["pp_entries_open"] == 19 and out["pp_entries_stale"] == 0

    def test_only_a_filled_entry_carries_facts_and_the_close_variant_has_none_to_walk(self, world):
        _, store, _ = world
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        for r in store.entry.values():
            if r["status"] != "filled":
                assert r["day0_pp"] is None
            elif r["entry_variant"] == "close":
                assert r["day0_pp"] == ppx.no_day0_facts()
            else:
                assert r["day0_pp"]["v"] == 1 and r["day0_pp"]["stopped"] == (r["day0_pp"]["exit_price"] is not None)
        assert {r["entry_variant"] for r in store.entry.values() if r["status"] == "filled"} >= {"close", "orh5"}

    def test_every_pp_and_A_row_equals_the_registered_walk_fed_the_real_minutes(self, world):
        m, store, coll = world
        for d in m.cal[m.cal.index(WATCH_NIGHT):]:
            run(d)
        bars = _mrna_bars(m)
        r = {x[0]: x for x in m.bars["MRNA"]}[BREAK_DAY]
        by_id = {x["id"]: x for x in store.entry.values()}
        n_checked, variants = 0, set()
        for (eid, arm), x in _pp_rows(store).items():
            ent = by_id[eid]
            e = bars.dates.index(ent["break_date"])
            fwd, _cut = cb.forward_window(bars, np.arange(len(bars)), e, rn.HORIZON)
            if ent["entry_variant"] == "close":                       # no minute after a close fill: day 0 is empty
                want = rn.exitpb_walk(fill=ent["fill"], stop=ent["stop"], closes_before=bars.c[:e + 1], fwd=fwd,
                                      arm=rn.EXITPB_ARMS[arm], adr20=ent["adr20"], day0_partial_px=None, day0_peak=float("-inf"))
            else:
                # the minutes the entry step saw, rebuilt exactly as it built them
                mb, _state = sh.minute_bars_from_alpaca(coll.minutes_for[("MRNA", ent["break_date"])], ent["break_date"])
                want = rn.exitpb_walk_arms({"fill": ent["fill"], "stop": ent["stop"], "fill_minute": ent["fill_minute"]},
                                           closes_before=bars.c[:e + 1], fwd=fwd, adr20=ent["adr20"], minutes=mb,
                                           arms={arm: rn.EXITPB_ARMS[arm]})[arm]
            assert x["status"] == want["status"], (ent["k"], ent["entry_variant"], arm)
            assert x["realized_r"] == pytest.approx(want["realized_r"], abs=1e-12)
            assert x["pnl_adr"] == pytest.approx(want["pnl_adr"], abs=1e-12)
            assert x["sessions_held"] == want["sessions_held"]
            assert [tuple(ev) for ev in x["events"]] == [tuple(ev) for ev in sh._json_safe(want["events"])]
            assert x["mature"] == rn.is_mature(want["status"], x["n_fwd"])
            n_checked += 1
            variants.add(ent["entry_variant"])
        assert n_checked == len([e for e in store.entry.values() if e["status"] == "filled"]) * 2 and n_checked >= 38
        assert "close" in variants and len(variants) > 1

    def test_the_exit_step_fetches_no_minute(self, world):
        """Day 0 is read from the facts stored at entry time: after the break day's own look-back no night asks Alpaca for a
        minute of it again, yet the pp / A rows keep accruing."""
        m, store, coll = world
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        n_calls = len(coll.minute_calls)
        before = {k: v["n_fwd"] for k, v in _pp_rows(store).items()}
        for d in m.cal[m.cal.index(BREAK_DAY) + 1:m.cal.index(BREAK_DAY) + 8]:
            run(d)
        assert all(day > BREAK_DAY for day, _t in coll.minute_calls[n_calls:])
        assert any(v["n_fwd"] > before[k] for k, v in _pp_rows(store).items() if k in before)

    def test_a_mature_row_is_final_and_a_second_run_of_the_same_night_changes_nothing(self, world):
        m, store, _ = world
        for d in m.cal[m.cal.index(WATCH_NIGHT):m.cal.index(BREAK_DAY) + 8]:
            run(d)
        frozen = {k: dict(v) for k, v in _pp_rows(store).items() if v["mature"]}
        assert frozen and any(not v["mature"] for v in _pp_rows(store).values())
        night = m.cal[m.cal.index(BREAK_DAY) + 8]
        run(night)
        snap = {k: dict(v) for k, v in store.exit.items()}
        run(night)                                                    # a restart on the same night
        assert {k: dict(v) for k, v in store.exit.items()} == snap
        for k, v in frozen.items():
            assert store.exit[k] == v

    def test_the_pp_arms_accrue_every_night_from_stored_bars(self, world):
        m, store, _ = world
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        first = {k: v["n_fwd"] for k, v in _pp_rows(store).items()}
        for d in m.cal[m.cal.index(BREAK_DAY) + 1:m.cal.index(BREAK_DAY) + 6]:
            out = run(d)
        later = {k: v["n_fwd"] for k, v in _pp_rows(store).items() if k in first}
        assert all(later[k] >= first[k] for k in first) and any(later[k] > first[k] for k in first)
        assert out["pp_entries_open"] > 0

    def test_a_pre_change_fill_has_no_facts_and_is_not_walked_while_its_fifteen_still_are(self, world):
        m, store, _ = world
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        # make half the fills look like they pre-date the change: no facts, and drop their pp rows
        old_ids = {r["id"] for r in store.entry.values() if r["status"] == "filled"
                   and r["entry_variant"] in ("orh5", "orh60")}
        assert old_ids
        for r in store.entry.values():
            if r["id"] in old_ids:
                r["day0_pp"] = None
        store.exit = {k: v for k, v in store.exit.items() if not (k[0] in old_ids and k[1] in ppx.PP_ARMS)}
        out = run(m.cal[m.cal.index(BREAK_DAY) + 1])
        assert not [k for k in store.exit if k[0] in old_ids and k[1] in ppx.PP_ARMS]          # never written
        with_facts = {r["id"] for r in store.entry.values() if r["status"] == "filled" and r["day0_pp"] is not None}
        assert 0 < out["pp_entries_open"] <= len(with_facts)          # a day-0 stop-out's two arms were final already
        assert {eid for (eid, a) in store.exit if a in ppx.PP_ARMS} == with_facts
        assert {a for (e, a) in store.exit if e in old_ids} == set(cb.ARMS)                  # the fifteen walked as ever

    def test_a_failed_facts_computation_loses_no_entry_row_and_walks_no_pp(self, world, monkeypatch):
        m, store, _ = world
        def boom(*a, **k):
            raise RuntimeError("facts down")
        monkeypatch.setattr(ppx, "day0_facts", boom)
        run(WATCH_NIGHT)
        out = run(BREAK_DAY)
        filled = [r for r in store.entry.values() if r["status"] == "filled"]
        minute_filled = [r for r in filled if r["entry_variant"] != "close"]
        assert len(filled) == 19 and out["pp_day0_missing"] == len(minute_filled) and out["pp_day0_recorded"] == 19 - len(minute_filled)
        assert all(r["day0_pp"] is None for r in minute_filled)
        assert {a for (e, a) in _pp_rows(store)} <= {"A", "pp"} and len(_pp_rows(store)) == 2 * (19 - len(minute_filled))
        assert len(store.exit_registered()) == 19 * len(cb.ARMS) and out["step_errors"] == []

    def test_a_crash_in_the_pp_walk_is_counted_per_entry_and_never_touches_the_fifteen(self, world, monkeypatch):
        m, store, _ = world
        real = ppx.walk_pp_arms
        def boom(*a, **k):
            raise RuntimeError("pp walk down")
        monkeypatch.setattr(ppx, "walk_pp_arms", boom)
        run(WATCH_NIGHT)
        out = run(BREAK_DAY)
        n_filled = sum(1 for v in store.entry.values() if v["status"] == "filled")
        assert out["pp_exit_errors"] == n_filled == 19                # one counted crash per filled entry, nothing else
        assert _pp_rows(store) == {} and len(store.exit_registered()) == 19 * len(cb.ARMS) == out["exit_rows"]
        monkeypatch.setattr(ppx, "walk_pp_arms", real)
        out = run(m.cal[m.cal.index(BREAK_DAY) + 1])                   # the next night recomputes in full
        assert out["pp_exit_errors"] == 0 and len(_pp_rows(store)) == 19 * 2

    def test_the_audit_row_carries_the_pp_counters(self, world):
        m, store, _ = world
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        ev = [e for e in store.audit if e[0] == sh.AUDIT_RUN_EVENT][-1]
        detail = json.loads(ev[2])
        for k in ("pp_day0_recorded", "pp_day0_missing", "pp_entries_open", "pp_entries_stale", "pp_split_deferred",
                  "pp_exit_rows", "pp_exit_mature", "pp_exit_status", "pp_exit_errors"):
            assert k in detail
        assert "pp/A 38 exit row(s)" in ev[1]

    # ── splits: the same reading as the registered arms' ───────────────────────────────────
    def test_a_real_split_after_the_break_day_makes_the_open_pp_arms_unbookable_and_final(self, world):
        from tests.test_cb_shadow import _real_split
        m, store, _ = world
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        store.splits.append(_real_split("recorded", D(2026, 9, 21), 1, 4))
        out = run(D(2026, 9, 21))
        by_id = {r["id"]: r for r in store.entry.values()}
        for (eid, arm), x in _pp_rows(store).items():
            d0 = by_id[eid]["day0_pp"]
            assert x["status"] == ("stopped_day0" if d0["stopped"] else "unbookable"), (eid, arm)
        un = [x for x in _pp_rows(store).values() if x["status"] == "unbookable"]
        assert un and all(x["mature"] and x["realized_r"] is None and "after_entry" in x["reason"] for x in un)
        assert out["pp_exit_status"]["unbookable"] == len(un)

    def test_a_phantom_is_ignored_and_an_unapplied_split_defers_then_decides(self, world):
        from tests.test_cb_shadow import _phantom_split, _real_split
        m, store, _ = world
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        store.splits.append(_phantom_split(D(2026, 9, 21)))
        out = run(D(2026, 9, 21))
        assert out["pp_exit_status"].get("unbookable", 0) == 0 and out["pp_exit_rows"] > 0
        store.splits[:] = [_real_split("recorded", D(2026, 9, 22), 1, 4, adjustment_applied=False,
                                       adjustment_outcome=None, applied_factor=None)]
        before = {k: dict(v) for k, v in store.exit.items()}
        out = run(D(2026, 9, 22))
        assert out["pp_split_deferred"] > 0 and out["pp_exit_rows"] == 0 and store.exit == before
        store.splits[0].update(adjustment_applied=True, adjustment_outcome="applied", applied_factor=0.25)
        out = run(D(2026, 9, 23))
        assert out["pp_split_deferred"] == 0 and out["pp_exit_status"]["unbookable"] > 0


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 4. the fifteen are untouched
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _r9(x):
    if isinstance(x, float):
        return round(x, 9)
    if isinstance(x, (list, tuple)):
        return [_r9(v) for v in x]
    if isinstance(x, dict):
        return {str(k): _r9(v) for k, v in sorted(x.items())}
    if isinstance(x, (dt.date, dt.datetime)):
        return x.isoformat()
    return x


def _digest(rows) -> str:
    return hashlib.sha256(json.dumps(_r9(rows), sort_keys=True, default=str).encode()).hexdigest()


# NB the fixture includes the real MRNA bars (`tests/fixtures/htf_labelled_bars.psv`): a change to that fixture, to `build_market`
# or to `synth_minutes` moves the digest and needs a re-pin FROM THE CODE AS IT STANDS (re-derive, do not paste the new value).
# Taken from the code as it stood BEFORE #705 (c) (git HEAD d3e8ed20), run on exactly these fixtures: the MRNA + MRNB market
# on its real calendar through 24 future sessions (MRNB with a morning dip), every night from the watch night. The registered
# rows are what the table held; the entry rows are compared on the columns the table had.
GOLDEN_ENTRY_SHA = "935a26b251f60e42e25a2b668e4919cab8aaed05161f2ffec6b68191b86e2c36"
GOLDEN_EXIT_SHA = "2e777de521fd9cde1064c2e032fde764797405390ac17cbc5fb8ae495013bfc0"
GOLDEN_COUNTS = {"entry": 250, "exit": 960}


def _fixture_run(monkeypatch):
    market = build_market(future=24, clone_mrna=True)
    r = {x[0]: x for x in market.bars["MRNA"]}[BREAK_DAY]
    r2 = {x[0]: x for x in market.bars["MRNB"]}[BREAK_DAY]
    minutes = {("MRNA", BREAK_DAY): synth_minutes(BREAK_DAY, *r[1:5]),
               ("MRNB", BREAK_DAY): synth_minutes(BREAK_DAY, *r2[1:5], dip_after=45)}
    store = FakeStore(market)
    store.install(monkeypatch, sh)
    FakeCollector(market, minutes_for=minutes, polygon=_polygon).install(monkeypatch)
    for d in market.cal[market.cal.index(WATCH_NIGHT):market.cal.index(BREAK_DAY) + 12]:
        run(d)
    return store


def _registered_view(store):
    entry_cols = [c for c in db.CB_ENTRY_COLS if c != "day0_pp"]
    by_id = {v["id"]: k for k, v in store.entry.items()}
    entries = sorted([{c: v[c] for c in entry_cols} for v in store.entry.values()],
                     key=lambda r: (r["ticker"], str(r["pole_date"]), r["k"], r["entry_variant"], str(r["break_date"])))
    exits = sorted([dict(x, key=list(map(str, by_id[eid]))) for (eid, arm), x in store.exit.items() if arm in cb.ARMS],
                   key=lambda r: (r["key"], r["arm"]))
    for x in exits:
        x.pop("entry_id")
    return entries, exits


class TestTheFifteenAreUntouched:
    def test_the_registered_rows_and_the_entry_rows_equal_the_pre_change_code_on_the_same_fixtures(self, monkeypatch):
        store = _fixture_run(monkeypatch)
        entries, exits = _registered_view(store)
        assert (len(entries), len(exits)) == (GOLDEN_COUNTS["entry"], GOLDEN_COUNTS["exit"])
        assert _digest(entries) == GOLDEN_ENTRY_SHA, "an entry row's EXISTING columns moved"
        assert _digest(exits) == GOLDEN_EXIT_SHA, "a registered arm's exit row moved"

    def test_the_registered_work_list_counts_only_the_registered_arms(self, world):
        """A `pp` / `A` row maturing early must not drop an entry (and its still-open `stop_only` control) from the fifteen's
        walk: the SQL joins `x.arm NOT IN ('A', 'pp')`, the in-memory store mirrors it, and this is the observable."""
        m, store, _ = world
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        pp_mature = {k for k, v in _pp_rows(store).items() if v["mature"]}
        assert pp_mature, "the fixture should mature a pp arm on the break day (a day-0 stop-out)"
        eid = next(iter(pp_mature))[0]
        # force the entry to look 13-of-15 registered-mature + both pp arms mature: it must STILL be open for the fifteen
        keep = sorted(cb.ARMS)[:13]
        for arm in cb.ARMS:
            row = dict(store.exit_registered().get((eid, arm)) or {}, mature=arm in keep)
            if row:
                store.exit[(eid, arm)] = row
        for arm in ppx.PP_ARMS:
            store.exit[(eid, arm)] = dict(store.exit[(eid, arm)], mature=True)
        assert eid in {e["id"] for e in asyncio.run(store.cb_get_open_entries(len(cb.ARMS), D(2000, 1, 1)))}
        assert eid not in {e["id"] for e in asyncio.run(store.cb_get_pp_open_entries(list(ppx.PP_ARMS), D(2000, 1, 1)))}
