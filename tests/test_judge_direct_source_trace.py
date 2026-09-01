"""We tell the grader "no direct source" whenever we do not KNOW — and that suppresses grades.

FOUND 2026-09-01, from the monthly review's line: "97/99 assessable rows had a DIRECT source the
judge was shown 'no' for". Traced to one helper in `_build_judge_prompt`:

    def _b(v): return "yes" if v else "no"

`None` is falsy in Python, so an UNKNOWN flag renders as a definitive "no". The rubric in the same
file tells the judge that `has_direct_source=false` plus a materiality-driven promotion is "the
highest-risk pattern: apply explicit skepticism and prefer the floor tier". So on nearly every
graded row we assert a fact we do not hold, in the direction that lowers the grade — and grades
decide which alerts fire.

NOT FIXED HERE. Fixing it moves live grades, which is the operator's call (the max_tokens fix in
the same file set that precedent explicitly). What ships instead is TRACEABILITY, which is what he
asked for: *"seems critical that we log this and make it traceable"*. These tests pin both halves —
the defect is real and characterised, and every grade now records what we held versus what we sent.
"""
from __future__ import annotations

import inspect

from agents.market_intelligence import ep_grade_judge as j


def test_unknown_still_renders_as_a_definitive_no():
    """CHARACTERISATION, not approval. This asserts the defect as it stands so that fixing it is
    a deliberate act with a failing test to update, never an accidental tidy-up of `_b`."""
    # exercise the real helper through the real prompt builder
    p_unknown = j._build_judge_prompt({"ticker": "X", "has_direct_source": None})
    p_false = j._build_judge_prompt({"ticker": "X", "has_direct_source": False})
    p_true = j._build_judge_prompt({"ticker": "X", "has_direct_source": True})
    assert "Direct source present: no" in p_unknown, (
        "if this now says 'unknown', the defect was fixed — update this test deliberately and "
        "make sure the operator signed off, because it moves live grades")
    assert "Direct source present: no" in p_false
    assert "Direct source present: yes" in p_true
    assert p_unknown == p_false, (
        "UNKNOWN and FALSE are currently indistinguishable to the judge — that is the defect")


def test_the_rubric_still_punishes_a_no_so_the_defect_has_teeth():
    """The mis-render would be harmless if the judge ignored the field. It does not: the rubric
    names a `no` as grounds to prefer the floor tier. This is what makes it a suppression bug
    rather than a cosmetic one."""
    src = inspect.getsource(j)
    assert "has_direct_source=false" in src and "prefer the floor tier" in src


def test_every_grade_records_what_we_held_versus_what_we_sent():
    """The traceability the operator asked for. MUTATION TARGET: dropping the trace, which would
    make the discrepancy invisible again in every surface we have."""
    src = inspect.getsource(j.grade_ep_with_judge) if hasattr(j, "grade_ep_with_judge") else None
    if src is None:
        import pathlib
        src = pathlib.Path("agents/market_intelligence/ep_grade_judge.py").read_text(
            encoding="utf-8")
    assert "judge_direct_source_trace" in src
    assert "UNKNOWN RENDERED AS NO" in src, (
        "the trace must SAY when the two differ — a row recording only the sent value would "
        "hide exactly the case worth finding")


def test_the_detector_ACTUALLY_PASSES_the_flag_to_the_judge():
    """THE FIX ITSELF (2026-09-01). The bug was never in the renderer — it was that
    `ep_detector`'s `assemble_judge_inputs(...)` call omitted `has_direct_source` entirely, so the
    payload took the parameter default None on every grade and `_b()` turned that into "no".

    Everything else already existed: corpus_provenance computes the flag, the catalyst cache
    preserves it across re-grades, and the prompt has a slot for it. One argument at one call site
    was missing, and it was missing from the day the call was written.

    MUTATION TARGET: dropping the argument again during a refactor of that call — which is exactly
    how it was absent for months without anyone noticing, because nothing downstream fails when a
    judge is merely misinformed."""
    import pathlib as _pl
    import re as _re

    src = _pl.Path("agents/market_intelligence/ep_detector.py").read_text(encoding="utf-8")
    call = src[src.index("payload = assemble_judge_inputs("):]
    call = call[:call.index("verdict = await grade_holistic(")]
    assert "has_direct_source=" in call, (
        "the live judge payload no longer carries has_direct_source — the judge is being told "
        "'no direct source' on every grade again, which its rubric treats as grounds to prefer "
        "the floor tier")
    assert _re.search(r"has_direct_source=r\.get\(", call), (
        "it must come from the candidate row, which is where corpus_provenance stored it")


def test_the_renderer_still_lies_about_a_GENUINE_unknown():
    """Residual, recorded rather than fixed. With the flag now wired, None means we genuinely
    could not tell (a cache miss, a provenance failure) — and `_b()` still reports that as "no".
    Left alone deliberately: the rubric defines no behaviour for "unknown", so inventing a third
    word would put an unmodelled token in front of a live grader. The trace row shows how often a
    real unknown survives, which is the evidence needed before changing it."""
    p_unknown = j._build_judge_prompt({"ticker": "X", "has_direct_source": None})
    assert "Direct source present: no" in p_unknown
