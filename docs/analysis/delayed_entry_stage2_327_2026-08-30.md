# #327 Stage 2 — The eight #562 triggers, priced on the EPs that got past us (2026-08-30)

> 🗂 **DELAYED-ENTRY CONTEXT LEDGER — READ FIRST: `docs/setups/delayed_ep_reentry.md § THE CONTEXT LEDGER`.** It carries the goal, every operator ruling, every study and its result, and the open questions.

**⚖ THE LINE — MEASUREMENT ONLY.** Entry discipline, triggers, stops and re-entry rules are the
operator's sole authority. Nothing here is flipped, shipped, or proposed as decided. $0 — prod
read-only (SELECT only), no LLM calls, no backfill run, no commits to live code.

## The decision this serves

The operator's question behind the whole program (P1): *a real EP got past us on day 1 — what do
we watch for, in what order, with what buy and stop?* #562 priced his eight triggers on 44
episodes we ENTERED and were STOPPED OUT of — a population Stage 1 showed is materially different
(gaps 12.1–20.9% vs the ≥10R missed class at 8.7–11.1%, and ~93% tail-free). **This stage answers
the transfer question Stage 1 raised: does #562's ranking hold on the population the question is
actually about?** What would change the decision: if the missed-cohort ranking matched #562's
(everything ≈0 or negative), the delayed-entry lane would be dead on its motivating population;
if arms bank 4R+ tails at material rates, the lane is worth the operator's design attention and
the arm ordering tells him where. Judged by P3 (the tail, not the average) and P4 (return on
risk), never by win rate alone.

## Method — population, instrument, era

- **Population: the 55 missed-real-EP events of `missed_ep_population_327_2026-08-29.md`**
  (24 tier-1 ≥10R · 25 tier-2 5–10R · 6 tier-3 provisional; per-event rows
  `327s1_metrics.psv`). Its per-cause counts are NOT used anywhere here (the correction banner:
  the top-20-by-gap attribution describes a retired rule); only the membership is.
- **Window and rules: byte-faithful to #562** — signals on 5-min bars resampled from
  `mi_intraday_bars` 1-min rows, following sessions +1..+25 after the EP day, one entry per
  episode per arm, first fillable signal decides, entry = next 1-min bar's open, signals after
  15:54 ET lapse. Exits: the `geometry_sweep_572.simulate` policy unchanged (+2R partial half →
  breakeven → MAX(SMA10,SMA20) daily-close trail → 20-session time stop), conservative
  sequencing, entry day walked at 1-minute resolution. Data edge 2026-08-28; a position still
  open there is an OPEN MARK, reported separately, never banked.
- **Instrument reconstruction, because #562's probe file no longer exists.** The 620 turn was
  rebuilt from the study text + the Stage-0 reconstruction that already reproduced SMCI's entry
  to the minute: MACD(6,20) on 5-min closes, EMA-9 signal, continuous across sessions; qualified
  bullish cross = cross with MACD<0 + basing (high−low range of the prior 8 buckets ≤ 0.4×ADR$,
  ADR$ = 20-day mean daily range × EP-day close) + the hook (MACD's 6-bucket min ≤ its 12-bucket
  min — the tightest form consistent with the TEAM worked example, whose low sits exactly 6
  buckets before the cross). EPC-REC re-arms after a failed reclaim; EPL-UR is one-shot with the
  2-session reclaim window; EPH-BRK is a resting buy-stop at the EP-day high, prior session's
  low as stop.
