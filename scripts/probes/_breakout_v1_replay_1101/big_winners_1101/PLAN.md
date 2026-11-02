# Big winners 2017–2024 vs breakout v1 — the definitions, FIXED BEFORE ANY COUNT (2026-11-01)

**His ask (2026-11-01, `docs/methodology/operator_shared_notes.md`, last entry):** *"looking at the biggest winners over that
period, of which how many fit our criteria vs those that don't, and of those that do is there some common features... study 1000s of
winners, patterns and internalize what big winners look like."*

**Offline research, $0, nothing live changes; no rule is proposed to move (THE LINE). Nothing dated 2025-01-01 or later is read
(#710's seal): cb702's daily export is stream-filtered on its date column to < 2025 before any bar is parsed (`v1_replay.sealed_copy_of_daily`),
its split list likewise (`load_splits_sealed`), the 2025+ regime rows of `small_pulls.psv` are never read (`load_types`). Every trade
outcome comes from the frozen replay's `trades.tsv.gz` (E ≤ 2024-12-31); this study computes NO new outcome. Descriptive only: no
pass/fail bar anywhere; every cell carries its n.**

This file was written before `01_episodes.py` ran. Results sit in `RESULTS.md`; nothing below is picked over its alternative after
seeing a number.

## 1. The population — big-winner EPISODES, the 10-22 definitions unchanged (`docs/analysis/cb_big_winner_recall_2026-10-22.md` §D)

The code is `01_episodes.py`, a copy of `scripts/probes/_702_winner_recall_1022/01_episodes.py` changed ONLY in (a) the stores and
trough windows below, (b) where it writes (this folder), (c) the sealed cb702 copy. The rule as APPLIED by that code (the 10-22
verifier's note: the admitted trough is kept when a lower close inside the run fails the universe) is the rule here too.

- **A big winner (the +100% set, headline):** per ticker, a session t is an episode's TROUGH when the universe passes at t (RAW close
  ≥ $5, 20-session median dollar volume ≥ $10M, 130 consecutive readable sessions, ticker `^[A-Z]{1,5}$`, security type CS / ADRC /
  unknown, not a test symbol), the highest close over (t, t+63] is ≥ 2.0 × close(t), and close(t) is the lowest close before that
  peak; peak extended while a higher close arrives within 20 sessions (cap t+126); gain = close(p)/close(t) − 1; non-overlapping; the
  artifact exclusions (a ≥ +50% one-day jump on < 2× volume; an identity break in [t−60, p]) counted and dropped.
  **The +50% set** (factor 1.5) is the same code, reported beside.
- **Its start** = the trough t (the low). **s25 / s50** = the first session whose close ≥ close(t) × (1 + 0.25 / 0.50 × gain) —
  s50 is "the half-way point of its move".
- **Its first measurable breakout** = the 10-22 primary rule: the longest 10–60-session window before b that is contained (span ≤ 5
  × ADR60(b−1) × close(b−1)) and sideways; b = the first session in (t, s25] whose close > that base's high. Classes as 10-22:
  `measurable_breakout` (b ≤ s25), `late_base` (b > s25, ≤ p), `ep_gap` (a ≥ 10% gap on ≥ 3× volume within 5 sessions of t that
  started the run), `no_consolidation`, `other`. The breakout day's volume multiple, gap and range, the base length L and depth come
  from the same code.
- **Period and stores (survivorship-corrected export, `docs/methodology/backtest_data_standard.md`):** troughs **2017-01-03 ..
  2022-03-31** on `apollo_data/cb702_pre_v2` (daily 2016-01-04..2022-06-30, exact raw closes), troughs **2022-04-01 .. 2024-12-31** on
  the sealed copy of `apollo_data/cb702` (daily 2021-09-27..2024-12-31). The split date is the replay's own store boundary
  (`ERA_A_D_LAST` = 2022-03-31). A late-March-2022 trough whose 63-session qualifying window crosses 2022-06-30 is excluded and
  counted (`window_cut`); a peak extension cut by a store's end is flagged (`ext_truncated`), the gain then under-measured. cb702
  starts 2021-09-27, so early-April-2022 troughs need their 130 sessions of history from it (counted if lost). Reporting eras follow
  the replay: 2017–21 (trough ≤ 2021-12-31) and 2022–24.
- **Cross-check before anything else:** restricted to troughs 2017-03-01..2021-12-31 the era-A table must reproduce the
  `rerun_v2_1025` counts (1,181 kept +100%; 4,946 +50%) exactly — same code, same store.

## 2. Did breakout v1 see it — the funnel (joined by (ticker, date), never by index)

v1's nightly list = `../out/list_eraA.tsv.gz` + `list_eraB.tsv.gz` (the replay's population stage: the live `breakout_v1.v1_gates`
on every night 2016-12-30..2024-12-30; a row = the name passed every gate that night, `list_rank` by `rs_best`). The daily-bar
trigger on E = `../out/list_coverage.tsv` (`level_pass`: high(E) > level; `fired`: and volume(E) ≥ 1.2× the 50-day). The minute
walk = `../out/trades.tsv.gz` keyed `E|ticker` (every list row walked whatever the cap: `outcome` filled / cancelled / abstain /
never_placed, `r_2c` the primary row's R at 2c each way, `realized_r` at 0c, `adm_cap` = took one of the 5 slots in the PRIMARY
capped book, `decisive`, `status`, `exit_date`, `sessions_held`).

