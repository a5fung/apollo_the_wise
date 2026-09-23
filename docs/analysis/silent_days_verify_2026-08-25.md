# Did we throw away a real EP on either silent day? (2026-08-24 and 2026-08-25)

**MEASUREMENT ONLY. Nothing was changed. No rule, threshold, filter, toggle or trade state was
touched. Nothing here is a recommendation — every change this implies is the operator's fork
(THE LINE).** This is the P14 recall audit: over-admission is visible, under-admission is not,
so silence is only acceptable when it is *earned*.

## The answer in one line

**No. Not one of the 27 name-days rejected across the two days looks like a real EP** — every
single one is far outside the liquidity profile of the 26 operator/evidence-labelled real EPs,
and the three that come closest were each stopped by a rule that was doing exactly its job.

## The one number that settles it

Re-derived from `mi_daily_closes`, on one basis, for the 26 labelled real EPs in
`tests/fixtures/must_not_miss_eps.py` and for every rejected name:

| | median 20-day dollar volume | thinnest member | ATR-14 range |
|---|---|---|---|
| **The 26 labelled real EPs** | **$309M/day** | **$38.9M/day** (QURE) | 2.4% – 13.0% |
| The 27 rejected name-days | $7.8M/day | $0.25M/day (PMI) | 0.9% – 57.6% |

**24 of the 27 rejections sit below the thinnest real EP we have ever labelled — most by 10× to
1,000×.** Only three land inside the labelled band at all (FLNC $80M, MAIR $48M, CAPR $40M), and
all three are treated individually below. Every one of the 26 real EPs clears both the $1M
dollar-volume floor and the 15% ATR cap; the gates that did the most killing on these two days
have never touched a labelled real EP.

**This is not circular — the source population was never liquidity-screened.** The 26 are the
≥10R subset of 78 "tier-A tail winners" selected purely on forward move (≥8×ADR from the close,
20-day forward, ETF-clean), market-wide, with no liquidity or price filter
(`docs/analysis/winner_r_available_2026-08-16.txt`). That file reports median EP-day dollar volume
by R bucket for all 78: **$561M for the ≥10R group, $235M for 5-10R, $397M for under 5R.** Every
bucket of a market-wide winner screen — including the weakest — runs in the hundreds of millions a
day. Thin names had the chance to appear and did not dominate. (Different basis from the 20-day
median used above — EP-day dollar volume, inflated by the gap day itself — so read it as
corroboration of the order of magnitude, not as the same number.)

⚠ **SDOT is in that parent cohort, twice** (2026-06-08 and 2026-06-17, 5-10R bucket) — so a
sub-$2M/day name *can* produce a real tradeable tail move. What it has never done is appear in the
≥10R subset that defines a labelled EP. That distinction matters for SDOT on 08-24 (below).

## What was actually there

Both days were healthy at the scan: **38 ticks, 07:00 to 09:55 ET, no gaps, no null timestamps.**

| | rows in the scan log | killed by the two D-1 universe floors (sub-$5 / illiquid) | reached a real gate | graded (news read) | alerted |
|---|---|---|---|---|---|
| 2026-08-24 | 222 | 213 | **9** | 3 (SCTX, NSSC, AERO) | 0 |
| 2026-08-25 | 212 | 194 | **18** | 4 (APMD, IMTX, MAIR, NBBK) | 0 |

⚠ Two corrections to the framing this study started from: today reached **18** names past the
universe floors, not 8, and **4** were graded, not 1 (`ep_provenance_daily`, 10:05 ET:
"4 graded · 3 direct · 0 unknown").

### Which gate did the most work

Across the 27 name-days that cleared the universe floors:

| gate | names | thinnest / thickest of them, by dollar volume |
|---|---|---|
| $1M average dollar volume | **6** | $0.25M – $1.00M — all 39× to 156× below the thinnest real EP |
| $500M market cap | **5** | $2.0M – $39.7M |
| 15% ATR cap | **4** | $1.7M – $19.2M |
| score below the alert bar | **3** | $3.7M – $9.3M |
| pre-market share floor (25,000) | 2 | $3.6M, $9.9M |
| pre-market / session relative-volume floors | 2 | $7.8M, $18.7M |
| 60-day EP cooldown | 2 | $13.6M, $80.3M |
| M&A filter | 1 | $47.6M |
| routine grade + gap under 12% | 1 | $3.9M |
| extension cap | 1 | $12.0M |
| **upstream — real-time sustain rule** | **6 on 08-24, 0 net on 08-25** | see below |

