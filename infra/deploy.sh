#!/usr/bin/env bash
# ============================================================
# Apollo VPS Deploy Script
# Run from your local machine: ./infra/deploy.sh
#
# Prerequisites:
#   - VPS reachable via SSH (configure VPS_HOST below or in env)
#   - Tailscale installed on VPS
#   - Docker + Docker Compose installed on VPS
#   - .env file on VPS at $REMOTE_DIR/.env
# ============================================================

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
VPS_HOST="${VPS_HOST:-apollo-vps}"        # SSH host alias or IP
VPS_USER="${VPS_USER:-ubuntu}"
REMOTE_DIR="${REMOTE_DIR:-/opt/apollo}"
COMPOSE_FILE="docker/docker-compose.prod.yml"

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[deploy]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
err()  { echo -e "${RED}[error]${NC} $*"; exit 1; }

# ── Checks ────────────────────────────────────────────────────────────────────
log "Checking prerequisites..."

command -v rsync >/dev/null 2>&1 || err "rsync is required"
command -v ssh >/dev/null 2>&1 || err "ssh is required"

# Ensure we're in the project root
[[ -f "main.py" ]] || err "Run this script from the Apollo project root directory"

# ── Sync code ─────────────────────────────────────────────────────────────────
log "Syncing code to ${VPS_USER}@${VPS_HOST}:${REMOTE_DIR}..."

rsync -avz --delete \
    --exclude='.git' \
    --exclude='.env' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.egg-info' \
    --exclude='.venv' \
    --exclude='audit.log' \
    ./ "${VPS_USER}@${VPS_HOST}:${REMOTE_DIR}/"

log "Code synced"

# ── Deploy on remote ──────────────────────────────────────────────────────────
log "Deploying on remote..."

ssh "${VPS_USER}@${VPS_HOST}" bash << EOF
    set -euo pipefail
    cd "${REMOTE_DIR}"

    echo "--- Pulling/building images ---"
    docker compose -f ${COMPOSE_FILE} build --pull

    echo "--- Rolling restart (zero-downtime for stateless services) ---"
    docker compose -f ${COMPOSE_FILE} up -d --remove-orphans

    echo "--- Cleaning up old images ---"
    docker image prune -f

    echo "--- Checking service health ---"
    sleep 5
    docker compose -f ${COMPOSE_FILE} ps
EOF

log "Deploy complete!"
log ""
log "Check logs: ssh ${VPS_USER}@${VPS_HOST} 'docker compose -f ${REMOTE_DIR}/${COMPOSE_FILE} logs -f orchestrator'"
