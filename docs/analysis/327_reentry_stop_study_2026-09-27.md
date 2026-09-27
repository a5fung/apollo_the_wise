# #327 — a daily-range stop with re-entries, on the 277 real EPs our system caught

**2026-09-27 (Sunday build slot).** Read-only replay from the 09-26 rerun's captured files; $0; no prod access;
nothing deployed, no toggle, no table, no PLAN.md line. Probe: `scripts/probes/_327_real_ep/reentry.py` — its
docstring is the pre-registration of record (grid, pass bar, declared outcomes and the expected result were written
before any cell was computed); outputs `gate_reentry_out.txt`, `anchor_out.txt`, `reentry_rows.tsv`,
`reentry_chains.tsv`, `reentry_cells.tsv`, `reentry_report.txt`, `reentry_summary.json` in the same folder.

**The question (operator 2026-09-26: *"we can explore reentries along with everything else you suggested"*).** The
rerun found the lane's loss is made at the stop (62% of first attempts stopped; the lane's tight stop kept 4 of the
7 big winners' 11 fires at ≥ 3R where a one-day-range stop keeps 7–9). Does a daily-range stop combined with up to
1/2/3 re-entries after a stop-out make any of the lane's four patterns pay, in both rule eras, robustly?

## ⚠ VERIFIED 2026-09-27 — the outcome stands; two of the ten ERA A clears were a floor artifact (this section wins)

Checked by the orchestrator from the row file, with its own code, population first:

- **Population:** every campaign in `reentry_rows.tsv` is one of the 277 in `campaigns.tsv`; era by alert_date
  (< 08-22) matches on all 267 campaigns that fired (A 252, B 15). The 10 with no fire of any pattern (9 A, 1 B)
  include MRNA 08-19, as the rerun found.
- **Cells reproduced to the decimal:** EP-low reclaim × 1×ADR × trail, one try +32.2R on 202 ERA A campaigns
  (drop best two +15.6R), up to three re-entries +33.6R (drop two +16.9R); ERA B −4.5R with 10 of 13 losing.
  Close reclaim × 1.5×ADR and the lane's-stop one-try cell also match.
- **Corrected — the lane's own stop with re-entries:** the probe drops a whole campaign when any re-entry's stop is
  under 0.5% wide. Eight ERA A campaigns fall out only for that reason, and their OTHER, validly-sized attempts lost
  −14.7R. Scoring the floored attempts out but keeping the campaign, the drop-best-two total is **−9.6R with two
  re-entries and −3.1R with three** (not +0.5R / +11.6R), so **those two cells fail the ERA A bar: 8 of 120 clear,
  not 10.** The 1×ADR and 1.5×ADR cells are unaffected (their stops are never under 0.5% wide).
- **Unchanged:** outcome (ii) — ERA B is negative in every cell that clears ERA A. The only surviving candidate is
  the wider stop on the EP-low reclaim, and on the one-try cell 21.6R of its 32.2R is May.

## The answer first

**Declared outcome (ii): the eras disagree — stop there.** 10 of the 120 cells clear the ERA A bar, every one on
the same pattern and exit (the EP-low reclaim with the lane's own trailing exit), and **ERA B contradicts every one
of them**: under a 1×ADR stop, 10 of the 13 ERA B campaigns lose (−4.5R in total, −0.34R a campaign); under the
lane's own stop with re-entries, 5 of 7 lose (−4.8R). The re-entries themselves are not what clears ERA A. On a
daily-range stop they add almost nothing — the 1×ADR stop makes +32.2R on 202 ERA A campaigns with ONE try, and
+33.6R with up to three re-entries (35 re-entry attempts adding +1.4R); the 1.5×ADR stop goes +21.0R → +25.6R. That
first-try result is the rerun's own stop-width finding at a later checkpoint, and it is a May result: +21.6R on the
60 May campaigns, then +5.3R on 44 in June, +2.6R on 31 in July, +2.8R on 67 in August, then −4.5R on the 13 ERA B
campaigns. The lane's own tight stop with re-entries (the 09-02 family, now on the whole population) goes from
−19.1R on one try to +41.9R on up to three re-entries, but after dropping the best two names it is +0.5R (two
re-entries) or +11.6R (three), and after dropping three it is −13.4R / −2.2R — it is KURA, TE, NRIX and BLSH. The
expected result (about −15R after two drops) was wrong in size and right in kind. On the other three patterns nothing
is positive and every re-entry column is worse than one try (close reclaim best cell −22.7R on 142 campaigns; high
break −1.4R on 48; 620 proximity −5.2R on 203). **Plain words: re-entry does not rescue the lane on real EPs in both
eras; the daily-range stop's May edge on the EP-low reclaim is not confirmed by the current rules' EPs; the lane ruling
(keep observing / retire / a different re-entry) goes back to him.**

## Method and population

**Population gate — reproduced from the files this probe loads (`gate_reentry_out.txt`), before any result:**
every live-source `mi_ep_alerts` row 2026-05-01 → 09-11, one campaign per (ticker, alert_date), split at 08-22:

| era | campaigns | names | HIGH / MODERATE / other | alert dates | priced under $5 | named campaigns present |
|---|---:|---:|---|---|---:|---|
| **A** (alert_date < 08-22) | **261** | **243** | **184 / 66 / 11** | 05-11 → 08-21 (May 74 · Jun 53 · Jul 41 · Aug 93) | 0 | TEAM 08-07, MRNA 08-19, PLTR 08-04, HTFL 08-14 |
| **B** (alert_date ≥ 08-22) | **16** | **16** | **14 / 2 / 0** | 08-27 → 09-08 | 0 | — |
| all | **277** | **256** | | | | |

Every line of the rerun's `gate_out.txt` matched, including the medians (ERA B's two medians sit exactly on a
half-cent — 114.885 and 10.895 — and the first gate run flagged them because Python's `.2f` rounds them down where
SQL rounds them up; the gate now rounds the way `gate.sql` does and passes on every line). `campaigns.tsv` holds the
same 277 keys; `fires.tsv` holds 632 first-attempt fires on 267 of them (ERA A 595, ERA B 37); the 23 lane-recorded
first fires sit on the 10 uncovered ERA B campaigns exactly as the rerun pre-registered. `mi_delayed_entry_trigger`
rows are never the population.

**Instrument — reused, not rewritten.** First attempts = the rerun's `fires.tsv` (the 09-01 walker with the horizon
patched to 2026-09-25 and the < 100-bar session = missing rule). Re-entry shapes = the 09-02 retry test's functions
imported from `_545_retry_test.py` (mirrors of the lane's own `_record_reentries_for` / `_replay_same_pattern_*` /
`replay_level_break`): policy "either" = whichever of same-pattern / new-high-break fires first after a stop-out;
a re-entry opens only after a stop-out; each stop-out opens a fresh 20-session window from the next session.
Settlement = the lane's `compute_settlement` on every attempt, with the rerun's day-0 source order (real post-fire
5-minute bars → the lane's cached day-0 excursion for lane-recorded fires → abstain); the 09-02 `_settle` was not
imported because it passes an empty list for missing day-0 bars, which `compute_settlement` reads as "the fire was
the last bar". A window the horizon cuts before the 20th session is marked at the last close (09-25); the trail arm
exits at the first close below the real `sma_trail_line`. Stop per attempt: the attempt's own lane stop, or its
entry − k × ADR$ (the EP-anchored `compute_ep_adr_dollar`, cross-checked equal on all 277 campaigns). **The judged R
charges a gap-through stop at the open** (524 of 5,078 stops across every chain opened below the stop); the house
−1.00R total is shown beside it. Block 5's 0.5% width floor applies (an attempt under 0.5% wide makes its campaign
unreadable in that cell — on the EP-low reclaim under the lane's own stop, 31 ERA A first attempts and 11 razor-thin
re-entry stops, 39 campaigns in all at three re-entries; the 31 first attempts' house R under that stop summed to
−20.7R, so the floor flatters the lane's stop, not the ADR stops, which never fall under it). The lane stamps a
re-entry row's `stop_price` with the evaluator's own stop (`delayed_entry_shadow.py` lines 1766/1796; the level-break
re-entry with the prior-session low, line 1881), which is what the "incumbent" chain uses. Exit arms: the lane's trail (a close
below max(SMA10, SMA20)) and the lane's M-none (stop, else the 20th-session close); "hold to horizon" is read as
M-none — a literal hold to 09-25 would give May EPs a four-month hold. Unit = per-campaign total R at equal dollar
risk per attempt. One chain per (first fire × stop × arm), up to 4 attempts: 632 × 4 × 2 = **5,056 chains, 7,943
attempt rows**; the attempts=1/2/3/4 columns are prefixes.

