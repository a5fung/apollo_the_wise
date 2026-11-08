"""#720 — the monthly trade review runner (scripts/probes/_720_monthly/run_review.py) is itself tested, on
INVENTED fixtures in the UNITS PROD WRITES. Nothing here touches a database or a real outcome row; the numbers
are hand-computed so the runner can be trusted on 11-29 without a prod dry run (the plan is pre-registered:
docs/analysis/720_monthly_review_plan_2026-11-08.md; revised 11-08 against the challenge — one test per finding,
each written to FAIL on the pre-revision runner: set RUN_REVIEW_720_PATH to that file to prove it).

Units the fixtures honour (the challenge's point: green tests on wrong units proved nothing):
  mi_ep_missed_outcomes.max_high_5d       FRACTION from the gap-day open, window incl. day 0 -> NOT READ any more
  breakout_v1_missed_by_slots.width       FRACTION (level - stop) / level; adr20 a fraction too
  mi_sell_discipline_records.peak_r       hard-stop frame (entry - hard_stop); the breakeven arm is ORB-frame
  live_replay.exits[*].shares             fractions of ONE share (1/3 partial, 2/3 rest)
"""
from __future__ import annotations

import csv
import importlib.util
import json
import os
import sys
from datetime import date
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_PATH = Path(os.environ.get("RUN_REVIEW_720_PATH") or (_REPO / "scripts" / "probes" / "_720_monthly" / "run_review.py"))
_spec = importlib.util.spec_from_file_location("run_review_720", _PATH)
rr = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rr  # a @dataclass in the module needs its module registered (py3.14)
_spec.loader.exec_module(rr)  # type: ignore[union-attr]

PLAN = _REPO / "docs" / "analysis" / "720_monthly_review_plan_2026-11-08.md"
YAML = _REPO / "data_gated_reviews.yaml"
CAPTURE = _REPO / "scripts" / "probes" / "_720_monthly" / "capture"


# ── fixture builders (invented; prod units) ────────────────────────────────────────────────────
def trade(**kw) -> dict:
    # entry 100, ORB low 99 (ORB R = 1), hard stop 98 (the entry-2R stop -> hard-stop R = 2), 10 shares
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
           "partial_fired": "f", "target_r": "8", "breakeven_arm_r": "3", "exit_era": "era_e",
           "admission_era": "adm_2026-08-31_extension_cap_50_slot_rank_rs", "regime": "Bull",
           "entry_price": "100", "stop_price": "98", "live_stop": "98", "exits": "[]"}
    row.update(kw)
    return row


def fill(trade_id, live_r, replay_r=None, ok=True, live_rcap=None, replay_rcap=None, **kw) -> dict:
    replay_r = live_r if replay_r is None else replay_r
    out = {"trade_id": str(trade_id), "fidelity_pass": ok,
           "live_actual": arm_row(trade_id, "live_actual", live_r, live_r if live_rcap is None else live_rcap),
           "live_replay": arm_row(trade_id, "live_replay", replay_r, replay_r if replay_rcap is None else replay_rcap)}
    out.update(kw)
    return out


def legs(*items) -> str:
    """(reason, price[, shares]) tuples -> the exits JSON the writers produce."""
    out = []
    for it in items:
        reason, price = it[0], it[1]
        lg = {"reason": reason, "price": price, "time": "2026-10-22T19:30:00+00:00"}
        if len(it) > 2:
            lg["shares"] = it[2]
        out.append(lg)
    return json.dumps(out)


def replay_legs(partial_px, final_px, final_reason="stop_hit") -> str:
    """The recorder's one-fractional-share walk: 1/3 at the partial, 2/3 at the final leg."""
    return json.dumps([{"reason": "partial_profit", "price": partial_px, "shares": 1 / 3, "time": "s1"},
                       {"reason": final_reason, "price": final_px, "shares": 2 / 3, "time": "s4"}])


# ── §1 population ──────────────────────────────────────────────────────────────────────────────
class TestLanesAndEras:
    def test_four_lanes(self):
        assert rr.lane_of(trade()) == "L1"
        assert rr.lane_of(trade(account_mode="paper", signal_type="magna53_smallcap")) == "L2"
        assert rr.lane_of(trade(account_mode="paper", signal_type="breakout_v1", exit_rule="breakout_pp")) == "L3"
        assert rr.lane_of(trade(account_mode="paper", signal_type="magna53")) == "L4"

    def test_magna53_eras_come_from_the_row(self):
        assert rr.era_of(trade(alert_date="2026-08-20", exit_rule="")) == "era_c"
        assert rr.era_of(trade(alert_date="2026-09-10", exit_rule="")) == "era_d"
        assert rr.era_of(trade(alert_date="2026-10-20", exit_rule="depth")) == "era_e"
        assert rr.era_of(trade(alert_date="2026-10-01", exit_rule="depth")) == "era_e"
        assert rr.era_of(trade(alert_date="2026-10-20", exit_rule="")) == "era_d"

    def test_breakout_rows_get_their_own_era_and_a_stamp_mismatch_is_refused(self):
        t = trade(account_mode="paper", signal_type="breakout_v1", exit_rule="breakout_pp", alert_date="2026-11-03")
        assert rr.era_of(t) == rr.BREAKOUT_ERA == "bp1"
        with pytest.raises(ValueError):
            rr.era_of(trade(signal_type="breakout_v1", exit_rule=""))

    def test_admission_era_recorder_stamp_first_then_derived_and_said_so(self):
        """D5: the stamp when a recorder row exists; derived (and labelled) when none; n/a for breakout."""
        t = trade(alert_date="2026-10-20")
        assert rr.admission_era_of(t, arm_row(1, "live_actual", 1.0, admission_era="adm_X")) == ("adm_X", "recorder")
        lbl, src = rr.admission_era_of(t, None)
        assert src == "derived" and lbl.startswith("adm_2026-08-31")
        assert rr.admission_era_of(trade(account_mode="paper", signal_type="breakout_v1", exit_rule="breakout_pp"), None) == (None, "n/a")

    def test_open_floor_split_date_is_the_first_acting_session_of_the_718_flip(self):
        """#718 flipped ON 2026-11-03 15:05:28 UTC (after the ORB window) -> first acting session 2026-11-04 (D5).
        Derived here through rule_eras' own helper, never re-typed."""
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from agents.market_intelligence.rule_eras import first_acting_session_after
        flip = datetime(2026, 11, 3, 15, 5, 28, tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("America/New_York"))
        assert first_acting_session_after(flip, is_trading_day=rr.is_trading_day) == rr.OPEN_FLOOR_FIRST_SESSION == date(2026, 11, 4)
        assert rr.post_open_floor(trade(alert_date="2026-11-03")) is False
        assert rr.post_open_floor(trade(alert_date="2026-11-04")) is True


class TestWindow:
    def test_closed_at_et_date_decides(self):
        t = trade(closed_at="2026-11-07 00:30:00+00")  # 20:30 ET on 11-06
        assert rr.in_window(t, date(2026, 11, 1), date(2026, 11, 6))
        assert not rr.in_window(t, date(2026, 11, 7), date(2026, 11, 29))
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
        assert e["window"] == 4 and e["open"] == 1 and e["excluded"] == ["BUG"] and e["no_r"] == ["NOR"] and e["flagged"] == ["RE2"]
        assert pop["by_lane_era"][("L1", "era_d")]["carried"] == 1
        assert [r["read_1106"] for r in pop["rows"]][:2] == [True, False]

    def test_era_mismatch_is_detected(self):
        t = trade(id=7)
        assert rr.era_mismatches([t], [arm_row(7, "live_actual", 1.0, exit_era="era_d")]) != []
        assert rr.era_mismatches([t], [arm_row(7, "live_actual", 1.0, exit_era="era_e")]) == []


class TestRecorderGaps:
    def test_a_dead_recorder_is_named_not_read_as_a_thin_era(self):
        """Finding 8: per era fills / with rows / settled pairs, and every closed fill older than the recorder's
        own retry window with no rows is NAMED as a gap."""
        old = trade(id=1, ticker="OLD", closed_at="2026-10-01 20:00:00+00")
        fresh = trade(id=2, ticker="NEW", closed_at="2026-11-27 20:00:00+00")
        rowed = trade(id=3, ticker="ROW", closed_at="2026-10-01 20:00:00+00")
        cf = [arm_row(3, "live_actual", 1.0), arm_row(3, "live_replay", 1.0)]
        g = rr.recorder_gaps([old, fresh, rowed], cf, date(2026, 11, 29))
        e = g["era_e"]
        assert e["fills"] == 3 and e["with_rows"] == 1 and e["settled_pairs"] == 1
        assert len(e["gaps"]) == 1 and e["gaps"][0].startswith("OLD")   # NEW is inside the retry window
        assert rr.RECORDER_GAP_SESSIONS == 5                              # live_fill_counterfactuals.GAP_RETRY_SESSIONS, imported


# ── exits legs: the writers' vocabulary ────────────────────────────────────────────────────────
class TestExitReasons:
    def test_vocabulary_is_the_five_writers_and_gap_through_is_not_a_leg(self):
        """Finding 9: stop_hit / partial_profit / sma_trail_stop / breakout_stall_cut / the width sale (a sentence,
        bucketed by prefix) / 'exit'. gap_through and intraday_stop are never written as legs."""
        assert rr.reason_bucket("stop_hit") == "stop_hit"
        assert rr.reason_bucket("setup:stop_too_wide_after_fill: fill $10.00 - true low $9.00 = 10.00% > ADR20 5.00%") == rr.REASON_WIDE_AFTER_FILL
        assert rr.reason_bucket("gap_through") == "other:gap_through"
        assert "gap_through" not in rr.EXIT_REASONS and "intraday_stop" not in rr.EXIT_REASONS

    def test_depth_sale_is_exit_rule_depth_plus_a_final_sma_trail_stop_leg(self):
        t = trade(exit_rule="depth", exits=legs(("sma_trail_stop", 105)))
        assert rr.is_depth_sale(t) is True
        assert rr.is_depth_sale(trade(exit_rule="", alert_date="2026-09-10", exits=legs(("sma_trail_stop", 105)))) is False
        assert rr.is_depth_sale(trade(exit_rule="depth", exits=legs(("stop_hit", 98)))) is False

    def test_depth_sale_cost_is_the_open_sale_vs_the_prior_close_in_r(self):
        t = trade(exit_rule="depth", exits=json.dumps([{"reason": "sma_trail_stop", "price": 105, "time": "2026-10-22T13:31:00+00:00"}]))
        daily = {"AAA": [{"trade_date": "2026-10-21", "close": "106"}, {"trade_date": "2026-10-22", "close": "104"}]}
        assert rr.depth_sale_cost_r(t, daily) == pytest.approx((105 - 106) / 2)     # hard-stop R = 2
        assert rr.depth_sale_cost_r(trade(exits=legs(("stop_hit", 98))), daily) is None


