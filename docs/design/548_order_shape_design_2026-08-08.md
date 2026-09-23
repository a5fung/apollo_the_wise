# #548 — order-shape design for the 2R limit + real-time breakeven

**DESIGN ONLY. Nothing built, nothing proposed for a live flip.** Exit discipline is THE LINE:
CHANGE_PROCESS + operator sign-off.

## The operator's constraint, which RANKS the criteria

> *"yes to both, but this can be tricky to get right, we've been bitten by stop orders failing at
> broker when it gets complex so i want to make sure we get this right. But for our math to work
> and accurate we need to sell as close to 2R as possible, and stop to breakeven needs to be
> real-time."*

Broker-simplicity FIRST, arithmetic second. A design that nails the maths by stacking legs onto
the bracket is a regression even if the numbers improve.

---

## ⚠ CORRECTION FIRST: my Phase A smoke test measured a LOOKALIKE

On 2026-08-08 I ran a probe on a FLAT paper account: a naked sell-stop for shares we did not own
was **ACCEPTED**, and I concluded Alpaca does not validate sell quantity at submission.

**That conclusion does not transfer to the real system, because the real system is never flat in
that sense.** Every MAGNA53 entry places an **OTO bracket**, and its stop leg **reserves all the
shares**. With nothing held and nothing reserved there is nothing to collide with — so the probe
answered an easier question than the one that matters.

This is the "prove it exercises the LIVE mechanism, not a lookalike" rule, and I broke it.

## THE REAL ANSWER ALREADY EXISTS — measured 2026-08-04, and I should have read it first

`scripts/probes/_508_oto_leg_probe.py`, paper, recorded verbatim in `order_manager.py`:

| test | result |
|---|---|
| T1 `replace(leg, qty)` | **REJECTED 42210000** — qty cannot change on an advanced-order leg |
| T1b leg after failed replace | still live (the rejection is atomic) |
| **T2 `replace(leg, stop_price only)`** | **OK — price moves on legs DO work** |
| T2b the replacement | still `order_class=oto` (no detach) |
| T3 `replace(replacement, qty)` | REJECTED 42210000 — once a leg, always a leg |
| **T4 2nd stop while the leg holds** | **REJECTED 40310000** insufficient qty |
| **T5 market sell while the leg holds** | **REJECTED 40310000 — can't sell first** |
| T6 cancel → release | reservation clears ~78ms AFTER the cancel confirms |

**Conclusion already on record:** for a bracket-leg stop, cancel-then-new is the only mechanism
Alpaca permits.

---

## What that means for each of the two remaining defects

### Defect 2 — real-time breakeven: **NOT BLOCKED. The mechanism is already proven.**

Moving the stop to breakeven is a **price-only change on the leg**, and **T2 shows price-only
replace works on a bracket leg.** No cancel, no new order, no extra leg, no reservation race — the
single operation the operator's constraint is most comfortable with.

- It is not wired. `finalize_partial_exit` sets `breakeven_active = TRUE` in the DB and stops
  there; only `exit_logic`'s daily pass consumes the flag.
- The fix is to issue the price-only replace at the moment the partial commits.
- **Broker-complexity cost: zero new orders, zero new legs.** One replace on an order that already
  exists.

▶ **This is the cheap half and it is currently sitting behind the expensive half for no reason.**

### Defect 1 — resting limit at 2R: **the obvious design is DEAD on T5.**

A resting limit sell placed while the full-size stop leg holds the shares is the T5 shape:
**REJECTED 40310000, "can't sell first."** So "rest a limit at the 2R level and let the broker fill
it" cannot be built as stated — not because it is risky, but because Alpaca will not accept it.

Surviving candidates, scored on broker-failure surface first:

| # | shape | orders live | new failure modes | verdict |
|---|---|---|---|---|
| A | rest limit alongside full stop | 2 | — | **DEAD (T5)** |
| B | reduce stop to 2/3 (cancel-then-new), then rest the limit for 1/3 | 2, briefly 1 | the T6 reservation race, already hardened | viable |
| C | keep the poll, but send a marketable LIMIT instead of a market order | 1 | none — same slot, better price control | viable, smallest |
| D | pre-split at entry: stop for 2/3 + resting limit for 1/3 from the start | 2 | 1/3 unprotected by any stop until the limit fills | **rejected — unprotected shares** |

**C deserves attention precisely because it is boring.** Today's loss is not that the fill happens
late — the trigger fired at 09:35:02, two seconds after the high. The loss is that it fired a
MARKET order into a price that had already moved. A marketable limit with a floor at (or just
under) the 2R level captures most of the gap with **no change to the order topology at all** — the
constraint the operator ranked first.

**B buys the rest of the gap** but pays the cancel-then-new reservation race for it, on the hot
path, during market hours.

---

## What Monday's probe should ACTUALLY test — re-scoped

The original Phase B ("what happens to the oversized stop when the resting limit fills") is now
**moot for candidate A**, which is dead. The open questions that remain are narrower and real:

1. **Candidate C:** does a marketable limit sell get accepted while the stop leg holds? T5 rejected
   a MARKET sell — is a LIMIT sell treated identically? *(Expected: yes, rejected — the reservation
   is order-type-agnostic. If so, C also needs the stop reduced first, and C collapses into B.)*
2. **Candidate B:** after the stop is reduced to 2/3 via cancel-then-new, is a limit sell for the
   freed 1/3 accepted immediately, or does it hit the same ~78ms reservation lag T6 measured?
3. **Defect 2:** confirm a price-only replace to the entry price is accepted on a live leg mid-session
   (T2 proved the mechanism; this confirms it at the exact moment we would use it).

⚠ **(1) is the one that decides everything** and it is a 5-minute test. If a limit is rejected the
same way a market sell is, then every design must reduce the stop first and the question becomes
*only* about sequencing — which is already-hardened code.

## Sequencing recommendation

1. **Ship defect 2 first, on its own.** Proven mechanism (T2), one price-only replace, no new
   orders. It is the half that would have saved FIGS's remaining 41 shares.
2. **Then answer (1) above**, and only then choose between C and B for defect 1.

⚖ Both remain THE LINE. This document is the decision framework, not the decision.

## Honest note on how this went

The answer to most of #548's "unknown" was already measured on 2026-08-04 and written into
`order_manager.py`. I proposed a smoke test, ran half of it, and drew a conclusion from a flat
account before reading the file that already had the answer. The $0 path was to read the code.
