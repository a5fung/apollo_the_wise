# Can a supply-ladder read tell a real EP from what we threw away? — structure read v2, 2026-08-25

**MEASUREMENT ONLY. Nothing was changed.** No rule, threshold, filter, toggle, cutline or trade
state was touched, nothing is wired into the live score, and nothing below is a recommendation —
every change this implies is the operator's fork (THE LINE). Every comparison direction was written
into the harness header before it was computed; no cutline was chosen or tuned.

---

## The answer in one line

**Yes, and it separates CAPR from MRNA cleanly — but the size of the edge depends on the price
basis. The supply reading scores AUC 0.728 read at the open, and 0.647 (95% interval 0.499 - 0.796,
p = 0.052) when every reject is re-read at the best price its own scan log showed that day. The
direction holds across both bases; the statistical significance does not. Either way it beats the
live structure axis's 0.481 on the identical 26-versus-27 populations, and it is not gap size in
disguise: at matched gap size the rejects gap BIGGER (median 14.4% against 9.9%) and the supply
reading gets stronger, to 0.763, while raw gap % runs backwards at 0.241.**

⚠ **Which basis is right is a real question, not a formality.** The live path re-checks the gap in
real time and can admit a name that was under the floor at the open but crossed it intraday
(`must_not_miss_eps.py` says so explicitly), so the best-price read is arguably *closer* to the live
mechanism than the open — for both arms, not just the rejects. The labelled real EPs are only
recorded on an open basis, so a symmetric best-price comparison cannot be run today. **Treat 0.647
as the conservative number and 0.728 as the open-basis number; do not quote 0.728 alone.**

The one part of his objection that did **not** produce a working measure is base tightness: the
defect he named is real and reproducible at N=1, but fixing it separates nothing (AUC 0.553).

## The three answers asked for

| question | answer |
|---|---|
| **Where is this gap landing?** | Measured, per name. CAPR on 08-24 opened at **8.03 — 0.02 ADR under its first overhead level (8.06) and 0.21 ADR under the bottom of a $10 vacuum it has never traded back into**, with 44% of every share it has ever traded sitting above the open. MRNA opened at 116.02 with **0.0%** of its volume overhead and no vacuum at all. |
| **How many zones does the move clear?** | The ladder count. Real EPs clear a median of **1** overhead zone, rejects **0** (AUC 0.770, the only secondary to survive Holm). But it is partly gap size — see §5, it falls to 0.678 once gap size is matched. |
| **Is the base actually tight, or does it merely average tight?** | His objection is **correct and mechanically reproducible** (§3). The gap-robust replacement is a **null**: AUC 0.553, p = 0.51. Reported as a null, not dressed up. |

---

## 1. What was built, and what was reused

**Extended the existing encoder — no third implementation** (P15). The level derivation is
**imported** from `scripts/probes/_533_nbis_structure_encoder.py`: pivot highs merged within 0.3%
(his own RMVP developer parameter), qualified only by **≥2 failed test episodes**, level dies on a
daily close above it, **and the lookback is each level's own test dates — no window parameter**
(`structure_model.md` §3). The tightness primitive is the live `flag_detector._compute_rmv`, so the
v1-versus-v2 comparison is against the real thing.

**Parity-checked before anything was computed on top of it.** The dict→tuple adapter reproduces all
four level values `structure_model.md` §4 documents — **NBIS 226.81** (his own "~$227"), **EROC
11.88**, **SE 118.09**, **FRMI's 50-day 7.06** — 4/4, pinned by
`tests/test_structure_read_v2.py::test_parity_reproduces_the_four_documented_levels`. An adapter bug
here would have made every ladder number meaningless while still looking plausible.

**Three things are new, because nothing in the repo encodes them:**

1. **Volume-at-price overhead** — the share of the name's own traded volume sitting above the open,
   each session's volume spread across its own high-low range. His supply argument taken literally
   (*"congestion of prices is where potential supply is… that's where lots of buy/sell happened"*).
   **Threshold-free**: no cutline, no window, no tuned constant. 0.0 = blue sky.
2. **Unfilled gap zones** — a true price vacuum (`high[i] < low[i-1]` down, `low[i] > high[i-1]` up)
   with the part later sessions traded back through subtracted away. This is the July-27 CAPR
   object. It answers below / inside / above, per zone.
