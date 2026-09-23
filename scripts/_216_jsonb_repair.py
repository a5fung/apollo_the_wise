#!/usr/bin/env python3
"""scripts/_216_jsonb_repair.py — repair double/multi-encoded JSONB columns (PLAN #216).

WHY. `db.py`'s asyncpg pool registers a jsonb type codec whose encoder is plain
`json.dumps`, applied AUTOMATICALLY to every jsonb bind param. Several call sites ALSO
called `json.dumps(value)` themselves before binding it into a `$N::jsonb` param — so
the already-serialised JSON text got encoded a SECOND time by the codec, and the column
ended up holding a JSON *string* whose content is itself JSON text
(`jsonb_typeof(col) = 'string'`) instead of a proper jsonb object/array. Measured on prod
2026-08-17 across 9 tables, ~4,300 rows (see PLAN.md #216 for the full diagnosis and the
write-path fix, which is a SEPARATE change owned by another agent — this script only
repairs data already written wrong; it does not touch how new rows get written).

THE RULE, matching the diagnosis exactly:
  - A row is a REPAIR CANDIDATE only if `jsonb_typeof(col) = 'string'` in Postgres AND the
    string, decoded, itself parses as JSON yielding an OBJECT or ARRAY.
  - A jsonb string that decodes to a scalar (number/bool/null), or that does not parse as
    JSON at all, is a LEGITIMATE string value and is left untouched.
  - Encoding can be more than two levels deep (rare, but the rule handles it): decode
    repeatedly while the current value is still a JSON-string that itself parses as JSON,
    stopping at an object/array (repair) or a scalar/non-parsing string (leave alone).

SAFETY.
  - `--dry-run` is the DEFAULT. Mutating requires the explicit `--apply` flag.
  - Every row slated for repair is dumped to a timestamped JSON file BEFORE any UPDATE
    runs (table, primary key, old raw value, decoded value) — capture once, so the change
    is reversible without re-querying prod. Written on EVERY run, dry-run included, so a
    dry-run doubles as a reviewable preview.
  - Idempotent by construction: the WHERE clause is always `jsonb_typeof(col) = 'string'`,
    and a successfully repaired row no longer matches it — re-running the script after a
    partial or full apply only ever touches rows still in the broken state.
  - Target columns are DISCOVERED from `information_schema` (all jsonb columns, all public
    tables), not hardcoded — the 9-table list in PLAN #216 is today's measurement, not a
    spec. A table with no discoverable PRIMARY KEY is skipped and reported (an UPDATE needs
    a unique target); every table in the #216 measurement has one.

CONNECTION. Deliberately does NOT import `agents.market_intelligence.db` — that module
registers a custom jsonb codec (`_json_encoder = json.dumps`) on its pool, which is
EXACTLY the mechanism that caused this bug: binding a plain Python str to a `$N::jsonb`
param through that codec would re-encode it and reintroduce the corruption this script
exists to fix. This script opens its own asyncpg connection with NO custom codec, so
asyncpg's default jsonb behaviour applies (plain str passthrough on both directions —
verified against `asyncpg/pgproto/codecs/json.pyx`): `col::text` reads always come back
as a plain string, and `json.dumps(decoded)` bound to `$1::jsonb` is written EXACTLY ONCE.
It also keeps this script decoupled from the concurrent write-path fix landing in db.py.

USAGE.
    python scripts/_216_jsonb_repair.py                 # dry-run (default) — report + dump only
    python scripts/_216_jsonb_repair.py --apply          # mutate — dump, then repair
    python scripts/_216_jsonb_repair.py --output-dir DIR # override dump location (default scratch/jsonb_repair)

Do NOT run this against production without operator awareness — that is the operator's
call, not this script's (PLAN #216, CLAUDE.md THE LINE).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
_MAX_DECODE_LEVELS = 10  # pathological-input guard; every real case here is 1-3 levels

logger = logging.getLogger("jsonb_repair")

_DEFAULT_OUTPUT_DIR = Path("scratch/jsonb_repair")

# `mi_live_trades` is CLEAN today (verified on prod 2026-08-17, PLAN #216) and MUST stay that
# way — it is live trade state, THE LINE. Excluded from the MUTATION path outright, even
# though schema-wide discovery would otherwise put it in scope the moment a string-typed row
# ever appears there (e.g. if the concurrent write-path fix regresses). The nightly guard
# (health_checks.run_jsonb_encoding_check) still COUNTS it — read-only telemetry is fine and
# is exactly the early warning you want if this table ever needs a human to look at it; only
# this script's UPDATE path is barred.
_EXCLUDED_TABLES = frozenset({"mi_live_trades"})


# ─── Pure decision logic (no DB/IO — directly testable) ────────────────────────────────


def _fully_decode(raw_text: str) -> tuple[Any | None, int]:
    """Decode a jsonb column's `::text` representation, given `jsonb_typeof` already
    confirmed the STORED value's top-level type is 'string'.

    Returns (decoded_value, levels) where:
      - decoded_value is a dict/list if the string is a repair candidate (safe to write
        back), or None if it must be LEFT ALONE (decodes to a scalar, or does not
        further parse as JSON — some string values are legitimate).
      - levels is how many json.loads() passes were applied (>=2 for any actual repair:
        one to un-quote the jsonb text form, at least one more to reach the real value).

    `raw_text` is the literal `col::text` cast — for a jsonb value whose top type is a
    JSON string, that text is itself a quoted, escaped JSON string literal (e.g.
    `"{\\"a\\": 1}"`), so the FIRST json.loads() always un-quotes it into a plain Python
    str (mirroring exactly what a jsonb-aware decoder would hand back automatically).
    Every subsequent pass asks "is this string itself further JSON-encoded?".
    """
    try:
        current = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None, 0
    if not isinstance(current, str):
        # jsonb_typeof said 'string' — this should not happen; be conservative and skip.
        return None, 0

    levels = 1
    while levels <= _MAX_DECODE_LEVELS:
        try:
            parsed = json.loads(current)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None, 0  # does not parse further as JSON -> legitimate string, leave alone
        levels += 1
        if isinstance(parsed, str):
            current = parsed
            continue  # multi-level encoding — keep unwrapping
        if isinstance(parsed, (dict, list)):
            return parsed, levels
        return None, 0  # scalar (number/bool/None) -> legitimate string, leave alone

    logger.warning("jsonb_repair: hit max decode depth (%d) — leaving value alone", _MAX_DECODE_LEVELS)
    return None, 0


# ─── DB-facing helpers (accept a conn with .fetch/.execute/.transaction — testable via mock) ──


async def _discover_jsonb_columns(conn) -> list[tuple[str, str]]:
    """All (table, column) pairs in the public schema whose type is jsonb. No hardcoded
    list — PLAN #216's 9-table measurement is today's snapshot, not a spec.

    Restricted to BASE TABLEs (excludes VIEWs): `information_schema.columns` returns view
    columns too, and a view has no primary key of its own — it would otherwise show up as a
    permanent "skipped, no PK" line and its `jsonb_typeof` scan would run the view's whole
    underlying query for nothing. Mirrors `run_db_growth_check`'s `relkind = 'r'` filter.
    """
    rows = await conn.fetch(
        """
        SELECT c.table_name, c.column_name
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_schema = c.table_schema AND t.table_name = c.table_name
        WHERE c.table_schema = 'public' AND c.data_type = 'jsonb'
          AND t.table_type = 'BASE TABLE'
        ORDER BY c.table_name, c.column_name
        """
    )
    return [(r["table_name"], r["column_name"]) for r in rows]


async def _primary_key_columns(conn, table: str) -> list[str]:
    """PK column names for `table`, in ordinal order. Empty list if the table has no PK
    (an UPDATE needs a unique target — such a table is skipped, not guessed at)."""
    rows = await conn.fetch(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = 'public' AND tc.table_name = $1
          AND tc.constraint_type = 'PRIMARY KEY'
        ORDER BY kcu.ordinal_position
        """,
        table,
    )
    return [r["column_name"] for r in rows]


