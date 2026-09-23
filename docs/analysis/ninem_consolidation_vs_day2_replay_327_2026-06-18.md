# #327 — 9M Day-2 ORB vs consolidation-entry replay (the #326 directional read)

**Status: DIRECTIONAL READ COMPLETE 2026-06-18.** Replay-first (live forward-shadow cannot
reach decision-grade N by the accelerated #326 ~7/7 call). Symmetric two-arm replay over the
historical `mi_9m_day2_candidates` cohort settles realized R on BOTH entries on the SAME 9M
names, same harvest, same forward window. **Read (two claims, different strength): (A SOLID) the
9M Day-2 ORB entry earns NO robust edge — break-even/outlier-carried — which alone carries the
#326 RETIRE half; (B PROMISING, selection-inflated → Phase-B-gated) the consolidation
(tightness→expansion) entry is the better replacement candidate. Operator decision (#326).**

Harness: `scripts/_327_replay.py` (Phases 1+3) · `scripts/_327_pull_minute.py` (Polygon pull)
· `scripts/_327_dump.py` (per-name audit). Data: `_327_cohort.tsv` (121 rows), `_327_daily.tsv`
(27,380 daily bars), `_327_minute.tsv` (94,796 Polygon 1-min bars, 103/105 tickers).

## The #326 question

Should the 9M Day-2 ORB entry be RETIRED in favour of a consolidation entry on the same 9M
names? (`memory:user_pradeep_9m_universe_methodology` — "all 9M EPs enter the flag-detector
universe; entry comes from tightness→expansion", not the Day-2 ORB.) #326 was pulled to ~7/7 to
move fast; a replay is the only thing that yields a clear read in that window.

## Method (advisor-locked 2026-06-18)

Two arms, **both** settled through `anticipation.SETTLE_RULE` (+1R/+3R ½-½ scale-out, day-5
time-stop) over the same forward window, realized R via the day-0-minute scale-out +
daily trail (`anticipation.simulate` / `simulate_first5` / `build_mixed_path` — MFE-free; **no
daily approximation of the intraday entry**, the error the #270 arc closed):

- **ARM 1 — Day-2 ORB** (incumbent): entry day = alert_date+1; entry = break of the Day-2
  opening-range (first-5-min) high; **STOP = prior day's low** (the 9M breakout-day low — the
  live `prepare_9m_day2_orb_order` rule, NOT the ORB low). Skip if stop >15% wide.
- **ARM 2 — consolidation**: the 9M day is the runup anchor; after a coil (tight/quiet base —
  `find_consolidation_breakout`, reusing `TIGHT_RANGE`/`VOL_CONTRACT`), take the intraday
  FIRST5-break on the first base-high breakout day; **STOP = first-5-min OR low** (tight).

Guards against this project's documented failure classes (advisor):
- **Full-universe expectancy** — a no-fill / never-consolidates name scores **0R**, never
  silently dropped (vs conditioning Arm 2 only on "a setup formed").
- **Replay both arms identically** — do NOT pull historical Day-2 ORB outcomes (IEX-paper
  contaminated per the Gate-3 finding; different live exits). Same bars, same rule.
- **Outlier-decompose** (the W2 skip-wide-open lesson): report median + ex-top-3 + top-3 share.
- **Universe both ways** — 9M-anchored (the 9M event is the qualifier) AND runup-canary-gated
  (≥1.15), so the detection-criterion fork stays explicit.

## Cohort funnel (Phase 1, daily)

```
cohort N=121 / 105 tickers · alert_date 2026-04-21..06-17 · daily back to 2025-05-12
anchor (9M day) found        : 121/121
ARM 1 settleable (≥5 fwd bars): 109
ARM 2 consolidation set up    : 37/121 (31%)  · settleable 35   [9M-anchored]
ARM 2 consolidation set up    : 28          [canary-gated ≥1.15]
```

**Finding #1 — the consolidation entry is SELECTIVE (~31% of 9M names coil+break in 15d).** It
is therefore a *complement/filter*, not a 1:1 blanket replacement for Day-2 ORB. The canary gate
drops only ~9 marginal names (median set-up runup 1.21), so that fork is low-stakes.

## Head-to-head (Phase 3, realized R)

```
                              filled-only                          full universe (0R no-fill)
ARM 1 Day-2 ORB    n=36  median −0.24R  win 47%  +3.2R   |  n=109  mean +0.03R  win 16%
   robustness: top-3 = 190% of total, ex-top-3 mean −0.09R  → the bulk LOSES; edge is 3 outliers
ARM 2 consolidation (9M-anchored)
                   n=17  median +2.00R  win 82%  +25.0R  |  n=108  mean +0.23R
   robustness: top-3 = 24% of total,  ex-top-3 mean +1.36R  → BROAD, not outlier-driven
ARM 2 consolidation (canary-gated ≥1.15)
                   n=14  median +2.00R  win 79%  +19.0R  |  n=89   mean +0.21R

PAIRED (N=108 both arms evaluable): per-name wins  Day-2 17  ·  consolidation 29  ·  tie 62
                                    mean delta (consol−Day2) +0.20R/name

WITHIN-NAME (N=17 names where consolidation FIRED — the apples-to-apples cut):
   ARM 1 Day-2 ORB on those same 17 : median +0.00R  mean −0.08R  win 18%  total −1.4R
      (10 of 17 had no Day-2 trigger = 0R; ex-top-3 −0.25R)
   ARM 2 consolidation              : median +2.00R  mean +1.47R  win 82%  total +25.0R
   per-name wins: consolidation 14  ·  Day-2 3      within-name delta median +2.00R / mean +1.55R
```

**Finding #4 — the edge survives the subset confound (advisor catch).** The paired 29-vs-17 is
diluted by 62 tie-at-0R names; the load-bearing cut is *within-name*: on the SAME 17 names where
consolidation fired, Day-2 ORB returned **−1.4R** (net negative, 10/17 didn't trigger). So
consolidation is not merely winning on an easier subset — on identical names, the incumbent
Day-2 entry was a net loser. That said, those 17 are still the daily-close-confirmed breakout
days (caveat #1) — the within-name cut removes the *which-names* confound, not the *which-days*
optimism.

**Finding #2 — the consolidation entry has a real, broad-based edge where it fires; Day-2 ORB is
break-even/outlier-carried.** Consolidation: +2.00R median, 82% win, +25R total, and crucially
NOT outlier-dependent (top-3 only 24%, ex-top-3 still +1.36R). Day-2 ORB: negative median on the
filled set (−0.24R), and its small +3.2R total is *entirely* 3 outliers (top-3 = 190% of total,
ex-top-3 negative) — the W2 artifact shape, here flagging the INCUMBENT as fragile.

**Finding #3 — the mechanism is stop tightness (the U&R paradox), audited per-name
(`_327_dump.py`).** Same harvest rule; the difference is the stop. Consolidation entries carry
tight first-5-min-low stops (~0.8–3.5%: APP 533/514, F 13.25/13.14, TXN 281/279) so the +3R
rung hits and winners bank the +2.00R ceiling. Day-2 ORB's prior-day-low stop is wide (~6–14%:
DELL 307/265, BABA 141/130) so +3R rarely hits → mostly −1R / partials. 17 distinct winners, no
single-ticker concentration — not a settlement bug.

## Caveats (this is DIRECTIONAL, not a ship verdict)

1. **Breakout-day selection is daily-close-confirmed → an OPTIMISTIC bias in Arm 2.** The replay
   takes the intraday FIRST5-break only on days the daily close confirmed the base-high break. A
   live intraday entry-watch would also fire on days that break intraday but **close weak**
   (failed breakouts → mostly −1R on the tight stop), which this replay excludes. So Arm 2's
   **magnitude is upward-biased by an unquantified amount** — I do not know the size of the
   excluded failed-breakout population, so I am NOT putting a number on the de-rated edge (any
   such number would be invented). The clean +2/−1 winner shape is itself a *symptom* of this
   selection — strong-close days are clean directional runs by construction. Honest statement:
   **the direction may survive largely because the incumbent is so weak (Finding #2), not
   because consolidation's measured magnitude is trustworthy.** Closing this is the Phase-B job:
   test FIRST5-break on EVERY post-coil day (not only confirmed-close days) — runnable offline
   with a wider minute pull, and the forward-shadow's whole point. **→ DONE (Phase B below): the +2R
   was an entry-model artifact (daily-close selection + a 2%-sub-base tolerance) → consolidation drops
   into the same break-even/outlier bucket as Day-2 ORB; the real live #94 watcher is NOT evaluable offline.**
2. **Harvest CAPS the tail.** SETTLE_RULE banks ½ at +1R and ½ at +3R → winners cap at +2.00R;
   the fat tail (MNTS-class) is not captured. Deliberate "derisk fast" (#270). Both arms capped
   identically, so the comparison is fair, but neither arm's absolute R reflects tail capture.
3. **N is small** (17 consolidation fills, one ~2-month window) and in-sample. Read median +
   ex-top-3 (done), treat magnitudes as illustrative.
4. **Day-2 ORB replay uses a 5-min OR;** the live entry uses `get_first_bar` (1-min). A 1-min OR
   gives a slightly higher trigger / different stop distance — second-order vs the prior-day-low
   stop that drives Arm-1's weakness, but noted.

## Read for #326 — two claims of DIFFERENT evidential strength (do not weld them)

The decision splits into two claims; the *retire* half rests on the strong one.

- **CLAIM A (SOLID, self-standing) — the 9M Day-2 ORB entry earns no robust edge.** This needs
  nothing from Arm 2: filled median −0.24R, win 47%, and its only positive total (+3.2R) is
  *entirely* 3 outliers (top-3 = 190% of total, ex-top-3 negative); on the 17 names where
  consolidation fired it was net −1.4R. The wide prior-day-low stop is the mechanism. **This
  alone carries the RETIRE half of #326** — we are not displacing a positive base case.
- **CLAIM B (PROMISING but selection-inflated) — the consolidation entry is better.** +2.00R
  median, 82% win, broad (ex-top-3 +1.36R), within-name +2.00R delta — but the magnitude is
  upward-biased by the daily-close-confirmed breakout selection (caveat #1), unquantified.
  **GATE on Phase-B forward confirmation before any live sizing.**

So: the read supports **retiring/de-emphasising Day-2 ORB now** (Claim A), and **prioritising
the consolidation entry as the replacement candidate, shadow-first** (Claim B, confirmation-
gated). The accelerated #326 call asked for a directional read; this is it. GO is operator's.

**OPEN — a SCOPE call for the operator, not a data call:** consolidation fires on only ~⅓ of 9M
names. Retiring Day-2 ORB therefore *narrows the entered universe to that ⅓*. Claim A says the
other ⅔ weren't being profitably entered by Day-2 ORB anyway (so nothing of value is lost) — but
if #326 wants 9M names to retain *some* entry path, the ⅔ that never consolidate need a decision
(leave unentered / keep a de-sized Day-2 ORB for them / a different entry). Surface before cut-over.

## Entry-signal study (operator 2026-06-18) — is the entry timed by DEPTH or PERSISTENCE?

The operator's deeper question: instead of a fixed entry mode, what *signal* across the multi-day coil
times the best entry — combine RMV + range + volume + a **consecutive-day count** ("low RMV for 3
days") to detect the apex where expansion is imminent, then take the asymmetric bet (capture, or a
quick tight-stop loss). `scripts/_327_entry_signal.py` — a HYPOTHESIS TEST (advisor-hardened), NOT a
grid search: per-cell N visible (●=n<10 not read), baselines **stop-matched** (the #270-Step-0 trap was
that an RMV edge was a STOP artifact), entry scored on **capture-rate + UNCAPPED MFE/risk** (the harvest
buries good entries), one fire per name (first N-consecutive-tight run, close-of-Nth, no reenter).

```
tight day = rmv_5d≤30 & range≤5% & vol≤1.0×ADV20 ;  capture = MFE hits +3R before the stop
COUNT CURVE (read DOWN = stop FIXED, so the count effect is NOT a stop artifact):
            coiled_low stop            structural stop
  N=1   32% cap · 67% st · +0.8R · n65    32% · 67% · +0.8R · n65
  N=2   42% cap · 57% st · +2.0R · n45    37% · 55% · +1.6R · n45
  N=3   44% cap · 56% st · +2.1R · n25    44% · 52% · +2.1R · n25   ← the sweet spot
  N=4   ●33% · 66% · +0.4R · n9 (NOISE)   30% · 60% · +0.3R · n10
TREND gate (N=3, structural): flat-tight 44%/+2.1R/n25  vs  +contracting ●37%/n8 → trend does NOT add
```

**Finding — the entry signal is PERSISTENCE, not DEPTH.** Requiring **3 consecutive tight days** (vs a
single tight day) lifts the +3R-capture rate **~32% → 44%** and median uncapped MFE **+0.8R → +2.1R**,
**stop-matched** (monotone N=1→3 at BOTH the coiled-low and structural stops, so it is not the
#270-Step-0 stop artifact). This RECONCILES with #270-Step-0: the RMV *level* (how deep the contraction)
does NOT sort entries — it inverts via the stop — but *how long it has been tight* (the count = coil
maturity) DOES. The range-**contraction trend** added nothing here (and shrank N below the floor); the
**count** carries the signal. N=3 is the readable sweet spot (N=4 collapses to n≈9 = noise).

**Robustness sweep (one knob at a time, stop-matched, Δ = N3−N1 capture%):** the count effect is
ROBUST across RMV (Δ+10/+12/+9pp at rmv≤20/30/40 — not an RMV≤30 spike) and across the looser range/vol
settings (range≤5% Δ+12, range≤**7% Δ+15pp @ n=45** = strongest/largest, vol≤1.0 Δ+12). It VANISHES at
the OVER-TIGHT level gates (range≤4% Δ0; vol≤0.7 Δ+1, non-monotonic/noisy). That pattern is the deeper
confirmation of persistence-not-depth: **tightening the *level* gate kills the count effect** — the strict
gate over-selects and starves the count of the marginal days it filters. So the **count is the lever; the
level gates just define the candidate pool and must NOT be cranked tight.** Robust region = a LOOSER level
gate (range≤5–7%, vol≤1.0, rmv≤30–40) **+ N=2–3** (best/largest read: range≤7% / N=3 → 44% cap / +2.8R / n45).

**Caveats (the discipline — this is a hypothesis, not a ship):** N≈77, in-sample, one window → the
deliverable is the *shape* (count adds, monotone to N=3, robust across two stops) + the *region* (N=2–3),
NOT a tuned cell. MFE/capture is ENTRY QUALITY (uncapped) — it says the entry POSITIONS you for a +3R
expansion 44% of the time, NOT that you realize +3R (the harvest caps that — separate decision). The
cross-stop comparison is confounded (a +3R target is a bigger move under the wider ATR stop → its low
capture% is a target-unit artifact, not "ATR is worse") — so this study claims the COUNT effect only,
not a best stop. **The forward shadow validates the N=2–3 region; it does not ship from here.**

## The 3-mode rerun (operator 2026-06-18) — ARM 2 was only ONE of three consolidation modes

**Correction (operator catch):** the original ARM 2 (and the Phase-B caveat-#1 work below) tested ONLY
the **Confirm/FIRST5** entry — buy the confirmed base-high breakout. Family A (ADR 0013) has **three**
entry modes that differ only by WHEN you enter: **Anticipate** (in the coil, BEFORE the break, stop =
tight-range low), **Confirm/flag** (on the breakout), **U&R** (undercut→reclaim). The one we're building
is **Anticipate**, which the prior replay never tested. This section reruns it. (`scripts/_327_anticipate.py`
— ports the advisor-hardened `_270_anticipation_replay` machinery [`find_coiled_days` + `simulate_reenter`
+ `realized_net` + the maturity sweep] WHOLESALE, re-anchored from the Family-B gap_day_low to the 9M-day
anchor. Survivorship-honest [universe = every coiler, breakout or not] + the maturity sweep [the 6/14
verdict was maturity-dependent].)

### ANTICIPATE arm — result (9M cohort, DIRECTIONAL, small-N, in-sample)

```
COMPLEMENTARITY : 77/121 (64%) of 9M names form a coiled day (min_base=1); 31 later confirm a breakout,
                  46 NEVER do (the false-anticipation COST set, kept). The other 36% are fast runners
                  Confirm/FIRST5 must cover → the modes are complementary, not substitutes.
PRICE-CAPTURE   : winning anticipate close enters a median 2% BELOW the FIRST5 price = 19% of the run to
                  the window high captured earlier (N=19). REAL but MODEST (6/14 delayed-EP saw 6%/25%).
REALIZED (full universe, 77 coilers, harvest == Confirm's SETTLE_RULE +1R/+3R/5d):
                  median −1.0R · mean −1.2R · win 23% · total −91R · ex-top −1.5R  → NEGATIVE.
MFE ceiling     : +2.2R mean (the fat tail: CNC +70R, HUT +26R MFE) — perfect-foresight, NOT realized.
MATURITY SWEEP  : caught/coiled 27%/27%/25%/15% across min_base 1→4 — maturity does NOT rescue it here
                  (unlike the 6/14 delayed-EP cohort where min_base=3 flipped the verdict).
```

**Read (anticipation on its OWN yardsticks, not just R):** price-capture + complementarity are REAL but
the 9M-cohort numbers are weak — modest 2% capture, and **realized expectancy is NEGATIVE (−1.2R)**,
dominated by the **60% false-coil set** (46 of 77 coilers never break out → repeated −1R shakes the
captures don't pay back). Worse than the 6/14 delayed-EP result (≈0R) precisely because the 9M cohort
coils more but confirms less.

**The load-bearing caveat — harvest sensitivity.** The MFE ceiling is +2.2R but realized is −1.2R: a
**3.4R/name collapse driven entirely by the derisk-fast harvest** (banks ½ at +1R / ½ at +3R, 5-day stop)
capping the fat tail anticipation exists to catch (CNC +70R MFE → ~+2R realized) AND the runner half
giving back. So the negative realized is **as much a statement about the exit rule as about the entry** —
a tail-capturing exit would change this number (for ALL modes, equally). The cross-arm comparison stays
fair (same harvest), but no mode's absolute R reflects tail capture.

**Net for #326:** of the modes tested so far — Day-2 ORB ≈0, Confirm de-rated to break-even (Phase B),
Anticipate −1.2R realized / price-capture+complementarity its real (modest) value — **none shows a clean
standalone realized edge on the 9M cohort in-sample under the derisk-fast harvest.** They are
complementary by design. U&R untested. The forward shadow (all modes tagged by mode, ADR 0013 Phase 3) +
the exit-rule question are what actually settle it — not this replay.

## Phase B — offline caveat-#1 correction (DONE 2026-06-18) + the live-wiring bridge

The offline half of Phase B re-times Arm 2 to the entry a LIVE watcher actually gets — the FIRST
post-coil day whose first-5 OR breaks the *as-of* coil base — instead of the daily-close-confirmed
day the Phase-A replay used. `scripts/_327_replay.py` (extended; `consolidation_scan` exposes every
post-coil day with its as-of base_high; the Phase-A confirmed-close numbers stay byte-identical) over
a wider 266-day minute pull (incl 147 post-coil days). Both timing arms harvested identically
(SETTLE_RULE), only the entry DAY differs — the delta is the daily-close selection bias.

```
CAVEAT-#1 (N=35 consolidation names, full-universe; 0R for no-fill)
  Phase-A confirmed-close (loose OR trigger)   : filled n=17  median +2.00R  win 82%  +25.0R  ex-top3 +1.36R
  LIVE first-intraday-break (same loose model) : filled n=24  median −1.00R  win 38%  +3.7R   ex-top3 −0.07R  (top3 163%)
     full-universe mean +0.71R -> +0.11R ;  20/35 entries move to an earlier, weaker-close day
  GENUINE break on both arms (OR5-high > base) : Phase-A "fills" that were ACTUALLY above the base = 7/17
     live first-genuine-intraday-break          : filled n=13  median −1.00R  +5.0R  (top3 120%, ex-top3 negative)
```

**Two mechanisms inflated Phase A's +2.00R, both pushing the same way:**
1. **Daily-close selection (caveat #1):** 20/35 names break intraday on an EARLIER day than the
   confirmed close; a live watcher takes those (many close weak → −1R). Re-timed, the filled median
   goes +2.00R → −1.00R and the broad edge (ex-top3 +1.36R) becomes outlier-carried (ex-top3 ≈0).
2. **Entry tolerance:** `detect_first5_break` carries a 2% reclaim tolerance, so only **7 of 17**
   Phase-A "fills" had the OR5-high actually ABOVE the base — the other 10 entered up to 2% UNDER it.

**What this harness CAN settle (robust):** the specific **+2.00R/82% was an entry-model artifact**, not
a live edge. On a full-universe basis the de-rated consolidation entry (+3.7R loose / +5.0R genuine) is
now in the **same break-even, outlier-carried bucket as Day-2 ORB (+3.2R)** — the *quantitative* case
for "consolidation is the strong replacement" is **gone**.

**What this harness CANNOT settle (explicit):** whether a **properly-specified live base-break watcher**
(#94: all-day, volume-confirmed, genuine base break) has an edge. EVERY Arm-2 variant here — Phase A's,
the loose re-timed, the genuine — is an **OR-break-*near*-base** entry: it can only fire on an opening
break and is blind to a base break that grinds through mid-session (why APP's confirmed day shows a
genuine-OR5 R of 0 — it broke the base intraday, just not in the first 5 min). The OR5 proxy
**under-catches** the real watcher; the loose version **over-fires** on sub-base pokes #94 would reject.
The honest bracket is wide and centered near break-even — **no single de-rate number from this harness is
faithful** (not −0.61R, not ≈0; the genuine-arm ≈0 timing-delta is a small-N intersection coincidence,
not a result).

**Bridge to the live wiring (#326 read, updated):**
- **Claim A (retire Day-2 ORB): UNCHANGED, still solid.** Arm 1 has no base-break gate, so none of this
  touches it — its weakness is the wide prior-day-low stop, independently established.
- **Claim B (consolidation as the replacement): the +2R was an entry-model artifact, so consolidation is
  NO LONGER a quantitatively-demonstrated replacement** — BUT the direction is *not* killed, because this
  offline harness structurally cannot evaluate the real #94 watcher.
- **Resolution = the forward shadow with the ACTUAL #94 detector — observe-only, NO sizing.** Measure-
  before-wire did not moot the live wiring; it concluded *the offline harness can't answer the live-edge
  question, and the shadow is the only instrument that can.* So Phase B's live wiring is **justified**, but
  it must shadow the real volume-confirmed all-day base-break entry (NOT the naive OR-break, and NOT
  expecting +2R), accrue out-of-sample realized R, and PROVE a positive edge before any sizing.

Optional offline follow-up (NOT now): an all-day base-break proxy would reopen stop placement (the exact
mechanism Phase A turned on) — the forward shadow is the better instrument, so defer.

## Phase B — live wiring (the deployable shadow; PLAN #327 follow-on)

Feed confirmed 9M names → Family-A consolidation universe → intraday entry-watch (reuse #94 flag-break,
**volume-confirmed all-day base break — not the OR5 proxy above**) → shadow consolidation-entry → settle
realized R forward. Produces the forward-confirmation that the offline harness structurally cannot, and
accrues out-of-sample N. Execution-side/split-adjacent; observe-only, no sizing until a forward positive
edge is proven.
