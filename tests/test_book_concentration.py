"""#452 R1 Stage 1 — correlated-book concentration telemetry pins.

Pins: (1) ≥2 open positions sharing a Stage-A family flag; disjoint books
don't; (2) a multi-family ticker counts in EACH family (over-warn, never
under-warn); (3) entry-basis notional + %-of-equity math incl. the equity-None
degrade; (4) the wiring writes the audit row ALWAYS and Telegrams ONLY when
flagged (actionable-only house rule); (5) read-only — no mi_live_trades writes.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from tests.conftest import make_mock_pool

from agents.market_intelligence import book_concentration as bc


def _pos(tk, shares=10, px=100.0):
    return {"ticker": tk, "remaining_shares": shares, "entry_price": px}


THEMES = [
    {"name": "Pure-Play Quantum Computing Hardware", "tickers": ["QBTS", "IONQ"]},
    {"name": "Quantum Networking Infrastructure", "tickers": ["QUBT"]},
    {"name": "U.S. Petroleum Refining & Downstream Processing", "tickers": ["PBF"]},
]


def test_same_family_across_two_themes_flags():
    # QBTS and QUBT are in DIFFERENT themes but the SAME stem family (quantum) —
    # exactly the "one theme in five costumes" premortem scenario.
    res = bc.compute_concentration([_pos("QBTS"), _pos("QUBT"), _pos("PBF")],
                                   THEMES, equity=10_000)
    assert res["flagged"] == [("quantum", ["QBTS", "QUBT"])]
    assert res["n_open"] == 3
    line = bc.format_concentration_line(res)
    assert "2/3" in line and "quantum" in line and "QBTS" in line


def test_disjoint_book_no_flag():
    res = bc.compute_concentration([_pos("QBTS"), _pos("PBF")], THEMES, 10_000)
    assert res["flagged"] == []


def test_empty_book():
    res = bc.compute_concentration([], THEMES, 10_000)
    assert res == {"n_open": 0, "notional": 0.0, "pct_equity": 0.0,
                   "families": {}, "flagged": [], "unthemed": []}


def test_notional_and_pct_math_and_equity_none_degrade():
    res = bc.compute_concentration([_pos("QBTS", 10, 100.0), _pos("QUBT", 5, 200.0)],
                                   THEMES, equity=4_000)
    assert res["notional"] == 2_000.0
    assert res["pct_equity"] == 50.0
    res2 = bc.compute_concentration([_pos("QBTS")], THEMES, equity=None)
    assert res2["pct_equity"] is None
    # the line degrades to absolute $ when equity is unknown
    res2["flagged"] = [("quantum", ["QBTS"])]
    assert "$" in bc.format_concentration_line(res2)


def test_unthemed_tickers_tracked_not_flagged():
    res = bc.compute_concentration([_pos("ZZZZ"), _pos("YYYY")], THEMES, 10_000)
    assert res["unthemed"] == ["YYYY", "ZZZZ"]
    assert res["flagged"] == []


@pytest.mark.asyncio
async def test_snapshot_wiring_audit_always_telegram_only_when_flagged(monkeypatch):
    pool, conn = make_mock_pool()
    # open book: 2 quantum names → flagged
    conn.fetch = AsyncMock(side_effect=[
        [_pos("QBTS"), _pos("QUBT")],                       # positions
        [dict(name=t["name"], tickers=t["tickers"]) for t in THEMES],  # themes
    ])
    conn.fetchrow = AsyncMock(return_value={"equity": 15_000})
    monkeypatch.setattr(bc, "get_pool", AsyncMock(return_value=pool))
    audit = AsyncMock()
    monkeypatch.setattr(bc, "log_audit_event", audit)
    from agents.market_intelligence import briefing as _brief
    tg = AsyncMock()
    monkeypatch.setattr(_brief, "send_telegram_message", tg)

    res = await bc.run_book_concentration_snapshot("live")

    assert res["flagged"] and res["flagged"][0][0] == "quantum"
    audit.assert_awaited_once()
    assert audit.await_args.args[0] == "book_concentration_snapshot"
    tg.assert_awaited_once()
    assert "quantum" in tg.await_args.args[0]
    conn.execute.assert_not_called()   # read-only: zero writes to trade state


@pytest.mark.asyncio
async def test_snapshot_clean_book_audits_but_stays_silent(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[
        [_pos("QBTS"), _pos("PBF")],                        # disjoint book
        [dict(name=t["name"], tickers=t["tickers"]) for t in THEMES],
    ])
    conn.fetchrow = AsyncMock(return_value=None)            # no equity snapshot yet
    monkeypatch.setattr(bc, "get_pool", AsyncMock(return_value=pool))
    audit = AsyncMock()
    monkeypatch.setattr(bc, "log_audit_event", audit)
    from agents.market_intelligence import briefing as _brief
    tg = AsyncMock()
    monkeypatch.setattr(_brief, "send_telegram_message", tg)

    res = await bc.run_book_concentration_snapshot("live")

    assert res["flagged"] == []
    audit.assert_awaited_once()      # the series is written even when clean
    tg.assert_not_awaited()          # no noise on a clean book
