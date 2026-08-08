"""Tests for the #213 operator-protection shield in _validate_theme_membership.

Regression: the Mon/Wed/Fri Haiku membership validator over-removes legit core
members when a theme name carries a narrowing qualifier (SNDK = "NAND flash
storage" judged "not matching AI Memory & Storage" on the "AI" word). The
operator re-added SNDK/SIMO and bypassed their cooldowns — but a bypass only
suppresses re-ASSIGNMENT, not re-REMOVAL, so the very next validation run would
silently strip them again.

The shield: a bypassed (ticker, theme) cooldown = operator ruled this ticker
BELONGS; the validator must veto its removal. Two-sided invariant under test:
the shield KEEPS protected tickers AND still REMOVES genuinely-flagged ones.
"""
from __future__ import annotations

import json

import pytest

from agents.market_intelligence import theme_engine


def _fake_client(remove_list):
    """Async Anthropic client stub whose messages.create returns {"remove": [...]}."""
    class _Block:
        # `type` is REQUIRED on every fake block (#544): the real API always sets it, and
        # our reader now selects BY type instead of by position. A fake without it is a
        # shape production never produces — the exact "fabricated input proves nothing"
        # trap that let the 08-06 thinking-block outage through every existing test.
        type = "text"
        text = json.dumps({"remove": remove_list})

    class _Resp:
        content = [_Block()]
        stop_reason = "end_turn"

    class _Messages:
        async def create(self, *a, **kw):
            return _Resp()

    class _Client:
        messages = _Messages()

    return _Client()


def _patch_common(monkeypatch, protected, remove_list):
    """Wire the validator's external deps: LLM, protected-set, cooldown writer, audit."""
    audit: list[tuple[str, str]] = []
    cooldowns: list[tuple[str, str]] = []

    async def fake_audit(event_type, summary, detail=None):
        audit.append((event_type, summary))

    async def fake_protected():
        return protected

    async def fake_cooldown(ticker, theme_name, reason=""):
        cooldowns.append((ticker, theme_name))
        return 1

    monkeypatch.setattr(theme_engine, "_get_anthropic_client", lambda: _fake_client(remove_list))
    monkeypatch.setattr(theme_engine, "get_operator_protected_set", fake_protected)
    monkeypatch.setattr(theme_engine, "add_validation_cooldown", fake_cooldown)
    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)
    return audit, cooldowns


@pytest.mark.asyncio
async def test_protected_ticker_kept_despite_llm_removal(monkeypatch):
    """SNDK case: LLM flags SNDK for removal, but it's operator-protected → kept."""
    audit, cooldowns = _patch_common(
        monkeypatch,
        protected={("SNDK", "AI Memory & Storage")},
        remove_list=["SNDK"],
    )

    survivors = await theme_engine._validate_theme_membership(
        "AI Memory & Storage",
        ["MU", "SNDK", "WDC", "STX", "SIMO"],
        changelog=[],
    )

    assert "SNDK" in survivors            # shield vetoed the removal
    assert ("SNDK", "AI Memory & Storage") not in cooldowns  # no new cooldown written
    assert any(e[0] == "validation_removal_shielded" for e in audit)


@pytest.mark.asyncio
async def test_unprotected_ticker_still_removed(monkeypatch):
    """Two-sided: a genuinely-flagged ticker with NO protection is still removed."""
    audit, cooldowns = _patch_common(
        monkeypatch,
        protected={("SNDK", "AI Memory & Storage")},  # SNDK protected, CAR is not
        remove_list=["CAR"],
    )

    survivors = await theme_engine._validate_theme_membership(
        "AI Memory & Storage",
        ["MU", "SNDK", "WDC", "CAR", "SIMO"],
        changelog=[],
    )

    assert "CAR" not in survivors        # unprotected removal proceeds
    assert ("CAR", "AI Memory & Storage") in cooldowns
    assert any(e[0] == "ticker_revalidated_out" for e in audit)


@pytest.mark.asyncio
async def test_mixed_removal_shields_only_protected(monkeypatch):
    """LLM flags both SNDK (protected) and CAR (not): keep SNDK, remove CAR."""
    audit, cooldowns = _patch_common(
        monkeypatch,
        protected={("SNDK", "AI Memory & Storage")},
        remove_list=["SNDK", "CAR"],
    )

    survivors = await theme_engine._validate_theme_membership(
        "AI Memory & Storage",
        ["MU", "SNDK", "WDC", "CAR", "SIMO"],
        changelog=[],
    )

    assert "SNDK" in survivors
    assert "CAR" not in survivors
    assert ("CAR", "AI Memory & Storage") in cooldowns
    assert ("SNDK", "AI Memory & Storage") not in cooldowns


@pytest.mark.asyncio
async def test_shield_fails_open_on_db_error(monkeypatch):
    """If the protected-set lookup raises, removal proceeds (fail-open, no crash)."""
    audit: list = []
    cooldowns: list = []

    async def fake_audit(event_type, summary, detail=None):
        audit.append((event_type, summary))

    async def boom():
        raise RuntimeError("pool exhausted")

    async def fake_cooldown(ticker, theme_name, reason=""):
        cooldowns.append((ticker, theme_name))
        return 1

    monkeypatch.setattr(theme_engine, "_get_anthropic_client", lambda: _fake_client(["CAR"]))
    monkeypatch.setattr(theme_engine, "get_operator_protected_set", boom)
    monkeypatch.setattr(theme_engine, "add_validation_cooldown", fake_cooldown)
    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)

    survivors = await theme_engine._validate_theme_membership(
        "AI Memory & Storage",
        ["MU", "SNDK", "WDC", "CAR", "SIMO"],
        changelog=[],
    )

    assert "CAR" not in survivors        # fail-open: removal still happens
