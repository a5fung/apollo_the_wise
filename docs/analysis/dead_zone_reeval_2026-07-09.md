# Dead-zone re-eval (ORB-window extension precision) — 2026-07-09

**#290 · `dead_zone_reevaluation` gated review fired ready** (predicate = distinct missed-HIGH
≥10% winners post-2026-03-20; grew 29 → 155 → this run's 330 unique HIGH_missed). Re-ran the
2026-04-30 analysis on the fatter, trustworthy-timestamp cohort to confirm the conclusion holds.

**Pipeline (prod, read-only):** `scripts.probes.backfill_dead_zone_v2 --days 120` (covers the
2026-03-20 cutoff) → `/tmp/dead_zone_v2.csv` (563 rows post-cutoff) → `analyze_late_detection_v3`.

## The core result — ORB-window extension precision (unique, post-2026-03-20)

late_detection cohort: n=252, positives=58 (a "positive" = a ≥10% forward-5d winner that was missed).

| Extend ORB cutoff to | captures | positives | **precision** | recall |
|---|---|---|---|---|
| 9:50 | 1 | 0 | 0.0% | 0.0% |
| 9:55 | 26 | 5 | **19.2%** | 8.6% |
| 10:00 | 38 | 7 | **18.4%** | 12.1% |
| 10:30 | 38 | 7 | **18.4%** | 12.1% |
| 11:00 | 168 | 40 | 23.8% | 69.0% |

**The real comparator is NOT an asserted 20% — it's this run's own control.** `HIGH_entered`
(the HIGHs we actually took), deduped by (ticker,date): **5/25 = 20.0%** hit ≥10% forward
(raw 7/36 = 19.4%). So the "~20% baseline" the 4/30 write-up asserted is genuinely ~this — and
the extension must be read *against it*, both ways:
- **Near-window (9:55–10:30) = 18–19% ≈ the ~20% control** → statistically indistinguishable from
  the trades we already take, at this N. Modestly extending the cutoff neither clearly beats nor
  clearly trails what we do now.
