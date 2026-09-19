"""#666 (2026-09-19) — trigger (b) stops correlating, starts counting.

WHY. Trigger (b) fired 2026-09-15 at p=0.086 (a coin does this 1 time in 12) and printed
revert SQL for the catalyst-tier lattice off a bare conversion-rate comparison. Operator:
"Don't revert, keep monitoring but make monitor more precise." `_lattice_prevented_alerts`
reconstructs, from real recorded rows (`mi_catalyst_tier_shadow` x `mi_ep_scan_log`), the
specific alerts the fact-check actually stopped — named by ticker and date, never inferred
from a rate — and `_lattice_b_accounts_for_shortfall` decides whether that named count
explains the shortfall trigger (b) is reporting. The wiring in
`run_catalyst_lattice_monitor` (withhold the revert SQL unless hard evidence — a P1 miss or
the always-armed zero-alert-days trigger — is also present) is pinned in
tests/test_catalyst_lattice_monitor.py alongside the rest of the monitor's runner tests;
this file covers the two new pieces of logic in isolation.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.market_intelligence import health_checks as hc


# ── the pure threshold: named count vs the reported shortfall ──────────────────────────────


def test_b_accounts_for_shortfall_is_strict_not_loose():
    """MUTATION PROVEN: flipping `prevented_count >= shortfall` to `>` in the source makes
    this test's first assertion (3 named preventions vs a shortfall of exactly 3.0) fail,
    since 3 > 3 is False — confirmed by hand during review; restored before commit."""
    assert hc._lattice_b_accounts_for_shortfall(3, 3.0) is True     # exact cover
    assert hc._lattice_b_accounts_for_shortfall(2, 3.0) is False    # short by one
    assert hc._lattice_b_accounts_for_shortfall(4, 3.0) is True     # more than covers it
    assert hc._lattice_b_accounts_for_shortfall(0, 0.0) is True     # nothing to explain
    assert hc._lattice_b_accounts_for_shortfall(0, -1.0) is True    # negative -> trivial


# ── the real recompute: a bespoke fake conn returning pre-joined rows ──────────────────────


class _PrevConn:
    """Returns pre-joined (mi_catalyst_tier_shadow x mi_ep_scan_log) rows — this fake never
    simulates the SQL JOIN itself, only the function's row-by-row reconstruction math and
    attribution guards, which is what actually differs from a rate comparison."""

    def __init__(self, rows=None, raise_exc=False):
        self.rows = rows if rows is not None else []
        self.raise_exc = raise_exc
        self.saw_args = None

    async def fetch(self, sql, *args):
        self.saw_args = args
        if self.raise_exc:
            raise RuntimeError("boom")
        return self.rows


def _row(ticker="ABCD", scan_date=date(2026, 9, 10), acted="strong", raw="game_changer",
         gap_pct=12.0, ep_score=65.0, ep_bar=70.0, score_side="separation",
         acted_catalyst_quality=None, breakdown=None):
    """A minimal, valid pre-joined row: `strong` acted (15 raw catalyst points), would have
    scored `game_changer` (25 raw points + the branch-4 conviction floor at gap>=10, which
    together push a 65.0 acted score to a 90.0 counterfactual — exact numbers chosen so the
    test asserts round figures, not floating-point near-misses)."""
    return {
        "scan_date": scan_date, "ticker": ticker,
        "live_quality_last": raw, "shadow_tier_last": acted,
        "gap_pct": gap_pct, "ep_score": ep_score, "ep_bar": ep_bar,
        "score_side": score_side,
        "acted_catalyst_quality": acted_catalyst_quality
        if acted_catalyst_quality is not None else acted,
        "score_breakdown": breakdown if breakdown is not None else {
            "gap": 15, "liquidity": 10, "catalyst": 15, "float": 0,
            "vol_conviction": 0, "theme_bonus": 0},
    }


@pytest.mark.asyncio
async def test_empty_window_short_circuits_without_a_query():
    """MUTATION PROVEN: disabling the `if not window_days:` early return made the fake conn's
    canned `rows=[{"should": "never be reached"}]` flow through the recompute instead
    (`uncountable` came back 1, not 0 — the row is missing every score field the guard
    normally never lets it reach) and set `saw_args`, both failing; restored before commit."""
    conn = _PrevConn(rows=[{"should": "never be reached"}])
    out = await hc._lattice_prevented_alerts(conn, [])
    assert out == {"prevented": [], "caused": [], "uncountable": 0}
    assert conn.saw_args is None


@pytest.mark.asyncio
async def test_query_failure_is_uncountable_None_never_zero():
    """MUTATION PROVEN: changing `except Exception` to swallow-and-return-{} silently would
    make `uncountable` come back 0 instead of None — the caller (accounts_for_shortfall) would
    then read 0 named preventions and 0 uncountable, indistinguishable from 'genuinely
    checked, found nothing' instead of 'the check itself failed'. Confirmed by hand: with the
    real except-block temporarily replaced by `return out` (the pre-declared zero dict), this
    test's `is None` assertion fails; restored before commit."""
    conn = _PrevConn(raise_exc=True)
    out = await hc._lattice_prevented_alerts(conn, [date(2026, 9, 10)])
    assert out["prevented"] == [] and out["caused"] == []
    assert out["uncountable"] is None


