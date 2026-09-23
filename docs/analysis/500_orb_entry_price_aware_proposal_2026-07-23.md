# #500 — Price-aware initial ORB entry + broker-cancel reason capture (CHANGE_PROCESS proposal)

**Status: PROPOSAL ONLY — no code changed, nothing deployed.** This is a money/execution-path
change (THE LINE): the live change happens only after the operator signs this CHANGE_PROCESS
entry. All evidence below is from read-only prod SQL (`docker exec apollo-market`, SELECTs only)
+ Polygon/market-data reads. Draft diffs live in this doc as text; they must be re-derived
against HEAD at implementation time.

Date: 2026-07-23. Author: agent (design + read-only backtest). Operator sign-off: **PENDING**.

---

## 1. The confirmed bug (ARWR 2026-07-22, live)

ARWR (+19.57% gap, Phase-3 SHASTA readout) → HIGH EP alert → ORB entry submitted 9:31:00.8 ET →
**Alpaca cancelled the entry within ~1 minute** (`pending_new → cancelled`; recorded by the 9:32
order-status reconcile, NOT the 10:00 cleanup). Operator saw "entry cancelled, no reason."

Root cause (confirmed read-only):

- **Initial entry** — `agents/market_intelligence/broker/order_manager.py::submit_entry`
  (~lines 215 and 231) ALWAYS places `alpaca.place_bracket_order(stop_price=orb_high,
  limit_price=stop_limit_buy_price(orb_high), ...)` — a stop-limit BUY triggered at the ORB
  high — with **no check of current price vs orb_high**. A buy stop that is already
  in-the-money at broker processing (last > stop) is invalid; Alpaca kills it instead of
  filling it.
- **Re-entry** — same file, `attempt_day1_reentry` (~611–695) ALREADY handles this:
  `latest = await alpaca.get_latest_trade(ticker)`; `if latest["price"] > orb_high:` →
  `place_limit_buy_with_stop(limit_price=round(latest*1.002, 2), ...)` instead of the bracket
  — added precisely because a stop-limit buy can't work when price is already above the stop.
- ARWR traded ~$89.06 (Alpaca reference; diagnosis) vs the $87.92 ORB high when the order
  landed. SMCI the same morning (+15.88%, sitting AT its ORB high) filled fine.
- Pattern: **the best EPs — violent gappers — are the most likely to blow through the ORB high
  before the 9:31 order lands, and they are exactly the ones that get cancelled.**
- Secondary: the WS cancel handler (`trade_stream.py::_handle_cancel_or_reject`, ~1040) writes
  `skip_reason = event_norm` — a bare `"cancelled"` — and Alpaca supplies no textual reason
  anywhere. Hence "no reason".

## 2. What the fix mirrors — and one thing it must NOT blindly copy

The design mirrors the re-entry branch (same price fetch, same `> orb_high` predicate, same
`latest × 1.002` limit formula, same `place_limit_buy_with_stop` call shape, same
account_mode/COID threading). Two honesty caveats found during this review:

1. **The re-entry limit branch has NEVER fired in prod.** `mi_live_orders` contains 89 buy
   entries, ALL `order_type='stop_limit'`, zero `'limit'`. "Existing, tested logic" = code
   parity + kill-switch tests (`tests/test_moneypath_audit_fixes.py`), NOT battle-tested parity.
   The #500 change must carry direct unit tests for the branch (both entry and re-entry).
2. **Latent naked-order bug in `place_limit_buy_with_stop`** (`alpaca_client.py:770-804`): it
   passes `stop_loss={"stop_price": ...}` as a plain dict and does **NOT** pass
   `order_class=OrderClass.OTO`. CLAUDE.md's own documented gotcha: *"Always
   `order_class=OrderClass.OTO` — alpaca-py silently drops `stop_loss` kwarg without it."*
   `place_bracket_order` (line 294-330) passes `OrderClass.OTO` + `StopLossRequest` AND has a
   naked-order guard (extract stop leg, else cancel + raise). `place_limit_buy_with_stop` has
   neither. If the gotcha applies to `LimitOrderRequest` the same way, the fallback would fill
   a position with NO broker stop. **Required hardening (also fixes the re-entry path):** add
   `order_class=OrderClass.OTO` + `StopLossRequest(...)` + the same stop-leg guard, and smoke
   the order shape on the paper account before ship.

