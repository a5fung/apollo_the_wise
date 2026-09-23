"""Preflight gate: ban the timezone footguns that have bitten us for weeks.

THE recurring bug (CLAUDE.md ⏰ section, #180/#183 2026-06-05, 2026-04-29 false
L1, and more): wall-clock times constructed in the WRONG timezone.

Root cause, finally pinned 2026-06-05: the codebase's `_ET` was
`pytz.timezone(...)`. A pytz zone attached via `tzinfo=` (the datetime
constructor, `datetime.combine(..., tzinfo=_ET)`, or `.replace(tzinfo=_ET)`)
silently applies the historical **LMT** offset (-04:56 for New York), NOT
EDT/EST. So a "9:31 ET" bound was really ~10:27 ET — the ORB window shifted 56
minutes and the bug recurred because rules/memory relied on a human remembering.

`zoneinfo.ZoneInfo` computes the correct offset for the wall-clock time in EVERY
construction path, so once pytz is gone, `tzinfo=_ET` is always right. This gate
makes the footgun mechanically impossible to reintroduce:

  BANNED (deploy-blocking) in agents/ core/ channels/ shared/ :
    1. `import pytz` / `from pytz ...` / any `pytz.` use — the LMT footgun. Use
       `zoneinfo.ZoneInfo`. For UTC use `datetime.timezone.utc`.
    2. naive `datetime.now()` (no tz arg) — returns the container's UTC clock
       with no tzinfo, silently breaking every ET-keyed comparison. Use
       `datetime.now(_ET)`.
    3. bare `.astimezone()` (no arg) — converts to the system LOCAL zone (UTC on
       the container), a silent trap. Pass an explicit zone.

  ALSO BANNED (Phase 2, 2026-06-05 — BAN_NAIVE_UTC=True):
    4. `datetime.utcnow()` — naive UTC + deprecated in 3.12. Use
       `datetime.now(timezone.utc)`.
    5. `date.today()` / `datetime.today()` — returns the container's UTC date
       (wrong after ~8pm ET). Use `et_today()` (or `# tz-ok` if deliberately
       paired with a server-side SQL CURRENT_DATE).

  Escape hatch: append `# tz-ok: <reason>` on the offending line to whitelist a
  deliberate, reviewed exception.

Scope note: the offline `backtester/` is excluded (see EXCLUDE_SUBPATHS) — its
DB inserts use naive UTC against `timestamp` columns where aware-vs-naive matters
at the asyncpg boundary, and it carries zero live-trading risk.

Static AST walk (comments mentioning "pytz" are NOT flagged). No runtime needed.
Run: docker exec apollo-market python -m scripts.preflight_datetime_hygiene
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

# Directory roots to police — the live/orchestrator code. scripts/ and tests/
# are intentionally excluded (offline/throwaway; policing them would never go
# green and the gate would get disabled — a disabled gate is worse than none).
SCOPED_DIRS = ["agents", "core", "channels", "shared"]

# Excluded subpaths: offline backtester analysis (not live trading). Its DB
# inserts use naive UTC against `timestamp` columns where aware-vs-naive matters
# at the asyncpg boundary; policing it here would force a column-type audit for
# zero live-trading benefit. It is already pytz-free (migrated 2026-06-05).
EXCLUDE_SUBPATHS = ("backtester/", "backtester\\")

# Phase 2 (2026-06-05): the ~13 live utcnow()/date.today() sites are migrated
# (utcnow()->now(timezone.utc); date.today()->et_today()), so the full ban is on.
BAN_NAIVE_UTC = True

ESCAPE = "# tz-ok"


def _has_escape(source_lines: list[str], lineno: int) -> bool:
    if 1 <= lineno <= len(source_lines):
        return ESCAPE in source_lines[lineno - 1]
    return False


class HygieneVisitor(ast.NodeVisitor):
    def __init__(self, filepath: str, source_lines: list[str]):
        self.filepath = filepath
        self.lines = source_lines
        self.violations: list[dict] = []

    def _flag(self, lineno: int, code: str, msg: str):
        if _has_escape(self.lines, lineno):
            return
        self.violations.append(
            {"file": self.filepath, "line": lineno, "code": code, "msg": msg}
        )

    # ── 1. pytz ───────────────────────────────────────────────────────────
    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            if alias.name == "pytz" or alias.name.startswith("pytz."):
                self._flag(node.lineno, "pytz",
                           "`import pytz` — pytz as tzinfo applies the LMT "
                           "offset (-04:56). Use `zoneinfo.ZoneInfo`.")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module and (node.module == "pytz" or node.module.startswith("pytz.")):
            self._flag(node.lineno, "pytz",
                       "`from pytz ...` — use `zoneinfo.ZoneInfo` / "
                       "`datetime.timezone.utc`.")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        # any `pytz.X` reference (e.g. pytz.UTC, pytz.timezone)
        if isinstance(node.value, ast.Name) and node.value.id == "pytz":
            self._flag(node.lineno, "pytz",
                       f"`pytz.{node.attr}` — use stdlib zoneinfo/timezone.")
        self.generic_visit(node)

    # ── 2 & 3. naive now() / bare astimezone() ───────────────────────────
    def visit_Call(self, node: ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute):
            # datetime.now() / dt.now() with NO args → naive container clock
            if (func.attr == "now"
                    and isinstance(func.value, ast.Name)
                    and func.value.id in ("datetime", "dt")
                    and not node.args and not node.keywords):
                self._flag(node.lineno, "naive_now",
                           "naive `datetime.now()` — returns the container's "
                           "UTC clock with no tzinfo. Use `datetime.now(_ET)`.")
            # .astimezone() with NO args → converts to system LOCAL zone
            if func.attr == "astimezone" and not node.args and not node.keywords:
                self._flag(node.lineno, "bare_astimezone",
                           "bare `.astimezone()` — converts to the system local "
                           "zone (UTC on the container). Pass an explicit zone.")
            # Phase 2: utcnow() / date.today() / datetime.today()
            if BAN_NAIVE_UTC:
                if func.attr == "utcnow" and not node.args:
                    self._flag(node.lineno, "utcnow",
                               "`datetime.utcnow()` — naive UTC + deprecated. "
                               "Use `datetime.now(timezone.utc)`.")
                if (func.attr == "today"
                        and isinstance(func.value, ast.Name)
                        and func.value.id in ("date", "datetime")):
                    self._flag(node.lineno, "today",
                               "`date.today()` — returns the container's UTC "
                               "date (wrong after ~8pm ET). Use `et_today()`.")
        self.generic_visit(node)


def check_file(filepath: Path) -> list[dict]:
    try:
        source = filepath.read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError as e:
        print(f"WARN: syntax error parsing {filepath}: {e}", file=sys.stderr)
        return []
    v = HygieneVisitor(str(filepath), source.splitlines())
    v.visit(tree)
    return v.violations


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    all_violations: list[dict] = []
    n_files = 0
    for d in SCOPED_DIRS:
        root = repo_root / d
        if not root.exists():
            continue
        for filepath in sorted(root.rglob("*.py")):
            if any(sub in str(filepath) for sub in EXCLUDE_SUBPATHS):
                continue
            n_files += 1
            all_violations.extend(check_file(filepath))

    if not all_violations:
        print(f"Preflight datetime-hygiene check — OK "
              f"({n_files} files in {'/'.join(SCOPED_DIRS)} clean; "
              f"pytz banned, naive now()/astimezone() banned"
              f"{', utcnow()/today() banned' if BAN_NAIVE_UTC else ''}).")
        return 0

    print("DEPLOY FAILED — timezone footgun(s) detected "
          "(the LMT / naive-UTC bug class):")
    print()
    for v in all_violations:
        rel = v["file"].replace(str(repo_root) + "/", "").replace(str(repo_root) + "\\", "")
        print(f"  {rel}:{v['line']}  [{v['code']}]")
        print(f"    {v['msg']}")
    print()
    print("These silently produce WRONG wall-clock times (LMT -04:56, or the")
    print("container's UTC clock for an ET comparison). Fix, or annotate a")
    print("reviewed exception with `# tz-ok: <reason>` on the line.")
    print("Background: CLAUDE.md ⏰ section + docs root-cause 2026-06-05.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
