# #468 — MODERATE-vs-HIGH EP realized-R study (2026-07-18)

**Status: STUDY ONLY — probe delivered + numbers RUN 2026-07-18 (§3).** ⚠ CORRECTION
(operator-caught): the HIGH-"actual" arm's "31 closed magna53" = **26 PAPER + 5 LIVE** (no
`account_mode='live'` filter) — it is the SETUP's realized-R, not the live book (live = 5 closed,
−$96 real-$). Nothing here
changes entry/sizing/detection logic (THE LINE). Whether MODERATE→ORB-entry ships is the
**operator's** call, and only after this study's numbers + a full backtest + CHANGE_PROCESS.

Probe: `scripts/probes/_468_moderate_realized_r.py` (read-only; phased like
`scripts/_327_replay.py`; reuses the `anticipation.simulate` / `build_mixed_path` /
`SETTLE_RULE` primitives — the proven MFE-free reconstruction, not reinvented).

---

## 1. The question

Q4 (`docs/analysis/ep_theme_coverage_loop_design_2026-07-13.md` §5-RESULTS) found MODERATE ≈
HIGH on **raw** 5-day forward return:

| pop | n | settled | avg 5d | med 5d | wins ≥5% |
|---|---|---|---|---|---|
| C_all_moderate | 83 | 63 | **+13.2%** | +6.2% | 40 (63%) |
| D_all_high | 157 | 129 | **+10.4%** | +7.0% | 74 (57%) |

But MODERATE gets a briefing, NOT an ORB entry — raw forward return (close-anchored, stopless)
≠ realized-R under the live bracket. The ORB geometry is unforgiving: entry chases the ORB-high
break, the stop sits at the 1-minute ORB-low (median stop distance small relative to a gapper's
intraday range), the order dies at 10:00 ET unfilled, and 9:45+ detections never submit. A
population can carry raw-return parity and still be untradeable once that geometry bites
(day-0 stop-outs + no-fills + too-wide skips). **Does MODERATE keep its parity in realized-R
terms, or does the entry/stop geometry erase it?**

## 2. Method

Three arms, one machinery:

