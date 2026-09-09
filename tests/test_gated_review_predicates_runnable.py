"""Every operator-facing pending review must carry a predicate that CAN be evaluated.

WHY (2026-09-09). `scripts/operator_asks.py` shipped 09-08 printing "NOT an ask until its own
predicate says READY" for every pending review — without ever running a predicate. When it was
made to actually run them, FOUR reviews had been ready (one since 2026-07-29) and one,
`gap_near_miss_tradeable_miss_rate_617`, had been UNRUNNABLE since it was written: its SQL
referenced a column `reached_4r` that does not exist on `mi_gap_near_miss_replays`.

A gate that cannot fire is indistinguishable from a gate that says "not yet" — that is the
defect class of the week, and it had lodged inside the fix for it. CI has no database, so this
test cannot execute the SQL. It pins what IS decidable offline: the predicate exists, is a
string, and is not obviously inert. The execution half is covered at OPEN, where
`operator_asks.py` now runs each predicate and reports UNKNOWN (never "not ready") on failure.
"""
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO = Path(__file__).resolve().parent.parent


def _operator_facing_pending():
    d = yaml.safe_load((REPO / "data_gated_reviews.yaml").read_text())
    return [r for r in d.get("reviews", [])
            if r.get("status") == "pending"
            and "operator" in str(r.get("action_when_ready", "")).lower()]


def test_every_pending_operator_review_can_become_ready_somehow():
    """Data-gated reviews need a predicate; `kind: cadence` reviews are DATE-gated by design and
    correctly carry none — they need an earliest_review_date instead. What is forbidden is a
    review with NEITHER, which can never become ready and will sit pending forever."""
    bad = []
    for r in _operator_facing_pending():
        sql = r.get("predicate_sql")
        has_sql = isinstance(sql, str) and bool(sql.strip())
        is_dated_cadence = (str(r.get("kind", "")).lower() == "cadence"
                            and r.get("earliest_review_date") is not None)
        if not has_sql and not is_dated_cadence:
            bad.append(f"{r['review_id']}: no predicate_sql and no dated cadence — it can never "
                       f"become ready on its own, so it will sit pending forever")
    assert not bad, (
        "gated reviews that cannot be evaluated:\n  " + "\n  ".join(bad))


def test_predicates_are_scalar_shaped_and_have_a_threshold():
    """A predicate must SELECT something and pair with a numeric threshold, or the
    ready-vs-accruing comparison has nothing to compare."""
    bad = []
    for r in _operator_facing_pending():
        sql = r.get("predicate_sql")
        if not (isinstance(sql, str) and sql.strip()):
            continue                      # dated cadence review — covered by the test above
        if "select" not in sql.lower():
            bad.append(f"{r['review_id']}: predicate has no SELECT")
        if not isinstance(r.get("threshold"), (int, float)):
            bad.append(f"{r['review_id']}: threshold is {r.get('threshold')!r}, not a number")
    assert not bad, "unusable gated-review predicates:\n  " + "\n  ".join(bad)


def test_617_does_not_reference_the_column_that_never_existed():
    """The specific regression: `reached_4r` is not a column on mi_gap_near_miss_replays.
    Its rule is 'a name that reached >= 4R', which is `realized_r >= 4`."""
    d = yaml.safe_load((REPO / "data_gated_reviews.yaml").read_text())
    r = [x for x in d["reviews"] if x["review_id"] == "gap_near_miss_tradeable_miss_rate_617"]
    assert r, "the 617 review disappeared — if it was closed, delete this test with it"
    assert "reached_4r" not in r[0]["predicate_sql"], (
        "617's predicate is back to the phantom column; it errors on prod and the gate goes dark")
