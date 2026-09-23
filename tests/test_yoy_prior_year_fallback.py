"""#321 — period-matched prior-year YoY recovery.

When the news corpus states the CURRENT quarter's revenue but NOT the YoY %, we recover it from the
prior-year SAME quarter (a year old, so structured sources reliably have it). The match is by
fiscal_period — deterministic, never the crude yfinance [-1] (which on a gap day is the prior quarter).
None on any gap (no period / no prior-year match / scale-inconsistent) → caller keeps the conservative
downgrade. NEVER fabricate.

Bug fix (2026-08): the match previously silently broke for any company whose fiscal year is not
calendar-aligned (e.g. LRCX ~June FYE, ARM March FYE, TAL February FYE) because the yfinance-side
label was built from raw CALENDAR month, not the company's own fiscal-quarter numbering — see
TestFiscalQuarterMislabelBug below for the end-to-end reproduction against get_fundamentals().
"""
import asyncio
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from agents.market_intelligence import fundamentals
from agents.market_intelligence.fundamentals import (
    _parse_fiscal_quarter,
    compute_yoy_from_prior_year,
    get_fundamentals,
)


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


# ── Non-calendar fiscal year: end-to-end reproduction of the mislabeling bug ────────────────────
#
# Real cases (2026-08-08 DB pull, mi_ep_catalyst_metrics): LRCX "Q4 FY2026" and TAL "Q1 FY2027" both
# had a matching prior-year row PRESENT in yfinance's own quarterly_income_stmt, but stayed unfilled
# because _quarter_label bucketed every column by raw calendar month, so a company whose fiscal year
# doesn't end in December gets every quarter mislabeled relative to its own "Qn FYyyyy" convention.
# These tests exercise the REAL get_fundamentals() (only yfinance.Ticker is mocked) so they cover the
# label-construction bug directly, not just the matching function in isolation.

def _fye_income_stmt(quarters: list, revenues: list) -> pd.DataFrame:
    data = {
        "Total Revenue": dict(zip(quarters, revenues)),
        "Basic EPS": dict(zip(quarters, [0.1] * len(quarters))),
        "Gross Profit": {q: r * 0.5 for q, r in zip(quarters, revenues)},
    }
    return pd.DataFrame(data).T


def _fye_mock_ticker(quarters: list, revenues: list, last_fiscal_year_end_ts: int) -> MagicMock:
    df = _fye_income_stmt(quarters, revenues)
    t = MagicMock()
    t.quarterly_income_stmt = df
    t.quarterly_financials = df
    t.income_stmt = df
    t.financials = df
    t.info = {"lastFiscalYearEnd": last_fiscal_year_end_ts}
    t.calendar = None
    return t


class TestFiscalQuarterMislabelBug:
    # LRCX-shaped: fiscal year ends ~June 30. Fiscal Q4 FY2025 = quarter ending 2025-06-30;
    # fiscal Q4 FY2026 = quarter ending 2026-06-30 (the "current" quarter in this scenario).
    _JUNE_FYE_QUARTERS = [
        pd.Timestamp("2024-09-30"), pd.Timestamp("2024-12-31"),
        pd.Timestamp("2025-03-31"), pd.Timestamp("2025-06-30"),
        pd.Timestamp("2025-09-30"), pd.Timestamp("2025-12-31"),
        pd.Timestamp("2026-03-31"), pd.Timestamp("2026-06-30"),
    ]
    _JUNE_FYE_REVENUES = [50e6, 55e6, 60e6, 100e6, 70e6, 80e6, 90e6, 200e6]
    # 2025-06-30 (index 3) = prior-year Q4 -> $100M; 2026-06-30 (index 7) = current Q4 -> $200M.
    _JUNE_FYE_TS = int(pd.Timestamp("2026-06-30").timestamp())

    def test_quarter_label_honors_fiscal_year_end(self):
        """The June-2025 column must be labeled Q4'25 (this company's own numbering), not the
        calendar-quarter Q2'25 the old unconditional calendar-month bucketing produced."""
        t = self._fye_mock_ticker_helper()
        with patch("yfinance.Ticker", return_value=t):
            result = asyncio.run(get_fundamentals("LRCXLIKE"))
        periods = {q["period"]: q["revenue_m"] for q in result["quarterly_revenue"]}
        assert "Q4'25" in periods, f"expected fiscal Q4'25 label, got periods={sorted(periods)}"
        assert abs(periods["Q4'25"] - 100.0) < 0.1
        assert "Q4'26" in periods, f"expected fiscal Q4'26 label, got periods={sorted(periods)}"

    @pytest.mark.asyncio
    async def test_compute_yoy_fills_for_non_calendar_fye(self):
        """End-to-end: a company reporting its OWN 'Q4 FY2026' (fiscal, not calendar) now recovers
        YoY from the prior-year fiscal Q4 even though that row's calendar month differs from Q4."""
        t = self._fye_mock_ticker_helper()
        with patch("yfinance.Ticker", return_value=t):
            rec = await compute_yoy_from_prior_year("LRCXLIKE", "Q4 FY2026", 200_000_000)
        assert rec is not None, "fiscal-quarter match should now succeed for a non-calendar FYE company"
        assert rec["yoy_pct"] == 100.0   # (200M - 100M) / 100M * 100
        assert rec["prior_period"] == "Q4'25"

    def _fye_mock_ticker_helper(self) -> MagicMock:
        return _fye_mock_ticker(self._JUNE_FYE_QUARTERS, self._JUNE_FYE_REVENUES, self._JUNE_FYE_TS)


