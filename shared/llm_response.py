"""One place that reads an Anthropic response. Never index `content[0]` again (#544).

**THE INCIDENT.** On 2026-08-06 the earnings-metrics extractor started failing on EVERY call
with `KeyError: 'text'`. For two sessions it graded ~14 earnings names a day as weak — on an
exception — including an entire software cohort gapping together. Nothing alerted. The operator
found it by noticing there were no EP alerts during earnings season.

**THE BUG WAS ONE CHARACTER OF ASSUMPTION:** `data["content"][0]["text"]`. True for
sonnet-4-6, false for sonnet-5, which returns a **thinking block first**. The grade-quality eval
gate passed throughout, because it measures grades and this was a parse.

**WHY A HELPER AND NOT NINE FIXES.** The same positional assumption existed at ten sites — five
in the theme engine, plus the market agent, the scheduler, catalyst materiality and the
orchestrator's own context compression. Several sit on auto-tracked model roles, so the next
tier bump breaks whichever ones are still hand-rolled. This repo already has the rule for
exactly this shape: `extract_stop_leg_id` is one canonical helper across five call sites
precisely so a future fix cannot land in four of them. Same discipline, applied to LLM
responses.

**THE CONTRACT:** take the first block whose `type` is `"text"`, wherever it sits. Never assume
position, never assume the block count, never assume a `.text` attribute exists. Works on both
the SDK object and the raw-HTTP dict shape, because both are used in this codebase.
"""
from __future__ import annotations

from typing import Any

__all__ = ["first_text", "content_block_types"]


def _blocks(response: Any) -> list:
    """The content list off an SDK response OR a raw-HTTP JSON dict. Empty list if absent."""
    if response is None:
        return []
    if isinstance(response, dict):
        blocks = response.get("content")
    else:
        blocks = getattr(response, "content", None)
    return list(blocks) if isinstance(blocks, (list, tuple)) else []


def _block_type(block: Any) -> str:
    if isinstance(block, dict):
        return str(block.get("type") or "")
    return str(getattr(block, "type", "") or "")


def _block_text(block: Any) -> str:
    if isinstance(block, dict):
        return str(block.get("text") or "")
    return str(getattr(block, "text", "") or "")


def first_text(response: Any, default: str = "") -> str:
    """The first TEXT block's text — the model's actual answer.

    Returns `default` (empty string) when there is no text block at all, which is a real and
    meaningful outcome: a response that is pure thinking, or pure tool_use, has no prose answer.
    Callers must treat "" as "the model did not answer in text" and NOT as "the model said
    nothing was there" — conflating those is the shape of the 08-06 outage, where a parse
    failure was read downstream as a weak catalyst.

    Deliberately does NOT concatenate multiple text blocks: every caller here parses a single
    JSON object or a single prose answer, and joining blocks would silently corrupt the JSON
    ones. If a caller ever genuinely needs all the prose, give it its own function.
    """
    for block in _blocks(response):
        if _block_type(block) == "text":
            text = _block_text(block)
            if text:
                return text
    return default


def content_block_types(response: Any) -> list[str]:
    """The block types in order — for logging when `first_text` comes back empty. Knowing it
    was `['thinking']` rather than `[]` is the difference between a five-minute diagnosis and
    the two days the 08-06 outage actually took."""
    return [_block_type(b) for b in _blocks(response)]
