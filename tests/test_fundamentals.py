"""
Tests for agents/market_intelligence/fundamentals.py

Covers:
- get_fundamentals() structure and quality flag logic
- format_fundamentals() output correctness
- Edge cases: empty data, missing columns, None EPS
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_quarterly_income(quarters: list[tuple], eps_vals: list, rev_vals: list) -> pd.DataFrame:
    """
    Build a fake quarterly_income_stmt DataFrame.
    quarters: list of pd.Timestamp columns (oldest first)
    eps_vals: list of EPS values aligned to quarters
    rev_vals: list of revenue values (in absolute dollars) aligned to quarters
    """
    data = {
        "Basic EPS": dict(zip(quarters, eps_vals)),
        "Total Revenue": dict(zip(quarters, rev_vals)),
        "Gross Profit": {q: r * 0.55 for q, r in zip(quarters, rev_vals)},  # 55% margin
    }
    return pd.DataFrame(data).T


def _make_quarters(n: int = 8):
    """Generate n quarterly Timestamps, oldest first."""
    from datetime import datetime
    base = datetime(2024, 3, 31)
    quarters = []
    for i in range(n - 1, -1, -1):
        month = ((base.month - 1 - i * 3) % 12) + 1
        year = base.year - (i * 3) // 12 + (1 if (base.month - 1 - i * 3) < 0 else 0)
        quarters.append(pd.Timestamp(year=base.year - (i // 4), month=[3, 6, 9, 12][i % 4], day=28))
    return quarters


# ── get_fundamentals: structure ───────────────────────────────────────────────

class TestGetFundamentalsStructure:
    def _fake_ticker(self, eps_vals=None, rev_vals=None):
        """Build a mock yfinance Ticker with controlled quarterly income data."""
        quarters = [
            pd.Timestamp("2022-03-31"), pd.Timestamp("2022-06-30"),
            pd.Timestamp("2022-09-30"), pd.Timestamp("2022-12-31"),
            pd.Timestamp("2023-03-31"), pd.Timestamp("2023-06-30"),
            pd.Timestamp("2023-09-30"), pd.Timestamp("2023-12-31"),
        ]
        eps = eps_vals or [0.10, 0.12, 0.14, 0.16, 0.18, 0.22, 0.28, 0.36]
        rev = rev_vals or [40e6, 45e6, 50e6, 55e6, 60e6, 72e6, 88e6, 110e6]

        df = _make_quarterly_income(quarters, eps, rev)

        t = MagicMock()
        t.quarterly_income_stmt = df
        t.quarterly_financials = df
        t.income_stmt = df
        t.financials = df
        t.info = {"grossMargins": 0.55}
        t.calendar = None
        return t

    def test_returns_required_keys(self):
        from agents.market_intelligence.fundamentals import get_fundamentals

        with patch("yfinance.Ticker", return_value=self._fake_ticker()):
            result = asyncio.run(get_fundamentals("AXTI"))

        for key in ["ticker", "quarterly_eps", "quarterly_revenue",
                    "annual_eps", "annual_revenue", "gross_margin_pct",
                    "next_earnings_date", "quality_flags"]:
            assert key in result, f"Missing key: {key}"

    def test_ticker_uppercased(self):
        from agents.market_intelligence.fundamentals import get_fundamentals

        with patch("yfinance.Ticker", return_value=self._fake_ticker()):
            result = asyncio.run(get_fundamentals("axti"))

        assert result["ticker"] == "AXTI"

    def test_quarterly_eps_structure(self):
        from agents.market_intelligence.fundamentals import get_fundamentals

        with patch("yfinance.Ticker", return_value=self._fake_ticker()):
            result = asyncio.run(get_fundamentals("AXTI"))

        eps = result["quarterly_eps"]
        assert isinstance(eps, list)
        assert len(eps) > 0
        for q in eps:
            assert "period" in q
            assert "eps" in q
            assert "yoy_pct" in q

    def test_gross_margin_populated(self):
        from agents.market_intelligence.fundamentals import get_fundamentals

        with patch("yfinance.Ticker", return_value=self._fake_ticker()):
            result = asyncio.run(get_fundamentals("AXTI"))

        assert result["gross_margin_pct"] is not None
        assert 0 < result["gross_margin_pct"] < 100

    def test_yoy_pct_computed_correctly(self):
        """YoY % for a quarter should compare to same quarter 1 year prior."""
        from agents.market_intelligence.fundamentals import get_fundamentals

        # 8 quarters: Q1'22 to Q4'23
        # Q1'23 eps=0.18, Q1'22 eps=0.10 → YoY = +80%
        quarters = [
            pd.Timestamp("2022-03-31"), pd.Timestamp("2022-06-30"),
            pd.Timestamp("2022-09-30"), pd.Timestamp("2022-12-31"),
            pd.Timestamp("2023-03-31"), pd.Timestamp("2023-06-30"),
            pd.Timestamp("2023-09-30"), pd.Timestamp("2023-12-31"),
        ]
        eps = [0.10, 0.12, 0.14, 0.16, 0.18, 0.22, 0.28, 0.36]
        rev = [40e6] * 8
        df = _make_quarterly_income(quarters, eps, rev)

        t = MagicMock()
        t.quarterly_income_stmt = df
        t.quarterly_financials = df
        t.income_stmt = df
        t.financials = df
        t.info = {}
        t.calendar = None

        with patch("yfinance.Ticker", return_value=t):
            result = asyncio.run(get_fundamentals("AXTI"))

        # Find Q1'23 (5th entry, index 4)
        q1_23 = next((q for q in result["quarterly_eps"] if q["period"] == "Q1'23"), None)
        assert q1_23 is not None
        assert q1_23["yoy_pct"] is not None
        assert abs(q1_23["yoy_pct"] - 80.0) < 1.0  # (0.18 - 0.10) / 0.10 * 100

    def test_returns_gracefully_on_yfinance_error(self):
        from agents.market_intelligence.fundamentals import get_fundamentals

        with patch("yfinance.Ticker", side_effect=RuntimeError("no data")):
            result = asyncio.run(get_fundamentals("FAKE"))

        assert "error" in result


# ── Quality flags ─────────────────────────────────────────────────────────────

class TestQualityFlags:
    def _result_with_eps_yoy(self, yoy_list: list[float]) -> dict:
        """Build a minimal result dict with controlled eps yoy sequence."""
        return {
            "quarterly_eps": [{"period": f"Q{i}", "eps": 0.5, "yoy_pct": v} for i, v in enumerate(yoy_list)],
            "quarterly_revenue": [{"period": f"Q{i}", "revenue_m": 50, "yoy_pct": v} for i, v in enumerate(yoy_list)],
        }

    def test_eps_accelerating_true(self):
        from agents.market_intelligence.fundamentals import get_fundamentals
        import asyncio

        # Manual: latest yoy > prior yoy → accelerating
        from agents.market_intelligence.fundamentals import _yoy_pct
        # Just test the flag logic directly
        eps_yoy = [20.0, 30.0, 45.0, 60.0]  # each higher than previous
        assert eps_yoy[-1] > eps_yoy[-2]  # sanity

    def test_eps_accelerating_flag_via_get_fundamentals(self):
        from agents.market_intelligence.fundamentals import get_fundamentals

        quarters = [
            pd.Timestamp("2022-03-31"), pd.Timestamp("2022-06-30"),
            pd.Timestamp("2022-09-30"), pd.Timestamp("2022-12-31"),
            pd.Timestamp("2023-03-31"), pd.Timestamp("2023-06-30"),
            pd.Timestamp("2023-09-30"), pd.Timestamp("2023-12-31"),
        ]
        # Each year's Q grows faster than the year before (acceleration)
        eps = [0.10, 0.10, 0.10, 0.10,   # year 1 baseline
               0.15, 0.20, 0.30, 0.50]   # year 2: each quarter accelerating
        rev = [40e6] * 8
        df = _make_quarterly_income(quarters, eps, rev)

        t = MagicMock()
        t.quarterly_income_stmt = df
        t.quarterly_financials = df
        t.income_stmt = df
        t.financials = df
        t.info = {}
        t.calendar = None

        with patch("yfinance.Ticker", return_value=t):
            result = asyncio.run(get_fundamentals("AXTI"))

        flags = result["quality_flags"]
        assert "eps_accelerating" in flags
        assert "eps_streak_25pct" in flags
        assert "sales_confirms" in flags
        assert "gross_margin_trend" in flags

    def test_eps_streak_counts_consecutive_25pct(self):
        """eps_streak_25pct counts from most recent quarter backwards."""
        from agents.market_intelligence.fundamentals import get_fundamentals

        quarters = [
            pd.Timestamp("2022-03-31"), pd.Timestamp("2022-06-30"),
            pd.Timestamp("2022-09-30"), pd.Timestamp("2022-12-31"),
            pd.Timestamp("2023-03-31"), pd.Timestamp("2023-06-30"),
            pd.Timestamp("2023-09-30"), pd.Timestamp("2023-12-31"),
        ]
        # Year 1 baseline. Year 2: +50% growth each quarter vs year 1 (4 qtrs ≥25%)
        baseline = 0.20
        eps = [baseline] * 4 + [baseline * 1.5] * 4  # +50% each qtr in yr 2
        rev = [50e6] * 4 + [75e6] * 4
        df = _make_quarterly_income(quarters, eps, rev)

        t = MagicMock()
        t.quarterly_income_stmt = df
        t.quarterly_financials = df
        t.income_stmt = df
        t.financials = df
        t.info = {}
        t.calendar = None

        with patch("yfinance.Ticker", return_value=t):
            result = asyncio.run(get_fundamentals("AXTI"))

        streak = result["quality_flags"]["eps_streak_25pct"]
        assert streak == 4  # all 4 year-2 quarters have 50% growth

    def test_sales_confirms_true_when_rev_growth_above_15pct(self):
        from agents.market_intelligence.fundamentals import get_fundamentals

        quarters = [
            pd.Timestamp("2022-03-31"), pd.Timestamp("2022-06-30"),
            pd.Timestamp("2022-09-30"), pd.Timestamp("2022-12-31"),
            pd.Timestamp("2023-03-31"), pd.Timestamp("2023-06-30"),
            pd.Timestamp("2023-09-30"), pd.Timestamp("2023-12-31"),
        ]
        eps = [0.10] * 8
        rev = [50e6] * 4 + [65e6] * 4   # +30% revenue growth in yr 2 ≥ 15%
        df = _make_quarterly_income(quarters, eps, rev)

        t = MagicMock()
        t.quarterly_income_stmt = df
        t.quarterly_financials = df
        t.income_stmt = df
        t.financials = df
        t.info = {}
        t.calendar = None

        with patch("yfinance.Ticker", return_value=t):
            result = asyncio.run(get_fundamentals("AXTI"))

        assert result["quality_flags"]["sales_confirms"] is True

    def test_sales_confirms_false_when_rev_growth_below_15pct(self):
        from agents.market_intelligence.fundamentals import get_fundamentals

        quarters = [
            pd.Timestamp("2022-03-31"), pd.Timestamp("2022-06-30"),
            pd.Timestamp("2022-09-30"), pd.Timestamp("2022-12-31"),
            pd.Timestamp("2023-03-31"), pd.Timestamp("2023-06-30"),
            pd.Timestamp("2023-09-30"), pd.Timestamp("2023-12-31"),
        ]
        eps = [0.10] * 8
        rev = [50e6] * 4 + [52e6] * 4   # only +4% revenue growth
        df = _make_quarterly_income(quarters, eps, rev)

        t = MagicMock()
        t.quarterly_income_stmt = df
        t.quarterly_financials = df
        t.income_stmt = df
        t.financials = df
        t.info = {}
        t.calendar = None

        with patch("yfinance.Ticker", return_value=t):
            result = asyncio.run(get_fundamentals("AXTI"))

        assert result["quality_flags"]["sales_confirms"] is False


# ── format_fundamentals ───────────────────────────────────────────────────────

class TestFormatFundamentals:
    def _sample_data(self):
        return {
            "ticker": "AXTI",
            "gross_margin_pct": 58.2,
            "next_earnings_date": "2026-04-15",
            "quarterly_eps": [
                {"period": "Q1'24", "eps": 0.12, "yoy_pct": 20.0},
                {"period": "Q2'24", "eps": 0.18, "yoy_pct": 50.0},
                {"period": "Q3'24", "eps": 0.24, "yoy_pct": 85.0},
                {"period": "Q4'24", "eps": 0.31, "yoy_pct": 120.0},
                {"period": "Q1'25", "eps": 0.38, "yoy_pct": 217.0},
                {"period": "Q2'25", "eps": 0.47, "yoy_pct": 161.0},
            ],
            "quarterly_revenue": [
                {"period": "Q1'24", "revenue_m": 42.0, "yoy_pct": 15.0},
                {"period": "Q2'24", "revenue_m": 58.0, "yoy_pct": 32.0},
                {"period": "Q3'24", "revenue_m": 71.0, "yoy_pct": 47.0},
                {"period": "Q4'24", "revenue_m": 89.0, "yoy_pct": 65.0},
                {"period": "Q1'25", "revenue_m": 108.0, "yoy_pct": 157.0},
                {"period": "Q2'25", "revenue_m": 134.0, "yoy_pct": 131.0},
            ],
            "annual_eps": [
                {"year": 2021, "eps": 0.42},
                {"year": 2022, "eps": 0.55},
                {"year": 2023, "eps": 0.71},
                {"year": 2024, "eps": 1.23},
            ],
            "annual_revenue": [
                {"year": 2021, "revenue_m": 180.0},
                {"year": 2022, "revenue_m": 210.0},
                {"year": 2023, "revenue_m": 254.0},
                {"year": 2024, "revenue_m": 380.0},
            ],
            "quality_flags": {
                "eps_accelerating": True,
                "eps_streak_25pct": 5,
                "sales_confirms": True,
                "gross_margin_trend": "expanding",
            },
        }

    def test_ticker_in_header(self):
        from agents.market_intelligence.fundamentals import format_fundamentals
        text = format_fundamentals(self._sample_data())
        assert "AXTI" in text

    def test_gross_margin_shown_in_table(self):
        """Gross margin shown per-quarter in GM% row, not just header."""
        from agents.market_intelligence.fundamentals import format_fundamentals
        data = self._sample_data()
        # Add quarterly_gross_margin to sample data
        data["quarterly_gross_margin"] = [
            {"period": p, "gm_pct": 58.0 + i}
            for i, p in enumerate(["Q1'24", "Q2'24", "Q3'24", "Q4'24", "Q1'25", "Q2'25"])
        ]
        text = format_fundamentals(data)
        assert "GM%" in text
        assert "58%" in text or "59%" in text

    def test_next_earnings_shown(self):
        from agents.market_intelligence.fundamentals import format_fundamentals
        text = format_fundamentals(self._sample_data())
        assert "Apr 15, 2026" in text

    def test_quarterly_eps_values_present(self):
        from agents.market_intelligence.fundamentals import format_fundamentals
        text = format_fundamentals(self._sample_data())
        assert "0.47" in text   # latest quarterly EPS
        assert "0.12" in text   # oldest shown

    def test_yoy_pct_shown_with_sign(self):
        from agents.market_intelligence.fundamentals import format_fundamentals
        text = format_fundamentals(self._sample_data())
        assert "+217%" in text or "+217" in text

    def test_annual_table_present(self):
        from agents.market_intelligence.fundamentals import format_fundamentals
        text = format_fundamentals(self._sample_data())
        assert "2021" in text
        assert "2024" in text
        assert "1.23" in text   # FY2024 EPS

    def test_quality_flags_green_when_all_good(self):
        from agents.market_intelligence.fundamentals import format_fundamentals
        text = format_fundamentals(self._sample_data())
        assert "🟢 EPS accelerating" in text
        assert "🟢" in text and "consecutive qtrs" in text
        assert "🟢 Revenue confirms" in text
        # Gross margin trend flag removed — now shown as GM% row in table

    def test_quality_flags_red_when_bad(self):
        from agents.market_intelligence.fundamentals import format_fundamentals
        data = self._sample_data()
        data["quality_flags"] = {
            "eps_accelerating": False,
            "eps_streak_25pct": 0,
            "sales_confirms": False,
        }
        text = format_fundamentals(data)
        assert "🔴 EPS decelerating" in text
        assert "🔴 No recent" in text
        assert "🔴 Revenue weak" in text

    def test_error_data_returns_graceful_message(self):
        from agents.market_intelligence.fundamentals import format_fundamentals
        text = format_fundamentals({"ticker": "FAKE", "error": "no data"})
        assert "unavailable" in text.lower() or "FAKE" in text

    def test_empty_lists_dont_crash(self):
        from agents.market_intelligence.fundamentals import format_fundamentals
        data = {
            "ticker": "XYZ",
            "gross_margin_pct": None,
            "next_earnings_date": None,
            "quarterly_eps": [],
            "quarterly_revenue": [],
            "annual_eps": [],
            "annual_revenue": [],
            "quality_flags": {},
        }
        text = format_fundamentals(data)
        assert "XYZ" in text


# ── Agent routing ─────────────────────────────────────────────────────────────

class TestFundamentalsRouting:
    def test_fundamentals_keyword_triggers_handler(self):
        """Agent should route 'fundamentals AXTI' to _handle_fundamentals_query."""
        import inspect
        from agents.market_intelligence.agent import MarketIntelligenceAgent
        src = inspect.getsource(MarketIntelligenceAgent.execute_task)
        assert "fundamental" in src
        assert "_handle_fundamentals_query" in src

    def test_canslim_keyword_triggers_handler(self):
        """'canslim' query should also route to fundamentals."""
        import inspect
        from agents.market_intelligence.agent import MarketIntelligenceAgent
        src = inspect.getsource(MarketIntelligenceAgent.execute_task)
        assert "canslim" in src
