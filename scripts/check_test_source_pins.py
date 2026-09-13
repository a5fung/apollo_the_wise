"""Pre-commit gate: a NEW or EDITED test may not assert on SOURCE TEXT instead of behaviour (#653).

THE PROBLEM (measured 2026-09-12): 285 of 5,881 test functions across 120 files assert on the
literal text of a production module — `inspect.getsource(fn)`, `Path("agents/.../x.py").read_text()`,
`open("scripts/deploy.sh")` — rather than on what the code DOES. 32 of them broke the same day
against a refactor (`send_telegram_message(md_to_html(text), parse_mode="HTML")` replacing a bare
legacy-Markdown call) that changed NO behaviour whatsoever, and that friction is part of why a
correct cleanup was abandoned that day (see CLAUDE.md 2026-09-12). A test that blocks a safe
refactor and misses a real defect (see #649 the same week: 20 green tests, dead code) is paying
twice.

THIS GATE, same shape as `check_plan._review_can_fire_gate` (2026-09-09's eleven-bad-reviews fix):
scoped to tests ADDED or CHANGED versus origin/main. **The existing ~285 are a surfaced backlog,
not a wall** — this gate never touches them unless someone edits the function they live in. It
also prints the whole-repo count on every run (DoD #2) so the trend is visible; that print is
informational, never blocking, because the backlog shrinking is a choice, not a per-commit tax.

WHAT COUNTS (deliberately narrow — see `docs/testing/test_discipline.md` for the written rule this
gate enforces): a `test_*` function whose body (a) contains at least one `assert`, AND (b) reads or
references the SOURCE of a file under `agents/ scripts/ channels/ core/ shared/` — via
`inspect.getsource(...)`, `<path>.read_text()`, `open(<path>)` (or the equivalent
`with open(...) as f: ... f.read()`), a module-level variable holding one of those reads (the
`HEALTH = Path(...).read_text()` pattern this repo already uses), or a same-file helper function
that returns one of those reads (the `_src(obj): return inspect.getsource(obj)` pattern). Reading a
DATA file — a `.tsv` fixture, a `.json` baseline, `PLAN.md`, a docs `.md` — is NOT a source pin:
only `.py`/`.sh` paths under the five scoped dirs count.

ESCAPE: a `# source-pin-ok: <why behaviour cannot be exercised>` comment anywhere in the function's
own line range, with a real reason (>=12 chars, same floor `can_fire_missing` uses elsewhere in
this repo for "not a bare marker"). A wiring check that a correct function is actually CALLED is a
real thing this repo has been burned by missing (a correct helper nobody called) — the escape lets
that stay, reviewed, rather than banning source pins outright.

Static AST walk; heuristic, not exhaustive (same posture as `preflight_no_silent_failures.py` and
`preflight_account_mode_literals.py` — both heuristic AST scanners with a reviewed escape hatch).
False positives are the safe failure mode here (the escape is one comment away); false negatives
are not, so detection errs toward flagging.

Run: python3 scripts/check_test_source_pins.py
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TESTS_DIR = REPO / "tests"
BASELINE_PATH = Path(__file__).resolve().parent / "test_source_pin_baseline.json"

SCOPED_DIR_NAMES = ("agents", "scripts", "channels", "core", "shared")
SOURCE_EXTS = (".py", ".sh")

ESCAPE_MARKER = "source-pin-ok"
_ESCAPE_RE = re.compile(r"#\s*source-pin-ok:\s*(.+)")
_ESCAPE_REASON_FLOOR = 12   # "yes" / "wiring check" are not reasons; same floor as can_fire_missing

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


# ── low-level AST predicates (pure — each is unit-testable on a raw string) ─────────────────

def _literal_strings(node: ast.AST) -> list:
    return [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _looks_like_scoped_source_path(node: ast.AST, path_vars: dict) -> bool:
    """True if the literal strings reachable from `node` (plus any named path-variable it
    references) spell a path under one of the five scoped dirs, ending in a source extension.

    Deliberately excludes docs/data files: a `.tsv`/`.json`/`.yaml`/`.md` read never matches
    because it never ends in `.py`/`.sh` — the false-positive case CLAUDE.md/#653 calls out
    by name (a fixture, a baseline, PLAN.md, a docs file).
    """
    lits = list(_literal_strings(node))
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id in path_vars:
            lits.extend(path_vars[n.id])
    if not lits:
        return False
    has_scoped_dir = any(part in SCOPED_DIR_NAMES
                          for s in lits for part in s.replace("\\", "/").split("/"))
    has_source_ext = any(s.endswith(ext) for s in lits for ext in SOURCE_EXTS)
    return has_scoped_dir and has_source_ext


def _is_getsource_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    if isinstance(f, ast.Attribute) and f.attr == "getsource":
        return True
    if isinstance(f, ast.Name) and f.id == "getsource":
        return True
    return False


def _is_read_text_call(node: ast.AST, path_vars: dict) -> bool:
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "read_text"):
        return False
    return _looks_like_scoped_source_path(node.func.value, path_vars)


def _is_scoped_open_call(node: ast.AST, path_vars: dict) -> bool:
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open"):
        return False
    if not node.args:
        return False
    return _looks_like_scoped_source_path(node.args[0], path_vars)


def _is_scoped_open_read(node: ast.AST, path_vars: dict, file_handles: set) -> bool:
    """`open(<scoped path>).read()` inline, or `f.read()` where `f` came from
    `with open(<scoped path>) as f:`."""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "read"):
        return False
    v = node.func.value
    if _is_scoped_open_call(v, path_vars):
        return True
    return isinstance(v, ast.Name) and v.id in file_handles


def _is_inline_source_read(node: ast.AST, path_vars: dict, file_handles: set) -> bool:
    return (_is_getsource_call(node) or _is_read_text_call(node, path_vars)
            or _is_scoped_open_read(node, path_vars, file_handles))


# ── whole-file resolution: path variables, file handles, helper functions, atoms ────────────

def _collect_path_vars(tree: ast.AST) -> dict:
    """`NAME = <literal path expression>` (NOT itself a source-read) -> its literal fragments.

    Supports the `DB_PY = REPO / "agents" / "x.py"` ... `DB_PY.read_text()` split-site pattern.
    """
    path_vars: dict = {}
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)):
            continue
        is_read = any(
            _is_getsource_call(m)
            or (isinstance(m, ast.Call) and isinstance(m.func, ast.Attribute) and m.func.attr == "read_text")
            or (isinstance(m, ast.Call) and isinstance(m.func, ast.Name) and m.func.id == "open")
            for m in ast.walk(n.value)
        )
        if is_read:
            continue
        lits = _literal_strings(n.value)
        if lits:
            path_vars[n.targets[0].id] = lits
    return path_vars


def _collect_file_handles(tree: ast.AST, path_vars: dict) -> set:
    """Names bound by `with open(<scoped path>) as NAME:`."""
    handles = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.With):
            for item in n.items:
                if isinstance(item.optional_vars, ast.Name) and _is_scoped_open_call(item.context_expr, path_vars):
                    handles.add(item.optional_vars.id)
    return handles


def _collect_source_helpers(tree: ast.AST, path_vars: dict, file_handles: set) -> set:
    """Function names (anywhere in the file) whose body both `return`s something AND reads
    source somewhere in that body — the `_src(obj): return inspect.getsource(obj)` pattern this
    repo's own `test_647_machine_text_alerts_on_html_layer.py` and `test_yoy_writeback...` use."""
    helpers = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        has_return = any(isinstance(n, ast.Return) and n.value is not None for n in ast.walk(node))
        has_read = any(_is_inline_source_read(n, path_vars, file_handles) for n in ast.walk(node))
        if has_return and has_read:
            helpers.add(node.name)
    return helpers


