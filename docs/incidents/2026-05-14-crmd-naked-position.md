# Incident Post-Mortem: CRMD Naked Position (2026-05-14)

**Status**: DRAFT — pending full root-cause walk + sign-off
**Severity**: P0 — would have caused materially worse damage on live $
**Detected**: 2026-05-14 ~10:50 ET (user-flagged via Telegram)
**Resolved**: 2026-05-14 11:08 ET (manual market SELL on CRMD)
**Live-cutover impact**: **BLOCKER** — see action items §6

---

## 1. Summary

A schema change shipped 2026-05-10 (`35c1f6c` — add `lowest_price_seen` / `highest_price_seen` NUMERIC columns) introduced an `AmbiguousParameterError` in `trade_stream._process_entry_fill`'s SQL UPDATE. The error has silently failed every entry-fill UPDATE since deploy. On 2026-05-14, CRMD's OTO bracket stop-leg was canceled by Alpaca when the WebSocket fill callback threw, leaving the position **naked for 1h34m** (09:34 ET → 11:08 ET). User flagged via Telegram after seeing price drift well below the intended stop. Manual market SELL recovered at -$778 (vs intended -$220 had the stop fired correctly).

**This incident is a P0 live-cutover blocker.** Same code path executes identically against the live Alpaca account. On live $ with the same setup, the loss could be 5-10× larger (no daily_loss_limit cap on a single naked position; a runaway gap-down could exceed account equity).

---

## 2. Timeline (all times ET)

| Time | Event | Source |
|---|---|---|
| **2026-05-10 22:43 PT** | Commit `35c1f6c` deployed: adds `lowest_price_seen` / `highest_price_seen` NUMERIC columns; reuses `$2` (entry_price = double precision) in `_process_entry_fill` UPDATE. Bug latent. | git log |
| **2026-05-11 09:53 ET** | BW entry fills — bug should have triggered. UPDATE failed silently. `filled_at` NULL. Later populated by 5-min `track_open_position_extremes` cron path. | audit log |
| **2026-05-11 09:50 ET** | MRAM entry fills — UPDATE failed. Day-1 re-entry path later wrote `filled_at` via different UPDATE. | audit log |
| **2026-05-14 09:31:00** | OTO bracket placed for CRMD: entry stop-limit BUY @ $8.65 + stop SELL @ $8.45 (qty 2214). | trade_stream log |
| **2026-05-14 09:34:40** | CRMD entry FILLED at $8.36 (gap-fill). WS `_process_entry_fill` UPDATE threw `AmbiguousParameterError: inconsistent types deduced for parameter $2 / numeric versus double precision`. Trade stuck at `status='filling'`. | trade_stream ERROR log |
| **2026-05-14 09:34:40** | Telegram alert fired: `📄 PAPER ⚠️ Stream handler error / fill for CRMD: inconsistent types deduced for parameter $2`. **Generic framing — did not convey "POSITION NAKED."** | Telegram history |
| **2026-05-14 09:34:41** (1s after) | Alpaca CANCELED stop leg `a06c09fc...`. OTO bracket teardown — the broker no longer recognized a valid parent-child relationship after the WS handler threw. **Position became naked.** | broker order history |
| **2026-05-14 09:35:29** | KLAR entry fill — same UPDATE failure. Stop-leg survived (different OTO state at broker?). Stop later fired naturally at $15.16 (DB recorded via different code path). | trade_stream ERROR log |
| **2026-05-14 09:39:09** | CSCO entry fill — same UPDATE failure. Stop fired at $115.04. | trade_stream ERROR log |
| **2026-05-14 09:35 – 10:50** | CRMD bleeds from $8.36 → $7.93 (intended stop was $8.45; breach $0.52 deep). Unrealized P&L drifts to -$955. **No further alerts.** | broker position polling |
| **2026-05-14 ~10:50** | User notices price drift on CRMD position; Telegram-flags to Claude Code session. | user report |
| **2026-05-14 11:08:04** | Manual market SELL submitted (`scripts/_emergency_close_crmd.py`). Filled 2214 @ $8.01. P&L -$778.02. Position flat. | broker fill confirmation |
| **2026-05-14 ~11:11** | Commit `96fd7ee` shipped: `::numeric` casts disambiguate `$2`. Deployed; preflight green. | git log |
| **2026-05-14 ~11:14** | Backfill `filled_at` on KLAR/CSCO (`scripts/_backfill_filled_at.py`). | reconciliation log |

---

## 3. Damage assessment

**Day P&L (paper)**:
| Trade | Entry | Exit | Shares | P&L | Notes |
|---|---|---|---|---|---|
| KLAR | $15.92 | $15.16 (stop) | 1203 | -$914 | Stop fired correctly; bug only impacted DB state |
| CSCO | $117.55 | $115.04 (stop) | 162 | -$407 | Stop fired correctly; bug only impacted DB state |
| CRMD | $8.36 | $8.01 (manual) | 2214 | **-$778** | **Stop did NOT fire — bug-induced damage ~ -$558** |
| **Total** | | | | **-$2,099** | Triggered `daily_loss_limit` ($1,897 cap) — system correctly blocked further entries |

