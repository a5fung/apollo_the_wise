"""Deployed-without-verify-claim gate in check_plan.py (operator 2026-08-09, the INVERSE of the
pending-verify gate, asked the same day).

The sibling gate (`_pending_verify_gate`, `tests/test_check_plan_pending_verify.py`) catches a task
whose text CLAIMS a pending verify while status lags `deployed`. Within hours it found #471 — but
the operator's next question named the other half of the gap: "a task that ships and claims NOTHING
is still invisible. No claim means no warning, so it can sit at `deployed` forever and never be
confirmed — or worse, be closed on 'it deployed fine'." A task at `deployed` means built-and-shipped
AWAITING PROOF; if the line names no observable, it can never honestly close.

ONE shared vocabulary, not a second divergent one: both gates match through `_verify_claim_body`
(meta-tag strip) + `_VERIFY_CLAIM_TRIGGER` — the exact trigger phrases the sibling gate already
tuned against the live board (VERIFY-LIVE / VERIFY-DUE / "NOT done until" / "must be confirmed" /
"confirm in prod", case-insensitive). This gate does not widen or re-tune it.

THE SUBTLE PART this gate must get right: a verify condition that is already SATISFIED — checkmark-
marked historical ("✅ VERIFY-LIVE DONE 6/18: ...") — must still count as "stated". The task named an
observable; it simply already fired. So this gate uses `_verify_claim_raw_matches` (ALL trigger
hits, historical + open), never the OPEN-only `_pending_verify_matches` the sibling gate uses.

Measured 2026-08-09 against the live 16 `deployed`-task board: 4 fire (#544 #525 #513 #539), all
pre-existing (WARN, not HARD-FAIL). Manual read of all 4 found each ALREADY states an observable —
just phrased outside the shared vocabulary's narrow trigger set (bare "VERIFY <date/day>:" without a
"-live"/"-due" suffix; past-tense "VERIFIED IN PROD" vs the regex's "confirm in prod"). That is a
finding about the shared vocabulary's recall on THIS direction, reported rather than silently fixed
by widening the trigger the sibling gate shipped and tuned this same morning (a separate, operator-
level decision — it would also change what the sibling gate matches). The FROZEN_* snippets below
are pinned verbatim from PLAN.md as of that measurement, mirroring the sibling test file's own
anti-loosening-pin idiom, so a future vocabulary change is a deliberate act, not an accident.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta

import scripts.check_plan as cp
from scripts.check_plan import (
    _deployed_no_verify_gate,
    _deployed_no_verify_violations,
    _verify_claim_raw_matches,
    parse,
)

TODAY = datetime.now(cp._OPERATOR_TZ).date()
FUTURE = (TODAY + timedelta(days=30)).isoformat()

# ── frozen board snippets, captured verbatim 2026-08-09 (see module docstring) ──────────────────
# All 4 are the FULL match-relevant excerpt of a real `deployed` task whose title carries NO hit of
# the shared trigger vocabulary anywhere — despite each one, read in full, actually stating a check.
FROZEN_544_NO_TRIGGER_HIT = (
    "▶ **VERIFY MONDAY:** theme engine 17:00 ET run (5 of the 10 sites) + the morning EP scan "
    "(extractor + catalyst grade) both clean. Close this task only when 1-6 are all confirmed IN PROD."
)
FROZEN_525_NO_TRIGGER_HIT = (
    "VERIFIED IN PROD RIGHT AFTER DEPLOY: `breaker[live]=0`, `breaker[paper]=0` against a threshold "
    "of 3 — the per-mode query runs and nothing tripped on the cutover (see "
    "docs/architecture/dual_account.md). DEPLOYED != VERIFIED — the verify is EVENT-GATED: the fix "
    "only demonstrably ACTS when a partial-exit failure or success occurs in one book while the "
    "other's breaker state differs."
)
FROZEN_513_NO_TRIGGER_HIT = (
    "DoD: a re-run of the 8/01 sweep renders in a message the operator can act on without pasting "
    "it anywhere, with both decisions above surfaced in the first block. [ok:2026-08-03->2026-09-01 "
    "- CLOSE rebump - EVENT-GATED on the monthly cadence. The rebuild is deployed and its tests "
    "pass; the sweep next FIRES 2026-09-01, so no earlier date can verify it.]"
)
FROZEN_539_NO_TRIGGER_HIT = (
    "▶ VERIFY 2026-08-08 (Sat morning, on tonight's 17:00 ET run): a theme that RETIRES tonight "
    "still has its `stage='Retired'` row in `mi_themes` tomorrow. Query: `SELECT name, theme_date, "
    "stage, source FROM mi_themes WHERE stage='Retired' AND theme_date='2026-08-07';`"
)


def test_frozen_board_snippets_have_zero_raw_trigger_hits():
    # documents the 2026-08-09 finding: these 4 real deployed tasks DO state a check, but not in the
    # shared vocabulary's exact idiom -> they are genuine hits for THIS gate today (see docstring).
    for snippet in (FROZEN_544_NO_TRIGGER_HIT, FROZEN_525_NO_TRIGGER_HIT,
                    FROZEN_513_NO_TRIGGER_HIT, FROZEN_539_NO_TRIGGER_HIT):
        assert _verify_claim_raw_matches(snippet) == [], snippet


# ── shared vocabulary: same trigger phrases as the sibling gate, not a second definition ─────────

def test_shares_trigger_vocabulary_with_the_pending_gate():
    for phrase in ("VERIFY-LIVE", "VERIFY-DUE", "verify-live", "NOT done until",
                   "must be confirmed", "confirm in prod"):
        assert _verify_claim_raw_matches(f"some prose {phrase} more prose"), phrase


def test_generic_verify_prose_never_matches():
    for prose in (
        "Opus-verified: setup NOT dead",
        "ETF% unverified — re-derive on clean data",
        "verified in git",
        "card-built Fable-reviewed",
        "the promote path verified ALREADY-LIVE under v1",
        "operator confirms Rank Flow reads correctly on the live URL",
        "confirms signal on next active close",
    ):
        assert _verify_claim_raw_matches(prose) == [], prose


def test_meta_tags_are_stripped_here_too_same_as_the_sibling_gate():
    # a mention that lives ENTIRELY inside an [ok:]/[blocked:]/[swept:]/[revalidated:] bracket is
    # meta-commentary about a past bump/sweep decision, not the task's own stated verify condition
    # -> does NOT count as "stated" for this gate either. One shared definition, not two.
    for tag in ("[ok:operator-CLOSE reconcile 7/17 — verify-live pending Monday market]",
                "[swept:2026-08-06:f92b — verify-live already checked, no change]",
                "[revalidated:2026-07-26 — verify-live confirmed stale-block]"):
        assert _verify_claim_raw_matches(tag) == [], tag


# ── the subtle requirement: a SATISFIED historical claim still counts as "stated" ────────────────

def test_checkmark_satisfied_historical_claim_still_counts_as_stated():
    # the exact opposite behavior of the sibling gate's `_pending_verify_matches`, which DROPS
    # checkmark-history on purpose. Here it must NOT be dropped: the task named an observable and
    # it already fired -> that IS a stated condition, not a gap.
    title = "✅ VERIFY-LIVE DONE 6/18 (deploy abc123): write-probe proved the insert path clean."
    assert _verify_claim_raw_matches(title), title
    tasks, perr = parse(f"## X\n- #9901 | {FUTURE} | deployed | {title}\n")
    assert perr == []
    assert _deployed_no_verify_violations(tasks) == []


def test_open_pending_claim_also_counts_as_stated_for_this_gate():
    # this gate only asks "is ANY condition stated", not "is it still open" — that question belongs
    # to the sibling gate. A still-open ▶ claim on a `deployed` task is not a violation of THIS gate.
    title = "▶ VERIFY-LIVE = tomorrow's run confirms the write path."
    tasks, perr = parse(f"## X\n- #9901 | {FUTURE} | deployed | {title}\n")
    assert perr == []
    assert _deployed_no_verify_violations(tasks) == []


def test_mixed_done_and_pending_still_counts_as_stated():
    title = ("✅ VERIFY-LIVE DONE 6/18: first half confirmed. REMAINING: deploy the rest -> "
             "verify-live 16:18 audit row -> close.")
    tasks, perr = parse(f"## X\n- #9901 | {FUTURE} | deployed | {title}\n")
    assert perr == []
    assert _deployed_no_verify_violations(tasks) == []


# ── the core violation: deployed + literally nothing ─────────────────────────────────────────────

def test_deployed_with_no_claim_at_all_is_a_violation():
    tasks, perr = parse(f"## X\n- #9901 | {FUTURE} | deployed | ship the widget, done.\n")
    assert perr == []
    viol = _deployed_no_verify_violations(tasks)
    assert len(viol) == 1 and viol[0]["id"] == 9901


def test_deployed_with_claim_only_inside_meta_tag_is_still_a_violation():
    title = "ship the widget. [ok:rebump — verify-live pending, unrelated to this fix]"
    tasks, perr = parse(f"## X\n- #9901 | {FUTURE} | deployed | {title}\n")
    assert perr == []
    viol = _deployed_no_verify_violations(tasks)
    assert len(viol) == 1 and viol[0]["id"] == 9901


def test_non_deployed_status_is_never_a_violation_of_this_gate_regardless_of_claim():
    for status in ("pending", "in_progress", "blocked"):
        tasks, perr = parse(f"## X\n- #9901 | {FUTURE} | {status} | ship the widget, done.\n")
        assert perr == []
        assert _deployed_no_verify_violations(tasks) == [], status


# ── the frozen real-board fixtures wired end-to-end ───────────────────────────────────────────────

def test_frozen_board_snippets_fire_as_deployed_no_verify_violations():
    for i, snippet in enumerate((FROZEN_544_NO_TRIGGER_HIT, FROZEN_525_NO_TRIGGER_HIT,
                                  FROZEN_513_NO_TRIGGER_HIT, FROZEN_539_NO_TRIGGER_HIT)):
        tid = 9910 + i
        tasks, perr = parse(f"## X\n- #{tid} | {FUTURE} | deployed | {snippet}\n")
        assert perr == []
        viol = _deployed_no_verify_violations(tasks)
        assert len(viol) == 1 and viol[0]["id"] == tid, snippet


# ── hard-fail (touched this commit) vs warn (pre-existing, unchanged since HEAD:PLAN.md) ────────

def _fake_git_show(prior_plan_text: str | None, ok: bool = True):
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
    monkeypatch.setattr(subprocess, "run", _fake_git_show("## X\n"))
    tasks, perr = parse(f"## X\n- #9901 | {FUTURE} | deployed | ship the widget, done.\n")
    assert perr == []
    errors: list = []
    _deployed_no_verify_gate(tasks, errors)
    assert len(errors) == 1
    assert "#9901" in errors[0] and "states NO verify condition" in errors[0]


def test_modified_line_this_commit_hard_fails(monkeypatch):
    old = f"## X\n- #9901 | {FUTURE} | deployed | ship the widget, still needs polish.\n"
    monkeypatch.setattr(subprocess, "run", _fake_git_show(old))
    new_title = "ship the widget, done — polish landed."
    tasks, perr = parse(f"## X\n- #9901 | {FUTURE} | deployed | {new_title}\n")
    assert perr == []
    errors: list = []
    _deployed_no_verify_gate(tasks, errors)
    assert len(errors) == 1 and "#9901" in errors[0]


def test_unchanged_line_since_head_warns_not_hard_fails(monkeypatch, capsys):
    plan_text = f"## X\n- #9901 | {FUTURE} | deployed | ship the widget, done.\n"
    monkeypatch.setattr(subprocess, "run", _fake_git_show(plan_text))
    tasks, perr = parse(plan_text)
    assert perr == []
    errors: list = []
    _deployed_no_verify_gate(tasks, errors)
    assert errors == []   # WARN, not a commit-blocker
    out = capsys.readouterr().out
    assert "WARN" in out and "#9901" in out and "pre-existing" in out


def test_status_change_to_deployed_alone_counts_as_touched(monkeypatch):
    prior = f"## X\n- #9901 | {FUTURE} | in_progress | ship the widget, done.\n"
    monkeypatch.setattr(subprocess, "run", _fake_git_show(prior))
    tasks, perr = parse(f"## X\n- #9901 | {FUTURE} | deployed | ship the widget, done.\n")
    assert perr == []
    errors: list = []
    _deployed_no_verify_gate(tasks, errors)
    assert len(errors) == 1 and "#9901" in errors[0]


def test_git_unavailable_fails_open_to_warn_never_hard(monkeypatch, capsys):
    def _boom(cmd, **kwargs):
        raise FileNotFoundError("git not on PATH")
    monkeypatch.setattr(subprocess, "run", _boom)
    tasks, perr = parse(f"## X\n- #9901 | {FUTURE} | deployed | ship the widget, done.\n")
    assert perr == []
    errors: list = []
    _deployed_no_verify_gate(tasks, errors)
    assert errors == [], "a git/infra hiccup must never HARD-fail a commit (fail-open, like the other git gates)"
    assert "WARN" in capsys.readouterr().out


def test_no_head_commit_yet_fails_open_to_warn(monkeypatch, capsys):
    monkeypatch.setattr(subprocess, "run", _fake_git_show(None, ok=False))
    tasks, perr = parse(f"## X\n- #9901 | {FUTURE} | deployed | ship the widget, done.\n")
    assert perr == []
    errors: list = []
    _deployed_no_verify_gate(tasks, errors)
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
    plan_text = f"## X\n- #9901 | {FUTURE} | deployed | ship the widget, done.\n"
    monkeypatch.setattr(subprocess, "run", _fake_git_show(plan_text))
    rc = _run_main(monkeypatch, tmp_path, plan_text)
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "WARN" in out and "#9901" in out


def test_main_exits_one_when_violation_is_new_this_commit(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(subprocess, "run", _fake_git_show("## X\n"))
    plan_text = f"## X\n- #9901 | {FUTURE} | deployed | ship the widget, done.\n"
    rc = _run_main(monkeypatch, tmp_path, plan_text)
    out = capsys.readouterr().out
    assert rc == 1
    assert "#9901" in out and "states NO verify condition" in out
