"""A per-role pin moves ONE role and leaves the rest of its tier tracking (2026-09-29).

claude-sonnet-5-5 refused every theme prompt while grading normally on catalyst grades, so the
theme roles were pinned back to claude-sonnet-5 without moving the money-path sonnet roles.
"""
from shared import llm_models


def test_pinned_theme_roles_resolve_to_the_pin():
    for role, pin in llm_models._ROLE_OVERRIDES.items():
        if pin:
            assert role in llm_models.RESOLVED_ROLES, f"{role} is not a tracked role — the pin does nothing"
            assert llm_models.effective_model(role) == pin
            assert llm_models.role_resolution(role).source == "override"


def test_a_role_pin_does_not_move_the_rest_of_its_tier():
    pinned = {r for r, v in llm_models._ROLE_OVERRIDES.items() if v}
    for role, tier in llm_models.RESOLVED_ROLES.items():
        if role in pinned or llm_models._TIER_OVERRIDES.get(tier):
            continue
        assert llm_models.role_resolution(role).source != "override", role
