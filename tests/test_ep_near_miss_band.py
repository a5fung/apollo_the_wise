"""#533 follow-on (2026-08-22) — the near-miss band is back, VISIBILITY ONLY.

Operator: "we don't need separate alerts but we have a section for close but misses, or
moderates, can we put them there? I want them recorded in case we miss real EPs there."

The #533 rescale (2026-08-22) removed the briefing's MODERATE band on the separation side
(`ep_rubric.resolve_moderate_cutline` returns None while the flag is ON) — anything scoring
presented < 65 became a completely silent skip. This restores a presented [50, 65) band as a
RECORD in the morning briefing's existing EP ALERTS section, sourced entirely from
`mi_ep_scan_log` skip rows `ep_detector.py` already writes (never new storage, never a new
Telegram surface).

⚠ THE TRAP this file exists to close (flagged in the #533 rescale change-log entry itself):
re-arming a MODERATE band on the presented scale also re-arms the earnings-day
MODERATE→HIGH override (`ep_detector.py`, ~line 4341) on names that today skip silently. This
suite proves that CANNOT happen: the near-miss population is sourced from rows where
`score_tier` is NULL — and by construction (`resolve_moderate_cutline(True) is None`), a
presented score in [50, 65) NEVER gets `tier = "MODERATE"` assigned while separation is live,
so the earnings-override's `if tier == "MODERATE"` guard is unreachable for it. Nothing here
touches scoring, tiering, the entry pipeline, or the allocator — pure display of an
already-decided, already-terminal skip.
"""
from __future__ import annotations

import inspect
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from agents.market_intelligence import briefing, ep_detector
from agents.market_intelligence.ep_detector import _score_ep
from agents.market_intelligence.ep_rubric import (
    SCORE_WEIGHTS, SEPARATION_BAR, LEGACY_MODERATE_CUTLINE,
    resolve_ep_bar, resolve_moderate_cutline,
)


# ── Part A: the near-miss band can NEVER become MODERATE/HIGH (the promotion proof) ────


def test_no_moderate_band_while_separation_is_live():
    """Baseline the trap rests on: unchanged since the rescale, re-asserted here so a
    future edit to ep_rubric can't silently re-open the earnings-override door."""
    assert resolve_moderate_cutline(True) is None
    assert resolve_moderate_cutline(False) == LEGACY_MODERATE_CUTLINE == 50


def test_near_miss_band_scores_always_hit_the_skip_continue_not_moderate():
    """The exact boolean run_ep_scan evaluates (`ep_score < ep_threshold and
    (_mod_cut is None or ep_score < _mod_cut)`), using the REAL resolve_* functions —
    for every score in the near-miss band [50, 65), with separation live (_mod_cut=None),
    this is always True, i.e. `continue` fires and `tier = ... "MODERATE"` (the line right
    after the skip block) is never reached for these candidates, regardless of gap size or
    earnings-day status — the override lives further downstream and needs tier=='MODERATE'."""
    ep_threshold = resolve_ep_bar(True, regime_ep_threshold=65)  # separation bar, presented
    mod_cut = resolve_moderate_cutline(True)
    assert ep_threshold == SEPARATION_BAR == 65
    assert mod_cut is None
    for presented_score in (50.0, 52.5, 58.0, 63.0, 64.9):
        would_continue = ep_threshold_gate = (
            presented_score < ep_threshold and (mod_cut is None or presented_score < mod_cut)
        )
        assert would_continue, (
            f"score {presented_score} in the near-miss band must still hit the "
            f"skip-continue — it must never reach `tier = ... MODERATE`"
        )


