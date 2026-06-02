"""#173 — theme discovery must not silently drop a whole discovery pass.

The ADR-0007 shadow wrote 0 rows for days because the Sonnet discovery model,
uncertain on the igniting-name pool, consulted the advisor and then returned NO
tool call at all — hitting the old `if not tool_uses: return []` branch and
silently discarding a discovered drone/UAS cluster (UMAC/RCAT). Same shared code
path likely caused the live drone-theme miss on 2026-05-30.

The fix: when the model stops without reporting OR exhausts its advisor budget,
force a final `report_themes` so it commits its best judgment. A forced report
can still return `themes=[]`, so this recovers lost themes without inventing any.
These tests pin that control flow. (Heavy-import stubbing via tests/conftest.py.)
"""
import asyncio
from types import SimpleNamespace

from agents.market_intelligence import theme_engine as te


class _Block:
    def __init__(self, type, name=None, input=None, id="b1"):
        self.type = type
        self.name = name
        self.input = input or {}
        self.id = id


def _resp(*blocks):
    return SimpleNamespace(content=list(blocks))


def _fake_client(responses):
    """A stand-in Anthropic client whose messages.create returns scripted
    responses in order; records each call's kwargs for assertions."""
    calls = []

    async def _create(**kwargs):
        calls.append(kwargs)
        return responses[len(calls) - 1]

    return SimpleNamespace(messages=SimpleNamespace(create=_create)), calls


_DRONE = _Block("tool_use", name="report_themes",
                input={"themes": [{"name": "Drone/UAS", "tickers": ["UMAC", "RCAT"]}]})


def _drone_stocks(monkeypatch):
    # Tickers must have descriptions or they're filtered out before the LLM call.
    from agents.market_intelligence import universe
    monkeypatch.setitem(universe.TICKER_DESC, "UMAC", "commercial drone maker")
    monkeypatch.setitem(universe.TICKER_DESC, "RCAT", "defense drone maker")
    stocks = [
        {"ticker": "UMAC", "rs_composite": 99, "sector": "Industrials"},
        {"ticker": "RCAT", "rs_composite": 95, "sector": "Industrials"},
    ]
    return stocks, {s["ticker"]: s for s in stocks}


def test_model_stops_then_forced_report_recovers_theme(monkeypatch):
    stocks, sbt = _drone_stocks(monkeypatch)
    # call 1: model emits TEXT only (no tool_use) -> this WAS a silent `return []`.
    # call 2: forced report_themes commits the drone cluster.
    client, calls = _fake_client([_resp(_Block("text")), _resp(_DRONE)])
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    out = asyncio.run(te._discover_new_themes(stocks, [], sbt))

    assert len(calls) == 2, "should re-issue a forced call, not return [] on stop"
    assert calls[0]["tool_choice"] == {"type": "auto"}
    assert calls[1]["tool_choice"] == {"type": "tool", "name": "report_themes"}
    assert [t["name"] for t in out] == ["Drone/UAS"]
    assert out[0]["tickers"] == ["UMAC", "RCAT"]


def test_advisor_exhaustion_forces_report(monkeypatch):
    stocks, sbt = _drone_stocks(monkeypatch)

    async def _advice(*a, **k):
        return "plausible — but confirm the cluster"
    monkeypatch.setattr(te, "_call_advisor", _advice)

    advisor = _resp(_Block("tool_use", name="consult_advisor",
                           input={"question": "real?", "context": "drones"}, id="a"))
    # 3 advisor rounds hit _MAX_ADVISOR_CALLS, then the forced report on the 4th call.
    client, calls = _fake_client([advisor, advisor, advisor, _resp(_DRONE)])
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    out = asyncio.run(te._discover_new_themes(stocks, [], sbt))

    assert len(calls) == 4
    assert calls[3]["tool_choice"] == {"type": "tool", "name": "report_themes"}, \
        "must force report once the advisor budget is spent, not loop forever"
    assert [t["name"] for t in out] == ["Drone/UAS"]


def test_forced_report_can_still_return_empty(monkeypatch):
    # Forcing report_themes must NOT fabricate a theme — an empty report is honest.
    stocks, sbt = _drone_stocks(monkeypatch)
    empty = _resp(_Block("tool_use", name="report_themes", input={"themes": []}))
    client, calls = _fake_client([_resp(_Block("text")), empty])
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    out = asyncio.run(te._discover_new_themes(stocks, [], sbt))

    assert calls[1]["tool_choice"] == {"type": "tool", "name": "report_themes"}
    assert out == []
