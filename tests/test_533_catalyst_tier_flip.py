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
    assert "resolve_live_tier(" in src


def test_flip_sits_after_prose_downgrade_and_before_score_ep():
    """Order is the criterion: the lattice re-tiers the FINAL raw grade (post-#72
    downgrade, post-earnings-boost) and everything from _score_ep on sees its verdict."""
    src = _scan_src()
    i_prose = src.index("Prose-mismatch downgrade (#72")
    i_flip = src.index("llm_catalyst_quality = catalyst_quality")
    i_score = src.index("ep_score, breakdown = _score_ep(")
    assert i_prose < i_flip < i_score


def test_lattice_failure_fails_open_to_the_raw_grade_loudly():
    src = _scan_src()
    assert src.count("LLM grade acts this tick") >= 2, (
        "both the setup and the per-candidate lattice paths must degrade to the raw "
        "grade AND say so in the log — degraded-loud, never dark")


def test_record_carries_raw_grade_acting_verdict_and_live_side():
    """The both-sides record: live_quality stays the RAW LLM grade (constant column
    semantics across the flip), the ACTING verdict rides along verbatim, live_side says
    which side acted — the live-vs-old comparison never infers the side from dates."""
    src = _scan_src()
    assert '"live_quality": llm_catalyst_quality,' in src
    assert '"verdict": _lattice_verdict,' in src
    assert '"live_side": _live_side,' in src


def test_post_grade_filters_still_read_the_raw_grade():
    """Deliberate scope line (SSoT change log): the shadow evaluation covered only the
    post-filter pool, so the flip must NOT reach _post_grade_filters — the lattice
    re-assignment happens strictly AFTER both filter call sites."""
    src = _scan_src()
    i_flip = src.index("llm_catalyst_quality = catalyst_quality")
    assert src.rindex("_post_grade_filters(") < i_flip


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
