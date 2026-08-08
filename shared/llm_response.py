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

from typing import Any, Optional

__all__ = [
    "first_text",
    "content_block_types",
    "is_truncated",
    "stop_reason",
    "usage_tokens",
    "perplexity_finish_reason",
    "perplexity_usage_tokens",
]


def _attr(obj: Any, name: str) -> str:
    """One dict-or-object accessor. Both response shapes are in use here — the SDK returns
    objects, `catalyst_metrics_extractor` calls the API over urllib and sees dicts — and every
    field below needs the same duality, so it lives in one place rather than once per field."""
    if isinstance(obj, dict):
        return str(obj.get(name) or "")
    return str(getattr(obj, name, "") or "")


def _blocks(response: Any) -> list:
    """The content list off an SDK response OR a raw-HTTP JSON dict. Empty list if absent."""
    if response is None:
        return []
    blocks = response.get("content") if isinstance(response, dict) \
        else getattr(response, "content", None)
    return list(blocks) if isinstance(blocks, (list, tuple)) else []


def first_text(response: Any) -> str:
    """The first TEXT block's text — the model's actual answer.

    Returns "" when there is no text block at all, which is a real and meaningful outcome: a
    response that is pure thinking, or pure tool_use, has no prose answer. Callers must treat
    "" as "the model did not answer in text" and NOT as "the model said nothing was there" —
    conflating those is the shape of the 08-06 outage, where a parse failure was read
    downstream as a weak catalyst.

    Deliberately does NOT concatenate multiple text blocks: every caller here parses a single
    JSON object or a single prose answer, and joining blocks would silently corrupt the JSON
    ones. If a caller ever genuinely needs all the prose, give it its own function.
    """
    for block in _blocks(response):
        if _attr(block, "type") == "text" and _attr(block, "text"):
            return _attr(block, "text")
    return ""


def stop_reason(response: Any) -> Optional[str]:
    """The model's OWN report of why it stopped, or None when the response carries none.

    THE canonical stop_reason reader (#543). The spend trackers in BOTH containers derive the
    `api_usage.stop_reason` column through this — call sites no longer hand-thread
    `getattr(resp, "stop_reason", None)` at ~22 sites, because a kwarg threaded by hand at N
    sites is exactly how one site forgets and truncation goes dark there. Works on the SDK
    object and the raw-HTTP dict shape, same duality as `first_text`.
    """
    if response is None:
        return None
    raw = response.get("stop_reason") if isinstance(response, dict) \
        else getattr(response, "stop_reason", None)
    return str(raw) if raw is not None else None


def usage_tokens(response: Any) -> Optional[dict]:
    """The four Anthropic token counts off a response, or None when it carries no usage at all.

    Returns {"input_tokens", "output_tokens", "cache_creation_input_tokens",
    "cache_read_input_tokens"} with absent fields as 0. None (vs a dict of zeros) is a real
    distinction: the spend trackers SKIP a row when there is no usage object, but must still
    write one when usage exists with zero-valued fields.

    Dict-or-object at BOTH levels — the response may be a raw-HTTP JSON dict whose `usage` is
    also a dict (`catalyst_metrics_extractor`). That site used to wrap its dict in a
    SimpleNamespace purely to survive the tracker's getattr-based reader; this reader makes
    the wrap (and the zero-cost-row trap it patched over) unnecessary.
    """
    if response is None:
        return None
    usage = response.get("usage") if isinstance(response, dict) \
        else getattr(response, "usage", None)
    if usage is None:
        return None

    def _tok(name: str) -> int:
        raw = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, 0)
        return int(raw or 0)

    return {
        "input_tokens": _tok("input_tokens"),
        "output_tokens": _tok("output_tokens"),
        "cache_creation_input_tokens": _tok("cache_creation_input_tokens"),
        "cache_read_input_tokens": _tok("cache_read_input_tokens"),
    }


def perplexity_finish_reason(response: Any) -> Optional[str]:
    """Perplexity's stop reason, off its raw JSON. `'length'` is its word for truncation.

    Perplexity, not Anthropic, but it lives HERE because this module is the one place that
    reads an LLM response: the exact `(choices or [{}])[0].get(...)` dance was hand-copied to
    three call sites across two files on the night #544 shipped a whole module arguing against
    doing precisely that. One schema change should mean one edit. (Moved from
    `collector.pplx_finish_reason` when #543 made the spend tracker derive it internally —
    call sites no longer touch it at all.)
    """
    if not isinstance(response, dict):
        return None
    return ((response.get("choices") or [{}])[0] or {}).get("finish_reason")


def perplexity_usage_tokens(response: Any) -> dict:
    """Perplexity token counts (OpenAI naming: prompt/completion), zeros when absent.

    Zeros rather than None, unlike `usage_tokens`: a Perplexity row must land even with no
    usage block, because the per-request SEARCH FEE — the dominant cost — is owed regardless.
    """
    usage = response.get("usage") if isinstance(response, dict) \
        else getattr(response, "usage", None)

    def _tok(name: str) -> int:
        if usage is None:
            return 0
        raw = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, 0)
        return int(raw or 0)

    return {"prompt_tokens": _tok("prompt_tokens"),
            "completion_tokens": _tok("completion_tokens")}


def is_truncated(response: Any) -> bool:
    """True when the model was CUT OFF by max_tokens — i.e. this response is not an answer.

    Lives here, next to `first_text`, for the same reason `first_text` exists: the check was
    hand-copied into `judge_transport.invoke_forced_tool` and `ep_detector.
    _classify_catalyst_claude` on the same night, and the second copy's own comment said "same
    rule the shared judge transport now enforces" — the author noticed the duplication and
    copied it anyway. That is the `extract_stop_leg_id` shape exactly.

    The PREDICATE is shared; the HANDLING deliberately is NOT. The judge transport returns None
    into its fail-open; the catalyst grader RAISES, because its enclosing `except` is what runs
    the #273 credit-exhaustion alert. Two genuinely different contracts, one definition of
    "truncated".
    """
    return stop_reason(response) == "max_tokens"


def content_block_types(response: Any) -> list[str]:
    """The block types in order — for logging when `first_text` comes back empty. Knowing it
    was `['thinking']` rather than `[]` is the difference between a five-minute diagnosis and
    the two days the 08-06 outage actually took."""
    return [_attr(b, "type") for b in _blocks(response)]
