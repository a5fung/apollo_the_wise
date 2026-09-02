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
  - a task whose OWN TEXT asserts a pending verification (VERIFY-LIVE/VERIFY-DUE/"NOT done until"/etc)
    must be `deployed` — else the claim has nowhere to surface from (operator 2026-08-09, the #167
    lesson: the claim was written, the status never flipped). Pre-existing violations WARN (surfaced
    every `--today`); a violation on a line ADDED or MODIFIED this commit HARD-FAILS;
  - the INVERSE: a task AT `deployed` must itself state a verify condition somewhere in its text
    (same trigger vocabulary as above; a satisfied/checkmarked historical claim still counts as
    "stated" — it named an observable and it already fired) — else it ships claiming NOTHING and can
    sit `deployed` forever, or get closed on "it deployed fine" with nothing ever checked (operator
    2026-08-09, same day, closing the gap class both directions). Same WARN/HARD-FAIL split;
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
import subprocess
import sys
from datetime import date, datetime
from datetime import time as dtime
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

# --- SHIPPED-BUT-UNRECORDED (2026-08-30) -------------------------------------------------------
# The gap every other surface here misses, and it has cost us ~30 redone tasks.
#
# LIKELY-BUILT asks "does this line's own TEXT read as built". PENDING-VERIFY asks "does its text
# claim a verify while the status disagrees". Both read only the line. **So a task whose text says
# NOTHING SHIPPED stays invisible forever, even when the thing shipped weeks ago in a commit that
# named the task by number.**
#
# The case that forced this, and the operator's words: "this is what our close process should
# catch and we've run into this many times and you promised its gap is closed... This is like the
# 30th task we had to do this."
#   #516's line read `⚖ NOTHING SHIPPED — criterion change = CHANGE_PROCESS + sign-off` and
#   `AWAITING HIS RULING`. He ruled on 08-08 and commit 841ab270 shipped it on 08-11 with the
#   subject "#516: a keyword match may no longer overrule a contrary classification —
#   OPERATOR-SIGNED". The line was never updated, so on 2026-08-30 a card was commissioned to
#   build what already existed. Nothing in the board could have known: the board only ever knew
#   what its own text said.
#
# THE CHECK: a task claiming it has NOT shipped, whose #ID appears in a commit that touched real
# code. Both halves are needed — a task legitimately accumulates commits while in progress, so
# the CLAIM is what makes a commit contradictory rather than expected.
#
# Deliberately narrow: only the strong claim phrases, only commits touching code paths (not docs
# or PLAN.md itself), and it is a SURFACE, not a gate — a genuinely-multi-part task can ship one
# piece while the rest is honestly unshipped, and blocking on that would train people to reword
# the claim instead of updating the line.
_NOT_SHIPPED_CLAIM = re.compile(
    r"NOTHING SHIPPED|NOT SHIPPED|awaiting (his|the operator|operator)|AWAITING HIS RULING"
    r"|pending (his |the )?sign-?off|needs operator sign-?off|DO NOT ship|not yet (built|shipped)",
    re.I)

# `[shipped-ack:YYYY-MM-DD[:hash]...]` — the line already records what shipped under this
# number. Dated + content-fingerprinted via `_marker_is_fresh` (2026-08-30 fix — see that
# function and `_shipped_ack_is_fresh` below): the presence-only form this replaced could mute
# SHIPPED-BUT-UNRECORDED forever, including for genuinely new, honestly-unshipped scope added
# under the same task number later — exactly the failure this surface exists to catch.
_SHIPPED_ACK = re.compile(r"shipped-ack:\s*(\d{4}-\d{2}-\d{2})(?::([0-9a-f]{4}))?", re.I)
_SHIPPED_ACK_TAG = re.compile(r"\s*\[shipped-ack:[^\]]*\]", re.I)
_SHIPPED_ACK_MAX_AGE = 30   # days a shipped-ack acknowledgement stays good, mirrors `swept:`


def shipped_ack_fingerprint(title: str) -> str:
    """4-hex-char digest of the line WITHOUT its shipped-ack tag — mirrors `sweep_fingerprint`
    exactly, same reasoning: a `[shipped-ack:]` asserts "this line's CURRENT unshipped claim is
    honest", and any edit to the line — e.g. genuinely new, honestly-unshipped scope filed under
    the same task number — must void that judgement immediately, not whenever the timer expires.
    """
    import hashlib
    body = _SHIPPED_ACK_TAG.sub("", title).strip()
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:4]


def stale_blockers(tasks: list[dict]) -> list[tuple[dict, list[str]]]:
    """Tasks marked `blocked` on a task that is NO LONGER on the board.

    THE BLIND SPOT THIS CLOSES. `shipped_but_unrecorded` looks for a task CLAIMING it has not
    shipped. A task that says `blocked:#329` claims nothing of the kind — it defers to another
    line entirely — so a blocker that closes leaves the dependent frozen with nobody watching.

    Found 2026-08-30 by the operator, not by me, on #331: blocked on #329 and #330 since June.
    Both had shipped, both were off the board, and both shadows were live and writing (588 and
    122 rows, last write 08-28). The block had been fiction for weeks and the task's own text
    even said to CLOSE it if #330's shadow was still unbuilt — it was built, so the instruction
    pointed the wrong way too.

    Decidable with certainty: either the referenced id is on the board or it is not. No claim
    phrase to guess at, unlike the sibling surface.
    """
    live = {str(t["id"]) for t in tasks}
    out: list[tuple[dict, list[str]]] = []
    for t in tasks:
        if t["status"] != "blocked":
            continue
        # ONLY THE LAST `[blocked:...]` TAG IS THE CURRENT CLAIM. A long-lived task carries
        # its whole block history inline, and reading every tag makes a SUPERSEDED reference
        # fire forever: #353 was re-pointed off the closed #327 on 2026-09-01 and kept
        # flagging, because a tag from August still named #327 as history. That trains you to
        # ignore the surface, which is worse than not having it. Same principle the drift
        # checker uses — the most recent statement about a subject is the current claim.
        # Two blockers named in ONE tag still both count; it is the OLD tags that are history.
        tags = re.findall(r"blocked:([^\]]*)", t["title"])
        if not tags:
            continue
        refs = set(re.findall(r"#(\d+)", tags[-1]))
        gone = sorted(r for r in refs if r not in live)
        if gone:
            out.append((t, gone))
    return out


