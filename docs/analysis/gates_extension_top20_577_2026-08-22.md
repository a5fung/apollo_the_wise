# #577 CARD A — Pricing the two biggest winner-killers: `extension_gate` and `outside_top20` (2026-08-22)

**MEASUREMENT ONLY. No criterion changed, nothing deployed. Any loosening is CHANGE_PROCESS +
operator sign-off (THE LINE), one gate at a time, smallest first (P9).**

## The question

The 08-21 gate ranking put these two at the top: together they excluded **55 names that later
reached a ≥100% 20-day peak** — more than triple the ADV floor and cooldown combined. Neither
had ever been priced. The operator's stated fear: *"it's hard for us to catch the 1-3 real ep
big winners per quarter if we might kill them off before even evaluating let alone trading
them."* This card prices both the way the 9% gap floor was priced (P5: both directions;
P3: tail first; P1: name every real winner killed).

## Where each gate sits (this controls what every count means)

- **`outside_top20`** — `ep_detector.py:2800`. Candidates are sorted by gap size each scan
  tick; ranks 21+ are logged and never evaluated. It is the SECOND wall (only the gap floor
  precedes it). A blocked name was never tested against RVOL, cooldown, extension, quality
  or scoring — the rawest population in the whole table.
- **`extension_gate`** — `ep_detector.py:3017-3022`. Skip if (prev close − MIN(close, prior
  ~5 sessions)) / MIN ≥ **50%** (`MAX_EXTENSION_PCT`, line 158). Mid-cascade: blocked names
  already passed the gap floor, top-20 cap, RVOL/pace and cooldown; they were never tested
  against ADV → ATR% → mcap (`backtester/filters.py::check_filters`) or catalyst/score.
  The same constant also gates the #490 rt-miss watchdog (line 2332) — a loosening widens
  both automatically.

## Data and provenance

- `mi_ep_missed_outcomes`: 170 extension rows (102 names, 04-16 → 08-21) and 789 top-20 rows
  (627 names, 04-14 → 08-07). Head-start said 167/789 — 3 extension rows accrued since.
- **Return basis verified in code**: every `ret_*`/`max_high_*` is from **`open_d0`, the
  gap-day OPEN** (`missed_outcomes.py`, "what a day-2 chaser pays"). Not our ORB entry, and
  a `max_high` is an excursion nobody could time. Used as context, never as the verdict.
- Ranks: `mi_ep_scan_log.rank_by_gap` where logged (547 ticker-days); **reconstructed for the
  April rows that predate the column** (242) from same-day skip-gap ordering — exact on
  single-tick days, and where both exist the reconstruction overstates rank by ~7 (median),
  so April recovery counts below are if anything UNDERSTATED.
- Remaining-gate replication: ADV (median 20d $ volume ≥ $1M, <10 bars = fail, live
  behavior), ATR-14 Wilder /close ≤ 15%, extension, 60d cooldown vs `mi_ep_alerts` — all
  recomputed point-in-time from `mi_daily_closes` on bars strictly before the alert date.
  Market cap: `mi_market_caps` + yfinance fill, **fail-open on missing data exactly as the
  live gate** (`_check_market_cap` returns pass when FMP has nothing).
- Captures (pulled once, read many, $0, read-only): `scratchpad/577_extension.psv`,
  `577_top20.psv`, `577_batch{4,5,6,7,8}.out`, `577_mcap_yf.psv`; computation
  `577_local.py`, `577_ranks.py`, `577_bandrep.py`, `577_final.py`.

---

## Gate 1 — `extension_gate` (already up ≥50% in the prior 5 sessions)

### Result 1 — the unconditional distribution: the most toxic cohort of any gate priced yet

All 170 rows, open basis, no outcome conditioning:

| horizon | median | notes |
|---|---|---|
| 5d close | **−25.6%** | only 20% positive |
| 20d close | **−43.7%** | only 22% positive; **63% fall ≥30%, 39% fall ≥50%** |

The tail is also the biggest of any gate (P3): 33.5% of rows reach a ≥50% 20-day peak, 17.1%
reach ≥100%. Huge peaks over ruined closes = the pump-and-fade shape. The 29 doubler rows are
**18 distinct names** — SDOT ×4, AKAN ×3, NVVE ×3, PN ×3, AIOS/DFNS ×2 — the same pumps
re-firing. Doubler median 20-day CLOSE is +13% against a +79% median peak (outcome-selected,
so even that is generous).

