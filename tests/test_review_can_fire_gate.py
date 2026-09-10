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
"""
import pytest

from scripts.check_plan import _CAN_FIRE_KEYS, _reviews_by_id


_FULL = {k: "a real sentence about what was actually checked here" for k in _CAN_FIRE_KEYS}


def _yaml(**over):
    import yaml
    r = {"review_id": "probe", "status": "pending", "predicate_sql": "SELECT 1",
         "threshold": 5, "earliest_review_date": "2026-10-01"}
    r.update(over)
    return yaml.safe_dump({"reviews": [r]})


def test_the_five_questions_are_the_five_failures_seen():
    """Pin the vocabulary — each key is one of the ways a review turned out unable to fire."""
    assert set(_CAN_FIRE_KEYS) == {
        "predicate_runs", "nonzero_possible", "lane_live",
        "threshold_vs_observed", "era_scoped"}


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
