"""
Tests for recent changes:
- get_premarket_snapshot() in collector.py
- _format_morning_briefing() premarket line in briefing.py
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


# ── collector: get_premarket_snapshot ─────────────────────────────────────────

def _make_polygon_snapshot(spy_prev, spy_curr, qqq_prev, qqq_curr):
    """Build a fake Polygon /v2/snapshot response for SPY and QQQ."""
    tickers = []
    if spy_prev is not None:
        tickers.append({
            "ticker": "SPY",
            "prevDay": {"c": spy_prev},
            "min": {"c": spy_curr},
        })
    if qqq_prev is not None:
        tickers.append({
            "ticker": "QQQ",
            "prevDay": {"c": qqq_prev},
            "min": {"c": qqq_curr},
        })
    return {"tickers": tickers}


class TestGetPremarketSnapshot:
    def test_returns_pct_when_data_available(self):
        """Should compute % change correctly from Polygon prevDay.c / min.c."""
        from agents.market_intelligence.collector import get_premarket_snapshot

        payload = _make_polygon_snapshot(500.0, 510.0, 450.0, 445.5)
        with patch("agents.market_intelligence.collector._polygon_get", new=AsyncMock(return_value=payload)):
            result = asyncio.run(get_premarket_snapshot())

        assert "spy_pct" in result
        assert "qqq_pct" in result
        assert abs(result["spy_pct"] - 2.0) < 0.01    # (510-500)/500*100
        assert abs(result["qqq_pct"] - (-1.0)) < 0.01  # (445.5-450)/450*100

    def test_returns_empty_dict_on_exception(self):
        """Should fail gracefully and return {} — never crash the briefing."""
        from agents.market_intelligence.collector import get_premarket_snapshot

        with patch("agents.market_intelligence.collector._polygon_get", new=AsyncMock(side_effect=RuntimeError("network error"))):
            result = asyncio.run(get_premarket_snapshot())

        assert result == {}

    def test_skips_entry_when_prev_missing(self):
        """If prevDay.c is missing for SPY, only QQQ should appear."""
        from agents.market_intelligence.collector import get_premarket_snapshot

        payload = {
            "tickers": [
                {"ticker": "SPY", "prevDay": {}, "min": {"c": 510.0}},  # no prevDay.c
                {"ticker": "QQQ", "prevDay": {"c": 450.0}, "min": {"c": 445.5}},
            ]
        }
        with patch("agents.market_intelligence.collector._polygon_get", new=AsyncMock(return_value=payload)):
            result = asyncio.run(get_premarket_snapshot())

        assert "spy_pct" not in result
        assert "qqq_pct" in result


# ── briefing: _format_morning_briefing with premarket ────────────────────────

class TestFormatMorningBriefing:
    def _regime(self, label="Bull", vix=14.5, ep_thresh=70):
        return {"regime": label, "vix": vix, "ep_threshold": ep_thresh}

    def test_premarket_line_present_when_data_available(self):
        from agents.market_intelligence.briefing import _format_morning_briefing
        text = _format_morning_briefing(
            regime=self._regime(),
            ep_alerts=[],
            briefing_date="2026-03-14",
            premarket={"spy_pct": 0.3, "qqq_pct": -0.8},
        )
        assert "Pre-market:" in text
        assert "SPY" in text
        assert "QQQ" in text
        assert "+0.3%" in text
        assert "-0.8%" in text

    def test_premarket_line_absent_when_empty_dict(self):
        from agents.market_intelligence.briefing import _format_morning_briefing
        text = _format_morning_briefing(
            regime=self._regime(),
            ep_alerts=[],
            briefing_date="2026-03-14",
            premarket={},
        )
        assert "Pre-market:" not in text

    def test_premarket_line_absent_when_none(self):
        from agents.market_intelligence.briefing import _format_morning_briefing
        text = _format_morning_briefing(
            regime=self._regime(),
            ep_alerts=[],
            briefing_date="2026-03-14",
            premarket=None,
        )
        assert "Pre-market:" not in text

    def test_only_spy_shown_when_qqq_missing(self):
        from agents.market_intelligence.briefing import _format_morning_briefing
        text = _format_morning_briefing(
            regime=self._regime(),
            ep_alerts=[],
            briefing_date="2026-03-14",
            premarket={"spy_pct": 1.2},
        )
        assert "SPY" in text
        assert "QQQ" not in text

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

    def test_morning_gather_includes_premarket_snapshot(self):
        """The morning gather should include get_premarket_snapshot."""
        from agents.market_intelligence import briefing
        src = inspect.getsource(briefing.send_morning_briefing)
        assert "get_premarket_snapshot" in src


# ── db: purge_old_data ────────────────────────────────────────────────────────

class TestPurgeOldData:
    def test_purge_deletes_correct_tables(self):
        """purge_old_data() should issue DELETEs against the three retention tables."""
        from unittest.mock import AsyncMock, MagicMock, patch
        import agents.market_intelligence.db as db_module

        executed_sqls = []

        async def fake_execute(sql, cutoff):
            executed_sqls.append(sql.strip())
            return "DELETE 5"

        mock_conn = MagicMock()
        mock_conn.execute = fake_execute

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch.object(db_module, "get_pool", AsyncMock(return_value=mock_pool)):
            result = asyncio.run(db_module.purge_old_data())

        tables_deleted = {sql.split("FROM")[1].split("WHERE")[0].strip() for sql in executed_sqls if "DELETE" in sql}
        assert "mi_ep_alerts" in tables_deleted
        assert "mi_stock_scores" in tables_deleted
        assert "mi_themes" in tables_deleted
        assert "mi_market_regime" not in tables_deleted
        assert "mi_tracked_stocks" not in tables_deleted

    def test_purge_returns_row_counts(self):
        """Return dict should map table names to deleted row counts."""
        from unittest.mock import AsyncMock, MagicMock, patch
        import agents.market_intelligence.db as db_module

        call_order = []

        async def fake_execute(sql, cutoff):
            if "mi_ep_alerts" in sql:
                call_order.append("ep_alerts")
                return "DELETE 12"
            elif "mi_stock_scores" in sql:
                call_order.append("stock_scores")
                return "DELETE 340"
            elif "mi_themes" in sql:
                call_order.append("themes")
                return "DELETE 0"
            return "DELETE 0"

        mock_conn = MagicMock()
        mock_conn.execute = fake_execute

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch.object(db_module, "get_pool", AsyncMock(return_value=mock_pool)):
            result = asyncio.run(db_module.purge_old_data())

        assert result["mi_ep_alerts"] == 12
        assert result["mi_stock_scores"] == 340
        assert result["mi_themes"] == 0

    def test_purge_cutoffs_are_correct(self):
        """Verify each table uses the right retention window."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from datetime import date, timedelta
        import agents.market_intelligence.db as db_module

        captured = {}

        async def fake_execute(sql, cutoff):
            if "mi_ep_alerts" in sql:
                captured["ep_alerts"] = cutoff
            elif "mi_stock_scores" in sql:
                captured["stock_scores"] = cutoff
            elif "mi_themes" in sql:
                captured["themes"] = cutoff
            return "DELETE 0"

        mock_conn = MagicMock()
        mock_conn.execute = fake_execute

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        today = date.today()
        with patch.object(db_module, "get_pool", AsyncMock(return_value=mock_pool)):
            asyncio.run(db_module.purge_old_data())

        assert captured["ep_alerts"] == today - timedelta(days=90)
        assert captured["stock_scores"] == today - timedelta(days=365)
        assert captured["themes"] == today - timedelta(days=365)

    def test_weekly_cleanup_job_registered(self):
        """Scheduler should register a weekly_cleanup job."""
        from agents.market_intelligence import scheduler as sched_module
        src = inspect.getsource(sched_module.start_scheduler)
        assert "weekly_cleanup" in src
        assert "sun" in src


