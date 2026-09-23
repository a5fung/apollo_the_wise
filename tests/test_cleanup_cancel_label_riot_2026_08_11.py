"""2026-08-11 RIOT labelling bug — operator-reported live.

Operator received `📄 PAPER 🕓 ORB window unfilled: cancelled 1 unfilled order(s) —
RIOT` for a trade `mi_live_trades` confirms was `account_mode='live'`. The cancel
ITSELF was correct (no open orders left in either book — verified in prod) — this
is a Telegram LABEL bug only. No trading logic, cancel behaviour, skip_reason, or
return value is touched by this fix; THE LINE is untouched.

Root cause: `order_manager.cancel_unfilled_entries`'s two batch cleanup callers
(scheduler.py 10:00 ET ORB-window job, scheduler.py 16:05 ET EOD job) call it with
`account_mode=None` (cancellations genuinely span both books in one run). The
Telegram digest then called bare `mode_prefix(account_mode)` i.e. `mode_prefix(None)`,
which silently falls back to `current_account_mode()` — the `ALPACA_PAPER` env
default — NOT which book the cancelled rows actually belonged to. In prod
`ALPACA_PAPER=true`, so every cleanup-cancel digest always said PAPER regardless of
the real book, which is exactly how a LIVE cancel got labelled PAPER.

Fix: `order_manager._cleanup_cancel_label(explicit_mode, touched_modes)` derives the
label from the modes of the rows ACTUALLY cancelled/failed when the caller didn't
scope a mode (explicit_mode is None) — single mode -> label it, mixed -> say so
explicitly, never guess via the global. When the caller DID scope a mode (/pause
passes account_mode="live"), the label is `mode_prefix(explicit_mode)` exactly as
before — untouched path.

Every test below uses the same opposite-value trap as test_444_moneypath_finalizer_
account_mode.py: `current_account_mode()` is monkeypatched to the OPPOSITE of the
row(s)' real account_mode, so a test that silently degraded back to the legacy
global would fail loudly instead of accidentally passing.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence.broker import order_manager as om
import agents.market_intelligence.constants as constants
from agents.market_intelligence.constants import mode_prefix

from tests.conftest import make_mock_pool


# ─── _cleanup_cancel_label — pure-function unit tests ────────────────────────
#
# Each monkeypatches current_account_mode() to the OPPOSITE of the expected
# label (the same opposite-value trap used throughout test_444_moneypath_
# finalizer_account_mode.py). Without it, a mutation that falls back to
# mode_prefix(explicit_mode)'s env-based guess can still pass "by accident"
# whenever the test environment's own ALPACA_PAPER default happens to match —
# which is exactly what happened here (env default is "paper", so the
# all-paper case coincidentally passed against a bugged fallback until this
# trap was added).


def test_cleanup_cancel_label_all_live_rows(monkeypatch):
    """None (batch-cleanup) + every touched row live -> LIVE label."""
    monkeypatch.setattr(constants, "current_account_mode", lambda: "paper")
    assert om._cleanup_cancel_label(None, {"live"}) == "💰 LIVE-$ "


def test_cleanup_cancel_label_all_paper_rows(monkeypatch):
    """None (batch-cleanup) + every touched row paper -> PAPER label."""
    monkeypatch.setattr(constants, "current_account_mode", lambda: "live")
    assert om._cleanup_cancel_label(None, {"paper"}) == "📄 PAPER "


def test_cleanup_cancel_label_mixed_rows(monkeypatch):
    """None (batch-cleanup) + touched rows span BOTH books -> explicit mixed
    wording, not a guess at either book. Assert absence of the actual
    mode_prefix() strings (not the substring "PAPER"/"LIVE-$") so a future
    reword of the MIXED copy can't accidentally still contain one of them."""
    monkeypatch.setattr(constants, "current_account_mode", lambda: "live")
    label = om._cleanup_cancel_label(None, {"live", "paper"})
    assert "MIXED" in label
    assert mode_prefix("live") not in label and mode_prefix("paper") not in label


def test_cleanup_cancel_label_empty_touched_modes_does_not_guess(monkeypatch):
    """Defensive/unreachable in practice (callers only send a message when
    `cancelled`/`failed_tickers` is non-empty, so touched_modes can't really
    be empty when this fires) — but if it ever is, the label must still not
    fall back to guessing a mode from the env."""
    monkeypatch.setattr(constants, "current_account_mode", lambda: "live")
    label = om._cleanup_cancel_label(None, set())
    assert mode_prefix("live") not in label and mode_prefix("paper") not in label


def test_cleanup_cancel_label_explicit_mode_ignores_touched_modes():
    """/pause's scoped path (explicit_mode set) must render via mode_prefix
    (explicit_mode) UNCONDITIONALLY — even if touched_modes somehow disagreed
    (defensive: the SQL WHERE guarantees every row matches explicit_mode in
    practice, but the label function itself must not second-guess it)."""
    assert om._cleanup_cancel_label("live", {"paper"}) == "💰 LIVE-$ "
    assert om._cleanup_cancel_label("paper", {"live"}) == "📄 PAPER "


