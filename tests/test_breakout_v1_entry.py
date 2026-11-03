"""Breakout v1 PAPER phase 2 part A (B4 + B5, build 2026-10-30) — the strategy row, the four paper walls, the
`orh5` entry, F1, the day-low stop kept until the fill, the 15:55 cancel, and the shared-code defaults.

Owner of the rules: docs/setups/consolidation_breakout.md (his PAPER GO 2026-10-28, F1 / F2 RULED 2026-10-29).
Parts:
  1. the pure arithmetic: the opening range and level, the abstains, F1, the stop on the cent, parity with
     `consolidation_breakout._entry_one`'s `orh5` (level, stop at the fill, the width rule), the curve, the sizing
     (EP's arithmetic), the re-size on a lower stop;
  2. the walls (its own list table only; phase 'paper' resolving to 'paper'; the funnel bound to paper; the paper
     order-id family), the pre-flight, the stop switch;
  3. the shared code: the funnel's `bar_fetcher` default (EP + the small-cap lane unchanged), the exit stamp, the
     #500 price-aware submit on a breakout row, the 10:00 ET cleanup's exclusion by signal type;
  4. the minute job: a new low re-prices (cancel confirmed BEFORE the new buy — never two live buys), a racing
     fill is never re-placed, too wide / volume lapse / 15:55 cancel with their named reasons, restart from broker
     truth, an orphan order is cancelled, the volume hold, the no-opening-range abstain;
  5. the trade stream: a marked planned cancel is not recorded as a broker kill; an unmarked one (EP) is unchanged;
  6. the strategy row, the job registration, the preflight SQL copies.
"""
from __future__ import annotations

import asyncio
import json
import random
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from agents.market_intelligence import consolidation_breakout as cb
from agents.market_intelligence import db
from agents.market_intelligence.broker import breakout_v1_entry as be
from agents.market_intelligence.broker import entry_pipeline as ep
from agents.market_intelligence.broker import live_tracker as lt
from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker.breakout_v1_volume_curve import CUM_SHARE
from agents.market_intelligence.strategies.registry import Strategy

_ET = ZoneInfo("America/New_York")
_REPO = Path(__file__).resolve().parent.parent
TODAY = date(2026, 11, 2)          # a Monday
PREV = date(2026, 10, 30)
SID = "breakout_v1"


def _bar(m: int, o: float, h: float, l: float, c: float, v: float, d: date = TODAY) -> dict:
    return {"t_et": datetime(d.year, d.month, d.day, 9, 30, tzinfo=_ET) + timedelta(minutes=m),
            "open": o, "high": h, "low": l, "close": c, "volume": v}


def _flat_bars(n: int, *, low: float = 9.80, high: float = 10.00, vol: float = 10_000.0) -> list[dict]:
    return [_bar(m, 9.90, high, low, 9.90, vol) for m in range(n)]


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 1. pure arithmetic
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _mins(bars, last):
    return be.bars_by_minute(bars, TODAY, last)


def test_opening_range_level_and_stop_from_the_first_five_minutes():
    bars = [_bar(0, 10.0, 10.20, 9.90, 10.1, 5e4), _bar(1, 10.1, 10.30, 10.0, 10.2, 3e4),
            _bar(2, 10.2, 10.25, 9.85, 10.0, 3e4), _bar(4, 10.0, 10.10, 9.95, 10.0, 2e4),
            _bar(5, 10.0, 10.05, 9.70, 9.8, 2e4)]
    st = be.evaluate(_mins(bars, 5), list_level=10.10, adr20=0.06, vol_bar=1e6, last_completed=5)
    assert st["orh5"] == 10.30 and st["orl5"] == 9.85          # minutes 0..4 only (minute 3 had no trade)
    assert st["level"] == 10.30                                 # max(ORH5, list level)
    assert st["day_low"] == 9.70 and st["stop"] == 9.70         # the day's low so far, minute 5 included
    st2 = be.evaluate(_mins(bars, 5), list_level=10.50, adr20=0.06, vol_bar=1e6, last_completed=5)
    assert st2["level"] == 10.50                                # the list level wins when higher
    # the minute in progress (minute 6) is never read
    bars.append(_bar(6, 9.8, 9.8, 5.00, 5.0, 1e9))
    assert be.evaluate(_mins(bars, 5), list_level=10.1, adr20=0.06, vol_bar=1e6, last_completed=5)["day_low"] == 9.70


def test_no_opening_range_minutes_abstains_only_once_later_minutes_prove_the_feed_answered():
    later_only = [_bar(7, 10.0, 10.1, 9.9, 10.0, 1e4)]
    st = be.evaluate(_mins(later_only, 9), list_level=10.0, adr20=0.05, vol_bar=1e5, last_completed=9)
    assert st["status"] == "abstain" and st["reason"].startswith("setup:no_opening_range_minutes")
    assert be.evaluate({}, list_level=10.0, adr20=0.05, vol_bar=1e5, last_completed=9)["status"] == "wait"


def test_at_0935_the_range_waits_for_the_0934_bar():
    st = be.evaluate(_mins(_flat_bars(4), 4), list_level=9.9, adr20=0.05, vol_bar=1e3, last_completed=4)
    assert st["status"] == "wait" and st["reason"] == "opening_range_not_settled"
    st = be.evaluate(_mins(_flat_bars(5), 4), list_level=9.9, adr20=0.05, vol_bar=1e3, last_completed=4)
    assert st["status"] == "ok"
    # a minute later a thin name with no 09:34 trade is judged on the bars it has
    st = be.evaluate(_mins(_flat_bars(4), 5), list_level=9.9, adr20=0.05, vol_bar=1e3, last_completed=5)
    assert st["status"] == "ok"


def test_too_wide_is_level_minus_day_low_over_adr20_of_the_level():
    bars = _flat_bars(6, low=9.50, high=10.00)              # level 10.00, stop 9.50: width 5.0%
    assert be.evaluate(_mins(bars, 5), list_level=9.0, adr20=0.0501, vol_bar=1, last_completed=5)["status"] == "ok"
    st = be.evaluate(_mins(bars, 5), list_level=9.0, adr20=0.0499, vol_bar=1, last_completed=5)
    assert st["status"] == "abstain" and st["reason"].startswith("setup:stop_too_wide")
    st = be.evaluate(_mins(bars, 5), list_level=9.0, adr20=None, vol_bar=1, last_completed=5)
    assert st["status"] == "abstain" and st["reason"].startswith("setup:stop_too_wide")    # fail closed


def test_f1_is_volume_so_far_against_the_volume_bar_times_the_curve_at_the_last_completed_minute():
    for m in (4, 29, 200, 389):
        need = 1_200_000.0 * CUM_SHARE[m]
        assert be.f1_permits(need, 1_200_000.0, m) == (True, need)
        assert be.f1_permits(need - 1, 1_200_000.0, m)[0] is False
    bars = _flat_bars(10, vol=10_000.0)                     # 100k shares by minute 9
    st = be.evaluate(_mins(bars, 9), list_level=9.9, adr20=0.05, vol_bar=1.2 * 1_000_000, last_completed=9)
    assert st["cum_volume"] == 100_000 and st["need_volume"] == pytest.approx(1.2e6 * CUM_SHARE[9])
    assert st["f1_ok"] is (100_000 >= 1.2e6 * CUM_SHARE[9])


def test_the_curve_is_390_monotone_minutes_in_the_unit_of_the_full_day_volume_bar_with_its_source_stated():
    """F1's units (review fix 2026-10-30): `vol_bar` is 1.2 x the mean FULL daily volume of the list's window (the last
    10 sessions since his 2026-11-02 ruling; the 50 sessions before — the unit is the same)
    (`mi_daily_closes`, extended hours + the 16:00 closing cross included), while the live numerator is regular-hours
    minute volume only. So the curve must be regular-hours volume through m / the FULL day's volume: it ends BELOW 1.0
    at 15:59 (the regular-hours share of a day, ~0.8). The first build divided by regular-hours volume and ended at
    exactly 1.0, which made F1 ask ~1.45-1.6x normal volume instead of his 1.2x."""
    from agents.market_intelligence.broker import breakout_v1_volume_curve as vc
    assert len(CUM_SHARE) == 390 and 0 < CUM_SHARE[0] < CUM_SHARE[4] < 0.1
    assert all(b >= a for a, b in zip(CUM_SHARE, CUM_SHARE[1:]))
    assert 0.70 < CUM_SHARE[-1] < 0.90                    # NOT 1.0: the denominator is the full day, not regular hours
    assert "full daily volume" in vc.DENOMINATOR.lower() and "full daily volume" in vc.METHOD.lower()
    assert vc.DATE_RANGE == ("2017-03-02", "2022-01-03") and vc.N_TICKER_DAYS > 100_000
    assert "cb702_pre_v2" in vc.SOURCE


def test_f1_admits_a_day_at_his_1_2x_full_day_volume_running_at_a_normal_intraday_pace():
    """A name whose day runs at exactly 1.2x its average FULL-day volume (the list's last-10-session average since
    2026-11-02), with a typical intraday profile (regular-hours volume through m = 1.2 x that average x CUM_SHARE[m]),
    is admitted at every minute; 2% under it is not. With the old regular-hours denominator the same day failed at
    every minute (it needed ~1.25x more volume)."""
    adv = 1_000_000.0
    vol_bar = 1.2 * adv
    for m in (4, 9, 29, 119, 239, 389):
        on_pace = 1.2 * adv * CUM_SHARE[m]
        assert be.f1_permits(on_pace, vol_bar, m)[0] is True
        assert be.f1_permits(0.98 * on_pace, vol_bar, m)[0] is False


def test_stop_sits_on_the_cent_at_or_below_the_low():
    assert be.stop_from_low(12.345) == 12.34
    assert be.stop_from_low(12.35) == 12.35                 # an exact cent is not pushed a cent lower
    assert be.stop_from_low(9.999) == 9.99


def test_parity_with_cb_entry_one_orh5_level_stop_and_width_at_the_fill():
    """On random minute paths (prices on the cent): wherever `cb._entry_one('orh5')` fills at the level (no gap
    through it), this module's state with the fill minute completed carries the same level, the same stop (the
    low through the fill minute) and the same too-wide decision. A gap-through fill (open above the level) is the
    #500 path's and is excluded; `no_opening_range_minutes` agrees separately."""
    rng = random.Random(1030)
    compared = 0
    for _ in range(600):
        px = rng.uniform(5, 50)
        mins, o, h, l, c, v = [], [], [], [], [], []
        for m in range(60):
            if rng.random() < 0.1:
                continue
            op = round(px, 2)
            px = max(1.0, px * (1 + rng.gauss(0.0005, 0.006)))
            hi = round(max(op, px) * (1 + abs(rng.gauss(0, 0.002))), 2)
            lo = round(min(op, px) * (1 - abs(rng.gauss(0, 0.002))), 2)
            mins.append(m); o.append(op); h.append(hi); l.append(lo); c.append(round(px, 2)); v.append(1000.0)
        if not mins:
            continue
        pivot = round(rng.uniform(0.97, 1.03) * h[0], 2)
        adr20 = rng.uniform(0.01, 0.08)
        ref = cb._entry_one(cb.minute_bars_from_lists(mins, o, h, l, c, v), "orh5", pivot, adr20, 0.0)
        bars = [_bar(m, o[i], h[i], l[i], c[i], v[i]) for i, m in enumerate(mins)]
        if ref["reason"] == "no_opening_range_minutes":
            assert be.evaluate(_mins(bars, 59), list_level=pivot, adr20=adr20, vol_bar=1,
                               last_completed=59)["reason"].startswith("setup:no_opening_range_minutes")
            continue
        if ref["status"] == "no_trigger" or ref.get("fill_minute") is None:
            continue
        fm = ref["fill_minute"]
        if o[mins.index(fm)] > ref["level"]:
            continue                                         # gapped through: the fill is the open (#500 path)
        st = be.evaluate(_mins(bars, fm), list_level=pivot, adr20=adr20, vol_bar=1, last_completed=fm)
        assert st["level"] == pytest.approx(ref["level"])
        assert st["stop"] == pytest.approx(ref["stop"])
        assert (st["status"] == "abstain" and st["reason"].startswith("setup:stop_too_wide")) is \
            (ref["reason"] == "too_wide")
        compared += 1
    assert compared >= 100, compared


def test_resize_never_grows_shares_or_the_dollar_risk_placed():
    assert be.resize_for_new_stop(100, 50.0, 10.0, 9.50) == 100           # 0.50 x 100 = $50 risk: unchanged
    assert be.resize_for_new_stop(100, 50.0, 10.0, 9.00) == 50            # the stop doubled: half the shares
    assert be.resize_for_new_stop(100, 500.0, 10.0, 9.90) == 100          # a budget above the cap never adds shares
    assert be.resize_for_new_stop(100, 50.0, 10.0, 10.0) == 0
    assert be.resize_for_new_stop(3, 1.0, 10.0, 8.0) == 0


