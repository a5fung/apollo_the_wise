# Was the supply-ladder read measuring overhead supply, or just liquidity? — the answer, 2026-08-25

**MEASUREMENT ONLY. Nothing was changed.** No rule, threshold, filter, toggle, cutline or trade
state was touched, nothing is wired into any score, and nothing below is a recommendation — every
change this implies is the operator's fork (THE LINE). `_structure_read_v2.py` was run **unchanged**:
not one parameter was adjusted, no cutline was chosen, no direction was flipped after seeing a
number. Every comparison direction was written into the harness header before it was computed.

---

## The answer in one line

**It does not survive — and the two questions collapse separately, so say them separately.**

**(a) The separation the 0.728 measured** — labelled real EPs against rejects — falls to **0.579**
once the reject arm is every historical reject instead of 27 ultra-thin names, and to **0.511** with
dollar volume held constant. Dollar volume by itself, with no chart read at all, scores **0.888** on
that same comparison. **The 0.728 was liquidity class.**

**(b) Forward outcome, tested inside the scan cohort where there is no arm contrast at all**, is a
coin: **0.496** within dollar-volume bands and 0.481 within band-and-day, on 2,787 name-days across
92 trading days, day-clustered 95% interval **[0.454, 0.536]** — and **0.468** on the 173 HIGH
alerts we actually sent.

The read still reproduces the operator's CAPR call exactly (verified below, to three decimals).
It is a **faithful description of a chart and a non-predictor of anything** on this evidence.

---

## 1. Forward outcome, liquidity held constant — the test the operator authorised

**The design.** Every comparison is restricted to **pairs of names inside the same stratum** and
pooled across strata by pair count — so "dollar volume held constant" is structurally true, not
approximated. Two strata: dollar-volume decile, and decile × the same trading day (which holds
liquidity *and* market regime constant at once).

| how the read is scored | pooled | within dollar-volume band | within band **and** day |
|---|---|---|---|
| **share of volume above the open** (the primary) | 0.505 | **0.496** | 0.481 |
| the same on a fixed 60-session window | 0.497 | 0.492 | 0.459 |
| congestion zones cleared | 0.492 | 0.482 | 0.426 |
| gap-robust base tightness | 0.531 | 0.522 | 0.503 |
| *for reference* — distance below the trailing high | *0.541* | *0.528* | *0.487* |
| *for reference* — raw gap % at the open | *0.459* | *0.455* | *0.440* |

0.500 is a coin. Day-clustered 95% interval on the primary within band: **[0.454, 0.536]** — the
clustered test the 08-25 study could not run with ten days against two.

**No band hides a working sub-population.** Decile by decile the primary reads 0.504, 0.494,
0.500, 0.471, 0.504, 0.503, 0.540, 0.510, 0.467, 0.466 — from names trading $0.2M a day to names
trading $844M a day. By month: 0.510, 0.483, 0.496, 0.409, 0.498.

**And with no binary label at all.** Over pairs inside a stratum whose 5-session returns differ,
the share where the *lower* overhead reading had the better return is **0.488** within band
(0.484 within band-and-day). Against what the name *offered* (best high over sessions 0–5) it is **0.482** —
i.e. slightly the wrong way.

