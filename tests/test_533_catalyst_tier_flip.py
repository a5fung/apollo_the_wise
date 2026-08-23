"""#533 Change 6 — THE FLIP's wiring pins (2026-08-22, operator-signed).

The behavioral semantics (flag off -> raw grade; lattice verdict acts when on; fail-open)
are pinned as VALUES in test_catalyst_tier_shadow.py::resolve_live_tier tests. These are
the test_347-pattern source pins: a refactor of run_ep_scan cannot silently drop the flip
point, the fail direction, the both-sides record, the nightly monitor wiring, or the
fixture's ride to prod (which keeps revert trigger (a) alive).
"""
from __future__ import annotations

import inspect
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from agents.market_intelligence import ep_detector

_REPO = pathlib.Path(__file__).resolve().parent.parent


def _scan_src() -> str:
    return inspect.getsource(ep_detector.run_ep_scan)


def test_flip_is_gated_by_the_one_revert_flag():
    src = _scan_src()
    assert 'get_runtime_toggle(' in src
    assert '"catalyst_tier_lattice", "CATALYST_TIER_LATTICE_ENABLED", default=True)' in src, (
        "the #400a instant-revert toggle IS the whole safety story — one flag, default ON")
    # Since the 2026-08-22 consistency fix the resolve is centralized: run_ep_scan calls
    # _resolve_acting_catalyst_quality (grade-settle, post-mutation, final), and THAT
    # helper is where resolve_live_tier gates on the one flag.
    assert "_resolve_acting_catalyst_quality(" in src
    helper = inspect.getsource(ep_detector._resolve_acting_catalyst_quality)
    assert "resolve_live_tier(" in helper


def test_flip_sits_after_prose_downgrade_and_before_score_ep():
    """Order is the criterion: the FINAL resolve re-tiers the FINAL raw grade (post-#72
    downgrade, post-earnings-boost) and everything from _score_ep on sees its verdict."""
    src = _scan_src()
    i_prose = src.index("Prose-mismatch downgrade (#72")
    i_flip = src.index("FINAL RESOLVE")
    i_score = src.index("ep_score, breakdown = _score_ep(")
    assert i_prose < i_flip < i_score


def test_lattice_failure_fails_open_to_the_raw_grade_loudly():
    src = _scan_src()
    assert "LLM grade acts this tick" in src, (
        "the setup path must degrade to the raw grade AND say so in the log")
    helper = inspect.getsource(ep_detector._resolve_acting_catalyst_quality)
    assert "LLM grade acts this tick" in helper, (
        "the per-candidate resolve must degrade to the raw grade loudly — never dark")


def test_record_carries_raw_grade_acting_verdict_and_live_side():
    """The both-sides record: live_quality stays the RAW LLM grade (constant column
    semantics across the flip), the ACTING verdict rides along verbatim, live_side says
    which side acted — the live-vs-old comparison never infers the side from dates.

    DELIBERATELY updated 2026-08-2x (Finding 3 cleanup): the post-score capture used to
    hand-write these three keys as a dict literal inline in run_ep_scan, duplicating the
    filter-killed kill-row's identical 11 shared fields — the two-places-to-sync fork the
    2026-08-22 grade-consistency commit was itself fixing for the grade. Both call sites
    now spread `_tier_shadow_base(...)`, so the key literals live there, not in
    run_ep_scan's own source; run_ep_scan just calls the builder positionally."""
    base_src = inspect.getsource(ep_detector._tier_shadow_base)
    assert '"live_quality": llm_quality,' in base_src
    assert '"verdict": verdict,' in base_src
    assert '"live_side": live_side,' in base_src
    src = _scan_src()
    # run_ep_scan calls _tier_shadow_base directly once (the post-score capture) and
    # _tier_kill_row twice (the two filter-kill sites) — _tier_kill_row itself spreads
    # _tier_shadow_base internally, so all THREE tier-shadow rows build on the one
    # shared shape even though only one call to the builder is textually in this
    # function's own source.
    assert src.count("_tier_shadow_base(") == 1
    assert src.count("_tier_kill_row(") == 2