# ── §5 fidelity ────────────────────────────────────────────────────────────────────────────────
class TestFidelity:
    def test_live_fraction_comes_from_the_real_partial_leg_shares(self):
        """Finding 10: not a dated share-sizer model — the shares the LIVE sizer actually sold, from `exits`."""
        assert rr.partial_fraction(trade(entry_shares="2", exits=legs(("partial_profit", 116, 1), ("stop_hit", 100, 1)))) == pytest.approx(0.5)
        assert rr.partial_fraction(trade(entry_shares="1", exits=legs(("stop_hit", 100, 1)))) == 0.0
        assert rr.partial_fraction(trade(entry_shares="9", exits=legs(("partial_profit", 116, 3), ("stop_hit", 100, 6)))) == pytest.approx(1 / 3)

    def test_reweighting_the_replay_to_the_live_fraction(self):
        # replay: 1/3 @ 116 (+16) and 2/3 @ 110 (+10) on one share -> pnl 12 -> 6.0R in the live-stop frame (risk 2)
        lr = arm_row(1, "live_replay", 6.0, partial_fired="t", exits=replay_legs(116, 110))
        assert rr.reweight_replay_r(lr, 1 / 3) == pytest.approx(6.0)
        assert rr.reweight_replay_r(lr, 0.0) == pytest.approx(5.0)      # a 1-share live position sold nothing at the partial
        assert rr.reweight_replay_r(lr, 0.5) == pytest.approx(6.5)      # a 2-share position sold half
        no_partial = arm_row(1, "live_replay", -1.0, exits=json.dumps([{"reason": "stop_hit", "price": 98, "shares": 1.0}]))
        assert rr.reweight_replay_r(no_partial, 0.0) == pytest.approx(-1.0)   # nothing to re-weight: as stored

    def test_a_whole_share_miss_passes_only_reweighted_and_then_compares_arms_with_the_replay(self):
        t = trade(entry_shares="1", total_pnl="10", exits=legs(("stop_hit", 110, 1)))     # live 5.0R, no partial leg
        la = arm_row(1, "live_actual", 5.0)
        lr = arm_row(1, "live_replay", 6.0, partial_fired="t", exits=replay_legs(116, 110))
        res = rr.fidelity(t, la, lr)
        assert res["pass"] and res["via"] == "reweighted" and res["baseline"] == "live_replay"
        assert res["tol"] == pytest.approx(0.5) and res["diff"] == pytest.approx(1.0) and res["diff_reweighted"] == pytest.approx(0.0)
        assert res["tol_old_pass"] is False

    def test_tolerance_is_max_of_abs_and_ten_percent_with_no_extra_bound(self):
        """The old bound added up to 2.67R on a 1-share fill; now a replay error the re-weighting cannot explain fails."""
        t = trade(entry_shares="1", exits=legs(("stop_hit", 110, 1)))
        la = arm_row(1, "live_actual", 5.0)
        lr = arm_row(1, "live_replay", 7.0, partial_fired="t", exits=replay_legs(116, 113))   # re-weighted 6.5 -> still off by 1.5
        res = rr.fidelity(t, la, lr)
        assert not res["pass"] and res["tol"] == pytest.approx(0.5) and res["cls"] == "whole_share"
        assert not hasattr(rr, "partial_size_bound")

    def test_ten_percent_arm_passes_a_kod_sized_miss_on_the_stored_replay(self):
        res = rr.fidelity(trade(entry_shares="20"), arm_row(1, "live_actual", 5.87), arm_row(1, "live_replay", 5.58))
        assert res["pass"] and res["via"] == "stored" and res["baseline"] == "live_actual" and res["tol_old_pass"] is False

    def test_session_or_reason_difference_is_classified_before_whole_share(self):
        """Finding 10: a 2-share fill whose replay exited in a different session is a different exit path, not a
        sizing artefact — the old order called it whole_share."""
        t = trade(entry_shares="2", exits=legs(("stop_hit", 100, 2)))
        la = arm_row(1, "live_actual", 1.0, exit_session="6", final_reason="sma_trail_stop")
        lr = arm_row(1, "live_replay", 3.0, partial_fired="t", exit_session="4", final_reason="sma_trail_stop",
                     exits=replay_legs(116, 102))
        assert rr.classify_fidelity_miss(t, la, lr) == "exit_session_differs"
        res = rr.fidelity(t, la, lr)
        assert not res["pass"] and res["cls"] == "exit_session_differs"

    def test_other_class_and_unsettled_controls(self):
        t = trade(entry_shares="5")
        assert rr.fidelity(t, arm_row(1, "live_actual", 1.0), arm_row(1, "live_replay", 2.0))["cls"] == "other"
        assert rr.fidelity(t, arm_row(1, "live_actual", 1.0), arm_row(1, "live_replay", 1.0, outcome="horizon"))["cls"] == "controls_unsettled"
        assert rr.fidelity(t, None, None)["cls"] == "controls_unsettled"


# ── §2 / §3 arm cells and the ladder ───────────────────────────────────────────────────────────
class TestEraCellAndLadder:
    def _fills(self):
        return [dict(fill(1, -1.0), arm_row=arm_row(1, "stop_orb_low", -0.5, -0.5)),
                dict(fill(2, 0.5), arm_row=arm_row(2, "stop_orb_low", 0.8, 0.8)),
                dict(fill(3, -1.0), arm_row=arm_row(3, "stop_orb_low", -0.6, -0.6))]

    def test_cell_arithmetic_by_hand(self):
        c = rr.era_cell("stop_orb_low", "era_e", self._fills())
        assert c.n == 3 and c.readable
        assert c.rcap_delta_sum == pytest.approx(1.2) and c.rown_delta_sum == pytest.approx(1.2)
        assert c.drop_best == pytest.approx(1.2 - 0.5) and c.better == 3 and c.engine_agrees and c.won is True

    def test_tail_clip_loses_regardless_of_mean(self):
        fills = [dict(fill(1, 2.5), arm_row=arm_row(1, "harvest_t3", 1.0, 1.0)),
                 dict(fill(2, -1.0), arm_row=arm_row(2, "harvest_t3", 1.0, 1.0)),
                 dict(fill(3, -1.0), arm_row=arm_row(3, "harvest_t3", 1.0, 1.0))]
        c = rr.era_cell("harvest_t3", "era_e", fills)
        assert c.rcap_delta_sum > 0 and c.tail_clip == 1 and c.won is False

    def test_excluded_classes_are_counted_not_dropped_silently(self):
        fills = [dict(fill(1, -1.0, ok=False), arm_row=arm_row(1, "stop_orb_low", 0.0, 0.0)),
                 dict(fill(2, -1.0), arm_row=arm_row(2, "stop_orb_low", 0.0, outcome="abstain")),
                 dict(fill(3, -1.0), arm_row=None)]
        c = rr.era_cell("stop_orb_low", "era_e", fills)
        assert c.n == 0 and c.excluded == {"fidelity_fail": 1, "abstain": 1, "pending": 1}

    def test_a_reweighted_fill_is_compared_with_the_replay_on_every_condition(self):
        """§5: baseline = live_replay for a fill that passed only re-weighted — the delta AND the >= +4R / tail-clip
        counts read the replay row, not live_actual."""
        fl = dict(fill(1, 7.3, replay_r=3.0, live_rcap=7.3, replay_rcap=3.0, baseline="live_replay"),
                  arm_row=arm_row(1, "harvest_t3", 3.5, 3.5))
        c = rr.era_cell("harvest_t3", "era_e", [fl])
        assert c.rcap_delta_sum == pytest.approx(0.5) and c.live_ge4 == 0 and c.tail_clip == 0 and c.baseline_replay == 1
        c2 = rr.era_cell("harvest_t3", "era_e", [dict(fl, baseline="live_actual")])
        assert c2.rcap_delta_sum == pytest.approx(-3.8) and c2.live_ge4 == 1 and c2.tail_clip == 1

    def test_pre_and_post_1104_counts_ride_on_the_cell(self):
        c = rr.era_cell("stop_orb_low", "era_e", [dict(f_, post_1104=(i == 2)) for i, f_ in enumerate(self._fills())])
        assert (c.n_pre_1104, c.n_post_1104) == (2, 1)

    def _cell(self, era, n, won):
        c = rr.EraCell(arm="x", era=era, n=n)
        if n >= rr.READABLE_MIN:
            c.rcap_deltas = [0.1] * n
            c.rcap_delta_sum = 0.1 * n if won else -0.1 * n
            c.rown_delta_sum = c.rcap_delta_sum
            c.engine_sum = c.rcap_delta_sum
        return c

    def test_ladder_is_judged_on_the_current_era_only_older_eras_are_context(self):
        """Finding 1 / D1: on 11-06 every arm lost era C or D, and those eras never change — under the old veto no
        arm could ever reach WATCH or PROPOSE."""
        cur = "era_e"
        assert rr.verdict({cur: self._cell(cur, 2, True)}, cur)[0] == "CAN'T TELL"
        assert rr.verdict({}, cur)[0] == "CAN'T TELL"
        assert rr.verdict({cur: self._cell(cur, 5, True)}, cur)[0] == "WATCH"
        v, why = rr.verdict({cur: self._cell(cur, 10, True), "era_d": self._cell("era_d", 6, False), "era_c": self._cell("era_c", 7, False)}, cur)
        assert v == "PROPOSE" and "era_c lost (n 7)" in why and "era_d lost (n 6)" in why
        assert rr.verdict({cur: self._cell(cur, 10, False), "era_d": self._cell("era_d", 6, True)}, cur)[0] == "NOTHING"

    def test_count_ladder(self):
        assert rr.count_verdict(2, True) == "CAN'T TELL"
        assert rr.count_verdict(5, False) == "NOTHING"
        assert rr.count_verdict(5, True) == "WATCH"
        assert rr.count_verdict(12, True) == "PROPOSE"

    def test_arm_lens_runs_every_arm_and_admission_cells_never_pool(self):
        fills_by_era = {"era_e": [dict(fill(i, -1.0), admission_era=("adm_A" if i < 3 else "adm_B")) for i in range(1, 5)]}
        arm_rows = {(str(i), a): arm_row(i, a, -0.5, -0.5) for i in range(1, 5) for a in rr.STOP_ARMS}
        out = rr.arm_lens("stop", fills_by_era, arm_rows, "era_e")
        assert set(out) == set(rr.STOP_ARMS) and all(v["verdict"] == "WATCH" for v in out.values())
        cells = rr.admission_cells("stop", fills_by_era, arm_rows)
        assert {(c["admission_era"], c["n"]) for c in cells if c["arm"] == "stop_orb_low"} == {("adm_A", 2), ("adm_B", 2)}

    def test_a_propose_needs_one_admission_era_with_ten_on_its_own(self):
        """§1.3 / D5: 12 winning fills split 7 / 5 across two admission eras is WATCH (pooled to reach 10); 12 in one
        admission era is PROPOSE."""
        arm_rows = {(str(i), "stop_orb_low"): arm_row(i, "stop_orb_low", 0.0 + 0.01 * i, 0.0 + 0.01 * i) for i in range(1, 13)}
        split = {"era_e": [dict(fill(i, -1.0), admission_era=("adm_A" if i <= 7 else "adm_B")) for i in range(1, 13)]}
        res = rr.arm_lens("stop", split, arm_rows, "era_e")["stop_orb_low"]
        assert res["verdict"] == "WATCH" and "demoted" in res["why"] and "adm_A pre-11-04 n 7" in res["why"]
        one = {"era_e": [dict(fill(i, -1.0), admission_era="adm_A") for i in range(1, 13)]}
        assert rr.arm_lens("stop", one, arm_rows, "era_e")["stop_orb_low"]["verdict"] == "PROPOSE"

    def test_era_starts_follow_rule_eras_dated_record(self, monkeypatch):
        """The safeguard-void window starts where rule_eras says the current era starts; a moved record moves it."""
        assert rr.era_start_for("era_e", date(2026, 1, 1)) == date(2026, 10, 13)
        assert rr.era_start_for("era_c", date(2026, 1, 1)) == date(2026, 8, 16)
        assert rr.era_start_for("bp1", date(2026, 10, 31)) == date(2026, 10, 31)          # no dated record -> the fallback
        monkeypatch.setattr(rr, "exit_era_start", lambda label: date(2030, 1, 1))
        assert rr.era_start_for("era_e", date(2026, 1, 1)) == date(2030, 1, 1)

    def test_regime_table_names_thin_cells(self):
        fills_by_era = {"era_e": [fill(1, -1.0), dict(fill(2, -1.0), live_actual=arm_row(2, "live_actual", -1.0, -1.0, regime="Choppy"))]}
        arm_rows = {(str(i), "stop_orb_low"): arm_row(i, "stop_orb_low", 0.0, 0.0) for i in (1, 2)}
        rows = [c for c in rr.regime_table(fills_by_era, arm_rows) if c["arm"] == "stop_orb_low"]
        assert {(c["regime"], c["n"], c["thin"]) for c in rows} == {("Bull", 1, True), ("Choppy", 1, True)}


