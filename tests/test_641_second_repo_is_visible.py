"""A task that ships in the OTHER repo must be visible to this board.

WHY (2026-09-11, #641). Every git-derived surface in `check_plan.py` — SHIPPED-BUT-UNRECORDED,
LIKELY-BUILT, the deploy-age scan — reads THIS repository's log. The dashboard lives in
`portfolio-app2`, so a task that ships there fires none of them. **That is how #555 sat five days
after shipping**, found in the end by a card running `git log` by hand rather than by any gate, and
it is why #553 and #561 were still sitting open with their work already committed.

⚠ THE MATCHER IS LOOSER FOR THE SECOND REPO AND THE NUMBER IS THE REASON. In this repo, matching
ANY `#N` mention flags 31 of 84 tasks — subjects cross-reference ids constantly — so `_OWN_COMMIT`
anchors at the start of the subject. Measured on portfolio-app2 the day this shipped: **182
commits, 15 mentioning an id, 11 distinct ids, and 9 of the 11 are already-closed tasks so they
flag nothing.** The anchored rule would have missed #555 itself, whose commit reads
*"#553/#555 — a cohort identity model, not a tenth guard"*.
"""
import subprocess

import pytest

from scripts.check_plan import (
    PLAN,
    _sidecar_commits_touching_tasks,
    _sidecar_repos,
    parse,
)


def _has_sidecar():
    return bool(_sidecar_repos())


def test_it_never_raises_when_the_second_repo_is_absent(tmp_path, monkeypatch):
    """The laptop and the prod box do not have it. A board-hygiene surface must fail OPEN."""
    monkeypatch.setenv("APOLLO_SIDECAR_REPOS", str(tmp_path / "nope"))
    assert _sidecar_repos() == []
    assert _sidecar_commits_touching_tasks({1, 2, 3}) == {}


def test_a_non_git_directory_is_skipped_not_scanned(tmp_path, monkeypatch):
    (tmp_path / "plain").mkdir()
    monkeypatch.setenv("APOLLO_SIDECAR_REPOS", str(tmp_path / "plain"))
    assert _sidecar_repos() == []


def test_an_empty_id_set_short_circuits():
    assert _sidecar_commits_touching_tasks(set()) == {}


def test_a_mention_anywhere_in_the_subject_counts(tmp_path, monkeypatch):
    """THE #555 CASE. Its commit names two ids mid-subject; an anchored matcher misses both."""
    repo = tmp_path / "side"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "app.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m",
                    "a cohort identity model, not a tenth guard (#553/#555)"], cwd=repo, check=True)
    monkeypatch.setenv("APOLLO_SIDECAR_REPOS", str(repo))
    got = _sidecar_commits_touching_tasks({553, 555, 999})
    assert set(got) == {553, 555}, "a mid-subject id was missed — this is the #555 failure"
    assert 999 not in got
    assert got[553][0] == "side"


def test_only_ids_we_asked_about_come_back(tmp_path, monkeypatch):
    repo = tmp_path / "side2"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "a.py").write_text("1\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "#111 and #222 both"], cwd=repo, check=True)
    monkeypatch.setenv("APOLLO_SIDECAR_REPOS", str(repo))
    assert set(_sidecar_commits_touching_tasks({111})) == {111}


@pytest.mark.skipif(not _has_sidecar(), reason="the dashboard repo is not on this machine")
def test_the_real_board_sees_the_two_tasks_that_were_invisible():
    """THE REGRESSION, on the real population: #553 and #561 shipped in portfolio-app2 and no
    surface here could see them. If this ever returns nothing, the scan has gone dark."""
    tasks = parse(PLAN.read_text(encoding="utf-8"))[0]
    got = _sidecar_commits_touching_tasks({t["id"] for t in tasks})
    assert got, "the second-repo scan found nothing at all — it has gone dark"
    assert {553, 561} & set(got), f"expected the known pair, got {sorted(got)}"


@pytest.mark.skipif(not _has_sidecar(), reason="the dashboard repo is not on this machine")
def test_it_does_not_flag_the_whole_board():
    """The looser matcher earns its keep only if it stays quiet. 9 of the 11 ids it can match are
    closed tasks; if this ever balloons, the calibration has stopped holding."""
    tasks = parse(PLAN.read_text(encoding="utf-8"))[0]
    got = _sidecar_commits_touching_tasks({t["id"] for t in tasks})
    assert len(got) <= 6, f"second-repo scan is flagging {len(got)} open tasks — recalibrate"
