# Can the chart read throw out his junk without throwing out his real EPs? — structure read v3, 2026-08-25

**MEASUREMENT ONLY. Nothing was changed.** No rule, threshold, filter, toggle, cutline or trade
state was touched, nothing is wired into any score, and nothing below is a recommendation — every
change this implies is the operator's fork (THE LINE). Every direction and both cutline definitions
were written into the harness header before a single count was computed.

---

## The answer in one line

**Of his 11 horrendous charts it rejects 8, and of the 26 must-not-miss real EPs it wrongly rejects
0 — but the thing that gets there is not a new chart read. It is the extension rule we already have,
read over 20 sessions instead of 5, at his own signed 75% threshold, with nothing fitted to
anything.**

- **The live stack already rejects all 11.** None was ever admitted, alerted or traded. The
  extension gate alone gets 6; cooldown, market cap, dollar volume, relative volume and the score
  floor get the other 5. **His first objective is already met on these labels.**
- **The whole gain is the lookback window.** The live gate looks back 5 sessions and catches 6 of
  the 11. The identical rule at the identical 75% threshold over **20 sessions catches 8** — adding
  CAR on 04-21 (up 467% over 20 sessions, but only 64% over 5) and AEHR on 08-14 (up 89% over 20,
  25% over 5). It still costs **0 of the 26 real EPs**, whose most-extended member reaches 62%
  against the 75% cap.
- **The chart read adds nothing to that.** At every cutline tested, the run-up number alone rejects
  exactly the same names. Its only demonstrated contribution is saving CAR on 04-01 — the date he
  called ok'ish — which the run-up number alone kills.
- ⚠ **One flag, not a proven miss.** The 20-session setting also rejects MXL on 04-24, the date he
  pointed at when he said the 04-21 setup was on the wrong day. He never said 04-24 was tradeable,
  so this is a cost worth surfacing, not a labelled miss.

🛑 **Window length is a detection criterion, so it is his alone (THE LINE).** Nothing here proposes
changing it; the measurement is on the table and the fork is his.

## What his bar actually was, and why the earlier study answered a different question

> *"The first bar I want it to clear is to filter out the bad charts, like CAPR. I want to make sure
> we don't trade these poor charts, that's the first objective."*

The 08-25 backtest measured whether the supply read predicts winners and got a null (0.496 at
matched dollar volume, 2,787 name-days). That was the wrong test for this bar. His bar is
**precision on the reject side**: throw out junk, keep the real EPs. It is an easier bar and it is
what this card measures — two counts, not an AUC.

## 1. 🔴 The overlap, first — because it decides what the counts mean

`blocked_by_live_extension_rule` replicates `ep_detector.py` to the line: `MIN(close)` over
`[alert date − 10 calendar days, alert date)`, skip when `(prev close − MIN) / MIN ≥ 75%`
(`MAX_EXTENSION_PCT`, operator-signed 50 → 75 on 2026-08-22). The constant is **imported**, so if he
moves it this measure moves with it.

| ticker | date | extension reading | at the 75% cap | the gate that actually rejected it |
|---|---|---|---|---|
| GDC | 05-06 | 76.7% | **blocked** | already up 77% in prior 5 days |
| CAR | 04-22 | 92.4% | **blocked** | already up 92% in prior 5 days |
| ADVB | 07-24 | 242.4% | **blocked** | already up 242% in prior 5 days |
| JLHL | 06-08 | 137.0% | **blocked** | already up 137% in prior 5 days |
| QH | 06-18 | 223.7% | **blocked** | already up 224% in prior 5 days |
| MRAM | 05-13 | 134.7% | **blocked** | EP cooldown (extension would have caught it too) |
| CAR | 04-21 | 64.1% | passes | relative volume 0.1× < 2.0× |
| AEHR | 08-14 | 24.8% | passes | EP cooldown |
| YOU | 08-05 | 4.7% | passes | score 36 < 50 |
| QTTB | 07-13 | 0.0% | passes | market cap $190M < $500M |
| IPCX | 07-29 | 0.0% | passes | dollar volume $522K |

**6 of 11 die to the extension gate. 11 of 11 die to the live stack.** And the gate costs nothing on
the other side: the most extended of the 26 real EPs reads 27.2%, against a 75% cap — **0 of 26**.

⚠ **So the honest frame for everything below is not "does a new filter work" but "is there anything
left for a new filter to do".** On this evidence the answer is: very little, and what is left is
already being done by gates that exist.

## 2. The two counts

Two cutlines were declared in advance and only these two are quoted:

- **ANCHOR-75** — his own signed 75%, carried over unchanged to each percent-basis measure. Chosen
  by him, on other evidence, before this study existed. **Unfitted.**
