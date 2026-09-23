"""Operator 7/8 — EP alerts + EOD digest must reflect the OWNING strategy's account,
not the legacy paper default. MAGNA53 is live real-money; its signals were rendering
PAPER and the EOD 'Live Trade Update' reported only the (dormant, historical) paper book.

Pins:
  1. `_insert_skipped_trade` writes the passed account_mode (skip rows attribute to live).
  2. `send_live_trade_summary` renders LIVE as the primary block (💰 LIVE-$ / "Alpaca — Live").
  3. The folded PAPER block only appears when paper is ACTIVE that day (not for the dormant
     historical cumulative) — nothing is phase='paper' today, so it stays silent.

#479 (2026-07-17): the routine summary is routed to close_digest.contribute("BOOK", ...)
instead of a direct Telegram — the render pins are unchanged, asserted on the
contributed text; a direct send is now a regression.
"""
import sys
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.conftest import make_mock_pool
import agents.market_intelligence.broker.live_tracker as lt
import agents.market_intelligence.close_digest as close_digest
import agents.market_intelligence.constants as constants


def _stats(total, winners, losers, pnl):
    return {"total": total, "winners": winners, "losers": losers, "realized_pnl": pnl}


class _Strat:
    def __init__(self, phase):
        self.phase = phase


def test_get_strategy_account_mode_phase_guard(monkeypatch):
    # The shared resolver the EP-scan + entry-pipeline skip sites delegate to (reuse dedup).
    # paper/live resolve directly; shadow/deprecated/None fall back to the global mode (no raise).
    monkeypatch.setattr(constants, "current_account_mode", lambda: "paper")
    assert constants.get_strategy_account_mode(_Strat("live")) == "live"
    assert constants.get_strategy_account_mode(_Strat("paper")) == "paper"
    assert constants.get_strategy_account_mode(_Strat("shadow")) == "paper"      # fallback, no raise
    assert constants.get_strategy_account_mode(_Strat("deprecated")) == "paper"  # fallback, no raise
    assert constants.get_strategy_account_mode(None) == "paper"                  # None → fallback


@pytest.mark.asyncio
async def test_insert_skipped_trade_uses_passed_account_mode(monkeypatch):
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    monkeypatch.setattr(lt, "get_pool", AsyncMock(return_value=pool))
    await lt._insert_skipped_trade(
        "PENG", date(2026, 7, 8), None, None,
        "window:out_of_orb: detected 09:55 ET",
        signal_type="magna53", account_mode="live",
    )
    # account_mode is the last positional arg of the INSERT
    assert conn.execute.await_args.args[-1] == "live"


