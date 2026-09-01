"""Credentials must never become durable in the audit log.

WHAT HAPPENED (2026-09-01). The #333 analyst-estimates recorder logged raw upstream errors, and
FMP authenticates by QUERY STRING — so its first live run wrote 99 `analyst_estimates_error` rows
into `mi_audit_log`, each carrying a working API key in plain text. Audit rows are read back into
the weekly review, `/audit` and the nightly digests, so the leak was one render from Telegram.

The fix is at `db.log_audit_event`, the chokepoint where text becomes durable — not at the one
caller. Every provider we authenticate by query parameter (FMP, Polygon) has the same shape, and
the next person to log an exception verbatim would repeat it.
"""
from __future__ import annotations

import inspect

from shared.secret_redaction import redact_secrets

_REAL_LEAK = (
    "analyst_estimates_snapshot: ZBRA: HTTPStatusError: Client error '402 Payment Required' "
    "for url 'https://financialmodelingprep.com/stable/income-statement"
    "?apikey=27WigvQk81FImdkhfov8uZ5rmHyyXOSQ&symbol=ZBRA&period=quarter&limit=1'"
)


def test_the_exact_string_that_leaked_is_masked():
    out = redact_secrets(_REAL_LEAK)
    assert "27WigvQk81FImdkhfov8uZ5rmHyyXOSQ" not in out
    assert "apikey=***REDACTED***" in out, "mask the value, keep the parameter name"
    assert "income-statement" in out and "ZBRA" in out, (
        "the error must stay diagnosable — only the credential goes")


def test_common_credential_shapes():
    for raw, secret in [
        ("?api_key=abc123&x=1", "abc123"),
        ("&token=zzz999 trailing", "zzz999"),
        ("Authorization: Bearer sk-ant-abcdefgh12345", "sk-ant-abcdefgh12345"),
        ("password=hunter2", "hunter2"),
    ]:
        assert secret not in redact_secrets(raw), f"leaked from: {raw}"


def test_benign_query_parameters_survive():
    """Over-redaction hides the diagnosis, which is its own failure — a `symbol=` or `period=`
    must come through untouched or nobody can read the error."""
    s = "symbol=ZBRA&period=quarter&limit=1"
    assert redact_secrets(s) == s


def test_the_redactor_never_raises():
    """It runs inside a logging path that must never raise. A redactor that throws would be
    worse than the leak it prevents."""
    class Boom:
        def __str__(self): raise RuntimeError("nope")
    assert "REDACTION FAILED" in redact_secrets(Boom())


def test_log_audit_event_actually_calls_it():
    """Guard the guard: the module can be perfect and unused. MUTATION TARGET — removing the
    redact_secrets call from log_audit_event, which no other test would notice."""
    from agents.market_intelligence.db import log_audit_event
    src = inspect.getsource(log_audit_event)
    assert "redact_secrets" in src
    assert "redact_secrets(summary)" in src and "redact_secrets(detail)" in src, (
        "BOTH fields are written to the row; redacting one is a false sense of safety")
