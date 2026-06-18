"""#329 Path A — the no-spend sizing helper that recomputes has_direct_source from the STORED
grounded_text section markers. This is the correctness core of eval_judge_enrich --size-only:
a wrong marker rule mis-sizes the blast radius and either wastes Opus spend or hides a live defect.
"""
from scripts.eval_judge_enrich import recompute_has_direct_source


def test_sec_marker_is_direct():
    g = "[SEC 8-K filed 2026-06-18, items 2.02] Q1 revenue +44% YoY ..."
    assert recompute_has_direct_source(g) == (True, True)


def test_benzinga_marker_is_direct():
    g = "[Benzinga 2026-06-18T12:30] Company announces $270M cloud deal ..."
    assert recompute_has_direct_source(g) == (True, True)


def test_web_summary_only_is_not_direct_but_assessable():
    # Has a section marker (assessable) but the only source is the least-trusted web tail.
    g = "[Web summary] Perplexity says the stock gapped on sector momentum ..."
    assert recompute_has_direct_source(g) == (False, True)


def test_sec_plus_web_is_direct():
    g = "[SEC 8-K filed 2026-06-18, items 2.02] beat. [Web summary] also some web color."
    assert recompute_has_direct_source(g) == (True, True)


def test_thin_grounded_has_no_markers_excluded():
    # Pre-W1 / thin rows carry just the catalyst text, no section markers → not assessable
    # from stored text (excluded from the blast-radius denominator).
    assert recompute_has_direct_source("Company gapped 18% on heavy volume.") == (False, False)


def test_empty_and_none():
    assert recompute_has_direct_source("") == (False, False)
    assert recompute_has_direct_source(None) == (False, False)