def shipped_but_unrecorded(tasks: list[dict], today: date, repo: Path = REPO) -> list[tuple[dict, str]]:
    """Tasks claiming they have not shipped, whose #ID appears in a code commit.

    Returns (task, commit-subject) so the surface can say WHICH commit contradicts the line —
    a bare task id would just move the search rather than end it.

    The "does a commit naming this task touch code" check itself is `_own_commits_touching_code`
    — the SAME helper `_shipped_pending_gate` uses, so the two can no longer drift on path tuple
    or anchoring the way `_CODE_PATHS`/`_OWN_COMMIT` did (2026-08-30 fix; see that helper's
    docstring for the drift this closed).
    """
    candidates = []
    for t in tasks:
        if t["status"] not in ("in_progress", "pending", "blocked"):
            continue
        if not _NOT_SHIPPED_CLAIM.search(t["title"]):
            continue
        # An explicit, DATED + content-fingerprinted acknowledgement suppresses the surface: the
        # line ALREADY records what shipped under this number, and the remaining claim is
        # honest. #299 on 2026-08-30 is the case — its eval rig shipped and the line says so;
        # what is unshipped is the paid full run, which is blocked on funding, an operator
        # decision. Without this the surface would nag forever on a task that is telling the
        # truth, and a surface that cries wolf gets ignored — which is how the original 30 tasks
        # were missed. Fresh (not aged out, not edited since) via `_shipped_ack_is_fresh` — a
        # presence-only ack could otherwise mute this forever, including for genuinely new,
        # honestly-unshipped scope added under the same number later (the bug this fixed).
        if _shipped_ack_is_fresh(t["title"], today):
            continue
        candidates.append(t)
    hits = _own_commits_touching_code({t["id"] for t in candidates}, repo=repo)
    out: list[tuple[dict, str]] = []
    for t in candidates:
        hit = hits.get(t["id"])
        if hit:
            sha, subj = hit
            out.append((t, f"{sha} {subj}"))
    return out


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


def _marker_age_days(pattern, title: str, today: date) -> int | None:
    """Age in days of a dated `<name>:YYYY-MM-DD` marker, or None when it cannot be trusted.

    Shared by BOTH dated markers in this file — `swept:` (the LIKELY-BUILT surface) and
    `revalidated:` (the stale-block gate). They were written independently and had already
    drifted: the newer one rejected future dates, the older one did not, so a
    `revalidated:2099-01-01` computed a NEGATIVE age, satisfied `<= 45`, and read as fresh —
    buying indefinite silence on the one gate here that actually blocks commits. Nothing had
    exploited it (checked: zero future-dated markers on the board), but two copies of
    "parse a date, subtract, compare" is how that divergence happened, so there is now one.

    None means "do not trust this marker" and every caller must treat it as NOT fresh:
      * absent, malformed, or an impossible date (`2026-13-45`) — a typo must never buy silence;
      * dated in the FUTURE — the cheapest way to mute a task forever.
    """
    m = pattern.search(title)
    if not m:
        return None
    try:
        age = (today - date.fromisoformat(m.group(1))).days
    except ValueError:
        return None
    return age if age >= 0 else None


def _marker_is_fresh(pattern, title: str, today: date, max_age: int, fingerprint) -> bool:
    """True when `title` carries a `<name>:YYYY-MM-DD[:hash]` marker (matched by `pattern`,
    whose group(1) is the date and group(2) the optional hex fingerprint — the same contract
    `_marker_age_days` already assumes for group(1)) that is BOTH recent (age <= `max_age`) and,
    when it carries a `:hash` suffix, still about `title`'s CURRENT content (the hash must equal
    `fingerprint(title)`).

    THE SHARED FRESHNESS PRIMITIVE (2026-08-30). `swept:` and `revalidated:` already share
    `_marker_age_days` after THEY drifted once — one rejected future dates, the other didn't
    (see that function's docstring). This generalises the other half of the same shape (age
    bound + content-fingerprint bound, together) so a third marker never has to hand-roll its
    own copy of "is this judgement still good": that is exactly how `[shipped-ack:]` shipped
    presence-only (no date, no fingerprint, no expiry) and could mute SHIPPED-BUT-UNRECORDED
    forever — including for genuinely new, honestly-unshipped scope filed under the same task
    number later, the precise failure this surface exists to catch. `swept:` (via
    `_sweep_is_fresh`) and `shipped-ack:` (via `_shipped_ack_is_fresh`) both route through this
    now — one function owns "dated + content-fingerprinted marker is still good," not two, and
    a fourth marker gets it for free.

    A marker with no `:hash` suffix is accepted purely on the timer (backwards compatible with
    date-only markers) — content protection is opt-in per marker instance, not per marker kind.
    """
    age = _marker_age_days(pattern, title, today)
    if age is None or age > max_age:
        return False
    m = pattern.search(title)
    stamped = m.group(2)
    if stamped and stamped.lower() != fingerprint(title):
        return False        # line edited since the marker was written — judgement no longer applies
    return True


