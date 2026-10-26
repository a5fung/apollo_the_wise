# #705 — Context rules: which of his rules he applies in which context, matched closely — pre-registration (2026-10-26)

**Status: REGISTERED, NOT FROZEN, NOT RUN.** His words (2026-10-26, verbatim, `docs/methodology/operator_shared_notes.md` l.2604, after
the rule-mix inventory): *"we're not looking for 100% coverage, trading is an art, so some variations that are close to a set of rules
applied based on context is what I hope we get out of it, then the challenge is to recreate those rules for apollo"*. The method line
recorded with it (l.2606): a small set of rules, each applied in a CONTEXT, matched closely rather than exactly; the next read asks which
context picks which rule and how much closer to his trades that gets than one rule for all; then those context rules are rebuilt for Apollo.
**Outcome-free:** this registration read the rule-mix registration (`cb_rule_mix_prereg_2026-10-25.md`), its tag printout
(`scripts/probes/_705_rule_mix_1025/01_mix_tag.txt`) and recount (`verify/recount_tag.txt`), the RESULTs of the two registrations before it
(`cb_reverse_engineer_his_rules_prereg_2026-10-24.md`, `cb_intraday_layer_prereg_2026-10-25.md`), the frozen rule-mix module's code as text
(nothing run), the per-trade tag files' HEADER LINES and their label and offset columns only (`block`, `dated`, `flicker`, `tagged`, `status`,
`room`, `loser`, `exit_lo_j`, `exit_hi_j`, the buy-day clocks; the fix stage added `fill_src` and `fill_minute`, population columns), the
timeline's `setup` label, and his words. **No price bar — daily or minute — was opened; no context value was computed; THIS read crossed no
bucket column with any context or label; nothing of 2025-26 was opened (sealed).** **Two crosses already EXIST before this read and are
disclosed (§1 4e):** the rule-mix printout gives every rule's ±0 share on dated vs undated trades on both blocks (`01_mix_tag.txt`
sub-block headers l.63 / l.79, l.159 / l.175, l.312 / l.337, l.389 / l.414, l.563 / l.584, l.673 / l.694; untouched l.466 / l.491, l.783 /
l.804) — so the setup context is known at ±0 and is taken OUT of the map search (§3, §13 Q5); and the exits study crossed fast vs slow (ADR20 above 4.79%) with his 2020 exit timing (`cb_his_exits_study_2026-10-24.md` l.71-72).
Every number below is copied from those printouts (each cited) or counted from dates, clocks and labels. **One disclosure:** §2's
setup split of the STOP losers reads the rule-mix's `loser` column (an outcome) against the setup label — the losers' composition by setup;
its dated / undated half is already printed (`01_mix_tag.txt` l.312, l.337, l.389, l.414), the breakout / EP / both split within dated
(2020: 39 / 6 / 3) is new and is a population count, not a share of anything this read measures. Measurement and registration only —
nothing here changes or proposes to change a strategy, entry, stop, exit, size, safeguard or live trade state (THE LINE). **The read is
DESCRIPTIVE: it decides nothing** (§7).

**His words this tests, by context (line cites into `operator_shared_notes.md`):**
- **Speed and the trail** l.2046-2047: *"trail rest at break of 10 or 20d, I recall he mentioned 10d for faster stocks and 20d for slower
  stocks, also depend how far the are from 10/20"*; l.2095-2096: *"trailed with the 10- or the 20-day moving average. Depends on how fast the
  stock is"*; the notes' own open item l.2054-2055: *"what makes a stock 'faster' (e.g. its ADR), and how 'how far they are from the 10/20'
  picks the average"*.
- **Volume confirmation and the entry candle** — his interview as the notes paraphrase it (l.1699-1700, "paraphrased with short quotes"),
  l.1712-1713: *"if opening volume is large enough, buy a move above the high of the FIRST 5-MINUTE bar; otherwise wait and buy above the
  first 1-HOUR bar"* — his EP entry words, which this read TRANSFERS to all trades (our reading); l.1735-1736 (*"the first 1-hour bar when
  volume needs confirming"* — the notes' own summary, not his words); his article l.1941-1942: *"The opening range
  highs can be the highs of the first 1-minute candle, the 5-minute candle or the 60-minute candle."* Or buy as the daily chart starts to
  break out (l.2091-2092: *"just look at the daily chart and enter when the stock is starting to break out"*).
- **The stop's cap** l.1943: *"Stop is always lows of the day and stop should not be wider than the ATR or ADR of the stock."*
- **The market's trend — OUR READING as a context for any decision.** His 10-22 ruling l.2481 is a PHRASING ruling: *"Better phrasing should
  be uptrend vs downtrend instead of bull/bear, under 200d but trending up can still be uptrend"*; l.1948 is about move size: *"In a bullish
  market it is very common to get moves that are 10-20x+ your initial risk"*. Neither ties the market to an entry, a stop or an exit; the
  method line recorded with his ask (l.2606, the notes' paraphrase) names "the market's trend" as an example context.
- **The setup** — the EP entry and hold (l.1712-1714: the 5-minute / 1-hour bar; *"Hold for weeks or months"*) against the breakout entry
  (l.1941-1942) and exit (l.1946-1947), and the momentum burst's *"hold three to five days"* (l.1732). Our binary (our event fired vs none)
  is OUR reading, not his EP / momentum-burst / breakout distinction; it is known at ±0 and prints BESIDE, out of the search (§13 Q5).
- **His rule for a miss (2026-10-23):** a backtest that does not reproduce his profit is a defect in OUR implementation or interpretation.

## 0. In plain words

- **What the rule-mix left.** Measured as ONE rule set for ALL trades, no set beat chance by its bar: ENTER's union 56.8% / 66.7% of his
  in-session buys against 49.9% / 52.0% for random prices (`01_mix_tag.txt` l.281); STOP's union 54.0% / 57.8% UNDER its random-level line
  61.9% / 64.7% (l.534); EXIT's 71.5% / 72.9% against 69.8% / 70.9% for random sell windows (l.885). One rule for every trade never carried.
- **What this read asks.** Whether his rules are applied BY CONTEXT: for each decision a short list of contexts his words name or we read
  from them (fast vs slow, how far from the 10/20-day, opening volume, the daily breakout still ahead, the market's trend), a small map
  context → rule (at most four groups, each group one rule from the rule-mix library), chosen on 2020 and scored on 2021-22 as the share of
  his trades it matches closely. The setup (our event vs none) is already known per rule and prints beside every group, out of the search.
- **What "close" means.** EXIT and STOP: the rule's sale lands within his sell window or ONE session on the side its booking convention can
  move it (§4a). ENTER: the level is first crossed inside his buy bracket — the panel's own 27-46 minute tolerance (§4b).
- **Against what.** The best single rule for all trades; the same map search on shuffled contexts (the chance of a context map); and the
  map scored on random buyers and sellers (random prices, random sell windows, random levels) — the map's GAIN over the best rule must
  beat the same gain on random buyers and sellers, arm by arm (§7a).
- **What it cannot do.** It cannot test anything on unseen trades: every library rule was already scored on 2021-22 (the rule-mix tag), so a
  map is a description; the untouched years are a sign check; the confirmatory tests are the forward shadow and the one sealed 2025-26 run.
- **What it costs.** Nothing new to fetch (§10); one run after the freeze.
- **Action from him:** none. The four design questions are DECIDED (main loop, 2026-10-26, as recommended); three review forks are applied
  as recommended and await the main loop's confirmation before the freeze (§13 Q5-Q7; none is THE LINE).

## 1. The four questions of the standard

1. **Decision served:** which of his rules Apollo should rebuild IN WHICH CONTEXT — so a context map, if one holds, becomes a recorded arm in
   the forward shadow or the #482 bracket lab (§8). It changes no branch of #710's sealed 2025-26 test (that registration may adopt a map
   or not).
2. **What would change it:** the labels of §7 — `context map` makes a map a candidate arm (adding it is his sign-off); `context helps, chance
   too` and `no context gain` leave the single-rule arms as they are. No label moves a rule, threshold, size or safeguard.
3. **Population:** §2 — the rule-mix's scorable sets as they stand: ENTER in-session buy brackets, STOP losing exits, EXIT all exits; blocks
   2020 (the map is chosen), 2021-22 (scored as chosen), untouched (sign only).
4. **What would make this wrong:**
   - (a) **Inherited, unchanged:** survivorship, the panel's OCR, a position's missing side, a window that is not a day, a clock that bounds a
     minute and not a price, partials invisible (FSLY 693: half on the 60-minute close 07-10, the last share 07-13 / 07-14 — every share is
     a floor).
   - (b) **The search overfits 2020.** Up to 449 candidate maps on EXIT (§5c) beat the best single rule in-sample by construction. Guarded by
     the shuffled-context control (§6b: the same search on contexts that carry no information) and by scoring on 2021-22 as chosen.
   - (c) **A context can be MECHANICAL.** A context that sorts trades into easy and hard groups lifts a map without saying anything about
     him: on 2020 the random-price chance of the ENTER union is 59.9% on dated windows vs 44.5% undated (`01_mix_tag.txt` l.74, l.90), the
     STOP random-level chance 75.1% vs 55.0% (l.332, l.357); dated and undated trades carry different fills (ORH5 vs the open), the
     max(level, pivot) chain and different certainty regimes. Guarded by the per-leaf chance (§6c-1): the chosen map applied to random
     buyers and sellers, each trade scored with ITS OWN leaf's rule — and the label compares GAINS, arm by arm (§7a): the map's gain over
     BEST must beat the same map's gain over BEST on every random arm, so a gain the timing arms also show is not credited to him. Known
     couplings, flagged: C-S1 is S1-T's own distance (the stop's width to the low of the day); C-E2 decides whether a level above the prior
     high can be first crossed in session.
   - (d) **Look-ahead.** A context read after the decision correlates with the outcome. Every context is computed from a view truncated at
     its decision time (§3, guard D1) and a planted future bar must change nothing (test).
   - (e) **2021-22 is not unseen, and two contexts have a prior read.** Every rule's ±0 bucket there is printed (the rule-mix tag). **The
     setup context has ALREADY been crossed with every rule's ±0 column on BOTH blocks** — the tag printout's dated and undated sub-blocks
     per rule per block (`01_mix_tag.txt` sub-block headers l.63 / l.79, l.159 / l.175, l.312 / l.337, l.389 / l.414, l.563 / l.584,
     l.673 / l.694; the untouched block's too, l.466 / l.491, l.783 / l.804) — so any tree rooted on it is
     knowable at ±0 before the freeze and its 2021-22 "transfer" carries no information; it is therefore OUT of the search and prints as the
     per-group stratification (dated / EP counts) only (§13 Q5). **Speed has a prior read:** the exits study crossed fast vs slow (ADR20
     above 4.79%, 97 / 20 of the study's 117 2020 trades) with his 2020 exit timing and scored the speed trail (the 10-day if fast, else the
     20-day) against his windows on 2020 and its check (`cb_his_exits_study_2026-10-24.md` l.71-72, l.232); Apollo runs that cut
     (`TRAIL_SPEED_ADR_CUT = 0.0479`, `consolidation_breakout.py` l.186), so HW-X' at 4.79% prints beside (§5e). New here: the other
     contexts, their joint with the buckets, the widened buckets and the maps. So the 2021-22 score measures a map's TRANSFER, not a rule's
     (§7c).
   - (f) **Widening the window raises chance with the real line.** One session on a hold whose window starts at session 4 (exit_lo_j median
     3, quartiles 1-9, from the offsets) admits more first firings for every rule and every control alike; every comparison is at the SAME
     tolerance; ±0, the symmetric ±1 and ±2 print beside (§4).
   - (g) **Small n.** ENTER scores 60 trades on 2021-22: a 10-point margin is 6 trades, about one and a half standard errors of ONE share
     (L1's interval there, [30.8%, 55.9%], gives 6.4 points); the label is a PAIRED difference, whose interval prints beside (§5d). Intervals
     printed; the labels describe, they do not test.
   - (h) **The bracket's width is a hidden context.** A wide bracket makes every level likelier to be first crossed inside it (median 27
     minutes on 2020, 46 on 2021-22, non-flicker windows, from the clocks). It is the panel's resolution, not a market context Apollo can read, so it is not on
     the list; its median per leaf prints beside, and a leaf that differs mainly by bracket width is flagged a panel artefact.

## 2. POPULATION — the rule-mix's scorable sets, as they stand

Every set is the rule-mix tag's scorable set, re-built through the frozen rule-mix module and asserted equal to its tag files by eid (§11
gate G1). No trade is added or dropped. Counts are trades; dated = our tl breakout or EP gap day fired on the buy day (the timeline's
`setup` ∈ {breakout, EP, both}); undated = no event.