⚠ **The sustain rule is the joint-largest single gate on 08-24 and it is invisible in the scan
log.** A live gap that fails to hold the 9% level for three consecutive bars is not admitted, and
on 08-24 it declined six names that ended the day with **no scan-log row at all** — RUM, USDE,
NXTT, CLF, SUJA, WBTN. On 08-25 it fired six times but declined nothing net: SPAI, WAFD, MEI,
IMTX, GRML and OESX all got rows at other ticks. Yesterday's study flagged this rule as costing
more on a thin board than it was measured to cost when it was signed on 08-02; this is the same
finding at name level. All six 08-24 declines are screened individually below.

**No liquidity or volatility gate killed anything institutional.** Every ADV, ATR and market-cap
rejection is at least 10× thinner than the thinnest labelled real EP. The only three names inside
the labelled band were stopped by the cooldown, the M&A filter and the market-cap floor.

## The margin on every rejection

Ordered by how close the name came. A gate that kills by 0.1% is a different conversation from one
that kills by 284%.

**2026-08-24** (the D0 bar is in, so the day's own outcome is shown; a full 5-session read is not):

| ticker | killed by | miss by | D0 open / high / close vs prior close |
|---|---|---|---|
| SCTX | score 60 vs bar 65 | **7.7%** | +4.8% / +14.0% / **+9.1%** |
| CAPR | mcap $466M vs $500M | **6.8%** | +27.7% / +27.7% / +8.1% |
| SDOT | ATR 16.2% vs 15% | 8.0% | +63.3% / +139.8% / **+75.7%** |
| NSSC | score 52 vs bar 65 | 20.0% | +21.2% / +35.9% / **−1.3%** |
| BBCQ | mcap $372M vs $500M | 25.6% | +4.3% / +10.0% / +7.6% |
| SUPX | mcap $368M vs $500M | 26.4% | +13.8% / +24.4% / +23.7% |
| HVII | ADV$ $600k vs $1M | 40.0% | +15.9% / +21.2% / +9.2% |
| JLHL | ATR 25.1% vs 15% | 67.3% | +6.4% / +6.5% / −4.4% |
| AERO | pre-market 3,037 sh vs 25,000 | 87.9% | +2.0% / +5.5% / +5.0% |

**2026-08-25** (no D0 bar yet — it lands tonight):

| ticker | killed by | miss by |
|---|---|---|
| **OESX** | ADV$ **$999,273** vs $1,000,000 floor | **0.07% — $727** |
| **CAPR** | mcap **$491M** vs $500M floor | **1.8% — $9M** |
| NBBK | score 60 vs bar 65 | 7.7% |
| WAFD | pre-market relative volume 0.68× vs 1.0× | 32.0% |
| HVII | ADV$ $607k vs $1M | 39.3% |
| GRML | ADV$ $533k vs $1M | 46.7% |
| SPAI | ADV$ $505k vs $1M | 49.5% |
| DTIL | mcap $233M vs $500M | 53.4% |
| MEI | session relative volume 0.33× vs 1.0× | 67.0% |
| PMI | ADV$ $249k vs $1M | 75.1% |
| APMD | pre-market 622 sh vs 25,000 | 97.5% |
| AMIX | ATR 32.5% vs 15% | 116.7% |
| DFNS | ATR 57.6% vs 15% | 284.0% |
| REAX | "already up 900% in 5 days" vs 75% cap | see the split note below |
| FLNC · KURA | 60-day EP cooldown | binary |
| MAIR | M&A filter | binary |
| IMTX | routine grade + gap under 12% | binary |

**SDOT closed +75.7% on 08-24 after the ATR gate cut it by 8%** — the largest single-day move
either day produced, and the honest caveat on this whole study. It is not a missed *EP*: at
$1.7M/day it is 23× thinner than the thinnest labelled real EP, it was already up 56% in five
days, and it opened +63.3%, so there is no ORB entry with sane risk. But SDOT is in the parent
tail-winner cohort twice, so "not an EP" and "not a big move" are different statements and only
the first one is being made here.

**The two razor-thin misses are both on names nothing like a real EP.** OESX missed the
dollar-volume floor by **$727** — but at $999,273 it is 39× thinner than the thinnest labelled real
EP, so the floor's *placement* is what excludes it, not the last dollar. CAPR at $491M missed the
market-cap floor by $9M; it is treated on its own below.

## The three names that are genuinely inside the real-EP band

### FLNC — the closest thing to a real EP on either day, and the cooldown is why it stopped

- Dollar volume **$80.3M/day**, ATR **8.3%** (the 26 real EPs run 2.4%–13.0%, median 7.3%), prior
  close $10.86, gap 9.8%. On every liquidity and volatility measure this is a well-formed EP shape.
- Killed by the **60-day cooldown**: it fired a HIGH alert on **2026-07-31**, 25 days ago, on a
  game-changer catalyst at a 10.02% gap.
- **We never read today's news.** The cooldown runs before catalyst grading, so FLNC has no row in
  `mi_catalyst_tier_shadow` — no rationale, no headlines, nothing. That is the honest finding for
  this name: it was excluded before anyone looked.
- The carve-out cannot reach it by construction: it needs gap ≥ 15% **and** an earnings day, and
  FLNC gapped 9.8%. The #170 re-setup shadow did not fire either, for the same reason — it also
  requires a ≥ 15% gap.
- **Verdict: not a demonstrated miss, but the one name where the rule made the call without
  evidence.** 25 days after a game-changer alert on the same ticker is squarely what the cooldown
  was built to suppress. Whether a fresh 9.8% gap 25 days later should be re-read rather than
  binned is a criteria question, and therefore the operator's — stated as evidence, not a proposal.

### MAIR — the only institutional-liquidity name a filter killed before scoring

- Dollar volume **$47.6M/day**, ATR 6.8%, prior close $24.97, gap 15.0%. Inside the labelled band.
- Killed by the **M&A filter**, via the Claude classifier path (`mna_filter_fired: MAIR via
  claude_classifier`).
- **MAIR is the acquirer, not the target.** Its own stored rationale says so: "MAIR acquiring
  ebm-papst"; the news summary says "its announced acquisition of German airflow specialist
  ebm-papst"; the 8-K is a $2.25B private placement funding the equity portion of that purchase.
- The acquirer veto (#416 R6 Guard C, `text_implies_acquirer_or_completed`) **did not recognise it**
  — re-run offline against MAIR's three stored texts, it returns `False` on each and on all three
  together, so the classifier path fired unopposed. The #284 `title_implies_acquirer` work guards
  the headline path; this name came through the grade path.
- **Verdict: not a real EP on the merits** — a $2.25B dilutive placement issuing 90.1M new shares is
  an overhang, and the grader's own words are "the market already treated [it] as a negative
  overhang rather than a clean momentum catalyst". But the *route* to that verdict was wrong, and
  the same gap would suppress an acquirer whose deal genuinely is a repricing catalyst. Evidence,
  and the fork, for the operator.

### CAPR — the $9M market-cap miss, and a basis question underneath it

- Dollar volume **$39.7M/day** (just above the thinnest labelled real EP at $38.9M), but prior close
  $6.80 — **below the cheapest real EP we have labelled** ($10.62) — and ATR 14.75%, above the
  ATR of all 26 and one quarter-point under the cap.
- Rejected on both days, and **the market cap the gate read is prior-close-based**: $466M against a
  $6.29 prior close on 08-24, $491M against a $6.80 prior close on 08-25 (about 72M shares both
  times). Priced at today's +15% gap, CAPR is roughly **$565M and clears the floor by 13%**.
  Whether the floor should read the pre-gap or post-gap cap is a criteria question — surfaced, not
  proposed. (The cache is not stale: the value moved day to day with the price.)
- **Never graded** — the market-cap gate also runs before catalyst classification, so there is no
  catalyst read for CAPR either.
- **Verdict: ambiguous, and named as such.** It has EP-grade liquidity and an EP-sized gap; it also
  has a sub-$10 price, the highest ATR of any name in the labelled band, and it round-tripped on
  08-24 (opened +27.7% at the day's high, closed +8.1%). It is the one name a reasonable person
  could argue about, and the argument is settled by the forward read on 09-02, not by judgement now.

## Names we never even logged: the upstream layer

`mi_ep_scan_log` is not the whole rejection set. Names declined in real time before the scan log
were pulled from `mi_audit_log` and screened against the same mechanical gates:

- **2026-08-24 — 6 names sustain-rejected, 4 shadow-caught, all screened.** The system's own
  watchdog flagged exactly one as a mechanically-clean miss: **CLF** (`ep_rt_live_miss`, 09:40 ET),
  dollar volume **$216.8M/day** — right at the labelled median.
  **CLF resolves cleanly and is not a miss:** its actual 08-24 bar opened at **+5.8%**, well under
  the 9% floor. It only touched +9.4% intraday and closed **+0.3%** — an intraday cross, not a gap.
  And it alerted on **2026-07-23**, 32 days ago, so the 60-day cooldown would have suppressed it
  anyway.
- **2026-08-25 — 6 sustain-rejected, 9 shadow-caught.** The three with real-EP-band liquidity:
  **ABCL** ($53.0M) alerted 15 days ago and is inside cooldown; **CRML** ($36.8M) and **HMN**
  ($11.9M) are both below the thinnest labelled real EP, and both real-time prints (09:45 and
  08:20) are outside the 09:31–09:45 ORB submission window, so a catch could not have been traded
  that morning regardless.
- Everything else upstream fails a mechanical gate outright: USDE 166% extended, NXTT 52% ATR and
  $619k dollar volume, DBGI 40% ATR, PSQH/SPAI/CLRO all under $510k dollar volume.

## Two data defects found while checking — neither cost us an EP

1. **REAX: the extension gate fired on a split artifact.** A reverse split was effective 08-25.
   The gate compared a split-adjusted prior close ($24, Polygon) against unadjusted 5-day-low closes
   in `mi_daily_closes` ($2.40) and got "already up 900% in prior 5 days". The real extension is
   **0%**. The system *detected* the split (`ep_rt_corp_action_hold`, `ep_rt_prev_close_mismatch:
   REAX prev_close alpaca 2.4 vs polygon 24`) but only **intraday on 08-25, by the real-time layer**.
   The path is now specific: the nightly split ingest at 08-24 17:00 ET applied 15 splits and
   detected 3 future ones (WHLR, KAPA, SOXX) — **REAX is in neither list**, and the two failures it
   did record are SCPFD and TKUNF, not REAX. So `mi_daily_closes` was never adjusted, the extension
   map read the raw table, and the gate compared an adjusted price to unadjusted history. A reverse
   split is not an EP catalyst, so nothing was lost here — but the same mismatch on a genuine gapper
   would be a silent exclusion.
2. **NBBK's 24.4% gap is very likely a phantom print.** The delayed feed held 24.4% while real time
   read **0.0%** at four consecutive post-open ticks; `ep_rt_tick_quality_reject` called it
   `stale_quote`. The grader independently found no fresh catalyst — the earnings beat is from a
   7/22 filing and the only recent item is a $43,500 insider purchase against a $986M market cap.

## The finding the operator most needs: the score rescale is what made both days zero

`mi_ep_score_shadow` records both scales for every scored name. Across the two days only three
names reached scoring, and **two of them flip**:

| date | ticker | new "separation" score vs bar 65 | old legacy score vs bar 70 | old outcome |
|---|---|---|---|---|
| 08-24 | NSSC | 52.5 → below | **80** | **HIGH alert** |
| 08-24 | SCTX | 60 → below | 42 | no alert |
| 08-25 | NBBK | 60 → below | **96** | **HIGH alert** |

**Under the pre-2026-08-22 scoring, each day would have produced exactly one HIGH alert and neither
day would have been silent.**

⚠ **An alert is not an entry, and the two differ here.** NBBK held legacy 96 from **08:55 ET**, so
it would have been in the 09:31–09:45 submission window — a tradeable entry. NSSC's legacy score
is recorded at **36 at 07:25 ET** and **80 at 09:50 ET**; its separation score sat flat at 60 for
every pre-open tick and only moved at 09:50, when the gap widened from 20.8% to 34.2%. The shadow
table keeps only the first and last value, so the crossing is not pinned — but on that evidence the
legacy HIGH arrived at **09:50 ET**, which is `WINDOW_OUT_OF_ORB`. So the legacy scale gives two
alerts across the two days and, most likely, **one** tradeable entry. The zero-alert pair is a direct consequence of the operator-signed
score rescale, not only of a thin tape. Yesterday's study
(`docs/analysis/alert_volume_collapse_2026-08-24.md`, limitation 2) said one day could not separate
noise from a side effect of the 08-22 batch and needed a second and a third; this is the second, and
the shadow table answers it directly.

**On the merits, the rescale suppressed the right two names:**

- **NSSC** opened +21.2%, ran to +35.9%, and closed **−1.3%** — it gave the entire gap back inside
  the session. An ORB entry would have been stopped out. Its dollar volume is $9.3M, four times
  thinner than the thinnest labelled real EP.
- **NBBK** is the phantom-gap name above: no fresh catalyst, real-time gap 0.0%, $8.5M dollar
  volume.

So the rescale is the gate that changed the outcome, and on the evidence available it changed it
correctly. **That is a statement of what the evidence shows, not a proposal to leave it or move
it** — the bar is the operator's.

## What this does NOT answer

1. **The five-day outcomes are not in.** This is the decisive evidence and it does not exist yet.
   08-25's D0 bar lands tonight; nothing beyond D0 exists for either day.
2. **The catalyst is unknown for 20 of the 27 rejected name-days.** The market-cap, ADV, ATR,
   cooldown, extension and relative-volume gates all run *before* catalyst grading, so those names
   have no `mi_catalyst_tier_shadow` row at all. For FLNC and CAPR in particular, "we rejected it
   before ever reading its news" is the literal state. This audit judged them on shape and liquidity
   because that is all the system recorded.
3. **The upstream layer is screened, not graded.** Names declined in real time were checked against
   the mechanical gates only. If one of them had a real catalyst, nothing in the system would show it.
4. **It says nothing about the days before 08-24.** Two days is two days, and the D-1 universe
   floors only started leaving a row on 08-22, so the same census cannot be run on earlier dates.
5. **The labelled real EPs are mostly names we never alerted on either.** The same source file
   records **0 of the ≥10R subset and 4 of all 78** as live-alerted. Recall against that cohort is a
   pre-existing, much larger question than two silent days, and nothing here measures it.
6. **It cannot prove the score bar is right.** It shows the bar changed the outcome on both days and
   that both suppressed names look wrong on the evidence available. Two names is not a calibration.

## How to settle this on evidence — exact re-read

Both tables refresh themselves nightly; **no ad-hoc query is needed, just read them on the date.**
`refresh_missed_outcomes` runs in the nightly scheduler job over a rolling 30-day window and
recomputes forward returns on every pass, so `ret_5d` fills in as the bars accrue.

- **2026-09-01** — read 2026-08-24 (its 5 sessions are 08-25, 26, 27, 28, 31; no holiday in the window):
  ```sql
  SELECT ticker, skip_category, gap_pct, ret_1d, ret_5d, max_high_5d
  FROM mi_ep_missed_outcomes WHERE alert_date = '2026-08-24' ORDER BY ret_5d DESC NULLS LAST;
  ```
- **2026-09-02** — read 2026-08-25 (sessions 08-26, 27, 28, 31, 09-01):
  ```sql
  SELECT ticker, skip_category, gap_pct, ret_1d, ret_5d, max_high_5d
  FROM mi_ep_missed_outcomes WHERE alert_date = '2026-08-25' ORDER BY ret_5d DESC NULLS LAST;
  ```
- **The names to look at first, in order:** CAPR (the ambiguous one), FLNC and MAIR (the two inside
  the labelled band), OESX and NBBK (the two 0.07%/7.7% misses), and SDOT (which closed **+75.7%**
  on 08-24 after the ATR gate cut it — a big move, but at $1.7M/day it is not an EP by any measure
  in the fixture, and the two things should not be confused).
- ⚠ **The upstream names will not appear in that table** — no scan-log row means no outcome row.
  CLF, HMN, ABCL, CRML, PSQH, NCTY, RUM, SUJA, WBTN, USDE, NXTT, DBGI, PTHS and FISI have to be read
  straight out of `mi_daily_closes`.

## Data

Three read-only production captures, pulled once and read many (cost rule), all under
`scripts/probes/`. No paid calls, no LLM regrades, nothing written to production.

- `_silentdays_capture.sql` → `_silentdays_capture_out.txt` — every scan tick and the deduped last
  state for both days, alerts, prior-alert/cooldown history, the catalyst-grader rows with their
  full rationale and headlines, the complete audit log for both days, 60 sessions of OHLCV for every
  scanned ticker, and the outcome/shadow/toggle tables. Free-text columns are emitted via
  `row_to_json` so embedded newlines and pipes cannot shred the delimiter.
- `_silentdays_capture2.sql` → `_silentdays_capture2_out.txt` — the upstream names that never
  reached the scan log, plus OHLCV for the 25 fixture tickers so the real-EP profile is re-derived
  from our own data rather than taken from a reason string.
- `_silentdays_profile.py` → `_silentdays_profile_out.txt` — the arithmetic. Dollar volume, ATR-14
  and extension are recomputed with the **same formulas the live gates use**
  (`backtester/filters.py::_check_adv_dollar_volume`, `compute_atr_14`, `ep_detector`'s extension),
  on bars strictly before the scan date, which is the set the 9:31 live path actually sees.
