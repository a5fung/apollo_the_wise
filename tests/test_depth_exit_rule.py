"""#687 B — the DEPTH exit rule for new MAGNA53 trades (operator-ruled 2026-09-29), behind the
`magna53_depth_exit` runtime toggle (default OFF).

The rule, in the order the money moves:
  * ENTRY — a MAGNA53 row created while the toggle is ON for its account mode is stamped
    `exit_rule='depth'` inside the insert's own transaction and keeps it for life. Rows the
    toggle did not stamp (NULL — every trade before it, KOD and VICR included) keep today's stop.
    Flipping the toggle never changes an open trade's rule.
  * RESTING STOP — from day 1, max(hard stop, entry once breakeven is armed,
    round(line × (1 − ADR20%), 2)), line = today's trailing line, ADR20% = the mean daily
    (high − low)/close over the 20 sessions BEFORE entry. Raised by the 16:45 job through
    `update_stop` (raise-only). PARITY: equals the #687 analysis walker's resting stop on a golden
    file built from the walker's own lines (`scripts/probes/_687/depth_stop_golden.py`).
  * DECISION — on the TRUE close at 16:45, `apply_daily_exit_step` unchanged; a close below the
    line only MARKS the trade "sell at the next open" and the depth stop stays on.
  * SALE — 19:01 ET: under the per-trade lock, cancel the depth stop → wait for the shares →
    market-on-open AUCTION sell (TIF opg) for the broker position minus a resting profit-take
    third (which keeps its own target and breakeven stop) → `full_exit` row → clear the mark.
    Rejected → restore the stop at its price and page.
  * EXPIRY — an unfilled opg is cancelled by the broker after the open → the stream's full-exit
    cancel path restores the stop, sized from the broker, and pages.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence.broker import exit_logic as el
from agents.market_intelligence.broker import live_tracker as lt
from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker.exit_logic import ExitStep

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "687_depth_stop_golden.json"


# ══════════════════════════════════════════════════════════════════════════════════════════
# 1. The resting stop — parity with the analysis walker
# ══════════════════════════════════════════════════════════════════════════════════════════

def _golden() -> dict:
    return json.loads(GOLDEN.read_text())


def test_the_live_depth_stop_equals_the_walkers_resting_stop_on_every_golden_case():
    g = _golden()
    bad = []
    for c in g["cases"]:
        live = el.depth_stop_price(line=c["line"], hard_stop=c["hard"], entry_price=c["entry"],
                                   breakeven_active=c["be_active"], adr20_pct=c["adr_pct"])
        if live != c["walker_rest"]:
            bad.append((c["label"], live, c["walker_rest"]))
    assert not bad, f"{len(bad)} of {len(g['cases'])} cases diverge from the walker: {bad[:5]}"


def test_the_golden_file_has_teeth():
    """The pin is only as good as its cases: it must include the edges AND at least one
    half-cent boundary where `line_r - 1.0*adr*line_r` and `line_r*(1-adr)` round differently —
    a live function written the 'simpler' way would fail there."""
    g = _golden()
    labels = [c["label"] for c in g["cases"]]
    assert sum("half-cent boundary" in lab for lab in labels) >= 1
    assert any("no ADR20" in lab for lab in labels)
    assert any("breakeven armed" in lab for lab in labels)
    assert len(g["cases"]) >= 300
    assert "line_r - 1.0 * adr_pct * line_r" in g["walker_block"]


def test_the_simpler_algebra_would_NOT_match_the_walker():
    """Proves the boundary cases discriminate: the alternative form misses at least one."""
    g = _golden()
    misses = 0
    for c in g["cases"]:
        if "half-cent boundary" not in c["label"]:
            continue
        line_r = round(max(c["line"], c["hard"]), 2)
        if round(line_r * (1 - c["adr_pct"]), 2) != c["walker_rest"]:
            misses += 1
    assert misses >= 1


def test_no_adr20_rests_at_the_floor_never_the_line():
    """Fewer than 10 prior sessions: the walker rests the trade at its floor ("D10
    unhostable"); so does live."""
    assert el.depth_stop_price(line=70.0, hard_stop=58.08, entry_price=63.15,
                               breakeven_active=False, adr20_pct=None) == 58.08
    assert el.depth_stop_price(line=70.0, hard_stop=58.08, entry_price=63.15,
                               breakeven_active=True, adr20_pct=None) == 63.15


def test_adr20_matches_the_replays_own_adr():
    """ADR20% is the #687 replays' ADR (`scripts/ep_replay.adr20_pct`): the last 20 sessions
    before entry, unusable bars dropped AFTER the cut, None below 10 usable."""
    from scripts.ep_replay import adr20_pct as replay_adr

    bars = []
    for i in range(30):
        c = 100.0 + i
        bars.append({"h": c * (1 + 0.01 * (i % 5 + 1)), "l": c * (1 - 0.01 * (i % 3 + 1)), "c": c})
    bars[25]["h"] = None                     # an unusable bar INSIDE the last 20
    by_day = {date(2026, 1, 1 + i): b for i, b in enumerate(bars)}
    expect, _n = replay_adr(by_day, date(2026, 2, 28))
    assert el.adr20_pct_from_bars(bars) == pytest.approx(expect, rel=1e-12)

    assert el.adr20_pct_from_bars(bars[:9]) is None
    assert el.adr20_pct_from_bars([]) is None


# ══════════════════════════════════════════════════════════════════════════════════════════
# 2. The toggle and the stamp
# ══════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("row,expect", [
    ({"state": "on"}, True), ({"state": "off"}, False), (None, False)])
