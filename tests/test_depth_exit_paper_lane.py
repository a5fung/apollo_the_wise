"""#687 / #624 — the DEPTH exit also covers the small-cap PAPER lane (operator "Ok", 2026-10-10).

His ruling: the lane's exits mirror live MAGNA53 (his earlier #624 ruling), and the #687 depth exit
goes live Monday 2026-10-12 at noon ET through `mi_safeguard_state('magna53_depth_exit', <mode>)`.
Before this change the stamp (`order_manager.resolve_exit_rule_stamp`) fired for signal_type
'magna53' only, so a `magna53_smallcap` paper trade could never have received it.

WHAT CHANGED — one decision, in one place: the stamp is a SET, {magna53, magna53_smallcap}, and the
toggle is still read for the ROW'S OWN account mode (a 'paper' row governs paper rows, a 'live' row
governs live rows; no row = OFF; the two never cross).

WHAT MUST NOT CHANGE (the pins below):
  * a smallcap paper row is stamped only by a 'paper' toggle row — with no paper row, or with ONLY
    the live row on, it is not stamped, so the change is inert until the paper row is set;
  * live MAGNA53 is stamped exactly as before; 9M and every other strategy never are;
  * `_DEPTH_EXIT_STRATEGY` stays a STRING ("magna53") — the 19:01 sale's client-order-id fallback.

THE DOWNSTREAM POPULATION (derived, not hand-listed — see docs/setups/magna53_ep.md 2026-10-10):
every path that acts on a 'depth' row reads `exit_rule` and `account_mode` from the ROW, never
`signal_type == 'magna53'`. The sections below drive each of them with a `magna53_smallcap` row on
the PAPER account and assert the ROUTING (client order id, account_mode on every broker call, the
Telegram prefix, the audit row's mode), not just that the code ran.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import db
from agents.market_intelligence.broker import entry_pipeline as ep
from agents.market_intelligence.broker import live_tracker as lt
from agents.market_intelligence.broker import order_manager as om
from tests.test_depth_exit_rule import (
    DEPTH_STOP,
    TODAY,
    _install_1645,
    _row,
    _sale_wire,
    _stamp_capture,
    _step,
)

SMALLCAP = "magna53_smallcap"


# ══════════════════════════════════════════════════════════════════════════════════════════
# 1. The stamp — a SET, read per the ROW'S account mode
# ══════════════════════════════════════════════════════════════════════════════════════════

def _toggle_rows(monkeypatch, rows: dict[str, str]):
    """`db.get_safeguard_state` with the table's real PK semantics: ('magna53_depth_exit', mode)
    answers its OWN row or None — never another mode's, never a 'global' fallback. Records every
    read, so a test can say WHICH mode the stamp asked about."""
    seen: list[tuple[str, str]] = []

    async def _get(name, mode):
        seen.append((name, mode))
        state = rows.get(mode) if name == "magna53_depth_exit" else None
        return {"state": state} if state else None

    monkeypatch.setattr(db, "get_safeguard_state", _get)
    return seen


def test_the_stamp_covers_exactly_magna53_and_the_smallcap_lane():
    assert om._DEPTH_EXIT_STRATEGIES == frozenset({"magna53", "magna53_smallcap"})


def test_the_single_strategy_name_stays_a_string_for_the_auction_orders_id_fallback():
    """`execute_depth_open_sale` falls back to this when a row has no signal_type; the id is
    built by an f-string, so a set here would produce `apollo_live_frozenset({...})_KOD_...`."""
    assert isinstance(om._DEPTH_EXIT_STRATEGY, str)
    assert om._DEPTH_EXIT_STRATEGY == "magna53"
    assert om._DEPTH_EXIT_STRATEGY in om._DEPTH_EXIT_STRATEGIES


@pytest.mark.asyncio
async def test_a_smallcap_paper_row_is_stamped_depth_when_the_paper_toggle_is_on(monkeypatch):
    """THE NEW BEHAVIOUR. On origin/main this returns None (the stamp was magna53-only)."""
    seen = _toggle_rows(monkeypatch, {"paper": "on"})
    assert await om.resolve_exit_rule_stamp(SMALLCAP, "paper") == "depth"
    assert seen == [("magna53_depth_exit", "paper")]


@pytest.mark.asyncio
async def test_with_no_paper_row_nothing_on_the_paper_account_is_stamped(monkeypatch):
    """INERT UNTIL THE PAPER ROW: today's prod has no `magna53_depth_exit` row in either mode
    (scripts/probes/_wk1010_depth_paper/q1_toggles.out). Every paper trade stays on today's rule."""
    seen = _toggle_rows(monkeypatch, {})
    for st in (SMALLCAP, "magna53", "9m_day2"):
        assert await om.resolve_exit_rule_stamp(st, "paper") is None, st
    assert {m for _n, m in seen} == {"paper"}, "a paper row was never read from another mode"


