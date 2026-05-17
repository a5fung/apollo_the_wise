# Trade-state column ownership

**Status**: Active 2026-05-17 (Sunday Phase 2 shipped). Gate 5 G enforces
these rules at deploy time via `scripts/audit_column_writes.py check` →
`deploy.sh` step `[5c/5]`. Live since commit `fd31e5b`.

**History**:
- 2026-05-15 (Fri): Phase 1 audit + this doc drafted.
- 2026-05-17 (Sun): T1.1/T1.2/T1.4 refactors + T1.5 Gate 5 G ship.
- See `docs/setups/safeguards.md` change log for the full ledger.

**Why this exists**: Five trade-state corruption bugs this week
(CRMD/KLAR/ARM/BW/AIXI), same root cause every time — multiple writers to
the same column with no ownership rule, last-write-wins by accident. The
boot-time prepare validation (Gate 5 B) catches type errors but not
semantic-overwrite. This doc + Gate 5 G fix that.

## The principle

Every column on `mi_live_trades` has:
1. **One initial setter** — the INSERT statement that creates the row
2. **At most one authorized updater per logical phase** — explicit, named, audited
3. **Forbidden everywhere else** — Gate 5 G fails the deploy on violation

"Convenient overwrite" patterns (the recurring class) are banned. If a
function "needs" to refresh a column it doesn't own, it must either:
- Read the existing value and pass it through (no-op write) — clearly
  intentional
- Call the authorized owner's update function (explicit delegation)
- Document the exception inline AND add the call-site to the allow-list

---

## Audit summary

**47 write sites** across 6 files (47 = 2 INSERT + 45 UPDATE) post-2026-05-17.
**35 distinct columns** written.

Run `python scripts/audit_column_writes.py audit` to regenerate the full
column→writers matrix. `python scripts/audit_column_writes.py check` runs
Gate 5 G against `ALLOWED_WRITERS`.

### High-fanout columns — pre-refactor → post-refactor

Today's three refactors (T1.1, T1.2, T1.4) closed the high-risk surface
on stop_price, partial_taken, and the BW-class second-write columns.

| Column | Pre-refactor | Post-refactor | Note |
|---|---:|---:|---|
| `stop_order_id` | 23 | 25 | +1 stop-ACK watchdog (8e8f6f3), +1 sync sites |
| `total_pnl` | 11 | 11 | unchanged (live_tracker remains pending T1.3) |
| `closed_at` | 9 | 10 | +1 sync site |
| `exits` | 9 | 10 | +1 sync site |
| **`stop_price`** | **7** | **4** | **T1.1+T1.2+T1.4: KLAR/ARM/BW closed ✓** |
| `remaining_shares` | 7 | 14 | regex caught more sites; ownership unchanged |
| `hold_days` | 4 | 4 | unchanged |
| `entry_price` | 3 | 3 | unchanged |
| `hard_stop` | 3 | 2 | T1.1 dropped entry-fill writer |
| `entry_shares` | 3 | 3 | unchanged |
| `entry_order_id` | 3 | 3 | unchanged |
| `filled_at` | 3 | 3 | unchanged |
| `partial_taken` | 2 | 1 | T1.4 dropped no-partial branch writer ✓ |
| `breakeven_active` | 2 | 2 | unchanged (architecturally correct co-write) |

The `stop_price` reduction 7 → 4 closes the KLAR/ARM bug surface at source.
The `partial_taken` reduction 2 → 1 closes BW bug class.

T1.3 (close-path delegation, deferred) would further reduce stop_price 4→3,
total_pnl 11→10, exits 10→9.

---

## Per-column ownership rules

### `stop_price` + `hard_stop` (paired; treat as one)

**Initial setter**:
- `entry_pipeline._skip` INSERT (line 358) — sets to `order_spec["stop_loss_price"]`

**Authorized updaters** (post-2026-05-17):
- `order_manager.update_stop` (line 878) — **the canonical trail mechanism**.
  Called from morning_stop_refresh, partial-exit replacement, manual override.
- `order_manager.check_fills` (line 336) — polling backup for entry fill
  when WS misses. Writes stop_price = `trade["stop_price"]` (the existing
  value) — effectively a no-op. Safe.
- `live_tracker.update_open_positions_live` line 537 close path — writes
  `stop_price = NULL` on close. **TEMPORARY entry pending T1.3 ship** —
  the close path will eventually delegate to `finalize_full_exit` /
  `finalize_stop_fill` (which already do this). Listed in ALLOWED_WRITERS
  to honestly reflect current state; tightens when T1.3 ships.

**Closed (refactored 2026-05-17)**:
- ~~`trade_stream._process_entry_fill`~~ — **T1.1 dropped (commit 68096bc)**.
  Was the KLAR/ARM bug origin. Entry-fill is not the authorized writer;
  INSERT sets initial value, update_stop owns trail.
- ~~`live_tracker.update_open_positions_live` partial-fired branch~~ —
  **T1.2 dropped (67c3257)**. update_stop at same call site owns trail.
  Falsely optimistic write when update_stop failed.
