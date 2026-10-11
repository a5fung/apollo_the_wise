"""#687 — every operator page of the stream's full-exit cancel/expire branch, FROZEN word for word.

WHY THIS FILE EXISTS (2026-10-10 cleanup pass). `trade_stream._handle_cancel_or_reject` §3 and its
background twin `_restore_stop_after_dead_sale_in_background` send the same five pages — re-placed,
price-already-through-the-stop, broker-flat, covered, STOP RESTORE FAILED — and the same
`exit_reason` read, each written out in both places. Folding them behind one builder is only safe if
nothing an operator reads, and nothing the branch writes, moves by a byte. The expected values
below were captured from the code BEFORE that fold (HEAD d9631f63, both paths) and pasted in as
literals: they are the identity proof, and they stay as the pin on the wording.

Both paths are driven through their real code on the #687 convergence harness (NOT edited - its
sha256 is pinned by `test_687_toggle_off_convergence.py`): the inline branch end to end through
`_handle_cancel_or_reject`; the background task through `_restore_stop_after_dead_sale_in_background`
with the retry's result fixed, so every (outcome, order id) pair maps once - including the two
pairs a live broker rarely produces (a placement with no id, a market sale with no id), which must
fall through to the FAILED page on both.
"""
from __future__ import annotations

import json
import logging

import pytest

import tests._convergence_687_harness as H
from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker import trade_stream as ts
from tests._convergence_687_harness import (
    BREACH,
    World,
    _boco,
    _bsell,
    _mirror,
    _position,
    _trade,
    _ws_order,
)

OTHER_REFUSAL = '{"code":40010001,"message":"qty must be > 0"}'
_AUDIT_KEYS = ("outcome", "order_id", "qty", "stop_price", "site", "reason")


async def _drive(w, *steps):
    undo = H._install(w)
    try:
        return [await step() for step in steps]
    finally:
        H._uninstall(undo)


def _world(*, exit_reason="sma_trail_stop"):
    """A 10-sh MAGNA53 position with no stop on it and a queued full-exit sale the stream has just
    been told is dead (the 10-09 PEP shape)."""
    w = World()
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 0.0)
    _bsell(w, "sell-q", "KOD", 10, status="new")
    _mirror(w, "sell-q", 401, "KOD", "full_exit", 10, status="accepted", exit_reason=exit_reason)
    return w


def _snap(w, caplog, *, grep=("exit_reason read failed", "pointer write failed")):
    audits = []
    for a in w.audits:
        d = json.loads(a["detail"] or "{}")
        audits.append((a["event_type"], {k: d[k] for k in _AUDIT_KEYS if k in d}))
    return {
        "pages": list(w.pages),
        "audits": audits,
        "sales": [(o["purpose"], o["exit_reason"]) for o in w.orders
                  if o["alpaca_order_id"] != "sell-q"],
        "pointer": w.trades[401]["stop_order_id"],
        "logs": [r.getMessage() for r in caplog.records if any(g in r.getMessage() for g in grep)],
    }


def _raise_on_exit_reason_select(monkeypatch):
    real = H.FakeConn.fetchval

    async def _fetchval(self, sql, *a, **k):
        if "SELECT exit_reason FROM mi_live_orders" in sql:
            raise RuntimeError("db down")
        return await real(self, sql, *a, **k)
    monkeypatch.setattr(H.FakeConn, "fetchval", _fetchval)


# ── the inline branch, end to end ───────────────────────────────────────────────────────────────

async def _run_inline(w, caplog, event="expired", *pre):
    caplog.set_level(logging.WARNING)
    await _drive(w, *pre, lambda: ts._handle_cancel_or_reject(
        _ws_order("sell-q", "KOD", status=event), event, "live"))
    return _snap(w, caplog)


@pytest.mark.asyncio
async def test_inline_replaced(caplog):
    s = await _run_inline(_world(), caplog)
    assert s == EXPECTED["inline_replaced"], s


@pytest.mark.asyncio
async def test_inline_replaced_on_a_cancel(caplog):
    s = await _run_inline(_world(), caplog, "cancelled")
    assert s == EXPECTED["inline_replaced_cancelled"], s


