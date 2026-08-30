# Delayed-entry definitions — BASE and RECLAIMED PIVOT, specified to detector depth (#327)

> 🗂 **DELAYED-ENTRY CONTEXT LEDGER — READ FIRST: `docs/setups/delayed_ep_reentry.md § THE CONTEXT LEDGER`.** It carries the goal, every operator ruling, every study and its result, and the open questions. Two cards ran on this subject without it on 2026-08-29 and returned nothing new. Kept complete by `tests/test_delayed_entry_ledger_complete.py`.


**Date:** 2026-08-29 (PT) · **Status: DEFINITION + DETECTOR PROPOSAL — nothing built, nothing
flipped, no live behaviour changed.** · **Standard:** `docs/methodology/analysis_standard.md`
(§6 sections present; §1 questions answered in §0).

---

## §0 · The decision this serves

**Operator's ruling, 2026-08-29, verbatim:**

> *"day 2 shouldn't use any ORB entry, delay entries always look for some base and/or reclaim
> pivots; not just day 2, it's day 2+ can be any subsequent days up to a point."*

1. **What decision does this serve?** An opening range is a day-1 construct, and every delayed
   entry candidate specified so far still prices off one — §4a of
   `docs/roadmap/ep_profitability_program.md` has DE-1 buying the standing ORB high with an ORB-low
   stop, DE-5 buying the re-trigger day's first-5-minute high, and DE-6 sweeping a day-2 ORB stop.
   This ruling replaces that pricing basis with **structure**: a base, or a reclaimed pivot. Until
   "base" and "reclaimed pivot" are precise enough to detect from stored bars, no delayed-entry
   replay can be built — this definition is the gate on everything downstream.
2. **What would change the decision?** Nothing here is an expectancy claim. The decisions this
   document sets up are (a) the operator's ruling on the two proposed buy/stop definitions, (b) his
   ruling on the staleness bound, (c) whether to extend the minute-bar backfill to forward days
   (the one real data gap, §5).
3. **What population answers it?** The 310 distinct HIGH alerts since 2026-04-13 (237 usable with
   ≥20 forward sessions of full daily OHLCV) for the staleness and fire-rate probes; four real EP
   names with forward minute coverage for the worked examples. Derivation in §7.
4. **What would make this wrong?** §6 (adversarial) is written against my own proposal: the
   junk-firing modes, the failed-move-vs-continuation ambiguity, and the criteria that measured as
   too strict or too loose on first contact with real charts.

**Vocabulary discipline:** everything below builds on the house's existing structural vocabulary —
`docs/methodology/pivots-and-stock-character.md` (a pivot locates the entry AND is the stop),
`docs/methodology/structure_model.md` (congestion = supply; held-not-touched), and the operator's
own words in `docs/methodology/operator_shared_notes.md` (HNGE/GH flat-base features 06-27, Bonde's
four consolidation dimensions 06-22, the MNTS two-fold U&R 06-11, MRNA's base-as-neglect 08-19).
No parallel vocabulary is invented.

---

## §1 · BASE — the post-EP continuation base

### 1a. What it is, in methodology language

After the EP day, the stock **stops going up and refuses to go down**: price moves sideways in a
flat, narrowing band that **holds the upper part of the EP move**, on volume that dries up day by
day. It is the HNGE shape transposed to the days after a gap: prior thrust → a flat horizontal
band, small range-bound candles, NOT trending, holding its level — with a **flat top that becomes
the breakout pivot**. In the supply-ladder model a base is a congestion zone the stock is
absorbing; holding it after the EP is the *"gapping up above key levels, holding, even pulling
back to not failing"* strength signal. Bonde's four dimensions (depth / duration / range /
volume, notes 06-22) are the sourced numeric skeleton.

A trader would point at: the flat shelf under the post-EP high, three to ten quiet days long.

### 1b. Detection criteria (daily bars, `mi_daily_closes`)

