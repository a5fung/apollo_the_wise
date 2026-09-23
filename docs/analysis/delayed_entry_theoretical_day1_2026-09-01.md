# The day-1 split redone under the operator's population ruling: theoretical day-1 trades, simulated, then delayed entry per group

**Date:** 2026-09-01 · **Read-only replay** — no prod writes, no thresholds, no strategy changed.
**Acting-rules source:** `live_rules_2026-09-01.txt` (0 drift findings).
**Supersedes the Q2 population cut** in `delayed_entry_stop_and_population_2026-09-01.md`
(groups A/B/C/D) — that split was built on "did WE enter", which the operator ruled invalid, and
on a 15-minute ORB level the live system does not use. Probe + captured data:
`scripts/probes/_562_theoretical_day1_probe.py` + `_562td_*.tsv` (full tables:
`_562td_report.txt`). The backfill harness and its captures are reused; one new read-only
capture was taken (`_562td_capture.sql`, run once).

---

## The decision this serves

The operator, on the A/B/C/D split, verbatim: *"the names we didn't enter can be for reasons
beyond the stock itself, like we hit our cap, or the window beyond 9:45 like you said, etc. we
should consider them as EPs we theoretically would've traded in day 1 as well, so we should
just look at all EPs that meet our criteria."*

So the question is re-asked on the right population: **among caught EPs that MET OUR ENTRY
CRITERIA — whether or not an order ever existed — does going back in (the delayed-entry rungs)
pay on the names whose day-1 trade would have stopped out, versus the names whose day-1 trade
never triggered?** The infrastructure noise (cap, window, breaker, key outage) is moved out of
the split and into a route report.

**What would change the answer:** a positive-expectancy per-rung table on the simulated
stopped-out group would make it the delayed-entry target population; a stopped-out group
materially worse than the never-triggered group would confirm the 08-29/09-01 "knocked-out
names are dead" reading on an unbiased population. **Written before running:** the prior
finding could fail here, because the 41 real stopped-outs were selection-biased (only names
with a free slot and a timely detection) and the old "never broke" group was measured against
the wrong ORB level.

## Method / population

**Population — "met our entry criteria", derived from CODE, not from `mi_live_trades`:**

| criterion | source (file:line) | effect on the 267 caught EPs |
|---|---|---|
| `score_tier = 'HIGH'` — the only tier the ORB job submits | `broker/live_tracker.py:375` | 190 in; 66 MODERATE + 11 suppressed (`score_tier` NULL) out. Zero magna53 order rows exist for any non-HIGH pair (checked), so the stored tier IS the acting router, earnings-day override included |
| real-time gap floor at submission | `check_rt_gap_floor`, `broker/entry_pipeline.py:604`; floor 10% → 9% on 2026-08-19 | 9 recorded `setup:gap_below_floor` skips out; 9 more out by the uniform proxy (no minute close in 09:31–09:44 implying gap ≥ the era floor) on pairs the live system never re-checked; fail-OPEN where data is absent, matching the live check's direction |
| ORB entry validation | `validate_orb_entry`, `backtester/filters.py:207` (zero range; ORB range > 1.5×ATR14, `compute_atr_14` filters.py:96 mirrored as the 9:31 path sees it — bars strictly before the EP day) | 8 recorded `stop_too_wide` + 1 `zero_range` out; 4 + 2 more out by the uniform computation on never-checked pairs. Pairs with a real order passed the live gates and are never re-litigated with local ATR |
| fade guard | MAGNA53 HIGH passes `ratio=None` — skipped | no effect |

**Population = 157 of 267.** Routes in (what "theoretical" is doing — 111 of 157 (71%) had no
day-1 fill for reasons that say nothing about the stock):

