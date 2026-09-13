"""#653 — a NEW or EDITED test may not assert on SOURCE TEXT instead of behaviour.

WHY: 285 of 5,881 test functions pinned literal source text (`inspect.getsource`, `.read_text()`
on a module, `open("agents/...")`) rather than behaviour, and 32 of them broke 2026-09-12 against
a refactor that changed nothing real. `scripts/check_test_source_pins.py` gates any NEW/EDITED one
(vs `origin/main`) the same way `check_plan._review_can_fire_gate` gates new/edited reviews — the
existing backlog is surfaced, never blocked on.

Every test below states, in its own docstring or an inline comment, the mutation that reddens it —
each was run RED against that mutation and restored green before this file was committed (the
CLAUDE.md rule this task itself is enforcing: an unproven assertion is worse than none).
"""
from __future__ import annotations

import textwrap

from scripts.check_test_source_pins import (
    find_source_pin_functions,
    parse_added_lines,
    scan_repo,
)


def _src(body: str) -> str:
    """Dedent a triple-quoted test-module snippet used as a synthetic source file."""
    return textwrap.dedent(body).lstrip("\n")


# ── detection: each of the three read mechanisms named in the DoD ──────────────────────────

def test_getsource_on_a_scoped_symbol_is_flagged():
    """MUTATION: deleting the `_is_getsource_call` branch from `_is_inline_source_read`
    (replacing its `or` chain with just `_is_read_text_call(...)`) reddened this — the
    function stopped being flagged at all. Restored, re-verified green."""
    src = _src("""
        import inspect
        from agents.market_intelligence import ep_detector

        def test_run_ep_scan_still_sorts_by_score():
            assert "sort" in inspect.getsource(ep_detector.run_ep_scan)
    """)
    hits = find_source_pin_functions(src, "<t>")
    assert [h["name"] for h in hits] == ["test_run_ep_scan_still_sorts_by_score"]
    assert hits[0]["escaped"] is False


def test_read_text_on_a_scoped_module_is_flagged():
    """MUTATION: deleting the `.endswith(SOURCE_EXTS)` half of `_looks_like_scoped_source_path`
    (leaving only the scoped-dir check) did NOT redden this one (still flagged) — expected,
    since it's a genuine `.py` path; it's the NEXT test (a `.json` fixture) that mutation
    catches. Proven together: see `test_data_file_reads_are_not_flagged` below."""
    src = _src("""
        import pathlib

        SRC = pathlib.Path("agents/market_intelligence/db.py").read_text()

        def test_conflict_target_matches_the_key():
            assert "ON CONFLICT" in SRC
    """)
    hits = find_source_pin_functions(src, "<t>")
    assert [h["name"] for h in hits] == ["test_conflict_target_matches_the_key"]


def test_open_on_a_scoped_path_is_flagged():
    """MUTATION: removing `_is_scoped_open_read` from the `_is_inline_source_read` `or` chain
    reddened this (dropped to zero hits). Restored, re-verified green."""
    src = _src("""
        def test_no_bare_send_left():
            src = open("agents/market_intelligence/health_checks.py").read()
            assert "run_account_mode_graduation_sweep" in src
    """)
    hits = find_source_pin_functions(src, "<t>")
    assert [h["name"] for h in hits] == ["test_no_bare_send_left"]


def test_with_open_as_handle_pattern_is_flagged():
    """The `with open(...) as f: ... f.read()` shape (not the inline `open().read()` form
    above). MUTATION: making `_collect_file_handles` return an empty set unconditionally
    reddened this (the `f.read()` reference stopped resolving to a scoped read). Restored,
    re-verified green."""
    src = _src("""
        def test_handler_is_registered():
            with open("channels/telegram.py") as f:
                body = f.read()
            assert "/partialnow" in body
    """)
    hits = find_source_pin_functions(src, "<t>")
    assert [h["name"] for h in hits] == ["test_handler_is_registered"]


# ── detection: the two indirection patterns this repo's own tests actually use ──────────────

