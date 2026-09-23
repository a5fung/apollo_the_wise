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


def test_a_regated_review_actually_moves_its_gate():
    """A re-gate must change something that stops the review surfacing. There are two honest
    ways to do that and this test must not force the wrong one.

    `regate_kind: date`      — pushed the calendar floor out. The date MUST move forward, or the
                               review resurfaces tomorrow and the re-gate was theatre. This is
                               the 2026-08-06 bug that created this file.
    `regate_kind: predicate` — repointed predicate_sql at the population/event that would
                               actually change the decision, leaving the date alone ON PURPOSE.

    ⚠ Do NOT "fix" a predicate re-gate by also pushing its date out. For an EVENT-gated review
    (first live REDUCE tier · first HIGH-without-direct-source) a future date is actively
    harmful: the event can fire next week and the date floor would suppress the surface until
    the quarter turns — the review would go quiet at exactly the moment it had something to say.
    A predicate that reads 0 is already the gate; the date is a floor it does not need.
    """
    stale = []
    for r in REG:
        if not r.get("regated_on"):
            continue
        kind = r.get("regate_kind")
        if kind not in ("date", "predicate"):
            stale.append(f"{r['review_id']}: regated {r['regated_on']} but regate_kind="
                         f"{kind!r} — say which gate moved (date|predicate)")
        elif kind == "date":
            e = r.get("earliest_review_date")
            if not isinstance(e, date) or e <= r["regated_on"]:
                stale.append(f"{r['review_id']}: regate_kind=date but earliest={e!r} "
                             f"is not after regated_on {r['regated_on']}")
        elif not str(r.get("predicate_sql") or "").strip():
            stale.append(f"{r['review_id']}: regate_kind=predicate but predicate_sql is empty — "
                         f"nothing gates it at all")
    assert not stale, "\n  ".join(stale)
