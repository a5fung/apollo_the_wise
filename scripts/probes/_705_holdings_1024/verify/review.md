# #705 holdings timeline + replay registration — adversarial review (2026-10-24)

**Verdict: FIX.** Four small, mechanical fixes are needed before the freeze. None is an outcome and none touches the walk's rules. Together
they affect 4 of the 266 deciding entries in the window, and they also clean up exits and undated entries outside the deciding set.

Scope: `docs/analysis/cb_holdings_replay_prereg_2026-10-24.md`, `scripts/probes/_705_holdings_1024/` (timeline, replay, tests, printouts),
`scripts/probes/_705_positions_panel_1024/02_read_all.txt`, plus the timeline's TSVs and the panel jsonl. **No outcome was opened.** No minute
file was read, no bar after any buy day was read, no replay output was read. The only commands run were the test suites (29/29 pass) and
read-only scans of the timeline's own outputs and the panel frames.

## Checks

| # | check | PASS/FAIL | evidence |
|---|---|---|---|
| 1 | A scrolled or cut-off list never creates a false exit or entry | **PASS** (the mechanism) | Exits come only from FULL snapshots, and an exit needs two of them in a row. Full means the footer total equals the rows read (2,070 frames). The 760 scrolled frames can never exit a name. A scrolled frame can open an entry, but its window starts at the last FULL snapshot. Tests cover this: `test_entries_exits_initial_and_windows` (step s2, scrolled, B absent, no exit) and `test_partial_snapshot_can_open_an_entry_with_the_window_from_the_last_full`. 247 single-frame drops were cancelled. I checked all 28 deciding re-entries that come ≤1 session after an exit against the footer arithmetic: the list count changes with the name (SAVE 2020-09-16 swaps with ESTC; TSLA 2020-09-30 goes 14→15 items), so these are real sells and re-buys. |
| 1b | Ordering of frames across videos of one day | **FAIL** | **Duplicate uploads:** 22 video pairs on 13 dates carry identical frames (19 pairs identical, 3 partial: same stream time, clock and list). The sort key is (date, the video's earliest context, its earliest clock, **vid**), so copy 2 replays after copy 1 and the clock runs backwards. Damage: **QS #1069** (EP 2020-12-09, DECIDING, in the window) is a phantom re-entry: copy 1 ends at 10:25 without QS and copy 2 restarts at 09:26 with it. GBTC #1068, ICLN #1293, CLF #1407 and BNTX #1484 are undated phantoms. On 2021-03-08, PLUG/TAN/EYES/TQQQ each get two entries, and the first one carries an exit dated 2021-03-05, before its own first sighting. SPG 2020-08-10 has the same problem. |
| 2 | OCR misreads cannot create phantom entries; how one-stream names are treated | **FAIL** (1 case, plus 1 wrong bracket) | A name seen in one stream is a flagged *flicker*, and dated flickers decide (93 of 296; 90 of 266 in the window). All 37 single-frame deciding entries are unanimous 1080p reads, and every one's % cell is consistent with its own bars. 292 of 296 deciding entries have at least one sighting whose % cell matches. The 4 that don't: FEAC and APXT (SPACs the reader has no bars for, joined by alias), ITCI (720p) and TSLA 2020-09-21. A look-alike swap scan over all 296 found 4 swaps. **LI #1664** (breakout 2021-11-29, in the window) is **mis-dated**: the 09:24 pre-market frame `p_QDYyiDbeVmU_a` shows LI by eye (+7.65%), but it was read as "UI" (`mismatch_kept`, outside UI's 1.3–3.4% range). So LI was already held before the 11-29 open, and the 11-29 breakout cannot be his buy. **SQ #1225**: frame `g_0443` at 10:02 shows SQ by eye, read as "SO" (votes SO 1 / SQ 1, `pct_suggest` = SQ). The day is right (bought 09:42–10:02), but the clock bracket is wrong and SO #1223 is a phantom (undated). SI #1666 is clean. IOT #1881 is outside the window. §1(4)(a)'s "unless its look-alike had a breakout that day" case has happened once. |
| 3 | Buy dating uses only bars up to the buy day, and the window (previous stream, this stream] | **PASS** (with registered caveats) | Events are tl rows (`high(E) > level(D)`) and primary EPs (`open(E)` gap ≥ 9%, `volume(E)` ≥ 3× the 20-day mean). Both use the buy day's own bar (its high and its full-day volume) and nothing after it. `lo` = the last full snapshot's day if it was pre-market or in-session (a later buy that day is possible), otherwise the next session; `hi` = asof(first sighting). 249 of 266 are dated on `hi` itself, so the latest-event rule keeps the window leak small. **What the day-level window ignores (outcome-free, measured):** (a) 9 in-window entries were already held at 09:30–09:34 on E, before any ORH5 fill can exist: TSLA 2020-04-14, UAL 2020-05-27, DXCM 2020-07-29, PINS 2020-07-31, SHOP and TTD 2020-08-26, KOLD 2022-04-19, LAC and TSLA 2022-04-21. (b) 94 were flat at an in-session snapshot on E (51 at ≥10:00 ET, 29 at ≥10:30), so an ORH5 fill earlier than that clock contradicts the panel. 53 are bracketed on both sides within E; for example INO 2020-04-23 is flat at 10:36 and held at 11:00, confirmed by eye. (c) Two duplicate (ticker, E) pairs: PLUG 2021-02-03 (#1221/#1228) and SNAP 2021-06-11 (#1479/#1480). The re-buy came after the panel showed him flat (10:55 / 11:51 ET), yet it is dated to the same E, so the replay walks the same ORH5 fill twice. (d) **Survival conditioning is not stated:** only buys still held at the first sighting are seen (173 first seen in-session on E, 76 after E's close, 17 a session or more later). Round trips completed between two snapshots are invisible, which biases the result upward. |
| 4 | Positive control (his 236 calls): recovery, and why misses miss | **PASS** | 29 of 236 (12%) are dated on E. 33 have a window that holds E, and 29 of those 33 (88%) are dated on E (27 under the earliest-event rule). The other 4 date to a later event in the window (+1, +4, +9, +101 sessions). Misses, one class each: 75 were already held at E (49 of them with the window ending 1–5 sessions before E); 53 were held in E−20..E−1 and sold before E (for example SHOP left 2020-07-14; his calls 07-20/21/28/29 were not bought); 30 never appear; 35 appear only elsewhere; 10 appear only after E. 224 of 236 E-days have a snapshot on E itself, so the misses are not a coverage gap. It was read twice, and that is disclosed. It tests the dating rule, not whether a call was a buy. |
| 5 | Hand check of 10 entries against their two frames (panel crops viewed) | **PASS** 10/10 real new holdings | Seeded sample (`random_state=705`) of in-window deciding entries; prev-full crop → first-sighting crop: INO #500 (10:36 ET, 10 items, no INO → 11:00, 12 items with INO); ACB #581 (05-15, 16 items → 05-20 pre-market, 20 items); TSLA #1006 (09:28 flat → 10:20 held); NVAX #1087 (12-14 → 12-18 09:30); NVAX #575 (05-11 09:45 → 05-14 10:28); FCX #1679 (09:26, 2 items → 09:54, 7 items); SRNE #687 (06-17 10:02, 19/19 → 06-24 09:49); AMC #1266 (02-22 10:43 flat → 02-23 pre-market); LVGO #919 (09:35 flat → 09:52 held); BKKT #1606 (09:29 flat → 10:38 held). The footer counts are consistent in all 10. **Side caveat seen in the crops:** BKKT shows −19.3% on its +18% gap day, next to PHUN and DWAC, and leaves the same day. That looks like a short or a day trade. 43 of 266 in-window entries leave the panel on E itself (11 of the 44 EP-dated). |
| 6 | The deciding threshold is fixed before outcomes, and a FAIL reads as an implementation gap | **PASS** | §7 + `bar_verdict`: alpha t ≥ 2.0 vs QQQ AND total > QQQ AND total > SPY AND Sharpe > QQQ's. It is a conjunction, tested (`test_bar_verdict`, `test_market_stats_recovers_beta_and_alpha`), and it sits above the marker, so it is hashed. The FAIL branch names our parts and quotes his 2026-10-23 rule. Wording fixes are in F6. |
| 7 | Survivorship and delisting | **PASS** | Era A carries delisted tickers (2,809 of its 12,532 symbols end before 2022). 14 deciding names' bars end before the export end. All are acquisitions, mergers or take-privates except LK (fraud delisting, last bar 2020-06-26): DRYS, MIK ×3, TIF, IPHI, XLRN, LK, WORK, FLIR, LVGO, APHA ×3. SPAC-to-merger joins hold (FEAC→FIRY, APXT→AVPT). An open walk marks at the last bar (counted). A panel exit past the last bar marks there (counted). The 81 no-bar panel names (SPACs, OTC, ETNs) are undated by construction and listed. **Doc error:** §2(ii) blames all 8 short forward windows on the era-A export end. Only 3 are; the other 5 are LK 2020-02-18, LVGO 2020-09-25 and APHA 2021-01-06 / 02-10 / 03-02, all marked at the last bar. |
| 8 | The freeze lock | **PASS** mechanics / **FAIL** completeness | The marker is line-anchored and appears exactly once. `doc_body` is the sha of the bytes above it; `5172edc9…` today equals the dry run. Every pin value must sit under the marker. The run refuses if a printout, STOPPED file or named output already exists, and a crash writes STOPPED. I re-hashed the holdings-specific pins now (`02_replay.py`, `test_02_replay.py`, `01_timeline.py`, `test_01_timeline.py`, `01_timeline.txt`, `entries.tsv`, the panel jsonl, `doc_body`) and they equal the dry run's values. The ~40 frozen-read pins were checked by the dry run itself at 13:44, not re-hashed by me. Tests pass 29/29. **Gaps:** (a) the panel reader `scripts/probes/_705_positions_panel_1024/01_read_panel.py` (sha `14a9764f…`, 847 lines uncommitted) is NOT pinned; only its output jsonl is. (b) The doc and the holdings directory are untracked in git. (c) Guard (2) in §10 says "any output under replay/", but `existing_outputs` checks only the 8 named files. (d) §2's dry-run facts (KEEP 234, missing 27/39) go stale once the EP minutes are fetched. |

## Entry precision (in the window, n = 266 deciding entries)

- **Hand check:** 10 of 10 are real new holdings on screen (95% CI 69–100%).
- **Whole-population scans** (duplicate-upload clock reversal, look-alike swap, duplicate (ticker, E)):
  - 1 phantom (QS #1069).
  - 1 mis-dated real holding (LI #1664).
  - 2 re-buys that reuse the first trade's ORH5 fill (PLUG #1228, SNAP #1480).
  - Result: **262 of 266 (98.5%) are valid dated entries**; 265 of 266 (99.6%) are real holdings.
- **Day right AND an ORH5 fill possible on the panel clock:** at most 253 of 266 (95.1%), after removing the 9 already held before 09:35.
  - 94 more can only be checked against the fill minute in the run (fix F5).
- **The dating rule on the control:** 29 of 33 (88%) dated on E.

## Exact fixes (pre-freeze, outcome-free; none change a walk rule)

- **F1, duplicate uploads (`01_timeline.py::load_snapshots`):**
  - On each date, drop a frame whose (`et_time`, `stream_ts`, `symbols`, `visible_n`, `total_n`) signature already appeared in another video that day. Keep the copy with more frames.
  - Then order each date's frames by ET clock across videos, not video then stream time.
  - Test: two identical videos on one date give no extra entry or exit.
  - Expected: QS #1069, GBTC #1068, ICLN #1293, CLF #1407 and BNTX #1484 vanish, along with the 2021-03-08 PLUG/TAN/EYES/TQQQ doubles and the SPG 2020-08-10 double. Deciding entries drop by 1.
- **F2, look-alike guard (`01_timeline.py::timeline`):**
  - Rule: name X first appears in snapshot s, and the last full snapshot holds a symbol Y one edit away from X. Y is absent from s, and Y's row was `mismatch_kept` (or its `pct_suggest` is X). Then treat Y as X in that snapshot: X was held there, so no entry for X and none for Y.
  - Test it.
  - Expected: LI #1664 is re-dated to its true window (bought after 11-26 10:43 ET or pre-market on 11-29). SQ #1225's bracket becomes (09:42, 10:02]. SO #1223 vanishes.
- **F3, panel clock columns (`01_timeline.py`, written to `entries.tsv`):**
  - Add `first_clock_on_E`, `flat_clock_on_E` (the previous full snapshot's ET clock, when it is on E) and `orh5_infeasible` (held on E before 09:35 ET; 9 in the window).
  - Deciding membership does not change; these feed F5.
- **F4, same-day re-buy (`02_replay.py`):**
  - A second entry of a name dated to the same E as an earlier entry (PLUG 2021-02-03, SNAP 2021-06-11) must not reuse the ORH5 fill.
  - Classify it `same_day_rebuy` and read it beside only. Register this in §4.
- **F5, panel-vs-fill counts (`02_replay.py`, registered in §7 as beside):**
  - Per filled deciding trade, compare the fill minute with `flat_clock_on_E` and `first_clock_on_E`.
  - Print the contradicting count by setup, and the deciding account without those trades, beside.
  - Also count our day-0 stop-outs that come before the first-sighting clock (our walk is out while the panel shows him holding).
  - Without these counts, §7 cannot split a FAIL between the entry model and the dating, which it says it will.
- **F6, doc text:**
  - §1(4): add (h) survival conditioning (only buys still held at the first sighting are seen: 173 / 76 / 17, as in check 3; round trips between snapshots are invisible; the bias is upward).
  - §1(4): add (i) 43 of 266 entries leave the panel on E (day trades or shorts; 11 of 44 EP-dated).
  - §1(4): add (j) the blip fill overrides footer-consistent absences in 100 of 121 fills (for example SPXL 2020-04-20: 4 items, 4 rows, no SPXL). These merge real round trips and cost recall, not precision.
  - §2(ii): 5 of the 8 short forward windows come from delistings or mergers, not the export end.
  - §7: excluding dividends **flatters the account** by ~0.6–1.5% a year; the doc currently says "in the market's favour". Add the branch "breakout-dated subset passes while the whole account fails → the EP-dated part (sides, no-minute abstentions)".
  - Header and §2: the dry run **counts** sessions after E (`fwd_sessions`) and reads no price. Say so instead of "no bar after any buy day read".
  - §10 guard (2): match `existing_outputs`, or make the code refuse on any file under `replay/`.
  - §12: add revision rows for F1–F4, each justified from timeline counts and frames, with no outcome seen.
- **F7, pins:**
  - Add `panel_reader` = `scripts/probes/_705_positions_panel_1024/01_read_panel.py` and `panel_read_printout` = `02_read_all.txt` to `02_replay.py`'s `CODE`/`FILES`.
  - Commit the reader, the doc and `scripts/probes/_705_holdings_1024/` in the freeze commit.
- **F8, sequence:**
  - F1–F4.
  - Rerun `01_timeline.py`.
  - Update §2's tables, `EXPECT` and `test_constants_are_the_registration`; rerun the tests.
  - Fetch the missing EP minutes into `cb702/minutes_ep_1024/`.
  - Rerun `02_replay.py --dry-run` and update §2's dry-run facts.
  - Paste the pins under the marker.
  - Commit (check `git show --stat HEAD`), then run once.

## Method notes

- The scans used `holdings_1024/{entries,snapshots,control}.tsv`, `vision/positions_panel_all.jsonl` (row votes, `pct_check`, `pct_suggest`) and the lexicon's first/last dates. Scratch scripts only; nothing in the repo was changed except this file.
- Crops: each panel box was cut from `vision/frames_{grades,positions}/<frame>.png` and upscaled 3×. The 10 sampled pairs, plus LI's `p_QDYyiDbeVmU_a` and SQ's `g_0443`, were viewed by eye.
