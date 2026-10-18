"""#314 / ADR 0020 card B3 - the parabolic-short forward SHADOW (arm / trigger / outcome rows, no orders).

Three layers, all on SYNTHETIC bars (no DB, no network):
  1. the pure replay - fill convention, the arm window, the invalidation, the 1R flush, the trailing stop, the
     time stop, the earnings exit, the conservative intra-bar ordering;
  2. the nightly step against an in-memory store (`Env`) that reproduces the INSERT-ONCE write guard and the
     two readers' joins - the arm decision (market-cap floor, borrow check incl. a broker error), the trigger
     (borrow check repeated), settlement, idempotence, catch-up, "reads only data <= tonight";
  3. the digest line, the job wiring, and the boundary: the module can reach exactly ONE broker call,
     `execution_client.get_asset`, and no order function.

The facade itself (both transports, the route, the broker wrapper) is pinned in tests/test_get_asset_facade_314.py.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.market_intelligence import db
from agents.market_intelligence import execution_client as ec
from agents.market_intelligence import parabolic_short_shadow as psh
from agents.market_intelligence.constants import RISK_PCT

REPO = Path(__file__).resolve().parent.parent


# ── synthetic market ─────────────────────────────────────────────────────────────────────────────

def bdays(start: date, n: int) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def bar(d: date, o: float, h: float, l: float, c: float, v: int = 2_000_000) -> dict:
    return {"trade_date": d, "open_price": o, "high_price": h, "low_price": l, "close": c, "volume": v}


DAYS = bdays(date(2026, 8, 3), 48)
N_HIST = 30
D = {k: DAYS[N_HIST + k] for k in range(0, 12)}      # D[0] = the climax day, D[1] = the first session after it
CLIMAX = (150.0, 160.0, 140.0, 155.0)                # open, high, low, close
# ATR14 at the climax day = (13 flat bars x TR 2 + the climax TR 60) / 14 = 6.142857; the buffer
# min(3% x 160 = 4.80, 0.5 x ATR = 3.0714) = 3.0714 -> stop 163.07; level for session 1 = the climax low 140.
LEVEL0, STOP = 140.0, 163.07
R = STOP - LEVEL0                                    # 23.07: 1R in dollars when the entry is at 140


def history() -> list[dict]:
    return [bar(DAYS[i], 100, 101, 99, 100) for i in range(N_HIST)]


def market(post: list[tuple]) -> list[dict]:
    """30 flat bars, the climax day, then `post` = [(o, h, l, c), ...] for sessions D[1], D[2], ..."""
    return history() + [bar(D[0], *CLIMAX)] + [bar(D[i + 1], *b) for i, b in enumerate(post)]


def replay(post, *, armed_on=None, **kw) -> dict:
    return psh.replay_episode(market(post), N_HIST, stop_price=STOP, armed_on=armed_on or D[0], **kw)


# The scenario every lifecycle test reuses: triggers on D1 (open 150 above the 140 level, low 138 -> filled AT
# 140), flushes on D3 (low 115 <= 116.93), exits on D5 at the time stop.
TRIGGER_THEN_TIME_STOP = [
    (150, 153, 138, 139),      # D1: fill at 140
    (138, 145, 130, 132),      # D2: stop trails to 153
    (131, 135, 115, 118),      # D3: stop 145; low 115 <= 116.93 -> the 1/3 flush
    (117, 120, 110, 112),      # D4: stop 135
    (113, 118, 108, 110),      # D5: stop 120; 5th session held -> out at the close 110
]


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# 1. the pure functions
# ═════════════════════════════════════════════════════════════════════════════════════════════════

class TestGeometry:
    def test_arm_geometry_matches_the_adr_formula(self):
        g = psh.arm_geometry(market([]), N_HIST)
        assert g["climax_high"] == 160.0 and g["climax_low"] == 140.0 and g["prior_day_low"] == 140.0
        assert g["atr_14"] == pytest.approx((13 * 2 + 60) / 14)
        assert g["stop_buffer"] == pytest.approx(0.5 * g["atr_14"])            # ATR half binds (3.07 < 4.80)
        assert g["stop_price"] == STOP
        assert g["limit_price"] == 139.3                                       # 140 x 0.995

    def test_buffer_is_the_smaller_of_three_percent_and_half_atr(self):
        assert psh.stop_buffer(100.0, 4.0) == 2.0          # 0.5 x ATR (2.0) < 3% (3.0)
        assert psh.stop_buffer(100.0, 10.0) == 3.0         # 3% (3.0) < 0.5 x ATR (5.0)
        assert psh.stop_buffer(100.0, None) == 3.0         # no ATR: the cap stands alone
        assert psh.stop_buffer(100.0, 0.0) == 3.0

    def test_short_limit_mirrors_the_buy_side_convention(self):
        from agents.market_intelligence.broker.order_manager import stop_limit_buy_price
        for s in (5.49, 10.0, 41.5, 100.0, 140.0, 2000.0):
            assert round(s - psh.short_limit_price(s), 2) == round(stop_limit_buy_price(s) - s, 2), s

    def test_atr_missing_history_falls_back_to_the_cap(self):
        rows = market([])[N_HIST - 5:]                     # climax index 5: fewer than 14 TRs available
        g = psh.arm_geometry(rows, 5)
        assert g["atr_14"] is None and g["stop_buffer"] == pytest.approx(0.03 * 160.0)


class TestFillConvention:
    """A resting DAY stop-limit SHORT at 140 (limit 139.30) against one daily bar (open, high, low)."""

    @pytest.mark.parametrize("o,h,l,expect", [
        (150.0, 151.0, 141.0, ("none", None)),                    # the low never reached 140
        (150.0, 151.0, 140.0, ("intraday", 140.0)),               # a print AT the level triggers a sell-stop
        (150.0, 151.0, 138.0, ("intraday", 140.0)),               # opened above, traded down through: filled AT the level
        (140.0, 141.0, 135.0, ("gap_open", 140.0)),               # opened AT the level: the open is the fill
        (139.8, 141.0, 137.0, ("gap_open", 139.8)),               # gapped under the stop but inside the 139.30 limit
        (139.3, 141.0, 130.0, ("gap_open", 139.3)),               # exactly at the limit still fills at the open
        # opened BELOW the limit: the opening print triggers the stop, the order rests as a limit SELL at 139.30
        # and fills the moment the session trades back up to it (the open is the first print, so any high that
        # reaches the limit came while the order was live)
        (139.29, 141.0, 130.0, ("limit_recovery", 139.3)),
        (135.0, 141.0, 130.0, ("limit_recovery", 139.3)),
        (135.0, 139.3, 130.0, ("limit_recovery", 139.3)),         # a high exactly at the limit fills
        # the REAL no-fill: opened under the limit and never got back to it
        (139.29, 139.29, 130.0, ("gap_through_limit", None)),
        (135.0, 139.0, 130.0, ("gap_through_limit", None)),
    ])
    def test_stop_limit_short_against_one_bar(self, o, h, l, expect):
        assert psh.trigger_fill(LEVEL0, bar(D[1], o, h, l, l)) == expect

    def test_a_session_that_opens_under_the_limit_and_rallies_back_to_it_is_a_fill_not_a_skipped_arm(self):
        # The reviewer's case: level 140, open 139.0, high 141.0, low 130.0 - the old model recorded a no-fill and
        # re-armed at the session's low; a real resting limit sell is certain to have filled at 139.30.
        assert psh.trigger_fill(140.0, bar(D[1], 139.0, 141.0, 130.0, 133.0)) == ("limit_recovery", 139.3)
        r = replay([(139.0, 141.0, 130.0, 133.0)])
        t = r["trigger"]
        assert (t["date"], t["kind"], t["entry_price"], t["level"], t["limit"]) == (D[1], "limit_recovery", 139.3, 140.0, 139.3)
        assert t["risk_per_share"] == pytest.approx(STOP - 139.3) and r["gap_skips"] == 0 and r["state"] == "open"


class TestArmWindowAndInvalidation:
    def test_first_session_break_fills_at_the_level(self):
        r = replay([(150, 153, 138, 139)])
        t = r["trigger"]
        assert (t["date"], t["level"], t["entry_price"], t["kind"]) == (D[1], 140.0, 140.0, "intraday")
        assert t["risk_per_share"] == pytest.approx(R) and t["limit"] == 139.3
        assert r["state"] == "open"

    def test_the_level_trails_to_each_prior_session_low(self):
        r = replay([(150, 152, 142, 148), (146, 149, 141.5, 143)])     # D1 does not break 140; D2 breaks D1's 142
        assert r["trigger"]["date"] == D[2] and r["trigger"]["entry_price"] == 142.0

    def test_a_higher_low_loosens_the_level(self):
        # D1 low 142 then D2 low 145 (higher): D3's level is 145, so a D3 low of 144.5 triggers it.
        r = replay([(150, 152, 142, 148), (150, 153, 145, 150), (150, 152, 144.5, 148)])
        assert r["trigger"]["date"] == D[3] and r["trigger"]["entry_price"] == 145.0

    def test_triggers_on_the_third_session_not_the_fourth(self):
        quiet = [(150, 152, 142, 148), (150, 153, 143, 149)]
        third = replay(quiet + [(148, 150, 141.5, 145)])
        assert third["trigger"] is not None and third["trigger"]["date"] == D[3]
        fourth = replay(quiet + [(150, 154, 144, 150), (149, 150, 100, 105)])
        assert fourth["trigger"] is None
        assert fourth["outcome"] == {"status": "closed_untriggered", "reason": "expired_untriggered", "date": D[3]}

    def test_three_untriggered_sessions_expire_the_arm(self):
        r = replay([(150, 152, 141, 148), (150, 153, 142, 149), (150, 154, 143, 150)])
        assert r["state"] == "closed" and r["outcome"]["reason"] == psh.OUT_EXPIRED
        assert r["outcome"]["date"] == D[3]

    def test_a_close_above_the_climax_high_before_a_trigger_invalidates(self):
        r = replay([(150, 162, 141, 161)])                 # high 162 < stop 163.07, but CLOSE 161 > 160
        assert r["outcome"] == {"status": "closed_untriggered", "reason": "invalidated", "date": D[1]}
        assert r["trigger"] is None

    def test_a_high_above_the_climax_high_that_closes_back_under_does_not_invalidate(self):
        r = replay([(150, 162, 141, 158)])
        assert r["state"] == "waiting" and r["outcome"] is None

    def test_a_session_that_triggers_is_not_also_invalidated(self):
        r = replay([(150, 162, 138, 161)])                 # broke 140 AND closed above 160: trigger wins, position open
        assert r["trigger"]["entry_price"] == 140.0 and r["outcome"] is None and r["state"] == "open"

    def test_gap_through_the_limit_is_a_no_fill_and_the_arm_carries(self):
        r = replay([(135, 139, 130, 132), (133, 134, 128, 129)])
        # D1: opened 135 under the 139.30 limit - no fill, the level re-sets to D1's low 130; D2 breaks it.
        assert r["gap_skips"] == 1
        assert r["trigger"]["date"] == D[2] and r["trigger"]["entry_price"] == 130.0

    def test_a_late_arm_gets_no_credit_for_a_break_before_it_existed(self):
        post = [(150, 153, 138, 139), (140, 142, 134, 136)]
        early = replay(post, armed_on=D[0])
        late = replay(post, armed_on=D[1])                 # armed on D1's night: D1 cannot trigger
        assert early["trigger"]["date"] == D[1]
        assert late["trigger"]["date"] == D[2]             # D2 breaks D1's low (138)? 134 <= 138 -> yes, at 138
        assert late["trigger"]["entry_price"] == 138.0

    def test_a_late_arm_still_sees_an_invalidating_close(self):
        r = replay([(150, 162, 141, 161)], armed_on=D[1])
        assert r["outcome"]["reason"] == "invalidated"

    def test_a_bar_missing_a_price_stalls_the_replay(self):
        rows = market([(150, 153, 138, 139)])
        rows[-1]["low_price"] = None
        r = psh.replay_episode(rows, N_HIST, stop_price=STOP, armed_on=D[0])
        assert r["state"] == "data_gap" and r["outcome"] is None


class TestManagement:
    def test_flush_then_time_stop_blends_one_third_at_plus_one_r(self):
        r = replay(TRIGGER_THEN_TIME_STOP)
        o = r["outcome"]
        assert (o["status"], o["reason"], o["date"], o["sessions_held"]) == ("settled", "time_stop", D[5], 5)
        assert o["flush_taken"] and o["flush_price"] == pytest.approx(140.0 - R)
        assert o["exit_price"] == 110.0 and o["exit_leg_r"] == pytest.approx(30.0 / R)
        assert o["realized_r"] == pytest.approx(1 / 3 + (2 / 3) * (30.0 / R))
        # MAE: D1 is an `intraday` fill, so its high (153) may predate the fill and is NOT counted; D2's 145 is the worst
        assert o["mfe_r"] == pytest.approx(32.0 / R) and o["mae_r"] == pytest.approx(5.0 / R)
        assert o["entry_day_ambiguous"] is False

    def test_the_time_stop_counts_the_entry_session_as_one(self):
        r = replay(TRIGGER_THEN_TIME_STOP[:4])
        assert r["state"] == "open" and r["outcome"] is None          # 4 sessions held: not yet
        assert r["open"]["sessions_held"] == 4 and r["open"]["flush_taken"]

    def test_the_stop_trails_to_the_prior_session_high_and_never_up(self):
        # D1 fills at 140 (high 153); D2's stop is 153 - a high of 152.9 holds, 153.0 stops it at 153.
        held = replay([(150, 153, 138, 139), (138, 152.9, 130, 132)])
        assert held["state"] == "open" and held["open"]["stop"] == 153.0
        hit = replay([(150, 153, 138, 139), (141, 155, 139, 150)])
        o = hit["outcome"]
        assert (o["reason"], o["exit_price"]) == ("trail_stop", 153.0)
        assert o["exit_leg_r"] == pytest.approx(-13.0 / R) and o["realized_r"] == pytest.approx(-13.0 / R)

    def test_a_higher_prior_high_never_raises_the_stop(self):
        # D2 prints a LOWER high (145) than D1 (153); D3 would trail to 145. D3's high 150 stops it at 145, not 153.
        r = replay([(150, 153, 138, 139), (138, 145, 130, 133), (132, 150, 131, 148)])
        assert r["outcome"]["reason"] == "trail_stop" and r["outcome"]["exit_price"] == 145.0

    def test_entry_session_stop_out_is_flagged_ambiguous_and_exits_at_the_stop(self):
        r = replay([(150, 170, 138, 139)])                 # high 170 >= 163.07 on the fill session itself
        o = r["outcome"]
        assert o["reason"] == "stop" and o["exit_price"] == STOP and o["entry_day_ambiguous"] is True
        assert o["realized_r"] == pytest.approx(-1.0)

    def test_a_gap_above_the_stop_exits_at_the_open(self):
        r = replay([(150, 153, 138, 139), (170, 175, 165, 172)])      # D2 stop 153, opens 170
        o = r["outcome"]
        assert o["reason"] == "trail_stop" and o["exit_price"] == 170.0
        assert o["exit_leg_r"] == pytest.approx(-30.0 / R)

    def test_the_stop_is_assumed_to_hit_before_the_flush_on_the_same_bar(self):
        r = replay([(150, 153, 138, 139), (141, 153.5, 110, 120)])    # stop 153 AND low 110 <= 116.93 in one bar
        o = r["outcome"]
        assert o["reason"] == "trail_stop" and o["flush_taken"] is False
        assert o["realized_r"] == pytest.approx(o["exit_leg_r"])      # no flush credit on the stop bar

    def test_flush_taken_earlier_still_pays_after_a_later_stop(self):
        r = replay([(150, 153, 138, 139), (138, 145, 115, 118), (119, 146, 117, 140)])
        o = r["outcome"]                                              # D2 flush; D3 stop 145 hit by high 146
        assert o["flush_taken"] and o["reason"] == "trail_stop" and o["exit_price"] == 145.0
        assert o["realized_r"] == pytest.approx(1 / 3 + (2 / 3) * (-5.0 / R))

    def test_no_overnight_through_earnings_exits_at_that_close(self):
        r = replay(TRIGGER_THEN_TIME_STOP, earnings_after=frozenset({D[3]}))
        o = r["outcome"]
        assert (o["reason"], o["date"], o["exit_price"], o["sessions_held"]) == ("earnings_exit", D[3], 118.0, 3)

    def test_an_earnings_date_after_an_earlier_stop_changes_nothing(self):
        r = replay([(150, 153, 138, 139), (141, 155, 139, 150)], earnings_after=frozenset({D[3]}))
        assert r["outcome"]["reason"] == "trail_stop"

    def test_no_adds_exist_the_position_is_one_entry_one_exit(self):
        r = replay(TRIGGER_THEN_TIME_STOP)
        assert set(r["trigger"]) == {"idx", "date", "level", "limit", "entry_price", "kind", "risk_per_share"}
        assert r["outcome"]["sessions_held"] == 5

    def test_a_limit_recovery_fill_credits_no_flush_and_no_excursion_from_the_low_that_came_before_it(self):
        # D1 opens under the limit (135 < 139.30), trades down to 110 (<= the 115.53 flush level), THEN rallies to
        # 141 and fills at 139.30. The 110 low almost surely predates the fill: no flush, no MFE from it, flagged.
        # D2-D5 never get down to the flush level again, so the flush stays untaken to the time stop.
        post = [(135, 141, 110, 120), (125, 128, 120, 126), (126, 127, 119, 121), (121, 125, 118, 120),
                (120, 124, 117, 119)]
        r = replay(post)
        t, o = r["trigger"], r["outcome"]
        risk = STOP - 139.3
        assert t["kind"] == "limit_recovery" and t["entry_price"] == 139.3
        assert (o["reason"], o["sessions_held"], o["exit_price"]) == ("time_stop", 5, 119.0)
        assert o["flush_taken"] is False and o["entry_day_ambiguous"] is True
        assert o["realized_r"] == pytest.approx((139.3 - 119.0) / risk)             # no 1/3 flush leg
        assert o["mfe_r"] == pytest.approx((139.3 - 117.0) / risk)                  # D2-D5's best low, NOT D1's 110
        assert o["mae_r"] == pytest.approx((141.0 - 139.3) / risk)                  # the D1 high WAS after the fill

    def test_a_limit_recovery_flush_on_a_later_session_is_credited(self):
        r = replay([(135, 141, 110, 120), (121, 124, 112, 114)])        # D2 low 112 <= the 115.53 flush level
        o = r["state"], r.get("open")
        assert r["state"] == "open" and r["open"]["flush_taken"] is True

    def test_an_intraday_fill_counts_no_mae_from_the_entry_sessions_high(self):
        # Opened above the level and came DOWN to the fill: that session's high (158) may predate it.
        r = replay([(150, 158, 138, 139)])
        assert r["trigger"]["kind"] == "intraday" and r["open"]["mae_r"] == 0.0
        assert r["open"]["mfe_r"] == pytest.approx(2.0 / R)               # the low (138) is at/after the fill: counted
        r2 = replay([(150, 158, 138, 139), (140, 150, 135, 141)])          # D2's high (150) counts in full
        assert r2["open"]["mae_r"] == pytest.approx(10.0 / R)

    def test_a_gap_open_fill_counts_the_entry_sessions_high_in_full(self):
        r = replay([(139.8, 150.0, 137.0, 140.0)])                         # the open IS the first print: the high is after the fill
        assert r["trigger"]["kind"] == "gap_open"
        assert r["open"]["mae_r"] == pytest.approx((150.0 - 139.8) / (STOP - 139.8))

    def test_a_stop_out_always_carries_at_least_the_stop_distance_as_mae(self):
        r = replay([(150, 170, 138, 139)])                                # intraday fill, high excluded - the stop still hit
        assert r["outcome"]["mae_r"] == pytest.approx(1.0)

    def test_a_stop_at_or_below_the_entry_voids_the_episode(self):
        r = psh.replay_episode(market([(150, 153, 138, 139)]), N_HIST, stop_price=139.0, armed_on=D[0])
        assert r["outcome"]["status"] == "voided" and r["outcome"]["reason"] == psh.OUT_VOID_GEOMETRY


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# 2. the nightly step against an in-memory store
# ═════════════════════════════════════════════════════════════════════════════════════════════════

ETB = {"symbol": "ZZZ", "status": "active", "tradable": True, "shortable": True, "easy_to_borrow": True,
       "marginable": True, "fractionable": True, "exchange": "nasdaq", "asset_class": "us_equity"}
HTB = {**ETB, "easy_to_borrow": False}
NOT_SHORTABLE = {**ETB, "shortable": False, "easy_to_borrow": False}
INACTIVE = {**ETB, "status": "inactive"}


class _Facade:
    """Stands in for `execution_client` inside the shadow module: ONLY get_asset exists. Any other attribute
    raises - so a lifecycle test that finishes proves no other broker function was touched."""

    def __init__(self, env):
        self._env = env

    async def get_asset(self, symbol, account_mode=None):
        self._env.borrow_calls.append((symbol, account_mode))
        plan = self._env.plan.get(symbol, [ETB])
        resp = plan.pop(0) if len(plan) > 1 else plan[0]
        if isinstance(resp, Exception):
            raise resp
        return resp

    def __getattr__(self, name):
        raise AssertionError(f"the shadow reached for execution_client.{name} - only get_asset is allowed")


class Env:
    """In-memory db + broker. Reproduces what the SQL does that the logic depends on: INSERT-ONCE per
    (ticker, climax_date, row_kind), the new-candidate anti-join, the open-episode join."""

    def __init__(self, mp):
        self.rows: list[dict] = []
        self.audit: list[tuple] = []
        self.bars: dict[str, list[dict]] = {}
        self.cands: list[dict] = []
        self.plan: dict = {}
        self.borrow_calls: list = []
        for name in ("get_recent_daily_history", "get_parabolic_short_new_candidates",
                     "get_parabolic_short_open_episodes", "insert_parabolic_short_shadow_row", "log_audit_event"):
            mp.setattr(db, name, getattr(self, name))

        async def _enabled(_strategy_id):
            return True

        async def _no_pool():
            raise AssertionError("the shadow reached the real database - only the five faked db.* functions are allowed")
        mp.setattr("agents.market_intelligence.strategies.registry.should_run", _enabled)
        mp.setattr(psh, "execution_client", _Facade(self))
        mp.setattr(db, "get_pool", _no_pool)

    # -- db
    async def get_recent_daily_history(self, ticker, days, end_date=None):
        rows = [r for r in self.bars[ticker] if end_date is None or r["trade_date"] <= end_date]
        return rows[-days:]

    def _find(self, ticker, d0, kind):
        return next((r for r in self.rows if (r["ticker"], r["climax_date"], r["row_kind"]) == (ticker, d0, kind)), None)

    async def get_parabolic_short_new_candidates(self, trade_date, lookback_days=7):
        return [c for c in self.cands
                if c["scan_date"] <= trade_date and (trade_date - c["scan_date"]).days <= lookback_days
                and c.get("excluded_reason") is None and not self._find(c["ticker"], c["scan_date"], "arm")]

    async def get_parabolic_short_open_episodes(self):
        out = []
        for a in self.rows:
            if a["row_kind"] != "arm" or a["status"] != "armed" or self._find(a["ticker"], a["climax_date"], "outcome"):
                continue
            t = self._find(a["ticker"], a["climax_date"], "trigger")
            out.append({**{k: a.get(k) for k in ("ticker", "climax_date", "climax_high", "climax_low", "stop_price",
                                                  "atr_14", "stop_buffer", "risk_fraction", "market_cap")},
                        "armed_on": a["event_date"],
                        "trigger_status": t["status"] if t else None,
                        "trigger_date": t["event_date"] if t else None,
                        "trigger_entry": t["entry_price"] if t else None})
        return out

    async def insert_parabolic_short_shadow_row(self, row):
        assert set(row) <= set(db.PS_SHADOW_COLS), set(row) - set(db.PS_SHADOW_COLS)
        if self._find(row["ticker"], row["climax_date"], row["row_kind"]):
            return False
        self.rows.append(dict(row))
        return True

    async def log_audit_event(self, event_type, summary, detail=""):
        self.audit.append((event_type, summary, detail))

    # -- helpers
    def load(self, ticker, post, *, mcap=1_000_000_000, scan_date=None, excluded=None):
        self.bars[ticker] = market(post)
        self.cands.append({"ticker": ticker, "scan_date": scan_date or D[0], "market_cap": mcap, "cap_tier": "small",
                           "excluded_reason": excluded})

    def row(self, ticker, kind, d0=None):
        return self._find(ticker, d0 or D[0], kind)

    async def night(self, k):
        return await psh.run_parabolic_short_shadow(D[k], earnings_checker=_never_earnings)


async def _never_earnings(ticker, session):
    return False


@pytest.fixture
def env(monkeypatch):
    return Env(monkeypatch)


@pytest.mark.asyncio
class TestArmDecision:
    async def test_etb_name_arms_and_records_the_data_prep(self, env):
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP)
        s = await env.night(0)
        a = env.row("ZZZ", "arm")
        assert a["status"] == "armed" and a["reason"] is None and a["event_date"] == D[0]
        assert (a["climax_high"], a["climax_low"], a["prior_day_low"], a["stop_price"]) == (160.0, 140.0, 140.0, STOP)
        assert a["atr_14"] == pytest.approx(86 / 14) and a["limit_price"] == 139.3
        assert a["risk_fraction"] == pytest.approx(RISK_PCT * 0.5) and a["risk_fraction"] == pytest.approx(0.01)
        assert (a["borrow_acct"], a["shortable"], a["easy_to_borrow"], a["asset_status"]) == ("paper", True, True, "active")
        assert s["armed"] == [{"ticker": "ZZZ", "level": 140.0, "stop": STOP}]
        assert env.borrow_calls == [("ZZZ", "paper")]

    async def test_the_arm_reads_only_data_up_to_tonight(self, env):
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP)            # D1 would trigger - but tonight is D0
        await env.night(0)
        assert env.row("ZZZ", "trigger") is None and env.row("ZZZ", "outcome") is None

    @pytest.mark.parametrize("asset,reason", [
        (HTB, "borrow:hard_to_borrow"),
        (NOT_SHORTABLE, "borrow:not_shortable"),
        (INACTIVE, "borrow:not_tradable"),
        ({**ETB, "tradable": False}, "borrow:not_tradable"),
        ({**ETB, "shortable": None, "easy_to_borrow": None}, "borrow:not_shortable"),   # "Alpaca did not say" is not yes
        ({**ETB, "easy_to_borrow": None}, "borrow:hard_to_borrow"),
        (None, "borrow:asset_not_found"),
    ])
    async def test_non_etb_names_are_skipped_with_a_named_reason(self, env, asset, reason):
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP)
        env.plan["ZZZ"] = [asset]
        s = await env.night(0)
        a = env.row("ZZZ", "arm")
        assert a["status"] == "rejected" and a["reason"] == reason
        assert a["climax_high"] == 160.0 and a["stop_price"] == STOP            # the geometry is recorded anyway
        assert s["armed"] == [] and s["rejected"] == [{"ticker": "ZZZ", "reason": reason, "stage": "arm"}]
        await env.night(1)
        assert env.row("ZZZ", "trigger") is None                                   # a rejected episode never advances

    @pytest.mark.parametrize("exc", [
        RuntimeError("alpaca 503"),
        asyncio.TimeoutError(),
        ec.ExecutionUnreachable("execution call 'get_asset' failed over HTTP: ConnectError"),
        ec.ExecutionCallFailed("execution call 'get_asset' failed IN the execution service: APIError: 503"),
    ])
    async def test_a_broker_or_transport_error_is_retried_then_an_infra_row_never_an_assumed_etb(self, env, exc):
        # Rows are insert-once, so a row written on night 0 would forfeit the climax for good while the arm window
        # still has two nights to run: while a later night can arm it, a failed READ writes NOTHING and the
        # candidate is retried. Only on the last window night (2 sessions after D0) is the infra row written.
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP)
        env.plan["ZZZ"] = [exc]                                # the broker stays unreadable every night
        for k in (0, 1):
            s = await env.night(k)
            assert env.row("ZZZ", "arm") is None, k            # nothing decided yet
            assert s["armed"] == [] and s["rejected"] == [] and s["errors"] == []     # `errors` would page
            assert [(d["ticker"], d["reason"], d["sessions_since"]) for d in s["deferred"]] == \
                [("ZZZ", "infra:borrow_check_failed", k)]
            assert type(exc).__name__ in s["deferred"][0]["error"]
        assert len(env.borrow_calls) == 2
        s = await env.night(2)                                 # the last night the window allows
        a = env.row("ZZZ", "arm")
        assert a["status"] == "rejected" and a["reason"] == "infra:borrow_check_failed"
        assert a["shortable"] is None and a["easy_to_borrow"] is None          # nothing was learned, nothing recorded
        assert type(exc).__name__ in a["detail"]["borrow_error"]
        assert s["armed"] == [] and s["errors"] == [] and s["deferred"] == []  # a recorded outcome, not a crashed run
        assert s["rejected"] == [{"ticker": "ZZZ", "reason": "infra:borrow_check_failed", "stage": "arm"}]
        await env.night(3)
        assert env.row("ZZZ", "trigger") is None and len(env.borrow_calls) == 3     # a rejected episode never advances

    async def test_a_transient_borrow_failure_on_the_arm_night_still_arms_the_next_night(self, env):
        env.load("ZZZ", [(150, 152, 141, 148)] + TRIGGER_THEN_TIME_STOP[1:])        # D1 does not break 140
        env.plan["ZZZ"] = [ec.ExecutionUnreachable("down"), ETB]
        s0 = await env.night(0)
        assert env.row("ZZZ", "arm") is None and len(s0["deferred"]) == 1 and s0["armed"] == []
        s1 = await env.night(1)
        a = env.row("ZZZ", "arm")
        assert a["status"] == "armed" and a["event_date"] == D[1] and a["detail"]["late_sessions"] == 1
        assert s1["armed"] == [{"ticker": "ZZZ", "level": 141.0, "stop": STOP}] and s1["deferred"] == []
        # a LATE arm: the level on the row is the one in force (D1's low), not the climax day's
        assert (a["prior_day_low"], a["limit_price"]) == (141.0, psh.short_limit_price(141.0))
        assert a["climax_low"] == 140.0
        await env.night(2)                                     # D2 (138,145,130,132) breaks 141 -> triggers after the late arm
        assert env.row("ZZZ", "trigger")["status"] == "triggered"
        assert [r["row_kind"] for r in env.rows] == ["arm", "trigger"]

    async def test_a_deferral_is_in_the_audit_row_but_a_deferral_alone_pages_nothing(self, env):
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP)
        env.plan["ZZZ"] = [ec.ExecutionUnreachable("down")]
        s = await env.night(0)
        assert "deferred 1" in env.audit[0][1] and '"deferred": [{' in env.audit[0][2]
        assert s["errors"] == []                               # the job pages on `errors` only (see TestJobWiring)

    async def test_only_an_infra_failure_defers_a_definite_answer_is_written_at_once(self, env):
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP)
        env.plan["ZZZ"] = [HTB]
        s = await env.night(0)
        assert env.row("ZZZ", "arm")["reason"] == "borrow:hard_to_borrow" and s["deferred"] == []

    async def test_a_late_arm_records_the_level_in_force_not_the_climax_days_low(self, env):
        env.load("ZZZ", [(150, 152, 142, 148)] + TRIGGER_THEN_TIME_STOP[1:])
        await env.night(1)                                     # first met on D1's night (a carried-over candidate)
        a = env.row("ZZZ", "arm")
        assert a["status"] == "armed" and a["climax_low"] == 140.0
        assert (a["prior_day_low"], a["limit_price"]) == (142.0, psh.short_limit_price(142.0))
        assert a["stop_price"] == STOP                         # the stop is the climax high + buffer either way

    @pytest.mark.parametrize("mcap,reason", [
        (249_999_999, "filter:mcap_too_small"),
        (50_000_000, "filter:mcap_too_small"),
        (None, "filter:mcap_unknown"),
    ])
    async def test_the_250m_floor_is_a_hard_reject_and_skips_the_borrow_read(self, env, mcap, reason):
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP, mcap=mcap)
        await env.night(0)
        a = env.row("ZZZ", "arm")
        assert a["status"] == "rejected" and a["reason"] == reason and a["market_cap"] == mcap
        assert env.borrow_calls == []                                               # rejected before any broker read

    async def test_exactly_250m_passes(self, env):
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP, mcap=250_000_000)
        await env.night(0)
        assert env.row("ZZZ", "arm")["status"] == "armed"

    async def test_an_excluded_climax_never_arms(self, env):
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP, excluded="acquisition: buyout")
        s = await env.night(0)
        assert env.rows == [] and s["armed"] == [] and env.borrow_calls == []

    async def test_a_name_already_closed_above_the_climax_high_is_rejected_not_armed(self, env):
        env.load("ZZZ", [(150, 162, 141, 161)], scan_date=D[0])
        await env.night(1)                                  # first met on D1's night, after it already invalidated
        a = env.row("ZZZ", "arm")
        assert a["status"] == "rejected" and a["reason"] == "invalidated_before_arm"
        assert env.borrow_calls == []

    async def test_a_candidate_past_its_window_is_dropped_without_a_row(self, env):
        env.load("ZZZ", [(150, 152, 141, 148)] * 4)
        s = await env.night(3)                              # 3 sessions after the climax: nothing left to arm for
        assert env.rows == [] and s["stale"] == 1

    async def test_a_candidate_whose_climax_bar_is_missing_is_counted_as_an_error_not_swallowed(self, env):
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP)
        env.bars["ZZZ"] = [b for b in env.bars["ZZZ"] if b["trade_date"] != D[0]]
        s = await env.night(0)
        assert env.rows == [] and len(s["errors"]) == 1 and "ZZZ" in s["errors"][0]

    @pytest.mark.parametrize("asset,key", [(ETB, "armed"), (HTB, "rejected")])
    async def test_a_repeated_decision_is_not_counted_or_written_twice(self, env, asset, key, monkeypatch):
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP)
        env.plan["ZZZ"] = [asset]

        async def always(trade_date, lookback_days=7):          # a duplicate scan row / a racing second run
            return list(env.cands)
        monkeypatch.setattr(db, "get_parabolic_short_new_candidates", always)
        first = await env.night(0)
        second = await env.night(0)
        assert len(first[key]) == 1 and second[key] == []
        assert len([r for r in env.rows if r["row_kind"] == "arm"]) == 1

    async def test_one_failing_episode_does_not_stop_the_others(self, env):
        env.load("BAD", TRIGGER_THEN_TIME_STOP)
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP)
        env.bars["BAD"] = None                              # the bars read blows up for BAD
        s = await env.night(0)
        assert env.row("ZZZ", "arm")["status"] == "armed"
        assert len(s["errors"]) == 1 and s["errors"][0].startswith("BAD decide")

    # ── ADR 0020 "NO adds, ever": one open episode per name ───────────────────────────────────────
    @staticmethod
    def _two_climaxes(env, d1_bar):
        """ZZZ: D0 climaxes (150,160,140,155); D1 is ALSO flagged a climax. `d1_bar` decides how D1 treats D0."""
        env.load("ZZZ", [d1_bar, (140, 148, 135, 138), (136, 140, 128, 130)])
        env.cands.append({"ticker": "ZZZ", "scan_date": D[1], "market_cap": 1_000_000_000, "cap_tier": "small",
                          "excluded_reason": None})

    async def test_a_second_climax_on_a_name_with_an_open_episode_is_rejected_by_name(self, env):
        # D1 is a record-volume gap-up climax that closes UNDER D0's high (158 < 160): D0's arm is not invalidated.
        self._two_climaxes(env, (156, 165, 150, 158))
        await env.night(0)
        s1 = await env.night(1)
        d1 = env.row("ZZZ", "arm", D[1])
        assert d1["status"] == "rejected" and d1["reason"] == "episode_already_open"
        assert d1["climax_high"] == 165.0 and d1["detail"]["open_episode"] is True      # geometry still recorded
        assert s1["rejected"] == [{"ticker": "ZZZ", "reason": "episode_already_open", "stage": "arm"}]
        assert len(env.borrow_calls) == 1                       # no broker read spent on it
        for k in (2, 3, 4, 5, 6):
            await env.night(k)
        kinds = [(r["climax_date"], r["row_kind"]) for r in env.rows]
        assert kinds.count((D[0], "trigger")) <= 1 and (D[1], "trigger") not in kinds and (D[1], "outcome") not in kinds
        assert sum(1 for r in env.rows if r["row_kind"] == "trigger") <= 1                # never two entries on one name
        assert [r["status"] for r in env.rows if r["row_kind"] == "arm"].count("armed") == 1

    async def test_an_open_triggered_position_also_blocks_a_new_episode_no_adds(self, env):
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP)                  # D0 arms; D1 triggers; held through D5
        env.cands.append({"ticker": "ZZZ", "scan_date": D[2], "market_cap": 1_000_000_000, "cap_tier": "small",
                          "excluded_reason": None})
        for k in (0, 1, 2):
            await env.night(k)
        assert env.row("ZZZ", "trigger")["status"] == "triggered" and env.row("ZZZ", "outcome") is None
        a = env.row("ZZZ", "arm", D[2])
        assert a["status"] == "rejected" and a["reason"] == "episode_already_open"

    async def test_the_prior_episode_closing_on_the_same_bar_does_not_block_the_new_climax(self, env):
        # D1 closes ABOVE D0's high (165 > 160): D0's arm is invalidated tonight - and D1 is the next, higher climax.
        # Advance-then-decide: D0 is closed before the open-episode check reads, so D1 arms.
        self._two_climaxes(env, (150, 170, 141, 165))
        await env.night(0)
        s1 = await env.night(1)
        assert env.row("ZZZ", "outcome")["reason"] == "invalidated"
        assert env.row("ZZZ", "arm", D[1])["status"] == "armed" and s1["rejected"] == []
        assert len(env.borrow_calls) == 2

    async def test_a_catch_up_night_arms_the_earlier_climax_and_rejects_the_later_one(self, env):
        self._two_climaxes(env, (156, 165, 150, 158))
        env.cands.reverse()                                     # the real reader returns newest first
        s = await env.night(1)                                  # the shadow first runs on D1's night
        assert env.row("ZZZ", "arm", D[0])["status"] == "armed"
        assert env.row("ZZZ", "arm", D[1])["reason"] == "episode_already_open"
        assert [a["ticker"] for a in s["armed"]] == ["ZZZ"]

    async def test_a_different_name_is_never_blocked_by_an_open_episode(self, env):
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP)
        env.load("AAA", TRIGGER_THEN_TIME_STOP)
        await env.night(0)
        assert env.row("ZZZ", "arm")["status"] == "armed" and env.row("AAA", "arm")["status"] == "armed"

    async def test_a_name_may_arm_again_once_its_earlier_episode_has_an_outcome(self, env):
        env.load("ZZZ", [(150, 152, 141, 148), (150, 153, 142, 149), (150, 154, 143, 150), (150, 150, 140, 145)])
        for k in (0, 1, 2, 3):
            await env.night(k)                                  # D0's arm expires untriggered on D3
        assert env.row("ZZZ", "outcome")["reason"] == "expired_untriggered"
        env.cands.append({"ticker": "ZZZ", "scan_date": D[3], "market_cap": 1_000_000_000, "cap_tier": "small",
                          "excluded_reason": None})
        await env.night(3)
        assert env.row("ZZZ", "arm", D[3])["status"] == "armed"


@pytest.mark.asyncio
class TestLifecycle:
    async def test_arm_trigger_settle_over_six_nights(self, env):
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP)
        s0 = await env.night(0)
        assert len(s0["armed"]) == 1 and not s0["triggered"] and not s0["settled"]

        s1 = await env.night(1)
        t = env.row("ZZZ", "trigger")
        assert t["status"] == "triggered" and t["event_date"] == D[1] and t["entry_price"] == 140.0
        assert t["prior_day_low"] == 140.0 and t["limit_price"] == 139.3
        assert t["risk_per_share"] == pytest.approx(R) and t["stop_price"] == STOP
        assert t["detail"]["kind"] == "intraday"
        assert s1["triggered"] == [{"ticker": "ZZZ", "entry": 140.0, "stop": STOP}] and not s1["armed"]

        for k in (2, 3, 4):                                  # holding: nothing new to say
            s = await env.night(k)
            assert not (s["armed"] or s["triggered"] or s["settled"] or s["closed"]), k
        assert env.row("ZZZ", "outcome") is None

        s5 = await env.night(5)
        o = env.row("ZZZ", "outcome")
        assert (o["status"], o["reason"], o["event_date"], o["exit_date"]) == ("settled", "time_stop", D[5], D[5])
        assert (o["entry_price"], o["exit_price"], o["sessions_held"], o["flush_taken"]) == (140.0, 110.0, 5, True)
        assert o["realized_r"] == pytest.approx(1 / 3 + (2 / 3) * (30.0 / R)) and o["realized_r"] == pytest.approx(1.2003, abs=1e-3)
        assert s5["settled"] == [{"ticker": "ZZZ", "reason": "time_stop", "realized_r": pytest.approx(o["realized_r"])}]

        before = len(env.rows)
        for k in (5, 6):                                     # re-running / later nights never duplicate or reopen it
            s = await env.night(k)
            assert not (s["armed"] or s["triggered"] or s["settled"] or s["closed"])
        assert len(env.rows) == before == 3
        assert [r["row_kind"] for r in env.rows] == ["arm", "trigger", "outcome"]
        assert len(env.borrow_calls) == 2                    # once at arm, once at trigger - no more

    async def test_catching_up_after_missed_nights_gives_the_same_settlement(self, env):
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP)
        await env.night(0)
        await env.night(1)
        await env.night(5)                                   # nights 2-4 never ran
        o = env.row("ZZZ", "outcome")
        assert o["reason"] == "time_stop" and o["realized_r"] == pytest.approx(1 / 3 + (2 / 3) * (30.0 / R))

    async def test_every_night_writes_one_audit_row_even_when_nothing_happens(self, env):
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP)
        await env.night(0)
        await env.night(2)
        assert [a[0] for a in env.audit] == ["parabolic_short_shadow_run"] * 2
        assert "armed 1" in env.audit[0][1] and "armed 0" in env.audit[1][1]

    async def test_the_stop_settles_with_a_loss(self, env):
        env.load("ZZZ", [(150, 153, 138, 139), (141, 155, 139, 150)])
        for k in (0, 1, 2):
            await env.night(k)
        o = env.row("ZZZ", "outcome")
        assert (o["status"], o["reason"], o["exit_price"]) == ("settled", "trail_stop", 153.0)
        assert o["realized_r"] == pytest.approx(-13.0 / R) and o["flush_taken"] is False

    async def test_an_untriggered_arm_expires_with_an_outcome_row_and_no_message_worth_sending(self, env):
        env.load("ZZZ", [(150, 152, 141, 148), (150, 153, 142, 149), (150, 154, 143, 150)])
        sums = [await env.night(k) for k in (0, 1, 2, 3)]
        o = env.row("ZZZ", "outcome")
        assert (o["status"], o["reason"], o["event_date"]) == ("closed_untriggered", "expired_untriggered", D[3])
        assert o.get("realized_r") is None and env.row("ZZZ", "trigger") is None
        assert sums[3]["closed"] == [{"ticker": "ZZZ", "reason": "expired_untriggered", "realized_r": None}]
        assert sums[3]["settled"] == []                      # not a settled TRADE

    async def test_an_invalidation_closes_the_arm(self, env):
        env.load("ZZZ", [(150, 162, 141, 161)])
        await env.night(0)
        await env.night(1)
        o = env.row("ZZZ", "outcome")
        assert (o["status"], o["reason"]) == ("closed_untriggered", "invalidated")

    async def test_the_borrow_check_is_repeated_at_the_trigger_and_an_htb_flip_skips_the_entry(self, env):
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP)
        env.plan["ZZZ"] = [ETB, HTB]                          # easy at arm, hard to borrow by the trigger
        await env.night(0)
        s = await env.night(1)
        t = env.row("ZZZ", "trigger")
        assert t["status"] == "skipped" and t["reason"] == "borrow:hard_to_borrow" and t["easy_to_borrow"] is False
        o = env.row("ZZZ", "outcome")
        assert (o["status"], o["reason"]) == ("closed_untriggered", "trigger_skipped")
        assert s["triggered"] == [] and s["rejected"] == [{"ticker": "ZZZ", "reason": "borrow:hard_to_borrow", "stage": "trigger"}]
        assert len(env.borrow_calls) == 2
        await env.night(5)
        assert len(env.rows) == 3                             # closed for good

    async def test_a_broker_error_at_the_trigger_is_an_infra_skip_never_an_assumed_fill(self, env):
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP)
        env.plan["ZZZ"] = [ETB, ec.ExecutionUnreachable("down")]
        await env.night(0)
        s = await env.night(1)
        t = env.row("ZZZ", "trigger")
        assert t["status"] == "skipped" and t["reason"] == "infra:borrow_check_failed"
        assert s["triggered"] == [] and s["errors"] == []
        assert env.row("ZZZ", "outcome")["reason"] == "trigger_skipped"

    async def test_a_crash_between_the_trigger_row_and_its_outcome_is_finished_next_night(self, env):
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP)
        env.plan["ZZZ"] = [ETB, HTB]
        await env.night(0)
        orig = env.insert_parabolic_short_shadow_row

        async def die_on_outcome(row):
            if row["row_kind"] == "outcome":
                raise RuntimeError("db hiccup")
            return await orig(row)
        env.insert_parabolic_short_shadow_row = die_on_outcome
        db.insert_parabolic_short_shadow_row = die_on_outcome
        s = await env.night(1)
        assert env.row("ZZZ", "trigger")["status"] == "skipped" and env.row("ZZZ", "outcome") is None
        assert len(s["errors"]) == 1
        db.insert_parabolic_short_shadow_row = orig
        await env.night(2)
        assert env.row("ZZZ", "outcome")["reason"] == "trigger_skipped"

    async def test_an_earnings_date_inside_the_hold_exits_at_that_close(self, env):
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP)

        async def earnings_after_d3(ticker, session):
            return session == D[3]
        await env.night(0)
        await env.night(1)
        for k in (2, 3):
            await psh.run_parabolic_short_shadow(D[k], earnings_checker=earnings_after_d3)
        o = env.row("ZZZ", "outcome")
        assert (o["reason"], o["event_date"], o["exit_price"], o["sessions_held"]) == ("earnings_exit", D[3], 118.0, 3)

    async def test_an_unknowable_earnings_calendar_does_not_force_an_exit_but_is_recorded(self, env):
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP)

        async def unknown(ticker, session):
            return None
        await env.night(0)
        for k in (1, 5):
            await psh.run_parabolic_short_shadow(D[k], earnings_checker=unknown)
        o = env.row("ZZZ", "outcome")
        assert o["reason"] == "time_stop" and o["detail"]["earnings_unknown_sessions"]

    async def test_a_split_that_restates_the_bars_voids_the_episode_instead_of_booking_a_made_up_r(self, env):
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP)
        await env.night(0)
        await env.night(1)
        env.bars["ZZZ"] = [{**b, **{k: b[k] / 2 for k in ("open_price", "high_price", "low_price", "close")}}
                           for b in env.bars["ZZZ"]]               # a 2-for-1 restates the whole history
        await env.night(2)
        o = env.row("ZZZ", "outcome")
        assert (o["status"], o["reason"]) == ("voided", "void_restated") and o.get("realized_r") is None

    async def test_a_trigger_row_the_replay_can_no_longer_reproduce_is_voided_by_name(self, env):
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP)
        await env.night(0)
        await env.night(1)
        env.bars["ZZZ"][N_HIST + 1] = bar(D[1], 150, 153, 141, 148)    # a corrected bar: D1 no longer breaks 140 ...
        env.bars["ZZZ"][N_HIST + 2] = bar(D[2], 150, 153, 142, 149)    # ... and D2 does not break D1's (corrected) low 141
        await env.night(2)
        o = env.row("ZZZ", "outcome")
        assert (o["status"], o["reason"]) == ("voided", "void_replay_mismatch")

    async def test_a_bar_that_loses_its_prices_stalls_the_episode_it_does_not_void_it(self, env):
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP)
        await env.night(0)
        await env.night(1)
        env.bars["ZZZ"][N_HIST + 1]["low_price"] = None        # a hole, not a correction
        s = await env.night(2)
        assert env.row("ZZZ", "outcome") is None and s["errors"] == []
        env.bars["ZZZ"][N_HIST + 1]["low_price"] = 138.0       # the hole is filled: the episode resumes
        await env.night(5)
        assert env.row("ZZZ", "outcome")["reason"] == "time_stop"

    async def test_an_episode_whose_bars_stop_arriving_is_voided_not_left_open_forever(self, env):
        env.load("ZZZ", [(150, 153, 138, 139)])
        await env.night(0)
        await psh.run_parabolic_short_shadow(D[0] + timedelta(days=31), earnings_checker=_never_earnings)
        o = env.row("ZZZ", "outcome")
        assert o["status"] == "voided" and o["reason"] == "void_data_gap"

    async def test_a_disabled_strategy_runs_nothing(self, env, monkeypatch):
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP)

        async def off(_):
            return False
        monkeypatch.setattr("agents.market_intelligence.strategies.registry.should_run", off)
        s = await env.night(0)
        assert s["disabled"] is True and env.rows == [] and env.borrow_calls == [] and env.audit == []


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# 3. digest line, job wiring, boundary
# ═════════════════════════════════════════════════════════════════════════════════════════════════

from agents.market_intelligence import parabolic_detector as pdx  # noqa: E402


class TestDigestLine:
    def test_silent_unless_something_armed_triggered_or_settled(self):
        assert pdx._fmt_shadow_lines(None) == []
        quiet = {"armed": [], "triggered": [], "settled": [], "closed": [{"ticker": "A", "reason": "expired_untriggered"}],
                 "rejected": [{"ticker": "B", "reason": "borrow:hard_to_borrow", "stage": "arm"}], "errors": []}
        assert pdx._fmt_shadow_lines(quiet) == []

    def test_one_line_with_all_three_events_and_no_raw_underscores(self):
        line, = pdx._fmt_shadow_lines({
            "armed": [{"ticker": "AAA", "level": 140.0, "stop": 163.07}],
            "triggered": [{"ticker": "BBB", "entry": 140.0, "stop": 163.07}],
            "settled": [{"ticker": "CCC", "reason": "time_stop", "realized_r": 1.2003},
                        {"ticker": "DDD", "reason": "trail_stop", "realized_r": -0.5635}],
        })
        assert line.startswith("Short shadow (simulated, no orders): ")
        assert "armed `AAA`" in line and "triggered `BBB` @ 140.00" in line
        assert "`CCC` +1.2R (time stop)" in line and "`DDD` -0.6R (trail stop)" in line
        assert "_" not in line.replace("`", "")

    @pytest.mark.asyncio
    async def test_a_shadow_event_alone_sends_exactly_one_message_with_the_line(self, monkeypatch):
        sent = []

        async def _send(text, *a, **k):
            sent.append(text)
        monkeypatch.setattr("agents.market_intelligence.briefing.send_telegram_message", _send)
        shadow = {"armed": [{"ticker": "AAA", "level": 140.0, "stop": 163.07}], "triggered": [], "settled": []}
        await pdx.send_parabolic_digest({"climax": [], "anticipation": []}, shadow=shadow)
        assert len(sent) == 1 and "Short shadow" in sent[0] and "No parabolic-short setups" not in sent[0]

    @pytest.mark.asyncio
    async def test_the_line_rides_in_the_same_message_as_the_scan_sections(self, monkeypatch):
        sent = []

        async def _send(text, *a, **k):
            sent.append(text)
        monkeypatch.setattr("agents.market_intelligence.briefing.send_telegram_message", _send)
        climax = {"ticker": "XYZ", "prior_move_pct": 3.0, "ext_vs_sma50": 2.1, "cap_tier": "small", "score": 4}
        shadow = {"armed": [], "triggered": [], "settled": [{"ticker": "CCC", "reason": "stop", "realized_r": -1.0}]}
        await pdx.send_parabolic_digest({"climax": [climax]}, shadow=shadow)
        assert len(sent) == 1 and "CLIMAX" in sent[0] and "`CCC` -1.0R (stop)" in sent[0]

    @pytest.mark.asyncio
    async def test_all_quiet_still_sends_nothing(self, monkeypatch):
        send = AsyncMock()
        monkeypatch.setattr("agents.market_intelligence.briefing.send_telegram_message", send)
        await pdx.send_parabolic_digest({"climax": [], "anticipation": []})
        await pdx.send_parabolic_digest({"climax": []}, shadow={"armed": [], "triggered": [], "settled": []})
        send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_filtered_only_footer_is_unchanged(self, monkeypatch):
        sent = []

        async def _send(text, *a, **k):
            sent.append(text)
        monkeypatch.setattr("agents.market_intelligence.briefing.send_telegram_message", _send)
        ex = {"ticker": "OGN", "stage": "climax", "excluded_source": "news_check", "excluded_reason": "buyout"}
        await pdx.send_parabolic_digest({"excluded": [ex]})
        assert len(sent) == 1 and "FILTERED (1)" in sent[0] and "No parabolic-short setups today" in sent[0]


@pytest.mark.asyncio
class TestJobWiring:
    @pytest.fixture
    def job(self, monkeypatch):
        from agents.market_intelligence import collector, scheduler
        calls = {"order": []}
        monkeypatch.setattr(collector, "et_today", lambda: D[0])

        async def scan(td):
            calls["order"].append(("scan", td))
            return {"climax": [], "anticipation": []}

        async def shadow(td):
            calls["order"].append(("shadow", td))
            return {"armed": [], "triggered": [], "settled": [], "errors": []}

        async def digest(by_stage, shadow=None):
            calls["order"].append(("digest", shadow))
        calls["notify"] = AsyncMock()
        monkeypatch.setattr(pdx, "run_parabolic_scan", scan)
        monkeypatch.setattr(pdx, "send_parabolic_digest", digest)
        monkeypatch.setattr(psh, "run_parabolic_short_shadow", shadow)
        monkeypatch.setattr(scheduler, "notify_job_failure", calls["notify"])
        calls["scheduler"] = scheduler
        calls["scan"], calls["shadow"], calls["digest"] = scan, shadow, digest
        return calls

    async def test_the_shadow_runs_after_the_scan_and_feeds_the_same_digest(self, job):
        await job["scheduler"]._parabolic_scan_job()
        assert [c[0] for c in job["order"]] == ["scan", "shadow", "digest"]
        assert job["order"][0][1] == job["order"][1][1] == D[0]
        assert job["order"][2][1] == {"armed": [], "triggered": [], "settled": [], "errors": []}
        job["notify"].assert_not_awaited()

    async def test_a_shadow_crash_pages_on_its_own_and_the_digest_still_goes_out(self, job, monkeypatch):
        async def boom(td):
            raise RuntimeError("shadow bug")
        monkeypatch.setattr(psh, "run_parabolic_short_shadow", boom)
        await job["scheduler"]._parabolic_scan_job()
        assert [c[0] for c in job["order"]] == ["scan", "digest"] and job["order"][1][1] is None
        job["notify"].assert_awaited_once()
        assert job["notify"].await_args.args[0] == "parabolic_short_shadow" and "shadow bug" in job["notify"].await_args.args[1]

    async def test_episode_errors_page_without_blocking_the_digest(self, job, monkeypatch):
        async def partial(td):
            return {"armed": [], "triggered": [], "settled": [], "errors": ["ZZZ advance: KeyError: 'x'"]}
        monkeypatch.setattr(psh, "run_parabolic_short_shadow", partial)
        await job["scheduler"]._parabolic_scan_job()
        assert [c[0] for c in job["order"]] == ["scan", "digest"]
        job["notify"].assert_awaited_once()
        assert "ZZZ advance" in job["notify"].await_args.args[1]

    async def test_a_scan_crash_pages_but_open_episodes_still_settle(self, job, monkeypatch):
        async def boom(td):
            raise RuntimeError("scan bug")
        monkeypatch.setattr(pdx, "run_parabolic_scan", boom)
        await job["scheduler"]._parabolic_scan_job()
        assert [c[0] for c in job["order"]] == ["shadow", "digest"]
        job["notify"].assert_awaited_once()
        assert job["notify"].await_args.args[1] == "scan bug"


class TestBoundary:
    def test_the_module_loads_no_broker_code_beyond_the_skip_reason_vocabulary(self):
        r = subprocess.run(
            [sys.executable, "-c",
             "import sys; import agents.market_intelligence.parabolic_short_shadow; "
             "bad = [m for m in sys.modules if m.startswith('agents.market_intelligence.broker') "
             "and m not in ('agents.market_intelligence.broker', 'agents.market_intelligence.broker.skip_reasons')]; "
             "print(bad); sys.exit(1 if bad else 0)"],
            cwd=REPO, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr

    def test_the_execution_boundary_gate_is_clean(self):
        sys.path.insert(0, str(REPO))
        from scripts import check_execution_boundary as gate
        assert gate.find_violations() == []

    def test_the_execution_image_does_not_load_the_module(self):
        listed = (REPO / "scripts" / "exec_loaded_modules.txt").read_text()       # a DATA list, not source
        assert "parabolic_short_shadow" not in listed
        r = subprocess.run(
            [sys.executable, "-c",
             "import sys; import agents.market_intelligence.scheduler; "
             "sys.exit(int('agents.market_intelligence.parabolic_short_shadow' in sys.modules))"],
            cwd=REPO, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr

    def test_no_order_function_is_importable_into_the_module_namespace(self):
        # Introspection of the LIVE module object (not its source text): a module-level `from ...alpaca_client import
        # place_market_sell` (or an alias of any order / trade-state function) would show up here. Function-local
        # imports are caught by the execution-boundary gate above, and every executed path by the strict _Facade
        # (any attribute but get_asset raises) in the lifecycle tests.
        forbidden = {
            "place_bracket_order", "place_stop_order", "place_market_on_open_sell", "place_market_sell",
            "place_limit_sell", "place_oco_sell", "place_limit_buy_with_stop", "replace_order", "cancel_order",
            "close_position", "submit_order", "trigger_orb_entry", "trigger_lowcap_paper_entry",
            "execute_partial_exit", "place_timestop_sell", "cancel_unfilled_entries", "sync_positions",
            "sync_positions_for_mode", "record_skipped_trade", "subscribe_orb_candidate",
            "reset_bar_stream_daily_state", "get_trading_client", "alpaca_client", "order_manager", "entry_pipeline",
        }
        assert not forbidden & set(vars(psh)), forbidden & set(vars(psh))
        assert psh.execution_client is ec                  # the facade module itself, nothing wrapped or aliased

    @pytest.mark.asyncio
    async def test_the_shadow_touches_no_database_function_but_its_five(self, env):
        # `Env` replaces exactly five db.* functions and makes `db.get_pool` raise: a full lifecycle (arm, trigger,
        # borrow re-check, settle, an HTB reject, a mcap reject) completing means the module reached for nothing else
        # - no trade, order, position or strategy table.
        env.load("ZZZ", TRIGGER_THEN_TIME_STOP)
        env.load("HTB", TRIGGER_THEN_TIME_STOP)
        env.load("MIC", TRIGGER_THEN_TIME_STOP, mcap=10_000_000)
        env.plan["HTB"] = [HTB]
        for k in range(0, 7):
            s = await env.night(k)
            assert s["errors"] == [], (k, s["errors"])
        assert {r["row_kind"] for r in env.rows} == {"arm", "trigger", "outcome"}
        assert len(env.rows) == 3 + 1 + 1                  # ZZZ: arm/trigger/outcome; HTB and MIC: a rejected arm each


class TestRegistryAndSchema:
    def test_the_registered_adr_constants_match_the_module(self):
        sys.path.insert(0, str(REPO))
        from scripts.check_gate_provenance import evaluate_entry
        from scripts.gate_provenance_registry import GATE_REGISTRY
        mine = [e for e in GATE_REGISTRY if e["id"].startswith("parabolic_short_shadow.")]
        assert {e["name"] for e in mine} == {
            "SHORT_MCAP_FLOOR_USD", "STOP_BUFFER_PCT_CAP", "STOP_BUFFER_ATR_MULT", "ARM_WINDOW_SESSIONS",
            "TIME_STOP_SESSIONS", "FLUSH_COVER_DENOM", "FLUSH_R_MULT", "SHORT_RISK_FRACTION"}
        for e in mine:
            assert getattr(psh, e["name"]) == e["value"], e["id"]
            assert evaluate_entry(e, REPO) == [], e["id"]

    def test_every_written_column_exists_in_the_ddl_and_the_insert_is_complete(self):
        import re
        body = db._PARABOLIC_SHORT_SHADOW_DDL
        ddl_cols = set(re.findall(r"^\s{8}(\w+)\s+(?:SERIAL|TEXT|DATE|DOUBLE|BIGINT|BOOLEAN|INT|JSONB|TIMESTAMPTZ)",
                                  body, re.M))
        assert set(db.PS_SHADOW_COLS) <= ddl_cols
        assert db.PS_SHADOW_INSERT_SQL.count("$") == len(db.PS_SHADOW_COLS)
        assert db.PS_SHADOW_INSERT_SQL.count("::jsonb") == 1 and "DO NOTHING RETURNING id" in db.PS_SHADOW_INSERT_SQL

    @pytest.mark.asyncio
    async def test_insert_reports_new_vs_existing_and_encodes_the_detail_once(self, monkeypatch):
        from tests.conftest import make_mock_pool
        pool, conn = make_mock_pool()
        conn.fetchval = AsyncMock(side_effect=[7, None])
        monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
        row = {"ticker": "ZZZ", "climax_date": D[0], "row_kind": "arm", "event_date": D[0], "status": "armed",
               "detail": {"d": D[0]}}
        assert await db.insert_parabolic_short_shadow_row(row) is True
        assert await db.insert_parabolic_short_shadow_row(row) is False
        args = conn.fetchval.await_args_list[0].args
        assert args[0] == db.PS_SHADOW_INSERT_SQL and len(args) == 1 + len(db.PS_SHADOW_COLS)
        assert args[1 + db.PS_SHADOW_COLS.index("detail")] == {"d": str(D[0])}     # a dict, not a pre-dumped string

    @pytest.mark.asyncio
    async def test_the_candidate_reader_asks_only_for_unexcluded_climax_rows_without_an_arm_row(self, monkeypatch):
        from tests.conftest import make_mock_pool
        pool, conn = make_mock_pool()
        conn.fetch = AsyncMock(return_value=[])
        monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
        await db.get_parabolic_short_new_candidates(D[1])
        sql = " ".join(conn.fetch.await_args.args[0].split())
        assert "stage = 'climax'" in sql and "excluded_reason IS NULL" in sql
        assert "NOT EXISTS" in sql and "row_kind = 'arm'" in sql

    @pytest.mark.asyncio
    async def test_the_weekly_purge_never_deletes_the_shadow_table(self, monkeypatch):
        executed = []

        async def fake_execute(sql, cutoff):
            executed.append(sql)
            return "DELETE 0"
        conn = MagicMock()
        conn.execute = fake_execute
        pool = MagicMock()
        pool.acquire = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
        await db.purge_old_data()
        assert executed and not any("mi_parabolic_short_shadow" in s for s in executed)