@pytest.mark.asyncio
async def test_only_the_live_row_on_does_not_stamp_a_smallcap_paper_row(monkeypatch):
    """The per-mode routing: Monday's live row alone must leave the paper lane on today's rule —
    the lane gets depth only when the PAPER row is set (he sets both together)."""
    seen = _toggle_rows(monkeypatch, {"live": "on"})
    assert await om.resolve_exit_rule_stamp(SMALLCAP, "paper") is None
    assert seen == [("magna53_depth_exit", "paper")], "it asked for the paper row, not the live one"


@pytest.mark.asyncio
async def test_a_paper_off_row_beats_nothing_and_an_unreadable_row_fails_closed(monkeypatch):
    _toggle_rows(monkeypatch, {"paper": "off"})
    assert await om.resolve_exit_rule_stamp(SMALLCAP, "paper") is None
    monkeypatch.setattr(db, "get_safeguard_state", AsyncMock(side_effect=Exception("db down")))
    assert await om.resolve_exit_rule_stamp(SMALLCAP, "paper") is None


@pytest.mark.asyncio
async def test_live_magna53_is_stamped_exactly_as_before(monkeypatch):
    """LIVE BYTE-IDENTICAL: a live MAGNA53 row follows the LIVE row alone — the paper row, set
    or not, changes nothing about it."""
    seen = _toggle_rows(monkeypatch, {"live": "on"})
    assert await om.resolve_exit_rule_stamp("magna53", "live") == "depth"
    assert seen == [("magna53_depth_exit", "live")]

    seen = _toggle_rows(monkeypatch, {"paper": "on"})
    assert await om.resolve_exit_rule_stamp("magna53", "live") is None
    assert seen == [("magna53_depth_exit", "live")]

    _toggle_rows(monkeypatch, {"live": "on", "paper": "on"})
    assert await om.resolve_exit_rule_stamp("magna53", "live") == "depth"


@pytest.mark.asyncio
async def test_9m_and_every_other_strategy_never_get_it_and_never_read_the_toggle(monkeypatch):
    """Membership is checked BEFORE the toggle read: an excluded strategy costs no DB read."""
    seen = _toggle_rows(monkeypatch, {"live": "on", "paper": "on"})
    for st in ("9m_day2", "magna53_lowcap", "magna53_smallcap2", "", "unknown"):
        for mode in ("live", "paper"):
            assert await om.resolve_exit_rule_stamp(st, mode) is None, (st, mode)
    assert seen == []


# ── through the REAL entry funnel: the stamp lands atomically with the row's insert ────────────

async def _submit_smallcap(ticker: str) -> dict:
    """The lane's call shape (`lowcap_paper_entry`): signal_type magna53_smallcap, required mode
    'paper', no CAP+1 page. The strategy row is phase 'paper'."""
    import tests.test_461_cap_toctou_race as t461
    return await ep.submit_trade_entry(
        alert_context={"ticker": ticker, "ep_score": 71, "catalyst_quality": "strong",
                       "gap_pct": 10.0},
        spec_builder=t461._spec_builder,
        regime_record=None,
        strategy_label="MAGNA53 small-cap (paper)",
        signal_type=SMALLCAP,
        today=t461._TODAY,
        atr_14=1.0,
        fade_midpoint_ratio=None,
        require_account_mode="paper",
        page_cap_plus_one=False,
    )


@pytest.mark.asyncio
async def test_a_smallcap_paper_entry_is_stamped_inside_the_insert_transaction(monkeypatch):
    t461, stamps = _stamp_capture(monkeypatch)
    fake = t461.FakeDB()
    t461._wire(monkeypatch, fake, phase="paper", live_real_enabled=False)
    seen = _toggle_rows(monkeypatch, {"paper": "on"})

    res = await asyncio.wait_for(_submit_smallcap("KOD"), timeout=10)

    assert res["action"] == "auto_entered", res
    assert len(stamps) == 1 and stamps[0]["rule"] == "depth"
    assert stamps[0]["inside_txn_lock"], "the stamp must land atomically with the row's insert"
    row = next(r for r in fake.rows if r["ticker"] == "KOD")
    assert (row["signal_type"], row["account_mode"], row.get("exit_rule")) == (
        SMALLCAP, "paper", "depth")
    assert seen == [("magna53_depth_exit", "paper")]


