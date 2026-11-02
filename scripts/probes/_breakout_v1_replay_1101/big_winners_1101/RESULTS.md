# The big winners of 2017–2024 vs breakout v1 — how many fit, which rule kept the rest out, what the fits share (2026-11-01)

**Descriptive only. $0, local data, no network, nothing live changes; no rule is proposed to move (THE LINE). Nothing dated 2025-01-01
or later was read. Every trade outcome is the frozen replay's (`../out/trades.tsv.gz`); this study computed no new outcome.** The
definitions were fixed in `PLAN.md` before any count. R = profit per share divided by risk per share (the buy price minus the stop).

His ask: *"looking at the biggest winners over that period, of which how many fit our criteria vs those that don't, and of those that do is
there some common features... study 1000s of winners, patterns and internalize what big winners look like."* The winners database he asked
for is `big_winners_2017_2024.tsv` (9,212 rows: 1,626 stocks that doubled, 7,586 that gained 50%; one row each with its dates, move,
v1 status, the gate that kept it out, and 130 columns of features). Every table below is in `out/tables.md` with its n.

## 1. The answer in plain words (the +100% set: 1,626 stocks that at least doubled from a low within three months)

- **One in three fit; the uncapped walk would have bought one in five, the 5-slot paper book took one in twenty.** v1 listed **528 (32%)**
  on some night between the low and the half-way point of the move. Walking EVERY list name (no position cap): bought **305 (19%)**, the
  first buy made money on **144 (9%)**, ≥ 3R on **45 (3%)**, ≥ 10R on 19, **90 (6%)** still held when the stock had made half its move.
  The PRIMARY 5-slot book — the lane as it actually runs — took **83 (5%)** of them, made money on 40 (2%), ≥ 3R on 14 (1%), ≥ 10R on 6,
  still in at half-way 31 (2%); counting any later fill, some fill took a slot on 133 (8%).
- **The two in three never listed were kept out by RS, then by the pole.** On the night before their breakout, **95% were below the 98th RS
  percentile** (their median RS 79; only 8% were even at 97); **53% had no 30% prior move**; 38% were not riding a moving average (surf);
  29% were not tightening. 18% failed ONLY the RS gate. Over the whole window the nearest miss was RS alone on 39%, RS + prior move on 22%.
  In plain words: **big winners mostly start from a decline** (the never-listed were down a median 42% over the three months into their
  low; the fits were down 15% or up) — they are not yet in the top 2% of relative strength when they break out; RS catches up later.
- **The fits that made money look the same as the fits that lost on the night they were bought** — same prior move (0.84 vs 1.02), same base
  age (14 vs 18 sessions), same tightening (0.81 vs 0.83), same surf (8 vs 8), same RS (99 vs 99), same stop width (4.0% vs 3.7%). **What
  differs is the breakout day itself**: the winners' day ran 1.63× the 50-day volume vs 1.23×, a range of 1.14 ADR vs 0.95, and closed at
  75% of its range vs 49% — the day's own action, not knowable at the buy. The winners were also bought later: a median 8 calendar days after
  the stock's first measurable breakout vs 2 for the losers; the ≥ 3R catches 15 days after.
- **The 5-slot book's slots were already full when the biggest catches came.** Of the 45 catches that made ≥ 3R, only **14 took a slot**;
  of the 31 that did not, 30 were refused because the five slots were full (`block:max_positions`) and 1 because the book already held
  that ticker. TSLA (+53R), RKLB (+47R), SOL (+28R), PACB (+28R), ALT (+25R), GOTU (+18R), SMR (+17R), FCEL (+16R) all came while the
  slots were full (the book fills day → minute → rank, so an earlier fill holds the slot; who held them was not read here). This is the
  observation behind the slot-order test he OK'd on 11-01; nothing is decided here.
- **2020 holds 889 of the 1,184 winners of 2017–21 and v1 listed only 21% of them** (crash-recovery winners start under every average, with
  no pole); every other year listed 36–67%.
- **Action: none from this data.** The gates that keep out the most winners (RS ≥ 98, the 30% pole) are the same gates that keep out every
  loser that looks like them — this read measures recall only, never precision. Which gate is a rule question is his.

## 2. The funnel (+100% set; the +50% set beside)

