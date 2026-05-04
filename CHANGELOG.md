# Apollo the Wise — Change Log

Compressed historical change log. **Live operational reference + recent prose entries (~2 weeks) live in `CLAUDE.md`.** Entries graduate here once they age out of the recent window.

Each entry is a one-liner: `topic — key change & lesson`. Full prose lives in git history at the listed commits — `git log --grep="<topic>"` or `git blame` for code-level context.

When consulted: investigating "why did we change X?", design reviews, retrospectives. Not loaded by default into agent context.

---

### 2026-04-28
- **session 4 — P22 Wick-Fill shadow tracker**: First strategy shipped through Strategy Maturity Framework. Negated shooting-star setup (`close_in_range_pct ∈ [0.50, 0.75)`) → Day 2+ break of `prior_high` is the short-trap fill. New `mi_wick_candidates` mirrors sugar-baby shape + adds `filled_wick BOOL` + dual fwd-return anchors (from-high conditional on fill, from-close unconditional baseline — gap = strategy edge). Reuses `_NINEM_CONTEXT_CTE` + `is_9m_directional` so WU 2026-04-24 fix stays enforced. Promotion model `telemetry_review` (n≥30, fill_rate≥0.50). Lesson: framework worked as designed — strategy #5 = config row + adapter + sweep call site.
- **session 3 — Strategy Maturity Framework (Option A)**: `agents/market_intelligence/strategies/` package (registry / adapters / promotion / telegram). `mi_strategies` table + `mi_live_trades.signal_type` column (backfilled). Phase gate at 3 entry points (entry_pipeline, shadow_orb_tracker, parabolic_detector). Three promotion evaluators (unpaired_r / paired_r / telemetry_review). Manual promotion. Lesson: thin overlay over per-strategy outcome tables is right when each has materially different telemetry semantics; schema unification first would block on backfill that doesn't pay off until ≥6 strategies.
- **session 2 — Theme Pass 1.5 protected-theme relief valve**: `protected_names` exemption made existing-vs-existing consolidation impossible once a duplicate slipped in. Replaced blanket protection skip with score-direction guard (more-established theme survives) + protection contract preserved (when t protected, target must also be protected). Lesson: protection mechanism implicitly assumed existing themes are mutually distinct.
- **session 1 — 5-min Shadow ORB tracker**: Live ORB hard-coded to 1-min; shadow records would-be 5-min entries + outcomes. Pure telemetry. Extracted `broker/exit_logic.py::apply_daily_exit_step` as SSOT (was duplicated across backtester+live). `mi_orb_shadow_trades` UNIQUE (ticker, alert_date, bar_size_minutes). Lesson: highest-risk step was exit_logic extraction — two parity gates (deterministic backtest + mocked-Alpaca call sequence) caught what unit tests can't.

### 2026-04-27
- **session 3 — Parabolic-short M&A/news exclusion**: OGN false positive (buyout-driven). Two-layer: `mi_parabolic_exclusions` (manual permanent + LLM 14-day TTL) + Perplexity news check on climax/anticipation. Three sources with precedence `manual_keep > manual > news_check`. `/parabolic exclude/include/exclusions`. Lesson: price-action detectors need news/context layer for one-shot catalysts.
- **session 2 — Audit-noise reduction**: Three L1 noise sources: (1) `validation_error` lumped 429s + 5xx + parse → split into `*_rate_limited` / `*_api_failure` / `*_error`; (2) zombie themes invariant queried `stage != 'Retired'` but codebase never writes `'Retired'` → narrowed to Mainstream + 10d; (3) `silent_audit_error_window` 30d trained dismissal → hardcoded 24h; (4) `nightly_data_pull` no-show deadline 17:30 too tight + ignored `mi_job_runs` running → bumped 18:30 + cross-check. Lesson: L1 invariants must model system's actual semantics, not textbook ideal.
- **session 1 — Tiered ORB fade guard**: midpoint pre-check stricter than Qullamaggie/Pradeep methodology, redundant with 10:00 ET cleanup + 15% stop-width gate. `check_fade_guard` takes `ratio: float | None`; MAGNA53 HIGH passes `None`, 9M Day 2 passes `0.25`. Lesson: stacked guardrails should each protect a distinct failure mode.