# ── §3 descriptives ────────────────────────────────────────────────────────────────────────────
class TestDescriptives:
    def test_runner_shape_partial_then_breakeven_needs_both_bounds(self):
        """Finding 6a: |stop fill - entry| <= 0.05R — a stop filled at +5R is a trailed winner, not a give-back."""
        assert rr.runner_shapes(trade(exits=legs(("partial_profit", 116), ("stop_hit", 100.05))))["partial_breakeven"] is True
        assert rr.runner_shapes(trade(exits=legs(("partial_profit", 116), ("stop_hit", 110))))["partial_breakeven"] is False
        assert rr.runner_shapes(trade(exits=legs(("partial_profit", 116), ("stop_hit", 97.5))))["partial_breakeven"] is False
        assert rr.runner_shapes(trade(exits=legs(("stop_hit", 100))))["partial_breakeven"] is False

    def test_runner_shape_armed_breakeven_is_keyed_on_the_orb_frame_peak_not_a_partial_leg(self):
        """Finding 6b: eras D/E give the runner back with NO partial leg (breakeven armed at +3R, stopped at entry).
        +3R is in the ORB frame (entry + 3 x (entry - ORB low) = 103); sell_discipline's peak_r is hard-stop-frame
        (103 -> 1.5R), so the record's peak_price is compared with the arm price."""
        t = trade(exits=legs(("stop_hit", 100.0)))
        armed = rr.runner_shapes(t, {"peak_price": "103.2", "peak_r": "1.6"}, arm_row(1, "live_actual", 0.0, breakeven_arm_r="3"))
        assert armed["armed_breakeven"] is True and armed["partial_breakeven"] is False and armed["arm_price"] == pytest.approx(103.0)
        assert rr.runner_shapes(t, {"peak_price": "102.5"}, arm_row(1, "live_actual", 0.0, breakeven_arm_r="3"))["armed_breakeven"] is False
        assert rr.runner_shapes(t, {"peak_price": "103.2"}, None)["armed_breakeven"] is True        # no row: the era's arm via rule_eras.exit_rules_as_of (era E magna53 -> 3)
        assert rr.runner_shapes(trade(exits=legs(("stop_hit", 98))), {"peak_price": "103.2"}, None)["armed_breakeven"] is False

    def test_stopped_then_ran_reads_only_a_real_stop_leg(self):
        t = trade(exits=legs(("stop_hit", 98)), closed_at="2026-10-22 19:30:00+00")
        bars = [{"trade_date": f"2026-10-{23 + i:02d}", "high_price": "103", "low_price": "99"} for i in range(5)]
        assert rr.stopped_then_ran(t, {"AAA": bars}) is False
        bars[3]["high_price"] = "104.5"
        assert rr.stopped_then_ran(t, {"AAA": bars}) is True
        assert rr.stopped_then_ran(t, {"AAA": bars[:3]}) is None
        assert rr.stopped_then_ran(trade(exits=legs(("gap_through", 95))), {"AAA": bars}) is None   # never a leg reason

    def test_post_exit_high_in_r(self):
        t = trade(closed_at="2026-10-22 19:30:00+00")
        bars = [{"trade_date": f"2026-11-{1 + i:02d}", "high_price": str(100 + i), "low_price": "99"} for i in range(10)]
        assert rr.post_exit_high_r(t, {"AAA": bars}) == pytest.approx((109 - 100) / 2)
        assert rr.post_exit_high_r(t, {"AAA": bars[:9]}) is None

    def test_partial_and_exit_descriptives(self):
        trades = [trade(id=1, partial_taken="t", entry_shares="2", total_pnl="40",
                        exits=legs(("partial_profit", 116, 1), ("stop_hit", 100, 1))),
                  trade(id=2, total_pnl="-20", exits=legs(("stop_hit", 98)))]
        sd = {"1": {"capture_pct": "0.5", "giveback_r": "4", "hold_trading_days": "6", "peak_r": "8", "peak_price": "116", "stop_pct": "2", "stop_per_adr": "0.4"},
              "2": {"capture_pct": "", "giveback_r": "0.5", "hold_trading_days": "1", "peak_r": "0.4", "peak_price": "100.8", "stop_pct": "2", "stop_per_adr": "0.5"}}
        p = rr.partial_descriptives(trades, sd)
        assert p["partial_fired"] == 1 and p["runner_shape_partial"] == 1 and p["runner_shape_armed"] == 1 and p["shares_le_2"] == 1
        la = {"1": arm_row(1, "live_actual", 2.0, 2.0), "2": arm_row(2, "live_actual", -1.0, -1.0)}
        e = rr.exit_descriptives(trades, sd, {}, la)
        assert e["reasons"] == {"stop_hit": 2} and e["hold_days_median"] == 3.5 and e["stop_per_adr_median"] == 0.45
        assert e["rcap_sum"] == pytest.approx(1.0) and e["disappoints"] is False

    def test_disappoints_is_capped_dollar_r_not_trade_r(self):
        """Finding 11: the plan and the 11-06 fact use capped-dollar R; without a recorder row it is n/a."""
        t = trade(id=3, total_pnl="40")                                       # the trade's own R = +2.0
        la = {"3": arm_row(3, "live_actual", 2.0, -0.3)}                     # its capped-dollar R = -0.3
        assert rr.exit_descriptives([t], {}, {}, la)["disappoints"] is True
        assert rr.exit_descriptives([t], {}, {}, {})["disappoints"] is None

    def test_slippage_counts_a_null_fill_vs_trigger_apart(self):
        """Finding 8: a NULL fill_vs_trigger_pct was read as a <= 1% fill."""
        fills = [{"fill_vs_trigger_pct": "2.0", "live_rcap": "-1"}, {"fill_vs_trigger_pct": "1.5", "live_rcap": "-0.5"},
                 {"fill_vs_trigger_pct": "3.0", "live_rcap": "-1"}, {"fill_vs_trigger_pct": "0.2", "live_rcap": "2"},
                 {"fill_vs_trigger_pct": "", "live_rcap": "-5", "real_risk_vs_trigger_risk": "1.2"}]
        s = rr.slippage_test(fills)
        assert s["null_n"] == 1 and s["n"] == 4 and s["under_sum"] == 2 and s["over_1pct"] == 3 and s["verdict"] == "WATCH"
        assert s["real_risk_median"] == 1.2
        assert rr.slippage_test(fills[:2] + fills[3:])["verdict"] == "CAN'T TELL"

    def test_fill_minute_histogram(self):
        h = rr.fill_minute_histogram([trade(filled_at="2026-10-20 13:31:05+00"), trade(filled_at="2026-10-20 13:31:40+00"), trade(filled_at="")])
        assert h == {"09:31": 2, "unknown": 1}


# ── §4 the tail ────────────────────────────────────────────────────────────────────────────────
class TestTail:
    def test_tail_reads_the_real_trade_with_the_full_fields_and_is_never_gated_by_fidelity(self):
        big = trade(id=1, ticker="WIN", total_pnl="146", exits=legs(("partial_profit", 116, 3), ("sma_trail_stop", 112, 7)),
                    closed_at="2026-10-22 19:30:00+00")  # R = 146 / (2 x 10) = 7.3
        bad = trade(id=2, ticker="GAP", total_pnl="-32")          # R = -1.6
        mid = trade(id=3, ticker="MID", total_pnl="10")
        bug = trade(id=4, ticker="BUG", total_pnl="200", pnl_attribution="bug")
        fid = {"1": {"pass": False, "cls": "whole_share", "via": None}}
        arm_rows = {("1", "fill_facts"): {"fill_vs_trigger_pct": "0.4", "real_risk_vs_trigger_risk": "1.02"},
                    ("1", "live_actual"): arm_row(1, "live_actual", 7.3, admission_era="adm_Z")}
        bars = [{"trade_date": f"2026-11-{1 + i:02d}", "high_price": "120", "low_price": "99"} for i in range(10)]
        out = rr.tails([big, bad, mid, bug], {"1": {"peak_r": "9.1", "capture_pct": "0.8", "peak_hold_day": "5"}}, fid,
                       arm_rows=arm_rows, daily={"WIN": bars}, labels={("WIN", "2026-10-20"): "his EP"})
        w = out["winners"][0]
        assert [r["ticker"] for r in out["winners"]] == ["WIN"] and w["fidelity"] is False and w["fidelity_cls"] == "whole_share"
        assert w["fill_minute"] == "09:31" and w["fill_vs_trigger_pct"] == 0.4 and w["peak_session"] == 5
        assert [lg["reason"] for lg in w["exit_legs"]] == ["partial_profit", "sma_trail_stop"] and w["exit_legs"][0]["price_r"] == pytest.approx(8.0)
        assert w["admission_era"] == "adm_Z" and w["label"] == "his EP" and w["post_exit_high_r"] == pytest.approx(10.0)
        assert [r["ticker"] for r in out["losers"]] == ["GAP"]


