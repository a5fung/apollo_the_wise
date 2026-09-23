"""#479 half-1 — Market Close Digest (16:55 ET consolidated post-close message).

Pins the contribution-buffer contract in close_digest.py:
  1. contribute + flush renders the mock's shape (docs/analysis/
     479_telegram_noise_proposal_2026-07-17.md §2): ONE monospace ``` block,
     sections ordered BOOK/EP/9M/JUDGE/SIGNALS (extras after), EMPTY sections
     OMITTED, markdown decoration stripped inside the fence, one
     market_close_digest_sent audit row listing the included sections.
  2. Empty buffer → nothing sent, no audit row.
  3. flush clears the buffer (a second flush sends nothing).
  4. A folded job (9m_pace_digest) CONTRIBUTES instead of Telegramming.
"""
# Alpaca SDK + backtester stubbing handled by tests/conftest.py.
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.conftest import make_mock_pool
import agents.market_intelligence.briefing as briefing_mod
import agents.market_intelligence.close_digest as close_digest
import agents.market_intelligence.db as db_mod


@pytest.fixture(autouse=True)
def _fresh_buffer():
    close_digest.clear()
    close_digest._buffer_date = None
    yield
    close_digest.clear()
    close_digest._buffer_date = None


def _wire_flush(monkeypatch):
    """Capture the Telegram send + audit row the flush emits."""
    sent = []
    monkeypatch.setattr(briefing_mod, "send_telegram_message",
                        AsyncMock(side_effect=lambda m, *a, **k: sent.append(m) or True))
    audits = []
    monkeypatch.setattr(db_mod, "log_audit_event",
                        AsyncMock(side_effect=lambda *a, **k: audits.append(a)))
    return sent, audits


# ── 1. contribute + flush renders the mock shape ─────────────────────────────

@pytest.mark.asyncio
async def test_flush_renders_mock_shape(monkeypatch):
    sent, audits = _wire_flush(monkeypatch)

    # Contribute OUT of render order (jobs fire 16:00→16:45, SIGNALS first) +
    # an unknown section (NEWS renders after the canonical five). 9M and JUDGE
    # deliberately absent — empty sections must be OMITTED (quiet-day rule;
    # deprecated strategies contribute nothing so they get NO line).
    close_digest.contribute("SIGNALS", "📋 *Stocks-in-Play* (2): `AAPL`, NVDA")
    close_digest.contribute("EP", "📊 *EP EOD Recap — 2026-07-17*\nHIGH: 1 detected")
    close_digest.contribute("BOOK", "💰 LIVE-$ 📊 *Live Trade Update*\n_2 open_ · infra:subscribe_timeout")
    close_digest.contribute("NEWS", "🗞 *News drift*: none material")

    n = await close_digest.flush_and_send()
    assert n == 4
    assert len(sent) == 1                                   # ONE message
    msg = sent[0]

    # Monospace block wrapping the whole digest; header inside the fence.
    assert msg.startswith("```\n🔔 CLOSE — ") and msg.endswith("\n```")

    # Section order: BOOK → EP → SIGNALS → NEWS; 9M/JUDGE omitted entirely.
    body = msg[3:-3]
    assert body.index("\nBOOK\n") < body.index("\nEP\n") < body.index("\nSIGNALS\n") < body.index("\nNEWS\n")
    assert "\n9M\n" not in body and "\nJUDGE\n" not in body

    # Markdown V1 decoration stripped inside the fence (the fence's own
    # backticks are the ONLY backticks); snake_case machine tokens survive.
    assert "*" not in msg and "_" not in body.replace("subscribe_timeout", "")
    assert msg.count("`") == 6
    assert "infra:subscribe_timeout" in body
    assert "AAPL" in body and "Live Trade Update" in body

    # One market_close_digest_sent audit row, detail JSON lists the sections.
    assert len(audits) == 1
    event_type, summary, detail = audits[0]
    assert event_type == "market_close_digest_sent"
    d = json.loads(detail)
    assert d["sections"] == ["BOOK", "EP", "SIGNALS", "NEWS"]
    assert d["contributions"] == 4 and d["sent"] is True


# ── 2. empty buffer sends nothing ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_buffer_sends_nothing(monkeypatch):
    sent, audits = _wire_flush(monkeypatch)
    assert await close_digest.flush_and_send() == 0
    assert sent == [] and audits == []


@pytest.mark.asyncio
async def test_blank_contribution_ignored(monkeypatch):
    sent, audits = _wire_flush(monkeypatch)
    close_digest.contribute("EP", "   \n ")
    assert await close_digest.flush_and_send() == 0
    assert sent == []


# ── 3. flush clears the buffer ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_flush_clears_buffer(monkeypatch):
    sent, _ = _wire_flush(monkeypatch)
    close_digest.contribute("EP", "recap text")
    assert await close_digest.flush_and_send() == 1
    assert close_digest._buffer == {}
    assert await close_digest.flush_and_send() == 0         # second flush: nothing
    assert len(sent) == 1


# ── 4. a swapped job contributes instead of sending ──────────────────────────

@pytest.mark.asyncio
async def test_9m_pace_job_contributes_instead_of_sending(monkeypatch):
    import agents.market_intelligence.scheduler as sched

    monkeypatch.setattr(sched, "get_market_status",
                        lambda d: SimpleNamespace(is_trading_day=True))
    pool, conn = make_mock_pool()
    pace_rows = [{"ticker": "FOO", "projected_vol": 20_000_000,
                  "current_price": 10.0, "gap_pct": 5.0}]
    conn.fetch = AsyncMock(side_effect=[pace_rows, []])     # pace, actual-fired
    monkeypatch.setattr(sched, "get_pool", AsyncMock(return_value=pool))
    direct = AsyncMock()
    monkeypatch.setattr(sched, "send_telegram_message", direct)

    n = await sched._9m_pace_digest_job()

    assert n == 1
    direct.assert_not_awaited()                             # no standalone Telegram
    assert list(close_digest._buffer.keys()) == ["9M"]      # buffered for 16:55
    text = close_digest._buffer["9M"][0]
    assert "FOO" in text and "9M EP Pace" in text
