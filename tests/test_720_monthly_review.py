"""#720 — the monthly trade review runner (scripts/probes/_720_monthly/run_review.py) is itself tested, on
INVENTED fixtures only. Nothing here touches a database or a real outcome row; the numbers are hand-computed
so the runner can be trusted on 11-29 without a prod dry run (the plan is pre-registered:
docs/analysis/720_monthly_review_plan_2026-11-08.md)."""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_PATH = _REPO / "scripts" / "probes" / "_720_monthly" / "run_review.py"
_spec = importlib.util.spec_from_file_location("run_review_720", _PATH)
rr = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rr  # a @dataclass in the module needs its module registered (py3.14)
_spec.loader.exec_module(rr)  # type: ignore[union-attr]


# ── fixture builders (invented) ────────────────────────────────────────────────────────────────
def trade(**kw) -> dict:
    base = {"id": 1, "ticker": "AAA", "alert_date": "2026-10-20", "account_mode": "live", "signal_type": "magna53",
            "status": "closed", "entry_attempt": "1", "exit_rule": "depth", "regime": "Bull",
            "entry_price": "100", "entry_shares": "10", "hard_stop": "98", "orb_low": "99", "orb_high": "100",
            "total_pnl": "0", "partial_taken": "f", "exits": "[]", "pnl_attribution": "",
            "filled_at": "2026-10-20 13:31:00+00", "closed_at": "2026-10-22 19:30:00+00"}
    base.update(kw)
    return base


def arm_row(trade_id, arm, realized_r, rcap=None, outcome="settled", **kw) -> dict:
    row = {"trade_id": str(trade_id), "arm": arm, "outcome": outcome, "realized_r": str(realized_r),
           "realized_r_capped": "" if rcap is None else str(rcap), "exit_session": "1", "final_reason": "stop_hit",
           "partial_fired": "f", "target_r": "8", "exit_era": "era_e"}
    row.update(kw)
    return row


def fill(trade_id, live_r, replay_r=None, ok=True, live_rcap=None, replay_rcap=None) -> dict:
    replay_r = live_r if replay_r is None else replay_r
    return {"trade_id": str(trade_id), "fidelity_pass": ok,
            "live_actual": arm_row(trade_id, "live_actual", live_r, live_r if live_rcap is None else live_rcap),
            "live_replay": arm_row(trade_id, "live_replay", replay_r, replay_r if replay_rcap is None else replay_rcap)}


# ── §1 population ──────────────────────────────────────────────────────────────────────────────
class TestLanesAndEras:
    def test_four_lanes(self):
        assert rr.lane_of(trade()) == "L1"
        assert rr.lane_of(trade(account_mode="paper", signal_type="magna53_smallcap")) == "L2"
        assert rr.lane_of(trade(account_mode="paper", signal_type="breakout_v1", exit_rule="breakout_pp")) == "L3"
        assert rr.lane_of(trade(account_mode="paper", signal_type="magna53")) == "L4"
        assert rr.lane_of(trade(account_mode="paper", signal_type="9m_day2", exit_rule="")) == "L4"

    def test_magna53_eras_come_from_the_row(self):
        assert rr.era_of(trade(alert_date="2026-08-20", exit_rule="")) == "era_c"
        assert rr.era_of(trade(alert_date="2026-09-10", exit_rule="")) == "era_d"
        assert rr.era_of(trade(alert_date="2026-10-20", exit_rule="depth")) == "era_e"
        # the stamp wins over the date: a depth row alerted before 10-13 is still E; an unstamped later row is D
        assert rr.era_of(trade(alert_date="2026-10-01", exit_rule="depth")) == "era_e"
        assert rr.era_of(trade(alert_date="2026-10-20", exit_rule="")) == "era_d"

    def test_smallcap_lane_labels_like_magna53_but_is_its_own_lane(self):
        t = trade(account_mode="paper", signal_type="magna53_smallcap", alert_date="2026-10-20", exit_rule="depth")
        assert rr.era_of(t) == "era_e" and rr.lane_of(t) == "L2"

    def test_breakout_rows_get_their_own_era_never_era_c(self):
        t = trade(account_mode="paper", signal_type="breakout_v1", exit_rule="breakout_pp", alert_date="2026-11-03")
        assert rr.era_of(t) == rr.BREAKOUT_ERA == "bp1"

    def test_breakout_stamp_mismatch_is_refused(self):
        with pytest.raises(ValueError):
            rr.era_of(trade(signal_type="breakout_v1", exit_rule=""))
        with pytest.raises(ValueError):
            rr.era_of(trade(signal_type="magna53", exit_rule="breakout_pp"))


