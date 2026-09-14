"""The EP-time theme FIT judgement reuses the nightly assignment judgement (2026-09-14).

`theme_engine.judge_theme_fit` is the second stage of the EP theme-belonging rule
(ep_theme_belonging.py): correlation shortlists a few themes, THIS decides whether the stock
clearly fits one of them. It must be the SAME judgement the nightly `_assign_uncovered_to_themes`
pass makes — one prompt, one tool, one set of rules — or the codebase carries two definitions
of "fits a theme" that drift. Pinned here, all through the real functions (no source pins):

  1. the nightly prompt is byte-identical to its pre-refactor form — theme line, stock line,
     intro — rendered from a fixture and compared to a literal written HERE;
  2. the EP-time call sends the same rules text, the shortlisted themes ONLY, the assign tool
     ONLY (forced), no advisor paragraph, and its telemetry on its OWN audit/cost rows;
  3. the verdict mapping: a shortlisted theme → confirmed (stage label stripped); no fit →
     rejected with the model's own line; an echo of a theme not offered or of another
     ticker → rejected; truncation / a silent stop → FAILED, never rejected; no description →
     failed without spending a call.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from agents.market_intelligence import theme_engine as te


class _Block:
    def __init__(self, type, name=None, input=None, id="b1", text=""):
        self.type, self.name, self.input, self.id, self.text = type, name, input or {}, id, text


def _resp(*blocks, stop_reason="tool_use"):
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason,
                           usage=SimpleNamespace(output_tokens=200))


def _assign_resp(assignments, scratch="XYZ: makes widgets — no fit", stop_reason="tool_use"):
    return _resp(_Block("tool_use", name="assign_stocks_to_themes",
                        input={"analysis_scratchpad": scratch, "assignments": assignments}),
                 stop_reason=stop_reason)


def _client(responses):
    calls = []

    async def _create(**kw):
        calls.append(kw)
        r = responses[len(calls) - 1]
        return r() if callable(r) else r

    return SimpleNamespace(messages=SimpleNamespace(create=_create)), calls


def _quiet(monkeypatch):
    events = []

    async def _audit(event_type, summary="", detail="", **kw):
        events.append(event_type)

    async def _spend(**kw):
        events.append(f"spend:{kw.get('caller')}")

    import agents.market_intelligence.spend_tracker as spend_mod
    monkeypatch.setattr(te, "log_audit_event", _audit)
    monkeypatch.setattr(spend_mod, "log_anthropic_call_safe", _spend)
    return events


def _text(call) -> str:
    return "".join(b.get("text", "") for b in call["messages"][0]["content"])


THEMES = [
    {"name": "Bitcoin Miners", "stage": "Accelerating", "tickers": ["MARA", "RIOT", "CLSK"],
     "description": "Bitcoin mining operators with hashrate growth and AI data-center pivots"},
    {"name": "Old Optical", "stage": "Fading", "tickers": ["LITE", "COHR"],
     "description": "Optical networking components" + " x" * 80},   # >120 chars: truncated
]


# ── 1. the nightly prompt did not move ─────────────────────────────────────────────────────

def test_nightly_prompt_is_byte_identical_to_its_pre_refactor_form():
    prefix = te.assignment_shared_prefix(THEMES)
    expected = (
        "You are a market intelligence analyst. Assign uncovered stocks to existing themes ONLY when the fit is obvious.\n"
        "\n"
        "EXISTING THEMES:\n"
        "- Bitcoin Miners: MARA, RIOT, CLSK — Bitcoin mining operators with hashrate growth and AI data-center pivots\n"
        "- Old Optical [Fading]: LITE, COHR — " + ("Optical networking components" + " x" * 80)[:120] + "\n"
    )
    assert prefix == expected
    from agents.market_intelligence import universe
    universe.TICKER_DESC["ZZTEST"] = "widget maker"
    try:
        assert te._assignment_stock_line({"ticker": "ZZTEST", "rs_composite": 91.4, "sector": "Technology"}) \
            == "- ZZTEST (RS 91, sector: Technology — widget maker)"
        # the EP path: its own description wins, no RS when none is known
        assert te._assignment_stock_line({"ticker": "ZZTEST", "sector": "Utilities", "description": "power utility"}) \
            == "- ZZTEST (sector: Utilities — power utility)"
    finally:
        universe.TICKER_DESC.pop("ZZTEST", None)


# ── 2. the EP-time call: same rules, shortlist only, assign tool only, own telemetry ───────

def test_fit_call_sends_the_same_rules_to_the_shortlist_only_with_the_tool_forced(monkeypatch):
    events = _quiet(monkeypatch)
    client, calls = _client([_assign_resp([{"ticker": "IREN", "theme": "Bitcoin Miners",
                                             "rationale": "a bitcoin miner"}])])
    status, theme, why = asyncio.run(te.judge_theme_fit(
        "iren", description="Bitcoin mining and AI cloud compute", sector="Financial Services",
        themes=THEMES[:1], client=client))
    assert (status, theme, why) == (te.FIT_CONFIRMED, "Bitcoin Miners", "a bitcoin miner")
    assert len(calls) == 1
    kw = calls[0]
    assert [t["name"] for t in kw["tools"]] == ["assign_stocks_to_themes"]
    assert kw["tool_choice"] == {"type": "tool", "name": "assign_stocks_to_themes"}
    text = _text(kw)
    assert text.startswith(te.assignment_shared_prefix(THEMES[:1]))
    assert "Old Optical" not in text                       # shortlist only
    assert "- IREN (sector: Financial Services — Bitcoin mining and AI cloud compute)" in text
    for rule in ("Only assign if the stock's business CLEARLY matches the theme's thesis",
                 "When in doubt, do NOT assign",
                 "Pick the most specific theme if multiple could fit",
                 "Return empty array if nothing fits — that is the correct answer",
                 "Use the EXACT theme name from the list above"):
        assert rule in text
    assert "Consult the advisor" not in text
    assert "spend:ep_theme_fit" in events and "ep_theme_fit_llm_proposed" in events
    assert not any(e.startswith("assignment_") for e in events), \
        "EP-time fit telemetry landed on the NIGHTLY pass's audit rows"


def test_nightly_call_still_carries_the_advisor_and_its_own_telemetry(monkeypatch):
    events = _quiet(monkeypatch)
    client, calls = _client([_assign_resp([])])
    out = asyncio.run(te._propose_assignment_batch(
        client, [{"ticker": "AAA", "rs_composite": 90, "sector": "Technology"}],
        te.assignment_shared_prefix(THEMES), "", {"calls": 0}, 1, 1, 1))
    assert out == []
    kw = calls[0]
    assert {t["name"] for t in kw["tools"]} == {"assign_stocks_to_themes", "consult_advisor"}
    assert kw["tool_choice"] == {"type": "any"}
    assert "Consult the advisor ONLY if either of these apply" in _text(kw)
    assert "spend:theme_assignment" in events and "assignment_llm_proposed" in events


# ── 3. the verdict mapping ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("assignments, scratch, expected", [
    # the model echoes the [Fading] label it was shown — a fit, name stripped
    ([{"ticker": "LITE", "theme": "Old Optical [Fading]", "rationale": "optical parts"}], "",
     (te.FIT_CONFIRMED, "Old Optical", "optical parts")),
    # no fit: the model's own scratchpad line is the rationale
    ([], "LITE: a utility — no fit", (te.FIT_REJECTED, None, "LITE: a utility — no fit")),
    # a theme that was not offered is an echo, never a fit
    ([{"ticker": "LITE", "theme": "Quantum Computing", "rationale": "x"}], "s",
     (te.FIT_REJECTED, None, "named a theme not offered: Quantum Computing")),
    # another ticker's assignment says nothing about this one
    ([{"ticker": "COHR", "theme": "Old Optical", "rationale": "x"}], "LITE: no fit",
     (te.FIT_REJECTED, None, "LITE: no fit")),
])
def test_verdict_mapping(monkeypatch, assignments, scratch, expected):
    _quiet(monkeypatch)
    client, _ = _client([_assign_resp(assignments, scratch=scratch)])
    got = asyncio.run(te.judge_theme_fit("LITE", description="optical components",
                                         sector="Technology", themes=THEMES, client=client))
    assert got == expected


def test_no_verdict_is_failed_not_rejected(monkeypatch):
    _quiet(monkeypatch)
    truncated, _ = _client([_assign_resp([], stop_reason="max_tokens")])
    assert asyncio.run(te.judge_theme_fit("LITE", description="d", sector=None, themes=THEMES,
                                          client=truncated))[0] == te.FIT_FAILED
    silent, _ = _client([_resp(_Block("text", text="I would rather not."))])
    assert asyncio.run(te.judge_theme_fit("LITE", description="d", sector=None, themes=THEMES,
                                          client=silent))[0] == te.FIT_FAILED


def test_no_description_fails_without_spending_a_call(monkeypatch):
    _quiet(monkeypatch)
    client, calls = _client([])
    status, theme, why = asyncio.run(te.judge_theme_fit(
        "LITE", description="   ", sector="Technology", themes=THEMES, client=client))
    assert (status, theme) == (te.FIT_FAILED, None) and "no description" in why
    assert calls == []
    assert asyncio.run(te.judge_theme_fit("LITE", description="d", sector=None, themes=[],
                                          client=client))[0] == te.FIT_REJECTED


def test_api_errors_raise_to_the_caller(monkeypatch):
    _quiet(monkeypatch)

    def _boom():
        raise RuntimeError("api down")

    client, _ = _client([_boom])
    with pytest.raises(RuntimeError):
        asyncio.run(te.judge_theme_fit("LITE", description="d", sector=None, themes=THEMES,
                                       client=client))