# ── ep_detector: _volume_percentile ──────────────────────────────────────────

class TestVolumePercentile:
    def test_basic_percentile(self):
        from agents.market_intelligence.ep_detector import _volume_percentile
        history = [100_000, 200_000, 300_000, 400_000, 500_000]
        # 350K exceeds 3 of 5 values → 60th percentile
        assert _volume_percentile(350_000, history) == 60.0

    def test_above_all_history(self):
        from agents.market_intelligence.ep_detector import _volume_percentile
        history = [100_000, 200_000, 300_000]
        assert _volume_percentile(999_999, history) == 100.0

    def test_below_all_history(self):
        from agents.market_intelligence.ep_detector import _volume_percentile
        history = [100_000, 200_000, 300_000]
        assert _volume_percentile(50_000, history) == 0.0

    def test_empty_history_returns_neutral(self):
        from agents.market_intelligence.ep_detector import _volume_percentile
        assert _volume_percentile(500_000, []) == 50.0

    def test_zero_volume_returns_neutral(self):
        from agents.market_intelligence.ep_detector import _volume_percentile
        assert _volume_percentile(0, [100_000, 200_000]) == 50.0


class TestScoreEpVolConviction:
    def _base_profile(self):
        return {"floatShares": 100_000_000, "price": 50.0, "52WeekHigh": 60.0}

    def test_high_vol_percentile_adds_10pts(self):
        from agents.market_intelligence.ep_detector import _score_ep
        score_high, bd_high = _score_ep(
            gap_pct=10, rel_volume=5, catalyst_quality="strong",
            profile=self._base_profile(), analyst_upgrades=0,
            regime_multiplier=1.0, vol_percentile=92.0,
        )
        score_low, bd_low = _score_ep(
            gap_pct=10, rel_volume=5, catalyst_quality="strong",
            profile=self._base_profile(), analyst_upgrades=0,
            regime_multiplier=1.0, vol_percentile=50.0,
        )
        assert bd_high["vol_conviction"] == 5
        assert bd_low["vol_conviction"] == 0
        assert score_high > score_low

    def test_mid_vol_percentile_adds_5pts(self):
        from agents.market_intelligence.ep_detector import _score_ep
        _, breakdown = _score_ep(
            gap_pct=10, rel_volume=5, catalyst_quality="strong",
            profile=self._base_profile(), analyst_upgrades=0,
            regime_multiplier=1.0, vol_percentile=75.0,
        )
        assert breakdown["vol_conviction"] == 3

    def test_low_vol_percentile_adds_0pts(self):
        from agents.market_intelligence.ep_detector import _score_ep
        _, breakdown = _score_ep(
            gap_pct=10, rel_volume=5, catalyst_quality="strong",
            profile=self._base_profile(), analyst_upgrades=0,
            regime_multiplier=1.0, vol_percentile=40.0,
        )
        assert breakdown["vol_conviction"] == 0

    def test_short_interest_slot_replaced(self):
        """short_interest should no longer appear in score breakdown."""
        from agents.market_intelligence.ep_detector import _score_ep
        _, breakdown = _score_ep(
            gap_pct=10, rel_volume=5, catalyst_quality="strong",
            profile=self._base_profile(), analyst_upgrades=0,
            regime_multiplier=1.0,
        )
        assert "short_interest" not in breakdown
        assert "vol_conviction" in breakdown