def test_prose_downgrade_telegram_sends_after_the_final_resolve():
    """Finding 5 (2026-08-2x, coordinator-verified): the #72 downgrade fires on prose
    markers ("no specific catalyst" / "no specific news") that are themselves literal
    substrings of the lattice corrective's own rule-4-demotion-marker regex — so if a
    concrete company event is ALSO present in the same text, the FINAL resolve can
    promote the name straight back out of routine. A message sent from inside the
    downgrade branch (before that resolve runs) can assert "will not promote to HIGH"
    on a name the lattice is about to un-downgrade. The send must therefore sit AFTER
    the last (final) resolve call and report whichever grade actually acted."""
    src = _scan_src()
    # The 5th/last _resolve_acting_catalyst_quality( call is the unconditional FINAL
    # resolve (cached settle, fresh settle, earnings boost, revenue gate, final = 5;
    # pinned by test_every_resolve_site_is_present in test_lattice_admission_consistency.py).
    i_final_resolve = src.rindex("_resolve_acting_catalyst_quality(")
    i_send = src.index('📰 *Catalyst downgrade:*')
    i_score = src.index("ep_score, breakdown = _score_ep(")
    assert i_final_resolve < i_send < i_score, (
        "the downgrade Telegram must sit AFTER the FINAL resolve and BEFORE the score "
        "call — it can only report a grade that has already been fully resolved")
    # Exactly one send site, and both possible outcomes are named in plain words — the
    # message never asserts an outcome before the resolve has confirmed it.
    assert src.count('📰 *Catalyst downgrade:*') == 1
    assert "This alert will not promote to HIGH." in src, (
        "unreversed case: still routine after the final resolve")
    assert "reversed it" in src and "Acting grade now:" in src, (
        "reversed case: the corrective promoted it back out of routine — must say so, "
        "not stay silent or repeat the stale 'will not promote' line")


def test_post_grade_filters_read_the_acting_grade():
    """⚖ REVERSAL of the flip-day scope line (2026-08-22, operator-directed — "if we
    change something we change it everywhere, consistency at all times, no forks").
    The prior rule ("the filters keep reading the RAW grade because the shadow eval
    only covered the post-filter pool") was WRONG, not just incomplete: it re-killed
    the exact class the flip was signed to save — a real EP mis-graded routine at a
    sub-12% gap died at the admission filter before the correction could act, and a
    filter and a score disagreed about what the same news was worth. Now every filter
    call site sits AFTER an acting-grade resolve and passes the acting grade +
    lattice_acting. Full rationale + numbers: docs/setups/magna53_ep.md change log
    2026-08-22 (consistency fix)."""
    src = _scan_src()
    i_first_resolve = src.index("_resolve_acting_catalyst_quality(")
    i_first_filter = src.index("_post_grade_filters(")
    assert i_first_resolve < i_first_filter, (
        "an acting-grade resolve must precede the first filter call site")
    # BOTH call sites must thread the acting-side marker — no raw-grade filter path.
    assert src.count("lattice_acting=(_live_side == \"lattice\")") == 2


def test_monitor_is_wired_into_the_existing_nightly_audit_job():
    """No new cron surface — the flip monitor rides _post_nightly_audit_job like every
    neighbouring health check, with its own try/except + notify_job_failure."""
    from agents.market_intelligence import scheduler
    src = inspect.getsource(scheduler._post_nightly_audit_job)
    assert "run_catalyst_lattice_monitor" in src
    assert 'notify_job_failure("catalyst_lattice_monitor"' in src


def test_fixture_ships_to_prod_so_trigger_a_cannot_be_dark():
    """Revert trigger (a) reads tests/fixtures/must_not_miss_eps.py AT RUNTIME in prod:
    the market image must COPY it, and deploy.sh must scope a member edit to the market
    image (the generic tests/* arm is deploy-irrelevant and would let it go stale)."""
    dockerfile = (_REPO / "docker" / "Dockerfile.market").read_text()
    assert "COPY tests/fixtures/must_not_miss_eps.py tests/fixtures/must_not_miss_eps.py" \
        in dockerfile
    deploy = (_REPO / "scripts" / "deploy.sh").read_text()
    arm = "tests/fixtures/must_not_miss_eps.py)"
    generic = "tests/*|docs/*"
    assert arm in deploy and deploy.index(arm) < deploy.index(generic), (
        "the fixture's NEED_MARKET arm must precede the deploy-irrelevant tests/* arm")


def test_live_side_column_is_declared_with_llm_backfill():
    """The migration stamps every pre-flip row 'llm' — the side that WAS live when it
    was written — so no reader ever infers the acting side from the date."""
    db_src = (_REPO / "agents" / "market_intelligence" / "db.py").read_text()
    assert ("ALTER TABLE mi_catalyst_tier_shadow ADD COLUMN IF NOT EXISTS live_side "
            "TEXT DEFAULT 'llm';") in db_src