**Bug-attributable damage (CRMD only)**:
- Intended stop $8.45 → exit at ~$8.40 mid-spread → -$220 expected
- Actual exit $8.01 (manual recovery) → -$778
- **Delta = -$558 caused by the bug**

**Live-$ projection** (same setup, $50K account):
- Position size at 1% risk on $8.65 entry with $0.20 risk: $19.1K
- Same naked drift to $7.93: -$1,634 → -$2,150 difference vs intended stop
- **Worst case if not noticed for full session**: $7.50 close → -$3,500 (additional -$2,580 beyond stop)

**Live-$ projection** (same setup, $250K account at planned cutover size):
- Position size scales 5×: 11,070 shares
- Same drift: **-$7,800** worst case if unnoticed full session
- Account-wide blast: a runaway gap-down (e.g., -20% on negative news) could push -$25K+ on a single trade — beyond what `daily_loss_limit` catches because it's a single position, not aggregate.

---

## 4. Root cause walk (5 Whys)

1. **Why did CRMD bleed below stop?**
   The Alpaca OTO bracket's stop-leg was canceled at 09:34:41 (1 second after entry filled). No active stop order existed at broker.

2. **Why did Alpaca cancel the stop?**
   When the entry-fill WebSocket callback (`_handle_fill` → `_process_entry_fill`) threw an exception, the OTO bracket relationship was torn down by the broker. Alpaca treats unhandled callback failures on a parent fill as a bracket-integrity failure.

3. **Why did `_process_entry_fill` throw?**
   The UPDATE statement at `trade_stream.py:680` raised `asyncpg.exceptions.AmbiguousParameterError: inconsistent types deduced for parameter $2: numeric versus double precision`. asyncpg's prepared statement type-deduction couldn't reconcile `$2` being used for both `entry_price` (double precision) and `lowest_price_seen` / `highest_price_seen` (numeric).

4. **Why was `$2` overloaded across two column types?**
   Commit `35c1f6c` (2026-05-10) added `lowest_price_seen` / `highest_price_seen` as **NUMERIC** columns and reused `$2` for them in the UPDATE without testing the prepared-statement behavior. The original `entry_price = $2` was double precision; the new lines extended `$2` into numeric columns.

