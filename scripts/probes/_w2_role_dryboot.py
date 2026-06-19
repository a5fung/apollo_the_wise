"""Throwaway (#256 W2): dry-boot start_scheduler() in a given SERVICE_ROLE and
report the partition outcome against REAL registration — the path combined-mode
verification + the synthetic _FakeScheduler unit tests never exercise (advisor
6/13). Patches scheduler .start + asyncio.create_task to no-ops so only job
registration + _apply_role_partition run.

Usage: SERVICE_ROLE=execution python scripts/_w2_role_dryboot.py
       (or pass the role as argv[1])
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

role = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SERVICE_ROLE", "combined")
os.environ["SERVICE_ROLE"] = role
# intelligence+http coherence isn't asserted here (we only call start_scheduler,
# not assert_service_role_coherent), but set a URL so nothing trips if it is.
os.environ.setdefault("EXECUTION_SERVICE_URL", "http://apollo-execution:8006")

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
AsyncIOScheduler.start = lambda self, *a, **k: None  # no-op: register only


def _noop_create_task(coro, *a, **k):
    try:
        coro.close()
    except Exception:
        pass
    return None


asyncio.create_task = _noop_create_task

from agents.market_intelligence import scheduler as S
from agents.market_intelligence import constants as C

print(f"SERVICE_ROLE={C.SERVICE_ROLE} runs_execution={C.runs_execution_jobs()} "
      f"runs_intelligence={C.runs_intelligence_jobs()}")

try:
    sched = S.start_scheduler()
except Exception as e:
    print(f"  [X] start_scheduler RAISED ({type(e).__name__}): {e}")
    sys.exit(1)

ids = sorted(j.id for j in sched.get_jobs())
exec_owned = [i for i in ids if i in S.EXECUTION_OWNED_JOB_IDS]
print(f"  start_scheduler OK -> {len(ids)} jobs survive the partition")
print(f"  (execution-owned among them: {len(exec_owned)})")
