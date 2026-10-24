# #705 — His trade list v2 from the streams: the extraction rule, the census, and how it enters the replay (2026-10-24)

**Status: REGISTERED. The extraction rule and its precision checks RAN (outcome-free, $0); NOTHING here was run on outcomes.** No fill,
stop, exit, R, return or any bar after an event day E was read for any trade named here — an event's EXISTENCE on a day is the only
price fact used, and the candidate / EP tables were read with explicit `usecols` (the excluded columns are named in the script header).
Every era-B row dated after 2024-12-31 was dropped at read and asserted (5,210,943 export rows; 72,951 fetch-log rows). Nothing here
changes or proposes to change a strategy, an entry, a stop, an exit, a size, a safeguard or any live trade state — those are the
operator's (THE LINE). Script: `scripts/probes/_705_his_trades_v2_1024/01_census.py` (+ `01_census.txt`, the run's printout, pins last).
Outputs: `/Users/alvinfung/apollo_data/cb702/qm_streams/his_trades_v2/` (`census.tsv`, `pairs_v2.tsv`, `trades_v2.tsv`,
`hand_check_30.tsv`, `hand_check_30_text_read.tsv`, `v2_minute_fetch_list.psv`).

His words this serves (verbatim): *"I don't, his streams are the only source"* (2026-10-24, asked whether any other record of his trades
exists) — and the 10-23 correction that shapes the rule: *a stream moment is when he TALKED about the trade, not when he bought it* (EPs
are bought at the opening-range high on the gap day; the label only says WHICH event he took).

## 0. In plain words

- **What this is:** his 2017–23 streams carry 2,871 "I bought / I'm long" phrases. The replays so far used only the 236 breakout calls a
  screenshot confirmed (caption = screen = our bars, said on or before our breakout day) — thin outside 2020–21. This builds the list a
  caption-only rule finds, counts what it adds, and measures how often the rule names the wrong stock, before any outcome is read.
- **The rule (v2):** a (video, ticker) pair where "I bought / I'm long" sits in the ticker's own caption line (STRICT; anywhere in the
  ±30 s window = WIDE, beside), the ticker has our bars, and OUR event of that stock — a trendline breakout or an EP gap day — falls in the
  10 sessions before the stream or the 2 after. **The event's day is the trade day; the stream only says which event.** One row per
  (stock, event day, setup).
- **What it found:** 1,828 bought pairs → 954 strict → 807 with our bars → **336 with an event → 295 trades (249 breakout, 46 EP)**. 100
  of the 249 are already among the 236; **149 breakout trades and 46 EP trades are new**. WIDE adds 194 more trades (489 total). The
  years stay lopsided: 2020 holds 170 of the 249 strict breakout trades; 2017–19 have 11.
- **How right is it:** where a screenshot exists, a bought moment's named stock IS the chart on screen 60% of the time when our event is in
  the window vs 46% when it is not — the event requirement is the precision device; the own-line requirement adds nothing on that proxy
  (46.4% vs 44.4%) while halving recall. A planted wrong ticker has a breakout in the window 19% of the time (his named stocks: 37%). A
  text read of the 30-row hand sample (new rows only, the harder half) found the phrase plainly about the named stock in 15, about ANOTHER
  stock or not a buy in 9 ("i bought save … i didn't buy nclh", "i wish i had bought the pen", "im short draftkings").
- **What decides (written now, §6):** the v2 list (strict ∪ the 236) replayed under his rules at the round-3 configuration, against the
  same days' other breakouts and against holding QQQ / SPY (`04_vs_market.py`) — his bar, translated as alpha t ≥ 2 AND final equity ≥ QQQ
  over 2017-03..2021-12, is **his to confirm**.