### 2026-04-26
- **session 3 — Job-run telemetry + `/audit job_runs`**: Closes gap between `notify_job_failure` (crashes) and data-layer audit (table invariants); slow runs and silent zeroes had no signal. New `mi_job_runs` + `core/job_audit.py::audit_run` asynccontextmanager + `audit_wrap(fn, job_id, expected_min_rows=N)`. ~30 jobs wrapped. Lesson: a wrapper that interprets return values must agree with wrapped function's failure semantics — `return None` for opt-out vs `return 0` for "wrote nothing".
- **session 2b — Theme merge min-shared-ticker gate**: Pass 1 trigger conditions (`is_subset`, `overlap_ratio ≥ 0.6`) collapse to noise on tiny themes (1/1=100%, 1/2=50%). New `MIN_SHARED_FOR_MERGE = 3` gates Pass 1. Pass 1.5 (small-theme absorption) intentionally targets ≤3-ticker themes, unchanged.
- **session 2a — Crypto RS surveillance (shadow-mode)**: Parallel crypto RS layer; nightly ingest + RS + alt-season trigger eval all run, Telegram surfaces gated by `CRYPTO_RS_ENABLED=false`. New `agents/market_intelligence/crypto/` package (Kraken + DexScreener + CoinGecko + DefiLlama, US-VPS-safe $0). Three-signal alt-season trigger (stablecoin slope + BTC.D + TOTAL3). 11 `crypto_*` tables. RS = 40/30/30 vs `close_btc` ratio. Lesson: data-source sanity check is non-trivial — rejected Polygon Crypto + CMC; DefiLlama doesn't expose BTC.D (caught mid-design).
- **session 1 — RVOL@T pre-open gate (closes INTC-class entry leak)**: Legacy `today_volume / 20d_daily_ADV` mismatched numerator/denominator (thin pre-market vs full-session). Canonical Relative Volume at Time: today's cumulative vs 20-day mean cumulative at same ET clock-minute. New `mi_minute_volume_curves` + `agents/market_intelligence/minute_volume.py`. Pre-9:30 only. Graceful degradation: not in top-500 universe → skip silently. Lesson: stacked filters with mismatched denominators are a class of "silently passes garbage" bug.

### 2026-04-25
- **session 2 — Weekend data fallback + HUD EP button**: Saturday queries returned "no data today" (handlers used `et_today()`). New `collector.last_trading_day(from_date=None)` (skips Sat/Sun → Friday). Wired into HUD/EP/9M/cluster/trades handlers. Added EP button back to HUD inline keyboard.
- **session 1 — Parabolic short detector (TI1 Stage 1)**: Telemetry-only Stamatoudis/Qullamaggie short. Three-tier state machine: `watch → anticipation → climax`. Velocity-delta gate (`roc_5d ≥ 1.10× roc_20d`) is the canonical "parabolic vs linear" discriminator. Backfill verified CAR/GME ✅, NVDA correctly rejected. New `mi_parabolic_candidates` (persists ALL stages incl. unqualified for offline tuning). 17:15 ET cron. Required one-time OHLC backfill via `scripts/backfill_ohlc.py`. Lesson: pure-compute detectors need historical replay tooling first.

### 2026-04-24
- **session 6 — Sugar baby intraday/EOD direction parity**: WU 4/24 surfaced as Day-2 sugar baby despite net −4.6% (gapped −10%, recovered close > open). Intraday filter gated net direction vs prev_close; EOD filter gated only on `close > open` (intraday recovery). Added `(d.close - m.prev_close) / m.prev_close >= 0.03` to EOD SQL. Lesson: SSoT violation — same conceptual filter, two different gates.
- **session 5 — Apollo Resilience & Self-Audit System (L1/L2/L3)**: `system_audit.py` + `audit_invariants.py` (shared invariants). L1 invariant breach → Telegram. L2 anomaly (30d trimmed median ± 3 MAD or > 5× median) → Telegram + Sonnet hypothesis. L3 drift → audit row + Sunday digest. Three jobs (16:15 / 17:30 / 02:00 ET). `/audit <topic>` on-demand. Cold-start tiers (n<7 hardcoded ceilings, 7-14 L3-only, ≥14 full L2). Backfill verification deferred until ≥30 days of baselines (~2026-05-24).
- **session 4 — Zombie theme cooldown flood**: `db.py::get_active_themes()` had no recency filter — returned every theme ever written. Fix: `get_active_themes(stale_after_days=7)`. Recency cap is de-facto retirement mechanism.
- **session 3 — Unified entry pipeline**: `broker/entry_pipeline.py::submit_trade_entry` is the single funnel for MAGNA53 EP + 9M Day 2 ORB. Strategy diffs (stop, sizing) inject via `spec_builder` callback. Bounded action vocabulary (AUTO_ENTERED/PROPOSED/etc). Per-alert work `asyncio.gather` with `Semaphore(5)`. Lesson: two near-identical entry paths drift in opposite directions; one funnel + injection is the fix.
- **session 2 — ORB late-entry & fade guard**: CHE gapped +17.9%, HIGH at 9:55 ET, bracket placed but tape had faded. Fade guard in `_submit_orb_trade`: skip if `last_price < (orb_high+orb_low)/2`. Tightened window `hour==9 and minute<45`. 10:00 ET cleanup job cancels stuck `order_placed`. Lesson: wide intraday windows let dead-cat orders linger.
- **session 1 — OTO bracket stop-leg ID capture**: INTC false UNPROTECTED + Untracked SELL traced to 4 separate "find stop leg" impls; one used strict `==`, broken under Py3.12 `str(OrderType.STOP)` → `"OrderType.STOP"`. Single canonical `alpaca_client.extract_stop_leg_id(order)` (stop_price primary, case-insensitive type fallback) at all 5 sites. Lesson: same conceptual operation in N places drifts; centralize.