## 3. Fix design — `submit_entry` price-aware branch

### Behavior

At submission time (after the /pause peek + atomic `confirmed → submitting` claim, before
placing the order):

1. `latest = await alpaca.get_latest_trade(ticker)` (Alpaca's own feed — the right reference,
   since Alpaca does the cancelling; same call the re-entry and fade-guard already use; no
   account_mode needed — data client).
2. **`latest.price <= orb_high` or `latest` is None/flaky → byte-identical today's path**
   (stop-limit bracket). Fail-open to current behavior on any data problem — a data flake must
   never change entry mechanics.
3. **`latest.price > orb_high` → today's order is a guaranteed broker cancel.** Fall back to
   `place_limit_buy_with_stop`:
   - **Limit price** = `round(latest.price * 1.002, 2)` — the exact re-entry formula (20 bps
     over last trade; bounds slippage vs the observed price).
   - **Chase cap (NEW — the re-entry has no ceiling and this proposal says it needs one
     here):** entry shares were sized on planned risk `orb_high − stop_price`; a fallback fill
     at `limit` carries actual risk `limit − stop_price`. Gate:
     `actual_risk <= CHASE_RISK_INFLATION_CAP × planned_risk`, with
     `CHASE_RISK_INFLATION_CAP = 1.5` (env-tunable). Exceeded → NO entry: status `cancelled`,
     new skip reason `setup:chase_cap_exceeded` (+ audit event + Telegram via `humanize()` —
     the terminal-failure contract).
     - Calibration on the historical class (§5): ARWR = 1.37× → **admitted** (headroom to
       ~+2.0% above its ORB high); CADL (+14.8% chase) = 11.3× → **skipped** (its sim lost
       −3R/−11R; chasing that far is toxic).
     - Worst-case realized risk on an engaged entry = 1.5 × the standard 1% = **1.5% of
       equity** on a full stop-out (vs 1.0% today). Explicit operator acceptance required
       (§7, decision 2).
   - **Stop-loss leg** = `trade["stop_price"]` — unchanged (ORB low for MAGNA53; prior-day low
     for 9M Day 2). Same OTO child as the bracket, after the §2.2 hardening.
   - **Threading** — unchanged: `account_mode` from the trade row; COID via
     `make_client_order_id(account_mode, signal_type, ticker)` (fresh COID on retry, as today);
     stop-leg capture via `extract_stop_leg_id` + REST refetch (as today).
4. **Retry semantics** — the existing 1-retry-after-5s wraps the branch: the retry re-runs the
   price fetch + branch selection + cap gate (5s is long at 9:31; the branch must re-decide).
   Terminal failure path (`order_failed` + Telegram) unchanged.
5. **DB record honesty** — the `mi_live_orders` INSERT currently hardcodes
   `order_type='stop_limit'`, `stop_price=orb_high`, `limit_price=stop_limit_buy_price(orb_high)`.
   Write the ACTUAL order: `order_type='limit'`, `stop_price=NULL`, `limit_price=<fallback
   limit>` when the branch engages. (Note: the re-entry INSERT records the legacy columns even
   for its limit orders — do not copy that inaccuracy.)
6. **Scope** — `submit_entry` serves every initial entry: ORB monitor auto-entries (MAGNA53 +
   9M Day 2, paper + live) and `telegram_confirm` manual confirms. Initial entries only occur
   in the 9:31–9:44 ORB window (magna53_ep.md submission-window rules), so the branch's
   engagement window is bounded. The 10:00 cleanup remains the time-bound for an unfilled
   resting fallback limit — identical to the bracket today.

Explicitly UNCHANGED (THE LINE): detection/scoring/alerting, sizing (`entry_shares` computed
exactly as today), stops, all safeguards (`_check_safeguards`, /pause peek, caps, breakers —
all run before/around this code and are untouched), the ORB window, the 10:00 cleanup. Only the
ENTRY ORDER TYPE changes, and only in the state where today's order is a guaranteed cancel.

### Draft diff (draft — do NOT apply as-is; re-derive against HEAD)