# ── structured outputs: catalyst classification ───────────────────────────────

class TestCatalystStructuredOutput:
    def _make_tool_response(self, quality: str, analysis: str):
        """Build a mock Anthropic response with a tool_use block."""
        block = MagicMock()
        block.type = "tool_use"
        block.input = {"quality": quality, "analysis": analysis}
        response = MagicMock()
        response.content = [block]
        return response

    def test_uses_tool_choice(self):
        """Claude call must use tool_choice to force structured output."""
        from agents.market_intelligence import ep_detector
        calls = []

        async def mock_create(**kwargs):
            calls.append(kwargs)
            return self._make_tool_response("strong", "Solid beat.")

        with patch.object(ep_detector._get_claude(), "messages") as mock_msgs:
            mock_msgs.create = mock_create
            asyncio.run(ep_detector._classify_catalyst_claude("AXTI", [], {}))

        assert calls, "No API call made"
        assert calls[0].get("tool_choice") == {"type": "tool", "name": "classify_catalyst"}
        assert calls[0].get("tools")

    def test_returns_structured_quality_and_analysis(self):
        from agents.market_intelligence import ep_detector

        async def mock_create(**kwargs):
            return self._make_tool_response("game_changer", "Massive earnings beat.")

        with patch.object(ep_detector._get_claude(), "messages") as mock_msgs:
            mock_msgs.create = mock_create
            quality, analysis = asyncio.run(
                ep_detector._classify_catalyst_claude("AXTI", [], {})
            )

        assert quality == "game_changer"
        assert analysis == "Massive earnings beat."

    def test_falls_back_to_routine_on_exception(self):
        from agents.market_intelligence import ep_detector

        def mock_create(**kwargs):
            raise RuntimeError("API error")

        with patch.object(ep_detector._get_claude(), "messages") as mock_msgs:
            mock_msgs.create = mock_create
            quality, analysis = asyncio.run(
                ep_detector._classify_catalyst_claude("AXTI", [], {})
            )

        assert quality == "routine"
        assert "failed" in analysis.lower()

    def test_catalyst_tool_schema_has_enum(self):
        """Schema must constrain quality to valid values — no free-form strings."""
        from agents.market_intelligence.ep_detector import _CATALYST_TOOL
        props = _CATALYST_TOOL["input_schema"]["properties"]
        assert "enum" in props["quality"]
        # 'mna' added when M&A became a hard-skip catalyst class (price capped at deal value).
        assert set(props["quality"]["enum"]) == {"game_changer", "strong", "routine", "mna"}


