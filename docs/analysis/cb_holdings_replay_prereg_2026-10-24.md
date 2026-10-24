# #705 — His holdings, replayed under his rules against the market: pre-registration (2026-10-24)

**Status: REGISTERED, NOT FROZEN, NOT RUN.** Outcome-free: no price after any buy day, no fill, stop, exit, R or return has been read
for any entry named here, and no stored replay outcome file (the three frozen replays' trade tables and curves) was opened. The timeline
(`scripts/probes/_705_holdings_1024/01_timeline.py`, printout `01_timeline.txt`) read the panel, the candidate streams' pre-E columns, the
EP gap-day rows and the frozen label classes. The replay module's dry run (`02_replay.py --dry-run`, `02_replay_dryrun.txt`) loaded the
entries, the daily exports up to each buy day's D, the fetch logs and the pins; it COUNTS the sessions the export holds after each buy
day (`fwd_sessions`, a calendar count) and reads each ticker's last bar DATE, but reads no price after D, opens no minute file and calls
no entry or exit function. Revised once before the freeze on an adversarial review (§12, F1–F8), from timeline counts and frames only.
Measurement and registration only. Nothing here changes or proposes to change a strategy, an entry, a stop, an exit, a size, a
safeguard or any live trade state — those are the operator's (THE LINE). The main loop freezes this doc and the module, commits, and
runs the replay ONCE.

**His bar (2026-10-24, verbatim, PLAN #705):** *"at the very least the test needs to show real alpha and strong market outperformance,
otherwise the strategy is DOA"*. **His rule for a miss (2026-10-23, `docs/methodology/operator_shared_notes.md`):** *"the setups work (at
least in the past), so our backtest should show the same, if not that it's something wrong with our implementation and interpretation, not
that it's not profitable"*. **His source (2026-10-24):** *"the bottom right of his screen is a stock list of his holding"* — verified on
four frames: the TC2000 list "A - Positions".

## 0. In plain words

- **The question.** His stream screen shows his holdings. Every frame is a snapshot of his book, so a name that appears between two
  streams was bought in between and a name that disappears was sold. That gives HIS trade list — not the 236 breakouts he happened to
  mention, but what he held — over 2017–2023, with 2020–2021 nearly day by day. We date each buy to the breakout day or the gap day our
  streams show inside that window, trade it his way, compound the trades in one account, and ask his own question: does it show real
  alpha and beat holding QQQ and SPY over the same dates?
- **The answer is one table** (§7): the account's total return, Sharpe, beta and alpha (with its t-statistic) against QQQ and SPY over
  2020-01-27 .. 2022-06-14, the span where every stream is 1080p and the gaps between streams are a few days. The bar is fixed below
  before any outcome: **alpha t ≥ 2, total above QQQ and above SPY, Sharpe above QQQ's.**
- **What a FAIL means (his rule):** our implementation — the dating, the fills, the exits, the sizing, or the data — never the setups.
  The panel's own exit dates are replayed beside his rules so a fail can be split: if his book sold at the panel's dates passes while
  our exit rules fail, the leak is our exits.
- **Action from him: none now.**

## 1. The four questions of the standard

1. **Decision served:** whether the trades he actually held, traded under his written rules, clear his own bar. PASS → the setups as
   dated carry his bar and the gap to his record is WHICH names our detector finds (Track A's 1-of-66) plus the trades we cannot date;
   FAIL → the next work is named by the beside readings (§7).
2. **What would change it:** the bar in §7, fixed before any outcome.
3. **Population:** §2, from the timeline printout (outcome-free).
4. **What would make this wrong:**
   - (a) **The panel is read by OCR.** 89% of frames carry the panel; symbols are ~98% right at 1080p and ~92% at 720p
     (`scripts/probes/_705_positions_panel_1024/02_read_all.txt`). The timeline guards (§2: duplicate uploads, two-snapshot exits,
     blips, flickers, the look-alike guard) are built from the measured failure modes; a residual misread becomes an undated entry,
     never a dated one, unless its look-alike had a breakout or gap that day. The look-alike guard (F2, §12) catches the case the review
     found twice (LI read as UI, SQ as SO, in the last full snapshot before the true name's first sighting): 18 renames over the
     timeline.
   - (b) **The dating is ours.** A name bought inside a window is placed on the LATEST breakout or gap day inside it; 90 of 344 dated
     windows hold more than one event. With 1,158 of 1,861 windows one session long, most datings are forced; the rest are a reading.
   - (c) **82% of his entries cannot be dated to a breakout or gap day** (1,517 of 1,861): ETFs and leveraged funds (TQQQ, SOXL, TNA,
     YINN …), names our bars never carry (GBTC, ETNs, SPACs), and 1,040 real names with no breakout or gap inside the window — his
     parabolic shorts (the panel shows positions, not their side), day trades, adds and buys we do not recognise. The deciding
     account is the 18% we can date; the rest is read beside at the open of the first possible day, or not at all.
   - (d) **The panel shows positions, not their side.** A parabolic short on a gap-up day reads as an EP-dated long. The breakout-dated
     subset is read beside as the clean long set.
   - (e) **Our walk is our reading of his article** (ORH5, low-of-day stop, the day-3 third, the trail), one point of his sizing ranges,
     and no adds. The panel's own exits beside his rules bound the exit part only.
   - (f) **Minutes:** the first dry run found 39 EP-dated deciding entries with no minute file in any tree; they were fetched before the
     freeze (§9), and the dry run now reads every deciding entry covered (0 missing). Any pair missing at the run would abstain
     `no_minutes`, counted.
   - (g) **Coverage is one regime:** 151 + 104 of the 294 deciding entries sit in 2020–21; 2018 has one stream; Q1 2022 has no breakout
     stream at all (era A's last E is 2022-01-03, era B's discovery starts 2022-04-01).
   - (h) **Survival conditioning.** The panel shows only buys still held at a snapshot: of the timeline's 264 deciding entries in the
     window, 172 are first seen in session on E, 75 after E's close (an after-close frame on E or the next pre-market), 17 a session or
     more after E. A round trip completed between two snapshots is invisible, so the dated book leans toward the buys he kept — the
     bias is UPWARD.
   - (i) **Same-day exits.** 42 of those 264 leave the panel by E's close (EP-dated: 11 of 43) — day trades or shorts (BKKT on its
     +18% gap day shows −19.3% on the panel and leaves the same day). They are walked like every other entry.
   - (j) **The blip fill costs recall, not precision.** 118 of the 125 blip fills override a footer-consistent absence (the footer total
     equals the rows read and the name is not among them; SPXL 2020-04-20: 4 items, 4 rows, no SPXL) — so some fills merge a real round
     trip into one hold. That can drop an entry; it never creates one.

## 2. POPULATION — his panel entries (the timeline, `01_timeline.txt`; every rule fixed before its count)

**The timeline rules** (the module's docstring is the registration of record; summary):
- **snapshot** = a frame with the panel found (2,977 of 3,342 frames; list A, or the 2017 "B - Positions" list, 24 frames), less the
  duplicate uploads (below): **2,907 snapshots in 517 streams**. Its date is the MODE of its video's taskbar dates; its clock context is
  pre / in / closed (142 unknown read as in-session, the widest window).
- **duplicate uploads** (F1) = the same stream uploaded twice on one date: a frame whose (clock read, stream time, list, rows read,
  footer total) already appeared in ANOTHER video that date is dropped, the larger copy kept (17 videos on 13 dates, 70 frames); a
  duplicate's leftover frames (10, the same stream sampled seconds apart) join the kept copy's stream.
- **full** = the whole list is visible: footer total = rows read (2,009); footer above the rows = scrolled, NOT full (751); no usable
  footer → geometry, the last row ends ≥ 1.5 row pitches above the panel bottom (73 full / 74 not). "0 items" is a full empty list.
- **order** (F1) = each date's frames by ET clock ACROSS videos: the video's clock fitted to its stream time (the median of clock read −
  stream time; the 21 misread clocks, all 2019, never reorder a video), then the stream time. The 7 videos with no clock read are each
  the only video on their date.
- **asof(s)** = the last session the snapshot's holdings reflect: pre → the session before its date; in / closed → its date.
- **entry** = a name in snapshot s not held: bought in [lo, hi] sessions, hi = asof(s), lo = the first session a buy could be missing
  from the last FULL snapshot f (f pre or in → f's date; f closed → the next session). No full snapshot before → INITIAL (13, all in
  2017-01, all gone by 2017-08-23; undatable, never replayed). lo > hi → lo = hi, flagged (34).
- **exit** needs TWO consecutive full snapshots without the name (a sighting in between cancels it: 229 single-frame drops); hi = asof of
  the first. Streams absent from one whole full stream but present either side are blips (125 filled). A name still held at the end:
  13.
- **look-alike guard** (F2) = a name X first appears in snapshot s; the last full snapshot f holds a symbol Y one edit away (UI / LI,
  SO / SQ, BIL / BILI, CC / CCJ); Y is absent from s; and the reader flagged Y's row in f — its % cell disagrees with Y's own bars that
  day, or its look-alike search suggested X. Then f is relabelled Y → X (X was held there: no entry for Y, X's window starts before f),
  and the timeline is recomputed to a fixed point. Ties: the suggested name, else the nearest % read, else no rename. 18 renames (8
  suggested, 9 % mismatches, 1 nearest % read: UI → LI 2021-11-29), 0 ambiguous; each printed with both frames. The % check uses the
  frame day's own range — no bar after it.
- **flicker** = one-stream sighting whose exit is confirmed within 5 sessions (659): flagged, read beside; a DATED flicker decides.
- **dating** = the LATEST tl breakout day (era A K = tl for E ≤ 2022-03-31; era B K = tl, discovery, E ≥ 2022-04-01, rows after 2024-12-31
  dropped at read) or primary EP gap day (gap ≥ 9% on ≥ 3× the 20-day volume, $5, $10M; `ep_events_{A,B}`) inside [lo, hi]; both on
  one day → `both`; none → undated (beside: the first session of the window at its open). Era A's files key today's symbol: a panel name
  with no era-A rows is mapped by the overlap-close signature (FB → META; 504 aliases) or the dedupe map (70); 14 panel names joined via
  an alias.
- **decides** = dated AND window ≤ 10 sessions AND not initial.
- **panel clock on E** (F3; read beside the fill minute in the run, §7, never a filter): `first_clock_on_E` = the first sighting's ET
  clock when it is on E in session; `flat_clock_on_E` = the clock of the last full snapshot without the name when it is on E;
  `orh5_infeasible` = held on E before 09:35 ET, before any ORH5 fill can exist.
- **same-day re-buy** (F4, the replay) = a name's later entry dated to the same buy day as its earlier one: it cannot reuse the earlier
  fill (the panel showed him flat in between), so it leaves every account (§4).

**The timeline by year** (stream date year):

| year | streams | stream dates | snapshots | full | distinct holdings | entries | initial | flickers | exits | median days between streams | max gap |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2017 | 11 | 11 | 33 | 8 | 92 | 81 | 13 | 4 | 46 | 6 | 164 |
| 2018 | 1 | 1 | 8 | 8 | 16 | 16 | 0 | 0 | 48 | – | – |
| 2019 | 39 | 39 | 223 | 125 | 133 | 198 | 0 | 82 | 184 | 1 | 18 |
| 2020 | 218 | 216 | 1,535 | 1,018 | 337 | 803 | 0 | 304 | 814 | 1 | 6 |
| 2021 | 177 | 177 | 887 | 706 | 246 | 583 | 0 | 211 | 589 | 1 | 28 |
| 2022 | 59 | 59 | 159 | 157 | 90 | 132 | 0 | 51 | 139 | 1 | 142 |
| 2023 | 12 | 12 | 62 | 60 | 38 | 48 | 0 | 7 | 41 | 3 | 175 |
| **all** | **517** | | **2,907** | **2,082** | **684 names** | **1,874** | **13** | **659** | **1,861** | | |

Entry windows (sessions, 1,861 non-initial entries): 1 session 1,158 · 2: 251 · 3–5: 173 · 6–10: 128 · 11–20: 63 · 21–60: 40 · 61+: 48;
within the cap 1,710.

**The buy dating** (the latest event in the window):

| year | entries | breakout | EP | both | undated | DECIDES (dated, window ≤ 10) | of which flickers | dated, wider | undated: no bars | never a candidate | no event in window | window touches the Q1-2022 hole |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2017 | 81 | 7 | 3 | 1 | 70 | 3 | 0 | 8 | 11 | 16 | 43 | 0 |
| 2018 | 16 | 7 | 4 | 2 | 3 | 0 | 0 | 13 | 0 | 2 | 1 | 0 |
| 2019 | 198 | 14 | 9 | 0 | 175 | 16 | 3 | 7 | 25 | 34 | 116 | 0 |
| 2020 | 803 | 125 | 20 | 6 | 652 | 151 | 45 | 0 | 52 | 129 | 471 | 0 |
| 2021 | 583 | 88 | 22 | 1 | 472 | 104 | 37 | 7 | 28 | 136 | 308 | 0 |
| 2022 | 132 | 10 | 5 | 0 | 117 | 13 | 6 | 2 | 0 | 41 | 76 | 73 |
| 2023 | 48 | 8 | 12 | 0 | 28 | 7 | 0 | 13 | 1 | 2 | 25 | 0 |
| **all** | **1,861** | **259** | **75** | **10** | **1,517** | **294** | **91** | **50** | **117** | **360** | **1,040** | **73** |

- **DECIDING population: 294 entries** (breakout 229, EP 58, both 7), 153 panel names, 211 buy days, era A 277 / era B 17; 165 of the
  breakout-dated sit on a RETRIGGER of our trendline (he buys later crossings too); 91 are flickers. Panel exits seen for 290, 4 still
  held at the last snapshot; the exit window's median is 1 session. Two of the 294 are same-day re-buys (F4: PLUG 2021-02-03, SNAP
  2021-06-11), so **292 are walked** as deciding entries.
- **The deciding WINDOW of the account: 2020-01-27 .. 2022-06-14** — the first stream date in 2020 with every frame at 1920×1080 (the
  last 720p stream is 2020-01-23; at 720p a name and its look-alike alternate inside one stream, APPS / ASPS, so the frame-level state
  machine is not reliable there) to the last stream before the 5-month gap (2022-06-14 → 2022-11-03). **264 deciding entries fall in
  it** (breakout 214, EP 43, both 7; 133 panel names, 185 buy days); without the two same-day re-buys **the deciding ACCOUNT holds
  262** (breakout 212, EP 43, both 7; 132 bar-file tickers, an alias merging two panel names). The 2017–19 and 2022-11..2023 deciding
  entries (30) are read beside, by year.
- **Symbol join (684 distinct panel names):** in a candidate stream directly 436, via an alias 14, bars but never a candidate (ETFs,
  leveraged funds, thin names) 153, no bars at all 81 (ACTC, CCIV, CIIC, ETCG, FNMA, GBTC … — SPACs, ETNs, OTC).
- **Holes stated now:** (i) **Q1 2022** (2022-01-04 .. 2022-03-31) has no breakout stream, so 73 entries whose window touches it can only
  be EP or undated; (ii) 8 deciding entries have a forward window shorter than the 120-session horizon (an open walk is marked at its
  last bar, booked at that close, counted `degraded`): 3 from the era-A export's end 2022-06-30 (SNAP 2022-02-04, DDOG 2022-02-10, UPST
  2022-02-16) and 5 from the names' own bars — LK 2020-02-18 (its 2020 trading halt cuts the window; delisted 2020-06-26), LVGO
  2020-09-25 and APHA 2021-01-06 / 02-10 / 03-02 (mergers; bars end 2020-10-29 / 2021-04-30); era B carries no 130-session history
  before ~2022-04-01; (iii) 2018 holds one stream, 2017 eleven at 24% full; (iv) 6 deciding entries (4 in the window) have a hole in
  the 130 sessions of bars before E and cannot be walked (counted, listed).

**Dry-run facts (`02_replay_dryrun.txt`, outcome-free: bars up to D, a COUNT of the sessions after E and each ticker's last bar date —
no price after D —, the fetch logs, the identity guard, the calendars):**
- The deciding window holds **602 sessions**; its 262 entries (n = 262) fall on **185 buy days** and **132 names** (2020: 149, 2021: 102, 2022: 11);
  the busiest month holds 27 entries.
- **Walkable 258 of 262** (4 with a hole before E); minutes covered (fetch logs) **258 of 258** (era A tree 213, era B 7, the EP tree 11,
  the pre-freeze EP fetch 27), **missing 0**, so **KEEP = 258 walked in the real run**. Over all 292 deciding entries: walkable 286,
  covered 286 (A 224, B 11, EP 12, EP2 39), missing 0 (`holdings_1024/replay_missing_minutes.tsv` is empty).
- ADR20 at D: median 6.3%; **199 of 258 are above the speed cut (4.79%)**, so the deciding exit trails the 10-day on 77% of them and the
  20-day on 59 (the same share as his 236 calls: 77%).
- QQQ at D (the close before the buy day): up 162 / mixed 40 / down 56 — a reading, never a filter.
- Identity breaks in (E − 130, E]: 0. Forward window shorter than the horizon: 8 (hole (ii)).
- Panel clocks (F3) in the account's window: held on E before 09:35 ET 9 (TSLA 2020-04-14, UAL 2020-05-27, DXCM 2020-07-29, PINS
  2020-07-31, SHOP and TTD 2020-08-26, KOLD 2022-04-19, LAC and TSLA 2022-04-21 — no ORH5 fill can precede the panel there); flat at
  an in-session snapshot on E 92; first seen in session on E 172.
- Same-day re-buys (F4): 30 — the 2 dated ones above, and 28 undated doubles (beside: never walked twice at the same open).
- Calendars: era A 2016-01-04 .. 2022-06-30 and era B 2021-09-27 .. 2024-12-31 agree on all 192 overlap sessions; the unified calendar has
  2,264 sessions; QQQ / SPY closes stitch within 0.5% on the overlap (asserted).
- The same-day band's pool: 22,660 era-A tl rows on 151 of his breakout buy days (2,537 tickers, loaded with his names).

## 3. THE CONTROLS

- **The positive control of the dating — his 236 stream calls** (the Track A positive events, labels said on or before our breakout day
  E, derived by the frozen fit module). It tests the dating, it decides nothing. **Disclosed: it was read three times.** The first
  timeline run (one-frame exits, flickers never replayed) read 34 dated on E / 38 windows holding E; the rules were then revised on the
  SNAPSHOT diagnostics (single-frame drops, the APPS / ASPS alternation, the MDGL stream gap — §12), not on the control, and the second
  run read 29 / 33. The review's fixes F1–F4 (§12) came from the duplicate-upload and look-alike scans and the frames, not from the
  control; the third run (after them) reads 29 / 33 again, every control line unchanged. All three numbers stand here; the control was
  not used to choose a rule.
  - **29 of 236 (12%) are panel entries dated ON their own E** by the rule (27 by the earliest-event rule); 33 have a window holding E;
    31 decide. Of the strictly-before 127: 7 dated on E.
  - **75 were ALREADY in his book at E** (an open panel entry whose window ended before E: 49 by 1–5 sessions, 16 by 6–20, 10 by more;
    their open entry is undated 47 / breakout 27 / both 1); **53 more** were seen in the panel in the 20 sessions before E with no
    entry we can place. So for about half of his calls our breakout day E is LATER than his buy — consistent with the first replay's
    "62 of 236 never fill at our level": he was in before the day our trendline broke.
  - 30 never appear in the panel (TDOC 2021-04-07: he graded it, he did not hold it); 35 appear only elsewhere; 10 appear only after E.
  - 224 of the 236 E-days carry a snapshot on E itself, so the misses are not coverage.
  - **Reading:** the panel dates his buys independently of our E; a call is not a buy. The replay below is of the panel's entries, not
    of the calls.
- **The same-day band (beside, never deciding):** for the breakout-dated deciding entries of era A inside the window, the first replay's
  reference band exactly — on every buy day E, as many OTHER tl breakouts of that day as his entries on it, drawn without replacement
  (all of them on a day that holds fewer, counted), **200 draws, seed 702, key `holdings|band|A`**, each draw run through the same walk
  and the same deciding account. Reported: the 5th / 25th / 50th / 75th / 95th percentile of the final equity and of each year's return,
  and the share of draws at or above his final equity. The pool excludes every row of a name he held that day (any entry of the name
  with lo ≤ E ≤ exit). EP-dated entries have no same-day pool here (the EP stream is not a detector stream) and are not in the band.

## 4. HIS RULES — the walk (the frozen modules, imported read-only; nothing edited)

| piece | rule | his words / source | code |
|---|---|---|---|
| entry, breakout-dated | **ORH5 on the buy day E**: the first minute after the 5-minute opening range whose high clears max(the opening-range high, the trendline level projected to E), filled at that level or the minute's open if it gapped through, 0.1% slippage | the article: *"Enter on the opening range highs"* | `cb.entry_variants(...)["orh5"]` with the candidate row's `pivot`, `adr20` (the first replay's wiring, `rp.walk_event`) |
| entry, EP-dated | **ORH5 on the gap day**, the level = the prior close (`prev_close_adj`; the gap clears it, so the fill is the pure opening-range high); ADR20 = ours from the 20 bars ending D (`ex.adr_pair`) | his correction 2026-10-23: *"he buys orb high and states this many times and wrote this in his own webpage"* | the same function, `pivot` = the prior close |
| stop | **the low of the day at the fill**; **skipped (`too_wide`) when wider than ADR20** | *"Stop is always lows of the day and stop should not be wider than the ATR or ADR"* | same |
| day 0 | the rest of E on the minutes; a stop-out is −1R, or worse on a gap | the runner's day-0 walk | `cb.day0_walk` (inside `entry_variants`) |
| exit, PRIMARY-of-the-first-replay (beside here) | `p33_s3_t10`: sell 1/3 at the session-3 close, stop to breakeven, the rest at the NEXT OPEN after the first close under the 10-day average | *"sell 1/3 to 1/2 … after 3-5 days, move the stop to break even … trailed with the 10- or the 20-day"* | `cb.ARMS["p33_s3_t10"]` via `cb.walk_arms` |
| exit, DECIDING | **the speed trail `d3_p33_tspd`**: the same day-3 third and breakeven move, then the 20-day average, or the 10-day when ADR20 at D is above 4.79% (`cb.TRAIL_SPEED_ADR_CUT`, fixed 2026-10-18) | his 10-18 correction: *"10d for faster stocks and 20d for slower stocks"*; round 3's only registered gain (2.20× vs 2.04×, a different population) | `cb.HIS_EXIT_ARMS["d3_p33_tspd"]` via `cb.walk_arms` |
| sizing, DECIDING | **risk 1% of equity per trade, position capped at 30% of equity, at most 30% of equity at cost in one stock, no margin** (the first replay's `cap_30` row, round 3's baseline) | the article's ranges; the 30% cap was the only sizing gain of the second read | `rp.Config("cap_30", cap=0.30)`, `rp.simulate` |
| sizing, beside | the first replay's PRIMARY: 1% risk, 20% cap, 30% per stock | the SSoT's article sizing | `rp.PRIMARY_CONFIG` |
| horizon | 120 sessions, then marked | the runner's | `rp.HORIZON` |

- **The DECIDING configuration is ONE: ORH5 entry, low-of-day stop, the speed trail, the 30% cap** — the best-known reading of his rules
  from the three frozen replays, fixed before this population's outcome. The primary exit at the 30% cap, the primary exit at the 20%
  cap, and the speed trail at the 20% cap are beside (a 2 × 2 grid).
- **Re-entries:** every panel entry is its own trade. A name that leaves and re-enters the panel is two entries, each dated and walked
  on its own; nothing is "retried" beyond what the panel shows.
- **Same-day re-buys (F4):** a re-entry dated to the SAME buy day as the name's earlier entry (PLUG 2021-02-03, flat on the panel at
  10:55 between the two; SNAP 2021-06-11, flat at 11:51) would walk the earlier entry's ORH5 fill a second time. It is classified
  `same_day_rebuy`: out of the deciding set, the window, every account and the walk; listed beside with its earlier entry. The same
  rule keeps 28 undated same-day doubles from walking one open fill twice in the undated beside account.
- **Undated entries (beside only):** bought at the OPEN of the first session of the window (the first session after the last full
  snapshot without the name), 0.1% slippage; the stop is one ADR20 below the fill (his cap on the stop's width used as the stop — a
  modelling choice, stated; no low-of-day exists for an open fill); a day whose low touches it is a day-0 stop at the stop price.
  Names without bars are not replayed and are listed with their count.
- **Costs:** the entry pays 0.1%; every R and curve is printed at 0 / 0.1 / 0.2% exit slippage per leg; the headline at 0 (the runner's
  convention).

## 5. EXITS — his rules AND the panel's (beside)

- **His rules:** §4 (the speed trail deciding; the primary exit beside).
- **The panel's exits (beside, never deciding):** the same entry fill; NO stop and no trail; the whole position sells at the CLOSE of the
  exit window's LAST session (hi: the first full snapshot without the name, confirmed by the next) — the latest the panel allows. A
  position still held at the last stream is marked at the close of that stream's asof session. A dated entry whose ORH5 did not fill
  (no trigger, too wide, no minutes) is bought at the CLOSE of its buy day instead (he held it, so he bought it that day at some price;
  the close is the neutral proxy), labelled, so the panel-exit account holds his WHOLE dated book. Sizing: the same 1% / 30% / 30% rule
  with the width = the ORH5 stop width when the entry filled, else one ADR20. An exit session beyond the ticker's last bar marks at the
  last bar (counted).
- **Why both:** the panel bounds what his book did between the dates it shows; his rules say what our reading of his article would
  have done with the same entries. If the panel-exit account clears the bar and the his-rules account does not, the leak is our exits.

## 6. ACCOUNT — putting the entries back together (deciding window 2020-01-27 .. 2022-06-14)

- **Start:** equity 1.0 in cash at the close before 2020-01-27. The 13 initial holdings left the panel by 2017-08-23; no deciding entry
  before the window is carried in (entries dated before 2020-01-27 are read beside by year).
- **Calendar:** era A's SPY sessions (2016-01-04 .. 2022-06-30) joined with era B's after 2022-06-30; the two files' sessions on their
  overlap (2021-09-27 .. 2022-06-30) are asserted equal, and QQQ / SPY closes are stitched at 2022-07-01 after an overlap check (within
  0.5%). Era by buy day: E ≤ 2022-03-31 → era A bars and minutes; E ≥ 2022-04-01 → era B (point-in-time symbols).
- **Sizing, order inside a day, the per-stock limit, no margin, partial sells and the trail legs:** exactly the first replay's
  `simulate` (its §6): equity for sizing = the mark at the previous close; exits at the open, then entries in fill-minute order, then
  intraday exits, then exits at the close; a trade whose full position does not fit the free cash is skipped and counted.
- **Reported (deciding config, then the 2 × 2 grid and the panel-exit account):** the daily marked curve; equity at each year end and
  the yearly return (2020, 2021, and 2022 to the last exit of a window entry — the account runs the open walks out past 2022-06-14,
  while the market comparison of §7 cuts the curve at the window's end); the final equity; max drawdown; trades entered / skipped per year (no room, per-stock
  limit, cap-bound); max open positions and max gross exposure; per-trade R tail-first (≥5R / ≥10R / ≥20R per 100, max, worst, win rate,
  mean, median, sum) for the deciding set, breakout / EP / both apart, flickers apart, retriggers apart, era A / B apart, and the
  not-mature count with its booked R.
- **Beside:** the whole deciding set (292 walked, the two same-day re-buys out) from 2017-01-27 to 2023-12-15 by year (sparse years
  labelled); the deciding set without flickers; the dated-but-wider-than-cap entries (50) added; the undated entries (open fill, §4)
  added; the 2022-23 tail alone; the deciding account without the panel-clock contradictions (F5, §7).

## 7. THE DECIDING READOUT — the market comparison, and his bar (fixed now)

- **The measure:** `04_vs_market.py`'s formulas, re-implemented line for line in `02_replay.py` (`market_stats`, tested on a synthetic
  curve of known beta and alpha): over the deciding window's sessions, the account's daily returns against QQQ's and SPY's price returns
  (split-adjusted price, dividends excluded: the market's return is understated by ~0.6–1.5% a year, which FLATTERS the account
  against it); total return, CAGR, max drawdown, Sharpe (daily, rf =
  0, × √252), and a daily regression of the account on QQQ → beta, annualised alpha (intercept × 252) and its t-statistic. The curve is
  the deciding account's, reindexed onto every session of the window (1.0 in cash before the first fill; open positions marked at the
  window's last close).
- **HIS BAR, as a threshold — all four, over 2020-01-27 .. 2022-06-14:**
  1. **real alpha:** alpha t ≥ 2.0 against QQQ;
  2. **strong outperformance:** total return above QQQ's total over the same dates;
  3. and above SPY's;
  4. Sharpe above QQQ's.
- **PASS** (all four) → the trades he actually held, traded under his written rules, clear his bar in the one window we can read. The
  gap between Apollo and his record is then **which names to take** (our detector finds 1 of 66 of his breakouts — Track A) and the 82%
  of his book we cannot date (shorts, ETFs, adds). Next: the selection work, on unread data.
- **FAIL** (any of the four) → **our implementation, never the setups** (his 2026-10-23 rule). The beside readings name the part:
  - the panel-exit account PASSES while his-rules fails → **our exit model** (the day-3 third, the trail, the horizon) leaks;
  - the breakout-dated subset PASSES while the whole account fails → **the EP-dated part** (the side of a gap-day position, §1(4)(d);
    any no-minute abstention);
  - both fail, and the breakout-dated subset alone fails → **entry / dating / sizing / data** (the level, the low-of-day stop and the
    too-wide skip, the 1% risk, the dating of retriggers); the panel-clock counts (F5, below) split this one: an account that clears
    the bar without the contradicting fills points at the entry's TIMING (ORH5 against the minute the panel shows he bought), one that
    does not at the dating or the rest;
  - both fail but the whole dated book at the panel's exits is far above the his-rules account → sizing and holding period together.
  Each next step is its own registration; none is pre-decided here.
- **The panel's clock against our fill (F5, beside, deciding nothing; outcome-free inputs from the timeline, F3):** per filled deciding
  trade in the window, the ORH5 fill minute against `flat_clock_on_E` (a full snapshot on E shows him flat LATER than our fill: he
  bought after it) and `first_clock_on_E` (the first snapshot on E shows him holding EARLIER than our fill: he bought before it; every
  fill of the 9 `orh5_infeasible` entries); the same minute is ambiguous and never counted. Printed: the contradicting count by setup
  (all / breakout / EP), the deciding account WITHOUT those trades with its §7 line, and our day-0 stop-outs that come before the
  panel's first holding snapshot on E (our walk is out while his book is in) and on entries first seen after E.
- **What NEITHER outcome shows:** his actual returns (the account compounds our walk of the 14–18% of his book we can date, at one
  sizing point, with no adds and no shorts); that the dated entries were knowable before the open (the panel shows he bought, not when
  in the day); anything about 2022-11 onward or 2025–26 (unread, sealed); the side of EP-dated positions.
- **Beside, deciding nothing:** the same table for the 2 × 2 grid, the panel-exit account, the breakout-dated subset, the set without
  flickers, 2020 and 2021 alone, and the whole 2017–2023 span by year; the same-day band's share at or above his final equity (§3).

## 8. Expectations, written now (a miss changes no rule)

- The deciding account holds many more trades than the 236-call replays (262 vs 236 on the same years) and is in the market more of
  the time (his book carried 8–26 names), so beta reads above the first replays' 0.10–0.15 and the cash drag is smaller.
- Fills: the dated breakouts cross our level more often than his calls did (the panel shows he held them that day), so fewer than 26%
  fail to fill; no EP entry abstains for want of minutes (all fetched before the freeze).
- 2020 is the strongest year; 2021's growth-stock break (Feb–Mar) is the hardest stretch; Q1–Q2 2022 is a bear market with few entries.
- The panel-exit account turns over faster than his rules (the exit window median is 1 session; many holds are 1–5 sessions).
- The breakout-dated subset reads cleaner than the EP-dated (shorts contaminate the latter).
- Most of the curve's growth comes from fewer than 10 trades (his 10-19 point, repeated in every replay so far).

## 9. DATA GATE (STEP 0) and the point-in-time declarations

- **Era A = `cb702_pre_v2`**, passing S0, G1–G7, G9 (`audit_1023/verdict.txt`, pinned; printed by the dry run). **G8 = THIS read's own
  trade list:** the real run writes the `--kind r1` files (`g8_A.tsv`, `g8_B.tsv`: cell = the arm, attempt 0, entry_date = E, exit_j =
  sessions held) and runs `scripts/backtest_data_audit/trade_impact.py` on each BEFORE any number is printed; era A must read
  entered-after-cutoff 0 and holds-past-last-bar 0 (asserted; else STOP, exit 3); era B's two counts are printed beside the headline.
- **Era B = `cb702`:** every export, candidate and fetch-log row dated after 2024-12-31 dropped at read and asserted; no minute file after
  the cut is opened. The deciding window ends 2022-06-14 and every walk ends by 2022-12 (120 sessions), so the cut is never near.
- **Identity breaks:** an entry whose (E − 130, E] window holds a listed break is excluded and counted (era A `symbol_guard.tsv`, era B
  `symbol_guard_B.tsv`); a break after E cuts the forward window at the session before it (the first replay's `cut_at_break`), never an
  exclusion.
- **Minutes (from the fetch logs only, dry run):** four trees — era A `cb702_pre_v2/minutes` (the first replay's walk set), era B
  `cb702/minutes`, the EP tree `cb702/minutes_ep_1023` (196 gap days fetched 2026-10-23), and the pre-freeze EP fetch
  `cb702/minutes_ep_1024` (below). The dry run checks every deciding entry's (E, ticker) against the four logs and the date files. The
  first dry run found every breakout-dated entry covered and 39 EP-dated deciding entries missing (33 era A, 6 era B; 27 inside the
  window; 36 distinct gap days); **those 39 were fetched BEFORE the freeze** into the new folder `cb702/minutes_ep_1024/` (39 ok, 0
  failed; the same fetcher as 2026-10-23; the pinned trees untouched), which the module reads as the fourth tree and pins (`done_EP2`,
  `minutes_EP2_used`). The dry run after F1–F4 reads **0 missing** over all deciding entries (`holdings_1024/replay_missing_minutes.tsv`
  empty); any pair missing at the run would abstain `no_minutes` and be counted — never silently dropped.
- **Point in time:** era A keyed by today's symbol with the alias map (the join's resolutions); era B point-in-time; splits as each vendor
  adjusted them at its fetch; the candidates' level and ADR20 are the detector's values at D; the EP rows' prior close and gap are the
  gap day's own; nothing after a buy day enters a selection — the dating uses only E inside a window the panel fixed.

## 10. Files, the module, its guards, the readings chosen

- **Inputs (pinned; the first replay's pins re-checked at start):** the panel reader's `positions_panel_all.jsonl`; the timeline's four
  TSVs under `apollo_data/cb702/qm_streams/holdings_1024/` (`snapshots`, `entries`, `exits`, `control`); the calendar cache, the lexicon
  and the dedupe map the join used; `candidates_tl_com.tsv` (A) and `candidates.tsv` (B); `ep_events_{A,B}.tsv.gz`; the exports,
  `sessions.txt`, the guard and flags files, the verdict, the four fetch logs; the labels (`labels_joined.tsv`, `matched_events.tsv`,
  `graded_moments.tsv`) for the control; the panel reader's printout `scripts/probes/_705_positions_panel_1024/02_read_all.txt`
  (`panel_read_printout`, F7).
- **Code (pinned):** the panel reader `scripts/probes/_705_positions_panel_1024/01_read_panel.py` (`panel_reader`, F7; committed with the
  freeze); `01_timeline.py` + `test_01_timeline.py` (23 synthetic tests: the full flag, the session windows by clock context, the state
  machine with two-snapshot exits, blips, flickers, the duplicate-upload drop and the clock order, the look-alike guard, the panel clocks
  on E, the dating rule, the control matching); `02_replay.py` + `test_02_replay.py` (16: the entries reader, the same-day re-buy, the
  panel clock against the fill, the output guard, the calendar unification and the QQQ / SPY stitch, the market statistics on a curve of
  known beta and alpha, his bar, the undated open fill, the panel-exit trade, the era-B index shift, one hand-computed account through
  the frozen `simulate`, the single marker line, and an END-TO-END run of the real path on a synthetic world — minute file, daily export,
  fetch log, G8 stubbed — whose breakout trade, deciding account and panel-exit account equal hand-computed values); the frozen `01_replay.py` /
  `02_execution_variants.py` (imported read-only: the loaders, `Event` / `Trade` / `make_trade` / `simulate`, the band draw, G8, the
  line-anchored freeze lock, `adr_pair`), `runner.py`, `registered_read.py`, the cb module (= `runner.EXITPB_MODULE_SHA`), `constants.py`,
  the frozen fit module, `trade_impact.py`.
- **Guards:** (1) the freeze lock — the real run refuses (exit 2) unless every pin the dry run prints, including the sha256 of this doc's
  bytes above the freeze marker taken at run time, sits under the marker (the marker is matched only as its own line, exactly once; any
  edit above it after the freeze changes the hash and the run refuses); (2) it refuses if `02_replay.txt`, a STOPPED file or ANY file
  under `holdings_1024/replay/` exists (`existing_outputs` lists the folder, not only the named outputs); (3) the populations are
  asserted against §2 (entries 1,874 / deciding 294 / same-day re-buys 30, 2 of them deciding / the account 262 / by setup 212-43-7)
  before any minute file is opened; (4) G8 before numbers; (5) per trade the realised R recomputed from the dated legs
  equals the walk's (1e-9) and the legs' fractions sum to 1; (6) a crash after the walk writes a STOPPED file.
- **Readings chosen (B = this registration's choice):**
  - **R1** the LATEST event in the window dates the buy (B; the earliest beside in the control only).
  - **R2** the window cap is 10 sessions (B).
  - **R3** an exit needs two consecutive full snapshots (B; fixed after the first timeline run, §12).
  - **R4** dated flickers decide (B; §12).
  - **R5** the deciding window is the all-1080p dense span 2020-01-27 .. 2022-06-14 (B; from coverage, §2).
  - **R6** the deciding configuration = speed trail at the 30% cap (B; round 3's best reading, fixed before this population).
  - **R7** EP entries take the prior close as the level and our ADR20 at D (B).
  - **R8** the panel exit sells at the close of the exit window's LAST session (B; the latest the panel allows).
  - **R9** undated entries: open fill, one-ADR stop, beside only (B).
  - **R10** era by buy day: ≤ 2022-03-31 era A, ≥ 2022-04-01 era B (B).
  - **R11** the bar's four conditions are a conjunction (B; "at the very least" is his floor, each piece his words).
  - **R12** the look-alike guard's ties: the reader's suggestion, else the nearest % read, else no rename (B; F2, §12).
  - **R13** a same-day re-buy leaves every account; it is listed, not walked (B; F4, §4).
  - **R14** the panel's clock on E is read beside the fill minute, never a filter (B; F3 / F5, §7).
- **Outputs (real run):** `scripts/probes/_705_holdings_1024/02_replay.txt`; under `apollo_data/cb702/qm_streams/holdings_1024/replay/`:
  `trades.tsv.gz`, `g8_{A,B}.tsv` + `g8_{A,B}_impact.txt`, `account_his.tsv` (the daily curves per configuration), `account_band.tsv`,
  `market.tsv` (the §7 table).

## 11. What this does not answer

- **His actual returns.** 18% of his entries are dated; ETFs, shorts, adds, SPACs and the undated 1,040 names are outside the deciding
  account.
- **What he paid.** The panel shows a name, not a fill; ORH5 is our reading.
- **The side of a position.** A short reads as a long.
- **Anything after 2022-06-14 at the deciding level**, and nothing of 2025–26.
- **Whether our detector finds these names before the day** (Track A's question).

## 12. Revisions after the first timeline run (2026-10-24, before the freeze; no outcome seen — only the timeline's own counts)

| change | before | after | why (from the counts and the frames, not from any outcome) |
|---|---|---|---|
| R3 exits | one full snapshot without the name booked the exit | two consecutive full snapshots; a sighting in between cancels (247 drops) | 231 of 2,131 one-frame exits were undone by the very next full frame (174 inside the same stream): the reader's ~2% per-symbol miss, not round trips (SHOP 2020-04-21 alternated inside minutes) |
| R4 flickers | "counted, never replayed" | flagged; a dated flicker decides; the set without flickers beside | 652 of the 1,019 first-run flicker sightings were unanimous reads passing the % check — real one-stream holds (TSLA, SOXL, GME …); dropping dated ones would drop his quick exits, likely his losers; the first definition also flagged a 4-month stream gap (MDGL) as a flicker |
| flicker definition | gone at the next full snapshot | and that exit confirmed within 5 sessions | the stream-gap case above |
| R5 window | "2019–23 where streams exist" (the brief's example) | 2020-01-27 .. 2022-06-14 | 720p alternation (APPS / ASPS) before 2020-01-23; a 5-month gap after 2022-06-14 |

**Revisions after the adversarial review** (`scripts/probes/_705_holdings_1024/verify/review.md`, 2026-10-24, before the freeze; no
outcome seen — the review and these fixes read only the timeline's own outputs, the panel rows and the frames). Counts are the
timeline's; "in window" = deciding entries with E in 2020-01-27 .. 2022-06-14. The positive control is unchanged by all four (29 / 33).

| fix | before | after | why (from the counts and the frames, not from any outcome) |
|---|---|---|---|
| F1 duplicate uploads + clock order | frames ordered video by video (the video's earliest context and clock); a re-uploaded stream replayed after its first copy and the clock ran backwards; 2,977 snapshots in 534 streams; entries 1,897; deciding 296, in window 266 | a frame repeating another video's frame that date is dropped (17 videos on 13 dates, 70 frames; 10 leftover frames join the kept stream); each date's frames ordered by the fitted ET clock across videos; 2,907 snapshots in 517 streams; entries 1,883; deciding 295, in window 265 | 22 video pairs on 13 dates carry identical frames (review check 1b). Gone: QS 2020-12-09 (deciding: copy 1 ends 10:25 without QS, copy 2 restarts 09:26 with it — a phantom re-entry), the undated phantoms GBTC 2020-12-09, ICLN 2021-03-05, CLF 2021-04-19, BNTX 2021-06-15, the 2021-03-08 PLUG / TAN / EYES / TQQQ and 2020-08-10 SPG doubles, and NVAX 2020-08-10, SPXL 2021-09-17, TQQQ / WEAT 2022-06-06 of the same kind. One date (2020-01-06, two different 720p videos) now interleaves by clock |
| F2 look-alike guard | a misread in the last full snapshot before the true name's first sighting opened a phantom entry for the look-alike and dated the true name late | Y one edit from X in that snapshot, flagged by the reader (% mismatch or suggestion X), absent where X first appears → that snapshot reads X; 18 renames, 0 ambiguous; entries 1,883 → 1,874; deciding 295 → 294, in window 265 → 264 | review check 2, by eye: frame `p_QDYyiDbeVmU_a` (09:24 pre-market 2021-11-29) shows LI read as UI → LI is re-dated to [2021-11-26] (undated: held before the 11-29 open, so the 11-29 breakout cannot be his buy) and the UI phantom goes; frame `g_0443` (10:02) shows SQ read as SO → SQ 2021-02-03's bracket becomes (09:42, 10:02] and the SO phantom goes. Also CC → CCJ on `g_0259` 2021-11-05 (CCJ on the frame by eye): CCJ's deciding entry of 2021-10-12 keeps its date, its panel exit moves 11-05 → 11-08, a phantom re-entry goes. The other 15 renames are undated or 2019 (BIL → BILI ×5, U / UI ×4, ASPS → APPS ×3, ID → JD, LX → UX, LX → LK) |
| F3 panel clocks on E | none | `first_clock_on_E`, `flat_clock_on_E`, `orh5_infeasible` in `entries.tsv`; in window (264): held before 09:35 ET 9, flat at an in-session snapshot on E 94 (≥ 10:00: 50, ≥ 10:30: 29), bracketed on both sides within E 53; deciding membership unchanged | review check 3 (a)–(b): the day-level window ignores the clock; read beside the fill minute (F5, §7) |
| F4 same-day re-buy | PLUG 2021-02-03 and SNAP 2021-06-11 each held two deciding entries on one E: the re-buy (after the panel showed him flat at 10:55 / 11:51) walked the first entry's ORH5 fill again | the later entry is `same_day_rebuy`, out of every account and the walk; the deciding account 264 → 262 (deciding walked 294 → 292); 28 undated same-day doubles likewise leave the undated beside account | review check 3 (c) |

<!-- FREEZE -->
## Freeze record

Empty until the freeze commit. The main loop pastes, below the marker line above, every pin `02_replay.py --dry-run` prints under "## Pins
(sha256)", including `doc_body` (the sha256 of the bytes above the marker line), then commits, then runs `02_replay.py` once. Any edit
above the marker after that changes `doc_body`, and the run refuses.

### FREEZE 2026-10-24 (this commit; the one real run follows it)

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
- first_doc_body: aaaadd295aba5a9de534a738410ebe391ac4993637faa7ead0cab78e2b7a9dab
- second_doc_body: 329ac865f814de0909332ff516ea5d52dea525fbef7b5fdcf1c9208a521143fe
- minutes_A_used: d6098818f6d3310d4cf498709cd8f9b574fc42eed201b6d99aa2e455516c9abd
- minutes_B_used: 3d892a04acc4c587507255a2e15d78f570f9f13076cb6719d7173f473d79317c
- minutes_EP_used: 7854578cff34f90e3cfe4038899b9f70a4dcc037cb5e669f5f9d5fe5b5546e6b
- minutes_EP2_used: 9656330d98339fe8a9692f9c85b47a2702e509090e058c266f2473b2607433ce
- doc_body: 69510e1a3092e1c74b9869342a24b624500ca65c814410ae7cf2348f71384b58

## RESULT — the one real run, 2026-10-24 after the freeze commit (printout `scripts/probes/_705_holdings_1024/02_replay.txt`)

- **HIS BAR: PASS.** The deciding account (his trades read off the 'A - Positions' panel, 262 dated buys, his rules with the speed
  trail at the 30% cap) over 2020-01-27..2022-06-14 (602 sessions): total +263.5% vs QQQ +26.5% and SPY +15.6% (price only);
  Sharpe 1.50 vs QQQ 0.48; max drawdown −24.2% vs QQQ −31.8%; beta 0.01; alpha +62.4% a year, t 2.31. By year 2020 +162.7%,
  2021 +46.8%, 2022 −5.8% (QQQ −31.3% in that span). Every beside exit / sizing config also passes (t 2.36–2.67).
- **Selection is real:** his breakout-dated buys alone 3.60× vs the same-day random breakout band (median 1.07×, 95th pct 1.66×,
  0 of 200 draws at or above him). Per trade +1.06R (n = 205), win rate 37%, 2.9 of every 100 trades at ≥ 10R.
- **His own exits (the panel's sell dates, beside):** 14.1× (+1,306%; per trade +2.03R) — his exits beat our rule set by far.
- **Read with it (the registered limits):** only buys still held at the next stream are visible, so trades bought and sold
  between two streams are missing — an upward bias; without the 47 fills that contradict the panel clock the account reads +145.6%,
  Sharpe 1.32, t 1.95 (just under the bar's 2.0). The EP-dated buys alone do not pass (+15.2%, t 0.92, n = 43); 2021 alone has
  t 0.96. Independent recount: running.
