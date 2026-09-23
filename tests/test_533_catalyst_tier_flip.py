"""#533 Change 6 — THE FLIP's wiring pins (2026-08-22, operator-signed).

The behavioral semantics (flag off -> raw grade; lattice verdict acts when on; fail-open)
are pinned as VALUES in test_catalyst_tier_shadow.py::resolve_live_tier tests, and in
tests/test_lattice_admission_consistency.py, which drives the real
`_resolve_acting_catalyst_quality` / `_tier_kill_row` helpers end to end (toggle on/off,
fail-open, filter admission). These are the test_347-pattern source pins: a refactor of
run_ep_scan cannot silently drop the flip point, the fail direction, the both-sides
record, the nightly monitor wiring, or the fixture's ride to prod (which keeps revert
trigger (a) alive).

2026-09-13 (#653 cleanup): `_resolve_acting_catalyst_quality` and `_tier_shadow_base` are
plain, standalone functions (not closures inside run_ep_scan) — two of these pins now call
them directly instead of grepping ep_detector.py's source text; both mutation-proven. One
db.py schema pin converts the same way as test_yoy_writeback_and_window.py's
test_schema_adds_the_column_at_boot (real initialize_schema() against a fake pool). Two
assertions that exactly duplicated existing checks in test_lattice_admission_consistency.py
(`test_both_filter_call_sites_thread_the_acting_side_marker`,
`test_filter_killed_graded_candidates_are_captured_for_the_tier_record`) are DELETED here,
named at the point of deletion below. The rest stay TAGGED: they pin where inside
run_ep_scan's ~2100-line body (a closure with no independently-callable seam) a call
happens, or in what order — genuinely wiring/ordering claims, the closed-list legitimate
case, not a value this file could exercise by calling anything."""
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
    # source-pin-ok: wiring check that run_ep_scan calls the correct helper at the
    # correct toggle name — the VALUE semantics of that helper (and of resolve_live_tier
    # it threads to) are behaviorally proven in test_lattice_admission_consistency.py and
    # test_catalyst_tier_shadow.py; this file's job is only "is it wired in", per its
    # own module docstring.
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
    # source-pin-ok: ordering check on three markers inside run_ep_scan's own body — a
    # closure with no independently-callable seam (see module docstring).
    src = _scan_src()
    i_prose = src.index("Prose-mismatch downgrade (#72")
    i_flip = src.index("FINAL RESOLVE")
    i_score = src.index("ep_score, breakdown = _score_ep(")
    assert i_prose < i_flip < i_score


def test_lattice_setup_failure_also_fails_open_loudly():
    """The lattice SETUP path (toggle read + board-sector prefetch, once per scan tick,
    before the per-candidate loop) is a separate fail-open site from the per-candidate
    resolve helper (converted below) -- it lives inline in run_ep_scan's own body with
    no independently-callable seam."""
    # source-pin-ok: ordering/presence check on run_ep_scan's own setup-path fail-open
    # branch — see module docstring; the per-candidate helper's fail-open is converted
    # (test_resolve_helper_fails_open_to_the_raw_grade_loudly, below).
    src = _scan_src()
    assert "LLM grade acts this tick" in src, (
        "the setup path must degrade to the raw grade AND say so in the log")


def test_resolve_helper_fails_open_to_the_raw_grade_loudly(caplog):
    """Calls the REAL `_resolve_acting_catalyst_quality` with the lattice forced to
    raise, instead of grepping its source text. `test_lattice_admission_consistency.py`
    ::test_resolve_fails_open_to_the_raw_grade already proves the RETURN VALUE degrades
    to the raw grade; this test adds the other half of "loudly" -- the log line.

    MUTATION TARGET: delete the `logger.warning(...)` call in the except branch (keep
    the fail-open return) -- the scan would silently keep working on a broken lattice
    with nothing in the logs to say so."""
    import logging
    from unittest.mock import patch

    caplog.set_level(logging.WARNING)
    with patch(
        "agents.market_intelligence.catalyst_tier_shadow.compute_shadow_verdict",
        side_effect=RuntimeError("boom"),
    ):
        acting, verdict, side = ep_detector._resolve_acting_catalyst_quality(
            "TEST", "routine", "analysis text", None, None, {}, True)
    assert (acting, verdict, side) == ("routine", None, "llm")
    assert "LLM grade acts this tick" in caplog.text, (
        "the per-candidate resolve must degrade to the raw grade loudly — never dark")


