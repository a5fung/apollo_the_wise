#!/usr/bin/env bash
# #194 — daily auto-export: regenerate the dashboard snapshots (themes + trades + funnel, and since #719
# the guarded market-breadth one) and push them to the portfolio-app2 repo, so the Streamlit dashboards
# stay fresh without a manual regen. The first three are all-or-nothing (any one failing aborts the push);
# the breadth export is guarded so its failure never blocks them. Since #723 the script ALSO writes the
# live-breadth reference to the host's logs/ first (its own guarded block, not published — see below).
#
# Runs on the prod host (has docker access to apollo-postgres + the apollo_export_deploy key,
# used only for the portfolio-app2 remote via the `github-p2` SSH-config alias — the apollo repo's
# own git auth is untouched). Read-only against prod (SELECT-only export SQL). Pushes only when a
# snapshot actually changed. Version-controlled here; a host cron calls it (see #194).
set -euo pipefail

APOLLO="${APOLLO_DIR:-/home/apollo/apollo_the_wise}"
DEST="${EXPORT_DIR:-/home/apollo/portfolio-app2-export}"
PG="apollo-postgres"

# #723 (2026-11-10): the live-breadth REFERENCE — what the intraday job (breadth_live.py) compares today's
# Alpaca snapshots against (last close, 252-session high/low ending at that close, eligibility, theme and
# group memberships). It is NOT a dashboard snapshot: nothing publishes it, and it runs FIRST — before
# `cd $DEST`, the fetch/reset and the all-or-nothing sanity loop — so a GitHub outage, a failed theme /
# trades / funnel export, or anything else that aborts this script under `set -e` can never leave the
# next session without a fresh reference (which would have the live job refuse all day and page at 10:15).
# Guarded like the breadth block (ON_ERROR_STOP, 300 s statement_timeout, 200-byte floor): a failure
# leaves the previous reference exactly where it was and the script continues to the snapshots. The
# output lands straight at $APOLLO/logs/ — the directory docker-compose.prod.yml bind-mounts into
# apollo-market at /app/logs — written tmp + mv, so the intraday job never reads a half-written file.
# SSoT: docs/architecture/market_breadth_snapshot.md §Live breadth.
REFERENCE_HOST_COPY="${BREADTH_REFERENCE_COPY:-$APOLLO/logs/apollo_breadth_reference.json}"
if mkdir -p "$(dirname "$REFERENCE_HOST_COPY")" \
   && docker exec -i -e PGOPTIONS="-c statement_timeout=300s" "$PG" psql -U apollo -d apollo -A -t -X -v ON_ERROR_STOP=1 -f - \
        < "$APOLLO/scripts/export_breadth_reference.sql" > "$REFERENCE_HOST_COPY.tmp" \
   && [ "$(wc -c < "$REFERENCE_HOST_COPY.tmp")" -ge 200 ]; then
  mv -f "$REFERENCE_HOST_COPY.tmp" "$REFERENCE_HOST_COPY"
else
  echo "auto-export: breadth REFERENCE export FAILED or truncated ($(wc -c < "$REFERENCE_HOST_COPY.tmp" 2>/dev/null || echo 0) bytes);" \
       "keeping the previous $REFERENCE_HOST_COPY — the snapshots continue." >&2
  rm -f "$REFERENCE_HOST_COPY.tmp"
fi

cd "$DEST"
BR="$(git rev-parse --abbrev-ref HEAD)"

# Always start from the current remote state (so a manual/operator push to portfolio-app2 is never clobbered).
git fetch -q origin
git reset -q --hard "origin/$BR"

# The snapshot files this run publishes: the sanity loop checks them and the commit stages them. The
# breadth file (#719) is appended further down only when its guarded export succeeds.
SNAPSHOTS=(apollo_themes_snapshot.json apollo_trades_paper.json apollo_funnel_snapshot.json)

# Regenerate the three snapshots (read-only; the theme SQL carries the #194 e_code ecosystem join).
docker exec -i "$PG" psql -U apollo -d apollo -A -t -X -f - < "$APOLLO/scripts/export_theme_snapshot.sql"  > apollo_themes_snapshot.json
docker exec -i "$PG" psql -U apollo -d apollo -A -t -X -f - < "$APOLLO/scripts/export_trades_snapshot.sql" > apollo_trades_paper.json
# #589 (2026-09-07): the funnel page's snapshot was hand-made and uncommitted — the same
# ad-hoc-then-silently-stale failure export_trades_snapshot.sql exists to prevent. Joined here.
docker exec -i "$PG" psql -U apollo -d apollo -A -t -X -f - < "$APOLLO/scripts/export_funnel_snapshot.sql" > apollo_funnel_snapshot.json

# Sanity: each must be non-trivial JSON, else abort WITHOUT pushing (never publish a truncated/empty snapshot).
for f in "${SNAPSHOTS[@]}"; do
  if [ ! -s "$f" ] || [ "$(wc -c < "$f")" -lt 200 ]; then
    echo "auto-export: ABORT — $f is empty/truncated ($(wc -c < "$f") bytes); not pushing." >&2
    git checkout -q -- . ; exit 1
  fi
done

# #719 (2026-11-04): the Market Breadth page's snapshot. GUARDED, unlike the three above: a
# failure here must NEVER cost the other three their nightly refresh. It writes to a temp file
# first, so on failure the published breadth file (the one `git reset --hard` just restored, or
# none yet) is left exactly as it was and is not committed. ON_ERROR_STOP makes a SQL error a
# non-zero exit (without it psql exits 0 with empty output; the size floor catches that too).
BREADTH=apollo_breadth_snapshot.json
# statement_timeout: a hung breadth query (a lock from a boot-time ALTER, a cold-cache plan) must
# not hold up the other three, which commit after it — it ends as a non-zero exit the guard handles.
# Prod timing and the headroom this cap leaves: docs/architecture/market_breadth_snapshot.md (Cost).
if docker exec -i -e PGOPTIONS="-c statement_timeout=300s" "$PG" psql -U apollo -d apollo -A -t -X -v ON_ERROR_STOP=1 -f - \
     < "$APOLLO/scripts/export_breadth_snapshot.sql" > "$BREADTH.tmp" \
   && [ "$(wc -c < "$BREADTH.tmp")" -ge 200 ]; then
  mv -f "$BREADTH.tmp" "$BREADTH"
  SNAPSHOTS+=("$BREADTH")
else
  echo "auto-export: breadth export FAILED or truncated ($(wc -c < "$BREADTH.tmp" 2>/dev/null || echo 0) bytes);" \
       "keeping the last published $BREADTH — the other three snapshots continue." >&2
  rm -f "$BREADTH.tmp"
fi

# Stage first, then ask the index: `git diff --cached` sees the breadth file's FIRST publish (a new
# file), which a plain `git diff --quiet` would not.
git add -- "${SNAPSHOTS[@]}"
if git diff --cached --quiet; then
  echo "auto-export: no snapshot change — nothing to push."
else
  git commit -q -m "auto-export dashboard snapshots $(date -u +%Y-%m-%dT%H:%MZ)"
  git push -q origin "$BR"
  echo "auto-export: pushed updated snapshots to $BR."
fi
