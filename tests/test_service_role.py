"""#256 W2 — service-role / execution-mode coherence gate (2026-06-13).

The boot assertion is safety-critical: a misread SERVICE_ROLE must NEVER fall
back to 'combined' (= two services both running the execution job set + both
consuming the trade stream = double order execution). These pin the fail-loud
contract. The role helpers default to pre-split behavior (combined/inprocess).
"""
import pytest

from agents.market_intelligence import constants


@pytest.fixture
def role(monkeypatch):
    """Set SERVICE_ROLE / EXECUTION_MODE on the module, return the assert fn."""
    def _set(service_role, execution_mode):
        monkeypatch.setattr(constants, "SERVICE_ROLE", service_role)
        monkeypatch.setattr(constants, "EXECUTION_MODE", execution_mode)
        return constants
    return _set


def test_default_combined_inprocess_is_coherent(role):
    c = role("combined", "inprocess")
    c.assert_service_role_coherent()  # must not raise — pre-split default
    assert c.runs_execution_jobs() is True
    assert c.runs_intelligence_jobs() is True


def test_split_roles_are_coherent_with_http(role):
    for r in ("execution", "intelligence"):
        c = role(r, "http")
        c.assert_service_role_coherent()
    assert role("execution", "http").runs_execution_jobs() is True
    assert role("execution", "http").runs_intelligence_jobs() is False
    assert role("intelligence", "http").runs_intelligence_jobs() is True
    assert role("intelligence", "http").runs_execution_jobs() is False


def test_invalid_role_fails_loud(role):
    c = role("worker", "inprocess")
    with pytest.raises(RuntimeError, match="SERVICE_ROLE='worker' invalid"):
        c.assert_service_role_coherent()


def test_invalid_mode_fails_loud(role):
    c = role("combined", "grpc")
    with pytest.raises(RuntimeError, match="EXECUTION_MODE='grpc' invalid"):
        c.assert_service_role_coherent()


def test_http_with_combined_fails_loud(role):
    # The dangerous combo: a single process told to HTTP-call itself. Must NOT
    # boot — this is the guard against a half-configured cutover.
    c = role("combined", "http")
    with pytest.raises(RuntimeError, match="EXECUTION_MODE=http requires"):
        c.assert_service_role_coherent()


def test_intelligence_inprocess_allowed(role):
    # intelligence + inprocess is an odd but non-dangerous combo (used in
    # transition); coherence allows it, the partition just won't reach a broker.
    c = role("intelligence", "inprocess")
    c.assert_service_role_coherent()
