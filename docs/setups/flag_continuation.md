# Continuation Flag — VCP / Qullamaggie Tightening — RETIRED as a standalone strategy

> ⚠ **SUPERSEDED 2026-06-27 by `docs/setups/htf.md` (#356)** for detection criteria — this detector's
> *code* (`flag_detector.py`) was rebuilt into the sourced HTF setup. The "Detection criteria" below
> (runup `50%/60d`, proximity `≤20%`) are the RETIRED **n=1** values; the LIVE `/flags`-board criteria are
> HTF's `90%/40d` + `≤25%` absolute-low depth + the `10/20/50` Stage-2 trend filter + flagpole volume
> confirmation — see `htf.md` for the current spec + provenance. The universe/carryforward and the
> 5-stage machine here are unchanged and still accurate (they now serve the HTF board).
>
> ⚠ **RETIRED 2026-07-19 as a standalone *strategy*, per `docs/decisions/0026-consolidation-family-unification.md`
> (ADR 0026) §D1 (card C4).** `flag_continuation` is no longer one of the three Family-A setups — it does
> not exist as its own play. Its conceptual role (enter on a confirmed range breakout) is absorbed as the
> **consolidation family's Confirm (b) entry mode** (`entry_mode='confirm'` shadow rows in
> `mi_consolidation_entry_shadow`, SHADOW-only — see "Retirement + absorption" below). This is a
> **documentation-only** change: the `mi_strategies` row was already flipped `phase='deprecated'` earlier
> under ADR 0022 §1 / #424 (operator-signed 2026-07-05/06); ADR 0026 does not re-deprecate it, it reframes
> the retirement inside the 3-setup family model and completes the param reconciliation. `flag_detector.py`
> and the `/flags` board are **untouched** by this change — they remain the live HTF setup's code+telemetry.

> ⚠ **DISABLED 2026-08-02** — `mi_strategies.enabled` flipped `true → false` (operator-directed:
> *"keep our system clean is ok"*). It had been `phase='deprecated'` **but still `enabled=true` since
> 2026-07-05** — a legal-but-half-alive state that kept the registry row live while it looked retired.
> All three deprecated strategies were in it (9M Day 2 for 26 days, Continuation Flag, Fishhook). That
> combination is now **impossible**: `strategies.registry.assert_no_deprecated_but_enabled` raises at
> load. **The detector was NOT touched** — `_flag_scan_job` still runs 17:25 ET and still stages
> (7/31: 562 unqualified · 9 INVALIDATED · 3 WATCH · 2 TIGHTENING · 1 COILED).

## Why the DETECTOR exists but the STRATEGY does not — the one-paragraph answer

Per the operator's **SETUP vs FAMILY** definition (CLAUDE.md, 2026-08-02): *a setup needs a clear buy
point AND stop; a family is a chart condition that hosts setups but is not tradeable itself.*

- **`flag_detector.py` is STAGING, and it is LIVE** — it computes the general runup → coil → tighten →
  break state machine (`WATCH/TIGHTENING/COILED/TRIGGERED/INVALIDATED`) over the universe. Operator,
  2026-08-02: *"flag detector is on, that can just be detecting flags in general of which the real
  setups can be sourced from, the whole stage of run up, coil etc is useful overall, though some
  parameters differ like how steep run up is etc."* It is **the live HTF setup's engine** (`htf.md`)
  and it feeds the `/watch` board.
- **`flag_continuation` the STRATEGY is dead** because "a continuation flag" names a *shape*, not an
  entry: on its own it has no buy point and no stop. The tradeable thing sourced from that shape is
  the **Confirm (b)** entry mode of the consolidation family, and that lives elsewhere
  (`anticipation.py::confirm_signal_at`, shadow-only).
- ⚠ **Therefore the parameters legitimately DIFFER by consumer** — runup steepness, coil tightness,
  whether an undercut disqualifies. Anticipate wants one thing, a breakout entry another, HTF another.
  **Do not "reconcile" the detector to a single universe**; that would collapse a shared capability
  into one caller's preferences. Shared staging underneath, per-setup parameters on top.