@pytest.mark.asyncio
async def test_a_real_demotion_reconstructs_to_a_named_prevented_alert():
    """The core recompute, end to end: `strong` acted at 65.0 (below the 70.0 bar); the raw
    `game_changer` grade — 10 more raw catalyst points AND the branch-4 conviction floor
    (gap>=10 + game_changer -> floor 60) it would additionally have cleared — reconstructs to
    a 90.0 counterfactual, which clears the bar. MUTATION PROVEN: temporarily dropping the
    `resolve_conviction_floor` re-application (`_raw_for` returning `before_floor` unconditionally)
    changes the counterfactual to 25(other)+25(game_changer)=50 raw -> presented 77.5 instead of
    90.0 — this test's `counterfactual_score == 90.0` assertion failed on exactly that value
    (`77.5 == 90.0`); restored before commit. The bar=80 test below isolates the SAME mutation
    with a bar chosen so a dropped floor also flips prevented/not-prevented, not just the number."""
    conn = _PrevConn(rows=[_row()])
    out = await hc._lattice_prevented_alerts(conn, [date(2026, 9, 10)])
    assert out["uncountable"] == 0 and out["caused"] == []
    assert len(out["prevented"]) == 1
    p = out["prevented"][0]
    assert p["ticker"] == "ABCD" and p["scan_date"] == "2026-09-10"
    assert p["acted_score"] == 65.0 and p["counterfactual_score"] == 90.0
    assert p["ep_bar"] == 70.0 and p["acted_grade"] == "strong" and p["raw_grade"] == "game_changer"


@pytest.mark.asyncio
async def test_the_conviction_floor_is_re_applied_for_the_counterfactual_grade():
    """Isolates the floor specifically: WITHOUT the branch-4 floor (gap>=10 + game_changer ->
    60), the counterfactual raw would be other_sum(25) + game_changer(25) = 50 -> presented
    1.25*50+15 = 77.5, still clearing an 80 bar by luck only if rounding cooperates — pick a
    bar of 80 so a dropped floor (77.5 < 80) reads as NOT prevented while the correct
    floor-applied counterfactual (60 -> 90.0) clears it. This is the assertion that actually
    distinguishes 'floor re-applied' from 'floor dropped', unlike the 70-bar case above."""
    row = _row(ep_score=65.0, ep_bar=80.0,
               breakdown={"gap": 10, "liquidity": 10, "catalyst": 15, "float": 0,
                         "vol_conviction": 0, "theme_bonus": 5})
    # other_raw_sum = 10+10+0+0+5 = 25; raw_acted = 25+15(strong) = 40 -> presented 65.0
    # (matches ep_score, i.e. regime_mult backs out to 1.0); raw_other before floor =
    # 25+25(game_changer) = 50 -> floor(gap=12>=10, game_changer) = 60 -> raw_other = 60 ->
    # presented 1.25*60+15 = 90.0, clearing bar 80. Without the floor it would be 77.5 (does
    # NOT clear 80) -> this row would wrongly land in neither bucket.
    conn = _PrevConn(rows=[row])
    out = await hc._lattice_prevented_alerts(conn, [date(2026, 9, 10)])
    assert len(out["prevented"]) == 1
    assert out["prevented"][0]["counterfactual_score"] == 90.0


