"""#260 — execute_task routing FREEZE (behavioral pin, not source-grep).

The ~30-rule first-match-wins substring cascade in agent.py is frozen policy:
new features get slash-commands/structured entry points, and any reorder or
keyword change to the cascade must consciously update this table instead of
silently misrouting an operator phrase. Every `_handle_*` method is replaced
with a recorder, so the assertions exercise the REAL routing code with zero
I/O — a canonical phrase landing on a different handler fails here, not in
production.
"""
import asyncio

import pytest

from agents.market_intelligence.agent import MarketIntelligenceAgent
from shared.models import AgentRequest


@pytest.fixture(scope="module")
def routed():
    agent = MarketIntelligenceAgent()

    def _recorder(name):
        async def _rec(*args, **kwargs):
            return {"handler": name, "kwargs": kwargs}
        return _rec

    for attr in dir(agent):
        if attr.startswith("_handle_") and callable(getattr(agent, attr)):
            setattr(agent, attr, _recorder(attr))

    def _route(task: str) -> dict:
        req = AgentRequest(task=task, user_id=1, conversation_id="t")
        return asyncio.run(agent.execute_task(req))

    return _route


# Canonical phrase → handler. ORDER-SENSITIVE cases carry a comment naming the
# rule they must beat. Change this table ONLY together with a conscious change
# to the cascade (CLAUDE.md "Market Agent Routing" section).
ROUTING_TABLE = [
    ("/flags", "_handle_slash_command"),                  # slash fast-path beats all NLP
    ("friday watchlist", "_handle_friday_watchlist"),     # before generic watchlist
    ("track NVDA overnight", "_handle_watchlist"),
    ("parabolic exclude BTBT", "_handle_parabolic_exclusion"),  # before theme exclusion
    ("exclude TSEM from theme", "_handle_theme_exclusion"),
    ("theme assign NVDA to semiconductors", "_handle_theme_assign"),
    ("restore retired themes", "_handle_restore_themes"),
    ("rerun theme engine", "_handle_theme_only"),
    ("refresh data", "_handle_data_refresh"),
    ("weekly review", "_handle_system_review"),
    ("audit cooldowns", "_handle_audit_topic"),           # bare-audit topic, not audit log
    ("strategy", "_handle_strategy_command"),
    ("journal: long NVDA half size", "_handle_journal_add"),
    ("show journal", "_handle_journal_query"),
    ("postmortem IBM", "_handle_postmortem"),             # before trades_query's "trade" net
    ("audit log", "_handle_audit_log"),
    ("show trades", "_handle_trades_query"),
    ("when did metals peak", "_handle_history_query"),    # before theme/RS
    ("ep history", "_handle_history_query"),              # "history" net wins — the
                                                          # ep-history keyword is dead (#260)
    ("recent eps", "_handle_ep_history"),                 # the live ep-history phrasings
    ("show clusters", "_handle_correlation_clusters"),
    ("show cooldowns", "_handle_cooldown_query"),
    ("bypass cooldown semiconductors NVDA", "_handle_cooldown_bypass"),
    ("validation report", "_handle_validation_report"),
    ("9m outcome", "_handle_9m_ep_outcomes"),             # before 9m query + general ep
    ("show 9m trades", "_handle_9m_trades"),              # SHOW must not ticker-extract (#260)
    ("sugar babies", "_handle_9m_ep_query"),
    ("9m", "_handle_9m_ep_query"),
    ("wick watch", "_handle_wick_query"),
    ("fishhook", "_handle_fishhook_query"),
    ("flags", "_handle_flag_query"),                      # bare word, before theme net
    ("setup RCAT", "_handle_setup_query"),
    ("ep outcomes", "_handle_ep_outcomes"),               # before general ep
    ("missed winners", "_handle_missed_query"),
    ("trace RCAT", "_handle_why_query"),                  # execution-side diagnostic
    ("show ep", "_handle_ep_query"),
    ("top themes", "_handle_theme_query"),
    ("btc dominance", "_handle_crypto_query"),            # before regime/RS ticker-extract
    ("regime", "_handle_regime_query"),
    ("rs leaders", "_handle_rs_query"),                   # no ticker → list view
    ("score NVDA", "_handle_single_score"),               # ticker → single-score
    ("morning brief", "_handle_briefing_query"),
    ("pullback list", "_handle_pullback_query"),
    ("earnings growth NVDA", "_handle_fundamentals_query"),
    ("research MRNA", "_handle_single_score"),
    ("screener", "_handle_screener_query"),
    ("position sizing", "_handle_trading_config"),
    ("hello there friend", "_handle_general"),            # fallback
]


@pytest.mark.parametrize("phrase,expected", ROUTING_TABLE,
                         ids=[p for p, _ in ROUTING_TABLE])
def test_phrase_routes_to_pinned_handler(routed, phrase, expected):
    assert routed(phrase)["handler"] == expected


def test_single_ticker_trade_lookup_passes_ticker(routed):
    res = routed("TVTX trade")
    assert res["handler"] == "_handle_trades_query"
    assert res["kwargs"].get("ticker") == "TVTX"


def test_what_happened_phrasing_goes_to_audit_log_not_trades(routed):
    # The code's old comment claimed this phrase hits the trade lookup — it
    # never did: "what happened" sits in the audit-log keyword net above it.
    # Pinned so a future "fix" of either rule is a conscious decision.
    assert routed("what happened with TVTX trade")["handler"] == "_handle_audit_log"