@pytest.mark.asyncio
@pytest.mark.parametrize("rows", [{}, {"live": "on"}, {"paper": "off"}])
async def test_a_smallcap_paper_entry_without_the_paper_row_on_keeps_todays_rule(
        monkeypatch, rows):
    t461, stamps = _stamp_capture(monkeypatch)
    fake = t461.FakeDB()
    t461._wire(monkeypatch, fake, phase="paper", live_real_enabled=False)
    _toggle_rows(monkeypatch, rows)

    res = await asyncio.wait_for(_submit_smallcap("KOD"), timeout=10)

    assert res["action"] == "auto_entered", res
    assert stamps == []
    assert next(r for r in fake.rows if r["ticker"] == "KOD").get("exit_rule") is None


# ══════════════════════════════════════════════════════════════════════════════════════════
# 2. The 16:45 decision/mark and the evening stop raise — a smallcap row on the PAPER account
# ══════════════════════════════════════════════════════════════════════════════════════════

def _paper_row(**over):
    return _row("depth", account_mode="paper", signal_type=SMALLCAP, **over)


@pytest.mark.asyncio
async def test_1645_a_smallcap_paper_depth_row_closing_below_the_line_is_marked_not_sold(
        monkeypatch):
    conn, calls = _install_1645(monkeypatch, _paper_row(), _step("sma_stopped", 70.40, 69.10))

    out = await lt.update_open_positions_live()

    calls["execute_full_exit"].assert_not_awaited()      # today's 16:45 queued market sale: NOT used
    calls["update_stop"].assert_not_awaited()
    marks = [a for a in conn.executed if "depth_sell_pending_on" in a[0]]
    assert len(marks) == 1 and marks[0][4] == TODAY, marks
    assert out == [{"ticker": "KOD", "action": "depth_sell_pending", "hold_days": 8}]
    audit = next(c for c in calls["log_audit_event"].await_args_list
                 if c.args[0] == "depth_close_below_line")
    assert json.loads(audit.args[2])["account_mode"] == "paper"
    page = calls["send_telegram_message"].await_args_list[0].args[0]
    assert "PAPER" in page and "7:01 PM ET" in page, page      # the paper prefix, not live's


@pytest.mark.asyncio
async def test_1645_a_smallcap_paper_depth_row_still_open_raises_the_depth_stop(monkeypatch):
    """Same arithmetic as MAGNA53: line 70.40, ADR20 4% → 67.58, above breakeven 63.15."""
    _conn, calls = _install_1645(monkeypatch, _paper_row(), _step("updated", 70.40, 72.00))

    await lt.update_open_positions_live()

    calls["update_stop"].assert_awaited_once()
    args, kwargs = calls["update_stop"].await_args
    assert args == (501, 67.58) and kwargs.get("stop_source") == "depth_trail"


@pytest.mark.asyncio
async def test_1645_a_smallcap_paper_row_with_no_stamp_keeps_todays_sale(monkeypatch):
    """The inert case, driven through the 16:45 job: a smallcap paper row the toggle did not
    stamp is sold exactly as today (execute_full_exit), never marked."""
    conn, calls = _install_1645(
        monkeypatch, _row(None, account_mode="paper", signal_type=SMALLCAP),
        _step("sma_stopped", 70.40, 69.10))

    await lt.update_open_positions_live()

    calls["execute_full_exit"].assert_awaited_once_with(501, "sma_trail_stop")
    assert not [a for a in conn.executed if "depth_sell_pending_on" in a[0]]


# ══════════════════════════════════════════════════════════════════════════════════════════
# 3. The 19:01 opening-auction sale — paper routing on every broker call
# ══════════════════════════════════════════════════════════════════════════════════════════

def _paper_sale_wire(monkeypatch, **kw):
    """`_sale_wire` over a smallcap PAPER depth row, with two additions: the opg fake records the
    account_mode it was called with, and the Telegram prefix is made to name the mode."""
    row = kw.pop("row", None) or _paper_row(
        remaining_shares=6, stop_price=DEPTH_STOP, status="filled", depth_sell_pending_on=TODAY)
    h = _sale_wire(monkeypatch, row=row, **kw)
    opg_calls: list = []
    opg_raises = kw.get("opg_raises")

    async def _opg(ticker, qty, account_mode=None, client_order_id=None):
        opg_calls.append({"ticker": ticker, "qty": qty, "mode": account_mode,
                          "coid": client_order_id})
        h["events"].append(("opg", qty, client_order_id))
        if opg_raises:
            raise opg_raises
        return {"id": "opg-1", "status": "accepted"}

    monkeypatch.setattr(om.alpaca, "place_market_on_open_sell", _opg)
    monkeypatch.setattr(om, "mode_prefix", lambda m: f"[{m}] ")
    h["opg_calls"] = opg_calls
    return h


