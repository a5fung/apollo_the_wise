"""STALE-DEPLOY (2026-09-05): the gap every other check_plan.py surface misses — a task that
sat `deployed` for weeks behind a self-chosen verify-date ETA that just hasn't arrived yet.
VERIFY-DUE only fires once that ETA is reached; the ETA is a date the AGENT wrote, not a
measurement, so nothing stops it hiding an old ship behind a distant date. This surface derives
"how long has it ACTUALLY been deployed" from git instead — the commit that flipped the task's
PLAN.md line to `deployed` — and is independent of the ETA entirely.

Pins: the flip date comes from git, not the line's own prose; a cosmetic edit to an already-
`deployed` line (an appended note, an ETA rebump) does not re-date it; a deployed -> back ->
deployed id is dated by the SECOND flip; an id git cannot place is UNDATEABLE, never guessed;
a live-vs-history status disagreement also routes to UNDATEABLE (the consistency check); a
FRESH `swept:` marker suppresses `aged` but never `undateable`; the whole thing is a --today
SURFACE, never a commit gate.
"""
from datetime import date, datetime, timedelta

import scripts.check_plan as cp
from scripts.check_plan import (
    _STALE_DEPLOY_DAYS,
    _deploy_dates_from_history,
    parse,
    stale_deploys,
    sweep_fingerprint,
)
# Reuse the ONE `_run_main` helper (mirrors tests/test_check_plan_growth_gate.py's precedent for
# borrowing it) rather than hand-rolling a second copy of "run main() against a throwaway PLAN.md".
from tests.test_check_plan_deployed import _run_main

TODAY = datetime.now(cp._OPERATOR_TZ).date()
FUTURE = (TODAY + timedelta(days=60)).isoformat()


def _sha(n: int) -> str:
    return f"{n:040x}"


def _history_text(entries: list[tuple[str, str, list[str]]]) -> str:
    """Fake `git log -p --reverse --format=%H%x00%cd --date=short` stdout.

    `entries` is OLDEST FIRST (matching --reverse): each item is
    (sha, iso-date, [full '+'-prefixed PLAN.md line, ...]) — only the '+' lines matter to the
    parser under test, so the fake diff carries no '-' side or real hunk headers.
    """
    out = []
    for sha, d, plus_lines in entries:
        block = [f"{sha}\x00{d}", "diff --git a/PLAN.md b/PLAN.md", "--- a/PLAN.md",
                 "+++ b/PLAN.md", "@@ -1,1 +1,1 @@"]
        block.extend(plus_lines)
        out.append("\n".join(block))
    return "\n".join(out) + "\n"


class _Result:
    def __init__(self, returncode, stdout):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


def _fake_history_git(history_text: str | None, ok: bool = True, raise_instead: bool = False):
    """Stands in for `git log -p --reverse ... -- PLAN.md` only — every OTHER subprocess.run
    call (`_own_commits_touching_code`'s `git log --all ...` inside the --today path, etc.)
    gets a harmless empty-success result, mirroring `_fake_git_show` in
    test_check_plan_pending_verify.py so this fake cannot break an unrelated gate."""
    def _run(cmd, **kwargs):
        if raise_instead:
            raise FileNotFoundError("git not on PATH")
        if cmd[:2] == ["git", "log"] and "-p" in cmd and "--reverse" in cmd:
            return _Result(0 if ok else 1, history_text or "")
        return _Result(0, "")
    return _run


# ── _deploy_dates_from_history: the git-history walk itself ───────────────────────────────────

def test_flip_recorded_at_the_correct_commit_date(monkeypatch):
    history = _history_text([
        (_sha(1), "2026-08-01", ["+- #9901 | 2026-08-15 | in_progress | build the widget"]),
        (_sha(2), "2026-08-10", ["+- #9901 | 2026-08-15 | deployed | widget shipped — verify Friday"]),
    ])
    monkeypatch.setattr(cp.subprocess, "run", _fake_history_git(history))
    since, last_status = _deploy_dates_from_history()
    assert since[9901] == date(2026, 8, 10)
    assert last_status[9901] == "deployed"


