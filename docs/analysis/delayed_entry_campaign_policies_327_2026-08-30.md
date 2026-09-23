# #327 Stage 3 — Campaign policies on the missed real EPs: entry + stop + management + re-entry + abandon, measured per NAME (2026-08-30)

> 🗂 **DELAYED-ENTRY CONTEXT LEDGER — READ FIRST: `docs/setups/delayed_ep_reentry.md § THE CONTEXT LEDGER`.**

**⚖ THE LINE — MEASUREMENT ONLY.** Entry, stops, management, re-entry and abandon rules are
entry/exit discipline = the operator's sole authority. Nothing here is flipped, shipped, or
proposed as decided; the live exit rules are unchanged. $0 — every number computed offline from
the Stage-2 captures (no new prod reads, no LLM calls, no commits to live code).

## The decision this serves

The operator's rejection of Stage 2, verbatim: *"this analysis is incomplete, how do you
determine buy and stop? ... we need to find the real EPs and then figure out the entry/exit
tactics that can potentially keep us in them for a big run, including multiple re-entries.
Your analysis is just a lazy one try and done."* Stage 2 priced one entry per name with one
fixed management rule. This stage prices complete POLICIES — buy, stop, management, re-entry,
abandon — per NAME across the whole campaign, and reports what fraction of the available move
each policy actually banks. What would change the decision: if no policy shape materially beats
the single-try baseline, campaign design is not where the leak is; if one dimension dominates,
that is where the operator's design attention goes. Ranking order (operator, 2026-08-30):
**1) recall — how many real EPs the policy gets us into at all (P1); 2) expected return —
total R and R per event including every failed attempt; 3) capture ratio; 4) the tail — events
netting ≥4R (P3, THE GOAL).** Win rate appears only as a descriptive column.

## ⚠ The caveat that applies to EVERY number below

**The "real EP" label is OUTCOME-CONDITIONED** — every member is in the population because it
went on to a 5–10R+ tail, so every positive number is inflated by construction; real EPs that
FAILED are invisible. Each headline below must be read against the companion stopped-44 table
(real-EP-shaped names, ~93% tail-free — the closest available bleed proxy) and the break-even
blend in §7. Nothing in this document is a tradeable expectancy.

## Method — population, era, instrument

- **Population: the 55 missed-real-EP events** of `missed_ep_population_327_2026-08-29.md`
  (24 tier-1 ≥10R · 25 tier-2 5–10R · 6 tier-3 provisional), March–August 2026, mixed
  admission eras by construction (the miss defines membership). **Evaluable n=43**: 12 events
  are dark (zero minute bars — the April cap-kill class; coverage 64% and correlated, per
  Stage 2). **The per-event file `327s1_metrics.psv` holds 100 rows: 1 header + 44 stopped-44
  rows + 24 t1 + 25 t2 + 6 t3 = the 55 Stage 2 used.** The 44 stopped rows are the #562
  cohort, used here only as the bleed proxy (§7). ELPW's two events carry a **split-basis
  defect** — its daily rows (~$70–220) and minute rows (~$1–10) disagree on the same dates, so
  no pivot-referenced trigger can ever fire on it; they count as evaluable but no policy can
  enter them (flagged in the matrix).
- **Instrument: the Stage-2 harness unchanged** — the pinned port of
  `geometry_sweep_572.simulate` that reproduced #562's nine anchor trades and three full arms
  exactly (`delayed_entry_stage2_327_2026-08-30.md` §Method). The campaign layer WRAPS that
  single-position walker; no second replayer was written. (`scripts/probes/_bt_replay.py` was
  considered and not used: it is the DAY-1 ORB bracket harness — 1/3 partial, 40-session
  horizon, ORB-anchored stops — and rebasing Stage 3 on it would have broken byte-equality
  with the Stage-2 baseline this comparison is anchored to. One walker per lineage; the
  equality assertion below is the guard.) Signals on 5-min bars from `mi_intraday_bars`
  captures; entry = next 1-min open; window = following sessions +1..+25; each attempt holds
  ≤20 sessions; data edge 2026-08-28; positions open at the edge are OPEN MARKS, reported,
  never banked.