| step | 2017–21 | 2022–24 | all +100% | all +50% |
|---|---|---|---|---|
| big winners | 1,184 | 442 | **1,626** | 7,586 |
| LISTED on some night from the low to the half-way point ("fits the criteria") | 341 (29%) | 187 (42%) | **528 (32%)** | 1,270 (17%) |
| … FIRED: the next day cleared the level on ≥ 1.2× volume (daily bars) | 204 (17%) | 110 (25%) | 314 (19%) | 636 (8%) |
| … FILLED: the minute walk bought it | 205 (17%) | 100 (23%) | **305 (19%)** | 627 (8%) |
| … the catch took one of the 5 slots in the primary capped book (the lane as it runs)¹ | 54 (5%) | 29 (7%) | 83 (5%) | 179 (2%) |
| … some fill (not only the first) took a slot | — | — | 133 (8%) | 259 (3%) |
| … the catch MADE MONEY (R at 2c > 0) | 101 (9%) | 43 (10%) | **144 (9%)** | 284 (4%) |
| … the catch made ≥ 3R | 27 (2%) | 18 (4%) | **45 (3%)** | 75 (1%) |
| … the catch made ≥ 10R | 13 (1%) | 6 (1%) | 19 (1%) | 26 (0%) |
| … the catch was still in the trade at the half-way point | 61 (5%) | 29 (7%) | 90 (6%) | 220 (3%) |
| … some fill (not only the first) still in at the half-way point | 115 (10%) | 54 (12%) | 169 (10%) | 350 (5%) |
| listed anywhere from 28 calendar days before the low to the peak (loose cross-check; 20 sessions approximated) | 560 (47%) | 350 (79%) | 910 (56%) | — |

