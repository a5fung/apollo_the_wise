# #461 — Position-cap check→insert TOCTOU race: design (2026-07-18)

**Status: DESIGN ONLY — operator sign-off required before any build touches the live path.**
This touches the `max_concurrent_positions` SAFEGUARD (THE LINE). Per `docs/setups/CHANGE_PROCESS.md`,
this doc is the sign-off artifact; no code changes ship until the operator rules.

**Scope guarantee (THE LINE):** every option below only makes the EXISTING cap correct under
concurrency. Cap value (5), counting vocabulary (`db.OPEN_POSITION_STATUSES`), skip-reason
vocabulary (`block:max_positions`), per-mode isolation, and #436 semantics
(`pending_confirmation` excluded) are all UNCHANGED. §7 flags the one option that risks
behavior drift.

---

## 1. The race window (file:line-anchored)

The entry pipeline (`agents/market_intelligence/broker/entry_pipeline.py::submit_trade_entry`)
checks the cap and inserts the position row in two separate, non-transactional DB round-trips.
(The in-code step labels are `# 2. Safeguards` and `# 6. Insert trade row`; PLAN.md's #461 line
calls them "STEP 4 → STEP 6" — same two points.)

**Count read (check):**
- `entry_pipeline.py:376-378` — `await _check_safeguards(account_mode=_safeguard_mode, signal_type=signal_type)`
- `agents/market_intelligence/broker/live_tracker.py:121-124` — the per-mode open count:
  `SELECT COUNT(*) FROM mi_live_trades WHERE status = ANY($2) AND account_mode = $1`
  compared at `live_tracker.py:125` against `MAX_CONCURRENT_LIVE_POSITIONS` (=5, `constants.py:260`).
