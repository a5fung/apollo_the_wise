# Can the structure axis tell a real EP from what we threw away? — replay, 2026-08-25

**MEASUREMENT ONLY. Nothing was changed.** No rule, threshold, filter, toggle, cutline or trade
state was touched, and nothing here is a recommendation — every change this implies is the
operator's fork (THE LINE). No number below was fitted: every comparison direction was written down
before it was computed, and no cutline was chosen or tuned.

---

## The answer in one line

**No — the structure axis does not separate real EPs from the rejects. It emits the identical
verdict (zero credit) for 52 of the 53 name-days, and the single name it would have boosted is one
we rejected, not one of the 26 labelled real EPs. Not one axis output separates the two groups once
the sensitivity checks are run.**

## The three answers asked for

| question | answer |
|---|---|
| Does it separate? | **No.** It gives zero credit to 52 of 53 name-days, so its own output carries almost no information at all — as an AUC that is 0.481, against 0.50 for a coin, the selection score's 0.63-0.70 and its earlier version's 0.37-0.41. Its Stage-2 ingredient carries a weak signal on its own; its tightness ingredient turns out to be an artifact (§4). |
| What does it say about CAPR? | **`no_stage2`, zero credit — the identical verdict it gives MRNA, the operator's own textbook EP.** And it does not reproduce his read at all: there is no congestion, level, pivot or gap-zone concept anywhere in the module. |
| Can it be called at admission time? | **Yes.** Both functions are pure over daily bars strictly prior to the date; no alert context is needed. The real limit is that it needs 200 prior sessions, so it returns "unknown" for any name younger than ~10 months — 7 of the 27 rejects, and 1 of the 26 real EPs. |

---

## 1. The replay is the live mechanism, proven — 116 of 116 rows reproduced exactly

`compute_structure_features` and `structure_axis_credit` are **imported** from
`agents/market_intelligence/structure_axis_shadow.py`, not re-implemented. The only thing rebuilt
is the bar accessor (`db.get_daily_bars_asof` needs a live database connection), so its SQL
predicate was mirrored against a one-shot capture and then **verified**: the harness was run over
the 116 rows the live path has already written to `mi_structure_axis_shadow` and reproduced
**every one of ten fields on all 116 rows, exactly** — `prior_close`, `stage2`, `sma_200`,
`trailing_high`, `rmv_15`, `rmv_tight`, `extension_ratio`, `sma_10`, `credit_steps`, `marker`.

This is a replay of the live component, not a lookalike.

## 2. The two populations

| | what it is | name-days | market days |
|---|---|---|---|
| **Real EPs** | `tests/fixtures/must_not_miss_eps.py`, the operator/evidence-labelled set (TDIC dropped, it is flagged excluded in the fixture itself) | 26 | 10 |
| **Rejects** | every name that cleared the $5 / 50,000-share universe floors on the two silent days and was then killed by a real gate — re-derived from `mi_ep_scan_log`, not from prose | 27 | 2 |

Re-derivation matches the prose exactly: 9 on 08-24, 18 on 08-25.

⚠ **These are not 26 versus 27 independent observations.** Thirteen of the 26 real EPs — half the
arm — are the same market day, 2026-04-08. The whole reject arm is two consecutive days. Every
number in this document should be read as ten days against two.

## 3. A data-retention trap that had to be worked around first

`mi_daily_closes` is purged at 400 calendar days (`db.purge_old_data`). Most of the labelled real
EPs are April-May 2026 dates, now near that edge, so replaying them **today** leaves only ~180
prior sessions — under the 200 the 200-day average needs — and the axis returned "unknown" for
**21 of the 26**, while the rejects (yesterday and today) mostly computed fine.

That is an artifact of replaying old dates, not of the axis: in April those names had ~260
sessions available and would have computed. Left uncorrected it would have made the comparison
meaningless, so the history was re-pulled for both arms from Polygon — the same adjusted source
`mi_daily_closes` is built from — through the production container, read-only, no database write,
zero marginal cost. **46 of the 50 tickers agree with production to within 1% on every overlapping
close; the 4 that differ are split-adjustment differences on reject names and not one of them
changes its verdict.** Coverage went from 5/26 to 25/26 on the EP side and did not move on the
reject side.

**Both readings are reported below.** The restored-history one is the fair comparison.

## 4. Does it separate? The numbers

Direction for every field was fixed in advance from `docs/methodology/structure_model.md` §4c and
the axis's own stated semantics — less extended is better, tighter base is better, closer to the
trailing high is better, Stage-2 present is better, more credit is better. AUC is the chance a
randomly picked real EP scores better than a randomly picked reject; 0.50 is a coin flip. Ties
count half. Confidence intervals are 95%.

| what is measured | AUC | 95% confidence | real EP median | reject median | reading |
|---|---|---|---|---|---|
| **the axis's own verdict** (`credit_steps`) | **0.481** | 0.325 – 0.638 | 0 | 0 | **nothing** |
| base tightness (RMV-15, continuous) | 0.692 | 0.549 – 0.835 | 48.6 | 74.9 | **an artifact — see below** |
| Stage-2 long-term trend | 0.675 | 0.518 – 0.832 | yes | no | suggestive, does not survive |
| distance below the trailing high | 0.662 | 0.515 – 0.809 | 0.78 | 0.59 | suggestive, does not survive |
| extension above the 10-day | 0.390 | 0.238 – 0.542 | 1.010 | 0.959 | runs backwards, not significant |