def _modes_of(mock) -> set:
    return {c.kwargs.get("account_mode") for c in mock.await_args_list}


@pytest.mark.asyncio
async def test_1901_a_smallcap_paper_depth_sale_routes_to_the_paper_account(monkeypatch):
    h = _paper_sale_wire(monkeypatch)

    ok = await om.execute_depth_open_sale(501)

    assert ok is True
    [opg] = h["opg_calls"]
    assert opg["mode"] == "paper" and opg["qty"] == 6
    assert opg["coid"].startswith("apollo_paper_magna53_smallcap_KOD_"), (
        "invariant 1: the mode-bound id names the REAL signal_type and the PAPER mode")
    assert _modes_of(h["cancel"]) == {"paper"}, "the depth stop is cancelled on the paper account"
    assert _modes_of(h["pos"]) == {"paper"} and _modes_of(h["orders"]) == {"paper"}
    placed = next(c for c in h["audit"].await_args_list if c.args[0] == "depth_open_sale_placed")
    assert json.loads(placed.args[2])["account_mode"] == "paper"
    assert h["sent"] and all(m.startswith("[paper] ") for m in h["sent"]), h["sent"]


@pytest.mark.asyncio
async def test_1901_a_rejected_smallcap_paper_auction_order_restores_the_paper_stop(monkeypatch):
    h = _paper_sale_wire(monkeypatch, opg_raises=Exception("opg rejected: market closed"))
    h["orders"].return_value = []            # the stop is gone by the restore's read

    ok = await om.execute_depth_open_sale(501)

    assert ok is False
    h["place_stop"].assert_awaited_once()
    assert h["place_stop"].await_args.args[1:3] == (6, DEPTH_STOP)
    assert h["place_stop"].await_args.kwargs["account_mode"] == "paper"
    rejected = next(c for c in h["audit"].await_args_list if c.args[0] == "full_exit_rejected")
    assert json.loads(rejected.args[2])["account_mode"] == "paper"
    assert any("Stop RESTORED" in m and m.startswith("[paper] ") for m in h["sent"]), h["sent"]


@pytest.mark.asyncio
async def test_1901_the_runner_selects_by_the_stamp_alone_not_by_strategy(monkeypatch):
    """`run_depth_open_sales` finds every marked depth row in either book. Its SQL must carry no
    `signal_type` (a smallcap row would silently drop out) and no `account_mode` FILTER (it serves
    both books). `account_mode` IS selected — only to label the failure page with the row's own book."""
    seen: dict = {}

    class _C:
        async def fetch(self, q, *a, **k):
            seen["q"], seen["args"] = " ".join(q.split()), a
            return [{"id": 501, "ticker": "KOD", "account_mode": "paper"}]

    class _A:
        async def __aenter__(self):
            return _C()

        async def __aexit__(self, *e):
            return False

    class _P:
        def acquire(self, *a, **k):
            return _A()

    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=_P()))
    sale = AsyncMock(return_value=True)
    monkeypatch.setattr(om, "execute_depth_open_sale", sale)

    out = await om.run_depth_open_sales()

    assert out == [{"trade_id": 501, "ticker": "KOD", "placed": True}]
    assert seen["args"] == ("depth",)
    assert "exit_rule = $1" in seen["q"] and "depth_sell_pending_on IS NOT NULL" in seen["q"]
    where = seen["q"].split("WHERE", 1)[1]
    assert "signal_type" not in seen["q"], seen["q"]
    assert "account_mode" not in where, f"no account_mode FILTER: {where}"
    assert "SELECT id, ticker, account_mode FROM" in seen["q"], seen["q"]
    sale.assert_awaited_once_with(501)


