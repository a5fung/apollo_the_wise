"""ONE GRADE EVERYWHERE — the 2026-08-22 catalyst-grade consistency fix, pinned.

Operator (2026-08-22, verbatim): "why you think it's ok that we change grading that
it's ok to have places to use old grading, if we change something we change it
everywhere, consistency at all times, no forks."

THE BUG THIS FIXES: `_post_grade_filters`'s routine-gap<12 check read the RAW LLM
grade while `_score_ep` read the corrected lattice verdict (`catalyst_tier_lattice`
flip, same day). The typical labelled real EP gaps ~10% and the news grader is
measured backwards (4 of the 7 graded labelled real EPs came out `routine`), so a
real EP wrongly graded routine was binned at admission BEFORE the correction built to
save it could act. MRNA 2026-08-19 itself scored at gap 10.0 graded `strong` — one
grade notch from dying in that filter.

WHAT IS PINNED HERE:

1. BEHAVIOUR — the resolve helper + the filters, driven with the REAL lattice
   (deterministic, $0, no DB):
   - toggle ON: a routine raw grade whose analysis shows the rule-4 demotion fired
     AND a concrete company event (the corrective) resolves to `strong` and SURVIVES
     the routine-gap<12 filter at gap 10; a routine that stays routine still dies.
   - toggle OFF: the raw grade acts everywhere — byte-identical pre-flip behaviour
     (the one revert flag; `tests/test_405_catalyst_cache_filters.py` pins the frozen
     raw-side filter semantics in full).
   - R6 pm-shares carve-out on the acting side accepts strong OR game_changer — a
     lattice PROMOTION must never strip a name of the bypass its old grade earned;
     the raw side keeps the historical strong-only carve-out exactly.
2. DIRECTION — the lattice never outputs `routine` for a non-routine input, so the
   acting-grade filter can only ADMIT MORE through the routine-gap<12 check than the
   raw-grade filter, never newly exclude (the P1 / must-not-miss direction).
3. SOURCE INVARIANT — no code path reads the raw grade once the lattice is acting:
   every use of `llm_catalyst_quality` inside `run_ep_scan` is on a small allowlist
   (its own maintenance, resolve input, cache write, both-sides record, re-poll
   raw-compare); `cached.catalyst_quality` is read exactly once (into the raw var);
   both `_post_grade_filters` call sites thread `lattice_acting`. Reintroducing a
   second grade path fails here by name.
"""
from __future__ import annotations

import inspect
import re
from datetime import date
from itertools import product
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence import ep_detector
from agents.market_intelligence.catalyst_tier_shadow import SHADOW_TIERS, shadow_retier

_TODAY = date(2026, 8, 22)

# Analysis text that trips the corrective: a rule-4 demotion marker ("sector-wide")
# plus a concrete company event ("contract"). Same vocabulary family the lattice's
# own regexes declare.
_CORRECTIVE_ANALYSIS = (
    "Gapping on a new $500M defense contract announced this morning; grader called "
    "the move sector-wide momentum with no company-specific catalyst priced."
)
# Routine-and-stays-routine text: no demotion marker, no concrete event.
_INERT_ANALYSIS = "Drifting higher; nothing notable."


def _no_mna():
    return patch.object(ep_detector, "is_likely_ma", AsyncMock(return_value=(False, None)))


def _resolve(quality, analysis, live):
    return ep_detector._resolve_acting_catalyst_quality(
        "TEST", quality, analysis, None, None, {}, live)


# ── 1. The resolve helper — the ONE derivation ──────────────────────────────────────

def test_corrective_promotes_routine_to_strong_when_lattice_live():
    acting, verdict, side = _resolve("routine", _CORRECTIVE_ANALYSIS, True)
    assert (acting, side) == ("strong", "lattice")
    assert verdict["rule"] == "routine_promoted_demotion_corrective"


def test_routine_without_evidence_stays_routine():
    acting, verdict, side = _resolve("routine", _INERT_ANALYSIS, True)
    assert (acting, side) == ("routine", "lattice")
    assert verdict["rule"] == "routine_unchanged"


def test_toggle_off_returns_the_raw_grade_for_every_tier():
    for q in SHADOW_TIERS:
        acting, _verdict, side = _resolve(q, _CORRECTIVE_ANALYSIS, False)
        assert (acting, side) == (q, "llm"), (
            f"toggle OFF must be byte-identical pre-flip: raw grade {q} acts")


