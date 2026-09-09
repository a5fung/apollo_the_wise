#!/usr/bin/env python3
"""THE single source for "what waits on the operator" — computed, never remembered.

WHY THIS EXISTS (2026-09-08). Operator, after being asked the same answered questions on
consecutive days: "everyday you tell me you're waiting on me for the same things, over and
over" -> "I don't want you asking me these answered items again." An audit that day found
THREE OF FOUR standing asks were already answered:

  #184  the flip was taken 2026-07-17 and carried for seven weeks
  #612  dead since 09-02 — he had said twice we have no FMP sub
  #452  he ruled it the previous day
  #594  he had already labelled the chart sample, AND a cadence gate existed
        (chart_reading_review_cycle: 40 new alerts, earliest 2026-09-20) built on
        2026-09-06 for the express purpose of not depending on my memory. I asked anyway.

The failure was never forgetfulness. It was that I ASSEMBLED the list BY HAND from PLAN.md
task text, which is written once when an ask is raised and never retracted when he answers.
Every other prose discipline in this repo rotted the same way and every one of them had to
become a gate. This is that gate.

THE RULE THIS ENFORCES: an ask may only be put to him if it appears in THIS script's output.
If it is not here, it is not open — do not raise it, do not "just check". The script runs the
predicates rather than trusting prose, so an answered ask disappears on its own.

Read-only. No DB writes, no network beyond the read-only prod query the gated reviews already use.
"""
from __future__ import annotations

import base64
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLAN = REPO / "PLAN.md"

# An ask that is genuinely open must state, in one line, the LIVE FACT that proves it.
# "The task text says so" is not a proof — that is exactly what rotted.
_ASK_BLOCK = re.compile(
    r"^### Standing — waits on the operator.*?(?=^## |\Z)", re.M | re.S)


def _gated_reviews_ready() -> list[str]:
    """Asks that carry a real predicate live in data_gated_reviews.yaml — and this RUNS the
    predicates rather than asserting their answer.

    ⚠ WHY THIS WAS REWRITTEN (2026-09-09, one day after the script shipped). The first version
    listed every pending review under the line "NOT an ask until its own predicate says READY"
    — **without ever asking the predicate.** So a review that WAS ready could never surface, and
    the sentence was not a finding but a fixed string. `gap_alignment_331_accrual` is the proof:
    its predicate is `SELECT count(*) FROM mi_theme_axis_shadow` against a threshold of 700, prod
    holds **3,120**, and #331 sat parked to 2026-11-06 on a hand-count of 592 that was wrong by
    more than 5x. A gate that cannot fire is the exact defect class this file was written to stop,
    and it shipped inside the fix for it.

    Returns (ready, accruing, error). **`error` is not cosmetic: an unreachable database must
    NEVER render as "nothing waits on him"** — that is the silent-guard failure wearing the
    friendliest possible face."""
    try:
        import yaml
    except ImportError:
        return [], ["(pyyaml missing — cannot read the gated reviews)"], "pyyaml missing"
    d = yaml.safe_load((REPO / "data_gated_reviews.yaml").read_text())
    pending = [r for r in d.get("reviews", [])
               if r.get("status") == "pending"
               and "operator" in str(r.get("action_when_ready", "")).lower()]
    if not pending:
        return [], [], None

    today = _operator_today()
    # ONE ssh + ONE psql for every predicate, not one per review (the capture-once cost rule).
    numbered = [(i, r) for i, r in enumerate(pending) if _has_predicate(r)]
    counts, err = _run_predicates(numbered)

    ready, accruing = [], []
    for i, r in numbered:
        rid = r["review_id"]
        thr = r.get("threshold")
        earliest = str(r.get("earliest_review_date") or "")
        got = counts.get(i)
        if got is None:
            accruing.append(f"{rid}: predicate DID NOT RUN — treat as UNKNOWN, never as not-ready.")
            continue
        date_ok = (not earliest) or earliest <= today
        if thr is not None and got >= thr and date_ok:
            # NOT "this is an ask". Every one of these actions starts with work that is MINE —
            # re-run the probe, produce the cut — and only THEN yields a decision for him.
            # Labelling a ready review as an operator ask would walk straight back into raising
            # things before they are answerable, which is what this file exists to stop.
            ready.append(f"{rid}: ⚠ READY — predicate reads {got} against threshold {thr}"
                         f"{'' if not earliest else f', earliest {earliest} has passed'}. "
                         f"RUN THE REVIEW (my work first; his decision only after it produces a "
                         f"result). Action: {str(r.get('action_when_ready','')).strip().splitlines()[0][:100]}")
        elif thr is not None and got >= thr:
            accruing.append(f"{rid}: threshold MET ({got}/{thr}) but earliest date {earliest} "
                            f"is still ahead. Not an ask yet.")
        elif got == 0 and earliest and earliest <= today:
            # A review reading ZERO whose own earliest date has already passed is not
            # "accruing" — it has produced nothing since the day it became eligible. Every
            # dead gate found on 2026-09-09 wore the accruing label: a phantom column (617),
            # an audit event emitted nowhere (harvest), a column never SET (failed_break), a
            # deprecated lane (9M convergence). Say ZERO out loud so it gets looked at.
            accruing.append(_zero_line(rid, r, got, thr, earliest, _days_since(earliest) or 0))
        else:
            accruing.append(f"{rid}: accruing {got}/{thr} (earliest {earliest}).")
    # A `kind: cadence` review is DATE-gated by design and correctly carries no predicate — it
    # becomes ready when its own earliest date arrives (chart_reading_review_cycle is the model).
    # Only a data-gated review with no predicate is broken.
    for r in pending:
        if _has_predicate(r):
            continue
        rid, earliest = r["review_id"], str(r.get("earliest_review_date") or "")
        if str(r.get("kind", "")).lower() == "cadence" and earliest:
            if earliest <= today:
                ready.append(f"{rid}: ⚠ READY — cadence review, earliest {earliest} has passed. "
                             f"RUN THE REVIEW (my work first; his decision only after).")
            else:
                accruing.append(f"{rid}: cadence — not due until {earliest}.")
        else:
            accruing.append(f"{rid}: NO predicate_sql and not a dated cadence review — it cannot "
                            f"become ready on its own. Give it a predicate or close it.")
    return ready, accruing, err


