"""Reset EVERY module-level mutable state the EP scan can carry between calls — DERIVED, not listed.

WHY (#663). The byte-identity guards run two `run_ep_scan`s in ONE process and assert the results
are identical. `ep_detector` and `ep_theme_belonging` hold module-level dedupe and "seen"
structures that are first-call-does-X / later-calls-skip BY DESIGN — `_tinycap_seen` logs one
audit row per ticker per day, `_rt_fresh_seen` remembers which names printed fresh this session,
`_catalyst_cache` grades once. If the harness does not clear them between the two scans, scan 1
can behave differently from scan 2, and WHETHER it does depends on what earlier tests left behind.
That is precisely the shape of the 2026-09-14 CI flake: passes in isolation, passes on re-run,
fires once.

⚠ **THE LIST IS DERIVED BY AST, NOT WRITTEN DOWN**, because a hand-list is how this hole reopens:
someone adds `_new_seen: set = set()` next month, no test mentions it, and the guard silently
stops being a guard. `state_holders()` walks the modules' own source for module-level mutable
containers and for names rebound via `global`, so a new one is picked up the day it lands — and
`test_663_module_state_is_derived_not_listed.py` fails if one appears that `reset_all()` cannot
clear. [[derive-the-population-never-hand-list-it]]

⚠ WHAT THIS DOES **NOT** ESTABLISH. Clearing these removes ONE class of cross-scan divergence.
The 2026-09-14 event itself has never been reproduced — poisoning each of the four un-reset
structures on 2026-09-22 did NOT make the guard fail. So this closes the named suspect class; it
does not prove the flake cannot recur by some other route, and #663 stays open saying so.
"""
from __future__ import annotations

import ast
import inspect
from functools import lru_cache
from typing import Any

#: The modules whose state a `run_ep_scan` comparison can carry between calls.
WATCHED = ("agents.market_intelligence.ep_detector",
           "agents.market_intelligence.ep_theme_belonging")

#: Containers that are CONFIGURATION or live task-handles, not per-run state. Clearing these
#: would break the process rather than isolate it — each is named with why, so the exclusion is
#: a decision on the record and not an oversight.
_NOT_PER_RUN_STATE = {
    "_COMPOSITE_AXIS_CREDIT_SOURCES": "a constant source table, read-only",
    "_CATALYST_TOOL": "the tool schema handed to the LLM, immutable config",
    "_yoy_bg_tasks": "live asyncio task handles — dropping them lets the GC kill in-flight work",
    "_yoy_bg_started": "guards double-starting those tasks; clearing re-starts them",
    "_WATCHDOG_BG_TASKS": "same strong-ref idiom for the watchdog tasks",
    "_PENDING_PROVIDER_NOTES": "same, for the #680 fire-and-forget audit writes",
    "_claude": "the lazily-built LLM client, not per-run state; tests stub it themselves",
    "_yoy_bg_semaphore": "an asyncio.Semaphore bound to a loop — replacing it mid-process is a bug",
}

#: Modules that own a PROPER reset function. Always prefer it: a blanket `.clear()` is WRONG for
#: a dict the code INDEXES BY KEY. `ep_theme_belonging._ctx_cache` is read as `_ctx_cache["key"]`
#: and `_fit_day` as `_fit_day["date"]`, so clearing them raises KeyError on the next call — the
#: module's own `_reset_cache()` sets those keys to None instead. Found by running this helper
#: before wiring it in; a derived reset that is too blunt breaks the thing it isolates.
_OWN_RESET = {"agents.market_intelligence.ep_theme_belonging": "_reset_cache"}


def state_holders(module: Any) -> "dict[str, str]":
    """{name: kind} for every module-level mutable container and `global`-rebound name in
    `module`'s own source. Kind is 'container' or 'rebound'. The parse is cached per module (the
    source does not change inside a test session; ep_detector alone is ~6,800 lines and
    `reset_all` runs before every compared scan); callers get their own copy."""
    return dict(_state_holders_parsed(module))


@lru_cache(maxsize=None)
def _state_holders_parsed(module: Any) -> "dict[str, str]":
    try:
        tree = ast.parse(inspect.getsource(module))
    except (OSError, TypeError, SyntaxError):
        return {}
    out: dict[str, str] = {}
    for node in tree.body:
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AnnAssign) else [])
        for t in targets:
            if not isinstance(t, ast.Name):
                continue
            v = node.value
            if isinstance(v, (ast.Dict, ast.Set, ast.List)) or (
                    isinstance(v, ast.Call) and isinstance(v.func, ast.Name)
                    and v.func.id in ("dict", "set", "list", "defaultdict", "deque")):
                out[t.id] = "container"
    for node in ast.walk(tree):
        if isinstance(node, ast.Global):
            for n in node.names:
                out.setdefault(n, "rebound")
    return {k: v for k, v in out.items() if k not in _NOT_PER_RUN_STATE}


def reset_all() -> "list[str]":
    """Clear every per-run state holder in WATCHED. Returns the names it cleared, so a caller
    (and the gate) can see the list GROW when a new cache is added rather than discover it in CI."""
    import importlib

    cleared: list[str] = []
    for mod_name in WATCHED:
        mod = importlib.import_module(mod_name)
        own = _OWN_RESET.get(mod_name)
        if own and callable(getattr(mod, own, None)):
            getattr(mod, own)()
            cleared.extend(f"{mod_name.rsplit('.', 1)[-1]}.{n} (via {own})"
                           for n in sorted(state_holders(mod)))
            continue
        for name, kind in state_holders(mod).items():
            cur = getattr(mod, name, None)
            if isinstance(cur, dict):
                cur.clear()
            elif isinstance(cur, set):
                cur.clear()
            elif isinstance(cur, list):
                del cur[:]
            elif kind == "rebound":
                # a date stamp or sentinel paired with one of the containers above; None is what
                # every one of them uses for "nothing seen yet", and it is what forces the
                # container's own date-guard to re-initialise on the next call.
                if not callable(cur):
                    setattr(mod, name, None)
            else:
                continue
            cleared.append(f"{mod_name.rsplit('.', 1)[-1]}.{name}")
    return sorted(cleared)
