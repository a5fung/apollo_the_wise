"""EP per-ticker line rendering (`_format_ep_ticker_block`) — display fixes, operator 6/25.

Pins both fixes from the SNX/MU confusion: (1) the tier WORD is on the line + the grade is labeled
"catalyst" (not a rival verdict to HIGH); (2) pre-market alerts show pm_rvol (the meaningful pre-
market relative volume), NOT the rel_volume that reads ≈ 0 pre-market; intraday keeps accumulated
rel_volume.
"""
from agents.market_intelligence.briefing import _format_ep_ticker_block


def _line(**kw):
    base = {"ticker": "X", "score_tier": "HIGH", "gap_pct": 10.0, "ep_score": 80,
            "catalyst_quality": "game_changer"}
    base.update(kw)
    return _format_ep_ticker_block(base)[0]


def test_tier_word_and_catalyst_label_present():
    line = _line()
    assert "HIGH" in line                     # the tier WORD, not just the emoji
    assert "game changer catalyst" in line    # grade labeled + underscore sanitized
    assert "game_changer" not in line         # the raw underscore (Markdown italic) is gone


def test_premarket_shows_pm_rvol_not_tiny_rel_volume():
    # SNX 6/25: rel_volume 0.01x pre-market while pm_rvol was 12.1x — show the meaningful one.
    line = _line(rel_volume=0.01, pm_rvol=12.085)
    assert "pm rvol 12.1x" in line
    assert "rv 0.01x" not in line


def test_intraday_shows_accumulated_rel_volume():
    # rel_volume >= 1.0 → the day's volume has accumulated; rel_volume is now meaningful.
    line = _line(rel_volume=2.5, pm_rvol=12.0)
    assert "rv 2.5x" in line
    assert "pm rvol" not in line


def test_no_pm_rvol_falls_back_to_rel_volume():
    # no pre-market figure available → show rel_volume even if small (it's the only data).
    line = _line(rel_volume=0.03, pm_rvol=None)
    assert "rv 0.03x" in line


def test_ep_alert_premarket_shows_pm_rvol_not_raw_rel_volume():
    """The LIVE EP alert (send_ep_alert) — not just the brief line — must show pm_rvol pre-market.
    Regression for the 6/26 SNX/MU split: the brief got the pm_rvol fix but send_ep_alert kept
    rendering raw rel_volume (≈ 0 pre-market). Both now route through _resolve_ep_rvol."""
    import asyncio
    from unittest.mock import AsyncMock, patch
    from agents.market_intelligence import briefing

    ep = {"ticker": "SNX", "score_tier": "HIGH", "gap_pct": 8.0, "ep_score": 80,
          "catalyst_quality": "game_changer", "rel_volume": 0.01, "pm_rvol": 12.085}
    captured = {}

    async def _cap(text, *a, **k):
        captured["text"] = text
        return True

    with patch.object(briefing, "send_telegram_message", new=AsyncMock(side_effect=_cap)):
        asyncio.run(briefing.send_ep_alert(ep))

    assert "pm RVOL: *12.1x*" in captured["text"]    # the pre-market figure, labeled
    assert "| RVOL: *0.01x*" not in captured["text"]  # NOT the raw rel_volume that reads ~0