With five comparisons, only base tightness survives a multiple-comparison correction (Holm at 5%;
raw p = 0.008). Stage-2 (p = 0.029) and trailing-high distance (p = 0.030) do not. At this sample
size a confidence interval is roughly ±0.15 wide, so **0.63 and 0.37 are both indistinguishable
from a coin flip here** — this is indicative, not a verdict.

### 🔴 And the one survivor does not survive its own sensitivity checks

**RMV-15 is clamped to a 0-100 range, and 9 of the 27 rejects sit exactly on the 100 ceiling while
no real EP goes above 89.7.** Those nine therefore lose to all 26 real EPs automatically — 234 of
the 702 pairwise comparisons the number is built from, roughly half its entire winning margin.

- **Drop the nine ceiling-pinned rejects and the separation collapses: AUC 0.538 (0.364 – 0.712),
  raw p = 0.67.** Nothing.
- **Drop the 13 real EPs that all share 2026-04-08 and the confidence interval crosses a coin
  flip: AUC 0.672 (0.486 – 0.859).**

So the field is not measuring a tightness *gradient* between the groups. It is flagging "this
name's recent range is erratic", which nine thin rejects trip and no real EP does. **After the
sensitivity checks, no axis output separates these two populations.** Stage-2 at 0.675 is the last
one standing and it already failed the multiplicity correction.

### Why the axis scores nothing while two of its ingredients score something

The credit rule is an AND: Stage-2 **and** a tight base, where "tight" is RMV-15 at or below 30
(`ENTRY_RMV_MAX`, inherited from the consolidation-entry gate).

- With history restored, **15 of 25 real EPs are Stage-2** — against 5 of 20 rejects. The trend
  half works.
- But **only 2 of the 26 real EPs have a base tight enough to pass** (QURE at 16.8, MRNA at 24.0)
  — and neither of those two is Stage-2, so they fail the other half. **All 15 Stage-2 real EPs
  land in the uncredited "near-miss" bucket.** The two halves never coincide on a single real EP.
- Result: **the axis credits 0 of 26 real EPs and 1 of 27 rejects.** The single credited name in
  the entire study is **OESX** — the 08-25 name that missed the dollar-volume floor by $727.

So the tightness measure points the right way as a *gradient* (real EPs are meaningfully tighter
than rejects, 48.6 against 74.9) while sitting entirely on one side of the cutline the axis
actually uses. **That is a statement of fact about where the two populations fall, not a proposal
to move anything** — the cutline is the operator's.

### What the axis actually said, both readings

| | as production data stands today | with history restored |
|---|---|---|
| real EPs | 21 unknown · 3 no-Stage-2 · 2 near-miss · **0 credited** | 1 unknown · 10 no-Stage-2 · 15 near-miss · **0 credited** |
| rejects | 7 unknown · 15 no-Stage-2 · 4 near-miss · 1 credited | 7 unknown · 15 no-Stage-2 · 4 near-miss · **1 credited (OESX)** |

## 5. CAPR — the worked example

**The axis says `no_stage2`, credit 0, on both 08-24 and 08-25. It gives MRNA on its own EP day the
exact same verdict.** It cannot tell them apart.

| | prior close | 200-day average | trailing high | Stage-2 | RMV-15 | extension | verdict |
|---|---|---|---|---|---|---|---|
| CAPR 08-24 | 6.29 | 23.20 | 40.37 | no | 54.2 | 1.076 | `no_stage2`, 0 |
| CAPR 08-25 | 6.80 | 23.20 | 40.37 | no | 76.3 | 1.107 | `no_stage2`, 0 |
| MRNA 08-19 | 62.96 | 46.86 | 85.60 | no | 24.0 | 1.036 | `no_stage2`, 0 |
| SNOW 05-07 | 139.74 | 206.02 | 280.67 | no | 51.6 | 0.986 | `no_stage2`, 0 |
| QURE 05-29 | 24.85 | 26.45 | 71.50 | no | 16.8 | 0.982 | `no_stage2`, 0 |

⚠ The two names arrive at the same label from opposite places. CAPR trades at **under 30% of its 200-day
average and 17% of its trailing high**. MRNA is **above** its 200-day average and fails only the
other half of the same test — 73.6% of its trailing high against a 75% requirement, short by 1.4
points. One label, two completely different charts.

### It does not reproduce his read, and it structurally cannot

His call was about **overhead supply**: *"the gap up just barely made up for the most recent drop
but just at where there's a huge gap down from July 27."* The bars show exactly what he means —
CAPR closed 19.70 on 24 July and opened **5.87** on 27 July on 30 million shares, a ~70% gap down
that has never been filled; it then based near $4, gapped to 7.66 on 14 August, and on 24-25 August
was gapping back into that same $6-8 shelf with $18-20 of untouched supply above it.