async def test_the_toggle_reads_its_own_mode_row(monkeypatch, row, expect):
    from agents.market_intelligence import db
    seen = []

    async def _get(name, mode):
        seen.append((name, mode))
        return row

    monkeypatch.setattr(db, "get_safeguard_state", _get)
    assert await om._magna53_depth_exit_enabled("live") is expect
    assert seen == [("magna53_depth_exit", "live")]


@pytest.mark.asyncio
async def test_an_unreadable_toggle_fails_closed(monkeypatch):
    from agents.market_intelligence import db
    monkeypatch.setattr(db, "get_safeguard_state", AsyncMock(side_effect=Exception("db down")))
    assert await om._magna53_depth_exit_enabled("live") is False


@pytest.mark.asyncio
async def test_only_magna53_is_stamped(monkeypatch):
    monkeypatch.setattr(om, "_magna53_depth_exit_enabled", AsyncMock(return_value=True))
    assert await om.resolve_exit_rule_stamp("magna53", "live") == "depth"
    assert await om.resolve_exit_rule_stamp("magna53_lowcap", "live") is None
    assert await om.resolve_exit_rule_stamp("9m_day2", "live") is None
    monkeypatch.setattr(om, "_magna53_depth_exit_enabled", AsyncMock(return_value=False))
    assert await om.resolve_exit_rule_stamp("magna53", "live") is None


def _stamp_capture(monkeypatch):
    """Run the REAL submit_trade_entry over the #461 FakeDB and record the exit-rule stamp,
    including whether it landed while the per-mode cap transaction lock was held."""
    import tests.test_461_cap_toctou_race as t461

    stamps = []
    orig = t461.FakeConn.execute

    async def _execute(self, sql, *args):
        s = " ".join(sql.split())
        if "SET exit_rule" in s:
            stamps.append({"trade_id": args[0], "rule": args[1],
                           "inside_txn_lock": bool(self._xact_locks)})
            for r in self.db.rows:
                if r["id"] == args[0]:
                    r["exit_rule"] = args[1]
            return "UPDATE 1"
        return await orig(self, sql, *args)

    monkeypatch.setattr(t461.FakeConn, "execute", _execute)
    return t461, stamps


@pytest.mark.asyncio
async def test_a_magna53_entry_while_the_toggle_is_on_is_stamped_depth(monkeypatch):
    t461, stamps = _stamp_capture(monkeypatch)
    db = t461.FakeDB()
    t461._wire(monkeypatch, db)
    toggle = AsyncMock(return_value=True)
    monkeypatch.setattr(om, "_magna53_depth_exit_enabled", toggle)

    res = await asyncio.wait_for(t461._submit("KOD"), timeout=10)

    assert res["action"] == "auto_entered", res
    assert len(stamps) == 1 and stamps[0]["rule"] == "depth"
    assert stamps[0]["inside_txn_lock"], "the stamp must land atomically with the row's insert"
    row = next(r for r in db.rows if r["ticker"] == "KOD")
    assert row.get("exit_rule") == "depth"
    toggle.assert_awaited_once_with("live")


@pytest.mark.asyncio
async def test_toggle_off_leaves_a_new_trade_on_todays_rule(monkeypatch):
    t461, stamps = _stamp_capture(monkeypatch)
    db = t461.FakeDB()
    t461._wire(monkeypatch, db)
    monkeypatch.setattr(om, "_magna53_depth_exit_enabled", AsyncMock(return_value=False))

    await asyncio.wait_for(t461._submit("KOD"), timeout=10)

    assert stamps == []
    assert next(r for r in db.rows if r["ticker"] == "KOD").get("exit_rule") is None


# ══════════════════════════════════════════════════════════════════════════════════════════
# 3. The 16:45 job — decision on the true close, resting stop raised
# ══════════════════════════════════════════════════════════════════════════════════════════

TODAY = date(2026, 10, 6)


class _Conn:
    def __init__(self, rows):
        self.rows, self.executed = rows, []

    async def fetch(self, *_a, **_k):
        return self.rows

    async def execute(self, *a, **_k):
        self.executed.append(a)


class _Acq:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class _Pool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self, *a, **k):
        return _Acq(self.conn)


def _row(exit_rule, **over):
    r = {"id": 501, "ticker": "KOD", "alert_date": date(2026, 9, 28), "account_mode": "live",
         "remaining_shares": 4, "entry_price": 63.15, "hard_stop": 58.08, "stop_price": 63.15,
         "stop_order_id": "stop-1", "partial_taken": False, "breakeven_active": True,
         "exits": [], "running_closes": [70.0, 71.0], "exit_rule": exit_rule}
    r.update(over)
    return r


def _prior_bars():
    """25 sessions before entry with a steady 4% range → ADR20 = 0.04 exactly."""
    return [{"h": 52.0, "l": 50.0, "c": 50.0, "o": 50.5} for _ in range(25)]


def _step(action, effective_stop, close):
    closed = action == "sma_stopped"
    return ExitStep(
        action=action, closed=closed,
        close_reason="sma_trail_stop" if closed else None,
        close_price=close if closed else None, close_shares=4 if closed else None,
        close_pnl=None, partial_fired=False, partial_shares=0, partial_price=None,
        partial_pnl=None, effective_stop=effective_stop, active_sma=effective_stop,
        bar_low=close - 1, bar_close=close, hold_days=8, new_remaining=0 if closed else 4,
        new_partial_taken=False, new_breakeven_active=True,
        new_running_closes=[70.0, 71.0, close], new_exits=[], new_total_pnl=0.0,
        stop_source="trail",
    )


