"""Throwaway audit (#256 W2): introspect ALL registered jobs and show exactly
what the EXECUTION partition would REMOVE — the completeness check combined mode
can't give (advisor 2026-06-13). Scan the REMOVED list for trade/stop-shaped ids;
an omission from EXECUTION_OWNED_JOB_IDS silently drops a safeguard at cutover.

No scheduler is actually started (.start patched to no-op) — pure introspection.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["SERVICE_ROLE"] = "combined"

from apscheduler.schedulers.asyncio import AsyncIOScheduler
AsyncIOScheduler.start = lambda self, *a, **k: None  # no-op: register only

# start_scheduler() fires asyncio.create_task() for boot coroutines (reap stale
# runs, boot marker) which need a running loop. We only want job *registration*,
# so neutralize create_task — close the coroutine to avoid "never awaited".
import asyncio
def _noop_create_task(coro, *a, **k):
    try:
        coro.close()
    except Exception:
        pass
    return None
asyncio.create_task = _noop_create_task

from agents.market_intelligence import scheduler as S

sched = S.start_scheduler()
all_ids = sorted(j.id for j in sched.get_jobs())

kept = [i for i in all_ids if S._job_belongs_to_role(i, "execution")]
removed = [i for i in all_ids if not S._job_belongs_to_role(i, "execution")]

SUS = ("stop", "order", "position", "reconcile", "trade", "fill", "entry",
       "exit", "orb", "equity", "stuck", "ack", "stream", "partial",
       "timestop", "time_stop", "9m", "allocator", "backstop", "extremes",
       "cleanup", "broker", "alpaca", "safeguard", "drawdown", "shadow")
flagged = [i for i in removed if any(s in i.lower() for s in SUS)]

print(f"TOTAL registered jobs: {len(all_ids)}")
print(f"\nKEPT in execution ({len(kept)}):")
for i in kept:
    print(f"  + {i}")
print(f"\nREMOVED from execution -> swept to intelligence ({len(removed)}):")
for i in removed:
    mark = "  [!]" if i in flagged else "     "
    print(f"{mark} {i}")
print(f"\n[!] REMOVED ids matching trade/stop/order-shaped keywords ({len(flagged)}):")
for i in flagged:
    print(f"  [!] {i}")

# Completeness: every registered id must be classified in one of the manifests
# (this is what the boot omission guard enforces in split roles).
unclassified = [
    i for i in all_ids
    if i not in S.EXECUTION_OWNED_JOB_IDS and i not in S.INTELLIGENCE_OWNED_JOB_IDS
]
print(f"\nUNCLASSIFIED (in neither manifest — omission guard would FAIL boot): "
      f"{len(unclassified)}")
for i in unclassified:
    print(f"  [X] {i}")
print("\nOK — every registered job is classified." if not unclassified
      else "\n*** FIX: add each [X] id to EXECUTION_OWNED or INTELLIGENCE_OWNED ***")
