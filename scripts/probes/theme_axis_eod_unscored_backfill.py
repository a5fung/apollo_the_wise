#!/usr/bin/env python3
"""Theme-correctness programme Step 4 (THE INSTRUMENT, 2026-09-07) — one-time historical
backfill of the EOD-unscored NULL-CONTROL population into `mi_theme_axis_shadow`
(source='eod_unscored').

WHAT THIS DOES. Walks every `mi_ep_scan_log` (ticker, scan_date) pair since 2026-04-13,
classifies its EFFECTIVE reject stage (theme_axis_shadow.effective_reject_stage: the
column itself when #605 already captured it, >= 2026-08-31, else the legacy
classify_legacy_filter_reason() read of the older free-text `filter_reason` column — see
that module section for the full pattern map + citations), keeps the ones landing in one
of the seven unscored/under-bar stages (db.UNSCORED_THEME_AXIS_REJECT_STAGES —
scored-under-bar 'score_bar' PLUS the group prior scoping missed: candidates killed
before scoring ever ran at shortlist_cap/rvol_gate/cooldown/extension/quality_filter/
post_grade_filter), and writes each one via the SAME per-row logic the live EOD job uses
(theme_axis_shadow._write_unscored_candidates, built on compute_unscored_theme_axis_row +
write_unscored_theme_axis_row) — one write path, live or backfilled, never two.

⚠ WHY reject_stage ALONE ISN'T ENOUGH (found 2026-09-08, prod-verified, not assumed):
`mi_ep_scan_log.reject_stage` was added by #605 on 2026-08-29, but is populated only from
2026-08-31 on — every row from the table's start (2026-04-13) through 2026-08-30 carries
reject_stage=NULL. A population built on reject_stage alone recovers only 38 ticker-days
(all after the 08-22 score-separation cutline) — an instrumentation gap, not "nothing
existed before." `filter_reason` (the older free-text column) IS populated back to day
one (53,079 of 53,432 total rows) and its wording is regular, not free-form prose — see
theme_axis_shadow._LEGACY_FILTER_REASON_PATTERNS for the full map, each pattern sourced
from the exact string literal ep_detector.py builds for that stage.

⚠ NOT A BYTE-IDENTITY CLAIM — that exact false claim is what #629 is. Unlike
scripts/probes/_486_backfill_bounded.py (which fidelity-checks against 4 rows the live
writer had ALREADY captured), there is NO live capture of this population to diff a
backfilled row against: this EOD-unscored writer has never run live before today, so
nothing was ever recorded for a candidate that never became an alert. The real guarantee,
stated plainly and no stronger:
  1. `mi_themes` is dated append-only per day (verified for #486 — every INSERT/UPDATE
     call site resolves its target theme_date to et_today()/CURRENT_DATE at CALL time; a
     past theme_date row is never mutated after its day ends).
  2. `mi_ep_scan_log` and `mi_daily_closes` are equally frozen for a scan_date/trade_date
     once that date has passed (no call site in this codebase rewrites a historical row of
     either table).
  Given (1) and (2), calling compute_unscored_theme_axis_row for a historical trade_date
  TODAY reads the exact same theme/price inputs a live run on that date would have read.
  What is NEW, and weaker, for the pre-2026-08-31 rows specifically: the STAGE itself is
  RECOVERED via pattern-matching free text, not read off a column the original scan wrote
  — a wording this map doesn't recognize is invisible to it (see the UNMATCHED tail this
  script reports every run) and a wording that LOOKS like a known pattern but means
  something subtly different would misclassify silently. Verified on prod 2026-09-07: the
  full 2026-04-13-on population classifies with ZERO unmatched rows today — that is
  evidence the map is complete AS OF TODAY'S DATA, not a permanent guarantee against a
  future new wording (which is exactly why this script reports the unmatched count on
  every run rather than assuming it stays zero).

⚠ ERA SPLIT (2026-08-22): the EP score-separation cutline (ep_detector.py's `#533
SEPARATION FLIP`, docs/setups/magna53_ep.md change log 2026-08-22) moved that day —
SCORE_WEIGHTS and the HIGH bar both changed. The population is reported split before/after
so a scored-under-bar count from one era is never mistaken for "everything we cannot see"
across the whole history; the two eras are not the same measuring stick.

Usage (run inside apollo-market, which has the modules + DB — same pattern as
scripts/probes/_486_backfill_bounded.py):
  python -m scripts.probes.theme_axis_eod_unscored_backfill              # snapshot + dry-run sample, no writes
  python -m scripts.probes.theme_axis_eod_unscored_backfill --commit     # snapshot + backfill
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date

from agents.market_intelligence.db import (
    UNSCORED_THEME_AXIS_REJECT_STAGES, get_ep_scan_log_raw_population, get_pool,
)
from agents.market_intelligence.theme_axis_shadow import (
    _write_unscored_candidates,
    compute_unscored_theme_axis_row,
    effective_reject_stage,
    get_legacy_classification_unmatched,
)

_SINCE_DATE = date(2026, 4, 13)
_ERA_CUTLINE = date(2026, 8, 22)  # #533 EP score-separation flip (ep_detector.py, magna53_ep.md)


def split_by_era(rows: "list[dict]", cutline: date = _ERA_CUTLINE) -> "tuple[list, list]":
    """Pure era split — before/after the #533 EP score-separation cutline (2026-08-22).
    Extracted so the split itself is unit-testable without a DB (see the module docstring's
    ⚠ ERA SPLIT note for why this matters: SCORE_WEIGHTS and the HIGH bar both changed that
    day, so a scored-under-bar count from one era is not the same measuring stick as the
    other). Returns (before, after); `before` excludes the cutline date itself (< cutline),
    `after` includes it (>= cutline) — the day of the flip runs under the NEW rules."""
    before = [r for r in rows if r["scan_date"] < cutline]
    after = [r for r in rows if r["scan_date"] >= cutline]
    return before, after


def build_population(raw_rows: "list[dict]") -> "list[dict]":
    """Classify every raw scan-log row's EFFECTIVE stage (reject_stage when #605 already
    captured it, else the legacy filter_reason read) and keep the ones landing in
    UNSCORED_THEME_AXIS_REJECT_STAGES. Returns candidate dicts shaped for
    theme_axis_shadow._write_unscored_candidates: {"scan_date", "ticker",
    "reject_stage" (the EFFECTIVE one, never the raw column), "ep_score"}.

    Pure — no DB, no write — so it is unit-testable directly against fixture rows."""
    out = []
    for r in raw_rows:
        stage = effective_reject_stage(r.get("reject_stage"), r.get("filter_reason"))
        if stage in UNSCORED_THEME_AXIS_REJECT_STAGES:
            out.append({
                "scan_date": r["scan_date"], "ticker": r["ticker"],
                "reject_stage": stage, "ep_score": r.get("ep_score"),
            })
    return out


async def _population_snapshot(conn) -> dict:
    raw_rows = await get_ep_scan_log_raw_population(conn, _SINCE_DATE)
    candidates = build_population(raw_rows)
    unmatched = get_legacy_classification_unmatched(raw_rows)
    before, after = split_by_era(candidates)
    dates = sorted({r["scan_date"] for r in candidates})

    print(f"=== POPULATION SNAPSHOT: {len(raw_rows)} raw scan-log ticker-day(s) since "
          f"{_SINCE_DATE}, {len(candidates)} classified into the unscored population ===")
    print(f"  pre-score-separation  (< {_ERA_CUTLINE}): {len(before)}")
    print(f"  post-score-separation (>= {_ERA_CUTLINE}): {len(after)}")
    if dates:
        print(f"  spanning {dates[0]} .. {dates[-1]} across {len(dates)} distinct scan date(s)")

    by_stage: dict[str, int] = {}
    for r in candidates:
        by_stage[r["reject_stage"]] = by_stage.get(r["reject_stage"], 0) + 1
    print("  by effective reject_stage:")
    for stage, n in sorted(by_stage.items(), key=lambda kv: -kv[1]):
        print(f"    {stage}: {n}")

    print(f"\n  UNMATCHED (real filter_reason, no known pattern): {len(unmatched)}")
    if unmatched:
        print("  ⚠ sample of unmatched reasons (report these, do not silently drop):")
        seen_texts: set[str] = set()
        shown = 0
        for r in unmatched:
            if r["filter_reason"] in seen_texts:
                continue
            seen_texts.add(r["filter_reason"])
            print(f"    {r['scan_date']} {r['ticker']}: {r['filter_reason']!r}")
            shown += 1
            if shown >= 10:
                break

    return {"raw_rows": raw_rows, "candidates": candidates, "unmatched": unmatched,
            "before": before, "after": after, "dates": dates}


async def _existing_row_count(conn) -> int:
    return await conn.fetchval(
        "SELECT COUNT(*) FROM mi_theme_axis_shadow WHERE source = 'eod_unscored'")


async def main() -> None:
    commit = "--commit" in sys.argv[1:]
    pool = await get_pool()
    async with pool.acquire() as conn:
        snap = await _population_snapshot(conn)
        candidates = snap["candidates"]
        already = await _existing_row_count(conn)
        print(f"\nAlready in mi_theme_axis_shadow (source='eod_unscored'): {already}")

        if not candidates:
            print("Nothing to backfill.")
            return

        if not commit:
            print("\n--- DRY-RUN sample (first 5 candidates; READ-ONLY, no writes) ---")
            for r in candidates[:5]:
                fields = await compute_unscored_theme_axis_row(conn, r["ticker"], r["scan_date"])
                print(
                    f"  {r['scan_date']} {r['ticker']:6} reject_stage={r['reject_stage']:<18} "
                    f"ep_score={r['ep_score']} -> theme={fields['theme_name']!r} "
                    f"themeless={fields['themeless_flag']} co_moving={fields['co_moving']}"
                )
            print(
                "\nNo flag: dry-run sample printed above, no writes made. "
                "Re-run with --commit to perform the backfill."
            )
            return

        out = await _write_unscored_candidates(conn, candidates)
        print(
            f"\n=== BACKFILL RESULT === candidates={len(candidates)} written={out['written']} "
            f"(themed={out['themed']} themeless={out['themeless']})"
        )
        after_count = await _existing_row_count(conn)
        print(f"mi_theme_axis_shadow rows with source='eod_unscored' now: {after_count}")

        # ── Idempotency check (the "idempotent on source" requirement, verified in
        # practice, not just by SQL construction): re-run the exact same pass immediately.
        # Every candidate now already has a row, so the ON CONFLICT DO NOTHING guard must
        # block every single write — a non-zero second-pass `written` means either the
        # classification or the write path is not actually idempotent.
        out2 = await _write_unscored_candidates(conn, candidates)
        print(
            f"\n=== IDEMPOTENCY CHECK (immediate re-run) === "
            f"candidates={len(candidates)} written={out2['written']} "
            f"({'OK — fully idempotent' if out2['written'] == 0 else 'MISMATCH — investigate before trusting this backfill'})"
        )


if __name__ == "__main__":
    asyncio.run(main())
