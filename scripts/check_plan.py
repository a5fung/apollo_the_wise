"""THE single-source-of-truth gate: PLAN.md is the only plan; this enforces it.

WHY (operator 2026-06-16, after the launch-runway spine was missed 3 asks running): we kept ADDING plan
surfaces (calendar, BACKLOG, runway doc, snapshot) and reconciling them BY HAND each session — and the
hand-reconcile kept failing. The fix is not another surface; it is ONE file (PLAN.md) + a MECHANICAL gate,
the only kind of discipline that has ever held in this repo (the deploy bans, the YAML dupe gate).

WHAT this enforces on PLAN.md (every task line `- #<id> | <YYYY-MM-DD> | <status> | <title>`):
  - every task is under a `## <project>` header (filed under a project — no loose tasks);
  - every task has a parseable ETA date and a known status (pending|in_progress|blocked|deployed);
  - NO open task has a PAST ETA (must be >= today in the operator's PT day) — the CLOSE ritual rebumps stale dates so the plan
    never silently rots; a past ETA FAILS the commit;
  - `deployed` = built + shipped to prod, AWAITING verify-live (operator 2026-07-18): its ETA is the
    VERIFY-DATE — the day its effect becomes checkable in prod. A past verify-date FAILS the commit via
    the SAME past-ETA gate (verify-worded): VERIFY-LIVE in prod + close, or rebump the verify-date.
    This makes "done = VERIFIED-LIVE, not deployed" a STATUS with teeth instead of forgettable prose —
    built tasks stop sitting `in_progress` under a stale to-build headline and getting re-built;
  - task ids are unique.

USAGE:
  python scripts/check_plan.py            # validate (pre-commit gate). exit 1 on any violation.
  python scripts/check_plan.py --today    # OPEN helper: OVERDUE + due-today + VERIFY-DUE (deployed
                                          #   tasks whose verify window is here) + LIKELY-BUILT
                                          #   (reads as built but still in_progress/pending —
                                          #   reclassify to `deployed` or close) = the day's plan.

ASCII-only output (Windows cp1252 console). Stdlib only. "today" = the operator's PT day (PLAN ETAs are
the operator's PLANNING dates, NOT market/ET — the "ALWAYS ET" rule is for trading code only).
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
# PLAN ETAs are the OPERATOR's PLANNING dates in THEIR timezone (Pacific) — NOT market/ET dates.
# Comparing against ET force-churns tasks in the late-night-PT window (ET has rolled to tomorrow, PT
# hasn't) — the recurring timezone friction. The codebase "ALWAYS ET" rule is for MARKET code (ORB
# windows / market hours), NOT the operator's to-do dates. (Operator is PT; feedback_operator_timezone_pdt.)
_OPERATOR_TZ = ZoneInfo("America/Los_Angeles")
# `deployed` (operator 2026-07-18) = built + shipped, AWAITING verify-live; ETA = the VERIFY-DATE.
_STATUSES = {"pending", "in_progress", "blocked", "deployed"}
# `- #298 | 2026-06-17 | in_progress | title...`
_TASK = re.compile(r"^- #(\d+)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(\w+)\s*\|\s*(.+?)\s*$")
_PROJECT = re.compile(r"^##\s+(.+?)\s*$")
# Deploy-marker (operator 2026-07-18): a task LINE that reads as already-built — a `>> BUILT` /
# `DEPLOYED` note, a verify-live mention, or a dated lowercase "deployed YYYY-…" — while its STATUS
# still says in_progress/pending. These are exactly the tasks that get re-checked/re-built off a
# stale to-build headline (the note is appended at the END of a long line; the status never flips).
# Surfaced every OPEN by `--today` (LIKELY-BUILT) → reclassify to `deployed` (+ a verify-date) or
# close. A SURFACE, not a hard gate (mirrors the looks_thin/--audit-new precedent): many hits are
# legit partial deploys. Case-sensitive on purpose — lowercase "deploy(ed)" prose counts only when
# date-stamped; a plain to-build title ("build X + deploy market-agent") must NOT trip it.
_DEPLOY_MARKER = re.compile(r"DEPLOYED|>>\s*BUILT|verify-live|VERIFY-LIVE|deployed \d{4}-")

# --- SWEEP SUPPRESSION (2026-08-06) -----------------------------------------------------------
# `_DEPLOY_MARKER` asks "has this line EVER mentioned a deploy", not "is this line's headline
# lying". Task lines accumulate `>>` updates forever, so any multi-part task that ships ONE piece
# matches for the rest of its life and can never stop matching. Measured 2026-08-06 on the live
# board: all 9 flagged tasks were checked one by one and **all 9 were already correctly
# classified** — a 100% false-positive rate. Three of them (#261, #327, #452) even carried a prose
# note from the 2026-07-31 sweep saying "checked, classification is HONEST, no change" and were
# re-flagged anyway, because prose is invisible to a regex.
#
# That is this repo's own documented failure mode — "a guard that always fires is not a guard"
# (CLAUDE.md 2026-08-03) — and it is precisely why the operator's 07-18 note says this surface
# "got triaged as housekeeping and ignored". A surface at 9/9 noise trains you to skip it, and
# then the ONE real misclassification hides in the list.
#
# Fix mirrors the `revalidated:` idiom already used by the stale-block gate below: a dated
# `swept:YYYY-MM-DD` marker suppresses the line until the marker ages out. The date is the point —
# it forces a RE-CHECK against today's reality on a cadence rather than silencing it forever, and
# a line that materially changes gets re-swept when its marker expires.
_SWEPT = re.compile(r'swept:\s*(\d{4}-\d{2}-\d{2})(?::([0-9a-f]{4}))?', re.I)
_SWEEP_MAX_AGE = 30        # days a LIKELY-BUILT sweep-check stays good

# The whole `[swept:...]` bracket, stripped before hashing so the marker cannot hash itself.
_SWEPT_TAG = re.compile(r'\s*\[swept:[^\]]*\]', re.I)


def sweep_fingerprint(title: str) -> str:
    """4-hex-char digest of the line WITHOUT its sweep tag — what the sweep was a judgement about.

    Content-keyed, not just time-keyed, because a date alone answers the wrong question. A sweep
    asserts "I read THIS line and its status is honest". If the line then gains a `>> SHIPPED`
    update, that judgement is void immediately — waiting out a 30-day timer would hide exactly the
    misclassification the surface exists to catch, and this surface is the board's only detector
    for it. So the marker carries the content it was made against, and any edit invalidates it.
    """
    import hashlib
    body = _SWEPT_TAG.sub("", title).strip()
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:4]


def _sweep_is_fresh(title: str, today: date) -> bool:
    """True when the line carries a `swept:YYYY-MM-DD[:hash]` marker that is BOTH recent and
    still about this line's current content.

    Three ways to be stale, all deliberate:
      * older than `_SWEEP_MAX_AGE` days — a re-read is due on cadence regardless;
      * the line changed since the sweep (fingerprint mismatch) — the judgement is void NOW;
      * malformed or future-dated — must never buy silence. `swept:2099-01-01` would otherwise
        mute a task for 73 years, and a typo'd date would mute it forever.
    A marker with no hash is accepted while in date (backwards compatible) but re-surfaces on the
    normal timer; new sweeps should write the hash.
    """
    m = _SWEPT.search(title)
    if not m:
        return False
    try:
        age = (today - date.fromisoformat(m.group(1))).days
    except ValueError:
        return False
    if not (0 <= age <= _SWEEP_MAX_AGE):
        return False
    stamped = m.group(2)
    if stamped and stamped.lower() != sweep_fingerprint(title):
        return False        # line edited since the sweep — judgement no longer applies
    return True

# --- SESSION GROWTH GATE (operator 2026-07-12, HARD) ------------------------------------------
# A session may NOT end with more open tasks than the PT-day began with. The open count is
# monotonic NON-INCREASING per day unless the operator signs a carryover. This is the mechanical
# backing for "no fake burndown": prose reconciles here failed for a month (99->116 across four
# burndown 'exercises') — only a gate holds. `--today` (the OPEN ritual, run every session) pins
# the day's starting count; the plain gate (pre-commit + CLOSE) then hard-fails any commit that
# would end the day above that line. Machine-local (gitignored) — re-armed at each machine's OPEN.
BASELINE = REPO / ".apollo_session_baseline.json"


def _load_baseline() -> dict | None:
    try:
        return json.loads(BASELINE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_baseline(data: dict) -> dict:
    try:
        BASELINE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass
    return data


def _pin_daily_baseline(count: int, today: date) -> dict:
    """First OPEN of the PT day pins the starting count; later same-day calls leave it (else a
    mid-session `--today` after opening tasks would silently re-baseline upward and game the gate)."""
    cur = _load_baseline()
    if cur and cur.get("pt_date") == today.isoformat():
        return cur
    data = {"pt_date": today.isoformat(), "baseline_count": count,
            "carryover_allowance": 0, "carryover_reason": None,
            "last_seen_date": (cur or {}).get("last_seen_date"),
            "last_seen_count": (cur or {}).get("last_seen_count")}
    return _write_baseline(data)


def _record_watermark(base: dict | None, count: int, today: date) -> None:
    """Remember the LAST count observed on the LAST day check_plan ran (operator 2026-07-31).

    This is what makes a skipped day carry over instead of leaving a hole: every plain run — the
    pre-commit gate and the CLOSE reconcile alike — drops a watermark, and the next PT day arms its
    ceiling from it. So running CLOSE is not incidental: **it is what sets tomorrow's ceiling.**"""
    data = dict(base or {})
    if data.get("last_seen_date") == today.isoformat() and data.get("last_seen_count") == count:
        return
    data["last_seen_date"] = today.isoformat()
    data["last_seen_count"] = count
    _write_baseline(data)


