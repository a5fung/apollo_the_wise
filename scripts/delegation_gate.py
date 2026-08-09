#!/usr/bin/env python3
"""PreToolUse gate: a main-loop write into an implementation path is DENIED unless today's
routing declaration consciously routed that work to the main thread.

WHY A PreToolUse BLOCK AND NOT ANOTHER LEDGER (2026-08-09)
`delegation_report.py` already ships both retrospective surfaces — a routing declaration at
OPEN and a ledger at CLOSE. Both sit at the ENDS of the day; the failure happens in the middle:
within an hour of that ledger shipping, routing was pinned AFTER six main-thread tool calls had
already done the work, and the operator caught it again ("we literally just fixed the delegation
card thing, what happened here?"). This repo's history is unambiguous — reporting surfaces
drift, things that BLOCK hold (report_format_gate.py holds; check_plan.py's commit gates hold;
every prose/ledger reconcile has failed). So the intervention moves to the only moment that
cannot be reported around: the instant the edit is attempted.

WHAT IT IS NOT: a security boundary. It is a tripwire for the habitual inline-edit pattern.
A determined evader can always route a write through indirection the text scan cannot see
(variables, base64, git apply). That is fine — the target is drift, not adversaries, and the
escape hatch is a conscious, visible DECLARATION (`delegation_report.py --route "#N:main"`),
not a bypass. The same file the CLOSE ledger cross-checks, so the choice leaves a trail.

MAIN LOOP vs SUBAGENT — measured, not assumed (Claude Code 2.1.221, 2026-08-09)
A spawned card's first edit must NOT die on this gate, or delegation itself breaks. The
discriminator was established EMPIRICALLY by logging real PreToolUse payloads from a probe
session that did a main-loop Write and then a Task-subagent Write:
  - main loop keys:  cwd, hook_event_name, permission_mode, prompt_id, session_id,
                     tool_input, tool_name, tool_use_id, transcript_path
  - subagent adds:   agent_id, agent_type          (everything else identical)
  - session_id and transcript_path are IDENTICAL in both — they CANNOT discriminate.
So: `agent_id`/`agent_type` present -> subagent -> always allow. If a future harness stops
sending those fields, subagent edits would start denying with the actionable message below
(annoying, loud, instantly diagnosable) — not silently wedging; the env kill switch
(DELEGATION_GATE=off) is the immediate stopgap while the discriminator is re-measured.

FAIL-OPEN CONTRACT (matches report_format_gate.py): any unexpected error — unreadable stdin,
bad JSON, classification blow-up — allows the call. ONE deliberate exception to "missing file
= fail open": an ABSENT routing declaration is not an error, it is the gate's trigger. If a
missing `.apollo_routing.json` allowed everything, the hook would be a no-op on exactly the
undeclared day it exists to catch. A CORRUPT routing file is treated the same as absent
(deny path) because the one-command fix (`--route`) also repairs the file.

Output contract: exit 0 always. Deny = JSON `hookSpecificOutput.permissionDecision:"deny"`
on stdout (harness feeds the reason back to the model); allow = no output. If the harness
ever fails to parse the JSON it treats it as plain text and proceeds — the failure direction
is open, which is the correct direction for a discipline gate.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_PT = ZoneInfo("America/Los_Angeles")
REPO = Path(__file__).resolve().parents[1]

# The surfaces whose main-loop edits are card-shaped work (CLAUDE.md operating model: Sonnet
# for mechanical, Fable for the hard part). Includes broker/ even though this checkout has no
# such dir today — delegation_report.py's IMPL_DIRS counts it as implementation and the two
# surfaces must agree on what "implementation" means.
GATED_DIRS = ("agents/", "core/", "channels/", "shared/", "scripts/",
              "infra/", "tests/", "broker/")
# Probe output is analysis artifact, not implementation (mirrors delegation_report.IMPL_EXCLUDE;
# the probe TSVs in git status are exactly this legitimate main-thread pattern).
GATED_EXCLUDE = ("scripts/probes/",)

# Legitimately-main-loop bookkeeping — never gated, by basename wherever it lives.
ALWAYS_ALLOWED_BASENAMES = frozenset({
    "PLAN.md", "CLAUDE.md", "CHANGELOG.md", "HANDOFF.md",
    ".apollo_open_tasks.json", ".apollo_session_baseline.json", ".apollo_routing.json",
    "data_gated_reviews.yaml",
})

# "opus" counts too: in the operating model Opus IS the main loop, and the ledger's own
# discrepancy check (route_discrepancies) already treats main and opus as the same declaration.
_MAIN_WHO = frozenset({"main", "opus"})

_EDIT_TOOL_PATH_KEY = {"Edit": "file_path", "Write": "file_path",
                       "NotebookEdit": "notebook_path"}

# ── bash write-target extraction ─────────────────────────────────────────────────────────────
# Bash-in-disguise is how half the drift happens — a gate that only sees Edit/Write is already
# defeated. Text-level scan, deliberately conservative in BOTH directions: extraction over-
# collects candidate tokens and classify() filters them (a token that does not resolve into a
# gated repo dir can never deny), while unattributable writes (variable filenames in inline
# python) are allowed — see "NOT a security boundary" above.

# `> file` / `>> file` / `2> file` / `&> file`; refuses `2>&1` (fd dup, not a file write).
_REDIRECT = re.compile(
    r'(?:^|[\s;|&(])(?:\d*>>?|&>>?)(?!\s*&)\s*("[^"]*"|\'[^\']*\'|[^\s;|&<>]+)')
# Inline python writes with a LITERAL path — the only attribution the text supports honestly.
_PY_OPEN_WRITE = re.compile(
    r'''open\(\s*(?:[rbf]{1,2})?["']([^"']+)["']\s*,\s*["'][^"']*[wax+][^"']*["']''')
_PY_PATH_WRITE = re.compile(
    r'''Path\(\s*["']([^"']+)["']\s*\)\s*\.\s*write_(?:text|bytes)''')

_SEGMENT_SPLIT = re.compile(r"\|\||&&|[;|\n]")


def _segment_targets(segment: str) -> list[str]:
    """Write targets of one pipeline segment: tee / sed -i / cp / mv / install / rsync."""
    try:
        toks = shlex.split(segment)
    except ValueError:           # unbalanced quotes — heredoc bodies etc.; fall back crudely
        toks = segment.split()
    if not toks:
        return []
    if toks[0] in ("sudo", "command", "nohup", "env") and len(toks) > 1:
        toks = toks[1:]
    cmd, rest = toks[0], toks[1:]
    args = [t for t in rest if not t.startswith("-")]
    if cmd == "tee":
        return args
    if cmd == "sed" and any(t.startswith("-i") for t in rest):
        # every non-flag token is a candidate; the s/// expression won't classify as gated
        return args
    if cmd in ("cp", "mv", "install", "rsync") and len(args) >= 2:
        return [args[-1]]        # destination
    return []


def bash_write_targets(command: str) -> list[str]:
    """Every path this command text can be seen writing to. Over-collection is fine —
    classify() is the filter; only tokens resolving into GATED_DIRS can ever deny."""
    targets = [m.strip("\"'") for m in _REDIRECT.findall(command)]
    for seg in _SEGMENT_SPLIT.split(command):
        targets.extend(_segment_targets(seg))
    targets.extend(_PY_OPEN_WRITE.findall(command))
    targets.extend(_PY_PATH_WRITE.findall(command))
    return targets


# ── path classification ──────────────────────────────────────────────────────────────────────

def classify_gated(target: str, cwd: str) -> str | None:
    """repo-relative path if the target is gated implementation surface, else None.

    The allow-list is checked FIRST and broadly (scratch, memory, bookkeeping basenames,
    docs/, .claude/, outside-repo): a false DENY is the failure mode that gets a discipline
    gate switched off within a week, so every ambiguity resolves toward allow."""
    if not target or not isinstance(target, str):
        return None
    t = target.strip().strip("\"'")
    if not t or t.startswith("-"):
        return None
    t = t.replace("${CLAUDE_PROJECT_DIR}", str(REPO)).replace("$CLAUDE_PROJECT_DIR", str(REPO))
    t = os.path.expanduser(t)
    p = Path(t)
    if not p.is_absolute():
        p = Path(cwd or str(REPO)) / p
    fp = os.path.normpath(str(p))
    if "/scratchpad" in fp or fp.startswith(("/tmp/", "/private/tmp/", "/dev/")):
        return None
    if "/memory/" in fp or os.path.basename(fp) in ALWAYS_ALLOWED_BASENAMES:
        return None
    try:
        rel = str(Path(fp).relative_to(REPO))
    except ValueError:
        return None              # outside the repo — never our business
    if rel == ".claude" or rel.startswith((".claude/", "docs/")):
        return None
    # `cp new.py scripts/` writes INTO the dir — normpath strips the trailing slash, so the
    # bare dir name must gate (and be excludable) exactly like a file underneath it.
    if any(rel == ex.rstrip("/") or rel.startswith(ex) for ex in GATED_EXCLUDE):
        return None
    if any(rel == d.rstrip("/") or rel.startswith(d) for d in GATED_DIRS):
        return rel
    return None


# ── routing declaration ──────────────────────────────────────────────────────────────────────

def _routing_file() -> Path:
    env = os.environ.get("APOLLO_ROUTING_FILE")     # test override, same spirit as
    return Path(env) if env else REPO / ".apollo_routing.json"  # APOLLO_TRANSCRIPT_DIR


def routed_main_today() -> bool:
    """True iff today's (PT) declaration routes at least one piece of work to the main thread.

    Day-granular on purpose: the point is that the CHOICE was made consciously this morning
    (or re-declared mid-day), not to map every file to a task number — that mapping is the
    CLOSE ledger's job. Absent/stale/corrupt file = no declaration (see module docstring for
    why absence is the trigger, not an error to fail open on)."""
    try:
        data = json.loads(_routing_file().read_text())
        if data.get("pt_date") != datetime.now(_PT).date().isoformat():
            return False
        return any(isinstance(r, dict) and r.get("who") in _MAIN_WHO
                   for r in data.get("routes") or [])
    except (OSError, json.JSONDecodeError, ValueError, AttributeError):
        return False


# ── verdict ──────────────────────────────────────────────────────────────────────────────────

def _deny(rel: str) -> None:
    reason = (
        f"DELEGATION GATE — main-loop write into implementation path: {rel}\n"
        "Implementation work routes to a card (Sonnet for mechanical, Fable for the hard "
        "part — CLAUDE.md operating model). Spawn the Agent instead of editing inline.\n"
        "Bookkeeping is never gated: PLAN.md, CLAUDE.md, CHANGELOG.md, docs/, .claude/, "
        "memory, scratchpad, scripts/probes/.\n"
        "If main-thread IS the right call for this work, declare it, then retry:\n"
        '    python3 scripts/delegation_report.py --route "#<task>:main:<one-line reason>"\n'
        "The declaration is the escape by design — visible at OPEN, cross-checked by the "
        "CLOSE ledger. A conscious decision, not a bypass."
    )
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))


def main() -> int:
    try:
        if os.environ.get("DELEGATION_GATE") == "off":
            return 0
        try:
            payload = json.load(sys.stdin)
        except (json.JSONDecodeError, ValueError):
            return 0             # unreadable payload -> nothing to judge; never wedge
        if not isinstance(payload, dict):
            return 0
        # Subagent -> always allow. Empirical discriminator (see module docstring): these two
        # fields exist ONLY in subagent payloads; session_id/transcript_path do not differ.
        if payload.get("agent_id") or payload.get("agent_type"):
            return 0
        tool = payload.get("tool_name")
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0
        cwd = payload.get("cwd") or str(REPO)
        if tool in _EDIT_TOOL_PATH_KEY:
            targets = [tool_input.get(_EDIT_TOOL_PATH_KEY[tool])]
        elif tool == "Bash":
            targets = bash_write_targets(str(tool_input.get("command") or ""))
        else:
            return 0
        for target in targets:
            rel = classify_gated(target, cwd)
            if rel is not None:
                if routed_main_today():
                    return 0     # the choice was declared — that is all this gate asks
                _deny(rel)
                return 0
        return 0
    except Exception:            # noqa: BLE001 — fail OPEN, always: a discipline gate must
        return 0                 # never be able to wedge a session (report_format_gate rule)


if __name__ == "__main__":
    sys.exit(main())
