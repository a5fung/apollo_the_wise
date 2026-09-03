# exit_tune_bull_regime_read — run 1 at stamped-Bull n=10 (2026-09-02)

**VERDICT: the STOP conclusions transfer to Bull unchanged — Bull trades still die on the entry day
(7 of 10) behind a stop that is 0.42 of one normal day's range (7 of 7 under a day's range). The
PARTIAL, BREAKEVEN/TRAIL and STOP-FLOOR conclusions cannot be graded in Bull, because every Bull
trade ran under the post-08-05 exit stack and every non-Bull trade but one ran bare — the
comparison is of exit stacks, not tapes, and n (10 vs 16; era-matched 3 vs 1) cannot separate them.**
The "every conclusion we hold is a non-bull conclusion" caveat is **re-worded, not retired** (§9).

**MEASUREMENT ONLY. No exit rule, stop width, profit-take level or sizing changed. Any change is
CHANGE_PROCESS + #151 harness + operator sign-off (THE LINE).** Runs inside #545 (Phase 4); reported
into `docs/design/545_entry_exit_program_v2_2026-09-02.md` Axis 6.

## 1. The decision this serves

`data_gated_reviews.yaml :: exit_tune_bull_regime_read` (threshold 8, predicate = 10 on 09-02). Its
three questions, in the entry's own words: (1) do trades still die on the entry day in Bull, or run;
(2) does the +2R partial still look like the best rule, or does it cap runners — the operator's
2026-08-01 hypothesis (*"runners probably happen more often in bull markets… let runners go in bull
markets"*); (3) does the stop-floor refutation (08-06) still hold. What would change a decision: a
Bull cell where trades run and the partial measurably caps them would argue for a regime-conditional
harvest; a Bull cell that dies on day 0 like the rest says the tape is not the lever. Win rate is a
selection measure, not an exit measure — reported as a column, never ranked on.

## 2. Method / population

**Population:** the 26 closed real-money `mi_live_trades` (`account_mode='live'`, `status='closed'`,
`signal_type='magna53'`, first attempts), alerts 2026-07-06 → 08-28, from the 09-01 read-only capture
`scripts/ep_replay_data/_pull2_out.txt` (trades + exit legs + `mi_market_regime` + `mi_daily_closes`)
and `_pull4_min.tsv.gz` (RTH minute bars, alert day). **No prod query was run for this document, $0.**
Runner: `scripts/probes/_545p4_bull_read.py` → `_545p4_bull_read_out.txt` (offline; reads the two
committed capture files only; re-runnable by anyone).
`scripts/live_rules.py --drift-only` run first (1 drift finding, in `545_retry_test_2026-09-02.md`,
not in this scope).

**Regime basis = the ENTRY STAMP (`mi_live_trades.regime`), and here is the mechanism, not just the
08-08 ruling.** The nightly engine (`scheduler.py::_nightly_data_pull`, 17:00 ET) writes the regime
row for THAT date (`regime.py:534`); the ORB monitor at 09:31 reads `regime_date <= today ORDER BY
regime_date DESC LIMIT 1` (`live_tracker.py:522`). So the stamp is the **prior session's** regime —
what was knowable at the decision — and the date-join is the **entry day's own close**, which
includes the entry day's price action (look-ahead). The 08-17 doc called the difference "revised
after entry"; it is a one-session lag by construction. The rule "stamp = the regime row of the
prior session" **reproduces all 22 stamps already on record** (20 from the 08-17 doc, PLTR = Choppy
and ETON = Bull from the 08-24 capture). The capture has no `regime` column, so four stamps are
**inferred from that rule: ABCL, AMLX, SOLS = Bull; CRWD = Choppy.** They match tonight's prod
counts (Bull 10 · Choppy 8 · Correcting 7 · Crisis 1) and the 5/1/1 disagreement pattern in the
brief. Confirm with `scripts/probes/_545p4_bull_capture.sql` Q1.