- **The window of nights** = scan nights D with **t ≤ D ≤ s50** (from the low to the half-way point; E = D+1 is the breakout day).
  Fills made while the stock was still falling into its low are not catches (the 10-22 correction).
- **LISTED** = a list row (ticker, D) for some D in the window. **FIRED** = a listed night with `fired = 1`. **FILLED** = a listed
  night whose trade row has `outcome = filled`. **SLOT** = a filled night with `adm_cap = True` (the primary book took it).
- **The catch** = the FIRST filled night in the window (by D); its `r_2c` is the winner's R (headline), `realized_r` beside; "made
  money" = r_2c > 0, "stopped out / lost" = r_2c ≤ 0; ≥ 3R and "still in at s50" (exit_date ≥ s50's date) beside; the count of
  listed / fired / filled nights per winner beside; the sum of r_2c over every filled night in the window beside.
- Beside the window: listed on any night in [t−20, p] ("ever listed during the move") as a loose cross-check only.

## 3. Never listed — which gate kept it out (the live `v1_gates`, called on the historical bars)

For EVERY winner and EVERY night D in its window, `02_v1_nights.py` rebuilds the night exactly as the replay's population stage
does — `v1_replay.load_store` / `ticker_facts` / `night_members` / `cb.cross_section_one_date` (imported, not re-implemented;
`BV1_SCRATCH` points at this study's scratch so the sealed copy regenerates there) — and records per (winner, D):
- **pool status**: in the RS pool, else the pool exclusion in `night_members`' order (`ticker`, `identity_break`, `short_history`,
  `below_floors`, `no_r63`); `admitted` (CS / ADRC / unknown / a kept fund) or the type reason;
- **rs_best** from the night's cross-section (None when not in the pool → the rs gate fails);
- **the full gate vector** from `bv.v1_gates(bars, Di, rs_best, raw_close, cidx)` — every gate is evaluated without short-circuit,
  so the `failed` LIST is kept, not just its head; plus the values it returns (prior_move, pole date, base_len, tightening ratio,
  surf runs, higher-lows lows, breakdown values, adr20, level, vol_bar, close).
- **The parity check that proves the call IS v1 (10-22's first build had 628 disagreements):** on every winner-night, my call
  passes ⇔ the ticker is in the list file for that night. Both disagreement counts are reported; any disagreement is explained
  before a tally is quoted.

**Three attribution readings, all reported, the quoted one named:**
- (i) the FIRST failing gate in `GATES` order (`history, universe, rs, prior_move, higher_lows, surf, tightening, breakdown`; a pool
  exclusion reads as `universe` or `history`, as the live job's own order has it) on the ANCHOR night (§4) — order-dependent;
- (ii) per-gate fail SHARE on the anchor night across the never-listed winners (independent of order; **this is the table quoted**);
- (iii) the NEAREST MISS over the window: the night with the fewest failed gates (ties → the latest night); the gate named when
  exactly one failed, the set listed otherwise; tallied per winner.

## 4. The anchor night and the features (descriptive; median and quartiles; n per cell; no bar)

- **Anchor night** = b − 1 when a base breakout b exists (`measurable_breakout`, `late_base`); gap_day − 1 for `ep_gap` with no b;
  otherwise s25 − 1 (said so, counted). For FILLED winners the features are ALSO measured at the catch's own D (what the system saw
  when it bought); the money-vs-stopped comparison uses the catch's D.
- **Features** (one value per winner per measurement night): base length L and depth (10-22 base, episode-level); v1's base_len
  (D − pole) and prior_move (pole high / pole low − 1) and the 63-session return into the trough; tightening ratio (last 5 / prior 5
  range); surf best run; rs_best and r21 / r63 / r126; ADR20; RAW close; volume on E over the 50-day mean and the gap open(E)/close(D)
  − 1 (and the 10-22 breakout-day expansion flags where b exists); sector = the 2-digit SIC from `cb702_sic.psv` (a 2026-10-16
  point-in-time classification, identical in both stores — declared; missing → `unknown`); market phase = QQQ close vs its 50-day
  SMA at D (the task's words; the store's own QQQ bars) with the replay's 10/20 phase beside; the episode's gain, sessions t → p,
  trough year, class.
- **Groups**: never listed | listed, never fired | fired, never filled | filled, lost (r_2c ≤ 0) | filled, made money (r_2c > 0);
  with "fit" = LISTED. Tables per feature: median (Q1 .. Q3) and n per group; +100% headline, +50% beside; by era beside.

## 5. Deliverables

- `big_winners_2017_2024.tsv` — one row per big winner (+100% and +50%, `factor` column): ticker, era, trough / s25 / s50 / peak /
  breakout dates, gain, class, base, v1 status (listed / fired / filled / slot / catch D / r_2c / realized_r / status / first failing
  gate / nearest-miss gate / per-gate flags at the anchor), every feature at the anchor and at the catch.
- `RESULTS.md` — the funnel, the gate tables, the feature tables, the parity counts, what this does not answer.
- Scripts: `01_episodes.py`, `02_v1_nights.py`, `03_tables.py`; logs beside. Scratch: `scratchpad/Cfollow/big_winners/`.