# ── §6 missed-by-slots ─────────────────────────────────────────────────────────────────────────
class TestMissedBySlots:
    def _bars(self, day, highs_lows):
        return [{"trade_date": date.fromordinal(date.fromisoformat(day).toordinal() + i + 1).isoformat(),
                 "high_price": str(h), "low_price": str(lo)} for i, (h, lo) in enumerate(highs_lows)]

    def test_width_rule_is_fraction_vs_fraction(self):
        """Finding 5: width = (level - stop) / level (breakout_v1_entry.py:530); the old test w <= adr20 x price let a
        $2 width through against a 0.05 'fraction' x $50."""
        ok = {"ticker": "ZZZ", "break_price": 50, "stop": 48, "width": 0.04, "adr20": 0.05}
        wide = {"ticker": "WID", "break_price": 50, "stop": 47, "width": 0.06, "adr20": 0.05}
        assert rr.width_ok(ok) is True and rr.width_ok(wide) is False
        assert rr.width_ok({"width": 2, "adr20": 0.05, "break_price": 50}) is False    # a dollar width can never pass now
        assert rr.width_ok({"width": 0.04}) is None

    def test_records_count_bad_json(self):
        audit = [{"id": "1", "event_type": rr.MISSED_EVENT, "detail": json.dumps({"ticker": "ZZZ", "day": "2026-11-10", "break_price": 50, "stop": 48, "width": 0.04, "adr20": 0.05})},
                 {"id": "2", "event_type": rr.MISSED_EVENT, "detail": "{not json"},
                 {"id": "3", "event_type": rr.HOLD_EVENT, "detail": json.dumps({"state": "slots_full"})}]
        recs, bad = rr.missed_records(audit)
        assert [r["ticker"] for r in recs] == ["ZZZ"] and bad == 1

    def test_proxy_walk(self):
        day = date(2026, 11, 10)
        plus = rr.missed_proxy_walk(50, 48, day, self._bars("2026-11-10", [(51, 49), (55, 50)] + [(52, 50)] * 8))
        assert plus["mature"] and plus["plus2r_before_stop"] is True and plus["mfe_r"] == pytest.approx(2.5)
        both = rr.missed_proxy_walk(50, 48, day, self._bars("2026-11-10", [(55, 47)] + [(55, 50)] * 9))
        assert both["plus2r_before_stop"] is False
        assert not rr.missed_proxy_walk(50, 48, day, self._bars("2026-11-10", [(51, 49)] * 4))["mature"]

    def test_missed_vs_seated_and_absence(self):
        w_hit = {"mature": True, "plus2r_before_stop": True, "mfe_r": 3.0}
        w_miss = {"mature": True, "plus2r_before_stop": False, "mfe_r": 0.5}
        missed = [{"walk": w_hit}] * 3 + [{"walk": {"mature": False}}]
        seated = [{"walk": w_miss, "realized_r": -1.0}] * 3
        assert rr.missed_vs_seated(missed, seated)["verdict"] == "WATCH"
        assert rr.missed_vs_seated(missed * 4, seated)["verdict"] == "PROPOSE"
        assert rr.missed_vs_seated(missed[:1], seated)["verdict"] == "CAN'T TELL"
        audit = [{"event_type": rr.HOLD_EVENT, "detail": json.dumps({"state": "slots_full"})},
                 {"event_type": rr.ENTRY_DAY_EVENT, "detail": "{}"}, {"event_type": rr.UNREADABLE_EVENT, "detail": "{}"}]
        obs = rr.absence_observables(audit, 2, 5, "on", {"strategy_id": "breakout_v1", "enabled": "t", "phase": "paper"})
        assert obs["slots_full_holds"] == 1 and obs["entry_day_rows"] == 1 and obs["unreadable_rows"] == 1
        assert obs["strategy_enabled"] is True and obs["strategy_phase"] == "paper" and obs["env_default"] == "not captured"
        assert rr.absence_sentence(obs, 0).startswith("1 hold rows, none broke out while held") and "unreadable" in rr.absence_sentence(obs, 0)
        assert "did not run" in rr.absence_sentence(dict(obs, list_nights=0), 0)
        assert "recorder did not run" in rr.absence_sentence(dict(obs, entry_day_rows=0), 0)   # no entry_day row != nothing missed
        assert rr.absence_sentence(obs, 1) == "missed 1 of 1 held rows"

    def test_breakout_buy_point_fill_vs_level_decisions_and_thirds(self):
        l3 = [trade(id=9, ticker="BPP", account_mode="paper", signal_type="breakout_v1", exit_rule="breakout_pp", alert_date="2026-11-04",
                    entry_price="101", hard_stop="99", orb_low="", exits=legs(("partial_profit", 105.5, 3), ("stop_hit", 101, 7))),
              trade(id=10, ticker="BQQ", account_mode="paper", signal_type="breakout_v1", exit_rule="breakout_pp", alert_date="2026-11-04",
                    entry_price="50", hard_stop="49", orb_low="", exits=legs(("partial_profit", 50.8, 3), ("stop_hit", 50, 7)))]
        blist = [{"scan_date": "2026-11-03", "ticker": "BPP", "level": "100"}]
        audit = [{"event_type": rr.FILL_STOP_EVENT, "detail": json.dumps({"trade_id": 9, "decision": "lower"})}]
        b = rr.breakout_buy_point(l3, blist, audit)
        assert b["fill_vs_level_median"] == pytest.approx(1.0) and b["decisions"] == {"lower": 1, "unchecked": 1}
        assert b["thirds"] == {"+2R": 1, "session_3": 1}


# ── §3 stop (c) ────────────────────────────────────────────────────────────────────────────────
class TestStopTooWide:
    def test_fisher_is_two_sided_as_the_yaml_read_it(self):
        """Finding 3 / D2: 4 of 11 vs 17 of 25 -> p 0.141 (two-sided; the YAML's own 09-16 reading = CANNOT TELL).
        One-sided gives 0.080 and would have said KEEP."""
        p = rr.fisher_exact_two_sided(4, 7, 17, 8)
        assert p == pytest.approx(0.141, abs=0.002) and p > 0.10
        assert rr.fisher_exact_two_sided(0, 10, 10, 0) < 1e-4 and rr.fisher_exact_two_sided(5, 5, 5, 5) == pytest.approx(1.0)
        rej = [12.0] * 4 + [1.0] * 7
        adm = [12.0] * 17 + [1.0] * 8
        m = rr.stop_too_wide_matrix(rej, adm)
        # finding 6 (re-challenge): CANNOT TELL is the ladder's CAN'T TELL — never NOTHING ("the current rule is best")
        assert m["matrix"] == "CANNOT TELL" and m["p"] == pytest.approx(0.141, abs=0.002) and m["verdict"] == "CAN'T TELL"

    def test_matrix(self):
        assert rr.stop_too_wide_matrix([12, 11, 15], [5, 4, 3])["verdict"] == "WATCH"
        keep = rr.stop_too_wide_matrix([1] * 10, [12] * 10)
        assert keep["matrix"] == "KEEP" and keep["p"] < 0.10 and keep["verdict"] == "NOTHING"
        split = rr.stop_too_wide_matrix([12, 1, 1], [5, 5, 5])
        assert split["matrix"] == "CANNOT TELL" and split["verdict"] == "CAN'T TELL"
        assert rr.stop_too_wide_matrix([12, 11], [5, 4, 3])["verdict"] == "CAN'T TELL"
        assert rr.stop_too_wide_matrix([12] * 10, [5] * 10)["verdict"] == "PROPOSE"

    def _daily(self, ticker, start, n, open_=100, hi=100, lo=99):
        return [{"ticker": ticker, "trade_date": date.fromordinal(date.fromisoformat(start).toordinal() + i).isoformat(),
                 "open_price": str(open_), "high_price": str(hi), "low_price": str(lo), "close": str(open_), "volume": "1"} for i in range(n)]

    def test_rejected_mfe_comes_from_daily_bars_never_the_fraction_column(self):
        """Finding 2: max_high_5d is a FRACTION (0.12 = +12%) whose window includes day 0; read as a price it made
        every rejected name -99.9%. The section must ignore it and score both cohorts on the same raw bars."""
        bars = self._daily("Q", "2026-10-01", 8)
        bars[3]["high_price"] = "111"   # d+3
        daily = {"Q": bars}
        assert rr.mfe_5d_pct("Q", date(2026, 10, 1), daily) == pytest.approx(11.0)
        assert rr.mfe_5d_pct("Q", date(2026, 10, 5), daily) is None
        skip = {"ticker": "Q", "alert_date": "2026-10-01", "open_d0": "100", "max_high_5d": "0.12"}   # the fraction prod writes
        sec = rr.stop_too_wide_section([skip, skip, skip], [{"ticker": "Q", "alert_date": "2026-10-01", "account_mode": "live"}] * 3, daily)
        assert sec["rejected_n"] == 3 and sec["rejected_median"] == pytest.approx(11.0) and sec["admitted_median"] == pytest.approx(11.0)
        assert sec["admitted_modes"] == {"live": 3} and list(sec["admitted_admission_eras"]) == ["adm_2026-08-31_extension_cap_50_slot_rank_rs"]
        assert sec["rejected_unscored"] == 0


# ── §3 selection ───────────────────────────────────────────────────────────────────────────────
class TestSelection:
    def test_labels_join_alerts_and_exclude_declared_abstentions(self):
        """Finding 7: 'never alerted' needs mi_ep_alerts; CHPT 09-03 is a declared abstention, not a monthly WATCH."""
        trades = [trade(id=1, ticker="PLTR", alert_date="2026-08-04", total_pnl="60")]
        skips = [{"ticker": "HTFL", "alert_date": "2026-08-14", "skip_reason": "setup:stop_too_wide"}]
        alerts = [{"ticker": "ABNB2", "alert_date": "2026-08-07"}]
        sel = rr.selection_labels(trades, skips, [("PLTR", "2026-08-04"), ("HTFL", "2026-08-14"), ("ABNB2", "2026-08-07"),
                                                  ("NEVR", "2026-08-09"), ("CHPT", "2026-09-03")],
                                  alerts, {("CHPT", "2026-09-03")})
        assert [s["did"] for s in sel] == ["traded", "skipped", "alerted, no trade row", "never alerted", "abstention"]
        assert rr.selection_verdict(sel) == ("WATCH", 3)

    def test_under_three_missed_labels_is_cannot_tell_not_watch(self):
        one = [{"did": "traded"}, {"did": "never alerted"}]
        assert rr.selection_verdict(one) == ("CAN'T TELL", 1)
        assert rr.selection_verdict([{"did": "traded"}]) == ("NOTHING", 0)
        assert rr.selection_verdict([{"did": "abstention"}]) == ("CAN'T TELL", 0)

    def test_declared_abstentions_come_from_the_fixture(self):
        abst = rr.declared_abstentions()
        assert ("CHPT", "2026-09-03") in abst and ("ABNB", "2026-08-07") in abst
        assert not any(tk == "TDIC" for tk, _ in abst)          # evidence-labelled, not operator-labelled

    def test_breakout_grades_come_from_his_chart_sheets(self):
        """D4: tests/fixtures/breakout_list_grades.py (good / ok / no / conditional), not mi_breakout_v1_grades."""
        g = rr.breakout_grades_fixture()
        assert len(g) >= 12 and {x["grade"] for x in g} <= {"good", "ok", "no", "conditional"}
        assert any(x["ticker"] == "IAG" and x["list_date"] == "2026-11-06" and x["grade"] == "good" for x in g)
        assert not (CAPTURE / "breakout_grades.sql").exists()
        grades = [{"list_date": "2026-11-02", "ticker": "X", "grade": "no"}, {"list_date": "2026-11-05", "ticker": "X", "grade": "good"}]
        assert rr.breakout_grade_for("X", date(2026, 11, 4), grades) == "no"
        assert rr.breakout_grade_for("X", date(2026, 11, 6), grades) == "good"
        l3 = [trade(id=i, ticker="X", account_mode="paper", signal_type="breakout_v1", exit_rule="breakout_pp", alert_date="2026-11-04",
                    total_pnl="-20") for i in range(3)] + [trade(id=7, ticker="W", account_mode="paper", signal_type="breakout_v1",
                                                                exit_rule="breakout_pp", alert_date="2026-11-06", total_pnl="60")]
        bs = rr.breakout_selection(l3, grades + [{"list_date": "2026-11-05", "ticker": "W", "grade": "good"}])
        assert bs["low_n"] == 3 and bs["high_n"] == 1 and bs["verdict"] == "WATCH"


