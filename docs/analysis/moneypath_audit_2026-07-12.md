# Money-path adversarial audit — verified findings register (Block 4 T2, Fable, 2026-07-12)

**Method:** 5 parallel finder lenses (race/concurrency · partial-fill/replace-atomicity · status
state-machine · dual-account/kill-switch · silent-failure) over the real-$ spine, then EVERY
candidate adversarially verified by hand against the code (and prod schema, read-only) — 23
candidates → **8 verified findings + 3 minors**; 7 rejected as false/known; the strong defenses
confirmed are listed too (an audit that only lists holes misrepresents the posture). **Fixes are
operator-gated cards — nothing was hot-patched.**

---

## Verified findings (ranked)

### R1 · HIGH (active) — fill finalizers are lock-free read-modify-writes; the #151 advisory lock doesn't cover them
`finalize_partial_exit` (order_manager:1857) · `finalize_full_exit` (:1998) · `finalize_stop_fill`
(:2071) and the WS stop-close block (trade_stream:~904-921) all do bare
`SELECT * → mutate exits/remaining_shares/total_pnl in memory → UPDATE`, with **no
`_trade_advisory_lock` and no WHERE-status guard** — while the job-side writers
(`execute_partial_exit`/stop-replace, :1285-1294) DO hold the lock. The lock therefore serializes
job-vs-job only. Finalizers are called ONLY from the sequential WS handler (verified: trade_stream
:485-496, :587-603 — so finalizer-vs-finalizer races die), but **WS-finalizer vs job-writer
interleaving at DB awaits is real**: a finalize racing `update_open_positions_live` /
`sync_positions` / `update_stop` on the same trade can lose an exits[] append, clobber
`remaining_shares`, or double-append `running_closes` (the 3:45-partial vs 4:45-EOD window).
Also: the `status='filled'` write at trade_stream:772 is `WHERE id=$1` only (a concurrent
terminalize could be resurrected).
**Fix (one careful session):** take the EXISTING `_trade_advisory_lock(trade_id)` inside all
three finalizers + the WS stop-close; add `AND status='filling'`-style guards on
transitional→terminal writes. Mechanism already exists; this is coverage, not new machinery.

### R2 · HIGH (latent — a HARD precondition, not an active bug) — day-1 re-entry bypasses the kill switches
`attempt_day1_reentry` (order_manager:567-600) places real orders with **no
`LIVE_TRADING_ENABLED` check and no `/pause` halt check** (contrast `submit_entry`, which checks
both). Trigger path: WS stop-fill → re-entry, no gate. **Currently harmless**:
`R3_DAY1_REENTRY_ENABLED` defaults `false` (:472). **The precondition: R3 must NEVER be enabled
until this path checks the halt + kill switch** (ideally routes through `_check_safeguards`).
Recorded here + on the fix card; the 0029/#414 bracket-mechanics work touches this file and must
honor it.

