# Operator-shared methodology notes (verbatim capture log)

**Why this file exists:** tweets / screenshots / notes the operator shares in chat live only in
conversation context, which gets compacted — and image content is LOST in summarization. They were
not being captured, so critical methodology shared "yesterday" became unrecoverable (operator
called this out 2026-06-16). **RULE (memory `feedback_capture_operator_shared_notes`): the moment
the operator shares a tweet / image / note with methodology, transcribe it VERBATIM here in the same
turn**, with date + source + how it maps to the build. Append-only; newest at top. This is the
durable home that survives context compaction — grep here before asking the operator to re-explain.

---

## 2026-08-07 — the 620-CHART (Gil Morales / theowltrader.com), operator-shared: article + 2 screenshots

**Full spec captured separately at `docs/methodology/620_chart.md`** — it ran long enough (source
article, both worked examples, the process-ordering constraint, and a computed TEAM example) to
warrant its own file. This entry is the index pointer so the append-only log stays the single place
to grep.

⚠ **CAPTURE FAILURE THAT PROMPTED IT:** the operator had shared this "a while back" and asked
2026-08-07 whether we still had a record. **We did not** — nothing in memory, nothing in the repo.
It was shared in a session whose context is gone and was never transcribed here, which is exactly
what this file exists to prevent. The governing memory `feedback_capture_operator_shared_notes`
was ALSO missing from the memory directory; written on 2026-08-07.

**The essentials** (detail in the dedicated file):
- 5-min candles · 6-EMA + 20-EMA · MACD on the same 6/20 periods · eSignal `(6,20,C,9)`, where the
  trailing digit is an auto-fill the author does not tune.
- **MACD cross is the SIGNAL; the 6-over-20 EMA cross is CONFIRMATION and lags ~1 hour** — by then
  price is "well up and away from the original entry".
- MACD **stretch** (fast pulling from slow) marks extension; its flattening is his take-profit.
- The 20-EMA is the intraday guide rail.
- The author calls it **"a tool, NOT a trading system"**, twice, and subordinates it to price (his
  NVDA short came from the $400 Century Mark alone, MACD only confirming).

⚖ **THE CONSTRAINT THAT GOVERNS ANY EVAL** (operator, verbatim): *"it's critical to note that 620
is used to fine-tune entry, not stock selection or only entry tool. In TEAM's case, it's already an
EP, it already has the fundamentals, the software theme and daily chart etc. I used 620 to pick
entry after all this already lined up."* → the 620 is the LAST step; testing it standalone across
all names measures something he never does.

**Worked example, computed from real bars — TEAM 2026-08-07** (he entered $144.39 on the same stock
Apollo was stopped out of at $143.21 that morning): MACD stretched to −1.86 at 11:10 ET, turned up
11:15, bullish cross 11:40, his entry ~12:05, 6/20 EMA cross 12:25. He entered ~25 min AFTER the
MACD signal and ~20 min BEFORE the EMA confirmation. His stated rule — *"I waited for the 6 period
stretched and turning while price chart also forming bottom"* — is three computable conditions.

**Maps to the build:** PLAN #545 (entry/exit tactics program) — the one specifiable piece of the
"other technicals" behind his delayed entries. Population for any sweep = the Day-1 stop-out set
(names already qualified), NOT all names.

---

## 2026-06-27 — ANTICIPATION coil POSITIVE EXAMPLES + the detector's structure gap (operator-shared, charts) — grounds setup #354

Operator reviewed the anticipation labeling worksheet (258 post-RMV-fix candidates) and flagged it's
STILL wrong, both directions. Verbatim:
- The shown candidates are **"average setup at best, most of them don't look tight at all or there's no
  basing at all."** Many are **"a dip then rise, then continue to rise and that is counted as tightness,
  there's no coiling in the structure itself, the range is wide and loose."**
- Real coils are **MISSING** (false negatives): **"GH... clear run up and a clear flat basing structure,
  and the past few days broke out from it"** does not appear. **"HNGE is another one that looks great on
  the chart, clear run up, clear tight basing, clear break out."**

**HNGE (Hinge Health, 1D) — 2 charts shared (wide + zoom), the canonical positive structure:**
- Prior runup (steep advance into the area).
- A **FLAT, SIDEWAYS base**: price oscillates inside a **tight HORIZONTAL band** (operator drew the flat
  resistance line across the top). Small, range-bound candles, **NOT trending**; sits ON the rising MAs and
  **HOLDS the level** (no breakdown) ~12–15 days.
- **Breakout** up through the flat top on a big expansion candle.

**GH — operator-described (not charted): clear runup → clear flat basing → broke out the past few days.**

**The positive-class structural features the detector MUST encode (what the operator's eye uses, that RMV
alone does NOT):**
1. **FLATNESS** — the base oscillates around a LEVEL (near-zero slope), not climbing. (The admitted garbage
   was DIRECTIONAL: dip→rise→rise.)
2. **ABSOLUTE tightness** — a genuinely NARROW band, not just contracting-relative-to-the-runup (Gemini's
   "6% is still a chainsaw" point, 2026-06-27 RMV review).
3. **HOLDS + a clean flat RESISTANCE line** — the flat top that becomes the breakout pivot.