def _sweep_is_fresh(title: str, today: date) -> bool:
    """True when the line carries a `swept:YYYY-MM-DD[:hash]` marker that is BOTH recent and
    still about this line's current content — see `_marker_is_fresh` for the full contract
    (age bound, content-fingerprint bound, malformed/future-dated rejection).

    Three ways to be stale, all deliberate:
      * older than `_SWEEP_MAX_AGE` days — a re-read is due on cadence regardless;
      * the line changed since the sweep (fingerprint mismatch) — the judgement is void NOW;
      * malformed or future-dated — must never buy silence. `swept:2099-01-01` would otherwise
        mute a task for 73 years, and a typo'd date would mute it forever.
    A marker with no hash is accepted while in date (backwards compatible) but re-surfaces on the
    normal timer; new sweeps should write the hash.
    """
    return _marker_is_fresh(_SWEPT, title, today, _SWEEP_MAX_AGE, sweep_fingerprint)


def _shipped_ack_is_fresh(title: str, today: date) -> bool:
    """True when the line carries a `[shipped-ack:YYYY-MM-DD[:hash]]` marker that is BOTH recent
    and still about this line's CURRENT content.

    Replaces the presence-only `[shipped-ack:<why>]` (2026-08-30 fix, the day it shipped): that
    form had no date, no content fingerprint and no expiry, so it suppressed SHIPPED-BUT-
    UNRECORDED for a task number FOREVER — including once genuinely new, honestly-unshipped
    scope was filed under the same number, exactly the drift this surface exists to catch.
    Routes through `_marker_is_fresh`, the same primitive `swept:` uses, so this can't recreate
    that gap a third time by drifting its own copy of "is this ack still good."
    """
    return _marker_is_fresh(_SHIPPED_ACK, title, today, _SHIPPED_ACK_MAX_AGE, shipped_ack_fingerprint)

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


# --- PENDING-VERIFY CLAIM GATE (operator 2026-08-09) --------------------------------------------
# WHY: operator caught task #167's OWN TEXT reading "VERIFY-LIVE — the flip is NOT done until this
# is confirmed" while its status sat at `in_progress` — nothing in the mechanical surfaces
# (VERIFY-DUE / LIKELY-BUILT) would ever have surfaced it, because those key off STATUS, and the
# status was never flipped to `deployed` in the first place. The claim was written in the
# mechanism's own vocabulary and then the mechanism itself was skipped — "I'll verify it" is prose,
# and prose drifts (caught twice, same shape). This gate makes the CLAIM and the STATUS the same
# fact: if a task's own text asserts a verification is still open, its status must already be
# `deployed` (the SoT rule, CLAUDE.md Session Protocol) — otherwise the claim has nowhere to
# mechanically surface from.
#
# TRIGGER VOCABULARY (tuned against the live 84-line board, not guessed): this codebase's own idiom
# for a live-verify checkpoint — VERIFY-LIVE / VERIFY-DUE (either case) / "NOT done until" / "must
# be confirmed" / "confirm in prod". Deliberately NARROW: generic English "verify" is common
# load-bearing prose here ("Opus-verified", "ETF% unverified", "verified in git", "Fable-reviewed")
# and would be pure noise if matched — measured zero of those trip this gate on the real board.
# This is `_VERIFY_CLAIM_TRIGGER_STRICT` below. THIS gate (pending-verify, HARD-FAIL) uses STRICT
# and ONLY STRICT — a false fire here blocks a commit, so precision is non-negotiable and this
# vocabulary is never widened for this direction. The sibling inverse gate further down
# (`_deployed_no_verify_gate`, WARN-only) uses a WIDER `_VERIFY_CLAIM_TRIGGER_BROAD` — see that
# gate's section comment for why a warn-only gate wants recall instead, and why the two vocabularies
# must stay two objects, not one, even though BROAD is built by extending STRICT's own pattern.
#
# PENDING vs HISTORICAL (the core difficulty): the SAME phrase ("VERIFY-LIVE") is used for both an
# OPEN claim ("VERIFY-LIVE = tomorrow's job writes the first row") and a CLOSED checkpoint ("✅
# VERIFY-LIVE DONE 6/18: ..."), and a single task can carry both at once (#452, #471 do — a done
# sub-checkpoint plus a still-open one). Two suppressions, both measured against the real board:
#   1. `[ok:...]` / `[blocked:...]` / `[swept:...]` / `[revalidated:...]` tags are META-COMMENTARY
#      about a PAST rebump/sweep decision, not a live claim about the task's current state — #261's
#      ONLY match lives entirely inside one such tag (boilerplate rebump-reason text reused
#      verbatim across #261/#414/#452/#479). Stripped before matching, mirroring `_SWEPT_TAG`'s
#      bracket-strip-before-hash precedent.
#   2. A match immediately preceded (within `_VERIFY_CLAIM_HIST_WINDOW` chars, with no intervening
#      "▶" pending-arrow) by a "✅" checkmark is this codebase's own convention for "already
#      confirmed" — #327 carries THREE "✅ VERIFY-LIVE DONE" checkpoints and zero open ones; none
#      of them should fire. The intervening-▶ guard exists so "✅ built; ▶ VERIFY-LIVE" (a done note
#      immediately followed by a NEW open one) cannot be false-suppressed by the earlier checkmark.
# A task fires if AT LEAST ONE match survives both filters — it is not exempt just because it ALSO,
# elsewhere on the same line, once verified something else (#452, #471).
#
# Measured 2026-08-09 against the live board: 19 lines carry the raw vocabulary; after both
# suppressions, 5 are real open violations (#548 #184 #354 #471 #452) and #261/#327 are correctly
# suppressed (see above) — 0 false positives against the operator's own manual read of all 84 lines.
#
# HARD-FAIL vs WARN: hard-failing the commit on all 5 pre-existing violations today would repeat
# this repo's own documented failure mode — a gate that fails the very first commit gets bypassed
# with `--no-verify` (three broad guards were built and binned in one week for exactly this). So:
# a violation UNCHANGED since `HEAD:PLAN.md` (pre-existing) WARNS only, surfaced every `--today` so
# it cannot go quiet between sessions; a violation on a line ADDED or MODIFIED this commit
# HARD-FAILS — the #167 shape (write new VERIFY-LIVE prose without flipping status) can never land
# again. Mirrors `_rebump_gate`'s git idiom (`HEAD:PLAN.md`, fail-open on any git error — never
# block a commit on a git/infra hiccup; when git is unavailable every violation degrades to WARN,
# never escalates to HARD, matching how the other git-touching gates fail open by skipping outright).
_VERIFY_CLAIM_TRIGGER_STRICT = re.compile(
    r"verify-live|verify-due|not done until|must be confirmed|confirm in prod", re.I)

