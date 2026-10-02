# M&A filter — operator labels on the September blocks (2026-10-01)

Ground truth for #692. The agent did NOT classify (HARD gate, CHANGE_PROCESS rules #3/#4); every
label below is the operator's own word. Earlier rounds: 2026-07-04 (`operator_labels_sitting_2026-07-04.md`,
3 of 4 wrong → #416 guards A/B/C) and 2026-08-08 (`docs/setups/magna53_ep.md`, 7 of 8 wrong → #516 guard D).

## Population

n = 11 — every `mna_filter_fired` suppression in the 35 days to 2026-10-01, from
`python -m scripts.mna_filter_accuracy_review 35` on prod (raw output and per-block source text:
`scripts/probes/_692/`). Nothing passed as acquirer-side in the window (n = 0).

## His words

- FWDI, first: *"there is no buyout so it shouldn't have been flagged for m&a"*
- All eleven: *"only ACVA is m&a, none of the others are so our m&a filter is wrong"*

## Labels

| Ticker | Blocked | Path | What our source said | Rise after (vs open) | His label |
|---|---|---|---|---|---|
| ACVA | 2026-09-11 | classifier | Copart to acquire ACV Auctions, all-cash, ~$1.9B | +0.4% | **real buyout — correctly blocked** |
| FWDI | 2026-09-18 | classifier | FWDI's own sweetened proposal to acquire SkyAI | +31.1% | wrongly blocked |
| IOVA | 2026-09-29 | headline | raised 2026 revenue outlook | +19.6% | wrongly blocked |
| VKTX | 2026-09-22 | headline | speculation Novo could pursue acquisitions | +16.5% | wrongly blocked |
| SWKS | 2026-09-15 | classifier | proposed $22B merger with Qorvo | +14.3% | wrongly blocked |
| RGTI | 2026-09-08 | headline | $100M Commerce Dept funding agreement | +4.1% | wrongly blocked |
| GPRK | 2026-09-03 | classifier | entry into Venezuela's Bare Block | +3.4% | wrongly blocked |
| CSR | 2026-09-09 | classifier | $8.1B all-stock merger with Independence Realty | +2.5% | wrongly blocked |
| JBS | 2026-09-18 | classifier | JBS proposes to buy out Pilgrim's minority | +1.8% | wrongly blocked |
| WAY | 2026-09-15 | classifier | exploring strategic alternatives incl. a sale | +0.9% | wrongly blocked |
| CHYM | 2026-09-09 | classifier | Chime to acquire Stride Bank, $590M | +0.6% | wrongly blocked |

10 of 11 wrong: 7 of 8 classifier blocks, 3 of 3 headline blocks.

## Use

The #692 replay must release all ten and keep ACVA blocked, plus the earlier real targets
(SUNE 2026-07-04, CLRO 2026-08-08). Each wrongly-blocked name becomes a named regression case in
`scripts/_284_mna_acquirer_backtest.py`.

## What this does not answer

- Whether the ten wrongly-blocked names would have been TRADED or made money: the "rise after" column is the price from the open after the block, not an entry under our rules, and some would have failed other gates (position cap, breaker, grade).
- Whether the filter misses real buyouts: this lists only what it BLOCKED. A real target it let through is not here (nothing passed as acquirer-side in the window, n = 0, but the keyword and classifier paths leave no row when they stay silent).
- How the fix should decide: the labels say which names are wrong, not which rule replaces the guards — that is #692's replay and his sign-off.
