"""Regression tests for the Alpaca env-var boot guard (#139, 2026-05-28).

Pre-fix: `os.environ["ALPACA_LIVE_API_KEY"]` raised bare KeyError when
boot bootstrap was bypassed. The 2026-05-13 outage was that exact path:
operator couldn't tell whether bootstrap failed, var was misspelled, or
ENABLE_LIVE_MODE was off.

Post-fix: `_require_alpaca_env(name, account_mode)` raises RuntimeError
with diagnostic context (which var, which mode, what to check).
"""
import os
import pytest


def test_require_alpaca_env_raises_with_context_when_missing(monkeypatch):
    from agents.market_intelligence.broker.alpaca_client import _require_alpaca_env
    monkeypatch.delenv("ALPACA_LIVE_API_KEY", raising=False)
    with pytest.raises(RuntimeError) as exc:
        _require_alpaca_env("ALPACA_LIVE_API_KEY", "live")
    msg = str(exc.value)
    # Diagnostic surface area:
    assert "ALPACA_LIVE_API_KEY" in msg
    assert "live" in msg
    assert "boot bootstrap" in msg.lower() or "_bootstrap" in msg
    assert "ENABLE_LIVE_MODE" in msg  # operator self-diagnosis hint
    assert "CLAUDE.md" in msg


def test_require_alpaca_env_returns_value_when_present(monkeypatch):
    from agents.market_intelligence.broker.alpaca_client import _require_alpaca_env
    monkeypatch.setenv("ALPACA_PAPER_API_KEY", "test-key-value")
    assert _require_alpaca_env("ALPACA_PAPER_API_KEY", "paper") == "test-key-value"


def test_require_alpaca_env_empty_string_treated_as_missing(monkeypatch):
    """Some shells set empty strings rather than unsetting — same operator
    confusion class. Treat empty as missing."""
    from agents.market_intelligence.broker.alpaca_client import _require_alpaca_env
    monkeypatch.setenv("ALPACA_PAPER_API_KEY", "")
    with pytest.raises(RuntimeError):
        _require_alpaca_env("ALPACA_PAPER_API_KEY", "paper")
