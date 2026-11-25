from datetime import date
"""2026-11-24 — the nightly RS member prune is VISIBLE (audit row per pruned member) and the operator
promotion confirm WARNS about members the cut will likely drop. Membership behaviour is unchanged
(operator ruling 11-24: keep the prune, no exemption for promoted themes)."""
import datetime as _dt
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import db as dbmod
from agents.market_intelligence import theme_engine as te
from agents.market_intelligence.agent import _render_promote_result

TUESDAY = _dt.date(2026, 11, 24)
NAME = "Bitcoin Miners & AI/HPC Data-Center Pivot"
STOCKS = {
    "CORZ": {"ticker": "CORZ", "rs_composite": 3.5, "sector": "Technology"},
    "CRWV": {"ticker": "CRWV", "rs_composite": 3.9, "sector": "Technology"},
    "RIOT": {"ticker": "RIOT", "rs_composite": 44.8, "sector": "Technology"},
    "FIGR": {"ticker": "FIGR", "rs_composite": 44.6, "sector": "Technology"},
}
FALLING = {"CORZ": [3.5, 5.0, 8.0, 12.0, 15.0, 20.0], "CRWV": [3.9, 6.0, 9.0, 13.0, 17.0, 22.0]}


def _mocks(monkeypatch, hist, audit):
    async def fake_batch(tickers, today, days=3):
        return {tk: hist.get(tk, []) for tk in tickers}

    async def fake_history(name, days=7, tickers=None):
        return []

    async def fake_news(name, tickers=None):
        return 30, "solid description", False

    async def fake_breadth(tickers, today):
        return 0.9

    monkeypatch.setattr(te, "get_recent_rs_batch", fake_batch)
    monkeypatch.setattr(te, "_get_theme_history", fake_history)
    monkeypatch.setattr(te, "_news_check", fake_news)
    monkeypatch.setattr(te, "get_ticker_breadth_above_sma20", fake_breadth)
    monkeypatch.setattr(te, "log_audit_event", audit)


def _theme():
    return {"name": NAME, "tickers": ["CORZ", "RIOT", "CRWV", "FIGR"], "score": 60,
            "stage": "Nascent", "description": "d"}


@pytest.mark.asyncio
async def test_prune_writes_one_row_per_pruned_member_and_membership_unchanged(monkeypatch):
    rows = []

    async def audit(event_type, summary="", detail=""):
        rows.append((event_type, summary, detail))

    _mocks(monkeypatch, FALLING, audit)
    result, changelog = await te._rescore_existing_theme(_theme(), STOCKS, TUESDAY, protected=set())
    assert result["tickers"] == ["RIOT", "FIGR"]
    assert [c["ticker"] for c in changelog if c["type"] == "ticker_pruned"] == ["CORZ", "CRWV"]
    pr = [r for r in rows if r[0] == "theme_member_pruned_rs"]
    assert len(pr) == 2
    assert pr[0][1] == f"'{NAME}': CORZ pruned — RS 3.5 below the hard floor 25 (not rising)"
    assert f"theme={NAME}" in pr[0][2] and "ticker=CORZ" in pr[0][2]
    assert "rs_now=3.5" in pr[0][2] and "rule=hard" in pr[0][2] and "floor=25" in pr[0][2]
    assert "CRWV" in pr[1][1]


