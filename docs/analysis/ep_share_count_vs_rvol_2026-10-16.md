# Gap-day share count (≥ 9M) vs relative volume — which marks our big runners? (2026-10-16)

**MEASUREMENT ONLY. $0. Local files only (no prod read, no deploy, no commit).** Nothing here changes
or proposes to change the EP score, admission, any threshold, stop, size or safeguard — any such change
is CHANGE_PROCESS and the operator's call (THE LINE). This is a SEPARATE test from the frozen #686 read:
it edits nothing #686 pins (it imports #684's `study.py` read-only, with bytecode writing off) and it
reads no outcome of any scan date on/after 2026-09-04.

## The decision it serves

- **His prompt, 2026-10-15 ("food for thought"),** `docs/methodology/operator_shared_notes.md` §2026-10-15:
  @Muninn on Bonde's "EP 9 million" — *"names which traded 9M+ shares outperform by +0.32 R on avg ...
  extreme relative volume have no reliable edge compared to lower relative volume"* (1992–2024).
- **Question:** on OUR scored EP candidates (#684's population, safeguard-blocked included), does
  gap-day SHARE COUNT separate the big runners better than RELATIVE VOLUME?
- **What hangs on it:** whether a share-count term is worth proposing for his ruling as a later /
  day-2 filter — never for today's 09:31 ORB entry (the full-day count is not known then; §Timing).

---

## PRE-REGISTRATION — written 2026-10-16 10:14–10:40 PDT, BEFORE any outcome was split by volume

Integrity: `scripts/probes/_9m_share_count_1016/prereg.sha256` holds the sha256 of this section's text
(from this heading to the line `END OF PRE-REGISTRATION`), written before `read.py` was run; `read.py`
recomputes it at run time, prints both, and refuses on a mismatch.

### P1. Population — composition stated first (`composition.out`, no outcome read)

- **Rows:** #684's population verbatim — every candidate the gap-day EP scan SCORED
  (`mi_ep_scan_log.ep_score IS NOT NULL`), one row per (ticker, scan_date), scan dates 2026-05-01 ..
  2026-09-03: **n = 670** (546 names, 86 scan dates). Alerted 307 / scored-not-alerted 363.
  Safeguard-blocked candidates are INCLUDED (a row enters on its score alone; breaker / position cap
  are downstream and orthogonal — his ruling 2026-09-28).
- **By month:** May 228 · Jun 110 · Jul 119 · Aug 198 · Sep (1–3) 15. Era A (old score) 630, era B
  (08-22 on) 40.
- **Outcome-eligible:** 667 (3 rows lack 15 forward sessions; #684 censors them). Aggregate outcome
  counts already PUBLISHED by #684 (not split by any volume measure): 71 runners ≥ 5 ADR, 26 ≥ 8 ADR,
  of which about 4 sit in the held-out block (PLAN #686).
- **Gap-day share count present on 670 of 670.** Median 6.1M; p25 2.6M; p75 16.2M.
  **≥ 9M: 268 of 670 (40 %)** — discovery 235 of 607 (39 %), held-out 33 of 63 (52 %); alerted 129 of
  307, not alerted 139 of 363. No split-mismatch row (no adjusted-volume distortion to flag).
- **Feed check passed:** the first 15 minutes' shares / full-day shares has median 0.127 (p10 0.074,
  p90 0.185) — consolidated volume, not an IEX-only slice (which would read ~0.02).
- **What share count is made of (rank correlations, n 667):** with 20-day average SHARES **+0.88**;
  with gap-day relative volume (`CLOSE_vol_vs_avg50`) **+0.29**; with 20-day dollar volume +0.49; with
  price −0.21. Identity: log(gap-day shares) = log(20-day avg shares) + log(relative volume). **On this
  population ≥ 9M is mostly a LIQUIDITY screen, and only partly a participation one.**
- **His labelled EPs (operator_labelled_eps.md) in the population: 5** — BFLY 06-18, PLTR 08-04,
  TEAM 08-07, HTFL 08-14 (discovery) and MRNA 08-19 (held-out). **All 5 traded ≥ 9M** (HTFL 9.9M,
  barely). With a 40 % base rate and two mega-caps (PLTR 172M, MRNA 192M) that is composition, NOT
  evidence. ABNB 08-07 and CHPT 09-03 were never scored (outside the population); PENG 10-07 is outside
  the window.

### P2. The two measures (both known at the gap-day CLOSE — the same moment, so a fair contest)

- **Share count:** gap-day total shares = `mi_daily_closes.volume` on the scan date (consolidated,
  split-adjusted). Tested two ways: **D1 `SC_ge9m`** ≥ 9,000,000 vs < 9M (Bonde's literal rule), and
  **D2 `SC_log_shares`** as a continuous feature, top tercile vs the rest (cut points from DISCOVERY).
- **Relative volume, as #684 defines it at the close:** **D3 `CLOSE_vol_vs_avg50`** = gap-day volume /
  mean volume of the 50 prior sessions, top tercile vs the rest. This is the apples-to-apples
  comparator (full-day volume, relative). NOT `PRE_rel_volume_scan` — that column's median 0.13 says it
  is cumulative scan-time volume ÷ ADV, not a relative-volume ratio.
- **Declared direction, all three: HIGHER = more runners** (his claim for share count; #684's declared
  direction for relative volume).

### P3. Outcome — tail first

- #684's outcome, unchanged, from the **gap-day close** (the moment both measures become known):
  `run_xadr` = (max HIGH over sessions +1..+15 − gap-day close) / ADR$ (house ADR20 × gap-day close).
  **Primary tail: share reaching ≥ 5 ADR** (`runner5`). Then ≥ 8 ADR, then p90 and median `run_xadr`,
  then the mean (the closest echo of his "+0.32R on average"). Stop-free by construction.

### P4. Split and the bar (#684's own — imported, not re-implemented)

- **Split:** DISCOVERY = scan_date ≤ 2026-08-14 (607 rows, 16 ISO weeks); HELD-OUT = 08-15..09-03
  (63 rows, 3 ISO weeks). Tercile cut points from DISCOVERY, applied unchanged to HELD-OUT.
- **Per-draw verdict = #684's four conditions, verbatim:** (1) DISCOVERY week-blocked permutation
  p < 0.05 (2,000 shuffles of the runner label within ISO week, one-sided in the declared direction);
  (2) the same sign on HELD-OUT, which reads "can't tell (held-out too thin)" with < 3 held-out runners
  or < 8 rows on either side; (3) survives dropping the DISCOVERY week holding the most runners;
  (4) survives dropping the two biggest DISCOVERY runners. Seed **9016** (not #684's 684).
- **Why not "held-out p < 0.05":** the held-out block holds ~4 runners; even all 4 in the top group
  barely reaches p < 0.05, so that bar could only ever say "too few". As #686 does, the held-out
  permutation p is printed beside every verdict and every PASS is labelled **"with p < 0.05"** or
  **"sign-only"**. A sign-only PASS is weak (a held-out sign is close to a coin flip under the null).
- **Draws and chance:** 3 decisive draws → 0.05 × 3 = 0.15 expected chance clears of condition (1).
- **Head-to-head (one declared statistic):** on DISCOVERY, AUC(`SC_log_shares`) − AUC(`CLOSE_vol_vs_avg50`)
  for `runner5`, tested by a PAIRED permutation (each row's two percentile ranks swapped with
  probability ½, 2,000 draws), one-sided "share count > relative volume". Reported on HELD-OUT and the
  whole population too, as description. Alongside it, his two chart comparisons in our units: ≥ 9M vs
  < 9M, and top vs BOTTOM relative-volume tercile.

### P5. Verdict map (decided now, applied mechanically)

1. A draw reading **"can't tell (held-out too thin)"**, or a DISCOVERY favourable group under 30 rows,
   → **`too_few_to_judge`**, unless rule 2 already gives a clean answer.
2. **`share_count_separates`** = D1 or D2 PASSES and D3 does not. **`rvol_separates`** = D3 PASSES and
   neither D1 nor D2 does.
3. Both sides PASS → the side whose PASS has the larger HELD-OUT favourable-minus-rest ≥ 5 ADR rate
   wins; equal → `neither`.
4. No PASS and no thin draw → **`neither`**.
- Every verdict is carried with the head-to-head AUC difference and its p, and with "sign-only" where it
  applies.

### P6. What I already know (disclosed before running) and my prior

- #684 already drew `CLOSE_vol_vs_avg50` (draw 55) on this same population, and its ONLY PASS was
  `PRE_dollar_vol_20d` in the **LOWER** direction (sign-only on held-out, #686 §dry run). So relative
  volume at the close did NOT pass #684's bar — known from the published PASS list; its row was not
  opened before this registration. D3 is therefore a re-read, not a fresh test; D1/D2 are new.
- #684 also published ADR % HIGHER as a discovery lead (p ≈ 0.02).
- **Prior:** share count ≈ liquidity × relative volume, and the less-liquid third ran MORE in #684. So I
  expect D1/D2 to read flat or **wrong way** here. If they do, it is attributed to the liquidity half
  #684 already found, not reported as a new feature. **Range restriction:** Bonde's sample is "all
  qualified gappers"; ours is the already-scored subset, where 40 % clear 9M — the rule may separate the
  wide universe and not this pre-filtered slice.

### P7. Secondaries — reported with the same machinery, NO verdict, NOT mapped to the answer

- **What admission leans on (pre-open):** `PRE_pm_rvol`, `PRE_projected_vol_multiple` (both #684 draws).
- **The liquidity half of the identity:** `PRE_vol_20d_shares` (20-day avg shares), HIGHER.
- **Early proxy (known by 09:44 ET — the END of the 09:30–09:44 ORB window, not 09:31):**
  E1 `E_log_orb_shares` = shares 09:30–09:44 (rows with ≥ 12 of 15 minute bars; a small undercount
  where 12–14), top tercile vs rest; E2 `E_orb_ge_equiv` = 09:30–09:44 shares ≥ 9M × the DISCOVERY
  median of (first-15-minute ÷ full-day shares) — fixed from volumes alone, printed before any
  outcome; E3 `O945_orb_vol_vs_20d` (early RELATIVE volume, #684 draw 50). Coverage 608 of 670.
- **Descriptive tables:** bottom / middle / top tercile and ≥ 9M / < 9M, each with n, ≥ 5 ADR count and
  rate, ≥ 8 ADR count and rate, p90, median and mean `run_xadr`; the same on alerted rows only; where
  the 5 labelled EPs sit.
- **Not available locally (stated, not routed around):** pre-market ABSOLUTE shares (only the pm RVOL
  ratio is stored), and per-minute volume (so no 09:31 or 09:35 cut). The 09:44 sum is the earliest
  absolute count on disk.

### P8. What would make this wrong

- The outcome not matching #684's: `read.py` asserts 667 outcome rows, 71 runners ≥ 5 ADR and 26 ≥ 8 ADR,
  and that D3's DISCOVERY favourable/rest rates equal #684's published `CLOSE_vol_vs_avg50` row.
- One or two names carrying a result (condition 4 drops the two biggest; the tables name them).
- Mega-cap ≥ 9M rows (PLTR, MRNA class) whose ADR is small, making ≥ 5 ADR easier — read against
  `PRE_adr20_pct` in the descriptive table.

END OF PRE-REGISTRATION

---

## Method

- **Population:** `mi_ep_scan_log` scored rows (`ep_score IS NOT NULL`), one per (ticker, scan_date),
  2026-05-01..2026-09-03, n = 670 (667 with an outcome), alerted and scored-not-alerted, safeguard-blocked
  included — #684's pull of 2026-09-28, read from `scripts/probes/_684/` (features.tsv, daily.tsv.gz,
  orb.tsv). Era A 630 / era B 40.
- **Code:** `scripts/probes/_9m_share_count_1016/` — `common.py` (loader; gap-day bar only),
  `composition.py` → `composition.out` (no outcome), `read.py` → `read.out` + `read_rows.tsv` (the one
  run; imports #684's `study.add_outcomes / perm_p / diff_stat / fav_mask / tercile_cuts / auc`).
- **#686 left intact, verified after the run:** sha256 of `_684/daily.tsv.gz`, `study.py`, `features.tsv`,
  `results.tsv` all equal the #686 freeze footer; bytecode writing was off. `rel_volume` (scan) = cumulative
  volume ÷ ADV, confirmed in `agents/market_intelligence/ep_detector.py:2556` — so it is not a relative-volume ratio.

## Results — run once 2026-10-16 10:17 PDT (`read.out`; pre-registration hashed 10:15 PDT, hash MATCH `40a76a72…` at run time)

**Verdict (P5 map, mechanical): `neither`.** Share count LEANS the right way on the ≥ 5 ADR tail but
misses the bar and the lean is gone at ≥ 8 ADR; relative volume is flat — the one part of his chart
that reproduces here.

- **Integrity:** outcome rows 667, runners ≥ 5 ADR 71, ≥ 8 ADR 26 — identical to #684. D3 reproduces
  #684's published `CLOSE_vol_vs_avg50` rates exactly (11.39 % vs 10.95 %). Best week 2026-W19 and the
  two biggest runners UMC, CRSR — same as #684. Held-out: 63 rows, 4 runners ≥ 5 ADR, **0 runners ≥ 8 ADR**.

### The three decisive draws (#684 bar; rate = share reaching ≥ 5 ADR within 15 sessions of the gap-day close)

| draw | DISCOVERY favourable | DISCOVERY rest | diff | AUC | disc p | HELD-OUT fav vs rest (p) | drop best week | drop best two | verdict |
|---|---|---|---|---|---|---|---|---|---|
| D1 shares ≥ 9M | 34 of 235 = 14.5 % | 33 of 369 = 8.9 % | +5.5pp | 0.567 | **0.051** | 3 of 33 vs 1 of 30 (0.32) | +1.7pp, p 0.386 | +4.9pp, p 0.061 | can't tell (disc p ≥ 0.05) |
| D2 shares, top third (≥ 11.2M) | 24 of 202 = 11.9 % | 43 of 402 = 10.7 % | +1.2pp | 0.563 | 0.457 | 3 of 29 vs 1 of 34 (0.22) | −1.8pp | +0.9pp | can't tell |
| D3 relative volume, top third (≥ 3.76×) | 23 of 202 = 11.4 % | 44 of 402 = 10.9 % | +0.4pp | 0.510 | 0.678 | 2 of 30 vs 2 of 33 (0.67) | +1.7pp | +0.6pp | can't tell |

- **Head-to-head (declared statistic):** DISCOVERY AUC shares 0.563 vs relative volume 0.510, difference
  **+0.052, p 0.112** (n = 604, 67 runners) — share count ranks runners slightly better, not significantly.
  Held-out (n = 63, 4 runners) −0.068; all rows (n = 667) +0.048, p 0.128.

### Tail first — the bigger the run, the less share count matters (all 667 rows)

| group | n | ≥ 5 ADR | ≥ 8 ADR | p90 run (ADR) | median run (ADR) | mean run (ADR) | median ADR % |
|---|---|---|---|---|---|---|---|
| ≥ 9M shares | 268 | 37 (13.8 %) | **10 (3.7 %)** | 5.8 | 1.95 | 2.50 | 5.7 |
| < 9M shares | 399 | 34 (8.5 %) | **16 (4.0 %)** | 4.5 | 1.66 | 2.30 | 4.9 |
| shares, bottom third (< 3.4M) | 221 | 17 (7.7 %) | 8 (3.6 %) | 4.4 | 1.63 | 2.25 | 4.7 |
| shares, middle third | 215 | 27 (12.6 %) | 9 (4.2 %) | 5.5 | 1.78 | 2.50 | 5.1 |
| shares, top third (≥ 11.2M) | 231 | 27 (11.7 %) | 9 (3.9 %) | 5.6 | 1.88 | 2.39 | 5.9 |
| relative volume, bottom third (≤ 2.31×) | 219 | 23 (10.5 %) | 8 (3.7 %) | 5.0 | 1.67 | 2.29 | 6.5 |
| relative volume, middle third | 216 | 23 (10.6 %) | 9 (4.2 %) | 5.1 | 1.76 | 2.46 | 4.8 |
| relative volume, top third (≥ 3.76×) | 232 | 25 (10.8 %) | 9 (3.9 %) | 5.5 | 1.84 | 2.38 | 4.9 |

- **At ≥ 8 ADR — the runs that make the book — ≥ 9M and < 9M are identical (3.7 % vs 4.0 %).** The ≥ 5 ADR
  gap is a moderate-run effect, and it reads as "the thinnest third runs less", not "the 9M names run more".
- **Of the 15 biggest runs, 10 traded under 9M shares** (CRSR 4.0M, VOYG 3.0M, PSNL 5.8M, HQ 6.2M,
  VPG 1.1M, VCX 0.5M, ALOY 4.2M, EFOR 1.1M, HLIT 7.8M, FET 0.4M). A hard 9M floor would have cut most of
  the tail.
- **Alerted rows only (n = 306):** ≥ 9M 16 of 129 (12.4 %) vs < 9M 19 of 177 (10.7 %) at ≥ 5 ADR, and at
  ≥ 8 ADR **≥ 9M is worse: 3 (2.3 %) vs 11 (6.2 %).** Relative volume among alerted rows runs the other way
  (bottom third 14.1 %, top third 9.3 %).
- **His chart's two comparisons in our units:** ≥ 9M − < 9M = +5.3pp at ≥ 5 ADR (mean run +0.20 ADR);
  top − bottom relative-volume third = +0.3pp (mean run +0.09 ADR). Direction matches his chart; size and
  significance do not carry to the tail.
- **His labelled EPs:** all 5 sit in ≥ 9M AND in the top relative-volume third, so neither measure is
  favoured by them. None of the 5 reached 5 ADR from the gap-day close (TEAM 4.9, HTFL 4.4, PLTR 2.7,
  BFLY 1.2, MRNA −1.3) — the same "a real EP is not a 15-session runner by this outcome" caveat #684 states.

### Secondaries (no verdict mapped)

| measure | known at | DISCOVERY fav vs rest (≥ 5 ADR) | disc p | verdict under #684's bar |
|---|---|---|---|---|
| pre-market relative volume, top third | pre-open | 28 of 182 (15.4 %) vs 35 of 363 (9.6 %) | 0.194 | can't tell (disc p); held-out sign against (1 of 30 vs 3 of 31) |
| projected volume multiple, top third | scan | 7 of 100 (7.0 %) vs 21 of 197 (10.7 %) | 0.858 | fail (wrong way) |
| 20-day average shares, top third | pre-open | 27 of 202 (13.4 %) vs 40 of 402 (10.0 %) | 0.141 | can't tell |
| shares 09:30–09:44, top third (≥ 1.49M) | 09:44 | 23 of 183 (12.6 %) vs 38 of 364 (10.4 %) | 0.332 | can't tell |
| shares 09:30–09:44 ≥ 1.12M (the 9M equivalent) | 09:44 | 25 of 211 (11.8 %) vs 36 of 336 (10.7 %) | 0.490 | can't tell |
| 09:30–09:44 relative volume, top third | 09:44 | 20 of 183 (10.9 %) vs 41 of 364 (11.3 %) | 0.784 | fail (wrong way) |

- Early head-to-head (DISCOVERY, n = 547, 61 runners): AUC early shares 0.558 vs early relative volume
  0.491, +0.066, p 0.047 — descriptive, one of seven secondary readings (expect ~0.35 chance clears), not mapped to the answer.

### Post-hoc — written after seeing the run, attribution only (`posthoc.out`)

- **The D1 lean lives in one week.** In 2026-W19 (the early-May earnings cluster): ≥ 9M 13 of 28 (46 %) vs
  < 9M 5 of 37 (14 %). Every other discovery week: 21 of 207 (10.1 %) vs 28 of 332 (8.4 %), +1.7pp.
- **It flips with volatility.** Low- and mid-ADR names: ≥ 9M runs more (15.7 % vs 3.6 %, n = 70 / 165;
  17.8 % vs 7.8 %, n = 90 / 129). High-ADR names (ADR ≥ 6.4 %): **< 9M runs more — 17.1 % vs 9.3 %
  (n = 105 / 108), and holds 10 of the 12 ≥ 8 ADR runs in that band.** A one-cut share rule would cut the
  wild, thin names where our biggest runs live. Post-hoc; a hypothesis for #686's successor, not a finding.

## Timing — what is knowable at 09:31 vs the close

- **Full-day share count is known only after the close.** At our 09:31 ORB order we hold the pre-market
  relative-volume ratio (no absolute pre-market share count is stored) and one minute of regular-session
  volume. So even a clean result here could only feed a day-2 / delayed entry or a later filter — and the
  outcome above is measured from the gap-day close, i.e. exactly that day-2 frame, where it does not pass.
- **The earliest absolute count on disk is shares 09:30–09:44,** which ranks almost identically to the
  full-day count (rank correlation 0.97) and carries the same weak lean (+2.1pp, p 0.33; the 1.12M
  "9M-equivalent" +1.1pp, p 0.49). 09:44 is the END of the ORB submission window, so it is already too
  late for the 09:31 order. Per-minute volume (a 09:31 / 09:35 cut) is not in the local files.

## What this does not answer

- **R under a stop.** His +0.32R is the average R of trades; ours is a stop-free share reaching ≥ 5 / ≥ 8
  ADR from the gap-day close. A stop-and-target replay could differ, though the ≥ 8 ADR tie says the big
  winners would not.
- **The wide universe.** Bonde tested "all qualified gappers" since 1992; this is the already-scored slice,
  where 40 % clear 9M. The rule may separate the raw gapper list and not ours (range restriction).
- **Out of sample.** Four held-out runners, none ≥ 8 ADR: no held-out reading here means anything. The
  September block belongs to #686 (frozen read 10-17) and was not touched; a share-count read on it is a
  separate, later step.
- **Era.** 630 of 670 rows were admitted by the pre-08-22 score; the read is about which scored names ran,
  not about today's admission line.
- **Mixed catalysts.** Earnings and non-earnings EPs are pooled; the W19 concentration is an earnings week.

## ⚖ THE LINE

Any change to the EP score, admission, a filter or an entry rule from this read is CHANGE_PROCESS and the
operator's call. Nothing was changed, flipped or deployed. **Nothing here warrants a proposal:** no draw
passed, and the post-hoc ADR split argues against a hard 9M floor.

## Files

- `scripts/probes/_9m_share_count_1016/` — `common.py`, `composition.py` → `composition.out`,
  `prereg.sha256`, `read.py` → `read.out` + `read_rows.tsv`, `posthoc.py` → `posthoc.out`.
- Inputs (read-only, unmodified): `scripts/probes/_684/{features.tsv, daily.tsv.gz, orb.tsv, results.tsv, study.py}`.

## ⚖ THE LINE

Any change to the EP score, admission, a filter or an entry rule from this read is CHANGE_PROCESS and the
operator's call. Nothing was changed, flipped or deployed.

## Verifier notes (Opus, 2026-10-16 — outside the hashed pre-registration, which stays byte-for-byte)

- **UPHELD: `neither`.** Every load-bearing number reproduced.
- **The reason, corrected:** D1 (>= 9M shares) did not merely "just miss" — its p of 0.051 is Monte-Carlo noise (0.040-0.054 across 10 seeds, 0.046 at 20,000 shuffles), so it clears condition (1) on most seeds and condition (2). It FAILS condition (3) decisively: drop its best week (2026-W19, an early-May earnings week) and the edge is +1.7pp, p 0.39. The edge lives in one week.
- **Erratum:** the pre-registration heading says "written 10:14-10:40 PDT"; the hash was written 10:15:51 and the run finished 10:17:27, so "10:40" is wrong. Not edited (it would break the hash); the before-evidence chain holds (prereg.sha256 10:15:51 → read.py 10:17:15 → read.out MATCH 10:17:27).
- **For him:** 10 of our 15 biggest runs traded UNDER 9M shares, so a hard 9M floor would cut most of the tail; relative volume is flat too (the one part of the tweet's chart that holds on our data).
