"""#380 — FMP v3 → /stable/ migration: endpoint + FIELD-NAME mapping.

Context (the finding behind this test): the codebase pointed `FMP_BASE` at the
DEPRECATED `/api/v3/` API, which 403s on every endpoint (verified live
2026-06-25, incl. the free quote). The current `/stable/` API returns 200 — but
it RENAMES response fields and takes the symbol as a QUERY param. A naive
base-URL swap would still have produced NULL fundamentals because the field
names changed.

IMPORTANT: `_fmp_get` has NO live caller today (the grade's Q/Q + Y/Y comes from
Polygon `/vX/reference/financials` + news-corpus LLM extraction, not FMP). This
test pins the verified /stable/ field mapping + proves the catalyst Q/Q + Y/Y
math populates from it — so the mapping is correct and tested for the operator's
re-wire decision (#380), WITHOUT wiring FMP into the live grade.

Covers:
  (1) _fmp_get reads the real /stable/ income-statement fields from a mocked
      200 response (camelCase: revenue, grossProfit, eps, epsDiluted, ...).
  (2) normalize_fmp_stable_quarter maps those into our quarter shape.
  (3) the normalized quarters feed compute_growth_deltas → real Q/Q + Y/Y
      revenue & EPS growth (the "catalyst depth actually populates" check).
"""
from __future__ import annotations

import pytest

import agents.market_intelligence.collector as collector
from agents.market_intelligence.collector import normalize_fmp_stable_quarter
from scripts.fetch_ep_fundamentals import compute_growth_deltas


# A faithful slice of the REAL /stable/income-statement response shape
# (field names verified live 2026-06-25 against AAPL). Two fiscal years of the
# same quarter so YoY resolves, plus the sequential prior quarter for QoQ.
def _stable_income_response() -> list[dict]:
    return [
        # Q2 FY2026 (current)
        {"symbol": "AAPL", "date": "2026-03-28", "period": "Q2", "fiscalYear": 2026,
         "filingDate": "2026-05-01", "revenue": 120_000_000_000, "grossProfit": 56_000_000_000,
         "operatingIncome": 36_000_000_000, "netIncome": 30_000_000_000,
         "eps": 2.00, "epsDiluted": 1.98},
        # Q1 FY2026 (sequential prior — for QoQ)
        {"symbol": "AAPL", "date": "2025-12-28", "period": "Q1", "fiscalYear": 2026,
         "filingDate": "2026-02-01", "revenue": 110_000_000_000, "grossProfit": 50_000_000_000,
         "operatingIncome": 33_000_000_000, "netIncome": 27_000_000_000,
         "eps": 1.80, "epsDiluted": 1.78},
        # Q2 FY2025 (prior-year same quarter — for YoY)
        {"symbol": "AAPL", "date": "2025-03-29", "period": "Q2", "fiscalYear": 2025,
         "filingDate": "2025-05-02", "revenue": 100_000_000_000, "grossProfit": 45_000_000_000,
         "operatingIncome": 30_000_000_000, "netIncome": 25_000_000_000,
         "eps": 1.60, "epsDiluted": 1.58},
    ]


@pytest.mark.asyncio
async def test_fmp_get_reads_stable_fields(monkeypatch):
    """_fmp_get returns the /stable/ rows with their (renamed) field names."""
    monkeypatch.setenv("FMP_API_KEY", "k")
    captured = {}

    class _Resp:
        def raise_for_status(self): return None
        def json(self): return _stable_income_response()

    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params=None):
            captured["url"] = url
            captured["params"] = params
            return _Resp()

    monkeypatch.setattr(collector.httpx, "AsyncClient", lambda *a, **k: _Client())

    rows = await collector._fmp_get("/income-statement", {"symbol": "AAPL", "period": "quarter"})

    # Hits the /stable/ base (not /api/v3/), with the symbol as a QUERY param.
    assert collector.FMP_BASE.endswith("/stable")
    assert "/stable/income-statement" in captured["url"]
    assert captured["params"]["symbol"] == "AAPL"
    # The renamed stable fields are present (this is what v3→stable changed).
    assert rows[0]["revenue"] == 120_000_000_000
    assert "grossProfit" in rows[0] and "epsDiluted" in rows[0]


def test_normalizer_maps_renamed_fields():
    q = normalize_fmp_stable_quarter(_stable_income_response()[0])
    assert q["revenue"] == 120_000_000_000
    assert q["gross_profit"] == 56_000_000_000     # ← grossProfit
    assert q["operating_income"] == 36_000_000_000  # ← operatingIncome
    assert q["net_income"] == 30_000_000_000        # ← netIncome
    assert q["eps_basic"] == 2.00                   # ← eps
    assert q["eps_diluted"] == 1.98                 # ← epsDiluted
    assert q["fiscal_period"] == "Q2"               # ← period
    assert q["fiscal_year"] == 2026                 # ← fiscalYear
    # margins computed from absolutes (free tier has no ratios endpoint)
    assert q["gross_margin"] == pytest.approx(56 / 120)
    assert q["net_margin"] == pytest.approx(30 / 120)


def test_catalyst_qq_yoy_populates_from_stable_mapping():
    """The 'catalyst depth actually populates' check: the normalized /stable/
    quarters feed compute_growth_deltas and yield REAL Q/Q + Y/Y numbers."""
    quarters = [normalize_fmp_stable_quarter(r) for r in _stable_income_response()]
    deltas = compute_growth_deltas(quarters)

    # Y/Y revenue: 120B vs prior-year-Q2 100B = +20%
    assert deltas["rev_yoy_q0"] == pytest.approx(0.20)
    # Q/Q revenue: 120B vs sequential 110B = +9.09%
    assert deltas["rev_qoq_q0"] == pytest.approx(120 / 110 - 1)
    # Y/Y EPS (diluted preferred): 1.98 vs prior-year 1.58 = +25.3%
    assert deltas["eps_yoy_q0"] == pytest.approx(1.98 / 1.58 - 1)
    # all populated (not None) — the silent-null symptom is gone for this path
    assert deltas["rev_yoy_q0"] is not None
    assert deltas["eps_yoy_q0"] is not None
