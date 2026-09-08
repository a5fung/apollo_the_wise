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
    """Asks that carry a real predicate live in data_gated_reviews.yaml. A review that is
    not READY is not an ask — its own gate says so, and overriding that by hand is the
    2026-09-08 #594 mistake."""
    try:
        import yaml
    except ImportError:
        return ["(pyyaml missing — cannot read the gated reviews)"]
    d = yaml.safe_load((REPO / "data_gated_reviews.yaml").read_text())
    out = []
    for r in d.get("reviews", []):
        if r.get("status") != "pending":
            continue
        if not str(r.get("action_when_ready", "")).lower().count("operator"):
            continue
        out.append(f"{r['review_id']}: gated — earliest {r.get('earliest_review_date')}, "
                   f"threshold {r.get('threshold')}. NOT an ask until its own predicate says READY.")
    return out


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
    print("\n--- gated reviews that will become asks on their own schedule ---")
    for line in _gated_reviews_ready():
        print("  " + line)
    print("\nIf an item is not printed above, it is NOT open. Do not raise it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
