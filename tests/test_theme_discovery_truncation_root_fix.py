"""Root fix for the recurring "discovery emits 0 new themes" bug (2026-06-25).

THE BUG (verified via `theme_discovery_llm_call` telemetry, 6/22-24): the live
`_discover_new_themes` produced ZERO new themes for days. The tell was
`stop=max_tokens out_tok=4000` on BOTH the tool_choice=auto call AND the forced
`report_themes` retry — i.e. the 4000-token budget was being consumed *inside*
the bounded tool output, so the JSON truncated mid-array and parsed to nothing.

Two drivers, both fixed by mirroring the PROVEN assignment path (theme_engine.py
~2117, which had the identical 5/12-13 silent_stop and stayed fixed once it
(a) demanded a TERSE scratchpad and (b) banned pre-tool free text):
  1. the `report_themes.analysis_scratchpad` description demanded a HEAVY
     per-group 3-part essay → over five input pools it overflowed the budget
     inside the forced tool call. Now: terse one-line-per-cluster.
  2. the prompt's "ask yourself… Consult the advisor FIRST" framing INDUCED
     pre-tool free-reasoning text on the auto call → it stopped with
     tool_uses=0. Now: a no-free-text-before-tool guard + advisor-only-on-real-
     ambiguity, reasoning in the scratchpad.

WHAT THIS TEST CAN AND CANNOT DO (honesty, per the anti-recurrence ask): a fake
Anthropic client returns whatever we script — it cannot emit 4000 real tokens of
scratchpad, so it cannot LITERALLY reproduce volume truncation. Instead these
tests pin the load-bearing *properties* that prevent the truncation:
  - structural: the schema's scratchpad description is the TERSE form, the
    "Consult the advisor FIRST" inducer is GONE, and the no-free-text guard is
    present (the two prompt/schema levers that stop the budget burn);
  - control-flow: a first response that TRUNCATES (stop_reason='max_tokens', no
    tool_use) still triggers `force_report`, and a forced response carrying only
    a bounded `{name, thesis, tickers}` payload parses to real themes — i.e. the
    #173 force_report fallback now actually LANDS where it used to truncate
    again. (Mirrors tests/test_theme_synthesis_truncation.py.)

The clustering CRITERION is untouched: min-3, #214 breadth, sector-coherence and
the when-in-doubt-exclude disposition still live in the Rules block + the
downstream `_validate_theme_membership` / `_strip_sector_outliers` gates. These
tests assert the Rules survived. (Heavy-import stubbing via tests/conftest.py.)
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


def _resp(*blocks, stop_reason="end_turn", out_tok=120):
    """A scripted response carrying the attrs the discovery telemetry reads
    (stop_reason + usage.output_tokens) — unlike the older force_report test's
    bare namespace, so the per-call audit block actually runs here."""
    return SimpleNamespace(
        content=list(blocks),
        stop_reason=stop_reason,
        usage=SimpleNamespace(output_tokens=out_tok),
    )


def _fake_client(responses):
    calls = []

    async def _create(**kwargs):
        calls.append(kwargs)
        return responses[len(calls) - 1]

    return SimpleNamespace(messages=SimpleNamespace(create=_create)), calls


# A complete, bounded report_themes payload — only {name, thesis, tickers}, NO
# verbose scratchpad. This is the shape the forced call now emits without
# overflowing the budget; the test asserts it parses to a real theme.
_MEMORY = _Block(
    "tool_use", name="report_themes",
    input={
        "analysis_scratchpad": "memory makers — HBM demand, keep",
        "themes": [{
            "name": "AI Memory & HBM",
            "thesis": "HBM demand from AI accelerators is re-rating DRAM/NAND makers.",
            "tickers": ["MU", "SNDK", "WDC"],
        }],
    },
)


def _memory_stocks(monkeypatch):
    """A clusterable 3-stock set (>= NEW_THEME_MIN_STOCKS). Tickers must carry a
    description or they're filtered out before the LLM call."""
    from agents.market_intelligence import universe
    descs = {
        "MU": "DRAM and NAND memory maker",
        "SNDK": "NAND flash storage maker",
        "WDC": "hard drive and flash storage maker",
    }
    for tk, d in descs.items():
        monkeypatch.setitem(universe.TICKER_DESC, tk, d)
    stocks = [
        {"ticker": "MU", "rs_composite": 96, "sector": "Technology"},
        {"ticker": "SNDK", "rs_composite": 93, "sector": "Technology"},
        {"ticker": "WDC", "rs_composite": 91, "sector": "Technology"},
    ]
    return stocks, {s["ticker"]: s for s in stocks}