**Phase**: **Deprecated** (`mi_strategies.phase='deprecated'`, terminal — ADR 0022 §1 / #424, 2026-07-05/06;
confirmed by ADR 0026 §D1, 2026-07-19). No promotion path; `entry_pipeline._phase_gate_skip_reason` treats
`deprecated` like `shadow` (never fires an order) as defense-in-depth. The detector *code* underneath
(`flag_detector.py`) is NOT deprecated — it is the live HTF setup's engine (see `htf.md`); only this
*strategy identity* (registry row + promotion/entry-gate eligibility) is retired.
**Origin**: Mark Minervini VCP (Volatility Contraction Pattern) + Qullamaggie tightening flag methodology.
**Code**: `agents/market_intelligence/flag_detector.py` (now HTF's engine, see `htf.md`), scheduler 17:25 ET
cron `flag_continuation_scan` (job name unchanged; historical). The retired Confirm(b) breakout *idea* now
lives as a separate, independent pure function: `agents/market_intelligence/anticipation.py::confirm_signal_at`
(see below) — it does **not** reuse `flag_detector.py`'s code or universe.

## Definition

A stock makes a strong runup (≥ 50% over weeks), then forms a tight consolidation (range contracting, volume drying up) below the runup high. The base is the bullish rest before the next leg up; the breakout above base high is the entry signal.

This is a long-side continuation pattern — opposite of `parabolic_short.md`. Both share visual surface features (high-volume past activity, structural metrics) but differ on intent and outcome.

## Universe / eligibility

Organic paths (common-gate enforced):
- **Top 200 RS** OR **rs_1m percentile ≥ 80** OR **last_close / 10-session min ≥ 1.25** (burst inclusion)
- Common gates: price ≥ $5, ADV-20 dollar volume ≥ $5M, ≥ 60 sessions of history, security type ∈ (CS, ADRC)
- Sector enriched via `mi_ticker_overrides`

Carryforward paths (bypass common gates — already vetted on prior admission):
- **MAGNA53-failed R3** (P7.2 2026-05-17) — R3-stopped MAGNA53 names in last 7d. Env: `MAGNA53_FLAG_CARRYFORWARD_ENABLED`
- **9M universe-watch** (P7.3b 2026-05-17) — ALL 9M EPs in last 14d. Env: `NINEM_FLAG_CARRYFORWARD_ENABLED`
- **Flag-stage carryforward** (2026-05-19) — tickers that were COILED or TIGHTENING in last 5 trading days. Bridges one-day RS percentile dips that would otherwise drop consolidating leaders from the universe. Env: `FLAG_STAGE_CARRYFORWARD_ENABLED`

## Detection criteria — RETIRED n=1 values, superseded by `htf.md` (kept for provenance only)

> These are the n=1 `50%/60d` runup + `≤20%` proximity values retired 2026-06-27 (#356). The
> LIVE criteria running in `flag_detector.py` today are HTF's sourced values — see `htf.md`.
> This section is NOT "current" despite its original heading; retained verbatim below for
> historical/provenance reference (the pivot/hysteresis/fresh-tightening mechanics ARE still
> live, just with HTF's runup/depth/trend numbers plugged in — see the top-of-doc banner).

`compute_flag_metrics` (`flag_detector.py:611`) emits a stage per (ticker, scan_date):

### Pivot anchor

- `_find_pivot_high`: 25-session lookback EXCLUDING today. Anchor = bar with highest VOLUME among bars whose HIGH is within `_PIVOT_HIGH_BAND` (2%) of period max-high.
- High-anchored intent: capture blow-off shooting-star reversal days that close low but had the runup's true volume climax.
- `pivot_high_price` = pivot bar's high; `base_high` = max base bar high; `base_low` = min base bar low; `base_age` = number of bars between pivot and today.

### Qualifying gates

1. `base_age ≥ 3` (`_BASE_AGE_MIN_WATCH`)
2. `base_age ≤ 25` (`_BASE_AGE_MAX`) — older base = stale, INVALIDATED
3. **Runup**: `pivot_high / 60d_low ≥ 1.50` (50%+ prior runup)
4. **Proximity**: `|today_close - pivot_high| / pivot_high ≤ 20%` (close to pivot, not extended past)

### Stage progression

- `unqualified` → `WATCH` → `TIGHTENING` → `COILED` → `TRIGGERED` (or `INVALIDATED`)

Stages depend on:
- `range_contraction_ratio` (recent 5-bar range vs base average)
- `vol_contraction_ratio` (recent 5-bar volume vs ADV20 or recent base avg, whichever is lower per fresh-tightening hybrid)
- `last_body_pct` and `prev_body_pct` (small bodies = tight days)
- `breakout_close > base_high` (TRIGGERED)
- `close < pivot_low` (INVALIDATED)

### Hysteresis

Single-day downward stage flips held one day (`held_from_stage` audit-reviewable). INVALIDATED never holds; upgrades fire immediately. Implemented in `compute_flag_metrics` via `yesterday_stage` parameter.

### Fresh-tightening predicate (alternative COILED path)

Added 2026-05-04 to catch short-base tight setups that don't fit the early-vs-recent window math. Fires when:
- `base_age ≥ 4`
- `max(2-bar TR%) ≤ 0.6 × ATR-14%`
- `max(2-bar volume) ≤ max(recent_5d_avg_vol, 0.5 × ADV20)` (hybrid ceiling, advisor-flagged 2026-05-05)

## Known limitations / open questions

1. **ATR-relative pivot walk threshold** (filed 2026-05-08): `_PIVOT_WALK_THRESHOLD` is currently a flat 1% for all tickers. For a $5 stock that's a 5¢ beat — could be noise on a high-ATR runup name. Future tune: `max(0.01 × prior_pivot_high, 0.25 × ATR14)`. Ship-then-tune, not flip-blocking.

2. **Trailing-10 burst path** (CLAUDE.md 2026-05-05): currently inert (`rs_1m ≥ 80` carries the burst path on most tickers). Documented in flag_detector docstring; non-action item.

## Retirement + absorption into the consolidation family (ADR 0026 D1, card C4)

**The 3-way split (ADR 0026 §1, confirming the 2026-06-22 operator split).** What was once one
`flag_continuation` strategy is now three separate things, each with its own SSoT:

1. **Anticipation** (`docs/setups` — see `anticipation.py` module docstring / ADR 0013 §2, signed) — the
   coil-finder: enter **in** the tightening base, before the break. Family-A's `entry_mode='anticipate'`.
2. **HTF (High Tight Flag)** — `docs/setups/htf.md` — the *setup*: `flag_detector.py`'s 5-stage state
   machine, now running HTF's sourced `90%/40d` + `≤25%` depth + Stage-2 trend criteria. Drives the live
   `/flags` board + the #94 intraday break scan. **Untouched by this retirement.**
3. **Confirm (b)** — the *entry*, absorbed here — enter on the base's **confirmed breakout** (close above
   the base high, on confirming volume). This is what `flag_continuation`'s breakout logic became.

**Confirm is Family-A's breakout entry mode, not flag_detector's TRIGGERED stage.** Deliberately: gating
Confirm by membership in the flag/HTF cohort would silently under-detect the very names the family
universe is built to measure (the #270 phantom failure-mode in miniature) and would touch the load-bearing
live `/flags` path. Instead, `anticipation.py::confirm_signal_at` (~965-998) is a **new, isolated pure
function** mirroring `entry_signal_at`'s shape, detected on the **same §2 Family-A universe** the
Anticipate entry uses (`db.get_anticipation_universe`), via the EOD daily-bar pass:

- Wired at `scheduler.py:3499-3527` inside `_consolidation_readiness_job` — the **7/14-signed EOD
  §2-universe pass**, dual-mode (fires both `entry_signal_at` "anticipate" and `confirm_signal_at`
  "confirm" per ticker/anchor, same job, same digest). **[AMENDED 2026-07-18, operator-ratified]**: ADR
  0026's original text specified wiring off the #94 *intraday* flag-break event; the running implementation
  differs and is authoritative — the #327 Phase-B replay showed intraday re-timing de-rates the edge, and
  the flag cohort narrowed to the HTF 90/40 universe (#356), both favoring the EOD-§2 (#270-phantom-avoiding)
  wiring actually built.
- Entry = the break-day close (`close > base_high` where `base_high` = max base **close** since the runup
  peak, pre-break); confirming volume = `vol_min × ADV20` with `ENTRY_CONFIRM_VOL_MIN = 1.5` (`anticipation.py:962`).
  Stop = the base low (`stop_kind='base_low'`).
- Writes an `entry_mode='confirm'` row to `mi_consolidation_entry_shadow` via the same
  `insert_consolidation_entry_shadow` / settlement machinery Anticipate uses (`db.py` ~7401-7442).
  **SHADOW-only** — zero execution authority; Confirm entering the live entry pipeline is a separate, later
  money-gated promotion (`#397`), untouched by this card.
- Realized-R is **never blended across entry modes** (ADR 0013:91) — the `by_mode` settlement readout
  (`db.py` ~7513-7521) groups by `entry_mode`, and `data_gated_reviews.yaml`'s
  `consolidation_anticipate_paper_graduation` / `htf_breakout_paper_graduation` reviews already show this
  pattern for the other two modes; `consolidation_unification_review` (filed below, C5) is Confirm's.

**Param reconciliation — confirmed code-complete, no thresholds invented.** The retired `flag_continuation`
params (runup `≥50%/60d`, pivot-walk anchor, ratio-based tightness gates) reconcile to the SIGNED family
model that `confirm_signal_at` already inherits by running on the §2 universe:

| Param | Retired (`flag_continuation`) | Now (Family-A §2, signed) | Code |
|---|---|---|---|
| Runup | `≥50%` over 60d | `≥15%` (`RUNUP_MIN=1.15`) over a rolling **10-session** window | `anticipation.py:618-619`; `db.get_anticipation_universe(runup_min=1.15)` (`db.py:7285-7286`) |
| Anchor | Pivot-walk (`_find_pivot_high`, `_PIVOT_WALK_THRESHOLD`) | **Runup-peak-close** — the ANCHOR-STABILITY invariant (absolute peak-close date, not a scan-relative index, so the lifecycle key never drifts) | `anticipation.py:606-611` (invariant), `find_coil_setup` peak (`anticipation.py:687-742`) |
| Tightness | Ratio-based range/volume contraction gates | **Volatility-relative RMV/ATR** — `compute_fresh_tightening` + `compute_rmv`, the shared primitives already imported by `anticipation.py` (no duplicate implementation) | `anticipation.py:222`, `:238`; gates the `coiled` lifecycle state at `anticipation.py:825-828` |
| 0.4% tight-close | N/A (flag_continuation had no analog) | Stays **ranking-only** (Pradeep's "series of tight days" streak counter), NOT the universe admission gate — the LOCKED inclusion gate is `\|today %chg\| ≤ 1.0%` | `TIGHT_CLOSE_PCT=0.004` (`anticipation.py:57`); `tight_close_streak` (`anticipation.py:281`); `incl_max=0.010` (`db.py:7287`, `get_anticipation_universe` docstring `:7290`) |
| Universe floor | Flag-specific (`$5M` ADV, RS-based) | `$20M/day` median dollar volume, price ≥ $5 | `db.get_anticipation_universe(dvol_min=20_000_000.0, price_min=5.0)` (`db.py:7285-7286`) |

`entry_mode` currently accepts `'anticipate'` \| `'confirm'` only (`mi_cons_entry_shadow_mode_chk`,
`db.py:1829-1831`) — `'ur'` is **not yet added**; ADR 0026's D3 (undercut → `WATCH_UR`) is signed but its own
card (C3) has not landed, so U&R has no wiring to reconcile yet. Not this card's scope.

**Regression pins verified (not touched by this card):** the #94 intraday scan still reads
`mi_flag_candidates` stages (HTF board, `flag_detector.py`) unchanged; HTF detection (#356) still consumes
the same 5-stage state machine unchanged; `/flags` routing (`test_execute_task_routing.py`) is unaffected —
none of these read the `mi_strategies` registry row or `anticipation.py`.

## Change log (newest first)

### 2026-07-24 — FL-5 reconcile: doc synced to code (line citations + header clarity, no values changed)

Re-pointed every drifted line citation to the current code location (values were all still
correct — only line numbers moved from intervening commits): `compute_flag_metrics`
193→611; `get_flag_universe` 2396→4181; `breakout_vol_ratio` denominator 369→899; the
TRIGGERED-branch `coiled_today OR was_coiled_recent` check 630-635→936-949; the dual-mode
Confirm/Anticipate fire site in `scheduler.py` 3494-3501→3499-3527; `insert_consolidation_
entry_shadow` 7382-7420→7401-7442; the `by_mode` settlement readout 7493-7498→7513-7521;
`get_anticipation_universe`'s param defaults + docstring 7264-7266/7266/7269→7285-7286/
7287/7290; `mi_cons_entry_shadow_mode_chk` 1873→1829-1831. (`confirm_signal_at`/
`ENTRY_CONFIRM_VOL_MIN`/`RUNUP_MIN`/anchor-invariant/`find_coil_setup`/`compute_rmv`/
`compute_fresh_tightening`/`tight_close_streak`/`TIGHT_CLOSE_PCT`/coiled-lifecycle citations
were all still exact — no drift on those.) Also retitled the "Detection criteria (current)"
section — it documents the RETIRED n=1 values (superseded by `htf.md` 2026-06-27), and the
bare "(current)" in that header contradicted the doc's own top-of-file retirement banner for
a reader who jumps straight to that section. No code change.

### 2026-07-19 — Retired as a standalone strategy; absorbed as Family-A's Confirm (b) entry (ADR 0026 D1, card C4)

**Trigger**: `#354` / ADR 0026 (Fable weekend block 1, signed 2026-07-11/12; D1+D3 SIGNED, D2 PARKED at the
7/12 sitting). SSoT + review-filing card, executed 2026-07-19 — documentation only, no detection-criterion
or money-path change.

**Evidence**: code-verified against the running implementation, not re-derived: `mi_strategies.phase` already
`'deprecated'` on prod (ADR 0022 §1 / #424, 2026-07-05/06 — pre-dates ADR 0026, which confirms rather than
re-executes the retirement); `anticipation.py::confirm_signal_at` (shipped 2026-06-22, commit `befb41e`) and
its dual-mode wiring at `scheduler.py:3499-3527` (re-wired to the EOD §2-universe pass per the operator-
ratified 7/18 amendment) already write `entry_mode='confirm'` shadow rows on the signed §2 universe; param
reconciliation (runup 15%/10d, runup-peak-close anchor, RMV/ATR tightness, 0.4% ranking-only) was already
code-complete before this card — see the "Retirement + absorption" section above for the full mapping.

**Anticipated effect**: none on any running system — `flag_detector.py`, the `/flags` board, the #94
intraday scan, and HTF detection (#356) are byte-identical. The only new production artifact from this
card is the `consolidation_unification_review` data-gated review (`data_gated_reviews.yaml`), which will
surface once ≥10 `entry_mode IN ('confirm','ur')` shadow rows settle.

**Reversion-flag**: NEW (a documentation/registry-framing change, not a reversal — the underlying
`mi_strategies` deprecation and the Confirm shadow code both predate this entry and are unchanged by it).

**Status**: shipped 2026-07-19 (docs + review-filing only; regression pins re-verified green, see test run
below). Next: `consolidation_unification_review` fires the first settled-R readout per entry mode; drives
the next promotion (paper) decision, which remains gated behind `#397` (money) and full CHANGE_PROCESS +
operator sign-off (THE LINE — no code in this card touches a live-money path).

### 2026-05-28 — Intraday detector idempotency guard (#145, ADTN/IREN-class false-fire)

**Trigger**: ADTN + IREN false-fired in this morning's intraday flag-break scan. Both tickers had broken their TIGHTENING range yesterday 2026-05-27 with conviction (ADTN +21% above base_high on 4× volume; IREN +10% on 2× volume), but the EOD state machine left them at TIGHTENING because the TRIGGERED branch in `compute_flag_metrics` (flag_detector.py:936-949, current line — was :630-635 at ship) requires `coiled_today OR was_coiled_recent` — neither ticker had reached COILED. Today's intraday detector loaded yesterday's TIGHTENING row and saw `current_price > base_high` trivially satisfied → emitted false "fresh break" alerts.

**Evidence**: N=2 confirmed (ADTN, IREN). DB sweep across today's universe surfaced 7 more candidates in the same shape (TVTX +3.9%, UCTT +3.5%, WULF +3.1%, ARCB +2.1%, QS +0.8%, PAYS +0.6%, PLPC +0.4%) — 9/92 = ~10% of yesterday's eligible candidates had already-realized breaks. Pattern is recurring, not single-case.

**Architecture**: SQL guard in all three intraday loaders (`run_intraday_flag_break_scan`, `run_intraday_support_test_scan`, `run_intraday_ma_pullback_scan`). Each candidate query LEFT JOINs `mi_daily_closes` on `(ticker, scan_date)` and excludes rows where `prior_close > base_high`. `dc.close IS NULL` rows kept (fail-open for missing data, matches existing universe behavior).

**Anticipated effect**: ~10% of the daily intraday candidate universe stops false-firing on Day-2-of-breakout. Sister detectors (#95 support-test, #96 MA-pullback) get the same guard — both gate on stage labels that, post-bug, label these tickers as "still pre-break" when they aren't.

**User principle** (2026-05-28): "a flag is a tight trading range; if it breaks that range, it's a flag break." Idempotency guard codifies the corollary: a break realized yesterday isn't a fresh break today.

**Reversion-flag**: NEW (universe-side filter, doesn't change detection logic itself).

**Related — Fix A filed as #146**: the EOD state machine's COILED prerequisite is the deeper bug per the user principle — direct TIGHTENING→TRIGGERED on close > base_high_close + vol should be allowed. Filed as #146 methodology investigation requiring N≥10 backtest cohort. If Fix A ships, the universe guard here becomes belt-and-suspenders.

**Status**: shipped 2026-05-28. Verification: tomorrow's 9:35 AM intraday scan should NOT fire on any of ADTN/IREN/TVTX/UCTT/WULF/ARCB/QS/PAYS/PLPC (assuming they remain above base_high — most will).

### 2026-05-19 — Universe path (e): flag-stage carryforward (RVMD-class fix)

**Trigger**: RVMD on 2026-05-19 was COILED for 3 consecutive scans (5/14, 5/15, 5/18) — textbook tight consolidation in a $141-$151 range with rs_composite=92 and rs_3m=94. Today's scan dropped it entirely (not in mi_flag_candidates at all, not even WATCH). Investigation: rs_rank went 321→499 and rs_1m went 85.6→70.3 in a single day (one-day percentile rotation as bigger-mover names entered the 1-month window). All three organic universe gates (rs_top200 ≤200, rs_1m ≥80, momentum_25pct ≥+25%) failed simultaneously despite price action being identical to prior days (RVMD actually +2% on 5/19). Not in MAGNA53-failed or 9M-watch carryforward paths either.

**Evidence**: N=1 case (RVMD). But this is a STRUCTURAL inversion, not a calibration question — the flag detector's whole purpose is catching consolidating leaders before breakout. A 1-day RS percentile dip dropping a 3-day-COILED textbook setup is the gate logic working against the detector's intent. Sample-size discipline doesn't apply to gate inversions, only to threshold tuning.

**Anticipated effect**: tickers that were COILED or TIGHTENING in last 5 trading days stay in the universe. State machine handles correctness — carried-forward tickers either re-establish COILED/TIGHTENING (consolidation continued) or progress to INVALIDATED (base broke). Universe expansion alone doesn't change detection rules. Expected volume: ~20-50 additional carryforward tickers per scan tick (depending on market regime and recent setup density). Most will be the same names already in organic paths; the marginal admit is RVMD-class names on one-day RS dips.

**Architecture**: new SQL in `get_flag_universe`:
```sql
SELECT DISTINCT ticker FROM mi_flag_candidates
WHERE scan_date < $1::date AND scan_date >= ($1::date - INTERVAL '5 days')
  AND stage IN ('COILED', 'TIGHTENING')
```
Tag: `flag_stage_carryforward`. Same source-tag-list pattern as P7.2 / P7.3b carryforward paths. Multi-source admission preserved (a ticker in top-200 RS AND prior COILED captures both tags).

**Env flag**: `FLAG_STAGE_CARRYFORWARD_ENABLED=true` (default). Set false + docker compose restart to revert.

**Reversion-flag**: NEW (introduces 5th universe pattern).

**Status**: shipped 2026-05-19. Stage 1 verification: confirm RVMD appears in 2026-05-20 mi_flag_candidates with `universe_sources @> ARRAY['flag_stage_carryforward']` (and ideally re-enters COILED). Stage 2 telemetry: count carryforward-admitted tickers that progress to TRIGGERED over next 30d — if ≥10 carryforward-admitted tickers fire TRIGGERED, the fix is empirically validated.

### 2026-05-17 — P7.2 universe expansion: MAGNA53-failed carryforward

**Trigger**: R3 (drop Day-1 same-day re-entry) shipped 2026-05-17 morning leaves a known alpha-slip window — Block D audit found 65% of failed-Day-1 MAGNA53 alpha names made +5% within 21d, but only 34% caught by downstream detectors (continuation flag 31.6%, 9M EP 5.3%, sugar baby 0%, next MAGNA53 EP 0%). Sugar baby loosening (P7.1a) confirmed structurally insufficient (most names fail 9M-volume gate). The right hedge: feed R3-stopped MAGNA53 names directly into the flag detector's universe via universe-query expansion.

**Evidence**: P7.1a analysis on 76 alpha names from 60d Block D cohort — 22.4% recovery at sugar baby 0.50 cutoff (Option C verdict — sugar baby insufficient). MAGNA53-failed names are typically smaller-cap, lower-volume than 9M class. They're flag-candidate-class, not sugar-baby-class.

**Anticipated effect**: 3-10 R3-stopped names enter the flag scan's universe per scan tick (bursty around earnings season; ~1.3/day average). Flag detector evaluates them via the normal `compute_flag_metrics` — most enter as `unqualified` initially (base_age=1, runup not yet ≥50%), progress through WATCH → TIGHTENING → COILED as basing develops over 1-3 weeks. Targets ~60-70% downstream capture vs current 31.6%.

**Architecture**: modified `get_flag_universe` (db.py:4181, current line — was :2396 at ship) to return `dict[str, list[str]]` (ticker → source-tag list). New universe-pattern query: `WHERE alert_date >= scan_date - INTERVAL '7 days' AND status='closed' AND skip_reason='block:r3_reentry_disabled' AND account_mode='paper'`. Multi-source admission preserved — a ticker in top-200 RS AND R3-stopped captures both tags.

New `mi_flag_candidates.universe_sources TEXT[]` column records provenance for telemetry. Tag taxonomy: `rs_top200`, `rs_1m_80`, `momentum_25pct`, `magna53_failed_r3`, `ninem_universe_watch` (P7.3b — Monday). `ALTER TABLE ADD COLUMN IF NOT EXISTS` pattern, idempotent on restart.

**Env flag**: `MAGNA53_FLAG_CARRYFORWARD_ENABLED=true` (default). Set false + docker compose restart to revert.

**Reversion-flag**: NEW (introduces 4th universe pattern + audit-trail column).

**Status**: shipped 2026-05-17 commit `370aed1`. Stage 1 verification at Day 7-14 (universe pattern firing, looking for ≥1 R3-stopped name appearing in `mi_flag_candidates` with `universe_sources @> ARRAY['magna53_failed_r3']`). Stage 2 alpha-capture measurement at Day 21+.

### 2026-05-08 — Stable-anchor pivot (1% walk threshold)

**Trigger**: advisor flag 2026-05-08, deeper structural issue surfaced by VECO 5/06: pivot can walk forward on any new bar that beats prior pivot's high (even by 1¢). For a base making slow higher-highs in tight increments, pivot keeps walking and base_age stays near zero — contraction math never accumulates a window. The 5% → 2% band tightening (commit 42993e1) was a band-aid that addressed the volume-stealing-pivot symptom; this fix addresses the marginal-walk-forward cause.

**Evidence**: replay verification on three known calibration cases — XNDU progression unchanged (pivot stable at 04-16 throughout 4/22-5/01, every stage matches expected); VECO 4/27-5/06 base preserved with pivot at 04-24 (5/07 walks forward correctly after the +25% breakout decisively beats prior pivot); OKLO base at 04-23 preserved through 5/07 with fresh-tightening firing 5/04-5/05 as expected. No regressions on previously-correct stages.

**Anticipated effect**: pivots stay stable across the base regardless of marginal new highs in the lookback. Decisive breakouts (≥1% above prior pivot) still walk the anchor forward as today. Logic is conditional — only applies when prior pivot data is available AND prior pivot bar still falls within the current 25-session lookback. Cold start (no prior data) and aged-out (>25 sessions) cases fall through to the existing fresh-anchor logic. Same shape as the hysteresis pattern: state from yesterday's row carries forward by default, override only on decisive change.

**Reversion-flag**: NEW. Adds `_PIVOT_WALK_THRESHOLD = 0.01` constant and `prior_pivot_date` / `prior_pivot_high` kwargs through `compute_flag_metrics` → `_find_pivot_high`. New `db.get_yesterday_flag_pivots` helper mirrors `get_yesterday_flag_stages` shape (5-day lookback, DISTINCT ON ticker, filters NULL pivot fields).

**Status**: shipped 2026-05-08. Watch for: (a) bases that should reset but don't (look for pivot at age >20 with weak metrics); (b) surprise non-resets near the breakout (compare TRIGGERED rate before/after).

### 2026-05-08 — Tightened `_PIVOT_HIGH_BAND` 5% → 2%

**Trigger**: VECO 5/06 went TIGHTENING → unqualified the day before its +25% breakout. Pivot wrongly reset to 5/05 (high $52.16, 2.4% off period max $53.43 on 4/24) due to 5/05's high volume (3.0M vs 1.5M at 4/24). With pivot reset, `base_age = 0` → unqualified.

**Evidence**: 30d backtest of 6 pivot-shift cases in qualified candidates: COHU, AMSC, CORZ, FROG, TSHA all had new-pivot 2.6-4.9% off period max — all 5 blocked by 2% band. SGML new-pivot 1.2% off max → still moves (legitimate). 5 of 6 cases addressed.

**Anticipated effect**: fewer pivot resets on high-volume non-near-max-high bars; bases accumulate longer.

**Reversion-flag**: NEW.

**Status**: shipped (commit 42993e1), awaiting 5/8+ field validation.

### 2026-05-04 (session 6) — Burst-class universe + fresh-tightening COILED path

**Trigger**: OKLO 5/04 forming a visible flag with no detector hit. Replay surfaced two structural gaps: (a) universe gate excluded post-runup names whose composite RS is dragged down by pre-runup downtrend; (b) contraction math can't fire on short bases (early-vs-recent window overlap).

**Evidence**: OKLO 5/04 replay (`scripts/backfill_flag_xndu.py`); existing path catches XNDU 4/29-30 baseline.

**Anticipated effect**: (a) `get_flag_universe` adds OR-clause `rs_1m_pct ≥ 80 OR (last_close / trailing10_min - 1) ≥ 0.25`; (b) new `_compute_fresh_tightening` predicate creates alternative COILED path on `base_age ≥ 4 AND max(2bar TR%) ≤ 0.6 × ATR14% AND max(2bar vol) ≤ ADV20`.

**Reversion-flag**: NEW (both additions).

**Status**: shipped + validated (XNDU progression unchanged; OKLO 5/04 promotes to TIGHTENING).

### 2026-05-05 (session 5b) — Fresh-tightening dry-volume gate hybrid

**Trigger**: ADV20 climax-inflated for post-parabolic names — OKLO 5/04 hit 14.65M vs ADV20 15M = 0.98 (barely passing). The fresh-tightening predicate's volume gate against ADV20 alone was too lenient.

**Evidence**: OKLO 5/04 ratio 0.98 vs ADV20; 1.93× vs base recent. Same SSoT shape as `breakout_vol_ratio` denominator at flag_detector.py:899 (current line — was :369 at ship).

**Anticipated effect**: switched to hybrid ceiling `max(recent_5d_avg_vol, 0.5 × ADV20)`. Anchors on contraction floor; 0.5×ADV20 fallback prevents one sub-average bar from over-tightening the gate.

**Reversion-flag**: REFINEMENT of 2026-05-04 fresh-tightening ship.

**Status**: shipped + verified ($188 telemetry).

### 2026-05-01 — Initial Stage 1 ship (5-stage state machine, hysteresis, 17:25 ET cron)

**Trigger**: Plan in `~/.claude/plans/shiny-mapping-locket.md`. User-stated need: post-runup VCP / Qullamaggie tightening flags.

**Evidence**: Replay-driven calibration on XNDU 4/16-5/01 progression (WATCH → TIGHTENING → COILED → TRIGGERED → INVALIDATED).

**Status**: shipped (CLAUDE.md 2026-05-01 session 2).

---

Pre-2026-05-01 history is in CLAUDE.md / `CHANGELOG.md`. Backfill incrementally as touched.
