#!/usr/bin/env python3
"""Preflight: keep deploy.sh's execution-scope routing honest (#456, 2026-07-26).

THE BUG CLASS. apollo-execution runs `scheduler.py` and keeps 29 EXECUTION_OWNED
jobs, and those job paths import a large slice of `agents/market_intelligence/`.
But deploy.sh routed `agents/market_intelligence/*` to NEED_MARKET only, so a fix
to any of those modules built into the shared image and left the RUNNING
apollo-execution container on the old code — silent-dark, no error, no signal.
Found while shipping the stop-ack watchdog defer: `scheduler.py` was one of 29
loaded modules and only 4 were routed to the execution scope.

WHY THIS IS A GATE AND NOT A LIST. The obvious fix — enumerate the modules in
deploy.sh — is a hand-synced list, which is precisely the drift this repo keeps
losing to (the root-yaml COPY class, #474; the three hand-synced ticker-extraction
copies, #260). So the list is machine-DERIVED here and this preflight fails the
deploy when the checked-in list no longer matches what the execution container
actually imports. Adding a new import to an execution-owned path is therefore
caught at deploy time instead of by a stale container weeks later.

DIRECTION OF FAILURE. Fails on UNDER-coverage (a module the container loads that
deploy.sh would not route to execution) — that is the silent-dark direction.
Over-coverage (a listed module no longer imported) is reported as a warning, not
a failure: it only costs an unnecessary container recreate, and failing the deploy
over it would be its own foot-gun.

USAGE
    python -m scripts.preflight_exec_deploy_scope            # check (deploy gate)
    python -m scripts.preflight_exec_deploy_scope --emit     # regenerate the list

Must run INSIDE a container that can import the package (deploy.sh runs it via
`docker exec $PREFLIGHT_CONTAINER`), because the derivation is a real import.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_LIST_REL = "scripts/exec_loaded_modules.txt"
_PKG = "agents.market_intelligence"


def _repo_root() -> Path:
    """The directory containing `agents/` — works in-container (/app) and in-repo."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "agents" / "market_intelligence").is_dir():
            return parent
    raise SystemExit("preflight_exec_deploy_scope: cannot locate the repo root")


def derive_loaded_modules() -> set[str]:
    """Repo-relative paths of every `agents/market_intelligence` module that
    importing the EXECUTION entrypoint pulls in.

    SERVICE_ROLE is FORCED to `execution` (not setdefault) before any import: the
    role is read at import time in places, and this preflight normally runs in the
    market-agent container, which would otherwise carry its own role and understate
    the set — the exact under-coverage this gate exists to catch. Safe because a
    fresh `python -m` process has not imported the package yet.
    """
    os.environ["SERVICE_ROLE"] = "execution"
    root = _repo_root()

    # These two are what the execution container itself imports at boot: the
    # agent entrypoint, and the scheduler that registers the execution-owned jobs.
    import agents.market_intelligence.agent  # noqa: F401
    import agents.market_intelligence.scheduler  # noqa: F401

    paths: set[str] = set()
    for name, mod in list(sys.modules.items()):
        if not name.startswith(_PKG):
            continue
        f = getattr(mod, "__file__", None)
        if not f:
            continue  # namespace package — nothing to deploy
        try:
            rel = Path(f).resolve().relative_to(root)
        except ValueError:
            continue  # imported from outside the repo (shouldn't happen)
        paths.add(str(rel))
    return paths