- **Equality assertion, run before any campaign number was read**: under the `live` management
  setting the parameterized walker reproduces every Stage-2 first-entry trade exactly — B-EPC
  below IS Stage 2's EPC-REC row (n=23, median +1.02, mean +2.26, sum +52.1), and likewise
  B-EPL/B-620/B-EPH. One boundary difference: a re-entry signal must be strictly AFTER the
  prior exit minute (Stage 2's flat-floor allowed the same minute); it affects one
  stopped-cohort episode (PLTR 08-04 EPH-BRK, −1R there) and nothing else.
- **Re-entry mechanics**: only a STOP exit (hard/breakeven/gap) permits a re-entry; a trail or
  time exit ends the campaign (it is a harvest, not a failure). Same-session re-entry is
  possible only when the stop-out itself was minute-resolved (attempt day 0); a stop-out on a
  daily-resolution day frees the name the next session — so the operator's TEAM-style same-day
  re-entry is only partly visible, stated as a limitation.
- **Capture ratio** — the number Stage 2 never reported: per event,
  **available = (max daily high over sessions +1..+25 − EP-day close) / ADR$** (one number per
  event, shared by all policies); **captured = campaign P&L per share / ADR$** (every attempt,
  including failures). Reported pooled over ALL evaluable events — a never-entered event
  captures 0, so recall is priced into it, and R-unit games (tiny stops inflating R) cannot
  flatter it.
- **Pre-registration.** The 13 policies below were fixed, with mechanisms, in the probe header
  before any campaign outcome was computed (`327s3_campaign.py`). Disclosed prior knowledge:
  the published Stage-2 single-entry tables (they are what the one-dimension-at-a-time
  variations start from). Every pre-registered policy is reported; §6's two post-hoc cells are
  labelled as such. NOT swept: giveback-of-peak management — the operator ruled out a
  peak-lock floor 2026-08-11 ("winners run"), and n=43 outcome-conditioned events is not the
  evidence to reopen a ruling with.

## The policies — buy and stop stated for every one (P11: no buy + no stop = not a policy)

Component vocabulary is #562's, verbatim, not redefined:

| component | definition |
|---|---|
| **EPC-REC** | arm on a 5-min close below the EP-day close; BUY the next 1-min open after the first 5-min close back above it; STOP = min low of the below-stretch; re-arms |
| **EPL-UR** | undercut of the EP-day low; BUY the next 1-min open after a 5-min close back above it within 2 sessions; STOP = min low since the undercut |
| **620@EPC** | BUY the next 1-min open after a qualified 620 turn (MACD 6/20/9, cross with MACD<0, basing ≤0.4×ADR$, hook) within 0.5×ADR$ of the EP close; STOP = low-of-day-so-far |
| **EPH-BRK** | resting BUY-STOP at the EP-day high; STOP = prior session's low |
| **M-live** | +2R partial (half) → breakeven → MAX(SMA10,SMA20) close trail → 20-session time stop — today's live shape |
| **M-none** | hard stop or the 20-session close. No partial, no breakeven, no trail |
| **M-trail** | no partial, no breakeven; hard stop stays live; exit on daily close below MAX(SMA10,SMA20); time stop |
| **M-noBE** | +2R partial (half); stop STAYS at the initial stop (never to breakeven); trail; time stop |

| id | entry | mgmt | re-entry / abandon | mechanism stated a priori |
|---|---|---|---|---|
| B-EPC | EPC-REC | M-live | none / 1 attempt | **the do-nothing baseline — Stage 2's exact shape** |
| B-EPL | EPL-UR | M-live | none / 1 | entry dim: the MNTS undercut blueprint |
| B-620 | 620@EPC | M-live | none / 1 | entry dim: #562's best arm |
| B-EPH | EPH-BRK | M-live | none / 1 | entry dim: breakout side — fires on 95% (Stage 2) |
| M1 | EPC-REC | M-none | none / 1 | mgmt dim: is management worth anything at all? |
| M2 | EPC-REC | M-trail | none / 1 | mgmt dim: does the +2R partial cost the tail (P3)? |
| M3 | EPC-REC | M-noBE | none / 1 | mgmt dim: the BE stop dies to re-tests (72/80 full stops sat in front of ≥4R) |
| R1 | EPC-REC | M-live | same trigger ×1 / 2 | re-entry dim: one more try, bounded cost |
| R2 | EPC-REC | M-live | same, unlimited / window | re-entry dim: the cost ceiling |
| R3 | EPC-REC | M-live | EPH-BRK ×1 / 2 | re-entry dim: get back in only on proof of strength |
| L1 | first of {EPC-REC, EPH-BRK} | M-live | EPH-BRK ×1 / 2 | composite: the fire-rate inversion — pullback arms never see the strongest names |
| L2 | as L1 | M-noBE | EPH-BRK ×1 / 2 | composite + the mgmt candidate |
| L3 | first of {EPC-REC, EPH-BRK} | M-live | same set, unlimited / window | composite cost ceiling |

## The numbers — campaign level, missed cohort (n=43 evaluable events)

Ranked columns in the operator's order: recall · expected return · capture · tail. `medR/ent`
and `meanR/ent` are per ENTERED event; `meanR/ev` spreads total R over all 43 (a no-entry = 0).
`cap%` = pooled captured/available (ADR frame, all 43); win% is descriptive only.

| policy | recall | attempts | re-entries | tot R | meanR/ev | medR/ent | meanR/ent | cap% | ≥4R | ≥2R | open | win% |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B-EPC | 23/43 | 23 | 0 | +52.1 | +1.21 | +1.02 | +2.26 | 8.1 | 5 | 10 | 0 | 57 |
| B-EPL | 13/43 | 13 | 0 | +75.3 | +1.75 | −1.00 | +5.79 | 3.4 | 4 | 4 | 0 | 38 |
| B-620 | 18/43 | 18 | 0 | +25.1 | +0.58 | −1.00 | +1.40 | 0.8 | 3 | 3 | 0 | 39 |
| B-EPH | 41/43 | 41 | 0 | +29.5 | +0.69 | +0.26 | +0.72 | 13.0 | 1 | 10 | 1 | 56 |
| **M1** | 23/43 | 23 | 0 | **+162.3** | **+3.77** | −0.09 | +7.06 | **20.6** | **10** | 11 | 2 | 48 |
| M2 | 23/43 | 23 | 0 | +90.0 | +2.09 | +1.92 | +3.91 | 12.0 | 7 | 11 | 0 | 57 |
| M3 | 23/43 | 23 | 0 | +53.4 | +1.24 | +1.96 | +2.32 | 8.2 | 5 | 11 | 0 | 57 |
| R1 | 23/43 | 31 | 8 | +56.2 | +1.31 | +1.96 | +2.44 | 10.4 | 5 | 11 | 0 | 70 |
| R2 | 23/43 | 33 | 10 | +52.7 | +1.22 | +1.96 | +2.29 | 10.1 | 5 | 11 | 0 | 65 |
| R3 | 23/43 | 33 | 10 | +65.0 | +1.51 | +2.09 | +2.83 | 12.4 | 5 | 14 | 0 | 74 |
| L1 | **41/43** | 53 | 12 | +64.6 | +1.50 | +1.28 | +1.58 | 16.8 | 3 | 16 | 1 | 66 |
| L2 | **41/43** | 51 | 10 | +66.7 | +1.55 | +1.28 | +1.63 | 16.9 | 3 | 16 | 1 | 68 |
| L3 | **41/43** | 61 | 20 | +65.4 | +1.52 | +1.28 | +1.60 | 19.3 | 3 | 16 | 1 | 68 |

### Finding 1 — RECALL splits the board in two, and the split is structural

Every pullback-entry policy enters **23/43 (53%)** at best; every policy carrying EPH-BRK
enters **41/43 (95%)**. **Eighteen events — the entire evaluable 04-08 cap-kill cluster plus
AEHR, OKLO, MSTR, BAND, VPG, NOK-class names — are reachable ONLY through the breakout side**
(see the matrix): they never pulled back to any pivot. This is `pivot_proximity_2026-08-16.txt`
measured a third time, now at campaign level: the strongest names never come back, so a
pullback-only campaign fails P1's test on ~40% of real EPs before management even matters.
The two events no policy enters are the ELPW basis defect, not a tactic gap.

### Finding 2 — MANAGEMENT is the dominant dimension: the live harvest gives back two-thirds of what the entry finds

Same entry (EPC-REC), same 23 fills, only management varied:
**M-none +162.3 R > M-trail +90.0 > M-noBE +53.4 ≈ M-live +52.1 (the live shape).**
Decomposed: adding the SMA trail to a pure hold costs **−72.3R** (M1→M2); adding the +2R
partial costs **−36.6R** (M2→M3); the breakeven move itself costs ~−1.3R here (M3→B-EPC).
Per name: FTNT +24.7 (hold) vs +13.3 (live); STX +53.6 vs +12.0; UMC 04-17 +43.8 vs −0.0 —
the live trail exited UMC on a day-2 dip for zero and the run went on without it. All three
verified against raw bars: the initial stop was never touched post-entry. **On tail-labelled
names, every early-derisk layer sells the tail** — P3's arithmetic, measured. The capture
column says the same thing without R-unit flattery: 20.6% vs 8.1%.
⚠ Two caveats, stated with the finding: (a) this is the outcome-conditioned population —
M-none is exactly the policy most flattered by a tails-only label (§7 is mandatory context);
(b) `#270`'s Layer-3 found the OPPOSITE on its trigger cohort (buy-and-hold lost the median);
the sign of the management question flips with the population (P8) — which is precisely why
"find the real EPs" (§8) is the binding problem, not the exit rule.

### Finding 3 — RE-ENTRY is real but small, and its cost is bounded, not assumed

The operator asked what failed attempts subtract. Measured across the whole cohort:

| policy | re-entries | R won on them | R lost on them | net |
|---|---|---|---|---|
| R1 (same ×1) | 8 | +8.1 | −4.0 | +4.2 |
| R2 (same, unlimited) | 10 | +8.1 | −7.5 | +0.6 |
| R3 (EPH-BRK on strength ×1) | 10 | +15.4 | −2.5 | **+12.9** |
| L1 | 12 | +12.8 | −4.3 | +8.4 |
| L3 (unlimited) | 20 | +19.5 | −10.3 | +9.2 |

**The best re-entry rule is the strength-proof one** (after a stop-out, get back in only when
the name takes out the EP-day high): it recovered QCOM (−1R first try → +3.5 net), FCEL
(−1 → +2.1), BRKR (−1 → +2.0) at a total failed-attempt cost of −2.5R. **Unlimited re-entry
roughly doubles the cost for no added win** (R2 vs R1) — one re-try, or one on strength, is
where the value is; the abandon rule after 2 attempts loses nothing measurable. Re-entry does
NOT rescue recall: it re-enters names the pullback already found, it does not find new ones.

### Finding 4 — the tail (THE GOAL's own metric)

Events netting **≥4R: M1 10 · M2 7 · B-EPC/M3/R1/R2/R3 5 · L-family 3 · B-EPH 1** — of a
union ceiling of 12 (Stage 2). THE GOAL needs ~4 tail winners in 4½ months; M1 banks 10 over
this ~5-month (outcome-conditioned) population. The L-family's recall does not convert to
tails because EPH-BRK's wide stop (median 13%) turns tails into +1–3R wins AND, firing first,
it PREEMPTS the tighter EPC-REC entry on names that would have pulled back. B-EPH alone: 41
entries, one 4R+. **Recall and tail conversion live on opposite sides of the ladder** — that
is the design tension the pre-registered set exposes, and §6 prices the obvious resolution.

## Robustness — how much is three names?

Total R with the top-k events removed, per policy (top-3 named):

| policy | tot R | ex-top1 | ex-top2 | ex-top3 | top 3 |
|---|---|---|---|---|---|
| M1 | +162.3 | +108.7 | +65.0 | +40.3 | STX +53.6, UMC +43.8, FTNT +24.7 |
| M2 | +90.0 | +65.3 | +43.2 | +26.4 | FTNT, STX, MRAM |
| B-EPC | +52.1 | +38.7 | +26.7 | +17.3 | FTNT, STX, MRAM |
| B-EPL | +75.3 | +24.0 | +12.7 | +1.9 | ALMU +51.3, VSH, UMC |
| L2 | +66.7 | +53.3 | +41.3 | +36.1 | FTNT, STX, SNOW |
| L3 | +65.4 | +52.1 | +40.1 | +34.9 | FTNT, STX, SNOW |

**75% of M1's total is its top three names.** That is not a defect to explain away — a
tail-hunting policy SHOULD be carried by its tail (P3), and ex-top-3 M1 (+40.3) still leads
every other policy's ex-top-3 — but it means the margin rests on 3 trades and n=23 entries.
B-EPL collapses ex-top-3 (+1.9): the undercut arm is one name (ALMU, a $14M micro-cap the
live mcap floor refuses) wearing a policy costume. The L-family degrades most gracefully
(breadth), M1 degrades steepest (concentration): **tail total vs graceful degradation is a
real fork, and it is the operator's.**

## §6 Post-hoc cells — labelled, maximal fitting risk

The board above begs one combination the pre-registered set deliberately did not contain
(ladder recall × no-management capture). Priced AFTER seeing the results — treat as a
hypothesis for the next population, never as a finding of this one:

| policy (POST-HOC) | recall | tot R | meanR/ev | cap% | ≥4R | ex-top3 |
|---|---|---|---|---|---|---|
| PH-LN0: first of {EPC-REC, EPH-BRK} · M-none · no re-entry | 41/43 | +142.4 | +3.31 | 31.7 | 11 | +55.8 |
| PH-LN1: + one EPH-BRK re-entry | 41/43 | +156.7 | +3.64 | 35.3 | 13 | +69.9 |
| PH-EPHN: EPH-BRK · M-none | 41/43 | +63.1 | +1.47 | 29.7 | 8 | +41.5 |

Tier-1 only (the ≥10R class, n=17): PH-LN0 enters 17/17 with 5 events ≥4R vs the pullback-only
M1's 7/17 and 4. The post-hoc composite is the only shape that is top-2 on all four ranked
metrics at once — which is exactly what a fitted champion would also look like; it earns a
pre-registered re-test on the next cohort (tier-3 settles ~mid-October), nothing more.

## §7 The bleed side — the same policies on the stopped-44, and the break-even blend

Same instrument, same policies, the 44 real-EP-shaped stopped episodes (~93% tail-free):

| policy | recall | tot R | meanR/ev | med R/ent | ≥4R | break-even real-EP rate p* |
|---|---|---|---|---|---|---|
| B-EPC | 36/44 | −0.7 | −0.02 | −0.66 | 2 | 1.3% |
| B-EPH | 27/44 | +0.1 | 0.00 | −1.00 | 0 | ~0% |
| M1 | 36/44 | **+11.8** | **+0.27** | −1.00 | 3 | positive at p=0 |
| M2 | 36/44 | +2.1 | +0.05 | −0.92 | 2 | positive at p=0 |
| R3 | 36/44 | −7.6 | −0.17 | −0.56 | 2 | 10.3% |
| L1 | 37/44 | −14.7 | −0.33 | −0.81 | 0 | 18.2% |
| L3 | 37/44 | −14.0 | −0.32 | −0.48 | 0 | 17.3% |
| PH-LN1 (post-hoc) | 37/44 | −13.5 | −0.31 | −1.00 | 2 | 7.9% |

*p\* solves p×(missed meanR/ev) + (1−p)×(stopped meanR/ev) = 0 — the fraction of a live
watch-lane's fires that must be genuine tails for the policy to break even, under the
strong assumption that the stopped-44 is the right bleed model.*

Two things worth the operator's attention: **M-none is the only management arm positive on
BOTH cohorts** — on the stopped names it let the three real winners (INTC/SMCI/NRIX) pay for
the −1R crowd, which is THE GOAL's arithmetic working even in a ~93% tail-free population —
and **the L-family (and the post-hoc champion) need roughly 8–18% of their fires to be real
tails** to carry their wider-stop bleed. ⚠ The stopped-44 is a generous bleed proxy: those
names passed full admission and were alerted; a raw watch-lane population would bleed worse
(§8 sizes it).

## §8 "Find the real EPs" — is a non-outcome-conditioned population reachable?

- **Reconciliation first**: `327s1_metrics.psv` = 100 rows = header + 44 stopped + 55 missed
  (24 t1 + 25 t2 + 6 t3). Stage 2 and this stage use the 55; the 44 are the bleed proxy.
- **In-sample, an ex-ante direction exists but is not a definition**: gap 8–12% holds 21/24
  tier-1 vs 7/44 stopped (adding $vol ≤ $900M: 11/24 vs 3/44) — but only 11/25 of tier-2.
  Computed on the same 99 events the question is about; it cannot be promoted from here.
- **Reachable: YES, forward; NO, backward past mid-April.** The defensible non-conditioned
  definition is the ex-ante screen itself: open gap ≥8%, prior close ≥$5–10, day-0 $vol
  ≥$50M, extension ≤50%, catalyst grade ≥ strong — every term computable at the open from
  stored data (`mi_daily_closes`; catalyst from `mi_ep_scan_log`, which exists only from
  04-13, alerts from 05-11 — the pre-April catalyst axis is unknowable forever, and the
  operator's structure axis is not yet computable at scale, #519). Stage 1 measured the raw
  screen at **265 qualifying gap-days over 07-16..08-10 (~15/session), of which 6 (2.3%)
  reached the provisional tail label.** That 2.3% is the honest base-rate anchor for §7's p\*:
  an UNSELECTED watch-lane sits far below every composite's break-even (~8–18%) and roughly
  at the pullback baselines' (~1–3%); **the selection layer between the raw screen and the
  fire is where the whole live viability of this lane lives** — which is P13's unpriced
  question, not a campaign-design question. **The concrete fix this stage proposes (evidence
  only): persist the ex-ante screen membership daily from now on.** Outcomes then accrue
  UN-conditioned within ~25 sessions, and every future stage prices winners AND failures on
  the same footing. Until that exists, every delayed-entry number — including all of the
  above — carries the conditioning inflation.

## The per-event matrix — every event × every policy (net campaign R; `.` = never entered, `*` = open mark)

```
event            avADR  B-EPC  B-EPL  B-620  B-EPH    M1     M2     M3     R1     R2     R3     L1     L2     L3
AEHR 03-31 t1    15.5     .      .      .    -0.1     .      .      .      .      .      .    -0.1   -0.1   -0.1
MU   04-08 t1    16.8     .      .      .    -1.0     .      .      .      .      .      .    -1.0   -1.0   -1.0
STRL 04-08 t1    18.8     .      .      .    +0.2     .      .      .      .      .      .    +0.2   +0.2   +0.2
NBIS 04-08 t1    10.6     .      .      .    -0.4     .      .      .      .      .      .    -0.4   -0.4   -0.4
BE   04-08 t1    11.9     .      .      .    +1.7     .      .      .      .      .      .    +1.7   +1.7   +1.7
USAR 04-08 t1     8.9     .      .      .    +1.1     .      .      .      .      .      .    +1.1   +1.1   +1.1
QBTS 04-08 t1    10.7     .      .      .    -0.0     .      .      .      .      .      .    -0.0   -0.0   -0.0
HUT  04-08 t1    11.5     .      .      .    -0.2     .      .      .      .      .      .    -0.2   -0.2   -0.2
IREN 04-08 t1    11.0     .      .      .    -1.1     .      .      .      .      .      .    -1.9   -1.9   -1.9
APLD 04-08 t1     9.4     .      .      .    -1.0     .      .      .      .      .      .    +0.0   +2.8   +1.7
UMC  04-17 t1    23.5   -0.0     .      .    -0.8   +43.8   -0.0   -0.0   -0.0   -0.0   -0.0   -0.8   -0.8   -0.8
QCOM 04-24 t1    31.3   -1.0     .    -1.9   +2.7    -1.0   -1.0   -1.0   -3.0   -3.0   +3.5   +2.7   +2.7   +2.7
AMD  04-24 t1    11.8   +2.0   -1.0   +9.8   +2.0    +4.4   +1.9   +2.0   +2.0   +2.0   +2.0   +2.0   +2.0   +2.0
UMC  05-06 t1    17.3   -1.0  +10.8   -1.0   -1.2    -1.0   -1.0   -1.0   -2.0   -5.2   -2.2   -2.2   -2.2   -2.1
ARM  05-06 t1    13.6   +2.3   -1.0     .    +2.6    +5.0   +2.6   +2.3   +2.3   +2.3   +2.3   +2.6   +2.6   +2.6
SNOW 05-07 t1    15.0   +5.2   +8.5   -1.0   +5.1    +8.4   +8.4   +5.2   +5.2   +5.2   +5.2   +5.2   +5.2   +5.2
QURE 05-29 t1     9.2   -1.0   -1.0   +1.0   -0.9    -1.0   -1.0   -1.0   -1.9   -1.9   -1.9   -1.9   -1.9   -1.9
OKLO 04-08 t2     9.0     .      .      .    +1.3     .      .      .      .      .      .    +1.3   +1.3   +1.3
MSTR 04-08 t2    10.8     .      .      .    -1.0     .      .      .      .      .      .    -2.0   -2.0   -5.0
ALMU 04-13 t2    12.7   +4.5  +51.3     .    -1.0    +7.0   +7.0   +4.5   +4.5   +4.5   +4.5   +2.8   +2.8   +3.5
ELPW 04-22 t2    22.1     .⚠     .      .      .      .      .      .      .      .      .      .      .      .
NOK  04-23 t2    14.2     .      .   +12.8   +2.8     .      .      .      .      .      .    +2.8   +2.8   +2.8
MXL  04-24 t2    11.3   +2.2   -1.0     .    +1.9    +3.3   +2.4   +2.2   +2.2   +2.2   +2.2   +2.2   +2.2   +2.2
ELPW 04-24 t2    11.7     .⚠     .      .      .      .      .      .      .      .      .      .      .      .
FCEL 04-29 t2    11.3   -1.0     .    -1.0   -1.0    -1.0   -1.0   -1.0   +2.0   +2.0   +2.1   +2.1   +2.1   +2.1
STX  04-29 t2    10.2  +12.0     .   +12.0   +1.4   +53.6  +22.1  +12.0  +12.0  +12.0  +12.0  +12.0  +12.0  +12.0
MRAM 04-30 t2    30.0   +9.4     .      .    +2.9   +12.9  +16.8   +9.4   +9.4   +9.4   +9.4   +2.9   +2.9   +2.9
BAND 04-30 t2    16.8     .      .      .    +2.4     .      .      .      .      .      .    +2.4   +2.4   +2.4
OUST 05-04 t2    10.8   -1.0   -1.0   -1.0   -1.0    -1.0   -1.0   -1.0   -0.7   -0.7   -1.1   -1.2   -1.2   -0.7
BRKR 05-06 t2    11.7   -1.0     .    -1.0   -0.2    -1.0   -1.0   -1.0   -1.0   -1.0   +2.0   -0.2   -0.2   -0.2
FTNT 05-07 t2    11.9  +13.3     .      .    +2.9   +24.7  +24.7  +13.3  +13.3  +13.3  +13.3  +13.3  +13.3  +13.3
VPG  05-12 t2    14.4     .      .      .    +2.0     .      .      .      .      .      .    +2.0   +2.0   +2.0
VSH  05-13 t2    16.8   +3.0  +11.3     .    +2.3    +6.6   +4.0   +3.0   +3.0   +3.0   +3.0   +3.0   +3.0   +3.0
UMC  05-26 t2     8.7   -1.6   -1.0   -1.7   -1.1    -1.6   -1.6   -1.6   +0.5   +0.5   +1.3   +1.8   +1.8   +1.0
HPE  05-29 t2    12.6   +2.1     .    -1.0   +3.2    -1.0   +2.3   +2.1   +2.1   +2.1   +2.1   +3.2   +3.2   +3.2
SDOT 06-08 t2    19.1   -1.0   -1.0   +0.0   -1.0    -1.0   -1.0   -1.0   +0.0   -0.3   -0.0   -0.0   -0.1   -0.1
SDOT 06-17 t2    11.4   +1.0   -0.7   -1.1   +1.0    -0.1   +0.2   +1.1   +2.8   +2.8   +2.0   +2.0   +1.1   +3.8
IQV  07-23 t3     9.1     .      .    -1.0   +0.1     .      .      .      .      .      .    +0.1   +0.1   +0.1
DFNS 07-27 t3    23.3   -0.7     .    +1.0   +1.6    -0.6*  -0.7   -0.7   -0.7   -0.7   -0.7   +1.6   +1.6   +1.6
DFNS 07-28 t3     9.6   +1.0     .    -1.0   +1.1    -1.6   +2.4   +2.2   +1.0   +1.0   +0.8   +0.9   +1.1   +0.9
AXTI 07-30 t3     8.4     .      .      .    +0.3     .      .      .      .      .      .    +0.3   +0.3   +0.3
GFI  08-05 t3    10.7     .      .      .    +1.1*     .      .      .      .      .      .    +1.1*  +1.1*  +1.1*
AU   08-07 t3     8.1   +3.3   +1.1   +1.1   -1.0    +4.6*  +4.6   +3.3   +3.3   +3.3   +3.3   +3.3   +3.3   +3.3
```
(⚠ = the ELPW split-basis data defect; n=43 rows. The 18 EPH-only rows at the top ARE
Finding 1. Open marks: GFI/AU/DFNS tier-3 events at the 08-28 edge — 1–2 per policy,
reported in the table's `open` column, never banked.)

## Adversarial answers, as briefed

- **How much of the winner's margin is fitting?** The pre-registered winner (M1) varies ONE
  component from the live shape with an a-priori mechanism; its margin survives top-3 removal
  (+40.3, still first). But its top-3 carry 75% of the sum, its median entered event is
  −0.09R, and its flattery-by-construction is maximal on a tails-only label. The post-hoc
  composite (§6) is where fitting risk peaks and is labelled accordingly. With 13
  pre-registered policies on n=43, ~2 policies could look this good by luck; the management
  ordering (none > trail > partial) is monotone across four independent cells, which is the
  strongest internal evidence here.
- **Tail or many small wins?** M1 wins on the tail (10×≥4R, negative median) — THE GOAL's
  shape. The L/R families win on breadth (win% 65–74) and are the WORSE finding by the
  operator's own arithmetic, stated as such.
- **Followable in real time?** Every trigger and stop is computable from live bars with no
  hindsight (EPC-REC needs 5-min closes + the below-stretch low; EPH-BRK is a resting order).
  M-none requires only inaction. Caveats: modeled minute-open fills carry the engine's
  measured +0.41R/attempt optimism (attempts/event 1.0–1.5, so up to ~0.6R/event of the
  means); ALMU/ELPW/DFNS/SDOT sit below live floors (mcap/$5) — their R exists only in the
  operator's WATCH lane; and the 20-session time exit, while ex-ante, was inherited from the
  Stage-2 engine, not chosen for this cohort.

## What this does not answer

- **A tradeable expectancy.** The label is outcome-conditioned; §7's blend is arithmetic on a
  generous proxy, not a forecast. No ex-ante feature yet separates a real-EP fire from a
  bleed fire at trigger time (P13, open).
- **The dark 12** (no minute bars — 7 of tier-1's 24). Backfilling their windows is the
  standing $0 sibling task; the recall finding would likely STRENGTHEN (they are the
  April cap-kill class that never pulled back), but that is untested.
- **Whether M-none's dominance survives a non-conditioned population** — the #270 cohort
  answered the same question the other way; §8's screen persistence is what settles it.
- **Position sizing, slot competition, portfolio interaction** (P4): campaigns priced
  independently; a live book with 5 slots and ~15 screen names/day is a different problem.
- **Same-day re-entry in full** (the operator's TEAM move): only visible when the stop-out
  was minute-resolved; daily-resolution stop-outs free the name next session.
- **Tier-3 labels** (~mid-October) and TEAM's settle (09-08) — pre-registered re-cuts stand.
- **The 620 arms beyond @EPC** and behaviour-based "near" (the 08-29 ruling) — deliberately
  out of scope; #562 definitions were reused verbatim so results transfer.

## Files

- This doc: `docs/analysis/delayed_entry_campaign_policies_327_2026-08-30.md`
- Probe (pre-registration in header): `~/.claude/jobs/6b173ac9/tmp/327s3_campaign.py`;
  verification + post-hoc: `327s3_verify.py`; outputs `327s3_out.txt`,
  `327s3_verify_out.txt`; per-attempt rows `327s3_attempts.psv`
- Inputs (captured once by Stage 2, reused): `327s2_min_out.psv`, `327s2_daily_all.psv`,
  `327s2_episodes.json`; population `327s1_metrics.psv`
- Companions: `delayed_entry_stage2_327_2026-08-30.md` (the single-entry stage this extends) ·
  `delayed_entry_562_2026-08-22.md` (trigger definitions) ·
  `missed_ep_population_327_2026-08-29.md` (the population and its defect)
