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
async def test_one_same_family_NOW_emits(monkeypatch):
    """Threshold lowered 2 → 1 (operator-ruled 2026-07-27). This test previously
    pinned the opposite (`breach is False` for a single same-family position) and
    it was right to — at the old threshold it was correct behavior.

    Why it changed: at 2, the shadow was structurally incapable of firing. It had
    recorded ZERO events since shipping 7/12, because an emit needed two EXISTING
    same-family positions plus the candidate, while the live book has reached 4
    concurrent positions ONCE and averages 1.50. The zero was honest, not broken
    instrumentation — there was simply nothing to observe. At 1, an emit means
    "this entry makes two positions share a theme", which is the base rate needed
    before anyone can argue for a blocking cap.

    Still SHADOW — this can never block an entry.
    """
    _setup(monkeypatch, ["AAA", "CCC"],
           _themes(("Insurance Underwriters", ("NEWT", "AAA")), ("Other", ("CCC",))))
    info = await ef.check_family_exposure("NEWT", "live")
    assert info["breach"] is True and info["same_family"] == ["AAA"]


@pytest.mark.asyncio
async def test_zero_same_family_still_never_emits(monkeypatch):
    """The floor that must hold at ANY threshold: an entry sharing a theme with
    NOTHING open is not a concentration event. Guards against lowering the
    threshold to 0 and turning every entry into an alert."""
    _setup(monkeypatch, ["CCC"],
           _themes(("Insurance Underwriters", ("NEWT",)), ("Other", ("CCC",))))
    info = await ef.check_family_exposure("NEWT", "live")
    assert info["breach"] is False and info["same_family"] == []


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


# ---------------------------------------------------------------------------
# HEARTBEAT (2026-09-07) — the shadow must record that it RAN, not only that it
# fired. It shipped 2026-08-09 and wrote nothing across five weeks and 19 filled
# entries, which is indistinguishable from the hook never executing; container
# logs cannot settle it either, because a deploy recreates the container. These
# pins make silence mean something.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_heartbeat_written_when_there_is_no_breach(monkeypatch):
    """The case that made #452 unverifiable: nothing to report, so nothing was."""
    _setup(monkeypatch, ["CCC"], _themes(("T", ("NEWT", "AAA"))))
    audit = AsyncMock()
    monkeypatch.setattr(ef, "log_audit_event", audit)

    await ef.shadow_check_and_emit("NEWT", "live", "MAGNA53")

    assert audit.await_count == 1, "a no-breach check must still leave a trace"
    assert audit.await_args.args[0] == "exposure_family_checked"
    d = json.loads(audit.await_args.args[2])
    assert d["breach"] is False and d["shadow"] is True
    assert d["threshold"] == ef.EXPOSURE_FAMILY_SHADOW_THRESHOLD


@pytest.mark.asyncio
async def test_heartbeat_written_when_the_name_has_no_theme(monkeypatch):
    """Most alerts carry no theme, so this is the common path — and it must log."""
    _setup(monkeypatch, ["AAA", "BBB"], _themes(("T", ("AAA", "BBB"))))
    audit = AsyncMock()
    monkeypatch.setattr(ef, "log_audit_event", audit)

    await ef.shadow_check_and_emit("NEWT", "live", "MAGNA53")

    assert audit.await_count == 1
    assert audit.await_args.args[0] == "exposure_family_checked"
    assert json.loads(audit.await_args.args[2])["candidate_themes"] == []


@pytest.mark.asyncio
async def test_breach_still_writes_both_rows_and_still_never_blocks(monkeypatch):
    """The heartbeat is additive: a breach leaves the check row AND the breach row."""
    _setup(monkeypatch, ["AAA", "BBB"], _themes(("T", ("NEWT", "AAA", "BBB"))))
    audit = AsyncMock()
    monkeypatch.setattr(ef, "log_audit_event", audit)
    import agents.market_intelligence.briefing as briefing
    import agents.market_intelligence.constants as constants
    monkeypatch.setattr(briefing, "send_telegram_message", AsyncMock())
    monkeypatch.setattr(constants, "mode_prefix", lambda m=None: "")

    out = await ef.shadow_check_and_emit("NEWT", "live", "MAGNA53")

    events = [c.args[0] for c in audit.await_args_list]
    assert events == ["exposure_family_checked", "exposure_family_breach"]
    assert out is None, "observe-only: the hook returns nothing the caller can act on"
