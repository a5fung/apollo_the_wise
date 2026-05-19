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

**TIERED REDESIGN 2026-05-18**: The original binary OK/TRIPPED design hard-blocked entries on any -5% drawdown. For a 20-30% win-rate strategy, P(7 consecutive losses) = 13.3% — meaning -7% drawdowns are statistically NORMAL variance, not strategy failure. Hard-blocking during normal variance structurally prevents the methodology from finding the winners that pay for losses. The tiered design adjusts SIZING with drawdown depth instead of fully stopping.

**Equity source**: `alpaca_client.get_account()` returns current `equity` (cash + open-position MTM). Already includes unrealized — open winners' gains lift equity, which is the entire point of the methodology-aware shape.

**Peak source**: `MAX(equity)` over last `DRAWDOWN_PEAK_WINDOW_DAYS` (=30) snapshots in `mi_account_equity_snapshots`, scoped to `account_mode`. Snapshots written daily at 16:12 ET cron (`account_equity_snapshot` job).

**Tiered state machine** (`mi_safeguard_state` table, PK `(safeguard, account_mode)`):

| State | Trip threshold | Release threshold | Sizing multiplier | Audit event (entry) |
|---|---:|---:|---:|---|
| OK | — | — | 1.0× | (no event) |
| WATCH | drawdown ≤ -4% | drawdown ≥ -2.5% | 1.0× | `drawdown_watch_entered` |
| REDUCE | drawdown ≤ -7% | drawdown ≥ -4% | 0.5× | `drawdown_reduce_entered` |
| BLOCK | drawdown ≤ -12% | drawdown ≥ -7% | 0.0× | `drawdown_block_entered` |

**Transition logic** (`_next_state` in `broker/drawdown_breaker.py`):

- **Trip-side**: jump to deepest applicable tier in ONE snapshot. A -15% one-day drop from OK lands directly in BLOCK, not WATCH-REDUCE-BLOCK over three days.
- **Release-side**: step up at most ONE tier per evaluation, gated on per-tier release threshold (asymmetric hysteresis at each boundary). Prevents flap.

**Sizing composition** (applied in `entry_pipeline.py` post-spec_builder):

```
final_shares = floor(spec.shares × strategy.position_size_multiplier × drawdown_tier_multiplier)
```