async def _string_typed_rows(conn, table: str, column: str, pk_cols: list[str]) -> list[dict]:
    """Rows where `column` is a top-level jsonb STRING, with their PK values and the
    column's raw ::text form. `::text` sidesteps any client-side jsonb codec entirely —
    the result is always a plain Python str regardless of how the connection is configured."""
    pk_sql = ", ".join(f'"{c}"' for c in pk_cols)
    sql = f'''
        SELECT {pk_sql}, "{column}"::text AS col_text
        FROM "{table}"
        WHERE jsonb_typeof("{column}") = 'string'
    '''
    rows = await conn.fetch(sql)
    return [dict(r) for r in rows]


def _build_repair_plan(table: str, column: str, pk_cols: list[str], rows: list[dict]) -> dict:
    """Pure: classify each string-typed row as repair-candidate or leave-alone."""
    repairs, left_alone = [], []
    for row in rows:
        pk = {c: row[c] for c in pk_cols}
        decoded, levels = _fully_decode(row["col_text"])
        if decoded is None:
            left_alone.append({"pk": pk, "old_raw_text": row["col_text"]})
        else:
            repairs.append({
                "table": table, "column": column, "pk": pk,
                "old_raw_text": row["col_text"], "decoded": decoded, "levels": levels,
            })
    return {"table": table, "column": column, "string_typed": len(rows),
            "repairs": repairs, "left_alone": left_alone}


