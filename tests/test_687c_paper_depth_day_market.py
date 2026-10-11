"""#687 option (c) — on the PAPER account the 19:01 depth sale is a regular DAY market sell queued
overnight; LIVE keeps the opening-auction (opg) order. HIS RULING 2026-10-10 (*"got it, c"*).

WHY: Alpaca's paper simulator never fills an opening-auction order. The only paper opg ever sent —
PEP, 3 sh, queued Thu 2026-10-08 19:01 ET by the production job — EXPIRED Fri 09:30:57 ET with
`filled_qty 0`; KO's DAY market sale queued at 16:45 ET the same evening FILLED at 09:32:04 ET
(`scripts/probes/_1008/dayB_opg_order.out`). With opg on paper, the small-cap lane's depth exit would
never sell at the next open, which is the whole of what the depth rule exists to do.

WHAT MUST HOLD (every behaviour change below is RED on origin/main):
  * a PAPER row -> `alpaca.place_market_sell` (TIF DAY), account_mode='paper', the SAME mode-bound
    client order id (`apollo_paper_<signal_type>_<ticker>_...`), the SAME qty, the SAME
    cancel-stop -> wait-for-shares -> sell -> full_exit-row -> clear-mark sequence;
  * a LIVE row -> `alpaca.place_market_on_open_sell` exactly as before (and the DAY helper is NEVER
    called for it);
  * the audit rows say which vehicle was used ('opg' live, 'day_market' paper);
  * paper pages say "at the open", never "opening auction" / "Opening-auction"; live pages are
    byte-identical to before;
  * a paper sale that is rejected restores the stop inline; one that expires (a DAY order that does not
    fill by 16:00 ET) or is cancelled hits the SAME trade_stream §3 restore the opg sale hits.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence.broker import live_tracker as lt
from agents.market_intelligence.broker import order_manager as om
from tests.test_depth_exit_rule import (
    DEPTH_STOP,
    TODAY,
    _audited,
    _install_1645,
    _row,
    _sale_wire,
    _step,
)

REPO = Path(__file__).resolve().parent.parent
SMALLCAP = "magna53_smallcap"


def _depth_row(account_mode, signal_type, **over):
    fields = dict(account_mode=account_mode, signal_type=signal_type, remaining_shares=6,
                  stop_price=DEPTH_STOP, status="filled", depth_sell_pending_on=TODAY)
    fields.update(over)
    return _row("depth", **fields)


def _paper_row(signal_type=SMALLCAP, **over):
    return _depth_row("paper", signal_type, **over)


def _live_row(**over):
    return _depth_row("live", "magna53", **over)


# ══════════════════════════════════════════════════════════════════════════════════════════
# 1. The vehicle selector — paper only; anything else is the auction
# ══════════════════════════════════════════════════════════════════════════════════════════

def test_the_vehicle_is_a_day_market_order_on_paper_and_the_auction_everywhere_else():
    assert om.depth_sale_vehicle("paper") == "day_market"
    assert om.depth_sale_vehicle("live") == "opg"
    # fail toward the LIVE vehicle: nothing but the literal 'paper' ever leaves the auction order
    for other in (None, "", "Paper ", "PAPER", "global", "sandbox"):
        assert om.depth_sale_vehicle(other) == "opg", other


# ══════════════════════════════════════════════════════════════════════════════════════════
# 2. The sale — paper -> DAY market; live -> opg (unchanged)
# ══════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("signal_type", [SMALLCAP, "magna53"])
async def test_a_paper_row_sells_with_a_day_market_order_never_an_opg(monkeypatch, signal_type):
    """RED on origin/main: the paper row went through `place_market_on_open_sell`.
    Both strategies: the vehicle follows the ROW'S book, not the strategy."""
    h = _sale_wire(monkeypatch, row=_paper_row(signal_type=signal_type))

    ok = await om.execute_depth_open_sale(501)

    assert ok is True
    assert h["opg_calls"] == [], "paper must never send an opening-auction order"
    [sale] = h["day_calls"]
    assert sale["mode"] == "paper" and sale["qty"] == 6 and sale["ticker"] == "KOD"
    assert sale["coid"].startswith(f"apollo_paper_{signal_type}_KOD_"), (
        "invariant 1: the SAME mode-bound client order id, naming the PAPER mode")
    names = [e[0] for e in h["events"]]
    assert names[0] == "lock" and names[-1] == "unlock", names
    assert names.index("cancel") < names.index("day_market") < names.index("clear_mark"), (
        "same sequence: cancel the stop -> (wait for the shares) -> sell -> clear the mark")
    rows = [a for a in h["executed"] if "INSERT INTO mi_live_orders" in a[0]]
    assert rows and rows[0][2] == "day-1" and rows[0][4] == 6.0 and "'full_exit'" in rows[0][0], (
        "the sale is recorded as the trade's full_exit order, so the stream finalizes / restores it")


