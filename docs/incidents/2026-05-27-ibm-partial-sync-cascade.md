# Incident post-mortem: IBM partial-exit failure + DB mass-close cascade

**Date:** 2026-05-27 (evening session, 20:45 ET — 01:25 UTC 2026-05-28)
**Severity:** High — live trade DB state corrupted twice within 90 minutes; broker-side protection never compromised but operational confidence breach.
**Author:** Claude (acting agent), reviewed by user + advisor.
**Status:** Incident closed; verification pending tomorrow 4:45 PM ET EOD partial.

---

## Summary

A real pre-existing bug (cancel-new race in `execute_partial_exit`) fired on IBM trade #167 at 4:45 PM ET, generating a CRITICAL "POSITION NAKED" Telegram alert. The position was actually broker-protected; the alert was a DB-vs-broker drift, not a real naked position.

Investigating the alert, I (Claude) made **two distinct judgment errors** that each touched live trade state. The first destroyed DB rows for three active trades (IBM, PURR, CRSR); manual SQL restore recovered them. The second attempted an after-hours partial retry that further corrupted IBM's stop_order_id reference; manual SQL re-sync recovered it.

Broker protection on all three positions was intact throughout. No fills were lost, no orders mis-routed, no actual P&L impact. The damage was confined to DB consistency and operator trust.

---

## Timeline (all times ET)