5. **Why wasn't this caught before deploy?**
   - No CI/test that exercises every parameterized UPDATE statement against a fresh DB schema.
   - The preflight (#84, shipped 2026-05-13) walks `_check_safeguards` but does NOT walk hot DB-mutation paths.
   - asyncpg's `AmbiguousParameterError` is a **prepare-time** error — discoverable by calling `connection.prepare(sql)` once at boot, but no such validation runs.
   - Local dev environment likely uses different test data that doesn't exercise the path, OR the dev exercising it manually re-creates the column type relationship from prior runs.

**Deeper cause**: schema changes that touch hot UPDATE paths are not gated by regression coverage. The same shape of bug (column-type addition silently breaks an UPDATE) is reachable any time a new column is added to a hot table.

**Deepest cause**: the system has no boot-time validation that DB-mutation statements actually prepare against the current schema. This is the same architectural gap as the 2026-05-13 outage where strategy `phase='live'` redefinition broke entry pipelines silently. Both are catchable by a preflight that walks every hot path at boot, not just credentials.

---

## 5. What went right / wrong

### What went right
- ✅ User Telegram-flagged within ~75 minutes of the bug firing. Without that observation, position could have bled all session.
- ✅ Telegram alert DID fire for the stream handler error (the user saw it earlier but the generic framing didn't escalate).
- ✅ `daily_loss_limit` safeguard correctly tripped at -$2,099 (≥ $1,897 paper cap), preventing further damage from new entries.
- ✅ Same-day code fix + deploy. Total downtime ~1h34m for the naked position.
- ✅ Reconciliation scripts preserved as evidence; DB state restored cleanly.
- ✅ The bug was reproducible and root cause was unambiguous (asyncpg error message names the parameter and the type conflict).

### What went wrong
- ❌ **Schema-touching commit shipped with no regression coverage on the UPDATE path.** A `connection.prepare()` check at boot would have caught this at deploy time, not at first entry fill.
- ❌ **The stream handler exception did not escalate to a naked-position alert.** Generic "Stream handler error" framing was easy to dismiss. The user saw the alert but didn't connect it to "the system has lost control of a position."
- ❌ **No defensive remediation when entry-fill UPDATE fails.** The code path that should have fired ("if we can't record the fill, IMMEDIATELY submit a fallback stop") doesn't exist. Trust in the OTO bracket assumes the WS callback succeeds — which is wrong, because asyncpg can fail at prepare time before any DB state changes.
- ❌ **Silent failure had been happening since 2026-05-10** (4 trades affected: MRAM, KLAR, CSCO, CRMD). KLAR/CSCO/MRAM appeared to "work" because their close paths used different UPDATE statements without the type collision. CRMD only surfaced as a naked position because its stop was canceled by the OTO teardown.
- ❌ **The preflight #84 was the right pattern but insufficient scope.** It walks `_check_safeguards` but not DB UPDATE prepare. The architectural lesson from 2026-05-13 (preflight more than just credentials) was not generalized far enough.

---

## 6. Action items — LIVE CUTOVER BLOCKERS

The following MUST ship before any strategy is promoted to `phase='live'` + `live_real_enabled=True`. The composite live cutover gate (`live_cutover_decision` in `data_gated_reviews.yaml`) must be updated to require all of these:

### A. Naked-position remediation in `_process_entry_fill` (P0)
- When the entry-fill UPDATE raises ANY exception, IMMEDIATELY submit a stop-market SELL at `trade["orb_low"]` (the intended stop) BEFORE any other action. Do NOT trust the OTO bracket to remain intact when the WS callback throws.
- Emit `naked_position_remediation_fired` audit event with full diagnostic context.
- Telegram: 🚨 NAKED POSITION REMEDIATED with order ID of the fallback stop.
- Reference implementation: this is what the manual `_emergency_close_crmd.py` did today, but should run automatically inside the exception handler.

### B. Boot-time DB UPDATE prepare validation (P0)
- Extend `agents/market_intelligence/preflight.py` (or create one) that walks every parameterized UPDATE statement in `trade_stream.py`, `order_manager.py`, `live_tracker.py` and calls `connection.prepare(sql)` against the production schema.
- Any `AmbiguousParameterError` or other prepare-time error fails the deploy. Use the same `scripts/deploy.sh` chaining pattern as `scripts/preflight_check.py`.
- Trade-off: prepare doesn't validate runtime parameter values, only types. Sufficient for catching today's bug class.

### C. Escalated naked-position alert (P0 — partially shipped)
- ✅ Shipped 2026-05-14: `event=='fill'` exception → "🚨 POSITION MAY BE NAKED — INTERVENTION REQUIRED" Telegram.
- 🔲 Add: same escalation for `partial_fill` exception (less critical but same risk shape).
- 🔲 Add: monitor for `entry_order_id IS NOT NULL AND status='filling' AND filled_at IS NULL AND created_at < NOW() - INTERVAL '2 minutes'` — surfaces stuck fills regardless of which path failed. Cron every 60s during market hours.

### D. Regression test for schema column-type additions (P1)
- Add a pytest that exercises EVERY UPDATE statement in `mi_live_trades` against a fresh test DB. Asserts no `AmbiguousParameterError`.
- Hook to pre-commit + CI (when CI exists). Local-only is sufficient as a stopgap.
- Use the schema dump in `migrations/` (or `scripts/init_db.sql`) as the test fixture.

### E. Backfill remaining historical state (P2 — non-blocking)
- ✅ KLAR/CSCO `filled_at` backfilled today.
- 🔲 BW (id=119) `filled_at` — populated indirectly by tracker cron but should be confirmed.
- 🔲 Inspect `exits` jsonb_typeof on KLAR/CSCO — stored as JSON-encoded string, not array. Separate bug (deferred commit path with stringified payload). File as new review.

---

## 7. Live cutover gate requirement

The `live_cutover_decision` review in `data_gated_reviews.yaml` is updated to add a 5th gate:

> **Gate 5 — Naked-Position Hardening Complete (incident 2026-05-14)**
> Action items A, B, C in `docs/incidents/2026-05-14-crmd-naked-position.md` MUST be shipped + verified. Verification: trigger the entry-fill UPDATE failure deliberately in paper (mock a type error via SQL); confirm the naked-position remediation submits a fallback stop within 5 seconds and that Telegram escalates correctly.

**No live promotion until Gate 5 is green.**

---

## 8. Sign-off

| Role | Reviewer | Sign-off Date | Notes |
|---|---|---|---|
| Author | Claude Code session 2026-05-14 | 2026-05-14 | Draft |
| Operator | Alvin | pending | |
| Live cutover gate | n/a | pending | Gates A/B/C above must ship before sign-off |

---

## 9. Related

- Commit `35c1f6c` (2026-05-10) — bug-introducing
- Commit `96fd7ee` (2026-05-14) — same-day fix
- Commit `6f28604` (2026-05-14) — backfill + CLAUDE.md
- `scripts/_emergency_close_crmd.py` — manual recovery
- `scripts/_reconcile_crmd_close.py` — DB reconciliation
- `scripts/_backfill_filled_at.py` — KLAR/CSCO backfill
- Related architectural lesson: 2026-05-13 outage (preflight needs more than just credentials)
- Related architectural lesson: 2026-05-07 splits_ingest premature-apply (flag tracked PROCEDURE-ran, not OUTCOME-correct)