@pytest.mark.asyncio
async def test_a_live_row_still_sends_the_opening_auction_order_and_never_the_day_helper(
        monkeypatch):
    """LIVE BYTE-IDENTICAL: the opg helper, the live mode, the live coid, the same qty — and the
    DAY helper is not called at all."""
    h = _sale_wire(monkeypatch, row=_live_row())

    ok = await om.execute_depth_open_sale(501)

    assert ok is True
    assert h["day_calls"] == [], "a live row must never use the paper vehicle"
    [sale] = h["opg_calls"]
    assert sale["mode"] == "live" and sale["qty"] == 6
    assert sale["coid"].startswith("apollo_live_magna53_KOD_")
    names = [e[0] for e in h["events"]]
    assert names.index("cancel") < names.index("opg") < names.index("clear_mark"), names


@pytest.mark.asyncio
async def test_a_paper_sale_still_waits_for_the_broker_to_release_the_shares(monkeypatch):
    """The #646 race holds on the DAY vehicle exactly as on the auction: the sell goes out only AFTER
    the poll that shows the freed shares (0, 0, then 6 free)."""
    h = _sale_wire(monkeypatch, row=_paper_row())
    polls = {"after_cancel": 0}

    async def _pos(*a, **k):
        if any(e[0] == "cancel" for e in h["events"]):
            polls["after_cancel"] += 1
            free = 6 if polls["after_cancel"] >= 3 else 0
            h["events"].append(("poll", free))
            return {"qty": 6, "qty_available": free}
        return {"qty": 6, "qty_available": 0}

    h["pos"].side_effect = _pos
    assert await om.execute_depth_open_sale(501) is True

    names = [e[0] for e in h["events"]]
    released_at = h["events"].index(("poll", 6))
    assert names.index("cancel") < released_at < names.index("day_market"), h["events"]


@pytest.mark.asyncio
async def test_a_paper_resting_profit_take_third_keeps_its_shares_on_the_day_vehicle(monkeypatch):
    """Sizing is shared, so the ruled OCO-third carve-out is unchanged on paper: 6 held, 2 under
    the OCO -> the DAY order sells 4."""
    oco = {"id": "oco-1", "side": "sell", "type": "limit", "qty": 2, "filled_qty": 0,
           "status": "new", "order_class": "oco"}
    stop = {"id": "stop-1", "side": "sell", "type": "stop", "qty": 4, "filled_qty": 0,
            "status": "new", "order_class": "simple"}
    h = _sale_wire(monkeypatch, row=_paper_row(), open_orders=[stop, oco],
                   pending_rows=[{"alpaca_order_id": "oco-1", "purpose": "partial_exit", "qty": 2}])

    await om.execute_depth_open_sale(501)

    assert [c["qty"] for c in h["day_calls"]] == [4]
    assert [e for e in h["events"] if e[0] == "cancel"] == [("cancel", "stop-1")]


# ══════════════════════════════════════════════════════════════════════════════════════════
# 3. The audit rows record the vehicle truthfully
# ══════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("row_fn,vehicle", [(_paper_row, "day_market"), (_live_row, "opg")])
async def test_the_placed_audit_names_the_vehicle(monkeypatch, row_fn, vehicle):
    h = _sale_wire(monkeypatch, row=row_fn())

    await om.execute_depth_open_sale(501)

    [placed] = _audited(h, "depth_open_sale_placed")
    assert json.loads(placed.args[2])["vehicle"] == vehicle, placed.args


@pytest.mark.asyncio
@pytest.mark.parametrize("row_fn,vehicle", [(_paper_row, "day_market"), (_live_row, "opg")])
async def test_the_rejected_audit_names_the_vehicle_that_was_rejected(monkeypatch, row_fn, vehicle):
    """The rejection row used to hardcode "opg" — a paper row's rejected DAY order would have been
    recorded as an auction order."""
    h = _sale_wire(monkeypatch, row=row_fn(), opg_raises=Exception("rejected: insufficient qty"))
    h["orders"].return_value = []

    assert await om.execute_depth_open_sale(501) is False

    [rejected] = _audited(h, "full_exit_rejected")
    assert json.loads(rejected.args[2])["vehicle"] == vehicle, rejected.args


