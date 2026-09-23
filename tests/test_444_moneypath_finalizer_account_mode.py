"""#444 — money-path finalizer account_mode threading (operator-authorized 2026-07-27).

Scope: `order_manager.py` fill/exit finalizers, `entry_pipeline.py`'s CAP+1 alert, and
`live_tracker.py`'s ORB-monitor digest — every site was a bare `mode_prefix()` (or a
Alpaca-account default) that silently fell back to the legacy env-based
`current_account_mode()` global instead of the ACTUAL trade/strategy's account_mode.
Label-only fixes (Telegram prefix text) — no trading logic, threshold, sizing, or
safeguard changed; THE LINE untouched.

Every test below monkeypatches `current_account_mode()` to the OPPOSITE of the trade's
real `account_mode` — this is load-bearing: without the opposite-value monkeypatch, a
test would pass on the pre-fix bare-`mode_prefix()` code too (paper is usually both the
row's mode AND the legacy default), silently proving nothing. Each assertion here was
checked to FAIL against the code it targets (see comments per test) — for most tests
that's the pre-#444 bare `mode_prefix()`; the `cancel_unfilled_entries` None-mode test
(2026-08-11) instead targets the post-#444/pre-2026-08-11 code, which had the SAME
env-fallback bug for the batch-cleanup path (see order_manager._cleanup_cancel_label).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker import entry_pipeline as ep
from agents.market_intelligence.broker import live_tracker as lt
from agents.market_intelligence.broker.skip_reasons import BLOCK_MAX_POSITIONS
import agents.market_intelligence.constants as constants

from tests.conftest import make_mock_pool


@asynccontextmanager
async def _noop_lock(_tid):
    yield


# ─── order_manager finalizers: FILLED / partial / full / stop-fill ──────────


@pytest.mark.asyncio
async def test_check_fills_filled_alert_uses_trade_account_mode(monkeypatch):
    """check_fills' FILLED Telegram must label the TRADE's own account_mode
    (from the SELECT), not the legacy global — pre-fix this was a bare
    mode_prefix() call (order_manager.py:692)."""
    pool, conn = make_mock_pool()
    trade_row = {
        "id": 1, "ticker": "LIVE1", "entry_order_id": "ord-1",
        "entry_shares": 100, "orb_low": 9.0, "orb_high": 10.0,
        "stop_price": 9.5, "entry_attempt": 1, "account_mode": "live",
    }
    # check_fills() also calls _check_day1_reentry() at the tail, which issues
    # its OWN conn.fetch — side_effect covers both in call order (pending
    # entries, then the day-1-reentry query, empty so it no-ops).
    conn.fetch = AsyncMock(side_effect=[[trade_row], []])
    conn.execute = AsyncMock(return_value="UPDATE 1")
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om.alpaca, "get_order", AsyncMock(return_value={
        "status": "filled", "filled_avg_price": 10.5, "filled_qty": 100,
    }))
    monkeypatch.setattr(om.alpaca, "extract_stop_leg_id", lambda o: "stop-1")
    # Opposite-value trap: global default is "paper" while the row is "live".
    monkeypatch.setattr(constants, "current_account_mode", lambda: "paper")

    sent = []
    async def _capture(msg, *a, **k):
        sent.append(msg)
        return True
    monkeypatch.setattr(om, "send_telegram_message", _capture)

    results = await om.check_fills()

    assert results and results[0]["action"] == "filled"
    assert len(sent) == 1
    assert "💰 LIVE-$" in sent[0] and "📄 PAPER" not in sent[0], (
        f"FILLED alert did not attribute to the trade's own (live) account_mode: {sent[0]}"
    )


@pytest.mark.asyncio
async def test_finalize_partial_exit_uses_trade_account_mode(monkeypatch):
    """_finalize_partial_exit_locked's Telegram must label the trade's
    account_mode — pre-fix, bare mode_prefix() (order_manager.py:2270)."""
    pool, conn = make_mock_pool()
    trade_row = {
        "id": 5, "ticker": "LIVE2", "exits": [], "entry_price": 10.0,
        "remaining_shares": 100, "account_mode": "live",
    }
    conn.fetchrow = AsyncMock(return_value=trade_row)
    conn.execute = AsyncMock()
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om, "log_audit_event", AsyncMock())
    monkeypatch.setattr(om, "_trade_advisory_lock", _noop_lock)
    monkeypatch.setattr(constants, "current_account_mode", lambda: "paper")

    sent = []
    async def _capture(msg, *a, **k):
        sent.append(msg)
        return True
    monkeypatch.setattr(om, "send_telegram_message", _capture)

    await om.finalize_partial_exit(
        trade_id=5, filled_qty=40, filled_price=11.0, order_id="order-xyz",
    )

    assert len(sent) == 1
    assert "💰 LIVE-$" in sent[0] and "📄 PAPER" not in sent[0], (
        f"Partial-exit FILLED alert did not attribute to the trade's own (live) "
        f"account_mode: {sent[0]}"
    )


@pytest.mark.asyncio
async def test_finalize_full_exit_uses_trade_account_mode(monkeypatch):
    """_finalize_full_exit_locked's Telegram must label the trade's
    account_mode — pre-fix, bare mode_prefix() (order_manager.py:2426)."""
    pool, conn = make_mock_pool()
    trade_row = {
        "id": 1, "ticker": "LIVE3", "exits": [], "entry_price": 100.0,
        "account_mode": "live",
    }
    conn.fetchrow = AsyncMock(return_value=trade_row)
    conn.execute = AsyncMock()
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om, "log_audit_event", AsyncMock())
    monkeypatch.setattr(om, "_trade_advisory_lock", _noop_lock)
    monkeypatch.setattr(constants, "current_account_mode", lambda: "paper")

    sent = []
    async def _capture(msg, *a, **k):
        sent.append(msg)
        return True
    monkeypatch.setattr(om, "send_telegram_message", _capture)

    await om.finalize_full_exit(
        trade_id=1, filled_qty=100, filled_price=110.0,
        order_id="order-abc", reason="sma_trail_stop",
    )

    assert len(sent) == 1
    assert "💰 LIVE-$" in sent[0] and "📄 PAPER" not in sent[0], (
        f"Full-exit Closed alert did not attribute to the trade's own (live) "
        f"account_mode: {sent[0]}"
    )


@pytest.mark.asyncio
async def test_finalize_stop_fill_uses_trade_account_mode(monkeypatch):
    """_finalize_stop_fill_locked's Telegram must label the trade's
    account_mode — pre-fix, bare mode_prefix() (order_manager.py:2515)."""
    pool, conn = make_mock_pool()
    trade_row = {
        "id": 9, "ticker": "LIVE4", "exits": [], "entry_price": 50.0,
        "entry_attempt": 1, "account_mode": "live",
    }
    conn.fetchrow = AsyncMock(return_value=trade_row)
    conn.execute = AsyncMock()
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om, "log_audit_event", AsyncMock())
    monkeypatch.setattr(om, "_trade_advisory_lock", _noop_lock)
    monkeypatch.setattr(constants, "current_account_mode", lambda: "paper")

    sent = []
    async def _capture(msg, *a, **k):
        sent.append(msg)
        return True
    monkeypatch.setattr(om, "send_telegram_message", _capture)

    await om.finalize_stop_fill(
        trade_id=9, filled_qty=50, filled_price=48.0, order_id="order-stop",
    )

    assert len(sent) == 1
    assert "💰 LIVE-$" in sent[0] and "📄 PAPER" not in sent[0], (
        f"Stop-fill alert did not attribute to the trade's own (live) account_mode: {sent[0]}"
    )


# ─── order_manager.cancel_unfilled_entries — the function's OWN `account_mode` param ──


@pytest.mark.asyncio
async def test_cancel_unfilled_entries_threads_the_passed_mode(monkeypatch):
    """/pause passes account_mode="live" — every cancelled row IS that mode, so
    the digest should now say LIVE-$ instead of falling back to the legacy
    global. Pre-fix: bare mode_prefix() (order_manager.py:2739)."""
    pool, conn = make_mock_pool()
    pending_row = {
        "id": 3, "ticker": "PAUSED1", "entry_order_id": "ord-3",
        "alert_date": date(2026, 7, 27), "proposed_at": None,
        "entry_price": None, "stop_price": None, "entry_shares": None,
        "orb_high": None, "account_mode": "live", "pm_rvol": None,
    }
    conn.fetch = AsyncMock(return_value=[pending_row])
    conn.fetchrow = AsyncMock(return_value={"exits": [], "total_pnl": 0})
    conn.execute = AsyncMock()
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om.alpaca, "cancel_order", AsyncMock(return_value=True))
    monkeypatch.setattr(om, "log_audit_event", AsyncMock())
    monkeypatch.setattr(om, "_update_trade_status", AsyncMock())
    # Opposite-value trap: global default is "paper" while /pause passed "live".
    monkeypatch.setattr(constants, "current_account_mode", lambda: "paper")

    sent = []
    async def _capture(msg, *a, **k):
        sent.append(msg)
        return True
    monkeypatch.setattr(om, "send_telegram_message", _capture)

    n = await om.cancel_unfilled_entries(reason="manual /pause", account_mode="live")

    assert n == 1
    assert len(sent) == 1
    assert "💰 LIVE-$" in sent[0] and "📄 PAPER" not in sent[0], (
        f"/pause cancellation digest did not attribute to the passed (live) "
        f"account_mode: {sent[0]}"
    )


@pytest.mark.asyncio
async def test_cancel_unfilled_entries_none_mode_labels_from_actual_row_not_global(monkeypatch):
    """SUPERSEDES the old byte-identical assertion (2026-08-11, RIOT mislabel fix,
    docs/setups CHANGE_PROCESS not applicable — labelling-only, no strategy/sizing/
    safeguard touched). The batch cleanup paths (10:00 ET / 4:05 PM) pass
    account_mode=None because cancellations genuinely span both books — but the
    PRE-fix code then called bare `mode_prefix(None)`, which silently falls back to
    `current_account_mode()` (the env-var global), NOT the mode of the row actually
    cancelled. That is exactly the operator-reported bug: a LIVE order's cleanup-
    cancel was labelled PAPER because the container default is paper.

    Opposite-value trap here: the row is "paper" while current_account_mode() is
    mocked to "live" — the OLD code would have said LIVE-$ (this exact assertion,
    inverted, was the pre-fix test — see git history). Post-fix it must say PAPER,
    matching the row, not the global."""
    pool, conn = make_mock_pool()
    pending_row = {
        "id": 4, "ticker": "EOD1", "entry_order_id": "ord-4",
        "alert_date": date(2026, 7, 27), "proposed_at": None,
        "entry_price": None, "stop_price": None, "entry_shares": None,
        "orb_high": None, "account_mode": "paper", "pm_rvol": None,
    }
    conn.fetch = AsyncMock(return_value=[pending_row])
    conn.fetchrow = AsyncMock(return_value={"exits": [], "total_pnl": 0})
    conn.execute = AsyncMock()
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om.alpaca, "cancel_order", AsyncMock(return_value=True))
    monkeypatch.setattr(om, "log_audit_event", AsyncMock())
    monkeypatch.setattr(om, "_update_trade_status", AsyncMock())
    monkeypatch.setattr(constants, "current_account_mode", lambda: "live")

    sent = []
    async def _capture(msg, *a, **k):
        sent.append(msg)
        return True
    monkeypatch.setattr(om, "send_telegram_message", _capture)

    n = await om.cancel_unfilled_entries(reason="EOD unfilled")  # account_mode=None (default)

    assert n == 1
    assert len(sent) == 1
    # Row is "paper" -> label must be PAPER even though the mocked global says "live".
    assert "📄 PAPER" in sent[0] and "💰 LIVE-$" not in sent[0], (
        f"cleanup-cancel digest used the global default instead of the actual "
        f"cancelled row's account_mode: {sent[0]}"
    )


# ─── entry_pipeline._skip — CAP+1 CANDIDATE alert ────────────────────────────


def _wire_cap_plus_one(monkeypatch, *, strategy_mode_raises: bool = False):
    """Drive submit_trade_entry straight to a BLOCK_MAX_POSITIONS + game_changer
    skip (the #197 CAP+1 path) with minimal DB/registry mocking. Returns `sent`."""
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(side_effect=[False, None])  # 1: not exists, 1b: not open
    monkeypatch.setattr(ep, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ep, "log_audit_event", AsyncMock())
    monkeypatch.setattr(constants, "current_account_mode", lambda: "paper")

    strategy = SimpleNamespace(
        enabled=True, phase="live", live_real_enabled=True,
        position_size_multiplier=1.0, strategy_id="magna53",
    )
    import agents.market_intelligence.strategies.registry as registry
    monkeypatch.setattr(registry, "get_strategy", AsyncMock(return_value=strategy))
    monkeypatch.setattr(
        lt, "_check_safeguards",
        AsyncMock(return_value=(False, f"{BLOCK_MAX_POSITIONS}: 5/5 (mode=live)", 0.0)),
    )
    monkeypatch.setattr(lt, "_insert_skipped_trade", AsyncMock())

    if strategy_mode_raises:
        monkeypatch.setattr(
            ep, "get_strategy_account_mode",
            lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("resolver boom")),
        )

    sent = []
    async def _capture(msg, *a, **k):
        sent.append(msg)
        return True
    monkeypatch.setattr(ep, "send_telegram_message", _capture)
    return sent


