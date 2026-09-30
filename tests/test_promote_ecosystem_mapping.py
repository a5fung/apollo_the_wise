"""Promoted themes get their ADR-0032 ecosystem mapping AT promotion.

2026-07-16: the 17:05 nightly promote job wrote 4 themes into mi_themes AFTER
run_theme_engine's ensure_theme_ecosystems hook had already run (17:03), so
all 4 sat E-UNASSIGNED on the /themes board until the next nightly self-heal.
Both promote paths (nightly auto-promote + operator /promotetheme) now call
ensure_theme_ecosystems on what they wrote — these tests pin that, and that
a mapping failure never breaks the promotion itself.
"""
from __future__ import annotations

import datetime as _dt
from unittest.mock import AsyncMock

import pytest

from tests.conftest import make_mock_pool

from agents.market_intelligence import db as dbmod
from agents.market_intelligence import theme_engine as te
from agents.market_intelligence import theme_ecosystems as eco


@pytest.fixture(autouse=True)
def _birth_gate_off(monkeypatch):
    """Phase-1 birth gate (2026-07-27): pin the 3-state 'theme_birth_gate' mode 'off' so
    these pre-gate promote pins exercise the byte-identical legacy path without
    a real DB read (fail-closed OFF is the production default)."""
    monkeypatch.setattr(te, "get_theme_birth_gate_mode", AsyncMock(return_value="off"))

_TODAY = _dt.date(2026, 7, 16)


def _wire_promote_mocks(monkeypatch, cands):
    pool, conn = make_mock_pool()
    # #530: promote_shadow_themes now issues THREE conn.fetch calls — prior_rows
    # (days_active), prior_desc_rows (tombstone-skipping description lookup — empty here,
    # none of these tests exercise thesis preservation), RS rows.
    conn.fetch = AsyncMock(side_effect=[[], [], []])   # prior rows, prior desc rows, RS rows
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(te, "_canonicalize_theme_names", AsyncMock(return_value=0))
    monkeypatch.setattr(te, "log_audit_event", AsyncMock())
    from agents.market_intelligence import briefing as _brief
    monkeypatch.setattr(_brief, "send_telegram_message", AsyncMock())
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=cands))
    return conn


@pytest.mark.asyncio
async def test_nightly_promote_maps_promoted_themes(monkeypatch):
    _wire_promote_mocks(monkeypatch, [
        {"name": "Quantum Networking", "tickers": ["QX", "QY", "QZ"],
         "thesis": "t", "source": "rs_slope_synthesis"},
    ])
    ensure = AsyncMock(return_value=[])
    monkeypatch.setattr(eco, "ensure_theme_ecosystems", ensure)

    n = await te.promote_shadow_themes(_TODAY)

    assert n == 1
    ensure.assert_awaited_once()
    mapped_names = [t["name"] for t in ensure.await_args.args[0]]
    assert mapped_names == ["Quantum Networking"]


@pytest.mark.asyncio
async def test_nightly_promote_skips_mapping_when_nothing_promoted(monkeypatch):
    _wire_promote_mocks(monkeypatch, [
        {"name": "Too Small", "tickers": ["A"], "thesis": "t", "source": "shadow_v2"},
    ])
    ensure = AsyncMock(return_value=[])
    monkeypatch.setattr(eco, "ensure_theme_ecosystems", ensure)

    n = await te.promote_shadow_themes(_TODAY)

    assert n == 0
    ensure.assert_not_awaited()


@pytest.mark.asyncio
async def test_nightly_promote_survives_mapping_failure(monkeypatch):
    """The mapping call is wrapped — an ecosystem-layer error must never turn a
    successful promotion into a failure (the promote wrote mi_themes already)."""
    _wire_promote_mocks(monkeypatch, [
        {"name": "Quantum Networking", "tickers": ["QX", "QY", "QZ"],
         "thesis": "t", "source": "rs_slope_synthesis"},
    ])
    monkeypatch.setattr(
        eco, "ensure_theme_ecosystems", AsyncMock(side_effect=RuntimeError("haiku down")))

    n = await te.promote_shadow_themes(_TODAY)   # must not raise

    assert n == 1


@pytest.mark.asyncio
async def test_operator_promote_maps_the_promoted_theme(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])        # RS rows
    conn.fetchrow = AsyncMock(return_value=None)   # no prior row
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(te, "_canonicalize_theme_names", AsyncMock(return_value=0))
    monkeypatch.setattr(te, "log_audit_event", AsyncMock())
    monkeypatch.setattr(te, "_upsert_promoted_theme", AsyncMock(return_value=True))
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[
        {"name": "Probe: Robotics 2026-07-10", "tickers": ["A", "B", "C"],
         "thesis": "t", "source": "coverage_probe"},
    ]))
    ensure = AsyncMock(return_value=[])
    monkeypatch.setattr(eco, "ensure_theme_ecosystems", ensure)

    res = await te.promote_candidate_by_name("Robotics", _TODAY)

    assert res["status"] == "promoted"
    ensure.assert_awaited_once()
    assert ensure.await_args.args[0][0]["name"] == "Probe: Robotics 2026-07-10"
