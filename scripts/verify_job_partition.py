"""#256 W2 — static verifier for the scheduler job partition.

Checks the EXECUTION_OWNED_JOB_IDS set is well-formed and that the partition is
a clean disjoint cover, WITHOUT booting the scheduler (so it's deploy/CI-safe).
The live-registration reality is verified separately by the boot-time
`_apply_role_partition` fail-loud guards + the boot log of kept/removed ids.
Since #279 those boot guards are BIDIRECTIONAL in both split roles:
registered ⊆ classified (omission) AND EXECUTION_OWNED ⊆ registered
(stale/renamed partition entry). The registered set only exists at boot, so the
reverse direction can't be checked statically here — for an offline
real-registration check use scripts/probes/_w2_role_dryboot.py.

Usage: python scripts/verify_job_partition.py
Exit 0 = OK; non-zero = a partition definition problem.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    from agents.market_intelligence.scheduler import (
        EXECUTION_OWNED_JOB_IDS, INTELLIGENCE_OWNED_JOB_IDS, _job_belongs_to_role,
    )
    errors: list[str] = []

    # 1. Every execution-owned id is a non-empty string (a blank/None id would
    #    get a UUID at registration and be silently dropped in execution role).
    for jid in EXECUTION_OWNED_JOB_IDS:
        if not isinstance(jid, str) or not jid.strip():
            errors.append(f"execution-owned id is not a non-empty string: {jid!r}")

    # 1b. The two manifests must be DISJOINT — a shared id is ambiguous and would
    #     defeat the omission guard (it could be "classified" yet wrong-routed).
    overlap = EXECUTION_OWNED_JOB_IDS & INTELLIGENCE_OWNED_JOB_IDS
    if overlap:
        errors.append(f"execution/intelligence manifests overlap: {sorted(overlap)}")

    # 2. Disjoint cover: for any id, exactly one of {execution, intelligence}
    #    owns it, and combined owns everything.
    probe = set(EXECUTION_OWNED_JOB_IDS) | {
        "ep_scan", "theme_synthesis", "morning_briefing", "9m_ep_scan",
    }
    for jid in probe:
        in_exec = _job_belongs_to_role(jid, "execution")
        in_intel = _job_belongs_to_role(jid, "intelligence")
        if in_exec == in_intel:
            errors.append(
                f"id {jid!r} not cleanly partitioned: "
                f"execution={in_exec} intelligence={in_intel} (must differ)")
        if not _job_belongs_to_role(jid, "combined"):
            errors.append(f"id {jid!r} not owned by combined role")

    if errors:
        print("Job partition verify FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"Job partition verify — OK "
          f"({len(EXECUTION_OWNED_JOB_IDS)} execution-owned + "
          f"{len(INTELLIGENCE_OWNED_JOB_IDS)} intelligence-owned ids, "
          f"disjoint, clean cover).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