**Era split (mechanics-based, the 08-22 doc's boundaries; never averaged across):** A = fills ≤ 08-04
(ORB-low stop; the +2R partial was deployed 08-01 but could not execute on MAGNA53 brackets until
the leg-safe path went live 08-05) n=15 · B = 08-05 → 08-14 (ORB-low stop + +2R partial 1/3 + stop
to breakeven at the broker — live by 08-14, not yet on FIGS 08-07 — + daily trail) n=7 · C = fills ≥ 08-17 (entry − 2R stop at half size,
target pinned, same partial/BE/trail) n=4. The v2 design doc §2 splits by deploy date (A <08-01
n=12 / B 08-01→08-15 n=10 / C n=4); the two differ only on BLZE, BTDR, PLTR (08-04).

**R basis = realized per-share: `pnl / (shares × (fill − hard_stop))`** — the sell-discipline
recorder's `realized_r`, so every cell reconciles to the 08-17/08-22 docs (PLTR +3.42R, MRVL −0.95R,
MANE −0.23R, era-A-ex-PLTR −13.15R all reproduce). ⚠ **The brief's recipe
`COALESCE(risk_dollars_actual, risk_dollars)` is the PRE-CAP budget on 24 of 26 rows** (db.py:898 —
the 20 %-of-equity cap truncates shares and never rewrites `risk_dollars`): on the three capped rows a
full stop-out reads NET −0.32R, TEAM −0.50R, FTNT −0.55R. `risk_dollars_actual` = `shares ×
(orb_high − hard_stop)` (verified on both rows that carry it: CRWD 28.92, SOLS 48.72) and is
reconstructable for all 26 with no NULLs. Both bases are shown in §3.

**MFE:** minute bars between the fill minute and the exit minute (fill and exit bars excluded) +
daily highs of full in-hold days + the recorder's peaks where a prior doc/capture quoted one (PLTR
180.18, ETON 59.79 from the 08-24 capture; NET/FIGS/TEAM/FRMI/BW/MRVL/MANE/QBTS/SMCI/NVCR/CRCL/HUT/
TSEM/THC/WKC/FTNT from the 08-17/08-22 docs), max of the two. The close-day daily high is post-exit
contaminated and is never used. Peaks are floors under ~10 min of hold.

**Measurement traps carried:** the R-unit is not a unit (stop widths 0.15–1.85 ADR); every peak is
shown in ADR20 units beside R. `fwd_5d_pct` / `max_high_*` are MFE — not used. Live and paper never
pool — paper is absent from every table here.

## 3. Brief fact-check (26 closed live) — what survives, what moves with the basis