def _raising_runner_wire(monkeypatch, rows):
    """`run_depth_open_sales` over `rows`, every sale RAISING; capture the audit rows + pages.
    The prefix is made to name the book so a page can be told apart by its mode."""
    class _C:
        async def fetch(self, q, *a, **k):
            return rows

    class _A:
        async def __aenter__(self):
            return _C()

        async def __aexit__(self, *e):
            return False

    class _P:
        def acquire(self, *a, **k):
            return _A()

    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=_P()))
    monkeypatch.setattr(om, "execute_depth_open_sale", AsyncMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(om, "_clear_depth_sell_mark", AsyncMock())
    audit, sent = AsyncMock(), AsyncMock()
    monkeypatch.setattr(om, "log_audit_event", audit)
    monkeypatch.setattr(om, "send_telegram_message", sent)
    monkeypatch.setattr(om, "mode_prefix", lambda m: f"[{m}] ")
    return audit, sent


@pytest.mark.asyncio
async def test_1901_a_raising_paper_lane_sale_pages_and_audits_as_paper_not_as_live(monkeypatch):
    """The runner's outer page used to carry no book at all, so a paper-lane failure read like a
    live one (the lane makes a PAPER depth row an expected population). The row's own
    `account_mode` now prefixes the page and rides in the `depth_open_sale_error` detail — and a
    LIVE row in the same run is labelled live, so the label comes from the ROW, not a default."""
    audit, sent = _raising_runner_wire(monkeypatch, [
        {"id": 501, "ticker": "KOD", "account_mode": "paper"},
        {"id": 502, "ticker": "VICR", "account_mode": "live"},
    ])

    out = await om.run_depth_open_sales()

    assert [r["placed"] for r in out] == [False, False]
    pages = [c.args[0] for c in sent.await_args_list]
    assert len(pages) == 2
    assert pages[0].startswith("[paper] ") and "KOD" in pages[0], pages[0]
    assert pages[1].startswith("[live] ") and "VICR" in pages[1], pages[1]
    errs = [c for c in audit.await_args_list if c.args[0] == "depth_open_sale_error"]
    assert [json.loads(c.args[2])["account_mode"] for c in errs] == ["paper", "live"]
    assert [json.loads(c.args[2])["trade_id"] for c in errs] == [501, 502]


# ══════════════════════════════════════════════════════════════════════════════════════════
# 4. Restore after an expired / cancelled / rejected sale — paper routing
# ══════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("event", ["canceled", "expired"])
async def test_expiry_of_a_smallcap_paper_auction_order_restores_the_stop_on_the_paper_account(
        monkeypatch, event):
    """trade_stream §3: the broker cancels an unfilled opg after the open; the stop goes back on
    the account the EVENT came from (here 'paper'), sized from the broker, and the page says so."""
    from agents.market_intelligence.broker import trade_stream as ts
    from tests.test_oco_cancel_handler_566 import PLAIN_RAW, _cancel_data, _pending
    from tests.test_oco_cancel_handler_566 import _wire as _ws_wire

    h = _ws_wire(
        monkeypatch,
        pending_exit_row=_pending(purpose="full_exit", raw=PLAIN_RAW, trade_id=501),
        trade_row={"id": 501, "ticker": "KOD", "remaining_shares": 4, "stop_price": DEPTH_STOP,
                   "stop_order_id": None, "signal_type": SMALLCAP},
        position_qty=4.0,
    )
    monkeypatch.setattr(ts.alpaca, "get_open_orders", AsyncMock(return_value=[]))
    monkeypatch.setattr(om, "get_pending_exit_qty", AsyncMock(return_value=0))
    monkeypatch.setattr(om, "_read_preserved_dead_stop", AsyncMock(return_value=None))

    await ts._handle_cancel_or_reject(_cancel_data(order_id="opg-1"), event, "paper")

    h["place_stop"].assert_awaited_once()
    assert h["place_stop"].await_args.args[1:3] == (4, DEPTH_STOP)
    assert h["place_stop"].await_args.kwargs["account_mode"] == "paper"
    assert h["set_stop"].await_args.kwargs["account_mode"] == "paper"
    assert any("Stop re-placed" in m and "PAPER" in m for m in h["sent"]), h["sent"]


@pytest.mark.asyncio
async def test_the_held_shares_retry_names_the_smallcap_signal_type_and_the_paper_mode(
        monkeypatch):
    """`_retry_restore_while_shares_held` re-places the stop with a NEW submission: its client
    order id must be `apollo_paper_magna53_smallcap_...` (invariant 1) and every broker read /
    write must carry account_mode='paper'."""
    from tests.test_687_restore_retry_held_shares import STOP_PRICE, _audit_rows, _b2

    _audit_rows(monkeypatch)
    h = _b2(monkeypatch, release_at=7.0, signal_type=SMALLCAP)

    restored = await om._restore_stop_after_failed_exit(
        382, "OKTA", 3, STOP_PRICE, "paper", cancelled_stop_id="stop-1",
        reason="sma_trail_stop", signal_type=SMALLCAP)

    assert restored == om.RESTORE_PLACED
    first, retry = h["placed"]
    assert first["mode"] == "paper" and first["coid"] is None
    assert retry["mode"] == "paper"
    assert retry["coid"].startswith("apollo_paper_magna53_smallcap_OKTA_"), retry["coid"]
    assert _modes_of(h["pos"]) == {"paper"}
