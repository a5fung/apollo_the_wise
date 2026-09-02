# The full entry × stop expectancy grid — all four delayed-entry buy signals, every stop basis, one population

**Date:** 2026-09-01 · **Read-only replay** — no prod access at all (consumes the already-captured
`_562bf_*` / `_562sp_*` files), no thresholds, no live behaviour changed.
**Acting-rules source:** `live_rules_2026-09-01.txt` (captured 06:27 PDT, 0 drift findings).
**Extends** `delayed_entry_backfill_2026-09-01.md` (the 267-caught-EP replay — same fires, same
instrument) and generalizes the Q1 stop sweep of `delayed_entry_stop_and_population_2026-09-01.md`
(which ran for ONE of the four signals) to all four. Probe + rows:
`scripts/probes/_562_stop_grid_probe.py` + `_562grid_rows.tsv` (7,826 = 602 fires × 13 bases);
full tables `_562grid_report.txt`.

---

## 1. The decision this serves

The operator's reframe, verbatim (2026-09-01): *"we are not predicting anything, we're not
building a prediction engine here, we are building a trading system that can be risk managed, we
find entries and exits where we can manage risk properly and where we have positive expected
returns."* The #545 selection test proved no fire-time fact picks the winners; the one-signal
stop sweep proved the stop moves `ep_high_break` from −0.41R to +1.66R per fire. **So the open
question is the grid: for each of the four buy signals, is there a stop basis under which taking
every fire has positive expected return — with a risk that can actually be managed?**

**What would change the answer — written before the grid ran:** a (signal × stop) cell positive
POOLED and EX-MAY, at n ≥ 30, that does not rest on one fire, would be a candidate tactic; a grid
where only May cells are positive would say the stop lever is a regime artifact and the 09-01
high-break finding must not be built on.

## 2. Method / population

- **Population:** the backfill's 602 recorded first-attempt fires over the 267 live-source
  `mi_ep_alerts` campaigns (May 74 · Jun 53 · Jul 41 · Aug 99, window 2026-05-01..08-31). The
  walk was re-run and **reproduces the recorded population exactly — 602/602 fires, 0
  entry/stop mismatches — before anything was varied.** Entries never change; only the stop does.
- **Instrument:** the lane's own pure functions (`delayed_entry_shadow.py`), settlement through
  `compute_settlement`, both arms — **M-none** (hard stop, else 20th-session close) and
  **M-trail** (same stop + close below MAX(SMA10,20) exits). **R is HARVESTED R in each
  variant's OWN units** (risk = entry − that variant's stop); MFE is reported separately and
  never as a return.
- **13 stop bases per fire:** the incumbent (dip-low for the two reclaims, prior session low for
  the high break, low-of-day-at-cross for 620-prox) · the fire bar's own low · low-of-day at
  fire · prior session low · entry − k×ADR$ for k ∈ {0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0}
  (EP-anchored ADR$, `compute_ep_adr_dollar`) · the EP-day close · the EP-day low. All are
  levels the lane's code already computes; no new mechanics invented.
