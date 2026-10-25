# #705 — the intraday layer: his 1-minute and 30-minute opening-range entries, intraday stops and the 60-minute exit, read on his panel trades — pre-registration (2026-10-25)

**Status: REGISTERED, NOT FROZEN, NOT RUN.** His ruling (2026-10-24, verbatim, `docs/methodology/operator_shared_notes.md` last section): *"let's continue
with option 1 tmr"* — option 1 = test his INTRADAY rules from his own words before the one sealed 2025-26 test is spent. **Outcome-free:** this
registration read the holdings timeline's three TSVs (names, dates, clocks, flags), the calendar (dates), the type tables, our event DATES, the
minute fetch logs and the minute trees' date-file listings, the previous read's registration and printouts (`cb_reverse_engineer_his_rules_prereg_2026-10-24.md`,
`01_rev_check.txt`, the fit printouts, `verify/recount/recount_check.txt`) and his words. **No price bar — daily or minute — was opened for any
trade; nothing of 2025-26 was opened (sealed).** Every count below was derived by `scripts/probes/_705_intraday_1025/00_pop_fetch.py`
(sha256 `b7b75d56…`) and is printed in its printout `00_pop_fetch.txt` (sha256 `d6bd0f67…`; a copy beside the fetch lists). Measurement and
registration only — nothing here changes or proposes to change a strategy, entry, stop, exit, size, safeguard or live trade state (THE LINE).
The questions of §14 are DECIDED (2026-10-25, main loop, no money, not THE LINE; every change since the review is in §15). The main loop
freezes this doc and the module, runs the fit stages, writes the keyed chosen lines above the marker, pins, and runs the check ONCE.
**Since this registration the minute fetch has run** (its log only was read, no bar file opened: 19,184 pairs ok, 286 empty at the source,
0 failed — `verify/recount_prefreeze.txt` §15). **The module check of 2026-10-25 (15 findings, verdict BLOCK) is applied: every finding is
DECIDED in §15 (rows C1-C15) with its direction; the two gates it found failing or empty on real data (gate (i) on the auction-print basis of
the open and close; the EXIT warm-up floor) were re-set from stated numbers, never from the reading they first cleared (§12, §7a).** The
check read the 2020 fit trades' buy-day minute and daily bars (gate (i)'s preview) and nothing after any buy day; this revision read none.
**The re-check of 2026-10-25 (7 findings N1-N7, verdict FIX) is applied (§15), and one read path it did not name is bounded (X1, §9); that
revision read no price bar.**