def _install_1645(monkeypatch, row, step):
    conn = _Conn([row])
    monkeypatch.setattr(lt, "get_pool", AsyncMock(return_value=_Pool(conn)))
    monkeypatch.setattr(lt, "et_today", lambda: TODAY)

    async def _hist(ticker, start, end, *a, **k):
        if start == end:
            return [{"h": step.bar_close + 1, "l": step.bar_low, "c": step.bar_close, "o": 70.0}]
        return _prior_bars()

    monkeypatch.setattr(lt, "get_index_history", _hist)
    monkeypatch.setattr(lt, "apply_daily_exit_step", lambda *a, **k: step)
    calls = {"update_stop": AsyncMock(return_value=True),
             "execute_full_exit": AsyncMock(return_value=True),
             "send_telegram_message": AsyncMock(), "log_audit_event": AsyncMock(),
             # #687 review fix 7 — by default the remaining shares are NOT only the OCO third
             "depth_remaining_held_by_profit_take": AsyncMock(return_value=False),
             "announce_depth_third_rests_alone": AsyncMock()}
    for name, mock in calls.items():
        monkeypatch.setattr(lt, name, mock)

    async def _toggle_must_not_be_read(*_a, **_k):
        raise AssertionError("the 16:45 job read the toggle — an open trade's rule must come "
                             "from its row alone")

    monkeypatch.setattr(om, "_magna53_depth_exit_enabled", _toggle_must_not_be_read)
    return conn, calls


@pytest.mark.asyncio
async def test_a_depth_trade_closing_below_the_line_is_marked_not_sold(monkeypatch):
    """The true close decides; the sale waits for the opening auction. Nothing is cancelled or
    sold at 16:45 and the depth stop stays on."""
    conn, calls = _install_1645(monkeypatch, _row("depth"), _step("sma_stopped", 70.40, 69.10))

    out = await lt.update_open_positions_live()

    calls["execute_full_exit"].assert_not_awaited()
    calls["update_stop"].assert_not_awaited()
    marks = [a for a in conn.executed if "depth_sell_pending_on" in a[0]]
    assert len(marks) == 1 and marks[0][4] == TODAY, marks
    assert out == [{"ticker": "KOD", "action": "depth_sell_pending", "hold_days": 8}]
    assert any("7:01 PM ET" in c.args[0] for c in calls["send_telegram_message"].await_args_list)


@pytest.mark.asyncio
async def test_a_depth_trade_held_only_by_its_oco_third_is_not_marked(monkeypatch):
    """#687 review fix 7: the only remaining shares are the profit-take third, resting on its own
    target and stop. Nothing will be sold at the open — so no mark, no "Selling at the next
    open…" (which went out EVERY evening until the third resolved); the plain sentence instead."""
    conn, calls = _install_1645(monkeypatch, _row("depth", remaining_shares=2),
                                _step("sma_stopped", 70.40, 69.10))
    calls["depth_remaining_held_by_profit_take"].return_value = True

    out = await lt.update_open_positions_live()

    assert not [a for a in conn.executed if "depth_sell_pending_on" in a[0]], "marked anyway"
    assert not any("Selling at the next open" in c.args[0]
                   for c in calls["send_telegram_message"].await_args_list)
    calls["announce_depth_third_rests_alone"].assert_awaited_once()
    calls["execute_full_exit"].assert_not_awaited()
    assert out == [{"ticker": "KOD", "action": "depth_third_rests", "hold_days": 8}]


def _announce_pool(monkeypatch, audit_rows):
    class _C:
        async def fetchval(self, q, *a, **k):
            return sum(1 for e, d in audit_rows
                       if e == "depth_close_below_third_only"
                       and json.loads(d)["trade_id"] == int(a[0]))

    class _A:
        async def __aenter__(self):
            return _C()

        async def __aexit__(self, *e):
            return False

    class _P:
        def acquire(self, *a, **k):
            return _A()

    async def _audit(event, summary="", detail=None, **k):
        audit_rows.append((event, detail))

    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=_P()))
    monkeypatch.setattr(om, "log_audit_event", _audit)
    monkeypatch.setattr(om, "mode_prefix", lambda _m: "")
    sent: list = []
    monkeypatch.setattr(om, "send_telegram_message",
                        AsyncMock(side_effect=lambda m, *a, **k: sent.append(m)))
    return sent


@pytest.mark.asyncio
async def test_the_third_only_sentence_is_sent_once_not_every_evening(monkeypatch):
    rows: list = []
    sent = _announce_pool(monkeypatch, rows)
    trade = _row("depth", remaining_shares=2)
    await om.announce_depth_third_rests_alone(trade, 69.10, 70.40)
    await om.announce_depth_third_rests_alone(trade, 68.90, 70.10)    # the next evening
    assert len(sent) == 1, sent
    assert "rests on its own target and stop" in sent[0]
    assert len(rows) == 2, "the audit row still lands every evening"


@pytest.mark.asyncio
@pytest.mark.parametrize("order_class, expect", [("oco", True), ("simple", False)])
async def test_only_an_oco_third_counts_as_holding_the_remaining_shares(
        monkeypatch, order_class, expect):
    """A PLAIN resting limit has no stop of its own — fix 9 sells it with the rest, so the
    trade must still be marked."""
    class _C:
        async def fetch(self, *a, **k):
            return [{"qty": 2, "raw_response": json.dumps({"order_class": order_class})}]

    class _A:
        async def __aenter__(self):
            return _C()

        async def __aexit__(self, *e):
            return False

    class _P:
        def acquire(self, *a, **k):
            return _A()

    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=_P()))
    assert await om.depth_remaining_held_by_profit_take(501, 2) is expect
    assert await om.depth_remaining_held_by_profit_take(501, 3) is False   # 1 sh outside it