```diff
--- a/agents/market_intelligence/broker/order_manager.py
+++ b/agents/market_intelligence/broker/order_manager.py
@@ module constants (near stop_limit_buy_price)
+# #500: bound the price-aware fallback's chase. Shares are sized on PLANNED
+# risk (orb_high - stop); a fallback fill at `limit` carries ACTUAL risk
+# (limit - stop). Cap actual/planned so a runaway gapper can't silently
+# multiply per-trade risk (CADL 2026-04-20 would have been 11.3x). 1.5x =
+# worst-case 1.5% equity on a full stop-out at standard 1%-risk sizing.
+CHASE_RISK_INFLATION_CAP = float(os.getenv("CHASE_RISK_INFLATION_CAP", "1.5"))
@@ imports
 from agents.market_intelligence.broker.skip_reasons import (
     BLOCK_REENTRY_GAP_THROUGH,
     INFRA_ORDER_SUBMIT_FAILED,
+    SETUP_CHASE_CAP_EXCEEDED,
     ...
 )
+from agents.market_intelligence.broker.skip_reasons import humanize
@@ async def submit_entry(trade_id: int) -> dict | None:
     ticker = trade["ticker"]
     account_mode = trade.get("account_mode") or current_account_mode()
     signal_type = trade.get("signal_type") or "unknown"
-    coid = alpaca.make_client_order_id(account_mode, signal_type, ticker)
+    orb_high = float(trade["orb_high"])
+    stop_loss = float(trade["stop_price"])
+
+    async def _pick_entry() -> tuple[str, float | None]:
+        """('stop_limit', None) = today's bracket; ('limit', px) when price is
+        already above the ORB high (mirrors attempt_day1_reentry ~615).
+        Fail-open: any data problem -> the bracket (today's behavior)."""
+        latest = await alpaca.get_latest_trade(ticker)
+        if latest and latest.get("price") and float(latest["price"]) > orb_high:
+            return "limit", round(float(latest["price"]) * 1.002, 2)
+        return "stop_limit", None
+
+    async def _submit(entry_type: str, fallback_limit: float | None, coid: str) -> dict:
+        if entry_type == "limit":
+            logger.info(
+                f"{ticker}: price above ORB high {orb_high:.2f} — "
+                f"limit-buy fallback at {fallback_limit:.2f} (#500)"
+            )
+            return await alpaca.place_limit_buy_with_stop(
+                ticker=ticker, qty=trade["entry_shares"],
+                limit_price=fallback_limit, stop_loss_price=trade["stop_price"],
+                account_mode=account_mode, client_order_id=coid,
+            )
+        return await alpaca.place_bracket_order(
+            ticker=ticker, qty=trade["entry_shares"],
+            stop_price=trade["orb_high"],
+            limit_price=stop_limit_buy_price(trade["orb_high"]),
+            stop_loss_price=trade["stop_price"],
+            account_mode=account_mode, client_order_id=coid,
+        )
+
+    async def _chase_cap_blocked(fallback_limit: float) -> str | None:
+        planned = orb_high - stop_loss
+        actual = fallback_limit - stop_loss
+        if planned > 0 and actual <= CHASE_RISK_INFLATION_CAP * planned:
+            return None
+        return (
+            f"{SETUP_CHASE_CAP_EXCEEDED}: limit ${fallback_limit:.2f} risk "
+            f"${actual:.2f}/sh vs planned ${planned:.2f} "
+            f"(cap {CHASE_RISK_INFLATION_CAP:.2f}x, ORB high ${orb_high:.2f})"
+        )
+
+    entry_type, fallback_limit = await _pick_entry()
+    if entry_type == "limit":
+        reason = await _chase_cap_blocked(fallback_limit)
+        if reason:
+            await _update_trade_status(trade_id, "cancelled", skip_reason=reason)
+            await log_audit_event(
+                "entry_chase_cap_skipped",
+                f"{ticker} [{account_mode}]: {reason}",
+                json.dumps({"trade_id": trade_id, "ticker": ticker,
+                            "orb_high": orb_high, "stop": stop_loss,
+                            "limit": fallback_limit}),
+            )
+            await send_telegram_message(
+                f"{mode_prefix(account_mode)}⚠️ No entry for {ticker}: {humanize(reason)}"
+            )
+            return None
+
+    coid = alpaca.make_client_order_id(account_mode, signal_type, ticker)
     try:
-        order = await alpaca.place_bracket_order(
-            ticker=ticker, qty=trade["entry_shares"],
-            stop_price=trade["orb_high"],
-            limit_price=stop_limit_buy_price(trade["orb_high"]),
-            stop_loss_price=trade["stop_price"],
-            account_mode=account_mode, client_order_id=coid,
-        )
+        order = await _submit(entry_type, fallback_limit, coid)
     except Exception as e:
         # 1 retry after 5s for transient errors
         logger.warning(f"Entry order failed for {ticker}, retrying: {e}")
         await asyncio.sleep(5)
         try:
-            coid = alpaca.make_client_order_id(account_mode, signal_type, ticker)
-            order = await alpaca.place_bracket_order(...)
+            # Re-decide: 5s is long at 9:31 — price may have crossed either way.
+            entry_type, fallback_limit = await _pick_entry()
+            if entry_type == "limit":
+                reason = await _chase_cap_blocked(fallback_limit)
+                if reason:
+                    await _update_trade_status(trade_id, "order_failed", skip_reason=reason)
+                    await send_telegram_message(
+                        f"{mode_prefix(account_mode)}⚠️ No entry for {ticker}: {humanize(reason)}"
+                    )
+                    return None
+            coid = alpaca.make_client_order_id(account_mode, signal_type, ticker)
+            order = await _submit(entry_type, fallback_limit, coid)
         except Exception as e2:
             ... (unchanged order_failed path)
@@ mi_live_orders INSERT (record the ACTUAL order placed)
-            VALUES ($1, $2, $3, 'buy', 'stop_limit', $4, $5, $6, $7, $8::jsonb)
+            VALUES ($1, $2, $3, 'buy', $9, $4, $5, $6, $7, $8::jsonb)
             ...
-            float(trade["orb_high"]),
-            stop_limit_buy_price(float(trade["orb_high"])),
+            (float(trade["orb_high"]) if entry_type == "stop_limit" else None),
+            (fallback_limit if entry_type == "limit"
+             else stop_limit_buy_price(float(trade["orb_high"]))),
+            ..., entry_type,
```

