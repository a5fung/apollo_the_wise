"""#267 — grade_holistic chart-axis anchoring (advisor 2026-06-17). The with-chart eval arm must
APPEND a candidate chart-axis instruction; without it the attached image is unanchored and the
judge (whose base rubric never mentions charts) would likely ignore it → false-negative eval.
Pins: chart_note appends to the prompt when set, and the LIVE path (chart_note=None) is
byte-identical to the existing prompt."""
import asyncio
from unittest.mock import AsyncMock, patch

from agents.market_intelligence import ep_grade_judge
from agents.market_intelligence.ep_grade_judge import _build_judge_prompt, grade_holistic

_PAYLOAD = {"ticker": "TEST", "score_tier": "MODERATE", "catalyst": "FDA approval",
            "ep_score": 60, "materiality_tier": "material"}


def _captured_prompt(**kw):
    """Call grade_holistic with invoke_forced_tool mocked; return the prompt it forwarded."""
    cap = {}

    async def _fake(client, prompt, **rest):
        cap["prompt"] = prompt
        cap["image_png"] = rest.get("image_png")
        return {"tier": "HIGH"}

    with patch.object(ep_grade_judge, "invoke_forced_tool", new=AsyncMock(side_effect=_fake)):
        asyncio.run(grade_holistic(object(), _PAYLOAD, **kw))
    return cap


def test_live_path_prompt_is_byte_identical():
    # chart_note=None (the live grade path) → exactly _build_judge_prompt, nothing appended.
    cap = _captured_prompt()
    assert cap["prompt"] == _build_judge_prompt(_PAYLOAD)
    assert cap["image_png"] is None


def test_chart_note_is_appended_when_set():
    note = "\n--- ATTACHED: DAILY CHART ---\nread the structure"
    cap = _captured_prompt(chart_note=note, image_png=b"\x89PNG\r\n\x1a\nX")
    base = _build_judge_prompt(_PAYLOAD)
    assert cap["prompt"] == f"{base}\n{note}"
    assert cap["prompt"].startswith(base)        # base rubric preserved, axis appended after
    assert cap["image_png"] == b"\x89PNG\r\n\x1a\nX"
