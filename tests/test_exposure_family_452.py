"""#452 exposure-family shadow pins — observe-only, fork-B vocabulary, breach emit."""
import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import make_mock_pool
from agents.market_intelligence import exposure_family as ef


def _themes(*pairs):
    return [{"name": n, "tickers": list(t)} for n, t in pairs]


def _setup(monkeypatch, opens, themes):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[[{"ticker": t} for t in opens], themes])
    monkeypatch.setattr(ef, "get_pool", AsyncMock(return_value=pool))
    return conn


@pytest.mark.asyncio
async def test_breach_when_two_same_family_opens(monkeypatch):
    conn = _setup(monkeypatch, ["AAA", "BBB", "CCC"],
                  _themes(("Insurance Underwriters", ("NEWT", "AAA", "BBB")),
                          ("Unrelated Theme", ("CCC",))))
    info = await ef.check_family_exposure("NEWT", "live")
    assert info["breach"] is True
    assert info["same_family"] == ["AAA", "BBB"]
    assert info["candidate_themes"] == ["Insurance Underwriters"]
    # fork-B vocabulary pin: the opens query binds OPEN_POSITION_STATUSES
    from agents.market_intelligence.db import OPEN_POSITION_STATUSES
    assert conn.fetch.await_args_list[0].args[2] == list(OPEN_POSITION_STATUSES)


@pytest.mark.asyncio
async def test_no_breach_one_same_family(monkeypatch):
    _setup(monkeypatch, ["AAA", "CCC"],
           _themes(("Insurance Underwriters", ("NEWT", "AAA")), ("Other", ("CCC",))))
    info = await ef.check_family_exposure("NEWT", "live")
    assert info["breach"] is False and info["same_family"] == ["AAA"]


@pytest.mark.asyncio
async def test_no_theme_candidate_never_breaches(monkeypatch):
    _setup(monkeypatch, ["AAA", "BBB"], _themes(("T", ("AAA", "BBB"))))
    info = await ef.check_family_exposure("LONE", "live")
    assert info["breach"] is False and info["candidate_themes"] == []


@pytest.mark.asyncio
async def test_shadow_emit_fires_audit_and_telegram_on_breach(monkeypatch):
    _setup(monkeypatch, ["AAA", "BBB"], _themes(("T", ("NEWT", "AAA", "BBB"))))
    audit = AsyncMock()
    tg = AsyncMock()
    monkeypatch.setattr(ef, "log_audit_event", audit)
    import agents.market_intelligence.briefing as briefing
    import agents.market_intelligence.constants as constants
    monkeypatch.setattr(briefing, "send_telegram_message", tg)
    monkeypatch.setattr(constants, "mode_prefix", lambda m=None: "")

    await ef.shadow_check_and_emit("NEWT", "live", "MAGNA53")

    assert audit.await_args.args[0] == "exposure_family_breach"
    assert json.loads(audit.await_args.args[2])["shadow"] is True
    tg.assert_awaited_once()


@pytest.mark.asyncio
async def test_entry_pipeline_hook_is_error_isolated(monkeypatch):
    # the hook is wrapped at the CALL SITE — pin the wrapper exists in the source
    src = open("agents/market_intelligence/broker/entry_pipeline.py").read()
    assert "shadow_check_and_emit" in src
    hook_region = src.split("shadow_check_and_emit")[0][-600:] + src.split("shadow_check_and_emit")[2][:400]
    assert "except Exception" in src.split("from agents.market_intelligence.exposure_family")[1][:500]
