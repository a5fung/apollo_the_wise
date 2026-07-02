"""#384(1) — format_ep_tweet routes RVOL through the pm_rvol SSoT resolver
(briefing._resolve_ep_rvol). Pre-market, rel_volume is ~0.01x while pm_rvol
carries the real signal (SNX/MU 6/25) — the tweet must show the resolved value."""
from unittest.mock import patch

from agents.market_intelligence.twitter import format_ep_tweet


def _ep(**over):
    ep = {
        "ticker": "SNX", "rel_volume": 0.01, "pm_rvol": 12.3,
        "gap_pct": 8.0, "ep_score": 85.0,
        "catalyst_quality": "strong", "claude_analysis": "",
    }
    ep.update(over)
    return ep


def test_premarket_tweet_uses_pm_rvol_not_raw():
    with patch("agents.market_intelligence.universe.get_description", return_value=None):
        tweets = format_ep_tweet(_ep())
    assert tweets, "must render at least one tweet"
    assert "RVol 12.3x" in tweets[0]
    assert "0.01" not in tweets[0], "raw pre-market rel_volume must not leak into the tweet"


def test_intraday_tweet_uses_rel_volume():
    with patch("agents.market_intelligence.universe.get_description", return_value=None):
        tweets = format_ep_tweet(_ep(rel_volume=3.4, pm_rvol=None))
    assert "RVol 3.4x" in tweets[0]