| Time | Actor | Event |
|---|---|---|
| **5/22 9:34 AM** | Apollo | IBM entry stop-limit BUY submitted with OTO bracket stop @ $260.03 |
| **5/22 — 5/27** | — | Position sits unfilled 5 trading days; OTO bracket child stop sat alongside |
| **5/27 9:00 AM** | Alpaca | IBM entry fills at $263.17 (26 shares). Hold_days now = 5 (counts from alert_date 5/22) |
| **5/27 9:35 AM** | Apollo `morning_stop_refresh` | Refreshed stop to SMA-trail level $230.94, broker order id `10a550b4-6127-4429-9da5-557ed86b1dfd` |
| **5/27 4:45 PM** | Apollo `live_position_update` | Triggered partial-exit: sell 8 of 26 (forced at hold_days≥5) |
| **5/27 4:45:00.488 UTC** | Apollo | `partial_exit_started` audit row |
| **5/27 4:45:00.531 UTC** | Apollo | Cancel of `10a550b4` accepted by Alpaca; new 18-share stop submission rejected with `held_for_orders=26` — 43ms after cancel, broker's share reservation hadn't released. `partial_exit_aborted`. Bug class: cancel-new race. |
| **5/27 4:45:00.532 UTC** | Apollo | DB `stop_order_id` cleared to NULL; `naked_position_detected` audit row; CRITICAL Telegram fired to user |
| **5/27 evening** | User | Reported CRITICAL alert to Claude. Investigation began. |
| **5/27 ~8:00 PM** | Claude | Diagnosed cancel-new race; shipped `replace_order_by_id` atomic fix as commit `fa70976` |
| **5/27 ~9:00 PM** | User | Asked: "IBM does have a stop order — what's the action?" |
| **5/27 9:01 PM (01:01:32 UTC)** | **Claude (R3)** | Ran `sync_positions` via `docker exec apollo-market python -c "..."` to "trigger DB resync." Alpaca client failed cred bootstrap (env vars not remapped in subprocess), returned `[]`. `sync_positions` interpreted as "user liquidated everything" → **mass-closed DB rows for IBM (id 167), PURR (id 161), CRSR (id 172).** All three positions intact on broker. |
| **5/27 9:09 PM (01:09 UTC)** | Claude | Detected the corruption via follow-up DB query (status='closed' on all three). Manual SQL `UPDATE` restored status=`filled`, `remaining_shares`, `total_pnl`, `closed_at=NULL`. Logged `manual_db_restore` audit row. |
| **5/27 9:15 PM** | Claude | Shipped safety guard (#137) — `sync_positions` now refuses mass-close when Alpaca returns empty AND DB has N>0 active filled trades. Deployed. |
| **5/27 9:20 PM** | User | Asked: "ship 1, also run it now so we sell open tmr" (option 1 = same-window retry; run = manual partial trigger so IBM partial executes at tomorrow's open) |
| **5/27 9:25 PM** | Claude | Shipped same-window retry inside `execute_partial_exit` as `f236976`. Deployed. |
| **5/27 9:30 PM (01:18 UTC)** | **Claude (R4)** | Ran one-shot `_manual_partial_ibm_167.py` via `docker exec`. This time the script DID call `_bootstrap_alpaca_credentials` first, so creds resolved. Execution: replace_order succeeded (new stop `af4a1d47` created); **market sell of 8 failed with `held_for_orders=26`** — after-hours Alpaca reservation behavior leaves shares marked held even after replace succeeds; rollback also failed; DB `stop_order_id` cleared to NULL again. |
| **5/27 9:35 PM** | Claude | Read-only broker query confirmed: position 26 shares intact, single active stop `af4a1d47` qty=26 @ $230.94 status=ACCEPTED. Broker fully protected the whole time. |
| **5/27 9:38 PM** | Claude | Manual SQL `UPDATE` set `stop_order_id='af4a1d47-...'` on trade #167. Logged `manual_stop_order_id_resync` audit row. |
| **5/27 9:42 PM** | User | "This is not good. Do a complete post-mortem with advisor." |

---

## Impact assessment

### What was actually at risk

- **Real broker protection: intact throughout.** Alpaca's stop on IBM never lapsed — first via `10a550b4`, then via `af4a1d47` (the replace-created order, which Alpaca retained even when the partial-exit flow thought the rollback failed). Same for PURR and CRSR — broker-side state was never touched by the DB mass-close.
- **No fills lost, no orders mis-routed, no P&L impact.** The 8-share IBM partial that *should* have executed at today's 4:00 PM close did not execute. That's a methodology miss, not a financial loss.

### What was operationally damaged

- **DB consistency:** 3 trades wrongly marked `closed` for ~8 minutes (mass-close), 1 trade left with NULL `stop_order_id` after the second attempt for ~8 minutes. Both recovered via manual SQL.
- **Operator trust:** the user received a CRITICAL "POSITION NAKED" alert that wasn't a real naked position; later watched me cause two additional DB corruption events while trying to help. Asymmetric: small in dollar terms, large in confidence terms.
- **Audit trail:** all events written to `mi_audit_log`. Reconstruction was possible because of the existing audit discipline. This wasn't luck; it's a deliberate property of the system.

### Methodology drift

Pradeep partial-exit rule says **Day-5 forced partial at the close price.** Today's 4:45 PM run was that fire. It failed. Tomorrow's run executes at `hold_days=6` (still ≥5, will fire) using tomorrow's close price. That's a one-day drift; cannot be recovered.

---

## Root causes

Five distinct issues, not nested. Mixing them blurs prevention.

### R1 — Pre-existing code bug: cancel-new race in `execute_partial_exit`

**Mechanism:** `cancel_order` returns synchronously when Alpaca accepts the cancel; the broker's share-reservation system clears asynchronously. The flow then immediately submitted a new stop. At 43ms, the old stop's share lock hadn't released → Alpaca rejected the new stop with `insufficient qty available`.

**Why it lasted:** the race was timing-dependent; most days the cancel settled within the gap. IBM's particular state (5-day-old OTO bracket child stop that had been in some refresh-replaced lineage) may have made the reservation slower to release. Not a fluke — a tail-of-distribution event for a race that was structurally present.

**Mitigation shipped:** commit `fa70976` — `alpaca_client.replace_order_by_id` (atomic broker-side). The cancel-new sequence is replaced with a single atomic call. No share release window.

### R2 — Pre-existing code bug: `sync_positions` conflates "Alpaca returned []" with "user liquidated everything"

**Mechanism:** when `get_all_positions(account_mode=paper)` returned `[]`, the loop "DB has positions Alpaca doesn't" fired for every active trade and mass-closed them. The function couldn't distinguish "broker truly has 0 positions" from "Alpaca client failed and returned empty."

**Why it lasted:** in normal scheduled operation, `sync_positions` runs inside the agent process where credentials are properly bootstrapped — so `get_all_positions` only returns empty when broker truly has no positions. The destructive path was only reachable from an ill-formed manual invocation. **The bug was always there; nothing had stress-tested the failure mode.**

**Mitigation shipped:** commit `fa49304` — `_sync_positions_for_mode` aborts with `sync_positions_aborted_alpaca_empty` audit row when Alpaca returns empty AND DB has N>0 active filled trades. Two tests pin the guard.

### R3 — Judgment error: ran `sync_positions` via `docker exec python -c` without verifying the credential path

**What I did:** Ran a one-shot Python command to "trigger DB resync." The `docker exec` spawned a new Python subprocess. The agent's `_bootstrap_alpaca_credentials` function only runs at boot in the agent's main Python process; it modifies `os.environ` in-process to remap legacy `ALPACA_API_KEY` → `ALPACA_PAPER_API_KEY`. That remap is **not visible to a sibling `docker exec` subprocess**, which gets a fresh env that still only has the legacy var.

**What I should have considered:** the IBM situation didn't need urgent DB resync. The user reported broker has a stop. The right action was: confirm via read-only broker query, then either wait for the scheduled 21:00 ET evening sync (which runs in the agent process with correct creds) OR update DB via SQL directly with explicit operator review. I chose to "trigger sync_positions" without verifying the invocation path was safe.

**This is the destructive event of the night.** R1 and R2 were pre-existing bugs that needed real fixes. R3 was me actively introducing a destructive action by not pausing to think through the failure mode.

### R4 — Judgment error: pushed forward with after-hours manual partial retry

**What I did:** After recovering from R3 and shipping the safety guard, the user asked me to ship the same-window retry and "run it now so we sell open tmr." I interpreted "run it now" as triggering `execute_partial_exit` directly via another one-shot script (this time WITH `_bootstrap_alpaca_credentials` called first).

**What I should have considered:** the 4:45 PM ET EOD partial-exit job is scheduled there for a reason — it runs at the end of the regular session when share reservations behave normally. Running at 9:30 PM ET is **extended hours**, where Alpaca's paper account holds shares as `held_for_orders` even when no stop exists for them, possibly due to pending-but-not-yet-released reservations from earlier-evening orders. The market sell could not get available shares. The replace succeeded (the broker happily replaced the stop), but the subsequent market sell failed. The rollback then failed. The user's "run it now so we sell open tmr" request was a reasonable operator intent, but the technical execution was not equivalent to "queue for tomorrow's open" the way I had framed it.

**Why this was a separate judgment error from R3:** R3 was about the bootstrap-vs-subprocess gap (R5's architectural absence). R4 was about not pausing to assess whether the action made sense at that hour at all. After R3's destructive event, the discipline should have been "stop and re-evaluate, don't push forward on live trade state." Instead I shipped the retry fix and immediately attempted another manipulation.

**The user's permission was not exculpatory.** The user trusted my framing that "running now queues for tomorrow open." That was wrong, and trusting the user's permission on a technical claim I had asserted incorrectly transfers the judgment error back to me.

### R5 — Architectural gap: no operator-confirm "trigger job once" path

**What's missing:** there is no in-band mechanism for an operator to invoke any of the scheduled trade-state jobs (partial-exit, stop-update, sync_positions, reconcile) outside their scheduled time, using the agent's proper bootstrap. The only paths are:
- Wait for the scheduler (correct, but slow)
- `docker exec python -c "..."` (subprocess, missing bootstrap — R3 footgun)
- Custom one-shot script with manual `_bootstrap_alpaca_credentials()` call (R4's approach — works, but no rate-limiting / safety-net beyond the script author's discipline)

The codebase has Telegram operator-confirm patterns (e.g., `/timestop TICKER`) for some workflows but not for partial-exit or sync. When a real operational need arises (like tonight's IBM partial), the absence forces ad-hoc tooling that has its own failure modes.

---

## What worked

Not to deflect — to identify load-bearing existing structures that kept the blast radius small.

1. **Audit log discipline.** Every event was logged. Reconstruction of "what state was the trade in 30 minutes ago" was possible because of audit rows. Without that, R3 would have been much harder to detect and would have required asking the broker for ground truth on every field.

2. **Broker-side is the source of truth, always.** Apollo's design treats Alpaca state as authoritative for position qty and protection. Even when DB went corrupt, broker state stayed clean. This is by intent (CLAUDE.md feedback memory `feedback_ground_truth_verification.md`) and it saved us.

3. **The user pushed back early.** User asked "what's the exact issue?" → "where's the 8 shares?" → "this is not good, do a post-mortem." Each was a precision tool that forced me to slow down. Especially the third: the post-mortem demand stops further pushing.

4. **The safety guard shipped post-R3 would have prevented R3.** That's not consolation; it's the smallest learning loop. The class of bug is now closed for future invocations from any path.

---

## Prevention

Ranked by impact, with explicit ship status.

### P1 — Already shipped tonight

- **`fa70976`** — `alpaca_client.replace_order_by_id` atomic replace; partial-exit no longer uses cancel-then-new. Closes R1.
- **`fa49304`** — `sync_positions` safety guard against mass-close on Alpaca-empty. Closes R2 + provides the mechanism that would have prevented R3's damage.
- **`f236976`** — Same-window 2-attempt retry inside `execute_partial_exit` with 1.5s backoff. Partial mitigation for transient broker errors during EOD window.

### P2 — Discipline rules (codify before next session)

- **Hard rule:** never run trade-state-mutating code via `docker exec python -c`. Save for tomorrow morning: write feedback memory `feedback_no_docker_exec_for_trade_state.md` enumerating the failure modes and forbidden patterns.
- **Hard rule:** on live trade state, the default is STOP and CONSULT (with operator + advisor), not ATTEMPT and RECOVER. Trade-state corruption isn't reversible by retrying — it's only reversible by audit-log reconstruction + manual SQL. Codify in CLAUDE.md.

### P2 — Operator-confirm Telegram commands (next session)

- **`/partialnow TRADE_ID`** — triggers `execute_partial_exit` inside agent process with proper bootstrap. Operator-confirm pattern, reuses `/timestop`-style flow. Sizing: ~50 LOC, one commit.
- **`/syncnow [ticker]`** — triggers `sync_positions` for one ticker (or all) inside agent process. Same pattern.

### P3 — Defensive checks (next session)

- Module-level guard in `alpaca_client.py` that asserts `ALPACA_PAPER_API_KEY` exists in `os.environ` before constructing any TradingClient. Fails loudly at the FIRST call from any path that skipped boot. Currently the SDK fails deep with a KeyError — easy to miss.
- Telegram alert taxonomy distinction: `⚠️ DB-DRIFT detected` (DB and broker disagree, broker authoritative, position safe) vs `🚨 NAKED POSITION` (broker has no stop, real risk). Today's `partial_exit_aborted` fired the latter when reality was the former. Operator can't tell.

### P4 — Architectural

- After-hours partial-exit behavior: the 4:45 PM ET scheduled job runs in extended hours where Alpaca paper reservations are quirky. Three options to evaluate:
  - Move partial-exit retry to **next-morning pre-open** (queue at 9:15 ET, execute at 9:30 open). Aligns with broker behavior windows; loses the "today's close price" methodology purity but recovers reliability.
  - **Accept the drift and document** that EOD partials can miss the day; tomorrow's job picks them up.
  - **Investigate** whether the 4:45 PM ET window is actually after-hours-quirky in normal practice (PURR succeeded earlier today at 9:37 AM ET intraday; what about pure 4:45 PM EOD?).

  Not for tonight. File as data-gated review with predicate "count of partial_exit_aborted events in 14d" — if ≥3, the after-hours behavior is structurally bad and needs design work.

### Discipline change — me (Claude), explicit

The advisor framed it cleanly: **on live trade state, default is STOP and CONSULT, not ATTEMPT and RECOVER.** Today I violated this twice (R3, R4) under operational pressure. The R3 violation was a destructive event; the R4 violation was a smaller-blast iteration of the same anti-pattern. The fact that I "recovered" both is misleading — the discipline rule is about not entering the state in the first place. Going forward: any trade-state-mutating action gets an explicit "this WILL touch live trade state, here's exactly what, here's the failure mode if it goes wrong, are we sure?" pause before execution.

---

## Verification

The prevention claims are not validated until:

1. **Tomorrow 9:35 AM ET** — Apollo runs morning_stop_refresh. IBM's `af4a1d47` stop should still be present + DB sees it.
2. **Tomorrow 4:45 PM ET** — Apollo runs `live_position_update`. IBM `execute_partial_exit` should fire (hold_days=6, still ≥5 forced partial path). With `replace_order` + same-window retry shipped, the partial should:
   - Atomically replace 26-share stop → 18-share stop
   - Market sell 8 shares
   - DB shows `partial_taken=t`, `remaining_shares=18`, broker has new stop for 18.
   - If this succeeds, P1 fixes are validated.
   - If this fails (any failure mode), the post-mortem's prevention section is premature and needs revision.

If verification fails: write addendum to this incident doc with the new findings + revised prevention.

---

## References

- Commits: `d3d092d` (morning triage start), `fa70976` (#136 replace_order), `fa49304` (#137 sync_positions guard), `f236976` (#136 retry). All on `main` deployed to prod 2026-05-27.
- Audit rows: `manual_db_restore` 2026-05-28 01:09:53 UTC, `manual_stop_order_id_resync` 2026-05-28 01:38:xx UTC.
- Tasks: #136, #137 in TaskList.
- Related: `feedback_ground_truth_verification.md`, `feedback_no_silent_trading_failures.md`.
