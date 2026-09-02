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

⚠ AND A THIRD, 2026-09-02 — the reason this file now has a second half. The guard above reads ONE
call site, so it proved the LIVE payload complete while `judge_replay_common.build_judge_payload`
— the documented mirror of that same assembly, used by the production chart-axis shadow job and
every replay script — had no `revenue_stage` parameter at all and left `has_direct_source` at
None. The shadow grader deciding whether chart-vision earns a place in the live rubric was
therefore being told "no direct source" on every ticker: the identical defect, one layer over,
still running the day after the live fix shipped. A guard scoped to one caller certifies one
caller. The second half of this file holds the MIRROR to the same bar: it must OFFER every signal
the assembler takes, so a gap is always a value someone can pass rather than a parameter that does
not exist.
"""
from __future__ import annotations

import inspect
import pathlib
import re

from agents.market_intelligence.ep_grade_judge import assemble_judge_inputs
from agents.market_intelligence.judge_replay_common import build_judge_payload

# Signals deliberately NOT passed by the live call. Each needs a real reason — "not yet" is one,
# "we decided against it" is one, silence is not.
DECLARED_UNWIRED = {
    "tape": "#329 Path A — built for the composite flip, wired by #335 (judge is load-bearing)",
    "theme_stage": "#329 Path A — same flip, same gate (#335)",
    "theme_score": "#329 Path A — same flip, same gate (#335)",
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


def test_the_two_signals_found_by_this_guard_stay_wired():
    """Both bugs this file exists for. Neither may drift back into a declaration — being
    "declared unwired" would make the original defect permanent and look deliberate.
    has_direct_source was found by the monthly review; revenue_stage was found by this guard
    within an hour of it being written, which is the whole argument for having it."""
    call = _live_call_source()
    for name in ("has_direct_source", "revenue_stage"):
        assert name not in DECLARED_UNWIRED, f"{name} must stay wired, not be declared away"
        assert f"{name}=" in call, f"{name} is no longer passed to the judge"


# ── the mirror: judge_replay_common.build_judge_payload ──────────────────────────────────
# Signals the mirror does not need to EXPOSE, each with the reason it cannot be a forgotten
# argument. Only "this function computes it itself" and "it is already a positional argument"
# qualify — "no caller fills it yet" does NOT, because that is exactly how the 09-02 gap looked.
MIRROR_NOT_EXPOSED = {
    "materiality_tier": "computed inside build_judge_payload itself (rule_materiality over the "
                        "row's own catalyst text + market cap) — passing it in would let a "
                        "caller contradict the deterministic rule",
    "grounded_text": "already a positional parameter of build_judge_payload",
    "market_cap": "already a positional parameter of build_judge_payload",
    "sector": "already a positional parameter of build_judge_payload",
}


def test_the_replay_mirror_exposes_every_signal_the_assembler_takes():
    """MUTATION TARGET: adding a signal to assemble_judge_inputs, wiring it live, and leaving the
    replay/shadow mirror without a parameter for it — which is what happened to `revenue_stage`
    on 2026-09-01 and went unnoticed because the guard above only reads ep_detector.

    A missing PARAMETER is strictly worse than a None argument: no caller can close the gap, and
    nothing anywhere reports that the shadow judge and the live judge are reading different
    prompts."""
    signals = {p for p in inspect.signature(assemble_judge_inputs).parameters if p != "r"}
    exposed = set(inspect.signature(build_judge_payload).parameters)
    missing = sorted(signals - exposed - set(MIRROR_NOT_EXPOSED))
    assert not missing, (
        f"build_judge_payload cannot pass judge signal(s) {missing} — the shadow/replay graders "
        f"would silently grade a different prompt than live. Add the parameter (default None) and "
        f"forward it, or add it to MIRROR_NOT_EXPOSED with a reason that is not 'no caller needs "
        f"it yet'.")


def test_the_mirror_actually_forwards_what_it_exposes():
    """A parameter that is accepted and then dropped on the floor is worse than no parameter: the
    call site reads as correct. Checks the forwarding text, not just the signature."""
    src = inspect.getsource(build_judge_payload)
    body = src[src.index("assemble_judge_inputs("):]
    exposed = [p for p in inspect.signature(build_judge_payload).parameters
               if p not in ("row", "grounded_text", "market_cap", "sector")]
    dropped = [p for p in exposed if f"{p}=" not in body]
    assert not dropped, f"build_judge_payload accepts but never forwards: {dropped}"


def test_mirror_exemptions_are_not_stale():
    """Same rot rule as DECLARED_UNWIRED: an exemption for a parameter that no longer exists would
    let a future parameter of that name slip through unnoticed."""
    signals = {p for p in inspect.signature(assemble_judge_inputs).parameters if p != "r"}
    stale = [k for k in MIRROR_NOT_EXPOSED if k not in signals]
    assert not stale, f"MIRROR_NOT_EXPOSED names parameters that no longer exist: {stale}"


def test_the_chart_axis_shadow_job_recovers_has_direct_source():
    """The production caller this guard was extended for. The shadow job replays STORED alert rows
    and mi_ep_alerts has no has_direct_source column, so the value must be RECOMPUTED from the
    stored grounded_text — leaving it None means the judge is told a confident "no" on every
    ticker (_b renders falsy as "no"), which is the whole bug."""
    src = pathlib.Path("agents/market_intelligence/scheduler.py").read_text(encoding="utf-8")
    job = src[src.index("async def _chart_axis_shadow_job("):]
    job = job[:job.index("build_judge_payload(") + 400]
    assert "recompute_has_direct_source(" in job, (
        "the chart-axis shadow job no longer recomputes has_direct_source — its judge is back to "
        "being told 'no direct source' on every ticker")
    assert "has_direct_source=" in job, "recomputed but not passed"
