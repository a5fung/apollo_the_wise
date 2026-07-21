# #483 — "exit-leg double-count" diagnosis: NOT A BUG (pre-R3 re-entry, already fixed)

**Date:** 2026-07-21 · **Scope:** READ-ONLY trace · **Verdict:** No open code bug; go-forward provably clean.

## The carried hypothesis (refuted)
#483 was filed as: *"a re-fired stop appends a 2nd full-position `stop_hit` exit leg, both summed →
P&L doubled"* — with MRAM (−$2,199 vs an assumed real ~−$1,100) as the example, and a suspected
missing idempotency guard in the live exit-recording path.

**The data does not support this.** The 2nd legs are not duplicate recordings of one fill.

## Ground truth (`mi_live_trades`, account_mode=paper)
Every row with ≥2 `stop_hit` legs, and only these 5:

| id | ticker | first stop | entry_attempt | legs | note |
|----|--------|-----------|---------------|------|------|
| 34 | OMCL | 2026-04-28 | 2 | stop@43.50 (att1) → stop@45.01 37min later (att2) | distinct price/time |
| 57 | TEAM | 2026-05-01 | 2 | stop@82.56 (att1) · **partial_profit@89.51** · stop@85.18 (att2, backfill_5_07) | genuine multi-day 2nd trip |
| 81 | AMD | 2026-05-06 | 2 | stop@405.57 (att1, 5/06) → stop@405.59 (att2, **5/07**) | different days |
| 82 | SMCI | 2026-05-06 | 2 | stop@31.23 (att1) · **partial_profit@32.97** · stop@32.57 (att2, 5/12) | genuine multi-day 2nd trip |
| 120| MRAM | 2026-05-11 | 2 | stop@33.89 (att1, 13:42) → stop@33.88 (att2, 13:59) | 17-min same-day; see below |

All are `entry_attempt=2` — the **pre-R3 Day-1 re-entry** path (`order_manager.py::attempt_day1_reentry`,
lines 484–501): att1 stop is recorded, a 2nd bracket is placed (attempt 2), and if it fills+stops a 2nd
`stop_hit` leg is recorded. This is two distinct round-trips, not one fill logged twice — proven by:
- distinct fill prices/times on the two legs;
- SMCI/TEAM carry their own `partial_profit` leg **between** the two stops (a real held 2nd position);
- there is no missing guard — the legs correctly reflect what the simulator executed.

## Already fixed for go-forward — R3 ship (2026-05-17)
`order_manager.py:505–544`: R3 **disabled Day-1 same-day re-entry** (0/6 win rate over 60d; a failed
first breakout invalidates the setup). With `R3_DAY1_REENTRY_ENABLED` unset (default false, **confirmed
unset in prod**), `attempt_day1_reentry` now closes at att1 and returns — no 2nd bracket, no att2 leg.

**Verification (2026-07-21):** `mi_live_trades` rows with ≥2 `stop_hit` legs → **5, all pre-R3, 0 post-R3**;
`entry_attempt≥2` with `filled_at ≥ 2026-05-17` → **0**. Go-forward is clean by construction + by data.

## The P&Ls are CORRECT — no residual (traced, not inferred)
An earlier draft speculated MRAM's att2 was a "paper-simulator phantom fill" inflating the loss. **That
was wrong — traced and refuted.** The paper account fills via Alpaca's **paper API (a real simulated
order book)**, not an internal simulator; `source="websocket"` = the Alpaca paper trade-update stream.
Every fill is a real order with a real UUID and fill price.

MRAM trade 120 (orb_high 36.425, orb_low/stop 34.07), from `mi_live_orders`:

| order | side | type | filled_avg_price | leg |
|-------|------|------|------------------|-----|
| 54 | buy | stop_limit | **36.52** | att1 entry |
| 56 | sell | stop | **33.890096** | att1 stop → leg1 −$1,101.93 ✓ |
| 61 | buy | stop_limit | **36.50** (filled 13:50) | att2 entry |
| (OTO stop) | sell | stop | **33.88** | att2 stop → leg2 −$1,097.78 ✓ |

The market genuinely whipsawed on 5/11: stop att1 @33.89 (13:42) → **rallied through orb_high 36.425,
filling the re-entry @36.50 (13:50)** → dropped and stopped att2 @33.88 (13:59). Violent for a small-cap
but real. Both legs' P&L reconcile exactly to `(stop − entry) × 419`. **MRAM's −$2,199.71 is the correct
sum of two real round-trips.** The operator's "real was ~−$1,100" is att1 only.

**All 5 rows verified (2026-07-21) — order book or partial-leg, no inference left:**

| row | att1 entry (real fill) | att1 stop → pnl | att2 entry (real fill) | att2 stop → pnl | proof |
|-----|------|------|------|------|-------|
| MRAM 120 | 36.52 | 33.89 → −1101.93 | **36.50** (order 61) | 33.88 → −1097.78 | order book |
| AMD 81 | 415.17 | 405.57 → −460.95 | **413.31** | 405.59 → −370.53 (o/n, 5/07) | order book |
| OMCL 34 | 45.998 | 43.50 → −1078.95 | **46.00** | 45.01 → −427.68 | order book |
| SMCI 82 | 31.23(att1) | −720.77 | real held (partial +82.14 @32.97) | 32.57 → −0.71 | partial_profit leg |
| TEAM 57 | 82.56(att1) | −595.81 | real held (partial +328.32 @89.51) | 85.18 → −1.53 | partial_profit leg |

Each att2 has a **distinct real buy fill at a distinct price** (MRAM/AMD/OMCL traced through `mi_live_orders`);
SMCI/TEAM's `partial_profit` leg is impossible without a real held 2nd position. Every leg reconciles to the
penny as `(stop − entry) × shares`. **No over-counting in any row. No correction warranted.**

**Nothing to correct. No code change. No trade-state mutation.** #483 as framed (a live idempotency
double-count bug) does not exist; the observation is two real pre-R3 re-entry round-trips, and R3 already
disabled the feature. Close the task.