def test_appended_note_and_eta_rebump_while_deployed_keeps_the_original_flip_date(monkeypatch):
    history = _history_text([
        (_sha(1), "2026-08-01", ["+- #9901 | 2026-08-15 | in_progress | build the widget"]),
        (_sha(2), "2026-08-10", ["+- #9901 | 2026-08-15 | deployed | widget shipped — verify Friday"]),
        # a later session appends a note AND rebumps the ETA — the line is a full replace in the
        # diff (PLAN.md tasks are one giant line each) but the STATUS token is unchanged.
        (_sha(3), "2026-08-20", ["+- #9901 | 2026-09-01 | deployed | widget shipped — verify "
                                  "Friday >> swept 08-20, still waiting on Monday's run [b1]"]),
    ])
    monkeypatch.setattr(cp.subprocess, "run", _fake_history_git(history))
    since, _ = _deploy_dates_from_history()
    assert since[9901] == date(2026, 8, 10), (
        "an edit that keeps the status at `deployed` must not look like a fresh flip")


def test_deployed_back_to_in_progress_and_deployed_again_dates_to_the_SECOND_flip(monkeypatch):
    history = _history_text([
        (_sha(1), "2026-07-01", ["+- #9901 | 2026-07-15 | deployed | first attempt shipped"]),
        (_sha(2), "2026-07-05", ["+- #9901 | 2026-07-20 | in_progress | reverted, bug found"]),
        (_sha(3), "2026-08-10", ["+- #9901 | 2026-08-20 | deployed | re-shipped — verify Monday"]),
    ])
    monkeypatch.setattr(cp.subprocess, "run", _fake_history_git(history))
    since, last_status = _deploy_dates_from_history()
    assert since[9901] == date(2026, 8, 10), "must date the CURRENT deployed streak, not the first ever"
    assert last_status[9901] == "deployed"


def test_git_failure_returns_none_none_not_a_throw(monkeypatch):
    monkeypatch.setattr(cp.subprocess, "run", _fake_history_git(None, ok=False))
    since, last_status = _deploy_dates_from_history()
    assert since is None and last_status is None


def test_git_raising_returns_none_none_not_a_throw(monkeypatch):
    monkeypatch.setattr(cp.subprocess, "run", _fake_history_git(None, raise_instead=True))
    since, last_status = _deploy_dates_from_history()
    assert since is None and last_status is None


# ── stale_deploys: thresholding, undateable routing, sweep suppression ────────────────────────

def _task(tid, status="deployed", eta=None, title="shipped — verify Monday"):
    return {"id": tid, "eta": date.fromisoformat(eta) if eta else None,
            "status": status, "title": title, "project": "Ops", "line": 1}


def test_aged_past_threshold_surfaces_sorted_oldest_first(monkeypatch):
    old_date = (TODAY - timedelta(days=_STALE_DEPLOY_DAYS + 20)).isoformat()
    older_date = (TODAY - timedelta(days=_STALE_DEPLOY_DAYS + 40)).isoformat()
    # entries must be oldest-first (matches --reverse), so #9902 (older_date) comes first.
    history = _history_text([
        (_sha(1), older_date, ["+- #9902 | 2026-12-01 | deployed | shipped — verify Tuesday"]),
        (_sha(2), old_date, ["+- #9901 | 2026-12-01 | deployed | shipped — verify Monday"]),
    ])
    monkeypatch.setattr(cp.subprocess, "run", _fake_history_git(history))
    tasks = [_task(9901), _task(9902)]
    aged, undateable = stale_deploys(tasks, TODAY)
    assert undateable == []
    assert [t["id"] for t, _, _ in aged] == [9902, 9901], "oldest (largest age) first"


def test_below_threshold_does_not_surface(monkeypatch):
    recent = (TODAY - timedelta(days=_STALE_DEPLOY_DAYS - 1)).isoformat()
    history = _history_text([(_sha(1), recent,
                              ["+- #9901 | 2026-12-01 | deployed | shipped — verify Monday"])])
    monkeypatch.setattr(cp.subprocess, "run", _fake_history_git(history))
    aged, undateable = stale_deploys([_task(9901)], TODAY)
    assert aged == [] and undateable == []


def test_exactly_at_threshold_surfaces(monkeypatch):
    """`age < threshold: continue` means age == threshold DOES fire — pin the boundary the
    "14+ days" header wording promises."""
    at_threshold = (TODAY - timedelta(days=_STALE_DEPLOY_DAYS)).isoformat()
    history = _history_text([(_sha(1), at_threshold,
                              ["+- #9901 | 2026-12-01 | deployed | shipped — verify Monday"])])
    monkeypatch.setattr(cp.subprocess, "run", _fake_history_git(history))
    aged, _ = stale_deploys([_task(9901)], TODAY)
    assert len(aged) == 1 and aged[0][0]["id"] == 9901


