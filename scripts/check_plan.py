"""THE single-source-of-truth gate: PLAN.md is the only plan; this enforces it.

WHY (operator 2026-06-16, after the launch-runway spine was missed 3 asks running): we kept ADDING plan
surfaces (calendar, BACKLOG, runway doc, snapshot) and reconciling them BY HAND each session — and the
hand-reconcile kept failing. The fix is not another surface; it is ONE file (PLAN.md) + a MECHANICAL gate,
the only kind of discipline that has ever held in this repo (the deploy bans, the YAML dupe gate).

WHAT this enforces on PLAN.md (every task line `- #<id> | <YYYY-MM-DD> | <status> | <title>`):
  - every task is under a `## <project>` header (filed under a project — no loose tasks);
  - every task has a parseable ETA date and a known status (pending|in_progress|blocked);
  - NO open task has a PAST ETA (must be >= today ET) — the CLOSE ritual rebumps stale dates so the plan
    never silently rots; a past ETA FAILS the commit;
  - task ids are unique.

USAGE:
  python scripts/check_plan.py            # validate (pre-commit gate). exit 1 on any violation.
  python scripts/check_plan.py --today    # OPEN helper: print OVERDUE + due-today open tasks = the day's plan.

ASCII-only output (Windows cp1252 console). Stdlib only. ET "today" per the codebase tz rule.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # PLAN.md titles use em-dashes

REPO = Path(__file__).resolve().parent.parent
PLAN = REPO / "PLAN.md"
SNAPSHOT = REPO / ".apollo_open_tasks.json"  # harness open-task checksum (plumbing, NOT a plan surface)
_ET = ZoneInfo("America/New_York")
_STATUSES = {"pending", "in_progress", "blocked"}
# `- #298 | 2026-06-17 | in_progress | title...`
_TASK = re.compile(r"^- #(\d+)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(\w+)\s*\|\s*(.+?)\s*$")
_PROJECT = re.compile(r"^##\s+(.+?)\s*$")
# Buried-work tripwire (operator 2026-06-17): high-signal phrases that mean a task description is
# DESCRIBING undone critical work inline instead of TRACKING it as its own dated task. Rare +
# high-signal (only #326 tripped it at authoring) so this can be a hard gate, not just a warning.
# The #326/#327 miss: "CRITICAL-PATH BUILD ... = #311[8/1]" buried the near-term build in prose.
_BURIED_WORK = re.compile(r"critical[- ]path build|the only (real )?blocker|critical path\s*[=:]", re.I)


def parse(text: str):
    """-> (tasks, errors). tasks = list of dict(id,eta,status,title,project,line)."""
    tasks, errors = [], []
    project = None
    seen: dict[int, int] = {}
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        pm = _PROJECT.match(line)
        if pm:
            project = pm.group(1)
            continue
        if not line.startswith("- #"):
            continue
        m = _TASK.match(line)
        if not m:
            errors.append(f"L{n}: malformed task line (need `- #<id> | YYYY-MM-DD | status | title`): {line}")
            continue
        tid, eta_s, status, title = int(m.group(1)), m.group(2), m.group(3), m.group(4)
        if project is None:
            errors.append(f"L{n}: task #{tid} is not under a `## <project>` header (loose task)")
        if status not in _STATUSES:
            errors.append(f"L{n}: task #{tid} bad status '{status}' (use {sorted(_STATUSES)})")
        try:
            eta = date.fromisoformat(eta_s)
        except ValueError:
            errors.append(f"L{n}: task #{tid} bad ETA '{eta_s}'")
            eta = None
        if tid in seen:
            errors.append(f"L{n}: task #{tid} duplicate (also L{seen[tid]})")
        seen[tid] = n
        tasks.append({"id": tid, "eta": eta, "status": status, "title": title,
                      "project": project, "line": n})
    return tasks, errors


def main(argv: list[str]) -> int:
    if not PLAN.exists():
        print(f"[plan] ERROR: {PLAN} not found — it is the single source of truth.")
        return 2
    tasks, errors = parse(PLAN.read_text(encoding="utf-8"))
    today = datetime.now(_ET).date()

    if "--today" in argv:
        overdue = sorted([t for t in tasks if t["eta"] and t["eta"] < today], key=lambda t: t["eta"])
        due = sorted([t for t in tasks if t["eta"] == today], key=lambda t: t["project"] or "")
        print(f"=== PLAN — {today} (ET) ===  ({len(tasks)} open tasks total)")
        print(f"\n-- OVERDUE ({len(overdue)}) — rebump or close at CLOSE --")
        for t in overdue or []:
            print(f"  #{t['id']:<4} {t['eta']}  [{t['status']:<11}] {t['project']} — {t['title']}")
        if not overdue:
            print("  (none)")
        print(f"\n-- DUE TODAY ({len(due)}) = the day's plan --")
        for t in due or []:
            print(f"  #{t['id']:<4} [{t['status']:<11}] {t['project']} — {t['title']}")
        if not due:
            print("  (none)")
        return 0

    # validation gate
    past = [t for t in tasks if t["eta"] and t["eta"] < today]
    for t in past:
        errors.append(f"L{t['line']}: task #{t['id']} ETA {t['eta']} is PAST (today {today}) — "
                      f"rebump to a future date at CLOSE, or close the task")

    # buried-work tripwire: when a task NAMES critical-path/blocker build work, that phrase must be
    # IMMEDIATELY followed by the #id of the task that does it — forcing "name it -> point at the
    # task", never "name it -> describe it in prose" (the #326/#327 miss, operator 2026-06-17). The
    # immediate-ref rule is what makes this robust: a naive "has a near-term ref somewhere on the
    # line" check is gameable by an INCIDENTAL ref (#326 says "reuse #270 recorder"), so it would NOT
    # have caught the original. This version WOULD have ("CRITICAL-PATH BUILD (the only real blocker"
    # -> no #id after the phrase). Catches the SHAPE; not a 100% proof of good decomposition.
    for t in tasks:
        for m in _BURIED_WORK.finditer(t["title"]):
            tail = t["title"][m.end(): m.end() + 12]
            if not re.match(r"[\s:=(\[–—-]{0,8}#\d+", tail):
                errors.append(
                    f"L{t['line']}: task #{t['id']} says \"{m.group(0)}\" but does not IMMEDIATELY "
                    f"reference the #task that does it — file that build as its OWN dated task and put "
                    f"its #id right after the phrase (buried-work tripwire); got: ...{tail!r}")
                break  # one flag per task is enough

    # completeness: every OPEN harness task (the snapshot) must be filed in PLAN.md
    plan_ids = {t["id"] for t in tasks}
    if SNAPSHOT.exists():
        try:
            snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
            open_ids = {int(r["id"]) for r in snap
                        if str(r.get("status", "")).lower() not in ("completed", "deleted")}
        except (ValueError, KeyError, TypeError) as e:
            open_ids = set()
            errors.append(f"snapshot {SNAPSHOT.name} unreadable: {e}")
        missing = sorted(open_ids - plan_ids)
        for tid in missing:
            errors.append(f"open task #{tid} is in the snapshot but NOT filed in PLAN.md (add a line under a project)")
        # PLAN ids below the new-launch range (<298) absent from the snapshot = likely CLOSED -> shouldn't be here
        stale = sorted(tid for tid in plan_ids if tid < 298 and tid not in open_ids)
        if stale:
            print(f"[plan] WARN — PLAN.md lists ids not in the open snapshot (likely closed; "
                  f"remove or reconcile): {', '.join('#'+str(t) for t in stale)}")
    if errors:
        print(f"[plan] FAIL — {len(errors)} issue(s) in PLAN.md:")
        for e in errors:
            print(f"    {e}")
        print("\nPLAN.md is the single SoT. Fix above (CLOSE rebumps past ETAs; every task needs a "
              "project + ETA + status), re-stage, re-commit.")
        return 1
    print(f"[plan] OK: {len(tasks)} open tasks, all filed under a project with a non-past ETA.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
