"""Pending-verify-claim gate in check_plan.py (operator 2026-08-09, the #167 lesson).

Operator caught task #167's OWN TEXT reading "VERIFY-LIVE — the flip is NOT done until this is
confirmed" while its status sat at `in_progress` — nothing mechanical would ever have surfaced it,
because the existing surfaces (VERIFY-DUE / LIKELY-BUILT) key off STATUS, and status was never
flipped to `deployed`. "I'll verify it" was prose, and prose drifted (caught twice, same shape).

This gate makes the CLAIM and the STATUS the same fact: a task whose own text asserts a
verification is still open must already be `deployed`, or the line HARD-FAILS (if touched this
commit) / WARNS (if pre-existing, so it can never go quiet).

The core difficulty (per the ticket): the SAME phrase ("VERIFY-LIVE") is used for both an OPEN
claim and a CLOSED historical checkpoint ("✅ VERIFY-LIVE DONE 6/18: ..."), sometimes on the SAME
line. Measured 2026-08-09 against the real 84-line board: 19 lines carry the raw vocabulary; after
the two suppressions (meta-bracket strip, ✅-checkmark lookback), 5 are real open violations
(#548 #184 #354 #471 #452) and #261 / #327 are correctly suppressed — 0 false positives against
the operator's own manual read of all 84 lines.

The FROZEN_* snippets below are copied verbatim from PLAN.md as it stood 2026-08-09 — pinned as
literal strings so this test does NOT depend on the live file (which will keep changing) and so a
future loosening of the classifier is caught even after the real board's #548/#184/etc. get fixed
and removed. This is the anti-loosening pin the operator asked for in the ticket.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta

import scripts.check_plan as cp
from scripts.check_plan import (
    _pending_verify_gate,
    _pending_verify_matches,
    _pending_verify_violations,
    parse,
)

TODAY = datetime.now(cp._OPERATOR_TZ).date()
FUTURE = (TODAY + timedelta(days=30)).isoformat()

# ── frozen board snippets, captured verbatim 2026-08-09 (see module docstring) ──────────────────
FROZEN_548_PENDING = (
    "write it up; do NOT write live code before Q1 answers. ▶ **VERIFY-LIVE for the flip "
    "(this is what closes defect 2, not the deploy):** the next partial")
FROZEN_184_PENDING = (
    "wired into the 15-min reconcile; card-built Fable-reviewed; VERIFY-LIVE Mon 7/6 = first "
    "reconcile cycles write coverage_drift audit rows, expect quiet")
FROZEN_354_PENDING = (
    "xes; old 2-col index dropped · execution/orch untouched). ▶ VERIFY-LIVE = tonight's "
    "17:35 ET consolidation job writes the first `entry_mode='confirm'`")
FROZEN_471_PENDING = (
    "trigger — needs operator naming) OR Fri 7/17 ~5PM ET nightly. VERIFY-LIVE checkpoints on "
    "the armed run: (1) `theme_dominant_split_eligible` audit event")
FROZEN_452_PENDING = (
    "ite 2972. REMAINING = deploy (rides the next batch w/ T5) + verify-live = the hook logs on "
    "the next entry evaluation. >> STAGE-1 BUILT 7/16 eve (inlin")
FROZEN_261_SUPPRESSED_BRACKET = (
    "ssion, not an EOD roll] [ok:operator-CLOSE reconcile 7/17 — verify-live pending Monday "
    "market / remaining-deliverable / event-gated] >> RE-HOMED to #4")
FROZEN_327_SUPPRESSED_HISTORICAL = (
    " (alt) for later settlement. ALL SHADOW (zero execution). ✅ VERIFY-LIVE DONE 6/18 (deploy "
    "b8245ec, both): write-probe proved the insert path (insert✓ ")


# ── trigger vocabulary: fires on the codebase's own idiom, not generic English "verify" ─────────

def test_all_candidate_trigger_phrases_match():
    for phrase in ("VERIFY-LIVE", "VERIFY-DUE", "verify-live", "NOT done until",
                   "must be confirmed", "confirm in prod"):
        assert _pending_verify_matches(f"some prose {phrase} more prose"), phrase


def test_generic_verify_prose_never_matches():
    # high-frequency narrative uses of plain English "verify" on the real board — none of these
    # are a live-verify claim, and false-firing on them is exactly the noise this gate must avoid.
    for prose in (
        "Opus-verified: setup NOT dead",
        "ETF% unverified — re-derive on clean data",
        "verified in git",
        "card-built Fable-reviewed",
        "the promote path verified ALREADY-LIVE under v1",
        "operator confirms Rank Flow reads correctly on the live URL",
        "confirms signal on next active close",
    ):
        assert _pending_verify_matches(prose) == [], prose


# ── the two suppressions, pinned against the real board's own shapes ────────────────────────────

def test_frozen_548_184_354_471_452_fire_as_pending():
    for snippet in (FROZEN_548_PENDING, FROZEN_184_PENDING, FROZEN_354_PENDING,
                    FROZEN_471_PENDING, FROZEN_452_PENDING):
        assert _pending_verify_matches(snippet), snippet


def test_frozen_261_meta_bracket_is_suppressed():
    # #261's ONLY "verify-live" mention lives entirely inside an `[ok:...]` rebump-justification
    # tag — meta-commentary about a PAST bump decision, not a live claim about the task today.
    assert _pending_verify_matches(FROZEN_261_SUPPRESSED_BRACKET) == []


def test_frozen_327_checkmark_history_is_suppressed():
    # #327 carries THREE "✅ VERIFY-LIVE DONE" checkpoints and zero open ones.
    assert _pending_verify_matches(FROZEN_327_SUPPRESSED_HISTORICAL) == []


def test_other_meta_tags_also_suppressed():
    for tag in ("[blocked:HTF Phase-3 shadow N-accrual → #397 GO/NO-GO gate 7/18; "
                "verify-live ongoing]",
                "[swept:2026-08-06:f92b — verify-live already checked, no change]",
                "[revalidated:2026-07-26 — verify-live confirmed stale-block]"):
        assert _pending_verify_matches(tag) == [], tag


def test_collision_guard_intervening_pending_arrow_cancels_earlier_checkmark():
    # a done note immediately followed by a NEW open claim must NOT be false-suppressed by the
    # earlier checkmark — the exact shape #452/#471 carry (one done sub-checkpoint, one live one).
    hits = _pending_verify_matches("✅ built fine; ▶ VERIFY-LIVE = tomorrow's run confirms it")
    assert hits, "the intervening ▶ must cancel the earlier ✅ and let the new claim fire"


def test_task_with_both_done_and_pending_still_fires_on_the_pending_one():
    title = ("✅ VERIFY-LIVE DONE 6/18: first half confirmed. REMAINING: deploy the rest → "
             "verify-live 16:18 audit row → close.")
    hits = _pending_verify_matches(title)
    assert hits and "16:18" in hits[0]


def test_pure_checkmark_only_line_fires_nothing():
    title = "✅ VERIFY-LIVE DONE 6/18 (deploy abc123): write-probe proved the insert path clean."
    assert _pending_verify_matches(title) == []


# ── _pending_verify_violations: status gates the verdict, not the match alone ───────────────────

def test_deployed_status_is_never_a_violation_even_with_pending_language():
    tasks, perr = parse(f"## X\n- #9901 | {FUTURE} | deployed | {FROZEN_548_PENDING}\n")
    assert perr == []
    assert _pending_verify_violations(tasks) == []


def test_non_deployed_status_with_pending_claim_is_a_violation():
    for status in ("pending", "in_progress", "blocked"):
        tasks, perr = parse(f"## X\n- #9901 | {FUTURE} | {status} | {FROZEN_548_PENDING}\n")
        assert perr == []
        viol = _pending_verify_violations(tasks)
        assert len(viol) == 1 and viol[0]["id"] == 9901, status


def test_no_trigger_no_violation_regardless_of_status():
    tasks, perr = parse(f"## X\n- #9901 | {FUTURE} | in_progress | build the widget -> tests green\n")
    assert perr == []
    assert _pending_verify_violations(tasks) == []


# ── the #167 fixture: the exact bug that motivated this gate ─────────────────────────────────────

def test_would_have_caught_167():
    title = ("v1.0 promote-path flip — verified ALREADY-LIVE under v1; (3) signed. "
             "▶ **VERIFY-LIVE — the flip is NOT done until this is confirmed:** the next "
             "weekday nightly run (Mon 2026-08-10 ~17:00 ET, en...")
    tasks, perr = parse(f"## Live-money cutover\n- #167 | 2026-09-08 | in_progress | {title}\n")
    assert perr == []
    viol = _pending_verify_violations(tasks)
    assert len(viol) == 1 and viol[0]["id"] == 167


# ── hard-fail (touched this commit) vs warn (pre-existing, unchanged since HEAD:PLAN.md) ────────

def _fake_git_show(prior_plan_text: str | None, ok: bool = True):
    """Stand in for `git show HEAD:PLAN.md` only; every other subprocess.run call (the OTHER
    git-touching gates run earlier in main()) gets a harmless empty-success result so this fake
    cannot break `_rebump_gate`/`_shipped_pending_gate` if a future test exercises main() whole."""
    class _Result:
        def __init__(self, returncode, stdout):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    def _run(cmd, **kwargs):
        if cmd[:3] == ["git", "show", "HEAD:PLAN.md"]:
            return _Result(0 if ok else 1, prior_plan_text or "")
        return _Result(0, "")
    return _run


def test_new_line_this_commit_hard_fails(monkeypatch):
    # #9901 absent from HEAD:PLAN.md entirely -> a brand-new line -> HARD.
    monkeypatch.setattr(subprocess, "run", _fake_git_show("## X\n"))
    tasks, perr = parse(f"## X\n- #9901 | {FUTURE} | in_progress | {FROZEN_548_PENDING}\n")
    assert perr == []
    errors: list = []
    _pending_verify_gate(tasks, errors)
    assert len(errors) == 1
    assert "#9901" in errors[0] and "set status=deployed" in errors[0] and "ETA=" in errors[0]


def test_modified_line_this_commit_hard_fails(monkeypatch):
    old = f"## X\n- #9901 | {FUTURE} | in_progress | build the widget, nothing verify-related yet\n"
    monkeypatch.setattr(subprocess, "run", _fake_git_show(old))
    new_title = FROZEN_548_PENDING
    tasks, perr = parse(f"## X\n- #9901 | {FUTURE} | in_progress | {new_title}\n")
    assert perr == []
    errors: list = []
    _pending_verify_gate(tasks, errors)
    assert len(errors) == 1 and "#9901" in errors[0]


def test_unchanged_line_since_head_warns_not_hard_fails(monkeypatch, capsys):
    plan_text = f"## X\n- #9901 | {FUTURE} | in_progress | {FROZEN_548_PENDING}\n"
    monkeypatch.setattr(subprocess, "run", _fake_git_show(plan_text))
    tasks, perr = parse(plan_text)
    assert perr == []
    errors: list = []
    _pending_verify_gate(tasks, errors)
    assert errors == []   # WARN, not a commit-blocker
    out = capsys.readouterr().out
    assert "WARN" in out and "#9901" in out and "pre-existing" in out


def test_status_change_alone_counts_as_touched(monkeypatch):
    # title identical, but status just moved (e.g. blocked -> in_progress) without the claim being
    # resolved -> still an active edit to this line this commit, so it HARD-fails too.
    prior = f"## X\n- #9901 | {FUTURE} | blocked | {FROZEN_548_PENDING}\n"
    monkeypatch.setattr(subprocess, "run", _fake_git_show(prior))
    tasks, perr = parse(f"## X\n- #9901 | {FUTURE} | in_progress | {FROZEN_548_PENDING}\n")
    assert perr == []
    errors: list = []
    _pending_verify_gate(tasks, errors)
    assert len(errors) == 1 and "#9901" in errors[0]


def test_git_unavailable_fails_open_to_warn_never_hard(monkeypatch, capsys):
    def _boom(cmd, **kwargs):
        raise FileNotFoundError("git not on PATH")
    monkeypatch.setattr(subprocess, "run", _boom)
    tasks, perr = parse(f"## X\n- #9901 | {FUTURE} | in_progress | {FROZEN_548_PENDING}\n")
    assert perr == []
    errors: list = []
    _pending_verify_gate(tasks, errors)
    assert errors == [], "a git/infra hiccup must never HARD-fail a commit (fail-open, like the other git gates)"
    assert "WARN" in capsys.readouterr().out


def test_no_head_commit_yet_fails_open_to_warn(monkeypatch, capsys):
    # `git show` returning non-zero (e.g. PLAN.md not yet committed) mirrors _rebump_gate's own
    # "no committed PLAN yet" case.
    monkeypatch.setattr(subprocess, "run", _fake_git_show(None, ok=False))
    tasks, perr = parse(f"## X\n- #9901 | {FUTURE} | in_progress | {FROZEN_548_PENDING}\n")
    assert perr == []
    errors: list = []
    _pending_verify_gate(tasks, errors)
    assert errors == []
    assert "WARN" in capsys.readouterr().out


# ── main() integration: the plain gate exits 0 on a pre-existing-only violation, 1 on a new one ──

def _run_main(monkeypatch, tmp_path, plan_text: str):
    plan = tmp_path / "PLAN.md"
    plan.write_text(plan_text, encoding="utf-8")
    monkeypatch.setattr(cp, "PLAN", plan)
    monkeypatch.setattr(cp, "SNAPSHOT", tmp_path / "no_snapshot.json")
    monkeypatch.setattr(cp, "BASELINE", tmp_path / "baseline.json")
    return cp.main([])


def test_main_exits_zero_when_only_pre_existing_violations(monkeypatch, tmp_path, capsys):
    plan_text = f"## X\n- #9901 | {FUTURE} | in_progress | {FROZEN_548_PENDING}\n"
    monkeypatch.setattr(subprocess, "run", _fake_git_show(plan_text))
    rc = _run_main(monkeypatch, tmp_path, plan_text)
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "WARN" in out and "#9901" in out


def test_main_exits_one_when_violation_is_new_this_commit(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(subprocess, "run", _fake_git_show("## X\n"))
    plan_text = f"## X\n- #9901 | {FUTURE} | in_progress | {FROZEN_548_PENDING}\n"
    rc = _run_main(monkeypatch, tmp_path, plan_text)
    out = capsys.readouterr().out
    assert rc == 1
    assert "#9901" in out and "set status=deployed" in out