- **ANCHOR-EP** — the highest value any of the 26 real EPs reaches, plus a hair. ⚠ **Its 0-of-26 is
  arithmetically forced and is NOT a result** — the cutline is that population's own maximum. Only
  its of-11 count carries information.

| measure | cutline | basis | **of the 11 rejected** | **of the 26 wrongly rejected** | dates he named as good, lost |
|---|---|---|---|---|---|
| run-up over 5 sessions | 75.0% | unfitted | **5** | **0** | none |
| run-up over 5 sessions | 11.9% | fitted to the 26 | 8 | 0 | MXL 04-24 (pointed-at) |
| run-up over 10 sessions | 75.0% | unfitted | **7** | **0** | none |
| **run-up over 20 sessions** | **75.0%** | **unfitted** | **8** | **0** | MXL 04-24 (pointed-at) |
| run-up over 20 sessions | 62.1% | fitted to the 26 | 8 | 0 | MXL 04-24 (pointed-at) |
| run-up in daily-range units, 20 sessions | 10.3 | fitted to the 26 | **0** | 0 | none |
| position in the whole captured range | 0.97 | fitted to the 26 | 3 | 0 | none |

**The best honest result is the bolded row: 8 of 11 against 0 of 26 at a threshold he set himself,
before this study existed.** It is the only 8-of-11 in the table that owes nothing to a cutline
chosen after seeing the labels. Every configuration that reaches 8 also rejects MXL on 04-24.

⚠ **The two anchors are not the same kind of evidence.** He STATED that CAR on 04-01 was ok'ish —
rejecting that date contradicts his own words, and nothing above does. He only POINTED AT MXL 04-24
while explaining that 04-21 was the wrong day; he never ruled it tradeable. The fixture keeps the
two apart (`MUST_NOT_REJECT_DATES` versus `POINTED_AT_DATES`) so an inference never wears his name.

**The normalised variant fails outright.** Dividing the run by the name's own average daily range —
the version that could not be a liquidity proxy — rejects **0 of 11**. The reason is mechanical and
worth knowing: the very move being measured inflates the name's average daily range, so a stock up
240% divides by a range that grew with it and reads no more extended than a quiet one. That measure
is dead for this purpose.

### The full trade-off, with nothing chosen

| cutline | of 11 | of 26 | dates he named, lost |
|---|---|---|---|
| 5% | 8 | 3 | 1 |
| 10% | 8 | 2 | 1 |
| **12%** | **8** | **0** | **1** |
| 20% | 7 | 0 | 1 |
| 35% | 7 | 0 | 0 |
| 45% | 6 | 0 | 0 |
| 75% | 5 | 0 | 0 |
| 150% | 1 | 0 | 0 |

On this measure there is no cutline that gets more than 7 of the 11 without also rejecting MXL on
04-24 — and the same holds on the 20-session window, whose own sweep runs 8/11 from 40% to 88% with
MXL lost throughout, then falls to 6/11 at 100% where MXL survives. ⚠ That statement covers only the
measures swept here.

## 3. What it adds beyond the extension rule we already have — nothing, on the 11

Every composed verdict was run beside the identical cutline applied with **no chart read at all**.

| measure | cutline | composed (chart + run-up) | run-up alone | names where they differ |
|---|---|---|---|---|
| 5-session run-up | 75.0% | 5 of 11 | 5 of 11 | **none** |
| 5-session run-up | 15.2% (its own fit) | 8 of 11 | 8 of 11 | **none** |
| 20-session run-up | 75.0% | 8 of 11 | 8 of 11 | **none** |
| 20-session run-up | 62.1% | 8 of 11 | 8 of 11 | **none** |

**The supply read changes no verdict on any of the eleven.** The run-up number carries the whole
result. That is the finding the card asked for in advance, and it says the right move is to trust
the rule we already have rather than add a chart read on top of it.

**Its one demonstrated contribution is a single name, and it is on the admit side.** CAR on 04-01 —
the date he called ok'ish — had run 18% in five sessions, enough for the run-up number alone to
reject it. The chart read saves it, because on 04-01 CAR still had **43% of its traded volume
overhead and 13 congestion zones above the open**, and by 04-21 both are zero. That is exactly his
distinction, encoded. It is N = 1.

## 4. The cost at scale

Run over the whole scan cohort — 2,867 readable name-days across 92 trading days, median 25 names a
day:

| measure | cutline | flagged | share of the cohort | **new** (not already extension-blocked) | **new per day** |
|---|---|---|---|---|---|
| 5-session run-up | 75.0% | 43 | 1.5% | 0 | **0.0** |
| 5-session run-up | 11.9% | 280 | 9.8% | 222 | **2.4** |
| 20-session run-up | 75.0% | 149 | 5.2% | 91 | **1.0** |
| 20-session run-up | 62.1% | 189 | 6.6% | 131 | **1.4** |

