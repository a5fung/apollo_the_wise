"""#652 — call-site census of `send_telegram_message` (AST, not grep).

WHY AST: 125 of the 239 grep hits are multi-line calls, so a same-line `parse_mode`
grep is blind to what they pass. This walks every Call node, resolves import aliases
(`from ...briefing import send_telegram_message [as x]`, `briefing.send_telegram_message`,
`x = send_telegram_message`), and classifies each site by what a DEFAULT FLIP would do to it.

Three denominators are kept apart on purpose (call sites != senders != messages):
  * call sites — Call nodes in production code (agents/ core/ shared/ scripts/ channels/ main.py)
  * wrappers   — a def that forwards `parse_mode` to the sender; its callers are counted separately
  * tests/     — reported for context only, never in the production denominator

Run:  python scripts/probes/_652_call_site_census.py [--tsv out.tsv]
Read-only. Edits nothing.
"""
from __future__ import annotations

import ast
import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROD_SCAN = ["agents", "core", "shared", "scripts", "channels", "main.py"]
SELF_PREFIX = "scripts/probes/_652_"
TARGET = "send_telegram_message"

CLASSES = {
    "default_markdown": "no parse_mode passed — rides the shared default (FLIPS with it)",
    "explicit_html_md_to_html": 'parse_mode="HTML" + md_to_html(...) at the call (already safe)',
    "explicit_html_native": 'parse_mode="HTML" with a body built by the HTML helpers (already safe; must NOT be double-converted)',
    "explicit_markdown": 'parse_mode="Markdown" written out (opts into legacy; a flip does not touch it)',
    "passthrough": "parse_mode is a variable / **kwargs — decided by the caller (wrapper)",
    "other_constant": "parse_mode is some other constant (None, MarkdownV2, ...)",
}


def _rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


def _describe_arg(node: ast.AST | None) -> str:
    if node is None:
        return "<none>"
    if isinstance(node, ast.Call):
        f = node.func
        name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "?")
        return f"call:{name}"
    if isinstance(node, ast.Name):
        return f"name:{node.id}"
    if isinstance(node, ast.JoinedStr):
        return "fstring"
    if isinstance(node, ast.Constant):
        return "const"
    if isinstance(node, ast.BinOp):
        return "binop"
    if isinstance(node, ast.Attribute):
        return f"attr:{node.attr}"
    if isinstance(node, ast.Subscript):
        return "subscript"
    return type(node).__name__


def _aliases(tree: ast.AST) -> tuple[set[str], set[str]]:
    """Names bound to the sender, and module aliases whose `.send_telegram_message` is it."""
    names: set[str] = set()
    mods: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module and n.module.endswith("briefing"):
            for a in n.names:
                if a.name == TARGET:
                    names.add(a.asname or a.name)
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.name.endswith("briefing"):
                    mods.add(a.asname or a.name.split(".")[-1])
        elif isinstance(n, ast.ImportFrom) and n.module and n.module.endswith("market_intelligence"):
            for a in n.names:
                if a.name == "briefing":
                    mods.add(a.asname or a.name)
        elif isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            v = n.value
            if (isinstance(v, ast.Name) and v.id == TARGET) or (
                isinstance(v, ast.Attribute) and v.attr == TARGET
            ):
                names.add(n.targets[0].id)
    names.add(TARGET)  # a bare name is the sender in briefing.py itself and after any import
    return names, mods


