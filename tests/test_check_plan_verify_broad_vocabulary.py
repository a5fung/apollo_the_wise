"""STRICT vs BROAD verify-claim vocabulary (operator 2026-08-09, same day as both verify gates).

Background: `_pending_verify_gate` (HARD-FAIL on a touched line) and `_deployed_no_verify_gate`
(WARN-only) share ONE trigger-vocabulary definition point but were found to need DIFFERENT error
profiles. A false fire on gate 1 blocks real work, so precision wins there — it keeps
`_VERIFY_CLAIM_TRIGGER_STRICT` untouched (today's 5 triggers: VERIFY-LIVE / VERIFY-DUE / "NOT done
until" / "must be confirmed" / "confirm in prod"), the exact vocabulary that already caught #471. A
MISS on gate 2 is the expensive error (a task that already states its check gets nagged forever), so
it uses the wider `_VERIFY_CLAIM_TRIGGER_BROAD` = STRICT plus phrasings measured against the live
board's real `deployed` tasks: bare "VERIFY <day-name>" / "VERIFY <YYYY-MM-DD>" (#544, #539) and
past-tense "VERIFIED IN PROD" (#525). "VERIFIED <date>" is also included for recall consistency
(real board idiom on OTHER deployed tasks — #356 "VERIFIED 8/04", #471 "VERIFIED 7/16", #306
"VERIFIED 7/9" — though none of those needed it to already clear STRICT some other way), even though
no board line among the 4 originally-firing tasks uses that exact form.

This file pins THREE things the ticket asked for directly, so a future edit that re-merges the two
vocabularies (or accidentally widens STRICT) fails loudly here rather than silently in the field:
  1. BROAD is a structural superset of STRICT (built by extending STRICT's own pattern string).
  2. Each new phrasing matches BROAD and does NOT match STRICT.
  3. Gate 1 (STRICT / `_pending_verify_matches`) is completely unchanged: run against the same
     frozen real-board corpus the sibling test files already pin, its verdicts are identical to
     what they were before this change (all the FROZEN_* snippets from both sibling test files,
     re-asserted here against STRICT directly).
"""
from __future__ import annotations

import scripts.check_plan as cp
from scripts.check_plan import (
    _VERIFY_CLAIM_TRIGGER_BROAD,
    _VERIFY_CLAIM_TRIGGER_STRICT,
    _pending_verify_matches,
    _verify_claim_raw_matches,
)

# ── 1. structural superset: BROAD is STRICT extended, not a hand-maintained parallel list ────────

def test_broad_pattern_is_built_by_literally_extending_strict():
    assert _VERIFY_CLAIM_TRIGGER_BROAD.pattern.startswith(_VERIFY_CLAIM_TRIGGER_STRICT.pattern + "|")


def test_broad_matches_everything_strict_matches_over_a_mixed_corpus():
    # implication over a real corpus, not just the pattern-string check above: for every string
    # here, STRICT-match -> BROAD-match. Covers frozen real-board snippets (both sibling test
    # files) plus generic negatives (neither should match) plus the #513 negative.
    corpus = [
        # positives (from tests/test_check_plan_pending_verify.py FROZEN_* set)
        "▶ **VERIFY-LIVE for the flip (this is what closes defect 2, not the deploy):** the next partial",
        "wired into the 15-min reconcile; card-built Fable-reviewed; VERIFY-LIVE Mon 7/6 = first "
        "reconcile cycles write coverage_drift audit rows, expect quiet",
        "▶ VERIFY-LIVE = tonight's 17:35 ET consolidation job writes the first `entry_mode='confirm'`",
        "VERIFY-LIVE checkpoints on the armed run: (1) `theme_dominant_split_eligible` audit event",
        "REMAINING = deploy (rides the next batch w/ T5) + verify-live = the hook logs on the next "
        "entry evaluation.",
        "✅ VERIFY-LIVE DONE 6/18 (deploy b8245ec, both): write-probe proved the insert path (insert✓ ",
        # negatives (generic prose that must never fire either vocabulary)
        "Opus-verified: setup NOT dead",
        "ETF% unverified — re-derive on clean data",
        "verified in git",
        "the promote path verified ALREADY-LIVE under v1",
        "operator confirms Rank Flow reads correctly on the live URL",
        "so no earlier date can verify it",   # #513's real phrase — a BROAD-only-must-not-catch case
        "still unverified in prod, do not close",   # regression: \b must stop "un-"+"verified in prod"
    ]
    for s in corpus:
        strict_hit = bool(_VERIFY_CLAIM_TRIGGER_STRICT.search(s))
        broad_hit = bool(_VERIFY_CLAIM_TRIGGER_BROAD.search(s))
        if strict_hit:
            assert broad_hit, f"STRICT matched but BROAD did not (superset broken): {s!r}"
        else:
            # none of these 8 negatives is a new-phrasing string, so BROAD must also stay silent —
            # makes the implication check non-vacuous on its negative half too.
            assert not broad_hit, f"BROAD false-fired on generic prose: {s!r}"


# ── 2. each new phrasing matches BROAD and does NOT match STRICT ─────────────────────────────────

