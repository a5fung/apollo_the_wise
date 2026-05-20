"""Preflight check: detect import-shadowing landmines.

2026-05-20 incident: commit bb17e69 added `from agents.market_intelligence.db
import log_audit_event` INSIDE run_ep_scan() (a 1000+ line async function).
The module already imported log_audit_event at the top. Python sees the local
import → makes log_audit_event a LOCAL variable for the ENTIRE function scope
→ every reference BEFORE the local import line raises UnboundLocalError.

EP scans failed for 1h 21m before the user noticed and reported it. Preflight
didn't catch it because _check_safeguards + DB UPDATE prepare don't exercise
run_ep_scan's function body.

This check walks every function in scoped files, collects:
  - Names imported at module level
  - Names locally imported via `from X import Y` inside the function

If a name is BOTH module-imported AND function-locally-imported, the function-
local import shadows the module binding for the entire function body, creating
the UnboundLocalError bug class. We flag it as a deploy-blocking error.

The check is purely static (AST walk) — no runtime needed. Fast.

Run as part of deploy.sh:
  bash scripts/deploy.sh  → [5d/5] runs this script
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path


# Files to scope. Trading-critical hot paths where the UnboundLocalError class
# would be silent-but-deadly. Add new files here when they're added to the
# hot path. Keeping it tight (vs walking entire repo) means the check stays
# fast and surfaces only signal.
SCOPED_FILES = [
    "agents/market_intelligence/ep_detector.py",
    "agents/market_intelligence/ninem_detector.py",
    "agents/market_intelligence/flag_detector.py",
    "agents/market_intelligence/broker/entry_pipeline.py",
    "agents/market_intelligence/broker/order_manager.py",
    "agents/market_intelligence/broker/trade_stream.py",
    "agents/market_intelligence/broker/live_tracker.py",
    "agents/market_intelligence/scheduler.py",
    "agents/market_intelligence/theme_engine.py",
    "agents/market_intelligence/collector.py",
    "agents/market_intelligence/system_audit.py",
    "agents/market_intelligence/catalyst_metrics_extractor.py",
]


class ModuleImports:
    """Names imported at module level in a single file."""

    def __init__(self, tree: ast.Module):
        self.names: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    self.names.add(alias.asname or alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    self.names.add(alias.asname or alias.name.split(".")[0])


def _function_local_names(fn_node) -> dict[str, int]:
    """Return {name: first_assignment_lineno} for names assigned inside the
    function's OWN body (not in nested functions). Includes `from X import Y`
    targets, `Y = ...` assignments, `for Y in ...` and `with ... as Y` targets.

    These are the names Python treats as LOCAL to fn_node — referencing one
    of them before its first binding point raises UnboundLocalError.
    """
    local_assignments: dict[str, int] = {}

    def _walk_excluding_nested(node):
        # Visit children, but skip the body of nested function defs so we
        # don't mistake their local-imports for our own.
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue  # nested def — has its own scope
            if isinstance(child, ast.ImportFrom):
                for alias in child.names:
                    name = alias.asname or alias.name
                    local_assignments.setdefault(name, child.lineno)
            elif isinstance(child, ast.Import):
                for alias in child.names:
                    name = alias.asname or alias.name.split(".")[0]
                    local_assignments.setdefault(name, child.lineno)
            elif isinstance(child, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                for t in targets:
                    if isinstance(t, ast.Name):
                        local_assignments.setdefault(t.id, child.lineno)
            elif isinstance(child, (ast.For, ast.AsyncFor)):
                if isinstance(child.target, ast.Name):
                    local_assignments.setdefault(child.target.id, child.lineno)
            elif isinstance(child, (ast.With, ast.AsyncWith)):
                for item in child.items:
                    if item.optional_vars and isinstance(item.optional_vars, ast.Name):
                        local_assignments.setdefault(item.optional_vars.id, child.lineno)
            _walk_excluding_nested(child)

    # Walk the function body
    for stmt in fn_node.body:
        _walk_excluding_nested(stmt)
    return local_assignments


def _name_references_before(fn_node, target_name: str, before_line: int) -> list[int]:
    """Return line numbers where `target_name` is referenced (as Load context)
    inside fn_node's OWN body BEFORE `before_line`. Excludes nested functions.
    """
    refs: list[int] = []

    def _walk_excluding_nested(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(child, ast.Name) and child.id == target_name:
                if isinstance(child.ctx, ast.Load) and child.lineno < before_line:
                    refs.append(child.lineno)
            _walk_excluding_nested(child)

    for stmt in fn_node.body:
        _walk_excluding_nested(stmt)
    return refs


class ShadowingVisitor(ast.NodeVisitor):
    """Walks each function body; flags `from X import Y` where:
      1. Y is also imported at module level (so the function-local import
         shadows the module binding)
      2. Y is REFERENCED somewhere in the function body BEFORE its local
         import line (the UnboundLocalError landmine condition)

    Without condition 2, a function-local import that's the FIRST reference
    of the name in the function is technically redundant but not a bug.
    """

    def __init__(self, module_imports: set[str], filepath: str):
        self.module_imports = module_imports
        self.filepath = filepath
        self.violations: list[dict] = []
        self._fn_stack: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._check_fn(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._check_fn(node)

    def _check_fn(self, node):
        self._fn_stack.append(node.name)
        # Collect function-local import bindings of module-shadowed names
        # (excluding nested functions — they have their own scope)
        local_imports: list[tuple[str, int, str]] = []  # (name, lineno, from_module)

        def _walk_excluding_nested(n):
            for child in ast.iter_child_nodes(n):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    continue
                if isinstance(child, ast.ImportFrom):
                    for alias in child.names:
                        local_name = alias.asname or alias.name
                        if local_name in self.module_imports:
                            local_imports.append((local_name, child.lineno, child.module or ""))
                _walk_excluding_nested(child)

        for stmt in node.body:
            _walk_excluding_nested(stmt)

        # For each local-shadowing import, check if the name was referenced
        # BEFORE the local-import line in this function.
        for local_name, import_lineno, from_module in local_imports:
            prior_refs = _name_references_before(node, local_name, import_lineno)
            if prior_refs:
                self.violations.append({
                    "file": self.filepath,
                    "function": " > ".join(self._fn_stack),
                    "line": import_lineno,
                    "shadowed_name": local_name,
                    "from_module": from_module,
                    "prior_ref_lines": prior_refs,
                })
        # Recurse to visit nested defs
        self.generic_visit(node)
        self._fn_stack.pop()


def check_file(filepath: Path) -> list[dict]:
    """Return list of violations in this file."""
    try:
        source = filepath.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError as e:
        print(f"WARN: syntax error parsing {filepath}: {e}", file=sys.stderr)
        return []
    module_imports = ModuleImports(tree)
    visitor = ShadowingVisitor(module_imports.names, str(filepath))
    visitor.visit(tree)
    return visitor.violations


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    all_violations: list[dict] = []
    for rel in SCOPED_FILES:
        filepath = repo_root / rel
        all_violations.extend(check_file(filepath))

    if not all_violations:
        print(f"Preflight import-shadowing check — OK "
              f"({len(SCOPED_FILES)} scoped files clean).")
        return 0

    print("DEPLOY FAILED — UnboundLocalError landmines detected:")
    print()
    for v in all_violations:
        print(f"  {v['file']}:{v['line']}")
        print(f"    function: {v['function']}")
        print(f"    shadows:  `from {v['from_module']} import {v['shadowed_name']}`")
        print(f"    but `{v['shadowed_name']}` is referenced earlier on line(s): "
              f"{', '.join(map(str, v['prior_ref_lines'][:5]))}"
              + (f" (+{len(v['prior_ref_lines'])-5} more)" if len(v['prior_ref_lines']) > 5 else ""))
        print(f"    fix: remove the function-local import. The module-level binding")
        print(f"         is sufficient — the local import makes the name a LOCAL")
        print(f"         variable, raising UnboundLocalError on the prior refs.")
        print()
    print("This pattern caused the 2026-05-20 UnboundLocalError outage.")
    print("Python treats the function-local import as making the name a LOCAL")
    print("variable for the entire function scope, so any reference BEFORE the")
    print("local import raises UnboundLocalError.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
