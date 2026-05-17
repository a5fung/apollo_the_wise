# Apollo Setup Guide

> Complete walkthrough from zero to a running assistant on Telegram.

---

## Quick start

Have your API keys ready (see Step 1 below), then:

```bash
bash setup.sh   # one-time setup: installs deps, prompts for credentials, starts Docker
bash start.sh   # every time after that: starts Docker + Apollo in one command
```

The rest of this guide explains what each step does and covers optional integrations (TradingView, Alpaca).

---

## Before you start — terminal on Windows

All commands in this guide use Unix shell syntax. On Windows, run them in **Git Bash** (installed with Git for Windows), not in Command Prompt or PowerShell.

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.12+ | `python --version` to check |
| Docker Desktop | Latest | Required for Postgres + Redis |
| Git | Any | Already done if you cloned this |
| Git Bash | Any | Comes with Git for Windows — use this as your terminal |

---

## Step 1 — Get your API keys

You'll need accounts/keys from four services. All are free or low-cost.

### 1a. Telegram Bot Token

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Choose a name (e.g. `Apollo`) and a username (e.g. `my_apollo_bot`)
4. BotFather gives you a token like `7123456789:AAFxxx...` — save it

**Your Telegram user ID** (so Apollo only responds to you):
1. Message **@userinfobot** on Telegram
2. It replies with your numeric ID (e.g. `123456789`)

### 1b. Anthropic API Key

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. API Keys → Create Key
3. Save it — starts with `sk-ant-...`

### 1c. Perplexity API Key (catalyst news search)