- `live_tracker.py:144-148` — the per-strategy count (#65, `strat_cap`) has the IDENTICAL
  TOCTOU shape and must be covered by the same fix.

**Insert (use):**
- `entry_pipeline.py:472-495` — `INSERT INTO mi_live_trades ... status='pending_confirmation' ... ON CONFLICT (ticker, alert_date) DO NOTHING`.
- Crucially, the inserted row does **not yet count** against the cap:
  `db.OPEN_POSITION_STATUSES = ('filled','order_placed','confirmed')` (`db.py:4576`, #436 fork B).
  The row becomes countable only at the auto-enter confirm flip
  `entry_pipeline.py:510-514` (`UPDATE ... SET status='confirmed' ... WHERE id=$1`), which runs
  in a **separate** `pool.acquire()` immediately after the insert (sub-ms gap — per the #436
  analysis this extension of the window is negligible relative to the seconds below).

**What sits between check and countability** (all `await` points where other tasks interleave):
- exposure-family shadow check (`entry_pipeline.py:387-391`) — DB + possible Telegram
- **bar fetch with retry** (`entry_pipeline.py:394` → `fetch_orb_bar_with_retry`, :64-93):
  up to 3 REST attempts with 2 × 10 s sleeps → up to ~20-30 s
- fade guard REST call (`entry_pipeline.py:411`)
- `spec_builder` (`entry_pipeline.py:417`) — Alpaca account-equity REST fetch for sizing

So the check→countable window is **hundreds of ms to ~30 s per candidate** — enormous in
event-loop terms. Any other candidate whose `_check_safeguards` runs inside that window counts
a stale total.

## 2. Are entries actually concurrent? YES — verified, not theoretical

PLAN.md #461 asked "assess likelihood first: if the 9:31 entries are dispatched sequentially,
document + close." They are **not** sequential:

- **MAGNA53:** `live_tracker.py:314-318` — deliberate per-alert concurrency
  (`sem = asyncio.Semaphore(5)`, comment: serial would stack past the 5-min cron on bar-retry
  mornings) and `live_tracker.py:376-378` — `await asyncio.gather(*(_process_alert(a) for a in alerts))`.
  Up to **5 `submit_trade_entry` calls in flight simultaneously**, each calling
  `_check_safeguards` then racing to insert. Caller: `live_tracker.py:360`.
- **9M Day 2:** `scheduler.py:4519-4524` — the same `Semaphore(5)` + gather fan-out
  (explicitly "mirrors MAGNA53 pattern"; the sequential loop was the TEAM 5/04 bug).
  Caller: `live_tracker.py:1095`. Currently short-circuited (strategy deprecated,
  `scheduler.py:4348-4355`) but the code path is preserved for re-promotion, and when both
  jobs ran they fired at 9:31 into the **same mode's cap** (the "MAGNA53-priority reserve"
  budget math at `scheduler.py:4428-4450` is advisory, read outside any lock — it does not
  close the race).
- **Cross-invocation:** the ORB monitor is triggered from three overlapping paths —
  bar_stream on first-bar close (`broker/bar_stream.py:277-278`), the 9:31 cron fallback
  (`scheduler.py:1005-1010`), and post-open new-HIGH inline (`scheduler.py:1001-1004`).
  Same-ticker overlap is deduped (duplicate check + `ON CONFLICT`), but **different tickers
  across overlapping invocations add more concurrent pipelines**.
- **Cross-process:** under `EXECUTION_MODE=http` (#256 W2 service split),
  `trigger_orb_entry` / `submit_9m_day2_trade` run in the apollo-execution service
  (`execution_client.py:67-72`). Process topology is not fixed — which is exactly the #151
  lesson (`order_manager.py:1165-1173`): an in-process lock is a no-op across the split.

**Likelihood + severity bound.** The race fires when (a) the open count is within
N-1 of the cap and (b) ≥2 candidates are in flight in the same mode. Both occur in production:
cap-adjacent states are real (4/5 live slots occupied 6/24–6/26; WULF nearly cap-blocked 7/6)
and multi-HIGH mornings are routine (the grouped-skip digest exists because of them). Worst
case is **not just +1**: with open_count=4 and 5 concurrent candidates all reading the count
during the first one's bar-fetch window, all 5 pass → up to **9 open positions (cap+4)** in
the worst alignment. Verdict: **fix, don't document-close.**

## 3. Candidate fixes

### (a) RECOMMENDED — atomic recount + insert(+confirm) in one transaction under a per-mode `pg_advisory_xact_lock` (double-checked locking)

Keep the existing STEP-2 `_check_safeguards` call untouched as the cheap early gate (it still
short-circuits obviously-blocked candidates before the expensive bar fetch — identical
operator-visible skip behavior). Add the **authoritative** check at insert time: wrap the
STEP-6 region in ONE transaction on ONE connection:

1. `SELECT pg_advisory_xact_lock($1, hashtext($2))` — namespace constant (new, distinct from
   `_TRADE_LOCK_NAMESPACE = 0x504152`), key = `account_mode`.
2. Re-run the per-mode count (byte-identical SQL to `live_tracker.py:121-124`) and, when the
   strategy row sets `max_concurrent_positions`, the per-strategy count
   (byte-identical to `live_tracker.py:144-148`).
3. If either cap is hit → exit the txn and return the existing `_skip(...)` blocked path with
   the **exact same reason format** (`block:max_positions: N/5 (mode=x)`), so the ledger's
   `cap_blocked` mapping and the #197 CAP+1 alert (`entry_pipeline.py:292-304`, matches on
   `startswith(BLOCK_MAX_POSITIONS)`) work unchanged. Optionally emit a new observe-only
   audit event (`cap_recheck_blocked`) — this is also the verify-live signal.
4. Else: the existing INSERT (unchanged SQL, `ON CONFLICT DO NOTHING`); if the auto-enter
   branch applies (`_should_auto_enter` is computable pre-txn — inputs `account_mode` +
   `strategy.live_real_enabled` are already in scope), the `status='confirmed'` UPDATE
   (currently `entry_pipeline.py:510-514`) moves **inside the same transaction**.
5. Commit. The xact lock releases at transaction end, i.e. **after** the confirmed row is
   committed — the next waiter's recount necessarily sees it.

No external I/O inside the lock: the Alpaca submit (`submit_entry`, `entry_pipeline.py:515`)
stays after commit, exactly where it is today. Lock hold time = recount + insert + update =
single-digit ms.

- **Correctness under concurrency:** every code path that can add a countable row via the
  entry funnel serializes on the same per-mode lock; each waiter recounts committed state
  after the previous holder commits → at cap-1, exactly one of N racers is admitted. Holds
  across coroutines, overlapping triggers, AND processes (the lock lives in Postgres). The
  #151 real-PG test pattern (`tests/test_advisory_lock_real_pg.py`) already proves this
  mechanism's semantics in this codebase.
- **Per-account-mode isolation:** lock key is derived from `account_mode`
  (`hashtext('paper')` ≠ `hashtext('live')`) and both recounts already filter
  `account_mode = $1` — paper entries never serialize against (or count toward) live, and
  vice versa. #66 isolation fully preserved.
- **Deadlock risk:** none by construction — a single lock, acquired once, no nested lock
  acquisition inside the txn, xact-scoped (auto-releases on commit, rollback, error, or
  connection death; no unlock bookkeeping). It is never held together with the #151
  session-level trade lock (that one guards the exit path — partial vs reconciler — and a
  different namespace). Pool note: `db.py:122-124` pool `max_size=5` equals the Semaphore
  width; each contender holds its own connection while waiting, but the holder needs no
  second connection and finishes in ms, so waits are bounded and there is no circular wait.
- **Blast radius:** ~30 lines in `entry_pipeline.py` STEP 6 plus one small count helper
  (shared with `_check_safeguards` so the SQL cannot drift) — the single funnel both
  strategies already use. No schema change, no env change, no new failure mode on the hot
  path (a lock-wait is just a short delay; an error inside the txn rolls back and takes the
  existing crash-handling path).

### (b) Conditional insert (`INSERT … WHERE (SELECT COUNT(*) …) < cap`) / SERIALIZABLE

A plain conditional insert is **not correct under READ COMMITTED**: two concurrent
transactions each evaluate the count subquery against a snapshot that excludes the other's
uncommitted row — both pass, both insert (classic write-skew/phantom; locking a count cannot
be done with `FOR UPDATE`, since the rows that matter are the ones that don't exist yet).
Making it correct requires `SERIALIZABLE` + a 40001 retry loop on the live entry path — retry
machinery interleaved with the pipeline's crash handling, and a spurious serialization abort
on a legitimately-admittable entry becomes a missed entry unless retried carefully. It also
still needs the confirm flip inside the same transaction (the inserted `pending_confirmation`
row doesn't count — §1). Strictly more moving parts than (a) with no correctness advantage.
**Rejected.**

### (c) DB constraint / trigger (BEFORE INSERT OR UPDATE count-and-RAISE, or a slot-counter table)

A naive count-inside-trigger races identically (same phantom problem); the robust version
needs its own serialization (an advisory lock inside the trigger, or a per-mode counter row
whose UPDATE row-lock serializes) — i.e. option (a) relocated into the database, plus:
- **Cap value duplicated** into DDL/trigger — a second source of truth beside
  `constants.MAX_CONCURRENT_LIVE_POSITIONS`. Drift between them silently changes the
  effective cap: **this is the option that risks THE LINE** (§7).
- **Wide blast radius:** the trigger fires on every `mi_live_trades` write — fills, partials,
  closes, reconciler repairs, backfills, manual ops SQL — not just entries. A breach surfaces
  as an asyncpg exception wherever the write happened (e.g. the confirm UPDATE), taking the
  🚨 `orb_pipeline_crash` path instead of a clean `block:max_positions` skip, and could even
  block a reconciliation that is recording broker truth.
- Schema migration + rollback ceremony for what (a) does in pure code.
**Rejected.**

### (d) In-process `asyncio.Lock` — rejected outright

Closes only the single-process case. `EXECUTION_MODE=http` runs the entry paths in the
execution service; boot/cron/bar-stream overlap and any future topology change reopen the
race. #151 already paid for this lesson (`order_manager.py:1165-1173`). **Rejected.**

## 4. RECOMMENDATION

**Option (a):** per-`account_mode` `pg_advisory_xact_lock` + atomic recount-and-insert(+confirm)
at STEP 6, with the existing STEP-2 check kept as the early filter (double-checked locking).

**Why not hold the lock from check (STEP 2) through insert?** That would serialize every
candidate in a mode across the full bar-fetch window (up to ~30 s each) — re-creating the
TEAM 5/04 serial-stacking bug the gather exists to prevent, and pinning pool connections for
seconds. Check-early + recheck-at-insert keeps full pipeline concurrency and only serializes
the ms-scale critical section.

**Minimal safe change (sketch, ~30 lines, one file + one shared helper):**
- Extract the two count queries (`live_tracker.py:121-124`, :144-148) into one shared helper
  (e.g. `count_open_positions(conn, account_mode, signal_type=None)`) used by BOTH
  `_check_safeguards` and the new STEP-6 recheck — single SQL SoT, zero drift.
- In `submit_trade_entry` STEP 6: one `conn.transaction()` containing
  advisory-xact-lock → recheck(s) → existing INSERT → (auto-enter only) the confirm UPDATE.
  On recheck failure return the existing `_skip` blocked path with the unchanged
  `BLOCK_MAX_POSITIONS` / `BLOCK_STRATEGY_POSITION_CAP` reason formats + a
  `cap_recheck_blocked` audit event (observe-only telemetry of how often the race fires).
- New namespace constant beside the lock code, documented against `_TRADE_LOCK_NAMESPACE`.
- Nothing else moves: proposal path still inserts inert `pending_confirmation` (uncounted,
  #436 — correct: since #364 removed the confirm flow, a staged proposal can never become a
  position, so it cannot consume a slot at any point); Alpaca submit stays post-commit;
  skip/Telegram/ledger surfaces byte-identical.

**Out of scope (deliberate):** the other `_check_safeguards` gates (halt, daily loss,
breakers) are not check-then-insert races on `mi_live_trades` — re-evaluating them at
insert-time would CHANGE when they bind (THE-LINE-adjacent) and is not part of this fix.
Reconciler/backfill writes that record broker truth are also out of scope: the cap governs
what Apollo *submits*, not what the broker already holds.

## 5. Test plan — proving the race is closed

1. **Race-reproduction test (must fail pre-fix, pass post-fix).** Mocked Alpaca, real or
   fake pool: seed 4 countable rows in mode `live`; launch 3 concurrent
   `submit_trade_entry` calls whose mocked bar fetch blocks on a shared `asyncio.Event` so
   all three pass STEP 2 before any reaches STEP 6; release. Assert: exactly 1 row reaches
   `confirmed`, 2 return `ACTION_BLOCKED` with `block:max_positions`, final countable
   rows == 5. Run against the pre-fix code first to prove the test actually detects the
   overshoot (expect 7).
2. **Real-PG cross-connection serialization** — sibling of
   `tests/test_advisory_lock_real_pg.py` (APOLLO_TEST_DSN-gated, explicitly not mockable):
   conn A opens a txn, takes the cap lock for `live`, inserts a `confirmed` row; conn B
   blocks on the same key, then after A commits, B's recount sees A's row. Plus the
   isolation assertion: while A holds the `live` key, the `paper` key acquires immediately.
3. **Per-strategy cap variant of (1)** with `mi_strategies.max_concurrent_positions` set —
   proves the #65 recheck is covered by the same lock.
4. **Regression:** full `python -m pytest tests/ -q`; specifically
   `test_open_position_cap_excludes_proposals.py` (pending_confirmation still uncounted —
   #436 preserved) and `test_entry_auto_enter.py` (auto-enter truth table unchanged).
5. **Duplicate-conflict path:** two same-ticker calls → `ON CONFLICT` still yields the
   silent WINDOW_DUPLICATE return from inside the txn (no lock leak — xact scope).

## 6. Deploy / rollback

- **Process:** operator sign-off on this doc first (safeguard, THE LINE). Code +
  `docs/setups/safeguards.md` change-log entry in the SAME commit (SSoT rule).
- **Deploy:** `bash scripts/deploy.sh market-agent` (entry_pipeline/live_tracker/db are
  market-agent-owned; no channels/core files). No schema migration, no env var, no restart
  ordering concern. Preflight [5/7] already exercises `_check_safeguards` on the real path.
- **Verify-live:** (i) clean boot + preflight green; (ii) next multi-HIGH ORB morning shows
  normal entries (lock uncontended = no visible change); (iii) the race itself is only
  provable synthetically — the DoD "cap holds under a concurrent-entry simulation" is test
  (1)/(2) run against the prod-schema DB, plus zero `cap_recheck_blocked` anomalies. A
  fired `cap_recheck_blocked` event in prod is the fix working (it was a live race hit).
- **Rollback:** single `git revert` (pure code). Reverting reopens the pre-existing race —
  i.e. returns to today's status quo, never to something worse. Advisory xact locks leave no
  persistent state to clean up.

## 7. THE LINE — explicit compliance statement

This design changes **when the count is read** (a second, authoritative read at insert-time
under mutual exclusion), and nothing else:

- Cap VALUE unchanged (`MAX_CONCURRENT_LIVE_POSITIONS = 5`; per-strategy caps from
  `mi_strategies` unchanged).
- Counting vocabulary unchanged (`OPEN_POSITION_STATUSES`; #436 pending-confirmation
  exclusion preserved).
- Skip-reason vocabulary + formats unchanged (ledger `cap_blocked` mapping, #197 CAP+1
  alert intact).
- Per-mode isolation unchanged (per-mode lock keys, per-mode counts).
- The only observable difference: an entry that would previously have EXCEEDED the cap in
  the race window now receives `block:max_positions` — the cap enforcing what
  `safeguards.md` §3 already specifies.

**Flagged risk:** option (c) duplicates the cap value into the database — a second SoT whose
drift could silently change the effective cap (a behavior change without operator sign-off).
That risk is a reason it is rejected, not mitigated. Option (b) under SERIALIZABLE without a
careful retry loop could spuriously reject an admittable entry (also a behavior change).
Option (a) carries neither risk.

---
*Design produced 2026-07-18 for PLAN.md #461 (ETA 2026-07-19). No code changed. Refs: #436
fork B (`docs/analysis/436_phantom_root_cause_2026-07-11.md`), #151 advisory-lock precedent
(`order_manager.py:1165-1242`, `tests/test_advisory_lock_real_pg.py`), #66 dual-account
(`docs/architecture/dual_account.md`), safeguards SSoT (`docs/setups/safeguards.md` §3).*
