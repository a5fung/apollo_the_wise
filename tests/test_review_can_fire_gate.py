"""A new or edited gated review must record that it CAN fire — before it is trusted.

WHY (operator 2026-09-09): *"how do we safeguard from this in future, that's a lot of bad review
conditions. you've built all on them, they all suffer from defects"* — after eleven reviews were
found reading zero for five different reasons, every one invisible at creation and invisible for
56-70 days afterwards:

  * a predicate naming a column that does not exist (#617's `reached_4r`)
  * an audit event emitted NOWHERE, so the count could never leave zero
  * a column declared DEFAULT FALSE and never SET
  * a threshold outside the metric's entire observed range — and that range itself measured on a
    CENSORED table whose write condition WAS the threshold
  * a predicate counting trades from a rule that had already been replaced

The detectors shipped that day find a bad gate LATE. This is the front half, and it asks the author
the five questions rather than checking the answers — which is the only honest thing a gate can do
about a question like "is this threshold sane".

⚠ The gate is scoped to reviews ADDED or CHANGED versus origin/main; the 153 existing ones are a
standing backlog reported by `operator_asks.py --audit`, not a wall in front of every commit.

EXTENDED 2026-09-19 (#669, operator 2026-09-16: *"So many wrong info and action from review, this
needs to be cleaned up to avoid so much wasted resource and wrong info"*). Six failures in ONE day
and only one of them was a review that could not fire — the others FIRED and pointed at the wrong
work: a predicate counting rows its action could not act on, a method reading a broken instrument,
a measure straddling a criteria change in a table the method (not the cohort) read. Two more
questions, same shape: `population_actionable` and `instrument_trusted`. The gate cannot check the
answers; it forces them to be written down, which is what stopped the 09-09 class.
"""
import subprocess
from pathlib import PosixPath

import pytest

import scripts.check_plan as cp
from scripts.check_plan import (
    _CAN_FIRE_ACTION_KEYS, _CAN_FIRE_KEYS, _review_can_fire_gate, _reviews_by_id, can_fire_missing,
)


_FULL = {k: "a real sentence about what was actually checked here" for k in _CAN_FIRE_KEYS}
_ORIGINAL_FIVE = {k: _FULL[k] for k in _CAN_FIRE_KEYS if k not in _CAN_FIRE_ACTION_KEYS}


def _yaml(**over):
    import yaml
    r = {"review_id": "probe", "status": "pending", "predicate_sql": "SELECT 1",
         "threshold": 5, "earliest_review_date": "2026-10-01"}
    r.update(over)
    return yaml.safe_dump({"reviews": [r]})


def test_the_seven_questions_are_the_seven_failures_seen():
    """Pin the vocabulary — five ways a review turned out unable to fire (2026-09-09) and two ways
    a review that CAN fire still sent us at the wrong work (2026-09-16, #669)."""
    assert set(_CAN_FIRE_KEYS) == {
        "predicate_runs", "nonzero_possible", "lane_live",
        "threshold_vs_observed", "era_scoped",
        "population_actionable", "instrument_trusted"}
    assert set(_CAN_FIRE_ACTION_KEYS) == {"population_actionable", "instrument_trusted"}
    assert set(_CAN_FIRE_ACTION_KEYS) < set(_CAN_FIRE_KEYS), "the action keys are a subset"


def test_the_original_five_alone_are_now_too_thin():
    """A block that answered the 2026-09-09 questions but not the 2026-09-16 ones is reported
    missing exactly those two — the shared `can_fire_missing` is what `--audit` prints, so this
    is the backlog's own definition. RED-PROVEN: dropping the two keys from `_CAN_FIRE_KEYS`
    makes `missing` empty and this fails."""
    assert can_fire_missing(_ORIGINAL_FIVE) == list(_CAN_FIRE_ACTION_KEYS)
    assert can_fire_missing(_FULL) == []


def test_a_review_parses_out_of_the_yaml_by_id():
    got = _reviews_by_id(_yaml(review_id="alpha"))
    assert "alpha" in got and got["alpha"]["threshold"] == 5


def test_unparseable_yaml_degrades_to_empty_rather_than_raising():
    """This runs in a pre-commit hook — it must never be the reason a commit cannot be made."""
    assert _reviews_by_id("{{{ not yaml") == {}


def test_the_live_file_still_parses():
    """Cheap canary: the one edit made while building this gate broke the file once."""
    import pathlib
    got = _reviews_by_id(pathlib.Path("data_gated_reviews.yaml").read_text(encoding="utf-8"))
    assert len(got) > 100


def test_the_review_fixed_while_building_this_carries_its_evidence():
    """`chart_reading_review_cycle` was 100% SQL comment — a folded `--` swallowed its SELECT.

    Found by `operator_asks.py --audit` on its first run, which is the outcome the tool was
    built for. It is pinned here because a folded scalar will do this again to someone.
    """
    import pathlib
    r = _reviews_by_id(pathlib.Path("data_gated_reviews.yaml").read_text(encoding="utf-8"))[
        "chart_reading_review_cycle"]
    assert "--" not in r["predicate_sql"], "a `--` comment is back inside a folded scalar"
    assert r["predicate_sql"].strip().upper().startswith("SELECT")
    assert set(r["can_fire"]) == set(_CAN_FIRE_KEYS)