def test_module_level_shared_source_variable_is_flagged():
    """The `HEALTH = Path("agents/.../health_checks.py").read_text()` pattern
    `tests/test_account_mode_literal_gate.py` uses today, read only via a bare Name inside the
    test function. MUTATION: seeding `module_atoms` with `set()` unconditionally (instead of the
    fixed-point over module-level assigns) reddened this. Restored, re-verified green."""
    src = _src("""
        import pathlib

        HEALTH = pathlib.Path("agents/market_intelligence/health_checks.py").read_text()

        def test_sweep_is_wired():
            assert "run_account_mode_graduation_sweep" in HEALTH
    """)
    hits = find_source_pin_functions(src, "<t>")
    assert [h["name"] for h in hits] == ["test_sweep_is_wired"]


def test_sliced_derivative_of_a_source_atom_is_flagged():
    """The `call = TRACKER[j:call_end]` shape — asserting against a SLICE of a source-read
    variable, not the variable itself. MUTATION: capping `_fixed_point_atoms` at 0 rounds (no
    propagation at all, atoms == seed only) reddened this — `call` never joined the atom set.
    Restored, re-verified green."""
    src = _src("""
        import pathlib

        TRACKER = pathlib.Path("agents/market_intelligence/broker/live_tracker.py").read_text()

        def test_insert_skipped_trade_is_mode_scoped():
            i = TRACKER.find("async def process_new_alerts_live")
            call = TRACKER[i:i + 400]
            assert "_insert_skipped_trade" in call
    """)
    hits = find_source_pin_functions(src, "<t>")
    assert [h["name"] for h in hits] == ["test_insert_skipped_trade_is_mode_scoped"]


def test_same_file_helper_indirection_is_flagged():
    """The `_src(obj): return inspect.getsource(obj)` wrapper
    `tests/test_647_machine_text_alerts_on_html_layer.py` uses. MUTATION: making
    `_collect_source_helpers` return an empty set unconditionally reddened this (the call to
    `_src(fn)` no longer resolved to a source read). Restored, re-verified green."""
    src = _src("""
        import inspect

        def _src(obj):
            return inspect.getsource(obj)

        def test_sender_converted_at_the_boundary():
            from agents.market_intelligence import mgmt_judge
            assert 'parse_mode="HTML"' in _src(mgmt_judge.run_position_mgmt_judge)
    """)
    hits = find_source_pin_functions(src, "<t>")
    assert [h["name"] for h in hits] == ["test_sender_converted_at_the_boundary"]


# ── the scanner does NOT cry wolf ───────────────────────────────────────────────────────────

def test_a_source_extension_outside_any_scoped_dir_is_not_flagged():
    """A `.py` read that is NOT under `agents/ scripts/ channels/ core/ shared/` — e.g. a test
    helper module. Extension alone must not be enough. MUTATION: dropping the `has_scoped_dir`
    half of the `and` in `_looks_like_scoped_source_path` (matching on source-extension alone)
    reddened this — the read flipped to flagged even though it names no scoped dir. Restored,
    re-verified green. (`PLAN.md` and a docs `.md` are ALSO covered here, belt-and-suspenders —
    neither has a scoped dir OR a source extension, so this one mutation does not move them
    either way; the CLAUDE.md/#653 examples are folded in for the regression record.)"""
    src = _src("""
        import pathlib

        HELPER = pathlib.Path("tests/helpers/fake_module.py").read_text()
        PLAN = pathlib.Path("PLAN.md").read_text()
        DOC = pathlib.Path("docs/setups/magna53_ep.md").read_text()

        def test_helper_has_expected_function():
            assert "def helper" in HELPER

        def test_plan_names_the_task():
            assert "#653" in PLAN

        def test_doc_explains_the_window():
            assert "ORB" in DOC
    """)
    assert find_source_pin_functions(src, "<t>") == []