**The cost is not the problem here.** At the 8-of-11 setting it newly excludes about two and a half
names a day out of twenty-five — a tenth of the board, not a third. The problem is what it excludes,
not how much.

### On the names the live stack actually admits — where a new filter could bite

Everything else was already rejected, so the 183 readable HIGH alerts are the only population a new
exclusion could change.

| measure | cutline | HIGH alerts flagged | of those, outcome settled | their median 5-session return | the rest |
|---|---|---|---|---|---|
| 5-session run-up | 75.0% | **0** | 0 | — | +3.0% |
| 5-session run-up | 11.9% | 10 | **6** | +0.9% | +3.0% |
| 20-session run-up | 75.0% | 2 | **1** | +4.8% | +2.9% |
| 20-session run-up | 62.1% | 5 | **4** | −9.3% | +3.0% |

⚠ **Every median above is over the settled column, not the flagged column** — four of the ten and
one of the two have not printed a 5th session yet. Six settled names is far too few to call, and the
six are mixed: GRRR −31% and HPE −24%, against AMBQ +34%, SLS +11% and RDW +5% (which reached +36%
at its high).

**At his own signed 75% over 5 sessions it would have flagged not one alert we ever sent.** Over 20
sessions it flags two.

⚠ **Denominator note:** 183 HIGH alerts are readable here and 136 carry a settled 5-session outcome
in `mi_ep_missed_outcomes`. The 08-25 backtest quotes 173, which counts HIGH alerts with a settled
outcome *after* it additionally recomputed returns from bars where the table carried no row. A
different denominator, not a disagreement.

## 5. He is judging the DATE, not the ticker — the natural experiments

This is the part that generalises, and it is not really about extension.

| ticker | date | 5-session run-up | overhead volume | zones above | his verdict |
|---|---|---|---|---|---|
| AEHR | 2026-03-31 | 0.0% | 19% | 5 | **a real EP** (`must_not_miss_eps.py`) |
| AEHR | 2026-08-14 | 19.6% | 0% | 0 | **horrendous** |
| CAR | 2026-04-01 | 17.9% | 43% | 13 | **ok'ish** — the good version |
| CAR | 2026-04-21 | 53.8% | 0% | 0 | **horrendous** |
| CAR | 2026-04-22 | 80.4% | 0% | 0 | **horrendous** |
| MXL | 2026-04-21 | 47.2% | 0% | 0 | wrong day — *"3 tight days prior to the big gap on 4/24"* |
| MXL | 2026-04-24 | 30.4% | 0% | 0 | **the day he wants** |

- **AEHR is the clean case.** Same ticker, opposite verdicts, and both the run-up and the chart read
  separate the two dates the right way.
- **CAR is the case the chart read wins and the run-up loses.** The run-up barely moves across the
  three dates in daily-range terms; what collapses is the overhead — 43% to 0%, 13 zones to 0.
- **🔴 MXL is the case both lose.** The day he named as the setup is *less* extended than the day we
  scanned (30% against 47%) but still far enough along that any cutline reaching 8 of 11 kills it.
  A run-up filter cannot tell "extended and done" from "extended and about to gap 58%".

**Across all four rulings his pattern is one thing: the tradeable day is frequently not the day our
system evaluated** — earlier for CAR, later for MXL, not yet for ARQQ (*"decent, but still within
bottoming base"*). Our scanner judges a name on the day it gaps. That mismatch, not the supply read,
is where the signal is.

## 6. How much of this could be fitting — say it plainly

**The headline result is the one part that is NOT fitted — that is exactly why it is the headline.
Everything else here is, and here is the arithmetic.**

- **The 8-of-11 at 75% over 20 sessions owes nothing to the labels.** The threshold is his, signed
  on 2026-08-22 on separate evidence. The window is one of four declared before any count was
  computed. Nothing was moved after a number was seen. ⚠ What IS a free parameter is **which of the
  four windows to quote**, and 20 is the one that wins — so read it as "one of four pre-declared
  windows worked", not as "the window was derived". The other three give 5, 7 and 9 of 11 (the
  60-session one reaches 9 but costs 2 of the 26).
- **Every ANCHOR-EP row is fitted and its 0-of-26 is forced, not measured** — the cutline *is* that
  population's maximum. Only those rows' of-11 counts are information.
- **The fitted version rests on one name.** ANCHOR-EP on the 5-session window is 11.9%, set by
  **SNDK alone**.
  Drop SNDK and the cutline falls to 11.1% and the count becomes **8 of 11 against 1 of 26**. A
  clean sweep one name from a miss is not a clean sweep. The unfitted 75%/20-session setting has
  real headroom instead — 62% is the highest any of the 26 reaches, 13 points under the cap.