### Result 2 (the decisive correction) — 91% of its kills would have died anyway

Replaying every one of the 170 rows through the gates it was never tested against
(ADV → ATR% → mcap): **155 of 170 die anyway** — mostly at ADV (116) and ATR% (27). A
name up 50%+ in five sessions almost always carries a disqualifying ATR or a micro-cap
ADV. The gate's UNIQUE kills — names the rest of the stack would have admitted — are
**15 rows / 13 names in 4 months**:

| ext band | unique kills | what they did (peak20 / 20d close) |
|---|---|---|
| **50-75%** | **8** | **MXL +93/+84 · FCEL +108/+63 · MRAM +140/+41 · POET +81/+28 · SWMR +66/−18** · RGTU +8/−10 · SCTX +9/unsettled · SIDU 0/−63 |
| 75-100% | 5 | POET +53/+8 · REPL +40/+24 · DGXX +24/−20 · **SPCE +22/−60 · CAR +9/−80** |
| ≥100% | 2 | POET +118/+40 (same episode as its 04-22 row) · XNDU +44/−49 |

- **The 50-75 band is the good slice**: 5 of 8 ran ≥50%, 2 doubled, one bad loser (SIDU −63%,
  mcap borderline $240-500M). This is the exact band a 50→75 loosening admits.