# ── §7 safeguard voids + predicates verbatim ──────────────────────────────────────────────────
class TestFoldedReviews:
    def test_safeguard_transitions_reuse_the_yaml_exclusion_list(self):
        rows = [{"safeguard": "drawdown_breaker", "account_mode": "live", "state": "on", "last_transition_at": "2026-11-10 14:00:00+00"},
                {"safeguard": "magna53_open_below_floor", "account_mode": "global", "state": "on", "last_transition_at": "2026-11-03 15:05:28+00"},
                {"safeguard": "theme_birth_gate", "account_mode": "paper", "state": "on", "last_transition_at": "2026-11-10 14:00:00+00"},
                {"safeguard": "some_live_toggle", "account_mode": "live", "state": "off", "last_transition_at": "2026-11-10 14:00:00+00"},
                {"safeguard": "old_toggle", "account_mode": "live", "state": "off", "last_transition_at": "2026-10-01 14:00:00+00"}]
        voids = rr.safeguard_transitions_check(rows, date(2026, 10, 13))
        assert len(voids) == 1 and voids[0].startswith("some_live_toggle|live")
        import yaml
        reg = yaml.safe_load(YAML.read_text(encoding="utf-8"))["reviews"]
        sql = next(e for e in reg if e["review_id"] == "runner_rule_sweep_recut")["predicate_sql"]
        for name in rr.SAFEGUARD_VOID_EXCLUDED:
            assert f"'{name}'" in sql
        assert rr.SAFEGUARD_ANSWERED_THROUGH in sql

    def test_predicates_sql_is_the_yaml_verbatim(self):
        """Finding 12: the committed capture file equals what the generator emits from the YAML, and every embedded
        body IS the YAML's predicate_sql with only its trailing semicolon (and what follows it) removed."""
        emitted = rr.emit_predicates_sql(YAML)
        assert (CAPTURE / "predicates.sql").read_text() == emitted
        bodies = rr.predicate_bodies_from_yaml(YAML)
        assert set(bodies) == set(rr.FOLDED_REVIEWS)
        for rid, body in bodies.items():
            assert body in emitted, rid
            assert "SELECT" in body and not body.rstrip().endswith(";"), rid
        # the runner-gate and the +40 safeguard arm the old file dropped are present
        assert "LEAST(" in bodies["exit_tune_cohort_review"] and "peak_adr >= 1.5" in bodies["exit_tune_cohort_review"]
        assert "+ 40 * (SELECT count(*) FROM mi_safeguard_state" in bodies["runner_rule_sweep_recut"]
        # a `;` inside a comment is text, not a terminator
        assert rr.strip_trailing_semicolon("-- a; b\nSELECT 1\n-- c") == "-- a; b\nSELECT 1\n-- c"
        assert rr.strip_trailing_semicolon("SELECT 1;\n  -- lag") == "SELECT 1"


# ── §9 render + end to end on a temp run dir ───────────────────────────────────────────────────
def _write_csv(path: Path, rows: list[dict]):
    fields: list[str] = []
    for r in rows:
        fields += [k for k in r if k not in fields]
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


class TestRenderAndDriver:
    def test_render_first_line_is_the_answer_and_action_is_always_present(self):
        rep = {"run_date": "2026-11-29", "answer": "Nothing beats what we run; action: none.", "window_start": "2026-08-16",
               "window_end": "2026-11-29", "population": {("L1", "era_e"): {"window": 3, "carried": 0, "open": 1, "excluded": [], "no_r": [], "flagged": []}},
               "lens_rows": [{"lens": "stop: stop_orb_low", "where": "L1 / era_e", "n": 3, "reading": "era_e WON on n 3", "verdict": "WATCH"}],
               "tails": {"winners": [], "losers": []}, "missed": {}, "folded": [], "action": "none", "fidelity": None, "window_trades": []}
        md = rr.render(rep)
        assert md.splitlines()[2].startswith("**Nothing beats")
        assert "**Action: none**" in md and "| 3 |" in md and "Total" not in md

    def _daily(self, ticker, start, n, open_=100, hi=103, lo=99):
        return [{"ticker": ticker, "trade_date": date.fromordinal(date.fromisoformat(start).toordinal() + i).isoformat(),
                 "open_price": str(open_), "high_price": str(hi), "low_price": str(lo), "close": str(open_), "volume": "1"} for i in range(n)]

    def test_build_report_end_to_end_reaches_every_lens(self, tmp_path):
        run = tmp_path / "runs" / "2026-11-29"
        (run / "data").mkdir(parents=True)
        trades = [trade(id=i, ticker=f"T{i}", total_pnl=str(-20 if i < 3 else 150), closed_at="2026-11-12 20:00:00+00",
                        alert_date=("2026-11-05" if i == 3 else "2026-10-20"),
                        exits=legs(("stop_hit", 98)) if i < 3 else legs(("sma_trail_stop", 115, 10))) for i in range(1, 4)]
        trades.append(trade(id=9, ticker="BPP", account_mode="paper", signal_type="breakout_v1", exit_rule="breakout_pp",
                            alert_date="2026-11-04", total_pnl="-20", closed_at="2026-11-06 20:00:00+00", filled_at="2026-11-04 15:00:00+00"))
        _write_csv(run / "data" / "trades.csv", trades)
        cf = []
        for i in range(1, 4):
            r = -1.0 if i < 3 else 7.5
            cf += [arm_row(i, "live_actual", r, r), arm_row(i, "live_replay", r, r)]
            cf += [arm_row(i, a, -0.5 if i < 3 else 7.5, -0.5 if i < 3 else 7.5) for a in rr.ALL_ARMS]
            cf.append(arm_row(i, rr.FILL_FACTS, "", outcome="unscoreable", fill_vs_trigger_pct=str(0.3 * i), real_risk_vs_trigger_risk="1.01"))
        _write_csv(run / "data" / "cf_arms.csv", cf)
        _write_csv(run / "data" / "sell_discipline.csv", [{"trade_id": "3", "peak_r": "8.0", "peak_price": "116", "capture_pct": "0.94", "hold_trading_days": "7",
                                                            "stop_pct": "2", "stop_per_adr": "0.4", "giveback_r": "0.5", "peak_hold_day": "4"}])
        daily = []
        for tk in ("T1", "T2", "T3", "BPP", "ZZZ", "PENG", "ADM"):
            daily += self._daily(tk, "2026-10-01", 60)
        _write_csv(run / "data" / "daily_bars.csv", daily)
        _write_csv(run / "data" / "skips_window.csv", [{"id": "50", "ticker": "PENG", "alert_date": "2026-10-07", "account_mode": "live",
                                                         "signal_type": "magna53", "status": "skipped", "skip_reason": "setup:stop_too_wide", "ep_score": "70", "created_at": ""}])
        _write_csv(run / "data" / "skips_stop_too_wide.csv", [{"id": "50", "ticker": "PENG", "alert_date": "2026-10-07", "account_mode": "live", "ep_score": "70",
                                                                "skip_reason": "setup:stop_too_wide", "orb_high": "", "orb_low": "", "atr_14": "", "open_d0": "100",
                                                                "close_d0": "101", "ret_1d": "", "ret_5d": "", "ret_20d": "", "max_high_5d": "0.12", "max_high_20d": ""}])
        _write_csv(run / "data" / "admitted_magna53.csv", [{"id": str(100 + i), "ticker": "ADM", "alert_date": "2026-10-07", "account_mode": "paper" if i else "live",
                                                             "status": "closed", "filled_at": "2026-10-07 13:31:00+00"} for i in range(4)])
        _write_csv(run / "data" / "ep_alerts.csv", [{"ticker": "NEVR", "alert_date": "2026-10-09", "ep_score": "70", "score_tier": "HIGH", "detected_at": ""}])
        _write_csv(run / "data" / "breakout_list.csv", [{"scan_date": "2026-11-03", "ticker": "BPP", "level": "100", "vol_bar": "1", "adr20": "0.05",
                                                         "rs_best": "90", "close": "99", "list_rank": "1", "order_score": "0.9"}])
        _write_csv(run / "data" / "strategy_toggles.csv", [{"safeguard": "breakout_v1_paper", "account_mode": "paper", "state": "on", "last_transition_at": ""}])
        _write_csv(run / "data" / "strategies.csv", [{"strategy_id": "breakout_v1", "name": "b", "family": "cb", "phase": "paper", "enabled": "t",
                                                      "live_real_enabled": "f", "signal_type": "breakout_v1", "max_concurrent_positions": "", "profit_trigger_r": "", "breakeven_arm_r": ""}])
        _write_csv(run / "data" / "safeguard_transitions.csv", [{"safeguard": "x_live", "account_mode": "live", "state": "on", "last_transition_at": "2026-11-10 14:00:00+00"}])
        _write_csv(run / "data" / "audit_breakout.csv", [
            {"id": "1", "created_at": "", "event_type": rr.HOLD_EVENT, "summary": "", "detail": json.dumps({"ticker": "ZZZ", "state": "slots_full"})},
            {"id": "2", "created_at": "", "event_type": rr.MISSED_EVENT, "summary": "",
             "detail": json.dumps({"ticker": "ZZZ", "day": "2026-11-04", "break_price": 100, "stop": 98, "width": 0.02, "adr20": 0.05})},
            {"id": "3", "created_at": "", "event_type": rr.ENTRY_DAY_EVENT, "summary": "", "detail": "{}"},
            {"id": "4", "created_at": "", "event_type": rr.FILL_STOP_EVENT, "summary": "", "detail": json.dumps({"trade_id": 9, "decision": "keep"})}])
        _write_csv(run / "data" / "predicates.csv", [{"review": "stop_too_wide_outcome_cohort", "n": "1"}, {"review": "bracket_geometry_variants_parked", "n": "3"}])
        _write_csv(run / "data" / "audit_recorder.csv", [{"id": "7", "created_at": "2026-11-27 23:04:10+00", "event_type": rr.RECORDER_RUN_EVENT, "summary": "3 fill(s)"}])
        _write_csv(run / "data" / "legacy_paper_count.csv", [{"legacy_paper_closed_in_window": "0"}])
        _write_csv(run / "data" / "pre_window_closes.csv", [{"account_mode": "live", "signal_type": "magna53", "n": "2"}])
        rep = rr.build_report(run, date(2026, 11, 29), rr.FIRST_WINDOW_START,
                              labelled=[("T1", "2026-10-20"), ("NEVR", "2026-10-09"), ("CHPT", "2026-09-03")],
                              abstentions={("CHPT", "2026-09-03")}, grades=[{"list_date": "2026-11-03", "ticker": "BPP", "grade": "good"}])
        assert rep["population"][("L1", "era_e")]["window"] == 3 and rep["population"][("L3", "bp1")]["window"] == 1
        assert rep["fidelity"] == {"n": 3, "pass": 3, "stored": 3, "reweighted": 0, "old_pass": 3, "classes": {}}
        assert rep["recorder_gaps"]["era_e"] == {"fills": 3, "with_rows": 3, "settled_pairs": 3, "gaps": [], "unsettled": []}
        assert rep["not_captured"] == [] and rep["recorder_runs"]["ran"] == 1 and rep["recorder_runs"]["last_run"] == date(2026, 11, 27)
        assert [w["ticker"] for w in rep["tails"]["winners"]] == ["T3"] and rep["tails"]["winners"][0]["best_arm"]
        lenses = {r["lens"] for r in rep["lens_rows"]}
        for needle in ("stop: stop_orb_low", "partials: harvest_t3", "exits: trail_pivot_swing", "buy_point: entry_first_hour_bar",
                       "selection: his EP labels", "selection: his breakout grades (chart sheets)", "buy point: fill vs trigger",
                       "stop: stopped out, then ran", "partials: fired / kept", "exits: how trades ended", "stop: the stop-too-wide filter",
                       "breakout: missed by slots vs seated", "buy point: fill vs list level / fill-stop decision / thirds"):
            assert needle in lenses, needle
        assert all(r["verdict"] in rr.VERDICTS + ("descriptive",) or r["verdict"].startswith("context") for r in rep["lens_rows"])
        # D5: the era-E lens lines carry the pre/post 11-04 split
        stop_line = next(r for r in rep["lens_rows"] if r["lens"] == "stop: stop_orb_low")
        assert "pre-11-04 2 / post 1" in stop_line["reading"]
        # the absence rule reads the observables, not a hard-wired zero
        assert "did not run" not in rep["missed_absence"] and "missed 1 of 1" in rep["missed_absence"]
        assert rep["missed"]["missed_n"] == 1 and rep["missed"]["seated_n"] == 1 and rep["missed"]["seated_all"] == 1 and rep["missed"]["bad_json"] == 0
        assert rep["breakout_selection"]["by_grade"] == {"good": 1}
        # finding 4: the admitted control is the captured cohort, not the L1 closed trades
        assert rep["stop_too_wide"]["rejected_n"] == 1 and rep["stop_too_wide"]["admitted_n"] == 4
        assert rep["stop_too_wide"]["admitted_modes"] == {"live": 1, "paper": 3}
        # selection: the label join uses the alerts file and the abstention is not a miss
        sel = {s["ticker"]: s["did"] for s in rep["selection"]}
        assert sel == {"T1": "traded", "NEVR": "alerted, no trade row", "CHPT": "abstention"}
        assert next(r for r in rep["lens_rows"] if r["lens"] == "selection: his EP labels")["verdict"] == "CAN'T TELL"
        # finding 2 / 8: ALWAYS the five rows, in FOLDED_REVIEWS order; a review absent from predicates.csv is "not captured"
        assert [fr["review"] for fr in rep["folded"]] == list(rr.FOLDED_REVIEWS)
        folded = {fr["review"]: fr for fr in rep["folded"]}
        assert folded["bracket_geometry_variants_parked"]["n"] == "3" and folded["exit_tune_cohort_review"]["n"] == rr.NOT_CAPTURED
        assert folded["runner_rule_sweep_recut"]["verdict"] == "descriptive"
        assert folded["live_fill_counterfactuals_first_read_482"]["verdict"] == "WATCH"     # the stop arms WON on 3 (stop lens), trail arms too
        n_watch = sum(1 for r in rep["lens_rows"] if r.get("kind") == "arm" and r["verdict"] == "WATCH")
        assert n_watch == len(rr.ALL_ARMS)                                                     # every arm WON on n 3 in this fixture
        assert rep["answer"].startswith(f"{n_watch} arm(s) on watch (beat what we run, but on under 10 trades; nothing proposed); 0 did not beat it, 0 unreadable")
        assert rep["safeguard_voids"] and rep["safeguard_voids"][0].startswith("x_live|live")
        assert rep["pre_window_closes"] == {"live/magna53": "2"}
        assert len(rep["window_trades"]) == 4 and all("forensic_class" in r for r in rep["window_trades"])
        assert rep["legacy_paper_count"] == 0 and "stop_low_of_day = stop_orb_low on 3 of 3" in rep["out"]
        assert "regime " in rep["out"] and "admission mix L1 era_e" in rep["out"]
        md = rr.render(rep)
        (run / "review.md").write_text(md)
        assert (run / "review.md").read_text().startswith("# #720 monthly trade review — 2026-11-29")
        assert "Total" not in md and "Every closed trade in the window" in md and "Recorder coverage" in md
        manifest = rr.write_manifest(run, "2026-11-29T18:00:00-05:00")
        assert "trades.csv: rows 4 md5" in manifest

    def test_era_mismatch_stops_the_read(self, tmp_path):
        run = tmp_path / "r"
        (run / "data").mkdir(parents=True)
        _write_csv(run / "data" / "trades.csv", [trade(id=1)])
        _write_csv(run / "data" / "cf_arms.csv", [arm_row(1, "live_actual", 1.0, exit_era="era_d")])
        with pytest.raises(SystemExit):
            rr.build_report(run, date(2026, 11, 29), rr.FIRST_WINDOW_START, labelled=[], abstentions=set(), grades=[])