# ══════════════════════════════════════════════════════════════════════════════════════════
# 4. A rejected paper sale restores the stop (the same restore as the auction's)
# ══════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_a_rejected_paper_day_sale_restores_the_stop_on_the_paper_account_and_pages(
        monkeypatch):
    h = _sale_wire(monkeypatch, row=_paper_row(),
                   opg_raises=Exception("insufficient qty available for order"))
    h["orders"].return_value = []            # the stop is gone by the restore's read
    monkeypatch.setattr(om, "mode_prefix", lambda m: f"[{m}] ")

    ok = await om.execute_depth_open_sale(501)

    assert ok is False
    assert len(h["day_calls"]) == 1 and h["opg_calls"] == []
    h["place_stop"].assert_awaited_once()
    assert h["place_stop"].await_args.args[1:3] == (6, DEPTH_STOP)
    assert h["place_stop"].await_args.kwargs["account_mode"] == "paper"
    assert ("clear_mark",) in h["events"]
    assert any("Stop RESTORED" in m and m.startswith("[paper] ") for m in h["sent"]), h["sent"]


# ══════════════════════════════════════════════════════════════════════════════════════════
# 5. Page wording — the vehicle is never misdescribed
# ══════════════════════════════════════════════════════════════════════════════════════════

_AUCTION_WORDS = ("opening auction", "opening-auction", "Opening-auction", "Opening auction")


def _says_auction(text: str) -> bool:
    return any(w in text for w in _AUCTION_WORDS)


@pytest.mark.asyncio
async def test_the_paper_placed_page_says_at_the_open_not_opening_auction(monkeypatch):
    h = _sale_wire(monkeypatch, row=_paper_row())

    await om.execute_depth_open_sale(501)

    [page] = h["sent"]
    assert "at the open" in page and not _says_auction(page), page
    [placed] = _audited(h, "depth_open_sale_placed")
    assert not _says_auction(placed.args[1]) and "day-market" in placed.args[1], placed.args[1]


@pytest.mark.asyncio
async def test_the_live_placed_page_and_audit_text_are_unchanged(monkeypatch):
    """Byte-identical live wording, pinned to the literal."""
    h = _sale_wire(monkeypatch, row=_live_row())

    await om.execute_depth_open_sale(501)

    [page] = h["sent"]
    assert page == (
        "📋 *Closing order placed (opening auction):* KOD — sma_trail_stop\n"
        "Sells 6 sh in the next opening auction (Order opg-1). "
        "The depth stop was cancelled; the queued sale is the exit.\n"
        "_Confirms with real P&L on fill._"), page
    [placed] = _audited(h, "depth_open_sale_placed")
    assert placed.args[1] == ("KOD: opening-auction sell 6 sh queued (sma_trail_stop); "
                              "depth stop stop-1 cancelled"), placed.args[1]


@pytest.mark.asyncio
async def test_the_rejected_page_wording_follows_the_vehicle(monkeypatch):
    paper = _sale_wire(monkeypatch, row=_paper_row(), opg_raises=Exception("boom"))
    paper["orders"].return_value = []
    await om.execute_depth_open_sale(501)
    page = next(m for m in paper["sent"] if "FAILED" in m)
    assert "Sale at the open FAILED for KOD" in page and not _says_auction(page), page
    rej = _audited(paper, "full_exit_rejected")[0].args[1]
    assert not _says_auction(rej), rej

    live = _sale_wire(monkeypatch, row=_live_row(), opg_raises=Exception("boom"))
    live["orders"].return_value = []
    await om.execute_depth_open_sale(501)
    page = next(m for m in live["sent"] if "FAILED" in m)
    assert "Opening-auction sale FAILED for KOD: boom" in page, page
    assert "opening-auction sale REJECTED" in _audited(live, "full_exit_rejected")[0].args[1]