- **Fidelity, verified before any missed-cohort number was read** (calibration = the stopped-44
  re-run at the study's own 08-21 edge):
  - **Nine anchor trades reproduce exactly**: INTC EPC-REC 04-28 @82.91/80.80 → +7.13R · INTC
    EPH-BRK +3.10 · INTC 620-ANY/@EPC d+1 −1.00 each · SMCI 05-06 EPC-REC +1.67 · SMCI EPH-BRK
    +2.41 · NRIX EPH-BRK +1.80 · SMCI 07-22 620@EPC 08-06 12:50 @30.15/29.33 → +5.45 · TEAM
    620@EPC @148.14/145.00 → +4.77 (entry minute 11:40 vs the study's 11:41 — same bar prices,
    same stop, same R; ±1 bucket is the reconstruction tolerance).
  - **Three arms reproduce Result 1 to every column** (n, win%, median, mean, sum): EPL-UR
    34 fires/−18.97R · EPC-REC 36/−2.26 (study −2.29) · EPH-BRK 28/−0.75, med stop 7.7%.
  - **620 arms reproduce their fire counts** (@EPC 31, @PDH 23, ANY 44 exact; @EPL 37 vs 34,
    @MA10 41 vs 40) and both @EPC open marks (+10.22 exact), but per-episode cross SELECTION
    differs on a handful of episodes: my per-trade means sit −0.19 to +0.32R from the study's
    on the same cohort (e.g. @EPL −0.14 vs −0.44), and turn multiplicity reads 1.38/session vs
    the study's 1.12 — the backfilled bar table is richer than the study's capture, so some
    crosses shift. **⚠ Reproduction tolerance: differences under ~0.4R/trade on a 620 arm are
    instrument noise, not population signal.** The cross-population deltas below are 5–10× that.
- **Era**: the missed events span March–August under whatever admission ran each day — that
  heterogeneity is intrinsic to a missed-EP population (the miss, not the admission rule, defines
  membership). Live/paper pooling does not arise (none of these were trades).
- Captures (pulled once, read many): `~/.claude/jobs/6b173ac9/tmp/327s2_*` — 684,510 minute
  bars, merged daily, episodes, trades, probe + calibration scripts.

### ⚠ The coverage boundary — 12 of 55 events cannot be priced at all

`mi_intraday_bars` holds forward bars for **861 of the missed cohort's 1,350 ticker-sessions
(64%)** — against 100% for the stopped 44. The forward backfill was anchored on scan-log/alert
ticker-days, and the cap-killed tier-1 names were RECONSTRUCTED (never logged), so their April
windows were never backfilled. **Dark (0 bars, n=12):** MRVL, ASX, SNDK, ALGM, AMKR, FLY 03-12,
SMTC (t1) · AUGO, NSIT, GLXY, FLY 03-20, LGN (t2). **Partial (n=19)**, concentrated on the
04-08 cluster (MU 3/25, NBIS 1/25, IREN 4/25 …). **Evaluable: n=43** (24 full-coverage, 19
partial — a partial event can only fire where bars exist, so its entry timing is biased late).
The hole is NOT random: it removes 7 of tier-1's 24 members and most of the 04-08 cap-kill
cluster — the small-gap April class Stage 1 flagged — so the evaluable 43 over-represent
May–August. Extending the backfill work-list to the reconstructed names is a $0 sibling task
(prod write → not run from this read-only card).

## The numbers — the eight arms on the missed cohort (n=43 evaluable, data to 08-28)

| arm (buy / stop) | fires/43 | win% | med R | mean R | sum R | ADR/t | ≥2R | ≥4R | full stops | med stop |
|---|---|---|---|---|---|---|---|---|---|---|
| EPL-UR (reclaim of undercut EP-low / min low since undercut) | 13 | 38 | −1.00 | **+5.79** | +75.3 | +1.62 | 4 | 4 | 7 | 3.4% |
| EPC-REC (reclaim of EP-close / min low of below-stretch) | 23 | **57** | **+1.02** | +2.26 | +52.1 | +2.10 | 10 | **5** | 8 | 7.5% |
| 620@EPL (620 turn near EP-low / low-of-day) | 13 | 38 | −1.00 | +2.57 | +33.4 | +0.79 | 3 | 3 | 8 | 1.9% |
| 620@EPC (620 turn near EP-close / low-of-day) | 18 | 39 | −1.00 | +1.40 | +25.1 | +0.27 | 3 | 3 | 11 | 1.3% |
| 620@PDH (620 turn near prior-day high / low-of-day) | 6 | 50 | −0.27 | +1.83 | +11.0 | +0.66 | 1 | 1 | 3 | 1.2% |
| 620@MA10 (620 turn near SMA10 / low-of-day) | 21 | 48 | −0.58 | +0.38 | +8.0 | +0.19 | 3 | 2 | 9 | 3.1% |
| 620-ANY (any qualified turn / low-of-day) | 40 | 42 | −1.00 | +1.18 | +47.1 | +0.42 | 7 | 5 | 23 | 2.0% |
| EPH-BRK (buy-stop at EP-high / prior session low) | 41 | 56 | +0.26 | +0.72 | +29.5 | +1.79 | 10 | 1 | 11 | 13.4% |

Open marks: one (EPH-BRK GFI +1.12 at the 08-28 edge). Everything else is settled inside the
simulator. The dark 12 fire nothing by construction and are NOT in any denominator above.

**Single-mover sensitivity (§5 — the carriers, named):** ALMU 04-13 carries EPL-UR (+51.3R on a
0.93% stop; ex-ALMU the arm is **+2.00 mean, −1.00 median** over n=12) and 620@EPL/620-ANY
(+25.6R). FTNT 05-07 carries EPC-REC (+13.3R; **ex-top-1 +1.76 mean, +1.01 median**, n=22).
NOK 04-23 carries @EPC and is the entirety of @PDH's sum (ex-NOK @PDH is −0.36 over n=5).
EPH-BRK ex-top-1: +0.61 mean, +0.24 median (n=40). **The only arms whose MEDIAN stays positive
after dropping their best trade: EPC-REC and EPH-BRK.** ⚠ R on sub-1% stops is volatility in
disguise (the study's own warning): ALMU's +51R is +5.6 in ADR units — real, but the R unit
flatters it; the ADR/t column is the honest cross-check, and it ranks EPC-REC (+2.10) and
EPH-BRK (+1.79) first.

**The fire-rate inversion — the structural finding:**

| arm | fires on missed (n=43) | fires on stopped (n=44, same instrument) |
|---|---|---|
| EPL-UR | 30% | 77% |
| EPC-REC | 53% | 82% |
| 620@EPL | 30% | 84% |
| 620@EPC | 42% | 70% |
| 620@PDH | 14% | 55% |
| 620@MA10 | 49% | 95% |
| 620-ANY | 93% | 100% |
| EPH-BRK | **95%** | 64% |

Real EPs rarely come back to the pullback pivots (`pivot_proximity_2026-08-16.txt` said exactly
this: the strongest names never approach), so the pullback-side arms fire on a third to a half
of them — while the breakout-side EPH-BRK fires on 95%. Qualified 620 turns are also scarcer on
runners: 0.87/session vs 1.38 on the stopped cohort.

**Transfer verdict — #562's ranking does NOT transfer; it roughly inverts.** Same instrument,
both cohorts, settled to 08-28: on the stopped 44 every arm sits between −0.52 and +0.08R/trade
(620@EPC +0.08 the best, EPL-UR −0.52 the worst — matching the study). On the missed 43 every
arm is mean-positive, the stopped cohort's WORST arm (EPL-UR — the operator's original MNTS
undercut-and-rally blueprint) is top by mean and its structure-sibling EPC-REC is top by median
and ADR, while the stopped cohort's ONLY positive (620@EPC) is mid-pack. The deltas (e.g.
EPC-REC +2.26 vs −0.02; EPL-UR +5.79 vs −0.52) are 5–10× the ≤0.4R instrument tolerance.

