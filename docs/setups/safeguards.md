# Portfolio Safeguards SSoT

**Phase**: live in production. The drawdown breaker (#6 below) is currently in **shadow phase** — the daily 16:12 ET cron emits transition audit events but `_check_safeguards()` does not block on it. Promotes to active after ≥14 days of post-live-cutover shadow telemetry.
**Code**: `agents/market_intelligence/broker/live_tracker.py::_check_safeguards` (lines 101-212+).

## Definition

Portfolio-level pre-trade gate. Every entry submission (MAGNA53 EP, 9M Day 2, future strategies) calls `_check_safeguards()` before placing an order. The function returns `(True, None)` to allow or `(False, skip_reason)` to block. Each safeguard is checked in order; first block short-circuits.

This is **not** a per-setup quality gate (those live in setup-specific SSoTs like `magna53_ep.md`, `ninem.md`, etc.). These are the guards that protect the *portfolio* from compounding damage regardless of which setup generated the candidate.

## Active safeguards (in order)

1. **`live_trading_enabled`** — env-gate kill switch (`LIVE_TRADING_ENABLED`). Returns False if disabled. No skip reason — the entire pipeline early-exits.
2. **`max_concurrent_positions`** (`BLOCK_MAX_POSITIONS`) — count of open `mi_live_trades` rows in `('filled','order_placed','pending_confirmation','confirmed')` ≥ `MAX_CONCURRENT_LIVE_POSITIONS` (5). Bounds total simultaneous exposure.
3. **PDT guards** — at equity < $25K:
   - `BLOCK_PDT_LOCKOUT_ACTIVE` if Alpaca's `pattern_day_trader=True`
   - `BLOCK_PDT_LOCKOUT_IMMINENT` if `daytrade_count ≥ 3` (one more day-trade and the broker locks out)
4. **`daily_loss_limit`** (`BLOCK_DAILY_LOSS`) — sum of today's closed-trade `total_pnl` ≤ `-equity * DAILY_LOSS_LIMIT_PCT` (-2%). Catastrophic intraday backstop. Magnitude-based, not count-based.
5. **`circuit_breaker`** (`BLOCK_CIRCUIT_BREAKER`) — last `CIRCUIT_BREAKER_CONSEC_LOSSES` (=10) closed trades all losses, cooldown until `latest_loss_at + CIRCUIT_BREAKER_COOLDOWN_DAYS` (=1d). **DEPRECATED**: superseded by drawdown breaker (#6); will be removed after #6 promotes to active. Threshold bumped 5→10 on 2026-05-08 as a stand-in.
6. **`drawdown_breaker`** (`BLOCK_DRAWDOWN_BREAKER`) — currently SHADOW. Persisted state machine; when `mi_safeguard_state.state='TRIPPED'`, blocks. See "Drawdown breaker — Mechanics" below.

## Drawdown breaker — Mechanics

**Equity source**: `alpaca_client.get_account()` returns current `equity` (cash + open-position MTM). Already includes unrealized — open winners' gains lift equity, which is the entire point of the methodology-aware shape.

**Peak source**: `MAX(equity)` over last `DRAWDOWN_PEAK_WINDOW_DAYS` (=30) snapshots in `mi_account_equity_snapshots`, scoped to `account_mode`. Snapshots written daily at 16:12 ET cron (`account_equity_snapshot` job).

**State machine** (`mi_safeguard_state` table, PK `(safeguard, account_mode)`):

| Current state | Drawdown condition | New state | Audit event |
|---|---|---|---|
| OK | `drawdown_pct ≤ DRAWDOWN_TRIP_PCT` (-5%) | TRIPPED | `drawdown_breaker_tripped` |
| OK | else | OK | (no event) |
| TRIPPED | `drawdown_pct ≥ DRAWDOWN_RELEASE_PCT` (-2.5%) | OK | `drawdown_breaker_released` |
| TRIPPED | else | TRIPPED | (no event) |

State-aware threshold check eliminates the `-5.1% → -4.9% → -5.1%` flap-and-spam scenario a stateless comparator would produce. Audit events fire only on transitions.

**Account-mode scoping**: paper history doesn't carry over to live. Live cutover starts a fresh peak. `mi_safeguard_state` row is per `(safeguard, account_mode)`.

## Drawdown breaker — Trip & Release

- **Trip**: `current_equity ≤ peak * 0.95` while state was OK
- **Release**: `current_equity ≥ peak * 0.975` while state was TRIPPED
- **Asymmetric thresholds** (5% trip / 2.5% release) prevent flapping — the breaker stays tripped through the noise band before declaring recovery
- **Min-history gate** (active phase only): `snapshots_count ≥ MIN_SNAPSHOT_HISTORY_DAYS` (=7). Don't trip on sparse history (new account / mode flip). Shadow always evaluates and emits regardless (calibration data from day 1).
- **Stale-data fail-open** (advisor-flagged): if most recent snapshot is older than 48 hours, `sufficient_history=False` and the breaker is effectively disabled until data freshens. Protects against silent cron-failure lockouts on a week-old peak. Active-phase reads see `state='OK'` because `recompute_drawdown_state` won't transition without fresh data.

## Drawdown breaker — Design choices

These are deliberate, not oversights. Future readers should understand the reasoning before changing them:

- **Daily resolution, not intraday**. Peak is captured at 16:12 ET close, NOT intraday max. Drawdown is *understated* relative to true peak-to-current — conservative for trip purposes (less false-positive). Catches day-to-day equity erosion. Intraday volatility is the daily-loss-limit's job (#4 above). Together they cover the magnitude side at two timescales: 2% intraday + 5% multi-day.
- **State machine, not per-call evaluation**. `_check_safeguards()` is called per-candidate (20+ times per scan tick on busy days). Per-call drawdown computation would flood the audit log with duplicate events. Instead: evaluate ONCE daily at the cron, persist state, hot-path reads via cheap PK lookup.
- **Dedicated `mi_safeguard_state` table**, not derived from `mi_audit_log`. PK lookup is materially faster than scanning audit log; table is extensible to other future safeguards; explicit state beats derived state for an active-phase hot path.
- **Env-var phase gate**, not strategy-registry phase. Registry is for strategies; this is a portfolio safeguard. Single env var (`DRAWDOWN_BREAKER_PHASE=shadow|active`) is the entire promotion mechanism.
- **No backfill from `mi_live_trades`**. Realized P&L alone can't reconstruct equity-at-time including unrealized. Day-1 baseline insert is the only "backfill". 7-day cold-start gate handles new-account scenarios.

## Other notes

- **`mi_account_equity_snapshots` is generically reusable** beyond this safeguard — analytics, `/status` enrichment, cross-strategy ranking allocator track-record dimension (#31 Phase 2). Future readers: do NOT assume the table belongs exclusively to drawdown-breaker semantics. Add columns and consumers freely; the table stays mode-scoped and idempotent per (date, mode).
- **Manual deposits/withdrawals** (live mode only): a $5K deposit looks like +5% equity (raises peak); a $5K withdrawal looks like -5% drawdown (false trip). Currently undetected. Defer to first quarter of live data; revisit via Alpaca `account_activities` API if it becomes a real problem.

## Known limitations / open questions

1. **Manual deposits/withdrawals**: not detected; deferred. See above.
2. **Quarterly hard peak reset**: not implemented. Using rolling 30-day window instead. Natural recency. Revisit if a stretched-out drawdown leaves a stale peak that prevents legitimate recovery.
3. **Cross-mode peak transfer**: paper peak does NOT inform live peak (mode-scoped table). Intentional — live cutover starts a fresh peak per CLAUDE.md cutover plan. If this proves wrong (e.g., user wants paper history as live's seed peak), it's a small change.

## Promotion plan (shadow → active)

**Trigger**: ≥14 calendar days of post-live-cutover shadow telemetry. Paper telemetry serves as threshold sanity-check only — NOT promotion evidence.

**Validation queries** before flip:

```sql
-- Trip/release transition history (post-cutover)
SELECT created_at, summary, detail FROM mi_audit_log
WHERE event_type IN ('drawdown_breaker_tripped','drawdown_breaker_released','drawdown_check_unavailable')
  AND created_at AT TIME ZONE 'America/New_York' >= '<live_cutover_date>'
ORDER BY created_at;

-- Daily state evolution
SELECT s.snapshot_date, s.equity, st.state, st.last_drawdown_pct
FROM mi_account_equity_snapshots s
LEFT JOIN mi_safeguard_state st
  ON st.account_mode = s.account_mode AND st.safeguard='drawdown_breaker'
WHERE s.account_mode = 'live'
ORDER BY s.snapshot_date DESC;
```

**Acceptance gates**:
- Trip rate ≤ ~1× per quarter equivalent
- Zero `drawdown_check_unavailable` clusters (Alpaca API reliability concern)
- ≥1 `drawdown_breaker_released` observed (proves recovery path works)

**Flip steps**:
1. Set `DRAWDOWN_BREAKER_PHASE=active` (env var, restart container).
2. Mark `CIRCUIT_BREAKER_CONSEC_LOSSES` and `CIRCUIT_BREAKER_COOLDOWN_DAYS` deprecated in `constants.py` with a 30-day removal comment.
3. Remove the count-based block from `_check_safeguards` (lines 184-210) after 30 days of clean drawdown-active operation. Keep constants in place during the deprecation window for easier rollback.
4. Update this file's change log: shadow → active, evidence link to validation queries.

## Change log (newest first)

### 2026-05-17 — Stop-ACK timeout watchdog (MRAM-class silent-failure gate)

**Trigger**: Weekly review 2026-05-17 surfaced the MRAM #120 (2026-05-11) incident — entry filled cleanly, `stop_order_id` persisted as NULL, position closed via WS-only path with phantom double-exit (logged -$2,199 vs actual -$1,100). Gate 5 A naked-position remediation (shipped 2026-05-14 from CRMD postmortem) handles the EXCEPTION case (entry-fill UPDATE raises) but does NOT handle the SILENT case (entry UPDATE succeeds, but OTO bracket child stop-leg never ACKs from Alpaca or its acceptance event is missed by WS handler). Weekly review proposed a 30-sec stop-ACK timeout gate; per investigation, it was a DIFFERENT class from Gate 5 A and was never built — this entry closes that gap.

**Evidence**: MRAM #120 has `stop_order_id IS NULL` with `status='closed'` and `filled_at='2026-05-11 13:50:17'` confirmed in production. Direct production evidence of the failure class. Weekly review framing: 40% of losers stopped in <10 minutes with no mechanical floor.

**Anticipated effect**: new scheduler job `_stop_ack_timeout_watchdog_job` runs every 30s during market hours (9:00-15:30 ET, mon-fri). Predicate: `status='filled' AND filled_at IS NOT NULL AND stop_order_id IS NULL AND filled_at < NOW() - INTERVAL '30 seconds'`. On detection: submits fallback stop-market at `trade['orb_low']` (matches Gate 5 A pattern), UPDATEs `mi_live_trades.stop_order_id` with fallback order ID, emits `stop_ack_timeout_remediated` audit event, sends "🛡 STOP-ACK TIMEOUT — REMEDIATED" Telegram. On fallback failure: escalates to CRITICAL with `stop_ack_remediation_failed` + double-burst Telegram. Dedup: one remediation attempt per (trade_id, day).

**Why "fallback stop" not "flatten"** (deviation from weekly review proposal): Gate 5 A precedent submits fallback stop, not flatten. The fallback approach is recoverable if real ACK arrives later (race with cancel). Flatten on transient ACK delay loses the trade entirely. Acceptable risk: position naked for 30-60s window (between fill and watchdog detection). Trade-off accepted because the alternative (flatten on every 30-sec-delayed ACK) would surface false-positives on normal Alpaca latency.

**Env flag**: `STOP_ACK_TIMEOUT_GATE_ENABLED=true` (default). Set false + docker compose restart to revert.

**Reversion-flag**: NEW. Sibling of Gate 5 D stuck-fill watchdog (which only catches `status='filling'` cases, not `status='filled' + stop_order_id NULL`).

**Status**: shipped 2026-05-17. Field validation: monitor `stop_ack_timeout_remediated` audit events; expect zero firings if OTO bracket child-leg ACKs normally; non-zero count = a real MRAM-class case the gate caught.

---

### 2026-05-08 — Initial shadow ship

**Trigger**: 5/8 morning ORB blocked by 5-consecutive-loss count breaker (BSX 4/23 → AMD 5/07 streak). User flagged the breaker as methodology-blind + self-perpetuating. Two structural flaws documented in `constants.py:37-43`: (1) cooldown anchored to `latest_loss_at + 24h`, advancing with each new loss closing during cooldown — only a closed winner breaks it, but during cooldown no new entries fire, so only existing open winners can resolve it; (2) Pradeep methodology holds winners for days/weeks while losers stop fast in minutes/hours, so the trailing-N closed-trade window structurally over-weights losers.

**Evidence**: One streak (4/24-5/07) directly observed. Plan agent + advisor reviewed two design iterations: per-call vs. daily state machine (state machine chosen for audit-flood + ordering + hot-path reasons); stateless threshold check vs. state-aware hysteresis (state-aware chosen to eliminate `-5.1%/-4.9%/-5.1%` flap scenario). Backtesting against historical losing streaks deferred — equity-at-time including unrealized cannot be reconstructed from `mi_live_trades.total_pnl` alone.

**Anticipated effect**: Shadow ship emits `drawdown_breaker_tripped` / `drawdown_breaker_released` audit events on state transitions only. Zero impact on trading behavior during shadow. Active flip (env var) blocks new entries when state='TRIPPED'. Methodology-aware (Alpaca equity includes unrealized → open winners lift equity, prevent false trips). Self-clearing on recovery to within 2.5%. Magnitude-sensitive (5 small losses don't trip; 1 big loss can).

**Reversion-flag**: NEW. Replaces the count-based breaker (#5 above) which stays in place threshold=10 as backup until the drawdown breaker promotes and bakes for 30 days.

**Status**: shadow shipped 2026-05-08. Promotion gated on ≥14d post-live-cutover (live cutover earliest ~5/12) telemetry + acceptance gates above.