@pytest.mark.asyncio
async def test_inline_broker_flat(caplog):
    w = _world()
    w.positions.pop("KOD")
    s = await _run_inline(w, caplog)
    assert s == EXPECTED["inline_flat"], s


@pytest.mark.asyncio
async def test_inline_every_free_share_is_held_by_another_order(caplog):
    w = _world()
    _boco(w, "oco-1", "KOD", 10)
    s = await _run_inline(w, caplog)
    assert s == EXPECTED["inline_covered"], s


@pytest.mark.asyncio
async def test_inline_price_through_the_stop_sells_at_market(caplog):
    w = _world()
    w.place_errors = [Exception(BREACH)]
    s = await _run_inline(w, caplog)
    assert s == EXPECTED["inline_sold"], s


@pytest.mark.asyncio
async def test_inline_sale_label_falls_back_to_stop_hit_when_the_row_has_no_reason(caplog):
    w = _world(exit_reason=None)
    w.place_errors = [Exception(BREACH)]
    s = await _run_inline(w, caplog)
    assert s == EXPECTED["inline_sold_no_reason"], s


@pytest.mark.asyncio
async def test_inline_sale_label_falls_back_to_stop_hit_when_the_read_fails(caplog, monkeypatch):
    _raise_on_exit_reason_select(monkeypatch)
    w = _world()
    w.place_errors = [Exception(BREACH)]
    s = await _run_inline(w, caplog)
    assert s == EXPECTED["inline_sold_read_fails"], s


@pytest.mark.asyncio
async def test_inline_failed_on_another_refusal(caplog):
    w = _world()
    w.place_errors = [Exception(OTHER_REFUSAL)]
    s = await _run_inline(w, caplog, "rejected")
    assert s == EXPECTED["inline_failed_other"], s


@pytest.mark.asyncio
async def test_inline_failed_when_the_breach_sale_fails_too(caplog):
    w = _world()
    w.place_errors = [Exception(BREACH)]
    w.close_errors = [Exception("sale refused")]
    s = await _run_inline(w, caplog)
    assert s == EXPECTED["inline_failed_sale_fails"], s


# ── the background task, one retry result per mapping ───────────────────────────────────────────

def _retry(outcome, placed, last_error="HELD: insufficient qty available"):
    return om._RestoreRetry(outcome, placed, 4, 3, 1.5, last_error)


async def _run_bg(w, caplog, monkeypatch, retry, *, event="expired", set_pointer=None):
    caplog.set_level(logging.WARNING)
    seen = {}

    async def _fake_retry(*a, **k):
        seen["reason"] = k["reason"]
        seen["also_exclude_ids"] = k["also_exclude_ids"]
        return retry
    monkeypatch.setattr(om, "_retry_restore_while_shares_held", _fake_retry)
    if set_pointer is not None:
        monkeypatch.setattr(om, "set_stop_order_id", set_pointer)

    async def _go():
        await ts._restore_stop_after_dead_sale_in_background(
            trade_id=401, ticker="KOD", symbol="KOD", account_mode="live", event_norm=event,
            order_id="sell-q", signal_type="magna53", fallback_qty=10.0, restore_qty=10,
            restore_price=58.0, cancelled_stop_id=None, first_error=Exception("HELD"))
    await _drive(w, _go)
    s = _snap(w, caplog)
    s["retry_kwargs"] = seen
    return s


@pytest.mark.asyncio
async def test_bg_replaced(caplog, monkeypatch):
    s = await _run_bg(_world(), caplog, monkeypatch, _retry(None, {"id": "stop-new-1"}))
    assert s == EXPECTED["bg_replaced"], s


@pytest.mark.asyncio
async def test_bg_replaced_even_when_the_pointer_write_fails(caplog, monkeypatch):
    async def _boom(*a, **k):
        raise RuntimeError("pointer db down")
    s = await _run_bg(_world(), caplog, monkeypatch, _retry(None, {"id": "stop-new-1"}),
                      set_pointer=_boom)
    assert s == EXPECTED["bg_replaced_pointer_fails"], s


@pytest.mark.asyncio
async def test_bg_a_placement_with_no_order_id_is_a_failure(caplog, monkeypatch):
    s = await _run_bg(_world(), caplog, monkeypatch, _retry(None, {}))
    assert s == EXPECTED["bg_placed_no_id"], s


