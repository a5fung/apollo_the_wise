"""ADR 0015 (#328) — theme axis credit, SHADOW ONLY. Focused tests for:

  • theme_axis_credit() — the pure stage→credit function, one test per ADR
    table row (docs/decisions/0015-theme-axis-meta-rubric.md) + a boost-only
    sweep pinning that no negative path exists.
  • apply_theme_axis_step() — the pure label-stepper.
  • derive_theme_coverage_state() — the #319 blind-spot/standalone/unknown
    classifier, reusing briefing.py's exact source signal (membership +
    fire_axes).
  • log_theme_axis_adjusted_shadow() — the SHADOW writer: fires the audit
    event when informative, stays silent otherwise, NEVER mutates the `r`
    dict it's handed (THE LINE — the live grade must be untouched), and
    NEVER raises.

SHADOW ONLY — none of this touches the live grade / judge output / trade
state. See docs/decisions/0015-theme-axis-meta-rubric.md for the full design.
"""
from __future__ import annotations

import asyncio
import copy
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence.catalyst_rubric_runtime import (
    apply_theme_axis_step,
    derive_theme_coverage_state,
    log_theme_axis_adjusted_shadow,
    theme_axis_credit,
)


def _run(coro):
    return asyncio.run(coro)


# ─── theme_axis_credit — one test per ADR table row ────────────────────────


def test_accelerating_unconditional_full_credit_no_context_needed():
    """Accelerating -> +1 tier-step, UNCONDITIONAL — no composite/label context
    required (the NBIS case, Pradeep #1 catalyst driver)."""
    result = theme_axis_credit({"stage": "Accelerating", "score": 92.0})
    assert result == {
        "credit_steps": 1,
        "marker": "accelerating",
        "reason": (
            "Accelerating theme membership — unconditional +1 tier-step "
            "(Pradeep #1 catalyst driver)"
        ),
    }


def test_accelerating_full_credit_even_with_composite_context_present():
    """Accelerating stays unconditional even when composite/label ARE supplied
    — it must not accidentally start gating on the boundary like Nascent."""
    result = theme_axis_credit(
        {"stage": "Accelerating"}, label="weak", composite_scaled=1.0,
    )
    assert result["credit_steps"] == 1
    assert result["marker"] == "accelerating"


def test_nascent_within_near_miss_band_gets_credit():
    """Nascent + composite within ~10% below the next boundary -> +1 step.
    routine->strong boundary = 22.0; 22*0.90 = 19.8 <= 21.5 < 22 -> in band."""
    result = theme_axis_credit(
        {"stage": "Nascent"}, label="routine", composite_scaled=21.5,
    )
    assert result["credit_steps"] == 1
    assert result["marker"] == "nascent_near_miss"


def test_nascent_outside_near_miss_band_gets_zero():
    """Nascent + composite well below the boundary (outside the ~10% band)
    -> no credit; marker collapses to the generic 'none'."""
    result = theme_axis_credit(
        {"stage": "Nascent"}, label="routine", composite_scaled=15.0,
    )
    assert result["credit_steps"] == 0
    assert result["marker"] == "none"


def test_nascent_missing_composite_context_falls_back_to_zero():
    """Nascent with no composite/label context supplied at all -> safe
    fallback to zero credit (never guesses toward a boost)."""
    result = theme_axis_credit({"stage": "Nascent"})
    assert result == {
        "credit_steps": 0,
        "marker": "none",
        "reason": (
            "Nascent theme but composite is outside the ~10% near-miss "
            "band (or no composite/label context supplied) — no credit"
        ),
    }


def test_mainstream_on_boundary_tie_gets_credit():
    """Mainstream + composite on a genuine boundary TIE (much tighter than
    Nascent's near-miss band) -> +1 step. 22*0.98=21.56 <= 21.6 < 22 -> tie."""
    result = theme_axis_credit(
        {"stage": "Mainstream"}, label="routine", composite_scaled=21.6,
    )
    assert result["credit_steps"] == 1
    assert result["marker"] == "mainstream_tiebreak"