NEW_PHRASINGS = [
    ("bare VERIFY + day-name (#544 'VERIFY MONDAY:')", "▶ **VERIFY MONDAY:** theme engine 17:00 ET run clean."),
    ("bare VERIFY + ISO date (#539 'VERIFY 2026-08-08')", "▶ VERIFY 2026-08-08 (Sat morning, on tonight's run): a check."),
    ("past-tense VERIFIED IN PROD (#525)", "**VERIFIED IN PROD RIGHT AFTER DEPLOY:** breaker[live]=0."),
    ("past-tense VERIFIED + ISO date (ticket-named, no firing board line)", "VERIFIED 2026-08-08: confirmed in prod."),
    ("past-tense VERIFIED + M/D date (real board idiom, e.g. #356/#471/#306)", "VERIFIED 8/04: reran clean."),
]


def test_new_phrasings_match_broad_but_not_strict():
    for label, phrase in NEW_PHRASINGS:
        assert not _VERIFY_CLAIM_TRIGGER_STRICT.search(phrase), f"{label}: must NOT match STRICT: {phrase!r}"
        assert _VERIFY_CLAIM_TRIGGER_BROAD.search(phrase), f"{label}: must match BROAD: {phrase!r}"


def test_new_phrasings_reach_verify_claim_raw_matches_the_gate2_primitive():
    # `_verify_claim_raw_matches` is what `_deployed_no_verify_violations` actually calls -> confirm
    # the new phrasings are visible through the real call path, not just the raw regex.
    for label, phrase in NEW_PHRASINGS:
        assert _verify_claim_raw_matches(phrase), label


# ── 3. gate 1 (STRICT / `_pending_verify_matches`) is completely unchanged ───────────────────────

def test_new_phrasings_never_reach_pending_verify_matches_gate1_is_untouched():
    # the exact assertion the ticket asked for: widening gate 2's vocabulary must not widen gate 1.
    for label, phrase in NEW_PHRASINGS:
        assert _pending_verify_matches(phrase) == [], f"{label}: leaked into gate 1: {phrase!r}"


# frozen real-board corpus, pinned verbatim (mirrors both sibling test files' own anti-loosening-pin
# idiom) — gate 1's verdict on each must be byte-for-byte what it was before this change.
FROZEN_GATE1_POSITIVES = (
    "▶ **VERIFY-LIVE for the flip (this is what closes defect 2, not the deploy):** the next partial",
    "wired into the 15-min reconcile; card-built Fable-reviewed; VERIFY-LIVE Mon 7/6 = first "
    "reconcile cycles write coverage_drift audit rows, expect quiet",
    "▶ VERIFY-LIVE = tonight's 17:35 ET consolidation job writes the first `entry_mode='confirm'`",
    "trigger — needs operator naming) OR Fri 7/17 ~5PM ET nightly. VERIFY-LIVE checkpoints on "
    "the armed run: (1) `theme_dominant_split_eligible` audit event",
    "ite 2972. REMAINING = deploy (rides the next batch w/ T5) + verify-live = the hook logs on "
    "the next entry evaluation. >> STAGE-1 BUILT 7/16 eve (inlin",
)
FROZEN_GATE1_SUPPRESSED = (
    "ssion, not an EOD roll] [ok:operator-CLOSE reconcile 7/17 — verify-live pending Monday "
    "market / remaining-deliverable / event-gated] >> RE-HOMED to #4",
    " (alt) for later settlement. ALL SHADOW (zero execution). ✅ VERIFY-LIVE DONE 6/18 (deploy "
    "b8245ec, both): write-probe proved the insert path (insert✓ ",
)
# the 4 lines the sibling `_deployed_no_verify` test file froze — BROAD widened for THAT gate; gate 1
# must still see NOTHING in any of them (none carry STRICT vocabulary at all).
FROZEN_GATE2_LINES_MUST_STAY_INVISIBLE_TO_GATE1 = (
    "▶ **VERIFY MONDAY:** theme engine 17:00 ET run (5 of the 10 sites) + the morning EP scan "
    "(extractor + catalyst grade) both clean. Close this task only when 1-6 are all confirmed IN PROD.",
    "VERIFIED IN PROD RIGHT AFTER DEPLOY: `breaker[live]=0`, `breaker[paper]=0` against a threshold "
    "of 3 — the per-mode query runs and nothing tripped on the cutover. DEPLOYED != VERIFIED — the "
    "verify is EVENT-GATED.",
    "▶ VERIFY 2026-08-08 (Sat morning, on tonight's 17:00 ET run): a theme that RETIRES tonight "
    "still has its `stage='Retired'` row in `mi_themes` tomorrow.",
)


def test_gate1_unchanged_frozen_positives_still_fire():
    for s in FROZEN_GATE1_POSITIVES:
        assert _pending_verify_matches(s), s


def test_gate1_unchanged_frozen_suppressions_still_suppressed():
    for s in FROZEN_GATE1_SUPPRESSED:
        assert _pending_verify_matches(s) == [], s


def test_gate1_unchanged_gate2s_newly_recognized_lines_still_invisible_to_gate1():
    # the whole point: BROAD's 3 new catches for gate 2 must produce ZERO change in gate 1's view.
    for s in FROZEN_GATE2_LINES_MUST_STAY_INVISIBLE_TO_GATE1:
        assert _pending_verify_matches(s) == [], s