def _rhs_references_source(node: ast.AST, path_vars: dict, file_handles: set, helpers: set, atoms: set) -> bool:
    for n in ast.walk(node):
        if _is_inline_source_read(n, path_vars, file_handles):
            return True
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in helpers:
            return True
        if isinstance(n, ast.Name) and n.id in atoms:
            return True
    return False


def _fixed_point_atoms(assigns: list, path_vars: dict, file_handles: set, helpers: set, seed: set) -> set:
    """Which of these `NAME = <expr>` assigns hold SOURCE TEXT (or a derivative slice/alias of
    it) — a variable an assert can pin against. Fixed-point over aliasing/slicing
    (`call = TRACKER[j:k]`), capped at 6 rounds (this repo's files never chain that deep)."""
    atoms = set(seed)
    changed = True
    rounds = 0
    while changed and rounds < 6:
        changed = False
        rounds += 1
        for a in assigns:
            name = a.targets[0].id
            if name in atoms:
                continue
            if _rhs_references_source(a.value, path_vars, file_handles, helpers, atoms):
                atoms.add(name)
                changed = True
    return atoms


def _named_assigns(node: ast.AST) -> list:
    return [n for n in ast.walk(node)
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)]


# ── per-function detection ──────────────────────────────────────────────────────────────────