```diff
--- a/agents/market_intelligence/broker/alpaca_client.py   (§2.2 hardening, REQUIRED)
+++ b/agents/market_intelligence/broker/alpaca_client.py
@@ async def place_limit_buy_with_stop(...)
         req_kwargs = dict(
             symbol=ticker, qty=qty,
             side=OrderSide.BUY, type=OrderType.LIMIT,
             time_in_force=TimeInForce.DAY,
             limit_price=round(limit_price, 2),
-            stop_loss={"stop_price": round(stop_loss_price, 2)},
+            order_class=OrderClass.OTO,
+            stop_loss=StopLossRequest(stop_price=round(stop_loss_price, 2)),
         )
         if client_order_id:
             req_kwargs["client_order_id"] = client_order_id
         order = client.submit_order(LimitOrderRequest(**req_kwargs))
+        # Same naked-order guard as place_bracket_order: Alpaca must have
+        # accepted the stop leg, else cancel the entry and raise.
+        if not extract_stop_leg_id(order):
+            try:
+                client.cancel_order_by_id(order.id)
+            except Exception as cancel_err:
+                logger.error(f"Failed to cancel naked limit-buy {ticker} {order.id}: {cancel_err}")
+            raise RuntimeError(
+                f"Limit-buy {order.id} for {ticker} returned no stop_loss leg — "
+                f"Alpaca rejected the stop. Entry cancelled."
+            )
```

```diff
--- a/agents/market_intelligence/broker/skip_reasons.py
+++ b/agents/market_intelligence/broker/skip_reasons.py
@@ setup:
+SETUP_CHASE_CAP_EXCEEDED   = "setup:chase_cap_exceeded"   # #500 bounded-chase gate
@@ new category (see §4):
+# ── broker: the BROKER killed an accepted order (cancel/reject/expire) ──────
+BROKER_ENTRY_CANCELLED = "broker:entry_cancelled"
+BROKER_ENTRY_REJECTED  = "broker:entry_rejected"
+BROKER_ENTRY_EXPIRED   = "broker:entry_expired"
@@
-VALID_CATEGORIES = frozenset({"filter", "setup", "block", "infra", "window"})
+VALID_CATEGORIES = frozenset({"filter", "setup", "block", "infra", "window", "broker"})
@@ _HUMAN_LABELS:
+    SETUP_CHASE_CAP_EXCEEDED:  "Ran too far past ORB high to chase",
+    BROKER_ENTRY_CANCELLED:    "Broker cancelled the entry order",
+    BROKER_ENTRY_REJECTED:     "Broker rejected the entry order",
+    BROKER_ENTRY_EXPIRED:      "Entry order expired unfilled",
```