**Restricted to EP-shaped name-days only** (open gap ≥ 8.1%, the labelled real-EP arm's own
minimum, reused unchanged from the 08-25 study's gap-matched control): 1,315 name-days, primary
**0.495 [0.442, 0.550]** within band. Same null.

## 2. 🔎 The test that decides the 0.728 — where it actually goes

Same 26 labelled real EPs, same measure, same bar source. **Only the reject arm changes.**

| reject arm | n | median daily dollar volume | the supply read | **dollar volume alone** |
|---|---|---|---|---|
| the 08-25 study's arm (9 of its 27 readable here) | 9 | $2.0M | **0.731** | **1.000** |
| every historical reject killed by a substantive gate | 2,418 | $10.0M | 0.579 | 0.888 |
| …restricted to the real-EP dollar-volume band | 756 | $148.6M | 0.521 | 0.646 |
| …with dollar volume held constant (decile-stratified) | 2,418 | $10.0M | **0.511** | — |

**The row that carries the argument is the second one: 0.888 against 0.579, on 2,418 rejects.**
A quantity that never looked at a chart beats the supply read by a wide margin on a real sample
whose liquidity ranges overlap. The 0.728 was not evidence that the read sees supply; it is what any
liquidity-correlated quantity scores on two populations that differ 85-fold in liquidity.

⚠ **The 1.000 in the first row is arithmetically forced, not a measurement, and should not be
quoted as one.** Those 9 rejects sit entirely below the real-EP band's $38.9M floor, so two disjoint
ranges separate perfectly by construction. It restates the 08-25 caveat rather than testing it.

**The overlap the study could not get, it now has.** The 08-25 study had **four** rejects inside
the labelled real-EP liquidity band and called that "a description, not a test". This cohort has
**756**. Inside that band the read scores **0.521**.

The pooled correlation between the read and dollar volume also falls from the study's −0.403 on 53
rows to **−0.188** on 2,867 — the read is less of a pure liquidity proxy than the small sample
suggested, but what it has beyond liquidity does not predict anything.

## 3. On the names we actually alerted — also a coin

The bigger, cleaner sample the operator asked for. 261 live alert name-days, 248 with a settled
5-session outcome.

| | n | closed day 5 above the open | median 5-day return | median best high |
|---|---|---|---|---|
| **HIGH alerts** | **173** | 52% | +0.5% | +10.2% |
| MODERATE alerts | 66 | 52% | +0.5% | +10.5% |

| on HIGH alerts | AUC (day-5 close above the open) | 95% interval | within dollar-volume band |
|---|---|---|---|
| **share of volume above the open** | **0.468** | 0.389 – 0.543 | 0.472 |
| fixed 60-session window | 0.444 | 0.362 – 0.514 | 0.413 |
| congestion zones cleared | 0.451 | 0.364 – 0.551 | 0.419 |
| gap-robust base tightness | 0.536 | 0.453 – 0.639 | 0.506 |

Against what the name offered (best high over sessions 0–5) the primary reads **0.509** — a coin.
**The read carries no information about which of our HIGH alerts worked.** If anything the sign
runs backwards, though not distinguishably from chance.

Descriptively, by the read's own label, on those alerts:

| label | n | closed day 5 up | median best high |
|---|---|---|---|
| CLEARED_NOTHING | 23 | 61% | +13.3% |
| IFFY_AT_FIRST_ZONE | 57 | 54% | +11.8% |
| INTO_SUPPLY | 85 | 49% | +9.4% |
| CLEAR_AIR | 47 | 47% | +9.1% |
| LADDER_CLIMBING | 36 | 47% | +8.6% |

**CLEAR_AIR — the read's cleanest verdict — is tied for the worst win rate of the five, and is
fourth of five on median best high.** The
ordering is roughly the reverse of the model's. Descriptive only (the label depends on the
disclosed fixture-calibrated `MARGIN_ADR`), and no number tested above depends on it.

## 4. The cohort — the real N, not an estimate

| | value |
|---|---|
| `mi_ep_scan_log`, one row per (scan date, ticker), last tick of the day | **3,343 name-days · 1,925 tickers · 93 scan days · 2026-04-13 → 2026-08-25** |
| median names per scan day | **26** (not ~200 — that rate exists only on 08-24/08-25) |
| computable reads | 3,079 |
| the analysis pool after the regime-break exclusion below | **2,867 name-days · 1,564 tickers · 92 days** |
| with a settled 5-session outcome | **2,787** |

**What was dropped, and why — none of it silently.**

- **212 name-days on 2026-08-25**: `mi_daily_closes` ends 2026-08-24, so there is no alert-day open
  to read them at. That is 18 of the 08-25 study's own 27 rejects.
- **51** with fewer than the module's 10-session floor of history; **1** with no prior bars.
- **407 `filter:universe_*` rows** are excluded from every test because they exist **only** on
  08-24/08-25 — the scanner began logging universe-floor rejects then. Keeping them would put a
  regime break inside the date range. This is the same exclusion the 08-25 study's reject arm used.

