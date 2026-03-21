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
│  theme clustering, regime     TradingView webhooks              │
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
- **Deduplication:** Overlapping themes auto-merged (Jaccard ≥ 0.6 or ticker subset). Sector-level caps prevent theme proliferation (e.g. max 2 oil/gas themes, biotech excluded).
- **Trimmed mean scoring:** Theme RS composite drops bottom 20% of constituents — resists outlier drag from 1-2 weak stocks in an otherwise strong theme

### EP Detection

MAGNA53 scoring (Pradeep Bonde / Kullamägi methodology).

- **Inputs:** Gap %, relative volume, catalyst quality (Claude), neglect factor, float, regime multiplier
- **HIGH (≥85):** Immediate Telegram alert during pre-market scan
- **MODERATE (≥65):** Shown in morning briefing
- **Gemini cross-validation:** When Claude + Gemini agree on catalyst → 1.2x confidence multiplier
- **Scan schedule:** 7:00–9:30 AM ET, every 5 minutes

### Market Regime

| Label | EP Threshold | Meaning |
|---|---|---|
| Bull | ≥70 | Standard criteria |
| Choppy | ≥80 | Raise your bar |
| Correcting | ≥85 | Exceptional setups only |
| Crisis | ≥90 | Very selective |

Signals: SPY/QQQ vs 50MA + 200MA, VIX, breadth (% stocks above 40MA), +/-4% ratio (10-day rolling).

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

---

## Daily Schedule

| Time (ET) | Time (PT) | What |
|---|---|---|
| 4:30 PM | 1:30 PM | Data pull — RS engine + regime + themes (right after close) |
| 8:00 PM | 5:00 PM | Evening briefing → Telegram |
| 7:00 AM | 4:00 AM | EP scan starts; HIGH alerts fire in real-time |
| 9:00 AM | 6:00 AM | Morning briefing → Telegram |
| 9:35 AM | 6:35 AM | EP scan stops |

---

## Data Sources

| Source | Used For | Tier |
|---|---|---|
| Polygon.io | Price history, RS engine, EP gap data | Starter ($29/mo) |
| yfinance | Company profile, sector, analyst ratings, news | Free |
| Tavily | EP catalyst news search, theme confirmation | Free/Pro |
| Anthropic | Orchestrator, catalyst classification, theme clustering | Pay-per-use |
| Gemini | EP catalyst cross-validation | Free (gemini-1.5-flash-8b) |
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
│       └── backtest_ep.py           # EP backtest against historical dates
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
| Irreversible actions | YES/NO confirmation gate before execution |
| Sub-agent isolation | Each container has only its own secrets |
| TradingView webhooks | Verified via shared secret header |
| Audit trail | Append-only `audit.log` — every action logged |
| Secrets | Env vars only, never in code or logs |

---

## Backlog / Upgrade Path

**Highest leverage (Polygon Starter now active):**
- Real T2108 breadth (% stocks above 50MA) from full universe
- Full Pradeep Market Monitor (50%+ 1M count, 25%+ 1Q count, consecutive breakdown tracking)
- Correlation clustering — find stocks moving together before they're RS leaders

**Morning briefing enrichments:**
- ✅ Futures / overnight moves
- ✅ Economic calendar
- Earnings calendar for tracked stocks
- MODERATE EP recap

**Fundamentals:**
- EPS estimates (next quarter consensus + surprise%) via Alpha Vantage free tier — see backlog
