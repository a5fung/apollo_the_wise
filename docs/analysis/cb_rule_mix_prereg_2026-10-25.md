# #705 — The rule mix: which of his rules explains which trade, and what the set covers together — pre-registration (2026-10-25)

**Status: REGISTERED, NOT FROZEN, NOT RUN.** His words (2026-10-25, verbatim, `docs/methodology/operator_shared_notes.md` l.2596, after
the intraday check): *"What seems to be the case is there's no 100% had rule, there's rules and discretion, so best to to categorize them
e.g. 20% rule X, 34% rule Y, etc. To see if we get the right coverage when summed together."* He said *"Ok"* to registering it. The method
line recorded with it (l.2598): list the candidate rules from his words per decision, tag each trade with the rule that explains it, report
each rule's share, and judge the set by its combined coverage — against what the same set covers by chance. **Outcome-free:** this
registration read the two previous registrations and their RESULTs (`cb_reverse_engineer_his_rules_prereg_2026-10-24.md`,
`cb_intraday_layer_prereg_2026-10-25.md`), their check printouts (`01_rev_check.txt`, `01_intra_check.txt`), the fit printouts
(`01_rev_enter_fit.txt`, `01_rev_exit_fit.txt`, `01_intra_{enter,stop,exit}_fit.txt`), the intraday dry-run printout (`01_intra_dryrun.txt`),
the exits study (`cb_his_exits_study_2026-10-24.md`), the per-trade TSVs' HEADER LINES only, the frozen intraday module's code as text (its
functions and docstrings; nothing run), and his words. **No price bar — daily or
minute — was opened; no outcome was computed; nothing of 2025-26 was opened (sealed).** Every number below is copied from those printouts
(each cited) or derived from dates and clocks. Measurement and registration only — nothing here changes or proposes to change a strategy,
entry, stop, exit, size, safeguard or live trade state (THE LINE). **The read is DESCRIPTIVE: it decides nothing** (§6).

**His words this tests, by decision (line cites into `operator_shared_notes.md`; stream captions by video id in `qm_streams/subs/`):**
- **Entry** l.1941-1942: *"Enter on the opening range highs. The opening range highs can be the highs of the first 1-minute candle, the
  5-minute candle or the 60-minute candle."* Or simply buy as the daily chart starts to break out (l.1942 — the notes' paraphrase of the
  article, NOT in quote marks there); l.2090-2092: *"(on the 60-minute timeframe the first candle is always only 30 minutes, 9.30-10 AM). You
  can use whatever timeframe or a combination of them. You don't even have to use any intraday chart, just look at the daily chart and enter
  when the stock is starting to break out."*; l.2093-2094: anticipating the breakout *"I don't find it as effective"*.
