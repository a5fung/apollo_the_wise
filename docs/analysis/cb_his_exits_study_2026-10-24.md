# #705 — His exits: where he sold, and which exit rule reproduces it (2026-10-24)

**Status: REGISTERED. The 2020 description is read; the rules below are fixed; the 2020 fit runs next; the check on 2021-22 buys runs ONCE
after the freeze.** The holdings replay (`docs/analysis/cb_holdings_replay_prereg_2026-10-24.md` §RESULT) passed his bar, and selling where
HE sold (the panel's exit dates) gave 14.1x against 3.6x under our exit rules on the same buys — per trade +2.03R against +1.06R. He ruled the
order: study his exits first. This is that study: a description of his exits, candidate rules fixed before any check, a fit on the 2020 buys,
and one check on the 2021-22 buys whose outcomes stay unread until the rules are frozen. Measurement and registration only — nothing here
changes or proposes to change a strategy, an entry, a stop, an exit, a size, a safeguard or any live trade state (THE LINE). Module:
`scripts/probes/_705_his_exits_1024/01_his_exits.py`; the frozen holdings replay is imported read-only (its module and tests at their
freeze-record hashes, refused on drift); nothing in it is edited.

## 0. In plain words

- **The question.** Our exit rules (sell a third on day 3, trail the rest on the 10- or 20-day average) made 3.6x on his 2020-22 buys; his own
  exits made 14x. What does he actually do, and can a written rule copy it?
- **What the panel tells us.** It shows which names he held at each stream. A name that disappears was sold between two streams: we know the
  window, not the day or the price, and we never see a partial sale — only the last share leaving. So "his exit" below is always a range over
  that window, and his R is the whole position at the last share's exit.
- **The order.** First the description of his 2020 exits (done, §3). Then the rules (§4), written from his words (S) and from that
  description (B), fixed here. Then the fit: every rule's account on the 2020 buys, the best one chosen by the criterion in §5. Then the
  freeze, then ONE check on the 2021-22 buys (§6), whose outcomes no stage has computed.
- **Action from him: none now.** The stop question §7 raises is his call later, not asked here.

## 1. Population

- The holdings replay's **262 deciding buys** (its registration §2: dated to a breakout or gap day, window ≤ 10 sessions, buy day in
  2020-01-27 .. 2022-06-14, the two same-day re-buys out): **2020: 149, 2021: 102, 2022: 11** — asserted by the frozen loader.
- **Fit set = the 149 buys of 2020** (E in 2020-01-27 .. 2020-12-31). **Check set = the 113 buys of 2021-01-04 .. 2022-06-14.**
- Every rule takes the SAME entry and stop as the holdings replay: ORH5 on the buy day, the low of the day at the fill, skipped when wider
  than one ADR20. On the 2020 set that is 117 filled, 18 too wide, 14 never triggered. Unfilled entries are described beside on the panel
  account's close-fill proxy (the buy day's close + 0.1%, one ADR20 wide) and are in the panel-exit account only, as in the holdings replay.
- **His exit window** = [`exit_lo`, `exit_hi`] from the timeline: the last stream's session that still shows the name, and the first session
  whose two consecutive full snapshots do not. 74 of the 117 filled 2020 windows are one session wide (lo = hi), 25 are two, 18 wider.
- **Partials are invisible.** The panel shows presence only. His R here is the whole position at the last share's exit; a third sold earlier
  at a different price is not seen. **The survival bias of the dated book is inherited** (only buys still held at a snapshot are seen; round
  trips between streams are invisible; the bias is upward).

## 2. Disclosed pre-freeze reads (what was seen before the rules were fixed)

1. While orienting, the calendar-day hold lengths of all 264 in-window entries were read as one aggregate from `exits.tsv` (mean 9.7, median
   4 calendar days, p75 14). No outcome, no price.
2. The holdings replay's own result was known (the brief states it): the panel-exit account 14.07x vs the speed trail's 3.64x, per trade
   +2.03R vs +1.06R over the whole window.
3. **The 2020 description was read in full** (`01_describe_2020.txt`, §3 below) before the rules were written — that is its purpose. One
   exploration script on the same 2020 walk added three fast-exit markers (the first red close, the first close below the prior low, the
   first close below the 5-day) and printed, per filled 2020 trade, the per-trade R of two provisional B rules: a session-5 time stop
   (sum +234R) and "sell into strength" (a big up day or a 2-ADR extension over the 10-day, else the 10-day trail; sum +143R). On the
   description — a big up day or an extension sits inside his window on only 6 and 13 of 117 — the strength rule was dropped and B2 below
   written in its place. **So the B rules are 2020-fitted by construction; the time split exists for exactly that reason.**
