# Operator-shared methodology notes (verbatim capture log)

> 📜 **THE PRINCIPLES (P1-P10) + THE GOAL live in `docs/roadmap/ep_profitability_program.md` § THE PRINCIPLES.** Read them before any analysis, card or proposal here — they are the operator's own rules, in precedence order, and they govern this document. Cite by name (P1, P2…). ⚖ THE LINE sits above all of them.


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

## 2026-08-16 — WHY THE TAIL, AND THE RS TRAJECTORY SHAPE (his reading of the tail result)

On being shown that RS improvement predicts the TAIL (+50%/+100% excursion) while leaving the
median flat:

> "this makes sense to me, the tail is where i'd expect neglect to form and the middle has already
> risen at some point and for whatever reason didn't continue to the top (yet). One more nuance to
> consider, i'd expect RS to drop then stabilize and stay at certain level before the rise, or maybe
> this is moot because the tail can't go lower?"

### Claim 1 — WHY low RS is the fertile ground, and the middle is not

**The bottom is where NEGLECT forms. The middle is the STALLED cohort** — names that already rose
at some point and, for whatever reason, did not continue. That is a mechanism, not a correlation,
and it explains the result rather than merely restating it: a mid-RS name has already spent part of
its move, so there is less left; a bottom-RS name has spent nothing.

▶ It also explains why RS LEVEL failed as a grade input while RS IMPROVEMENT worked in the tail —
his two labelled good EPs, PLTR (rank 2230/2415) and EROC (2373/2415), both sat in the bottom
decile.

### Claim 2 — the TRAJECTORY SHAPE: drop → stabilise → hold → rise

He expects a **three-phase** signature, not a two-point slope: RS falls, then **stabilises and sits
at a level for a while**, and only then rises. That is the base-building shape stated in RS terms,
and it is richer than the `rs_1m − rs_6m` sign we tested (a 2-point difference cannot tell
*still-falling* from *flat*).

📌 **PLTR's own trace fits it** — rank 2225 → 2129 → 2195 → 2121 → 2230 across the week into the
gap: FLAT, not still-falling. (`plan §2026-08-15 RS IMPROVEMENT` section.)

### Claim 2b — the SECOND DERIVATIVE, his own cleaner encoding of claim 2

> "or another way to think about it is the 2nd derivative, RS deceleration/acceleration down or up,
> I'd expect deceleration associated with neglect and acceleration associated with attention in
> either direction"

**The three-phase shape IS a curvature statement**, and this says it in one number instead of a
hand-drawn classification. It also carries a semantic mapping we did not have before:

- **DECELERATION ↔ NEGLECT** — the selling is exhausting; nobody is trading it any more.
- **ACCELERATION ↔ ATTENTION, in EITHER direction** — someone is acting on it, up or down.

**The two derivatives together give four regimes**, and his hypothesis names which one is the EP
precursor:

| 1st deriv | 2nd deriv | Regime | His reading |
|---|---|---|---|
| falling | accelerating down | still being actively sold | attention, negative |
| falling | **decelerating** | 🎯 **neglect settling in, sellers exhausting** | **the EP precursor** |
| rising | accelerating | attention, positive | likely his *"middle that already rose"* |
| rising | decelerating | fading | — |

⚠ **It does NOT dissolve his floor objection** (claim 3 below) — curvature compresses near the
bottom just as slope does, so the within-RS-band test governs this encoding too. And **duration in
the bottom decile stays the feature least affected by the floor.**

⚠ Three encodings of one idea — the `rs_1m − rs_6m` sign, slope+dispersion, and curvature — are
**related tests, not three independent findings.** The multiplicity accounting must treat them as
such, or the same effect gets counted three times.

### Claim 3 — his own methodological objection, and it is the right one to raise

> *"or maybe this is moot because the tail can't go lower?"*

**Partly, and it must be tested rather than assumed.** RS percentile is bounded at 0, so variance
compresses near the floor and "stabilisation" could be mechanically guaranteed for anything already
at rank ~2300 of 2415 — in which case the flat trace carries no information.

**But level is not the only observable, and two things stay measurable at the floor:**
- **DURATION** — a name that fell to the bottom decile last week is not the same as one that has sat
  there for three months. Time-in-the-bottom is the "basing" length in RS terms.
- **SHAPE** — still-falling vs flat is distinguishable even inside the bottom decile, via the slope
  over the prior 20/60 sessions and the dispersion of RS around its own recent level.

▶ **The test that settles the moot-ness question directly: condition on RS LEVEL.** Compare
trajectory shapes **within narrow RS bands**, so "cannot go lower" is held constant across the
comparison. If shape still separates the tail inside a band, it is not a floor artifact.

▶ Feeds: the RS-inflection candidate (plan §2026-08-16 tail re-read, fork S-3), and the "decent
looking base" condition from his SE list — this is the same idea measured in RS space rather than
price space.

---

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

---

## 2026-08-19 — MRNA: THE TEXTBOOK EP, transcribed from his two shared charts + two tweets

**Captured the same turn he shared them** — images do not survive compaction and the 620 chart was
lost exactly this way ([[capture-operator-shared-notes]]). Everything below is READ OFF THE CHARTS,
not inferred.

> *"$MRNA MEMORIZE these daily, weekly and 5 min charts FOR EPs. THIS IS PERFECT *SO FAR*..."*
> *"For anyone wondering, $MRNA is an absolutely perfect and textbook EP. To not be confused with a PEG"*

His own framing the same morning: *"MRNA is a textbook EP (i also see other traders mention it as such
today), the news is truly gamechanging, the move, etc. is textbook."*

### 🔑 THE STRUCTURAL POINT: three timeframes, and the base is MEASURED, not eyeballed

The author's instruction is to memorise **daily, weekly AND 5-minute** together. The bases are
annotated as **duration × depth** on both higher timeframes — this is exactly the tightness/structure
axis our encoder is supposed to capture, expressed as a pair of numbers:

| timeframe | annotated bases |
|---|---|
| **Daily** | **74 days · 27%** · **101 days · 34%** |
| **Weekly** | **17 weeks · 27%** · **23 weeks · 34%** · **26 weeks · 37%** |

Read: a long, SHALLOW consolidation. Roughly a quarter to a third of depth over 3–6 months. The
weekly and daily agree because they are the same base at two resolutions.

### THE GAP DAY, by the numbers (both charts)

| metric | value |
|---|---|
| open / high / low / close | 116.02–116.25 · 140.00–142.04 · 114.46 · 139.44–142.04 |
| change | **+79.08, +125.61%** (chart 2) · +76.48, +121.48% (chart 1, earlier snapshot) |
| volume | **41.4M vs 8.0M average — +5,595%**, RVOL **42.03×**, projected 226M |
| dollar volume | $6.6B day-1 · avg $V 1.137B |
| **ADR%** | **6.92%** (ATR% 6.36%) |
| **ATR multiple from MA** | **18.93 → 19.59** |
| **% gain from MA** | **120.60% → 124.53%** |
| Off 52-week high | **0.0% — it is AT its 52-week high** |
| U/D volume ratio | 2.03–2.1 (daily), 3.0 (weekly) |
| prior day close / high | PDC 62.97 · PDH 64.37 → the gap roughly DOUBLED the stock |

### 🔴 WHAT THIS SAYS ABOUT OUR OWN FILTERS — two direct collisions worth carrying

1. **EXTENSION: this name is ~19× ATR from its moving average and 124% above it, and he calls it
   PERFECT.** Our extension filter skips when the prior close sits ≥50% above the 5-day low
   (`ep_detector.MAX_EXTENSION_PCT`). MRNA passes only because the extension is created BY the gap —
   the *prior* close was consolidating. **The lesson is that post-gap extension is not a defect in an
   EP, it is the event.** Any extension rule must be measured on the PRE-gap state, never the gap day.
2. **THE BASE IS THE QUALIFIER, AND WE DO NOT MEASURE IT THIS WAY.** He is reading duration × depth
   (74d·27%, 26w·37%). Our structure work counts congestion zones cleared; his annotation is the
   containing base's *tightness over time*. **These are complementary, not the same number** — file
   against #569 (the structure-encoder split).

### THE 5-MINUTE CHART — the intraday half, and it is the 620 shape