def test_resolve_fails_open_to_the_raw_grade():
    with patch(
        "agents.market_intelligence.catalyst_tier_shadow.compute_shadow_verdict",
        side_effect=RuntimeError("boom"),
    ):
        acting, verdict, side = _resolve("routine", _CORRECTIVE_ANALYSIS, True)
    assert (acting, verdict, side) == ("routine", None, "llm")


# ── 2. The routine-gap<12 filter reads the acting grade (the MRNA-class pin) ────────

@pytest.mark.asyncio
async def test_promoted_routine_at_gap_10_survives_the_routine_filter():
    """THE GOAL: raw routine + corrective evidence + gap 10 → the name that used to be
    binned pre-score now clears admission and reaches the scorer."""
    acting, _v, side = _resolve("routine", _CORRECTIVE_ANALYSIS, True)
    with _no_mna():
        reason = await ep_detector._post_grade_filters(
            "TEST", acting, _CORRECTIVE_ANALYSIS, "news", 10.0, 500_000, None, _TODAY,
            lattice_acting=(side == "lattice"),
        )
    assert reason is None


@pytest.mark.asyncio
async def test_unpromoted_routine_at_gap_10_still_dies():
    acting, _v, side = _resolve("routine", _INERT_ANALYSIS, True)
    with _no_mna():
        reason = await ep_detector._post_grade_filters(
            "TEST", acting, _INERT_ANALYSIS, "news", 10.0, 500_000, None, _TODAY,
            lattice_acting=(side == "lattice"),
        )
    assert reason == "routine catalyst, gap 10.0%"


@pytest.mark.asyncio
async def test_toggle_off_kills_the_same_name_exactly_as_before():
    acting, _v, side = _resolve("routine", _CORRECTIVE_ANALYSIS, False)
    with _no_mna():
        reason = await ep_detector._post_grade_filters(
            "TEST", acting, _CORRECTIVE_ANALYSIS, "news", 10.0, 500_000, None, _TODAY,
            lattice_acting=(side == "lattice"),
        )
    assert reason == "routine catalyst, gap 10.0%"


# ── 3. R6 pm-shares carve-out: strong-or-better on the acting side only ─────────────

@pytest.mark.asyncio
async def test_r6_carveout_accepts_game_changer_on_the_acting_side():
    """A lattice promotion (strong → game_changer, the MRNA signature) must not strip
    the low-pm-shares bypass the name's old grade earned."""
    with _no_mna():
        reason = await ep_detector._post_grade_filters(
            "TEST", "game_changer", "analysis", "news", 12.5, 10_000, 1.0, _TODAY,
            lattice_acting=True,
        )
    assert reason is None


@pytest.mark.asyncio
async def test_r6_carveout_still_rejects_game_changer_on_the_raw_side():
    """Toggle OFF is byte-identical pre-flip: the historical carve-out was strong-ONLY."""
    with _no_mna():
        reason = await ep_detector._post_grade_filters(
            "TEST", "game_changer", "analysis", "news", 12.5, 10_000, 1.0, _TODAY,
            lattice_acting=False,
        )
    assert reason == "pre-mkt volume 10,000 < 25,000 shares"


# ── 4. Direction: the fix can only ADMIT more, never newly exclude ──────────────────

def test_lattice_never_demotes_any_grade_to_routine():
    """For every reachable input, `routine` out ⟹ `routine` in — so reading the
    acting grade in the routine-gap<12 filter is monotonic in the admit direction
    (P1: a false exclusion is invisible; this change must never create one)."""
    for live, sched, combined, beat, marker, event, sector in product(
        SHADOW_TIERS, ("scheduled", "unscheduled", "unknown"),
        ("forward", "backward", "none"), (True, False), (True, False),
        (True, False), (True, False),
    ):
        tier, _rule = shadow_retier(live, sched, combined, beat, marker, event, sector)
        if tier == "routine":
            assert live == "routine", (
                f"lattice demoted {live} to routine on {(sched, combined, beat, marker, event, sector)}"
                " — the admission filter would newly exclude; forbidden direction")


