"""#321 — period-matched prior-year YoY recovery.

When the news corpus states the CURRENT quarter's revenue but NOT the YoY %, we recover it from the
prior-year SAME quarter (a year old, so structured sources reliably have it). The match is by
fiscal_period — deterministic, never the crude yfinance [-1] (which on a gap day is the prior quarter).
None on any gap (no period / no prior-year match / scale-inconsistent) → caller keeps the conservative
downgrade. NEVER fabricate.
"""
import pytest

from agents.market_intelligence import fundamentals
from agents.market_intelligence.fundamentals import _parse_fiscal_quarter, compute_yoy_from_prior_year


def test_parse_fiscal_quarter_forms():
    assert _parse_fiscal_quarter("Q2 FY2026") == (2, 2026)
    assert _parse_fiscal_quarter("Q3 2026") == (3, 2026)
    assert _parse_fiscal_quarter("Q2'26") == (2, 2026)          # yfinance's form
    assert _parse_fiscal_quarter("fiscal Q1 2027") == (1, 2027)
    assert _parse_fiscal_quarter("") is None
    assert _parse_fiscal_quarter("no quarter stated") is None


def _fake_gf(rows):
    async def _gf(ticker):
        return {"quarterly_revenue": rows}
    return _gf


@pytest.mark.asyncio
async def test_compute_yoy_period_matched(monkeypatch):
    monkeypatch.setattr(fundamentals, "get_fundamentals", _fake_gf([
        {"period": "Q2'25", "revenue_m": 100.0},
        {"period": "Q3'25", "revenue_m": 110.0},
        {"period": "Q4'25", "revenue_m": 120.0},
        {"period": "Q1'26", "revenue_m": 130.0},
    ]))
    # current Q2 FY2026 = $125M; prior-year Q2'25 = $100M -> +25.0%
    rec = await compute_yoy_from_prior_year("XYZ", "Q2 FY2026", 125_000_000)
    assert rec is not None
    assert rec["yoy_pct"] == 25.0
    assert rec["prior_period"] == "Q2'25"
    assert rec["source"] == "yfinance_prior_year"


@pytest.mark.asyncio
async def test_compute_yoy_no_prior_year_match_stays_none(monkeypatch):
    # the prior-year same quarter (Q2'25) is absent -> None (conservative, no fabrication)
    monkeypatch.setattr(fundamentals, "get_fundamentals", _fake_gf([
        {"period": "Q1'26", "revenue_m": 130.0},
    ]))
    rec = await compute_yoy_from_prior_year("XYZ", "Q2 FY2026", 125_000_000)
    assert rec is None


@pytest.mark.asyncio
async def test_compute_yoy_scale_guard_drops_inconsistent(monkeypatch):
    # current $125M vs a $0.1M prior leg -> +124900%, outside the sane band -> None (scale mismatch)
    monkeypatch.setattr(fundamentals, "get_fundamentals", _fake_gf([
        {"period": "Q2'25", "revenue_m": 0.1},
    ]))
    rec = await compute_yoy_from_prior_year("XYZ", "Q2 FY2026", 125_000_000)
    assert rec is None


@pytest.mark.asyncio
async def test_compute_yoy_no_period_label_stays_none():
    # no fiscal_period -> can't match deterministically -> None (don't infer-and-guess)
    assert await compute_yoy_from_prior_year("XYZ", None, 125_000_000) is None
    assert await compute_yoy_from_prior_year("XYZ", "Q2 FY2026", None) is None