def derive_broker_modules(root: Path) -> set[str]:
    """Every `broker/*.py` — execution-loaded BY DEFINITION, not by observation.

    WHY (found 2026-08-02). `derive_loaded_modules` samples `sys.modules` after importing the
    entrypoints, so it only sees IMPORT-TIME imports. A module imported LAZILY inside a function
    body is invisible to it. `broker/entry_pipeline.py` is exactly that:
    `live_tracker.process_new_alerts_live` is imported inside `_orb_monitor_job`, and with
    `EXECUTION_MODE=http` that job RUNS ON apollo-execution — yet entry_pipeline was absent from the
    generated list, so a change to it alone would not have routed to the execution scope and the
    container would have kept running stale ENTRY code. The #456 silent-dark class, on the money
    path.

    ⚠ A transitive AST closure was tried first and REJECTED: seeded from either the entrypoints or
    from broker/ it returns 132 of ~150 modules, because everything in this package eventually
    imports everything. That makes the scope gate meaningless ("always deploy both") rather than
    safer. A shipped guard that always fires is not a guard.

    So the rule is definitional and narrow instead, matching CLAUDE.md's own statement that
    *"broker/ + execution_routes RUN on apollo-execution"*. Unioned with the runtime derivation,
    which still covers everything reached at import time or dynamically.
    """
    d = root / "agents" / "market_intelligence" / "broker"
    if not d.is_dir():
        return set()
    return {str(f.resolve().relative_to(root)) for f in d.glob("*.py")}


def read_list(root: Path) -> set[str]:
    p = root / _LIST_REL
    if not p.exists():
        return set()
    return {
        ln.strip() for ln in p.read_text().splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    }


def main() -> int:
    root = _repo_root()
    emit = "--emit" in sys.argv

    try:
        # UNION of two derivations — neither alone is sufficient. Runtime sampling misses
        # modules imported LAZILY inside function bodies (entry_pipeline, 2026-08-02). The broker
        # rule is definitional. Under-coverage is the silent-dark direction, so take both.
        derived = derive_loaded_modules() | derive_broker_modules(root)
    except Exception as e:  # an import failure here is itself a real problem
        print(f"✘ preflight exec-deploy-scope: could not import the execution "
              f"entrypoint to derive the module set: {e!r}")
        return 1

    if emit:
        header = (
            "# GENERATED — do not hand-edit.\n"
            "# Regenerate: docker exec <container> python -m "
            "scripts.preflight_exec_deploy_scope --emit\n"
            "#\n"
            "# Every agents/market_intelligence module that apollo-execution loads.\n"
            "# deploy.sh routes a change to any of these to the EXECUTION scope as\n"
            "# well as market-agent — otherwise the fix builds into the image and the\n"
            "# RUNNING execution container stays stale (#456). Drift is caught by the\n"
            "# preflight that generated this file.\n"
        )
        (root / _LIST_REL).write_text(header + "\n".join(sorted(derived)) + "\n")
        print(f"wrote {_LIST_REL} — {len(derived)} modules")
        return 0

    listed = read_list(root)
    # broker/* and execution_routes.py already have their own explicit deploy.sh
    # arm (#324), so they are covered whether or not they appear in the list.
    def _already_armed(p: str) -> bool:
        return (p.startswith("agents/market_intelligence/broker/")
                or p == "agents/market_intelligence/execution_routes.py")

    missing = {p for p in derived if p not in listed and not _already_armed(p)}
    stale = {p for p in listed if p not in derived}

    if missing:
        print("✘ preflight exec-deploy-scope: apollo-execution imports modules that "
              "deploy.sh would NOT route to the execution scope.")
        print("  A change to one of these would build into the image and leave the "
              "RUNNING execution container stale (silent-dark, #456):")
        for p in sorted(missing):
            print(f"    + {p}")
        print(f"\n  Fix: regenerate the list —")
        print(f"    docker exec <container> python -m "
              f"scripts.preflight_exec_deploy_scope --emit")
        print(f"  then commit {_LIST_REL}.")
        return 1

    if stale:
        print(f"⚠ preflight exec-deploy-scope: {len(stale)} listed module(s) no "
              f"longer imported by the execution entrypoint "
              f"(harmless — costs an extra container recreate; regenerate when convenient):")
        for p in sorted(stale):
            print(f"    - {p}")

    print(f"Preflight exec-deploy-scope — OK ({len(derived)} execution-loaded "
          f"modules, all routed to the execution scope).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