def _enclosing_defs(tree: ast.AST) -> dict[int, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Map every Call node id -> its nearest enclosing function (for wrapper detection)."""
    parent: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[id(child)] = node
    out: dict[int, ast.FunctionDef | ast.AsyncFunctionDef] = {}

    def nearest(n: ast.AST):
        cur = parent.get(id(n))
        while cur is not None:
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return cur
            cur = parent.get(id(cur))
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            d = nearest(node)
            if d is not None:
                out[id(node)] = d
    return out


def census(paths: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for path in paths:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as e:  # pragma: no cover
            print(f"SKIP {path}: {e}", file=sys.stderr)
            continue
        names, _mods = _aliases(tree)
        encl = _enclosing_defs(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            hit = False
            if isinstance(f, ast.Name) and f.id in names:
                hit = True
            elif isinstance(f, ast.Attribute) and f.attr == TARGET:
                hit = True  # briefing.send_telegram_message / bm.send_telegram_message / self.x
            if not hit:
                continue
            arg0 = node.args[0] if node.args else None
            if arg0 is None:
                for kw in node.keywords:
                    if kw.arg == "text":
                        arg0 = kw.value
            pm_kind, pm_val = "absent", ""
            star_kw = any(kw.arg is None for kw in node.keywords)
            for kw in node.keywords:
                if kw.arg == "parse_mode":
                    v = kw.value
                    if isinstance(v, ast.Constant):
                        pm_kind, pm_val = "constant", repr(v.value)
                    else:
                        pm_kind, pm_val = "expr", ast.unparse(v)
            if pm_kind == "absent" and star_kw:
                pm_kind, pm_val = "expr", "**kwargs"
            arg_desc = _describe_arg(arg0)
            if pm_kind == "constant" and pm_val == "'HTML'":
                cls = "explicit_html_md_to_html" if arg_desc == "call:md_to_html" else "explicit_html_native"
            elif pm_kind == "constant" and pm_val == "'Markdown'":
                cls = "explicit_markdown"
            elif pm_kind == "constant":
                cls = "other_constant"
            elif pm_kind == "expr":
                cls = "passthrough"
            else:
                cls = "default_markdown"
            d = encl.get(id(node))
            func = d.name if d is not None else "<module>"
            is_wrapper = bool(d is not None and any(a.arg == "parse_mode" for a in d.args.args + d.args.kwonlyargs))
            rows.append({
                "file": _rel(path), "line": node.lineno, "func": func,
                "class": cls, "parse_mode": pm_val or "<default>", "arg0": arg_desc,
                "in_wrapper_def": is_wrapper, "is_test": _rel(path).startswith("tests/"),
            })
    return rows


def wrapper_callers(rows: list[dict], prod_files: list[Path]) -> dict[str, int]:
    """For each wrapper def (a function that forwards parse_mode), count its callers in prod."""
    wrappers = sorted({r["func"] for r in rows if r["in_wrapper_def"] and not r["is_test"]})
    counts: dict[str, int] = {w: 0 for w in wrappers}
    if not wrappers:
        return counts
    for path in prod_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                nm = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
                if nm in counts:
                    counts[nm] += 1
    return counts


def main(argv: list[str]) -> int:
    tsv_out = None
    if "--tsv" in argv:
        tsv_out = Path(argv[argv.index("--tsv") + 1])
    prod_files: list[Path] = []
    for p in PROD_SCAN:
        pp = ROOT / p
        if pp.is_file():
            prod_files.append(pp)
        elif pp.is_dir():
            prod_files.extend(sorted(x for x in pp.rglob("*.py") if not _rel(x).startswith(SELF_PREFIX)))
    test_files = sorted((ROOT / "tests").rglob("*.py"))
    rows = census(prod_files + test_files)
    prod = [r for r in rows if not r["is_test"]]
    tests = [r for r in rows if r["is_test"]]

    print(f"PRODUCTION call sites of {TARGET}: {len(prod)}  (files scanned: {len(prod_files)}; "
          f"tests/ carries another {len(tests)} in {len({r['file'] for r in tests})} files — context only)")
    by_cls = Counter(r["class"] for r in prod)
    for cls, desc in CLASSES.items():
        n = by_cls.get(cls, 0)
        print(f"  {n:4d} / {len(prod)}  {cls:26s} {desc}")
    print()
    wc = wrapper_callers(prod, prod_files)
    if wc:
        print("WRAPPERS (a def that forwards parse_mode — one call site, many senders):")
        for w, n in sorted(wc.items()):
            sites = [f"{r['file']}:{r['line']}" for r in prod if r["func"] == w and r["in_wrapper_def"]]
            print(f"  {w}: {n} callers in prod  <- {', '.join(sites)}")
        print()
    print("DEFAULT-MARKDOWN sites by file (the population a default flip changes):")
    per_file = Counter(r["file"] for r in prod if r["class"] == "default_markdown")
    for f, n in sorted(per_file.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {n:3d}  {f}")
    print()
    print("EXPLICIT parse_mode sites (every one, so double-conversion can be checked):")
    for r in prod:
        if r["class"] != "default_markdown":
            print(f"  {r['file']}:{r['line']:<5d} {r['class']:26s} parse_mode={r['parse_mode']:<12s} arg0={r['arg0']}  in {r['func']}")
    if tsv_out:
        with tsv_out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), delimiter="\t")
            w.writeheader()
            w.writerows(rows)
        print(f"\nwrote {tsv_out} ({len(rows)} rows incl. tests)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
