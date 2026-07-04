"""#347 — the LIVE enriched-corpus flip (operator-approved 2026-07-04).

The BEHAVIORAL evidence is the 10-day prod shadow (183 grades, 5 change-events
all correct-direction, dilution 10/10, re-poll once/clean — the 7/4 walkthrough).
These tests pin the flip's inline INVARIANTS in run_ep_scan so a refactor can't
silently drop them; the repoll cache-apply is exercised against the REAL
CachedGrade shape (the S6 machinery the upgrade rides on).
"""
import inspect

from agents.market_intelligence import ep_detector


def _scan_src():
    return inspect.getsource(ep_detector.run_ep_scan)


def test_live_enriched_is_premarket_and_toggle_gated():
    src = _scan_src()
    # the validated shape: premarket-only + the #400 instant-revert toggle
    assert '_is_premarket(now_et)' in src
    assert 'get_runtime_toggle("live_enriched_corpus", "LIVE_ENRICHED_CORPUS")' in src


def test_apog_sentinel_falls_back_to_legacy_not_routine():
    src = _scan_src()
    # the enriched fail-routine sentinel must RAISE into the legacy fallback...
    assert 'Classification failed" in (_ea or "")' in src
    # ...and the legacy path fires whenever the enriched grade didn't land
    assert "if catalyst_quality is None:" in src
    # the failure is audited, never silent
    assert '"live_enriched_grade_failed"' in src


def test_enrichment_shadow_gated_to_reversion_mode():
    src = _scan_src()
    assert "if (not _use_enriched" in src, (
        "#347: the enrichment shadow must run only when the live path is NOT "
        "enriched (toggle off) — enriched-vs-enriched is noise + double cost"
    )


def test_repoll_live_apply_resets_the_s6_fields():
    src = _scan_src()
    # the live re-poll rewrites the cache via _replace with EXACTLY the safe field set:
    for frag in ("catalyst_quality=_rq", "confidence_multiplier=1.0",
                 "pplx_quality=None", "filters_cleared=False"):
        assert frag in src, f"#347 repoll cache-apply must set {frag}"
    assert '"catalyst_repoll_regraded_live"' in src


def test_repoll_apply_matches_real_cachedgrade_shape():
    # The _replace call the repoll makes must be valid against the REAL CachedGrade
    cg = ep_detector.CachedGrade(
        catalyst_quality="routine", confidence_multiplier=1.2,
        news_summary="s", claude_analysis="a", pplx_quality="routine",
        filters_cleared=True,
    )
    out = cg._replace(catalyst_quality="strong", claude_analysis="new",
                      confidence_multiplier=1.0, pplx_quality=None,
                      filters_cleared=False)
    assert out.catalyst_quality == "strong" and out.filters_cleared is False
    assert out.confidence_multiplier == 1.0 and out.pplx_quality is None
    assert out.news_summary == "s"  # untouched fields carry over