def test_a_data_file_under_a_scoped_dir_is_still_not_flagged():
    """The inverse case: a NON-source file that DOES sit under a scoped dir (e.g. a fixture
    shipped next to production code, or a `.tsv`/`.json` baseline). MUTATION: dropping the
    `has_source_ext` half of the `and` in `_looks_like_scoped_source_path` (matching on
    scoped-dir alone) reddened this — the `.json` read flipped to flagged. Restored,
    re-verified green."""
    src = _src("""
        import pathlib

        FIXTURE = pathlib.Path("agents/market_intelligence/fixtures/seed_data.json").read_text()

        def test_fixture_has_expected_rows():
            assert "HIGH" in FIXTURE
    """)
    assert find_source_pin_functions(src, "<t>") == []


def test_functions_with_no_assert_are_not_flagged():
    """A function that reads source for setup/printing but never asserts against it is not a
    pin — there is nothing here to break a refactor. MUTATION: deleting the `has_assert` guard
    (checking `references_source` alone) reddened this — it started flagging a print-only probe.
    Restored, re-verified green."""
    src = _src("""
        import inspect
        from agents.market_intelligence import ep_detector

        def test_prints_source_for_debugging():
            print(inspect.getsource(ep_detector.run_ep_scan))
    """)
    assert find_source_pin_functions(src, "<t>") == []


def test_non_test_functions_are_ignored():
    """A helper itself is not the thing being gated — only `test_*` functions are, even one that
    (unusually) both reads source AND asserts against it internally. MUTATION: relaxing
    `_is_test_func` to accept any function/async-function (dropping the `.startswith("test_")`
    check) reddened this — `_helper_check` started showing up in the results. Restored,
    re-verified green."""
    src = _src("""
        import inspect

        def _helper_check(obj):
            src = inspect.getsource(obj)
            assert "def" in src
            return src
    """)
    assert find_source_pin_functions(src, "<t>") == []


# ── the escape hatch: a reviewed reason suppresses it, a bare marker does not ───────────────

def test_escape_with_a_real_reason_is_honored():
    """MUTATION: deleting the `_escape_for` call in `find_source_pin_functions` (hardcoding
    `escaped=False`) reddened this — the escaped test stopped being marked escaped. Restored,
    re-verified green."""
    src = _src("""
        import inspect
        from agents.market_intelligence import ep_detector

        def test_run_ep_scan_still_sorts_by_score():
            # source-pin-ok: no runtime seam exposes sort order, only the source shows it
            assert "sort" in inspect.getsource(ep_detector.run_ep_scan)
    """)
    hits = find_source_pin_functions(src, "<t>")
    assert len(hits) == 1
    assert hits[0]["escaped"] is True
    assert hits[0]["reason"] == "no runtime seam exposes sort order, only the source shows it"


def test_bare_escape_marker_without_a_reason_is_not_honored():
    """The task is explicit: 'a reviewed marker requiring a stated reason, not a bare marker.'
    MUTATION: dropping the `_ESCAPE_REASON_FLOOR` length check (honoring any non-empty match)
    reddened this — a 3-character non-reason ('n/a') started being accepted as an escape.
    Restored, re-verified green."""
    src = _src("""
        import inspect
        from agents.market_intelligence import ep_detector

        def test_run_ep_scan_still_sorts_by_score():
            # source-pin-ok: n/a
            assert "sort" in inspect.getsource(ep_detector.run_ep_scan)
    """)
    hits = find_source_pin_functions(src, "<t>")
    assert len(hits) == 1
    assert hits[0]["escaped"] is False, "a bare marker with no real reason must still be a violation"


# ── diff plumbing: which lines a unified diff added, pure (no git needed) ──────────────────

def test_parse_added_lines_on_a_simple_hunk():
    """MUTATION: incrementing `cur` on `-` lines too (instead of leaving it alone) reddened
    this — added-line numbers shifted off by the deletion count. Restored, re-verified green."""
    diff = (
        "diff --git a/tests/x.py b/tests/x.py\n"
        "--- a/tests/x.py\n"
        "+++ b/tests/x.py\n"
        "@@ -10,2 +10,3 @@\n"
        " def test_a():\n"
        "-    assert 1 == 1\n"
        "+    assert 1 == 1\n"
        "+    assert 2 == 2\n"
    )
    assert parse_added_lines(diff) == {11, 12}