class TestWindow:
    def test_closed_at_et_date_decides(self):
        t = trade(closed_at="2026-11-07 00:30:00+00")  # 20:30 ET on 11-06
        assert rr.in_window(t, date(2026, 11, 1), date(2026, 11, 6))
        assert not rr.in_window(t, date(2026, 11, 7), date(2026, 11, 29))

    def test_open_rows_are_never_in_a_window(self):
        assert not rr.in_window(trade(status="open", closed_at=""), date(2026, 1, 1), date(2026, 12, 31))

    def test_population_counts_window_carried_open_excluded(self):
        trades = [trade(id=1, closed_at="2026-11-10 20:00:00+00"),
                  trade(id=2, closed_at="2026-09-10 20:00:00+00", alert_date="2026-09-08", exit_rule=""),
                  trade(id=3, status="open", closed_at=""),
                  trade(id=4, closed_at="2026-11-12 20:00:00+00", pnl_attribution="bug_x", ticker="BUG"),
                  trade(id=5, closed_at="2026-11-12 20:00:00+00", hard_stop="101", orb_low="102", ticker="NOR"),
                  trade(id=6, closed_at="2026-11-12 20:00:00+00", entry_attempt="2", ticker="RE2")]
        pop = rr.population(trades, date(2026, 11, 1), date(2026, 11, 29), read_1106_ids=[1])
        e = pop["by_lane_era"][("L1", "era_e")]
        assert e["window"] == 4 and e["open"] == 1 and e["excluded"] == ["BUG"] and e["no_r"] == ["NOR"]
        assert e["flagged"] == ["RE2"]
        assert pop["by_lane_era"][("L1", "era_d")]["carried"] == 1
        assert [r["read_1106"] for r in pop["rows"]][:2] == [True, False]

    def test_era_mismatch_is_detected(self):
        t = trade(id=7)
        assert rr.era_mismatches([t], [arm_row(7, "live_actual", 1.0, exit_era="era_d")]) != []
        assert rr.era_mismatches([t], [arm_row(7, "live_actual", 1.0, exit_era="era_e")]) == []


# ── §5 fidelity ────────────────────────────────────────────────────────────────────────────────
class TestFidelity:
    def test_partial_size_bound_whole_shares(self):
        assert rr.partial_size_bound(1, 8.0, True) == pytest.approx(8 / 3)
        assert rr.partial_size_bound(2, 8.0, True) == pytest.approx(4 / 3)
        assert rr.partial_size_bound(3, 8.0, True) == pytest.approx(0.0)
        assert rr.partial_size_bound(4, 8.0, True) == 0.0
        assert rr.partial_size_bound(2, 8.0, False) == 0.0
        assert rr.partial_size_bound(2, 2.0, True) == pytest.approx(1 / 3)

    def test_ten_percent_arm_passes_a_kod_sized_miss(self):
        t = trade(entry_shares="20")
        res = rr.fidelity(t, arm_row(1, "live_actual", 5.87), arm_row(1, "live_replay", 5.58))
        assert res["pass"] and res["tol"] == pytest.approx(0.587) and res["tol_old_pass"] is False

    def test_small_position_with_replay_partial_passes_a_vicr_sized_miss(self):
        t = trade(entry_shares="2")
        la = arm_row(1, "live_actual", 7.30)
        lr = arm_row(1, "live_replay", 6.19, partial_fired="t", target_r="8")
        res = rr.fidelity(t, la, lr)
        assert res["pass"] and res["tol"] == pytest.approx(0.73 + 4 / 3)

    def test_same_miss_on_a_five_share_position_fails_and_is_classified(self):
        t = trade(entry_shares="5")
        la = arm_row(1, "live_actual", 7.30, exit_session="6", final_reason="sma_trail_stop")
        lr = arm_row(1, "live_replay", 6.19, partial_fired="t", exit_session="4", final_reason="sma_trail_stop")
        res = rr.fidelity(t, la, lr)
        assert not res["pass"] and res["cls"] == "exit_session_differs"

    def test_other_class_and_unsettled_controls(self):
        t = trade(entry_shares="5")
        res = rr.fidelity(t, arm_row(1, "live_actual", 1.0), arm_row(1, "live_replay", 2.0))
        assert not res["pass"] and res["cls"] == "other"
        res2 = rr.fidelity(t, arm_row(1, "live_actual", 1.0), arm_row(1, "live_replay", 1.0, outcome="horizon"))
        assert not res2["pass"] and res2["cls"] == "controls_unsettled"
        res3 = rr.fidelity(t, None, None)
        assert res3["cls"] == "controls_unsettled"


