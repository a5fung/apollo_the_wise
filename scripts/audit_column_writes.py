"""Static analysis of every UPDATE/INSERT site that writes to mi_live_trades.

Builds a column → writer-site matrix for trade-state ownership review
(Gate 5 G, 2026-05-15). Designed to:

1. Phase 1 (Friday audit): enumerate every write site + columns it touches.
   Output → docs/architecture/trade-state-ownership.md raw input.

2. Phase 2 (Sunday Gate 5 G): compare against ALLOWED_WRITERS allow-list.
   Any column written from a site NOT in the allow-list → exit non-zero.
   Wires into scripts/deploy.sh as `[5c/5] column-write authority`.

Approach: parse each `UPDATE mi_live_trades SET ... WHERE` block, extract
column names from the SET clause. Map to (file, line, enclosing-function).
This catches the recurring "second-write clobber" class (CRMD/KLAR-style).

Limitations:
- Regex-based parsing — multiline UPDATEs handled, but dynamic SQL
  string-concat would be invisible (none exist in our codebase per inspection)
- Doesn't catch bypass via raw conn.execute with template strings
- INSERT statements treated as 'initial write' authority for every column
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TARGET = "mi_live_trades"

# Match an UPDATE block: from `UPDATE mi_live_trades SET` up to first
# `WHERE` (case-insensitive, multiline). Captures the SET clause.
UPDATE_RE = re.compile(
    rf"UPDATE\s+{TARGET}(?:\s+\w+)?\s+SET\s+(.*?)\s+WHERE\b",
    re.IGNORECASE | re.DOTALL,
)
# Match column = ... (column = anything until next column or end)
COLUMN_RE = re.compile(r"\b(\w+)\s*=")
# Match INSERT (...) — capture the column list
INSERT_RE = re.compile(
    rf"INSERT\s+INTO\s+{TARGET}\s*\(([^)]+)\)",
    re.IGNORECASE | re.DOTALL,
)


def extract_columns_from_set_clause(set_clause: str) -> set[str]:
    """Extract column names from `col1 = ..., col2 = ...`.

    Handles:
    - simple: `status = 'filled'`
    - expressions: `total_pnl = $4, partial_taken = TRUE`
    - jsonb: `exits = $2::jsonb`
    - functions: `filled_at = NOW(), closed_at = NOW()`
    - COALESCE: `lowest_price_seen = COALESCE(lowest_price_seen, $6)` —
      only the LEFT side of = is the target column

    Strategy: split on commas at top-level (not inside parens), then
    extract first identifier before = on each chunk.
    """
    cols: set[str] = set()
    depth = 0
    chunk = ""
    chunks: list[str] = []
    for ch in set_clause:
        if ch == "(":
            depth += 1
            chunk += ch
        elif ch == ")":
            depth -= 1
            chunk += ch
        elif ch == "," and depth == 0:
            chunks.append(chunk)
            chunk = ""
        else:
            chunk += ch
    if chunk.strip():
        chunks.append(chunk)
    for c in chunks:
        m = re.match(r"\s*(\w+)\s*=", c)
        if m:
            cols.add(m.group(1))
    return cols


def find_enclosing_function(text: str, byte_offset: int) -> str:
    """Walk backward from byte_offset to find the most recent
    `def funcname(` or `async def funcname(`. Returns funcname or '<module>'."""
    prefix = text[:byte_offset]
    matches = list(re.finditer(r"^\s*(async\s+def|def)\s+(\w+)\s*\(", prefix, re.MULTILINE))
    if matches:
        return matches[-1].group(2)
    return "<module>"


def audit_file(path: Path) -> list[dict]:
    """Return list of {file, line, function, kind, columns} for every write site."""
    text = path.read_text(encoding="utf-8")
    results: list[dict] = []

    # INSERTs first.
    for m in INSERT_RE.finditer(text):
        col_list = m.group(1)
        cols = {c.strip() for c in col_list.split(",") if c.strip()}
        # Filter to actual column names (skip line comments, whitespace).
        cols = {c for c in cols if re.match(r"^\w+$", c)}
        line = text[: m.start()].count("\n") + 1
        func = find_enclosing_function(text, m.start())
        results.append({
            "file": str(path.relative_to(ROOT)),
            "line": line,
            "function": func,
            "kind": "INSERT",
            "columns": sorted(cols),
        })

    # UPDATEs.
    for m in UPDATE_RE.finditer(text):
        set_clause = m.group(1)
        cols = extract_columns_from_set_clause(set_clause)
        line = text[: m.start()].count("\n") + 1
        func = find_enclosing_function(text, m.start())
        results.append({
            "file": str(path.relative_to(ROOT)),
            "line": line,
            "function": func,
            "kind": "UPDATE",
            "columns": sorted(cols),
        })

    return results


def main(mode: str = "audit") -> int:
    py_files = []
    for d in [ROOT / "agents/market_intelligence"]:
        py_files.extend(d.rglob("*.py"))
    py_files = [p for p in py_files if "test_" not in p.name and "__pycache__" not in str(p)]

    all_sites: list[dict] = []
    for p in py_files:
        sites = audit_file(p)
        all_sites.extend(sites)

    if mode == "audit":
        # Print column → writer-sites matrix.
        column_to_sites: dict[str, list[dict]] = {}
        for s in all_sites:
            for col in s["columns"]:
                column_to_sites.setdefault(col, []).append(s)
        print(f"# mi_live_trades column-writer audit\n")
        print(f"Total write sites: {len(all_sites)} ({sum(1 for s in all_sites if s['kind'] == 'INSERT')} INSERT, {sum(1 for s in all_sites if s['kind'] == 'UPDATE')} UPDATE)")
        print(f"Distinct columns written: {len(column_to_sites)}\n")
        for col in sorted(column_to_sites.keys()):
            sites = column_to_sites[col]
            print(f"## {col}  ({len(sites)} writers)")
            for s in sites:
                print(f"  - {s['file']}:{s['line']}  `{s['function']}`  [{s['kind']}]")
            print()
        return 0

    elif mode == "check":
        # Phase 2 (Sunday Gate 5 G): compare against ALLOWED_WRITERS.
        # For now (Phase 1), this branch just emits a placeholder.
        print("Gate 5 G column-write authority check — not yet implemented.")
        print("Phase 2 (Sunday): load ALLOWED_WRITERS, exit non-zero on violations.")
        return 0

    print(f"Unknown mode: {mode}")
    return 2


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "audit"
    sys.exit(main(mode))