def test_no_open_review_has_a_predicate_that_is_pure_comment():
    """The whole class, not just the one instance — cheap to check across the file."""
    import pathlib
    revs = _reviews_by_id(pathlib.Path("data_gated_reviews.yaml").read_text(encoding="utf-8"))
    def _survives_comments(sql: str) -> bool:
        """A `--` comments out the rest of ITS LINE. So the SELECT survives iff some line has it
        before any `--`. On a FOLDED scalar (`>-`) every line becomes one, which is why a comment
        there swallows the statement — that is the whole bug, and the reason this is per-line."""
        return any("select" in ln.split("--")[0].lower() for ln in sql.splitlines())

    bad = [rid for rid, r in revs.items()
           if str(r.get("status", "")).lower() not in ("done", "closed", "retired", "superseded")
           and isinstance(r.get("predicate_sql"), str)
           and "select" in r["predicate_sql"].lower()
           and not _survives_comments(r["predicate_sql"])]
    assert not bad, f"predicate is entirely inside a `--` comment: {bad}"


# ── the gate itself, exercised (nothing did before 2026-09-19) ───────────────────────────────
#
# `_review_can_fire_gate` reads two things: `git show origin/main:data_gated_reviews.yaml` (the
# base) and `REVIEWS_YAML.read_text()` (the working copy). The base is faked through
# `subprocess.run`, the same idiom the verify-claim gate tests use. The working copy cannot be
# pointed at a tmp file — the gate's first line refuses any path that is not the repo's own — so
# it is injected through a PosixPath subclass that compares EQUAL to the real path and only
# overrides `read_text`. Reading the registry is a DATA file, never a source pin.


class _Result:
    def __init__(self, stdout: str, returncode: int = 0):
        self.stdout, self.returncode, self.stderr = stdout, returncode, ""


def _fake_git(base_yaml: str, changed: bool = True):
    def _run(cmd, **kwargs):
        if cmd[:3] == ["git", "diff", "--quiet"]:
            return _Result("", 1 if changed else 0)      # rc 1 = the file changed
        if cmd[:2] == ["git", "show"]:
            return _Result(base_yaml, 0)
        return _Result("", 0)
    return _run


class _Working(PosixPath):
    """The repo's own registry path, with the working-copy TEXT swapped in."""
    _text = ""

    def read_text(self, *a, **k):        # noqa: D401
        return type(self)._text


def _arm(monkeypatch, base_yaml: str, working_yaml: str, changed: bool = True):
    monkeypatch.setattr(subprocess, "run", _fake_git(base_yaml, changed))
    w = _Working(cp.REPO / "data_gated_reviews.yaml")
    type(w)._text = working_yaml
    monkeypatch.setattr(cp, "REVIEWS_YAML", w)


def test_an_edited_review_answering_only_the_original_five_fails_naming_the_two(monkeypatch):
    """The 2026-09-16 class: a review whose can_fire proves it CAN fire, but says nothing about
    whether the rows it counts are rows the action can act on, or what instrument the action
    reads. RED-PROVEN: removing `population_actionable` / `instrument_trusted` from
    `_CAN_FIRE_KEYS` leaves `errors` empty and this fails."""
    base = _yaml(threshold=5, can_fire=_ORIGINAL_FIVE)
    edited = _yaml(threshold=9, can_fire=_ORIGINAL_FIVE)       # threshold moved = edited
    _arm(monkeypatch, base, edited)
    errors: list = []
    _review_can_fire_gate(errors)
    assert len(errors) == 1, errors
    assert "`probe`" in errors[0]
    for k in _CAN_FIRE_ACTION_KEYS:
        assert k in errors[0], f"the error must name the missing key {k}"
    assert "rows the action can ACT on" in errors[0]        # the hint says what to write


def test_an_untouched_review_is_never_blocked_only_counted(monkeypatch, capsys):
    """Same entry, byte-identical to origin/main, missing the two new keys: no error — it is the
    surfaced backlog, and the gate prints its count. RED-PROVEN: making the untouched branch
    fall through to the check turns this into an error."""
    same = _yaml(can_fire=_ORIGINAL_FIVE)
    _arm(monkeypatch, same, same)
    errors: list = []
    _review_can_fire_gate(errors)
    assert errors == []
    out = capsys.readouterr().out
    assert "backlog: 1 open review(s)" in out, out


def test_a_full_seven_key_block_passes_and_is_not_backlog(monkeypatch, capsys):
    base = _yaml(threshold=5, can_fire=_FULL)
    edited = _yaml(threshold=9, can_fire=_FULL)
    _arm(monkeypatch, base, edited)
    errors: list = []
    _review_can_fire_gate(errors)
    assert errors == []
    assert "backlog: 0 open review(s)" in capsys.readouterr().out


def test_closing_a_review_as_done_is_not_proposing_one(monkeypatch, capsys):
    """`status: done` is the registry's documented closed status (yaml header: pending | done |
    deferred) and the gate's own comment says "closing one is not proposing one" — but before
    2026-09-19 only `closed`/`retired`/`superseded` were skipped, so flipping a can_fire-less
    review to `done` would have failed the commit. RED-PROVEN: dropping "done" from the skip
    tuple makes this produce an error."""
    base = _yaml(status="pending")                    # never had a can_fire block
    closed = _yaml(status="done", closed_on="2026-09-19", outcome="answered: not chatty")
    _arm(monkeypatch, base, closed)
    errors: list = []
    _review_can_fire_gate(errors)
    assert errors == []
    assert "backlog: 0 open review(s)" in capsys.readouterr().out, "a closed review is not backlog"


def test_an_untouched_file_short_circuits_before_any_yaml_is_read(monkeypatch, capsys):
    """`git diff --quiet` rc 0 = nothing to judge; the gate returns before `git show` or the
    working copy is touched (the 230 ms it used to cost every commit). No print either — the
    backlog count belongs to `--audit` on those runs."""
    _arm(monkeypatch, _yaml(), _yaml(), changed=False)
    errors: list = []
    _review_can_fire_gate(errors)
    assert errors == []
    assert "backlog" not in capsys.readouterr().out