@pytest.mark.asyncio
async def test_a_promotion_that_crosses_the_bar_is_CAUSED_not_prevented():
    """The reverse direction: the lattice PROMOTED (acted='game_changer', raw='strong') and
    that promotion is what cleared the bar — the fact-check CAUSED this alert, matching the
    operator's own manual finding ("CAUSED 0" on 2026-09-15, i.e. the category exists and
    should read zero when nothing was caused — here we force a nonzero case to prove the
    branch is live, not merely unreached). MUTATION PROVEN: this row shares the same
    conviction-floor dependency as the demotion test above (acted='game_changer' at gap=12
    only clears the 60-floor because of it) — dropping the floor re-application made this
    test fail alongside the other two in the same batch run (`len(out["caused"]) == 1` ->
    `0 == 1`, acted_score never reconstructing to 90.0); restored before commit."""
    row = _row(acted="game_changer", raw="strong", ep_score=90.0, ep_bar=70.0,
               breakdown={"gap": 15, "liquidity": 10, "catalyst": 25, "float": 0,
                         "vol_conviction": 0, "theme_bonus": 0})
    # acted raw = 25(other)+25(game_changer)=50, floor(gap12>=10,game_changer)=60 -> raw=60
    # -> presented 90.0 (matches ep_score, regime_mult=1.0). counterfactual (strong): raw =
    # 25+15=40 (no floor, catalyst != game_changer) -> presented 65.0, below bar 70.
    conn = _PrevConn(rows=[row])
    out = await hc._lattice_prevented_alerts(conn, [date(2026, 9, 10)])
    assert out["prevented"] == []
    assert len(out["caused"]) == 1
    c = out["caused"][0]
    assert c["acted_score"] == 90.0 and c["counterfactual_score"] == 65.0


@pytest.mark.asyncio
async def test_attribution_requires_the_scan_log_row_to_match_the_lattice_verdict():
    """GUARD ADDED ON ADVISOR REVIEW (2026-09-19): a row whose LAST scan_log tick scored
    something OTHER than the lattice's own verdict (an M&A / sector-momentum / downgrade-
    marker override applied AFTER the lattice) must never be pinned on the fact-check — even
    though its score numbers alone would classify as 'prevented'. MUTATION PROVEN: dropping
    the `r.get("acted_catalyst_quality") != acted_cq` clause from the guard made this row
    reconstruct and land in `prevented` (`out["prevented"] == []` failed, one item present);
    restored before commit."""
    row = _row(acted_catalyst_quality="routine")   # scan_log's actual acted grade disagrees
    conn = _PrevConn(rows=[row])
    out = await hc._lattice_prevented_alerts(conn, [date(2026, 9, 10)])
    assert out["prevented"] == [] and out["caused"] == []
    assert out["uncountable"] == 1


@pytest.mark.asyncio
async def test_legacy_score_side_is_uncountable_not_reconstructed():
    """The legacy rubric's catalyst points and conviction floor differ from SCORE_WEIGHTS —
    never guessed at here. MUTATION PROVEN: dropping `r.get("score_side") != "separation"`
    from the guard made this row reconstruct and land in `prevented` (`out["prevented"] == []`
    failed); restored before commit."""
    row = _row(score_side="legacy")
    conn = _PrevConn(rows=[row])
    out = await hc._lattice_prevented_alerts(conn, [date(2026, 9, 10)])
    assert out["prevented"] == [] and out["caused"] == [] and out["uncountable"] == 1


@pytest.mark.asyncio
async def test_missing_breakdown_is_uncountable_not_a_crash():
    """NOT mutation-discriminating for the `not breakdown` guard clause specifically —
    verified by hand: dropping that clause still passes this test, because a `None` breakdown
    then reaches `breakdown.items()`, raises `AttributeError`, and lands in the SAME
    `uncountable += 1` bucket via the outer `except Exception` instead. What this test
    actually proves is the outcome (no crash, correctly bucketed) is stable either way — not
    that the explicit guard is what produces it. Recorded honestly rather than claimed as
    RED-proven for that clause."""
    row = _row(breakdown=None)
    row["score_breakdown"] = None
    conn = _PrevConn(rows=[row])
    out = await hc._lattice_prevented_alerts(conn, [date(2026, 9, 10)])
    assert out["uncountable"] == 1 and out["prevented"] == [] and out["caused"] == []


@pytest.mark.asyncio
async def test_two_rows_mixed_countable_and_not_are_bucketed_independently():
    good = _row(ticker="GOOD")
    bad = _row(ticker="BAD", score_side="legacy")
    conn = _PrevConn(rows=[good, bad])
    out = await hc._lattice_prevented_alerts(conn, [date(2026, 9, 10)])
    assert [p["ticker"] for p in out["prevented"]] == ["GOOD"]
    assert out["uncountable"] == 1
