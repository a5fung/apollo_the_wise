# #705 — Reverse-engineering his rules from his trades: pre-registration (2026-10-24)

**Status: REGISTERED, NOT FROZEN, NOT RUN. Revised before the freeze on 2026-10-24 (four pre-freeze reviews — a design review, an
independent recount, a module-vs-registration check and a re-check of the fixed module — every finding listed in §16).** Outcome-free: this registration read the holdings timeline's three TSVs (`entries`, `exits`, `snapshots`: names, dates, clocks,
flags), the two session calendars (era A's `sessions.txt`; era B's SPY dates from the export — dates only), the candidate and EP event
files' `ticker / E / K / split / primary` columns (event EXISTENCE on a day, nothing else), the security-type tables (`small_pulls.psv`,
`cb702_sic.psv`), the caption files (his words) and the `video_status` upload dates. No price bar after any buy day was read for any
2021-01-01+ trade; nothing of 2025-26 was opened (sealed, the runner's holdout); the frozen `trades.tsv.gz` and the exits study's per-trade
files were opened for their HEADER LINE only. **One forward fact was read:** event dates up to 5 sessions AFTER each buy window were counted
for all years (§2: 126 of the 633 no-event buys, 48 of them in 2021-22); an event after the buy day means the price crossed our level later,
which is forward price information. It is used nowhere as a feature and is split by fit / check year in §10. **The counts below were derived
by hand-run scripts (`scripts/probes/_705_reverse_1024/verify/recount_prefreeze.py` and the main loop's own checks) and are REPRODUCED by the
module's dry run (`01_rev_dryrun.txt`, every count below asserted against this file, ending `DRY RUN COMPLETE`; the fit stages refuse to run
without it).** Measurement and registration only. Nothing here changes or proposes to change a
strategy, an entry, a stop, an exit, a size, a safeguard or any live trade state — those are the operator's (THE LINE). The main loop
freezes this doc and the module, commits, runs the fit, writes the chosen rules above the freeze marker, pins, and runs the check ONCE.

**His words this serves (2026-10-24, verbatim, `docs/methodology/operator_shared_notes.md`):** *"Either way we need to reverse engineer his
rules"*; and the method: *"we can infer the buy and sell dates based on when the stock appears and when the stock disappears from the list.
And once we are able to lock down the date, we can infer the buy point based on the chart pattern, assuming he's using some form of his
rules to enter. We're not going to be exact, but we should be in the ballpark based on that."* **His rule for a miss (2026-10-23):** a
backtest that does not reproduce his profit is a defect in OUR implementation or interpretation, never a finding that the setup does not work.

## 0. In plain words

- **What changed.** Until today his rules were written FROM HIS WORDS and tested one by one; the exits study tried six and none reproduced
  his sells. From here his rules are INFERRED FROM HIS DECISIONS — what he bought, when, what he held through, when he sold — and his words
  are the cross-check, not the source.
- **The source.** His stream screen's "A - Positions" list (columns Flag · Sym · % Change · Vol Buzz — no size, fill, P&L or partial is
  visible; checked on frame `g_0000`). A name appearing = a buy inside a dated window; a name disappearing = a sell inside one. The
  timeline already turned 2,907 snapshots into 1,861 buys and 1,848 sells with their windows.
- **Four decisions, four inferences.** SELECT (which chart he bought, against everything else on offer that day), ENTER (at what level,
  bounded by the clock on the frames), STOP (which price levels he held THROUGH — a level he held through was not his stop), EXIT (a
  per-day hold-or-sell rule learned from the bar state). Plus WHY: his own caption words ("stopped out", "sold a third") joined to the
  trades the panel dates.
- **Stocks only.** ETFs and leveraged funds (UVXY, GUSH, AGQ, BOIL …) are removed from his buys AND from the comparison pool by one type
  rule (§2b); a stock our candidate stream never flagged is put back into SELECT.
- **The accuracy bar is BALLPARK, his word, and it is a number here before any run** (§6): a buy point counts as found when it sits inside
  the price range the stock traded between the frame that showed him flat and the frame that showed him holding, or within a quarter of a
  day's typical range (0.25 ADR20) of it — and it must beat a random price from the same day by 15 points, so a lucky guess cannot pass.
  It is scored only where the flat frame was taken during the session (at a pre-market flat frame the opening price passes by construction).
- **What is already seen.** 2020 and 2021-22 are not blank pages: the exits study described his exits for every dated trade in every year,
  and the holdings replay printed our fills against his clock. §10 lists what was seen per decision type and builds each check only on
  what was not: the no-event buys (his buys where our detectors fired nothing) carry most of the honest checks.
- **Action from him: none.** The six design choices are DECIDED in §15 (main loop; no money, not THE LINE). The minute fetch ran on
  2026-10-24 with his permission (§12: 1,302 of the 1,322 pairs fetched, 20 empty at the source and listed); nothing waits on him before the freeze.

## 1. The four questions of the standard

1. **Decision served:** what rule set, inferred from his panel trades, reproduces his decisions — so that the gap between his record and
   our replay can be closed where it actually is (selection, entry timing, the stop, or the exit) instead of guessed from his words.
2. **What would change it:** the per-decision bars in §5–§9, fixed before any outcome; the sealed one-shot in §12.
3. **Population:** §2 — the timeline's entries, split by what our detectors saw, with exact buy days where the panel gives one; §2b — the
   sets actually used after the type gate, the inverted windows and the same-day re-buys come out.
4. **What would make this wrong:**
   - (a) **Survivorship.** The panel shows only buys still held at a snapshot. A round trip completed between two streams is invisible; of
     the 264 dated buys in the dense window, 42 had left the panel by the buy day's close and those are the quickest exits we CAN see.
     **Every rule inferred here is a rule for trades he held at least to one stream frame.** For the same reason SELECT reads the chart up
     to the session BEFORE the buy day plus the buy day's open (§5b): a buy-day close looks strong partly because he only shows it when it
     survived to the frame.
   - (b) **The panel reads by OCR** (symbols ~98% right at 1080p). The timeline's guards (duplicates, two-snapshot exits, blips, flickers,
     the look-alike rename) are inherited unchanged; a residual misread is an undated entry whose bar state is noise — it lowers recall,
     it never manufactures a rule.
   - (c) **A position has no side.** A parabolic short reads as a long. The no-event population is where his shorts most likely sit; the
     EP-dated subset was already the dirtier one in the holdings replay.
   - (d) **A window is not a day.** 427 of the 633 no-event buys have a one-session window; 8 of those are inverted windows (the frames
     contradict each other and the timeline forced the window to one day), so their day is forced, not known — they are excluded (§2b).
     206 span 2–10 sessions and are PLACED by a rule (§5c) — placed days are never fit material.
   - (e) **The clock bounds a minute, not a price.** The frames give the minute he was still flat and the minute he was first seen holding
     (in-session brackets after §2b: median 23.5 minutes on dated buys, 35 on undated); the price he paid is inferred inside that bracket, never read.
   - (f) **Learned rules fish.** Every model family, feature list, threshold grid, threshold direction and selection criterion is fixed in
     this document (§5–§8) before the fit; the fit chooses WITHIN a family and nothing is added after. SELECT's search (about 4 million
     candidate conditions) is held against a planted-name control before its check is read (§5b). The exits study's erratum (a rule seen
     before it was registered) is the lesson applied.
   - (g) **Population shift.** The clean EXIT check is on no-event buys while the fit holds dated ones; a FAIL there could be the rule or
     the population. A within-population time split runs beside so the two are separable (§8).
   - (h) **Twenty buy days have no minute bars at the source** (§12: the fetch of 2026-10-24 returned 1,302 of the 1,322 pairs; the 20 empty
     pairs — AXNX for seven sessions of January 2020, FBR, HTZ, FACT, CHRD, SRTA, U, XP — abstain `no_minutes`, counted and listed by the dry run
     with the set each sits in — none in a check set, one an ENTER fit bracket). Before the fetch only 11 of the 108 undated in-session
     brackets in the dense window had minute bars.
   - (i) **The type table is not point in time** (one row per symbol as of 2026-10-16). LAZR (Luminar, a stock in 2020-22) is typed ETF
     today and is kept by a one-name override; any other symbol whose current holder differs is mistyped the same way and is not caught.

## 2. POPULATION — what the panel gives, split by what our detectors saw (outcome-free; the timeline's partition as is)

The timeline (`scripts/probes/_705_holdings_1024/01_timeline.py`, pinned by the holdings replay) is taken as is: 1,874 entries, 13 initial,
**1,861 non-initial** (2017-01 .. 2023-12; 2,907 snapshots in 517 streams). Nothing in it is edited. The buy day of an undated entry is
its window start (`lo`), as in the holdings module's `load_events`; every year and era below is on that basis.

| group | n | names | how our detectors saw it | role here |
|---|---|---|---|---|
| **dated, deciding** (a tl breakout or EP gap day inside a window ≤ 10 sessions) | **294** | 153 | our event fired on the buy day | ENTER / STOP / EXIT fit material; 264 in the dense window 2020-01-27..2022-06-14 (2020: 149, 2021-22: 115); exits known for 290 |
| dated, window > 10 | 50 | 47 | our event fired, the window is too wide to trust | beside only (held-to-exit median 116 sessions — STREAM SPARSITY, not long holds: 21 of the 50 are 2017–18, where one stream a year or a 164-day gap makes every window wide) |
| **no event, non-flicker, window ≤ 10** | **633** | 274 | **our breakout and EP definitions fired NOTHING inside the window**; every name has bars and sits in a candidate stream | **the SELECT population** (after §2b); 427 have a one-session window, 103 a 2-session window, 66 3–5, 37 6–10 |
| no event, flicker, window ≤ 10 | 349 | 196 | same, but seen in one stream and gone within 5 sessions | beside for SELECT; INCLUDED for STOP / EXIT (273 have a one-session window; they hold the quick round trips) |
| no event, window > 10 | 58 | — | same, window too wide | listed, not used |
| never a candidate | 360 | 147 | bars exist, no event, never in our candidate stream. By type: 233 funds or non-stocks (ETF 178 — TQQQ 26, SOXL 21, TNA 16, SPXL 14 …; ETV 32; ETN 19; other 4), 53 typed stocks (CS / ADRC: GOEV, OGI, NAK, IBIO …), 74 with no type row (DIDI, GRUB, GSX, HOFV, IDEX … mostly delisted companies, some SPAC shells) | the 127 that pass the type gate re-enter SELECT (§2b); beside in ENTER / STOP / EXIT (their minutes are not on the fetch list) |
| no bars | 117 | 81 | SPACs, ETNs, OTC (NO, SBE, TVIX, ICP, CCIV …) | out |

**The 633 no-event buys against our events just OUTSIDE their window** (event dates only; each buy counted once, in this priority order:
another level fired inside the window, then an event 1–5 sessions before, then 1–5 after, then 6–20 before): 343 have none of our events
within 20 sessions before or 5 after — a chart condition our definitions do not carry at all; 97 had one 6–20 sessions before (a late buy
of an old breakout, or an add); 69 had one 1–5 sessions before (he bought a few days after our trigger); **77 had one 1–5 sessions AFTER
the window and none 1–5 before (he was in before our line broke — the same shape the census found: 57 strict pairs with the talk before our
event)**; 47 had one of our OTHER level definitions (k5 / k10 / full / com) fire inside the window while `tl` did not. Counted without the
priority, **126 of the 633 have an event 1–5 sessions after** (forward information; split in §10). By buy year (window start) the 633 fall
2017: 6 · 2019: 69 · 2020: 301 · 2021: 196 · 2022: 45 · 2023: 16; 597 are era-A buys, 36 era B; 24 touch the Q1-2022 hole.

**One-session-window no-event buys, as the timeline gives them (before §2b):**