# ─── cancel_unfilled_entries — end-to-end Telegram text + cancel behaviour ───


def _pending_row(id_, ticker, mode):
    return {
        "id": id_, "ticker": ticker, "entry_order_id": f"ord-{id_}",
        "alert_date": date(2026, 8, 11), "proposed_at": None,
        "entry_price": None, "stop_price": None, "entry_shares": None,
        "orb_high": None, "account_mode": mode, "pm_rvol": None,
    }


def _wire(monkeypatch, rows, *, cancel_ok=True, opposite_global="paper"):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=rows)
    conn.fetchrow = AsyncMock(return_value={"exits": [], "total_pnl": 0})
    conn.execute = AsyncMock()
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om.alpaca, "cancel_order", AsyncMock(return_value=cancel_ok))
    monkeypatch.setattr(om, "log_audit_event", AsyncMock())
    monkeypatch.setattr(om, "_update_trade_status", AsyncMock())
    # Opposite-value trap.
    monkeypatch.setattr(constants, "current_account_mode", lambda: opposite_global)

    sent = []
    async def _capture(msg, *a, **k):
        sent.append(msg)
        return True
    monkeypatch.setattr(om, "send_telegram_message", _capture)
    return sent


@pytest.mark.asyncio
async def test_all_live_rows_cleanup_digest_says_live(monkeypatch):
    """Both cleanup callers pass account_mode=None; when every cancelled row is
    live, the digest must say LIVE-$, not fall back to the paper global."""
    rows = [_pending_row(1, "RIOT", "live"), _pending_row(2, "AMD", "live")]
    sent = _wire(monkeypatch, rows, opposite_global="paper")

    n = await om.cancel_unfilled_entries(reason="ORB window unfilled")

    assert n == 2
    assert len(sent) == 1
    assert "💰 LIVE-$" in sent[0] and "📄 PAPER" not in sent[0], sent[0]
    assert "RIOT" in sent[0] and "AMD" in sent[0]


@pytest.mark.asyncio
async def test_all_paper_rows_cleanup_digest_says_paper(monkeypatch):
    """Mirror of the above: every cancelled row paper -> digest says PAPER, not
    the live global."""
    rows = [_pending_row(3, "SHOP", "paper")]
    sent = _wire(monkeypatch, rows, opposite_global="live")

    n = await om.cancel_unfilled_entries(reason="EOD unfilled")

    assert n == 1
    assert len(sent) == 1
    assert "📄 PAPER" in sent[0] and "💰 LIVE-$" not in sent[0], sent[0]


@pytest.mark.asyncio
async def test_mixed_rows_cleanup_digest_says_mixed(monkeypatch):
    """A single cleanup run cancelling BOTH a live and a paper resting entry must
    say so explicitly, not pick one book and mislabel the other trade — this is
    the actual RIOT bug shape (one real order, wrong single label)."""
    rows = [_pending_row(4, "RIOT", "live"), _pending_row(5, "SOXL", "paper")]
    sent = _wire(monkeypatch, rows, opposite_global="paper")

    n = await om.cancel_unfilled_entries(reason="ORB window unfilled")

    assert n == 2
    assert len(sent) == 1
    assert "MIXED" in sent[0]
    assert "RIOT" in sent[0] and "SOXL" in sent[0]


@pytest.mark.asyncio
async def test_cancel_failed_digest_labels_by_failed_rows_not_global(monkeypatch):
    """The sibling 'cancel FAILED' message must use the same derivation — an
    operator dismissing a 'PAPER' cancel-failure that was really live is the
    dangerous version of this bug (a resting real-money order stays live,
    unflagged)."""
    rows = [_pending_row(6, "RIOT", "live")]
    sent = _wire(monkeypatch, rows, cancel_ok=False, opposite_global="paper")

    n = await om.cancel_unfilled_entries(reason="ORB window unfilled")

    assert n == 0
    assert len(sent) == 1
    assert "FAILED" in sent[0]
    assert "💰 LIVE-$" in sent[0] and "📄 PAPER" not in sent[0], sent[0]


@pytest.mark.asyncio
async def test_pause_scoped_path_unchanged_even_with_stale_row_mode(monkeypatch):
    """/pause passes account_mode="live" explicitly — the label must come from
    THAT param, not from touched_modes, even in a defensive edge case where a
    row's own account_mode disagrees (should never happen given the SQL WHERE,
    but the label function must not second-guess the caller's explicit scope)."""
    rows = [_pending_row(7, "PAUSED1", "paper")]  # deliberately disagrees
    sent = _wire(monkeypatch, rows, opposite_global="paper")

    n = await om.cancel_unfilled_entries(reason="manual /pause", account_mode="live")

    assert n == 1
    assert len(sent) == 1
    assert "💰 LIVE-$" in sent[0] and "📄 PAPER" not in sent[0], sent[0]