@pytest.mark.asyncio
async def test_sizing_is_eps_arithmetic_when_the_stops_coincide(monkeypatch):
    """EP's `prepare_orb_order` sizes against entry - 2R; feed both builders the SAME entry and stop and they agree
    share for share and dollar for dollar (risk_pct x equity / risk per share, the 20% notional cap)."""
    import agents.market_intelligence.constants as consts
    monkeypatch.setattr(consts, "REGIME_SIZING_ENABLED", False)
    acct = AsyncMock(return_value={"equity": 100_000.0})
    monkeypatch.setattr(om.alpaca, "get_account", acct)
    monkeypatch.setattr(be.alpaca, "get_account", acct)
    monkeypatch.setattr(be.alpaca, "get_latest_trade", AsyncMock(return_value=None))
    monkeypatch.setattr(om, "_log_notional_cap_truncation", AsyncMock())
    monkeypatch.setattr(om, "validate_orb_entry", lambda h, l, atr: (True, None))   # stubbed module in tests
    regime = {"vix": 18.0, "qqq_ema_bullish": True, "regime": "Bull"}
    for orh, orl in ((10.50, 10.20), (50.0, 49.0), (3.10, 3.00)):
        ep_spec, _ = await om.prepare_orb_order({"ticker": "X"}, {"high": orh, "low": orl}, 100.0, regime,
                                                account_mode="paper", today=TODAY)
        stop = 2 * orl - orh
        bo_spec, why = await be.prepare_breakout_order({"ticker": "X"}, {"level": orh, "stop": stop, "low": orl},
                                                       regime, "paper", today=TODAY, adr20=0.9)
        assert why is None
        for k in ("shares", "risk_dollars", "risk_dollars_actual", "position_size", "entry_price", "limit_price"):
            assert bo_spec[k] == pytest.approx(ep_spec[k]), (orh, k)
        assert bo_spec["orb_high"] == orh and bo_spec["stop_loss_price"] == pytest.approx(stop)


@pytest.mark.asyncio
async def test_spec_builder_judges_the_width_at_the_500_fallback_fill(monkeypatch):
    monkeypatch.setattr(be.alpaca, "get_account", AsyncMock(return_value={"equity": 100_000.0}))
    monkeypatch.setattr(om, "_resolve_regime_risk_pct", AsyncMock(return_value=0.005))
    monkeypatch.setattr(be.alpaca, "get_latest_trade", AsyncMock(return_value={"price": 10.60}))
    spec, why = await be.prepare_breakout_order({"ticker": "X"}, {"level": 10.0, "stop": 9.60, "low": 9.6}, None,
                                                "paper", today=TODAY, adr20=0.05)
    assert spec is None and why.startswith("setup:stop_too_wide")         # 10.62 - 9.60 = 9.6% > 5%
    monkeypatch.setattr(be.alpaca, "get_latest_trade", AsyncMock(return_value={"price": 9.95}))
    spec, why = await be.prepare_breakout_order({"ticker": "X"}, {"level": 10.0, "stop": 9.60, "low": 9.6}, None,
                                                "paper", today=TODAY, adr20=0.05)
    # EP's arithmetic exactly (raw float risk per share, as prepare_orb_order computes it)
    assert why is None and spec["shares"] == __import__("math").floor(500.0 / (10.0 - 9.60))
    assert spec["risk_per_share"] == pytest.approx(0.40)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# the world: a fake broker + DB for the minute job
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _strategy(phase="paper", enabled=True) -> Strategy:
    return Strategy(strategy_id=SID, name="Breakout v1 (paper)", family="long_setup", phase=phase, enabled=enabled,
                    signal_type=SID, outcomes_table="mi_live_trades", promotion_model="unpaired_r")


_LIST = {"scan_date": PREV, "ticker": "BRKO", "level": 10.00, "vol_bar": 1_200_000.0, "adr20": 0.06,
         "rs_best": 99.1, "close": 9.80, "security_type": "CS", "list_rank": 1}


class World:
    def __init__(self, monkeypatch, *, at=(9, 35), phase="paper", toggle=True, list_rows=None, bars=None,
                 rows=None, orders=None, cancel_outcome="dead", latest=None):
        self.now = datetime(TODAY.year, TODAY.month, TODAY.day, *at, 10, tzinfo=_ET)
        self.rows = {r["ticker"]: dict(r) for r in (rows or [])}
        self.orders = {o["id"]: dict(o) for o in (orders or [])}
        self.audits: list[tuple] = []
        self.pages: list[str] = []
        self.events: list[tuple] = []
        self.sql: list[str] = []
        self.skips: list[tuple] = []
        self.cancel_outcome = cancel_outcome
        self.latest = latest
        self.bars = bars if bars is not None else {"BRKO": _flat_bars(5, low=9.80, high=9.95, vol=60_000.0)}
        self.list_rows = [dict(_LIST)] if list_rows is None else list_rows
        self._n = 0
        w = self

        pool = MagicMock()
        conn = MagicMock()
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=None)
        pool.acquire = MagicMock(return_value=cm)

        async def fetch(sql, *a):
            w.sql.append(sql)
            if "FROM mi_live_trades WHERE alert_date" in sql:
                return [dict(r) for r in w.rows.values() if r["ticker"] in a[2] and r["account_mode"] == a[1]]
            if "FROM mi_audit_log" in sql:
                return [{"event_type": e, "detail": d} for e, _s, d in w.audits if e == a[0]]
            if "FROM mi_breakout_v1_list" in sql:
                return [dict(r) for r in w.list_rows if r["scan_date"] == a[0]]
            raise AssertionError(f"unhandled fetch: {sql[:90]}")

        async def fetchrow(sql, *a):
            w.sql.append(sql)
            if "mi_market_regime" in sql:
                return None
            if "FROM mi_live_trades WHERE id = $1" in sql:
                return next((dict(r) for r in w.rows.values() if r["id"] == a[0]), None)
            raise AssertionError(f"unhandled fetchrow: {sql[:90]}")

        async def fetchval(sql, *a):
            w.sql.append(sql)
            row = next((r for r in w.rows.values() if r["id"] == a[0]), None)
            if "SET stop_order_id = $2, stop_price = $3, hard_stop = $3" in sql:     # _record_stop_lowered (CAS)
                ok = (row is not None and row["status"] == "filled" and (row["signal_type"], row["account_mode"])
                      == tuple(a[4:6]) == (SID, "paper") and not row.get("partial_taken")
                      and (row.get("stop_price") is None or row["stop_price"] >= a[2]))
                if not ok:
                    return None
                row.update(stop_order_id=a[1], stop_price=a[2], hard_stop=a[2], risk_dollars_actual=a[3])
                w.events.append(("row_stop_lowered", row["ticker"], a[1], a[2], a[3]))
                return row["id"]
            cas = (row is not None and row["status"] == a[1] and row.get("entry_order_id") == a[2]
                   and (row["signal_type"], row["account_mode"]) == tuple(a[-2:]) == (SID, "paper"))
            if "SET status = 'cancelled'" in sql:
                if not cas:
                    return None
                row.update(status="cancelled", skip_reason=a[3])
                w.events.append(("row_cancelled", row["ticker"], a[3]))
                return row["id"]
            if "SET status = 'confirmed'" in sql:
                if not cas:
                    return None
                row.update(status="confirmed", entry_order_id=None, stop_order_id=None, stop_price=a[3],
                           hard_stop=a[3], entry_shares=a[4], position_size=a[5], risk_dollars_actual=a[6])
                w.events.append(("row_rearmed", row["ticker"], a[3], a[4]))
                return row["id"]
            raise AssertionError(f"unhandled fetchval: {sql[:90]}")

        async def execute(sql, *a):
            w.sql.append(sql)
            if "INSERT INTO mi_live_orders" in sql:
                w.events.append(("order_row", a[1], a[4]))
                return "INSERT 0 1"
            raise AssertionError(f"unhandled execute: {sql[:90]}")

        conn.fetch, conn.fetchrow, conn.fetchval, conn.execute = fetch, fetchrow, fetchval, execute
        self.pool = pool

        async def audit(ev, summary, detail=""):
            w.audits.append((ev, summary, detail))

        async def tg(msg, *a, **k):
            w.pages.append(msg)
            return True

        fake = SimpleNamespace()

        async def get_open_orders(account_mode=None, raise_on_error=False, ticker=None):
            assert account_mode == "paper"
            return [dict(o) for o in w.orders.values() if be._classify(o) == "open"]

        async def get_minute_bars_range(ticker, start, end):
            return list(w.bars.get(ticker, []))

        async def get_order(oid, account_mode=None, timeout=None):
            assert account_mode == "paper"
            o = w.orders.get(oid)
            return dict(o) if o else None

        async def cancel_order(oid, account_mode=None):
            assert account_mode == "paper"
            w.events.append(("cancel", oid))
            o = w.orders.get(oid)
            if o is None:
                return False
            if w.cancel_outcome == "dead":
                o["status"] = "canceled"
            elif w.cancel_outcome == "filled":
                o.update(status="filled", filled_qty=o["qty"])
            return w.cancel_outcome != "refused"

        async def get_account(account_mode=None):
            assert account_mode == "paper"
            return {"equity": 100_000.0, "trading_blocked": False, "account_blocked": False}

        async def get_latest_trade(ticker):
            return w.latest

        fake.get_open_orders, fake.get_minute_bars_range = get_open_orders, get_minute_bars_range
        fake.get_order, fake.cancel_order, fake.get_account = get_order, cancel_order, get_account
        fake.get_latest_trade = get_latest_trade
        self.alpaca = fake

        async def submit_entry(trade_id):
            row = next(r for r in w.rows.values() if r["id"] == trade_id)
            assert row["status"] == "confirmed" and row["account_mode"] == "paper"
            live = [o for o in w.orders.values() if o["symbol"] == row["ticker"] and be._classify(o) == "open"]
            assert not live, f"a second live buy for {row['ticker']}: {live}"      # never two live buys
            w._n += 1
            oid = f"new-{w._n}"
            w.orders[oid] = {"id": oid, "symbol": row["ticker"], "side": "buy", "status": "new",
                             "qty": row["entry_shares"],
                             "filled_qty": 0, "client_order_id": f"apollo_paper_breakout_v1_{row['ticker']}_{w._n}"}
            row.update(status="order_placed", entry_order_id=oid)
            w.events.append(("submit", row["ticker"], row["stop_price"], row["entry_shares"]))
            return {"id": oid}

        self.submit_entry = submit_entry
        self.funnel = AsyncMock(return_value={"ticker": "BRKO", "action": ep.ACTION_AUTO_ENTERED, "trade_id": 1})

        from agents.market_intelligence import briefing, trading_calendar
        from agents.market_intelligence.strategies import registry
        monkeypatch.setattr(be, "get_pool", AsyncMock(return_value=pool))
        monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
        monkeypatch.setattr(be, "log_audit_event", audit)
        monkeypatch.setattr(trading_calendar, "get_market_status",
                            lambda d: trading_calendar.MarketStatus(True, "test"))
        monkeypatch.setattr(be, "get_runtime_toggle", AsyncMock(return_value=toggle))
        monkeypatch.setattr(registry, "get_strategy", AsyncMock(return_value=_strategy(phase=phase)))
        monkeypatch.setattr(be, "LIVE_TRADING_ENABLED", True)
        monkeypatch.setattr(be, "alpaca", fake)
        monkeypatch.setattr(be, "submit_trade_entry", self.funnel)
        monkeypatch.setattr(om, "submit_entry", submit_entry)
        monkeypatch.setattr(briefing, "send_telegram_message", tg)
        monkeypatch.setattr(be, "CANCEL_POLL_S", 0)
        monkeypatch.setattr(be, "_preflight_ok_date", None)
        monkeypatch.setattr(be, "_paged", set())
        monkeypatch.setattr(be, "_noted", {})
        monkeypatch.setattr(be, "_snapshot_fails", 0)
        monkeypatch.setattr(be, "_fill_checked", set())

        async def ins(ticker, today, alert, regime, reason, signal_type=None, account_mode=None):
            w.skips.append((ticker, reason, signal_type, account_mode))
        monkeypatch.setattr(lt, "_insert_skipped_trade", ins)

    async def tick(self, at=None):
        if at is not None:
            self.now = datetime(TODAY.year, TODAY.month, TODAY.day, *at, 10, tzinfo=_ET)
        return await be.run_breakout_v1_entry_tick(self.now)

    def ev(self, name):
        return [a for a in self.audits if a[0] == name]


