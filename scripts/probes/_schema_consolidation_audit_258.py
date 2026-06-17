#!/usr/bin/env python3
"""#258 step 1 (throwaway audit) — evidence for the initialize_schema() consolidation.

Read-only. Classifies every `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in db.py
against (a) the CREATE-TABLE column sets parsed from the same file and (b) the LIVE
prod schema (scripts/_prod_columns_258.tsv = information_schema.columns from prod).

Each ALTER (table T, column C) lands in one bucket:
  REDUNDANT  C is in a CREATE def AND present in live prod  -> ALTER is a no-op on
             prod and a fresh DB still gets C from CREATE   -> SAFE TO DROP.
  FOLD       C present in live prod but NOT in any CREATE def -> a fresh DB would
             MISS C; fold C into the CREATE, then the ALTER only migrates old DBs.
  KEEP       C in a CREATE def but ABSENT from live prod     -> prod's table predates
             C; the ALTER is the live migration -> must stay.
  ANOMALY    C neither in a CREATE def nor in live prod      -> investigate.

The REDUNDANT list is the provably-safe-to-remove set for the (post-gate) edit.
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "agents" / "market_intelligence" / "db.py"
TSV = Path(__file__).resolve().parent / "_prod_columns_258.tsv"

src = DB.read_text(encoding="utf-8")

# ── live prod columns ────────────────────────────────────────────────────────
live: dict[str, set[str]] = defaultdict(set)
for line in TSV.read_text(encoding="utf-8").splitlines():
    line = line.rstrip("\r")
    if "\t" not in line:
        continue
    t, c = line.split("\t", 1)
    live[t.strip()].add(c.strip().lower())

# ── CREATE TABLE column sets (paren-balanced top-level item scan) ─────────────
create_cols: dict[str, set[str]] = defaultdict(set)
_CONSTRAINT = re.compile(r"^\s*(PRIMARY\s+KEY|FOREIGN\s+KEY|CONSTRAINT|UNIQUE|CHECK)\b", re.I)
for m in re.finditer(r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\(", src):
    table = m.group(1)
    i = m.end() - 1          # at the opening '('
    depth = 0
    body_start = m.end()
    end = None
    while i < len(src):
        ch = src[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                end = i
                break
        i += 1
    if end is None:
        continue
    body = src[body_start:end]
    # split top-level items by commas not nested in parens
    items, buf, d = [], [], 0
    for ch in body:
        if ch == "(":
            d += 1
        elif ch == ")":
            d -= 1
        if ch == "," and d == 0:
            items.append("".join(buf)); buf = []
        else:
            buf.append(ch)
    if buf:
        items.append("".join(buf))
    for item in items:
        item = item.strip()
        if not item or _CONSTRAINT.match(item):
            continue
        col = re.match(r"(\w+)", item)
        if col:
            create_cols[table].add(col.group(1).lower())

# ── ALTER ADD COLUMN sites ───────────────────────────────────────────────────
alters = []  # (table, col, lineno)
for n, line in enumerate(src.splitlines(), 1):
    a = re.search(r"ALTER TABLE\s+(\w+)\s+ADD COLUMN IF NOT EXISTS\s+(\w+)", line, re.I)
    if a:
        alters.append((a.group(1), a.group(2).lower(), n))

# ── classify ─────────────────────────────────────────────────────────────────
buckets = {"REDUNDANT": [], "FOLD": [], "KEEP": [], "ANOMALY": []}
for table, col, n in alters:
    in_create = col in create_cols.get(table, set())
    in_live = col in live.get(table, set())
    if in_create and in_live:
        buckets["REDUNDANT"].append((table, col, n))
    elif in_live and not in_create:
        buckets["FOLD"].append((table, col, n))
    elif in_create and not in_live:
        buckets["KEEP"].append((table, col, n))
    else:
        buckets["ANOMALY"].append((table, col, n))

# ── report ───────────────────────────────────────────────────────────────────
print(f"db.py: {DB}")
print(f"live prod tables: {len(live)}  |  CREATE defs parsed: {len(create_cols)}  |  ALTER sites: {len(alters)}")
print(f"tables in CREATE but NOT live prod: {sorted(set(create_cols) - set(live)) or 'none'}")
print()
for name in ("REDUNDANT", "FOLD", "KEEP", "ANOMALY"):
    rows = buckets[name]
    print(f"=== {name}  ({len(rows)}) ===")
    for table, col, n in sorted(rows):
        print(f"  L{n:<5} {table}.{col}")
    print()
print(f"SUMMARY: REDUNDANT(drop-safe)={len(buckets['REDUNDANT'])} "
      f"FOLD(into-create)={len(buckets['FOLD'])} KEEP(live-migration)={len(buckets['KEEP'])} "
      f"ANOMALY={len(buckets['ANOMALY'])}  of {len(alters)} ALTERs")
sys.exit(0)
