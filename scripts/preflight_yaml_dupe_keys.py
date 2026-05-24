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


def main() -> int:
    if not REGISTRY.exists():
        print(f"YAML lint: registry not found at {REGISTRY}", file=sys.stderr)
        return 2
    src = REGISTRY.read_text(encoding="utf-8")
    issues = find_duplicate_keys(src)
    if not issues:
        print(f"YAML lint: 0 entries with duplicate keys (registry clean).")
        return 0
    print(f"YAML lint FAILED: {len(issues)} entries with duplicate top-level keys.")
    print("Duplicate keys silently overwrite earlier values (YAML last-wins).")
    print("Fix by removing redundant key lines, then re-run.\n")
    for rid, dups in issues:
        print(f"  {rid}: {dups}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