def _placed_row(stop=9.80, shares=1250.0, oid="ord-1", status="order_placed", ticker="BRKO", tid=11):
    return {"id": tid, "ticker": ticker, "alert_date": TODAY, "account_mode": "paper", "signal_type": SID,
            "status": status, "entry_order_id": oid, "stop_order_id": "leg-1", "orb_high": 10.00, "orb_low": 9.80,
            "stop_price": stop, "hard_stop": stop, "entry_shares": shares, "risk_dollars": 250.0}


def _order(oid="ord-1", ticker="BRKO", status="new", qty=1250.0, filled=0.0):
    return {"id": oid, "symbol": ticker, "side": "buy", "status": status, "qty": qty, "filled_qty": filled,
            "client_order_id": f"apollo_paper_breakout_v1_{ticker}_1"}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 2. walls, pre-flight, stop switch
# ═══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_the_0935_tick_orders_a_list_name_through_the_funnel_bound_to_paper(monkeypatch):
    w = World(monkeypatch)
    out = await w.tick()
    assert out["actions"] == {"BRKO": ep.ACTION_AUTO_ENTERED}
    kw = w.funnel.await_args.kwargs
    assert kw["signal_type"] == SID and kw["require_account_mode"] == "paper"      # wall 3
    assert kw["page_cap_plus_one"] is False and kw["aggregate_skips"] is True
    assert kw["rt_gap_floor_pct"] is None and kw["fade_midpoint_ratio"] is None
    assert kw["alert_context"]["ticker"] == "BRKO" and kw["today"] == TODAY
    bar = await kw["bar_fetcher"]("BRKO", TODAY, "x")                                 # its own 5-minute range
    assert bar == {"open": 9.90, "high": 9.95, "low": 9.80, "level": 10.00, "stop": 9.80}
    assert w.pages == []                                                              # a placed order: no Telegram
    assert w.ev("breakout_v1_entry_order") and w.ev("breakout_v1_preflight_ok")


@pytest.mark.asyncio
async def test_wall_1_the_tick_reads_its_own_list_table_and_never_the_live_alert_table(monkeypatch):
    w = World(monkeypatch)
    monkeypatch.setattr(be, "bv1_get_list", db.bv1_get_list)                        # the REAL reader
    monkeypatch.setattr(lt, "process_new_alerts_live",
                        AsyncMock(side_effect=AssertionError("the live order step was entered")))
    await w.tick()
    assert [c.kwargs["alert_context"]["ticker"] for c in w.funnel.await_args_list] == ["BRKO"]
    assert any("mi_breakout_v1_list" in s for s in w.sql)
    assert not [s for s in w.sql if "mi_ep_alerts" in s or "mi_lowcap_paper_lane_alerts" in s]


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["live", "shadow"])
async def test_wall_2_any_phase_but_paper_is_refused_and_paged(monkeypatch, phase):
    w = World(monkeypatch, phase=phase)
    out = await w.tick()
    assert out["skipped"] == "switched_off" and not w.funnel.await_count
    assert w.ev("breakout_v1_refused") and len(w.pages) == 1 and w.pages[0].startswith("📄 PAPER")
    await w.tick()
    assert len(w.pages) == 1                                                          # paged once, not every minute


@pytest.mark.asyncio
async def test_the_switch_off_places_nothing_and_cancels_a_resting_buy(monkeypatch):
    w = World(monkeypatch, toggle=False, rows=[_placed_row()], orders=[_order()])
    out = await w.tick(at=(10, 5))
    assert out["skipped"] == "switched_off" and not w.funnel.await_count
    assert ("cancel", "ord-1") in w.events and w.rows["BRKO"]["status"] == "cancelled"
    assert w.rows["BRKO"]["skip_reason"].startswith("block:strategy_disabled")
    assert w.ev(be.PLANNED_ENTRY_CANCEL)                                              # marked before the cancel


@pytest.mark.asyncio
async def test_the_switch_off_frees_a_row_that_never_got_its_order(monkeypatch):
    w = World(monkeypatch, toggle=False, rows=[_placed_row(status="confirmed", oid=None)], orders=[])
    await w.tick(at=(10, 5))
    assert w.rows["BRKO"]["status"] == "cancelled" and not [e for e in w.events if e[0] == "submit"]


@pytest.mark.asyncio
async def test_disabled_row_is_the_switch_off_quietly(monkeypatch):
    w = World(monkeypatch)
    from agents.market_intelligence.strategies import registry
    monkeypatch.setattr(registry, "get_strategy", AsyncMock(return_value=_strategy(enabled=False)))
    out = await w.tick()
    assert out["skipped"] == "switched_off" and not w.funnel.await_count and w.pages == []


@pytest.mark.asyncio
async def test_live_trading_disabled_stops_the_job(monkeypatch):
    w = World(monkeypatch)
    monkeypatch.setattr(be, "LIVE_TRADING_ENABLED", False)
    assert (await w.tick())["skipped"] == "live_trading_disabled" and not w.funnel.await_count


@pytest.mark.asyncio
async def test_preflight_failure_places_nothing_and_pages_once_then_retries(monkeypatch):
    w = World(monkeypatch)
    w.alpaca.get_account = AsyncMock(side_effect=RuntimeError("paper 401"))
    await w.tick()
    await w.tick(at=(9, 36))
    assert not w.funnel.await_count and len(w.pages) == 1 and w.pages[0].startswith("📄 PAPER")
    w.alpaca.get_account = AsyncMock(return_value={"equity": 1e5, "trading_blocked": False, "account_blocked": False})
    await w.tick(at=(9, 37))
    assert w.funnel.await_count == 1


@pytest.mark.asyncio
async def test_outside_the_window_and_on_a_holiday_nothing_runs(monkeypatch):
    w = World(monkeypatch)
    assert (await w.tick(at=(9, 34)))["skipped"] == "outside_window"
    assert (await w.tick(at=(15, 56)))["skipped"] == "outside_window"
    from agents.market_intelligence import trading_calendar
    monkeypatch.setattr(trading_calendar, "get_market_status", lambda d: trading_calendar.MarketStatus(False, "h"))
    assert (await w.tick(at=(10, 0)))["skipped"] == "not_a_trading_day"
    assert not w.funnel.await_count


@pytest.mark.asyncio
async def test_the_list_is_the_previous_nyse_sessions_and_a_stale_list_is_never_traded(monkeypatch):
    """Monday 11-02 reads Friday 10-30's list (the exchange calendar). A list that exists only for an OLDER night (the
    nightly job did not run last night) is no names — never a list a session stale. MUTATION: take the previous
    session from the last stored SPY bar / read the latest list night."""
    lst = AsyncMock(side_effect=db.bv1_get_list)
    w = World(monkeypatch)
    monkeypatch.setattr(be, "bv1_get_list", lst)
    await w.tick()
    assert lst.await_args.args[0] == PREV and w.funnel.await_count == 1
    w = World(monkeypatch, list_rows=[dict(_LIST, scan_date=date(2026, 10, 29))])
    out = await w.tick()
    assert out["skipped"] == "no_list_names" and not w.funnel.await_count
    # Friday 11-27 (after Thanksgiving) reads Wednesday 11-25's list
    assert await be._previous_session(date(2026, 11, 27)) == date(2026, 11, 25)


@pytest.mark.asyncio
async def test_a_sell_side_order_carrying_the_family_prefix_is_never_cancelled(monkeypatch):
    """A protective stop leg is never an orphan — even if the broker stamped it with the parent's order id prefix.
    MUTATION: drop the buy-side filter in `_family_open_orders` -> the leg is cancelled (a naked position)."""
    leg = dict(_order(oid="leg-x", ticker="HELD"), side="sell")
    w = World(monkeypatch, rows=[], orders=[leg])
    await w.tick()
    assert not [e for e in w.events if e[0] == "cancel"] and not w.ev("breakout_v1_orphan_order")


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 3. the shared code
# ═══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_ep_and_the_small_cap_lane_call_the_funnel_without_a_bar_fetcher(monkeypatch):
    """Both existing callers, DRIVEN to their funnel call: live MAGNA53 (`process_new_alerts_live`) and the small-cap
    paper lane (`process_lowcap_paper_alerts`) pass no `bar_fetcher`, so the funnel keeps
    `fetch_orb_bar_with_retry` (the next test). 9M Day 2 has had no funnel call since #515 retired its entry.
    MUTATION: pass `bar_fetcher=` from either caller -> red."""
    from tests.test_624_paper_lane import _wire_live_step, _wire_order_step
    from agents.market_intelligence.broker import lowcap_paper_entry as lpe
    cf, submit = _wire_live_step(monkeypatch, magna_mode="live", paper_row_exists=False)
    cf.return_value = (True, None)
    monkeypatch.setattr(lt, "compute_atr_14", AsyncMock(return_value=(0.5, 5.0)))
    submit.return_value = {"ticker": "SMLL", "action": ep.ACTION_AUTO_ENTERED}
    await lt.process_new_alerts_live(today=date(2026, 10, 12))
    assert submit.await_count == 1 and submit.await_args.kwargs["signal_type"] == "magna53"
    assert "bar_fetcher" not in submit.await_args.kwargs
    w = _wire_order_step(monkeypatch)
    await lpe.process_lowcap_paper_alerts(today=date(2026, 10, 12))
    assert w.submit.await_count == 1 and w.submit.await_args.kwargs["signal_type"] == "magna53_smallcap"
    assert "bar_fetcher" not in w.submit.await_args.kwargs


@pytest.mark.asyncio
@pytest.mark.parametrize("with_fetcher", [False, True])
async def test_the_funnel_uses_fetch_orb_bar_with_retry_unless_handed_a_fetcher(monkeypatch, with_fetcher):
    from tests.test_461_cap_toctou_race import FakeDB, _spec_builder, _wire
    fdb = FakeDB()
    _wire(monkeypatch, fdb, phase="live", live_real_enabled=True)
    default = AsyncMock(return_value={"open": 10.0, "high": 10.5, "low": 9.8})
    monkeypatch.setattr(ep, "fetch_orb_bar_with_retry", default)
    mine = AsyncMock(return_value={"open": 10.0, "high": 10.5, "low": 9.8})
    res = await ep.submit_trade_entry(
        alert_context={"ticker": "EPX", "ep_score": 71, "catalyst_quality": "strong", "gap_pct": 10.0},
        spec_builder=_spec_builder, regime_record=None, strategy_label="ORB", signal_type="magna53",
        today=date(2026, 7, 17), atr_14=1.0, fade_midpoint_ratio=None,
        **({"bar_fetcher": mine} if with_fetcher else {}))
    assert res["action"] == ep.ACTION_AUTO_ENTERED
    assert default.await_count == (0 if with_fetcher else 1)
    assert mine.await_count == (1 if with_fetcher else 0)
    assert (mine if with_fetcher else default).await_args.args == ("EPX", date(2026, 7, 17), "ORB")


@pytest.mark.asyncio
async def test_resolve_exit_rule_stamp_breakout_is_pp_and_every_other_strategy_is_unchanged(monkeypatch):
    reads = []

    async def _state(name, mode):
        reads.append((name, mode))
        return {"state": "on"}
    monkeypatch.setattr(db, "get_safeguard_state", _state)
    assert await om.resolve_exit_rule_stamp(SID, "paper") == "breakout_pp" == om.BREAKOUT_PP_EXIT_RULE
    assert reads == []                                                  # no toggle read for breakout
    assert await om.resolve_exit_rule_stamp("magna53", "live") == "depth"
    assert await om.resolve_exit_rule_stamp("magna53_smallcap", "paper") == "depth"
    assert await om.resolve_exit_rule_stamp("9m_day2", "paper") is None

    async def _off(name, mode):
        return {"state": "off"}
    monkeypatch.setattr(db, "get_safeguard_state", _off)
    assert await om.resolve_exit_rule_stamp("magna53", "live") is None
    assert await om.resolve_exit_rule_stamp(SID, "paper") == "breakout_pp"