- **Stop** l.1943: *"Stop is always lows of the day and stop should not be wider than the ATR or ADR of the stock."*
- **Exit** l.1946-1947: *"sell 1/3 to 1/2 of the position after 3-5 days, and then move the stop to break even"*; the rest *"trailed with the
  10- or the 20-day moving average... You wait for the first CLOSE below the 10-day"* (and l.2095-2096: *"10- or the 20-day moving
  average. Depends on how fast the stock is"*); l.2046-2047: *"sell 1/3 at 2R then move to break even
  stop then trail rest at break of 10 or 20d ... 10d for faster stocks and 20d for slower stocks, also depend how far the are from 10/20"*;
  l.2060: *"The day thing is also correct, it may be a combo and depends"*; l.2066-2071 (stallers: *"if breakouts have no follow through in
  next few days then it may be better to get out"*; *"Cut stallers is important"*) and his *"yes"* (l.2078-2079) to the definition: no +1R by
  the close of session 3 → sold at that close; the FSLY captions (`cMkRsqvlVHM` 2020-07-14 ~00:52:28; `YwMoUTd4naQ` 2020-07-13 ~00:04:44):
  half sold when it *"broke below the 20 ... EMA on the 60-minute chart"*, the rest *"when it took out the previous day's lows"*.
- **His rule for a miss (2026-10-23):** a backtest that does not reproduce his profit is a defect in OUR implementation or interpretation.

## 0. In plain words

- **What the two previous reads left.** No SINGLE rule reproduces his entry, stop or exit: the best entry level was first crossed inside his
  buy window on 45% of his unseen trades (bar 50%); every stop level was held through on 20-33% of the untouched trades where price crossed
  it (25-61% on the 2020 fit; the 12 library cells, controls excluded); the 60-minute exit recovered none of the gap between our exits and his. **But one beside line already says what this read asks:** ANY
  of the three opening-range highs (1-, 5-, 30-minute) explains 55% of his 2020 in-session buys against 21% for a random price, and 62.5%
  against 30% on 2021-22 (`01_intra_enter_fit.txt` l.34, `01_intra_check.txt` l.30). The union of several rules carries more of him than any one.
- **What this read does.** For each decision — ENTER, STOP (on his losing exits), EXIT — a FIXED library of candidate rules, each traced to his
  words or labelled our reading, in a FIXED order. Each trade is tagged with the FIRST rule in that order that explains it; each rule's share,
  the union's coverage and the discretion remainder are printed — against the same library applied to random prices (entry) or to random
  windows of his sell window's width and random levels (stop, exit), so a union of many rules cannot look good by having many rules.
- **What it cannot do.** It cannot test anything on unseen trades: 2021-22 was the check for every level and variant here (L1-L9, E1-E4, the
  stop cells), the untouched years were their vetoes, and the 2020 numbers set the library ORDER. So the read reports 2020, 2021-22 and the
  untouched years side by side against chance and **decides nothing**. The only confirmatory tests left are the forward shadow and the one
  sealed 2025-26 strategy test (§6).
- **What it costs.** Nothing new: no fetch (the intraday fetch holds the warm-up, the hold and 20 tail sessions of every trade here, §8); one
  run after the freeze.
- **Action from him:** none. §11 decided by the main loop (2026-10-25; no money, not THE LINE).

## 1. The four questions of the standard

1. **Decision served:** how much of his trading is RULES (which rules, each with its share) and how much is discretion, per decision — so the
   forward shadow records the right candidate rules beside the live watch names. It informs which candidate rules the forward shadow
   records; it changes no branch of the sealed 2025-26 test (§6).
2. **What would change it:** nothing here is a bar; the read is descriptive (§6). What CAN change the readout's meaning is the chance line: a
   rule or a union that does not beat its chance coverage says nothing about him.
3. **Population:** §2 — the in-session buy windows (ENTER), his losing exits (STOP), his exits (EXIT), per block: 2020, 2021-22, the
   untouched years; the pre-market-flat windows beside.
4. **What would make this wrong:**
   - (a) **Survivorship, the panel's OCR, a position's missing side, a window that is not a day, a clock that bounds a minute and not a price**
     — inherited unchanged from the previous registrations (§1 of each).
   - (b) **Greedy tagging is order-dependent.** Two rules can both explain a trade (the 1-minute high and the 30-minute high are both first
     crossed inside the window); the first in the order takes the tag. The order is fixed here from his words and the 2020 printouts (§3);
     every rule's STANDALONE share is printed beside its greedy share, and the earliest-firing order is printed as a sensitivity (§4).
   - (c) **The order is in-sample on 2020.** The 2020 shares that set it were measured on the same 2020 trades the read tags. On 2021-22 the
     standalone shares are already printed (known) but the ORDER is new there; on neither block is any share a test of him.
   - (d) **A union of many rules covers more by chance.** Guarded by applying the SAME library, in the SAME order, to the controls (§5): the
     union's chance coverage is printed beside its real coverage.
   - (e) **Partials are invisible.** The panel sees the LAST share leave. A rule he acted on with half the position (FSLY: half on the
     60-minute close on 07-10, one to two sessions before the last share left on 07-13 / 07-14) reads as a rule that fired while he still held
     — a miss for that rule. **So
     every precision line is a FLOOR** (§4); FSLY 693 is the known answer that pins this (§9 gate ix).
   - (f) **The chance line depends on where the random window may fall.** A window placed into the tail after his sell catches fewer first
     firings (they happened inside the hold), which LOWERS chance coverage and flatters the read. Two placement ranges run; the harder one
     (inside the hold) is the comparison line (§5).
   - (g) **"Losing" is an outcome.** The STOP library runs on trades whose exit was a loss, defined at the run (the close of exit_hi below the
     registered fill); the sign can flip inside a multi-session window (`sign_ambiguous`, counted; exit_lo beside).
   - (h) **One cell is genuinely new.** The EXIT library on the 62 untouched undated trades (and the 60-minute rules on the 304 undated 2020
     trades) has not been read by any stage; everything else re-reads known firings under a new tagging (§2b). Disclosed, beside.

## 2. POPULATION — the previous registrations' sets as they stand, per decision

**The timeline is taken as is** (1,874 entries; the type gate, inverted windows and same-day re-buys out, in that order — the previous §2b; the
clock-sanity rule §2c of the intraday registration). Every set equals the previous registrations' counts (asserted by the dry run against
the intraday dry run's claims). Record floors as before (ENTER 20 bars before the buy day; STOP / EXIT 50). Counts are trades unless marked.
**This run's n is NOT the printouts' n.** The intraday fits excluded trades under their guard (5) (a fit trade whose span touched a check-side
trade): ENTER fit 1 of 90 (`01_intra_enter_fit.txt` l.11), STOP fit 16 of 453 (`01_intra_stop_fit.txt` l.11), EXIT fit 10 of 149
(`01_intra_exit_fit.txt` l.11). This read has no fit stage and runs every block once (`BarGuard(allowed_eids=None)`), so those trades RETURN:
the run's records are about 88 / 431 / 149 on those sets (the record floor still applies), printed by eid. The known-answer gates re-read
ONLY the eids present in each intraday TSV (§9).

| decision | block | set | n = records / scorable (as the previous printouts give them; this run adds the returning guard-5 trades) | role |
|---|---|---|---|---|
| **ENTER** | 2020 | in-session windows after §2c: 31 dated + 59 undated non-flicker (34 flickers beside) | 87 scorable deciding (30 + 57; `01_intra_enter_fit.txt` l.35, l.47); flickers 28 | the library tagged; the ORDER's source |
| ENTER | 2021-22 | 20 dated (7 flickers) + 43 undated non-flicker windows (19 undated flickers) | 40 undated non-flicker + 20 dated scorable (`01_intra_check.txt` l.18-19, l.31); flickers 19 | tagged; standalone shares known |
| ENTER | untouched | 9 non-flicker + 8 flickers (2019: 6 nf; APT 2020-01-23; CVNA, AI 2023) | 9 + 7 scorable (l.55, l.67) | tagged; ±33 points on 9 |
| ENTER beside | all | pre-market-flat windows: 2020 41 dated + 56 undated scored (58 in the population); 2021-22 41 + 52 scored (55 in the population) | as the printouts (`01_intra_enter_fit.txt` l.73-96; `01_intra_check.txt` l.81-104) | the open first by construction; **never summed with the in-session rows** |
| ENTER beside | all | no flat frame on the buy day; pre-market first sightings; `no_minutes` | counted per block | the composition line (§4c): the share of his buys that CAN be tagged |
| **STOP** (losing exits) | 2020 | dated 149 + undated 304 (flickers in), THOSE whose exit was a loss | the loss share is read at the run; the exits study's 2020 description: 49 of 117 filled dated exits below the fill at exit_hi (29 at or below −1R, 20 in (−1, 0)) | tagged |
| STOP | 2021-22 | dated 111 (110 records) + undated 226 (212), the losers | exits study 2021-22: 52 of 88 filled dated below the fill at exit_hi (28 + 24) | tagged |
| STOP | untouched | 62 undated (58 records) + 27 dated (26), the losers | few; printed with intervals | tagged |
| **EXIT** (all exits; losers / non-losers split beside) | 2020 | dated 149 | 139 scorable for the hit rate (`01_intra_exit_fit.txt` l.37) | tagged; the ORDER's source |
| EXIT | 2020 | undated 304 | the 60-minute rules UNREAD there (§2b) | tagged, flagged new-cell |
| EXIT | 2021-22 | dated 111; undated 226 | 107 armed / 199 scorable (`01_intra_check.txt` l.182-183, l.203) | tagged |
| EXIT | untouched | 27 dated (23 with exits on the timeline, 19 of them with windows ≤ 20 sessions; after the record floor 22 trades, 18 windows ≤ 20 sessions — the intraday veto's base); 62 undated | the dated read (veto); the undated UNREAD for every exit rule (§2b) | tagged; the undated flagged new-cell |

**2a. The sell window and the hit unit (kept).** The panel sees the last share leave inside [exit_lo, exit_hi] (one session wide on 80 of 101
of 2021's dated, `01_intra_dryrun.txt` l.35); a rule's firing is scored on windows ≤ 20 sessions (R17 / §7b of the intraday registration);
wider windows leave the denominator (§4b) and stay in the composition line. The buy day = session 1; the first red close is read from session 2 (R17).

**2b. Exposure — what was read where, per population × rule (constraint: nothing here is a test).**

| population | ENTER L1-L6 | ENTER L7-L9 | STOP S1 / S3 / S9 / S10 × T / C / H | STOP S4 | EXIT 60-minute and touch rules (M-1, M-2, M-2s) | EXIT daily rules (M-3..M-11) |
|---|---|---|---|---|---|---|
| 2020 dated | read (rev fit) | read (intra fit) | read (intra fit) | S4-T / C read (rev fit); S4-H unread | read (intra fit, 139) **with the chain's stop pre-empting** — 67 of 139 walks stopped first, so the 60-minute firing after the stop's session is UNREAD on those | read (exits study, 117 filled; rev EXIT fit features) |
| 2020 undated | read | read | read | S4-T / C read; S4-H unread | **UNREAD** (the intraday EXIT fit was dated 2020 only) | read as features (rev EXIT fit X1-X10; the trivial exits) |
| 2021-22 dated | read (rev + intra checks) | read (intra check) | read (intra check, beside) | S4-T / C read (rev, beside); S4-H unread | read (intra check, 107) with the stop pre-empting (56 of 107) — as above | read (exits study; rev EXIT fit in-sample) |
| 2021-22 undated | read | read | read | S4-T / C read (rev check) | read (intra check beside, 199) | read (rev EXIT check: the list, the trivial exits) |
| untouched dated 27 | read (intra veto, 9 windows incl.) | read | read (beside) | unread | read (intra veto, 22 / 18) | read (exits study beside; rev EXIT fit) |
| untouched undated 62 | — (no in-session windows beyond the 9 + 8 above) | — | read (intra check, DECIDING) | unread | **UNREAD** | **UNREAD** |

So the NEW cells are: the EXIT library on the 62 untouched undated trades and the 60-minute rules on the 304 undated 2020; S4-H everywhere and
S4 on the untouched block; the extension / big-up-day markers on undated trades (the exits study described dated trades only); **and the
no-stop first firing of M-1 / M-2 / M-7 on every trade the frozen walk stopped first** (67 of 139 on 2020 dated, 56 of 107 on 2021-22 dated,
44 of 200 on 2021-22 undated — `01_intra_exit_fit.txt` l.43, `01_intra_check.txt` l.185, l.205), because this read's `first_fire` runs without
a stop (§9). Every other cell re-reads known firings. **What is new EVERYWHERE is the tag** — the first-rule assignment, the union, the remainder, the precision lines and the
random-window controls — none of which any stage has computed.

## 3. THE LIBRARIES — fixed rules, fixed order (his words first, then the 2020 printout's share; ties → the order he named them)

**The order rule, stated once:** tier 1 = a rule his words state, even where its level or its all-out is our operationalisation (labelled);
tier 2 = a rule only we propose (a different trigger from the one he names — a close below where he says a touch or "took out", a level he
names only as a cap — is our proposal). Within a tier, descending by the 2020 printout number named in the table (the SOURCE and n differ by
rule — the two ENTER fits scored 89 and 87 windows, the exits study 117 filled trades, the intraday EXIT fit 139 — the order is taken as
printed, never re-measured); **a rule that is a strict subset of another sits directly before it** (M-5 before M-9); a rule with no 2020
number sits last in its tier; ties among those → the order fixed in the table (M-2s, then M-11). The rule IDs are names; **the table's row
order is the order.** The order is a constant in the module (`LIBRARY[decision]`), printed by the dry run with each source.

**3a. ENTER (in-session windows). Level definitions are the frozen modules' (dated breakout rows keep max(level, pivot); the raw level beside).**

| # | rule | definition (exists from) | source | ordering number (source; taken as printed) |
|---|---|---|---|---|
| E-1 | **L1** the 5-minute opening-range high | max high of minutes 0-4 (09:35) | his words l.1941-1942 | feasible 36.0% on 89 (`01_rev_enter_fit.txt` l.12); the intraday re-read on 87: 36.8% (`01_intra_enter_fit.txt` l.27) |
| E-2 | **L8** the 30-minute high — his "60-minute first candle" | max high of minutes 0-29 (10:00) | his words l.1941-1942, l.2090 | 34.5% on 87 (`01_intra_enter_fit.txt` l.25) |
| E-3 | **L2** the prior session's high | daily | a READING of his words — *"enter when the stock is starting to break out"* (l.2091-2092; the notes' paraphrase at l.1942 says the same) names no level | 18.0% (`01_rev_enter_fit.txt` l.13); re-read 18.4% on 87 (l.28) |
| E-4 | **L7** the 1-minute opening-range high | the 09:30 minute's high (09:31) | his words l.1941-1942 | 16.1% (`01_intra_enter_fit.txt` l.24) |
| E-5 | **L3** the base high / breakout level | the candidate row's pivot; undated: the prior-20-session high | a READING of his words (as E-3) | 13.5% (`01_rev_enter_fit.txt` l.14); re-read 13.8% on 87 (l.29) |
| E-6 | **L9** the prior completed 60-minute bar's high | the runner's clock-anchored bars; differs from L8 only from 11:00 | our reading (the intraday §5a; caption `tnHw5CKxcH4` names the 60-minute range for an ADD) | 34.5% (l.26) — tier 2, so after E-1..E-5 whatever its share |
| E-7 | **L4** the open | the 09:30 open | our reading ("pre-market buys"); **almost never feasible on an in-session window** (the open trades before any in-session flat frame; only a re-cross of the open after a dip counts): 1 of 87 on 2020 (`01_intra_enter_fit.txt` l.30), 0 of 40 deciding, 0 of 20 dated and 1 of 19 flickers on 2021-22 (`01_intra_check.txt` l.26, l.38, l.50) | 1.1% (`01_rev_enter_fit.txt` l.15) |
| — | discretion | no rule above explains the window | — | the remainder |

Not in the library, by rule: L5 the prior close (an EP gap level, 1.1% / 5.0%; the EP rows' "buy the ORB high" is already E-1 / E-2) and L6 the
first-hour high (our earlier mis-reading of his 60-minute candle, superseded by L8) — both printed as re-reads, never tagged.

**3b. STOP — on his LOSING exits. Cells (level × variant) as the frozen intraday module reads them (S4 added from the reverse read).**

| # | cell | level | variant | source | 2020 ordering number |
|---|---|---|---|---|---|
| S-1 | **S1-T** | the low of the day up to the fill minute | touch | his words l.1943 *"lows of the day"* | tier 1 alone |
| S-2 | **S10-T** | the last completed 60-minute bar's low before the read minute | touch | our reading (the "60-minute lows" of the option-1 ruling; `S10_is_S1` when read inside the first bar) | median width 2.8% (`01_intra_stop_fit.txt` l.49) |
| S-3 | **S10-H** | same | 60-minute close below | our reading | after S-2 (fire order T → H → C within a level, §4) |
| S-4 | **S10-C** | same | daily close below | our reading | after S-3 |
| S-5 | **S9-T** | the 09:30-10:00 low | touch | our reading (his "first candle" low; `S9_is_S1` before 10:00) | 2.9% (l.46) |
| S-6 / S-7 | S9-H / S9-C | same | H / C | our reading | after S-5 |
| S-8 | **S1-H** | the low of the day at the fill | 60-minute close below | our reading (a close below, where his words name the low itself) | 3.2% (l.42) |
| S-9 | **S1-C** | same | daily close below | our reading | after S-8 |
| S-10 | **S3-T** | the prior session's low | touch | our reading (his FSLY words name it as an EXIT on a winner — M-2, tier 1; as a stop on a loser it is our transfer) | 5.6% (l.43) |
| S-11 / S-12 | S3-H / S3-C | same | H / C | our reading | after S-10 |
| S-13 | **S4-T** | one ADR20 below the fill | touch | our reading of l.1943's cap (*"not wider than the ... ADR"*) used as a level | last by definition (one full ADR20 against medians under 6%) |
| S-14 / S-15 | S4-H / S4-C | same | H / C | our reading | after S-13 |
| — | discretion | no cell breached inside the sell window | — | the remainder |

The controls S8 (two ADR20) and the 50-day are not in the library (never his stop). **Order within tier 2 = tightest median width first (the 2020
stop fit's printout), variants T → H → C within a level** (a touch precedes the 60-minute close, which precedes or equals the daily close —
gate (iii) of the intraday read: a C event implies an H event up to the auction band). This differs from the module's tie constant
`STOP_VARIANT_TIE` (T, C, H — a tie-break on width for CHOOSING a stop); here the order is by fire time within a level, stated.

**3c. EXIT — on ALL exits (the losing / non-losing split beside). The LAST share's session is what the panel sees.**

| # | rule | first firing = | source | 2020 ordering number |
|---|---|---|---|---|
| M-1 | **the 60-minute 20-EMA close** | the first clock-anchored 60-minute bar closing below the 20-EMA from the first completed bar after the fill (E1's trigger; the 65-bar warm-up floor, `ema_thin` abstains) | his words (the FSLY captions name the trigger); "all out" at it is OUR reading of the last share | E1 last-leg hit 40.3% on 139 (`01_intra_exit_fit.txt` l.37) |
| M-2 | **the prior session's low, touched** | the first intraday touch from the armed bar's close (E4; = E3's last leg — E3 collapses onto it for the panel: 39.6% both) | his words (FSLY: *"took out the previous day's lows"*) | 39.6% (l.37) |
| M-3 | **the 10-day average, first close below** | from the buy day's close on (session 1) | his words l.1946-1947, l.2046 | within his window 39 of 117 = 33.3% (exits study §3) |
| M-4 | **the 20-day average, first close below** | as M-3 | his words l.1946-1947, l.2046 | 28 of 117 = 23.9% (exits study §3) |
| M-5 | **the session-3 stall cut** | the close of session 3 when no +1R (the day-0 peak or any high) was reached by then | his "yes" l.2078-2079 to the definition | an upper bound only: 16 of 21 stallers left by session 3 (exits study §3) → ≤ 13.7%; a strict subset of M-9, so it sits directly before M-9 |
| M-9 | **the close of session 3** | the buy day = session 1 | his words l.1946 (*"after 3-5 days"*) and l.2060 (*"The day thing is also correct"*); all out at it = our reading (his words name a 1/3-1/2 partial) | 20.1% on 139 (l.40) |
| M-6 | **+2R** | the first session whose high reaches the fill + 2R under the registered stop's width | his words l.2046 (*"sell 1/3 at 2R"*); all out at it = our reading | 12 of 117 = 10.3% (exits study §3) |
| M-2s | **the prior session's low touched ON OR AFTER the first 60-minute close below the 20-EMA** — his FSLY SEQUENCE | armed at M-1's bar close; the first intraday touch of the prior session's low from that minute on (M-1 abstaining → M-2s abstains) | his words (the FSLY captions, read as the sequence they state: the break of the 20-EMA first, the prior low after it) | no 2020 number printed (E3's touch leg is armed from the fill, not from E1's bar) → after the numbered tier-1 rules, before M-11 |
| M-11 | **the close of session 5** | — | his words l.1946 (*"after 3-5 days"*), l.2060; all out at it = our reading | no 2020 hit rate printed → last in tier 1, after M-2s |
| — | **tier 2 — rules only we propose** | | | |
| M-7 | **the prior session's low, daily close below** | from the armed session on (E2's last leg) | our reading (a daily close below, where his word was *"took out"* — a different trigger; E2 is our reading) | E2 last-leg hit 40.3% on 139 (l.37) |
| M-8 | **the first red close** | close < prior close, from session 2 (R17) | our reading (the exits study's description) | 31.7% on 139 (l.40) |
| M-10 | **an extension or big up day** | close ≥ 10-day × (1 + 2.0 ADR20), or close ≥ prior close + 1.5 ADR20 (the exits study's fixed markers) | our reading (the brief's example; the description did not support it) | extension 13 / big up 6 of 117 (exits study §3) → ordered on 11.1% |
| — | discretion | no rule above fires inside the sell window | — | the remainder |

Beside, never tagged: a 20-bar plain average in M-1's place (other captions say *"20ma"*); a "second close below" M-1; the previous read's
3-rule daily list (in-sample on dated 2021-22 — a known 50.5% there, `01_intra_check.txt` l.184). **M-5 fires only on session 3 and only
without +1R; M-9 fires on every session 3 — so with M-5 ahead in the order, M-9's greedy share reads "session-3 sells on trades that HAD
reached +1R".** Stated so the table reads right. **The ordering numbers of M-1, M-2 and M-7 are the frozen walk's hit rates WITH the chain's
stop pre-empting the leg** (a stopped walk's `last_j` is the stop's session, a hit when it fell in his window) — they order the library as
printed; they are NOT this read's standalone shares, which run without a stop (§4a, §9 gate viii-b) and are new numbers (§7). **M-2s takes a
tag only in the FSLY shape:** the unconditional prior-low touch (M-2) came early (MISS-EARLY), the 60-minute close (M-1) came before the
window, and the first touch AFTER that close lands inside it — the sequence his words state. When the first touch already lands inside the
window, M-2 (earlier in the order) takes it.

## 4. THE TAGGING RULE — first firing, four buckets, the greedy tag, the standalone share, precision

**4a. Per trade and per rule, the rule's FIRST firing** (the first session — and minute, where intraday — at or after the point the rule is
armed: ENTER from the level's existence minute; STOP / EXIT from the fill, the 60-minute rules from the first completed bar after the fill
(`armed_index`), E2's daily leg from the armed session (C15)), then ONE of four buckets:
- **EXPLAINS** — ENTER: the level's first crossing minute lies in (flat_clock, first_clock] (feasible, the frozen `score_level` /
  `score_new_fixed` / `score_l9`). STOP / EXIT: the first firing's session (as the table below defines it) lies in [exit_lo, exit_hi] (a
  touch on exit_lo counts whatever its minute — the window is the unit the panel gives, and the controls have no frames).
- **MISS-EARLY** — ENTER: crossed at or before flat_clock (he was provably flat after the break). STOP / EXIT: the first firing's session is
  before exit_lo on a session he CERTAINLY held (the intraday §6a certainty rule, reused: on the buy day an event at or after first_clock is
  certain, at or before flat_clock is not an event and the scan goes on; sessions between the buy day and exit_lo are certain). **A rule
  that fired early and again inside the window does NOT explain the trade** (first firing only).
- **UNRESOLVED** — a buy-day firing between the later of (fill minute, flat_clock) and first_clock; a trade with no in-session holding frame
  on the buy day makes every buy-day firing unresolved (the §6a rule, through the frozen `held_through_intra` for the stop cells and the
  same clock test for the exit rules); **and a firing that comes after any `no_bar` / `no_minutes` session between the armed point and the
  firing** (the missing session could hold an earlier firing, so missing data never upgrades MISS-EARLY to EXPLAINS) — in the real tag and in
  every control alike. Counted; in neither numerator.
- **NEITHER** — never fires by exit_hi (ENTER: not crossed by first_clock), fires after exit_hi, or abstains (`no_minutes`, `no_level_yet`,
  `ema_thin`). A window wider than 20 sessions is not NEITHER: it is outside the denominator (§4b).

**Which session a firing is compared with [exit_lo, exit_hi] — per rule (the booked session: the session the sale is booked in).**

| rule | session compared | why |
|---|---|---|
| M-1 | the bar's own session; a close below on the day's LAST 60-minute bar → the next session (booked at its open) | equals the frozen `exit_walk_intra`'s E1 booking (`jb = j + 1` there), so gate (viii-b) compares like with like |
| M-7 | the next session (booked at its open); no next bar → the close's own session | equals E2's daily leg in the frozen walk |
| M-2, M-2s, every STOP touch (T) | the touch's own session | booked at the level the same session |
| every STOP H cell | as M-1 | the same 60-minute close |
| M-3, M-4, M-5, M-6, M-8, M-9, M-10, M-11, every STOP C cell | the close's (or, for M-6, the high's) own session | equals the frozen trivial exits (`rev.trivial_sell_days` / `rule_fire_day`) that gate (viii-c) re-reads |

The ordering numbers of §3 were printed under their own sources' conventions and are not re-measured. **Consequence, stated:** a 60-minute
close below on exit_hi's LAST bar books on the next session, so on a one-session window (80 of 101 of 2021's dated) it reads NEITHER. That is
the frozen walk's convention; the printed 40.3% already carries it, and gate (viii-b) requires it.

**From the frozen `held_through_intra` output to the four buckets (STOP cells; the exit rules use the same mapping on their own first firing).**

| frozen output | bucket |
|---|---|
| `first_j` < exit_lo_j and `certain` | MISS-EARLY (a C cell's buy-day close: R16 below) |
| `first_j` in [exit_lo_j, exit_hi_j] (whatever `certain` says on exit_lo) | EXPLAINS — the window unit, the same as the controls |
| `unresolved` on the buy day (or after a missing session, above) | UNRESOLVED |
| no `first_j` by exit_hi_j | NEITHER |

On exit_lo the frozen function reads a touch before the last in-session frame as "held through"; this read counts it as EXPLAINS (the window
unit). The count of **EXPLAINS on exit_lo contradicted by an in-session frame that day** is printed per rule and block beside the shares.
**One exception to the mapping (R16, chosen at the second check's fix 2026-10-26 by §4a's own sentence; no money, not THE LINE):** the frozen function applies no
buy-day clock test to a C cell (`if j == 0 and variant != "C"`) and reads a buy-day close below the level as `certain`; this read applies
§4a's buy-day rule to it, as it does to the exit daily rules (M-3, M-4, M-7, M-10) on the same close — no in-session buy-day frame →
UNRESOLVED; a flat frame after the close → not an event, the scan goes on. So the stop C cells and the EXIT library read the same close
alike. Gate (viii) still compares the frozen fields; the (trade, C cell) pairs R16 moves are counted beside the STOP table.

**4b. The greedy tag** = the first rule in the library order whose bucket is EXPLAINS; none → **discretion**. Printed per rule and block:
**greedy share** (tagged ÷ scorable), **standalone share** (EXPLAINS ÷ scorable — the previous reads' feasible share / hit rate, re-read),
**precision** = EXPLAINS ÷ (EXPLAINS + MISS-EARLY) — how often, when the rule fired by his sell, he acted on it (ENTER: feasible ÷ crossed by
first_clock); **a floor** (constraint e), **the union's coverage** = 1 − discretion share, each with its 95% binomial interval and n. **Beside:
the tag under the EARLIEST-firing order** (the rule that fired first in clock time takes the tag; ties → the library order) — the sensitivity
of the greedy order; and the standalone shares under the previous reads' definitions, which must re-read exactly (gate viii).

**Scorable — ONE per-trade denominator for every rule and every control of a decision.** ENTER: an in-session window after §2c with a
record and minutes (the previous reads' scorable). STOP / EXIT: the sell window is ≤ 20 sessions; the record exists (floor 50 bars); the
frozen `exit_hit` scorability holds (`J_tail` ≥ exit_hi_j, no hole cut before the window); and control (a) has room (at least 2 placements,
§5). A trade outside it is counted in the composition line, never in a share. The trades that fail ONLY the room test are printed beside
with their real buckets and their n. **The room test applies to the tag and the controls only:** every gate-(viii) share is computed on the
TSV's own scorable rows (the frozen `exit_hit` / trivial-exit base, which keeps the buy-day windows), never on this denominator. The
random-level control's own `no_room` (a hold whose lowest low is not below the fill) prints its chance share on its scorable subset, with n.

**4c. The composition line (ENTER).** Per block, every buy after §2b: in-session window after §2c (taggable) · pre-market-flat window (the
open first by construction — beside) · no flat frame on the buy day · pre-market first sighting (no window; degrades to "crossed that
session", as before) · `no_minutes` · dropped by §2c. So the reader sees what share of his buys the library CAN speak to. For STOP / EXIT: the
losers' share of exits per block (at exit_hi; at exit_lo beside; `sign_ambiguous` counted), windows > 20 sessions, still-held trades.

**4d. The R unit and the fill.** Neither ENTER nor STOP passed its check, so the chain carries the REGISTERED fill (ORH5 where it filled, the
close-fill proxy on the dated unfilled, the open of lo for undated) and the registered stop's width (the low of the day at the fill, dated;
one ADR20, undated) — the R unit of M-6 and the "losing" test. Stated, never fit.

## 5. THE CONTROLS (deciding nothing; each names the failure it guards)

- **ENTER, the single random-price control (kept; identical draws):** 200 seeded closes of random minutes of the session (seed 702, key
  `rev|minute`) scored as a level. **It is every rule's STANDALONE chance floor (21.0% on 2020, 30.0% on 2021-22 — the share a random price
  is first crossed inside the window).** "Identical draws" is made true, not assumed: the draws come from ONE shared generator, so the stream
  is replayed over the EXACT previous draw population in its (buy day, eid) order, unscored records included, and only then read on this
  run's records. Gate (vii) re-reads 31.7% / 85.9% on the previous 41 undated 2021-22 records; gate (viii) re-reads the per-row
  `control_feasible`, `control_hit`, `union_feasible`, `union_shift_feasible` columns of the ENTER TSVs.
- **ENTER, the k-price random control (NEW) — the chance line for the UNION and for the greedy chance shares.** One random price cannot
  stand for 7 levels: the real union asks whether ANY of 7 levels is first crossed inside the window. Per record and draw d, k = 7
  random-minute closes (key `mix|rprice|{eid}|{d}|{i}`, i = 1..7, seed 702, through the frozen `rng_for`), price i standing for library rule
  i: the first price in the library order first crossed inside the window takes the greedy tag; the draw is "explained" if any is.
  Independent prices are the HIGH bound on chance for levels that move together. 200 draws per record. The ENTER `mix` label must beat this
  union (§6); the single-price line stays the per-rule floor.
- **ENTER, the shifted-window controls: per-rule chance shares and the union's.** (1) **The frozen per-level control (kept, for the gate
  re-reads):** each level inside its own trade's window width at 200 random starts (key `intra|bracket|{eid}|{level}|{draw}`, seed 702;
  `no_room` counted). Draw d is therefore 7 DIFFERENT windows, one per level, not one shifted window: its union is a union of 7 independent
  per-level windows — a high bound on chance, stated so. (2) **The shared-window control (NEW):** one start per draw (key
  `mix|bracket|{eid}|{draw}`, seed 702, 200 draws), uniform over [09:31, the session close − width]; every level scored in that SAME window
  (a level that does not yet exist at the window's end is not feasible); the library order applied → per-rule greedy chance shares and a
  chance union that model one random window.
- **STOP / EXIT, the random-window control (NEW): a window of his sell window's width placed along the trade's path, EVERY placement
  enumerated exactly with equal weight** (the integer starts on the record's own calendar — few per trade, so no sampling and no seed), the
  SAME library in the SAME order tagged inside each placement (first firing from the armed point; MISS-EARLY = fired before the placement's
  start; the booked-session table and the missing-session rule of §4a apply unchanged). Two placement ranges, both printed:
  - **(a) inside the hold — the comparison line:** starts s in {0 .. exit_lo_j} in offsets (session 1 = offset 0; exit_hi − width + 1 =
    exit_lo), his own window included. A trade whose window starts on the buy day (exit_lo_j = 0) has ONE placement — his own — so (a)
    cannot place a random window there → `no_room`. Those trades include the buy-day sells (16 of 117 2020 dated windows ended on the buy
    day, exits study l.58). **So real and chance are compared on the SAME trades: those with at least 2 placements in (a)** (§4b); the
    `no_room` trades' real buckets are printed beside with their n. HARDER: first firings cluster in the hold, so chance coverage runs high.
  - **(b) hold plus tail:** starts in {0 .. exit_hi_j + 20 − width + 1} (the fetched tail; a path cut by a hole, the horizon or the data's
    end is bounded there, counted). EASIER (constraint f): a window in the tail catches fewer first firings. Printed beside as the other
    bound, on the same trades as (a).
  The width is `exit_hi_j − exit_lo_j + 1` on the record's own calendar (C12).
- **STOP / EXIT, the random-level control (NEW) — so STOP / EXIT, like ENTER, must beat a LEVEL control as well as a timing control.** A
  seller who reacts to any weakness beats a timing control with any "price drops below X" rule. Per trade and draw d (200 draws, key
  `mix|rlevel|{eid}|{d}`, seed 702, through `rng_for`): a level uniform between the hold's lowest low (from the fill minute through exit_hi)
  and the fill; its first touch from the armed point, scored with the same buckets in his real window. A hold whose lowest low is not below
  the fill → `no_room`, counted. `carries` for a STOP or EXIT rule is held against the LARGER of control (a) and this control (§6).
- **The precision line (every decision):** EXPLAINS ÷ (EXPLAINS + MISS-EARLY) per rule — the rule's "fired while he held and he did not act"
  rate is its complement. On the controls the same line is printed (a random window has its own early firings).
- **The trivial exits are no longer controls** — the session-3 and session-5 closes and the first red close are LIBRARY rules here (M-5, M-8,
  M-9, M-11); the random-window and random-level controls take their guarding role.
- **The ambiguity control of WHY-lite** is not run (no caption join here).

## 6. THE INFERENCE — what a share means, and what this read does NOT decide

- **A library's reading, per block:** the union's coverage against the chance union; the discretion remainder; the per-rule greedy shares with
  precision. **The chance share a rule is held against, named:** ENTER — the LARGER of the single random-price floor (21-30%) and the
  rule's shifted-window share (the intraday PASS rule's "beat BOTH controls"). Why both: L8 read 45.0% on the deciding 2021-22 windows
  against the check's own random-price control of 30.0% (`01_intra_check.txt` l.21, l.29; the intraday read failed it on the absolute 50%
  bar) — against its shifted share alone (3.6%) it sits 41 points over chance, against the random-price floor exactly 15.0 points over,
  the bar's edge, so there its label turns on precision. STOP / EXIT — the LARGER of control (a) and the random-level control (§5). **Labelling
  convention for the table, fixed now (a label, not a verdict), printed per block, compared on the printed one-decimal percentages:** a
  STANDALONE share ≥ 15 points over that chance share
  AND precision ≥ 50% → `carries`; within 5 points of it → `chance`; more than 5 points UNDER it → `below chance`; the rest → `weak`. **A
  rule's summary label is `carries` only when it is `carries` on BOTH 2020 and 2021-22, each against its own chance line** (the greedy
  share is printed beside, never labelled — it depends on the order). The union is labelled `mix` when it beats the chance union by ≥ 15
  points on BOTH 2020 and 2021-22, else `no mix` — ENTER: the LARGEST of the k-price union, the shared-window union and the per-level
  shifted union; STOP / EXIT: the larger of control (a)'s union and the random-level control's union. Every comparison is on the SAME
  trades (§4b: STOP / EXIT trades with room in (a)). These labels order the next registration's candidates; they move no rule, threshold,
  size or safeguard (THE LINE), and they are not a PASS / FAIL.
