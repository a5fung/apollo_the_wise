"""#360 (CHANGE_PROCESS 2026-06-23, operator-signed): the stored `catalyst` text on
mi_ep_alerts must come from the GROUNDED `claude_analysis` when a direct/primary source
was found — NOT the Perplexity `news_summary`, which confabulates a "no catalyst"
disclaimer when it can't discover the catalyst (QURE alert 12310: catalyst text disclaimed
a catalyst while claude_analysis, grounded on the 8-K, led with the FDA AMT-130 BLA).

Pins the pure source-selection helper independent of the scan loop. The clip limit (500
in the live call sites) is exercised here with small explicit limits so the slice is
visible. LLM-as-judge-of-grounded-not-discoverer; behavior-preserving for the
no-direct-source path (byte-identical to the pre-#360 `news_summary[:limit]`).
"""
from agents.market_intelligence.ep_detector import _resolve_catalyst_text


def test_direct_source_with_analysis_uses_grounded_claude():
    # has_direct_source True + grounded claude_analysis present → the GROUNDED text wins.
    out = _resolve_catalyst_text(
        claude_analysis="The specific catalyst is the FDA-cleared AMT-130 BLA.",
        news_summary="No specific catalyst found in the news.",  # the confabulated disclaimer
        has_direct_source=True,
        limit=500,
    )
    assert out == "The specific catalyst is the FDA-cleared AMT-130 BLA."


def test_no_direct_source_uses_news_summary():
    # has_direct_source falsy → keep the Perplexity narrative (unchanged behavior).
    out = _resolve_catalyst_text(
        claude_analysis="Grounded analysis that must NOT be used here.",
        news_summary="Company gapped on sector strength.",
        has_direct_source=False,
        limit=500,
    )
    assert out == "Company gapped on sector strength."


def test_direct_source_but_empty_analysis_falls_back_not_blank():
    # has_direct_source True but claude_analysis whitespace-only → fall back to news_summary,
    # NEVER blank (an LLM-call failure must not produce an empty catalyst).
    out = _resolve_catalyst_text(
        claude_analysis="   ",
        news_summary="Fallback narrative.",
        has_direct_source=True,
        limit=500,
    )
    assert out == "Fallback narrative."


def test_direct_source_but_none_analysis_falls_back_not_crash():
    # The real LLM-failure mode: claude_analysis is None. Must fall back, not raise on .strip().
    out = _resolve_catalyst_text(
        claude_analysis=None,
        news_summary="Fallback narrative.",
        has_direct_source=True,
        limit=500,
    )
    assert out == "Fallback narrative."


def test_clip_limit_applies_to_chosen_source():
    # Same clip the live field uses — applied to whichever source is chosen.
    grounded = "A" * 600
    assert _resolve_catalyst_text(grounded, "n", True, 500) == "A" * 500
    news = "B" * 600
    assert _resolve_catalyst_text("g", news, False, 500) == "B" * 500


def test_both_empty_returns_empty_not_error():
    # Degenerate case: no grounded analysis, no news. Returns "" (never blanks via crash).
    assert _resolve_catalyst_text(None, "", True, 500) == ""
    assert _resolve_catalyst_text(None, "", False, 500) == ""