| claim (brief) | per-share basis (this doc) | budget basis (brief's recipe) | n |
|---|---|---|---|
| 26 closed, 5 winners | 26 · 5 (PLTR, ABCL, AMLX, ETON, CRWD) | same | 26 |
| best +3.31R (PLTR) | **+3.42R** PLTR | +3.31R | 26 |
| worst −1.18R (WKC) | **−1.09R** BW | −1.18R WKC | 26 |
| none reached 4R | none REALIZED ≥4R; **3 reached ≥4R unrealized** (MANE 7.92, ABCL 5.70, PLTR 5.39) | same | 26 |
| cohort total | **−11.27R** (cash −$165.65) | −7.82R (understates: 3 capped stop-outs read −0.3 to −0.6R) | 26 |
| stamp Bull 10 / Choppy 8 / Correcting 7 / Crisis 1 | reproduced by the prior-session rule | — | 26 |
| stamp vs join disagree on 7 | **8** — FTNT (07-30, Crisis → Correcting) is the eighth; the other seven: WULF, BLZE, BTDR, PLTR, CRWD Choppy → Bull; TSEM Correcting → Choppy; SOLS Bull → Choppy | — | 26 |
| "era-C non-bull trade = SOLS" (v2 Axis 6) | **SOLS is stamped Bull (08-27's row); CRWD is the era-C non-bull trade** (stamped Choppy from 08-26's row, joins Bull) | — | 4 |

## 4. (a) Per-trade forensic — the Bull cell, plus the era-C match and the spanner

| tkr | fill | era | stamp / join | stop % · /ADR | R real | R budget | peak R · ADR | hold | exit |
|---|---|---|---|---|---|---|---|---|---|
| FIGS | 08-07 | B | Bull / Bull | 2.0 · 0.41 | −0.37 | −0.14 | +2.90 · 1.18 | 1d, 19 min | partial +1.13R at 09:35 (target +2R); remainder stopped 15.16 behind the ORIGINAL 15.19 stop — breakeven never armed (#548 defect 2) |
| NET | 08-07 | B | Bull / Bull | 1.6 · 0.31 | −1.00 | −0.32 | +1.68 · 0.51 | 1d, 59 min | stop |
| TEAM | 08-07 | B | Bull / Bull | 2.7 · 0.42 | −1.02 | −0.50 | +1.08 · 0.46 | 1d, 13 min | stop; closed +16.8 % ten sessions later |
| ABCL | 08-10 | B | Bull / Bull | 6.3 · 0.83 | **+2.68** | +2.66 | +5.70 · 4.75 | 11d | partial 10.08 · trailed stop 10.65 |
| BW | 08-11 | B | Bull / Bull | 4.7 · 0.58 | −1.09 | −1.02 | 0.00 · 0.00 | 1d, 7 s | stop |
| FRMI | 08-11 | B | Bull / Bull | 3.3 · 0.36 | −0.98 | −0.65 | +0.04 · 0.02 | 1d, 35 s | stop |
| ETON | 08-14 | B | Bull / Bull | 4.0 · 0.66 | +0.52 | +0.40 | +2.09 · 1.38 | 1d, 14 min | BE stop 55.05 at ~0R, then the #566 defect fill +$21.89 |
| AMLX | 08-18 | C | Bull / Bull | 10.3 · 1.58 | **+1.26** | +1.29 | +3.50 · 5.52 | 10d | partial 33.47 · trailed stop 34.45 |
| MRVL | 08-19 | C | Bull / Bull | 4.7 · 0.70 | −0.95 | −0.87 | +0.35 · 0.25 | 1d, 31 min | stop |
| SOLS | 08-28 | C | Bull / Choppy | 6.1 · 1.85 | −1.00 | −1.01 | +0.18 · 0.33 | 2d | stop |
| CRWD | 08-27 | C | **Choppy** / Bull | 5.6 · 1.29 | +0.40 | +0.50 | +1.31 · 1.70 | 2d | partial 227.72 · BE stop 213.30 |
| PLTR | 08-04 | A→B | **Choppy** / Bull | 3.9 · 0.86 | **+3.42** | +3.31 | +5.39 · 4.62 | 12d | partial 165.69 · trailed stop 170.39 |

Peak sources: bars for the same-day exits; daily in-hold highs for ABCL/AMLX/PLTR (all three ran
past their partial); recorder values where higher. All 26 rows: `scripts/probes/_545p4_bull_read_out.txt` §2.

## 5. (c0) The regime cells, entry-stamped — and the confound on every row

| cell | n | sum R | mean · median | wins | day-0 exits | hold med · max | peak R mean · max | ≥2R · ≥4R peaks | peak ≥1.5 ADR | eras |
|---|---|---|---|---|---|---|---|---|---|---|
| **Bull (stamped)** | 10 | **−1.95** | −0.19 · −0.97 | 3 | 7 | 1d · 11d | +1.75 · +5.70 | 4 · 1 | 2 | **B×7 C×3** |
| non-Bull (stamped) | 16 | −9.33 | −0.58 · −1.00 | 2 | 10 | 1d · 12d | +1.82 · +7.92 | 5 · 2 | 4 | **A×15 C×1** |
| · Choppy | 8 | −1.50 | −0.19 · −1.00 | 2 (PLTR, CRWD) | 5 | 1d · 12d | +2.33 · +7.92 | 2 · 2 | 2 | A×7 C×1 |
| · Correcting | 7 | −6.80 | −0.97 · −1.00 | 0 | 4 | 1d · 4d | +1.50 · +3.74 | 3 · 0 | 2 | A×7 |
| · Crisis | 1 | −1.03 | — | 0 | 1 | 1d | +0.07 | 0 · 0 | 0 | A×1 |
| non-Bull era A excl PLTR (the 08-06 baseline) | 14 | **−13.15** | −0.94 · −1.01 | 0 | 10 | 1d · 4d | +1.64 · +7.92 | 3 · 1 | 1 | A×14 |
| **era-C matched: Bull** | 3 | −0.70 | −0.23 · −0.95 | 1 (AMLX) | 1 | 2d · 10d | +1.34 · +3.50 | 1 · 0 | 1 | C |
| **era-C matched: non-Bull** | 1 | +0.40 | — | 1 (CRWD) | 0 | 2d | +1.31 | 0 · 0 | 1 | C |
| sensitivity — Bull by DATE-JOIN | 14 | −0.17 | −0.01 · −0.97 | 5 | 10 | 1d · 12d | +1.90 · +5.70 | 5 · 2 | 4 | A×4 B×7 C×3 |
| sensitivity — non-Bull by DATE-JOIN | 12 | −11.10 | −0.93 · −1.01 | 0 | 7 | 1d · 4d | +1.75 · +7.92 | 3 · 1 | 1 | A×11 C×1 |

🔴 **THE CONFOUND, said on the numbers:** Bull is B×7 + C×3 and has **no era-A trade**; non-Bull
is A×15 + C×1. So "Bull −1.95R vs non-Bull −9.33R" is "partial + breakeven + trail vs a bare
ORB-low stop" as much as it is "Bull vs not." The only era-matched contrast is era C: **3 vs 1**,
which decides nothing. The date-join sensitivity moves PLTR (the best trade) and CRWD into Bull and
SOLS out — the Bull cell's sum swings from −1.95R to −0.17R on which basis is used, which is why the
basis had to be settled first (§2).

**What IS era-robust in this table:** the day-0 exit rate. Bull 7 of 10 (6 of 7 under the ORB-low
stop, 1 of 3 under the 2R stop); non-Bull 10 of 16. Same rate, same three sub-10-minute deaths
(BW 7 s, FRMI 35 s — the 9:31 whipsaw, cf. HUT 51 s in July). The tape did not change that.

## 6. (b) The partial, priced on REAL fills — no simulation

The 34-candidate grid (`_508_exit_rule_replay.py`) needs a fresh 4-TSV snapshot (the 08-17/08-22
snapshots lived in session scratchpads and are gone; `_545p4_bull_capture.sql` Q3–Q6 re-creates it).
What n=10 supports without a harness is exact: every trade whose partial fired live, actual R
against **holding every share to the SAME terminal leg price** (the trailed/BE stop that actually
fired) — the partial's cost or benefit with nothing modelled.

| tkr | stamp | era | peak R | actual R | hold-all R | partial effect | what happened |
|---|---|---|---|---|---|---|---|
| FIGS | Bull | B | +2.90 | −0.37 | −1.10 | **+0.73** | banked +1.13R on 1/3 three minutes after fill (target was +2R); remainder stopped 15.16 behind the original 15.19 stop (breakeven not yet live) |
| ABCL | Bull | B | +5.70 | +2.68 | +3.02 | −0.34 | 1/3 sold at +2R; the TRAIL took the rest at +3.0R |
| AMLX | Bull | C | +3.50 | +1.26 | +1.36 | −0.10 | same shape, 2R-stop unit |
| PLTR | Choppy (join Bull) | A→B | +5.39 | +3.42 | +3.69 | −0.27 | same shape |
| CRWD | Choppy (join Bull) | C | +1.31 | +0.40 | −0.00 | +0.40 | partial then BE scratch |
| ETON | Bull | B | +2.09 | +0.52 | −0.07 | (+0.59) | **defect, excluded**: BE stop closed all 17 shares at 55.05 (~0R) at 09:45 ET — the post-fill low was 54.80, the 53.01 ORB-low stop was never touched, and the 09:32 bar had printed 59.79; the 5-share limit filled at 59.58 six hours later with the position flat (#566) |

- **Net over the 5 real firings: +0.42R** (Bull-stamped three: +0.29R). The partial **cost 0.10–0.34R
  on each of the three runners and returned +0.73R on the one collapse** — a wash at this n, and the
  "caps runners" half is bounded by construction (a third of the position gives up at most the
  trail-minus-2R distance).
- **The TRAIL, not the partial, is what carried the Bull winners**: ABCL and AMLX exited on stops
  trailed to 10.65 / 34.45 against hard stops of 8.40 / 27.09 — a mechanism that did not exist in
  era A, where MANE (+7.92R peak), QBTS (+3.74R), SMCI (+3.21R) and NVCR (+2.00R) gave back all of
  it. PLTR, entered in a Choppy stamp and managed under era B, did exactly what ABCL did.
- **The BREAKEVEN arm has one visible cost**: ETON's BE stop closed the position at ~0R at 09:45 on
  day 0 (post-fill low 54.80; the 53.01 ORB-low stop was never touched) and the stock closed that day
  +6.6 % and ran +8 % over ten sessions (§7). One case; recorded, not weighed.
- On the operator's hypothesis: the three biggest ADR-normalised runs in the live record (ABCL 4.75,
  AMLX 5.52, PLTR 4.62 ADR) were all entered on Bull DAYS (2 of 3 by stamp); the one non-Bull-stamped
  trade ≥ 4 ADR out of 16 is PLTR, itself a Bull day by join. The 08-17 read (n=6/7)
  pointed the other way; this one points with the hypothesis — **on n=3, and multi-week holds exist
  only under the trail stack, so even peaks are era-confounded.** Not a finding; a direction.

## 7. (e) Stop geometry and the floor — the stop finding holds; the floor rescued one trade, not three

Stop width vs the stock's own 20-day range (`stop/ADR20`):

| cell | n | min · median · max | under one day's range |
|---|---|---|---|
| Bull, ORB-low stop (era B) | 7 | 0.31 · **0.42** · 0.83 | 7 of 7 |
| non-Bull, ORB-low stop (era A) | 15 | 0.15 · 0.55 · 1.19 | 12 of 15 |
| Bull, 2R stop (era C) | 3 | 0.70 · 1.58 · 1.85 | 1 of 3 |
| non-Bull, 2R stop (era C) | 1 | 1.29 | 0 of 1 |

The 08-22 finding — the ORB-low stop sits inside one day's noise, uncorrelated with the stock's
character — **holds in Bull at the identical median (0.42).**

**Floored stop, re-run on the 7 Bull ORB-low trades** — `stop_k = min(hard_stop, entry × (1 − k ×
ADR20/100))` (the 08-06 formula; may only widen), floor ALONE (partial off), day 0 walked on minute
bars (the fill bar needs a close below the stop), forward sessions 1–10 at DAILY grain (a daily low
≤ stop = stopped; else exit at the session-10 close), R in the WIDENED unit:

| k | Bull era B (n=7): sum R · wins · day-0 stops · later stops | non-Bull era A ex-PLTR (n=14), same method — the 08-06 calibration set |
|---|---|---|
| 0.0 (ORB low, held to s10) | +0.04 · 2 · 5 · 0 | −14.00 · 0 · 10 · 4 |
| 0.5 | +0.04 · 2 · 5 · 0 | −14.00 · 0 · 9 · 5 |
| 0.75 | +4.33 · 3 · 4 · 0 — TEAM +3.54 (**the one rescue**), ABCL +2.95 and ETON +1.84 (both already survive at k=0) | −14.00 · 0 · 9 · 5 |
| 1.0 | +2.49 · 3 · 3 · 1 (FRMI stopped session 2) | −14.00 · 0 · 9 · 5 |

- **Calibration first:** on the non-Bull 14 this daily-grain method reproduces the 08-06 harness
  exactly — −14.00R at every k, zero winners, and the four day-0 rescues (MANE s1, QBTS s1–2, SMCI
  s3–4, HUT s6) all hit the wider stop within 1–6 sessions. The method is faithful on the set the
  refutation was built on.
- **What the floor actually changed in Bull — one trade at 0.75, two at 1.0.** ABCL and ETON survive
  day 0 under the ORB-low stop itself (k=0 row: 5 day-0 stops, not 7), so they are not rescues. At
  k = 0.75 the floor rescues **TEAM alone**, which then closes session 10 at +16.8 % (the name the
  operator re-entered by hand on 08-07) — the whole +4.29R gap between the k=0.75 and k=0 rows is that
  one trade. At k = 1.0 it also rescues **FRMI, which hits the wider stop on session 2** — the 08-06
  mechanism (survival = delay) repeating. **n = 1–2, direction mixed.**
- **Why this neither re-opens nor answers the question:** (i) one rescue at 0.75×ADR, two at 1.0×ADR
  of which one repeated the delay;
  (ii) R is in the widened unit — at equal dollar risk the position is smaller, so +3.54R on TEAM is
  +3.54 × the risk budget, not +3.54 × the ORB-low R; (iii) the forward walk is daily-grain
  touch/no-touch, not fill-ordered (the tested harness needs the Q6 minute capture to settle it);
  (iv) the "actual" these 7 ran was the era-B stack (−1.25R), whose k=0 floor-alone counterpart is
  +0.04R — the entire gap is ETON, where the BE stop, not the ORB-low stop, ended the trade. **The
  operator's signed 2R stop (era C, 0.70–1.85 ADR wide) is already the live version of this test**:
  AMLX +1.26R, MRVL −0.95R, SOLS −1.00R, CRWD +0.40R. Grade it there, at n, not here.

## 8. (c)(d) Character and holding period — descriptive, cells under 10

| ADR20 tier | Bull | non-Bull |
|---|---|---|
| slow < 3.5 % | n=1 −1.00R (SOLS) | n=2 −2.06R, 0 wins |
| mid 3.5–6.5 % | n=4 −1.87R, 1 win (ETON, defect); peaks +1.94R mean, 0 ≥1.5 ADR | n=6 +0.09R, 2 wins (PLTR, CRWD); 4 ≥1.5 ADR |
| fast > 6.5 % | n=5 +0.92R, 2 wins (ABCL, AMLX); 2 ≥1.5 ADR | n=8 −7.35R, 0 wins; 0 ≥1.5 ADR |

The 08-22 note ("the fast tier is 0-for-11 with the tightest stops") now reads 2-for-5 in Bull and
0-for-8 outside it — the two Bull fast-tier winners are the two trail-managed runners, so this is
the era confound again, not a character finding. **Holding period:** Bull 1d×7 · 2d×1 · 10d×1 ·
11d×1; non-Bull 1d×10 · 2d×4 · 4d×1 · 12d×1. Sub-10-minute deaths: Bull 2 of 10, non-Bull 4 of 16.
Nothing has held 20 sessions in either tape.

## 9. The caveat, re-worded (not retired)

**Old (PLAN #545, the YAML, the roadmap):** *"all 14 closed live trades were taken in
Correcting/Choppy/Crisis and ZERO in Bull, so every conclusion we hold is a non-bull conclusion."*

**New:** *26 closed live trades, 10 entered in a Bull tape (stamped; measured 09-02). What we know
about the STOP — trades die on the entry day, the ORB-low stop sits inside one day's range — holds
in Bull unchanged. What we know about the PARTIAL, the BREAKEVEN/TRAIL and the STOP-FLOOR is
era-confounded: every Bull trade ran under the post-08-05 stack and every non-Bull trade but one
(CRWD) ran bare, so those are exit-STACK conclusions until non-Bull closes under the current stack
accrue (1 today; readable at ~5). A volatility floor rescued one Bull trade at 0.75×ADR (TEAM, which
then ran) and one more at 1.0×ADR (FRMI, which repeated the 08-06 delay and stopped two sessions
later) — n=1–2, direction mixed; the signed 2R stop is the live test.*

**Re-gate (applied to the YAML entry):** threshold 8 → 20 stamped-Bull closes AND ≥ 5 non-Bull
closes entered on/after 2026-08-16 (`LEAST(bull, 4 × nonbull_eraC) ≥ 20`) — the second term is the
cell that breaks the confound; a bigger Bull count alone cannot. Stall clause unchanged (run at
whatever n exists on 2026-11-01).

## 10. What this does not answer

1. **A per-regime exit rule** — blocked by the era confound; the era-matched cell is 3 vs 1.
2. **Whether the +2R partial is the "best available" rule in Bull** — the 34-candidate grid needs a
   fresh snapshot in the engine's shape (`_545p4_bull_capture.sql` Q3–Q6); what is answered here is
   the partial's exact effect on the five trades where it actually fired (+0.42R net).
3. **Whether the stop-floor should return** — one rescue at 0.75×ADR and two at 1.0×ADR (one of them
   the delay mechanism again), in widened-R units on a daily-grain forward walk, neither re-open nor
   answer it. The signed 2R stop is the live test.
4. **The four inferred stamps** (ABCL/AMLX/SOLS Bull, CRWD Choppy) — from a rule that reproduced
   22 of 22; confirmed only by Q1 of the capture. A mismatch moves one trade between cells.
5. **Recorder peaks for the 26** — MFE here is bar-reconstructed plus the values prior docs quoted;
   the recorder's `peak_r`/`peak_adr` (Q3) are canonical. Peaks under ~10 minutes of hold are floors.
6. **Live fill quality** — FIGS's partial filled +1.13R against a +2R target and its stop 3c through;
   ETON's breakeven stop filled 0.3 % through; nothing here quantifies slippage beyond those rows.
7. **Regime-conditional arms (`rgm_*`)** — not re-run; the 08-17 finding (every "let Bull run" arm
   scores the do-nothing baseline because no Bull peak cleared 3R) is now false on ABCL (5.70R) and
   AMLX (3.50R) but cannot be re-scored without the engine snapshot.
8. **Paper** — absent by design; never pooled with live.

## 11. ⚖ THE LINE

Evidence and a re-worded caveat only. No strategy, stop, sizing, target or safeguard was changed;
`data_gated_reviews.yaml` was edited only to record this run and re-key the trigger. Any exit change
is CHANGE_PROCESS + the #151 harness + operator sign-off.