def _is_test_func(node: ast.AST) -> bool:
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")


def _escape_for(lines: list, start: int, end: int):
    """A `# source-pin-ok: <reason>` anywhere in [start, end] with a real reason. Returns
    (escaped: bool, reason: str | None)."""
    for i in range(start, min(end, len(lines)) + 1):
        m = _ESCAPE_RE.search(lines[i - 1])
        if m and len(m.group(1).strip()) >= _ESCAPE_REASON_FLOOR:
            return True, m.group(1).strip()
    return False, None


def find_source_pin_functions(source: str, filename: str = "<string>") -> list:
    """Every `test_*` function in `source` that asserts against SOURCE TEXT.

    Returns a list of dicts: name, lineno, end_lineno, escaped, reason.
    """
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return []

    path_vars = _collect_path_vars(tree)
    file_handles = _collect_file_handles(tree, path_vars)
    helpers = _collect_source_helpers(tree, path_vars, file_handles)

    module_assigns = [n for n in getattr(tree, "body", [])
                       if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)]
    module_atoms = _fixed_point_atoms(module_assigns, path_vars, file_handles, helpers, set())

    lines = source.splitlines()
    out = []
    for node in ast.walk(tree):
        if not _is_test_func(node):
            continue
        has_assert = any(isinstance(n, ast.Assert) for n in ast.walk(node))
        if not has_assert:
            continue
        func_assigns = _named_assigns(node)
        func_atoms = _fixed_point_atoms(func_assigns, path_vars, file_handles, helpers, module_atoms)
        references_source = any(
            _is_inline_source_read(n, path_vars, file_handles)
            or (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in helpers)
            or (isinstance(n, ast.Name) and n.id in func_atoms)
            for n in ast.walk(node)
        )
        if not references_source:
            continue
        end = getattr(node, "end_lineno", node.lineno)
        escaped, reason = _escape_for(lines, node.lineno, end)
        out.append({"name": node.name, "lineno": node.lineno, "end_lineno": end,
                     "escaped": escaped, "reason": reason})
    return out


# ── whole-repo scan (informational trend — DoD #2, never blocking) ─────────────────────────

def scan_repo(tests_dir: Path = TESTS_DIR):
    per_file: dict = {}
    total = 0
    unescaped = 0
    for fpath in sorted(tests_dir.rglob("*.py")):
        try:
            source = fpath.read_text(encoding="utf-8")
        except (FileNotFoundError, UnicodeDecodeError):
            continue
        rel = str(fpath.relative_to(REPO))
        fns = find_source_pin_functions(source, rel)
        if not fns:
            continue
        per_file[rel] = len(fns)
        total += len(fns)
        unescaped += sum(1 for f in fns if not f["escaped"])
    return total, unescaped, per_file


# ── diff plumbing: which lines of which test files are NEW or EDITED vs origin/main ────────
# Same shape as check_plan._review_can_fire_gate: cheap `git diff --quiet` skip first, fail
# OPEN (never block on git/offline infrastructure) if origin is unreachable or unparseable.

