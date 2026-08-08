"""A model update broke the MECHANICAL contract and no test could have caught it (#544).

**THE OUTAGE.** From 2026-08-06 the earnings-metrics extractor failed on EVERY call with
`KeyError: 'text'`. For two sessions it graded ~14 earnings names a day as weak — on an
exception — including an entire software cohort gapping together on 08-07. Nothing alerted.
The operator found it by noticing there were no EP alerts during earnings season, and said:
*"we didn't have sufficient tests on Sonnet 5 or any assumptions we have when model updates —
not grading/llm perf, but just the mechanical side of those models, apis, etc."*

**THE BUG.** `data["content"][0]["text"]` — the first content block is the answer. True for
sonnet-4-6. False for sonnet-5, which returns a **thinking block first**.

**WHY NOTHING CAUGHT IT.** The judge-eval gate measures GRADE QUALITY; this was a parse. Every
unit test fed hand-built single-block responses, which is the one shape that cannot fail. A test
built on fabricated input proves nothing about a contract you did not know you were relying on.

**WHAT THESE TESTS DO.** They assert the codebase can no longer make the assumption at all —
one canonical reader, no positional indexing anywhere — and they exercise that reader against
the response shapes a model tier bump can actually produce: thinking-first, tool_use-first,
multi-block, empty, and both the SDK-object and raw-HTTP-dict forms this codebase uses.
"""
import pathlib
import re

import pytest

from shared.llm_response import content_block_types, first_text

REPO = pathlib.Path(__file__).resolve().parent.parent
SCANNED = ["agents", "core", "channels", "shared"]


# ── the reader survives every shape a tier bump can produce ───────────────────────────────

class _Block:
    """Stands in for an SDK content block. Note `thinking` blocks have NO `.text`."""

    def __init__(self, type_, text=None):
        self.type = type_
        if text is not None:
            self.text = text


class _Resp:
    def __init__(self, blocks):
        self.content = blocks


def test_a_thinking_block_first_is_the_exact_08_06_outage():
    """sonnet-5's actual shape. `content[0]` is a thinking block with no `.text` at all."""
    r = _Resp([_Block("thinking"), _Block("text", '{"themes": []}')])
    assert first_text(r) == '{"themes": []}'


def test_the_raw_http_dict_shape_too():
    """catalyst_metrics_extractor calls the API over urllib, not the SDK — it sees dicts. The
    original fix lived only in that file; the reader must cover both or the helper is useless
    to exactly the caller that started this."""
    data = {"content": [{"type": "thinking", "thinking": "hmm"},
                        {"type": "text", "text": "the answer"}]}
    assert first_text(data) == "the answer"


def test_a_tool_use_block_first():
    """Forced-tool calls with reasoning enabled can lead with tool_use or thinking."""
    r = _Resp([_Block("tool_use"), _Block("text", "prose")])
    assert first_text(r) == "prose"


def test_no_text_block_at_all_returns_the_default_not_a_crash():
    """A pure-tool_use or pure-thinking response HAS no prose answer. That must be a clean
    empty, because the caller's job is to distinguish it from a real answer — the outage
    happened because a parse failure was read downstream as 'weak catalyst'."""
    assert first_text(_Resp([_Block("tool_use")])) == ""
    assert first_text(_Resp([])) == ""
    assert first_text(None) == ""
    assert first_text({"content": None}) == ""


def test_an_empty_text_block_is_skipped_not_returned():
    """Some shapes emit an empty text block alongside the real one."""
    r = _Resp([_Block("text", ""), _Block("text", "real content")])
    assert first_text(r) == "real content"


def test_it_does_not_concatenate_text_blocks():
    """Every caller here parses ONE JSON object or ONE prose answer. Joining blocks would
    silently corrupt the JSON ones into unparseable garbage — a quieter bug than the original."""
    r = _Resp([_Block("text", '{"a": 1}'), _Block("text", '{"b": 2}')])
    assert first_text(r) == '{"a": 1}'


def test_block_types_are_reportable_for_diagnosis():
    """Knowing the response was ['thinking'] rather than [] is the difference between a
    five-minute diagnosis and the two days this actually took."""
    assert content_block_types(_Resp([_Block("thinking"), _Block("text", "x")])) == \
        ["thinking", "text"]
    assert content_block_types({"content": [{"type": "tool_use"}]}) == ["tool_use"]


# ── nobody can make the assumption again ──────────────────────────────────────────────────

_POSITIONAL = re.compile(r"""\.content\[0\]|\[["']content["']\]\[0\]""")


def _offenders() -> list[str]:
    hits = []
    for top in SCANNED:
        for path in sorted((REPO / top).rglob("*.py")):
            # The canonical reader itself DOCUMENTS the banned pattern — that prose is the
            # whole point of the file and must not trip its own gate.
            if path.name == "llm_response.py":
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
                code = line.split("#", 1)[0]
                if _POSITIONAL.search(code):
                    hits.append(f"{path.relative_to(REPO)}:{n}")
    return hits


def test_the_scanner_would_actually_catch_the_original_bug():
    """Guards the guard: a regex that matches nothing passes the gate below vacuously."""
    assert _POSITIONAL.search('data["content"][0]["text"]')
    assert _POSITIONAL.search("resp.content[0].text")
    assert not _POSITIONAL.search("first_text(resp)")


def test_no_code_indexes_the_first_content_block():
    """Ten sites made this assumption on 08-06 — five in the theme engine, plus the market
    agent, the scheduler, catalyst materiality, the orchestrator's context compression, and the
    extractor that actually broke. Several sit on AUTO-TRACKED model roles, so the next tier
    bump breaks whichever are still hand-rolled. This repo already has the rule for this exact
    shape: `extract_stop_leg_id` is one canonical helper across five call sites precisely so a
    fix cannot land in four of them."""
    offenders = _offenders()
    assert not offenders, (
        "these read the FIRST content block positionally — the 2026-08-06 outage, which cost "
        "two days of EP grading: " + ", ".join(offenders) +
        "\nUse shared.llm_response.first_text() instead.")


# ── the parse at each real call site survives a thinking-first response ────────────────────

@pytest.mark.parametrize("module,fn", [
    ("agents.market_intelligence.catalyst_materiality", None),
    ("agents.market_intelligence.theme_engine", None),
    ("agents.market_intelligence.scheduler", None),
    ("agents.market_intelligence.agent", None),
    ("core.context", None),
])
def test_every_repaired_module_imports_the_canonical_reader(module, fn):
    """A module that stopped indexing but re-hand-rolled its own loop is back to square one:
    the next fix lands in one copy and not the others."""
    import importlib
    m = importlib.import_module(module)
    assert hasattr(m, "first_text"), (
        f"{module} no longer imports the canonical response reader — if it hand-rolls its own "
        "block scan, the next model-shape change fixes some sites and misses this one")


def test_the_extractor_that_broke_uses_it_too():
    """The original fix was a local loop inside catalyst_metrics_extractor. Leaving it there
    would have made the helper cosmetic for the one caller that started all of this."""
    src = (REPO / "agents/market_intelligence/catalyst_metrics_extractor.py").read_text(
        encoding="utf-8")
    assert "first_text(data)" in src, (
        "the extractor is back to a hand-rolled block scan")
    assert "content_block_types(data)" in src, (
        "the extractor's diagnostic log no longer names the block types it got — that log line "
        "is what makes the NEXT shape change a five-minute diagnosis")