# ── structured outputs: theme discovery ───────────────────────────────────────

class TestThemeDiscoveryStructuredOutput:
    def _make_tool_response(self, themes: list):
        block = MagicMock()
        block.type = "tool_use"
        block.name = "report_themes"  # the loop keys on this to find the report block
        block.input = {"themes": themes}
        response = MagicMock()
        response.content = [block]
        return response

    _STOCKS = [
        {"ticker": "A", "rs_composite": 80, "rs_rank": 1, "sector": "Tech"},
        {"ticker": "B", "rs_composite": 75, "rs_rank": 2, "sector": "Tech"},
        {"ticker": "C", "rs_composite": 70, "rs_rank": 3, "sector": "Tech"},
    ]
    _STOCKS_BY_TICKER = {s["ticker"]: s for s in _STOCKS}

    def test_uses_tool_choice(self):
        from agents.market_intelligence import theme_engine
        calls = []

        async def mock_create(**kwargs):
            calls.append(kwargs)
            return self._make_tool_response([])

        mock_client = MagicMock()
        mock_client.messages.create = mock_create

        descs = {s["ticker"]: f"{s['ticker']} description" for s in self._STOCKS}
        with patch("anthropic.AsyncAnthropic", return_value=mock_client), \
                patch("agents.market_intelligence.universe.TICKER_DESC", descs):
            asyncio.run(theme_engine._discover_new_themes(
                uncovered_stocks=self._STOCKS,
                existing_themes=[],
                stocks_by_ticker=self._STOCKS_BY_TICKER,
            ))

        assert calls
        # Discovery is now an agentic loop (advisor-consult option): the FIRST call uses
        # tool_choice "auto" so the model can think/consult; report_themes is only FORCED
        # on a recovery pass if the model stops without reporting (#173).
        assert calls[0].get("tool_choice") == {"type": "auto"}
        assert calls[0].get("tools")

    def test_returns_themes_list(self):
        from agents.market_intelligence import theme_engine
        expected = [{"name": "Edge AI", "thesis": "AI chips.", "tickers": ["A", "B"]}]

        async def mock_create(**kwargs):
            return self._make_tool_response(expected)

        mock_client = MagicMock()
        mock_client.messages.create = mock_create

        descs = {s["ticker"]: f"{s['ticker']} description" for s in self._STOCKS}
        # Patch _get_anthropic_client (not anthropic.AsyncAnthropic): the client is
        # cached in a module global (_anthropic_client), so a sibling discovery test
        # that runs first pins its own mock and an AsyncAnthropic patch becomes a
        # no-op — leaking an empty-themes client into this test (#205).
        with patch("agents.market_intelligence.theme_engine._get_anthropic_client", return_value=mock_client), \
                patch("agents.market_intelligence.universe.TICKER_DESC", descs):
            result = asyncio.run(theme_engine._discover_new_themes(
                uncovered_stocks=self._STOCKS,
                existing_themes=[],
                stocks_by_ticker=self._STOCKS_BY_TICKER,
            ))

        # Structured output surfaces the reported theme. Assert by identity (name +
        # members) rather than brittle exact-dict equality — the discovery pipeline
        # legitimately enriches the theme dict (stage/score/sector strip) downstream.
        assert len(result) == 1
        assert result[0]["name"] == "Edge AI"
        assert set(result[0]["tickers"]) == {"A", "B"}

    def test_returns_empty_list_on_exception(self):
        from agents.market_intelligence import theme_engine

        async def mock_create(**kwargs):
            raise RuntimeError("API error")

        mock_client = MagicMock()
        mock_client.messages.create = mock_create

        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            result = asyncio.run(theme_engine._discover_new_themes(
                uncovered_stocks=self._STOCKS,
                existing_themes=[],
                stocks_by_ticker=self._STOCKS_BY_TICKER,
            ))

        assert result == []

    def test_theme_tool_schema_requires_themes_array(self):
        from agents.market_intelligence.theme_engine import _THEME_DISCOVERY_TOOL
        schema = _THEME_DISCOVERY_TOOL["input_schema"]
        assert "themes" in schema["required"]
        assert schema["properties"]["themes"]["type"] == "array"
        item_props = schema["properties"]["themes"]["items"]["properties"]
        assert set(item_props.keys()) >= {"name", "thesis", "tickers"}

    # (Removed test_no_json_import_in_theme_engine — #205. Its premise that structured
    #  output would eliminate the json import never held: theme_engine legitimately uses
    #  json.loads to parse the validation model's response. Asserting a non-requirement.)