## 4. Capture-the-reason fix ("no reason" never recurs)

Where the bare reason is written: `trade_stream.py::_handle_cancel_or_reject` line ~1043
(`skip_reason = event_norm` → literal `"cancelled"`), plus `check_fills` line ~413
(`skip_reason=status` — same bare form on the polling path).

**What Alpaca gives us:** no textual cancel/reject reason exists anywhere in the API — not on
the order object, not in the WS payload, not on the dashboard (confirmed in the ARWR incident).
The order's terminal snapshot only carries the lifecycle timestamps (`canceled_at`,
`failed_at`, `expired_at`). So the fix is: **persist what Alpaca does send, and synthesize the
diagnosis Alpaca won't.**

1. **Synthesized diagnosis at event time** (both WS + polling paths): fetch
   `get_latest_trade(symbol)` and compare against the entry trigger
   (`entry_trade["entry_price"]` = orb_high; already SELECTed in the WS handler for the #475
   telemetry). Write a prefixed, humanizable reason instead of the bare word:
   - `broker:entry_cancelled: last $89.06 above trigger $87.92 at event — in-the-money stop
     (#500 class)`
   - `broker:entry_rejected: last $102.36 near trigger $102.46 at event` (LULD/AEHR class —
     the raw payload + timing distinguish it on drill-down)
   - Errors in the diagnosis fetch degrade to `broker:entry_cancelled` with no detail — never
     block the status update or the Telegram.