- ~~`live_tracker.update_open_positions_live` no-partial branch~~ —
  **T1.4 dropped (f3539d2)**. Was a LOST UPDATE hazard on concurrent
  WS fills due to stale-read idempotent rewrite.

### `entry_price`, `entry_shares`, `filled_at`

**Initial setter**:
- `entry_pipeline._skip` INSERT (line 358) — `entry_price` = `orb_high`
  (the intended fill price, may differ from actual)

**Authorized updaters**:
- `trade_stream._process_entry_fill` (line 733) — fills in actual broker
  fill price + qty. **This is the legitimate writer.**
- `order_manager.check_fills` (line 335) — polling backup; same role.
- `order_manager.attempt_day1_reentry` (line 563) — re-entry fills overwrite
  prior attempt's values (lifetime extreme stays; entry refreshes per-attempt).

**Forbidden**: anywhere else.

### `total_pnl`

**Initial setter**: 0.0 default (column DEFAULT).

**Authorized updaters** (incrementally builds via exit fills):
- `order_manager.finalize_partial_exit` (line 1225) — partial fill → adds to total
- `order_manager.finalize_full_exit` (line 1364) — full exit → adds final
- `order_manager.finalize_stop_fill` (line 1441) — stop hit → adds stop loss
- `trade_stream._process_stop_fill` (line 867) — WS stop fill route
- `order_manager.cancel_unfilled_entries` (line 1542) — cleanup; sets to 0 on cancel
- `order_manager.attempt_day1_reentry` (lines 439, 464, 534, 563) — re-entry
  resets/recomputes (4 sites in one function — concerning, but contained
  within a single function's branches)

**Forbidden / refactor targets**:
- `live_tracker.update_open_positions_live` (lines 537, 614) — currently
  writes total_pnl in close / trail paths. Should DELEGATE to the
  `finalize_*` functions, not write directly. Sunday: refactor to call
  finalize_full_exit on close paths; the trail-only branches should not
  touch total_pnl.

### `remaining_shares`

**Initial setter**:
- `trade_stream._process_entry_fill` (line 733) — sets to `entry_shares`
  on fill (full position).

**Authorized updaters** (decrement on partial/full exit):
- `order_manager.finalize_partial_exit` (line 1225) — partial exit subtracts
- `order_manager.finalize_full_exit` (line 1364) — sets to 0 on close
- `order_manager.finalize_stop_fill` (line 1441) — sets to 0 on stop hit
- `order_manager._sync_positions_for_mode` (line 1706) — reconciliation
  override against broker truth (explicit; safe)
- `order_manager.attempt_day1_reentry` (line 563) — re-entry resets to
  new entry_shares

**Forbidden / refactor targets**:
- `live_tracker.update_open_positions_live` line 614 — writes remaining_shares
  in trail. Same delegation rule as total_pnl: trail shouldn't directly write
  remaining_shares. Sunday investigation: is this path actually used? If yes,
  add explicit audit; if no, remove.

### `partial_taken`, `breakeven_active`

**Initial setter**: FALSE default (column DEFAULT).

**Authorized updaters** (post-2026-05-17):
- `order_manager.finalize_partial_exit` (line 1267) — sets both to TRUE
  on confirmed partial fill. The canonical writer.
- `live_tracker.update_open_positions_live` line 643 — writes
  `breakeven_active` only (NOT `partial_taken`). state machine derives
  `step.new_breakeven_active`; this is the live-tracker no-partial branch
  that survived T1.4. Architecturally correct co-write (the value can
  only flip TRUE inside the same step that finalize_partial_exit runs;
  computed deterministically). Watch as a possible second-write surface.

**Closed (refactored 2026-05-17)**:
- ~~`live_tracker.update_open_positions_live` no-partial branch `partial_taken` write~~
  — **T1.4 dropped (f3539d2)**. Was the BW pre-fill bug pattern.
  finalize_partial_exit is now sole writer for `partial_taken`.

### `stop_order_id`

**Initial setter**:
- `order_manager.submit_entry` (line 247) — sets after bracket order placed

**Authorized updaters**:
- `order_manager.update_stop` (lines 806, 836) — null-on-cancel, set-on-new
- `order_manager.execute_partial_exit` (lines 987, 1019, 1100, 1135) — cycle
  old → new stop on partial
- `order_manager.attempt_day1_reentry` (lines 439, 464, 534, 563) — re-entry
- `order_manager.finalize_full_exit` / `finalize_stop_fill` (1364, 1441) —
  null on close
- `order_manager._sync_positions_for_mode` (1717, 1775, 1842) — reconcile
- `trade_stream._process_entry_fill` (line 733) — `COALESCE($5, stop_order_id)`
- `trade_stream._process_stop_fill` (line 867) — null on stop hit
- `trade_stream._handle_cancel_or_reject` (lines 929, 986, 1043) — null on cancel
- `live_tracker.update_open_positions_live` line 537 — null on close

**23 writers** is concerning but `stop_order_id` is a routing pointer. The
fan-out is across the trade lifecycle (entry → partial → cancel → close)
and routes through valid state transitions. Lower risk than `stop_price`.
Sunday: audit each for null-vs-set consistency.

### `status`

**Authorized updaters** (state machine):
- Many sites — every state transition writes status. This is the state
  machine and is OK to have many writers, **provided** transitions are
  acyclic and predictable. Verified-OK pattern.

---

## Refactor status (2026-05-17 Sunday Phase 2)

| # | Target | Status | Commit |
|---|---|---|---|
| 1 | `trade_stream._process_entry_fill` stop_price/hard_stop removal | ✅ shipped (T1.1) | `68096bc` + fixup `223ec92` |
| 2 | `live_tracker.update_open_positions_live` partial-fired stop_price | ✅ shipped (T1.2) | `67c3257` |
| 3 | `live_tracker.update_open_positions_live` no-partial redundant writes | ✅ shipped (T1.4) | `f3539d2` |
| 4 | `live_tracker.update_open_positions_live` close path delegation | ⏸ deferred (T1.3) | BACKLOG |
| 5 | `stop_order_id` 25-writer consolidation helper | ⏸ deferred (T1.5a) | BACKLOG |
| — | Gate 5 G ALLOWED_WRITERS + check mode + deploy.sh `[5c/5]` | ✅ shipped (T1.5) | `fd31e5b` |

T1.3 deferred per drop-priority — complex WS-vs-fallback ownership.
T1.5a deferred per advisor — cosmetic allow-list tightening, not safety.

## Sunday Gate 5 G design

`scripts/audit_column_writes.py` mode `check` reads `ALLOWED_WRITERS`:

```python
ALLOWED_WRITERS: dict[str, set[str]] = {
    "stop_price": {
        "entry_pipeline._skip",                       # INSERT
        "order_manager.update_stop",                  # trail
        "order_manager.check_fills",                  # polling backup
        "live_tracker.update_open_positions_live",    # SMA-trail (TBD remove)
    },
    "hard_stop": { ... same as stop_price ... },
    "partial_taken": {
        "order_manager.finalize_partial_exit",
    },
    "remaining_shares": {
        "trade_stream._process_entry_fill",
        "order_manager.finalize_partial_exit",
        "order_manager.finalize_full_exit",
        "order_manager.finalize_stop_fill",
        "order_manager._sync_positions_for_mode",
        "order_manager.attempt_day1_reentry",
    },
    # ... (full list Sunday)
}
```

Static analysis: for every `UPDATE mi_live_trades SET col = ...`, the
enclosing function name must be in `ALLOWED_WRITERS[col]`. Else fail.

Wired into `scripts/deploy.sh` as `[5c/5] column-write authority`:
```bash
echo "=== [5c/5] Preflight column-write authority check ==="
if ! docker exec apollo-market python -m scripts.audit_column_writes check; then
  echo "DEPLOY FAILED — unauthorized writer to mi_live_trades.<col>"
  exit 6
fi
```

Friction is the point. Adding a new writer requires updating
`ALLOWED_WRITERS` in the same commit — an explicit ack of "yes, this
column now has another owner."

---

## Migration order (Sunday)

1. Refactor #1 (trade_stream:733 stop_price removal) — synthetic test in paper, deploy, confirm
2. Refactor #2 (live_tracker:614 partial_taken delegation) — same
3. Refactor #3 (live_tracker:537 close delegation) — same
4. Refactor #4 (live_tracker:606/614 stop_price duplication) — investigate first
5. Ship audit_column_writes.py `check` mode + ALLOWED_WRITERS
6. Wire into deploy.sh
7. Final deploy — both preflights green
8. Synthetic violation test: insert a fake unauthorized write, confirm deploy blocks

## Open questions — resolved 2026-05-17

- **`total_pnl` 4 writers inside `attempt_day1_reentry`** — accepted as
  branches-of-one-function. Each writes the post-attempt total per a
  distinct branch (r3-disabled, stop-no-reentry, gap-through, capped).
  Functionally one writer.
- **`stop_order_id` 25-writer consolidation into `set_stop_order_id` helper** —
  per advisor 2026-05-17, deferred to next session as cosmetic. 12 sites
  are solo `UPDATE … SET stop_order_id = …` writes; 13 are multi-column
  atomic closes (e.g. `status='closed', stop_order_id=NULL, closed_at=NOW()`)
  that must stay inline to preserve atomicity. Gate 5 G's enforcement
  value is identical with or without consolidation.
- **`status` FSM enforcement** — per advisor, skip. State machine is a
  "verified-OK pattern" with many legitimate writers across the lifecycle.
  Documenting the set in ALLOWED_WRITERS is sufficient.

## Future-work followups

See `BACKLOG.md` Surfaced 2026-05-17 PM section for T1.3 and T1.5a items.

A separate data-gated review `gate_5g_historical_coverage` validates the
gate retroactively — would Gate 5 G have caught CRMD/KLAR/ARM/BW/AIXI at
their introducing commits? Useful regression evidence for the
`live_cutover_decision` composite review.