@pytest.mark.asyncio
async def test_the_real_funnel_stamps_breakout_pp_and_refuses_a_row_resolving_to_live(monkeypatch):
    """The REAL funnel over the shared FakeDB: a paper breakout entry lands in the paper book with
    exit_rule='breakout_pp'; the same strategy resolving to live (live_real_enabled — the worst case) is refused
    before any row or order (wall 3)."""
    from tests import test_461_cap_toctou_race as t461

    class _Conn(t461.FakeConn):
        async def execute(self, sql, *args):
            if "SET exit_rule" in " ".join(sql.split()):
                for r in self.db.rows:
                    if r["id"] == args[0]:
                        r["exit_rule"] = args[1]
                return "UPDATE 1"
            return await super().execute(sql, *args)

    class _Pool(t461.FakePool):
        def acquire(self):
            conn = _Conn(self.db)

            class _CM:
                async def __aenter__(_s):
                    return conn

                async def __aexit__(_s, *e):
                    return False
            return _CM()

    async def _spec(alert_ctx, orb_bar, regime, account_mode):
        return ({"orb_high": 10.0, "orb_low": 9.8, "entry_price": 10.0, "stop_loss_price": 9.8, "shares": 100,
                 "position_size": 1000.0, "risk_dollars": 20.0, "risk_per_share": 0.2}, None)

    async def _bar(*a):
        return {"open": 9.9, "high": 9.95, "low": 9.8}

    for phase, live_real, expect in (("paper", False, ep.ACTION_AUTO_ENTERED), ("live", True, ep.ACTION_BLOCKED)):
        fdb = t461.FakeDB()
        t461._wire(monkeypatch, fdb, phase=phase, live_real_enabled=live_real)
        monkeypatch.setattr(ep, "get_pool", AsyncMock(return_value=_Pool(fdb)))
        monkeypatch.setattr(lt, "get_pool", AsyncMock(return_value=_Pool(fdb)))
        res = await ep.submit_trade_entry(
            alert_context={"ticker": "BRKO", "alert_date": TODAY}, spec_builder=_spec, regime_record=None,
            strategy_label="Breakout v1 (paper)", signal_type=SID, today=TODAY, fade_midpoint_ratio=None,
            aggregate_skips=True, require_account_mode="paper", page_cap_plus_one=False, bar_fetcher=_bar)
        assert res["action"] == expect, res
        if expect == ep.ACTION_AUTO_ENTERED:
            row = fdb.rows[-1]
            assert row["account_mode"] == "paper" and row["signal_type"] == SID
            assert row["exit_rule"] == "breakout_pp"
        else:
            assert res["reason"].startswith("block:account_mode_mismatch") and fdb.rows == []
            assert not om.submit_entry.await_count


@pytest.mark.asyncio
async def test_wall_4_and_the_500_branch_a_breakout_row_submits_in_the_paper_family(monkeypatch):
    """`submit_entry` on a breakout paper row: the order id is make_client_order_id('paper', 'breakout_v1', T) and a
    price already past the level takes the #500 limit at latest x 1.002 with the row's day-low stop."""
    from tests.test_500_price_aware_entry import _wire_submit_entry
    trade = {"id": 7, "ticker": "BRKO", "account_mode": "paper", "signal_type": SID, "orb_high": 10.0,
             "orb_low": 9.8, "stop_price": 9.70, "entry_shares": 100, "entry_price": 10.0}
    fake, conn, _ = _wire_submit_entry(monkeypatch, {"price": 10.10}, trade=trade)
    from agents.market_intelligence.broker import alpaca_client as _real_alpaca
    fake.make_client_order_id = MagicMock(side_effect=_real_alpaca.make_client_order_id)
    order = await om.submit_entry(7)
    assert order is not None
    fake.place_bracket_order.assert_not_awaited()
    kw = fake.place_limit_buy_with_stop.await_args.kwargs
    assert kw["limit_price"] == round(10.10 * 1.002, 2) and kw["stop_loss_price"] == 9.70
    assert kw["account_mode"] == "paper" and kw["client_order_id"].startswith("apollo_paper_breakout_v1_BRKO_")
    assert fake.make_client_order_id.call_args.args == ("paper", SID, "BRKO")
    # below the level: the stop-limit bracket at the level, limit stop_limit_buy_price(level)
    fake, conn, _ = _wire_submit_entry(monkeypatch, {"price": 9.95}, trade=trade)
    await om.submit_entry(7)
    kw = fake.place_bracket_order.await_args.kwargs
    assert kw["stop_price"] == 10.0 and kw["limit_price"] == om.stop_limit_buy_price(10.0)
    assert kw["stop_loss_price"] == 9.70