- entered 46 · window-late detection 38 · order placed but never filled 34 · no attempt at all 9
  (six are the 05-20 cluster detected 18:40 ET, plus FTK/LIND/LZB) · account-key outage 8 (May)
  · circuit breaker 7 · position cap 5 · account-size (can't buy 1 share / price cap) 5 ·
  no-bar infra 2 · broker reject 2 · chase-cap 1.

**The day-1 simulation — the real mechanics, read from code (one correction to this card's own
brief):** the live ORB is **the first 1-minute bar of the day** (`get_first_bar`,
`broker/alpaca_client.py:812`, via `fetch_orb_bar_with_retry`, `entry_pipeline.py:82`) — **not
the 9:30–9:45 fifteen-minute range** the previous classification used. Validated: stored
`orb_high` equals the 09:30 `mi_intraday_bars` high on 13/13 filled trades. Entry = stop-buy AT
the ORB high (touch fills — BW 08-11 proves it: daily high == orb_high == the real fill).
Protective stop era-correct, boundary read from the trades themselves (`hard_stop` ≡ orb_low
through 08-14 fills, ≡ 2·orb_low − orb_high from 08-18): EP day ≤ 08-14 → ORB low; ≥ 08-17 →
2·orb_low − orb_high (`order_manager.py:498`, operator-signed 08-16). Classification is **by
what the stock did** (the ruling): the 10:00 ET unfilled-cancel is a we-mechanic and is only
counted (4 of 75 minute-graded fills broke at/after 10:00). Levels prefer the live system's own
trade-row ORB where an order recorded one, else the stored 09:30 bar.

**Abstain, never fabricate:** minute-resolution decisions without minutes fall back to the
validated daily authority (daily high ≡ RTH minute max and daily low ≡ minute min: 0 low / 1
high mismatches >0.2% across 142 full-coverage EP days, checked before the probe was written):
strictly-below-the-level daily high → never triggered; triggered + daily low above the stop →
survived; anything needing intra-day ordering → **abstain, counted**. Where a **real day-1 fill
exists, the broker's own record classifies the pair** (evidence grade `real`) — reality is not
fabrication; the bar-sim is still computed and kept beside it for the fidelity read. 25 of 157
abstain (13 one-bar days ambiguous, 9 touch-at-level-only ambiguous, 3 with no bars at all —
ALAB/DYN/GH 05-20, and ALAB is the backfill's biggest winner: stated, not guessed).

**Fidelity gate (the card is unsound if this fails — it does not):** 45 real day-1 fills on the
acting lane. An independent minute-path sim exists for 34: **agreement 33/34 (97%)**. The sole
mismatch is MANE 07-15 — the pessimistic intra-bar convention (fill-bar low 118.00 vs stop
118.02; the dip preceded the break inside the same 5-minute bar; the real trade survived to day
2). The other 11 fills sit on one-bar days where no independent sim can run; the broker record
classifies them directly. Secondary check: 31/37 cancelled-unfilled orders show no pre-10:00
sim break; all 6 exceptions have trade-row orb_high exactly equal to the stored 09:30-bar high
— order-lifecycle effects (submission latency, ask-aware cancel), not level drift.

**Result of classification (157):** **stopped day 1 = 68 · survived day 1 = 52 · never
triggered = 12 · abstain = 25.** Stop era: ORB-low 66/44/12/22, 2R 2/8/0/0 — every readable
(mature) month is ORB-low-stop era. ⚠ Under the CORRECT first-minute level, only 12 of 157
never trigger — the prior study's "B: the ORB high never broke, n=94 of 267" was mostly the
wrong (higher, 15-minute) level plus names that never met the entry criteria at all.

**Delayed-entry instrument unchanged:** the lane's own recorded fires and settlements
(`_562bf_triggers.tsv` — the backfill's walk, the lane's `compute_settlement`, M-none and
M-trail, HARVESTED R never MFE), regrouped by the simulated day-1 class. Mature fires only
(20 post-fire sessions existed by 08-31); immature settled rows are stops by construction and
are never pooled. Era split by month, mandatory.

## The numbers — delayed entry per simulated day-1 group

Mature settled fires, first attempts, all four rungs pooled ("family") and per rung in
`_562td_report.txt`:

| simulated group | campaigns | mature fires | M-none mean / med | M-trail mean / med | ≥4R fires (none/trail) |
|---|---|---|---|---|---|
| **(ii) triggered, stopped out day 1** | **68** | **91** | **−0.45 / −1.00** | −0.23 / −1.00 | **4 / 4** |
| (i) never triggered | 12 | 15 | −0.79 / −1.00 | −0.34 / −1.00 | 0 / 0 |
| (iii) triggered, survived day 1 | 52 | 67 | −0.36 / −1.00 | −0.24 / −1.00 | 3 / 2 |
| abstain (bars can't decide) | 25 | 53 | +0.02 / −1.00 (ALAB-carried: May supplies +36.1R, ALAB alone +33.9R) | −0.25 / −1.00 | 3 / 2 |
| did NOT meet criteria (reference) | 110 | 148 | −0.48 / −1.00 | −0.07 / −1.00 | 8 / 8 |

Monthly (M-none, the era split — August is immature by construction, readable ~late September):

- **stopped day 1:** May −0.44 (n=52) · Jun −0.53 (n=18) · Jul −0.40 (n=21) · Aug 54 immature
- **never triggered:** May −1.00 (n=5) · Jun — (0 campaigns) · Jul −0.68 (n=10) · Aug 14 immature
- **survived day 1:** May +0.06 (n=36) · Jun −0.55 (n=10) · Jul −1.00 (n=21) · Aug 63 immature

**Plain words:**

- **Going back in pays nowhere wholesale.** Every group's median fire is a full stop-out, in
  every readable month, under both exit styles — the backfill's mechanism finding survives the
  population correction intact.
- **But the prior ranking INVERTS: the knocked-out names are no longer the worst place to go
  back in — and their tail is real and not May-carried.** The simulated stopped-out group holds
  the biggest in-population tail count: ANF +7.3R (May) · FET +7.1R (Jul) · VPG +6.2R (May) ·
  NAVN +4.9R (Jun) on M-none, and BLZE +6.0 / FTNT +5.5 / KLAR +4.1 on M-trail — 4 of its 7
  either-arm ≥4R fires are outside May. Ex-May it runs −0.46/fire vs never-triggered's −0.68.
  The 08-29/09-01 conclusion "being stopped out on day 1 is evidence the name has no tail"
  **does not survive the ruling**: it was an artifact of the did-we-enter selection (names we
  actually traded needed a free slot and a timely detection) and of the wrong ORB level.
- **The never-triggered group is now small and tail-free** (12 campaigns, 15 mature fires, 0
  ≥4R) — but n is thin; "too few to judge" is the honest read, not "dead".
- **Most of the recorded delayed-entry tail lives OUTSIDE the day-1-tradeable population.** TE
  +10.7/+14.2, GO +6.6, BHVN +6.7, MMYT +5.9/+7.0, QBTS trail +9.6, CLF trail +6.4 all sit on
  names that did not meet the entry criteria (mostly MODERATE tier). The lane's own population
  (all caught EPs, the 09-01 re-seed ruling) is deliberately wider than the day-1-tradeable
  subset; on that subset the recorded tail is thinner than the backfill's headline 18.
- **Descriptive only, and thin:** inside the stopped group the high-break rung is the lone
  mean-positive cell (+0.40, n=9, VPG-carried — one fire decides it; no claim).

## What this says (and the fork)

Removing the "we couldn't act" noise changes the day-1 split's answer: the stopped-out group is
mid-pack with the only spread-across-months in-population tail, and the never-triggered group —
correctly measured against the first-minute ORB — is nearly empty and shows nothing. No group
is positive, so **the binding constraint is unchanged: selection (P13), not the group cut and
not rung definitions.**

Fork for the operator (evidence only, his call — nothing flipped):

- **(1)** The 09-01 recommendation *"stop pointing delayed-entry design at the knocked-out
  names"* rested on the invalidated split — **withdraw it.** On the corrected population,
  knocked-out-day-1 is as good a target as any in-population group and carries the tail count.
- **(2)** If a selection layer gets built (the backfill's fork (b)), day-1 group membership is
  computable ex ante but its measured value is second-order versus the selection gap — a
  ranking signal at most, not a filter.

## What this does not answer

- **August, at all** — 131 of its fires immature; settled Aug rows are stops by construction.
- **Day-2+ initial-stop knock-outs.** The card's classification is day-1 only; a name that
  triggered day 1 and hit the initial stop on day 3 sits in "survived day 1". The real trades
  say this matters (several real stops landed day 2+).
- **Overlap for group (iii):** its delayed-entry fires can occur while the day-1 position would
  still be open — an add-on question, not a re-entry one; not modeled.
- **The 25 abstains**, which include ALAB (+33.9R settled across its fires) — wherever it truly
  belongs, that group's sum moves by ~+34R. Stated, not guessed.
- **Re-entry shapes and management layers** beyond the lane's two arms — out of scope, as in
  the backfill.
- **Whether the earnings-day MODERATE→HIGH override ever promoted silently** — no order row for
  any non-HIGH alert exists in this window, so the stored tier is taken as the router; a
  promotion that left no alert-row update AND no order would be invisible here.
- **Feed drift beyond what the fidelity checks caught** — sim levels come from
  `mi_intraday_bars`/trade rows; live fills act on the Alpaca feed. 97% agreement bounds the
  effect on names we can check; unfilled theoretical names carry the residual risk.

## ⚖ THE LINE

Entry/exit discipline, stops, selection rules, sizing and thresholds are the operator's sole
authority. This card measures and recommends; it changes no rung, no threshold, no live code.
Prod access was read-only SELECTs captured once (`_562td_capture.sql` → `_562td_*.tsv`); the
live lane and its tables were not touched.

---
*Population: 157 of the 267 live-source caught EPs (May 74 · Jun 53 · Jul 41 · Aug 99, window
2026-05-01..08-31) meeting the code-derived entry criteria. Instrument: day-1 sim per
`_562_theoretical_day1_probe.py` (phases pop/sim/agree/table); delayed-entry outcomes are the
backfill's recorded fires and the lane's own settlements, regrouped. Hand-verified: ANF 05-27
(fill minute 572, stop touch 574), AMRC 08-04 and ARM 07-30 (never triggered) reproduced from
raw bars; 45-fill census ties to `mi_live_trades`. Related: PLAN #562/#327;
`docs/setups/delayed_ep_reentry.md § THE CONTEXT LEDGER` needs its row for this doc — ledger
edit deliberately left to the main session (this card is scoped to `scripts/probes/` +
`docs/analysis/`).*
