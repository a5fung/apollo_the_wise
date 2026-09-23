# FL-4 / #184b — live_r1 promotion criterion: PROPOSAL (operator signs)

**Status: PROPOSAL ONLY — nothing changed.** The gate in `data_gated_reviews.yaml`
(`broker_order_ingest_promotion`, earliest 7/25) and the ingest itself are untouched. This is a
shadow→live promotion criterion = operator authority (THE LINE + CHANGE_PROCESS). Companion to the
YELLOW-3 meter fix (`v1_readiness_redteam_2026-07-12.md`): `compute_fl4` now honestly gates the
quiet-day clock on live_r1 promotion, which makes THIS criterion the binding constraint on the
declare date.

## 1. The problem — the current criterion is unsatisfiable by a healthy system

Current gate: dry_run → **"≥3 clean R1 dry-run proposals"** (from the LIVE book) → sign `live_r1`.

R1 proposals fire only on real stop-pointer drift (the a41e7c6a false-naked class) — exactly the
drift the last month of hardening exists to prevent (stop-ack watchdog, 15-min order-status
reconcile, T1.5a single-writer pointer discipline, WS/DB/REST triple-check). A healthy system
produces these at rate ≈ 0. The expected wait for N=3 organic events is unbounded; **zero proposals
is the SUCCESS state, but the gate reads it as missing evidence.** With the meter now honest, FL-4
green — and the v1.0 declare — waits on a bug we've engineered out of existence.

## 2. What already proves the R1 path works

- **`scripts/_184b_ingest_paper_exercise.py`** (#151 discipline; exists, run PASS 2026-07-11 per
  the review entry). It drives the PRODUCTION `run_ingest` path against the REAL paper-Alpaca book:
  places a real SELL stop, fabricates the false-naked DB state (`stop_order_id=NULL`), asserts
  `live_r1` repoints the pointer to the real broker order id, then asserts `dry_run` writes NOTHING.
- Unit suite (spec §6): COID truth table, no-overwrite, per-cycle cap, foreign-COID never proposed,
  dedup.
- **Structural fact that bounds the paper→live delta:** R1's live mutation writes ONLY our DB
  (`order_manager.set_stop_order_id` with a no-overwrite guard + `mi_live_orders` upsert). It never
  writes to the broker. The only live-account-specific surface is the READ side — which the
  detection half already exercises against the live book every 15 minutes since 7/5.

## 3. Proposed criterion (exact wording)

Sign `live_r1` when BOTH legs hold:

**(a) Repair-path leg (positive evidence): 3 clean synthetic R1 repairs via the paper exercise.**
Three distinct PASS runs of `_184b_ingest_paper_exercise.py` (real paper-Alpaca orders through the
production `run_ingest` code path), each leaving its `ingest_reconstructed` audit row.
*Recommended:* at least one run exercises the **dead-pointer variant** (DB pointer set to a
canceled order id, not NULL — the second R1 candidate shape from spec §2). That's a ~10-line
extension to the exercise script; if the operator prefers zero new code, 3 NULL-pointer runs still
prove the repair path (the dead-pointer branch stays covered by unit tests only — name it at
sign-off).

**(b) Healthy-book leg (negative evidence): ≥5 consecutive trading days at `dry_run` in production
with zero WRONG proposals.** Any R1/R2/R3i proposal that fires in the window must be
operator-reviewed correct; **zero-proposal days count as clean** — that is the healthy state this
leg exists to confirm, not missing evidence. Any wrong proposal → do NOT enable; investigate
(unchanged from the current gate).

R2/R3i stay dry-run — this proposal touches the R1 tier only.

## 4. Why this is satisfiable yet still meaningful

The original criterion conflated two things: *prove the repair executes correctly* and *wait for a
real bug to occur*. Leg (a) delivers the first through the exact production path
(`run_ingest → _handle_r1 → validate_coid → order_manager.set_stop_order_id → _upsert_stop_order`)
against a real broker book — everything a live R1 would do except which account's book it reads.
Leg (b) delivers what live evidence would actually have added: specificity on the real book at the
real cadence (no false proposals, dedup holds, caps hold). Neither leg requires a real incident;
together they prove repair-works AND doesn't-fire-when-it-shouldn't.

## 5. Evidence artifacts at sign-off

1. 3× exercise PASS output + `mi_audit_log` rows: `event_type='ingest_reconstructed' AND summary
   LIKE 'ingest|paper|r1|%'`.
2. Dry-run window review: `SELECT * FROM mi_audit_log WHERE event_type IN ('ingest_proposed',
   'ingest_rejected','ingest_error') AND created_at >= <window start>` — each row reviewed, zero
   wrong (empty set = clean).
3. CHANGE_PROCESS entry + ADR 0008 build-status update at the flip (spec §7, unchanged).
4. Flip SQL — **must set `last_transition_at`** (the review's current UPDATE recipe bumps only
   `updated_at`; the honest FL-4 meter reads `GREATEST(last_transition_at, updated_at)` so it can't
   over-credit either way, but keep the row semantically right):
   ```sql
   INSERT INTO mi_safeguard_state (safeguard, account_mode, state, last_transition_at, updated_at)
   VALUES ('broker_order_ingest','global','live_r1',NOW(),NOW())
   ON CONFLICT (safeguard, account_mode)
   DO UPDATE SET state='live_r1', last_transition_at=NOW(), updated_at=NOW();
   ```

## 6. Residual risk (named)

1. **First ORGANIC live R1 unobserved at flip** — inherent to any criterion that doesn't wait for a
   real bug. Bounded by: DB-only write, no-overwrite guard, PER_CYCLE_CAP=2, real-time Telegram per
   mutation, instant kill (toggle back to `dry_run`). Spec §7's VERIFY-LIVE clause stays: the next
   organic R1 event (if ever) is the ambient verify.
2. **Live-account read differences** (creds/order shapes) — mitigated: detection reads the live
   book every 15 min since 7/5; ingest reuses the same already-fetched reads.
3. **Synthetic ≠ every drift shape** — the NULL-pointer case is exercised end-to-end; the
   dead-pointer case only if the variant run is included (rec: include it).

## 7. Alternatives considered

- **(i) Status quo** — wait for organic drift: unbounded FL-4/declare slip; the gate rewards the
  system for being broken. Rejected.
- **(ii) Sign on the existing 7/11 exercise alone** (no dry_run soak): drops the healthy-book
  specificity leg. Weaker; not recommended.
- **(iii) Inject synthetic drift into the LIVE account** to generate "real" proposals: manufactures
  trade-state corruption on the live book to satisfy a meter. Rejected outright (THE LINE).

**Rec (1 line): adopt (a)+(b) — 3 paper-exercise R1 repairs (≥1 dead-pointer variant) + 5 clean
dry_run trading days = sign live_r1.**

## 8. Timeline if adopted (the declare-date math)

Flip `dry_run` Mon 7/13 → leg (b) window 7/13–7/17 (exercise runs for leg (a) any day in parallel)
→ sign `live_r1` EOD Fri 7/17 → honest FL-4 credits from Mon 7/20 → **FL-4 green EOD Fri 7/24** —
matching the redteam's date-honesty finding (earliest internally-consistent declare 7/24, not
7/22). Requires pulling the review's `earliest_review_date` 7/25 → 7/17 (operator edit of
`data_gated_reviews.yaml`, not made here).