def test_record_shape_carries_raw_grade_acting_verdict_and_live_side():
    """The both-sides record: live_quality stays the RAW LLM grade (constant column
    semantics across the flip), the ACTING verdict rides along verbatim, live_side says
    which side acted — the live-vs-old comparison never infers the side from dates.

    Calls the REAL `_tier_shadow_base` (a plain, standalone function) instead of
    grepping its source text for the three key literals.

    MUTATION TARGET: rename the `"live_side"` key to `"acting_side"` in the returned
    dict — `catalyst_tier_shadow.record_catalyst_tier_shadow` reads every key by name
    (per this function's own docstring), so every write would silently stop recording
    which side acted."""
    row = ep_detector._tier_shadow_base(
        "TEST", "routine", {"shadow_tier": "strong", "rule": "x"}, "lattice",
        "analysis", "grounded", "news", {"gap_pct": 10.0, "adv": 1e6, "prev_close": 20.0},
        0.5)
    assert row["live_quality"] == "routine", "constant column semantics: RAW grade, not acting"
    assert row["verdict"] == {"shadow_tier": "strong", "rule": "x"}
    assert row["live_side"] == "lattice"


def test_tier_shadow_base_is_called_exactly_once_in_run_ep_scan():
    """DELIBERATELY updated 2026-08-2x (Finding 3 cleanup): the post-score capture used to
    hand-write these three keys as a dict literal inline in run_ep_scan, duplicating the
    filter-killed kill-row's identical 11 shared fields — the two-places-to-sync fork the
    2026-08-22 grade-consistency commit was itself fixing for the grade. Both call sites
    now spread `_tier_shadow_base(...)`, so the key literals live there (converted above),
    not in run_ep_scan's own source; run_ep_scan just calls the builder positionally.

    _tier_kill_row's OWN call count (2, the two filter-kill sites) is intentionally not
    re-checked here — test_lattice_admission_consistency.py
    ::test_filter_killed_graded_candidates_are_captured_for_the_tier_record already pins
    `src.count("_tier_kill_row(") == 2` byte-for-byte; re-asserting it here would be a
    second copy of the same check, not a second claim."""
    # source-pin-ok: wiring check that run_ep_scan calls the (converted, above) builder
    # exactly once — see module docstring.
    src = _scan_src()
    assert src.count("_tier_shadow_base(") == 1