Anchors, fixed on the EP day: `pre_gap_close` (close of the day before), `EP_low` (EP-day low),
`ADR20` (mean daily range %, 20 pre-EP sessions). Running: `move_top` = highest high since and
including the EP day; the base window = every session after the current `move_top` day. Evaluated
each session; a new post-EP high resets the window (still in the thrust, not basing).

| # | criterion | PROPOSED value | source |
|---|---|---|---|
| B1 DEPTH | every base-day low ≥ `move_top − 0.30 × (move_top − pre_gap_close)` — the base holds the **upper third of the whole move** | 0.30 | Bonde "Upper Third Rule" (20–30%); outer bound taken |
| B2 ONE-STRIKE | ≤ 1 daily close-to-close drop of ≥ 4% inside the window | 1 strike, 4% | Bonde "One-Strike Breakdown Rule", verbatim |
| B3 FLAT | \|OLS slope of closes\| ≤ 0.25 × ADR20 per day — oscillating around a LEVEL, not drifting | 0.25 | operator flatness (HNGE: "flat, sideways… NOT trending") |
| B4 CONTRACT | mean true-range% of last 2 days ≤ 0.75 × first 2 days, OR last-day range ≤ 0.60 × ADR20 (ADR-relative NR day) | 0.75 / 0.60 | Bonde progressive tightening; ADR-normalised per the operator's 06-16 note ("absolute range fails") |
| B5 VOLUME | median base-day volume ≤ 0.50 × EP-day volume | 0.50 | Bonde volume dry-up |
| B6 DURATION | window ≥ 3 sessions (so the earliest daily-base entry is session 4+) | 3–20 d | Bonde 3–20, sweet spot 4–10 |

All six are **proposals for sweep**, not tuned values; §6 reports which ones mis-measured on first
contact.

### 1c. The buy and the stop (what makes it a SETUP, not a family)

- **BUY:** stop-buy just above the **base top** (the max high of the base window — the flat-top
  pivot). At minute grain: the first 5-minute close above the base top, volume ≥ 1.5× the base
  days' pace. No opening range anywhere in the price basis; the level is valid at any minute of
  any session inside the eligibility window.
