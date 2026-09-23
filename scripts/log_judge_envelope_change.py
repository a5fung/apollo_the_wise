"""[5m/7] companion — writes the judge call-ENVELOPE-change audit row (#547 / ADR 0030).

`scripts/preflight_judge_eval_gate.py` stays HOST-side, stdlib-only, no DB access (the
[5l/7] pattern this file's docstring documents) — so it cannot write to `mi_audit_log`
itself. This tiny script is the other half: it runs IN-CONTAINER via `docker exec` (has DB
access + app imports) and does exactly one thing — relay the JSON payload that
`preflight_judge_eval_gate.py --envelope-audit-json` printed into `mi_audit_log` via the
existing `log_audit_event()` helper (agents/market_intelligence/db.py — the SSoT for every
DB query per CLAUDE.md; this adds no new query, it calls the one that already exists).

Never blocks the deploy: an empty/missing/unparseable argv or a DB failure inside
`log_audit_event` (which itself never raises) all resolve to a quiet no-op, exit 0.
`deploy.sh` additionally wraps the call with `|| true` as a second belt.

Usage: python -m scripts.log_judge_envelope_change '<json payload from stdout>'
"""
from __future__ import annotations

import asyncio
import json
import sys


async def _write(payload: dict) -> None:
    from agents.market_intelligence.db import log_audit_event
    await log_audit_event(
        payload.get("event_type", "judge_envelope_changed"),
        payload.get("summary", ""),
        payload.get("detail", ""),
    )


def main() -> int:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        return 0  # nothing to log — not an error, just no payload this run
    try:
        payload = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(f"log_judge_envelope_change: could not parse payload ({e}): {sys.argv[1]!r}",
              file=sys.stderr)
        return 0  # malformed payload must never fail the deploy over an audit-log write
    asyncio.run(_write(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
