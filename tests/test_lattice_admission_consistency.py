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

# Finding 4 cleanup (2026-08-2x): three entries below matched ZERO lines of the scanned
# source, verified empirically (each line containing "llm_catalyst_quality" was checked
# against every entry; these never fired) — dead allowlist slack, not a live carve-out:
#   - the old "resolve input line" entry (`_resolve_acting_catalyst_quality\(`) never
#     matched: the resolve call's own line never ALSO contains "llm_catalyst_quality"
#     (it's on the next physical line, as the args); any line it might have covered was
#     already covered by the "resolve/kill-row args" entry below.
#   - the old "(defensive; unused)" entry was self-labelled dead on arrival.
#   - the old "both-sides record" entry (`"live_quality": llm_catalyst_quality,`) died
#     as a SIDE EFFECT of the Finding 3 cleanup in this same pass: that dict-literal key
#     moved out of run_ep_scan's own source into the new `_tier_shadow_base` builder, so
#     it's no longer a line this function's source contains at all.
# ⚠ Interaction with Finding 1: `^\s*llm_catalyst_quality = ` (kept, "maintenance") would
# ALSO pass a bare raw-grade mutation that never re-resolves — this allowlist only says
# "this is a legitimate RAW-grade write, not a second read path"; it says nothing about
# whether a re-resolve follows. That is what `test_every_mutation_is_followed_by_a_resolve`
# (below) enforces — the two tests are deliberately layered, not redundant.
_ALLOWED_RAW_USE = (
    re.compile(r"^\s*llm_catalyst_quality = "),                      # maintenance
    re.compile(r"^\s*ticker, llm_catalyst_quality, "),               # resolve/kill-row args
    re.compile(r"^\s*catalyst_quality=llm_catalyst_quality,?\s*(#.*)?$"),  # cache stores RAW
    re.compile(r"^\s*llm_catalyst_quality, confidence_multiplier"),  # CachedGrade stores RAW
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
    """SECONDARY TRIPWIRE ONLY (2026-08-2x) — NOT the invariant. This used to be the
    only guard, and it was backwards: adding a 6th raw-grade mutation WITH its correct
    resolve turns this number 5→6 (the "fix" was bumping the magic number — pure
    status theatre), while adding a 6th mutation and FORGETTING the resolve leaves the
    count at 5 and this test green. `test_every_mutation_is_followed_by_a_resolve`
    below is the actual invariant — it enforces the pairing, not a headcount, so it
    stays green at 5 sites or 6 as long as every mutation is paired. This assert stays
    only as a "the shape changed, go read the invariant test" flag for a human skimming
    a diff.

    5 resolve sites today: cached settle, fresh settle, post-earnings-boost,
    post-revenue-gate-downgrade, plus the FINAL resolve (covers the #72 prose downgrade,
    which has no resolve of its own)."""
    src = "\n".join(_scan_lines())
    assert src.count("_resolve_acting_catalyst_quality(") == 5, (
        "resolve call count changed from 5 — not a failure by itself: go re-read "
        "test_every_mutation_is_followed_by_a_resolve and, if this is a genuine new "
        "mutation site with its own correct resolve, update both that test's "
        "expectations and this number together")


# ── 6. THE INVARIANT: every raw-grade mutation is followed by a re-resolve ─────────
#
# These regexes classify SOURCE SHAPE (is this line a raw-grade write, and what kind)
# — a SEPARATE question from whether a resolve follows, which the test below answers
# by walking forward from each mutation. A line can be a well-formed mutation here and
# still be an unresolved fork below; the two checks are deliberately layered.
_LLM_MUTATION_RE = re.compile(r"^\s*llm_catalyst_quality\s=\s(?!=)")
_BARE_CQ_ASSIGN_RE = re.compile(r"^\s*catalyst_quality(,\s*\w+)?\s=\s(?!=)")
_RESOLVE_CALL_RE = re.compile(r"_resolve_acting_catalyst_quality\(")
_KWARG_KEY_RE = re.compile(r"(?<!llm_)\bcatalyst_quality=")  # dict/call keyword name, not a read

# The bare `catalyst_quality = ` (or `catalyst_quality, x = `) assignments that are NOT
# the resolve's own tuple-unpack (structurally excluded — that line has TWO extra
# comma-targets, `_lattice_verdict, _live_side`, and this regex allows at most one) and
# are NOT paired with an immediately-preceding `llm_catalyst_quality = ` mutation of the
# same value. Each one here establishes the RAW grade for the FIRST TIME in its branch —
# cached-path raw read, fresh-path init, enriched-corpus result, legacy-classify result,
# pplx-hedge downgrade — all BEFORE that branch's own first resolve has run, so there is
# no already-resolved acting grade yet to protect. A new entry here is a real claim
# ("this too runs pre-first-resolve") a reviewer should see named, not infer from a
# blanket exemption.
_PROLOGUE_RAW_ESTABLISH = (
    re.compile(r"^\s*catalyst_quality = cached\.catalyst_quality$"),
    re.compile(r"^\s*catalyst_quality = None$"),
    re.compile(r"^\s*catalyst_quality, claude_analysis = _eq, _ea$"),
    re.compile(r"^\s*catalyst_quality, claude_analysis = await claude_task$"),
    re.compile(r"^\s*catalyst_quality = downgraded$"),
)


def _strip_non_reads(line: str) -> str:
    """A `catalyst_quality` substring that is a kwarg/dict KEY (`catalyst_quality=`, no
    space — e.g. the cache-write `catalyst_quality=llm_catalyst_quality,`) or the LHS of
    a bare assignment (`catalyst_quality = ` — the WRITE itself) is not a READ. Strip
    both; anything left over is a genuine read — including the VALUE half of a kwarg
    like `catalyst_quality=catalyst_quality,` (the _score_ep call site): the key gets
    stripped, the value stays and still counts."""
    s = _KWARG_KEY_RE.sub("", line)
    s = _BARE_CQ_ASSIGN_RE.sub("", s, count=1)
    return s


def _line_reads_catalyst_quality(line: str) -> bool:
    if re.match(r"^\s*#", line):
        return False
    return bool(re.search(r"\bcatalyst_quality\b", _strip_non_reads(line)))


def test_every_mutation_is_followed_by_a_resolve():
    """THE INVARIANT (Finding 1, 2026-08-2x — replaces the count-only guard above,
    which was backwards: see its docstring).

    What this enforces: every mutation of the raw grade inside run_ep_scan is followed
    by a re-resolve before the next read of catalyst_quality. Concretely: every line
    that assigns `llm_catalyst_quality` must be followed, before any later line reads
    `catalyst_quality`, by a `_resolve_acting_catalyst_quality(` call. Every bare
    `catalyst_quality = ` assignment must be either the resolve's own tuple-unpack,
    paired with an immediately-preceding `llm_catalyst_quality` mutation of the same
    value (which then owes rule 1 its resolve), or named on `_PROLOGUE_RAW_ESTABLISH`
    (establishing the raw grade for the first time in its branch — nothing "acting"
    exists yet to protect).

    What a future editor IS allowed to do and still see this GREEN: add a 6th mutation
    of `llm_catalyst_quality` immediately followed (before any read) by its OWN
    `_resolve_acting_catalyst_quality(` call — the exact shape of the 5 sites here
    today.

    What turns this RED: add a mutation with no following resolve; add a bare
    `catalyst_quality = ` write that is neither paired nor named on the prologue list;
    or let anything read `catalyst_quality` between a mutation and its resolve.

    Interaction with `_ALLOWED_RAW_USE` above (`test_every_raw_grade_use_...`):
    `^\\s*llm_catalyst_quality = ` there only certifies "this is a legitimate RAW-grade
    WRITE, not a second READ path" — it says nothing about whether a resolve follows.
    THIS test is what catches a bare mutation with no resolve that the other allowlist
    would otherwise let through clean."""
    lines = _scan_lines()
    # Longest real gap today is 52 lines (revenue-gate downgrade -> its own resolve, via
    # the audit-log + cache-write block in between); generous margin above that, not a
    # per-site knob.
    window_ceiling = 70

    for i, ln in enumerate(lines):
        if _LLM_MUTATION_RE.search(ln):
            resolved = False
            for j in range(i + 1, min(i + 1 + window_ceiling, len(lines))):
                nxt = lines[j]
                if _RESOLVE_CALL_RE.search(nxt):
                    resolved = True
                    break
                assert not _line_reads_catalyst_quality(nxt), (
                    f"line {i} mutates the raw grade (`{ln.strip()}`) but line {j} "
                    f"reads catalyst_quality before any resolve call: `{nxt.strip()}`")
            assert resolved, (
                f"line {i} mutates the raw grade (`{ln.strip()}`) with no "
                f"_resolve_acting_catalyst_quality( call within {window_ceiling} lines")
        elif _BARE_CQ_ASSIGN_RE.search(ln) and not _RESOLVE_CALL_RE.search(ln):
            prev = lines[i - 1] if i > 0 else ""
            paired = bool(_LLM_MUTATION_RE.search(prev)) and (
                prev.split("=", 1)[1].strip() == ln.split("=", 1)[1].strip())
            prologue = any(rx.search(ln) for rx in _PROLOGUE_RAW_ESTABLISH)
            assert paired or prologue, (
                f"line {i} mutates catalyst_quality alone (`{ln.strip()}`) — pair it "
                "with an llm_catalyst_quality mutation on the line directly above (which "
                "then owes a resolve per rule 1), or add it, named, to "
                "_PROLOGUE_RAW_ESTABLISH with a reason it runs before any resolve")


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