1. Go to [perplexity.ai/api](https://perplexity.ai/api) → Sign up
2. Dashboard → API Keys → copy your key (starts with `pplx-`)

### 1d. Polygon.io API Key (market data)

1. Go to [polygon.io](https://polygon.io) → sign up for Starter ($29/mo)
2. Dashboard → API Keys → copy your key

### 1e. Alpaca API Keys (dual-account architecture)

Apollo runs ONE container that subscribes to BOTH Alpaca paper + live accounts simultaneously. Strategies route per their `mi_strategies.phase` (shadow / paper / live). You need separate API key pairs for each.

1. Go to [alpaca.markets](https://alpaca.markets) → sign up
2. **Paper account** — Dashboard → Paper Trading → Generate API keys → save `API Key` + `Secret Key` (these become `ALPACA_PAPER_API_KEY` / `ALPACA_PAPER_SECRET_KEY`)
3. **Live account** (optional for dev / single-account opt-out) — Dashboard → Live → Generate → save (these become `ALPACA_LIVE_API_KEY` / `ALPACA_LIVE_SECRET_KEY`)

**Single-account opt-out**: if you only want paper trading, set `ENABLE_LIVE_MODE=false` in `.env` — only the paper key pair is required. Strategies at `phase='live'` are blocked.

**Legacy fallback** (one deploy cycle only): if you have an old `.env` with `ALPACA_API_KEY` / `ALPACA_SECRET_KEY`, those are auto-remapped to `ALPACA_PAPER_*` at boot. Migrate to the new variable names when convenient — the fallback will be removed after dual-mode is stable.

### 1f. Generate random secrets

You need two random strings for internal security. Run this in your terminal:

```bash
python -c "import secrets; print(secrets.token_hex(32)); print(secrets.token_hex(32))"
```

Save the two outputs — one is your `INTERNAL_API_SECRET`, one is your `TRADINGVIEW_WEBHOOK_SECRET`.

---

## Step 2 — Configure environment

In your terminal, navigate to the project root first:
```bash
cd /c/Users/lasto/Documents/Apollo_Assistant   # adjust path if different
```

Then copy the example env file:
```bash
cp .env.example .env
```

Open `.env` and fill in these values (the ones with ⚠️ are required to start):

```env
# ⚠️ Required
TELEGRAM_BOT_TOKEN=7123456789:AAFxxx...
TELEGRAM_ALLOWED_USER_IDS=123456789        # Your Telegram user ID from @userinfobot
ANTHROPIC_API_KEY=sk-ant-...
POSTGRES_PASSWORD=pick_a_strong_password
REDIS_PASSWORD=pick_another_password
INTERNAL_API_SECRET=<first random string>
TRADINGVIEW_WEBHOOK_SECRET=<second random string>

# Market data + catalyst research
POLYGON_API_KEY=...                        # Required
PERPLEXITY_API_KEY=pplx-...                # Required — catalyst news + cross-validation
FMP_API_KEY=...                            # Optional — fundamentals fallback

# Paper/live trading (Alpaca — dual-account architecture)
ENABLE_LIVE_MODE=false                     # Set true to enable both paper + live; false = paper only
ALPACA_PAPER_API_KEY=...                   # Required
ALPACA_PAPER_SECRET_KEY=...                # Required
ALPACA_LIVE_API_KEY=...                    # Required ONLY when ENABLE_LIVE_MODE=true
ALPACA_LIVE_SECRET_KEY=...                 # Required ONLY when ENABLE_LIVE_MODE=true
ALPACA_DATA_FEED=iex                       # "sip" requires Algo Trader Plus ($99/mo)
LIVE_TRADING_ENABLED=false                 # Master kill switch (disables ALL submits)
```

**Legacy variables**: `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` / `ALPACA_PAPER=true` are auto-remapped to `ALPACA_PAPER_*` at boot for one deploy cycle. Migrate when convenient.

---

## Step 3 — Start infrastructure (Docker)

### 3a. Install Docker Desktop (if you haven't)

1. Download from [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/)
2. Install and launch it — you need to see the Docker whale icon in your taskbar/menu bar before continuing
3. Leave Docker Desktop running in the background whenever you use Apollo

### 3b. Start Postgres and Redis

Open a terminal in the **project root** (`Apollo_Assistant/`) and run:

```bash
cd docker
docker compose up -d postgres redis
```

- `up` = create and start the containers
- `-d` = detached (runs in background, you get your terminal back)
- `postgres redis` = only start these two services for now (the agents start later)

Docker will download the images on first run (~500 MB). This only happens once.

### 3c. Confirm they're healthy

```bash
docker compose ps
```

You should see something like:

```
NAME              STATUS
apollo-postgres   running (healthy)
apollo-redis      running (healthy)
```

Both must say `healthy` before moving on. If they show `starting`, wait 10 seconds and run `docker compose ps` again.

**If Postgres shows `unhealthy`:** check that `POSTGRES_PASSWORD` is set in your `.env` file (Step 2).

### 3d. What these containers are

| Container | What it is | Port |
|---|---|---|
| `apollo-postgres` | Database — stores memory, audit log | 5432 |
| `apollo-redis` | Cache + real-time state | 6379 |

They persist data in Docker volumes (`postgres_data`, `redis_data`) so your data survives restarts.

### Stopping / restarting

These commands must be run from the `docker/` folder (same as where you ran `docker compose up`):

```bash
# Stop (keeps data)
docker compose stop

# Stop and remove containers (keeps data volumes)
docker compose down

# Start again
docker compose up -d postgres redis
```

---

## Step 4 — Run Apollo

### Option A — Local (recommended for first run)

Run these from the **project root** (the `Apollo_Assistant/` folder, not the `docker/` subfolder):

```bash
pip install -r requirements/base.txt
playwright install chromium

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

- `--reload` = auto-restarts when you edit code (remove it in production)
- Keep this terminal open — closing it stops Apollo

You should see:
```
Apollo starting up...
Database ready
Apollo ready
```

### Option B — Full Docker Compose

```bash
cd docker
docker compose up -d
```

This runs the orchestrator + all five sub-agents in containers.

---

## Step 5 — Expose Apollo to Telegram (webhook)

Telegram needs a public HTTPS URL to deliver messages. Two options:

### Option A — ngrok (local dev, easiest)

1. Install ngrok from [ngrok.com/download](https://ngrok.com/download)
2. **Open a new terminal** (leave Apollo running in the first one), then:
```bash
ngrok http 8000
```
3. Copy the `https://xxxx.ngrok-free.app` URL ngrok prints, then add it to `.env`:
```env
WEBHOOK_BASE_URL=https://xxxx.ngrok-free.app
```
4. Restart Apollo: go to the terminal where Apollo is running, press `Ctrl+C`, then run the `uvicorn` command again. Apollo registers the webhook automatically on startup.

### Option B — VPS (production)

```bash
# 1. Set on your VPS:
WEBHOOK_BASE_URL=https://your-domain.com

# 2. Deploy:
./infra/deploy.sh
```

See the [Production Deploy](#production-deploy) section below.

---

## Step 6 — Talk to Apollo

1. Open Telegram and find your bot (the username you gave BotFather)
2. Send `/start`
3. Apollo asks for a name → type your preferred name or `.` to keep "Apollo"
4. Apollo asks for a personality → describe the tone you want, or `.` for the default
5. Done — start chatting

**Try these:**
```
What can you do?
What's the market doing today?
Show top RS leaders
EP alerts today
Themes and stages
RS for CIEN
/trades
```

---

## Step 7 — Set up TradingView alerts (optional)

1. In TradingView, create an alert on any chart
2. Under **Notifications**, enable **Webhook URL**
3. Set the URL to:
   ```
   https://your-domain.com/tradingview/alert?token=YOUR_TRADINGVIEW_WEBHOOK_SECRET
   ```
4. Set the **Message** to JSON, for example:
   ```json
   {"ticker": "{{ticker}}", "exchange": "{{exchange}}", "price": "{{close}}", "alert_name": "{{plot_0}}", "message": "Your custom message"}
   ```
5. Fire the alert — Apollo pushes a notification to your Telegram instantly

---

## Bot Commands Reference

Once running, type `/` in Telegram to see the full command menu:

| Command | Description |
|---|---|
| `/help` | Full capabilities + command reference |
| `/agents` | Live status of all sub-agents (green/red) |
| `/status` | System health — DB, Redis, all agents |
| `/setup` | Change the assistant's name or personality |
| `/memory` | View everything Apollo remembers about you |
| `/audit` | Recent action log (what actions were taken) |
| `/start` | Re-run the welcome / onboarding flow |

---

## Troubleshooting

**Apollo doesn't respond to Telegram messages**
- Check the webhook is set: `curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo`
- Make sure `WEBHOOK_BASE_URL` is set and the URL is publicly reachable over HTTPS

**"Unauthorized" error in Telegram**
- Confirm your Telegram user ID is in `TELEGRAM_ALLOWED_USER_IDS` in `.env`

**Database errors on startup**
- Make sure `docker compose up -d postgres` is running and healthy
- Check `POSTGRES_PASSWORD` matches in `.env`

**Market agent shows 🔴 in `/agents`**
- In local dev, start the market agent in a second terminal: `bash start_market.sh`
- Or run directly: `uvicorn agents.market_intelligence.agent:app --port 8006`

**TradingView webhook returning 401**
- Verify the `?token=` in your TradingView webhook URL matches `TRADINGVIEW_WEBHOOK_SECRET` in `.env`

---

## Production Deploy

### VPS requirements
- Ubuntu 22.04+ recommended
- 2 vCPU / 4 GB RAM minimum
- Docker + Docker Compose installed
- Tailscale installed (for secure access)
- A domain pointing to the VPS (for HTTPS)

### Nginx + SSL (example)
```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Deploy
```bash
# Set your VPS SSH host (or add an alias in ~/.ssh/config)
export VPS_HOST=your-vps-ip
export VPS_USER=ubuntu          # default
export REMOTE_DIR=/opt/apollo   # default

./infra/deploy.sh
```

The script will:
1. `rsync` the project to your VPS (skipping `.env`, `.git`, caches)
2. Build/pull Docker images remotely
3. Do a rolling restart with `docker compose up -d`
4. Print service health

**Check logs after deploy:**
```bash
ssh ubuntu@your-vps-ip 'docker compose -f /opt/apollo/docker/docker-compose.prod.yml logs -f orchestrator'
```

### VPS `.env` file

The deploy script does **not** copy your `.env` — you must create it on the VPS manually the first time:

```bash
ssh ubuntu@your-vps-ip
sudo mkdir -p /opt/apollo
nano /opt/apollo/.env   # paste your filled-in .env here
```

### Production resource summary

| Service | Memory limit |
|---|---|
| Postgres | 2 GB |
| Redis | 512 MB |
| Orchestrator | 1 GB |
| Market Intelligence agent | 1 GB |
| **Total** | ~4.5 GB (CPX21 4 GB VPS works) |

### Re-deploying after code changes

Just run `./infra/deploy.sh` again — it syncs only changed files and does a rolling restart, so there is minimal downtime.

---

## Updating Apollo

```bash
git pull
./infra/deploy.sh   # for VPS
# or
docker compose -f docker/docker-compose.prod.yml up -d --build   # on VPS directly
```

---

## Uninstalling / removing data

```bash
# Stop everything
docker compose -f docker/docker-compose.yml down

# Remove all data volumes (irreversible — deletes Postgres + Redis data)
docker compose -f docker/docker-compose.yml down -v
```

---

*That's everything. If you hit a problem not covered here, open the logs (`docker compose logs -f`) and check the Troubleshooting section above.*