3. **Gap-aware base tightness** — `base_range_adr`: the base's close-to-close span (which a gap
   inflates) divided by ADR20 (a mean of *intraday* ranges, which a gap does not inflate).

**No lookahead, asserted not assumed.** Every read takes bars strictly prior to the alert date plus
the **alert-day open** (known at 09:30, which is when admission decides), and the function raises if
a bar dated on or after the alert date reaches it — the 08-25 rows in the capture are partial-day
and physically present in the same file.

**One inherited constant is disclosed as calibrated**: `MARGIN_ADR = 0.25` is fixture-calibrated on
his eight labelled reads. It is used **only** for the descriptive IFFY label; nothing tested depends
on it. `LARGE_GAP_ADR = 1.0` is the encoder's `REJECT_ADR`, swept at 0.5× and 2.0× in §8.

## 2. The populations — the same ones the 08-25 replay used

| | what it is | name-days | market days |
|---|---|---|---|
| **Real EPs** | `tests/fixtures/must_not_miss_eps.py`, operator/evidence-labelled (TDIC excluded in the fixture itself) | 26 | 10 |
| **Rejects** | every name that cleared the universe floors on the two silent days and was killed by a real gate — re-derived from `mi_ep_scan_log`, not from prose | 27 | 2 |

⚠ **These are not 26 versus 27 independent observations.** Thirteen of the 26 real EPs are the same
market day, 2026-04-08; the whole reject arm is two consecutive days. Read every number as **ten
days against two**. Bars are the restored-history Polygon capture the 08-25 replay already pulled
(re-read, never re-pulled — $0), which the replay validated at 46/50 tickers within 1% of
`mi_daily_closes`. Coverage is **53/53** — v2 needs no 200-session average, so nothing is "unknown".

## 3. 🔴 His base-tightness objection is right, and here is the mechanism

> *"even base tightness seems off — how can CAPR have a tight base when there's two large gap downs?"*

RMV-15 is a **ratio**: mean daily true range over the last 3 bars ÷ the mean over the last 15,
mapped to 0-100. **Two independent defects, both present on CAPR:**

- **Inside the window it inverts.** CAPR's 15-bar base contains a single **59.25%** true-range bar
  (2026-08-14). That one bar drags the baseline mean to 15.13% — so a name whose *recent* daily
  ranges are 11%, 17% and 17% comes out at a ratio of **0.996** and reads **RMV 54.2**, comfortably
  inside real-EP territory (the labelled real-EP median is 48.6 and the reject median 74.9 — `structure_axis_replay_2026-08-25.md` §4). **A big
  gap in the base makes the base read tighter.**
- **Outside the window it is blind.** The gap he actually named — **27 July** — is about 20 sessions
  back, outside the 15-bar lookback entirely. RMV-15 cannot see it at any value.

The gap-robust replacement says what he says: CAPR's base spans **6.33 ADR** of close-to-close
range and contains a **2.48-ADR vacuum**, so `tight_v2` is **False** on both days.

**And then it separates nothing.** `base_range_adr` scores **AUC 0.553 [0.397, 0.709], p = 0.51** —
a null, and it stays a null in every subgroup (0.575 hard cut, 0.559 gap-matched, 0.576 excluding
young names). Fixing the defect is correct; it does not buy admission accuracy on this reference
class. That is the honest result, and it is reported as one.

## 4. Does it separate? The pre-registered numbers

Directions were fixed from `structure_model.md` before computing. AUC is the chance a randomly
picked real EP scores better than a randomly picked reject; 0.500 is a coin. Ties count half.

| what is measured | AUC | 95% confidence | real EP median | reject median | raw p |
|---|---|---|---|---|---|
| **PRIMARY — share of volume above the open** | **0.728** | 0.591 – 0.865 | **0.093** | **0.515** | 0.0011 |
| secondary — congestion zones cleared | 0.770 | 0.642 – 0.898 | 1 | 0 | <0.0001 |
| secondary — gap-robust base tightness | 0.553 | 0.397 – 0.709 | 3.67 | 3.88 | 0.51 |
| secondary — unfilled air above the open | 0.497 | 0.340 – 0.654 | 0.00 | 0.00 | 0.97 |
| *for reference* — the live structure axis | *0.481* | *0.325 – 0.638* | *0* | *0* | — |
| *for reference* — distance below the trailing high | *0.662* | — | — | — | — |

