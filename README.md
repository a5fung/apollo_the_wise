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
- **5:00 PM PT (8 PM ET)** — Evening briefing: full EOD review package. Sent after close when you sit down to review charts.
- **6:00 AM PT (9 AM ET)** — Morning briefing: EP recap + regime context, 30 min before open.
- HIGH EP alerts fire in real-time during pre-market scan (4–6:30 AM PT). No waiting for briefing.

### Paper Trading (Alpaca)

Apollo runs semi-automated paper trading via Alpaca to validate EP signals with real market execution.

| Feature | How it works |
|---|---|
| ORB entry (pre-market HIGHs) | Pre-market HIGH alerts subscribe to Alpaca bar WebSocket. First bar close at 9:30:59 → order placed at 9:31:00 |
| ORB entry (post-open HIGHs) | 9:31 AM scan finds new HIGHs → ORB order placed inline |
| ORB fallback | If bar stream misses a pre-market HIGH, 9:31 scan fires `_orb_monitor_job` as safety net |
| Stop width validation | `validate_orb_entry(orb_high, orb_low, atr_14)` — single shared rule used by both EOD sim and live Alpaca path. ORB range must be ≤ 1.5x ATR-14. |
| M&A hard filter | Definitive agreement / tender offer / going-private catalysts classified as `mna` → hard skip before scoring |
| 11 AM cutoff | Re-entry after stop-out only before 11 AM ET — after that, the trade is closed |
| Auto-confirm | Paper mode bypasses Telegram confirmation — trades execute automatically |
| Day 2+ management | 4:45 PM — SMA 10/20 trailing stops, partial exits (1/3 on Day 3-5), breakeven activation |
| Position tracking | `/trades` command — entry/stop once + per-attempt timestamps (`#1 09:31 → 10:00 (stop_hit) P&L $-635`) |
| Safeguards | Max 4 positions, 2% daily loss limit, 3-loss circuit breaker |
| Morning stops | 9:35 AM — GTC stop orders refreshed for Day 2+ positions |
| EOD cleanup | 4:05 PM — cancel unfilled entries, sync positions with Alpaca |

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

### EP Detection

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
| 7:00 AM | 4:00 AM | EP scan starts; HIGH alerts fire in real-time + bar stream subscriptions |
| 9:00 AM | 6:00 AM | Morning briefing → Telegram |
| 9:31 AM | 6:31 AM | Post-open EP scan; ORB orders placed for new HIGHs |
| 9:35 AM | 6:35 AM | Bar stream cleanup; morning stop refresh for Day 2+ positions |
| 9:35–10:00 AM | 6:35–7:00 AM | Fill checker — poll Alpaca for order fills |
| 10:00 AM | 7:00 AM | EP scan stops |
| 4:05 PM | 1:05 PM | EOD cleanup — cancel unfilled orders, sync positions |
| 4:30 PM | 1:30 PM | Data pull — RS engine + regime + themes (right after close) |
| 4:45 PM | 1:45 PM | Live position update — SMA trail, partials, stop updates + daily summary |
| 8:00 PM | 5:00 PM | Evening briefing → Telegram |

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
│       ├── regime.py                # Market regime engine
│       ├── briefing.py              # Evening + morning briefing formatters
│       ├── theme_engine.py          # Theme discovery + deduplication + lifecycle
│       ├── scheduler.py             # APScheduler jobs (4:30pm data, 8pm evening, 9am morning)
│       ├── fundamentals.py          # O'Neil fundamentals + get_fundamentals_batch()
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

### Next up

**P6 — Trading Journal**
You tell Apollo: "Bought NVDA breakout at 142" / "Stopped out of SMCI at -7%". Apollo stores execution → tracks win rate by EP tier, regime, theme stage, setup type. Over time surfaces patterns: "Your Bull regime EP trades: 68% win rate. Choppy: 41%." Builds on automated outcome tracking (P8) by adding your actual execution data.

**P7 — EPS Estimates**
Next-quarter consensus + surprise % surfaced in two places: morning briefing earnings calendar (flag RS leaders / theme stocks reporting that day/week) and on-demand fundamentals command. Via Alpha Vantage free tier or yfinance.

**P10 — Observability / Reasoning Traces**
"Why did Apollo surface this?" — add reasoning traces to alerts and briefing entries.
- EP alert: "gap 12%, rvol 4.2x, game_changer catalyst, RS 87, Accelerating theme"
- Theme: "Moved to Accelerating: 4/5 constituents RS 80+"
- RS leader: "RS jumped 65→91 in 2 weeks (velocity leader)"

**Morning briefing enrichments**
- MODERATE EP recap — HIGHs fire real-time; briefing should recap MODERATEs for manual catalyst check
- Earnings calendar — flag when RS leader or tracked stock reports that day/week
- Pre-market movers in theme stocks — which tracked names are gapping pre-market?

---

### North Star

**Correlation clustering** — Find stocks moving together *before* they're RS leaders. If 4 photonics names show 0.85+ daily return correlation over 2 weeks, that's an early cluster — even if none is top-60 RS yet. Builds bottom-up theme discovery earlier in the cycle. Needs stored daily returns for broader universe (Polygon Starter active).

**Live trading** — Current goal is validating the paper trading system. Once Crisis regime lifts and paper results are consistent, flip `LIVE_TRADING_ENABLED=true` with real money on a small account.