@pytest.mark.asyncio
async def test_bg_price_through_the_stop_page_names_the_sale(caplog, monkeypatch):
    s = await _run_bg(_world(), caplog, monkeypatch,
                      _retry(om.RESTORE_SOLD, {"id": "sell-9f8e7d6c5b"}))
    assert s == EXPECTED["bg_sold"], s


@pytest.mark.asyncio
async def test_bg_a_market_sale_with_no_order_id_is_a_failure(caplog, monkeypatch):
    s = await _run_bg(_world(), caplog, monkeypatch, _retry(om.RESTORE_SOLD, None))
    assert s == EXPECTED["bg_sold_no_id"], s


@pytest.mark.asyncio
async def test_bg_broker_flat(caplog, monkeypatch):
    s = await _run_bg(_world(), caplog, monkeypatch, _retry(om.RESTORE_FLAT, None))
    assert s == EXPECTED["bg_flat"], s


@pytest.mark.asyncio
async def test_bg_covered_on_a_cancel(caplog, monkeypatch):
    s = await _run_bg(_world(), caplog, monkeypatch, _retry(om.RESTORE_COVERED, None),
                      event="cancelled")
    assert s == EXPECTED["bg_covered_cancelled"], s


@pytest.mark.asyncio
async def test_bg_failed_carries_the_retrys_last_error(caplog, monkeypatch):
    s = await _run_bg(_world(), caplog, monkeypatch, _retry(om.RESTORE_FAILED, None),
                      event="rejected")
    assert s == EXPECTED["bg_failed"], s


@pytest.mark.asyncio
async def test_bg_an_exception_pages_failed_with_the_exception(caplog, monkeypatch):
    caplog.set_level(logging.WARNING)

    async def _boom(*a, **k):
        raise RuntimeError("retry exploded")
    monkeypatch.setattr(om, "_retry_restore_while_shares_held", _boom)
    w = _world()

    async def _go():
        await ts._restore_stop_after_dead_sale_in_background(
            trade_id=401, ticker="KOD", symbol="KOD", account_mode="live", event_norm="expired",
            order_id="sell-q", signal_type="magna53", fallback_qty=10.0, restore_qty=10,
            restore_price=58.0, cancelled_stop_id=None, first_error=Exception("HELD"))
    await _drive(w, _go)
    s = _snap(w, caplog)
    assert s == EXPECTED["bg_exception"], s


@pytest.mark.asyncio
async def test_bg_reads_the_dead_sales_exit_reason_for_a_breach_sale(caplog, monkeypatch):
    s = await _run_bg(_world(exit_reason="sma_trail_stop"), caplog, monkeypatch,
                      _retry(om.RESTORE_FLAT, None))
    assert s["retry_kwargs"] == EXPECTED["bg_reason_read"], s["retry_kwargs"]


@pytest.mark.asyncio
async def test_bg_reason_falls_back_to_stop_hit_when_the_row_has_none(caplog, monkeypatch):
    s = await _run_bg(_world(exit_reason=None), caplog, monkeypatch, _retry(om.RESTORE_FLAT, None))
    assert s["retry_kwargs"] == EXPECTED["bg_reason_none"], s["retry_kwargs"]


@pytest.mark.asyncio
async def test_bg_reason_falls_back_to_stop_hit_when_the_read_fails(caplog, monkeypatch):
    _raise_on_exit_reason_select(monkeypatch)
    s = await _run_bg(_world(), caplog, monkeypatch, _retry(om.RESTORE_FLAT, None))
    assert s["retry_kwargs"] == EXPECTED["bg_reason_read_fails"], s["retry_kwargs"]
    assert s["logs"] == EXPECTED["bg_reason_read_fails_logs"], s["logs"]