# ── Emit-dedup wiring pin (2026-08-12) ───────────────────────────────────────
# catalyst_yoy_recovered_live must be guarded per-ticker-per-day, same idiom as
# the carve-out (test_catalyst_downgrade_carveout.py::test_carveout_audit_emit_is_dedup_guarded)
# — else it re-fires on every 5-min scan for an earnings name. Operator report
# 2026-08-12: KRNT rescued ONCE but logged 5-6x, inflating the morning digest
# to "10 rescued" when only 1 name was actually rescued. The recovery DECISION
# (_downgrade_reason = None) must stay UNGUARDED (idempotent, must run every
# scan) — only the audit emit is deduped.
import re as _re
from pathlib import Path as _Path

_EP_SRC_YOY = (_Path(__file__).resolve().parent.parent
               / "agents" / "market_intelligence" / "ep_detector.py").read_text()


def test_yoy_recovered_live_emit_is_dedup_guarded():
    """catalyst_yoy_recovered_live log_audit_event must sit inside an
    `await _should_log_catalyst_earnings_event_today(...)` guard (logs once per
    ticker per day, not once per 5-min scan)."""
    guard = _re.search(
        r'_should_log_catalyst_earnings_event_today\(\s*'
        r'"catalyst_yoy_recovered_live"', _EP_SRC_YOY)
    emit = _re.search(
        r'log_audit_event\(\s*"catalyst_yoy_recovered_live"', _EP_SRC_YOY)
    assert guard, "catalyst_yoy_recovered_live emit lost its per-day dedup guard (KRNT-class regression)"
    assert emit, "catalyst_yoy_recovered_live log_audit_event not found (refactor?)"
    assert guard.start() < emit.start(), "the dedup guard must precede the emit"
    assert emit.start() - guard.start() < 400, "the guard must wrap the emit (same block)"


def test_yoy_recovered_decision_runs_before_the_emit_guard():
    """The recovery DECISION (_downgrade_reason = None) must appear BEFORE the
    emit-dedup guard, so clearing the downgrade stays idempotent every scan even
    when the audit row is deduped away."""
    block = _EP_SRC_YOY[_EP_SRC_YOY.find("#321 LIVE rescue"):]
    none_idx = block.find("_downgrade_reason = None")
    guard_idx = block.find("_should_log_catalyst_earnings_event_today")
    assert none_idx != -1 and guard_idx != -1
    assert none_idx < guard_idx, "the recovery decision must run outside/before the emit-dedup guard"


# `extraction_error` and `live_enriched_grade_failed` are DELIBERATELY left unguarded
# at the source (2026-08-11 commit 703d450: "the monitor dedupes its own read, so the
# signal is safe, but the raw rows still inflate") — the grading-health check reads
# distinct error text per failure and its own (event, ticker) read-side dedup already
# makes the count safe; guarding the source would silently drop later distinct error
# messages for the same ticker/day. Not touched here — still KNOWN RESIDUAL.