async def _spec_builder(alert_ctx, orb_bar, regime, account_mode):
    return ({}, None)  # never reached — _check_safeguards blocks first


@pytest.mark.asyncio
async def test_cap_plus_one_alert_uses_resolved_strategy_mode(monkeypatch):
    """CAP+1 CANDIDATE alert must label the OWNING strategy's account_mode
    (magna53 -> live here), not the legacy global. Pre-fix: bare mode_prefix()
    (entry_pipeline.py:313)."""
    sent = _wire_cap_plus_one(monkeypatch)

    result = await ep.submit_trade_entry(
        alert_context={"ticker": "GC1", "ep_score": 80,
                       "catalyst_quality": "game_changer", "gap_pct": 12.0},
        spec_builder=_spec_builder,
        regime_record=None,
        strategy_label="ORB",
        signal_type="magna53",
        today=date(2026, 7, 27),
        atr_14=1.0,
    )

    assert result["action"] == ep.ACTION_BLOCKED
    cap_msgs = [m for m in sent if "CAP+1 CANDIDATE" in m]
    assert len(cap_msgs) == 1, f"expected exactly one CAP+1 alert, got {sent}"
    assert "💰 LIVE-$" in cap_msgs[0] and "📄 PAPER" not in cap_msgs[0], (
        f"CAP+1 alert did not attribute to magna53's resolved (live) account_mode: {cap_msgs[0]}"
    )