@pytest.mark.asyncio
async def test_a_trade_without_the_stamp_keeps_todays_close_below_sale(monkeypatch):
    """KOD / VICR shape: entered before the toggle (exit_rule NULL) — today's rule, unchanged:
    `execute_full_exit` at 16:45, no depth mark. The toggle is never consulted."""
    conn, calls = _install_1645(monkeypatch, _row(None), _step("sma_stopped", 70.40, 69.10))

    await lt.update_open_positions_live()

    calls["execute_full_exit"].assert_awaited_once_with(501, "sma_trail_stop")
    assert not [a for a in conn.executed if "depth_sell_pending_on" in a[0]]


@pytest.mark.asyncio
async def test_a_depth_trade_still_open_raises_the_stop_to_the_depth_level(monkeypatch):
    """Line 70.40, ADR20 4% → round(70.40 − 0.04×70.40, 2) = 67.58, above breakeven 63.15."""
    _conn, calls = _install_1645(monkeypatch, _row("depth"), _step("updated", 70.40, 72.00))

    await lt.update_open_positions_live()

    calls["update_stop"].assert_awaited_once()
    args, kwargs = calls["update_stop"].await_args
    assert args == (501, 67.58)
    assert kwargs.get("stop_source") == "depth_trail"
    assert args[1] == el.depth_stop_price(line=70.40, hard_stop=58.08, entry_price=63.15,
                                          breakeven_active=True, adr20_pct=0.04)


@pytest.mark.asyncio
async def test_todays_rule_still_rests_the_stop_on_the_line(monkeypatch):
    _conn, calls = _install_1645(monkeypatch, _row(None), _step("updated", 70.40, 72.00))

    await lt.update_open_positions_live()

    assert calls["update_stop"].await_args.args == (501, 70.40)


@pytest.mark.asyncio
async def test_a_depth_stop_never_lowers(monkeypatch):
    """The resting stop already sits above today's depth level → no move requested (and
    `update_stop`'s broker floor would refuse one anyway)."""
    _conn, calls = _install_1645(monkeypatch, _row("depth", stop_price=68.00),
                                 _step("updated", 70.40, 72.00))
    await lt.update_open_positions_live()
    calls["update_stop"].assert_not_awaited()


# ══════════════════════════════════════════════════════════════════════════════════════════
# 4. The 19:01 sale — opening auction, under the lock
# ══════════════════════════════════════════════════════════════════════════════════════════

DEPTH_STOP = 67.58


def _sale_wire(monkeypatch, *, row=None, position_qty=6, open_orders=None, pending_rows=(),
               opg_raises=None):
    trade = row or _row("depth", remaining_shares=6, stop_price=DEPTH_STOP,
                        status="filled", depth_sell_pending_on=TODAY, signal_type="magna53")
    events: list = []
    executed: list = []

    class _C:
        async def fetchrow(self, q, *a):
            return trade if "mi_live_trades" in q else None

        async def fetch(self, q, *a, **k):
            return list(pending_rows) if "mi_live_orders" in q else []

        async def execute(self, *a, **k):
            executed.append(a)
            if "depth_sell_pending_on = NULL" in a[0]:
                events.append(("clear_mark",))
            return "UPDATE 1"

        async def fetchval(self, *a, **k):
            return None

    class _A:
        async def __aenter__(self):
            return _C()

        async def __aexit__(self, *e):
            return False

    class _P:
        def acquire(self, *a, **k):
            return _A()

    @asynccontextmanager
    async def _lock(trade_id):
        events.append(("lock",))
        try:
            yield
        finally:
            events.append(("unlock",))

    if open_orders is None:
        open_orders = [{"id": "stop-1", "side": "sell", "type": "stop", "qty": 6,
                        "filled_qty": 0, "status": "new", "order_class": "simple"}]

    async def _opg(ticker, qty, account_mode=None, client_order_id=None):
        events.append(("opg", qty, client_order_id))
        if opg_raises:
            raise opg_raises
        return {"id": "opg-1", "status": "accepted"}

    sent: list = []
    m = {
        "cancel": AsyncMock(side_effect=lambda *a, **k: events.append(("cancel", a[0])) or True),
        "pos": AsyncMock(return_value={"qty": position_qty, "qty_available": position_qty}),
        "orders": AsyncMock(return_value=[dict(o) for o in open_orders]),
        "place_stop": AsyncMock(return_value={"id": "stop-restored"}),
        "audit": AsyncMock(),
    }
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=_P()))
    monkeypatch.setattr(om, "_trade_advisory_lock", _lock)
    monkeypatch.setattr(om.alpaca, "cancel_order", m["cancel"])
    monkeypatch.setattr(om.alpaca, "get_position", m["pos"])
    monkeypatch.setattr(om.alpaca, "get_open_orders", m["orders"])
    monkeypatch.setattr(om.alpaca, "place_market_on_open_sell", _opg)
    monkeypatch.setattr(om.alpaca, "place_stop_order", m["place_stop"])
    monkeypatch.setattr(om, "log_audit_event", m["audit"])
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock(return_value=True))
    monkeypatch.setattr(om, "mode_prefix", lambda _m: "")
    monkeypatch.setattr(om, "send_telegram_message",
                        AsyncMock(side_effect=lambda msg, *a, **k: sent.append(msg)))
    monkeypatch.setattr(om, "_EXIT_RELEASE_SLEEP_S", 0)
    from agents.market_intelligence import collector
    monkeypatch.setattr(collector, "et_today", lambda: TODAY)
    return {"events": events, "executed": executed, "sent": sent, **m}


def _audited(h, event):
    return [c for c in h["audit"].await_args_list if c.args[0] == event]