2. **Persist the terminal order snapshot**: in the same handler, update the `mi_live_orders`
   row — `status = event_norm`, `cancelled_at = COALESCE(cancelled_at, <event ts>)`, and merge
   the final order dict (with Alpaca's lifecycle timestamps) into `raw_response`
   (`raw_response || $n::jsonb`, keyed `"terminal"`). Today `cancelled_at` is backfilled with
   reconcile-run `NOW()` — the April cohort rows all show a meaningless `09:00:00`.
3. **Telegram** (existing cancel/reject alert, line ~1080): append the humanized reason —
   `🗑 Entry CANCELLED: ARWR — Broker cancelled the entry order (last $89.06 above trigger
   $87.92 — in-the-money stop)`.
4. **The #475 audit row** gains `"diagnosis"` + the terminal snapshot — the
   `entry_order_rejections_systematic` review then classifies itself.
5. **Race-awareness (observed in this backtest, §5):** AVAV 5/28, MRVL 6/2, LION 6/17 are
   10:00/10:15 CLEANUP cancels whose rows ended up with the WS's bare `"cancelled"` instead of
   `"ORB window unfilled"` — the WS event beat/overwrote the cleanup's DB write (same race
   class as the 7/17 CLSK false-positive filed on #184). The capture fix keeps these
   informative regardless of which writer wins; the write-ordering itself stays #184's scope.

## 5. Backtest / evidence (read-only prod SQL + Polygon)

**Cohort**: all `mi_live_trades` entry deaths, full history (2026-04-16 → 2026-07-22).
`status='cancelled'` splits: 29 × `'ORB window unfilled'` + 1 × `'EOD unfilled'` (deliberate
cleanup — out of scope) + 4 × empty reason (the #436 phantom-proposal class — out of scope) +
**11 × bare broker event** (`'cancelled'/'canceled'/'rejected'/'expired'` — the class under
study; 9 paper, 2 live; 10 magna53, 1 9m_day2). Per-row classification against the tape
(Polygon SIP second/minute aggs at the submission timestamp + `mi_live_orders` lifecycle):

| # | Ticker | Date | Mode | Submit (ET) | Price@submit vs ORB-high | Cancel timing | Class |
|---|---|---|---|---|---|---|---|
| 1 | **ARWR** | 07-22 | live | 9:31:00.8 | **above** (~$89.06 Alpaca ref; SIP prints straddle 87.9 at :00–:01, minute high 89.21) | ≤ 9:32 (broker) | **#500: in-the-money stop** |
| 2 | **CADL** | 04-20 | paper | 11:19:06 | **+14.8% above** ($7.49 vs $6.52) | broker | **#500: in-the-money stop** (pre-window era) |
| 3 | AEHR | 07-15 | live | 9:31:03 | −0.10% (at trigger) | rejected ≤ 9:32 | LULD/exchange reject (#475, filed) |
| 4 | MRVL | 06-02 | paper | 9:31:10.8 | −2.0% | 10:00 cleanup (WS-race mislabel) | gap-through-limit: crossed trigger AND $261.10 limit within 9:31; unfilled |
| 5 | LION | 06-17 | paper | 9:31:11 | −0.13% | 10:15 cleanup (mislabel) | gap-through-limit (crossed within 9:31) |
| 6 | AVAV | 05-28 | paper | 9:31:10.4 | −4.0% | 10:00 cleanup (mislabel) | crossed at 9:48 in-window, unfilled → gap-through-limit |
| 7 | RDW | 05-26 | paper | 9:31:02.4 | −2.3% | expired EOD | gap-through-limit (crossed 9:32, H 19.90 > limit 19.78) |
| 8–11 | SIRI, GSHD, CHE, AEHR | 04-16..24 | paper | various | below | expired/legacy cleanup | benign: ORB high never reached — correct no-fill |

**N for the #500 class: 2 of 11** (1 live, 1 paper) over ~3.2 months ≈ 2% of the 89 entry
submissions — **small but real, and concentrated exactly in the top tier**: ARWR gap +19.6%
score 80; CADL gap +17.0% score 100. The broader pattern is stark: **4 of the 5 in-window
broker-side entry deaths since May ran ≥ +7% past the ORB high the same day** (ARWR +8.6%,
AEHR-7/15 +7.6%, MRVL +12.1%, RDW +17.4%) — the entry mechanism fails preferentially on the
strongest names. #500 fixes ONE of the three failure classes (in-the-money stop); LULD rejects
stay with the #475 review and gap-through-limit stays with the #22 telemetry / magna53_ep.md
known-limitation 4 — named here so their misses aren't silently attributed to this fix.

**Would the bounded fallback have been profitable?**

- **ARWR (the class member the fix targets):** planned risk $3.58/sh, stop $84.34 (never hit
  after 9:31). Entry bounds: $88.10 (SIP bar-open floor ×1.002) → +0.16R at the day-1 close
  ($88.66); $89.24 (diagnosed $89.06 ×1.002) → −0.16R at the close. Rest-of-day high $95.49 →
  **MFE +1.7R to +2.1R**. Risk inflation 1.05–1.37× (within the 1.5× cap, which for ARWR's
  geometry admits up to ~$89.71 = +2.0% above the ORB high). Day-1-close is a deliberately
  conservative proxy — the real system holds through partials (day 3–5) and an SMA trail; the
  fix's value is participation in the violent-gapper winner cohort, which this cohort shows the
  current mechanism systematically misses.
- **CADL (the class member the cap rejects):** +14.8% chase → risk inflation 11.3×. Sim: day-1
  close −3.05R; multi-day stop-first −11.3R (planned-risk units; day-1 MFE +1.63R). Chasing
  that far converts a $0.10-risk entry into a $1.08-risk entry — this single case is the
  cap's justification, and it is the ONLY historical candidate the cap drops (§7, decision 3).

**Data limits (explicit):**

- Feed asymmetry: Polygon SIP second-prints at ARWR's submit second straddle $87.9, while the
  confirmed diagnosis has Alpaca's reference at $89.06; the same-minute SIP high (89.21)
  confirms the runup. The fix branches on Alpaca's own `get_latest_trade` — the correct
  reference, since Alpaca is the party doing the cancelling. Exact submit-millisecond prices
  are unknowable from aggregates; second aggs have gaps on thin tape (LION, CADL).
- `mi_live_orders.cancelled_at` is a reconcile-write `NOW()`, not Alpaca's cancel time (April
  rows all read 09:00:00) — broker cancel timing is bounded (≤ 1 min for ARWR/AEHR via the
  9:32 records) but not exact. Fixed going forward by §4.2.
- Multi-day sims ignore management (no partials/trail) — stop-first daily-bar approximation.
- Paper-mode fills are Alpaca's simulator; the two live cases (ARWR, AEHR) are the only
  real-broker data points.
- N=2 is far below the N≥10 discipline bar for THRESHOLD changes. Claimed basis: the branch
  itself is a **correctness fix** (an order type that cannot work in the observed state —
  same class as the 2026-05-20 "gate inversion" precedent where sample-size discipline was
  ruled inapplicable), while the **cap value (1.5×) IS a threshold calibrated on N=2** and is
  flagged as such — mitigated by env-tunability, the fail-safe failure direction (a too-tight
  cap costs a missed entry, never a bad fill), and the bounded worst case (1.5% equity).

## 6. Risk / safeguard review

- **Not changed:** detection, scoring, alerting, sizing (shares identical), stop levels, ORB
  window, 10:00 cleanup, all safeguards (they gate before/around this code), account-mode
  invariants (COID minting + per-mode client routing identical). The branch engages ONLY when
  the status-quo outcome is a guaranteed cancel — when it engages correctly, the fix strictly
  dominates today (bounded fill or clean rest-then-cleanup, vs certain death).
- **New risk 1 — bounded risk inflation:** engaged entries can realize up to 1.5× planned risk
  (1.5% equity worst case) because shares aren't resized. Bounded by the cap; needs explicit
  operator acceptance. (Resizing shares at the fallback price would hold risk at exactly 1%,
  but that is a SIZING change — out of this proposal's scope by design; noted only so the
  operator knows the alternative exists.)
- **New risk 2 — mis-trigger on a bad/stale print:** if `latest` wrongly reads above orb_high,
  the marketable limit fills immediately near market — possibly BELOW the ORB high, i.e. a
  pre-trigger fill. Consequences are bounded (fill at market, stop unchanged, risk geometry
  smaller than planned) but it's an entry-discipline deviation. Post-open Alpaca prints at
  9:31+ are fresh; the re-entry has run the same exposure since May. Residual accepted.
- **New risk 3 — worse fills vs the bracket:** the bracket's limit is `orb_high × 1.005`; the
  fallback's is `latest × 1.002` (higher, by construction, since latest > orb_high). That IS
  the fix — paying up to at most cap-bounded distance for a breakout already in progress.
  Slippage beyond `latest × 1.002` is impossible (limit semantics); no-fill decays to the
  10:00 cleanup exactly like an untriggered bracket.
- **Fade guard:** unaffected — runs upstream in the pipeline (MAGNA53 HIGH passes None; 9M
  Day 2 0.25); the engaged state (price ABOVE orb_high) is definitionally not a fade state.
- **Position-notional cap:** the 20%-of-equity share cap was computed at orb_high; an engaged
  fill at ≤ cap-distance above it can exceed 20% by ≤ ~2% relative (≈20.4% worst case).
  Negligible; noted.
- **Race residual:** price crossing orb_high between our check and Alpaca's processing still
  produces today's cancel — now visibly labeled by §4. A cancel-triggered one-shot fallback
  retry (option B) is deliberately DEFERRED: observe the post-fix residual rate via the
  `broker:entry_cancelled` rows first (data-gated), rather than adding a second submit path in
  the same change.
- **Kill/reversion:** reversion = delete the branch (restores the unconditional bracket);
  `/pause` + `LIVE_TRADING_ENABLED` cover it like any entry. No new state, no new job, no
  schema change (skip-reason strings + one INSERT parameter only).

## 7. Operator decision points (sign-off checklist)

1. **Approve the price-aware fallback branch** in `submit_entry` (money-path order-type
   change) + the §2.2 `place_limit_buy_with_stop` OTO/naked-guard hardening (required; also
   fixes the latent re-entry exposure).
2. **Cap form + value:** risk-inflation ≤ 1.5× (recommended) — accepts worst-case 1.5% equity
   on engaged entries. A tighter 1.25× would have SKIPPED ARWR (1.37×) — recommended against.
3. **Drop-list review (CHANGE_PROCESS rule 3 HARD gate):** the cap's full historical drop list
   is **{CADL 2026-04-20}** (sim −3R/−11R). Operator confirms this list is correctly dropped.
4. **Reason-capture** (§4: `broker:` skip-reason category + terminal-snapshot persistence +
   humanized Telegram) — observability only; recommend yes.
5. **Option B (cancel-triggered one-shot fallback retry): defer** — recommend yes (data-gated
   on post-fix residual `broker:entry_cancelled` rows).

## 8. Test + verify plan (pre-ship / post-ship)

- **Unit tests (new, `tests/test_500_price_aware_entry.py`):** below/at orb_high → bracket
  byte-identical; above → limit order with `latest×1.002`; above + cap → skip with
  `setup:chase_cap_exceeded` + Telegram; `get_latest_trade` None/error → bracket (fail-open);
  retry path re-decides branch + cap; mi_live_orders row records actual type/limit; naked-guard
  raise on missing stop leg. Plus a direct test of the re-entry branch (currently untested
  directly) and §4 reason-capture tests (WS + polling paths; diagnosis-fetch failure degrades
  gracefully).
- **Paper smoke before live deploy:** place one OTO limit-buy-with-stop on the paper account
  off-hours; verify the stop leg comes back (the §2.2 alpaca-py gotcha check).
- **Deploy** via `bash scripts/deploy.sh market-agent` (respecting the deploy-timing memory:
  not 9:25–10:05 or 16:00–17:00 ET).
- **Verify-live (the class is rare — verify in layers):** (L1, deploy day) normal below-orbH
  entries produce byte-identical brackets; (L2, first engagement — paper or live) a
  `limit-buy fallback` log line + OTO stop leg present + honest mi_live_orders row; (L3) the
  next broker cancel of any entry carries a `broker:*` reason with price diagnosis — never a
  bare `"cancelled"` again. Task stays `deployed` until L2/L3 observed.

## 9. Draft CHANGE_PROCESS change-log entry (for `docs/setups/magna53_ep.md`; cross-ref line in `ninem.md`; `entry_pipeline.md` + skip-reason count updated same commit)

```
### 2026-07-XX — #500 Price-aware initial ORB entry: bounded limit-buy fallback when price is
already above the ORB high (+ broker-cancel reason capture)

**Trigger**: ARWR 2026-07-22 (live) — +19.57% gap HIGH EP; the 9:31:00.8 stop-limit bracket
went pending_new → cancelled by Alpaca within ~1 min because price (~$89.06) was already above
the $87.92 ORB-high trigger; operator saw "entry cancelled, no reason." SMCI (at its ORB high)
filled the same morning. The re-entry path has handled exactly this since May
(attempt_day1_reentry ~615); the initial entry never did.

**Evidence**: docs/analysis/500_orb_entry_price_aware_proposal_2026-07-23.md — full-history
cancelled-entry cohort N=11 (read-only prod SQL + SIP tape): in-the-money-stop class N=2
(ARWR live, CADL paper) — FLAGGED small-N (below the N≥10 bar; the branch is an order-type
correctness fix per the 2026-05-20 gate-inversion precedent, but the 1.5× chase cap IS a
threshold calibrated on N=2). ARWR fallback sim: +0.16R/−0.16R day-1-close bounds, MFE
+1.7R–2.1R, risk inflation ≤1.37×. CADL (+14.8% chase, 11.3× inflation, −3R/−11R sims) is the
cap's sole historical drop — operator reviewed per rule 3. Adjacent classes NOT fixed (named
to prevent attribution drift): LULD rejects (#475), gap-through-limit (#22 / known-limitation 4).

**Anticipated effect**: entries where price ≤ ORB high at submit — byte-identical bracket
(zero behavior change; the overwhelming majority). When price > ORB high at submit (~2% of
submissions historically, concentrated in the strongest gappers): a bounded limit buy
(latest×1.002, risk-inflation cap 1.5×, worst case 1.5% equity) replaces a guaranteed broker
cancel; beyond the cap → setup:chase_cap_exceeded skip (fail-safe: missed entry, never a bad
fill). Broker cancels/rejects now persist a broker:* skip_reason with a price-vs-trigger
diagnosis + Alpaca's terminal order snapshot — "no reason" cannot recur. Est. ~1 engaged
entry / 6 weeks at current alert volume.

**Reversion-flag**: NEW for submit_entry (extends the re-entry's price-aware branch — in code
since May, never fired in prod — to the initial entry, with a new chase bound the re-entry
lacks). Hard revert = delete the branch (restores the unconditional bracket) + revert the
skip-reason additions; the place_limit_buy_with_stop OTO hardening should survive any revert
(it fixes a latent naked-order bug independently).

**Status**: PROPOSED — awaiting operator sign-off (decisions §7 of the analysis doc). On ship:
deployed → verify-live per §8 layers.
```

---

*Probes (run read-only 2026-07-23): cohort survey + per-order lifecycle from `mi_live_trades` /
`mi_live_orders` / `mi_audit_log` in the prod container; classification + sims from Polygon SIP
1-second/1-minute/daily aggs via `collector._polygon_get`. No production file, config, or DB row
was modified.*