# ── §2 / §3 arm cells and the ladder ───────────────────────────────────────────────────────────
class TestEraCellAndLadder:
    def _fills(self):
        return [dict(fill(1, -1.0), arm_row=arm_row(1, "stop_orb_low", -0.5, -0.5)),
                dict(fill(2, 0.5), arm_row=arm_row(2, "stop_orb_low", 0.8, 0.8)),
                dict(fill(3, -1.0), arm_row=arm_row(3, "stop_orb_low", -0.6, -0.6))]

    def test_cell_arithmetic_by_hand(self):
        c = rr.era_cell("stop_orb_low", "era_e", self._fills())
        assert c.n == 3 and c.readable
        assert c.rcap_delta_sum == pytest.approx(0.5 + 0.3 + 0.4)
        assert c.rown_delta_sum == pytest.approx(1.2)
        assert c.drop_best == pytest.approx(1.2 - 0.5)
        assert c.better == 3 and c.worse == 0 and c.tie == 0
        assert c.engine_sum == pytest.approx(1.2) and c.engine_agrees
        assert c.tail_clip == 0 and c.rescues == 0  # a rescue needs the arm's own R > 0, not just "less bad"
        assert c.won is True
        rescued = rr.era_cell("stop_orb_low", "era_e", self._fills()[:2] + [dict(fill(3, -1.0), arm_row=arm_row(3, "stop_orb_low", 0.2, 0.2))])
        assert rescued.rescues == 1 and rescued.rcap_delta_sum == pytest.approx(0.5 + 0.3 + 1.2)

    def test_tail_clip_loses_regardless_of_mean(self):
        fills = [dict(fill(1, 2.5), arm_row=arm_row(1, "harvest_t3", 1.0, 1.0)),      # live rode to +2.5R, arm took 1.0 -> clip
                 dict(fill(2, -1.0), arm_row=arm_row(2, "harvest_t3", 1.0, 1.0)),
                 dict(fill(3, -1.0), arm_row=arm_row(3, "harvest_t3", 1.0, 1.0))]
        c = rr.era_cell("harvest_t3", "era_e", fills)
        assert c.rcap_delta_sum > 0 and c.tail_clip == 1 and c.won is False

    def test_excluded_classes_are_counted_not_dropped_silently(self):
        fills = [dict(fill(1, -1.0, ok=False), arm_row=arm_row(1, "stop_orb_low", 0.0, 0.0)),
                 dict(fill(2, -1.0), arm_row=arm_row(2, "stop_orb_low", 0.0, outcome="abstain")),
                 dict(fill(3, -1.0), arm_row=None),
                 dict(fill(4, -1.0), arm_row=arm_row(4, "entry_first_hour_bar", "", outcome="unscoreable",
                                                     final_reason="no_entry:never_crossed"))]
        c = rr.era_cell("stop_orb_low", "era_e", fills[:3])
        assert c.n == 0 and c.excluded == {"fidelity_fail": 1, "abstain": 1, "pending": 1}
        c2 = rr.era_cell("entry_first_hour_bar", "era_e", [fills[3]])
        assert c2.n == 1 and c2.rcap_delta_sum == pytest.approx(1.0) and c2.rown_delta_sum == 0.0  # I3: no-entry = 0 in R_cap

    def test_unreadable_cell_has_no_won(self):
        c = rr.era_cell("stop_orb_low", "era_e", self._fills()[:2])
        assert not c.readable and c.won is None

    def _cell(self, era, n, won):
        c = rr.EraCell(arm="x", era=era, n=n)
        if n >= rr.READABLE_MIN:
            c.rcap_deltas = [0.1] * n
            c.rcap_delta_sum = 0.1 * n if won else -0.1 * n
            c.rown_delta_sum = c.rcap_delta_sum
            c.engine_sum = c.rcap_delta_sum
            c.tail_clip = 0
        return c

    def test_ladder(self):
        cur = "era_e"
        assert rr.verdict({cur: self._cell(cur, 2, True)}, cur)[0] == "CAN'T TELL"
        assert rr.verdict({}, cur)[0] == "CAN'T TELL"
        assert rr.verdict({cur: self._cell(cur, 5, True)}, cur)[0] == "WATCH"
        assert rr.verdict({cur: self._cell(cur, 10, True)}, cur)[0] == "PROPOSE"
        assert rr.verdict({cur: self._cell(cur, 10, True), "era_d": self._cell("era_d", 6, False)}, cur)[0] == "NOTHING"
        assert rr.verdict({cur: self._cell(cur, 10, True), "era_d": self._cell("era_d", 2, False)}, cur)[0] == "PROPOSE"
        assert rr.verdict({cur: self._cell(cur, 10, False)}, cur)[0] == "NOTHING"

    def test_count_ladder(self):
        assert rr.count_verdict(2, True) == "CAN'T TELL"
        assert rr.count_verdict(5, False) == "NOTHING"
        assert rr.count_verdict(5, True) == "WATCH"
        assert rr.count_verdict(12, True) == "PROPOSE"
        assert rr.count_verdict(12, True, other_eras_lost=True) == "NOTHING"

    def test_arm_lens_runs_every_arm_of_the_lens(self):
        fills_by_era = {"era_e": [fill(i, -1.0) for i in range(1, 4)]}
        arm_rows = {(str(i), a): arm_row(i, a, -0.5, -0.5) for i in range(1, 4) for a in rr.STOP_ARMS}
        out = rr.arm_lens("stop", fills_by_era, arm_rows, "era_e")
        assert set(out) == set(rr.STOP_ARMS)
        assert all(v["verdict"] == "WATCH" for v in out.values())