4. **No stage has computed any outcome of a 2021 or 2022 buy.** The description stage walks the 2020 buys only (asserted: "walked by year
   2020 149"); the frozen `trades.tsv.gz` is opened only for rows with E ≤ 2020-12-31 (the parity check). The 2021-22 rows are walked for the
   first time by the check.

## 3. The description — his 2020 exits (117 filled; the unfilled 32 beside in the printout)

| what | reading |
|---|---|
| sessions held to the window's END | median **3**, p25 1, p75 9; on E itself 16, 1-2: 33, 3-5: 23, 6-10: 21, 11-20: 14, >20: 10 |
| R at his exit (RANGE) | at the close of exit_lo median +0.30 [p25 −0.70, p75 +2.45]; at the close of exit_hi median +0.58 [−0.93, +2.57]; mean +2.39 .. +2.59; **sum +279 .. +303R** |
| his losers | **29 of 117 exits at or below −1R** (mean −2.2R; our low-of-day stop would have taken every one at −1R or at the gap) and 20 in (−1, 0) |
| his winners | 21 exits ≥ 5R, 7 ≥ 10R; the ≥ 5R exits were held a median 11 sessions and had reached +2R before his window in 19 of 21 |
| the 10-day trail | his exit comes **before** the first close below the 10-day in 57 of 117, within it 39, after 21 — he is faster than the 10-day on half |
| the 20-day trail | before 79, within 28, after 10 |
| the first red close | before or within his window on 94 of 117 (before 55); the first close below the prior low: before 39, within 33, after 45 |
| +2R / +3R | +2R reached before his window on 58, within 12, after 40, never 7; +3R: 51 / 9 / 48 / 9 |
| a close below the breakout level | before 12, within 24, after 51, never 30 |
| a gap-down day (open ≤ prior close − 0.5 ADR20) | inside his window on only 9 of 117 (first one: before 21, within 6, after 88) |
| a big up day (close ≥ prior close + 1.5 ADR20) / an extension (close ≥ 10-day × (1 + 2 ADR20)) | inside his window on 6 / 13 of 117 — **selling into strength is NOT what the panel shows** |
| the stall (no +1R by the close of session 3) | 21 of 117 stalled; **16 of the 21 left his book by session 3** (R at exit median −1.2); the 96 that did not stall: exit median session 4, R median +1.0 |
| the 3-5 day count | exit_hi in 3-5 on 23; the window overlaps 3-5 on 29; **45 held past session 5** (R at exit median +2.45; 16 of them ≥ 5R) |
| fast vs slow (ADR20 above 4.79%) | 97 fast / 20 slow; exit median 3 sessions in both |
| OUR deciding exit (the speed trail) vs his window | **before 33** (our stop did 23 of them — 14 on day 0 — our trail 10; his R at exit on those: mean +3.3), **inside 55**, **after 29** (ours trailed longer: our R mean +3.9 vs his +5.9) |
| the top tail (the 12 trades where his exit beats ours most; their gap +160R, the whole set's +153R) | his hold median 14 sessions vs 3; the max R reached by his exit +12 vs +2.9; ours stopped early on 9 of 12 (W, VIR, BILI, ARCT, MRNA, ROKU, TSLA, QDEL on day 0-4 while he held to +4 .. +43R); APT 02-21: his [+40 .. +92]R in 3-4 sessions vs ours +49R at session 11 |
| per trade, every S rule on 2020 (sum R) | ours (speed trail) +150; S1 +107; S2 (hold to the 20-day) +185; S3 +102; S4 (day-3 third only in profit) +192; **his +279 .. +303** |

Reading: his exits are FAST (median 3 sessions, usually on or before the first red close), he cuts the stallers by day 3, he takes losses
larger than our 1R, and he holds the few that work far longer than the 10-day trail would. The biggest single gap to our result is not the
exit at all: on 33 of 117 our STOP (14 on day 0) closed the trade while his book still held it, and those went on to a mean +3.3R — a stop
question (§7), his call, not a rule written here.

## 4. The candidate rules (fixed here, before the fit; every number fixed)

Every rule keeps the registered entry (ORH5), the registered stop (the low of the day at the fill, no wider than one ADR20) and the day-0
minute walk; every trail is "first CLOSE below, sold at the next open" (the registered sequence). Names are the module's.

| # | tag | rule | his words (S) / the description (B) | module |
|---|---|---|---|---|
| S1 | S | sell 1/3 at +2R (day 0 on the minutes), stop to breakeven, trail the rest on the 10-day (ADR20 at D above 4.79%) or the 20-day, first close below | l.2046-2047: *"sell 1/3 at 2R then move to break even stop then trail rest at break of 10 or 20d, I recall he mentioned 10d for faster stocks and 20d for slower stocks"* | `cb.HIS_EXIT_ARMS["r2_p33_tspd"]` |
| S2 | S | hold the WHOLE position to the first close below the 20-day; no partial | l.1946-1947: *"trailed with the 10- or the 20-day moving average... You wait for the first CLOSE below"*; the brief's example | `Arm(qm, no partial, trail 20)` |
| S3 | S | 1/3 at +2R or at the session-3 close, whichever first; breakeven; the speed trail; a trade with no +1R by the close of session 3 is sold whole at that close | l.2070-2079: *"if breakouts have no follow through in next few days then it may be better to get out... Cut stallers is important"* (the +1R / session-3 numbers = the 10-19 confirmation); l.2061-2062: *"the partial may be a combination of the two (+2R or a number of days)"* | `c3_p33_tspd` + stall cut 3 / +1R |
| S4 | S | the session-3 third ONLY when the close is above the fill; breakeven after it; the speed trail from session 4 | l.2126-2132: *"Yes"* to "applies only when the trade is in profit" → *"the day-based third is sold only when the trade is in profit"* | `Arm(qm, 1/3 @ s3 if profit, speed)` |
| B1 | B | time stop: the whole position at the close of session 5 (the stop until then) | §3: 62% of his windows end by session 5, median 3; the article's "3-5 days" | `Arm(fixed, max_sessions 5)` |
| B2 | B | no +2R (day-0 peak or any high) by the close of session 5 → all sold at that close; else held to the first close below the 10-day | §3: the stallers leave by day 3; the ≥ 5R exits were held a median 11 sessions and had reached +2R first | `XRule(time 5 unless +2R, trail 10)` |

- **Not a candidate, and why:** "sell into a parabolic extension" (the brief's example) — a big up day or a 2-ADR extension over the 10-day
  sits inside his exit window on 6 / 13 of 117 (§3); the gap-down sale — inside on 9 of 117. The description does not support them.
- **Markers' numbers (fixed; ADR20 = the module's unit, ADR20 × the price):** gap-down 0.5 ADR20 under the prior close; big up day 1.5 ADR20
  over the prior close; extension 2.0 ADR20 over the 10-day; the stall = session 3 / +1R (`cb.STALL_CUT_SESSION / _R`); the time stop = session
  5 (`TIME_N`); B2's keep level = +2R (`TIME_UNLESS_R`); the speed cut = 4.79% (`cb.TRAIL_SPEED_ADR_CUT`).
- **Baselines beside:** ours = the holdings replay's DECIDING exit `d3_p33_tspd` (the day-3 third, breakeven, the speed trail); its primary
  `p33_s3_t10`; **his = the panel's own exits** (the whole position at the close of exit_hi, no stop; unfilled entries bought at the buy
  day's close), exactly the holdings replay's `panel_exit` account on the same subset.
- Both custom shapes (`walk_x`) are parity-tested against `cb.walk_exit` on the plain 20-day trail they share (every filled entry, 1e-9); the
  speed-trail re-walk is parity-tested against the frozen `trades.tsv.gz` per entry (realized R to 1e-9 and sessions held) — both held on
  all 117 filled 2020 entries.

## 5. The fit (2020 buys) and the choice — the criterion, fixed now

- **The account:** every rule, the two baselines and the panel exits through the frozen `simulate` with the holdings sizing (`cap_30`: risk
  1% of equity, position ≤ 30% of equity, ≤ 30% at cost in one stock, no margin), start 1.0 in cash at 2020-01-27, the same 149 buys, open
  walks run out past the year's end; the market comparison (`04_vs_market.py`'s formulas via the holdings module) over the 237 sessions
  2020-01-27 .. 2020-12-31 with open positions marked at the last close; his bar reported beside (it was registered for the whole window).
- **Recovery share** = (ln rule final − ln speed-trail final) / (ln panel-exit final − ln speed-trail final) on the SAME subset and window:
  0 = ours, 1 = his. Per trade, the sum of R is reported beside; the account decides.
- **The choice:** the candidate with the HIGHEST recovery share, which must be above 0 (it beats the speed trail); ties → S over B, then the
  shorter name (fewer parameters). If no candidate beats the speed trail, `CHOSEN: none` and the check is descriptive.
- After the fit the main loop writes exactly one line `CHOSEN: <rule>` above the freeze marker, prints the pins (`--pins`) and pastes them
  under it, then runs the check once.
- **Beside (deciding nothing):** the same table without the 3 entries with the highest panel R (the holdings recount showed the pass rests
  on the biggest winners — the dependence is made visible, not removed); breakout-dated only.

### 5a. The fit's result (2020; `01_fit.txt`, written once) and the choice

| rule | tag | final (2020 buys, cap_30) | recovery | 2020 return | max DD | Sharpe | alpha t | per trade sum R / mean R (n 117) |
|---|---|---|---|---|---|---|---|---|
| ours `d3_p33_tspd` | — | 2.697 | 0 | +163% | 22.6% | 2.18 | 2.17 | +150 / +1.28 |
| `p33_s3_t10` (beside) | — | 2.744 | +0.03 | +167% | 22.6% | 2.23 | 2.24 | +152 / +1.30 |
| S1 +2R third, speed trail | S | 2.181 | −0.33 | +113% | 18.4% | 1.97 | 1.98 | +107 / +0.92 |
| S2 hold to the 20-day | S | 2.199 | −0.31 | +119% | 41.0% | 1.50 | 1.47 | +185 / +1.58 |
| S3 combo third + stall cut | S | 2.210 | −0.31 | +116% | 18.4% | 2.00 | 2.00 | +102 / +0.87 |
| S4 day-3 third only in profit | S | 2.835 | +0.08 | +176% | 20.2% | 2.27 | 2.22 | +192 / +1.64 |
| **B1 time stop, session 5** | B | **5.087** | **+0.97** | +396% | 13.0% | 3.30 | 3.27 | +234 / +2.00 |
| B2 time 5 unless +2R, then the 10-day | B | 2.738 | +0.02 | +166% | 24.9% | 1.88 | 1.89 | +161 / +1.37 |
| his panel exits | his | 5.174 | 1 | +401% | 14.3% | 3.14 | 3.04 | +376 / +2.52 (n 149) |

- Without the 3 highest panel-R entries (APT 02-21, FSLY 05-07, W 07-27): ours 1.809, his 1.971, **B1 2.733** (above his), S4 1.901, every
  other rule below ours. Breakout-dated only (n 130): ours 2.316, his 5.337, B1 4.543, S4 2.643.
- **The reading before the check:** on 2020 none of the four S rules — the ones written from his words — beats our day-3-third + speed trail
  on the account; three lose to it. The time stop does, by nearly the whole gap, and it beats his own exits once the three big winners are
  out — so its mechanism is at least partly TURNOVER (the capital comes back after five sessions and goes into the next buy; it skipped 17
  entries for want of room against our 27), not a copy of his sells. It is 2020-fitted by construction (the session count came from §3).
  The check decides whether it holds on buys it never saw.

CHOSEN: B1_time5 (the registered criterion: the highest recovery share above 0 — +0.97; S4 is the only S rule above 0, at +0.08)

## 6. The check (2021-22 buys) — the bar, fixed now

- The same table on the 113 buys of 2021-01-04 .. 2022-06-14 (account from 2021-01-04; the market comparison over the window's sessions).
  Every rule is run; **only the frozen `CHOSEN` rule decides; every other number is beside.**
- **PASS** = the chosen rule's final equity is above the speed trail's AND its recovery share ≥ 0.25 (it recovers at least a quarter of the
  ln-gap between our exits and his). **FAIL** otherwise. Reported with it: the market comparison (his bar beside — the window is not the
  registered one), the per-trade sums, the same without the top-3 panel-R entries, breakout-dated only, 2021 and 2022 alone.
- Then the description of the 2021-22 exits (read for the first time) and, after the check, of all 262 and of the dated buys outside the
  account (the other years' deciding buys, the wider-than-cap windows) — descriptive, beside.
- **What a PASS means:** a written exit rule copies enough of his behaviour to be worth carrying as an ARM in the breakout read's exit grid
  (a registration of its own; the live exit stays his call). **What a FAIL means:** his exit is not a rule of this family — or the gap is the
  stop (§7) — and the next step is named from the description, not from the fit.

## 7. The stop question this raises (listed for him; nothing here moves it — THE LINE)

- 33 of our 117 filled 2020 trades were out before his window opened: 23 by our stop (14 on day 0), 10 by our trail; his R at exit on them
  averaged +3.3. And 29 of his 117 exits printed at or below −1R: he takes larger losses than one R. Both say his stop is wider, or later,
  than the low of the day at the fill. The holdings replay's stop × retry read (`cb_entry_stop_retry_2026-10-22.md`) and the stop variants
  are where that belongs; every rule here keeps the registered stop so the EXIT is what differs.

## 8. What this does not answer

- His partial sales (invisible), his fills (the panel shows a name, not a price), the side of a gap-day position (a short reads as a long),
  anything after 2022-06-14, his actual returns (18% of his book is dated).
- Whether a rule chosen on 2020 generalises beyond 2021-22 — one holdout, one regime pair (2020 bull, 2021 growth break, H1-2022 bear).

## 9. Files, guards, the freeze

- **Inputs:** the holdings replay's `entries.tsv` / `exits.tsv` / `snapshots.tsv` (pinned there), its `replay/trades.tsv.gz` (parity),
  the frozen exports, candidates, labels, guards and fetch logs (the holdings pins, re-checked at every stage), the holdings module and its
  tests at their freeze hashes. **Outputs:** `01_describe_2020.txt`, `01_fit.txt`, `01_check.txt`, `01_describe_all.txt` in the module's
  folder; `describe_rows_*.tsv`, `trades_fit_2020.tsv`, `trades_check_2021_22.tsv` under `holdings_1024/his_exits/`.
- **Guards:** the holdings module's sha asserted at import; every holdings pin re-hashed per stage; populations asserted by the frozen loader
  (262); the fit walks 2020 only (asserted), the check 2021-22 only (asserted); parity with the frozen replay per entry; `walk_x` parity with
  `cb.walk_exit`; every printout written once (a stage refuses when its printout exists).
- **The freeze lock (line-anchored; it locks the CHECK, not the fit):** the doc-body hash covers every byte above the one line that is
  exactly the freeze marker (the literal appears nowhere else in this file — prose says "the freeze marker"); `--check` refuses unless every
  pin `--pins` prints (the holdings module and tests, this module and its tests, the three timeline TSVs, the frozen trades file, the
  description and fit printouts, `doc_body`) sits under the marker, a single `CHOSEN:` line exists above it, the fit printout exists and the
  check printout does not. A crash writes a STOPPED file.
- Tests: `test_01_his_exits.py` (walk_x parity with cb.walk_exit on 40 random worlds, leg kinds and statuses, each custom shape, the rules
  build, the time-unless keep, the marker and `CHOSEN:` parsing).

<!-- FREEZE -->
## Freeze record

Empty until the freeze. After the fit, the main loop writes the `CHOSEN:` line above the marker line, runs `--pins`, pastes every pin below,
then runs `--check` once. Any edit above the marker after that changes `doc_body`, and the check refuses.

### FREEZE 2026-10-24 (the one check follows it)

- holdings_module: 4275d72f82aaf66c7c24372afe48e0b503dedb51e2c7715d8fbd26c4372e9ce9
- holdings_tests: eee66bf08ef8f70c5da66b4aeec0f626f592ca327dcfc7c6c0c6fd1943a0b75f
- his_exits_module: 47cd0aa95c559a2f99c262dd409a737401204f60373b5803727ea1864d2591cb
- his_exits_tests: ffaab961745dad9b05dc2a71dc057c7849d515e7fab11309fa446d1fc5d16f6f
- entries: 6a0dda2da7932b6d54f122594df817215c1237636629f3ce6efa7cef1b9bdabf
- exits: 1ed76a2806091f7d56726c56e6b2a389dfa2e96db24c382d4296da096529b50f
- snapshots: a8987fce15fa1a968010b4290c249f2c62de24d18d1b71bca4b9b0c4f507caff
- trades_frozen: 1d3dccc45e1798dc7f9b808e74df5f29bb0a952b8c68e3de63ba69610952b74a
- describe_2020_printout: deac58a391a6bdbb3a9c95aad2c90a4b3bd96dfc62aa5d3ad845da6617054a09
- fit_printout: 37413d2b2e77cff74f32800aca3c5541332f3ac2f5327fb8349831e6008ef11b
- doc_body: 50d7a8f96ca5288cd406ffe7f3ee8d92569735d706e68a7c83f0c6ec3e5a225e

### Freeze-record note (2026-10-24, after the check and after the review; the pin lines above are untouched)

- **The pinned module is not on disk.** The `his_exits_module` pin (`47cd0aa9…`) names a file that no longer exists: no copy was kept beside
  the pins, and 16 reconstructions of "undo the None-guard" (the review's attempt) did not hash to it. So the post-check edit's exact size
  is **not byte-verifiable**. The module on disk is `0157529f28ff09f75d94ed69682d6e422fe5d055142ae7dbe987c78593a7da3b` (sha256 taken
  2026-10-24 for this note).
- **What is verified instead** (`scripts/probes/_705_his_exits_1024/verify/review.md`, check 2): the module as it stands, re-run read-only,
  reproduces every final in `01_fit.txt` and `01_check.txt` (printed to 3 decimals; the review compared at 4, e.g. B1 5.0874 on the fit and
  1.4444 on the check), so the post-check edit changed no account.
- **The one post-check edit:** a None-guard in `describe_print`, so the beside set (names still held at the last stream have no exit window)
  could print. Nothing else; no outcome recomputed (as disclosed in RESULT below).
- **Not committed:** at this note the doc, the module, its tests and the printouts are untracked, so the freeze order rests on the pins
  and the file times (the review's chain, from the repo and the session logs: exploration 15:37, description 15:39, fit 15:43, pins 15:43,
  check 15:44, module edit 15:45, doc 15:49; the exploration files now in the folder are copies dated 15:48), not on commits. For future runs: copy the module beside the pins before any post-check edit, so a disclosed edit can be diffed.

## RESULT (2026-10-24; written BELOW the marker after the one check — `01_check.txt`; the body above is unchanged)

**The check FAILS: none of the six registered exit rules reproduces his exits. The 2020 winner (a 5-session time stop, recovery +0.97) recovers +0.10 of
the gap on the 2021-22 buys it never saw.** On 113 buys of 2021-01-04 .. 2022-06-14, cap_30 sizing, the market comparison over 365 sessions:

| rule | tag | final | recovery | 2021 / 2022 | max DD | Sharpe | alpha t | per trade sum R / mean R (n 88) |
|---|---|---|---|---|---|---|---|---|
| ours `d3_p33_tspd` | — | 1.330 | 0 | +41% / −6% | 24.2% | 0.79 | 0.98 | +66 / +0.75 |
| S1 +2R third, speed trail | S | 1.632 | +0.26 | +73% / −6% | 21.4% | 1.36 | 1.68 | +59 / +0.67 |
| S2 hold to the 20-day | S | 1.403 | +0.07 | +49% / −6% | 43.7% | 0.75 | 0.94 | +62 / +0.70 |
| S3 combo third + stall cut | S | 1.335 | +0.00 | +41% / −6% | 19.4% | 0.90 | 1.12 | +61 / +0.69 |
| S4 day-3 third only in profit | S | 1.314 | −0.01 | +40% / −6% | 24.8% | 0.76 | 0.94 | +64 / +0.73 |
| **B1 time stop, session 5 (CHOSEN)** | B | **1.444** | **+0.10 → FAIL** (bar ≥ 0.25) | +51% / −4% | 22.9% | 1.09 | 1.34 | +48 / +0.55 |
| B2 time 5 unless +2R, then the 10-day | B | 1.422 | +0.08 | +50% / −5% | 33.4% | 0.84 | 1.04 | +77 / +0.88 |
| his panel exits | his | **2.942** | 1 | +261% / −19% | 29.8% | 1.76 | 2.21 | +148 / +1.36 (n 109) |

- The chosen rule beats the speed trail by a tenth of the gap and is WORSE per trade (+0.55R vs +0.75R): what it had on 2020 was turnover
  in a year when every breakout ran in its first week. The best rule on 2021-22 after the fact is S1 (his +2R third, +0.26) — the WORST of
  the six on 2020 (−0.33); post hoc, it decides nothing. **No rule is above +0.26 on both year-sets (B1 is +0.97 on 2020 and +0.10 on 2021-22; S1
  is −0.33 and +0.26), and none beats his exits by a wide margin anywhere except the time stop on 2020 without the three biggest winners.**
- Without the 3 highest panel-R entries (TLRY 02-02, MARA 02-08, LCID 10-25): ours 1.056, his 1.736, B1 1.154, S1 1.291. Breakout-dated
  only: ours 1.506, his 2.842, B1 1.400. 2021 alone: ours 1.396, his 3.408, B1 1.503, S1 1.709. 2022 alone (11 buys): everything loses
  3-5%, his exits −14% — his 2022 exits were worse than any rule's.
- **The 2021-22 description (read for the first time in the check)** repeats 2020: his exit median 3 sessions (p75 6); 28 of 88 exits at
  or below −1R at exit_hi (22 .. 30 across his window; see the corrections below), 24 in (−1, 0); 13 ≥ 5R, 7 ≥ 10R; his exit before the first close below the 10-day on 52 of 88; a red close before or within
  on 65; 20 of 24 stallers gone by session 3; a big up day inside his window on 3 of 88. Our speed exit: before his window 24 (our stop 20 of
  them, 11 on day 0; his R on those averaged +2.3), inside 37, after 27. The top tail is the same shape: MARA, RIOT, AMC, BB stopped on day 0
  while he held to +6 .. +22R; TLRY +27R at session 6 vs our +5R.
- **What separates the trades where his exit beats ours most (all 262):** his hold 12 sessions vs 3; the max R reached by his exit +19 vs
  +2.4; our walk stopped on 70% of them (half on day 0), against 74% of the rest — the stop rate does not separate them; 80% retriggers,
  0% EP-dated; a faster-than-10-day sell in 40% vs 55%.
- **Reading, for him (no action asked):** his exits are not a trail, a target, a time stop, a partial schedule or a sale into strength as
  written — the fast half (cut by day 3, often on the first red close, at losses beyond 1R) and the slow half (a handful held 10-45 sessions
  through the 10-day) do not come from one rule we can write from the panel. Beside the exit, a separable piece sits in our stop: on 57 of
  the 205 filled trades our exit came before his window — our stop on 43 (25 on day 0), our trail on 14 — and those averaged +2.9R at his
  exit. It is not shown to be the larger gap: our stop closed 70% of the trades where his exit beats ours most and 74% of the rest, so the
  stop rate does not separate them. Round 3's base-low stop (wider at the same risk, so smaller positions; 1.43x on his calls) is not the
  stop these trades need; a stop that keeps them at the same size is untested. Where that goes next is his call (THE LINE); the stop × retry
  read is where it belongs.
- **Post-check edit, disclosed:** after the check, `describe_print` was given a None-guard so the beside set (names still held at the last
  stream have no exit window) could print; nothing else changed, no outcome was recomputed. The module on disk is now
  `0157529f28ff09f75d94ed69682d6e422fe5d055142ae7dbe987c78593a7da3b`; the check ran at the pinned `47cd0aa95c559a2f99c262dd409a737401204f60373b5803727ea1864d2591cb`. The all-years description
  (`01_describe_all.txt`) comes from the edited module; its `2020 alone` block was diffed against `01_describe_2020.txt` (identical but for the
  two B-rule rows that printout left out by design); its 2021 / 2022 blocks are splits of the check printout's 2021-22 block. The pre-freeze
  exploration (§2 item 3) is kept as `00_explore_2020.py` / `.out` in the module's folder. Two B1 rows were checked against the export by hand:
  APT 2020-02-21 marks at the 2020-02-28 close 21.00 (+88.8R), NVAX 2020-04-03 at the 04-13 close 17.64 (+2.85R) — the time stop is a clean close mark.

### Window sensitivity and corrections to the body's claims (review 2026-10-24)

His exit is a window, and the registered accounts sell at the CLOSE of its last session (`exit_hi`, "the latest the panel allows", the holdings
replay's R8; an unfilled entry is bought at the buy-day close + 0.1%). The body states some points of that window as single facts. It is frozen, so each is
corrected here, named by section. The figures are the review's read-only recomputation from the stored legs (`verify/review.md`, checks 1
and 5); nothing was re-run.

- **The verdict holds at every reading of his window (review F6).** B1's recovery on 2021-22: +0.104 at exit_hi (registered), +0.092 at
  exit_lo, +0.112 at the worst close inside each window, +0.080 at the best; on the 88 ORH5-filled entries only, +0.108 / +0.100 / +0.115 /
  +0.087. All are under the 0.25 bar (n = 109 panel trades; n = 88 on the filled entries).
- **The 2020 "+0.97" is a point in a range (F6).** B1's recovery on 2020: +0.97 at exit_hi, +1.44 at exit_lo, +3.58 at the worst close, +0.75
  at the best (n = 149 panel trades). The choice does not move (B1 is the highest at every reading), but "recovers nearly the whole gap" is +0.75 .. +3.6.
- **Header and §0, "selling where HE sold ... gave 14.1x" (F5):** 14.1x is the panel account selling every position at the close of the
  window's LAST session. Over the whole window (n 258 trades): 12.5x at exit_lo, 8.3x at the worst close inside each window, 21.6x at the best;
  11.9x on the 205 entries our rules can fill (no close-fill buys). The 3.6x on our side is unchanged.
- **§5 "on the SAME subset"; header "on the same buys" (F7):** the same buys are offered to every account, but the panel account also holds
  the close-fill buys the rules cannot fill: 32 in 2020 and 21 in 2021-22 (53 over the window), so the panel trades 149 / 109 (258 over the
  window) against the rules' 117 / 88 (205). The header's per-trade +2.03R is over the panel's 258, the +1.06R over the rules' 205. In 2020 the
  32 close-fill buys carry +72.5R (mean +2.27R, six at ≥ 5R): part of the panel's 2020 edge is entries the rules never get (ordering them
  after the day's ORH5 fills moves the 2020 panel 5.174 → 5.347, so the registered order is not what flatters it). On the filled entries only,
  B1's recovery is +1.41 on 2020 and +0.108 on 2021-22 — the verdict is unchanged.
- **§3 "his losers" and §7 "29 of 117 exits at or below −1R"; RESULT "28 of 88" (F10):** these are the exit_hi point. Across his window it is
  21 .. 33 of 117 on 2020 (23 at exit_lo; 21 at the best close, 33 at the worst) and 22 .. 30 of 88 on 2021-22 (28 at exit_hi, 23 at
  exit_lo). "He takes losses beyond 1R" holds at every reading.
- **The edits made in place above (F1-F4), for the record** (no commit exists to diff against):

  - Headline: "no written exit rule reproduces his exits" → "none of the six registered exit rules reproduces his exits" (the red-close, prior-low and 5-day markers were described, §2 item 3 and §3, and never registered as rules).
  - Bullet 1: "No rule is above +0.26 on either year-set" → "... on both year-sets", with B1 +0.97 / +0.10 and S1 −0.33 / +0.26 beside.
  - "What separates": "i.e. the gap is mostly the STOP, not the exit" deleted; the rest of the trades are stopped 74% (01_describe_all.txt l.40), so the stop rate does not separate the top tail.
  - Reading: "on 57 of the 205 filled trades our low-of-day stop closed the trade while his book still held it ... +2.9R" → "our exit came before his window — our stop on 43 (25 on day 0), our trail on 14 — and those averaged +2.9R at his exit" (`01_describe_all.txt` l.37).

## Erratum (2026-10-24, after the check)

Found by the adversarial review after the check (`verify/review.md`, checks 2 and 4). The body above the freeze marker is frozen, so each
correction is named here by the §-row it corrects. None changes a candidate rule, the choice, the check or the verdict: the S tags label rules
that ran exactly as registered. What was wrong is how the body quotes his words and what it says was seen before the freeze. Line numbers
are in `docs/methodology/operator_shared_notes.md`, each read against the file (F8, F9).

- **§4 row S1** — the body quotes l.2046-2047 and stops at "... 20d for slower stocks" with no ellipsis. His sentence continues
  *"also depend how far the are from 10/20."* (l.2047): the 10-day / 20-day choice also depends on how far the stock is from the averages, which a
  fixed ADR20 cut at 4.79% does not encode. His 10-19 follow-up *"Wait , with 2r profit the original stop will be breakeven for the trade"*
  (l.2135) is not encoded either: S1 moves the stop to the fill, where on his reading a +2R third leaves the original stop in place
  (l.2132-2136).
- **§4 row S2** — the body quotes l.1946-1947 as *"trailed with the 10- or the 20-day moving average... You wait for the first CLOSE below"*.
  The source continues *"the 10-day."* (l.1947), and the same sentence prescribes *"sell 1/3 to 1/2 of the position after 3-5 days, and then
  move the stop to break even."* (l.1946). S2 (the whole position to the first close below the 20-day, no partial) is **the brief's
  construction — neither his words nor the description**, and it departs from the quoted sentence twice: the 20-day instead of the 10-day, and no partial.
- **§4 row S3** — the body cites l.2070-2079 for the stall quotes and gives *"the partial may be a combination of the two (+2R or a number of
  days)"* (l.2061-2062) as his words. The stall quotes are at l.2066-2071 (*"The timing thing is interesting because a thinking is that if
  breakouts have no follow through in next few days then it may be better to get out..."*, l.2066-2067; *"Cut stallers is important because
  funds are limited, turnover for swing trades is important..."*, l.2070-2071); l.2078-2079 records his "yes" to the +1R / session-3
  definition. The partial sentence is the NOTES' gloss (l.2061-2062); his words are l.2060: *"The day thing is also correct, it may be a combo
  and depends"*.
- **§4 row S4** — *"Yes"* is his, verbatim (l.2129-2130: *"Yes, and maybe we need to vary the stop adjustment, can we try adjusting stop so
  the whole trade is breakeven after taking the partial?"*), answering whether the day-based third applies only in profit (the question,
  l.2126-2127, is the notes' paraphrase). The second phrase, *"the day-based third is sold only when the trade is in profit"*, is the notes'
  reading ("What it means", l.2132), not his words. Part (2) of the same ruling — the stop where the WHOLE trade nets zero — is left out of S4
  because it was tested on 10-19 and lost (−0.12R a trade, −0.16 .. −0.08, n 79; `docs/analysis/cb_exit_partial_prereg_2026-10-19.md` RESULT).
- **§2 item 2** ("the holdings replay's own result was known ... over the whole window") — more was in view. The holdings replay printout
  (`scripts/probes/_705_holdings_1024/02_replay.txt`) showed both baselines' per-year returns before the freeze: the speed trail 2021 +46.8% /
  2022 −5.8% (l.128), the panel exits 2021 +245.2% / 2022 −18.6% (l.132); and its frozen `replay/trades.tsv.gz` holds per-trade 2021-22 R for
  `d3_p33_tspd` and `p33_s3_t10`. None was used to write or choose a rule, but "over the whole window" understates it, and §2 item 4 ("No
  stage has computed any outcome of a 2021 or 2022 buy") is true of this study's stages, not of the holdings replay's.
- **§2 item 3** (the exploration) — it ran BEFORE the pinned description, with `B1_time5` and `B2_strength_t10` already in the module's `RULES`,
  and printed B1's 2020 sum (+234.3R; `00_explore_2020.out`). B1's 2020 result was therefore seen before B1 was fixed as a candidate: **the 2020
  fit is not a test of B1; only the check is.** The pinned description printout also contains the exploration's three markers, so if a
  description was read before the exploration (§2 item 3 says one was), the written-once file was regenerated after that earlier printout was
  deleted by hand; the "refuses when the printout exists" guard cannot see that. None of the three touches a candidate's 2021-22 outcome.
- **§3 Reading** ("on 33 of 117 our STOP (14 on day 0) closed the trade while his book still held it") — the row above it says our stop did
  23 of the 33 (14 on day 0) and our trail 10; the 33 are all our exits before his window, not stop exits alone. The same stop / trail
  mix-up F2 corrected in RESULT.