def test_every_capture_query_is_read_only():
    files = sorted(CAPTURE.glob("*.sql"))
    assert len(files) >= 14
    names = {p.name for p in files}
    for need in ("admitted_magna53.sql", "ep_alerts.sql", "strategies.sql", "pre_window_closes.sql", "predicates.sql", "audit_recorder.sql"):
        assert need in names, need
    for p in files:
        text = p.read_text()
        assert text.splitlines()[0].strip() == "SET default_transaction_read_only = on;", p.name
        assert ("\\copy (" in text or "COPY (" in text) and "TO STDOUT WITH CSV HEADER" in text, p.name
    assert "breakout_v1_entry_day" in (CAPTURE / "audit_breakout.sql").read_text()
    assert "live_fill_counterfactual_recorded" in (CAPTURE / "audit_recorder.sql").read_text()   # finding 10: the recorder's heartbeat
    admitted = "skip_reason IS NULL AND status NOT IN ('cancelled', 'skipped') AND filled_at IS NOT NULL AND alert_date >= DATE '2026-05-05'"
    assert admitted in (CAPTURE / "daily_bars.sql").read_text() and admitted in (CAPTURE / "admitted_magna53.sql").read_text()
    # finding 8 counts malformed missed-by-slots rows; a ::jsonb cast in the bars capture would abort on the first one
    assert "::jsonb" not in (CAPTURE / "daily_bars.sql").read_text()


def test_pinned_constants_match_the_plan():
    assert rr.FIRST_WINDOW_START == date(2026, 8, 16)
    assert rr.READABLE_MIN == 3 and rr.PROPOSE_MIN == 10
    assert rr.FIDELITY_ABS == 0.25 and rr.FIDELITY_REL == 0.10 and rr.SMALL_POSITION_SHARES == 3
    assert rr.TAIL_WIN_R == 4.0 and rr.TAIL_LOSS_R == -1.5 and rr.BREAKEVEN_TOL_R == 0.05
    assert rr.RECORDER_FIRST_SESSION == date(2026, 9, 4) and "**2026-09-04**" in PLAN.read_text()
    plan = PLAN.read_text()
    for needle in ("2026-08-16", "max(0.25, 0.10", "≥ +4R", "≤ −1.5R", "bp1", "CAN'T TELL", "PROPOSE", "two-sided",
                   "admitted_magna53.sql", "ep_alerts.sql", "strategies.sql", "pre_window_closes.sql", "review.out",
                   "breakout_list_grades.py", "must_not_miss_eps.py", "2026-11-04", "D1", "D7", "D10", "I16", "width ≤ adr20",
                   "NOT CAPTURED", "audit_recorder.sql", "charts support, never decide", "too few trades to read yet"):
        assert needle in plan, needle
    assert "max_high_5d" not in plan.split("## 3.")[1].split("## 4.")[0].replace("NEVER `mi_ep_missed_outcomes.max_high_5d`", "")


def test_the_five_yaml_entries_point_at_this_cadence_and_the_fidelity_bar_is_the_plans():
    """D6: each folded review's action_when_ready names PLAN #720's monthly review; the 482 read's 0.25R quote bar
    is replaced by the plan's."""
    import yaml
    reg = {e["review_id"]: e for e in yaml.safe_load(YAML.read_text(encoding="utf-8"))["reviews"]}
    for rid in rr.FOLDED_REVIEWS:
        act = reg[rid]["action_when_ready"]
        assert "#720" in act and "720_monthly_review_plan_2026-11-08.md" in act, rid
    one = reg["live_fill_counterfactuals_first_read_482"]["action_when_ready"]
    assert "more than 0.25R" not in one and "max(0.25R, 10%" in one


# ── the 2026-11-08 re-challenge: findings 1-10, one test each, every one RED on HEAD b3d0a215 ─────────────────
def _full_capture(run: Path, trades: list[dict], cf: list[dict], audit: list[dict] | None = None,
                  audit_recorder: list[dict] | None = None, predicates: list[dict] | None = None, skip: set[str] = frozenset()):
    """Every capture file the runner requires, minimal rows (the fixture the re-challenge probes lacked)."""
    (run / "data").mkdir(parents=True, exist_ok=True)
    daily = [{"ticker": tk, "trade_date": date.fromordinal(date(2026, 10, 1).toordinal() + i).isoformat(), "open_price": "100",
              "high_price": "103", "low_price": "99", "close": "100", "volume": "1"} for tk in {t["ticker"] for t in trades} for i in range(60)]
    files = {"trades": trades, "cf_arms": cf, "sell_discipline": [], "daily_bars": daily, "skips_window": [], "skips_stop_too_wide": [],
             "admitted_magna53": [], "ep_alerts": [], "breakout_list": [{"scan_date": "2026-11-03", "ticker": "BPP", "level": "100"}],
             "strategy_toggles": [{"safeguard": "breakout_v1_paper", "account_mode": "paper", "state": "on", "last_transition_at": ""}],
             "strategies": [{"strategy_id": "breakout_v1", "phase": "paper", "enabled": "t"}], "safeguard_transitions": [],
             "audit_breakout": audit if audit is not None else [{"id": "3", "created_at": "", "event_type": rr.ENTRY_DAY_EVENT, "summary": "", "detail": "{}"}],
             "audit_recorder": audit_recorder if audit_recorder is not None else [
                 {"id": "1", "created_at": "2026-11-27 23:04:10+00", "summary": "0 fill(s)",
                  "event_type": getattr(rr, "RECORDER_RUN_EVENT", "live_fill_counterfactual_recorded")}],
             "predicates": predicates if predicates is not None else [{"review": rid, "n": "0"} for rid in rr.FOLDED_REVIEWS],
             "legacy_paper_count": [{"legacy_paper_closed_in_window": "0"}], "pre_window_closes": []}
    required = getattr(rr, "REQUIRED_CAPTURES", None)          # absent on the pre-fix runner: the helper still writes every file
    assert required is None or set(files) == set(required), set(files) ^ set(required)
    headers = {"trades": list(trade().keys()), "cf_arms": list(arm_row(1, "live_actual", 0).keys()), "predicates": ["review", "n"],
               "sell_discipline": ["trade_id", "peak_r"], "skips_window": ["id", "ticker", "alert_date", "skip_reason"],
               "skips_stop_too_wide": ["id", "ticker", "alert_date"], "admitted_magna53": ["id", "ticker", "alert_date", "account_mode"],
               "ep_alerts": ["ticker", "alert_date"], "safeguard_transitions": ["safeguard", "account_mode", "state", "last_transition_at"],
               "pre_window_closes": ["account_mode", "signal_type", "n"], "audit_breakout": ["id", "created_at", "event_type", "summary", "detail"],
               "audit_recorder": ["id", "created_at", "event_type", "summary"]}
    for name, rows in files.items():
        if name in skip:
            continue
        if rows:
            _write_csv(run / "data" / f"{name}.csv", rows)
        else:
            (run / "data" / f"{name}.csv").write_text(",".join(headers[name]) + "\n")


