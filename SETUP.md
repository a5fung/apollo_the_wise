# Apollo Setup Guide

> Complete walkthrough from zero to a running assistant on Telegram.

---

## Quick start

Have your API keys ready (see Step 1 below), then:

```bash
bash setup.sh   # one-time setup: installs deps, prompts for credentials, starts Docker
bash start.sh   # every time after that: starts Docker + Apollo in one command
```

The rest of this guide explains what each step does and covers optional integrations (calendar, IBKR, TradingView).

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

### 1c. Tavily API Key (for web search — free tier)

1. Go to [tavily.com](https://tavily.com) → Sign up free
2. Dashboard → API Keys → copy your key

### 1d. Generate random secrets

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

# Research / news search (primary)
PERPLEXITY_API_KEY=pplx-...                # Required — get from perplexity.ai/api

# Optional (needed for full agent functionality)
TAVILY_API_KEY=tvly-...                    # Legacy fallback only — not used in main pipeline
GOOGLE_CAL_TOKEN=...                       # See Step 8 for calendar setup
IBKR_CLIENT_PORTAL_URL=https://localhost:5000
```

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
Show me my calendar for this week
Research the best ETFs for long-term investing
What's my IBKR portfolio worth?
Plan a 4-day trip to Tokyo in October
Which lounge can I use at JFK with my Amex Platinum?
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

## Step 8 — Connect Google Calendar (optional)

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project → Enable **Google Calendar API**
3. OAuth 2.0 → Create credentials (Desktop app type)
4. Download `credentials.json` — place it in the **project root** (`Apollo_Assistant/credentials.json`)
5. Run the auth flow from the project root:
   ```bash
   pip install google-auth-oauthlib
   python -c "
from google_auth_oauthlib.flow import InstalledAppFlow
flow = InstalledAppFlow.from_client_secrets_file('credentials.json', ['https://www.googleapis.com/auth/calendar'])
creds = flow.run_local_server(port=0)
import json; print(json.dumps(json.loads(creds.to_json())))
   "
   ```
   A browser window will open — log in and grant access. The terminal will then print a JSON blob.
6. Copy the entire JSON output and set it as `GOOGLE_CAL_TOKEN` in `.env` (on one line, in quotes if it contains spaces)

---

## Step 9 — Connect IBKR (optional)

1. Download and install [IBKR Client Portal Gateway](https://www.interactivebrokers.com/en/trading/ib-api.php)
2. Start the gateway: runs on `https://localhost:5000`
3. Log in via the IBKR mobile app when prompted
4. Set in `.env`:
   ```env
   IBKR_CLIENT_PORTAL_URL=https://localhost:5000
   IBKR_ACCOUNT_ID=your_account_id
   ```
5. Test: `python tests/test_ibkr.py`

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

**Sub-agents show 🔴 in `/agents`**
- In local dev, only the orchestrator runs by default — agents show offline until you start them individually or use `docker compose up -d`
- Run a specific agent: `uvicorn agents.research.agent:app --port 8003`

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
| Finance / Calendar / Research / Travel agents | 512 MB each |
| Browser agent | 2 GB (Playwright) |
| **Total** | ~7 GB (use an 8 GB+ VPS) |

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