def parse_added_lines(diff_text: str) -> set:
    """Line numbers (in the NEW file) that a unified diff (`-U0`) added. Pure — no git needed."""
    added = set()
    cur = None
    for ln in diff_text.splitlines():
        m = _HUNK_RE.match(ln)
        if m:
            cur = int(m.group(1))
            continue
        if cur is None:
            continue
        if ln.startswith("+++") or ln.startswith("---"):
            continue
        if ln.startswith("+"):
            added.add(cur)
            cur += 1
        elif ln.startswith("-"):
            pass
        else:
            cur += 1
    return added


def _changed_test_files(repo: Path):
    """relpaths of tests/*.py touched vs origin/main, or None if we can't tell (fail-open)."""
    try:
        quiet = subprocess.run(["git", "diff", "--quiet", "origin/main", "--", "tests"],
                                cwd=str(repo), capture_output=True)
    except Exception:
        return None
    if quiet.returncode == 0:
        return []
    try:
        out = subprocess.run(["git", "diff", "--name-only", "origin/main", "--", "tests"],
                              cwd=str(repo), capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        if out.returncode != 0:
            return None
    except Exception:
        return None
    return [f for f in out.stdout.splitlines() if f.endswith(".py")]


def _added_lines_for_file(repo: Path, relpath: str):
    try:
        out = subprocess.run(["git", "diff", "-U0", "origin/main", "--", relpath],
                              cwd=str(repo), capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        if out.returncode != 0:
            return None
    except Exception:
        return None
    return parse_added_lines(out.stdout)


def check_new_or_edited(repo: Path = REPO) -> list:
    """Human-readable violation strings for NEW/EDITED, unescaped source-pin test functions.
    Empty list = pass. `None` changed-files (offline / no origin) also yields an empty list —
    this gate must never be the reason a commit cannot be made when git itself is unavailable."""
    changed = _changed_test_files(repo)
    if not changed:
        return []
    violations = []
    for relpath in changed:
        fpath = repo / relpath
        if not fpath.exists():
            continue  # deleted file — nothing new to check
        added = _added_lines_for_file(repo, relpath)
        if not added:
            continue
        try:
            source = fpath.read_text(encoding="utf-8")
        except (FileNotFoundError, UnicodeDecodeError):
            continue
        for fn in find_source_pin_functions(source, relpath):
            if fn["escaped"]:
                continue
            if any(fn["lineno"] <= ln <= fn["end_lineno"] for ln in added):
                violations.append(
                    f"{relpath}:{fn['lineno']} `{fn['name']}` asserts on SOURCE TEXT, not "
                    f"behaviour. Rewrite to exercise behaviour, or add a reviewed "
                    f"`# source-pin-ok: <why behaviour cannot be exercised>`.")
    return violations


# ── CLI ──────────────────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    total, unescaped, per_file = scan_repo()

    if "--update-baseline" in argv:
        BASELINE_PATH.write_text(
            json.dumps({"total": total, "unescaped": unescaped, "per_file": per_file},
                       indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Baseline written: {total} source-pin test(s) ({unescaped} unescaped) across "
              f"{len(per_file)} file(s) -> {BASELINE_PATH.name}.")
        return 0

    baseline_total = 0
    if BASELINE_PATH.exists():
        try:
            baseline_total = json.loads(BASELINE_PATH.read_text(encoding="utf-8")).get("total", 0)
        except Exception:
            baseline_total = 0
    delta = total - baseline_total
    trend = "RISING — must go down" if delta > 0 else ("improved" if delta < 0 else "flat")
    print(f"[check_test_source_pins] source-pin test count: {total} total ({unescaped} unescaped "
          f"of a stated reason), baseline {baseline_total} ({trend}).")

    violations = check_new_or_edited(REPO)
    if not violations:
        print("check_test_source_pins: OK (no NEW/EDITED test asserts on source text).")
        return 0

    print("\nFAILED — a NEW or EDITED test asserts on SOURCE TEXT instead of behaviour (#653):\n")
    for v in violations:
        print(f"  {v}")
    print("\nThe 32 tests that broke 2026-09-12 against a behaviour-neutral refactor were exactly "
          "this shape, and the existing ~285 are a surfaced backlog, not something this blocks on.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