@pytest.mark.asyncio
async def test_the_sale_is_an_opening_auction_order_sent_under_the_lock(monkeypatch):
    h = _sale_wire(monkeypatch)
    ok = await om.execute_depth_open_sale(501)

    assert ok is True
    names = [e[0] for e in h["events"]]
    assert names[0] == "lock" and names[-1] == "unlock", names
    assert names.index("cancel") < names.index("opg") < names.index("clear_mark"), names
    opg = next(e for e in h["events"] if e[0] == "opg")
    assert opg[1] == 6
    assert opg[2].startswith("apollo_live_magna53_KOD_"), "mode-bound client order id (invariant 1)"
    rows = [a for a in h["executed"] if "INSERT INTO mi_live_orders" in a[0]]
    assert rows and rows[0][2] == "opg-1" and rows[0][4] == 6.0
    assert "'full_exit'" in rows[0][0]
    assert any("opening auction" in m for m in h["sent"]), h["sent"]


@pytest.mark.asyncio
async def test_a_resting_profit_take_third_keeps_its_shares(monkeypatch):
    """Ruled: the OCO third keeps its own target and breakeven stop. Sell the position minus
    the third — 6 held, 2 under the OCO → 4."""
    oco = {"id": "oco-1", "side": "sell", "type": "limit", "qty": 2, "filled_qty": 0,
           "status": "new", "order_class": "oco"}
    stop = {"id": "stop-1", "side": "sell", "type": "stop", "qty": 4, "filled_qty": 0,
            "status": "new", "order_class": "simple"}
    h = _sale_wire(monkeypatch, open_orders=[stop, oco],
                   pending_rows=[{"alpaca_order_id": "oco-1", "purpose": "partial_exit",
                                  "qty": 2}])
    await om.execute_depth_open_sale(501)
    assert next(e for e in h["events"] if e[0] == "opg")[1] == 4
    assert [e for e in h["events"] if e[0] == "cancel"] == [("cancel", "stop-1")]


@pytest.mark.asyncio
async def test_a_plain_resting_third_without_a_stop_is_sold_in_the_auction(monkeypatch):
    """#687 review fix 9 on the depth sale: the third rests as a PLAIN limit (OCO off / fell
    back) — no stop of its own. It is cancelled first and its shares join the auction sale."""
    plain = {"id": "lim-1", "side": "sell", "type": "limit", "qty": 2, "filled_qty": 0,
             "status": "new", "order_class": "simple", "stop_price": None}
    stop = {"id": "stop-1", "side": "sell", "type": "stop", "qty": 4, "filled_qty": 0,
            "status": "new", "order_class": "simple"}
    h = _sale_wire(monkeypatch, open_orders=[stop, plain],
                   pending_rows=[{"alpaca_order_id": "lim-1", "purpose": "partial_exit",
                                  "qty": 2}])
    assert await om.execute_depth_open_sale(501) is True
    assert [e for e in h["events"] if e[0] == "cancel"] == [("cancel", "lim-1"),
                                                             ("cancel", "stop-1")]
    assert next(e for e in h["events"] if e[0] == "opg")[1] == 6


@pytest.mark.asyncio
async def test_a_rejected_auction_order_restores_the_stop_and_pages(monkeypatch):
    h = _sale_wire(monkeypatch, opg_raises=Exception("opg rejected: market closed"))
    h["orders"].return_value = []           # the stop is gone by the restore's read
    ok = await om.execute_depth_open_sale(501)

    assert ok is False
    h["place_stop"].assert_awaited_once()
    assert h["place_stop"].await_args.args[1:3] == (6, DEPTH_STOP)
    assert _audited(h, "full_exit_rejected")
    assert ("clear_mark",) in h["events"]
    assert any("Stop RESTORED" in m for m in h["sent"]), h["sent"]


@pytest.mark.asyncio
async def test_nothing_free_to_sell_cancels_nothing_and_pages(monkeypatch):
    oco = {"id": "oco-1", "side": "sell", "type": "limit", "qty": 2, "filled_qty": 0,
           "status": "new", "order_class": "oco"}
    h = _sale_wire(monkeypatch, row=_row("depth", remaining_shares=2, stop_price=DEPTH_STOP,
                                         status="filled", depth_sell_pending_on=TODAY,
                                         stop_order_id=None),
                   position_qty=2, open_orders=[oco],
                   pending_rows=[{"alpaca_order_id": "oco-1", "purpose": "partial_exit",
                                  "qty": 2}])
    ok = await om.execute_depth_open_sale(501)

    assert ok is False
    h["cancel"].assert_not_awaited()
    assert not [e for e in h["events"] if e[0] == "opg"]
    assert _audited(h, "full_exit_skipped")
    assert ("clear_mark",) in h["events"]


@pytest.mark.asyncio
async def test_a_mark_from_an_earlier_session_is_never_sold_on(monkeypatch):
    """The rule decides on the TRUE close. A 19:01 run that was missed (or re-driven after
    midnight) must not sell on yesterday's decision — today's close may be back above the line.
    Nothing cancelled, nothing sold, the mark cleared, he is told."""
    from datetime import timedelta
    h = _sale_wire(monkeypatch, row=_row("depth", remaining_shares=6, stop_price=DEPTH_STOP,
                                         status="filled", signal_type="magna53",
                                         depth_sell_pending_on=TODAY - timedelta(days=1)))
    ok = await om.execute_depth_open_sale(501)

    assert ok is False
    h["cancel"].assert_not_awaited()
    assert not [e for e in h["events"] if e[0] == "opg"]
    assert ("clear_mark",) in h["events"]
    assert _audited(h, "depth_sale_mark_stale")
    assert any("never sent" in m for m in h["sent"]), h["sent"]


