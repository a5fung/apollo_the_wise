# #711 — step 7: his trades grouped by what the chart shows, by confidence tier — registration (2026-10-27)

**Status: REGISTERED, NOT FROZEN, NOT RUN.** The step-7 document the frozen steps-5/6 registration
(`cb_asis_reconstruction_prereg_2026-10-26.md`, §5: *"registered in its own document after step 6 reports"*) called for. His words
that set it (2026-10-26): *"stop trying to pigeon hole his trades, we're starting without any preconceptions, I want to reverse eng
his trades as they are, not as we want them to be and fit into our rules, that reconciliation comes later"*; and his decision of
2026-10-27 ("Go"): *"sort out which trades we're confident are correct and which we aren't, then we can run next step with these
distinctions ... if we have a decent number of trades we're confident about we should be able to deduce his rough trading rules, as long
as we have sufficient sample. The ones we're not confident we can decide what to do, if we include and if so what its effects are, the
worse case is we include trades that aren't correct and deduce the wrong rules."*

**Where step 6 left it:** on windows v2 (gap-filling limited to single-frame misses, his Ok to option A), R1 (his spoken prices inside
our range) is NOT DECIDABLE — 11 clean priced fills against a floor of 100 (it would read PASS: 72.7% inside vs 47.0% on a shifted
window, 5.1% on another stock); R5 (the action agreeing with the window's side) 48 of 66 = 72.7% against a bar of 90%, the misses
being the panel's blind spots (same-day round trips, trades never on the panel, talk about another day) rather than wrong windows
(`fork/r5_miss_diagnosis.md`). So the per-trade check cannot grade trades one by one; **confidence comes from the screen facts
themselves** — how tightly the panel brackets each side — and his words confirm a few.

**What this read does NOT use:** our rule library (every setup name, level, the L1..L9 / M-1..M-12 rules of the earlier reads); any
trade outcome (return, R, gain, win / loss — §3.5); the candidate families' tags and directions (held out, as the frozen §3.3 / §5
require). **Guards:** no paid model call, no network, no production server, nothing dated after 2024-12-31 (the 2025-26 data is sealed
for #710), none of the seven outcome folders opened, nothing imported from the rule folders. Nothing here changes or proposes to change
a strategy, entry, stop, exit, size, safeguard or live trade state (THE LINE).

## 0. In plain words

- **The tiers, from the screen alone, before any trade's result was looked at:** HIGH 398 / MEDIUM 279 / ONE-STREAM 510 / LOW 401 of his
  1,588 positions (bought January 2020 to June 2022) — the counts he approved, reproduced exactly (§2); 53 are confirmed by his own words.
- **What each tier over-represents:** HIGH = holds of one to five sessions with minute bars; MEDIUM = the longer holds; ONE-STREAM = the
  same-day and overnight trades; LOW = missing bars (two in five) and long holds. ⚠ **The confident set (HIGH + MEDIUM) holds no same-day
  round trip** — any exit pattern it shows is a trade held at least overnight; same-day exits enter only when ONE-STREAM is added (§2.3).
- **What step 7 produces:** three to six groups in plain chart words with their shares, on the confident 677 first, then with each
  less-confident tier added and the count of confident trades that change group (his "what its effects are"); the exit side is read with
  every return-shaped measure removed (§3.3), and the entry-only grouping is the outcome-free reference beside the joint one (§3.5).
- **Two departures from the frozen steps-5/6 text, his to approve:** the 53 confirmed trades are read against the groups rather than
  grouped on their own (too few to fit; 47 have features — 33 sit in the confident set's own fit, 14 are placed in its nearest group — a
  coverage check of which groups his words touch, not a held-out test; §2.4), and the primary run uses no length our old rules used (the
  frozen order; "with our lengths" is the check run — §5). Cost $0, ~420k tokens of capacity, ~35 minutes of his time (§8).
- **Action from him now:** read §2 (the tiers) and §5 (the runs), say go — then this document freezes, the tier file is written, and the
  grouping is built and run.

## 1. The four questions of the standard

1. **Decision served:** whether the confident trades are enough to show what his trades have in common on the chart, and whether
   adding the less-confident ones changes that picture (his question: *"if we include and if so what its effects are"*). It changes
   nothing live and no branch of the sealed 2025-26 test.
2. **What would change it:** the primary run finding no stable grouping (§4.3: no number of groups reaches the stability line) — then the
   trades are described as one population with distributions, not groups, and the question goes back to him; the confirmed trades
   landing in groups that the primary run never formed (§5: the 53 against the groups); a tier count differing from the approved one
   (§2.2 — the dry run's claims; it did not).
3. **Population:** §2.1 — the 1,588 positions whose BUY window ends in 2020-01-01..2022-06-30 on windows v2 (`ranges.tsv`, step 5
   re-run 2); 1,585 of them also have their sale window in span, the 3 others are kept (the position is in span by its buy).
4. **Limits:** §9.

## 2. The tiers — locked from screen facts, before any outcome was read

**Population:** every row of `asis_1026/ranges.tsv` (step 5, re-run 2 on windows v2) whose side is `buy` and `in_span` is true —
the buy window's end in 2020-01-01..2022-06-30 — joined to its `sale` row and to `windows_v2/entries_v2.tsv` (the panel's `flicker`,
`n_streams`, `n_sightings`); n = 1,588 positions, all with a sale row. Nothing after 2024-12-31 is read from any file.

### 2.1 The definitions (approved 2026-10-27; `05_tiers.py::tier_of`)

| tier | definition (screen facts only) | n |
|---|---|---|
| **HIGH** | buy AND sale side each in a bracket of at most one session (`same_in_in`, `same_pre_in`, `next_in_pre`, `next_in_in`), resolution minute on both, not inverted, seen on 2+ streams (not a flicker) | n = 398 |
| **MEDIUM** | both sides within 2-5 sessions or better (the four brackets above or `sessions_2_5`), any resolution WITH a reachable range on both sides, not inverted, seen on 2+ streams (not a flicker) | n = 279 |
| **ONE-STREAM** | flickers — the panel's own flag: seen on one stream only AND gone within 5 sessions — whose two sides would otherwise read MEDIUM or better; a real quick trade or a misread ticker, the file cannot tell which | n = 510 |
| **LOW** | the rest: a wide window (6+ sessions) on either side (153), a side with no reachable range because no bars exist (153), a `bracket_other` side — the two clocks give no narrower rule than the full session (64), an inverted window — extended hours (31) | n = 401 |

The approved wording, verbatim (the module carries it as `TIERS_TEXT` and the dry run prints it):
- HIGH = buy AND sale side each in a bracket of at most one session (same_in_in, same_pre_in, next_in_pre, next_in_in), resolution minute, not inverted, seen on 2+ streams (not a flicker)
- MEDIUM = both sides within 2-5 sessions or better, any resolution with a range, seen on 2+ streams
- ONE-STREAM = flickers (seen on one stream only): a real quick trade or a misread ticker
- LOW = the rest (wide windows, missing data, inverted)

The order is fixed: a side that is wide, rangeless, inverted or `other` reads LOW whatever the stream count; a flicker never reads
HIGH or MEDIUM. **CONFIRMED-BY-HIS-WORDS is a sub-flag, not a tier** (§2.4).

### 2.2 The counts, re-derived — and the one fork, disclosed

The dry run (`05_tiers_dryrun.txt`, 21 claims, 21 OK, 0 MISMATCH) reproduces the approved counts exactly: 398 / 279 / 510 / 401,
summing to 1,588. **One reading had to be fixed:** "seen on 2+ streams" is implemented as the panel's `flicker` flag being false
(`flicker` = seen on one stream AND gone within 5 sessions). The literal reading `n_streams >= 2` differs on 3 positions — seen on one
stream but held LONGER than 5 sessions, both windows within 5 sessions with a range (UVXY 2021, KWEB 2021, BOIL 2022): they are
MEDIUM under the flicker reading (279 / 510) and would be ONE-STREAM under the literal one (276 / 513). The flicker reading is locked
because it is the reading the approved text names ("not a flicker") and the one the approved counts came from; the 3 carry
`single_stream_nonflicker = True` in `tiers.tsv` and are printed by eid. The 50 other single-stream non-flickers are LOW on their
own facts. **A second reading, also disclosed:** "within 2-5 sessions or better" is implemented as the four named brackets or
`sessions_2_5`; a `bracket_other` side (`next_other` / `same_other` — one or two sessions wide, but the two clocks give no narrower rule
than the full sessions) is neither and reads LOW (64 positions, `tier_reason = bracket_other`). Read literally by session count they
would be MEDIUM or ONE-STREAM; the approved 401 came from the bracket reading and it is kept. **A third reading, in the same place:**
the approved text says "ONE-STREAM = flickers", but the tier order reads a flicker's SIDES first — 130 flickers whose sides are wide (28),
rangeless (73), inverted (22) or `bracket_other` (7) read LOW, and ONE-STREAM is the 510 flickers whose sides would otherwise read MEDIUM
or better (the definition table says so; the approved 510 embeds it; a dry-run claim pins the 130). No tier boundary was moved after seeing
any count's effect on anything.

### 2.3 Composition — what each tier over- or under-represents (screen facts only; `05_tiers_dryrun.txt`)

| facet | HIGH (n = 398) | MEDIUM (n = 279) | ONE-STREAM (n = 510) | LOW (n = 401) |
|---|---|---|---|---|
| hold length, sessions (max) | 1: 22% · 2-5: 44% · 6-20: 29% · 21+: 6% | 1: 1% · 2-5: 34% · 6-20: 55% · 21+: 10% | 0: 43% · 1: 32% · 2-5: 23% · 6-20: 2% | 0: 10% · 1: 7% · 2-5: 20% · 6-20: 52% · 21+: 11% |
| year of the buy | 2020 52% · 2021 44% · 2022 4% | 50% · 37% · 13% | 51% · 37% · 11% | 57% · 35% · 7% |
| bracket pair (buy/sale) | tight/tight 100% | tight/near 48% · near/tight 34% · near/near 14% · tight/tight 4% | tight/tight 70% · tight/near 14% · near/tight 13% | spread over 24 pairs; wide on a side 44% (153 = 38% read LOW for that reason, the rest for inverted or no range first); other on a side 22%; inverted 8% |
| minute bars on both sides | 100% | 91% (one side 8%, none 1%) | 96% | 16% (one side 37%, none 48%) |
| average traded price, buy side (minute-resolved sides) | <$5 6% · $5-20 15% · $20-100 45% · $100+ 34% | 8% · 16% · 47% · 24% · daily-only side (no minute price) 5% | 7% · 19% · 45% · 27% · daily-only 1% | 3% · 5% · 16% · 10% · daily-only 21% · **no bars 38%** · no range (inverted) 6% |
| same-day round trips (hold 0) / one-session holds | **0** / 87 (22%) | **0** / 2 (1%) | 220 (43%) / 164 (32%) | 39 (10%) / 27 (7%) |
| exit-side look-backs defined (§3.3 rule) | none 24% · prior session only 28% · up to 3-5 sessions 26% · longer 22% | none 12% · 30% · 31% · 27% | none 57% · all (same-session) 43% | none 43% · the rest spread |
| streams seen on | 2: 35% · 3-5: 33% · 6+: 32% | 1: 1% · 2: 24% · 3-5: 37% · 6+: 38% | 1: 100% | 1: 45% · 2: 15% · 3-5: 22% · 6+: 19% |
| pre-market possible (buy side) | 39% | 29% | 38% | 41% |
| confirmed by his words | 18 (4.5%) | 15 (5.4%) | 4 (0.8%) | 16 (4.0%) |

Read: **HIGH over-represents the short holds he closed within a week and 2020-21; MEDIUM is the longer holds** (a tight bracket on one
side and a 2-5-session window on the other is what a multi-week hold looks like when he streams most mornings); **ONE-STREAM is the
day trades and overnight trades** (three in four gone within one session) — a group that forms only when ONE-STREAM is added is either
his quick-trade behaviour or misread tickers, and the captions, not the chart, decide which; **LOW is where the bars are missing**
(two in five have no bars on the buy side — delisted names, funds and notes, extended hours; another one in five is a daily-only side with
no minute price) and the long holds whose window the panel could not bracket. The four "minute, no price" sides (one MEDIUM, two
ONE-STREAM, one LOW) are minute-resolved windows whose reachable minutes hold no bar (`no_minute_bar_in_reach` / `bar_holes`), a step-5
artefact carried as is. 2022 is thin in every tier (the captions and the streams thin out after mid-2021).

**The confident set holds no same-day trade — by construction.** "Seen on 2+ streams" needs the position to be held into a second
stream, so the confidence criterion is tied to hold length: all 259 same-session round trips are ONE-STREAM (220) or LOW (39), and
HIGH + MEDIUM has none (and only 89 one-session holds). Any exit pattern the primary run shows describes a trade held at least overnight;
the + ONE-STREAM run is where same-day exits enter, and §4.1 maps their hold length (below the primary's minimum) by extrapolation, not
by clipping.

### 2.4 The confirmed sub-flag (`confirmed`, from 6b's `check_r1_r5.tsv`)

| flag | meaning | positions |
|---|---|---|
| `confirmed_r5` | a statement of his, joined uniquely by symbol and day (never by action), whose action agreed with the side of the window it landed on | n = 46 |
| `confirmed_r1` | a stated FILL price (`fill == 'fill'`; a stop LEVEL — "my stop is 40" — never confirms a fill) inside the side's reachable range, any day class | n = 19 (of which the R1 primary line: 8) |
| `confirmed` | either | n = 53 (overlap 12): HIGH 18, MEDIUM 15, ONE-STREAM 4, LOW 16 |
| `confirmed`, assignable | a reachable range on both sides, so the §3.3 features exist and the trade can be placed in a group | n = 47 of 53 (9 of them daily-only on a side; the 6 others have no bars on a side — `no_range`): 33 are HIGH / MEDIUM rows of the primary fit itself, 14 (ONE-STREAM 4, LOW 10) lie outside it |

53 of 1,588 (3.3%) — enough to read AGAINST the groups (§5), not enough to group on their own. They are the trades he chose to talk
about (morning-heavy; the frozen §4.1 step 7). **A departure from the frozen §5, for his approval (§0):** it asked for the anchored and
unanchored trades to be grouped SEPARATELY; at 53 (47 with features) a separate fit cannot reach the §4.5 minimum. So the confirmed
trades stay ordinary rows of whatever run their tier puts them in (33 of the 47 are HIGH / MEDIUM and are fitted with the primary), the
14 outside the primary are placed in its nearest group by centroid, and the CONFIRMED read reports where all 47 land against the
primary's shares — **a coverage check of which groups his words touch, not a held-out test** (§5).

## 3. What step 7 groups

### 3.1 Unit of analysis

One row per position: the ENTRY side's chart measures, the EXIT side's chart measures, and the hold length — a trade. The primary
grouping is on the joint row (his "trading rules" are entry AND exit); the entry-only and exit-only groupings are run beside and
reported, because an entry behaviour can pair with several exit behaviours and the joint groups should be readable as such.

### 3.2 The reference minute of a side — OUR convention, stated once

A window gives a band of minutes, not a fill. Each side is described at its **middle minute**: for a minute-resolved side, the minute at
which the cumulative volume over the reachable minutes crosses half of the total (the volume-median minute — the minute a trade placed
somewhere in those minutes most likely sits in; the same logic as 6c's volume-weighted middle price, which the frozen §4.3 chose because
it does not carry the choice of point families); for a daily-only side, the reachable session with the largest volume, described at its
typical price (high + low + close) / 3 with the minute blank and `daily_only` flagged. Not the candidate points: averaging the §3.4
features over the candidates would weight them by family density (round numbers dominate), the hazard the frozen §4.3 named. The band's
width (`range_width_pct`) is NOT a feature — it is uncertainty, not behaviour — and is reported per group as a descriptor, with a
sensitivity run (§5, "edges") that describes every side at its band's low end and at its high end instead.

### 3.3 The features — continuous chart measures only (the frozen §3.4 columns, recomputed at the middle minute), registered as code

The lists live in `05_tiers.py::STEP7_FEATURES` (pinned under this marker; `06_groups.py` imports them and may not widen them; the dry run
prints the counts and a test holds the rules). Lengths: `dist_hi_N` / `dist_lo_N` and `ret_N` for N = 3, 5, 10, 20, 40, 60; `dist_ma_N`
for N = 5, 8, 10, 13, 20, 30, 50; `sessions_since_hi_N` for N = 5, 20, 60; and — new here, computed the same way as the frozen column
they generalize — `range_vs_avgrange_N`, `vol_day_vs_N`, `vol_sofar_vs_N` for N = 5, 10, 20, 40, 60 (the frozen §3.4 had these three
ratios at 20 only — `range_vs_avgrange20`, `vol_day_vs_20`, `vol_sofar_vs_20` — with no sweep to stand in their place; the 20 column
keeps its meaning under the swept name). **The `our_length` columns** (the frozen §3.4 flag: the 20-session range and
volume, the 10- and 20-day price averages, the 20- and 60-session highs and lows, the 20-session since-high; 10 is NOT ours for a range or
volume average — the frozen flag on 10 is the price moving average) are **held out of the primary run** and of every tier-adding run,
with the sweep in their place — the frozen l.221-223 / l.587 order (*"held out of step 7's features and read with and without"*); the
run WITH them is the sensitivity run (§5).

**Entry side (40 columns in the primary; 50 with `our_length`):** the day's own measures — `pos_in_day` (where the middle price sits in
the day's full range), `minute` (time of day; the session's midpoint when daily-only, flagged), `gap_pct`, `range_pct`, the range and
volume ratios; the look-backs — `dist_prev_high`, `dist_prev_low`, `dist_prev_close`, `dist_hi_N`, `dist_lo_N`, `dist_ma_N`,
`sessions_since_hi_N`; and the run-up before the entry, `ret_N`. Every look-back on the entry side ends before the entry.

**Exit side (34 / 44 columns) — the result kept out (review F1):** at the exit, a look-back over the prior N sessions reaches back
ACROSS the entry whenever N is at or above the hold, and `ret_N` is then the stock's close-to-close move from just before the entry to
just before the exit — the trade's return under another name; `dist_hi_N` / `dist_lo_N` / `dist_ma_N` / `sessions_since_hi_N` carry the
same path more weakly. So: **(a) the exit side carries no `ret_N` at all**; **(b) an exit-side look-back of length N is defined only when
N < `hold_sessions_min`** (the prior N sessions then end before the entry day; `hold_sessions_min` is the test because N below it is
below the true hold) **or the trade is a same-session round trip** (`hold_sessions_max` = 0: every prior session precedes the entry) —
otherwise it is a STRUCTURAL blank (§3.4), counted, never filled from the bars (`exit_lookbacks_defined`); `dist_prev_close` on a hold of
one session is blank by the same rule (the prior close is the entry day's close, after the fill); **(c) the exit day's own measures stay** —
`pos_in_day`, `minute`, `gap_pct`, `range_pct`, and the range and volume ratios, which are kept even when their averaging window crosses
the entry because a ratio of ranges or of volumes has no sign and cannot give the direction of the move since entry. Trade-level:
`hold_sessions_max`. The feature set is therefore hold-dependent by construction — in the primary, 128 positions (19%) have no exit
look-back at all (hold_sessions_min of 0 or 1), 196 (29%) the prior session only, the rest up to 3-5 sessions or longer; the dry run prints
the table per tier — and §3.4 / §4.6 say how that is kept from forming groups on its own.

**Held out, by the frozen §3.3 / §5:** the candidate family and direction tags; `dist_round` and `dist_vwap` (point-level, tied to a
family); `pos_in_day_so_far` and `vol_min_vs_median` (minute-level noise at a convention minute); the band width; every outcome (§3.5).
"Base length" is not a feature by that name (a rule-shaped word); `sessions_since_hi_N` and the range ratios carry what a plain chart
shows of it.

**Daily-only sides in the same groups (the frozen §5's open question, answered now):** a side with no minute bars is described at
its largest-volume session with the minute blank; in the primary run these are 24 of 677 rows (MEDIUM: 22 with one side daily-only,
2 with both — a dry-run claim), so they cannot form a group of their own at the §4.5 minimum. They sit in the same fit; their distribution
over the groups is printed, and a concentration of them in one group is reported as a feature artefact (the blank minute, the typical
price), not a behaviour. In the + LOW run (147 one-side, 191 none) the same readout is printed and a group that is mostly daily-only is flagged.

### 3.4 Missing values

Two kinds, kept apart. **Data blanks** — a side with a short history (`short_history`, fewer than 60 prior sessions) has blank
long-length columns; a row with more than a quarter of its NON-structural features blank is dropped from the fit and listed. **Structural
blanks** — the exit look-backs the §3.3 rule leaves undefined — never count toward that quarter (they would evict most of the primary:
every one-session hold has all of them blank). Both kinds are filled with zero after standardization (the run's median under the
rank-normal map — the stated convention) and counted; the dry run prints, per run and per group, the share of rows under each structural
blank pattern. A group in which 80% or more of the rows carry one structural pattern is flagged "structural" and its exit description is
read on the day-own columns only (§4.6) — the hold length is itself a feature, so a group that IS the one-session holds is legitimate, but
its exit look-backs say nothing.

### 3.5 Why outcomes are excluded — and the mechanical guard

A group formed with the return inside it is a winners / losers split, not a behaviour; a tier chosen with any outcome in view would
make the confident set the lucky set. So no return, R, gain, win / loss or "worked" is read, computed or printed anywhere in step 7.
**One input does carry outcome-shaped columns:** 6b's `check_r1_r5.tsv` has his stated dollar result (20 rows) and a `stopped` action
(39 rows); `05_tiers.py` loads that file with `usecols` limited to six columns (`eid`, `r5_agree`, `inside`, `fill`, `primary`,
`join_status`), so neither is ever in memory, and a dry-run claim and a test hold the loaded columns to exactly those six.
`forbidden_outcomes.txt` — result_pct, result_in_day_ranges, pnl, gain, winner, loser, worked, and the names 04_band and 03_check use for
outcomes (dollar_result, ret_middle, ret_worst, ret_best, ret_anchored, daily_middle, stopped_out) — is scanned against the step-7 modules with the
frozen §3.1 names (a whole identifier or whole string literal fails the run and the test). Outcomes enter after step 8, when a group has
a name, as a description of the named groups — never before.

**What the guard cannot remove, said plainly:** an exit description is a description of where on the chart he sold, and that is after
the entry — so the joint grouping still carries the price path after entry in the exit day's own measures (a sale near the day's low on a
gap down is part of the path). What §3.3 removes is every measure that encodes the ENTRY-to-exit move. The entry-only grouping (§5) is the
outcome-free reference and is reported beside the joint one; his exit behaviour cannot be described without the path, and the report says
so where it reads an exit.

## 4. The grouping method — stated now, no choice left to after the groups are seen

1. **Standardize:** each feature is mapped to its rank-normal score (van der Waerden) over the run's rows, so a 300% gap does not own the
   distance; the primary run's maps are FROZEN and applied to every other run, so all runs share one space. **A value outside the
   primary's range is never clipped:** the map is piecewise-linear through the primary's (value, score) knots and continues the slope of
   the outermost pair of knots beyond either end (a same-day hold of 0 sessions, below the primary's minimum of 1, scores below the
   primary's lowest hold, not equal to it); the number of extrapolated values per feature and per run is printed. The reduction (2) stays
   fitted on the primary. **A run whose COLUMNS differ from the primary's** (with `our_length` — 20 columns the primary never mapped;
   entry-only / exit-only — subsets whose reduction cannot be the primary's) **fits its own rank-normal maps and its own reduction on its
   own 677 rows**, with the same prints; it is compared in mode B (§5), never in the primary's space.
2. **Reduce:** principal components of the standardized features to 90% of the variance, whitened; fitted on the primary run and
   applied to the others (the number of components printed). The sweep lengths are collinear by construction (`dist_hi_3..60`); without
   this a block of six near-copies would own the distance.
3. **Cluster:** k-means (20 seeded starts, `rng_for("step7_<run>_k<k>")`, the best inertia) for k = 2..8.
4. **The number of groups — chosen again in EVERY run by this rule, never fixed at the primary's k:** prediction strength (Tibshirani & Walther 2005): for each k, 50 seeded random halves; fit on half A, assign
   half B to A's nearest centroid; the strength is the smallest, over B's own clusters, of the share of pairs in that cluster that A's
   centroids also put together; averaged over the 50 halves. **k = the LARGEST k whose mean strength is ≥ 0.80** (the paper's suggested
   line) **and whose full-data fit has every group ≥ the minimum size (§4.5).** None at k ≥ 2 → "no stable grouping": the trades are
   described as one population (distributions of each feature) and §1.2 applies. Every k's strength is printed, so a near miss is visible.
5. **Minimum size per group:** 30 trades or 5% of the run's n, whichever is larger (34 for the primary). A k whose fit has a smaller group
   is skipped, not merged.
6. **A group's description:** its share; the five features whose group mean is farthest from the run's mean in standardized units, with
   the sign and the raw median in chart words from a FIXED phrase table written before the run (e.g. `dist_hi_20` within ±1% → "at the
   one-month high"; `minute` < 30 → "in the first half hour"; `vol_day_vs_20` > 2 → "on twice the usual volume"; `ret_10` > 15% → "after a
   two-week run"); the tier mix; the band width (median `range_width_pct` per side); three example positions drawn with
   `rng_for("step7_examples_<run>_<group>")` (eid, symbol, dates — for him to pull up, never read by us for the description); and the
   share of its rows under each structural blank pattern (§3.4) with the "structural" flag when one pattern holds 80% or more — the exit
   description of such a group is then read on the day-own columns only.

## 5. The runs and the stability measure

| run | rows | features | what it answers | n |
|---|---|---|---|---|
| **primary** | HIGH + MEDIUM | §3.3 without the `our_length` columns (the sweep in their place) | the groups among the trades we are confident about | n = 677 |
| + ONE-STREAM | HIGH + MEDIUM + ONE-STREAM | the same | does the quick-trade / misread tier move the confident groups, or add its own (same-day exits enter here) | n = 1,187 |
| + LOW | all four tiers | the same | does the missing-data tier move them (its rangeless 153 drop at §3.4; printed) | n = 1,588 |
| CONFIRMED | the confirmed trades with features | the same | where his words land: the 33 primary rows by their fitted group, the 14 others by the nearest primary centroid; their shares against the primary's — coverage, not a held-out test | n = 47 of 53 |
| primary, with `our_length` | HIGH + MEDIUM with the ° columns added | §3.3 full | whether the groups change when our old lengths are on offer (the sensitivity run; the primary stays the no-`our_length` one whatever it shows) | n = 677 |
| primary, edges | HIGH + MEDIUM described at the band's low end, then at its high end | the same columns, other values | whether the middle-minute convention makes the groups | n = 677 |
| 2020 / 2021-22 | HIGH + MEDIUM split by the buy year | the same | the frozen §7's stability read (both already seen; not a holdout) | n = 347 / 330 |
| entry-only / exit-only | HIGH + MEDIUM, one side's features | one side | the outcome-free reference (entry-only, §3.5) and the readable exit behaviours behind the joint groups | n = 677 |

**The stability measure, between the primary and each other run — two modes, by whether the feature set is the same:**

- **Mode A, centroid-matched (same columns, so the frozen maps and the primary's reduction give one shared space: + ONE-STREAM, + LOW,
  CONFIRMED, edges, 2020 / 2021-22):** k is chosen again in the other run (§4.4); its groups are matched to the primary's by the Hungarian
  assignment on centroid distance in the shared space; **a primary group left unmatched when k differs counts every one of its trades as
  changed.**
- **Mode B, partition-based (other columns, no shared space: with `our_length`, entry-only, exit-only):** the two partitions of the
  primary's 677 trades are compared on their row contingency table — the Hungarian assignment on it gives the share of trades that change
  group, and the adjusted Rand index is printed beside.
- **The noise floor, printed beside every comparison:** the primary against itself under 5 seeded k-means refits (other starts, same rows)
  and 5 bootstrap refits (fit on a resample, every one of the 677 assigned) — the share of trades moved in each; **the 10% / 25% lines
  below are read as EXCESS over the larger of the two floors**, so a floor that is itself 12% cannot make an added tier read as "bending".
- **(b) the share of PRIMARY trades whose group changes** under the matching; **(c) description survival, on feature FAMILIES**, the sweep
  lengths collapsed (13 families: position in day, minute, gap, range, range ratio, distance from the prior session, from recent highs, from
  recent lows, from averages, run-up, volume, sessions since the high, hold) — a group's description survives when the same five families
  carry its five largest standardized means with the same signs, measured against the primary's FROZEN means (never the other run's), AND
  the Spearman correlation of its standardized-mean profile over the common columns with the primary group's is ≥ 0.8 (0.5-0.8 = partial;
  below = lost; a swap of `dist_hi_10` for `dist_hi_20` within a family is not a change); **(d) a new group** = any group of the other run
  whose matched centroid is farther than the primary's median inter-centroid distance (mode A) or whose rows are ≥ 60% from the added tier
  (either mode), described on its own — with its structural blank pattern read first (§3.4): a group that forms on the blank pattern alone,
  and not on the entry side or the exit day's own columns, is an artefact, not a behaviour.

**What each outcome means (decided now):**

| reading | meaning | consequence |
|---|---|---|
| ≤ 10% of primary trades move (over the floor) and every description survives | the added tier does not change the picture | the tier is INCLUDED in step 8's shares; its trades carry their tier label |
| 10-25% move, or one description partial | the tier bends the groups | both pictures are reported; which to carry to step 8 is his call |
| > 25% move, a description lost, or a new group that is not an artefact | the tier carries a different behaviour (quick trades) or noise (misreads) | the new / changed groups are described; he decides whether the tier is included, and the captions (not the chart) are the next check on ONE-STREAM |
| a new group that is structural (≥ 80% one blank pattern, nothing on the entry side or the exit day's own columns) | the feature set's hold-dependence, not him | reported as an artefact; the tier's inclusion is judged on the moved share alone |
| with `our_length`: another k or a lost description | the groups lean on our old lengths when offered | reported as a finding about the lengths; the primary (no `our_length`) is the picture carried — decided here, not after |
| CONFIRMED shares differ from the primary's by more than 15 points in any group, or a primary group holds no confirmed trade | the groups are not evenly checked by his words | the unchecked groups are flagged "unchecked by his words" in the report; nothing is dropped |
| no stable grouping on the primary | the confident trades do not separate into groups at this resolution | described as one population; his call whether to run on + ONE-STREAM (more trades) or stop |

## 6. What he gets, and his decision after step 7

A one-screen report per run: the groups with their shares, the plain-words chart description of each, the tier mix, the band width,
three example positions, and the stability table (how many confident trades moved, which descriptions survived, any new group). Then
**his decision:** accept the groups, merge or split them (by name, in chart words) — after which step 8 (the frozen §6) lays his stated
rules (`operator_shared_notes.md` l.1941-2096) and our library over the groups as LABELS: matched / flexed / broken / no rule.

## 7. Expectations, written now (scored at the report; a miss changes nothing by itself)

| item | expectation | if it misses |
|---|---|---|
| primary k (no `our_length`) | 3-5 groups at strength ≥ 0.80; k = 2 would read as "entries vs exits dominate"; k ≥ 6 unlikely at n = 677 | no stable k: §1.2 |
| noise floor | under 5% of primary trades move between seeded refits, under 10% between bootstrap refits | a floor above 15%: the groups are not stable enough to compare tiers against; reported as such, the tier comparisons read as excess over it |
| + ONE-STREAM | under 15% of primary trades move (over the floor); a NEW group appears — the same-day trades — and it is NOT structural: it separates on the entry side and the exit day's own columns (a late-day sale near the entry day's range), not on the blank pattern alone | over 25% move: the quick trades are not separable from the confident ones on the chart; a structural-only new group: the feature set, not him |
| + LOW | under 10% move; no new group (the rangeless rows drop; the rest are long holds already in MEDIUM's groups) | a new group: the long holds are a behaviour MEDIUM under-represents |
| with `our_length` | the same k and descriptions (the sweep carries the same information) | a different k: the groups lean on our lengths when offered — a finding reported; the primary picture does not change |
| extrapolated values | only `hold_sessions_max` (the same-day trades) and a handful of tail values per feature in the added tiers | a feature with over 5% of a run extrapolated: its map is too narrow on the primary; reported, the feature flagged in the descriptions |
| edges | under 20% move between low-end and high-end descriptions | over: the band is too wide for a minute-level description; the daily-level features carry the groups |
| 2020 vs 2021-22 | the same groups by description, with 2021's short-heavy Feb-Mar showing as a larger share of one group | different groups: a finding about him (or the captions), not a test |
| CONFIRMED | shares within 15 points of the primary's in every group; at least one confirmed trade in every group | a group with none: flagged "unchecked by his words" |
| descriptions | at least one group reads as an early-day buy near a recent high after a run-up, and one as a sale within two sessions near the day's low — plain chart words, no rule name | — |

## 8. Cost — the whole path priced up front

| item | $ | my capacity | his time |
|---|---|---|---|
| part 1: the tiers (`05_tiers.py`, this registration, tests, the dry run) | 0 | written (this session) | this review, ~15 min; one go |
| the freeze and `05_tiers.py --run` (writes `tiers.tsv`) | 0 | main loop, minutes | — |
| part 2: `06_groups.py` (features at the middle minute from step 5's bar code; the method of §4; the runs of §5) + tests + dry run + run | 0 (bars on disk; no model call) | 1 Fable build (~250k) + 1 Sonnet tests (~70k) + 1 read (~100k) | the report, ~20 min; one decision |
| **total** | **$0** | **~420k tokens, one weekend slot** | **~35 min, two decisions** |

No paid call is proposed; no vision read of charts (if one is ever proposed it is priced then and is his call).

## 9. What this does not answer

- **Which price he paid** — the middle minute is OUR convention for where a fill most likely sits; the edges run bounds how much it
  matters, nothing resolves it.
- **An exit without the path** — an exit description is where on the chart he sold, after the entry; §3.3 strips every entry-to-exit
  measure, but the exit day's own measures still sit on the path, and the primary's exits are all trades held overnight or longer (§2.3).
  The entry-only grouping is the outcome-free reference; the joint groups are read with this in mind.
- **Whether a HIGH trade is a correct trade** — a tier is screen quality (how tightly the panel brackets the sides), not correctness; a
  tightly bracketed misread ticker is HIGH. Only the 53 confirmed trades carry his words, and they are the ones he chose to talk about.
- **Real quick trade or misread ticker** among the 510 ONE-STREAM positions — the chart cannot tell; the captions could (a later count,
  his call).
- **His sizes, his side (long / short), adds and trims, and the trades between two streams** — the panel never shows them; a short is
  described at its entry and cover like a long, and the groups may mix the two.
- **2021-07 to 2022-06 with the same confidence as 2020** — the streams thin out; 2022 is 4-13% of every tier.
- **A behaviour that is a continuum** — k-means cuts a continuum into arbitrary pieces; the strength criterion is meant to read such a
  case as k = 1 or 2, but a smooth gradient with a stable cut would still show as groups. The feature distributions are printed beside
  the groups for this reason.
- **Rules** — no rule is named, matched or rejected before step 8; a group is a description.
- **Stability beyond 2020 vs 2021-22** — both are already seen by the earlier reads; the forward shadow and the sealed 2025-26 test stay
  the only confirmatory reads, and this read is not one.

## 10. Files, guards, tests

**Code (under `scripts/probes/_705_asis_1026/`):**
- `05_tiers.py` (built): `--dry-run` (the claims: the approved counts, the population, the flag agreement, the confirmed sets; every table)
  → `05_tiers_dryrun.txt`; `--print-pins` → `05_tiers_pins.txt`; `--run` → `asis_1026/tiers.tsv` + `05_tiers.txt`, refused unless the dry
  run completed with 0 MISMATCH and was made by the modules on disk, every pin is below THIS doc's freeze marker (none ABSENT), the
  ledger verifies and no output exists. Ledger rows `step7_tiers_*` in `01_ledger.tsv`.
- `forbidden_outcomes.txt` (built): the outcome names scanned against the step-7 modules together with `forbidden_identifiers.txt`,
  including the names 04_band and 03_check use for outcomes.
- `05_tiers.py::STEP7_FEATURES` / `exit_lookbacks_defined` / `exit_features_defined` (built): part 2's feature lists and the exit look-back
  rule (§3.3), pinned with the module, printed by the dry run, imported by `06_groups.py` and never widened there.
- `06_groups.py` + its tests (part 2, after the freeze): the features at the middle minute (step 5's `day_context` / `features`, called
  at the middle minute — the band's reachable minutes from `ranges.tsv`, the bars from the minute store), the method of §4, the runs of §5,
  the phrase table; the same `--dry-run` / `--print-pins` / `--run` gates, pinned below this marker before its run.

**Pins (`05_tiers.py --print-pins`):** step 5's inputs and modules (`asis_common.pins`), **both doc bodies** (`doc_body` = this document
above its marker; `doc_body_steps56` = the frozen steps-5/6 document, so step 7 is tied to the text it rests on), step 5's three outputs,
6b's modules, printout and per-statement file, `05_tiers.py`, `forbidden_outcomes.txt`, the dry-run printout.

**Guards:** the seal (every window date read is asserted ≤ 2024-12-31); the seven forbidden folders (`checked` on every path); the
identifier scan with BOTH name lists; the import belt (no rule module in `sys.modules`); seeded draws only through `rng_for` with a
named key; no network, no model client.

**Tests (`tests/test_asis_tiers.py`, synthetic, CI-safe):** `tier_of` on hand-built sides — every tier and every LOW reason, the order
(a flicker with tight minute sides is ONE-STREAM, a wide side is LOW whatever the streams, a `bracket_other` side is LOW, a missing
sale row is LOW); the 3-position fork (a single-stream non-flicker with near sides is MEDIUM and flagged); `confirmed_flags` (a stop
LEVEL inside the range does not confirm; `r5_agree` only; the primary sub-count); `population` (in-span by the buy side only; a sale
out of span kept); `assign_all` columns and the composition buckets; the identifier scan on the module with both lists (a planted
outcome name fails); the fresh-interpreter import test; the run gate (no dry run / MISMATCH / a pin above the marker / an ABSENT stage
pin / an existing output each refuse; a two-marker doc refuses); the real-data dry run ends `DRY RUN COMPLETE` with 0 MISMATCH (skipped
without the local data tree); after the 2026-10-27 review: no `ret_N` on either run's exit side and no `our_length` column in the primary
set; the exit look-back rule on hand-built holds (one session → none; same-session → all; hold 4-5 → 1 and 3); the per-statement file
read through `usecols` drops its other columns; the outcome-name list carries the band names; the price facet keyed on resolution.

## 11. Revisions before the freeze (2026-10-27)

| source | finding | change |
|---|---|---|
| advisor, first pass | two readings of "seen on 2+ streams" (the `flicker` flag vs `n_streams >= 2`) differ on 3 positions; six variants had been explored, the limit | §2.2: the flicker reading locked (the approved text's word, the approved counts' source), the 3 printed by eid and flagged, the fork a dry-run claim; no further variant |
| advisor, first pass | `inside == True` on a stop LEVEL does not confirm a fill | §2.4: `confirmed_r1` requires `fill == 'fill'`; the primary-line count beside; `r5_agree` only on unique joins is a claim |
| advisor, first pass | the §3.4 features exist only at candidate points; averaging over them weights by family density | §3.2: the middle minute (volume-median minute; the largest-volume session when daily-only); point-level columns held out; the band width a descriptor, with an edges run |
| advisor, first pass | the frozen §5 groups anchored and unanchored separately; at 11 primary / 53 confirmed an anchored grouping is impossible | §2.4 / §5: the confirmed trades are never pooled into a fit; assigned to the primary groups and compared; the joint row is the primary unit, one-sided runs beside |
| advisor, first pass | the method must leave no choice to after the groups are seen | §4: rank-normal, PCA to 90% whitened, k-means seeded, prediction strength ≥ 0.80 with the largest k, minimum group size, a fixed phrase table; §5 the Hungarian matching and the consequence table |
| advisor, first pass | outcome names need a mechanical guard; both doc bodies pinned; a single marker | §3.5 / §10: `forbidden_outcomes.txt` scanned with the §3.1 names; `doc_body_steps56` pinned; the run gate refuses a doc without exactly one marker |
| review, second pass (F1, high) | the exit side's `ret_N` with N at or above the hold is the trade's close-to-close return under another name; the exit look-backs carry the same path | §3.3: no `ret_N` on the exit side; a look-back only when N < `hold_sessions_min` or a same-session round trip; `dist_prev_close` on a one-session hold blank; the ratios kept (no sign); registered as `STEP7_FEATURES` + a test; §3.5 / §9: the entry-only run is the outcome-free reference |
| review, second pass (F2) | `check_r1_r5.tsv` carries a stated-dollar column and a `stopped` action; the outcome-name list missed 04_band's names | `usecols` on the six columns, a claim and a test; the names added; §3.5 and the docstring say "present in one input, never read" |
| review, second pass (F3) | the primary holds no same-day round trip (2+ streams needs a hold into a second stream); clipping would squash their hold length | §0 / §2.3 say so; §4.1: linear tails, never a clip, extrapolated counts printed |
| review, second pass (F4) | the primary included the `our_length` columns, reversing the frozen order | §3.3 / §5 / §7: the primary runs without them, the sweep in their place; "with `our_length`" is the sensitivity run; the primary stays whatever it shows |
| review, second pass (F5) | k per run, unmatched groups, the noise floor and family-level survival were unstated | §4.4 / §5: k re-chosen per run; unmatched = all moved; seeded + bootstrap floor, lines read as excess; survival on 13 families + Spearman ≥ 0.8 against the frozen means |
| review, second pass (F6) | "no price at all" conflated daily-only sides with sides having no bars | the facet keyed on resolution; §0 / §2.3 corrected (two in five no bars; one in five daily-only) |
| review, second pass (F7) | 130 flickers read LOW on their side facts, a third reading not listed | §2.2 names it; a dry-run claim pins the 130 |
| review, second pass (F8) | assigning the confirmed trades departs from the frozen §5; 6 of 53 have no features | §0 / §2.4 / §5: the departure stated for his approval; 47 assignable (a claim) |
| advisor, final pass | "never pooled into any fit" contradicted itself — 33 of the 47 are rows of the primary fit; mode B runs had no stated standardization or reduction | §0 / §2.4 / §5: the confirmed read is a coverage check (33 fitted, 14 placed by nearest centroid — a claim); §4.1: a run with other columns fits its own maps and reduction on its own rows |
| review, second pass (F9) | §0 too long; the no-same-day fact missing from it | §0 cut to five bullets, the fact in it |
| advisor, second pass | structural blanks vs the quarter-drop rule; two comparison modes (no shared space when the columns differ); the blank pattern can form a group on its own; the sweep's ° flag | §3.4: structural blanks exempt, zero-filled, counted per group, "structural" flag at 80%; §5: mode A / mode B; §4.6 / §5 (d) / §7: the artefact read; §3.3: only 20 carries ° for the range / volume ratios |

<!-- FREEZE -->
## Freeze record

Empty until the freeze. After his go: the main loop freezes this document (`doc_body` pinned), runs `05_tiers.py --print-pins`, pastes
every pin below, runs `05_tiers.py --run` once (writes `tiers.tsv`), then builds part 2 (`06_groups.py`), whose dry run and pins are
pasted below the marker before ITS run. Nothing above the marker is edited after the freeze; any edit changes `doc_body` and the run
refuses.
