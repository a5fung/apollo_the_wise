# #184(b) — Broker-order ingest: execution-depth spec (Fable block 2, 2026-07-06)

**ADR 0008 increment 2(b)** — the a41e7c6a-class closer. Increment 2(a) (coverage-drift
DETECTION) is live since 7/5; this specs the MUTATION half: when the broker holds an
apollo-created order/position the DB doesn't track, reconstruct/repair the mirror so the gap
is structurally impossible to persist. **FL-4's DoD** (5 quiet drift days) rides on this.

**Authority model up front (THE LINE):** detection stays always-on; ingest MUTATES
`mi_live_trades`/`mi_live_orders` and ships DARK behind a runtime toggle, phased on per case
class below, each enable = operator sign-off after reviewing dry-run proposals. #151
discipline: exercised against real paper Alpaca before any enable.

---

## 1. The case classes (what coverage-drift detects → what ingest does)

| Class | Broker state | DB state | Ingest action | Risk tier |
|---|---|---|---|---|
| **R1 — stop-pointer repair** | live apollo-COID SELL stop for ticker T | open trade row for T with `stop_order_id` NULL or pointing at a dead order | Repoint `stop_order_id` (+ upsert the `mi_live_orders` row from the wire dict). **This is the a41e7c6a false-naked case itself** — DB thinks naked, broker is covered | LOWEST (one column, broker-confirmed; kills false-naked alarms + false remediation) |
| **R2 — untracked entry order** | live apollo-COID BUY stop-limit, unfilled | no open trade row | Reconstruct a minimal `mi_live_trades` row `status='order_placed'` + `mi_live_orders` row (fields §3) so the 10:00 cleanup / fill paths govern it normally | MEDIUM (row creation; wrong reconstruction = a ghost the cleanup then cancels — self-limiting) |
| **R3i — untracked position** | position for T (D1) + optionally its apollo stop | no open trade row | Reconstruct `status='filled'` row from position (qty/avg_entry) + attach the stop if present (else the existing naked-remediation places one) | HIGHEST (a filled row enters exit management; sizing/PnL fields must be right) |
| **Never** | foreign/manual COID (D2-INFO) | — | NEVER ingest — operator's manual trading is not ours to mirror. Unchanged INFO telemetry | — |

Phased enable: **R1 first** (the actual incident class, minimal blast radius) → R2 → R3i,
each after ≥3 clean dry-run proposals reviewed by the operator. R3i may stay dry-run-only
indefinitely if it never occurs (don't build authority for a case with zero observations —
it has never happened; R1 has).

## 2. Placement + plumbing

- **Where**: `coverage_drift.py` grows an `propose_ingest(...)` step invoked right after D1/
  D2-HIGH classification (same 15-min reconcile cadence, same per-mode guard). Runs where
  the reconcile runs (execution role in the split — holds the creds; the reaper's 7/6
  lesson: the market/intelligence container CANNOT read the live broker).