@pytest.mark.asyncio
async def test_a_row_no_longer_pending_is_left_alone(monkeypatch):
    h = _sale_wire(monkeypatch, row=_row("depth", status="closed", remaining_shares=0,
                                         depth_sell_pending_on=TODAY))
    assert await om.execute_depth_open_sale(501) is False
    h["cancel"].assert_not_awaited()
    assert not [e for e in h["events"] if e[0] == "opg"]


@pytest.mark.asyncio
async def test_a_row_without_the_depth_stamp_is_never_sold_by_the_1901_job(monkeypatch):
    h = _sale_wire(monkeypatch, row=_row(None, status="filled", depth_sell_pending_on=TODAY))
    assert await om.execute_depth_open_sale(501) is False
    h["cancel"].assert_not_awaited()


@pytest.mark.asyncio
async def test_one_failing_sale_does_not_stop_the_next(monkeypatch):
    class _C:
        async def fetch(self, q, *a, **k):
            assert a == ("depth",), "the job selects depth-stamped rows only"
            return [{"id": 1, "ticker": "AAA"}, {"id": 2, "ticker": "BBB"}]

        async def execute(self, *a, **k):
            return "UPDATE 1"

    class _A:
        async def __aenter__(self):
            return _C()

        async def __aexit__(self, *e):
            return False

    class _P:
        def acquire(self, *a, **k):
            return _A()

    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=_P()))
    sale = AsyncMock(side_effect=[RuntimeError("boom"), True])
    monkeypatch.setattr(om, "execute_depth_open_sale", sale)
    monkeypatch.setattr(om, "log_audit_event", AsyncMock())
    monkeypatch.setattr(om, "send_telegram_message", AsyncMock())

    out = await om.run_depth_open_sales()

    assert [r["placed"] for r in out] == [False, True]
    assert sale.await_count == 2


# ══════════════════════════════════════════════════════════════════════════════════════════
# 5. Expiry — the broker cancels an unfilled auction order after the open
# ══════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("event", ["canceled", "expired"])
async def test_an_unfilled_auction_order_restores_the_depth_stop_and_pages(monkeypatch, event):
    from agents.market_intelligence.broker import trade_stream as ts
    from tests.test_oco_cancel_handler_566 import PLAIN_RAW, _cancel_data, _pending
    from tests.test_oco_cancel_handler_566 import _wire as _ws_wire

    h = _ws_wire(
        monkeypatch,
        pending_exit_row=_pending(purpose="full_exit", raw=PLAIN_RAW, trade_id=501),
        trade_row={"id": 501, "ticker": "KOD", "remaining_shares": 4,
                   "stop_price": DEPTH_STOP, "stop_order_id": None},
        position_qty=4.0,
    )
    monkeypatch.setattr(ts.alpaca, "get_open_orders", AsyncMock(return_value=[]))
    monkeypatch.setattr(om, "get_pending_exit_qty", AsyncMock(return_value=0))
    monkeypatch.setattr(om, "_read_preserved_dead_stop", AsyncMock(return_value=None))

    await ts._handle_cancel_or_reject(_cancel_data(order_id="opg-1"), event, "live")

    h["place_stop"].assert_awaited_once()
    assert h["place_stop"].await_args.args[1:3] == (4, DEPTH_STOP)
    assert any("Stop re-placed" in m and "for 4 sh" in m for m in h["sent"]), h["sent"]


@pytest.mark.asyncio
async def test_an_auction_sale_that_partly_filled_commits_the_sold_shares_first(monkeypatch):
    """#687 review fix 1 — THE SHORT-SALE RISK. The opg sale of 4 sold 3 in the auction and the
    broker cancelled the last 1. The cancel branch never recorded the 3, so the books kept all
    4 and a later stop/refresh could size a sell stop for shares the account no longer held. It
    must commit the 3 through `finalize_full_exit` (idempotent per order id) BEFORE it sizes the
    restore — which then covers only the 1 share the broker still holds."""
    from agents.market_intelligence.broker import trade_stream as ts
    from tests.test_oco_cancel_handler_566 import PLAIN_RAW, _cancel_data, _pending
    from tests.test_oco_cancel_handler_566 import _wire as _ws_wire

    order: list = []
    pending = dict(_pending(purpose="full_exit", raw=PLAIN_RAW, trade_id=501),
                   exit_reason="sma_trail_stop")
    h = _ws_wire(
        monkeypatch,
        pending_exit_row=pending,
        # the row as read AFTER the commit: 4 − 3 = 1 left
        trade_row={"id": 501, "ticker": "KOD", "remaining_shares": 1,
                   "stop_price": DEPTH_STOP, "stop_order_id": None},
        position_qty=1.0,
    )
    finalize = AsyncMock(side_effect=lambda *a, **k: order.append("commit"))
    monkeypatch.setattr(om, "finalize_full_exit", finalize)
    h["place_stop"].side_effect = lambda *a, **k: order.append("restore") or {"id": "r-1"}
    monkeypatch.setattr(om, "get_pending_exit_qty", AsyncMock(return_value=0))
    monkeypatch.setattr(om, "_read_preserved_dead_stop", AsyncMock(return_value=None))

    await ts._handle_cancel_or_reject(
        _cancel_data(order_id="opg-1", filled_qty=3.0, avg=69.50), "canceled", "live")

    finalize.assert_awaited_once_with(501, 3, 69.50, "opg-1", "sma_trail_stop")
    assert order == ["commit", "restore"], order
    assert h["place_stop"].await_args.args[1:3] == (1, DEPTH_STOP)


