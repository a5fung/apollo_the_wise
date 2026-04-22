# Apollo Assistant

A Telegram-based personal assistant that acts as a "chief of staff" — it plans, reasons, and delegates to specialized sub-agents. Built around market intelligence as its core capability, with calendar, research, travel, and browser automation alongside.

---

## What Apollo Does

**Talk to it naturally in Telegram. It figures out the rest.**

### Market Intelligence (primary)

Apollo runs a full market intelligence stack focused on momentum/EP trading methodology (Qullamaggie, Pradeep Bonde, Marios Stamatoudis).

| Ask Apollo | What happens |
|---|---|
| "Send evening briefing" | Regime + RS leaders + active themes + MA pullbacks |
| "Send morning briefing" | EP alerts recap + regime context (pre-market) |
| "Any EPs today?" | EP alerts with MAGNA53 score, catalyst quality, Gemini cross-validation |
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

### General capabilities

- **Finance** — IBKR portfolio/P&L (read-only), TradingView price alerts pushed to Telegram
- **Calendar** — Google Calendar + iCloud events, create/reschedule/cancel (with confirmation)
- **Research** — Web search with synthesized answers, article summarization
- **Travel** — Flight/hotel research, trip itineraries, Amex Platinum perks optimizer
- **Browser** — General website automation via Playwright

---

## Architecture

