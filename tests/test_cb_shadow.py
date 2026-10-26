"""#702 P6 - the Consolidation Breakout forward SHADOW recorder (`consolidation_breakout_shadow.py`).

What is pinned, and against what:

  1. PARITY with the offline runner (`scripts/probes/_cb_backtest/runner.py`): the plumbing both use (test symbols,
     the contiguity test, the breakout test, gap fields, the maturity label, the forward-window cut, the
     cross-section, the one-trade-per-base stamping, `walk_arms`) is ONE definition in `consolidation_breakout`
     (its own tests pin it); what is checked here is the part that is the shadow's alone - the stamping run
     INCREMENTALLY (night by night, as the job runs) against the BATCH over the whole set - and the watch build
     against the runner's `scan_ticker` on real bars.
  2. The JOB end to end on an in-memory store (`tests/cb_shadow_support.FakeStore`: the same write guards the SQL
     has) with MRNA - the module's canary - on its REAL calendar: a watch row on 2026-09-16, entries on 2026-09-17,
     exits walked on later nights, each against an ORACLE built straight from the module's public functions.
  3. Failure modes: a minute outage defers (never writes a false abstain), a split abstains / makes a walk
     unbookable, no Telegram on a normal night, a crash propagates after the audit row, the time budget fails open,
     the SIC cap holds.
  4. The census: registered at 17:48 mon-fri, intelligence-owned, not loaded by execution, no broker import.

`tests/test_cb_shadow_pg.py` runs the SQL for real (skipped unless a throwaway Postgres is supplied).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import random
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pytest

from agents.market_intelligence import consolidation_breakout as cb
from agents.market_intelligence import consolidation_breakout_shadow as sh
from scripts.probes._cb_backtest import runner as rn
from tests.cb_shadow_support import (BREAK_DAY, WATCH_NIGHT, FakeCollector, FakeStore, build_market,
                                     synth_minutes)

REPO = Path(__file__).resolve().parent.parent
D = dt.date


def run(day):
    return asyncio.run(sh.run_consolidation_breakout_shadow(day))


def _polygon(path):
    return {"results": {"sic_code": "2836", "sic_description": "biological products", "type": "CS"}}


def _real_split(style, exec_date, split_from, split_to, **over):
    """A REAL split row for MRNA as `mi_splits` holds it. 'recorded' = what the ingest writes since #704 (outcome
    'applied' + the factor it restated by); 'legacy' = a row written before the column existed (a bare boolean)."""
    row = {"ticker": "MRNA", "execution_date": exec_date, "split_from": split_from, "split_to": split_to,
           "adjustment_applied": True, "adjustment_outcome": None, "applied_factor": None}
    if style == "recorded":
        row.update(adjustment_outcome="applied", applied_factor=split_from / split_to)
    return {**row, **over}


def _nodata_split(exec_date, split_from=1, split_to=4):
    """The ingest got no bars to apply ('skipped_no_data') - Polygon had none, OR the fetch FAILED (every error is
    swallowed to []): either way no bar was written, which is NOT "no bar moved" for a real split."""
    return _real_split("recorded", exec_date, split_from, split_to, adjustment_outcome="skipped_no_data",
                       applied_factor=None)


def _phantom_split(exec_date, split_from=1, split_to=4):
    """Polygon reported a split that never happened: the ingest recorded 'phantom' and wrote no bar."""
    return _real_split("recorded", exec_date, split_from, split_to, adjustment_outcome="phantom", applied_factor=None)


@pytest.fixture
def world(monkeypatch):
    m = build_market(future=24)
    store = FakeStore(m)
    store.install(monkeypatch, sh)
    r = {x[0]: x for x in m.bars["MRNA"]}[BREAK_DAY]
    mins = synth_minutes(BREAK_DAY, *r[1:5])
    coll = FakeCollector(m, minutes_for={("MRNA", BREAK_DAY): mins}, polygon=_polygon)
    coll.install(monkeypatch)
    return m, store, coll


def _mrna_bars(m):
    rows = m.bars["MRNA"]
    return cb.daily_bars_from_arrays([r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows],
                                     [r[3] for r in rows], [r[4] for r in rows], [r[5] for r in rows])


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 1. parity with the runner
# ═══════════════════════════════════════════════════════════════════════════════════════════════
class TestRunnerParity:
    # ── one trade per base ────────────────────────────────────────────────────────────────
    @staticmethod
    def _cand(ticker, pole_ci, k, e_ci, cal_iso, rng):
        c = {"ticker": ticker, "pole_ci": pole_ci, "pole_date": cal_iso[pole_ci], "K": k, "E": cal_iso[e_ci]}
        for name in sh.CELL_NAMES:
            c[name] = rng.random() < 0.4
        return c

    def _scenario(self, seed):
        rng = random.Random(seed)
        cal_iso = [(D(2026, 1, 1) + dt.timedelta(days=i)).isoformat() for i in range(120)]
        cands = []
        for ticker in ("AAA", "BBB", "CCC"):
            for pole_ci in rng.sample(range(10, 60), 4):
                for k in sh.KS:
                    for e_ci in sorted(rng.sample(range(pole_ci + 10, 110), rng.randint(0, 4))):
                        cands.append(self._cand(ticker, pole_ci, k, e_ci, cal_iso, rng))
        return cal_iso, cands

    @pytest.mark.parametrize("seed", range(6))
    def test_night_by_night_stamping_equals_the_batch_when_no_later_pole_bridges(self, seed):
        """The job stamps each breakout day against the candidates it has already written; the runner stamps the
        whole set at once. They agree whenever the chain key's poles are all known by the time of the candidate
        (a LATER pole falling between two earlier ones can merge two bases after the fact - the one documented
        way a forward row can differ from a batch row; the scenario's poles are known up front)."""
        cal_iso, cands = self._scenario(seed)
        poles = [(c["ticker"], c["pole_ci"], c["pole_date"]) for c in cands]
        batch = [dict(c) for c in cands]
        cb.stamp_retrigger(batch)
        cb.stamp_base_chain(batch, cb.chain_bases(set(poles)))
        want = {(c["ticker"], c["pole_date"], c["K"], c["E"]): c for c in batch}

        keys = ("retrigger", "retrigger_chain", "base_id") + tuple("first_" + n for n in sh.CELL_NAMES) \
            + tuple("first_chain_" + n for n in sh.CELL_NAMES)
        got = {}
        for e in sorted({c["E"] for c in cands}):
            new = [dict(c) for c in cands if c["E"] == e]
            history = [dict(c) for c in cands if c["E"] < e]
            sh.stamp_forward(history, new, poles)
            for c in new:
                got[(c["ticker"], c["pole_date"], c["K"], c["E"])] = c
        assert got.keys() == want.keys()
        for key in want:
            assert {k: got[key][k] for k in keys} == {k: want[key][k] for k in keys}, key

    def test_a_later_bridging_pole_is_the_documented_difference(self):
        """Poles at sessions 10 and 14 are two bases; a pole at 12 (seen only AFTER the second candidate) bridges
        them. The batch merges all three; the night-by-night job, which cannot see the future, does not."""
        cal_iso = [(D(2026, 1, 1) + dt.timedelta(days=i)).isoformat() for i in range(60)]
        def cand(pole_ci, e_ci):
            c = {"ticker": "AAA", "pole_ci": pole_ci, "pole_date": cal_iso[pole_ci], "K": "k5", "E": cal_iso[e_ci]}
            c.update({n: False for n in sh.CELL_NAMES})
            return c
        c1, c2 = cand(10, 30), cand(14, 31)
        poles_known_at_c2 = [("AAA", 10, cal_iso[10]), ("AAA", 14, cal_iso[14])]
        all_poles = poles_known_at_c2 + [("AAA", 12, cal_iso[12])]
        batch = [dict(c1), dict(c2)]
        cb.stamp_retrigger(batch)
        cb.stamp_base_chain(batch, cb.chain_bases(set(all_poles)))
        new = [dict(c2)]
        sh.stamp_forward([dict(c1)], new, poles_known_at_c2)
        assert batch[1]["retrigger_chain"] == 1 and new[0]["retrigger_chain"] == 0       # the known limit
        assert batch[1]["retrigger"] == new[0]["retrigger"] == 0                           # the spec key is unaffected


class TestWatchParity:
    def _fixture_series(self):
        rows = {}
        for ln in (REPO / "tests" / "fixtures" / "htf_labelled_bars.psv").read_text().splitlines():
            f = ln.split("|")
            rows.setdefault(f[0], []).append(f)
        out = {}
        for t, rs in rows.items():
            cols = [[float(r[k]) for r in rs] for k in (2, 3, 4, 5, 6)]
            out[t] = cb.daily_bars_from_arrays([D.fromisoformat(r[1]) for r in rs], *cols)
        return out

    @staticmethod
    def _norm(feat):
        return {k: v for k, v in feat.items() if k != "i" and not k.endswith("_idx")}

    def test_a_150_bar_slice_gives_the_same_features_as_the_whole_history(self):
        """The shadow loads 150 sessions per name, the runner scans each ticker's whole history. Every feature
        the module reads sits inside the last 130 bars, so the two must agree wherever a night passes C0 - and
        on the failing gate where it does not."""
        seen_pass = 0
        for t, bars in self._fixture_series().items():
            for i in range(160, len(bars)):
                whole = cb.explain_watch(bars, i)
                part = cb.explain_watch(bars.slice(i - 149, i + 1), 149)
                assert whole[1] == part[1], (t, i)
                if whole[0] is not None:
                    seen_pass += 1
                    assert self._norm(whole[0]) == self._norm(part[0]), (t, i)
        assert seen_pass >= 20            # the comparison saw real passing nights, not an empty loop

    def test_scan_universe_equals_the_runners_scan_ticker_on_the_last_night(self):
        compared = 0
        for t, full in self._fixture_series().items():
            for j in range(max(150, len(full) - 45), len(full)):               # 45 consecutive watch nights
                bars = full.slice(0, j + 1)                                    # the runner sees the whole history
                cidx = np.arange(len(bars), dtype=np.int64)
                res = sh.scan_universe({t: (full.slice(j - 149, j + 1), cidx[-150:])}, today_ci=j,
                                       mi_types={t: "CS"}, sic_types={}, unapplied=set())
                ran = rn.scan_ticker(t, bars, cidx, [], "CS", j)               # d0 = this night only
                assert len(res["members"]) == len(ran["uni_ci"]) == (1 if ran["uni_ci"].size else 0), (t, j)
                if not res["members"]:
                    continue
                m = res["members"][0]
                assert (m["r21"], m["r63"], m["r126"]) == tuple(None if x != x else x for x in ran["rs"][0]), (t, j)
                if ran["watch"]:
                    drop = {"ticker", "ci", "pole_ci", "i"}
                    want = {k: v for k, v in ran["watch"][0].items() if k not in drop and not k.endswith("_idx")}
                    assert self._norm(m["feat"]) == want, (t, j)
                    compared += 1
                else:
                    assert m["feat"] is None, (t, j)
        assert compared >= 5                                                   # real passing nights were compared


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 2. the job end to end
# ═══════════════════════════════════════════════════════════════════════════════════════════════
class TestWatchNight:
    def test_mrna_is_the_watch_row_with_the_canary_pivots(self, world):
        m, store, _ = world
        out = run(WATCH_NIGHT)
        assert out["watch_n"] == 1 and out["universe_n"] == 21
        row = store.watch[("MRNA", WATCH_NIGHT)]
        assert row["pole_date"] == D(2026, 8, 19) and row["pole_high"] == 176.66
        assert row["pivot_k5"] == 149.7344 and row["pivot_k5_date"] == D(2026, 9, 11)
        assert row["pivot_k10"] == 156.4151 and row["pivot_k10_date"] == D(2026, 9, 2)
        assert row["pivot_full"] == 161.37 and row["pivot_full_date"] == D(2026, 8, 25)
        assert row["pivot_tl"] is not None and row["pivot_tl_date"] is not None
        assert set(row["cells"]) == set(sh.KS)
        for k in sh.KS:
            assert row["cells"][k]["C0"] is True and "C1_s5" in row["cells"][k]
        assert row["universe_n"] == 21

    def test_stored_features_carry_no_slice_relative_positions(self, world):
        _, store, _ = world
        run(WATCH_NIGHT)
        feats = store.watch[("MRNA", WATCH_NIGHT)]["features"]
        assert "i" not in feats and not any(k.endswith("_idx") for k in feats)
        assert feats["pole_date"] == "2026-08-19" and feats["pole_hi_over_oc"] > 0

    def test_the_rs_denominator_is_the_whole_universe_not_the_watch_set(self, world):
        _, store, _ = world
        out = run(WATCH_NIGHT)
        # 22 tickers loaded: SPY / QQQ (ETFs - out of the universe), MRNA + 20 fillers - 21 members, 1 watch row
        assert out["gate_funnel"]["universe_fail"] == 2 and out["universe_n"] == 21 and out["watch_n"] == 1
        row = store.watch[("MRNA", WATCH_NIGHT)]
        assert row["rs_best"] is not None and 0.0 <= row["rs_best"] <= 100.0
        # percentile among 21 names: positions are multiples of 100/20 = 5.0
        assert (row["rs_best"] * 20 / 100) == pytest.approx(round(row["rs_best"] * 20 / 100), abs=0.2)

    def test_phases_come_from_spy_and_qqq_joined_by_date(self, world):
        m, store, _ = world
        out = run(WATCH_NIGHT)
        assert out["phase_data_gap"] is False
        i = m.cal.index(WATCH_NIGHT)
        qqq = cb.daily_bars_from_arrays(m.cal[:i + 1], *[[r[k] for r in m.bars["QQQ"][:i + 1]] for k in range(1, 6)])
        spy = cb.daily_bars_from_arrays(m.cal[:i + 1], *[[r[k] for r in m.bars["SPY"][:i + 1]] for k in range(1, 6)])
        row = store.watch[("MRNA", WATCH_NIGHT)]
        assert row["phase_qqq_10_20"] == cb.phase_qqq_10_20(qqq, i, 1)
        assert row["phase_qqq_10_20_s5"] == cb.phase_qqq_10_20(qqq, i, 5)
        assert row["phase_spy_qqq_50"] == cb.phase_spy_qqq_50(spy, qqq, i, i)

    def test_a_phase_series_with_a_missing_session_reads_false_and_says_so(self):
        m = build_market(future=0)
        i = len(m.cal) - 1
        mk = lambda t, drop: cb.daily_bars_from_arrays(
            [d for k, d in enumerate(m.cal) if k != drop], *[[r[c] for k, r in enumerate(m.bars[t]) if k != drop]
                                                              for c in range(1, 6)])
        ok = sh.compute_phases(mk("SPY", i), mk("QQQ", i), m.cal[-56:])
        assert ok["gap"] is True                      # the series are missing the last session: not the calendar's tail
        full = cb.daily_bars_from_arrays(m.cal, *[[r[c] for r in m.bars["QQQ"]] for c in range(1, 6)])
        fine = sh.compute_phases(full, full, m.cal[-56:])
        assert fine["gap"] is False and i == len(full) - 1

    def test_no_row_when_there_is_no_spy_bar_for_today(self, world):
        _, store, _ = world
        out = run(D(2026, 9, 19))                      # a Saturday
        assert out["skipped"] == "no_spy_bar_for_today" and not store.watch and not store.entry
        assert any("skipped" in a[1] for a in store.audit if a[0] == sh.AUDIT_RUN_EVENT)


class TestBreakoutDay:
    def _two_nights(self, world):
        m, store, coll = world
        run(WATCH_NIGHT)
        out = run(BREAK_DAY)
        return m, store, coll, out

    def test_every_k_and_variant_is_a_row_and_equals_the_module(self, world):
        m, store, coll, out = self._two_nights(world)
        w = store.watch[("MRNA", WATCH_NIGHT)]
        mr = {r[0]: r for r in m.bars["MRNA"]}[BREAK_DAY]
        mb, state = sh.minute_bars_from_alpaca(coll.minutes_for[("MRNA", BREAK_DAY)], BREAK_DAY)
        assert state == "ok"
        assert len(store.entry) == 20 == out["entry_rows"]            # 4 K x (4 minute variants + the close)
        for k in sh.KS:
            ev = cb.entry_variants(mb, pivot=w[f"pivot_{k}"], adr20=w["adr20"], day_high=mr[2], day_low=mr[3])
            ev["close"] = cb.close_entry(mr[4], mr[3], w[f"pivot_{k}"], w["adr20"])
            for v in sh.VARIANTS:
                row = store.entry[("MRNA", D(2026, 8, 19), k, v, BREAK_DAY)]
                want = ev[v]
                assert row["status"] == want["status"] and row["reason"] == want["reason"], (k, v)
                for col in ("fill", "stop", "fill_minute", "width_pct", "level"):
                    assert row[col] == want[col], (k, v, col)
                if want["status"] == "filled":
                    d0 = want["day0"]
                    assert (row["day0_stopped"], row["day0_exit_price"], row["day0_exit_minute"]) == \
                        (d0["stopped"], d0["exit_price"], d0["exit_minute"])
                assert row["watch_date"] == WATCH_NIGHT and row["break_date"] == BREAK_DAY
                assert row["gap_pct"] == pytest.approx(mr[1] / w[f"pivot_{k}"] - 1.0)

    def test_minutes_that_disagree_with_the_daily_bar_abstain_by_name_and_are_not_retried(self, monkeypatch):
        m = build_market(future=3)
        store = FakeStore(m)
        store.install(monkeypatch, sh)
        r = {x[0]: x for x in m.bars["MRNA"]}[BREAK_DAY]
        # the minute day's high (157.0) sits 3% under the daily high (161.96): the feeds disagree, not a breakout
        bad = synth_minutes(BREAK_DAY, 152.5, 157.0, 149.5, 156.0)
        coll = FakeCollector(m, minutes_for={("MRNA", BREAK_DAY): bad}, polygon=_polygon)
        coll.install(monkeypatch)
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        minute_rows = [x for x in store.entry.values() if x["entry_variant"] != "close"]
        assert len(minute_rows) == 16
        assert {(x["status"], x["reason"], x["minutes_state"]) for x in minute_rows} == \
            {("abstain", "minute_daily_mismatch", "ok")}
        assert not any(x["status"] == "filled" for x in minute_rows) and r[2] == 161.9599
        coll.minute_calls.clear()
        run(m.cal[m.cal.index(BREAK_DAY) + 1])                        # final: the next night does not fetch it again
        assert all(day != BREAK_DAY for day, _t in coll.minute_calls)

    def test_abstains_and_no_triggers_are_rows_with_a_named_reason(self, world):
        m, store, coll, out = self._two_nights(world)
        assert out["entry_status"].get("no_trigger", 0) >= 1          # MRNA closes (158.07) under the full-base 161.37 pivot
        no_trig = [r for r in store.entry.values() if r["status"] == "no_trigger"]
        assert no_trig and all(r["reason"] for r in no_trig)
        assert all(r["reason"] for r in store.entry.values() if r["status"] != "filled")

    def test_the_first_break_of_a_base_is_retrigger_zero_and_carries_its_cells(self, world):
        _, store, _, _ = self._two_nights(world)
        for r in store.entry.values():
            assert r["retrigger"] == 0 and r["retrigger_chain"] == 0 and r["base_id"] == "MRNA|2026-08-19"
            assert r["cells"] == store.watch[("MRNA", WATCH_NIGHT)]["cells"][r["k"]]
            assert set(r["first_cells"]) == set(sh.CELL_NAMES)
            assert r["first_cells"]["C0"] == 1                          # the first break where C0 held

    def test_minutes_are_recorded_with_their_feed(self, world, monkeypatch):
        monkeypatch.setenv("ALPACA_DATA_FEED", "sip")
        _, store, _, _ = self._two_nights(world)
        minute_rows = [r for r in store.entry.values() if r["entry_variant"] != "close"]
        assert {r["feed"] for r in minute_rows} == {"sip"} and {r["minutes_state"] for r in minute_rows} == {"ok"}
        assert {r["feed"] for r in store.entry.values() if r["entry_variant"] == "close"} == {None}

    def test_exit_rows_appear_the_first_night_for_every_filled_entry_and_arm(self, world):
        _, store, _, out = self._two_nights(world)
        filled = [r for r in store.entry.values() if r["status"] == "filled"]
        assert len(filled) == 19 and len(store.exit_registered()) == 19 * len(cb.ARMS) == 285 == out["exit_rows"]
        for r in store.exit_registered().values():
            assert r["status"] in ("degraded", "stopped_day0") and r["last_bar_date"] == BREAK_DAY


class TestExitsAgainstTheOracle:
    def test_every_arm_of_every_entry_equals_the_module_walked_on_the_full_bars(self, world):
        m, store, _ = world
        for d in m.cal[m.cal.index(WATCH_NIGHT):]:
            run(d)
        bars = _mrna_bars(m)
        by_id = {r["id"]: r for r in store.entry.values()}
        n_checked = 0
        for (eid, arm), x in store.exit_registered().items():
            ent = by_id[eid]
            e = bars.dates.index(ent["break_date"])                 # later nights' breakouts are entries too
            if ent["day0_stopped"]:
                want = cb.day0_result_to_outcome({"status": "filled", "fill": ent["fill"], "stop": ent["stop"],
                                                  "day0": {"stopped": True, "exit_price": ent["day0_exit_price"],
                                                           "exit_minute": ent["day0_exit_minute"]}}, ent["adr20"])
            else:
                want = cb.walk_exit(fill=ent["fill"], stop=ent["stop"], closes_before=bars.c[:e + 1],
                                    fwd=bars.slice(e + 1, e + 2 + cb.EXIT_HORIZON), arm=cb.ARMS[arm],
                                    adr20=ent["adr20"], horizon=cb.EXIT_HORIZON)
            assert x["status"] == want["status"], (ent["k"], ent["entry_variant"], arm)
            assert x["realized_r"] == pytest.approx(want["realized_r"], abs=1e-12)
            assert x["pnl_adr"] == pytest.approx(want["pnl_adr"], abs=1e-12)
            assert x["sessions_held"] == want["sessions_held"]
            assert x["mature"] == rn.is_mature(want["status"], len(bars.slice(e + 1, e + 2 + cb.EXIT_HORIZON)))
            n_checked += 1
        filled = [r for r in store.entry.values() if r["status"] == "filled"]
        assert n_checked == len(filled) * len(cb.ARMS) == len(store.exit_registered())
        assert len({r["break_date"] for r in filled}) > 1 and n_checked >= 19 * 15      # not only the first break day

    def test_a_day_zero_stop_out_is_minus_one_r_or_worse_on_every_arm_and_never_reaches_the_daily_walk(self, world):
        m, store, _ = world
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        stopped = [r for r in store.entry.values() if r["day0_stopped"]]
        assert stopped, "the synthetic path breaks the pivot-variant stop on day 0"
        for ent in stopped:
            rows = [x for (eid, _a), x in store.exit_registered().items() if eid == ent["id"]]
            assert len(rows) == 15 and {x["status"] for x in rows} == {"stopped_day0"}
            want_r = (ent["day0_exit_price"] - ent["fill"]) / (ent["fill"] - ent["stop"])   # -1R at the stop, worse on a gap
            assert want_r <= -1.0 + 1e-12
            for x in rows:
                assert x["sessions_held"] == 0 and x["mature"] and x["last_bar_date"] == BREAK_DAY
                assert x["realized_r"] == pytest.approx(want_r)

    def test_a_morning_low_broken_after_an_early_fill_is_a_day_zero_stop_for_the_early_variants_only(self, monkeypatch):
        m = build_market(future=3)
        store = FakeStore(m)
        store.install(monkeypatch, sh)
        r = {x[0]: x for x in m.bars["MRNA"]}[BREAK_DAY]
        mins = synth_minutes(BREAK_DAY, *r[1:5], dip_after=45)
        FakeCollector(m, minutes_for={("MRNA", BREAK_DAY): mins}, polygon=_polygon).install(monkeypatch)
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        by = {(k, v): store.entry[("MRNA", D(2026, 8, 19), k, v, BREAK_DAY)] for k in sh.KS for v in cb.ENTRY_VARIANTS}
        assert by[("k5", "orh5")]["status"] == "filled" and by[("k5", "orh5")]["day0_stopped"] is True
        assert by[("k5", "orh5")]["fill_minute"] < 45
        assert by[("k5", "orh60")]["status"] == "filled" and by[("k5", "orh60")]["day0_stopped"] is False
        eid = by[("k5", "orh5")]["id"]
        assert {x["status"] for (e, _a), x in store.exit_registered().items() if e == eid} == {"stopped_day0"}

    def test_a_mature_arm_is_not_walked_again_and_an_open_one_is(self, world):
        m, store, _ = world
        for d in m.cal[m.cal.index(WATCH_NIGHT):m.cal.index(BREAK_DAY) + 8]:
            run(d)
        frozen = {k: dict(v) for k, v in store.exit_registered().items() if v["mature"]}
        assert frozen and any(not v["mature"] for v in store.exit_registered().values())
        out = run(m.cal[m.cal.index(BREAK_DAY) + 8])
        for k, v in frozen.items():
            assert store.exit[k] == v                                   # untouched
        assert out["exit_entries_open"] > 0

    def test_only_the_arms_that_are_not_final_are_recomputed(self, world, monkeypatch):
        m, store, _ = world
        for d in m.cal[m.cal.index(WATCH_NIGHT):m.cal.index(BREAK_DAY) + 8]:
            run(d)
        n_arms = len(cb.ARMS)
        mature_before = defaultdict(set)                                    # entry id -> arms already final
        for (eid, arm), x in store.exit_registered().items():
            if x["mature"]:
                mature_before[eid].add(arm)
        open_ids = [v["id"] for v in store.entry.values()
                    if v["status"] == "filled" and len(mature_before[v["id"]]) < n_arms]
        assert open_ids and any(0 < len(mature_before[i]) < n_arms for i in open_ids)   # a PARTLY-final entry exists
        written, calls = [], []
        real_upsert, real = sh.cb_upsert_exit_rows, cb.walk_exit

        async def spy(rows):
            written.extend((r["entry_id"], r["arm"]) for r in rows if r["arm"] in cb.ARMS)   # the pp / A rows are #705 (c)'s
            return await real_upsert(rows)
        monkeypatch.setattr(sh, "cb_upsert_exit_rows", spy)
        monkeypatch.setattr(cb, "walk_exit", lambda **kw: calls.append(kw["arm"].name) or real(**kw))
        out = run(m.cal[m.cal.index(BREAK_DAY) + 8])
        assert out["exit_entries_open"] == len(open_ids) and out["exit_errors"] == 0
        # exactly each open entry's NON-final arms are written - none of the arms that were final before the run
        assert len(written) == len(set(written)) == out["exit_rows"] == sum(n_arms - len(mature_before[i]) for i in open_ids)
        assert not [k for k in written if k[1] in mature_before[k[0]]]
        # ... and the chunk's walk cache computes an identical walk once: the K x variant entries of one candidate
        # that share (fill, stop, day-0, adr20) walk once per arm, every row still written
        assert 0 < len(calls) < out["exit_rows"]

    @pytest.mark.parametrize("style", ["recorded", "legacy"])
    @pytest.mark.parametrize("split_from,split_to", [(1, 4), (4, 1)], ids=["forward_1_for_4", "reverse_4_for_1"])
    def test_a_split_after_the_break_day_makes_the_walk_unbookable_and_final(self, world, style, split_from, split_to):
        """A REAL split (forward and reverse; the ingest's recorded verdict, and a legacy row written before it)."""
        m, store, _ = world
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        store.splits.append(_real_split(style, D(2026, 9, 21), split_from, split_to))
        out = run(D(2026, 9, 21))
        rows = list(store.exit_registered().values())
        un = [x for x in rows if x["status"] == "unbookable"]
        assert un and all(x["mature"] and x["realized_r"] is None
                          and f"split_{split_from}:{split_to}_on_2026-09-21_after_entry" in x["reason"] for x in un)
        # a day-0 stop-out was booked on the break day itself (raw fill, raw stop, same session) and is already
        # final - the split cannot touch it; every entry still OPEN when the split executed becomes unbookable
        by_id = {r["id"]: r for r in store.entry.values()}
        for (eid, _arm), x in store.exit_registered().items():
            assert x["status"] == ("stopped_day0" if by_id[eid]["day0_stopped"] else "unbookable")
        assert out["exit_status"]["unbookable"] == len(un) == 17 * 15

    def test_a_recorded_phantom_after_the_break_day_does_not_void_the_walk(self, world):
        """#704: the ingest recorded a split that never happened and moved no bar. The old guard voided every open arm
        for ANY row; the walk is as bookable as with no split at all, and the rows are the no-split rows."""
        m, store, _ = world
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        store.splits.append(_phantom_split(D(2026, 9, 21)))
        out = run(D(2026, 9, 21))
        assert out["exit_status"].get("unbookable", 0) == 0 and out["exit_rows"] > 0 and out["exit_split_deferred"] == 0
        assert not [x for x in store.exit_registered().values() if x["status"] == "unbookable"]
        by_id = {r["id"]: r for r in store.entry.values()}
        live = [x for (eid, _a), x in store.exit_registered().items() if not by_id[eid]["day0_stopped"]]
        assert live and all(x["n_fwd"] >= 1 for x in live)                 # walked forward over the 09-18 / 09-21 bars

    def test_a_no_data_split_after_the_break_day_still_voids_the_walk(self, world):
        """Review fix on #704: 'skipped_no_data' is also what a FAILED Polygon fetch of a real split records, and then the
        pre-split bars stay raw while later bars are post-split - a cliff. It is not "no bar moved" (a phantom is), so the
        walk is unbookable exactly as it was before the verdict column existed."""
        m, store, _ = world
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        store.splits.append(_nodata_split(D(2026, 9, 21)))
        out = run(D(2026, 9, 21))
        un = [x for x in store.exit_registered().values() if x["status"] == "unbookable"]
        assert un and all(x["mature"] and "split_1:4_on_2026-09-21_after_entry" in x["reason"] for x in un)
        assert out["exit_split_deferred"] == 0 and out["exit_status"]["unbookable"] == len(un)

    def test_an_unapplied_split_after_the_break_day_defers_the_walk_then_the_applied_verdict_decides(self, world):
        m, store, _ = world
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        store.splits.append(_real_split("recorded", D(2026, 9, 21), 1, 4, adjustment_applied=False,
                                        adjustment_outcome=None, applied_factor=None))
        before = {k: dict(v) for k, v in store.exit.items()}
        out = run(D(2026, 9, 21))
        assert out["exit_split_deferred"] == 17 and out["exit_rows"] == 0 and out["exit_status"].get("unbookable", 0) == 0
        assert store.exit == before                                       # nothing written, nothing voided for good
        store.splits[0].update(adjustment_applied=True, adjustment_outcome="applied", applied_factor=0.25)
        out = run(D(2026, 9, 22))
        assert out["exit_split_deferred"] == 0 and out["exit_status"]["unbookable"] == 17 * 15

    def test_a_walk_is_cut_at_a_hole_and_ends_degraded(self, monkeypatch):
        m = build_market(future=12)
        i = m.cal.index(BREAK_DAY)
        hole = i + 5
        m.bars["MRNA"] = [r for k, r in enumerate(m.bars["MRNA"]) if k != hole]       # MRNA misses one session
        store = FakeStore(m)
        store.install(monkeypatch, sh)
        r = {x[0]: x for x in m.bars["MRNA"]}[BREAK_DAY]
        FakeCollector(m, minutes_for={("MRNA", BREAK_DAY): synth_minutes(BREAK_DAY, *r[1:5])},
                      polygon=_polygon).install(monkeypatch)
        for d in m.cal[m.cal.index(WATCH_NIGHT):]:
            run(d)
        live = [x for x in store.exit_registered().values() if x["status"] not in ("stopped_day0",)]
        assert live and all(x["last_bar_date"] < m.cal[hole] for x in live if x["status"] == "degraded")
        assert any(x["reason"] == "fwd_hole" for x in live)


class TestExitWalkEfficiency:
    """Pure dedupe + the bounded work list: nothing about WHAT is written changes."""

    @staticmethod
    def _entry(eid, ticker, e_date, fill=10.5, stop=10.0, adr20=0.05, final=()):
        return {"id": eid, "ticker": ticker, "break_date": e_date, "fill": fill, "stop": stop, "adr20": adr20,
                "day0_stopped": False, "day0_exit_price": None, "day0_exit_minute": None, "mature_arms": list(final)}

    def test_identical_walks_are_computed_once_and_each_entry_keeps_its_own_arms(self, monkeypatch):
        bars = _mrna_bars(build_market(future=24))
        cidx = np.arange(len(bars), dtype=np.int64)
        e_date = bars.dates[len(bars) - 60]
        calls = []
        real = cb.walk_exit

        def counting(**kw):
            calls.append((kw["fill"], kw["stop"], kw["arm"].name))
            return real(**kw)
        monkeypatch.setattr(cb, "walk_exit", counting)
        a, b = self._entry(1, "MRNA", e_date), self._entry(2, "MRNA", e_date, final=sorted(cb.ARMS)[:3])
        other = self._entry(3, "MRNA", e_date, fill=10.6)                               # another fill: its own walk
        cache: dict = {}
        ra, rb, ro = (sh.walk_entry_rows(x, bars, cidx, [], cache) for x in (a, b, other))
        assert len(calls) == 2 * len(cb.ARMS)                                            # a and `other` walk; b rides a's
        calls.clear()
        alone = [sh.walk_entry_rows(x, bars, cidx, []) for x in (a, b, other)]           # no cache: the reference rows
        assert len(calls) == len(cb.ARMS) + (len(cb.ARMS) - 3) + len(cb.ARMS)
        assert (ra, rb, ro) == tuple(alone)
        assert {r["arm"] for r in rb} == set(cb.ARMS) - set(sorted(cb.ARMS)[:3])         # b still walks only ITS non-final arms
        assert len(ra) == len(cb.ARMS) and {r["entry_id"] for r in ra} == {1} and {r["entry_id"] for r in rb} == {2}

    def test_the_work_list_is_bounded_by_the_stale_date_and_the_stale_ones_are_counted(self, world):
        m, store, _ = world
        run(WATCH_NIGHT)
        out = run(BREAK_DAY)
        assert out["exit_entries_open"] > 0 and out["exit_entries_stale"] == 0
        # age every entry past the horizon + margin: nothing is walked any more, the unfinished ones are counted
        unfinished = len(store._open_entries(len(cb.ARMS)))
        assert unfinished > 0                                          # not vacuous: some entry still has an open arm
        for r in store.entry.values():
            r["break_date"] = D(2020, 1, 2)
        out = run(m.cal[m.cal.index(BREAK_DAY) + 1])
        assert out["exit_entries_open"] == 0 and out["exit_entries_stale"] == unfinished


class TestSplitScaleArithmetic:
    def test_the_table_factor_is_the_product_of_from_over_to_exactly(self):
        """A LEGACY row (applied, no recorded outcome) is read at the table's ratio, and the product over several is
        bit-identical to the plain product of `split_from / split_to` this function has always computed."""
        import random
        rng = random.Random(5)
        for _ in range(300):
            ss = [{"execution_date": D(2026, 9, 17) + dt.timedelta(days=k), "split_from": rng.randint(1, 20),
                   "split_to": rng.randint(1, 20), "adjustment_applied": True}
                  for k in range(rng.randint(1, 3))]
            want = 1.0
            for s_ in ss:
                want *= float(s_["split_from"]) / float(s_["split_to"])
            close_watch = 100.0
            got = sh.split_scale(ss, close_watch * want, close_watch, D(2026, 9, 16))       # the data agrees with the table
            if not 0.0 < want:
                continue
            assert got == want                                                             # bit-for-bit, not approx

    def test_an_unreadable_split_row_is_none_not_a_guess(self):
        applied = {"execution_date": D(2026, 9, 17), "adjustment_applied": True}
        assert sh.split_scale([{**applied, "split_from": 1, "split_to": 0}], 100.0, 100.0, D(2026, 9, 16)) is None
        assert sh.split_scale([{**applied, "split_from": 1}], 100.0, 100.0, D(2026, 9, 16)) is None
        assert sh.split_scale([{**applied, "split_from": 1, "split_to": 4}], 100.0, None, D(2026, 9, 16)) is None

    def test_the_scale_is_the_ingests_recorded_verdict_with_the_data_as_the_cross_check(self):
        """#704: a recorded 'applied' row is read at its `applied_factor`; a recorded PHANTOM is 1.0; an unapplied row
        is None whatever the data says; and a reading the data does not bear out is None, never a guess."""
        d = D(2026, 9, 16)
        row = {"execution_date": D(2026, 9, 17), "split_from": 1, "split_to": 4, "adjustment_applied": True}
        applied = {**row, "adjustment_outcome": "applied", "applied_factor": 0.25}
        phantom = {**row, "adjustment_outcome": "phantom", "applied_factor": None}
        nodata = {**row, "adjustment_outcome": "skipped_no_data"}      # no bar written: NOT a phantom, read at the table
        assert sh.split_scale([applied], 25.0, 100.0, d) == 0.25                    # the bars moved, as recorded
        assert sh.split_scale([phantom], 100.0, 100.0, d) == 1.0                    # recorded phantom, bars unmoved
        assert sh.split_scale([nodata], 100.0, 100.0, d) is None                    # the bars did not move but the table says 1:4: sits out
        assert sh.split_scale([nodata], 25.0, 100.0, d) == 0.25                     # the data bears the table out: rescaled
        assert sh.split_scale([{**applied, "adjustment_applied": False}], 25.0, 100.0, d) is None   # not applied yet
        assert sh.split_scale([phantom], 25.0, 100.0, d) is None                    # recorded phantom but the bars moved
        assert sh.split_scale([applied], 100.0, 100.0, d) is None                   # recorded applied but they did not
        # a LEGACY phantom (no outcome) cannot be told from a real split: the table says 0.25, the data says 1.0 -> sits out
        assert sh.split_scale([row], 100.0, 100.0, d) is None
        # the recorded factor beats the table when they differ (a measured restatement that was not the table's ratio)
        assert sh.split_scale([{**applied, "applied_factor": 0.5}], 50.0, 100.0, d) == 0.5


class TestOneTradePerBaseInTheJob:
    def test_a_second_break_of_the_same_base_is_a_retrigger_and_matches_the_runners_batch(self, world):
        m, store, _ = world
        for d in m.cal[m.cal.index(WATCH_NIGHT):m.cal.index(BREAK_DAY) + 6]:
            run(d)
        cands = {}
        for r in store.entry.values():
            cands.setdefault((r["ticker"], r["pole_date"], r["k"], r["break_date"]), r)
        assert len({c[3] for c in cands}) >= 2, "MRNA must break the same base on more than one day"
        flat = []
        for (t, pd, k, bd), r in cands.items():
            c = {"ticker": t, "pole_date": pd.isoformat(), "K": k, "E": bd.isoformat(),
                 "pole_ci": m.cal.index(pd)}
            c.update({n: bool(r["cells"].get(n)) for n in sh.CELL_NAMES})
            flat.append(c)
        poles = {(t, m.cal.index(pd), pd.isoformat()) for (t, pd) in store_watch_poles(store)}
        rn.stamp_retrigger(flat)
        rn.stamp_base_chain(flat, rn.chain_bases(poles))
        want = {(c["ticker"], c["pole_date"], c["K"], c["E"]): c for c in flat}
        assert any(c["retrigger"] == 1 for c in flat)
        for (t, pd, k, bd), r in cands.items():
            w = want[(t, pd.isoformat(), k, bd.isoformat())]
            assert r["retrigger"] == w["retrigger"] and r["retrigger_chain"] == w["retrigger_chain"]
            assert r["base_id"] == w["base_id"]
            assert r["first_cells"] == {n: w["first_" + n] for n in sh.CELL_NAMES}
            assert r["first_chain_cells"] == {n: w["first_chain_" + n] for n in sh.CELL_NAMES}


def store_watch_poles(store):
    return {(k[0], v["pole_date"]) for k, v in store.watch.items()}


class TestMinuteFailures:
    def test_an_outage_defers_the_candidates_instead_of_writing_false_abstains(self, world):
        m, store, coll = world
        coll.outage_days.add(BREAK_DAY)
        run(WATCH_NIGHT)
        out = run(BREAK_DAY)
        assert not store.entry and out["minutes_deferred"] > 0 and out["minutes_outage_days"] == ["2026-09-17"]
        assert any(a[0] == sh.AUDIT_MINUTES_EVENT for a in store.audit)

    def test_the_next_nights_catch_up_writes_what_the_outage_deferred(self, world):
        m, store, coll = world
        coll.outage_days.add(BREAK_DAY)
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        coll.outage_days.clear()
        out = run(m.cal[m.cal.index(BREAK_DAY) + 1])
        e17 = [r for r in store.entry.values() if r["break_date"] == BREAK_DAY]
        assert len(e17) == 20 and out["entry_rows"] >= 20
        assert all(r["minutes_state"] in ("ok", "n/a") for r in e17)
        # 09-18 (MRNA breaks out again) has NO minutes provisioned in this world: a successful empty answer, which is
        # an observation (`no_minutes`, retryable) - the old all-empty-means-outage guess would have deferred it
        e18 = [r for r in store.entry.values() if r["break_date"] != BREAK_DAY]
        assert e18 and {r["reason"] for r in e18 if r["entry_variant"] != "close" and r["status"] == "abstain"} == {"no_minutes"}

    def test_a_raised_fetch_on_the_oldest_lookback_day_is_deferred_too_never_written_as_no_minutes(self, world):
        """#702: the collector now RAISES, so "the fetch failed" is known rather than guessed from an empty batch. The old
        code wrote the oldest day's candidates as `no_minutes` (it could not tell a failure from an empty session); a
        raised error is not an observation about the day, so NO row is written on any look-back day. The oldest day is
        the one no later night reads - that loss is counted (`minutes_deferred_oldest`) and named in the audit event."""
        m, store, coll = world
        coll.outage_days.add(BREAK_DAY)
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        run(m.cal[m.cal.index(BREAK_DAY) + 1])          # E = 09-17 is still inside the 3-session look-back, but not oldest
        assert not [r for r in store.entry.values() if r["break_date"] == BREAK_DAY]
        out = run(m.cal[m.cal.index(BREAK_DAY) + 2])    # now 09-17 is the OLDEST of the three: the last night that reads it
        assert not [r for r in store.entry.values() if r["break_date"] == BREAK_DAY]       # no row - and no `no_minutes`
        assert out["minutes_deferred_oldest"] > 0 and out["minutes_deferred"] >= out["minutes_deferred_oldest"]
        named = [a for a in store.audit if a[0] == sh.AUDIT_MINUTES_EVENT and "OLDEST" in a[1]]
        assert named and BREAK_DAY.isoformat() in named[-1][1]

    def test_every_minute_call_asks_the_collector_to_raise(self, world):
        m, store, coll = world
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        assert coll.raise_flags and all(coll.raise_flags)

    def test_a_genuinely_empty_session_is_written_as_no_minutes_and_a_later_fetch_heals_it(self, world):
        """A SUCCESSFUL call with no bars for the ticker is an observation, not a failure: the retryable `no_minutes`
        abstain is written (the four minute variants; `close` needs no minutes) and a later night may overwrite it."""
        m, store, coll = world
        coll.empty_days.add(BREAK_DAY)
        run(WATCH_NIGHT)
        out = run(BREAK_DAY)
        rows = [r for r in store.entry.values() if r["break_date"] == BREAK_DAY]
        assert len(rows) == 20 and out["minutes_deferred"] == 0 and not out["minutes_feed_down"]
        assert {(r["status"], r["reason"]) for r in rows if r["entry_variant"] != "close"} == {("abstain", "no_minutes")}
        coll.empty_days.clear()                                           # the bars arrive later
        run(m.cal[m.cal.index(BREAK_DAY) + 1])
        healed = [r for r in store.entry.values() if r["break_date"] == BREAK_DAY and r["entry_variant"] == "orh5"]
        assert {r["status"] for r in healed} == {"filled"}

    def test_only_the_batch_that_raised_is_deferred_the_rest_are_written(self, monkeypatch):
        """MRNA and MRNB are asked in separate batches (MINUTE_BATCH = 1 here); MRNA's batch raises both tries. MRNB is
        written, MRNA gets NO row (not a `no_minutes`), and the next night's look-back writes it."""
        monkeypatch.setattr(sh, "MINUTE_BATCH", 1)
        m = build_market(future=3, clone_mrna=True)
        store = FakeStore(m)
        store.install(monkeypatch, sh)
        mins = {(t, BREAK_DAY): synth_minutes(BREAK_DAY, *{x[0]: x for x in m.bars[t]}[BREAK_DAY][1:5])
                for t in ("MRNA", "MRNB")}
        coll = FakeCollector(m, minutes_for=mins, polygon=_polygon, error_tickers={("MRNA", BREAK_DAY)})
        coll.install(monkeypatch)
        run(WATCH_NIGHT)
        out = run(BREAK_DAY)

        def rows_of(t):
            return [x for x in store.entry.values() if x["ticker"] == t and x["break_date"] == BREAK_DAY]
        assert len(rows_of("MRNB")) == 20
        assert {x["status"] for x in rows_of("MRNB") if x["entry_variant"] == "orh5"} == {"filled"}
        assert rows_of("MRNA") == [] and out["minutes_deferred"] > 0 and out["minutes_deferred_oldest"] == 0
        assert sum(1 for d, ts in coll.minute_calls if d == BREAK_DAY and ts == ("MRNA",)) == 2      # asked, then once more
        coll.error_tickers.clear()
        run(m.cal[m.cal.index(BREAK_DAY) + 1])
        assert len(rows_of("MRNA")) == 20
        assert {x["status"] for x in rows_of("MRNA") if x["entry_variant"] == "orh5"} == {"filled"}

    def test_a_ticker_missing_from_a_good_fetch_is_a_retryable_no_minutes_abstain_that_later_heals(self, monkeypatch):
        m = build_market(future=3, clone_mrna=True)                 # MRNA and MRNB: two candidates on the same day
        store = FakeStore(m)
        store.install(monkeypatch, sh)
        r = {x[0]: x for x in m.bars["MRNB"]}[BREAK_DAY]
        good = synth_minutes(BREAK_DAY, *r[1:5])
        coll = FakeCollector(m, minutes_for={("MRNB", BREAK_DAY): good}, polygon=_polygon)   # MRNA's bars are missing
        coll.install(monkeypatch)
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        mrna = [x for x in store.entry.values() if x["ticker"] == "MRNA" and x["entry_variant"] == "orh5"]
        mrnb = [x for x in store.entry.values() if x["ticker"] == "MRNB" and x["entry_variant"] == "orh5"]
        assert {(x["status"], x["reason"]) for x in mrna} == {("abstain", "no_minutes")} and len(mrna) == 4
        assert {x["status"] for x in mrnb} == {"filled"}               # a fetch that reached MRNB is not an outage
        a = [x for x in store.entry.values() if x["ticker"] == "MRNA"]
        r2 = {x[0]: x for x in m.bars["MRNA"]}[BREAK_DAY]
        coll.minutes_for[("MRNA", BREAK_DAY)] = synth_minutes(BREAK_DAY, *r2[1:5])      # the bars arrive later
        out = run(m.cal[m.cal.index(BREAK_DAY) + 1])
        healed = [x for x in store.entry.values() if x["ticker"] == "MRNA" and x["entry_variant"] == "orh5"
                  and x["break_date"] == BREAK_DAY]
        assert healed and {x["status"] for x in healed} == {"filled"}
        assert all(x["retrigger"] == 0 for x in healed)                               # the retry did not re-stamp the base
        assert out["entry_rows"] >= 20 and a

    def test_a_filled_entry_is_never_overwritten_by_a_later_night(self, world):
        m, store, coll = world
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        before = {k: dict(v) for k, v in store.entry.items()}
        coll.minutes_for[("MRNA", BREAK_DAY)] = synth_minutes(BREAK_DAY, 152.5, 161.9599, 149.5, 150.0, low_minute=40)
        run(m.cal[m.cal.index(BREAK_DAY) + 1])
        for k, v in before.items():
            assert store.entry[k]["fill"] == v["fill"] and store.entry[k]["status"] == v["status"]


class TestAMissedWatchNight:
    def test_a_missed_watch_night_is_named_in_the_audit_row_and_its_breakouts_are_not_recovered(self, world):
        """The look-back recovers ENTRIES, not a WATCH LIST: with no D = 09-16 rows, E = 09-17 has nothing to
        break out of, tonight and on every later night. The audit row says which sessions had no watch rows."""
        m, store, coll = world
        out = run(BREAK_DAY)                                            # night 09-16 never ran
        assert not store.entry and WATCH_NIGHT.isoformat() in out["entry_days_without_watch"]
        nxt = run(m.cal[m.cal.index(BREAK_DAY) + 1])
        assert not [r for r in store.entry.values() if r["break_date"] == BREAK_DAY]
        assert WATCH_NIGHT.isoformat() in nxt["entry_days_without_watch"]      # still named a night later
        assert all(day != BREAK_DAY for day, _t in coll.minute_calls)          # and no minute was ever fetched for it

    def test_a_session_with_watch_rows_is_not_listed(self, world):
        m, store, _ = world
        run(WATCH_NIGHT)
        out = run(BREAK_DAY)
        assert WATCH_NIGHT.isoformat() not in out["entry_days_without_watch"]
        assert out["entry_rows"] == 20


class TestMinuteFeedDown:
    """A hanging / failing feed costs a bounded few minutes, not the job's whole budget - and only a RAISED call counts
    as failing: an EMPTY answer is a genuine empty session (#702, `raise_on_error`)."""

    @staticmethod
    def _fetch(monkeypatch, responder, tickers, out=None):
        """`responder(batch, n)` returns the dict to answer or raises; n = the call number (1-based)."""
        from agents.market_intelligence import collector
        calls = []

        async def fake(batch, start, end, timeout_s=6.0, *, raise_on_error=False):
            assert raise_on_error is True                                # the shadow always asks for the raise
            calls.append(tuple(batch))
            return responder(batch, len(calls))
        monkeypatch.setattr(collector, "get_alpaca_minute_bars_window", fake)
        got = asyncio.run(sh.fetch_minutes(BREAK_DAY, tickers, out))
        return got, calls

    @staticmethod
    def _boom(*_a):
        raise RuntimeError("alpaca down")

    def test_three_raised_batches_in_a_row_end_the_fetch_and_defer_every_ticker(self, monkeypatch):
        tickers = [f"T{i:03d}" for i in range(12 * sh.MINUTE_BATCH)]    # 12 batches
        out = {"minutes_feed_down": False}
        (mins, errored), calls = self._fetch(monkeypatch, self._boom, tickers, out)
        assert out["minutes_feed_down"] is True
        assert len(calls) == 2 * sh.MINUTE_ERROR_STREAK_STOP == 6         # 3 batches x (ask + one retry), not 24
        assert sh.MINUTE_BATCH * sh.MINUTE_ERROR_STREAK_STOP == 75        # the outage threshold: 75 tickers that raised
        assert all(len(c) == sh.MINUTE_BATCH for c in calls)
        assert errored == set(tickers) and mins == {}                     # the unasked 9 batches are deferred too

    def test_the_stop_defers_the_unasked_tickers_but_keeps_the_batches_that_answered(self, monkeypatch):
        """Batch 1 answers, then the feed dies: batch 1 is written (a real answer), everything after is deferred."""
        tickers = [f"T{i:03d}" for i in range(12 * sh.MINUTE_BATCH)]
        good = synth_minutes(BREAK_DAY, 10.0, 11.0, 9.5, 10.5)

        def responder(b, n):
            if n == 1:
                return {t: good for t in b}
            raise RuntimeError("alpaca down")
        out = {"minutes_feed_down": False}
        (mins, errored), _calls = self._fetch(monkeypatch, responder, tickers, out)
        assert out["minutes_feed_down"] is True
        assert set(mins) == set(tickers[:sh.MINUTE_BATCH]) and {st for _mb, st in mins.values()} == {"ok"}
        assert errored == set(tickers[sh.MINUTE_BATCH:]) and not (errored & set(mins))

    def test_a_batch_that_raises_once_and_then_answers_is_kept(self, monkeypatch):
        tickers = [f"T{i:03d}" for i in range(sh.MINUTE_BATCH)]
        good = synth_minutes(BREAK_DAY, 10.0, 11.0, 9.5, 10.5)
        out = {"minutes_feed_down": False}
        (mins, errored), calls = self._fetch(
            monkeypatch, lambda b, n: self._boom() if n == 1 else {t: good for t in b}, tickers, out)
        assert errored == set() and len(calls) == 2 and out["minutes_feed_down"] is False
        assert {st for _mb, st in mins.values()} == {"ok"} and set(mins) == set(tickers)

    def test_two_raised_batches_then_a_good_one_do_not_stop_the_fetch(self, monkeypatch):
        tickers = [f"T{i:03d}" for i in range(8 * sh.MINUTE_BATCH)]    # 8 batches
        good = synth_minutes(BREAK_DAY, 10.0, 11.0, 9.5, 10.5)
        # calls 1-4 are batches 1 and 2 (each asked twice) and raise: a streak of TWO, under the stop of 3
        out = {"minutes_feed_down": False}
        (mins, errored), calls = self._fetch(
            monkeypatch, lambda b, n: self._boom() if n <= 4 else {t: good for t in b}, tickers, out)
        assert out["minutes_feed_down"] is False and len(calls) == 4 + 6   # the 2 failed batches twice, then 6 good ones
        assert errored == set(tickers[:2 * sh.MINUTE_BATCH])
        assert sum(1 for mb, st in mins.values() if st == "ok") == 6 * sh.MINUTE_BATCH
        assert set(mins) == set(tickers[2 * sh.MINUTE_BATCH:])

    def test_an_empty_answer_is_neither_an_error_nor_retried_nor_a_streak(self, monkeypatch):
        """The heuristic this replaces read twelve empty batches in a row as a dead feed and deferred. A call that
        RETURNS means Alpaca answered: every ticker is a `no_minutes` observation, one call per batch, no stop."""
        tickers = [f"T{i:03d}" for i in range(12 * sh.MINUTE_BATCH)]
        out = {"minutes_feed_down": False}
        (mins, errored), calls = self._fetch(monkeypatch, lambda b, n: {}, tickers, out)
        assert errored == set() and out["minutes_feed_down"] is False
        assert len(calls) == 12                                          # one ask per batch: no retry of an empty answer
        assert set(mins) == set(tickers) and {st for _mb, st in mins.values()} == {"no_minutes"}

    def test_once_a_day_finds_the_feed_down_the_later_days_of_the_run_do_not_ask_again(self, world, monkeypatch):
        m, store, coll = world
        coll.outage_days.add(BREAK_DAY)
        run(WATCH_NIGHT)
        run(BREAK_DAY)                                                  # deferred: nothing returned
        calls = []

        async def feed_down(e, tickers, out=None):
            calls.append(e)
            out["minutes_feed_down"] = True
            return {}, set(tickers)
        monkeypatch.setattr(sh, "fetch_minutes", feed_down)
        out = run(m.cal[m.cal.index(BREAK_DAY) + 1])                    # look-back: 09-16, 09-17, 09-18
        assert calls == [BREAK_DAY]                                     # 09-18 had candidates too, and did not ask
        assert out["minutes_feed_down"] is True and out["minutes_deferred"] >= 2
        assert not store.entry


def _rescale_bars(m, ratio, when=lambda d: True):
    """What the 17:00 pull leaves behind for a split: MRNA's stored bars on the post-split scale (price / ratio,
    volume x ratio) - the split is 1:4 forward at ratio 4.0, 4:1 reverse at 0.25. `when` picks the dates."""
    m.bars["MRNA"] = [(d, o / ratio, h / ratio, l / ratio, c / ratio, v * ratio) if when(d) else (d, o, h, l, c, v)
                      for d, o, h, l, c, v in m.bars["MRNA"]]


SPLITS = pytest.mark.parametrize("split_from,split_to,ratio", [(1, 4, 4.0), (4, 1, 0.25)],
                                 ids=["forward_1_for_4", "reverse_4_for_1"])
STYLES = pytest.mark.parametrize("style", ["recorded", "legacy"])      # the ingest's verdict, and a pre-#704 boolean row


class TestSplitGuard:
    @STYLES
    @SPLITS
    def test_a_split_between_the_watch_night_and_the_break_day_abstains_every_variant(self, world, split_from,
                                                                                      split_to, ratio, style):
        """Both directions, with the stored bars ACTUALLY on the post-split scale (as the 17:00 pull leaves them)
        and the pivot still raw from night D. Before the breakout test carried the pivot into the stored units, a
        forward split wrote no row at all and a reverse one wrote a row for every K whether or not it broke out."""
        m, store, coll = world
        run(WATCH_NIGHT)
        w = dict(store.watch[("MRNA", WATCH_NIGHT)])
        e_bar = {x[0]: x for x in m.bars["MRNA"]}[BREAK_DAY]
        _rescale_bars(m, ratio)
        store.splits.append(_real_split(style, BREAK_DAY, split_from, split_to))
        out = run(BREAK_DAY)
        rows = [r for r in store.entry.values() if r["break_date"] == BREAK_DAY]
        assert len(rows) == len(store.entry) == 20 and {(r["status"], r["reason"]) for r in rows} == \
            {("abstain", sh.SPLIT_REASON)}
        assert not coll.minute_calls                                # no minute was fetched for a raw/adjusted mismatch
        assert out["entry_reasons"][sh.SPLIT_REASON] == 20
        assert out["entry_split_rescaled"] == 1 and out["entry_split_unresolved"] == 0
        for r in rows:                                              # pivot and gap read in the STORED units
            assert r["pivot"] == pytest.approx(w[f"pivot_{r['k']}"] / ratio)
            assert r["gap_pct"] == pytest.approx(e_bar[1] / w[f"pivot_{r['k']}"] - 1.0)

    @STYLES
    @SPLITS
    def test_a_split_on_a_name_that_did_not_break_out_writes_no_row_in_either_direction(self, world, split_from,
                                                                                        split_to, ratio, style):
        """The pivot is lifted out of reach (x1.5). On the RAW numbers a reverse split would still read as a break
        (E's stored high is 4x the raw pivot) - the phantom candidate that used to enter the one-trade-per-base
        history; in the stored units neither direction broke out, so neither writes anything."""
        m, store, coll = world
        run(WATCH_NIGHT)
        w = store.watch[("MRNA", WATCH_NIGHT)]
        for key in ("pivot_k5", "pivot_k10", "pivot_full", "pivot_tl"):
            w[key] *= 1.5
        _rescale_bars(m, ratio)
        store.splits.append(_real_split(style, BREAK_DAY, split_from, split_to))
        out = run(BREAK_DAY)
        assert not store.entry and out["entry_candidates"] == 0 and out["entry_rows"] == 0
        assert out["entry_split_rescaled"] == 1 and not coll.minute_calls

    def test_a_recorded_phantom_split_is_no_split_at_all(self, world):
        """#704. Polygon sometimes reports a split that never happened; `splits_ingest` writes no bar and now RECORDS
        'phantom'. The entry step reads that one verdict: the name is the unsplit name it is - minutes are fetched, the
        variants fill like on any other break day, nothing abstains `split_after_watch`. (Before, a phantom was still
        a "split" here: all twenty rows abstained although no price had moved.)"""
        m, store, coll = world
        store.splits.append(_phantom_split(BREAK_DAY))
        run(WATCH_NIGHT)
        out = run(BREAK_DAY)
        assert len(store.entry) == 20 and sh.SPLIT_REASON not in {r["reason"] for r in store.entry.values()}
        assert {r["status"] for r in store.entry.values() if r["entry_variant"] == "orh5"} == {"filled"}
        assert coll.minute_calls                                         # the minutes WERE fetched
        assert out["entry_split_rescaled"] == 0 and out["entry_split_unresolved"] == 0
        assert out["entry_reasons"].get(sh.SPLIT_REASON, 0) == 0

    def test_a_no_data_split_is_not_a_phantom_it_sits_out_when_no_bar_moved(self, world):
        """Review fix on #704: a split the ingest could not fetch ('skipped_no_data') leaves the pre-split bars raw, so
        it is NOT read as 1.0. The table says 1:4, the stored D close did not move: the data cross-check refuses both
        readings and the name sits out (counted, named) - it neither enters on a raw/adjusted mismatch nor claims the
        name is unsplit. The loosened reading (1.0) used to let a reverse split invent a breakout and write FILLED rows."""
        m, store, coll = world
        store.splits.append(_nodata_split(BREAK_DAY))
        run(WATCH_NIGHT)
        out = run(BREAK_DAY)
        assert not store.entry and not coll.minute_calls
        assert out["entry_split_unresolved"] == 1 and out["entry_split_rescaled"] == 0

    def test_a_no_data_split_whose_bars_did_move_is_rescaled_by_the_table(self, world):
        m, store, coll = world
        run(WATCH_NIGHT)
        _rescale_bars(m, 4.0)                                       # the bars were restated by some other route
        store.splits.append(_nodata_split(BREAK_DAY))
        out = run(BREAK_DAY)
        rows = [r for r in store.entry.values() if r["break_date"] == BREAK_DAY]
        assert len(rows) == 20 and {r["reason"] for r in rows} == {sh.SPLIT_REASON}
        assert out["entry_split_rescaled"] == 1 and out["entry_split_unresolved"] == 0

    def test_a_legacy_phantom_that_moved_no_bar_sits_out_rather_than_being_rescaled_by_the_table(self, world):
        """A phantom written BEFORE the outcome column cannot be told from a real split by its boolean: the table
        says 1:4, the stored D close is unchanged. The data cross-check refuses the table's rescale (it would lift the
        pivot x0.25 and miss a real breakout) and the name sits out, counted and named - the safe degradation."""
        m, store, coll = world
        store.splits.append(_real_split("legacy", BREAK_DAY, 1, 4))
        run(WATCH_NIGHT)
        out = run(BREAK_DAY)
        assert not store.entry and not coll.minute_calls
        assert out["entry_split_unresolved"] == 1 and out["entry_split_rescaled"] == 0

    def test_an_unexplained_scale_sits_the_name_out_instead_of_guessing(self, world):
        m, store, coll = world
        run(WATCH_NIGHT)
        _rescale_bars(m, 2.0)                                       # the table says 1:4; the bars moved by half
        store.splits.append({"ticker": "MRNA", "execution_date": BREAK_DAY, "split_from": 1, "split_to": 4,
                             "adjustment_applied": True})
        out = run(BREAK_DAY)
        assert not store.entry and out["entry_split_unresolved"] == 1 and out["entry_split_rescaled"] == 0
        assert out["entry_split_unresolved_tickers"] == ["MRNA:2026-09-17"]

    def test_an_unapplied_split_sits_out_tonight_and_the_catch_up_writes_it_once_applied(self, world):
        m, store, coll = world
        run(WATCH_NIGHT)
        # the split executed on E; E's bar (grouped daily) is on the new scale, the history is not yet adjusted
        _rescale_bars(m, 4.0, when=lambda d: d == BREAK_DAY)
        store.splits.append({"ticker": "MRNA", "execution_date": BREAK_DAY, "split_from": 1, "split_to": 4,
                             "adjustment_applied": False})
        out = run(BREAK_DAY)
        assert not store.entry and out["entry_split_unresolved"] == 1 and not coll.minute_calls
        # the next 17:00 pull applies it: the history (and every later bar) is on the new scale
        _rescale_bars(m, 4.0, when=lambda d: d != BREAK_DAY)
        store.splits[0]["adjustment_applied"] = True
        out = run(m.cal[m.cal.index(BREAK_DAY) + 1])
        rows = [r for r in store.entry.values() if r["break_date"] == BREAK_DAY]
        assert len(rows) == 20 and {r["reason"] for r in rows} == {sh.SPLIT_REASON}
        assert out["entry_split_rescaled"] >= 1

    def test_a_split_after_the_break_day_never_touches_the_days_recorded_fills(self, world):
        m, store, coll = world
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        before = {k: dict(v) for k, v in store.entry.items()}
        assert any(v["status"] == "filled" for v in before.values())
        nxt = m.cal[m.cal.index(BREAK_DAY) + 1]
        _rescale_bars(m, 0.25)                                      # a reverse 4:1 on the next session
        store.splits.append({"ticker": "MRNA", "execution_date": nxt, "split_from": 4, "split_to": 1,
                             "adjustment_applied": True})
        run(nxt)
        for k, v in before.items():                                 # the look-back re-reads E: nothing is rewritten
            assert store.entry[k] == v
        assert not any(r["reason"] == sh.SPLIT_REASON for r in store.entry.values() if r["break_date"] == BREAK_DAY)

    def test_an_announced_future_split_changes_nothing(self, world):
        m, store, coll = world
        store.splits.append({"ticker": "MRNA", "execution_date": D(2026, 12, 1), "split_from": 1, "split_to": 4,
                             "adjustment_applied": False})
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        assert {r["status"] for r in store.entry.values() if r["entry_variant"] == "orh5"} == {"filled"}

    def test_a_name_with_an_unapplied_split_in_its_history_sits_out_the_watch_list(self, world):
        m, store, _ = world
        store.splits.append({"ticker": "MRNA", "execution_date": D(2026, 8, 1), "split_from": 1, "split_to": 4,
                             "adjustment_applied": False})
        out = run(WATCH_NIGHT)
        assert out["watch_n"] == 0 and out["gate_funnel"].get("split_unapplied") == 1


class TestSicCache:
    def test_the_nightly_cap_holds_and_watch_names_go_first(self, world, monkeypatch):
        m, store, coll = world
        monkeypatch.setattr(sh, "SIC_CALLS_PER_NIGHT", 5)
        out = run(WATCH_NIGHT)
        assert len(coll.polygon_calls) == 5 and out["sic_fetched"] == 5
        assert coll.polygon_calls[0] == "/v3/reference/tickers/MRNA"     # the watch name before any filler
        coll.polygon_calls.clear()
        run(m.cal[m.cal.index(WATCH_NIGHT) + 0])                          # same night again: cached names are not re-fetched
        assert len(coll.polygon_calls) == 5 and not set(coll.polygon_calls) & {"/v3/reference/tickers/MRNA"}

    def test_a_404_is_cached_as_none_and_a_server_error_is_not(self, world, monkeypatch):
        m, store, coll = world

        class Http404(Exception):
            response = type("R", (), {"status_code": 404})()

        def poly(path):
            t = path.rsplit("/", 1)[1]
            if t == "FAB":
                raise Http404()
            if t == "FAC":
                raise RuntimeError("boom")
            return _polygon(path)
        coll.polygon = poly
        run(WATCH_NIGHT)
        assert store.sic["FAB"]["status"] == "none" and store.sic["MRNA"]["status"] == "ok"
        assert "FAC" not in store.sic                                    # tried again tomorrow

    def test_five_failures_in_a_row_end_the_fill(self, world):
        m, store, coll = world
        coll.polygon = lambda p: (_ for _ in ()).throw(RuntimeError("down"))
        out = run(WATCH_NIGHT)
        assert len(coll.polygon_calls) == sh.SIC_ERROR_STREAK_STOP and out["sic_errors"] == sh.SIC_ERROR_STREAK_STOP
        assert not store.sic and out["watch_n"] == 1                      # the night still completes

    def test_group_rs_needs_ten_members_with_a_sic(self, world):
        m, store, coll = world
        out = run(WATCH_NIGHT)
        assert out["groups_ge10"] == 1 and out["members_with_group"] == 21           # all 21 share SIC 28
        assert store.watch[("MRNA", WATCH_NIGHT)]["grp_pct"] == 0.0                 # one group: percentile 0
        coll2_store = FakeStore(m)
        assert coll2_store is not store


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 3. failure handling
# ═══════════════════════════════════════════════════════════════════════════════════════════════
class TestFailureHandling:
    def test_a_normal_night_sends_no_telegram(self, world, monkeypatch):
        from agents.market_intelligence import briefing
        from core import notifications
        sent = []
        for mod, name in ((briefing, "send_telegram_message"), (notifications, "notify_owner"),
                          (notifications, "notify_job_failure")):
            async def boom(*a, _n=name, **k):
                sent.append(_n)
            monkeypatch.setattr(mod, name, boom)
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        run(D(2026, 9, 18))
        assert sent == []

    def test_the_job_reaches_no_telegram_sender_and_no_wall_clock_date(self):
        from scripts import check_job_date_sources as cj
        job = next(j for j in cj.analyse()["jobs"] if j["job_id"] == "consolidation_breakout_shadow")
        assert job["sends"] == [] and job["date_from_clock"] == [] and job["reach"] > 3

    def test_the_steps_run_watch_first_then_entries_then_exits(self, world, monkeypatch):
        m, store, _ = world
        order = []
        for name in ("build_watch", "record_entries", "walk_exits"):
            real = getattr(sh, name)

            async def spy(*a, _real=real, _n=name, **k):
                order.append(_n)
                return await _real(*a, **k)
            monkeypatch.setattr(sh, name, spy)
        run(WATCH_NIGHT)
        assert order == ["build_watch", "record_entries", "walk_exits"]

    def test_a_hanging_minute_fetch_cannot_stop_tonights_watch_list_and_the_next_night_recovers_the_entries(
            self, world, monkeypatch):
        """Tonight's watch list is the one output with no catch-up (build_watch builds only tonight); the entries
        come back from the 3-session look-back. A hang in the minute fetch used to eat the shared 900 s budget
        BEFORE the watch step ran."""
        from agents.market_intelligence import collector
        m, store, coll = world
        run(WATCH_NIGHT)

        async def hang(*a, **k):
            await asyncio.sleep(60)
        monkeypatch.setattr(collector, "get_alpaca_minute_bars_window", hang)
        monkeypatch.setattr(sh, "BUDGET_S", 2.0)
        out = run(BREAK_DAY)                                            # no raise: fail open
        assert out["timed_out"] is True and not store.entry
        assert ("MRNA", BREAK_DAY) in store.watch                       # tonight's watch list WAS written
        assert sh.AUDIT_ERROR_EVENT in [a[0] for a in store.audit]
        monkeypatch.setattr(sh, "BUDGET_S", 900)
        coll.install(monkeypatch)                                       # the feed is back
        nxt = m.cal[m.cal.index(BREAK_DAY) + 1]
        run(nxt)
        assert len([r for r in store.entry.values() if r["break_date"] == BREAK_DAY]) == 20     # recovered
        assert ("MRNA", nxt) in store.watch

    def test_a_crash_propagates_after_the_audit_row_and_the_other_steps_still_ran(self, world, monkeypatch):
        m, store, _ = world

        async def broken(n_arms, stale_before):
            raise RuntimeError("db down")
        monkeypatch.setattr(sh, "cb_get_open_entries", broken)
        with pytest.raises(RuntimeError, match="db down"):
            run(WATCH_NIGHT)
        assert store.watch                                              # tonight's watch list was still written
        ev = [a for a in store.audit if a[0] == sh.AUDIT_RUN_EVENT]
        assert len(ev) == 1 and "STEP ERRORS" in ev[0][1] and "exits" in ev[0][1]

    def test_the_time_budget_fails_open_with_an_error_row(self, world, monkeypatch):
        m, store, _ = world

        async def slow(upto, limit=400):
            await asyncio.sleep(2)
            return []
        monkeypatch.setattr(sh, "cb_get_calendar", slow)
        monkeypatch.setattr(sh, "BUDGET_S", 0.05)
        out = run(WATCH_NIGHT)                                          # no raise
        assert out["timed_out"] is True
        kinds = [a[0] for a in store.audit]
        assert sh.AUDIT_ERROR_EVENT in kinds and sh.AUDIT_RUN_EVENT in kinds

    def test_an_exit_walk_that_fails_for_one_entry_is_counted_and_the_rest_are_written(self, world, monkeypatch):
        m, store, _ = world
        run(WATCH_NIGHT)
        real = sh.walk_entry_rows
        calls = {"n": 0}

        def flaky(entry, bars, cidx, splits, cache=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ValueError("bad bars")
            return real(entry, bars, cidx, splits, cache)
        monkeypatch.setattr(sh, "walk_entry_rows", flaky)
        out = run(BREAK_DAY)
        assert out["exit_errors"] == 1 and out["exit_rows"] == 18 * 15

    def test_one_audit_row_per_run_with_the_counts(self, world):
        _, store, _ = world
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        rows = [a for a in store.audit if a[0] == sh.AUDIT_RUN_EVENT]
        assert len(rows) == 2
        detail = __import__("json").loads(rows[1][2])
        for key in ("watch_n", "universe_n", "gate_funnel", "cells_per_k", "entry_candidates", "entry_rows",
                    "entry_status", "entry_reasons", "exit_rows", "exit_status", "sic_fetched", "wall_s"):
            assert key in detail


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 4. census, boundary, DDL
# ═══════════════════════════════════════════════════════════════════════════════════════════════
class TestCensus:
    def _jobs(self, monkeypatch):
        from agents.market_intelligence import scheduler as sched
        from tests.test_job_partition import _CapturingScheduler
        monkeypatch.setattr(sched, "AsyncIOScheduler", _CapturingScheduler)
        holder = {}
        real = sched._apply_role_partition

        def spy(scheduler, role):
            holder["jobs"] = list(scheduler.get_jobs())
            return real(scheduler, role)
        monkeypatch.setattr(sched, "_apply_role_partition", spy)

        async def go():
            sched.start_scheduler()
        asyncio.run(go())
        return sched, holder["jobs"]

    def test_registered_at_1748_mon_fri_and_wrapped_in_audit_wrap(self, monkeypatch):
        sched, jobs = self._jobs(monkeypatch)
        job = next(j for j in jobs if j.id == "consolidation_breakout_shadow")
        t = str(job.trigger)
        assert "hour='17'" in t and "minute='48'" in t and "day_of_week='mon-fri'" in t
        assert str(job.trigger.timezone) == "America/New_York"
        assert job.func.__name__ == "_consolidation_breakout_shadow_job"
        assert job.func.__code__.co_filename.endswith("core/job_audit.py")          # the audit_wrap closure
        assert job.misfire_grace_time == 600

    def test_the_slot_is_not_shared_with_another_job_at_17_48(self, monkeypatch):
        _, jobs = self._jobs(monkeypatch)
        same = [j.id for j in jobs if "hour='17'" in str(j.trigger) and "minute='48'" in str(j.trigger)]
        assert same == ["consolidation_breakout_shadow"]

    def test_intelligence_owned_and_not_execution_owned(self):
        from agents.market_intelligence import scheduler as sched
        assert "consolidation_breakout_shadow" in sched.INTELLIGENCE_OWNED_JOB_IDS
        assert "consolidation_breakout_shadow" not in sched.EXECUTION_OWNED_JOB_IDS

    @staticmethod
    def _fresh(code: str):
        import subprocess, sys
        return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=REPO)

    def test_execution_does_not_load_the_module(self):
        """Importing the scheduler (which the execution image does) must not import the shadow: the job imports it
        inside the function, and the execution image's module list does not carry it."""
        listed = (REPO / "scripts" / "exec_loaded_modules.txt").read_text()          # a DATA list, not source
        assert "consolidation_breakout_shadow" not in listed and "consolidation_breakout_pp" not in listed     # #705 (c)
        r = self._fresh("import sys; import agents.market_intelligence.scheduler; "
                        "sys.exit(int('agents.market_intelligence.consolidation_breakout_shadow' in sys.modules "
                        "or 'agents.market_intelligence.consolidation_breakout_pp' in sys.modules))")
        assert r.returncode == 0, r.stdout + r.stderr

    def test_the_module_loads_no_broker_code_beyond_the_pure_exit_math_and_the_boundary_gate_passes(self):
        """The shadow imports nothing from broker/. The pure core it calls (`cb`) imports exactly ONE broker module -
        `broker.exit_logic`, pure ladder math with no client and no trade-state I/O, under the `# exec-boundary-ok:`
        marker - so those two names (the package and the module) are the whole allowed set: an order, a position or
        a client module appearing here is a leak into the money path."""
        r = self._fresh("import sys; import agents.market_intelligence.consolidation_breakout_shadow; "
                        "got = sorted(m for m in sys.modules if m.startswith('agents.market_intelligence.broker')); "
                        "print(got); sys.exit(0 if got == ['agents.market_intelligence.broker', "
                        "'agents.market_intelligence.broker.exit_logic'] else 1)")
        assert r.returncode == 0, r.stdout + r.stderr
        import subprocess, sys
        g = subprocess.run([sys.executable, str(REPO / "scripts" / "check_execution_boundary.py"), "check"],
                           capture_output=True, text=True, cwd=REPO)
        assert g.returncode == 0, g.stdout + g.stderr


class TestDdlAndStatements:
    def test_the_ddl_is_idempotent_by_construction(self):
        from agents.market_intelligence import db
        ddl = db._CB_SHADOW_DDL
        creates = re.findall(r"CREATE\s+(?:UNIQUE\s+)?(TABLE|INDEX)\s+(IF NOT EXISTS)?", ddl)
        assert len(creates) == 8 and all(c[1] == "IF NOT EXISTS" for c in creates)
        assert not re.search(r"\bDROP\b|\bTRUNCATE\b|\bDELETE\s+FROM\b", ddl)      # (ON DELETE CASCADE is fine)

    def test_not_a_trade_table_no_account_mode_column(self):
        from agents.market_intelligence import db
        assert "account_mode" not in db._CB_SHADOW_DDL.lower().replace("-- ", "")
        for sql in (db.CB_WATCH_UPSERT_SQL, db.CB_ENTRY_UPSERT_SQL, db.CB_EXIT_UPSERT_SQL, db.CB_SIC_UPSERT_SQL):
            assert "mi_live_" not in sql and "mi_strategies" not in sql

    def test_the_write_guards_are_in_the_sql(self):
        from agents.market_intelligence import db
        assert "WHERE mi_consolidation_breakout_entry.status = 'abstain'" in db.CB_ENTRY_UPSERT_SQL
        assert "mi_consolidation_breakout_entry.reason = 'no_minutes'" in db.CB_ENTRY_UPSERT_SQL
        assert "WHERE NOT mi_consolidation_breakout_exit.mature" in db.CB_EXIT_UPSERT_SQL
        assert "UNIQUE (ticker, pole_date, k, entry_variant, break_date)" in db._CB_SHADOW_DDL
        assert "UNIQUE (entry_id, arm)" in db._CB_SHADOW_DDL

    def test_every_statement_is_registered_with_the_deploy_prepare_gate(self):
        from agents.market_intelligence import db
        import scripts.preflight_db_updates as pf
        registered = {id(sql) for _l, sql in pf.SHADOW_WRITER_STATEMENTS}
        for name in ("CB_WATCH_UPSERT_SQL", "CB_ENTRY_UPSERT_SQL", "CB_EXIT_UPSERT_SQL", "CB_SIC_UPSERT_SQL"):
            assert id(getattr(db, name)) in registered, name

    def test_placeholder_counts_match_the_column_lists(self):
        from agents.market_intelligence import db
        for sql, cols in ((db.CB_WATCH_UPSERT_SQL, db.CB_WATCH_COLS), (db.CB_ENTRY_UPSERT_SQL, db.CB_ENTRY_COLS),
                          (db.CB_EXIT_UPSERT_SQL, db.CB_EXIT_COLS), (db.CB_SIC_UPSERT_SQL, db.CB_SIC_COLS)):
            assert set(re.findall(r"\$(\d+)", sql)) == {str(i) for i in range(1, len(cols) + 1)}

    def test_jsonb_params_are_codec_ready_dicts_and_lists_never_strings(self):
        from agents.market_intelligence import db
        row = {"events": [(1, "stop", 1.5, 1.0)], "cells": {"C0": True}, "first_cells": None}
        p = db._row_params(row, ("events", "cells", "first_cells"), jsonb_dict=frozenset({"cells", "first_cells"}),
                           jsonb_list=frozenset({"events"}))
        assert p == ([[1, "stop", 1.5, 1.0]], {"C0": True}, None)