@pytest.mark.asyncio
async def test_an_unfilled_auction_order_on_a_flat_account_places_no_stop(monkeypatch):
    """#687 review fix 1 — the books still show 4 but the broker shows NO position: a sell stop
    there would be a short sale. Place nothing; say so plainly."""
    from agents.market_intelligence.broker import trade_stream as ts
    from tests.test_oco_cancel_handler_566 import PLAIN_RAW, _cancel_data, _pending
    from tests.test_oco_cancel_handler_566 import _wire as _ws_wire

    h = _ws_wire(
        monkeypatch,
        pending_exit_row=_pending(purpose="full_exit", raw=PLAIN_RAW, trade_id=501),
        trade_row={"id": 501, "ticker": "KOD", "remaining_shares": 4,
                   "stop_price": DEPTH_STOP, "stop_order_id": None},
    )
    monkeypatch.setattr(ts.alpaca, "get_position", AsyncMock(return_value=None))
    monkeypatch.setattr(om, "get_pending_exit_qty", AsyncMock(return_value=0))
    monkeypatch.setattr(om, "_read_preserved_dead_stop", AsyncMock(return_value=None))

    await ts._handle_cancel_or_reject(_cancel_data(order_id="opg-1"), "canceled", "live")

    h["place_stop"].assert_not_awaited()
    assert any("NO position" in m for m in h["sent"]), h["sent"]


@pytest.mark.asyncio
async def test_a_restore_rejected_because_price_is_through_the_stop_sells_at_market(monkeypatch):
    """#687 review fix 3 (b): the opg died unfilled and the stop restore is REJECTED — the price
    is already below the depth stop. The exit rule had already decided to sell (that is what the
    opg was); do what a triggered stop does: sell the free shares at market at once, as a
    `full_exit` row (its fill commits through `finalize_full_exit`), and page."""
    from agents.market_intelligence.broker import trade_stream as ts
    from tests.test_oco_cancel_handler_566 import PLAIN_RAW, _cancel_data, _pending
    from tests.test_oco_cancel_handler_566 import _wire as _ws_wire

    pending = dict(_pending(purpose="full_exit", raw=PLAIN_RAW, trade_id=501),
                   exit_reason="sma_trail_stop")
    h = _ws_wire(monkeypatch, pending_exit_row=pending,
                 trade_row={"id": 501, "ticker": "KOD", "remaining_shares": 4,
                            "stop_price": DEPTH_STOP, "stop_order_id": None},
                 position_qty=4.0)
    h["place_stop"].side_effect = Exception(
        'stop price must be less than current price (stop_price: "67.58", last: "66.10")')
    monkeypatch.setattr(om, "get_pending_exit_qty", AsyncMock(return_value=0))
    monkeypatch.setattr(om, "_read_preserved_dead_stop", AsyncMock(return_value=None))
    close = AsyncMock(return_value={"id": "mkt-1", "status": "accepted"})
    monkeypatch.setattr(om.alpaca, "close_position", close)
    sale_rows: list = []

    class _C:
        async def execute(self, *a, **k):
            sale_rows.append(a)

    class _A:
        async def __aenter__(self):
            return _C()

        async def __aexit__(self, *e):
            return False

    class _P:
        def acquire(self, *a, **k):
            return _A()

    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=_P()))
    monkeypatch.setattr(om, "log_audit_event", AsyncMock())

    await ts._handle_cancel_or_reject(_cancel_data(order_id="opg-1"), "canceled", "live")

    close.assert_awaited_once()
    assert close.await_args.kwargs.get("qty") == 4
    row = next(a for a in sale_rows if "INSERT INTO mi_live_orders" in a[0])
    assert "'full_exit'" in row[0] and row[2] == "mkt-1" and row[6] == "sma_trail_stop"
    assert any("selling 4 sh at market" in m for m in h["sent"]), h["sent"]


# ── #687 review fix 3 (a): the 09:00 watchdog must not dedup a queued sale past the open ─────

def _watchdog_world(monkeypatch, *, orders_per_tick, place_raises=None, position_qty=4.0):
    """One depth trade whose stop was cancelled for the 19:01 opening-auction sale (pointer
    NULL), driven through `_stop_ack_timeout_watchdog_job` tick by tick. The fake DB honours
    the watchdog's once-a-day dedup (the three event types) against the audit rows it writes,
    and lists one `full_exit` mirror row (the opg). `orders_per_tick[i]` is what the broker
    lists on tick i."""
    from datetime import datetime

    from agents.market_intelligence import briefing, db

    audit: list = []
    placed: list = []
    sent: list = []
    stuck = {"id": 501, "ticker": "KOD", "account_mode": "live", "orb_low": 50.0,
             "entry_shares": 6, "remaining_shares": 4, "stop_price": DEPTH_STOP,
             "filled_at": datetime(2026, 9, 28, 13, 31), "entry_order_id": "entry-1"}
    _DEDUP = ("stop_ack_timeout_remediated", "stop_ack_remediation_failed",
              "stop_ack_broker_covered")

    class _WConn:
        async def fetch(self, *a, **k):
            return [stuck]

        async def fetchrow(self, *a, **k):
            return {"status": "filled", "stop_order_id": None}

        async def fetchval(self, q, *a, **k):
            if "stop_ack_timeout_remediated" in q:          # the once-a-day dedup
                return 1 if any(e in _DEDUP for e, *_ in audit) else None
            if "FROM mi_live_orders" in q:                   # the opg mirror row
                return "sma_trail_stop"
            return None

    class _WAcq:
        async def __aenter__(self):
            return _WConn()

        async def __aexit__(self, *e):
            return False

    class _WPool:
        def acquire(self, *a, **k):
            return _WAcq()

    @asynccontextmanager
    async def _try_lock(_tid):
        yield True

    async def _audit(event, summary="", detail=None, **k):
        audit.append((event, summary, detail))

    async def _tg(msg, *a, **k):
        sent.append(msg)

    tick = {"n": 0}

    async def _orders(*a, **k):
        return [dict(o) for o in orders_per_tick[min(tick["n"], len(orders_per_tick) - 1)]]

    async def _place(ticker, qty, price, account_mode=None, **k):
        placed.append((qty, price))
        if place_raises:
            raise place_raises
        return {"id": "fallback-1"}

    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=_WPool()))
    monkeypatch.setattr(db, "log_audit_event", _audit)
    monkeypatch.setattr(om, "log_audit_event", _audit)
    monkeypatch.setattr(briefing, "send_telegram_message", _tg)
    monkeypatch.setattr(om, "_trade_advisory_try_lock", _try_lock)
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock(return_value=True))
    monkeypatch.setattr(om, "_read_preserved_dead_stop", AsyncMock(return_value=None))
    monkeypatch.setattr(om.alpaca, "get_open_orders", _orders)
    monkeypatch.setattr(om.alpaca, "get_position", AsyncMock(
        return_value=None if position_qty is None else {"qty": position_qty,
                                                         "qty_available": position_qty}))
    monkeypatch.setattr(om.alpaca, "place_stop_order", _place)

    async def _run_tick():
        from agents.market_intelligence import scheduler
        await scheduler._stop_ack_timeout_watchdog_job()
        tick["n"] += 1

    return {"audit": audit, "placed": placed, "sent": sent, "tick": _run_tick}


