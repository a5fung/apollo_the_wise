"""S6/#405 (2026-07-03) — separate GRADE (cached at completion) from FILTERS
(re-run every tick).

Pre-#405 bug: the M&A / routine-catalyst / pm-shares-floor filters ran
BEFORE the catalyst cache-store, so a filter-skipped ticker was never
cached — a full LLM re-grade fired on every 5-min scan tick (CMCSA class,
36x/day). The hazard: the cached path skips the filters entirely and is
entry-producing, which was only safe because pre-#405 ONLY filter-survivors
ever reached the cache. Naively caching filtered tickers would have let
them skip the M&A filter on a later tick and wrongly enter.

Two layers of coverage:

1. `_post_grade_filters` unit tests — pin the extracted helper's ORDER,
   reason strings, and thresholds byte-identical to the pre-#405 inline
   checks (M&A -> routine-catalyst -> pm-shares floor).

2. Tick-contract tests (a)/(b)/(c) from the task card — drive the REAL
   `ep_detector._catalyst_cache` global and the REAL `_post_grade_filters`
   helper through a minimal two-tick harness that mirrors the documented
   run_ep_scan contract (design points 2/3 in the S6/#405 card): cache the
   grade at completion tagged `filters_cleared`; on a cache hit with
   filters_cleared=False, re-run filters with NO grade call; a filters
   PASS flips the flag and proceeds like a fresh survivor; a filters
   PASS from the start (survivor path) never re-invokes the filters check
   on a later tick at all.

   This harness intentionally does NOT invoke `run_ep_scan` itself — that
   function has ~20 DB/network dependencies and zero existing test
   precedent (grepped; no test in this suite mocks it). It DOES exercise
   the two production artifacts the design isolates for reuse
   (`_catalyst_cache`'s real tuple shape + `_post_grade_filters`'s real
   logic), which is where the hazard actually lives. The run_ep_scan
   wiring itself (cache-store call sites, control-flow order) was verified
   by direct code reading, not by this file — see the S6/#405 commit
   message / report for that trace.
"""
import contextlib
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence import ep_detector


_TODAY = date(2026, 7, 3)


@pytest.fixture(autouse=True)
def _fresh_cache():
    """Isolate the module-level catalyst cache across tests."""
    ep_detector._catalyst_cache = {}
    ep_detector._catalyst_cache_date = _TODAY
    yield
    ep_detector._catalyst_cache = {}
    ep_detector._catalyst_cache_date = None


def _no_mna():
    return patch.object(ep_detector, "is_likely_ma", AsyncMock(return_value=(False, None)))


def _yes_mna(source="keyword_in_text_0"):
    return patch.object(
        ep_detector, "is_likely_ma",
        AsyncMock(return_value=(True, {"source": source})),
    )


@contextlib.contextmanager
def _quiet_audit():
    """Silence log_audit_event + should_log_mna_filter_fired — DB-backed,
    irrelevant to the filter-logic being pinned here."""
    with patch.object(ep_detector, "log_audit_event", AsyncMock(return_value=None)), \
         patch(
             "agents.market_intelligence.ma_filter.should_log_mna_filter_fired",
             AsyncMock(return_value=False),
         ):
        yield


# ── 1. _post_grade_filters: order + reason strings + thresholds (FROZEN) ────

@pytest.mark.asyncio
async def test_filters_clear_returns_none():
    with _no_mna(), _quiet_audit():
        reason = await ep_detector._post_grade_filters(
            "AAPL", "strong", "analysis", "news", 15.0, 100_000, None, _TODAY,
        )
    assert reason is None


@pytest.mark.asyncio
async def test_mna_filter_fires_with_exact_reason_string():
    with _yes_mna(), _quiet_audit():
        reason = await ep_detector._post_grade_filters(
            "AVNS", "strong", "analysis", "news", 15.0, 100_000, None, _TODAY,
        )
    assert reason == "M&A/buyout catalyst — no momentum trade"


@pytest.mark.asyncio
async def test_routine_low_gap_filter_fires_with_exact_reason_string():
    with _no_mna(), _quiet_audit():
        reason = await ep_detector._post_grade_filters(
            "CMCSA", "routine", "analysis", "news", 8.5, 100_000, None, _TODAY,
        )
    assert reason == "routine catalyst, gap 8.5%"


