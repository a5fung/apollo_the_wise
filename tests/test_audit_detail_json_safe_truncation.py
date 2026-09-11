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


# ── The envelope must fit EXACTLY, at any cap (2026-09-10) ───────────────────────────────────
#
# The first version reserved a fixed 200 chars for the wrapper and then closed with
# `[:_AUDIT_DETAIL_MAX]`. That is the same blind cut this function exists to remove, one level up:
# JSON escaping expands quotes, backslashes and newlines, so the wrapper itself can cross the budget
# and be sliced mid-token. It survived at 8,000 and broke the moment the cap moved to 32,000 — which
# is only a lucky escape, not a design.

@pytest.mark.parametrize("size", [8_001, 12_000, 40_000, 200_000])
def test_output_is_valid_json_and_within_budget_at_any_size(size):
    src = json.dumps({"blob": "x" * size})
    out = _fit_audit_detail(src)
    json.loads(out)
    assert len(out) <= _AUDIT_DETAIL_MAX


def test_escape_heavy_content_still_fits():
    """Quotes and newlines double in length once escaped — the reserve cannot be a constant."""
    src = json.dumps({"blob": '"\\\n' * 20_000})
    out = _fit_audit_detail(src)
    json.loads(out)
    assert len(out) <= _AUDIT_DETAIL_MAX


def test_the_cap_is_not_a_database_limit():
    """Recorded so nobody re-derives it: mi_audit_log.detail is `text`, unlimited in Postgres.
    8,000 was a number we chose and then forgot we had, and it silently ate the tail of the one
    instrument built to explain why the model declined a cluster."""
    from agents.market_intelligence.db import _AUDIT_DETAIL_MAX as cap
    assert cap >= 32_000


# ── The mark must be READ by something, not just written (2026-09-10) ────────────────────────
#
# Half the fix is that a truncated row now carries `_truncated`. The other half is that some
# surface queries it — a marker nothing looks at is the same silence relocated, which is exactly
# how the 8,000-char cut survived unnoticed until a JSON parse failed by accident.

def test_the_nightly_sweep_reads_the_truncation_mark():
    import inspect

    from agents.market_intelligence import scheduler
    src = inspect.getsource(scheduler._check_nightly_silent_errors)
    assert "count_truncated_audit_rows" in src, (
        "the nightly sweep stopped counting truncated rows — the mark is unread again")
    assert "_trunc" in src


def test_the_sweep_reports_even_when_only_truncations_happened():
    """A night with zero errors but truncated payloads must still speak. Under `if total:` it
    would have stayed silent, which is the failure mode being fixed."""
    import inspect

    from agents.market_intelligence import scheduler
    src = inspect.getsource(scheduler._check_nightly_silent_errors)
    assert "if total or _trunc:" in src, "a truncation-only night would be silent again"


def test_the_counter_never_raises_into_its_caller():
    """It rides on the sweep; a diagnostic must not break the surface it reports through."""
    import inspect

    from agents.market_intelligence.db import count_truncated_audit_rows
    src = inspect.getsource(count_truncated_audit_rows)
    assert "return 0" in src and "except Exception" in src


# ── The truncation must be LOUD at the moment it happens (2026-09-10, second pass) ───────────
#
# Commit 3e5400d7's message says "A truncation also logs a warning at the moment it happens".
# It did not: the envelope-fit edit replaced the span that held the line, and no test asserted it,
# so the claim survived in prose and died in code. That is this week's defect applied to a claim
# instead of a gate — a statement nothing can falsify reads the same as a true one.

def test_a_truncation_logs_a_warning_when_it_happens(caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger="agents.market_intelligence.db"):
        _fit_audit_detail(_big_json(40_000))
    assert any("truncated" in r.message for r in caplog.records), (
        "truncation went silent at the moment it happened")


def test_the_warning_covers_non_json_text_too(caplog):
    """The plain cut loses a tail as surely as the JSON path does."""
    import logging

    with caplog.at_level(logging.WARNING, logger="agents.market_intelligence.db"):
        _fit_audit_detail("z" * (_AUDIT_DETAIL_MAX + 500))
    assert any("truncated" in r.message for r in caplog.records)


def test_a_payload_that_fits_says_nothing(caplog):
    """The ordinary row is the overwhelming majority — it must not page anyone."""
    import logging

    with caplog.at_level(logging.WARNING, logger="agents.market_intelligence.db"):
        _fit_audit_detail(json.dumps({"a": 1}))
    assert not caplog.records