- **Why nothing is decided here (constraint c):** 2021-22 was the check for L1-L9 and E1-E4 and every stop cell; the untouched years were their
  vetoes; 2020 set the order. There is no unseen trade left to test a tag on. The read is the DESCRIPTION the ask names (*"20% rule X, 34% rule
  Y"*); the two blocks side by side against chance show whether the mix is stable across years, which is information, not evidence.
- **The only confirmatory tests left, named:** (1) **the forward shadow** — each library rule's firing recorded beside the live watch names
  (PLAN #705 (c): a recorder change beside `cb.ARMS`, no order path; adding an arm is his sign-off — this doc proposes none), read by the
  forward read when it has settled entries; (2) **the sealed 2025-26 strategy test, ONCE**, whose branch table is the intraday §11's
  (universe = SELECT's PASSED set; entry / stop / exit words-based unless a check passed — none did) — this read changes no branch of it.
- **What a BROKEN pipeline prints (so the expected shape confirms nothing):** NOT always chance. A wrong day, symbol, calendar or clock
  randomises the firings and reads near chance; but **WOULD-FAIL-IF: a scan-origin bug (a first-firing scan that starts at the window, or
  at the random window, instead of the armed point) turns every MISS-EARLY into EXPLAINS, so the real data reads ABOVE chance with
  precision near 100% on every rule.** A near-100% precision is an alarm, not a finding. Which gate catches which failure: wrong symbol or
  session — gate (i); a consistent calendar offset (which gate (i) cannot see, since it compares the SAME (ticker, session) both ways) —
  gates (viii) and (x); a clock shift — gate (i)'s clock arm (a one-minute-late stamp empties minute 0 on every session; the open / close
  arm reads such a shift within about a point of its 90% bar) and gate (viii) ENTER's cross minutes row for row (only where the TSVs came
  from other files); the 60-minute builder — gates (ii) and (viii-a); the daily rules' session index — gate (viii-c); the scan origin —
  gate (viii) (`_certain` row for row), (viii-b), (viii-c) and (x). The known-answer gates certify the run, never the shape of the result.

## 7. Expectations, written now (guesses to be scored, never targets; a miss changes nothing)

- **Known already, restated as the floor of ENTER:** the union of L7 / L1 / L8 is 55.2% on 2020 (87) and 62.5% on 2021-22 (40) against the
  random-price control 21.0% / 30.0% and the shifted-window union 6.5% / 6.7%; on the 20 dated 2021-22 windows 65.0% vs 32.7% / 15.2%; on the
  untouched 9, 33.3% vs 3.3% / 4.0%; flickers 2021-22 52.6% vs 22.5%. Those chance lines are the SINGLE random price and the per-level
  shifted union; the k-price and shared-window unions (§5) are new numbers. **Guesses:** adding L2, L3, L9 and L4 lifts the union 4-10 points
  (2020 60-65%, 2021-22 66-72%); the per-level shifted union moves by less than 2 points (L4 is almost never feasible in-session, L9 differs
  from L8 only from 11:00); the k-price union runs well above the single price (a guess: 35-55%), so the ENTER `mix` label is not assured. Greedy shares: L1 about 36% / 35% (first in order, so its greedy share equals its standalone share); L8 adds 12-20 points; L2 3-6;
  L7 2-5; L3 1-3; L9 0-3; L4 about 0-1. Discretion 28-40%. Precision: L7 lowest (the 1-minute high is crossed before most in-session flat frames —
  30-50%); L1 and L8 55-75%. The earliest-firing order moves the L7 / L1 / L8 split, not the union.
- **STOP on losers:** losers are 40-55% of exits per block (the exits study's 52 of 88 on 2021-22 dated is the filled-exits subset only). S1-T greedy share 20-35% (the exits study: 29 of 117 2020 exits at or below −1R
  where the low-of-day stop would have taken every one — but S1 was held through on 44% of the fit trades where price crossed it, so its
  first touch is often MISS-EARLY); S10 / S9 touches add 10-20 points; S3 cells 10-20; S4 under 10. Union 55-75%; chance union (a) 35-55%,
  (b) 20-40%; the random-level control 30-50%. Precision for S1-T 50-65%.
- **EXIT on all exits:** known on the dated blocks are M-8 (the first red close 31.7% / 25.2%) and M-9 (the session-3 close 20.1% / 14.0%),
  which no stop touched — on the printouts' base (buy-day windows kept); this read's standalone on §4b's base (room in (a)) is a slightly
  different number, and the exits study's 2020 within-window counts for M-3, M-4, M-6, M-10. **M-1, M-2 and M-7's standalone shares are
  NEW numbers:** the printed 40.3 / 39.6 / 40.3 (2020) and 38.3 / 35.5 / 36.4 (2021-22) were scored with the chain's stop pre-empting the
  leg on 67 of 139 and 56 of 107 trades; without a stop those trades' first firing can land earlier, later or inside the window — direction
  unknown. Guesses: the no-stop M-1 standalone 30-45% on 2020 dated; the union 65-80% on 2020 dated, 60-75% on 2021-22 dated, 55-70% on
  the undated blocks; chance union (a) 45-60%, (b) 30-45% — the lift over (a) 15-25 points. Greedy (the §3c order): M-1 30-45% (first in
  order, so its greedy share equals its standalone share); M-2 adds 5-12; M-3 5-10; M-4 2-5; M-5 3-8; M-9 2-6 (session-3 sells after +1R);
  M-6 1-3; M-2s 2-6 (it takes a tag only in the FSLY shape); M-11 0-3; the tier-2 rules (M-7, M-8, M-10) 3-10 together. Precision (floors): M-3 ≈ 65% (39 within vs 21 fired-while-held in the exits study), M-4 ≈ 74%, M-8 ≈ 40%,
  M-6 ≈ 17%, M-1 45-60%; **M-2 LOW, 25-45% — the prior day's low is touched routinely on a multi-session hold, so its unconditional first
  touch is often early**; M-2s higher than M-2 (the sequence filters the routine touches). The losers' EXIT-library remainder is larger than
  the non-losers' (a stop is not in that library).
- **The new cells** (the EXIT library on the 62 untouched undated; the 60-minute rules on the 304 undated 2020): shares within 10 points of the
  neighbouring blocks' — a larger gap is a population-shift note, never a finding.
- **FSLY 693 (gate ix):** gate (ix) pins only what his words and the gate-(vi) printout establish: M-1 is not EXPLAINS and not NEITHER, and
  its first firing is on or before 2020-07-10 (one session before exit_lo 07-13 on the calendar; 07-11 and 07-12 are a weekend) — so
  MISS-EARLY or UNRESOLVED; M-2 and M-2s are not NEITHER and each fires on or before 07-13. **Whether 07-10 is M-1's first close below
  since the 06-29 fill, and 07-13 M-2's first touch, is not established** (a 10-session undated hold with no in-session buy-day frame, so a
  buy-day firing reads UNRESOLVED; an earlier touch is likely). The expectation, not the gate: M-1 MISS-EARLY, M-2 MISS-EARLY, M-2s takes the
  tag; if M-2's first touch is 07-13, M-2 takes it. Either way his HALF-sale on M-1 reads as a miss for M-1 — the floor of §4b.

