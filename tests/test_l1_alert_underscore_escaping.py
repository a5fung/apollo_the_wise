"""2026-08-16 incident: the operator's L1 Telegram alert had every underscore stripped —
`silent_audit_error_window` rendered as `silentauditerrorwindow`, `mi_audit_log` as
`miauditlog`, `event_type`/`created_at` the same way. The drill-down SQL came through
unpasteable into psql: worse than useless, it was wrong.

ROOT CAUSE: `_format_l1_alert` in system_audit.py interpolated the invariant name, the
offending-row strings, the drill SQL, and the code pointers as BARE text. Telegram
Markdown treats a bare `_` as an italics delimiter — underscores pair up arbitrarily
across the WHOLE message and get silently consumed as formatting, not printed as
characters. `_format_l2_alert` already avoided this (metric name backticked, drill SQL
fenced, #121) — L1 predates that fix and was never brought in line with it.

FIX: L1 now backtick-wraps every identifier-bearing field (name, summary, offending
rows, code pointers) and fences the drill SQL in a ``` code block — the same escaping
idiom L2 already used.

MUTATION DISCIPLINE: every assertion below targets a SPECIFIC dynamic field going back
to bare interpolation. A test that passes whether or not the escaping is present is not
a test (operator, repeated).
"""
from agents.market_intelligence import system_audit

_BODY = {
    "summary": "1 '*_error' events in last 24h",
    "offending": ["job_cancelled_error: 1"],
    "drill_sql": (
        "SELECT event_type, summary, detail, created_at FROM mi_audit_log\n"
        "WHERE event_type LIKE '%_error'\n"
        "  AND created_at >= NOW() - INTERVAL '24 hours'"
    ),
    "code_pointers": ["agents/market_intelligence/system_audit.py::_format_l1_alert"],
}


def test_l1_alert_name_is_backtick_wrapped():
    """MUTATION TARGET: `f'... · {name}'` (bare) instead of `f'... · `{name}`'`.
    A bare name is exactly tonight's reported failure — Telegram would consume its
    underscores as italics delimiters and print `silentauditerrorwindow`."""
    text = system_audit._format_l1_alert("silent_audit_error_window", _BODY)
    assert "🚨 INVARIANT BREACH [L1] · `silent_audit_error_window`" in text
    # The bare (unescaped) form must NOT appear anywhere in the output.
    assert " · silent_audit_error_window\n" not in text


def test_l1_alert_summary_is_backtick_wrapped():
    """MUTATION TARGET: appending `summary` bare. The reported alert's summary line
    ("1 '*_error' events...") independently carries an underscore and was itself
    corrupted in the real incident (rendered as "1 '*error' events...")."""
    text = system_audit._format_l1_alert("silent_audit_error_window", _BODY)
    assert "`1 '*_error' events in last 24h`" in text


def test_l1_alert_offending_rows_are_backtick_wrapped():
    """MUTATION TARGET: `f'  • {s}'` (bare) instead of `f'  • `{s}`'`."""
    text = system_audit._format_l1_alert("silent_audit_error_window", _BODY)
    assert "  • `job_cancelled_error: 1`" in text


def test_l1_alert_drill_sql_is_fenced_and_verbatim():
    """MUTATION TARGET: `lines.append(drill)` (bare) instead of fencing with ```.
    This is the operator's core complaint: the drill SQL must survive Telegram
    Markdown byte-for-byte so it can be pasted straight into psql."""
    text = system_audit._format_l1_alert("silent_audit_error_window", _BODY)
    assert f"```\n{_BODY['drill_sql']}\n```" in text
    # Every identifier the operator named as corrupted must be present, VERBATIM,
    # inside that fenced block.
    assert "mi_audit_log" in text
    assert "event_type" in text
    assert "created_at" in text


def test_l1_alert_code_pointers_are_backtick_wrapped():
    """MUTATION TARGET: `f'  {p}'` (bare) instead of `f'  `{p}`'`."""
    text = system_audit._format_l1_alert("silent_audit_error_window", _BODY)
    assert "  `agents/market_intelligence/system_audit.py::_format_l1_alert`" in text


def test_l1_alert_renders_tonights_exact_reported_body():
    """End-to-end reproduction of the exact alert the operator received tonight —
    every underscore-bearing token from the real incident must appear verbatim
    (not stripped of its underscores) somewhere in the rendered text."""
    text = system_audit._format_l1_alert("silent_audit_error_window", _BODY)
    for token in ("silent_audit_error_window", "mi_audit_log", "event_type",
                  "created_at", "job_cancelled_error"):
        assert token in text, f"{token!r} missing/corrupted in the rendered text"
    # The corrupted (underscore-stripped) forms the operator actually received
    # must NOT appear.
    for corrupted in ("silentauditerrorwindow", "miauditlog", "eventtype", "createdat"):
        assert corrupted not in text
