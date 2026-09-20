# Should the shared DB pool get a default acquire timeout? — the fork, one page (2026-09-20, #672)

**Decision requested: none yet — this is the operator's call.** Written because the coordinator asked for
the fork to be laid out rather than decided. Nothing in this document changed code; `db.py:154` is untouched.

## The decision it serves

Whether the shared asyncpg pool (`agents/market_intelligence/db.py::get_pool`, `max_size=5`, no acquire
timeout) should fail a starved caller after a bound instead of letting it wait forever. His words on the
outcome: *"i want a real fix, no more missed jobs or telegrams"* (2026-09-20). ⚖ **THE LINE:** the pool
serves the ORDER PATH, so any timeout changes how an entry or a stop-placement FAILS. That is his call;
nothing here was flipped.

## Method — population and how it was derived

- **Acquire sites:** every `acquire(` in `agents/ core/ shared/ channels/` on this branch, counted by grep
  (745 total; 324 inside `db.py`; 15 carrying an explicit `timeout=`), 2026-09-20. No era filter — the
  question is about the code as it stands.
- **Order-path subset:** the files under `agents/market_intelligence/broker/` plus
  `execution_routes.py`, i.e. what `EXECUTION_OWNED_JOB_IDS` and the entry pipeline run — the same
  ownership map `scripts/deploy.sh` uses, not a hand list.
- **Job durations:** `mi_job_runs`, `status='success'`, last 60 days to 2026-09-20 (read-only via
  `psql` on prod), max and p95 per `job_id`, to bound the false-timeout risk of a default.
- **The incident itself:** `mi_job_runs` rows 2026-09-18 19:00Z → 2026-09-19 06:00Z, exported once to a
  file (`tests/fixtures/672_mi_job_runs_2026-09-16_to_09-20.csv` holds the daily-job subset).

## What is already true after 2026-09-19

- The exact 09-18 deadlock — a `db.py` function asking the pool for a SECOND connection while holding one —
  is **impossible**, not survivable: `tests/test_no_nested_pool_acquire.py` fails the build on any such
  call across all 408 top-level functions in `db.py` (transitive closure, no allowlist).
- The nightly pull carries a 45-minute hard cap; a skipped job is now recorded and paged; and (this task)
  every missed daily intelligence job is **re-run from the ledger** at boot and every 30 minutes, date
  pinned to the slot it missed. So the *consequence* of a stall — a lost evening — is closed regardless
  of what is decided here.

## What the gate does NOT cover — the residual hang classes

| Class | Can it still exhaust the 5-connection pool? | Would an acquire timeout help? |
|---|---|---|
| Nested acquire **outside `db.py`** — a module holding a `conn` and calling a `db.py` acquirer | Yes. The gate scans `db.py` only; **≈420 acquire sites live in other modules** (745 total − 324 in `db.py`). | Yes — same shape as 09-18. |
| A query that never returns (lock wait, network stall to Postgres, a runaway plan) | Yes — 5 such callers hold every connection forever. | Not this one: it needs a **query** bound (`command_timeout`), the instrument the coordinator's brief and the 09-19 note both rejected for the order path. |
| Five legitimately long batch writers overlapping | Yes for their duration (the `executemany` nightly writers, some thousands of rows). | Yes, but a short timeout would **fail healthy jobs** — this is why the number is not obvious. |

## The blast radius of a pool-wide default, derived

- **745 `pool.acquire(` sites** under `agents/ core/ shared/ channels/`; **15 already pass a `timeout=`**
  (7 in `broker/order_manager.py` at `_REPROTECT_DB_TIMEOUT = 5.0` since #621, 2 in `db.py`, 1 in
  `health_checks.py`; the rest of the 15 are the same three files). Those 15 keep their own value under any
  default — a default only changes the **730 that pass nothing**.
- **On the order path** (money): `broker/entry_pipeline.py`, `broker/order_manager.py` (the 7 unbounded
  ones), `broker/live_tracker.py`, `broker/trade_state.py`, `execution_routes.py`. Today an unbounded one
  **hangs forever** if the pool is starved — no stop placed, no alert, and the job's own Telegram never
  fires because `audit_wrap` cannot write its start row either. With a timeout it **raises**, and every
  terminal failure in the entry pipeline Telegrams via `humanize()`. That is almost certainly the safer
  failure — but it is a change to how the money path fails, which is THE LINE.
- **Normal-load risk of a false timeout:** a healthy `acquire()` waits milliseconds; the longest observed
  successful jobs (60-day ledger: `crypto_category_refresh` 69 min, `delayed_entry_shadow` 50 min,
  `analyst_estimates_snapshot` 40 min) hold connections for stretches but never queue behind five others.
  There is no wait-time telemetry to size it from — `asyncpg` does not expose queue depth, and nothing
  records how long an acquire waited.

## The three options

1. **Leave it** (today). The one known deadlock is impossible; the residual classes are recovered by the
   sweep after the fact rather than prevented. Cost: a stall still loses the evening until a restart;
   the next one will be diagnosed from `mi_job_runs` only, as this one was.
2. **Generous default acquire timeout, everywhere** — e.g. 120 s, applied only where a caller passes
   nothing, via a `Pool` subclass in `get_pool()`. A starved job fails in 2 minutes with a real
   `TimeoutError` → `audit_wrap` records `failed`, pages once per job per hour, the sweep re-runs it once
   the pool frees; and a nested-acquire deadlock **self-resolves** in 120 s because the inner waiters
   raise and release. Changes the money path's failure from hang to raise at 730 sites in one line.
   **Needs sign-off** (THE LINE), and a first-week watch for false timeouts on the nightly writers.
3. **Extend the static gate to every module** instead of a timeout. Zero runtime risk; makes the nested
   class impossible everywhere; does nothing for the lock/network class. ~420 more sites to scan, same
   AST approach, one afternoon.

## Recommendation (one line)

**Do (3) now — it is free and closes the class that actually happened — and put (2) to the operator with the
number 120 s and the 730-site blast radius stated above; not on my authority.**

## What this does not answer

- **How long a healthy acquire actually waits under the nightly load.** Nothing records it — asyncpg
  exposes no queue depth and `mi_job_runs` stores job durations, not connection waits. "120 s" is an
  argument from the millisecond norm, not a measurement; a week of wait-time telemetry would make it one.
- **Whether a slow-query stall has ever happened here.** The 60-day ledger shows the nested-acquire
  deadlock once (09-18) and no confirmed lock/network stall; the residual classes are plausible, not
  observed.
- **The orchestrator's own pool** (`core/memory.py`, `max_size=10`) — a separate process and container,
  not counted in the 745 and not part of this fork.
- **What the money path should DO on a raised timeout** — page and stop, or retry — that is entry-pipeline
  design and needs the operator, not a pool constant.
