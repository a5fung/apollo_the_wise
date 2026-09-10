"""A long audit payload must stay READABLE, not just get written.

WHY (2026-09-10). `log_audit_event` truncated with `detail[:8000]` — a blind character cut. Most
callers pass `json.dumps(...)`, so an over-long payload was stored sliced mid-token and the row
could not be read back at all: `SELECT detail::json->>'x'` fails for the WHOLE row with "invalid
input syntax for type json".

Found while verifying #486 — whose discovery recorder had just been fixed that morning to write the
model's per-cluster reasoning. The 17:06 run parsed; the 17:13 run hit exactly 8,000 characters and
became unreadable. **An instrument that records and cannot be read back is the same defect as one
that records nothing**, which is the subject of this entire week.

The #486 recorder bounds its own payload to 60,000 — a number that never applied, because the real
budget lives at this chokepoint and is 8,000. Hence the fix is here, like the redaction above it.
"""
import json

import pytest

from agents.market_intelligence.db import _AUDIT_DETAIL_MAX, _fit_audit_detail


def _big_json(n_chars):
    payload = {"scratchpads": ["x" * 500 for _ in range(n_chars // 500)], "ok": True}
    return json.dumps(payload)


def test_the_real_failure_a_long_json_payload_stays_parseable():
    """THE REGRESSION. Under the old `[:8000]` this came back as invalid JSON."""
    out = _fit_audit_detail(_big_json(40_000))
    json.loads(out)          # raises if we regressed — that IS the assertion
    assert len(out) <= _AUDIT_DETAIL_MAX


def test_a_truncated_row_announces_its_own_loss():
    """Silent loss is worse than loud loss — the row must say it was cut and by how much."""
    src = _big_json(40_000)
    out = json.loads(_fit_audit_detail(src))
    assert out["_truncated"] is True
    assert out["_original_len"] == len(src)
    assert out["_head"], "the head content was dropped entirely"


def test_a_payload_that_fits_is_untouched():
    """No behaviour change for the ordinary case — most rows are small."""
    src = json.dumps({"a": 1, "b": "short"})
    assert _fit_audit_detail(src) == src


def test_exactly_at_the_budget_is_untouched():
    src = "y" * _AUDIT_DETAIL_MAX
    assert _fit_audit_detail(src) == src


def test_non_json_text_still_gets_a_plain_cut():
    """Prose has no structure to protect; wrapping it would only cost room."""
    src = "z" * (_AUDIT_DETAIL_MAX + 500)
    assert _fit_audit_detail(src) == "z" * _AUDIT_DETAIL_MAX


def test_none_and_empty_pass_through():
    """This sits on a logging path that must never raise."""
    assert _fit_audit_detail(None) is None
    assert _fit_audit_detail("") == ""


def test_the_write_path_actually_calls_it():
    """Guard the guard. The helper's own tests pass whether or not log_audit_event USES it —
    reverting the call site to `detail[:8000]` broke nothing, which is this week's defect in
    miniature. Pin the wiring, not just the function."""
    import inspect

    from agents.market_intelligence.db import log_audit_event
    src = inspect.getsource(log_audit_event)
    assert "_fit_audit_detail(detail)" in src, "the write path stopped using the JSON-safe fit"
    assert "detail[:8000]" not in src, "the blind character cut is back"