def _arm_from_watermark(base: dict | None, today: date) -> dict | None:
    """A PT day that never ran the OPEN ritual inherits the PREVIOUS day's ending count as its
    ceiling (operator 2026-07-31: "on days i skip it should just carry over the next day
    automatically"). Returns the armed baseline, or None when there is nothing to carry.

    Deliberately taken from the previous day's WATERMARK, never from today's current count: pinning
    "now" at the first commit of the day would bake any tasks already opened this session into the
    ceiling and silently ratchet it upward — the exact gaming `_pin_daily_baseline` refuses."""
    if base and base.get("pt_date") == today.isoformat():
        return base  # already armed today
    prev_date = (base or {}).get("last_seen_date")
    prev_count = (base or {}).get("last_seen_count")
    if not prev_date or prev_count is None or prev_date == today.isoformat():
        return None
    return _write_baseline({
        "pt_date": today.isoformat(), "baseline_count": prev_count,
        "carryover_allowance": 0, "carryover_reason": None,
        "armed_from": prev_date,  # provenance: carried, not pinned at OPEN
        "last_seen_date": prev_date, "last_seen_count": prev_count})


def _growth_gate_error(cur_count: int, base: dict | None, today: date) -> str | None:
    """The session-growth check as a PURE function (testable). Returns the error string when the
    PT-day's open count exceeds the pinned ceiling, else None. No baseline or a stale-date baseline
    (a prior day) → None (skip — the day hasn't been armed; `--today` arms it at OPEN)."""
    if not base or base.get("pt_date") != today.isoformat():
        return None
    ceiling = base["baseline_count"] + base.get("carryover_allowance", 0)
    if cur_count <= ceiling:
        return None
    co = (f" (+{base['carryover_allowance']} carryover: {base['carryover_reason']})"
          if base.get("carryover_allowance") else "")
    return (f"SESSION GROWTH GATE: {cur_count} open tasks now; the PT-day started at "
            f"{base['baseline_count']}{co} (ceiling {ceiling}). A session may NOT end above where "
            f"it began (operator 2026-07-12, HARD — no fake burndown). CLOSE a real task to reach "
            f'<= {ceiling}, or record NECESSARY growth: check_plan.py --carryover <N> "<reason>".')