**P3 — the tail, answered separately from the average:** realized 4R+ per arm: EPC-REC 5 ·
620-ANY 5 · EPL-UR 4 · 620@EPL 3 · 620@EPC 3 · @MA10 2 · @PDH 1 · EPH-BRK 1 (EPH-BRK's wide
stop converts tails into low-R wins — 10 of 41 reach 2R but only 1 reaches 4R; in ADR units it
is second-best). **Union across the ladder (hindsight best-arm — a capture CEILING, not a
tradeable number): 12 of 43 evaluable events (28%) bank ≥4R; 19 (44%) ≥2R; 32 (74%) >0; on 6
events every arm that fired stopped out; every evaluable event fired at least one arm.** Against
THE GOAL's arithmetic (~4 tail winners in 4½ months), 12 recovered 4R+ names over ~5 months of
missed events is material — conditional on the caveats below.

**The stop-dies-first mechanism, reproduced and amplified:** of the 80 full stop-outs across
the seven pullback-side arms, **72 sat in front of a ≥4R favourable excursion after the entry**
(EPL-UR 7/7, EPC-REC 8/8, @EPL 7/8, @EPC 10/11, @PDH 3/3, @MA10 9/9, ANY 22/23; EPH-BRK 6/11).
On a population that is all-tail by label this is partly by construction — but it is the same
disease #562 Result 4 measured (tight stop under a 5–8%-ADR name dies to noise in front of the
run), and it says the binding constraint on this cohort is still stop geometry, not location.