Per-strategy (#65, e.g. 9M Day 2 at 0.5×) and drawdown tier multipliers compound multiplicatively. A 9M Day 2 trade during REDUCE state = 0.5 × 0.5 = 0.25× sizing. This is methodology-correct — bleed weeks should compound conservative sizing across both axes.

**Account-mode scoping**: paper history doesn't carry over to live. Live cutover starts a fresh peak. `mi_safeguard_state` row is per `(safeguard, account_mode)`.

## Drawdown breaker — Why tiered instead of binary

For a 20-30% WR momentum strategy with R-expectancy positive:

| Event | Probability | Drawdown |
|---|---|---|
| 7 consecutive losses (at 1% each) | 13.3% | -7% |
| 10 consecutive losses | 5.6% | -10% |
| 13 consecutive losses | 2.4% | -13% |

The binary -5% trip caught NORMAL variance. After a normal drawdown, the strategy needs to keep trading to find the winners (3-10R) that pay for the losses. Pausing for ~30 days after a normal drawdown structurally breaks the strategy.

The tiered design preserves the safeguard's purpose (catastrophic loss prevention) WITHOUT preventing the methodology from operating during expected variance. WATCH = informational, REDUCE = halve risk (still fishing), BLOCK = true catastrophic floor (rare).

**Daily loss limit (2% of account)** remains in place as the same-day blow-up guard, independent of this tiered cumulative-drawdown logic.

- **Min-history gate** (active phase only): `snapshots_count ≥ MIN_SNAPSHOT_HISTORY_DAYS` (=7). Don't trip on sparse history (new account / mode flip). Shadow always evaluates and emits regardless (calibration data from day 1).
- **Stale-data fail-open** (advisor-flagged): if most recent snapshot is older than 48 hours, `sufficient_history=False` and the breaker is effectively disabled until data freshens. Protects against silent cron-failure lockouts on a week-old peak. Active-phase reads see `state='OK'` because `recompute_drawdown_state` won't transition without fresh data.
- **Legacy `TRIPPED` state migration**: pre-2026-05-18 `mi_safeguard_state` rows with `state='TRIPPED'` auto-migrate via `_next_state` on next recompute. Maps to REDUCE state (0.5× multiplier) until the recompute cron repopulates with a proper tier.

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

### 2026-05-18 — Drawdown breaker: tiered redesign (OK/WATCH/REDUCE/BLOCK)

**Trigger**: User correctly flagged that the binary -5%/-2.5% breaker design was methodology-incompatible. For a 20-30% WR strategy, P(7 consecutive losses) = 13.3%, making a -7% drawdown statistically NORMAL variance. Hard-blocking on normal variance prevents the methodology from finding the winners that pay for losses. The whole strategy structurally cannot work under the original design.

**Evidence**: 2026-05-18 paper account state — peak $99,271 (5/08), current $93,255, drawdown -6.06% caused by CRMD/KLAR/CSCO/MRAM cumulative damage over 10 days. Under binary design: TRIPPED state, would have blocked entries for ~30 days waiting for peak to age out or equity to recover to -2.5% (= +$3,535 from current). Under tiered design: same drawdown lands in WATCH state (informational only, no sizing impact). The system continues to fish for winners that pay for losses.

**Anticipated effect**:
- Tier definitions: OK (1.0×), WATCH at -4% (1.0×, alert only), REDUCE at -7% (0.5×), BLOCK at -12% (0.0×).
- Trip-side: jump to deepest applicable tier in one snapshot.
- Release-side: step up one tier per evaluation, asymmetric hysteresis.
- Sizing composition: `final_shares = strategy_multiplier × drawdown_tier_multiplier × base_shares`. 9M Day 2 (0.5×) × REDUCE (0.5×) = 0.25× during bleed weeks — methodology-correct conservative compounding.
- Audit events: tier-specific (`drawdown_watch_entered`, `drawdown_reduce_entered`, etc.) — no dual-emit since no production readers of legacy event names.

**Why tiered**:
- Daily loss limit (2%) is the same-day blow-up guard
- WATCH = telemetry tier (-4% to -7%): alerts but no trading change. Captures cumulative-bleed state for operator visibility.
- REDUCE = sizing tier (-7% to -12%): halves risk per trade. Strategy keeps fishing for winners but with reduced exposure. The methodology STILL operates.
- BLOCK = catastrophic tier (-12%+): rare; true emergency floor

**Reversion-flag**: REPLACEMENT of binary design (shipped 2026-05-08, #39). Legacy `DRAWDOWN_TRIP_PCT/RELEASE_PCT` constants kept as aliases for one cycle. Legacy `'TRIPPED'` state auto-migrates to REDUCE via `_next_state` + `get_tier_multiplier`. Rollback path: revert constants to binary values; ALLOWED_WRITERS unchanged; tiered code paths fall through to binary semantics via aliases.

**Promotion / live cutover impact**: this unblocks Gate 1 of live-cutover composite review. Under binary design, today's -6% would have blocked any live cutover for ~30 days. Under tiered: WATCH state, system trades normally at full size. Composite review can evaluate cleanly Friday.

**Status**: SHIPPED 2026-05-18. Live verification: today's -6.06% recomputes into WATCH state (informational); existing-position management unaffected; new entries (in shadow phase) continue at 1.0× sizing. Active-phase promotion still gated on 14d telemetry + acceptance gates.

---

### 2026-05-18 — Stop-ACK timeout watchdog: first real production catch (GOOGL #56)

**Field validation**: the stop-ACK timeout watchdog shipped 2026-05-17 (commit `8e8f6f3`) fired its first real case at 09:00:00 ET Monday 2026-05-18.

**Timeline** (UTC times in audit log → ET):
- 13:00:00 UTC (09:00 ET) — Watchdog scan detected GOOGL #56: `status='filled' AND filled_at NOT NULL AND stop_order_id IS NULL AND filled_at < NOW() - INTERVAL '30 seconds'`. Position had no broker stop entering Monday open.
- 13:00:00 UTC — `stop_ack_timeout_remediated` audit event. Fallback stop-market placed at `trade['orb_low']` = $379.43, order `b47256af-a252-4df9-865c-776e52fde847`.
- (Implicit) 09:35 ET — `morning_stop_refresh` ran. Read `trade["stop_price"]=$394.497` (the BE-level trailed stop from prior Day-2 management), called `update_stop()` to re-establish proper methodology stop above the conservative fallback.
- 20:45:00 UTC (16:45 ET) — Day-2 `update_open_positions_live` ran. `stop_update_started: $394.497 → $395.87` (slight SMA-trail bump). New stop `a16b3bbe-b105-4524-8800-bec219ad7cb6`.

**Why the stop_order_id was NULL Monday morning**: most likely Friday's DAY-TIF stop expired at 4:00 PM ET close (Alpaca DAY orders don't carry over weekends), and the weekend orphan-remediation didn't re-place — the normal 9:35 ET `morning_stop_refresh` would have re-established it, but for the 35 minutes between 9:00-9:35 ET the position would have been naked at broker. The 9:00 ET watchdog tick caught it.

**Concrete evidence**: position protected at $379.43 from 9:00 ET (well before market open at 9:30) instead of unprotected until 9:35 — 35 minutes of naked exposure eliminated. If GOOGL had gapped down hard at open, the methodology stop would have been re-established at the right level by 9:35 OR the fallback would have already stopped the position out. Either path is safe; no path leaves the position naked through market open.

**Operational outcome**: the watchdog did exactly what it was designed for. The MRAM-class silent-failure gate is now field-validated less than 48 hours after ship.

**Followup filed** (BACKLOG): investigate WHY GOOGL's stop_order_id went NULL between Friday close and Monday open — was it (a) Alpaca DAY TIF expiration as theorized, (b) weekend maintenance, or (c) some race with the 5:00 PM data-pull pipeline. Understanding the trigger informs whether to add a Friday-close stop-renewal job OR confirm the watchdog is sufficient on its own.

**Followup outcome (2026-05-18 investigation)**: Stops are placed via `place_stop_order` with `TimeInForce.GTC`, NOT DAY — so Friday close didn't expire d3b1850f. Audit log shows:
- Fri 16:45 ET: `stop_updated` placed d3b1850f at $394.50
- Fri 21:00 ET: `evening_position_backstop` ran sync_positions — quiet (stop ACTIVE)
- Sat/Sun: no scheduled jobs (mon-fri only)
- **14 container restarts** Sat 5:15 PM ET → Sun 12:11 PM ET (Track 1 deploy cycle)
- Mon 09:00 ET: watchdog catches stop_order_id NULL

Most-likely cause: during one of the Saturday restarts, Alpaca's WS dispatched a backlogged cancel/reject/expired event for d3b1850f. Pre-T1.5a (today), `trade_stream._handle_cancel_or_reject` nulled stop_order_id via inline `UPDATE mi_live_trades SET stop_order_id = NULL` WITHOUT any `log_audit_event` call — silent state mutation. That's why no audit trail.

**Going forward**: T1.5a's `set_stop_order_id` helper emits `stop_order_id_changed` audit event with `reason='cancel_or_reject_null'` for exactly this code path. If this recurs, full timeline will be in audit log.

**Verdict**: defense in depth sufficient. No additional code change needed.
1. Trigger (silent WS cancel during restart) — was silent pre-T1.5a, NOW audited
2. Watchdog catches NULL Monday 09:00 — already working
3. morning_stop_refresh re-establishes proper stop at 09:35 — already working

Closes the followup. Three-layer protection is in place.

---

### 2026-05-17 — Trade-state ownership refactor (T1.1/T1.2/T1.4) + Gate 5 G (column-write authority preflight)

**Trigger**: Five trade-state corruption bugs in May (CRMD/KLAR/ARM/BW/AIXI), same root cause every time — multiple writers to the same column with no ownership rule, last-write-wins by accident. Boot-time prepare validation (Gate 5 B, shipped 2026-05-14) catches type errors but not semantic-overwrite. Friday's Phase 1 audit (`docs/architecture/trade-state-ownership.md`) enumerated every writer per column + drafted ownership rules; today's Phase 2 work refactors three hot-path bug surfaces + ships the static-analysis gate.

**Three refactors shipped (commit chain T1.1 → T1.2 → T1.4):**

- **T1.1** — `trade_stream._process_entry_fill` no longer writes `stop_price` / `hard_stop`. Entry-fill is NOT the authorized writer; INSERT at `entry_pipeline._skip` sets the initial value, `update_stop()` owns trail. KLAR/ARM bug root cause. Cuts stop_price writers 7 → 4. Param count 6 → 5.

- **T1.2** — `live_tracker.update_open_positions_live` partial-fired branch no longer writes `stop_price`. `update_stop()` at the same call site is the authorized writer. When `update_stop()` failed (returning False + nulling stop_order_id per naked-position protocol), the wrapping write previously falsely reported a stop_price the broker no longer held. Cuts stop_price writers 4 → 3. Param count 4 → 3.

- **T1.4** — `live_tracker.update_open_positions_live` no-partial branch no longer writes `stop_price` / `total_pnl` / `partial_taken` / `remaining_shares`. Beyond the stop_price reason: in this branch `step.new_X == state[X]` (no change when no partial fires), so the "idempotent no-op write" was actually a LOST UPDATE hazard if a WS fill arrived concurrently between state-load and UPDATE. Cuts stop_price writers 3 → 2 effective (live_tracker close path at line 537 still writes NULL — T1.3 future-work). Param count 8 → 4.

**Gate 5 G ship (T1.5):**

`scripts/audit_column_writes.py check` mode + `ALLOWED_WRITERS` dict + `deploy.sh` step `[5c/5]` wire. Walks every UPDATE / INSERT site touching `mi_live_trades`, builds `(column, module.function)` pairs, fails the deploy on any pair not in `ALLOWED_WRITERS`. Output names the violation, the file/line, the function, the existing allowed set, and the two fix paths (add to allow-list OR refactor to authorized writer).

**Verification protocol passed**:
1. `check` mode on clean tree → OK, 47 sites verified clean.
2. Synthetic test: injected a `rogue_writer` function writing `stop_price` from `fake_violator.py` → check correctly flagged the violation + named the four legitimate writers. Test passed.

**Promotion**: Active on every deploy via `scripts/deploy.sh` step `[5c/5]`. Exit code 6 reserved for column-write authority failures.

**Friction by design**: adding a new writer requires updating `ALLOWED_WRITERS` in the same commit. Explicit ack of new co-ownership.

**Limitations** (per script docstring): regex-based parsing handles multiline UPDATEs but would miss dynamic SQL string-concat (none currently exist). Doesn't catch raw `conn.execute` with template strings. Acceptable for current codebase pattern.

**Future-work follow-ups filed**:
- T1.3 — `live_tracker.update_open_positions_live` close path (line 537) delegates to `finalize_full_exit` / `finalize_stop_fill`. Deferred today per drop priority (complex — WS-vs-fallback ownership for Alpaca-confirms-gone case).
- T1.5a — `set_stop_order_id` helper consolidates 12 solo writes into one authorized writer. Allow-list tightening (cosmetic per advisor 2026-05-17); not safety.

**Reversion-flag**: NEW for Gate 5 G. REFINEMENTs of 2026-05-14 KLAR/ARM fix (d6fa74c) and 2026-05-14 BW fix (c0fa67f) for T1.1/T1.2/T1.4 — the inline COALESCE / `partial_fired` skips remain as belt-and-suspenders; refactors remove the SECOND-WRITE pattern at source.

**Status**: shipped 2026-05-17. Closes Gate 5 G live-cutover blocker. Composite `live_cutover_decision` review evaluation continues per schedule (2026-05-22 earliest).

---

### 2026-05-17 — Stop-ACK timeout watchdog (silent-failure gate, sibling of Gate 5 A)

**Trigger**: Weekly review 2026-05-17 proposed a 30-sec stop-ACK timeout gate to close the gap that Gate 5 A doesn't cover. Gate 5 A (naked-position remediation, shipped 2026-05-14 from CRMD postmortem) handles the EXCEPTION case (entry-fill UPDATE raises). The silent case — entry UPDATE succeeds cleanly, but OTO bracket child stop-leg never ACKs from Alpaca OR its acceptance event is missed by WS handler — was not covered by any gate. This entry closes that gap.

**Note (2026-05-18 correction)**: the weekly review framed MRAM #120 (2026-05-11) as the trigger incident citing "phantom double-exit" with stop_order_id persisting NULL. That framing was incorrect — broker order history (`mi_live_orders` for trade_id=120) shows MRAM had stop `b59f5633` placed cleanly + filled, plus a legitimate Day-1 re-entry (entry #2 `f7d0cad4` filled at 13:50). The -$2,199 was real damage from two real stop-outs on a re-entered trade, not phantom. See BACKLOG entry 2026-05-18 + commit `de01238` for the revert. The watchdog's design rationale (silent vs exception class) stands; the specific MRAM justification was wrong.

**Evidence (revised)**: the field-validation evidence is today's GOOGL #56 catch (2026-05-18 09:00 ET). GOOGL had its broker stop silently nulled some time between Friday 4:45 PM ET (last `stop_updated` audit event) and Monday 9:00 AM ET (watchdog firing). Most likely cause: WS cancel/reject event for stop `d3b1850f` during Saturday's 14 Track 1 container restarts. Pre-T1.5a `_handle_cancel_or_reject` nulled stop_order_id without audit logging — silent state mutation. Watchdog detected the NULL state at 9:00 ET, placed fallback at orb_low ($379.43). morning_stop_refresh re-established proper trail at 9:35 ET. Position never naked through market open.

**Anticipated effect**: new scheduler job `_stop_ack_timeout_watchdog_job` runs every 30s during market hours (9:00-15:30 ET, mon-fri). Predicate: `status='filled' AND filled_at IS NOT NULL AND stop_order_id IS NULL AND filled_at < NOW() - INTERVAL '30 seconds'`. On detection: submits fallback stop-market at `trade['orb_low']` (matches Gate 5 A pattern), UPDATEs `mi_live_trades.stop_order_id` with fallback order ID, emits `stop_ack_timeout_remediated` audit event, sends "🛡 STOP-ACK TIMEOUT — REMEDIATED" Telegram. On fallback failure: escalates to CRITICAL with `stop_ack_remediation_failed` + double-burst Telegram. Dedup: one remediation attempt per (trade_id, day).

**Why "fallback stop" not "flatten"** (deviation from weekly review proposal): Gate 5 A precedent submits fallback stop, not flatten. The fallback approach is recoverable if real ACK arrives later (race with cancel). Flatten on transient ACK delay loses the trade entirely. Acceptable risk: position naked for 30-60s window (between fill and watchdog detection). Trade-off accepted because the alternative (flatten on every 30-sec-delayed ACK) would surface false-positives on normal Alpaca latency.

**Env flag**: `STOP_ACK_TIMEOUT_GATE_ENABLED=true` (default). Set false + docker compose restart to revert.

**Reversion-flag**: NEW. Sibling of Gate 5 D stuck-fill watchdog (which only catches `status='filling'` cases, not `status='filled' + stop_order_id NULL`).

**Status**: shipped 2026-05-17. **Field-validated 2026-05-18** by GOOGL #56 catch (see safeguards.md change log entry above this one). Continue monitoring `stop_ack_timeout_remediated` audit events; non-zero count = a real silent-failure case the gate caught.

---

### 2026-05-08 — Initial shadow ship

**Trigger**: 5/8 morning ORB blocked by 5-consecutive-loss count breaker (BSX 4/23 → AMD 5/07 streak). User flagged the breaker as methodology-blind + self-perpetuating. Two structural flaws documented in `constants.py:37-43`: (1) cooldown anchored to `latest_loss_at + 24h`, advancing with each new loss closing during cooldown — only a closed winner breaks it, but during cooldown no new entries fire, so only existing open winners can resolve it; (2) Pradeep methodology holds winners for days/weeks while losers stop fast in minutes/hours, so the trailing-N closed-trade window structurally over-weights losers.

**Evidence**: One streak (4/24-5/07) directly observed. Plan agent + advisor reviewed two design iterations: per-call vs. daily state machine (state machine chosen for audit-flood + ordering + hot-path reasons); stateless threshold check vs. state-aware hysteresis (state-aware chosen to eliminate `-5.1%/-4.9%/-5.1%` flap scenario). Backtesting against historical losing streaks deferred — equity-at-time including unrealized cannot be reconstructed from `mi_live_trades.total_pnl` alone.

**Anticipated effect**: Shadow ship emits `drawdown_breaker_tripped` / `drawdown_breaker_released` audit events on state transitions only. Zero impact on trading behavior during shadow. Active flip (env var) blocks new entries when state='TRIPPED'. Methodology-aware (Alpaca equity includes unrealized → open winners lift equity, prevent false trips). Self-clearing on recovery to within 2.5%. Magnitude-sensitive (5 small losses don't trip; 1 big loss can).

**Reversion-flag**: NEW. Replaces the count-based breaker (#5 above) which stays in place threshold=10 as backup until the drawdown breaker promotes and bakes for 30 days.

**Status**: shadow shipped 2026-05-08. Promotion gated on ≥14d post-live-cutover (live cutover earliest ~5/12) telemetry + acceptance gates above.
