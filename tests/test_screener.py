"""
Tests for the composite screener.

Covers: ScreenerFilters, run_screener logic, format_screener_results,
get_fundamentals_batch, and agent routing.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.market_intelligence.screener import (
    ScreenerFilters,
    ScreenerResult,
    format_screener_results,
    run_screener,
    _THEME_BONUS,
)
from agents.market_intelligence.fundamentals import get_fundamentals_batch


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_leader(ticker: str, rs: float, rank: int, sector: str | None = None) -> dict:
    return {"ticker": ticker, "rs_composite": rs, "rs_rank": rank, "sector": sector}


def _make_fund(ticker: str, eps_yoy: list[float | None], rev_yoy: list[float | None],
               accelerating: bool | None = None, sales_confirms: bool | None = None,
               streak: int = 0, gm_pct: float | None = None) -> dict:
    """Build a minimal fundamentals dict matching the shape from get_fundamentals."""
    q_eps = [{"period": f"Q{i+1}'24", "eps": 1.0, "yoy_pct": v} for i, v in enumerate(eps_yoy)]
    q_rev = [{"period": f"Q{i+1}'24", "revenue_m": 100.0, "yoy_pct": v} for i, v in enumerate(rev_yoy)]
    return {
        "ticker": ticker,
        "quarterly_eps": q_eps,
        "quarterly_revenue": q_rev,
        "quarterly_gross_margin": [],
        "gross_margin_pct": gm_pct,
        "annual_eps": [],
        "annual_revenue": [],
        "next_earnings_date": None,
        "quality_flags": {
            "eps_accelerating": accelerating,
            "eps_streak_25pct": streak,
            "sales_confirms": sales_confirms,
            "gross_margin_trend": "stable",
        },
    }


def _make_theme(name: str, stage: str, tickers: list[str]) -> dict:
    return {"name": name, "stage": stage, "tickers": tickers, "score": 80.0}


# ── ScreenerFilters defaults ───────────────────────────────────────────────────

class TestScreenerFilters:
    def test_defaults(self):
        f = ScreenerFilters()
        assert f.min_rs == 60.0
        assert f.min_eps_yoy_pct is None
        assert f.min_rev_yoy_pct is None
        assert f.require_acceleration is False
        assert f.require_sales_confirms is False
        assert f.theme_stage is None
        assert f.max_results == 20

    def test_custom(self):
        f = ScreenerFilters(min_rs=70, min_eps_yoy_pct=25, require_acceleration=True, max_results=10)
        assert f.min_rs == 70
        assert f.min_eps_yoy_pct == 25
        assert f.require_acceleration is True
        assert f.max_results == 10


# ── _THEME_BONUS values ────────────────────────────────────────────────────────

class TestThemeBonus:
    def test_accelerating_highest(self):
        assert _THEME_BONUS["Accelerating"] > _THEME_BONUS["Nascent"]
        assert _THEME_BONUS["Nascent"] > _THEME_BONUS["Mainstream"]
        assert _THEME_BONUS["Fading"] == 0.0

    def test_all_stages_present(self):
        for stage in ["Accelerating", "Nascent", "Mainstream", "Fading"]:
            assert stage in _THEME_BONUS


# ── run_screener ───────────────────────────────────────────────────────────────

LEADERS = [
    _make_leader("AXTI", 85.0, 1, "Technology"),
    _make_leader("AAOI", 78.0, 2, "Technology"),
    _make_leader("CIEN", 72.0, 3, "Technology"),
    _make_leader("LOW_RS", 55.0, 4, "Retail"),   # below default min_rs=60
]

THEMES = [
    _make_theme("Optical Networking", "Accelerating", ["AXTI", "AAOI"]),
    _make_theme("Legacy Retail", "Fading", ["LOW_RS"]),
]

FUND_MAP = {
    "AXTI": _make_fund("AXTI", [30.0, 40.0, 50.0, 55.0], [20.0, 25.0, 30.0, 35.0],
                       accelerating=True, sales_confirms=True, streak=4, gm_pct=42.0),
    "AAOI": _make_fund("AAOI", [10.0, 15.0, 20.0, 30.0], [5.0, 10.0, 12.0, 20.0],
                       accelerating=True, sales_confirms=False, streak=1, gm_pct=35.0),
    "CIEN": _make_fund("CIEN", [5.0, 8.0, 10.0, -5.0], [10.0, 12.0, 14.0, 10.0],
                       accelerating=False, sales_confirms=False, streak=0, gm_pct=50.0),
}


def _patch_screener_deps(leaders=LEADERS, themes=THEMES, fund_map=FUND_MAP):
    """Context manager patching all external deps for screener tests."""
    import contextlib

    @contextlib.asynccontextmanager
    async def _ctx():
        with (
            patch("agents.market_intelligence.screener.get_rs_leaders",
                  new=AsyncMock(return_value=leaders)),
            patch("agents.market_intelligence.screener.get_today_themes",
                  new=AsyncMock(return_value=themes)),
            patch("agents.market_intelligence.screener.get_fundamentals_batch",
                  new=AsyncMock(return_value=fund_map)),
        ):
            yield

    return _ctx()


class TestRunScreener:
    def test_returns_list(self):
        async def _run():
            async with _patch_screener_deps():
                return await run_screener(ScreenerFilters())
        results = asyncio.run(_run())
        assert isinstance(results, list)

    def test_excludes_below_min_rs(self):
        async def _run():
            async with _patch_screener_deps():
                return await run_screener(ScreenerFilters(min_rs=60))
        results = asyncio.run(_run())
        tickers = [r.ticker for r in results]
        assert "LOW_RS" not in tickers

    def test_sorted_by_composite_score_descending(self):
        async def _run():
            async with _patch_screener_deps():
                return await run_screener(ScreenerFilters(min_rs=60))
        results = asyncio.run(_run())
        scores = [r.composite_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_axti_has_highest_score(self):
        """AXTI: highest RS + Accelerating theme bonus + high EPS bonus + accel bonus."""
        async def _run():
            async with _patch_screener_deps():
                return await run_screener(ScreenerFilters(min_rs=60))
        results = asyncio.run(_run())
        assert results[0].ticker == "AXTI"

    def test_composite_score_formula(self):
        """AXTI: 85 RS + 15 (Accelerating) + 10 (EPS≥50%) + 5 (accel) = 115."""
        async def _run():
            async with _patch_screener_deps():
                return await run_screener(ScreenerFilters(min_rs=60))
        results = asyncio.run(_run())
        axti = next(r for r in results if r.ticker == "AXTI")
        assert axti.composite_score == 85.0 + 15.0 + 10.0 + 5.0  # 115

    def test_theme_bonus_applied(self):
        async def _run():
            async with _patch_screener_deps():
                return await run_screener(ScreenerFilters(min_rs=60))
        results = asyncio.run(_run())
        axti = next(r for r in results if r.ticker == "AXTI")
        assert axti.theme_bonus == 15.0  # Accelerating
        assert axti.theme_name == "Optical Networking"

    def test_no_theme_zero_bonus(self):
        leaders_no_theme = [_make_leader("SOLO", 75.0, 1)]
        fund_solo = {"SOLO": _make_fund("SOLO", [20.0, 25.0], [10.0, 15.0],
                                        accelerating=True, sales_confirms=True)}

        async def _run():
            async with _patch_screener_deps(
                leaders=leaders_no_theme, themes=[], fund_map=fund_solo
            ):
                return await run_screener(ScreenerFilters(min_rs=60))
        results = asyncio.run(_run())
        assert results[0].theme_bonus == 0.0
        assert results[0].theme_name is None

    def test_min_eps_yoy_filter(self):
        """CIEN has latest EPS YoY = -5% — should be excluded with min_eps_yoy_pct=0."""
        async def _run():
            async with _patch_screener_deps():
                return await run_screener(ScreenerFilters(min_rs=60, min_eps_yoy_pct=0))
        results = asyncio.run(_run())
        tickers = [r.ticker for r in results]
        assert "CIEN" not in tickers

    def test_min_rev_yoy_filter(self):
        """AAOI has latest Rev YoY = 20% — should pass ≥15 but fail ≥25."""
        async def _run():
            async with _patch_screener_deps():
                return await run_screener(ScreenerFilters(min_rs=60, min_rev_yoy_pct=25))
        results = asyncio.run(_run())
        tickers = [r.ticker for r in results]
        assert "AAOI" not in tickers

    def test_require_acceleration_filter(self):
        """CIEN has eps_accelerating=False — excluded when require_acceleration=True."""
        async def _run():
            async with _patch_screener_deps():
                return await run_screener(ScreenerFilters(min_rs=60, require_acceleration=True))
        results = asyncio.run(_run())
        tickers = [r.ticker for r in results]
        assert "CIEN" not in tickers
        assert "AXTI" in tickers

    def test_require_sales_confirms_filter(self):
        """AAOI has sales_confirms=False — excluded when require_sales_confirms=True."""
        async def _run():
            async with _patch_screener_deps():
                return await run_screener(ScreenerFilters(min_rs=60, require_sales_confirms=True))
        results = asyncio.run(_run())
        tickers = [r.ticker for r in results]
        assert "AAOI" not in tickers
        assert "AXTI" in tickers

    def test_theme_stage_filter(self):
        """Only Accelerating theme stocks: AXTI, AAOI. CIEN (no theme) excluded."""
        async def _run():
            async with _patch_screener_deps():
                return await run_screener(ScreenerFilters(min_rs=60, theme_stage="Accelerating"))
        results = asyncio.run(_run())
        tickers = [r.ticker for r in results]
        assert "CIEN" not in tickers
        assert all(t in ("AXTI", "AAOI") for t in tickers)

    def test_max_results_respected(self):
        async def _run():
            async with _patch_screener_deps():
                return await run_screener(ScreenerFilters(min_rs=60, max_results=1))
        results = asyncio.run(_run())
        assert len(results) <= 1

    def test_empty_when_no_leaders(self):
        async def _run():
            async with _patch_screener_deps(leaders=[], fund_map={}):
                return await run_screener(ScreenerFilters())
        results = asyncio.run(_run())
        assert results == []

    def test_multi_theme_ticker_keeps_highest_bonus(self):
        """Ticker in both Nascent and Accelerating themes should get Accelerating bonus."""
        themes = [
            _make_theme("Theme A", "Nascent", ["AXTI"]),
            _make_theme("Theme B", "Accelerating", ["AXTI"]),
        ]
        async def _run():
            async with _patch_screener_deps(themes=themes):
                return await run_screener(ScreenerFilters(min_rs=60))
        results = asyncio.run(_run())
        axti = next((r for r in results if r.ticker == "AXTI"), None)
        assert axti is not None
        assert axti.theme_stage == "Accelerating"
        assert axti.theme_bonus == 15.0


# ── EPS bonus tiers ───────────────────────────────────────────────────────────

class TestEpsBonusTiers:
    def _run_with_eps(self, eps_yoy: float) -> ScreenerResult | None:
        leaders = [_make_leader("X", 70.0, 1)]
        fund = {"X": _make_fund("X", [eps_yoy], [20.0], accelerating=False)}

        async def _run():
            async with _patch_screener_deps(leaders=leaders, themes=[], fund_map=fund):
                return await run_screener(ScreenerFilters(min_rs=60))
        results = asyncio.run(_run())
        return results[0] if results else None

    def test_eps_bonus_tier_50(self):
        r = self._run_with_eps(55.0)
        assert r is not None and r.eps_bonus == 10.0

    def test_eps_bonus_tier_25(self):
        r = self._run_with_eps(30.0)
        assert r is not None and r.eps_bonus == 5.0

    def test_eps_bonus_tier_0(self):
        r = self._run_with_eps(10.0)
        assert r is not None and r.eps_bonus == 2.0

    def test_eps_bonus_negative(self):
        r = self._run_with_eps(-5.0)
        assert r is not None and r.eps_bonus == 0.0


# ── format_screener_results ────────────────────────────────────────────────────

class TestFormatScreenerResults:
    def _make_result(self, ticker="AXTI", rs=85.0, rank=1, composite=115.0,
                     eps_yoy=55.0, rev_yoy=30.0, accelerating=True,
                     theme_name="Optical Networking", theme_stage="Accelerating",
                     theme_bonus=15.0, eps_bonus=10.0, accel_bonus=5.0) -> ScreenerResult:
        return ScreenerResult(
            ticker=ticker, rs_composite=rs, rs_rank=rank, sector="Technology",
            composite_score=composite, theme_name=theme_name, theme_stage=theme_stage,
            theme_bonus=theme_bonus, latest_eps_yoy=eps_yoy, latest_rev_yoy=rev_yoy,
            eps_accelerating=accelerating, eps_streak_25pct=4, eps_bonus=eps_bonus,
            accel_bonus=accel_bonus, next_earnings_date="2026-05-01", gross_margin_pct=42.0,
        )

    def test_empty_results(self):
        text = format_screener_results([], ScreenerFilters())
        assert "No stocks" in text

    def test_header_contains_min_rs(self):
        r = self._make_result()
        text = format_screener_results([r], ScreenerFilters(min_rs=70))
        assert "RS ≥ 70" in text

    def test_header_contains_eps_filter(self):
        r = self._make_result()
        text = format_screener_results([r], ScreenerFilters(min_eps_yoy_pct=25))
        assert "EPS YoY ≥ 25%" in text

    def test_ticker_in_output(self):
        r = self._make_result()
        text = format_screener_results([r], ScreenerFilters())
        assert "AXTI" in text

    def test_composite_score_shown(self):
        r = self._make_result(composite=115.0)
        text = format_screener_results([r], ScreenerFilters())
        assert "115" in text

    def test_eps_yoy_shown(self):
        r = self._make_result(eps_yoy=55.0)
        text = format_screener_results([r], ScreenerFilters())
        assert "+55%" in text

    def test_accel_emoji_shown(self):
        r = self._make_result(accelerating=True)
        text = format_screener_results([r], ScreenerFilters())
        assert "⚡" in text

    def test_no_accel_emoji_when_false(self):
        r = self._make_result(accelerating=False)
        text = format_screener_results([r], ScreenerFilters())
        assert "⚡" not in text

    def test_result_count_shown(self):
        results = [self._make_result("AXTI"), self._make_result("AAOI", rank=2, composite=100.0)]
        text = format_screener_results(results, ScreenerFilters())
        assert "2 results" in text

    def test_none_eps_shows_na(self):
        r = self._make_result(eps_yoy=None)
        text = format_screener_results([r], ScreenerFilters())
        assert "n/a" in text


# ── get_fundamentals_batch ────────────────────────────────────────────────────

class TestGetFundamentalsBatch:
    def test_returns_dict_keyed_by_upper_ticker(self):
        async def _run():
            with patch(
                "agents.market_intelligence.fundamentals.get_fundamentals",
                new=AsyncMock(side_effect=lambda t: {"ticker": t.upper()}),
            ):
                return await get_fundamentals_batch(["axti", "cien"])
        result = asyncio.run(_run())
        assert "AXTI" in result
        assert "CIEN" in result

    def test_exception_returns_error_entry(self):
        async def _run():
            with patch(
                "agents.market_intelligence.fundamentals.get_fundamentals",
                new=AsyncMock(side_effect=RuntimeError("yfinance down")),
            ):
                return await get_fundamentals_batch(["FAIL"])
        result = asyncio.run(_run())
        assert "error" in result["FAIL"]

    def test_concurrency_semaphore_respected(self):
        """Verify all tickers are returned even with concurrency=2."""
        tickers = ["A", "B", "C", "D", "E"]

        async def _run():
            with patch(
                "agents.market_intelligence.fundamentals.get_fundamentals",
                new=AsyncMock(side_effect=lambda t: {"ticker": t}),
            ):
                return await get_fundamentals_batch(tickers, concurrency=2)
        result = asyncio.run(_run())
        assert set(result.keys()) == set(tickers)


# ── Screener routing in agent ─────────────────────────────────────────────────

class TestScreenerRouting:
    """Inspect execute_task source to verify screener keyword routing."""

    def _src(self):
        import inspect
        from agents.market_intelligence.agent import MarketIntelligenceAgent
        return inspect.getsource(MarketIntelligenceAgent.execute_task)

    @pytest.mark.parametrize("keyword", [
        "screener",
        "screen for",
        "find top",
        "best stocks with",
        "filter stocks",
        "composite score",
        "quality stocks",
        "fundamental stocks",
    ])
    def test_screener_keyword_present_in_execute_task(self, keyword):
        src = self._src()
        assert keyword in src, f"Keyword '{keyword}' missing from execute_task routing"

    def test_handle_screener_query_called_on_route(self):
        src = self._src()
        assert "_handle_screener_query" in src