¹ The rows below LISTED are each a share of ALL big winners, and FIRED → FILLED is NOT nested: 42 filled winners (121 in the +50% set) were
bought on a night whose daily bar did not clear level + 1.2× volume — the minute walk's own pace rule bought them — and 51 (130) fired on
daily bars without the minute walk buying. The "made money / ≥ 3R / still in" rows are of the FIRST fill of every filled winner (the
uncapped walk); the primary 5-slot book's own results on the 83 it took: made money 40, ≥ 3R 14, ≥ 10R 6, still in at half-way 31, mean
R +1.14 (the +50% set's 179: 73, 20, 7, 61, +0.56).

The catches (the first filled night): median R at 2c −1.00 (quartiles −1.06 .. +0.65), mean +1.43 (n = 305); exits: stopped day 0 116,
stopped 112, trailed 65, time exit 11; sessions held median 1; the stop a median 3.8% under the buy; list rank that night median 16. A
listed winner was on the list a median 5 nights in its window; a filled winner was bought a median 2 times (summing R over every fill:
median −0.00, quartiles −1.06 .. +4.08).

By breakout class: measurable breakouts (872) listed 44%, bought 26%, made money 13%; late bases (592) listed 17%, bought 8%, made money
3%; gap starts (150) listed 29%, bought 16%, made money 7%.

## 3. Never listed (1,098 of 1,626): which gate kept it out — on the night before the breakout

Every gate is evaluated on every night (no short-circuit), so a winner can fail several. Anchor night = the night before the 10-22
breakout day (b − 1) for 1,081 (97 of them gap starts that also had a base breakout later); the night before the gap for the 9 gap starts
with no base breakout; s25 − 1 for 8 (no consolidation / other).

| gate (what v1 demands) | 2017–21 (n = 843) | 2022–24 (n = 255) | all (n = 1,098) | +50% set (n = 6,316) |
|---|---|---|---|---|
| **rs** — top 2% of relative strength (best of 1/3/6 months) | 814 (97%) | 233 (91%) | **1,047 (95%)** | 97% |
| **prior_move** — a 30% pole in the last 10–45 sessions | 463 (55%) | 123 (48%) | **586 (53%)** | 59% |
| **surf** — 5 sessions riding a 10/20/50-day line | 304 (36%) | 112 (44%) | 416 (38%) | 42% |
| **tightening** — last-5 range ≤ 1.1× the prior 5 | 217 (26%) | 97 (38%) | 314 (29%) | 31% |
| higher_lows | 59 (7%) | 44 (17%) | 103 (9%) | 11% |
| breakdown | 31 (4%) | 28 (11%) | 59 (5%) | 7% |
| universe ($2 raw, $5M) | 5 (1%) | 11 (4%) | 16 (1%) | 1% |
| history | 0 | 0 | 0 | 0% |
| gates failed per winner (median, quartiles) | 2 (2 .. 3) | 2 (2 .. 3) | 2 (2 .. 3) | — |
| fails ONLY the rs gate (every structure gate passes) | 154 (18%) | 42 (16%) | 196 (18%) | 15% |
| RS percentile ≥ 90 / ≥ 95 / ≥ 97 | 26% / 12% / 6% | 41% / 27% / 15% | 29% / 15% / 8% | 29% / 13% / 7% |

First failing gate in v1's own order: rs 1,031 (94%), universe 16, surf 13, prior_move 12, higher_lows 11, tightening 7, breakdown 1; 7
passed every gate on the anchor night but that night fell AFTER the half-way point (5 gap starts, 2 late bases — the list did hold them,
too late to count). **Nearest miss over the whole window** (the night with the fewest failing gates): rs alone 429 (39%), two gates 355
(32%; rs + prior_move 244, rs + surf 38, prior_move + surf 27, surf + tightening 25), surf alone 116 (11%), prior_move alone 62 (6%),
tightening alone 32, three gates 61. Over the window's nights the rs gate failed on a median 100% of a never-listed winner's nights,
prior_move 54%, surf 59%, tightening 34%, breakdown 22%, higher_lows 21%.

## 4. What the fits share — features at the night before the breakout, by status (median, quartiles; n in `out/tables.md`)

| feature | never listed (1,098) | listed, never fired (172) | fired, not filled (51) | filled: lost (161) | filled: made money (144) |
|---|---|---|---|---|---|
| prior move: pole high / pole low − 1 | 0.27 (0.15 .. 0.53) | 0.50 (0.32 .. 0.97) | 0.48 (0.34 .. 0.88) | 0.77 (0.44 .. 1.61) | 0.77 (0.44 .. 1.67) |
| v1 base age: sessions since the pole top | 41 (33 .. 44) | 37 (23 .. 44) | 29 (16 .. 38) | 31 (18 .. 41) | 24 (14 .. 40) |
| 10-22 base length, sessions | 24 (15 .. 37) | 28 (20 .. 40) | 27 (18 .. 41) | 26 (18 .. 39) | 26 (16 .. 39) |
| 10-22 base depth, % | 29 (23 .. 36) | 29 (23 .. 35) | 26 (21 .. 32) | 31 (24 .. 42) | 32 (24 .. 41) |
| tightening ratio (v1 ≤ 1.1) | 0.95 (0.79 .. 1.14) | 1.02 (0.81 .. 1.24) | 0.86 (0.77 .. 1.00) | 0.98 (0.77 .. 1.20) | 0.93 (0.80 .. 1.16) |
| surf run, sessions (v1 ≥ 5) | 6 (3 .. 12) | 7 (3 .. 13) | 6 (4 .. 9) | 7 (3 .. 13) | 6 (4 .. 11) |
| RS percentile, best of 1/3/6 mo (v1 ≥ 98) | **79 (46 .. 92)** | 94 (80 .. 98) | 94 (85 .. 99) | 98 (95 .. 99) | 99 (94 .. 100) |
| 1-month return, % | 7 (−6 .. 18) | 11 (0 .. 21) | 10 (1 .. 24) | 13 (2 .. 35) | 20 (6 .. 48) |
| 3-month return, % | **−22 (−39 .. 2)** | −3 (−19 .. 27) | 17 (0 .. 34) | 23 (−1 .. 98) | 27 (−3 .. 108) |
| 6-month return, % | −20 (−42 .. 16) | 15 (−25 .. 78) | 35 (−8 .. 71) | 67 (15 .. 147) | 69 (2 .. 158) |
| 63-session return INTO the low, % | **−42 (−61 .. −15)** | −15 (−35 .. 24) | 4 (−13 .. 32) | 12 (−18 .. 81) | 14 (−17 .. 79) |
| ADR20, fraction of price | 0.074 | 0.066 | 0.059 | 0.076 | 0.081 |
| RAW close, $ | 20.5 (11.1 .. 39.8) | 21.2 (10.7 .. 33.7) | 20.6 (8.3 .. 34.9) | 15.7 (9.3 .. 31.9) | 13.3 (7.9 .. 31.1) |
| 20-day median dollar volume, $M | 29 (15 .. 76) | 19 (11 .. 44) | 21 (12 .. 40) | 30 (14 .. 91) | 26 (14 .. 82) |
| next day's volume over its 50-day mean | 1.28 (0.90 .. 2.19) | 1.34 (0.85 .. 2.76) | 1.54 (0.90 .. 2.54) | 1.80 (1.15 .. 2.91) | 1.70 (1.13 .. 3.43) |
| next day's gap at the open, % | 2.7 (0.9 .. 5.5) | 1.4 (0.2 .. 4.6) | 1.5 (0.2 .. 3.5) | 2.1 (0.4 .. 5.1) | 1.3 (0.1 .. 4.1) |
| next day's range, ADR units | 1.10 (0.75 .. 1.70) | 1.32 (0.94 .. 1.93) | 1.30 (0.99 .. 2.04) | 1.42 (1.10 .. 2.09) | 1.42 (1.03 .. 1.89) |
| gain low → peak, % | 131 (112 .. 170) | 146 (116 .. 197) | 139 (117 .. 192) | 168 (125 .. 258) | 194 (140 .. 306) |
| v1 prior-move gate passes | 47% | 77% | 84% | 88% | 90% |
| v1 RS gate passes | 5% | 23% | 29% | 52% | 60% |
| the 10-22 base contains the low | 59% | 76% | 86% | 82% | 84% |
| QQQ above its 50-day | 69% | 73% | 75% | 73% | 70% |

**At the catch's own night (filled winners): made money vs lost vs ≥ 3R** — prior move 0.84 / 1.02 / 0.75; base age 14 / 18 / 15 sessions;
tightening 0.81 / 0.83 / 0.82; surf 8 / 8 / 8; RS 99 / 99 / 99; 6-month return 97% / 84% / **115%**; stop width 4.0% / 3.7% / 3.7%; list
rank 14 / 17 / 15; **next day's volume 1.63× / 1.23× / 1.66×; range 1.14 / 0.95 / 1.18 ADR; close location 0.75 / 0.49 / 0.76**; bought
+8 / +2 / **+15** calendar days after the first measurable breakout; the eventual move 194% / 168% / 212%. QQQ above its 50-day 77% / 78% /
82%; took a slot 28% / 27% / 31%.

**Sector** (2-digit SIC, a 2026 point-in-time file; 22% of the winners — mostly delisted names — have no row): pharma / biotech is 17% of
the winners and 23% of the fits; software 9% of the winners and 6% of the fits; semis 6% / 6%; credit (the bitcoin miners sit here) 4% / 5%;
oil & gas 3% / 5%. **Market phase:** QQQ was above its 50-day on 70% of the anchor nights and the share is the same in every group (69–75%);
the replay's 10/20 phase likewise (56–65%).

**By year** (+100%): listed / bought / made money — 2017: 58% / 33% / 14%; 2018: 67% / 38% / 22%; 2019: 50% / 30% / 15%; **2020: 21% / 12% /
6%** (889 winners); 2021: 48% / 31% / 18%; 2022: 36% / 19% / 10%; 2023: 45% / 22% / 5%; 2024: 47% / 28% / 14%.

**The 30 biggest moves** (`out/tables.md`, last table of each set): RIOT +1,384% bought and stopped (−1.04R); W +1,356% never listed (no 30%
pole, not surfing); FLNA +1,195% never listed (RS); NXH, MGNI, VKTX, BLNK, IONQ, LVGO bought and stopped at −1R; DDD, FSLY, MARA (+3.2R),
IMMU, NVAX, PACB (+27.7R), CVNA, AMC, TNDM bought and made money; MSTR 2020 and RUN never listed (RS); TLRY and JMIA listed but never fired.

## 5. What this does not answer

- **Precision.** The gates that lose the most winners (RS ≥ 98, the 30% pole) also reject every loser that resembles them; a gate that admitted
  the never-listed winners would admit an unmeasured number of losers. Only a registered replay of a changed rule can say what it pays, and
  the rule is his.
- **The features are descriptive, in-sample and unadjusted for the gates.** A fit's prior move is higher than a non-fit's partly BECAUSE
  v1 demands a pole; "made money vs lost" differs mainly on the breakout day's own volume, range and close — facts that exist only after the
  buy. No feature here separates winners from losers at the buy; the next-day numbers describe what a working breakout looked like, not a
  filter.
- **Survivorship.** The export is the rebuilt survivorship-corrected one, but 22% of the winners have no sector row (names since delisted),
  and the early-2022 seam (troughs in 2022-Q1 whose peak extension crossed the pre-2022 store's end, 44 of them) under-measures the gain.
- **2017–21 is 75% a 2020 story** (889 of 1,184 troughs); the by-year table is there for that reason.
- **The +100%-within-63-sessions definition** misses slower doublers and stocks whose low sat under the $5 universe floor (the 10-22 study's
  own caveat; unchanged).
- **The window (low → half-way point)** makes a gap-start winner's window two or three nights long — the gap made the move; such a winner
  listed on a later base night (7 cases) counts as never listed in the window and is named as such.

## 6. Verification (run before any number above was written)

- **The gate call IS v1, not a lookalike:** on every one of the **232,394 winner-nights** my call (the replay's own pool, cross-section and the
  live `v1_gates`) passes ⇔ the replay's list file holds the name: **0 + 0 disagreements** (8,052 agree-pass, 224,292 agree-fail). My
  daily-bar "fired" flag equals the replay's coverage flag on every listed night (314 vs 314 winners, 0 disagreements).
- **The population reproduces the 10-22 v2 rerun:** restricted to its trough window, 1,180 of its 1,181 +100% episodes are identical
  (ticker, trough, gain, class); the one missing (AAOI 2017-04) and the 33 / 3 +50% differences are tickers whose scan start moved because
  this run's window begins 2017-01-03 rather than 03-01 or ends 2022-03-31 rather than 2021-12-31 (the non-overlapping scan is
  path-dependent on its window; all 36 explained by a tail episode or a trough re-anchored across the old window end).
- **Independent recount** of listed / filled / made money / ≥ 3R straight from the replay's list and trades files by date window, without
  the step-2 rows: 528 / 305 / 144 / 45 (+100%) and 1,270 / 627 / 284 / 75 (+50%) — equal to the tables.
- **Raw-export hand check** of two anchor nights (W 2020-04-16: prior move 0.189, surf 2, tightening 0.764; MSTR 2020-09-14: 0.335, 1, 0.728)
  built from the gz export without the store loader — equal to the stored rows.
- **Seal:** the cb702 daily copy was stream-filtered on its date column (8,619,626 rows kept, 5,210,943 dropped unparsed); 3,090 split rows
  dated ≥ 2025 skipped on their date; the regime rows of `small_pulls.psv` (dated 2025+) never read. The security-type and sector files
  (`cb702_sic.psv`, the `sectype` rows of `small_pulls.psv`, the committed ETV name list) are static classifications stamped 2026-10-16 /
  2026-10-28 — point-in-time labels, not market data, used exactly as the 10-22 study and the replay used them (declared). No `*_holdout*`
  file opened; no network; no subagent.

## 7. Files

`PLAN.md` (definitions, written first) · `00_seal.py` (the sealed inputs) · `01_episodes.py` (+ `01_episodes_A.txt`, `01_episodes_B.txt`,
`01_run.log`) · `02_v1_nights.py` (+ `02_run.log`; `out/v1_nights.tsv.gz` = 232,394 winner-nights with the full gate vector; `out/qqq_nights.tsv`)
· `03_tables.py` (+ `03_run.log`; `out/tables.md` every table, `out/numbers.json`) · **`big_winners_2017_2024.tsv`** (9,212 winners × 130
columns) · `out/episodes_all.tsv.gz`, `out/wrecall_episodes_{A,B}_{x200,x150}.tsv.gz` (the episode tables). Scratch:
`scratchpad/Cfollow/big_winners/pop/` (the sealed copies). Nothing outside this folder and that scratch was written.

## Independent check (Opus, 2026-11-01) — every headline number MATCHES; three wording corrections
- "1,626 stocks" = 1,626 DOUBLINGS by 1,062 stocks; 2020 holds 55% of the +100% set.
- A small double count where the two stores meet (April 2022): 3 of 1,626 winners (AMR, VTNR; DQ and WTI in the +50% set) — corrected 1,623 / 526 listed / 304 filled / 143 made money / 45 at 3R+; no share moves more than 0.3 points.
- 131 of the 1,098 never-listed winners had their pre-breakout night after the half-way point (a reading caveat on the gate table).

## His 11-01 clarification — the population that judges breakouts: REAL BIG BREAKOUTS only (`real_breakouts_cut.txt`)
"We're not trying to catch everything ... what we're trying to do is to catch the real big breakouts" (docs/methodology/operator_shared_notes.md, 2026-11-01). Of the 1,626 doublings, 872 began as a measurable breakout (the rest: 592 late bases, 150 EP gaps, 12 other — other setups' ground). On the 872: LISTED 380 (44%), BOUGHT 231 (26%), MADE MONEY 113 (13%), 3R+ 40, 10R+ 17; the 5-slot paper book took 63 (7%). By era: 2017-21 597 -> listed 42%, 2022-24 275 -> listed 47%.
v1_nights.tsv.gz (31.6 MB) is kept out of git at /Users/alvinfung/apollo_data/cb702/big_winners_1101/ (reproducible with 02_v1_nights.py).