# Buried-work tripwire (operator 2026-06-17): high-signal phrases that mean a task description is
# DESCRIBING undone critical work inline instead of TRACKING it as its own dated task. Rare +
# high-signal (only #326 tripped it at authoring) so this can be a hard gate, not just a warning.
# The #326/#327 miss: "CRITICAL-PATH BUILD ... = #311[8/1]" buried the near-term build in prose.
_BURIED_WORK = re.compile(r"critical[- ]path build|the only (real )?blocker|critical path\s*[=:]", re.I)
# High-stakes pointer gate (operator 2026-06-20, the #305 lesson): the filing-quality gate
# bans only the contentless-stub PHRASES ("confirm scope"/"at triage"), so #305 — the
# real-money launch GO — slipped as a plausible-sounding one-liner with no runbook/config.
# "Adequate detail" is semantic + can't be gated without over-flagging terse-but-fine tasks
# (a sweep flagged 34, most fine). But the highest-consequence class IS catchable cheaply:
# a launch / real-money / cutover task must POINT at where its execution lives. NARROW
# (fires only on high-stakes markers) + recognizes every legit pointer form (a doc/runbook
# file, another #task, a memory, or its SSoT/CHANGE_PROCESS) → ~zero false positives.
_HIGH_STAKES = re.compile(r"🚀|GO/NO-?GO|real[- ]money|\bcutover\b|go[- ]live", re.I)
_POINTER = re.compile(r"\.(?:md|py|sql|yaml|sh)\b|\bmemory \w|\[\[|CHANGE_PROCESS|\bSSoT\b", re.I)
# A definition-of-done / outcome signal: an arrow, a DoD/verify/outcome marker, a done-tick.
_DOD = re.compile(r"→|->|⮕|\bDoD\b|verif|definition.of.done|outcome|✅|⚠", re.I)
_ANY_TASK_REF = re.compile(r"#\d+")


