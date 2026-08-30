# #605 — The EP decision vector: enumeration, capture fix, and the anti-rot guard

**Date:** 2026-08-29 · **Task:** #605 (log the full decision vector for every candidate at every
stage, not just survivors) · **Scope:** CAPTURE ONLY — no admission criterion, threshold, weight,
sizing rule, target or safeguard moved. · **Registry (code SoT):**
`agents/market_intelligence/ep_decision_vector.py` · **Guard:**
`tests/test_605_decision_vector_capture.py`.

Operator, 2026-08-29: *"we need to collect data properly so we don't keep running into issues
every time. every time you say we're missing this or that, we patch it and next time we're still
missing stuff, I don't want to see this again."* Measured symptom: of 19,752 `mi_ep_scan_log`
rows in 30 days, only 12% carried `ep_score` or `catalyst_quality`; the 08-29 backtest could not
sign EP's expectancy because the catalyst grade was unreconstructible for 88% of candidates.

---

## §1 · ENUMERATION — every input the admission stack + score consume

"Pre" = persisted per-candidate BEFORE this change. Stage order is `run_ep_scan`'s actual order.

### 1a. Admission stack (`ep_detector.run_ep_scan`)

| # | Gate (stage tag) | Inputs consumed | Pre-#605: persisted? for whom? where? | After #605 |
|---|---|---|---|---|
| 1 | Symbol hygiene (`MAX_TICKER_LEN`, `_SKIP_TICKERS`, "." ) | ticker string | No row, by design — static universe noise | Unchanged (deliberate — §6) |
| 2 | Security type (CS/ADRC only; unclassified fail-safe) | `mi_security_types` row | Aggregate count in container log only | Unchanged (deliberate — the input table itself is persisted; §6) |
| 3 | `MIN_PREV_CLOSE` $5 (`universe_floor`) | prev_close, gap | #570 rows only (would-be candidates): prev_close as column, volume only inside the reason STRING | + `prev_day_volume`, `current_price`, `reject_stage` columns |
| 4 | `MIN_PREV_DAY_VOLUME` 50k (`universe_floor`) | prev D-1 volume | Compared value existed NOWHERE as data (reason string only) | Same row now carries it as a column; also on every candidate row via `_snap_candidate` |
| 5 | Price availability (`if not current_price`) | snapshot price fields | Silent drop | Unchanged (data availability, not policy — no gap measurable, nothing to counterfactual; §6) |
| 6 | **Gap ≥ acting Pass-1 floor** (`gap_floor`) | gap_pct, current_price, prev_close | **NO ROW below the floor — the censorship class.** June+July 2026 logged zero 9-10% rows because `MIN_GAP_PCT` was 10.0 then | + full-vector rows for the **[`EP_CAPTURE_GAP_FLOOR`=5.0, floor)** band, `filter:universe_below_gap_floor`, record-only |
| 7 | Pass-0 rt overlay / Pass-2 rt confirm + floor re-check (`gap_floor`) | rt price, gap_pct_rt/delayed, prev_close_alpaca, print age, Q1-Q4 | rt columns on SURVIVING rows (#490 G1); dropped superset names: audit events only, no scan row | + a full-vector row for every Pass-2 floor drop (rt readings included) |
| 8 | Shortlist order + `SHORTLIST_SIZE` cap (`shortlist_cap`) | D-1 ADV$ (adv × prev_close), flat gap, theme membership | `rank_by_gap` column; prescore + both orders per tick in `mi_ep_shortlist_shadow`; outside-cap rows: rank inside reason string | + `rank_by_prescore`, `in_active_theme` columns on EVERY row |
| 9 | RVOL@T gate, pm/session anchor (`rvol_gate`) | rvol_at_time, baseline_n, baseline_mean, today cumulative vol, clock | `pm_rvol` column (30% of rows); baseline_n / mean / cum vol inside reason string only | + `pm_rvol_baseline_n`, `today_volume` (mean derivable: cum/rvol); anchor derivable from `minutes_since_open` |
| 10 | Cooldown 60d + earnings bypass (`cooldown`) | days since prior alert, gap, is_earnings_day | Outcome only; days-since only inside #170 shadow audit events for the resetup subset | + `days_since_prior_alert` on EVERY row (from the gate's own map) |
| 11 | Already-scored-today (`duplicate`) | same-day `mi_ep_alerts` row | Reason string | + stage tag (input is the alert row itself) |
| 12 | Extension ≥ `MAX_EXTENSION_PCT` vs MIN(close 5d) (`extension`) | prev_close, low 5d close | Killed rows: pct inside reason string; **survivors: nothing** | + `extension_pct` on EVERY row (derived in `_scan_row` from the gate's own map) |
| 13 | Quality filters — 30d median ADV$ ≥ $1M, ATR14 ≤ 15%, mcap ≥ $500M (`quality_filter`) | adv_dollar, atr_pct, market_cap | Only the FAILING check's value, inside the reason string; survivors: nothing | + `quality_adv_dollar`, `atr_pct`, `market_cap` columns via `check_filters(metrics=...)` sink — zero extra queries; a killed row carries what was computed up to its kill point |
| 14 | Catalyst grade path (LLM → pplx → hedge → lattice → boost/revenue-gate/prose downgrades) | raw grade, acting grade, verdict, corpus, q_rev_yoy… | `mi_catalyst_tier_shadow` (every GRADED candidate incl. filter-kills, since 08-23) + `mi_ep_catalyst_metrics` + deduped audit events; **scan row catalyst NULL on every post-grade kill** | + `catalyst_quality` (acting) + `llm_catalyst_quality` (raw) on post-grade-kill and scored rows — the 88%-hole fix |
| 15 | Post-grade filters — M&A / routine<12% / pm-shares 25k (`post_grade_filter`) | acting grade, gap, today_volume, pm_rvol | Reason string; today_volume nowhere | + `today_volume` + both grade columns |
| 16 | Score bar (`score_bar`) | ep_score, acting bar, side | Bar inside reason string; both sides per graded candidate in `mi_ep_score_shadow` | + `ep_bar`, `score_side` columns (self-contained row) |
| 17 | Earnings-day MOD→HIGH override | is_earnings_day, tier, score | Audit events (deduped per ticker/day) — complete | Unchanged |
| 18 | Judge (post-loop) | alert-row fields, corpus | `mi_ep_alerts` judge columns — alerts only, its population | Unchanged |

### 1b. Score inputs (`_score_ep` / `ep_rubric.SCORE_WEIGHTS`)

| Component / param | Input | Pre-#605: persisted? | After #605 |
|---|---|---|---|
| gap | gap_pct | ✓ column, all rows | ✓ |
| liquidity | adv × prev_close (fallback: projected_vol_multiple / rel_volume) | ✓ columns (adv 45%, proj 5%) | ✓ (coverage rises with row completeness) |
| catalyst | acting catalyst_quality | 12% of rows (scored only) | every graded row + raw grade |
| float | profile.floatShares | ✗ nowhere in scan_log | + `float_shares` |
| vol_conviction | volume percentile vs own ADV history | ✗ (alert rows only) | + `vol_percentile` |
| theme_bonus | in Accelerating/Mainstream theme | ✗ in scan_log (shortlist shadow only) | + `in_active_theme` |
| conviction_floor | gap + catalyst | ✓/12% | ✓ per above |
| regime multiplier | regime label (Bull=1.2) × confidence_multiplier (pinned 1.0, #233) | derivable: `mi_market_regime` per date + alert column | registered as derived |
| output_scale / weights table | which side acted | `mi_ep_score_shadow.live_side` per graded | + `score_side` on every row |
| (whole vector) | component breakdown | **computed then DISCARDED** for every sub-bar candidate | + `score_breakdown` JSONB |
| Shortlist pre-score | adv_dollar, gap, theme | raw inputs per tick in `mi_ep_shortlist_shadow` | + `rank_by_prescore` on the scan row |

---

## §2 · The capture fix (Part 2) — extend `mi_ep_scan_log`, no new table

The enumeration says extending is RIGHT: every hole is a per-candidate-per-stage value, which is
exactly this table's grain; the graded-path extras (both-sides scores, tier verdicts, shortlist
orders) already live in purpose-built side tables that are complete for their populations. 19
nullable columns added (see `db.py` CREATE + mirrored ALTERs — `CREATE TABLE IF NOT EXISTS` is a
no-op on the existing prod table; only the ALTERs reach production).

Mechanics, all capture-only:
- `_scan_row` now emits the full vector; values ride the candidate dict the moment each stage
  computes them (`c["vol_percentile"]`, `c["llm_catalyst_quality"]`, `check_filters(metrics=)`…).
  NULL now means "genuinely not computed at that stage", never "computed then discarded".
- **Floor censorship ended two ways:** the scan loop records the fixed band
  [`EP_CAPTURE_GAP_FLOOR`=5.0, acting floor) via `_snap_candidate` (pure dict build, 0.18 ms per
  300 names, measured), and Pass-2's floor re-check records every name it silently discarded.
  Reason `filter:universe_below_gap_floor` — the `filter:universe_` prefix deliberately routes it
  OUT of the briefing's "gap candidates scanned" count and near-miss lines (existing exclusion),
  into its own `below_gap_floor` category (missed_outcomes, both Python and SQL categorizers,
  structural/hidden-by-default) and `/scanned` funnel stage. The nightly
  `mi_ep_scan_outcomes` refresher picks these rows up automatically → forward returns accrue for
  the band, which is precisely the "did the floor throw away winners" join.
- Write path unchanged in shape: same batched `executemany`, same never-raises contract, end-of-
  scan flush still fire-and-forget. The one awaited write (the existing #570 early flush) now
  carries the below-floor rows in the SAME single round trip.

**Cost.** Rows: ~20k/30d today → est. 60-90k/30d (the 5-9% band is ~2-4× the ≥9% candidate count,
logged per tick like everything else), at ~250-450 B/row wider ≈ **25-45 MB per 30 days
table+index (< ~0.5 GB/yr)** — not material. Latency: **zero new round trips and no new blocking
call** on the graded path; the early flush grows by ≤ a few hundred rows in one batch (single-
digit ms); the row builds are pure dict work (measured 0.18 ms / 300 candidates).

## §3 · Minute bars: population-driven (Part 3)

`broker/order_manager.py::persist_alert_day_paths` (16:22 ET EOD job, execution service) now
UNIONs a fourth population arm: every `mi_ep_scan_log` ticker whose **day-MAX** gap ≥
`_PATH_CAPTURE_MIN_GAP` (8.0 = the 9% admission floor minus one point of counterfactual
headroom; deliberately NOT the 5.0 row floor — bars cost ~50× a row and the 5-8% band has no
open admission question). Day-MAX so an intraday fade can't drop a name that WAS a candidate.
Cost: ~45-65 names/day → **~+10 MB/day ≈ +2.5-3 GB/yr** at the measured 571 B/row (vs ~1-1.3
GB/yr before), inside the existing 5y retention pricing. The 08-29 backfill's 97% coverage now
stays closed from the next session instead of re-rotting.

## §4 · The anti-rot guard (Part 4)

`ep_decision_vector.py` (registry) + `tests/test_605_decision_vector_capture.py` (15 tests):
exact-set equality between `_score_ep` params / `SCORE_WEIGHTS(_LEGACY)` components /
`shortlist_prescore` params and the registry; every registered column wired end-to-end (row
builder → INSERT → CREATE, with ALTER↔CREATE parity already pinned by #258's test); every funnel
`stage=` literal registered and vice versa; tripwire counts on `continue` statements and
`_log_filtered` calls inside `run_ep_scan` (a new gate is textually one of those two); capture
floors pinned ≤ every acting admission floor (the June/July-hole guard, both rows and bars);
the bar population pinned to read `mi_ep_scan_log` by day-MAX gap.

**Mutation-tested at ship time:** (a) a fake `_score_ep` parameter → red
(`test_score_ep_parameters_all_registered`); (b) a fake silent `continue` gate in the graded
loop → red (`test_no_unregistered_continue_in_run_ep_scan`). Both reverted; suite green
(6550 passed / 7 skipped; baseline was 6534+15 new+1 new vocab case).

## §5 · What could make this insufficient (stated now, not discovered later)

- The tripwires are TRIPWIRES, not proofs — a gate hidden inside a helper called from the loop
  (no new `continue`, no `_log_filtered`) would not move the counts. The registry review at the
  forced touch is the human checkpoint, same honesty note as `gate_provenance_registry.py`.
- A "derived" registry entry is a claim; make it true when adding one.
- Catalyst inputs still exist only for GRADED candidates — that is the `SHORTLIST_SIZE` LLM
  budget (a spend policy), not a capture hole; the shortlist's own inputs are captured, so the
  cap itself is fully re-askable.

## §6 · Deliberately NOT done

- No rows below 5% gap (whole-market noise per tick; 5.0 = the hybrid's own Pass-1 superset
  floor, test-pinned ≤ every admission floor so it moves consciously with any floor cut).
- Symbol-hygiene / security-type / no-price skips stay row-less — their inputs are constants or
  the persisted `mi_security_types` table; thousands of static rows per tick buy no counterfactual.
- Premarket minute bars still not stored (capture window stays 09:30-16:00, pinned by the #306
  comparability contract) — replaying the pm-RVOL/pm-shares gates from bars remains impossible;
  widening the window is a separate ~2× bar-storage decision, filed here by name rather than
  discovered later.
- No `docs/setups/magna53_ep.md` change-log entry — no detection criterion, threshold, or weight
  moved (capture only); this doc + the registry are the record. Flag if the operator wants a
  cross-reference line there anyway.