@pytest.mark.asyncio
async def test_cap_plus_one_alert_survives_mode_resolve_failure(monkeypatch):
    """#444 hardening: `_skip_mode` is bound to None BEFORE the try block, so a
    resolver failure degrades the CAP+1 alert to the legacy-global label instead
    of being silently swallowed by the CAP+1 try/except (which would DROP the
    alert entirely on pre-fix code, since `_skip_mode` would be referenced
    unbound at the mode_prefix() call)."""
    sent = _wire_cap_plus_one(monkeypatch, strategy_mode_raises=True)

    result = await ep.submit_trade_entry(
        alert_context={"ticker": "GC2", "ep_score": 80,
                       "catalyst_quality": "game_changer", "gap_pct": 12.0},
        spec_builder=_spec_builder,
        regime_record=None,
        strategy_label="ORB",
        signal_type="magna53",
        today=date(2026, 7, 27),
        atr_14=1.0,
    )

    assert result["action"] == ep.ACTION_BLOCKED
    cap_msgs = [m for m in sent if "CAP+1 CANDIDATE" in m]
    assert len(cap_msgs) == 1, (
        "CAP+1 alert was DROPPED when strategy-mode resolution failed — "
        f"_skip_mode must default to None, not stay unbound. sent={sent}"
    )
    # Legacy-global fallback (mode_prefix(None) == mode_prefix()) — "paper" here.
    assert "📄 PAPER" in cap_msgs[0]


