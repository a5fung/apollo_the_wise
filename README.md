# Apollo Assistant

A Telegram-based trading assistant for momentum / episodic-pivot (EP) methodology (Qullamaggie, Pradeep Bonde, Marios Stamatoudis). Full RS + EP + theme engine + paper/live Alpaca ORB trading.

---

## What Apollo Does

**Talk to it naturally in Telegram. It figures out the rest.**

### Market Intelligence (primary)

Apollo runs a full market intelligence stack focused on momentum/EP trading methodology (Qullamaggie, Pradeep Bonde, Marios Stamatoudis).

| Ask Apollo | What happens |
|---|---|
| "Send evening briefing" | Regime + RS leaders + active themes + MA pullbacks |
| "Send morning briefing" | EP alerts recap + regime context (pre-market) |
| "Any EPs today?" | EP alerts with MAGNA53 score, catalyst quality, Perplexity cross-validation |
| "9m" / "show 9m" | 9M EP intraday detections + today's sugar babies (Day 2 ORB watchlist) |
| "9m trades" | Day 2 ORB trade log with P&L for 9M entries |
| "9m performance" | Sugar baby history: volume, range quality, Day 2 outcome |
| "What's the market regime?" | Bull/Choppy/Correcting/Crisis + VIX + breadth + MA context |
| "Top RS stocks" | Momentum leaders ranked by 1M/3M/6M composite RS |
| "What themes are active?" | Persistent themes with lifecycle stage + constituent stocks |
| "Optical stocks near 20MA?" | MA pullback scan filtered to a theme's tickers |
| "Score AXTI" | On-demand RS rank for any ticker (1 API call, exact percentile) |
| "Fundamentals on CIEN" | O'Neil-style EPS/revenue quarterly table + quality flags (yfinance) |
| "Find top 20 stocks with RS > 70 and EPS growth > 25%" | Composite screener: RS + theme stage + fundamentals ranked by score |
| "Best Accelerating theme stocks with fundamentals" | Screener filtered to Accelerating themes with EPS/revenue data |
| "AXTI is working, track it" | Apollo asks questions, adds to tracking + seeds theme |
| Any stock/investment question | Apollo consults market agent before answering |
| `/setup TICKER [days]` | Reverse-lookup detector chronology across 10 tables (EP, 9M, wick, parabolic, flag, themes, trades) with TradingView chart link |
| `/flags` / `/flags TICKER` | Continuation flag detector (VCP / Qullamaggie tightening) — today's COILED + TRIGGERED, or 14d ticker history |
| `/watchlist` | Friday curated watchlist (Friday 6 PM ET) — best ideas across all sources + TradingView import block |
| `/wick` | Wick-fill candidates (telemetry) — today's candidates + 30d fill-rate footer |
| `/why TICKER [date]` | EP lifecycle timeline — every gate hit/miss for one alert |
| `/audit <topic>` | On-demand L1/L2/L3 anomaly check — cooldowns, themes, skips, positions, feed, 9m, all |
| `/strategies` / `/strategy <id>` | Strategy maturity registry — phase + KPI promotion thresholds, manual `enable / disable / promote / demote` |
| `/dryrun` | Pre-flight sizing math against current Alpaca equity (no orders placed) |
| `/pregame` | Compact trade shortlist for tomorrow — Accelerating themes + HIGH EPs + watchlist + sugar babies |
| `/postmortem TICKER [YYYY-MM-DD]` | Sonnet-narrated 4-section trade postmortem (Setup / Execution / Outcome / Lesson) |

**Two daily briefings (automatic):**
- **5:00 PM PT (8 PM ET)** — Evening briefing: full EOD review package. Sent after close when you sit down to review charts. Includes 🍭 Sugar Babies section if any confirmed 9M days.
- **6:00 AM PT (9 AM ET)** — Morning briefing: EP recap + regime context, 30 min before open.
- HIGH EP alerts fire in real-time during pre-market scan (4–6:30 AM PT). No waiting for briefing.
- 🏦 9M EP alerts fire in real-time during market hours when a stock crosses the 9M share threshold.

### Paper Trading (Alpaca)

Apollo runs semi-automated paper trading via Alpaca. Two independent systems share the same position limits and safeguards.

