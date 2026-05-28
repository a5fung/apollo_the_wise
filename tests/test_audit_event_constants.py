"""Regression tests for the audit-events constants module (#117, 2026-05-28).

Pin the discipline:
  - Constants are uppercase Python identifiers
  - Values are lowercase snake-case strings
  - Values are unique (no two constants map to the same string)
  - Values match the audit_log convention (alphanumeric + underscore,
    starts with a letter)

If you add a new constant to `audit_events.py` with a typo or duplicate
value, these tests fail at CI time. That's the whole point of the
constants module — turn run-time silent failures (audit row written
with wrong type → predicate SQL never matches) into import-time errors.
"""
import re

import pytest


def _public_constants():
    """Return list of (name, value) for all SCREAMING_SNAKE_CASE str
    constants exported by audit_events."""
    from agents.market_intelligence import audit_events
    return [
        (name, value)
        for name, value in vars(audit_events).items()
        if not name.startswith("_")
        and name.isupper()
        and isinstance(value, str)
    ]


def test_constants_are_uppercase_snake_case_identifiers():
    """Naming convention: SCREAMING_SNAKE_CASE Python identifier."""
    pattern = re.compile(r"^[A-Z][A-Z0-9_]+$")
    for name, _value in _public_constants():
        assert pattern.match(name), f"{name!r} is not SCREAMING_SNAKE_CASE"


def test_constant_values_match_audit_log_convention():
    """Values must be lowercase snake-case strings (the convention used
    by every existing `event_type` value in mi_audit_log)."""
    pattern = re.compile(r"^[a-z][a-z0-9_]+$")
    for name, value in _public_constants():
        assert pattern.match(value), (
            f"{name} = {value!r} doesn't match lowercase snake_case"
        )


def test_constant_values_are_unique():
    """No two constants may map to the same string — catches copy-paste
    typos where a new event accidentally aliases an existing one."""
    seen: dict[str, str] = {}
    for name, value in _public_constants():
        if value in seen:
            pytest.fail(
                f"Duplicate value {value!r}: {seen[value]} and {name} both map to it"
            )
        seen[value] = name


def test_today_shipped_events_present():
    """Spot-check that the events shipped in today's session are in the
    constants module — guards against the file being silently emptied
    by a misguided refactor."""
    from agents.market_intelligence import audit_events
    # Audit events introduced or migrated 2026-05-28:
    assert audit_events.STUCK_PENDING_NEW_DETECTED == "stuck_pending_new_detected"
    assert audit_events.CATALYST_DOWNGRADE_CARVEOUT_APPLIED == "catalyst_downgrade_carveout_applied"
    assert audit_events.PARTIAL_NOW_OPERATOR_CONFIRMED == "partial_now_operator_confirmed"
    assert audit_events.SYNC_NOW_OPERATOR_CONFIRMED == "sync_now_operator_confirmed"
    assert audit_events.CATALYST_EARNINGS_REVENUE_WEAK_DOWNGRADE == \
        "catalyst_earnings_revenue_weak_downgrade"
