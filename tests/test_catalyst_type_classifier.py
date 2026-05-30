"""Unit tests for the isolated catalyst_type classifier (North Star C1).

Deterministic — the Anthropic client is faked, so no API calls / no network.
Covers the contract that matters for a fail-open advisory signal:
  - genuine "none" when there's nothing to classify (NOT a failure)
  - fail-open to None (NULL) on any hard error — never raises to caller
  - enum guard: out-of-enum model output → None (don't persist garbage)
  - happy path: valid tool output → that type + rationale

The `quality` gating call (ep_detector._classify_catalyst_claude / _CATALYST_TOOL)
is intentionally NOT touched by this module — see test_gating_call_untouched.
"""
from __future__ import annotations

import asyncio

from agents.market_intelligence import catalyst_type_classifier as ctc


# ── fakes ────────────────────────────────────────────────────────────────────
class _FakeBlock:
    type = "tool_use"

    def __init__(self, inp):
        self.input = inp


class _FakeResp:
    def __init__(self, inp):
        self.content = [_FakeBlock(inp)]


class _FakeClient:
    def __init__(self, inp=None, raise_exc=None):
        self._inp = inp
        self._raise = raise_exc

        async def _create(**_kw):
            if self._raise:
                raise self._raise
            return _FakeResp(self._inp)

        self.messages = type("M", (), {"create": staticmethod(_create)})()


def _run(coro):
    return asyncio.run(coro)


def _with_client(client):
    """Swap the module client getter; returns a restore fn."""
    orig = ctc._get_client
    ctc._get_client = lambda: client
    return lambda: setattr(ctc, "_get_client", orig)


# ── tests ────────────────────────────────────────────────────────────────────
def test_no_input_is_unknown_not_none():
    # No text → "unknown" (a coverage/knowledge gap), NOT "none", NOT None(failure).
    res = _run(ctc.classify_catalyst_type("XYZ", None, None))
    assert res["catalyst_type"] == "unknown"
    assert res["rationale"]  # explains why


def test_failopen_to_none_on_client_error():
    restore = _with_client(_FakeClient(raise_exc=RuntimeError("boom")))
    try:
        res = _run(ctc.classify_catalyst_type("XYZ", "some catalyst text", "analysis"))
    finally:
        restore()
    # Hard failure → None (NULL in DB), distinct from the model saying "none".
    assert res["catalyst_type"] is None
    assert res["rationale"] is None


def test_enum_guard_rejects_unknown_type():
    restore = _with_client(_FakeClient({"catalyst_type": "buyback_megatrend", "rationale": "x"}))
    try:
        res = _run(ctc.classify_catalyst_type("XYZ", "catalyst", "analysis"))
    finally:
        restore()
    assert res["catalyst_type"] is None  # out-of-enum is not persisted


def test_happy_path_returns_type_and_rationale():
    restore = _with_client(_FakeClient(
        {"catalyst_type": "theme", "rationale": "Part of the AI-infrastructure secular tailwind."}
    ))
    try:
        res = _run(ctc.classify_catalyst_type("NVDA", "AI datacenter demand", "secular AI"))
    finally:
        restore()
    assert res["catalyst_type"] == "theme"
    assert "AI" in res["rationale"]


def test_all_enum_values_are_distinct_and_ranked():
    # Hierarchy sanity: theme is most-powerful (rank 0), none is least.
    assert ctc.CATALYST_TYPE_RANK["theme"] == 0
    assert ctc.CATALYST_TYPE_RANK["unknown"] == len(ctc.CATALYST_TYPES) - 1
    assert "none" not in ctc.CATALYST_TYPES  # no false absence-of-catalyst class
    assert ctc.CATALYST_TYPE_RANK["policy"] < ctc.CATALYST_TYPE_RANK["sales_acceleration"]
    assert len(set(ctc.CATALYST_TYPES)) == len(ctc.CATALYST_TYPES)
    # pre_catalyst_anticipation: distinct slot (the backfill found the 'none' bucket
    # was really pre-earnings gaps) — ranks below operational, above other/none.
    assert "pre_catalyst_anticipation" in ctc.CATALYST_TYPES
    assert (ctc.CATALYST_TYPE_RANK["management_change"]
            < ctc.CATALYST_TYPE_RANK["pre_catalyst_anticipation"]
            < ctc.CATALYST_TYPE_RANK["other"])


def test_catalyst_type_renders_in_ep_block():
    """The shared /EP block surfaces catalyst_type with the right fire marker."""
    try:
        from agents.market_intelligence.briefing import _format_ep_ticker_block
    except Exception as e:  # pragma: no cover - local dep gaps
        import pytest
        pytest.skip(f"briefing import unavailable locally: {e}")
    base = {"ticker": "RCAT", "score_tier": "HIGH", "gap_pct": 16.1, "ep_score": 100.8,
            "rel_volume": 5, "catalyst_quality": "strong"}
    # high-tier type → 🎯 (NOT 🔥 — that's the HIGH tier emoji)
    blk = "\n".join(_format_ep_ticker_block({**base, "catalyst_type": "policy"}))
    assert "RCAT" in blk and "🎯policy" in blk
    # operational type → muted marker
    blk2 = "\n".join(_format_ep_ticker_block({**base, "ticker": "OMCL",
                                              "catalyst_type": "sales_acceleration"}))
    assert "▫️sales acceleration" in blk2
    # unknown (knowledge gap) → ❓ marker (cue the operator to investigate coverage)
    blku = "\n".join(_format_ep_ticker_block({**base, "ticker": "ZBRA",
                                              "catalyst_type": "unknown"}))
    assert "❓unknown" in blku
    # no catalyst_type (classifier unavailable) → no type-suffix marker, renders cleanly
    blk3 = "\n".join(_format_ep_ticker_block(base))
    assert "🎯" not in blk3 and "▫️" not in blk3


def test_gating_call_untouched():
    # The catalyst_type classifier must NOT have reached into the gating call's
    # tool schema. Assert the gating tool still has exactly its original fields
    # (quality + analysis) and no catalyst_type leaked in.
    from agents.market_intelligence.ep_detector import _CATALYST_TOOL
    props = _CATALYST_TOOL["input_schema"]["properties"]
    assert set(props.keys()) == {"quality", "analysis"}
    assert "catalyst_type" not in props