_OPG = {"id": "opg-1", "side": "sell", "type": "market", "time_in_force": "opg", "qty": 4,
        "filled_qty": 0, "status": "accepted", "order_class": "simple", "stop_price": None}


@pytest.mark.asyncio
async def test_a_queued_auction_sale_is_not_deduped_past_the_open(monkeypatch):
    """THE NAKED WINDOW: 09:00 the opg covers the 4 shares → the old watchdog wrote
    `stop_ack_broker_covered` (in its 24h dedup) and never looked again. 09:30 the opg is
    cancelled unfilled and the stream's restore is missed → nothing re-protected all session.
    Now the 09:00 coverage is noted WITHOUT burning the day, and the first tick after the opg
    is gone re-places the stop — at the trade's own depth stop, never the entry-day orb_low."""
    w = _watchdog_world(monkeypatch, orders_per_tick=[[_OPG], []])

    await w["tick"]()                                   # 09:00 — the opg is queued
    assert w["placed"] == []
    assert not [e for e, *_ in w["audit"] if e == "stop_ack_broker_covered"], (
        "a queued sale was recorded as the day's coverage — the dedup would blind the watchdog")
    assert [e for e, *_ in w["audit"] if e == "stop_ack_covered_by_exit_order"]

    await w["tick"]()                                   # 09:31 — the opg died unfilled
    assert w["placed"] == [(4, DEPTH_STOP)], w["placed"]
    assert any("closing order no longer live" in m for m in w["sent"]), w["sent"]


@pytest.mark.asyncio
async def test_after_the_open_a_stop_through_the_market_sells_at_market(monkeypatch):
    """Fix 3 (b) on the watchdog path: the re-protect is rejected because the price is already
    below the depth stop — sell the free shares at market now and page."""
    w = _watchdog_world(monkeypatch, orders_per_tick=[[]], place_raises=Exception(
        "stop price must be less than current price"))
    close = AsyncMock(return_value={"id": "mkt-2", "status": "accepted"})
    monkeypatch.setattr(om.alpaca, "close_position", close)
    rows: list = []

    class _C:
        async def execute(self, *a, **k):
            rows.append(a)

    class _A:
        async def __aenter__(self):
            return _C()

        async def __aexit__(self, *e):
            return False

    class _P:
        def acquire(self, *a, **k):
            return _A()

    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=_P()))

    await w["tick"]()

    close.assert_awaited_once()
    assert close.await_args.kwargs.get("qty") == 4
    assert any("selling 4 sh at market" in m for m in w["sent"]), w["sent"]
    assert not any("CRITICAL" in m for m in w["sent"]), w["sent"]


@pytest.mark.asyncio
async def test_the_watchdog_never_places_a_stop_on_a_flat_position(monkeypatch):
    """The opg FILLED a moment before its fill was committed: the row still says 4 sh, the
    broker is flat. A sell stop there would be a short sale — place nothing."""
    w = _watchdog_world(monkeypatch, orders_per_tick=[[]], position_qty=None)
    await w["tick"]()
    assert w["placed"] == []
    assert [e for e, *_ in w["audit"] if e == "stop_ack_broker_flat"]


# ══════════════════════════════════════════════════════════════════════════════════════════
# 6. The 19:01 job is registered where the broker lives
# ══════════════════════════════════════════════════════════════════════════════════════════

def test_the_sale_job_runs_at_1901_et_weekdays_in_the_execution_service(monkeypatch):
    from agents.market_intelligence import scheduler as sched
    from tests.test_672_missed_job_recovery import _real_job_list

    _s, jobs = _real_job_list(monkeypatch)
    job = next(j for j in jobs if j.id == "depth_open_auction_sale")
    trig = str(job.trigger)
    assert "hour='19'" in trig and "minute='1'" in trig and "day_of_week='mon-fri'" in trig, trig
    assert str(job.trigger.timezone) == "America/New_York"
    assert "depth_open_auction_sale" in sched.EXECUTION_OWNED_JOB_IDS


@pytest.mark.asyncio
async def test_the_job_drives_the_sale_runner(monkeypatch):
    from agents.market_intelligence import constants, scheduler as sched
    monkeypatch.setattr(constants, "LIVE_TRADING_ENABLED", True)
    runner = AsyncMock(return_value=[])
    monkeypatch.setattr(om, "run_depth_open_sales", runner)
    await sched._depth_open_auction_sale_job()
    runner.assert_awaited_once()