# BROAD is a strict SUPERSET of STRICT — built by extending STRICT's own pattern string, not a
# hand-maintained parallel list, so "BROAD matches everything STRICT matches" is true by
# construction and cannot rot out of sync as either side is edited later (`test_check_plan_verify_
# broad_vocabulary.py` also pins this structurally). Only `_deployed_no_verify_gate` (WARN-only,
# recall wants to win) uses BROAD; `_pending_verify_gate` (HARD-FAIL, precision wants to win) always
# uses STRICT — see the section comments on both gates for the full rationale.
#
# Additions measured 2026-08-09 against the 4 real `deployed` tasks STRICT was missing on the live
# board (#544 #525 #513 #539 — see `_deployed_no_verify_gate`'s section comment for the full read):
#   - bare "VERIFY <day-name>" / "VERIFY <YYYY-MM-DD>", no "-live"/"-due" suffix
#     -> #544 "▶ **VERIFY MONDAY:** theme engine 17:00 ET run ...", #539 "▶ VERIFY 2026-08-08 (Sat
#     morning, on tonight's 17:00 ET run): ..."
#   - past-tense "VERIFIED IN PROD" -> #525 "**VERIFIED IN PROD RIGHT AFTER DEPLOY:** `breaker[live]=0`..."
#   - past-tense "VERIFIED <date>" (ISO or M/D) is ticket-named, not itself the phrase that fires any
#     of the 4 -> included because the M/D shape IS real board idiom elsewhere (#356 "VERIFIED
#     8/04", #471 "VERIFIED 7/16", #306 "VERIFIED 7/9"), just on tasks that already clear STRICT some
#     other way on the same line, so adding it does not change today's violation count. Stated here so
#     it reads as "grounded in real board text" rather than "imagined to satisfy the ticket."
#   #513 is deliberately NOT covered — its only "verify" mention lives entirely inside a stripped
#   `[ok:...]` meta-tag and, even unstripped, is generic lowercase prose ("so no earlier date can
#   verify it"), not a stated observable. That is this gate finding a genuine gap, not a vocabulary
#   miss — see the finding note in `_deployed_no_verify_gate`'s section comment.
_VERIFY_CLAIM_BROAD_EXTRA = (
    r"\bverify\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{4}-\d{2}-\d{2})"
    r"|\bverified\s+in\s+prod\b"
    r"|\bverified\s+(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2})"
)
_VERIFY_CLAIM_TRIGGER_BROAD = re.compile(
    _VERIFY_CLAIM_TRIGGER_STRICT.pattern + "|" + _VERIFY_CLAIM_BROAD_EXTRA, re.I)
_VERIFY_CLAIM_META_TAG = re.compile(r"\[(?:ok|blocked|swept|revalidated):[^\]]*\]", re.I)
_VERIFY_CLAIM_HIST_WINDOW = 15   # chars back to look for a "✅ done" marker before a trigger match


def _verify_claim_body(title: str) -> str:
    """`title` with META-COMMENTARY brackets ([ok:]/[blocked:]/[swept:]/[revalidated:]) stripped —
    the ONE substrate both verify-claim gates (pending-claim and its inverse, deployed-no-claim)
    match against, so "what counts as a verify claim" cannot drift into two definitions. A meta
    tag is commentary about a PAST rebump/sweep DECISION, not a live statement of the task's OWN
    verify condition (#261's only "verify-live" mention lives entirely inside an `[ok:...]`
    rebump-justification tag reused verbatim across several tasks — it is boilerplate about the
    bump, not a claim about #261 itself), so neither direction should treat it as a stated claim."""
    return _VERIFY_CLAIM_META_TAG.sub(" ", title)


def _verify_claim_raw_matches(title: str) -> list[str]:
    """ALL BROAD trigger-vocabulary hits in `title` (meta-tag-stripped), historical (✅) and open (▶)
    alike. This is the primitive the INVERSE gate needs: "does this task's text state a verify
    condition AT ALL" does not care whether that condition already fired — a satisfied,
    checkmark-marked historical claim ("✅ VERIFY-LIVE DONE 6/18: ...") still counts as "stated"
    (the task named an observable; it happened to already clear). `_pending_verify_matches` below
    is this same primitive further filtered down to the OPEN subset only — and matches against
    STRICT, not BROAD (see `_VERIFY_CLAIM_TRIGGER_BROAD`'s comment for why the two directions use
    different vocabularies on purpose)."""
    body = _verify_claim_body(title)
    return [body[m.start():min(len(body), m.end() + 50)].strip()
            for m in _VERIFY_CLAIM_TRIGGER_BROAD.finditer(body)]