| decision | block | n | setup within dated (breakout / EP / both) | source (`01_mix_tag.txt`) | role |
|---|---|---|---|---|---|
| **ENTER** (in-session buy brackets after §2c; dated flickers in, undated flickers beside) | 2020 | **88** (31 + 57) | 26 / 3 / 2 | l.47 | the map is chosen |
| ENTER | 2021-22 | **60** (20 + 40) | 15 / 4 / 1 | l.143 | scored as chosen |
| ENTER | untouched | **9** (0 + 9) | — | l.239 | sign only |
| ENTER beside | all | undated flickers 30 / 19 / 7 | — | l.95, l.191, l.255 | printed, never summed; the pre-market-flat windows are not used (the open first by construction, union 100%, l.122, l.138) |
| **STOP** (his LOSING exits — the rule-mix's `loser` column, at the close of exit_hi under the registered fill — with room in control (a)) | 2020 | **139** (48 + 91) | 39 / 6 / 3 | l.285 | chosen |
| STOP | 2021-22 | **116** (40 + 76) | 32 / 8 / 0 | l.362 | scored |
| STOP | untouched | **12** (4 + 8) | 3 / 1 / 0 | l.439 | sign only |
| **EXIT** (all exits with room in control (a); the losers / non-losers split beside) | 2020 | **333** (122 + 211) | 103 / 13 / 6 | l.540 | chosen |
| EXIT | 2021-22 | **229** (79 + 150) | 62 / 16 / 1 | l.650 | scored |
| EXIT | untouched | **44** (16 + 28) | 9 / 7 / 0 | l.760 | sign only |

- **n = the scorable trades, written (dated + undated).**
- **"Losing" is the rule-mix's outcome column, reused as it stands** (its §4d / §11 Q5); it is a population filter for STOP and a split
  for EXIT, **never a context** (it is an outcome).
- **The trades out of the rule-mix's comparison stay out here** (buy-day sells and every other `no_room` trade in control (a): 97 / 92 / 28
  EXIT, 56 / 57 / 14 STOP losers; windows over 20 sessions; still-held trades) — counted in the composition line, never in a share.
- **EP is too small for its own group** (2020: 5 of 31 dated ENTER windows, 19 of 122 dated exits, both under the leaf floor of §5b), and
  the setup (dated vs undated) is already known at ±0 per rule (§1 4e), so the setup is NOT a context of the search (§13 Q5): the dated and
  EP counts print beside every group as its stratification.

## 3. THE CONTEXTS — a fixed, short list per decision, each from his words or flagged our reading, each read at its decision time

**Decision time, per decision.** ENTER: the buy day's open and prior bars, plus the buy day's opening minutes for C-E1 — the minutes
strictly before min(09:35, flat_clock): 09:35 is the moment the 5-minute high exists (the branch point his words name), and flat_clock bounds
the decision on a bracket that opens earlier (17 of 88 scorable 2020 brackets and 20 of 60 on 2021-22 have flat_clock before 09:35, 1 of 9
untouched — from the clocks; §13 Q6). STOP: the fill (the registered fill: ORH5 or the close-fill proxy on dated rows, the buy day's open on
undated rows) and the minutes strictly before it, plus prior bars. **EXIT: the close of D, the session before the buy day** — the last close
before any library rule can fire (the 60-minute and touch rules arm from the fill, on the buy day). A static context per trade is the only
reading under which each group's rule is ONE library rule (§5a); the per-session reading his "how far they are from 10/20" invites enters as
the 10/20 switch (§5e), a composite rule beside the map (§13 Q2, DECIDED). **D is the record's own export calendar's predecessor of E** (one
calendar per record): every daily read at D is the stock's bar DATED that calendar session, never the stock's own bar index e − 1 (if the
stock has no bar dated D, every D context is MISSING, §3d). Units: ADR20 is the frozen record's `adr20` (`rev.adr20_at(bars, e − 1, b)`, a
fraction of price, prior 20 sessions) — `adr20_at(bars, e − 1, b)` is KEPT for identity with the rule-mix, and the by-date assertion
reconciles it: if the stock's bar e − 1 is not dated D, every D context is MISSING; the dry run and G6 assert it on every trade.

**Cuts.** A continuous context is split at the 2020 pool's TERTILE boundaries — T1 = the ⌈n/3⌉-th and T2 = the ⌈2n/3⌉-th smallest value
among the decision's 2020 scorable trades whose value is DEFINED (missing values excluded); a trade goes left when its value ≤ the cut. **The
cut VALUES cannot be known now (they need bars): the dry run computes them before any bucket is read, prints them and they are pinned under
the marker** — the same pattern as the rule-mix's library order (a constant printed by the dry run). A binary context has one cut. Where his
words give a number it is a candidate too (C-S1: one ADR). **Dedupe:** candidate splits that give the SAME 2020 partition (after the
missing rule of §3d; ties at a mass point can make T1 and T2 one partition) are merged before trees are counted — the earlier in the order
of §5c is kept. The dry run prints every candidate split's 2020 child sizes (outcome-free), so a registered candidate the floor kills is
visible before the freeze.

**3a. ENTER (decision: which level he bought).**

| id | context | definition | read at | cut candidates | his words |
|---|---|---|---|---|---|
| C-E1 | **opening volume** | the mean volume per minute over the buy day's minutes from 09:30 to strictly before min(09:35, flat_clock), ÷ (ADV20 ÷ 390), ADV20 = the mean daily volume of the 20 sessions to D; MISSING when no minute lies before the bound (a 09:30 flat_clock: 0 / 7 / 0 by block, from the clocks) | min(09:35, flat_clock) | T1, T2 | l.1712-1713 — his EP words, TRANSFERRED to all trades (our reading); l.1735-1736 is the notes' summary |
| C-E2 | **the daily breakout still ahead at the open** | the buy day's open ≤ the prior session's high (1) or above it (0) | the open | binary | l.2091-2092 (*"enter when the stock is starting to break out"*); l.1942 |
| C-E3 | **the market's trend** — OUR READING (his words do not tie the market to the entry) | SPY's 50-day average at D higher than 10 sessions earlier (uptrend) or not — on the pinned era export (§10) | D's close | binary | l.2606 (the method line's example context); l.2481 is a phrasing ruling; the registered reading `scripts/probes/_702_race_1022/03_market_trend_split.py` l.1-3 |

Not on the list, by rule: the bracket's width and its clocks (the panel's resolution and his own action, not a context — §1 4h); the gap's size
(no number in his words; C-E2 carries its breakout half); speed (not in his entry words; the method line's speed example is the trail);
the setup (known at ±0, §1 4e — beside: dated and EP counts per group).

**3b. STOP (decision: which level took him out of a loser).**

| id | context | definition | read at | cut candidates | his words |
|---|---|---|---|---|---|
| C-S1 | **the stop's width against his cap** | (fill − the lowest low of the buy day's minutes STRICTLY BEFORE the fill minute) ÷ (ADR20 × fill); for the close-fill proxy, every minute of the session before the close; **MISSING on open fills** (no minute precedes the fill) and when no minute precedes it | the fill | **1.0 (his cap)**, T1, T2 (on the defined rows) | l.1943 (*"should not be wider than the ATR or ADR"*); mechanically coupled to S1-T (§1 4c) |
| C-S2 | **speed** | ADR20 | D | T1, T2 | l.2046-2047, l.2095-2096 — his trail words; transferred to the stop is our reading |
| C-S3 | the market's trend — OUR READING | as C-E3 | D's close | binary | l.2606 (the method line); l.2481 is a phrasing ruling |

