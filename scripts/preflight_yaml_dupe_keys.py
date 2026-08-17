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
# `kind` is OPTIONAL (absent = accrual, today's behaviour) but a TYPO must not silently
# degrade a tripwire back into an age-ranked accrual item.
DOCUMENTED_KINDS = {"accrual", "tripwire", "cadence"}


def find_fanout_predicates(src: str) -> list:
    """Predicates that COUNT(*) across a JOIN on an INEQUALITY without DISTINCT — the shape that
    silently multiplies the count.

    Found 2026-08-04 in `rel_volume_large_cap_floor_evidence`: it joined `mi_stock_scores` on
    `score_date <= alert_date`, so every alert fanned out to EVERY prior score row. It returned
    **5710 where the true alert count was 100** — a 57x overstatement, and the review had been
    reading READY on it. A threshold means nothing if the number it gates is the wrong shape.

    Narrow on purpose: an equality join cannot fan out this way, and DISTINCT or LATERAL means the
    author has already handled it. Exactly one entry matched when this was written, and it was the
    live defect — the check is silent afterwards until someone writes the same shape again."""
    import re as _re
    import yaml as _yaml
    try:
        doc = _yaml.safe_load(src)
    except Exception:
        return []
    out = []
    for entry in (doc or {}).get("reviews") or []:
        if not isinstance(entry, dict) or entry.get("status") != "pending":
            continue
        pred = entry.get("predicate_sql") or ""
        if not pred.strip():
            continue
        if (_re.search(r"\bJOIN\b", pred, _re.I)
                and _re.search(r"\bON\b[^\n]*?(<=|>=|<|>)", pred, _re.I)
                and _re.search(r"COUNT\(\s*\*\s*\)", pred, _re.I)
                and not _re.search(r"DISTINCT|LATERAL", pred, _re.I)):
            out.append((entry.get("review_id", "<no id>"),
                        "COUNT(*) across a JOIN on an inequality with no DISTINCT/LATERAL — "
                        "this fans out and overstates the count"))
    return out


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
        if "kind" in entry and entry["kind"] not in DOCUMENTED_KINDS:
            out.append((rid, f"kind {entry['kind']!r} is not one of {sorted(DOCUMENTED_KINDS)} "
                             f"— a typo here silently re-ranks a tripwire as a stale accrual item"))
    return out


# ── readiness sanity check, informational only (#517, 2026-08-17) ────────────────────────────
# Reuses the pure (no-DB) detectors from data_gated_reviews.py so the definition lives in exactly
# one place. Deliberately NOT wired into the hard-fail exit code below: 17 of the 132 entries
# already registered flag on the population-mismatch rule (verified 2026-08-17 against prod
# information_schema.columns), and turning this into a hard gate today would block every commit
# on a backlog this task explicitly did not sign up to clear — see PLAN #517. Printed so a NEW
# entry with either shape is visible at `git commit` time, same posture as the fanout check
# above before it had a clean baseline to hard-fail from.
def find_readiness_sanity_flags(src: str) -> list[tuple[str, str]]:
    """(review_id, reason) for pending/deferred entries whose predicate is date-only or reads a
    table without filtering a column that separates different questions. Info-only — printed,
    never fails the commit."""
    import yaml as _yaml
    try:
        doc = _yaml.safe_load(src)
    except Exception:
        return []
    repo_root = str(Path(__file__).resolve().parent.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from agents.market_intelligence.data_gated_reviews import (
        is_date_fire_predicate, find_population_mismatch,
    )
    out = []
    for entry in (doc or {}).get("reviews") or []:
        if not isinstance(entry, dict) or entry.get("status") not in ("pending", "deferred"):
            continue
        rid = entry.get("review_id", "<no id>")
        sql = entry.get("predicate_sql")
        if is_date_fire_predicate(sql):
            out.append((rid, "predicate has no FROM clause — calendar-only, not evidence-gated"))
        for tag in find_population_mismatch(sql):
            out.append((rid, f"reads {tag.split('.')[0]} without filtering {tag.split('.')[1]}"))
    return out


def main() -> int:
    if not REGISTRY.exists():
        print(f"YAML lint: registry not found at {REGISTRY}", file=sys.stderr)
        return 2
    src = REGISTRY.read_text(encoding="utf-8")
    issues = find_duplicate_keys(src)
    status_issues = find_status_problems(src) + find_fanout_predicates(src)
    sanity_flags = find_readiness_sanity_flags(src)
    if sanity_flags:
        print(f"YAML lint INFO: {len(sanity_flags)} readiness-sanity flag(s) — not a commit "
              f"blocker, see #517 in PLAN.md:")
        for rid, reason in sanity_flags:
            print(f"  {rid}: {reason}")
        print()
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