def _pending_verify_matches(title: str) -> list[str]:
    """The surviving OPEN verify-claim snippets in `title` (empty = nothing pending asserted).
    See the section comment above for the two suppressions (meta-tag strip, ✅-checkmark lookback).
    Matches against STRICT (`_VERIFY_CLAIM_TRIGGER_STRICT`), never BROAD — this is the HARD-FAIL
    direction and precision is non-negotiable there; the WARN-only inverse gate is the one that
    widens (see `_VERIFY_CLAIM_TRIGGER_BROAD`'s comment)."""
    body = _verify_claim_body(title)
    hits = []
    for m in _VERIFY_CLAIM_TRIGGER_STRICT.finditer(body):
        back = body[max(0, m.start() - _VERIFY_CLAIM_HIST_WINDOW):m.start()]
        ck, pend = back.rfind("✅"), back.rfind("▶")   # ✅ done-marker, ▶ pending-marker
        if ck != -1 and ck > pend:
            continue   # nearest marker is a checkmark -> historical/closed, not a live claim
        hits.append(body[m.start():min(len(body), m.end() + 50)].strip())
    return hits


def _pending_verify_violations(tasks):
    """Pure (no IO): tasks whose CURRENT text asserts an open verify claim while status != deployed.
    Split out from `_pending_verify_gate` so the classifier is unit-testable without touching git,
    and reused by the `--today` surface so the same 5-line list appears at OPEN, not just at commit."""
    return [t for t in tasks if t["status"] != "deployed" and _pending_verify_matches(t["title"])]


def _pending_verify_gate(tasks, errors) -> None:
    """Apply the pending-verify-claim check: HARD-FAIL on lines touched this commit, WARN on
    pre-existing ones. See the section comment above for the full rationale."""
    violations = _pending_verify_violations(tasks)
    if not violations:
        return
    import subprocess
    prior_by_id: dict[int, dict] = {}
    git_ok = False
    try:
        head = subprocess.run(["git", "show", "HEAD:PLAN.md"], cwd=str(REPO),
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=5)
        if head.returncode == 0:
            prior_tasks, _ = parse(head.stdout)
            prior_by_id = {t["id"]: t for t in prior_tasks}
            git_ok = True
    except Exception:
        pass   # git unavailable — git_ok stays False; every violation below degrades to WARN
    for t in violations:
        snippet = _pending_verify_matches(t["title"])[0]
        fix = ("set status=deployed and ETA=<the date this becomes confirmable in prod> "
               "(the #167 lesson, operator 2026-08-09)")
        touched = False
        if git_ok:
            prior = prior_by_id.get(t["id"])
            touched = prior is None or prior["title"] != t["title"] or prior["status"] != t["status"]
        msg = (f"L{t['line']}: task #{t['id']} asserts a PENDING verify (\"{snippet}\") but status "
               f"is `{t['status']}`, not `deployed` — {fix}.")
        if touched:
            errors.append(msg)
        else:
            print(f"[plan] WARN — pre-existing pending-verify claim: {msg}")


# --- DEPLOYED-WITHOUT-VERIFY-CLAIM GATE (operator 2026-08-09, same day) -------------------------
# WHY: this is the INVERSE of the gate directly above, asked the same day it shipped. That gate
# catches a task whose text CLAIMS a pending verify while its status lags behind `deployed`. Within
# hours it found #471 — but the operator's next question exposed the other half of the gap: "a task
# that ships and claims NOTHING is still invisible. No claim means no warning, so it can sit at
# `deployed` forever and never be confirmed — or worse, be closed on 'it deployed fine'." A task at
# `deployed` means built-and-shipped-AWAITING-PROOF (CLAUDE.md Session Protocol); if the line names
# no observable, the task can never honestly close, which is exactly the failure the status exists
# to prevent.
#
# SHARED DEFINITION POINT, TWO VOCABULARIES ON PURPOSE (2026-08-09, same day as the finding below):
# both directions still match through the ONE `_verify_claim_body` (meta-tag strip) — "what counts
# as a verify claim" cannot drift into two definitions of THAT — but they no longer share one regex.
# The sibling gate above HARD-FAILS on a touched line, so a false fire there blocks real work:
# precision wins, and it stays on `_VERIFY_CLAIM_TRIGGER_STRICT`, untouched, forever (it is tuned and
# it caught #471). THIS gate only WARNs, so a MISS here is the expensive error — a task that already
# states its check gets nagged forever and the warning becomes wallpaper, exactly the failure mode
# that killed three earlier broad guards this codebase built and binned. So this gate uses the wider
# `_VERIFY_CLAIM_TRIGGER_BROAD` (defined right after STRICT, built by literally extending STRICT's
# pattern string so BROAD ⊇ STRICT is true by construction — a future reader cannot "helpfully"
# re-merge them back into one without visibly editing that construction). Never widen STRICT to
# match this gate's needs; never narrow BROAD to match the sibling's.
#
# THE SUBTLE PART (the ticket's own framing): a verify condition that is already SATISFIED —
# checkmark-marked historical ("✅ VERIFY-LIVE DONE 6/18: ...") — must still count as "stated". The
# task named an observable; it simply already fired, which is a legitimate close case, not a gap.
# So this gate does NOT reuse `_pending_verify_matches` (which deliberately DROPS checkmark-history
# to find only OPEN claims) — it uses `_verify_claim_raw_matches`, the shared primitive BEFORE that
# filter, so a purely-historical claim still counts as "stated" here even though it would count as
# "nothing pending" for the sibling gate. One vocabulary (BROAD, for this gate), two different
# questions asked of the shared `_verify_claim_body` substrate.
#
# UPDATE 2026-08-09, same day: measured against the live board's 16 `deployed` tasks, 4 fired under
# STRICT-only matching (#544 #525 #513 #539), all pre-existing -> WARN, not HARD-FAIL. Manual read of
# all 4 full task bodies found 3 of them DO in fact state an observable, just phrased outside
# STRICT's narrow idiom: "VERIFY MONDAY:" + a numbered checklist (#544), "VERIFIED IN PROD RIGHT
# AFTER DEPLOY: ..." (#525), "VERIFY 2026-08-08 ... Query: SELECT ..." (#539). BROAD now catches all
# three (bare "VERIFY <day-name/date>" and past-tense "VERIFIED IN PROD" — see
# `_VERIFY_CLAIM_TRIGGER_BROAD`'s own comment for the exact additions and which board line grounds
# each). **#513 still fires, and correctly so** — its only "verify" mention lives entirely inside a
# stripped `[ok:...]` meta-tag ("... so no earlier date can verify it."), not a stated observable;
# its real check is an event-gated ETA tied to the monthly sweep cadence, not text this gate can see.
# That is the gate finding a genuine gap, not a vocabulary miss, and BROAD was deliberately NOT
# stretched to swallow it (see `_VERIFY_CLAIM_TRIGGER_BROAD`'s comment). WARN-only means nothing is
# blocked by it meanwhile.
def _deployed_no_verify_violations(tasks):
    """Pure (no IO): `deployed` tasks whose text states NO verify condition at all — checkmark-
    satisfied historical claims still count (see section comment; uses `_verify_claim_raw_matches`,
    NOT the OPEN-only `_pending_verify_matches`). Mirrors `_pending_verify_violations`'s shape."""
    return [t for t in tasks if t["status"] == "deployed" and not _verify_claim_raw_matches(t["title"])]