def test_a_real_score_ep_output_in_the_near_miss_band_with_earnings_shape_stays_skipped():
    """End-to-end through the REAL scorer (never a reimplementation): a gap >= 10% +
    game_changer candidate — the exact shape (`gap_pct >= 10.0`) the earnings-day override
    checks for — that happens to land in the near-miss band on the separation side must
    still resolve to `tier=None` (skip), because the HIGH/skip decision happens BEFORE the
    override ever runs. Earnings-day status is irrelevant here by construction: the override
    branch is unreachable when tier is never set to MODERATE for this score."""
    # A routine/strong-ish shape that presents inside [50, 65) on the live rubric.
    presented, breakdown = _score_ep(
        gap_pct=10.5, rel_volume=1.8, catalyst_quality="strong", profile={},
        regime_multiplier=1.0, adv_dollar=120_000_000, weights=SCORE_WEIGHTS,
    )
    assert LEGACY_MODERATE_CUTLINE <= presented < SEPARATION_BAR, (
        f"fixture drifted off the near-miss band (presented={presented}); "
        f"adjust the fixture inputs, not the band constants"
    )
    ep_threshold = SEPARATION_BAR
    mod_cut = resolve_moderate_cutline(True)
    # This IS the run_ep_scan skip condition, evaluated on the real scorer's output.
    assert presented < ep_threshold and (mod_cut is None or presented < mod_cut), (
        "a real near-miss score must hit the skip-continue before tier assignment — "
        "gap>=10% (the override's own trigger condition) changes nothing here"
    )


# ── Part B: source-inspection pins (test_347/test_533/test_570 pattern) ────────────────


def _scan_src() -> str:
    return inspect.getsource(ep_detector.run_ep_scan)


def test_skip_continue_precedes_tier_assignment_precedes_earnings_override():
    """Structural ordering pin: the skip-continue block, the tier assignment, and the
    earnings-day override must appear in exactly this order in run_ep_scan's source — a
    refactor that reorders them could re-open the trap silently."""
    src = _scan_src()
    skip_idx = src.index(
        "if ep_score < ep_threshold and (_mod_cut is None or ep_score < _mod_cut):"
    )
    tier_idx = src.index('tier = "HIGH" if ep_score >= ep_threshold else "MODERATE"')
    override_idx = src.index('if tier == "MODERATE" and c["gap_pct"] >= 10.0:')
    assert skip_idx < tier_idx < override_idx, (
        "skip-continue must run BEFORE tier assignment, which must run BEFORE the "
        "earnings-day override — reordering this is exactly the trap"
    )
    # The skip block must actually `continue` (not just log) — otherwise scored-but-
    # skipped candidates would fall through into tier assignment anyway.
    between = src[skip_idx:tier_idx]
    assert "continue" in between


def test_earnings_override_still_only_guards_on_tier_moderate():
    """Unchanged precondition: the override is gated on `tier == "MODERATE"` — this file's
    entire promotion-proof rests on that population being reachable ONLY via the legacy
    (flag OFF) side for scores in the near-miss window, never the separation side."""
    src = _scan_src()
    assert 'if tier == "MODERATE" and c["gap_pct"] >= 10.0:' in src


def test_is_earnings_day_call_lives_inside_the_moderate_guard_not_before_it():
    """Matches the operator's literal ask ('a test that a near-miss name with an earnings-
    day flag does NOT get promoted') as a textual containment pin: the `is_earnings_day`
    lookup that could promote a candidate is called ONLY inside the `if tier == "MODERATE"`
    block, never before it / never unconditionally — so a near-miss candidate (which never
    gets tier == "MODERATE" while separation is live, per the boundary sweep above) never
    triggers the earnings-day lookup at all, let alone a promotion."""
    src = _scan_src()
    guard_idx = src.index('if tier == "MODERATE" and c["gap_pct"] >= 10.0:')
    # End of that if-block: the next top-level statement at the same indentation
    # ("# Theme-gated ADVISORY grade" comment marks the next section).
    block_end_idx = src.index("# Theme-gated ADVISORY grade", guard_idx)
    call_idx = src.index("await is_earnings_day(ticker, today)", guard_idx)
    assert guard_idx < call_idx < block_end_idx, (
        "is_earnings_day must be called ONLY inside the tier=='MODERATE' guard — a near-miss "
        "candidate (tier never MODERATE while separation is live) never reaches this call"
    )


# ── Part C: the briefing surface — visibility, correct scope, no double-count ──────────