def _refs_other_task(title: str, tid: int | None) -> bool:
    """True if the title cross-references a DIFFERENT #task — a pointer. A self-reference
    (the task's own #id in its own line) does NOT count, so it's stripped first."""
    other = title.replace(f"#{tid}", "") if tid is not None else title
    return bool(_ANY_TASK_REF.search(other))


def looks_thin(title: str, tid: int | None = None) -> bool:
    """Heuristic for the CLOSE-time NEW-TASK audit (operator 2026-06-20): a freshly created
    task that needs more detail before the session ends — SHORT and lacking ALL of a pointer
    (file/#task/memory/SSoT) AND a definition-of-done/outcome signal. This is deliberately a
    SURFACE-for-review, not a hard gate: "adequate detail" is semantic and a hard block
    over-flags terse-but-fine tasks (a full-backlog sweep flagged 34, most fine). Scoped to
    tasks ADDED this session, the false-positive cost is a quick eyeball, not noise."""
    rich = bool(_POINTER.search(title)) or _refs_other_task(title, tid) or bool(_DOD.search(title))
    return len(title) < 120 and not rich


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
        # Filing-quality gate (operator 2026-06-20, the 9-ghost lesson): a task must be filed
        # with actionable detail + a clear outcome, NOT a placeholder bucket. Ban the exact
        # markers that produced 9 contentless stubs ("(SiP backlog — confirm scope/title at
        # triage)"). High-signal substrings — a real task title never contains these.
        _tl = title.lower()
        if "confirm scope" in _tl or "at triage" in _tl:
            errors.append(
                f"L{n}: task #{tid} has a PLACEHOLDER title ('{title[:55]}…') — file it with "
                f"actionable detail + a clear outcome (definition-of-done), not a 'confirm scope "
                f"at triage' stub. (the 9-ghost lesson, operator 2026-06-20)")
        # High-stakes pointer gate (the #305 lesson): a launch/real-money/cutover task must
        # reference where its execution lives — a runbook/doc, a #task, a memory, or its SSoT.
        if _HIGH_STAKES.search(title):
            if not (_POINTER.search(title) or _refs_other_task(title, tid)):
                errors.append(
                    f"L{n}: task #{tid} is HIGH-STAKES (launch/real-money/cutover) but does NOT "
                    f"point at where its execution lives — add its runbook/doc file, a #task xref, "
                    f"a memory, or its SSoT/CHANGE_PROCESS. A real-money task must never be a bare "
                    f"line (the #305 lesson, operator 2026-06-20).")
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


_BUMP = re.compile(r'\[b(\d+)\]')
_BUMP_OK = re.compile(r'\[(?:ok|blocked):', re.I)


def _bump_count(title: str) -> int:
    m = _BUMP.search(title)
    return int(m.group(1)) if m else 0


_BLOCKED_BY = re.compile(r'blocked_by:?\s*#(\d+)', re.I)
_DEFER_UNTIL = re.compile(r'defer_until:\s*(\d{4}-\d{2}-\d{2})', re.I)
_BLOCKED_TAG = re.compile(r'\[blocked:', re.I)
_REVALIDATED = re.compile(r'revalidated:\s*(\d{4}-\d{2}-\d{2})', re.I)
_STALE_BLOCK_BUMPS = 5     # [blocked:] buys unlimited bumps below this
_REVALIDATE_MAX_AGE = 45   # days a re-validation stays good


def _dependency_gate(tasks, errors, today) -> None:
    """Dependency gate (operator 2026-06-28): when a blocker resolves or a time-deferral expires, the
    dependent MUST be re-dated — it can't keep sitting at a phantom ETA justified by a gate that already
    passed (the #320/#321/#335 'post-launch' drift). A task tagged `blocked_by:#N` whose #N is no longer
    open, or `defer_until:YYYY-MM-DD` whose date is past, FAILS the commit until re-dated. Use these
    PARSEABLE tags for any deferral so the dependency is mechanically tracked, not buried in prose."""
    open_ids = {t["id"] for t in tasks
                if str(t["status"]).lower() not in ("completed", "done", "closed", "deleted")}
    for t in tasks:
        if str(t["status"]).lower() in ("completed", "done", "closed", "deleted"):
            continue
        for m in _BLOCKED_BY.finditer(t["title"]):
            bid = int(m.group(1))
            if bid not in open_ids:
                errors.append(
                    f"L{t['line']}: task #{t['id']} is `blocked_by:#{bid}` but #{bid} is no longer open "
                    f"— the blocker CLEARED; un-defer + re-date #{t['id']} to a real ETA (dependency gate).")
        m = _DEFER_UNTIL.search(t["title"])
        if m:
            try:
                if date.fromisoformat(m.group(1)) < today:
                    errors.append(
                        f"L{t['line']}: task #{t['id']} `defer_until:{m.group(1)}` is PAST (today {today}) "
                        f"— the deferral EXPIRED; re-date to a real near-term ETA (dependency gate).")
            except ValueError:
                pass