@pytest.mark.asyncio
async def test_insert_skipped_trade_defaults_to_current_mode(monkeypatch):
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    monkeypatch.setattr(lt, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(constants, "current_account_mode", lambda: "paper")
    await lt._insert_skipped_trade("XYZ", date(2026, 7, 8), None, None, "r", signal_type="magna53")
    assert conn.execute.await_args.args[-1] == "paper"  # legacy fallback preserved


def _wire_summary(monkeypatch, *, paper, live):
    """Wire get_pool/alpaca/telegram/et_today. `paper`/`live` are dicts of the 5 slices.
    Returns (sent, contribs): direct Telegram sends (must stay empty since #479)
    and close-digest contributions [(section, text), ...]."""
    pool, conn = make_mock_pool()
    # gather order: for m in ['paper','live'] → fetchrow(stats) then fetch(open,closes,entries,skipped)
    conn.fetchrow = AsyncMock(side_effect=[paper["stats"], live["stats"]])
    conn.fetch = AsyncMock(side_effect=[
        paper["open"], paper["closes"], paper["entries"], paper["skipped"],
        live["open"], live["closes"], live["entries"], live["skipped"],
    ])
    monkeypatch.setattr(lt, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(lt, "et_today", lambda: date(2026, 7, 8))
    monkeypatch.setattr(constants, "active_account_modes", lambda: ["paper", "live"])
    monkeypatch.setattr(lt.alpaca, "get_account", AsyncMock(return_value={"equity": 89846.0}))
    monkeypatch.setattr(lt.alpaca, "get_position", AsyncMock(return_value=None))
    sent = []
    monkeypatch.setattr(lt, "send_telegram_message", AsyncMock(side_effect=lambda m, *a, **k: sent.append(m)))
    contribs = []
    monkeypatch.setattr(close_digest, "contribute",
                        lambda section, text: contribs.append((section, text)))
    return sent, contribs


@pytest.mark.asyncio
async def test_summary_live_primary_paper_hidden_when_dormant(monkeypatch):
    # Live filtered PENG today; paper only has a HISTORICAL cumulative (dormant today).
    paper = {"stats": _stats(34, 10, 24, -10669.59),
             "open": [], "closes": [], "entries": [], "skipped": []}
    live = {"stats": _stats(1, 0, 1, -32.80), "open": [], "closes": [], "entries": [],
            "skipped": [{"ticker": "PENG", "skip_reason": "window:out_of_orb: detected 09:55 ET"}]}
    sent, contribs = _wire_summary(monkeypatch, paper=paper, live=live)
    await lt.send_live_trade_summary()

    assert sent == []                                      # #479: no direct Telegram
    assert len(contribs) == 1 and contribs[0][0] == "BOOK"
    msg = contribs[0][1]
    assert "💰 LIVE-$" in msg and "Alpaca — Live" in msg   # live is the primary block
    assert "PENG" in msg and "Filtered today" in msg       # the live skip surfaces here
    assert "Paper (shadow book)" not in msg                # dormant paper stays hidden
    assert "0W/1L" in msg                                   # live record, not the paper 10W/24L


@pytest.mark.asyncio
async def test_summary_folds_paper_when_active(monkeypatch):
    # Paper traded today (an entry) → the folded paper block appears alongside live-primary.
    paper = {"stats": _stats(35, 10, 24, -10669.59), "open": [], "closes": [],
             "entries": [{"ticker": "SHDW", "entry_price": 10.0, "entry_shares": 100}],
             "skipped": []}
    live = {"stats": _stats(1, 0, 1, -32.80),
            "open": [], "closes": [], "entries": [], "skipped": []}
    sent, contribs = _wire_summary(monkeypatch, paper=paper, live=live)
    await lt.send_live_trade_summary()

    assert sent == []                                      # #479: no direct Telegram
    assert len(contribs) == 1 and contribs[0][0] == "BOOK"
    msg = contribs[0][1]
    assert "Alpaca — Live" in msg                           # still live-primary
    assert "Paper (shadow book)" in msg                     # folded block now present
    assert "1 entered" in msg                               # paper's today activity, compact


# ── #444 follow-up: broker/bar_stream.py subscribe-failure labeling ────────
# The per-ticker ORB subscribe-failure alert (bar_stream._record_subscribe_failure)
# now accepts the caller's resolved account_mode instead of always reading the
# legacy paper-default global — mirrors the #443 pattern for a lower-traffic site.

import agents.market_intelligence.broker.bar_stream as bar_stream
import agents.market_intelligence.briefing as briefing_mod
import agents.market_intelligence.db as db_mod
from agents.market_intelligence.broker.skip_reasons import INFRA_SUBSCRIBE_FAILED


@pytest.mark.asyncio
async def test_record_subscribe_failure_labels_with_passed_account_mode(monkeypatch):
    sent = []
    monkeypatch.setattr(briefing_mod, "send_telegram_message",
                        AsyncMock(side_effect=lambda m, *a, **k: sent.append(m)))
    monkeypatch.setattr(db_mod, "log_audit_event", AsyncMock())

    await bar_stream._record_subscribe_failure(
        "ABCD", f"{INFRA_SUBSCRIBE_FAILED}: boom", account_mode="live",
    )

    assert len(sent) == 1
    assert "💰 LIVE-$" in sent[0]
    assert "📄 PAPER" not in sent[0]


@pytest.mark.asyncio
async def test_record_subscribe_failure_defaults_without_account_mode(monkeypatch):
    sent = []
    monkeypatch.setattr(briefing_mod, "send_telegram_message",
                        AsyncMock(side_effect=lambda m, *a, **k: sent.append(m)))
    monkeypatch.setattr(db_mod, "log_audit_event", AsyncMock())
    monkeypatch.setattr(constants, "current_account_mode", lambda: "paper")

    await bar_stream._record_subscribe_failure("ABCD", f"{INFRA_SUBSCRIBE_FAILED}: boom")

    assert len(sent) == 1
    assert "📄 PAPER" in sent[0]  # legacy fallback preserved for callers with no strategy context


@pytest.mark.asyncio
async def test_subscribe_ep_candidate_threads_account_mode_into_failure(monkeypatch):
    """subscribe_ep_candidate (called from _ep_scan_job pre-market) must forward
    the caller's account_mode into _record_subscribe_failure on a subscribe error —
    the label should attribute to the owning strategy, not the legacy default."""
    bar_stream.reset_daily_state()

    class _FakeStream:
        def subscribe_bars(self, *a, **k):
            raise RuntimeError("SDK boom")

    monkeypatch.setattr(bar_stream, "_data_stream", _FakeStream())
    fail_calls = []

    async def _fake_failure(ticker, reason, account_mode=None):
        fail_calls.append((ticker, reason, account_mode))

    monkeypatch.setattr(bar_stream, "_record_subscribe_failure", _fake_failure)

    await bar_stream.subscribe_ep_candidate("ABCD", account_mode="live")

    assert len(fail_calls) == 1
    assert fail_calls[0][0] == "ABCD"
    assert fail_calls[0][2] == "live"
    bar_stream.reset_daily_state()