The primary is a **single** pre-registered test and carries no correction. Of the three-member
secondary family, **only zones-cleared survives Holm** at family alpha 0.05.

**The median gap is the readable part:** half the labelled real EPs opened with **under 10% of their
own traded history overhead**; half the rejects opened with **over 51%** overhead.

### Is the primary new information, or trailing-high distance in disguise?

Pre-registered check, declared before the number was seen: if Spearman against `near_high_frac` is
0.90 or above, the honest headline is "restates the live axis's own trailing-high term, computed
differently". **It is −0.747 — related, not the same thing**, and it scores 0.728 against that
term's 0.662 on the same rows.

### The unfilled-gap span is a null as a population scalar — say so plainly

`overhead_unfilled_gap_span_adr` is **0.00 for 33 of the 53 name-days**, so as a continuous score it
is mostly ties (AUC 0.497). It is decisive on CAPR specifically (17.95 ADR) but **QURE, a labelled
real EP, carries 12.86 ADR of it**. The vacuum concept is what makes CAPR legible; it is not a
discriminator on its own.

## 5. 🎯 The control that matters most: it is not gap size

Every labelled real EP gapped ≥8.1% at the open by construction. Many rejects were logged on an
intraday gap and barely moved at the open. So a measure keyed off the open could separate the arms
purely by separating gap size. `structure_model.md` §1 claim 4 makes this the decisive test —
zones-consumed against raw gap %, **at comparable gap size**.

- **Correlation with the open gap: −0.003.** The primary is uncorrelated with gap size across all 53.
- **Matched to gap ≥8.1%** (the real-EP arm's own minimum, so the floor comes from the data's
  definition, not from a choice): 26 real EPs against 15 rejects, and the rejects now gap **more**
  (median 14.4% against 9.9%).

| matched on gap size | AUC | 95% confidence |
|---|---|---|
| **share of volume above the open** | **0.763** | 0.617 – 0.908 |
| congestion zones cleared | 0.678 | 0.513 – 0.844 |
| **raw gap % itself** | **0.241** | 0.079 – 0.403 |

**Raw gap % runs backwards.** Inside a gap-matched field the rejects gap harder and are far more
buried. ⚠ **Name the mechanism before over-reading it:** most rejects were killed by liquidity or
market-cap gates, not by gap size, so what survives an 8.1% filter is the violent thin end of the
board (SDOT 63%, DFNS 48%, AMIX 42%). The 0.241 is a real signed effect on 26 against **15**, but it
is a selection property of this reject arm — **not** evidence that gap % is anti-predictive in
general. This is his own claim 4 — *raw gap % has no reference frame; zones-consumed does* —
measured, and it is the first evidence in this repo that comes out **for** it rather than against
(compare `structure_model.md` §7, whose ladder gradient came back backwards on a different question:
excursion magnitude within declined alerts, not real-EP recall).

### Two more controls, both run before this was written

- **Best-admission-price sensitivity (the harshest test).** Re-read every reject at the *highest*
  price its own scan log showed that day — the most favourable moment admission could have fired
  (every reject reached at least a 9.2% gap at some tick), while real EPs keep their opens. The
  primary falls to **0.647 [0.499, 0.796], p = 0.052** — the edge survives in direction but is no
  longer distinguishable from chance at this N. It is asymmetric — rejects get their best price,
  real EPs only have an open recorded — but **not simply pessimistic**: the live path re-checks the
  gap in real time, so a best-price read is arguably closer to what admission actually sees. Quote
  0.647 as the conservative number and 0.728 as the open-basis number; never 0.728 alone.
- **Does zones-cleared measure clearing, or just "this name has zones"?** A level needs ≥2 failed
  test episodes to qualify, so a name that collapsed and never retested has none. Both arms are
  similar (22/26 real EPs and 25/27 rejects have ≥1 qualified overhead zone), so availability is not
  the driver. Restricted to names that had zones, the *share* cleared scores 0.865 — ⚠ **post-hoc,
  outside the pre-registered family, reported as a confound check, not as a finding.**