def _deployed_no_verify_gate(tasks, errors) -> None:
    """Apply the deployed-no-verify-claim check: HARD-FAIL on lines touched this commit, WARN on
    pre-existing ones. Same git idiom as `_pending_verify_gate` (HEAD:PLAN.md diff, fail-open on
    any git error — never block a commit on a git/infra hiccup)."""
    violations = _deployed_no_verify_violations(tasks)
    if not violations:
        return
    import subprocess
    prior_by_id: dict[int, dict] = {}
    git_ok = False
    try:
        head = subprocess.run(["git", "show", "HEAD:PLAN.md"], cwd=str(REPO),
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=5)
        if head.returncode == 0:
            prior_tasks, _ = parse(head.stdout)
            prior_by_id = {t["id"]: t for t in prior_tasks}
            git_ok = True
    except Exception:
        pass   # git unavailable — git_ok stays False; every violation below degrades to WARN
    for t in violations:
        fix = ("state a concrete observable in the task text (e.g. `VERIFY-LIVE = <what confirms "
               "it in prod>`), or use a status other than `deployed` if it has not actually shipped "
               "(operator 2026-08-09, the inverse of the #167 lesson)")
        touched = False
        if git_ok:
            prior = prior_by_id.get(t["id"])
            touched = prior is None or prior["title"] != t["title"] or prior["status"] != t["status"]
        msg = (f"L{t['line']}: task #{t['id']} is `deployed` but its text states NO verify "
               f"condition at all — {fix}.")
        if touched:
            errors.append(msg)
        else:
            print(f"[plan] WARN — pre-existing deployed-with-no-verify-claim: {msg}")


_SHIPPED_CODE_DIRS = ("agents/", "core/", "channels/", "shared/", "main.py")
_OWN_COMMIT = re.compile(r"^#(\d+)[:.\s]")


def _own_commits_touching_code(tids: set[int], repo: Path = REPO) -> dict[int, tuple[str, str]]:
    """For each id in `tids`: the NEWEST commit whose subject STARTS with `#id` (this repo's
    convention for "this commit IS that task's work", anchored via `_OWN_COMMIT`) AND which
    touched real product code under `_SHIPPED_CODE_DIRS`. An id with no such commit is absent
    from the result.

    THE SINGLE SOURCE OF TRUTH for "does a commit naming this task touch code" (2026-08-30
    fix). It was implemented three times with drifted answers: this scan (formerly inlined in
    `_shipped_pending_gate`) and `shipped_but_unrecorded`'s separate `--grep` search, which used
    a DIFFERENT path tuple (`_CODE_PATHS` — missing `main.py`, carrying a dead `broker/` entry
    that matched nothing since the real path is `agents/market_intelligence/broker/`, already
    covered by `agents/`) and a looser, unanchored match (any `#N` mention in the first 120
    chars of the subject, not a subject that STARTS with it). One path tuple, one anchoring
    regex now — measured 2026-07-25 on the live board: matching ANY `#N` mention in a
    code-touching commit flags 31 of 84 tasks (subjects cross-reference IDs constantly —
    unusable); requiring the subject to START with `#N` flags 4 of 55 pending. Callers keep
    their own trigger predicate (pending-status vs a NOT-SHIPPED-claim) and their own
    hard-fail-vs-advisory response.

    Fails open (empty dict) on any git problem — a board-hygiene helper must never block a
    commit on a git/infra hiccup.
    """
    if not tids:
        return {}
    try:
        log = subprocess.run(["git", "log", "--all", "--format=%h%x00%s"], cwd=str(repo),
                             capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=10)
        if log.returncode != 0:
            return {}
    except Exception:
        return {}   # git unavailable — never block a commit on infra
    first: dict[int, tuple[str, str]] = {}
    for line in log.stdout.splitlines():
        sha, _, subj = line.partition("\x00")
        m = _OWN_COMMIT.match(subj)
        if not m:
            continue
        tid = int(m.group(1))
        if tid in tids and tid not in first:
            first[tid] = (sha, subj)   # log is newest-first -> first hit is the newest commit
    out: dict[int, tuple[str, str]] = {}
    for tid, (sha, subj) in first.items():
        try:
            files = subprocess.run(["git", "show", "--name-only", "--format=", "-r", sha],
                                   cwd=str(repo), capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=10).stdout
        except Exception:
            continue
        if any(f.startswith(_SHIPPED_CODE_DIRS) for f in files.splitlines() if f.strip()):
            out[tid] = (sha, subj)
    return out


