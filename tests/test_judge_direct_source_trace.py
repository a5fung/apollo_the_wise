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
