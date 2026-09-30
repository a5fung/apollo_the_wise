"""#635 F5 — DERIVE the population of audit-event emitters from the source, never hand-list it.

Why this is a helper module and not code inside the tests: the tests that use it assert on
BEHAVIOUR (they feed each derived event name through the real nightly sweep) and only need the
*population of names* the source can emit. Same shape and same reason as `tests/_module_state.py`
(#663): a hand-written list of event names is exactly how RED-3b hid for a month, and a count
floor cannot catch a scanner that silently stopped reading.

What it can and cannot see: an event name passed as a string literal, or as a constant imported
from `audit_events`, is resolved. A name passed through a variable is not (the sweep itself queries
by LIKE pattern, so RUNTIME coverage never depends on this list — only the allowlist's "is it really
loud" check does).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Functions that put a message in front of the operator.
TELEGRAM_SENDERS = frozenset({
    "send_telegram_message", "notify_owner", "notify_job_failure", "record_job_failure",
})


def audit_event_constants() -> dict:
    from agents.market_intelligence import audit_events
    return {k: v for k, v in vars(audit_events).items() if k.isupper() and isinstance(v, str)}


def like_to_regex(pattern: str):
    """SQL LIKE (default ESCAPE backslash) -> regex. `%` any run, `_` one char, `\\x` literal."""
    out, i = [], 0
    while i < len(pattern):
        c = pattern[i]
        if c == "\\" and i + 1 < len(pattern):
            out.append(re.escape(pattern[i + 1]))
            i += 2
            continue
        out.append(".*" if c == "%" else "." if c == "_" else re.escape(c))
        i += 1
    return re.compile("^" + "".join(out) + "$")


def static_audit_emitters() -> dict:
    """{event_name: [(relpath, lineno, [enclosing function nodes, innermost first])]} for every
    `log_audit_event(<literal or audit_events constant>, ...)` under agents/ and core/."""
    consts = audit_event_constants()
    found: dict = {}
    for path in list((REPO / "agents").rglob("*.py")) + list((REPO / "core").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        parents = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else None
            if name != "log_audit_event" or not node.args:
                continue
            a = node.args[0]
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                ev = a.value
            elif isinstance(a, ast.Name) and a.id in consts:
                ev = consts[a.id]
            else:
                continue
            chain, cur = [], node
            while cur in parents:
                cur = parents[cur]
                if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    chain.append(cur)
            found.setdefault(ev, []).append((str(path.relative_to(REPO)), node.lineno, chain))
    return found


def names_called_in(relpath: str, func_name: str) -> frozenset:
    """Every bare/attribute call name inside the top-level or nested function `func_name` of
    `relpath` - a structural wiring check ("the pull still CALLS the helper"), not a text match,
    so a re-wrap or a renamed local does not break it, only an inlined copy or a dropped call."""
    tree = ast.parse((REPO / relpath).read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            out = set()
            for n in ast.walk(node):
                if isinstance(n, ast.Call):
                    f = n.func
                    nm = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
                    if nm:
                        out.add(nm)
            return frozenset(out)
    raise LookupError(f"{func_name} not found in {relpath}")


def calls_a_telegram_sender(fn_node) -> bool:
    for n in ast.walk(fn_node):
        if isinstance(n, ast.Call):
            f = n.func
            nm = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if nm in TELEGRAM_SENDERS:
                return True
    return False