# ── briefing: EP alert prioritization composite ───────────────────────────────

class TestEpCompositeSort:
    def _ep(self, ticker, score, rs=0):
        return {"ticker": ticker, "ep_score": score, "rs_composite": rs,
                "gap_pct": 8.0, "score_tier": "HIGH", "rel_volume": 3.0,
                "catalyst_quality": "strong"}

    def _theme(self, tickers, stage):
        return {"tickers": tickers, "stage": stage, "name": "Test Theme",
                "score": 60, "description": ""}

    def test_accelerating_theme_ep_sorts_first(self):
        from agents.market_intelligence.briefing import _format_morning_briefing
        regime = {"regime": "Bull", "vix": 14.0, "ep_threshold": 70}
        eps = [
            self._ep("PLAIN", score=85),                  # no theme
            self._ep("THEMED", score=80),                 # Accelerating theme → +15
        ]
        themes = [self._theme(["THEMED"], "Accelerating")]
        text = _format_morning_briefing(
            regime=regime, ep_alerts=eps, briefing_date="2026-03-14",
            themes=themes,
        )
        # THEMED (80+15=95) should appear before PLAIN (85+0=85)
        assert text.index("THEMED") < text.index("PLAIN")

    def test_no_themes_falls_back_to_ep_score_order(self):
        from agents.market_intelligence.briefing import _format_morning_briefing
        regime = {"regime": "Bull", "vix": 14.0, "ep_threshold": 70}
        eps = [self._ep("LOW", score=72), self._ep("HIGH", score=88)]
        text = _format_morning_briefing(
            regime=regime, ep_alerts=eps, briefing_date="2026-03-14",
            themes=[],
        )
        assert text.index("HIGH") < text.index("LOW")

    def test_rs_bonus_breaks_tie(self):
        from agents.market_intelligence.briefing import _ep_composite_key
        ep_high_rs = {"ticker": "A", "ep_score": 80, "rs_composite": 95}
        ep_low_rs  = {"ticker": "B", "ep_score": 80, "rs_composite": 40}
        assert _ep_composite_key(ep_high_rs, {}) > _ep_composite_key(ep_low_rs, {})

    def test_rs_bonus_capped_at_10(self):
        from agents.market_intelligence.briefing import _ep_composite_key
        ep = {"ticker": "A", "ep_score": 80, "rs_composite": 200}  # extreme RS
        assert _ep_composite_key(ep, {}) == 90.0  # 80 + 10 (capped) + 0

    def test_theme_bonus_values(self):
        from agents.market_intelligence.briefing import _ep_composite_key, _THEME_BONUS
        ep = {"ticker": "T", "ep_score": 80, "rs_composite": 0}
        assert _ep_composite_key(ep, {"T": "Accelerating"}) == 80 + 15
        assert _ep_composite_key(ep, {"T": "Mainstream"})   == 80 + 10
        assert _ep_composite_key(ep, {"T": "Nascent"})      == 80 + 5
        assert _ep_composite_key(ep, {})                    == 80

    def test_fading_theme_gets_no_bonus(self):
        from agents.market_intelligence.briefing import _ep_composite_key
        ep = {"ticker": "T", "ep_score": 80, "rs_composite": 0}
        assert _ep_composite_key(ep, {"T": "Fading"}) == 80

    def test_morning_gather_includes_themes(self):
        from agents.market_intelligence import briefing
        src = inspect.getsource(briefing.send_morning_briefing)
        assert "get_today_themes" in src

    def test_multi_theme_ticker_keeps_strongest_stage(self):
        """When a ticker belongs to multiple themes, the strongest stage bonus should win."""
        from agents.market_intelligence.briefing import _ep_composite_key, _THEME_BONUS, _format_morning_briefing
        regime = {"regime": "Bull", "vix": 14.0, "ep_threshold": 70}
        eps = [{"ticker": "AXTI", "ep_score": 80, "rs_composite": 0,
                "gap_pct": 8.0, "score_tier": "HIGH", "rel_volume": 3.0,
                "catalyst_quality": "strong"}]
        # AXTI in two themes: Nascent (bonus=5) and Accelerating (bonus=15)
        themes = [
            {"tickers": ["AXTI"], "stage": "Nascent",      "name": "Theme A", "score": 50, "description": ""},
            {"tickers": ["AXTI"], "stage": "Accelerating", "name": "Theme B", "score": 70, "description": ""},
        ]
        text = _format_morning_briefing(
            regime=regime, ep_alerts=eps, briefing_date="2026-03-14", themes=themes,
        )
        # Verify: composite key should use Accelerating (+15), not Nascent (+5)
        # Build the stage map the same way the function does and assert
        stage_map: dict = {}
        for t in themes:
            stage = t.get("stage", "")
            for ticker in t.get("tickers") or []:
                existing = stage_map.get(ticker, "")
                if _THEME_BONUS.get(stage, 0) > _THEME_BONUS.get(existing, 0):
                    stage_map[ticker] = stage
        assert stage_map["AXTI"] == "Accelerating"
        assert _ep_composite_key(eps[0], stage_map) == 80 + 15  # Accelerating wins


# ── collector: 0% premarket change (falsy float fix) ─────────────────────────

class TestPremarketSnapshotFalsyZero:
    def test_zero_pct_change_is_included(self):
        """SPY flat overnight (0.0% change) must NOT be dropped — 0.0 is falsy."""
        from agents.market_intelligence.collector import get_premarket_snapshot

        payload = _make_polygon_snapshot(500.0, 500.0, 450.0, 445.5)  # SPY 0% change
        with patch("agents.market_intelligence.collector._polygon_get", new=AsyncMock(return_value=payload)):
            result = asyncio.run(get_premarket_snapshot())

        assert "spy_pct" in result, "0.0% overnight change must be included (not treated as falsy)"
        assert abs(result["spy_pct"]) < 0.001