**Forward outcomes.** 2,773 of 2,867 have a `mi_ep_missed_outcomes` row; **all 2,773 pass the #583
freshness guard** and **0 are stale** — the stale class that corrupted the earlier ranking table is
absent from this cohort, so the guard is applied as instructed but is a no-op here rather than a
filter. 94 have no row at all and 77 have a fresh row whose 5th session has not printed yet; both
are reported, not dropped. An independent recompute from `mi_daily_closes`, reproducing
`missed_outcomes.py`'s own arithmetic, agrees with the table on **2,696/2,696 rows to within 0.5
percentage points (Spearman 1.0000)**, and supplies 91 rows the table did not carry.

Base rate: **48.3%** of name-days closed the 5th session above the gap-day open; median 5-day
return **−0.4%**.

## 5. The read is faithful — that is not what failed

Recomputed here from `mi_daily_closes` rather than the study's own capture:

| | overhead | zones overhead | cleared | unfilled air | published |
|---|---|---|---|---|---|
| **CAPR 2026-08-24** | 0.444 | 17 | 0 | 17.95 ADR | 0.440 · 17 · 0 · 17.95 ✅ |
| **MRNA 2026-08-19** | 0.000 | 0 | 0 | 0.00 ADR | 0.000 · 0 · 0 · 0.00 ✅ |
| SNOW 2026-05-07 | 0.829 | 20 | 2 | 2.81 ADR | 0.826 · — · 4 · — |

**Bar-source fidelity, name by name** on the 35 name-days readable on both sources: Spearman
**0.988** on the primary (median absolute difference 0.0063), **1.000** on the fixed-window variant,
0.989 on zones cleared, 1.000 on the open gap. Every material disagreement is history depth —
`mi_daily_closes` starts 2025-07-21, so a 2026-04 name-day gets ~180 prior sessions where the
study's Polygon capture had ~271 (SNOW's two missing zones are exactly this). The fixed 60-session
variant, which is immune to it, agrees to three decimals and produces the same null.

**Join integrity.** The replayed session-open gap differs from the gap the scanner logged by a
median 4.5pp, one-directional (the log reads higher on 83% of rows) and rank-correlated at 0.503 —
the expected intraday-tick-versus-session-open basis difference, which is what a basis difference
looks like and what a wrong-row join does not.

## 6. The review sample for the labelling loop

40 name-days, written machine-readable to **`scripts/probes/_srbt_review_sample.psv`**. Buckets are
threshold-free — the read's top and bottom decile of overhead crossed with the sign of the
5-session outcome — drawn at most 2 per month and 2 per dollar-volume decile so the sample is not
twenty microcaps from one week. **The two "wrong" buckets are where a label teaches most.**

**🔴 B — the read said CLEAR AIR and the name collapsed** (198 candidates):

| ticker | date | daily $ vol | overhead | 5-day | why we saw it |
|---|---|---|---|---|---|
| GDC | 2026-05-06 | $0.1M | 0.000 | −97.9% | already up 77% in 5 days |
| CAR | 2026-04-22 | $1,293M | 0.000 | −76.6% | already up 92% in 5 days |
| ADVB | 2026-07-24 | $0.1M | 0.000 | −65.4% | already up 242% in 5 days |
| JLHL | 2026-06-08 | $0.8M | 0.000 | −61.8% | already up 137% in 5 days |
| MRAM | 2026-05-13 | $15.5M | 0.000 | −42.4% | EP cooldown |
| AEHR | 2026-08-14 | $211M | 0.000 | −23.9% | EP cooldown |

**A pattern worth his eye:** four of the six had already run 77–242% in the prior five days. Blue
sky above is exactly what a vertical move produces — **"nothing overhead" and "extended" are the
same chart**, and the read scores that chart as clean.

**🔴 C — the read said BURIED and the name ran** (140 candidates):

| ticker | date | daily $ vol | overhead | 5-day | best high | why we saw it |
|---|---|---|---|---|---|---|
| VEEE | 2026-07-08 | $0.2M | 0.923 | +353.8% | +732.6% | dollar-volume floor |
| IONL | 2026-04-14 | $4.8M | 0.904 | +98.4% | +119.9% | low relative volume |
| ARQQ | 2026-06-15 | $8.1M | 0.892 | +102.1% | +108.0% | market cap floor |
| FJET | 2026-05-22 | $5.0M | 0.924 | +81.6% | +86.4% | market cap floor |
| BLSH | 2026-08-13 | $27.5M | 0.926 | +13.8% | +17.5% | passed every gate |

