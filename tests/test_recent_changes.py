"""
Tests for recent changes:
- get_premarket_futures() in collector.py
- _format_morning_briefing() futures line in briefing.py
- _safe() module-level extraction in telegram.py
- RISKY_REGIMES module-level constant in orchestrator.py
- asyncio.gather() usage in briefing (structural check)
"""
import asyncio
import inspect
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── collector: get_premarket_futures ─────────────────────────────────────────

class TestGetPremarketFutures:
    def test_returns_pct_when_data_available(self):
        """Should compute % change correctly from last_price / previous_close."""
        from agents.market_intelligence.collector import get_premarket_futures

        def make_fast_info(last, prev):
            fi = MagicMock()
            fi.last_price = last
            fi.previous_close = prev
            return fi

        with patch("yfinance.Ticker") as mock_ticker:
            def ticker_side_effect(symbol):
                t = MagicMock()
                if symbol == "ES=F":
                    t.fast_info = make_fast_info(5100.0, 5000.0)
                elif symbol == "NQ=F":
                    t.fast_info = make_fast_info(17820.0, 18000.0)
                return t
            mock_ticker.side_effect = ticker_side_effect

            result = asyncio.run(get_premarket_futures())

        assert "es_pct" in result
        assert "nq_pct" in result
        assert abs(result["es_pct"] - 2.0) < 0.01    # (5100-5000)/5000*100
        assert abs(result["nq_pct"] - (-1.0)) < 0.01  # (17820-18000)/18000*100

    def test_returns_empty_dict_on_exception(self):
        """Should fail gracefully and return {} — never crash the briefing."""
        from agents.market_intelligence.collector import get_premarket_futures

        with patch("yfinance.Ticker", side_effect=RuntimeError("network error")):
            result = asyncio.run(get_premarket_futures())

        assert result == {}

    def test_skips_entry_when_price_missing(self):
        """If previous_close is None, that symbol should be omitted."""
        from agents.market_intelligence.collector import get_premarket_futures

        def make_fast_info(last, prev):
            fi = MagicMock()
            fi.last_price = last
            fi.previous_close = prev
            return fi

        with patch("yfinance.Ticker") as mock_ticker:
            def ticker_side_effect(symbol):
                t = MagicMock()
                if symbol == "ES=F":
                    t.fast_info = make_fast_info(5100.0, None)  # missing prev
                elif symbol == "NQ=F":
                    t.fast_info = make_fast_info(17820.0, 18000.0)
                return t
            mock_ticker.side_effect = ticker_side_effect

            result = asyncio.run(get_premarket_futures())

        assert "es_pct" not in result
        assert "nq_pct" in result


# ── briefing: _format_morning_briefing with futures ──────────────────────────

class TestFormatMorningBriefing:
    def _regime(self, label="Bull", vix=14.5, ep_thresh=70):
        return {"regime": label, "vix": vix, "ep_threshold": ep_thresh}

    def test_futures_line_present_when_data_available(self):
        from agents.market_intelligence.briefing import _format_morning_briefing
        text = _format_morning_briefing(
            regime=self._regime(),
            ep_alerts=[],
            briefing_date="2026-03-14",
            futures={"es_pct": 0.3, "nq_pct": -0.8},
        )
        assert "Futures:" in text
        assert "ES" in text
        assert "NQ" in text
        assert "+0.3%" in text
        assert "-0.8%" in text

    def test_futures_line_absent_when_empty_dict(self):
        from agents.market_intelligence.briefing import _format_morning_briefing
        text = _format_morning_briefing(
            regime=self._regime(),
            ep_alerts=[],
            briefing_date="2026-03-14",
            futures={},
        )
        assert "Futures:" not in text

    def test_futures_line_absent_when_none(self):
        from agents.market_intelligence.briefing import _format_morning_briefing
        text = _format_morning_briefing(
            regime=self._regime(),
            ep_alerts=[],
            briefing_date="2026-03-14",
            futures=None,
        )
        assert "Futures:" not in text

    def test_only_es_shown_when_nq_missing(self):
        from agents.market_intelligence.briefing import _format_morning_briefing
        text = _format_morning_briefing(
            regime=self._regime(),
            ep_alerts=[],
            briefing_date="2026-03-14",
            futures={"es_pct": 1.2},
        )
        assert "ES" in text
        assert "NQ" not in text

    def test_regime_line_present(self):
        from agents.market_intelligence.briefing import _format_morning_briefing
        text = _format_morning_briefing(
            regime=self._regime(label="Choppy", vix=22.0, ep_thresh=80),
            ep_alerts=[],
            briefing_date="2026-03-14",
        )
        assert "Choppy" in text
        assert "VIX 22.0" in text
        assert "≥80" in text

    def test_ep_section_included(self):
        from agents.market_intelligence.briefing import _format_morning_briefing
        ep = {
            "ticker": "AXTI",
            "gap_pct": 8.2,
            "ep_score": 87,
            "score_tier": "HIGH",
            "rel_volume": 4.3,
            "catalyst_quality": "strong",
        }
        text = _format_morning_briefing(
            regime=self._regime(),
            ep_alerts=[ep],
            briefing_date="2026-03-14",
        )
        assert "AXTI" in text
        assert "EP ALERTS" in text


# ── telegram: _safe() is module-level ────────────────────────────────────────

class TestSafeModuleLevel:
    def test_safe_is_module_level(self):
        """_safe() should be a module-level function, not nested inside a method."""
        import channels.telegram as tg_module
        assert hasattr(tg_module, "_safe"), "_safe() must be defined at module level"
        assert callable(tg_module._safe)

    def test_safe_strips_markdown(self):
        from channels.telegram import _safe
        assert _safe("hello *world*") == "hello world"
        assert _safe("`code` _italic_") == "code italic"
        assert _safe("no [link] here") == "no link here"

    def test_safe_leaves_plain_text_unchanged(self):
        from channels.telegram import _safe
        assert _safe("connection refused") == "connection refused"


# ── orchestrator: RISKY_REGIMES is module-level ───────────────────────────────

class TestRiskyRegimesModuleLevel:
    def test_risky_regimes_defined_at_module_level(self):
        import core.orchestrator as orch
        assert hasattr(orch, "RISKY_REGIMES"), "RISKY_REGIMES must be at module level"
        assert isinstance(orch.RISKY_REGIMES, (set, frozenset))
        assert "Choppy" in orch.RISKY_REGIMES
        assert "Correcting" in orch.RISKY_REGIMES
        assert "Crisis" in orch.RISKY_REGIMES
        assert "Bull" not in orch.RISKY_REGIMES

    def test_httpx_imported_at_module_level(self):
        """httpx should be a top-level import, not inside a function body."""
        import core.orchestrator as orch
        assert hasattr(orch, "httpx"), "httpx must be imported at module level in orchestrator.py"


# ── briefing: asyncio.gather() used (structural) ─────────────────────────────

class TestBriefingUsesGather:
    def test_send_evening_briefing_uses_gather(self):
        """gather() call should appear in the source of send_evening_briefing."""
        from agents.market_intelligence import briefing
        src = inspect.getsource(briefing.send_evening_briefing)
        assert "asyncio.gather" in src

    def test_send_morning_briefing_uses_gather(self):
        from agents.market_intelligence import briefing
        src = inspect.getsource(briefing.send_morning_briefing)
        assert "asyncio.gather" in src

    def test_morning_gather_includes_futures(self):
        """The morning gather should include get_premarket_futures."""
        from agents.market_intelligence import briefing
        src = inspect.getsource(briefing.send_morning_briefing)
        assert "get_premarket_futures" in src