The module imports exactly four things: a simple moving average, the volatility-contraction
measure, the tightness cutline, and the bar accessor. **There is no level derivation, no pivot
merging, no gap-zone detection, no congestion concept in it at all.** It measures long-term trend
position, base tightness, and distance above the 10-day average. It happens to be negative on CAPR
— but the same label lands on MRNA, SNOW and QURE, three labelled real EPs, and in MRNA's case for
a reason (1.4 points short of the trailing-high requirement) that has nothing to do with the supply
overhead he is describing.

**So the premise that this component would have caught his read is wrong.** The component that
encodes supply zones is `scripts/probes/_533_nbis_structure_encoder.py` (`structure_model.md` §3),
which is shadow-only and wired into nothing. Testing that against CAPR is the natural follow-up and
is deliberately not done here: three of its thresholds were calibrated on the eight operator-labelled
fixtures, so running it on new names needs its own design, and its hold leg needs minute bars that
an unalerted name does not have.

## 6. Can it be called at admission time?

**Yes — and there is direct evidence, not just an argument from code.** All 116 existing shadow
rows were written **during the live morning scan** (07:00 to 09:56 ET) and **all 116 carry a
non-null prior close**, so the accessor demonstrably returns a usable bar history at exactly the
moment an admission decision is made. On top of that, `compute_structure_features` and
`structure_axis_credit` are pure functions over daily bars strictly prior to the date; only the
shadow *writer* needs an alert row, and only to record the grade column. This replay is the
demonstration: 53 name-days scored, none of which had ever been scored.

**The real operational limit is the 200-session requirement.** A name with fewer prior sessions
gets "unknown" and zero credit, silently. That is **7 of the 27 rejects** (SCTX 21 sessions,
APMD 17, MAIR 90, GRML 114, DFNS 136, BBCQ 141, AERO 198) and **1 of the 26 real EPs** (FLY, 149).
Roughly a quarter of what reaches a real gate on a thin board is invisible to this axis by
construction — and recently-listed names are a population that throws EPs.

## 7. Limitations — read these before citing any number above

1. **The two arms differ in everything, not just structure.** The rejects were selected by failing
   a gate; the 26 were selected by forward return. Their median 20-day dollar volume is **$305M
   against $3.6M** — roughly 85× apart. RMV-15 correlates with dollar volume at −0.32 across the
   pooled 53, so *thinner reads as less tight*. **This design cannot separate structure from
   liquidity class**, and the tightness result is the one most exposed to it. Restricting to the
   three rejects inside the labelled real-EP liquidity band leaves AUC 0.705 — with three names on
   one side, which is a description, not a test.
2. **The tightness result is saturation, quantified in §4** — remove the nine ceiling-pinned
   rejects and it goes to 0.538 with p = 0.67. Treat the 0.692 in the table as an artifact, not a
   finding.
3. **Ten market days against two.** Half the EP arm is 2026-04-08. Collapsing to one observation
   per day gives AUC 0.95, which is not a result — it is two days on one side.
4. **The extension read runs backwards here** (0.390 against the pre-registered direction). That is
   not a contradiction of `structure_model.md` §4c, which measured extension against *outcome
   magnitude within alerts*, a different question. It is reported unflipped because flipping a sign
   after seeing the number is the fitting this study is forbidden from doing.
5. **Four reject names carry retro-adjusted prices** in the restored-history read (REAX, PMI, AMIX,
   SDOT) because of splits — and this cannot matter, by arithmetic rather than by luck: **every
   axis output is a ratio** (close ÷ 200-day average, close ÷ trailing high, close ÷ 10-day
   average, and the volatility measure normalises by close), so a uniform split adjustment cancels.
   Confirmed empirically too: all four are `no_stage2` under both sources.
6. **The labelled reference class is aging out of replayability.** At a 400-day purge, the April
   2026 EPs stop being replayable from our own database within weeks; MRNA is the only recent
   member. This replay only worked because the history could be re-pulled.

## 8. What this does and does not license

- **It does not license any change.** No cutline is proposed, no gate is proposed, nothing is
  promoted out of shadow. Structure work stays shadow per `structure_model.md` §8.
- **The finding for the operator** is that the axis, as built, adds nothing to admission on this
  reference class: it emits the same zero-credit verdict for 52 of 53 names, and after the
  sensitivity checks none of its outputs tells the two groups apart. Its Stage-2 ingredient is the
  only one with any residual signal, and it does not survive multiplicity.
- **The CAPR finding is architectural, not statistical**: the thing he is looking at is not
  represented anywhere in this component.

## 9. Reproduction

Harness: `scripts/probes/_structax_replay.py` (imports the live functions; read-only; $0).
Full output: `scripts/probes/_structax_replay_out.txt`.
Captures, each pulled once: `_structax_scanlog.psv` (scan log, both days), `_structax_bars.psv`
(`mi_daily_closes`, 156 tickers), `_structax_shadow_rows.psv` (the 116 live shadow rows, for the
fidelity check), `_structax_bars_polygon.psv` (restored history, both arms).