@pytest.mark.asyncio
async def test_the_stale_mark_page_wording_follows_the_vehicle(monkeypatch):
    from datetime import timedelta
    yesterday = TODAY - timedelta(days=1)
    paper = _sale_wire(monkeypatch, row=_paper_row(depth_sell_pending_on=yesterday))
    assert await om.execute_depth_open_sale(501) is False
    [page] = paper["sent"]
    assert "never sent for the open" in page and not _says_auction(page), page

    live = _sale_wire(monkeypatch, row=_live_row(depth_sell_pending_on=yesterday))
    assert await om.execute_depth_open_sale(501) is False
    [page] = live["sent"]
    assert "was never sent to the opening auction." in page, page


@pytest.mark.asyncio
async def test_the_runner_failure_page_and_audit_wording_follow_the_rows_book(monkeypatch):
    class _C:
        async def fetch(self, q, *a, **k):
            return [{"id": 501, "ticker": "KOD", "account_mode": "paper"},
                    {"id": 502, "ticker": "VICR", "account_mode": "live"}]

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

    await om.run_depth_open_sales()

    pages = [c.args[0] for c in sent.await_args_list]
    assert pages[0].startswith("[paper] ") and not _says_auction(pages[0]), pages[0]
    assert "Sale at the open for KOD raised before it finished" in pages[0], pages[0]
    assert pages[1].startswith("[live] 🚨 Opening-auction sale for VICR raised"), pages[1]
    errs = [c.args[1] for c in audit.await_args_list if c.args[0] == "depth_open_sale_error"]
    assert not _says_auction(errs[0]) and "opening-auction sale raised" in errs[1], errs


@pytest.mark.asyncio
async def test_the_1645_page_and_audit_say_at_the_open_for_paper_and_stay_the_same_for_live(
        monkeypatch):
    """The 16:45 'closed below its line' page told the operator "the opening-auction order goes in
    at 7:01 PM ET". On paper the order is a DAY market order that fills at the open."""
    conn, calls = _install_1645(monkeypatch, _paper_row(), _step("sma_stopped", 70.40, 69.10))
    await lt.update_open_positions_live()
    page = calls["send_telegram_message"].await_args_list[0].args[0]
    assert "7:01 PM ET" in page and "at the open" in page and not _says_auction(page), page
    audit = next(c for c in calls["log_audit_event"].await_args_list
                 if c.args[0] == "depth_close_below_line")
    assert not _says_auction(audit.args[1]) and "at the next open" in audit.args[1], audit.args[1]

    conn, calls = _install_1645(monkeypatch, _live_row(), _step("sma_stopped", 70.40, 69.10))
    await lt.update_open_positions_live()
    page = calls["send_telegram_message"].await_args_list[0].args[0]
    assert page.endswith(
        "Selling at the next open: the opening-auction order goes in at 7:01 PM ET. "
        "The stop stays on until then."), page
    audit = next(c for c in calls["log_audit_event"].await_args_list
                 if c.args[0] == "depth_close_below_line")
    assert audit.args[1].endswith("selling in the next opening auction"), audit.args[1]


# ══════════════════════════════════════════════════════════════════════════════════════════
# 6. The stream side — a paper DAY market sale that expires / is cancelled / fills hits the SAME paths
# ══════════════════════════════════════════════════════════════════════════════════════════

DAY_MARKET_RAW = json.dumps({"id": "day-1", "order_class": "simple", "type": "market",
                             "time_in_force": "day", "side": "sell", "qty": 6.0})


@pytest.mark.asyncio
@pytest.mark.parametrize("event", ["expired", "canceled"])
async def test_an_expired_or_cancelled_paper_day_sale_restores_the_depth_stop_on_paper(
        monkeypatch, event):
    """PIN (unchanged code): a DAY order that does not fill by 16:00 ET is the paper analogue of an
    opg expiry. trade_stream §3 is keyed on the order's `mi_live_orders.purpose='full_exit'` row —
    which `_record_full_exit_order` writes for both vehicles — and on nothing about its TIF."""
    from agents.market_intelligence.broker import trade_stream as ts
    from tests.test_oco_cancel_handler_566 import _cancel_data, _pending
    from tests.test_oco_cancel_handler_566 import _wire as _ws_wire

    h = _ws_wire(
        monkeypatch,
        pending_exit_row=_pending(purpose="full_exit", raw=DAY_MARKET_RAW, trade_id=501),
        trade_row={"id": 501, "ticker": "KOD", "remaining_shares": 6, "stop_price": DEPTH_STOP,
                   "stop_order_id": None, "signal_type": SMALLCAP},
        position_qty=6.0,
    )
    monkeypatch.setattr(ts.alpaca, "get_open_orders", AsyncMock(return_value=[]))
    monkeypatch.setattr(om, "get_pending_exit_qty", AsyncMock(return_value=0))
    monkeypatch.setattr(om, "_read_preserved_dead_stop", AsyncMock(return_value=None))

    await ts._handle_cancel_or_reject(_cancel_data(order_id="day-1"), event, "paper")

    h["place_stop"].assert_awaited_once()
    assert h["place_stop"].await_args.args[1:3] == (6, DEPTH_STOP)
    assert h["place_stop"].await_args.kwargs["account_mode"] == "paper"
    assert h["set_stop"].await_args.kwargs["account_mode"] == "paper"
    assert any("Stop re-placed" in m and "PAPER" in m for m in h["sent"]), h["sent"]


