"""#650 — the judge's DEMOTIONS get the same zero-authority 2nd-model read a HIGH does.

Background (docs/analysis/485_judge_meta_review_feasibility_2026-09-12.md §2d): the #301
ensemble-divergence monitor (judge_divergence.py) triggered on HIGH-tier verdicts only —
97/97 HIGH verdicts since 2026-07-27 got a same-day second read, but the judge's 17
DEMOTIONS in that same window (the judge deciding a floor-HIGH/MODERATE candidate is NOT
tradeable — HIGH->MODERATE, HIGH->none, MODERATE->none) got zero. A demotion silently
removes a candidate, which is exactly the decision worth a second look.

`_is_judge_demotion` (agents/market_intelligence/ep_detector.py) is the pure, FACTUAL
tier-rank predicate (SSoT `constants.TIER_RANK`, the same none < MODERATE < HIGH lattice
`briefing._judge_direction` uses for the operator-facing promote/hold/demote line) that
the `_judge_shadow` trigger now ORs alongside the pre-existing `tier == "HIGH"` check.
Deliberately NOT the judge's own raw `direction_vs_floor` field, which is unvalidated
model output that can disagree with what the tier actually did (OKTA 2026-08-27).

ZERO AUTHORITY (THE LINE): none of this reads or writes a grade/entry/exit. These tests
pin only the TRIGGER POPULATION — that a demotion now qualifies for the same fire-and-
forget `launch_divergence_check` call a HIGH does, via the same dedupe-guarded `if` in
ep_detector.py. `tests/test_judge_divergence.py` pins that the downstream call itself
(`judge_divergence._run`) never feeds anything back — unchanged by this widening.
"""
from agents.market_intelligence.ep_detector import _is_judge_demotion


# ─── _is_judge_demotion: the pure tier-rank predicate ──────────────────────────────────────
#
# Each test below was RED-proved by temporarily reverting `_is_judge_demotion` to
# `return False` unconditionally (the pre-#650 state has no such function at all, so a
# stub-false body is the closest same-shape mutation) and confirming the demotion-expecting
# assertions failed while the non-demotion ones kept passing (see the #650 commit message
# for the exact before/after pytest output) — then restoring the real rank comparison.


def test_high_to_moderate_is_a_demotion():
    """MUTATION: stub body `return False` — this assertion (expects True) is the one that
    flips and fails; it is the #485-cited HIGH->MODERATE population (17 of the 17 rows in
    the 2d table are HIGH->MODERATE or HIGH->none or MODERATE->none)."""
    assert _is_judge_demotion("MODERATE", "HIGH") is True


def test_high_to_none_is_a_demotion():
    """MUTATION: stub body `return False` — fails on this assertion. HIGH->none is the
    judge fully suppressing a floor-HIGH candidate (score_tier becomes 'none', no alert)."""
    assert _is_judge_demotion("none", "HIGH") is True


def test_moderate_to_none_is_a_demotion():
    """MUTATION: stub body `return False` — fails on this assertion. MODERATE->none is the
    judge suppressing a floor-MODERATE candidate."""
    assert _is_judge_demotion("none", "MODERATE") is True


def test_hold_is_not_a_demotion():
    """MUTATION: swap `a < b` for `a <= b` — this is the assertion that flips (a hold has
    a == b, so `<=` wrongly reports True where the real rank comparison reports False)."""
    assert _is_judge_demotion("HIGH", "HIGH") is False
    assert _is_judge_demotion("MODERATE", "MODERATE") is False
    assert _is_judge_demotion("none", "none") is False


def test_promotion_is_not_a_demotion():
    """MUTATION: swap `a < b` for `a != b` — this is the assertion that flips (a promotion
    has a > b, which `!=` wrongly reports as a demotion). MODERATE->HIGH is the #243
    fat-tail-capture promotion path; #650 must not also fire the divergence check on it
    under the demotion arm (it's still exempt from the trigger unless tier == 'HIGH', which
    the promoted case IS — so this test is what proves the demotion arm alone stays False
    here, distinct from the separate HIGH arm that legitimately fires on it)."""
    assert _is_judge_demotion("HIGH", "MODERATE") is False


def test_unknown_tier_is_not_a_demotion_fail_closed():
    """MUTATION: remove the `a is None or b is None` guard — this would raise `TypeError:
    '<' not supported between instances of 'NoneType' and 'int'` instead of returning False,
    which would crash the live `_judge_shadow` scan loop on a malformed/unrecognized tier
    string rather than simply skipping the (zero-authority) 2nd read. Fail-closed, not
    fail-crash."""
    assert _is_judge_demotion(None, "HIGH") is False
    assert _is_judge_demotion("HIGH", None) is False
    assert _is_judge_demotion("bogus-tier", "HIGH") is False


# ─── The trigger site: demotions reach launch_divergence_check the same way HIGH does ──────


def test_trigger_site_ors_demotion_alongside_high_gated_by_the_same_dedupe():
    """Source-level pin (the `_judge_shadow` trigger lives inside a closure nested in
    `run_ep_scan`, the same reason `_resolve_grade_authority`'s call site and the
    composite-authority wire-in are pinned this way rather than by invoking the closure
    directly — see test_judge_divergence.py's sibling static test and
    test_composite_authority_wire.py's docstring).

    MUTATION: revert the ep_detector.py trigger edit (drop the
    `or _is_judge_demotion(...)` clause) — this test fails because `_is_judge_demotion(`
    no longer appears in the module, while `tests/test_judge_divergence.py`'s original
    HIGH-only assertion (`'v.get("tier") == "HIGH"'`) keeps passing unchanged, which is
    exactly the gap #650 closes: the HIGH arm alone is not evidence the demotion arm
    exists."""
    import agents.market_intelligence.ep_detector as ep
    src = open(ep.__file__).read()

    assert "_is_judge_demotion(" in src
    assert "def _is_judge_demotion(judge_tier, floor_tier)" in src

    # The demotion check and the pre-existing HIGH check must be OR'd into ONE `if` that
    # is ANDed with the SAME per-ticker-per-day dedupe call (`_audit_dedupe_check(...,
    # "judge_divergence_check")`) guarding the SAME `launch_divergence_check(` call —
    # i.e. one trigger population, not a second parallel code path with its own dedupe/
    # call-site (which could silently diverge from the HIGH arm's fire-and-forget
    # discipline or double-fire the same-day check).
    idx_high = src.index('v.get("tier") == "HIGH"')
    idx_demotion = src.index("_is_judge_demotion(v.get(\"tier\"), floor_tier)")
    idx_dedupe = src.index('_audit_dedupe_check(\n', idx_high)
    idx_launch = src.index("launch_divergence_check(\n", idx_dedupe)

    assert idx_high < idx_demotion < idx_dedupe < idx_launch, (
        "expected ONE if-block: (HIGH or demotion) and dedupe -> launch_divergence_check, "
        "in that source order"
    )
    # Only one launch_divergence_check( call site exists for this trigger — a second,
    # separately-dedupe'd call site would be exactly the "new code path" this test rules out.
    assert src.count("launch_divergence_check(\n") == 1