## 8. DATA GATE (STEP 0) — nothing new to fetch

- **Eras, exports, loaders, G8, the 2025-26 seal — unchanged** (era A = `cb702_pre_v2`, era B = `cb702` cut at 2024-12-31 and asserted; era by
  buy day ≤ 2022-03-31 A, else B; the holdings loaders through the frozen modules; `trade_impact.py` before any number).
- **Minutes:** the intraday fetch (`/Users/alvinfung/apollo_data/cb702/minutes_intra_1025/`, 19,470 pairs: 10 warm-up sessions + the buy day +
  the hold + 20 tail sessions for fit 2020, the untouched block and 2021-22; 19,184 ok, 286 empty at the source — `01_intra_dryrun.txt` l.49)
  covers every session this read
  walks, including control (b)'s tail. The dry run asserts coverage per block from the fetch logs ONLY (no minute file opened), lists the
  empty pairs by set, and writes `pending.psv` (expected empty). A pair still missing: ENTER `no_minutes`; for STOP / EXIT a missing session
  between the armed point and a rule's firing makes that firing UNRESOLVED (§4a — never skipped, so a missing day cannot hide an earlier
  firing), in the real tag and the controls alike; every abstention counted, nothing silent. The frozen `held_through_intra` skips a
  `no_bar` session; this module checks for one before the returned `first_j` itself.