**Tier splits (thin — §5, no conclusion from cells under n=10):** tier-1 evaluable n=17: EPH-BRK
fires 17/17 (+0.51 mean, med −0.15), EPL-UR +3.25 (n=5), but the 620 timing arms are flat-to-
NEGATIVE (620-ANY −0.42 over 14, @EPL −2.10 over 4) — on the very class where every name is a
≥10R winner by label, the intraday timing arms still failed to convert. Tier-2 (n=20 evaluable)
carries most of the pooled sums; tier-3 (n=6, provisional labels) is small positives, EPH-BRK
5/6 winners. The 04-08 cluster does not drive the headline — its evaluable members fired only on
the late-window arms (ex-cluster table nearly identical for the top arms).

## What this does not answer

- **A tradeable expectancy. The label is outcome-conditioned** — every member went on to a
  5–10R+ tail, so every positive number is inflated by construction. Real EPs that FAILED are
  invisible to the label; a live watch-lane would also fire on those and bleed. The stopped-44
  is the closest available proxy for that bleed (real-EP-shaped names, ~93% tail-free): there
  the same arms return −0.5 to +0.1R/trade. A live blend sits between the two tables, weighted
  by how rare real tails are among fired names — and **no ex-ante feature measured here
  separates the two populations at trigger time** (that is P13's unpriced-residual question,
  not the trigger's).
- **Whether the dark 12 would change the ranking.** The coverage hole is correlated (April
  cap-kill / March pre-instrumentation names — 7 of tier-1's 24), not random. 64% ticker-session
  coverage is the honest denominator; the missing third is the small-gap April class.
- **Sub-population reads.** Per-arm n = 6–41; tier cells 1–18; several arms' sums are one trade
  (@PDH). Six tickers carry two overlapping episodes each (ELPW 04-22/24 fire the identical
  trade twice; DFNS, SDOT, UMC, FLY similar) — these are correlated, not independent trials.
- **Fills.** The engine's measured optimism (+0.41R/trade, #572) applies to every positive here;
  several carriers are thin micro-caps (ALMU $14, DFNS $4→$39, SDOT, ELPW $4.10) where modeled
  minute-open fills understate slippage badly — and ALMU (mcap floor), ELPW/DFNS ($5 floor)
  are names the live auto-lane's still-live floors would refuse today, so part of the
  recoverable R exists only if the operator's WATCH lane (which deliberately includes
  sub-$500M) is where these fire.
- **The day-0 re-entry arm** (the operator's own TEAM move) — still unpriced, pre-registered
  in #562; unchanged here.
- **Tier-3's labels** confirm ~mid-October; the full #562 re-cut on TEAM's settle (09-08)
  remains pre-registered.
- **"Near" as behaviour** (the 08-29 ruling): every 620 arm here still uses the rigid ±0.5×ADR$
  proximity band the ruling replaces — kept deliberately so #562's definitions transfer intact.
  A behaviour-based "near" is a different instrument and a different card.

## What would settle it further ($0, in order of information per dollar)

1. **Backfill the dark 12's forward windows** (extend the work-list to reconstructed names) and
   re-run this exact probe — closes the correlated coverage hole; prod write, needs its slot.
2. **Price the stopped-44 as a bleed model**: blend tables at plausible real-EP base rates to
   bound what a live watch-lane would net.
3. TEAM settles 09-08 → the pre-registered #562 re-cut settles the 620@EPC sign question.

## Files

- This doc: `docs/analysis/delayed_entry_stage2_327_2026-08-30.md`
- Probe + calibration + runs: `~/.claude/jobs/6b173ac9/tmp/327s2_probe.py`, `327s2_final.py`,
  `327s2_run.py`, `327s2_calib*.py`, `327s2_sens.py`, `327s2_dump.py`
- Captures (pulled once): `327s2_min_out.psv` (684,510 bars), `327s2_daily_all.psv`,
  `327s2_episodes.json`; per-trade rows `327s2_trades_final.psv`
- Companions: `delayed_entry_562_2026-08-22.md` (the stopped-cohort study) ·
  `missed_ep_population_327_2026-08-29.md` (Stage 1) · `pivot_proximity_2026-08-16.txt`