- **75-100 is the dead zone** (the #556 pattern again): best is +53% peak; it contains the two
  genuine disasters the gate prevented — CAR −80% and SPCE −60%.
- ≥100 adds nothing a 75% cap plus the 60d cooldown doesn't already get: POET's +118% row is
  the same episode a 75% cap catches 3 days earlier (and the cooldown then suppresses the
  re-fire); XNDU closed −49%.
- These still face catalyst grading + score ≥ 50 + the HIGH bar — measured pass rate for
  names reaching that stage is **~24%** (≈190 HIGHs of ≈787 reaching catalyst). So a 75% cap
  yields **~2 extra HIGH alerts per 4 months**, of which ~1 in expectation is a ≥50% runner.
  (Caveat: that 24% is a population average; how the grader treats 5-day-runup names
  specifically has never been measured.)

### Result 3 — the one modelable fill: a winner under today's rules, a loser under the rules in force

Only MXL 04-24 has minute bars (the other 7 winner ticker-days have zero — never alerted,
never captured; said plainly). Real bars, live mechanics: ORB 58.64/53.70, filled 09:32 at
58.64. Under the ORB-low stop in force that week it stopped **D1 for −1R** (04-27 low 50.40).
Under the operator-signed 2R stop (2026-08-16, half size) it survives, takes the +2R partial
on 05-01 and marks **≈+3.5R at 20 days**. The same lesson as #557's ALOY, with the sign
flipped: peak-ranked misses are not fills, and the stop rule decides whether even the real
winner converts. This is conversion (#562) territory, and it is why loosening admission alone
is not the fix.

### Result 4 — era and what the gate prevented

- Every ≥50% runner in the unique-kill set is April-May except SWMR (05-28). One regime
  supplied the whole recoverable prize (P8).
- Uniquely prevented: CAR −80%, SPCE −60%, XNDU −49%, SIDU −63% — and a **75% cap keeps three
  of those four out** (they sit at 72-92% extension... SIDU at 72% is admitted; the other
  three are not).
- The redundant 155 kills cost nothing to keep killing early — they save FMP/catalyst spend.

### Verdict — extension, plain words

**As configured the gate is 91% redundant with the quality filters; where it uniquely binds,
this sample says it killed 7 real ≥50% runners (3 doubler rows) against 4 bad losers in 4
months — and the good and bad halves live in different bands.** The 50-75 band is the good
slice (5 runners, 2 doublers, 1 loser); 75-100 is the dead zone holding the disasters. The priced
options:

| option | admits (4 mo) | winners recovered | losers admitted | extra HIGHs (est) |
|---|---|---|---|---|
| keep 50% | — | — | — | — |
| **→ 75%** | **8 uniquely-viable rows** (43 pre-filter) | **5 ≥50% runners, 2 doublers** | SIDU −63% | ~2 |
| → 100% | +5 more | +1 (POET +53% pk) | **CAR −80%, SPCE −60%** | ~3 |
| remove | +2 more | 0 new episodes | XNDU −49% | ~4 |

**75% is the only defensible move; 100% buys the disasters for one mediocre peak.** Smallest
first (P9), and the ruling is the operator's.

---

## Gate 2 — `outside_top20` (the gap-rank cap)

### Result 5 — this cohort is not toxic; the cap is a throughput limiter, not a judgement

789 rows, open basis, unconditional: median 5d close **+1.6%**, median 20d close **−0.4%**,
50% positive at 20 days, only 7% fall ≥30%. Compare the extension cohort's −44% median. The
cap binds on ~30 of 91 scan days — flood days (05-06: 106 rows, 04-14: 80, 07-30: 62) —
and **has not bound at all since 08-07, including the three sessions since the 9.0% floor
went live** (deepest rank 7-18). Its entire effect is concentrated on macro gap days.

### Result 6 — corrections to the "26 doublers" headline

1. **4 of the 26 were not killed by the cap.** Their min-rank cracked the top 20 during the
   day and the scan log names their real killer verbatim: QMCO 07-30 (`mcap_too_small $411M`),
   POET 05-06 (`atr_too_high 22.9%`), LFVN 05-26 (`adv_too_low $878k`), WOLF 05-05 scored and
   downgraded (`routine catalyst`). Cap-attributable: **22 rows**.
2. **Rank bands of the 22**: ranks 21-25: 5 · 26-30: 5 · 31-50: 8 · beyond 50: 4 (ASTS at 77,
   MRAM 04-14 at 99 — unreachable by any sane cap).
3. **Mechanical survival** (cooldown + extension + ADV + ATR + mcap) collapses the 10 rows in
   the 21-30 band to **3**: MXL (rank 21, +193% 20d close), MRAM 04-27 (rank 21, +127%), AGL
   (rank 26, +224%). The other 7 die on the stack they never reached — ERNA/JLHL/CUE dead two
   ways or more, OCC mcap $122M, VCX ATR 28%, POET-0508 ATR 23%, QBTX ATR **15.4% vs the 15.0
   line** (a 0.4-point miss — P2's band-vs-line point, filed for the ATR gate's own pricing).

### Result 7 — the exact bands a loosening would admit (full bands, no outcome conditioning)

Every rank-21-30 ticker-day replayed through the mechanical gates:

| band | ticker-days | survive mech. gates | of survivors: ≥50% peak | ≥100% | med 20d close | closed ≤−30% |
|---|---|---|---|---|---|---|
| ranks 21-25 | 157 | 112 | 12 (10.7%) | 2 | +1.9% | 0 |
| ranks 26-30 | 99 | 80 | 7 (8.8%) | 1 | +0.7% | 0 |
| **21-30 total** | **256** | **192 (75%)** | **19 (10%)** | **3 (1.6%)** | **+1.4%** | **0 of 129 settled** |

**The P5 comparison that decides it: the current HIGH pool itself (all 184 HIGH ticker-days,
same open basis) runs 6.5% ≥50% peak, 0.5% ≥100%, median 20d close −2.7%.** The band the cap
discards is as rich as or richer than the pool we keep, and contains zero −30% closes. The
cap is not protecting winner density — it is bounding scan/scoring load, nothing else.

### Result 8 — priced options, with the honest funnel applied

Survivors still face RVOL@T (unreplicable offline; measured population pass ≈77%, transfer to
thinner rank-21-30 names unknown — it fails open on missing baselines) and catalyst/score
(~24%): combined ≈18%.

| option | extra scored (4 mo) | extra HIGH alerts (est) | expected ≥50% runners alerted | expected doublers alerted | doublers recovered pre-funnel |
|---|---|---|---|---|---|
| keep 20 | — | — | — | — | — |
| **→ top-25** | 157 (~5/binding day) | **~21 (+11%)** | ~2.2 | ~0.4 | MXL, MRAM (both April) |
| → top-30 | 256 (~10/binding day) | ~35 (+19%) | ~3.5 | ~0.6 | + AGL (April) |
| → top-50 | 491 | ~65 | — | — | + 8 rows, all April-era |

- **All three mechanically-viable doublers are April 2026** (23 of 26 doubler rows pre-05-15;
  post-05-15 band survivors: 3 of 71 reached ≥50%, none doubled). The entire recoverable
  prize sits in one macro regime (P8). In the current regime the cap does nothing.
- **P4 cost**: +21-35 HIGHs per 4 months compete for the same 5 slots. Their estimated
  density (~1.6% doublers among survivors) is not worse than the current pool's 0.5% —
  loosening does not dilute — but slot-order risk (the MRNA/MRVL case) rises with volume.
- **Interaction with the 9.0% floor (live 08-19)**: the floor's +6-8 candidates/day are the
  SMALLEST gaps and rank last — on flood days the cap re-kills exactly the band the floor
  just recovered. The two levers partially cancel whenever the cap binds. Any future flood
  day repeats April's pattern unless the cap moves or ranks on something better than raw gap.

### Verdict — top-20 cap, plain words

**The cap is not earning its keep as a filter — it prevents nothing (zero −30% closes in the
admissible band, median ~0) and discards a slice at least as winner-dense as the pool we
keep — but everything it cost us sits in one April macro regime, and it costs nothing at all
in the current tape.** Smallest defensible move is **top-25** (~21 extra HIGHs/4 months,
recovers the rank-21 winners); top-30 roughly doubles the load for one more April winner
(AGL). A rank axis better than raw gap size (e.g. rank the 20 by RVOL or score the 30) is the
structurally better fix but is a criterion redesign, not a threshold move. Per the operator's
own 08-21 re-sequencing: conversion (#562) is priority 1, and P9 says admission loosenings
should wait for a downstream funnel that converts. The ruling is his.

---

## Cross-gate synthesis (P7)

- **The 55-doubler headline deflates to ~5 distinct recoverable winner names** once the four
  traps are applied: 4 rows mis-attributed, most die on the gates they never reached (91% of
  extension's blocked rows; 7 of the cap's 10 band-21-30 doubler rows), the
  survivors overlap heavily between the two gates (MXL, MRAM, POET recovered by EITHER
  loosening; FCEL only by extension→75; AGL only by top-30), and repeats collapse (POET ×5
  across both gates is one April episode).
- **Every recoverable winner is April-May except SWMR.** The two gates were expensive in
  exactly one regime — the same regime the gap-floor study flagged (10 of its 15 winners on
  04-08). A macro flood day is when these gates bite; we have not had one since early August.
- **Both loosenings are cheap in scoring load** (+8 and +21-35 catalyst-scored names per 4
  months against ~790 today) — the real cost is P4 slot competition, and the real bottleneck
  remains conversion: the one modelable recovered winner (MXL) was a −1R loser under the
  stop rules in force when it was skipped.

## ⚠ What this study does NOT answer

- **No R-per-trade for 7 of the 8 key winner ticker-days** — zero minute bars exist for
  never-alerted names (prod-checked). MXL 04-24 is the only modeled fill.
- **RVOL@T pass rates for rank-21-30 names are unmeasured** — the 77% figure is the top-20
  population's, and the gate fails open on missing baselines; bias sign unknown.
- **Catalyst/score behavior on extended names is unmeasured** — the 24% pass rate is the
  all-comers average; an LLM grader may treat a 5-day-runup name systematically differently.
- **Market caps are point-in-now, not point-in-time** (same limitation as the live gate
  itself); SIDU and SWMR sit within data-disagreement range of the $500M line.
- **One regime.** The recoverable winners are one April cluster; a fresh flood day is the
  out-of-sample test, and the 08-19 floor change makes the cap MORE likely to bind on it.

## Files

- This doc: `docs/analysis/gates_extension_top20_577_2026-08-22.md`
- Captures + computation: session scratchpad `577_*.{psv,sql,out,py}` (re-derivable from the
  embedded queries; all read-only)
- Method templates: `docs/analysis/adv_floor_556_2026-08-20.md`,
  `docs/analysis/cooldown_cost_557_2026-08-21.md`; gate ranking: PLAN.md #577 (2026-08-21)