@pytest.mark.asyncio
async def test_routine_filter_does_not_fire_at_gap_12_threshold():
    # Frozen threshold: strictly < 12 fires, >= 12 clears.
    with _no_mna(), _quiet_audit():
        reason = await ep_detector._post_grade_filters(
            "CMCSA", "routine", "analysis", "news", 12.0, 100_000, None, _TODAY,
        )
    assert reason is None


@pytest.mark.asyncio
async def test_pm_shares_floor_fires_below_threshold_no_carveout():
    with _no_mna(), _quiet_audit():
        reason = await ep_detector._post_grade_filters(
            "TINY", "strong", "analysis", "news", 5.0, 10_000, None, _TODAY,
        )
    assert reason == "pre-mkt volume 10,000 < 25,000 shares"


@pytest.mark.asyncio
async def test_pm_shares_floor_bypassed_by_pm_rvol_carveout():
    # quality="strong" so the routine-gap filter (checked earlier) never
    # fires — isolates the pm-shares carve-out specifically.
    with _no_mna(), _quiet_audit():
        reason = await ep_detector._post_grade_filters(
            "TINY", "strong", "analysis", "news", 5.0, 10_000, 5.5, _TODAY,
        )
    assert reason is None


@pytest.mark.asyncio
async def test_pm_shares_floor_bypassed_by_r6_strong_carveout():
    with _no_mna(), _quiet_audit():
        reason = await ep_detector._post_grade_filters(
            "TINY", "strong", "analysis", "news", 11.0, 10_000, None, _TODAY,
        )
    assert reason is None


@pytest.mark.asyncio
async def test_pm_shares_floor_r6_carveout_requires_strong_not_routine():
    # gap=13% clears the earlier routine-gap filter (needs >= 12) so this
    # isolates the R6 carve-out's own catalyst_quality=='strong' condition —
    # "routine" at the same gap/volume must NOT get the carve-out.
    with _no_mna(), _quiet_audit():
        reason = await ep_detector._post_grade_filters(
            "TINY", "routine", "analysis", "news", 13.0, 10_000, None, _TODAY,
        )
    assert reason is not None
    assert "pre-mkt volume" in reason


@pytest.mark.asyncio
async def test_order_mna_checked_before_routine_catalyst():
    """A ticker that would ALSO fail the routine-gap filter must still report
    the M&A reason — pins M&A-first order (byte-identical to pre-#405)."""
    with _yes_mna(), _quiet_audit():
        reason = await ep_detector._post_grade_filters(
            "XYZ", "routine", "analysis", "news", 3.0, 100_000, None, _TODAY,
        )
    assert reason == "M&A/buyout catalyst — no momentum trade"


@pytest.mark.asyncio
async def test_order_routine_checked_before_pm_shares_floor():
    """A ticker that would ALSO fail the pm-shares floor must still report
    the routine reason — pins routine-before-pm-volume order."""
    with _no_mna(), _quiet_audit():
        reason = await ep_detector._post_grade_filters(
            "XYZ", "routine", "analysis", "news", 3.0, 10_000, None, _TODAY,
        )
    assert reason == "routine catalyst, gap 3.0%"


# ── 2. Tick-contract hard-gate tests (a)/(b)/(c) ─────────────────────────────

async def _tick(ticker, gap_pct, today_volume, pm_rvol, grade_calls, *,
                 grade_quality="strong"):
    """Minimal two-artifact simulation of the run_ep_scan cache/filter
    contract (S6/#405 design points 2/3): drives the REAL `_catalyst_cache`
    dict and the REAL `_post_grade_filters` helper. `grade_calls` is a list
    the test appends to every time a fresh LLM grade would fire — the thing
    the hard-gate tests assert on.

    Returns "ENTER" or ("SKIP", reason).
    """
    cached = ep_detector._catalyst_cache.get(ticker)
    if cached:
        if not cached.filters_cleared:
            skip_reason = await ep_detector._post_grade_filters(
                ticker, cached.catalyst_quality, cached.claude_analysis,
                cached.news_summary, gap_pct, today_volume, pm_rvol, _TODAY,
            )
            if skip_reason:
                return ("SKIP", skip_reason)
            ep_detector._catalyst_cache[ticker] = cached._replace(filters_cleared=True)
        return "ENTER"
    # Fresh grade — the expensive LLM path.
    grade_calls.append(ticker)
    cq, ca, ns, pq = grade_quality, "analysis text", "news text", None
    skip_reason = await ep_detector._post_grade_filters(
        ticker, cq, ca, ns, gap_pct, today_volume, pm_rvol, _TODAY,
    )
    ep_detector._catalyst_cache[ticker] = ep_detector.CachedGrade(
        cq, 1.0, ns, ca, pq, skip_reason is None,
    )
    if skip_reason:
        return ("SKIP", skip_reason)
    return "ENTER"


