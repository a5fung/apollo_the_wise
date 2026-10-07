# #624 — The low-cap lane's tail rate, replayed on 2024-01 → 2026-09 history (2026-10-06)

**STATUS: RESULTS WRITTEN 2026-10-06 17:15 PT — verdict NOT PINNED: on 2024-01-02 → 2026-06-05 the lane's
≥ 3R rate is 2.5% (90% interval 1.1%–4.2%, 279 walked trades), wholly below the review's 5% refusal line.** The
pre-registration below is unchanged (hash re-verified). Research only — nothing here changes a live rule, and
nothing here recommends one (THE LINE, below). Probe folder: `scripts/probes/_624_backfill/`.

## The decision this serves

- **His words (2026-10-06):** *"Six months is way too long to wait. We need to speed it up."*
- **The question:** the live shadow (`mi_lowcap_lane_signals`) holds 19 signals from 13 of the 19 sessions
  2026-09-09 → 2026-10-05. Pinning the lane's tail rate that way needs roughly 250 walked trades — at about one
  signal a session, a year or more. Replaying the SAME frozen rule on history answers it now.
- **What would change the decision:** a pinned interval (pass line in §5) lets the #624 tail-rate readout
  come forward to the 2026-11-03 checkpoint instead of waiting on live accrual — his call. An unpinned
  interval still states how far history narrowed it (n=46 left it uncertain by a factor of about 4.5), and
  the live shadow keeps recording as the forward check either way.

## Pre-registration (frozen before any outcome was seen)

**Frozen 2026-10-06 16:05 PT (19:05 ET)** at repo HEAD `9e3b6c7c`. The section's sha256 is recorded in
`scripts/probes/_624_backfill/PREREG_FREEZE.txt`; this section is never edited after the freeze — changes go
in "Amendments" (end of section) under the rules stated there.

**What had been read before the freeze (inputs only):** `prereg_counts_out.txt` (split-table and
security-type coverage, day-row counts, the 19 live lane rows' INPUT columns — gap, prices, cap, both
volume readings, percentile, tick) and `prereg_counts2_out.txt` (the pull-size counts in §6). **No outcome was
read:** `mi_lowcap_lane_replays` was not queried, no Polygon call was made, nothing was walked. The n=46
evidence (PLAN #624) was known — its thresholds are the rule's, which is why §4 sets its window apart.

**Code the run imports unchanged (git blob, first 12 of the hash):** `lowcap_lane.py` 7bb49f266cc1 ·
`lowcap_lane_replay.py` 24a14d012ee8 · `sustain_reject_replay.py` 098f1f595322 · `live_fill_counterfactuals.py`
f374fefd5338 · `rule_eras.py` 6785a809959c · `ep_detector.py` 1581b8661bd7 · `backtester/filters.py`
b96021ac6f80 · `alert_rank_shadow.py` 0d4ef59cda77 · `scripts/probes/_687/backfill.py` c53987221734 ·
`scripts/probes/_685/study.py` d7794ee825e1. The probe fails at start if any blob differs.

### 1. Population and method

- **Window:** every trading session **2024-01-02 → 2026-09-03** (671 sessions) — all before the live lane's
  first recorded row (2026-09-09).
- **Universe on session D**, mirroring the live board at a post-open tick:
  - Symbol of 1–5 upper-case letters, no `.`, not in `constants.SKIP_TICKERS`.
  - **Common stock only (`CS` or `ADRC`).** Authority = Polygon `/v3/reference/tickers/{t}?date=D` → `type`,
    point-in-time, read for every name that passes the two free terms (so delisted names and re-used symbols
    are typed as they were on D). Before the minute pull, names typed non-stock in today's
    `mi_security_types` (ETF, WARRANT, UNIT, PFD, RIGHT, FUND, SP, ETS, ETV, ETN) are skipped; names absent
    from it (mostly delisted since) ARE pulled and decided by the Polygon type. Live skips unclassified names;
    here they are kept when Polygon typed them CS/ADRC on D (they were classified at the time; dropping them
    is survivorship) and stamped `untyped_today`. Stated loss: a symbol that was common stock on D but is
    re-used today by a non-stock security is never pulled.
  - **Raw prior close ≥ $5.00** and **raw prior-day volume ≥ 50,000 shares** (`MIN_PREV_CLOSE`,
    `MIN_PREV_DAY_VOLUME` — live reads the unadjusted snapshot). `mi_daily_closes` is split-adjusted, so
    raw = adjusted × F(D) for price and adjusted ÷ F(D) for volume, F(D) = product of `split_to / split_from`
    over every split with execution date ≥ D, from a FRESH Polygon `/v3/reference/splits` pull since
    2024-01-02 (`mi_splits` starts 2026-03-02 and cannot serve 2024–25). That factor is for D − 1 values;
    D's own raw values (price at T for S4, the acting volume at T for `pm_shares_floor`) use splits with
    execution date AFTER D.
- **The rule (P15), frozen exactly as live — imported, never restated:** `lowcap_lane.free_terms()` on a
  candidate dict `{ticker, gap_pct, prev_close (raw), today_volume}` with the reconstructed history, then the
  cap test. Thresholds: gap ≥ 15.0% (`LANE_MIN_GAP_PCT`) · volume percentile ≥ 90.0
  (`LANE_MIN_VOL_PERCENTILE`; `ep_detector._volume_percentile`, strict `>`, rounded to 0.1) · prior close ≥
  $5.00 (`LANE_MIN_PREV_CLOSE`) · market cap < $500,000,000 (`LANE_MAX_MARKET_CAP`; ≥ that = not a lane row).
  The probe asserts the four constants equal 15.0 / 90.0 / 5.0 / 5e8 at start and aborts otherwise. **No
  re-tuning:** no other threshold is run as an arm.
- **Ticks:** T ∈ {09:30, 09:31, 09:35, 09:40, 09:45, 09:50, 09:55} ET — the post-open ticks of the live scan
  (`ep_scan` cron hours 7–9 every 5 min, plus `ep_scan_open` at 09:31; there is no 10:00 tick). Evaluated in
  order. For each (ticker, D) the FIRST tick where the free terms pass triggers ONE cap read (live dedupes the
  same way): cap < $500M → a signal recorded at T; cap ≥ $500M → no signal that day; cap unreadable → no
  signal, counted `cap_unavailable`. `MAX_ENRICH_PER_TICK = 6` is mirrored: on a tick with more than six new
  survivors, the six largest gaps are read and the rest roll to the next tick (counted).
- **Board membership** is modelled as "the real-time gap at T is ≥ 15%". Live also needs the delayed-snapshot
  gap to clear the Pass-1 floor (or the Pass-0 real-time admission) — not modelled; anchor A1 measures the
  effect.

### 2. Each term — how history reproduces it, and how that differs from live

| term | live (the lane at a tick) | backfill | difference, and how it is checked |
|---|---|---|---|
| Price at tick T | Alpaca real-time last trade (`gap_pct`, `price_source=alpaca_sip`) | Polygon 1-min bars (consolidated, `adjusted=true`). T = 09:30: the 09:30 bar's OPEN (alternative: the 09:29 bar's close). T ≥ 09:31: the close of the bar that started at T − 1 min. No bar → the latest earlier bar's close since 04:00; none at all → that tick is not evaluable | Calibration C2 on the 19 live rows' stored `current_price` |
| Gap at T | (price − prior close) ÷ prior close | the same, both sides adjusted (the ratio is split-invariant) | C2 |
| Volume at T — the ACTING reading | the DELAYED Polygon snapshot (`day.v`, else `min.av`; ~15 min behind; includes pre-market). At the 09:30 tick it is in effect pre-market volume | **Primary:** sum of Polygon minute volume, bars starting in [04:00, T − 15 min). **Sensitivity S3:** through T (the real-time reading, `today_volume_rt`) | Calibration C1 picks nothing silently: the cut-off rule is fixed below |
| Volume history | rolling 20-session mean volumes from `mi_daily_closes`, one per end-date in the 60 calendar days before D (≥ 20 rows in the 124 calendar days before D, else no history) — `db.get_volume_history_daily_closes` | the identical loop over the Stage-0 daily pull (adjusted units; the minute volume is adjusted to the same basis) | C4 reproduces the stored history length and percentile on the 19 live rows |
| Market cap | yfinance `marketCap` (via `get_fmp_profile`) read at the first surviving tick | **Polygon point-in-time:** `/v3/reference/tickers/{t}?date=D` → `weighted_shares_outstanding` (else `share_class_shares_outstanding`) × raw prior close. Polygon's own `market_cap` field is never used. **Sensitivity S4:** × raw price at T | Calibration C3 (two-sided). **Missing shares = unreadable: counted, never imputed as a pass, never a signal** — live does the same with an unreadable cap |
| Prior close / prior-day volume floors | raw snapshot `prevDay` | raw via F(D) (§1) | stated |
| Security type | today's `mi_security_types`; unclassified skipped | Polygon type on D; unclassified-today kept if CS/ADRC on D | stated; reported as a count |