**Implication:** RMV (relative volatility contraction) **cannot carry coil-detection alone** — it must be
PAIRED with STRUCTURAL gates (flatness/sideways + absolute narrow range + flat-top pivot). The worksheet's
candidate-SELECTION is the problem, not just the RMV thresholds. CALIBRATE from the operator's known-good
coils (GH, HNGE, + more) as the POSITIVE class — reverse-engineer the shared structure — NOT from the
detector's flawed candidate set (same data-grounded move as the 6/15 Pradeep cohort). Open diagnostic: are
GH/HNGE missing because of (A) structure-detection (gates reject flat bases / rank grinds higher) or (B) the
worksheet is a STALE 6/22 snapshot (their bases may have formed AFTER 6/22)? → the GH/HNGE bar-pull
diagnoses it. (RMV recalibration that preceded this: commit 20c9c06; #387 = the M&A/buyout false-positive.)

**RMV-creator reference chart (DOCU, 1D, from the video) — operator-shared 2026-06-27:** the creator
annotates **"Tight Areas/Ranges"** (low-RMV, the coiled spring) → then BOTH **"Expansion Up"** AND
**"Expansion Down."** KEY: **RMV is DIRECTION-AGNOSTIC** — a tight area precedes an expansion EITHER way
(the creator labels up- and down-expansions off the same tight zones). RMV finds the SPRING, not the
DIRECTION. This is exactly why ranking on RMV alone over-admits — it flags every tight zone, including
ones that resolve DOWN or are mid-trend pauses. The bullish anticipation setup = RMV (the spring) **+**
the bullish STRUCTURE/CONTEXT (post-runup + a flat, holding base → biases the break UP). The creator's
own rule (video summary): RMV is highest-probability **"up the right-hand side of a BASE"** or **"first
pullbacks to key MAs in an uptrend"** — i.e. RMV INSIDE a structure, never RMV alone. → The fix shape:
the STRUCTURE (post-runup + flat/holding base) is the GATE; RMV is the TIMING within it — not RMV ranking
the whole universe.

**Gemini diagnosis of the worksheet garbage (operator-shared 2026-06-27, builds on the above):** the bulk
of the false positives are **3–4 day post-runup PAUSES, not bases.** Mechanism: the 15-bar RMV baseline
straddles the vertical runup leg; when the base is only 3–4 days old, the tiny recent 3-bar numerator vs
the runup-inflated 15-bar denominator → rmv≈0 on a stock that "just stopped hyperventilating 72 hours ago"
— a structural pause, not a base. (PAYO baseD 4/rmv 0; NUVL baseD 6/rmv 0; PTGX baseD 4/rmv 22.) Bonde/Qulla
require a STABLE anchor — 3–4 days is a micro-swing, not a daily-chart base. FIXES (pre-RMV gates): **(1)
baseD floor ≥ 6–7** (current gate 3–20; forces a recognizable horizontal pivot + a loose-hands shakeout).
**(2) absolute NTR_3d cap < ~3–4%** (beta-adjusted) — relative contraction paired with an absolute ceiling,
reject high-beta chainsaws regardless of the relative rmv. Keep the shadow gate at 30 to finish the batch.
**CAVEATS (mine, NOT Gemini's, surfaced to the operator):** (a) Gemini INFERRED the labels (assumed
ROKU/ZVRA=G) — it does not have them; operator said ALL shown are poor, so "the G's passed" is unvalidated.
(b) baseD+NTR fix the false POSITIVES but NOT the false NEGATIVES (GH/HNGE missing) — separate diagnostic.
(c) baseD+NTR give duration+tightness but NOT FLATNESS — a 6-day low-NTR GRIND still climbs; the operator's
flat-sideways check (HNGE) is the piece Gemini omits. The 15-bar baseline spanning the runup is INTENDED
(not the bug); the bug is the baseD floor admitting 3-day pauses where the baseline is ~all runup.

---

## 2026-06-22 — HTF (High Tight Flag) blueprint (operator-shared, Gemini research) — grounds setup #356

Operator shared this to GROUND the HTF setup (the former flag → its OWN setup, #356) so we can
quick-start even if not shipping today. Canonical HTF spec + primary sources. Verbatim:

**FLAGPOLE (surge):** price surges **90–100%+ in 4–8 weeks**. O'Neil's original = **100–120% in 4–8
weeks** (modern scanners relax to 90% to catch near-doubles). Scanner signature: **C ≥ 1.9 × C₄₀**
(close ≥90% above the close 40 trading days ago) OR **High₄₀ ≥ 1.9 × Low₄₀**. Lookback 40 days (~8
wks); tighten to 20 for faster 4-wk flagpoles. *Shows undeniable institutional demand / extreme momentum.*

**FLAG (consolidation):** a SHALLOW pullback of **≤10–25% from the high**, lasting **3–5 weeks**
(sometimes 5–10 days). Scanner: **Close ≥ 0.75 × High₄₀** (within 25% of the 40-day high). Plus volume
DRIES UP + daily ranges CONTRACT tightly on the right side of the flag (the coiled spring). *Rejects
pump-and-dumps: if it doubles then gives back >25%, the trend is broken.*

**TREND:** price above the 10/20/50-day MAs; a Stage-2 uptrend (Minervini) before the flag forms.

**LIQUIDITY / VOL:** ADV > 500,000 shares; ADR > 4%.

**CATALYST:** the flagpole is backed by a massive fundamental catalyst — revolutionary product / a
"monster" earnings surprise (O'Neil) / an Episodic Pivot (earnings gap, FDA, defense contract — Qulla).

**ENTRY:** WAIT for the breakout above the flag's downtrend line / the absolute high of the flag, on a
MASSIVE volume surge (project ≥150% of ADV in the first 30–60 min). Pivot = the high of the TIGHTEST
daily candle on the right side of the flag. Order = **Buy Stop Limit 5–10¢ above the pivot** (only buys
on the break; protects vs slippage on a wild gap). DO NOT buy early in anticipation.

**STOP:** just below the low of the flag's tightest consolidation day, OR below the 10/20-day EMA.
Pivot-low = 1–2% below the tightest multi-day contraction. Hard max-loss cap **5–8%** from entry.

**SIZING:** risk **0.5–1%** of equity. `Shares = Equity × Risk% / (Entry − Stop)`.

**MANAGEMENT:** (1) scale out **33–50% into strength 3–5 days** after the breakout; (2) move the
remainder's stop to **breakeven**; (3) trail the runner on the **10/20-day EMA** — sell the rest ONLY
on a daily close below it. **TARGET:** measure the flagpole height ($) + add to the breakout point
("stocks that double tend to double again").

**SOURCES:** **O'Neil** (*How to Make Money in Stocks* — the ORIGINATOR: 100–120%/4–8wk flagpole,
≤10–25%/3–5wk pullback, fundamental catalyst; the rarest/most powerful pattern). **Minervini** (*Trade
Like a Stock Market Wizard* — HTF under the VCP umbrella: progressive tightening 20%→10%→4% + extreme
volume dry-up; Stage-2 prerequisite; buys the pivot on high volume). **Qullamaggie** (open-sourced —
EP-ignited flagpoles, shorter 5–10 day flags, scale at 3–5 days + trail the 10/20-EMA; cites O'Neil).
MarketSmith (O'Neil's team) HTF webinar. **ThinkScript/TC2000 scanner provided** (the two signatures:
the 90%+ 40-day surge + the ≤25% pullback near the 40-day high).

**HOW THIS MAPS TO OUR BUILD (#356):** the live `flag_detector` uses an UNSOURCED **50%/60d** runup;
HTF's sourced spec is **90%/40d surge + ≤25% pullback near the 40d high** (tighter/stronger than the
current 50%/60d). The HTF rebuild reconciles `flag_detector` to THIS spec (90%/40d, ≤25% pullback,
breakout entry on volume, the EMA-trail management). Load-bearing `/flags` → CHANGE_PROCESS + N≥10
backtest + sign-off.

---

## 2026-06-22 — Gemini cross-reference: full Pradeep Bonde Anticipation blueprint (operator-shared)

Operator shared this as a precise cross-reference for the #270 consolidation-play DEFINITION (after
the consolidation detector was found firing on declines/uptrends — it never enforced a real
consolidation). This is the canonical spec we BUILD TO. Verbatim:

**1. THE VELOCITY LEG (run-up).** Two universes:
- **Universe A (established trend):** Baseline Trend Intensity `C / C_65 > 1.05` (today's close ≥5%
  above the close 65 days ago — grinding up, filters chop/downtrends) AND Velocity `15%+ thrust over
  the last 10 days`.
- **Universe B (Episodic Pivot):** 10-day gap scan for `L > H_1 AND V > V_1` (today's low strictly
  above yesterday's high + volume surge).

**2. THE CONSOLIDATION PHASE ("coiled spring")** — a valid consolidation is defined by FOUR
dimensions; violate ANY one → the setup is VOIDED:

- **DEPTH (price retracement) — "holds the gains":**
  - **Upper Third Rule:** consolidate NEAR THE ABSOLUTE HIGH of the thrust; should NOT retrace more
    than **20–30% of the preceding move**.
  - **One-Strike Breakdown Rule:** during the consolidation, a **MAXIMUM of ONE** daily breakdown of
    **≥4%**. Two days of 4%+ drops → accumulation structure is broken → DISCARD.
  - **MA support:** price pauses long enough for the 10 EMA / 20 SMA to catch up (dynamic support).
- **DURATION (time):** **3 to 20 trading days** sideways. Sweet spot **4–10 days** (short = more
  explosive secondary burst; months-long = no urgency).
- **RANGE (volatility contraction):** intraday swings must SHRINK left→right; daily ranges (H−L)
  progressively tighten, closes tightly clustered. INVALID = "drunken man walk" (wild intraday swings,
  long wicks, gap-up-close-low then gap-down-close-high — chaotic, untradable). VALID = "linear and
  orderly." Ripe when it culminates in a **Narrow Range (NR) day**:
  - **3-bar total range ≤ 1.5%**
  - **Final daily range ≤ 0.3%**
  - Daily contraction scan: today's close within a **1% band** of yesterday's close.
- **VOLUME (the footprint):** volume dries up SYMMETRICALLY with the range. Absolute contraction:
  tightest-day volume is **well below the 50-day average** AND a fraction of the velocity-leg volume.
  Red-day volume during the pause < up-day volume during the velocity leg (institutions NOT dumping).
  The "dead" day: the narrowest-range day just before the breakout has the LOWEST volume of the whole
  3–20 day sequence (absolute equilibrium).
- **FLOAT:** < 25M shares (ideal < 10M) — low supply + catalyst = the friction for a rapid burst.

**3. TRIGGER:** Buy Stop just above the high of the narrow-range day (or OPG to execute at the opening
print on a slight gap out of the tight range).

**4. RISK / EXECUTION:**
- **Stop:** hard stop just below the low of the narrow-range day or the bottom of the 3-day tight
  block. Risk typically **2–4%**.
- **Exit:** target a Momentum Burst of **8–20% in 3–5 days**. Sell **30–50%** into the initial thrust
  (often within 1–2 days). Move the remainder's stop to **breakeven** immediately; trail the rest;
  cut it if the burst fades.

**HOW THIS MAPS TO OUR BUGS (the divergences to fix, not a new definition):**
- DEPTH is the missing "holds near the high" gate — Upper-Third (≤20–30% retrace) + One-Strike (≤1
  daily 4% breakdown). This is what cleanly rejects BTU/UFO/DRUG (multi-day 4%+ declines) that the
  code lets in.
- RANGE must be VOLATILITY-RELATIVE + a progressive contraction culminating in an NR day — NOT the
  absolute `≤7%` range `is_entry_tight` uses (which admits quiet declines + drops high-ATR leaders).
  Reconciles with the operator's own 6/16 note ("absolute range fails; ATR-normalized is the shape").
- A rising name (PTGX) is still in the velocity leg, not consolidating → no NR day → no trigger.
- The runup anchor must be the velocity-leg peak with the consolidation strictly AFTER it (the STM
  anchor bug). The velocity definition (`C/C_65>1.05` + 15%/10d) is the run-up gate.

Source (operator-shared, Gemini synthesis of Bonde's published materials): Stockbee.biz, "Low Range
Bar Breakout Strategies" bootcamp (the 1% contraction + TTT params), "Stocks in Play: A Trading Guide"
(EPs + OPG), LuxAlgo Stockbee screener ports (TI65 `C/C_65>1.05`).

---

## 2026-06-19 — Operator label + Gemini EP analysis on BFLY 6/18 (the #344 catalyst-correctness case)

**Operator correction of Apollo's `routine` grade reasoning ("no named customer or partner; no
contract value"):** *"this is technically incorrect because the partner/customer is mid journey and
the contract value is $74M previously disclosed in 8k filing."*

**Operator label (HARD gate):** BFLY 6/18 **IS** an Episodic Pivot — `routine` is the WRONG grade.
Maps to #344 → the "should grade higher" branch: re-point the 6/22 gate at catalyst-CORRECTNESS, not
the cache fix.

Gemini's EP analysis the operator shared, verbatim:

> You are completely right—good catch. Q1 earnings were actually reported back on April 30th.
> Yesterday's gap up was driven entirely by an unexpected commercial partnership, not an earnings report.
>
> **The Actual Catalyst: Midjourney Medical**
> Midjourney announced the launch of a new division, Midjourney Medical, alongside a prototype
> full-body tomographic ultrasound scanner. The critical detail for Butterfly Network is that the
> current scanner prototype incorporates **40 Butterfly Ultrasound-on-Chip modules per system** under
> a co-development agreement. A previously filed agreement also disclosed up to **$74 million** in
> expected payments to Butterfly over a five-year term.
>
> **Does this qualify as an Episodic Pivot (EP)? Yes.** While earnings are the most common driver, an
> EP requires a fundamental, unexpected news event that permanently alters a stock's valuation
> trajectory and triggers massive institutional accumulation. A high-profile, hardware-scaling
> partnership hits that requirement perfectly.
>
> | EP Criteria | $BFLY Data (June 18, 2026) | Verdict |
> | :--- | :--- | :--- |
> | **Surprise Catalyst** | High-visibility AI hardware integration (40 chips/scanner) out of nowhere. | ✅ Pass |
> | **Volume Surge** | Traded ~60.4 million shares, completely dwarfing its average daily volume. | ✅ Pass |
> | **Price Action (The Close)** | Opened at $7.21, closed at $8.90 (+55.9%), just pennies off the High of Day ($8.94) — sustained buying, not a "gap and crap" exhaustion. | ✅ Pass |
> | **Thematic Resonance** | Directly attaches a MedTech hardware supplier to the massive AI infrastructure theme. | ✅ Pass |
>
> **Tactical View:** Textbook Episodic Pivot. Massive volume + strong close near highs confirm
> institutional demand absorbing overhead supply. The stock has effectively reset its base. Focus
> shifts to post-EP risk management — watching for a tight consolidation flag holding the upper half
> of the momentum candle without heavy distribution volume.

**The fix this scopes (to verify):** the catalyst was a MATERIAL escalation of an EXISTING partnership
(Midjourney named in the 6/18 PR; the $74M / 5-yr terms in a PRIOR 8-K that the grounded corpus did
NOT carry — replay found SEC=0 in-window, the deal 8-K is ~Nov-2025). So the grade was made without
the prior material-agreement context → likely a CORPUS-COMPLETENESS gap (surface prior agreement terms
when a PR updates an existing partnership) and/or a named-partner / materiality recognition gap — NOT a
cache-timing problem. CHANGE_PROCESS + N≥10 cohort + sign-off before any load-bearing grade change.

---

## 2026-06-16 — Pradeep Bonde (@PradeepBonde / stockbee), full ANTICIPATION thread (posted 2026-06-15)

The complete playbook for the anticipation setup = our #270. Verbatim, in chronological order (each
is Pradeep's post/reply in a Q&A thread; the quoted question is in parentheses where shown):

1. **3:58 PM** — "See my short list for today. Do you see what I look for in anticipation? **Multiple
   tight days.**" Short list: **$COO, $HYLN, $ALHC, $APPS, $NTAP.** (reply Mat: "$NOK $RXT would be
   tight day anticipatory entry today?")
2. **4:48 PM** — "**3 to 5 day hold if they break else close.**"
3. **5:07 PM** — "**All of my selections have recent catalyst and have a first leg of 15% plus in 10
   days or less and are up or down tiny amount today. Have series of tight days.** Does your
   selection meets that criteria?" (reply WatchlistGuy: "After a strong acceleration, I like to see
   the price moving in a tight range for days. Hyln is doing exactly that.")
4. **5:08 PM** — "Today in anticipation" (reply NavsariGuju: "Did you buy any of these today or on
   the break tomorrow?")
5. **5:21 PM** — "**Unless they have catalyst which my analysis shows has long term potential no.
   Exit by end of third 4th or 5 the day or 20% whichever is earlier**" (reply chris: "Do you hold
   anything after 3-5 days or exit fully? And how do you choose the # of days?")
6. **5:42 PM** — "**I use time stop. If the stock does not move, I close.**" (reply ursachi: "How do
   you manage names that hold near day-one highs for the next 3+ days? No movement whatsoever but
   staying close to entry and increasing gap risk day over day")
7. **5:59 PM** — "**I just move my stops aggressively to protect profit if it gaps or breakouts in
   first few minutes so it starts fading you out with profit. Genuine breakouts don't fade so you
   hold for 3 to 5 days.**" (reply EternalCipher: "how are you deciding which one to do a morning
   sell and which ones to hold for 3-5 days?")
8. **7:04 PM** — "**Price percent change today between -.4 and .4. That is the qualifying criteria.
   After that, I look for a series of tight days in the previous two bars. Plus some additional
   criteria like catalyst, and what is the buzz about the stock amongst the popular traders on
   Twitter.**" (reply Poor Pay Rich: "closing prices +/- .4% or actual candle of day within .4%
   range?" → it's the **close-to-close % change**, not the intrabar range.)
9. **7:25 PM** — "**2 quarters in a row of 39% plus sales growth and also projected growth for next
   4 quarters are 39% plus**" (reply Steadfast, re catalysts with long-term potential).

### The setup, decomposed (the canonical #270 spec — from the source)

**SELECTION / readiness (a name qualifies when ALL hold):**
- **Recent catalyst** (ideally long-term — see catalyst quality below).
- **A first leg of +15% or more in ≤10 days** (the prior acceleration/thrust). ⚠ NOTE: BROADER than
  our current WATCHED gate (+40% gap). Pradeep's thrust is a *15%/10d leg*, not a one-day +40% gap →
  our universe is likely too narrow (ties to the generalization + task #15).
- **Up or down only a TINY amount today**: |close % change today| ≤ 0.4% (the qualifying tight bar).
- **A SERIES of tight days** (multiple tight days; "price moving in a tight range for days" after the
  acceleration). Tightness is a RUN, not one day.
- **Buzz among popular traders on Twitter** (social/theme axis).

**CATALYST QUALITY (the long-term-potential bar):** 2 quarters in a row of **39%+ sales growth** AND
projected **39%+ for the next 4 quarters** — strong, sustained, accelerating REVENUE/SALES growth
(reinforces [[user_pradeep_revenue_over_eps]]: revenue is the signal).

**ENTRY:** anticipate — buy on the tight day (the day before), or on the break the next day.

**EXIT / management (derisk fast; catalyst-conditional leash):**
- **3–5 day hold IF it breaks; else close** (no break → close).
- **Time stop:** if the stock does not move, close it (don't let a dead name sit and accumulate gap
  risk day over day).
- **Aggressive stop-trail on a fast move:** if it gaps / breaks out in the first few minutes, move
  stops aggressively to protect profit so it "fades you out WITH profit." Genuine breakouts don't
  fade → you hold those 3–5 days. (This IS the day-0 giveback-trail / two-phase exit we backtested.)
- **Hard cap:** exit by end of day 3 / 4 / 5 OR +20%, whichever is earlier — **UNLESS** it has a
  catalyst with long-term potential, then hold longer. ⚠ This **CONFIRMS the catalyst-conditional
  leash is real Pradeep methodology** — our SSoT had it as "inconclusive / confounded by unsourced
  catalysts." It's not inconclusive in principle; it was just untestable on the backfill cohort.

### ARCHITECTURE — "CONSOLIDATION PLAYS POST A RUNUP" (the family; operator 2026-06-16)
**Umbrella name (operator): "consolidation plays post a runup."** anticipation, flags/continuation, and
U&R-on-the-consolidation are the SAME family (FAMILY A): a runup → a consolidation (tight base/coil) →
entry. Share ONE universe + ONE coil detection (undercut allowed). Differ on ONE axis — **ENTRY MODE
(when you enter):** Anticipate (in the coil, before the break) · Confirm/flag (on the confirmed break) ·
U&R (on undercut of the base/consolidation low → reclaim; tightest stop). EP NOT required for Family A
("anticipation can be from an EP but not necessary").

**U&R is a GENERIC MECHANIC, not a family member** (operator nuance 6/16): "price falls below SOME
reference point → reclaims it." Reference = a consolidation/base low (Family A), an EP low, an MA,
congestion, etc. Reusable across families (`fishhook_detector` + `anticipation.detect_gdl_reclaim` were
reclaim-mechanic implementations — `fishhook_detector` retired 2026-07-21, operator call; the mechanic
survives in `anticipation.detect_gdl_reclaim`). Do NOT treat U&R as owned by one family.

**Fishhook / delayed-EP are FAMILY B (the EP family), NOT Family A** (operator correction 6/16): a
delayed-EP REQUIRES an EP first (fishhook's gap-up IS the EP), then re-enters — often via a U&R on the
EP low. The EP is not an "optional gate on consolidation"; delayed-EP is its own EP-family play. **FAMILY
B = the EP family (MAGNA53 / 9M / delayed-EP / fishhook) = the NEXT rework, SEPARATE** from the current
Family-A build. ⇒ current scope tightens to Family A only; fishhook stays put. (2026-07-21 update:
fishhook_v3 was retired outright — operator call, discretionary re-entry doesn't belong in the automated
core — rather than staying put for the Family-B rework; the delayed-EP concept survives in #297/#314 for
a possible future non-fishhook approach.)

Anticipation is NOT a from-scratch detector — it's a sibling in FAMILY A sharing the substrate. Three
unification decisions:
1. **One shared, well-tuned UNIVERSE for ALL tactics** — a post-runup tightening universe (loose runup
   + liquidity), tuned ONCE, feeding flags + anticipation + others. NOT per-tactic universes.
   "We want a good universe for all tactics." (Folds in #15 + reconciles the flag universe.)
2. **Undercut is OK for BOTH** — the flag detector's "INVALIDATE on undercut" is wrong for flags too,
   not just anticipation. An undercut (U&R) is a valid shape for both. → fix in `flag_detector`
   (detection-criterion change → CHANGE_PROCESS + sign-off).
3. **The difference = ENTRY TIMING on the same coiled candidate — THREE modes** (operator added U&R):
   - **Anticipate** — enter BEFORE the move, in the tightness. Stop = tight-range low. (anticipation entry)
   - **Confirm / flag** — WAIT for the confirmed breakout (base_high + vol). Stop = base/breakout low. (#94)
   - **U&R (undercut & rally)** — undercut the low → RECLAIM it. Stop = the undercut/washout low (TIGHTEST,
     biggest cushion — the U&R paradox). Mechanic EXISTS: `anticipation.detect_gdl_reclaim` (a gap-up
     undercut & reclaim state machine also existed as `fishhook_detector`, retired 2026-07-21). REUSE the
     surviving implementation — but on the shared post-runup TIGHT universe (higher conviction), not a
     broad gap-up/low-R harvester universe.
⇒ Build = ONE shared universe → ONE coil detection (undercut allowed) → THREE entry modes. All three
mechanics existed (anticipation / flag-break / fishhook-reclaim) — the unification was pointing them
at the shared coiled universe. Formalize as an ADR (reshapes flags + anticipation). RESOLVED 2026-07-21:
fishhook-the-broad-harvester did NOT get folded into U&R — operator retired it outright (discretionary
delayed-EP re-entry doesn't belong in the automated core); #297/#314 track a possible future non-fishhook
delayed-EP approach.

### LAYERING — anticipation (a TACTIC) ≠ Stocks in Play (operator 2026-06-16, recurring correction)
**Anticipation is ONE tactic** (runup → tight spot → entry); it produces a ranked candidate feed.
**Stocks in Play is the CONSOLIDATED list across ALL tactics** — anticipation + MAGNA53 EP + 9M-derived
+ flag + … merged (ADR-0004 `mi_stocks_in_play`). The anticipation shortlist is ONE INPUT that feeds
SiP, not SiP itself. Do not call a single tactic's output "Stocks in Play." (I've conflated these
multiple times — stop.)

### VERIFICATION RESULTS — 6 known-good names, as-of 2026-06-15 (read-only probe, 6/16)
Validation set: COO/HYLN/ALHC/APPS/NTAP (Pradeep 6/15) + MNTS. Measured, no thresholds applied.
- **+15% in ≤10d leg: holds 6/6** (COO 15% exactly · NTAP 52 · ALHC 55 · APPS 130 · HYLN 159 · MNTS 265).
  The sourced universe gate WORKS.
- **Universe sources (as-of-6/15, date-filtered — not "ever"):** flag_candidates has all 6 but only as
  **WATCH (APPS/HYLN/MNTS/NTAP) / unqualified (COO/ALHC)** — its TIGHTENING/COILED classification fired
  for NONE. 9M alerts = **2/6** (APPS 6/9, MNTS 6/11). EP alerts = **0/6** in window. multiple-9M cohort
  = **0/6**. ⇒ **9M/multiple-9M are TOO SPARSE to be the universe** (refuted). The flag WATCH list is the
  closest existing post-runup radar (all 6), but its tightening gate MISSES genuinely-tight names.
- **Tightness must be VOLATILITY-RELATIVE (stock character), not absolute:** COO/ALHC/NTAP tight by
  RMV+range (rmv5 0-19, range 2-4%). HYLN/MNTS are "tight" only RELATIVE to their own 159%/265% legs
  (range 12%/28% absolute). Absolute range fails; the ≤0.4% close-streak is far too strict (all 0-1);
  RMV closer but imperfect (HYLN rmv5=37, MNTS=33). ⇒ confirms COMBINE + normalize to the stock's own
  ATR/character ([[user_pivot_generalization]]). The ATR-normalized fresh_tightening primitive is the
  right shape.
- **Catalyst:** EP data covers the EP-subset only (APPS/NTAP/MNTS) — one input, not universal.
- **DIRECTION the data supports:** anticipation = the post-runup WATCH universe (flag radar; NOT 9M) →
  rank by OUR volatility-relative tightness (RMV + ATR-relative range; recalibrate the close-streak) +
  catalyst → top-N. Verify next; nothing gated yet.

### Design inputs to VERIFY — NOT facts (operator 2026-06-16)
The operator's framing: these connect anticipation to what we already have, but they are **ideas to
verify against data, not criteria to hardcode** (the whole phantom-criterion lesson). Reuse + measure:
- **Catalyst** can share from our **EP/MAGNA53 detector** as a possible input (reuse its catalyst data).
- **Tightness** can include **RMV** — and **compare or COMBINE** it with the tight-close series / range
  (don't pick one blindly; measure which separates the real picks).
- **Universe** can include **9M / multiple-9M cohort** (sugar-baby list) as the initial list to monitor,
  or to AUGMENT the +15%/≤10d leg universe.
VERIFY each against the known-good set (Pradeep 6/15: COO/HYLN/ALHC/APPS/NTAP + MNTS) before any gate:
does 9M/multi-9M capture them? does +15%/≤10d? do RMV/tight-close agree on which are "tight"? do they
have EP catalyst? Report what the data says; gate only on what holds. No invented thresholds.

### Build implications (FLAGGED — detection changes need sign-off + CHANGE_PROCESS, not auto-applied)
- **Thrust gate too narrow:** +40% one-day gap vs Pradeep's "first leg +15% in ≤10 days." Broadening
  the WATCHED universe to the 15%/10d leg is the biggest delta (and is essentially task #15's loose
  universe). Evidence + sign-off gated.
- **tight_close_streak** (shipped 6/16) = his "series of tight days." ✓ on the right track.
- **Catalyst-conditional exit leash** = CONFIRMED real; revisit the W3 exit work + reopen the leash
  test once #210/#211 source catalysts properly (the SSoT already filed this; now it has the source).
- **Catalyst-quality bar** (2× 39%+ sales growth + 39%+ projected) = a concrete materiality input for
  #189 / the rubric.

## RMV developer's settings (RMVP - Relative Measured Volatility Pivots) - shared by operator 2026-06-30

Reference for our own RMV indicator (#54 / reference_rmv_tightness_metric memory - our RMV = `flag_detector._compute_rmv`, rmv_5d/15d). The developer's TradingView suite (prefix "DV"): "DV - Relative Measured Volatility (RMV)" (the 0-100 oscillator, reading **57.64** on CRWD = mid-range, not extreme-tight) + "DV - Relative Measured Volatility Pivots (RMVP)" (the pivots overlay) + "DV - Base Pivots" + "DV - Key Moving Averages".

**RMVP settings (VERBATIM from the screenshot):**
- Max Pivots: **2**
- Breakout Threshold: **ADR**
- Merge Within %: **0.3**
- Breakout %: **2**
- ADR Lookback: **20**
- ADR Multiplier: **1.5**
- Style: Line Color blue - Line Width 3 - Line Style Solid

**Key takeaway for building our RMV:** the developer's logic is **ADR-based** (Average Daily Range over a 20-day lookback x a 1.5 multiplier as the volatility/breakout yardstick; pivots merge within 0.3%, breakout at 2%, max 2 pivots). At #54 eval: compare our rmv_5d/15d COMPUTATION BASIS against this ADR(20)x1.5 approach - if ours diverges, this is the canonical reference to reconcile against (established-setup -> use the primary definition, per feedback_established_setup_use_primary_definition). Chart context: CRWD daily, RMV 57.64, "$785.66 - 20 days - 21%" pivot annotation, Avg $ Vol 2.53B.

**Image saved:** `docs/methodology/rmv_developer_settings_2026-06-30.jpg` (the original screenshot - the RMVP settings panel + the CRWD chart context, preserved in-repo since the operator's Screenshots folder is transient).

---

## 2026-08-11 — SE as a DELAYED-EP candidate: the operator's own read, verbatim

Captured live during the session, minutes after SE was skipped at the open
(`setup:gap_below_floor: rt 9.2% < 10% floor`; it reclaimed to +10.5% by 09:35).

> "regardless, SE is one i'm looking for a possible delayed EP, it gapped through while above
> all Moving averages, with a decent looking base, looks may be moving to a stage 2 uptrend
> after bottoming and basing for a while; also, retail group is strong where this belongs"

**Why this is worth preserving rather than leaving in chat:** #562 asks *what IS our
delayed-entry trigger today* — and the honest answer is that our machine trigger fires roughly
once per hundred watched names. This is the HUMAN version of that trigger, stated on a live
name, by the person whose judgement the machine is meant to approximate. It is the closest
thing we have to a labelled positive example.

**The four conditions he named, decomposed — each is separately checkable, and NONE of them is
in the current TRIGGERED logic:**

1. **Gapped through while above ALL moving averages.** Not "gapped" alone — the gap happened
   from a position of existing strength, not off a bottom. We store `sma_10/20/40/50` in
   `mi_stock_scores`; whether price sat above all of them at the gap is computable today.
2. **A decent-looking base.** The prior consolidation. This is the closest to something we
   already measure (`rmv_5d`/`rmv_15d`, the consolidation-family tightness work) — but "decent
   looking" is a shape judgement we have never pinned to a number.
3. **Possibly moving to a Stage 2 uptrend after bottoming and basing for a while.** Stage
   analysis — a REGIME statement about the name, not about the day. We have no stage
   classifier. This is the biggest gap of the four.
4. **The GROUP is strong, and this name belongs to it.** Theme/group strength as a
   precondition for the individual entry — the north star chain
   (`theme-north-star-early-rs-before-mainstream`) pointed at a single trade.

⚠ **CONDITION 4 FAILED ON OUR SIDE, MEASURED THE SAME MINUTE: `SE` is in NO live theme at all**
(zero `mi_themes` rows in the last 10 days contain it). He can see the retail group is strong
and that SE belongs to it; the system cannot. This is the same shape as the 2026-08-07 software
cohort (#471) — the strength is real, the membership is missing — and it is a live worked
example for **#563** (are we under-using EP gaps to find themes early).

⚠ **SETUP vs FAMILY discipline (CLAUDE.md):** "delayed EP" as described here is NOT yet a setup.
It has no stated buy point and no stated stop. Conditions 1-4 describe a CONTEXT that would make
a name eligible; the entry and the stop still have to be named before anything is tradeable.
That naming is exactly what **#562** owes.

▶ Feeds: **#562** (delayed-entry trigger — use this as the worked positive example),
**#563** (theme coverage of EP gap names), **#559** (the gap-floor block that kept us out of SE
in the first place).

▶ **2026-08-15 — SPECIFIED:** the four conditions are now the delayed-entry family's eligibility
gate E1–E4 (each encoded, Stage-2 build spec included), and the same-day re-look is setup **DE-1**
— `docs/roadmap/ep_profitability_program.md` §4a.

---

## 2026-08-12 — "What is a REAL EP" — the operator reframes the ranking question

Said at the start of the day the ranking readout was due, and it **supersedes the framing of that
work**. Verbatim:

> "On the EP ranking, what i believe now and want to iterate on is that it's not so much just
> ranking itself, but more what is a real EP. I believe we're too lose right now, just any
> sufficient gap up is a EP which makes us overtrade, gaps are the signal that EP might be there,
> but we need to do more to filter for real EPs, that's where the rest of our criteria comes in.
> I also think we haven't fully implemented the spirit of 'neglected stock gapping through key
> levels' that quallamaggie looks at, some of the trades we make it just gaps into congestion,
> resistance areas and had no strength to break through it, this is where chart structure is
> important."

**Analysis, the three claims separated, the 08-11 evidence, and how this reframes #533: merged into
`docs/roadmap/ep_profitability_program.md` §2 (Selection/Ranking) and the GOAL section — not
duplicated here. That doc is the single place this question's current answer lives.**

---

## 2026-08-12 (later) — operator pushes back on the structure null, and he is right

I reported "structure does not separate" off 244 settled alerts. His response, verbatim:

> "i don't neccessary agree here. First, our sample size is small, and EPs are rare, so I don't
> claim that structure will reveal itself in a few trades. Also, chart structure is part science
> part art, how you determine if it's gapping up above certain levels depends on what the chart
> looks like, sometimes you go further back because we see multiple tests of certain levels that
> failed previously, sometimes you don't need to if you don't see such test; sometimes you want it
> to gap up above key moving averages, sometimes not because it's too far away and not realistic,
> etc. etc. We can't make conclusions other than the fact that structure does matter for EPs. The
> better way to see this is probably to have a few winners to compare it with. THe whole premise
> here is to be more selective. And this is only one criteria, my whole point is that we need to
> leverage all factors, some we may not know about now, to help us filter down the universe to
> what we think are potential real EPs, and even then the win rate make by only 20% or so. What my
> fear is that our winrate is 10% of lower now because we are not selective enough. Then there's
> also alternate delay entries."

**Analysis (what I got wrong, his contextual definition of structure, the design correction, his
win-rate numbers): merged into `docs/roadmap/ep_profitability_program.md` §2 (Selection/Ranking)
and the GOAL section — not duplicated here.**

---

## 2026-08-12 — NBIS: the clearest structure example yet, AND a grading complaint

Operator, live, verbatim:

> "quick note on today's EP, i see NBIS is moderate due to marginal revenue beat on expectation,
> but it was >400% reveune growth. Also, it's a good stock to review what i see in structure, it
> gapped up through the 50d which is a resistance, pulled back and held up in the early morning,
> also it gapped up through previous highs which as been a resistant in the past few rallies
> around $227 price point, now it's trending up through the day (so far). If it were to gap up but
> drop and held below those points or even gap and not breach those points, it would have been a
> poor structure."

### (1) THE GRADING COMPLAINT — beat-vs-expectation is not growth

NBIS graded **moderate**, reasoned as a *marginal revenue beat on expectation* — while revenue grew
**>400% year over year**. The rubric is scoring the SURPRISE (actual vs analyst estimate) and is
blind to the MAGNITUDE of the underlying growth. Those are different facts and a 400% grower that
merely meets a high bar is not the same event as a flat company beating by a cent.

⚠ Unverified against the rubric code as of writing — **check what NBIS actually scored on and
which component drove "moderate" before concluding the rubric is at fault**; the grade may have
come from elsewhere. Feeds the SELECTION surface of The Real EP Plan.

### (2) THE STRUCTURE EXAMPLE — and it is the first one that is FALSIFIABLE

This is the most operationalisable statement of "gapping through key levels" he has given, because
he stated the NEGATIVE case as well as the positive:

**GOOD (what NBIS did):**
1. Gapped **through the 50-day**, which was acting as resistance.
2. **Pulled back and HELD** in the early morning — it did not fall back through.
3. Gapped **through prior highs around $227**, a level that had rejected price on the past few
   rallies.
4. Trending up through the day.

**POOR (his stated counter-case — this is what makes it measurable):**
- gapped up, then **dropped and held BELOW** those levels; or
- gapped and **never breached** them at all.

### Why this is better than the proxy I tested and failed with

My 08-12 readout tested "close above all three SMAs" as a stand-in for structure and got a null.
This is a different and better question in three ways:
- **It is about a LEVEL THAT PREVIOUSLY REJECTED PRICE**, not about a moving average per se. The
  50-day counts here *because* it was resistance; the $227 high counts because it had failed
  "the past few rallies". A generic above-the-SMA test cannot see that.
- **It has an INTRADAY HOLD TEST.** Clearing a level at the open and holding it after a pullback
  is a different event from gapping over it and fading. We have minute bars; this is measurable.
- **It has an explicit failure mode**, so it can be scored on both sides rather than only counting
  the wins.

▶ This is the candidate feature the structure work should test next — NOT "above all three SMAs".
Three checks: was there a level that had previously rejected price; did the gap CLEAR it; did price
HOLD above it after the first pullback.

▶ **2026-08-15 — ENCODED:** the three checks + the congestion metric are specified in
`docs/roadmap/ep_profitability_program.md` §2 (THE NBIS ENCODING); this section's positive and
failure labels are its validation fixtures, and the grading complaint above is scoring proposal
S-4 there.

⚠ Standing rule applies: NBIS is ONE name and illustrates the definition; it does not establish
that the feature works. That needs the distribution, with N and distinct sessions.

---

📚 **Consolidated into the structure SSoT: `docs/methodology/structure_model.md`** — read that
first; the sections below are the dated verbatim captures it draws on.

## 2026-08-16 — THE SUPPLY-LADDER MODEL: why structure works, in his words

Said after seeing the encoder pass his eight labelled reads. This is the MECHANISM behind the
definition he gave on NBIS — capture it verbatim, because it changes what we should be measuring.

> "At the end of the day, structure shows historical prices, and congestion of prices is where
> potential supply is (in theory, that's where lots of buy/sell happened, and where ppl may be
> holding stock at that price and maybe will be willing to sell it there to breakeven or whatever
> reason), and each supply point / pivot it passes, the stock has chance to move to the next supply
> zone until it's all clear and where the stock has blue sky potential. Of course, there's lots of
> nuance, like how far back to look etc. and this is where concepts like basing, etc. comes in.
> Anyways, I believe price/chart structure is key ingredient to EP."

### What is NEW here, versus the definition we already encoded

The NBIS definition told us how to judge ONE level: did the gap clear it, did it hold. **This tells
us what the levels ARE and why passing them matters** — and it implies a different measurement:

1. **Congestion = potential supply, and the reason is holders.** Volume traded at a price means
   people own stock there; many will sell at breakeven. That is why a level rejects price, and it
   is a supply argument, not a chart-pattern argument.
2. 🔴 **It is a LADDER, not a single gate.** Each pivot cleared buys the stock a run **to the next
   supply zone**. So the quantity that predicts how far a move can go is **how much supply remains
   overhead and how far away the next zone sits** — not a binary good/poor verdict.
3. **Blue sky is the limiting case** — the ladder is empty, nothing overhead, and the stock is
   free to run. Our encoder already has this as its own class (ETON 08-14).
4. **"How far back to look" is the acknowledged nuance** — and the encoder already answers it the
   way he does: each level reaches back exactly as far as its own failed tests, no fixed window.
5. **Basing belongs to this model** — a base IS a congestion zone the stock has already absorbed;
   it is why "a decent looking base" was one of his four SE conditions.

### 2026-08-16 (same session, his refinement) — COUNT the zones cleared; raw gap % has no reference

> "an added point, EPs that clear congestion zones the more it clears the stronger all else equal.
> If the gap up just meets the first congestion or fails even to go above it is iffy, the same
> concept of moving averages, it's just any proxy or gauge to see how strong the gap up is aside
> from raw % which has no reference. Gapping up above key levels, holding, even pulling back to not
> failing is sign of strength."

🔴 **This is the sharpest statement anyone has made about the gap problem.** A gap percentage is a
number with **no reference frame** — 20% means nothing on its own. *How much overhead structure the
gap consumed* is the gauge that does have one. It explains the plan's own contradiction directly:
BW gapped **34.9%** into the bottom of the RS field and died inside 60 seconds, while PLTR and EROC
both gapped ~**16%** and are his two labelled good EPs. Same signal, opposite meaning — because
percent was never the measurement.

Four things it specifies, each measurable:

1. **`zones_cleared` — a COUNT, and more is stronger** (all else equal). Not a binary cleared/not.
2. **The IFFY case, named by him:** the gap lands at, or fails to get above, the FIRST congestion.
   That is its own bucket, not a low value on a continuous scale.
3. **Moving averages are the same concept** — his words: "just another proxy or gauge". So an
   MAs-cleared count is a legitimate cheap parallel gauge, and we already store sma_10/20/40/50.
4. **HELD, not touched** — "gapping above key levels, holding, even pulling back to not failing is
   sign of strength." The strength measure is zones cleared AND still held after the first pullback.

▶ **The decisive test this sets up:** run `zones_cleared` head-to-head against RAW GAP % on the same
cohort, at comparable gap size. His hypothesis is that percent is close to noise and
structure-consumed carries the information. If that holds, it is the replacement for gap in the
selection surface — and gap's dominance of the grade (§the grade mechanism read) is not just
over-weighted but **measured in the wrong unit**.

### ▶ What it changes in the measurement — this is actionable, not philosophy

**We tested the wrong dependent variable.** The 08-15 sweep asked whether a GOOD/POOR verdict
predicts forward RETURN, and got a null on an all-losing cohort. His model says the structure
signal is about **how far a move can travel before it meets sellers** — so the right test is
**room-to-next-supply vs the SIZE of the excursion** (max favourable move), which is measurable
even in names that ended up losers.

That matters for the GOAL arithmetic directly: we need average winners above 4R, and "how much
clear air is above the entry" is a structural prior on how big a winner can get. It is the first
feature we have that speaks to the W term rather than to the p term.

▶ Feeds: the structure encoder (`_533_nbis_structure_encoder.py` already computes remaining
overhead — SE's January $129 shelf at 0.28 ADR, exactly where it stalled), plan §2 fork S-3, and
the winner reference set (§1b step 5).

---

## 2026-08-14 PRE-OPEN — a LABELLED PREDICTION on three live alerts (HTFL, ETON, VERA)

⚠ **Recorded BEFORE the open, before any outcome is known.** That is what makes it evidence rather
than hindsight — the plan's standing rule is that a case may illustrate, but a call stated in
advance and then scored is a genuine test of the structure thesis.

Operator, verbatim:

> "quick note on today's EPs so far, Apollo fired 3 HTFL, ETON, VERA, market's not opened yet so i
> don't know how they'll trade when open, however, just by quickly eyeballing the charts I see HTFL
> and ETON clearing above key levels, both are actually moving near or above ATH; while VERA looks
> rather poor, just chopping back above where it was a few days ago but still deep in it's
> downtrend. THings can change and turn out anyway, but my cursory look says VERA is the weakest
> one and one that I won't be trading if I decide."

### His call, decomposed

| Name | His read | The structural fact he used |
|---|---|---|
| **HTFL** | strong | clearing above key levels; near or above all-time high |
| **ETON** | strong | clearing above key levels; near or above all-time high |
| **VERA** | **weakest — would not trade** | chopping back above where it sat a few days ago, still deep in a downtrend |

### Why this matters to The Real EP Plan

- It is the **same structure criterion as NBIS** (2026-08-12): does the gap CLEAR a level that
  previously mattered, or does it land inside prior chop. Here he adds the **at/near all-time-high**
  case — the cleanest version of "nothing overhead", i.e. no supply to fight.
- **VERA is the negative case stated in advance**: price back above a few days' chop but still
  inside a downtrend = no level cleared, plenty overhead.
- ⚠ He hedged it himself — *"things can change and turn out anyway"* — and the standing rule says
  one session cannot conclude. **Three names is an illustration; the value is that the label was
  fixed before the outcome.**

### ▶ SCORE THIS — do not let it evaporate

Record what each of the three actually did (forward return / MFE / MAE at 1, 3, 5, 10 days from the
alert) and whether our system traded, skipped, or graded them differently from his read. **Add the
result to §0a of The Real EP Plan when it settles.** If his call separates and our score does not,
that is a direct measurement of the gap this whole plan exists to close.