### 2026-04-23
- **session 3 — Validation-window hardening**: `Dockerfile.market` now COPYs `scripts/`; `_eod_ep_recap_job` appends `📡 Feed (sip)` line + fires on zero-HIGH days when feed events present; new `scripts/readiness_check.py` encodes 6 SQL cutover gates. Cutover target 2026-05-23.
- **session 2 — Env-var-gated SIP feed**: URI ORB miss traced to IEX zero-range first-minute bars on mid-liquidity. `ALPACA_DATA_FEED` env (iex/sip), resolved by `alpaca_client.get_data_feed()`. Validated AAPL parity 0.037%, URI 4/22 IEX=$0 → SIP=$4.20. `ALPACA_DATA_FEED=sip` set in prod. Phase 2 (Polygon Advanced dual-feed) trigger: book 5–10×, feed incident, OHLC divergence > 0.2%, or 2nd broker.
- **session 1 — Broker alert gaps + bracket hardening**: BSX/GSHD/SIRI naked positions traced to `StopLimitOrderRequest(stop_loss=...)` without `order_class=OTO` — alpaca-py silently drops kwarg. Fix: always OTO + verify stop leg, cancel naked bracket. Silent state changes: 3 branches in `_handle_cancel_or_reject` (was rejected-only); untracked-sell rowcount alert; UNPROTECTED escalation in `_process_entry_fill`. Lesson: silent-drop kwargs are catastrophic — verify what came back.

### 2026-04-22
- **Strip to market/trading focus**: deleted 5 unused sub-agents + Dockerfiles + dead secrets. Lesson: rotting scaffolding is deploy surface.
- **9M Sugar Baby going-in shape telemetry**: 6 new shape cols + `_shape_tag()` bucket. Telemetry-only — promote to filter after 30+ outcomes.
- **Humanize skip reasons + theme validation rate-limit**: `humanize()` translator; `_VALIDATION_SEMAPHORE(2)` + retry on 429. Lesson: "parse errors" were really rate limits — split exception handlers.
- **EP entry diagnostics**: `broker/skip_reasons.py` (18 bounded constants); `/why TICKER [date]` lifecycle timeline; 4:10 PM EOD EP recap. Lesson: free-form skip reasons broke aggregation.

### 2026-04-21
- **Briefing fixes, 9M quality**: 9M intraday range gate (≥ 2%) + extension gate (prev_close ≤ 1.20× SMA-10), anticipation carve-out (gap ≥ 10% OR proj_vol ≥ 25M).
- **`/trades` richer summary**: open + last 5 closed + totals. UTC/ET boundary fix for `closed_at` via `AT TIME ZONE`.

### 2026-04-20
- **Hardening triage**: LLM rate-limit guard in `ep_detector`; correlation matrix off event loop; theme breadth decay (`pct_above_20sma` < 40% × 2d → forced Fading).
- **Weekly system self-audit**: `system_review.py` — Sunday 8 AM ET 7d aggregation → Sonnet synthesis → 4-section Telegram digest.
- **9M quality filters (74 → 2-5/day)**: price ≥ $5, dollar-vol ≥ $50M, directional conviction, 3× ADV ratio (not flat ceiling). Lesson: flat ceilings silently block mid-ADV genuine catalysts.
- **Theme validation + broker partials**: `_extract_json_object()` brace-depth-aware (replaces regex broken by Haiku nested JSON); cross-sector Unknown fallback. KURA partial-exit stop-first ordering.

### 2026-04-19
- **9M ETF flood + EP ETF leakage + catchup ORB orders**: 3-layer 9M ETF filter; EP secondary `mi_security_types` gate; ORB window `now_et.hour < 10` + `misfire_grace_time=300`.
- **`/pregame` + pinned HUD + inline keyboards**: compact trade-ready shortlist; HUD auto-refresh; `/eps`, `/themes`, `/trades` drill-down.
- **9M EP system (Pradeep Bonde "9M" tactic)**: parallel track, zero changes to MAGNA53. New `ninem_detector.py`, `mi_9m_ep_alerts`, `mi_9m_sugar_babies`. Day 2 ORB at 9:31, stop = prior day's low.

### 2026-04-17
- **P15 Correlation clustering**: `correlation_engine.py` — beta-adjusted SPY-residual Pearson 20d. Backtest inconclusive — revalidate ~June 2026.
- **Validation cooldown**: `mi_validation_cooldowns` (14-day cooldown on validation removal); fixes CAR-in-Data-Center churn.
- **Hardening for live trading prep**: orphaned stop remediation; yfinance 30s timeout wrapper; data pull 4:30 → 5:00 PM ET.
- **Theme engine + EP detector fixes**: scratchpad in tool schemas; Unknown sector keyword fallback; post-assignment validation. EP: 15-min projection gate (≥ 9:45 AM); extension via `MIN(close)` over 5d.