def test_parse_added_lines_on_a_brand_new_file():
    """A wholly new test file: every line is `+` under a `-0,0` hunk (verified against a real
    `git diff --cached -U0` on a newly `git add`-ed file, not assumed)."""
    diff = (
        "@@ -0,0 +1,2 @@\n"
        "+def test_new():\n"
        "+    assert True\n"
    )
    assert parse_added_lines(diff) == {1, 2}


def test_parse_added_lines_when_the_new_side_hunk_is_a_single_line():
    """Unified diff omits the `,count` when a side's hunk is exactly 1 line — real `git diff -U0`
    output for a single added line reads `@@ -2,0 +3 @@ def test_new():` (no `,1` on the `+3`, plus
    trailing context after the closing `@@`), verified against an actual `git diff`, not assumed.
    MUTATION: making the new-side count mandatory (`\\+(\\d+),(\\d+)` instead of
    `\\+(\\d+)(?:,(\\d+))?`) reddened this — the hunk header stopped matching at all, so the
    single added line was silently dropped. Restored, re-verified green."""
    diff = "@@ -2,0 +3 @@ def test_new():\n+    assert 1\n"
    assert parse_added_lines(diff) == {3}


def test_parse_added_lines_ignores_unchanged_context():
    """With `-U0` there is normally no context, but the parser must not choke if some appears
    (e.g. a differently-invoked diff). MUTATION: removing the `else: cur += 1` branch (only
    ever incrementing inside the `+` branch) reddened this — a context line after a hunk header
    no longer advanced `cur`, so the SECOND `+` line was mis-numbered."""
    diff = (
        "@@ -5,1 +5,2 @@\n"
        " def test_a():\n"
        "+    assert True\n"
    )
    assert parse_added_lines(diff) == {6}


# ── the new/edited orchestration: only touched lines count, escaped ones never do ───────────