def test_mainstream_not_a_tie_gets_zero_even_inside_nascent_band():
    """Mainstream must NOT get Nascent's wider near-miss-band credit —
    composite=21.0 is inside the 10% near-miss band (19.8-22) but OUTSIDE
    the 2% tie-break band (21.56-22) -> zero credit for Mainstream."""
    result = theme_axis_credit(
        {"stage": "Mainstream"}, label="routine", composite_scaled=21.0,
    )
    assert result["credit_steps"] == 0
    assert result["marker"] == "none"


def test_mainstream_missing_context_falls_back_to_zero():
    result = theme_axis_credit({"stage": "Mainstream"})
    assert result["credit_steps"] == 0
    assert result["marker"] == "none"


def test_fading_zero_credit_never_negative():
    """Fading -> 0 credit, marker 'fading'. Validated NOT poison (+11.1% in
    the STEP-0 calibration) — merely not special; boost-only means never
    penalized either."""
    result = theme_axis_credit({"stage": "Fading", "score": 41.0})
    assert result["credit_steps"] == 0
    assert result["marker"] == "fading"


def test_retired_defensive_same_as_fading():
    """Retired shouldn't reach this function in practice (get_theme_membership
    filters stage != 'Retired'), but the ADR collapses Fading/Retired into one
    row — defensive parity, never negative."""
    result = theme_axis_credit({"stage": "Retired"})
    assert result["credit_steps"] == 0
    assert result["marker"] == "fading"


def test_blind_spot_zero_credit_no_penalty():
    """#325 coverage blind spot: no tracked cohort but judge lit theme/
    narrative -> 0 credit, marker 'blind_spot' (unknown != absent)."""
    result = theme_axis_credit(None, "blind_spot")
    assert result["credit_steps"] == 0
    assert result["marker"] == "blind_spot"


def test_standalone_zero_credit():
    """#319 genuine standalone: no tracked cohort, judge lit no theme/
    narrative -> 0 credit, marker 'standalone'."""
    result = theme_axis_credit(None, "standalone")
    assert result["credit_steps"] == 0
    assert result["marker"] == "standalone"


def test_no_membership_no_coverage_signal_falls_back_to_none_marker():
    result = theme_axis_credit(None, None)
    assert result["credit_steps"] == 0
    assert result["marker"] == "none"


def test_no_membership_unknown_coverage_state_falls_back_to_none_marker():
    """coverage_state='unknown' (judge-silent) is not itself a credit signal —
    same zero-credit fallback as no signal at all."""
    result = theme_axis_credit(None, "unknown")
    assert result["credit_steps"] == 0
    assert result["marker"] == "none"


def test_unrecognized_stage_string_safe_default():
    """A garbage/unexpected stage string (schema drift) must never crash or
    guess a boost — safe zero-credit default."""
    result = theme_axis_credit({"stage": "SomeFutureStage"})
    assert result["credit_steps"] == 0
    assert result["marker"] == "none"


# ─── Boost-only pin — no negative path exists anywhere in the function ─────


@pytest.mark.parametrize("stage", [
    "Accelerating", "Nascent", "Mainstream", "Fading", "Retired", "Bogus", None,
])
@pytest.mark.parametrize("coverage_state", [None, "blind_spot", "standalone", "unknown"])
@pytest.mark.parametrize("label", [None, "weak", "routine", "strong", "game_changer", "bogus"])
@pytest.mark.parametrize("composite_scaled", [None, -100.0, 0.0, 14.0, 21.9, 22.0, 30.0, 50.0])
def test_boost_only_credit_steps_never_negative_and_at_most_one(
    stage, coverage_state, label, composite_scaled,
):
    """Property sweep: across every stage / coverage_state / label / composite
    combination, credit_steps is ALWAYS in {0, 1} — never negative. This is
    the hard guardrail from the 6/5 evidence (naive theme-gating refuted);
    absence/weakness of a theme signal can only ever settle at zero."""
    membership = {"stage": stage} if stage is not None else None
    result = theme_axis_credit(
        membership, coverage_state, label=label, composite_scaled=composite_scaled,
    )
    assert result["credit_steps"] in (0, 1)
    assert result["marker"] in (
        "accelerating", "nascent_near_miss", "mainstream_tiebreak",
        "fading", "standalone", "blind_spot", "none",
    )


# ─── apply_theme_axis_step — pure label stepper ────────────────────────────


