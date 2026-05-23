# ADR 0005 — Intraday flag-break detector

**Date**: 2026-05-23
**Status**: Phase 1 shipped (telemetry-only shadow) 2026-05-23. Phase 2 (operator-confirm entry) gated on N≥10 settled breaks.
**Authors**: Apollo Assistant (with user direction 2026-05-23)
**Supersedes**: none
**Sequencing**: Step 1 — Commit 1 (schema + scan + scheduler), Commit 2 (operator surface + monitoring + this ADR). Phase 2 = operator-confirm entry. Phase 3 = auto-entry on highest-conviction subset.

## 1. Context

The continuation-flag detector (`mi_flag_candidates`, shipped shadow 2026-05-04) runs end-of-day at 5:25 PM ET. It classifies each ticker into one of five stages — WATCH / TIGHTENING / COILED / TRIGGERED / INVALIDATED — based on the close vs `base_high`. This is the IDENTIFICATION layer: it tells us *which* stocks have established bases.

**The structural problem** (surfaced 2026-05-23 PM via user pushback on #92 graduation review): TRIGGERED-as-classified-at-5:25-PM is a *post-hoc* state, not an actionable trigger. By the time the scan stamps TRIGGERED on a ticker, the actual range-break occurred hours earlier intraday; the move has played out; sellers-into-strength have started fading the breakout.

Evidence (#92 backward check, realistic D+1 open entry):
- TRIGGERED N=5: avg 10d return -2.66%, WR 0%
- TRIGGERED tickers fade -2.03% on average from breakout-day close to next-day open
- TIGHTENING (pre-breakout state): N=104 +1.73% avg 10d / 28.8% WR / 21.2% big-winners

The TIGHTENING bright-spot is the move "leaking out" while we wait for EOD classification. Methodology-correct breakout entry per Qullamaggie/Minervini is the *moment* of range-break, not the close confirmation.

**This ADR adds the EXECUTION layer**: a real-time intraday scanner that detects the moment of break with volume confirmation. The EOD scan stays in place as the watchlist/IDENTIFICATION layer; the intraday detector adds the actionable trigger.

## 2. Outcome state (Phase 1 — telemetry only, shipped 2026-05-23)

- `_flag_break_scan_job` runs every 5 min, 9:35 AM–3:55 PM ET, Mon-Fri
- Reads MAX(scan_date) WHERE < CURRENT_DATE from `mi_flag_candidates`; filters to TIGHTENING/COILED/TRIGGERED
- Calls `get_snapshot_all()` (one Polygon batch call)
- Per-ticker break detection: `current_price > base_high` AND volume gates pass
- Writes to `mi_flag_breaks` table + emits `intraday_flag_break` audit + consolidated Telegram alert
- **No entry execution.** Telemetry-only.
- `/flagbreaks` Telegram command surfaces today's + recent breaks
- Post-EOD reconciliation flips `parent_invalidated_eod=TRUE` for any same-day break whose parent ticker is now classified INVALIDATED — excludes structurally-failed breakouts from forward-return analysis
- Monthly auto-refresh via `scripts/_b94_intraday_flag_break_evidence.py` in quarterly_review.py sweep — graduation decision at N≥10 settled

## 3. Detection logic

**Scope (load-bearing — captured 2026-05-23 user direction):** this detector handles ONE entry mechanic — the breakout trigger. A tight-range consolidation admits at least 5 distinct entry techniques per `memory/user_tight_range_entry_techniques.md`:

| # | Entry technique | This detector? |
|---|---|---|
| 1 | **Breakout** (price tags `base_high` with volume) | **YES — this detector** |
| 2 | Support-test bottom (price tests `base_low` and holds) | No — future detector class |
| 3 | MA pullback (retrace to MA10/20/50 on light volume) | No — future detector class |
| 4 | Low-volume rest (mid-range drift, institutional pause) | No — future detector class |
| 5 | U&R — Undercut & Rally (quick undercut of `base_low` or key MA, then rally back above) | No — future detector class; Stamatoudis "shake the tree" pattern |

These are distinct signal mechanics on the SAME stock — Stocks-in-Play (ADR 0004) surfaces the stock once; multiple entry-technique detectors can fire independently. This ADR scopes to #1; the other 4 are filed for future detector work and explicitly reserved as source_detector enum slots in ADR 0004 §4.

### Volume-pace projection (primary gate)

```
projected_full_day = today_volume × (390 / minutes_since_open)
require: projected_full_day ≥ adv_20
```

Matches the 9M anticipation pattern. At 11:00 AM (90 min since open) a stock with `today_volume = adv_20 / 4` projects to `adv_20 * 1.083` — passes. The same volume at 3:30 PM (360 min since open) projects to `adv_20 * 0.271` — fails. The gate fires when the day's pace meets ADV, regardless of clock time.

### Opening-30min block-trade guard (secondary gate, Gemini contract)

```
if minutes_since_open < 30:
    require: today_volume ≥ 0.15 × adv_20  (raw absolute floor)
```

Prevents the edge case where a single 150,000-share institutional block trade at 9:31 AM gets multiplied by (390/5) = 78× into a fake 11.7M projected day-volume on a flatlined stock. Both gates must pass for early-morning fires; after 10:00 AM, only the projection gate applies.

### Price gate

```
require: current_price > base_high
```

Trivial but load-bearing. `base_high` is captured at EOD per the existing flag detector's `compute_flag_metrics`. The intraday detector reads yesterday's value; doesn't recompute.

### Dedup

`UNIQUE (ticker, break_date)` constraint on `mi_flag_breaks`. First break of the day wins; subsequent breaks of the same ticker on the same trading day are no-ops at the INSERT layer (via `ON CONFLICT DO NOTHING`).

## 4. Schema

`mi_flag_breaks` (21 columns):

- Identity: `id`, `ticker`, `break_date`, `break_time`
- Timing: `minutes_since_open` (0 at 9:30 ET, 390 at 16:00 ET)
- Parent state (snapshot of yesterday's flag classification): `parent_stage`, `parent_scan_date`, `base_high`, `base_low`, `base_age`
- Break event: `break_price`, `pct_above_base_high`
- Volume context: `today_volume`, `adv_20`, `volume_pct_of_adv`, `projected_full_day_volume`
- Cohort decoration (read-side display only): `in_sugar_baby_cohort`, `cohort_count_180d`
- Post-EOD reconciliation: `parent_invalidated_eod`, `invalidated_at`
- Audit: `created_at`

UNIQUE constraint on `(ticker, break_date)`. Indexes on `break_date DESC` and `(ticker, break_date DESC)`.

365-day retention via `purge_old_data()`.

## 5. Post-EOD reconciliation (Gemini contract)

After `run_flag_scan` commits its 5:25 PM EOD classification:

```sql
UPDATE mi_flag_breaks
   SET parent_invalidated_eod = TRUE,
       invalidated_at = NOW()
 WHERE break_date = CURRENT_DATE
   AND ticker IN (
       SELECT ticker FROM mi_flag_candidates
        WHERE scan_date = CURRENT_DATE
          AND stage = 'INVALIDATED'
   );
```

A stock that broke intraday but is reclassified INVALIDATED by the same evening's flag scan (e.g. it broke then immediately closed back under base_high — failed structurally) gets excluded from forward-return analysis. The backward-check evidence script (`_b94_intraday_flag_break_evidence.py`) filters `WHERE parent_invalidated_eod = FALSE`.

## 6. Architectural choices (decided)

| Choice | Decision | Rationale |
|---|---|---|
| Scan placement | Separate `_flag_break_scan_job` (NOT piggyback in 9M scan) | Single responsibility; 2 batch API calls per 5min is acceptable on Polygon Starter |
| Cron expression | `hour="9-15" minute="*/5"` with in-function 9:35–15:55 ET gate | Multi-value hour + multi-value minute is product-set bug; in-function gate matches 9M pattern |
| Universe scope | Yesterday's TIGHTENING/COILED/TRIGGERED only (~250 tickers) | Small set, cheap per-tick check; no need to walk full universe |
| Snapshot source | `collector.get_snapshot_all()` (batch) | Same pattern as 9M + EP scans; well-tested, free |
| Storage | New `mi_flag_breaks` table | Cleaner than extending mi_flag_candidates; event-table semantics with UNIQUE dedup |
| Cohort decoration | Read-side display only (NOT detector coupling) | Per user choice 2026-05-23 — independent surfaces. 🍬 prefix is informational; detector doesn't filter on cohort membership |
| Phase 1 scope | Telemetry-only (no entry execution) | Same discipline as parabolic / fishhook / wick / sugar-baby-convergence shipped detectors |
| automation_class | `informational` (not entry-class) | Per ADR 0004 §2 axis 3 — graduation to operator_only requires N≥10 settled + Phase 2 entry mechanism design |
| Forward-return entry proxy | Break-day OPEN (not break_price) | Approximation for analysis; Phase 2 will use minute-bar simulation for actionable validation |
| Time of first scan | 9:35 AM ET (5 min after open) | Lets opening range settle; opening-30min raw-volume floor still applies for the first 25 min of valid scans |
| Time of last scan | 3:55 PM ET (5 min before close) | Avoids closing-auction noise |

## 7. Out of scope (deferred to later phases)

### Phase 2 — operator-confirm entry (gated on N≥10 settled breaks)
- `/flagbreak ENTER TICKER` command — submits bracket order via `submit_trade_entry` with:
  - Entry: market or limit at current price
  - Stop: `base_low` (captured in `mi_flag_breaks`)
  - Sizing: per-strategy `position_size_multiplier` (start at 0.5, cap at 2 per #65 pattern)
- New `flag_break_intraday` source_detector value in `stocks_in_play_sources.py` (created when ADR 0004 Phase 1 ships)
- Telegram alert escalation when convergence shape fires (cohort × intraday-break)

### Phase 3 — auto-entry on highest-conviction subset (gated on N≥30 settled positive)
- Auto-bracket-entry for breaks meeting tightened criteria (e.g. ≥2x ADV projected, ≥3% above base_high, in cohort)
- `automation_class = apollo_eligible` migration via SQL UPDATE
- Drawdown breaker integration

### Other entry-technique detectors (sibling classes, filed for future)
- **Support-test detector** — fires when price tests `base_low` intraday and holds (close > test_low + minimum bounce). Tightest stop placement; counter-trend signal mechanic
- **MA-pullback detector** — fires when price pulls back to MA10/MA20/MA50 inside the range on light volume. Classic VCP entry; requires MA-distance + volume-contraction logic
- **Low-volume rest detector** — fires when mid-range drift on contracting volume (`vol_contraction_ratio` already in COILED stage). Sniper entry; hardest to automate; may stay operator-only longer
- **U&R (Undercut & Rally) detector** — fires when ticker undercuts `base_low` or key MA AND rallies back above within N bars. Stamatoudis pattern. Counter-intuitive risk profile (tightest stop, biggest cushion). Most-complex shape; likely last to detect automatically

Each is a distinct detector class with different signal mechanics; per `feedback_sample_size_discipline.md`, each ships shadow-first with N≥10 settled before paper-phase consideration.

### Other deferred concerns
- Stop placement design (base_low vs ATR-based) — Phase 2
- Cancellation logic if break fades intraday — Phase 2 (depends on entry mechanism)
- Multi-day re-break tracking — defer until data shows the pattern matters
- Backward-replay against historical 1-min bars — requires minute-bar storage we don't have; forward-data accumulates
- **TIGHTENING watchlist surface (#93)** — refined per user 2026-05-23 to "TIGHTENING watchlist + entry-technique annotation": each watched ticker tagged with which of the 5 entry techniques are currently valid (operator picks the entry style). Rides alongside #94 but doesn't block first phase.

## 8. Critical files

| File | Change | Commit |
|---|---|---|
| `agents/market_intelligence/db.py` | `mi_flag_breaks` table + 365d retention | 1 |
| `agents/market_intelligence/flag_detector.py` | `run_intraday_flag_break_scan()` + `reconcile_flag_breaks_post_eod()` + post-EOD reconciliation wired into `run_flag_scan` | 1 |
| `agents/market_intelligence/scheduler.py` | `_flag_break_scan_job` + cron registration | 1 |
| `agents/market_intelligence/agent.py` | `_handle_flag_breaks_query` + `/flagbreaks` + `/flagbreak` dispatch | 2 |
| `scripts/_b94_intraday_flag_break_evidence.py` | Monthly auto-revalidation script | 2 |
| `agents/market_intelligence/quarterly_review.py` | Sweep entry | 2 |
| `data_gated_reviews.yaml` | `intraday_flag_break_signal_n10` review entry | 2 |
| `CLAUDE.md` | Daily schedule table row | 2 |
| `docs/decisions/0005-intraday-flag-break-detector.md` | This document | 2 |

## 9. Reuse from existing code

- `flag_detector.compute_flag_metrics` — stays as-is; intraday detector reads its EOD output, doesn't replace
- `collector.get_snapshot_all()` — batch Polygon call, same as 9M + EP scans
- `db.log_audit_event` — module-level imported per preflight [5d/5]
- `audit_wrap` from `core.job_audit` — scheduler error handling
- `send_telegram_message` from `briefing.py` — module-level imported in scheduler
- `db.get_sugar_babies_cohort_latest` would be the cohort lookup; instead we query `mi_sugar_babies_cohort` directly in scan to avoid extra round-trip
- `db.get_pool` — async DB pool accessor

## 10. Verification (Phase 1 ship)

Manual checks executed post-deploy 2026-05-23:

1. **Schema**: `\d mi_flag_breaks` confirmed 21 columns + indexes + UNIQUE
2. **Direct scan smoke**: `run_intraday_flag_break_scan(mocked_time)` returned 7 breaks against Friday's snapshot — proves logic works
3. **Top-quality break**: DELL TIGHTENING +13.30% above base_high with 246% ADV volume (operator-validated as A+ catch: right theme + momentum stock + catalyst alignment)
4. **Audit event format**: matches contract `{TICKER} stage={stage} pct_above={X.X}% vol_pct_adv={Y}%`
5. **Cleanup**: smoke residue deleted; database empty pending Tuesday 9:35 AM first real scan
6. **Preflight gates**: all 5 deploy gates pass

First real-world scan fires Tuesday 2026-05-27 9:35 AM ET (Memorial Day Monday closed).

## 11. Discipline notes

- **Shadow phase first** per `feedback_methodology_insights_need_periodic_revalidation.md` — every methodology insight needs auto-refresh; entry execution before signal validation is the bug class to prevent
- **Filter behavior decoupled from audit telemetry** — Telegram failure CANNOT block detection write. Wrap in try/except, fail-open. Same lesson as #84 + #89 ships
- **Audit event payload format is a contract** — every `intraday_flag_break` summary follows `{TICKER} stage={stage} pct_above={X.X}% vol_pct_adv={Y}%`. Format drift breaks future backtest queries
- **automation_class** (per ADR 0004 §2 axis 3) — `informational` for Phase 1; Phase 2 ship promotes to `operator_only`; later automation promotion is SQL UPDATE only
- **Trading-session vs calendar-day** (Gemini contract from ADR 0004) — `parent_scan_date` lookup uses `MAX(scan_date) WHERE < CURRENT_DATE`, NOT yesterday calendar-day. Handles Memorial Day Monday correctly
- **Sample-size discipline** — Phase 2 entry execution requires N≥10 settled breaks + advisor review + minute-bar entry simulation
- **Per-feedback `validate_metric_before_decision.md`** — forward-return analysis at Phase 2 review MUST use minute-bar entry simulation, not break-day-open approximation. Current monthly script's break-day OPEN is acceptable for Phase 1 telemetry but not for Phase 2 ship decision

## 12. Per-feedback `methodology_insights_need_periodic_revalidation`

The `_b94_intraday_flag_break_evidence.py` script wired into monthly `quarterly_review.py` sweep ensures this finding doesn't become a stale "we evaluated it" assumption. Decision gate auto-runs every month; operator sees Telegram digest of current N + signal strength.

## 13. Cross-references

- ADR 0004 (Stocks in Play unified watchlist) §4 — source_detector enum reserves `'flag_break_intraday'` slot
- ADR 0004 §7 Phase 4 — flag detector migration into mi_stocks_in_play awaits THIS validation
- `data_gated_reviews.yaml::intraday_flag_break_signal_n10` — N≥10 graduation decision matrix
- `data_gated_reviews.yaml::flag_detector_graduation_evidence_n30` — superseded by THIS detector when entry path ships (Phase 2)
- `data_gated_reviews.yaml::sugar_baby_convergence_backtest_first_eval` — sibling alert class; independent surfaces per user choice 2026-05-23
- `feedback_methodology_insights_need_periodic_revalidation.md` — drives monthly auto-refresh
- `user_pradeep_9m_universe_methodology.md` — Pradeep's "entry = tightness→expansion" framing literally describes this detector
- `feedback_validate_metric_before_decision.md` — Phase 2 must use minute-bar entry simulation
- CLAUDE.md daily schedule table — `9:35 AM–3:55 PM (every 5 min, mon-fri)` row
- `_b94_intraday_flag_break_evidence.py` — monthly sweep script
- `_b78_decliner_band_bounce_signal.py` — sibling discipline script (Pradeep rally-band investigation)
- `_b92_flag_detector_graduation_evidence.py` — predecessor (EOD-classification analysis; superseded by intraday entry shape)