### R3 · HIGH (latent, chronic) — every alpaca-py SDK call is synchronous inside async code
`get_account()`, `get_order()`, `place_bracket_order()` etc. are bare sync SDK calls in
`async def`s — zero `to_thread`/`run_in_executor` in alpaca_client.py (verified). A slow/hung
Alpaca endpoint doesn't stall one task — **it blocks the entire event loop**: WS fill processing,
every scheduled job, the reconcile safety net. Default SDK timeout unverified (possibly
unbounded). Long-standing (live since day 1) — a hazard class, not an active bug.
**Fix:** wrap money-path SDK calls in `asyncio.to_thread` + explicit `asyncio.wait_for` budgets
(or adopt the SDK's async client if available). Medium refactor; its own card.

### R4 · MEDIUM — the same-day dedup is cross-mode at the SCHEMA level (paper can suppress live)
`mi_live_trades_ticker_alert_date_key = UNIQUE (ticker, alert_date)` — **no account_mode**
(verified on prod pg_indexes). Entry INSERT is `ON CONFLICT (ticker, alert_date) DO NOTHING`
(entry_pipeline:442) and the pre-checks (:292, :315) also lack mode filters. A PAPER 9M-Day-2 row
on ticker X blocks a LIVE magna53 entry on X the same day (or vice versa, timing-dependent) —
fail-safe direction (skip, never a double-order) but a silently missed REAL entry with a
misleading `window:duplicate` skip reason. Overlap is plausible: a 9M day is often an EP day.
**Fix:** migrate the unique key to `(ticker, alert_date, account_mode)` + mode-filter the two
pre-checks. Schema migration on the live table — careful path, its own card.

### R5 · MEDIUM — `stop_processing` has no watchdog; transitional states lack a janitor
A `filling` watchdog EXISTS (scheduler:1394 — alert-only, >2 min). `stop_processing`
(trade_stream:561 claim) has **no equivalent**: a crash inside `_process_stop_fill` strands the
row forever, invisible to reconciliation (which keys on other statuses). The #436(b) self-heal
design covered `pending_confirmation/confirmed/submitting` — `filling`/`stop_processing` are new
transitional states outside its table.
**Fix:** extend the watchdog to `stop_processing` + fold both transitional states into the
#436(b) janitor (broker-confirmed state resolution, never blind).

### R6 · MEDIUM — `check_fills` lacks the stop-leg REST-refetch fallback its siblings have
`submit_entry` (:258-265) and `_process_entry_fill` refetch when `extract_stop_leg_id` returns
None; `check_fills` (:354, :374) writes `COALESCE(NULL, stop_order_id)` — a no-op — with no
refetch (verified). A polling-detected fill whose order payload omits legs leaves the pointer
NULL until reconcile/ingest-R1 repairs it; meanwhile coverage remediation may fire on a
false-naked read (defended by `_ensure_stop_coverage`'s open-orders dedupe, so the cost is noise
+ window, not a duplicate stop). **Fix:** copy the 3-line fallback. Trivial card.

### R7 · MED-LOW — non-terminal partial stop fills leave `remaining_shares` stale until the daily qty-sync
trade_stream:468-470: only a TERMINAL partial (cum ≥ total) finalizes; earlier ticks are
visibility-only, so DB `remaining_shares` diverges from the broker until the daily sync. Any
intraday sizing read in that window uses the stale value. Bounded by the qty-sync; note-grade
fix rides the R1 session (finalize partial-tick deltas under the same lock, or accept + document).

### R8 · LOW (defense-in-depth) — WS cancel/reject order-update lacks a mode filter
trade_stream:1067-1072 updates `mi_live_orders` by `alpaca_order_id` alone. Alpaca UUIDs make
cross-account collision negligible; still a one-line JOIN-filter tightening when that file is
next open.

### Minors (recorded, no cards)
- `_persist_first_bar` fire-and-forget failure is log-only (no audit row) — analytics-side.
- The partial-exit abort re-protect failure message says "deferred — sync cron will reconcile"
  even when the broker read itself failed (the cron may fail the same way) — wording tightening.
- `attempt_day1_reentry`'s combined status+stop_order_id UPDATE is CAS-free (gate-clean since
  it's not a solo write; noted for the R1 session).

## Rejected after verification (candidates that did NOT survive)
- "Duplicate stop after replace-reject + verify-timeout" — `_ensure_stop_coverage` is
  dedupe-by-design (discovers live stops via `get_open_orders`, never the stale pointer); the
  path degrades to the known NULL-pointer-until-reconcile class.
- "Unprotected Telegram raise on terminal entry failure (CRITICAL)" — false premise:
  `send_telegram_message` returns False, never raises (contract); the audit row fires.
- "Re-entry ambiguous-accept untracked order" — documented residual; #184(b) ingest R2 is the
  designed catcher (dry-run pending).
- "WS-vs-polling double finalize" — finalizers are WS-only (verified callers); premise dead.
- "F22 breakeven sibling" — the finder self-retracted (the SQL-side monotonic OR is safe).
- "Boot race pool-vs-stream" — events block politely on pool init; no loss mechanism shown.
- "'confirmed' strands" — already the #436(b) scope.

## Defenses CONFIRMED strong (verified, worth knowing)
COID discipline at every submission site · cross-account event rejection before mutation ·
account_mode threading on all order paths · kill-switch coverage on the ENTRY path (submit +
safeguards) · replace-verify-before-sell (Step 1b) · `_ensure_stop_coverage` exactly-one-stop
semantics · flat-position mass-close guard in sync_positions · the 10:00 cleanup status gate ·
`filling` watchdog · terminal states are one-way.

## Cards filed
- **#463** — R1+R5+R6+R7 bundle: finalizer lock coverage + transitional-state janitor/watchdog +
  the check_fills fallback (one careful #151 session; trade-state).
- **#464** — R3: sync-SDK-in-async → `to_thread` + explicit timeouts (money-path refactor).
- **#465** — R4: mode-scoped same-day dedup (schema migration + pre-check filters).
- R2 = a precondition line on #463 + honored by 0029/#414; R8 + minors ride whichever card next
  opens their file.
