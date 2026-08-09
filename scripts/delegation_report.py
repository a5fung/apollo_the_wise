#!/usr/bin/env python3
"""Delegation ledger for the CLOSE ritual — a REPORTER, deliberately not a blocking gate.

WHY THIS IS NOT A STOP HOOK (measured 2026-08-09, 41 PT-day units, Jun 29 - Aug 9)
The operator's ask ("i keep needing to prompt you to not do all work yourself") repeats across
days, and the repo's lesson says only gates hold. But a gate needs an objectively-decidable
trigger with a low false-positive rate, and the transcript history says NO COUNT-BASED TRIGGER
HAS ONE. Mined against 4 labeled delegation complaints (07-17, 07-23, 08-03, 08-09):

  - "impl edits with ZERO Agent spawns"      -> catches 0 of 4 complaint days (every one HAD
                                                spawns, 2-12 of them). Recall zero. Dead.
  - "impl edits >= 10 in a day"              -> fires 15 days, 1 was a complaint. Precision 7%.
  - "work-calls per spawn >= 40"             -> fires 17 days, 2 complaints. Precision 12%.
  - "longest no-spawn run >= 100 calls"      -> fires 17 days, 3 complaints. Precision 18%
                                                (~3 false fires/week -> wallpaper in a week).
  - "first spawn later than 100 calls"       -> fires 7 days, 2 complaints. Precision 29% —
                                                the best found, and it still misses 08-09.
  - "bash heredoc/redirect writes into impl" -> near-zero base rate; 0 on every complaint day.

Killer facts: the sharpest complaint (08-09, "are you planning to do all the work yourself
today?") landed on one of the LIGHTEST days in the corpus — 41 read-only calls, zero impl
edits, zero spawns at that moment; while the two most extreme days by every count metric
(08-01: a 436-call no-spawn run; 08-02: 443) drew no complaint, and on 08-08 the operator
explicitly asked to STAY in the main thread. The variable he reacts to is the KIND of work
being done inline (complex/open-ended vs mechanical/bookkeeping) and whether the morning plan
routed it — which is semantic. Same boundary report_format_gate.py drew: rules a gate cannot
decide from the text alone stay judgement calls, because a guard that always fires is not a
guard (three broad checks were built and thrown away here in one week for exactly that).

WHAT SHIPS INSTEAD — two mechanical surfaces around the semantic core:
  1. This ledger, run at CLOSE: names the specific card-shaped chunks that were done inline
     (files with >= CARD_SHAPED_EDITS main-loop edits — e.g. 07-20 built ep_detector.py x17 +
     briefing.py x13 + ep_delayed_residual.py x12 inline), the spawn list, and the longest
     no-spawn stretch. Retrospective, specific, zero block cost.
  2. A ROUTING DECLARATION (--route, written at OPEN): pins WHO does each planned piece into
     .apollo_routing.json. The ledger then cross-checks declared-vs-observed — "declared
     #494 -> sonnet, but no sonnet card ran today" IS objectively decidable, against your own
     morning promise instead of a population threshold. This also covers the count-blind spot:
     a read-only investigation shows up in the morning routing even though it never edits.
     main/opus declarations (delegation_gate.py's escape hatch for a conscious main-loop day)
     get a parallel but different check — main_route_crosscheck() below — since there's no
     separate agent to watch for; it compares the declaration against the day's own observed
     card-shaped edits instead of spawn presence (2026-08-09: this used to be entirely
     unchecked — route_discrepancies() skipped main/opus and nothing else picked it up, while
     the gate's own docstring claimed it WAS cross-checked. Fixed the substance.).

WHAT THIS CANNOT SEE, said plainly: main-loop work that produces no tool-visible artifact
mix shift — above all a long READ-ONLY investigation (the 08-09 miss) on a day with no
routing declared. The declaration surface exists precisely because the counts cannot.

Fails OPEN everywhere: missing transcript dir, unreadable files, malformed lines, any
unexpected exception -> prints a skip note and exits 0. A discipline report must never
wedge a session. Exit code is ALWAYS 0 — there is nothing here worth blocking on.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

_PT = ZoneInfo("America/Los_Angeles")
REPO = Path(__file__).resolve().parents[1]

# IMPL_DIRS / IMPL_EXCLUDE / BOOKKEEPING_BASENAMES / MAIN_WHO / routing-file read+parse used to
# be defined here AND independently in delegation_gate.py — a 2026-08-09 4-reviewer pass found
# they'd already diverged (this file's IMPL_DIRS was missing infra/ and tests/, which the gate
# already gated) and the routing-file reader was reimplemented twice with one honoring
# APOLLO_ROUTING_FILE and one hardcoding the path. Now sourced from one shared module. This
# script is a CLI reporter, not a PreToolUse hook, but it makes the same "fails OPEN, always"
# promise (module docstring above) — an unguarded import failing here would crash before
# main()'s own try/except ever ran, breaking that promise, so it gets the same guarded import
# with an allow/degrade-biased fallback as the gate.
try:
    from delegation_shared import (
        IMPL_DIRS, IMPL_EXCLUDE, BOOKKEEPING_BASENAMES, MAIN_WHO,
        routing_file_path, load_routing_for_day,
    )
except Exception:            # noqa: BLE001 — see note above; a report must never wedge a session
    IMPL_DIRS = ()
    IMPL_EXCLUDE = ()
    BOOKKEEPING_BASENAMES = frozenset()
    MAIN_WHO = frozenset({"main", "opus"})
    routing_file_path = lambda: REPO / ".apollo_routing.json"  # noqa: E731 - degraded fallback
    load_routing_for_day = None

# Module-level, monkeypatchable attribute (kept, rather than resolving fresh on every call) so
# tests can redirect it exactly as before; the difference from pre-2026-08-09 is that its
# default now honors APOLLO_ROUTING_FILE via the shared resolver instead of always hardcoding
# the repo path — the other half of the finding-#4 divergence (the gate already honored it).
ROUTING_FILE = routing_file_path()

# >= this many main-loop edits to ONE impl file in a day reads as a built-inline chunk.
# Measured: at 3 the flag names the real ones (ep_detector x17, theme_engine x13) while
# 1-2-edit files are usually the trivial one-liners CLAUDE.md keeps inline.
CARD_SHAPED_EDITS = 3

# classify_path() early-returns a dedicated "tests" bucket for tests/ BEFORE it ever consults
# IMPL_DIRS (same for "docs") — kept separate for the operator-facing label, "wrote tests" vs
# "built a detector" is a real distinction worth keeping visible. But tests/ IS card-shaped
# implementation work (CLAUDE.md operating model: Sonnet cards explicitly own "scoped
# well-specified builds, tests, refactors, sweeps") and delegation_gate.py already blocks
# main-loop tests/ writes without a routing declaration — so a main-loop day of writing tests
# needs to feed the SAME card-shaped detection impl edits do, or it is gated on the way in and
# invisible on the way out (2026-08-09 finding #1's stated consequence). "docs" stays out on
# purpose: docs/ is never gated by delegation_gate.py at all (never needs a declaration).
CARD_SHAPED_CLASSES = frozenset({"impl", "tests"})

WORK_TOOLS = frozenset({"Bash", "Edit", "Write", "Read", "NotebookEdit", "Grep", "Glob"})
SPAWN_TOOLS = frozenset({"Agent", "Task"})  # "Task" = older harness name for the same tool
EDIT_TOOLS = frozenset({"Edit", "Write", "NotebookEdit"})

_ROUTE_ARG = re.compile(r"^(?P<task>[^:]+):(?P<who>fable|sonnet|opus|main|advisor)(?::(?P<note>.*))?$")


# ── time ─────────────────────────────────────────────────────────────────────────────────────

def pt_today() -> str:
    return datetime.now(_PT).date().isoformat()


def pt_day_of(ts: str) -> str | None:
    """ISO PT date for a transcript timestamp like 2026-08-09T13:10:57.161Z; None if unparseable."""
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(_PT).date().isoformat()
    except (ValueError, TypeError):
        return None


# ── path classification ──────────────────────────────────────────────────────────────────────

def classify_path(fp: str) -> str:
    """impl | tests | docs | bookkeeping | probes | scratch | repo_other | outside | none."""
    if not fp:
        return "none"
    p = Path(fp)
    if not p.is_absolute():
        p = REPO / p
    fp_norm = os.path.normpath(str(p))
    if "/scratchpad" in fp_norm or fp_norm.startswith(("/tmp/", "/private/tmp/")):
        return "scratch"
    if "/memory/" in fp_norm or os.path.basename(fp_norm) in BOOKKEEPING_BASENAMES:
        return "bookkeeping"
    try:
        rel = str(Path(fp_norm).relative_to(REPO))
    except ValueError:
        return "outside"
    if rel.startswith("tests/"):
        return "tests"
    if rel.startswith("docs/"):
        return "docs"
    if any(rel.startswith(ex) for ex in IMPL_EXCLUDE):
        return "probes"
    if any(rel.startswith(d) for d in IMPL_DIRS):
        return "impl"
    return "repo_other"


# ── transcript scan ──────────────────────────────────────────────────────────────────────────

@dataclass
class DayLedger:
    day: str
    tool_counts: Counter = field(default_factory=Counter)
    impl_edits: Counter = field(default_factory=Counter)      # rel path -> n
    other_edit_classes: Counter = field(default_factory=Counter)
    spawns: list = field(default_factory=list)                # (model, subagent_type, description)
    longest_no_spawn_run: int = 0
    _run: int = 0
    files_scanned: int = 0

    @property
    def work_calls(self) -> int:
        return sum(v for k, v in self.tool_counts.items() if k in WORK_TOOLS)


def transcript_dir() -> Path:
    """Claude Code project transcript dir for this repo (env-overridable for tests).

    The harness munges the project path by replacing every non-alphanumeric with '-'."""
    env = os.environ.get("APOLLO_TRANSCRIPT_DIR")
    if env:
        return Path(env)
    munged = re.sub(r"[^A-Za-z0-9]", "-", str(REPO))
    return Path.home() / ".claude" / "projects" / munged


def _sanitize(s: str, limit: int = 60) -> str:
    """Transcript content is untrusted data — strip control chars, truncate, never interpret."""
    return re.sub(r"[\x00-\x1f\x7f]", " ", str(s))[:limit]


def scan_day(day: str, tdir: Path | None = None) -> DayLedger:
    """Stream every transcript touched since the target PT day began; bucket by PT day;
    dedup entries by uuid (forked sessions duplicate history across files)."""
    ledger = DayLedger(day=day)
    tdir = tdir or transcript_dir()
    try:
        day_start = datetime.combine(
            datetime.fromisoformat(day).date(), time.min, tzinfo=_PT).timestamp()
        paths = [p for p in glob.glob(str(tdir / "*.jsonl"))
                 if os.path.getmtime(p) >= day_start]
    except (OSError, ValueError):
        return ledger
    seen: set[str] = set()
    for path in sorted(paths):
        try:
            fh = open(path, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            ledger.files_scanned += 1
            ledger._run = 0          # a stretch never spans two separate sessions
            last_day = None
            for line in fh:
                try:
                    d = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(d, dict):
                    continue
                ts = d.get("timestamp")
                entry_day = pt_day_of(ts) if ts else last_day
                if entry_day:
                    last_day = entry_day
                if entry_day != day or d.get("type") != "assistant":
                    continue
                uid = d.get("uuid")
                if uid:
                    if uid in seen:
                        continue
                    seen.add(uid)
                content = (d.get("message") or {}).get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not (isinstance(block, dict) and block.get("type") == "tool_use"):
                        continue
                    name = block.get("name", "")
                    inp = block.get("input") or {}
                    if not isinstance(inp, dict):
                        inp = {}
                    ledger.tool_counts[name] += 1
                    if name in SPAWN_TOOLS:
                        ledger.spawns.append((
                            _sanitize(inp.get("model") or "inherit", 12),
                            _sanitize(inp.get("subagent_type") or "-", 20),
                            _sanitize(inp.get("description") or "", 60),
                        ))
                        ledger._run = 0
                    elif name in WORK_TOOLS:
                        ledger._run += 1
                        ledger.longest_no_spawn_run = max(ledger.longest_no_spawn_run, ledger._run)
                        if name in EDIT_TOOLS:
                            cls = classify_path(inp.get("file_path", ""))
                            if cls in CARD_SHAPED_CLASSES:
                                fp = inp.get("file_path", "")
                                try:
                                    rel = str(Path(fp).relative_to(REPO))
                                except ValueError:
                                    rel = fp
                                ledger.impl_edits[rel] += 1
                            else:
                                ledger.other_edit_classes[cls] += 1
    return ledger


# ── routing declaration (--route, written at OPEN) ──────────────────────────────────────────

def load_routes(day: str) -> list[dict]:
    """Thin wrapper: the actual read/parse/date-check lives in delegation_shared.
    load_routing_for_day (shared with delegation_gate.routed_main_today, 2026-08-09 finding
    #4). ROUTING_FILE stays a module attribute, not a fresh routing_file_path() call, so tests
    can keep monkeypatching dr.ROUTING_FILE directly."""
    if load_routing_for_day is None:   # delegation_shared failed to import — degrade, don't crash
        return []
    return load_routing_for_day(day, ROUTING_FILE)


def save_routes(day: str, specs: list[str]) -> list[dict]:
    """Parse '#494:fable[:note]' specs and pin them for the day. Overwrites — OPEN is the
    one moment this is written; re-running --route re-declares the whole day."""
    routes = []
    for spec in specs:
        m = _ROUTE_ARG.match(spec.strip())
        if not m:
            raise ValueError(
                f"bad route spec {spec!r} — want TASK:WHO[:note], "
                "WHO in fable|sonnet|opus|main|advisor")
        routes.append({"task": m.group("task").strip(), "who": m.group("who"),
                       "note": (m.group("note") or "").strip()})
    ROUTING_FILE.write_text(json.dumps({"pt_date": day, "routes": routes}, indent=1) + "\n")
    return routes


def route_discrepancies(routes: list[dict], ledger: DayLedger) -> list[str]:
    """Declared-vs-observed, the one objectively-decidable check: a task routed to a card
    model with ZERO spawns of that model all day. Conservative on purpose — we cannot map a
    spawn to a task #, so any spawn of the declared model clears every task declared to it.

    main/opus routes are deliberately SKIPPED here — not because they go unchecked, but
    because "no X agent ran" has no meaning for the main loop (declaring main IS the work,
    there's no separate agent whose absence would be a gap). They get a different, real check
    instead: see main_route_crosscheck() below, which compares the declaration against the
    day's own observed card-shaped edits rather than spawn presence. That split is what makes
    delegation_gate.py's "cross-checked by the CLOSE ledger" claim true (2026-08-09 4-reviewer
    finding — it used to be false: this function skipped main/opus and nothing else picked
    them up)."""
    spawned_models = Counter(m for m, _t, _d in ledger.spawns)
    spawned_types = Counter(t for _m, t, _d in ledger.spawns)
    out = []
    for r in routes:
        who = r.get("who")
        if who in MAIN_WHO:
            continue
        if spawned_models.get(who, 0) == 0 and spawned_types.get(who, 0) == 0:
            out.append(
                f"{r.get('task', '?')} was declared {who.upper()} work this morning, "
                f"but no {who} agent ran today — carded elsewhere, replanned, or done inline?")
    return out


def main_route_crosscheck(routes: list[dict], ledger: DayLedger) -> list[str]:
    """The check delegation_gate.py's docstring promises for the day-granular main/opus
    escape hatch — not just echoed at OPEN, actually compared against what this ledger
    observed. Two directions:

    1. main/opus declared today -> name the card-shaped inline edits actually observed (files
       + counts, not a bare total — a number the operator can't act on is noise, CLAUDE.md
       report-format rule 6), or say plainly that none were found.
    2. card-shaped inline edits observed with NO main/opus declared that day -> structurally
       shouldn't happen while delegation_gate.py is live (it would have denied the write); if
       this fires, the gate was off (DELEGATION_GATE=off), bypassed, or the subagent
       discriminator broke. That direction has teeth even when direction 1 stays quiet.

    LIMIT, stated plainly so this doesn't just re-overclaim what got fixed: the escape is
    still DAY-granular. This confirms card-shaped work happened on a day main/opus was
    declared, not that the observed files match the declared task's own scope — a "#494:main"
    declaration for one fix still nominally covers an unrelated file edited the same day."""
    declared = [r.get("task", "?") for r in routes if r.get("who") in MAIN_WHO]
    if declared:
        if ledger.impl_edits:
            named = ", ".join(f"{f} ({n})" for f, n in ledger.impl_edits.most_common(5))
            return [f"main/opus declared ({', '.join(declared)}) — card-shaped inline edits "
                    f"observed today: {named}"]
        return [f"main/opus declared ({', '.join(declared)}) — zero card-shaped inline edits "
                "observed today (declared but unused, replanned, or done via a spawn instead)"]
    if ledger.impl_edits:
        named = ", ".join(f"{f} ({n})" for f, n in ledger.impl_edits.most_common(5))
        return [f"inline edits observed with NO main/opus declared today: {named} — if "
                "delegation_gate.py was on that day, it should have denied every one of "
                "these; if it fires on a day the gate was live, check DELEGATION_GATE isn't "
                "'off' and the subagent discriminator still holds (no action needed for days "
                "before the gate existed)"]
    return []


# ── render ───────────────────────────────────────────────────────────────────────────────────

def render(ledger: DayLedger, routes: list[dict]) -> str:
    L: list[str] = [f"DELEGATION LEDGER — {ledger.day} (PT), "
                    f"{ledger.files_scanned} transcript(s) scanned"]
    if ledger.files_scanned == 0 or (ledger.work_calls == 0 and not ledger.spawns):
        L.append("  no main-loop activity found for this day — nothing to report")
        return "\n".join(L)

    if ledger.spawns:
        L.append(f"  agent spawns: {len(ledger.spawns)}")
        for model, stype, desc in ledger.spawns[:20]:
            L.append(f"    - {model:8} {stype:16} {desc}")
        if len(ledger.spawns) > 20:
            L.append(f"    ... and {len(ledger.spawns) - 20} more")
    else:
        L.append("  agent spawns: NONE")

    mix = "  ".join(f"{k} {v}" for k, v in ledger.tool_counts.most_common()
                    if k in WORK_TOOLS)
    L.append(f"  main-loop work calls: {ledger.work_calls}  ({mix})")
    L.append(f"  longest stretch without a spawn: {ledger.longest_no_spawn_run} work calls")

    card_shaped = [(f, n) for f, n in ledger.impl_edits.most_common()
                   if n >= CARD_SHAPED_EDITS]
    small = [(f, n) for f, n in ledger.impl_edits.most_common() if n < CARD_SHAPED_EDITS]
    if card_shaped:
        L.append(f"  CARD-SHAPED, done inline ({CARD_SHAPED_EDITS}+ main-loop edits to one "
                 "implementation file):")
        for f, n in card_shaped:
            L.append(f"    - {f}  ({n} edits)  -> this was a Sonnet card "
                     "(or Fable, if it was the hard part)")
    if small:
        L.append(f"  small inline impl edits (fine if trivial): "
                 + ", ".join(f"{f} x{n}" for f, n in small[:8]))

    if ledger.other_edit_classes:
        L.append("  other inline edits (context, not implementation): "
                 + ", ".join(f"{k} {v}" for k, v in ledger.other_edit_classes.most_common()))

    if routes:
        gaps = route_discrepancies(routes, ledger)
        L.append(f"  routing declared at OPEN: "
                 + ", ".join(f"{r.get('task')}->{r.get('who')}" for r in routes))
        if gaps:
            L.append("  ROUTING GAPS (declared vs observed):")
            L.extend(f"    - {g}" for g in gaps)
        else:
            L.append("  routing gaps: none — every declared card model ran")
    else:
        L.append("  no routing declared today (OPEN step: "
                 "`delegation_report.py --route \"#N:fable\" \"#M:sonnet\"`)")

    crosscheck = main_route_crosscheck(routes, ledger)
    if crosscheck:
        L.append("  MAIN/OPUS CROSS-CHECK (what the gate's day-granular escape actually did):")
        L.extend(f"    - {c}" for c in crosscheck)
        L.append("    limit: confirms card-shaped work happened on a day main/opus was "
                 "declared, not that it matches the declared task's scope — the escape is "
                 "still day-granular, not task-scoped.")

    L.append("  blind spot, stated: read-only main-loop investigations (the 2026-08-09 miss) "
             "leave no edit trail — only the OPEN routing declaration surfaces those.")
    return "\n".join(L)


# ── main ─────────────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], add_help=True)
    ap.add_argument("--day", default=None, help="PT day to report (default: today)")
    ap.add_argument("--route", nargs="+", metavar="TASK:WHO[:note]", default=None,
                    help="declare today's routing at OPEN (who: fable|sonnet|opus|main|advisor)")
    try:
        args = ap.parse_args(argv)
        day = args.day or pt_today()
        if args.route is not None:
            routes = save_routes(day, args.route)
            print(f"[delegation] routing pinned for {day}: "
                  + ", ".join(f"{r['task']}->{r['who']}" for r in routes))
            return 0
        ledger = scan_day(day)
        print(render(ledger, load_routes(day)))
    except SystemExit:
        raise
    except ValueError as e:
        # bad --route spec is the ONE loud path — it is caller input, not environment
        print(f"[delegation] {e}", file=sys.stderr)
        return 0
    except Exception as e:  # noqa: BLE001 — fail OPEN, always: a report must never wedge a session
        print(f"[delegation] report skipped ({type(e).__name__}: {e})", file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