## 6. CAPR versus MRNA — the worked examples

| | open | volume above the open | zones overhead | cleared | to the next zone | unfilled air above | verdict, live axis | v2 label |
|---|---|---|---|---|---|---|---|---|
| **CAPR 08-24** | 8.03 | **44.0%** | 17 | **0** | **0.02 ADR** | **17.95 ADR** | `no_stage2`, 0 | IFFY_AT_FIRST_ZONE |
| **CAPR 08-25** | 7.25 | **56.4%** | 18 | **0** | 0.48 ADR | **18.94 ADR** | `no_stage2`, 0 | INTO_SUPPLY |
| **MRNA 08-19** | 116.02 | **0.0%** | **0** | 0 | nothing overhead | **0.00 ADR** | `no_stage2`, 0 | CLEAR_AIR |

**It reproduces his read, in his own terms.** The July-27 vacuum is found and dated:
**7.85 → 18.30, a 53.1% gap down of which 10.02 of 10.46 has never been traded back into.** CAPR
opened at 8.03 — *below* the bottom of that remnant (0.21 ADR under it) and 0.02 ADR under its first
overhead level at 8.06, with $18-20 of untouched supply above. That is *"the gap up just barely made
up for the most recent drop but just at where there's a huge gap down from July 27."*

MRNA is the opposite in every column: nothing traded above 116.02 in 272 sessions, no qualified
overhead level, no vacuum. **The live axis gives both names the identical `no_stage2`, credit-0
verdict; v2 puts 44-56 percentage points of overhead supply between them.**

Two other worked names, for calibration: **SNOW** (a labelled real EP) opened with **82.6%**
overhead and cleared 4 zones — so a high overhead reading is not by itself disqualifying, and the
measure is a gradient, not a gate. **OESX**, the reject that missed the dollar-volume floor by $727
and the only name the live axis credited in the whole study, reads **0.0% overhead, CLEAR_AIR** —
v2 agrees with the live axis that this one looked structurally fine.

## 7. Young names — a number, not "unknown"

The live axis needs 200 sessions and silently returns "unknown" plus zero credit below that: **7 of
the 27 rejects and 1 of the 26 real EPs**. **v2 requires 10 sessions and reads whatever exists**,
reporting its own history depth alongside. All eight get a real read:

| name | arm | prior sessions | live axis | volume above the open | zones cleared | v2 label |
|---|---|---|---|---|---|---|
| APMD | reject | 17 | unknown | 0.515 | 0 | CLEARED_NOTHING |
| SCTX | reject | 21 | unknown | 0.047 | 0 | CLEAR_AIR |
| MAIR | reject | 90 | unknown | **0.961** | 0 | CLEARED_NOTHING |
| GRML | reject | 114 | unknown | 0.680 | 1 | INTO_SUPPLY |
| DFNS | reject | 136 | unknown | 0.468 | 0 | CLEARED_NOTHING |
| BBCQ | reject | 141 | unknown | 0.793 | 0 | INTO_SUPPLY |
| **FLY** | **real EP** | 149 | unknown | 0.628 | **4** | IFFY_AT_FIRST_ZONE |
| AERO | reject | 198 | unknown | 0.883 | 0 | INTO_SUPPLY |

⚠ **The bias runs against the measure, which is why they stay in the headline.** A short history
means little overhead *by construction*, so the seven young rejects should read cleaner than they
deserve — and two do (SCTX 0.047, DFNS 0.468). Excluding all eight moves the primary to 0.710
[0.560, 0.860], essentially unchanged. **What v2 cannot do for a young name is see structure that
predates its listing** — SCTX's 21 sessions contain no congestion because there is barely any
history, not because the stock is free. `thin_history` is flagged in the output for exactly this
reason; the flag is honest, but it is a flag, not a fix.

## 8. Limitations — read these before citing any number above

