# #456 F6 — min-ORB-range floor backtest (2026-07-19, no-money sizing step)

**Premortem #450 F6:** `shares = floor(risk_dollars / (orb_high − orb_low))` has no minimum-range
floor → a thin/corrupt first bar → divide-by-tiny → shares clamp to the 20% cap → a **20%-of-equity
position with a stop a few cents away = a guaranteed-stop-out coin-flip** where the real loss is
slippage at multiples of nominal risk. This is the no-money first step: **size the thin-bar class
against real data before proposing any threshold.**

## Data
71 distinct `orb_bar_fetched` audit rows (2026-04-16 → 2026-07-15). Metric = ORB range as % of the
opening price (a stand-in for risk-per-share; ATR isn't in the audit row).

## Distribution
`min 0.55% · p10 1.59% · p25 2.44% · median 3.78% · p75 5.20% · max 10.03%`

**The typical ORB is a healthy ~3.8%-of-price range.** The thin-bar problem is a TAIL, not systemic.

## Would-be-blocked by a min-range floor
| floor (% of price) | blocked | who |
|---|---|---|
| 0.3–0.5% | 0/71 (0%) | — |
| **0.75%** | **2/71 (3%)** | **BZH 0.55%, MANE 0.61%** |
| 1.0% | 2/71 (3%) | (same 2) |
| 1.5% | 7/71 (10%) | + MU 1.11%, DELL 1.17%, JBL 1.20%, TWLO 1.23%, … |
| 2.0% | 11/71 (15%) | (starts hitting legitimately-tight setups) |

## The genuine F6 danger (thinnest 2) — and it's not hypothetical
- **BZH** — range $0.14 on a $25.30 open = **0.55%** stop
- **MANE** — range $0.73 on a $118.75 open = **0.61%** stop → **⚠ MANE was a REAL LIVE LOSER (stopped out −$2, 7/15).** A thin-bar entry that stopped out is exactly the F6 class materializing.

## Recommendation for the ⚖ threshold decision
**A min-range floor at ~0.75% of the entry price** (equivalently: reject if risk-per-share <
~0.75% of price) catches the 2 genuine coin-flip cases with **near-zero collateral** — there is
nothing legitimate between 0.61% and 0.75%. Tighter (0.3–0.5%) catches nothing; wider (1.5–2%)
starts blocking legitimately-tight-but-tradeable bars (MU/DELL/JBL/TWLO at ~1.1–1.2%).

**Caveat — small N.** The thin-bar class is only 2–11 entries → below the N≥10 clean-backtest bar.
So this is a **small-sample operator call**: do 2 clear coin-flip cases (one a real loser) justify
a floor? **My lean: yes, at ~0.75%.** The mechanism is unambiguous regardless of sample — a 0.55%
stop on a 20%-of-equity position is a guaranteed stop-out; it's cheap insurance against the worst
sizing pathology at ~zero collateral. It's a detection-criterion change → SSoT (`magna53_ep.md`)
change-log + operator sign-off (THE LINE) before any live flip.

Refs: premortem #450 F6 (`docs/analysis/450_premortem_2026-07-18.md`), #456, #482 (ORB-bar
reliability, the sibling geometry lab).
