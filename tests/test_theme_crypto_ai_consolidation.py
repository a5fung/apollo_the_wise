"""#368 crypto→AI-conversion consolidation (2026-08-04) — four surgical fixes.

The failure (operator ground truth, #368 labelling): one real phenomenon — crypto
miners converting power/data-centre capacity to AI compute — was born under 8+
theme names Mar–Aug 2026, none surviving, members oscillating between the crypto
and AI framings. Mechanisms (prod-evidenced, docs/analysis/
368_crypto_ai_consolidation_replay_2026-08-04.md):

  1. Arm-B Stage A had NO stem family for either framing → the near-duplicate
     themes were never once paired for adjudication → `compute_infra` family.
  2. Single-print RS pruning evicted the (rising) recovery cohort on day 2 of
     its ignition → rising-recovery hold on both prune paths.
  3. The retire counter kept running through hysteresis-held Fading rows — the
     theme retired 8/04, one day AFTER its 8/03 recovery confirmed → weak-only
     fading streak.
  4. Description-vs-name validation evicted converting miners from the AI theme
     whose own thesis said "Bitcoin-miner-to-AI infrastructure" (7/27 kill) →
     the validator now sees the theme's thesis.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from agents.market_intelligence import theme_engine
from agents.market_intelligence.theme_merge_arm import (
    FAMILIES, family_of, propose_merge_pairs,
)

MONDAY = date(2026, 7, 27)    # validation runs Mon/Wed/Fri
TUESDAY = date(2026, 7, 28)   # no validation


# ── 1. compute_infra Stage-A family — WITHDRAWN 2026-08-04, NOT SHIPPED ──────
#
# The family that would let the crypto-framed and AI-framed shards of one cohort
# finally meet the adjudicator was built, then held after its own pre-deploy gate
# ran against the REAL Stage-B judge on the two frozen historical pairs:
#
#   P1 (2026-07-21)  verdict=DISTINCT       (the gate's own hold condition)
#   P2 (2026-08-04)  verdict=PARENT_CHILD
#   N1 (optical)     verdict=DISTINCT       (negative control — correct)
#
# PARENT_CHILD is NOT a consolidation on this codebase's own terms. The
# operator-signed v2 prompt ruling (7/12, rulings-pack R3) states it directly, in
# theme_merge_arm.py right above the code this would have changed: v1 'answered
# PARENT_CHILD to pure slices, which keeps both themes and leaves the fragmentation
# (#274's whole purpose) unfixed'. And the persistence path for a PARENT_CHILD
# verdict — parent_theme + sub_theme_parents — is ADR 0032 Phase 2, which is task
# #471 and is NOT BUILT. So both historical pairs deliver zero consolidation, and
# the winning verdict has nowhere to be written.
#
# So the fix is real but PREMATURE: it is gated on #471 Phase 2, filed as #529.
# Fixes 2-4 below are independent of it and shipped.

# ── 2. rising-recovery prune hold ────────────────────────────────────────────

def test_rs_rising_boundaries():
    assert theme_engine._rs_rising([18.3, 18.4, 13.5, 16.6]) is True    # newest > oldest
    assert theme_engine._rs_rising([9.7, 8.6, 10.1, 13.5]) is False     # falling
    assert theme_engine._rs_rising([10.0, 12.0, 10.0]) is False         # too few points
    assert theme_engine._rs_rising([]) is False
    assert theme_engine._rs_rising([10.0, 11.0, 12.0, 10.0]) is False   # flat = not rising


def _rescore_mocks(monkeypatch, rs_history: dict[str, list[float]]):
    """Silence I/O for the full rescore path; feed a canned RS-history batch."""
    async def fake_batch(tickers, today, days=3):
        return {tk: rs_history.get(tk, []) for tk in tickers}

    async def fake_history(name, days=7, tickers=None):
        return []

    async def fake_news(name, tickers=None):
        return 30, "solid description", False

    async def fake_breadth(tickers, today):
        return 0.9

    async def fake_audit(event_type, summary, detail=None):
        pass

    monkeypatch.setattr(theme_engine, "get_recent_rs_batch", fake_batch)
    monkeypatch.setattr(theme_engine, "_get_theme_history", fake_history)
    monkeypatch.setattr(theme_engine, "_news_check", fake_news)
    monkeypatch.setattr(theme_engine, "get_ticker_breadth_above_sma20", fake_breadth)
    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)


# The real 2026-07-22 shape: CIFR/HUT/CORZ strong, WULF sub-25 but RISING off the
# 7/21 ignition — pre-fix WULF was pruned that day, splitting the cohort.
STOCKS_722 = {
    "CIFR": {"ticker": "CIFR", "rs_composite": 96.7, "sector": "Technology"},
    "HUT": {"ticker": "HUT", "rs_composite": 92.3, "sector": "Financial Services"},
    "CORZ": {"ticker": "CORZ", "rs_composite": 64.5, "sector": "Technology"},
    "WULF": {"ticker": "WULF", "rs_composite": 18.3, "sector": "Technology"},
}


@pytest.mark.asyncio
async def test_hard_prune_holds_rising_recovery_member(monkeypatch):
    _rescore_mocks(monkeypatch, {"WULF": [18.3, 18.4, 13.5, 13.8, 12.7, 16.6]})
    theme = {"name": "T", "tickers": ["CIFR", "HUT", "CORZ", "WULF"], "score": 60,
             "stage": "Nascent", "description": "d"}
    result, changelog = await theme_engine._rescore_existing_theme(
        theme, STOCKS_722, TUESDAY, protected=set())
    assert result is not None
    assert "WULF" in result["tickers"]
    held = [c for c in changelog if c["type"] == "ticker_prune_held_rising"]
    assert held and held[0]["ticker"] == "WULF"
    assert not any(c["type"] == "ticker_pruned" for c in changelog)


@pytest.mark.asyncio
async def test_hard_prune_still_prunes_falling_member(monkeypatch):
    _rescore_mocks(monkeypatch, {"WULF": [18.3, 20.0, 22.0, 25.0, 27.0, 29.4]})  # falling
    theme = {"name": "T", "tickers": ["CIFR", "HUT", "CORZ", "WULF"], "score": 60,
             "stage": "Nascent", "description": "d"}
    result, changelog = await theme_engine._rescore_existing_theme(
        theme, STOCKS_722, TUESDAY, protected=set())
    assert "WULF" not in result["tickers"]
    pruned = [c for c in changelog if c["type"] == "ticker_pruned"]
    assert pruned and pruned[0]["ticker"] == "WULF"


@pytest.mark.asyncio
async def test_hard_prune_short_history_fails_conservative(monkeypatch):
    # only 3 points (< PRUNE_HOLD_MIN_POINTS) — prune exactly as before
    _rescore_mocks(monkeypatch, {"WULF": [18.3, 13.5, 12.7]})
    theme = {"name": "T", "tickers": ["CIFR", "HUT", "CORZ", "WULF"], "score": 60,
             "stage": "Nascent", "description": "d"}
    result, changelog = await theme_engine._rescore_existing_theme(
        theme, STOCKS_722, TUESDAY, protected=set())
    assert "WULF" not in result["tickers"]
    assert not any(c["type"] == "ticker_prune_held_rising" for c in changelog)


@pytest.mark.asyncio
async def test_soft_prune_holds_v_shaped_ignition(monkeypatch):
    """The real IREN 7/23 shape: [34.5, 10.7, 7.4, ...] — 3 consecutive days below
    the soft floor ONLY because the base of the V is inside the window. Pre-fix the
    soft prune read a name that TRIPLED its RS in 3 days as slow decay."""
    stocks = dict(STOCKS_722)
    stocks["IREN"] = {"ticker": "IREN", "rs_composite": 34.5, "sector": "Technology"}
    stocks["WULF"] = {"ticker": "WULF", "rs_composite": 80.0, "sector": "Technology"}
    _rescore_mocks(monkeypatch, {"IREN": [34.5, 10.7, 7.4, 6.0, 1.5, 1.7]})
    theme = {"name": "T", "tickers": ["CIFR", "HUT", "CORZ", "WULF", "IREN"],
             "score": 60, "stage": "Nascent", "description": "d"}
    result, changelog = await theme_engine._rescore_existing_theme(
        theme, stocks, TUESDAY, protected=set())
    assert "IREN" in result["tickers"]
    assert any(c["type"] == "ticker_prune_held_rising" and c["ticker"] == "IREN"
               for c in changelog)


@pytest.mark.asyncio
async def test_soft_prune_still_prunes_slow_decay(monkeypatch):
    stocks = dict(STOCKS_722)
    stocks["IREN"] = {"ticker": "IREN", "rs_composite": 30.0, "sector": "Technology"}
    stocks["WULF"] = {"ticker": "WULF", "rs_composite": 80.0, "sector": "Technology"}
    _rescore_mocks(monkeypatch, {"IREN": [30.0, 31.0, 33.0, 36.0, 40.0, 44.0]})  # decaying
    theme = {"name": "T", "tickers": ["CIFR", "HUT", "CORZ", "WULF", "IREN"],
             "score": 60, "stage": "Nascent", "description": "d"}
    result, changelog = await theme_engine._rescore_existing_theme(
        theme, stocks, TUESDAY, protected=set())
    assert "IREN" not in result["tickers"]
    assert any(c["type"] == "ticker_pruned" and c["ticker"] == "IREN" for c in changelog)


# ── 3. weak-only fading streak ───────────────────────────────────────────────

def _fading_row(rs_avg):
    return {"stage": "Fading", "rs_avg": rs_avg}


@pytest.mark.asyncio
async def test_fading_streak_counts_weak_rows(monkeypatch):
    async def fake_history(name, days=10, tickers=None):
        return [_fading_row(None)] * 3 + [{"stage": "Nascent", "rs_avg": 50.0}]
    monkeypatch.setattr(theme_engine, "_get_theme_history", fake_history)
    assert await theme_engine._count_consecutive_fading("T") == 3


@pytest.mark.asyncio
async def test_healthy_held_fading_row_breaks_streak(monkeypatch):
    """The 8/03 prod shape: 5 weak-Fading rows, then the theme re-qualified healthy
    (elite pair) but hysteresis held the STAGE at Fading — that row carries rs_avg.
    Pre-fix the streak read 6 and retired the theme on 8/04, one day after the
    recovery confirmed. The rs_avg-bearing row must break the retire streak."""
    async def fake_history(name, days=10, tickers=None):
        # newest first: the healthy-but-held row (rs_avg 84.9), then 5 weak rows
        return [_fading_row(84.9)] + [_fading_row(None)] * 5
    monkeypatch.setattr(theme_engine, "_get_theme_history", fake_history)
    assert await theme_engine._count_consecutive_fading("T") == 0


@pytest.mark.asyncio
async def test_weak_streak_stops_at_embedded_healthy_row(monkeypatch):
    async def fake_history(name, days=10, tickers=None):
        return [_fading_row(None)] * 2 + [_fading_row(60.0)] + [_fading_row(None)] * 5
    monkeypatch.setattr(theme_engine, "_get_theme_history", fake_history)
    assert await theme_engine._count_consecutive_fading("T") == 2


@pytest.mark.asyncio
async def test_non_fading_row_still_breaks_streak(monkeypatch):
    async def fake_history(name, days=10, tickers=None):
        return [{"stage": "Accelerating", "rs_avg": 80.0}] + [_fading_row(None)] * 4
    monkeypatch.setattr(theme_engine, "_get_theme_history", fake_history)
    assert await theme_engine._count_consecutive_fading("T") == 0


# ── 4. thesis-aware validation ───────────────────────────────────────────────

def _capturing_client(remove_list, captured: list):
    class _Block:
        text = json.dumps({"remove": remove_list})

    class _Resp:
        content = [_Block()]
        stop_reason = "end_turn"

    class _Messages:
        async def create(self, *a, **kw):
            captured.append(kw["messages"][0]["content"])
            return _Resp()

    class _Client:
        messages = _Messages()

    return _Client()


CONVERSION_THESIS = (
    "Renewed focus on bitcoin miners as scarce, large-scale power and data-center "
    "landlords for the AI compute boom, re-rating names with contracted power "
    "capacity and AI/HPC pivots."
)


@pytest.mark.asyncio
async def test_validator_prompt_includes_sane_thesis(monkeypatch):
    captured: list[str] = []
    monkeypatch.setattr(theme_engine, "_get_anthropic_client",
                        lambda: _capturing_client([], captured))
    await theme_engine._validate_theme_membership(
        "AI Compute & GPU Data Center Hosting Operators", ["WULF", "CORZ", "APLD"],
        [], protected=set(), thesis=CONVERSION_THESIS)
    assert captured
    prompt = captured[0]
    assert "Theme thesis: " in prompt
    assert "power and data-center" in prompt
    assert "Judge against the THESIS above" in prompt
    # legacy structure intact
    assert "Identify stocks that DO NOT BELONG" in prompt
    assert prompt.rstrip().endswith('if all belong.')


@pytest.mark.asyncio
async def test_validator_prompt_without_thesis_is_legacy_shape(monkeypatch):
    captured: list[str] = []
    monkeypatch.setattr(theme_engine, "_get_anthropic_client",
                        lambda: _capturing_client([], captured))
    await theme_engine._validate_theme_membership(
        "Semiconductors", ["NVDA", "AMD"], [], protected=set())
    prompt = captured[0]
    assert "Theme thesis:" not in prompt
    assert "Judge against the THESIS" not in prompt
    assert "Identify stocks that DO NOT BELONG" in prompt


@pytest.mark.asyncio
async def test_validator_garbage_thesis_omitted(monkeypatch):
    captured: list[str] = []
    monkeypatch.setattr(theme_engine, "_get_anthropic_client",
                        lambda: _capturing_client([], captured))
    await theme_engine._validate_theme_membership(
        "Semiconductors", ["NVDA", "AMD"], [], protected=set(),
        thesis="The search results show no information about these stocks.")
    prompt = captured[0]
    assert "Theme thesis:" not in prompt        # _is_garbage → shielded members never
    assert "Judge against the THESIS" not in prompt


@pytest.mark.asyncio
async def test_validator_thesis_truncated_at_300(monkeypatch):
    captured: list[str] = []
    monkeypatch.setattr(theme_engine, "_get_anthropic_client",
                        lambda: _capturing_client([], captured))
    await theme_engine._validate_theme_membership(
        "T", ["A", "B"], [], protected=set(), thesis="x" * 1000)
    prompt = captured[0]
    assert "x" * 300 in prompt
    assert "x" * 301 not in prompt


@pytest.mark.asyncio
async def test_rescore_passes_theme_description_to_validator(monkeypatch):
    """Caller wiring: the Mon/Wed/Fri rescore validation must feed the theme's own
    stored description as the thesis (the 7/27 kill happened precisely because the
    validator never saw it)."""
    captured: list[str] = []
    monkeypatch.setattr(theme_engine, "_get_anthropic_client",
                        lambda: _capturing_client([], captured))
    _rescore_mocks(monkeypatch, {})
    theme = {"name": "AI Compute & GPU Data Center Hosting Operators",
             "tickers": ["CIFR", "HUT", "CORZ"], "score": 60,
             "stage": "Nascent", "description": CONVERSION_THESIS}
    await theme_engine._rescore_existing_theme(
        theme, STOCKS_722, MONDAY, protected=set())
    assert captured and "power and data-center" in captured[0]