def _report(run: Path, **kw):
    return rr.build_report(run, date(2026, 11, 29), rr.FIRST_WINDOW_START, labelled=[], abstentions=set(), grades=[], **kw)


class TestRechallenge1108:
    def test_f1_line_one_says_too_few_or_recorder_gap_never_nothing_beats_on_an_unread_month(self, tmp_path):
        """Finding 1: 'Nothing beats what we run' only when an ARM lens on the current era actually read NOTHING.
        Three era-E fills with no recorder rows inside the retry window -> 'too few trades to read yet'; the same
        three closed past the retry window -> 'recorder gap on 3 fill(s)'."""
        fresh = [trade(id=i, ticker=f"T{i}", closed_at="2026-11-27 20:00:00+00", total_pnl="-20", exits=legs(("stop_hit", 98))) for i in range(1, 4)]
        _full_capture(tmp_path / "fresh", fresh, [])
        rep = _report(tmp_path / "fresh")
        assert rep["answer"].startswith("too few trades to read yet") and "Nothing beats" not in rep["answer"]
        old = [dict(t, closed_at="2026-11-12 20:00:00+00") for t in fresh]
        _full_capture(tmp_path / "old", old, [])
        rep = _report(tmp_path / "old")
        assert rep["answer"].startswith("recorder gap on 3 fill(s)")
        # a count lens reading NOTHING (none of his labels missed) is not an arm reading NOTHING
        rows = [{"lens": "selection: his EP labels", "where": "L1", "n": 1, "reading": "x", "verdict": "NOTHING"},
                {"lens": "stop: stop_orb_low", "where": "L1 / era_e", "n": 0, "reading": "x", "verdict": "CAN'T TELL"}]
        assert not rr.answer_line(rows, {"winners": [], "losers": []}).startswith("Nothing beats")
        rows[1]["verdict"] = "NOTHING"
        assert rr.answer_line(rows, {"winners": [], "losers": []}).startswith("Nothing beats what we run")
        rows[1]["verdict"] = "WATCH"
        assert rr.answer_line(rows, {"winners": [], "losers": []}).startswith("1 arm(s) on watch")
        # item 2 (freeze check): one arm lost (NOTHING), one won on fewer than 10 trades (WATCH), one unreadable -> WATCH is
        # checked FIRST and the line never prints "Nothing beats" beside an arm that beat what we run
        mixed = [{"lens": "stop: stop_orb_low", "where": "L1 / era_e", "n": 12, "reading": "x", "verdict": "NOTHING"},
                 {"lens": "stop: stop_adr_050", "where": "L1 / era_e", "n": 6, "reading": "x", "verdict": "WATCH"},
                 {"lens": "stop: stop_adr_075", "where": "L1 / era_e", "n": 1, "reading": "x", "verdict": "CAN'T TELL"}]
        line = rr.answer_line(mixed, {"winners": [], "losers": []})
        assert "Nothing beats" not in line and line.startswith("1 arm(s) on watch") and "1 did not beat it, 1 unreadable" in line

    def test_freeze4_a_dead_recorder_leads_line_one_with_the_gap_not_wait(self, tmp_path):
        """Freeze item 4: ran 0 of N sessions (or none of the last GAP_RETRY_SESSIONS) -> the recorder-gap headline, even with no old closes."""
        dead = {"sessions": 60, "ran": 0, "missing": [], "recent_n": 5, "recent_ran": 0}
        assert rr.recorder_dead(dead) and rr.answer_line([], {}, {}, None, (), dead).startswith("recorder gap")
        lately = {"sessions": 60, "ran": 50, "missing": [], "recent_n": 5, "recent_ran": 0}
        assert rr.recorder_dead(lately) and "none of the last 5" in rr.answer_line([], {}, {}, None, (), lately)
        alive = {"sessions": 60, "ran": 59, "missing": [], "recent_n": 5, "recent_ran": 4}
        assert not rr.recorder_dead(alive) and not rr.recorder_dead(rr.NOT_CAPTURED) and not rr.recorder_dead(None)
        assert not rr.recorder_dead({"sessions": 0, "ran": 0, "missing": [], "recent_n": 0, "recent_ran": 0})
        # end to end: three fresh fills, an audit_recorder with only an old row and none in the last 5 sessions
        fresh = [trade(id=i, ticker=f"T{i}", closed_at="2026-11-27 20:00:00+00", total_pnl="-20", exits=legs(("stop_hit", 98))) for i in range(1, 4)]
        old_row = [{"id": "1", "created_at": "2026-09-04 22:04:10+00", "summary": "0 fill(s)", "event_type": rr.RECORDER_RUN_EVENT}]
        _full_capture(tmp_path / "late", fresh, [], audit_recorder=old_row)
        assert _report(tmp_path / "late")["answer"].startswith("recorder gap — the 18:04 ET job wrote a nightly row on 1 of ")
        # a missing night in the middle with a recent row is NOT dead (the default fixture has a row on 11-27)
        _full_capture(tmp_path / "ok", fresh, [])
        assert _report(tmp_path / "ok")["answer"].startswith("too few trades to read yet")
        # a recorder that never wrote a row
        (tmp_path / "none").mkdir()
        _full_capture(tmp_path / "none", fresh, [], audit_recorder=[{"id": "1", "created_at": "2026-11-27 23:04:10+00", "summary": "x", "event_type": "other"}])
        assert _report(tmp_path / "none")["answer"].startswith("recorder gap — the 18:04 ET job wrote no nightly row on any of ")

    def test_freeze1_a_capture_file_with_no_header_line_is_not_captured(self, tmp_path):
        """Freeze item 1: `psql ... > x.csv` leaves a 0-byte file when psql fails; `\\copy ... CSV HEADER` always writes a header line."""
        fresh = [trade(id=i, ticker=f"T{i}", closed_at="2026-11-12 20:00:00+00", total_pnl="-20", exits=legs(("stop_hit", 98))) for i in range(1, 4)]
        r = tmp_path / "Z"
        _full_capture(r, fresh, [])
        for name in ("cf_arms", "predicates", "audit_recorder"):
            (r / "data" / f"{name}.csv").write_bytes(b"")
        (r / "data" / "strategies.csv").write_text("\n")           # whitespace only is no header either
        assert sorted(rr.missing_captures(r / "data")) == ["audit_recorder", "cf_arms", "predicates", "strategies"]
        manifest = rr.write_manifest(r, "x")
        for name in ("cf_arms", "predicates", "audit_recorder", "strategies"):
            assert f"{name}.csv: NOT CAPTURED" in manifest and f"{name}.csv: rows" not in manifest
        rep = _report(r)
        assert set(rep["not_captured"]) == {"audit_recorder", "cf_arms", "predicates", "strategies"}
        assert rep["answer"].startswith("capture incomplete") and "recorder gap" not in rep["answer"]

    def test_f2_a_missing_capture_file_is_named_not_read_as_an_empty_month(self, tmp_path):
        """Finding 2: trades.csv alone (the probe's Case A) -> every other file NOT CAPTURED on the page, five folded
        rows 'n/a — not captured', the absence sentence makes no claim, line 1 leads with the incomplete capture."""
        run = tmp_path / "runA"
        (run / "data").mkdir(parents=True)
        (run / "data" / "trades.csv").write_text(",".join(trade().keys()) + "\n")
        rep = _report(run)
        missing = rep.get("not_captured", [])
        assert "predicates" in missing and "strategy_toggles" in missing and "audit_recorder" in missing and "trades" not in missing
        assert len(rep["folded"]) == 5 and all(fr["n"] == rr.NOT_CAPTURED for fr in rep["folded"])
        assert rep["missed_absence"].startswith("NOT CAPTURED") and "did not run" not in rep["missed_absence"]
        assert rep["answer"].startswith("capture incomplete") and "Nothing beats" not in rep["answer"]
        md = rr.render(rep)
        assert "**NOT CAPTURED: predicates.csv**" in md and rr.NOT_CAPTURED in md
        assert "NOT CAPTURED" in rr.write_manifest(run, "2026-11-29T18:00:00-05:00")
        # one file missing from an otherwise full capture is named too; trades.csv missing stops the read
        _full_capture(tmp_path / "runB", [trade()], [], skip={"predicates"})
        rep = _report(tmp_path / "runB")
        assert rep.get("not_captured", []) == ["predicates"] and rep["answer"].startswith("capture incomplete — 1 file(s)")
        _full_capture(tmp_path / "runC", [trade()], [], skip={"trades"})
        with pytest.raises(SystemExit):
            _report(tmp_path / "runC")
        assert set(rr.REQUIRED_CAPTURES) == {p.stem for p in CAPTURE.glob("*.sql")} and len(rr.REQUIRED_CAPTURES) >= 17

    def test_f3_a_propose_needs_one_admission_cell_on_one_side_of_1104(self):
        """Finding 3: 12 winning era-E fills under ONE admission label split 7 before / 5 after 2026-11-04 mix the two
        sides of #718 (an admission change) — WATCH, not PROPOSE; 12 on one side is PROPOSE. The cell key is
        (admission era, pre/post 11-04); for a post-11-04 fill the DERIVED label (I16: the recorder rows from 11-04 until the row is deployed
        carry the 08-31 stamp from before the row existed)."""
        arm_rows = {(str(i), "stop_orb_low"): arm_row(i, "stop_orb_low", 0.0 + 0.01 * i, 0.0 + 0.01 * i) for i in range(1, 13)}
        mixed = {"era_e": [dict(fill(i, -1.0), admission_era="adm_A", post_1104=(i > 7)) for i in range(1, 13)]}
        res = rr.arm_lens("stop", mixed, arm_rows, "era_e")["stop_orb_low"]
        assert res["verdict"] == "WATCH" and "demoted" in res["why"] and "adm_A pre-11-04 n 7" in res["why"] and "adm_A post-11-04 n 5" in res["why"]
        one_side = {"era_e": [dict(fill(i, -1.0), admission_era="adm_A", post_1104=True) for i in range(1, 13)]}
        assert rr.arm_lens("stop", one_side, arm_rows, "era_e")["stop_orb_low"]["verdict"] == "PROPOSE"
        cells = rr.admission_cells("stop", mixed, arm_rows)
        assert {(c["admission_era"], c["side"], c["n"]) for c in cells if c["arm"] == "stop_orb_low"} == {("adm_A", "pre-11-04", 7), ("adm_A", "post-11-04", 5)}
        stamped = arm_row(1, "live_actual", 1.0, admission_era="adm_2026-08-31_extension_cap_50_slot_rank_rs")
        assert rr.admission_cell_key(trade(alert_date="2026-11-05"), stamped) == ("adm_2026-11-04_open_below_floor", "post-11-04")
        assert rr.admission_cell_key(trade(alert_date="2026-11-03"), stamped) == ("adm_2026-08-31_extension_cap_50_slot_rank_rs", "pre-11-04")
        assert rr.admission_cell_key(trade(alert_date="2026-11-03"), None) == ("adm_2026-08-31_extension_cap_50_slot_rank_rs", "pre-11-04")

    def test_f4_the_armed_runner_shape_does_not_apply_where_the_era_had_no_arm(self):
        """Finding 4: an era-C trade (partial at +4, stop at entry, peak 104) counted as BOTH shapes under the 3R
        fallback. The arm comes from rule_eras.exit_rules_as_of(alert_date, signal_type, exit_rule=row); None = n/a."""
        era_c = trade(alert_date="2026-08-20", exit_rule="", exits=legs(("partial_profit", 104, 3), ("stop_hit", 100.0, 7)))
        s = rr.runner_shapes(era_c, {"peak_price": "104"}, {"breakeven_arm_r": ""})
        assert s["partial_breakeven"] is True and s["armed_breakeven"] is False and s["arm_r"] is None and s["arm_price"] is None
        assert rr.breakeven_arm_for(era_c) is None
        assert rr.breakeven_arm_for(trade(alert_date="2026-10-20", exit_rule="depth")) == 3.0
        assert rr.breakeven_arm_for(trade(alert_date="2026-10-20", account_mode="paper", signal_type="magna53_smallcap", exit_rule="depth")) == 3.0
        l3 = trade(account_mode="paper", signal_type="breakout_v1", exit_rule="breakout_pp", alert_date="2026-11-04", exits=legs(("stop_hit", 100.0)))
        assert rr.runner_shapes(l3, {"peak_price": "104"}, None)["arm_r"] is None
        era_e = trade(exits=legs(("stop_hit", 100.0)))
        assert rr.runner_shapes(era_e, {"peak_price": "103.2"}, None)["armed_breakeven"] is True       # era E: 3 via rule_eras
        assert rr.partial_descriptives([era_c, era_e], {str(era_c["id"]): {"peak_price": "104"}})["armed_na"] == 1

    def test_f5_the_absence_sentence_names_width_dropped_and_malformed_records(self, tmp_path):
        """Finding 5: two missed-by-slots records both dropped by the width rule + one malformed -> the page names
        them; it never says 'none broke out while held' when records were written."""
        audit = [{"id": "1", "created_at": "", "event_type": rr.HOLD_EVENT, "summary": "", "detail": json.dumps({"ticker": "ZZZ", "state": "slots_full"})},
                 {"id": "3", "created_at": "", "event_type": rr.ENTRY_DAY_EVENT, "summary": "", "detail": "{}"}]
        wide = {"ticker": "WID", "day": "2026-11-04", "break_price": 50, "stop": 47, "width": 0.06, "adr20": 0.05}
        bad = {"ticker": "BAD", "day": "2026-11-04", "break_price": 50, "width": 0.02, "adr20": 0.05}     # no stop
        audit += [{"id": str(10 + i), "created_at": "", "event_type": rr.MISSED_EVENT, "summary": "", "detail": json.dumps(rec)}
                  for i, rec in enumerate((wide, wide, bad))]
        _full_capture(tmp_path / "run", [trade()], [], audit=audit)
        rep = _report(tmp_path / "run")
        s = rep["missed_absence"]
        assert "hold rows, none broke out while held" not in s and s.startswith("3 missed-by-slots record(s) written, none readable")
        assert "2 dropped by the width rule" in s and "1 malformed" in s
        assert rep["missed"]["raw_n"] == 3 and rep["missed"]["width_dropped"] == 2 and rep["missed"]["malformed"] == 1
        obs = rr.absence_observables(audit, 0, 5, "on", None)
        assert rr.absence_sentence(obs, 0, raw_n=0) == "1 hold rows, none broke out while held"
        assert rr.absence_sentence(obs, 0, raw_n=1, bad_json=1).startswith("1 missed-by-slots record(s) written, none readable — 1 unreadable JSON")
        assert rr.absence_sentence(obs, 1, raw_n=3, width_dropped=2) == "missed 1 of 1 held rows; 2 dropped by the width rule"

    def test_f6_cannot_tell_stays_cannot_tell(self):
        """Finding 6: the YAML's own 09-16 reading (4 of 11 vs 17 of 25, p 0.141) maps to the ladder's CAN'T TELL;
        KEEP -> NOTHING (the current filter is right); REVISIT -> WATCH / PROPOSE."""
        assert rr.stop_too_wide_matrix([12.0] * 4 + [1.0] * 7, [12.0] * 17 + [1.0] * 8)["verdict"] == "CAN'T TELL"
        assert rr.stop_too_wide_matrix([1] * 10, [12] * 10)["verdict"] == "NOTHING"
        assert rr.stop_too_wide_matrix([12, 11, 15], [5, 4, 3])["verdict"] == "WATCH"
        assert rr.stop_too_wide_matrix([12, 11], [5, 4, 3])["verdict"] == "CAN'T TELL"      # under 3: the ladder's own rung

    def test_f7_the_breakout_grade_test_caps_at_watch(self):
        """Finding 7: ten graded `no` losers and a `good` winner is WATCH, never PROPOSE — charts support, never
        decide; his EP labels are capped the same way."""
        grades = [{"list_date": "2026-11-03", "ticker": f"N{i}", "grade": "no"} for i in range(10)] + [{"list_date": "2026-11-03", "ticker": "G", "grade": "good"}]
        l3 = [trade(id=i, ticker=f"N{i}", account_mode="paper", signal_type="breakout_v1", exit_rule="breakout_pp", alert_date="2026-11-04", total_pnl="-20")
              for i in range(10)] + [trade(id=99, ticker="G", account_mode="paper", signal_type="breakout_v1", exit_rule="breakout_pp", alert_date="2026-11-04", total_pnl="60")]
        bs = rr.breakout_selection(l3, grades)
        assert bs["graded"] == 11 and bs["low_n"] == 10 and bs["verdict"] == "WATCH"
        l3[0]["total_pnl"] = "20"                                      # a `no` name that won: the test is not met
        assert rr.breakout_selection(l3, grades)["verdict"] == "NOTHING"
        assert rr.breakout_selection(l3[:2], grades)["verdict"] == "CAN'T TELL"

    def test_f8_folded_rows_read_every_lens_each_review_asked_about(self):
        """Finding 8: 482 asked stop + harvest + trail; the parked geometry review asked stop + entry; the runner
        sweep is descriptive. A stop arm on WATCH shows on the 482 row even when the trail arms are unreadable."""
        arm_results = {"stop": {"stop_orb_low": {"verdict": "WATCH"}, "stop_adr_050": {"verdict": "CAN'T TELL"}},
                       "partials": {"harvest_t3": {"verdict": "CAN'T TELL"}}, "exits": {"trail_pivot_swing": {"verdict": "CAN'T TELL"}},
                       "buy_point": {"entry_first_hour_bar": {"verdict": "NOTHING"}}}
        preds = [{"review": rid, "n": str(i)} for i, rid in enumerate(rr.FOLDED_REVIEWS) if rid != "exit_tune_cohort_review"]
        rows = {r["review"]: r for r in rr.folded_rows(preds, arm_results, "CAN'T TELL")}
        assert list(rows) == list(rr.FOLDED_REVIEWS)
        assert rows["live_fill_counterfactuals_first_read_482"]["verdict"] == "WATCH"
        assert rows["bracket_geometry_variants_parked"]["verdict"] == "WATCH"
        assert rows["exit_tune_cohort_review"]["verdict"] == "CAN'T TELL" and rows["exit_tune_cohort_review"]["n"] == rr.NOT_CAPTURED
        assert rows["runner_rule_sweep_recut"]["verdict"] == "descriptive" and rows["stop_too_wide_outcome_cohort"]["verdict"] == "CAN'T TELL"
        assert rr.FOLD_MAP["live_fill_counterfactuals_first_read_482"] == ("stop", "partials", "exits")
        assert rr.FOLD_MAP["bracket_geometry_variants_parked"] == ("stop", "buy_point")

    def test_f9_the_stop_too_wide_yaml_pointer_says_nothing_stays_outside_and_marks_step_one_replaced(self):
        """Finding 9: plan §7's last column says nothing stays outside; the pull from mi_ep_missed_outcomes (step 1)
        is the source the plan bans and is marked REPLACED by #720 §3 Stop (c). The other four keep their 'outside'."""
        import yaml
        reg = {e["review_id"]: e for e in yaml.safe_load(YAML.read_text(encoding="utf-8"))["reviews"]}
        act = reg["stop_too_wide_outcome_cohort"]["action_when_ready"]
        assert "keeps its own predicate and bar for what stays OUTSIDE" not in act
        assert "Nothing stays outside" in act and "REPLACED by #720 §3 Stop (c)" in act
        assert act.index("REPLACED by #720 §3 Stop (c)") < act.index("mi_ep_missed_outcomes")
        for rid in rr.FOLDED_REVIEWS:
            if rid != "stop_too_wide_outcome_cohort":
                assert "what stays OUTSIDE" in reg[rid]["action_when_ready"], rid

    def test_f10_the_recorder_heartbeat_and_unsettled_pairs_are_named(self):
        """Finding 10: the nightly `_recorded` / `_error` audit rows are captured, the sessions with no row are
        named, and a closed fill WITH rows but no settled control pair past the retry window is named too."""
        assert (CAPTURE / "audit_recorder.sql").exists()
        audit = [{"id": "1", "created_at": "2026-11-23 23:04:10+00", "event_type": rr.RECORDER_RUN_EVENT, "summary": "0 fill(s)"},
                 {"id": "2", "created_at": "2026-11-24 23:04:10+00", "event_type": rr.RECORDER_ERROR_EVENT, "summary": "run failed: boom"},
                 {"id": "3", "created_at": "2026-11-25 23:04:10+00", "event_type": rr.RECORDER_RUN_EVENT, "summary": "0 fill(s)"}]
        runs = rr.recorder_runs(audit, date(2026, 11, 23), date(2026, 11, 29))
        assert runs["sessions"] == 4 and runs["ran"] == 2 and runs["last_run"] == date(2026, 11, 25)       # 11-26 Thanksgiving is no session
        assert runs["missing"] == [date(2026, 11, 24), date(2026, 11, 27)] and runs["error_rows"] == 1 and runs["error_samples"] == ["run failed: boom"]
        assert rr.recorder_runs([], date(2026, 11, 23), date(2026, 11, 29))["ran"] == 0
        # the first window starts 08-16 but the job's first FIRE was 09-04 (built 09-03, deployed after that night's run): 08-17..09-03 are never "missing"
        first = rr.recorder_runs([{"id": "9", "created_at": "2026-09-04 22:04:10+00", "event_type": rr.RECORDER_RUN_EVENT, "summary": ""}],
                                 rr.FIRST_WINDOW_START, date(2026, 9, 4))
        assert rr.RECORDER_FIRST_SESSION == date(2026, 9, 4) and first["from"] == date(2026, 9, 4)
        assert first["sessions"] == 1 and first["ran"] == 1 and first["missing"] == []
        old_rows = trade(id=5, ticker="HALF", closed_at="2026-10-01 20:00:00+00")
        cf = [arm_row(5, "live_actual", 1.0), arm_row(5, "live_replay", 1.0, outcome="horizon")]
        g = rr.recorder_gaps([old_rows], cf, date(2026, 11, 29))["era_e"]
        assert g["with_rows"] == 1 and g["settled_pairs"] == 0 and g["gaps"] == [] and g["unsettled"] == ["HALF (trade 5, closed 2026-10-01)"]
        assert rr.recorder_gap_count({"era_e": g}) == 1
        fresh = trade(id=6, ticker="NEW", closed_at="2026-11-27 20:00:00+00")
        assert rr.recorder_gaps([fresh], [arm_row(6, "live_actual", 1.0)], date(2026, 11, 29))["era_e"]["unsettled"] == []