@pytest.mark.asyncio
async def test_a_filled_paper_day_sale_is_committed_through_finalize_full_exit(monkeypatch):
    """PIN (unchanged code): the paper stream's fill handler claims the sale's `full_exit` row and
    commits it with the REAL fill price through `finalize_full_exit`, exactly as it does an opg fill
    (the claim has no TIF in it). Drives `_handle_fill` itself, not just the row's shape."""
    from types import SimpleNamespace

    from agents.market_intelligence.broker import trade_stream as ts

    claims = [None, None, {"trade_id": 501, "purpose": "full_exit",
                           "exit_reason": "sma_trail_stop", "qty": 6}]

    class _C:
        async def fetchrow(self, q, *a):
            return claims.pop(0)       # entry claim -> none; stop claim -> none; exit claim -> row

    class _A:
        async def __aenter__(self):
            return _C()

        async def __aexit__(self, *e):
            return False

    class _P:
        def acquire(self, *a, **k):
            return _A()

    fin = AsyncMock()
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=_P()))
    monkeypatch.setattr(om, "finalize_full_exit", fin)
    order = SimpleNamespace(id="day-1", symbol="KOD", filled_avg_price=65.10, filled_qty=6)

    await ts._handle_fill(SimpleNamespace(order=order, price=None, qty=None), "paper")

    fin.assert_awaited_once_with(501, 6, 65.10, "day-1", "sma_trail_stop")


@pytest.mark.asyncio
async def test_the_full_exit_row_a_paper_day_sale_writes_is_what_the_stream_routes_on(monkeypatch):
    """The link the previous test relies on: the sale's order is recorded with purpose='full_exit'
    (the stream's fill path -> finalize_full_exit, and its cancel/expiry path -> the restore)."""
    h = _sale_wire(monkeypatch, row=_paper_row())

    await om.execute_depth_open_sale(501)

    [ins] = [a for a in h["executed"] if "INSERT INTO mi_live_orders" in a[0]]
    assert "'full_exit'" in ins[0] and ins[2] == "day-1" and ins[3] == "KOD"


# ══════════════════════════════════════════════════════════════════════════════════════════
# 7. The Monday 08:25 ET paper test is unaffected; the dry run drives the REAL function
# ══════════════════════════════════════════════════════════════════════════════════════════

def test_the_monday_paper_test_still_imports():
    """The Monday 08:25 ET paper test sends its OWN opg order (`env.alpaca.place_market_on_open_sell`)
    and records it with `order_manager._record_full_exit_order`; it never calls
    `execute_depth_open_sale` (read + grepped 2026-10-11 — a source pin would add to the #653 ratchet,
    so this stays an import check). Its imports must still resolve against the changed module."""
    proc = subprocess.run(
        [sys.executable, "-c", "import scripts.probes._687.expiry_path_test"],
        cwd=REPO, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-800:]


def test_the_dry_run_prints_pass_for_the_real_function():
    """`scripts/probes/_wk1011_depth_paper_day/dryrun_vehicle.py` drives the REAL
    `execute_depth_open_sale` on fabricated rows with every broker function replaced by a recorder.
    On origin/main both rows go to the auction, so it prints DRYRUN FAIL."""
    proc = subprocess.run(
        [sys.executable, "scripts/probes/_wk1011_depth_paper_day/dryrun_vehicle.py"],
        cwd=REPO, capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0 and "DRYRUN PASS" in proc.stdout, (proc.stdout + proc.stderr)[-1500:]
