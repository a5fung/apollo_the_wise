"""Preflight gate + scanner: hardcoded account-mode/phase literals in production SQL.

THE BUG CLASS (operator 2026-08-11, after the get_flag_universe path-(c) rot):
a query hardcodes `AND account_mode = 'paper'` (or `phase = 'live'`). Correct the
day it ships; then the strategy GRADUATES (mi_strategies.phase changes), the book
the literal names stops moving, and the query silently reads a dead book. The
known case sat dark ~7 weeks (paper-only carryforward after MAGNA53 went live
2026-06-22: 17 live R3 rows invisible vs 1 paper). Nothing said so.

A static ban alone cannot catch this — the literal is CORRECT at ship time, and
still present-and-annotated when it rots. So this file is BOTH halves of the fix:

  1. GATE (deploy [5o/7], this file as __main__): every account-mode/phase string
     literal inside a non-docstring string in agents/ core/ channels/ shared/
     must carry a reviewed escape on the SAME line —
         `# mode-ok: <reason>`   (Python side)  or
         `-- mode-ok: <reason>`  (inside a SQL string)
     Unannotated literal → exit 1. This forces every book-pin to be a visible,
     greppable, reviewed decision — the INVENTORY.

  2. SCANNER (`collect_pinned_sites()`): the runtime graduation sweep
     (health_checks.run_account_mode_graduation_sweep) imports this to list the
     annotated sites whenever a strategy's phase actually changes or a book goes
     dormant — the rot moment, which no deploy-time check can see. The gate makes
     the inventory complete; the sweep replays it at the only time it matters.

Scope notes (narrow BY DESIGN — a guard that always fires is not a guard):
- Only STRING literals are scanned (AST walk), so Python kwargs like
  `account_mode="paper"` (explicit plumbing, mode visible at the call site) and
  comments never flag. Docstrings are excluded (they describe, not filter).
- The five mi_safeguard_state runtime toggles keyed `(<name>, "paper")`
  (_JUDGE_TOGGLE etc., db.py) are NOT literals in SQL strings and never flag:
  the `"paper"` there is a fixed namespace key both read AND written with the
  same constant — confusing, not rot. Documented in dual_account.md.
- scripts/ and tests/ are out of scope (offline analysis; policing them would
  never go green and the gate would get disabled). backtester/ excluded like
  the datetime-hygiene gate.

Run: python3 scripts/preflight_account_mode_literals.py
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCOPED_DIRS = ["agents", "core", "channels", "shared"]
EXCLUDE_SUBPATHS = ("backtester/", "backtester\\", "__pycache__")

ESCAPE = "mode-ok:"

# The environment-ish literals a graduation / phase flip invalidates.
#   account_mode = 'paper' | 'live'          — the book filter (the known rot)
#   phase = 'shadow'|'paper'|'live'|'deprecated' — the strategy-phase filter
# Single-quoted only: that is the SQL value form. (`phase IN (...)` DDL CHECK
# vocabulary deliberately not matched — it enumerates the domain, filters nothing.)
LITERAL_RE = re.compile(
    r"(?:account_mode|\bphase)\s*=\s*'(?:paper|live|shadow|deprecated)'"
)


def _docstring_line_ranges(tree: ast.AST) -> list[tuple[int, int]]:
    """(start, end) line ranges of docstrings (module/class/def body[0] strings).

    Docstrings DESCRIBE queries; they filter nothing — excluding them keeps the
    gate from crying wolf on prose like order_manager's "account_mode='live' —
    paper is deliberately excluded"."""
    out: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant) and \
                    isinstance(body[0].value.value, str):
                c = body[0].value
                out.append((c.lineno, c.end_lineno or c.lineno))
    return out


def scan_source(source: str, filepath: str) -> list[dict]:
    """Return every account-mode/phase literal outside comments and docstrings.

    Line-based scan (exact linenos even through implicit f-string concatenation,
    where AST constant linenos lie) with AST-derived docstring exclusion.
    Each hit: {file, line, text, escaped, src_line} — `escaped` True when the
    source line carries the `mode-ok:` marker (either comment style).
    """
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as e:
        print(f"WARN: syntax error parsing {filepath}: {e}", file=sys.stderr)
        return []
    doc_ranges = _docstring_line_ranges(tree)
    hits: list[dict] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("#") or stripped.startswith("--"):
            continue  # pure comment line (Python or SQL) — describes, never filters
        if any(a <= lineno <= b for a, b in doc_ranges):
            continue
        for m in LITERAL_RE.finditer(line):
            hits.append({
                "file": filepath,
                "line": lineno,
                "text": m.group(0),
                "escaped": ESCAPE in line,
                "src_line": stripped.rstrip(),
            })
    return hits


def collect_pinned_sites(root: Path = ROOT) -> list[dict]:
    """All literal sites (annotated or not) — the inventory the runtime
    graduation sweep replays. Each: {file, line, text, escaped, src_line},
    file relative to repo root."""
    sites: list[dict] = []
    for d in SCOPED_DIRS:
        base = root / d
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.py")):
            sp = str(p)
            if any(sub in sp for sub in EXCLUDE_SUBPATHS):
                continue
            try:
                source = p.read_text(encoding="utf-8")
            except (FileNotFoundError, UnicodeDecodeError):
                continue
            for h in scan_source(source, sp):
                h["file"] = str(p.relative_to(root))
                sites.append(h)
    return sites


def sites_pinned_to(value: str, sites: list[dict] | None = None) -> list[dict]:
    """Inventory subset whose literal names `value` (e.g. 'paper')."""
    if sites is None:
        sites = collect_pinned_sites()
    needle = f"'{value}'"
    return [s for s in sites if s["text"].endswith(needle)]


def main() -> int:
    sites = collect_pinned_sites()
    violations = [s for s in sites if not s["escaped"]]
    if not violations:
        print(
            f"Preflight account-mode-literal check — OK "
            f"({len(sites)} annotated book-pin(s) in {'/'.join(SCOPED_DIRS)}, "
            f"0 unannotated). Inventory replayed at graduation by "
            f"run_account_mode_graduation_sweep."
        )
        return 0
    print("DEPLOY FAILED — hardcoded account-mode/phase literal(s) without a "
          "reviewed escape (the get_flag_universe 7-weeks-dark rot class):")
    print()
    for v in violations:
        print(f"  {v['file']}:{v['line']}  {v['text']}")
        print(f"    {v['src_line'][:100]}")
    print()
    print("A mode/phase literal in a query is a bet that the environment never")
    print("changes — graduation changes it. Either resolve the mode dynamically,")
    print("drop the filter (see get_flag_universe path (c), 2026-08-11), or mark")
    print("a deliberate book-pin with `# mode-ok: <reason>` / `-- mode-ok: <reason>`")
    print("on the literal's line. Annotated pins are re-surfaced automatically on")
    print("every phase change (health_checks.run_account_mode_graduation_sweep).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