def _shipped_pending_gate(tasks, errors) -> None:
    """A `pending` task whose OWN commit already shipped product code is contradictory — `pending`
    means NOT STARTED, and code named after the task exists. That contradiction is what makes a line
    read as unstarted months after it shipped, which then generates a DUPLICATE card: on 2026-07-25
    #495 (built 7/21, `786b294`) and #402 both did exactly that in one day, and the existing
    LIKELY-BUILT surface is ADVISORY so it got triaged as housekeeping and ignored.

    Fix by correcting the STATUS (a task with shipped code is at minimum `in_progress`, usually
    `deployed` + a verify-date), never by deleting the tag. `in_progress` is exempt: a multi-part
    task legitimately ships part 1 while remaining open."""
    pending = {t["id"]: t for t in tasks if str(t["status"]).lower() == "pending"}
    if not pending:
        return
    hits = _own_commits_touching_code(set(pending))
    for tid, (sha, subj) in sorted(hits.items()):
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
        # Shared with the `swept:` marker via _marker_age_days — which also closed a real hole
        # here: this check had no lower bound, so `revalidated:2099-01-01` gave a NEGATIVE age
        # that satisfied `<= _REVALIDATE_MAX_AGE` and read as fresh, muting a COMMIT-BLOCKING
        # gate indefinitely. Found 2026-08-07 by the /simplify reuse+altitude passes, which
        # noticed the two markers had drifted. No board task was future-dated, so this is
        # hardening, not a fix for an active break.
        _rv_age = _marker_age_days(_REVALIDATED, title, today)
        fresh = _rv_age is not None and _rv_age <= _REVALIDATE_MAX_AGE
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


def _print_pinned_runbooks() -> None:
    """Surface any pinned runbook at OPEN (operator 2026-08-27: "make sure the runbook is
    accessible when i start day or when we deploy tonight so it's not missed").

    Reads `RUNBOOK_PIN:` lines out of docs/ops/runbook_*.md — the SAME marker deploy.sh's
    banner reads, so one file feeds both surfaces and they cannot drift. Delete the runbook
    (or its pin lines) once it is spent.

    ⚠ Wholly wrapped: this function runs inside a COMMIT GATE. A missing directory, an
    unreadable file or a decoding error must never turn into a failed commit, so every error
    is swallowed and it degrades to printing nothing.
    """
    try:
        import glob
        for path in sorted(glob.glob("docs/ops/runbook_*.md")):
            try:
                with open(path, encoding="utf-8") as fh:
                    pins = [l.split("RUNBOOK_PIN:", 1)[1].strip()
                            for l in fh if l.startswith("RUNBOOK_PIN:")]
            except OSError:
                continue
            if not pins:
                continue
            print(f"\n📕 PINNED RUNBOOK — {path}")
            for line in pins:
                print(f"   {line}")
    except Exception:
        pass


def day_movement(today) -> dict:
    """What OPENED and CLOSED on the operator's PT day, derived from git — never from memory.

    WHY THIS EXISTS (2026-09-01). Asked what the day achieved, I listed nine closes; four of them
    were the PREVIOUS day's. The operator caught it: "you show us have 9 real closes but task
    closed is only 1". Reporting the day's movement from recollection across a date boundary is
    exactly the kind of claim that should never have been prose — the board's history is in git
    and the answer is decidable.

    Compares the SET of task ids in PLAN.md at the last commit BEFORE the PT day began against
    the set now. A line that was edited (removed and re-added with a note) is correctly NOT a
    close, which a naive diff of +/- lines gets wrong.
    """
    import subprocess

    def _ids(text: str) -> set:
        return {m.group(1) for m in (_TASK.match(l) for l in text.splitlines()) if m}

    start = datetime.combine(today, dtime(0, 0), tzinfo=_OPERATOR_TZ).isoformat()
    try:
        rev = subprocess.run(["git", "rev-list", "-1", f"--before={start}", "HEAD"],
                             cwd=REPO, capture_output=True, text=True, timeout=20).stdout.strip()
        if not rev:
            return {"error": "no commit precedes the PT day — cannot compute movement"}
        before = subprocess.run(["git", "show", f"{rev}:PLAN.md"],
                                cwd=REPO, capture_output=True, text=True, timeout=20).stdout
    except Exception as e:  # loud-ok: reporting aid, never blocks a commit
        return {"error": f"{type(e).__name__}: {e}"}

    was, now = _ids(before), _ids(PLAN.read_text(encoding="utf-8"))
    return {"closed": sorted(was - now, key=int), "opened": sorted(now - was, key=int),
            "start_count": len(was), "end_count": len(now), "since": rev[:8]}