- **Action from him:** (1) confirm the numeric reading of his bar in §6; (2) the 30-row hand check (`hand_check_30.tsv`, links open 15 s
  before each moment) — or say the text read is enough; (3) **the headline arm is a fork, not a pre-decided choice:** STRICT ∪ 236 (385
  trades; pre-declared; the only arm with a hand read) or WIDE ∪ 236 (486 trades, +100; 2017–19 doubles from 14 to 30 trades; equal
  precision on the screen proxy, but its WIDE-only rows have NO hand read yet) — rec: keep STRICT as the headline, WIDE beside, since the
  05 module walks both anyway; a WIDE headline needs its own 30-row sample first.

## 1. The four questions of the standard

1. **Decision served:** whether the trades he mentioned without a confirming screenshot are worth adding to the replay population, and what
   the replay of the fuller list says against his bar.
2. **What would change it:** the registered bar in §4a (event agreement with the frame-confirmed join ≥ 80% — PASS, 96.6%) and the hand
   check (§4d). A hand-check wrong-ticker rate above a third on the new rows means the new rows enter the replay only as a beside arm.
3. **Population:** §3; every count is reproduced by the script from the pinned inputs.
4. **What would make this wrong:** §5.

## 2. The rule — fixed before the first run (the script header is the record; this is a copy)