async def _apply_repairs(conn, plans: list[dict]) -> None:
    """Mutate. One transaction per (table, column) — a failure on one pair rolls back only
    that pair; the script is safe to re-run afterward (idempotent WHERE clause)."""
    for plan in plans:
        repairs = plan["repairs"]
        if not repairs:
            continue
        table, column = plan["table"], plan["column"]
        pk_cols = list(repairs[0]["pk"].keys())
        where_sql = " AND ".join(f'"{c}" = ${i + 2}' for i, c in enumerate(pk_cols))
        sql = f'UPDATE "{table}" SET "{column}" = $1::jsonb WHERE {where_sql}'
        tx = conn.transaction()
        async with tx:
            for r in repairs:
                params = [json.dumps(r["decoded"])] + [r["pk"][c] for c in pk_cols]
                await conn.execute(sql, *params)


# ─── Orchestration ──────────────────────────────────────────────────────────────────────


async def build_plans(conn) -> list[dict]:
    """Discover every jsonb column, then classify its string-typed rows. Tables with no PK
    are skipped (reported, not silently dropped)."""
    plans = []
    for table, column in await _discover_jsonb_columns(conn):
        if table in _EXCLUDED_TABLES:
            plans.append({"table": table, "column": column, "string_typed": None,
                          "repairs": [], "left_alone": [], "skipped_no_pk": False,
                          "skipped_excluded": True})
            continue
        pk_cols = await _primary_key_columns(conn, table)
        if not pk_cols:
            plans.append({"table": table, "column": column, "string_typed": None,
                          "repairs": [], "left_alone": [], "skipped_no_pk": True})
            continue
        rows = await _string_typed_rows(conn, table, column, pk_cols)
        if not rows:
            continue  # column is clean — no report noise for the common case
        plan = _build_repair_plan(table, column, pk_cols, rows)
        plan["skipped_no_pk"] = False
        plans.append(plan)
    return plans


def _is_skipped(p: dict) -> bool:
    """True for a plan that carries no repair work — either no PK or an explicitly
    excluded table (`_EXCLUDED_TABLES`, currently just `mi_live_trades`)."""
    return bool(p.get("skipped_no_pk") or p.get("skipped_excluded"))


