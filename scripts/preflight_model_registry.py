"""Preflight gate: ban string-literal Claude model ids outside the registry (#257).

Why: model ids were scattered as literals across 17 call sites and DRIFTED —
found 2026-06-09: the theme advisor still called claude-opus-4-6 while the judge
eval compared against claude-opus-4-8, the metrics extractor sat on a stale
claude-sonnet-4-5 pin, and both spend-pricing tables carried wrong rates for
models they referenced by literal. File-by-file upgrades will always miss spots.

THE RULE: every production model id lives in `shared/llm_models.py` (tier +
role constants); call sites import a ROLE constant. A string literal matching
`claude-…` anywhere else in agents/ core/ channels/ shared/ fails this gate.

  Escape hatch: `# model-ok: <reason>` on the offending line (reviewed,
  deliberate — e.g. a migration shim that must name an old id).

Scope mirrors preflight_datetime_hygiene: agents/ core/ channels/ shared/,
offline backtester/ excluded, scripts/ and tests/ excluded (eval harnesses
legitimately enumerate model ids to compare them). Docstrings are skipped —
prose examples are not call sites.

Static AST walk; comments are never flagged. No runtime needed.
Run: python scripts/preflight_model_registry.py
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

SCOPED_DIRS = ["agents", "core", "channels", "shared"]
EXCLUDE_SUBPATHS = ("backtester/", "backtester\\")
REGISTRY_FILE = "llm_models.py"
ESCAPE = "# model-ok"

_MODEL_RE = re.compile(r"^claude-[a-z0-9.\-\[\]]+$")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """ids() of Constant nodes that are docstrings (module/class/function)."""
    doc_ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                doc_ids.add(id(body[0].value))
    return doc_ids


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
    lines = source.splitlines()
    doc_ids = _docstring_nodes(tree)
    violations: list[dict] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in doc_ids:
            continue
        if not _MODEL_RE.match(node.value.strip()):
            continue
        lineno = node.lineno
        if 1 <= lineno <= len(lines) and ESCAPE in lines[lineno - 1]:
            continue
        violations.append({"file": str(filepath), "line": lineno, "literal": node.value})
    return violations


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
            if filepath.name == REGISTRY_FILE:
                continue
            n_files += 1
            all_violations.extend(check_file(filepath))

    if not all_violations:
        print(f"Preflight model-registry check — OK ({n_files} files clean; "
              f"all model ids come from shared/llm_models.py).")
        return 0

    print("DEPLOY FAILED — string-literal Claude model id(s) outside the registry:")
    print()
    for v in all_violations:
        rel = v["file"].replace(str(repo_root) + "/", "").replace(str(repo_root) + "\\", "")
        print(f"  {rel}:{v['line']}  \"{v['literal']}\"")
    print()
    print("Import a ROLE constant from shared/llm_models.py instead (or add it there).")
    print("Deliberate exception: annotate the line with `# model-ok: <reason>`.")
    print("Why: scattered ids drift — the theme advisor sat on opus-4-6 while the")
    print("judge eval used opus-4-8 (caught 2026-06-09).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
