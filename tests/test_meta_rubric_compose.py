"""ADR 0024 M1-a — golden tests for compose_final_tier (dark meta-rubric composition).
Pins: the ±1 net cap (F2), lattice clamps, fallback-on-floor, Fading=0, dark-by-default.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.market_intelligence.meta_rubric_compose import (
    compose_final_tier,
    composite_authority_enabled,
    NET_CAP,
)


def _credit(axis, steps, marker="", reason=""):
    return {"axis": axis, "credit_steps": steps, "marker": marker, "reason": reason}


# ── golden cases named in the ADR M1-a row ──
def test_nbis_boost_moderate_to_high():
    # NBIS-class: MODERATE base, theme Accelerating +1 → HIGH.
    final, comp = compose_final_tier("MODERATE", [_credit("theme", 1, "Accelerating")])
    assert final == "HIGH"
    assert comp.net_raw == 1 and comp.net_capped == 1
    assert comp.contributions[0].axis == "theme" and comp.contributions[0].marker == "Accelerating"


def test_cap_clip_net_exceeds_one():
    # theme +1 and structure +1 → raw +2, but the ±1 stacking cap holds it to +1 → HIGH (not above).
    final, comp = compose_final_tier("MODERATE", [_credit("theme", 1), _credit("structure", 1)])
    assert comp.net_raw == 2 and comp.net_capped == NET_CAP == 1
    assert final == "HIGH"


def test_fallback_composes_on_floor():
    # authority=floor → base IS the floor tier; the SAME function composes (no separate path).
    final, comp = compose_final_tier("MODERATE", [_credit("theme", 1, "Accelerating")])
    assert final == "HIGH" and comp.base_tier == "MODERATE"  # identical to the judge-base path


def test_fading_theme_contributes_zero():
    final, comp = compose_final_tier("HIGH", [_credit("theme", 0, "Fading")])
    assert final == "HIGH" and comp.net_raw == 0 and comp.net_capped == 0


# ── lattice clamps + neg axis ──
def test_clamp_at_high_ceiling():
    # already HIGH + a boost → cannot compose above HIGH.
    final, comp = compose_final_tier("HIGH", [_credit("theme", 1)])
    assert final == "HIGH" and comp.net_capped == 1


def test_neg_axis_demote_and_floor_clamp():
    # two dilution demotes → raw −2, capped to −1, MODERATE → none (can't go below none).
    final, comp = compose_final_tier("MODERATE",
                                     [_credit("dilution", -1), _credit("dilution", -1)])
    assert comp.net_raw == -2 and comp.net_capped == -1
    assert final == "none"


def test_no_credits_is_identity():
    final, comp = compose_final_tier("MODERATE", [])
    assert final == "MODERATE" and comp.net_raw == 0 and comp.contributions == []


def test_bad_base_tier_raises():
    with pytest.raises(ValueError):
        compose_final_tier("BOGUS", [])


class _ObjCredit:
    """An axis may emit an object credit (with .credit_steps), not just a dict."""
    def __init__(self, axis, credit_steps):
        self.axis = axis
        self.credit_steps = credit_steps


def test_object_credits_also_supported():
    final, comp = compose_final_tier("MODERATE", [_ObjCredit("theme", 1)])
    assert final == "HIGH" and comp.contributions[0].steps == 1


# ── dark by default ──
def test_composite_authority_dark_by_default(monkeypatch):
    monkeypatch.delenv("COMPOSITE_AUTHORITY", raising=False)
    assert composite_authority_enabled() is False
    monkeypatch.setenv("COMPOSITE_AUTHORITY", "true")
    assert composite_authority_enabled() is True
    monkeypatch.setenv("COMPOSITE_AUTHORITY", "false")
    assert composite_authority_enabled() is False