1. 🔴 **This design cannot separate structure from liquidity class.** The two arms differ 85× in
   dollar volume ($305M against $3.6M median), and the primary correlates with dollar volume at
   **−0.403** across the pooled 53 — thinner names read as more buried. It is *partly* a
   between-group effect: **within** each arm the correlation is much weaker (−0.248 real EPs,
   −0.175 rejects), so the measure is not purely a liquidity proxy — but it is not cleanly separated
   either. Against only the four rejects inside the labelled real-EP liquidity band it scores 0.885
   — with four names on one side, which is a description, not a test.
2. **Ten market days against two.** Half the real-EP arm is 2026-04-08. Dropping that day leaves the
   primary at 0.738 [0.563, 0.913] on 13 names — the direction holds, the interval widens.
3. **The reference class is selected on forward return, not on structure**, so there is no direct
   circularity — but a common cause (big liquid names in uptrends both gap to new highs *and* go on
   to run) is not excluded by this design.
4. **The reject arm is "what a gate killed", not "what failed".** These names were selected by
   failing an admission gate, and 24 of 27 sit below the thinnest labelled real EP by dollar volume.
   A cleaner test needs rejects that were genuinely EP-shaped.
5. **PMI's 455-ADR unfilled-gap figure is an outlier**, not an error: its Polygon-adjusted history
   runs from ~$350 to ~$3, so most of the descent is genuinely untraded air. AUC is rank-based, so
   it does not move any number above.
6. **The volume profile has an implicit window** — the ~13 months the capture holds (272 sessions
   for most names). The level derivation does not (its lookback is each level's own test dates), but
   the profile does. The 60-day variant is reported per name in the capture and is not tested.
7. **`base_range_adr` is a null here and is reported as one.** It is uncorrelated with dollar volume
   (+0.038), so its null is not a liquidity artifact — it simply does not discriminate on this pair
   of populations.
8. **No permutation or session-clustered test was run.** With ten days against two, a session
   permutation would be uninformative; the confidence intervals above already understate the
   clustering, and §8.2 is the honest version of that caveat.

## 9. What this does and does not license

- **It licenses nothing.** No cutline is proposed, no gate is proposed, nothing is promoted out of
  shadow. Structure work stays shadow per `structure_model.md` §8; promotion is fork **S-3**
  (CHANGE_PROCESS + his sign-off).
- **The finding for the operator:** the supply-ladder read reproduces his CAPR call in his own terms
  and separates the two populations at 0.728 where the live axis manages 0.481 — and it is not gap
  size in disguise. **The fork is his: whether a shadow supply reading gets recorded alongside the
  structure axis, and on what evidence it would ever be allowed to touch admission.**
- **His base-tightness objection is confirmed and the fix is a null.** Both halves of that sentence
  matter; the second is not softened.
- ⚠ **One observation cuts against a stated corollary of his, and it is surfaced rather than
  buried.** `structure_model.md` §1 records the IFFY case — a gap that stalls at, or fails to exceed,
  the FIRST congestion — as *"its own bucket, not a low score"*, i.e. read as a weakness. On this
  cohort it is **the modal real EP**: 10 of the 26 labelled real EPs open within a quarter-ADR of
  their nearest overhead zone, against 2 of the 27 rejects. **Descriptive only** — the label depends
  on `MARGIN_ADR = 0.25`, which is fixture-calibrated on his eight reads, and it was not part of the
  pre-registered set. It is flagged because he asked for chart reading to be fixed, and this is a
  place where the encoded model disagrees with his own written corollary.

## 10. Reproduction

- Measure: `scripts/probes/_structure_read_v2.py` (imports the encoder's level derivation; pure over
  prior bars + the open; parity-checked; read-only; $0).
- Study: `scripts/probes/_structure_read_v2_study.py`. Full output:
  `scripts/probes/_structure_read_v2_out.txt`.
- Tests: `tests/test_structure_read_v2.py` — 14 cases pinning the parity targets, the gap-fill
  arithmetic (clean / filled / partially filled / two-remnant / up-gap / touching), the volume
  weighting, the gap-robust tightness claim, and the no-lookahead guard.
- Captures, all pulled once by the 08-25 replay and re-read here, never re-pulled:
  `_structax_bars_polygon.psv`, `_structax_bars.psv`, `_structax_scanlog.psv`, and the encoder's own
  `_533n_daily.tsv` for the parity check.