- **Daily bars:** the exports hold every session of M-3 / M-4 / M-6 / M-10 and the random windows (the tail ends ≤ 2024-01 for the 2023
  still-held trades; nothing of 2025-26).
- **One calendar per record** (the intraday §11c, guard 10): every offset — the buy day, exit_lo, exit_hi, the tail, every random window's
  start — is a bisect on the record's own export calendar; the width in sessions likewise (C12).

## 9. Files, the module, its gates and guards

- **Inputs (pinned at the dry run):** everything the intraday registration pinned (its §12; carried through the frozen module's `pins`), plus the
  intraday fit and check printouts and per-trade TSVs this read re-reads (`intraday/enter_fit_trades.tsv`, `check_enter_trades.tsv`,
  `stop_fit_trades.tsv`, `check_stop_trades.tsv`, `exit_fit_trades.tsv`, `check_exit_trades.tsv` — gate viii), the frozen intraday module
  `scripts/probes/_705_intraday_1025/01_intra_frozen_ac598fc58aae.py` (sha256 `ac598fc58aae…`, refused on drift) and the intraday
  registration's `doc_body` (`6c3741e48788…`).
- **Code:** `scripts/probes/_705_rule_mix_1025/01_mix.py` + `test_01_mix.py`. **Imports the FROZEN intraday module read-only** and through it
  the frozen reverse module, the holdings replay, the runner and `cb`. Reused as they are: `load_core`, `intra_sets`, `enter_sets`,
  `windows_of` / `clock_sane` (§2c), `recs_for` / `make_irec` / `IRec` (one calendar per record), `MinuteStore` (guard 12 at read),
  `BarGuard`, `h60_bars` / `bar_sequence` / `ema_series` / `armed_index` / `ema_is_thin` (the 60-minute bars and the 20-EMA with its 65-bar
  floor), `intraday_levels` / `enter_score_trade` / `shifted_control` / `rev.random_levels` (every ENTER crossing, verdict and control draw),
  `stop_levels_intra` / `held_through_intra` (every stop cell's any / certain / unresolved / first_j — the four buckets), `prior_low`,
  `rev.level_at`, `smas_for`, `fnum` (never `float()` of an array), `IdCache` (the only cache; a module-scan test fails on any other `id(`),
  `rng_for` (the key-to-generator function of every new draw), `--reset`'s archive procedure (N2). **The freeze-lock, dry-run, ledger and
  pins helpers default to the INTRADAY read's files** (`DOC`, `P_DRY` = `01_intra_dryrun.txt`, `LEDGER`, `OUT_DIR`) — a bare call would pass
  guard (1) on the intraday dry run (which already ends `DRY RUN COMPLETE`), hash the intraday doc's body and append to the intraday ledger.
  So they are reused ONLY with this read's paths passed explicitly: `doc_body_text(doc)`, `pin_under_marker(name, doc)`,
  `store_freeze_body(doc, out_dir)`, `freeze_body_text(h, doc, out_dir)`, `freeze_state(doc, out_dir)`, `ledger_append(stage, path, ledger)`,
  `ledger_verify(ledger)`, `dry_run_complete(path)` (this doc, `01_mix_dryrun.txt`, `01_mix_ledger.tsv`, `rule_mix/`), and
  `pins(doc, include_outputs=False)` for the CARRIED pins only. `stage_outputs`, `any_stage_output` and `pins`' own output entries hard-code the intraday files and take no path, so
  this module owns `mix_pins`, `mix_stage_outputs` and `mix_any_stage_output` over its own files. **Own code, small and tested:** `LIBRARY` (the three ordered lists
  of §3 with each rule's source string and 2020 number), `first_fire(rec, rule)` → (session as §4a's booking table defines it, minute,
  bucket) per rule — for M-1 / M-2 / M-7
  built on the same primitives `exit_walk_intra` uses, WITHOUT a stop pre-empting (the stop is a library rule on losers here; the frozen
  walk lets the chain's stop pre-empt legs), for M-2s the first prior-low touch from M-1's bar-close minute on, for M-3 / M-4 / M-8 / M-9 /
  M-11 on daily closes and session indices, for M-5 / M-6 on the registered R unit, for M-10 on the exits study's fixed thresholds (2.0 / 1.5
  ADR20); `tag(rec, decision, order)`; `random_windows(rec, range)` (every placement enumerated); `k_price_control`, `shared_shift_control`,
  `random_level_control` (§5); the tables. **Stages:** `--dry-run` (populations asserted against the intraday dry run's claims and §2; the composition line from
  clocks alone; coverage from the fetch logs; the library order printed from the constants with each source; the loss share is NOT computed —
  it is an outcome; pins), `--pins`, **`--tag` (ONCE, after the freeze: gates, then ENTER → STOP → EXIT on every block, the controls, the
  tables, the per-trade files)**, `--reset "<reason>"` (after a STOP only; archives, never deletes; the event pinned under the marker before
  `--tag` may run again).
- **Known-answer gates on REAL data, at the top of `--tag`, each STOPS the run before any new number** (cleared only by a bug fix shown in the
  code, never by changing a registered rule): **(i)** minute-built session bars vs the daily export, two arms (high / low within 0.5% on ≥ 98%;
  open / close within 0.5% on ≥ 90%), and a clock arm on the buy days: a bar at minute 0 (09:30) on ≥ 98% of them (expected about 99%:
  `no_bar_0930` on 3 of the 400 scored windows, `01_intra_enter_fit.txt` l.62, `01_intra_check.txt` l.44, l.56); **(ii)** raw L7 ≤ L1 ≤ L8 ≤ L6 and the 60-minute builder's first bar = L8_raw on every window; **(iii)**
  a daily close below a level beyond the auction band implies the last 60-minute bar closes below it on ≥ 98% of such days; **(vii)** the
  random-price control re-reads 31.7% / 85.9% on the previous 41 undated 2021-22 records, with the draw stream replayed over the exact
  previous draw population (§5). **Every gate (viii) arm runs ONLY on the eids present in the intraday TSV it re-reads**
  (`enter_fit_trades` / `check_enter_trades` / `stop_fit_trades` / `check_stop_trades` / `exit_fit_trades` / `check_exit_trades`) — the
  returning guard-5 trades (§2) are not in them — **and re-runs each row with that row's OWN fill, `fill_minute`, `fill_src`, stop and
  `J_tail` from the TSV** (as the intraday gate (iv) did), because the 2020 fits ran under the fit chain: `fill_level:L8` on 33 stop rows and
  8 exit rows, 22 exit walks bounded (`01_intra_stop_fit.txt` l.18; `01_intra_exit_fit.txt` l.18, l.43). The tag itself runs under the
  registered fill (§4d); the rows whose fill differs (33 / 8) and the 22 bounded rows are printed by eid beside it. **(viii) NEW — row-for-row
  re-reads of the intraday TSVs:** every ENTER record's L1-L9 cross minute, feasible and verdict, and its `control_feasible`, `control_hit`,
  `union_feasible`, `union_shift_feasible`, equal `intraday/enter_fit_trades.tsv` / `check_enter_trades.tsv`; every stop cell's `_any /
  _certain / _unresolved / _first_j` — the S8 and SMA50 control cells included (they certify `smas_for` and the daily close-below path) —
  equal `stop_fit_trades.tsv` / `check_stop_trades.tsv` (the §6a certainty rule through the frozen function); and the ENTER standalone shares
  re-read the printed feasible shares on the TSV eids (2020: L1 36.8 / L2 18.4 / L3 13.8 / L4 1.1 / L5 1.1 / L6 16.1 / L7 16.1 / L8 34.5 /
  L9 34.5 on 87, `01_intra_enter_fit.txt` l.24-32; 2021-22: L7 27.5 / L8 45.0 / L9 45.0 / L1 35.0 on 40) at one decimal, the returning eids
  printed by name. **The EXIT part is in three arms, because the printed hit rates were scored WITH the chain's stop pre-empting the leg
  (`stop_preempt` 67 of 139; 56 of 107): (viii-a)** the frozen `exit_walk_intra`, re-run here WITH each row's own chain stop and fill
  through this module's bars, EMA and calendar, reproduces every trade's `E1_last_j` / `E2_last_j` / `E4_last_j` and the printed hit rates
  (2020: 40.3 / 40.3 / 39.6 / 39.6 on 139; 2021-22: 38.3 / 36.4 / 35.5 / 35.5 on 107) — a known answer for the bars, the average and the
  calendar; **(viii-b)** on every row whose `E1_stop_preempt` (resp. `E4_stop_preempt`, `E2_stop_preempt`) is False, this module's no-stop
  `first_fire` gives M-1 = `E1_last_j`, M-2 = `E4_last_j`, M-7 = `E2_last_j` — BOOKED sessions both sides (§4a's table: a close on the
  day's last 60-minute bar and every daily close below the prior low book on the next session) — the tagger's own primitives against the
  frozen walk where no stop intervened; on the pre-empted rows the no-stop firing is a NEW number and is not gated; **(viii-c)** M-8 and M-9
  standalone (own-session convention) re-read the printed trivial exits on the TSV eids: 31.7 / 20.1 on 139 (`01_intra_exit_fit.txt`
  l.40), 25.2 / 14.0 on 107 (`01_intra_check.txt` l.184), 27.6 / 21.1 on 199 (l.204) — the daily rules' session index. **(ix) NEW — his own
  words as the tagger's known answer, pinned only as far as his words and the printout establish it:** FSLY eid 693 (undated 2020-06-29,
  exit 07-13..07-14): M-1's bucket is NOT EXPLAINS and NOT NEITHER, and its first firing is on or before the 2020-07-10 offset — so
  MISS-EARLY or UNRESOLVED (gate (vi), `01_intra_stop_fit.txt` l.35, counted closes ON 07-10 only — three, the first at 13:59 — so an
  earlier, buy-day firing that reads UNRESOLVED is not excluded); M-2 and M-2s are NOT NEITHER and each fires on or before the 07-13
  offset. M-2s arms at M-1's first firing whatever its bucket, UNRESOLVED included. **The TAG is not pinned** (§7 states the expectation); a
  gate that pinned it would be edited after the data if wrong. **(x) NEW — the identity gate:** the random-window machinery placed at
  s = exit_lo_j reproduces every real bucket for every rule and trade, and the ENTER shared-window and per-level shifted machinery placed
  at the real window reproduce the real feasible flags. Gates (iv), (v), (vi) of the intraday read are not re-run (their objects are re-read
  through viii / ix).
- **Guards (the intraday twelve, kept; stated where this read differs):** (1) the line-anchored freeze lock — `--tag` refuses unless every pin
  incl. `doc_body` (the sha256 of this file's bytes above the one line that is exactly the freeze marker; the literal appears once in this
  file) sits under the marker BY NAME (each pin's own `- name: value` line carries its value; an ABSENT pin its literal `- name: ABSENT`
  line), the module's sha equals its pin, THIS read's dry run (`01_mix_dryrun.txt`, passed by path) opens with this read's dry-run header,
  carries a `RESULT: .. 0 MISMATCH` line and ends `DRY RUN COMPLETE`, and the tag printout does not exist —
  **there is no fit stage and no chosen line: the library order is a constant, printed by the dry run and pinned with the module**; (2) the
  module copied beside the pins before any post-run edit; (3) populations asserted before any bar; (4) G8 before numbers; (5) **no fit stage,
  so no forbidden pairs: the one run reads every block once (`BarGuard(allowed_eids=None)`) — this read has no held-out set, said plainly**;
  (6) a crash writes a STOPPED file; the only way past it is `--reset` (N2); (7) the append-only sha256 ledger; (8) misread clocks EXCLUDE
  (§2c); (9) `replay/` and `his_exits/` never opened (the exits study's numbers enter as printed constants for the ORDER, never as files);
  (10) one calendar per record; (11) IdCache only; (12) the 2025-26 seal — every date read asserted ≤ 2024-12-31.
- **Tests (synthetic, before any real run):** the four buckets per rule on a hand-built trade (an early firing then an inside firing → MISS-EARLY;
  a buy-day firing between flat and first → UNRESOLVED; a firing on exit_lo → EXPLAINS; after exit_hi → NEITHER); the greedy tag against a
  hand order; the earliest-firing order; the random window's placement bounds for (a) and (b) incl. `no_room` and a cut path; the width on the
  own calendar; M-5 vs M-9 on a stalled and a non-stalled session-3 exit; M-6 on the registered R unit; M-10's thresholds; M-2s against M-2 on
  a world with an early touch, a 60-minute close, then a second touch (M-2 MISS-EARLY, M-2s EXPLAINS) and on one whose first touch follows the
  close (M-2 takes the tag); the (viii-a) re-run of the frozen walk with a stop on a world where the stop pre-empts (last_j = the stop's
  session) and (viii-b) on one where it does not; the FSLY 693 buckets on synthetic bars shaped like it; the library constants' sources parse; the freeze lock against this exact text; the module scan;
  **one end-to-end synthetic world** (`--dry-run` → `--tag`) with era-A and era-B trades, an early-close day, a missing minute day, a
  still-held trade, a 1-session hold (control (a) `no_room`), a loser and a winner on one name, objects freed and ids reused between stages;
  and the gate (viii) re-read on a planted TSV row that must FAIL when one `first_j` is shifted by a session — and one planted failure per
  known-answer gate ((i) incl. its clock arm, (ii), (iii), (vii), (viii), (viii-a), (viii-b), (x)) and a dry-run mismatch, each of which must STOP. **The synthetic world also
  holds the real shapes that drive the gates:** an undated trade with no in-session buy-day frame (every buy-day firing UNRESOLVED — the
  common case on the 304 + 226); a TSV row with `fill_src = level:L8`; a guard-5 trade that returns; a firing on the session's last 60-minute
  bar (booked on the next session); a `no_bar` day before an in-window firing (must read UNRESOLVED); an exit_lo firing before the last
  in-session frame (EXPLAINS, and counted in the "contradicted" line); an era-B record whose own calendar offsets differ (shaped like the 7
  era-B 2022-04 rows, `01_intra_check.txt` l.175-181); a window over 20 sessions (out of the denominator); a flicker; a buy-day sell
  (control (a) `no_room`, out of the same-trades comparison). **Module scans:** no bare `float(` in the new module (`fnum` only); no call of
  a freeze, dry-run, ledger or pins helper without its path argument; a test that guard (1) refuses when only the intraday dry run exists.
- **Outputs:** `01_mix_dryrun.txt`, `01_mix_tag.txt`, `01_mix_pins.txt`, `01_mix_ledger.tsv` in the module's folder; per-trade TSVs under
  `apollo_data/cb702/qm_streams/holdings_1024/rule_mix/` (`tags_enter.tsv`, `tags_stop.tsv`, `tags_exit.tsv`: eid, block, per rule its
  bucket / first_j / first_minute, the tag, the earliest-order tag; `control_windows.tsv.gz`: per draw the range, start, and per-rule bucket).

**The expected output table, per decision and block (the template the run fills; one table per decision, blocks as column groups):**

```
decision ENTER — block 2020 (n scorable .. — about 88 with the returning guard-5 trade; composition: in-session 87 | pre-market-flat 97 (beside) | no flat frame .. | pre-market sighting .. | no_minutes ..)
rule  | source       | greedy share (95%) | standalone | chance: random-price | chance: shifted (greedy) | precision (floor) | label
L1    | his words    |  ..%  [..,..]      |  ..% (36.8% re-read on 87) |  ..%  |  ..%                     |  ..%              | carries / weak / chance / below chance
L8    | his words    |  ..%               |  ..% (34.5% re-read on 87) |       |  ..%                     |  ..%              |
..
discretion            |  ..%
UNION                 |  ..%  vs chance union: k-price ..% | shared-window ..% | per-level shifted ..%  → mix / no mix (needs both 2020 and 2021-22)
earliest-firing order: L1 ..% L8 ..% L7 ..% .. (union unchanged by construction)
```
The STOP and EXIT tables carry `chance (a) inside the hold`, `chance: random level` and `chance (b) hold + tail` in the chance columns, the
losers' share of exits and the `no_room` trades' n in the header, the "EXPLAINS on exit_lo contradicted by a frame" count per rule, and the
EXIT table once on all exits and once per sign beside.

## 10. What this does not answer

- **Which rule he actually used on a trade where two explain it** — the greedy order is a convention; the standalone shares and the
  earliest-firing order bound the ambiguity, they do not resolve it.
- **His partials** — a rule he acted on with half the position reads as a miss (FSLY); precision is a floor, and the union may under-read him.
- **Whether a share is stable** — 2020 and 2021-22 are both read; neither is unseen; the forward shadow is the only out-of-sample read left.
- **The side of a position, trades between two streams, his fund and ETF trades, his fills and sizes** — as before.
- **Rules not in the library** — a limit inside the range, anticipation (his l.2093-2094), a mental stop wider than one ADR20, a time stop
  longer than five sessions, a sale into a specific news event: the discretion remainder holds them undifferentiated.
- **Anything about 2024 beyond the fetched tails, or 2025-26 beyond the one sealed strategy test.**

## 11. Design questions — DECIDED (main loop, 2026-10-25; no money, not THE LINE)

Every one of the 13 was decided as the doc recommended; items 2, 5, 7, 8 and 13 carry the wording fixes of the review. Items 14-21 record
the choices the review's fixes required.

1. **EXIT population: all exits primary, or a losers / non-losers partition?** DECIDED: all exits primary, split beside (§3c) — the panel is
   sign-blind and the 60-minute close fires on losers too; the partition hides that; the losers' "explained by neither library" line is the
   honest remainder.
2. **The random-window placement range?** DECIDED: both; (a) inside the hold is the comparison line, (b) hold + tail beside (constraint f).
   Amended: real and chance are compared on the SAME trades — those with at least 2 placements in (a); the buy-day-window trades (`no_room`
   in (a)) are printed beside with their real buckets and n (§4b, §5).
3. **Order within a tier?** DECIDED: the 2020 printout number for the tag (fixed, cited, nothing re-measured), the earliest-firing order
   beside (§4b).
4. **Partial sales?** DECIDED: precision is a floor (§4b); FSLY 693 is the known answer (gate ix); named in §10.
5. **"Losing" defined at the close of exit_hi under the registered fill, exit_lo beside, `sign_ambiguous` counted?** DECIDED: yes — one
   booking point, the one the reverse registration's 'his' account uses (its §8c, l.405-406: the panel exit at the close of `exit_hi`).
6. **S4 (one ADR20 below the fill) as a stop level?** DECIDED: yes, tier 2, last (§3b); its S4-H variant is a new read, disclosed.
7. **The stall cut (M-5) AND the plain session-3 close (M-9)?** DECIDED: both. Amended by the restated order rule (§3): M-9 and M-11 are
   his words ("after 3-5 days", l.1946; "the day thing", l.2060) with an all-out that is ours, so both move to tier 1; M-5, a strict subset
   of M-9, sits directly before it. M-9's greedy share still reads "session-3 sells after +1R".
8. **One run over every block (no fit, no held-out set)?** DECIDED: yes — nothing is left to protect; gates (viii)-(x) certify the run; the
   read is descriptive. Amended: the guard-5 trades the fits excluded RETURN (ENTER +1, STOP +16, EXIT +10), so this run's n is not the
   printouts' n; the gates re-read only the TSV eids (§2, §9).
9. **M-10's thresholds?** DECIDED: keep the exits study's fixed markers (2.0 ADR20 over the 10-day; 1.5 ADR20 over the prior close), last
   in tier 2.
10. **The 20-bar plain average as a separate M rule?** DECIDED: beside only (§3c) — a second 60-minute rule would double-count M-1.
11. **Minimum n for a printed share?** DECIDED: none; every share printed with its interval and n.
12. **The dated rows' max(level, pivot) convention?** DECIDED: keep (gate viii re-reads row for row); the raw level beside.
13. **Where M-2s sits?** DECIDED: after the numbered tier-1 rules, before M-11 (§3c). It takes a tag only in the FSLY shape wherever it
    sits, since M-1 and M-2 precede it either way; the placement moves at most its split with M-3, M-4, M-5, M-9 and M-6.
14. **Which session a firing is compared with the window?** DECIDED: the booked session, per rule (§4a's table) — M-1 and the H cells
    book a last-bar close on the next session, M-7 on the next session, touches and the other daily rules on their own session — so
    gates (viii-b) and (viii-c) compare like with like.
15. **The ENTER union's chance line?** DECIDED: the k-price control (7 independent random prices, §5), with the shared-window and per-level
    shifted unions beside; `mix` must beat the largest.
16. **STOP / EXIT level control?** DECIDED: add the random-level control (§5); `carries` is held against the larger of control (a) and it.
17. **The STOP / EXIT random windows?** DECIDED: every placement enumerated with equal weight (no draws).
18. **Missing data before a firing?** DECIDED: the firing reads UNRESOLVED (§4a), in the real tag and the controls.
19. **The denominator?** DECIDED: one scorable set per decision for every rule and control (§4b); windows > 20 sessions are out of it, not
    NEITHER.
20. **Labels?** DECIDED: `carries` needs both 2020 and 2021-22, each against its own chance line; a fourth label `below chance` (§6).
21. **The exit_lo frame conflict?** DECIDED: EXPLAINS on exit_lo whatever the minute (the window unit, as the controls); the contradicted
    count printed beside (§4a).

## 12. Revisions before the freeze (2026-10-25)

The review (25 findings) and the recount (4 mismatches, 14 notes) were applied before any freeze; nothing was run and no bar opened. The
second check of the module (12 findings, 2026-10-26) was applied likewise: only the dry run and the TSVs' offset columns (`cut_why`,
`J_tail`, `exit_hi_j`) were read; no outcome was computed. Each row is one change.

| source | finding | change |
|---|---|---|
| review | F1 | §2 and §9: the guard-5 trades return; gates re-read only TSV eids, returning eids printed |
| review | F2 | §9: gates re-run each row with its own fill, fill minute, stop and J_tail; the 33 / 8 differing and 22 bounded rows printed |
| review | F3 | §4a: booked-session table per rule; gate (viii-b) compares booked sessions |
| review | F4 | §9: reused freeze / ledger / dry-run / pins helpers take explicit paths; own `mix_*` output helpers; scan test |
| review | F5 | §5: k-price random control for the ENTER union and greedy chance shares |
| review | F6 | §4b, §5, §11 Q2: comparison on trades with room in (a); `no_room` trades beside |
| review | F7 | §4a: frozen-output-to-bucket mapping table; the exit_lo contradiction count |
| review | F8 | §7, §9 gate (ix): FSLY pins only "MISS-EARLY or UNRESOLVED" and "fires by 07-13" |
| review | F9 | §9: gate (viii-c), S8 / SMA50 cells in (viii), identity gate (x); gate (i)'s blind spot stated |
| review | F10 | §6: WOULD-FAIL-IF for a scan-origin bug; gate per failure |
| review | F11 | §5, §6, §11 Q16: random-level control for STOP / EXIT |
| review | F12 | §5: per-level shifted control described honestly; shared-window control added |
| review | F13 | §4a, §8: a firing after a missing session reads UNRESOLVED |
| review | F14 | §3, §3c, §11 Q7: order rule restated; M-9 and M-11 to tier 1; subset rule |
| review | F15 | §5, §9: draw stream replayed over the previous population; per-row control columns re-read |
| review | F16 | §4a, §4b: one denominator; > 20 sessions out of NEITHER |
| review | F17 | §2 table header reads "n = records / scorable" (the doc checker passes) |
| advisor | final pass | §4b: the room test applies to the tag and controls only, gates keep the TSV base; §4a last-bar consequence; §3b S3-T reason |
| review | F18 | §0, §11: decisions recorded as DECIDED |
| review | F19 | §6: `carries` on both blocks; `below chance` label |
| review | F20 | §3a column relabelled, re-read numbers added; gate (viii) lists 2020 L1-L6; template |
| review | F21 | §3a, §7: L4 "almost never" (1 of 87; 1 of 19 flickers) |
| review | F22 | §0 20-33%; dry-run printout cited and listed; l.2090-2092 and l.2095-2096 |
| review | F23 | §1.1 reworded: changes no branch of the sealed test |
| review | F24 | §9 tests: the real shapes and the module scans |
| review | F25 | §5: placements enumerated, no draws |
| recount | F1-F4 | L4 wording; L8 example against the check's own 30.0%; 20-33%; l.2090-2092 |
| recount | notes | pre-market scored vs population counts; untouched-dated bases; S-8 cite l.42; l.1942 paraphrase unquoted; §11 Q5 cite |
| check 2 | F1 | module: a guard-bounded EXIT row is re-walked under its own cut reason (`cut_at_guard`); latent here — all 22 such rows have J_tail = exit_hi + 20 |
| check 2 | F2 | §9 guard (1): pins checked by name (ABSENT on its own line); the dry run by its header and its 0-MISMATCH RESULT line |
| check 2 | F3 | §4a: R16 — a C cell's buy-day close takes the buy-day clock test, as the exit daily rules do; the moved pairs counted beside STOP |
| check 2 | F4-F7, F9 | tests only: registered semantics, every gate's failing branch, gate (vii) and G8 run end to end, an era-B own-calendar offset |
| check 2 | F8 | §6, §9 gate (i): a clock arm (a bar at minute 0 on ≥ 98% of buy days); the clock shift named in the gate-per-failure sentence |
| check 2 | F9 | §6: labels compared on the printed one-decimal percentages |
| check 2 | F10 | module: gate (x) re-reads the frozen per-level shifted placements through this read's window predicate |
| check 2 | F11, F12 | module: the dry run prints no self-hash; every §2b NEW cell flagged in its table; the pre-empted rows' no-stop firings counted |

<!-- FREEZE -->
## Freeze record

Empty until the freeze. The main loop freezes this doc and the module (`doc_body` pinned), runs `--dry-run` (the library order and its
sources printed; no outcome), runs `--pins`, pastes every pin below (the intraday pins carried, plus the intraday fit / check printouts and
per-trade TSVs this read re-reads, the frozen intraday module, this module and its tests, the dry run, the ledger, `doc_body`), copies the
module beside the pins, and runs `--tag` once. There is no chosen line: nothing is written above the marker after the freeze. Any edit above
the marker after that changes `doc_body`, and `--tag` refuses.

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
- runner: a4f016720f8226933367ae3d776a7067d9d94dea634b28e5e5685e186bc3ad69
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
- rev_dryrun_printout: 935ce2981efec7b314f6f9ffa9746f6602982ccc195a2456d0b161d79e7e2e4a
- rev_select_fit_printout: 0893e38a7d2afbf9abfc0c350db2d43f4cf461b0a26f86ce4b46b9b96297208e
- rev_enter_fit_printout: 743e0c124bc5992b3d7adc1ff55545540f267f4def4f5788f9aae5f93d326724
- rev_stop_fit_printout: 95b97b95b44099b41c52acbff0623ff48c8b6c918286a6d162e4011c8abe80f0
- rev_exit_fit_printout: eac07e9a42fce45397b6951e14594fe0bddca59b8dcabedc7635812fbaf29305
- rev_ledger: 45dc2c7cd2870e017cf0906dadaed53b425521e1452e2b0828f076319976045f
- rev_doc_body: 16a3057d99b55f4588ffa3cf3fea34da97d5d1e7dee7c0da76d8bfaffe7fe287
- fetch_list_intra: e66f33d690f7d0d2ac9c797bedc16ff5bc79b9fffda268859016ed0d1d3f6254
- pop_fetch_script: b7b75d56adb80aeb0a6833a3cf4b9f274e7038e7f4e85de6f96db89a6db4cd67
- pop_fetch_printout: d6bd0f6743773f562ce92f28fcfc6cb9fc872227dfe5bf8fe04afd954245c7d5
- rev_frozen_module: e908253f7405f814351ced03bd61a80b7886268bcee366f70f66c4a5f74aaeff
- rev_enter_fit_trades: ae8efb34baa439295f911b1e4495c601568f4187f5f61a61ec5c722804a318d8
- rev_stop_fit_trades: 78f890fcc5011a90c82d2ee429b24b1f92c445eac095e6d0d00b2e7fa384464c
- rev_exit_fit_chosen: d62e7410ae7c7d0cba825f3763d68a65e860c3244470d6f043a2714085f2074f
- rev_check_printout: 43e3de92c29f6e955e48176b134ae1f5aca7b8aea0d39c8a2ee8da8b6b56a43a
- done_INTRA: a9dc793c33af220a2c030ae3d36f83af5d80ab91890b0e80c0deea3868d3f243
- intra_module: ac598fc58aae62dc03c93f5d274aa26af37594821f98d1e1c162c2bb8d20f7ee
- intra_tests: b9669a31d32c36cd5771b69ec8173013e8a774e319d3ca62fafe4664e7725d15
- intra_doc: f816434f3f666de220d74b8961acfff83680f58c5c9419fc822b327734eff918
- intra_frozen_module: ac598fc58aae62dc03c93f5d274aa26af37594821f98d1e1c162c2bb8d20f7ee
- intra_dryrun_printout: 62eae23a68e2405a5920f9b8df6aad778462495a890b8941fd38ebb7ee0c21f6
- intra_enter_fit_printout: c34caf77d12e09aabb95afd33278bd0b0f6111ccd89204eb91a64f93ab9281b6
- intra_stop_fit_printout: 4b6af1c4b039c477358f793067b72daae40af43e5cd05ba6fec0024b86e9433b
- intra_exit_fit_printout: 64d9089a1fd95f7e428f8d97ef57bf0d42a1cca358286dfe9753005b69cca9cd
- intra_check_printout: a6db5a635fafbe02f78140cf41dcac4ff7f2d2ad32fdb0c54181e314b93b034f
- intra_ledger: 542d7ab449f25342bfb37e02eb02bc0e20caec4b32bfacbd1cad7f05bf9360cc
- intra_enter_fit_trades: 85c04f260b20321450694bccd36dd5052b9dc0e1c6322e76cb148eef14986d59
- intra_check_enter_trades: 36e0f05ce74cf1e3cbcbe04022d1b3d276b43c7656d7347427fa359f5d032865
- intra_stop_fit_trades: f3a282aa864c36f0a7c383529aca0499c4615aa7d43645a89b726383daffcb55
- intra_check_stop_trades: 3ce21d8fd072e2d010f09fe8da31bee1552a1b5addbd66ff7d30c98ae57e0211
- intra_exit_fit_trades: 238cfdbdcdba7d4df5eb9cf406a9d9c8a7ad2c57b1ee5d82cd66e3c82bc95a2b
- intra_check_exit_trades: ed1e617b1046e46cd75776c1b505a1946342f1e73a07f6f2d71bb55f8286e200
- exits_study: a95d323b106e81cfd6c7ddd5dc112773951fa119754dbc62ece88bb1852eb783
- intra_doc_body: 6c3741e48788c1fab6664a366e86980c9e10b74a07aa63c6190577b773668bc3
- mix_module: 75c832541cef5e0abf2476a6484f37b857ab191284672914666996669d7bf300
- mix_tests: 1af37fcb01c7b6003f94da39f1214e1fed17accdf2b1106f71339b12008a7a8f
- mix_dryrun_printout: 3e3d27736dd788c1df75684ea45089564e19b3b13d353fecc3df57e0661bd2e0
- mix_ledger: ABSENT
- doc_body_freeze: 6a2512024c5f2ed562469919d5e733dd48ba36a4d6bde0045f2d9e7f071985fd
- doc_body: 6a2512024c5f2ed562469919d5e733dd48ba36a4d6bde0045f2d9e7f071985fd

## RESULT — the one tag run, 2026-10-26 (freeze `7dfa483e`; printout `scripts/probes/_705_rule_mix_1025/01_mix_tag.txt`; written BELOW the marker)

**No decision shows a rule mix by the registered bar (the union must beat the same union by chance by ≥ 15 points on BOTH 2020 and
2021-22).** Independent recount (Sonnet, own stdlib script, `verify/recount_tag.py` + `.txt`): all nine union / chance / verdict cells and all
102 deciding labels (0 of 413 printed labels differ) reproduce from the per-trade files; caveats in the recount (the STOP / EXIT random-level
union taken as printed — a 1−(1−p)^k check lands within 0.2 point; 42 secondary ENTER cells checked by bound only).

| Decision | 2020: union vs chance (n) | 2021-22: union vs chance (n) | untouched (sign check) | Verdict |
|---|---|---|---|---|
| ENTER (his in-session buy windows; 7 levels) | 56.8% vs 49.9% (88) | 66.7% vs 52.0% (60) | 44.4% vs 20.7% (9) | no mix: +6.9 / +14.7 points (the bar is +15 on both) |
| STOP (his losing exits) | 54.0% vs 61.9% (139) | 57.8% vs 64.7% (116) | 75.0% vs 74.6% (12) | no mix: below chance |
| EXIT (all exits; 12 rules) | 71.5% vs 69.8% (333) | 72.9% vs 70.9% (229) | 61.4% vs 67.7% (44) | no mix: at chance |

- **Reading (no money, no rule changed):** his buys lean on his own opening-range highs (the union beats random prices by 7-15 points, and the
  1-, 5- and 30-minute highs carry most of it); as ONE rule set for all trades, no stop level and no exit rule in the library explains his
  trades better than the same rules fired at random. Fragile: ENTER 2021-22 sits 0.3 point under the bar.
- **His reading, 2026-10-26 (verbatim):** *"we're not looking for 100% coverage, trading is an art, so some variations that are close to a set
  of rules applied based on context is what I hope we get out of it, then the challenge is to recreate those rules for apollo"* → the next read
  asks which CONTEXT picks which rule (`docs/analysis/cb_context_rules_prereg_2026-10-26.md`, registered separately).