# ── §3 descriptives ────────────────────────────────────────────────────────────────────────────
class TestDescriptives:
    def test_runner_shape(self):
        legs_be = json.dumps([{"reason": "partial_profit", "price": 116}, {"reason": "stop_hit", "price": 100.0}])
        legs_lo = json.dumps([{"reason": "partial_profit", "price": 116}, {"reason": "stop_hit", "price": 97.5}])
        assert rr.runner_shape(trade(exits=legs_be, partial_taken="t"))
        assert not rr.runner_shape(trade(exits=legs_lo, partial_taken="t"))
        assert not rr.runner_shape(trade(exits=json.dumps([{"reason": "stop_hit", "price": 98}])))

    def test_stopped_then_ran_needs_bars_never_an_absence(self):
        t = trade(exits=json.dumps([{"reason": "stop_hit", "price": 98}]), closed_at="2026-10-22 19:30:00+00")
        bars = [{"trade_date": f"2026-10-{23 + i:02d}", "high_price": "103", "low_price": "99"} for i in range(5)]
        assert rr.stopped_then_ran(t, {"AAA": bars}) is False
        bars[3]["high_price"] = "104.5"  # entry 100 + 2 x 2 = 104
        assert rr.stopped_then_ran(t, {"AAA": bars}) is True
        assert rr.stopped_then_ran(t, {"AAA": bars[:3]}) is None
        assert rr.stopped_then_ran(trade(exits=json.dumps([{"reason": "sma_trail_stop"}])), {"AAA": bars}) is None

    def test_partial_and_exit_descriptives(self):
        trades = [trade(id=1, partial_taken="t", entry_shares="2", total_pnl="40",
                        exits=json.dumps([{"reason": "partial_profit", "price": 116}, {"reason": "stop_hit", "price": 100}])),
                  trade(id=2, total_pnl="-20", exits=json.dumps([{"reason": "stop_hit", "price": 98}]))]
        sd = {"1": {"capture_pct": "0.5", "giveback_r": "4", "hold_trading_days": "6", "peak_r": "8"},
              "2": {"capture_pct": "", "giveback_r": "0.5", "hold_trading_days": "1", "peak_r": "0.4"}}
        p = rr.partial_descriptives(trades, sd)
        assert p == {"n": 2, "partial_fired": 1, "no_record": 0, "capture_pct_median": 0.5, "giveback_r_median": 2.25,
                     "runner_shape": 1, "shares_le_2": 1}
        e = rr.exit_descriptives(trades, sd)
        assert e["reasons"] == {"stop_hit": 2} and e["hold_days_median"] == 3.5 and e["disappoints"] is False
        # disappoints = sum < 0 and nothing >= +4R
        e2 = rr.exit_descriptives([trade(id=3, total_pnl="-20")], {})
        assert e2["disappoints"] is True

    def test_slippage_test(self):
        fills = [{"fill_vs_trigger_pct": "2.0", "live_rcap": "-1"}, {"fill_vs_trigger_pct": "1.5", "live_rcap": "-0.5"},
                 {"fill_vs_trigger_pct": "3.0", "live_rcap": "-1"}, {"fill_vs_trigger_pct": "0.2", "live_rcap": "2"}]
        s = rr.slippage_test(fills)
        assert s["over_1pct"] == 3 and s["over_sum"] == -2.5 and s["under_sum"] == 2 and s["verdict"] == "WATCH"
        assert rr.slippage_test(fills[:2] + fills[3:])["verdict"] == "CAN'T TELL"


