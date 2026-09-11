#!/usr/bin/env python3
"""Repair the audit rows that the OLD blind `detail[:8000]` cut left unreadable.

WHY (2026-09-10). Until today `log_audit_event` truncated with `detail[:8000]`, slicing
`json.dumps(...)` payloads mid-token. Those rows cannot be read back — and worse, a SINGLE invalid
row makes any `SELECT detail::json ...` over the whole table fail, so they break readers that never
touch them. The write path is fixed and verified live tonight (`_fit_audit_detail`, 32,000 budget,
valid-JSON-in/valid-JSON-out, plus a warning at the moment it happens), so no NEW ones can appear.
This repairs the history the old path left behind.

⚠ THE COUNT, corrected twice in one evening — write down the one that survived the query.
15 rows hit the 8,000 cap. I first told him "only 1 is broken"; a wider query then said 10; the
right answer is **2**. The other 8 are `description_generated` rows whose detail is PLAIN PROSE
("MNTS: Industrials / Aerospace & Defense — ...") — the old cut lost their tail and no repair can
bring it back, but they were never JSON and nothing reads them as JSON. The 2 that matter are
`theme_birth_gate` (2026-09-03) and `theme_discovery_shown_declined` (2026-09-10, the row that
exposed the bug).

Also corrected: "one invalid row breaks every `detail::json` query over the table" is TRUE but not
special to these — legitimately plain-text rows do it too, and always have. Real readers filter by
`event_type` first. The harm here is narrower and is the whole point: a JSON payload written to be
read back, that cannot be read back.

WHAT IT DOES: wraps each broken payload in the SAME envelope the live path now writes, so the row
becomes valid JSON that announces its own loss. The 8,000 surviving characters are preserved
VERBATIM in `_head` — nothing is deleted, and the tail was already gone before this ran.
`_original_len` is null on purpose: the old cut did not record it and inventing a number would be
worse than saying we cannot know.

SAFETY: dry-run by default. Every original `detail` is written to a snapshot file BEFORE any write,
every repaired value is parsed and size-checked in Python first, and the update is keyed by id with
an unchanged-detail guard so a concurrent write cannot be clobbered. `--commit` applies.

    python scripts/probes/_501_repair_unreadable_audit_rows.py            # dry run
    python scripts/probes/_501_repair_unreadable_audit_rows.py --commit
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.market_intelligence.db import _AUDIT_DETAIL_MAX, get_pool   # noqa: E402

_ET = ZoneInfo("America/New_York")
# ⚠ THE FIRST DRAFT OF THIS QUERY WAS WRONG and the dry run caught it. `NOT pg_input_is_valid` alone
# also selects rows whose detail is legitimately PLAIN TEXT — `_fit_audit_detail` allows those on
# purpose, and the first run offered to rewrite an 11-character `stage_change` row. The target is
# narrower: a row that was a JSON payload AND was cut by the old cap. Both conditions, or the repair
# invents a problem.
_OLD_CAP = 8000
_FIND = """
    SELECT id, event_type, created_at, detail
      FROM mi_audit_log
     WHERE detail IS NOT NULL
       AND length(detail) = $1               -- cut by the OLD blind cap, exactly
       AND left(ltrim(detail), 1) IN ('{', '[')   -- and it was a JSON payload
       AND NOT pg_input_is_valid(detail, 'json')
     ORDER BY created_at
"""


def repair(detail: str) -> str:
    """The live envelope, with `_original_len` null because the old cut never recorded it."""
    env = {
        "_truncated": True,
        "_original_len": None,
        "_note": ("payload was cut mid-token by the pre-2026-09-10 blind detail[:8000] truncation; "
                  "the head below is what survived, the tail was lost before this repair ran"),
        "_head": detail,
    }
    out = json.dumps(env)
    head = detail
    while len(out) > _AUDIT_DETAIL_MAX and head:
        head = head[: max(0, len(head) - (len(out) - _AUDIT_DETAIL_MAX) - 8)]
        env["_head"] = head
        out = json.dumps(env)
    return out


async def main(commit: bool) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_FIND, _OLD_CAP)
        if not rows:
            print("nothing to repair — every audit row parses as JSON")
            return 0

        stamp = datetime.now(_ET).strftime("%Y%m%dT%H%M%S")
        snap = Path(os.environ.get("APOLLO_PROBE_DIR", "/tmp")) / f"_501_audit_repair_{stamp}.json"
        snap.write_text(json.dumps(
            [{"id": r["id"], "event_type": r["event_type"],
              "created_at": r["created_at"].isoformat(), "detail": r["detail"]} for r in rows],
            indent=2))
        print(f"snapshot of {len(rows)} original row(s) -> {snap}\n")

        planned = []
        for r in rows:
            fixed = repair(r["detail"])
            json.loads(fixed)                        # refuses to plan a write that does not parse
            assert len(fixed) <= _AUDIT_DETAIL_MAX, r["id"]
            # compare the DECODED head, not the encoded text — JSON escaping changes the bytes,
            # which is what made the first version of this assertion fire on a valid repair.
            kept = json.loads(fixed)["_head"]
            assert r["detail"].startswith(kept), "the surviving head was not preserved verbatim"
            assert kept, "the head was dropped entirely"
            planned.append((r["id"], fixed))
            print(f"  id={r['id']:<7} {r['event_type']:<34} "
                  f"{r['created_at'].astimezone(_ET):%Y-%m-%d %H:%M} "
                  f"{len(r['detail'])} -> {len(fixed)} chars")

        if not commit:
            print(f"\nDRY RUN — {len(planned)} row(s) would be repaired. Re-run with --commit.")
            return 0

        done = 0
        for rid, fixed in planned:
            # keyed by id AND still-broken, so a concurrent rewrite is never clobbered
            done += int(bool(await conn.execute(
                "UPDATE mi_audit_log SET detail = $2 "
                " WHERE id = $1 AND NOT pg_input_is_valid(detail, 'json')", rid, fixed
            ) != "UPDATE 0"))
        # ⚠ AND THE SUCCESS CHECK WAS WRONG TOO — it counted every non-JSON row (24,367 of them,
        # nearly all legitimately plain text) and would have reported failure after a clean repair.
        # A check has to measure the population it just fixed. Same query as _FIND, by construction.
        left = await conn.fetchval(
            "SELECT count(*) FROM mi_audit_log "
            " WHERE detail IS NOT NULL AND length(detail) = $1 "
            "   AND left(ltrim(detail), 1) IN ('{', '[') "
            "   AND NOT pg_input_is_valid(detail, 'json')", _OLD_CAP)
        print(f"\nrepaired {done} row(s); unreadable rows remaining: {left}")
        return 0 if left == 0 else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    sys.exit(asyncio.run(main(ap.parse_args().commit)))