```
User (Telegram)
      │
      ▼
Apollo Orchestrator (port 8000)     ← Claude Sonnet — plans, reasons, delegates
      │ internal REST API
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  Sub-agents (each isolated in Docker)                           │
│                                                                 │
│  Market Intelligence :8006    Finance Agent :8001               │
│  RS engine, EP detection,     IBKR read-only,                   │
│  theme clustering, regime,    TradingView webhooks              │
│  Alpaca paper trading                                           │
│                                                                 │
│  Calendar Agent :8002         Research Agent :8003              │
│  Google + iCloud CalDAV       Tavily web search                 │
│                                                                 │
│  Travel Agent :8005           Browser Agent :8004               │
│  Flights, hotels,             Playwright automation             │
│  Amex Platinum perks                                            │
└─────────────────────────────────────────────────────────────────┘
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

### EP Detection (MAGNA53)

MAGNA53 scoring (Pradeep Bonde / Kullamägi methodology).

- **Inputs:** Gap %, relative volume, catalyst quality (Claude), neglect factor, float, regime multiplier
- **HIGH (≥85):** Immediate Telegram alert during pre-market scan
- **MODERATE (≥65):** Shown in morning briefing
- **Gemini cross-validation:** When Claude + Gemini agree on catalyst → 1.2x confidence multiplier
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
| 4:45 PM | 1:45 PM | Live position update — SMA trail, partials, stop updates + daily summary |
| 8:00 PM | 5:00 PM | Evening briefing → Telegram (includes sugar babies section if any) |

---

## Data Sources

| Source | Used For | Tier |
|---|---|---|
| Polygon.io | Price history, RS engine, EP gap data | Starter ($29/mo) |
| yfinance | Company profile, sector, analyst ratings, news | Free |
| Tavily | EP catalyst news search, theme confirmation | Free/Pro |
| Anthropic | Orchestrator, catalyst classification, theme clustering | Pay-per-use |
| Gemini | EP catalyst cross-validation | Free (gemini-1.5-flash-8b) |
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
│       ├── collector.py             # Polygon + yfinance + Tavily data fetching
│       ├── constants.py             # Shared constants (skip lists, sector filters, trimmed_mean)
│       ├── rs_engine.py             # RS scoring + MA computation + single-ticker score
│       ├── ep_detector.py           # MAGNA53 EP scoring + Claude + Gemini
│       ├── ninem_detector.py        # 9M EP scanner + EOD sugar baby sweep
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
│   └── backtest_clusters.py         # Correlation cluster precision/recall backtest
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
- `GEMINI_API_KEY`
- `TAVILY_API_KEY`
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
| IBKR | Read-only API — no trade execution implemented |
| Alpaca trading | Master kill switch (`LIVE_TRADING_ENABLED`), paper/live toggle (`ALPACA_PAPER`), confirmation timeout (5 min), atomic status transitions prevent duplicate orders |
| Trade data integrity | DB DELETE triggers block accidental deletion on trade tables; startup row count logging detects data loss |
| Account info | Account equity never shown in Telegram messages (% of account only) |
| Irreversible actions | YES/NO confirmation gate before execution |
| Sub-agent isolation | Each container has only its own secrets |
| TradingView webhooks | Verified via shared secret header; delivered via nginx reverse proxy on port 80 |
| Single ORB rule | `validate_orb_entry()` in `backtester/filters.py` — shared by EOD sim and live Alpaca path, structural divergence impossible |
| Audit trail | `mi_audit_log` DB table — advisor calls, theme changes, exclusions, ORB events; queryable from Telegram |
| Secrets | Env vars only, never in code or logs |

---

## Backlog / Upgrade Path

### Recently completed (April 2026)
- ✅ **9M EP system** — parallel LLM-free EP track (Pradeep Bonde "9M" tactic). Intraday scan, sugar baby EOD sweep, Day 2 ORB auto-entry, evening briefing section, outcome tracking, backtest script (`scripts/backtest_9m_ep.py`)
- ✅ Correlation clustering — BFS connected components on beta-adjusted returns, fed into theme discovery as early signals (`show clusters`)
- ✅ Validation cooldowns — 14-day re-assignment ban after validation removal; `show cooldowns`, `bypass cooldown TICKER`
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

The critical path to live trading: **P2 → P3 → P4 → P6 → live**. Everything else adds independent value.

| # | Item | Why now |
|---|---|---|
| P1 | **Fix X/Twitter RS leaders tweet** | Broken — half of nightly distribution silently failing |
| P2 | **MODERATE EP recap in morning briefing** | HIGHs fire real-time; MODERATEs vanish. One could be the best trade of the day. Single DB query. |
| P3 | **Paper trading validation report** | Gate before real money — win rate / avg-R by regime, catalyst type, theme stage over full history |
| P4 | **EP outcome table** | "How did last week's EPs do?" Already have `mi_signal_outcomes` — mostly a formatter. Makes scoring calibration visible. |
| P5 | **Theme conviction display** | Days active + consecutive Accelerating days on every theme line. Tells you "3-week run" vs. "flipped yesterday." One column addition. |
| P6 | **Trading journal** | Log your own trades ("Bought NVDA at 142"). Win rate by regime/setup accumulates over time — start now so data builds. |
| P7 | **"What to watch today" pregame** | On-demand morning synthesis: regime + Accelerating themes + open EPs + tracked stocks near MAs. More compact than the scheduled brief, available after open when the brief is stale. |
| P8 | **Earnings calendar** | Flag when RS leaders / theme stocks report that week. Holding through earnings unknowingly is a real risk. yfinance has next earnings date already. |
| P9 | **Trade postmortem command** | `postmortem TICKER` — joins EP score/catalyst, entry/stop timeline, regime, theme context, and news into one narrative. Turns failed (and winning) trades into structured learning. Most data already in DB; hardest part is intraday news for past dates. Most useful after P4 surfaces which trades to review. |
| P10 | **Watchlist price alerts** | "Alert me when NVDA breaks 140." Scheduled price check, high daily utility. |
| P11 | **EPS estimates** | Forward consensus + surprise%. Data source TBD (Alpha Vantage free tier). Lower priority than earnings date. |
| P12 | **Sector rotation view** | 4-week RS trend by sector/theme — "is money rotating from semis to defense?" Query against existing `mi_stock_scores.sector`. |
| P13 | **Theme constituent churn detection** | Flag stocks entering/exiting a theme 2+ times in 10 days — oscillating members that need permanent exclusion. |
| P14 | **Weekend "what to watch this week" briefing** | Saturday morning synthesis: regime trend + momentum themes + EP setups to watch. Lower urgency — already queryable on demand. |
| P15 | **Correlation clustering** | Early sub-theme discovery before RS leaders emerge. Highest alpha, highest complexity. Build after feedback loop is working. |
| P16 | **Live trading** | Flip `LIVE_TRADING_ENABLED=true` after P3 validation report is solid and regime improves from Crisis. |