- **A stop at/above the entry KILLS the fire at birth** (no stop exists below the buy — the
  lane's own fill-sanity rule) — counted as a real cost with the incumbent's outcome on that
  fire shown (P14). **A basis unestablishable from stored bars ABSTAINS and is counted** (the
  fire-bar bases on the 33 daily-grade high-break fires derive the first level touch only when
  the 5-min series is gap-free through it — the prior study's exact convention).
- **Maturity discipline inherited verbatim:** expectancy = MATURE fires only (20 post-fire
  sessions existed by 08-31). Immature settled rows are stops by construction — never pooled.
  **August is therefore unreadable** (readable ~late September); the readable months are
  May/Jun/Jul. Era split (pooled AND ex-May, monthly sums) on every cell.
- **Fidelity gates, all green before any number was read:** 602/602 walk reproduction ·
  incumbent-column settlements identical to the recorded triggers (0 drift) · 620-prox
  lod==incumbent and high-break prior-low==incumbent asserted per fire (0 mismatches) · all
  432 rows of the prior study's `_562sp_stopvariants.tsv` reproduced exactly (0 diffs) ·
  ABVX 06-24 hand-walked from raw 5-min bars (fire bar m=615 close 82.00 reclaiming 80.77;
  post-fire dip to 79.51 stops the 0.50×ADR stop at 79.67 and misses the 0.75×ADR stop at
  78.51, which time-exits +14.07R — the knife edge is real in the bars).
- One convention: for every non-killing ADR base the mature comparison set is IDENTICAL per
  rung (n=130/86/32/126) — apples to apples; the structural bases shrink it by their kills.

## 3. The grid — mature fires, first attempts, both arms, pooled and ex-May

**Family summary first (all four rungs pooled; n=374 mature settled where nothing is killed):**

| stop basis | mature killed (n) | M-none mean / sum (n) | ex-May M-none (n) | M-trail mean / sum (n) | ex-May M-trail (n) | ≥4R none/trail (ex-May) |
|---|---|---|---|---|---|---|
| incumbent | 0 | −0.39 / −147R (374) | −0.66 (194) | −0.18 / −65R (374) | −0.29 (194) | 18/16 (6/8) |
| fire bar's low | 21 | −0.69 / −243R (353) | −0.81 (184) | −0.49 / −174R (353) | −0.46 (184) | 8/17 (4/10) |
| low-of-day at fire | 12 | −0.41 / −149R (362) | −0.63 (189) | −0.21 / −77R (362) | −0.31 (189) | 17/16 (7/8) |
| prior session low | 78 | −0.35 / −104R (296) | −0.53 (162) | −0.17 / −50R (296) | −0.16 (162) | 11/10 (5/6) |
| entry − 0.25×ADR | 0 | −0.06 / −22R (374) | −0.75 (194) | −0.02 / −9R (374) | −0.38 (194) | 16/19 (2/5) |
| entry − 0.50×ADR | 0 | −0.14 / −54R (374) | −0.40 (194) | −0.03 / −11R (374) | −0.11 (194) | 25/22 (10/10) |
| **entry − 0.75×ADR** | **0** | **−0.12 / −46R (374)** | **−0.24 (194)** | **+0.05 / +19R (374)** | **+0.05 (194)** | **30/16 (15/11)** |
| entry − 1.00×ADR | 0 | −0.11 / −41R (374) | −0.29 (194) | +0.07 / +26R (374) | +0.03 (194) | 25/11 (7/4) |
| entry − 1.25×ADR | 0 | −0.10 / −36R (374) | −0.24 (194) | +0.07 / +27R (374) | +0.07 (194) | 21/8 (6/3) |
| entry − 1.50×ADR | 0 | −0.13 / −47R (374) | −0.24 (194) | +0.06 / +23R (374) | +0.06 (194) | 14/7 (6/2) |
| entry − 2.00×ADR | 0 | −0.13 / −48R (374) | −0.24 (194) | +0.03 / +13R (374) | +0.04 (194) | 7/2 (5/2) |
| EP-day close | 176 | −0.33 / −66R (198) | −0.78 (101) | −0.05 / −10R (198) | −0.38 (101) | 6/10 (2/5) |
| EP-day low | 11 | −0.58 / −210R (363) | −0.67 (187) | −0.36 / −130R (363) | −0.31 (187) | 7/8 (4/6) |

### ep_low_reclaim — 203 fires, 130 mature (buy = the reclaim bar's close over the EP-day low)

| stop basis | killed (mature) | med stop | M-none mean/med (n) | M-trail mean/med (n) | ≥4R n/t | ex-May M-none (n) | ex-May M-trail | ex-May ≥4R n/t |
|---|---|---|---|---|---|---|---|---|
| incumbent (dip low) | 0 (0) | 2.1% ≈0.34×ADR | −0.39 / −1.00 (130) | −0.25 / −1.00 (130) | 6/3 | −0.62 (70) | −0.39 (70) | 2/1 |
| fire bar's low | 3 (1) | 1.0% ≈0.15×ADR | −0.51 / −1.00 (129) | −0.45 / −1.00 (129) | 6/6 | −0.72 (70) | −0.48 (70) | 3/3 |
| low-of-day at fire | 0 (0) | 1.9% ≈0.31×ADR | −0.37 / −1.00 (130) | −0.24 / −1.00 (130) | 7/3 | −0.57 (70) | −0.38 (70) | 3/1 |
| prior session low | 78 (45) | 0.8% ≈0.13×ADR | −0.54 / −1.00 (85) | −0.29 / −1.00 (85) | 4/4 | −0.65 (53) | −0.23 (53) | 2/3 |
| entry − 0.25×ADR | 0 (0) | 1.6% | −0.18 / −1.00 (130) | −0.19 / −1.00 (130) | 6/4 | −0.72 (70) | −0.60 (70) | 1/0 |
| entry − 0.50×ADR | 0 (0) | 3.1% | −0.14 / −1.00 (130) | +0.01 / −1.00 (130) | 11/9 | −0.34 (70) | −0.04 (70) | 5/4 |
| **entry − 0.75×ADR** | **0 (0)** | **4.7%** | **+0.02 / −1.00 (130)** | **+0.17 / −0.27 (130)** | **13/6** | **−0.03 (70)** | **+0.19 (70)** | **7/5** |
| **entry − 1.00×ADR** | **0 (0)** | **6.3%** | **+0.10 / −1.00 (130)** | **+0.25 / −0.07 (130)** | **12/5** | **−0.14 (70)** | **+0.16 (70)** | **3/2** |
| entry − 1.25×ADR | 0 (0) | 7.8% | +0.12 / −1.00 (130) | +0.19 / −0.05 (130) | 10/3 | −0.09 (70) | +0.12 (70) | 3/1 |
| entry − 1.50×ADR | 0 (0) | 9.4% | +0.05 / −1.00 (130) | +0.15 / −0.04 (130) | 6/3 | −0.11 (70) | +0.08 (70) | 3/1 |
| entry − 2.00×ADR | 0 (0) | 12.5% | +0.06 / −1.00 (130) | +0.11 / −0.03 (130) | 3/1 | −0.09 (70) | +0.05 (70) | 3/1 |
| EP-day close | 189 (120) | 1.6% | −0.19 / −1.00 (10) | +3.65 / −1.00 (10) | 1/2 | +0.35 (6) | +0.35 (6) | 1/1 |
| EP-day low | 0 (0) | 0.3% ≈0.06×ADR | −0.89 / −1.00 (130) | −0.66 / −1.00 (130) | 2/4 | −0.80 (70) | −0.51 (70) | 2/3 |

Monthly sums for the band, trail arm: **0.75×ADR: May +9.1R (n=60) · Jun +6.4R (n=44) · Jul
+6.7R (n=26)** — positive in every readable month, the only cell family on the board that is.
Drop-best-campaign (EFOR +11.6R): pooled +0.08/fire, ex-May +0.02. At 1.00×ADR: +0.19 / +0.04.

### ep_close_reclaim — 144 fires, 86 mature (buy = the reclaim bar's close over the EP-day close)

| stop basis | killed (mature) | med stop | M-none mean/med (n) | M-trail mean/med (n) | ≥4R n/t | ex-May M-none (n) | ex-May M-trail | ex-May ≥4R n/t |
|---|---|---|---|---|---|---|---|---|
| incumbent (dip low) | 0 (0) | 2.8% ≈0.50×ADR | −0.44 / −1.00 (86) | −0.06 / −1.00 (86) | 2/8 | −0.66 (42) | +0.03 (42) | 1/5 |
| fire bar's low | 2 (1) | 1.4% | −0.45 / −1.00 (85) | −0.11 / −1.00 (85) | 2/8 | −0.65 (41) | +0.07 (41) | 1/5 |
| low-of-day at fire | 0 (0) | 2.6% | −0.47 / −1.00 (86) | −0.08 / −1.00 (86) | 2/8 | −0.66 (42) | +0.03 (42) | 1/5 |
| prior session low | 18 (12) | 6.5% | −0.50 / −1.00 (74) | −0.24 / −1.00 (74) | 0/1 | −0.54 (38) | −0.01 (38) | 0/1 |
| entry − 0.25×ADR | 0 (0) | 1.5% | −0.25 / −1.00 (86) | +0.01 / −1.00 (86) | 3/7 | −0.29 (42) | +0.33 (42) | 1/4 |
| entry − 0.50→2.00×ADR | 0 (0) | 2.9–11.6% | −0.32..−0.57 (86) | −0.09..−0.25 (86) | ≤4/≤3 | −0.31..−0.66 (42) | −0.09..+0.05 (42) | ≤1/≤2 |
| EP-day close | 0 (0) | 0.5% ≈0.10×ADR | −0.88 / −1.00 (86) | −0.27 / −1.00 (86) | 1/5 | −0.76 (42) | −0.13 (42) | 1/3 |
| EP-day low | 0 (0) | 7.8% | −0.54 / −1.00 (86) | −0.23 / −0.60 (86) | 0/1 | −0.58 (42) | −0.03 (42) | 0/1 |

The one positive-looking cell (0.25×ADR trail, ex-May +0.33) is **FET-carried**: drop that single
fire (+20.3R) and it is −0.16 (n=41). Monthly: May −13.1 · Jun −16.3 · Jul +30.2 — one July name.

### ep_high_break — 48 fires, 32 mature (buy = the EP-day high, a stop-buy at the level)

| stop basis | killed (mature) | med stop | M-none mean/med (n) | M-trail mean/med (n) | ≥4R n/t | ex-May M-none (n) | ex-May M-trail | ex-May ≥4R n/t |
|---|---|---|---|---|---|---|---|---|
| incumbent (prior low) | 0 (0) | 10.8% ≈1.91×ADR | −0.41 / −1.00 (32) | −0.12 / −0.39 (32) | 2/0 | −0.81 (17) | −0.23 (17) | 0/0 |
| fire bar's low | **21 (12)** | 1.4% | −1.00 / −1.00 (20) | −0.72 / −1.00 (20) | 0/1 | −1.00 (12) | −0.54 (12) | 0/1 |
| low-of-day at fire | **21 (12)** | 2.2% | −0.82 / −1.00 (20) | −0.72 / −1.00 (20) | 0/0 | −0.71 (12) | −0.54 (12) | 0/0 |
| entry − 0.25×ADR | 0 (0) | 1.4% | **+1.66** / −1.00 (32) | +1.18 / −1.00 (32) | 2/3 | **−1.00 (17)** | +0.02 (17) | 0/1 |
| entry − 0.50×ADR | 0 (0) | 2.8% | +0.36 / −1.00 (32) | +0.23 / −1.00 (32) | 2/3 | −1.00 (17) | −0.40 (17) | 0/1 |
| entry − 0.75×ADR | 0 (0) | 4.3% | +0.12 / −1.00 (32) | +0.10 / −1.00 (32) | 3/3 | −0.64 (17) | −0.18 (17) | 1/1 |
| entry − 1.00→2.00×ADR | 0 (0) | 5.7–11.4% | −0.30..+0.04 (32) | +0.02..+0.08 (32) | ≤3/≤2 | −0.59..−0.74 (17) | −0.29..+0.03 (17) | 0/0 |
| EP-day close | 0 (0) | 2.2% ≈0.40×ADR | **+1.63** / −1.00 (32) | +0.88 / −1.00 (32) | 2/3 | −0.75 (17) | −0.16 (17) | 0/1 |
| EP-day low | 0 (0) | 11.1% | −0.39 / −1.00 (32) | −0.11 / −0.39 (32) | 2/0 | −0.77 (17) | −0.23 (17) | 0/0 |

**Ex-May, NO basis rescues this rung**: under 0.25×ADR all 17 ex-May mature fires are full stops
(0-for-17); the pooled +53R is VPG +49.5R and ARM +33.8R — two May gap-over fires. The prior
study's headline survives the widening of the grid but its meaning changes: it is May evidence,
not a rung property. The bar-low kills (VPG and ARM, the rung's only winners, because winners GAP
OVER the level) stand as before.

### ep_close_620_prox — 207 fires, 126 mature (buy = the qualified 620 cross close near the EP close)

| stop basis | killed (mature) | med stop | M-none mean/med (n) | M-trail mean/med (n) | ≥4R n/t | ex-May M-none (n) | ex-May M-trail | ex-May ≥4R n/t |
|---|---|---|---|---|---|---|---|---|
| incumbent (LOD at cross) | 0 (0) | 2.1% ≈0.34×ADR | −0.35 / −1.00 (126) | −0.19 / −1.00 (126) | 8/5 | −0.67 (65) | −0.41 (65) | 3/2 |
| fire bar's low | 7 (7) | 0.4% ≈0.06×ADR | **−1.00** / −1.00 (119) | −0.77 / −1.00 (119) | 0/2 | −1.00 (61) | −0.78 (61) | 0/1 |
| prior session low | 34 (21) | 4.6% | −0.08 / −1.00 (105) | −0.04 / −0.63 (105) | 5/5 | −0.33 (54) | −0.18 (54) | 3/2 |
| entry − 0.50×ADR | 0 (0) | 2.9% | −0.07 / −1.00 (126) | −0.03 / −1.00 (126) | 8/7 | −0.17 (65) | −0.13 (65) | 4/3 |
| **entry − 0.75×ADR** | **0 (0)** | **4.3%** | **−0.02 / −1.00 (126)** | **+0.12 / −0.49 (126)** | **11/6** | **−0.10 (65)** | **+0.06 (65)** | **6/4** |
| entry − 1.00→1.25×ADR | 0 (0) | 5.8–7.2% | −0.10..−0.12 (126) | +0.07..+0.12 (126) | ≤7/≤3 | −0.17..−0.24 (65) | −0.03..+0.09 (65) | ≤3/≤1 |
| EP-day close | 100 (56) | 1.6% | −0.58 / −1.00 (70) | −0.74 / −1.00 (70) | 2/0 | −1.00 (36) | −0.89 (36) | 0/0 |
| EP-day low | 14 (11) | 5.1% | −0.30 / −1.00 (115) | −0.18 / −0.50 (115) | 3/3 | −0.55 (58) | −0.29 (58) | 2/2 |

Monthly trail sums at 0.75×ADR: May +11.6 (n=61) · Jun +2.5 (n=38) · Jul +1.2 (n=27) — all
positive, but drop-best-campaign (EFOR +11.9R) leaves ex-May at −0.13. ⚠ This rung is NOT an
independent confirmation of ep_low_reclaim: 109 campaigns carry both rungs' mature fires, 26 fire
the SAME day, and the winner lists share TE, EFOR, AKTS, MMYT, STUB — one pullback measured twice.

## 4. Plain words — the verdict per signal

- **The grid has a shape, and it is the same shape everywhere: the stop that works is
  proportional to the stock's volatility, not anchored on structure.** Every incumbent sits
  OUTSIDE the 0.75–1.25×ADR band — the three pullback rungs at 0.34–0.50×ADR (inside one
  session's noise: the median fire is a full stop), the high break at 1.91×ADR (so wide the
  winners barely pay). Moving INTO the band improves every rung, from either direction.
- **POSITIVE (thin): `ep_low_reclaim` × entry−0.75..1.00×ADR × trail exit.** +0.17..+0.25R/fire
  pooled (n=130), **+0.16..+0.19 ex-May (n=70)**, positive in May AND June AND July, survives
  drop-best pooled (+0.08..+0.19); after drop-best ex-May it is +0.02..+0.04 — a band that
  holds everywhere but thinly. Under the trail arm the median fire becomes a −0.27..−0.07R
  scratch instead of a −1.00R stop-out — this is the risk-management reframe made literal: the
  wide stop is disaster insurance, the trail is the working exit, and the full stop stops being
  the median outcome. At live sizing the band's ~4.7–6.3% width also deploys near-full risk
  (the 20% notional cap truncates below ~5%), unlike the 0.25×ADR razor: cap-scaled dollar
  terms, ex-May, incumbent −5.3R-eq → 0.75×ADR +13.7R-eq (n=130).
- **BREAK-EVEN: `ep_close_620_prox` × the same band × trail** (+0.12 pooled, +0.06 ex-May,
  n=126; drop-best ex-May −0.13) — and it is correlated with the cell above, not independent.
  Also `ep_low_reclaim` band on M-none (−0.03..+0.02) and wide-ADR high-break trail (≈0).
- **DEAD: `ep_close_reclaim` under every basis** (best cell FET-carried), **`ep_high_break`
  ex-May under every basis** (0 positive cells, 17 mature fires), **every bar-anchored stop on
  every rung** (fire bar's low: worse than the incumbent on all four rungs — 0% win M-none on
  the high break and on 620-prox, where all 119 mature fires are full stops (n=119), 5–6% win on
  the reclaims — plus it kills VPG/ARM on the high break), **the EP-day low as a stop for the low-reclaim**
  (0.06×ADR ⇒ −0.89R/fire, worst on the board), and **every above-entry structural pivot**:
  the EP-day close as a stop kills 176 mature pullback fires at birth including EVERY big
  winner both reclaim-side rungs ever produced (STUB +11.4, TE +10.7, ABVX +6.8, GO +6.6,
  FPS +6.5, BHVN +6.7, NAVN +4.9 — each shown against its incumbent harvest), and the prior
  session low kills 45 mature low-reclaim fires including ABVX +6.8. **A stop basis must sit on
  the pullback's own side of the entry; a pivot above the buy point selects out the winners.**
- **What the winning cells kill to get there: NOTHING.** The ADR bases kill zero fires on any
  rung — recall (P1) fully intact, all 13 ran-hard campaigns still covered. The cost is not
  kills; it is that R units grow with width, so the same move pays fewer R (family ≥4R falls
  30 → 7 from 0.75×ADR to 2.00×ADR on M-none) — the band peaks where noise-survival and R-unit
  size trade off, and beyond 1.25×ADR both arms decay.
- **Caught-but-not-kept (MFE, separately):** at 0.75×ADR on the low-reclaim, 25 of 130 mature
  fires TOUCH ≥4R in their own units; M-none harvests 13, the trail keeps 6. The harvest layer
  still gives back roughly half of what the entry+stop finds — the campaign study's management
  finding, unchanged by the stop.
- **The knife edge is real and argues for a band, not a value:** ABVX's +14.07R at 0.75×ADR is
  −1.00R at 0.50×ADR — twenty cents of stop on an $82 entry, verified in the raw 5-min bars.
- **Honesty about breadth:** ~104 cells per arm were scanned; the strongest surviving cell is
  +0.19R/fire ex-May. Any SINGLE cell at that size would be noise. The evidence is the
  STRUCTURE — a smooth monotone band, the same direction on all three pullback rungs, positive
  in every readable month on the best rung, robust to drop-best pooled — but the honest status
  is *candidate for a forward out-of-sample read*, not a proven edge.

## 5. What this says (and the fork)

The operator's frame survives contact with the full grid, with a sharper answer than the
one-signal sweep gave: **the stop is a real lever family-wide — it moves the whole family
roughly +0.25R/fire (−0.18 → +0.05 trail, holding ex-May: −0.29 → +0.05) while killing nothing —
but on this population it turns "clearly losing" into "about break-even", not into a business.**
The one cell that clears zero everywhere is the EP-low reclaim with a 0.75–1.00×ADR stop under
the trail exit. Selection (P13) and the harvest layer still decide whether anything compounds on
top of that base — but they would now be compounding on ~breakeven instead of on a −0.4R/fire
bleed, which is the difference between a system that can be improved and one that cannot.

Fork for the operator (evidence only, his call — nothing flipped, nothing proposed as done):

- **(1)** If any rung's recorded stop changes, the candidate is **entry − 0.75×ADR (band
  0.75–1.00) on `ep_low_reclaim`**, judged on the trail arm — a nameable setup with a buy (the
  reclaim close over the EP-day low) and a stop. The shadow lane's schema carries stop width
  first-class and can record BOTH bases forward, making September's accrual the out-of-sample
  test. A rung change is CHANGE_PROCESS + sign-off.
- **(2)** Retire the structural bases from further delayed-entry work: bar-low, LOD-at-fire,
  EP-close-below-pullback-entries, prior-low-under-reclaims are dominated or winner-killing on
  every rung measured.
- **(3)** Do not build on the high-break +53R: ex-May it is 0-for-17 under the very stop that
  produced it. If the gap-over monsters (VPG/ARM class) matter, that is a different entry
  definition (buy the gap-over open), not a stop choice on this rung.

## 6. What this does not answer

- **Whether the band survives out of sample.** ~104 cells per arm were scanned and the winner
  is +0.19R/fire ex-May at n=70 — real structure, thin magnitude. Only the forward lane (or a
  pre-2026-05 backfill extension) separates a durable band from a well-dressed survivor.
- **August, at all** — 228 immature fires; settled August rows are stops by construction;
  readable ~late September. Every number above is May–July.
- **Whether May's tail supply was regime or luck** — unchanged from the backfill; three May
  campaigns from one hot week still carry most of the pooled tail.
- **The gap-over entry itself** on the high break (a killed bar-low fire means "no stop below
  the booked level", not "untradeable at the open with a different definition").
- **Re-entry economics and any management beyond the two modelled arms** — the +2R-partial live
  shape is deliberately not an arm (operator 08-30); MFE says the harvest layer binds either way.
- **Per-stock character** (the 06-11 ruling): every ADR multiple here is still one global
  parameter; a per-name band is the anti-pattern fix this grid cannot test at n=1 per name.
- **Whether the trail arm's advantage is exit alpha or just loss-truncation** — mechanically it
  is the latter (losers exit at the SMA cross before the far stop); the grid cannot say whether
  a different loss-truncation (time stop, tighter trail) does better.
- **The behavioural "near"** for rung 4 — still the ±0.5×ADR placeholder band, not the 08-29
  behaviour ruling.

## 7. ⚖ THE LINE

Entry/exit discipline, stops, selection rules, sizing and every threshold are the operator's
sole authority. This grid measures and ranks; it changes no rung, no threshold, no live code.
No prod access occurred (captured files only); the live lane and its tables were not touched.

---
*Population: the backfill's 267 campaigns / 602 first-attempt fires, walk reproduced exactly
(602/602, 0 mismatches) before varying anything. Rows: `_562grid_rows.tsv` (7,826 = 602 × 13).
Hand-verified: ABVX 06-24 fire and both settlement branches from raw bars; VPG +49.45R / ARM
+33.75R carried over unchanged from the prior study's hand checks (its 432 rows reproduce to 0
diffs). Related: PLAN #562/#327/#545; `docs/setups/delayed_ep_reentry.md § THE CONTEXT LEDGER`
needs its row for this doc — ledger edit deliberately left to the main session (this card is
scoped to `scripts/probes/` + `docs/analysis/`).*