def test_prose_downgrade_telegram_sends_after_the_final_resolve():
    """Finding 5 (2026-08-2x, coordinator-verified): the #72 downgrade fires on prose
    markers ("no specific catalyst" / "no specific news") that are themselves literal
    substrings of the lattice corrective's own rule-4-demotion-marker regex — so if a
    concrete company event is ALSO present in the same text, the FINAL resolve can
    promote the name straight back out of routine. A message sent from inside the
    downgrade branch (before that resolve runs) can assert "will not promote to HIGH"
    on a name the lattice is about to un-downgrade. The send must therefore sit AFTER
    the last (final) resolve call and report whichever grade actually acted."""
    # source-pin-ok: ordering + content check inside run_ep_scan's own body — a closure
    # with no independently-callable seam (see module docstring).
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
    2026-08-22 (consistency fix).

    The "both call sites thread lattice_acting" half is DELETED here — it exactly
    duplicated test_lattice_admission_consistency.py
    ::test_both_filter_call_sites_thread_the_acting_side_marker
    (`src.count('lattice_acting=(_live_side == "lattice")') == 2`, byte-for-byte, same
    file that already owns this claim). Only the ordering half (not pinned there)
    stays."""
    # source-pin-ok: ordering check inside run_ep_scan's own body — a closure with no
    # independently-callable seam (see module docstring).
    src = _scan_src()
    i_first_resolve = src.index("_resolve_acting_catalyst_quality(")
    i_first_filter = src.index("_post_grade_filters(")
    assert i_first_resolve < i_first_filter, (
        "an acting-grade resolve must precede the first filter call site")


def test_monitor_is_wired_into_the_existing_nightly_audit_job():
    """No new cron surface — the flip monitor rides _post_nightly_audit_job like every
    neighbouring health check, with its own try/except + notify_job_failure."""
    # source-pin-ok: wiring check that the monitor is actually called from the nightly
    # job — _post_nightly_audit_job is a ~300-line orchestrator awaiting ~13 unrelated
    # health checks in sequence; no existing test in this repo drives it end-to-end
    # (each of the other checks binds its own get_pool at ITS OWN module's import time —
    # see tests/test_inert_sweep_check.py's file docstring for the full reasoning, which
    # applies verbatim here).
    from agents.market_intelligence import scheduler
    src = inspect.getsource(scheduler._post_nightly_audit_job)
    assert "run_catalyst_lattice_monitor" in src
    assert 'notify_job_failure("catalyst_lattice_monitor"' in src


def test_fixture_ships_to_prod_so_trigger_a_cannot_be_dark():
    """Revert trigger (a) reads tests/fixtures/must_not_miss_eps.py AT RUNTIME in prod:
    the market image must COPY it, and deploy.sh must scope a member edit to the market
    image (the generic tests/* arm is deploy-irrelevant and would let it go stale)."""
    # source-pin-ok: deploy-config ordering check (a declarative Dockerfile/shell-script
    # ordering, not executable Python behavior) — the closed-list "a specific
    # constant/id appears in a registration block" case, applied to a deploy arm.
    dockerfile = (_REPO / "docker" / "Dockerfile.market").read_text()
    assert "COPY tests/fixtures/must_not_miss_eps.py tests/fixtures/must_not_miss_eps.py" \
        in dockerfile
    deploy = (_REPO / "scripts" / "deploy.sh").read_text()
    arm = "tests/fixtures/must_not_miss_eps.py)"
    # 2026-08-29: docs/* got its OWN preceding arm (the drift-check job now reads docs/ at
    # runtime too), so the generic deploy-irrelevant arm no longer combines tests/* with docs/*
    # on one line — the invariant this test pins (fixture arm precedes the generic tests/* arm)
    # is unchanged, only the literal text of that arm.
    generic = "tests/*|*.md"
    assert arm in deploy and deploy.index(arm) < deploy.index(generic), (
        "the fixture's NEED_MARKET arm must precede the deploy-irrelevant tests/* arm")


class _FakeSchemaConn:
    """Records every statement `initialize_schema()` sends to (a fake) Postgres at boot —
    the same harness as test_yoy_writeback_and_window.py::test_schema_adds_the_column_at_boot."""

    def __init__(self, sink):
        self._sink = sink

    async def execute(self, sql, *a, **k):
        self._sink.append(sql)
        return "OK"

    async def executemany(self, sql, seq, *a, **k):
        self._sink.append(sql)

    async def fetchval(self, sql, *a, **k):
        return 0  # startup row-count log query -- value is unused by the guard below


class _FakeSchemaAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *a):
        return False


class _FakeSchemaPool:
    def __init__(self, sink):
        self._conn = _FakeSchemaConn(sink)

    def acquire(self):
        return _FakeSchemaAcquire(self._conn)


def test_live_side_column_is_declared_with_llm_backfill(monkeypatch):
    """The migration stamps every pre-flip row 'llm' — the side that WAS live when it
    was written — so no reader ever infers the acting side from the date. Calls the
    REAL initialize_schema() against a fake pool and inspects the literal DDL it would
    send to Postgres at boot, instead of grepping db.py's source text.

    MUTATION TARGET: drop ` DEFAULT 'llm'` from the ALTER statement -- an existing
    deployment's pre-flip rows would backfill the new column as NULL, and every reader
    would have to guess whether a NULL live_side means 'llm' (the true pre-flip fact)
    or a broken write, instead of it saying so."""
    import asyncio

    from agents.market_intelligence import db as db_mod

    sink: list[str] = []

    async def _pool():
        return _FakeSchemaPool(sink)

    monkeypatch.setattr(db_mod, "get_pool", _pool)
    asyncio.run(db_mod.initialize_schema())
    assert any(
        "ALTER TABLE mi_catalyst_tier_shadow ADD COLUMN IF NOT EXISTS live_side "
        "TEXT DEFAULT 'llm';" in sql
        for sql in sink
    ), "boot-time DDL must add live_side with the 'llm' backfill default"
