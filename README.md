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

**Two daily briefings (automatic):**
- **5:00 PM PT (8 PM ET)** — Evening briefing: full EOD review package. Sent after close when you sit down to review charts. Includes 🍭 Sugar Babies section if any confirmed 9M days.
- **6:00 AM PT (9 AM ET)** — Morning briefing: EP recap + regime context, 30 min before open.
- HIGH EP alerts fire in real-time during pre-market scan (4–6:30 AM PT). No waiting for briefing.
- 🏦 9M EP alerts fire in real-time during market hours when a stock crosses the 9M share threshold.

### Paper Trading (Alpaca)

Apollo runs semi-automated paper trading via Alpaca. Two independent systems share the same position limits and safeguards.

| Feature | How it works |
|---|---|
| **MAGNA53 EP entries** | Pre-market HIGH alerts subscribe to Alpaca bar WebSocket. First bar close at 9:30:59 → order placed at 9:31:00 |
| ORB entry (post-open HIGHs) | 9:31 AM scan finds new HIGHs → ORB order placed inline |
| ORB fallback | If bar stream misses a pre-market HIGH, 9:31 scan fires `_orb_monitor_job` as safety net |
| Stop width validation | `validate_orb_entry(orb_high, orb_low, atr_14)` — single shared rule. ORB range must be ≤ 1.5x ATR-14. |
| M&A hard filter | Definitive agreement / tender offer → classified `mna` → hard skip before scoring |
| 11 AM cutoff | Re-entry after stop-out only before 11 AM ET |
| **9M EP Day 2 entries** | Sugar babies from the prior day → ORB entry at 9:31 AM. Stop = prior day's low (institutional wall), not ATR. Auto-enters in paper mode. |
| Auto-confirm | Paper mode bypasses Telegram confirmation — both systems execute automatically |
| Day 2+ management | 4:45 PM — SMA 10/20 trailing stops, partial exits (1/3 on Day 3-5), breakeven activation |
| Position tracking | `9m trades` / `trades` command — log with P&L per trade |
| Safeguards | Max 4 positions (shared across both systems), 2% daily loss limit, 3-loss circuit breaker |
| Morning stops | 9:35 AM — GTC stop orders refreshed for Day 2+ positions |
| EOD cleanup | 4:05 PM — cancel unfilled entries, sync positions with Alpaca |
| Position limit config | `MAX_CONCURRENT_LIVE_POSITIONS` in `constants.py` |

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
      ▼