def _zero_line(rid: str, r: dict, got: int, thr, earliest: str, stale: int) -> str:
    """A review reading ZERO past its own date is either RULED or UNEXAMINED — never "accruing".

    #633 (2026-09-09) ruled the eleven that read zero that day: six were WAITING on an event that
    genuinely has not happened, with the proof written into the entry. Printing "check the
    predicate can ever be true" for a gate checked yesterday is a re-ask generator — the exact
    drift this script exists to stop — so a ruled entry carries `zero_verdict:` (a dated one-liner
    the loader can see; comments cannot be seen) and prints its ruling instead. An entry WITHOUT
    one stays loud: that zero has not been looked at."""
    ago = f", {stale}d ago" if stale else ""
    verdict = str(r.get("zero_verdict") or "").strip()
    if verdict:
        return (f"{rid}: ZERO since its date passed ({got}/{thr}, earliest {earliest}{ago}) — "
                f"RULED {verdict}")
    return (f"{rid}: ⚠ ZERO since its date passed ({got}/{thr}, earliest {earliest}{ago}). "
            f"Not accruing — it has produced NOTHING, and nobody has ruled why. Check the "
            f"predicate can ever be true before trusting this 0; when it can, record a dated "
            f"`zero_verdict:` on the entry so this is not re-asked.")


def _days_since(iso: str) -> "int | None":
    from datetime import date
    try:
        y, m, d = (int(x) for x in iso.split("-"))
        return (date.fromisoformat(_operator_today()) - date(y, m, d)).days
    except Exception:
        return None


def _has_predicate(r: dict) -> bool:
    """A predicate must be a non-empty STRING. `str(None)` is "None" — truthy — which let a
    review with an explicit YAML null reach the SQL builder and crash the whole tool on its
    first real run (2026-09-09)."""
    v = r.get("predicate_sql")
    return isinstance(v, str) and bool(v.strip())


