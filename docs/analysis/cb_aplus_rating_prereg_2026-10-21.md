# #705 — the A+ RATING for breakouts: rank them and take only the best few a week — pre-registration (2026-10-21; revised 2026-10-22 after review, again the same day after the recheck, and a third time the same day for his rulings on base length and fractal contraction; BEFORE any rating outcome)

**Why.** The operator (2026-10-21): *"for breakouts we'll also need ranking similar to what we try to do with EPs, but breakouts are
going to be more common and we need a rating system to select the best ones ... We need to focus on the A+ setups per Qullamaggie, he
definitely doesn't trade all however many thousands breakouts per year"*, and *"we should also have some secondary indicators to
test, like group themes, etc."*. Every breakout our rules find (C0) runs about 33 a week in 2017–21 and 53 a week in 2022–24
(medians; 76 in 2025–26); the strict FILTER (C1) keeps ~30 a year, shows no edge, and dropped 342 of the 352 trades on the 39 known
2020–21 multibaggers. This read asks whether a RATING that picks the top few a week from all breakouts does better than taking them
all. $0; no paper, no live.

## Method / population

**The rating — FIXED, pre-named, unfitted, and known AT THE FILL.** Both eras have been read many times (advisor 10-21), so no
weight is chosen on any number: equal weights, directions fixed below. Every input is known before or at the 5-minute fill; nothing
after it (no breakout-day close, high or full-day volume: `close_E`, `high_E`, `vol_E`, `breakout_vol_x` are look-ahead and excluded;
the base's daily bars are read only through D).

- **The seven concepts (his 10-21 list, minus base length and market phase (a split) — both RULED OUT of the score 2026-10-22; each a "concept" with weight 1/7).**
  D = the watch night, E = the breakout day. Concept 1 is his 10-22 ruling: contraction is FRACTAL — three scales inside ONE concept.

| # | his word | input (file · column · how computed) | better = | known at |
|---|---|---|---|---|
| 1 | volatility contracting over the base, at several scales (his 10-22 ruling: *"volatility has to be contracting over time, tightening, if base is long but wide and loose, that's not good"* · *"Volatility contraction can be fractal … you can see it contract over months, weeks, days and or intraday … Not a hard rule but pattern should be visible"*) | THREE scale readings, each a late ÷ early ratio over the base's sessions P..D (P = the pole top; the weekly and daily windows start at P+1, the pullbacks at P itself): WEEKLY `wk_ratio`, DAILY `tightening_ratio`, PULLBACKS `pb_ratio` — the full spec in "Concept 1, the three scales" below; the concept's percentile = the mean of the three scale percentiles with a MISSING scale counted 0.5 | lower, every scale | D |
| 2 | volume dry-up | `vol_dry5` = mean daily volume over D−4..D ÷ mean over D−9..D−5, from the daily export (his captured note 10-18, the Deepvue screen: *"weekly volume at least 50% lower than the previous week"*); a zero or absent earlier-week mean → missing (the fill is then unrated, counted) | lower | D |
| 3 | RS leadership on 1/3/6 months | `rs_best` (candidates: the best of the 21 / 63 / 126-session return percentiles across the universe on D) | higher | D |
| 4 | the run-up before the base | `prior_move` (candidates: pole high ÷ pole low − 1) | higher | D |
| 5 | the stair-step number | `stair_n` = the count of DISTINCT bases among the same ticker's `K = tl`, `retrigger = 0` candidate rows (filled or not, abstained or not) whose E′ lies in [E − 120, E − 1] SPY sessions, from the same candidates file, EXCLUDING the fill's own base. The base of every such row, and of the fill, = its `pole_ci` mapped through the chain built AT D: `cb.chain_bases` over the pinned watch table's rows of that ticker with `watch_date ≤ D` (`pole_ci`, `pole_date`; poles ≤ 3 sessions apart are one base, `POLE_DRIFT_MAX`). The candidates' pre-stamped `base_id` is NEVER read — it comes from a chain over EVERY watch row, later nights included (the recheck measured that chain moving 1 of 22,357 fills: AMRSQ 2021-08-26, 3 → 4, a pole first seen on 2021-08-31 bridged the 06-25 and 07-02 bases); the figures "17,405 first breaks over 14,379 chains" (pre) are that full-file chain's. A resumption of the same base is the same base, his stair step is a new pole | lower (fewer prior bases = EARLIER in the run = better — his lean, 2026-10-22, verbatim: *"I'm not exactly sure, but I feel earlier the breakout the better. Later breakouts, may run out of momentum."* His uncertainty is disclosed; the REVERSED orientation is a side row, reported beside, never deciding) | D (= E − 1; the watch rows ≤ D) |
| 6 | breakout-day range so far | `range_open5_adr` = (max high − min low over the PRESENT minutes 0..4 of E) ÷ (the first present minute's open × `adr20`), from the minute file | higher (a range-expansion day; "lower" would select tight stops and inflate R — the #327 class) | the fill |
| 7 | breakout-day volume so far | `open_drive` = Σ volume over minutes 0..4 of E ÷ `adv20_vol_D` (candidates: the mean of the 20 daily volumes ending D). A RANK input only: SIP regular-hours minutes over a daily ADV20 that for 2022+ (Polygon) counts extended hours — not a calibrated "× normal" | higher | the fill |

  Every fill's `fill_minute` is ≥ 5 in all three tables (min 5), so minutes 0..4 are strictly before every fill. A minute absent from
  0..4 contributes 0 volume and nothing to the range; no minute present → both breakout-day inputs missing. The window of concept 5
  starts before the candidates file for 505 fills (2017–21) / 1,778 (2022–24) — those fills are unrated on that concept only (counted).
  Market phase (`phase_qqq_10_20`) is NOT a rank input: it is an A+ SPLIT (below; RULED "Ok" 2026-10-22). NOT in the score, each an
  "alone" row beside (deviations table below): `base_len` (RULED 2026-10-22: never deciding), `range5_adr` (the P5 table's 5-session
  mean range ÷ ADR20 at D — a LEVEL of tightness, not a contraction over time), `base_depth`, `atr14_slope` (= ATR14% at D ÷ ATR14%
  over the 14 sessions ending P+1 — its denominator is the POLE's volatility, not the base's early part; a positive ratio, lower =
  tighter) and `rs_all`.

- **Concept 1, the three scales — the spec (his 10-22 fractal ruling; intraday is NOT one of them: the base's own intraday bars
  (P..D) are in no pinned table, so an intraday contraction over the base cannot be read before the fill — said, not scored;
  E's minutes 0..4 are used only as concepts 6–7, range and volume so far. MONTHS are not a separate scale either: no base
  exceeds 45 sessions (`BASE_MAX_SESSIONS = 45`, `consolidation_breakout.py` line 105, about two months), so no base holds even
  three monthly blocks and the weekly reading across the whole base is the longest scale the data can read — a mechanical
  reason, like `atr14_slope`'s, not an ask).** The base = the ticker's rows of the pinned daily export (`daily_closes_all.csv.gz`:
  ticker, date, o, h, l, c, v) with date in [`pole_date`, D] (P = the row at `pole_date`, from the candidates row; D = the watch
  night); the row count MUST equal `base_len` + 1 (measured: every fill, both eras) and h at P must equal the watch row's
  `pole_high` (check 12). Index 0 = P, n − 1 = D; nothing after D is read (checks 1 and 12). **Every reader sorts the daily
  export by (ticker, date) before reading the base rows, the session calendar or `vol_dry5`: the cb702 export is NOT date-ordered
  within a ticker (18,991 of 20,285 tickers, SPY included; the cb702_pre export is sorted), so file order is never index order.**

| scale | input · formula (all from the export's h, l, c over the base) | direction | missing when | measured present (2017–21 / 2022–24) |
|---|---|---|---|---|
| WEEKLY — the weekly bars' highs and lows converging across the base | `wk_ratio`: k = ⌊`base_len` ÷ 5⌋ full 5-session blocks counted BACK from D (block 1 = D−4..D, block 2 = D−9..D−5, …; the 0–4 earliest sessions after P that do not fill a block are dropped — so the block ending at D is always full and NO partial block exists; calendar weeks are not used, so the question "does the current partial week count" does not arise); a block's envelope = (max h − min l) ÷ its last close; m = ⌊k ÷ 2⌋; `wk_ratio` = mean envelope of the LAST m blocks ÷ mean envelope of the FIRST (earliest) m blocks (k odd → the middle block is unused) | lower | k < 3 (`base_len` < 15; k ≥ 3 so the reading runs from the base's start to its end, not just its last two weeks — see the overlap disclosure below); an early mean of 0 | 5,166 of 13,359 (39%) / 3,919 of 8,989 (44%); the per-scale pool floor then strips 346 / 79 of those (below) |
| DAILY — the last days' ranges smaller than the base's earlier ones | `tightening_ratio` (candidates column = the watch row's `range_recent5` ÷ `range_early5`: the mean of (h − l) ÷ c over D−4..D ÷ the same over P+1..P+5) | lower | never (zero missing, check 3) | all / all |
| PULLBACKS — successive pullbacks inside the base getting shallower | `pb_ratio`: swing highs = P and every j in [2, n − 3] with h[j] > h[j−1], h[j] > h[j−2], h[j] ≥ h[j+1], h[j] ≥ h[j+2] (two lower highs before, two not-higher after; the first of a tie counts); for consecutive swing highs s_k < s_{k+1} the COMPLETED pullback k = (h[s_k] − min l over the sessions strictly between them) ÷ h[s_k]; the pullback from the last swing high to D is incomplete and never counted; `pb_ratio` = the last completed pullback ÷ the first (the one from the pole top) | lower | fewer than 2 completed pullbacks (fewer than 3 swing highs including P); a first pullback of depth 0 | 5,713 of 13,359 (43%) / 4,138 of 8,989 (46%); the floor strips 234 / 49 more |

  - **Per-scale pool floor:** each scale is ranked against the pool's non-missing values of THAT scale, |S| ≥ 30 else the scale is
    missing for the fill (the count printed; the strips measured above). **The combining rule — ONE, pinned: the concept's percentile
    = the MEAN of the three scale percentiles, a missing scale (by base length, by depth, or by the floor) entered as 0.5.** Why the
    mean over a count: a count needs a per-scale threshold ("contracting" = ratio < 1?) — a hard rule per scale, which he said it is
    not — and ties on 0..3; the mean has no threshold and, because every percentile is bounded [0, 1], no one scale can carry more
    than a third of the concept, so a reading visible at three scales outranks one extreme reading. Why 0.5 for a missing scale
    rather than the mean of the present ones: his ruling as recorded rewards contraction "visible at more scales" — under the mean
    of the present scales a 10-session base with a daily percentile of 0.9 would score 0.9, equal to a 40-session base contracting
    at all three (0.9, 0.9, 0.9) and ABOVE one showing it at the daily scale only (0.9, 0.5, 0.5 = 0.63): the scale count would
    reward nothing. Under 0.5 the order is: long and contracting at every scale (0.9) > short and tight (without a pullback
    reading, ceiling 2/3 with two scales missing — 0.63 at a 0.9 daily percentile) > long but loose (0.2) — the three cases his words name. Consequence disclosed: a short base (10–14 sessions,
    61% / 56% of the population) without a pullback reading is capped at 2/3 on THIS concept (1/7 of the score; 0.63 at a 0.9
    daily percentile); one with two completed pullbacks (about 16% of short bases: 1,322 / 847 fills) can reach 5/6 (0.77 at 0.9
    per scale); base length is not rewarded by itself.
    Concept 1 is therefore never missing while the daily scale's floor holds. The swing rule and the 0.5 are "Put to him" items 1–2.
  - **Disclosed, these two readings:** no weekly or pullback reading exists in any pinned table; they were computed for the first
    time by this registration's feature census (counts above; no outcome column was read or joined — `scripts/probes/_cb_backtest/`
    holds no copy; the census is re-run by data check 2). Their look-ahead guard is checks 1 and 12. The first pullback (from the
    pole top to the first trough) overlaps `base_depth` / `retrace` when that trough is the base low — the alone rows show it.
    **Overlap with the daily scale, disclosed (the weekly k ≥ 3 rule stands):** at `base_len` = 15 (389 / 252 fills) k = 3 and
    m = 1 compare block 1 (D−4..D) with block 3 (D−14..D−10), which is exactly P+1..P+5 — the daily ratio's own ten sessions,
    read through a different statistic (a 5-session envelope vs the mean daily range); across `base_len` 15–19 (1,333 / 1,012 fills,
    26% of the weekly-present fills) 6–10 of the 10 sessions overlap.

- **The rank — against the PRIOR 20 sessions, never the week around the fill.** For a fill on E its POOL = every population fill
  (the C0 fills defined under Population below) with E′ in [E − 20, E − 1] on the SPY session calendar of the pinned daily export,
  open marks included. For a feature f with the pool's non-missing values S (the fill itself is not in S): pct_f = (number of S worse
  than the fill + 0.5 × number equal) ÷ |S|, "worse" by the direction above (so pct is in [0, 1], higher = better; the mid-rank
  percentile — pandas `rank(method="average", pct=True)` on S ∪ {fill} gives the same ordering, this formula is the definition).
  Concept 1's percentile = the mean of its three scale percentiles, a missing scale 0.5 (its block above); every other concept's =
  its one feature's pct; the SCORE = the mean of the present concepts' percentiles. Pool floor, EVERY concept (per scale for concept
  1): |S| ≥ 30 non-missing pool values, else that concept (scale) is missing for the fill (so concept 5 stays missing well past each
  era's first 120 sessions while its pool coverage is thin). A fill missing concept 5 alone is rated on the other six; a fill
  missing any other concept is UNRATED (counted). The pool of the first 20 sessions of each era is
  thin by construction (fills with fewer than 30 pooled fills: 36 in 2017–21, 77 in 2022–24 — burn-in, counted). The pool never
  crosses an era's table except at the sealed 2025–26 read, whose first 20 sessions pool the 2022–24 table's fills (both pinned);
  there the 23 fills of 2025-01-03 ARE in the pool of later fills (they are in the table) though never A+-eligible themselves.
- **The A+ rule (decides).** The pool's REFERENCE scores = each RATED pool member's own score by the same formula against E's pool
  with itself removed (never against the member's own [E′ − 20, E′ − 1] window). A member m is RATED for this purpose iff m's own
  value is present for every concept except 5 (for concept 1: its daily scale) AND, in the pool minus m, every concept except 5 has
  ≥ 30 non-missing values (concept 1: on the daily scale; a weekly or pullback scale short of 30 in the pool minus m is 0.5 for m);
  concept 5 enters m's reference score iff m's own `stair_n` is present and its floor holds in the pool minus m, else m is scored on
  the other six. Whether m was rated at its own fill time plays no part (the golden fixture holds one member that flips at this
  boundary, check 8). **Effective floor, stated once:** a fill gets a cutoff only through ≥ 12 rated members, and a member carrying
  a value sees the pool minus itself — so in practice a fill is rated only when the pool holds ≥ 31 non-missing values on every
  non-5 concept (measured 10-22 on the pinned tables: no fill in either era has a pool of exactly 30 fills — 0 / 0; the thin
  pools are the 36 / 77 under 30). **The per-scale boundary of concept 1 does bind in real data:** in 2017–21, 66 (weekly) / 98
  (pullbacks) fills have exactly 30 values of that scale in their pool (0 / 0 in 2022–24) — there the fill is ranked on the
  scale while every reference member carrying it sees 29 in the pool minus itself and enters it as 0.5; deterministic and pinned
  by the member rule above, and tested by the golden fixture E3 (check 8c). The CUTOFF for E = the 12th-highest reference score (N = 3 a week × 4 weeks of pool; the 4th-highest for
  N = 1, the 20th for N = 5; fewer rated members than that → the fill is unrated, counted). **A+ = score ≥ cutoff AND fewer than N
  A+ already taken in the fill's ISO week (Mon–Sun by E), taken in fill order (E, `fill_minute`, ticker A→Z).** A fill at or above
  the cutoff after the week's N is "capped" (counted; it stays in REST for the paired bar — conservative, stated). **N = 3 decides**
  (his "best few"); N = 1 and N = 5 beside. Nothing in the flag depends on any fill after it, same day or later — that is what the
  forward shadow can record at the entry, and WOULD-FAIL-IF check 2 tests it.
- **HINDSIGHT row (beside, labelled so, written only after both verdict files exist):** the within-ISO-week top-N by the same
  percentile formula over that week's rated fills (the fill against the week's other fills), ordered by score, then `rs_best`,
  then earlier `fill_minute`, then ticker. The draft's original rule; reported, never deciding.
- **The secondary indicator `+grp` — its OWN bar; it decides only what the shadow RECORDS, never a cell.** `grp_pct` (candidates:
  the SIC group's 63-session return percentile on D; groups under 10 members drop out; the SIC map is today's; higher = better)
  added as an EIGHTH concept at weight 1/8. The recipe, pinned: (i) a fill's +grp score = the mean of its present concepts'
  percentiles with `grp_pct` among them; a fill missing `grp_pct` is UNRATED under +grp (an eight-concept rule — it is not rated on
  seven), and the pool floor (≥ 30 non-missing) applies to `grp_pct` as to every concept; (ii) the +grp A+ set is produced by the
  SAME pool (every population fill with E′ in [E − 20, E − 1]), the same member rule (with `grp_pct` among the concepts a member
  must carry), the 12th-highest reference +grp score as the cutoff, the same cap (N = 3, fill order, counted over the +grp A+
  alone) and the same week rule — a complete second run of the rule, nothing shared with the core but the inputs; (iii) the
  comparison = the +grp A+ set vs the CORE A+ set, each intersected with the era's grp-present fills (present for 9,059 of 13,359 /
  7,291 of 8,989 — counted AFTER the 2022-01-03 drop; the share and the overlap of the two sets printed), on mean R, by the paired month-block recipe under Bars —
  2,000 draws, the difference of the two groups' means inside the drawn months, +grp minus core, generator
  `numpy.random.default_rng([702, zlib.crc32(b"aplus_pair_grp|<period>|3")])`. Lower end > 0 → **`+grp` ADDS**; upper end < 0 →
  **`+grp` SUBTRACTS**; else **CAN'T TELL**. The sets overlap (both pick about 3 a week from one pool): a trade in both is in
  both means, so the difference measures the swapped trades. **Consequence, fixed now (one choice):** ADDS in BOTH eras AND the
  core is RECORDED by the consequence table — the RECORD cell OR a LEAD cell, i.e. whenever the shadow records the core at all →
  the shadow records the +grp score, cutoff and flag BESIDE the deciding ones; it never changes the deciding rule in this read; any
  other reading → the core alone is recorded and the +grp verdict is reported. The +grp A+ set per era and its paired Δ
  are in the re-derivation's MATCH list (check 11).
- **The phase split (a descriptive split, beside, no bar) and themes.** The QQQ 10/20 phase at D: the A+ group split phase-on vs
  phase-off, n and mean R per side (it is the same for every fill in 190 of 254 / 103 of 145 weeks, so as a rank input it is a
  tie; RULED a split 2026-10-22 — his "Ok"). Themes:
  FORWARD-ONLY — the recorder in (c) stores the theme and stage of each watch name on D; no `mi_themes` history is read here (its
  rows are updated in place, so a past night can carry tickers added later, there is no local capture, and it needs the network).
- **Alone rows (beside; the pre-named table for "which ingredient carried it"):** each of the seven concepts ALONE under the same
  pool, cutoff, cap and N = 3; each of concept 1's three SCALES alone (weekly, daily, pullbacks; a fill missing that scale is
  unrated on the row); plus `base_len` (longer = better — the beside row his ruling allows, never deciding), `range5_adr` (lower),
  `base_depth` (shallower = better), `atr14_slope` (lower = better) and `rs_all` (higher) alone.
- **The reversed-orientation row (beside, never deciding):** the CORE score with concept 5 flipped (more prior bases = better),
  N = 3, same pool, cutoff and cap — the sensitivity row for his stated uncertainty on the stair step; reported next to the core.
- **Deviations from his 10-21 ruling and the proposal he said yes to — each with its reason** (the ones still open are collected
  in "Put to him before the freeze" below):

| item | ruling / proposal | here | why |
|---|---|---|---|
| stair-step number | an ingredient | an ingredient, oriented EARLIER = better (his 10-22 lean, verbatim in the table); the reversed orientation a side row | RULED 2026-10-22 (PLAN #705; `docs/methodology/operator_shared_notes.md` §2026-10-22); his uncertainty is disclosed in the cell, so the reverse row is reported beside, never deciding |
| base length | "a longer base rates higher" (the 10-21 draft's placeholder) | OUT of the score; an alone row beside, never deciding; not a next-registration candidate | RULED 2026-10-22, verbatim: *"Ok. On line bases, volatility has to be contracting over time, tightening, if base is long but wide and loose, that's not good"* · *"Long bases I meant"* — length is not rewarded by itself; what is scored is contraction over the base (concept 1) |
| contraction | one concept = `tightening_ratio` + `range5_adr` (the second-revision cell) | one concept, THREE scales (weekly, daily, pullbacks), the mean of the scale percentiles with a missing scale 0.5 | RULED 2026-10-22, verbatim: *"Volatility contraction can be fractal, what I mean is that you can see it contract over months, weeks, days and or intraday. So a long base will see contract over weeks with highs and lows tightening, then daily bars also tightening, etc. Not a hard rule but pattern should be visible"*; the swing rule and the 0.5 are this doc's mapping of his words → "Put to him" 1–2 |
| breakout-day range so far | kept, at the confirming bar | kept, at ORH5 = minutes 0..4 | at ORH5 it is close to the low-of-day stop width (`width_adr`), which scales R mechanically — so the A+ group is also read in ADR P&L units (ADR P&L > 0 is in PASS; its median stop width vs C0's is an expectation) |
| market phase | an ingredient | an A+ split | RULED 2026-10-22 — his "Ok" to "market condition used as a split of the result, not a scored input"; it is also a binary equal for nearly every fill in a pool, so it carries no rank |
| `range5_adr` | his 10-21 word "tightness / range contraction" | out of the core; an alone row | a LEVEL (the last 5 sessions' range in ADR units) says "tight now", not "tighter than before" — his 10-22 ruling scores contraction over TIME, and a level would double-count the daily scale → "Put to him" 3 |
| `base_depth`, `atr14_slope` | not named | not in the core; alone rows | not his list: `base_depth` is a retracement level, not a contraction; `atr14_slope`'s denominator is ATR14 over the 14 sessions ending P+1 (the pole's own volatility, code line 690 of `consolidation_breakout.py`), so it reads the run-up, not the base's early part — a mechanical reason, not an ask |
| themes | a 2026 descriptive read + forward | forward-only | the history is mutable and un-captured (above) |
| `rs_best` over `rs_all` | "his 1/3/6-month leaders" | `rs_best` | his scan is three separate lists; a name near the top of ANY one is a candidate; `rs_all` alone beside |
| `grp_pct` | secondary, every era | secondary on the grp-present subset, with its own bar (adds / subtracts / can't tell) and a recording-only consequence | missing for 32% / 19% of fills; in the core it would score a third of the trades on a different formula; the bar makes it a TESTED indicator (DoD (2)) without letting it move a cell |

- **Put to him before the freeze (yes / no each; nothing here is decided by this doc — his answers are written into the rows they
  name in the freeze commit, before the pins are taken). Only this doc's OWN mappings of his words are asked; what he has ruled
  (stair-step direction, base length out, phase as a split, contraction fractal) is not re-asked. ⚠ A "no" on ANY item has no
  pinned alternative: it REOPENS that row for a re-spec and a fresh recheck BEFORE the freeze; the freeze commit carries only "yes"
  answers or re-reviewed rows (the base-length "no" of 10-22 needed exactly this — a full re-spec, not a line edit).**
  1. Pullbacks as the third scale of concept 1, read VCP-style from the pole top (the first pullback = pole top → first trough, so
     it overlaps `base_depth` when that trough is the base low), by the pinned swing rule (two lower highs before, two not-higher
     after; completed pullbacks only) — our reading of his *"etc."*; weekly and daily are his words.
  2. A scale a base cannot show (too short for three weekly blocks, fewer than two completed pullbacks, or a thin pool) counts 0.5,
     so a short base without a pullback reading is capped at 2/3 on this one concept (0.63 at a 0.9 daily percentile; one with
     two completed pullbacks — about 16% of short bases — can reach 5/6) and contraction visible at more scales ranks higher —
     the alternative (score a base on the scales it has) rewards no scale count at all. Yes = 0.5.
  3. `range5_adr` (a LEVEL of tightness) out of the core, an alone row — his 10-22 words score contraction over time.
  4. Breakout-day range so far read at ORH5 (minutes 0..4), not at the confirming bar — the fill IS at ORH5; a later bar would read
     after the entry.
  5. Themes forward-only, the 2026 descriptive read dropped — the theme history is mutable and un-captured.
  6. `rs_best` (the best of the 1 / 3 / 6-month ranks) in the score, `rs_all` (all three) only beside — his scan is three lists.

- **Disclosed — what has already been read that touches this score:** (a) 10-18, 2022–24, C0 `tl`: the TIGHTEST fifth of bases did
  WORST under both exits, by the range ratio (`tightening_ratio`, now concept 1's daily scale) and by the 5-session range in ADR
  (`range5_adr`, now an alone row) (`docs/analysis/cb_his_exit_2026-10-18.md` §2.5, `exits_report_tl.tsv` `fifth_*` rows) —
  the daily scale points the other way; it is kept because he named it, at a third of 1/7 of the weight; the weekly and pullback
  scales have never been read against an outcome on any era (their census above was features only);
  (b) the selection test of his 330 stream picks (98 scored): CAN'T TELL on the 20-session forward return in ADR
  (`cb702_pre/out/selection_result.txt`); (c) C0 under `pp` is published for all three eras (`exitpb_report_{pre,discovery,holdout}.tsv`,
  the row `orh5 · C0 · tl · pp`): mean R +0.025 / −0.169 / −0.129; ≥ 5R 3.47 / 2.57 / 2.95 per 100; ≥ 10R 1.235 / 0.946 / 1.18 per
  100 (165 of 13,363 / 85 of 8,984 / 89 of 7,531 mature) — the numbers the bars are set against; (d) 2025–26 is NOT unread in
  general: the P5, exitpb and h60 reads and `regime_report_holdout.txt` already report it by cell (C0..C7, HTF, the C1 variants —
  cells built on the tightening, prior-move and RS gates), by stop variant, by exit arm, by the QQQ phase (C7, C1_s5) and by
  Apollo's regime. It is unread for THIS score only: no A+ score, cutoff, alone row, +grp row or stair-step count has been
  computed there. No era's A+ rows exist yet.

**Population, inputs, periods.**
- **Population (pinned, no new walk):** the spec-key first breaks of the trendline level (`tl`) filled at ORH5 under the low-of-day
  stop — the P5 fills — with the CARRIED exit `pp` (his ruling: the day-3 third only in profit, stop to cost after it), outcomes as
  already walked: the rows of `trades_<period>_exitpb.tsv.gz` with `arm = pp`, `entry = orh5`, `K = tl` (the table holds 6 arms ×
  2 entries × 2–3 levels of the same trades; this filter is checked, check 3). One row per fill; (ticker, E) unique.
- **Every input, as file · column · join key** (`cb702/…` = 2022+, Polygon daily; `cb702_pre/…` = 2017–21, Alpaca daily):

| input | file | columns used | join key |
|---|---|---|---|
| fills + outcomes | `out/trades_{pre,discovery}_exitpb.tsv.gz` (and `_holdout_`, sealed) | `fill`, `fill_minute`, `fill_month`, `adr20`, `width_adr`, `mature`, `open_mark`, `realized_r`, `pnl_adr` | (ticker, D, E, K) |
| D-night features | `cb702/out/candidates.tsv` · `cb702_pre/out/candidates_tl_com.tsv` | `tightening_ratio` (concept 1, daily scale), `rs_best`, `prior_move`, `adv20_vol_D`, `grp_pct`, `phase_qqq_10_20`; `pole_date` and `base_len` (the base's span for the weekly and pullback scales; `base_len` also the alone row); `base_depth`, `atr14_slope`, `rs_all` (alone rows); for concept 5 the ticker's other rows: `retrigger`, `pole_ci`, `E` (never `base_id`) | (ticker, D, E, K) |
| the chain at D (concept 5) | `out/watch.tsv.gz` · `cb702_pre/out/watch_tl_com.tsv.gz` | `watch_date`, `pole_ci`, `pole_date` — the ticker's rows with `watch_date ≤ D` into `cb.chain_bases` | (ticker, watch_date ≤ D) |
| the base's daily bars (concept 1, weekly + pullback scales) | `daily_closes_all.csv.gz` (same file as the volume row) | `h`, `l`, `c` of the ticker's rows with date in [`pole_date`, D] — `base_len` + 1 rows (equality checked per fill, check 12); `h` at `pole_date` = the watch row's `pole_high` | (ticker, date ∈ [pole_date, D]) |
| `range5_adr` (alone row) | `out/trades_{pre,discovery,holdout}_p5.tsv.gz`, rows `K = tl`, `arm = c3_p33_t20_cut3`, `stop_variant = lod` (one per fill, (ticker, D, E, K) unique) | `range5_adr` (= `range_recent5` ÷ `adr20` at D, 1e-9) | (ticker, D, E, K) |
| its cross-check, and `tightening_ratio`'s | `out/watch.tsv.gz` · `cb702_pre/out/watch_tl_com.tsv.gz` | `range_recent5`, `range_early5`, `adr20`, `pole_high` | (ticker, watch_date = D) |
| daily volume + the session calendar | `daily_closes_all.csv.gz` (no header: ticker, date, o, h, l, c, v) | `v` for `vol_dry5`; the SPY rows = the session calendar (2016-01-04..2022-06-30 pre; 2021-09-27..2026-10-16) | (ticker, date) |
| the first 5 minutes of E | `minutes/<E>.psv.gz` (`ticker|minute|o|h|l|c|v`, minute 0 = 09:30; the LAST gzip member per (date, ticker) is the row set, as every reader keeps it); `minutes/_done.psv` | minutes 0..4: `o`, `h`, `l`, `v` | (E, ticker) |
| the 39 (hindsight) | the list, in full: LVGO, TSLA, PTON, ZM, NIO, PLUG, ENPH, FUBO, ETSY, CRWD, DOCU, NVAX, BLNK, SE, SHOP, FSLY, NET, DDOG, NXH, W, CVNA, APPS, SNAP, MRNA, TDOC, ROKU, PINS, UPST, GME, AMC, DKNG, FVRR, PENN, QS, SPCE, TTD, LULU, NVDA, AMD (the 2017–21 addendum's; SQ absent from Alpaca) | — | ticker |

- **Periods, counts (from the pinned tables, population only):**

| period | table E range | fills | open marks | mature | ISO weeks | edge rule applied | unrated on concept 5 | thin pool (< 30) | A+ n expected (N = 3) |
|---|---|---|---|---|---|---|---|---|---|
| **2017–21 (decides)** | 2017-03-02..2022-01-03 | 13,368 | 5 | 13,363 | 254 | the 9 fills of 2022-01-03 (ISO 2022-W01, Monday 2022-01-03, outside the era) DROPPED → 13,359 fills, 253 weeks | 505 | 36 | 520–760 |
| **2022–24 (decides)** | 2022-04-01..2025-01-02 | 8,989 | 5 | 8,984 | 145 | ISO 2025-W01's Monday is 2024-12-30, inside the era: its 28 fills of 2025-01-02 STAY | 1,778 | 77 | 300–435 |
| 2025–26 (**SEALED**) | 2025-01-03..2026-10-16 | 7,570 joined → **7,547** rated population | 39 (none among the 23) | 7,531 published → **7,508** after the exclusion | 94 → **93** | its 23 fills of 2025-01-03 belong to 2025-W01, a 2022–24 week: EXCLUDED when it is read (the equality targets of check 2 are the post-exclusion numbers) | 0 | 0 (pools the 2022–24 table) | 215–279 (93 weeks × ≈ 2.3 to 3) |

  **Concept 1's scales, per era (features only, measured 10-22 on the pinned tables after the edge rule; equality targets of
  check 2):** WEEKLY present 5,166 / 3,919 (k ≥ 3 blocks, i.e. `base_len` ≥ 15), of which the per-scale floor strips 346 / 79;
  PULLBACKS present 5,713 / 4,138, the floor strips 234 / 49; both present 4,391 / 3,291; neither 6,871 / 4,223; DAILY present for
  every fill; the base-row equality (`base_len` + 1 rows) holds for every fill. The 2025–26 numbers are taken at the confirm read
  (not computed now).

  Week = the ISO week of E (never D: a Monday fill's D is the prior Friday); a week belongs to the era of its MONDAY; the cap is
  counted inside each era's own table. **Both deciding eras are read ONCE each and BOTH decide**; neither fitted the score.
  **2025–26 is SEALED for the rating: no A+ row, score or cutoff is computed on it in this read** (`periods = ("pre", "discovery")`).
  It is the confirmation set — read once, under the deciding rule, only when the consequence table calls for it, on its own
  PASS bar below; otherwise it stays unread for the next registration (the alone rows name that one).
- **Open marks** (`open_mark = 1`; 5 / 5 / 39 fills): ranked, in the pool, and they take an A+ slot (the slot is decided at the fill);
  excluded from every outcome number ("mature" only) and counted.
- **Missing values:** `rs_best`, `prior_move`, `base_len`, `tightening_ratio`, `adv20_vol_D`, `range5_adr` have zero missing in the
  joined rows (check 3); `grp_pct` as above; a missing minute as above; `wk_ratio` and `pb_ratio` missing only by their stated
  rules (the counts above); a feature missing is NEVER read as 0 (check 8) — a missing SCALE of concept 1 is 0.5 by the pinned
  combining rule, the only place a missing value carries a number.

**Data checks the run must pass before any outcome column is opened** (`runner.py aplus-read --period {pre,discovery}` on the
shared scaffold; a failure exits non-zero and writes no report).
1. `freeze_check` on every pin below the marker; a mismatch refuses the run. Once only per period: the A+ table, its `.partial`
   and the verdict file refuse a second run; the operator removes them by hand. The hindsight command (`aplus-hindsight`: the 39
   and the within-week top-N) refuses to run until BOTH verdict files exist; the consequence command (`aplus-verdict`) reads both
   verdict JSONs and prints the table cell, nothing else.
2. STEP 0, written and read before any outcome: per period the fills / open marks / weeks / dropped edge fills / concept-5-unrated
   / thin-pool counts AND concept 1's per-scale counts (weekly present, pullbacks present, each scale's floor strips, both / neither)
   — they must EQUAL the tables above; then the rated / unrated / capped counts, the pool sizes (min, median), and the A+ n (an
   expectation, not an equality).
3. Join: joined rows = 13,368 → 13,359 after the 2022-01-03 drop / 8,989 (at the confirm read: 7,570 joined, 7,547 after the
   2025-01-03 exclusion, 93 weeks, 39 open marks, concept-5-unrated 0, thin pool 0); zero missing in the six D-night inputs
   (`rs_best`, `prior_move`, `base_len`, `tightening_ratio`, `adv20_vol_D`, `range5_adr`); `vol_dry5`, `wk_ratio` and `pb_ratio`
   missing only by their stated rules (the counts printed); the base's export rows = `base_len` + 1 for every fill and `h` at
   `pole_date` = the watch row's `pole_high`; every E on the SPY calendar; (ticker, E) unique; the P5 filter yields exactly one
   row per fill; the exitpb filter yields exactly one row per fill.
4. The golden synthetic fixtures (check 8 below) pass on the committed code.
5. WOULD-FAIL-IF checks 1–2, 5–7, 9 and 12 run on the real inputs (they read features and the flag, never an outcome number) and
   pass.
6. Independent re-derivation (pandas, no runner code) — see Bars; VERDICT MATCH before the result is written.
7. **The confirmation read, `aplus-confirm --period holdout`:** the SAME pinned rule and code on the sealed 2025–26 table; it
   refuses unless both deciding verdict files exist AND read PASS × PASS; once only (its own table, `.partial` and verdict file);
   its bar = the PASS bar below with the 2025–26 numbers (C0 = the published 7,531 mature fills: mean R −0.129, ≥ 5R 2.95 per
   100; the outlier threshold: count_ge10 × 7,531 ≥ 2 × 89 × n — ≈ 2.36 per 100), read once; data checks 1–6 apply to it unchanged.

## Bars (per era; `tl`; ORH5; `pp`; mature walks; precedence: n first)

- **PASS (per era) — all of:** the A+ group (N = 3) has n ≥ 30 mature trades; its month-block 95% interval (blocks = `fill_month`,
  2,000 resamples, `block_bootstrap_ci`, seed 702, key `aplus|<period>|<N>|<score>` — the literal tokens are pinned under the
  paired bar below) has lower end > 0; ADR P&L > 0; it beats
  C0 on mean R AND on the ≥ 5R share, where **C0 = the PUBLISHED C0 `tl` ORH5 `pp` row of the era, its mature fills — 13,363 /
  8,984 / 7,531 (one choice: the 9 dropped 2022-01-03 fills and the 23 excluded 2025-01-03 fills STAY in the baseline, a 0.07% /
  0.3% difference in n): mean R +0.025 / −0.169 / −0.129, ≥ 5R 3.47 / 2.57 / 2.95 per 100**; **and the OUTLIER bar: its ≥ 10R
  trades per 100 mature trades, counted at ALL stop widths (like for like with the published `share_ge10`), are at least TWICE
  C0's published rate — decided as INTEGER comparisons, no rounding anywhere: 2017–21 **count_ge10 × 13,363 ≥ 2 × 165 × n**,
  2022–24 **count_ge10 × 8,984 ≥ 2 × 85 × n**, the 2025–26 confirm read **count_ge10 × 7,531 ≥ 2 × 89 × n** (n = the A+ group's
  mature trades, count_ge10 = its ≥ 10R trades); the per-100 figures 2.47 / 1.89 / 2.36 are DISPLAY roundings only (the exact rates
  are 2.4695 / 1.8923 / 2.3636 — e.g. 7 of 370 in 2022–24 reads 1.892 per 100 and FAILS, 7 × 8,984 = 62,888 < 2 × 85 × 370 =
  62,900) — AND those ≥ 10R trades come from ≥ 3 distinct tickers AND ≥ 3
  distinct calendar months (fill day), the spread counted ONLY over trades whose stop is ≥ 0.25 ADR20 wide (the runner's
  `tail_tickers` / `tail_months` precedent; the spread at all widths beside).** Why twice: at 300–760 trades a random subset at
  C0's own rate already holds about 3–9 ≥ 10R trades, so the 3-and-3 spread alone is met by chance most of the time (Poisson mean
  3.9: P(≥ 3) ≈ 0.74); his point (10-19) is that the method lives on outliers, so the bar asks the rating to find them at twice
  the base rate, spread across names and months.
- **FAIL:** n ≥ 30 AND (the interval's upper end < 0, OR not beating C0 on mean R). **CAN'T TELL:** otherwise — including "positive,
  no tail" (interval above zero, beats C0, outlier bar not met).
- **The paired rating bar (per era):** A+ minus REST (the era's rated fills not in A+, capped fills included), the mean R
  difference. NEW code, pinned here: 2,000 draws; each draw resamples the era's fill months with replacement (as many as there are
  months), takes BOTH groups' trades inside the drawn months and the difference of the two means; the 2.5 / 97.5 percentiles
  (numpy, linear); generator `numpy.random.default_rng([702, zlib.crc32(b"aplus_pair|<period>|<N>|<score>")])`; a draw with an
  empty side is discarded and redrawn (counted). Lower end > 0 → **the rating separates**; upper end < 0 → **it picks worse**;
  else can't tell. **The literal key tokens (both keys; the re-derivation must reproduce every interval):** `<period>` ∈ `pre` /
  `discovery` / `holdout`; `<N>` ∈ `1` / `3` / `5`; `<score>` ∈ `core`, `grp`, `rev_stair` (concept 5 reversed), `alone_c1` …
  `alone_c7` (the seven concepts, by the table's numbers), `alone_c1_weekly`, `alone_c1_daily`, `alone_c1_pullbacks`,
  `alone_base_len`, `alone_range5_adr`, `alone_base_depth`, `alone_atr14_slope`, `alone_rs_all`; +grp's paired key stays the
  literal `aplus_pair_grp|<period>|3`. Only the core's paired Δ and +grp's are computed (below); the PASS-interval key is built for
  every reported row.
- Reported per era × N × score (core; +grp; the core with concept 5 reversed; each alone row, the three scale-alone rows included): n, win rate, average win / loss,
  mean R and interval, ≥ 5R / ≥ 10R / ≥ 20R per 100, total R, ADR P&L, the median stop width in ADR vs C0's, the unrated / capped
  counts, the share of weeks with fewer than N A+ (after burn-in), the A+ group's weekday and `fill_minute` mix against C0's (the
  fill-order cap structurally favours Monday and early-minute fills — fine forward, but visible), the phase split; the paired Δ
  for the core (A+ vs REST) and for +grp (vs the core A+, grp-present subset, its own key) — no other row gets one.
- **Expectations, fixed now (a miss is reported first and changes NO rule):** A+ n 520–760 / 300–435 (the cutoff admits about 3
  a week on average BEFORE the cap; a cap of 3 in fill order on a Poisson-3 week keeps ≈ 2.3, and clustered weeks — 3 to 530 fills
  in 2017–21 — lower it further; the top of the range is 3 × weeks); the A+ median stop width in ADR ≥ C0's (concept 6 pulls toward
  wide opening ranges); weeks with fewer than 3 A+ ≤ 40% after the first 4 weeks of each era; C0 under `pp` reads as published
  (mean R +0.025 / −0.169; ≥ 10R 1.235 / 0.946 per 100); the A+ group's share of bases ≥ 15 sessions ABOVE C0's 39% / 44%
  (the 0.5 rule caps short bases on concept 1 — expected, visible, and a miss changes no rule); among the fills that CARRY the
  reading, the A+ group's median `wk_ratio` and `pb_ratio` below the population's, computed the same way (0.86 / 0.90 and 0.73 /
  0.76 over the carrying fills — the direction the score pulls).
- Chance of a false pass (the null: the A+ set is a random subset of C0 at C0's own rate; approximate — it ignores the week
  structure of the fill-order cap). PASS needs the A+ interval's lower end > 0 (one-sided, ≈ 2.5% under a true zero if the block
  bootstrap is calibrated) AND the outlier bar: a random subset holds Poisson-many ≥ 10R trades, and twice the rate is reached by
  chance with P ≈ 0.2–1.6% across n = 520–760 in 2017–21, ≈ 2.1–8.4% across n = 300–435 in 2022–24 (the peak at n = 317, which
  needs ≥ 6), and ≈ 3.4% (n = 254, needs ≥ 7) to ≈ 8.3% (n = 253, needs ≥ 6) across the confirm read's expected 215–279 (each
  span is the in-range minimum to maximum under the pinned integer thresholds; the integer threshold steps, so the chance is not
  monotone in n). The two are not independent (the outliers pull the mean), so a chance PASS in one era is at most a few per cent;
  RECORD (PASS × PASS) is far under 1%; a chance LEAD (PASS in one era, CAN'T TELL in the other) is a few per cent; beating C0 on
  mean R and the ≥ 5R share makes each rarer. **The paired Δ is NOT part of PASS:** it is a veto ("picks worse", ≈ 2.5% by chance
  per era) and decides only the CAN'T TELL × CAN'T TELL cell, where a chance LEAD needs "separates" in both eras (≈ 0.06%).
- **WOULD-FAIL-IF (a broken implementation) — every check runs (`aplus-read --self-check`, also inside the real run):**
  1. **Look-ahead invariance:** with every minute ≥ 5 of every E file replaced by random values AND every E-day-or-later column
     (`open_E`, `high_E`, `low_E`, `close_E`, `vol_E`, `breakout_vol_x`, every outcome column) shuffled, every score, cutoff and
     A+ flag is identical; AND, PER FILL — for each sampled fill (check 2's 50 plus every A+ fill) — with a copy of the daily
     export in which every ticker's `h`, `l`, `c`, `v` on every row dated after THAT fill's D is randomised (the rows `vol_dry5`,
     `wk_ratio` and `pb_ratio` must never reach — a reader that touched D+1 would pass the column shuffle alone), the fill's
     score, cutoff and flag are identical. One copy for all fills would be wrong: for a ticker with fills at D1 < D2 the rows
     in (D1, D2] lie inside the later fill's own base, so its `wk_ratio`, `pb_ratio` and `vol_dry5` — and its score — legitimately
     change.
  2. **Later-fill removal:** for 50 A+ fills (sampled with seed 702) remove every fill after it in (E, `fill_minute`, ticker) order
     — its score, cutoff and flag are unchanged.
  3. **Population:** check 3 of the data checks; the outcome columns of every A+ row equal the pinned exitpb rows (`realized_r`
     to 1e-9) — read, never re-walked.
  4. **Counts:** A+ unique by (ticker, E); per ISO week A+ = min(N, fills at or above the cutoff that week); never more than N.
  5. **Breakout-day inputs recomputed from the minute files** for every A+ fill: Σ v over minute index 0..4 and max h − min l
     over the present minutes 0..4 equal the stored values; the denominator is the stored `adv20_vol_D` (never recomputed with E's
     volume); the window never reaches the fill minute.
  6. **Pool:** each fill's pool count = the number of population fills with E′ in [E − 20, E − 1] sessions; ≥ 30 for every rated
     fill; every fill's week = the ISO week of its own E (asserted per row).
  7. **Shuffle invariance:** the A+ set is unchanged when the input rows are shuffled (seed 702).
  8. **Golden synthetic fixtures (direction, tie method, denominator) — THREE days, because the boundary flipper cannot live in the
     3-A+ week:** (a) day E: hand-set feature values for a pool of 40 synthetic fills over 20 sessions plus 6 fills on E with known
     oriented percentiles (every scale of concept 1 included, from hand-set daily bars so `wk_ratio` and `pb_ratio` are computed by
     the real code: a base with 3 full blocks and 2 completed pullbacks, one with 2 blocks (weekly missing), one with a single
     completed pullback (pullbacks missing)), a known 12th-highest reference score, exactly 3 A+ in fill order and a 4th
     above-cutoff fill capped; the same inputs with every direction flipped (every scale's too) must invert the A+ set; a fill with
     concept 5 missing must score as the mean of the present concepts (never 0); a fill with a missing SCALE must carry 0.5 for it
     (never 0, never the mean of the present scales); and one grp-missing fill that is rated under the core and unrated under
     +grp, with the two A+ sets differing by it. (b) day E2, its own pool: exactly 30 non-missing values on ONE non-5 concept, so
     every member carrying the value sees 29 once removed and every member without it fails its own-value clause — the reference
     set is EMPTY and every E2 fill reads UNRATED (the effective ≥ 31 floor, stated under the A+ rule); the same pool with a 31st
     value present must rate. (c) day E3, its own pool — the PER-SCALE boundary of concept 1: exactly 30 non-missing values on ONE
     scale (weekly; then the same on pullbacks), every non-5 concept at ≥ 31, so the fill is ranked on that scale (|S| = 30, its
     floor holds) while every reference member carrying the scale sees 29 once removed and enters it as 0.5 (the other scales and
     concepts unaffected); the fill's score, every member's reference score and the cutoff are HAND-COMPUTED and must equal the
     code's; the same pool with a 31st value on that scale ranks the members on it.
  9. **Concept 5 reads nothing after D:** for 50 fills sampled with seed 702 (and every fill of the golden fixtures), `stair_n`
     recomputed from a copy of the watch table in which every row of that ticker with `watch_date > D` carries randomised
     `pole_ci` and `pole_date` is unchanged; and the run with the candidates' `base_id` column DROPPED before any feature is
     computed leaves every `stair_n` unchanged (the column is never read).
  10. **The seal:** during `aplus-read`, any A+ table, score file or verdict file for `holdout` on disk is a broken run (the period
      is not in its `periods`); only `aplus-confirm` may write them, and only after PASS × PASS (data check 7).
  11. **Re-derivation** (data check 6): pandas from the SOURCE files, no runner code — **sorting the cb702 daily export by
      (ticker, date) first** (it is not date-ordered within a ticker: 18,991 of 20,285 tickers, SPY included; a reader that takes
      file order as index order mis-reads the base rows and the session calendar and fails VERDICT MATCH on a non-defect) — and
      recompute every feature (concept 1's three
      scales from the candidates row's `pole_date` / `base_len` and the daily export's base rows, the daily scale also from the
      candidates column; concepts 2–4 from the daily export / candidates; 5 from the ticker's watch rows ≤ D and its candidate
      rows, the chain built at D; 6–7 from the minute files; the alone-row features from candidates / P5), the pool percentiles
      (per scale for concept 1, the 0.5 rule), the reference scores, the cutoffs, the cap, and the A+ SET; MATCH first requires the
      identical (ticker, E) A+ set per era and per N for the core, for +grp and for the reversed-concept-5 row; only then n /
      mean R / interval / the two paired Δs (the core's and +grp's, same seed keys) / every PASS component (≥ 5R share, ADR P&L,
      the ≥ 10R integer comparison and its spread) and the +grp reading (adds / subtracts / can't tell) — VERDICT MATCH before the
      result is written.
  12. **Concept 1's scales recomputed from the export** for every A+ fill and for 200 fills sampled with seed 702: the base rows =
      `base_len` + 1 with `h` at `pole_date` = the watch row's `pole_high`; `wk_ratio` and `pb_ratio` recomputed by the pinned
      formulas equal the stored values (1e-9) and their missing flags equal the stored ones; `tightening_ratio` equals the watch
      row's `range_recent5` ÷ `range_early5` (1e-9); the block ending at D is full and no block reaches past D; the last swing
      high's incomplete pullback is never in `pb_ratio` (a copy with every row after D randomised gives the same two numbers —
      check 1's export clause, asserted here per fill).

## Consequence fixed now

"RECORD" = the forward shadow computes the DECIDING rule at every entry row of ITS OWN copy of the deciding population —
`mi_consolidation_breakout_entry` rows with `k = 'tl'`, `retrigger = 0` (the spec-key first break), `entry_variant = 'orh5'`,
`status = 'filled'`, whose `stop` is the low of the day at the fill (the entry's own stop = the replay's `lod` variant); its pool =
those rows with `break_date` in the prior 20 sessions. The inputs by source: the watch row (`mi_consolidation_breakout_watch`,
joined on ticker and `scan_date = watch_date`) — its `features` JSON for `tightening_ratio` (concept 1's daily scale),
`pole_date`, `pole_high`, `base_len`, `prior_move` (and `range_recent5`, `adr20` for the `range5_adr` beside row), and its
top-level columns `rs_best`, `grp_pct` and `phase_qqq_10_20`; **`mi_daily_closes.high_price`, `low_price` and `close` for the
ticker's rows with `trade_date` in [`pole_date`, D] — the base's bars, from which the recorder computes `wk_ratio` and `pb_ratio`
by the SAME pinned formulas (`high_price` and `low_price` were added by `ALTER TABLE … ADD COLUMN IF NOT EXISTS` after the table
existed (`db.py:911–923`; `close` is the original NOT NULL column), so old rows may be NULL: any NULL `high_price`, `low_price`
or `close` on ANY base row means both scales are missing and the row is flagged, IN ADDITION to the row count (must equal
`base_len` + 1) and `high_price` at `pole_date` (must equal `pole_high`) checks, each of which also makes both scales missing and
flags the row — checked, not assumed)**; `mi_daily_closes.volume` for `vol_dry5` (the
ten sessions ending D) and for `adv20_vol_D` (the mean of the 20 volumes ending D — the shadow stores no ADV today, the recorder
computes it); minutes 0..4 of E from the minutes the entry step already fetches; `stair_n` by the SAME chain-at-D remap as the
read — `cb.chain_bases` over the stored watch rows of the ticker with `scan_date ≤ D` (`pole_ci` = the calendar index of
`pole_date`), the ticker's earlier `k = 'tl'`, `retrigger = 0` entry rows of ANY status and entry variant (filled, no-trigger or
abstain — the read counts candidate rows "filled or not"; the five variant rows of one break share a pole, one base per pole) with
`break_date` in [E − 120, E − 1], mapped through it by their own poles (NOT their stored `base_id`, which each night stamped on
that night's chain) — unrated for its first 120 sessions, the pool thin for its first 20. It stores on the entry
row the score, the cutoff, the pool size, the seven concepts' inputs (nine numbers: the three scale readings of concept 1 with
their missing flags, `vol_dry5`, `rs_best`, `prior_move`, `stair_n`, `range_open5_adr`, `open_drive`), the week's A+ count and
the flag (new columns), plus the +grp score, cutoff and flag beside if +grp's consequence fires: a recorder change inside (c), no
order path, no money. **Paper is a proposal TO HIM only after the sealed 2025–26 read PASSES; live is his sign-off (THE
LINE).** The step that applies this table is `aplus-verdict`, run only when both verdict files exist.

| 2017–21 \ 2022–24 | **PASS** | **CAN'T TELL** | **FAIL** |
|---|---|---|---|
| **PASS** | RECORD; then the sealed 2025–26 read ONCE under the deciding rule (`aplus-confirm`, data check 7) — PASS there → a paper proposal to him; else "recorded, not confirmed" | LEAD (recorded, no claim) | not recorded |
| **CAN'T TELL** | LEAD (recorded, no claim) | LEAD only if the paired bar reads "separates" in BOTH eras; else not recorded | not recorded |
| **FAIL** | not recorded | not recorded | not recorded |

- **Precedence:** (1) the paired bar reading "picks worse" in EITHER era → not recorded, whatever the cell; (2) the cell; (3)
  "separates" promotes nothing beyond the cell except in the CAN'T TELL × CAN'T TELL cell. A FAIL in one decade beats a PASS in
  the other: a fixed score that selects in one era and not the other is not a selection rule.
- **Not recorded → the next registration is NAMED NOW:** among the SEVEN core concepts' alone rows ONLY (`alone_c1` … `alone_c7`;
  never a scale-alone row, never `base_len` — RULED never deciding — nor `range5_adr`, `base_depth`, `atr14_slope`, `rs_all`), the
  one with the highest mean over the two eras of ≥ 10R per 100 that also meets the 3-ticker / 3-month spread in both; ties →
  the higher two-era mean R, then the lower concept number; it is registered on its own and tested on the still-sealed 2025–26
  (unread for THIS score only — Disclosed (d)). If no eligible row meets it, the rating does not select on these ingredients —
  reported to him with the alone table, and no further read on these eras.
- `+grp`'s verdict decides only whether the shadow records the +grp score beside the deciding one (its consequence above); it, the
  phase split, the reversed-concept-5 row and the HINDSIGHT rows decide nothing in any cell.

## What the read may NOT do

- Switch N, the 20-session window, the pool floor, the member rule, the cutoff rule, the cap order, the tie-break, the week rule,
  an ingredient or a direction, the seed, the draw count, the n floor, the open-mark rule or the +grp recipe — after this
  registration, for any reason. Settle a "Put to him" item AFTER the freeze (his six answers go into the freeze commit, before the
  pins are taken; a "no" reopens the row for a re-spec and a recheck first — never a line edit). Compute any A+ row on 2025–26
  before the consequence table calls for it. Read the hindsight file before both verdict files exist. Run a period twice. Edit
  this document above the marker after the freeze commit. A side row (N = 1 / 5, `+grp` beyond its recording consequence, the
  core with concept 5 reversed, an alone row or a scale-alone row, the HINDSIGHT top-N) is never a finding.

## What this does not answer

- Whether his A+ is these ingredients at all (how he reads a chart); weights other than equal; the entry and the stop (held at
  ORH5 + low of day — concept 6 is read knowing it sits near the stop width); the intraday scale of his fractal (not available
  before the fill); survivorship in 2017–21 (Alpaca's symbol list);
  themes (forward only); sizing, slots, turnover.

## Revisions 2026-10-22 (the review of the 10-21 draft; every finding, what changed)

1. **Blocker — the flag looked ahead (within-week rank).** FIXED: the rank is against the prior 20 sessions' fills, the cutoff
   admits ~3 a week, the weekly cap runs in fill order; the within-week top-N is the HINDSIGHT row; the shadow records the
   deciding rule; WOULD-FAIL-IF 1–2 test it.
2. **Consequence rows overlapped.** FIXED: one table over (2017–21 × 2022–24) with precedence stated.
3. **Ingredients differed from his ruling.** FIXED: the stair-step is an ingredient (direction = placeholder, filled before the
   freeze), range-so-far kept with the stop-width caveat, volume dry-up and base length added, `base_depth` / `atr14_slope` / the
   phase moved out; every deviation listed with its reason.
4. **The tail condition did nothing at this n.** FIXED: the outlier bar (≥ 2 × C0's ≥ 10R rate plus the 3 / 3 spread) is in PASS.
5. **Inputs unnamed / unpinned.** FIXED: the input table (file · column · join key); the P5 and watch tables added to the pins;
   `adv20_vol_D` named; themes forward-only (no `mi_themes` read); the 39 listed in full.
6. **Open choices.** FIXED: the percentile formula, ties, the week rule and the edge weeks, open marks, missing minutes, the
   paired recipe and its seed key, `grp_pct` on the present subset — all pinned.
7. **Stair-step underspecified and truncated.** FIXED: fully defined (K, `retrigger`, distinct `base_id`, filled or not, the SPY
   calendar window); fills with a truncated window are unrated on that concept and counted (505 / 1,778). Direction: the
   placeholder, per the main loop (his ruling pending), not "both ways".
8. **Re-derivation not independent.** FIXED: it recomputes features, ranks, cutoffs and the A+ set from the source files; MATCH
   requires the identical set first.
9. **`atr14_slope` direction wrong.** FIXED: described as a ratio, lower = tighter; it is out of the core (an alone row); the
   golden week tests every direction.
10. **WOULD-FAIL-IF not runnable.** FIXED: eleven executable checks, including the arm / entry / K filter, week-by-E, NaN-never-0,
    the stored `adv20_vol_D`, the minute window.
11. **2025–26 spent, the next ingredient picked ad hoc.** FIXED: 2025–26 SEALED (no A+ row computed; the confirmation set, read
    only by `aplus-confirm` after PASS × PASS); the alone rows are the pre-named table and the selection rule for the next
    registration is written down.
12. **Counts mixed units / rows outside the ranges.** FIXED: the per-period table (fills, open marks, mature, weeks, the edge rule:
    the 9 fills of 2022-01-03 dropped, the 28 of 2025-01-02 kept, the 23 of 2025-01-03 excluded from the sealed era); the weekly
    counts corrected in Why.
13. **Two near-empty secondaries.** FIXED: `+grp` read on the grp-present subset with the share; the phase is a split, not a rank.
14. **"Unfitted" left out what was read.** FIXED: the Disclosed bullet (the tightest-fifth finding, the selection test, the
    published C0 numbers, `rs_best` vs `rs_all`); contraction is ONE concept at 1/8.
15. **Hindsight ordering, the combining step, the volume-source mix.** FIXED: the hindsight file refuses until both verdict files
    exist; `aplus-verdict` is the combining step; `open_drive` described as a rank input over mixed sources.
- Rejected: none. Chosen among the review's alternatives: SEAL 2025–26 (not a third deciding era — it keeps one unread set for
  whatever this read leads to); the explicit mid-rank formula instead of a pandas call (defined for the fill-against-pool case).

## Second revision 2026-10-22 (the recheck of the revision above; 10 findings, what changed)

1. **The stair-step direction was still a placeholder though his lean was on file (commit `914b3c1d`, PLAN #705, the shared notes
   §2026-10-22).** FIXED: the cell reads lower = fewer prior bases = EARLIER = better, his words quoted with his uncertainty; the
   reversed orientation is a side row (reported, never a finding); the deviations row says RULED; the placeholder, check 9's
   placeholder clause and the freeze-record clause are gone; the direction is no longer an ask. Revisions 3 and 7 above are history.
2. **`+grp` had no bar, no verdict, no consequence — DoD (2) could not be met.** FIXED: the recipe (grp-missing = unrated under
   +grp; the same pool, member rule, cutoff, cap and week rule run as a second complete rule), the paired bar vs the core A+ on the
   grp-present subset with its own key `aplus_pair_grp|<period>|3`, the reading adds / subtracts / can't tell, the consequence
   (adds in BOTH eras AND core RECORD → the shadow records the +grp score beside; the deciding rule never changes), the MATCH list.
3. **Outlier-bar numbers not pinned.** FIXED: ≥ 2.47 / 1.89 / 2.36 per 100 (unrounded, each shown as 2 × the published count ÷
   mature n); the ≥ 10R rate counts ALL widths; the 3-ticker / 3-month spread counts stops ≥ 0.25 ADR20 only; C0 = the published
   mature rows (13,363 / 8,984 / 7,531, edge fills included — one choice) with its mean R and ≥ 5R numbers written out.
4. **The chance paragraph described a rule PASS does not contain.** FIXED: the null stated; the interval and the outlier bar are
   the tested parts (Poisson arithmetic per era and n); the paired Δ is a veto and the CAN'T TELL × CAN'T TELL decider only.
5. **`stair_n` read later watch nights through the pre-stamped `base_id`.** FIXED: the chain is built at D over the watch rows
   ≤ D and every row is remapped through it; `base_id` is never read; the full-file chain's 1-of-22,357 difference (AMRSQ) is
   disclosed; check 9 is the randomise-after-D invariance plus the dropped-column run; the shadow computes it the same way.
6. **Equality targets for the confirm read unpinned.** FIXED: 7,547 fills / 93 weeks / 39 open / 7,508 mature after the exclusion,
   in the table and in check 3; the C0 baseline is the published row, stated once.
7. **"Rated pool member" undefined.** FIXED: pinned (own values present; ≥ 30 in the pool minus the member; concept 6 by its own
   floor; scored against E's pool, never its own window); the golden week holds a boundary-flipping member.
8. **The RECORD spec did not match the shadow.** FIXED: the population pinned to `k = tl`, `retrigger = 0`, `orh5`, `filled`, the
   `lod` stop; every input named by its real source (`features` JSON vs top-level watch columns vs `mi_daily_closes.volume`;
   `adv20_vol_D` computed by the recorder); `stair_n` by the same chain-at-D remap, not the stored `base_id`.
9. **The deviations from his 10-21 ruling were not in the ask.** FIXED: ONE "Put to him before the freeze" block, six lines
   (base-length direction, range so far at ORH5, phase as a split, themes forward-only, `rs_best`, the two dropped features);
   `grp_pct` is out of it (it has a bar), the stair step is out of it (ruled).
10. **"Its first unread data" overstated 2025–26.** FIXED: Disclosed (d) lists what has been read there; the wording is "unread
    for THIS score only".
- Rejected: none. Chosen: the +grp rule as a second complete run (not grp bolted onto the core's cutoff) so the two A+ sets are
  like for like; the chain-at-D remap (not the shadow's stored own-night `base_id`) so the read and the recorder compute one number.

## Third revision 2026-10-22 (his two rulings committed after the second revision — `3378fd5b` 07:53, `71d71f46` 07:57, the doc
was saved 07:53:19 — and the recheck's remaining findings; what changed. The two revision blocks above are history and keep the
OLD numbering, where the stair step was concept 6; the body above the marker is the current one.)

1. **Base length sat in the DECIDING score and was still an ask, though RULED out.** FIXED: `base_len` is out of the core (seven
   concepts, weight 1/7; +grp 1/8), an alone row beside, never deciding, and NOT a next-registration candidate; the deviations row
   quotes his words; ask 1 (base length) is gone. **Market phase as a split was answered "Ok" and still asked.** FIXED: RULED in
   the phase bullet and the deviations row; ask 3 is gone.
2. **Contraction had only daily-scale inputs (`tightening_ratio` + the level `range5_adr`) against his fractal ruling.** FIXED:
   concept 1 = three scales inside one concept, each to the standard of the other inputs — file · column · formula · direction ·
   missing rule · pool floor: WEEKLY `wk_ratio` (5-session blocks counted back from D across the whole base, the later half of
   blocks over the earlier half, ≥ 3 full blocks else missing — no partial block exists, so the current calendar week never
   counts partially), DAILY `tightening_ratio` (unchanged), PULLBACKS `pb_ratio` (5-bar swing highs from the pole top, completed
   pullbacks only, last ÷ first, ≥ 2 else missing); intraday stated unavailable before the fill. ONE combining rule: the mean of
   the three scale percentiles, a missing scale 0.5 (the reason written in the block; a count rejected — it needs a per-scale
   threshold, a hard rule he said it is not). `range5_adr` (a level) → an alone row; `atr14_slope` → an alone row for a mechanical
   reason (its denominator is the pole's ATR, code line 690), no longer an ask; `base_depth` not his list, no longer an ask.
   Measured, features only, on the pinned tables (no outcome read): weekly present for 5,166 / 3,919 fills, pullbacks for 5,713 /
   4,138, the per-scale floor strips 346 / 79 and 234 / 49; the base-row count equals `base_len` + 1 for every fill in both eras;
   the median base is 12–13 sessions and 61% / 56% of fills are 10–14 sessions — which is why a weekly rule needing three
   blocks leaves most fills on 0.5 for that scale, disclosed as an expectation (the A+ group's share of ≥ 15-session bases above
   C0's).
3. **Concept count, weights, numbering, Disclosed, inputs, RECORD, checks.** FIXED: seven concepts (1 contraction, 2 volume
   dry-up, 3 RS, 4 prior move, 5 stair step, 6 range so far, 7 volume so far); every "concept 6/7/8" reference renumbered;
   Disclosed (a) names both 10-18 measures and says the weekly and pullback scales have never been read against an outcome; the
   input table carries the base's export rows (h, l, c over [`pole_date`, D]) and the watch cross-checks (`range_early5`,
   `pole_high`); the RECORD inputs name `mi_daily_closes.high_price` / `low_price` / `close` for the base's bars with the
   NULL-on-old-rows guard; the per-scale counts are STEP 0 equality targets (check 2) and check 3 carries the missing rules and
   the base-row equality; check 1 randomises the export after D (a reader touching D+1 would pass the column shuffle alone);
   check 8 tests a missing scale = 0.5 and every scale's direction; check 11's recompute list is the new numbering; NEW check 12
   recomputes the scales per fill. The three scale-alone rows and the `base_len` / `range5_adr` alone rows are reported beside.
4. **The minors.** FIXED: a "no" on any ask reopens the row for a re-spec + recheck before the freeze (the freeze carries only
   "yes" or re-reviewed rows) — written in the ask block and in "may NOT do"; the boundary flipper is its own fixture (day E2,
   an empty reference set, every fill unrated) and the effective ≥ 31 floor is stated once under the A+ rule; the outlier bar is
   three integer comparisons (count_ge10 × 13,363 ≥ 2 × 165 × n, × 8,984 ≥ 2 × 85 × n, × 7,531 ≥ 2 × 89 × n) with the per-100
   figures labelled display roundings and the 7-of-370 counter-example; +grp's consequence is pinned to "whenever the core is
   recorded (RECORD or LEAD)"; the count bases are one basis (joined 13,368 → 13,359 after the drop; grp-present 9,059 of
   13,359); the bootstrap `<score>` / `<period>` / `<N>` tokens are literal; the next-registration set is the seven core alone
   rows with a tie-break; the confirm read's expected A+ n is 215–279 and its chance figure a span (≈ 5% at n = 279, ≈ 9% at
   n = 200).
5. **The asks are now this doc's own mappings only (six):** pullbacks as the third scale by the pinned swing rule (his "etc.");
   a missing scale = 0.5 (vs the mean of the present scales); `range5_adr` out of the core; range so far at ORH5; themes
   forward-only; `rs_best`. Ruled items (stair-step direction, base length, phase, fractal) are not re-asked.
- Rejected: weekly blocks anchored at the pole top with the trailing partial block folded into the last (a 6–9-session last
  block has a mechanically larger envelope — the latest sessions must sit in a full block); the weekly reading over the same two
  5-session windows as the daily ratio (always present, but the same ten sessions twice for the 56–61% of fills with a 10–14-session
  base — not a second scale); interior-only pullbacks (coverage falls to 25% / 29%; the pole top is the first swing high a
  trader reads, VCP-style — the `base_depth` overlap is disclosed instead); a count of contracting scales (threshold + ties).
  Chosen: the mean of the scale percentiles with 0.5 for a missing scale — the one rule under which "visible at more scales"
  ranks higher without rewarding length by itself.

Fourth pass 2026-10-22: the third recheck's minors applied.

<!-- FREEZE -->
## Freeze record

The doc body pin covers every byte above the `<!-- FREEZE -->` marker; the six "Put to him before the freeze" items are settled (his
yes / no written into the rows they name; a "no" re-specs and rechecks the row first) before the pin is taken. Pins (sha256) printed by `aplus-read --print-pins` and pasted here in the commit that precedes the run; the RESULT is
appended below this record. Pinned: `cb702/out/trades_discovery_exitpb.tsv.gz`, `cb702_pre/out/trades_pre_exitpb.tsv.gz`,
`cb702/out/trades_holdout_exitpb.tsv.gz` (sealed — pinned so the later confirmation read runs on the same bytes),
`cb702/out/trades_discovery_p5.tsv.gz`, `cb702_pre/out/trades_pre_p5.tsv.gz`, `cb702/out/trades_holdout_p5.tsv.gz`,
`cb702/out/candidates.tsv`, `cb702_pre/out/candidates_tl_com.tsv`, `cb702/out/watch.tsv.gz`, `cb702_pre/out/watch_tl_com.tsv.gz`,
`cb702/daily_closes_all.csv.gz`, `cb702_pre/daily_closes_all.csv.gz`, `cb702/minutes/_done.psv`, `cb702_pre/minutes/_done.psv`,
the two minute trees, the module, the runner, the scaffold (`registered_read.py`), the doc body.
