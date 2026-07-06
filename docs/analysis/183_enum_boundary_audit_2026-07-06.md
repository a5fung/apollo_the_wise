# #183 — Wire-boundary enum audit + change list (Fable block 1, 2026-07-06)

**The bug class (verified live 7/6):** `alpaca_client._order_to_dict` stringifies alpaca-py
enums raw — on prod Python 3.12, `str(OrderStatus.NEW)` = `"OrderStatus.NEW"`, so every wire
dict carries qualified strings for `status`/`side`/`type`. Sites comparing against plain
literals silently never match. The WS stream (raw payloads, not `_order_to_dict`) masks it —
which is exactly why the casualties are all FALLBACK paths: the ones that exist for when WS
fails. CHANGELOG session-5 filed it as "one root cause masquerading as N decoupled bugs";
this audit found all N.

**Contract:** this is the EXACT change list — a card applies it mechanically. Every consumer
of wire-dict `status`/`side`/`type` was classified (greps + per-site reads, 7/6).

---

## 1. THE FIX — normalize once at the boundary

`alpaca_client.py`: add a module-level helper + apply in `_order_to_dict`:

```python
def _enum_value(x) -> str | None:
    """'OrderStatus.NEW' -> 'new', 'OrderSide.BUY' -> 'buy', 'new' -> 'new'.
    The wire contract for _order_to_dict dicts: status/side/type are ALWAYS
    plain lowercase values (#183; same rule as order_manager._canonical_order_status,
    defined here because order_manager imports alpaca_client, not vice versa)."""
    if x is None:
        return None
    return str(x).split(".")[-1].lower()
```

In `_order_to_dict`: `"side": _enum_value(order.side)`, `"type": _enum_value(order.type)`,
`"status": _enum_value(order.status)`. (Legs recurse — covered automatically.)
NOTE for the card: check `_position_to_dict` for a `side` field (PositionSide.LONG class);
if present, apply `_enum_value` there too and grep its consumers the same way.

## 2. BROKEN TODAY → fixed/repaired by this change (4 sites)

| Site | Today | Change |
|---|---|---|
| `order_manager.py:338` (`check_fills`) `status == "filled"` | DEAD — polling fill detection never matches (WS masks) | Fixed by boundary alone |
| `order_manager.py:396` `status in ("cancelled", "expired", "rejected")` | DEAD — **and stays broken post-fix**: Alpaca's canonical spelling is one-L `"canceled"`, not in the tuple | **ALSO change the tuple** → reuse `_CANCEL_LIKE_ORDER_STATUSES` (has both spellings) |
| `order_manager.py:709` (`_check_day1_reentry`) `stop_order["status"] != "filled"` | DEAD — the originally-filed casualty | Fixed by boundary alone |
| `audit_invariants.py:116` (never-naked L1 broker-coverage fallback) `(o.get("side") or "").lower() == "sell"` | LATENT-BROKEN — `"orderside.sell" == "sell"` is False → broker coverage invisible EXACTLY when the DB stop pointer is NULL → **false naked L1 alarm** (the #433 class, on the L1 invariant) | Fixed by boundary alone; **ALSO harden the site** to `.endswith("sell")` (the #128 idiom) as defense-in-depth |

## 3. KEEP UNCHANGED — per-site defenses (now redundant-but-harmless; they also handle DB-side strings)

- `order_manager._canonical_order_status` + its 5 call sites (partial-exit verifies :1431/:1528;
  the order-status reconcile :2465/:2492/:2570) — the reconcile normalizes BOTH the DB and
  Alpaca sides; keep.
- `sync_positions` Path C inline `str(...).split(".")[-1].lower()` (:3077) — keep.
- `extract_stop_leg_id` (stop_price primary + case-insensitive type substring) — keep; its
  docstring already documents this exact bug class.
- #128 `_covered_by_broker` (scheduler :1501/:1518) and #433 `_find_replacement_stop`
  (trade_stream :316/:328) — `endswith("sell")` + substring idioms tolerate both forms; keep.

## 4. UNAFFECTED (verified, no change)

- **WS trade_stream event handling** — raw stream payloads, never `_order_to_dict`.
- **DB-sourced display sites** — `/trades` detail (`agent.py:6091+`) reads `mi_live_orders`
  rows whose `side` is INSERTed as plain literals; fine.
- **coverage_drift D2** — keys on `client_order_id` prefix (plain string) + writes side/type
  to audit detail only.
- **`mi_live_orders` data: NO migration needed** — verified on prod 7/6: `status` contains
  ONLY plain forms (filled/cancelled/canceled/expired/replaced/rejected) because the 15-min
  reconcile normalizes transitional rows on its cadence. Post-fix, INSERTs write plain forms
  immediately (a small consistency win; the reconcile keeps working unchanged).

## 5. BEHAVIOR CHANGE TO REVIEW CAREFULLY (the one real risk)

The fix brings DEAD fallback paths BACK TO LIFE. The card must verify the dedup guards with
tests before deploy:
- `check_fills` re-alive: it selects trades `WHERE status='order_placed'` — a fill already
  processed by WS has status='filled' → not selected → naturally deduped. PIN THIS with a
  test (WS-processed fill is not re-processed by polling).
- `_check_day1_reentry` re-alive: re-entry is gated by `entry_attempt < MAX_ENTRY_ATTEMPTS`
  AND R3 currently disables Day-1 re-entry entirely (verified live 7/6: WULF emitted
  `r3_day1_reentry_blocked`) — so no re-entries fire even with the path alive. PIN the
  attempt-count guard with a test anyway (R3 could be lifted later).
- The polling path firing duplicate TELEGRAMS: `check_fills`' fill Telegram only sends on the
  DB transition it performs; if WS did the transition, no dup. Covered by the first pin.

## 6. TESTS (the card adds; extend tests/test_stop_alert_false_naked_433.py's file or a new one)

1. `_enum_value` both-forms table: `"OrderStatus.NEW"→"new"`, `"new"→"new"`, `None→None`,
   real alpaca-py enum instances if importable in the test env.
2. Wire-contract pin: `_order_to_dict` on a stub order object with enum-shaped attrs yields
   plain `status="new"`, `side="buy"`, `type="stop_limit"` (this is the contract test that
   prevents regression).
3. `check_fills` fill-detection fires on `status="filled"`; WS-preprocessed trade not
   re-processed (dedup pin, §5).
4. :396 recognizes one-L `"canceled"` (via `_CANCEL_LIKE_ORDER_STATUSES`).
5. `audit_invariants` coverage check recognizes a sell stop in plain form (+ endswith
   hardening covers a hypothetical qualified form).
6. `_check_day1_reentry` attempt-count guard pin.

## 7. ROLLOUT

One card → one commit → deploy `market-agent` + `execution` (order_manager + audit_invariants
ship in both). Off-hours deploy fine. VERIFY next trading morning: check_fills logs show it
processing (or no-op'ing cleanly on WS-handled fills), zero duplicate fill Telegrams, no
naked-position L1 false alarms. The #426 FL-1 clock must NOT reset (no manual repair here —
this is a code deploy).

## Scope notes
- `execution_client` facade passes dicts through unchanged (transport only) — the fix lands
  wherever `_order_to_dict` runs (execution side in the split; combined locally). No facade change.
- Block-1's other folded items: today's money-path diffs were already reviewed (advisor +
  Sonnet + /simplify passes); the #367 read resolved unambiguously on Opus. Nothing further.