# ─── live_tracker.process_new_alerts_live — crash + skip digest ─────────────


_TODAY = date(2026, 7, 27)


def _mk_alert(ticker: str) -> dict:
    return {
        "ticker": ticker, "alert_date": _TODAY, "gap_pct": 12.0,
        "rel_volume": 6.0, "ep_score": 75, "score_tier": "HIGH",
        "catalyst": "earnings", "catalyst_quality": "strong",
        "vol_percentile": 92,
    }


def _wire_orb_monitor(monkeypatch, *, magna53_mode):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[_mk_alert("ABCD")])
    conn.fetchrow = AsyncMock(return_value=None)   # regime lookup
    conn.fetchval = AsyncMock(return_value=False)  # no pre-existing trade row
    monkeypatch.setattr(lt, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(lt, "LIVE_TRADING_ENABLED", True)

    import agents.market_intelligence.db as db
    monkeypatch.setattr(db, "log_audit_event", AsyncMock())
    monkeypatch.setattr(lt, "resolve_strategy_mode_nonfatal", AsyncMock(return_value=magna53_mode))
    # Opposite-value trap: global default is "paper" while magna53 resolves live.
    monkeypatch.setattr(constants, "current_account_mode", lambda: "paper")

    sent = []
    async def _capture(msg, *a, **k):
        sent.append(msg)
        return True
    monkeypatch.setattr(lt, "send_telegram_message", _capture)
    return sent


@pytest.mark.asyncio
async def test_orb_crash_digest_uses_resolved_magna53_mode(monkeypatch):
    """The per-alert crash alert must label magna53's resolved account_mode —
    pre-fix: bare mode_prefix() (live_tracker.py:441)."""
    sent = _wire_orb_monitor(monkeypatch, magna53_mode="live")
    monkeypatch.setattr(lt, "check_filters", AsyncMock(side_effect=RuntimeError("boom")))

    await lt.process_new_alerts_live(today=_TODAY)

    crash_msgs = [m for m in sent if "ORB pipeline crashed" in m]
    assert len(crash_msgs) == 1, f"expected one crash alert, got {sent}"
    assert "💰 LIVE-$" in crash_msgs[0] and "📄 PAPER" not in crash_msgs[0], (
        f"ORB crash alert did not attribute to magna53's resolved (live) account_mode: "
        f"{crash_msgs[0]}"
    )


@pytest.mark.asyncio
async def test_orb_skip_digest_uses_resolved_magna53_mode(monkeypatch):
    """The grouped skip digest must label magna53's resolved account_mode —
    pre-fix: bare mode_prefix() (live_tracker.py:474)."""
    sent = _wire_orb_monitor(monkeypatch, magna53_mode="live")
    monkeypatch.setattr(lt, "check_filters", AsyncMock(return_value=(False, "filter:test_reason")))
    monkeypatch.setattr(lt, "_insert_skipped_trade", AsyncMock())

    await lt.process_new_alerts_live(today=_TODAY)

    skip_msgs = [m for m in sent if "ORB skips" in m]
    assert len(skip_msgs) == 1, f"expected one skip digest, got {sent}"
    assert "💰 LIVE-$" in skip_msgs[0] and "📄 PAPER" not in skip_msgs[0], (
        f"ORB skip digest did not attribute to magna53's resolved (live) account_mode: "
        f"{skip_msgs[0]}"
    )


@pytest.mark.asyncio
async def test_orb_skip_digest_falls_back_when_resolve_fails(monkeypatch):
    """resolve_strategy_mode_nonfatal is fail-open (returns None on error) — the
    digest must degrade to the exact legacy behavior (mode_prefix(None) ==
    mode_prefix()), never raise or drop the digest."""
    sent = _wire_orb_monitor(monkeypatch, magna53_mode=None)
    monkeypatch.setattr(lt, "check_filters", AsyncMock(return_value=(False, "filter:test_reason")))
    monkeypatch.setattr(lt, "_insert_skipped_trade", AsyncMock())

    await lt.process_new_alerts_live(today=_TODAY)

    skip_msgs = [m for m in sent if "ORB skips" in m]
    assert len(skip_msgs) == 1
    assert "📄 PAPER" in skip_msgs[0]  # legacy fallback ("paper" global) preserved