def main(argv: list[str]) -> int:
    if not PLAN.exists():
        print(f"[plan] ERROR: {PLAN} not found — it is the single source of truth.")
        return 2
    tasks, errors = parse(PLAN.read_text(encoding="utf-8"))
    today = datetime.now(_OPERATOR_TZ).date()   # the operator's PT day, not ET (see _OPERATOR_TZ note)

    if "--movement" in argv:
        m = day_movement(today)
        if m.get("error"):
            print(f"[movement] {m['error']}")
            return 0
        print(f"=== BOARD MOVEMENT — {today} (PT), against {m['since']} ===")
        print(f"  started {m['start_count']} · now {m['end_count']} · "
              f"net {m['end_count'] - m['start_count']:+d}")
        print(f"  CLOSED ({len(m['closed'])}): " + (", ".join('#' + i for i in m['closed']) or "none"))
        print(f"  OPENED ({len(m['opened'])}): " + (", ".join('#' + i for i in m['opened']) or "none"))
        print("  (a line edited in place is NOT a close — this compares id SETS, not +/- lines)")
        print("  ⚠ a task OPENED AND CLOSED the same day appears in neither list: it is in neither\n"
              "     the start set nor the end set. #614 was one on 2026-09-01.")
        return 0

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
        # SHIPPED-BUT-UNRECORDED (2026-08-30) — the line SAYS it has not shipped, but a commit
        # naming this task touched real code. See shipped_but_unrecorded() for why this is the
        # one staleness class every other surface here is blind to.
        # STALE BLOCKER (2026-08-30) — blocked on a task that has left the board.
        stale_blocks = stale_blockers(tasks)
        print(f"\n-- STALE BLOCKER ({len(stale_blocks)}) — `blocked` on a task no longer on the "
              f"board: the block may be fiction --")
        if stale_blocks:
            for t, gone in stale_blocks:
                print(f"  #{t['id']}  blocked on {', '.join('#' + g for g in gone)} — gone")
            print("  (re-read: the blocker may have shipped. #331 sat blocked for weeks this way.)")
        else:
            print("  (none)")

        stale_claims = shipped_but_unrecorded(tasks, today)
        print(f"\n-- SHIPPED-BUT-UNRECORDED ({len(stale_claims)}) — the line claims NOT shipped, "
              f"but a commit naming it touched code: RE-READ before commissioning any work --")
        if stale_claims:
            for t, commit in stale_claims:
                print(f"  #{t['id']}  <- {commit}")
            print("  (⚠ this is the class that got ~30 tasks re-done. Update the line or close it.)")
        else:
            print("  (none)")
        # PENDING-VERIFY CLAIM (operator 2026-08-09, the #167 lesson): a task's OWN TEXT asserts a
        # verification is still open but its status says otherwise. Surfaced every OPEN — not just
        # at commit time — so a pre-existing (WARN-only) violation can never go quiet between
        # sessions the way #167 did.
        pending_verify = _pending_verify_violations(tasks)
        print(f"\n-- VERIFY-CLAIMED, NOT DEPLOYED ({len(pending_verify)}) — task text asserts a "
              f"pending verify but status isn't `deployed`: set status=deployed + a verify-date ETA --")
        for t in pending_verify or []:
            # Print the matched CLAIM, not the title's first 90 chars — on these multi-KB task
            # lines the claim sits thousands of characters into the title, so a plain title-prefix
            # truncation (as LIKELY-BUILT's bare-ID list sidesteps by not showing content at all)
            # would show the headline and hide the exact reason this line was flagged.
            claim = _pending_verify_matches(t["title"])[0][:100]
            print(f"  #{t['id']:<4} [{t['status']:<11}] {t['project']}")
            print(f"        claim: {claim}")
        if not pending_verify:
            print("  (none)")
        # NOTE: no `--today` surface for the inverse (deployed-no-claim) direction. Measured
        # 2026-08-09: at the time this surface was declined, ALL 4 current firings were, on manual
        # read, tasks that DO state a check just in idiom the (then-STRICT-only) shared vocabulary
        # didn't catch — a permanent OPEN-ritual block built entirely of known false positives is the
        # LIKELY-BUILT 9/9 failure mode this file already documents ("triaged as housekeeping and
        # ignored"). `_VERIFY_CLAIM_TRIGGER_BROAD` (same day, see that gate's section comment) closed
        # 3 of those 4 false positives; #513 remains a genuine gap, not a false positive, so this
        # decision is due for a fresh look but is unchanged by this card (board-hygiene scope only).
        # The gate's WARN print (every plain run, incl. pre-commit and CLOSE) already satisfies the
        # WARN/HARD-FAIL escalation the ticket asked for; see `_deployed_no_verify_gate`'s section
        # comment for the full finding.
        base = _pin_daily_baseline(len(tasks), today)
        # OPEN drops a watermark too, so a day where the operator runs `--today`
        # and never commits still arms TOMORROW's carry-over. Previously only the
        # plain run recorded it, so an open-but-no-commit day left no mark at all.
        _record_watermark(base, len(tasks), today)
        ceiling = base["baseline_count"] + base.get("carryover_allowance", 0)
        print(f"\n-- GROWTH GATE — day started at {base['baseline_count']} open tasks. This session must "
              f"END <= {ceiling} (HARD, operator 2026-07-12: no session ends bigger than it began).")
        print("   Take a HARD LOOK for real closes; open a new task only if you close a real one first.")
        _print_pinned_runbooks()
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
    _pending_verify_gate(tasks, errors)   # own text claims a pending verify but status != deployed; HARD on touched, WARN on pre-existing (operator 8/09, the #167 lesson)
    _deployed_no_verify_gate(tasks, errors)   # deployed but states NO verify condition at all; HARD on touched, WARN on pre-existing (operator 8/09, the inverse)

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