- **Extend to 11:00 = 23.8% > the control, recall 69%** (40/58 missed winners recoverable) → the
  review's literal trigger ("if precision crosses 20%, reopen") **did fire**. But this captures
  168 tuples (4.4× the 10:00 net) — it abandons the ORB *timing* discipline for an all-day
  late-entry policy, a fundamentally larger entry-discipline change (THE LINE, operator's call).

Precision did rise 12.5% (4/30) → 18–24% here with the fatter cohort. This is **not a clean close**:
late-window precision ≈ entered-trade precision, and the widest window exceeds it at 69% recall.

## Secondary observations (not the review question)
- **Mechanism breakdown:** late_detection 23.0% pos (n=252); **cancelled_unfilled 36.7% pos
  (n=30, 11 winners)** — NOT sparse (criterion (b) expected it sparse post-SIP-flip). These are
  HIGHs cancelled before fill (the 10:00 ET unfilled-cancel job) — 11 were ≥10% winners. Distinct
  from the ORB-extension question; a possible separate thread (why 30 HIGHs go cancelled_unfilled).
- **By-minute:** the 10:30–10:59 bucket is the richest (n=130, 25.4% pos, med_fwd 22.6%) — but
  entering there is the all-day policy, not an ORB extension.

## Decision — operator's (THE LINE); presented straight, not pre-loaded
The literal review trigger fired (23.8% > 20% at the 11:00 window), and late-window precision ≈
entered-trade precision — so this is a genuine fork, not a close-by-default:
- **CLOSE** — accept the residual: the *near-window* extension (~19%) only matches what we already
  take, and the only window that beats it (11:00, 69% recall) means abandoning ORB timing — a
  bigger discipline change than the marginal precision edge justifies. Accept ~1 winner/quarter lost.
- **REOPEN the entry-path question** — 23.8% precision at 69% recall exceeds our own entered-trade
  precision; the missed-winner $ (DGXX +64%, HTCO +60%, TE +49%, APPS +39% — all late_detection)
  is real. Scope a proper late-entry backtest (precision × realized-R × the ORB-timing cost), not
  just precision, before any change. Any live entry-window change = CHANGE_PROCESS + sign-off.

Separately: **cancelled_unfilled = 36.7% pos (n=30, 11 winners)** was expected sparse post-SIP and
is not — a distinct thread worth filing if wanted (why 30 HIGHs go cancelled-before-fill).

*Analysis is read-only; no trade change made.*

---

# PART 2 — Late-entry realized-R backtest (2026-07-09, operator reopened the entry-path question)

Precision was never the R question. A late entry has **no fresh ORB**, so it is forced onto a
stale-ORB stop (structure-low / ATR) — exactly the models #276 W2 study-2 showed collapse realized-R.
Measured realized-R for the late cohort. Script: `scripts/_290_late_entry_backtest.py` (prod run).

**Method (explicit UPPER BOUND — advisor 7/9):** cohort = 290 late-detection HIGH_missed (deduped,
9:45+, post-3/20; 278 had bars + a forward path). Entry fill = the **next minute-bar OPEN after the
detection minute + 10bps slippage** (immediate, no missed-breakout penalty — the most favorable
honest fill). Day-0 same-day stop vs the **post-entry** intraday low (no pre-entry lookahead).
Survivors replay forward daily bars (`mi_daily_closes` real lows/closes) through the SAME MAGNA53
exit ladder (`apply_daily_exit_step`). shares=100 (realized-R is size-independent). Stops honestly
available at a late entry (no lookahead): `low_so_far` = intraday range low UP TO entry (the tight
structure stop, the late analog of orb_low); `atr_1.0`, `atr_1.5`. **`day_low` (full-day low) was
dropped — it is LOOKAHEAD at a mid-morning entry.**

### Result — realized-R by stop × ORB-extension cutoff (upper bound; mean-R / win% ; N)
```
stop \ extend-to     9:55         10:00        10:30        11:00        [#276 entered bench]
low_so_far        +0.13R/38%   +0.02R/34%   +0.02R/34%   -0.35R/24%    (orb_low analog: +1.40R)
atr_1.0           +0.25R/46%   +0.31R/42%   +0.31R/42%   -0.21R/26%    (atr_1.0: +0.48R)
atr_1.5           +0.15R/50%   +0.15R/45%   +0.15R/45%   -0.16R/32%    (atr_1.5: +0.27R)
N per cutoff:        26           38           38          ~195
medians:          mostly -1.00R (most trades stop out; positive means carried by fat-tail winners)
```

### Read
1. **HEADLINE (well-powered, stands on its OWN harness — no cross-comparison needed): extend to
   11:00 — N≈196, the window that WON on precision at 23.8% — is R-NEGATIVE across EVERY stop
   (−0.16 to −0.35R).** Precision parity did NOT translate to realized-R.
2. The near-window best cell (`atr_1.0`, 10:00–10:30) is **+0.31R mean / 42% win** — marginally
   POSITIVE (on trades we take at zero today), **NOT** "loses money." But with a −1R median,
   fat-tail-carried, at N=38, the CI almost certainly straddles zero: **no ROBUST edge**, not a
   demonstrated win. Don't overstate this either direction.
3. The tight structure stop (`low_so_far`) is +0.02–0.13R near-window — a late entry's structure low
   is already far below the run-up price → wide risk → low R (the "wide stop hurts R" mechanism, by
   construction of a late entry).
4. Medians mostly **−1.00R** (most trades stop out); the positive means are fat-tail-carried; win
   24–50%. Many attempts, few pay — a lottery-shaped distribution, not a smooth edge.
5. **UPPER BOUND** (optimistic next-bar-open fill). The real late-entry mechanic (a stop-buy at
   *what* level? there's no ORB) would be worse, not better.

### #276 is DIRECTIONAL CONTEXT, not a pass/fail benchmark
The +1.40R orb_low / +0.48R atr numbers are a DIFFERENT cohort (44 entered vs 278 missed), a
DIFFERENT harness (selection_replay engine vs this fresh forward-replay), a different entry mechanic
— absolute-R across two harnesses is not apples-to-apples. Use it only for direction ("wide stops
hurt R"; "fresh-ORB entries earn more"), never as the bar this cohort must clear.

### Conclusion → recommend DON'T extend the ORB window — on the right grounds
The decisive, well-powered fact is internal: **the 11:00 window (N≈196) that beat on precision is
R-negative.** The near-window cells are marginally positive (+0.15 to +0.31R) but noisy (−1R
medians, small N, CI straddles zero) — no ROBUST edge. So extending is not a demonstrated win.

**The real decision variable is SLOT CONTENTION — the operator's call.** A +0.31R late entry is
only DILUTIVE if it displaces a fresher, higher-R ORB entry from one of the 5 concurrent slots over
its multi-day hold. Slots usually free → marginal +R is additive (mildly worth it). Slots bind →
it's a bad trade (gave up a better one). That — not "R is negative" — is why "below fresh-ORB
earnings" matters.

**Volume (correcting the 4/30 framing):** this is NOT "~1 winner/quarter." 290 late-detections over
~110 days at 24–50% win = DOZENS of missed winners — but at −1R medians / no robust R edge they're a
fat-tail lottery (many attempts, few pay), not a clean harvest.

**Caveats:** near-window N is small (26–38; the decisive 11:00 cell is robust at ≈196); the entered
control is a DIFFERENT population (selection bias); upper-bound fill. If the operator wants to chase
the marginal near-window +R, the next step is a slot-contention model + the real stop-buy fill
mechanic (a CHANGE_PROCESS-grade study), not this first-cut. THE LINE: any live entry-window change
= CHANGE_PROCESS + sign-off. *Read-only; no trade change made.*