PostgreSQL (pgvector)  +  Redis
Persistent memory          Caching + confirmations
```

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

**Quality gates (intraday + EOD):** price ≥ $5, dollar-volume ≥ $50M (actual) / ≥ $30M (anticipation), gap ≥ 3% OR intraday gain ≥ 4%, effective volume ≥ 3× 20-day ADV, intraday range ≥ 2% of price, `prev_close ≤ 1.20× 10-day SMA` (rejects already-extended chases).

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

### EP Detection (MAGNA53)

MAGNA53 scoring (Pradeep Bonde / Kullamägi methodology).

- **Inputs:** Gap %, relative volume, catalyst quality (Claude), neglect factor, float, regime multiplier
- **HIGH (≥85):** Immediate Telegram alert during pre-market scan
- **MODERATE (≥65):** Shown in morning briefing
- **Perplexity cross-validation:** When Claude + Perplexity agree on catalyst → 1.2x confidence multiplier
- **M&A hard filter:** Definitive agreement / tender offer / going-private → classified `mna` → hard skip before scoring. Buyouts don't trade like EPs.
- **Game-changer floor:** Gap ≥10% + `game_changer` catalyst → minimum score 60 (MODERATE), ensuring high-quality mid-gap moves aren't invisible
- **Open intensity metric:** Post-open volume shown as intensity (`raw_rvol × 390 / minutes_since_open`) rather than projected daily RVOL — honest label, not extrapolated noise
- **Scan schedule:** 7:00 AM – 10:00 AM ET, every 5 minutes

**EP diagnostic from Telegram:** "Why not EP ARAI?" → runs filter checks in sequence, stops at first failure, fetches recent news. Returns specific answer (e.g. `❌ Price filter: $0.67 < $5 minimum`) instead of a generic checklist.

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
| `theme_discovered` | New theme created — name, tickers, thesis |
| `theme_retired` | Theme retired after 5 fading days |
| `stage_change` | Theme lifecycle transition |
| `theme_excluded` | Ticker permanently banned from theme (manual or auto-validation) |
| `orb_triggered` | ORB order placed for an EP alert |
| `orb_filtered` | ORB skipped (stop too wide, ADV too low, etc.) |
| `orb_no_bar` | Bar data unavailable at entry time |
| `9m_ep_detected` | Intraday 9M volume threshold crossed — ticker, volume, price |
| `9m_sugar_babies_confirmed` | EOD sweep confirmed N sugar babies for Day 2 watchlist |

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
| 7:00 AM | 4:00 AM | MAGNA53 EP scan starts; HIGH alerts fire in real-time + bar stream subscriptions |
| 9:00 AM | 6:00 AM | Morning briefing → Telegram |
| 9:30 AM | 6:30 AM | 9M EP intraday scan starts (every 5 min) |
| 9:31 AM | 6:31 AM | Post-open EP scan; ORB orders placed for new HIGHs; 9M Day 2 ORB entries placed |
| 9:35 AM | 6:35 AM | Bar stream cleanup; morning stop refresh for Day 2+ positions |
| 9:35–10:00 AM | 6:35–7:00 AM | Fill checker — poll Alpaca for order fills |
| 10:00 AM | 7:00 AM | MAGNA53 EP scan stops |
| 4:00 PM | 1:00 PM | 9M EP intraday scan stops |
| 4:05 PM | 1:05 PM | EOD cleanup — cancel unfilled orders, sync positions |
| 5:00 PM | 2:00 PM | Data pull — RS engine + regime + themes; 9M EOD sweep → sugar babies confirmed |
| 5:15 PM | 2:15 PM | Parabolic-short scan (TI1 telemetry) → anticipation/climax digest if any |
| 4:45 PM | 1:45 PM | Live position update — SMA trail, partials, stop updates + daily summary |
| 8:00 PM | 5:00 PM | Evening briefing → Telegram (includes sugar babies section if any) |

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
│       ├── agent.py                 # FastAPI app on port 8006
│       ├── db.py                    # Schema + all DB queries
│       ├── collector.py             # Polygon + yfinance + Perplexity data fetching
│       ├── constants.py             # Shared constants (skip lists, sector filters, trimmed_mean)
│       ├── rs_engine.py             # RS scoring + MA computation + single-ticker score
│       ├── ep_detector.py           # MAGNA53 EP scoring + Claude + Perplexity
│       ├── ninem_detector.py        # 9M EP scanner + EOD sugar baby sweep
│       ├── parabolic_detector.py    # Parabolic-short scan (TI1 telemetry, 5:15 PM ET)
│       ├── regime.py                # Market regime engine
│       ├── briefing.py              # Evening + morning briefing formatters
│       ├── theme_engine.py          # Theme discovery + deduplication + lifecycle
│       ├── scheduler.py             # APScheduler jobs (4:30pm data, 8pm evening, 9am morning)
│       ├── fundamentals.py          # O'Neil fundamentals + get_fundamentals_batch()
│       ├── outcome_tracker.py       # Nightly forward return computation (RS/EP/9M → mi_signal_outcomes)
│       ├── screener.py              # Composite screener (RS + theme + fundamentals)
│       ├── universe.py              # Curated universe with company descriptions
│       ├── trading_calendar.py      # NYSE holiday calendar (exchange-calendars lib, offline)
│       ├── backtester/
│       │   ├── engine.py            # Core trade simulation (Day 1 ORB + Day 2+ SMA trail)
│       │   ├── filters.py           # validate_orb_entry() — single shared ORB stop-width rule
│       │   ├── models.py            # BacktestTrade, TradeEntry, TradeExit dataclasses
│       │   ├── tracker.py           # Paper trade tracker (EOD sim); parse_json_list, format_trade_attempts
│       │   ├── intraday.py          # Intraday bar fetching + caching
│       │   └── safeguards.py        # Position limits, daily loss cap, circuit breaker
│       └── broker/
│           ├── alpaca_client.py     # Async Alpaca SDK wrapper (paper + live)
│           ├── bar_stream.py        # Alpaca StockDataStream — subscribe EP candidates, fire ORB on first bar
│           ├── order_manager.py     # Order lifecycle (entry, stops, partials, exits)
│           ├── live_tracker.py      # Real-time ORB monitor + Day 2+ management
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

### Recently completed (April 2026)
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
| P22 | **Wick-fill shadow tracking (telemetry-only)** | 9M days closing mid-range with long upper wick + green body (Kristjan/Bonde "negated shooting star"). Sugar Baby filter correctly rejects these — but they capture alpha via different mechanism. Build `mi_wick_candidates` table; answer 3 questions after 30+ candidates before promoting to execution. |
| — | **MAGNA53 simulator** | Interactive frontend: slider over gap/RVOL/catalyst/float/regime → shows final score + component breakdown. Needs web UI. |
