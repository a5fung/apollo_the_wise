"""Regression: _normalize_slash_cmd must preserve underscores (#218, 2026-06-06).

The inline-keyboard drill-down callbacks /eps_detail, /themes_detail,
/trades_detail are real dispatch keys. The prior normalizer stripped every
non-alnum char incl. the underscore, so '/eps_detail' normalized to '/epsdetail'
and missed dispatch -> "Unknown command: /epsdetail" (operator screenshots 6/6).
"""
from __future__ import annotations

from agents.market_intelligence.agent import _normalize_slash_cmd


def test_detail_callbacks_keep_underscore():
    assert _normalize_slash_cmd("/eps_detail") == "/eps_detail"
    assert _normalize_slash_cmd("/themes_detail") == "/themes_detail"
    assert _normalize_slash_cmd("/trades_detail") == "/trades_detail"


def test_plain_commands_unchanged():
    assert _normalize_slash_cmd("/ep") == "/ep"
    assert _normalize_slash_cmd("/syncnow") == "/syncnow"


def test_still_strips_botname_and_invisible_chars():
    assert _normalize_slash_cmd("/status@ApolloBot") == "/status"
    # zero-width space (U+200B) embedded — the #138 class
    assert _normalize_slash_cmd("/sync​now") == "/syncnow"
    # underscore survives even alongside an invisible char
    assert _normalize_slash_cmd("/eps​_detail") == "/eps_detail"
