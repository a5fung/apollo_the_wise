"""A quoted date in the review registry silently disables its gate (2026-08-06).

`check_pending_reviews` guards with `if earliest and isinstance(earliest, date)`. A value written
as `earliest_review_date: '2026-09-01'` parses as a STRING, fails that isinstance check, and the
review is treated as having no date gate at all — it keeps surfacing every Sunday.

I did exactly this while re-gating five reviews: wrote the dates quoted, reported them re-gated,
and all five stayed in the ready list. The registry looked right and the behaviour was unchanged.

Nothing surfaced it — no error, no warning, and the YAML lint passes because quoting is legal
YAML. That is what makes it worth a test rather than a comment.
"""
import pathlib
from datetime import date

import yaml

REG = yaml.safe_load(pathlib.Path("data_gated_reviews.yaml").read_text())["reviews"]

_DATE_FIELDS = ("earliest_review_date", "deferred_until", "added_on", "closed_on",
                "deferred_on", "regated_on")


def test_every_date_field_parses_as_a_DATE_not_a_string():
    """The gate is `isinstance(earliest, date)`. A string passes YAML, passes the dupe-key lint,
    and silently turns the gate off."""
    bad = []
    for r in REG:
        for f in _DATE_FIELDS:
            v = r.get(f)
            if v is not None and not isinstance(v, date):
                bad.append(f"{r['review_id']}.{f} = {v!r} ({type(v).__name__})")
    assert not bad, (
        "these date fields are not dates — quoting makes them strings, which silently disables "
        "the date gate in check_pending_reviews:\n  " + "\n  ".join(bad))


def test_the_gate_it_protects_still_requires_a_date():
    """If the isinstance guard is ever relaxed to accept strings, this test should be deleted
    deliberately rather than left passing while asserting nothing."""
    import inspect
    from agents.market_intelligence import data_gated_reviews as dgr
    src = inspect.getsource(dgr.check_pending_reviews)
    assert "isinstance(earliest, date)" in src


def test_a_regated_review_actually_has_a_future_date():
    """Re-gating means moving the date. A review marked regated_on but left on a past date is
    the same silent no-op wearing a different disguise."""
    stale = []
    for r in REG:
        if not r.get("regated_on"):
            continue
        e = r.get("earliest_review_date")
        if not isinstance(e, date) or e <= r["regated_on"]:
            stale.append(f"{r['review_id']}: regated {r.get('regated_on')} but earliest={e!r}")
    assert not stale, "\n  ".join(stale)