**His words this tests.** Entry and stop from his notes, `operator_shared_notes.md` — entry l.1941-1942: *"Enter on the opening range highs.
The opening range highs can be the highs of the first 1-minute candle, the 5-minute candle or the 60-minute candle."* · the 60-minute candle
l.2090-2091: *"(on the 60-minute timeframe the first candle is always only 30 minutes, 9.30-10 AM)"* · stop l.1943: *"Stop is always lows of
the day and stop should not be wider than the ATR or ADR"*. **The exit is NOT in the notes; it is his stream captions** (`qm_streams/subs/`):
FSLY, `cMkRsqvlVHM` (2020-07-14, about 00:52:28): *"I sold half of it 2 days ago when it broke below the 20. Again, the same pattern. 20 EMA on
the 60-minute chart. It undercut a little bit, bounced, and then it broke below. And that's where I sold half. And then I sold the other half
when it took out the previous day's lows yesterday"*; and `YwMoUTd4naQ` (2020-07-13, about 00:04:44): *"fastly i did sell half on friday when
it took out those intraday lows when it broke below and confirmed the breakdown below the right uh 20 ema"*. **E3 is his rule in those words**
(half on the 60-minute close below, the rest on an intraday TOUCH of the prior day's low). **Our readings beyond his words, labelled where
used:** L9 (a 60-minute range break; the closest caption is `tnHw5CKxcH4`, 2020-06-23: *"when he takes out the 60-minute range that's my
ad[d]"*), S10, E1, E2 and E4. *"60-minute lows to stop"* (notes l.2592) is the ruling record's paraphrase of option 1, not his line. Other
captions say *"20ma"* on the 60-minute chart (`GVTyWZCJPn0`, `kITl8W5eaEA`), so the EMA against a plain average is an open reading (§7a).
**His rule for a miss (2026-10-23):** a backtest that does not reproduce his profit is a defect in OUR implementation or interpretation, never a
finding that the setup does not work.

## 0. In plain words

- **What the previous read left.** Inferred from his 2020 trades and checked on 2021-22: WHICH stocks he buys is recoverable from a daily scan
  (SELECT PASS: 65% of his unseen buys at one stock in five). WHERE he buys is not any daily or 5-minute level we tried (ENTER FAIL: the 5-minute
  opening-range high was first crossed inside his buy window on 37% of trades; a random price from the same day managed 32%). No fixed DAILY
  price level is his stop (STOP INCONCLUSIVE: every level held through on 39-99% of the trades where price crossed it — 39-68% on the four
  daily-style levels S1-S4, after the era-B fix). His exit edge lives in
  his dated breakout trades (his exits 2.62× against ours 1.40×), not in the no-event buys the daily exit rule was checked on (EXIT VOID).
- **What this read adds — only levels his own words name and the previous read never scored:** the 1-minute opening-range high; the 30-minute
  high (his "60-minute first candle", 09:30-10:00); a later 60-minute bar's high (a 60-minute range break); for the stop, the low of the day at
  the buy minute, the 09:30-10:00 low and the prior 60-minute bar's low, each as a TOUCH, a daily CLOSE below and a 60-MINUTE CLOSE below; for
  the exit, the FSLY rule — a 60-minute close below the 60-minute 20-period average (half or all), the rest on the prior day's low.
- **The headline before any run: the untouched years are too thin to decide the entry or the exit, and only partly untouched.** The years no
  read has scored — 2019, 2023, 2022 after June 14, January 2020 before the 27th — hold **89 of his trades: 62 undated and 27 dated by our
  events.** The 62 undated are clean: no bar after their buy day was opened beyond one aggregate account (the holdings replay). **The 27 dated
  are not:** the previous EXIT fit walked the daily paths of the 23 with exits, and the exits study recorded our stop, the prior-low and the
  moving-average markers for them and for the four still held (§9). For the entry they hold **17 usable buy windows (9 non-flicker, 8
  flickers)** after broken clocks are dropped: a share read on 9 windows carries ±33 points. For the exit, 23 dated trades: a profit ratio on
  20 trades is one trade's noise. **So (DECIDED, §15):** 2021-22 decides ENTER (its 43 undated non-flicker windows; n = 40 records expected) and EXIT (its 111
  dated trades); the untouched years are a sign veto on both; STOP decides on the 62 undated untouched trades (about 58 records; about 26
  traded through on the low of the day at the 2021-22 rate, so a too-few reading is live). The 2021-22 leakage is disclosed with its bound
  (§1c).
- **What it costs.** One minute fetch of **19,470 ticker-days over 1,005 dates** (the hold of every trade plus ten sessions before each buy for the
  60-minute average's warm-up and twenty after his sell for the exit rule to finish). **It has run** (the log: 8.0 minutes, 1,032 requests,
  19,184 ok, 286 empty at the source, 0 failed; exactly the list): `/Users/alvinfung/apollo_data/cb702/minutes_intra_1025/`.
- **What changes nothing.** No rule, threshold or size moves. The sealed 2025-26 test stays unspent until this read's check has run; its branch
  table (§11) takes the inferred entry / stop / exit only where a check PASSED and his words' registered reading everywhere else.
- **Action from him:** none — the fetch this version asked permission for has run (§11).

## 1. The four questions of the standard

1. **Decision served:** whether the intraday rules in HIS OWN WORDS — the 1-minute / 30-minute opening-range high to enter, the low of the day
   (at the buy, at 10:00, of the prior hour) to stop, the 60-minute 20-period average to exit — reproduce his dated decisions where the daily
   and 5-minute readings did not; so that the sealed 2025-26 strategy test runs with the entry, stop and exit that come closest to his, and the
   remaining gap is named (selection, entry timing, stop or exit).
2. **What would change it:** the per-stage bars of §5-§7, fixed here before any bar; the sealed one-shot afterwards (§11).
3. **Population:** §2 — the previous registration's sets as they stand (fit 2020; 2021-22 deciding ENTER and EXIT), plus the untouched
   years (STOP's deciding set; the sign veto of ENTER and EXIT), with the clock-sanity rule the untouched frames forced (§2c).
4. **What would make this wrong:**
   - (a) **Survivorship, the panel's OCR, a position's missing side, a window that is not a day, a clock that bounds a minute and not a price** —
     inherited unchanged from the previous registration §1 (a)-(e); every rule here is a rule for trades he held to at least one stream frame.
   - (b) **The untouched years are thin AND dirty.** 2019 has 39 stream days (2020: 216); its frames carry the only 21 misread clocks the
     previous guard found; 3 of its 10 undated non-flicker in-session buy windows have a flat frame AFTER the first frame or a zero width (APPS
     2019-10-01 reads 10:48 → 08:58). January 2020's six in-session windows all carry a flat frame at 09:08 labelled in-session. §2c drops
     these by rule, counted; nothing is "asserted away".
   - (c) **2021-22 decides ENTER and EXIT (DECIDED, §15) and is clean for the new readings but not virgin.** Its bracket minutes were opened
     and the 5-minute high, the first-hour high, the prior high, the base high, the open and the prior close were scored there; its daily
     bars were walked for eight daily stop levels and a daily exit list. **What was exposed for ENTER, exactly:** aggregates only — the six
     level shares and hit counts on the 41 undated windows and the random-price control's 31.7% feasible / 85.9% hit-or-ballpark
     (`01_rev_check.txt` l.24-34), plus L1 on the 20 dated windows (60.0% / 90.0%). No per-trade ENTER file exists for 2021-22 (`reverse/`
     holds the fit's `enter_fit_trades.tsv` only); the per-trade buy-window clocks are in `dryrun_clocks.tsv`; and per-trade, the dated rows'
     `fill_src` in `check_stop_trades.tsv` and `exit_fit_trades.tsv` (`orh5` / `orh5_too_wide` / `close_proxy`) says whether the 5-minute
     high filled that SESSION — a session crossing, not a window crossing. **The bound:** the new levels are unread and nested in PRICE
     between old ones (the 1-minute high ≤ the 5-minute high ≤ the 30-minute high ≤ the first-hour high); whether a level's first crossing
     falls inside the window is not monotone in its price, so the known shares (5-minute 36.6%, first-hour 22.0% feasible) bound the new
     shares only loosely — but the reader is not blind. **DWAC 2022-01-31** (flat 09:26) was scored in
     the previous 41 and is now dropped by §2c. Every design choice made after those results were seen is listed in §9 **with the direction
     it moves a PASS** — two make a PASS easier (§9).
   - (d) **The rolling 60-minute level fires more often than a fixed price.** A level that resets every hour has more chances to be "first
     crossed inside the window" than one price; a fixed-price control under-states its chance rate. A second control — the same level read
     inside a randomly placed window of the same width — is added for every level (§3).
   - (e) **The 60-minute exit needs bars after his sell.** The chosen rule may sell later than he did; its walk is cut 20 sessions after his
     sell window and booked at that close, flagged `cut_at_tail` and counted — a mark at the tail close, direction unknown (on a trend that
     runs past his sell it flatters the rule); a walk the frozen 120-session horizon or the export's last bar ends first is the same kind of
     mark (`cut_at_horizon` / `cut_at_data_end`, §7c). Too many such marks make the recovery INCONCLUSIVE (§7c).
   - (f) **Thin minutes.** Twenty buy days have no minute bars at the source (the previous §12's list; seven are AXNX in January 2020 —
     inside the untouched dates but not one of the 89 trades). The fetch since run logged 286 more pairs empty at the source (fit 2020 213,
     the untouched years 58, 2021-22 15), and four scorable ENTER windows have no buy-day bars (HTZ 2020-07-22, OAS 2020-04-30, U 2020-07-24,
     FBR 2019-10-22 — the first three on the fit, the last an untouched-year flicker); they read `no_minutes`. A bar missing inside a 60-minute
     window makes the window a no-bar for the average, as the runner's hourly entry already treats it.
   - (g) **The era-B calendar index** (buys on or after 2022-04-01: all of 2023, 7 of the 2021-22 dated, 8 of the undated): the previous module
     took the sell-date index from the full calendar and the buy-day index from era B's own export, so eight check trades carried sell dates
     about 1,440 sessions late (the recount's one MISMATCH). Eighteen of the 89 untouched trades are era B. Fixed by rule in §11, tested.

## 2. POPULATION — the previous registration's sets as they stand, plus the untouched years

**The timeline is taken as is** (1,874 entries, 13 initial, 1,861 non-initial, 2,907 snapshots in 517 streams; the holdings pins). The buy day of
an undated entry is its window start. **The §2b gate of the previous registration is applied unchanged and in the same order:** the type gate
(CS / ADRC / no type row; LAZR override), inverted windows out, same-day re-buys out. Every set below equals the previous registration's count
where it had one (asserted by the new module's dry run against this section AND against the previous dry run's 63 counts). In the table,
n = trades.

| set | n | non-flicker | in-session buy windows (non-flicker) | exits known | era B | role here |
|---|---|---|---|---|---|---|
| **fit, dated 2020** (2020-01-27..12-31) | **149** | 104 | 32 (24) | 149 | 0 | ENTER / STOP / EXIT fit |
| **fit, undated exact-day 2020** (flickers included) | **304** | 188 | 94 (59) | 304 | 0 | ENTER (non-flicker decide, flickers beside) / STOP fit |
| **2021-22 dated** (2021-01-04..2022-06-14) | **111** | 68 | 20 (13) | 111 | 7 | **EXIT check (decides, §7)**; STOP / ENTER beside |
| **2021-22 undated exact-day** | **226** | 145 | 63 (44) | 226 | 8 | **ENTER check (decides: the 43 non-flicker windows after §2c, expected 40 records)**; STOP beside; EXIT hit-rate beside |
| **untouched: 2019 dated** | 16 | 13 | 1 (1) | 16 | 0 | the virgin block, dated (daily paths read, §9) |
| untouched: 2019 undated exact-day | 44 | 26 | 18 (10) | 44 | 0 | the virgin block |
| untouched: 2023 dated | 7 | 7 | 0 | 3 (4 still held at the last stream, 2023-12) | 7 | the virgin block, dated (daily paths read, §9) |
| untouched: 2023 undated exact-day | 8 | 5 | 3 (2) | 8 | 8 | the virgin block |
| untouched: 2022 after 06-14 | 2 dated + 1 undated | 3 | 0 | 3 | 3 | the virgin block |
| untouched: 2020 before 01-27 | 2 dated + 9 undated | 11 | 7 (7) | 11 | 0 | the virgin block (the 2 dated walked by the previous EXIT fit — §9) |
| **the virgin block, all** | **89 = 62 undated + 27 dated** | 65 | 29 (20) → **17 (9) after §2c** | 85 | 18 | **STOP check: the 62 undated decide, the 27 dated beside; ENTER / EXIT sign veto (§5d, §7d)** |
| listed, never walked: 2017-18 | 4 | 4 | 0 | 4 (held ~250 sessions: one stream a year) | 0 | listed |

**2a. Streams per year (why the untouched years are thin):** 2017: 11 videos / 11 session dates · 2018: 1 / 1 · **2019: 39 / 39** · 2020: 218 / 216 ·
2021: 177 / 177 · 2022: 59 / 59 · **2023: 12 / 12**. A buy window is bounded by frames; with one stream a week the windows are wide (2019 undated:
held to the sell window's last session a median 13 sessions; 2020: 5) and the certain-held sessions few.

**2b. The buy windows' clocks (ET; what each level can exist at).** A level is scored only once it exists at the first frame showing him holding:
the 1-minute high from 09:31, the 30-minute high from 10:00, a later 60-minute bar's high from 10:00 (its value changes at 11:00, 12:00 …). Of
the 2021-22 in-session windows, **43 of the 44 undated non-flicker and 17 of the 20 dated close at or after 10:00** (the 30-minute high exists on
nearly all of them); 14 of the 44 open at or after 10:00 (the whole window sits after the first 60-minute candle). On the fit, 48 of 59 undated
and 19 of 32 dated close at or after 10:00. Nine trades were held before 09:35 (the previous list, KOLD out): the 1-minute high exists for the
seven first seen at 09:31-09:34 (TSLA 2020-04-14, UAL 05-27, DXCM 07-29, PINS 07-31, SHOP and TTD 08-26, ROKU 09-15) and not for LAC and TSLA
2022-04-21 (first seen 09:30).

**2c. Clock sanity — a rule the untouched frames forced (new; counted, never asserted away).** An in-session buy window is scorable only when
(i) the flat frame's context is in-session AND its clock reads 09:30 or later (the frames of ARWR / AVLR / ITCI / FCEL / LX / NTCT 2020-01-02 read
09:08 with an in-session label; FBR and JCP 2019-10-23 read 09:24 / 09:25), (ii) its width is positive (APPS 2019-10-01 10:48 → 08:58; ASPS
2019-10-17 and JCP 2019-10-23 zero), and (iii) neither frame is a misread clock under the previous guard (8) (|raw clock − fitted clock| > 2 min;
21 frames, all 2019; APPS 2019-10-01 is one — already out under (ii)). Applied in that order; dropped windows read `flat_before_open` /
`zero_width` / `clock_misread` (the derivation's printout, l.104-116 and l.147-148, lists every one by name). **Effect:** the virgin
block's 29 in-session windows → **17 scorable (9 non-flicker: ASPS 10-03, JCP 10-07, RLGY 10-10, CCS 10-17, BABA 11-01, LX 11-15 of 2019; APT
2020-01-23; CVNA 2023-05-18, AI 05-19; 8 flickers)**; 2021-22: one undated window out (DWAC 2022-01-31, flat 09:26 by the clock) → 43 + 20; the fit: one
dated and one flicker window of zero width out → 31 + 59 (+34 flickers). The dry run prints every dropped window by name.

**2d. His sells (EXIT's unit).** Dated 2021-22: 111 with exits, sell window one session wide on 80 of the 101 of 2021. The virgin dated: 2019's
16 windows span 1-14 sessions; GSIT and GTLB 2023 span 121 (a stream gap June-November 2023) and leave the hit rate (windows > 20) while staying
in the accounts.

## 3. THE CONTROLS (deciding nothing; each names the failure it guards)

- **The random-price control of ENTER (kept from the previous registration, identical draws):** 200 seeded closes of random minutes of the
  session (seed 702, key `rev|minute`), each scored as a level — feasibility and hit-or-ballpark. On the 2021-22 undated windows it read 31.7%
  feasible / 85.9% hit-or-ballpark; those numbers are known and are the floor there. **"Identical" is mechanical (C6):** one generator, the
  draws taken in (buy day, eid) order over the previous read's own population — its 20 dated in-session windows (7 of them flickers) + its 44
  undated non-flicker windows (DWAC 2022-01-31 among them), 64 windows, the records with minutes — so the check's draws are exactly
  **replayed over the previous read's population**; the dated flickers and DWAC are scored and never deciding (§5d). Gate (vii) at the check: the control's
  mean shares on the previous 41 undated records must re-read 31.7% / 85.9% at one decimal, else the draws are not the previous read's and the
  stage stops (§12).
- **The shifted-window control of ENTER (NEW — guards §1d):** for each scorable trade and each level, the trade's own window width is placed at
  200 random starts, uniform over [the level's existence minute, the session close − width] (the close = 16:00, or 13:00 on an
  `H60_EARLY_CLOSE` day); the draw key is `f"intra|bracket|{eid}|{level}|{draw}"` (seed 702). A width larger than close − existence →
  `no_room`, abstains, counted. The level's feasibility and hit-or-ballpark inside the shifted window are scored exactly as inside his. For
  a fixed price this control and the first agree in expectation; for the rolling 60-minute level only this one is fair. **Stated bias:**
  starting the draws only once the level exists, while his own windows can open before 10:00 (and then read `no_level_yet`), lifts this
  control against his windows — a conservative control. **Every level's FEASIBLE share must beat BOTH controls by 15 points; hit-or-ballpark
  is an absolute floor of 70% only** (DECIDED, §15 F1: the random-price control already reads 85.9% hit-or-ballpark on 2021-22, so a +15
  margin there would need 100.9%).
- **The held-through controls of STOP (kept):** two ADR20 below the fill and the 50-day average — never "his stop".
- **The trivial exits of EXIT (kept):** sell at the close of session 3; sell on the first red close from session 2 — the floor for the hit rate.
  **Plus the previous read's daily list** (a close at or under cost; a close half an ADR under the 10-day and under the prior low; a close under
  the 20-day after session 3), which hit his sell session on 37.7% of the undated 2021-22 trades and is IN-SAMPLE on the dated 2021-22 — printed
  beside as the daily benchmark the 60-minute rule must beat on the hit rate.
- **The ambiguity control of WHY (kept):** a phrase window naming two qualifying tickers is dropped.

## 4. THE INFERENCE CHAIN — order, and what each stage holds fixed

SELECT is NOT re-run: its PASSED condition set (ADR20 ≥ 4.26%, not down more than 5.8% over 60 sessions, a 52-week high within 233 sessions) is
carried as the sealed test's universe filter. ENTER → STOP → EXIT run as before, each on its own fit set, frozen, checked once.

| stage | holds fixed | produces | consumed by |
|---|---|---|---|
| ENTER | the buy day; the window; the levels of §5 | the level he buys at (one of L7-L9) and the inferred price | STOP (the fill, the fill minute, the R unit), EXIT (R so far) |
| STOP | the chain's fill (the chosen level where feasible, else the REGISTERED fill — ORH5 where it filled / the open for undated — flagged `fill_fallback`, counted) | the tightest intraday (level, variant) he rarely holds through | EXIT (the stop the chosen account follows); sizing |
| EXIT | the chain's fill and stop | the FSLY variant (E1-E4) | the sealed test |

If a stage FAILS, reads INCONCLUSIVE (by bar or by size) or VOID, the next stage runs on the REGISTERED reading (ENTER → ORH5 / the open; STOP →
the low of the day at the fill / one ADR20 for undated; EXIT → the speed trail) and says so; nothing is re-fit.

## 5. ENTER — the opening-range levels his words name and the previous read never scored

**5a. Levels (three new, fixed; the six old ones printed beside as re-reads).**
- **L7 — the 1-minute opening-range high:** the high of the 09:30 minute bar (minute index 0). Exists from 09:31. No bar at minute 0 →
  `no_bar_0930`, counted.
- **L8 — the 30-minute high** (his "60-minute first candle", 09:30-10:00): the maximum high over minute indices 0-29. Exists from 10:00.
- **L9 — the prior completed 60-minute bar's high (a 60-minute range break; our reading beyond his words, §0):** bars are the runner's clock-anchored windows [0,29], [30,89],
  [90,149], [150,209], [210,269], [270,329], [330,389] (`runner.h60_windows("h60", early_close)`; on the early-close days (20 in the runner's list, 17 inside this read's dates; 3 are 2025, sealed and unused) the last window is
  [150,209] and minutes ≥ 210 are dropped first, `h60_trim`). During bar k ≥ 2 the level is bar k−1's high; the trigger is the FIRST minute of the
  session (from 10:00) whose high exceeds the then-current level. During 10:00-11:00 the level IS the 30-minute high, so L9 differs from L8
  only from 11:00 on, and L9's trigger is never later than L8's. Exists from 10:00. **One bar, never "any bar"** (§1d).
- **Dated trades keep the previous convention:** the level is max(the intraday level, the candidate row's pivot) for breakout rows (the holdings
  replay's ORH5 reading); EP and undated rows use the intraday level alone; the raw level is printed beside.
- **"Buy as the daily chart starts to break out"** = the prior session's high (L2) and the base high (L3): scored by the previous read (2021-22
  undated: 22.0% and 7.3% feasible) — re-reads, printed beside, not re-added.
- **Beside, not a level: "any opening range"** — feasible when the first crossing of ANY of L7 / L1 / L8 lies inside the window. Its control
  is the union of the three levels' own controls: per draw index d, the union is feasible when any of the three levels is feasible under
  its own draw d (each level keeps its own key), for each of the two controls (he said *"you can use whatever timeframe"*).

**5b. Feasibility, HIT, BALLPARK — unchanged (R3):** feasible = the level's first crossing minute lies in (flat_clock, first_clock]; HIT = the
level inside the window's traded range [lowest low, highest high]; BALLPARK = within 0.25 ADR20 of the nearer edge; scored on in-session
windows that pass §2c; a window without minute bars → `no_minutes`, counted. A level that does not exist at first_clock → `no_level_yet`.

**5c. Fit:** the 2020 in-session windows after §2c — **31 dated + 59 undated non-flicker decide (34 flickers beside)**; a record needs 20 bars
before the buy day (the previous floor; the previous fit kept 89 of 91). **Chosen level** = the highest feasible share among L7-L9 on the deciding
fit windows (ties → L8, the article's own hourly entry). The old L1-L6 are printed on the same windows for scale (known: L1 36.0% feasible on 89).

**5d. Check — DECIDED (§15 Q1): 2021-22 decides; the untouched years are a sign veto.**
- **Deciding set = the 2021-22 UNDATED NON-FLICKER in-session windows that pass §2c: 43 windows; expected n = 40 records** after the 20-bar
  record floor (the previous floor took 3 of these 44 windows; DWAC 2022-01-31, scored among the previous 41, is now out by §2c). All 43
  have buy-day minute bars (the fetch log), so only the record floor can bite. `no_level_yet` counts as infeasible in the denominator, as
  L6 did (one window closes before 10:00, so L8 and L9 carry it as a non-crossing). **At 39 records or fewer → INCONCLUSIVE-by-size (the
  previous 40 floor, not moved now that the count is known)**, and the stage carries the REGISTERED fill, as on a FAIL.
- **PASS:** the chosen level's feasible share ≥ 50% AND ≥ each control's feasible share + 15 points (the random-price control read 31.7%
  there, so its bar is 46.7%, under the 50% absolute bar; the shifted-window control is unread) AND hit-or-ballpark ≥ 70% (a floor only;
  §3). **FAIL** otherwise; falsifier: no new level ≥ 50% feasible. Every share is printed with its 95% binomial interval.
- **The sign veto (the untouched years):** on the 9 non-flicker untouched windows (17 with flickers; flickers beside), a PASS reads
  INCONCLUSIVE when the chosen level's feasible share there is STRICTLY below the larger of the two controls' feasible shares on the same
  windows. Fewer than 5 scorable untouched windows → the veto abstains, said so. **Its false-veto rate, stated now:** with a true share of
  50% on n = 9, about 9% against a control at 32% (2 or fewer of 9) and about 25% against a control at 40% (3 or fewer of 9).
- **Beside, not deciding:** the 20 dated 2021-22 windows (they use max(level, pivot) and were known to read higher — L1 60% dated against
  37% undated — so admitting them after that was seen would make a PASS easier; they stay out; the 7 dated flickers among them are scored in the
  draw population of §3 and printed with the 20) and the 19 undated flickers, on L7-L9 under both controls and the same bars.
- **Beside, both populations:** L1-L6 (re-reads), the "any opening range" union, the pre-market-flat windows (populations 41 dated + 55
  undated on 2021-22, 41 + 58 on 2020; the previous read scored 52 and 57 of the undated — for the opening-range levels the crossing is NOT
  by construction, unlike L4 / L5, but the window is the whole morning and the controls run high; printed, never deciding — §14 Q7), the
  held-before-09:35 seven on L7, and the pre-market first sightings degraded to "crossed that session".
- **Expected scorable n per level on the deciding set:** 40 on each of L7, L8 and L9 (the one window closing before 10:00 is a non-crossing
  for L8 / L9, not a drop). On all 63 windows of 2021-22 (beside): L7 on 63, L8 and L9 on 59 scorable before the record floor (3 dated +
  1 undated windows close before 10:00).

## 6. STOP — intraday lows, as a touch, a daily close and a 60-minute close

**6a. Levels (two new; two kept because his words and his FSLY sell name them) × three variants.**
- **S1** the low of the day up to the fill minute (the registered stop; "lows of the day" at the buy) — read before as T and C.
- **S3** the prior session's low — read before as T and C.
- **S9 — NEW: the 09:30-10:00 low** (the first 60-minute candle's low: "lows of the day" for a 10:00 buy). Read at the READ MINUTE (below);
  a read minute before 10:00 → the candle is incomplete → S9 = S1, flagged `S9_is_S1`.
- **S10 — NEW, our reading beyond his words: the low of the last COMPLETED 60-minute bar before the read minute** (the runner's windows);
  a read minute inside the first bar → S10 = S1, flagged `S10_is_S1`.
- **The read minute:** the fill minute; but on a trade whose buy day carries an in-session holding frame, S9 and S10 are read at that
  frame's clock (first_clock — the latest minute he could have bought). Under the open fill (the undated) and ORH5 fills (the dated, nearly
  all before 10:00), S9 and S10 would otherwise be copies of S1 on almost every record.
- **Variants:** **T** an intraday touch (the session's low ≤ the level) · **C** a daily close below · **H — NEW: a 60-minute bar's close below
  the level** (the bar's close = the close of the last minute bar in its window; no bar in the window = no close). Cells: {S1, S3, S9, S10} ×
  {T, C, H} = 12; the four old cells (S1-T, S1-C, S3-T, S3-C) are re-reads on 2021-22 and on the fit; on the untouched undated trades they
  are new, on the untouched dated trades they are not (§9). The controls S8 and the 50-day run under T, C and H.
- **The buy-day certainty rule (NEW — the frozen `held_through` is NOT imported unchanged).** The frozen code (`01_rev_frozen_e908253f7405.py`
  l.2478-2503) calls any buy-day touch after the inferred fill minute CERTAIN and never compares it with the frames: on the 2020 STOP fit,
  83 of the 112 certain S3-T calls are buy-day touches, and 51 of those 83 have an in-session FLAT frame after the fill minute (S1-T: 23
  buy-day of 92 certain, 6 with a flat frame after the fill). The rule now, for T and for H (on the bar's close minute): **a buy-day event
  at or after first_clock is certain; between the later of (fill minute, flat_clock) and first_clock it is unresolved; at or before
  flat_clock it is not a held-through event and the scan goes on to later sessions.** No in-session holding frame on the buy day → every
  buy-day event is unresolved. **The first H bar on the buy day** is the first bar that closes after max(fill minute, flat_clock).
- **Held-through:** H_cond(level, variant) = trades where the level was traded through on a session he CERTAINLY held ÷ trades where it was
  traded through on any session ≤ exit_hi; H_all over all trades (the previous §7b, with the buy-day rule above). **Certainty on exit_lo
  under H:** the bar whose close is below must close before the last in-session frame's clock that shows the name (as T uses the touch
  minute); under C a frame after 16:00. A 2023 trade still held at the last stream contributes its certain sessions up to its last frame
  (`last_j`), no denominator event.
- **"His stop"** = the tightest (level, variant) with a positive median width, ≥ 20 trades traded through on the fit, and H_cond ≤ 10% on the fit
  (R6, R16); S8 and the 50-day never. Sizing and realised risk under H as under C (the previous §7c): sized on the level's distance, the exit
  booked at the next minute's open after the bar's close (the day's last bar → the next session's open). **An H stop can realise well beyond
  −1R** (a bar's close, or the next open, can sit far below the level): per cell, the share of stop-outs beyond −1R and beyond −2R and the
  worst one are printed. Nothing is resized (§11).

**6b. Fit:** dated 2020 (149) + undated exact-day 2020 (304, flickers included), under the chain's fill. **Check — DECIDES: the 62 UNDATED
untouched trades** (records after the 50-bar floor printed; expected about 58 at the 2021-22 rate, 212 of 226). **The 27 untouched dated
trades are beside**: their daily paths, S1-T / C and S3-C were read by the previous EXIT fit and the exits study (§9). **PASS:** the chosen
cell keeps H_cond ≤ 15% on the deciding set. **The chosen cell must have ≥ 20 trades traded through there, else INCONCLUSIVE-by-size** (on
the 2021-22 undated set the low of the day was crossed on 98 of 212 — about 45% — so about 26 here for S1-T, fewer under the buy-day rule
and under H: a too-few reading is live). **For S9 / S10:** the dry run counts, from clocks alone, the deciding records with S9 ≠ S1 and with
S10 ≠ S1 (the read minute at or after 10:00 / after the first bar); if the chosen cell is S9 or S10 and fewer than 20 records differ from
S1, STOP reads INCONCLUSIVE-by-size. **Expected, said now:** few untouched undated records carry an in-session holding frame after 10:00 on
the buy day, so S9 and S10 are near-certain INCONCLUSIVE-by-size there and only the H variant of S1 / S3 is new. Falsifier: every cell >
30% → his stop is not a fixed intraday level either (discretion, time, a mental stop wider than any of these). **Beside, not deciding:** the
ordering of the 12 cells by H_cond against the fit (Spearman, ties at average rank, cells that equal S1 on more than half their records
left out) — beside only, since part of the order is set by construction up to the auction difference (the daily close is the closing auction
print, the last 60-minute bar's close is the 15:59 minute's last trade — median 0.03% apart, p90 0.19%, one 4.9% day on the 88 ENTER-fit buy
days — so a daily close below a level implies the last bar closes below it except inside that band: the C events sit inside the H events up
to the band, which sit inside the T events; and S9 / S10 = S1 ties); the 2021-22 undated (226 / 212 records) on every
cell — the four old cells known there (S1-T 39.2%, S1-C 41.5%, S3-T 68.0%, S3-C 57.8% after the era-B fix, OLD certainty rule), the eight
new ones unread — and the 2021-22 dated (111) on every cell; the non-flicker and "untouched-by-a-dated-path" subsets as before. Re-buys
printed apart.

## 7. EXIT — the 60-minute rule in his FSLY words, on the dated breakout trades where his exit edge lives

**7a. The 60-minute 20-period average.** On the clock-anchored 60-minute bars of §5a (7 per full session, 4 on an early-close day; a window
with no minute bar is no bar). EMA with weight 2/21 on each bar's close; seeded with the plain average of the first 20 bars of a **10-session
warm-up before the buy day (70 bars; 67 when one early-close day falls inside it)**. **A trade abstains (`ema_thin`, counted) unless at least
20 seed bars plus 45 post-seed bars — 65 — exist before its first armed bar (C3, DECIDED 2026-10-25)**; after 45 bars the seed keeps
(19/21)^45 = 1.1% of its weight (1.1% of the seed's error, not of the price). **Why 65 and not 70:** the fetch holds exactly ten sessions
before each buy, so a 70-bar floor equalled the warm-up with no slack — one early close inside it (13 of the 111 deciding trades, bought after
2021-11-26; 9 of the 149 fit trades) made the trade `ema_thin` for any fill before about 12:00, and §7c's 10% clause was exceeded by
construction (11.7%). At 65 every logged warm-up of the deciding set clears the floor with two bars of slack (the dry run counts, from the fetch
logs and the calendar alone, the trades whose **warm-up alone under the 65-bar floor**: deciding 0 of 111, fit 0 of 149, virgin dated 0 of 23;
67-bar warm-ups 13 / 9 / 0; the buy day's pre-fill bars only add to these); a silent hour inside the warm-up costs one bar, and an `empty`
session seven — both counted as `ema_thin` where they bite. **Residual (N7):** that count assumes 7 bars per logged session, and thin hours
are not measured before the run, so the 13 deciding trades at 67 bars carry two bars of slack — three silent hours inside such a warm-up make
the trade `ema_thin`, and the abstention counts in §7c's clause. Each trade's residual seed weight is printed. A close "below" = the bar's close <
the EMA. **Beside, deciding nothing:** the same rules on a 20-bar plain average (other captions say *"20ma"* on the 60-minute chart, §0).

**7b. Variants (four, fixed; the ONLY fit is choosing among them).** **E3 is his FSLY rule in his words; E1, E2 and E4 are our readings
beyond them** (E2's daily close contradicts his *"took out"*; E1 and E4 are simplifications). Armed from the first completed 60-minute bar
after the fill minute (a close fill arms on the next session's first bar); **no leg's event counts before the armed bar completes — on the
armed session, whatever its day, a prior-low touch counts only after that bar's close minute, and E2's daily-close leg from the armed session
on (C15)**; the chain's stop pre-empts any leg. **"Undercut, bounced, then broke below":** an undercut is a wick; E1's trigger is the first
60-minute CLOSE below the 20-EMA (a bar whose low pierces the average while its close holds is no trigger); a "second close below" trigger is
printed beside, deciding nothing.
- **E1** all out at the first 60-minute close below the 20-EMA — sold at the next minute's open (the day's last bar → the next session's open).
- **E2** half at E1's bar; the rest at the first DAILY close below the prior session's low (sold at the next open). If that daily close
  comes before E1's bar, all shares leave at it.
- **E3** half at E1's bar; the rest when the prior session's low is TOUCHED intraday (sold at the level; a gap below it → the open). If the
  touch comes before E1's bar, all shares leave at that touch.
- **E4** all out when the prior session's low is touched intraday (no average).
- **The panel sees the LAST share leave.** Hit = the predicted LAST leg's session inside [exit_lo, exit_hi], on windows ≤ 20 sessions. Chosen on
  the fit by hit rate (ties → fewer legs: E1, E4, then E2, E3). **Printed beside the last-leg hit rate:** the half leg's hit rate (E1's bar's
  session inside the window) — on dated 2021-22 only that part is out-of-sample (§7d).

**7c. Accounts and the bar (the exits study's measure, kept).** Through the frozen `simulate` at cap_30: **ours** = the speed trail under the
chain's fill and stop; **chosen** = the variant under the chain's fill and stop (the half leg = half the shares at its price); **his** = the panel
exit at the close of exit_hi, no stop (the stop sets his size only). Recovery = (ln chosen − ln ours) ÷ (ln his − ln ours). **PASS ≥ 0.25;
falsifier < 0.25** → the 60-minute exit in his words does not close the gap on these trades, and the hit rate says whether it at least SEES his
sell day; **VOID if his ÷ ours < 1.25.** The chosen walk is cut at exit_hi + 20 sessions, booked at that close, `cut_at_tail`, counted (§1e: a
mark, direction unknown). A walk the frozen 120-session horizon ends first (a sell window longer than it: GSIT and GTLB 2023, exit offsets 126
and 123) is `cut_at_horizon`, and one the export's last bar ends first `cut_at_data_end` — the same kind of mark, counted with the tail cuts
and printed by name; 'his' is that mark there (C11). A walk a missing session or an identity break shortened (`mark_hole` / `mark_break`,
mid-walk or at the tail) is counted with them (N7: a cut is a cut whichever bound made it). **If `cut_at_tail` + `cut_at_horizon` +
`cut_at_data_end` + `mark_hole` + `mark_break` + `ema_thin` + no-bar abstentions together exceed 10% of the deciding trades, the recovery reads
INCONCLUSIVE** (the counts printed); the recovery without the cut and marked trades is printed beside. A trade-resampled 90% interval of the recovery (1,000 draws, seed 702, key `intra|boot`) is printed as information,
not a bar. The sell window's width (the ≤ 20-session rule of §7b) is read on the record's own calendar, as every offset is (§11c, C12).

**7d. Fit:** dated 2020 (149; every one described by the exits study at the daily level — disclosed; their 60-minute state unread). **Check —
DECIDES: dated 2021-22 (111).** This is the set the ask names (*"the dated breakout trades where his exit gap lives"*). **Which line decides:**
the CHAIN's fill and stop if ENTER or STOP passed, else the REGISTERED fill and stop — on that line his ÷ ours was 1.87 (his 2.62× vs ours
1.40×, `01_rev_check.txt` l.116, 110 trades) under the OLD offsets: 7 of them are era B and carried the calendar-index defect, and no recount
re-ran that account with the fix. So VOID is expected not to fire there, not certain; with the fixed offsets the ratio is re-read and VOID
applies as written. Both lines are printed. The daily list's in-sample recovery there (−0.027) is known — disclosed.
**What is new on 2021-22 = the 60-minute EMA leg only:** no 60-minute bar of any 2021-22 trade has been opened and the variant is chosen on 2020
alone. **The prior-low legs are not new there:** E2's and E4's last legs and E3's prior-low touch are daily or near-daily events whose markers
were read — `his_exits/describe_rows_2021_22.tsv` carries `first_below_prev_low` / `rel_below_prev_low` (the daily close below the prior low =
E2's last leg) and `first_sma10` / `first_sma20` for every dated trade, and the previous daily exit list included "under the prior low" (110 of
the 111 are in `reverse/exit_fit_trades.tsv`). Since a hit is the LAST leg's session, E2's hit rate there is largely set by a marker already
read; the half-leg hit rate (§7b) is the out-of-sample part. **Sign veto from the untouched dated trades** (23 with exits: 2019's 16, 2023's
3, 2022-H2's 2, January 2020's 2 — trades whose daily outcome and our and his daily accounts are known per trade, §9; the hit rate on the
≤ 20-session windows, the accounts on all): it fires only when ln(his ÷ ours) > 0 on those trades AND ln(chosen ÷ ours) < 0 — a PASS on
2021-22 then reads INCONCLUSIVE; otherwise (his ≤ ours there, so the recovery's sign means nothing) the veto abstains, said so. **Beside:**
the undated 2021-22 (226): hit rate against the trivial rules and the daily list's 37.7%, the three accounts (VOID there under the daily
rules: his ÷ ours 1.15); the registered fill and stop beside the chain's, as before.

## 8. WHY-lite — his 60-minute words joined to the trades the panel dates (a cross-check, never a source)

Counts are on the PARSED words (timing tags stripped, as the join rule and the inherited caption chain read them; the recount,
`verify/recount_prefreeze.txt`): of 495 caption files, 358 match `60[ -]?min|hourly|hour chart`, 122 mention the 20 EMA, and **77 carry
the phrase set below** (both within 80 characters). The earlier 334 / 344 / 103 / 169 were taken on the raw files or a wider pattern and are
withdrawn; the module re-derives and prints these counts on parsed words. The join rule is the
previous §9's (a phrase hit; a ticker mention within 30 s; the ticker's panel exit window covers the stream's session; ambiguous dropped) with
the phrase set `(60[ -]?min(ute)?|hourly).{0,80}(20|twenty)[ -]?(ema|day)|(20|twenty)[ -]?ema.{0,80}(60[ -]?min(ute)?|hourly)` on the
lowercased captions. **GATE: 10 joins hand-read (seed 1025, 2020 only) before any rate;** precision ≥ 70% → the share of those sells whose exit
session carries a 60-minute close below the 20-EMA is quoted; below → the joins are listed, no rate. It decides nothing.

## 9. THE FIT / CHECK SPLIT — what was seen where, and what each check rests on (constraint a)

| stage | seen before this registration | the untouched years (62 undated: no bar after the buy day opened beyond one aggregate account · 27 dated: daily path, S1-T / C, S3-C, the prior-low and moving-average markers, ours and his all seen; buy-day minutes opened for ORH5) | 2021-22 (opened by the previous read) | decides here |
|---|---|---|---|---|
| ENTER | L1-L6 scored on every 2020 and 2021-22 in-session window (fit and check printouts); L1 against the clock on all 262 dated in the dense window (holdings replay) | 17 scorable windows (9 non-flicker, all undated) — ±33 points on 9 | 20 dated + 43 undated non-flicker windows; the minutes read for L1-L6; L7-L9 unread; exposure aggregate only (§1c) | **2021-22's 43 undated non-flicker windows decide (expected n = 40); the untouched 9 are a sign veto (§5d)** |
| STOP | S1-S8 under T and C on the fit and on the undated 2021-22 (and the dated 2021-22 walked under them by the EXIT fit); the exits study's daily markers on every dated trade of every year | 62 undated: every cell new (S1 / S3 T and C included); 27 dated: S1-T / C and S3-C read (and S5-C, S7-C — the predecessor's §10) | 226 undated + 111 dated; four cells known, eight new | **the 62 undated untouched trades decide** (the chosen cell needs ≥ 20 traded through there) |
| EXIT | the daily exit list fit on every dated trade of every year (incl. 2021-22 and the untouched dated) and checked on the undated 2021-22; every dated trade's daily exit markers (exits study); his ÷ ours on dated 2021-22 = 1.87 | 23 dated with exits (2 windows of 121 sessions): all 23 in the previous EXIT fit set (22 walked in `exit_fit_trades.tsv`; DDOG 2019-11-13 in the set, not walked) — a recovery on ~20 trades is one trade's noise | 111 dated: the 60-minute state unread; the daily markers, the prior-low marker, the daily list's result and his ÷ ours known | **dated 2021-22 decides for the 60-minute EMA leg (new there; the variant chosen on 2020 alone); the untouched dated veto by sign (§7d)** |

- **The split the ask named — fit 2020, check 2019 + 2023 untouched, 2021-22 beside — is what STOP uses (on the untouched UNDATED trades).
  ENTER and EXIT cannot decide there** (ENTER 9 non-flicker windows, ±33 points; EXIT 23 dated trades whose daily paths were read), so
  2021-22 decides them and the untouched years veto by sign (DECIDED, §15 Q1). The previous RESULT's own sentence stands: 2021-22 is not a
  VIRGIN set for new entry levels.
- **The untouched dated trades were read** — the earlier label "never opened by any read" was wrong for them: `reverse/exit_fit_trades.tsv`
  holds 2019: 15, 2023: 3, 2022-H2: 2 and January 2020: 2 rows (walked on daily bars under the speed trail and the list rule, with an ORH5
  fill and stop S1-T); `his_exits/describe_rows_beside_dated.tsv` holds 2019: 21 and 2023: 14 rows (incl. the four still-held 2023 trades)
  with `our_status`, `our_vs_his`, `first_below_prev_low`, `first_sma10`, `first_sma20`; the era-B rows there carry the 1,445-1,569 session
  offset defect. The 62 undated untouched trades carry no fit or check tag in `dryrun_clocks.tsv` (three are SELECT's "other level" buys,
  read up to the buy day only) and entered only the holdings replay's aggregate open-fill account (`02_replay.txt` l.174: 2019 +38.0%,
  2023 +22.6%).
- **Design choices made AFTER the 2021-22 results were seen, with the direction each moves a PASS:** the shifted-window control (§3;
  harder); the clock-sanity rule (§2c; removes windows, neutral); the L9 definition (the last completed bar's high, not the day's high at the
  bar close — the latter is identical to L8's first crossing, so it was dropped by logic, not by data; neutral); the tail cut (§1e; a mark,
  direction unknown) with its 10% INCONCLUSIVE clause (harder); the EXIT variant list (his FSLY words and our readings of them; the
  article's 10-day trail already tested by the exits study, not re-added); the dated 2021-22 windows kept out of ENTER's deciding set
  (harder — they read higher); the sign vetoes (harder). **Two make a PASS EASIER and were chosen after the numbers were seen:** (1) ENTER's
  hit-or-ballpark becomes a 70% floor with no +15 margin — chosen after the random-price control's 85.9% was seen, because the margin
  would need 100.9% (§3); (2) STOP's Spearman ordering condition moves beside — its order is partly mechanical (§6b). **And one moves a STOP
  PASS easier by rule, not by data seen:** the buy-day certainty rule (§6a) turns touches made while he was provably flat from "certain"
  into "not an event" or "unresolved", which lowers H_cond — forced by the frames (on the 2020 fit, 51 of 83 buy-day S3-T "certain" calls
  have a flat frame after the fill), not by any 2021-22 or untouched-year result.
- **Forward facts carried, none used as a feature:** the previous §10's event count after the window (126 of the 633 no-event buys; 48 in
  2021-22); the known his ÷ ours ratios named above.
- **Fit trades that would read a check-side trade's path (C9, N1, N3, N5, DECIDED 2026-10-25; dates only, no bar read decides it).** Guard (5)
  is also per (bar symbol, session): the sessions after any check-side trade's buy day (buy day + 1 .. exit_hi + 20; a still-held trade: its
  last frame + 20) are forbidden to every fit stage. A fit trade's planned span runs from the daily lookback its stage reads before the buy day
  (ENTER 20 sessions: ADR20, the prior-session and base levels; STOP and EXIT 50: the 50-day average, the dated base low, the 10-session
  warm-up) to the last session a walk can book on (ENTER the buy day; STOP exit_hi + 1, a close or 60-minute stop selling at the next open;
  EXIT exit_hi + 21, the tail's next open). A 2020 fit trade whose span would **collide with a check-side trade's post-buy sessions** is
  excluded from that fit stage: ENTER 1 of 90 windows, STOP 16 of 453 trades, EXIT 10 of 149 (exposing 1 / 7 / 8 check-side trades) — the trades
  excluded, by name: ENTER: APT 2020-02-28 (its buy day sits inside the virgin APT 2020-01-23 trade's window); STOP: FCEL 2020-02-10 and
  2020-04-22 (FCEL 2019-11-12, FCEL 2020-01-02), BLDP 2020-02-10 (BLDP 2019-11-12), APT 2020-02-21, 02-28, 03-02, 03-05, 04-22, 04-23 and 05-06 (APT
  2020-01-23), STNE 2020-03-03 (the virgin dated STNE 2019-11-18), SE 2020-04-06, 04-27 and 05-05 (SE 2019-12-19), TDOC 2020-04-07 and 05-12
  (TDOC 2019-10-31); EXIT: BLDP 2020-02-10, APT 2020-02-21, 02-28, 04-22 and 04-23, TDOC 2020-05-12, FEAC 2020-11-30 (its tail runs into SKLZ
  2021-01-05 on the shared era-A symbol FIRY), TLRY 2020-12-16 (TLRY 2021-01-04 and the flicker 2021-01-26), MSTR 2020-12-28 (its exit_hi + 21
  session, a next open after the tail, is the first post-buy session of MSTR 2021-01-28 — N1), NIO 2020-12-30 (NIO 2021-02-08). The 50-session
  lookback adds 11 STOP and 3 EXIT trades whose 50-day average or ADR20 window read a virgin trade's post-buy sessions (N3; consumption, no fit
  printout carried a check-side value). **ENTER's beside windows lose** 6 of 194 the same way (N5): FCEL 2020-02-10, BLDP 2020-02-10, APT
  2020-02-21, APT 2020-03-05, SE 2020-04-06 and the held-before-09:35 TSLA 2022-04-21 (exposing TSLA 2022-02-11). **The belt:** the per-date
  refusal in the record and the minute store, and the record builder's check of the **pre-buy daily reads by bar index** on the record's own
  calendar (a hole stretches 50 bars past 50 sessions — MI 2020-05-26 and PLL 2020-10-05; on the kept trades none touches a forbidden pair, 0 / 0 /
  0 / 0 for ENTER, ENTER beside, STOP and EXIT, asserted). The dry run derives and asserts every count and name. Direction: unknown (removes 1 / 16
  / 10 fit trades and 6 beside windows; nothing of theirs was read).
- **X1 — the speed trail's forward window (found 2026-10-25 by the card that applied N1-N7; applied as below; **DECIDED 2026-10-25, main loop: keep
  the cut** — it moves no decision).** `ours` in the EXIT fit's 2020 accounts (in-sample, for scale, deciding nothing) is the frozen speed trail, which slices the
  121 sessions after the buy day straight off the bar arrays (`cb.forward_window`, as `break_horizon` does), outside `bar_at` and the per-pair
  belt. On 22 kept EXIT fit trades that **speed-trail window holds a forbidden session**, each after exit_hi + 21: PINS 2020-07-31, BE 2020-08-13,
  NIO 2020-09-14 and 09-29, TSLA 2020-09-21, 09-30, 10-12, 11-09 and 11-18, TWTR 2020-09-22, SE 2020-09-25 and 12-03, ZM 2020-10-09, TTD
  2020-10-29, ENPH 2020-11-05, SQ 2020-11-06, JMIA 2020-11-18, MRNA 2020-11-30, LAZR 2020-12-08, NVAX 2020-12-17, NCLH and CCL 2020-12-28. The
  fit bounds ours, his and chosen there by dates alone: the ticker's identity-break list gains one entry on that session, so every walk ends on
  the session before it (a trail still open there is the frozen walk's unsettled mark at its last close; the trades are named and counted in
  the fit printout; `cut_at_guard` if it ever shortened a tail, which the exclusion above rules out). The hit rates (the variant choice) do not
  move, and the check has no forbidden pairs, so its accounts are as registered. The other options were to exclude the 22 from the EXIT fit
  (a 15% smaller fit) or to drop the 2020 accounts. Direction: none on any decision; only the in-sample scale account moves.
- **2025-26 (sealed) holds no panel stream;** it tests the rule set as a STRATEGY once, after this read (§11).

## 10. Expectations, written now (guesses to be scored, never targets; a miss changes no rule)

- **ENTER:** L7 (the 1-minute high) feasible well UNDER L1's 36% — the first minute's high is crossed before most in-session flat frames; L8
  (the 30-minute high) feasible ABOVE L1's — a fresher level and 43 of 44 undated 2021-22 windows close after 10:00 — in the 40-55% range on
  the undated 2021-22 line; L9 near L8 on the after-10:00 windows, with the shifted-window control 10-15 points above the fixed-price control
  for L9 and level with it for L7 / L8. Hit-or-ballpark above 85% for any feasible level and for both controls (the test's weak side, stated;
  why it is a floor only, §3). The dated windows above the undated on every level (2021-22 L1: dated 60% vs undated 37%). The untouched 9
  agree in sign with 2021-22 (the veto does not fire).
- **STOP:** under TOUCH the tighter intraday levels (S9, S10) held through MORE often than S1's 39-44% (old certainty rule); the buy-day rule
  lowers every cell's held-through share on the fit by a few points; under the 60-MINUTE CLOSE every level held through less than under touch
  — S1-H in the 20-35% band, still above the 10% choose bar; no cell chosen → INCONCLUSIVE. S9 and S10 INCONCLUSIVE-by-size on the
  untouched undated trades (too few differ from S1). Stop-outs beyond −1.5R under H on 20-40% of stop-outs (a bar's close can sit far below
  the level).
- **EXIT:** E2 (half on the 60-minute average, the rest on a daily close below the prior low) wins the 2020 fit's hit rate at 40-50% (the daily
  list: 37.7% on undated 2021-22); on dated 2021-22 the recovery lands between 0.10 and 0.50 (ours 1.40 → chosen 1.6-2.1 against his 2.62);
  his ÷ ours on the untouched dated trades above 1, so the veto can fire, and it does not; the hit rate beats both trivial rules; the
  half-leg hit rate below the last-leg one on dated 2021-22.
- **WHY-lite:** the 10 hand-read 60-minute-EMA joins reach 70%; most name 2020 trades.
- **Which of these a BROKEN pipeline would also print** (so none of them confirms the pipeline; the known-answer gates of §12 do): ENTER FAIL
  (a wrong day, symbol, calendar or clock makes L7-L9 cross at random — feasibility about equal to the control); STOP INCONCLUSIVE (random
  held-through calls give no cell under 10%); an EXIT recovery below 0.25 (randomly firing 60-minute closes give recovery near 0).

## 11. DATA GATE (STEP 0), the fixes carried, the fetch list, and the sealed one-shot

- **Eras, exports, loaders, G8 — unchanged** from the previous §12 (era A = `cb702_pre_v2`, era B = `cb702` cut at 2024-12-31 and asserted;
  era by buy day ≤ 2022-03-31 A, else B; the holdings loaders imported read-only at the pinned sha; `trade_impact.py` before any number).
- **(c) The era-B calendar index — fixed by rule, tested.** Every session offset of a trade (the buy day, exit_lo, exit_hi, the still-held last
  frame, every walked session) is computed on ONE calendar: the record's own export calendar (`D.cal` of its era), by bisect on the date —
  never the pickle calendar for one end and the export's for the other (the previous `index_calendar` + `Rec._offset` mix; the recount's
  `off_fix`). Test: an era-B trade whose sell window is 5 sessions after its buy day reads offsets 0-5 (the old code read ~1,445); the dry run
  prints every era-B trade's offsets (the 8 undated 2021-22 check trades: 0-1, 4-4, 5-6, 5-6, 0-7, 2-6, 0-4, 0-4 per the recount) and refuses
  any offset beyond the trade's own calendar length. The frozen previous module is NOT edited; the new module builds its own record type.
- **(d) Caches keyed by identity hold the object.** One `IdCache` helper (`get(obj)` returns the entry only when `entry.obj is obj`) is the
  module's only cache; a test frees an array, reuses its id and shows the cache cannot serve the other array's entry; a module-scan test fails
  on any `id(` outside `IdCache`. (The previous module's two fixes — the cache entry holding the array, the numpy one-element scalar — are
  inherited through the frozen copy `01_rev_frozen_e908253f7405.py`.)
- **Minutes — the gate that bites (constraint b): computed, written, and since FETCHED** (the log: 19,184 ok, 286 empty at the source, 0
  failed, exactly the list — `verify/recount_prefreeze.txt` §15; no bar file has been opened). The 60-minute bars for the hold, the warm-up and the tail need
  minute bars on sessions the four pinned trees and `minutes_rev_1024/` do not hold (those cover the BUY DAYS: 1,302 of the 1,322 pairs of the
  10-24 list, plus the exit windows' first sessions on 60 of 230 trades). Pairs = ticker|date with minute bars in NO local tree's fetch log
  (`_done.psv` ok + the date file present); a pair logged `empty` (fetched, no bars at the source) is not re-listed. Bar symbol = `sym_a` on era-A
  dates, the panel symbol on era-B dates (by the SESSION's date, as `exit_minutes_for` did).
  - **The list (recommended, "with tail"):** `/Users/alvinfung/apollo_data/cb702/minutes_intra_1025/fetch_list_intra_1025.psv` — **19,470 pairs
    over 1,005 dates**, sha256 `e66f33d690f7d0d2ac9c797bedc16ff5bc79b9fffda268859016ed0d1d3f6254`, three columns `ticker|date|blocks`, no header
    (the fetcher's `parse_list` reads a third field as a tier only when it is all digits — `fit2020+virgin` is not, so every row is kept). Per trade: 10 sessions before the buy day (warm-up) + the buy day + the hold to exit_hi + 20 sessions after
    (the tail; a still-held trade: the buy day + 20). By block: fit 2020 8,795 pairs (+52 shared with the virgin block, +135 shared with 2021-22),
    the virgin block 3,179, 2021-22 7,309; by year 2019: 1,405 · 2020: 9,367 · 2021: 6,304 · 2022: 1,454 · 2023: 924 · **2024: 16** (the January
    2024 tails of the four 2023-12 still-held trades — inside era B's 2024-12-31 cut; nothing of 2025-26). The fit + virgin blocks alone = 12,026.
  - **The hold-only list** (the hit rates and STOP alone; no recovery account): `fetch_list_hold_only_intra_1025.psv` — 10,503 pairs over 966
    dates, sha256 `28624df669d9a7e1edeba35da2d6f5d3b0d91b6347648b345a3f41cbd2d0c525` (it still carries the 10-session warm-up). The tail is the
    difference: 8,967 pairs. Not used: Q2 DECIDED the list with the tail (§15).
  - **Cost, as run:** the fetcher (`scripts/probes/_cb_backtest/fetch_minutes.py`, 50 symbols per request per date, 0.25 s pause) took 8.0
    minutes for 1,032 requests (the estimate was 8-12 minutes and about 1,100). Command:
    `python scripts/probes/_cb_backtest/fetch_minutes.py --list /…/minutes_intra_1025/fetch_list_intra_1025.psv --out /…/minutes_intra_1025`.
  - **2017-18 (4 trades, ~800 pairs for 250-session holds) are listed, never walked** and not on the list. **A pair still missing at the run**
    degrades as before: ENTER `no_minutes` (neither HIT nor MISS); STOP's S1 → S2 and the H variant abstains for that session (`no_bar`); EXIT's
    average skips the window; every abstention counted, nothing silent.
- **Point in time, SELECT's era, the type table as of 2026-10-16 — unchanged** from the previous §12.
- **The sealed one-shot (2025-26, ONCE, after this read — his option 2 follows option 1):** the rule set as a strategy under his bar (alpha
  t ≥ 2 vs QQQ, total above QQQ and SPY, Sharpe above QQQ's) through the runner's holdout machinery. **The branch table, stated now:** universe =
  SELECT's PASSED condition set (the previous read); entry = the chosen intraday level where ENTER PASSED here, else ORH5 (`words-based`); stop =
  the chosen intraday cell where STOP PASSED, else the low of the day at the fill / one ADR20 (`words-based`); exit = the chosen FSLY variant
  where EXIT PASSED, else the speed trail (`words-based`). Every fallback is labelled in the sealed readout. **An H stop, if chosen, is
  sized on the level's distance; its realised R tail (§6a) is printed beside, and nothing is resized.** Research only; no rule moves.

## 12. Files, the module, its guards

- **Inputs (pinned at the dry run):** everything the previous §13 pinned (the timeline TSVs, exports, calendars, raw closes, candidates, EP
  events, guards, the type tables, captions, `qmlib.py`, the four minute trees' `_done.psv`, `minutes_rev_1024/_done.psv` and its list), plus
  `minutes_intra_1025/fetch_list_intra_1025.psv` (sha above) and the fetch's `minutes_intra_1025/_done.psv` (`done_INTRA`), the derivation
  script `00_pop_fetch.py` (`b7b75d56…`) and its printout (`d6bd0f67…`), the frozen previous module `01_rev_frozen_e908253f7405.py` and the
  previous registration's `doc_body`.
- **Code:** `scripts/probes/_705_intraday_1025/01_intra.py` + `test_01_intra.py`. Imports the FROZEN previous module read-only (refused on
  drift) for `load_core` / the sets / `derive_clocks` / `score_level` / `random_levels` / `exit_minutes_for` / the accounts, and the
  runner's `h60_windows` / `h60_trim` / `H60_EARLY_CLOSE` at its pinned sha; `cb.MinuteBars`, `cb.day0_walk`, the frozen `simulate`. **The
  frozen `held_through` is imported read-only but used for NO number:** the module's own held-through carries the buy-day rule of §6a; the
  frozen one runs only inside known-answer gate (iv), as the OLD certainty rule. Stages: `--dry-run` (populations asserted against §2 and against the previous dry run's counts; §2c's
  dropped windows listed; minute coverage per block; the era-B offsets printed; from clocks alone, per set, the records with S9 ≠ S1 and
  S10 ≠ S1; pins), `--enter-fit`, `--stop-fit`, `--exit-fit` (each writes once and prints its keyed chosen line), `--pins`, `--check` (ONCE:
  ENTER, STOP, EXIT, then WHY-lite's 10-row sheet), `--why-rates`, `--reset-fits "<reason>"` (N2, below).
- **Known-answer gates on REAL data (NEW — every expected verdict of §10 is also what a broken pipeline prints).** Each STOPS the stage
  before any new number, writes the failing rows, and may be cleared only by a bug fix shown in the code, never by changing a registered
  rule. **At the top of each fit stage, on the fit trades:** (i) per (ticker, session), the minute-built session bar against the daily export,
  in two arms (C1, DECIDED 2026-10-25 — the module check ran the first form of this gate on the 88 ENTER-fit buy days and saw it fail: 84 of
  88 within 0.5% on all four fields): **(i-a) the high AND the low within 0.5% on ≥ 98% of pairs** — both are set by trades on both sides, so
  they are exact on a right day (88 of 88) and gross on a wrong day, a wrong symbol under the era rename map, a wrong calendar or a DST / UTC
  clock shift; **(i-b) the open AND the close within 0.5% on ≥ 90% of pairs** — the daily open and close are the opening and closing auction
  prints while the minute bars open and close on ordinary trades, a basis difference of median 0.03%, p90 0.19% and one 4.9% day (APT
  2020-02-28, the closing cross on a 16.61-41.59 session) on the 88 buy days, where 84 of 88 = 95.5% sat within 0.5%. **The bars are set between
  the true and the broken readings, measured on the same 88 pairs, not at the first value the reading clears:** a one-hour clock shift (the
  10:30 price read as the open, the 15:00 price as the close) leaves the high and low within 0.5% on 8% of pairs and the open and close on
  3.4%; a wrong day (the previous session's daily bar against these minutes) 0% and 1.1%. So 98% for (i-a) sits 2 points under the true
  reading and 90 above the broken ones; 90% for (i-b) sits 5.5 under and 87 above. **Those margins are for that shift and a wrong day (N6):**
  on the same buy days (87 pairs now that APT 2020-02-28 is excluded, §9: high/low 100%, open/close 96.6%) the re-check's plants read, for
  the opposite whole-session shift, high/low 83.9% and open/close 27.6%, and for a daylight-saving bug that shifts only the standard-time
  sessions (10 of the 87) 98.9% and 88.5% — it clears the high/low arm and is caught by the open/close arm alone, 1.5 points under its bar. Both arms decide; every pair outside a band is written and
  listed by ticker; the hold, warm-up and tail sessions of the STOP and EXIT stages are unmeasured before their run (their bands are the
  same). **Stated now:** if the daily export and the minute source differ in split adjustment, failures cluster on one ticker's pre-split
  sessions — such a cluster reads as a source adjustment difference, listed by ticker, and no bar is raised after a gate fires. (ii) per window,
  on the raw intraday levels (before any max with a pivot), L7 ≤ L1 ≤ L8 ≤ L6, with the count of L8 < L6 printed; **the 60-minute bar
  BUILDER's first bar (`H60_0_high`, the value L9, S10 and EXIT consume) must equal the raw 30-minute high on every window, and that builder
  value equal to L6 on more than 90% of the windows with both is the [0,59] first-bar bug and stops the stage (C8)**; (iii) a daily close below
  a level implies the last 60-minute bar closes below it, **up to the auction band of (i-b)** (C2): per (session, level) with a last bar, a C
  event BEYOND the band (daily close < level × (1 − 0.5%)) whose last bar closes at or above the level is a failure, and the gate holds when
  ≥ 98% of the beyond-band C days are H days (the failures listed; a single APT-like day never stops a stage); C days inside the band that are
  not H days are counted beside, never failing; (iv) the L1-L6 crossing minute and verdict on the 2020 fit windows equal
  `reverse/enter_fit_trades.tsv` row for row (in `--enter-fit`), and S1 / S3 under T and C equal `reverse/stop_fit_trades.tsv` row for row (in
  `--stop-fit`) — that re-read takes each row's `fill_src` and `fill_minute` FROM THE TSV (the previous chain's fill, not this chain's), **takes
  the exit window's first-session minutes from the trees the previous fit read (A, B, EP, EP2, REV in that fixed order — never the new
  `minutes_intra_1025` tree, which holds those sessions for 251 of the 346 STOP fit trades with an exit; C4)** and applies the OLD certainty
  rule, so a difference is a bug; then the four old cells are re-printed under the old and the new rule on the same old-tree minutes; (vi)
  **his own words as a known answer, run inside `--stop-fit`** (FSLY is in the STOP fit set, the undated 2020 trades, and in no EXIT set, so
  guard (5) allows the read and EXIT's fit is not touched): FSLY eid 693 (undated 2020-06-29, exit window 07-13..07-14) shows a 60-minute
  close below the 20-EMA on 2020-07-10 and a touch of the prior day's low on 2020-07-13 (§0's two captions) — else the bar builder or the
  reading is wrong; FSLY's own pattern decides nothing for the variant choice (it is in no EXIT set). **At the top of `--check`, on the check
  trades, before any score:** (i), (ii) and (iii) again, (v) under the registered fill and stop, the frozen module's accounts (called
  read-only) and the new module's agree per trade ("ours" and "his") on the 103 era-A dated 2021-22 trades — a module-against-module check
  that needs no old offsets, so guard (10) holds; the 7 era-B trades are printed beside under the fixed offsets; l.116's 1.398 / 2.620 / 1.87
  is named as the old aggregate, not a target; and **(vii) the random-price control's known answer (C6): its mean feasible / hit-or-ballpark
  shares on the previous 41 undated 2021-22 records must read 31.7% / 85.9% at one decimal**, else the draws are not the previous read's.
  **The crossing of L7 / L8 is searched from the minute the level exists (09:31 / 10:00; C14).** The module check's F14 said a pivot-floored
  level could cross before it exists; it cannot: max(raw, pivot) is at least the raw level, which is the maximum high over every minute
  before the level exists, so no such minute's high is strictly above it — the two searches agree on every row (asserted on pivots above
  and below the raw range, a pre-10:00 spike, a sparse opening range). The explicit start is kept as a belt; the finding is rejected.
- **Recovery after a stop (N2, DECIDED 2026-10-25).** If fit 2 or 3, or the check, STOPS (a gate, the belt, a crash) after an earlier
  fit ran: (1) the fix is made in the code — a bug fix shown in the diff, never a registered rule; a fix that must change the body above the
  marker is a re-freeze (`doc_body_freeze` re-pinned, the old pin named in the disclosure); (2) `--reset-fits "<reason>"` moves every
  artifact — the fit, check and WHY printouts, the STOPPED file, the ledger, the dry run's and the pins' printouts, the chosen files, the
  per-trade files under `intraday/` and the module copies — into `verify/fit_events/<event>/` (copied, each copy's sha256 verified, and only
  then removed from its place: nothing is deleted), writes `MANIFEST.tsv` and `DISCLOSURE.md` (every archived printout's sha256 with the
  CHOSEN and STOPPED lines it carried) and appends the event to `verify/fit_events/events.tsv`; it refuses without a reason, when nothing
  STOPPED (a completed fit is never re-rolled) and after a completed check (the check runs once); (3) the dry run is re-run under the fixed
  module; (4) ALL three fits re-run in order on the fresh ledger; (5) every event's manifest is pinned under the marker (`fit_event_<event>`,
  listed by `--print-pins`) and every already-seen printout is disclosed there below it — `--check` refuses an event whose pin is missing or
  whose manifest changed. The check then runs once, on the final fits.
- **Tests (synthetic, before any real run).** The 60-minute bar builder (7 bars; 4 on an early-close day; a window without minutes is no
  bar; a [0,59] first bar fails); the EMA against a hand computation incl. the seed and `ema_thin`; L7 / L8 / L9 existence and L9's
  bar-by-bar level; the shifted-window control incl. `no_room` and early-close bounds; the clock-sanity rule on the named frames; the buy-day
  certainty rule (a touch before flat_clock, between flat_clock and first_clock, after first_clock; no in-session frame) for T and H; S9 / S10
  at the read minute; the H variant's certainty on exit_lo; E1-E4 incl. the half leg's booking, the E2 / E3 all-out when the prior-low event
  comes first, and the tail cut; the era-B offset test; the IdCache tests; the module scan; the freeze lock against this exact text.
  **And one END-TO-END synthetic world** run through every stage (`--dry-run` to `--check`) with real shapes: era-A and era-B trades (an
  era-B sell window five sessions after the buy), early-close days, a missing minute day inside a hold and on a buy day, a still-held
  trade, a 121-session sell window, numpy one-element arrays, exit-window minutes that exist in the new tree only (gate iv's re-read must not
  see them), and objects freed and their ids reused between stages — a fresh export and store per stage (the 10-24 module was green on unit
  fixtures and crashed twice on real data). **The check's DECISIONS are pinned, not only its lines (C7):** the deciding set is the chk22_und
  records (never the whole draw population); a forced ENTER / STOP PASS, FAIL, PASS-plus-veto and a forced VOID each flip the chain-carries
  lines, the deciding line and `check_verdicts.json` as §4 / §5d / §7c say; the STOP verdict is read on the virgin-undated table; 'his' is
  never 'ours'. Fixtures for a bar whose low pierces a level while its close holds (no H or E1 event), L9 crossing at the flat minute
  (infeasible) and at the first minute (feasible), the shifted starts read from the function, the T33 early-close day (4 bars, the last
  closing at minute 209, an E1 there sold at the NEXT session's open, never an after-hours print), a close fill whose prior-low touch waits for
  the armed bar's close on session 1 (C15), the horizon and data-end cuts (C11), the auction band of gates (i) and (iii), the builder's first
  bar in gate (ii), the collisions of guard (5) and its belt, and the per-fit freeze record. **Added with the re-check (§15 N1-N7, X1):** the
  planned span's two ends per stage and the bar-index lookback belt (N1, N3); the beside windows' exclusion in the synthetic world (N5); gate
  (vii) on hand records, the draw population's order and composition in the end-to-end check, a buy-day daily close below the prior low that
  must not sell a close fill under E2, the builder's first bar routed through `enter_row` with a [0,59] builder, the early-close trim in gate
  (i), a cached pair and the per-trade refusal from session 1 (N4); the guard bound of the speed trail (X1); a tail a hole or an identity break
  shortened counted in the clause (N7); and the reset path, unit and end to end: a STOP after the first fit, the reset, the dry run, all three
  fits and a check that refuses until the event is disclosed (N2). The module check's 37 one-line mutations and the re-check's 30 are re-run
  against this suite (§15 C7, N4).
- **Guards (the previous nine kept, three added):** (1) the line-anchored freeze lock — `--check` refuses unless every pin incl. `doc_body` (the
  sha256 of this file above the one line that is exactly the marker) sits under the marker, exactly one keyed chosen line per stage (ENTER,
  STOP, EXIT — parsed by its stage key, never by position; no such line exists in this document yet) stands above it, every fit printout exists
  and the check printout does not. **The freeze commit's (pre-fit) body is pinned too (`doc_body_freeze`), and `--check` asserts that the only
  lines differing above the marker between that commit and now are the three keyed chosen lines** (matched above the marker only, by
  the anchored pattern `^CHOSEN (ENTER|STOP|EXIT): `), so no other edit made after seeing a fit printout passes; **and each fit stage records
  the freeze body it validated and the module's sha in its chosen file and printout, and `--check` refuses unless all three records equal the
  pin under the marker and the module it is running (C5: without this the body could be edited after the fits, stored, re-pinned and every pin
  re-pasted — shown on a scratch copy — and the lock would pass)**; (2) the module copied beside the pins before any post-check edit; (3)
  populations asserted before any bar; no fit stage without a dry run ending `DRY RUN COMPLETE`; (4) G8 before numbers;
  (5) a fit stage opens no DAILY OR MINUTE bar after the buy day of a trade outside its own fit set (the BarGuard extended to minute reads by
  date; an undated 2021-22 or virgin-block buy refused by every fit stage), **and none on a (bar symbol, session) after ANY check-side trade's
  buy day — the fit trades whose planned span (from the stage's daily lookback to its last booked session, N1 / N3) would touch one are
  excluded by dates alone and named (§9, C9); the per-date refusal in the record and the minute store is the belt, on the pre-buy daily reads
  by bar index too; the speed trail's 121-session forward window is bounded before the first forbidden session (X1)**; (6) a crash writes a STOPPED file, and the only way past one is §12's reset (N2); (7) the append-only sha256 ledger;
  (8) misread clocks EXCLUDE, counted (§2c); (9) `replay/` and `his_exits/` never opened for an undated name; **(10) one calendar per record
  (§11c), asserted on every record; (11) IdCache only (§11d); (12) the 2025-26 seal — any file read is asserted ≤ 2024-12-31 at read.**
- **Outputs:** `01_intra_dryrun.txt`, `01_intra_{enter,stop,exit}_fit.txt`, `01_intra_check.txt`, `01_intra_why.txt`, `01_intra_ledger.tsv` in
  the module's folder; per-trade and per-bar TSVs under `apollo_data/cb702/qm_streams/holdings_1024/intraday/`.

## 13. What this does not answer

- **Which timeframe he used on a given trade** — each opening-range level is scored as a level; the "any opening range" union is read beside.
- **His fills, sizes and partials** (a half leg is modelled, never seen); **the side of a position** (a short reads as a long); **trades bought
  and sold between two streams**; **his fund and ETF trades** (the type gate) — as before.
- **A 60-minute average other than the 20-period, or a 5-minute chart** — his FSLY words name the 20 on the 60-minute; a 20-bar plain
  average is printed beside (other captions say "20ma"), deciding nothing; nothing else is tested.
- **A time-based stop** — EXIT's variants carry no session count; a separate registration.
- **Whether the entry can be decided without 2021-22** — it cannot on 9 untouched windows; Q1 DECIDED that 2021-22 decides with the
  untouched years as a sign veto (§15), so an ENTER PASS rests on a set whose minutes were opened for other levels (§1c).
- **Anything about 2024 beyond sixteen tail sessions, or 2025-26 beyond the one sealed strategy test.**

## 14. Design questions — DECIDED (main loop, 2026-10-25; no money, not THE LINE)

1. **Which set decides ENTER (and confirms EXIT's 2021-22)? DECIDED: the alternative.** 2021-22 decides ENTER — its undated non-flicker
   windows after §2c (§5d, expected n = 40) — and EXIT — its 111 dated trades (§7d); the untouched years are a sign veto on both, with the
   veto rules and false-veto rates of §5d and §7d. The leakage (the 2021-22 bracket windows' minutes were read for L1-L6; the new levels
   are unread and nested in price) is disclosed and its bound stated in §1c. Reason: the default (the untouched 9 decide) was a foregone
   INCONCLUSIVE-by-size that left the sealed test on ORH5 whatever the data showed. The previous RESULT's own sentence stands: 2021-22 is
   not a VIRGIN set for new entry levels.
2. **Fetch "with tail" or "hold only"? DECIDED: with tail** (19,470 pairs): the recovery account needs the chosen rule's actual sell. The
   decision said the fetch waits on his server permission; the fetch log shows the list has since run (§11).
3. **The untouched years' membership. DECIDED as written:** 2019 + 2023 + 2022 after 06-14 + January 2020 before the 27th. Their 27 dated
   trades were read by the previous EXIT fit and the exits study (§9), so STOP decides on the 62 undated and the dated are beside.
4. **The shifted-window control. DECIDED: keep for every level** (§3, with its bounds, key and stated bias).
5. **L9's definition. DECIDED: the last COMPLETED 60-minute bar's high** (the day's high at the bar close is identical to L8's first
   crossing; dropped by logic). L9 is labelled our reading beyond his words.
6. **The EXIT tail. DECIDED: 20 sessions after his sell window**, booked at that close and counted — a mark, direction unknown (not "a bias
   against the rule"), with the 10% INCONCLUSIVE clause of §7c.
7. **Pre-market-flat windows. DECIDED: beside only** (§5d).
8. **Flickers in ENTER's deciding set. DECIDED: the previous R1** — non-flicker decide (43 windows on 2021-22, expected 40 records),
   flickers beside (19 on 2021-22).

## 15. Revisions before the freeze

All made 2026-10-25, after the review and the recount of the registration and before any bar was opened. "Direction" = how the change moves a
PASS.

| # | what changed | where | source | direction |
|---|---|---|---|---|
| Q1 | 2021-22 decides ENTER (undated non-flicker after §2c) and EXIT (dated); the untouched years are a sign veto; leakage bound stated | §0, §1c, §5d, §7d, §9, §13, §14 | DECIDED, main loop | ENTER becomes decidable; vetoes harder |
| Q2 | fetch with the 20-session tail; the fetch has since run (log only read) | §0, §11, §14 | DECIDED, main loop | none |
| Q3-Q8 | as the doc recommended | §14 | DECIDED, main loop | none |
| F1 | ENTER hit-or-ballpark is a 70% floor only; the +15 margin applies to feasibility alone (the random-price control reads 85.9% hit-or-ballpark on 2021-22, so the margin needed 100.9%) | §3, §5d, §9 | review F1 (option a), chosen after 85.9% was seen | **easier** |
| F2 | the untouched dated 27 relabelled as read; STOP decides on the 62 undated (the review's "66" counted the four still-held dated 2023 trades as undated: 89 = 62 undated + 27 dated) | §0, §2, §6b, §9 | review F2 | harder (fewer, cleaner) |
| F3 | a buy-day certainty rule against the frames (51 of 83 buy-day S3-T "certain" calls on the 2020 fit had a flat frame after the fill); S9 / S10 read at first_clock on bracketed trades; the frozen `held_through` not used for numbers | §6a, §6b, §12 | review F3, re-derived from `stop_fit_trades.tsv` + `dryrun_clocks.tsv` (S1-T 92 / 23 / 6 / 14, S3-T 112 / 83 / 51 / 57) | easier for STOP, forced by the frames |
| F4 | known-answer gates on real data, each placed in the stage guard (5) allows (minute-vs-daily, the level order, C inside H, row-for-row re-reads on the TSV's own fills, 1.398 / 2.620 under the old offsets, FSLY 693 from his words inside `--stop-fit`); Spearman beside only; an end-to-end synthetic world; §7d's 1.87 qualified (old offsets) | §6b, §7d, §10, §12 | review F4; the lessons of 10-24 | Spearman beside: **easier**; gates: neutral |
| F5 | the deciding sets, the 39-record rule, both veto rules and the EXIT deciding line written into the body | §5d, §7d | review F5 | harder |
| F6 | citations fixed (stop l.1943; the exit from two stream captions, not the notes); E3 = his words; E1 / E2 / E4 / L9 / S10 = our readings; a wick = an undercut; a second-close and a plain-average variant beside; E2 / E3 all-out when the prior-low event comes first | title block, §5a, §6a, §7a, §7b | review F6, recount F6 | neutral |
| F7 | on dated 2021-22 only the 60-minute EMA leg is new; the prior-low marker files named; the half-leg hit rate printed | §1c, §7b, §7d | review F7 | neutral |
| F8 | the tail cut is a mark, direction unknown; > 10% tail or no-bar abstentions → recovery INCONCLUSIVE | §1e, §7c, §14 | review F8 | harder |
| F9 | `ema_thin` unless 20 seed + 50 post-seed bars; claim restated as a 0.7% seed residual | §7a | review F9 | neutral |
| F10 | the population table's header reads n; the checker exits 0 | §2 | review F10 | none |
| F11 | the shifted-window bounds, `no_room`, key, stated bias, and the union's control defined | §3, §5a | review F11 | neutral |
| F12 | an H stop's realised R tail printed (beyond −1R, −2R, the worst); nothing resized | §6a, §11 | review F12 | none |
| F13 | the freeze commit's body pinned; only the three keyed chosen lines may differ above the marker; the literal chosen-line text removed below the marker | §12, freeze record | review F13 | harder |
| F14 | the 2021-22 ENTER exposure stated exactly (aggregate only; no per-trade ENTER file; `fill_src` is a session crossing) | §1c | review F14 | none |
| R1 | 2019 dated non-flicker 15 → 13; 2023 dated 5 → 7 | §2 | recount F1 | none |
| R2 | caption counts restated on parsed words (358 / 122 / 77); the old 334 / 344 / 103 / 169 withdrawn | §8 | recount F2 | none |
| R3 | pre-market-flat undated populations 55 / 58 (52 / 57 were the scored counts) | §5d | recount F3 | none |
| R4 | "3 of its 10" undated 2019 windows | §1b | recount F4 | none |
| R5 | the previous STOP range 39-99% (39-68% on S1-S4) | §0 | recount F5 | none |
| V1 | files opened on 10-25 to verify the review and the recount, listed: `reverse/check_stop_trades.tsv` (DWAC 2022-01-31's row — its fill, stop and old-cell flags; a beside-set trade), `his_exits/describe_rows_beside_dated.tsv` (ticker, date, setup, `stalled` for the 2019 and 2023 dated — already-read trades; `stalled` is an outcome marker), `reverse/exit_fit_trades.tsv` (`fill_src`, exit offsets), `reverse/stop_fit_trades.tsv` + `reverse/dryrun_clocks.tsv` (the F3 counts), `reverse/enter_fit_trades.tsv` (header), five caption files (`cMkRsqvlVHM`, `YwMoUTd4naQ`, `tnHw5CKxcH4`, `GVTyWZCJPn0`, `kITl8W5eaEA` — text only), `02_replay.txt` l.174 (an aggregate); no price bar, daily or minute | §15 | verification | none (no deciding-set outcome read) |
| R6 | ±33 points on 9 windows, not ±30; AXNX is not one of the 89; four ENTER windows have no buy-day bars; the fetch outcome | §0, §1f, §11 | recount notes | none |

**The module check (2026-10-25, 15 findings, verdict BLOCK) — every finding DECIDED by the main loop the same day (no money, not THE LINE).** What
the check itself read: the 2020 fit trades' BUY-DAY minute and daily bars (gate (i)'s preview and the close comparison), the fetch logs, the
calendar and the sets; nothing after any buy day, nothing of 2021-22 or the untouched years, nothing of 2025-26. This revision read no bar.

| # | finding | decided | reason | direction |
|---|---|---|---|---|
| C1 | gate (i) failed as registered: 84 of 88 ENTER-fit buy days within 0.5% on all four fields (APT 2020-02-28 close −4.9%, CODX 2020-04-06 open +0.8%, BLNK 2020-07-22 close +0.7%, OPTT 2020-10-16 close +0.9%; high and low exact to the cent on all 88) | two arms: high AND low within 0.5% on ≥ 98%; open AND close within 0.5% on ≥ 90%; both decide (§12) | the four are auction-print basis differences, not a wrong day / symbol / calendar / clock (high and low exact); the bars sit between the true reading (100% / 95.5%) and the broken readings measured on the same 88 pairs (a one-hour shift 8% / 3.4%; a wrong day 0% / 1.1%), with margin on both sides — not at the value the reading clears | **easier** (the review saw 84 of 88 fail before the change) |
| C2 | gate (iii) had no tolerance: the daily close differs from the last 60-minute bar's close on 74% of buy days (median 0.03%, p90 0.19%, worst 4.9%), so any level between them failed the stage | a C event beyond the 0.5% auction band whose last bar closes at or above the level is a failure; the gate holds when ≥ 98% of beyond-band C days are H days; in-band non-H days counted beside (§12, §6b) | one band constant for (i-b) and (iii); a single APT-like day must not stop a stage | neutral (a gate) |
| C3 | EXIT INCONCLUSIVE by construction: the 70-bar floor equalled the 10-session warm-up; 13 of 111 deciding trades (11.7%) start under 70 after the 2021-11-26 early close | the floor is 20 seed + 45 post-seed = 65 bars; the dry run counts, from the fetch logs and the calendar, the trades whose warm-up alone is under 65 (deciding 0 of 111; fit 0 of 149; virgin 0 of 23) and asserts them (§7a) | the seed keeps 1.1% of its weight instead of 0.7%; every logged warm-up of the deciding set clears the floor with two bars of slack; the option (a) of not counting `ema_thin` would have hidden a real abstention | neutral (makes EXIT decidable; the EMA's value moves by the seed's residual only) |
| C4 | gate (iv) STOP re-read the exit window's first-session minutes from the new tree (251 of 346 fit trades have them there only), so correct code would mismatch the previous fit | the re-read and the old-rule re-print take those minutes from the old trees A, B, EP, EP2, REV in the previous fit's fixed order, through a restricted store; the synthetic world carries new-tree-only pairs (§12) | the previous fit's `exit_minutes_for` read those trees only | neutral (a gate) |
| C5 | the freeze body could be swapped after the fits (edit, store, re-pin, re-paste every pin: the lock passed on a scratch copy) | each fit records the freeze body and the module sha it ran under in its chosen file and printout; `--check` refuses unless all three equal the pin under the marker and the running module (§12 guard 1); the e2e test replays the hole | nothing tied the pinned body to the fits' versions | harder |
| C6 | the check's random-price draws were not the previous read's: 57 windows (the 7 dated flickers dropped) against 64, and the dated side set read 13, not 20 | the draw population = the previous read's `ent_chk_dated` (20, 7 flickers) + `ent_chk_und` (44, DWAC in) in (buy day, eid) order; the dated side set = the 20; gate (vii) at the check: the control on the previous 41 undated records must re-read 31.7% / 85.9% (§3, §5d, §12) | "identical draws" is a mechanical claim; the known answer makes it checkable | neutral (a gate; the deciding set is unchanged) |
| C7 | the tests ran every stage but pinned no decision: 21 of 37 one-line mutations survived | the check's decisions are pure helpers (chain carry, sign veto, deciding line, EXIT verdict order, abstention share) with unit tests; the e2e forces PASS / FAIL / veto / VOID and asserts the lines and `check_verdicts.json`; DECIDING n is pinned; fixtures for every case the check named (§12); the 37 mutations re-run — see the card's return for the kill table | a line that appears is not a decision that holds | neutral |
| C8 | gate (ii) read L8_raw from the minutes, not from the 60-minute bar builder L9, S10 and EXIT use, so it could not catch a [0,59] builder bug on real data | `enter_row` records the builder's first-bar high; gate (ii) asserts it equals L8_raw on every window and runs the > 90%-equal-to-L6 test on the builder value (§12) | the gate must check the value the stages consume | neutral (a gate) |
| C9 | guard (5) was per trade only: the STOP fit read 16 (symbol, session) pairs after the buy day of 3 check-side trades, the EXIT fit 59 after 6 | guard (5) per (bar symbol, session): forbidden pairs = every check-side trade's buy day + 1 .. exit_hi + 20 (a still-held trade: its last frame + 20); a fit trade whose planned span touches one is excluded from that stage by dates alone and named — ENTER 1, STOP 5, EXIT 6 (§9, §12; re-derived under N1 / N3: 1 / 16 / 10); the record and the minute store refuse the pairs as a belt | a fit that walks a check-side trade's path has seen its outcome; exclusion by planned span keeps the fit population independent of any outcome | unknown (removes 1 / 5 / 6 fit trades; nothing of theirs read) |
| C10 | the e2e world gave every stage the same market objects, so no id was ever reused between stages | a fresh export, bars and store per stage, the previous collected; asserted distinct (§12) | the registration promised freed objects and reused ids | neutral |
| C11 | sell windows longer than the 120-session horizon (GSIT 126, GTLB 123; CVNA 135, AI 134 undated) were labelled `mark_hole` and left out of the 10% clause | `cut_at_horizon` (and `cut_at_data_end` when the export's last bar ends the walk) — counted with `cut_at_tail` in the clause, printed by name; 'his' is that mark there (§7c) | a cut is a cut whichever bound made it | harder (more abstentions count) |
| C12 | the hit-rate window test read `exit_window_len()` from the main calendar beside offsets from the own calendar (two calendars on one record) | `exit_hi_j − exit_lo_j + 1` on the record's own calendar (§7c, §11c) | one calendar per record | neutral |
| C13 | `qqq_c` copied QQQ's closes after the buy day for the dry run's 33 era-B records (outside the guard; never used) | a dates-only record (`want_minutes` False) holds no QQQ close after the buy day | the dry run's "no bar after a buy day" must be literally true | none |
| C14 | "a pivot-floored L7 / L8 can cross before the level exists; L9 can then trigger after L8" | **rejected by proof**: max(raw, pivot) ≥ the raw level = the maximum high over every minute before the level exists, so no such minute's high is strictly above it; the search from the existence minute (09:31 / 10:00) is kept as an explicit belt and asserted equal to the frozen search on floored rows (§12) | the finding's premise cannot occur | none |
| C15 | E3 / E4 waited for the armed bar's close only on the buy day: a close fill arming on session 1's first bar counted touches from 09:30 that morning | no leg event before the armed session; on the armed session touches after the armed bar's close minute; later sessions from the open; E2's daily close from the armed session on (§7b) | the panel saw him hold from the fill; the rule arms on a completed bar | neutral |

**The re-check (2026-10-25, 7 findings N1-N7, verdict FIX) — every finding DECIDED by the main loop the same day (no money, not THE LINE),
plus one read path the re-check did not name (X1).** What the re-check itself read: the 2020 fit trades' buy-day minute and daily bars (gate
(i)'s plants and the close comparison), dates, calendars and fetch logs; nothing after any buy day. This revision read no price bar, daily or
minute: the re-check's findings and probe outputs, the timeline, the calendars, `base_id` dates and each export's dates and calendar index.

| # | finding | decided | source | direction |
|---|---|---|---|---|
| N1 | the planned span stopped at exit_hi (STOP) and exit_hi + 20 (EXIT), but a close or 60-minute stop and a sell on the tail's last session book at the NEXT open: MSTR 2020-12-28's exit_hi + 21 is the first post-buy session of MSTR 2021-01-28, so the belt could stop the EXIT fit after ENTER and STOP had printed | STOP hi = exit_hi + 1, EXIT hi = exit_hi + 21; the exclusions re-derived (EXIT adds MSTR 2020-12-28, exposing MSTR 2021-01-28) and asserted by name (§9) | DECIDED 2026-10-25, main loop | unknown (one more fit trade removed; none of its bars read) |
| N2 | no recovery once each fit records the module's sha: a fix after a stop split the fits' records and the ledger refused a re-run, so the check could never run | §12's procedure: the fix in the code, `--reset-fits` (archives, never deletes), the dry run, ALL three fits on a fresh ledger, each event pinned and its printouts disclosed under the marker (`--check` refuses until they are); unit and end-to-end tests | DECIDED 2026-10-25, main loop | none (no rule or bar moves; a re-run is disclosed) |
| N3 | the pre-buy daily reads (ADR20 over 20 bars, the 50-day average over 50, the dated base low) index the bar arrays outside the span and the belt: 3 STOP fit trades read virgin post-buy sessions inside the ADR20 window, 11 STOP and 3 EXIT inside the 50-bar window (consumption; no check-side value printed) | the span's lower bound = the stage's lookback (ENTER 20, STOP and EXIT 50 sessions): ENTER 1 of 90, STOP 16 of 453, EXIT 10 of 149 (exposing 1 / 7 / 8), by name (§9); the record builder refuses a forbidden pair inside the bar-index lookback (the belt); the dry run asserts 0 on the kept trades | DECIDED 2026-10-25, main loop | unknown (11 STOP and 3 EXIT fit trades removed; none of their bars read) |
| N4 | 11 of the re-check's 30 mutations survived (gate (vii), the draw order, the E2 buy-day close, the builder's wiring, the per-trade guard on session 1, the store's cache, STOP's span, the beside exclusion, the early-close trim, `restricted()`, C14) | the tests of §12 added; re-run on scratch copies: 28 of 30 killed; the 2 left are equivalent — `R_c14_from_zero` (C14's proof) and `R_drawpop_order` (the scoring loop sorts by (buy day, eid) before any draw; the order the draws are consumed in is now asserted end to end); the module check's 37: 36 killed, `h60_no_trim` a no-op (the windows end at minute 209); 15 new ones on this revision's changes: all killed | DECIDED 2026-10-25, main loop | none |
| N5 | 2 of ENTER's 194 beside windows were excluded by the code, but the dry run neither derived nor asserted them | one list for `enter_fit` and the dry run; under the new span 6 of 194 excluded, named in §9 and asserted | DECIDED 2026-10-25, main loop | none (beside only) |
| N6 | gate (i)'s margin ("90 points above the broken ones") holds for one shift; a daylight-saving-only shift clears the high/low arm (98.9%) and is caught by open/close alone (88.5%); the stage now reads 87 pairs / 96.6% | one sentence in §12 (i) with the opposite shift's and the daylight-saving plant's readings | DECIDED 2026-10-25, main loop | none (no bar moves) |
| N7 | a tail a hole or an identity break shortened (`mark_hole` / `mark_break`) was not counted in the 10% clause; the warm-up count's 2-bar slack and unmeasured thin hours were not named | counted with the cuts (§7c, `abstention_share`); the slack named as a residual (§7a) | DECIDED 2026-10-25, main loop | harder (more abstentions count) |
| X1 | found while applying N1: the frozen speed trail (`ours` in the EXIT fit's 2020 accounts) and `break_horizon` slice 121 forward sessions off the bar arrays outside the belt; 22 kept EXIT fit trades' windows hold a forbidden session (§9) | in a fit stage the ticker's identity-break list gains that session, so ours, his and chosen end before it, by dates; named and counted in the fit printout; the check unchanged | applied 2026-10-25 by the card; **DECIDED 2026-10-25, main loop: keep the cut** (excluding the 22 would shrink the EXIT fit 15%; the cut moves only the in-sample scale account) | none on a decision (the in-sample scale account only) |

<!-- FREEZE -->
## Freeze record

Empty until the freeze. The main loop freezes this doc and the module (`doc_body_freeze` pinned), runs the fit stages, writes the three keyed
chosen lines (one per stage) above the marker from the fit printouts, runs `--pins`, pastes every pin below (the previous registration's pins
carried, plus `fetch_list_intra`, `done_INTRA`, `pop_fetch_script`, `pop_fetch_printout`, `rev_frozen_module`, this module and its tests, the
dry run, the three fit printouts, the ledger, `doc_body_freeze`, `doc_body`), copies the module beside the pins, and runs `--check` once. Any
edit above the marker after that changes `doc_body`, and the check refuses.

### Pins

- doc_body_freeze: bc05126f9805087d0c8982f2f7f62cd9c0828dff56a6b47036e1248fc75956ce

(the rest after the three fit stages and the keyed CHOSEN lines)
