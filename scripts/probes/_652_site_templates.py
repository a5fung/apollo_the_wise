"""#652 — static message SKELETONS for every default-Markdown call site (AST data-flow-lite).

WHY: the test-suite harvest exercises 53 of the 173 call sites that ride the shared default;
the uncovered ones are mostly order_manager / trade_stream / scheduler — the money path. A
skeleton reconstructs the message TEMPLATE each site sends (its literal markup: `*…*`, backticks,
fences, brackets, newlines) with every dynamic slot filled by a placeholder chosen to carry the
hazards this task is about — underscores, an Alpaca-style JSON error, SQL, a snake_case verdict.
It is NOT a real body (no real values), so it is reported as its own group and judged on
STRUCTURE only: does the template itself, with hostile-but-typical values, 400 under HTML where
it renders under legacy Markdown?

Reconstruction follows the value flowing into the sender's first argument inside the enclosing
function: f-strings and string constants, `+`/`+=` concatenation, `name = …` reassignment,
`"\\n".join(lines)` over a list built by `[...]`, `.append(...)`, `.extend([...])`, `+= [...]`.
Every branch is taken (over-inclusive on purpose). A site whose body comes from a helper
function or a value the function does not build is reported as NOT reconstructible.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACCEPTANCE_SQL = "SELECT * FROM mi_live_trades WHERE stop_order_id IS NULL"
ALPACA_ERR = ('existing_qty not free: {"code":40310000,"message":"insufficient qty available for order '
              '(requested: 3, available: 0)"}')


def placeholder(expr_src: str) -> str:
    s = expr_src.lower()
    if "sql" in s:
        return ACCEPTANCE_SQL
    if any(k in s for k in ("ticker", "symbol", "sym")):
        return "OKTA"
    if any(k in s for k in ("reason", "err", "exc", "msg", "detail", "body", "why", "rationale",
                            "summary", "text", "humanize", "hint", "note", "desc")):
        return ALPACA_ERR
    if any(k in s for k in ("pct", "price", "qty", "pnl", "r_mult", ":.", "ratio", "score", "gap",
                            "rvol", "usd", "$", "atr", "stop", "entry", "avg", "median", "z")):
        return "12.34"
    if any(k in s for k in ("date", "day", "when", "time", "now", "asof")):
        return "2026-09-18"
    if any(k in s for k in ("id", "uuid", "order", "client")):
        return "ord_a1b2_c3d4"
    if any(k in s for k in ("mode", "account", "strategy", "verdict", "action", "status", "state",
                            "key", "name", "event", "job", "kind", "type", "tier", "label", "phase")):
        return "TRAIL_TIGHTEN"
    if any(k in s for k in ("count", "len(", "n_", "num", "total", "rows")):
        return "3"
    return "snake_case_val"


class _Builder:
    def __init__(self, fn: ast.AST, call_line: int):
        self.fn = fn
        self.call_line = call_line
        self.reconstructible = True
        self.pieces = 0

    def render(self, node: ast.AST | None, depth: int = 0) -> str | None:
        if node is None or depth > 6:
            return None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            self.pieces += 1
            return node.value
        if isinstance(node, ast.JoinedStr):
            self.pieces += 1
            out = []
            for v in node.values:
                if isinstance(v, ast.Constant):
                    out.append(str(v.value))
                elif isinstance(v, ast.FormattedValue):
                    inner = v.value
                    # a nested string literal / f-string inside the slot renders as itself
                    if isinstance(inner, (ast.Constant, ast.JoinedStr)):
                        r = self.render(inner, depth + 1)
                        out.append(r if r is not None else placeholder(ast.unparse(inner)))
                    else:
                        out.append(placeholder(ast.unparse(inner)))
            return "".join(out)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            l = self.render(node.left, depth + 1)
            r = self.render(node.right, depth + 1)
            if l is None and r is None:
                return None
            return (l or "") + (r or "")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):  # "..." % (...)
            l = self.render(node.left, depth + 1)
            return l.replace("%s", "snake_case_val").replace("%d", "3") if l else None
        if isinstance(node, ast.Call):
            f = node.func
            # "\n".join(X)
            if isinstance(f, ast.Attribute) and f.attr == "join" and isinstance(f.value, ast.Constant) and node.args:
                sep = str(f.value.value)
                items = self.render_list(node.args[0], depth + 1)
                if items is None:
                    return None
                return sep.join(items)
            if isinstance(f, ast.Attribute) and f.attr in ("strip", "rstrip", "lstrip", "format"):
                return self.render(f.value, depth + 1)
            if isinstance(f, ast.Name) and f.id in ("str",):
                return placeholder(ast.unparse(node))
            self.reconstructible = False  # a helper builds it — cannot see inside
            return None
        if isinstance(node, ast.Name):
            return self.render_name(node.id, depth + 1)
        if isinstance(node, ast.IfExp):
            a = self.render(node.body, depth + 1)
            b = self.render(node.orelse, depth + 1)
            return (a or "") + ("\n" if a and b else "") + (b or "") if (a or b) else None
        if isinstance(node, ast.Subscript):
            return self.render(node.value, depth + 1)
        if isinstance(node, ast.Attribute):
            return placeholder(ast.unparse(node))
        return None

    def render_name(self, name: str, depth: int) -> str | None:
        """Everything assigned/concatenated into `name` before the call, in source order."""
        parts: list[str] = []
        found = False
        for stmt in ast.walk(self.fn):
            ln = getattr(stmt, "lineno", None)
            if ln is None or ln > self.call_line:
                continue
            if isinstance(stmt, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in stmt.targets):
                found = True
                r = self.render(stmt.value, depth)
                if r is not None:
                    parts.append(r)
            elif isinstance(stmt, ast.AugAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id == name:
                found = True
                r = self.render(stmt.value, depth)
                if r is not None:
                    parts.append(r)
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id == name and stmt.value is not None:
                found = True
                r = self.render(stmt.value, depth)
                if r is not None:
                    parts.append(r)
        if not found:
            # a parameter or something built elsewhere
            self.reconstructible = False
            return None
        return "".join(parts) if parts else None

    def render_list(self, node: ast.AST, depth: int) -> list[str] | None:
        if isinstance(node, (ast.List, ast.Tuple)):
            out = []
            for e in node.elts:
                r = self.render(e, depth)
                if r is not None:
                    out.append(r)
            return out
        if isinstance(node, ast.ListComp):
            r = self.render(node.elt, depth)
            return [r] if r is not None else []
        if isinstance(node, ast.Name):
            name = node.id
            items: list[str] = []
            found = False
            for stmt in ast.walk(self.fn):
                ln = getattr(stmt, "lineno", None)
                if ln is None or ln > self.call_line:
                    continue
                if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                    targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
                    if any(isinstance(t, ast.Name) and t.id == name for t in targets) and stmt.value is not None:
                        found = True
                        sub = self.render_list(stmt.value, depth)
                        if sub:
                            items.extend(sub)
                elif isinstance(stmt, ast.AugAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id == name:
                    found = True
                    sub = self.render_list(stmt.value, depth)
                    if sub:
                        items.extend(sub)
                elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                    c = stmt.value
                    f = c.func
                    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == name:
                        if f.attr == "append" and c.args:
                            found = True
                            r = self.render(c.args[0], depth)
                            if r is not None:
                                items.append(r)
                        elif f.attr == "extend" and c.args:
                            found = True
                            sub = self.render_list(c.args[0], depth)
                            if sub:
                                items.extend(sub)
                        elif f.attr == "insert" and len(c.args) > 1:
                            found = True
                            r = self.render(c.args[1], depth)
                            if r is not None:
                                items.insert(0, r)
            if not found:
                self.reconstructible = False
                return None
            return items
        r = self.render(node, depth)
        return [r] if r is not None else None


def skeletons(sites: list[dict]) -> list[dict]:
    """sites: census rows (file, line, func, class). Returns rows with `skeleton` (str|None)."""
    by_file: dict[str, list[dict]] = {}
    for r in sites:
        by_file.setdefault(r["file"], []).append(r)
    out: list[dict] = []
    for file, rows in by_file.items():
        tree = ast.parse((ROOT / file).read_text(encoding="utf-8"))
        parent: dict[int, ast.AST] = {}
        for node in ast.walk(tree):
            for ch in ast.iter_child_nodes(node):
                parent[id(ch)] = node
        calls = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                nm = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
                if nm == "send_telegram_message":
                    calls[node.lineno] = node
        for r in rows:
            call = calls.get(int(r["line"]))
            if call is None:
                out.append({**r, "skeleton": None, "reconstructible": False, "pieces": 0})
                continue
            fn = parent.get(id(call))
            while fn is not None and not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn = parent.get(id(fn))
            arg0 = call.args[0] if call.args else next((kw.value for kw in call.keywords if kw.arg == "text"), None)
            if fn is None or arg0 is None:
                out.append({**r, "skeleton": None, "reconstructible": False, "pieces": 0})
                continue
            b = _Builder(fn, call.lineno)
            sk = b.render(arg0)
            out.append({**r, "skeleton": sk if (sk and sk.strip()) else None,
                        "reconstructible": bool(sk and sk.strip()), "partial": not b.reconstructible,
                        "pieces": b.pieces})
    return out


if __name__ == "__main__":  # quick look
    import csv
    import sys
    rows = [r for r in csv.DictReader((ROOT / "scripts/probes/_652_call_sites.tsv").open(encoding="utf-8"), delimiter="\t")
            if r["is_test"] == "False" and r["class"] == "default_markdown"]
    sk = skeletons(rows)
    ok = [s for s in sk if s["reconstructible"]]
    print(f"default-Markdown sites: {len(sk)}; skeleton reconstructed: {len(ok)}; partial (helper inside): {sum(1 for s in ok if s.get('partial'))}")
    for s in sk[: int(sys.argv[1]) if len(sys.argv) > 1 else 5]:
        print(f"--- {s['file']}:{s['line']} ({s['func']}) pieces={s['pieces']} partial={s.get('partial')}")
        print(repr((s["skeleton"] or "")[:300]))