def test_never_deployed_in_history_is_undateable(monkeypatch):
    history = _history_text([(_sha(1), "2026-07-01",
                              ["+- #9901 | 2026-08-01 | in_progress | still building"])])
    monkeypatch.setattr(cp.subprocess, "run", _fake_history_git(history))
    aged, undateable = stale_deploys([_task(9901)], TODAY)
    assert aged == []
    assert [t["id"] for t in undateable] == [9901]


def test_git_unavailable_makes_every_deployed_task_undateable_not_silently_dropped(monkeypatch):
    monkeypatch.setattr(cp.subprocess, "run", _fake_history_git(None, ok=False))
    aged, undateable = stale_deploys([_task(9901), _task(9902)], TODAY)
    assert aged == []
    assert {t["id"] for t in undateable} == {9901, 9902}, (
        "a git/infra hiccup must never silently hide staleness — everything currently "
        "`deployed` becomes undateable instead of vanishing")


def test_history_disagreeing_with_the_live_board_is_undateable_not_trusted(monkeypatch):
    """The consistency check: the walk's own idea of #9901's current status must agree with
    what's actually on the board right now. If the replayed history says #9901 ended up
    `in_progress` (e.g. a non-linear merge, or an uncommitted flip this session) while the live
    board says `deployed`, the derived date cannot be trusted for this id."""
    old_date = (TODAY - timedelta(days=_STALE_DEPLOY_DAYS + 20)).isoformat()
    history = _history_text([
        (_sha(1), old_date, ["+- #9901 | 2026-08-15 | deployed | shipped — verify Monday"]),
        (_sha(2), old_date, ["+- #9901 | 2026-08-16 | in_progress | actually reverted"]),
    ])
    monkeypatch.setattr(cp.subprocess, "run", _fake_history_git(history))
    # live board (what parse() would hand stale_deploys) still says deployed
    aged, undateable = stale_deploys([_task(9901)], TODAY)
    assert aged == []
    assert [t["id"] for t in undateable] == [9901]


def test_fresh_swept_marker_suppresses_aged(monkeypatch):
    old_date = (TODAY - timedelta(days=_STALE_DEPLOY_DAYS + 20)).isoformat()
    history = _history_text([(_sha(1), old_date,
                              ["+- #9901 | 2026-12-01 | deployed | shipped — verify Monday"])])
    monkeypatch.setattr(cp.subprocess, "run", _fake_history_git(history))
    body = "shipped — verify Monday"
    fp = sweep_fingerprint(body)
    swept_title = f"{body} [swept:{TODAY.isoformat()}:{fp}]"
    aged, _ = stale_deploys([_task(9901, title=swept_title)], TODAY)
    assert aged == [], "a fresh swept: marker must quiet the surface, exactly like LIKELY-BUILT"


def test_expired_swept_marker_does_not_suppress(monkeypatch):
    old_date = (TODAY - timedelta(days=_STALE_DEPLOY_DAYS + 20)).isoformat()
    history = _history_text([(_sha(1), old_date,
                              ["+- #9901 | 2026-12-01 | deployed | shipped — verify Monday"])])
    monkeypatch.setattr(cp.subprocess, "run", _fake_history_git(history))
    body = "shipped — verify Monday"
    fp = sweep_fingerprint(body)
    stale_marker_date = (TODAY - timedelta(days=cp._SWEEP_MAX_AGE + 1)).isoformat()
    swept_title = f"{body} [swept:{stale_marker_date}:{fp}]"
    aged, _ = stale_deploys([_task(9901, title=swept_title)], TODAY)
    assert len(aged) == 1, "an aged-out swept: marker must not buy indefinite silence"


def test_wrong_fingerprint_swept_marker_does_not_suppress(monkeypatch):
    old_date = (TODAY - timedelta(days=_STALE_DEPLOY_DAYS + 20)).isoformat()
    history = _history_text([(_sha(1), old_date,
                              ["+- #9901 | 2026-12-01 | deployed | shipped — verify Monday"])])
    monkeypatch.setattr(cp.subprocess, "run", _fake_history_git(history))
    swept_title = f"shipped — verify Monday [swept:{TODAY.isoformat()}:dead]"
    aged, _ = stale_deploys([_task(9901, title=swept_title)], TODAY)
    assert len(aged) == 1, "a line edited since the sweep must void the marker, same as LIKELY-BUILT"