# ── captured from HEAD d9631f63 (before the fold), both paths ─────────────────────────────────────
# `inline_*` = the §3 branch end to end; `bg_*` = the background task with the retry's result fixed.
# `sales` = the rows written for a breach sale; `logs` = the two loud-ok lines whose wording differs
# by path ('the market sale is labelled stop_hit' inline, 'a breach sale is labelled stop_hit' here).
EXPECTED: dict = {
    'inline_replaced': {
        'pages': [
            (
                '💰 LIVE-$ ⚠️ *Close order EXPIRED:* KOD\n'
                'Position still open. Stop re-placed @$58.00 for 10 sh.'
            ),
        ],
        'audits': [
            ('stop_order_id_changed', {
                    'reason': 'cancel_or_reject_restored',
                }),
        ],
        'sales': [],
        'pointer': 'stop-1',
        'logs': [],
    },
    'inline_replaced_cancelled': {
        'pages': [
            (
                '💰 LIVE-$ ⚠️ *Close order CANCELLED:* KOD\n'
                'Position still open. Stop re-placed @$58.00 for 10 sh.'
            ),
        ],
        'audits': [
            ('stop_order_id_changed', {
                    'reason': 'cancel_or_reject_restored',
                }),
        ],
        'sales': [],
        'pointer': 'stop-1',
        'logs': [],
    },
    'inline_flat': {
        'pages': [
            '💰 LIVE-$ ⚠️ *Close order EXPIRED:* KOD\n'
            + om.FLAT_RESTORE_PAGE_BODY,
        ],
        'audits': [
            ('restore_skipped_broker_flat', {
                    'stop_price': 58.0,
                    'site': 'trade_stream.full_exit_cancel_restore',
                }),
        ],
        'sales': [],
        'pointer': None,
        'logs': [],
    },
    'inline_covered': {
        'pages': [
            (
                '💰 LIVE-$ ⚠️ *Close order EXPIRED:* KOD\n'
                'Position still open. No stop re-placed: orders still resting at the broker '
                'hold every remaining share — check that one of them is a stop.'
            ),
        ],
        'audits': [],
        'sales': [],
        'pointer': None,
        'logs': [],
    },
    'inline_sold': {
        'pages': [
            (
                '💰 LIVE-$ 🚨 *Close order EXPIRED:* KOD\n'
                'The price is already below the stop $58.00, so no stop could be re-placed — '
                'selling 10 sh at market now (Order sell-1), as the triggered stop would have. '
                '_Confirms with real P&L on fill._'
            ),
        ],
        'audits': [
            ('stop_breach_market_sale', {
                    'order_id': 'sell-1',
                    'qty': 10,
                    'stop_price': 58.0,
                    'site': 'trade_stream.full_exit_cancel_restore',
                    'reason': 'sma_trail_stop',
                }),
        ],
        'sales': [
            ('full_exit', 'sma_trail_stop'),
        ],
        'pointer': None,
        'logs': [],
    },
    'inline_sold_no_reason': {
        'pages': [
            (
                '💰 LIVE-$ 🚨 *Close order EXPIRED:* KOD\n'
                'The price is already below the stop $58.00, so no stop could be re-placed — '
                'selling 10 sh at market now (Order sell-1), as the triggered stop would have. '
                '_Confirms with real P&L on fill._'
            ),
        ],
        'audits': [
            ('stop_breach_market_sale', {
                    'order_id': 'sell-1',
                    'qty': 10,
                    'stop_price': 58.0,
                    'site': 'trade_stream.full_exit_cancel_restore',
                    'reason': 'stop_hit',
                }),
        ],
        'sales': [
            ('full_exit', 'stop_hit'),
        ],
        'pointer': None,
        'logs': [],
    },
    'inline_sold_read_fails': {
        'pages': [
            (
                '💰 LIVE-$ 🚨 *Close order EXPIRED:* KOD\n'
                'The price is already below the stop $58.00, so no stop could be re-placed — '
                'selling 10 sh at market now (Order sell-1), as the triggered stop would have. '
                '_Confirms with real P&L on fill._'
            ),
        ],
        'audits': [
            ('stop_breach_market_sale', {
                    'order_id': 'sell-1',
                    'qty': 10,
                    'stop_price': 58.0,
                    'site': 'trade_stream.full_exit_cancel_restore',
                    'reason': 'stop_hit',
                }),
        ],
        'sales': [
            ('full_exit', 'stop_hit'),
        ],
        'pointer': None,
        'logs': [
            (
                'WS [live]: exit_reason read failed for KOD (db down) — the market sale is '
                'labelled stop_hit'
            ),
        ],
    },
    'inline_failed_other': {
        'pages': [
            (
                '💰 LIVE-$ 🚨 *CLOSE REJECTED + STOP RESTORE FAILED* for KOD!\n'
                '{"code":40010001,"message":"qty must be > 0"}\n'
                '*Position may be unprotected — manual intervention required.*'
            ),
        ],
        'audits': [],
        'sales': [],
        'pointer': None,
        'logs': [],
    },
    'inline_failed_sale_fails': {
        'pages': [
            (
                '💰 LIVE-$ 🚨 *CLOSE EXPIRED + STOP RESTORE FAILED* for KOD!\n'
                '{"code":42210000,"message":"stop price must be less than current price"}\n'
                '*Position may be unprotected — manual intervention required.*'
            ),
        ],
        'audits': [
            ('stop_breach_sale_failed', {
                    'qty': 10,
                    'stop_price': 58.0,
                    'site': 'trade_stream.full_exit_cancel_restore',
                }),
        ],
        'sales': [],
        'pointer': None,
        'logs': [],
    },
    'bg_replaced': {
        'pages': [
            (
                '💰 LIVE-$ ⚠️ *Close order EXPIRED:* KOD\n'
                'Position still open. Stop re-placed @$58.00 for 10 sh.'
            ),
        ],
        'audits': [
            ('stop_order_id_changed', {
                    'reason': 'cancel_or_reject_restored',
                }),
            ('stop_restore_retried', {
                    'outcome': 'restored',
                    'order_id': 'stop-new-1',
                    'qty': 10,
                    'stop_price': 58.0,
                    'site': 'order_manager.restore_after_failed_exit',
                }),
        ],
        'sales': [],
        'pointer': 'stop-new-1',
        'logs': [],
        'retry_kwargs': {
            'reason': 'sma_trail_stop',
            'also_exclude_ids': ('sell-q',),
        },
    },
    'bg_replaced_pointer_fails': {
        'pages': [
            (
                '💰 LIVE-$ ⚠️ *Close order EXPIRED:* KOD\n'
                'Position still open. Stop re-placed @$58.00 for 10 sh.'
            ),
        ],
        'audits': [
            ('stop_restore_retried', {
                    'outcome': 'restored',
                    'order_id': 'stop-new-1',
                    'qty': 10,
                    'stop_price': 58.0,
                    'site': 'order_manager.restore_after_failed_exit',
                }),
        ],
        'sales': [],
        'pointer': None,
        'logs': [
            (
                'WS [live]: KOD stop stop-new-1 placed by the retry but the pointer write '
                'failed — pointer db down'
            ),
        ],
        'retry_kwargs': {
            'reason': 'sma_trail_stop',
            'also_exclude_ids': ('sell-q',),
        },
    },
    'bg_placed_no_id': {
        'pages': [
            (
                '💰 LIVE-$ 🚨 *CLOSE EXPIRED + STOP RESTORE FAILED* for KOD!\n'
                'HELD: insufficient qty available\n'
                '*Position may be unprotected — manual intervention required.*'
            ),
        ],
        'audits': [
            ('stop_restore_retry_ended', {
                    'outcome': 'failed',
                    'order_id': None,
                    'qty': 10,
                    'stop_price': 58.0,
                    'site': 'order_manager.restore_after_failed_exit',
                }),
        ],
        'sales': [],
        'pointer': None,
        'logs': [],
        'retry_kwargs': {
            'reason': 'sma_trail_stop',
            'also_exclude_ids': ('sell-q',),
        },
    },
    'bg_sold': {
        'pages': [
            (
                '💰 LIVE-$ 🚨 *Close order EXPIRED:* KOD\n'
                'The price is already below the stop $58.00, so no stop could be re-placed — '
                'selling 10 sh at market now (Order sell-9f8), as the triggered stop would '
                'have. _Confirms with real P&L on fill._'
            ),
        ],
        'audits': [
            ('stop_restore_retry_ended', {
                    'outcome': 'sold_at_market',
                    'order_id': None,
                    'qty': 10,
                    'stop_price': 58.0,
                    'site': 'order_manager.restore_after_failed_exit',
                }),
        ],
        'sales': [],
        'pointer': None,
        'logs': [],
        'retry_kwargs': {
            'reason': 'sma_trail_stop',
            'also_exclude_ids': ('sell-q',),
        },
    },
    'bg_sold_no_id': {
        'pages': [
            (
                '💰 LIVE-$ 🚨 *CLOSE EXPIRED + STOP RESTORE FAILED* for KOD!\n'
                'HELD: insufficient qty available\n'
                '*Position may be unprotected — manual intervention required.*'
            ),
        ],
        'audits': [
            ('stop_restore_retry_ended', {
                    'outcome': 'sold_at_market',
                    'order_id': None,
                    'qty': 10,
                    'stop_price': 58.0,
                    'site': 'order_manager.restore_after_failed_exit',
                }),
        ],
        'sales': [],
        'pointer': None,
        'logs': [],
        'retry_kwargs': {
            'reason': 'sma_trail_stop',
            'also_exclude_ids': ('sell-q',),
        },
    },
    'bg_flat': {
        'pages': [
            '💰 LIVE-$ ⚠️ *Close order EXPIRED:* KOD\n'
            + om.FLAT_RESTORE_PAGE_BODY,
        ],
        'audits': [
            ('stop_restore_retry_ended', {
                    'outcome': 'broker_flat',
                    'order_id': None,
                    'qty': 10,
                    'stop_price': 58.0,
                    'site': 'order_manager.restore_after_failed_exit',
                }),
        ],
        'sales': [],
        'pointer': None,
        'logs': [],
        'retry_kwargs': {
            'reason': 'sma_trail_stop',
            'also_exclude_ids': ('sell-q',),
        },
    },
    'bg_covered_cancelled': {
        'pages': [
            (
                '💰 LIVE-$ ⚠️ *Close order CANCELLED:* KOD\n'
                'Position still open. No stop re-placed: orders still resting at the broker '
                'hold every remaining share — check that one of them is a stop.'
            ),
        ],
        'audits': [
            ('stop_restore_retry_ended', {
                    'outcome': 'covered',
                    'order_id': None,
                    'qty': 10,
                    'stop_price': 58.0,
                    'site': 'order_manager.restore_after_failed_exit',
                }),
        ],
        'sales': [],
        'pointer': None,
        'logs': [],
        'retry_kwargs': {
            'reason': 'sma_trail_stop',
            'also_exclude_ids': ('sell-q',),
        },
    },
    'bg_failed': {
        'pages': [
            (
                '💰 LIVE-$ 🚨 *CLOSE REJECTED + STOP RESTORE FAILED* for KOD!\n'
                'HELD: insufficient qty available\n'
                '*Position may be unprotected — manual intervention required.*'
            ),
        ],
        'audits': [
            ('stop_restore_retry_ended', {
                    'outcome': 'failed',
                    'order_id': None,
                    'qty': 10,
                    'stop_price': 58.0,
                    'site': 'order_manager.restore_after_failed_exit',
                }),
        ],
        'sales': [],
        'pointer': None,
        'logs': [],
        'retry_kwargs': {
            'reason': 'sma_trail_stop',
            'also_exclude_ids': ('sell-q',),
        },
    },
    'bg_exception': {
        'pages': [
            (
                '💰 LIVE-$ 🚨 *CLOSE EXPIRED + STOP RESTORE FAILED* for KOD!\n'
                'retry exploded\n'
                '*Position may be unprotected — manual intervention required.*'
            ),
        ],
        'audits': [],
        'sales': [],
        'pointer': None,
        'logs': [],
    },
    'bg_reason_read': {
        'reason': 'sma_trail_stop',
        'also_exclude_ids': ('sell-q',),
    },
    'bg_reason_none': {
        'reason': 'stop_hit',
        'also_exclude_ids': ('sell-q',),
    },
    'bg_reason_read_fails': {
        'reason': 'stop_hit',
        'also_exclude_ids': ('sell-q',),
    },
    'bg_reason_read_fails_logs': [
        (
            'WS [live]: exit_reason read failed for KOD (db down) — a breach sale is '
            'labelled stop_hit'
        ),
    ],
}