- **STOP:** the **base low** (structural; the pivot serves both sides). Sweep alternative: the
  NR-day low (tighter, Bonde's basis). Never an ORB low.

### 1d. What it is NOT — the near-misses that must not trigger

- **A deep retracement wearing a sideways costume.** If the pullback sits below the B1 floor it is
  not "holding the gains" — it is a failed move being digested. B1 is the single biggest killer on
  the real population (§4) and that is correct behaviour.
- **A directional drift.** Dip → rise → rise counted as "tightness" is the exact garbage the
  operator flagged on 06-27 (*"no coiling in the structure itself"*). B3 exists for this.
- **A chainsaw.** Wild alternating 4%+ days with tight *closes* — the "drunken man walk". B2 + B4.
- **A 1–2 day pause.** A micro-swing is not a stable anchor (Gemini's 3–4-day-pause point, 06-27);
  B6. Day-2/day-3 entries belong to the reclaimed-pivot setup or to intraday timing (§6c), not to
  a daily base that cannot exist yet.
- **A base formed UNDER the EP-day low.** That is not a continuation base at all — the EP
  structure has failed; whatever forms down there is a fresh Family-A consolidation on a new
  footing, not a delayed EP entry.

---

## §2 · RECLAIMED PIVOT — the post-EP undercut-and-reclaim

### 2a. What it is, in methodology language

A **pivot is any reasonable reference point for risk management: it locates the entry (the
reclaim) and it IS the stop** (`pivots-and-stock-character.md`, verbatim). Post-EP, the market
demonstrably referenced: the **gap-day low**, the **rising short moving average** the name's own
character respects, a **completed base's low**, a **post-EP swing low**. The setup is the MNTS
shape: pullback on contracting volume **loses** the reference — the undercut is the ARMING event,
not invalidation — then price **reclaims it decisively on expanding volume**. The reclaim is the
entry; the washout low is the stop; the U&R paradox is that the scariest-looking moment carries
the tightest honest risk, with the prior structure as cushion. Two pivots resolving in one move
(MNTS's 21EMA + gap-day low) upgrade quality.

### 2b. Detection criteria (daily bars; minute bars refine the trigger)

**Pivot inventory per name-day (computable tier only, v1):**

| pivot | level | qualification |
|---|---|---|
| P1 gap-day low | `EP_low` | always live from session 1 |
| P2 short MA | SMA10 (sweep: SMA20 / 21EMA — per-stock character picks ONE per name later) | valid only once its full lookback is post-EP (session ≥ 10 for SMA10) — an MA still averaging pre-gap prices is not a level the market used (§6, AMLX) |
| P3 base low | low of any completed VALID base (§1) | from base completion |
| P4 swing low | a post-EP daily low with 2 higher lows on both sides | from confirmation |

**State machine per pivot:** `HELD` → `LOST` (daily close < pivot; the intraday-touch variant is
the same-day U&R, below) → `RECLAIMED` (daily close back above the pivot) — subject to:

| # | criterion | PROPOSED value | why |
|---|---|---|---|
| R1 RECLAIM LAG | reclaim within ≤ 5 sessions of the loss | 5 (sweep 3–8) | measured: of 148 EP-low reclaims, median lag 2, p75 6 (§3); a reference under water for weeks is no longer a reference |
| R2 VOLUME | reclaim-day volume > mean volume of the pullback days | ratio > 1.0 (sweep 1.0–1.5) | MNTS: "the volume signature IS the confirmation"; contraction down, expansion back |
| R3 PROXIMITY | entry price ≤ pivot + 1.0 × ADR20-of-price | 1.0 ADR | a gap THROUGH the pivot is a new event, not a reclaim (QURE 06-17, §5) |
| R4 ATTEMPTS | stop watching a pivot after 2 failed reclaims (reclaimed then closed back below within 2 sessions) | 2 | a level that keeps failing has changed sides |
| R5 CONTEXT | reclaim-day close must not sit below BOTH falling SMA10 and SMA20 | — | the VERA class — chop back above a few days' range, still deep in a downtrend, is not strength |

### 2c. The buy and the stop

- **BUY:** at minute grain — the **first 5-minute close back above the pivot** with R2 volume
  running; at daily grain (the fallback where minute bars are missing) — the reclaim day's close.
  The daily-grain fill pays real slippage against the pivot (QURE: +8.3% worse, §5) — the minute
  trigger is where the R lives, which is why the forward-bar gap in §5 matters.
- **STOP:** the **washout low** — the lowest low printed while the pivot was lost. Structural,
  tight, and honest: if the washout low goes, the reclaim was false.
- **Same-day U&R variant:** intraday low undercuts the pivot but the day closes back above it
  (TEAM sessions 12–13, §5). Entry = the reclaim close (minute grain: the 5-min close back above);
  stop = that day's low.

### 2d. What it is NOT

- **A reclaim of a level that never mattered.** The reference must be demonstrable — the gap-day
  low, a qualified MA, a completed base low, a confirmed swing low. P2's qualification exists
  because a lagging SMA10 still contaminated by pre-gap closes produced a mechanically-true,
  economically-meaningless "U&R" on AMLX session 8 (§5).
- **A gap through the pivot.** QURE 06-17 "reclaimed" its lost EP low with a +60% buyout gap —
  mechanically a reclaim, actually a brand-new EP. R3 vetoes it; the delayed-entry frame does not
  apply to a fresh catalyst.
- **A dead structure coming back weeks later.** R1. A reclaim after 6+ sessions under water is
  Family-A consolidation territory (the 08-16 measurement: 81% of 20-day-window reclaim names were
  already on the Family A detector).
- **A quiet-volume reclaim.** Drift back above the level on shrinking volume is the pullback
  continuing, not demand returning. R2 (46 of 92 population reclaims failed it, §4).
- **The Nth attempt.** R4.

---

## §3 · The staleness bound — "up to a point", priced from the data

**He deliberately did not fix it. This is a RECOMMENDATION for his ruling, not a decision.**

Measured on the 237 usable HIGH alerts (40-session horizon):

| measurement | value |
|---|---|
| session of the 40-day peak high | median 12 · p75 26 (n=237) |
| **tail names (40d MFE ≥ +30% off EP close), peak session** | **median 19 · 54% by s20 · 77% by s30 (n=71)** |
| last session a NEW post-EP high is made | median 7 · p75 25 (n=237; 58 names never exceed the EP-day high) |
| EP-low pivot never closed below in 40 sessions | 44/237 (19%) |
| first close below EP low (the 193 that lost it) | median session 4 |
| reclaims of the lost EP low | 148/193; median lag 2 sessions; 100 within 5 |

The signal events cluster early — losses at ~session 4, reclaims ~2 sessions later, bases of 3–10
days complete inside two weeks — while the tail's PEAKS land at median session 19 and keep paying
into session 30. The entry must precede the run, not the peak; a window that chases session-25+
peaks is entering Family-A consolidation territory (the 81% overlap above), not a delayed EP.

**RECOMMENDATION: eligibility = session 2 through session 20 post-EP (~4 trading weeks),** with
structure ending it earlier than the calendar in most cases:

- **Hard invalidation:** EP low closed below and not reclaimed within 5 sessions (R1) → the EP is
  dead; stop watching. This retires most failures around week 2 on the measured distribution.
- **Hand-off, not cliff:** past session 20 a still-constructive name is a Family-A consolidation
  candidate — different universe, different owner, no EP-specific claim left.
- Sweep 15/20/25 in the replay; the bound is his call (THE LINE).

---

## §4 · Population fire rates — is either detector a firehose or a null?

Same 237-alert population, 20-session horizon, proposed constants as-is ($0, descriptive counts
only — **not** outcomes, which need the replay this document gates):

| detector | fired | notes |
|---|---|---|
| DB-1 daily base (B1–B6 all AND) | **9/237 names (4%)** ever show a valid base day; 8 buy-stops fill; resolution 4 up / 4 down (**n=8 — too few to judge, stated per standard §5**); 1 valid base never fills | criterion kill counts on basing days: depth 3,252 · strike 2,064 · flat 1,680 · contract 1,671 · volume 549 |
| DR-1 EP-low reclaim (R1+R2) | **92/237 names (39%)** produce a ≤5-session reclaim; 46 also clear R2 volume; 25 of those 46 make a new post-EP high within 10 sessions without re-losing the pivot | ~1 raw / ~0.5 vol-confirmed candidate per trading day over the window — attention-priced fine (P14 volume axis) |

Two honest readings:

- **B1 (depth) doing most of the killing is the definition working**, not a bug: the majority of
  post-EP "consolidations" in an alert population that mostly fails sit too deep to be
  continuation bases. That IS the failed-move class being excluded.
- **The 4%-fire AND-of-six is likely over-strict on the winners too** (§6b: on the worked
  examples it also refused TEAM's real base on one arm). The sweep must decide which arms are
  GATES and which are quality SCORES; candidates for demotion to score: B4-contract (measured
  refusing already-quiet bases for not contracting further) and B5-volume.

---

## §5 · Worked examples — the detectors run day-by-day on real EP charts

Full day-by-day tables: `/Users/alvinfung/.claude/jobs/6b173ac9/tmp/327_worked_out.txt` (probe
`327_worked.py`, reads only captured psv). Four names, chosen because they are the ONLY EP-family
names with forward minute coverage (§7): QURE (evidence-labelled ≥10R winner), TEAM (the
operator's own hand-done delayed entry), MRNA (his reference EP), AMLX (a live day-1 trade).

### QURE (EP 2026-05-29) — DR-1 textbook, including the honest loss

- s2 (06-02): closes 26.76 < EP low 27.59 → **P1 LOST**, washout 26.26.
- s3 (06-03): closes 29.88 back above, lag 1, **volume 3.3× the pullback's** → **DR-1 BUY,
  stop 26.26**. The MNTS shape exactly.
- s4: high 31.00; then fades — **stopped s7 at 26.26 = −1R.** Correct entry, honest stop, a loss.
- s5–s12: drifts under the pivot; R1 declares the structure dead at s11 (lag 6 > 5).
- s13 (06-17): the +60% buyout gap "reclaims" the pivot at 48.16 vs pivot 27.59 — **R3 vetoes**;
  that is a new EP, not a delayed entry. (QURE's famous ~15R was the buyout — no structure rule
  re-captures it, and pretending one does would be curve-fitting a takeover.)
- Grain note: 06-03 has no stored minute bars, so the daily-grain fill (29.88) pays +8.3% against
  the pivot vs a minute-grain reclaim fill (~27.6–28). The R difference between those two fills is
  the practical cost of the forward-bar gap in §8.

### TEAM (EP 2026-08-07) — the staircase: no ORB anywhere, and the composite fires

- s1–s9: new post-EP highs almost daily — **no base can form (window resets), no pivot lost.
  The detector correctly offers NOTHING to chase.**
- s10–s13: first real rest, 168–176 band. Daily base forms but fails B3/B4 on the wide s12/s13
  shakeout days.
- s12 (08-25): intraday undercut of qualified SMA10 (session 12 → P2 valid), closes back above →
  **same-day U&R: entry 166.49, stop 165.10 (day low).** s13 undercuts deeper → **−1R.** Thin
  washout stops on shallow undercuts stop easily — the #270 lesson that **re-entry discipline is
  load-bearing** (one-shot U&R was −1R there too).
- s13 (08-26): deeper undercut to 160.96, closes 168.47 back above SMA10 → **re-entry: 168.47,
  stop 160.96.** s14 (08-27): +10% day to 185.73 = **+2.3R MFE, +2.28R at the close.**
- The buy-the-base-top variant (176.00, stop 160.96) also fills s14, +0.65R at the day's high —
  same move, wider structural stop, smaller R. Both price off structure; neither touches an
  opening range.

### MRNA (EP 2026-08-19) — the reference EP, and the right answer is NO ENTRY (so far)

- Move: 62.96 → 176.66 (+125%). B1 floor = 142.55.
- s1–s7 (through 08-28): pulls to 128–133, multiple ≥4% down closes, closes 137.99 — **below the
  B1 floor with 2+ strikes. No valid base; DB-1 offers nothing.** P1 (114.46) never undercut →
  DR-1 armed but silent.
- This is the definition doing its job on the most important chart we have: a 42% retrace of the
  move with repeated 4% breakdowns is not yet a continuation base — under Bonde's own rules the
  accumulation structure is broken until proven otherwise. If MRNA later holds a flat shelf above
  ~142 or undercuts/reclaims a qualified pivot, the detectors arm again inside the window.

### AMLX (EP 2026-08-18) — two vetoes earning their keep

- s1–s3: new highs to 41.14. s4–s7: quiet 36.5–39.4 rest — passes depth/strike/flat but fails
  B4-contract (the early rest days were ALREADY quiet; there was nothing left to contract —
  the measured over-strictness named in §4/§6b).
- s8 (08-28): breaks down through the B1 floor (34.74 < 35.23) → **base VOIDED on the breakdown
  day** — correct, and had a looser B4 admitted the s6–s7 base, its buy-stop above 38.23 would
  simply **never have filled**: the stop-buy-above-the-top mechanic is itself the last line of
  defence against down-resolving bases.
- Same day, a mechanically-true "SMA10 U&R" fired — against an SMA10 still averaging two pre-gap
  closes near $21, i.e. a level no one in the market was using. **P2's qualification rule exists
  because of this row.**

---

## §6 · Adversarial — what makes these detectors fire on junk

### 6a. The intraday base CANNOT stand alone — measured, and this demotes DE-2

On the 30 covered forward days of the four worked names, a bare tightness scan (≥30 min of 5-min
bars, range ≤ 0.25×ADR20, low above EP low, then a 5-min close above the window high) fired on
**28 of 30 days**. Adding location gates (base top in the upper quarter of the day's range +
tested flat top + 1.5× volume on the break) still fired on **15 of 30** — and of those 15 fires,
6 stopped the same day, only one exceeded +2R intraday (TEAM 08-13), and 12 of 15 closed the
session below the entry (`327_intraday2_out.txt`; n=15, descriptive). **A liquid stock offers a
"tight base then break" on half of all afternoons.** This is the RMV/DOCU lesson at 5-minute
scale: tightness is direction-agnostic and near-ubiquitous; structure must be the gate and
tightness only the timing. Consequence for §4a: **DE-2 (intraday base as a standalone setup) is
demoted to the minute-grain TIMING component inside DB-1/DR-1** — used on a reclaim day or a
base-break day to place the entry, never to generate the day.

### 6b. Where the proposed numbers mis-measured on first contact (named, for the sweep)

- **B4-contract refuses already-quiet bases** (AMLX s6–s7; TEAM s13) because "contract further"
  is unsatisfiable when the rest starts quiet, and a U&R shakeout day legitimately widens the
  last-2-day range. Sweep: measure contraction vs the FIRST post-thrust days or drop to a score.
- **The AND-of-six fires on 4% of the population** — selective enough to be a null risk on the
  winners (P1 recall outranks precision). The sweep must check every known winner's post-EP path
  before any arm is kept as a hard gate.
- **Shallow-undercut washout stops are thin** (TEAM s12: 1.39 risk → next-day noise stops it).
  Sweep a stop floor (e.g. max(washout low, entry − 0.75×ADR)).

### 6c. Pre-continuation base vs failed-move base — can they be separated?

**Partially, ex-ante; fully only by the break — and the entry mechanics already encode that.**
What IS separable before resolution, on the measured population: **WHERE the rest sits** (B1 —
upper third of the move vs below it; the single biggest killer, and MRNA/AMLX show it reading
real charts correctly) and **whether the EP-day low is held or lost-unreclaimed** (44/237 never
lose it; 100/193 reclaim within 5 sessions — three distinct populations). What is NOT separable
ex-ante: a base that satisfies every criterion and then resolves DOWN — consolidation before
continuation and consolidation before failure are identical until they resolve. That is a
finding, not a failure, and the design absorbs it: **the buy is a stop order ABOVE the flat top
(or the reclaim close above the pivot), so a down-resolving base never fills**; the residual
exposure is the false break, which is what the washout/base-low stop prices. The 4-up/4-down
fill split at n=8 says nothing yet either way — the replay this document gates is what measures
it.

---

## §7 · Method / population

- **Staleness + fire-rate population:** distinct `mi_ep_alerts` HIGH alerts 2026-04-13 → 08-28
  (n=310), joined to `mi_daily_closes` −10/+60 calendar days; usable = ≥20 forward sessions with
  full OHLCV (n=237). Captures: `327_q4_out.psv` (13,813 rows); probes `327_probe.py`,
  `327_poprate.py`; outputs `327_probe_out.txt`, `327_poprate_out.txt` — all under
  `/Users/alvinfung/.claude/jobs/6b173ac9/tmp/`, captured once, read from file.
- **Worked examples:** `327_q2_out.psv` (daily, 7 tickers from 2026-02-01), `327_q3_out.psv`
  (22,245 minute rows: MRNA 08-19+, AMLX 08-18+, TEAM 08-07+, QURE 05-29→07-24).
- **Era caveat (standard §2):** the 237 alerts were admitted by the FLOORS OF THEIR DAY (10%
  era mid-May→mid-Aug etc.). For measuring when post-EP structure events happen this is
  acceptable — the events are properties of post-gap price paths, not of the admission rule —
  but the eventual replay must run on the re-derived backtest population
  (`ep_backtest_spec_2026-08-29.md` §2), not on this one. `mi_daily_closes` O/H/L begin
  2026-04-25; earlier rows lacking them were dropped by the usability filter.
- All prod access SELECT-only; $0; nothing written to prod.

## §8 · Detectability audit — computable today vs not

| ingredient | computable today? | detail |
|---|---|---|
| All DAILY-grain legs of B1–B6, R1–R5, P1/P3/P4, ADR20, staleness window | ✅ 100% | `mi_daily_closes` full coverage (O/H/L from 2026-04-25) |
| P2 MA pivots | ✅ | recompute from `mi_daily_closes` at $0 (do not depend on `mi_stock_scores` top-2,400 sector cap) |
| EP-day anchors (EP low, EP-day volume, pre-gap close) | ✅ 97% at minute grain, 100% daily | yesterday's backfill: 4,334/4,453 gap≥9% ticker-days have the 09:30 bar |
| **Minute-grain triggers on day 2+** (5-min reclaim close, break-bar volume, intraday timing, same-day U&R fills) | ❌ **~15–21% only** | forward-day coverage for HIGH alerts, measured per session +1…+20: 66/309 at +1, 45/304 at +5, 33/237 at +20 (`327_q5_out.psv`). The backfill covered EP DAYS; the days a delayed entry actually fires on are mostly dark |
| Per-stock character (which MA THIS name respects) | ❌ not built | computable from daily history; `pivots-and-stock-character.md` implementation sketch — v1 uses SMA10 with the sweep naming the alternative |
| Structural-tier pivots (volume-at-price shelves, congestion zones) | ❌ not built | derivable from daily bars (structure encoder territory); v1 pivot inventory is the computable tier ONLY, stated as a scope limit not designed around |

**What closing the real gap takes:** extend the existing Alpaca fetcher (same machinery as
yesterday's 1.1M-row backfill; runs on apollo-execution or locally with paper keys) to sessions
+1…+20 for the ~310 HIGH alerts ≈ **5,900 ticker-days ≈ 2.3M bars, $0, hours of wall-clock**.
Without it, the replay can still run at daily grain on 100% of the population (entries at reclaim-
day closes / next-day fills) — but §5's QURE row shows the daily-grain fill can cost most of the
edge, so daily-grain-only results would systematically UNDERSTATE both setups.

## §9 · What this does not answer

- **Whether either setup makes money.** No expectancy, no R distribution, no win rate is claimed
  anywhere here — that is the replay this definition unlocks, and it needs the forward-bar
  backfill plus the re-derived population to be honest.
- **The right constants.** Every threshold is a sourced proposal; §6b already names three that
  measured wrong on first contact. The sweep decides, against known winners first (P1).
- **Which MA is "the" pivot for a given name** — per-stock character is real
  (`pivots-and-stock-character.md`) and unbuilt; SMA10 is a v1 stand-in.
- **Structural-tier pivots** (congestion shelves) — out of v1 scope, named not designed-around.
- **Whether a base that passes everything resolves up** — not knowable ex-ante (§6c); the entry
  mechanics price it, the replay measures it.
- **Anything about same-day (day-1) delayed entries** — DE-1's reclaimed-floor case is day-1 and
  ORB-based; it is outside this ruling's day-2+ scope and untouched here.

## §10 · ⚖ THE LINE

Entry discipline is the operator's sole authority. This document defines and proposes; it changes
no live behaviour, flips no toggle, ships no detector. The two buy/stop definitions, the
staleness bound, the demotion of DE-2, and the forward-bar backfill are all HIS calls; nothing
proceeds to shadow, paper or live without his sign-off + CHANGE_PROCESS.
