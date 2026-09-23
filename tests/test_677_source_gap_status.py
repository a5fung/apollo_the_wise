"""#677 — a source gap caps an EP at MODERATE and nothing measures what it costs.

THE DEFECT (PLAN.md #677): the weekly source-gap finder (source_gap_finder.py) and the
should've-entered table (missed_outcomes.py's `top_shouldve_entered_gaps`) are two
disconnected surfaces. CIFR 2026-09-16 proved it: the source-gap finder said we could
not source its +9.2% move; the should've-entered table separately said "MODERATE — not
entered" at +16%, skip_category=moderate_tier, catalyst_quality=strong — a strong
catalyst capped at MODERATE because we could not source it (ep_grade_judge.py rubric
point 1: "has_direct_source=false combined with a materiality-driven promotion is the
highest-risk pattern ... prefer the floor tier").

REPORTING ONLY (THE LINE): this file pins the SIGNAL (recomputed from the alert's own
stored `grounded_text`, the SAME markers the judge's rubric rule reads), the PURE
aggregation of it, and the render — never the judge, tier rule, or admission.

No live Postgres in this environment (tests/conftest.py::make_mock_pool is the
established idiom — see tests/test_missed_outcomes_cancelled_capture.py's docstring).
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import make_mock_pool

from agents.market_intelligence.missed_outcomes import (
    _fmt_source_status,
    _row_source_status,
    aggregate_source_gap_counts,
    format_gaps_section_for_weekly,
    format_source_gap_summary,
    strong_catalyst_moderate_source_gap,
    top_shouldve_entered_gaps,
)

MOD = "agents.market_intelligence.missed_outcomes"

# The CIFR 2026-09-16 corpus shape per PLAN.md #677: graded off a web summary only — no
# SEC filing, no Benzinga wire — which is exactly why the judge's rubric rule caps it.
_CIFR_GROUNDED_TEXT = (
    "[Web summary] ERCOT disclosed grid access for 3.2 GW across CIFR's Texas sites."
)
_SEC_GROUNDED_TEXT = "[SEC 8-K filed 2026-09-16, items 2.02] grid access confirmed."


# ── _row_source_status: the tri-state signal ─────────────────────────────────────────

def test_row_source_status_true_on_sec_filing():
    assert _row_source_status(_SEC_GROUNDED_TEXT) is True


def test_row_source_status_false_on_web_summary_only():
    # THE CIFR CASE — a real catalyst, a web-only corpus, no direct source.
    assert _row_source_status(_CIFR_GROUNDED_TEXT) is False


def test_row_source_status_none_when_no_corpus():
    assert _row_source_status(None) is None
    assert _row_source_status("") is None


def test_row_source_status_none_on_thin_pre_grounding_corpus():
    # No section markers at all ([SEC/[Benzinga/[Web summary]) — not assessable, and
    # must NOT collapse into False (that would overstate the sourcing-gap count).
    assert _row_source_status("some free-text catalyst note with no markers") is None


# ── aggregate_source_gap_counts: the pure standing-question aggregator ──────────────

_ROWS = [
    # CIFR-shaped: strong catalyst, web-only corpus -> unsourced (the source-gap pop).
    {"catalyst_quality": "strong", "grounded_text": _CIFR_GROUNDED_TEXT},
    # strong catalyst, SEC-sourced -> sourced (a real judge call, not a gap).
    {"catalyst_quality": "strong", "grounded_text": _SEC_GROUNDED_TEXT},
    # game_changer catalyst, no corpus at all -> unassessed.
    {"catalyst_quality": "game_changer", "grounded_text": None},
    # routine catalyst -> EXCLUDED from the population entirely (not a MODERATE-cap-
    # for-catalyst-strength case; the rule capping it is unrelated to sourcing).
    {"catalyst_quality": "routine", "grounded_text": None},
]


def test_aggregate_counts_split_correctly():
    a = aggregate_source_gap_counts(_ROWS)
    assert a == {"denom": 3, "unsourced": 1, "sourced": 1, "unassessed": 1}


def test_aggregate_excludes_non_strong_catalyst_from_denominator():
    a = aggregate_source_gap_counts([{"catalyst_quality": "routine",
                                       "grounded_text": _CIFR_GROUNDED_TEXT}])
    assert a["denom"] == 0


def test_aggregate_empty_rows_safe():
    assert aggregate_source_gap_counts([]) == {
        "denom": 0, "unsourced": 0, "sourced": 0, "unassessed": 0}


# ── format_source_gap_summary: the standing number, with denominator + era ──────────

def test_summary_states_denominator_and_window_era():
    text = format_source_gap_summary({"denom": 18, "unsourced": 9, "sourced": 8,
                                       "unassessed": 1, "window_days": 60})
    assert "60d" in text and "n=18" in text
    assert "9 capped for want of a direct source" in text
    assert "8 had one" in text
    assert "1 not assessable" in text


def test_summary_blank_when_no_population():
    assert format_source_gap_summary({"denom": 0}) == ""
    assert format_source_gap_summary(None) == ""


# ── _fmt_source_status: the table's src column ───────────────────────────────────────

def test_fmt_source_status_codes():
    assert _fmt_source_status(True) == "SRC"
    assert _fmt_source_status(False) == "GAP"
    assert _fmt_source_status(None) == "  —"


# ── format_gaps_section_for_weekly: CIFR renders as ONE line, not two sections ───────

def _cifr_gap_row():
    return {"ticker": "CIFR", "alert_date": date(2026, 9, 16),
            "skip_category": "moderate_tier", "catalyst_quality": "strong",
            "max_high_5d": 0.16, "ret_5d": 0.14, "has_direct_source": False}


def test_cifr_row_carries_gap_status_and_moderate_reason_together():
    out = format_gaps_section_for_weekly([_cifr_gap_row()])
    assert "CIFR" in out
    assert "MODERATE — not entered" in out    # the should've-entered reason
    assert "GAP" in out                        # the source status, SAME line
    assert "+16%" in out
    # Both facts land in the SAME row of the SAME table — not two sections that
    # never reference each other (the #677 WOULD-FAIL-IF).
    cifr_line = next(l for l in out.splitlines() if "CIFR" in l)
    assert "GAP" in cifr_line and "MODERATE — not entered" in cifr_line


def test_direct_sourced_row_renders_src_not_gap():
    row = _cifr_gap_row()
    row["has_direct_source"] = True
    out = format_gaps_section_for_weekly([row])
    line = next(l for l in out.splitlines() if "CIFR" in l)
    assert "SRC" in line and "GAP" not in line


def test_unassessed_row_renders_dash_not_gap():
    row = _cifr_gap_row()
    row["has_direct_source"] = None
    out = format_gaps_section_for_weekly([row])
    line = next(l for l in out.splitlines() if "CIFR" in l)
    assert "GAP" not in line and "SRC" not in line


def test_gaps_section_embeds_standing_summary_line():
    out = format_gaps_section_for_weekly(
        [_cifr_gap_row()],
        {"denom": 18, "unsourced": 9, "sourced": 8, "unassessed": 1, "window_days": 60},
    )
    assert "n=18" in out and "60d" in out
    # Summary line must appear BEFORE the per-row table (a reader sees the standing
    # count before the ranked rows), and the table must still render.
    assert out.index("n=18") < out.index("CIFR")


def test_gaps_section_omits_summary_when_not_given():
    out = format_gaps_section_for_weekly([_cifr_gap_row()])
    assert "n=" not in out


def test_missing_has_direct_source_key_renders_dash_not_crash():
    # Old-shape row (pre-#677 dict, e.g. from a caller that hasn't been updated) must
    # degrade to "not assessable", never KeyError.
    row = {"ticker": "FTNT", "alert_date": date(2026, 5, 7),
           "skip_category": "cap_blocked", "max_high_5d": 0.18, "ret_5d": 0.12}
    out = format_gaps_section_for_weekly([row])
    line = next(l for l in out.splitlines() if "FTNT" in l)
    assert "GAP" not in line and "SRC" not in line


# ── behavioral DB-level tests (mocked asyncpg — no live Postgres available) ─────────

@pytest.mark.asyncio
async def test_top_shouldve_entered_gaps_computes_source_status_from_join():
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[
        {"ticker": "CIFR", "alert_date": date(2026, 9, 16), "source": "moderate_alert",
         "skip_category": "moderate_tier", "skip_reason": None, "ep_score": 62.0,
         "catalyst_quality": "strong", "open_d0": 12.0, "ret_5d": 0.14,
         "max_high_5d": 0.16, "grounded_text": _CIFR_GROUNDED_TEXT},
    ])
    with patch(f"{MOD}.get_pool", new=AsyncMock(return_value=pool)):
        rows = await top_shouldve_entered_gaps(window_days=30, limit=8)
    assert len(rows) == 1
    assert rows[0]["has_direct_source"] is False
    # grounded_text is raw corpus text — must not leak into the returned row (telemetry
    # hygiene; the caller only needs the boolean verdict).
    assert "grounded_text" not in rows[0]


@pytest.mark.asyncio
async def test_top_shouldve_entered_gaps_query_joins_alerts_for_grounded_text():
    # SQL-shape check on the ACTUAL executed query (runtime string, not a source pin —
    # same idiom as test_missed_outcomes_cancelled_capture.py's _run_and_capture_sql).
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    with patch(f"{MOD}.get_pool", new=AsyncMock(return_value=pool)):
        await top_shouldve_entered_gaps()
    sql = conn.fetch.call_args_list[0].args[0]
    assert "LEFT JOIN LATERAL" in sql
    assert "grounded_text" in sql
    assert "mi_ep_alerts" in sql


@pytest.mark.asyncio
async def test_strong_catalyst_moderate_source_gap_filters_to_moderate_tier():
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[
        {"catalyst_quality": "strong", "grounded_text": _CIFR_GROUNDED_TEXT},
        {"catalyst_quality": "strong", "grounded_text": _SEC_GROUNDED_TEXT},
    ])
    with patch(f"{MOD}.get_pool", new=AsyncMock(return_value=pool)):
        result = await strong_catalyst_moderate_source_gap(window_days=60)
    assert result == {"denom": 2, "unsourced": 1, "sourced": 1, "unassessed": 0,
                       "window_days": 60}
    sql = conn.fetch.call_args_list[0].args[0]
    assert "skip_category = 'moderate_tier'" in sql
