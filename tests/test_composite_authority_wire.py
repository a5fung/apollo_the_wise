"""M1-d (ADR 0024 §6) — composite-authority wire-in safety tests.

Pins the two load-bearing invariants of the DARK wire-in:
1. The DB toggle FAILS CLOSED — missing row or any error → False → the wire-in block
   in ep_detector._judge_shadow is a no-op and the grade path is byte-identical to
   pre-M1-d (the dark guarantee). Fail-OPEN here would silently make composition
   load-bearing with no operator flip — the single worst outcome.
2. resolve_composite_tier is a strict passthrough unless the composed tier actually
   MOVES — authority flips to 'composite' / override to True only on a real move;
   otherwise the base decision (floor/judge/fallback + its override flag) stands
   exactly as _resolve_grade_authority set it.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.market_intelligence import db
from agents.market_intelligence.meta_rubric_compose import (
    Composition,
    resolve_composite_tier,
)


# ── DB toggle: FAIL-CLOSED (the byte-identical / dark guarantee) ─────────────


def test_composite_toggle_fails_closed_on_db_error(monkeypatch):
    async def _boom():
        raise RuntimeError("db unreachable")
    monkeypatch.setattr(db, "get_pool", _boom)
    # Exception path → base grade (False), never composite.
    assert asyncio.run(db.get_composite_authority_enabled()) is False


def test_composite_toggle_defaults_false_no_row(monkeypatch):
    """THE dark guarantee: with no mi_safeguard_state row (no operator flip ever),
    the toggle reads False and the wire-in never runs — byte-identical grade path."""
    class _Conn:
        async def fetchrow(self, *a, **k):
            return None  # no toggle row yet (dormant default)

    class _Acq:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, *a):
            return False

    class _Pool:
        def acquire(self):
            return _Acq()

    async def _pool():
        return _Pool()
    monkeypatch.setattr(db, "get_pool", _pool)
    assert asyncio.run(db.get_composite_authority_enabled()) is False


def test_composite_toggle_reads_on_row(monkeypatch):
    # Sanity: an operator-flipped 'on' row DOES read True (the toggle can turn on).
    class _Conn:
        async def fetchrow(self, *a, **k):
            return {"state": "on"}

    class _Acq:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, *a):
            return False

    class _Pool:
        def acquire(self):
            return _Acq()

    async def _pool():
        return _Pool()
    monkeypatch.setattr(db, "get_pool", _pool)
    assert asyncio.run(db.get_composite_authority_enabled()) is True


# ── resolve_composite_tier (pure decision) ───────────────────────────────────


def _credit(steps, marker="accelerating"):
    return {"axis": "theme", "credit_steps": steps, "marker": marker, "reason": "test"}


def test_zero_credit_passthrough():
    # (a) credit_steps=0 → tier/authority/override unchanged; Composition still present.
    tier, auth, over, comp = resolve_composite_tier(
        "MODERATE", "judge", True, [_credit(0, marker="none")])
    assert (tier, auth, over) == ("MODERATE", "judge", True)
    assert isinstance(comp, Composition)
    assert comp.base_tier == "MODERATE" and comp.final_tier == "MODERATE"
    assert comp.net_capped == 0


def test_moderate_plus_one_composes_high():
    # (b) MODERATE + theme +1 → HIGH, authority='composite', override=True.
    tier, auth, over, comp = resolve_composite_tier("MODERATE", "floor", False, [_credit(1)])
    assert (tier, auth, over) == ("HIGH", "composite", True)
    assert comp.final_tier == "HIGH" and comp.net_capped == 1


def test_none_plus_one_composes_moderate():
    # (c) 'none' + 1 → MODERATE (composition works from the lattice bottom).
    tier, auth, over, comp = resolve_composite_tier("none", "floor", False, [_credit(1)])
    assert (tier, auth, over) == ("MODERATE", "composite", True)


def test_high_plus_one_clamped_is_passthrough():
    # (d) HIGH + 1 → clamped at HIGH; tier didn't move → the base authority stands
    # (NOT 'composite') — an unchanged tier must not masquerade as a composed one.
    tier, auth, over, comp = resolve_composite_tier("HIGH", "judge", True, [_credit(1)])
    assert (tier, auth, over) == ("HIGH", "judge", True)
    assert comp.final_tier == "HIGH" and comp.net_capped == 1  # clamped in the lattice


def test_passthrough_preserves_incoming_authority_and_override():
    # (e) no move → the incoming (authority, override) pair is preserved verbatim,
    # whatever _resolve_grade_authority produced (floor/False, fallback/True, ...).
    tier, auth, over, comp = resolve_composite_tier("MODERATE", "fallback", True, [_credit(0)])
    assert (tier, auth, over) == ("MODERATE", "fallback", True)
    tier, auth, over, comp = resolve_composite_tier("MODERATE", "floor", False, [])
    assert (tier, auth, over) == ("MODERATE", "floor", False)
    assert isinstance(comp, Composition)  # trace always returned, even on empty credits
