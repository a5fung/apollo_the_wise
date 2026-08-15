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


# Gate 5 G allow-list — per docs/architecture/trade-state-ownership.md.
#
# Each entry maps a column to the set of "module.function" pairs that are
# authorized to write it. The `check` mode walks every write site and
# fails the deploy on any (column, function) not in this allow-list.
#
# Adding a new writer requires updating this list in the same commit —
# explicit ack of new co-ownership. Friction by design.
#
# Module name = file's basename without .py extension. Function name = the
# enclosing def / async def's identifier (from find_enclosing_function).
#
# Naming convention for site identity: `<module>.<function>`. Duplicate
# function names across modules are distinguished by module prefix.
#
# Last refreshed: 2026-05-17 (T1.5 / Gate 5 G ship).
ALLOWED_WRITERS: dict[str, set[str]] = {
    # ── INSERT-side only (entry creation) ──────────────────────────────
    # These columns are set once at row creation by either the primary
    # entry path (entry_pipeline._skip — confusing name; despite "_skip"
    # it's the function that INSERTs every row including non-skipped) or
    # the skipped-only path (live_tracker._insert_skipped_trade).
    "account_mode":       {"entry_pipeline._skip", "live_tracker._insert_skipped_trade"},
    "alert_date":         {"entry_pipeline._skip", "live_tracker._insert_skipped_trade"},
    "atr_14":             {"entry_pipeline._skip"},
    "catalyst_quality":   {"entry_pipeline._skip", "live_tracker._insert_skipped_trade"},
    "ep_score":           {"entry_pipeline._skip", "live_tracker._insert_skipped_trade"},
    "gap_pct":            {"entry_pipeline._skip", "live_tracker._insert_skipped_trade"},
    "orb_high":           {"entry_pipeline._skip"},
    "orb_low":            {"entry_pipeline._skip"},
    "position_size":      {"entry_pipeline._skip"},
    "proposed_at":        {"entry_pipeline._skip"},
    "regime":             {"entry_pipeline._skip", "live_tracker._insert_skipped_trade"},
    "risk_dollars":       {"entry_pipeline._skip"},
    "signal_type":        {"entry_pipeline._skip", "live_tracker._insert_skipped_trade", "db.initialize_schema"},
    "ticker":             {"entry_pipeline._skip", "live_tracker._insert_skipped_trade"},

    # ── Entry-fill lifecycle ───────────────────────────────────────────
    "entry_order_id":     {"order_manager.submit_entry", "order_manager._submit", "order_manager.attempt_day1_reentry", "order_manager.cancel_unfilled_entries"},  # _submit = #500 relocated entry-write (multi-col atomic; same as submit_entry)
    "entry_price":        {"entry_pipeline._skip", "order_manager.check_fills", "trade_stream._process_entry_fill"},
    "entry_shares":       {"entry_pipeline._skip", "order_manager.check_fills", "trade_stream._process_entry_fill"},
    "filled_at":          {"order_manager.check_fills", "order_manager.attempt_day1_reentry", "trade_stream._process_entry_fill"},
    "confirmed_at":       {"entry_pipeline._skip", "telegram_confirm.handle_callback"},
    "entry_attempt":      {"order_manager.attempt_day1_reentry"},

    # ── Stop management (KLAR/CRMD strict-ownership column) ────────────
    # T1.1/T1.2/T1.4 (2026-05-17) cut writers 7 → 4. T1.3 (2026-05-18)
    # removed live_tracker close-path writer by delegating to
    # finalize_stop_fill. Now 3 writers: INSERT, trail update, polling
    # backup. update_stop owns trail. entry_pipeline._skip sets initial.
    # check_fills writes on poll-fill backup (no-op for stop in normal
    # ordering since stop_price unchanged from INSERT at that point).
    # +execute_partial_exit 2026-08-10 (#548 resting mode): it is the ONLY place that
    # moves the stop price WITHOUT going through update_stop's cancel-then-new — it does
    # an atomic price-only `replace_order` on the reduced stop, precisely to avoid the
    # unprotected window a cancel-then-new opens on a live position. Delegating to
    # update_stop would reintroduce that window, so this write is authorized here rather
    # than refactored away. It fires ONLY after the successor stop is CONFIRMED live at
    # the broker; the unconfirmed branch deliberately withholds the write (DB understating
    # protection is the safe direction — pinned in test_resting_mode_breakeven_548.py).
    "stop_price":         {"entry_pipeline._skip", "order_manager.update_stop", "order_manager.check_fills",
                           "order_manager.execute_partial_exit"},
    # hard_stop: SINGLE WRITER (entry_pipeline._skip INSERT only). Per Gate 3
    # initial-stop modeling (2026-05-18) — hard_stop is the immutable
    # risk-basis for R-expectancy calc, set once at INSERT, never updated.
    # check_fills removed as a writer 2026-05-18 (previously wrote
    # hard_stop = trade["stop_price"] which could corrupt initial basis
    # if the polling backup ran after a same-tick trail update).
    "hard_stop":          {"entry_pipeline._skip"},
    "stop_order_id":      {
        # T1.5a (2026-05-18): set_stop_order_id helper is the single
        # authorized writer for SOLO stop_order_id mutations. All 11 solo
        # call sites refactored 2026-05-18 (parts 1 + 2). Multi-column
        # atomic closes (e.g. submit_entry, check_fills, finalize_*,
        # attempt_day1_reentry, _sync_positions_for_mode close path,
        # _process_entry_fill via COALESCE) stay inline and remain
        # authorized writers — splitting them would lose atomicity.
        "order_manager.set_stop_order_id",  # T1.5a helper — SOLO mutations
        "order_manager.submit_entry", "order_manager._submit",  # _submit = #500 relocated entry-write (multi-col atomic)
        "order_manager.check_fills",
        "order_manager.update_stop", "order_manager.attempt_day1_reentry",
        "order_manager._finalize_full_exit_locked", "order_manager._finalize_stop_fill_locked",
        # #566 (2026-08-15): a partial fill that exhausts the position now CLOSES
        # the trade atomically (status/closed_at/stop_order_id in the same UPDATE
        # as exits/remaining) — the last shares can leave via the carve-out limit
        # once a partial-qty stop fill no longer zeroes the row.
        "order_manager._finalize_partial_exit_locked",
        "order_manager._sync_positions_for_mode",
        "trade_stream._process_entry_fill", "trade_stream._process_stop_fill",
    },

    # ── Exit lifecycle ─────────────────────────────────────────────────
    # T1.3 (2026-05-18) removed live_tracker.update_open_positions_live
    # from exits / remaining_shares / total_pnl / closed_at — close-path
    # delegated to finalize_stop_fill which is the canonical writer.
    "exits":              {
        "order_manager.attempt_day1_reentry", "order_manager._finalize_partial_exit_locked",
        "order_manager._finalize_full_exit_locked", "order_manager._finalize_stop_fill_locked",
        "trade_stream._process_stop_fill",
    },
    "remaining_shares":   {
        "order_manager.check_fills", "order_manager.attempt_day1_reentry",
        "order_manager._finalize_partial_exit_locked", "order_manager._finalize_full_exit_locked",
        "order_manager._finalize_stop_fill_locked", "order_manager._sync_positions_for_mode",
        "trade_stream._process_entry_fill", "trade_stream._process_stop_fill",
    },
    "total_pnl":          {
        "order_manager.attempt_day1_reentry", "order_manager._finalize_partial_exit_locked",
        "order_manager._finalize_full_exit_locked", "order_manager._finalize_stop_fill_locked",
        "order_manager.cancel_unfilled_entries", "trade_stream._process_stop_fill",
    },
    "closed_at":          {
        "order_manager.attempt_day1_reentry", "order_manager._finalize_full_exit_locked",
        "order_manager._finalize_stop_fill_locked", "order_manager.cancel_unfilled_entries",
        # #566: close-at-zero — see stop_order_id note above.
        "order_manager._finalize_partial_exit_locked",
        "order_manager._sync_positions_for_mode", "trade_stream._process_stop_fill",
    },

    # ── BW strict-ownership columns (single owner each) ────────────────
    # 2026-05-14 BW incident: wrapping UPDATE in live_tracker wrote
    # partial_taken=TRUE optimistically. c0fa67f fix moved write to
    # finalize_partial_exit. Strict-single-owner enforcement now.
    "partial_taken":      {"order_manager._finalize_partial_exit_locked"},
    "breakeven_active":   {"order_manager._finalize_partial_exit_locked", "live_tracker.update_open_positions_live"},

    # ── live_tracker-domain columns (computed by state machine) ────────
    "hold_days":          {"live_tracker.update_open_positions_live"},
    "running_closes":     {"live_tracker.update_open_positions_live"},

    # ── Position-extreme tracking ──────────────────────────────────────
    "lowest_price_seen":  {"order_manager.track_open_position_extremes", "trade_stream._process_entry_fill"},
    "highest_price_seen": {"order_manager.track_open_position_extremes", "trade_stream._process_entry_fill"},

    # ── Status / skip_reason (FSM-style; many legitimate writers) ──────
    # advisor 2026-05-17: skip FSM-style enforcement. Document the set
    # but allow many writers per the state machine.
    "status":             {
        # #436 (operator-signed 2026-07-17): the stale-proposal reaper — set-based
        # UPDATE, bounded to pending_confirmation + NULL entry_order_id + prior-ET-day
        # + per-account_mode; the ONLY writer of status='expired'.
        "order_manager.expire_stale_proposals",
        "entry_pipeline._skip", "live_tracker._insert_skipped_trade",
        # T1.3 (2026-05-18) removed live_tracker.update_open_positions_live —
        # close-path status='closed' write now delegated to finalize_stop_fill.
        "order_manager.submit_entry", "order_manager._submit",  # _submit = #500 relocated entry-write (multi-col atomic)
        "order_manager.check_fills",
        "order_manager.attempt_day1_reentry", "order_manager._finalize_full_exit_locked",
        "order_manager._finalize_stop_fill_locked", "order_manager.cancel_unfilled_entries",
        # #566: close-at-zero — see stop_order_id note above.
        "order_manager._finalize_partial_exit_locked",
        "order_manager._sync_positions_for_mode", "order_manager._update_trade_status",
        "telegram_confirm.handle_callback",
        "trade_stream._handle_fill", "trade_stream._process_entry_fill",
        "trade_stream._process_stop_fill", "trade_stream._handle_cancel_or_reject",
    },
    "skip_reason":        {
        # #436 (operator-signed 2026-07-17): the stale-proposal reaper — set-based
        # UPDATE, bounded to pending_confirmation + NULL entry_order_id + prior-ET-day
        # + per-account_mode; the ONLY writer of status='expired'.
        "order_manager.expire_stale_proposals",
        "live_tracker._insert_skipped_trade",
        "order_manager.attempt_day1_reentry", "order_manager.cancel_unfilled_entries",
        "order_manager._update_trade_status",
        "telegram_confirm.handle_callback",
        "trade_stream._process_entry_fill", "trade_stream._handle_cancel_or_reject",
    },
}

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
        # Gate 5 G (2026-05-17 T1.5 ship): compare every column-write site
        # against ALLOWED_WRITERS. Exit non-zero on any unauthorized pair.
        violations: list[dict] = []
        for s in all_sites:
            # Module identity = file basename without .py.
            file_path = Path(s["file"])
            module = file_path.stem
            func = s["function"]
            site_id = f"{module}.{func}"
            for col in s["columns"]:
                allowed = ALLOWED_WRITERS.get(col)
                if allowed is None:
                    # Column not in allow-list at all — strict gate: any
                    # new column write needs an explicit ALLOWED_WRITERS
                    # entry to acknowledge ownership.
                    violations.append({
                        "site": site_id,
                        "file": s["file"], "line": s["line"],
                        "column": col, "kind": s["kind"],
                        "reason": "column not in ALLOWED_WRITERS — new column requires explicit ownership entry",
                        "allowed": None,
                    })
                elif site_id not in allowed:
                    violations.append({
                        "site": site_id,
                        "file": s["file"], "line": s["line"],
                        "column": col, "kind": s["kind"],
                        "reason": "writer not in column's ALLOWED_WRITERS set",
                        "allowed": sorted(allowed),
                    })

        if not violations:
            print(f"Gate 5 G column-write authority check — OK ({len(all_sites)} sites verified clean against ALLOWED_WRITERS).")
            return 0

        print(f"Gate 5 G column-write authority check — FAIL ({len(violations)} violation(s)):\n")
        for v in violations:
            print(f"UNAUTHORIZED COLUMN WRITER:")
            print(f"  file:    {v['file']}:{v['line']}")
            print(f"  writer:  {v['site']}  [{v['kind']}]")
            print(f"  column:  {v['column']}")
            print(f"  reason:  {v['reason']}")
            if v["allowed"] is not None:
                print(f"  Allowed writers: {', '.join(v['allowed'])}")
            print(f"  Fix: either")
            print(f"    (a) add '{v['site']}' to ALLOWED_WRITERS['{v['column']}'] in scripts/audit_column_writes.py")
            print(f"    (b) refactor {v['site']} to call the authorized writer instead")
            print()
        return 1

    print(f"Unknown mode: {mode}")
    return 2


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "audit"
    sys.exit(main(mode))
