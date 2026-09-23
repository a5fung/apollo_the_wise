"""ADR 0008 increment 1 — write-side regression FENCE for trade-state demotions.

A "demotion" = a write that REMOVES protection/liveness from a trade in the DB:
  - `stop_order_id` -> NULL  (DB now believes the position has no stop = naked)
  - `status`        -> 'closed'  (DB now believes the trade is over)
nulled/closed via SQL `UPDATE mi_live_trades SET ...` OR the helper
`set_stop_order_id(trade_id, None, ...)`.

THE STRUCTURAL TARGET (advisor 2026-06-06): a demotion write **lexically inside
an `except` / error-handling block.** That is exactly the 2026-06-04 false-naked
shape — the partial-exit nulled stop_order_id in an except handler after a failed
op, WITHOUT a confirming broker read; the broker actually still had stops
(over-covered), so the DB lied "naked". A demotion driven by a caught exception is
INFERENCE from a failed op, which ADR 0008 forbids: only a *confirmed broker
read/event* may demote trade state.

Each flagged (except-enclosed) demotion must carry an explicit reviewed escape
  `# broker-confirmed: <reason>`
somewhere in its enclosing except block — asserting a human checked that the
demotion is justified by a real broker read/event (or is the deliberate fail-safe
direction), not blind inference. Missing tag -> `check` mode FAILS.

HONEST SCOPE (do NOT overclaim — advisor 2026-06-06):
  - This is a regression FENCE + residual surfacer, NOT a "kills the class at the
    source" fix. "Broker-confirmed" is a control-flow property a comment cannot
    verify; the real source-fix is the runtime chokepoint (a demote helper that
    REQUIRES the broker read as an argument) — ADR increment 3 / next-week paper.
  - Fences the 6/4 false-naked class (except-path demotion). Does NOT cover the
    5/27 mass-close (acting on an empty/degraded broker READ — a runtime property,
    #137-guarded, increment 3). A green gate here does not imply 5/27 safety.
  - The naked *alert* is already broker-gated by audit_invariants.classify_naked_
    positions (#140). This gate is SQL/helper demotion WRITES only.

Modes:
  audit  — enumerate every demotion write (except-enclosed or not) + tag status.
  check  — exit non-zero on any except-enclosed demotion lacking a tag.

Reuses `audit_column_writes.UPDATE_RE` so only SET-clause writes match (the grep
showed status='closed' is overwhelmingly WHERE/FILTER *reads* — a fresh regex
would drown in them).
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_column_writes import UPDATE_RE  # SET-clause-only matcher

ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = [ROOT / "agents/market_intelligence"]

# Demotion signatures inside an `UPDATE mi_live_trades SET ...` SET clause.
# Value-aware: `stop_order_id = $2` (a NEW id) is a PROMOTION, not a demotion —
# only a literal NULL demotes. status='closed' is the close demotion.
_DEMOTION_IN_SET = [
    ("stop_order_id->NULL", re.compile(r"\bstop_order_id\s*=\s*NULL\b", re.I)),
    ("status->'closed'", re.compile(r"\bstatus\s*=\s*'closed'", re.I)),
]
# Helper null-demotion at a CALL site: set_stop_order_id(<trade_id>, None, ...).
# (The helper's own internal UPDATE is parametrised `= $1`, never a literal NULL,
# so the demotion intent lives at the call site's None argument.)
_SET_STOP_NULL = re.compile(r"set_stop_order_id\s*\(\s*[^,]+,\s*None\b")
_TAG = re.compile(r"#\s*broker-confirmed:")


def _except_ranges(text: str) -> list[tuple[int, int]]:
    """(start_line, end_line) for every `except ...:` handler body. AST gives
    precise, nesting-correct block ranges (regex can't track block nesting)."""
    ranges: list[tuple[int, int]] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ranges
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            ranges.append((node.lineno, node.end_lineno or node.lineno))
    return ranges


def _line_of(text: str, offset: int) -> int:
    return text[:offset].count("\n") + 1


def _enclosing_except(line: int, ranges: list[tuple[int, int]]) -> tuple[int, int] | None:
    # Innermost (smallest) enclosing except block, if any.
    hits = [(s, e) for s, e in ranges if s <= line <= e]
    return min(hits, key=lambda r: r[1] - r[0]) if hits else None


def _block_has_tag(lines: list[str], rng: tuple[int, int]) -> bool:
    s, e = rng
    return any(_TAG.search(ln) for ln in lines[s - 1 : e])


def audit_text(text: str, name: str = "<text>") -> list[dict]:
    """Demotion sites in a source string. The testable seam — `audit_file`
    wraps this with the on-disk path."""
    lines = text.splitlines()
    ranges = _except_ranges(text)
    sites: list[dict] = []

    def _record(kind: str, line: int):
        exc = _enclosing_except(line, ranges)
        sites.append({
            "file": name,
            "line": line,
            "kind": kind,
            "in_except": exc is not None,
            "tagged": _block_has_tag(lines, exc) if exc else False,
        })

    # SQL demotions inside an UPDATE mi_live_trades SET clause.
    for m in UPDATE_RE.finditer(text):
        set_clause = m.group(1)
        for kind, pat in _DEMOTION_IN_SET:
            if pat.search(set_clause):
                _record(kind, _line_of(text, m.start()))

    # Helper null-demotions at call sites.
    for m in _SET_STOP_NULL.finditer(text):
        _record("set_stop_order_id(None)", _line_of(text, m.start()))

    return sites


def audit_file(path: Path) -> list[dict]:
    return audit_text(path.read_text(encoding="utf-8"), str(path.relative_to(ROOT)))


def _all_sites() -> list[dict]:
    out: list[dict] = []
    for d in SCAN_DIRS:
        for p in d.rglob("*.py"):
            if "test_" in p.name or "__pycache__" in str(p):
                continue
            out.extend(audit_file(p))
    return out


def main(mode: str = "audit") -> int:
    sites = _all_sites()
    flagged = [s for s in sites if s["in_except"]]            # gate-relevant
    violations = [s for s in flagged if not s["tagged"]]

    if mode == "audit":
        print("# Trade-state demotion audit (ADR 0008 increment 1)\n")
        print(f"Total demotion writes: {len(sites)} "
              f"({len(flagged)} inside except blocks)\n")
        for s in sites:
            loc = "EXCEPT" if s["in_except"] else "normal"
            tag = "" if not s["in_except"] else ("  [tagged]" if s["tagged"] else "  [UNTAGGED]")
            print(f"  {loc:<6}  {s['file']}:{s['line']}  {s['kind']}{tag}")
        print(f"\nExcept-enclosed demotions WITHOUT a broker-confirmed tag: "
              f"{len(violations)}")
        return 0

    if mode == "check":
        if not violations:
            print(f"ADR 0008 demotion fence — OK "
                  f"({len(flagged)} except-enclosed demotion(s), all tagged).")
            return 0
        print(f"ADR 0008 demotion fence — FAIL ({len(violations)} violation(s)):\n")
        for v in violations:
            print("UNCONFIRMED TRADE-STATE DEMOTION IN ERROR PATH:")
            print(f"  file:   {v['file']}:{v['line']}")
            print(f"  write:  {v['kind']}  (inside an except/error block)")
            print(f"  why:    a demotion driven by a caught exception is INFERENCE")
            print(f"          from a failed op — ADR 0008 forbids it without a")
            print(f"          confirming broker read/event.")
            print(f"  fix:    either")
            print(f"    (a) read the broker to CONFIRM the demoted state, then add")
            print(f"        `# broker-confirmed: <reason>` in the except block; or")
            print(f"    (b) route through the demote-helper (increment 3) that takes")
            print(f"        the broker read as a required argument.")
            print()
        return 1

    print(f"Unknown mode: {mode}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "audit"))
