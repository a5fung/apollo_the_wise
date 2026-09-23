"""The pre-push suite must grade the COMMIT BEING PUSHED, not whatever is on disk.

FOUND 2026-09-17, by a red CI email. The hook ran `pytest tests/ -q` in place, so it graded the
working tree. That morning the tree carried test fixes that were not yet committed — a separate
gate (#653's source-pin ratchet) was blocking the commit — while `HEAD` was `14710eb4`, nine tests
red. The hook saw a green tree, let the red commit through, and CI rejected it.

That is the exact class the hook's own header says it exists to close ("a commit could pass locally,
get pushed, and red CI"), one layer up from the 2026-08-06 data-file gap it already documents. A
gate that reads a different artefact than the one it is protecting is not a gate.

THE FIX: when the tree does not match the pushed SHA, run the suite in a throwaway worktree checked
out at that SHA. That is also strictly MORE faithful to CI, which builds from a clean checkout with
no untracked files — the in-place run reported 8,442/9-skipped vs 8,444/7-skipped precisely because
untracked local files were absent.

⚠ These tests EXECUTE the real shell out of `.githooks/pre-push` — the decision block is extracted
verbatim and run — so they cannot pass against a re-implementation that has drifted. They do NOT
run the suite itself; the end-to-end proof was done by hand on the day (the hook blocked `14710eb4`
with nine failures while the tree was green, and passed a matching tree in a temp worktree).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / ".githooks" / "pre-push"

_DECISION = re.compile(
    r"^_tree_matches_push=0\n(.*?)^if \[ \"\$_tree_matches_push\" -eq 0 \]; then$",
    re.S | re.M,
)


def _decision_block() -> str:
    m = _DECISION.search(HOOK.read_text(encoding="utf-8"))
    assert m, (
        "could not extract the tree-vs-pushed-SHA decision from .githooks/pre-push. Fix the "
        "extraction rather than deleting this test: without it nothing checks that the hook grades "
        "the commit it is about to push."
    )
    return m.group(0)


def _decide(push_sha: str, dirty: bool, untracked: bool) -> str:
    """Run the hook's OWN decision block against stubbed git state; return WORKTREE or IN_PLACE."""
    if shutil.which("bash") is None:  # pragma: no cover
        pytest.skip("bash unavailable")
    git_stub = "\n".join([
        "git() {",
        '  if [ "$1" = diff ]; then return %d; fi' % (1 if dirty else 0),
        '  if [ "$1" = "ls-files" ]; then %s; return 0; fi' % (
            'echo some_untracked_file.py' if untracked else 'true'),
        "  return 0",
        "}",
    ])
    script = "\n".join([
        "set -uo pipefail",
        git_stub,
        f'PUSH_SHA="{push_sha}"',
        _decision_block(),
        '  echo WORKTREE',
        "else",
        '  echo IN_PLACE',
        "fi",
    ])
    r = subprocess.run(["bash", "-c", script], cwd=REPO, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, f"extracted decision block failed: {r.stderr[-500:]}"
    return r.stdout.strip().splitlines()[-1]


def test_a_dirty_tree_is_tested_as_the_pushed_commit():
    """THE BUG. Uncommitted changes mean the tree is not what the remote receives."""
    assert _decide("abc1234", dirty=True, untracked=False) == "WORKTREE"


def test_untracked_files_alone_still_force_the_worktree():
    """CI has no untracked files. A tree that differs from CI only by untracked files can pass
    locally on a fixture CI will not have — the same wrong-artefact error in a quieter form."""
    assert _decide("abc1234", dirty=False, untracked=True) == "WORKTREE"


def test_a_clean_tree_matching_the_pushed_sha_runs_in_place():
    """The other half: the fix must not pay for a worktree on every ordinary push, where in-place
    and the worktree are the same bytes."""
    assert _decide("abc1234", dirty=False, untracked=False) == "IN_PLACE"


def test_an_unknown_push_sha_never_runs_in_place():
    """Fail-safe: if the refs could not be read, PUSH_SHA is empty and we must NOT claim the tree
    represents it. A safety gate must not fail open (the hook's own stated posture)."""
    assert _decide("", dirty=False, untracked=False) == "WORKTREE"


def test_the_hook_still_blocks_on_a_failing_suite():
    # source-pin-ok: the exit path runs the real 8k-test suite, so it cannot be exercised here
    # without a multi-minute run. Pinning the block-and-exit text is the only check available; the
    # end-to-end proof was done by hand on 2026-09-17 against the known-red 14710eb4.
    src = HOOK.read_text(encoding="utf-8")
    assert 'if ! ( cd "$_SUITE_DIR" && "$PY_BIN" -m pytest tests/ -q ); then' in src, (
        "the suite no longer runs in the chosen directory — it is grading the working tree again"
    )
    assert "exit 1" in src.split('pytest tests/ -q ); then')[1][:400], "a failing suite must block"


def test_the_temp_worktree_is_always_cleaned_up():
    # source-pin-ok: cleanup is a shell trap on EXIT; there is no seam to observe from Python
    # without running the whole hook. A leaked worktree per push would accumulate silently.
    src = HOOK.read_text(encoding="utf-8")
    assert "trap _cleanup_wt EXIT" in src, "no EXIT trap — a blocked push would leak its worktree"
    assert "git worktree remove --force" in src