# ── §4 the tail ────────────────────────────────────────────────────────────────────────────────
class TestTail:
    def test_tail_reads_the_real_trade_and_is_never_gated_by_fidelity(self):
        big = trade(id=1, ticker="WIN", total_pnl="146")          # R = 146 / (2 x 10) = 7.3
        bad = trade(id=2, ticker="GAP", total_pnl="-32")          # R = -1.6
        mid = trade(id=3, ticker="MID", total_pnl="10")
        bug = trade(id=4, ticker="BUG", total_pnl="200", pnl_attribution="bug")
        fid = {"1": {"pass": False, "cls": "whole_share"}}
        out = rr.tails([big, bad, mid, bug], {"1": {"peak_r": "9.1", "capture_pct": "0.8"}}, fid)
        assert [r["ticker"] for r in out["winners"]] == ["WIN"] and out["winners"][0]["fidelity"] is False
        assert out["winners"][0]["fidelity_cls"] == "whole_share" and out["winners"][0]["peak_r"] == 9.1
        assert [r["ticker"] for r in out["losers"]] == ["GAP"]


# ── §6 missed-by-slots ─────────────────────────────────────────────────────────────────────────
class TestMissedBySlots:
    def _bars(self, day, highs_lows):
        return [{"trade_date": (date.fromisoformat(day).toordinal() + i + 1) and date.fromordinal(date.fromisoformat(day).toordinal() + i + 1).isoformat(),
                 "high_price": str(h), "low_price": str(lo)} for i, (h, lo) in enumerate(highs_lows)]

    def test_records_and_width_rule(self):
        audit = [{"id": "1", "event_type": rr.MISSED_EVENT, "detail": json.dumps({"ticker": "ZZZ", "day": "2026-11-10", "break_price": 50, "stop": 48, "width": 2, "adr20": 0.05})},
                 {"id": "2", "event_type": rr.MISSED_EVENT, "detail": json.dumps({"ticker": "WID", "day": "2026-11-10", "break_price": 50, "stop": 46, "width": 4, "adr20": 0.05})},
                 {"id": "3", "event_type": rr.HOLD_EVENT, "detail": json.dumps({"state": "slots_full"})}]
        recs = rr.missed_records(audit)
        assert [r["ticker"] for r in recs] == ["ZZZ", "WID"]
        assert rr.width_ok(recs[0]) is True and rr.width_ok(recs[1]) is False
        assert rr.width_ok({"width": 1}) is None

    def test_proxy_walk(self):
        day = date(2026, 11, 10)
        plus = rr.missed_proxy_walk(50, 48, day, self._bars("2026-11-10", [(51, 49), (55, 50)] + [(52, 50)] * 8))
        assert plus["mature"] and plus["plus2r_before_stop"] is True and plus["mfe_r"] == pytest.approx(2.5)
        stopped = rr.missed_proxy_walk(50, 48, day, self._bars("2026-11-10", [(51, 47.9)] + [(60, 50)] * 9))
        assert stopped["plus2r_before_stop"] is False and stopped["mfe_r"] == pytest.approx(0.5)
        both = rr.missed_proxy_walk(50, 48, day, self._bars("2026-11-10", [(55, 47)] + [(55, 50)] * 9))
        assert both["plus2r_before_stop"] is False  # the same session: counts as stopped (conservative)
        young = rr.missed_proxy_walk(50, 48, day, self._bars("2026-11-10", [(51, 49)] * 4))
        assert not young["mature"] and young["plus2r_before_stop"] is None

    def test_missed_vs_seated_and_absence(self):
        w_hit = {"mature": True, "plus2r_before_stop": True, "mfe_r": 3.0}
        w_miss = {"mature": True, "plus2r_before_stop": False, "mfe_r": 0.5}
        missed = [{"walk": w_hit}] * 3 + [{"walk": {"mature": False}}]
        seated = [{"walk": w_miss, "realized_r": -1.0}] * 3
        res = rr.missed_vs_seated(missed, seated)
        assert res["missed_mature"] == 3 and res["verdict"] == "WATCH"
        assert rr.missed_vs_seated(missed * 4, seated)["verdict"] == "PROPOSE"
        assert rr.missed_vs_seated(missed[:1], seated)["verdict"] == "CAN'T TELL"
        assert rr.missed_vs_seated(missed, seated[:2])["verdict"] == "CAN'T TELL"
        obs = rr.absence_observables([{"event_type": rr.HOLD_EVENT, "detail": json.dumps({"state": "slots_full"})}], 2, 5, "on")
        assert obs["slots_full_holds"] == 1
        assert rr.absence_sentence(obs, 0) == "1 hold rows, none broke out while held"
        assert rr.absence_sentence(dict(obs, slots_full_holds=0), 0) == "no name was ever held for a full paper book"
        assert "did not run" in rr.absence_sentence(dict(obs, list_nights=0), 0)
        assert rr.absence_sentence(obs, 1) == "missed 1 of 1 held rows"