def _operator_today() -> str:
    """The operator's PT day as YYYY-MM-DD — never the harness UTC date."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()


def _run_predicates(numbered) -> tuple[dict, "str | None"]:
    """Run every predicate on prod in ONE ssh, each ISOLATED. Returns ({idx: value}, error).

    ⚠ TWO THINGS THIS SHAPE EXISTS FOR, both learned by running it (2026-09-09):
    1. **Isolation.** The first version UNION-ALL'd all 44 predicates into one statement. A single
       review whose SQL ends `...= TRUE;  -- proxy: ...` (a semicolon mid-string, then a comment)
       made the whole batch a syntax error, and every review reported "DID NOT RUN". One bad row
       must never blind the list. Each predicate now gets its own psql invocation.
    2. **No re-quoting.** Each predicate is base64'd here and decoded on the host into `psql -f -`,
       so embedded quotes, semicolons, comments and newlines are carried verbatim. A trailing
       semicolon is legal for a standalone statement — it was only illegal as a subquery.

    Still ONE ssh round trip, per the capture-once cost rule."""
    if not numbered:
        return {}, None
    lines = []
    for i, r in numbered:
        b64 = base64.b64encode(r["predicate_sql"].strip().encode()).decode()
        lines.append(
            f'echo "{i}|$(echo {b64} | base64 -d | '
            f'docker exec -i apollo-postgres psql -U apollo -d apollo -t -A -f - 2>/dev/null '
            f'| head -1 | tr -d " ")"')
    script = "\n".join(lines)
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=25",
           "apollo@87.99.134.162", script]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if proc.returncode != 0 and not proc.stdout.strip():
            return {}, f"prod read failed (ssh exit {proc.returncode}): {proc.stderr.strip()[:160]}"
    except Exception as e:   # loud-ok: unreachable prod degrades to UNKNOWN, never to "not ready"
        return {}, f"prod read failed ({type(e).__name__}: {e})"
    out = {}
    for ln in proc.stdout.splitlines():
        k, _, v = ln.strip().partition("|")
        if k.isdigit() and v.strip().lstrip("-").isdigit():
            out[int(k)] = int(v)
    if not out:
        return {}, "prod read returned nothing parseable — treat every review as UNKNOWN"
    return out, None


def main() -> int:
    text = PLAN.read_text()
    m = _ASK_BLOCK.search(text)
    print("=== WHAT ACTUALLY WAITS ON THE OPERATOR ===\n")
    if not m:
        print("No standing-ask section in PLAN.md — nothing to raise.")
        return 0
    block = m.group(0)
    rows = [ln for ln in block.splitlines() if ln.startswith("| **#")]
    if not rows:
        print("Standing section carries NO open asks. Nothing waits on him.\n")
    else:
        print("Each row below must carry a PROOF column. Run the proof BEFORE raising it;")
        print("if the proof fails, the ask is answered — delete the row, do not mention it.\n")
        for r in rows:
            print("  " + r.strip())
    retired = [ln for ln in block.splitlines() if ln.strip().startswith("- **#")]
    if retired:
        print(f"\n--- retired as ANSWERED ({len(retired)}) — do NOT resurrect ---")
        for r in retired:
            print("  " + r.strip()[:150])
    ready, accruing, err = _gated_reviews_ready()

    if err:
        # An unreachable database must never render as "nothing waits on him". Loud, and it
        # changes the exit code so a caller cannot treat a blind run as a clean one.
        print("\n🔴 COULD NOT EVALUATE THE GATED REVIEWS — " + err)
        print("   Their state is UNKNOWN, which is NOT the same as not-ready. Re-run when prod")
        print("   is reachable BEFORE telling him nothing waits on him.")

    if ready:
        print("\n🔴 --- GATED REVIEWS NOW READY: MY WORK IS DUE, NOT HIS ANSWER ---")
        for line in ready:
            print("  " + line)

    print("\n--- gated reviews still accruing (NOT asks — their own predicate says so) ---")
    for line in accruing:
        print("  " + line)

    print("\nIf an item is not printed above, it is NOT open. Do not raise it.")
    return 2 if err else 0


if __name__ == "__main__":
    sys.exit(main())