| set | all years | dense window | 2020 (01-27..12-31) | 2021-01-04..2022-06-14 | trade-days (buy day .. exit window's last session) | held to the window's last session, median |
|---|---|---|---|---|---|---|
| non-flicker | 427 (exits known 427; 8 inverted) | 374 | 197 | 177 | 4,436 all years · 3,203 to the window's first session | 6 sessions |
| flickers included | 700 (273 flickers; 161 left by the buy day's close; 26 inverted) | 615 | 335 | 280 | 3,438 in the window | 3 sessions |
| dated deciding (for scale) | 294 (exits known 290; 42 same-day exits; 91 flickers) | 264 | 149 | 115 | 3,351 all years · 2,260 to the first session | 5 sessions |

**The clock on the buy day** (ET). One definition for dated and undated alike — the timeline's `panel_clocks()` with the buy day as E:
`first_clock` = the first in-session frame on the buy day showing the name; `flat_clock` = the last full frame on the buy day without it.
**A bracket counts for scoring only when the flat frame is itself in session (at or after 09:30 — the frame's context is `in` in the
timeline's pre / in / closed reading; a pre-market or after-close frame gives no in-session bracket).** Dated deciding in the window: first
seen in session on the buy day **172**; a flat frame on the buy day **185 (in session 94, pre-market 91)**; both **135, of which 53 have
an in-session flat frame** (2020: 32, 2021-22: 21) — in-session bracket width median 24 minutes (quartiles 15–42; 29 are ≤ 30 minutes);
82 bracket from a pre-market flat frame (beside, §6c); 37 have no flat frame that day; **held before 09:35 — before any opening-range fill
can exist — 9** (TSLA 2020-04-14, UAL 05-27, DXCM 07-29, PINS 07-31, SHOP and TTD 08-26, KOLD 2022-04-19, LAC and TSLA 04-21). One-session
no-event buys in the window: first seen in session 237 (2020: 122, 2021-22: 115); every one has a flat frame that day; **in-session
brackets 108** (60 / 48; width median 35.5 minutes, quartiles 21–56.5), pre-market-flat 129; held before 09:35: 1 (ROKU 2020-09-15, a
pre-market-flat bracket); with flickers 175 in-session brackets (103 / 72; median 34 minutes). The stored `first_clock_on_E` /
`flat_clock_on_E` columns of `entries.tsv` are filled for dated rows only (re-derived here: they match `panel_clocks()` on all 264 dated
rows in the window) and EMPTY for every undated row; the module writes both columns for every row from the one derivation and its dry run
asserts these counts from them.

**Re-buys:** 280 of the 684 panel names carry more than one entry (1,467 entries). **A re-buy = an entry whose window start lies 0–14
calendar days after the same name's previous non-initial entry's `exit_hi`: 564** (2020: 282, 2021: 184, 2019: 60, 2022: 28; 75 of them
deciding, 486 undated) — the one definition used in §7. **A same-day re-buy** (a later entry of the same name on the same buy day — the
holdings module walks none) sits in the sets too: 8 of the 427, 24 of the 700, 2 of the dated 294 (PLUG, SNAP).

**Captions (his words), parsed with the repo's `qmlib.parse_vtt` (`scripts/probes/_qm_streams/qmlib.py`), lowercased, joined by spaces.**
495 videos carry a caption track. **The phrase set, pinned as one alternation:**
`\bstopped out\b|\bgot stopped\b|\bstopped me out\b|\bi sold\b|\bsold it\b|\bsold all\b|\bsold everything\b|\bsold out\b|\bsold a third\b|\bsold half\b|\bsold some\b|\btook partials?\b|\btook profits?\b|\btrimmed\b|\bi closed it\b`.
It occurs **4,015 times in 477 videos** (by upload year 2020: 2,224 · 2021: 884 · 2017: 425 · 2019: 341 · 2022: 87 · 2023: 41 · 2018: 13);
single forms: *"i sold"* 1,221, *"stopped out"* 2,099, *"i got stopped"* 883, *"stopped me out"* 321. **2,261 sit within 30 seconds of a
ticker mention; 786 of those name a ticker whose panel exit window covers the stream's session** (2020: 495, 2021: 212), reaching 380
distinct panel trades (before §2b), 88 of them deciding; 150 are ambiguous (two trades qualify). This is the WHY population before any
hand read (§9). The module's dry run prints this chain from the pinned alternation.

## 2b. THE SETS USED — after the type gate, the inverted windows and the same-day re-buys (one rule, applied in this order)

1. **Type gate, his buys and the pool alike.** The type of a name = `security_type_check.resolve_type` (`small_pulls.psv`, else the SIC
   pull `cb702_sic.psv`), keyed by `sym_a` on era-A buy days and by the panel symbol on era-B days; admitted: CS, ADRC, or no type row
   (the data standard's U rule as it stands; the no-type-row buys are flagged and every SELECT number is also printed without them).
   One override: LAZR (typed ETF today; Luminar, a stock in 2020-22). The table is as of 2026-10-16, not point in time (§1i).
2. **Inverted windows out** of every fit and check set, listed beside (their buy day is forced, not known).
3. **Same-day re-buys out** (the first entry of a name on its buy day stays); every set is also printed with them, beside.
4. **Never-a-candidate stocks back in, for SELECT only** (the 127 typed CS / ADRC or untyped): dropping them made SELECT depend on our own
   detector's candidate stream. Their one-session non-flicker buys add at most 12 (2020) and 15 (2021-22).
5. **His buys meet the pool's own floor (§3) on the session before the buy day,** or they are listed beside and kept out of recall — a
   buy the pool scan could never contain cannot test a condition measured on the pool. Read by the ONE floor function the fit uses, after the
   record builder (§13: in the era's export, a bar on the buy day, ≥ 50 bars before it): the prior session adjacent to the buy day, 130
   consecutive sessions ending there, raw close ≥ $5, 20-session median export close × export volume ≥ $10M. Counted by the dry run (the fit
   reproduces it): fit 188 → 136, check 145 → 121, never-a-candidate 12 → 0 / 15 → 1, flickers 116 → 79 / 81 → 69 pass; the loss reasons are
   printed (fit: 31 under $5, 13 short of 130 sessions, 6 under $10M, 2 without a bar on the buy day).

| set | as the timeline gives it | − type | − inverted | − same-day | **used** (before step 5) |
|---|---|---|---|---|---|
| no-event non-flicker, window ≤ 10 | 633 | 55 (UVXY 7, AGQ 7, GUSH 7, ERX 5, FAS 5, BOIL 5, KWEB 4, SLV 3, BRZU, JETS, VXX 2 each, 6 others 1 each) | 8 | 8 | **562** (one-session 375; 2–10 sessions 187) |
| SELECT fit: one-session non-flicker, 2020 | 197 | 5 | 2 | 2 | **188** (+ up to 12 never-a-candidate = 200; flickers beside 116) |
| SELECT check: one-session non-flicker, 2021-01-04..2022-06-14 | 177 | 30 | 1 | 1 | **145** (+ up to 15 = 160; flickers beside 81) |
| SELECT beside: 2017 / 2019 / 2023 one-session non-flicker | 1 / 35 / 7 | | | | 1 / 26 / 5 |
| STOP / EXIT undated fit: one-session incl. flickers, 2020 | 335 | 9 | 14 | 8 | **304** (1,822 trade-days; 188 non-flicker) |
| STOP / EXIT undated check: one-session incl. flickers, 2021-22 | 280 | 51 | 2 | 1 | **226** (1,260 trade-days; 145 non-flicker) |
| dated deciding | 294 | 2 (BOIL 2021-05-17, KOLD 2022-04-19) | 0 | 2 (PLUG, SNAP) | **290** (286 with known exits; 2020: 149; 2021-22: 111) |

KOLD leaves the held-before-09:35 list, which becomes 8 dated + 1 undated.

## 3. THE CONTROLS (deciding nothing; each names the failure it guards)

- **The positive control of SELECT — the 290 dated buys.** Our event fired on them by construction. A condition recovered on the no-event
  buys is also scored on them: if it fires on most of the 290 as well, he has one way of buying and we were missing part of it; if it
  fires on the no-event buys and not the 290, he has two setups and both get a name (never one).
- **The negative control of SELECT — the same-day pool.** On each buy day, every ticker in the era's export with **raw close ≥ $5 on the
  session before the buy day** (era A's `daily_raw_close.csv.gz`, which covers every fit and check day up to 2022-06-30, joined by
  `sym_a`; a beside-only buy after 2022-06-30 uses era B's export close and says so), **20-session median of the export's close × the
  export's volume ≥ $10M** over the 20 sessions ending on that session (both split-adjusted on ONE basis, so the product is split-invariant —
  the data standard's U rule; a raw close × adjusted volume carried later splits back into a 2020 decision: TSLA read 15× too high, CODX 30×
  too low — check H2), **type CS / ADRC / no type row** (§2b step 1) and **130 consecutive sessions of history ending on the session before
  the buy day, which is itself the session before it** (no hole) — the pool names not held by him that day, plus his pick itself (§5d). A
  condition's **pool rate** is the share of the POOLED (ticker, day) rows over the fit days meeting it (one rate over all rows, not a per-day
  average); the planted-wrong-ticker rate of the census (19% for a `tl` event) is the reference for what a coincidence looks like.
- **The search control of SELECT — planted names.** On the fit days, one random pool name is drawn per fit buy, uniformly from that day's
  pool rows of names he did not hold (seed 702, key `rev|select|k`, k = 1..20) and the identical search of §5b is run on those 20 planted sets. The real fit's recall must beat at least 19
  of the 20 planted runs at the same pool-rate cap, or SELECT is reported INCONCLUSIVE before its check is read.
- **The price control of ENTER — a random level from the same session.** For each bracketed trade, 200 seeded levels (seed 702, key
  `rev|minute`), each the close of a uniformly random minute of that session (09:30–16:00); a drawn minute without a bar takes the nearest
  prior bar's close (before the first bar, the first bar's open); each level's feasibility (first crossing inside the bracket) and
  hit-or-ballpark are scored exactly as a candidate level's. The control's shares are the floor every level must
  beat by 15 points (§6c).
- **The held-through control of STOP — a level he could not have used.** Two ADR20 below the fill (S8), and the 50-day average: levels so
  wide that holding through them says nothing. Their held-through rate calibrates what "rarely held through" means on each population;
  neither is ever chosen as "his stop" (§7b).
- **The trivial exits of EXIT** — "sell at the close of session 3" (his median hold of 3 trade-days; the buy day is session 1, so the
  close two sessions after it) and "sell on the first red close" (read from session 2 on — the buy day's own close is not scored): their hit
  rates on the check are the floor for the learned rule's hit rate.
- **The ambiguity control of WHY** — a phrase whose 30-second window names TWO tickers with qualifying exit windows is excluded from any
  rate (150 of 786); the 20 hand-read joins (§9) measure the rest.

## 4. THE INFERENCE CHAIN — order, and what each stage holds fixed

SELECT → ENTER → STOP → EXIT, each consuming the stage before it; every stage runs on its own fit set, is frozen, and is checked once.

| stage | holds fixed | produces | consumed by |
|---|---|---|---|
| SELECT | the buy WINDOW (the panel's) | the bar-state condition(s) he buys; the placed day for 2–10-session windows | ENTER (the day), the sealed test (the universe filter) |
| ENTER | the buy day; the bracket | the level he buys at (one of six) and the inferred price | STOP (the fill and its R unit), EXIT (R so far) |
| STOP | the inferred fill: **the chosen level where it is feasible on that trade; otherwise the registered fill (ORH5 where it filled, the open of lo for undated), flagged `fill_fallback` and counted — the SAME rule for dated and undated trades, so the R unit does not shift between the EXIT fit and check** | the tightest level he rarely holds through, in two variants | EXIT (R so far, max R); the sizing of §7c |
| EXIT | the inferred fill and stop | a per-day hold/sell rule | the sealed test |

If a stage FAILS its check (or reads INCONCLUSIVE, or VOID for EXIT), the next stage runs on the REGISTERED reading instead (ENTER → ORH5 /
the open for undated; STOP → the low of the day at the fill / one ADR20 for undated; EXIT → the speed trail) and says so; nothing is
re-fit.

## 5. SELECT — what he bought, against what was available

**5a. What the panel observes.** A name appears → bought inside [lo, hi] sessions. For the one-session windows lo = hi (exact; the
inverted ones excluded, §2b). The chart up to the buy day's open is outcome-free for every year and carries no survival from that day.

**5b. The event-recall read (first).** On each exact-day no-event buy, the bar state — 17 features, fixed now, every one in ADR20 units or
a universe percentile so eras compare. **Every feature is computed on bars up to the session BEFORE the buy day (called "the prior
session" below), plus the buy day's open for F14.** F1 the prior close vs the max high of the 20 sessions before it (≥ 0 = a 20-day high)
· F2 the same vs the 50 before it · F3 sessions since the highest high of the 252 sessions ending at the prior session (fewer when the history is
shorter) · F4 the 10-session range (high − low) · F5 / F6 / F7 the prior close vs SMA10 / SMA20 / SMA50 · F8 the prior close vs the close 20
sessions earlier (%) · F9 vs 60 sessions earlier · F10 ADR20 (%) · F11 the prior session's volume ÷ the mean volume of the 20 sessions BEFORE
it · F12 the prior session's range · F13 the prior close's position in the prior session's range, (close − low) ÷ (high − low), 0.5 when
high = low · F14 the buy day's open gap vs the prior close · F15 the 63-session return's percentile in that day's pool (the share of pool
returns below the pick's plus half the ties, the pick's own return included) · F16 the same for the 21-session return · F17 QQQ's prior close
vs its 10- and 20-day (above both / mixed / below both). **Beside, flagged
`survival-confounded`:** the same F1, F2, F11, F12, F13 read on the buy day's own bar; they decide nothing.

- **The family:** a conjunction of at most 3 single-feature thresholds; thresholds from a fixed grid = the pool's deciles (10th .. 90th) on
  the fit days — the days of the FIT BUYS only; every other day a pick is read on (flicker, beside, positive-control and window sessions) gets
  its own same-day pool for F15 / F16 alone, which enters no grid and no pool rate (F17 is categorical); **each threshold may be ≤ or ≥**
  (about 4 million candidate conditions in all). **Selection:** the conjunction with the highest recall on the fit buys subject to pool rate
  ≤ 20%; ties → fewer conditions, then the higher lift (recall ÷ pool rate), then grid order. Up to three conjunctions are kept greedily:
  each must add ≥ 10 points of recall, have its own pool rate ≤ 20% and keep the SET's pool rate (the union of its rows) ≤ 20%; the one
  adding the most recall is taken, ties by the same order (he may have more than one way of buying) — the "condition set". **Short-cluster flag (fixed now):** a conjunction whose buys have a median F8 or F9 (the prior 20- / 60-
  session move) above the pool's 95th percentile is flagged `parabolic_short?` — a stock that has already run that far is what he
  SHORTS, and the panel cannot show the side; the flag is carried into ENTER / STOP / EXIT and arms §8c's void rule.
- **Fit set:** the 188 exact-day non-flicker no-event buys of 2020-01-27..12-31 plus up to 12 never-a-candidate stocks, after the record
  builder and the pool floor (§2b step 5, counted there; flickers beside: 116). **Check set:** the 145 of 2021-01-04..2022-06-14 plus up to 15,
  after the same floor (flickers beside: 81); its pool is built on the check buys' days only, as the fit's is on the fit buys' days.
  **Beside:** the 2017 / 2019 exact-day buys (1 / 26 non-flicker, scored on era A), the 2023 buys (5 non-flicker) LISTED and not scored (era
  B, whose pool this stage does not build), the positive control (the 290), and the 47 buys where a k5 / k10 / full / com level fired inside
  the window (does the condition set find the same ones our other levels did?). **The 47 are split by year (re-check N3):** the fit reads
  the 32 of 2019 / 2020 / 2023 (2019: 1, 2020: 30, 2023: 1 — the 2023 one counted, not scored: era B); **the 15 of 2021 are read in `--check` only**,
  beside — 12 of them are SELECT check buys (PINS 2021-01-20, MELI 02-19, GMBL 03-02, W 03-15, AMAT 03-26, BNTX 05-25, RIOT 06-28, NVAX
  06-29, LTHM 10-12, CCJ 11-08, TSLA 11-19 and 11-30) and 3 are 2–10-session windows (SHOP 2021-04-08, SNOW 12-21, ZS 12-21), whose
  sessions §5c's placement still scores at the fit as it does every window's; none is of 2022 (the dry run asserts the split).
- **Search control first (§3):** the fit's recall must beat at least 19 of the 20 planted-name runs, or SELECT is INCONCLUSIVE and its
  check is not read.
- **PASS:** the CHOSEN condition set's recall on the check ≥ 50% at pool rate ≤ 20% (lift ≥ 2.5×). **Falsifier:** the CHOSEN condition
  set's lift on the check < 2.0 → the no-event buys are not a bar-state condition our daily bars can see (news, intraday, discretion,
  shorts). **Anything between the falsifier and PASS reads INCONCLUSIVE.** No conjunction other than the chosen set is scored on the check.

**5c. Placing a buy whose window spans 2–10 sessions (187 after §2b).** The window's sessions are scored by the FITTED condition set (each
session on its own prior-session bars and open, against its own same-day pool for F15 / F16; a session where the stock fails the pool floor,
or whose pool rows are missing, never meets it and is counted); the buy is placed on the LATEST session meeting it (the holdings replay's R1: the most
recent trigger opened the position held at hi); no session meets it → placed on lo (the first session a buy could be missing from),
flagged `placed_by_default`. **Placed days are never fit material** (the fit is exact-day only, §5b) — they are read beside in ENTER /
STOP / EXIT with their own flag. The same rule places the dated-but-wider 50 beside.

**5d. Selection against the pool (second).** Among the pool names meeting the condition set on each check day, a rank score on F1–F17 (a
logistic fit on the 2020 buys vs the 2020 qualifying pool, no interactions, L2 at λ = 1 on standardised features — no tuning) ranks the
check day's qualifying pool — **the qualifying names he did not hold that day, plus the pick itself**; his picks' percentile within it is
read. **PASS:** his picks' median percentile ≤ 0.25 (he picks from the top quarter of what qualifies). **Falsifier:** median ≥ 0.40 →
beyond the condition, his pick is not in these features (theme, news, the chart by eye). Between them: INCONCLUSIVE. Beside: the same on
the dated 290 against the `tl` same-day pool — the names our trendline fired on that day that meet the pool floor, not held, plus the pick;
run at the fit, where the rank model is fitted, reading no bar after any buy day (the holdings replay's band already says his dated picks
beat it 3.6× vs 1.07× — a result known, disclosed, not used to fit).

## 6. ENTER — the level, bounded by the clock (his method: date from the list, then the buy point from the chart)

**6a. What the panel observes.** On a bracketed buy day the stock was NOT in his book at `flat_clock` and WAS at `first_clock`; he bought in
between. On the 8 dated + 1 undated held-before-09:35 days, he held before any opening-range fill exists.

**6b. Candidate levels (six, fixed):** L1 the 5-minute opening-range high (dated: max of it and the breakout level — the holdings replay's
ORH5; undated: the opening-range high alone) · L2 the prior session's high · L3 the base high (dated breakout: the candidate row's pivot; EP-dated and
undated: the max high of the prior 20 sessions — an EP row's pivot is its prior close, which is L5) · L4 the session's open · L5 the prior
close (an EP's gap-day level) · L6 the first-hour high. **A level is scored only once it exists:** L1 needs `first_clock` at or after 09:35
and L6 at or after 10:30; a bracket that closes before that reads `no_level_yet` for the level — not feasible, neither HIT nor MISS, counted. A level
is **feasible** on a trade when price FIRST crossed it inside the bracket: crossed before `flat_clock` → he would already have been in →
not his trigger; not crossed by `first_clock` → not his trigger. **Feasibility and HIT are scored only on in-session brackets** (the flat
frame at or after 09:30 ET on the buy day). Brackets with a pre-market flat frame are read beside, because there L4 and L5 are crossed at
the first minute by construction and cannot be told apart from "bought at the open". **On an in-session bracket L4 is never feasible** (the
open trades at 09:30, before any in-session flat frame) and L5 is feasible only when the stock opened below the prior close and crossed it
later; both stay in the list so the readout shows it.

**6c. BALLPARK, as a number (his word; fixed before any run).** The inferred buy price = the level. The bracket's traded range = [the lowest
low, the highest high] of the minutes in (`flat_clock`, `first_clock`]. **HIT** = the level lies inside that range. **BALLPARK** = within
0.25 ADR20 (a quarter of a typical day's range) of the range's nearer edge — the clock reads to the minute and the frame may lag the fill.
**MISS** otherwise. Read beside, never deciding: pre-market-flat brackets (dated 82, undated non-flicker 113 after §2b) under the same
test; first seen in session with no flat frame that day (dated 36 after §2b): the ballpark is within 0.5 ADR20 of the level's first
crossing price; pre-market first sightings (he held at the next morning's frame; 78 of the 260 dated in the window after §2b): no bracket,
the level test degrades to "crossed that session" — per level, the share of those sessions that crossed it at all.

- **Fit set:** the 32 in-session-bracketed dated + 59 in-session-bracketed exact-day undated buys of 2020 (94 undated with flickers; the
  non-flicker brackets decide, the flicker brackets are beside — R1's one exception). **Check set:** 20 + 44 of 2021-22 (63 undated with
  flickers). An ENTER record needs 20 bars before the buy day (ADR20, the prior-20 high and low; §13 counts the records). **Chosen level** =
  the highest feasible share on the fit (ties → L1, the registered reading). **The deciding set of the check:** when the chosen level is L1
  the undated 44 decide ALONE — L1 on the dated 20 is a re-read (§10), printed beside — 41 records after the 20-bar floor (§13), ONE above the
  40-trade floor: one `no_minutes` drop there leaves exactly 40, which still decides, and two drops read INCONCLUSIVE (none of the 20 empty
  pairs sits in a check set, §12); any other level
  decides on the 20 + 44 (20 + 41 records). **PASS:** the chosen level's feasible share on the check ≥ 50% AND ≥ the random-level control's feasible share + 15
  points AND hit-or-ballpark ≥ 70% of the check's bracketed trades AND ≥ the random-level control's hit-or-ballpark + 15 points. Every
  share is printed with its 95% binomial interval (on 64 trades a 50% share carries ±12 points, on the 44 undated ±15 — the interval is
  part of the readout, not a footnote). **The fill the chain carries forward:** the chosen level's price where it is feasible on that
  trade; otherwise the registered fill (ORH5 where it filled, the open of lo for undated), flagged `fill_fallback`, counted (§4).
  **Falsifier:** no level ≥ 50% feasible → his entry is not a level crossing we model (anticipation inside the base, a limit in the
  range); the 8 dated + 1 undated held before 09:35 already falsify L1 for those nine and are listed. Between the falsifier and PASS:
  INCONCLUSIVE.
- **Disclosed, seen:** the holdings replay printed L1's fill minute against the panel clock for all 262 dated buys in the window (47 fills
  contradict the clock, by setup; the F5 section). L1's bracket test on dated 2021-22 is therefore a re-read, reported beside; L2–L6 and
  every undated trade are unread.

## 7. STOP — which levels he held THROUGH (a level he held through was not his stop)

**7a. What the panel observes.** He held the name with certainty on every session before the exit window's first session, and on the first
session itself up to the last frame's clock. A level price traded through on such a session was held through.

**7b. Candidate levels (eight) × two variants, fixed.** S1 the buy day's low up to the fill minute (the registered stop; dated at the ORH5
fill, undated at ENTER's inferred minute, else the day's low) · S2 the buy day's full low · S3 the prior session's low · S4 one ADR20 below
the fill · S5 the breakout level (dated: the pivot; undated: the prior-20-session high) · S6 the base low (dated: the lowest low of the
candidate's base; undated: the lowest low of the prior 20 sessions) · S7 the 10-day average · S8 two ADR20 below the fill (control) · and
the 50-day average (control). **"His stop" is chosen among S1–S7:** S8 and the 50-day are controls, read in the table and in the ordering
but never his stop; a level whose median width is not below the fill (S5 on an undated buy inside its base, say) is not choosable either. **Variant T** = an intraday touch (the session's low ≤ the level); **variant C** = a close below it. **S2 is
tested from session 1** (on the buy day the session's low IS the full low, so a day-0 touch is true by definition). A touch on the buy day
after the fill minute counts under T when a later frame that day shows him holding (minutes). **A close below a level on `exit_lo` counts
as held through only if a frame after 16:00 ET that day shows the name.**
**Held-through rate.** H_cond(level, variant) = (trades where the level was traded through on a session he certainly held) ÷ (trades
where it was traded through on any session ≤ `exit_hi`); H_all = the same numerator ÷ all trades. Both printed.
**His stop ≈ the tightest level with H_cond ≤ 10%.** Re-buys (§2's definition, 564) stay in H and are also printed apart; a re-buy whose
earlier entry's exit-window last close sat below that entry's INFERRED fill (the chain's: the chosen level where feasible, else the registered
fill) = a re-buy after a loss — **that flag reads the earlier trade's exit, so for 2021-22 trades it is computed only in `--check`; for the 2020
fit it is computed in the fit (a 2020 re-buy's earlier entry exited in or before 2020).**

**7c. Risk under a close-based stop — stated now, before any run (R is not bounded below).** The position is sized on the LEVEL's
distance as if it were an intraday stop: risk 1% of equity ÷ (fill − level) shares, the 30% cap, the per-stock limit, no margin (the
holdings `cap_30`). The exit is booked at the ACTUAL exit price — the next session's open after the close below (variant C), the level
itself (variant T) or the gap open when price opened through it — so the realised loss can exceed 1R and 1% of equity; the account
accepts it (the frozen `simulate` books legs at their dated prices and already carries gap stop-outs). Printed per variant: the
realised-R distribution of stop-outs (worst, 5th percentile, share beyond −1.5R and −2R), the largest single-trade loss as % of equity,
and the account's max drawdown. **No "too wide, skip" rule is inferred** — the panel cannot show a trade he skipped — so every level is
sized as above; the registered one-ADR20 skip is reported beside as the holdings replay had it. **Beside: a same-size variant** (shares
fixed by S1's width whatever level is used — the "stop that keeps them at the same size" the exits study named untested), flagged as risk
above 1% per trade.

- **Fit set:** dated 2020 (149: 117 filled + the 32 close-fill proxies, flickers included) + exact-day undated 2020 (304, flickers
  included). **Check set, what decides:** the exact-day undated buys of 2021-22 (226, flickers included; 145 non-flicker beside) ALONE, on
  EVERY level and variant. **The dated 2021-22 (111 after §2b) are printed BESIDE on every level and variant, never deciding (re-check N1):**
  the EXIT fit (§8) walks all 111 under the CHOSEN stop before `--check` and writes each one's stop price and per-day R at the close
  (`exit_fit_trades.tsv`, `exit_fit_days.tsv.gz`; X7 ≤ −1 = a close under the stop), so their held-through rate under the chosen level is
  readable before the check. The beside column still marks which (level, variant) the exits study left unread there (S2, S4, S6, S8, the
  50-day, and variant T of S2–S8; S1-T is READ: `our_status == stop` in the exits study's 2021-22 rows is the low-of-day stop touched, 20
  of 24 early exits, 11 on day 0).
  **H's denominator is bounded to sessions ≤ exit_hi** (a touch after he sold is not evidence; counting it would deflate H on the wide
  levels toward "rarely held through"), and **a level needs ≥ 20 trades traded through on the fit set to be eligible as "his stop"** (a
  level touched on 3 trades cannot win on 0 of 3).
  **PASS:** the level chosen on the fit keeps H_cond ≤ 15% on the undated 226 (5 points of slack), and the ordering of the eight levels by H
  on the undated 226 is preserved (Spearman ≥ 0.7). The dated 111 enter neither test (re-check N1; check M2's combining rule is withdrawn).
  **Falsifier:** every level has H_cond > 30% on the undated 226 → his stop is not a fixed price level (time, discretion, a mental stop wider
  than any of these); the report then says which variant and which level come closest. Between them: INCONCLUSIVE.
- **Disclosed, seen (2020 fit AND 2021-22 check AND the 63 beside — all dated):** the exits study's description files carry, per dated
  trade in every year, the FIRST CLOSE below the breakout level (S5-C), below the prior session's low (S3-C as a rolling marker), below
  the 10-day (S7-C) and the 20-day, the stall, the gap-down day, and the registered S1 stop's outcome (`our_status`; our stop closed 43 of
  205 filled trades before his window, 25 on day 0; in 2021-22, 20 of 24 early exits were our stop, 11 on day 0). So on DATED 2021-22
  trades S1 (both variants — our stop is a touch), S3-C, S5-C and S7-C are re-reads; the other levels there were walked by this
  registration's own EXIT fit under the chosen stop (N1). Every dated 2021-22 reading is beside, never deciding. His side on the
  undated trades was never joined to a bar, but some of their bars were walked inside dated trades' paths (§10).

## 8. EXIT — a per-day hold-or-sell rule learned from the bar state

**8a. What the panel observes.** The last share left inside [exit_lo, exit_hi] (one session wide on 183 of the 264 dated in the window; 1,120
of 1,848 overall). Partials are invisible. He held with certainty through every session before exit_lo.

**8b. Features per held session j ≥ 0 (ten, fixed; ADR20 units):** X1 close vs SMA10 · X2 close vs SMA20 · X3 red close (close < prior close)
· X4 close below the prior session's low · X5 sessions held (0 on the buy day) · X6 the open gap vs the prior close · X7 R so far at the close (under the
chain's fill and stop; the registered ones if STOP did not pass) · X8 drawdown from the max R reached (in R) · X9 QQQ red day · X10 the
day's range. **Model families (two, fixed):** (i) a **decision list** of at most 3 rules "sell at this close if (cond) [and (cond)]",
thresholds from the grid, each with its direction fixed: X1, X2 ≤ 0 or ≤ −0.5 (a close below the average, or half an ADR20 below it); X7
≥ 0, 1, 2 or 3 (a profit line) and X7 ≤ 0 (at or under water); X8 ≥ 1 or ≥ 2 (gave back that many R from the best); X5 ≥ 3, 5 or 10; X3,
X4, X9 true; (ii) a **logistic hazard** on X1–X10, no interactions, L2 at λ = 1 on standardised features, fit by the interval-censored
likelihood — the probability the sale fell in [exit_lo, exit_hi] is S(exit_lo − 1) − S(exit_hi) with S(k) = Π(1 − h_j), still-held
trades contribute S(last). **Selection within family:** the decision list by hit rate (its predicted sell session falls inside the
window), the hazard by likelihood. **Choosing between the two families:** both are fit on every fit trade EXCEPT those bought
2020-07-01..12-31 and compared on hit rate on those held-out 2020-07-01..12-31 trades; the family with the higher held-out hit rate wins
(ties → the decision list, fewer parameters) and is then refit on the whole fit set. **The hazard's sell day is its predicted MEDIAN
exit: the first session j where the cumulative sale probability 1 − S(j) reaches 0.5** (a per-day hazard on a 3–5-session hold runs near
0.2–0.3 and would never cross 0.5 on its own — that reading would never sell). **The hit rate is scored only on trades whose exit window
is ≤ 20 sessions wide** (a 2017 window hundreds of sessions wide is a hit for any rule; the likelihood keeps every trade, the hit rate
does not). **Data holes:** a trade whose bars stop at a hole BEFORE exit_lo is read as still held at its last bar (it contributes S(last))
and leaves the hit rate; one whose window a hole cuts keeps its rows in the likelihood and leaves the hit rate — both counted. The family
choice is the SAME held-out rule for the undated-only fit beside. Nothing is added to either family after this line.

**8c. Accounts and the bar (the exits study's measure, kept for comparability).** Three accounts through the frozen `simulate` at
`cap_30`: **ours** = the speed trail under the chain's fill and stop (§4; the frozen arm takes the stop as a price fixed on the buy day); **chosen**
= the chosen rule under the chain's fill and stop, the stop followed as a LEVEL day by day (a moving-average stop moves; its buy-day price
sizes the position and sets R); **his** = the panel exit at the close of `exit_hi`, **NO stop** (as in the exits study and the holdings
replay) — the chain's stop sets his position size only. Every account is cut where the speed trail's forward window ends — at a missing session or at the ticker's identity break
(`mark_hole` / `mark_break`). **Recovery share** = (ln chosen − ln ours) ÷ (ln his − ln ours). The registered fill and stop (ORH5 + the low of the
day; undated: the open at lo + one ADR20 — the holdings replay's R9) run the same three accounts beside, so a change in the R unit is
visible, not hidden.

- **Fit set:** every dated deciding trade with a known exit (286 after §2b, all years — every one of them already described, §10) + the
  exact-day undated buys of 2020 (304, flickers included; 1,822 trade-days); a record needs 50 bars before the buy day (§13). **Inside this
  fit the 20 dated 2021-22 in-session brackets (ENTER's dated check set) carry the REGISTERED fill, flagged `fill_checkwin_registered`**, so the
  chosen level's feasibility on them is not computed before `--check` (a different R unit on 20 of the 590 fit trades; the other way — calling
  ENTER's dated-20 line a re-read of this fit's chain — was not taken). In the check every trade carries the chain's rule. **Check set, what decides:** the exact-day undated buys of
  2021-01-04..2022-06-14 (**226**, flickers included, 1,260 trade-days; the 145 non-flicker beside) — the one population whose sell dates
  have never been joined to a bar. **Beside, to separate population shift from rule quality:** a second fit on the undated 2020 set
  ALONE, checked on the same 226; if the dated-inclusive fit fails and the undated-only fit passes, the dated trades are a different exit
  regime and it is named.
- **PASS:** recovery ≥ 0.25 on the check under the chain's fill and stop. **Falsifier:** recovery < 0.25 → his exit is not in this family
  either, and the hit rate against the trivial rules (§3) says whether the rule at least SEES his sell day (a high hit rate with a low
  recovery means the money is in the trades, not the days).
- **VOID when his final ÷ ours final < 1.25 on the check (or ≤ 1):** the recovery ratio's denominator is then too small to read (or zero
  or negative; the no-event set is where his shorts most likely sit, and a short read as a long sells "badly" under panel exits — the
  exits study already saw his 2022 exits under every rule). Then the readout is the hit rate against the trivial rules only, SELECT's
  short-cluster flag (§5b) is consulted, and the verdict is `no bar` — never a PASS or FAIL on recovery. **A VOID carries the registered
  speed trail into the sealed test, as a FAIL does.**
- **Flicker share, stated:** fit 35% flickers (dated 32%, undated 38%), check 36% — no real difference in flicker rate. The difference
  is name confirmation: 48% of the fit set (the 286 dated) is name-confirmed by our event firing on that name that day, and none of the
  check set is. A recovery that fails WITH flickers and passes on the 145 non-flicker trades is read as a misread problem, not a rule
  problem — the non-flicker line is beside for exactly this.
- **Disclosed, seen:** for every DATED trade in every year the exits study printed the markers (first close below the 10- / 20- / 5-day, the
  first red close, the first close below the prior low, +1R / +2R / +3R, the stall, the gap-down, a big up day) before / within / after his
  window, the six rules' per-trade R, the panel-exit account and the top tail by name (2020: APT, FSLY, W; 2021: TLRY, MARA, LCID, RIOT,
  AMC, BB). The holdings replay printed our account on the deciding AND undated buys COMBINED (`02_replay.txt` l.174: open fill, one-ADR20
  stop; final 20.53; by year 2021 +86.3%, 2022 +43.9%) and its `trades.tsv.gz` holds their per-trade rows under our rules, incl. each
  undated trade's stop status under the one-ADR20 stop (≈ S4) (this registration opened its header only). His side on the undated buys —
  the panel's sell window joined to any bar — has not been read; their bars partly have (§10). No per-day model has been fit on any
  population.

## 9. WHY — his words joined to the trades the panel dates (a cross-check, never a source)

- **The join rule (fixed; the one run for the counts in §2):** a phrase hit (the pinned alternation of §2, parsed by `qmlib.parse_vtt`) at
  caption time t in video v; a ticker mention in v within 30 s of t (`stream_moments.tsv`); the ticker has a panel exit window with the
  stream's session s0 (the last session ≤ the upload date) in [exit_lo − 1, exit_hi + 2]. **The panel window is the precision device**
  (the census's event requirement had that role); a phrase whose 30-second window names two qualifying tickers is ambiguous and dropped
  (150). Phrase classes: STOPPED (*"stopped out", "got stopped", "stopped me out"*) → routed to STOP: the exit session's bar says which of
  S1–S8 was hit, and the lowest level touched that session is his stated stop's proxy; SOLD (*"i sold", "sold it / all / everything /
  out", "i closed it"*) → EXIT: the exit session's X1–X10 (the median per feature and the shares red / below the prior low, printed by
  `--why-rates`); PARTIAL (*"sold a third / half / some", "took partials / profits",
  "trimmed"*) → the only evidence of partials the panel cannot show: counted per trade, with the caption day's R.
- **GATE: 20 joins hand-read (the caption line and, where it exists, the frame) BEFORE any rate is quoted.** Drawn stratified by class
  (8 STOPPED, 8 SOLD, 4 PARTIAL), seed 1024, **from 2020 only** — a 2021-22 join is read only after the §8 check has run. A hand-read
  precision < 70% → no rate is quoted; the joins are listed. ≥ 70% → the rates per class, and the level-hit distribution for STOPPED.
- **Why it cannot decide anything:** 786 joins reach 380 of 1,848 exits (21%); a quarter of 2021's streams and half of 2022's carry no
  caption track at all (44 of 189, 35 of 64 — the census); the caption names the stock he is TALKING about, not always the one on screen
  (the census: 45% of named stocks were not the chart on screen).

## 10. THE FIT / CHECK SPLIT — what was seen per decision type, and what each check rests on

| decision | seen before this registration (where) | clean check (decides) | re-reads (beside) |
|---|---|---|---|
| SELECT | nothing on the no-event names' bar states up to their buy days; the timeline counted them; the holdings replay walked them under OUR rules as an aggregate; the event dates 1–5 sessions after each window were counted (below) | 2021-01-04..2022-06-14 exact-day non-flicker (145 + up to 15, after the pool floor) vs the pool | the 290 dated (positive control); the 2017 / 2019 / 2023 buys; the 47 other-level buys — the 32 outside 2021-22 at the fit, the 15 of 2021 in `--check` (§5b, N3) |
| ENTER | L1 (ORH5) vs the panel clock for all 262 dated in the window (the F5 section, 47 contradictions) | 2021-22 in-session brackets: L2–L6 on dated (20), every level on undated (44; 63 with flickers); L1 chosen → the undated 44 alone | L1 on dated 2021-22; every pre-market-flat bracket |
| STOP | S1's outcome (touch AND close — our stop is a touch), S3-C / S5-C / S7-C and the stall for every dated trade, every year (the exits study's description files) | undated exact-day 2021-22 (226) ALONE, on every level and variant (§7) | dated 2021-22 (111) on every level and variant: S1 (T and C), S3-C, S5-C, S7-C re-reads of the exits study; the rest walked under the chosen stop by the EXIT fit (N1) |
| EXIT | every dated trade's exit markers and the six rules' R in 2020, 2021-22, 2017-19 + 2023 + wider (the 63 beside) — no dated year is unseen | undated exact-day 2021-22 (226), his side never joined to a bar | the dated 2021-22 under the chosen rule — **in-sample** (they are in the EXIT fit set; their 20 in-session brackets carry the registered fill there, §8), never deciding; the undated-2020-only fit |
| WHY | nothing (no exit-phrase census existed) | 20 hand-read 2020 joins gate the rate; 2021-22 joins read after the §8 check | — |

- **2021-22 is a clean check for SELECT, for the unread parts of ENTER and for STOP on the undated buys; it is NOT a clean check for STOP or
  EXIT on dated trades** (STOP: the EXIT fit walks them under the chosen stop, N1), and
  no other dated year is either (the 63 beside were described too). The EXIT check therefore moves to the population never joined to his
  sell window — the no-event buys with an exact buy day — with the time split kept inside it (fit 2020, check 2021-22) and a
  population-shift read beside.
- **The STOP / EXIT check's bars were partly walked.** 69 of the 280 check buys (40 of the 177 non-flicker) — after §2b 65 of the 226 (38
  of the 145) — have their buy day inside the 121-session path (buy day + 120) of a dated trade on the same name, which the exits study
  walked for markers and per-rule R. Several are named top-tail trades: MARA 2021-02-18 / 02-25 / 03-04 after dated MARA 02-08; BB
  2021-06-14 after BB 06-03; AMC 2021-06-09 after AMC 06-01; LCID 2021-12-17 / 12-28 after LCID 10-25; RIOT 2021-04-12 inside RIOT
  02-08's path. **The STOP and EXIT verdicts are printed on all 226 and on the 161 untouched beside; a PASS / FAIL that flips between them
  is reported as such.** (On the 2020 fit side 116 of the 335 sit in a dated path; that is fit material and needs nothing.)
- **The forward event count (header):** of the 77 buys classed "an event 1–5 sessions after, none 1–5 before", 39 are fit 2020, 35 check
  2021-22, 3 other years; of the 126 with any event 1–5 sessions after, 70 / 48 / 8; among the 177 one-session non-flicker check buys, 40.
  No feature, rule or placement reads it.
- **The EXIT grid's origin, disclosed:** the decision-list grid (the red close, the close below the prior low, sessions 3 / 5 / 10) was
  shaped with the exits study's dated results — including 2021-22 — in view. It decides only on the undated check set, which the exits
  study never joined to his sell window.
- **2025-26 (sealed) holds no panel stream** (the streams end 2023-12-15), so it cannot test REPRODUCTION. It is the one-shot COMBINED test of
  the inferred rule set as a STRATEGY (§12).

## 11. Expectations, written now (a miss changes no rule; each is a guess to be scored, not a target)

- **SELECT:** most no-event buys have a prior close at or within 0.5 ADR20 of a 20-day high with a prior 20-session move above the pool
  median (he buys strength our trendline does not draw — short bases, no straight line to break); a quarter open with a gap under our
  9% / 3× floor; lift 2–3×, recall near 50%. The condition set also fires on more than half of the 290. The fit beats all 20 planted runs.
- **ENTER:** L1 feasible on about half of the in-session brackets; L2 (the prior high) on a quarter; L3 (the base high) rarely — the 77
  "our line broke after his buy" cases say he is in before our level; L4 never (by construction); L5 on a few gap-down days only.
  Hit-or-ballpark above 70% for the chosen level, and the random-level control near 40–50%.
- **STOP:** S1 and S3 held through on more than 30% (the exits study's "losses beyond 1R"); S6 (the base low) and S4 (one ADR20) rarely;
  S7-C held through on the slow half. Realised stop-outs beyond −1.5R on 10–20% of stop-outs under variant C.
- **EXIT:** recovery between 0.10 and 0.40; the hazard beats the decision list on likelihood, the decision list on held-out hit rate;
  flickers are the hardest trade-days; the undated-only fit does no worse than the dated-inclusive one; his ÷ ours on the check above 1.25
  (not VOID).
- **WHY:** STOPPED joins hit S3 or S1 more than any other level; PARTIAL phrases confirm a partial on at least 10 dated trades the panel
  shows as one hold.

## 12. DATA GATE (STEP 0), the point-in-time declarations, and the sealed one-shot

- **Era A = `cb702_pre_v2`** (2017-21 rebuilt; passing S0, G1–G7, G9 at the holdings pins; export 2016-01-04..2022-06-30, 1,635 sessions).
  **Era B = `cb702`** (export 2021-09-27 onward; every row dated after 2024-12-31 dropped at read and asserted; 2025-26 never opened). Era by
  buy day: ≤ 2022-03-31 era A, ≥ 2022-04-01 era B (the holdings R10). The holdings module's loaders (`load_daily_subset`, `load_done`,
  `unify_calendars`, `stitched_closes`) are imported read-only at the pinned sha; nothing in them is edited.
- **G8 (this read's own trade list):** before any number the module writes its `--kind r1` files per era and runs `trade_impact.py`; era A
  must read entered-after-cutoff 0 and holds-past-last-bar 0 (asserted; else STOP).
- **Minutes (the gate that bites).** The deciding entries are covered (290 of 294 on E; DRYS 2017-02-01, DDOG 2019-11-13, FUBO 2021-01-05,
  QS 2021-02-12 have no minute file anywhere and are not on the fetch list; they stay `no_minutes`). **Before the fetch, on the four pinned
  trees:** of the 427 one-session no-event buys only 32 had minute bars on the buy day (missing 395: 2020 188, 2021 141, 2019 35, 2022 25,
  2023 5, 2017 1); of their 273 one-session flicker siblings 17; the 206 multi-session windows hold 717 window sessions with 22 covered;
  ENTER scorable on the four pinned trees alone 32 dated + 7 undated on the fit, 20 dated + 4 undated on the check. **The fetch list**
  `/Users/alvinfung/apollo_data/cb702/minutes_rev_1024/fetch_list.psv` — **1,322 distinct ticker|date pairs** (sha256 `4191485f…`; no
  header, sorted by date, latest 2023-12-14, nothing after 2024-12-31; by kind: one-session non-flicker 394, one-session flicker 235,
  window sessions 693; by year: 2017 17, 2019 139, 2020 615, 2021 368, 2022 131, 2023 52; bar symbol = `sym_a` on era-A dates, the panel
  symbol on era-B dates). It lists the timeline's sets before §2b (the funds the type gate removes are on it; the re-admitted
  never-a-candidate stocks are not — they are SELECT-only). **The fetch RAN on 2026-10-24 with the operator's permission** (the same Alpaca
  fetcher as 10-23 / 10-24, into `cb702/minutes_rev_1024/`, 508 date files, pinned by its `_done.psv` as `done_REV`; the pinned trees
  untouched): **1,302 ok, 20 empty (fetched, no bars at the source), 0 failed, 0 still missing, 0 rows off the list.** The 20 empty pairs
  abstain `no_minutes`, counted, and are: AXNX 2020-01-02, AXNX 2020-01-03, AXNX 2020-01-06, AXNX 2020-01-07, AXNX 2020-01-08, AXNX
  2020-01-09, AXNX 2020-01-10, CHRD 2020-04-30, FACT 2020-10-16, FACT 2020-11-05, FBR 2019-10-22, FBR 2019-10-23, FBR 2019-11-12, FBR
  2019-11-15, FBR 2019-11-18, HTZ 2020-03-24, HTZ 2020-07-22, SRTA 2019-11-15, U 2020-07-24, XP 2019-11-29 (the dry run names the set each
  sits in). **Coverage with the new tree:** one-session non-flicker 423 of 427; flickers 267 of 273; window sessions 707 of 717; ENTER set
  members with minute bars 32 + 58 (91 with flickers) on the fit, 20 + 44 (63) on the check; after the record floor 32 + 57 / 20 + 41 records
  (§13), so with L1 chosen the deciding undated check set is 41, one above the 40-trade floor (§6). None of the 20 empty pairs sits in a check
  set: 1 is an ENTER fit undated bracket (3 with flickers), 2 are SELECT fit buys, 6 undated fit buys, 10 window sessions.
- **A pair without minute bars at the run (the 20 empty ones; a record dropped by the floor is counted apart) degrades ENTER as follows,
  fixed now:** a bracketed trade with no minute bars is scored neither HIT nor MISS — a day-range ballpark cannot pass the random-level
  control, which is drawn from the same day — it is flagged `no_minutes`, counted and listed. ENTER is then scored on the bracketed trades
  that have minutes. **Fewer than 40 scorable DECIDING check trades → ENTER reads INCONCLUSIVE** (on 24 trades a 50% share carries ±20
  points), and the chain carries the registered fill, as on a FAIL. STOP's S1 becomes S2 for any undated trade without minutes (flagged);
  EXIT is unaffected (daily bars). Nothing abstains silently.
- **Point in time:** era A keyed by today's symbol with the timeline's alias map (`sym_a`); era B point-in-time; the pool's $5 / $10M / 130-
  session filter uses the session BEFORE the buy day and the 20 sessions ending there — the $5 test on the RAW close, the $10M test on the
  export's close × volume (split-invariant, §3); SMA / ADR / range features use bars ≤ the prior session (SELECT) or ≤ the session scored
  (STOP / EXIT); the universe percentiles use that day's pool only; the security type is as of 2026-10-16 (not point in time, §1i).
  **SELECT's era:** era A through 2022-06-30 (its export's last session), so a pick's features and its pool sit on one export (§3); ENTER /
  STOP / EXIT use the R10 era by buy day (≤ 2022-03-31 A, else B). The panel fixes every window; nothing after a buy day's open enters SELECT, and nothing
  after `first_clock` enters ENTER.
- **The sealed one-shot (2025-26, after all four stages, ONCE):** the inferred rule set as a strategy under his bar (alpha t ≥ 2 vs QQQ,
  total above QQQ and SPY, Sharpe above QQQ's) through the runner's holdout machinery. **Two branches, both stated now:** SELECT passed →
  the condition set scans the daily universe (the pool filter) and ENTER / STOP / EXIT act on what it finds; SELECT did not pass → ENTER /
  STOP / EXIT act on our detector's own `tl` and EP events. Either way the entry level, stop level and exit rule are the inferred ones
  where their check passed and the registered ones where it did not (§4). **Every branch that runs on a fallback is labelled in the sealed
  readout: `words-based` (a registered entry, stop or exit written from his words) or `our-detector` (our `tl` / EP events in place of
  SELECT).**

## 13. Files, the module, its guards, the readings chosen

- **Inputs (pinned at the dry run; the holdings pins re-checked at start):** the timeline's `entries.tsv` / `exits.tsv` / `snapshots.tsv`
  (holdings pins `6a0dda2d…` / `1ed76a28…` / `a8987fce…`); the exports, calendars, raw closes, candidates (`ticker / E / K / split /
  pivot / adr20 / base_id` only), EP events, guards, fetch logs at the holdings pins; `small_pulls.psv` and `cb702_sic.psv`;
  `stream_moments.tsv`, `video_status.tsv`, the caption files (`subs/*.vtt`, one sha over the sorted list) and `qmlib.py`; the fetch list
  (`fetch_list.psv`, sha256 `4191485f…`) and the new minute folder's `_done.psv` (`done_REV`, fetched 2026-10-24).
- **Code:** `scripts/probes/_705_reverse_1024/01_rev.py` (the folder that already holds the pre-freeze recount in `verify/`) — stages
  `--dry-run` (populations asserted against §2 and §2b, the clock columns written for every row, the caption chain printed, minute
  coverage, pins), `--select-fit` (incl. the planted-name control), `--enter-fit`, `--stop-fit`, `--exit-fit` (each writes once; each
  prints its CHOSEN line), `--pins`, `--check` (every stage's check ONCE, then WHY's 2020 hand-read sample), `--why-rates` (after the hand
  read is filed); `test_01_rev.py` (the interval-censored likelihood on a hand-computed world, the bracket feasibility and ballpark on
  synthetic minutes incl. a pre-market-flat bracket, the random-level control, the held-through counter on a synthetic frame sequence,
  the pool filter, the type gate, the placement rule, the join rule, the marker and CHOSEN parsing). The holdings module is imported at
  `4275d72f…` (refused on drift); the exits-study module is NOT imported (its pinned file is not on disk — its freeze note). The folder holds
  `01_rev.py` and `test_01_rev.py`; the dry run (`01_rev_dryrun.txt`, pinned as `dryrun_printout`) reproduces every count of §2 / §2b / §6 /
  §8 / §10 / §12 and the record floors below, and the fit stages refuse to run unless it ends `DRY RUN COMPLETE`.
- **Record floors (registered 2026-10-24):** a STOP / EXIT record and a SELECT pick record need 50 bars before the buy day (SMA50, the 50-day
  control); an ENTER record needs 20 (ADR20, the prior-20 high and low — nothing in ENTER reads further back; a STOP / EXIT record of the same
  trade still needs 50). Before the floor a record needs the era's export to hold the ticker and a bar on the buy day. The record builder keeps
  dated 290 → 288, undated fit 304 → 282, undated check 226 → 212, windows 187 → 175, ENTER fit 32 + 59 → 32 + 57, check 20 + 44 → 20 + 41,
  EXIT dated 286 → 284 (the dry run asserts these and prints the drop reasons; the three undated check brackets lost have fewer than 20 bars
  before the buy day).
- **Guards:** (1) the line-anchored freeze lock — `--check` refuses unless every pin `--pins` prints (incl. `doc_body`, the sha256 of this
  file's bytes above the one line that is exactly the freeze marker) sits under the marker, exactly one each of `CHOSEN SELECT: …`,
  `CHOSEN ENTER: …`, `CHOSEN STOP: …`, `CHOSEN EXIT: …` stands above it (parsed by its stage key, never by position), every fit printout
  exists and the check printout does not; (2) **the module is COPIED beside the pins before any post-check edit** (the exits study's
  lesson: its pinned module was lost); (3) populations asserted against §2 / §2b before any bar is opened, and no fit stage runs unless the dry run's printout ends `DRY RUN
  COMPLETE` (a STOPPED dry run also writes the file; it is pinned as `dryrun_printout`); (4) G8 before numbers; (5) a fit stage opens no bar
  after the buy day of any trade outside ITS OWN registered fit set — the fit set's composition is asserted against the registration at the
  start of the stage, and each record carries its own horizon: unbounded inside the fit set (the dated 2021-22 trades in the EXIT fit, §10),
  the buy day only outside it; an undated 2021-22 buy is refused by every fit stage whatever the set says (the first build keyed the guard on
  a DATE and the exit fit stopped on its first dated 2021 trade — check H1); the four fit sets, as the dry run asserts them on the real buys:
  SELECT 200, ENTER 91, STOP 453, EXIT 590, with 0 violations of the registered predicates; (6) a crash writes a STOPPED file; (7) every printout
  is written once, and **an append-only ledger (`01_rev_ledger.tsv`: stage, printout path, sha256, time) records each printout as it is
  written; `--check` verifies every ledger row against the file on disk and refuses on a missing or changed printout** (deleting a printout
  to re-run a stage is caught); (8) every bracket frame of a fit / check trade has |raw clock − fitted clock| ≤ 2 minutes (asserted; today
  the 21 misread clocks are all 2019, none in 2020-22); (9) the module never opens a row of `replay/trades.tsv.gz`, `his_exits/describe_rows_*`
  or `his_exits/trades_*` for an undated name (asserted by eid).
- **Readings chosen (B = this registration's choice):** R1 flickers: excluded from SELECT's deciding sets (a one-stream hold is a day
  trade or a misread, not a position), included in STOP / EXIT (they hold the quick exits the dated fit set also carries) with the
  non-flicker subset beside; in ENTER the non-flicker brackets decide and the flicker brackets are beside (§6, §12 — the one exception) (B). R2 the EXIT check is the undated exact-day 2021-22 set, since every dated year is described
  (B). R3 ballpark = inside the bracket's traded range, or within 0.25 ADR20 of it, scored on in-session brackets only and held against
  the random-level control; 0.5 ADR20 unbracketed, beside (B). R4 multi-session windows placed on the latest session meeting the fitted
  condition set, else lo, never fit material (B). R5 the pool = raw close ≥ $5 / 20-session median export close × export volume ≥ $10M
  (split-invariant) / type CS-ADRC-untyped / 130 consecutive sessions, on the session before the buy day (itself adjacent to it), the names
  he did not hold plus his pick; his buys meet the same floor after the record builder (B). R6 "his stop" =
  the tightest level with H_cond ≤ 10% (B). R7 the close-based stop is sized on the level's distance and booked at the actual exit (B;
  §7c). R8 EXIT's ours and chosen accounts run under the chain's fill and stop, his under no stop, the registered ones beside (B). R9
  recovery ≥ 0.25 kept from the exits study for comparability, VOID under a 1.25 his ÷ ours gap (B). R10 WHY's 20 hand reads come from
  2020 only (B). R11 type gate, inverted windows and same-day re-buys out of every fit and check set, in that order (B; §2b). **Readings resolved at the
  module-vs-registration check (2026-10-24, B):** R12 the STOP check decides on the undated 226 alone; the dated 111 are beside on every level
  (§7; revised at the re-check, N1 — the combining rule of check M2 withdrawn). R13 inside the EXIT fit the 20 dated 2021-22 in-session brackets carry the registered fill
  (§8). R14 with L1 chosen the ENTER check decides on the undated 44 alone (§6). R15 record floors 50 (STOP / EXIT / SELECT picks) and 20
  (ENTER) bars before the buy day (§13). R16 "his stop" is chosen among S1–S7 with a positive median width; S8 and the 50-day are controls
  (§7b). R17 the trivial exits count the buy day as session 1 and read the first red close from session 2 (§3). R18 L1 / L6 read
  `no_level_yet` on a bracket that closes before 09:35 / 10:30; an EP row's L3 is the prior-20 high (§6b). R19 the 2023 SELECT beside buys
  are listed, not scored (§5b). R20 a trade whose bars stop at a hole before exit_lo is still-held for the likelihood and out of the hit
  rate (§8b). R21 the chosen account follows a moving-average stop day by day; ours and his are cut at the identity break with it (§8c). **Resolved at
  the re-check (2026-10-24, B):** R22 the buy-day stop check is computed against the chain's ACTUAL stop for ours and chosen alike, every
  time the chain is applied; a close fill (the dated close-fill proxy) has nothing left in the day and is never a buy-day stop (N2).
- **Outputs:** `01_rev_dryrun.txt`, `01_rev_{select,enter,stop,exit}_fit.txt`, `01_rev_check.txt`, `01_rev_why.txt`, `01_rev_ledger.tsv`
  in the module's folder; per-trade and per-day TSVs under `apollo_data/cb702/qm_streams/holdings_1024/reverse/`.

## 14. What this does not answer

- **His actual fills, sizes and partials** — the panel shows a name; a level is inferred, a size never.
- **The side of a position** — a short reads as a long; the no-event set is where his shorts most likely sit.
- **Trades bought and sold between two streams** — invisible; every rule here is for trades he held to at least one frame.
- **Why he chose one qualifying name over another beyond these features** — themes, news, the chart by eye.
- **His fund and ETF trades** — the type gate removes them (55 of the 633, 30 of the 177 SELECT check buys); a rule for those is not asked.
- **Anything about 2024 (no streams) or 2025-26 beyond the one sealed strategy test**; 2018 holds one stream, 2023 twelve.
- **Whether a rule that reproduces his decisions also reproduces his returns** — the sealed test asks it once; this registration asks
  only whether the decisions are recoverable.

## 15. Design questions — DECIDED 2026-10-24 (main loop; no money, not THE LINE)

1. **Flickers in SELECT's deciding set → beside (R1).** Reason: a one-stream hold is a day trade or a misread, not a position; the recall
   is printed both ways.
2. **EXIT's "ours" baseline on undated buys → the chain's inferred fill and stop decides; the registered open fill + one ADR20 (R9) runs
   beside (§8c).** Reason: one R unit across ours / chosen; his account runs with no stop (§8c), the stop sets his size only.
3. **The minute fetch → fetched before the freeze** (2026-10-24, with his permission: 1,302 of the 1,322 pairs, 20 empty at the source and
   listed, §12). Reason: a day-range ballpark cannot see a half-hour bracket; a pair still without bars degrades ENTER as fixed in §12.
4. **The ballpark tolerance → 0.25 ADR20 beyond the bracket range (0.5 unbracketed, beside), kept and fixed now.** Reason: a quarter of a
   typical day's range, fixed before any run; it counts only together with the random-level control and on in-session brackets (§6c).
5. **One combined sealed test, after all four checks, both branches stated (§12).** Reason: a per-stage holdout would spend the sealed
   years four times.
6. **No time-based stop hypothesis in this registration.** Reason: EXIT's X5 (sessions held) already carries time; a separate stop family
   is a new registration.

## 16. Revisions before the freeze (2026-10-24)

Four pre-freeze reviews: a design review (`review`), an independent recount (`recount`, `verify/recount_prefreeze.txt`), a
module-vs-registration check of the built module (`check`, 2026-10-24, verdict BLOCK: H1, H2, M1–M10, L1–L8 — every one applied below) and
a re-check of the fixed module (`re-check`, 2026-10-24, verdict FIX: all 20 check fixes held; N1–N6 new, every one applied below — the
choices DECIDED 2026-10-24, main loop; no money, not THE LINE).
Every finding was checked against the files before it was applied.

| finding | change |
|---|---|
| review F1 — pre-market flat frames make L4 / L5 pass by construction | §6b: feasibility and HIT scored on in-session brackets only; pre-market-flat brackets beside; L4 never feasible stated; fit 32 + 59, check 20 + 44 (after §2b) |
| review F2 — two bracket definitions; undated clock columns empty | one `panel_clocks()` derivation for all rows, written by the module; §2 now "185 (in session 94, pre-market 91); 135, of which 53 in-session". The "13 dated rows that differ" did not reproduce: the stored dated columns match the derivation on all 264 |
| review F3 — ballpark has no control | §3: random-level control defined exactly (200 seeded minute closes, scored as a level); §6c PASS adds "≥ control's hit-or-ballpark + 15 points" |
| review F4 — buy-day close features are survival-confounded | §5b: every feature on bars to the prior session plus the buy day's open (F14); buy-day F1 / F2 / F11–F13 beside, flagged |
| review F5 — falsifier searched the check set | §5b: falsifier = the CHOSEN set's lift < 2.0; between it and PASS = INCONCLUSIVE; only the chosen set is scored on the check |
| review F6 — ETFs left in; ordinary stocks dropped as "never a candidate"; pool not on raw close | §2b type gate (resolve_type: CS / ADRC / untyped; LAZR override) on his buys and the pool; never-a-candidate stocks re-admitted to SELECT; pool on raw close ≥ $5, $10M, 130 sessions. Counts are mine, not the reviewer's: 55 funds out of the 633 (not 40), 30 of the 177 (not 18); 53 typed stocks + 74 untyped among the never-a-candidates (the reviewer's 180 / 126 did not reproduce) |
| review F7 — check buys inside dated trades' walked paths | §10: 69 of 280 (40 of 177 non-flicker; reviewer's 70 not reproduced), 65 of 226 after §2b; verdict printed on all and on the 161 untouched; guard (9); §8 disclosure corrected (l.174 is the deciding + undated account combined) |
| review F8 — events after the window are forward facts | header disclosure; §10 split (77: 39 / 35 / 3; 126: 70 / 48 / 8) |
| review F9 — 4 million candidates, no search control | §3 / §5b planted-name control (20 runs; beat 19 of 20 or INCONCLUSIVE before the check); threshold direction stated |
| review F10 — his account picked up a stop | §8c: his account = panel exit at the close of exit_hi, no stop; the stop sets size only |
| review F11 — VOID only at his ≤ ours | §8: VOID when his ÷ ours < 1.25; a VOID carries the speed trail into the sealed test |
| review F12 — family choice favoured the decision list | §8b: families compared on held-out 2020-07-01..12-31 hit rate, winner refit; each grid threshold's direction stated |
| review F13 — inverted windows treated as exact | §2b: excluded from every fit and check set, listed |
| review F14 — held-through counting holes; two re-buy definitions | §7b: S2 from session 1; exit_lo close needs a frame after 16:00; H_cond written out; re-buys in H and apart; after-loss flag only in `--check` for 2021-22. Re-buy definition unified on 0–14 calendar days vs the previous NON-INITIAL entry's exit_hi = 564 (reproduced twice); the reviewer's 565 was not reproduced |
| review F15 — the pick left out of its own pool | §5d: pool = names not held plus the pick |
| review F16 — clock misreads not asserted | guard (8); verified: 21 misreads, all 2019 |
| review F17 — CHOSEN lines unkeyed; printouts deletable; counts not yet reproduced | guard (1) keyed CHOSEN lines; guard (7) append-only sha256 ledger; header and §13 say hand-derived until the dry run |
| review F18 — fallbacks unlabelled; dated 2021-22 EXIT called "beside" | §12 fallback labels; §10 dated 2021-22 EXIT relabelled in-sample; the grid's origin disclosed |
| recount F1 / F2 — bracket rule mix; quartiles | in-session rule throughout; dated 53 (32 / 21), median 24, quartiles 15–42, 29 ≤ 30 minutes |
| recount F3 — "stopped out" count | 2,099 |
| recount F4 — caption chain not reproducible | the alternation and parser pinned in §2; figures 4,015 / 477 / 2,261 / 786 / 380 / 88 / 150 (re-run and reproduced) |
| recount F5 — flicker asymmetry | §8 reworded: fit 35% (dated 32%, undated 38%), check 36%; the difference is name confirmation (48% vs 0%; corrected from 49% at check M8 and the re-check, N5) |
| recount F6 — same-day re-buys in the undated sets | §2b: dropped from every set, printed with them beside |
| recount F7 — inverted windows called exact | as review F13 |
| recount F8 — fetch size omitted the flickers | §12: 1,322 pairs, with the list's path, sha and counts |
| recount F9 — era A sessions | 1,635 |
| recount F10 — dated window > 10 names | 47 |
| recount F11 — buy year basis | buy day of an undated entry = window start: 6 / 69 / 301 / 196 / 45 / 16; era A 597 / B 36 |
| recount F12 — undated bracket median | 35.5 for the 108; 34 is the 175 with flickers |
| recount F13 — priority order unstated | §2 states the order and the 126 without priority |
| check H1 — the exit fit's forward-bar guard was a DATE limit (2020-12-31) attached to every record, so the first forward bar of any dated 2021-22 fit trade STOPPED the fit | guard (5) rebuilt: the fit set's composition is asserted against the registration at the start of each stage, and each record carries its own horizon (unbounded inside the stage's fit set, the buy day outside it; an undated 2021-22 buy refused by every fit stage); an end-to-end runner test runs the EXIT fit on a synthetic world with a dated 2021 trade and refuses a smuggled undated 2021 one |
| check H2 — the $10M floor read the RAW close × the export's split-ADJUSTED volume, not split-invariant (TSLA 15× too high, CODX 30× too low in 2020). The check's "10 of 183 fit picks and 3 of 137 check picks" counted flips of the $10M test alone; after the $5 and history tests the reproduced NET effect is smaller: dollar-volume losses 11 → 6 on the fit set (131 → 136 admitted), 6 → 4 on the check (119 → 121), flickers 7 → 4 / 8 → 4 | §3 / R5 / §12: the $10M test = the export's close × the export's volume (one adjusted basis, the U rule's own computation); the $5 test stays on the raw close; one floor function for the fit and the dry run; the step-5 and record counts re-derived (§2b, §13) |
| check M1 — with L1 chosen, an already-read level decided the ENTER check | §6 / §10: L1 chosen → the undated 44 decide alone, the dated 20's L1 share printed beside (R14) |
| check M2 — the STOP check's dated-unread reading was printed but never entered the verdict; no combining rule | §7: the chosen level must hold H_cond ≤ 15% on the undated 226 and, where unread there, on the dated 111; the ordering and the falsifier on the undated (R12) — **superseded at the re-check (N1): the undated 226 decide alone** |
| check M3 — R1 said flickers are in ENTER; §6 / §12 and the module decide on the non-flicker brackets | R1 given its ENTER exception; §6 states it |
| check M4 — the exit fit ran the chosen level on the 20 dated 2021-22 in-session brackets (ENTER's dated check set), revealing its feasibility before `--check` | §8 / §10: those 20 carry the REGISTERED fill inside the exit fit, flagged `fill_checkwin_registered` (R13; the alternative, a re-read of the exit fit's chain, was not taken) |
| check M5 — a window session (or any non-fit day) had no pool, so F15 / F16 defaulted to 0.5 | §5b / §5c: every day a pick is read on gets its own same-day pool (returns only) for F15 / F16; a day without rows is NaN + `pool_empty`, counted, never a default |
| check M6 — the fit pool was built on the fit days PLUS flicker-only days; the check's on its buys' days only | §5b: the grid and every pool rate come from the fit BUYS' days only; the check mirrors it; flicker days get same-day pools for F15 / F16 alone |
| check M7 — the 50-bar record floor was unregistered, and the dry run's step-5 path differed from the fit's (no record drops, no adjacency) | §2b step 5 / §13: floors registered (50 STOP / EXIT / SELECT picks, 20 ENTER — R15), one floor path (record builder, then the pool floor incl. adjacency), the resulting counts carried in the doc and asserted by the dry run |
| check M8 — the doc contradicted the pins and the module (49% vs 48%; "NOT fetched" vs `done_REV` pinned; "no 01_rev.py yet"); none of the builder's readings was written down | 48%; §0 / §1h / §12 / §15 rewritten to the fetched state (1,302 ok, 20 empty listed); §13 the module and its dry run; the ctx rule (§2), pooled pool rates and the 130 consecutive sessions (§3), the planted draw and the random-minute rule (§3), F3 / F11 / F13 / F15 / F16 (§5b), the union cap with its tie order (§5b), SELECT's era (§12), the record floors and step-5 counts (§2b, §13) |
| check M9 — a hole before exit_lo left the window past the data: P negative, floored, one trade dominating the likelihood | §8b: still-held at the last bar for the likelihood, out of the hit rate, counted (R20) |
| check M10 — the chain froze the chosen stop at its buy-day price, so an S7 / 50-day stop never moved in the EXIT walks | §8c: the chosen account follows the level day by day; the buy-day price sizes and sets R (R21) |
| check L1 — S8 (a control) and a level at or above the fill could be chosen as his stop | §7b: chosen among S1–S7, positive median width (R16) |
| check L2 — ours was cut at identity breaks, chosen and his were not | §8c: every account cut at the same break (R21) |
| check L3 — a STOPPED dry run still satisfied the fit stages' "dry run written" check | guard (3): the printout must end `DRY RUN COMPLETE`; it is pinned |
| check L4 — the dry run called `event_facts`, which counts forward sessions and reads the last bar date | dropped; the walkability tally comes from `history_reason` (calendar indices up to the buy day) |
| check L5 — L1 / L6 scored on brackets that closed before the level existed; an EP's L3 equalled L5 | §6b: `no_level_yet` before 09:35 / 10:30; EP L3 = the prior-20 high (R18) |
| check L6 — registered beside items missing or altered | the §5d positive control (dated 290 vs the `tl` pool) runs at the fit; the pre-market first sightings read "crossed that session"; WHY's SOLD class gets its X1–X10; the undated-only EXIT fit uses the same held-out family rule; the after-loss flag reads the inferred fill, in the 2020 fit too; the 2023 SELECT beside buys are listed, not scored (R19) |
| check L7 — "session 3" was coded as offset 3; the first red close could fire on the buy day | §3: the buy day = session 1 (offset 2); the first red close from session 2 (R17) |
| check L8 — no test ran a stage runner; two asserts passed trivially | the EXIT fit runner test (H1), tests per finding, the two asserts tightened (the stop-choice one had hidden that the fixture's tightest C level is S1) |
| re-check N1 — the M2 fix let the dated 2021-22 trades (111) decide the STOP check, but the EXIT fit walks all 111 under the CHOSEN stop before `--check` and writes their stop prices and per-day R at the close, so their held-through rate under the chosen level is readable from the fit's files | **DECIDED 2026-10-24, main loop: option (b).** The undated 226 decide the STOP check alone (`stop_verdict` takes no dated table; §7, §10, R12); the dated 111 are printed beside on every level and variant; the EXIT fit stays one population under one stop. Option (a) — the registered stop on those 111 inside the EXIT fit — was not taken (it moves the R unit on 111 of the 590 fit trades). Test: the verdict's signature has no dated table; the undated table still blocks alone |
| re-check N2 — the chain's buy-day stop check was never recomputed against the chain's stop (`apply_chain` filled it only when empty; the undated registered fill returns a hard-coded "not stopped"; `check_stages`' second call kept the first call's result), so "ours" never stopped out on the buy day while "chosen" could | **DECIDED 2026-10-24, main loop:** `apply_chain` always sets `r.day0 = day0_for(r, r.fill_minute, r.stop)` after the stop is set (covers the second call). In the same mechanics, `day0_for` reads a close fill (`fill_minute` None, the dated close-fill proxy) as never a buy-day stop: the unconditional recompute would otherwise have spread to "ours" a defect already in the chosen walks — under S1 = the day's low a "low ≤ stop" reading is true by equality, a stop below the close he bought at (R22). Test: an undated buy whose buy-day low is under the chosen stop (S3-T) exits on the buy day in ours (`stopped_day0`) and chosen (`day0_stop`), on the second chain call; a close fill is not stopped; the test fails on the old `apply_chain` |
| re-check N3 — the SELECT fit scored the chosen set on all 47 other-level buys, 12 of them SELECT check buys of 2021, printing part of the check's recall before `--check` | **DECIDED 2026-10-24, main loop:** the fit reads the 32 of 2019 / 2020 / 2023; the 15 of 2021 (the 12 check buys + 3 windows, named in §5b) are scored in `--check`, beside (`check_select_other_level.tsv`); the fit's light same-day pools no longer include their days. Test: the year split in `build_sets` |
| re-check N4 — §6 said one `no_minutes` drop on the 41 reads INCONCLUSIVE; `enter_verdict` needs fewer than 40 | **DECIDED 2026-10-24, main loop:** §6 now says one drop leaves exactly 40 (still decides), two read INCONCLUSIVE |
| re-check N5 — §12 still listed `event_facts` among the imported loaders (dropped at L4); the recount F5 row still said 49% | **DECIDED 2026-10-24, main loop:** `event_facts` removed from §12; the F5 row reads 48% |
| re-check N6 — `pool_floor_for` was a second copy of the floor, used only by a test | **DECIDED 2026-10-24, main loop:** `pool_floor_for` deleted (and `contiguous_ending`, its only helper); the test keeps the `floor_reason_from_table` half, with the raw-close-rescue and the hole-inside-130 cases moved onto it |

## The four fit choices (2026-10-24, copied from the fit printouts `01_rev_<stage>_fit.txt`; the only text added above the marker after the registered commit `1e19a959`)

CHOSEN SELECT: F3<=233 & F9>=-0.05785 & F10>=0.04256
CHOSEN ENTER: L1
CHOSEN STOP: none
CHOSEN EXIT: list: X7<=0 ; X1<=-0.5 & X4 ; X2<=0 & X5>=3

<!-- FREEZE -->
## Freeze record

Empty until the freeze. After the four fit stages, the main loop writes the four keyed `CHOSEN SELECT / ENTER / STOP / EXIT:` lines above
the marker line, runs `--pins`, pastes every pin below (the holdings pins, the timeline TSVs, the type tables, the caption list sha and
`qmlib.py`, the fetch list and the new minute folder's `_done.psv`, this module and its tests, the dry run printout, the four fit printouts
and the ledger, `doc_body`), copies the module beside the pins, then runs `--check` once. Any edit above the marker after that changes `doc_body`, and the
check refuses.

### Pins

- labels_joined: d0299beba6f2d0def7947bb6e77eac008ced4586450bb260ceed51f7b0fdca3b
- matched_events: 4d07d6e542bf5064cacf5e446a20566e9a1cb17fd126efee560634a2f6cd11fc
- moments: f2c81633de6c6765477368876e300c4636d34222b43a5b13245cdf96b8d3add0
- cand_A: 3c5a66dc3052d0a284cbfee8202f74deb4e5bb75c74565dd8147df015e1baa5a
- cand_B: b75c828671171530225198f97fc1191c9bced8f9448b9b05aa46099d617ce0c7
- export_A: 0d5d2d0eb027abc06e4186ddec7d1e8b1234fd86f92c26798a8e15f113db668d
- export_B: ccc0097fe535cb8de9b83d6d534744b6cbadc114d9d29ecac677ac18a52900ba
- sessions_A: 098a9b50c92a1045043bc089a4d4d600a9631bdb45a8e22969d872440672f2f0
- guard_A: 876a75ec6d51744579c1ea2744c1b529cbd941355ef12eb8f0451bbe7ba1af08
- guard_A_audit: 729741b4cfc5759b6ea5d81da6afdd36c11d806bbcad845964b2b37c72d94057
- guard_B: b6cb81b6c4a1f415defc5adcf236402d93cd654c33736aa0b120b78c357b5650
- flags_A: 5358e31dc1b27d25c5143bdfca7a98b91a6c7a2d5b1da6c9c9d9ed9c55474c1d
- flags_B: 8bf843859afb70ea59edf6f11cda12160020936c8df3e978b6a819590ea5c3d5
- verdict_A: 02cbb1c0106101cb12e8d5deb9448051ae3ced67966ac11d2475d06f26538de3
- done_A: 1277e2b2e87845bd9c38d5978e1601681b0b6a89dd5afd10ba3d3b67420f0ac6
- done_B: cf60dbe4d2c514f93dec779b98db7d47054839f1b24f1e74f3fadc0133b92178
- panel: 2f3c5ee919fcb510c0ba31f4cb82d736c75fe3705d6d94fd16776d2a74835012
- calendar_cache: 47111a051ac101f12818fb1b2e300fd61ff953673db1286e7f1c2cbbe291b610
- lexicon: c7fb05ac383ff63f8f76702cec07ad1c08c517dbfb7a0843ee9a96a7d1e5105f
- dedupe_A: 223d3f360369cc009919c6fae83b3ba0bb37aa437706b45fcbbb70560477cf64
- ep_A: 59f196e5aa45a35eb7d98e1a1147ac4925e9f4967a17863e039659eed6c9dc46
- ep_B: 160401c752ff0b8d3d3f2ad7a1eff63d6c36d285aaa34c6e5ca00b737b68ee3c
- entries: 6a0dda2da7932b6d54f122594df817215c1237636629f3ce6efa7cef1b9bdabf
- exits: 1ed76a2806091f7d56726c56e6b2a389dfa2e96db24c382d4296da096529b50f
- snapshots: a8987fce15fa1a968010b4290c249f2c62de24d18d1b71bca4b9b0c4f507caff
- control: 193a5b985b1d979d59b2d09e67a8caeb4fac9d4073f54b84b1f7315d69d15ccc
- timeline_printout: cbc08080f82705b6fb4e2fd2970166113b5c0f35ab646ca2226d2344cea6a6ac
- panel_read_printout: cee0fca158007117fa4370511cbbce4a3d1da6ca6760f8792885988ecd1b9ad3
- done_EP: 0eb3548afe46feecf785e27b4b2e0839d5392c71bf4d67a1789f75e40c6ac735
- done_EP2: f8255199e52f0fa14aebcec5d50a407a1a52ac7c8b6cd4129bf41aa2f8cc591a
- small_pulls: b8d37aae5ef85c25bc52479eef7f6b04a8a4e67557caaef7a426d8ae20194643
- sic: 0e476c4422d56648d615c48d941edb971a348dfb99821023116d0fd98e617346
- raw_close_A: f978db45074e9109178a1755c232fa1e684a6f83dab96ab007a26b12008f1444
- stream_moments: 7cd53c671f425f71e44ecd70472564df125780bf2e1a55c92b51f5caecea7104
- video_status: 9f7a7e4cb1fd8ae5eb69a4daa4eb9eec7f9e969341249d41ffa469cb1bf9c692
- fetch_list: 4191485f2abddc25c042132729742491c191dfbe85d0dc2099fa023d34e3770f
- done_REV: 945c41fb3618ed6b85a000232f6becc82c9d8e201b9bde99bd8673f9f7036d5e
- runner: 213cbe6ddf0ff05555a11c347efd14bfa37f99096fd83961e9f5127f6c7c8dcf
- registered_read: 28fbc47f862f205071ab921af3a29f6093fca95e2d41e3a0f4a0f7afcd9aa449
- cb_module: e14027be38b24352dd3c19fd5a1dcd54bae2e1cf80fc58a064d1ea65c821861b
- constants: 72dadd72503a842f593621b0868f908ab99e1d77851330c2842be7797aa99400
- fit_module: 3fca7bf4f26ffcdf7152ddc9d4180c295aafe29067591def812fcc6884f38d27
- join_script: 6889819c41342c60831b0d62b277d47b677e4deaeab3443cbdde7a05d56b112c
- aplus_read: e344277817db88de7af2e65ad8858d4ca515c3cc3a647b3e0a67e0df9f7ec9ee
- trade_impact: 9b7cce415479c1abfda422c432c6de1f3a6d591f298a1167fa637a578051e146
- replay_module: c44785889670b31f3e9baf1ac0e1563aeacfefacc5de5ef426ee7b15724e7bfa
- replay_tests: 37c918a08329b138f6c37c5787af3c95e0ea2abeceb100209cd0f5f0dd0a96ad
- exec_module: 346516fb4c236cc552103032163b790d030b10a536e83c70d4cf2390c3f9f485
- exec_tests: 6ce013bb1d7f1521e8083d014e4221fc837f30c59f9c5e00fbc023344d1a1949
- timeline_module: e91e3f4dd8d7bc29664cfeccd2fe6b8ec7a5f906a25281bd338f3fe62d2bfee7
- timeline_tests: 920085c4fecd2b2ea4799b939f16a30a2f1b271fc199149419c2ed0f0df029af
- holdings_module: 4275d72f82aaf66c7c24372afe48e0b503dedb51e2c7715d8fbd26c4372e9ce9
- holdings_tests: eee66bf08ef8f70c5da66b4aeec0f626f592ca327dcfc7c6c0c6fd1943a0b75f
- panel_reader: 14a9764f883aa5516a85da47346871247eabfbcb514ce03c8e602175cbf2a230
- qmlib: 0f281f05338f5b40d4b1d8be4b9ada427ebcb919c012cd3af9300f6d70f8640b
- security_type_check: e634362271876028736100249f21bfa410b4c99a3cd2106af89f3af41972bc40
- rev_module: e908253f7405f814351ced03bd61a80b7886268bcee366f70f66c4a5f74aaeff
- rev_tests: c74babedfc1923d65e79698284c3783b0e405fe0f337eab26791fb6a1c6fc749
- subs_list: 99929453752cb3590b261e6928d99317312f35d9a50c0c147e33393b101a64a9
- first_doc_body: aaaadd295aba5a9de534a738410ebe391ac4993637faa7ead0cab78e2b7a9dab
- second_doc_body: 329ac865f814de0909332ff516ea5d52dea525fbef7b5fdcf1c9208a521143fe
- holdings_doc_body: 69510e1a3092e1c74b9869342a24b624500ca65c814410ae7cf2348f71384b58
- dryrun_printout: 935ce2981efec7b314f6f9ffa9746f6602982ccc195a2456d0b161d79e7e2e4a
- select_fit_printout: 0893e38a7d2afbf9abfc0c350db2d43f4cf461b0a26f86ce4b46b9b96297208e
- enter_fit_printout: 743e0c124bc5992b3d7adc1ff55545540f267f4def4f5788f9aae5f93d326724
- stop_fit_printout: 95b97b95b44099b41c52acbff0623ff48c8b6c918286a6d162e4011c8abe80f0
- exit_fit_printout: eac07e9a42fce45397b6951e14594fe0bddca59b8dcabedc7635812fbaf29305
- ledger: aba22388d8747cba87952cd264b09d7fbc6a407466917de1eb55dddb16691611
- doc_body: 16a3057d99b55f4588ffa3cf3fea34da97d5d1e7dee7c0da76d8bfaffe7fe287

### Fit-stage events (disclosed; below the marker)

- **Code changed after the registered commit `1e19a959`, before any outcome of a check set was read — two crash fixes, no rule, threshold, grid, family or set changed:**
  - SELECT fit run 1 crashed in its BESIDE block (`IndexError` in `pick_features`): the feature-table cache was keyed by `id()` of a bar array, and a freed array's id was reused by another ticker's, so a cached table could serve the wrong stock. Fixed in `feature_table_for` and the same pattern in `smas_for` (the cache entry now holds the array, so its id cannot be reused while cached); test `test_id_keyed_caches_never_serve_another_arrays_entry` fails on the old code. Run 1's printout up to the crash (the fit, the planted control, two beside lines) was seen; it is kept in `scripts/probes/_705_reverse_1024/verify/fit_events/select_fit_run1_stdout.txt` and `select_fit_run1_crash_STOPPED.txt`. Its fit lines equal run 3's (same CHOSEN set).
  - SELECT fit run 2 crashed in the rank fit (§5d): numpy 2 refuses `float()` of a one-element array; three sites (two in the fit, one in `--check`) take element `[0]`; test `test_rank_score_of_one_pick_is_a_scalar`. Run 2's STOPPED file and ledger are kept in `verify/fit_events/`; its side outputs moved to `apollo_data/cb702/qm_streams/holdings_1024/reverse_fit_events/`.
  - The dry run was re-run after each fix (63 / 63 counts, identical but for the module sha); the earlier printouts are kept in `verify/fit_events/`.
  - Run 3 of SELECT and the single runs of ENTER, STOP and EXIT are the fit printouts pinned below.
- `test_stage_outputs_refusal` reads the REAL outputs folder and fails whenever fit outputs exist (as now); it is an environment check, not a code defect.

## RESULT — the one check, 2026-10-24 (printout `scripts/probes/_705_reverse_1024/01_rev_check.txt`; written BELOW the marker; the body above is the freeze commit `1aea0959`'s)

**SELECT PASS · ENTER FAIL · STOP INCONCLUSIVE · EXIT VOID (no bar) · WHY below its gate (no rate).** Independent recount (Opus, own script,
`verify/recount/recount_check.py` + `.txt`): every printed number and verdict reproduces; one era-B calendar defect found (below), no verdict changes.

| Stage | What was inferred from his 2020 trades (the fit) | On the 2021-22 trades it never saw (the check) | Verdict |
|---|---|---|---|
| SELECT (his no-event buys, n = 144) | a three-part daily condition: ADR20 ≥ 4.26%, not down more than 5.8% over 60 sessions, a 52-week high within the last 233 sessions (fit recall 74% at a 19% pool rate; beats 20 of 20 planted sets) | recall 64.8% (±8) at a pool rate of 18.6%, lift 3.48 | **PASS** (bar: recall ≥ 50% at pool ≤ 20%) |
| SELECT rank (within the qualifying names, n = 79) | logistic on the 2020 buys vs the qualifying pool | his picks' median percentile 0.29 | INCONCLUSIVE (PASS ≤ 0.25; falsifier ≥ 0.40) |
| ENTER (in-session buy windows, n = 41) | the opening-range high (5-minute), first crossed inside his buy window on 36% of 2020 trades | 36.6% (random-minute control 31.7%); ballpark 87.8% vs control 85.9% | **FAIL**: no modelled level is his buy point |
| STOP (undated 2021-22, n = 212 records) | no level met the held-through bar (≤ 10%) on the fit | every level held through on 39-80% of the trades where price crossed it | **INCONCLUSIVE**: no fixed price level |
| EXIT (undated 2021-22, n = 212) | a 3-rule sell list: a close at or under cost; a close half an ADR under the 10-day AND under the prior low; a close under the 20-day after session 3 (fit recovery +0.45 in-sample) | ours 1.503× · the rule 1.646× · his 1.727×: his exits beat ours by only 1.15× (VOID under 1.25); the rule hits his sell session on 37.3% (trivial rules 19.6-27.0%) | **VOID (no bar)** |
| WHY (20 caption joins, two readers) | — | 12 of 20 correct (the readers agreed on 18; the two splits, VXRT and MGM, took the stricter reading) = 60% | below the 70% gate: no rate quoted |

- **Beside, read with it:** on the DATED 2021-22 breakout trades (in-sample for EXIT, never deciding) his exits are 2.62× against ours 1.40× — the
  exit gap lives in his breakout winners, not in the no-event buys the check decides on.
- **Recount defect (era B, buys on or after 2022-04-01):** the sell-date index came from the full calendar and the buy-day index from era B's
  own, so 8 check trades (and 12 dated EXIT-fit trades) carried sell dates ~1,440 sessions late. Corrected by the recount: STOP S4-C 80.0% →
  66.7%, S1-T 43.9% → 39.2% (still INCONCLUSIVE); EXIT his ÷ ours 1.149 → 1.152 (still VOID), the non-flicker 'his' 1.341 → 1.533; the hit rate
  37.3% → 37.7%. The EXIT fit's 12 era-B trades were not re-fit.
- **What it means (no money, no rule changed):** his no-event buys are not random — a simple daily scan (volatile, not falling, near the year's
  high) catches two in three at one stock in five. Inside that pool, which names he picks is not yet shown. His entry is not the first crossing
  of any daily or 5-minute level we model, and no fixed daily price level is his stop. His own words name the untried layer: *"the opening range
  highs can be the highs of the first 1-minute candle, the 5-minute candle or the 60-minute candle"* (operator_shared_notes.md l.1941-1942;
  his 60-minute first candle is 09:30-10:00, l.2090 — our L6 was 09:30-10:30), and 334 of 495 stream caption files mention the 60-minute chart
  (e.g. FSLY 2020-07-14: half sold *"when it broke below the 20 … ema on the 60-minute chart"*, the rest on the prior day's low).
- **Next (registered separately):** the intraday layer — the 1-minute and 30-minute opening-range highs for ENTER, 60-minute lows for STOP, the
  60-minute 20-EMA for EXIT — on the levels never scored here; the sealed 2025-26 test stays unspent until an entry and an exit reproduce him.
