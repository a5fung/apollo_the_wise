#!/usr/bin/env python3
"""Shared contract between scripts/delegation_gate.py (PreToolUse block) and
scripts/delegation_report.py (CLOSE ledger) — the constants and pure logic that MUST agree
between the two surfaces for the gate's own claim ("the two surfaces must agree on what
implementation means", delegation_gate.py:62-63) to actually hold. A 4-reviewer pass on
2026-08-09 found the two had already diverged (GATED_DIRS vs IMPL_DIRS differed on infra/ and
tests/; the basename allow-lists were byte-identical copies with nothing keeping them so; both
files independently re-implemented reading + parsing .apollo_routing.json). This module is the
single place those things live now.

DELIBERATELY INERT AT IMPORT TIME. delegation_gate.py is a PreToolUse hook whose fail-open
contract lives INSIDE main()'s try/except — a module-scope import that raised would fire
BEFORE that guard and crash the hook (block every edit) instead of failing open. So this
module does nothing at import but define constants and pure functions: stdlib imports only,
no file I/O, no env reads, no computation that can raise. Environment/filesystem access
happens only inside function bodies, only when called. Both callers additionally wrap the
`from delegation_shared import ...` itself in a guarded try/except with an allow-biased
fallback (see the top of each file) as a second belt for the case this module fails to import
at all (e.g. someone breaks it while both are checked out mid-edit).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# The single list both surfaces key off: the gate blocks undeclared main-loop writes here,
# the ledger counts main-loop edits here as "impl" for the CARD-SHAPED report. Widened
# 2026-08-09 to fix the divergence: delegation_report.py's old IMPL_DIRS (6 dirs) was missing
# infra/ and tests/, which delegation_gate.py's GATED_DIRS (8 dirs) already gated — an edit to
# either was blocked, forcing a #N:main declaration, and the ledger then silently never
# counted it as inline implementation work. Widened the REPORT to match the GATE (not narrowed
# the gate), because both are legitimately card-shaped work under the CLAUDE.md operating
# model: tests are explicitly named Sonnet-card territory ("scoped well-specified builds,
# tests, refactors, sweeps"), and infra/ holds deploy.sh/restore.sh/service_watchdog.sh —
# production-adjacent scripts that should route through the same conscious-declaration
# discipline as everything else, not get a quiet exemption. Includes broker/ even though this
# checkout has no such dir today (forward-looking; matches the pre-existing gate comment).
IMPL_DIRS = ("agents/", "core/", "channels/", "shared/", "scripts/",
             "infra/", "tests/", "broker/")

# Note: delegation_report.classify_path() early-returns a dedicated "tests" bucket for
# anything under tests/ BEFORE it ever consults IMPL_DIRS (same for "docs"), so tests/'s
# membership here does not change classify_path's per-file label — it stays informative
# ("wrote tests" vs "built a detector"). It IS still consulted by
# delegation_report.CARD_SHAPED_CLASSES so tests/ edits count toward card-shaped detection,
# which is the behavior that actually needed fixing.

# Probe output is analysis artifact, not implementation — the scripts/probes/ TSVs that show
# up in `git status` from a live run are exactly this legitimate main-thread pattern.
IMPL_EXCLUDE = ("scripts/probes/",)

# Legitimately-main-loop bookkeeping — never gated, never counted as implementation, by
# basename wherever it lives.
BOOKKEEPING_BASENAMES = frozenset({
    "PLAN.md", "CLAUDE.md", "CHANGELOG.md", "HANDOFF.md",
    ".apollo_open_tasks.json", ".apollo_session_baseline.json", ".apollo_routing.json",
    "data_gated_reviews.yaml",
})

# "opus" counts too: in the operating model Opus IS the main loop, and the ledger's
# main/opus cross-check (delegation_report.main_route_crosscheck) treats them identically.
MAIN_WHO = frozenset({"main", "opus"})


def routing_file_path() -> Path:
    """.apollo_routing.json location — APOLLO_ROUTING_FILE overrides for tests. Previously
    the gate honored this env var and the report hardcoded the path (2026-08-09 finding #4,
    the other half of it); both now resolve it the same way."""
    env = os.environ.get("APOLLO_ROUTING_FILE")
    return Path(env) if env else REPO / ".apollo_routing.json"


def load_routing_for_day(day: str, path: Path | None = None) -> list[dict]:
    """Routes declared for `day` (PT), or [] if the file is absent/stale/corrupt — the one
    parse+validate path delegation_gate.routed_main_today and delegation_report.load_routes
    now both call instead of each re-implementing the same read/parse/date-check/except
    tuple. `path` override lets a caller that keeps its own mutable path attribute (the report
    does, so its tests can keep monkeypatching it) pass it through explicitly."""
    p = path if path is not None else routing_file_path()
    try:
        data = json.loads(p.read_text())
        if data.get("pt_date") == day and isinstance(data.get("routes"), list):
            return [r for r in data["routes"] if isinstance(r, dict)]
    except (OSError, json.JSONDecodeError, ValueError, AttributeError):
        pass
    return []