# ── §3 stop (c) ────────────────────────────────────────────────────────────────────────────────
class TestStopTooWide:
    def test_matrix(self):
        assert rr.stop_too_wide_matrix([12, 11, 15], [5, 4, 3])["matrix"] == "REVISIT"
        assert rr.stop_too_wide_matrix([12, 11, 15], [5, 4, 3])["verdict"] == "WATCH"
        keep = rr.stop_too_wide_matrix([1] * 10, [12] * 10)
        assert keep["matrix"] == "KEEP" and keep["p"] < 0.10 and keep["verdict"] == "NOTHING"
        split = rr.stop_too_wide_matrix([12, 1, 1], [5, 5, 5])
        assert split["matrix"] == "CANNOT TELL"
        assert rr.stop_too_wide_matrix([12, 11], [5, 4, 3])["verdict"] == "CAN'T TELL"
        assert rr.stop_too_wide_matrix([12] * 10, [5] * 10)["verdict"] == "PROPOSE"

    def test_fisher_lower_tail_sanity(self):
        assert rr.fisher_exact_one_sided_le(0, 10, 10, 0) == pytest.approx(1 / 184756)
        assert rr.fisher_exact_one_sided_le(5, 5, 5, 5) > 0.5


# ── §9 render + end to end on a temp run dir ───────────────────────────────────────────────────
def _write_csv(path: Path, rows: list[dict]):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