# ── Control-flow: the truncation-then-recover path the bug broke ──────────────

def test_truncated_auto_call_then_forced_report_emits_themes(monkeypatch):
    """Failure-shape repro: the FIRST (auto) call truncates exactly as observed
    6/22-24 — stop_reason='max_tokens', out_tok at the 4000 ceiling, and NO
    tool_use block (the JSON never finished). Before the fix this fell through
    `if not tool_uses` to a forced retry that ALSO truncated → 0 themes. Now the
    forced retry carries a bounded payload and EMITS the theme. We assert the
    pass recovers a real theme rather than returning []."""
    stocks, sbt = _memory_stocks(monkeypatch)
    truncated = _resp(_Block("text"), stop_reason="max_tokens", out_tok=4000)
    client, calls = _fake_client([truncated, _resp(_MEMORY, stop_reason="tool_use")])
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    out = asyncio.run(te._discover_new_themes(stocks, [], sbt))

    assert len(calls) == 2, "a truncated/empty first call must force a final report, not return []"
    assert calls[0]["tool_choice"] == {"type": "auto"}, "first call stays auto (preserves #173 advisor path)"
    assert calls[1]["tool_choice"] == {"type": "tool", "name": "report_themes"}, "must force the report on the retry"
    assert [t["name"] for t in out] == ["AI Memory & HBM"], "the bounded forced report must EMIT the theme, not truncate to 0"
    assert out[0]["tickers"] == ["MU", "SNDK", "WDC"]


def test_bounded_report_parses_first_try(monkeypatch):
    """The healthy path: a complete report on the first (auto) call parses
    straight through — no forced retry needed once the output stays bounded."""
    stocks, sbt = _memory_stocks(monkeypatch)
    client, calls = _fake_client([_resp(_MEMORY, stop_reason="tool_use")])
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    out = asyncio.run(te._discover_new_themes(stocks, [], sbt))

    assert len(calls) == 1
    assert [t["name"] for t in out] == ["AI Memory & HBM"]


# ── Structural: the two prompt/schema levers that bound the output ────────────

def test_scratchpad_is_terse_form_not_heavy_essay(monkeypatch):
    """The schema's scratchpad description must be the TERSE one-line form. The
    old heavy 'per group: (1)…(2)…(3)… Reject spurious clusters here' essay over
    five pools is what overflowed the budget inside the forced tool call."""
    desc = te._THEME_DISCOVERY_TOOL["input_schema"]["properties"]["analysis_scratchpad"]["description"]
    assert "one terse line per candidate cluster" in desc.lower() or "keep it short" in desc.lower(), \
        "scratchpad must instruct a terse, bounded narration"
    # the heavy structured-essay phrasing that blew the budget must be gone
    assert "(1) what shared catalyst" not in desc
    assert "(2) which stocks clearly belong" not in desc


def test_prompt_kills_inducer_and_adds_no_free_text_guard(monkeypatch):
    """The 'Consult the advisor FIRST' inducer (which drove pre-tool free text →
    tool_uses=0 on the auto call) must be GONE, replaced by the assignment path's
    no-free-text-before-tool guard + advisor-only-on-ambiguity recipe."""
    stocks, sbt = _memory_stocks(monkeypatch)
    client, calls = _fake_client([_resp(_MEMORY, stop_reason="tool_use")])
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    asyncio.run(te._discover_new_themes(stocks, [], sbt))
    prompt = calls[0]["messages"][0]["content"]

    # inducer gone
    assert "Consult the advisor FIRST" not in prompt
    # no-free-text guard present (mirrors the assignment path that stayed fixed)
    assert "Do NOT write any free-text analysis before your tool call" in prompt
    assert "truncate" in prompt.lower()
    # advisor path preserved but gated to genuine ambiguity (not forced off)
    assert "Consult the advisor ONLY if" in prompt


def test_criterion_rules_unchanged(monkeypatch):
    """Bug-fix, not criterion-change: the clustering Rules the model is judged on
    must still be in the prompt verbatim (min-3, #214 breadth, when-in-doubt
    disposition). If this fails, the fix leaked into the criterion — STOP."""
    stocks, sbt = _memory_stocks(monkeypatch)
    client, calls = _fake_client([_resp(_MEMORY, stop_reason="tool_use")])
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    asyncio.run(te._discover_new_themes(stocks, [], sbt))
    prompt = calls[0]["messages"][0]["content"]

    assert "A theme REQUIRES at least 2 stocks" in prompt           # min-cluster rule
    assert "NAME-BREADTH RULE" in prompt                            # #214 breadth
    assert "Return zero themes if no clear cluster exists" in prompt  # precision disposition