**Anchors, all printed before any cell (`anchor_out.txt`):** (A) this probe's chain on the 09-02 test's own files
(horizon 08-31, four ADR stops, both arms, unlimited attempts) reproduces `_545rt_rows.tsv` on **10,239 of 10,239
attempt rows across 4,816 chains, 0 drift** — the only anchor that tests attempts ≥ 2. (B) attempt 1 at the lane's own
stop and the 09-25 horizon reproduces the rerun's own settlement on **606 of 606 replayed first fires**; the 3
replayed fires the rerun abstained on abstain here too (open window — marked in the run); of the 23 lane-recorded ERA B
fires 15 match the lane's record, 1 is the lane's open row (marked), and **7 abstain** (a day low at the stop and no
cached day 0 — the lane's own records say they were stops, so they can only have made ERA B worse). (C) the horizon
mark equals `compute_settlement`'s own session-10 mark on **293 of 293** fires whose session list was truncated to 10.
Bridge to the rerun: on the same 201 ERA A low-reclaim fires, the rerun's session-10 grid reads +0.23R for the 1×ADR /
trail cell and this study reads +0.16R at the final mark, 183 of 201 fires identical (the rest are session-10 marks
walked on to their exit) — the same fact at a later checkpoint; the rerun's ERA B for that cell was −0.45R on 11.

**ERA B's horizon, plainly.** ERA B alerts run 08-27 → 09-08 and have 13–20 sessions to 09-25, so no ERA B chain
reaches the 20th session: 1–2 campaigns per cell are marked open at the horizon and 0–7 re-entry windows per cell are
cut short. The 10 uncovered ERA B campaigns have no stored minute bars for September, so a same-pattern re-entry
search there is blind (counted per cell, never guessed): in the 1×ADR / up-to-3-re-entries cell, 2 of 13 ERA B
campaigns had blind sessions (CHRN 9, VEEV 2). **No attempts=1 cell has a re-entry window, so ERA B's sign on those
cells rests on nothing missing.**

**The grid and the bar (pre-registered).** 4 patterns × 4 stops (the lane's own, 0.75 / 1.0 / 1.5 × ADR$) × 4
attempt caps (1 = no re-entry) × 2 exits = **128 cells = 8 baselines + 120 draws**; noise band ≤ 2 clearing ERA A,
family ≥ 11; the cells are nested (prefix caps, adjacent stops), so the independent draws are far fewer. A cell
clears ERA A when, on gap-charged per-campaign totals: mean > 0 · total > 0 after dropping the best two names · beats
the same pattern's one-try / lane's-own-stop / same-exit cell on the campaigns readable under both · worst
single-name drawdown no worse than that baseline's minus the extra attempts' nominal risk · n ≥ 30; it is confirmed
only if ERA B's mean has the same sign (n stated; 0 ERA B = not confirmed). Declared: (i) confirmed cells → named;
(ii) clear ERA A, none confirmed → "eras disagree", stop; (iii) none clear → re-entry does not rescue the lane.
Expected before running: (iii).

**Verdict against the draws: 10 of 120 clear ERA A (above the noise band of 2, below the family line of 11, all
nested on one pattern × one exit); 0 confirmed; ERA B's mean is positive in 37 draws and negative in the 10 that
clear.**

## The grid

Per-campaign totals, gap-charged; "vs baseline" = this cell against the same pattern's one-try / lane's-own-stop /
same-exit cell on the campaigns readable under both; "runners" = the rerun's 7 big-winner EPs that fired on the
pattern; "windows cut" = re-entry windows the 09-25 horizon cut short with no fire; "blind" = campaigns whose
re-entry search hit a session with no stored minute bars; "unreadable" = campaigns dropped by an abstain or the width
floor. Legs, ERA A: mean > 0 · drop-2 > 0 · beats baseline · drawdown within nominal · n ≥ 30; then ERA B's sign.

| pattern | stop | tries | exit | ERA A n (names) | mean R | total R (gap-charged) | house total | drop best 2 names | worst name | vs baseline, same campaigns (cell / base) | ≥3R campaigns | runners ≥3R / fired | attempts fired | windows cut by horizon | blind names | ERA B n | ERA B mean | ERA B total | ERA B windows cut / blind | unreadable A / B | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| low reclaim | lane's own | 1 | trail | 171 (163) | -0.11 | -19.1 | -16.4 | -49.4 | AEHR -2.9 | -19.1 / -19.1 (n 171) | 10 | 1 / 3 | 171 | 0 | 0 | 7 | -0.70 | -4.9 | 0 / 0 | 31 / 6 | baseline |
| low reclaim | lane's own | 2 | trail | 166 (158) | +0.02 | +2.8 | +5.9 | -27.5 | AEHR -2.9 | +2.8 / -14.1 (n 166) | 14 | 2 / 3 | 241 | 0 | 3 | 7 | -0.76 | -5.3 | 1 / 2 | 36 / 6 | no |
| low reclaim | lane's own | 3 | trail | 164 (156) | +0.19 | +30.8 | +33.8 | +0.5 | LZB -3.0 | +30.8 / -12.1 (n 164) | 16 | 3 / 3 | 259 | 0 | 3 | 7 | -0.68 | -4.8 | 2 / 2 | 38 / 6 | clears ERA A, ERA B contradicts |
| low reclaim | lane's own | 4 | trail | 163 (155) | +0.26 | +41.9 | +44.9 | +11.6 | CAMT -3.8 | +41.9 / -11.1 (n 163) | 17 | 3 / 3 | 261 | 0 | 5 | 7 | -0.68 | -4.8 | 2 / 2 | 39 / 6 | clears ERA A, ERA B contradicts |
| low reclaim | lane's own | 1 | none | 171 (163) | -0.37 | -64.0 | -56.0 | -86.1 | HGTY -3.8 | -64.0 / -64.0 (n 171) | 11 | 1 / 3 | 171 | 0 | 0 | 7 | -0.82 | -5.8 | 0 / 0 | 31 / 6 | baseline |
| low reclaim | lane's own | 2 | none | 166 (158) | -0.40 | -66.6 | -57.9 | -91.4 | HGTY -4.8 | -66.6 / -59.0 (n 166) | 18 | 2 / 3 | 276 | 3 | 12 | 7 | +1.24 | +8.7 | 2 / 3 | 36 / 6 | no |
| low reclaim | lane's own | 3 | none | 164 (156) | -0.25 | -40.8 | -31.1 | -69.6 | AEHR -5.5 | -40.8 / -57.0 (n 164) | 21 | 3 / 3 | 319 | 12 | 23 | 7 | +1.32 | +9.2 | 3 / 3 | 38 / 6 | no |
| low reclaim | lane's own | 4 | none | 162 (154) | -0.23 | -36.8 | -27.1 | -65.7 | AEHR -5.8 | -36.8 / -55.0 (n 162) | 21 | 3 / 3 | 331 | 15 | 33 | 7 | +1.32 | +9.2 | 3 / 3 | 40 / 6 | no |
| low reclaim | 0.75×ADR | 1 | trail | 202 (189) | +0.11 | +21.4 | +24.2 | -0.8 | BLZE -2.2 | +28.0 / -19.1 (n 171) | 17 | 2 / 3 | 202 | 0 | 0 | 13 | -0.50 | -6.5 | 0 / 0 | 0 / 0 | no |
| low reclaim | 0.75×ADR | 2 | trail | 202 (189) | +0.10 | +20.5 | +24.9 | -1.6 | KC -3.3 | +28.2 / -19.1 (n 171) | 19 | 2 / 3 | 260 | 0 | 5 | 13 | -0.47 | -6.1 | 4 / 3 | 0 / 0 | no |
| low reclaim | 0.75×ADR | 3 | trail | 202 (189) | +0.07 | +14.9 | +19.3 | -7.3 | AEHR -4.2 | +25.5 / -19.1 (n 171) | 19 | 2 / 3 | 274 | 1 | 7 | 13 | -0.47 | -6.1 | 5 / 3 | 0 / 0 | no |
| low reclaim | 0.75×ADR | 4 | trail | 202 (189) | +0.09 | +17.9 | +22.3 | -4.2 | AEHR -5.2 | +29.2 / -19.1 (n 171) | 19 | 2 / 3 | 278 | 1 | 7 | 13 | -0.47 | -6.1 | 5 / 3 | 0 / 0 | no |
| low reclaim | 0.75×ADR | 1 | none | 202 (189) | -0.09 | -18.3 | -12.2 | -44.4 | HGTY -2.4 | +6.2 / -64.0 (n 171) | 21 | 2 / 3 | 202 | 0 | 0 | 13 | +0.16 | +2.1 | 0 / 0 | 0 / 0 | no |
| low reclaim | 0.75×ADR | 2 | none | 202 (189) | -0.09 | -18.9 | -10.6 | -45.1 | AVAV -4.0 | +14.0 / -64.0 (n 171) | 30 | 3 / 3 | 312 | 11 | 26 | 13 | +0.58 | +7.6 | 7 / 7 | 0 / 0 | no |
| low reclaim | 0.75×ADR | 3 | none | 202 (189) | -0.12 | -25.1 | -12.8 | -51.3 | QDEL -6.3 | +7.2 / -64.0 (n 171) | 35 | 3 / 3 | 358 | 21 | 46 | 13 | +0.58 | +7.6 | 8 / 7 | 0 / 0 | no |
| low reclaim | 0.75×ADR | 4 | none | 202 (189) | -0.23 | -46.5 | -31.2 | -72.7 | STC -6.3 | -12.2 / -64.0 (n 171) | 35 | 3 / 3 | 382 | 21 | 54 | 13 | +0.58 | +7.6 | 8 / 7 | 0 / 0 | no |
| low reclaim | 1.0×ADR | 1 | trail | 202 (189) | +0.16 | +32.2 | +34.2 | +15.6 | KC -1.8 | +30.4 / -19.1 (n 171) | 11 | 2 / 3 | 202 | 0 | 0 | 13 | -0.34 | -4.5 | 0 / 0 | 0 / 0 | clears ERA A, ERA B contradicts |
| low reclaim | 1.0×ADR | 2 | trail | 202 (189) | +0.15 | +31.0 | +33.0 | +14.3 | KC -2.3 | +30.7 / -19.1 (n 171) | 11 | 2 / 3 | 235 | 0 | 3 | 13 | -0.34 | -4.4 | 2 / 2 | 0 / 0 | clears ERA A, ERA B contradicts |
| low reclaim | 1.0×ADR | 3 | trail | 202 (189) | +0.17 | +33.6 | +35.6 | +16.9 | AUGO -3.0 | +33.3 / -19.1 (n 171) | 11 | 2 / 3 | 237 | 0 | 4 | 13 | -0.34 | -4.4 | 3 / 2 | 0 / 0 | clears ERA A, ERA B contradicts |
| low reclaim | 1.0×ADR | 4 | trail | 202 (189) | +0.17 | +33.6 | +35.6 | +16.9 | AUGO -3.0 | +33.3 / -19.1 (n 171) | 11 | 2 / 3 | 237 | 0 | 4 | 13 | -0.34 | -4.4 | 3 / 2 | 0 / 0 | clears ERA A, ERA B contradicts |
| low reclaim | 1.0×ADR | 1 | none | 202 (189) | -0.03 | -5.7 | -2.0 | -25.3 | RDW -2.1 | +8.5 / -64.0 (n 171) | 22 | 2 / 3 | 202 | 0 | 0 | 13 | +0.08 | +1.0 | 0 / 0 | 0 / 0 | no |
| low reclaim | 1.0×ADR | 2 | none | 202 (189) | -0.08 | -17.0 | -11.9 | -36.6 | AVAV -4.0 | +4.2 / -64.0 (n 171) | 28 | 3 / 3 | 287 | 12 | 27 | 13 | +0.37 | +4.8 | 6 / 5 | 0 / 0 | no |
| low reclaim | 1.0×ADR | 3 | none | 202 (189) | -0.14 | -29.2 | -24.0 | -48.8 | AVAV -5.0 | -5.0 / -64.0 (n 171) | 29 | 3 / 3 | 316 | 20 | 48 | 13 | +0.37 | +4.8 | 7 / 5 | 0 / 0 | no |
| low reclaim | 1.0×ADR | 4 | none | 202 (189) | -0.19 | -38.9 | -32.1 | -58.5 | STC -5.7 | -12.7 / -64.0 (n 171) | 29 | 3 / 3 | 330 | 21 | 53 | 13 | +0.37 | +4.8 | 7 / 5 | 0 / 0 | no |
| low reclaim | 1.5×ADR | 1 | trail | 202 (189) | +0.10 | +21.0 | +21.6 | +9.9 | SE -1.6 | +19.9 / -19.1 (n 171) | 6 | 2 / 3 | 202 | 0 | 0 | 13 | -0.22 | -2.8 | 0 / 0 | 0 / 0 | clears ERA A, ERA B contradicts |
| low reclaim | 1.5×ADR | 2 | trail | 202 (189) | +0.13 | +25.6 | +26.2 | +14.5 | NVCR -1.7 | +24.6 / -19.1 (n 171) | 6 | 2 / 3 | 216 | 0 | 1 | 13 | -0.22 | -2.8 | 1 / 1 | 0 / 0 | clears ERA A, ERA B contradicts |
| low reclaim | 1.5×ADR | 3 | trail | 202 (189) | +0.13 | +25.6 | +26.2 | +14.5 | NVCR -1.7 | +24.6 / -19.1 (n 171) | 6 | 2 / 3 | 216 | 0 | 1 | 13 | -0.22 | -2.8 | 1 / 1 | 0 / 0 | clears ERA A, ERA B contradicts |
| low reclaim | 1.5×ADR | 4 | trail | 202 (189) | +0.13 | +25.6 | +26.2 | +14.5 | NVCR -1.7 | +24.6 / -19.1 (n 171) | 6 | 2 / 3 | 216 | 0 | 1 | 13 | -0.22 | -2.8 | 1 / 1 | 0 / 0 | clears ERA A, ERA B contradicts |
| low reclaim | 1.5×ADR | 1 | none | 202 (189) | -0.08 | -15.8 | -13.6 | -30.7 | SE -2.3 | +0.1 / -64.0 (n 171) | 15 | 3 / 3 | 202 | 0 | 0 | 13 | -0.22 | -2.9 | 0 / 0 | 0 / 0 | no |
| low reclaim | 1.5×ADR | 2 | none | 202 (189) | -0.09 | -18.9 | -16.5 | -33.8 | AVAV -4.0 | -0.0 / -64.0 (n 171) | 17 | 3 / 3 | 258 | 19 | 22 | 13 | +0.02 | +0.3 | 7 / 5 | 0 / 0 | no |
| low reclaim | 1.5×ADR | 3 | none | 202 (189) | -0.14 | -28.2 | -25.1 | -43.1 | AVAV -5.0 | -7.3 / -64.0 (n 171) | 17 | 3 / 3 | 273 | 23 | 35 | 13 | +0.02 | +0.3 | 7 / 5 | 0 / 0 | no |
| low reclaim | 1.5×ADR | 4 | none | 202 (189) | -0.13 | -26.9 | -23.8 | -41.8 | AVAV -5.0 | -7.2 / -64.0 (n 171) | 17 | 3 / 3 | 276 | 25 | 38 | 13 | +0.02 | +0.3 | 7 / 5 | 0 / 0 | no |
| close reclaim | lane's own | 1 | trail | 135 (128) | -0.22 | -29.3 | -26.4 | -45.3 | KC -2.4 | -29.3 / -29.3 (n 135) | 11 | 1 / 2 | 135 | 0 | 0 | 6 | -1.39 | -8.3 | 0 / 0 | 7 / 3 | baseline |
| close reclaim | lane's own | 2 | trail | 134 (127) | -0.34 | -45.9 | -42.9 | -61.9 | MRVL -4.0 | -45.9 / -28.3 (n 134) | 12 | 1 / 2 | 196 | 0 | 2 | 6 | -1.26 | -7.6 | 3 / 2 | 8 / 3 | no |
| close reclaim | lane's own | 3 | trail | 133 (126) | -0.40 | -53.1 | -48.3 | -69.1 | MRVL -6.8 | -53.1 / -27.3 (n 133) | 12 | 1 / 2 | 212 | 1 | 6 | 6 | -1.26 | -7.6 | 3 / 2 | 9 / 3 | no |
| close reclaim | lane's own | 4 | trail | 133 (126) | -0.44 | -59.1 | -54.0 | -75.1 | MRVL -6.8 | -59.1 / -27.3 (n 133) | 12 | 1 / 2 | 219 | 1 | 6 | 6 | -1.26 | -7.6 | 3 / 2 | 9 / 3 | no |
| close reclaim | lane's own | 1 | none | 135 (128) | -0.50 | -67.7 | -62.9 | -99.1 | KC -2.4 | -67.7 / -67.7 (n 135) | 6 | 0 / 2 | 135 | 0 | 0 | 6 | -1.39 | -8.3 | 0 / 0 | 7 / 3 | baseline |
| close reclaim | lane's own | 2 | none | 134 (127) | -0.72 | -95.9 | -90.3 | -127.4 | MRVL -4.0 | -95.9 / -66.7 (n 134) | 7 | 0 / 2 | 206 | 6 | 8 | 6 | -0.63 | -3.8 | 3 / 2 | 8 / 3 | no |
| close reclaim | lane's own | 3 | none | 133 (126) | -0.75 | -99.7 | -92.4 | -131.2 | MRVL -6.8 | -99.7 / -65.7 (n 133) | 8 | 0 / 2 | 229 | 9 | 16 | 6 | -0.63 | -3.8 | 3 / 2 | 9 / 3 | no |
| close reclaim | lane's own | 4 | none | 133 (126) | -0.81 | -108.0 | -99.7 | -139.4 | MRVL -6.8 | -108.0 / -65.7 (n 133) | 8 | 0 / 2 | 240 | 10 | 20 | 6 | -0.63 | -3.8 | 3 / 2 | 9 / 3 | no |
| close reclaim | 0.75×ADR | 1 | trail | 142 (135) | -0.30 | -41.9 | -39.1 | -52.5 | KC -2.4 | -37.2 / -29.3 (n 135) | 6 | 1 / 2 | 142 | 0 | 0 | 9 | -0.82 | -7.4 | 0 / 0 | 0 / 0 | no |
| close reclaim | 0.75×ADR | 2 | trail | 142 (135) | -0.41 | -58.4 | -54.3 | -69.0 | MRVL -4.6 | -55.4 / -29.3 (n 135) | 7 | 1 / 2 | 192 | 0 | 3 | 9 | -0.60 | -5.4 | 4 / 3 | 0 / 0 | no |
| close reclaim | 0.75×ADR | 3 | trail | 142 (135) | -0.43 | -60.6 | -55.6 | -72.1 | MRVL -5.6 | -56.6 / -29.3 (n 135) | 8 | 1 / 2 | 215 | 0 | 7 | 9 | -0.19 | -1.7 | 4 / 3 | 0 / 0 | no |
| close reclaim | 0.75×ADR | 4 | trail | 142 (135) | -0.42 | -59.7 | -54.6 | -71.2 | MRVL -5.6 | -55.7 / -29.3 (n 135) | 8 | 1 / 2 | 225 | 0 | 10 | 9 | -0.19 | -1.7 | 4 / 3 | 0 / 0 | no |
| close reclaim | 0.75×ADR | 1 | none | 142 (135) | -0.58 | -82.2 | -77.1 | -98.7 | KC -2.4 | -75.1 / -67.7 (n 135) | 8 | 0 / 2 | 142 | 0 | 0 | 9 | -0.16 | -1.4 | 0 / 0 | 0 / 0 | no |
| close reclaim | 0.75×ADR | 2 | none | 142 (135) | -0.70 | -99.8 | -92.6 | -116.2 | MRVL -4.6 | -91.8 / -67.7 (n 135) | 9 | 0 / 2 | 206 | 6 | 11 | 9 | +0.28 | +2.5 | 5 / 4 | 0 / 0 | no |
| close reclaim | 0.75×ADR | 3 | none | 142 (135) | -0.76 | -108.2 | -100.0 | -124.6 | ZBRA -6.0 | -99.3 / -67.7 (n 135) | 11 | 0 / 2 | 237 | 9 | 21 | 9 | +0.69 | +6.3 | 5 / 4 | 0 / 0 | no |
| close reclaim | 0.75×ADR | 4 | none | 142 (135) | -0.83 | -118.0 | -109.3 | -134.5 | ZBRA -7.0 | -109.1 / -67.7 (n 135) | 11 | 0 / 2 | 252 | 11 | 30 | 9 | +0.69 | +6.3 | 5 / 4 | 0 / 0 | no |
| close reclaim | 1.0×ADR | 1 | trail | 142 (135) | -0.21 | -30.2 | -27.7 | -38.5 | WYFI -3.2 | -29.0 / -29.3 (n 135) | 2 | 1 / 2 | 142 | 0 | 0 | 9 | -0.64 | -5.8 | 0 / 0 | 0 / 0 | no |
| close reclaim | 1.0×ADR | 2 | trail | 142 (135) | -0.29 | -41.7 | -38.4 | -49.9 | WYFI -4.2 | -39.5 / -29.3 (n 135) | 2 | 1 / 2 | 177 | 0 | 3 | 9 | -0.53 | -4.8 | 4 / 3 | 0 / 0 | no |
| close reclaim | 1.0×ADR | 3 | trail | 142 (135) | -0.25 | -36.2 | -32.9 | -44.4 | MRVL -5.2 | -34.0 / -29.3 (n 135) | 3 | 1 / 2 | 188 | 0 | 7 | 9 | -0.53 | -4.8 | 4 / 3 | 0 / 0 | no |
| close reclaim | 1.0×ADR | 4 | trail | 142 (135) | -0.23 | -33.3 | -30.1 | -41.6 | MRVL -5.2 | -31.2 / -29.3 (n 135) | 3 | 1 / 2 | 190 | 0 | 8 | 9 | -0.53 | -4.8 | 4 / 3 | 0 / 0 | no |
| close reclaim | 1.0×ADR | 1 | none | 142 (135) | -0.52 | -74.0 | -62.4 | -86.3 | RARE -9.0 | -69.5 / -67.7 (n 135) | 6 | 1 / 2 | 142 | 0 | 0 | 9 | -0.02 | -0.1 | 0 / 0 | 0 / 0 | no |
| close reclaim | 1.0×ADR | 2 | none | 142 (135) | -0.61 | -87.0 | -74.7 | -99.6 | RARE -9.0 | -81.6 / -67.7 (n 135) | 7 | 1 / 2 | 190 | 9 | 13 | 9 | +0.51 | +4.5 | 5 / 4 | 0 / 0 | no |
| close reclaim | 1.0×ADR | 3 | none | 142 (135) | -0.64 | -90.6 | -78.3 | -103.2 | RARE -9.0 | -84.1 / -67.7 (n 135) | 8 | 1 / 2 | 207 | 12 | 23 | 9 | +0.51 | +4.5 | 5 / 4 | 0 / 0 | no |
| close reclaim | 1.0×ADR | 4 | none | 142 (135) | -0.67 | -95.2 | -82.7 | -107.8 | RARE -9.0 | -88.7 / -67.7 (n 135) | 8 | 1 / 2 | 213 | 13 | 28 | 9 | +0.51 | +4.5 | 5 / 4 | 0 / 0 | no |
| close reclaim | 1.5×ADR | 1 | trail | 142 (135) | -0.16 | -22.7 | -20.1 | -29.1 | WYFI -2.5 | -21.9 / -29.3 (n 135) | 2 | 0 / 2 | 142 | 0 | 0 | 9 | -0.62 | -5.6 | 0 / 0 | 0 / 0 | no |
| close reclaim | 1.5×ADR | 2 | trail | 142 (135) | -0.19 | -26.3 | -23.7 | -32.8 | WYFI -3.5 | -25.5 / -29.3 (n 135) | 2 | 0 / 2 | 158 | 0 | 2 | 9 | -0.55 | -4.9 | 4 / 3 | 0 / 0 | no |
| close reclaim | 1.5×ADR | 3 | trail | 142 (135) | -0.19 | -26.8 | -23.7 | -33.3 | MRVL -4.5 | -26.0 / -29.3 (n 135) | 2 | 0 / 2 | 162 | 0 | 4 | 9 | -0.55 | -4.9 | 4 / 3 | 0 / 0 | no |
| close reclaim | 1.5×ADR | 4 | trail | 142 (135) | -0.19 | -26.8 | -23.7 | -33.3 | MRVL -4.5 | -26.0 / -29.3 (n 135) | 2 | 0 / 2 | 162 | 0 | 4 | 9 | -0.55 | -4.9 | 4 / 3 | 0 / 0 | no |
| close reclaim | 1.5×ADR | 1 | none | 142 (135) | -0.45 | -63.7 | -55.9 | -71.9 | RARE -6.0 | -58.7 / -67.7 (n 135) | 5 | 0 / 2 | 142 | 0 | 0 | 9 | -0.24 | -2.1 | 0 / 0 | 0 / 0 | no |
| close reclaim | 1.5×ADR | 2 | none | 142 (135) | -0.53 | -75.2 | -67.4 | -83.5 | RARE -6.0 | -69.3 / -67.7 (n 135) | 5 | 0 / 2 | 174 | 9 | 16 | 9 | +0.11 | +1.0 | 5 / 3 | 0 / 0 | no |
| close reclaim | 1.5×ADR | 3 | none | 142 (135) | -0.57 | -81.1 | -72.8 | -89.3 | RARE -6.0 | -74.1 / -67.7 (n 135) | 5 | 0 / 2 | 184 | 11 | 25 | 9 | +0.11 | +1.0 | 5 / 3 | 0 / 0 | no |
| close reclaim | 1.5×ADR | 4 | none | 142 (135) | -0.60 | -85.0 | -75.8 | -93.2 | SYRE -6.1 | -78.0 / -67.7 (n 135) | 5 | 0 / 2 | 187 | 12 | 28 | 9 | +0.11 | +1.0 | 5 / 3 | 0 / 0 | no |
| high break | lane's own | 1 | trail | 48 (47) | -0.16 | -7.5 | -7.5 | -13.4 | RDW -1.2 | -7.5 / -7.5 (n 48) | 1 | 1 / 2 | 48 | 0 | 0 | 2 | +0.11 | +0.2 | 0 / 0 | 0 / 0 | baseline |
| high break | lane's own | 2 | trail | 48 (47) | -0.19 | -9.1 | -8.9 | -15.0 | DELL -2.3 | -9.1 / -7.5 (n 48) | 1 | 1 / 2 | 56 | 0 | 0 | 2 | +0.11 | +0.2 | 0 / 0 | 0 / 0 | no |
| high break | lane's own | 3 | trail | 48 (47) | -0.20 | -9.7 | -9.4 | -15.5 | DELL -2.8 | -9.7 / -7.5 (n 48) | 1 | 1 / 2 | 57 | 0 | 0 | 2 | +0.11 | +0.2 | 0 / 0 | 0 / 0 | no |
| high break | lane's own | 4 | trail | 48 (47) | -0.20 | -9.7 | -9.4 | -15.5 | DELL -2.8 | -9.7 / -7.5 (n 48) | 1 | 1 / 2 | 57 | 0 | 0 | 2 | +0.11 | +0.2 | 0 / 0 | 0 / 0 | no |
| high break | lane's own | 1 | none | 48 (47) | -0.38 | -18.3 | -18.1 | -28.9 | RDW -2.0 | -18.3 / -18.3 (n 48) | 2 | 2 / 2 | 48 | 0 | 0 | 2 | +0.08 | +0.2 | 0 / 0 | 0 / 0 | baseline |
| high break | lane's own | 2 | none | 48 (47) | -0.57 | -27.2 | -26.7 | -37.8 | DELL -2.3 | -27.2 / -18.3 (n 48) | 2 | 2 / 2 | 67 | 0 | 0 | 2 | +0.08 | +0.2 | 1 / 0 | 0 / 0 | no |
| high break | lane's own | 3 | none | 48 (47) | -0.60 | -28.6 | -28.1 | -39.2 | DELL -3.3 | -28.6 / -18.3 (n 48) | 2 | 2 / 2 | 74 | 0 | 0 | 2 | +0.08 | +0.2 | 1 / 0 | 0 / 0 | no |
| high break | lane's own | 4 | none | 48 (47) | -0.57 | -27.3 | -26.8 | -37.9 | DELL -4.3 | -27.3 / -18.3 (n 48) | 2 | 2 / 2 | 79 | 0 | 0 | 2 | +0.08 | +0.2 | 1 / 0 | 0 / 0 | no |
| high break | 0.75×ADR | 1 | trail | 48 (47) | -0.13 | -6.4 | -2.2 | -21.8 | SKM -3.3 | -6.4 / -7.5 (n 48) | 4 | 2 / 2 | 48 | 0 | 0 | 2 | -1.00 | -2.0 | 0 / 0 | 0 / 0 | no |
| high break | 0.75×ADR | 2 | trail | 48 (47) | -0.23 | -11.1 | -6.6 | -26.5 | SKM -3.3 | -11.1 / -7.5 (n 48) | 4 | 2 / 2 | 69 | 0 | 0 | 2 | -2.00 | -4.0 | 0 / 0 | 0 / 0 | no |
| high break | 0.75×ADR | 3 | trail | 48 (47) | -0.35 | -16.7 | -12.2 | -32.2 | SKM -3.3 | -16.7 / -7.5 (n 48) | 4 | 2 / 2 | 79 | 0 | 0 | 2 | -1.93 | -3.9 | 1 / 0 | 0 / 0 | no |
| high break | 0.75×ADR | 4 | trail | 48 (47) | -0.42 | -20.1 | -14.6 | -35.5 | DELL -5.3 | -20.1 / -7.5 (n 48) | 4 | 2 / 2 | 82 | 0 | 0 | 2 | -1.93 | -3.9 | 1 / 0 | 0 / 0 | no |
| high break | 0.75×ADR | 1 | none | 48 (47) | -0.17 | -8.0 | -3.8 | -35.8 | SKM -3.3 | -8.0 / -18.3 (n 48) | 4 | 2 / 2 | 48 | 0 | 0 | 2 | -1.00 | -2.0 | 0 / 0 | 0 / 0 | no |
| high break | 0.75×ADR | 2 | none | 48 (47) | -0.51 | -24.6 | -19.4 | -52.3 | SKM -3.3 | -24.6 / -18.3 (n 48) | 5 | 2 / 2 | 79 | 0 | 0 | 2 | -2.00 | -4.0 | 0 / 0 | 0 / 0 | no |
| high break | 0.75×ADR | 3 | none | 48 (47) | -0.47 | -22.4 | -16.9 | -50.2 | IREN -3.8 | -22.4 / -18.3 (n 48) | 7 | 2 / 2 | 97 | 1 | 0 | 2 | -0.96 | -1.9 | 1 / 0 | 0 / 0 | no |
| high break | 0.75×ADR | 4 | none | 48 (47) | -0.52 | -24.8 | -17.9 | -52.5 | DELL -5.3 | -24.8 / -18.3 (n 48) | 7 | 2 / 2 | 110 | 1 | 0 | 2 | -0.96 | -1.9 | 1 / 0 | 0 / 0 | no |
| high break | 1.0×ADR | 1 | trail | 48 (47) | -0.15 | -7.3 | -4.6 | -18.8 | SKM -2.5 | -7.3 / -7.5 (n 48) | 3 | 2 / 2 | 48 | 0 | 0 | 2 | -0.44 | -0.9 | 0 / 0 | 0 / 0 | no |
| high break | 1.0×ADR | 2 | trail | 48 (47) | -0.22 | -10.8 | -7.6 | -22.3 | DELL -2.6 | -10.8 / -7.5 (n 48) | 3 | 2 / 2 | 66 | 0 | 0 | 2 | -0.38 | -0.8 | 0 / 0 | 0 / 0 | no |
| high break | 1.0×ADR | 3 | trail | 48 (47) | -0.32 | -15.4 | -12.2 | -27.0 | DELL -3.6 | -15.4 / -7.5 (n 48) | 3 | 2 / 2 | 71 | 0 | 0 | 2 | -0.38 | -0.8 | 0 / 0 | 0 / 0 | no |
| high break | 1.0×ADR | 4 | trail | 48 (47) | -0.34 | -16.4 | -13.2 | -28.0 | DELL -4.6 | -16.4 / -7.5 (n 48) | 3 | 2 / 2 | 72 | 0 | 0 | 2 | -0.38 | -0.8 | 0 / 0 | 0 / 0 | no |
| high break | 1.0×ADR | 1 | none | 48 (47) | -0.19 | -9.3 | -6.6 | -30.1 | SKM -2.5 | -9.3 / -18.3 (n 48) | 5 | 2 / 2 | 48 | 0 | 0 | 2 | -1.00 | -2.0 | 0 / 0 | 0 / 0 | no |
| high break | 1.0×ADR | 2 | none | 48 (47) | -0.62 | -29.9 | -26.7 | -50.7 | DELL -2.6 | -29.9 / -18.3 (n 48) | 5 | 2 / 2 | 75 | 0 | 0 | 2 | -0.22 | -0.4 | 1 / 0 | 0 / 0 | no |
| high break | 1.0×ADR | 3 | none | 48 (47) | -0.43 | -20.8 | -17.5 | -41.6 | DELL -3.6 | -20.8 / -18.3 (n 48) | 7 | 2 / 2 | 89 | 1 | 0 | 2 | -0.22 | -0.4 | 1 / 0 | 0 / 0 | no |
| high break | 1.0×ADR | 4 | none | 48 (47) | -0.46 | -22.3 | -19.0 | -43.1 | DELL -4.6 | -22.3 / -18.3 (n 48) | 7 | 2 / 2 | 96 | 1 | 0 | 2 | -0.22 | -0.4 | 1 / 0 | 0 / 0 | no |
| high break | 1.5×ADR | 1 | trail | 48 (47) | -0.03 | -1.4 | -0.4 | -9.1 | SKM -1.7 | -1.4 / -7.5 (n 48) | 2 | 2 / 2 | 48 | 0 | 0 | 2 | +0.08 | +0.2 | 0 / 0 | 0 / 0 | no |
| high break | 1.5×ADR | 2 | trail | 48 (47) | -0.09 | -4.3 | -3.3 | -12.0 | DELL -2.0 | -4.3 / -7.5 (n 48) | 2 | 2 / 2 | 54 | 0 | 0 | 2 | +0.08 | +0.2 | 0 / 0 | 0 / 0 | no |
| high break | 1.5×ADR | 3 | trail | 48 (47) | -0.11 | -5.3 | -4.3 | -13.0 | DELL -3.0 | -5.3 / -7.5 (n 48) | 2 | 2 / 2 | 55 | 0 | 0 | 2 | +0.08 | +0.2 | 0 / 0 | 0 / 0 | no |
| high break | 1.5×ADR | 4 | trail | 48 (47) | -0.13 | -6.3 | -5.3 | -14.0 | DELL -4.0 | -6.3 / -7.5 (n 48) | 2 | 2 / 2 | 56 | 0 | 0 | 2 | +0.08 | +0.2 | 0 / 0 | 0 / 0 | no |
| high break | 1.5×ADR | 1 | none | 48 (47) | -0.21 | -10.3 | -9.2 | -24.1 | RDW -2.0 | -10.3 / -18.3 (n 48) | 3 | 2 / 2 | 48 | 0 | 0 | 2 | +0.02 | +0.0 | 0 / 0 | 0 / 0 | no |
| high break | 1.5×ADR | 2 | none | 48 (47) | -0.29 | -14.1 | -12.9 | -28.0 | HUT -2.1 | -14.1 / -18.3 (n 48) | 4 | 2 / 2 | 64 | 2 | 0 | 2 | +0.02 | +0.0 | 1 / 0 | 0 / 0 | no |
| high break | 1.5×ADR | 3 | none | 48 (47) | -0.31 | -14.8 | -13.5 | -28.6 | CRSR -3.0 | -14.8 / -18.3 (n 48) | 4 | 2 / 2 | 70 | 2 | 0 | 2 | +0.02 | +0.0 | 1 / 0 | 0 / 0 | no |
| high break | 1.5×ADR | 4 | none | 48 (47) | -0.27 | -12.9 | -11.7 | -26.8 | DELL -4.0 | -12.9 / -18.3 (n 48) | 4 | 2 / 2 | 72 | 2 | 0 | 2 | +0.02 | +0.0 | 1 / 0 | 0 / 0 | no |
| 620 prox | lane's own | 1 | trail | 188 (180) | -0.31 | -58.0 | -51.0 | -78.4 | RDW -2.7 | -58.0 / -58.0 (n 188) | 9 | 1 / 4 | 188 | 0 | 0 | 8 | -1.00 | -8.0 | 0 / 0 | 15 / 5 | baseline |
| 620 prox | lane's own | 2 | trail | 184 (176) | -0.44 | -80.5 | -64.3 | -100.9 | MRVL -6.2 | -80.5 / -54.0 (n 184) | 12 | 2 / 4 | 284 | 3 | 16 | 8 | -1.53 | -12.3 | 2 / 4 | 19 / 5 | no |
| 620 prox | lane's own | 3 | trail | 183 (175) | -0.50 | -91.5 | -74.1 | -111.8 | MRVL -7.9 | -91.5 / -53.0 (n 183) | 13 | 2 / 4 | 321 | 4 | 26 | 8 | -1.79 | -14.3 | 3 / 4 | 20 / 5 | no |
| 620 prox | lane's own | 4 | trail | 182 (174) | -0.53 | -96.3 | -79.2 | -116.7 | MRVL -8.9 | -96.3 / -52.0 (n 182) | 13 | 2 / 4 | 331 | 4 | 32 | 8 | -1.92 | -15.3 | 4 / 4 | 21 / 5 | no |
| 620 prox | lane's own | 1 | none | 188 (180) | -0.50 | -94.1 | -82.9 | -115.6 | RDW -2.7 | -94.1 / -94.1 (n 188) | 12 | 1 / 4 | 188 | 0 | 0 | 8 | -1.00 | -8.0 | 0 / 0 | 15 / 5 | baseline |
| 620 prox | lane's own | 2 | none | 182 (175) | -0.75 | -136.7 | -111.9 | -158.3 | MRVL -6.2 | -136.7 / -88.1 (n 182) | 19 | 2 / 4 | 302 | 7 | 28 | 8 | -1.67 | -13.4 | 2 / 4 | 21 / 5 | no |
| 620 prox | lane's own | 3 | none | 179 (173) | -0.96 | -171.8 | -145.0 | -193.3 | MRVL -9.3 | -171.8 / -84.5 (n 179) | 20 | 2 / 4 | 358 | 10 | 46 | 8 | -1.93 | -15.5 | 4 / 4 | 24 / 5 | no |
| 620 prox | lane's own | 4 | none | 177 (171) | -1.00 | -177.8 | -148.7 | -199.4 | MRVL -10.3 | -177.8 / -82.5 (n 177) | 21 | 2 / 4 | 382 | 14 | 63 | 8 | -2.06 | -16.5 | 5 / 4 | 26 / 5 | no |
| 620 prox | 0.75×ADR | 1 | trail | 203 (194) | -0.05 | -11.0 | +0.0 | -33.3 | SYRE -3.7 | -15.3 / -58.0 (n 188) | 15 | 2 / 4 | 203 | 0 | 0 | 12 | -0.50 | -6.0 | 0 / 0 | 0 / 1 | no |
| 620 prox | 0.75×ADR | 2 | trail | 203 (194) | -0.16 | -31.6 | -19.9 | -53.9 | SYRE -4.7 | -35.6 / -58.0 (n 188) | 15 | 2 / 4 | 268 | 1 | 15 | 12 | -0.84 | -10.1 | 5 / 5 | 0 / 1 | no |
| 620 prox | 0.75×ADR | 3 | trail | 203 (194) | -0.22 | -43.7 | -31.9 | -66.0 | SYRE -5.7 | -47.7 / -58.0 (n 188) | 15 | 2 / 4 | 294 | 2 | 20 | 12 | -0.97 | -11.7 | 7 / 5 | 0 / 1 | no |
| 620 prox | 0.75×ADR | 4 | trail | 203 (194) | -0.25 | -49.8 | -37.7 | -72.0 | SYRE -6.7 | -53.7 / -58.0 (n 188) | 15 | 2 / 4 | 304 | 3 | 23 | 12 | -1.06 | -12.7 | 7 / 5 | 0 / 1 | no |
| 620 prox | 0.75×ADR | 1 | none | 203 (194) | -0.27 | -54.9 | -41.6 | -80.3 | SYRE -3.7 | -54.2 / -94.1 (n 188) | 18 | 3 / 4 | 203 | 0 | 0 | 12 | -0.41 | -5.0 | 0 / 0 | 0 / 1 | no |
| 620 prox | 0.75×ADR | 2 | none | 203 (194) | -0.50 | -101.0 | -84.9 | -126.4 | SYRE -4.7 | -102.6 / -94.1 (n 188) | 24 | 3 / 4 | 314 | 10 | 37 | 12 | -0.76 | -9.1 | 6 / 6 | 0 / 1 | no |
| 620 prox | 0.75×ADR | 3 | none | 203 (194) | -0.69 | -139.6 | -120.6 | -165.0 | MRVL -6.6 | -139.2 / -94.1 (n 188) | 26 | 3 / 4 | 372 | 16 | 63 | 12 | -0.48 | -5.7 | 8 / 6 | 0 / 1 | no |
| 620 prox | 0.75×ADR | 4 | none | 203 (194) | -0.74 | -149.3 | -129.4 | -174.7 | ZBRA -7.0 | -148.9 / -94.1 (n 188) | 27 | 3 / 4 | 402 | 23 | 82 | 12 | -0.56 | -6.7 | 8 / 6 | 0 / 1 | no |
| 620 prox | 1.0×ADR | 1 | trail | 203 (194) | -0.05 | -10.8 | -3.3 | -27.5 | WYFI -3.2 | -13.9 / -58.0 (n 188) | 9 | 2 / 4 | 203 | 0 | 0 | 12 | -0.53 | -6.4 | 0 / 0 | 0 / 1 | no |
| 620 prox | 1.0×ADR | 2 | trail | 203 (194) | -0.11 | -22.5 | -15.0 | -39.2 | WYFI -4.2 | -24.7 / -58.0 (n 188) | 9 | 2 / 4 | 248 | 0 | 14 | 12 | -0.85 | -10.1 | 5 / 5 | 0 / 1 | no |
| 620 prox | 1.0×ADR | 3 | trail | 203 (194) | -0.14 | -29.3 | -21.6 | -46.0 | WYFI -5.2 | -31.5 / -58.0 (n 188) | 9 | 2 / 4 | 259 | 2 | 18 | 12 | -0.93 | -11.1 | 7 / 5 | 0 / 1 | no |
| 620 prox | 1.0×ADR | 4 | trail | 203 (194) | -0.16 | -32.0 | -24.3 | -48.7 | WYFI -6.2 | -34.1 / -58.0 (n 188) | 9 | 2 / 4 | 265 | 2 | 19 | 12 | -1.01 | -12.1 | 7 / 5 | 0 / 1 | no |
| 620 prox | 1.0×ADR | 1 | none | 203 (194) | -0.33 | -67.2 | -50.5 | -86.3 | RARE -9.0 | -64.7 / -94.1 (n 188) | 15 | 3 / 4 | 203 | 0 | 0 | 12 | -0.49 | -5.9 | 0 / 0 | 0 / 1 | no |
| 620 prox | 1.0×ADR | 2 | none | 203 (194) | -0.55 | -110.8 | -91.0 | -129.8 | RARE -9.0 | -107.6 / -94.1 (n 188) | 18 | 3 / 4 | 292 | 11 | 41 | 12 | -0.49 | -5.9 | 6 / 6 | 0 / 1 | no |
| 620 prox | 1.0×ADR | 3 | none | 203 (194) | -0.58 | -118.6 | -97.1 | -137.7 | RARE -9.0 | -115.5 / -94.1 (n 188) | 19 | 3 / 4 | 328 | 19 | 67 | 12 | -0.58 | -6.9 | 8 / 6 | 0 / 1 | no |
| 620 prox | 1.0×ADR | 4 | none | 203 (194) | -0.63 | -127.0 | -105.5 | -146.0 | RARE -9.0 | -123.8 / -94.1 (n 188) | 19 | 3 / 4 | 343 | 25 | 76 | 12 | -0.66 | -7.9 | 8 / 6 | 0 / 1 | no |
| 620 prox | 1.5×ADR | 1 | trail | 203 (194) | -0.03 | -5.2 | -2.4 | -16.3 | WYFI -2.5 | -7.2 / -58.0 (n 188) | 3 | 2 / 4 | 203 | 0 | 0 | 13 | -0.40 | -5.2 | 0 / 0 | 0 / 0 | no |
| 620 prox | 1.5×ADR | 2 | trail | 203 (194) | -0.04 | -8.3 | -5.4 | -19.4 | WYFI -3.5 | -10.3 / -58.0 (n 188) | 3 | 2 / 4 | 222 | 0 | 5 | 13 | -0.49 | -6.3 | 3 / 3 | 0 / 0 | no |
| 620 prox | 1.5×ADR | 3 | trail | 203 (194) | -0.05 | -9.5 | -6.6 | -20.7 | WYFI -4.5 | -11.6 / -58.0 (n 188) | 3 | 2 / 4 | 224 | 0 | 6 | 13 | -0.49 | -6.3 | 3 / 3 | 0 / 0 | no |
| 620 prox | 1.5×ADR | 4 | trail | 203 (194) | -0.05 | -10.5 | -7.6 | -21.7 | WYFI -5.5 | -12.6 / -58.0 (n 188) | 3 | 2 / 4 | 225 | 0 | 6 | 13 | -0.49 | -6.3 | 3 / 3 | 0 / 0 | no |
| 620 prox | 1.5×ADR | 1 | none | 203 (194) | -0.32 | -64.7 | -56.2 | -77.4 | RARE -6.0 | -64.3 / -94.1 (n 188) | 7 | 3 / 4 | 203 | 0 | 0 | 13 | -0.29 | -3.7 | 0 / 0 | 0 / 0 | no |
| 620 prox | 1.5×ADR | 2 | none | 203 (194) | -0.41 | -83.2 | -73.3 | -95.9 | RARE -6.0 | -80.8 / -94.1 (n 188) | 7 | 3 / 4 | 259 | 13 | 41 | 13 | -0.18 | -2.3 | 8 / 6 | 0 / 0 | no |
| 620 prox | 1.5×ADR | 3 | none | 203 (194) | -0.42 | -84.8 | -74.9 | -97.5 | RARE -6.0 | -82.5 / -94.1 (n 188) | 7 | 3 / 4 | 274 | 20 | 63 | 13 | -0.18 | -2.3 | 8 / 6 | 0 / 0 | no |
| 620 prox | 1.5×ADR | 4 | none | 203 (194) | -0.43 | -87.8 | -77.9 | -100.5 | RARE -6.0 | -85.5 / -94.1 (n 188) | 7 | 3 / 4 | 277 | 21 | 63 | 13 | -0.18 | -2.3 | 8 / 6 | 0 / 0 | no |

**The ten cells that clear ERA A, and what carries them (ERA A):**

| cell (EP-low reclaim, trail exit) | n | total R | drop best 2 | drop best 3 | top names | by alert month (R / n) | re-entries: attempts fired → their R | ERA B n · mean · losers |
|---|---:|---:|---:|---:|---|---|---|---|
| lane's own stop × up to 2 re-entries | 164 | +30.8 | **+0.5** | −13.4 | KURA +16.1 · TE +14.2 · NRIX +13.8 · BLSH +13.6 · EFOR +9.9 | May +10.0/46 · Jun +12.1/41 · Jul −1.1/28 · Aug +9.8/49 | try 2: 73 → +19.0 · try 3: 22 → +24.0 (try 1: 164 → −12.1) | 7 · −0.68 · 5 of 7 |
| lane's own stop × up to 3 re-entries | 163 | +41.9 | +11.6 | −2.2 | same | May +9.8/46 · Jun +10.8/41 · Jul −1.1/28 · Aug +22.4/48 | + try 4: 5 → +8.1 | 7 · −0.68 · 5 of 7 |
| 1.0×ADR × 1 try | 202 | +32.2 | +15.6 | +9.4 | EFOR +8.7 · TE +7.9 · BHVN +6.2 · BLSH +5.6 · KURA +5.2 | May +21.6/60 · Jun +5.3/44 · Jul +2.6/31 · Aug +2.8/67 | — | 13 · −0.34 · 10 of 13 |
| 1.0×ADR × up to 1 re-entry | 202 | +31.0 | +14.3 | +8.2 | same | May +25.8 · Jun +1.8 · Jul −0.5 · Aug +3.8 | try 2: 33 → −1.2 | 13 · −0.34 · 9 of 13 |
| 1.0×ADR × up to 2 / 3 re-entries | 202 | +33.6 | +16.9 | +10.7 | same | May +25.8 · Jun +0.8 · Jul +3.1 · Aug +3.8 | try 2: 33 → −1.2 · try 3: 2 → +2.6 | 13 · −0.34 · 9 of 13 |
| 1.5×ADR × 1 try | 202 | +21.0 | +9.9 | +5.7 | EFOR +5.8 · TE +5.3 · BHVN +4.1 · BLSH +3.7 · KURA +3.4 | May +14.2/60 · Jun +3.0/44 · Jul +0.4/31 · Aug +3.4/67 | — | 13 · −0.22 · 10 of 13 |
| 1.5×ADR × up to 1 / 2 / 3 re-entries | 202 | +25.6 | +14.5 | +10.4 | same | May +17.7 · Jun +2.8 · Jul +1.7 · Aug +3.5 | try 2: 14 → +4.7 | 13 · −0.22 · 10 of 13 |

Plain words: with a one-day-range stop the EP-low reclaim is stopped on 50 of 202 ERA A campaigns instead of 95 of
171 under the lane's own stop, and only 33 of those 50 ever re-enter — the re-entries net −1.2R. The money is the
first try, and mostly May. With the lane's own stop, 87 of 163 campaigns are stopped on the first try and the re-entry
buys the same reclaim a day or two later on a stop a fraction as wide — KURA, TE, NRIX and BLSH pay 13–16R each
(+57.7R between them) and the other 159 campaigns net −15.8R. In ERA B the first try under a one-day-range stop loses
on 10 of 13 EPs (best +1.1R on QCOM, worst −1.0R); the lane's own stop with re-entries loses on 5 of 7, and one of the
two positives (ERO +0.23R) is only a horizon mark three sessions after its fire.

**The big winners (descriptive).** Of the 7 big-runner EPs, 3 fired on the EP-low reclaim (TE, EFOR, NRIX): all 3 end
≥ 3R under the lane's own stop with re-entries (NRIX needs two re-entries: −1, −1, +15.8), 2 of 3 under the 1×ADR
stop (TE +7.9, EFOR +8.7; NRIX −1.0 then a −0.1 re-entry), 2 of 3 at 1.5×ADR. On the close reclaim (HQ, ALOY fired)
1 of 2 ends ≥ 3R under the lane's stop, 0.75×ADR or 1×ADR (ALOY +3.2R at 1×ADR; HQ +2.3R) and 0 of 2 in that
pattern's best cell (1.5×ADR); on the 620 proximity (TE, ALOY, EFOR, NRIX fired) 2 of 4 in its best cell (TE +7.8R,
EFOR +8.9R at 1×ADR; ALOY and NRIX are stopped) and up to 3 of 4 under the lane's stop with re-entries; on the high
break (ARM, VPG) 2 of 2 at 0.75–1.5×ADR (ARM +4.8R, VPG +6.8R at 1×ADR) and 1 of 2 under the lane's own stop with the
trail. So a one-day-range stop keeps most of the winners on every pattern (7 of the 11 runner fires at 1×ADR, as the
rerun found) — and the same cells still lose overall on three of the four patterns because the other campaigns pay
for it. Campaigns ending ≥ 3R in ERA A: 11 of 202 (5.4%) at
1×ADR × 1 try, 17 of 163 (10.4%) under the lane's stop × 3 re-entries — both far under the rerun's tail bar of 18.9%.

**TEAM 2026-08-07, walked by hand in each pattern's best cell.** TEAM did not fire on the EP-low reclaim or the
high break. Close reclaim, best cell 1.5×ADR × 1 try × trail: in 149.39 on 08-10 at 09:40 ET, stop 135.27 (9.5%
wide), trail exit **+1.91R** (peak +3.5R). 620 proximity, best cell 1.5×ADR × 1 try × trail: in 148.06 at 10:50 ET,
stop 133.94 (9.5%), trail exit **+2.01R** (peak +3.6R). Under the lane's own 2–3% stop the same fires read +5.0R /
+7.6R at session 10 in the rerun — a wide stop shrinks TEAM's R by 3–4× and it never needed a re-entry.

## What this does not answer

- **ERA B is 16 campaigns, 13 on the EP-low reclaim, 7 readable under the lane's own stop.** It can contradict a
  direction (it does, 10 of 13 losers) but cannot carry a bar; the 7 lane-recorded first fires that abstain (no cached
  day 0) were stops in the lane's own records, so the ERA B read here is if anything too kind.
- **Whether the daily-range stop's edge is May's tape or the rule change.** The 1×ADR one-try cell is +21.6R on 60
  May campaigns and +2.6R to +5.3R a month after; the rerun's fork (a) — re-score May–Aug under today's rules — is
  the test, and this study does not run it.
- **The rerun's tail-first bar.** This study's bar (pre-registered by the task) has no tail leg; under the rerun's
  (kept ≥ 3R at 3× the incumbent rate = 18.9%) none of the ten cells clears (5.4% and 10.4%).
- **Tighter stops than the lane's.** 0.25 / 0.5 × ADR were not in this grid; the 09-02 headline cell (0.25×ADR × 3 on
  the May–Aug subset) is not re-read here. The lane's-own-stop × re-entries cells are its nearest analog on the whole
  population: drop-2 +0.5R / +11.6R, drop-3 negative.
