"""EXPECT / DONE-WHEN gate in check_plan.py (operator 2026-09-13).

THE ASK, verbatim: "we should make this standard practice, write down expectations to be verified
live so we know how to treat what we see in real live data, what to do, and when we're done." The
shape came from a PRE-REGISTRATION written before a theme change went live (docs/analysis/
cross_industry_themes_2026-09-13.md): expected effects against today's baseline, plus a stopping
rule. Same reason every rule in this repo is mechanical, not prose: prose reconciles have never
held here.

`EXPECT:` = what we expect in live data, against today's baseline.
`DONE-WHEN:` = the stopping rule — when we stop watching and call it settled.
Escape: `EXPECT-NA: <reason>` (>=12 chars) for a task with genuinely nothing to expect.

SCOPED (operator's own framing, same shape as `_review_can_fire_gate` / Gate 7's source-pin
check): 23 `deployed` tasks were already on the board the day this shipped, none carrying
`EXPECT:`. Hard-failing all 23 would be a wall in front of the very next commit, so this BLOCKS
only a `deployed` line that is NEW or EDITED this commit (detected via `_diff_added_task_lines`,
the SAME differ `--audit-new` already used) and SURFACES the rest as a non-blocking backlog count.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta

import scripts.check_plan as cp
from scripts.check_plan import (
    PLAN,
    _diff_added_task_lines,
    _expect_done_when_gate,
    expect_done_when_for,
    expect_na_reason,
    parse,
)

TODAY = datetime.now(cp._OPERATOR_TZ).date()
FUTURE = (TODAY + timedelta(days=30)).isoformat()


class _Result:
    def __init__(self, stdout: str, returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = ""


def _fake_diff(diff_text: str):
    """A fake `subprocess.run` that answers `git diff origin/main -- PLAN.md` with `diff_text`
    and no-ops everything else — mirrors the `_fake_git_show` idiom the sibling verify-claim
    gate tests already use, just for a `git diff` (textual) call instead of `git show`."""
    def _run(cmd, **kwargs):
        if cmd[:2] == ["git", "diff"]:
            return _Result(diff_text)
        return _Result("")
    return _run


def _diff_adding(line: str) -> str:
    """A minimal unified diff whose only real content is one ADDED task line."""
    return (
        "diff --git a/PLAN.md b/PLAN.md\n"
        "--- a/PLAN.md\n"
        "+++ b/PLAN.md\n"
        "@@ -1,1 +1,1 @@\n"
        f"+{line}\n"
    )


# ── expect_done_when_for: the extractor ──────────────────────────────────────────────────────

def test_both_present_and_long_enough_is_accepted():
    title = ("shipped the theme change. EXPECT: cross-industry themes surface at the SAME rate "
             "seen today (baseline 4/week). DONE-WHEN: two full weekly cycles pass with no "
             "false-positive theme, or one clear false positive appears.")
    got = expect_done_when_for(title)
    assert got is not None
    expect_text, done_when_text = got
    assert "baseline" in expect_text
    assert "two full weekly cycles" in done_when_text


def test_missing_expect_returns_none():
    title = "shipped it. DONE-WHEN: two weekly cycles pass with no false-positive theme at all."
    assert expect_done_when_for(title) is None


def test_missing_done_when_returns_none():
    title = ("shipped the theme change. EXPECT: cross-industry themes surface at the same rate "
             "seen today, baseline four per week measured Monday.")
    assert expect_done_when_for(title) is None


def test_a_bare_expect_with_no_real_content_is_rejected():
    # "EXPECT: yes" carries no baseline and no observable — same floor close_bar_for applies to DoD.
    assert expect_done_when_for("shipped it. EXPECT: yes. DONE-WHEN: soon.") is None


def test_a_mention_inside_a_meta_tag_does_not_count():
    # a rebump/sweep tag is commentary about a past decision, never a live statement of THIS
    # task's own expectation — same substrate `close_bar_for` and the verify-claim gates share.
    title = ("shipped it. [ok:2026-09-01->2026-09-08 - EXPECT: this would have cleared the old "
             "gate too, DONE-WHEN: whatever the prior reviewer decided]")
    assert expect_done_when_for(title) is None


def test_bold_markdown_form_is_accepted():
    title = ("shipped it. **EXPECT:** the fallback rate stays under the 3% seen in the last 30 "
             "days of live trading, measured against that same baseline window. **DONE-WHEN:** "
             "two full weeks pass with the rate still under that same threshold throughout.")
    assert expect_done_when_for(title) is not None


def test_parenthetical_retrofit_form_is_accepted():
    # mirrors close_bar_for's DoD pattern: `EXPECT (added <date>): ...` is what you write when
    # retrofitting a criterion onto an OLD line, and this exact shape went silently unrecognized
    # during the LAST retrofit (five real DoDs, 2026-09-10) — must not go missing twice.
    title = ("shipped weeks ago, nothing stated at the time. **EXPECT (added 2026-09-14):** the "
             "fallback rate stays under the 3% seen in the last 30 days of live trading, same "
             "baseline window. **DONE-WHEN (added 2026-09-14):** two full weeks pass with the "
             "rate still under that same threshold throughout.")
    assert expect_done_when_for(title) is not None


# ── expect_na_reason: the escape ─────────────────────────────────────────────────────────────

def test_expect_na_with_a_real_reason_is_accepted():
    assert expect_na_reason("pure docs cleanup. EXPECT-NA: no behavior change, pure revert.")


def test_expect_na_too_short_is_rejected():
    assert expect_na_reason("pure docs cleanup. EXPECT-NA: n/a.") is None


def test_expect_na_absent_is_none():
    assert expect_na_reason("shipped the widget, nothing else said.") is None


# ── _diff_added_task_lines: the one differ, reused by --audit-new and this gate ──────────────

def test_diff_added_task_lines_parses_a_new_plus_line(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_diff(
        _diff_adding(f"- #9901 | {FUTURE} | deployed | ship the widget, done.")))
    found = _diff_added_task_lines("origin/main")
    assert found == [{"id": 9901, "title": "ship the widget, done."}]


def test_diff_added_task_lines_empty_diff_is_empty_list(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_diff(""))
    assert _diff_added_task_lines("origin/main") == []


def test_diff_added_task_lines_git_failure_is_none(monkeypatch):
    def _raise(cmd, **kwargs):
        raise FileNotFoundError("git not found")
    monkeypatch.setattr(subprocess, "run", _raise)
    assert _diff_added_task_lines("origin/main") is None


def test_default_cached_false_diffs_the_working_tree(monkeypatch):
    seen = []
    def _run(cmd, **kwargs):
        seen.append(cmd)
        return _Result("")
    monkeypatch.setattr(subprocess, "run", _run)
    _diff_added_task_lines("origin/main")
    assert seen and "--cached" not in seen[0]


def test_cached_true_diffs_the_staged_index(monkeypatch):
    seen = []
    def _run(cmd, **kwargs):
        seen.append(cmd)
        return _Result("")
    monkeypatch.setattr(subprocess, "run", _run)
    _diff_added_task_lines("origin/main", cached=True)
    assert seen and "--cached" in seen[0]


# ── the gate itself: HARD-FAIL touched, backlog pre-existing ─────────────────────────────────

def test_new_deployed_task_without_expect_hard_fails(monkeypatch, capsys):
    line = f"- #9901 | {FUTURE} | deployed | ship the widget, done."
    monkeypatch.setattr(subprocess, "run", _fake_diff(_diff_adding(line)))
    tasks, perr = parse(f"## X\n{line}\n")
    assert perr == []
    errors: list = []
    _expect_done_when_gate(tasks, errors)
    assert len(errors) == 1
    assert "#9901" in errors[0]
    assert "EXPECT" in errors[0] and "DONE-WHEN" in errors[0]


def test_new_deployed_task_with_expect_and_done_when_passes(monkeypatch):
    title = ("ship the widget, done. EXPECT: error rate stays at the same near-zero level seen "
             "in the last 30 days of production traffic. DONE-WHEN: one full week passes with "
             "the rate still at that same near-zero level throughout.")
    line = f"- #9901 | {FUTURE} | deployed | {title}"
    monkeypatch.setattr(subprocess, "run", _fake_diff(_diff_adding(line)))
    tasks, perr = parse(f"## X\n{line}\n")
    assert perr == []
    errors: list = []
    _expect_done_when_gate(tasks, errors)
    assert errors == []


def test_new_deployed_task_with_expect_na_passes(monkeypatch):
    title = "pure revert of the broken change, nothing else touched. EXPECT-NA: pure revert, no measurable live effect expected."
    line = f"- #9901 | {FUTURE} | deployed | {title}"
    monkeypatch.setattr(subprocess, "run", _fake_diff(_diff_adding(line)))
    tasks, perr = parse(f"## X\n{line}\n")
    assert perr == []
    errors: list = []
    _expect_done_when_gate(tasks, errors)
    assert errors == []


def test_new_deployed_task_with_thin_expect_na_still_hard_fails(monkeypatch):
    # "n/a" is not a reason — same floor as source-pin-ok / can_fire_missing elsewhere in this repo.
    title = "ship the widget, done. EXPECT-NA: n/a."
    line = f"- #9901 | {FUTURE} | deployed | {title}"
    monkeypatch.setattr(subprocess, "run", _fake_diff(_diff_adding(line)))
    tasks, perr = parse(f"## X\n{line}\n")
    assert perr == []
    errors: list = []
    _expect_done_when_gate(tasks, errors)
    assert len(errors) == 1 and "#9901" in errors[0]


def test_pre_existing_deployed_task_without_expect_does_not_fail_but_is_counted(monkeypatch, capsys):
    # diff is EMPTY -> this task line was not touched this commit -> WARN-shaped (no hard error),
    # but it must be counted in the printed backlog line.
    line = f"- #9902 | {FUTURE} | deployed | ship the widget, done long ago, never revisited."
    monkeypatch.setattr(subprocess, "run", _fake_diff(""))
    tasks, perr = parse(f"## X\n{line}\n")
    assert perr == []
    errors: list = []
    _expect_done_when_gate(tasks, errors)
    assert errors == []
    out = capsys.readouterr().out
    assert "1 pre-existing" in out and "backlog" in out.lower()


def test_git_unavailable_fails_open_and_counts_as_backlog_not_error(monkeypatch, capsys):
    def _raise(cmd, **kwargs):
        raise FileNotFoundError("git not found")
    monkeypatch.setattr(subprocess, "run", _raise)
    line = f"- #9903 | {FUTURE} | deployed | ship the widget, done."
    tasks, perr = parse(f"## X\n{line}\n")
    assert perr == []
    errors: list = []
    _expect_done_when_gate(tasks, errors)
    assert errors == []   # never block a commit on a git/infra hiccup
    out = capsys.readouterr().out
    assert "1 pre-existing" in out


def test_the_gate_diffs_the_staged_index_not_the_working_tree(monkeypatch):
    # a pre-commit gate must judge what is ABOUT to be committed (the staged index), not an
    # unstaged working-tree edit that will not actually be part of this commit — the same reason
    # `_close_evidence_gate` uses `git diff --cached origin/main -- PLAN.md`.
    seen = []
    def _run(cmd, **kwargs):
        seen.append(cmd)
        return _Result("")
    monkeypatch.setattr(subprocess, "run", _run)
    line = f"- #9907 | {FUTURE} | deployed | ship the widget, done."
    tasks, perr = parse(f"## X\n{line}\n")
    assert perr == []
    errors: list = []
    _expect_done_when_gate(tasks, errors)
    assert seen and any("--cached" in cmd for cmd in seen)


def test_non_deployed_status_never_triggers_regardless_of_touched(monkeypatch):
    for status in ("pending", "in_progress", "blocked"):
        line = f"- #9904 | {FUTURE} | {status} | ship the widget, done."
        monkeypatch.setattr(subprocess, "run", _fake_diff(_diff_adding(line)))
        tasks, perr = parse(f"## X\n{line}\n")
        assert perr == []
        errors: list = []
        _expect_done_when_gate(tasks, errors)
        assert errors == [], status


def test_compliant_deployed_task_is_never_counted_in_backlog(monkeypatch, capsys):
    title = ("ship the widget, done. EXPECT: error rate stays at the same near-zero level seen "
             "in the last 30 days of production traffic. DONE-WHEN: one full week passes with "
             "the rate still at that same near-zero level throughout.")
    line = f"- #9905 | {FUTURE} | deployed | {title}"
    monkeypatch.setattr(subprocess, "run", _fake_diff(""))   # untouched, but already compliant
    tasks, perr = parse(f"## X\n{line}\n")
    assert perr == []
    errors: list = []
    _expect_done_when_gate(tasks, errors)
    assert errors == []
    out = capsys.readouterr().out
    assert "0 pre-existing" in out


# ── the real board: stays green, and the printed backlog matches a manual recount ────────────

def test_the_real_board_stays_green_and_backlog_matches_a_manual_count(monkeypatch, capsys):
    """Deliberately does NOT hardcode the current backlog count (23 the day this shipped) — that
    number moves every time an unrelated task closes or a new one ships, and pinning it here would
    fail the suite on work that has nothing to do with this gate. Instead this proves the two
    invariants the operator actually asked for: the real board does not hard-fail, and the printed
    backlog count is exactly the deployed tasks with neither a bar nor a real EXPECT-NA reason.
    """
    monkeypatch.setattr(subprocess, "run", _fake_diff(""))   # nothing touched this commit
    tasks, perr = parse(PLAN.read_text(encoding="utf-8"))
    assert perr == []
    manual_backlog = [t for t in tasks if t["status"] == "deployed"
                      and expect_done_when_for(t["title"]) is None
                      and expect_na_reason(t["title"]) is None]
    errors: list = []
    _expect_done_when_gate(tasks, errors)
    assert errors == [], errors
    out = capsys.readouterr().out
    assert f"{len(manual_backlog)} pre-existing" in out