@pytest.mark.asyncio
async def test_prune_audit_failure_changes_nothing(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("db down")

    _mocks(monkeypatch, FALLING, boom)
    result, changelog = await te._rescore_existing_theme(_theme(), STOCKS, TUESDAY, protected=set())
    assert result["tickers"] == ["RIOT", "FIGR"]
    assert [c["ticker"] for c in changelog if c["type"] == "ticker_pruned"] == ["CORZ", "CRWV"]


@pytest.mark.asyncio
async def test_rising_held_member_writes_no_prune_row(monkeypatch):
    rows = []

    async def audit(event_type, summary="", detail=""):
        rows.append(event_type)

    hist = dict(FALLING)
    hist["CRWV"] = [3.9, 3.0, 2.0, 1.5, 1.0, 0.5]   # rising
    _mocks(monkeypatch, hist, audit)
    result, _ = await te._rescore_existing_theme(_theme(), STOCKS, TUESDAY, protected=set())
    assert "CRWV" in result["tickers"] and "CORZ" not in result["tickers"]
    assert rows.count("theme_member_pruned_rs") == 1


# ── promotion warning ────────────────────────────────────────────────────────

def test_warning_pure_hard_soft_and_rising():
    w = te.prune_warnings_for_members(
        {"A": 3.5, "B": 3.9, "C": 44.8, "D": 30.0, "E": 10.0, "F": 31.0},
        {"A": [3.5, 5, 8, 12, 15, 20], "B": [3.9, 6, 9, 13, 17, 22],
         "D": [30.0, 31.0, 32.0, 36.0, 40.0, 44.0],            # soft: 3 below 35, falling
         "E": [10.0, 9, 8, 7, 6, 5],                            # hard but rising
         "F": [31.0, 40.0, 41.0, 42.0]})                        # soft, only 1 of 3 below
    assert [(x["ticker"], x["rule"]) for x in w] == [("A", "hard"), ("B", "hard"), ("D", "soft")]


MONDAY_COMPLETE = date(2026, 11, 23)


def test_warning_no_current_data_member_and_min_floor():
    # missing from latest RS but last 5 readings all < 25 -> warned (mirrors the prune's no-data arm)
    w = te.prune_warnings_for_members({"A": None, "B": 44.0, "C": 45.0},
                                      {"A": [4.0, 5, 6, 7, 8, 9]})
    assert [(x["ticker"], x["rs"]) for x in w] == [("A", 4.0)]
    # 3 members, 2 sub-floor falling: floor 2 -> only the lowest-RS one is actually cut
    w = te.prune_warnings_for_members({"A": 3.5, "B": 3.9, "C": 44.0},
                                      {"A": [3.5, 5, 8, 12, 15, 20], "B": [3.9, 6, 9, 13, 17, 22]})
    assert [x["ticker"] for x in w] == ["A"]


@pytest.mark.asyncio
async def test_promote_history_bounded_to_latest_complete_date(monkeypatch):
    seen = {}
    orig_hist = {"CORZ": [3.5, 5, 8, 12, 15, 20]}

    async def _rec(tickers, d, days=3):
        seen["d"] = d
        return orig_hist
    res = await _promote(monkeypatch, _rs_rows(RS), FALLING)
    monkeypatch.setattr(te, "get_recent_rs_batch", _rec)
    from tests.conftest import make_mock_pool
    await te.promote_candidate_by_name("bitcoin miners", TUESDAY)
    assert seen["d"] == MONDAY_COMPLETE


async def _promote(monkeypatch, rs_rows, hist, batch_raises=False):
    from tests.conftest import make_mock_pool, stub_promotion_guards
    stub_promotion_guards(monkeypatch)
    monkeypatch.setattr(te, "get_theme_birth_gate_mode", AsyncMock(return_value="off"))
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=rs_rows)
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[
        {"name": NAME, "tickers": ["CORZ", "RIOT", "CRWV", "FIGR"], "thesis": "t",
         "source": "rs_slope_synthesis"}]))
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(te, "_canonicalize_theme_names", AsyncMock(return_value=0))
    monkeypatch.setattr(te, "log_audit_event", AsyncMock())
    if batch_raises:
        monkeypatch.setattr(te, "get_recent_rs_batch", AsyncMock(side_effect=RuntimeError("rs down")))
    else:
        monkeypatch.setattr(te, "get_recent_rs_batch",
                            AsyncMock(return_value={k: v for k, v in hist.items()}))
    return await te.promote_candidate_by_name("bitcoin miners", TUESDAY)


def _rs_rows(rs):
    return [{"ticker": k, "rs_composite": v, "close": 10.0, "sma_20": 9.0, "score_date": MONDAY_COMPLETE} for k, v in rs.items()]


RS = {"CORZ": 3.5, "CRWV": 3.9, "RIOT": 44.8, "FIGR": 44.6}


@pytest.mark.asyncio
async def test_promote_confirm_warns_for_sub_floor_falling(monkeypatch):
    res = await _promote(monkeypatch, _rs_rows(RS), FALLING)
    assert res["status"] == "promoted"
    text = _render_promote_result(res, "bitcoin miners")
    print("\n" + text)
    assert ("⚠ CORZ (RS 3.5), CRWV (RS 3.9) are below RS 25 — the nightly cut will likely drop "
            "them tomorrow.") in text
    assert "RIOT (RS" not in text and "FIGR (RS" not in text


@pytest.mark.asyncio
async def test_promote_confirm_omits_rising_member(monkeypatch):
    hist = dict(FALLING)
    hist["CRWV"] = [3.9, 3.0, 2.0, 1.5, 1.0, 0.5]
    res = await _promote(monkeypatch, _rs_rows(RS), hist)
    text = _render_promote_result(res, "bitcoin miners")
    assert "CORZ (RS 3.5) is below RS 25" in text and "CRWV (RS" not in text


@pytest.mark.asyncio
async def test_promote_unchanged_when_rs_read_fails(monkeypatch):
    res = await _promote(monkeypatch, _rs_rows(RS), {}, batch_raises=True)
    assert res["status"] == "promoted" and res["n_members"] == 4
    assert res["rs_warnings"] == []
    assert "⚠" not in _render_promote_result(res, "bitcoin miners")