def _write_dump(plans: list[dict], output_dir: Path, mode: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(_ET).strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"{mode}_{stamp}.json"
    payload = {
        "generated_at_et": datetime.now(_ET).isoformat(),
        "mode": mode,
        "tables": [
            {
                "table": p["table"], "column": p["column"],
                "string_typed": p["string_typed"],
                "skipped_no_pk": p.get("skipped_no_pk", False),
                "skipped_excluded": p.get("skipped_excluded", False),
                "repair_count": len(p["repairs"]),
                "left_alone_count": len(p["left_alone"]),
                "repairs": p["repairs"],       # full old/new values — the reversibility record
                "left_alone": p["left_alone"],  # pk + old value only, for audit
            }
            for p in plans
        ],
    }
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


def _print_report(plans: list[dict], *, applied: bool) -> None:
    total_string_typed = sum(p["string_typed"] or 0 for p in plans if not _is_skipped(p))
    total_repaired = sum(len(p["repairs"]) for p in plans)
    total_left_alone = sum(len(p["left_alone"]) for p in plans)
    skipped = [p for p in plans if _is_skipped(p)]

    print("=" * 78)
    print(f"jsonb repair — {'APPLIED' if applied else 'DRY RUN (no mutation)'}")
    print("=" * 78)
    for p in plans:
        if p.get("skipped_excluded"):
            print(f"  {p['table']}.{p['column']}: SKIPPED — excluded table (live trade state)")
            continue
        if p.get("skipped_no_pk"):
            print(f"  {p['table']}.{p['column']}: SKIPPED — no primary key found")
            continue
        verb = "repaired" if applied else "would repair"
        print(f"  {p['table']}.{p['column']}: {p['string_typed']} string-typed rows "
              f"-> {verb} {len(p['repairs'])}, left alone {len(p['left_alone'])}")
    print("-" * 78)
    print(f"TOTAL: {total_string_typed} string-typed rows across "
          f"{len([p for p in plans if not _is_skipped(p)])} column(s); "
          f"{total_repaired} {'repaired' if applied else 'would be repaired'}, "
          f"{total_left_alone} legitimately-string values left alone, "
          f"{len(skipped)} column(s) skipped (no PK / excluded)")
    print("=" * 78)


async def run(*, apply: bool, output_dir: Path, dsn: str | None = None) -> dict:
    """Full orchestration. `dsn=None` connects for real; tests pass a fake `conn` via
    `run_with_conn` instead so this stays exercisable without a live database."""
    import asyncpg  # local import: this module has no other DB dependency

    from shared.secrets import get_secrets

    conn = await asyncpg.connect(dsn=dsn or get_secrets().postgres_dsn_sync)
    try:
        return await run_with_conn(conn, apply=apply, output_dir=output_dir)
    finally:
        await conn.close()


async def run_with_conn(conn, *, apply: bool, output_dir: Path) -> dict:
    plans = await build_plans(conn)
    mode = "apply" if apply else "dryrun"
    dump_path = _write_dump(plans, output_dir, mode)  # BEFORE mutating, always

    before_counts = {(p["table"], p["column"]): p["string_typed"] for p in plans
                      if not _is_skipped(p)}

    if apply:
        await _apply_repairs(conn, plans)
        # Re-measure post-mutation so the "after" counts are real, not assumed.
        after_counts = {}
        for p in plans:
            if _is_skipped(p):
                continue
            pk_cols = await _primary_key_columns(conn, p["table"])
            rows = await _string_typed_rows(conn, p["table"], p["column"], pk_cols)
            after_counts[(p["table"], p["column"])] = len(rows)
    else:
        after_counts = before_counts  # nothing mutated

    _print_report(plans, applied=apply)
    print(f"Dump written to: {dump_path}")
    if apply:
        for key, before in before_counts.items():
            after = after_counts.get(key)
            print(f"  {key[0]}.{key[1]}: {before} -> {after} string-typed rows remaining")

    return {"plans": plans, "dump_path": str(dump_path),
            "before_counts": before_counts, "after_counts": after_counts}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true",
                     help="Mutate the database. Default is dry-run (report + dump only).")
    ap.add_argument("--output-dir", type=Path, default=_DEFAULT_OUTPUT_DIR,
                     help=f"Where to write the pre-mutation dump (default: {_DEFAULT_OUTPUT_DIR})")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(run(apply=args.apply, output_dir=args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
