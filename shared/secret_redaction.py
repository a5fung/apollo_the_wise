"""Strip credentials out of text before it is stored or shown.

WHY THIS EXISTS (2026-09-01). The #333 analyst-estimates recorder logged raw upstream errors
to `mi_audit_log`, and FMP puts the API key in the QUERY STRING. So 99 rows landed in the
database carrying a live key in plain text — and audit rows are read back into digests, the
`/audit` command and the weekly review, so the leak was one render away from a Telegram
message and from anything downstream that quotes an audit summary.

The fix belongs at the point text becomes durable or visible, not at one caller: any upstream
that authenticates by query parameter (FMP, Polygon, and several others we use) will do this
again the next time someone logs an exception verbatim.

Deliberately dependency-free and pure so it can be called from a logging path that must never
raise, and unit-tested without a DB or network.
"""
from __future__ import annotations

import logging
import re

__all__ = ["redact_secrets"]

logger = logging.getLogger(__name__)

# Query-string credentials: apikey=, api_key=, apiKey=, token=, key=, secret=, access_token=
_QS_SECRET = re.compile(
    r"((?:api[-_]?key|access[-_]?token|auth[-_]?token|token|secret|key|password|passwd|pwd)"
    r"\s*=\s*)([^&\s\"\'<>]+)",
    re.IGNORECASE,
)
# Bearer / Basic auth headers echoed into an error string.
_BEARER = re.compile(r"((?:bearer|basic)\s+)([A-Za-z0-9._\-+/=]{8,})", re.IGNORECASE)

_MASK = "***REDACTED***"


def redact_secrets(text) -> str:
    """Return `text` with query-string credentials and bearer tokens masked.

    Conservative by design: it masks the VALUE and keeps the parameter name, so an error
    stays diagnosable ("apikey=***REDACTED***" still tells you which credential was used).
    Never raises — a redactor that throws inside a logging path would be worse than the leak.
    """
    try:
        s = str(text)
        s = _QS_SECRET.sub(lambda m: m.group(1) + _MASK, s)
        s = _BEARER.sub(lambda m: m.group(1) + _MASK, s)
        return s
    except Exception as e:  # loud-ok: must never raise into a logging path, but must not be silent
        # SUPPRESS THE ORIGINAL, then say so. Returning the un-redacted text on failure would
        # defeat the whole point; returning a blank would hide that anything went wrong. The
        # no-silent-failures gate is right to demand a voice here — a redactor that fails
        # quietly is indistinguishable from one that works.
        logger.warning("secret redaction FAILED (%s: %s) — original text suppressed, not stored",
                       type(e).__name__, e)
        return "***REDACTION FAILED — original suppressed***"