_SHIPPED_CODE_DIRS = ("agents/", "core/", "channels/", "shared/", "main.py")
_OWN_COMMIT = re.compile(r"^#(\d+)[:.\s]")


def _shipped_pending_gate(tasks, errors) -> None:
    """A `pending` task whose OWN commit already shipped product code is contradictory — `pending`
    means NOT STARTED, and code named after the task exists. That contradiction is what makes a line
    read as unstarted months after it shipped, which then generates a DUPLICATE card: on 2026-07-25
    #495 (built 7/21, `786b294`) and #402 both did exactly that in one day, and the existing
    LIKELY-BUILT surface is ADVISORY so it got triaged as housekeeping and ignored.

    Deliberately NARROW so it can be a GATE rather than more wallpaper. Measured 2026-07-25 on the
    live board: matching ANY `#N` mention in a commit touching code flags 31 of 84 tasks (subjects
    cross-reference IDs constantly — unusable). Requiring the subject to START with `#N` — this
    repo's convention for "this commit IS that task's work" — and to touch product code flags **4 of
    55 pending**. Four is actionable; thirty-one is noise, and noise is how the advisory surface died.

    Fix by correcting the STATUS (a task with shipped code is at minimum `in_progress`, usually
    `deployed` + a verify-date), never by deleting the tag. `in_progress` is exempt: a multi-part
    task legitimately ships part 1 while remaining open."""
    import subprocess
    pending = {t["id"]: t for t in tasks if str(t["status"]).lower() == "pending"}
    if not pending:
        return
    try:
        log = subprocess.run(["git", "log", "--all", "--format=%h%x00%s"], cwd=str(REPO),
                             capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=10)
        if log.returncode != 0:
            return
    except Exception:
        return  # git unavailable — never block a commit on infra
    first: dict[int, tuple[str, str]] = {}
    for line in log.stdout.splitlines():
        sha, _, subj = line.partition("\x00")
        m = _OWN_COMMIT.match(subj)
        if not m:
            continue
        tid = int(m.group(1))
        if tid in pending and tid not in first:
            first[tid] = (sha, subj)
    for tid, (sha, subj) in sorted(first.items()):
        try:
            files = subprocess.run(["git", "show", "--name-only", "--format=", "-r", sha],
                                   cwd=str(REPO), capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=10).stdout
        except Exception:
            continue
        if not any(f.startswith(_SHIPPED_CODE_DIRS) for f in files.splitlines() if f.strip()):
            continue
        t = pending[tid]
        errors.append(
            f"L{t['line']}: task #{tid} is `pending` but its OWN commit {sha} already shipped product "
            f"code (\"{subj[:60]}\") — `pending` means NOT STARTED, so the line is stale and will "
            f"generate a duplicate card (the #495/#402 class, 2026-07-25). Correct the STATUS: "
            f"`in_progress` if work remains, `deployed` + a verify-date if it shipped.")