def test_undateable_is_never_suppressible_by_swept(monkeypatch):
    """`swept:` settles a JUDGEMENT about content; it cannot manufacture a date git doesn't
    have. An undateable id must keep showing even with a fresh marker."""
    history = _history_text([(_sha(1), "2026-07-01",
                              ["+- #9901 | 2026-08-01 | in_progress | still building"])])
    monkeypatch.setattr(cp.subprocess, "run", _fake_history_git(history))
    body = "shipped — verify Monday"
    fp = sweep_fingerprint(body)
    swept_title = f"{body} [swept:{TODAY.isoformat()}:{fp}]"
    aged, undateable = stale_deploys([_task(9901, title=swept_title)], TODAY)
    assert aged == []
    assert [t["id"] for t in undateable] == [9901]


def test_non_deployed_tasks_are_never_considered():
    aged, undateable = stale_deploys([_task(9901, status="in_progress")], TODAY)
    assert aged == [] and undateable == []


# ── --today wiring: header, count, (none), and the surface-not-gate guarantee ──────────────────

def test_today_prints_none_when_nothing_is_stale(monkeypatch, tmp_path, capsys):
    history = _history_text([(_sha(1), TODAY.isoformat(),
                              ["+- #9901 | " + FUTURE + " | deployed | shipped — verify Monday"])])
    monkeypatch.setattr(cp.subprocess, "run", _fake_history_git(history))
    plan = f"## Ops\n- #9901 | {FUTURE} | deployed | shipped — verify Monday\n"
    rc = _run_main(monkeypatch, tmp_path, plan, argv=["--today"])
    out = capsys.readouterr().out
    assert rc == 0
    sec = out.split("-- STALE-DEPLOY")[1].split("-- LIKELY-BUILT")[0]
    assert "(0)" in sec.splitlines()[0] or sec.splitlines()[0].strip().startswith("(0)")
    assert "(none)" in sec


def test_today_lists_stale_task_with_age_and_date(monkeypatch, tmp_path, capsys):
    old_date = TODAY - timedelta(days=_STALE_DEPLOY_DAYS + 5)
    history = _history_text([(_sha(1), old_date.isoformat(),
                              [f"+- #9901 | {FUTURE} | deployed | shipped — verify Monday"])])
    monkeypatch.setattr(cp.subprocess, "run", _fake_history_git(history))
    plan = f"## Ops\n- #9901 | {FUTURE} | deployed | shipped — verify Monday\n"
    rc = _run_main(monkeypatch, tmp_path, plan, argv=["--today"])
    out = capsys.readouterr().out
    assert rc == 0
    sec = out.split("-- STALE-DEPLOY")[1].split("-- LIKELY-BUILT")[0]
    assert "#9901" in sec
    assert str(old_date) in sec
    assert f"{_STALE_DEPLOY_DAYS + 5}d ago" in sec
    assert "SURFACE, not a gate" in sec


def test_today_shows_undateable_bucket(monkeypatch, tmp_path, capsys):
    history = _history_text([(_sha(1), "2026-07-01",
                              [f"+- #9901 | {FUTURE} | in_progress | never mentioned as deployed"])])
    monkeypatch.setattr(cp.subprocess, "run", _fake_history_git(history))
    plan = f"## Ops\n- #9901 | {FUTURE} | deployed | shipped — verify Monday\n"
    rc = _run_main(monkeypatch, tmp_path, plan, argv=["--today"])
    out = capsys.readouterr().out
    assert rc == 0
    sec = out.split("-- STALE-DEPLOY")[1].split("-- LIKELY-BUILT")[0]
    assert "UNDATEABLE" in sec and "#9901" in sec


def test_plain_validate_never_fails_on_a_very_stale_deploy(monkeypatch, tmp_path, capsys):
    """HARD RULE from the card: this must be a SURFACE, never a commit-blocking gate. A 100-day-
    old deployed task with a future (non-past) verify-date ETA must still pass plain `main([])`
    cleanly — the plain validate path must never even LOOK at deploy age."""
    old_date = TODAY - timedelta(days=100)
    history = _history_text([(_sha(1), old_date.isoformat(),
                              [f"+- #9901 | {FUTURE} | deployed | shipped — verify Monday"])])
    monkeypatch.setattr(cp.subprocess, "run", _fake_history_git(history))
    plan = f"## Ops\n- #9901 | {FUTURE} | deployed | shipped — verify Monday\n"
    rc = _run_main(monkeypatch, tmp_path, plan)  # no argv -> plain validate
    out = capsys.readouterr().out
    assert rc == 0
    assert "STALE-DEPLOY" not in out, "the plain validate path must not even print this surface"


def test_the_today_surface_actually_calls_stale_deploys():
    """Guard the guard: main()'s --today branch must route through stale_deploys(), not a
    hand-rolled inline copy of the same logic."""
    import inspect

    src = inspect.getsource(cp.main)
    assert "stale_deploys(" in src