def _cleanup_rows():
    return [
        {"id": 1, "ticker": "BRKO", "entry_order_id": "o1", "alert_date": TODAY, "proposed_at": None,
         "entry_price": 10.0, "stop_price": 9.8, "entry_shares": 10, "orb_high": 10.0, "account_mode": "paper",
         "pm_rvol": None, "signal_type": SID},
        {"id": 2, "ticker": "SMLL", "entry_order_id": "o2", "alert_date": TODAY, "proposed_at": None,
         "entry_price": 5.0, "stop_price": 4.0, "entry_shares": 10, "orb_high": 5.0, "account_mode": "paper",
         "pm_rvol": None, "signal_type": "magna53_smallcap"},
        {"id": 3, "ticker": "LEGA", "entry_order_id": "o3", "alert_date": TODAY, "proposed_at": None,
         "entry_price": 5.0, "stop_price": 4.0, "entry_shares": 10, "orb_high": 5.0, "account_mode": "paper",
         "pm_rvol": None, "signal_type": None},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("exclude,expect", [(("breakout_v1",), {"o2", "o3"}), ((), {"o1", "o2", "o3"})])
async def test_cancel_unfilled_entries_excludes_by_signal_type_only(monkeypatch, exclude, expect):
    """10:00 ET (exclude breakout_v1): the small-cap paper lane's row and a legacy NULL-signal row are still
    cancelled; the breakout row is not. 16:05 ET (default): every row, the breakout one included (the backstop)."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=_cleanup_rows())
    conn.fetchrow = AsyncMock(return_value={"exits": None, "total_pnl": None})
    conn.execute = AsyncMock(return_value="UPDATE 1")
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    cancel = AsyncMock(return_value=True)
    monkeypatch.setattr(om.alpaca, "cancel_order", cancel)
    monkeypatch.setattr(om, "log_audit_event", AsyncMock())
    monkeypatch.setattr(om, "send_telegram_message", AsyncMock())
    monkeypatch.setattr(om, "_update_trade_status", AsyncMock())
    n = await om.cancel_unfilled_entries(reason="EOD unfilled", exclude_signal_types=exclude)
    assert {c.args[0] for c in cancel.await_args_list} == expect and n == len(expect)


@pytest.mark.asyncio
async def test_the_1000_cleanup_passes_the_breakout_exclusion_and_the_1605_cleanup_does_not(monkeypatch):
    """DRIVEN: the 10:00 ET job hands `exclude_signal_types=("breakout_v1",)`; the 16:05 ET job hands nothing (every
    row, the backstop). MUTATION: drop the kwarg from `_orb_window_cleanup_job` / add it to `_eod_cleanup_job`."""
    from agents.market_intelligence import scheduler as sched
    import agents.market_intelligence.constants as consts
    monkeypatch.setattr(consts, "LIVE_TRADING_ENABLED", True)
    cancel = AsyncMock(return_value=0)
    monkeypatch.setattr(om, "cancel_unfilled_entries", cancel)
    monkeypatch.setattr(om, "expire_stale_proposals", AsyncMock(return_value=0))
    monkeypatch.setattr(om, "sync_positions", AsyncMock(return_value=[]))
    await sched._orb_window_cleanup_job()
    assert cancel.await_args.kwargs == {"reason": "ORB window unfilled", "exclude_signal_types": ("breakout_v1",)}
    cancel.reset_mock()
    await sched._eod_cleanup_job()
    assert cancel.await_args.args == () and cancel.await_args.kwargs == {}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 4. the minute job: the stop kept at the day's low until the fill, the cancels, restart safety
# ═══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_a_new_low_re_prices_the_stop_cancel_confirmed_before_the_new_buy(monkeypatch):
    bars = _flat_bars(12, low=9.80, high=9.95, vol=60_000.0) + [_bar(12, 9.8, 9.85, 9.60, 9.7, 60_000.0)]
    w = World(monkeypatch, rows=[_placed_row()], orders=[_order()], bars={"BRKO": bars})
    out = await w.tick(at=(9, 43))                                   # minute 13: minute 12 (low 9.60) completed
    assert out["actions"]["BRKO"] == "repriced"
    names = [e[0] for e in w.events]
    assert names == ["cancel", "row_rearmed", "submit"]            # the old buy is dead before the new one
    assert w.events[1][2] == 9.60                                   # the new stop: the new day low
    # re-sized: $250 risk / (10.00 - 9.60) = 625 shares (the dollar risk placed never grows)
    assert w.events[2][3] == 625.0 and w.rows["BRKO"]["entry_order_id"] == "new-1"
    marker = w.ev(be.PLANNED_ENTRY_CANCEL)
    assert marker and json.loads(marker[0][2])["order_id"] == "ord-1" and json.loads(marker[0][2])["trade_id"] == 11
    assert w.pages == []                                            # a re-price is a normal event: no Telegram
    # the next minute, nothing new: no churn
    await w.tick(at=(9, 44))
    assert [e[0] for e in w.events] == ["cancel", "row_rearmed", "submit"]


@pytest.mark.asyncio
async def test_a_fill_racing_the_re_price_cancel_is_never_re_placed(monkeypatch):
    bars = _flat_bars(12, low=9.80, high=9.95, vol=60_000.0) + [_bar(12, 9.8, 9.85, 9.60, 9.7, 60_000.0)]
    w = World(monkeypatch, rows=[_placed_row()], orders=[_order()], bars={"BRKO": bars}, cancel_outcome="filled")
    out = await w.tick(at=(9, 43))
    assert out["actions"]["BRKO"] == "filled"
    assert [e[0] for e in w.events] == ["cancel"] and w.rows["BRKO"]["status"] == "order_placed"
    assert len(w.pages) == 1 and "filled while it was being cancelled" in w.pages[0]
    await w.tick(at=(9, 44))                                        # the filled order is left to the fill path
    assert [e[0] for e in w.events] == ["cancel"]


@pytest.mark.asyncio
async def test_a_broker_refused_cancel_pages_and_retries(monkeypatch):
    bars = _flat_bars(12, low=9.80, high=9.95, vol=60_000.0) + [_bar(12, 9.8, 9.85, 9.60, 9.7, 60_000.0)]
    w = World(monkeypatch, rows=[_placed_row()], orders=[_order()], bars={"BRKO": bars}, cancel_outcome="refused")
    await w.tick(at=(9, 43))
    assert w.ev("breakout_v1_cancel_failed") and len(w.pages) == 1 and w.rows["BRKO"]["status"] == "order_placed"
    assert "submit" not in [e[0] for e in w.events]


@pytest.mark.asyncio
async def test_too_wide_cancels_with_the_named_reason(monkeypatch):
    bars = _flat_bars(12, low=9.80, high=9.95, vol=60_000.0) + [_bar(12, 9.8, 9.85, 9.30, 9.4, 60_000.0)]
    w = World(monkeypatch, rows=[_placed_row()], orders=[_order()], bars={"BRKO": bars})
    await w.tick(at=(9, 43))                                        # (10.00 - 9.30) / 10.00 = 7% > ADR20 6%
    assert w.rows["BRKO"]["status"] == "cancelled" and w.rows["BRKO"]["skip_reason"].startswith("setup:stop_too_wide")
    assert "submit" not in [e[0] for e in w.events] and w.pages == []


@pytest.mark.asyncio
async def test_a_volume_lapse_cancels_the_resting_buy(monkeypatch):
    bars = _flat_bars(30, low=9.80, high=9.95, vol=1_000.0)          # 30k by minute 29 << 1.2M x 12%
    w = World(monkeypatch, rows=[_placed_row()], orders=[_order()], bars={"BRKO": bars})
    await w.tick(at=(10, 0))
    assert w.rows["BRKO"]["status"] == "cancelled"
    assert w.rows["BRKO"]["skip_reason"].startswith("setup:breakout_volume_below_curve")


@pytest.mark.asyncio
async def test_unfilled_at_1555_is_cancelled_and_nothing_new_is_placed(monkeypatch):
    w = World(monkeypatch, rows=[_placed_row()], orders=[_order()],
              list_rows=[dict(_LIST), dict(_LIST, ticker="NEWB", list_rank=2)],
              bars={"BRKO": _flat_bars(385, vol=60_000.0), "NEWB": _flat_bars(385, vol=60_000.0)})
    out = await w.tick(at=(15, 55))
    assert w.rows["BRKO"]["skip_reason"].startswith("window:breakout_unfilled_eod")
    assert out["actions"]["NEWB"] == "never_placed" and not w.funnel.await_count
    assert w.ev("breakout_v1_entry_day")


@pytest.mark.asyncio
async def test_restart_finishes_a_planned_cancel_from_broker_truth(monkeypatch):
    """A tick crashed after cancelling (marker written, broker order dead) and before re-placing: the next tick
    reads the dead order + the marker and places the new buy at the current stop."""
    bars = _flat_bars(12, low=9.80, high=9.95, vol=60_000.0) + [_bar(12, 9.8, 9.85, 9.60, 9.7, 60_000.0)]
    w = World(monkeypatch, rows=[_placed_row()], orders=[_order(status="canceled")], bars={"BRKO": bars})
    w.audits.append((be.PLANNED_ENTRY_CANCEL, "x", json.dumps({"trade_id": 11, "order_id": "ord-1"})))
    out = await w.tick(at=(9, 43))
    assert out["actions"]["BRKO"] == "repriced" and [e[0] for e in w.events] == ["row_rearmed", "submit"]


@pytest.mark.asyncio
async def test_a_broker_kill_without_a_marker_and_a_filled_order_are_left_alone(monkeypatch):
    w = World(monkeypatch, rows=[_placed_row()], orders=[_order(status="canceled")],
              bars={"BRKO": _flat_bars(13, vol=60_000.0)})
    assert (await w.tick(at=(9, 43)))["actions"]["BRKO"] == "dead_unplanned" and w.events == []
    w = World(monkeypatch, rows=[_placed_row()], orders=[_order(status="partially_filled", filled=10)],
              bars={"BRKO": _flat_bars(12, low=9.8, vol=60_000.0) + [_bar(12, 9.8, 9.85, 9.30, 9.4, 6e4)]})
    assert (await w.tick(at=(9, 43)))["actions"]["BRKO"] == "filled" and w.events == []   # even when too wide


@pytest.mark.asyncio
async def test_a_confirmed_row_with_no_order_after_a_crash_is_submitted(monkeypatch):
    row = _placed_row(status="confirmed", oid=None)
    w = World(monkeypatch, rows=[row], orders=[], bars={"BRKO": _flat_bars(13, vol=60_000.0)})
    out = await w.tick(at=(9, 43))
    assert out["actions"]["BRKO"] == "repriced"
    assert [e[0] for e in w.events] == ["row_rearmed", "submit"] and not w.funnel.await_count


@pytest.mark.asyncio
async def test_an_order_in_the_family_no_row_tracks_is_cancelled_and_paged(monkeypatch):
    w = World(monkeypatch, rows=[], orders=[_order(oid="ghost", ticker="ZZZZ")])
    await w.tick()
    assert ("cancel", "ghost") in w.events and w.ev("breakout_v1_orphan_order")
    assert len(w.pages) == 1 and "no trade row tracks" in w.pages[0]
    # an order outside the family (the small-cap lane's, EP's) is never touched
    w = World(monkeypatch, rows=[], orders=[dict(_order(oid="lane", ticker="SMLL"),
                                                 client_order_id="apollo_paper_magna53_smallcap_SMLL_1")])
    await w.tick()
    assert not [e for e in w.events if e[0] == "cancel"]


@pytest.mark.asyncio
async def test_no_buy_before_the_volume_curve_permits_then_one_buy_once_it_does(monkeypatch):
    thin = _flat_bars(10, vol=1_000.0)
    w = World(monkeypatch, bars={"BRKO": thin})
    await w.tick(at=(9, 40))
    await w.tick(at=(9, 41))
    assert not w.funnel.await_count and len(w.ev("breakout_v1_entry_hold")) == 1     # recorded once, not per minute
    w.bars["BRKO"] = _flat_bars(12, vol=60_000.0)
    await w.tick(at=(9, 42))
    assert w.funnel.await_count == 1


@pytest.mark.asyncio
async def test_no_opening_range_minutes_is_a_durable_paper_skip(monkeypatch):
    w = World(monkeypatch, bars={"BRKO": [_bar(8, 10.0, 10.1, 9.9, 10.0, 1e6)]})
    out = await w.tick(at=(9, 40))
    assert out["actions"]["BRKO"] == "abstain" and not w.funnel.await_count
    assert w.skips == [("BRKO", w.skips[0][1], SID, "paper")]
    assert w.skips[0][1].startswith("setup:no_opening_range_minutes")


@pytest.mark.asyncio
async def test_a_name_another_paper_strategy_holds_today_is_left_to_it(monkeypatch):
    other = dict(_placed_row(), signal_type="magna53_smallcap")
    w = World(monkeypatch, rows=[other],
              orders=[dict(_order(), client_order_id="apollo_paper_magna53_smallcap_BRKO_1")])
    out = await w.tick(at=(9, 43))
    assert out["actions"]["BRKO"] == "owned_by_magna53_smallcap" and w.events == []


@pytest.mark.asyncio
async def test_an_unreadable_broker_takes_no_action_and_pages_after_three_minutes(monkeypatch):
    w = World(monkeypatch, rows=[_placed_row()], orders=[_order()])
    w.alpaca.get_open_orders = AsyncMock(side_effect=RuntimeError("503"))
    for mm in (40, 41):
        assert (await w.tick(at=(9, mm)))["skipped"] == "broker_unreadable"
    assert w.pages == []
    await w.tick(at=(9, 42))
    assert len(w.pages) == 1 and not w.funnel.await_count and w.events == []


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 5. the trade stream
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _cancel_event(oid="ord-1", filled=0.0):
    order = SimpleNamespace(id=oid, symbol="BRKO", side="buy", filled_qty=filled, status="canceled",
                            filled_avg_price=None, qty=100)
    return SimpleNamespace(order=order, event="canceled", reason=None)


async def _drive_stream_cancel(monkeypatch, signal_type, marked, filled=0.0):
    from agents.market_intelligence.broker import trade_stream as ts
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    entry = {"id": 11, "ticker": "BRKO", "gap_pct": None, "ep_score": None, "entry_price": 10.0, "stop_price": 9.8,
             "regime": None, "signal_type": signal_type}
    conn.fetchrow = AsyncMock(return_value=entry)
    conn.execute = AsyncMock(return_value="UPDATE 1")
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    audits = []

    async def _audit(ev, s, d=""):
        audits.append(ev)
    monkeypatch.setattr(ts, "log_audit_event", _audit)
    sent = AsyncMock()
    monkeypatch.setattr(ts, "send_telegram_message", sent)
    monkeypatch.setattr(be, "planned_entry_cancel_marked", AsyncMock(return_value=marked))
    monkeypatch.setattr(om, "broker_terminal_reason", AsyncMock(return_value="broker:entry_cancelled"))
    monkeypatch.setattr(ts.alpaca, "fetch_broker_reject_reason", AsyncMock(return_value="x"))
    await ts._handle_cancel_or_reject(_cancel_event(filled=filled), "canceled", "paper")
    status_writes = [c for c in conn.execute.await_args_list if "SET status = 'cancelled'" in c.args[0]]
    return audits, sent, status_writes


@pytest.mark.asyncio
async def test_stream_a_marked_unfilled_breakout_cancel_is_not_a_broker_kill(monkeypatch):
    audits, sent, writes = await _drive_stream_cancel(monkeypatch, SID, marked=True)
    assert "breakout_v1_planned_cancel_seen" in audits and not writes and not sent.await_count


@pytest.mark.asyncio
@pytest.mark.parametrize("signal_type,marked,filled", [("magna53", True, 0.0), (SID, False, 0.0), (SID, True, 5.0)])
async def test_stream_every_other_cancel_is_recorded_and_paged_as_before(monkeypatch, signal_type, marked, filled):
    """EP (marker or not), an unmarked breakout cancel, a breakout order carrying a fill: the existing branch."""
    audits, sent, writes = await _drive_stream_cancel(monkeypatch, signal_type, marked, filled)
    assert writes and sent.await_count == 1 and "breakout_v1_planned_cancel_seen" not in audits


@pytest.mark.asyncio
async def test_the_marker_reader_matches_trade_and_order_and_fails_safe(monkeypatch):
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[{"event_type": be.PLANNED_ENTRY_CANCEL,
                                          "detail": json.dumps({"trade_id": 11, "order_id": "ord-1"})}])
    monkeypatch.setattr(be, "get_pool", AsyncMock(return_value=pool))
    assert await be.planned_entry_cancel_marked(11, "ord-1") is True
    assert await be.planned_entry_cancel_marked(11, "ord-2") is False
    assert await be.planned_entry_cancel_marked(12, "ord-1") is False
    conn.fetch = AsyncMock(side_effect=RuntimeError("db down"))
    assert await be.planned_entry_cancel_marked(11, "ord-1") is False


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 6. the strategy row, the job, the SQL copies
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_strategy_row_is_paper_enabled_size_one_with_no_cap_of_its_own():
    from tests.test_strategy_deprecation_424 import _run_seed
    from agents.market_intelligence.constants import resolve_account_mode_for_strategy
    conn = _run_seed()
    calls = [(q, a) for q, a in conn.execute_calls if "INSERT INTO mi_strategies" in q and a and a[0] == SID]
    assert len(calls) == 1
    q, args = calls[0]
    assert db.BREAKOUT_V1_STRATEGY_ID == SID and args[0] == SID
    assert "'paper'" in q and "1.0, NULL)" in q and "ON CONFLICT (strategy_id) DO NOTHING" in q
    assert "max_concurrent_positions" in q                       # F2: NULL = the paper book's shared cap of 5
    assert "live_real_enabled" not in q and "enabled" not in q.replace("live_real_enabled", "")  # column defaults
    assert resolve_account_mode_for_strategy(SimpleNamespace(phase="paper")) == "paper"
    assert db.BREAKOUT_V1_PAPER_TOGGLE == "breakout_v1_paper" and db.BREAKOUT_V1_ACCOUNT_MODE == "paper"


@pytest.mark.asyncio
async def test_the_toggle_defaults_on(monkeypatch):
    monkeypatch.delenv(db.BREAKOUT_V1_PAPER_TOGGLE_ENV, raising=False)
    monkeypatch.setattr(db, "get_safeguard_state", AsyncMock(return_value=None))
    monkeypatch.setattr(db, "_runtime_toggle_cache", {})
    assert await db.get_runtime_toggle(db.BREAKOUT_V1_PAPER_TOGGLE, db.BREAKOUT_V1_PAPER_TOGGLE_ENV, default=True)
    w = World(monkeypatch)
    tog = AsyncMock(return_value=True)
    monkeypatch.setattr(be, "get_runtime_toggle", tog)
    await w.tick()
    assert tog.await_args.args == ("breakout_v1_paper", "BREAKOUT_V1_PAPER_ENABLED")
    assert tog.await_args.kwargs == {"default": True}


def test_the_job_is_execution_owned_every_minute_in_market_hours(monkeypatch):
    """The job start_scheduler REALLY registers (captured), its trigger fields and its classification."""
    from agents.market_intelligence import scheduler as sched
    from tests.test_672_missed_job_recovery import _real_job_list
    assert "breakout_v1_entry" in sched.EXECUTION_OWNED_JOB_IDS
    assert "breakout_v1_entry" not in sched.INTELLIGENCE_OWNED_JOB_IDS
    _, jobs = _real_job_list(monkeypatch)
    job = next(j for j in jobs if j.id == "breakout_v1_entry")
    f = {fld.name: str(fld) for fld in job.trigger.fields}
    assert (f["hour"], f["minute"], f["second"], f["day_of_week"]) == ("9-15", "*", "10", "mon-fri")
    assert str(job.trigger.timezone) == "America/New_York"
    assert be.FIRST_MINUTE == 5 and be.EOD_MINUTE == 385          # 09:35 .. 15:55 ET, enforced in the tick


def _norm(sql: str) -> str:
    return " ".join(re.sub(r"--[^\n]*", "", sql).split())


@pytest.mark.asyncio
async def test_the_preflight_sql_copies_match_what_the_writers_execute(monkeypatch):
    """The statement each writer SENDS (captured) equals its deploy-time prepare copy."""
    import scripts.preflight_db_updates as pf
    from tests.conftest import make_mock_pool
    by_label = dict(pf.TRADE_LIFECYCLE_UPDATES)
    pool, conn = make_mock_pool()
    sent = []

    async def _fv(sql, *a):
        sent.append(sql)
        return 1
    conn.fetchval = _fv
    monkeypatch.setattr(be, "get_pool", AsyncMock(return_value=pool))
    await be._mark_cancelled(1, "order_placed", "o", "r")
    await be._set_unsubmitted_order(1, "order_placed", "o", stop=9.6, shares=10, level=10.0)
    assert _norm(sent[0]) == _norm(by_label["breakout_v1_entry._mark_cancelled: a planned cancel settles the row"])
    assert _norm(sent[1]) == _norm(by_label["breakout_v1_entry._set_unsubmitted_order: the stop re-priced to a new "
                                            "day low, the row re-armed"])


def test_new_skip_reasons_are_in_the_vocabulary_and_humanized():
    from agents.market_intelligence.broker import skip_reasons as sr
    for code in (sr.SETUP_NO_OPENING_RANGE_MINUTES, sr.SETUP_BREAKOUT_VOLUME_BELOW_CURVE,
                 sr.WINDOW_BREAKOUT_UNFILLED_EOD):
        assert code.split(":")[0] in sr.VALID_CATEGORIES and sr.humanize(code) != code


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 7. Review fixes 2026-10-30: check_fills (the polling backup) vs the re-price; the orphan sweep's known set
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _pending(signal_type, *, tid=11, oid="ord-1", ticker="BRKO"):
    return {"id": tid, "ticker": ticker, "entry_order_id": oid, "entry_shares": 100, "orb_low": 9.5,
            "orb_high": 10.0, "stop_price": 9.5, "entry_attempt": 1, "account_mode": "paper",
            "signal_type": signal_type}


async def _drive_check_fills(monkeypatch, row, *, marked=False, cas_hits=True):
    """check_fills on ONE pending row whose order the broker reports 'canceled'. -> (results, the CAS writes sent,
    the _update_trade_status calls, the marker reads)."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[[row], []])        # 2nd fetch = the Day-1 stop-out poll -> empty
    cas: list[tuple] = []

    async def fetchval(sql, *a):
        cas.append((sql, a))
        return a[0] if cas_hits else None
    conn.fetchval = fetchval
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    fake = MagicMock()
    fake.get_order = AsyncMock(return_value={"status": "canceled"})
    fake.get_latest_trade = AsyncMock(return_value={"price": 9.90})
    monkeypatch.setattr(om, "alpaca", fake)
    upd = AsyncMock()
    monkeypatch.setattr(om, "_update_trade_status", upd)
    marker = AsyncMock(return_value=marked)
    monkeypatch.setattr(be, "planned_entry_cancel_marked", marker)
    results = await om.check_fills()
    return results, cas, upd, marker


def test_check_fills_breakout_signal_type_is_the_strategy_id():
    assert om.BREAKOUT_V1_SIGNAL_TYPE == db.BREAKOUT_V1_STRATEGY_ID == SID


@pytest.mark.asyncio
async def test_check_fills_leaves_a_planned_breakout_cancel_to_the_minute_job(monkeypatch):
    """The re-price race: the minute job cancelled order ord-1 on purpose (marker) and is re-placing on the same row.
    The polling backup must not record it as a broker kill — nothing written, the minute job settles it."""
    results, cas, upd, marker = await _drive_check_fills(monkeypatch, _pending(SID), marked=True)
    assert results == [] and cas == [] and not upd.await_count
    assert marker.await_args.args == (11, "ord-1")


@pytest.mark.asyncio
async def test_check_fills_never_overwrites_a_breakout_row_that_moved_to_a_new_order(monkeypatch):
    """An unmarked dead breakout order, but the row has already moved on (re-priced onto ord-2): the compare-and-set
    write on (order_placed, ord-1) misses and nothing is recorded — the row under the new order stays live."""
    results, cas, upd, _ = await _drive_check_fills(monkeypatch, _pending(SID), marked=False, cas_hits=False)
    assert results == [] and not upd.await_count
    [(sql, args)] = cas
    assert "status = 'order_placed'" in sql and "entry_order_id = $2" in sql
    assert args[0] == 11 and args[1] == "ord-1" and args[3] == SID
    assert args[2].startswith("broker:")                           # the #500 broker reason is still synthesized


@pytest.mark.asyncio
async def test_check_fills_records_an_unplanned_breakout_broker_kill_compare_and_set(monkeypatch):
    results, cas, upd, _ = await _drive_check_fills(monkeypatch, _pending(SID), marked=False, cas_hits=True)
    assert results == [{"ticker": "BRKO", "action": "canceled"}] and not upd.await_count and len(cas) == 1


@pytest.mark.parametrize("signal_type", ["magna53", "magna53_smallcap", "9m_day2", None])
@pytest.mark.asyncio
async def test_check_fills_every_other_strategys_cancel_takes_the_unchanged_path(monkeypatch, signal_type):
    """EP, the small-cap lane, 9M and legacy rows: the same _update_trade_status write as before, the marker never
    consulted, no compare-and-set statement sent."""
    results, cas, upd, marker = await _drive_check_fills(monkeypatch, _pending(signal_type), marked=True)
    assert results == [{"ticker": "BRKO", "action": "canceled"}]
    upd.assert_awaited_once()
    assert upd.await_args.args[:2] == (11, "cancelled") and upd.await_args.kwargs["skip_reason"].startswith("broker:")
    assert not marker.await_count and cas == []


@pytest.mark.asyncio
async def test_the_check_fills_cas_sql_copy_matches_what_the_writer_executes(monkeypatch):
    import scripts.preflight_db_updates as pf
    from tests.conftest import make_mock_pool
    by_label = dict(pf.TRADE_LIFECYCLE_UPDATES)
    pool, conn = make_mock_pool()
    sent = []

    async def _fv(sql, *a):
        sent.append(sql)
        return 1
    conn.fetchval = _fv
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    assert await om._cancel_breakout_row_if_unchanged(1, "o", "broker:x") is True
    assert _norm(sent[0]) == _norm(by_label["order_manager._cancel_breakout_row_if_unchanged: check_fills' breakout "
                                            "cancel write (CAS)"])


@pytest.mark.asyncio
async def test_an_open_family_order_under_a_cancelled_row_is_an_orphan_and_is_swept(monkeypatch):
    """A row settled 'cancelled' while an order still rests under it (no row then owns it): swept and paged."""
    w = World(monkeypatch, rows=[_placed_row(status="cancelled", oid="ord-1")], orders=[_order(oid="ord-1")])
    await w.tick()
    assert ("cancel", "ord-1") in w.events and w.ev("breakout_v1_orphan_order")


@pytest.mark.asyncio
async def test_a_partly_filled_entry_on_a_filled_row_is_not_an_orphan(monkeypatch):
    w = World(monkeypatch, rows=[_placed_row(status="filled", oid="ord-1")],
              orders=[_order(oid="ord-1", status="partially_filled", filled=400.0)])
    out = await w.tick()
    assert not [e for e in w.events if e[0] == "cancel"] and not w.ev("breakout_v1_orphan_order") and not w.pages
    assert out["actions"]["BRKO"] == "fill_check_wait"       # the stop at the fill waits for the complete fill


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 8. HIS RULING 2026-10-29 ("Go with rec") — THE STOP AT THE FILL
#    one minute after a fill: the TRUE low through the fill minute; too wide -> sell all; else lower the stop to it
# ═══════════════════════════════════════════════════════════════════════════════════════════════
from contextlib import asynccontextmanager  # noqa: E402

FILL_AT = datetime(TODAY.year, TODAY.month, TODAY.day, 9, 37, 2, tzinfo=_ET)      # inside minute 7


def _filled_row(**over):
    r = {"id": 11, "ticker": "BRKO", "alert_date": TODAY, "account_mode": "paper", "signal_type": SID,
         "status": "filled", "exit_rule": "breakout_pp", "entry_order_id": "ord-1", "stop_order_id": "leg-1",
         "orb_high": 10.00, "orb_low": 9.80, "stop_price": 9.80, "hard_stop": 9.80, "entry_price": 10.00,
         "entry_shares": 1250.0, "remaining_shares": 1250.0, "risk_dollars": 250.0, "partial_taken": False,
         "filled_at": FILL_AT}
    r.update(over)
    return r


def _filled_orders(*, leg_stop=9.80, leg_status="new", entry_status="filled", filled_at=FILL_AT):
    return [{"id": "ord-1", "symbol": "BRKO", "side": "buy", "status": entry_status, "qty": 1250.0,
             "filled_qty": 1250.0, "filled_avg_price": 10.00, "filled_at": filled_at.isoformat(),
             "client_order_id": "apollo_paper_breakout_v1_BRKO_1"},
            {"id": "leg-1", "symbol": "BRKO", "side": "sell", "type": "stop", "status": leg_status, "qty": 1250.0,
             "filled_qty": 0, "stop_price": leg_stop, "client_order_id": "leg-coid-1"}]


def _fill_minute_bars(low7: float, *, upto: int = 7):
    return _flat_bars(7, low=9.80, high=9.95, vol=60_000.0) + [_bar(7, 9.95, 10.05, low7, 10.02, 90_000.0)] + \
        [_bar(m, 10.02, 10.06, 9.99, 10.03, 60_000.0) for m in range(8, upto + 1)]


def _fill_world(monkeypatch, *, low7=9.70, rows=None, orders=None, bars=None, replace="ok", pending_exit=0,
                lock=True, **kw):
    w = World(monkeypatch, rows=rows or [_filled_row()], orders=orders or _filled_orders(),
              bars={"BRKO": bars if bars is not None else _fill_minute_bars(low7)}, **kw)
    w.replace_mode = replace
    w.full_exit = AsyncMock(return_value=True)

    async def _set_stop_id(tid, new_id, *, reason, account_mode, **_k):
        for r in w.rows.values():                                   # the pointer write, as the real helper does it
            if r["id"] == tid:
                r["stop_order_id"] = new_id
        return True

    w.set_stop_id = AsyncMock(side_effect=_set_stop_id)
    w.coverage = AsyncMock(return_value=None)

    async def replace_order(oid, *, stop_price=None, account_mode=None, client_order_id=None, **_k):
        assert account_mode == "paper" and client_order_id.startswith("apollo_paper_breakout_v1_BRKO_")
        w.events.append(("replace", oid, stop_price))
        if w.replace_mode == "reject":
            raise RuntimeError("42210000 rejected")
        w.orders[oid]["status"] = "replaced"
        new = {"id": f"leg-{len(w.orders) + 1}", "symbol": "BRKO", "side": "sell", "type": "stop", "status": "new",
               "qty": w.orders[oid]["qty"], "filled_qty": 0, "stop_price": stop_price, "client_order_id": client_order_id}
        w.orders[new["id"]] = new
        if w.replace_mode == "raise_after_accept":                   # the broker took it, the call timed out
            raise TimeoutError("read timed out")
        return dict(new)

    async def get_position(ticker, account_mode=None):
        return {"qty": 1250.0}

    w.alpaca.replace_order = replace_order
    w.alpaca.get_position = get_position
    w.alpaca.make_client_order_id = lambda mode, sid, t: f"apollo_{mode}_{sid}_{t}_99"

    @asynccontextmanager
    async def try_lock(_tid):
        yield lock

    monkeypatch.setattr(om, "execute_full_exit", w.full_exit)
    monkeypatch.setattr(om, "get_pending_exit_qty", AsyncMock(return_value=pending_exit))
    monkeypatch.setattr(om, "_trade_advisory_try_lock", try_lock)
    monkeypatch.setattr(om, "set_stop_order_id", w.set_stop_id)
    monkeypatch.setattr(om, "_ensure_stop_coverage", w.coverage)
    monkeypatch.setattr(be, "STOP_LOWER_VERIFY_S", 0)
    return w


def _marker(w):
    return [json.loads(a[2]) for a in w.ev(be.FILL_STOP_CHECKED)]


def test_the_stop_at_fill_decision_is_his_width_rule_on_the_raw_true_low_and_never_raises_a_stop():
    d = be.stop_at_fill_decision(fill=10.00, true_low=9.70, adr20=0.06, placed_stop=9.80)
    assert d["action"] == "lower" and d["new_stop"] == 9.70 and d["width"] == pytest.approx(0.03)
    d = be.stop_at_fill_decision(fill=10.00, true_low=9.39, adr20=0.06, placed_stop=9.80)
    assert d["action"] == "sell_all" and d["reason"].startswith("setup:stop_too_wide_after_fill")
    assert be.stop_at_fill_decision(fill=10.00, true_low=9.40, adr20=0.06, placed_stop=9.80)["action"] == "lower"
    assert be.stop_at_fill_decision(fill=10.00, true_low=9.85, adr20=0.06, placed_stop=9.80)["action"] == "keep"
    assert be.stop_at_fill_decision(fill=10.00, true_low=9.804, adr20=0.06, placed_stop=9.80)["action"] == "keep"
    assert be.stop_at_fill_decision(fill=10.00, true_low=9.70, adr20=None, placed_stop=9.80)["action"] == "keep"
    rng = random.Random(1029)
    for _ in range(2000):
        fill = rng.uniform(2, 300)
        placed = fill * (1 - rng.uniform(0.001, 0.06))
        low = min(fill, placed * (1 + rng.uniform(-0.05, 0.03)))
        d = be.stop_at_fill_decision(fill=fill, true_low=low, adr20=0.06, placed_stop=placed)
        assert d["action"] == ("sell_all" if (fill - low) / fill > 0.06 else d["action"])     # cb's rule on the raw low
        if d["action"] == "lower":
            assert d["new_stop"] < placed and d["new_stop"] <= low                            # only ever lower
        bad = cb._finish_entry(fill, low, 7, fill, 0.06)
        assert (d["action"] == "sell_all") == (bad is not None and bad["reason"] == "too_wide")


def test_ruled_the_reviewers_flush_inside_the_fill_minute_is_sold_a_minute_after_the_fill():
    """The disclosed shape of review finding 2 (2026-10-30), RULED 2026-10-29: the 09:36 minute flushes to 9.80 and
    breaks 10.50 in the same minute; the resting order (stop 10.20, from the 09:36:10 tick) fills. His rule abstains
    it too-wide (`cb._entry_one('orh5')`); the check a minute after the fill reads the true low 9.80 and SELLS ALL."""
    path = [(0, 10.20, 10.45, 10.20, 10.40), (1, 10.40, 10.48, 10.30, 10.45), (2, 10.45, 10.50, 10.35, 10.40),
            (3, 10.40, 10.42, 10.25, 10.30), (4, 10.30, 10.38, 10.28, 10.35), (5, 10.35, 10.36, 10.20, 10.25),
            (6, 10.25, 10.55, 9.80, 10.52)]
    m, o, h, l, c = (list(x) for x in zip(*path))
    ref = cb._entry_one(cb.minute_bars_from_lists(m, o, h, l, c, [1e4] * len(m)), "orh5", 10.40, 0.06, 0.0)
    assert ref["reason"] == "too_wide" and ref["fill_minute"] == 6
    bars = [_bar(*p, 1e4) for p in path]
    resting = be.evaluate(_mins(bars, 5), list_level=10.40, adr20=0.06, vol_bar=1, last_completed=5)
    assert resting["status"] == "ok" and resting["stop"] == 10.20 and resting["level"] == 10.50
    true_low = min(float(b["low"]) for b in _mins(bars, 6).values())
    d = be.stop_at_fill_decision(fill=10.50, true_low=true_low, adr20=0.06, placed_stop=resting["stop"])
    assert true_low == 9.80 and d["action"] == "sell_all"


@pytest.mark.asyncio
async def test_a_minute_after_the_fill_a_flush_in_the_fill_minute_lowers_the_stop_leg_to_the_true_low(monkeypatch):
    w = _fill_world(monkeypatch, low7=9.70)
    out = await w.tick(at=(9, 38))                                  # minute 8: the fill minute 7 is complete
    assert out["actions"]["BRKO"] == "fill_stop_lowered"
    assert ("replace", "leg-1", 9.70) in w.events                   # a price-only replace of the stop leg
    row = w.rows["BRKO"]
    assert row["stop_price"] == row["hard_stop"] == 9.70 and row["stop_order_id"] == "leg-3"
    assert row["risk_dollars_actual"] == pytest.approx(1250 * 0.30)  # $375 now vs $250 sized — recorded
    assert ("order_row", "leg-3", 9.70) in w.events                 # the successor routes as the stop
    [mk] = _marker(w)
    assert mk["decision"] == "lowered" and mk["trade_id"] == 11
    ev = w.ev("breakout_v1_stop_lowered_after_fill")
    assert ev and json.loads(ev[0][2])["risk_dollars_sized"] == 250.0
    assert w.pages == [] and not w.full_exit.await_count
    # exactly once: the next minute does nothing, and neither does a restart (the marker is read back)
    n = len(w.events)
    assert (await w.tick(at=(9, 39)))["actions"]["BRKO"] == "fill_checked"
    be._fill_checked.clear()
    assert (await w.tick(at=(9, 40)))["actions"]["BRKO"] == "fill_checked"
    assert len(w.events) == n


@pytest.mark.asyncio
async def test_too_wide_at_the_true_low_sells_the_whole_position_at_once_and_pages(monkeypatch):
    w = _fill_world(monkeypatch, low7=9.30)                          # (10.00 - 9.30) / 10.00 = 7% > ADR20 6%
    out = await w.tick(at=(9, 38))
    assert out["actions"]["BRKO"] == "fill_sold_too_wide"
    tid, reason = w.full_exit.await_args.args
    assert tid == 11 and reason.startswith("setup:stop_too_wide_after_fill")
    assert not [e for e in w.events if e[0] == "replace"]
    assert len(w.pages) == 1 and "sold the whole position" in w.pages[0]
    assert _marker(w)[0]["decision"] == "sold"
    await w.tick(at=(9, 39))
    assert w.full_exit.await_count == 1                              # exactly once


@pytest.mark.asyncio
async def test_the_page_is_paper_prefixed(monkeypatch):
    from agents.market_intelligence.constants import mode_prefix
    w = _fill_world(monkeypatch, low7=9.30)
    await w.tick(at=(9, 38))
    assert w.pages[0].startswith(mode_prefix("paper"))


@pytest.mark.asyncio
async def test_a_true_low_not_under_the_placed_stop_keeps_the_stop(monkeypatch):
    w = _fill_world(monkeypatch, low7=9.85)
    out = await w.tick(at=(9, 38))
    assert out["actions"]["BRKO"] == "fill_stop_kept" and _marker(w)[0]["decision"] == "kept"
    assert not [e for e in w.events if e[0] in ("replace", "row_stop_lowered")] and w.rows["BRKO"]["stop_price"] == 9.80


@pytest.mark.asyncio
async def test_it_waits_until_the_fill_minute_is_complete_then_up_to_three_minutes_for_its_bar(monkeypatch):
    w = _fill_world(monkeypatch, low7=9.70)
    assert (await w.tick(at=(9, 37)))["actions"]["BRKO"] == "fill_check_wait"     # minute 7 still printing
    w.bars["BRKO"] = _fill_minute_bars(9.70)[:7]                                   # the fill-minute bar not out yet
    assert (await w.tick(at=(9, 38)))["actions"]["BRKO"] == "fill_check_wait"
    assert (await w.tick(at=(9, 40)))["actions"]["BRKO"] == "fill_check_wait"
    assert not _marker(w) and not [e for e in w.events if e[0] == "replace"]
    out = await w.tick(at=(9, 41))                                                  # 3 minutes on: judged without it
    assert out["actions"]["BRKO"] == "fill_stop_kept" and _marker(w)[0]["fill_bar_seen"] is False


@pytest.mark.asyncio
async def test_the_fill_minute_is_the_brokers_fill_time_not_the_rows(monkeypatch):
    """The row's filled_at is the stream's NOW(); the broker's is the fill. Broker 09:37:02 (minute 7), row 09:39:30:
    judged at 09:38 on minute 7."""
    w = _fill_world(monkeypatch, low7=9.70, rows=[_filled_row(filled_at=FILL_AT + timedelta(minutes=2, seconds=28))])
    assert (await w.tick(at=(9, 38)))["actions"]["BRKO"] == "fill_stop_lowered"


@pytest.mark.asyncio
async def test_a_partly_filled_entry_waits_until_it_is_complete(monkeypatch):
    w = _fill_world(monkeypatch, low7=9.70, orders=_filled_orders(entry_status="partially_filled"))
    assert (await w.tick(at=(9, 38)))["actions"]["BRKO"] == "fill_check_wait"
    assert not _marker(w) and not w.events


def _replaced_leg_orders():
    """Broker truth after Alpaca accepted the lower: the OLD id reads 'replaced' (its price untouched) and a NEW id —
    in this strategy's order-id family — rests at the true low. (A replace never re-prices the same id.)"""
    orders = _filled_orders(leg_status="replaced")
    orders.append({"id": "leg-9", "symbol": "BRKO", "side": "sell", "type": "stop", "status": "new", "qty": 1250.0,
                   "filled_qty": 0, "stop_price": 9.70, "client_order_id": "apollo_paper_breakout_v1_BRKO_99"})
    return orders


@pytest.mark.asyncio
async def test_restart_after_the_replace_adopts_the_successor_and_records_it_without_replacing_again(monkeypatch):
    """A tick died after the broker accepted the lower and before the row followed: the row's leg reads 'replaced'.
    The next tick names the successor (one live family sell-stop covering the shares) and points the row at it; the
    tick after records it at its price. Never a second replace, never a re-protect."""
    w = _fill_world(monkeypatch, low7=9.70, orders=_replaced_leg_orders())
    assert (await w.tick(at=(9, 39)))["actions"]["BRKO"] == "fill_check_wait"
    assert w.rows["BRKO"]["stop_order_id"] == "leg-9" and w.ev("breakout_v1_fill_stop_successor_adopted")
    assert w.rows["BRKO"]["stop_price"] == 9.80 and not _marker(w)
    out = await w.tick(at=(9, 40))
    assert out["actions"]["BRKO"] == "fill_stop_lowered"
    row = w.rows["BRKO"]
    assert row["stop_price"] == row["hard_stop"] == 9.70 and row["stop_order_id"] == "leg-9"
    assert row["risk_dollars_actual"] == pytest.approx(1250 * 0.30)
    assert ("order_row", "leg-9", 9.70) in w.events               # the successor routes as the stop
    assert not [e for e in w.events if e[0] == "replace"] and not w.coverage.await_count
    assert _marker(w)[0]["decision"] == "lowered"


@pytest.mark.asyncio
async def test_a_replaced_leg_whose_successor_cannot_be_named_is_never_guessed(monkeypatch):
    orders = _replaced_leg_orders()
    orders.append(dict(orders[-1], id="leg-10"))                     # two family stops: ambiguous
    w = _fill_world(monkeypatch, low7=9.70, orders=orders)
    assert (await w.tick(at=(9, 39)))["actions"]["BRKO"] == "fill_check_wait"
    assert w.rows["BRKO"]["stop_order_id"] == "leg-1" and not w.ev("breakout_v1_fill_stop_successor_adopted")
    assert w.ev("breakout_v1_fill_stop_unreadable") and not w.coverage.await_count and not _marker(w)
    w = _fill_world(monkeypatch, low7=9.70, orders=_replaced_leg_orders())
    w.orders["leg-9"]["client_order_id"] = "apollo_paper_magna53_BRKO_1"   # another strategy's stop: never adopted
    assert (await w.tick(at=(9, 39)))["actions"]["BRKO"] == "fill_check_wait"
    assert w.rows["BRKO"]["stop_order_id"] == "leg-1" and not w.ev("breakout_v1_fill_stop_successor_adopted")


@pytest.mark.asyncio
async def test_the_row_points_at_the_successor_before_the_verify_polls(monkeypatch):
    """The process dies during the verify polls (here: the first read of the successor raises): the row ALREADY
    points at the successor, so the next tick records it — no dead pointer, no second replace."""
    w = _fill_world(monkeypatch, low7=9.70)
    real_get = w.alpaca.get_order

    async def dies_on_successor(oid, account_mode=None, timeout=None):
        if oid != "leg-1" and oid != "ord-1":
            raise SystemExit("killed mid-poll")
        return await real_get(oid, account_mode=account_mode)

    w.alpaca.get_order = dies_on_successor
    with pytest.raises(SystemExit):
        await be._check_stop_at_fill(dict(w.rows["BRKO"]), dict(_LIST), w.now.replace(hour=9, minute=38), 8)
    assert w.orders["leg-1"]["status"] == "replaced" and w.rows["BRKO"]["stop_order_id"] == "leg-3"
    w.alpaca.get_order = real_get
    out = await w.tick(at=(9, 39))
    assert out["actions"]["BRKO"] == "fill_stop_lowered"
    assert [e for e in w.events if e[0] == "replace"] == [("replace", "leg-1", 9.70)]
    assert w.rows["BRKO"]["stop_price"] == 9.70 and _marker(w)[0]["decision"] == "lowered"


@pytest.mark.asyncio
async def test_a_replace_that_raises_after_the_broker_took_it_adopts_the_successor_never_re_protects(monkeypatch):
    w = _fill_world(monkeypatch, low7=9.70, replace="raise_after_accept")
    assert (await w.tick(at=(9, 38)))["actions"]["BRKO"] == "fill_check_wait"
    assert w.rows["BRKO"]["stop_order_id"] == "leg-3" and not w.coverage.await_count
    assert not w.ev("breakout_v1_stop_lower_failed")
    out = await w.tick(at=(9, 39))
    assert out["actions"]["BRKO"] == "fill_stop_lowered" and w.rows["BRKO"]["stop_price"] == 9.70
    assert len([e for e in w.events if e[0] == "replace"]) == 1


@pytest.mark.asyncio
async def test_a_rejected_lower_keeps_the_old_stop_pages_once_and_retries(monkeypatch):
    w = _fill_world(monkeypatch, low7=9.70, replace="reject")
    assert (await w.tick(at=(9, 38)))["actions"]["BRKO"] == "fill_lower_rejected"
    assert w.rows["BRKO"]["stop_price"] == 9.80 and not _marker(w) and len(w.pages) == 1
    w.replace_mode = "ok"
    assert (await w.tick(at=(9, 39)))["actions"]["BRKO"] == "fill_stop_lowered"
    assert len(w.pages) == 1 and w.rows["BRKO"]["stop_price"] == 9.70


@pytest.mark.asyncio
async def test_never_lowered_beside_a_third_in_flight_or_a_stop_already_at_cost(monkeypatch):
    w = _fill_world(monkeypatch, low7=9.70, pending_exit=416)
    assert (await w.tick(at=(9, 38)))["actions"]["BRKO"] == "fill_superseded"
    assert not [e for e in w.events if e[0] == "replace"] and _marker(w)[0]["decision"] == "superseded_by_exit"
    w = _fill_world(monkeypatch, low7=9.70, orders=_filled_orders(leg_stop=10.00))
    assert (await w.tick(at=(9, 38)))["actions"]["BRKO"] == "fill_superseded"
    assert not [e for e in w.events if e[0] == "replace"]


@pytest.mark.asyncio
async def test_a_trade_lock_held_by_an_exit_defers_to_the_next_minute(monkeypatch):
    w = _fill_world(monkeypatch, low7=9.70, lock=False)
    assert (await w.tick(at=(9, 38)))["actions"]["BRKO"] == "fill_check_wait"
    assert not [e for e in w.events if e[0] == "replace"] and not _marker(w)


@pytest.mark.asyncio
async def test_a_sale_that_fails_pages_and_retries_and_a_closed_row_is_only_marked(monkeypatch):
    w = _fill_world(monkeypatch, low7=9.30)
    w.full_exit.return_value = False
    assert (await w.tick(at=(9, 38)))["actions"]["BRKO"] == "fill_sale_failed"
    assert not _marker(w) and len(w.pages) == 1 and w.ev("breakout_v1_fill_sale_failed")
    w.rows["BRKO"]["status"] = "closed"
    w.rows["BRKO"]["remaining_shares"] = 0
    out = await be._check_stop_at_fill(_filled_row(), dict(_LIST), w.now.replace(minute=39), 9)
    assert out == "fill_closed" and _marker(w)[0]["decision"] == "closed_before_sale"


@pytest.mark.asyncio
async def test_the_stop_at_the_fill_still_runs_with_the_switch_off_but_never_on_a_refused_phase(monkeypatch):
    w = _fill_world(monkeypatch, low7=9.70, toggle=False)
    out = await w.tick(at=(9, 38))
    assert out["skipped"] == "switched_off" and out["actions"]["BRKO"] == "fill_stop_lowered"
    w = _fill_world(monkeypatch, low7=9.70, phase="live")
    out = await w.tick(at=(9, 38))
    assert "BRKO" not in out["actions"] and not [e for e in w.events if e[0] == "replace"]


@pytest.mark.asyncio
async def test_a_non_breakout_or_non_paper_row_is_never_touched(monkeypatch):
    w = _fill_world(monkeypatch, low7=9.70, rows=[_filled_row(signal_type="lowcap_paper")])
    out = await w.tick(at=(9, 38))
    assert out["actions"]["BRKO"] == "owned_by_lowcap_paper" and not w.events
    for bad in (_filled_row(signal_type="magna53"), _filled_row(account_mode="live")):
        assert await be._check_stop_at_fill(bad, dict(_LIST), w.now, 8) == "untouched"
    assert not w.events and not _marker(w)


@pytest.mark.asyncio
async def test_a_fill_the_last_tick_cannot_judge_is_paged_not_left_silent(monkeypatch):
    late = datetime(TODAY.year, TODAY.month, TODAY.day, 15, 55, 3, tzinfo=_ET)       # minute 385, the last tick's
    w = _fill_world(monkeypatch, rows=[_filled_row(filled_at=late)], orders=_filled_orders(filled_at=late),
                    bars=_fill_minute_bars(9.70, upto=384))
    out = await w.tick(at=(15, 55))
    assert out["actions"]["BRKO"] == "fill_check_wait" and w.ev("breakout_v1_fill_stop_unchecked")
    assert len(w.pages) == 1 and "could not be" in w.pages[0]


@pytest.mark.asyncio
async def test_the_lowered_stop_row_write_is_its_preflight_copy(monkeypatch):
    import scripts.preflight_db_updates as pf
    from tests.conftest import make_mock_pool
    by_label = dict(pf.TRADE_LIFECYCLE_UPDATES)
    pool, conn = make_mock_pool()
    sent = []

    async def _fv(sql, *a):
        sent.append((sql, a))
        return 1
    conn.fetchval = _fv
    monkeypatch.setattr(be, "get_pool", AsyncMock(return_value=pool))
    assert await be._record_stop_lowered(11, stop_order_id="leg-2", new_stop=9.7, risk_dollars_actual=375.0)
    sql, args = sent[0]
    assert _norm(sql) == _norm(by_label["breakout_v1_entry._record_stop_lowered: the stop lowered to the true low "
                                        "after the fill"])
    assert args == (11, "leg-2", 9.7, 375.0, SID, "paper")


def test_the_lowered_stop_writer_is_registered_for_exactly_its_columns():
    from scripts.audit_column_writes import ALLOWED_WRITERS
    owned = {c for c, w in ALLOWED_WRITERS.items() if "breakout_v1_entry._record_stop_lowered" in w}
    assert owned == {"stop_order_id", "stop_price", "hard_stop", "risk_dollars_actual"}


def test_the_after_fill_exit_reason_is_in_the_vocabulary_and_humanized():
    from agents.market_intelligence.broker import skip_reasons as sr
    assert sr.SETUP_STOP_TOO_WIDE_AFTER_FILL == "setup:stop_too_wide_after_fill"
    assert sr.humanize(sr.SETUP_STOP_TOO_WIDE_AFTER_FILL + ": x") != sr.SETUP_STOP_TOO_WIDE_AFTER_FILL + ": x"


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# pre-merge 2026-10-31 (advisor item 3) — a 15:55 fill is checked by the 16:45 pass, on the refreshed GTC stop
# ═══════════════════════════════════════════════════════════════════════════════════════════════
LATE_FILL_AT = datetime(TODAY.year, TODAY.month, TODAY.day, 15, 55, 3, tzinfo=_ET)       # minute 385: no tick after it
EVENING = datetime(TODAY.year, TODAY.month, TODAY.day, 16, 45, tzinfo=_ET)


def _late_fill_bars(low385: float):
    return _flat_bars(385, low=9.80, high=9.95, vol=60_000.0) + [_bar(385, 9.95, 10.05, low385, 10.02, 90_000.0)]


def _evening_world(monkeypatch, *, low385=9.70, pointer="gtc-1", gtc_status="accepted", **kw):
    """The breakout day's evening: the entry's DAY stop leg EXPIRED at the close and the 16:20 post-close refresh
    placed a simple GTC stop at the row's (placed) stop — the row's pointer is on it (`pointer='gtc-1'`), or still on
    the dead leg when the refresh missed (`pointer='leg-1'`)."""
    orders = _filled_orders(leg_status="expired", filled_at=LATE_FILL_AT) + [
        {"id": "gtc-1", "symbol": "BRKO", "side": "sell", "type": "stop", "status": gtc_status, "qty": 1250.0,
         "filled_qty": 0, "stop_price": 9.80, "order_class": "simple", "client_order_id": "apollo_paper_breakout_v1_BRKO_7"}]
    return _fill_world(monkeypatch, rows=[_filled_row(filled_at=LATE_FILL_AT, stop_order_id=pointer)], orders=orders,
                       bars=_late_fill_bars(low385), **kw)


@pytest.mark.asyncio
async def test_a_1555_fill_is_checked_by_the_evening_pass_on_the_refreshed_gtc_stop_and_only_once(monkeypatch):
    """The disclosed 15:55 race: the minute job's last tick cannot judge the fill minute. The 16:45 pass runs the same
    check on the breakout day's minutes (every minute complete) and lowers the REFRESHED GTC stop (a price-only
    replace) to the true low; the row follows; the marker makes it once. The alternative pass — the next session's
    first tick — never sees a row filled the day before (its population is today's rows for last night's list)."""
    w = _evening_world(monkeypatch, low385=9.70)
    out = await be.check_stop_at_fill_after_close(w.rows["BRKO"], now_et=EVENING)
    assert out == "fill_stop_lowered"
    assert ("replace", "gtc-1", 9.70) in w.events                           # the refreshed stop, not the dead leg
    assert not [e for e in w.events if e[0] == "replace" and e[1] == "leg-1"]
    row = w.rows["BRKO"]
    assert row["stop_price"] == row["hard_stop"] == 9.70 and row["stop_order_id"] != "gtc-1"
    [mk] = _marker(w)
    assert mk["decision"] == "lowered" and mk["trade_id"] == 11 and mk["new_stop"] == 9.70
    assert w.pages == [] and not w.full_exit.await_count
    n = len(w.events)
    assert await be.check_stop_at_fill_after_close(w.rows["BRKO"], now_et=EVENING) == "fill_checked"
    be._fill_checked.clear()                                                # a restart re-reads the marker
    assert await be.check_stop_at_fill_after_close(w.rows["BRKO"], now_et=EVENING) == "fill_checked"
    assert len(w.events) == n


@pytest.mark.asyncio
async def test_the_evening_pass_leaves_a_pointer_on_a_dead_leg_alone_and_does_not_retry_it(monkeypatch):
    """The 16:20 refresh missed: the row still points at the EXPIRED day leg. Nothing is replaced and no stop is placed
    on top of one the row cannot see — audited, paged once, no marker — and the check is NOT retried the next evening
    (pre-merge 2026-10-31, review low: the pass visits only rows filled THIS session, so an older fill is never
    re-decided from its day-0 bars). The position never carries a stop WIDER than the one it filled with; on this path
    the lowered one never arrives, and the page says so."""
    w = _evening_world(monkeypatch, low385=9.70, pointer="leg-1")
    out = await be.check_stop_at_fill_after_close(w.rows["BRKO"], now_et=EVENING)
    assert out == "fill_check_wait"
    assert not [e for e in w.events if e[0] == "replace"] and not _marker(w)
    assert w.ev("breakout_v1_fill_stop_unreadable") and w.ev("breakout_v1_fill_stop_unchecked_after_close")
    assert len(w.pages) == 1 and "after the close" in w.pages[0] and "NOT retried" in w.pages[0]
    w.rows["BRKO"]["stop_order_id"] = "gtc-1"                               # the next morning's refresh placed one
    n = len(w.events)
    out = await be.check_stop_at_fill_after_close(w.rows["BRKO"], now_et=EVENING + timedelta(days=1))
    assert out == "fill_other_session" and len(w.events) == n and not _marker(w) and len(w.pages) == 1
    assert w.rows["BRKO"]["stop_price"] == 9.80                             # the stop stands as it filled


@pytest.mark.asyncio
async def test_a_day0_not_checkable_row_is_never_re_decided_on_a_later_evening_after_a_restart(monkeypatch):
    """Review low (pre-merge 2026-10-31): the 16:45 pass visits EVERY open breakout row every evening, and the marker
    lookup was 3 days deep — after a restart (the in-memory cache gone) a row filled more than 3 days ago read 'not
    checked' and was re-decidable from its day-0 bars: a `not_checkable` row (no bars that evening) could be SOLD days
    after the fill once the bars existed. Now (a) the pass checks only a row filled THIS session, and (b) the marker is
    read regardless of age."""
    w = _evening_world(monkeypatch, low385=9.30)
    w.bars["BRKO"] = []                                                      # no minute bars that evening
    assert await be.check_stop_at_fill_after_close(w.rows["BRKO"], now_et=EVENING) == "fill_not_checkable"
    [mk] = _marker(w)
    assert mk["decision"] == "not_checkable"
    # a restart, days later: the bars now exist and the true low is TOO WIDE — the row is never re-decided
    be._fill_checked.clear()
    w.bars["BRKO"] = _late_fill_bars(9.30)
    n_sql, n_ev = len(w.sql), len(w.events)
    for days in (1, 4, 10):
        out = await be.check_stop_at_fill_after_close(w.rows["BRKO"], now_et=EVENING + timedelta(days=days))
        assert out == "fill_other_session"
    assert not w.full_exit.await_count and len(w.events) == n_ev and len(_marker(w)) == 1
    assert len(w.sql) == n_sql                                               # no read of any kind: not this session's row
    # (b) the same session after a restart: the marker is found whatever its age — the read carries no date bound
    be._fill_checked.clear()
    assert await be.check_stop_at_fill_after_close(w.rows["BRKO"], now_et=EVENING) == "fill_checked"
    [marker_sql] = [s for s in w.sql[n_sql:] if "mi_audit_log" in s]
    assert "INTERVAL" not in marker_sql
    assert not w.full_exit.await_count and len(_marker(w)) == 1
    # the minute job's own caller is unchanged: today's row, checked once
    assert 11 in be._fill_checked


@pytest.mark.asyncio
async def test_the_evening_pass_sells_a_too_wide_fill_and_touches_no_other_row(monkeypatch):
    w = _evening_world(monkeypatch, low385=9.30)                              # (10.00 - 9.30) / 10.00 = 7% > ADR20 6%
    assert await be.check_stop_at_fill_after_close(w.rows["BRKO"], now_et=EVENING) == "fill_sold_too_wide"
    w.full_exit.assert_awaited_once()
    assert w.full_exit.await_args.args[0] == 11 and _marker(w)[0]["decision"] == "sold"
    for bad in (_filled_row(signal_type="magna53"), _filled_row(account_mode="live"), _filled_row(status="closed")):
        assert await be.check_stop_at_fill_after_close(bad, now_et=EVENING) == "untouched"
    assert w.full_exit.await_count == 1 and len(_marker(w)) == 1