- **The eleven are not one population.** Six are run-up cases the live gate already kills; two
  (CAR 04-21, AEHR 08-14) are milder run-ups below the cap and are the only genuinely new ground;
  **three — IPCX, YOU, QTTB — have no prior run-up at all** and are junk for reasons this read does
  not encode (IPCX is buried under 99.6% of its own volume; YOU and QTTB are a low score and a small
  market cap). So the run-up mechanism explains roughly eight of eleven, and a single count hides
  that.

## 7. 🔴 A measurement defect found on the way, unrelated to chart reading

**VEEE 2026-07-08 appeared in a "we rejected this and it ran +354%" sample. It gapped 4.1%** — prior
close 5.63, open 5.86, under our own 9% floor — **and closed that day at 4.64, down 21% from its own
open.** The +354% belongs to 2026-07-13, when it opened at 12.24 against a 4.82 close: a separate
event five sessions later. Verified from `mi_daily_closes`.

`mi_ep_missed_outcomes` measures forward returns from a date's open over the following sessions, so
a later unrelated explosion is credited to a date that had no setup. **Every "we missed this winner"
claim built on that table carries this defect.** Recorded in the fixture as
`NO_SETUP_ON_THIS_DATE`, not fixed here — it needs its own task and it is not a chart-reading
problem.

## 8. Limitations — read before citing any number above

1. **Eleven labels and twenty-six labels.** Every count here is a small-sample count. No confidence
   interval on 11 items is worth printing.
2. **The must-reject population is entirely names the live stack already rejected**, so no count
   above measures a change to anything we would actually have traded. §4's HIGH-alert row is the
   only test on admitted names and it has ten flagged items.
3. **The 26 real EPs are not a clean must-not-reject arm either**: 7 of them are already excluded by
   the gap floor (`BASELINE_DEBT`), so "v3 does not reject them" and "the system would admit them"
   are different statements.
4. **The chart read's `clear air` verdict is partly a label artifact.** IPCX reads 99.6% of volume
   overhead and is still "clear air", because that verdict consults only zones and gap vacuums. v3
   composes on the same three fields deliberately, and the limitation is inherited rather than
   fixed.
5. **`mi_daily_closes` starts 2025-07-21**, so a 20-session run-up is always computable but the
   whole-range measure is depth-limited in April.
6. **The 5-session and 20-session windows are not independent** — the same six extreme names drive
   both, which is why they return the same eight.

## 9. What this does and does not license

- **It licenses nothing.** No cutline is proposed, no gate is proposed, nothing is promoted out of
  shadow. The read is wired into nothing.
- **The finding:** 8 of his 11 junk charts can be rejected without touching any of the 26 real EPs,
  at his own signed 75% threshold — but the thing that does it is the **extension rule we already
  have, read over 20 sessions instead of 5**, not a chart read. The chart read changes no verdict on
  any of the 11. And the live stack already rejects all 11 anyway, so nothing here would have
  changed a single trade.
- **The one thing worth keeping from the chart read** is that it separates CAR 04-01 from CAR
  04-21/22 where the run-up number does not — overhead supply collapsing from 43% to 0% is his
  "where in the move" distinction, encoded. N = 1, and it is on the admit side.
- **Two forks are his, and both are detection criteria (THE LINE) — neither is proposed here.**
  First, narrow: **the extension gate's lookback window** — 5 sessions today, and 20 sessions would
  have caught two more of his eleven at the same 75% cap with no measured cost on the 26. Second,
  and larger: **should we be scoring the DATE at all?** Every
  ruling he has given says the tradeable day is often not the day the name gapped — earlier for CAR,
  later for MXL, not yet for ARQQ. Our scanner has no way to say "not this day, that one."
- **Action for him: none required.** Nothing is waiting on a decision unless he wants the date
  question opened.

## 10. Reproduction

- Measure: `scripts/probes/_structure_read_v3.py` — imports the v2 supply read unchanged, adds the
  run-up family and the composition, imports `MAX_EXTENSION_PCT` from the live detector. No cutline
  has a default. Read-only, $0.
- Study: `scripts/probes/_srv3_study.py` → `scripts/probes/_srv3_out.txt` (full output, captured
  once, read many).
- Labels: `tests/fixtures/must_not_trade_charts.py` — 15 operator rulings on (ticker, date) pairs
  across five verdicts, with his verbatim words and the 2026-08-25 ruling date.
- Tests: `tests/test_structure_read_v3.py` — 18 cases pinning the live-gate replication (calendar
  window, fail-open, inclusive cap, imported constant), the run-up arithmetic, the IPCX label
  artifact, the no-cutline-default rule, and fixture-versus-bars drift.
- Captures: all pulled once by the 08-25 backtest and re-read here, never re-pulled —
  `_srbt_bars.psv.gz`, `_srbt_scanlog.psv`, `_srbt_outcomes.psv`, `_srbt_alerts.psv`.