def test_apply_step_routine_to_strong():
    assert apply_theme_axis_step("routine", 1) == "strong"


def test_apply_step_strong_to_game_changer():
    assert apply_theme_axis_step("strong", 1) == "game_changer"


def test_apply_step_capped_at_top_tier():
    """game_changer is already the top tier — a step is a no-op, never errors."""
    assert apply_theme_axis_step("game_changer", 1) == "game_changer"


def test_apply_step_zero_credit_no_op():
    assert apply_theme_axis_step("weak", 0) == "weak"


def test_apply_step_none_label_passthrough():
    assert apply_theme_axis_step(None, 1) is None


def test_apply_step_unrecognized_label_passthrough():
    assert apply_theme_axis_step("bogus", 1) == "bogus"


# ─── derive_theme_coverage_state — #319 reuse, not re-derivation ──────────


def test_coverage_state_none_when_membership_present():
    """coverage_state is only meaningful for THEMELESS names."""
    assert derive_theme_coverage_state({"stage": "Accelerating"}, ["theme"]) is None
    assert derive_theme_coverage_state({"stage": "Accelerating"}, None) is None


def test_coverage_state_blind_spot_when_axes_light_theme():
    assert derive_theme_coverage_state(None, ["theme"]) == "blind_spot"


def test_coverage_state_blind_spot_when_axes_light_narrative():
    assert derive_theme_coverage_state(None, ["narrative", "catalyst"]) == "blind_spot"


def test_coverage_state_standalone_when_axes_rendered_without_theme():
    assert derive_theme_coverage_state(None, ["catalyst"]) == "standalone"


def test_coverage_state_standalone_when_axes_empty_list():
    """An empty list means the judge DID render a verdict and lit nothing —
    still a genuine standalone, distinct from a None (judge-silent) verdict."""
    assert derive_theme_coverage_state(None, []) == "standalone"


def test_coverage_state_unknown_when_judge_silent():
    """fire_axes is None -> the judge rendered NO verdict at all — distinct
    from a genuine standalone (briefing.py's JUDGE-SILENT case)."""
    assert derive_theme_coverage_state(None, None) == "unknown"


# ─── log_theme_axis_adjusted_shadow — the writer (mocked deps) ─────────────


def _base_r():
    from datetime import date
    return {
        "ticker": "NBIS", "alert_date": date(2026, 7, 4),
        "score_tier": "HIGH", "fire_axes": ["theme"],
    }


def test_shadow_never_mutates_r(monkeypatch):
    """THE LINE pin: the shadow computation must leave the caller's `r` dict
    byte-identical — the live grade the judge/floor/every downstream consumer
    sees is untouched, regardless of what credit fires."""
    r = _base_r()
    r_before = copy.deepcopy(r)

    async def _fake_lookup(ticker, alert_date):
        return {"q_revenue_usd": {"yoy_pct": 30.0}}  # truthy -> proceeds to scoring

    def _fake_rubric(ticker, extracted, today):
        # score_ep_with_rubric touches yfinance internally — bypass it here so
        # this unit test stays deterministic/offline; the label/composite are
        # the only things theme_axis_credit reads from its output.
        return {"label": "routine", "composite_scaled": 18.0}

    async def _fake_membership(ticker):
        return {"name": "Neo AI", "stage": "Accelerating", "score": 92.0, "theme_date": "2026-07-01"}

    audit_calls = []

    async def _fake_audit(event_type, summary, detail=""):
        audit_calls.append((event_type, summary, detail))

    monkeypatch.setattr(
        "agents.market_intelligence.catalyst_metrics_extractor.lookup_cached_metrics",
        _fake_lookup,
    )
    monkeypatch.setattr(
        "agents.market_intelligence.catalyst_rubric_runtime.score_ep_with_rubric",
        _fake_rubric,
    )
    monkeypatch.setattr(
        "agents.market_intelligence.catalyst_rubric_runtime.get_theme_membership",
        _fake_membership,
    )
    monkeypatch.setattr("agents.market_intelligence.db.log_audit_event", _fake_audit)

    _run(log_theme_axis_adjusted_shadow(r))

    assert r == r_before  # untouched — no key added/removed/changed
    assert len(audit_calls) == 1  # Accelerating fired -> informative
    assert audit_calls[0][0] == "theme_axis_shadow_adjusted"


