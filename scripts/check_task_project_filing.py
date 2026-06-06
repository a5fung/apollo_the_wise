"""Governance gate: every OPEN #-task is filed under exactly one project.

WHY (operator 2026-06-06): the "every #-task gets a project AT CREATION" rule was
prose discipline in CLAUDE.md — and prose-that-depends-on-memory is exactly what
failed (twice: the timezone bug class, then 2026-06-06 when #216/#217 were created
with a metadata.project tag but never landed in BACKLOG's hierarchy, and the
OPERATOR had to be the one to catch it). The operator's complaint is precisely
"why do I need to ask every time" — so the fix is a MECHANISM that fires at a
boundary nobody has to choose to run, not another paragraph.

WHAT this reconciles:
  - OPEN task set  ............ `.apollo_open_tasks.json` (refreshed from the
        #-task tracker at CLOSE / whenever tasks change — see CLAUDE.md CLOSE step).
  - Filed-under-project set ... the `#NNN` IDs that appear in BACKLOG.md's
        "📂 Open tasks by project (hierarchy — no loose tasks)" section.

FAILS (exit 1) when an open task is:
  - UNFILED   — present in the snapshot, absent from every project bucket.
  - DOUBLE-FILED — appears under more than one bucket (ambiguous home).
WARNS (exit 0) when a bucket references an ID that is no longer open (STALE) — a
  hygiene nudge, not a blocker (closing a task shouldn't fail a commit).

The harness #-task tracker is the SoT and lives outside the repo, so no repo-side
check can read it directly — the snapshot is the bridge. The residual gap ("task
created, snapshot never refreshed") is closed by refreshing the snapshot as the
FIRST step of the CLOSE ritual, which the operator triggers regardless ("where do
we stand" / wrap). This gate then makes snapshot↔BACKLOG drift non-bypassable at
commit time.

Windows note: ASCII-only output (PowerShell cp1252 console UnicodeEncodeErrors on
the failure path otherwise — same convention as preflight_command_parity.py).

Usage:
    python scripts/check_task_project_filing.py [open_tasks.json] [BACKLOG.md]
Exit 0 = clean (or stale-only). Exit 1 = unfiled/double-filed. Exit 2 = bad input.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SNAPSHOT = REPO_ROOT / ".apollo_open_tasks.json"
DEFAULT_BACKLOG = REPO_ROOT / "BACKLOG.md"

# The hierarchy section we parse. Start at this header, stop at the first "---"
# horizontal rule or the next top-level "## " heading after it.
_SECTION_START = "## "  # any H2; we match the specific one by substring below
_SECTION_MARKER = "Open tasks by project"
_ID_RE = re.compile(r"#(\d{1,4})\b")


def load_open_ids(snapshot_path: Path) -> dict[int, dict]:
    """Return {id: task_dict} for OPEN tasks (status pending/in_progress).

    Snapshot schema: a JSON list of objects, each at least {"id": int,
    "status": str}. Anything not pending/in_progress is ignored (defensive: the
    snapshot SHOULD already be open-only, but we filter so a full-dump also works)."""
    raw = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("snapshot must be a JSON list of task objects")
    out: dict[int, dict] = {}
    for t in raw:
        if not isinstance(t, dict) or "id" not in t:
            raise ValueError(f"bad task entry (need 'id'): {t!r}")
        status = str(t.get("status", "pending")).lower()
        if status in ("completed", "deleted"):
            continue
        out[int(t["id"])] = t
    return out


def extract_section(backlog_text: str) -> str:
    """Slice out the 'Open tasks by project' hierarchy section."""
    lines = backlog_text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith(_SECTION_START) and _SECTION_MARKER in ln:
            start = i
            break
    if start is None:
        raise ValueError(
            f"BACKLOG.md has no '{_SECTION_MARKER}' H2 section — cannot reconcile"
        )
    end = len(lines)
    for j in range(start + 1, len(lines)):
        ln = lines[j]
        if ln.strip() == "---" or (ln.startswith("## ") and j != start):
            end = j
            break
    return "\n".join(lines[start:end])


_PAREN_RE = re.compile(r"\([^()]*\)")


def parse_buckets(section_text: str) -> tuple[set[int], dict[int, int]]:
    """Parse the hierarchy section into:
      - present_anywhere: every #ID mentioned in any bucket line (generous — used
            for the UNFILED check so a legit cross-ref never causes a false fail).
      - primary_counts: per-ID count of PRIMARY filings (occurrences OUTSIDE
            parentheses). Cross-references in prose (e.g. '#172 ... gated behind
            #151 split') live in parens, so stripping parens before counting keeps
            the DOUBLE-FILED check from false-flagging a cross-ref as a 2nd home.
    A 'bucket' is a top-level '- **Name** ...' list item; an ID counts once per
    bucket line for the primary count (repeats within one line collapse)."""
    present: set[int] = set()
    primary: dict[int, int] = {}
    for ln in section_text.splitlines():
        if not ln.lstrip().startswith("- "):
            continue
        present.update(int(m) for m in _ID_RE.findall(ln))
        bare = _PAREN_RE.sub("", ln)  # drop (...) cross-ref spans
        for tid in {int(m) for m in _ID_RE.findall(bare)}:
            primary[tid] = primary.get(tid, 0) + 1
    return present, primary


def reconcile(open_ids: dict[int, dict], present: set[int],
              primary: dict[int, int]) -> dict[str, list]:
    open_set = set(open_ids)
    unfiled = sorted(open_set - present)
    double = sorted(tid for tid in open_set if primary.get(tid, 0) > 1)
    stale = sorted(present - open_set)
    return {"unfiled": unfiled, "double": double, "stale": stale}


def main(argv: list[str]) -> int:
    snap = Path(argv[1]) if len(argv) > 1 else DEFAULT_SNAPSHOT
    backlog = Path(argv[2]) if len(argv) > 2 else DEFAULT_BACKLOG

    if not snap.exists():
        print(f"[task-filing] SKIP: no open-task snapshot at {snap}")
        print("  (refresh it at CLOSE: export open #-tasks -> .apollo_open_tasks.json)")
        return 0  # absence is not a commit-blocker; CLOSE produces it
    if not backlog.exists():
        print(f"[task-filing] ERROR: BACKLOG not found at {backlog}")
        return 2

    try:
        open_ids = load_open_ids(snap)
        section = extract_section(backlog.read_text(encoding="utf-8"))
        present, primary = parse_buckets(section)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"[task-filing] ERROR: {e}")
        return 2

    r = reconcile(open_ids, present, primary)

    if r["stale"]:
        print("[task-filing] WARN stale bucket refs (filed but no longer open): "
              + ", ".join(f"#{t}" for t in r["stale"]))

    if not r["unfiled"] and not r["double"]:
        print(f"[task-filing] OK: all {len(open_ids)} open tasks filed under a project.")
        return 0

    if r["unfiled"]:
        print("[task-filing] FAIL UNFILED (open task, no project bucket in BACKLOG):")
        for t in r["unfiled"]:
            print(f"    #{t}  -> add under a project in BACKLOG.md 'Open tasks by "
                  f"project' (Miscellaneous if none fits)")
    if r["double"]:
        print("[task-filing] FAIL DOUBLE-FILED (open task under >1 bucket):")
        for t in r["double"]:
            print(f"    #{t}  -> pick ONE home bucket")
    print("\nThe 'every #-task gets a project AT CREATION' rule is mechanical now — "
          "file the task above, re-stage BACKLOG.md, re-commit.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