def test_acting_strong_pool_is_a_superset_of_raw_strong_for_the_r6_carveout():
    """Raw `strong` is never demoted by the lattice, and the acting-side carve-out
    accepts strong OR game_changer — so no name that bypasses the pm-shares floor
    today can lose that bypass under the acting grade."""
    for sched, combined, beat, marker, event, sector in product(
        ("scheduled", "unscheduled", "unknown"), ("forward", "backward", "none"),
        (True, False), (True, False), (True, False), (True, False),
    ):
        tier, _rule = shadow_retier("strong", sched, combined, beat, marker, event, sector)
        assert tier in ("strong", "game_changer")


# ── 5. Source invariant: no second grade path ───────────────────────────────────────

_ALLOWED_RAW_USE = (
    re.compile(r"^\s*llm_catalyst_quality = "),                      # maintenance
    re.compile(r"_resolve_acting_catalyst_quality\("),               # resolve input line
    re.compile(r"^\s*ticker, llm_catalyst_quality, "),               # resolve/kill-row args
    re.compile(r'^\s*"TEST", llm_catalyst_quality'),                 # (defensive; unused)
    re.compile(r"^\s*catalyst_quality=llm_catalyst_quality,?\s*(#.*)?$"),  # cache stores RAW
    re.compile(r"^\s*llm_catalyst_quality, confidence_multiplier"),  # CachedGrade stores RAW
    re.compile(r'^\s*"live_quality": llm_catalyst_quality,'),        # both-sides record
    re.compile(r"^\s*_rq != llm_catalyst_quality"),                  # re-poll raw-compare
    re.compile(r"^\s*#"),                                            # comments
)


def _scan_lines():
    return inspect.getsource(ep_detector.run_ep_scan).splitlines()


def test_every_raw_grade_use_in_run_ep_scan_is_allowlisted():
    """A NEW read of the raw grade (e.g. `if llm_catalyst_quality == ...`) is a second
    grade path — the fork the operator forbade — and fails here by line."""
    offenders = [
        ln for ln in _scan_lines()
        if "llm_catalyst_quality" in ln
        and not any(rx.search(ln) for rx in _ALLOWED_RAW_USE)
    ]
    assert not offenders, (
        "raw-grade reads outside the allowlist (one grade everywhere — no forks):\n"
        + "\n".join(offenders))


def test_cached_raw_grade_is_read_exactly_once_into_the_raw_var():
    lines = [ln for ln in _scan_lines() if "cached.catalyst_quality" in ln]
    assert lines == ["            catalyst_quality = cached.catalyst_quality"], (
        "the cached RAW grade may be read once, into the pipeline var that the settle "
        f"resolve immediately converts to the acting grade — got: {lines}")


def test_both_filter_call_sites_thread_the_acting_side_marker():
    src = "\n".join(_scan_lines())
    assert src.count('lattice_acting=(_live_side == "lattice")') == 2, (
        "both _post_grade_filters call sites (cached re-check + fresh grade) must pass "
        "the acting-side marker")


def test_every_resolve_site_is_present():
    """4 resolve sites in run_ep_scan: cached settle, fresh settle, post-earnings-boost,
    post-revenue-gate (the prose downgrade is covered by the FINAL resolve directly
    below it), plus the FINAL resolve = 5. Adding a raw-grade mutation without a
    re-resolve (or removing one) changes this count — deliberate speed bump."""
    src = "\n".join(_scan_lines())
    assert src.count("_resolve_acting_catalyst_quality(") == 5


def test_filter_killed_graded_candidates_are_captured_for_the_tier_record():
    """The ARM-class evidence hole: graded names killed at admission used to leave no
    recorded text anywhere (why 4 of 7 routine-graded labelled real EPs were
    'undetermined offline' in the #533 shadow eval). Both kill sites must append a
    tier record row."""
    src = "\n".join(_scan_lines())
    assert src.count("_tier_kill_row(") == 2
    row = ep_detector._tier_kill_row(
        "TEST", "routine", {"shadow_tier": "strong"}, "lattice",
        "analysis", None, "news", {"gap_pct": 10.0, "adv": 1e6, "prev_close": 20.0}, 0.5)
    assert row is not None and row["ep_score"] is None and row["live_tier"] is None
    assert row["live_quality"] == "routine" and row["adv_dollar"] == 2e7
