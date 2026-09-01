"""Every signal the judge's prompt can render must be WIRED or DECLARED — never silently absent.

HOW THE 2026-09-01 BUG SURVIVED FOR MONTHS. `ep_detector` builds the judge payload by calling
`assemble_judge_inputs(...)`. That function takes twelve optional signals. The live call passed
eight. `has_direct_source` was simply not among them, so it took the parameter default `None` on
every grade — and `_build_judge_prompt`'s `_b()` renders falsy as a definitive "no", which the
rubric treats as grounds to prefer the floor tier.

Nothing failed. No exception, no missing row, no alert. A judge that is merely MISINFORMED still
returns a grade, so every downstream surface looked healthy. The only thing that could see it was a
report that recomputes the truth and compares — the monthly review — which means a live-path bug
carried a THIRTY-DAY detection lag. The operator's words: *"catching at monthly review is 1 month
lag which is too much for live path bug."*

This test moves detection to commit time. A parameter that is neither passed by the live call nor
explicitly declared unwired — WITH a reason — fails the build. Forgetting an argument is no longer
survivable; deciding not to send one is, as long as you say so.

⚠ It found a SECOND instance immediately: `revenue_stage` is computed live (ep_detector ~4324),
rendered into the prompt (~383) and never passed either. It is declared below rather than silently
fixed, because wiring it moves live grades and that is the operator's call.
"""
from __future__ import annotations

import inspect
import pathlib
import re

from agents.market_intelligence.ep_grade_judge import assemble_judge_inputs

# Signals deliberately NOT passed by the live call. Each needs a real reason — "not yet" is one,
# "we decided against it" is one, silence is not.
DECLARED_UNWIRED = {
    "tape": "#329 Path A — built for the composite flip, wired by #335 (judge is load-bearing)",
    "theme_stage": "#329 Path A — same flip, same gate (#335)",
    "theme_score": "#329 Path A — same flip, same gate (#335)",
    "revenue_stage": (
        "⚠ NOT a decision — a GAP found 2026-09-01 by this very test, and the same defect class "
        "as has_direct_source: computed live in ep_detector (~4324), rendered into the prompt "
        "(~383) as `Revenue-stage: {_b(...)}`, and never passed, so the judge is told 'no' on "
        "every grade regardless of truth. Unlike has_direct_source it is not on the candidate "
        "row, so wiring it needs plumbing AND it moves live grades — the operator's call, "
        "surfaced 2026-09-01. Remove this entry when it is wired or when he rules it out."
    ),
}


def _live_call_source() -> str:
    src = pathlib.Path("agents/market_intelligence/ep_detector.py").read_text(encoding="utf-8")
    call = src[src.index("payload = assemble_judge_inputs("):]
    return call[:call.index("verdict = await grade_holistic(")]


def test_every_judge_signal_is_wired_or_declared():
    """MUTATION TARGET: adding a parameter to assemble_judge_inputs and forgetting to pass it —
    which is precisely what happened, and what nothing else in the suite would notice."""
    params = [p for p in inspect.signature(assemble_judge_inputs).parameters if p != "r"]
    call = _live_call_source()
    passed = set(re.findall(r"(\w+)=", call))

    unaccounted = [p for p in params if p not in passed and p not in DECLARED_UNWIRED]
    assert not unaccounted, (
        f"judge payload signal(s) neither passed nor declared: {unaccounted}. A signal that is "
        f"rendered into the prompt but never supplied does not fail loudly — the judge is simply "
        f"told the default, and every downstream surface still looks healthy. Pass it, or add it "
        f"to DECLARED_UNWIRED with a reason.")


def test_declarations_are_not_stale():
    """A declaration for a parameter that no longer exists is rot — it would let a future
    parameter of the same name pass unnoticed."""
    params = {p for p in inspect.signature(assemble_judge_inputs).parameters if p != "r"}
    stale = [k for k in DECLARED_UNWIRED if k not in params]
    assert not stale, f"DECLARED_UNWIRED names parameters that no longer exist: {stale}"


def test_declarations_carry_a_real_reason():
    """'TODO' is not a decision. Each entry must say something a reader can act on."""
    for name, reason in DECLARED_UNWIRED.items():
        assert len(reason) > 40, f"{name}'s declaration is too thin to be a decision: {reason!r}"


def test_has_direct_source_is_wired_not_declared():
    """The bug this file exists for. It must never drift back into a declaration — being
    'declared unwired' would make the original defect permanent and look deliberate."""
    assert "has_direct_source" not in DECLARED_UNWIRED
    assert "has_direct_source=" in _live_call_source()
