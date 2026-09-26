# #668 — why post-swap alpha capture is 20%: the carryforward is fine, the names do not base (2026-09-26)

**Answer first: (a) explains none of the shortfall and (c) explains all of it.** Of the 55
failed-Day-1 EP names that recovered +5% and were not picked up (the post-swap uncaptured set),
**0 of 55** would have been added by the MAGNA53→flag carryforward had it fired as written, and
**54 of 54 with usable history never form a qualifying base under the sourced HTF spec on any of
their 21 window days** — 39 never build the 90% pole, 11 fail the liquidity floor, and the 4 that
do have a pole fail the Stage-2 trend gate. The one remaining name (EROC, a 2026 listing with too
little history to replay) is unmeasured, not unexplained. **The 60–70% target was set against the
retired 1.50/60 detector: 33 of the 43 uncaptured names with a measurable pole clear that old bar,
which is why the old detector read 53% and this one reads 20%.** Recommendation: retire the 60–70%
number. Reaching it on today's detector means re-widening flag promotion, i.e. partially undoing
#356 — a detection criterion, his call only. Nothing was changed.

MEASURE-ONLY, $0, read-only against prod. No code, config, toggle, table or PLAN.md line touched.

## The decision it serves

#668's DoD: *"(a) and (c) measured separately against the post-swap baseline with a number per
cause; the residual named; then either a fix or a recommendation to retire the target — his ruling
either way."* The baseline is the 2026-09-16 read
(`docs/analysis/p74_alpha_capture_stage2_2026-09-16.md`): **POST-swap 14 of 69 = 20.3%**, never a
rate spanning the 2026-06-26 criteria swap (#356, commit `932dc066`).

## Method and population

| | |
|---|---|
| **Rows** | `mi_ep_alerts` HIGH alerts, distinct on (ticker, alert_date), pulled 2026-05-18 → 2026-09-05 and split at the swap; only the two era-clean windows are reported |
| **POST-swap window** | `alert_date` 2026-06-26 → 2026-08-27 (first alert 06-30); the whole 21-day forward window is post-swap and mature. This is the 20.3% baseline's own population, reproduced to the row (14 of 69) |
| **PRE-swap window** | `alert_date` ≤ 2026-06-24 — reproduced 51 of 96 = 53.1%; reported only as the bridge to the retired detector, never blended |
| **Failed Day 1** | Day-1 class ∈ {LOST_DAY1, NO_ENTRY, SKIPPED, NO_TRADE_ROW} from the live-preferring `mi_live_trades` join (the 09-16 correction); one alert (OKTA 08-27, status `filled`, still open) is in neither set — that is the 70 vs 69 |
| **Alpha** | 21-day max `high_price` in `mi_daily_closes` more than +5% over the gap-day `open_price`; 69 of 69 have both bars |
| **Capture** | any of: flag stage WATCH/TIGHTENING/COILED/TRIGGERED in `mi_flag_candidates`; a later HIGH/MODERATE EP alert; a `mi_9m_ep_alerts` row; a `mi_9m_day2_candidates` row — all within `alert_date+1 … +21`. ⚠ The shipped `ep_delayed_capture_audit.py` omits TIGHTENING from the flag leg; the 09-16 read included it. POST reads 14 either way; PRE reads 49 vs 51. This doc uses the 09-16 definition |
| **(a) source** | every `mi_live_trades` row with `skip_reason='block:r3_reentry_disabled'` (27: 8 paper 05-21→06-17, 19 live 07-06→09-14) vs every `mi_flag_candidates` row tagged `magna53_failed_r3` (79 rows, 17 tickers), on every scan day since 2026-06-01, against the path's own rule in `db.get_flag_universe` path (c): *R3-stopped, `alert_date` in `[scan_date−7d, scan_date)`* |
| **(c) instrument** | the flag detector **as it ran inside the window** — `flag_detector.py` at commit `0f82018f` (2026-08-06, the last change to `compute_flag_metrics` before 08-27; HEAD differs only by #592's pivot-walk rule and the #610/#354 telemetry columns) — replayed over stored `mi_daily_closes` bars with 380 calendar days of history (that era's `get_recent_daily_history` slice), on every trading day of each name's 21-day window, **with the name in the universe every day** (yesterday-stage / recent-stages / prior pivot chained from the previous replayed day, starting fresh at alert+1) |
| **Replay check** | on the 538 ticker-days where the board also stored a verdict, the replay agrees on stage **538 of 538** and on the blocking gate 535 of 538 (the 3 are a one-day pole/base-age ordering difference, same reject either way) |
| **What the system already did** | read before any miss was counted: 49 of the 55 uncaptured names were evaluated by the flag board on ≥1 window day (median 11 of a 15-day window) and rejected each day; the stored `reason` is quoted below |

Probe: `scripts/probes/_668_pull.py` (one-shot pull) and `_668_analyze.py` (replay + tables);
captures under `scripts/probes/_668_out/` (`summary.txt` holds every number here).

## 1. The baseline, reproduced — and with the two 9M legs removed

| era (flag criteria) | alpha n | captured | rate | flag | later EP | 9M EP | 9M Day-2 | flag-only | 9M-only |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PRE-swap 05-18→06-24 (retired 1.50/60) | n=96 | 51 | 53.1% | 49 | 5 | 1 | 0 | 45 | 1 |
| **POST-swap 06-30→08-27 (sourced HTF)** | **n=69** | **14** | **20.3%** | 6 | 1 | 7 | 1 | 6 | **7** |

| POST-swap, same 69 names | captured | rate |
|---|---:|---:|
| all four legs (the baseline) | 14 of n=69 | 20.3% |
| **without the two 9M legs** | **7 of n=69** | **10.1%** |
| flag leg alone | 6 of n=69 | 8.7% |

Half of the post-swap captures came from the 9M legs alone. `mi_9m_ep_alerts` last wrote
2026-09-08 (writer gated off); `mi_9m_day2_candidates` still writes 1–6 rows a day through 09-24
(the EOD sweep `run_9m_eod_sweep` inside the nightly pull is not behind that gate). Their absence
is a fact about the measure going forward, not a finding about (a) or (c).

## 2. Cause (a) — the carryforward against its own rule: verified fixed, quiet by design, adds 0

Expected admissions = R3 rows inside the 7-day lookback of each scan day; actual = rows tagged
`magna53_failed_r3` that day (`rule_audit.csv`, one row per scan day).

| period | scan days | expected ticker-days | fired | missed | tickers |
|---|---:|---:|---:|---:|---|
| paper era, 06-01 → 06-19 (census starts 06-01) | n=14 | 29 | 29 | 0 | 7 admitted, 0 missed |
| **dark, 06-22 → 08-11** (query pinned to `account_mode='paper'`) | n=35 | 58 | 3 | **55** | **10 missed entirely** (BLZE, BTDR, CRCL, FTNT, HUT, THC, TSEM, WDFC, WKC, WULF), **3 on 2 of 5 days** (FIGS, NET, TEAM); the 3 fired are JBL's paper rows |
| **post-fix, 08-12 → 09-25** (`93dcd212`, committed 08-11) | n=32 | 39 | **39** | **0** | 9 admitted; **0 admissions unexplained by the rule** |

- **It is not broken.** Since the first scan under the fix (08-12) every admission the rule calls
  for has fired and none has fired outside it. The re-gate's "7 distinct tickers since 08-11" (now
  9) is the rule's full output, not a shortfall.
- **It is quiet because its source is small.** 19 live R3 events in 10 weeks = 1.9 a week, each
  admitting a name for 5 scan days. That is the whole population the path can ever touch.
- **Against the 55 uncaptured: the rule applies to 3** (HUT 07-20, THC 07-24 — both in the dark
  window; MRVL 08-19 — admitted 08-20→08-26 as written). All three were on the board organically on
  **every** day of their 7-day admission window (HUT 9, THC 13, MRVL 7 window days evaluated) and
  rejected each day on the pole (`runup_…%_below_90%`). **The carryforward would have admitted names
  the board was already rejecting: it adds 0 of 55** (upper bound had all three based: 3 of 55).
- Wider check, same result: all 17 live R3 names that fall inside the cohort window were evaluated
  by the board on ≥1 window day through the organic paths (`rs_1m_80` / `momentum_25pct` admit a
  MAGNA53 gapper by construction). The dark-window bug removed a tag, not an evaluation.

**(a) = 0 of 55 (0.0%).** No fix is owed; the fix that was owed shipped 08-11 and is verified above.

## 3. Cause (c) — the names do not base under the sourced HTF spec: 54 of 54 measured

Replay of the era detector with each name in the universe every window day; the furthest gate
each name ever reached (gates in the order `compute_flag_metrics` evaluates them):

| furthest gate reached in 21 days | names (of n=55) | what it means |
|---|---:|---|
| **pole under 90%** (`pivot_high / 40-session low < 1.90`) | **39** | never built the sourced flagpole |
| liquidity floor (ADV < 500k shares or ADR < 4%) | 11 | rejected before geometry; stored rejects split ADR 70 rows / ADV 64 rows |
| below SMA20 (pole ≥ 1.90 but trend broke) | 3 | ARM 1.96×, CRWV 1.94×, TWST 1.92× |
| MA stack not 10 ≥ 20 ≥ 50 (pole ≥ 1.90) | 1 | AEVA 2.10× |
| no usable history | 1 | EROC (fewer than 60 bars on file — unmeasured) |
| **reached WATCH or better on any day** | **0** | — |

| the pole, per name (best `pivot_high / 40-session low` seen in-window) | n | |
|---|---:|---|
| names with a measurable pole | n=43 | median **1.60×** |
| ≥ 1.90× (the sourced HTF bar) | 4 of 43 | 9.3% — and all 4 then fail the trend gate |
| **≥ 1.50× (the retired n=1 bar)** | **33 of 43** | **76.7%** |

- **A failed-Day-1 EP that recovers is not a High Tight Flag.** The typical name in this set is a
  10–20% gapper whose 8-week run is 1.3–1.8×; the spec wants 1.9× *and* a Stage-2 trend *and* a
  ≤25% flag. The 4 names with a pole are recovering off a broken trend, which is exactly what the
  Stage-2 gate is written to refuse.
- **This is the bridge to the old 53%.** 33 of the 43 clear the retired 1.50 bar; the pre-swap
  detector was admitting them at WATCH (45 of its 51 captures were flag-only). The capture rate
  never measured a handoff — it measured the pole threshold.
- **Universe was not the constraint.** 49 of 55 were on the board (median 11 of 15 window days)
  and rejected on the same gates the replay finds; the 6 never evaluated (MANE, HGTY, DCTH, MTW,
  EROC, NMAX) replay to the same rejects (or, EROC, cannot be replayed).

**(c) = 54 of 55 (98.2%) measured on bars; 55 of 55 (100%) including the one unmeasurable name,
since no lane could have evaluated it either.**

## 4. The residual

**0 of 55.** No uncaptured name promotes in the replay on a day the board did not evaluate it (a
universe gap), with or without an R3 row. The one name outside the measurement is EROC — too few
bars to run the detector at all — and that is a data-coverage limit on a 2026 listing, not a lane
failure. Nothing is left that a working carryforward or a wider universe would have caught.

## 5. What the 60–70% target was pointing at — ⚖ THE LINE

The target (`data_gated_reviews.yaml`, P7.2/P7.3b Stage 2, written 2026-05-17) was set when the
flag board promoted ~18% of its universe under the n=1 50/60 spec. #356 replaced that spec with the
sourced one on 2026-06-26, deliberately and signed; promotion fell to ~2%. On today's detector:

| to reach | flag leg needs | that means |
|---|---:|---|
| 60% of n=69 | ≥ 34 more flag captures than the 6 it has (if the 9M legs stay gone) | admitting ~33 of the 43 names that sit between a 1.50× and a 1.90× pole — i.e. the retired bar |
| 20% without the 9M legs | ≥ 7 more | same names, same knob |

**Reaching it means re-widening flag promotion — partially undoing #356. That is a detection
criterion and the operator's sole authority. It is surfaced here, not proposed.** Capture is a reach
measure: the 53% it used to read was mostly loose WATCH flags on names with a 1.5× pole, which is
60% of noise, and worse than 20% of substance.

## Recommendation (his ruling either way)

**Retire the 60–70% number.** It was written against a detector that no longer exists, and the two
causes it was meant to discriminate are now measured: the carryforward is working (0 of 55 owed
to it), and the names do not form the setup the sourced spec describes (54 of 54 measured).
Whether *any* capture target belongs on the HTF detector is a separate question — the detector's
job is finding High Tight Flags, and a failed EP's recovery is a different shape. If he wants a
delayed-EP reach lane, that is a lane question (`docs/setups/delayed_ep_reentry.md` owns it), not
an HTF threshold.

**Fork, surfaced not pre-decided:** keep the sourced 1.90 pole (target retired) — or re-widen flag
promotion toward the retired bar to lift the number (= a #356 reversal under `CHANGE_PROCESS`
rule 3, with the 1.50 admits' own outcomes to be measured first). His call.

## What this does not answer

- **Whether the 55 were tradeable by any other setup.** Capture counts reach, never money; this doc
  says nothing about whether a delayed-EP or anticipation entry on these names would have paid.
  Median 21-day high over the gap-day open is +15.1% (n=55; 16 names ≥ +20%), which is the size of
  the reach question, not an answer to it.
- **Whether 20.3% is the steady state.** n=69 over nine weeks; and 7 of the 14 captures came from
  9M legs that no longer write (the EP-alert leg) or still write outside the 9M gate (the Day-2
  sweep) — the same measure on the next window will read differently for reasons unrelated to
  the flag board.
- **The replay's starting state.** Each name's chain starts fresh at alert+1 with no prior pivot
  or stage. The 538 of 538 stage agreement with the board's stored rows covers that assumption
  for the days both exist; days the board did not evaluate rest on the replay alone.
- **HEAD's detector.** The replay ran the window-era code (`0f82018f`). HEAD adds #592's
  pivot-walk rule, which holds a pole top in place across a wick — it cannot turn a 1.60× pole into
  a 1.90× one, but it was not re-run here.
- **EROC.** Not replayable (fewer than 60 bars); counted as unmeasured.
- **The ADR floor.** 11 names stop at liquidity, mostly ADR < 4%. That floor is a sourced spec
  value with its own data-gated tune review (`htf_adr_threshold_tune`); nothing here bears on it,
  and nothing here proposes touching it.
- **The pre-swap side.** 53.1% is reproduced only to bridge; whether the 1.50-bar admits were
  good flags is `docs/setups/htf.md` known-limitation 1's question, not this one's.

## Appendix — the 55 uncaptured post-swap names

Furthest gate = the era detector replayed with the name in the universe every window day. Best
pole = the highest `pivot_high / 40-session low` seen in-window (blank when the liquidity floor
rejected the name before the pole was measured).

| Ticker | Alert | Day-1 outcome | 21-day high over gap open | Board days evaluated (of window) | Furthest gate reached | Best pole (x) |
|---|---|---|---:|---:|---|---:|
| AVAV | 06-30 | NO_ENTRY | +13.5% | 10 of 14 | pole_under_90pct | 1.48 |
| AEHR | 07-15 | NO_ENTRY | +13.1% | 13 of 15 | pole_under_90pct | 1.74 |
| MANE | 07-15 | LOST_DAY1 | +5.4% | 0 of 15 | pole_under_90pct | 1.49 |
| HUT | 07-20 | LOST_DAY1 | +18.6% | 9 of 15 | pole_under_90pct | 1.87 |
| IREN | 07-20 | SKIPPED | +20.1% | 8 of 15 | pole_under_90pct | 1.50 |
| HAS | 07-21 | SKIPPED | +15.8% | 13 of 15 | liquidity | — |
| ARWR | 07-22 | NO_ENTRY | +6.4% | 13 of 15 | pole_under_90pct | 1.38 |
| NVCR | 07-23 | LOST_DAY1 | +19.2% | 9 of 15 | pole_under_90pct | 1.60 |
| THC | 07-24 | LOST_DAY1 | +15.1% | 13 of 15 | pole_under_90pct | 1.67 |
| NNE | 07-27 | SKIPPED | +27.3% | 5 of 15 | pole_under_90pct | 1.28 |
| QBTS | 07-27 | LOST_DAY1 | +23.2% | 9 of 15 | pole_under_90pct | 1.56 |
| TER | 07-29 | SKIPPED | +20.7% | 13 of 15 | pole_under_90pct | 1.58 |
| TEVA | 07-29 | SKIPPED | +12.4% | 13 of 15 | liquidity | — |
| ARM | 07-30 | NO_ENTRY | +16.0% | 9 of 15 | below_sma20 | 1.96 |
| CORT | 07-30 | SKIPPED | +8.7% | 13 of 15 | pole_under_90pct | 1.74 |
| EME | 07-30 | SKIPPED | +12.1% | 3 of 15 | liquidity | — |
| LRCX | 07-30 | SKIPPED | +8.5% | 12 of 15 | pole_under_90pct | 1.72 |
| PWR | 07-30 | SKIPPED | +12.0% | 3 of 15 | pole_under_90pct | 1.28 |
| SIMO | 07-30 | SKIPPED | +5.8% | 4 of 15 | pole_under_90pct | 1.82 |
| COHU | 07-31 | SKIPPED | +10.1% | 12 of 15 | pole_under_90pct | 1.80 |
| FET | 07-31 | SKIPPED | +42.3% | 14 of 15 | liquidity | — |
| FTK | 08-03 | NO_TRADE_ROW | +58.0% | 11 of 15 | pole_under_90pct | 1.83 |
| LIND | 08-03 | NO_TRADE_ROW | +12.9% | 10 of 15 | pole_under_90pct | 1.62 |
| TSAT | 08-04 | SKIPPED | +39.9% | 9 of 15 | liquidity | — |
| ZBRA | 08-04 | SKIPPED | +17.0% | 14 of 15 | pole_under_90pct | 1.78 |
| HGTY | 08-05 | SKIPPED | +10.1% | 0 of 15 | liquidity | — |
| KTOS | 08-05 | SKIPPED | +14.0% | 12 of 15 | pole_under_90pct | 1.56 |
| AEVA | 08-06 | SKIPPED | +9.7% | 10 of 15 | ma_stack | 2.10 |
| CAI | 08-06 | SKIPPED | +49.1% | 15 of 15 | pole_under_90pct | 1.55 |
| DCTH | 08-06 | SKIPPED | +24.2% | 0 of 15 | pole_under_90pct | 1.53 |
| INSM | 08-06 | NO_ENTRY | +5.7% | 14 of 15 | liquidity | — |
| RDW | 08-06 | NO_ENTRY | +15.9% | 13 of 15 | pole_under_90pct | 1.83 |
| SITM | 08-06 | SKIPPED | +11.4% | 12 of 15 | liquidity | — |
| U | 08-06 | SKIPPED | +34.6% | 15 of 15 | pole_under_90pct | 1.87 |
| FROG | 08-07 | NO_ENTRY | +9.9% | 11 of 15 | pole_under_90pct | 1.60 |
| MTW | 08-07 | SKIPPED | +24.5% | 0 of 15 | liquidity | — |
| ONTO | 08-07 | SKIPPED | +17.9% | 11 of 15 | pole_under_90pct | 1.65 |
| QNST | 08-07 | NO_ENTRY | +13.2% | 14 of 15 | pole_under_90pct | 1.85 |
| TWLO | 08-07 | SKIPPED | +9.8% | 14 of 15 | pole_under_90pct | 1.42 |
| ACHR | 08-10 | SKIPPED | +13.7% | 13 of 15 | pole_under_90pct | 1.70 |
| NESR | 08-10 | SKIPPED | +15.4% | 14 of 15 | pole_under_90pct | 1.55 |
| TH | 08-10 | SKIPPED | +26.5% | 9 of 15 | pole_under_90pct | 1.28 |
| ATRO | 08-12 | SKIPPED | +12.2% | 7 of 15 | pole_under_90pct | 1.47 |
| CRWV | 08-12 | SKIPPED | +8.1% | 10 of 15 | below_sma20 | 1.94 |
| EROC | 08-12 | NO_ENTRY | +35.3% | 0 of 15 | no usable history | — |
| MRX | 08-12 | SKIPPED | +20.4% | 9 of 15 | pole_under_90pct | 1.30 |
| CGEM | 08-13 | SKIPPED | +11.9% | 15 of 15 | pole_under_90pct | 1.54 |
| KURA | 08-13 | SKIPPED | +31.1% | 13 of 15 | pole_under_90pct | 1.58 |
| NMAX | 08-14 | SKIPPED | +19.1% | 0 of 15 | pole_under_90pct | 1.78 |
| VERA | 08-14 | SKIPPED | +18.1% | 8 of 15 | pole_under_90pct | 1.41 |
| ARGX | 08-17 | SKIPPED | +15.7% | 14 of 14 | liquidity | — |
| MRVL | 08-19 | LOST_DAY1 | +6.0% | 7 of 14 | pole_under_90pct | 1.55 |
| TWST | 08-19 | SKIPPED | +21.4% | 13 of 14 | below_sma20 | 1.92 |
| UUUU | 08-21 | SKIPPED | +12.8% | 11 of 14 | pole_under_90pct | 1.52 |
| VEEV | 08-27 | SKIPPED | +5.5% | 13 of 14 | liquidity | — |

## Files

- `docs/analysis/668_alpha_capture_causes_2026-09-26.md` — this document
- `scripts/probes/_668_pull.py` — the one-shot read-only prod pull (five queries + bars)
- `scripts/probes/_668_analyze.py` — baseline reproduction, rule audit, era-code replay, tables
- `scripts/probes/_668_out/` — `summary.txt`, `per_name.csv`, `rule_audit.csv`,
  `replay_vs_stored.csv`, and the raw captures (`cohort.csv`, `r3_rows.csv`, `r3_flag_rows.csv`,
  `scan_census.csv`, `cohort_flag_rows.csv`); `bars.csv.gz` (611 KB) is gitignored and
  re-derivable with `_668_pull.py --bars`; the era detector is extracted to a temp dir at run time