- **Calibration rules, fixed now (all outcome-blind — they compare INPUT readings, never a result):**
  - **C1 — volume cut-off.** Candidate cut-offs k ∈ {15 (primary), 14, 16, 10, 20, 0} minutes before T.
    Sets: L19 = the 19 live lane rows (target `today_volume_delayed` at `tick_wallclock_et`); F300 = 300 rows
    drawn at random (seed 624, proportional by tick) from `mi_universe_floor_shadow`, 2026-09-09 → 2026-10-05,
    `today_volume_at_open > 0` (target `today_volume_at_open`; tick = 09:30 when `minutes_since_open_at_open`
    = 1, else 09:30 + that many minutes). A cut-off PASSES when, on F300, the median ratio proxy ÷ stored is
    within [0.90, 1.10] and ≥ 80% of rows sit within ±20%, AND the ≥ 90 percentile verdict agrees with the
    verdict on the stored reading on ≥ 90% of F300 and ≥ 17 of L19. k = 15 is used if it passes; else the
    passing k whose median ratio is closest to 1.00; if none passes → HALT.
  - **C2 — tick price.** On L19, |reconstructed price ÷ stored `current_price` − 1| ≤ 1% on ≥ 16 of 19. The
    09:30 open is used if it passes; else the 09:29 close if it passes; else HALT.
  - **C3 — cap.** Sets: L19 (stored `market_cap`) and S300 = up to 150 ticker-days below $500M and 150 at or
    above, drawn at random (seed 624) from `mi_ep_scan_log` rows with `market_cap` 2026-08-31 → 2026-10-05.
    PASS = the below/above-$500M call agrees on ≥ 90% of S300 and ≥ 17 of L19. Prior-close basis if it passes;
    else the tick-price basis if it passes; else HALT. Median |log ratio| is reported either way.
  - **C4 — history.** Feeding the STORED `today_volume_delayed` through the reconstructed history reproduces
    `vol_history_n` exactly and `vol_percentile` within 0.1 on ≥ 17 of the 19 live rows.

### 3. Entry, stop and exit — the CURRENT MAGNA53 bracket; gates stamped, never filtered

- **Primary instrument = the live lane walker's own functions**, called on captured data in the order
  `lowcap_lane_replay._record_one_signal` calls them. Chosen over the #685/#687 chain because anchor A2 can
  only be hit by the walker that produced `mi_lowcap_lane_replays`; the #685/#687 chain runs on the same
  signals as sensitivities S1/S2 (below).
  1. `srr.submit_time_and_window(T)`: submit = max(T, 09:31); **T ≥ 09:45 → `window_out_of_orb`** — a
     signal, never walked.
  2. ORB = Polygon's 09:30 bar (high H, low L); none → `no_930_bar_for_orb` (unscoreable).
  3. ATR14 = `alert_rank_shadow.compute_atr14_prior` on the daily high/low/close of the 40 calendar days
     before D (D excluded); `validate_orb_entry(H, L, ATR14)` → `orb_invalid` on a zero range or H − L > 1.5 ×
     ATR14.
  4. `srr.entry_walk(day-0 bars 09:30–15:59, H, submit, cancel = 10:00)` — the stop-limit buy at H, limit
     `stop_limit_buy_price(H)`; `filled` / `no_entry` / `abstain` (minute gaps in the entry window).
  5. Stop = `srr.current_era_stop("entry_minus_2r", H, L)` = 2L − H; risk = entry − stop (≤ 0 → unscoreable).
  6. Rules = `rule_eras.exit_rules_as_of(2026-10-06, "magna53")` = **era D: stop entry − 2R, one third off at
     +8 ORB-R, stop to entry once price trades +3 ORB-R, trail max(SMA10, SMA20) on prior closes** (the
     10:00 entry cancel is `srr.entry_cancel_asof`). The #687 depth exit is OFF in production and is not used.
     `target, kw = lfc.stack_walk_inputs(rules, entry, L)`.
  7. `lfc.walk_arm(..., harvest="live_ladder", **kw)` with sessions = up to 40 trading sessions after D from
     `mi_daily_closes` (daily grain — the shape `lfc._assemble_sessions` returns) and prior closes = the 40
     calendar days before D.
  8. **R = pnl per share ÷ risk ("money-R", the live walker's `realized_r`; 1 money-R = 2 ORB-R on a fill at
     H).** Settled, `horizon` (40 sessions, marked), `open` at the data end (marked), or `unscoreable`.