def _row(ticker, ep_score, score_tier=None, gap_pct=12.0,
         catalyst_quality="strong", filter_reason=None):
    return {
        "ticker": ticker, "ep_score": ep_score, "score_tier": score_tier,
        "gap_pct": gap_pct, "catalyst_quality": catalyst_quality,
        "filter_reason": filter_reason or f"score {int(ep_score)} < bar 65 (catalyst={catalyst_quality})",
    }


def test_near_miss_band_renders_with_score_and_catalyst():
    scan_log = [_row("NMS1", 52.5), _row("NMS2", 63.0, catalyst_quality="routine")]
    out = briefing._format_ep_section([], section_num=1, scan_log=scan_log)
    assert "Near-miss (50-65, recorded only — not tradeable)" in out
    assert "`NMS1` score 52  gap 12.0%  strong" in out
    assert "`NMS2` score 63  gap 12.0%  routine" in out
    assert "2 near-miss" in out


def test_near_miss_band_excludes_scores_below_50():
    scan_log = [_row("TOOLOW", 30.0, filter_reason="score 30 < bar 65 (catalyst=routine)")]
    out = briefing._format_ep_section([], section_num=1, scan_log=scan_log)
    assert "Near-miss" not in out
    assert "TOOLOW" in out  # still visible via the pre-existing generic near-misses line


def test_near_miss_band_excludes_the_bar_itself_and_above():
    """Upper bound is exclusive — a score_tier=None row with ep_score>=65 should not occur
    structurally (>=65 always becomes tier=HIGH), but the filter must not include it if it
    somehow does (malformed/legacy data)."""
    scan_log = [_row("ATBAR", 65.0, filter_reason="score 65 < bar 65 (catalyst=strong)")]
    out = briefing._format_ep_section([], section_num=1, scan_log=scan_log)
    assert "Near-miss" not in out


def test_near_miss_band_excludes_real_moderate_and_high_rows():
    """A row that actually alerted (score_tier populated — the legacy side's real MODERATE,
    or a HIGH) must never be double-counted into the near-miss band; it is already recorded
    as a real alert elsewhere. This is the guard that keeps the legacy revert side's real
    MODERATE band from colliding with this display-only surface."""
    scan_log = [
        _row("LEGACYMOD", 58.0, score_tier="MODERATE"),
        _row("SOMEHIGH", 90.0, score_tier="HIGH"),
    ]
    out = briefing._format_ep_section([], section_num=1, scan_log=scan_log)
    assert "Near-miss" not in out


def test_near_miss_ticker_not_duplicated_in_generic_near_misses_line():
    scan_log = [_row("NMS1", 52.5), _row("OTHER", 30.0, filter_reason="cooldown active")]
    out = briefing._format_ep_section([], section_num=1, scan_log=scan_log)
    assert out.count("NMS1") == 1  # only in the dedicated near-miss block
    assert "OTHER" in out  # still shown in the generic catch-all line


def test_near_miss_band_caps_with_overflow_note():
    scan_log = [_row(f"NM{i}", 55.0) for i in range(15)]
    out = briefing._format_ep_section([], section_num=1, scan_log=scan_log)
    assert "…3 more" in out
    assert "15 near-miss" in out  # header count is the TRUE total, not the rendered cap


def test_near_miss_band_never_touches_the_score_tier_field():
    """Purely a display filter — asserts the function reads score_tier (via .get, never
    subscript/attribute assignment) and never writes it back onto any row."""
    src = inspect.getsource(briefing._format_ep_section)
    assert 'r.get("score_tier")' in src, "must read score_tier via .get, not assume it exists"
    # No assignment INTO any dict's score_tier key, in any of the forms that would mutate
    # a row: subscript assignment, dict literal construction, or .update(...).
    forbidden = ['"score_tier"] =', "'score_tier'] =", '"score_tier": ', "'score_tier':"]
    for pattern in forbidden:
        assert pattern not in src, f"found a score_tier WRITE pattern: {pattern!r}"