def _stale_block_gate(tasks, errors, today) -> None:
    """Close the [blocked:] free-pass on the rebump cap (operator 2026-07-26:
    "I don't want this work to be blocked for no reason going forward").

    `_rebump_gate` forbids a 2nd+ rebump WITHOUT `[ok:]` or `[blocked:]` — but a
    `[blocked:]` tag then buys UNLIMITED bumps. Measured on the live board that day:
    15 open tasks carried a block tag and TEN sat at [b4]+, each bump justified by
    re-writing a block reason. That is how a task stays parked for months.

    Worse, the reason itself can be WRONG: #329 sat blocked on #335's flip for a
    decision #329's OWN TEXT exempted ("advisory/shadow composite is UN-GATED →
    build it NOW") — the foundation gated on the roof, idle for weeks. Nothing
    re-checked it because a written block reason is self-certifying.

    So past `_STALE_BLOCK_BUMPS` rebumps, a block must be RE-VALIDATED with a dated
    `revalidated:YYYY-MM-DD` marker, fresh within `_REVALIDATE_MAX_AGE` days. The
    date is the point: it forces the block to be RE-STATED against today's reality
    rather than inherited from a phase that has since passed.

    Threshold chosen from measurement, not taste: [b5]+ flags 3 tasks (actionable);
    [b4]+ would flag 10 (which becomes wallpaper, the failure mode that let the
    LIKELY-BUILT surface be ignored)."""
    for t in tasks:
        if str(t["status"]).lower() in ("completed", "done", "closed", "deleted"):
            continue
        title = t["title"]
        if not _BLOCKED_TAG.search(title):
            continue
        if _bump_count(title) < _STALE_BLOCK_BUMPS:
            continue
        m = _REVALIDATED.search(title)
        fresh = False
        if m:
            try:
                fresh = (today - date.fromisoformat(m.group(1))).days <= _REVALIDATE_MAX_AGE
            except ValueError:
                fresh = False
        if not fresh:
            errors.append(
                f"L{t['line']}: task #{t['id']} is [b{_bump_count(title)}] AND carries a [blocked:] tag "
                f"with no fresh `revalidated:YYYY-MM-DD` (within {_REVALIDATE_MAX_AGE}d). A block tag "
                f"buys UNLIMITED rebumps, so a stale/wrong block parks a task indefinitely (#329 sat "
                f"blocked on a decision its own text exempted). RE-STATE the block against today: is the "
                f"blocker still real, and what CONCRETE condition clears it? Then tag "
                f"`revalidated:{today}` — or un-block it.")


def _rebump_gate(tasks, errors) -> None:
    """Rebump cap — HARD RULE (operator 2026-06-28): a task ETA may be rebumped AT MOST ONCE; a
    2nd+ bump needs [ok:reason] (operator approval) or [blocked:reason] (physically impossible). The
    default on a due task is UNBLOCK + SHIP, not bump. Each rebump tags [bN]; this gate forces the
    tag to increment on any forward ETA-move vs HEAD, and blocks [b2]+ without an approval marker.
    (The theme shadow lane sat 2026-06-02 -> void on silent re-bumps — never again.)"""
    import subprocess
    try:
        head = subprocess.run(["git", "show", "HEAD:PLAN.md"], cwd=str(REPO),
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=5)
        if head.returncode != 0:
            return  # no committed PLAN yet — nothing to diff against
        prior, _ = parse(head.stdout)
    except Exception:
        return  # git unavailable — don't block a commit on infra
    prior_eta = {t["id"]: t["eta"] for t in prior}
    prior_bump = {t["id"]: _bump_count(t["title"]) for t in prior}
    for t in tasks:
        if str(t["status"]).lower() in ("completed", "done", "closed", "deleted"):
            continue
        # A `deployed` task's ETA is a VERIFY-DATE, not a to-do date — setting or moving it (e.g. on
        # the in_progress->deployed ship, or slipping the verify window) is NOT a rebump; the past-ETA
        # gate already gives the verify-date its teeth (a passed verify-date hard-fails). So exempt
        # `deployed` from the rebump forward-ETA check. (#deployed status, operator 2026-07-18.)
        if t["status"] == "deployed":
            continue
        tid, title = t["id"], t["title"]
        cur = _bump_count(title)
        pe, pb = prior_eta.get(tid), prior_bump.get(tid, 0)
        if pe and t["eta"] and t["eta"] > pe and cur <= pb:
            errors.append(
                f"L{t['line']}: task #{tid} ETA moved forward ({pe} -> {t['eta']}) = a REBUMP, but the "
                f"[b] tag did not increment — tag it [b{pb+1}]. The rebump cap is mechanical now "
                f"(operator 2026-06-28: no more bumping into the void).")
        if cur >= 2 and not _BUMP_OK.search(title):
            errors.append(
                f"L{t['line']}: task #{tid} is at [b{cur}] (rebumped {cur}x) — a 2nd+ rebump is FORBIDDEN "
                f"without [ok:<reason>] (your approval) or [blocked:<physically impossible>]. The directive "
                f"is UNBLOCK + SHIP, not bump (operator 2026-06-28).")