class TestRenderAndDriver:
    def test_render_first_line_is_the_answer_and_action_is_always_present(self):
        rep = {"run_date": "2026-11-29", "answer": "Nothing beats what we run; action: none.", "window_start": "2026-08-16",
               "window_end": "2026-11-29", "population": {("L1", "era_e"): {"window": 3, "carried": 0, "open": 1, "excluded": [], "no_r": [], "flagged": []}},
               "lens_rows": [{"lens": "stop: stop_orb_low", "where": "L1 / era_e", "n": 3, "reading": "era_e WON on n 3", "verdict": "WATCH"}],
               "tails": {"winners": [], "losers": []}, "missed": {}, "folded": [], "action": "none", "fidelity": None}
        md = rr.render(rep)
        assert md.splitlines()[2].startswith("**Nothing beats")
        assert "**Action: none**" in md and "| 3 |" in md and "Total" not in md

    def test_action_and_answer_lines(self):
        rows = [{"lens": "stop: stop_orb_low", "where": "L1 / era_e", "n": 10, "reading": "", "verdict": "PROPOSE"}]
        assert "CHANGE_PROCESS" in rr.action_line(rows) and "sign-off" in rr.action_line(rows)
        assert rr.action_line([]) == "none"
        assert rr.answer_line([], {"winners": [1], "losers": []}).startswith("Nothing beats")

    def test_build_report_end_to_end(self, tmp_path):
        run = tmp_path / "runs" / "2026-11-29"
        (run / "data").mkdir(parents=True)
        trades = [trade(id=i, ticker=f"T{i}", total_pnl=str(-20 if i < 3 else 150), closed_at="2026-11-12 20:00:00+00") for i in range(1, 4)]
        trades.append(trade(id=9, ticker="BPP", account_mode="paper", signal_type="breakout_v1", exit_rule="breakout_pp",
                            alert_date="2026-11-04", total_pnl="-20", closed_at="2026-11-06 20:00:00+00"))
        _write_csv(run / "data" / "trades.csv", trades)
        cf = []
        for i in range(1, 4):
            r = -1.0 if i < 3 else 7.5
            cf += [arm_row(i, "live_actual", r, r), arm_row(i, "live_replay", r, r)]
            cf += [arm_row(i, a, -0.5 if i < 3 else 7.5, -0.5 if i < 3 else 7.5) for a in rr.STOP_ARMS + rr.HARVEST_ARMS + rr.TRAIL_ARMS + rr.ENTRY_ARMS]
        _write_csv(run / "data" / "cf_arms.csv", cf)
        _write_csv(run / "data" / "sell_discipline.csv", [{"trade_id": "3", "peak_r": "8.0", "capture_pct": "0.94", "hold_trading_days": "7",
                                                            "stop_pct": "2", "stop_per_adr": "0.4", "giveback_r": "0.5"}])
        rep = rr.build_report(run, date(2026, 11, 29), rr.FIRST_WINDOW_START)
        assert rep["population"][("L1", "era_e")]["window"] == 3 and rep["population"][("L3", "bp1")]["window"] == 1
        assert rep["fidelity"] == {"n": 3, "pass": 3, "old_pass": 3, "classes": {}}
        assert [w["ticker"] for w in rep["tails"]["winners"]] == ["T3"]
        assert all(r["verdict"] in rr.VERDICTS for r in rep["lens_rows"]) and len(rep["lens_rows"]) == 13
        md = rr.render(rep)
        (run / "review.md").write_text(md)
        assert (run / "review.md").read_text().startswith("# #720 monthly trade review — 2026-11-29")
        manifest = rr.write_manifest(run, "2026-11-29T18:00:00-05:00")
        assert "trades.csv: rows 4 md5" in manifest

    def test_era_mismatch_stops_the_read(self, tmp_path):
        run = tmp_path / "r"
        (run / "data").mkdir(parents=True)
        _write_csv(run / "data" / "trades.csv", [trade(id=1)])
        _write_csv(run / "data" / "cf_arms.csv", [arm_row(1, "live_actual", 1.0, exit_era="era_d")])
        with pytest.raises(SystemExit):
            rr.build_report(run, date(2026, 11, 29), rr.FIRST_WINDOW_START)


def test_every_capture_query_is_read_only():
    cap = _PATH.parent / "capture"
    files = sorted(cap.glob("*.sql"))
    assert len(files) >= 10
    for p in files:
        first = p.read_text().splitlines()[0]
        assert first.strip() == "SET default_transaction_read_only = on;", p.name
        assert "\\copy (" in p.read_text() and "TO STDOUT WITH CSV HEADER" in p.read_text(), p.name


def test_pinned_constants_match_the_plan():
    assert rr.FIRST_WINDOW_START == date(2026, 8, 16)
    assert rr.READABLE_MIN == 3 and rr.PROPOSE_MIN == 10
    assert rr.FIDELITY_ABS == 0.25 and rr.FIDELITY_REL == 0.10 and rr.SMALL_POSITION_SHARES == 3
    assert rr.TAIL_WIN_R == 4.0 and rr.TAIL_LOSS_R == -1.5
    plan = (_REPO / "docs" / "analysis" / "720_monthly_review_plan_2026-11-08.md").read_text()
    for needle in ("2026-08-16", "max(0.25, 0.10", "≥ +4R", "≤ −1.5R", "bp1", "CAN'T TELL", "PROPOSE"):
        assert needle in plan, needle