@pytest.mark.asyncio
async def test_hard_gate_a_mna_filtered_stays_filtered_one_grade_call():
    """(a) graded-then-M&A-filtered tick 1, still M&A-positive tick 2 ->
    NO entry either tick, exactly ONE LLM-grade call across both ticks."""
    grade_calls = []
    with _yes_mna(), _quiet_audit():
        r1 = await _tick("MNA1", 15.0, 100_000, None, grade_calls)
        r2 = await _tick("MNA1", 15.0, 100_000, None, grade_calls)

    assert r1 == ("SKIP", "M&A/buyout catalyst — no momentum trade")
    assert r2 == ("SKIP", "M&A/buyout catalyst — no momentum trade")
    assert grade_calls == ["MNA1"], f"expected exactly 1 grade call, got {grade_calls}"
    # Never cached as entry-eligible.
    assert ep_detector._catalyst_cache["MNA1"].filters_cleared is False


@pytest.mark.asyncio
async def test_hard_gate_b_filter_clears_on_later_tick_becomes_entry_eligible():
    """(b) filtered tick 1 (routine + gap<12), filter condition clears tick 2
    (gap rises to >=12) -> proceeds exactly like a fresh survivor (entry-
    eligible), never LESS conservative than today (still only 1 grade call,
    still ran the real filter check both ticks)."""
    grade_calls = []
    with _no_mna(), _quiet_audit():
        r1 = await _tick("CLR1", 8.0, 100_000, None, grade_calls, grade_quality="routine")
        assert r1 == ("SKIP", "routine catalyst, gap 8.0%")
        assert ep_detector._catalyst_cache["CLR1"].filters_cleared is False  # not yet cleared

        r2 = await _tick("CLR1", 13.0, 100_000, None, grade_calls, grade_quality="routine")

    assert r2 == "ENTER"
    assert grade_calls == ["CLR1"], f"expected exactly 1 grade call, got {grade_calls}"
    assert ep_detector._catalyst_cache["CLR1"].filters_cleared is True  # flipped


@pytest.mark.asyncio
async def test_hard_gate_b_never_less_conservative_still_filtered_stays_filtered():
    """Companion to (b): if the filter condition does NOT clear, the ticker
    must still be skipped on tick 2 (the flip is real, not a fallthrough)."""
    grade_calls = []
    with _no_mna(), _quiet_audit():
        r1 = await _tick("CLR2", 8.0, 100_000, None, grade_calls, grade_quality="routine")
        r2 = await _tick("CLR2", 9.0, 100_000, None, grade_calls, grade_quality="routine")

    assert r1 == ("SKIP", "routine catalyst, gap 8.0%")
    assert r2 == ("SKIP", "routine catalyst, gap 9.0%")
    assert grade_calls == ["CLR2"]
    assert ep_detector._catalyst_cache["CLR2"].filters_cleared is False


@pytest.mark.asyncio
async def test_hard_gate_c_survivor_path_unchanged():
    """(c) survivor path unchanged: grades once, caches filters_cleared=True
    immediately, later ticks are entry-eligible with NO further LLM call AND
    no re-invocation of _post_grade_filters at all (today's fast path)."""
    grade_calls = []
    with _no_mna(), _quiet_audit():
        r1 = await _tick("SURV1", 20.0, 100_000, None, grade_calls, grade_quality="game_changer")
        assert ep_detector._catalyst_cache["SURV1"].filters_cleared is True  # cleared on first tick

        # Second tick: patch _post_grade_filters to blow up if invoked —
        # today's fast path (filters_cleared=True) must never call it.
        with patch.object(
            ep_detector, "_post_grade_filters",
            AsyncMock(side_effect=AssertionError("must not re-run filters on a cleared cache hit")),
        ):
            r2 = await _tick("SURV1", 20.0, 100_000, None, grade_calls, grade_quality="game_changer")

    assert r1 == "ENTER"
    assert r2 == "ENTER"
    assert grade_calls == ["SURV1"], f"expected exactly 1 grade call, got {grade_calls}"