- **Blind sessions.** 290 (ticker, session) pairs across every chain had no stored minute bars where a same-pattern
  search needed them; a blind session can hide a re-entry, never invent one. No attempts=1 cell has a window, so ERA
  B's sign on those cells is fully observed; on the re-entry cells the hidden re-entries on 2 ERA B names would have
  to net more than +4.4R to flip ERA B's sign, and ERA A's re-entry attempts under a 1×ADR stop net −32.1R over 169
  attempts (all patterns) — the missing data cannot decide a cell, so no bars were pulled.
- **Fill reality and sizing.** The replay fills the reclaim bar's close and the stop at the level (gap-throughs at
  the open); the live 20% notional cap and per-stock character are not modelled (Axis 7, his).
- **Same-day re-entry** is structurally excluded (the lane's day-2+ boundary, ruled 2026-08-30); exits are the lane's
  two arms only (the +2R partial is not an arm, operator 08-30); one global ADR multiple.
- **"Hold to horizon" was read as the lane's 20-session M-none arm**, marked at 09-25 where the window was cut; a
  literal hold to 09-25 is a different, unmeasured instrument.

## THE LINE

Entry and exit discipline, stops, re-entry rules, sizing and every threshold are the operator's sole authority. This
study measured a pre-registered grid on captured files and reports it: no prod access, no bars pulled, no toggle, no
table, no deploy, no PLAN.md line, no live code touched. Every cell is a measurement; the lane ruling is his.

---
*Population: the rerun's 277 live-source `mi_ep_alerts` campaigns 2026-05-01 → 09-11 (eras split at 08-22), 632
first-attempt fires. Instrument: the 09-01 walker's fires, the 09-02 retry test's re-entry shapes, the lane's own
`compute_settlement`, all imported. Related: `327_real_ep_rerun_2026-09-26.md`, `327_delayed_entry_diagnosis_2026-09-26.md`,
`545_retry_test_2026-09-02.md`; PLAN #327, #545, #616.*
