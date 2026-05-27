"""Regression tests for _claude_text_signals_earnings (#131, 2026-05-27).

CRSR 2026-05-27 EP alert had no rubric block: catalyst extraction was
gated on `earnings_today_match` from yfinance, but yfinance earnings_dates
missed CRSR's Q1 date. Claude's analysis clearly identified earnings
("Corsair Gaming reported Q1 2026 earnings with $354.51M in sales and
returned to profitability with $12.78M net income, beating expectations")
but the textual signal wasn't being used.

Fix: add a regex over Claude's analysis as a fallback signal to the
extraction gate so yfinance ingest-lag doesn't silently kill the rubric.
"""
import sys
import types
from unittest.mock import MagicMock


class _MockModule(types.ModuleType):
    def __getattr__(self, name):
        v = MagicMock(name=f"{self.__name__}.{name}")
        setattr(self, name, v)
        return v


for mod_name in [
    "alpaca", "alpaca.trading", "alpaca.trading.client", "alpaca.trading.requests",
    "alpaca.trading.enums", "alpaca.trading.models", "alpaca.trading.stream",
    "alpaca.data", "alpaca.data.historical", "alpaca.data.requests",
    "alpaca.data.timeframe", "alpaca.data.enums", "alpaca.common",
    "alpaca.common.exceptions", "anthropic",
]:
    sys.modules.setdefault(mod_name, _MockModule(mod_name))

sys.modules.setdefault(
    "agents.market_intelligence.backtester",
    types.ModuleType("agents.market_intelligence.backtester"),
)
_filters_stub = types.ModuleType("agents.market_intelligence.backtester.filters")
_filters_stub.validate_orb_entry = MagicMock(name="validate_orb_entry")
_filters_stub.check_filters = MagicMock(name="check_filters")
sys.modules.setdefault("agents.market_intelligence.backtester.filters", _filters_stub)


from agents.market_intelligence.ep_detector import _claude_text_signals_earnings


# ── Cases that should signal earnings ────────────────────────────────────────

def test_crsr_real_alert_text_detected():
    """The exact CRSR 2026-05-27 Claude text."""
    text = (
        "Corsair Gaming reported Q1 2026 earnings with $354.51M in sales and "
        "returned to profitability with $12.78M net income (vs. a loss in the "
        "prior year), beating expectations and triggering analyst consensus "
        "estimate updates."
    )
    assert _claude_text_signals_earnings(text) is True


def test_q4_earnings_detected():
    assert _claude_text_signals_earnings(
        "ABC reported Q4 2025 earnings with strong revenue growth."
    ) is True


def test_quarterly_earnings_detected():
    assert _claude_text_signals_earnings(
        "Company XYZ reported quarterly earnings yesterday."
    ) is True


def test_eps_with_dollar_amount_detected():
    assert _claude_text_signals_earnings(
        "FOO posted EPS of $0.42 yesterday, beating consensus."
    ) is True


def test_revenue_with_dollar_amount_detected():
    """The DY-style 'revenue of $XXM' phrasing."""
    assert _claude_text_signals_earnings(
        "Strong quarter — revenue of $185M and improving margins."
    ) is True


def test_beat_consensus_detected():
    assert _claude_text_signals_earnings(
        "Solid execution, beat consensus by 12%."
    ) is True


def test_earnings_release_detected():
    assert _claude_text_signals_earnings(
        "Following last night's earnings release, shares are up..."
    ) is True


# ── Cases that should NOT signal earnings ────────────────────────────────────

def test_fda_approval_not_earnings():
    """An FDA approval catalyst should NOT match — extraction would be a
    wasted Sonnet call (rubric doesn't apply)."""
    assert _claude_text_signals_earnings(
        "FDA approval granted for novel therapy; shares spike on news."
    ) is False


def test_m_and_a_news_not_earnings():
    assert _claude_text_signals_earnings(
        "Company X announced acquisition of Y for $500M cash."
    ) is False


def test_analyst_upgrade_only_not_earnings():
    assert _claude_text_signals_earnings(
        "Goldman raised price target to $200 citing AI tailwinds."
    ) is False


def test_empty_text_no_signal():
    assert _claude_text_signals_earnings("") is False
    assert _claude_text_signals_earnings(None) is False


def test_revenue_word_alone_not_signal():
    """'revenue' without a dollar amount + period marker isn't enough."""
    assert _claude_text_signals_earnings(
        "Revenue stream looks promising long-term."
    ) is False