| Choice | Rule | Why |
|---|---|---|
| Unit | a (video, caption ticker) pair with ≥ 1 ticker-matched moment whose ±30 s window carries the bought phrase (`graded_moments.tsv`; regex asserted equal to 01/02's literal) | the extraction already exists and is pinned |
| Stream session s0 | the last era session ≤ the video's UPLOAD date, for every pair | upload − taskbar date is 0 d on 96.2% of frames; the same rule frame or not |
| STRICT arm (primary) | the phrase in the ticker's OWN caption line = `quote`, the words within [−9 s, +14 s] of the pair's first mention, 220 chars | the task's example; attribution of the phrase to the named stock |
| WIDE arm (beside) | the phrase anywhere in the ±30 s window (the grade itself) | recall; one output, one flag column |
| Era | upload ≤ 2022-01-03 → A (cb702_pre_v2, rebuilt 2017–21), else B (cb702, rows after 2024-12-31 dropped at read) | Track A's rule |
| Symbol | era A: the ticker, else `dedupe_applied` → `refetch_dropped` → `rename_map` (Track A's order); era B as read. "Resolves" = ≥ 1 bar inside the window | the export is keyed by today's symbol |
| Events | BREAKOUT = a `tl` candidate row, first breaks AND retriggers (A: `candidates_tl_com.tsv` K=tl; B: `candidates.tsv` K=tl, split discovery). EP = `ep_events_{A,B}` `primary` (gap ≥ 9% on ≥ 3× 20-day volume, $5 raw, $10M) — reused, not recomputed | the registered breakout level; the EP join's registered event |
| Window | E in [s0 − 10, s0 + 2] sessions, both setups | "I bought" is about a buy already made; +2 covers a pre-open stream / upload slop; −10 covers "two weeks ago". Beside: [−20, +2], [−10, +5], and the ±60 histogram |
| Match | nearest by \|delta\|; a tie goes to the EARLIER E | the talk is about something that happened (the EP join's rule; the opposite of Track A's anticipation tie) |
| Setup class | breakout / EP / both (a pair can support one row of each; same-day flagged) / neither (split: unresolved · no bar · no coverage · no event) | 2022-01..03 has no breakout candidates in either era |
| Dedupe | one TRADE row per (symbol, E, setup); mentions and videos counted on the row | |
| Registered bar | among the 854's bought pairs whose Track A join placed a tl event with delta ≤ +2 and v2 finds a tl event: ≥ 80% land on the SAME E | the stage the RULE controls, not the window |
| Window ceiling (fact, in advance) | Track A bought labels with delta ≤ +2 = 261/624 (42%); own line 350/669 (52%) → strict + [−10, +2] cannot recover "most" of the 854 by construction; the 236's 127 strictly-before events are out of v2's reach by design | |
| Planted control | 10 wrong tickers per strict resolved pair (seed 1024; bar on s0, close ≥ $5, close × volume ≥ $10M) → false-match rate of "an event in the window" | the frame check's control |
| Sample | 30 strict pairs with an event and NO frame-attributed label, stratified upload year × setup, seed 1024 | the uncertainty is in the new rows |

## 3. Census (counts only; `census.tsv`)

Per upload year. `pairs` = distinct (video, ticker) with a bought-graded moment; `in_854` = the pair has a frame-attributed label (any grade /
bought); `in_236` = its label sits on one of the 236 events; `own_line` = STRICT; `resolve` = a bar in the window; `event_*` = a tl / EP
event in [s0 − 10, s0 + 2]; `strict_*` = the same on the STRICT pairs.

| year | videos | with caps | phrase hits | bought moments | pairs | in 854 any | in 854 bought | in 236 | own line | resolve | event any | tl | EP | strict resolve | strict event | strict tl | strict EP |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2016 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2017 | 58 | 57 | 363 | 197 | 183 | 36 | 36 | 8 | 84 | 138 | 9 | 6 | 3 | 61 | 4 | 3 | 1 |
| 2018 | 2 | 2 | 20 | 6 | 6 | 0 | 0 | 0 | 2 | 5 | 3 | 1 | 2 | 1 | 0 | 0 | 0 |
| 2019 | 41 | 38 | 203 | 158 | 143 | 30 | 30 | 12 | 68 | 121 | 18 | 15 | 3 | 53 | 10 | 8 | 2 |
| 2020 | 219 | 214 | 1596 | 1175 | 1034 | 404 | 398 | 200 | 536 | 865 | 410 | 360 | 88 | 455 | 236 | 210 | 46 |
| 2021 | 189 | 145 | 581 | 409 | 388 | 163 | 160 | 55 | 219 | 335 | 137 | 120 | 34 | 192 | 77 | 69 | 18 |
| 2022 | 64 | 29 | 48 | 39 | 37 | 22 | 22 | 1 | 22 | 37 | 5 | 4 | 1 | 22 | 3 | 2 | 1 |
| 2023 | 12 | 10 | 60 | 40 | 37 | 18 | 18 | 7 | 23 | 36 | 12 | 8 | 7 | 23 | 6 | 6 | 1 |
| **all** | **588** | **495** | **2871** | **2024** | **1828** | **673** | **664** | **283** | **954** | **1537** | **594** | **514** | **138** | **807** | **336** | **298** | **69** |

- Why 2017 collapses from 138 resolved pairs to 9 with an event: 34 of the 84 strict 2017 pairs sit in January–February, before the first
  breakout candidate (2017-03-02) — a coverage fact, not a miss (the EP events do cover them); of the rest, 57 strict pairs resolve to our
  bars but have no event of either kind in the window, 14 tickers are unresolved and 9 have no bar in the window.
- Setup class, all pairs: neither 1,234 · breakout 456 · EP 80 · both 58. Strict: neither 618 · breakout 267 · EP 38 · both 31. "Neither"
  reasons (strict): no event 471 · unresolved ticker 70 (GBTC 37, TDOG 10, NICM 7, GSX 7 — OTC, mis-heard, delisted) · no bar in the
  window 77. Era A symbol resolution: own 1,537 · refetch 27 · rename 27 · dedupe 11 · unresolved 152.
- Of the strict pairs with a tl event, the nearest is a RETRIGGER for 215 of 298 and 240 have more than one tl event in the window; delta
  histogram (tl): 122 at 0, 60 at −1/−2, 90 at −3..−10, 26 at +1/+2. EP: 15 at 0, 21 at −1/−2, 27 at −3..−10, 6 at +1/+2.
- Beside windows (strict pairs with an event): [−20, +2] 395 · [−10, +5] 358 · primary 336. The ±60 read: 57 strict pairs have their
  nearest tl event 3–10 sessions AFTER the talk (he said "bought" before our line broke — our level fires late for them or he bought an
  earlier event), 109 more 11–60 after.

**The v2 TRADE list** (`trades_v2.tsv`, one row per symbol × E × setup), by EVENT year:

| arm | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | breakout | EP | total | in the 236 | new vs 236 (breakout) | no attributed label |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| STRICT | 4 | 0 | 10 | 199 | 73 | 3 | 6 | 249 | 46 | **295** | 100 | **149** | 111 |
| WIDE (beside) | 9 | 3 | 18 | 322 | 120 | 5 | 12 | 401 | 88 | **489** | 151 | 250 | 203 |

Strict breakout rows: era A 242 / era B 7; retrigger share 72%; |delta| 0 / 1–2 / 3–5 / 6–10 = 127 / 67 / 24 / 31; 109 symbols (MRNA 13,
FSLY 12, BLDP 8, SHOP 8, DKNG 7, PINS 7, CRWD 7). Same-day EP + breakout: 9 strict (one trade in the replay, flagged `same_day_other_setup`).

## 4. Precision checks (all outcome-free)

**(a) Positive control — the 854's 664 bought pairs through the same stages.** phrase 664 → own line 363 (54.7%) → resolves 664 → event in
window: tl 278 (41.9%), EP 67 (10.1%), any 319 (48.0%). Strict arm: 187 of 664 (28.2%) — inside the window ceiling stated in advance
(42% × 52%). **Registered bar: PASS** — of the 263 bought pairs whose Track A join placed a tl event with delta ≤ +2, v2 found a tl event
for all 263 and the SAME E for 254 (96.6%; bar ≥ 80%). The 9 that differ (checked one by one): 6 are the tie rule — a breakout the
session before AND the session after the talk, where Track A took the later day and v2 the earlier (JD, SHOP, MRNA ×2, ROKU, PDD) — and 3
are a video uploaded the day after the screen date, so v2's s0 and its delta-0 event moved one session (CMCM, SPOT, BIDU).
The 236 in the v2 breakout list: STRICT 97, WIDE 147. Split by the label's delta: inside v2's window (≤ 2) 152 events → strict 89, wide
44, missed 19 — 12 are BEST-graded calls with no bought phrase (v2 reads bought only) and 7 are the same tie-rule / upload-date cases above,
where v2 holds the neighbouring breakout day of the same stock instead; outside (≥ 3) 84 events → strict 8, wide 6, missed 70 (by design).

**(b) The frame reads as ground truth at scale** — 1,473 bought moments whose on-screen ticker was confirmed; P(the named stock is the chart
on screen): overall 45.4% · **own line 46.4% vs window only 44.4%** (no lift) · **event in window 59.8% vs no event 46.3%** (the lift) ·
own line AND event 61.5% · window only AND event 57.8%. Caveat: caption ≠ screen is an UPPER bound on the named stock being wrong (he may
speak of one chart while another is up; 7 of 20 moved quotes read by hand belonged to the spoken ticker). The most frequent own-line
caption → screen swaps are mis-hearings (TDOG→TDOC, OCTA→OKTA, LDP→BLDP, SC→SE, NVX→NVAX): the event requirement catches most of these
because the mis-heard ticker rarely has an event that week.

**(c) Planted wrong ticker** — 8,070 draws on 807 strict resolved pairs (pool median 2,463 tickers per s0): a wrong ticker has a tl event in
the window 19.4% (a first break 11.6%), an EP 1.4%, any 20.3%. His named stocks: tl 36.9%, EP 8.6%, any 41.6% → lift ×1.9 (tl), ×6.0 (EP).
Beside: a stock he merely MENTIONED (no grade; 9,617 pairs) has a tl event 26.4%, an EP 5.7% — topic selection explains part of the lift,
the bought phrase the rest. Reading: with ~55% of named stocks not the chart on screen and a 19% chance a wrong name has a breakout
anyway, roughly a quarter to a third of the strict breakout rows can be a wrong-stock coincidence — the hand check below is the test.

**(d) The 30-row hand check** (`hand_check_30.tsv`: `url` opens 15 s before the moment, `quote`, ticker, symbol, E, setup, delta; `verdict`
/ `why` blank). Drawn from the 146 strict pairs with an event and NO frame-attributed label — the NEW rows, where the uncertainty is, so
this is a lower bound for the whole list. **A text-only first read of the 30 caption lines** (`hand_check_30_text_read.tsv`; the video is
the operator's or a later card's):

| read | n | examples |
|---|---|---|
| CLEAR — the phrase is about the named stock | 15 | "i also bought some acad"; "correct entry on bili 42.87 … where i bought it"; "fcx i bought holding up nicely"; "i bought fastly csd estc twitter"; "im long gopro from since earnings day" |
| PARTIAL — he holds it, but the phrase or the timing is about something else | 2 | NTR ("tiny positions like lac and ntr … hold for longer term"); APHA ("stopped my apha … tilray i bought it down here") |
| AMBIGUOUS | 4 | CELH, MRNA ("i took a starter on …"), SPOT ("that why i bought it … adding spotify"), HI ("or h i bought some late day yesterday") |
| WRONG — about another stock, not a buy, or a short | 9 | NCLH ("i bought save … i didnt buy nclh"); PEN ("i wish i had bought the pen"); DKNG ("im short draftkings"); TWLO ("toku this is the one i bought"); FSLY ×2 ("i bought silo yesterday"; "tou i bought today"); POOL ("pool flag" = a flag pole); MDCO; SKLZ |

Text-read precision on the new strict rows: 15–17 of 30 (50–57%) right, 9 (30%) wrong, 4 unreadable from text. **The sample is strict-only:
the WIDE-only rows' precision is UNMEASURED, not inherited** — a WIDE headline would need its own 30 first. Among the CLEAR rows the
EVENT day is still uncertain for three (FUBO "since i bought them" weeks earlier; LMT "i bought it last week"; PDD a retrospective chart
walk) — the window picks the nearest event, not necessarily his. The dominant failure is one caption line naming several stocks with ONE
"I bought" — the phrase attaches to the wrong neighbour. The fix is a v3 arm (registered as the next step, not run): the phrase must sit
NEARER to this ticker's mention than to any other ticker's in the same line. It needs phrase timestamps (a re-parse of the VTTs), and its
precision must be read on a FRESH sample — the 30 above have now been read and cannot score it.

## 5. What the rule cannot see

- **Trades he never mentioned on stream** — the ceiling of any stream-derived list. 90 of 588 videos have no caption track (44 of 189 in
  2021, 35 of 64 in 2022); nothing before 2017-01.
- **Phrases outside the regex:** "i've been long", "i'm in", "i own", "rebought", "i'm buying", "added back" (CVNA) — recall, not precision.
- **The buy date:** "I bought it last week / two weeks ago" is placed on OUR nearest event, which may be a retrigger (72% of strict breakout
  rows) rather than the day he bought; a buy before our level broke (57 strict pairs with the nearest tl event 3–10 sessions after the talk)
  is outside the window by design, as are the 236's 127 strictly-before events.
- **Mis-heard tickers** that happen to have an event (the 19% planted rate), and the named-but-not-on-screen stocks (§4b).
- **Best-graded calls** ("A+ setup", "textbook") without a bought phrase — in the 236, not in v2 (12 of the 236's 152 inside-window events).
- **Shorts** — "im short draftkings" passed because "i bought this thing yesterday" followed; parabolic shorts need their own phrase set.
- **Era B is thin** (7 strict breakout trades, 4 EP) and **2020 is 68% of the strict breakout rows** — the same regime concentration as the 236.
- **Unresolved names:** GBTC (37 pairs, OTC), delisted or renamed names the rebuilt file lacks.

## 6. How the v2 list enters the replay (registered here; the 05 module freezes before it runs)

- **Module:** `scripts/probes/_705_qm_replay_1023/05_v2_list.py`, importing the frozen 01/02/03 read-only (03's pattern): loaders, walk
  wiring, trade builder, account simulation, control draw, date-matched difference, G8. Nothing in them edited.
- **Populations (breakout rows only; EP rows below):** HEADLINE = v2 STRICT ∪ the 236 (385 events: 236 + 149 new). BESIDE: v2 WIDE ∪ the
  236 (486); the 149 NEW strict rows alone (does the expansion carry its own weight?); the 236 alone (stored, no re-walk). Each reported
  per trade (R, tail first) and as the compounding account by year.
- **Control:** the same days' other tl breakouts under the round-3 exclusion (a row dropped only for a call said on or before its own E),
  recomputed for the new dates; the 200 same-day draws as the band.
- **Configuration:** the round-3 W2 row — his rules (ORH5 on E, low-of-day stop, too-wide skipped, 1/3 sold at the day-3 close, stop to
  breakeven), the speed trail (20-day; 10-day when ADR20 at D > 4.79%), 1% risk / 30% cap / 30% per stock, no margin; 2× margin BESIDE.
  Chosen now because it is the best registered reading on the 236 and the new rows are unread data for it.
- **Deciding readout:** `04_vs_market.py` on the headline curve — total return vs QQQ / SPY, Sharpe, beta, alpha with t-stat, over
  2017-03..2021-12 and 2020–21. **His bar, translated (his to confirm): alpha t ≥ 2 AND final equity ≥ QQQ over the full window.** The
  fork, written now: met → the stream list reproduces his record and the remaining gap is the trades he never mentioned; not met with the
  new rows no better than the 236 → the list is not the gap (execution / sizing / his EPs and shorts remain); not met with the new rows
  WORSE than the 236 → the caption-only rows are noise and the frame check (or the v3 arm) must confirm them first.
- **EP rows (46 strict / 88 wide):** a separate registration — no EP replay exists. Entry = the gap day's opening-range high (his rule);
  minute bars: 27 of the v2 EP days are not yet fetched (`v2_minute_fetch_list.psv`, tier 0 strict / tier 1 wide); every breakout E day
  already has its day-0 minutes.
- **Outcome-free so far:** this doc and the census read no outcome. The 05 module's dry run asserts the populations above; the real run
  happens once after the freeze commit pins this doc's body, the script and the inputs.

## 7. Pins

Every input and the script are pinned (sha256) at the end of `01_census.txt`: `graded_moments.tsv` f2c81633…, `grades_labels.tsv`
f4116fd9…, `labels_joined.tsv` d0299beb…, `candidates_tl_com.tsv` 3c5a66dc…, `candidates.tsv` b75c8286…, `ep_events_A` 59f196e5…,
`ep_events_B` 160401c7…, era-A export 0d5d2d0e…, era-B export ccc0097f…. The 236 was recomputed from `labels_joined.tsv` and asserted
(era A 236, era B 9); the era-B drop count (5,210,943 export rows) equals the EP join's.

## What this does not answer

- Whether his mention-based trades carry edge: no outcome was read, and the review (`scripts/probes/_705_his_trades_v2_1024/verify/review.md`)
  found the list too imprecise to decide anything (the stock wrong on 5 of 15 hand-read rows; his buy day on 3–5 of 15).
- His buy day for a mention: a stream labels the TALK, not the buy (his correction 10-23); the positions panel ('A - Positions') is the
  source that can date buys, and it supersedes this list as the primary record (PLAN #705, 10-24).
- Anything for 2018 (2 videos) or late 2023 (12 videos): the streams barely cover them.
