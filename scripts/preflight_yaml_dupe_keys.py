#!/usr/bin/env python3
"""Detect duplicate keys within review entries in data_gated_reviews.yaml.

YAML "last wins" semantics mean a duplicate `status` or `earliest_review_date`
silently overwrites the correct value — surfaces as the wrong status in the
weekly digest. Caught 2026-05-24: theme_assignment_sndk_class_refinement
had `status: done` + `closed_on: 2026-05-18` AND a stray `status: pending`
50 lines later. Parser saw `pending`, surfaced in this week's "Reviews ready."

Exits non-zero (and prints offenders) if any review entry has any duplicate
top-level key. Wire into scripts/deploy.sh preflight chain.
"""
import re
import sys
from pathlib import Path

REGISTRY = Path(__file__).resolve().parent.parent / "data_gated_reviews.yaml"


def find_duplicate_keys(src: str) -> list[tuple[str, dict[str, int]]]:
    """Return list of (review_id, {key: count}) for entries with dupes."""
    entries = src.split("  - review_id:")
    out: list[tuple[str, dict[str, int]]] = []
    for body in entries[1:]:
        body = "  - review_id:" + body
        rid_match = re.search(r"review_id:\s*(\S+)", body)
        rid = rid_match.group(1) if rid_match else "?"
        keys_seen: dict[str, int] = {}
        for line in body.split("\n"):
            m = re.match(r"^    ([a-z_]+):\s*\S", line)
            if m:
                keys_seen[m.group(1)] = keys_seen.get(m.group(1), 0) + 1
        dups = {k: v for k, v in keys_seen.items() if v > 1}
        if dups:
            out.append((rid, dups))
    return out


# ── status-vocabulary check (added 2026-08-03) ────────────────────────────────────────────────
# The renderer surfaces an entry ONLY when `status in ("pending", "deferred")`
# (data_gated_reviews.py). Anything else is skipped silently -- which is correct for `done`, and a
# TRAP for anything the schema does not define. Found on 2026-08-03: six entries used off-schema
# words (`closed` x3, `shipped`, `resolved` x2) and one carried NO status key at all. All seven were
# genuinely finished, so nothing was lost this time -- but the same omission on a LIVE question
# would hide it from every Sunday surface, forever, with nothing failing.
#
# Deliberately narrow: it checks membership in the documented vocabulary and nothing else. It does
# NOT judge whether a status is the RIGHT one -- that is triage, and a gate cannot do it.
DOCUMENTED_STATUSES = {"pending", "done", "deferred"}


def find_status_problems(src: str) -> list:
    """(review_id, problem) for entries whose status is missing or off-vocabulary."""
    import yaml
    try:
        doc = yaml.safe_load(src)
    except Exception as e:                      # a parse failure is the dupe-key check's job
        return [("<parse>", f"could not parse: {e}")]
    out = []
    for entry in (doc or {}).get("reviews") or []:
        if not isinstance(entry, dict):
            continue
        rid = entry.get("review_id", "<no review_id>")
        if "status" not in entry:
            out.append((rid, "NO status key — the renderer will skip it silently"))
        elif entry["status"] not in DOCUMENTED_STATUSES:
            out.append((rid, f"status {entry['status']!r} is not one of "
                             f"{sorted(DOCUMENTED_STATUSES)}"))
    return out


def main() -> int:
    if not REGISTRY.exists():
        print(f"YAML lint: registry not found at {REGISTRY}", file=sys.stderr)
        return 2
    src = REGISTRY.read_text(encoding="utf-8")
    issues = find_duplicate_keys(src)
    status_issues = find_status_problems(src)
    if status_issues:
        print(f"YAML lint FAILED: {len(status_issues)} entry(ies) with a missing/off-schema status.")
        print("The renderer surfaces ONLY status in (pending, deferred) — anything else is skipped")
        print("SILENTLY, so an off-schema status hides a live question with nothing failing.\n")
        for rid, prob in status_issues:
            print(f"  {rid}: {prob}")
        return 1
    if not issues:
        print(f"YAML lint: 0 entries with duplicate keys, "
              f"all statuses in {sorted(DOCUMENTED_STATUSES)} (registry clean).")
        return 0
    print(f"YAML lint FAILED: {len(issues)} entries with duplicate top-level keys.")
    print("Duplicate keys silently overwrite earlier values (YAML last-wins).")
    print("Fix by removing redundant key lines, then re-run.\n")
    for rid, dups in issues:
        print(f"  {rid}: {dups}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