- **Deviations from the live walker, declared:** (i) day-0 bars are Polygon's, not Alpaca's stored bars;
  (ii) a stock whose daily bars END before its 40th session and before the data end (it stopped trading) is
  closed at its last close, counted `delisted_forced_close` — the live walker would block and write
  `unscoreable`, which drops exactly the collapses; a missing session INSIDE the series still blocks
  (`unscoreable`, counted); (iii) the split guard (daily open vs the 09:30 bar's open > 5%) is kept as a
  consistency count. **Not modelled, as in the live walker:** safeguards, sizing, slot allocation, the fade
  guard, slippage, broker rejects.
- **Sensitivities on the SAME signals — reported beside, never the verdict:**
  - **S1 — the live MAGNA53 order (#500, price-aware):** `_687/backfill.live_entry(bars0, H, L, "open",
    submit)` with the tick-derived submit (a marketable limit at price × 1.002 when price is already above H,
    skipped past the 1.5× chase cap); forward walk as primary. This is the real difference on late ticks.
  - **S2 — the #685 forward walk:** `_687/backfill.day0_from_fill` + `walk_trail_arm("A0", …)` (today's stop,
    minute walk on days that test the trail line; `study.walk_hybrid_arm` underneath, unchanged) and
    `force_close_delisted`; needs a second minute pull for line-test days.
  - **S3** the real-time volume reading (C1's k = 0). **S4** the cap at the tick price.
- **Other MAGNA53 gates, STAMPED on every signal with `lowcap_lane.blocking_filters_for` (live row shape):**
  - `extended`: (prior close − lowest close in the 10 calendar days before D) ÷ that low ≥ 50%
    (`MAX_EXTENSION_PCT`). **Never waived, never proposed for waiver.**
  - `adv_no_data` / `adv_too_low`: median close × volume over the 30 calendar days before D (≥ 10 rows,
    volume > 0) < $1M — **D's own row excluded** (live at 09:3x has none).
  - `atr_too_high`: Wilder ATR14 over the 35 calendar days before D ÷ last close > 15% — checked only when
    ADV$ passed (the live short-circuit order).
  - `pm_shares_floor`: raw acting volume at T < 25,000.
  - `cooldown` (PROXY): a prior lane signal on the same ticker within 60 days. Live keys on EP alerts, which
    did not exist for most of this window; the earnings carve-out is not modelled.
  - **Not reconstructed (absent from the stamp list, stated):** the shortlist cap, the M&A check, the RVOL@T
    gate, the score bar.
- **Three populations, all reported:** **P** = every lane signal (the live shadow's own population — the
  verdict population) · **E** = extension guard passed (what a paper lane could trade without reversing his
  2026-08-29 ruling) · **G** = all five stamps passed.

### 4. What is measured

- **Tail events (the statistic):** money-R ≥ 3 (= the live `meets_3r`) and money-R ≥ 8. Rate = events ÷
  walked trades (filled; settled plus horizon/open rows at their mark — marked rows flagged; settled-only
  beside). Per-signal rate (all signals in the denominator, no-fills included) beside.
- **Interval:** 90% percentile interval from a bootstrap that resamples TICKERS (all rows of a drawn ticker
  together — serial names make rows dependent), 10,000 draws, seed 624; the row-level Wilson 90% interval
  beside.
- **Per block and population:** the entry funnel (signals → out of window → ORB invalid → never crossed →
  abstain → filled → settled / horizon / open); ≥ 3R and ≥ 8R count, rate, interval; mean R with its
  interval; median; total; **drop-best-two** (total and mean without the two largest); the full distribution
  (≤ −1.5, −1.5 to −1, −1 to −0.5, −0.5 to 0, 0 to 0.5, 0.5 to 1, 1–2, 2–3, 3–5, 5–8, ≥ 8) with p10 / p25 /
  p50 / p75 / p90 / p95 / max; worst trade; losses beyond −1.5R; forced delisting closes; the ten largest
  contributors; the top ticker's share of summed R. Descriptive splits: cap band (< $25M, $25–100M,
  $100–200M, $200–500M), prior-close band, gap band, tick.
- **Blocks (fixed now):** discovery = 2024-01-02 → 2024-12-31 (252 sessions) · held-out = 2025-01-02 →
  2026-09-03 (419), shown whole and split into 2025-01-02 → 2026-06-05 (357) and **the #623 evidence window
  2026-06-08 → 2026-09-03 (62) — in-sample, because the rule's thresholds were picked there** ·
  **OUT-OF-SAMPLE = 2024-01-02 → 2026-06-05 (609 sessions) — the verdict block** · ALL. Nothing is chosen on
  discovery (the rule is frozen); the split is a stability check.
- **Serial names:** a signal is SERIAL when its ticker has ≥ 3 lane signals (itself included) in the 60
  calendar days ending on D — knowable on D. P is reported with and without serial rows, and with a 60-day
  cooldown (first lane signal per ticker per 60 days). Tickers with ≥ 3 signals in any 60-day span are listed.
- **Beside every headline:** the live rows (`mi_lowcap_lane_replays` as it stands on the run date: signals,
  filled, settled, ≥ 3R, mean) and the **n=46 cell** — as published (era C bracket, +2R partial, submit 09:31,
  not re-walked: 4 of 46 ≥ 3R, mean +0.527R, +0.03R without WETO and FBRX) and its era D re-walk from
  `scripts/probes/_545p2_623_era_walk.tsv` (`era_d_ladder` rows joined on ticker and date; still submit 09:31).
- **For information, not a graduation:** the backfill's values for criteria 2–5 of the
  `lowcap_lane_graduation_624` review (≥ 4 tail events, ex-top-2 mean ≥ 0, no ticker > 40% of summed R with
  ≥ 20 tickers, signals per session).

### 5. Pass / fail, declared now

- **PINNED** if, on population P in the OUT-OF-SAMPLE block, the ≥ 3R rate's ticker-bootstrap 90% interval
  has a lower bound above 0 **and upper ÷ lower < 2.0**. One line, on that population only. (For scale: 4 of
  46 gives roughly 4%–18%, a ratio near 4.5.) Walked trades needed, before clustering: about 24.4 × (1 − p) ÷
  p — 256 at 8.7%, 163 at 13%, 463 at 5%.
- **Read-outs declared with it:** (i) the interval against the review's 5% refusal line — wholly above,
  straddling, or wholly below; (ii) stability — discovery and held-out each inside the other's interval =
  stable, else unstable, both shown; (iii) the same verdict computed on E, ex-serial, and ALL, reported
  beside, never substituted.
- **Expected before pulling (a stated guess, not a bar):** about 670 signals (the live 1.0 a session × 671
  sessions), plausibly 300–1,500; 150–800 walked trades; a ≥ 3R rate of 5–15%. A result outside is reported
  as a failed expectation (the #687 precedent: "a few dozen" partials became 217).
- **WOULD-FAIL-IF — any one makes the result not citable as pinned, and it is reported as such:**
  - **W1 survivorship:** fewer than 5% of signal tickers stopped trading before 2026-09-01, or no
    `untyped_today` names reach the population (delisted names missing).
  - **W2 cap coverage:** cap unreadable on more than 20% of free-term survivors.
  - **W3 instruments:** any of C1–C4, A1, A2 failing (they HALT the run first — see run order).
  - **W4 data:** no 09:30 bar or entry-window gaps on more than 15% of walkable signals, or minute-pull
    errors above 2%.
  - **W5 look-ahead:** any pre-open term (history, ADV$, ATR, extension) reading D's own daily row — a unit
    test in the probe asserts every window ends at D − 1.
  - **W6 prefilter unsafe:** on any F300 / L19 row, the minute volume 04:00 → 09:40 exceeds D's
    `mi_daily_closes` volume, or any of the 19 live rows fails the prefilter → the volume half of the
    prefilter is dropped and the full superset (~29,300 day-rows) is pulled. Price side: on the same rows,
    D's daily high must be ≥ the highest minute high 04:00 → 09:55; if it is not AND C2 adopted the 09:29
    pre-market close, the price half is widened to "daily high ≥ +15% OR open ≥ +5%" (a last pre-market
    print 10 points above the open is the only case still outside it) and the added rows are pulled.
  - **W7 one name:** a single ticker carries more than 40% of summed R, or the ≥ 3R count rests on two
    tickers or fewer.
- **Anchors (must pass before Stage 2; their outcomes are the LIVE window's, never the backfill's):**
  - **A1 — the rule re-finds the live signals.** Run the full screen on the 19 live sessions (2026-09-09 →
    2026-10-05). Recall ≥ 16 of 19 (same ticker-day, tick within one scheduled tick). Every backfill-only
    signal is explained from live records (`lowcap_lane_cap_unavailable` / `lowcap_lane_tick_cap` audit rows,
    a live cap ≥ $500M) or listed as unexplained; more than 10 unexplained → HALT.
  - **A2 — the walker re-prices the live walks.** On the matched live signals vs `mi_lowcap_lane_replays`:
    entry status agrees on ≥ 90%; entry price within 0.5% on ≥ 90% of rows filled in both; R within 0.05R on
    ≥ 90% of rows settled in both (open rows compared at the same last session). Every disagreement listed
    with its cause.
  - **A3 — report only, no bar:** how many of the n=46 cell's rows (inside the backfill window) the frozen
    replay re-finds, and why the rest differ (tick, volume reading, cap source). The 46 identities come from
    `scripts/probes/_623_master.jsonl` filtered exactly as the cell was: cap < $500M, gap ≥ 15, volume
    percentile ≥ 90, clean settled walk; a filter that does not return 46 rows is reported, not forced.
- **HALT before any outcome (composition, Stage 3):** signals outside 150–3,000; any ticker above 3% of
  signals; any calendar month above 12%; W2. A halt is written up with the population table and no outcome.

### 6. Data pull plan, budget and runtime

- **Prefilter (no look-ahead — it only removes rows the rule can never admit):** daily high ≥ 1.15 × prior
  close (a tick price can only be at or below the day's high) AND the day's full volume beats ≥ 90% of the
  rolling-mean history (a tick's cumulative volume cannot exceed the day's — W6 verifies this before it is
  relied on), plus the raw floors and the symbol/type screen of §1.
- **Counts from `prereg_counts2_out.txt`** (raw floors there used the partial `mi_splits`, so ±10% until the
  fresh split pull):

| year | n day-rows, high ≥ +15% | n opened ≥ +15% | n after the volume prefilter | n of those typed CS/ADRC today | n of those untyped today | n distinct names after the prefilter |
|---|---|---|---|---|---|---|
| 2024 | 7,983 | 1,449 | 6,134 | 4,564 | 1,131 | 2,220 |
| 2025 | 11,800 | 1,935 | 8,432 | 6,168 | 772 | 2,667 |
| 2026 (to 09-03) | 9,543 | 1,472 | 6,086 | 3,793 | 33 | 2,048 |
| **total** | **29,326** | **4,856** | **20,652** | **14,525** | **1,936** | — |

- **Stage 0 — prod reads, read-only, each captured once to a file:** `mi_daily_closes` for every superset
  ticker over [its first D − 130 calendar days, 2026-10-05]; `mi_security_types`; `mi_lowcap_lane_signals`
  (all columns); `mi_lowcap_lane_replays` (read ONLY for A2 and the "beside" column); the F300 and S300
  samples; `mi_audit_log` `lowcap_lane_*` rows 2026-09-09 → 2026-10-05 (to explain A1).
- **Stage 1 — Polygon, calibration and anchors** (inside `apollo-market`, `APOLLO_CALL_ORIGIN=probe`, one call
  per (ticker, day), paced ≥ 0.35 s, resumable logs, the `_687/fetch_minutes.py` pattern with pre-market
  kept): splits since 2024-01-02 (~20 calls) · minute bars 04:00–16:00 ET for L19 + F300 + the live-window
  superset (~600) ≈ 920 · point-in-time reference reads for L19 + S300 + the live-window survivors (~60) ≈
  380. **≈ 1,320 calls, ~10 minutes.** Gate: C1–C4, A1, A2 and W6 pass, else HALT.
- **Stage 2 — the population:** minute bars for the prefiltered superset, ≈ 16,461 (14,525 typed + 1,936
  untyped) · reference reads for free-term survivors, est. 2,500–5,000 · S2 line-test days ≤ 400. **≈
  19,500–22,000 calls, ~2.2–2.5 hours at ~0.4 s a call. $0** (Polygon Starter subscription; no LLM).
- **When:** outside 09:00–10:15 and 15:45–17:15 ET on market days (the production container hosts the pull);
  a weekend is preferred. **Storage:** ~120 MB gzipped under `scripts/probes/_624_backfill/` (git-ignored).
  **Compute:** local, importing the production pure functions, ~20 minutes. **Total wall-clock ≈ 3–3.5
  hours.**

### Run order

1. Freeze: this section + its sha256 in `PREREG_FREEZE.txt`.
2. Stage 0 reads.
3. Stage 1 pulls → C1–C4, A1, A2, W6. Any failure → HALT and write up; no outcome is computed.
4. Stage 2 pulls.
5. Build the population; the composition table and the HALT checks — **still no outcome.**
6. Walk; compute §4; apply §5 exactly as written.
7. Results are appended BELOW this section; this section is not edited.

### Amendments

- Allowed only before step 6, only to fix a defect found by an anchor or calibration, and only through the
  outcome-blind choice rules in §2 (C1–C3). Each one is dated, says what changed and why, and states that no
  outcome had been computed. None so far.

## Results

**Run 2026-10-06 19:09–20:15 ET (16:09–17:15 PT), executed as frozen (deviations: next section). Verdict: NOT PINNED — and the
whole 90% interval sits below the review's 5% refusal line.** Every number below is reproducible from the files in
`scripts/probes/_624_backfill/` (`s1_calib_out.txt`, `s1_anchor_out.txt`, `s3_compose_out.txt`, `s4_results_out.txt`,
`per_signal_P.tsv`); the freeze hash still reads `e56902f4…` after this section was written.

### Population (stated before any outcome; HALT checks passed)

- **Source:** prod `mi_daily_closes` (read-only), 26,091 day-rows 2024-01-02 → 2026-09-03 with a daily high ≥ 1.15 ×
  the prior close, a 1–5-letter symbol, raw prior close ≥ $5 and raw prior-day volume ≥ 50,000 (raw via a fresh
  Polygon split pull, 4,376 splits). Delisted names included.
- **Prefilter** (cannot drop a row the rule admits; W6 verified): 13,921 day-rows on 3,391 names were pulled (12,664
  typed common stock today, 1,257 untyped today) — the frozen plan estimated ~16,461. Dropped before the pull, both
  windows: typed non-stock today 6,726 · leveraged/index list 863 · no volume history 863 · full-day volume below
  the 90th percentile 4,073.
- **Calls:** 16,824 Polygon calls (5 split pages, 14,475 minute pulls, 2,344 reference reads), **0 errors**, $0.

| screen step (rule P15, k = 15 min delayed volume, 09:30 open, cap = dated shares × raw prior close) | n day-rows |
|---|---|
| prefilter rows pulled | 13,921 |
| no minute bars at all (Polygon returned none) | 55 |
| never passed gap ≥ 15% AND volume ≥ 90th percentile at any tick | 12,524 |
| passed both free terms (one cap read each) | 1,342 |
| — Polygon type on D not common stock (3 warrants, 3 ETFs) | 6 |
| — cap unreadable (no share count) | 1 |
| — cap ≥ $500M | 567 |
| **lane signals (population P)** | **768** |
| survivors deferred by the six-per-tick cap (3 ticks), re-screened next tick | 5 |

- **P = 768 signals on 509 tickers over 434 of the 671 sessions** (1.14 a session, max 10; the live shadow records
  1.0 a session). Discovery 2024: 228 · 2025-01-02 → 2026-06-05: 467 · the #623 in-sample window: 73.
  **Out-of-sample (the verdict block) = 695 signals.**
- **Tick of first qualification:** 09:30 449 · 09:31 26 · 09:35 28 · 09:40 23 · 09:45 23 · 09:50 118 · 09:55 101 →
  **242 (32%) are at 09:45 or later and are never walked**, as live. (The delayed volume first includes the opening
  minutes at the 09:50 tick, which is why late ticks are common — live's VNCE and SVRN did the same.)
- **Composition:** cap < $25M 237 · $25–100M 170 · $100–200M 138 · $200–500M 223. Prior close $5–10 525 ·
  $10–20 184 · $20–50 54 · $50+ 5. Gap at the tick 15–20% 223 · 20–30% 204 · 30–50% 188 · 50–100% 113 · 100%+ 40.
  Typed today CS 619 / ADRC 34 / **untyped today 115 rows on 81 tickers** (kept: Polygon typed them common on D).
- **Stamps (never filters):** ADV$ below $1M 449 · extended ≥ 50% 258 · prior lane signal within 60 days 147 · ATR
  above 15% 82 · pre-market shares below 25,000 7 · no ADV data 3. **E (extension passed) = 510 · G (all five
  passed) = 183.** Serial rows 28 (21 tickers ever had ≥ 3 signals in 60 days: ADVB, ARQQ, ASPC, BMR, CERO, CYN,
  DFNS, FORD, GSIT, HOLO, HUSA, LUNR, MNTS, NVA, PHUN, RNAZ, SBET, SDOT, UMAC, WETO, WSHP).
- **HALT checks — none fired:** signals 768 (bar 150–3,000) · top ticker HOLO 8 = 1.0% (bar 3%) · top month 2025-06
  47 = 6.1% (bar 12%) · cap unreadable 1 of 1,336 survivors = 0.1% (bar 20%).

### Stage 1 instruments (all passed before Stage 2)

| check | bar | result |
|---|---|---|
| C1 delayed volume, k = 15 | median ratio 0.90–1.10, ≥ 80% within ±20%, verdict agreement ≥ 90% F300 and ≥ 17/19 | median 0.986, 87.7% within ±20%, 300/300 and 19/19 — **pass** |
| C2 price at the tick (09:30 open) | ≥ 16/19 within 1% | 17/19 — **pass** |
| C3 cap (prior-close basis) | ≥ 90% of S300 (n = 215) and ≥ 17/19 | 210/215 (97.7%), 19/19, median abs log ratio 0.001 — **pass** |
| C4 volume history | ≥ 17/19 exact n and percentile within 0.1 | 19/19 — **pass** |
| A1 re-find the live signals | recall ≥ 16/19; ≤ 10 unexplained extras | **19/19 at the same tick**; 4 extras: DSP explained (live cap $667M), ELMT $493M, PRTH $481M, VEEE $5M unexplained (3) — **pass** |
| A2 re-price the live walks | ≥ 90% each | entry status 19/19, entry price 11/11, R 10/10 — **pass** |
| W6 prefilter | 0 rows with minute volume to 09:40 above the daily; all 19 live rows pass | 0 of 319; 19/19 — **safe** |
| added input check: Polygon dated shares | — | Polygon's own cap on D = dated shares × the RAW close on D for 10/10 names with a later reverse split — the shares are point-in-time |

- A2 only exercised stop-outs and scratches (no live walk reached +3R). **The runner path is corroborated
  independently by S2** — `study.walk_hybrid_arm`, different code — which reproduces the out-of-sample block
  exactly: the same 7 tail events and a total of −116.3R vs −116.3R.

### §5 verdict — P, out-of-sample 2024-01-02 → 2026-06-05

| P, out-of-sample | n signals | n walked (tickers) | ≥ 3R | 90% ticker bootstrap | upper ÷ lower | verdict |
|---|---|---|---|---|---|---|
| the verdict line | 695 | 279 (231) | 7 = **2.5%** | **1.1% – 4.2%** | **3.87** (bar < 2.0) | **NOT PINNED** |

- **(i) Against the review's 5% refusal line: wholly BELOW** (upper bound 4.2%).
- **(ii) Stability: STABLE** — discovery 2024 3.4% (1.0–7.0%) and held-out 2025-01-02 → 2026-09-03 3.0% (1.3–4.9%),
  each inside the other's interval.
- **(iii) Beside, never substituted:** E 2.3% (0.6–4.3%, ratio 7.43) · P ex-serial 2.6% (1.1–4.3%, ratio 3.83) ·
  P whole window 3.2% (1.6–4.8%, ratio 2.99) — all NOT PINNED, all wholly below 5%.
- **WOULD-FAIL-IF — none fired, so the verdict is citable as stated:**

| check | bar | result |
|---|---|---|
| W1 survivorship | ≥ 5% of signal tickers stopped before 2026-09-01; untyped-today names present | 110 of 509 (21.6%); 115 untyped-today rows — ok |
| W2 cap coverage | unreadable ≤ 20% of survivors | 0.1% (1 of 1,336) — ok |
| W3 instruments | C1–C4, A1, A2 pass | all pass — ok |
| W4 data | ≤ 15% of walkable signals without a 09:30 bar or with an entry-window-gaps abstain; pull errors ≤ 2% | 28 of 526 = 5.3%; 0 errors — ok (D9) |
| W5 look-ahead | every pre-open window ends at D−1 | `test_w5.py` pass, non-vacuous — ok |
| W6 prefilter | as above | safe — ok |
| W7 one name | top ticker ≤ 40% of summed R; ≥ 3R events on > 2 tickers | summed R is negative; AKAN = 10.2% of the positive R; 7 events on 7 tickers — ok |

- **Failed expectation, as declared:** the frozen guess was a ≥ 3R rate of 5–15%; history reads 2.5% (whole window
  3.2%). Signals (768 vs ~670, range 300–1,500) and walked trades (317 vs 150–800) landed inside their ranges.
- **Why history could not pin it, and what would:** at a 2.5% rate the frozen formula (24.4 × (1 − p) ÷ p) needs
  about **950 walked trades** for upper ÷ lower < 2, before ticker clustering — about 3.4× the 279 that 2024 →
  mid-2026 holds. The live shadow walks about 0.5 trades a session (10 settled in 19 sessions), so live accrual
  cannot pin it on any useful horizon either. What history DID settle: the interval sits wholly under 5%.

### By block — P, primary walker (money-R; all walked trades settled — none open, at the horizon or force-closed)

| block | n signals | n walked (tickers) | ≥ 3R n = rate | 90% bootstrap | Wilson 90% | ≥ 8R | mean R [90%] | median | total | without best two: total / mean |
|---|---|---|---|---|---|---|---|---|---|---|
| **out-of-sample (verdict)** | 695 | 279 (231) | 7 = 2.5% | 1.1–4.2% | 1.4–4.6% | 0 | −0.42 [−0.52, −0.31] | −1.00 | −116.3 | −128.1 / −0.46 |
| discovery 2024 | 228 | 87 (76) | 3 = 3.4% | 1.0–7.0% | 1.4–8.3% | 0 | −0.39 [−0.59, −0.16] | −1.00 | −33.5 | −43.7 / −0.51 |
| held-out 2025-01-02 → 2026-09-03 | 540 | 230 (185) | 7 = 3.0% | 1.3–4.9% | 1.7–5.5% | 1 | −0.30 [−0.45, −0.15] | −1.00 | −69.4 | −88.5 / −0.39 |
| held-out to 2026-06-05 | 467 | 192 (162) | 4 = 2.1% | 0.5–3.9% | 0.9–4.6% | 0 | −0.43 [−0.55, −0.30] | −1.00 | −82.8 | −93.7 / −0.49 |
| **#623 window 06-08 → 09-03 (in-sample)** | 73 | 38 (29) | 3 = 7.9% | 2.3–14.9% | 3.2–18.2% | 1 | +0.35 [−0.18, +0.93] | 0.00 | +13.4 | −4.8 / −0.13 |
| whole window | 768 | 317 (253) | 10 = 3.2% | 1.6–4.8% | 1.9–5.2% | 1 | −0.33 [−0.45, −0.20] | −1.00 | −102.9 | −122.0 / −0.39 |

- **The in-sample window reads about 3× the out-of-sample rate** (7.9% vs 2.5%) — what choosing the 15% / top-10%
  thresholds on that window predicts. That is the n=46 cell's 8.7% explained.
- **Entry funnel, whole window (768):** at/after 09:45 242 · ORB wider than 1.5 × ATR 76 · never crossed the ORB
  high 66 · opened above the limit, never filled 22 · entry abstain (minute gaps) 28 · **filled 334** → settled 317,
  unscoreable 17 (same-bar ambiguities). Out-of-sample (695): 225 · 69 · 59 · 21 · 26 · filled 295 → 279 settled.
- **Per-signal ≥ 3R rate** (no-fills in the denominator): out-of-sample 1.0% of 695 · whole window 1.3% of 768.
- **Hold length:** 77% of walked trades close on the entry day; the longest hold is 15 sessions.

### Distribution — P, whole window (317 walked) and out-of-sample (279)

| R bucket | ≤ −1.5 | −1.5 to −1 | −1 to −0.5 | −0.5 to 0 | 0 to 0.5 | 0.5 to 1 | 1–2 | 2–3 | 3–5 | 5–8 | ≥ 8 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| whole window, n | 1 | 195 | 3 | 73 | 4 | 3 | 28 | 0 | 6 | 3 | 1 |
| out-of-sample, n | 1 | 179 | 3 | 62 | 1 | 3 | 23 | 0 | 5 | 2 | 0 |

- **Shape:** 62% of walked trades lose about the full −1R; 23% end between −0.5R and 0 (mostly the 0R scratch after
  breakeven arms); the 1–2R cluster is mostly the +8 ORB-R partial followed by a breakeven exit (+1.33R). Percentiles, whole window: p10 −1.00 · p25 −1.00 ·
  p50 −1.00 · p75 0.00 · p90 +1.33 · p95 +1.43 · max +13.08. Worst trade RILYZ 2024-08-16 −1.54R (the only loss
  beyond −1.5R). Forced delisting closes: 0.
- **Ten largest, whole window:** WETO 2026-08-17 +13.08 · AKAN 2026-04-29 +6.00 · OMIC 2024-09-13 +5.86 · DFNS
  2026-07-28 +5.07 · CLPT 2025-09-24 +4.97 · ZEPP 2025-07-11 +4.31 · ARQQ 2024-11-22 +4.28 · NUKK 2024-12-18 +4.05 ·
  BLZE 2026-06-23 +3.93 · CRNC 2025-01-03 +3.06. The 10 tail events sit on 10 different tickers; summed R is
  negative, so a top ticker's share of it is undefined — WETO carries 14.5% of the positive R.

### Populations E, G, ex-serial, cooldown (primary walker)

| population | out-of-sample: n signals / n walked / ≥ 3R (rate, 90%) / mean R | whole window: n signals / n walked / ≥ 3R (rate, 90%) / mean R |
|---|---|---|
| P (verdict) | 695 / 279 / 7 (2.5%, 1.1–4.2%) / −0.42 | 768 / 317 / 10 (3.2%, 1.6–4.8%) / −0.33 |
| E — extension passed | 465 / 171 / 4 (2.3%, 0.6–4.3%) / −0.40 | 510 / 190 / 5 (2.6%, 1.0–4.7%) / −0.37 |
| G — all five stamps passed | 168 / 50 / 2 (4.0%, 0.0–8.2%) / −0.33 | 183 / 55 / 3 (5.5%, 1.8–10.9%) / −0.26 |
| P without serial rows | 673 / 270 / 7 (2.6%, 1.1–4.3%) / −0.40 | 740 / 303 / 10 (3.3%, 1.7–5.1%) / −0.30 |
| P, first lane signal per ticker per 60 days | 564 / 220 / 4 (1.8%, 0.5–3.3%) / −0.43 | 621 / 246 / 7 (2.8%, 1.2–4.8%) / −0.31 |

- Three intervals reach above 5%: G out-of-sample (0.0–8.2%, 50 walked), G whole window (1.8–10.9%, 55 walked) and
  P without serial rows over the whole window (upper 5.1%); every other row sits wholly below 5%. Serial rows
  (14 walked) produced no tail event and average −0.82R.

### Sensitivities (beside, never the verdict)

| sensitivity | out-of-sample: n walked / ≥ 3R (rate, 90%) / mean R | whole window: n walked / ≥ 3R (rate, 90%) / mean R | note |
|---|---|---|---|
| S1 the live #500 order (chase or skip above the ORB high) | 273 / 6 (2.2%, 0.8–3.7%) / −0.43 | 310 / 9 (2.9%, 1.3–4.5%) / −0.34 | 31 chase-cap skips |
| S2 the #685 forward walk (A0) | 279 / 7 (2.5%, 1.1–4.2%) / −0.42 | 317 / 10 (3.2%, 1.6–4.8%) / −0.33 | 9 day-0 ambiguities excluded; 20 line-test days pulled |
| S3 real-time volume (k = 0): 1,037 signals (+269) | 372 / 12 (3.2%, 1.8–4.8%) / −0.32 | 417 / 17 (4.1%, 2.6–5.7%) / −0.24 | ratio 2.62 / 2.20 — not pinned |
| S4 cap at the tick price: 697 signals (−71) | 254 / 7 (2.8%, 1.2–4.5%) / −0.40 | 289 / 9 (3.1%, 1.5–4.8%) / −0.32 | |

- **The verdict does not depend on the walker choice** (D1): S2 (the #685/#687 chain PLAN.md names) gives the same
  2.5%, and S1 gives 2.2%. Only S3's whole-window interval touches 5%.

### Descriptive splits — P, whole window, walked trades (n, ≥ 3R count and rate, mean R)

- **Cap band:** < $25M n 134, 4 (3%), −0.27 · $25–100M n 65, 3 (5%), −0.16 · $100–200M n 50, 0, −0.60 ·
  $200–500M n 68, 3 (4%), −0.39.
- **Prior close:** $5–10 n 227, 5 (2%), −0.35 · $10–20 n 65, 5 (8%), −0.20 · $20–50 n 23, 0, −0.41 · $50+ n 2, 0.
- **Gap at the tick:** 15–20% n 73, 2 (3%) · 20–30% n 96, 3 (3%) · 30–50% n 81, 2 (2%) · 50–100% n 58, 3 (5%) ·
  100%+ n 9, 0.
- **Tick:** 09:30 n 279, 8 (3%), −0.36 · 09:31 n 15, 0 · 09:35 n 12, 1 · 09:40 n 11, 1. Extended n 127, 5 (4%),
  −0.26 · not extended n 190, 5 (3%), −0.37. Every cell is small; none is a finding.

### Beside: the live shadow and the n=46 cell

| source | n signals | n walked | ≥ 3R | mean R |
|---|---|---|---|---|
| live shadow (`mi_lowcap_lane_replays`, as of 2026-10-06) | 19 | 10 settled (11 filled) | 0 | −0.40 |
| n=46 cell as published (era C bracket, submit 09:31) | 46 | 46 | 4 (8.7%) | +0.527 (+0.033 without the WETO 08-17 and FBRX 07-09 trades, n 44) |
| n=46 cell re-walked under era D (`_545p2_623_era_walk.tsv`) | 46 | 45 settled | 5 (≥ 8R: 2) | +0.503 |
| this backfill, out-of-sample | 695 | 279 | 7 (2.5%) | −0.42 |
| this backfill, #623 window | 73 | 38 | 3 (7.9%) | +0.35 |

- **A3 (report only):** the frozen replay re-finds **34 of the 46** rows. Of the 12 it does not: 7 never cleared
  both terms at one tick — mostly the delayed volume reading (**FBRX 07-09, the +10.71R trade, sat at the 80th
  percentile at every tick**; DFNS 08-03 ≤ 87.5; AMIX 08-25 63.4; WETO 08-31 73.2; JLHL 08-05 52.5), OCC 06-10
  cleared the gap only before its volume did, JLHL 07-10 never gapped 15% at a tick; 3 fail the raw floors or the
  +15% high (ASBP 06-12 high only +5.5%; WAVE 06-25 and VATE 08-07 prior-day volume 17,511 and 49,317, under 50,000);
  2 fail the full-day volume prefilter (JLHL 07-17, VEEE 07-27). Because A1 shows the backfill reads volume exactly
  as the live lane does (19/19), FBRX's absence is a property of the acting rule, not of the replay.

### For information — the `lowcap_lane_graduation_624` criteria 2–5 on the backfill (not a graduation)

- **2.** settled walks ≥ 3R: 10 (bar ≥ 4) · **3.** mean R without the top two: −0.39 (bar ≥ 0) · **4.** summed R
  is −102.9R; WETO carries 14.5% of the positive R; 253 tickers (bars ≤ 40%, ≥ 20) · **5.** 1.14 signals a session
  over 671 sessions, max 10. On the review's REFUSE clause "tail rate (≥ 3R) < 5% at n ≥ 60": every population
  above with at least 60 walked trades reads under 5%; G (50–55 walked) is short of the n the clause needs.

## Deviations

Each is declared; none changes a threshold, a measure, the pass line or the populations.

| # | what the frozen text says | what ran | why |
|---|---|---|---|
| D1 | PLAN.md #624 (10-06 text): "exits via the #685/#687 machinery"; the pre-registration's author asked for the walker choice to be confirmed before Stage 0 | the frozen doc's choice: the live lane walker is PRIMARY; the #687 live order (S1) and the #685 forward walk (S2) ran on every signal beside it. No confirmation reached this run | only the live walker can be checked against `mi_lowcap_lane_replays` (A2). The verdict does not move: S2 reads the same 2.5%, S1 2.2%. PLAN.md wording is for the orchestrator / operator to reconcile; this run could not edit PLAN.md |
| D2 | Stage 0 reads, then Stage 1 pulls | the Polygon splits pull (5 calls, a Stage 1 item) ran first | the Stage 0 daily read needed the raw floors to pick which tickers to pull. No outcome involved |
| D3 | "the `_687/fetch_minutes.py` pattern" | Polygon called directly over HTTPS (key in a header, never in a URL or a log), not through `collector._polygon_get`; 3 workers in Stage 2, each paced ≥ 0.35 s; pre-market kept | `_polygon_get` writes an `mi_audit_log` row on any failure, and the run had to make no DB write. Same endpoints, `adjusted=true` |
| D4 | F(D) = product over every split with execution date ≥ D | only splits executed on or before 2026-10-06 | 49 future-dated splits in Polygon's list are applied in no adjusted data yet |
| D5 | live retries an unreadable cap on up to 3 ticks | one cap read per (ticker, D), as the frozen §1 states | a historical read is deterministic; a retry only consumes enrich slots (1 unreadable cap in P) |
| D6 | the six-per-tick enrich cap | names Polygon typed non-common on D are dropped BEFORE the cap | live never has them on its board (6 such names) |
| D7 | "a stock whose daily bars END before its 40th session and before the data end" | coded as: last stored daily row < 2026-10-05 AND the walk's first missing session lies after that row → closed at the last close | the rule needed a boundary. It fired 0 times |
| D8 | S2 = `walk_trail_arm("A0")` + `force_close_delisted` | run unchanged, with `backfill.HORIZON` set to 2026-10-05 at runtime (as #687 sets `study.ADR_MULT`); S2 walks by date to the data end with no 40-session cap and #687's own delisting rule | the machinery is imported unchanged |
| D9 | W4: "no 09:30 bar or entry-window gaps" | read as the walker's own states (the frozen §3 step 4 term): no 09:30 bar / no day-0 bars / the `entry_window_gaps` abstain. Decided BEFORE any walk (`w4_profile_out.txt`) | the strict minute-record reading (any empty minute between submit and 10:00) is 36.5%: those minutes cluster at exactly 4 and 8 empty minutes (5-minute trading pauses at the open), every walkable signal has its 09:30 bar, and pull errors are 0 — a market event, not missing data |
| D10 | W7: "> 40% of summed R" | top ticker's R ÷ total R when the total is positive; ÷ the positive R otherwise | the total is negative, so a share of it is undefined |
| D11 | S300 = 150 below + 150 at/above $500M | 65 below (the whole pool) + 150 at/above = 215 | the pool held only 65 sub-$500M ticker-days |
| D12 | — | the real-time gap is rounded to 2 dp before the 15% test | live does `round(rt_gap, 2)` |
| D13 | — | daily rows pulled through 2026-10-06; the backfill walk stops at 2026-10-05 as written | A2 needed 10-06 for one live row |
| D14 | — | an added input check (not a gate): Polygon's own cap field used ONLY to confirm its dated shares are in D's units | C3 calibrates on 2026 rows, where dated and current shares coincide; it could not see the 2024 reverse-split case |

- **Boundary note (A1):** ELMT ($493M) and PRTH ($481M) carry live caps under $500M too, yet live did not record
  them — the backfill is slightly more inclusive than live right at the cap line, probably through board membership
  (not modelled, §1).
- **Split-row basis (descriptive):** on 699 split-affected rows Polygon's 09:30 open matched the daily open within
  0.5% on 680 of 681 comparable; 1.7% of them (12) show full-day minute volume under half the daily (0.5% of unsplit
  rows). A low minute volume can only drop a signal, never admit one.

## What this does not answer

- **Fillability:** quoted spread and bid/ask size at the tick — live records them; historical quotes are not
  pulled.
- **Overnight collapses from offerings:** the live walker's SEC 8-K Item 3.02 / 424B flag is not
  reconstructed (the forced delisting close captures only the endpoint).
- **The M&A check, RVOL@T gate, score bar and shortlist cap** — not reconstructible at $0; E and G are
  therefore looser than the live stack.
- **Whether the lane makes money as a book:** safeguards, slots, sizing and the 2% daily loss limit are not
  modelled.
- **Any exit other than era D:** #545 owns exits; a different bracket re-prices every row.
- **Whether history matches the live shadow:** different volume and cap sources (Polygon minute bars and
  point-in-time shares vs the delayed snapshot and yfinance). C1/C3/A1 measure the gap; the live shadow
  keeps recording as the forward check.
- **Symbol re-use inside a ticker's daily history** (two companies under one symbol) is not detected.
- **Board membership:** the live board also needs the delayed-snapshot gap to clear the scan's own floor (or the
  real-time admission); not modelled. A1 suggests the backfill is slightly more inclusive at the cap boundary
  (ELMT, PRTH).
- **A symbol that was common stock on D but is re-used today by a non-stock security** was never pulled; the count is
  unknown (the frozen §1's stated loss).
- **A pinned rate:** at the measured ~2.5% the frozen pass line needs about 950 walked trades; 2024 → mid-2026 holds
  279 out-of-sample. History bounds the rate (under 5%); it does not pin it.
- **Same-bar ambiguity:** 17 filled signals the 1-minute grain cannot order (stop and target or breakeven in one bar)
  are unscoreable and outside the denominator, as live.
- **Whether 2027 resembles 2024–26** — the rate is a property of this tape and this bracket; the live shadow remains
  the forward check.

## ⚖ THE LINE

- Research only. Nothing here changes the lane, the MAGNA53 bracket, the market-cap floor or any gate, and
  nothing recommends a change.
- **The extension guard is not waived and no waiver is proposed** — it is stamped and reported as cut E.
- Any move of the lane toward paper is CHANGE_PROCESS plus his sign-off; the waiver set is his pick.
- The result above recommends nothing. Whether the 2026-11-03 checkpoint reads this backfill, and what the lane does
  next, is his call.
