"""#266 (operator-signed 2026-06-17): newly-DISCOVERED themes are validated AT BIRTH.

Root cause: the discovery path never ran `_validate_theme_membership` on a born theme's founding
members, so mismatched members sat ~6d (median) until the next Mon/Wed/Fri rescore. These cover
`_validate_new_themes_at_birth` — the helper run_theme_engine calls after name-inheritance, before
persist. Two layers: (1) the helper's orchestration with the validator mocked, and (2) an
end-to-end pass through the REAL validator with a stubbed LLM (proves the wiring + the
min-survivor guard semantics carry over to birth)."""
from __future__ import annotations

import json

import pytest

from agents.market_intelligence import theme_engine


def _audit_capture(monkeypatch):
    events: list[tuple[str, str]] = []

    async def fake_audit(event_type, summary, detail=None):
        events.append((event_type, summary))

    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)
    return events


# ── Layer 1: helper orchestration (validator mocked) ──

@pytest.mark.asyncio
async def test_birth_validation_strips_mismatch_and_audits(monkeypatch):
    events = _audit_capture(monkeypatch)

    async def fake_validate(name, tickers, changelog, protected=None, thesis=None):
        return [t for t in tickers if t != "CAR"]   # strip the wrong-industry member

    monkeypatch.setattr(theme_engine, "_validate_theme_membership", fake_validate)

    new_themes = [{"name": "Semiconductors", "tickers": ["NVDA", "AMD", "CAR", "AVGO"]}]
    await theme_engine._validate_new_themes_at_birth(new_themes, changelog=[], protected=None)

    assert new_themes[0]["tickers"] == ["NVDA", "AMD", "AVGO"]   # CAR removed at birth
    assert any(e[0] == "theme_birth_validated" for e in events)


@pytest.mark.asyncio
async def test_birth_validation_noop_when_all_belong(monkeypatch):
    events = _audit_capture(monkeypatch)

    async def fake_validate(name, tickers, changelog, protected=None, thesis=None):
        return list(tickers)   # nothing flagged

    monkeypatch.setattr(theme_engine, "_validate_theme_membership", fake_validate)

    new_themes = [{"name": "Semiconductors", "tickers": ["NVDA", "AMD", "AVGO"]}]
    await theme_engine._validate_new_themes_at_birth(new_themes, changelog=[], protected=None)

    assert new_themes[0]["tickers"] == ["NVDA", "AMD", "AVGO"]   # unchanged
    assert not any(e[0] == "theme_birth_validated" for e in events)   # no strip → no roll-up


@pytest.mark.asyncio
async def test_birth_validation_skips_below_minimum(monkeypatch):
    calls: list[str] = []

    async def fake_validate(name, tickers, changelog, protected=None, thesis=None):
        calls.append(name)
        return list(tickers)

    monkeypatch.setattr(theme_engine, "_validate_theme_membership", fake_validate)
    # a single-member stub (below NEW_THEME_MIN_STOCKS=2) must not even call the validator
    new_themes = [{"name": "Tiny", "tickers": ["AAA"]}]
    await theme_engine._validate_new_themes_at_birth(new_themes, changelog=[], protected=None)
    assert calls == []


# ── Layer 2: end-to-end through the REAL validator (LLM stubbed) ──

def _fake_client(remove_list):
    class _Block:
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


@pytest.mark.asyncio
async def test_birth_validation_end_to_end_real_validator(monkeypatch):
    """A born 4-member theme with one wrong-industry name (CAR) is stripped at birth, through the
    real _validate_theme_membership + its cooldown/audit writes (4→3 survives the min guard)."""
    events: list[tuple[str, str]] = []
    cooldowns: list[tuple[str, str]] = []

    async def fake_audit(event_type, summary, detail=None):
        events.append((event_type, summary))

    async def fake_protected():
        return set()

    async def fake_cooldown(ticker, theme_name, reason=""):
        cooldowns.append((ticker, theme_name))
        return 1

    monkeypatch.setattr(theme_engine, "_get_anthropic_client", lambda: _fake_client(["CAR"]))
    monkeypatch.setattr(theme_engine, "get_operator_protected_set", fake_protected)
    monkeypatch.setattr(theme_engine, "add_validation_cooldown", fake_cooldown)
    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)

    new_themes = [{"name": "Semiconductors", "tickers": ["NVDA", "AMD", "CAR", "AVGO"]}]
    await theme_engine._validate_new_themes_at_birth(new_themes, changelog=[], protected=None)

    assert new_themes[0]["tickers"] == ["NVDA", "AMD", "AVGO"]        # stripped at birth
    assert ("CAR", "Semiconductors") in cooldowns                    # cooldown written at birth
    assert any(e[0] == "theme_birth_validated" for e in events)      # birth roll-up
    assert any(e[0] == "ticker_revalidated_out" for e in events)     # validator's per-ticker row


@pytest.mark.asyncio
async def test_birth_validation_two_member_theme_kept_by_min_guard(monkeypatch):
    """Min-survivor guard carries to birth: a 2-member theme can't be stripped below
    PRUNE_MIN_TICKERS, so even a flagged member is kept (no strip, no birth roll-up)."""
    events: list[tuple[str, str]] = []

    async def fake_audit(event_type, summary, detail=None):
        events.append((event_type, summary))

    async def fake_protected():
        return set()

    monkeypatch.setattr(theme_engine, "_get_anthropic_client", lambda: _fake_client(["CAR"]))
    monkeypatch.setattr(theme_engine, "get_operator_protected_set", fake_protected)
    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)

    new_themes = [{"name": "Semiconductors", "tickers": ["NVDA", "CAR"]}]
    await theme_engine._validate_new_themes_at_birth(new_themes, changelog=[], protected=None)

    assert new_themes[0]["tickers"] == ["NVDA", "CAR"]   # kept intact (would drop below 2)
    assert not any(e[0] == "theme_birth_validated" for e in events)