def test_shadow_silent_when_marker_none_and_label_unchanged(monkeypatch):
    """No theme, no coverage signal -> marker 'none' and adjusted==live ->
    the shadow must stay SILENT (no audit event) — not every scored HIGH
    should spam an uninformative row."""
    r = _base_r()
    r["fire_axes"] = None  # judge-silent -> coverage_state 'unknown'

    async def _fake_lookup(ticker, alert_date):
        return {"q_revenue_usd": {"yoy_pct": 30.0}}

    def _fake_rubric(ticker, extracted, today):
        return {"label": "routine", "composite_scaled": 18.0}

    async def _fake_membership(ticker):
        return None

    audit_calls = []

    async def _fake_audit(event_type, summary, detail=""):
        audit_calls.append((event_type, summary, detail))

    monkeypatch.setattr(
        "agents.market_intelligence.catalyst_metrics_extractor.lookup_cached_metrics",
        _fake_lookup,
    )
    monkeypatch.setattr(
        "agents.market_intelligence.catalyst_rubric_runtime.score_ep_with_rubric",
        _fake_rubric,
    )
    monkeypatch.setattr(
        "agents.market_intelligence.catalyst_rubric_runtime.get_theme_membership",
        _fake_membership,
    )
    monkeypatch.setattr("agents.market_intelligence.db.log_audit_event", _fake_audit)

    _run(log_theme_axis_adjusted_shadow(r))
    assert audit_calls == []


def test_shadow_silent_when_no_cached_extraction(monkeypatch):
    """No cached rubric extraction -> rubric can't score -> nothing to
    shadow; must return cleanly without calling membership lookup or audit."""
    r = _base_r()

    async def _fake_lookup(ticker, alert_date):
        return None

    membership_called = []

    async def _fake_membership(ticker):
        membership_called.append(ticker)
        return None

    audit_calls = []

    async def _fake_audit(event_type, summary, detail=""):
        audit_calls.append((event_type, summary, detail))

    monkeypatch.setattr(
        "agents.market_intelligence.catalyst_metrics_extractor.lookup_cached_metrics",
        _fake_lookup,
    )
    monkeypatch.setattr(
        "agents.market_intelligence.catalyst_rubric_runtime.get_theme_membership",
        _fake_membership,
    )
    monkeypatch.setattr("agents.market_intelligence.db.log_audit_event", _fake_audit)

    _run(log_theme_axis_adjusted_shadow(r))
    assert audit_calls == []
    assert membership_called == []


def test_shadow_never_raises_on_internal_failure(monkeypatch):
    """A failure anywhere inside (e.g. get_theme_membership raising) must be
    swallowed to its own audit event — the shadow can never disturb the scan."""
    r = _base_r()

    async def _fake_lookup(ticker, alert_date):
        return {"q_revenue_usd": {"yoy_pct": 30.0}}

    def _fake_rubric(ticker, extracted, today):
        return {"label": "routine", "composite_scaled": 18.0}

    async def _boom(ticker):
        raise RuntimeError("db unavailable")

    audit_calls = []

    async def _fake_audit(event_type, summary, detail=""):
        audit_calls.append((event_type, summary, detail))

    monkeypatch.setattr(
        "agents.market_intelligence.catalyst_metrics_extractor.lookup_cached_metrics",
        _fake_lookup,
    )
    monkeypatch.setattr(
        "agents.market_intelligence.catalyst_rubric_runtime.score_ep_with_rubric",
        _fake_rubric,
    )
    monkeypatch.setattr(
        "agents.market_intelligence.catalyst_rubric_runtime.get_theme_membership",
        _boom,
    )
    monkeypatch.setattr("agents.market_intelligence.db.log_audit_event", _fake_audit)

    _run(log_theme_axis_adjusted_shadow(r))  # must not raise
    assert len(audit_calls) == 1
    assert audit_calls[0][0] == "theme_axis_credit_shadow_failed"


def test_shadow_missing_ticker_or_alert_date_is_a_noop():
    r = {"score_tier": "HIGH"}  # no ticker/alert_date
    _run(log_theme_axis_adjusted_shadow(r))  # must not raise