The 5-min panel shows the gap open, a brief first-bar range, then a **staircase riding a rising
short moving average** with the pullbacks holding it. That is the same intraday structure as the
620 chart he shared on 08-07 (5-min, 6/20 EMA + MACD) — the trigger we have costed but never tested
(#562, the 574-ticker-day minute pull). **CDO marked at 116.25** (the day's open) acts as the
reference line; price never revisits it.

### ⚠ THE DISTINCTION HE DREW AND I CANNOT RESOLVE FROM THE IMAGES

*"To not be confused with a **PEG**."* He is separating EP from something abbreviated PEG. Our SSoT
does not define PEG anywhere. **ASK HIM** — this is a definitional line (SETUP vs FAMILY discipline,
CLAUDE.md) and guessing at it is exactly what that rule forbids. Recorded as an open question, not
answered.

### WHAT WE DID ON THE DAY
Scored **115.2 HIGH**, entered 09:31:09 at 120.75, banked the +2R partial the same day (+$17.71),
3 shares held at breakeven. MRVL scored 69.1 the same morning, was also entered, and stopped for
−0.87R — with the book at 5/5, **the ranking decided the outcome.** Full record: `ep_profitability_program.md` §0a.

### 2026-08-19 (same day, his answers to the two questions above)

**1. PEG = POWER EARNINGS GAP — and it is a DIFFERENT, WEAKER thing than an EP.**

> *"PEG is power earnings gap, a gap up after earnings. EPs are more powerful and rare."*

So the trader's *"not to be confused with a PEG"* is a **quality distinction, not a pedantic one**:
a gap after earnings is the common case; an EP is the rare, more powerful case. **The separator is
the CATALYST, not the gap** — an earnings beat is scheduled and expected-in-kind; an EP's catalyst is
something the market had no way to price.
▶ **This is the same axis as the expectedness work (#568)**: `expct_scheduled` marks 2.02/10-Q/10-K
as SCHEDULED, and a PEG is precisely a scheduled-catalyst gap. **The axis we shipped 08-18 is
therefore measuring the EP-vs-PEG line directly** — unscheduled reached ≥8×ADR 11.6% vs 3.8%.
⚠ Do NOT restate this as "EPs exclude earnings gaps" — he did not say that. He said EPs are more
powerful and rarer. Earnings can presumably still produce one; it is the bar that differs.

**2. THE BIG BASE IS A PROXY FOR NEGLECT — that is the mechanism, and I had it wrong.**

> *"i feel the point here is that there's a large base, so stock had time to build price structure
> and have a base to launch from if it so do so. Also, with a large base there's indication of
> neglect (at least there's no major movements up or down) so the news moving it significantly is
> truly unexpected and/or gamechanging."*

I transcribed the base as **tightness** (duration × depth). **He is making a different and better
point, and it has two halves:**

- **(a) A LAUNCHING PLATFORM.** Time spent basing = price structure built = something to launch
  FROM. Mechanical, and it is what the supply-ladder model already describes.
- **(b) 🔑 NEGLECT — and this is the half that matters.** A long base with **no major move in EITHER
  direction** is evidence nobody was paying attention. **So when news moves it hard, the size of the
  reaction proves the news was genuinely unexpected.** The base does not predict the move; it
  CERTIFIES the surprise.

**Why (b) reframes the whole selection surface:** it links three separate findings into one
mechanism we can state plainly.
- The expectedness axis (#568) tries to read surprise from the CATALYST's own text/form.
- **The base reads the SAME surprise from the PRICE — independently, and without needing to parse
  any news.** A neglected stock that suddenly moves 19×ATR is, by construction, reacting to
  something unpriced.
- His 08-16 RS-trajectory comment — *"the tail is where i'd expect neglect to form"* — is this same
  idea one level up, and the weekend read that winners were *quieter and less extended* is its
  measurable shadow.

▶ **WHAT TO MEASURE, and it is not what I first wrote:** not just duration × depth, but
**duration × QUIETNESS** — how long, and how little the stock moved in EITHER direction, before the
event. Absence of large up moves matters as much as absence of large down moves. **A tight base and
a neglected base are not the same object**, and the neglect reading is the one that carries a causal
story about why the reaction was large.
⚠ Still one case. MRNA is a reference example, not evidence — the test is whether a
duration×quietness term separates winners on the corpus.

---

## 2026-09-03 — HOOD: the catalyst we recorded was the smaller half of the story (operator-shared)

**Why this is here:** he shared an end-of-day summary from someone he follows on Twitter, and his
own read of what actually drove the move. Transcribed the same turn — chat compacts and shared text
is lost otherwise. Filed against **#210 (an accurate read of the news)**.

**His read, in his words:** *"today's EP HOOD we traded, the catalyst was analyst upgrades based on
prediction markets & robinhood chain, i believe the news on robinhood chain is the bigger driver.
Though we traded and marked it as high, and we did catch the chain news, but much of the key details
are missing so perhaps there's a potential gap on news sources, especially from social media, which
is hard to source."*

**What we got right:** we traded it, graded it HIGH, and we DID catch the Robinhood Chain news.
**What we missed: the substance underneath it** — and his hypothesis is that the chain story, not
the analyst upgrade, was the real driver. The upgrade is the *reportable* half; the chain data is
the half that explains the size of the move.

**The shared summary, verbatim** (Twitter, end-of-day stock recap account he follows):

> Robinhood $HOOD had its best day in over a year, rising 15% after a Morgan Stanley upgrade and
> renewed attention around Robinhood Chain. Part of the move may have come after Ansem, one of
> crypto's most influential voices, posted his Robinhood thesis to 1.3M followers, highlighting the
> company's growing onchain opportunity. Since launching July 1, Robinhood Chain has generated
> $34.6B in cumulative DEX volume, 576M transactions, and 12.3M addresses, with daily DEX volume
> recently hitting a record $1.5B and users paying $3.75M in fees on September 1. More than 190
> tokenized stocks are now live, producing over $3B in cumulative DEX volume, while RWA daily volume
> reached a record $390M, including $217M from memecoin/tokenized-stock pairs. Robinhood's onchain
> ecosystem has also grown to more than $750M in TVL while generating billions in perpetual-futures
> volume. The market appears to be waking up to the idea that Robinhood Chain may not be fully
> priced in, with the potential to become a new 9-figure revenue stream — and possibly much larger
> if growth continues.

### What this case is evidence FOR

1. **A named individual's post can be the proximate trigger.** The summary attributes part of the
   move to one crypto figure posting a thesis to 1.3M followers. **No source we currently read would
   ever surface that** — not SEC filings, not Benzinga wires, not the web synthesis. This is the
   gap he is pointing at, and it is a real one.
2. **The wire caught the LABEL, not the SUBSTANCE.** "Morgan Stanley upgrade" is what a wire
   reports. Every number above — cumulative volume, transaction count, addresses, fee revenue, TVL,
   the tokenized-stock count — is the actual argument, and none of it is in an upgrade headline.
   A catalyst read that stops at the label cannot tell a 15% day from a 2% one.
3. **It is a REVENUE-STAGE story told in operating metrics.** *"a new 9-figure revenue stream"* is
   exactly the shape the rubric's revenue axes want, but it arrives as onchain metrics, not as a
   guidance number — so nothing in the current stack can score it.

### The honest counter-position, to be argued rather than assumed

Social media as a catalyst source is **hard to source and easy to be fooled by** — that is his own
phrasing and it is the crux. Influencer posts are unattributed, unversioned, deletable, and
trivially gamed; a system that reads them can be fed. Any build here has to answer **how we know a
post moved a stock rather than followed it**, and the HOOD case cannot answer that on its own: the
Morgan Stanley upgrade is a confound, and the summary itself only says the move *"may have come
after"* the post.

⚠ **One case. HOOD is a reference example, not evidence** — same standing as MRNA above. The test is
whether a social-source leg separates winners across the corpus, not whether it explains this day.

---

## 2026-09-05 — WHAT FUNDAMENTALS ACTUALLY MEASURE, and the non-earnings EP problem

Said after a day of rubric analysis that found the catalyst rubric passes real EPs but cannot
separate them from lookalikes with identical fundamentals. **Two rulings, both durable, both
governing every future review of the catalyst rubric.** Verbatim:

> "I'm mostly aligned that fundamentals are not enough, b in theory is the gap between the
> fundamentals vs the expectation, which is partly expressed in the gap on day one, future price
> rise is the continued closing vs expectation.
>
> bfly is a concern, earnings EP is just one type, we can't penalize non earnings EP with this.
> Mrna is a middle case where there is earnings but the real driver is the vaccine news that day."

### 1. The model: the edge is SURPRISE, not absolute quality

**Fundamentals are only meaningful relative to what was already expected.** The tradeable quantity
is the *gap between fundamentals and expectation*, and:

- **Day one's gap size is a partial expression of that gap** — the market's first repricing of it.
- **Continued price rise is that gap continuing to close**, as expectation catches up to reality.

**This explains the 2026-09-05 null directly, and it is why it is a model rather than a hypothesis.**
We measured absolute revenue growth against forward returns and found nothing usable: 93% growth
(PLTR) worked, 50%+ growth as a band was the *worst* performer (32% still up), and the best band on
median (10-15%) had the fewest big winners. **Under this model that is the expected result** — 93%
growth that was *anticipated* is already in the price, and 12% growth that *nobody expected* re-rates
the stock. An absolute-magnitude axis cannot tell those apart, so it measures the wrong thing.

⚠ **The rubric's axes are all ABSOLUTE-magnitude** (revenue YoY, EPS trajectory, margin trajectory,
milestone) **except axis 4, beat-vs-consensus, which is the only true surprise measure in it.** That
is a testable consequence of his model and it is the shape of the next real question here.

### 2. Earnings is ONE type of EP. Non-earnings EPs must not be penalised for it.

**BFLY 2026-06-18 is the standing counterexample** and he has now called it a concern twice (the
first was the 2026-06-19 HARD label, `operator_labelled_eps.md`). It was downgraded
`strong` → `routine` on `news_corpus_sparse_no_q_rev` — the safety-net gate — because a *partnership*
catalyst has no quarterly revenue line. **We penalised it for missing data it could never have had.**
The same gate stands in front of every FDA decision, M&A event and partnership.

**MRNA is the middle case, and he named it as such:** there WERE earnings, but the real driver was
the vaccine news that day. **So "did this name report earnings" is not even a clean partition** — a
name can have earnings present and irrelevant. Any fix that just branches on "is this an earnings
catalyst" will mis-handle MRNA.

**Consequence for the rubric: the earnings axes may only judge a name whose MOVE is driven by
earnings, and absence of earnings data must never itself be evidence of a weak catalyst.** What
replaces it for a non-earnings EP is an open design question — not a threshold change.

🛑 THE LINE: the safety-net gate and the axis set are DETECTION CRITERIA. These rulings define the
intent; any implementation still needs CHANGE_PROCESS + backtest + his sign-off.

---

## 2026-09-06 — EIGHT CHART RULINGS, verbatim (review sample #1, #594)

I surfaced ten (ticker, date) pairs where our score and the outcome disagreed. He ruled on eight.
**Captured the same turn he wrote them** — [[capture-operator-shared-notes]]. Verbatim:

> 1. nvtx - chart is ok but there's a double top from Oct 2025 that it didn't clear, in fact, that
>    probably played out as resistance and it failed
> 2. nvts - looked good for one day but it failed to make new highs and quickly dropped lower,
>    closed on bottom of range on EP day. It was still ok until 3rd day it opened and dropped all
>    day to close at lows.
> 3. mrln - garbage chart, in downtrend, gapped didn't clear anothing, clear resistance and chop in
>    the area, poor chart
> 4. omer - ok'ish, didn't clear level and still in base but did clear all key moving averages
>    10/20/50 and 200 day. Another good gap up on 8/13 which held
> 5. abvx - absolute garbage
> 6. cgem on 6/8 is garbage, possible EP day is 6/22
> 7. RNG - looks good, stock been in a long base since 2022 and this gap cleared most of it into
>    top of previous range highs over multiple years, closed near high of day and just kept going,
>    moved above all moving averages on gap day, looks great
> 8. Avah - 6/2 day looks like garbage, gap on 8/13 looks excellent, cleared everything and into
>    new highs, sitll holding up

### The criteria he actually applied — read off the eight, not invented

**1. DID THE GAP CLEAR OVERHEAD SUPPLY? This is the first question in six of the eight.**
- NVTX: *"a double top from Oct 2025 that it didn't clear… that probably played out as resistance"*
  — **an eight-month-old level was the binding one.** Our lookback is nowhere near that.
- MRLN: *"gapped didn't clear anothing, clear resistance and chop in the area"*
- RNG: *"cleared most of it into top of previous range highs over multiple years"* → his best chart.
- AVAH 08-13: *"cleared everything and into new highs"* → *"excellent"*.
- OMER: *"didn't clear level and still in base"* — but survives to "ok'ish" on the MA criterion below.
⚠ **"Cleared" is measured against MULTI-YEAR structure — a 2022 base for RNG, an Oct-2025 double
top for NVTX. [[structure-is-a-supply-ladder]]: count the congestion zones a gap CLEARS.**

**2. WHERE DID IT CLOSE ON THE DAY?**
- NVTS: *"closed on bottom of range on EP day"* → the tell, on a day that "looked good".
- RNG: *"closed near high of day and just kept going"*.
**Close-within-day-range is a same-day, computable fact we do not currently score.**

**3. POSITION VS THE MOVING AVERAGES (10/20/50/200).**
- OMER: *"did clear all key moving averages 10/20/50 and 200 day"* — this alone lifts a chart that
  failed criterion 1 from garbage to "ok'ish".
- RNG: *"moved above all moving averages on gap day"*.

**4. THE PRIOR TREND.** MRLN: *"in downtrend"* → garbage before anything else is considered.

**5. WHAT HAPPENED AFTER, as part of the verdict.** NVTS: *"still ok until 3rd day it opened and
dropped all day to close at lows"* — he dates the failure precisely rather than condemning the setup.

### ⚠ TWO DATE CORRECTIONS — the "he judges the DAY" rule, again

- **CGEM: 06-08 is garbage; *"possible EP day is 6/22"*.**
- **AVAH: 06-02 is garbage; *"gap on 8/13 looks excellent"*.**
- **OMER: a second gap on **08-13** which HELD** — the same date as AVAH's good one.
Our system scanned the bad dates in both cases. **Two of eight rulings say we looked on the wrong
day** — the single most repeated finding in this whole programme.

### 2026-09-06 (same session) — "switch to higher time frame for longer term bases"

> "for longer term bases, perhaps switch to higher time frame to see the larger pattern, ie weekly
> or even monthly charts"

**He is right, and it is currently IMPOSSIBLE for a reason that is not the timeframe.**

**`mi_daily_closes` begins 2025-08-04 — THIRTEEN MONTHS of history, 14,721 tickers.** Aggregating
those dailies into weekly or monthly candles yields ~57 weekly or ~13 monthly bars. That is not a
higher timeframe in any useful sense; it is the same 13 months drawn coarser, and it cannot reveal
a pattern that predates the window.

Measured against his own two rulings from the same session:

| his reasoning | earliest bar we hold | can we see it? |
|---|---|---|
| **RNG** — *"a long base since 2022… cleared most of it into top of previous range highs over multiple years"* | 2025-08-04 (275 bars) | ❌ **NO. The entire basis of the only chart he has ever called outright good is outside our data.** |
| **NVTX** — *"a double top from Oct 2025 that it didn't clear"* | 2025-09-09 (250 bars) | ⚠️ barely — Oct-2025 sits ~1 month inside the window, with no prior context to judge it against |

**So the blocker is DATA DEPTH, not chart interval.** Switching to weekly candles over the same 13
months gains nothing; what is missing is years of bars. The fix is a **multi-year daily backfill**
for the names we evaluate (Polygon and Alpaca both serve years of daily history and we already pay
for both), after which weekly/monthly aggregation becomes a real option rather than a relabelling.

⚠ **And this reframes the 2026-08-25 structure-read null.** The supply read measured 0.496 — a coin
flip — against his labels. It was computed on ≤13 months of bars while he is judging multi-year
structure. **A null measured on a window that cannot contain the pattern is not evidence the
pattern is absent.** [[shadow-zero-effect-check-instrumentation]] · [[structure-is-a-supply-ladder]]

### 2026-09-06 (same session) — the idea the backfill unlocks: open-ended chart reading

> "with this data, i think we can expand the review and do more open ended chart vision reading,
> look at what bases look like, what break out looks like, what holds up and how it correlates
> with EPs we find, thats an potential idea"

**Flagged by him as a POTENTIAL idea, not a commitment — recorded as a direction.**

**What changes it from impossible to possible is the 5-year backfill** (approved and run the same
day). Everything below needs multi-year structure and none of it could be asked on 13 months.

**The shift it proposes is from JUDGING to CHARACTERISING.** Review sample #1 asked him a closed
question — is this date good or bad — on ten names we picked. He is describing the opposite: look
at the population and ask what the shapes actually ARE.

Four questions, in his words, and each is a different study:

1. **"what bases look like"** — a taxonomy of the accumulation structures that precede EPs. Length,
   depth, tightness, volume behaviour. Today we have no vocabulary for this beyond `extension_pct`.
2. **"what break out looks like"** — how a real break out of a base differs from a gap that stalls.
   His RNG ruling is the worked example: *"cleared most of it into top of previous range highs over
   multiple years, closed near high of day and just kept going."*
3. **"what holds up"** — the post-gap survival question. AVAH 08-13 *"still holding up"*; NVTS *"was
   still ok until 3rd day"*. **He dates the failure, which means holding-up is measurable per day
   rather than as one outcome.**
4. **"how it correlates with EPs we find"** — the join back to our own alert population. This is the
   one that makes it a system change rather than chart study: if a base shape predicts which of our
   EPs work, it becomes a selection input.

⚠ **THE TRAP THIS MUST AVOID, and it is the lesson of 2026-09-05: with ~30 labelled names and a
free hand over multi-year charts, a favourable pattern is trivially findable and worthless. Any
shape proposed from looking must be declared BEFORE it is measured, and measured on the TAIL, not
the median** (`analysis_standard.md` §THE STATISTIC). [[measure-the-tail-not-the-median]]

⚠ **And it must be checked against `must_not_miss_eps.py` before anything else** — the running list
of real EPs may never shrink. That guard already exists and stays in the loop.

## 2026-09-13 — reflexivity makes "was the theme the driver?" ambiguous for a LEADER

**His words, finishing the 44 themed labels:**

> *"one challenge I faced was that of reflexivity, some of these stocks drives the theme
> because they may be one of the leaders while the theme may drive the group, so it's a bit
> complicated, did what I can"*

**Why it matters: a `n` can mean two different things, and pooling them gives the wrong answer.**

| the `n` means | what it is | what to do about it |
|---|---|---|
| we credited a theme that was not the driver | a **false positive** — the theme axis over-credited | tighten the axis |
| this stock IS the leader; it drove the theme | **reflexivity** — the label is descriptively true, causally backwards | not a filter error; the arrow points the other way |

This is the same constraint already recorded for RS and EP (*a gap manufactures relative
strength*), arriving from the labelling side. **Never quote a themed precision number without
saying which of the two it is measuring.**

### ⚠ The obvious mechanical test FAILS — measured, not assumed

If a leader predated its theme, the theme could not have driven it. So: does the alert land
before the theme's birth? **Zero of 44.** Every alert came after its theme already existed —
median 22 days after. That operationalisation of his point rescues nothing.

The founder split is nearly as weak: tickers that were **founding members** of their theme label
`y` at **52%** (14/27); tickers that **joined later** at **41%** (7/17). An 11-point gap on tiny
n, both near a coin flip.

**So the concern is real but this is not its shape.** The sharper test his words actually imply:
on the alert date, did the theme's OTHER members move too? Group moves together → the theme is
driving. Only this name moves → the name is driving. That is a co-movement question, it is $0
from `mi_daily_closes`, and it is the one that should gate the theme-boost magnitude.

### The number his labels actually produced

**21 yes / 23 no on 44 alerts — 48% — under the CURRENT engine.**

⚠ **Do not pool this with the older 49y/9n (84%).** Those 59 rows are the pre-scrap cohort,
enrolled under an engine state we no longer run — the exact era error that has bitten this repo
before. The honest read of today's engine is 48%, not the 68% a pooled 70/103 would print.

[[check-the-rule-era-before-comparing-to-actual]] · [[themes-not-judged-on-returns-yet]]

## 2026-09-13 — HOOD: a stock can have several drivers and the engine names one

**His words, on why he labelled HOOD `n` despite 19 peers moving with it:**

> *"On Hood, the theme of wealth management is only partially correct, Hood also moves with crypto
> sometimes, and long with the market during high speculative times, so that's why I said no to
> that particular theme"*

**Checked on prod the same turn, and it holds mechanically:**

- **HOOD has only ever belonged to ONE theme** — *Wealth Management & Retail Brokerage Platforms*.
  Never a crypto grouping, never a speculative/high-beta one. The engine has one slot and HOOD
  needs three.
- **Across the whole board, only 37 of 679 tickers (5.4%) sit in more than one theme.** Nothing
  forbids multi-membership; it simply almost never happens. The engine is *de facto*
  one-theme-per-stock.

### This is a FOURTH thing an `n` can mean, and it is structural

| the `n` means | what it is |
|---|---|
| no theme drove it | false positive — tighten the axis |
| the stock drove the theme | reflexivity — the arrow points the other way |
| the theme is real but mis-named / wrong members | naming or membership |
| **the theme is ONE OF SEVERAL drivers and we can only name one** | **structural — the engine cannot express what he knows** |

**The question "was the theme the driver?" presumes a single driver.** For a multi-driver name it
is not answerable as posed, and his `n` is the most accurate answer available to him.

### ⚠ And it breaks the co-movement rule in a specific, fixable way

The co-movement test subtracts **SPY**. His phrase *"long with the market during high speculative
times"* names a factor SPY does not carry: risk appetite. If HOOD and 19 brokerage peers all rose
because speculation rose, the test reads "the group moved together" and credits the theme.

**SPY-adjustment is not enough for high-beta names.** The fix is the null control the theme
programme already specifies: does the theme's group move together **more than a matched set of
similar names that are not in the theme**? Without it, "the group moved" and "everything like this
moved" are indistinguishable — which is the same defect class as an alarm that cannot fail.

Related: the birth gate's own copy of `co_moving` is market-adjusted while the shared helper is
not — a filed doc-vs-code gap that now has a second reason to be closed.

[[his-theme-labels-are-supplementary]] · [[theme-north-star-early-rs-before-mainstream]]

## 2026-09-13 — coverage is NOT the goal; he stated the goal in two parts

> *"hold on, we don't have 100% coverage that is not the goal otherwise every gap will get
> boosted, our goal is to 1) boost the real EPs if there's a real theme attached and 2) the
> reflexive part, source new themes from the gap ups, this case may be an early mover in a theme
> bringing up the whole group for example. So low'ish coverage may not be a bad thing provided we
> catch the real EPs, the exact % i don't know"*

**This kills the framing I had been measuring against.** I reported "289 of 600 strong names have
no theme — 48%" as the problem. It is not a problem statement at all: **at 100% coverage every gap
gets boosted and the boost carries zero information.** Market-wide coverage is the wrong
denominator and a higher number is not automatically better.

### The two goals, and the measurement each one implies

| | goal | the right denominator |
|---|---|---|
| **1** | boost the **real EPs** when a **real theme** is attached | his own labelled real-EP list — did we have the theme on the day? |
| **2** | **source new themes from the gap-ups** — an early mover can be the start of a theme that later lifts the group | of gap-ups with no theme, how many later seeded a real one? |

He explicitly does not know the right coverage %, and it is **an output, not a target**.

### Measured against goal 1 the same turn — and it found something structural

Of his 7 labelled real EPs, **3 had a theme on the day**. But the sharper finding is in the other
column:

```
BFLY 06-18  theme: Physical AI & Robotics            (Fading)
PLTR 08-04  theme: U.S. Gov/Defense Spending Surge   (Nascent)   in_active_theme = FALSE
MRNA 08-19  theme: mRNA Vaccine & Therapeutics       (Nascent)   in_active_theme = FALSE
TEAM 08-07  no theme that day — themed LATER (Software Development & DevOps)
HTFL 08-14  no theme that day — themed LATER (AI-Driven Diagnostics & Imaging)
ABNB 08-07  never in any theme
CHPT 09-03  never in any theme
```

🔴 **`in_active_theme` counts ONLY Accelerating or Mainstream themes** (`ep_detector.py:1568`).
**PLTR and MRNA were both in NASCENT themes we had correctly found — and the boost did not fire.**
Those are two of his strongest labelled EPs (+15.5% and +84.3%).

**The boost excludes exactly the early stage his north star is about.** "Subtle RS → early theme →
buy before it is obvious" — and the bonus only switches on once a theme is already Accelerating or
Mainstream, i.e. once it is no longer early. The engine found the theme; the rubric ignored it.

⚠ The same docstring already records that the bonus is **decorative** at the current threshold: *"0
MODERATE-in-theme alerts would have crossed to HIGH"* over 60 days.

**TEAM and HTFL are goal 2's case:** both got their theme LATER. Their gap is precisely the
"early mover that brings up the group" he described, and nothing routes a gap into theme creation.

[[his-theme-labels-are-supplementary]] · [[theme-north-star-early-rs-before-mainstream]] ·
[[operator-labelled-ep-list]]

---

## 2026-09-17 — HTF labelled example: $MRNA, shared by the operator

**Source:** Leif Soreide (@LeifSoreide) on X, 17 Sep 2026 07:53, 4.9K views. Chart is his, dated
**Wed 16-Sep-2026 10:38 am** — i.e. the setup as it stood BEFORE that day's move.

**🖼 Images stored in-repo** (the uploads directory is session-scoped and does not survive —
this is the failure mode that lost the 620 chart, so the files are committed, not just cited):
- `docs/methodology/images/mrna_2026-09-16_htf_stockcharts_daily.jpg` — his annotated daily:
  the 170.3% pole marker, the 26.2% flag depth marker, the flag rails, and the ATR(14)
  down-trendline.
- `docs/methodology/images/mrna_2026-09-17_htf_soreide_post.png` — the post itself, so his
  wording is preserved as primary source rather than only as my transcription.

> **"$MRNA High Tight Flag.**
> Wanted closer to 5 weeks because the flag was a touch deep (~26%), but that was mostly one stretch
> day (~1% over).
> Yesterday's chart from before today's move. Today it moved from the Breakout Watch spot"

### What his chart actually marks

| | |
|---|---|
| **Pole** | **170.3%**, measured off the ~$63–65 base into the spike high (~$175). The whole move is essentially **ONE GAP DAY around 2026-08-18/19** on ~200M shares |
| **Flag** | **26.2% deep** — high ~$175 down to ~$132 — over roughly **4 weeks** (19 Aug → 16 Sep) |
| **His tolerance** | wanted **~5 weeks**; accepted 4. Called 26% *"a touch deep"* and discounted it because the excess was **one stretch day, ~1% over** his bar |
| **Trigger** | *"Breakout Watch spot"* — the flag's upper rail, ~$150–155 |
| **Quote** | last 145.71 (+1.35%), open 145.32, H 146.75, L 142.67, prev close 143.77, vol 2.03M |
| **Structure** | EMA8 143.40 · EMA21 132.07 · MA50 94.93 · MA200 58.94 — price over a fanned stack |
| **Strength** | SCTR **99.7**; price performance vs $SPX **+187.28%** |
| **Volatility** | **ATR(14) 11.426 and FALLING** — he draws a red down-trendline on the ATR pane. Contraction inside the flag is part of the read, not decoration |
| **Fundamentals** | Mkt cap 57.4B, EPS **−8.01**, no dividend. Last earnings 2026-07-31, next **2026-11-05** — so the flag sits clear of an earnings date |

### 🔑 WHAT OUR OWN BOARD SAID — checked before theorising, and it refutes my first guess

`mi_flag_candidates`, MRNA, every scan day 2026-08-17 → 09-16. **We saw it all 23 days and rejected
it all 23 days.** My first draft of this note guessed the pole WINDOW was the binding constraint.
It is not — the pole passes easily. [[check-what-the-system-already-did]]

| window | our stage | our stated reason |
|---|---|---|
| 08-17 → 08-19 | unqualified | `runup_58%_below_90%` — pre-gap, no pole yet |
| 08-20 → 08-24 | unqualified | `base_age_0/1/2_below_3` — flag too young |
| **08-25 → 09-15** | unqualified | **`flag_low_128.61_below_75%_of_pole_176.66`** — 15 consecutive days, one reason |
| **09-16** | **INVALIDATED** | **`close_145.62_below_sma20_145.67`** |

**🔴 THE BINDING CONSTRAINT IS FLAG DEPTH, AND WE MISS BY ABOUT TWO POINTS.** Our rule wants the
flag low to hold **≥75% of the pole high** — a 25% maximum retracement. MRNA: 128.61 / 176.66 =
**72.8%**, a **27.2%** retracement. **He called it 26.2% and took it anyway**, in his own words
because the breach was *"mostly one stretch day (~1% over)"*. Our gate has no such notion: it reads
the extreme bar and rejects. **The pole was never the problem — `runup_pct` reads 2.4 (240%) against
a 90% floor.**

**🔴 AND THE INVALIDATION FIRED BY FIVE CENTS, THE DAY BEFORE HIS BREAKOUT.** On 09-16 we killed the
setup on `close 145.62 below sma20 145.67`. That is a **$0.05** margin on a $145 stock — 0.03% — and
his tweet the next morning says *"Today it moved from the Breakout Watch spot."* So we did not merely
decline to flag it; we actively retired it one session early, on a rounding error.

### Why this matters to #610 / #592

| example | pole | flag depth | our verdict | what actually blocked it |
|---|---|---|---|---|
| **HNGE** (in `tests/fixtures/htf_labelled.py`) | +103% / 49 sessions | — | miss | pole outside the sourced 4–8 week window |
| **MRNA** (this one) | +240% / ~1 session | 27.2% | miss, then INVALIDATED | **flag-depth floor**, then a 5-cent SMA20 kill |

**Two shared names, two different gates — so there is no single knob, and that is the finding.**
HNGE argues about the pole window; MRNA never reached that argument. Anyone reasoning about the
detector from HNGE alone would tune the wrong thing.

⚠ **Recorded as observations, NOT proposals. Both gates are admission criteria — his sole authority
(THE LINE).** Two mechanical differences are now measured and named, and the ruling is his:
1. **A depth gate has no "one stretch day" allowance.** He discounts a single bar that pokes ~1%
   through; we read the extreme and reject. That is a difference in KIND, not a threshold argument.
2. **An SMA20 invalidation has no margin.** A 0.03% breach retires a setup as surely as a 5% one.

⚠ Neither observation says our numbers are wrong. 75%-of-pole and the SMA20 stop may both be
correctly excluding names that do not pay — that is what #610's both-directions read is for.
[[htf-tweets-are-a-tuning-corpus]] · [[htf-is-detection-not-trading]] · [[rising-volume-is-a-diagnosis-not-a-revert]]

---

## 2026-09-17 — ACVA is a BUYOUT, and the brief called it a theme-engine coverage gap

**Operator, on the evening brief's line `⚓ Unanchored persistent (5-session, RS≥90) — entered: ACVA`
and its footer `theme-engine coverage gap — no theme claimed these names all week`:**

> *"From evening brief, but stock is being bought out."*

He is right, and **our own bars already say so** — no external data needed.

### The two-leg deal signature, in data we already have

| leg | ACVA |
|---|---|
| **1. announcement** | **2026-09-11: +44.2% on 114.9M shares** against a ~3M-share norm (peak RVOL **28.7×**) |
| **2. the pin** | every session since trades in a **0.19–0.48% daily range**, closes 10.41 → 10.48. Daily changes: 0.00%, +0.19%, −0.10%, +0.58% |

A cash deal price. Before 09-11 the stock ranged 4–8% a day; after, it cannot move.

### 🔴 What it did to the RS board

| | |
|---|---|
| 2026-09-10 | rank **1084**, RS 54.2 |
| 2026-09-11 | rank **7**, RS 99.7 |
| through 09-17 | rank 7 → 7 → 10 → **17**, RS still **99.3** |

**One deal gap moved a name from rank 1084 to the RS top-10, and it will hold a top rank for the
months until the deal closes** — because RS is a backward-looking 1M/3M/6M percentile and the
forward path is a flat line. It displaces real leaders for as long as it sits there.

### ⚠ EIGHT names, not one — this is a class

Screening today's RS ≥ 90 population for **4 consecutive sessions under a 1% daily range**, then
requiring the announcement leg as a control (low range ALONE is just a sleepy stock):

| ticker | RS rank | biggest up-day | peak RVOL | avg range since 09-11 |
|---|---|---|---|---|
| ACVA | 17 | +44.2% | 28.7× | 0.35% |
| UTZ | 95 | +88.7% | 31.0× | 0.35% |
| CBZ | 157 | +17.6% | 24.1× | 0.24% |
| ITGR | 160 | +20.2% | 23.4× | 0.21% |
| SAFT | 182 | +41.5% | 13.9× | 0.16% |
| BWMN | 193 | +55.8% | 20.0× | 0.28% |
| ATKR | 200 | +28.2% | 25.7× | 0.28% |
| MKTX | 228 | +29.5% | 18.2× | 0.21% |

**All eight carry both legs.** The discriminator is cheap and needs no new data:
**one >15% day on >10× volume, followed by ≥4 sessions under a 1% range.**

### What is and is not wrong

✅ **The money path is clean** — verified: zero `mi_ep_alerts` rows, zero `mi_live_trades` rows for
ACVA. The EP side never touched it.

### 🛑 CORRECTION, same evening — operator: *"We have m&a validation"*

**He is right and I should have grepped before writing the section above.** I called this an
"unmodelled exception" and presented the range-collapse discriminator as if it were a finding. **Both
already exist in this repo**, and one of them is character-for-character the check I "found":

| existing mechanism | where | what it does | cost |
|---|---|---|---|
| **M&A news classifier** | `parabolic_detector._news_check_for_exclusion` + `_NEWS_CHECK_PROMPT` | asks Perplexity *"has there been a buyout, acquisition, merger…"*, parses `event_type: buyout\|acquisition\|merger\|fda\|lawsuit\|earnings\|other\|none`, and **excludes M&A from alert-worthy stages**. 14-day TTL cache, concurrency capped at 3 | **PAID** (Perplexity per call) |
| **merger-arb pin guard** | `db.get_eod_9m_sugar_babies` | *"intraday range >= 2% of close (**rejects merger-arb pins like DBRG**)"* | **$0**, structural |

**So the accurate statement is not "we have no M&A handling" — it is that we have it TWICE and
NEITHER is wired to the RS leaders board.** `_news_check_for_exclusion` is `_`-private to
`parabolic_detector` with no external caller; the range guard sits inside the **retired 9M** path.
The unanchored/persistent surface references neither. [[check-what-the-system-already-did]]

**That makes the situation better, not worse: the fix is REUSE, not invention**, and the $0 leg is
already proven in-repo with its own named example (DBRG). My eight-name screen is best read as
independent confirmation that the existing 2%-range rule generalises — all eight clear it by a wide
margin, averaging 0.16–0.35% against a 2.0% bar.

### 🔴 What remains genuinely wrong

**The brief's footer asserts a diagnosis the data contradicts.** *"Theme-engine coverage gap — no
theme claimed these names all week"* is false for this class: a company being acquired is
**definitionally un-themeable**. `brief_composer._persistent_unanchored_material`'s docstring states
the premise — *"A name that survives 5 straight sessions with no theme claiming it is a THEME-ENGINE
COVERAGE GAP, not routine churn"* — and that premise is simply not true for deal-pinned names. It
sends me at work that does not exist.

⚠ **The RS contamination is the larger half** and is not confined to the brief: the leaders list
feeds theme discovery and every RS-ranked surface. Eight pinned names sit in the RS ≥ 90 population
right now, one of them at rank 17.

⛔ **Nothing changed.** Which names a surface admits is an admission criterion — his sole authority
(THE LINE). Filing is his call too: the board is at its ceiling, and a carryover is
operator-initiated, never agent-proposed.
[[check-our-code-before-blaming-the-world]] · [[rising-volume-is-a-diagnosis-not-a-revert]]

### Theme impact of excluding deal-pinned names — measured 2026-09-17 on his instruction

**4 of the 8 sit in a live theme; 4 are unanchored** (ACVA, ATKR, BWMN, MKTX).

| theme | stage | members now | pinned | after | effect |
|---|---|---|---|---|---|
| **Management & Business Advisory Consulting Firms** | **Mainstream** | **2** `{HURN, CBZ}` | CBZ | **1** | **theme dissolves** |
| Emerging Medical Device Innovators Breakout | Fading | 3 `{ITGR, ATEC, INSP}` | ITGR | 2 | below the 3-member floor |
| Specialty P&C Insurance Underwriters Rotation Reversal | Nascent | 17 | SAFT | 16 | none |
| Defensive Consumer Staples Rotation | Fading | 17 | UTZ | 16 | none |

### 🔴 A BUYOUT PROMOTED A THEME TO MAINSTREAM — and Mainstream is the stage the EP boost reads

`Management & Business Advisory Consulting Firms` is **two names**, `{HURN, CBZ}`, and CBZ is the
deal. Its `rs_avg` climbed **80.3 → 83.7 → 88.2 → 90.1 → 92.9** across 09-10 → 09-16, and it
**graduated Nascent → Mainstream on 2026-09-15**. That climb is CBZ's +17.6% announcement day on 24×
volume being averaged into a two-name theme.

**`in_active_theme` counts ONLY Accelerating or Mainstream** (`ep_detector.py:1568`) — it is the flag
behind the EP theme boost. So if HURN alerts, it collects a theme boost from a theme that is
Mainstream **because its other member is being acquired.** I said earlier the money path was clean;
that was true directly (no ACVA alert, no trade) and **not true indirectly** — this is the path.

⚠ Also surfaced, not chased: the theme holds **2 members while `_PROMOTE_MIN_MEMBERS = 3`**, so the
floor evidently does not bind after birth. Separate question, recorded not investigated.

**Read on the exclusion: the two theme losses are a FEATURE.** One is a deal artefact that reached
Mainstream on the deal; the other is a 3-name Fading theme. Neither is evidence against excluding —
but both are visible board changes, which is why he asked.

## 2026-09-23 — 13 marked-up TraderLion charts of 2020 leaders, operator-shared (photos)

**Full transcription and synthesis: `docs/methodology/traderlion_2020_leaders_2026-09-23.md`**;
images in `docs/methodology/operator_shared_charts/2026-09-23_traderlion_2020_leaders/`. He shared
them as the marked-up charts he owed, before deciding on the chart-vision spend (#519). CRWD, FVRR,
ETSY, DOCU, PTON, PINS, NIO, SQ, SNAP, RARE, ZM, Z, TSLA — where to buy, add and sell on a leader:
pivot breakouts from proper bases (≥5 weeks flat, ≥7 other), pocket pivots, constructive shakeouts
to the MA each stock respects, sells on closes below that MA, and failure-prone shapes (too fast up
the right side, stage 3, wide and loose). Winners only — they teach the read, not the failure rate.

## 2026-09-23 — 11 leaders through their run AND their top (John Boik, *Monster Stock Lessons*), operator-shared (photos)

**Full transcription and synthesis: `docs/methodology/boik_monster_stock_lessons_2026-09-23.md`**;
images in `docs/methodology/operator_shared_charts/2026-09-23_boik_monster_stock_lessons_2020_2021/`.
His words: *"Here's stocks that went up, topped and subsequently went down"* — the failure examples,
shared right after the TraderLion winners. ZM, PTON, DOCU, PDD, NIO, FSLY, GRWG, ROKU, FVRR, PINS,
DKNG, each 2020 run over 2021 decline. The tops share: price cutting through both the 21- and 50-day
on heavy volume, those averages then acting as resistance, climax runs, volume drying up or flipping,
and chop. FVRR 2020 is the caution: the same heavy-volume break was an add when it reclaimed fast.

## 2026-09-24 — charts support a decision, they never make it (operator note, verbatim)

> *"One note is that, like everything else, charts are not 100%, there's no perfect accuracy or
> predictive value with charts so there's ones that work and ones that don't, we need to account for
> it and can't make definitive statements either way, charts can only help/support"*

- **Applied the same turn to #519's chart read** (`docs/analysis/519_paid_run_scoping_2026-09-24.md`):
  the pass bar went from a filter (one real EP read "bad" = fail) to a LEAN (how much more often it
  reads "bad" on his condemned charts than on the ones that worked). Revised before anything ran.
- **General rule:** a chart read, his or a model's, is a supporting input to a decision. Score it as
  a lean over a population, never as a verdict on one chart; never let it block on its own.

## 2026-09-24 — CDNA high tight flag follow-up (Leif Soreide tweet + MarketSurge chart), operator-shared

- **Images:** `docs/methodology/operator_shared_charts/2026-09-24_htf_cdna_leif_soreide/` (`01_tweet.jpg`, `02_marketsurge_daily.jpg`).
- **Tweet, verbatim (2026-09-24 11:37 AM):** *"$CDNA High Tight Flag. Took a first scale after a few risk multiples. Still long. Name is extended and the greater genomics theme is still hot. This is not the kind of action you typically see when you should be on the sidelines. Leaders that keep paying while the average stock looks soft are exactly the kind of follow-through I want on the board for the next high tight flag masterclass. @RichardMoglen"*
- **Chart marks:** pole 6/22 close 25.05 → 8/3 high 49.76 (+99%, 30 bars); flag 8/3 → 8/17, high 49.76 / low 45.02 (−9.5%, 11 bars); a second shelf topping at 53.67; 9/24 at $62.61, +15.3% on +144% volume, RS 99, "+169% from pivot in 78 days".
- **Role:** a labelled HTF example for the detector (his rule 2026-08-25), the same name he shared on 08-25. Our board's read on every date is in `docs/analysis/htf_surfacing_gap_2026-08-25.md` §CDNA follow-up: TIGHTENING on both flags, never COILED, so neither breakout could trigger. HTF stays behind EP.- **Source weight (operator, same day):** *"This author specializes in htf so these examples are good study."* Leif Soreide (@LeifSoreide) posts are a primary study source for the HTF detector: save each one he shares with its images, record our board's read on the dates, and keep them together as the HTF reference set.

## 2026-09-25 — charts are the basis of his trading: discretionary, imprecise by design, critical (verbatim)

> *"Ok, align with a pause here but not a full stop, we need to figure out how best to incorporate
> charts as that is the basis of my trading, is discretionary and imprecise by design but critical
> nonetheless"*

- Said on the #519 option A result (`docs/analysis/519_option_a_result_2026-09-25.md`): a model's chart
  read leaned the right way but weakly. The paid path is PAUSED, not stopped.
- **Standing frame for any chart work:** the goal is how charts enter the process, not whether a
  machine passes a test. Pairs with his 09-24 note that charts only support a decision.

## 2026-09-24 — MRNA high tight flag (PBA @801010athlete tweet), operator-shared

- **Image:** `docs/methodology/operator_shared_charts/2026-09-24_htf_mrna_pba/01_tweet.jpg`.
- **Tweet, verbatim (2026-09-24 6:50 PM):** *"Who knows what happens but this is a model book looking HTF. $MRNA"*
- **Chart marks:** $194.82, +40.78 (+26.4%) at 4:00 PM ET 09-24; *"+128% from Pivot in 6 weeks"*; base 43.68–59.55; an earlier low 22.28 (Dec 2025); RS 99.
- **Our board:** rejected every day of the flag on depth (flag low 27% under the pole's high; the rule allows 25%) — `docs/analysis/htf_surfacing_gap_2026-08-25.md` §MRNA.

## 2026-09-26 — true EPs we were stopped out of, that kept working (operator, verbatim)

> *"If you recall, we were stopped on team but I traded it myself after and it's still on. Mrna is another
> one still working after we got stopped"*

Our live trades, read from `mi_live_trades` the same day:

| stock | EP date | our entry | what happened to our trade | price 2026-09-25 |
|---|---|---|---|---|
| TEAM | 2026-08-07 | $147.13, stop $143.21 (the opening-range low) | stopped at $143.14 at 09:43 ET, twelve minutes after entry (−$23.94) | $187.74 (+28% from our entry); he re-entered himself and still holds |
| MRNA | 2026-08-19 | $120.75 | partial at $138.46 the same morning, stop to breakeven, trailed out at $145.20 on 09-03 (+$90.79) | $198.88 (+65% from our entry) |

- **Two different failures on true EPs:** TEAM = stopped by opening noise on day one; MRNA = caught, but exited
  early on the trail while the move doubled again.
- **Use:** named cases for the winners study (which EPs are the real ones, and how to trade them) and for
  EP exit discipline (#508). Both are on his labelled real-EP list (`tests/fixtures/must_not_miss_eps.py`).

## 2026-09-27 — delayed-EP entries and stops: pivot proximity, and close-based mental stops (operator, verbatim)

> *"A couple more ideas
> 1. Entries can be proximity to a pivot, on team, I looked at the 620 chart for intraday low entry
> 2. Stops can be varies, what I mean by that is that I sometimes hold mental stops, so if it's 10sma I don't
> immediately sell but sell if it closes below it to avoid intraday churn, but if it slices though strongly then
> I may sell. So there's art in this"*

- **Entry:** near a pivot, timed by the 6/20 MACD (620) chart turning at the intraday low — on TEAM 08-07 he
  entered ~$144.39 around 12:05 ET, two hours after the 09:56 low (`docs/methodology/620_chart.md`). The lane's
  only 620 pattern anchors to the EP-day close alone.
- **Stop:** a mental stop under a level (e.g. the 10-day SMA) judged on the CLOSE, to avoid intraday churn —
  with an intraday exit only when price slices through strongly. "Art" = the judgement of what counts as strong.
- **Filed as H12 and H13** in `docs/analysis/327_hypotheses_2026-09-27.md` (#327); both are $0 replays on the
  277 real EPs. Adopting either in live trading is a stop/entry change — his call, CHANGE_PROCESS.


## 2026-09-28 — OKTA: a 10-day-average touch that recovered (operator, verbatim)

> *"okta stopped today is a example where waiting for close may be better, often i see 10sma touch then recover,
> which is what happened to it today"*

- **What the record shows:** live trade 382 (entered $167.88 on 08-27, high seen $212.50) had its trail stop at
  **$193.25 = the 10-day average** (closes through 09-25 average $193.27). OKTA opened **$192.02** on 09-28, below
  the stop, sold at **$191.50** at 09:30:01 (+$47), low **$190.50**, then **$197.64** by 09:58 ET.
- **Standing evidence:** the 09-06 exit ruling tested close-only trailing on 65 MAGNA53 trades and it lost 5.3R vs
  the intraday trail (`docs/setups/magna53_ep.md`, in-sample, no holdout). His hybrid (close-based unless it slices
  through hard — H13 in `docs/analysis/327_hypotheses_2026-09-27.md`) was never tested on the live exit stack.
- **Any change to the live trail is his call** (THE LINE, CHANGE_PROCESS).

### 2026-09-28 (later) — tests of a pivot are buy points when they hold; how a slice-through looks (operator, verbatim)

> *"we took a pretty poor stop as the stock is up nicely now. THis is something i've observed, stocks may come back to
> test pivot areas, in this case the 10SMA, and often these are buy points if test is successful vs sell points. In
> this case, it did a quick U&R of the 10day, vs slice through. I know this will add a lot more complexity to our system
> if we need to monitor all our stocks vs have stop in place, but i think this will shake us out of big winners
> sometimes which i want to prevent. Also, much of the volatility around these areas often happen in first hour of
> market open. For slice through, what i often see is mutliple intraday bars breaking lower (i.e. red bars) and bars
> that close at lower end of their range."*

- **Undercut & reclaim (U&R) of the line = hold (often a buy point); a slice-through = sell.**
- **Where the noise is:** the first hour after the open.
- **What a slice looks like intraday:** several bars in a row breaking lower (red), each closing in the lower part of its
  own range.
- **His trade-off, stated:** more monitoring complexity than a resting stop, accepted to stop being shaken out of big
  winners. Carried into #685's test design.

## 2026-10-05 — chart rulings, review sample #3 (real EP days only)

Source: his reply on https://claude.ai/artifact/2u1rfqKEagBDtceyT1bKqC (ten point-in-time charts, every date a
real EP day: open >= 9% above the prior close, volume >= 3x its 20-day average). Labels recorded in
`tests/fixtures/must_not_trade_charts.py` session 4. Before it he rejected the first build outright: *"I want
real potential EPs, not garbage to grade"* — three of its dates (CHRN 08-27, AGX 09-03, DG 08-27) were
pre-market spikes that opened only +4-6% and faded.

His words, verbatim, and what each adds to the structure read:
- **AEVA 08-06 — "bad, gapped right into resistance area and failed to take them out".** A big gap (+31.6%,
  6x volume) is not enough: where it opens relative to overhead supply decides it. Opening INTO a resistance
  zone without clearing it is the failure shape (the same supply-ladder idea as `structure_model.md`).
- **MAN 07-16 — "good, cleared a lot of highs are pviot areas to the left".** The mirror of AEVA: the gap
  CLEARS the prior highs / pivot areas on the left side.
- **HPE 06-02 — "ok, it's already quite extended on the run up to the gap with previous gap up as well, this
  is a good candidate for HTF or delayed entry".** Extension before the gap (a prior gap-up and a run) makes
  the day-1 ORB entry worse; he points it at the HTF / delayed-entry families instead of rejecting it.
- **CDNA 07-16 — "good; would've been stopped but good delay entry near EP day low".** A good EP where the
  day-1 entry would have been stopped out, and a DELAYED entry near the EP day's low would have worked — the
  delayed-entry lane's case in his own words (#327).
- **RXT 06-16 — "real date is May 7".** Wrong day; he points at 2026-05-07 (recorded POINTED_AT).
- **RUM 06-04 — "bad, it gapped down not up as well".** ⚠ Our daily bars show the open +13.2% above the
  prior close and the close below it (a gap up that reversed to a red close); his read differs and is
  recorded as he said it.
- BLZE 08-04 good · IBTA 08-04 bad · KRO 08-06 good · HURN 07-29 bad (his reply read "kro - bad"; confirmed: "last one was hurn bad").

## 2026-10-06 — Qullamaggie book interview excerpt: EP, parabolic short, momentum burst (operator-shared reference)

Shared as reference ("just got reference"), 8 page photos of an interview with Kristjan Kullamägi (Qullamaggie).
Paraphrased with short quotes; the photos were not kept. **Reference, not a ruling** — nothing here changes a live
rule until he says so (THE LINE).

**Episodic pivot (his main strategy, learned from Pradeep Bonde / Stockbee):**
- Three ingredients: "a major news item, a big gap up, and a huge increase in volume" — best "especially in a bull
  market environment". Example TEM Jan 2025 (AI healthcare app, ~10× average volume out of the gate, more than doubled).
- Finding them: a daily scan of stocks "up at least 10% on high volume"; 99% are not of interest (no news, or not
  the right type of stock). "I'm not going to buy a utility stock. It needs to be a stock that can make a big move."
  Best sectors: technology, biotech, small caps; sometimes sector-wide (quantum computing, Dec 2024).
- **Best EP is a neglected stock:** sideways for months or years, then ~10× its average daily volume. "You don't
  want a stock that has already been up a lot in a short amount of time." Example PTON Aug 2024 earnings.
- Prefers a breakout from a sideways consolidation, but it is not required.
- **Entry:** if opening volume is large enough, buy a move above the high of the FIRST 5-MINUTE bar; otherwise wait
  and buy above the first 1-HOUR bar. "I always buy into strength." **Stop: the low of the day.**
- Hold for weeks or months. LAES Dec 11 2024: a sector EP he sold the same day on a weak close although it never hit
  his stop; it then ran ~800% in under two weeks — "stick to my rules and not let my mental state influence trade
  execution."
- Themes: several stocks in one sector on the scan; one or two leaders, the rest laggards that traders chase later.

**Parabolic short:**
- Short stocks up very sharply several days in a row (several hundred percent) that start showing weakness —
  typically small-cap pump-and-dumps. Pump tell: up several hundred percent with no filings or news and not part of a
  sector theme. Once a sector is hot, small caps move on any news (vaccines 2020, quantum Dec 2024).
- **A+ setup:** up three or four days in a row, total gain at least 300%. Never short day 1 ("I've seen stocks go
  up 1,000% in one day"), rarely day 2, usually day 3 or 4 — shorting early means several mid-size losses.
- **Trigger:** break of the opening-range low, or, if it keeps rising, a break below a 5-minute candle. **Stop: the
  high of the day** (most of the time). LAES: shorted day 3, stopped out; re-shorted day 5 near $10, covered ~$5.

**Momentum burst (breakout swing, from Bonde):**
- Most of an explosive move is over in three to five days — the holding period.
- A leading stock (top 1-2% by gain over the past 1, 3 and 6 months) in an uptrend that consolidates sideways for
  one to three weeks, preferably on reduced volume; buy the breakout above the opening range or the first 5-, 30- or
  60-minute bar high (longer = worse price, fewer false breakouts); hold three to five days.

**Where this differs from our live MAGNA53 EP today (facts, for his reading — no change proposed):**
- Entry bar: we buy above the first **1-minute** bar's high (09:31–09:44); the book uses the first 5-minute bar, or
  the first 1-hour bar when volume needs confirming.
- Stop: we use entry − 2R (R = entry − ORB low); the book uses the low of the day.
- Stock type: we have no utility / "can't make a big move" exclusion — the 10-06 live entry CEG is a $94.8B utility.
- Neglect: the old score's neglect / prior-momentum terms were deleted 2026-08-22 (they fired on real EPs and junk at
  the same rate); the book names neglect as the best EP trait.
- Parabolic short: our `days_up_streak >= 3` gate matches "day 3 or 4"; see `docs/setups/parabolic_short.md` for the
  gain and trigger rules.

**TEST MAP (his word 2026-10-06: *"No changes but worth comparing and see where we can test and tweak as we refine
our system"*)** — each book rule, where it is measured, and on what. All $0 on stored data; none changes a live rule.

| Book rule | Ours today | Where it gets tested | Data |
|---|---|---|---|
| EP entry above the first 5-min bar (1-hour bar if volume unconfirmed) | first 1-min bar high | #482 bracket lab — its 5-min ORB shadow lane already has 55+ closed trades; add a first-1-hour-bar arm | `mi_orb_shadow_trades`, stored minute bars |
| EP stop at the low of the day | entry − 2R | #482 — a low-of-day stop arm beside its intraday-low / ATR variants, scored in capped dollars too (the 10-06 H10 lesson) | stored minute bars |
| No utilities; only stocks that can make a big move | no sector filter | #686 follow-up, AFTER its frozen 10-17 read (the registration cannot take new features) — sector and size as candidate features on the out-of-sample block | `mi_ep_alerts` + sectors |
| Neglect: sideways for months, then ~10× volume | neglect / prior-momentum terms deleted 08-22 (fired on real EPs and junk alike) | same #686 follow-up — a base-length + EP-day volume-multiple feature, measured on the TAIL, against his labelled EPs | `mi_daily_closes` |
| Parabolic short: day 3-4, ≥ 300% total, short the OR-low break, stop at the high of day | detection only (shadow): streak ≥ 3 + cap-tier prior move; no trigger or stop defined | `docs/setups/parabolic_short.md` — replay the book's A+ definition against our climax rows | `mi_parabolic_candidates` + minute bars |
| Momentum burst: top 1-2% by 1/3/6-month gain, 1-3 week base on lower volume, buy the OR / 5-30-60-min high, hold 3-5 days | flag board (TIGHTENING/COILED) + #397 breakout-entry shadow | #397 — the leading-stock filter and the 3-5 day hold as arms on the breakout shadow | `mi_flag_candidates`, shadow rows |

## 2026-10-07 — PENG, another trader's EP call that he confirmed (operator-shared)

He shared @TedHZhang's post (12:33 PM, 07 Oct 26): *"$PENG is an EP - double beat and raise on earnings. This is
a rare setup that I've only seen once - HVE followed by HVE and higher highs."* — with a daily chart: two
consecutive highest-volume-ever days (16M +381%, then 19M +500% vs ~3M average), the second gapping to a higher
high out of a ~36-day base, RS 94 (1M/3M/6M 98/94/97). His words: *"We caught peng this morning, good to see
confirmation from other traders."* → added to the labelled EP list (`operator_labelled_eps.md`).
- **Setup note to keep:** "HVE followed by HVE and higher highs" — back-to-back highest-volume-ever sessions,
  the second making a higher high — is the trader's name for it; reference only, not a rule.
- **What we did:** HIGH 73.8, catalyst `strong` (the grader saw 'multiple company records' + a raised FY2027
  outlook but not the figures), live #414 — trigger $69.20 (ORB high), filled $72.21, stop $62.20.
- **His follow-up, same day:** *"The other things to note is the horizontal pivot lines that trader drew on the
  chart. You can see a clear pivot there, so this is useful for charting."* What the chart draws (read off the
  image he shared, so approximate prices): a horizontal line at each prior swing HIGH, carried right to today,
  labelled with **days since that high · depth of the pullback from it** —
  - **"36 days · 31%"** at ~$66: the late-August swing high; the base under it fell ~31% (to ~$45) over 36 days.
    The 10-07 EP gapped and held ABOVE this pivot (close $72.78) — the level it cleared.
  - **"63 days · 51%"** at ~$90: the July spike high (that day was itself an EP, marked E); ~51% down to the base
    low over 63 days. Still ~24% overhead — the next supply shelf.
  - Two short minor pivots (~$53.5, ~$57) inside the base, cleared on the way up in late September.
  Why it matters for us: these are the supply-ladder levels of `structure_model.md` drawn explicitly — "which
  pivot did the gap clear, and how far is the next one" — with the base's length and depth attached.

## 2026-10-11 — Pradeep Bonde (stockbee): "Growth stocks EP" — sudden acceleration on a neglected stock (operator-shared reference)

Shared with "we know this already, but here's bonde teaching about neglected stocks in EP concept". Source: @PradeepBonde
post, 2026-10-11 9:16 AM, "Sudden acceleration in revenue, profit, and margins on neglected stock — from my presentation to
members just a few minutes ago." Image kept: `docs/methodology/images/bonde_growth_stocks_ep_neglected_2026-10-11.png`.
**Reference, not a ruling** — nothing here changes a live rule until he says so (THE LINE).

The slide, transcribed ("Growth stocks EP"):
- **growing** — "significantly higher than average stock in mkt", on **profits, margins, sales, roe, roi**.
- In red: **"sudden acceleration in sales or profitability or margins"** — the trigger.
- In red: **"neglected"** — the stock it happens to.

How it maps to what we already run (no change proposed):
- **Acceleration** is already a scored input: the catalyst rubric scores trailing acceleration (revenue YoY + decel/accel);
  the forward/projected leg is #333 (catalyst durability). Our standing read is that the edge is SURPRISE versus
  expectation, not magnitude (memory `ep-edge-is-surprise-not-magnitude`) — the slide's "sudden" is the same idea.
- **Neglected** is NOT a scored axis today, on evidence: the old component (≥30% below the 52-week high) was deleted
  2026-08-22 on his sign-off because it measured BEATEN-DOWN, not quiet; a quiet-base measure calibrated to his MRNA
  annotations scored AUC 0.42 (real EPs had SHORTER quiet bases than their rivals) — `ep_detector.py` ~2094. Qullamaggie's
  version (2026-10-06 entry above: "sideways for months or years, then ~10× volume") is the same thesis. Neglect as
  ATTENTION (thin analyst coverage, low prior volume) rather than price shape is untested here — `analyst_estimates_recorder`
  carries a read-side thin-coverage rule; it is a candidate if he wants it measured.
- **His reply, same day (verbatim):** *"No action yet, on your idea about low analyst coverage I don't think it's good, if
  might just include thin stocks that's are tiny caps. A corollary to that may be the lack of or deceleration of analyst
  upgrades, just a thought."* → Thin COVERAGE is ruled out as the neglect measure (it would mostly select tiny caps).
  His candidate instead: **no analyst upgrades, or a slowing pace of upgrades, before the EP** — neglect as fading
  attention, independent of size. Not scheduled ("no action yet"); if it is ever measured, the natural source is the
  rating-change headlines already flowing through the Benzinga/Alpaca news feed (upgrade / downgrade / initiation counts in
  the weeks before the gap), read against real EPs vs their board rivals, size held equal.

## 2026-10-11 (later) — Pradeep Bonde: "What is neglect..." — five kinds (operator-shared reference)

Shared with "Bonde just shared his definition of neglect". Image kept:
`docs/methodology/images/bonde_what_is_neglect_2026-10-11.jpg`. **Reference, not a ruling** (THE LINE).

Transcribed (his words):
- **Financial neglect:** "A long period of time where stock had no growth. Longer the better. And then it suddenly starts growing."
- **Price neglect:** "A long period of time where stock had no meaningful price rally. Years of neglect better."
- **Volume/liquidity neglect:** "Long period of time where stock had below average daily volume."
- **News/attention neglect:** "no analyst coverage. No major news for months /years."
- **Ownership:** "funds ownership low because no reason to own stocks. Below 20 to 30 funds owning it."
- Chart examples: **GRWG** (2020-08-12 EP; annotated "neglect · not rallying in to earnings · going sideways for few months", "100/123"),
  **PDCO** (2020-12-14 EP; "63c exp 38c" — a beat against expectation), **UPWK** (2020-12-14, cut off in the image).

How each maps to what we have (no change proposed):
- **Financial** — the catalyst rubric scores recent acceleration (revenue YoY + decel/accel); "a LONG flat period before it" is not
  measured. Lives with #333.
- **Price** — note it is "no meaningful RALLY for a long time", which is NOT the same as a tight quiet base (the measure we built and
  that read backwards, AUC 0.42) and NOT "far below the 52-week high" (the component deleted 2026-08-22). A "largest rally in the past
  1–2 years stayed small" measure has never been tested.
- **Volume/liquidity** — not measured as a long-run state (our volume checks are about the gap day and the ADV floor).
- **News/attention** — Bonde names "no analyst coverage". **His 10-11 ruling stands: thin coverage alone mostly selects tiny caps**;
  his own corollary (no / slowing analyst upgrades) is on #333. A size-matched comparison would be the way to test Bonde's version
  without the tiny-cap confound. "No major news for months" is measurable from our stored headline feeds.
- **Ownership** — fund counts (13F) are not in our data.

## 2026-10-15 — MRNA: the post-EP consolidation and his two entries (operator, verbatim)

> *"I just looked at the MRNA chart, aside from EP, it's the perfect post-EP consolidation, pulled back and got really
> tight on 9/15-16 and broke out 9/17. Personally, I'd likely buy early on tight inside day on 9/16 anticipating the
> breakout, and a ORB entry on 9/17 can also work."*

**🖼 Image (committed, not cited):** `docs/methodology/images/mrna_2026-10-15_post_ep_consolidation_daily.png` — his TradingView
daily as of 10-15 (last $239.97, ADR 8.41%): the 08-19 EP gap on ~199M shares, his drawn flag rails from the ~$175 spike
high down to the mid-September tight spot, the 9/17 break and the trend to ~$240.

**Family vs setups (the CLAUDE.md definition):** post-EP consolidation is the FAMILY (Family A, #354). He names TWO setups
inside it, each with its own buy point — they need their own names and must never be pooled:
1. **Anticipation buy on the tight inside day — 9/16.** Buy before the break, in the tightest bar of the base.
2. **ORB breakout entry — 9/17.** Buy the opening-range break on the breakout day.
He gave no stop for either; the stop stays undetermined (see [[entries-and-exits-are-undetermined-for-new-setups]]).

**The bars (`mi_daily_closes`, `scripts/probes/_mrna_1015/q2.*`):**

| day | open | high | low | close | range % of close | note |
|---|---|---|---|---|---|---|
| 09-11 | 137.91 | 149.73 | 135.01 | 143.97 | 10.2 | the wide day whose high caps the base |
| 09-14 | 144.93 | 147.34 | 139.02 | 146.69 | 5.7 | |
| 09-15 | 146.00 | 148.70 | 141.16 | 143.77 | 5.2 | tight |
| **09-16** | 145.26 | 148.93 | 142.30 | 145.62 | **4.6** | **his inside day** — the tightest bar (about half its ADR); low inside 9/15's, high 0.15% over it, so a strict inside-day rule would miss it by 23 cents |
| **09-17** | **152.50** | 161.96 | 149.50 | 158.07 | 7.9 | **his ORB day** — opened above the 9/11 high on 2.2x the prior day's volume |

**WHAT OUR SYSTEM SAID — checked before writing (`scripts/probes/_mrna_1015/q1.*`):**

| day | flag stage board | delayed-entry lane |
|---|---|---|
| 09-10 → 09-15 | unqualified — `flag_low_128.61_below_75%_of_pole_176.66` (the depth gate, recorded 09-17) | no trigger |
| **09-16** (his anticipation day) | **INVALIDATED** — `close_145.62_below_sma20_145.67` (the 5-cent kill, recorded 09-17) | no trigger |
| **09-17** (his ORB day) | unqualified — **`ma_stack_not_stage2_144.5/144.9/96.6`** | no trigger |
| 09-18 | unqualified — `ma_stack_not_stage2_145.0/145.9/98.2` | no trigger |

**🔑 A THIRD gate, not in the 09-17 note:** on the breakout day itself the board read `ma_stack_not_stage2` — the short
averages were still tangled (144.5 vs 144.9) after the pullback, so the stack test failed exactly when the base resolved.
So MRNA was blocked by three different gates on three different days (depth, then a 5-cent SMA20 kill, then the MA-stack
order). The delayed-entry lane never fired at all — 9/17 is ~20 sessions after the EP.

**Pole vs EP — one clarification so the two MRNA notes do not read as two definitions:** the 09-17 note's "pole" (170% in his source's chart, our `runup_pct` 2.4) runs from the ~$52-65 base to the spike HIGH ($176.66); the 08-19 EP note measures the gap day from its ~$120 open. Both share the same pole HIGH, and our depth gate is `flag_low / pole_high` (128.61 / 176.66 = 72.8% vs the 75% bar) — so the depth math does not depend on where the pole starts; only the runup figure does.

**His emphasis, the same day (verbatim):**
> *"i want to emphasize that this is a really good setup per my estimation, also give it was a strong EP, pulled back
> orderly and tightened, lower vol then broke out again"*

**So this is a TOP-RATED labelled example — his own five-part definition of a good post-EP consolidation, each checked
against the bars:**

| his trait | MRNA, from `mi_daily_closes` / his chart |
|---|---|
| 1. a **strong EP** before it | 08-19 gap on ~199M shares (his "textbook EP", 08-19 note) |
| 2. an **orderly pullback** | ~$175 spike high down to ~$128-135 over 08-20 → 09-10, inside his drawn rails — no collapse through the base |
| 3. it **tightened** | daily range fell to 5.2% (09-15) and 4.6% (09-16) of close, about half its ~8% ADR |
| 4. **lower volume** | 8.2M (09-15) and 8.8M (09-16) vs 15.3M on 09-11 and ~199M on the EP day |
| 5. **broke out again** | 09-17 opened $152.50 above the 09-11 high ($149.73) on 19.2M (2.2x the prior day), closed $158.07; ~$240 by 10-15 |

⚠ **Recorded as a labelled example, not a proposal.** All three are detection/admission criteria (THE LINE), and HTF /
consolidation work stays behind EP profitability ([[priority-ep-profitability-before-new-setups]],
[[htf-is-detection-not-trading]]). Use: the #697 corpus (MRNA is `htf` there and, since 2026-10-15, carries the two entry days, the
third gate and his TOP rating — `tests/fixtures/htf_labelled.py`); the anticipation-vs-breakout split is a #354 / Family A question for when that work opens.

## 2026-10-15 — share count vs relative volume on EP gap days (James Muninn, reposted by stockbee), operator-shared "food for thought"

**🖼 Image:** `docs/methodology/operator_shared_charts/2026-10-15_muninn_9m_vs_rvol/01_tweet.png`.

> **Tweet, verbatim (@Muninn, reposted by @PradeepBonde):** *"This screening rule by @PradeepBonde is extraordinary. And for the
> life of me I don't know why it works. But does it even matter? He screens Episodic Pivots (catalyst trade) with a simple 9M+
> shares on gap day. When tested on all qualified gappers since 1992, this filter outperforms the relative volume screen. The names
> which traded 9M+ shares outperform by +0.32 R on avg.. The most surprising finding though is probably that extreme relative
> volume have no reliable edge compared to lower relative volume.."* (quoting Bonde, 19 Nov 2023: *"A new version of EP I trade
> called EP 9 million."*)

**His chart ("Share count vs relative volume — extra R per trade vs the other gaps"; dot = average, line = 95% range), read off the image:**

| comparison | period | average | 95% range | reading |
|---|---|---|---|---|
| 9M+ shares vs under 9M | 1992-2024 | ≈ +0.32R | ≈ +0.08 to +0.57R | clears zero |
| 9M+ shares vs under 9M | 2016-2024 | ≈ +0.32R | ≈ +0.03 to +0.62R | clears zero |
| highest vs lowest relative volume | 1992-2024 | ≈ +0.27R | ≈ -0.42 to +0.97R | no edge |
| highest vs lowest relative volume | 2016-2024 | ≈ -0.15R | ≈ -0.97 to +0.68R | no edge |

**How it touches our system (stated, not proposed):**
- **Timing:** "9M+ shares on gap day" is a FULL-DAY count. Our MAGNA53 entry is the 09:31-09:45 opening range, where we have
  pre-market and projected volume, not the day's share count. As a screen it is knowable for a day-2 / delayed entry, not for our ORB.
- **Our admission leans on RELATIVE volume** (pre-market and projected RVOL at scan time). His chart says extreme RVOL carries no
  reliable edge over low RVOL, while an absolute share count does. Consistent with [[ep-edge-is-surprise-not-magnitude]] only in part:
  a share count is a liquidity/participation measure, not a surprise measure.
- **The frozen #686 read (Sat 10-17)** carries 20-day dollar volume and pre-market RVOL but NOT gap-day share count, and its
  registration cannot be edited now. A $0 follow-up AFTER that read: gap-day share count (>= 9M, and as a continuous feature) vs
  RVOL on our scored candidates, tail first ([[measure-the-tail-not-the-median]]) — recorded on #686 beside the book-trait tests.
- Any change to the score or admission is CHANGE_PROCESS and his call (THE LINE).

## 2026-10-17 — Qullamaggie's BREAKOUT setup ("My 3 timeless setups that have made me tens of millions"), operator-shared reference

Source: https://qullamaggie.com/my-3-timeless-setups-that-have-made-me-tens-of-millions/ (fetched 2026-10-17). He asked to TEST a
special case of the consolidation family with these tighter criteria, plus additions of his own: group RS, RS, entry/exit timing,
bull vs bear phase. Quotes are the article's words (via a page summary).

- **Prior move:** *"A big move higher sometime in the past 1-3 months. This move can be anywhere from 30-100%+ and usually lasts
  a few days to a few weeks."*
- **Consolidation:** *"usually 2 weeks to 2 months. During the consolidation the stock price 'surfs' the rising 10- and 20-day
  and sometimes the 50-day moving average"*, with *"higher lows and tightening range."* Shapes: flat channels, symmetrical and
  descending triangles.
- **Which stocks:** *"the 1 or 2% of stocks that are up the most over these 3 timeframes: 1-month, 3-month, 6-month."*
- **Market:** bullish; when it turns bearish, *"fewer or no trades."*
- **Entry:** *"Enter on the opening range highs. The opening range highs can be the highs of the first 1-minute candle, the
  5-minute candle or the 60-minute candle."* Or simply buy as the daily chart starts to break out.
- **Stop:** *"Stop is always lows of the day and stop should not be wider than the ATR or ADR of the stock."*
- **Size:** positions 10-20% of the account; risk 0.25-1% a trade, rarely more than 1%; at most 30% of the account in one stock
  overnight.
- **Exits:** *"sell 1/3 to 1/2 of the position after 3-5 days, and then move the stop to break even."* The rest *"trailed with the
  10- or the 20-day moving average... You wait for the first CLOSE below the 10-day."*
- **What he expects:** *"In a bullish market it is very common to get moves that are 10-20x+ your initial risk if you are good at
  setup selection."*
- **Under our definitions (CLAUDE.md, SETUP vs FAMILY):** this is a SETUP inside the consolidation family. It has a defined buy
  point (the opening-range high on the breakout day) and a defined stop (the low of that day, no wider than one ADR).
- **Market rule, ATTRIBUTED, not in the article (operator-forwarded Gemini review, 2026-10-17):** Gemini review forwarded by the operator 10-17 attributes to Qullamaggie a NASDAQ 10-day > 20-day, both rising, market rule; not in the 10-17 article; source not given.
  A WebFetch of the article on 10-17 found no index moving-average rule; its only market words are the "bullish" / "fewer or no
  trades" lines above. #702 tests it as the primary bull-phase cell, using QQQ as a stand-in for the Composite, and keeps
  "SPY and QQQ above their 50-day" as the alternative cell. It is an addition to his setup, never "as written".

## 2026-10-17 — his note on the breakout ENTRY: a down-sloping trendline, not only the base high (operator, verbatim)

> *"If you actually look at all the traits, the entry he uses, break out base high, depends on how he draws it on the
> chart. A lot of time he draws a flag with a down sloping trend line and a breakout of that trend line. So I don't
> know how that translates to breakout for us, but that may dictate a lower entry than what we call a breakout. And
> with that, success and failure may differ a lot."*

- **Context:** said after the #702 discovery read (2026-10-17), whose breakout levels were all HORIZONTAL (the high of
  the last 5 or 10 sessions, or the whole base's high).
- **What #702 does with it:** adds a fourth breakout level, the down-sloping TRENDLINE across the base's highs. It is
  anchored at the pole top and drawn so that no later high sits above it, using bars up to the watch night only.
  The breakout day buys when price crosses the line's value that day. It is tested beside the horizontal levels,
  never instead of them.
- **Why it can matter:** a descending line sits BELOW the base high, so it triggers earlier and lower, and the
  stop, the R unit and the failure rate can all differ.

## 2026-10-18 — his note: read the CHARACTER of the base first, then draw the line, then set entry and exit (operator, verbatim)

> *"we should test all combinations; This is where it's difficult, when I watch qullamaggies streams the consolidation
> varies, if it's tight and flat then base high makes sense, when it's starts wide and then tightens the flag like makes
> more sense, sometimes not at the base high, etc. it's more art then science"*
>
> *"Yes, we need to look at the character of the base, e.g. if there's a larger upper wick and then settles lower and
> bases, sometimes we ignore part of the wick. This is best judged on a chart and where his streams draws out many of
> these. So maybe the initial step is to determine the character of the consolidation then from that where to draw the
> lines and where to put the setup entry and exit"*

- **What it changes in #702:** the breakout level is no longer one fixed rule (base high OR trendline). The order becomes:
  (1) classify the base's character — tight and flat, wide-then-tightening flag, wick-topped then settling lower, and
  so on; (2) draw the line by that character, e.g. ignore an outlier upper wick and use the settled highs; (3) then
  place the entry and the exit.
- **Where the labels come from:** Qullamaggie's streams, where he draws many of these by hand. Per
  [[charts-support-never-decide]], a chart read leans; it never decides alone.
- **Status:** the one-time 2025–26 read waits until this character → line step is built and frozen.

## 2026-10-18 — two Qullamaggie sources he shared, plus his go-ahead to mine the streams (free steps only)

His words: *"Do the first two for free and hold on 3rd paid."* That means pull and parse the stream transcripts and match
them to our bars. The frame-reading vision step is HELD until he okays its price. He shared two sources:
- **Kyna Kosling, "Qullamaggie Stream Notes"** — https://tradingresourcehub.substack.com/p/qullamaggie-stream-notes
  (his share link: https://share.google/6V10YzfiXjDYdY7Bl).
  - An index of notes from his streams, June 2020 to December 2023, plus interview notes.
  - Each linked post carries charts and position discussion; the index itself is free.
  - Use: a second source of labelled examples (ticker + date + what he said about the base), next to the stream
    transcripts.
- **Deepvue, "Find Stocks Like Qullamaggie"** — https://deepvue.com/screener/qullamaggie-screens/ (his share link:
  https://share.google/yFCEAfWV78OTjashw). Its screens, as the page states them (fetched 10-18):
  - Continuation base: "Stocks up at least 25% in the past month"; "Weekly volume at least 50% lower than the
    previous week"; "Trading within ~2% above or below the 10-day SMA".
  - Episodic pivot: "One-day price move over 7.5%"; "Dollar volume over $100 million".
  - Top monthly gainers: high AS (absolute strength) rating and a strong ADR.
  - Pattern names: high tight flags, continuation patterns (triangles, volatility contractions) and EPs.
  - Use in #702: the volume dry-up week over week and the within-2%-of-SMA10 test are candidate features for the P4b
    base-character step. They are recorded, never gates, until a read supports them.
- **His channel**, https://www.youtube.com/@qullamaggie: 588 videos, about 800 hours; auto-captions are downloadable.

## 2026-10-18 — his rule for where the line goes: the consolidation's CENTER OF MASS; short outliers are ignored (operator, verbatim)

Said while reviewing four of Qullamaggie's own drawn lines from his streams (RIOT 2021-04-13, SPOT 2020-08-17,
NIO 2020-12-24, AMD 2021-12-16), each drawn through a big upper wick:

> *"Yes, not just wick, in these cases he ignore some outlier parts of a daily bar, the way I'll put it is that he finds
> where the center of mass is in the consolidation and ignore the outliers if it's just a short period, meaning a 1-3 bars
> spike then drop back to the basing area. The only thing slightly off is the line for SPOT, his line is slight higher,
> you might've mistaken for another red line which is just a pointer and not a trendline."*

- **What it defines for #702 P4b:** the breakout line sits on the consolidation's center of mass, not on its single
  highest print. A spike of 1–3 bars that pokes out and then drops back into the basing area is an outlier and is
  ignored, whether it is a wick or a whole bar.
- **What it leaves open (the rule step must state it, not assume it):** how "center of mass" is measured on daily bars,
  and what counts as "back to the basing area".
- **Correction recorded:** the SPOT 2020-08-17 line read from the frame sits slightly LOW; his real line is a little
  higher. The reader took a pointer line (from a news note) for the trendline.
- **Status:** an input to the P4b character → line rule (step 6). Per [[charts-support-never-decide]], the labelled stream
  lines test the rule; they do not replace it.

## 2026-10-18 — his caution on market regime: breakouts do worse in bear and choppy markets (operator, verbatim)

> *"that is an important point, breakouts likely wont do as well in bear markets, or choppy markets"*

Said when told the P4b labelled lines are mostly from 2020–21, one bull market.
- **What #702 already carries:** the primary cell C1 buys only when QQQ's 10-day average is above its 20-day and both are
  rising; C3 is the same cell with no market filter, so the pair shows what the filter is worth. Every read reports
  results by year (2022 was a bear market) and by Apollo's daily regime label (Bull / Choppy / Correcting / Crisis),
  which exists only from 2025-03-03 — the holdout's non-Bull groups will be small.
- **Status:** reported beside the verdict, never deciding; any regime gate on paper or live is his call (THE LINE).

## 2026-10-18 — his correction on Qullamaggie's SELL rule: the first third goes at +2R, not after 3–5 days (operator, verbatim)

> *"His sell is to sell 1/3 at 2R then move to break even stop then trail rest at break of 10 or 20d, I recall he
> mentioned 10d for faster stocks and 20d for slower stocks, also depend how far the are from 10/20."*

Asked "aside from stops, what's the profit take and sell criteria", with his note that Qullamaggie stresses tightness
before the breakout (his "A+ setups") — *"higher qualifier there maybe an option"*.
- **What it changes in #702:** the 15 exit arms tested so far sell the first 1/3 (or 1/2) at the CLOSE of day 3 or 5
  (the 10-17 article's "after 3–5 days"). His rule is a PRICE target: sell 1/3 at +2R, then move the stop to breakeven,
  then trail the rest to the first break of the 10-day average (faster stocks) or the 20-day (slower stocks).
- **Open (the build must state how it reads them):** what makes a stock "faster" (e.g. its ADR), and how "how far they are
  from the 10/20" picks the average.
- **Measured the same evening (2022–24, registered trendline level, before this exit exists):** the tightest fifth of
  bases did WORST, not best — by both the range ratio (last 5 days vs the base's first 5) and the last 5 days' range in
  ADR units — and it is not explained by stop size (median stop 0.43–0.52 ADR, same-day stop-outs 35–38% in every fifth).
  So our tightness measures may not be what he means by "tight"; to be re-checked under his exit.
- **His follow-up, same evening (verbatim):** *"The day thing is also correct, it may be a combo and depends"* — the
  after-3–5-days partial is ALSO his rule; the partial may be a combination of the two (+2R or a number of days) and
  depends on the stock. So the tests carry all three: +2R, day 3/5, and whichever comes first.

## 2026-10-18 — his point on stalled breakouts: cut them for TURNOVER, even when they end near breakeven (operator, verbatim)

> *"The timing thing is interesting because a thinking is that if breakouts have no follow through in next few days then
> it may be better to get out as momentum didn't continue regardless if it isn't stopped, may be good to see what happens
> to these stocks that stalled after a breakout"*
>
> *"Cut stallers is important because funds are limited, turnover for swing trades is important, holding breakeven for a
> long time has opportunity cost"*

- **Measured the same evening (2022–24, trendline level, ORH5 entry, the registered exit):** by day 3, 1 in 10 trades
  still open had never reached +1R; they ended near breakeven (−0.10R), and none of the 322 eventual ≥5R winners was among
  them — so cutting them costs no tail. Per trade, R barely moves; the gain he names is CAPITAL-DAYS freed (scored next).
- **What it adds to #702:** a time stop ("no +1R within N days → out") is scored on R per position-day held, not only R per
  trade, and on a limited-slot account, because slots are the constraint.
- **Confirmed 2026-10-19 (his "yes")** to the definition built into the holdout read's primary: a trade that has not
  reached +1R by the close of session 3 after the breakout day (and was not stopped) is sold at that close.

## 2026-10-19 — the breakout article's full text, re-shared by him, and his pointer: "there are additional setups on these stocks" (verbatim)

His words: *"If you look closely, there are additional setups on these stocks."* Then the article's breakout section
(qullamaggie.com, "My 3 timeless setups"), pasted verbatim — the parts not already quoted in the 2026-10-17 entry:
> *"If you study thousands of the biggest winning stocks over the past 100 years they tend to move in stair steps. Meaning
> they will make a 20-50%+ move, pull back and go sideways for a while, then make another move. This is how most leading
> stocks act."*
> *"Identify the setups. You need to have a watchlist ready before the market open. You should also probably have alerts set,
> and know how many shares you want to buy."*
> *"(on the 60-minute timeframe the first candle is always only 30 minutes, 9.30-10 AM). You can use whatever timeframe or a
> combination of them. You don't even have to use any intraday chart, just look at the daily chart and enter when the stock
> is starting to break out."*
> *"This method can also be traded by anticipating the breakout but I don't find it as effective and more skill and
> experience is needed."*
> *"The rest of the position should be trailed with the 10- or the 20-day moving average. Depends on how fast the stock is.
> If a beginner stick to the 10-day."*
> *"There are variations of this setup but the premise stays the same. ... this setups also works on the weekly chart and the
> intraday (1- and 5-minute) charts. On the intraday timeframe this setup is called Holy Grail by some on the daily it can be
> called a hight tight flags sometimes. It's pretty much flat channels, symmertrical and descending triangles."*
- **What his pointer adds to #702:** the STAIR STEP — one leading stock gives several breakout setups in a row (move →
  sideways → move). Each step's base is its own C0 base in our runner (a new pole); what the tests never split is the STEP
  NUMBER (first base of a run vs the second or third).

## 2026-10-19 — his point on how Qullamaggie's breakouts make money: a ~25% win rate, outliers and small losses (operator, verbatim)

> "Qullamaggie claims his winrate is around 25%, his strategy depends on outliers and taking small losses"

Said after the 2017–21 read (#702), whose strict group read +0.28R per trade on 180 with one +54R trade carrying it.
**What it means for the tests:** an outlier-driven setup is judged on the outliers it catches and the size of its losses,
not on its win rate or its result without its best trades. A "mean without the top five" bar structurally fails exactly
this profile. On his terms (2017–21, every breakout): losses are small (about −1.0R on average), winners 34% — but winners
average only about +2R and a ≥ 10R trade comes about once per 80 trades, so the outliers do not pay for the losers.
Analysis: `docs/analysis/cb_2017_21_read_prereg_2026-10-19.md` §Addendum (his outlier point).

## 2026-10-19 — his question on the breakout ENTRY: scout it on intraday bars as price moves into the breakout area (operator, verbatim)

> "on breakouts, should we move to intraday bars to scout for an entry once it's moving into breakout area? I know he uses
> hourly bars, but 5min to 1hr intraday can show if the breakout is happening"

Asked after the TSLA 2020 example (our rule bought the 2020-05-18 intraday poke above the May triangle line, closed below,
stopped the same day; his breakout was the 2020-06-01 range expansion). Recorded late (captured 2026-10-19 with the
hourly-close entry test it motivates; #702).

## 2026-10-19 — his rulings on the partial and the stop after it (operator, verbatim)

Asked whether his "sell a third after 3–5 days" applies only when the trade is in profit (TSLA 2020-06-01: our day-3 rule
sold a third BELOW cost on 06-04, moved the stop to cost, and the 06-05 dip took the rest out before the run to $68):

> "Yes, and maybe we need to vary the stop adjustment, can we try adjusting stop so the whole trade is breakeven after
> taking the partial?"

**What it means:** (1) the day-based third is sold only when the trade is in profit; (2) after the partial, the stop goes
where the WHOLE trade nets zero, not to the entry price: with a third sold at price p and two thirds left, stop =
fill − (p − fill) / 2, never below the original stop. A third at +2R puts that stop at fill − 1R — the original stop. His
follow-ups: *"Wait , with 2r profit the original stop will be breakeven for the trade"* and *"This makes more sense given
original stop is where the pattern would fail"* — the stop belongs where the PATTERN fails, not at the entry price. Test:
`docs/analysis/cb_exit_partial_prereg_2026-10-19.md` (#702).

## 2026-10-20 — HTFL named as a high-tight-flag breakout (operator, verbatim)

> "Did we catch htfl htf breakout today?"

HTFL 2026-10-20: +9.0% to $55.59 (high $56.30) on 2.9M shares (~2x), clearing the 10-06 high $54.32 after a ~21-session base
under a ~117% run-up. **Our two readings that night:** the HTF stage board (#697) held HTFL at WATCH (`close_vs_pivot_+6.5%`)
— no TRIGGERED, because the #146 licence needs a TIGHTENING-or-better label in the last 5 days and HTFL's last TIGHTENING was
10-06: the base was reset to INVALIDATED five times in October (10-01, 10-07, 10-08, 10-14, 10-16) by closes just under the
20-day average (by $0.03–$1.34). The consolidation-breakout shadow (#702) caught it: trendline level, ORH5 filled $52.30, stop
$51.00, close $55.59. Recorded as a labelled HTF example for the detector (a tuning datum, not a trade question).

**2026-10-22 correction (the #697 read, `docs/analysis/htf_sma20_kill_htfl_2026-10-22.md`):** three of the five October kills
were shallow (−0.04% to −0.46% under the 20-day average) and two deep (−2.70%, −3.75%). Re-scored with the rule loosened
by 0.5–2%, HTFL's 10-20 breakout STILL reads WATCH: the 5 days before it hold no TIGHTENING label at any tolerance, because
the base stopped reading tight after 10-01. The 20-day rule was not the deciding gate.

## 2026-10-20 — a short-seller's method (book excerpt, a trader interview he shared; NOTES + short quotes, not the full text) — part 1

Shared by the operator to *"glean rules that can help with our short setup"* (complement to the parabolic short, #314 /
`docs/setups/parabolic_short.md`). Interviewee: Russo (small-cap short seller who later traded longs and large caps).

**The rules as he states them (part 1):**
- **Timing a parabolic short:** wait for *"total capitulation — volume and price accelerating to stratospheric levels"*;
  short *"in the rough vicinity of what will be the top and then use risk management"*. He was stopped out the day BEFORE
  the top on MGT (2016) at an acceptable loss and re-shorted the next day — sizing + stops keep you in the game for the
  day that matters.
- **Entry day mechanics (MGT):** on the top day the stock was *"losing momentum"*; it came within 20 cents of his stop,
  then turned down slowly, then faster → he **added** and **moved the stop to the day's high**; when the stock went
  **negative on the day** he shorted more; then it collapsed. Adds and stop-tightening happen together.
- **Selection is the edge** (his partner beat him by avoiding marginal trades).
- **Catalyst first:** find the exact minute the rally began and the news issued then. A short candidate rallies on news
  that *"superficially sounds bullish but, upon closer examination, is insignificant"* (fluff; e.g. "100% revenue
  growth" while still losing the same money). **Avoid** real news: a swing from net losses to profits, genuinely positive
  trial results — *"you don't want to be short, no matter how much the stock is up"*. **No identifiable news = worry,
  don't short** (*"What am I missing?"*).
- **Bearish fundamentals:** low cash / high burn / excessive debt (a raise is likely and dilutive); **hidden share
  overhang** in the capital structure (convertible debt, warrants — e.g. 10M outstanding but 40M convertible); an
  **identifiable seller**: convertible holders at $3 when the stock runs from $2 to $5 on huge volume will convert and
  sell; a known hedge fund behind the deal is itself a bearish confirmation.
- **Frequency / process:** ~2–3 qualifying shorts a week; quality over quantity (the best 1–2 a day); research 7–9 a.m.
  before the open; skip a trade whose research is unfinished.
- **"Broken short" → long:** the news and filings say short but the stock keeps rising: a GRADUAL trend (no capitulation
  phase), price breaks that rebound, a **tight intraday consolidation then a new high of day** (1- and 5-minute bars).
  Heuristic: where would a good mid-tier short seller's stop be? If it is breached (especially after late morning) the
  trapped shorts fuel it — *"Not here; not today"* means it is a long. A stop-out of longs followed by a new high (VRPX
  2021) = *"go-time on the upside"*.
- **Shape:** shorts that work go *"straight up and then straight down"*; consolidations on the way up mark broken shorts.
- **Exits / holding:** longs exit on a trailing stop or when they go parabolic (then often flip short); **shorts last 1–3
  days — longer is a red flag.**
- **Large caps (e.g. TSLA):** no dilution / identifiable seller; wait for an obvious news-triggered parabolic move, then
  judge the news and the technical nature of the rally. (Part 1 ends mid-answer.)

### Parts 2–3 (same excerpt; notes + short quotes)
- **Large caps:** the same parabolic short *"in a more legitimate company"*; no identifiable seller, so it is the news +
  the technical nature of the rally. **Longs mirror the shorts — a capitulation trade** (a month-long rally reversed in two
  days → mean reversion); a true capitulation looks like **gap-down openings on increasingly high volume for several days**
  (April 2025 tariffs: three days). **Capitulation buys are rare; capitulation shorts are common.** If early, the stop
  protects and he tries again.
- **Biggest winners (2021): parabolic meme-stock shorts** (GME twice, AMC, DWAC). GME: long at 120 as a broken short, out
  170; short ~350 and held through his stop to the $500+ overnight high — *"I wouldn't recommend following my actions in
  this trade"* (a broken rule that happened to work).
- **Pyramiding (since 2020):** after the first short, wait for the chart to give a reason to lower the stop; instead of
  cutting risk, ADD so the risk stays the same (~1%); repeat until profits are taken or stopped. *"This pyramiding strategy
  significantly increased the ratio of my average win to my average loss."* Reactive: wait for the signal, move the stop,
  size the add.
- **His two −$50M losses = rule breaks:** (1) shorting SPY with NO parabolic move (*"not a strategy-based trade ... stupid
  trade due to overconfidence"*), held as it ground to new highs; (2) Carvana: shorted *"one stage too early"*, rode it up,
  added, out at breakeven three months later, then **re-entered without the conditions and without a risk budget**, and
  exited after an earnings gap to a year-plus high (*"another broken short"*). Lessons he draws: only the setup; a risk
  budget on every trade; a gap to new highs on real news = out.
- **Risk:** 0.5–2% per trade — 1% typical mid/large cap, up to 2% on an A+ trade in a liquid stock; **size = risk ÷ stop
  distance** (a volatile stock gets a wide stop and a small size). A winner makes roughly 2x the risk on average. Win rate
  71% since 2018, plus a high win/loss ratio from the pyramid — *"I am very selective."*
- **Process:** the edge is high-level concepts that *"rhyme"*; small-cap shorting still works (a mentee trades it). An
  analyst alerts him only to obvious setups; *"reactive rather than predictive"*; the best trades *"fit all the boxes"* and
  look almost too good to be true.

### Part 4 (end of the excerpt)
- Wait for the market's signal; build your own method from other traders' ideas, never a copy (his 2016 "Robo-trader"
  exercise: combine the traits you admire). Trading is probabilities; tail risk is always near (Taleb). **Every blow-up
  started from one small, seemingly meaningless decision that compounded** — be vigilant. Act with intention; don't tie
  identity to the outcome.

### His ruling on it (2026-10-20, verbatim)
> "Yes, but let's do this in weekend. Also, his play is to short small caps, out filters are mainly for EPs, we haven't
> tested small caps for parabolic shorts"

Our parabolic-short floors (close >= $5, $10M dollar volume, cap >= $250M) came from the EP lane; small caps — where his
dilution / identifiable-seller rules live — have never been tested for parabolic shorts. The weekend replay reads both
populations (PLAN #314).
> "This is relevant to the dilution point" · "And it's not recent offering, the whole idea is stealth dilution that is in
> the horizon. Offering is after the fact" · "Eg warrants that the run up will unlock and convert to shares is the exact
> example given"

**The dilution rule, as he reads it:** count the shares that warrants and convertibles turn into once the run-up crosses
their exercise / conversion price (the "hidden" share count not visible in shares outstanding), and the holders who will
sell them — measured point-in-time BEFORE the climax. A completed offering is after the fact and is not the signal.

## 2026-10-21 — his idea: RANK breakouts like EPs and trade only the A+ ones (operator, verbatim)

> "idea, for breakouts we'll also need ranking similar to what we try to do with EPs, but breakouts are going to be more
> common and we need a rating system to select the best ones. I recall the backtest showed 8000+ breakouts (?), that is way
> too many trades even in a 5yr period, let alone 1 or 2 yr. We need to focus on the A+ setups per Qullamaggie, he
> definitely doesn't trade all however many thousands breakouts per year."

Counts behind it (the primary, trendline level): every breakout (C0) ~3,300 a year in 2022–24 (8,989 in 2.75 years, ~63 a
week) and ~2,800 a year in 2017–21 (~53 a week); the strict group (C1) only ~29–37 a year — yet C1 shows no edge and kept
just 10 of the 352 trades on the 39 known 2020–21 multibaggers. So a FILTER has been selecting the wrong things; a RATING
that picks the best few a week from all breakouts is the untested alternative (#705).
> "yes, we should also have some secondary indicators to test, like group themes, etc." (2026-10-21, on the A+ rating)

**Ruled:** #705's round-2 read is ONE A+ rating (the two single-feature reads become its ingredients), plus SECONDARY indicators
tested on top of it — group strength and themes first. Data reach: industry-group strength (`grp_pct`, the group's 3-month
return percentile) exists in every era, so it is testable on 2017–21 and 2022–24; the theme engine's history starts 2026-03-19
(151 nights), so themes can only be read on 2026 breakouts (descriptive) and recorded forward by the shadow.

## 2026-10-22 — his lean on the stair-step number (which base in a run) for the A+ rating (operator, verbatim)

> "I'm not exactly sure, but I feel earlier the breakout the better. Later breakouts, may run out of momentum."

**Used as:** the A+ rating's stair-step ingredient is oriented EARLIER = BETTER (the first / second base of a run ranks above a later
one), registered as his stated lean with his uncertainty disclosed; the reverse orientation is reported beside as a sensitivity row,
never deciding (#705).

## 2026-10-22 — his ruling on base LENGTH in the A+ rating (operator, verbatim)

> "Ok. On line bases, volatility has to be contracting over time, tightening, if base is long but wide and loose, that's not good"

(Replying to: market condition used as a SPLIT of the result, not a scored input — "Ok"; and "a longer base rates higher" —
corrected.) **Used as:** base length is NOT rewarded on its own. What the rating scores is volatility CONTRACTING OVER THE
BASE (tightening over time — e.g. the ATR / daily range falling from the base's early part to its late part); a long base that
stays wide and loose scores badly. Base length alone is reported beside, never deciding (#705).

His follow-ups (verbatim): *"Long bases I meant"* · *"Volatility contraction can be fractal, what I mean is that you can see it
contract over months, weeks, days and or intraday. So a long base will see contract over weeks with highs and lows tightening, then
daily bars also tightening, etc. Not a hard rule but pattern should be visible"* ("Fractal not factual" — his correction).
**Used as:** contraction is read at SEVERAL SCALES and the rating rewards it being visible at more of them — weekly (the weekly
bars' highs and lows converging across the base), daily (the last days' ranges smaller than the base's earlier ones), and the
successive pullbacks inside the base getting shallower; intraday is not available before the fill. A score, never a hard gate.

## 2026-10-22 — his answers on the A+ rating's six mapped choices (operator, verbatim)

> "4. what does it mean not later in the day? Unlike EPs, breakout can happen anytime. Rest is ok"

**Used as:** 1, 2, 3, 5, 6 — yes (pullbacks as the third tightening scale; a missing scale counts as middling; the single
tightness snapshot out of the score; themes recorded forward only; best-of-1/3/6-month strength in the score). 4 — a breakout can
happen at ANY time of day, so the breakout-day range and volume are read over every minute BEFORE the entry fills, whenever it
fills (not just the first five minutes); the volume is compared with how much a normal day has traded by that minute.

## 2026-10-22 — AMRX: three entries EARLIER than our breakout entry (operator, verbatim, with his marked chart)

> "Btw, I got alert on this anticipation entry and looked at the chart, I'd probably enter the breakout a day earlier if trading breakout or even earlier if trading u&r or tight days anticipating breakout. I've marked up the chart myself for your reference."

(Replying to the 10-22 Family A digest: *"Confirm entry fired today (1) — base-high breakout + volume (control arm, SHADOW) · AMRX buy 20.48 · stop 18.79 (-8.3%)"*.)

His follow-up (verbatim): *"I only saw amrx after I got the alert it's a consolidation entry, so one of our system caught it, I just marked up the chart after the fact"*. **So AMRX is a CAUGHT name entered late, not a miss:** the anticipation board found it, and he marked the chart after its alert. The gap is the entry timing (one to two days earlier), not detection of the stock.

**🖼 Image:** `docs/methodology/operator_shared_charts/2026-10-22_amrx_family_a_entries/01_chart_marked.png` — his labels: *"Second inside day, vol contracted"*, *"Reclaim 10/20ma"*, *"Flag breakout day"*, plus a down-sloping line drawn from the 9-21 high.

**His marks on the bars** (from `mi_daily_closes`; volume as a multiple of the prior 20-day average):

| Date | His label | Bar | Note |
|---|---|---|---|
| 10-14 / 10-15 | (the undercut) | lows 18.86 / 18.79 | below the 10-08 low 18.97: the "U" of U&R |
| 10-16, 10-19 | "Second inside day, vol contracted" | 10-16 h 19.39 l 18.94 (inside 10-15), 10-19 h 19.45 l 18.95 | volume 0.70x and 0.69x |
| 10-20 | "Reclaim 10/20ma" | close 19.84 over 10-day 19.53 and 20-day 19.81 | volume 1.82x: the "R" of U&R |
| 10-21 | "Flag breakout day" | open 19.90, close 20.20, through his drawn line | volume 1.56x |
| 10-22 | (our confirm entry) | buy 20.48 (the base high), stop 18.785 (the base low) | volume 1.68x |

**What our system said:**
- The anticipation board (`mi_anticipation_consolidation`, anchor 09-28) held AMRX as `post_runup` and never `coiled`. On the 10-22 evaluation it showed no pullback shape and a tight-close streak of 0. So the in-coil "anticipate" arm never fired, and only the confirm arm fired, on 10-22.
- The consolidation breakout watch (#705's detector, `mi_consolidation_breakout_watch`) never listed AMRX. Its run-up was 16.56 (09-16 low) to 21.175 (09-21 high), +27.9%, under the 30% prior-move minimum (`PRIOR_MOVE_MIN = 0.30`).
- Same stop for comparison only (the stop is his to set; entries-and-exits-are-undetermined): with the 18.785 base-low stop, a buy near 19.45 (above the second inside day, 10-20) risks 3.4%, near 19.90 (10-21) risks 5.6%, and ours at 20.48 risks 8.3%.

**Used as:** a labelled Family A example. It names THREE separate setups, each earlier than our base-high breakout, and each needs its own buy point and stop (SETUP vs FAMILY):
1. tight days (inside days on contracting volume), bought in anticipation;
2. undercut and reclaim (U&R) of the 10/20-day averages;
3. the flag/trendline break, which maps to the existing `pivot_tl` level in `consolidation_breakout.explain_watch`.

The example feeds #705's entry question after the A+ read. It is not a verdict on the stock, and it is not a rule (htf-tweets-are-a-tuning-corpus).

## 2026-10-22 — what A+ means (operator, verbatim, replying to the #705 rating result)

> "A+ setup according to qullamaggie is based on the chart and technicals, tightness, etc."

(Replying to: his seven-ingredient A+ score read CAN'T TELL in 2017–21 and 2022–24 and is not recorded; the plan's rule names RS
leadership alone as the next test.)

**What the data already says about tightness** (read, not new; `docs/analysis/cb_aplus_rating_prereg_2026-10-21.md` RESULT):
- The score was built from his chart words: contraction at weekly, daily and pullback scale, volume dry-up, and upward expansion
  on the breakout day.
- Measured alone, tightness was among the weakest ingredients in both eras: contraction 0.79 / 0.76 big winners (≥ 10R) per
  100 against 1.235 / 0.946 for all breakouts. The 5-day range in ADR alone gave 0.82 / 0.36.
- 10-18: the tightest fifth of bases did WORST.

So either our numbers do not capture the tightness he sees on a chart, or tightness alone does not pick the outliers in this
population.

**Used as:** an open question for him — how to test HIS chart read of A+ (his eye as ground truth) against our measures. It is
not a rule change, and the registered RS-alone read is unaffected unless he says otherwise.

## 2026-10-22 — his labels are Qullamaggie's own (operator, verbatim, on my ask that he grade charts)

> "Didn't we already have all the setups discuss be qullamaggie directly on his streams, why you need me to label charts? The whole point is to quantify his system, what better labels then his own"

**Used as:** the ask for him to grade charts is WITHDRAWN. The ground truth for "what an A+ setup is" is Qullamaggie's own
words on his streams.
- **Already read once** (`docs/analysis/cb_selection_test_prereg_2026-10-19.md` RESULT): the 98 bases he DISCUSSED while they
  were still basing broke out no better than the average base of the same months (+1.01 vs +1.10 ADR over 20 sessions, CAN'T
  TELL).
- **That read's own limit is the next step:** a mention is not a trade. The stricter label is the subset he said he BOUGHT (or
  called his best). The captions carry those words, e.g. FCX 2023-01-26 *"I bought when it broke out of this flag"*. That subset
  is to be extracted from the captions (no outcome read) and tested as its own pre-registered read.

## 2026-10-22 — Qullamaggie grades on stream (operator, verbatim)

> "He often say it's A+ or not, or say it needs a free more days to tighten etc."

**Used as:** the stream captions carry Qullamaggie's own GRADES, not just mentions. That makes them the label set for A+.
- **A first $0 look at the raw caption text** (rolling captions repeat lines about 3×; not yet de-duplicated):
  - "few more days" appears on 580 caption lines and "needs to tighten" / "need to tighten" on 134;
  - "I bought" on 3,398 and "I'm long" on 390;
  - "A plus" / "A+" only on 15, so he rarely says the letter grade aloud in the captions.
- **Next (#705):** extract each graded moment (ticker, talk date, grade: bought / best / not yet — "needs a few more days" or
  "needs to tighten" / passed), outcome-free. Then pre-register two reads before any outcome:
  1. do the bases he bought or called best beat the ones he said were not ready yet, and the average base (selection);
  2. does our tightness measure separate his "not ready yet" bases from his "bought" ones (whether our numbers see the
     tightness he sees; detection, no outcome).

## 2026-10-22 — what a breakout IS (operator, verbatim, on the R decomposition)

> "\"When a big move comes, it starts 5–6 weeks after entry\" this points to wrong entry, the whole point of breakout is that it has broken the consolidation period and enter the expansion phase, if this is happening 5-6 weeks after then the entry is not a breakout by definition"

**⚠ Correction (10-22, mine):** the line he quoted was MY wording, and it was wrong. The 26–28 sessions are when the stock
REACHED a +5 ADR gain, not when its move began. A 5-ADR gain takes weeks to build at any starting point. His conclusion that
our trigger is early was tested on its own and holds (the base high is cleared later on 70–76% of fills), but the 5–6 weeks
is not evidence for it.

**Used as:** a DEFINITION. A breakout = the stock leaves the consolidation and enters the EXPANSION phase.
- A trigger after which the stock behaves like any ordinary stock for weeks, and moves (if at all) 5–6 weeks later, is not a
  breakout. It fired early or on the wrong level.
- So the decomposition's "selection" finding is re-read as an ENTRY-DEFINITION finding: our trigger (the trendline level, ORH5)
  is not catching the moment the base breaks into expansion.
- **Next (#705, measurement only):** does a real breakout — the base high cleared, on an expansion day — follow through more
  than matched ordinary stocks, and sooner? And for our triggers: when did the stock actually clear its base high relative to
  our entry?

## 2026-10-22 — where the edge comes from (operator, verbatim)

> "The edge comes from which breakout to pick (the A+ setups), but also positive risk v reward, taking small losses and making huge returns when right"

**Used as:** the edge has TWO parts, and both must be tested together.
1. **Selection:** the A+ setups.
2. **Asymmetric risk / reward:** small losses, huge returns when right.

**What the data already says about part 2 on our breakouts** (`cb_r_decomposition_2026-10-22.md`):
- The losses ARE small (about −1R each).
- The huge returns never come: a trade lasts a median 1 session (6–9 if the stop does not take it), while a 5-ADR gain takes
  5–6 weeks to build (the time to REACH it, not when it starts).
- Even on the hindsight winners (the 39), the current stop and exit kept 7.7% of the move.

So part 2 fails on HOLDING, not on loss size. Without part 1, holding longer only earns what any stock of that volatility earns
(the matched control). That is why the next read measures both on the same A+ set — his stream grades:
- do they move more than ordinary stocks;
- and what stop / hold keeps the move while the losses stay small (registered before any outcome).

## 2026-10-22 — false breakouts, and the recall check he asked for (operator, verbatim)

> "If the big moves really does come 5-6 weeks later then we just need to figure out how to but the real breakout as the big moves is already measured to be there"
> "False breakout happen, that's why we take tight stop losses"
> "We need to check of the big winners in a period, how many have a measurable breakout and how many do we catch"

**Used as:** a RECALL read, outcome-first, a detection question.
- Take the big winners of a period, then ask: how many began with a measurable breakout (a consolidation, then a break above
  it)? How many did our detector watch and trigger on? And what did our tight stop do to the ones we caught?
- False breakouts are expected; the tight stop is what makes them cheap. The read measures what the same stop does to the real
  ones.
- (The "5–6 weeks" in his first line was my wrong wording — it is the time to REACH a +5 ADR gain, not when the move starts.
  Corrected in the docs.)

## 2026-10-22 — what the comparison must measure (operator, verbatim)

> "What is the comparison measuring? We're not trying to pick winners over a year or two year, we're trying to buy a stock at the precise moment it gives the best risk to reward. We don't care about what the stock does outside this period."

**Used as:** a correction to the yardstick. The breakout-vs-ordinary-stock comparison in the R decomposition and the breakout
read measured the stock's DRIFT over 5–60 sessions (ADR units). That is the wrong question for a timing strategy. The right
measure is risk / reward AT THE ENTRY MOMENT:
- from the exact entry, with the same tight stop, how often and how far the stock gets (+2R / +5R / +10R) BEFORE the stop;
- compared with the same stop geometry placed on non-breakout moments: matched ordinary stocks on the same day, and the same
  stock on other days of its base.

The "no edge" statements so far are about drift only. Whether the breakout moment gives better risk / reward is UNMEASURED. It
is the next read after the big-winner recall.

## 2026-10-22 — getting stopped out is a stop / re-entry / timing problem, not "no edge in breakouts" (operator, verbatim)

> "If the issue is getting stopped out to really it's either a stop placement problem or a reentry problem, or entry timing but not that there's no edge in breakouts which is my point"

**Used as:** a correction of my framing. "No edge in breakouts" overstated what was measured. What IS measured, and what is not:

| Lever | Tested so far | Result |
|---|---|---|
| Stop placement | low-of-day, ½-ADR cap / floor, level − ½ ADR, base low — all capped at 1 ADR (`cb_his_exit_2026-10-18.md`) | all read the same as the day-low stop |
| Stop placement | wider than 1 ADR, or structural (the base low uncapped) | NOT TESTED |
| Re-entry | one / two / every re-break after a stop (`cb_reentry_prereg_2026-10-19.md`) | does not rescue it in 2022–24 (re-entries −0.13R), on OUR trigger |
| Entry timing | hourly-close confirmation (`cb_hourly_entry_prereg_2026-10-19.md`) | FAIL / same as ORH5 |
| Entry timing | the real breakout (base high cleared, expansion day) WITH ITS OWN STOP | NOT TESTED (only as drift) |
| The moment | the stop-relative race vs ordinary stocks with the same stop | NOT TESTED (breakouts alone sit at the coin-flip line) |

**Next (#705):** the untested rows, measured together on the same bases:
- the real-breakout entry with its own stop;
- stops beyond 1 ADR and the structural base-low stop;
- each against the same stop on matched ordinary stocks.

## 2026-10-22 — the trade count itself is a problem (operator, verbatim)

> "That is ridiculous amount, qullamaggie or any human definitely didn't trade that many breakouts, that in itself is an issue, we need to cut out 90% of the trades"

(Replying to: 13,363 breakout trades in 2017–21 (~53 a week), 8,984 in 2022–24 (~63 a week).)

**Used as:** the target population is about a tenth of C0, around 5 a week.
- **Already tried:** the A+ score's top 3 a week (534 / 288 trades — CAN'T TELL) and the strict C1 cell (180 / 79 — CAN'T TELL /
  FAIL).
- **His own breakout definition cuts close to 90% by itself:** the base high cleared on an expansion day (R2 in
  `cb_breakout_definition_2026-10-22.md`) is 1,582 / 927 entries, about 6 a week. It has not yet been tested with its own stop.
  It leads the next read.
- The graded stream picks follow.

## 2026-10-22 — bull / bear split (operator, verbatim)

> "We also split bull bear periods right? Breakouts tend to fail during bear phase, which should mean we either size down or reduce trading, this may affect R for the strategy"

**Measured the same night** (`scripts/probes/_702_race_1022/02_market_phase_split.txt`; C0 trades, the market read at D):
- **No simple market filter separates them consistently.** In 2017–21 the best breakouts came while SPY was BELOW its 200-day:
  +0.50R per trade, 2.1 big winners (≥ 10R) per 100, n = 1,654 — the 2020 rebound. Above it: −0.04R, 1.1 per 100.
- In 2022–24, below the 200-day was a little worse: −0.21R vs −0.15R.
- The QQQ 10-over-20 and QQQ-over-50-day readings split the wrong way or barely.
- So "trade less in a bear phase" would have cut 2020's best trades. Sizing by phase is his call (THE LINE). The phase stays a
  reported split in every read.

## 2026-10-22 — "uptrend / downtrend", not "bull / bear" (operator, verbatim)

> "Better phrasing should be uptrend vs downtrend instead of bull/bear, under 200d but trending up can still be uptrend"

**Used as:**
- The market split is named by TREND DIRECTION, uptrend / downtrend, never bull / bear.
- A market under its 200-day but turning up can be an uptrend.
- **Re-measured by direction** (`scripts/probes/_702_race_1022/03_market_trend_split.txt`): in 2017–21 the trades taken while
  SPY's 50-day average was FALLING did best (+0.57R per trade, 2.5 big winners per 100, n = 2,147) vs −0.08R when it was rising.
  That is the 2020 V-bottom: leaders broke out while the lagging averages still pointed down. In 2022–24 direction made no
  difference (−0.17R both ways).
- So lagging trend readings mislabel a V-bottom, and a trend filter built on them would have cut the best breakouts.

## 2026-10-22 — the recall goal (operator, verbatim)

> "I wouldn't expect to catch 100% , that's not the goal, but the really good setup ones we shouldn't miss or stopped before the run, even if we need to retry"

**Used as:** the goal is NOT full recall. It is that the really good setups are (1) watched, and (2) held when the run comes —
re-entering after a stop if needed.
- A retry rule is judged on the good-setup winners caught and held, AGAINST what the retries cost on the false breakouts.
- The next read measures exactly that: entry at the real breakout, stop variants, and up to two retries. It runs on (a) the
  measurable-breakout doublers and (b) every real breakout, with matched ordinary stocks given the same rules.
- The baseline from the recall check: 28 / 17 in at half-way of 481 / 258. Counting every fill, not just the first, 49 / 20
  were in at half-way — retries already show up.

## 2026-10-22 — trail variants as the stop (operator, verbatim)

> "On trailing the 10/20, we can test a decisive break vs quick reclaim, close below, etc. as stop"

**Used as:** the next EXIT read, after the stop / re-entry read showed the exit keeps a median 5% of the good-setup winners' moves.
It tests trail variants on the 10- and 20-day, each fixed numerically before any outcome:
- (a) the first close below (today's rule);
- (b) a DECISIVE break: a close below by ≥ 0.5 ADR, or two closes in a row below;
- (c) a QUICK RECLAIM forgiven: a close below exits only if no close back above it within 2 sessions;
- (d) an intraday low below, the tighter end.

Beside them, the +2R third sold or not. It runs on the same populations and harness as `cb_entry_stop_retry_2026-10-22.md`:
the good-setup doublers (held / kept), every real breakout vs matched ordinary stocks given the same rules. It is a measurement;
the exit rule is his call.

## 2026-10-22 — attack from both ends (operator, verbatim)

> "We need to attack from both ends, we need to filter to less breakouts, trade reasonable amount and have better way to keep winners without taking major losses"

**Used as:** the breakout work runs as TWO tracks that meet in one registered test.
- **Track A — fewer, better breakouts** (about 5–7 a week, not 55):
  - Qullamaggie's graded stream picks as the labels: what his A+ and "not yet" bases look like;
  - his own definition (the base high cleared on an expansion day, ~6–7 a week);
  - the held RS-leadership read;
  - not missing the good ones: the 50-day and 30%-run-up gates that blocked half the doublers.
- **Track B — keep the winners, keep losses small:**
  - the trail variants (decisive break / quick reclaim / close / intraday);
  - the +2R third or not;
  - the re-entry that holds about 45% of the good doublers to half their move;
  - the day-3 stall cut's interplay with the stop width.
- **Where they meet:** Track A's filter × Track B's exit, pre-registered with its bars and read ONCE on the sealed 2025–26.
- The filter, the exit and anything live are his call (THE LINE).

## 2026-10-23 — a standing data standard for backtests (operator, verbatim)

> "let's look we're still fiding issues, let's take a moment to categorize problems we know or potential ones we don't know and verify the data, and do so for future runs as well. Let's document this, and this should be in our trading brain/doc once we have it, how to best run backtests. Btw, we discussed alpaca's backtest api, any use here?"

**Used as:** a standing standard, not a one-off fix.
- `docs/methodology/backtest_data_standard.md`, plus reusable checks in `scripts/backtest_data_audit/`, being written by the
  2026-10-23 audit workflow. It holds the taxonomy of known and potential data problems and a STEP 0 data gate every registered
  read must pass.
- It moves into the trading knowledge vault (#707) when that exists.
- **Alpaca's backtest skill:** a reproducible-run workflow on the same Alpaca data, with the same blind spots: its universe is
  today's assets and it does not adjust spin-offs. We borrow its data fingerprint, fee schedule and buy-and-hold benchmark; it does
  not fix the data.

## 2026-10-23 evening — after the Track A fit FAIL (#705)

> "We need to continue and figure this out, the truth is qullamaggie used these setups to achieve 10x return in a year, in fact his ~10yr record consist of multiple 100%+ years. This works, we need to figure it out"

> "If we hit 1/66, if those 66 are real, why we miss them is the question"

> "Also, his record is audited, the returns are real, this means we can put the trades back together and achieve the same returns when looking back in those periods, that should be a fact"

Recorded as the standing frame for #705: the setups work (audited record); a backtest that fails to reproduce it is measuring our model of the method, not the method. Next read: replay his own stream-confirmed calls under his own rules (PLAN #705, Sat 10-24).

> "on your point about qullamaggie using 3 setups (breakouts, EP, parabolic shorts), which is true, but each one of the setup is high profitiable for him over multiple years, so the fact is that the setups work (at least in the past), so our backtest should show the same, if not that it's something wrong with our implementation and interpretation, not that it's not profitable given his returns using these setups are a historical audited fact"

Standing rule from this (2026-10-23): for breakouts, EPs and parabolic shorts alike, a backtest that does not reproduce profit over his years is a defect in OUR implementation or interpretation to be found — never a finding that the setup does not work.

> "what he shared is that he has compiled charts of his setups (thousands and thousands) into a database, studied them and gain confidence on his setups. THis is what I'm trying to do with charts, with rules, with backtest, etc. We're trying to recreate his knowledge base as a basis of our trading for apollo"

The north star for #705 / #707 (2026-10-23): rebuild Qullamaggie's own setup database — thousands of charts of each setup, studied until the rules are trusted — as the basis of Apollo's trading. Charts, rules and backtests are three views of that one database.

> "Slight correction, goal is to build trading knowledge brain and successfully trade those setups and strategies profitably. His database is just the starting point, proven to work, we want to rebuild it, extract knowledge, build on top of it, improve it and trade it profitably"

Corrected north star (supersedes the line above): the GOAL is a trading knowledge brain that trades these setups and strategies profitably. Qullamaggie's database is the proven STARTING POINT: rebuild it → extract the knowledge → build on top of it → improve it → trade it profitably.

> "I'm not sure how accurate that is, he buys orb high and states this many times and wrote this in his own webpage" (10-23, on my claim that he buys EPs after the gap day)

Correction recorded: a stream label's date is when he TALKED about a trade, not when he bought it. EPs are bought at the opening-range high on the gap day (his own page and streams); the labels tell us which EPs he took, not when.

> "ok" (2026-10-24, on the four vault forks: own private repo; notes + short quotes for external material; large assets in a local data folder with hashes; setups first) — recorded in `docs/design/trading_knowledge_vault_scope_2026-10-24.md`; the build is #708.

> "Iirc the bottom right of his screen is a stock list of his holding, can you verify?" (2026-10-24)

VERIFIED the same day on stream frames: the bottom-right TC2000 panel is the list "A - Positions" — titled so on 2019-11-12 (APPS frame: YINN, PBR, ENDP, RLGY, BABA, DXCM, TEVA, TDOC, MNK, BLDP, JD, MU, QLED, IPHI, APPS, FCEL, SE; "15 of 17 items") and 2021-04-07 (TDOC frame: AMAT, AAL, LRCX, TSM, SOXL, ALB, JETS, RBLX, TWTR, TQQQ, CLF, FCX, HOFV, NTLA, TIGR, SI; "20 items"); the same "A -" panel on 2020-06-15 (SHOP frame, 19 items, SHOP among them the day he said he bought it) and 2023-01-26 (MDGL frame, 8 items). It holds ETFs as well (TQQQ, SOXL, TNA, JETS, YINN). So every stream frame carries a snapshot of his holdings — the fullest record of his trades the streams hold.

> "The vault is living as in we will continue to build on it, and to it, at lessons, trading results, charts and setups, etc." (2026-10-24)

Standing rule from this: the vault is not a one-time migration. Every new lesson, trading result (each registered read's verdict), chart he shares and setup change goes INTO the vault as it is made — Apollo keeps only the implementation.