- **Toggle**: `get_runtime_toggle("broker_order_ingest", ...)` three-state per class:
  `off` (default) / `dry_run` / `live-R1` → `live-R2` → `live-R3`. Dry-run writes
  `ingest_proposed` audit rows + ONE Telegram per NEW proposal (dedup by signature like
  coverage_drift's alerts) — the operator reviews these to grant the next phase.
- **COID parse**: `apollo_{mode}_{strategy}_{ticker}_{ms}` → validate ALL of: mode ==
  stream/account mode, ticker == order.symbol, strategy exists in the registry. Any
  mismatch → do NOT ingest, `ingest_rejected` audit row (a mismatched COID is itself a
  finding). The ms epoch gives the original submission time → `alert_date` (ET date of ms).
- **Idempotency + no-overwrite**: R1 only writes when `stop_order_id IS NULL` OR the current
  pointer is broker-confirmed dead (`_canonical_order_status in _TERMINAL_ORDER_STATUSES`)
  — never clobber a live pointer (re-assert in the UPDATE's WHERE, the reaper's
  belt-and-suspenders). R2/R3i: `INSERT ... ON CONFLICT DO NOTHING` keyed on the natural
  key + a pre-check that no open row exists for (ticker, mode).

## 3. Row reconstruction (R2/R3i minimal-field contract)

From the wire order/position dict + COID parse ONLY (never guessed):
`ticker` (symbol) · `alert_date` (COID ms → ET date) · `signal_type` (COID strategy) ·
`account_mode` (COID mode) · `entry_order_id`/`stop_order_id` (order ids) ·
`entry_price` (R3i: position avg_entry; R2: order stop/limit price) · `entry_shares`/
`remaining_shares` (qty) · `stop_price` (stop order's stop_price; R2: from the OTO leg if
present, else NULL and the naked-remediation path owns it) · `status` (`order_placed` /
`filled`). Provenance: `ingest_reconstructed` audit row carrying the full wire JSON (the
audit trail IS the provenance; no schema addition). Fields we CANNOT know (orb_high/low,
alert linkage) stay NULL — consumers already tolerate NULL orb fields (R-calc emits None,
ADR 0014's rule).

## 4. Safety rails (all inherited patterns, named)

- Degraded-read guard: runs inside coverage_drift's existing `raise_on_error=True` cycle —
  a failed broker read already aborts the whole cycle before ingest is reached.
- Per-cycle cap: max 2 ingests/cycle (a mass-gap event should page the operator via the
  existing D1/D2 alerts, not bulk-mutate).
- Every ingest: audit row + Telegram (real-time, per action — these are trade-state writes).
- Kill: the toggle back to `off`/`dry_run` instantly; `/pause` does NOT gate this (it's
  mirror-repair, not entries) — stated explicitly so nobody assumes it does.
- Mode isolation: COID mode must equal the cycle's account_mode (already how coverage_drift
  classifies); cross-mode proposals are rejected loudly.

## 5. #151 exercise (before ANY live enable; scriptable on paper)

`scripts/_184b_ingest_paper_exercise.py` (probe-class): on the PAPER account —
1. Place a real stop order via `make_client_order_id` (test strategy id), then NULL the DB
   row's `stop_order_id` → next cycle must propose/execute R1 repair → assert pointer
   restored + audit row. 2. Place an entry stop-limit, delete the DB row → R2 proposes a
   reconstruction matching §3's contract. 3. Foreign-COID order → asserts NO proposal.
4. Toggle at `dry_run` → proposals only, zero writes (byte-diff the rows).
Cleanup cancels all test orders (the existing paper-exercise idiom).

## 6. Tests (unit, beyond the exercise)

COID parse/validate truth table (good/mode-mismatch/ticker-mismatch/unknown-strategy/
malformed) · R1 no-overwrite (live pointer untouched; dead pointer repaired) · R2 ON CONFLICT
idempotency · dry-run writes nothing · per-cycle cap · foreign-COID never proposed ·
proposal-signature dedup (no Telegram spam across cycles).

## 7. Rollout + verify

Card builds module+tests+exercise-script (Sonnet, Fable/Opus review — trade-state) → deploy
dark (`off`) → run the paper exercise → operator flips `dry_run` → ≥3 clean proposals
reviewed → operator sign-off enables `live-R1` (CHANGE_PROCESS entry; ADR 0008 build-status
updated) → R2 later by the same gate. VERIFY-LIVE: the next organic R1 event repairs within
15 min with a correct Telegram (or stays quiet if none occurs — FL-4's 5 quiet days is the
ambient verify).

## Relation to existing work
- #436 (phantom self-heal) is the INVERSE direction (DB-has/broker-doesn't → reap); this is
  broker-has/DB-doesn't → ingest. Same home (the reconcile cycle), same rails — the #436
  card should reuse this spec's toggle/proposal/cap plumbing so both directions share one
  mechanism (one review covers both).
- ADR 0022's ladder_watchdog and this share nothing (strategy-level vs order-level) — noted
  to prevent scope creep.
