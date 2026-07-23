"""#475 (2026-07-15) — EP trade-alert noise reduction + order-rejection telemetry.

This morning's 2 live EP trades (MANE filled, AEHR rejected) produced 8
Telegrams. Operator ruling: 1 msg per trade (the FILLED msg) + real errors
only, and track broker-side order rejections before deciding any fix.

Pins the behavior-bearing pieces (all observability — no trade behavior change):

1. ORB skip digest filters WINDOW_DUPLICATE (dedup noise from the dual
   bar_stream/cron ORB trigger) but keeps every GENUINE skip; a run where only
   duplicates remain sends NO digest at all. Match is on the skip_reasons
   constant, never the humanized display string.
2. Stop-cancel "Position unprotected": ONE bounded re-check before alarming
   (MANE false-fire — a stop RE-PLACE was still in flight when the cancel WS
   event arrived). HARD INVARIANT preserved: persistent no-stop / broker read
   error STILL alarms — the re-check only absorbs the self-heal race.
3. entry_order_rejected telemetry (AEHR LULD class): mi_audit_log row with
   trade context; the "Entry REJECTED" Telegram (a real error) still fires,
   even if the telemetry emit itself blows up.
4. The FILLED msg — now the SOLE per-trade Telegram — shows the ACTUAL stop
   (mi_live_trades.stop_price; prior-day low for 9M Day 2), falling back to
   orb_low only for legacy NULL rows.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.market_intelligence.audit_events import ENTRY_ORDER_REJECTED
from agents.market_intelligence.broker import live_tracker as lt
from agents.market_intelligence.broker import trade_stream as ts
from agents.market_intelligence.broker.skip_reasons import (
    BLOCK_MAX_POSITIONS,
    FILTER_ADV_TOO_LOW,
    INFRA_NO_BAR,
    SETUP_STOP_TOO_WIDE,
    WINDOW_DUPLICATE,
    WINDOW_OUT_OF_ORB,
    humanize,
)
from tests.conftest import make_mock_pool


# ─── 1a. _is_window_duplicate_reason — the digest filter predicate ──────────


def test_duplicate_constant_is_filtered():
    assert lt._is_window_duplicate_reason(WINDOW_DUPLICATE) is True


def test_duplicate_with_detail_suffix_is_filtered():
    # skip_reasons vocabulary allows a ": detail" suffix after the constant.
    assert lt._is_window_duplicate_reason(WINDOW_DUPLICATE + ": trade row exists") is True


@pytest.mark.parametrize("reason", [
    WINDOW_OUT_OF_ORB,          # the OTHER window: reason must survive
    SETUP_STOP_TOO_WIDE,
    SETUP_STOP_TOO_WIDE + ": ORB $1.24 vs 1.5x ATR $0.83",
    BLOCK_MAX_POSITIONS,
    INFRA_NO_BAR,
    FILTER_ADV_TOO_LOW,
])
def test_genuine_skips_are_NOT_filtered(reason):
    assert lt._is_window_duplicate_reason(reason) is False


def test_display_string_is_not_the_match_key():
    # Constant-based matching, not the humanized Telegram phrase.
    assert lt._is_window_duplicate_reason(humanize(WINDOW_DUPLICATE)) is False
    assert lt._is_window_duplicate_reason("Duplicate — trade already exists") is False


def test_none_and_non_string_reasons_are_kept():
    assert lt._is_window_duplicate_reason(None) is False
    assert lt._is_window_duplicate_reason(42) is False


# ─── 1b. ORB skip digest end-to-end (process_new_alerts_live) ────────────────


_TODAY = date(2026, 7, 15)


def _mk_alert(ticker: str) -> dict:
    return {
        "ticker": ticker, "alert_date": _TODAY, "gap_pct": 12.0,
        "rel_volume": 6.0, "ep_score": 75, "score_tier": "HIGH",
        "catalyst": "earnings", "catalyst_quality": "strong",
        "vol_percentile": 92,
    }


async def _run_orb_monitor(monkeypatch, results_by_ticker: dict[str, dict]):
    """Drive process_new_alerts_live with submit_trade_entry stubbed to return
    a canned per-ticker result. Returns (results, sent_telegrams)."""
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[_mk_alert(t) for t in results_by_ticker])
    conn.fetchrow = AsyncMock(return_value=None)   # regime lookup
    conn.fetchval = AsyncMock(return_value=False)  # no pre-existing trade rows
    monkeypatch.setattr(lt, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(lt, "LIVE_TRADING_ENABLED", True)

    import agents.market_intelligence.db as db
    monkeypatch.setattr(db, "log_audit_event", AsyncMock())
    monkeypatch.setattr(lt, "check_filters", AsyncMock(return_value=(True, None)))
    monkeypatch.setattr(lt, "compute_atr_14", AsyncMock(return_value=(1.0, 2.0)))

    async def _fake_submit(*, alert_context, **_kw):
        t = alert_context["ticker"]
        return {"ticker": t, **results_by_ticker[t]}

    monkeypatch.setattr(lt, "submit_trade_entry", _fake_submit)

    sent: list[str] = []

    async def _capture(msg, *a, **k):
        sent.append(msg)
        return True

    monkeypatch.setattr(lt, "send_telegram_message", _capture)
    results = await lt.process_new_alerts_live(today=_TODAY)
    return results, sent


@pytest.mark.asyncio
async def test_digest_drops_duplicate_keeps_genuine_skip(monkeypatch):
    results, sent = await _run_orb_monitor(monkeypatch, {
        "DUPE": {"action": lt.ACTION_SKIPPED, "reason": WINDOW_DUPLICATE},
        "REAL": {"action": lt.ACTION_SKIPPED,
                 "reason": SETUP_STOP_TOO_WIDE + ": ORB $1.24 vs 1.5x ATR $0.83"},
    })
    digests = [m for m in sent if "ORB skips" in m]
    assert len(digests) == 1, f"exactly one digest expected, got: {sent}"
    assert "REAL" in digests[0]
    assert "DUPE" not in digests[0], "WINDOW_DUPLICATE must not reach the operator digest"
    assert ", 1)" in digests[0], "digest count must reflect the FILTERED list"
    # The duplicate stays observable in the RESULTS (telemetry unbroken).
    assert any(r["ticker"] == "DUPE" for r in results)


@pytest.mark.asyncio
async def test_all_duplicates_sends_no_digest(monkeypatch):
    results, sent = await _run_orb_monitor(monkeypatch, {
        "DUP1": {"action": lt.ACTION_SKIPPED, "reason": WINDOW_DUPLICATE},
        "DUP2": {"action": lt.ACTION_SKIPPED, "reason": WINDOW_DUPLICATE},
    })
    assert not [m for m in sent if "ORB skips" in m], (
        "nothing real remained — no digest Telegram should be sent"
    )
    assert len(results) == 2  # results list itself is untouched


@pytest.mark.asyncio
async def test_other_window_reason_still_reaches_digest(monkeypatch):
    _, sent = await _run_orb_monitor(monkeypatch, {
        "LATE": {"action": lt.ACTION_SKIPPED,
                 "reason": WINDOW_OUT_OF_ORB + ": detected 10:14 ET"},
    })
    digests = [m for m in sent if "ORB skips" in m]
    assert len(digests) == 1 and "LATE" in digests[0]


# ─── 2. Stop-cancel bounded re-check (the MANE false "unprotected") ──────────


def _ws_data(order_id: str = "stop-old-1", symbol: str = "MANE"):
    return SimpleNamespace(order=SimpleNamespace(id=order_id, symbol=symbol))


async def _run_stop_cancel(monkeypatch, confirm_side_effect):
    """Drive _handle_cancel_or_reject down the stop-leg-cancel branch with
    _broker_confirm_replacement_stop stubbed. Returns (sent, confirm_mock)."""
    pool, conn = make_mock_pool()
    stop_row = {"id": 42, "ticker": "MANE", "remaining_shares": 100.0,
                "stop_price": 25.10}
    # 1st fetchrow = entry-order lookup (miss), 2nd = stop-leg lookup (hit).
    conn.fetchrow = AsyncMock(side_effect=[None, stop_row])
    conn.execute = AsyncMock()
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))

    import agents.market_intelligence.broker.order_manager as om
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock())

    confirm = AsyncMock(side_effect=confirm_side_effect)
    monkeypatch.setattr(ts, "_broker_confirm_replacement_stop", confirm)
    monkeypatch.setattr(ts, "_STOP_CANCEL_RECHECK_DELAY_S", 0)  # no real sleep in tests

    sent: list[str] = []

    async def _capture(msg, *a, **k):
        sent.append(msg)
        return True

    monkeypatch.setattr(ts, "send_telegram_message", _capture)
    await ts._handle_cancel_or_reject(_ws_data(), "canceled", "live")
    return sent, confirm


@pytest.mark.asyncio
async def test_self_heal_replace_race_suppresses_false_alarm(monkeypatch):
    """MANE 2026-07-15: first broker look finds nothing (re-place in flight),
    the re-check finds the landed stop → 'Stop replaced', NOT 'unprotected'."""
    sent, confirm = await _run_stop_cancel(
        monkeypatch, [None, {"id": "new-stop-123"}],
    )
    assert confirm.await_count == 2  # initial look + exactly one re-check
    assert any("Stop replaced" in m for m in sent)
    assert not any("unprotected" in m.lower() for m in sent)


@pytest.mark.asyncio
async def test_replacement_found_first_look_needs_no_recheck(monkeypatch):
    sent, confirm = await _run_stop_cancel(monkeypatch, [{"id": "live-stop-9"}])
    assert confirm.await_count == 1
    assert any("Stop replaced" in m for m in sent)
    assert not any("unprotected" in m.lower() for m in sent)


@pytest.mark.asyncio
async def test_persistent_no_stop_STILL_alarms(monkeypatch):
    """HARD INVARIANT (#433, do not weaken): a genuinely naked position alarms
    after the single bounded re-check — never a third look, never silence."""
    sent, confirm = await _run_stop_cancel(monkeypatch, [None, None])
    assert confirm.await_count == 2, "exactly ONE re-check — the check is bounded"
    unprotected = [m for m in sent if "unprotected" in m.lower()]
    assert len(unprotected) == 1, f"naked stop must alarm; sent={sent}"
    assert not any("Stop replaced" in m for m in sent)


@pytest.mark.asyncio
async def test_broker_confirm_read_error_returns_none_so_caller_alarms(monkeypatch):
    """Fail-safe contract of the extracted helper: broker read raising (incl.
    asyncio.TimeoutError from the 8s bound) → None → the caller alarms."""
    import agents.market_intelligence.broker.alpaca_client as alp
    monkeypatch.setattr(
        alp, "get_open_orders", AsyncMock(side_effect=RuntimeError("broker down")),
    )
    assert await ts._broker_confirm_replacement_stop("MANE", "old-1", 100.0, "live") is None

    import asyncio as _asyncio
    monkeypatch.setattr(
        alp, "get_open_orders", AsyncMock(side_effect=_asyncio.TimeoutError()),
    )
    assert await ts._broker_confirm_replacement_stop("MANE", "old-1", 100.0, "live") is None


@pytest.mark.asyncio
async def test_broker_confirm_positive_evidence_returns_replacement(monkeypatch):
    import agents.market_intelligence.broker.alpaca_client as alp
    covering_stop = {"id": "new-7", "symbol": "MANE", "side": "sell",
                     "type": "stop", "qty": 100, "filled_qty": 0,
                     "stop_price": 25.10}
    monkeypatch.setattr(alp, "get_open_orders", AsyncMock(return_value=[covering_stop]))
    r = await ts._broker_confirm_replacement_stop("MANE", "old-1", 100.0, "live")
    assert r is not None and r["id"] == "new-7"


# ─── 3. entry_order_rejected telemetry (AEHR LULD class) ─────────────────────


_AEHR_ROW = {
    "id": 7, "ticker": "AEHR", "gap_pct": 29.5, "ep_score": 71.0,
    "entry_price": 21.87, "stop_price": 19.11, "regime": "Uptrend",
    "signal_type": "magna53",
}


async def _run_entry_reject(monkeypatch, event: str = "rejected",
                            row: dict | None = None, audit: AsyncMock | None = None):
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=dict(row or _AEHR_ROW))
    conn.execute = AsyncMock()
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    audit = audit or AsyncMock()
    monkeypatch.setattr(ts, "log_audit_event", audit)
    # #500: the reason-capture diagnosis fetches the latest trade — stub it so
    # the test never touches the network (bare broker:* prefix path).
    import agents.market_intelligence.broker.order_manager as om
    monkeypatch.setattr(
        om, "alpaca", MagicMock(get_latest_trade=AsyncMock(return_value=None)),
    )

    sent: list[str] = []

    async def _capture(msg, *a, **k):
        sent.append(msg)
        return True

    monkeypatch.setattr(ts, "send_telegram_message", _capture)
    await ts._handle_cancel_or_reject(
        _ws_data(order_id="ord-aehr-0001", symbol="AEHR"), event, "live",
    )
    return sent, audit, conn


@pytest.mark.asyncio
async def test_rejection_emits_audit_event_with_context(monkeypatch):
    sent, audit, conn = await _run_entry_reject(monkeypatch, "rejected")

    calls = [c for c in audit.await_args_list if c.args[0] == ENTRY_ORDER_REJECTED]
    assert len(calls) == 1, "exactly one entry_order_rejected row per event"
    _, summary, detail = calls[0].args
    assert summary.startswith("rejected: AEHR")
    ctx = json.loads(detail)
    assert ctx["ticker"] == "AEHR"
    assert ctx["account_mode"] == "live"
    assert ctx["event_norm"] == "rejected"
    assert ctx["gap_pct"] == 29.5
    assert ctx["ep_score"] == 71.0
    assert ctx["entry_price"] == 21.87
    assert ctx["stop_price"] == 19.11
    assert ctx["regime"] == "Uptrend"
    assert ctx["signal_type"] == "magna53"
    assert ctx["trade_id"] == 7

    # The real-error Telegram is KEPT.
    assert any("Entry REJECTED" in m and "AEHR" in m for m in sent)
    # The status update (pre-existing behavior) still ran.
    assert any("cancelled" in str(c.args[0]) for c in conn.execute.await_args_list)


@pytest.mark.asyncio
async def test_unexpected_cancel_also_recorded_with_event_norm(monkeypatch):
    sent, audit, _ = await _run_entry_reject(monkeypatch, "canceled")
    calls = [c for c in audit.await_args_list if c.args[0] == ENTRY_ORDER_REJECTED]
    assert len(calls) == 1
    assert calls[0].args[1].startswith("cancelled: AEHR")
    assert json.loads(calls[0].args[2])["event_norm"] == "cancelled"
    assert any("Entry CANCELLED" in m for m in sent)


@pytest.mark.asyncio
async def test_decimal_columns_serialize_cleanly(monkeypatch):
    """asyncpg returns NUMERIC as Decimal — the float casts must keep the
    detail JSON-serializable (json.dumps raises on raw Decimal)."""
    row = dict(_AEHR_ROW, gap_pct=Decimal("29.5"), ep_score=Decimal("71"),
               entry_price=Decimal("21.87"), stop_price=Decimal("19.11"))
    _, audit, _ = await _run_entry_reject(monkeypatch, "rejected", row=row)
    calls = [c for c in audit.await_args_list if c.args[0] == ENTRY_ORDER_REJECTED]
    ctx = json.loads(calls[0].args[2])
    assert ctx["gap_pct"] == 29.5 and ctx["stop_price"] == 19.11


@pytest.mark.asyncio
async def test_telemetry_failure_never_blocks_the_rejected_telegram(monkeypatch):
    sent, _, _ = await _run_entry_reject(
        monkeypatch, "rejected", audit=AsyncMock(side_effect=RuntimeError("boom")),
    )
    assert any("Entry REJECTED" in m for m in sent), (
        "the error Telegram must fire even if the telemetry emit blows up"
    )


# ─── 4. FILLED msg is self-contained and shows the ACTUAL stop ───────────────


async def _run_entry_fill(monkeypatch, trade: dict):
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ts, "log_audit_event", AsyncMock())
    # A stop leg came back with the fill — no remediation branch.
    monkeypatch.setattr(ts.alpaca, "extract_stop_leg_id", lambda o: "stop-leg-1")

    sent: list[str] = []

    async def _capture(msg, *a, **k):
        sent.append(msg)
        return True

    monkeypatch.setattr(ts, "send_telegram_message", _capture)
    order = SimpleNamespace(id="parent-1")
    await ts._process_entry_fill(trade, order, 20.00, 100.0, pool, "live")
    return sent


def _fill_trade(**over) -> dict:
    base = {
        "id": 5, "ticker": "MANE", "entry_shares": 100, "entry_attempt": 1,
        "orb_low": 18.50, "stop_price": 19.11, "exits": [],
    }
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_filled_msg_shows_entry_shares_and_ACTUAL_stop(monkeypatch):
    """#475: FILLED is now the sole per-trade Telegram — it must carry entry
    price, shares, and the ACTUAL stop (stop_price; for 9M Day 2 that is the
    prior-day low, NOT orb_low — the KLAR 2026-05-15 divergence class)."""
    sent = await _run_entry_fill(monkeypatch, _fill_trade())
    filled = [m for m in sent if "FILLED" in m]
    assert len(filled) == 1
    assert "Entry: $20.00 x 100 shares" in filled[0]
    assert "Stop: $19.11" in filled[0], "must show stop_price (the real stop)"
    assert "$18.50" not in filled[0], "orb_low is not the stop for 9M Day 2"


@pytest.mark.asyncio
async def test_filled_msg_falls_back_to_orb_low_for_legacy_rows(monkeypatch):
    sent = await _run_entry_fill(monkeypatch, _fill_trade(stop_price=None))
    filled = [m for m in sent if "FILLED" in m]
    assert len(filled) == 1 and "Stop: $18.50" in filled[0]
