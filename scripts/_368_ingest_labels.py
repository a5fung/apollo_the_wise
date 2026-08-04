"""#368 — ingest the operator's ground-truth labels from the labelling sheet.

The sheet (`docs/analysis/368_labeling_sheet.tsv`) is the operator's work product; this writes it
into `mi_theme_relevance_cohort.operator_label` / `.operator_note`, which is what the meta-rubric
weighting decision reads.

PARTIAL BY DESIGN. He labels what he has time for — 90 of 190 on the first pass — so this only ever
writes rows that HAVE a label and leaves the rest untouched. Re-running after another sitting tops
up rather than starting over.

MATCH KEY = (ticker, alert_date, stratum). The cohort table has no theme column, so a ticker that
appears twice on different dates is distinct, but the SAME ticker+date under two different THEMES
collapses to one row — the operator hit exactly that on rows 1 and 2 (ANNA in two themes on
adjacent dates) and noted it himself. Where a key matches more than one sheet row with CONFLICTING
labels, this refuses to guess: it reports the conflict and writes neither.

    python scripts/_368_ingest_labels.py           # dry run — what would be written
    python scripts/_368_ingest_labels.py --execute
"""
import argparse
import asyncio
import csv
import sys
from datetime import date as _date
from collections import defaultdict

SHEET = "docs/analysis/368_labeling_sheet.tsv"
VALID = {"y": "y", "n": "n", "?": "?"}


def _load():
    """(key -> (label, note)) for labelled rows; plus the conflicts we refuse to write."""
    rows = list(csv.DictReader(open(SHEET), delimiter="\t"))
    by_key = defaultdict(list)
    for r in rows:
        raw = (r.get("LABEL") or "").strip().lower()
        if not raw:
            continue
        if raw not in VALID:
            print(f"  ! row {r['row']}: unrecognised label {raw!r} — skipped")
            continue
        by_key[(r["ticker"].strip(), r["date"].strip(), r["stratum"].strip())].append(
            (VALID[raw], (r.get("NOTE") or "").strip(), r["row"]))
    clean, conflicts = {}, []
    for key, vals in by_key.items():
        labels = {v[0] for v in vals}
        if len(labels) > 1:
            conflicts.append((key, vals))
            continue
        note = next((v[1] for v in vals if v[1]), "")
        clean[key] = (vals[0][0], note)
    return len(rows), clean, conflicts


async def main(execute: bool) -> int:
    from agents.market_intelligence.db import get_pool

    total, clean, conflicts = _load()
    print(f"sheet rows {total} · labelled keys {len(clean)} · conflicting keys {len(conflicts)}")
    for key, vals in conflicts:
        print(f"  ! CONFLICT {key}: {[(v[2], v[0]) for v in vals]} — writing neither")

    pool = await get_pool()
    matched = missing = 0
    async with pool.acquire() as conn:
        for (ticker, date, stratum), (label, note) in clean.items():
            # asyncpg binds a DATE param as a date OBJECT — a string raises DataError even with
            # an explicit ::date cast. Same class as the 2026-07-28 bug that took the whole nightly
            # theme pull down ("inconsistent types deduced for parameter $2: text versus date").
            row_id = await conn.fetchval(
                "SELECT id FROM mi_theme_relevance_cohort "
                "WHERE ticker=$1 AND alert_date=$2 AND stratum=$3",
                ticker, _date.fromisoformat(date), stratum)
            if row_id is None:
                missing += 1
                continue
            matched += 1
            if execute:
                await conn.execute(
                    "UPDATE mi_theme_relevance_cohort "
                    "SET operator_label=$1, operator_note=NULLIF($2,''), labeled_at=NOW() "
                    "WHERE id=$3", label, note, row_id)

    print(f"\nmatched {matched} · no cohort row for {missing}")
    if not execute:
        print("DRY RUN — nothing written. Re-run with --execute.")
        return 0

    async with pool.acquire() as conn:
        done = await conn.fetchval(
            "SELECT COUNT(*) FROM mi_theme_relevance_cohort WHERE operator_label IS NOT NULL")
        tot = await conn.fetchval("SELECT COUNT(*) FROM mi_theme_relevance_cohort")
    print(f"cohort now labelled: {done}/{tot}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    sys.exit(asyncio.run(main(ap.parse_args().execute)))
