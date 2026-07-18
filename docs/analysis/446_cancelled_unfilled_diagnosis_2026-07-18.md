# #446 — cancelled_unfilled HIGH diagnosis (read-only) — 2026-07-18

**Question:** the #290 backtest (`docs/analysis/dead_zone_reeval_2026-07-09.md`) found
`cancelled_unfilled` HIGHs = 36.7% forward winner rate (n=30, 11 ≥10% winners) over the
post-3/20 cohort — "NOT sparse" was the surprise (expected sparse post-SIP-flip). Is the
stop-buy trigger / 9:45 ORB cutoff / 10:00 ET unfilled-cancel job dropping fillable winners?

**Method:** code-path read of the entry → cancel → classify chain, no live DB access from
this session (no code changed, no queries run against prod). Everything below is either a
direct code citation or an EXACT SQL for the orchestrator to run against prod Postgres.

---

## 1. What "cancelled_unfilled" actually is — a metric-validity problem first

The #290 script (`scripts/probes/backfill_dead_zone_v2.py::classify_high_mechanism`) buckets
a HIGH as `cancelled_unfilled` on one condition: `mi_live_trades.status == 'cancelled'` (and
detected before 9:45 — see §3). The 36.7% is a **forward-return stock label**
(`max(close T+1..T+5) ≥ +10% of close at alert`), computed the same way as every other
bucket in that script — it does **not** check whether the order's stop-buy trigger was ever
crossed, whether a fill was actually reachable, or which cancel path fired. "The stock ran
10%" is not "we would have filled at a survivable entry and held through the stop." Part 2
of the same dead_zone doc already proved this exact gap on the adjacent `late_detection`
cohort: the 11:00-cutoff window won on precision (23.8% > control) but was **R-negative
across every stop tested** (−0.16R to −0.35R). The same caution applies here by construction
— the 36.7% is not recoverable edge until it's decomposed by mechanism and run through a
realized-R sim, and that decomposition + sim **already exists** (§2).

`status='cancelled'` on a `mi_live_trades` row can be written by **three different code
paths**, not one:

1. **10:00 ET ORB-window cleanup** (`_orb_window_cleanup_job` → `cancel_unfilled_entries(reason="ORB window unfilled")`, `scheduler.py`) — the mechanism the operator is asking about. Fires `classify_orb_cancellation` (gap-through telemetry) + `record_shadow_for_cancellation` (counterfactual fill sim). `skip_reason = 'ORB window unfilled'`.
2. **4:05 PM EOD cleanup** (`_eod_cleanup_job` → `cancel_unfilled_entries()` default `reason="EOD unfilled"`) — only reachable if an order survived past 10:00 still `order_placed` (e.g. the 10:00 cancel call failed broker-side that day). Does **not** run the classifier or the shadow sim (`order_manager.py` comment: "Excluding 4:05 PM EOD cancellations keeps the dataset homogeneous"). `skip_reason = 'EOD unfilled'`.
3. **Broker-side WS cancel/reject** (`trade_stream.py::_handle_cancel_or_reject`) — an exchange-level event (e.g. a LULD halt reject, the AEHR 2026-07-15 class per the `#475` comment in that file) landing on an entry still in `order_placed`/`pending_confirmation` **before** the 10:00 job gets to it. `skip_reason = event_norm` (the raw Alpaca event string, e.g. `'rejected'`/`'canceled'`) — not one of the two reason strings above, and also **not** classified by the gap-through telemetry.

These are mechanistically distinct: (1) is "our own 10:00 cutoff killed a resting order,"
(2)/(3) are broker/ops noise unrelated to the ORB-cutoff design question. The #290 script
blends all three under one label. **First SQL below separates them** — this alone may
resolve most of the "why 36.7%" question before any fill-classification data is even read.

## 2. The classification + counterfactual-fill data already exists — don't recompute it

Two systems already answer "would this specific cancelled order have filled" per-trade,
built for exactly this question:

- **Gap-through classifier** (`agents/market_intelligence/broker/gap_through_telemetry.py`,
  task #22). Fires from path (1) only. Classifies each cancellation as `clean_miss` (trigger
  never crossed — correctly stayed out), `would_have_filled` (trigger crossed + a later bar
  low ≤ the stop-limit's limit price — a fillable order the system failed to fill),
  `gap_through` (trigger crossed but price ran past the limit before any reachable print), or
  `data_unavailable`. Writes one `orb_cancellation_classification` audit event per trade_id
  at ~10:00 (on **incomplete**, still-lagging Polygon bars — this intraday pass has a known
  false-`clean_miss` bug, see AVAV 2026-05-28 below). A **second, authoritative pass**
  (`reclassify_orb_cancellations_eod`, #183) re-runs after close on complete bars over the
  canonical 9:31–10:00 window and writes `orb_cancellation_reclassified`, explicitly flagging
  any flip from the intraday label. **Prefer `orb_cancellation_reclassified` over
  `orb_cancellation_classification` when both exist** — it's the corrected pass.
- **ORB-extension shadow** (`agents/market_intelligence/broker/orb_extension_shadow.py`,
  `mi_orb_extension_shadow` table). Also fires from path (1) only. For each cancelled trade,
  simulates the counterfactual fill + full exit ladder at 6 cutoffs (10:00/11:00/12:00/13:00/
  14:00/16:00), using the *same* `stop_limit_buy_price()` fill semantics as the live broker.
  Persists `would_fill, fill_at, fill_price, final_status, total_pnl, hold_days` per
  (trade_id, cutoff_minute) — i.e. **realized-R, not a stock-return label**, for the exact
  30-row cohort (subject to the shipped-date caveat in §5).

Both are gated on `event_type == 'orb_unfilled_cancelled'` (path 1 only) — rows cancelled via
paths (2)/(3) have neither. That absence is itself diagnostic (§4 SQL surfaces it).

## 3. The 9:45 cutoff and the fade guard are ruled out for this bucket, by construction

- **9:45 ORB cutoff**: `classify_high_mechanism` checks `et_min >= ORB_CUTOFF_MIN` **before**
  checking `status`. Any HIGH detected at/after 9:45 is bucketed `late_detection`, never
  `cancelled_unfilled`, regardless of what its (non-existent) trade row would say. So by
  construction, all 30 `cancelled_unfilled` rows were detected **before** 9:45, were
  submitted, and got a resting stop-limit order in the book. The 9:45 cutoff cannot be the
  mechanism dropping these 30 — it's a separate cohort (`late_detection`, already analyzed in
  the same dead_zone doc, and shown R-negative at the only precision-competitive cutoff).
- **Fade guard**: `check_fade_guard(..., ratio=...)` is called with `ratio=None` for MAGNA53
  HIGH (`entry_pipeline.py` docstring: "MAGNA53 EP HIGH passes None because Sonnet+Perplexity
  validation + ATR stop width + 10:00 ET cleanup already cover the dead-cat-fill case") — the
  check returns `(True, None)` unconditionally and never blocks a MAGNA53 submission. Ruled
  out for this cohort (9M Day 2 uses `ratio=0.25` but is excluded from the #290 query by the
  `signal_type='magna53'` filter).

That leaves exactly two live candidates for "what drops a fillable winner": **(a)** the
10:00 ET job correctly firing but killing an order that *would have* filled given more time
(a real cutoff-timing question) — largely a re-statement of the already-open
`dead_zone_reeval` extension question, or **(b)** the stop-buy trigger's tight fill buffer
(`stop_limit_buy_price()` = `max(stop×1.005, stop+$0.02)`) letting a fast mover gap through
before the limit is reachable — a design question, not a cutoff question.

## 4. account_mode is load-bearing — this is likely the biggest single confound

`mi_live_trades.account_mode` (`'paper'` default, `'live'` for promoted strategies) matters
because the **two accounts do not see the same market data for order triggering**. Per the
already-resolved `alpaca_stop_trigger_reliability` gated review (`data_gated_reviews.yaml`,
AVAV 2026-05-28 + LYG 2026-06-12 evidence): Apollo's own market-data feed is SIP
(`ALPACA_DATA_FEED=sip`), but **the Alpaca PAPER account's internal fill simulator only sees
IEX prints** — a real cross on the consolidated tape (SIP) that never printed on IEX will
never trigger a paper stop-limit order, even though it would trigger and fill on the LIVE
account (real exchange routing). LYG (2026-06-12, 9M Day 2, trade #214) is the "cleanest
confirmation": SIP printed the trigger in-window, IEX never printed that minute at all, order
sat untouched 28 minutes, 10:00 cleanup cancelled it — a `would_have_filled`-on-live case that
looks identical to a paper "clean miss" unless you check the feed. This is **already filed as
#182** ("paper may under-fill entries vs. live — cohort representativeness"), not a new bug.

Implication for #446: if the 30-row cohort is mostly **paper** trades, a chunk of the
`would_have_filled` classifications are a **paper-simulation artifact** — the stock ran, the
order would genuinely have filled on the live account, and nothing about the live 9:45/10:00
design dropped it. Only a **live-account** `gap_through` or `would_have_filled` row represents
a real, actionable gap in the live entry mechanism (routes to `alpaca_stop_trigger_reliability`,
already scoped as gated — widen-limit or stop-market-with-chase-cap, CHANGE_PROCESS-gated,
not new work).

## 5. Coverage caveat

`mi_orb_extension_shadow` and the gap-through classifier both shipped ~early May 2026 (per
CHANGELOG "session 7 — ORB-extension shadow telemetry"); the #290 cohort runs back to
2026-03-20. Rows from before the shipped date have **no** classification/shadow data — bar
replay against archived Polygon minute bars would need to be run fresh for those (the SQL in
§6 surfaces exactly which trade_ids are missing so this gap is visible, not silently backfilled
with guesses). At n=30 total, split further by mechanism × account_mode, expect small cells —
directional, not a powered read.

## 6. Exact SQL for the orchestrator to run (prod Postgres, read-only)

```sql
-- Step 1: the 30-row cohort with account_mode + which cancel path fired
SELECT t.id AS trade_id, t.ticker, t.alert_date, t.account_mode,
       t.status, t.skip_reason, t.orb_high, t.entry_price, t.stop_price,
       t.entry_shares, t.proposed_at, t.created_at
  FROM mi_live_trades t
  LEFT JOIN mi_ep_alerts a ON a.ticker = t.ticker AND a.alert_date = t.alert_date
 WHERE t.status = 'cancelled'
   AND t.alert_date > '2026-03-20'
   AND COALESCE(t.signal_type, 'magna53') = 'magna53'
   AND a.score_tier = 'HIGH'
   AND (a.created_at AT TIME ZONE 'America/New_York')::time < '09:45:00'
 ORDER BY t.alert_date DESC;

-- Step 2: mechanism split by cancel path (skip_reason distinguishes the 3 code paths — §1)
--   'ORB window unfilled' = path 1 (the 10:00 job, the one under question)
--   'EOD unfilled'        = path 2 (survived past 10:00 uncancelled — ops anomaly)
--   anything else         = path 3 (broker-side WS cancel/reject, e.g. LULD)
SELECT account_mode, skip_reason, COUNT(*) 
  FROM mi_live_trades
 WHERE status = 'cancelled' AND alert_date > '2026-03-20'
   AND COALESCE(signal_type, 'magna53') = 'magna53'
 GROUP BY account_mode, skip_reason
 ORDER BY account_mode, COUNT(*) DESC;

-- Step 3: authoritative EOD classification (prefer over intraday) for the path-1 subset
SELECT (details::jsonb->>'trade_id')::int AS trade_id,
       details::jsonb->>'classification' AS classification,
       details::jsonb->>'prior_intraday' AS prior_intraday,
       (details::jsonb->>'flipped_from_clean_miss')::bool AS flipped_from_clean_miss,
       (details::jsonb->>'trigger_price')::float AS trigger_price,
       (details::jsonb->>'limit_price')::float AS limit_price
  FROM mi_audit_log
 WHERE event_type = 'orb_cancellation_reclassified'
   AND created_at > '2026-03-20'
 ORDER BY created_at DESC;

-- Step 3b: fallback — intraday classification for any trade_id NOT in step 3
-- (either predates EOD-reclassify shipping, or the EOD pass hasn't run / data_unavailable)
SELECT (details::jsonb->>'trade_id')::int AS trade_id,
       details::jsonb->>'classification' AS classification,
       (details::jsonb->>'max_high_in_window')::float AS max_high_in_window,
       (details::jsonb->>'min_trade_after_trigger')::float AS min_trade_after_trigger,
       details::jsonb->>'pm_rvol' AS pm_rvol
  FROM mi_audit_log
 WHERE event_type = 'orb_cancellation_classification'
   AND created_at > '2026-03-20'
 ORDER BY created_at DESC;

-- Step 4: realized-R counterfactual (the actual R answer, not a stock-return label) —
-- pull ALL cutoffs per trade_id to compare 10:00 (as-is) vs later cutoffs' would_fill/pnl
SELECT trade_id, ticker, alert_date, cutoff_minute, would_fill, fill_at, fill_price,
       final_status, total_pnl, hold_days
  FROM mi_orb_extension_shadow
 WHERE trade_id IN (/* trade_ids from Step 1, skip_reason = 'ORB window unfilled' only */)
 ORDER BY trade_id, cutoff_minute;

-- Step 5: join everything for the final per-trade table (run after pulling the above 4
-- result sets and matching trade_id in application code / a spreadsheet — a single query
-- across mi_live_trades + mi_audit_log(jsonb) + mi_orb_extension_shadow is doable but the
-- four-step version above is easier to sanity-check row-by-row before trusting a JOIN).
```

## 7. Recommendation — GO/NO-GO

**NO-GO — close #446 as a standalone thread; do not open new work.** Everything this
question could surface already has an owner:

- The 36.7% headline is a **stock-return-label artifact** blending ≥3 cancel mechanisms and
  a coarse forward-return proxy, not a demonstrated dropped-R number (§1) — mirrors exactly
  what Part 2 of the `dead_zone_reeval` doc already proved on the sibling `late_detection`
  cohort (precision parity, R-negative).
- The 9:45 cutoff and fade guard are cleanly ruled out by construction (§3).
- A `would_have_filled` paper-account row is very likely the already-filed **#182**
  (paper-IEX under-fill vs. live-SIP), not a new live-side gap.
- A `gap_through`/`would_have_filled` **live**-account row is the already-scoped, already-
  gated **`alpaca_stop_trigger_reliability`** review (CHANGE_PROCESS-gated fix: widen the
  stop-limit buffer or switch to stop-market-with-chase-cap) — not a new thread either.
- Coverage is thin (n=30, shrinking further once split by mechanism × account_mode) and
  partially missing for the oldest rows (§5) — not enough to power a design decision even if
  it were a new question.

**The one flip that would change this call**: if the orchestrator runs the §6 SQL and Step 3/4
show a **material count of LIVE-account `gap_through` or `would_have_filled` rows with a
survivable stop in the shadow sim** (i.e., `mi_orb_extension_shadow.total_pnl` positive at the
10:00 cutoff specifically, not just a later one), that count should be added as evidence to
the existing `alpaca_stop_trigger_reliability` gated review (still not a new thread — folds
into work already scoped) rather than spawning a #446-specific fix. Any live-side change from
that review remains CHANGE_PROCESS-gated with operator sign-off (THE LINE) regardless.

*Read-only diagnosis; no code changed, no live query run, no trade state touched.*