**C-S1 on 2020, stated now (from the populations, no bar):** every undated row fills at the open (by `fill_src`: 211 of the 333 2020 EXIT trades
with room, 150 of 229 on 2021-22, 28 of 44 untouched — every undated row; the 91 undated of 139 2020 STOP losers, `01_mix_tag.txt` l.337), so C-S1 is MISSING on 91 of 139 and defined on the 48 dated
losers: T1 / T2 are the 16th / 32nd of 48, a child of about 16 against the floor of 15, and the 91 missing follow the larger child — so a
C-S1 split is "dated, with a narrow (or wide) stop" against the rest, a sub-partition of the dated trades. His 1.0 cut: the registered entry
flagged 43 ORH5 fills (all blocks; 18 of the 333 2020 EXIT trades with room by `fill_src`) whose low-of-day stop was wider than one ADR20
(`fill_orh5_too_wide`, tag printout l.9), so its wide child on 2020 STOP losers is about 18 or fewer (the runner's flag may read the low
INCLUDING the fill minute, C-S1 strictly before it, so the counts can differ) and is expected to fall under the floor of 15; the dry run
prints it (the loser column is not read against the flag here).

**3c. EXIT (decision: which rule sold the last share).**

| id | context | definition | read at | cut candidates | his words |
|---|---|---|---|---|---|
| C-X1 | **speed** | ADR20 | D | T1, T2 | l.2046-2047 (*"10d for faster stocks and 20d for slower stocks"*), l.2095-2096, l.2054-2055 (the notes name ADR); a prior read at 4.79% (§1 4e) |
| C-X2 | **how far from the 10-day** | (close_D − SMA10_D) ÷ (ADR20 × close_D) | D's close | T1, T2 | l.2047 (*"also depend how far the are from 10/20"*) |
| C-X3 | **how far from the 20-day** | (close_D − SMA20_D) ÷ (ADR20 × close_D) | D's close | T1, T2 | l.2047 |
| C-X4 | the market's trend — OUR READING | as C-E3 | D's close | binary | l.2606 (the method line); l.2481 is a phrasing ruling; l.1948 is about move size |

The SMAs are the frozen `smas_for(bars)` series read at the index of the stock's bar dated D on the record's own calendar. The setup (our
binary reading of l.1714 / l.1732 / l.1946-1947) prints beside every EXIT group, out of the search (§1 4e).

**3d. Missing values.** A context the record cannot give is MISSING: C-E1 with no minute before its bound (a 09:30 flat_clock) or no buy-day
minutes; C-S1 on an open fill or with no minute before the fill; an SPY bar missing at D or 10 sessions earlier; fewer than 20 sessions for
ADV20; **no stock bar dated D on the record's calendar** (every D context). The trade follows the LARGER child (by 2020 count of defined
values) at every split on that context; the floor is checked on each child's full count, missing included; counted per context, decision
and block. **Expected:** C-S1 missing on 91 of 139 / 76 of 116 / 8 of 12 STOP losers (the undated, `01_mix_tag.txt` l.337, l.414, l.491);
C-E1 missing on 0 / 7 / 0 (the 09:30 flat clocks); the others near zero (the dry run counts them, outcome-free).

## 4. "CLOSE TO" — defined now, in numbers

**4a. STOP and EXIT: the booked session within his sell window, widened by ONE session on the side the firing's own booking convention can
move it — the primary, "±1c" (convention-aware).** A firing `f` is the rule's first firing re-built UNCHANGED by the frozen rule-mix module
(its booked session per firing, §4a of that registration: M-1 and every H cell book a close on the day's last 60-minute bar on the NEXT
session; M-7 books on the next session; touches and the other daily rules on their own session). Each Fire carries its event session `je`
and its booked session `jb`; **next-session-booked ⇔ `jb > je`**. An R2 Fire (with an `alt` reading) takes its side from the OUTER
Fire's (`jb`, `je`), and both readings are evaluated by the frozen `bucket` on that one window (the frozen function untouched). A rule is CLOSE on a trade at ±1c when the frozen
`bucket(f, lo_f, hi_f)` reads EXPLAINS, with
- a SAME-session-booked firing (`jb == je`): [lo_f, hi_f] = [exit_lo_j − 1, exit_hi_j] — the other convention (the next open) moves the
  sale one session LATER, so a firing booked on exit_lo − 1 may be his sale;
- a NEXT-session-booked firing (`jb > je`): [lo_f, hi_f] = [exit_lo_j, exit_hi_j + 1] — the other convention (the close) moves the sale one
  session EARLIER, so a firing booked on exit_hi + 1 may be his sale;
- a rule that never fires, or abstains, reads by the frozen function on [exit_lo_j, exit_hi_j] (no side to widen).
At ±k symmetric (beside), [lo, hi] = [exit_lo_j − k, exit_hi_j + k] for every firing. What widening does (each a consequence of the frozen
function, stated so a test can hold it):
- a firing booked on exit_lo − 1 reads CLOSE exactly when ±0 read it MISS-EARLY (no missing session before its event and no buy-day
  unresolved flag) — a firing on a session he certainly held (the §6a certainty rule; a buy-day firing without an in-session buy-day frame
  stays UNRESOLVED);
- a firing booked on exit_hi + 1 reads CLOSE when ±0 read it NEITHER, unless a missing session lies before its event (then UNRESOLVED);
- **UNRESOLVED CAN upgrade** in one case of the frozen function: a NEXT-session-booked firing whose event lies on exit_hi when exit_hi is
  itself a missing session (no other missing session before the event). ±0 reads UNRESOLVED (a missing session at or before exit_hi, the
  firing booked after it); once the widened window contains the booked session, the function reads only missing sessions BEFORE the event,
  so it reads EXPLAINS. Never overridden: a test pins the frozen `bucket`'s behaviour on that case, and the run counts such upgrades per rule,
  block and tolerance and prints them;
- first firing only (a rule that fired before the widened window is MISS-EARLY however often it fires later); the window is clipped at the
  buy day (offset 0) and at J_tail.

**Why one session, and why one-sided, from the offsets.** One-session sell windows are 231 of 333 EXIT trades on 2020 and 165 of 229 on
2021-22 (108 of 139 and 80 of 116 STOP losers). The rule-mix fixed ONE booking per rule; an execution at the other convention — the close
instead of the next open, or the reverse — moves the sale by exactly one session in ONE direction per firing, and on a one-session window
that turns a sale on the rule into NEITHER (a close on the last 60-minute bar books the next session) or MISS-EARLY. **±1c absorbs the
booking convention, not his imprecision;** the symmetric ±1 (beside) admits about twice that looseness. It does not absorb a lag of two or
more sessions before exit_lo, nor a partial he sold earlier (§12).
**What the sensitivity lines show, beside (same procedure, same controls, printed and labelled, never in the summary):** ±0 = the rule-mix's
own EXPLAINS (identity-gated row for row, §11 G1) — the map against the exact tags; the symmetric ±1; ±2 = on a median window start at
session 4, a five-session window covers most of a short hold, so every rule and every control nears its ceiling and gains compress. A gain
at ±1c that vanishes at ±0 is the booking convention; one that holds at ±0 and ±1c and compresses at ±2 is the expected shape of a real one.
**The controls take the same widening, per firing:** every placement [s, s + width − 1] becomes [s − a_f, s + width − 1 + b_f] through the
frozen `bucket_vec` (frames and no-frames modes, R15), with (a_f, b_f) = (1, 0) for a same-session-booked firing and (0, 1) for a
next-session-booked one at ±1c, (k, k) at ±k; every random level through `touch_buckets_vec` on the widened window. **Clipping at offset 0:**
a placement at s < a_f gets less widening than the real window usually does (exit_lo_j = 1 on 102 of the 333 2020 EXIT trades, from the
offsets), which biases control (a) down; the run prints the share of clipped placements per decision, block and tolerance, and a control
(a) variant restricted to placements with s ≥ a_f, beside.