The confirming buckets (A: clear and it ran, 213 candidates; D: buried and it fell, 139) are in the
same file.

**What the labelled corpus should look like.** The existing precedent is
`tests/fixtures/must_not_miss_eps.py` — one appendable line per member, each carrying a
`label_source` naming exactly where the label came from ("operator" or "evidence:<citation>"), with
unverified metrics declared rather than guessed. A chart-read corpus wants the same shape plus the
read's own verdict at label time, so agreement and disagreement are both recoverable later: ticker,
date, the operator's verdict, his one-line reason, the read's output at that date, and the
label source. That fixture is replayed through the live stack on every suite run, which is what
stops a labelled corpus from rotting into a document nobody executes.

## 7. What this does and does not license

- **It licenses nothing.** No cutline, no gate, no promotion, no removal. The v2 read stays exactly
  where it was — wired into nothing.
- **The finding:** the 0.728 was liquidity class. Held constant, the supply read is a coin — on
  2,787 name-days, on the 1,315 EP-shaped ones, on the 173 HIGH alerts, and in every one of the ten
  dollar-volume deciles.
- **What it does NOT say:** that overhead supply is irrelevant to a chart. It says *this encoding of
  it*, on *this evidence*, does not predict a 5-session outcome and does not separate labelled real
  EPs from rejects once liquidity is matched. The operator's CAPR read is reproduced faithfully; the
  question was always whether that generalises, and it does not.
- **The fork is his**, unchanged in shape from the 08-25 doc: whether a shadow supply reading is
  worth recording at all now, and what evidence would ever let chart structure touch admission.

## 8. Limitations — read before citing any number above

1. **The cohort is "names a gate already logged."** It cannot speak to names never scanned. Not
   fixable from this data.
2. **The outcome is a 5-session return from the gap-day open**, not a traded R. A measure could
   carry entry-quality information that this horizon cannot see. The 08-25 study's own target — real
   EP versus reject — is tested separately (§2) and collapses the same way.
3. **The measure is partly degenerate on this cohort**: 15% of name-days read exactly 0.000 (blue
   sky). Ties count half in every AUC, so a real effect is dragged toward 0.500. This is a genuine
   ceiling on how much this measure *can* say here — but a ceiling does not explain the alerted-names
   result running mildly backwards, nor dollar volume scoring 1.000 where the read scores 0.731.
4. **`mi_daily_closes` starts 2025-07-21**, so the all-history volume profile is ~180 sessions deep
   in April and ~270 in August. The fixed 60-session variant is the control and gives the same
   answer; the decile × day stratification also removes it (every name on a day shares the depth).
5. **Test A's arms remain two different populations** — 13 of the 26 labelled real EPs are still one
   date, 2026-04-08. Banding shrinks an arm contrast, it cannot repair one. TA is a consistency
   check on the within-cohort test, not the test.
6. **`filter:universe_*` rows are excluded**, so the thinnest, cheapest rejects are absent from the
   pool by construction. That exclusion removes liquidity spread; it makes the null *harder* to
   produce, not easier.

## 9. Reproduction

- Stage 1 — the read, once per name-day: `scripts/probes/_srbt_reads.py` →
  `scripts/probes/_srbt_reads.psv` (3,449 rows). Measure imported unchanged from
  `scripts/probes/_structure_read_v2.py`.
- Stage 2 — the statistics: `scripts/probes/_srbt_analyze.py` → `scripts/probes/_srbt_out.txt`
  (full output) and `scripts/probes/_srbt_review_sample.psv`.
- Captures, pulled ONCE from prod read-only, re-read never re-pulled ($0):
  `_srbt_scanlog.psv` (3,343 name-days), `_srbt_outcomes.psv` (3,226 rows),
  `_srbt_alerts.psv` (261), `_srbt_bars.psv.gz` (490,050 daily bars, 1,926 tickers),
  and the 08-25 study's `_structax_bars_polygon.psv` / `_structax_scanlog.psv` for the
  bar-source fidelity check only.
- Statistics: rank-based AUC with midranks for ties; stratified AUC = pairs restricted to a stratum,
  pooled by pair count; threshold-free concordance as its continuous twin; 95% intervals by
  **cluster bootstrap over whole trading days**, 400 resamples.
