"""#482 evidence-quarantine remediation for the #216 jsonb double-encoding
freeze in `mi_orb_shadow_trades` (bar_size_minutes=5 lane).

BACKGROUND: `update_shadow_trade` double-encoded `running_closes`/`exits`
jsonb writes for months; `_row_to_state` then raised on the corrupted
string-typed column on the row's NEXT update attempt, and
`update_shadow_positions`'s per-row `except` silently swallowed it — so
every row froze after its first successful step. The 2026-08-17 fix landed
and the very next exit pass RESUMED every frozen row with ONE step spanning
the entire frozen gap (e.g. a 109-calendar-day span evaluated as if it were
the next trading day) — fabricating win/loss outcomes on ~100 days of price
action the exit rule never actually saw.

This script does NOT re-run automatically and does NOT run inside the live
daily cron (`update_shadow_positions` now self-guards new occurrences via
`detect_stale_for_step` — see shadow_orb_tracker.py). It is the ONE-TIME
cleanup for the rows already damaged by the 2026-08-17 resume:

  CLOSED rows showing the gap signature (`detect_path_gap`): quarantined
  only. Existing recorded values (running_closes/exits/total_pnl/status)
  are NEVER touched — only the additive `quarantined` / `quarantine_reason`
  / `quarantined_at` columns are set. A closed position is terminal; a
  faithful replay would mean deciding whether it EVER actually closed,
  which is a bigger intervention than this ticket asks for.

  OPEN rows showing the gap signature: faithfully RE-REPLAYED via
  `shadow_orb_tracker.replay_stale_open_row` — day-by-day, using real
  historical daily bars (`collector.get_index_history`), through the same
  canonical exit-ladder driver + kwargs the live path already uses (no
  strategy change — a data repair). The row's pre-replay (corrupted) values
  are dumped to `pre_replay_snapshot` before being overwritten, and this
  script ALSO dumps a full before/after JSON to disk (`--dump-dir`,
  default `/tmp`) as a second, file-level copy of "what was there before" —
  belt and suspenders, matching the constraint against erasing evidence.
  If replay is unavailable for a ticker (no historical bars), that row
  falls back to quarantine-only with the reason recorded.

Defaults to DRY RUN — prints every planned action, writes nothing. Pass
--apply to actually run the UPDATEs.

Run on PROD (dry run first, always):
    docker exec apollo-market python -m scripts.remediate_shadow_freeze_216
    docker exec apollo-market python -m scripts.remediate_shadow_freeze_216 --apply
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# Allow running as `python scripts/...` (path tweak so package imports work).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.market_intelligence.db import get_pool, update_shadow_trade  # noqa: E402
from agents.market_intelligence.broker.shadow_orb_tracker import (  # noqa: E402
    detect_path_gap,
    replay_stale_open_row,
)
from shared.dates import et_today  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
BAR_SIZE_MINUTES = 5


async def _fetch_candidates() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM mi_orb_shadow_trades
            WHERE bar_size_minutes = $1
              AND status IN ('open', 'closed')
              AND NOT quarantined
            ORDER BY alert_date ASC
            """,
            BAR_SIZE_MINUTES,
        )
    return [dict(r) for r in rows]


def _json_default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)


async def main(apply: bool, dump_dir: str) -> None:
    as_of = et_today()
    rows = await _fetch_candidates()
    logger.info(f"Scanning {len(rows)} non-quarantined open/closed 5-min shadow rows (as_of={as_of})")

    n_closed_gapped = 0
    n_closed_clean = 0
    n_open_gapped = 0
    n_open_clean = 0
    n_replayed = 0
    n_replay_unavailable = 0

    dump_records: list[dict] = []

    for row in rows:
        gapped, reason = detect_path_gap(
            row["alert_date"], row.get("hold_days"), row.get("running_closes"),
        )
        if row["status"] == "closed":
            if not gapped:
                n_closed_clean += 1
                continue
            n_closed_gapped += 1
            logger.info(f"QUARANTINE (closed) {row['ticker']} {row['alert_date']}: {reason}")
            if apply:
                await update_shadow_trade(row["id"], {
                    "quarantined": True,
                    "quarantine_reason": reason,
                    "quarantined_at": datetime.now(ET),
                })
            continue

        # status == 'open'
        if not gapped:
            n_open_clean += 1
            continue
        n_open_gapped += 1
        replay_fields = await replay_stale_open_row(row, as_of)
        if "_replay_unavailable" in replay_fields:
            n_replay_unavailable += 1
            fallback_reason = f"{reason}; replay unavailable: {replay_fields['_replay_unavailable']}"
            logger.info(f"QUARANTINE (open, replay unavailable) {row['ticker']} {row['alert_date']}: {fallback_reason}")
            if apply:
                await update_shadow_trade(row["id"], {
                    "quarantined": True,
                    "quarantine_reason": fallback_reason,
                    "quarantined_at": datetime.now(ET),
                })
            continue

        n_replayed += 1
        new_status = replay_fields.get("status", "open")
        logger.info(
            f"REPLAY (open) {row['ticker']} {row['alert_date']}: "
            f"corrected status={new_status} hold_days={replay_fields['hold_days']} "
            f"total_pnl={replay_fields['total_pnl']:.2f} "
            f"(pre-replay: status={row['status']} hold_days={row.get('hold_days')} "
            f"total_pnl={row.get('total_pnl')})"
        )
        dump_records.append({
            "id": row["id"], "ticker": row["ticker"],
            "alert_date": row["alert_date"].isoformat(),
            "pre_replay": replay_fields["pre_replay_snapshot"],
            "post_replay": {k: v for k, v in replay_fields.items()
                             if k not in ("pre_replay_snapshot",)},
        })
        if apply:
            await update_shadow_trade(row["id"], replay_fields)

    if dump_records:
        os.makedirs(dump_dir, exist_ok=True)
        dump_path = os.path.join(
            dump_dir,
            f"shadow_482_replay_dump_{as_of.isoformat()}"
            f"{'_applied' if apply else '_dryrun'}.json",
        )
        with open(dump_path, "w") as f:
            json.dump(dump_records, f, indent=2, default=_json_default)
        logger.info(f"Replay before/after dump written: {dump_path}")

    logger.info("─" * 60)
    logger.info(f"MODE: {'APPLY (mutated prod)' if apply else 'DRY RUN (nothing written)'}")
    logger.info(f"Closed: {n_closed_gapped} quarantined, {n_closed_clean} clean (untouched)")
    logger.info(f"Open:   {n_open_gapped} gapped -> {n_replayed} replayed, "
                f"{n_replay_unavailable} quarantined (replay unavailable); "
                f"{n_open_clean} clean (untouched)")
    logger.info("─" * 60)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                     help="Actually write the UPDATEs. Default is dry-run (print only).")
    ap.add_argument("--dump-dir", default="/tmp",
                     help="Directory for the replay before/after JSON dump.")
    args = ap.parse_args()
    asyncio.run(main(args.apply, args.dump_dir))
