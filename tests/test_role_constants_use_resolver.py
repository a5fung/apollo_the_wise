"""Every auto-tracked role CONSTANT must bind to the resolver, not the raw tier pin (2026-08-06).

⚠ WHY THIS EXISTS — the model-tracking work shipped 2026-07-31 and did NOT take effect, and the
gap was invisible for a week because the two halves disagreed silently:

    RESOLVED_ROLES had every role opted in, and effective_model("THEME_MODEL") returned
    claude-sonnet-5 correctly. But the module-level constant read `THEME_MODEL = SONNET`, and
    SONNET is SONNET_PIN = "claude-sonnet-4-6". Every call site imports the CONSTANT.

So the resolver was right and nothing used it. Measured on 2026-08-06: **28 of that day's 34
Sonnet calls still ran on claude-sonnet-4-6**, a week after "everything is updated" was reported —
including catalyst grading, theme assignment, discovery, validation, narrative discovery and
synthesis. Only the judge was current, and only because OPUS_PIN had been bumped BY HAND on 08-03.

Operator: *"we went through a whole process to update EVERYTHING… and a week later you say it's not
updated"* and *"you said model update is automatic which isn't"*. He is right. The pins are a
FALLBACK for when the resolver cannot answer; they were never meant to be what production calls.

This test is the thing that makes the two halves agree, because a human reading either half alone
sees something that looks correct.
"""
import ast
import pathlib

SRC = pathlib.Path("shared/llm_models.py").read_text()
TREE = ast.parse(SRC)


def _module_assignments():
    """{name: the source text of its value} for module-level `NAME = <expr>`."""
    out = {}
    for node in TREE.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            out[node.targets[0].id] = ast.get_source_segment(SRC, node.value)
    return out


def test_every_resolved_role_constant_calls_the_resolver():
    """The load-bearing assertion. A role opted into RESOLVED_ROLES but bound to a raw tier is the
    exact defect: it reads as auto-tracked and is not."""
    from shared.llm_models import RESOLVED_ROLES
    assigns = _module_assignments()
    stale = []
    for role in RESOLVED_ROLES:
        val = assigns.get(role)
        if val is None:
            continue  # not a module-level constant; nothing for a caller to import staly
        if "effective_model" not in val:
            stale.append(f"{role} = {val}")
    assert not stale, (
        "these roles are opted into RESOLVED_ROLES but bind to a raw tier pin, so every call site "
        "importing the constant gets the STALE pin while effective_model() reports the new model:\n  "
        + "\n  ".join(stale))


def test_the_raw_tier_constants_are_still_available_as_a_FALLBACK():
    """Not a cleanup — the pins remain the offline fallback the resolver degrades to. Deleting them
    would make a resolver outage fatal instead of merely stale."""
    import shared.llm_models as m
    for pin in ("SONNET_PIN", "OPUS_PIN", "HAIKU_PIN"):
        assert getattr(m, pin), f"{pin} must remain as the resolver's fallback"


def test_a_role_bound_to_a_bare_tier_is_caught_even_with_a_trailing_comment():
    """The original defect lines carried explanatory comments; a naive check that matched only
    `ROLE = TIER` exactly would have missed several of them."""
    assigns = _module_assignments()
    for role, val in assigns.items():
        if role.endswith("_MODEL") and val in ("SONNET", "OPUS", "HAIKU"):
            from shared.llm_models import RESOLVED_ROLES
            assert role not in RESOLVED_ROLES, (
                f"{role} is auto-tracked but bound to the bare tier {val}")


def test_resolution_is_observable_per_role():
    """The bug hid because nothing surfaced the disagreement. `role_resolution` is how a human can
    see what a role actually resolved to and why — keep it."""
    import shared.llm_models as m
    assert hasattr(m, "role_resolution")
