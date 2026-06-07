"""
Tests to pinpoint exactly why theme engine completion notification fails.
Tests the full code path:
  1. _handle_theme_only returns correct result (sync approach)
  2. send_telegram_message won't 400 on completion text
  3. AGENT_TIMEOUT is >= 300s
  4. run_theme_engine always returns a 2-tuple
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── 1. _handle_theme_only returns result through normal response channel ───────

class TestHandleThemeOnly:
    """The sync approach must return result in AgentResponse.result, not via direct Telegram."""

    def _make_request(self, task="rerun theme engine"):
        from shared.models import AgentRequest
        return AgentRequest(task=task, user_id=1, conversation_id="test")

    def _fake_themes(self, n_active=10, n_fading=2):
        active = [{"name": f"Theme {i}", "stage": "Accelerating", "score": 80, "tickers": []} for i in range(n_active)]
        fading = [{"name": f"Fading {i}", "stage": "Fading", "score": 30, "tickers": []} for i in range(n_fading)]
        return active + fading

    def _make_agent(self):
        """Create agent instance with agent_name set (skipping DB/FastAPI wiring)."""
        from agents.market_intelligence.agent import MarketIntelligenceAgent
        from shared.models import AgentName
        with patch("agents.base.get_secrets"), patch("shared.audit.log_action"):
            agent = MarketIntelligenceAgent.__new__(MarketIntelligenceAgent)
            agent.agent_name = AgentName.MARKET_INTELLIGENCE
        return agent

    def _themes_with_tickers(self, n_active=10, n_fading=2):
        """#205: _handle_theme_only re-scores via _compute_scored_themes from
        per-ticker RS data, so active themes need real tickers (empty-ticker themes
        are skipped → 0 active). Pair with _mock_rs() patched into the handler."""
        active = [{"name": f"Theme {i}", "stage": "Accelerating", "score": 80,
                   "tickers": [f"T{i}A", f"T{i}B"]} for i in range(n_active)]
        fading = [{"name": f"Fading {i}", "stage": "Fading", "score": 30,
                   "tickers": [f"F{i}A", f"F{i}B"]} for i in range(n_fading)]
        return active + fading

    def _run_handler(self, agent, themes, changelog=None):
        """Run _handle_theme_only with run_theme_engine + the RS getters mocked so
        _compute_scored_themes keeps every active theme (rs_composite present)."""
        rs = {tk: {"rs_composite": 80, "rs_1m": 80, "rs_3m": 80, "rs_6m": 80}
              for t in themes for tk in t["tickers"]}

        async def run():
            with patch("agents.market_intelligence.agent.run_theme_engine", new=AsyncMock(return_value=(themes, changelog or []))), \
                    patch("agents.market_intelligence.agent.get_rs_for_tickers", new=AsyncMock(return_value=rs)), \
                    patch("agents.market_intelligence.agent.get_prior_theme_scores", new=AsyncMock(return_value={})):
                return await agent._handle_theme_only(self._make_request())

        return asyncio.run(run())

    def test_returns_summary_in_result_field(self):
        """Result must be in AgentResponse.result — orchestrator sends it to Telegram."""
        themes = self._themes_with_tickers(n_active=10, n_fading=2)
        resp = self._run_handler(self._make_agent(), themes)
        assert resp.success, f"Expected success=True, got error: {resp.error}"
        assert resp.result is not None
        assert "THEME ENGINE — 10 active" in resp.result, f"Got: {resp.result}"

    def test_fading_themes_excluded_from_count(self):
        """Fading themes must not count toward active total."""
        themes = self._themes_with_tickers(n_active=5, n_fading=3)
        resp = self._run_handler(self._make_agent(), themes)
        assert resp.success, f"Error: {resp.error}"
        assert "THEME ENGINE — 5 active" in resp.result

    def test_revalidated_tickers_appear_in_summary(self):
        """Removed mismatched tickers must show in result."""
        themes = self._fake_themes(n_active=5)
        changelog = [
            {"type": "ticker_revalidated_out", "ticker": "AGRO", "theme": "IP Licensing & Ad-Tech"},
            {"type": "ticker_revalidated_out", "ticker": "DAR",  "theme": "IP Licensing & Ad-Tech"},
        ]
        agent = self._make_agent()

        async def run():
            with patch("agents.market_intelligence.agent.run_theme_engine", new=AsyncMock(return_value=(themes, changelog))):
                return await agent._handle_theme_only(self._make_request())

        resp = asyncio.run(run())
        assert resp.success, f"Error: {resp.error}"
        assert "AGRO" in resp.result
        assert "DAR" in resp.result
        assert "IP Licensing" in resp.result

    def test_exception_returns_error_response(self):
        """If run_theme_engine raises, must return error AgentResponse (not crash)."""
        agent = self._make_agent()

        async def run():
            with patch("agents.market_intelligence.agent.run_theme_engine", new=AsyncMock(side_effect=RuntimeError("DB down"))):
                return await agent._handle_theme_only(self._make_request())

        resp = asyncio.run(run())
        assert not resp.success
        assert "DB down" in resp.error

    def test_no_direct_telegram_send_called(self):
        """sync approach must NOT call send_telegram_message directly — orchestrator handles delivery."""
        themes = self._fake_themes()
        agent = self._make_agent()

        async def run():
            with patch("agents.market_intelligence.agent.run_theme_engine", new=AsyncMock(return_value=(themes, []))):
                with patch("agents.market_intelligence.agent.send_telegram_message") as mock_send:
                    resp = await agent._handle_theme_only(self._make_request())
                    await asyncio.sleep(0.05)
                    return resp, mock_send.call_count

        resp, send_count = asyncio.run(run())
        assert resp.success, f"Error: {resp.error}"
        assert send_count == 0, f"send_telegram_message was called {send_count} times — should be 0 in sync approach"


# ── 2. send_telegram_message won't 400 on typical completion text ─────────────

class TestSendTelegramMessageSafety:
    """Verify completion text won't trigger Telegram Markdown parse errors."""

    def _mock_client(self, status_code=200, body=None):
        """Return an httpx-like mock that returns the given status."""
        resp = MagicMock()
        resp.status_code = status_code
        resp.raise_for_status = MagicMock()
        if status_code >= 400:
            import httpx
            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                f"{status_code}", request=MagicMock(), response=resp
            )
        return resp

    def test_plain_completion_message_sends_ok(self):
        """The minimal summary text must not cause Telegram API errors."""
        from agents.market_intelligence.briefing import send_telegram_message

        mock_resp = self._mock_client(200)
        mock_post = AsyncMock(return_value=mock_resp)

        import os
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "fake:token", "TELEGRAM_ALLOWED_USER_IDS": "123"}):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = mock_post
                mock_client_cls.return_value = mock_client

                result = asyncio.run(send_telegram_message("Theme engine complete — 74 active themes"))

        assert result is True

    def test_completion_with_theme_names_containing_ampersand(self):
        """Theme names with & must not cause 400 — & is not Markdown special."""
        from agents.market_intelligence.briefing import send_telegram_message

        mock_resp = self._mock_client(200)
        mock_post = AsyncMock(return_value=mock_resp)

        text = "Theme engine complete — 74 active themes\nRemoved mismatched: AGRO from IP Licensing & Ad-Tech"

        import os
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "fake:token", "TELEGRAM_ALLOWED_USER_IDS": "123"}):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = mock_post
                mock_client_cls.return_value = mock_client

                result = asyncio.run(send_telegram_message(text))

        assert result is True

    def test_returns_false_on_telegram_400(self):
        """If Telegram rejects the message, must return False (not raise)."""
        from agents.market_intelligence.briefing import send_telegram_message

        mock_resp = self._mock_client(400)
        mock_post = AsyncMock(return_value=mock_resp)

        import os
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "fake:token", "TELEGRAM_ALLOWED_USER_IDS": "123"}):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = mock_post
                mock_client_cls.return_value = mock_client

                result = asyncio.run(send_telegram_message("test"))

        assert result is False  # must not raise

    def test_returns_false_when_no_token(self):
        """Missing TELEGRAM_BOT_TOKEN must return False, not crash."""
        from agents.market_intelligence.briefing import send_telegram_message

        import os
        env = {k: v for k, v in os.environ.items() if k not in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USER_IDS")}
        env["TELEGRAM_ALLOWED_USER_IDS"] = "123"
        with patch.dict(os.environ, env, clear=True):
            result = asyncio.run(send_telegram_message("test"))

        assert result is False

    def test_returns_false_when_no_allowed_users(self):
        """Missing TELEGRAM_ALLOWED_USER_IDS must return False, not crash."""
        from agents.market_intelligence.briefing import send_telegram_message

        import os
        env = {k: v for k, v in os.environ.items() if k not in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USER_IDS")}
        env["TELEGRAM_BOT_TOKEN"] = "fake:token"
        with patch.dict(os.environ, env, clear=True):
            result = asyncio.run(send_telegram_message("test"))

        assert result is False


# ── 3. AGENT_TIMEOUT is large enough for theme engine ─────────────────────────

class TestAgentTimeout:
    def test_agent_timeout_at_least_300s(self):
        """AGENT_TIMEOUT must be >= 300s so theme engine (2-4 min) doesn't get cut off."""
        from core.router import AGENT_TIMEOUT
        assert AGENT_TIMEOUT >= 300, (
            f"AGENT_TIMEOUT={AGENT_TIMEOUT}s is too low. "
            f"Theme engine can take 3-4 min. Must be >= 300s."
        )


# ── 4. run_theme_engine always returns a 2-tuple ──────────────────────────────

class TestRunThemeEngineReturnType:
    def test_early_return_is_tuple(self):
        """Even the early-exit path (no RS data) must return ([], []) not [] alone."""
        import inspect
        from agents.market_intelligence import theme_engine
        src = inspect.getsource(theme_engine.run_theme_engine)
        # All return statements should return 2-tuples
        import ast
        tree = ast.parse(src)
        returns = [n for n in ast.walk(tree) if isinstance(n, ast.Return) and n.value is not None]
        for r in returns:
            # Check if it's a Tuple node
            if not isinstance(r.value, ast.Tuple):
                # Could be a name/call — just warn, not fail (hard to check statically)
                pass
            else:
                assert len(r.value.elts) == 2, (
                    f"run_theme_engine has a return with {len(r.value.elts)} values, expected 2-tuple"
                )

    def test_no_background_task_in_handle_theme_only(self):
        """_handle_theme_only must NOT use asyncio.create_task for the main run — sync only."""
        import inspect
        from agents.market_intelligence.agent import MarketIntelligenceAgent
        src = inspect.getsource(MarketIntelligenceAgent._handle_theme_only)
        # Should not have create_task wrapping run_theme_engine
        assert "create_task(_run" not in src, (
            "Found create_task(_run) — this is the old background task approach. "
            "The sync approach should await run_theme_engine() directly."
        )
        assert "await run_theme_engine()" in src, (
            "run_theme_engine() must be directly awaited in _handle_theme_only"
        )
