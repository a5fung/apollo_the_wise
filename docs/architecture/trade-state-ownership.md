# Trade-state column ownership

**Status**: Draft 2026-05-15 (Friday weekend Phase 1) — written from the
audit output of `scripts/audit_column_writes.py`. Sunday refactor (Phase 2)
will enforce these rules and ship Gate 5 G column-write audit invariant.

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

**45 write sites** across 5 files (45 = 2 INSERT + 43 UPDATE).
**35 distinct columns** written.

Run `python scripts/audit_column_writes.py` to regenerate the full
column→writers matrix.

### High-fanout columns (most writers — riskiest)

| Column | Writers | Risk |
|---|---|---|
| `stop_order_id` | 23 | Routing pointer; corruption = lost stop ID, not wrong stop level |
| `total_pnl` | 11 | Account math; off-by-amount affects R-expectancy |
| `closed_at` | 9 | Timestamp; mostly safe but ordering matters |
| `exits` | 9 | JSONB history; append-only via per-function paths |
| **`stop_price`** | **7** | **Risk basis; KLAR/ARM bug ✱** |
| `remaining_shares` | 7 | Position truth; corruption = wrong size for trail/exit |
| `hold_days` | 4 | Telemetry; low-stakes |
| `entry_price` | 3 | Risk basis denominator (R calc) |
| `hard_stop` | 3 | Paired with stop_price |
| `entry_shares` | 3 | Position size at fill |
| `entry_order_id` | 3 | Routing pointer |
| `filled_at` | 3 | Fill timestamp |
| `partial_taken` | 2 | Trail logic gate; BW bug ✱ |
| `breakeven_active` | 2 | Trail logic gate |

✱ Indicates a column corrupted this week. Sunday refactor priority.

---

## Per-column ownership rules

### `stop_price` + `hard_stop` (paired; treat as one)

**Initial setter**:
- `entry_pipeline._skip` INSERT (line 358) — sets to `order_spec["stop_loss_price"]`

**Authorized updaters**:
- `order_manager.update_stop` (line 836) — **the canonical trail mechanism**.
  Called from morning_stop_refresh, partial-exit replacement, manual override.
- `live_tracker.update_open_positions_live` (lines 606, 614) — SMA-trail /
  breakeven path. Computes `step.effective_stop` and writes both rows AND
  separately calls `update_stop()` for the broker. **Possible redundancy:
  if `update_stop()` already writes stop_price, this wrapping UPDATE is a
  duplicate.** Sunday investigation.
- `order_manager.check_fills` (line 335) — polling backup for entry fill
  when WS misses. Writes stop_price = `trade["stop_price"]` (the existing
  value) — effectively a no-op for stop. Safe.

**Forbidden / refactor targets**:
- `trade_stream._process_entry_fill` (line 733) — **KLAR/ARM bug origin**.
  Currently writes `trade["stop_price"] or trade["orb_low"]` (today's fix).
  Sunday: **REMOVE stop_price/hard_stop from this UPDATE entirely.** The
  values were correctly set at INSERT; the fill event doesn't need to
  refresh them. If `update_stop()` ran (e.g., Day-1 re-entry), it
  already updated.
- `live_tracker.update_open_positions_live` close path (line 537) — sets
  `stop_price = NULL` on close. Belongs in `finalize_full_exit` /
  `finalize_stop_fill` (which already do this), not in the trail loop.
  Sunday: remove from line 537 path.

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

**Authorized updaters**:
- `order_manager.finalize_partial_exit` (line 1225) — sets both to TRUE on
  confirmed partial fill (the canonical writer)

**Forbidden / refactor targets**:
- `live_tracker.update_open_positions_live` line 614 — writes both. Same
  pattern as total_pnl/remaining_shares — should DELEGATE to
  `execute_partial_exit` which already manages this through `finalize_*`.
  **This is the BW pre-fill bug origin** (2026-05-14). Sunday: remove
  these writes; delegate to the authorized path.

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

## Sunday refactor targets (priority order)

1. **`trade_stream._process_entry_fill` line 733** — remove stop_price/hard_stop
   from the UPDATE. KLAR/ARM bug root cause. (Currently has the today's-fix
   workaround but the second-write pattern remains.)

2. **`live_tracker.update_open_positions_live` line 614** — partial_taken
   and remaining_shares writes belong to `execute_partial_exit` →
   `finalize_partial_exit`. Refactor to delegate. (BW bug root cause.)

3. **`live_tracker.update_open_positions_live` line 537** — close path
   writes belong to `finalize_full_exit` / `finalize_stop_fill`. Delegate.

4. **`live_tracker.update_open_positions_live` lines 606/614** — investigate
   stop_price duplication with `update_stop()`. If `update_stop()` already
   writes, the wrapping UPDATE is redundant. Remove or no-op.

5. **`stop_order_id` 23-writer audit** — confirm each transition is valid.
   Lower priority since it's a pointer not a value, but worth verifying.

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

## Open questions for advisor (Sunday)

- For `total_pnl`: is `attempt_day1_reentry` having 4 internal writers a smell? Or acceptable as one function with branches?
- For `stop_order_id`: 23 writers across the lifecycle — bundle into a `set_stop_order_id(trade_id, new_id)` helper to reduce surface area?
- For `status` state machine: should we add an invariant that status transitions follow a declared FSM (vs free-form writes)?
