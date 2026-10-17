"""#702 P6 - the Consolidation Breakout forward SHADOW recorder (`consolidation_breakout_shadow.py`).

What is pinned, and against what:

  1. PARITY with the offline runner (`scripts/probes/_cb_backtest/runner.py`): every small piece of plumbing the
     shadow re-writes (universe test symbols, the 130-consecutive-session test, the breakout test, gap fields, the
     maturity label, the forward-window cut, the cross-section, the one-trade-per-base stamping) returns what the
     runner's own returns on the same inputs - so a forward row and a backtest row for the same night agree. The
     stamping is also checked INCREMENTAL (night by night, as the job runs) against the runner's BATCH over the whole
     set. The watch build is checked against the runner's `scan_ticker` on real bars.
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
    def test_test_symbols_are_the_runners(self):
        assert sh.TEST_SYMBOLS == rn.TEST_SYMBOLS
        assert sh._TEST_FAMILY.pattern == rn._TEST_FAMILY.pattern
        for t in ("ZVZZT", "ZWZZT", "ZXZZT", "ZBZX", "NTEST", "AAPL", "ZZZZ", "ZAZZC", "TSLA"):
            assert sh.is_test_symbol(t) == rn.is_test_symbol(t)

    def test_contiguous_tail_is_the_runners_mask_at_the_last_index(self):
        rng = random.Random(1)
        for _ in range(200):
            n = rng.randint(100, 200)
            gaps = [1 if rng.random() > 0.01 else rng.randint(2, 4) for _ in range(n - 1)]
            cidx = np.cumsum([0] + gaps).astype(np.int64)
            assert sh.contiguous_tail(cidx, 130) == bool(rn.contiguous_window_mask(cidx, 130)[-1])
        assert sh.contiguous_tail(np.arange(129), 130) is False       # too short

    def test_breakout_gap_and_maturity_helpers_are_the_runners(self):
        for hi, pv in ((10.0, 9.9), (9.9, 9.9), (9.0, 9.9), (10.0, None)):
            assert sh.breaks_out(hi, pv) == rn.breaks_out(hi, pv)
        assert sh.gap_fields(11.0, 10.0, 0.05) == rn.gap_fields(11.0, 10.0, 0.05)
        assert sh.gap_fields(10.2, 10.0, 0.05) == rn.gap_fields(10.2, 10.0, 0.05)
        for st in ("stopped", "stopped_day0", "trailed", "target", "time_exit", "censored", "degraded", "unbookable"):
            for n in (0, 5, 120, 121, 130):
                assert sh.is_mature(st, n) == rn.is_mature(st, n)

    def test_fwd_end_is_the_runners_on_random_holes(self):
        rng = random.Random(2)
        for _ in range(300):
            n = rng.randint(5, 200)
            gaps = [1 if rng.random() > 0.05 else rng.randint(2, 3) for _ in range(n - 1)]
            cidx = np.cumsum([0] + gaps).astype(np.int64)
            e = rng.randint(0, n - 1)
            hi = e + rng.randint(1, 130)
            assert sh.fwd_end(cidx, e, hi) == rn.fwd_end(cidx, e, hi)

    def test_cross_section_is_the_runners(self):
        rng = random.Random(3)
        for _ in range(40):
            n = rng.randint(30, 80)
            mk = lambda: [None if rng.random() < 0.05 else rng.uniform(-0.5, 2.0) for _ in range(n)]
            r21, r63, r126 = mk(), mk(), mk()
            groups = [rng.choice(["28", "35", "73", None, "36"]) for _ in range(n)]
            assert sh.cross_section_one_date(r21, r63, r126, groups) == rn.cross_section_one_date(r21, r63, r126, groups)

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
    def test_stamping_matches_the_runners_batch_functions(self, seed):
        cal_iso, cands = self._scenario(seed)
        a = [dict(c) for c in cands]
        b = [dict(c) for c in cands]
        poles = {(c["ticker"], c["pole_ci"], c["pole_date"]) for c in cands}
        rn.stamp_retrigger(a)
        rn.stamp_base_chain(a, rn.chain_bases(poles))
        sh.stamp_retrigger(b)
        sh.stamp_base_chain(b, sh.chain_bases(poles))
        assert a == b

    @pytest.mark.parametrize("seed", range(6))
    def test_night_by_night_stamping_equals_the_batch_when_no_later_pole_bridges(self, seed):
        """The job stamps each breakout day against the candidates it has already written; the runner stamps the
        whole set at once. They agree whenever the chain key's poles are all known by the time of the candidate
        (a LATER pole falling between two earlier ones can merge two bases after the fact - the one documented
        way a forward row can differ from a batch row; the scenario's poles are known up front)."""
        cal_iso, cands = self._scenario(seed)
        poles = [(c["ticker"], c["pole_ci"], c["pole_date"]) for c in cands]
        batch = [dict(c) for c in cands]
        rn.stamp_retrigger(batch)
        rn.stamp_base_chain(batch, rn.chain_bases(set(poles)))
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
        rn.stamp_retrigger(batch)
        rn.stamp_base_chain(batch, rn.chain_bases(set(all_poles)))
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
        assert len(filled) == 19 and len(store.exit) == 19 * len(cb.ARMS) == 285 == out["exit_rows"]
        for r in store.exit.values():
            assert r["status"] in ("degraded", "stopped_day0") and r["last_bar_date"] == BREAK_DAY


class TestExitsAgainstTheOracle:
    def test_every_arm_of_every_entry_equals_the_module_walked_on_the_full_bars(self, world):
        m, store, _ = world
        for d in m.cal[m.cal.index(WATCH_NIGHT):]:
            run(d)
        bars = _mrna_bars(m)
        by_id = {r["id"]: r for r in store.entry.values()}
        n_checked = 0
        for (eid, arm), x in store.exit.items():
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
        assert n_checked == len(filled) * len(cb.ARMS) == len(store.exit)
        assert len({r["break_date"] for r in filled}) > 1 and n_checked >= 19 * 15      # not only the first break day

    def test_a_day_zero_stop_out_is_minus_one_r_or_worse_on_every_arm_and_never_reaches_the_daily_walk(self, world):
        m, store, _ = world
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        stopped = [r for r in store.entry.values() if r["day0_stopped"]]
        assert stopped, "the synthetic path breaks the pivot-variant stop on day 0"
        for ent in stopped:
            rows = [x for (eid, _a), x in store.exit.items() if eid == ent["id"]]
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
        assert {x["status"] for (e, _a), x in store.exit.items() if e == eid} == {"stopped_day0"}

    def test_a_mature_arm_is_not_walked_again_and_an_open_one_is(self, world):
        m, store, _ = world
        for d in m.cal[m.cal.index(WATCH_NIGHT):m.cal.index(BREAK_DAY) + 8]:
            run(d)
        frozen = {k: dict(v) for k, v in store.exit.items() if v["mature"]}
        assert frozen and any(not v["mature"] for v in store.exit.values())
        out = run(m.cal[m.cal.index(BREAK_DAY) + 8])
        for k, v in frozen.items():
            assert store.exit[k] == v                                   # untouched
        assert out["exit_entries_open"] > 0

    def test_only_the_arms_that_are_not_final_are_recomputed(self, world, monkeypatch):
        m, store, _ = world
        for d in m.cal[m.cal.index(WATCH_NIGHT):m.cal.index(BREAK_DAY) + 8]:
            run(d)
        calls = []
        real = cb.walk_exit
        monkeypatch.setattr(cb, "walk_exit", lambda **kw: calls.append(kw["arm"].name) or real(**kw))
        out = run(m.cal[m.cal.index(BREAK_DAY) + 8])
        assert out["exit_entries_open"] > 0
        assert len(calls) == out["exit_rows"] > 0                    # exactly one walk per row written ...
        assert len(calls) < out["exit_entries_open"] * len(cb.ARMS)  # ... and fewer than a full re-walk of every entry

    def test_a_split_after_the_break_day_makes_the_walk_unbookable_and_final(self, world):
        m, store, _ = world
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        store.splits.append({"ticker": "MRNA", "execution_date": D(2026, 9, 21), "split_from": 1, "split_to": 4,
                             "adjustment_applied": True})
        out = run(D(2026, 9, 21))
        rows = list(store.exit.values())
        un = [x for x in rows if x["status"] == "unbookable"]
        assert un and all(x["mature"] and x["realized_r"] is None and "split_1:4_on_2026-09-21_after_entry" in x["reason"]
                          for x in un)
        # a day-0 stop-out was booked on the break day itself (raw fill, raw stop, same session) and is already
        # final - the split cannot touch it; every entry still OPEN when the split executed becomes unbookable
        by_id = {r["id"]: r for r in store.entry.values()}
        for (eid, _arm), x in store.exit.items():
            assert x["status"] == ("stopped_day0" if by_id[eid]["day0_stopped"] else "unbookable")
        assert out["exit_status"]["unbookable"] == len(un) == 17 * 15

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
        live = [x for x in store.exit.values() if x["status"] not in ("stopped_day0",)]
        assert live and all(x["last_bar_date"] < m.cal[hole] for x in live if x["status"] == "degraded")
        assert any(x["reason"] == "fwd_hole" for x in live)


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
        assert len({r["break_date"] for r in store.entry.values()}) == 1 and BREAK_DAY in \
            {r["break_date"] for r in store.entry.values()}
        assert out["entry_rows"] >= 20
        assert all(r["minutes_state"] in ("ok", "n/a") for r in store.entry.values())

    def test_an_outage_on_the_oldest_lookback_day_is_written_as_no_minutes_not_dropped_forever(self, world):
        m, store, coll = world
        coll.outage_days.add(BREAK_DAY)
        run(WATCH_NIGHT)
        run(BREAK_DAY)
        run(m.cal[m.cal.index(BREAK_DAY) + 1])          # E = 09-17 is still inside the 3-session look-back, but not oldest
        assert not store.entry
        out = run(m.cal[m.cal.index(BREAK_DAY) + 2])    # now 09-17 is the OLDEST of the three: last chance
        mrna = [r for r in store.entry.values() if r["break_date"] == BREAK_DAY]
        assert len(mrna) == 20 and out["entry_rows"] >= 20
        assert {r["reason"] for r in mrna if r["entry_variant"] != "close" and r["status"] == "abstain"} == {"no_minutes"}

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
        healed = [x for x in store.entry.values() if x["ticker"] == "MRNA" and x["entry_variant"] == "orh5"]
        assert {x["status"] for x in healed} == {"filled"}
        assert all(x["retrigger"] == 0 for x in healed if x["break_date"] == BREAK_DAY)  # the retry did not re-stamp the base
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


class TestSplitGuard:
    def test_a_split_between_the_watch_night_and_the_break_day_abstains_every_variant(self, world):
        m, store, coll = world
        store.splits.append({"ticker": "MRNA", "execution_date": BREAK_DAY, "split_from": 1, "split_to": 4,
                             "adjustment_applied": True})
        run(WATCH_NIGHT)
        out = run(BREAK_DAY)
        assert len(store.entry) == 20 and {(r["status"], r["reason"]) for r in store.entry.values()} == \
            {("abstain", sh.SPLIT_REASON)}
        assert not coll.minute_calls                                # no minute was fetched for a raw/adjusted mismatch
        assert out["entry_reasons"][sh.SPLIT_REASON] == 20

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

    def test_a_crash_propagates_after_the_audit_row_and_the_other_steps_still_ran(self, world, monkeypatch):
        m, store, _ = world

        async def broken(n_arms):
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

        def flaky(entry, bars, cidx, splits):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ValueError("bad bars")
            return real(entry, bars, cidx, splits)
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
        assert "consolidation_breakout_shadow" not in listed
        r = self._fresh("import sys; import agents.market_intelligence.scheduler; "
                        "sys.exit(int('agents.market_intelligence.consolidation_breakout_shadow' in sys.modules))")
        assert r.returncode == 0, r.stdout + r.stderr

    def test_the_module_loads_no_broker_code_and_the_boundary_gate_passes(self):
        r = self._fresh("import sys; import agents.market_intelligence.consolidation_breakout_shadow; "
                        "bad = [m for m in sys.modules if m.startswith('agents.market_intelligence.broker')]; "
                        "print(bad); sys.exit(1 if bad else 0)")
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
        p = db._cb_row_params(row, ("events", "cells", "first_cells"), jsonb_dict=frozenset({"cells", "first_cells"}),
                              jsonb_list=frozenset({"events"}))
        assert p == ([[1, "stop", 1.5, 1.0]], {"C0": True}, None)