| Feature | How it works |
|---|---|
| **MAGNA53 EP entries** | Pre-market HIGH alerts subscribe to Alpaca bar WebSocket. First bar close at 9:30:59 → order placed at 9:31:00 via unified `entry_pipeline.submit_trade_entry` |
| ORB entry (post-open HIGHs) | 9:31 AM scan finds new HIGHs → ORB order placed inline |
| ORB fallback | If bar stream misses a pre-market HIGH, 9:31 scan fires `_orb_monitor_job` as safety net |
| Stop width validation | `validate_orb_entry(orb_high, orb_low, atr_14)` — single shared rule. ORB range must be ≤ 1.5x ATR-14. |
| M&A hard filter | Three-layer defense (`ma_filter.py`): EP catalyst classifier verdict → `_MNA_KEYWORDS` text scan → Polygon news headline backstop. SSoT shared by EP + flag detectors |
| Earnings-day catalyst boost | `is_earnings_day` (yfinance) confirms ±yesterday/today; routine catalyst → strong, plus MODERATE→HIGH override at gap ≥10%. Closes the DDOG/AAON/HIMX miss class |
| 11 AM cutoff | Re-entry after stop-out only before 11 AM ET |
| **9M EP Day 2 entries** | Sugar babies from the prior day → ORB entry at 9:31 AM. Stop = prior day's low (institutional wall), not ATR. Auto-enters in paper mode. Same `entry_pipeline.submit_trade_entry` funnel as MAGNA53 |
| Auto-confirm | Paper mode bypasses Telegram confirmation — both systems execute automatically |
| Day 2+ management | 4:45 PM — SMA 10/20 trailing stops, partial exits (1/3 on Day 3-5), breakeven activation |
| Position tracking | `9m trades` / `trades` / `/setup TICKER` — log with P&L per trade, reverse-lookup detector chronology across 10 tables |
| Safeguards (full list) | See **Safeguards** section below — kill switch, max 5 concurrent positions, PDT guards, 2% daily-loss limit, count-based circuit breaker (interim), drawdown breaker (shadow) |
| Morning stops | 9:35 AM — GTC stop orders refreshed for Day 2+ positions; stale `stop_order_id` nulled on update failure for orphan reconciliation |
| EOD cleanup | 4:05 PM — cancel unfilled entries (preserves prior fill history); 9:00 PM evening backstop catches late EXPIRED events |
| Position limit config | `MAX_CONCURRENT_LIVE_POSITIONS=5` in `constants.py` |
| **Cross-strategy allocator** | Shadow phase (#43, 5/8) — strategies enqueue to `mi_pending_allocations`; 9:35 AM allocator scores composite (40/30/20/10), emits `unified_allocation_decided` audit. Phase 1B activation gated on ≥5 days shadow telemetry. See `cross_strategy_allocator.py` |

**Status:** Paper trading live on Alpaca paper account ($100K). Collecting data to validate before real money.

---

## Architecture

```
User (Telegram)
      │
      ▼
Apollo Orchestrator (port 8000)     ← Claude Sonnet — plans, reasons, delegates
      │ internal REST API
      ▼
Market Intelligence :8006
  RS engine, EP detection, theme clustering, regime,
  Alpaca paper + live ORB trading, TradingView webhooks
      │
      ├──── Alpaca Paper Account (TradingClient + TradingStream)
      ├──── Alpaca Live Account  (TradingClient + TradingStream) — gated by ENABLE_LIVE_MODE
      │
      ▼
PostgreSQL (pgvector)  +  Redis
Persistent memory          Caching + confirmations
```

**Dual-account architecture** (#66, 2026-05-10): one Apollo container subscribes to BOTH Alpaca paper and live accounts simultaneously. Strategies route per `mi_strategies.phase`:

| phase | live_real_enabled | Submit destination |
|---|---|---|
| `shadow` | – | audit telemetry only (no submit) |
| `paper` | – | Alpaca paper account (real fills, fake $) |
| `live` | False | 🟡 STAGED-PAPER Telegram proposal (no auto-submit) |
| `live` | True | Alpaca live account (real fills, real $) |

Per-account safeguards are isolated (paper at-cap doesn't constrain live). Per-strategy `position_size_multiplier` + `max_concurrent_positions` enable gradual live promotion. Set `ENABLE_LIVE_MODE=false` for dev / single-account opt-out.

---

## Market Intelligence — How It Works

### RS Scoring

Momentum ranking in the style of Marios Stamatoudis (not IBD RS Rating).

- **Timeframes:** 1M / 3M / 6M price returns
- **Composite:** 40% × 1M rank + 30% × 3M rank + 30% × 6M rank
- **Score:** 0–100 percentile rank within the scored universe
- **Universe:** Full US stock universe (~9,700 stocks via Polygon daily closes)
- **On-demand:** "Score AXTI" → 1 Polygon call, ranks against today's stored distribution

### RS Filtering

Leaders are filtered to surface institutional-quality names only:

- **Min ADV:** 500K median daily volume (20-day median, immune to volume spikes)
- **Min price:** $10 (filters penny stocks)
- **Skip list:** Leveraged/inverse ETFs, broad index ETFs, sector ETFs, commodity ETFs
- **Sector filter:** Healthcare/Biotech excluded unless price ≥ $50 (filters drug-trial noise, keeps large-cap pharma)

### RS Persistence

Once a stock shows RS leadership it stays tracked nightly. Top 50 RS leaders each run are added to `mi_tracked_stocks`. A stock is deactivated after 7 consecutive weak days (RS composite < 40).

### Theme Engine

Bottom-up from price action (Marios Stamatoudis methodology). Themes emerge from which stocks move together — not top-down hypothesis.

- Existing themes are **re-scored daily** from current RS data (no redundant re-clustering)
- Claude clustering only runs on **uncovered RS leaders** (stocks not in any active theme)
- Lifecycle: 🌱 Nascent → ⚡ Accelerating → 📊 Mainstream → 🔻 Fading → Retired (after 5 fading days)
- Themes survive across days — persist until price action says otherwise
- **Deduplication:** Overlapping themes auto-merged (Jaccard ≥ 0.6 or ticker subset). Sector-level caps prevent theme proliferation (e.g. max 2 oil/gas themes, biotech excluded). Existing themes are protected — new clusters have overlap stripped rather than absorbing the existing theme.
- **Trimmed mean scoring:** Theme RS composite drops bottom 20% of constituents — resists outlier drag from 1-2 weak stocks in an otherwise strong theme
- **Stage transitions use 3-day smoothed score** (±8pt thresholds) — prevents noisy daily flips from Perplexity binary news scores
- **Name inheritance on rediscovery:** If a theme briefly retires and comes back, the old name is inherited via Jaccard ticker-overlap matching (threshold 0.4) — prevents the same 25-stock cluster cycling through new names every few weeks
- **Fat theme splitting:** Themes with >20 stocks are candidates for a sub-theme split. Sonnet analyzes the stock list; uncertain cases escalate to Opus advisor. Sub-themes with 3–8 stocks get a more specific thesis and are protected from re-absorption by their parent. Split decisions logged to `mi_audit_log`.
- **Sub-theme parent relationship:** `parent_theme` column in `mi_themes` — sub-themes coexist with their parent instead of being merged back
- **Commodity contradiction rules:** Stocks can't be in commodity-contradicting themes (e.g. gold miners can't be in uranium/nuclear themes) — stripped at enforcement layer
- **Jaccard history fallback:** Stage/age history inherited from prior name via ticker-overlap matching — renamed themes don't reset to Nascent
- **Description-based validation:** `_validate_theme_membership` runs Mon/Wed/Fri — asks Claude Haiku if each stock's description still matches the theme; removes mismatches
- **Persistent exclusions:** `mi_theme_exclusions` table — once a ticker is removed from a theme (via validation or manual command), it's permanently banned from re-entering that theme. Enforcement at DB layer, before any scoring runs.
- **Advisor strategy:** Theme discovery and assignment use Claude Sonnet with an Opus advisor tool. Sonnet consults Opus on genuinely hard decisions (borderline clusters, ambiguous assignments) — all other calls go straight to output. Capped at 3 Opus calls per run.

**Manage themes from Telegram:**
```
Exclude CAR from IT Infrastructure & Data Center    → permanent ban, takes effect next run
List exclusions                                     → see all active bans
Remove exclusion CAR from [theme name]              → undo ban
```

### 9M EP Detection

A parallel, LLM-free EP track based on Pradeep Bonde's "9M" tactic. Volume is the catalyst — ≥8.9M shares on a single day signals institutional repositioning confirmed, no news needed.

**Two signals:**
- **9M actual** — today's volume crosses 8.9M shares → Telegram `🏦 9M EP` alert fires immediately
- **9M pace** — projected volume ≥ 12M based on rate (only after 30 min elapsed, ≥3M shares already traded). Pings Telegram **only if** `gap ≥ 10%` or projected volume ≥ 25M (high-conviction carve-out). Lower-conviction anticipations still write to DB and surface via `/9m` and the evening-brief `🔍 Anticipation-only today` roundup.

**Quality gates (intraday + EOD, identical filters):** price ≥ $5, dollar-volume ≥ $50M (actual) / ≥ $30M (anticipation), gap ≥ 3% OR intraday gain ≥ 4%, effective volume ≥ 3× 20-day ADV (ratio, not flat ceiling), intraday range ≥ 2% of price, `prev_close ≤ 1.20× 10-day SMA` (rejects already-extended chases). **Target 2-5 alerts/day**.

**Sugar baby destroyed-name trend gate** (5/8, ATEC class): filters when ALL three fail — `prev_20d_pct < -10%` AND `prev_vs_sma50 < 0.85` AND `sma50_slope_pct < 0`. Catches dead-cat-bounce candidates (single 9M day on a structurally destroyed name).

**Sugar Babies** — stocks completing a 9M day with a strong close:
- Volume ≥ 9M shares
- Close > Open (green day)
- Close in top 25% of daily range: `(close - low) / (high - low) ≥ 0.75`
- Price ≥ $5.00, dollar-volume ≥ $50M, virgin 9M (≥ 3× ADV), range ≥ 2%, not extended vs 10d SMA

Sugar Babies appear in the evening briefing as Day 2 ORB candidates. At 9:31 AM next morning, Apollo automatically places ORB entries for each one (paper mode). Stop = prior day's low (the institutional volume wall), not ATR-based.

**From Telegram:**
```
9m                   → today's intraday detections + pending Day 2 watchlist
9m performance       → sugar baby history + Day 2 outcome rates
9m trades [30d]      → Day 2 ORB trade log with P&L
trade 9m TICKER      → manually queue a Day 2 entry for a specific ticker
```

**Scan schedule:** Every 5 minutes, 9:30 AM – 4:00 PM ET.

---

### Wick-Fill Shadow Tracking (TI2 / P22 — telemetry only)

A nightly EOD branch off the 9M sugar-baby selection. **Telemetry-only** — no entries, no orders. Promotion to paper gated on 30+ candidates AND fill rate ≥ 50%.

The "negated shooting star" setup (Kristjan / Pradeep Bonde): when a 9M day closes mid-range with a green body, shorts are trapped at the upper wick. Day 2+ break of `prior_high` is the canonical short-cover impulse.

**Three-way EOD branch off the shared 9M context CTE:**
- `close_in_range_pct ≥ 0.75` → sugar baby (existing Day-2 ORB path)
- `close_in_range_pct ∈ [0.50, 0.75)` → **wick candidate** (new — telemetry row only)
- `close_in_range_pct < 0.50` → distribution, ignored

Wick candidates inherit all sugar baby gates (price ≥ $5, dollar-vol ≥ $50M, ≥ 3× ADV, range ≥ 2%, extension cap, **and the same net-up ≥ 3% directional gate**). Only the range-position branch differs — single source of truth via shared `_NINEM_CONTEXT_CTE` + `is_9m_directional` / `is_green_close` predicates.

**Forward-returns measurement** (10-session horizon): two anchors deliberately — `fwd_{1,3,10}d_from_high_pct` (conditional on fill — measures the actual short-cover impulse) and `fwd_{1,3,10}d_from_close_pct` (unconditional drift baseline). The gap between them is the strategy's edge.

**From Telegram:**
```
/wick                → today's candidates + 30d telemetry footer (n_settled · n_filled / fill_rate)
```

**Schedule:** EOD sweep at 5:00 PM ET writes wick rows alongside sugar babies. New `_wick_forward_returns_job` 5:35 PM ET walks unsettled rows once the 10-session horizon elapses.

---

### Parabolic Short Detection (TI1 — telemetry only)

A nightly scan for the Stamatoudis / Qullamaggie parabolic-exhaustion setup. **Telemetry-only** — surfaces candidates to a Telegram digest, no entries placed. Promotion path (paper → live) requires 2-3 months of shadow data per `memory/project_trading_ideas_backlog.md` (TI1).

**Three-tier state machine** per (ticker, scan_date):
- `unqualified` — any qualifying gate fails. Persisted, no alert.
- `watch` — all qualifying gates pass; burst checklist not yet aligned. Silent DB row.
- `anticipation` — watch + burst score ≥ 3/4 (gaps, range expansion, volume expansion, up-day streak). Telegram watchlist.
- `climax` — anticipation + `gapped_today` + `climax_volume_flag`. Telegram trigger.

**Qualifying gates:**
- Liquidity: today's dollar volume ≥ $10M
- Prior move (cap-tier): Large ≥$10B → 50% · Mid $2-10B → 100% · Small <$2B → 200%
- Extension: `close / SMA-50 ≥ 1.50`
- Velocity: daily-compound `roc_5d ≥ 1.10× roc_20d` (parabolic, not linear)
- Pullback count last 20d (telemetry only — not a hard gate)

**Dual-use framing:** even when the climax cluster is a strong-RS leadership group (e.g. semi-cap sweep), the flags are actionable as profit-take signals on existing longs in the same name, or as hedge candidates (e.g. SOXS) when multiple cluster within one sector. Not just short candidates.

**Telegram digest:** 2-section format, suppressed entirely on zero candidates per audit-vs-alert rule.

**Scan schedule:** 5:15 PM ET, mon-fri (between nightly data pull and post-nightly audit).

**Verification tooling:**
```
python scripts/backfill_parabolic_car.py --source yf --end-date 2026-04-21
python scripts/backfill_parabolic_car.py --ticker GME --end-date 2021-02-05
python scripts/backfill_parabolic_car.py --ticker NVDA --end-date 2024-03-15  # should reject
```

---

### Continuation Flag Detector (VCP / Qullamaggie tightening)

Daily state-machine scan for the post-runup VCP / tightening flag setup. **Shadow phase** — telemetry-only, no entries. XNDU 4/16 → 5/01 was the calibration case (9-session base after pivot, breakout 5/01).

**Five stages** per (ticker, scan_date):
- `unqualified` → `WATCH` → `TIGHTENING` → `COILED` → `TRIGGERED` (or `INVALIDATED`)

**Pivot anchor:** highest-volume bar within 2% of period max-high (tightened 5% → 2% on 5/8 to prevent volume-stealing-pivot from a non-near-max-high bar).

**Stable-anchor (5/8):** pivot only walks forward when current lookback's max_high beats the prior pivot by ≥ 1% (`_PIVOT_WALK_THRESHOLD`). Fixes the marginal-walk-forward failure where slow higher-highs in tight increments kept `base_age` near zero.

**Fresh-tightening predicate**: alternative COILED path for short bases (≥4 sessions) where early-vs-recent contraction math can't fire — uses 2-bar TR vs ATR-14 + hybrid volume ceiling (`max(recent_5d_avg, 0.5 × ADV20)`).

**M&A filter** at COILED + TRIGGERED stages — same SSoT (`ma_filter.py`) as EP detection.

**From Telegram:**
```
/flags                 → today's COILED + TRIGGERED candidates with chart links
/flags watch           → WATCH + TIGHTENING tier (deeper drill-down)
/flags TICKER          → 14d stage history for one ticker
```

**Scan schedule:** 5:25 PM ET, mon-fri (between fishhook 5:20 and post-nightly audit 5:30).

**SSoT:** `docs/setups/flag_continuation.md`.

---

### Friday Curated Watchlist

Friday 6:00 PM ET aggregator — combines best ideas from EP / 9M / themes / wick / parabolic / RS into a single Telegram digest with TradingView import block + per-ticker chart-link buttons.

**Cross-source dedup priority:** EP > theme > 9M > wick > parabolic > RS. Single bullet per ticker with bracketed reason chips. Top 25 by composite priority.

**Two integration depths:**
1. Text import block `EXCHANGE:TICKER` comma-separated → TradingView mobile Watchlist Import
2. Per-ticker chart-link inline keyboard, top 8, 4×2 layout, deep-links to TradingView charts

**From Telegram:** `/watchlist`

---

### Drawdown Circuit Breaker (#39, shadow phase)

Replaces the count-based 10-loss circuit breaker (which was self-perpetuating and methodology-blind for Pradeep/Qullamaggie hold-winners style). State-machine evaluated daily at 4:12 PM ET cron.

**Mechanics:**
- **Equity source**: Alpaca `account.equity` (includes unrealized — open winners lift equity)
- **Peak window**: 30-day rolling max from `mi_account_equity_snapshots`
- **Trip threshold**: drawdown ≤ -5% while state='OK' → TRIPPED
- **Release threshold**: drawdown ≥ -2.5% while state='TRIPPED' → OK (asymmetric hysteresis prevents flap)
- **Stale-data fail-open**: if most recent snapshot >48h old, breaker effectively disabled (silent cron-failure protection)
- **Account-mode scoping**: paper history doesn't carry to live; live cutover starts a fresh peak

**Phase**: SHADOW — emits `drawdown_breaker_tripped` / `drawdown_breaker_released` audit events on transitions only; `_check_safeguards` does not block. Promotion to active gated on ≥14 days post-live-cutover telemetry (env var `DRAWDOWN_BREAKER_PHASE=active`).

**SSoT:** `docs/setups/safeguards.md`.

---

### Cross-Strategy Unified Allocator (#31, Phase 1A shadow)

Replaces the cron-order FCFS slot grab (5/7 incident: 9M Day 2 took all available slots before MAGNA53 ORB monitor). Shared queue + composite scoring across strategies.

**Scoring (Phase 1):**
- 40% setup quality (MAGNA53 = ep_score; 9M Day 2 = blend of close-in-range + gap)
- 30% catalyst (game_changer 100, strong 70, routine 30; 9M intrinsic 100)
- 20% volume (pm_rvol or vol/ADV ratio, capped + normalized)
- 10% regime (Bull 100, Crisis 60)

No Z-norm — multi-day spike (5/8) showed it systemically penalizes MAGNA53's cap-saturated top-tier scores. Track-record dimension (Phase 2) is the proper home for cross-strategy reliability.

**Tie-breakers:** pm_rvol → gap_pct → strategy priority (MAGNA53 > 9M > Flag).

**Phase 1A (shadow, current):**
- Strategies enqueue to `mi_pending_allocations`
- 9:35 AM ET cron drains, scores, marks `shadow_rank` + `shadow_allocated`
- Emits `unified_allocation_decided` audit event with full ranking
- Legacy submission paths run unchanged

**Phase 1B activation** (gated on ≥5 days shadow telemetry, earliest 5/15): move cron to 9:28 ET pre-market, add price-freshness HARD gate (>1.5% past trigger → drop), refactor strategies to drain queue (winners only), intraday re-sweep on stop/exit events, FCFS fallback.

Spec: `~/.claude/plans/cross-strategy-ranking-spike.md`. Spike harness: `scripts/spike_unified_allocator.py`.

---

### Live-cutover Gate 5 hardening (A–G)

A layered defense system for trade-state correctness, hardened across May 2026 in response to five trade-state corruption incidents (CRMD/KLAR/ARM/BW/AIXI). Each Gate addresses a distinct bug class. Run as preflight on every deploy via `scripts/deploy.sh`. SSoT: `docs/setups/safeguards.md`.

| Gate | What it catches | Implementation |
|---|---|---|
| **A — Naked-position remediation** | Entry-fill UPDATE raises exception → bracket child stop dies → position naked | `trade_stream._process_entry_fill` catches exception, immediately submits fallback stop-market at intended orb_low BEFORE any other action |
| **B — Boot-time DB UPDATE prepare validation** | asyncpg type-mismatch (CRMD class: numeric vs double precision sharing param) | `scripts/preflight_db_updates.py` walks every parameterized UPDATE via `connection.prepare()`. Deploy step `[5b/5]` blocks on `AmbiguousParameterError` |
| **C — Escalated naked-position alert** | partial_fill on entry leaves position un-stopped | Escalation to CRITICAL Telegram on naked detection |
| **D — Stuck-fill watchdog** | Entry stays `status='filling'` past ACK window | Cron surfaces rows where `entry_order_id IS NOT NULL AND status='filling' AND filled_at IS NULL AND created_at < NOW() - INTERVAL '2 min'` |
| **E — Schema regression pytest** | Column-type additions break hot-path UPDATEs | Test suite against mi_live_trades schema |
| **F — Operator post-mortem sign-off** | Process discipline gate | Manual review |
| **G — Column-write authority preflight** (2026-05-17) | Multi-writer column ownership violations (BW class) | `scripts/audit_column_writes.py check` + `ALLOWED_WRITERS` dict. Deploy step `[5c/5]` blocks on unauthorized (column, function) pair. See `docs/architecture/trade-state-ownership.md` |
| **Stop-ACK timeout watchdog** (2026-05-17, sibling to Gate 5 A) | OTO bracket child stop-leg never ACKs from Alpaca (silent failure, MRAM class) | New scheduler job every 30s during market hours: `status='filled' AND filled_at NOT NULL AND stop_order_id IS NULL AND filled_at < NOW() - INTERVAL '30 seconds'` → submit fallback stop |

**Deploy chain** (`scripts/deploy.sh`):
1. git pull
2. build images
3. restart containers
4. wait for boot
5. `[5/5]` entry-pipeline safeguard walk (PASS = strategies can authenticate)
6. `[5b/5]` DB UPDATE prepare validation
7. `[5c/5]` column-write authority check

Any preflight failure exits non-zero with a distinct code (4/5/6) — no green-deploy without all three gates passing.

---

### System Self-Audit (L1/L2/L3)

Three-tier anomaly + invariant scanner runs at 4:15 PM (post-EOD) and 5:30 PM (post-nightly). Detects silent breakage that would otherwise compound across days.

| Tier | Trigger | Action |
|---|---|---|
| **L1** | Hard SQL invariant breach | Immediate Telegram + audit row |
| **L2** | Metric outside 30d trimmed median ± 3 MAD OR > 5× median | Immediate Telegram with Sonnet hypothesis |
| **L3** | Band transition (drift) | Audit row only; surfaces in Sunday weekly digest |

Cold-start tiers: `sample_n < 7` → hardcoded ceilings only. `7 ≤ n < 14` → L3 only. `≥ 14` → full L2.

**On-demand:** `/audit <topic>` — cooldowns, themes, skips, positions, feed, 9m, all.

Sonnet hypothesis call gets last 5 CLAUDE.md change headers + last 10 distinct audit event types as context.

---

### EP Detection (MAGNA53)

MAGNA53 scoring (Pradeep Bonde / Kullamägi methodology).

- **Inputs:** Gap %, relative volume, catalyst quality (Claude), neglect factor, float, regime multiplier
- **HIGH (≥85):** Immediate Telegram alert during pre-market scan
- **MODERATE (≥65):** Shown in morning briefing
- **Perplexity cross-validation:** When Claude + Perplexity agree on catalyst → 1.2x confidence multiplier
- **Hedge-phrase downgrade** (Track B Layer 2): when `perplexity_answer` contains hedge phrases ("no specific information", "couldn't find", etc.), downgrade catalyst one notch and skip the agreement boost — defensive read against chained-LLM hollow-input grading
- **M&A hard filter** (`ma_filter.py`, three layers): EP catalyst classifier → `_MNA_KEYWORDS` text scan over catalyst texts → Polygon news headline backstop. SSoT shared by EP and flag detectors so both setups close the same coverage gap
- **Earnings-day catalyst boost** (Track B Layer 3, 5/8): `is_earnings_day(ticker, scan_date)` via yfinance `earnings_dates` + `calendar` confirms today/yesterday earnings; routine catalyst → strong, plus MODERATE→HIGH override at gap ≥ 10%. Tightened to {yesterday, today} window — closes DDOG/AAON/HIMX class without false-positive spillover
- **Cooldown bypass on fresh earnings**: 60-day re-alert cooldown bypassed when `gap ≥ 15% AND is_earnings_day` (HIMX 5/7-class — quarterly earnings is structurally fresh signal)
- **Pm-shares floor relative-anomaly carveout** (5/8): the absolute 25K pm-shares floor is skipped when `pm_rvol ≥ 5×` — low-float names with strong relative anomaly no longer false-blocked
- **pm_rvol gate (RVOL@T)** (`minute_volume.py`): per-minute baselines from `mi_minute_volume_curves` (~2,647 tickers, $5M+ ADV20 floor); pre-9:30 uses pm anchor, 9:30+ uses session anchor with the same primitive
- **Game-changer floor:** Gap ≥10% + `game_changer` catalyst → minimum score 60 (MODERATE), ensuring high-quality mid-gap moves aren't invisible
- **Open intensity metric:** Post-open volume shown as intensity (`raw_rvol × 390 / minutes_since_open`) rather than projected daily RVOL — honest label, not extrapolated noise
- **Scan schedule:** 7:00 AM – 10:00 AM ET, every 5 minutes
- **Bar fetch retry:** 10s delay (was 60s) — bars settle in seconds, not minutes
- **Stop-limit BUY buffer**: SSoT helper `stop_limit_buy_price(stop)` = `round(max(stop * 1.005, stop + 0.02), 2)` — 0.5% with $0.02 floor, prevents 1¢-effective-buffer on penny tickers

**EP diagnostic from Telegram:** "Why not EP ARAI?" → runs filter checks in sequence, stops at first failure, fetches recent news. Returns specific answer (e.g. `❌ Price filter: $0.67 < $5 minimum`) instead of a generic checklist.

**`/setup TICKER`**: reverse-lookup detector chronology across ~10 tables (EP, 9M intraday, 9M sugar, wick, parabolic, flag, themes, live/paper trades, weekly watchlist) with TradingView chart-link button. Answers "what did Apollo see in $XNDU?" — see also `/why TICKER` for EP-specific lifecycle.

### Market Regime

| Label | EP Threshold | Meaning |
|---|---|---|
| Bull | ≥70 | Standard criteria |
| Choppy | ≥80 | Raise your bar |
| Correcting | ≥85 | Exceptional setups only |
| Crisis | ≥90 | Very selective |

Signals: SPY/QQQ vs 50MA + 200MA, VIX, breadth (% stocks above 40MA), +/-4% ratio (10-day rolling).

### Single-Ticker Analysis

Every RS / fundamentals / research query on a single ticker includes two layers of peer context:

- **Layer 1 — Theme RS:** If the ticker is in an active theme, its rank within that theme's constituents (e.g. "#3 of 12 in AI Infrastructure")
- **Layer 2 — Industry RS:** GICS industry-level percentile rank among all same-industry stocks (e.g. "Biotechnology → 71st pct, #95 of 340 tracked"). Falls back to sector level if industry bucket < 10 peers.

"Research MRNA" / "Look up NVDA" also fetch a Perplexity news summary (recent catalyst, business developments) in parallel.

---

### O'Neil Fundamentals

On-demand earnings quality check via yfinance (no extra API key).

- **Quarterly table:** Last 6 quarters of EPS (with YoY %), revenue (with YoY %), gross margin % — Caruso-style monospace layout
- **Annual table:** Last 5 filed fiscal years of EPS + revenue
- **Quality flags:** EPS accelerating, consecutive quarters ≥25% growth, revenue confirms (≥15% YoY)
- **Gross margin:** Per-quarter actual % shown in table (sanity-clamped 0–100%)
- **Next earnings date** shown in header

Ask: "Fundamentals on AXTI" / "EPS growth for CIEN" / "quarterly revenue SMCI"

### Composite Screener

Finds the best setups by combining RS rank + active theme stage + O'Neil fundamentals into a single composite score.

**Composite score formula:** `rs_composite + theme_bonus + eps_bonus + accel_bonus`

| Bonus | Value |
|---|---|
| Accelerating theme | +15 |
| Nascent theme | +8 |
| Mainstream theme | +5 |
| EPS YoY ≥ 50% | +10 |
| EPS YoY ≥ 25% | +5 |
| EPS YoY ≥ 0% | +2 |
| EPS accelerating (latest > prior quarter) | +5 |

**Filters available:** min RS, min EPS YoY %, min revenue YoY %, require acceleration, require sales confirms, theme stage filter.

Ask: "Find top 20 fundamental stocks with RS" / "Best Accelerating theme stocks with EPS growth" / "Screen for RS > 70, EPS > 25%, revenue confirms"

### Teaching Apollo

When you spot something the system isn't tracking:

1. Tell Apollo: *"AXTI is working — it's a photonics play"*
2. Apollo asks: which tickers? new theme or existing? one-line thesis?
3. Apollo calls `/teach` → tickers added to RS tracking + theme seeded
4. Offer to run data refresh → new tickers scored immediately

### Audit Log

Critical engine events are written to `mi_audit_log` and queryable from Telegram — no SSH needed.

| Event type | What triggers it |
|---|---|
| `advisor_call` | Sonnet consulted Opus — includes full question + verdict |
| `theme_discovered` / `theme_retired` / `stage_change` / `theme_excluded` | Theme lifecycle |
| `validation_error` / `assignment_error` / `discovery_error` | Theme engine silent failures (banner in morning briefing) |
| `validation_rate_limited` / `anthropic_rate_limited` | 429 retries; surfaces in morning briefing 🟠 banner |
| `orb_triggered` / `orb_filtered` / `orb_no_bar` | ORB lifecycle |
| `orb_unfilled_cancelled` / `eod_unfilled_cancelled` | 10:00 ET / 4:05 PM cleanup of unfilled bracket entries |
| `partial_exit_committed` / `full_exit_committed` / `stop_exit_committed` | Trade lifecycle (real fill, not order placement) |
| `naked_position_detected` | `stop_order_id` nulled after stop placement / update failure → reconcile |
| `9m_ep_detected` / `9m_sugar_babies_confirmed` | 9M intraday + EOD |
| `9m_sugar_baby_filtered_destroyed_trend` | ATEC-class filter (prev_20d < -10% AND prev_vs_sma50 < 0.85 AND sma50 slope < 0) |
| `mna_filter_fired` | M&A filter caught a deal candidate (source: catalyst / keyword / polygon) |
| `catalyst_earnings_boost` / `earnings_override_applied` | EP earnings-day catalyst promotion |
| `ep_cooldown_bypassed_earnings` | 60-day cooldown bypassed on fresh earnings |
| `flag_stage_flip_held` | Flag detector hysteresis — single-day downgrade held one day |
| `parabolic_climax_detected` / `parabolic_anticipation` | Parabolic short scan |
| `drawdown_breaker_tripped` / `drawdown_breaker_released` / `drawdown_check_unavailable` | Drawdown breaker state transitions (shadow) |
| `unified_allocation_decided` | Cross-strategy allocator picks (shadow) — full ranking + winners |
| `split_detected` / `split_applied` / `split_phantom_detected` | Splits ingest pipeline (Phase 0 of nightly) |
| `audit_invariant_breach_*` | L1 hard guard fail (immediate Telegram) |
| `metric_anomaly` | L2 outlier (>3 MAD or >5× median) — includes Sonnet hypothesis |

**From Telegram:**
```
Audit log          → last 20 events, 48h
Advisor log        → Opus calls + verdicts (full detail)
Show logs 7d       → extend to 7 days
Show logs advisor  → filter to advisor calls only
Show logs discover → new theme discoveries only
Show logs excluded → exclusion events
```

---

## Daily Schedule

| Time (ET) | Time (PT) | What |
|---|---|---|
| 7:00 AM | 4:00 AM | MAGNA53 EP scan starts; HIGH alerts fire in real-time + bar stream subscriptions; allocator queue starts filling |
| 9:00 AM | 6:00 AM | Morning briefing → Telegram |
| 9:30 AM | 6:30 AM | 9M EP intraday scan starts (every 5 min) |
| 9:31 AM | 6:31 AM | Post-open EP scan; ORB orders placed for new HIGHs; 9M Day 2 ORB entries placed (parallel via `asyncio.gather`) |
| 9:35 AM | 6:35 AM | Bar stream cleanup; morning stop refresh for Day 2+ positions; **cross-strategy allocator shadow** — scores queue, emits `unified_allocation_decided` |
| 9:35–10:00 AM | 6:35–7:00 AM | Fill checker — poll Alpaca for order fills |
| 10:00 AM | 7:00 AM | MAGNA53 EP scan stops; ORB unfilled-entry cleanup |
| 4:00 PM | 1:00 PM | 9M EP intraday scan stops |
| 4:05 PM | 1:05 PM | EOD cleanup — cancel unfilled orders, sync positions, audit-log unfilled cancellations |
| 4:10 PM | 1:10 PM | EOD EP recap — HIGH outcomes + feed telemetry |
| 4:12 PM | 1:12 PM | **Account equity snapshot** + drawdown breaker state recompute (drawdown_breaker, currently shadow phase) |
| 4:15 PM | 1:15 PM | **Post-EOD audit** — L1 invariants + trade-side L2/L3 anomaly detection |
| 4:45 PM | 1:45 PM | Live position update — SMA trail, partials, stop updates + daily summary |
| 5:00 PM | 2:00 PM | Data pull — RS engine + regime + themes; 9M EOD sweep → sugar babies confirmed; splits ingest (Phase 0); error check |
| 5:15 PM | 2:15 PM | Parabolic-short scan (TI1 telemetry) → anticipation/climax digest if any |
| 5:25 PM | 2:25 PM | **Continuation flag scan** (shadow) — VCP / Qullamaggie tightening flag detector |
| 5:30 PM | 2:30 PM | **Post-nightly audit** — theme/cooldown/regime L2/L3 anomaly detection |
| 5:35 PM | 2:35 PM | Wick-fill forward-returns (TI2/P22 telemetry) — settles unsettled wick candidates |
| 6:00 PM (Fri) | 3:00 PM | **Friday curated watchlist** — chart-review aggregator + TradingView import block |
| 8:00 PM | 5:00 PM | Evening briefing → Telegram (includes sugar babies, wick watch, parabolic, flag candidates) |
| 9:00 PM | 6:00 PM | **Evening position backstop** — 2nd `sync_positions` pass catches late EXPIRED events |
| 2:00 AM | 11:00 PM | **Baseline refresh** — rebuild `mi_metric_baselines` 30d trailing for L2/L3 audit |
| Sun 8:00 AM | 5:00 AM | Weekly system self-audit — 7d metrics + L3 drift roll-up → Telegram digest |

---

## Data Sources

| Source | Used For | Tier |
|---|---|---|
| Polygon.io | Price history, RS engine, EP gap data | Starter ($29/mo) |
| yfinance | Company profile, sector, analyst ratings, news | Free |
| Perplexity | EP catalyst news search + cross-validation | Pay-per-use |
| Anthropic | Orchestrator, catalyst classification, theme clustering | Pay-per-use |
| Alpaca | Paper/live trading, real-time market data (ORB bars) | Free (paper) |
| Telegram | Bot delivery | Free |

---

## Project Structure

```
Apollo_Assistant/
├── main.py                          # Entry point
├── core/
│   ├── orchestrator.py              # Claude tool-use loop
│   ├── router.py                    # Tool definitions + sub-agent routing
│   ├── context.py                   # System prompt (market intelligence instructions)
│   ├── notifications.py             # Direct Telegram alerts (startup, job failures)
│   ├── memory.py                    # PostgreSQL + pgvector memory
│   └── confirmations.py             # YES/NO gate for irreversible actions
├── channels/
│   ├── telegram.py                  # Telegram bot + /help command
│   └── webhooks.py                  # FastAPI webhook receiver
├── agents/
│   └── market_intelligence/
│       ├── agent.py                 # FastAPI app on port 8006 + execute_task router
│       ├── db.py                    # Schema + all DB queries (single SSoT for table layout)
│       ├── collector.py             # Polygon + yfinance + Perplexity data fetching
│       ├── constants.py             # Shared constants (skip lists, safeguards, drawdown thresholds)
│       ├── rs_engine.py             # RS scoring + MA computation + single-ticker score
│       ├── ep_detector.py           # MAGNA53 EP scoring + Claude + Perplexity (with hedge-phrase downgrade)
│       ├── ninem_detector.py        # 9M EP scanner + EOD sugar baby sweep + destroyed-name filter
│       ├── parabolic_detector.py    # Parabolic-short scan (TI1 telemetry, 5:15 PM ET) + earnings-day exclusion
│       ├── flag_detector.py         # Continuation flag detector (VCP / Qullamaggie, 5:25 PM ET)
│       ├── friday_watchlist.py      # Friday 6:00 PM ET aggregator + TradingView import block
│       ├── wick_tracker.py          # Wick-fill forward-returns settlement (TI2/P22 telemetry)
│       ├── ma_filter.py             # SSoT M&A filter — keywords + Polygon news backstop
│       ├── earnings_calendar.py     # is_earnings_day(ticker, scan_date) via yfinance two-surface
│       ├── minute_volume.py         # RVOL@T per-minute baselines (mi_minute_volume_curves)
│       ├── splits_ingest.py         # Phase 0 of nightly — Polygon splits + post-apply ratio sanity
│       ├── system_audit.py          # L1/L2/L3 anomaly + invariant scans (4:15 + 5:30 PM ET)
│       ├── audit_invariants.py      # Shared invariant library (also used by readiness_check.py)
│       ├── cross_strategy_allocator.py  # Phase 1A shadow allocator (#31)
│       ├── regime.py                # Market regime engine
│       ├── briefing.py              # Evening + morning briefing formatters + send_telegram_message
│       ├── theme_engine.py          # Theme discovery + deduplication + lifecycle
│       ├── scheduler.py             # APScheduler jobs (full daily cron stack)
│       ├── fundamentals.py          # O'Neil fundamentals + get_fundamentals_batch()
│       ├── outcome_tracker.py       # Nightly forward return computation (RS/EP/9M → mi_signal_outcomes)
│       ├── screener.py              # Composite screener (RS + theme + fundamentals)
│       ├── universe.py              # Curated universe with company descriptions
│       ├── trading_calendar.py      # NYSE holiday calendar (exchange-calendars lib, offline)
│       ├── strategies/
│       │   ├── registry.py          # mi_strategies registry — phase + KPI thresholds + enable flag
│       │   └── adapters.py          # Per-strategy promotion-evaluation adapters
│       ├── backtester/
│       │   ├── engine.py            # Core trade simulation (Day 1 ORB + Day 2+ SMA trail)
│       │   ├── filters.py           # validate_orb_entry() + compute_atr_14 (Wilder TR, 5/5 fix)
│       │   ├── models.py            # BacktestTrade, TradeEntry, TradeExit dataclasses
│       │   ├── tracker.py           # Paper trade tracker (EOD sim); parse_json_list, format_trade_attempts(_live)
│       │   ├── intraday.py          # Intraday bar fetching + caching
│       │   └── safeguards.py        # Position limits, daily loss cap (legacy count breaker)
│       └── broker/
│           ├── alpaca_client.py     # Async Alpaca SDK wrapper + extract_stop_leg_id SSoT
│           ├── bar_stream.py        # Alpaca StockDataStream — subscribe EP candidates, fire ORB on first bar
│           ├── trade_stream.py      # WebSocket fill events — purpose-tagged routing (entry/partial/full/stop)
│           ├── order_manager.py     # Order lifecycle — finalize_partial_exit / finalize_full_exit / finalize_stop_fill
│           ├── entry_pipeline.py    # SSoT funnel — submit_trade_entry for MAGNA53 + 9M Day 2
│           ├── skip_reasons.py      # 18 bounded skip-reason constants (filter:* / setup:* / block:* / infra:* / window:*)
│           ├── live_tracker.py      # Real-time ORB monitor + Day 2+ management + _check_safeguards
│           ├── drawdown_breaker.py  # Daily account equity snapshot + state machine (shadow #39)
│           ├── orb_extension_shadow.py  # Counterfactual lifecycle for cancelled-ORB cutoffs
│           ├── gap_through_telemetry.py # Stop-limit gap-through frequency telemetry
│           ├── shadow_orb_tracker.py    # Shadow ORB strategy (paired_r promotion model)
│           └── telegram_confirm.py  # Inline keyboard trade proposals
├── docker/
│   ├── docker-compose.yml           # Local dev
│   ├── docker-compose.prod.yml      # Production (all services + Uptime Kuma)
│   ├── Dockerfile.orchestrator
│   └── Dockerfile.market            # Market Intelligence agent
├── shared/
│   ├── models.py                    # Pydantic models
│   ├── secrets.py                   # Secrets access
│   └── registry.py                  # Agent URL registry
├── integrations.yaml                # Agent URL config
├── scripts/
│   ├── backtest_9m_ep.py            # 9M EP historical backtest (D1/D5/D10/D21 returns by vol/range bucket)
│   ├── backtest_clusters.py         # Correlation cluster precision/recall backtest
│   ├── backfill_parabolic_car.py    # CAR/GME/NVDA verification tool for parabolic detector
│   ├── backfill_wick_replay.py      # POET-class wick-fill verification (yfinance, no DB)
│   └── backfill_ohlc.py             # One-time OHLC backfill (mi_daily_closes via Polygon grouped-daily)
├── start.sh                         # Start Apollo locally
└── start_market.sh                  # Start market agent locally
```

---

## Quick Start

See **`SETUP.md`** for the full setup guide.

```bash
# Terminal 1 — Apollo orchestrator + infrastructure
bash start.sh

# Terminal 2 — Market Intelligence Agent
bash start_market.sh

# Verify everything is up
# Send /agents in Telegram → all agents should show green
```

**Required `.env` keys:**
- `TELEGRAM_BOT_TOKEN` — from @BotFather
- `TELEGRAM_ALLOWED_USER_IDS` — your Telegram user ID
- `ANTHROPIC_API_KEY`
- `POLYGON_API_KEY`
- `PERPLEXITY_API_KEY`
- `FMP_API_KEY`
- `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` — from Alpaca dashboard
- `ALPACA_PAPER=true` — paper trading mode (default safe)
- `LIVE_TRADING_ENABLED=false` — master kill switch
- `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `INTERNAL_API_SECRET`

---

## Production Deploy

Target: Hetzner CPX21 Ashburn (~$8/mo), Docker Compose, Telegram long-polling.

```bash
docker compose -f docker/docker-compose.prod.yml up -d --build
```

Includes Uptime Kuma (self-hosted status dashboard) + Apollo self-reports startup health and scheduler failures directly to Telegram.

**Monthly cost:** ~$20–40 (server + APIs). Jumps to ~$50–70 with Polygon Starter.

See `docker/docker-compose.prod.yml` and the deployment notes in the project memory for the full checklist.

---

## Security Model

| Concern | Mitigation |
|---|---|
| Telegram access | Allowlist — only configured user IDs can interact |
| Alpaca trading | Master kill switch (`LIVE_TRADING_ENABLED`), paper/live toggle (`ALPACA_PAPER`), confirmation timeout (5 min), atomic status transitions prevent duplicate orders |
| Trade data integrity | DB DELETE triggers block accidental deletion on trade tables; startup row count logging detects data loss |
| Account info | Account equity never shown in Telegram messages (% of account only) |
| Irreversible actions | YES/NO confirmation gate before execution |
| TradingView webhooks | Verified via shared secret header; delivered via nginx reverse proxy on port 80 |
| Single ORB rule | `validate_orb_entry()` in `backtester/filters.py` — shared by EOD sim and live Alpaca path, structural divergence impossible |
| Audit trail | `mi_audit_log` DB table — advisor calls, theme changes, exclusions, ORB events; queryable from Telegram |
| Secrets | Env vars only, never in code or logs |

---

## Backlog / Upgrade Path

### Recently completed (May 2026)
- ✅ **Gate 5 G column-write authority preflight (5/17)** — static analysis at deploy time: `scripts/audit_column_writes.py check` walks every UPDATE/INSERT on `mi_live_trades`, fails the deploy on any `(column, function)` pair not in `ALLOWED_WRITERS`. Closes the BW-class bug surface (multi-writer column ownership). Last unshipped Gate 5 deliverable. Sibling refactors T1.1/T1.2/T1.4 same day cut `stop_price` writers 7 → 4
- ✅ **Stop-ACK timeout watchdog (5/17)** — sibling to Gate 5 A. Closes MRAM-class silent failure (entry fills, OTO bracket child stop-leg never ACKs, position naked). New scheduler job every 30s during market hours, submits fallback stop, escalates to Telegram CRITICAL on remediation failure
- ✅ **EP Selectivity Phase 1-7 (5/16-17 weekend)** — cohort analysis + meta-rubric architecture (catalyst rubric = ONE input among fundamentals/theme/technical/gap) + multi-dimensional catalyst grading (6 axes, Gemini-weighted 2× Axis 1 + 2× Axis 5) + immediate filter ships (R2/R4/R6/P2.0a/P2.0b) + alpha-slip hedge (MAGNA53→flag carryforward + 9M universe-watch). Sugar baby Day 2 recovery analysis at 22.4%. Operator catalyst labels (~98 alerts cross-tabbed). ADR `docs/decisions/0003-ep-selectivity-overhaul.md`
- ✅ **Dual-account architecture (#66, 5/10)** — one Apollo container subscribes to both paper + live Alpaca accounts. Strategy `phase` field routes per-account. Per-mode TradingClient singletons, mode-bound `client_order_id`, cross-account event validation in WebSocket dispatcher, per-mode safeguard isolation, per-mode position/drawdown state. Boot bootstrap hard-requires both keypairs when `ENABLE_LIVE_MODE=true`. Legacy `ALPACA_API_KEY` remapped to `ALPACA_PAPER_*` at boot
- ✅ **Per-strategy sizing + position cap (#65, 5/10)** — two new `mi_strategies` columns: `position_size_multiplier` + `max_concurrent_positions`. Applied in entry_pipeline post-spec-builder (covers both MAGNA53 and 9M Day 2). Enables gradual live promotion (e.g., 9M Day 2 starts at multiplier=0.5 + cap=2)
- ✅ **Track 1 trade-state ownership refactor (5/17)** — T1.1 dropped stop_price/hard_stop from entry-fill UPDATE (KLAR/ARM bug source); T1.2 dropped stop_price from partial-fired wrapping UPDATE; T1.4 dropped redundant writes from no-partial branch (BW class + LOST UPDATE hazard). Cuts stop_price writers 7→4, partial_taken writers 2→1. SSoT: `docs/architecture/trade-state-ownership.md`
- ✅ **P&L attribution column (5/14)** — `mi_live_trades.pnl_attribution` excludes incident damage from methodology evaluation metrics. NULL = methodology (default); non-NULL names the incident. Account equity still reflects actual hit; only Gate 3 paper R-expectancy + system review aggregations filter on this column
- ✅ **Preflight smoke test (#84, 5/13)** — `scripts/preflight_check.py` walks every enabled non-shadow strategy through `_check_safeguards`. Run as final deploy step. The 2026-05-13 outage (seed × dual-account mismatch — `phase='live'` rows but `ENABLE_LIVE_MODE=false`) would have been caught here
- ✅ **Cross-strategy unified allocator Phase 1A (#31, shadow ship 5/8)** — `mi_pending_allocations` queue + `cross_strategy_allocator.py` module + 9:35 AM shadow cron. MAGNA53 + 9M Day 2 strategies enqueue; allocator scores 40/30/20/10 (setup/catalyst/volume/regime), emits `unified_allocation_decided` audit. Z-norm DROPPED post-spike (8-day simulation showed it systemically penalizes MAGNA53's cap-saturated top-tier scores). Phase 1B activation gated on ≥5 days shadow telemetry (earliest 5/15)
- ✅ **Drawdown circuit breaker (#39, shadow ship 5/8)** — methodology-aware state machine replacing count-based breaker. Daily 4:12 PM ET cron snapshots Alpaca equity (includes unrealized — open winners lift), recomputes state with asymmetric hysteresis (-5% trip / -2.5% release). State-aware threshold check eliminates flap-spam; stale-data fail-open prevents silent cron-failure lockout. Promotion gated on ≥14d post-live-cutover
- ✅ **Stable-anchor pivot for flag detector (#37, 5/8)** — pivot only walks forward when current lookback's max_high beats prior pivot by ≥1%. Fixes marginal-walk-forward where slow higher-highs in tight increments kept `base_age` stuck at zero. Replay-verified on XNDU/VECO/OKLO calibration cases
- ✅ **5/7 paper-session triage (5/8)** — five additive fixes: parabolic earnings-day exclusion + `days_up_streak ≥ 3` hard gate (AGL/XMTR class); EP earnings-day catalyst boost (DDOG/AAON class); EP cooldown bypass on fresh earnings (HIMX class); pm-shares floor relative-anomaly carveout (`pm_rvol ≥ 5×`); phantom split sanity check via post-apply ratio
- ✅ **Setup SSoT discipline (5/7)** — `docs/setups/*.md` per-setup canonical files (magna53_ep, ninem, parabolic_short, flag_continuation, wick_fill, safeguards, convergence) + `CHANGE_PROCESS.md` discipline rules. Required reading before any setup change; all changes carry Trigger / Evidence / Anticipated effect / Reversion-flag / Status fields
- ✅ **`/setup TICKER` reverse-lookup (5/1)** — fans out across ~10 detector tables in parallel; ticker timeline merged + sorted, top 60 capped, TradingView chart-link button. Answers "what did Apollo see in $XNDU?"
- ✅ **Continuation flag detector (5/1, shadow)** — VCP / Qullamaggie tightening flag, daily 5:25 PM ET. Five-stage state machine, fresh-tightening predicate for short bases, M&A filter shared with EP via `ma_filter.py` SSoT
- ✅ **Friday curated watchlist (4/30)** — Friday 6:00 PM ET aggregator combining EP/9M/themes/wick/parabolic/RS into one digest with TradingView import block + per-ticker chart-link buttons
- ✅ **Splits ingest authoritative (5/1)** — Polygon `/v3/reference/splits` Phase 0 of nightly; replaces `MAX_PERIOD_RETURN=300` heuristic that misfired on recently-listed verticals. Phantom split sanity check via post-apply ratio (5/8)
- ✅ **`compute_atr_14` Wilder TR (5/5)** — switched from close-only approximation to full Wilder TR (`max(H-L, |H-prev_close|, |L-prev_close|)`). Volatile/gappy stocks (STRL/EVER) no longer reject as `setup:stop_too_wide`
- ✅ **Stop-leg ID capture SSoT (5/3)** — `alpaca_client.extract_stop_leg_id` is canonical helper; `_handle_fill` checks WS event legs + DB + REST refetch before remediation. Deferred-commit pattern for partial/full exits — DB writes happen on real fill, not order placement
- ✅ **Self-audit L1/L2/L3 (5/3+)** — daily 4:15 PM (post-EOD) + 5:30 PM (post-nightly) anomaly scans against `mi_metric_baselines` 30d trailing. Cold-start tiers, Sonnet hypothesis on L2, Sunday weekly drift roll-up. On-demand `/audit <topic>`
- ✅ **Hedge-phrase catalyst downgrade (5/3, Track B Layer 2)** — when Perplexity returns hedge phrases, downgrade catalyst one notch and skip agreement boost. Closes RDDT-class miss where chained-LLM grades hollow input as confident
- ✅ **Three-layer M&A filter SSoT (5/4, `ma_filter.py`)** — catalyst classifier verdict → `_MNA_KEYWORDS` text scan → Polygon news headline backstop. Shared by EP + flag detectors; no per-detector reinvention. AVNS take-private surfaced the gap
- ✅ **Limit-buffer SSoT (5/4)** — 7 hand-rolled `* 1.001` sites collapsed to one helper `stop_limit_buy_price(stop) = round(max(stop * 1.005, stop + 0.02), 2)`. Penny tickers ($5.49) no longer get 1¢-effective-buffer that doesn't cross
- ✅ **9M Day 2 cron parallelization (5/4)** — `asyncio.gather(*..., return_exceptions=True)` + `Semaphore(5)`. SOUN's 60s bar-retry no longer queues TEAM behind it
- ✅ **Apollo time handling discipline (4/29 → 5/8)** — every datetime/time comparison in this codebase is in America/New_York (ET). Container runs UTC; naive `datetime.now()` returns UTC clock with no tzinfo and silently breaks every ET-keyed comparison. `datetime.now(_ET)` everywhere, never `datetime.now()` / `datetime.utcnow()` / `date.today()`

### Recently completed (April 2026)
- ✅ **P22 — Wick-Fill shadow tracker (telemetry-only)** — 9M days closing mid-range with green body (Kristjan/Bonde "negated shooting star"). Three-way EOD branching off shared 9M CTE: `≥ 0.75` → sugar baby, `[0.50, 0.75)` → wick, `< 0.50` → ignored. Same gates as sugar babies (incl. net-up ≥ 3% via shared `is_green_close` predicate); only range-position differs. Forward-returns measured from two anchors (prior_high conditional on fill, prior_close unconditional baseline) — gap between them is the edge. `/wick` command, evening-brief Wick Watch line, weekly review drift-gap citation. POET 2026-04-21 verified via `scripts/backfill_wick_replay.py`. First strategy shipped through the Strategy Maturity Framework
- ✅ **Strategy Maturity Framework (Option A)** — thin overlay registry (`mi_strategies`); each strategy declares phase (shadow → paper → live) + KPI promotion thresholds + enable flag. Three promotion models: `paired_r` (Shadow ORB), `unpaired_r` (MAGNA53, 9M Day 2), `telemetry_review` (parabolic_short, wick_fill). Per-strategy outcome tables stay; adapter pattern layers on top. Phase gate at three entry points (entry_pipeline + shadow_orb_tracker + parabolic_detector). `/strategies` table + `/strategy <id> [enable|disable|promote|demote]`. Manual promotion only — verdict flags eligibility, user runs the action
- ✅ **Apollo strip to market/trading focus** — deleted 5 unused sub-agents (finance/calendar/research/browser/travel) + Dockerfiles + compose blocks + tool schemas + enum values + 9 dead secrets; orchestrator kept for future expansion
- ✅ **9M Sugar Baby going-in shape telemetry** — 6 new columns (prev_5d, prev_20d, prev_vs_sma10/50, sma50 slope, prior_sessions); bucket tags (uptrend/pullback/extended/bounce/downtrend/flat) surfaced in evening brief + `/9m` + `9m outcomes`. Telemetry-only — promote to filter after 30+ outcomes
- ✅ **EP entry diagnostics & performance traceability** — `broker/skip_reasons.py` (18 bounded constants); every HIGH EP has durable terminal state by 4:10 PM ET; `/why TICKER [date]` lifecycle timeline; 4:10 PM EOD EP recap; evening-brief "EP OUTCOMES TODAY" section
- ✅ **Humanize skip reasons** — Telegram shows English prose; DB keeps machine prefixes for `split_part()` aggregation
- ✅ **Theme validation rate-limit handling** — `_VALIDATION_SEMAPHORE(2)` caps concurrent Haiku; retry-once on 429; three-bucket error banner (🔴 errors / 🟠 rate-limited / 🟡 parse errors)
- ✅ **9M quality filters + cadence carve-out** — price ≥ $5, dollar-vol ≥ $50M actual / $30M anticipation, directional conviction (gap ≥ 3% OR intraday ≥ 4%), 3× ADV ratio (not flat ceiling), range ≥ 2%, extension gate (prev_close ≤ 1.20× SMA-10); silent anticipations unless gap ≥ 10% OR proj_vol ≥ 25M. Target ~6–7 pings/day
- ✅ **Haiku JSON parse hardening** — depth-aware brace parser replaces naive regex (fixed 20-error nightly breakage); `max_tokens` 200→400
- ✅ **Theme breadth decay** — `pct_above_20sma` forces Fading when breadth < 40% for 2 consecutive days
- ✅ **LLM rate-limit guard + correlation off-loop** — `ep_detector` `AsyncAnthropic` + `Semaphore(5)` + retry; `correlation_engine` 2800×2800 matrix wrapped in `asyncio.to_thread()`
- ✅ **Weekly system self-audit** — Sunday 8 AM ET; 7d aggregates → Sonnet synthesis → Telegram 4-section digest; persists `mi_system_reviews`; grades prior week's suggestions
- ✅ **Broker partial-exit hardening** — stop-first ordering (cancel old stop → place new for 2/3 → then sell 1/3); fractional qty fix; caller honors return value; skip-reason propagation through tuple return
- ✅ **Orphaned stop remediation** — auto-places protective stop if filled trade has no `stop_order_id`; yfinance 30s timeout wrapper
- ✅ **`/trades` richer summary** — open positions with entry→current→stop, last 5 closed inline, totals row; UTC/ET boundary fix for `closed_at`
- ✅ **P9 — Trade postmortem** `postmortem TICKER [YYYY-MM-DD]`; Sonnet 4-section recap (Setup/Execution/Outcome/Lesson); weekly review auto-narrates best+worst
- ✅ **P7 — `/pregame`** compact trade shortlist (Accelerating themes, HIGH EPs, watchlist MAs, 9M sugar babies); no LLM
- ✅ **Slash commands + pinned HUD** — `/hud`, `/eps`, `/9m`, `/themes`, `/clusters`, `/regime`, `/positions`, `/trades`; hourly auto-refresh of pinned HUD during market hours; inline-keyboard drill-downs
- ✅ **P2 — MODERATE EP recap** in morning briefing (rel_volume + claude_analysis)
- ✅ **P3 — Paper trade validation report** scaffold (`validation report` / `paper performance`); upgrades to full report at 10+ closed trades
- ✅ **9M EP system** — parallel LLM-free EP track (Pradeep Bonde "9M" tactic); intraday scan, sugar baby EOD sweep, Day 2 ORB auto-entry, outcome tracking, backtest script
- ✅ **P15 — Correlation clustering** — BFS connected components on beta-adjusted SPY-residual returns; feeds theme discovery; `show clusters`; revalidate once theme history reaches 6+ months (~June 2026)
- ✅ **Validation cooldowns** — 14-day re-assignment ban after validation removal; `show cooldowns`, `bypass cooldown TICKER`
- ✅ Real-time ORB entry via Alpaca bar WebSocket (pre-market HIGH → subscribed → order at 9:30:59)
- ✅ Single shared ORB stop-width rule (`validate_orb_entry`) — EOD sim and live path structurally identical
- ✅ M&A hard filter — definitive agreement / tender offer → skip before scoring
- ✅ EP scoring dead zone fix — 10%+ gap + game_changer catalyst → minimum MODERATE score
- ✅ TradingView webhooks — nginx reverse proxy on port 80, instant delivery
- ✅ Theme name inheritance on rediscovery — retired-then-returned themes keep their name
- ✅ Fat theme splitting — Sonnet + Opus advisor splits >20-stock catchalls into focused sub-themes
- ✅ Industry-relative RS — every single-ticker query shows theme rank + GICS industry percentile
- ✅ EP diagnostic — "why not EP TICKER?" runs filter checks, stops at first failure, fetches news
- ✅ Trade audit trail — per-attempt entry/exit timestamps on every trade display
- ✅ Audit log — all engine decisions queryable from Telegram (advisor calls, theme events, ORB events)
- ✅ **P4** EP outcome table (`ep outcomes 30d`)
- ✅ **P5** Theme conviction display (days active + consecutive Accelerating)
- ✅ **P6** Trading journal (`journal: <note>`, `show journal`)

### Previously completed
- ✅ Full Pradeep Market Monitor (T2108, breadth counts, 4% ratio, consecutive breakdown tracking)
- ✅ Signal outcome tracking (EP/RS forward returns, theme stage constituent returns)
- ✅ State-change alerts (RS deterioration, theme transitions, MA breaks)
- ✅ Composite screener (RS + theme stage + O'Neil fundamentals)
- ✅ Chart mosaic (top RS leaders grid → Telegram + X post)
- ✅ Persistent theme exclusions (DB-layer ban, not Haiku-dependent)
- ✅ Advisor strategy (Sonnet + Opus for hard clustering decisions)
- ✅ Real-time trade stream (Alpaca WebSocket fills + stops)
- ✅ Day 1 re-entry (max 2 attempts, price-aware re-entry logic)

---

### Priority backlog

The critical path to live trading: **P3 data accumulation → P16 live**. Flip when regime improves from Crisis and ~10 closed paper trades are on record.

| # | Item | Why now |
|---|---|---|
| P10 | **Conditional auto-entry alerts** | Not standalone price alerts (TradingView handles those). Becomes valuable only when fused: trigger AND ticker has Accelerating/Mainstream theme AND RS ≥ threshold AND permissive regime → auto-prepare/propose trade. Defer until live trading is on. |
| P13 | **Theme constituent churn detection** | Flag stocks entering/exiting a theme 2+ times in 10 days. Auto-suggest permanent exclusion. Query `mi_theme_history`. |
| P16 | **Live trading** | Flip `LIVE_TRADING_ENABLED=true` after P3 validation data is solid and regime improves from Crisis. |
| P17 | **Monthly & quarterly system reviews** | Weekly review ships already. Add monthly (1st Sun, 30d window, Opus) + quarterly (regime-conditional stats) after weekly has 3+ cycles and is trusted. |
| P18 | **+3R / 72h partial-profit path** | Current partial is hold-day based. Add R-multiple trigger (`price ≥ entry + 3×initial_risk → sell 1/3`) as additional path. Needs 10+ closed trades of data first. |
| P19 | **VIX-scaled continuous risk sizing** | Binary today (`RISK_PCT=0.01`, halved when QQQ EMA bearish). Continuous `risk = base × max(0, 1 - (VIX-15)/20)` is cleaner but needs VIX ingest. Revisit after 3+ months live. |
| P20 | **Earnings-week IV pre-pass** | Blocked: Polygon free tier has no IV. |
| P21 | **Cross-asset thematic validation** | Parallel RS on commodity/futures ETFs (CPER, URA, HG). Equity theme + commodity RS alignment → boost theme conviction ×1.2. |
| — | **MAGNA53 simulator** | Interactive frontend: slider over gap/RVOL/catalyst/float/regime → shows final score + component breakdown. Needs web UI. |
