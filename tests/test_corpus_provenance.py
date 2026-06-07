"""#210 Wave B — source-class provenance of what the GRADE consumed.

`corpus_provenance` mirrors the grader's INPUT BRANCH (not build_grounded_text):
- grounded_text present  -> SEC + Benzinga + web counted
- grounded_text None     -> grade fell back to fmp headlines -> fmp_aggregator

`has_direct_source` flips True only for a DIRECT/primary class (sec_* or
benzinga_pr). The inverse (graded-high, has_direct_source=False) is the #211
sourcing-gap cohort — and fmp-only must read `fmp_aggregator`, NOT `{}`, so the
gap is diagnosable (aggregator-only vs total silence).
"""
from agents.market_intelligence.ep_detector import corpus_provenance, build_grounded_text


def _sec(form="8-K"):
    return {"form": form, "filed": "2026-06-02", "items": "1.01", "text": "deal body"}


def _bz(n=1):
    return [{"title": f"item {i}", "summary": "...", "symbols": ["X"]} for i in range(n)]


def _prov(sec, bz, pplx, fmp):
    """Build grounded_text the same way the scan does, then derive provenance —
    keeps the two in lockstep exactly as production does."""
    gt = build_grounded_text(sec, bz, pplx)
    return corpus_provenance(sec, bz, pplx, gt, fmp)


def test_total_silence_no_sources():
    p = _prov(None, [], None, [])
    assert p == {"sources": {}, "has_direct_source": False}


def test_fmp_fallback_is_aggregator_not_empty():
    # THE case the metric exists to catch: graded off fmp headlines only.
    p = _prov(None, [], None, [{"title": "a"}, {"title": "b"}])
    assert p["sources"] == {"fmp_aggregator": 2}
    assert p["has_direct_source"] is False


def test_perplexity_only_is_not_direct():
    p = _prov(None, [], "web synthesis text", [{"title": "ignored-when-grounded"}])
    assert p["sources"] == {"web_perplexity": 1}   # fmp NOT counted — grade used grounded
    assert p["has_direct_source"] is False


def test_benzinga_is_direct():
    p = _prov(None, _bz(2), "web text", [])
    assert p["sources"] == {"benzinga_pr": 2, "web_perplexity": 1}
    assert p["has_direct_source"] is True


def test_sec_8k_is_direct_and_form_normalized():
    p = _prov(_sec("8-K"), [], None, [])
    assert p["sources"] == {"sec_8k": 1}
    assert p["has_direct_source"] is True


def test_sec_6k_form_normalized():
    p = _prov(_sec("6-K"), [], None, [])
    assert "sec_6k" in p["sources"]
    assert p["has_direct_source"] is True


def test_sec_425_counts_direct_structurally():
    # Wave D forward-proofing: a primary SEC form not in any hardcoded list
    # must still read as direct.
    p = _prov(_sec("425"), [], None, [])
    assert p["sources"] == {"sec_425": 1}
    assert p["has_direct_source"] is True


def test_grrr_as_of_shape():
    # GRRR 6/2 as-of: 6-K lagged (SEC absent), Benzinga + web -> direct via Benzinga.
    p = _prov(None, _bz(2), "web", [])
    assert p["sources"] == {"benzinga_pr": 2, "web_perplexity": 1}
    assert p["has_direct_source"] is True


def test_full_corpus_counts():
    p = _prov(_sec("8-K"), _bz(3), "web", [{"title": "ignored"}])
    assert p["sources"] == {"sec_8k": 1, "benzinga_pr": 3, "web_perplexity": 1}
    assert p["has_direct_source"] is True