- **MODERATE as-if** — every `mi_ep_alerts` MODERATE (source='live', deduped per ticker/date,
  **excluding** names that also fired HIGH the same day — live already entered those as HIGH,
  promotion wouldn't change them) reconstructed through the live MAGNA53 ORB pipeline.
- **HIGH as-if** — every HIGH alert through the IDENTICAL reconstruction. This is the
  apples-to-apples comparator (same simulator error on both sides).
- **HIGH actual** — `mi_live_trades` (`signal_type='magna53'`, status closed):
  R = `total_pnl / risk_dollars` under the REAL exit engine. Paired against HIGH as-if on
  shared (ticker, alert_date) it calibrates the reconstruction (the SETTLE_RULE↔live-exit
  delta + fill-model error); that signed correction frames how to read the MODERATE arm.

Live geometry, faithfully applied (each rule mirrored from the cited live code):

| Rule | Value | Source |
|---|---|---|
| ORB bar | earliest 1-min bar in 9:30–9:35 ET | `alpaca_client.get_first_bar` |
| Entry | stop-limit BUY, trigger @ ORB-high; limit = max(hi×1.005, hi+$0.02) | `order_manager.stop_limit_buy_price` |
| Stop | ORB-low | `order_manager.prepare_orb_order` |
| Validation | zero-range skip; ORB range > 1.5×ATR14 → `setup:stop_too_wide`; unknown ATR passes | `backtester.filters.validate_orb_entry` |
| ATR14 | Wilder TR, mean of last 14 TRs **through the prior close** (live 9:31 parity) | `compute_atr_14` docstring |
| Fade guard | skipped — MAGNA53 passes `ratio=None` | `entry_pipeline.check_fade_guard` |
| Window | detection ≥ 9:45 ET → `WINDOW_OUT_OF_ORB` (never submitted); submission = max(detection, 9:31) | scan-window rule; `shadow_orb_tracker._fetch_magna53_high_pre_open` |
| Fill deadline | trigger bar < 10:00 ET; else clean miss (0R in the full-universe view) | 10:00 unfilled-cancel job |
| Gap-through | trigger bar opens above the limit → order rests; fills only if price returns to the limit before 10:00 | stop-limit semantics |
| Exit | `anticipation.SETTLE_RULE` (+1R/+3R ½/½, day-5 time stop), 'pess' intrabar bound, mixed minute+daily path | `anticipation.simulate` / `build_mixed_path` (#327 primitives) |

Reported per arm: the funnel (window-ineligible / no-bar / too-wide / no-fill counts), fill
rate, **filled-only** and **full-universe (no-fill = 0R)** stats (median/mean/win%/total/top3
share/ex-top3 — the #327 outlier-decomposed shapes), clean vs polluted strata (§5's judge
window: polluted = alert_date 2026-05-11..2026-06-24), day-0 full-exit rate + stop-distance
median (the "chop" diagnostics), and raw `fwd_5d_pct` on the SAME filled names (the Q4-parity
recheck inside this cohort).

**Machinery verified** before any prod read: 27 hand-computed fixture checks (day-0 stop =
−1.00R; +1R/+3R ladder = +2.00R exactly; 10:00-cutoff no-fill incl. a break AT 10:00; ATR
too-wide boundary both sides; zero-range; gap-through-then-limit-touch fill at the limit;
in-window detection ignoring a pre-submission break; all four eligibility branches; ATR
prior-close basis; period split boundaries) + a synthetic end-to-end run of the full report
pipeline. All pass.

## 3. Results

**RUN 2026-07-18** (local, over the pulled TSVs — verbatim probe output):

```
MODERATE as-if : funnel alerts=84 filled=28 no_fill=10 not_settleable=1 stop_too_wide=4 window_out_of_orb=41
                 fill rate 28/38 (74%)
                 filled-only  n=28 median +0.00R mean +0.03R win 18% total +0.9R top3 650% ex-top3 -0.20R
                 full universe n=38 mean +0.02R (no-fill = 0R)
                 clean filled n=10 median -1.00R mean -0.60R win 0% · polluted n=18 mean +0.38R
                 day-0 full exits 19/28 (8 negative) · stop distance median 3.6% · raw fwd_5d same names avg +8.3%
HIGH as-if     : funnel alerts=161 filled=72 no_fill=27 not_settleable=4 stop_too_wide=6 window_out_of_orb=52
                 fill rate 72/99 (73%)
                 filled-only  n=72 median -1.00R mean +0.02R win 29% total +1.3R top3 449% ex-top3 -0.07R
                 full universe n=99 mean +0.01R
                 clean filled n=30 mean +0.11R · polluted n=42 mean -0.05R
                 day-0 full exits 61/72 (35 negative) · stop distance median 3.0% · raw fwd_5d avg +8.5%
HEAD-TO-HEAD   : delta (MOD − HIGH) filled-only median +1.00R mean +0.01R
HIGH actual    : closed n=31 · median -0.79R mean -0.62R win 19% total -19.1R · rows cancelled=36 closed=31 skipped=95
                 calibration n=28 paired: actual − recon median -0.08R mean -0.40R
```

**Reading against the §3 pre-committed bars:** MODERATE holds within 0.25R of HIGH as-if on
both filled-only (mean +0.03 vs +0.02; median +0.00 vs −1.00 — MODERATE ahead) and
full-universe mean (+0.02 vs +0.01), with an equal fill rate (74% vs 73%) → mechanically
"worth pursuing" — BUT the strata guard bites: the CLEAN MODERATE stratum is n=10, mean
−0.60R, win 0% (all parity lives in the judge-authored polluted window), below the N-floor
of 10 meaningful fills for the primary stratum. And the calibration haircut is −0.40R mean
(live exits + fills cost that much vs SETTLE) — applied to either arm, both go negative.
Net: **no promotion case at this N; the geometry+management diagnosis comes first** — see
`docs/analysis/468b_high_realized_r_diagnosis_2026-07-18.md` (the −19.1R decomposition:
management ≈ −9R gross = #306; geometry −6.3R; stop-execution −6.7R incl. SYRE −4.0).
Operator fork per §6 route (b): the Q4 parity feeds score composition, not entry expansion,
unless a clean-window extension changes the clean stratum.

### Pre-committed reading (signed BEFORE the numbers — the §5/F-E discipline)

- **N floor:** ≥10 MODERATE fills. Below that the study is underpowered — extend the window
  (backfill more history) rather than conclude.
- **"Geometry kills the parity"** (no-go) if EITHER: MODERATE full-universe mean R < 0, OR
  MODERATE filled-only median trails HIGH as-if by > 0.5R, OR the MODERATE funnel shows the
  population structurally can't enter (fill rate < ~half of HIGH's, or window/too-wide
  ineligibility consuming most of the cohort). Then the Q4 raw parity is a "right EPs"
  detection signal, not a tradeable entry — route the insight to score composition (#468's
  B6/meta-rubric thread), not to entry expansion.
- **"Worth pursuing"** (→ operator decision + full backtest) if MODERATE holds within ~0.25R
  of HIGH as-if on BOTH filled-only median and full-universe mean, with a comparable fill
  rate. Even then the ship decision is NOT automatic: more entries = more slot contention
  (see fidelity limit F6) and a selectivity-philosophy call the design doc explicitly
  reserves for the operator (§7.5: "more HIGHs = more ORB entries").
- **Calibration sign matters:** if HIGH actual − HIGH as-if is materially negative (live
  exit engine worse than SETTLE_RULE), apply the same haircut mentally to the MODERATE arm
  before reading the bars above.
- **Strata guard:** read the clean stratum as primary. Polluted-window tiers were
  judge-authored; if clean/polluted disagree, clean decides.

## 4. Why unrun + exact reproduction

The probe's Phase A uses the established operator-authorized read-only path
(`ssh apollo@87.99.134.162 → docker exec -i apollo-postgres psql -U apollo -d apollo -tAX`,
the `scripts/_454_regime_stratified_envelope.py` runner shape, SELECT-only asserted). This
session's permission layer (auto-mode classifier) denied that command class; per instruction
the probe was delivered fully instead. From a session/workstation with prod SSH permission:

```bash
python scripts/probes/_468_moderate_realized_r.py --pull-cohort   # 2 read-only SELECTs → _468_cohort.tsv, _468_trades.tsv
python scripts/probes/_468_moderate_realized_r.py --pull-bars     # Polygon via apollo-market env → _468_daily.tsv, _468_minute.tsv (~3 min)
python scripts/probes/_468_moderate_realized_r.py                 # local settle + report (offline, re-runnable)
```

The two SELECTs, verbatim (also embedded in the probe as `COHORT_SQL` / `TRADES_SQL`):

```sql
-- cohort (one row per ticker/date/tier, earliest detection):
SELECT DISTINCT ON (a.ticker, a.alert_date, a.score_tier)
       a.ticker, a.alert_date, a.score_tier,
       COALESCE(a.ep_score, 0), COALESCE(a.gap_pct, 0),
       to_char(COALESCE(a.detected_at, a.created_at) AT TIME ZONE 'America/New_York',
               'YYYY-MM-DD HH24:MI:SS'),
       COALESCE(a.catalyst_quality, ''), COALESCE(a.grade_engine_authority, ''),
       COALESCE(a.baseline_floor_tier, ''), COALESCE(o.fwd_5d_pct::text, '')
FROM mi_ep_alerts a
LEFT JOIN mi_ep_scan_outcomes o
       ON o.ticker = a.ticker AND o.scan_date = a.alert_date
WHERE a.score_tier IN ('MODERATE', 'HIGH') AND a.source = 'live'
ORDER BY a.ticker, a.alert_date, a.score_tier, COALESCE(a.detected_at, a.created_at);

-- HIGH actual (live exit engine ground truth):
SELECT t.ticker, t.alert_date, t.status, COALESCE(t.skip_reason, ''),
       COALESCE(t.orb_high::text, ''), COALESCE(t.orb_low::text, ''),
       COALESCE(t.atr_14::text, ''), COALESCE(t.entry_price::text, ''),
       COALESCE(t.stop_price::text, ''), COALESCE(t.risk_dollars::text, ''),
       COALESCE(t.total_pnl::text, ''), COALESCE(t.remaining_shares::text, ''),
       COALESCE(to_char(t.filled_at AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI:SS'), ''),
       COALESCE(to_char(t.closed_at AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI:SS'), ''),
       COALESCE(t.account_mode, '')
FROM mi_live_trades t
WHERE t.signal_type = 'magna53'
ORDER BY t.alert_date, t.ticker;
```

Bars (Phase B) are Polygon 1-min day-0 aggs per (ticker, alert_date) plus 1-day aggs per
ticker (alert−70d → alert+15d, for the prior-close ATR14 and the 5-bar forward window),
pulled through the in-container `POLYGON_API_KEY` exactly as `scripts/_327_pull_minute.py`
does (read-only market data; ~240 minute-days + ~200 daily ranges expected from the Q4
cohort sizes).

## 5. Fidelity limits (state them before believing any number)

- **F1 — exit rule is a proxy.** Both as-if arms settle on `SETTLE_RULE` (+1R/+3R halves,
  day-5 time stop), NOT the live exit engine (partial scan day 3-5, SMA trail, breakeven,
  giveback hooks). The HIGH-actual calibration arm bounds this error empirically on HIGH;
  the correction's SIGN transfers to MODERATE, its magnitude only approximately.
- **F2 — minute-bar fill model.** Intrabar ordering is unknown → 'pess' bound (stop-first on
  conflicted bars); trigger = bar-high ≥ ORB-high (stop-order semantics; matches
  `shadow_orb_tracker`'s convention). Fill at trigger/open/limit per stop-limit rules; true
  sub-minute gap-throughs and queue position are invisible. Slippage beyond the limit buffer
  is not modeled (bounded by the buffer: ≤0.5%/$0.02).
- **F3 — feed asymmetry.** Live ORB bar comes from the Alpaca feed (IEX default);
  reconstruction uses Polygon consolidated bars. Consolidated ORB H/L can be marginally wider
  → slightly earlier/ higher reconstructed triggers on both arms equally (comparison-neutral,
  level-shifting).
- **F4 — adjusted bars.** Polygon `adjusted=true` (repo standard) vs fill-basis unadjusted
  (the #306 lesson). Distorts only names with a split/dividend inside the ±window; the EP
  cohort is recent and gappers rarely split mid-window — spot-check any outlier R.
- **F5 — detection-time fidelity.** Submission minute = `COALESCE(detected_at, created_at)`
  in ET; pre-2026-03-20 rows carry a poisoned migration `created_at` → excluded from the
  primary universe (counted in the funnel; a 9:31-assumption sensitivity view is printed).
  MODERATEs never ran the live submission path, so their would-be submission latency
  (bar-fetch retries, spec build) is idealized to the detection minute — flatters MODERATE
  by seconds, not minutes.
- **F6 — no portfolio effects (the big one for the DECISION).** Position caps (5 global +
  per-strategy), daily-loss halt, drawdown breaker, dup/open-position guards, and capital
  contention are NOT simulated. Promoting MODERATE roughly triples bracket count; on hot
  days the 5 slots would force displacement choices between a MODERATE fill and a later
  HIGH. Per-name R parity is NECESSARY but not SUFFICIENT — the full backtest (post-operator
  go) must simulate the portfolio layer.
- **F7 — tier era mixing.** During the judge-authority window (2026-05-11..06-24) score_tier
  was judge-authored; strata are split and clean decides (§3).
- **F8 — regime coverage.** The cohort spans whatever regimes the alert table holds; the
  MODERATE threshold band (50–69 vs regime-dependent HIGH cut 65–75) means the two arms'
  score compositions shift with regime. Not correctable at this N; flagged for the full
  backtest.

## 6. Recommendation (conditional — the numbers decide, the operator rules)

1. **Run the three probe commands** from a prod-permitted session (~5 min total) and paste
   the report into §3.
2. Read against the **pre-committed bars** in §3 — they were signed before the numbers, so
   the reading can't be post-hoc rationalized.
3. If "worth pursuing": this becomes an **operator fork** (entry expansion = more brackets =
   THE LINE territory) with a 1-line rec attached to the actual numbers, and the next gate
   is a **full portfolio-level backtest** (F6) + CHANGE_PROCESS on `magna53_ep.md` before
   any live flip. A shadow-first ramp (MODERATE brackets in `mi_orb_shadow_trades` alongside
   the 5-min shadow) is the natural no-money instrumentation if the operator wants forward
   evidence first — note `shadow_orb_tracker` is currently HIGH-only
   (`_fetch_magna53_high_pre_open`), so that widening is itself a small gated change.
4. If "geometry kills": close #468 with the numbers filed here; the Q4 parity then feeds the
   score-composition thread (B6 / meta-rubric — the 60-69 band being the strongest is the
   same signal seen from the other side), not entry expansion.

*Probe self-test artifacts: 27 fixture checks + synthetic e2e run, 2026-07-18 (local, no
prod). Written under THE LINE: no entry/sizing/detection change; not committed.*
