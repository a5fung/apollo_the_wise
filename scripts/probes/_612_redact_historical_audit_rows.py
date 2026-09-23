"""#612 — mask the credentials sitting in historical `mi_audit_log` rows.

WHY. On 2026-09-01 a live FMP key reached the database in plain text: FMP authenticates by QUERY
STRING and the #333 recorder logged upstream errors verbatim. The WRITE PATH was fixed the same
night (`shared/secret_redaction.redact_secrets`, called from `db.log_audit_event`), and prod
confirms it holds — every row since 2026-09-02 is masked. **The historical rows were never
cleaned**, and audit rows are read back into digests, `/audit` and the weekly review.

⚠ THE COUNT IN THE TASK WAS WRONG, measured 2026-09-10: the line said 99 rows. 99 is the count for
the `summary` column ALONE; `detail` holds far more. The real exposure is **202 rows carrying an
unmasked value, 2026-06-26 → 2026-09-01**, out of 771 that merely contain the string `apikey=`.

DESIGN. Applies the SHIPPED `redact_secrets` rather than a SQL copy of its regex — a second
implementation of a security rule is how the two drift, and this repo has been bitten by
local-copy-of-the-real-thing more than once. Dry-run by default; `--commit` to write.

NEVER PRINTS A SECRET. Reports counts and lengths only; a preview shows the masked form.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys

sys.path.insert(0, "/app")

from shared.secret_redaction import redact_secrets  # noqa: E402

# A value that still looks like a real credential after redaction ran.
_LIVE = re.compile(r"(?:apikey|api_key|token|secret)\s*=\s*[A-Za-z0-9]{12,}", re.I)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="write the masked text back")
    args = ap.parse_args()

    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, summary, detail FROM mi_audit_log "
            "WHERE summary ~* 'apikey=' OR detail ~* 'apikey=' ORDER BY id")
        print(f"candidate rows containing 'apikey=': {len(rows)}")

        changes = []
        for r in rows:
            s_new = redact_secrets(r["summary"]) if r["summary"] else r["summary"]
            d_new = redact_secrets(r["detail"]) if r["detail"] else r["detail"]
            if s_new != r["summary"] or d_new != r["detail"]:
                changes.append((r["id"], s_new, d_new))

        live_before = sum(1 for r in rows
                          if _LIVE.search((r["summary"] or "") + " " + (r["detail"] or "")))
        print(f"rows still holding an unmasked value: {live_before}")
        print(f"rows this run would change:           {len(changes)}")
        if not changes:
            print("nothing to do.")
            return 0

        # Fidelity preview — MASKED text only, never the original.
        sample = changes[0]
        preview = (sample[1] or sample[2] or "")[:160]
        print(f"\nsample of the masked result (row {sample[0]}):\n  {preview}")

        if not args.commit:
            print("\nDRY RUN — nothing written. Re-run with --commit.")
            return 0

        async with conn.transaction():
            for rid, s_new, d_new in changes:
                await conn.execute(
                    "UPDATE mi_audit_log SET summary = $2, detail = $3 WHERE id = $1",
                    rid, s_new, d_new)
        print(f"\nCOMMITTED — {len(changes)} row(s) updated.")

        after = await conn.fetch(
            "SELECT summary, detail FROM mi_audit_log "
            "WHERE summary ~* 'apikey=' OR detail ~* 'apikey='")
        live_after = sum(1 for r in after
                         if _LIVE.search((r["summary"] or "") + " " + (r["detail"] or "")))
        print(f"rows still holding an unmasked value AFTER: {live_after}")
        return 0 if live_after == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