def test_check_new_or_edited_only_flags_lines_the_diff_actually_added(monkeypatch, tmp_path):
    """End-to-end through `check_new_or_edited`, with `subprocess.run` faked the way this
    repo's own `check_plan.py` tests fake `git show` for `_review_can_fire_gate` (see that
    module's docstring: 'a sibling test monkeypatches subprocess.run'). Two functions in one
    file: only the one whose lines the diff marks as added should be reported.

    MUTATION: removing the `if any(fn["lineno"] <= ln <= fn["end_lineno"] for ln in added)`
    line-overlap check (reporting every unescaped pin in a touched FILE, not just touched
    LINES) reddened this — the untouched, pre-existing function started being reported too.
    Restored, re-verified green."""
    import scripts.check_test_source_pins as mod

    test_file = tmp_path / "tests" / "test_probe.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(_src("""
        import inspect
        from agents.market_intelligence import ep_detector

        def test_untouched_pin():
            assert "sort" in inspect.getsource(ep_detector.run_ep_scan)

        def test_newly_added_pin():
            assert "score" in inspect.getsource(ep_detector.run_ep_scan)
    """), encoding="utf-8")
    relpath = "tests/test_probe.py"

    # The new function occupies lines 7-8 (1-indexed) of the new file; nothing else changed.
    added_diff = (
        "@@ -5,0 +6,3 @@\n"
        "+\n"
        "+def test_newly_added_pin():\n"
        "+    assert \"score\" in inspect.getsource(ep_detector.run_ep_scan)\n"
    )

    def fake_run(args, cwd=None, capture_output=False, text=None, encoding=None, errors=None):
        class R:
            pass
        r = R()
        if args[:3] == ["git", "diff", "--quiet"]:
            r.returncode = 1               # something changed
        elif args[:3] == ["git", "diff", "--name-only"]:
            r.returncode = 0
            r.stdout = relpath + "\n"
        elif args[:3] == ["git", "diff", "-U0"]:
            r.returncode = 0
            r.stdout = added_diff
        else:
            raise AssertionError(f"unexpected git invocation: {args}")
        return r

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.setattr(mod, "REPO", tmp_path)

    violations = mod.check_new_or_edited(tmp_path)
    assert len(violations) == 1
    assert "test_newly_added_pin" in violations[0]
    assert "test_untouched_pin" not in violations[0]


def test_check_new_or_edited_skips_an_escaped_new_pin(monkeypatch, tmp_path):
    """The same new-function shape as above, but with a reviewed escape comment. MUTATION:
    removing the `if fn["escaped"]: continue` line in `check_new_or_edited` reddened this — an
    escaped, brand-new pin started failing the gate anyway, defeating the whole escape hatch.
    Restored, re-verified green."""
    import scripts.check_test_source_pins as mod

    test_file = tmp_path / "tests" / "test_probe2.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(_src("""
        import inspect
        from agents.market_intelligence import ep_detector

        def test_newly_added_pin():
            # source-pin-ok: no runtime seam exposes sort order, only source shows it
            assert "sort" in inspect.getsource(ep_detector.run_ep_scan)
    """), encoding="utf-8")
    relpath = "tests/test_probe2.py"
    added_diff = (
        "@@ -0,0 +1,6 @@\n"
        "+import inspect\n"
        "+from agents.market_intelligence import ep_detector\n"
        "+\n"
        "+def test_newly_added_pin():\n"
        "+    # source-pin-ok: no runtime seam exposes sort order, only source shows it\n"
        "+    assert \"sort\" in inspect.getsource(ep_detector.run_ep_scan)\n"
    )

    def fake_run(args, cwd=None, capture_output=False, text=None, encoding=None, errors=None):
        class R:
            pass
        r = R()
        if args[:3] == ["git", "diff", "--quiet"]:
            r.returncode = 1
        elif args[:3] == ["git", "diff", "--name-only"]:
            r.returncode = 0
            r.stdout = relpath + "\n"
        elif args[:3] == ["git", "diff", "-U0"]:
            r.returncode = 0
            r.stdout = added_diff
        else:
            raise AssertionError(f"unexpected git invocation: {args}")
        return r

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.setattr(mod, "REPO", tmp_path)

    assert mod.check_new_or_edited(tmp_path) == []


def test_check_new_or_edited_fails_open_when_git_is_unavailable(monkeypatch, tmp_path):
    """Same posture as `_review_can_fire_gate`: this runs in a pre-commit hook and must never be
    the reason a commit cannot be made. MUTATION: making the outer `try/except Exception` around
    the `--quiet` call re-raise instead of returning `None` reddened this (the test itself would
    error instead of observing a clean empty list). Restored, re-verified green."""
    import scripts.check_test_source_pins as mod

    def fake_run(*a, **k):
        raise FileNotFoundError("git not on PATH")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    assert mod.check_new_or_edited(tmp_path) == []


# ── the baseline file matches what the scanner finds RIGHT NOW ──────────────────────────────

def test_baseline_matches_the_live_scan():
    """A baseline that silently drifts from the scanner is worse than none — it would let a real
    regression through unremarked (rising count, nobody told) or manufacture false 'improvement'.
    MUTATION: this test itself IS the mutation-detector for that drift — hand-editing
    `test_source_pin_baseline.json`'s total to a different number while running this test
    reddened it immediately. Restored to the real scanned value before commit."""
    import json
    from pathlib import Path

    total, unescaped, per_file = scan_repo()
    baseline = json.loads(mod_path().read_text(encoding="utf-8"))
    assert baseline["total"] == total
    assert baseline["unescaped"] == unescaped
    assert baseline["per_file"] == per_file


def mod_path():
    from pathlib import Path
    import scripts.check_test_source_pins as mod
    return mod.BASELINE_PATH