**4b. ENTER: the level first crossed inside his buy bracket (flat_clock, first_clock] — primary.** This is the rule-mix's ENTER EXPLAINS
(identity-gated against `tags_enter.tsv`). **Why not the union "crossed inside the bracket or within the registered ballpark":** a level
crossed inside the bracket lies inside the bracket's traded range, so that union equals the registered hit-or-ballpark (HIT = inside the
bracket's [lowest low, highest high]; BALLPARK = within 0.25 ADR20 of the nearer edge, `cb_reverse_engineer_his_rules_prereg_2026-10-24.md`
§6c, the intraday §5b), and a random price already reads 85.9% hit-or-ballpark on the 41 undated 2021-22 windows (`01_rev_check.txt`;
re-read by the rule-mix's gate (vii), `01_mix_tag.txt` l.24). No map can beat the best single rule by 10 points under it. **The bracket is
ENTER's tolerance the way a session is EXIT's** (in-session bracket median 27 minutes on 2020, 46 on 2021-22, non-flicker windows — from
the clocks). Beside,
two looser lines (printed, labelled, never in the summary; §13 Q1, DECIDED):
- **B1 RE-CROSS** — CLOSE also when the level was first crossed at or before flat_clock and is crossed AGAIN inside the bracket: a minute t
  in (flat_clock, first_clock] whose high ≥ the level, preceded by a minute u in [flat_clock, t) whose close < the level, the level existing
  by t (he bought the same level on its second break). New code (§11); its own control lines.
- **B2 HIT-OR-BALLPARK** — the instruction's union, through the frozen `range_verdict(mb, price, flat_m, first_m, adr20)`; expected at
  ceiling for every level and every control (stated, §9).

## 5. THE MAP — shallow, one library rule per group, chosen on 2020

**5a. The rules a group may take:** the rule-mix library as frozen (`LIBRARY[decision]` in `01_mix_frozen_75c832541cef.py`): ENTER L1, L8,
L2, L7, L3, L9, L4; STOP the 15 cells S1-T … S4-C; EXIT M-1, M-2, M-3, M-4, M-5, M-9, M-6, M-2s, M-11, M-7, M-8, M-10. Nothing added.

**5b. The tree.** Binary splits, each one context × one cut (§3). Depth ≤ 2: no split (one rule for all), one split (2 groups), or one split
whose children are each a group or one further split (3 or 4 groups) — **at most 4 groups.** **Every group holds at least m of the 2020
trades, m = max(15, ⌈0.10 × n_2020⌉): ENTER 15, STOP 15, EXIT 34.** A split that leaves a child under m is not a candidate. A child may split
on the root's context at its other cut (a three-way cut on one context). On 2021-22 a group may be small; its n is printed, no floor.

**5c. The search is exhaustive.** Candidate splits (the setup is out, §13 Q5): ENTER 4 (C-E1 × 2, C-E2, C-E3), STOP 6 (C-S1 × 3, C-S2 × 2,
C-S3), EXIT 7 (C-X1 × 2, C-X2 × 2, C-X3 × 2, C-X4). Trees before the dedupe and the floor: 1 + s + s·((s + 1)² − 1) = **101 / 295 / 449**;
after the dedupe of §3 (identical 2020 partitions merged) the count can only fall, and the dry run prints it. Each group's rule = the
library rule with the most CLOSE trades in that group on 2020 (ties → the library order). The CHOSEN map = the tree with the most CLOSE trades
on 2020; ties → fewer groups, then the earlier root split in the order above (contexts in §3's order, cuts ascending, T1 before T2, his
1.0 first on C-S1), then the left child's option before the right's (a group before a split; splits in the same order). The canonical
enumeration is a constant of the module; the dry run prints the tree count per decision and the first ten trees in order.

**5d. Scored** as the share of the block's scorable trades whose group's rule is CLOSE (UNRESOLVED counts in the denominator and in no
numerator — the rule-mix's convention), with its 95% binomial interval and n. Per group: n (2020, 2021-22, untouched), the rule, its CLOSE
share on each block, the setup stratification (the dated and EP counts — the setup is not a context, §1 4e), and the confound line (ENTER:
the median bracket width; STOP / EXIT: the median window width and exit_lo_j). **Paired intervals, beside (descriptive, never in a label):**
MAP − BEST and MAP − SHUF's mean are PAIRED differences on the same trades, so each prints with a paired bootstrap 95% interval (2,000
resamples of the block's trades, seed 702, key `ctx|boot|{decision}|{block}|{line}|{r}` through `rng_for`; the map, the groups and BEST
held fixed — a resample re-scores, it does not re-search) and the exact McNemar count of discordant trades (MAP close & BEST not / BEST
close & MAP not).

**5e. Beside — three more maps, each scored and labelled like the map, NEVER in the summary label.**
- **MAP-T1, his words only:** the same search restricted to the tier-1 rules (ENTER L1, L8, L2, L7, L3; EXIT M-1, M-2, M-3, M-4, M-5, M-9,
  M-6, M-2s, M-11). STOP has one tier-1 cell (S1-T), so its MAP-T1 is the single rule. Why beside: the full-library map describes him; MAP-T1
  is what Apollo would rebuild from his own words (§13 Q3, DECIDED).
- **HW, his words' own maps — fixed, no search** (the cut = the 2020 median where his words give no number, ⌈n/2⌉-th value, ≤ goes left):
  HW-E: C-E1 (the clipped definition of §3a; its median over the defined 2020 rows) above the median → L1, else → L8 (l.1712-1713: the
  5-minute bar if opening volume is large enough, else the first 1-hour bar, whose first candle is 09:30-10:00, l.2090); HW-S: C-S1 ≤ 1.0 →
  S1-T, else → S4-T (l.1943; a MISSING C-S1 — an open fill — follows the larger side, §3d: the ≤ 1.0 side, which holds all but about 18
  or fewer of the 48 defined 2020 rows, §3b); HW-X: C-X1 above the median → M-3
  (the 10-day), else → M-4 (the 20-day) (l.2046-2047); **HW-X'**: the same at Apollo's own cut, C-X1 > 0.0479 → M-3, else → M-4
  (`TRAIL_SPEED_ADR_CUT`, `consolidation_breakout.py` l.186; the exits study's fast vs slow, §1 4e) — no search freedom added, so §8's
  "recreate for Apollo" reads the cut Apollo actually runs. The 4.79% cut is NOT added to the search (it would add trees and its 2020 read
  exists).
- **SW, the 10/20 switch — a COMPOSITE rule, NOT in the library, flagged.** His *"also depend how far the are from 10/20"* read at EVERY
  held session's close: on held session j (offset 0 = the buy day) the trail in force is the 10-day when the distance of close_{j−1} above
  the 20-day (C-X3's formula; close_{−1} = close_D) is ≥ T2 of C-X3, else the 20-day; SW fires at the first close j below the trail in
  force (booked on its own session, as M-3 / M-4). His words do not say which way the distance points, so two readings print: **SW-a** (far
  → the 10-day) and **SW-b** (far → the 20-day). Known answer (§11 G4): with the cut at −∞, SW-a ≡ M-3 and SW-b ≡ M-4; at +∞ the reverse —
  first firing for first firing on every trade. Scored as a single rule (it has no groups) against the same comparators. Registered now,
  beside, never in the summary label (§13 Q4, DECIDED).

## 6. THE COMPARATORS AND THE CONTROLS (each names the failure it guards)

- **(a) BEST — the best single rule for all trades:** the no-split tree (the rule with the most CLOSE trades on 2020; ties → the library
  order), scored on every block. Beside: **ORACLE-1**, 2021-22's own best single rule chosen on 2021-22 (an upper bound for one rule there).
- **(b) SHUF — the chance of a context map:** 200 permutations (seed 702, key `ctx|perm|{decision}|{block}|{p}` through the frozen
  `rng_for`) of WHOLE context rows across the block's scorable trades, 2020 and 2021-22 permuted independently; the CLOSE matrix is never
  permuted. On each permutation the FULL procedure re-runs — the search on permuted 2020 (the cut values are unchanged: a permutation does not
  move a tertile), the chosen tree scored on permuted 2020 (in-sample) and on permuted 2021-22. The line = the mean; the 95th percentile and
  the real map's percentile print beside. The untouched block is NOT permuted (its sign check carries no SHUF term, §7a). Guards
  constraint 4b.
- **(c) CHANCE — random buyers and sellers, two lines, each over the rule-mix's arms:**
  - **(c-1) the PER-LEAF CHANCE of the chosen map:** the real map (chosen on his trades) applied unchanged to the control draws, each trade's
    draw scored with the rule of THAT trade's group — never the pooled best rule — the mean over trades. For the no-split tree it equals
    the best single rule's own chance share (§11 G5). Exact where the rule-mix enumerates (control (a): the mean over each trade's
    placements, then over trades). Guards constraint 4c.
  - **(c-2) the procedure on the controls:** the full search re-run on each control draw's CLOSE matrix (chosen on 2020's draw, scored on
    2021-22's draw), 200 draws, the mean — the chance of a context map for a random buyer or seller.
  - **The arms.** ENTER: the k-price random prices (the frozen rule-mix `K_KEY` = `mix|rprice|{eid}|{d}|{i}`, i = 1..7, price i standing
    for library rule i, 200 draws, seed 702) and the shared random window (`SHARED_KEY` = `mix|bracket|{eid}|{d}`, every level in one window
    of his bracket's width). STOP / EXIT: control (a), a window of his sell window's width inside the hold, frames and no-frames modes (for
    (c-2) one placement per trade per draw, uniform over the trade's (a) placements, key `ctx|place|{decision}|{eid}|{d}`, seed 702, because
    a map needs one joint placement across trades), and the random levels — for (c-1) the single-level draws (`RLEVEL_KEY` =
    `mix|rlevel|{eid}|{d}`, the rule-mix's per-rule floor), for (c-2) the k-level draws (`RLEVEL_K_KEY` = `mix|rlevel|{eid}|{d}|{i}`, k = 15
    STOP / 12 EXIT, level i standing for rule i). **Every arm prints on its own line, for the MAP and for BEST** (the no-split tree's
    (c-1) is G5's value; its (c-2) is the no-split procedure on the same draws); the label of §7a is computed arm by arm on GAINS, never on
    the largest arm's level — the largest prints beside only to match the rule-mix's layout.
  - **Which arm carries the mechanical check.** A random price or a random level does not depend on which rule a trade takes, so on those
    arms (c-1) is the same, in distribution, for every map — they measure how easy the POPULATION is (dated windows are easier: the per-rule
    k-price floor 23.6% dated vs 19.5% undated on 2020, l.75, l.91). The rule-specific mechanics — a rule that is first crossed inside a
    bracket, or fires inside a window, more easily in one group than another — show only on the TIMING arms (control (a) and the shared
    window), where each trade's own group rule is evaluated in a random window. Stated so the reader does not take a flat price arm for the
    guard — and the reason `beats chance` is a test on the GAIN per arm (§7a): on levels, the largest arm (the k-price arm on ENTER, 21.0% /
    31.3%, l.59, l.155; the random level on STOP, 40.4% / 41.7%, l.289, l.366) is flat across maps and BEST already clears it (L1 by 15.4 /
    12.0 points, S1-T by 4.9 / 3.1), so a levels test would follow from `context helps` and hide a gain the timing arm also shows.
- **(d) UNION — the ceiling:** the share of trades on which ANY library rule is CLOSE — no one-rule-per-trade map can exceed it. Printed per
  block and tolerance, with the map's share of the gap closed = (map − BEST) ÷ (UNION − BEST).

## 7. THE INFERENCE — labels fixed now, and what this read does NOT decide

**7a. Labels (a description, not a verdict), compared on the printed one-decimal percentages, at the primary tolerance (ENTER the bracket,
STOP / EXIT ±1c), each required on BOTH 2020 AND 2021-22:**
- **`context helps`** = MAP ≥ BEST + 10.0 points AND MAP ≥ SHUF's mean + 10.0 points.
- **`beats chance`** — on GAINS, arm by arm, never on the largest arm's level: for EVERY arm a of §6c,
  (MAP − BEST) − ((c-1)_a(MAP) − (c-1)_a(BEST)) ≥ 10.0 AND (MAP − BEST) − ((c-2)_a(MAP) − (c-2)_a(BEST)) ≥ 10.0, where (c-1)_a(BEST) is
  G5's value (the no-split tree on arm a) and (c-2)_a(BEST) is the no-split procedure's mean on arm a's draws. Every term prints in the §11
  template, so the label is decidable from the printout.
- **The decision's summary:** `context map` = both labels; `context helps, chance too` = `context helps` without `beats chance` (the gain is
  the path's shape, not him); `no context gain` = otherwise.
- **The untouched block: a sign check, never labelled** — the 2020-chosen map minus BEST, the sign (+ / 0 / −) and n. No SHUF term: SHUF
  permutes 2020 and 2021-22 only (§6b).
- The same labels print for ±0, the symmetric ±1 and ±2 (STOP / EXIT), B1 and B2 (ENTER), MAP-T1, HW, HW-X' and SW — beside, never in the
  summary.

**7b. What a share means.** The map's share is the part of his trades a context-picked rule matches closely; BEST is one rule for all;
the gap between them is what context adds; SHUF is how much of that gap a search finds in noise; (c) is how much a random buyer or seller
would get from the same map. A label orders the next registration's candidates; it moves no rule, threshold, size or safeguard (THE LINE).

**7c. Honest status — why nothing is decided here.** His unseen trades are used up for these rules: 2021-22 was the check for every library
rule (the rule-mix tag printed every rule's ±0 share there, on dated and undated trades apart; the intraday and reverse reads checked
L1-L9, E1-E4 and every stop cell on it; the exits study read fast vs slow at 4.79% against his 2020 exits, `cb_his_exits_study_2026-10-24.md`
l.71-72), and the untouched years were their vetoes. **The setup context's joint with every rule's ±0 bucket is therefore NOT new** (§1
4e) — it is out of the search. What is NEW is the other contexts, their joint with the buckets, the widened buckets and the maps — so
2021-22 shows whether a map chosen on 2020 TRANSFERS, which is information, not evidence. The untouched block (9 / 12 / 44) is a sign check.
**The only confirmatory tests left, named:** (1) **the forward shadow** — a map labelled `context map` recorded as an arm beside the live
watch names (§8; adding an arm is his sign-off), read by the forward read on settled entries; (2) **#710's one sealed 2025-26 run** — a map
is a candidate branch for that registration to adopt or not; this read writes no branch.

**7d. What a BROKEN pipeline prints (so the expected shape confirms nothing).** WOULD-FAIL-IF:
- **a group's rule leaks into the control scoring** (the controls scored with the pooled best rule instead of each trade's own group rule):
  MAP reads `beats chance` while SHUF stays flat — caught by G5 (the no-split tree's (c-1) must equal the best rule's own chance share) and a
  planted-leak test;
- **a context is read after its decision time** (a session ≥ the buy day for a D context; a minute at or after min(09:35, flat_clock) for
  C-E1; the fill minute or later for C-S1): contexts correlate with the outcome, MAP gains on both blocks AND beats SHUF — caught by guard
  D1 (truncated views), G6 and a planted-future-bar test;
- **C-E1 read at 09:35 on a bracket that opened before it** (the 17 / 20 / 1 brackets with flat_clock before 09:35): on those trades he
  may have bought before the context existed, so opening volume correlates with buying the early level (L1 / L7) — a false `context helps`
  on C-E1 that SHUF cannot see (a permutation carries the leak with the row) and the k-price arm does not move. Caught by the clip of §3a,
  by G6 truncating PER TRADE at min(09:34, flat_clock − 1 minute), and by a synthetic bracket opening at 09:32 whose 09:32-09:34 minutes are
  planted (they must change nothing);
- **contexts misjoined to trades** (a row shifted, a sort by sym instead of eid): the contexts carry no information about the trade, so it
  reads as a permutation — MAP ≈ SHUF, `no context gain` — a false NEGATIVE that G1 (buckets only) and G6 (recompute on the same record)
  both pass. Caught by `contexts.tsv` carrying eid + sym + E and a test asserting sym and E equal the tag row's by eid on every row;
- **a wrong calendar or an index off-by-one** (D taken as E; ADR20 indexed by the stock's own bar e − 1 while the SMA and SPY are read at
  the calendar's D): G6's truncated and full computations replay the same mistake, so G6 passes; if D lands on E it is look-ahead and a
  false POSITIVE. Caught by G6 asserting BY DATE: every bar in a context's view is dated < E (≤ the bound's minute for C-E1, < the fill
  minute for C-S1), and the bar it reads at D is dated the record calendar's predecessor of E; the synthetic world carries a record with no
  stock bar on D (it must read MISSING);
- **the permutation moves the CLOSE matrix or crosses blocks**: SHUF reads the wrong null — a test holds the CLOSE matrix byte-equal across
  permutations;
- **widening moves the scan origin** (every MISS-EARLY becomes CLOSE), **or the convention side is flipped** (same-session firings widened
  late, next-session firings early): the ±1c share sits near the UNION on every rule with precision near 100%, or ±1c reads like a shifted
  ±0 — caught by G1 (±0 re-reads the tags) and G3 (every widened bucket derivable from the ±0 bucket, `jb`, `je` and the missing sessions
  agrees);
- **the tertiles are computed on an outcome-bearing subset**: the dry run computes them on the scorable sets before any bucket column is
  read (guard D2).

## 8. FROM A MAP TO APOLLO — the second half of his ask ("then the challenge is to recreate those rules for apollo")

- **A decision labelled `context map` yields a small table — context → rule — and enters Apollo first as a RECORD, never an order.** Each
  context is something the live system already reads at the same decision time (ADR20, the 10- and 20-day, SPY's 50-day, the first
  minutes' volume, the prior high; the setup label stays a stratification, not a context); the map becomes one pure function, context in, rule id out, tested against this read's per-trade file.
- **EXIT →** one more arm in the consolidation-breakout forward shadow (`agents/market_intelligence/consolidation_breakout.py` `ARMS`; the
  rows in `mi_consolidation_breakout_exit.arm`, the recorder #705 (c) extends for `pp`, `consolidation_breakout_pp.py`): the context read at D,
  the group's rule walked, the row written beside `A` and `pp`.
- **ENTER / STOP →** one more arm in #482's bracket-geometry lab (`agents/market_intelligence/book_geometry_arms.py`; its 5-minute ORB lane
  and first-hour-bar arms exist, `_HOUR_ENTRY_ARMS`): a context-selected level is a selector over arms it already records.
- **Then** the forward read (`consolidation_breakout_forward_read`, 30 settled C1 entries) compares the map's arm with the single-rule arms.
- **THE LINE.** Adding an arm is a recorder change with no order path and still his sign-off; any paper or live use is his decision under
  CHANGE_PROCESS, a backtest and his sign-off. **This doc proposes no arm.** `context helps, chance too` or `no context gain` → nothing to
  record; the single-rule arms stay.

## 9. Expectations, written now (guesses to be scored, never targets; a miss changes nothing)

- **Known already (±0, the rule-mix):** BEST on 2020 = L1 36.4% (`01_mix_tag.txt` l.50), S1-T 45.3% (l.289), M-8 30.9% (l.554); on 2021-22
  L1 43.3% (l.146), S1-T 44.8% (l.366), M-8 27.9% (l.664; 2021-22's own best is M-2 28.4%, l.655); the UNION 56.8 / 66.7, 54.0 / 57.8,
  71.5 / 72.9 (l.58, l.154; l.305, l.382; l.557, l.667) — so the room a map has over BEST at ±0 is about 20 / 9 / 41 points on 2020.
- **ENTER (the bracket):** the chosen map one split (C-E2 or C-E1 at the root), 2020 in-sample 41-47%; SHUF's mean 39-43%; 2021-22 within 6
  points of L1's 43.3%; (c-1) 21-31% on the k-price arm (the per-rule random-price floor 20.8% / 30.9%, l.50, l.146), flat across maps, so
  the gain net of that arm equals the gain itself; the shared-window arm's gain under 3 points; `context helps` unlikely → **summary guess
  `no context gain`**. HW-E within 5 points of L1 alone. B2 at 85-92% for every map and control; B1 adds 5-15 points to every line, the
  controls' as well. C-E3's downtrend group (2020 buys Feb-May: 30 of 88 by date) may sit near the floor of 15.
- **STOP (±1c):** BEST S1-T at 50-60%; UNION 60-70%; the map 2020 +3-7 over BEST in-sample, SHUF +2-5; the random-level arm 45-55% →
  **`no context gain`**. HW-S within 2 points of S1-T alone (few dated fills wider than one ADR; open fills MISSING). Most C-S1 candidate
  splits die under the floor (his 1.0 cut almost surely).
- **EXIT (±1c):** BEST 38-48% (M-8 or M-1 or M-2); UNION 76-86%; the map 2020 +6-12 over BEST in-sample, SHUF +2-4 (n 333), 2021-22 +2-8;
  the control (a) arm's gain rises with the map's (the rule-mix union beat control (a) by only 1.7 / 2.0 at ±0, l.557, l.667) →
  **`context helps, chance too` or `no context gain`**. HW-X and HW-X' within 5 points of M-3 alone; SW-a / SW-b within 3 points of M-3 /
  M-4.
- **Tolerance shape:** ±0 gains smaller than ±1c by 0-4 points; the symmetric ±1 above ±1c on every line by 2-8 points; ±2 compresses every
  gap (BEST and chance both near 60-75% on EXIT). Clipped control placements under 10% of the total.
- **MAP-T1:** within 3 points of MAP on ENTER and EXIT (the full-library map picks a tier-2 rule in at most one group).

## 10. DATA GATE (STEP 0) — nothing new to fetch

- **Eras, exports, loaders, G8, the 2025-26 seal — unchanged** (era A = `cb702_pre_v2`, era B = `cb702` cut at 2024-12-31 and asserted; era by
  buy day ≤ 2022-03-31 A, else B; `trade_impact.py` before any number) — through the frozen rule-mix module.
- **Minutes:** the intraday fetch (`/Users/alvinfung/apollo_data/cb702/minutes_intra_1025/`, 19,470 pairs; `01_mix_tag.txt` l.8) holds every
  buy day (C-E1's opening minutes, C-S1's pre-fill minutes, B1's bracket minutes) and every session the ±2 windows and control (a) walk; a missing pair → the context is
  MISSING (§3d) or the firing UNRESOLVED (the rule-mix §4a), counted.
- **Daily bars:** the records' exports give ADR20, ADV20 (the loaded bars carry volume), the 10- and 20-day, D's close and the buy day's
  open; the minute bars carry volume (`MinuteBars.v`) for C-E1. **The minute trees may differ in volume convention** (A / B / EP / EP2 / REV
  / INTRA: feeds, split adjustment), so the dry run prints, per minute tree, C-E1's distribution and a coverage sanity check — the buy day's
  summed minute volume ÷ the export's buy-day volume (outcome-free, not a context; read for the bars' convention only) — and the main loop
  sees it before the freeze: a tree whose ratio sits apart means the tertiles would sort trades by data source. **SPY** comes from the SAME pinned era exports (`export_A` =
  `/Users/alvinfung/apollo_data/cb702_pre_v2/daily_closes_all.csv.gz`, `export_B` = `/Users/alvinfung/apollo_data/cb702/daily_closes_all.csv.gz`)
  and is already in every frozen load: the daily loader builds each era's calendar FROM SPY's rows (`load_daily_subset`, `spy = tid["SPY"]`,
  `scripts/probes/_705_qm_replay_1023/01_replay.py`), so SPY's close at D and 10 sessions earlier is a read on the record's own calendar,
  nothing added. The DEFINITION is the registered market reading's (`_702_race_1022/03_market_trend_split.py`); its era-A data file was the
  earlier `cb702_pre/` export, not the pinned `cb702_pre_v2/` — stated, so a 2020 split that differs from that printout by a session is
  read as the export, not the rule. Every SPY date read ≤ 2024-12-31 (guard 12).
- **One calendar per record** (guard 10): D, the buy day, exit_lo, exit_hi, every widened window and every placement are bisects on the
  record's own export calendar.

## 11. Files, the module, its gates and guards

- **Inputs (pinned at the dry run):** everything the rule-mix pinned (carried through the frozen rule-mix module's pins), plus the rule-mix
  tag printout, recount, per-trade tag files (`tags_enter.tsv`, `tags_stop.tsv`, `tags_exit.tsv`, `control_windows.tsv.gz`), the frozen
  rule-mix module `scripts/probes/_705_rule_mix_1025/01_mix_frozen_75c832541cef.py` (sha256 `75c832541cef…`, refused on drift) and the
  rule-mix registration's `doc_body` (`6a2512024c5f…`).
- **Code:** `scripts/probes/_705_context_1026/01_ctx.py` + `tests/test_context_rules.py` (every module, printout, ledger and pins path of
  this read lives in `scripts/probes/_705_context_1026/`; the per-trade files in its `out/`). **Imports the FROZEN rule-mix module
  read-only** and through it the frozen intraday module (`scripts/probes/_705_intraday_1025/01_intra_frozen_ac598fc58aae.py`, sha256
  `ac598fc58aae…`, refused on drift), the frozen reverse module, the holdings replay, the runner and `cb`. **The tag files are reused as the
  ±0 reference:** the ±0 CLOSE matrix is read from their bucket columns AND re-built from the frozen Fires — G1 holds the two equal — and the
  widened (±1c, ±1, ±2) matrices come from the re-built Fires (the files carry no missing-session or buy-day-frame flags, so a widened bucket cannot be
  read from them alone). Reused as they are: the record builders and populations, `exit_fires`,
  `stop_fire`, `Fire`, `bucket`, `bucket_vec`, `random_windows`, `random_level_draws`, `touch_path`, `touch_buckets_vec`, `enter_one` and its
  draw replay (`K_KEY`, `SHARED_KEY`), `LIBRARY`, `rng_for`, `fnum`, `IdCache`, `smas_for`, `range_verdict`, `rec.adr20`. **The path trap,
  one layer up:** the frozen rule-mix module's freeze, dry-run, ledger, pins and output helpers (`DOC`, `P_DRY`, `LEDGER`, `OUT_DIR`,
  `mix_pins`, `tag_lock`, `mix_stage_outputs`, `mix_dry_run_complete`) default to the RULE-MIX files — a bare call would pass guard (1) on
  the rule-mix dry run and append to its ledger. They are reused ONLY with this read's paths passed explicitly, or replaced by this module's
  own `ctx_*` helpers. **Own code, small and tested:** `CONTEXTS[decision]` (§3's tables as constants with their cites), `context_row(rec)`
  (built ONLY from a decision-time view: daily bars dated ≤ D, the buy day's open, the buy day's minutes strictly before min(09:35,
  flat_clock) for C-E1 and strictly before the fill minute for C-S1), `tertile_cuts` (on the defined rows), `dedupe_splits`, `close_matrix
  (fires, tol)` (tol ∈ {±0, ±1c, ±1, ±2}; ±1c widens per Fire by `jb > je`), `recross` (B1), `enumerate_trees(splits, m)` (the canonical
  order of §5c), `fit_map`, `score_map`, `paired_interval`, `shuffled`, `per_leaf_chance`, `procedure_on_controls`, `hw_maps` (incl.
  HW-X'), `switch_fire` (SW), the tables.
- **Stages:** `--dry-run` (populations re-asserted against the tag files by eid, reading ONLY their label, offset, clock and fill columns —
  never a bucket column; every context computed from decision-time views; missing counts; the tertile cuts and the HW medians printed;
  every candidate split's 2020 child sizes and the dedupe; the tree counts after the dedupe and the floor, and the first ten trees; per
  minute tree C-E1's distribution and the minute ÷ export buy-day volume ratio (§10); SPY's presence; coverage from the fetch logs; pins; no
  outcome), `--pins`, **`--run` (ONCE, after the freeze: the
  gates, then ENTER → STOP → EXIT on every block and tolerance, the comparators, the controls, the tables, the per-trade files)**,
  `--reset "<reason>"` (after a STOP only; archives, never deletes; the event pinned under the marker before `--run` may run again).
- **Known-answer gates at the top of `--run`, each STOPS the run before any new number** (cleared only by a bug fix shown in the code, never
  by changing a registered rule): **G1 identity** — the re-built ±0 buckets equal the tag files cell for cell (`tags_enter.tsv`: each
  level's `_bucket` and `_cross`, `tag`, `earliest_tag`, `kprice_union`, `shared_union`; `tags_stop.tsv` / `tags_exit.tsv`: each rule's
  `_bucket`, `_first_j`, `_booked_j`, `_first_minute`, `tag`, `earliest_tag`, `ctl_a_union`, and on EXIT `ctl_b_union`, `rlevel_ex`),
  parsed as the files serialize them — offsets and minutes as float strings ('3.0' → `int(float(x))`), a blank cell → None (still-held and
  never-fired rows), 'True' / 'False' → bool;
  **G2** the no-split tree's ±0 share re-reads the rule-mix standalone shares at one decimal (2020: L1 36.4%, S1-T 45.3%, M-8 30.9%;
  2021-22: L1 43.3%, S1-T 44.8%, M-8 27.9%) and the ±0 UNION re-reads 56.8 / 66.7, 54.0 / 57.8, 71.5 / 72.9; **G3 tolerance consistency** —
  every widened bucket derivable from (±0 bucket, `jb`, `je`, the missing sessions) agrees, at ±1c with the side set per Fire (same-session:
  MISS-EARLY booked on exit_lo − 1 → CLOSE; next-session: NEITHER booked on exit_hi + 1 → CLOSE or UNRESOLVED, and UNRESOLVED → CLOSE only
  in the one case of §4a; EXPLAINS stays; an R2 Fire's side from its outer Fire) and at the symmetric ±1 / ±2 with both sides — a planted one-session shift of one `booked_j`, or a
  flipped side, must FAIL; **G4** SW at the cut −∞ / +∞ equals M-3 / M-4
  first firing for first firing on every EXIT trade; **G5** the no-split tree's (c-1) equals the best rule's own chance share as the
  rule-mix printed it at ±0, arm by arm (2020: L1 k-price 21.0%, l.59, and shared window 3.1%, l.50; S1-T control (a) 30.0% / 31.5% and the
  single-level random-level floor 40.4%, l.289; M-8 control (a) 28.7% / 28.7% and random level 23.6%, l.554; and the same rows on 2021-22) —
  a pooled-rule leak or a re-drawn stream fails it; **G6** the decision-time guard — every context re-computed from views truncated at its
  decision time, PER TRADE (daily views at D; C-E1 at min(09:34, flat_clock − 1 minute); C-S1 at the minute before the fill), equals the
  full-record computation on every trade, AND asserts BY DATE that every bar in a context's view is dated < E (the minutes ≤ the bound) and
  that the bar read at D is dated the record calendar's predecessor of E.
- **Guards (the rule-mix's twelve, kept; stated where this read differs):** (1) the line-anchored freeze lock — `--run` refuses unless every
  pin incl. `doc_body` (the sha256 of this file's bytes above the one line that is exactly the freeze marker; the literal appears once in
  this file) sits under the marker BY NAME (an ABSENT pin on its own `- name: ABSENT` line), the module's sha equals its pin, THIS read's dry
  run (`01_ctx_dryrun.txt`, passed by path) opens with this read's header, carries a `RESULT: .. 0 MISMATCH` line and ends `DRY RUN
  COMPLETE`, and the run printout does not exist; **the tertile cuts, the HW medians, each candidate split's missing side and the tree order are constants printed by the dry run
  and pinned — no chosen line is written above the marker after the freeze**; (2) the module copied beside the pins before any post-run
  edit; (3) populations asserted before any bar; (4) G8 before numbers; (5) **the 2020 / 2021-22 split is a CHOOSE / SCORE split, not a
  held-out set — both blocks' ±0 buckets are known — so there is no forbidden-pairs guard; every block is read once (`BarGuard(allowed_eids=
  None)`), said plainly**; (6) a crash writes a STOPPED file; the only way past it is `--reset`; (7) the append-only sha256 ledger; (8)
  misread clocks EXCLUDE (§2c of the intraday read, inherited); (9) `replay/` and `his_exits/` never opened; (10) one calendar per record;
  (11) `IdCache` only — it holds the object it keys, and a module scan fails on any other `id(`; (12) the 2025-26 seal — every date read
  asserted ≤ 2024-12-31. **Added: (D1)** contexts only from decision-time views (G6 and a test); **(D2)** the tertiles and medians computed on
  the scorable sets before any bucket column is read; **(D3)** never `float()` of a numpy array — `fnum` only (module scan); **(D4)** a module
  scan that every reused freeze, dry-run, ledger, pins or output helper is called with this read's path, and a test that the lock refuses when
  only the rule-mix dry run exists.
- **Tests (synthetic, before any real run; `tests/test_context_rules.py`):** **the tests never read the live doc** — they read a fixture copy
  of the registered doc under `scripts/probes/_705_context_1026/fixtures/` (this read's folder, the write scope; C20) — and carry **no absolute machine path** (CI runs on a shallow clone elsewhere; a scan
  asserts no '/Users/' in the test file); **every module scan carries a reviewed `# source-pin-ok: <reason>`**. The tree enumeration's count
  and canonical order on a toy (101 / 295 / 449 before the dedupe and the floor; a dedupe of two identical partitions); the floor; the tie
  rules; a missing context following the larger child; the ±k and ±1c bucket mapping on hand-built Fires (same-session: MISS-EARLY on exit_lo
  − 1 → CLOSE at ±1c, a firing on exit_hi + 1 stays NEITHER at ±1c; next-session: a firing booked on exit_hi + 1 → CLOSE at ±1c, one booked
  on exit_lo − 1 stays MISS-EARLY at ±1c; a buy-day firing without an in-session frame stays UNRESOLVED; a firing on exit_hi + 1 after a
  `no_bar` session → UNRESOLVED; the one UNRESOLVED → EXPLAINS case of §4a pinned against the frozen `bucket`; an R2 Fire whose two
  readings book on different sides takes the outer Fire's side; first firing only); the
  clipped-placement share and the s ≥ a_f control variant; the contexts.tsv join (sym and E equal the tag row's by eid); B1 on a minute world (a first crossing before flat, a dip under the level, a second break inside → CLOSE; no dip →
  not); the permutation moves context rows only, within a block, the CLOSE matrix byte-equal; (c-1) scores each trade with its own group's
  rule (a planted pooled-rule leak FAILS); SW against M-3 / M-4 at the extreme cuts and on a world where the trail switches mid-hold; the
  decision-time guard (a planted bar on the buy day or later changes no D context; a planted 09:35 minute changes no C-E1; on a bracket
  opening at 09:32, planted 09:32-09:34 minutes change no C-E1; a planted fill-minute low changes no C-S1); the HW maps' fixed groups (HW-X'
  at 0.0479); the label function on printed one-decimal values, arm by arm on gains (a gain the timing arm also shows FAILS `beats
  chance` while the levels would have passed it); the paired interval's resampling holds the map fixed; one end-to-end synthetic world
  (`--dry-run` → `--run`) that mimics the real shapes — era-A and era-B trades, an SPY gap, a 1-session window, a loser and a winner on one
  name, a bracket opening before 09:35 and one flat at 09:30, open-fill STOP rows (C-S1 MISSING) with ties at a cut, exit_lo_j = 1 (control
  (a) with 2 placements, widening clipped at offset 0), a next-session-booked firing on exit_hi with a no-minute session, a record with no
  stock bar on D, tag files in their real serialization (offsets as float strings '3.0', blank when still_held, 'True' / 'False'), objects
  freed and ids reused between stages; the module scans (D3, D4, guard 11), each with its `# source-pin-ok:`.
- **Outputs:** `01_ctx_dryrun.txt`, `01_ctx_run.txt`, `01_ctx_pins.txt`, `01_ctx_ledger.tsv` in `scripts/probes/_705_context_1026/`;
  per-trade files under `scripts/probes/_705_context_1026/out/` (`contexts.tsv`: eid, sym, E, decision, block, every context value and its
  missing flag;
  `maps.tsv`: per decision × tolerance × map the chosen tree; `groups.tsv`: eid → group and rule per map; `controls.tsv.gz`: per permutation
  and per control draw the chosen tree and its 2020 / 2021-22 scores).

**The expected output table, per decision and tolerance (the template the run fills):**

```
decision EXIT — tolerance ±1c (primary) — n 333 / 229 / 44; the chosen map: C-X? ≤ T? -> [ ... ] (3 groups); m 34
  line                  | 2020 (fit, in-sample)            | 2021-22 (scored as chosen) | untouched (sign) | label
  MAP                   |  ..% [..,..]                     |  ..% [..,..]               |  MAP − BEST + / 0 / − (n ..) |
  BEST (M-?)            |  ..%                             |  ..%                       |                   |
  MAP − BEST (paired)   |  .. [..,..]; McNemar .. / ..     |  .. [..,..]; McNemar .. / ..|                  |
  ORACLE-1              |  —                               |  ..% (M-?)                 |                   |
  SHUF mean             |  ..% (p95 ..%; MAP at pctile ..) |  ..% (p95 ..%)             |                   |
  MAP − SHUF (paired)   |  .. [..,..]                      |  .. [..,..]                |                   |
  (c-1) arm <a>         |  MAP ..% / BEST ..% -> net gain ..|  MAP ..% / BEST ..% -> net gain .. |      |   (one line per arm)
  (c-2) arm <a>         |  MAP ..% / BEST ..% -> net gain ..|  MAP ..% / BEST ..% -> net gain .. |      |   (one line per arm)
  (largest arm, layout only) | (c-1) ..% / (c-2) ..%       |  ..% / ..%                 |                   |
  UNION                 |  ..%; gap closed ..%             |  ..%; gap closed ..%       |                   |
  -> context helps: yes / no | beats chance (every arm's net gain ≥ 10.0): yes / no | SUMMARY: context map / context helps, chance too / no context gain
  groups: [C-X? ≤ T?] n 2020 .. / 2021-22 .. -> M-? ..% / ..% (dated .., EP ..; window width median .., exit_lo_j median ..) ...
  controls: clipped placements ..%; control (a) at s ≥ a_f .. | UNRESOLVED → CLOSE upgrades .. | missing per context ..
  beside: ±0 .. | ±1 symmetric .. | ±2 .. | MAP-T1 .. | HW-X .. | HW-X' (4.79%) .. | SW-a .. | SW-b .. | losers / non-losers ..
```

## 12. What this does not answer

- **Which rule he used where two match** — a map picks one rule per group; the UNION bounds the ambiguity, it does not resolve it.
- **His partials** — a rule he acted on with half the position reads as a miss when the half lies outside the side the booking convention
  can reach (FSLY 693: half on the 60-minute close 07-10, the last share 07-13 / 07-14 — one to two sessions later, the rule-mix's wording);
  every share is a floor.
- **Contexts not on the list** — news, the chart's look, his P&L, how much time he had, his position size: the discretion remainder holds
  them undifferentiated; a map with `no context gain` says only that THESE contexts do not pick the rule.
- **The per-session dynamics** beyond the 10/20 switch — a map whose group changes session by session (§13 Q2).
- **Whether a map is stable forward** — the forward shadow is the only out-of-sample read left; 2025-26 only in #710's one sealed run.
- **The side of a position, trades between two streams, his fund and ETF trades, his fills and sizes** — as before.

## 13. Design questions — Q1-Q4 DECIDED (main loop, 2026-10-26); Q5-Q7 applied as recommended, the main loop confirms before the freeze (none is THE LINE)

1. **ENTER's "close".** — **DECIDED (main loop 2026-10-26, as recommended):** primary = the level STRICTLY first crossed inside the bracket
   (the rule-mix EXPLAINS, identity-gated); B1 (a re-cross inside) and B2 (hit-or-ballpark) beside, labelled, never in the summary (§4b).
   Why: the instruction's "crossed inside his buy bracket or within the registered ballpark" equals hit-or-ballpark, which a random price
   meets 85.9% of the time — no map can pass under it.
2. **EXIT contexts static at D, or re-read at each held session's close?** — **DECIDED (main loop 2026-10-26, as recommended):** static, read
   once at D, before the buy — each group's rule stays ONE library rule and reuses the frozen buckets; the per-session reading enters only
   through the 10/20 switch (SW), beside. A general per-session map waits until a static map earns `context helps`.
3. **The full library or his words only for the primary map?** — **DECIDED (main loop 2026-10-26, as recommended):** the full library is
   primary (it describes him; it may fill a group with a tier-2 rule — 2020's best single EXIT rule at ±0 is M-8, our reading); MAP-T1, his
   words only, beside (what Apollo would rebuild from his words); both printed with the same labels.
4. **The 10/20 switch now, or wait for the shadow?** — **DECIDED (main loop 2026-10-26, as recommended):** registered now as SW-a / SW-b,
   beside, out of the summary label — cheap, identity-gated against M-3 / M-4 (G4), his exact words.
5. **The setup context, known at ±0 (review F1).** (a) take it out of the map search and keep it as the stratification printed beside
   (dated / EP counts per group), or (b) keep it in, mark every tree that splits on it "known at ±0" and bar such trees from the summary at
   ±0 and at ENTER's primary (which IS ±0). **Applied: (a)** — ENTER's primary is the rule-mix's own EXPLAINS, so under (b) every ENTER tree
   on the setup would be barred anyway, and a uniform rule is simpler to gate; the search becomes 4 / 6 / 7 candidate splits (101 / 295 /
   449 trees before the dedupe and the floor). The main loop confirms or flips before the freeze.
6. **C-E1 on brackets that open before 09:35 (review F2: 17 / 20 / 1).** (a) C-E1 MISSING when flat_clock < 09:35, or (b) clipped to the
   minutes strictly before min(09:35, flat_clock), as a per-minute rate ÷ (ADV20 ÷ 390). **Applied: (b)** — it keeps the context defined on
   all but the 09:30-flat brackets (MISSING 0 / 7 / 0), where (a) would send a fifth to a third of each block to the larger child; HW-E's
   median and G6 use the same clip. The main loop confirms or flips before the freeze.
7. **±1 on STOP / EXIT (review F9).** (a) the primary convention-aware ("±1c": same-session-booked firings [lo − 1, hi], next-session-booked
   [lo, hi + 1], per Fire by `jb > je`), the symmetric ±1 beside, or (b) keep the symmetric ±1 primary and rewrite its reason. **Applied:
   (a)** — the stated reason (the booking convention) moves a sale in one direction per firing, so the primary should not admit both; the
   controls take the same per-Fire window. The main loop confirms or flips before the freeze.

Pre-decided here (small forks, stated): C-E1 at five minutes (his branch point) rather than thirty, clipped at flat_clock (Q6); ADV20 as
C-E1's denominator; SPY's 50-day vs 10 sessions earlier (the registered reading) for the market, flagged our reading; the market contexts
FLAGGED rather than dropped (review F7: the method line l.2606 names the market as an example context; dropping them would give 49 / 181 /
295 trees with the setup also out); binary splits at the 2020 tertiles on the defined rows, identical partitions deduped; m = max(15, 10% of
n_2020); SHUF permutes 2021-22 too, not the untouched block; the 4.79% speed cut beside (HW-X'), not in the search; the 10-point margins of
the instruction kept for every label.

## 14. Revisions before the freeze

Each change before the freeze is one row (source, finding, change). Fix stage 2026-10-26 (no bar opened, no context computed, no bucket
column crossed with any context; read: the tag files' `flat_clock`, `fill_src`, `fill_minute`, `exit_lo_j` columns and the printout's
sub-block headers, population counts only).

| # | source | finding | change |
|---|---|---|---|
| 1 | main loop 2026-10-26 | §13 Q1 | DECIDED as recommended: ENTER close = strict first crossing inside the bracket; B1 / B2 beside |
| 2 | main loop 2026-10-26 | §13 Q2 | DECIDED as recommended: EXIT contexts read once at D, before the buy; SW beside |
| 3 | main loop 2026-10-26 | §13 Q3 | DECIDED as recommended: the full library primary; MAP-T1 (his words only) beside |
| 4 | main loop 2026-10-26 | §13 Q4 | DECIDED as recommended: SW-a / SW-b registered now, beside, out of the summary label |
| 5 | review F1 (high) | the setup context was already crossed with every rule's ±0 column on both blocks (the printout's dated / undated sub-blocks) | disclosed in the header, §1 4e, §7c; fork recorded as §13 Q5, (a) applied: the setup is out of the search on all three decisions, printed beside as the per-group stratification; C-E4 / C-S4 / C-X5 removed; no map score written |
| 6 | review F2 (high) | C-E1 read at 09:35 on 17 of 88 / 20 of 60 / 1 of 9 brackets that open earlier (verified from the clocks) | fork recorded as §13 Q6, (b) applied: C-E1 = per-minute rate over the minutes strictly before min(09:35, flat_clock) ÷ (ADV20 ÷ 390), MISSING on a 09:30 flat (0 / 7 / 0); G6 truncates per trade; §7d case added; §3d expectation corrected; HW-E uses the clip |
| 7 | review F3 (high) | `beats chance` tested levels against the largest arm, which BEST already clears on ENTER / STOP (verified: L1 21.0% / 31.3% at l.59 / l.155; S1-T 40.4% / 41.7% at l.289 / l.366) | redefined on gains, arm by arm, for (c-1) and (c-2) (§7a); every arm prints for MAP and BEST in the §11 template; (c-2) per arm too, for the same reason |
| 8 | review F4 (medium) | the checker exited 1 (no n-equals and no n header cell) | §2 header cell renamed `n`; the "(dated + undated)" meaning moved to a bullet; checker exits 0 |
| 9 | review F5 (medium) + recount F2 (low) | module and output paths outside the write scope (`_705_context_rules_1026`, `apollo_data/.../context_rules/`) | every path moved to `scripts/probes/_705_context_1026/` and its `out/` (§11 Code, Outputs) |
| 10 | review F6 (medium) | misjoined contexts (false negative) and a wrong calendar / off-by-one (G6 replays it) missing from §7d; "no stock bar at D" not MISSING | both cases added to §7d; `contexts.tsv` carries eid + sym + E and a join test; G6 asserts by date; D defined as the calendar's predecessor of E; "no stock bar dated D" added to §3d; synthetic world gets that record |
| 11 | review F7 (medium) | the market context has no anchor in his entry / stop words; C-E1 / C-X5 / l.1735-1736 cites overstate | C-E3 / C-S3 / C-X4 flagged "our reading" (flag, not drop — the method line l.2606 names the market; recorded in §13's pre-decided line); C-E1 "his EP words, transferred"; the setup binary "our binary reading"; l.1735-1736 "the notes' summary"; ENTER's speed exclusion reworded |
| 12 | review F8 (medium) | the exits study's fast vs slow read (4.79%) undisclosed; Apollo runs that cut | disclosed in the header, §1 4e, §7c; HW-X' at 0.0479 added beside (§5e); the cut NOT added to the search |
| 13 | review F9 (medium) | symmetric ±1 justified by a one-sided reason | fork recorded as §13 Q7, (a) applied: primary ±1c per Fire (`jb > je`; an R2 Fire by its outer Fire), controls widened the same way, symmetric ±1 beside with ±0 / ±2; G3 extended; §9 guesses for STOP / EXIT re-stated at ±1c |
| 14 | review F10 (medium) | C-S1 undefined on open fills (look-ahead inside the fill minute), tertiles collapse | C-S1 from minutes strictly before the fill minute, MISSING on open fills (91 / 76 / 8 STOP losers); tertiles on defined rows; identical 2020 partitions deduped before counting; the dry run prints every candidate's child sizes; the his-cap cut's likely death under the floor stated (about 18 or fewer: the runner's flag may include the fill minute); coupling to S1-T flagged in §1 4c |
| 15 | review F11 (medium) | binding test lessons not in the plan; synthetic world missing real shapes | §11 Tests: fixture copy of the doc under `tests/fixtures/`, no '/Users/' (scan), `# source-pin-ok:` on each module scan, G1's parse (`int(float(x))`, blank → None, 'True' / 'False'); every listed shape added to the synthetic world |
| 16 | review F12 (low) | clipping at offset 0 biases control (a) down; "UNRESOLVED never upgrades" is false in one case | clipped share and an s ≥ a_f control variant print beside; verified against the frozen `bucket` (a next-session-booked firing whose event is on a missing exit_hi): the claim reworded, the case pinned by a test and counted, never overridden |
| 17 | review F13 (low) | §13 OPEN, §0 "four forks" | §13 Q1-Q4 DECIDED, §0 updated |
| 18 | review F14 (low) | the untouched sign check subtracted a SHUF never defined there | SHUF term dropped from the sign check (MAP − BEST only), stated in §6b and §7a |
| 19 | review F15 (low) | C-E1's minute volume may differ by minute tree | the dry run prints C-E1 per minute tree and the minute ÷ export buy-day volume ratio (§10), before the freeze |
| 20 | review F16 (low) | only MAP's interval printed, the label is a paired difference | paired bootstrap interval and McNemar counts beside MAP − BEST and MAP − SHUF (§5d, the template) |
| 21 | recount F1 (low) | FSLY's "two-session lag" contradicts the doc's own offsets (half on +8 = exit_lo − 1; M-1's first firing +0) | the FSLY parenthetical dropped from §4a; §12 restored to the rule-mix's "one to two sessions" |
| 22 | recount NOTEs | G1 listed `first_j` / `booked_j` for ENTER; §2 cited the rule-mix's §4b for "losing"; §1g "one SE"; §1h base unnamed | G1 lists each file's real columns; §2 cites §4d / §11 Q5; §1g states 1.5 SE of one share and points to the paired interval; §1h names the non-flicker base |
| 23 | check F1-F14 (2026-10-26; test strength, no registered value wrong) | the fixture's location stated wrongly; each split's missing side not pinned; the close-proxy bound hard-coded at 16:00 (an early close ends 13:00; no real close-proxy row falls on one); the dry run parsed the bucket columns before subsetting; the gates G2-G6 never shown to stop a run | §11 Tests names `scripts/probes/_705_context_1026/fixtures/`; §11 guard (1) pins each split's missing side (`ctx_const_<decision>_<context>_<cut>_missing_left`, re-derived by D2); C-S1's close-proxy bound = the session's own close; the tag files read with `usecols` = the label columns (`loser_lo` dropped: never used); tests added per finding |

<!-- FREEZE -->
## Freeze record

Empty until the freeze. The main loop decides §13, applies the review and recount as rows of §14, freezes this doc and the module
(`doc_body` pinned), runs `--dry-run` (the populations, the contexts' missing counts, the tertile cuts, the HW medians and the tree order
printed; no outcome), runs `--pins`, pastes every pin below (the rule-mix pins carried, plus the rule-mix tag printout, recount and per-trade
files, the frozen rule-mix module, this module and its tests, the dry run, the ledger, `doc_body`), copies the module beside the pins, and
runs `--run` once. Nothing is written above the marker after the freeze. Any edit above the marker after that changes `doc_body`, and `--run`
refuses.

### Pins