def main(argv: list[str]) -> int:
    if not PLAN.exists():
        print(f"[plan] ERROR: {PLAN} not found — it is the single source of truth.")
        return 2
    tasks, errors = parse(PLAN.read_text(encoding="utf-8"))
    today = datetime.now(_OPERATOR_TZ).date()   # the operator's PT day, not ET (see _OPERATOR_TZ note)

    if "--today" in argv:
        # `deployed` tasks live in their OWN surface (VERIFY-DUE) — excluded from the generic
        # OVERDUE/DUE lists so "verify + close" is never conflated with "rebump-overdue".
        overdue = sorted([t for t in tasks if t["eta"] and t["eta"] < today
                          and t["status"] != "deployed"], key=lambda t: t["eta"])
        due = sorted([t for t in tasks if t["eta"] == today and t["status"] != "deployed"],
                     key=lambda t: t["project"] or "")
        print(f"=== PLAN — {today} (PT, operator's day) ===  ({len(tasks)} open tasks total)")
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
        # VERIFY-DUE (operator 2026-07-18): deployed tasks whose verify window has arrived. Seen
        # every OPEN — the recurrence that replaces the forgotten "verify-live" prose step.
        verify_due = sorted([t for t in tasks if t["status"] == "deployed"
                             and t["eta"] and t["eta"] <= today], key=lambda t: t["eta"])
        print(f"\n-- VERIFY-DUE ({len(verify_due)}) — SHIPPED; verify window here -> confirm in prod + close --")
        for t in verify_due or []:
            print(f"  #{t['id']:<4} verify {t['eta']}  {t['project']} — {t['title']}")
        if not verify_due:
            print("  (none)")
        # LIKELY-BUILT (operator 2026-07-18): status says to-build, line says built. Reclassify.
        # Lines carrying a fresh `swept:YYYY-MM-DD` are suppressed — see _sweep_is_fresh.
        _lb_all = [t for t in tasks if t["status"] in ("in_progress", "pending")
                   and _DEPLOY_MARKER.search(t["title"])]
        likely_built = [t for t in _lb_all if not _sweep_is_fresh(t["title"], today)]
        _suppressed = len(_lb_all) - len(likely_built)
        print(f"\n-- LIKELY-BUILT ({len(likely_built)}) — line reads as built but status is still "
              f"in_progress/pending: flip to `deployed` (+ a verify-date ETA) or close --")
        if likely_built:
            ids = [f"#{t['id']}" for t in likely_built]
            for i in range(0, len(ids), 12):
                print(f"  {' '.join(ids[i:i+12])}")
            print("  (a SURFACE, not a gate — partial deploys legitimately linger; reclassify the truly built.)")
        else:
            print("  (none)")
        if _suppressed:
            # Say what was hidden and when it comes back — a suppression you cannot see is
            # indistinguishable from a surface that stopped working.
            print(f"  ({_suppressed} suppressed by a fresh `swept:` marker — re-surfaces "
                  f"{_SWEEP_MAX_AGE}d after each sweep date.)")
        base = _pin_daily_baseline(len(tasks), today)
        # OPEN drops a watermark too, so a day where the operator runs `--today`
        # and never commits still arms TOMORROW's carry-over. Previously only the
        # plain run recorded it, so an open-but-no-commit day left no mark at all.
        _record_watermark(base, len(tasks), today)
        ceiling = base["baseline_count"] + base.get("carryover_allowance", 0)
        print(f"\n-- GROWTH GATE — day started at {base['baseline_count']} open tasks. This session must "
              f"END <= {ceiling} (HARD, operator 2026-07-12: no session ends bigger than it began).")
        print("   Take a HARD LOOK for real closes; open a new task only if you close a real one first.")
        return 0

    if "--carryover" in argv:
        # OPERATOR-SIGNED escape for NECESSARY growth: raise TODAY's ceiling by N with a reason.
        # Deliberate + visible (not a silent default) — mirrors the [ok:]/[blocked:] rebump escape.
        idx = argv.index("--carryover")
        try:
            n = int(argv[idx + 1])
        except (IndexError, ValueError):
            print('usage: check_plan.py --carryover <N> "<reason>"')
            return 2
        reason = argv[idx + 2].strip() if idx + 2 < len(argv) else ""
        if not reason:
            print("[carryover] a reason is REQUIRED (this is an operator sign-off).")
            return 2
        base = _pin_daily_baseline(len(tasks), today)
        base["carryover_allowance"] = base.get("carryover_allowance", 0) + n
        base["carryover_reason"] = reason
        _write_baseline(base)
        print(f"[carryover] today's growth ceiling raised by {n} -> "
              f"{base['baseline_count'] + base['carryover_allowance']} (reason: {reason}).")
        return 0

    if "--audit-new" in argv:
        # CLOSE-ritual NEW-TASK audit (operator 2026-06-20): flag tasks ADDED this session
        # that look thin, so DETAIL gets added before the session ends. "Adequate detail"
        # can't be a hard commit-gate (semantic — over-flags terse-but-fine tasks), so it is
        # a scoped CLOSE review of only the new lines. Default base = origin/main (correct
        # when the session batches its commit at CLOSE); pass an explicit ref if you pushed
        # PLAN.md mid-session: `--audit-new <session-start-ref>`.
        import subprocess
        idx = argv.index("--audit-new")
        base = argv[idx + 1] if idx + 1 < len(argv) and not argv[idx + 1].startswith("-") else "origin/main"
        try:
            diff = subprocess.run(
                ["git", "diff", base, "--", "PLAN.md"], cwd=str(REPO),
                capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        except Exception as e:
            print(f"[audit-new] could not `git diff {base} -- PLAN.md`: {e}")
            return 0
        added = [ln[1:].strip() for ln in diff.splitlines()
                 if ln.startswith("+") and not ln.startswith("+++") and ln[1:].lstrip().startswith("- #")]
        new = [{"id": int(m.group(1)), "title": m.group(4)}
               for m in (_TASK.match(ln) for ln in added) if m]
        thin = [t for t in new if looks_thin(t["title"], t["id"])]
        print(f"=== NEW-TASK AUDIT — {len(new)} task(s) added vs {base} ===")
        if not new:
            print("  (no new tasks this session)")
        elif not thin:
            print(f"  OK: all {len(new)} new task(s) carry detail (pointer / DoD / length).")
        else:
            print(f"  WARN: {len(thin)} new task(s) look THIN — add detail + a clear outcome before CLOSE:")
            for t in thin:
                print(f"      #{t['id']}  {t['title'][:90]}")
            print("  (project+ETA+status are already gated; this checks DETAIL on new tasks.)")
        return 0

    # validation gate — `deployed` is NOT exempt (a stale verify-date rots the same way a stale ETA
    # does); it just gets the verify-worded instruction instead of the generic rebump wording.
    past = [t for t in tasks if t["eta"] and t["eta"] < today]
    for t in past:
        if t["status"] == "deployed":
            errors.append(f"L{t['line']}: task #{t['id']} is `deployed` and its VERIFY-DATE {t['eta']} "
                          f"is PAST (today {today}) — VERIFY-LIVE in prod + close the task (or rebump "
                          f"the verify-date). Done = VERIFIED-LIVE, not deployed (operator 2026-07-18).")
        else:
            errors.append(f"L{t['line']}: task #{t['id']} ETA {t['eta']} is PAST (today {today}) — "
                          f"rebump to a future date at CLOSE, or close the task")
    _rebump_gate(tasks, errors)   # HARD RULE: max 1 rebump, then [ok:]/[blocked:] or it FAILS (operator 6/28)
    _shipped_pending_gate(tasks, errors)   # `pending` + own code commit = stale line -> duplicate card (operator 7/25)
    _stale_block_gate(tasks, errors, today)   # [blocked:] is not an unlimited rebump pass (operator 7/26)
    _dependency_gate(tasks, errors, today)   # blocker-cleared / defer_until-expired → re-date (operator 6/28)

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
    # SESSION GROWTH GATE (operator 2026-07-12, HARD): the day's open count may not END above where
    # it began. Hard-fails the commit when over ceiling; an operator carryover is the only escape.
    base = _load_baseline()
    # A skipped OPEN no longer leaves a hole: carry the previous day's ending count forward.
    base = _arm_from_watermark(base, today) or base
    gate_err = _growth_gate_error(len(tasks), base, today)
    if base and base.get("armed_from"):
        print(f"[plan] NOTE: growth gate CARRIED OVER from {base['armed_from']} "
              f"(ceiling {base['baseline_count']}) — the OPEN ritual wasn't run today, so the day "
              f"inherits where the last one ended.")
    if gate_err:
        errors.append(gate_err)
    elif not base:
        print("[plan] NOTE: no session baseline today — run `check_plan.py --today` at OPEN to arm the growth gate.")
    elif base.get("pt_date") != today.isoformat():
        # A baseline from a PRIOR day is the QUIET failure: the file EXISTS, so the
        # `not base` note above never fires, and _growth_gate_error skips — the
        # burndown ceiling is off and nothing says so. That happens exactly on a day
        # the OPEN ritual wasn't run, which is the day you'd most want to be told
        # (operator 2026-07-31: the ritual is triggered by hand with "start the day",
        # not by a SessionStart hook — CLAUDE.md claimed a hook that never existed).
        print(f"[plan] WARN — growth gate is NOT ARMED today: the baseline on disk is from "
              f"{base.get('pt_date')}, not {today.isoformat()}. The burndown ceiling is NOT being "
              f"enforced this session. Run `check_plan.py --today` (the OPEN ritual) to arm it.")

    # Drop the watermark on EVERY plain run (pre-commit + the CLOSE reconcile), pass or fail —
    # a failing run still observed a real count, and tomorrow's ceiling should reflect it.
    _record_watermark(base, len(tasks), today)

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
