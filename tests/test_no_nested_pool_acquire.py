"""#672 — no db function may ask the pool for a SECOND connection while holding the first.

THE INCIDENT. On 2026-09-17 the deal-pin filter shipped with the pin lookup INSIDE each RS
pool's own connection block:

    async with pool.acquire() as conn:            # connection #1, held
        rows = await conn.fetch(...)
        pinned = await get_deal_pinned_tickers(...)    # asks for connection #2

`asyncpg.create_pool` is `max_size=5` and `pool.acquire()` takes NO timeout. The evening brief
gathers eight concurrent `get_rs_leaders`: five take every connection, then each waits for a
sixth only they can free. Nothing times out. The next full nightly — 2026-09-18 — hung for
**7.3 hours** and **23 jobs never ran**, the evening briefing among them.

WHY THIS GATE RATHER THAN A TIMEOUT. The operator asked for the clearest fix. A pool
`command_timeout` would not have caught it at all — that bounds a slow QUERY, and this deadlock
never ran a query, it waited on `acquire()`. A default acquire timeout would catch it, but there
are 742 acquire sites and it puts a new failure mode on the order path. This gate makes the bug
**impossible instead of survivable**, is decidable statically, and costs nothing at runtime.

It REPLACES the narrower six-pool check that shipped with the fix: this one covers every function
in the module, so a seventh pool — or any unrelated pair — is caught the day it is written.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
DB = REPO / "agents" / "market_intelligence" / "db.py"


def _acquires_directly(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.AsyncWith):
            for item in n.items:
                ce = item.context_expr
                if (isinstance(ce, ast.Call) and isinstance(ce.func, ast.Attribute)
                        and ce.func.attr == "acquire"):
                    return True
    return False


def _param_names(fn: ast.AST) -> list:
    a = fn.args
    return [p.arg for p in (list(a.posonlyargs) + list(a.args))]


def nested_acquire_offenders(source: str) -> list:
    """Every `(caller, callee, line)` where `caller` calls a connection-acquiring `callee`
    from inside its own `async with pool.acquire()` block WITHOUT handing over the connection
    it already holds.

    A call is SAFE when the connection is passed — as `conn=` OR positionally into a parameter
    named `conn`. ⚠ The positional form is not a nicety: `get_latest_two_theme_dates` acquires
    and then recurses as `get_latest_two_theme_dates(acquired)`, which is the CORRECT idiom, and
    a gate that flagged it would be training people to work around it.
    """
    tree = ast.parse(source)
    funcs = {n.name: n for n in tree.body
             if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))}
    acquirers = {name for name, n in funcs.items() if _acquires_directly(n)}
    changed = True                          # transitive: calling an acquirer is acquiring
    while changed:
        changed = False
        for name, n in funcs.items():
            if name in acquirers:
                continue
            for c in ast.walk(n):
                if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id in acquirers:
                    acquirers.add(name)
                    changed = True
                    break

    offenders = []
    for name, fn in funcs.items():
        for w in ast.walk(fn):
            if not isinstance(w, ast.AsyncWith):
                continue
            if not any(isinstance(i.context_expr, ast.Call)
                       and isinstance(i.context_expr.func, ast.Attribute)
                       and i.context_expr.func.attr == "acquire" for i in w.items):
                continue
            for c in ast.walk(w):
                if not (isinstance(c, ast.Call) and isinstance(c.func, ast.Name)):
                    continue
                callee = c.func.id
                if callee not in acquirers:
                    continue
                if any(k.arg == "conn" for k in c.keywords):
                    continue
                params = _param_names(funcs[callee]) if callee in funcs else []
                if "conn" in params and len(c.args) > params.index("conn"):
                    continue                # handed over positionally
                offenders.append((name, callee, c.lineno))
    return offenders


# ── the detector must not be blind — proven on synthetic source, not by mutating db.py ────

def test_the_detector_catches_the_exact_2026_09_18_shape():
    """The real bug, minimised. If this stops failing, the gate below is decorative."""
    src = """
async def get_deal_pinned_tickers(as_of, tickers=None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("...")

async def get_rs_leaders(d, limit=50):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("...")
        pinned = await get_deal_pinned_tickers(d, [r for r in rows])
        return rows
"""
    offenders = nested_acquire_offenders(src)
    assert [(a, b) for a, b, _ in offenders] == [("get_rs_leaders", "get_deal_pinned_tickers")]


@pytest.mark.parametrize("handover", ["conn=conn", "conn"])
def test_handing_the_connection_over_is_accepted_both_ways(handover):
    """Keyword AND positional. The positional form is the codebase's existing recursive idiom."""
    src = f"""
async def helper(as_of, conn=None):
    if conn is None:
        pool = await get_pool()
        async with pool.acquire() as c:
            return await helper(as_of, c)
    return await conn.fetch("...")

async def caller(d):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await helper(d, {handover})
"""
    assert nested_acquire_offenders(src) == []


def test_a_call_made_OUTSIDE_the_acquire_block_is_fine():
    """The fix for the real bug was to hand the connection over, but hoisting the call out of
    the block is equally correct — the gate must not force one shape over the other."""
    src = """
async def helper(x):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("...")

async def caller(d):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("...")
    return await helper(rows)
"""
    assert nested_acquire_offenders(src) == []


# ── the real module ───────────────────────────────────────────────────────────────────────

def test_no_db_function_holds_a_connection_while_asking_for_another():
    """THE GATE, with its own vacuity guard folded in so the two cannot drift apart.

    Hard fail, no allowlist and no backlog: when it was written the whole module held exactly ONE
    real offender (`assign_ticker_to_theme` -> `log_audit_event`, fixed in the same commit), so
    there is nothing to grandfather and nothing to hide behind."""
    # source-pin-ok: the defect is a NESTING relation between two statements — a call sited inside
    # an `async with` block. That is a property of the module's structure and of nothing else; the
    # only behavioural equivalent is a live pool plus enough concurrency to actually deadlock,
    # which is a test that HANGS rather than fails. The detector itself is proven on synthetic
    # source above, so this pin carries the scan and not the logic.
    source = DB.read_text(encoding="utf-8")

    tree = ast.parse(source)
    funcs = [n for n in tree.body if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))]
    acquirers = [n.name for n in funcs if _acquires_directly(n)]
    assert len(acquirers) > 100, (
        f"only {len(acquirers)} acquiring function(s) found in db.py — the detector broke, and a "
        f"broken detector here is indistinguishable from a clean codebase")

    offenders = nested_acquire_offenders(source)
    assert not offenders, (
        "these functions ask the pool for a SECOND connection while holding the first:\n  "
        + "\n  ".join(f"{a} (line {ln}) -> {b}" for a, b, ln in sorted(offenders))
        + "\n\nThe pool is max_size=5 and pool.acquire() has no timeout, so enough concurrent "
          "callers deadlock PERMANENTLY. That is the 2026-09-18 outage: 7.3 hours, 23 jobs, the "
          "evening briefing among them. Either hand over the connection you already hold "
          "(conn=conn, or positionally into a `conn` parameter) or move the call outside the "
          "acquire block."
    )
