#!/usr/bin/env bash
# #194 — daily auto-export: regenerate BOTH dashboard snapshots (themes + trades) and push
# them to the portfolio-app2 repo, so the Streamlit dashboards stay fresh without a manual regen.
#
# Runs on the prod host (has docker access to apollo-postgres + the apollo_export_deploy key,
# used only for the portfolio-app2 remote via the `github-p2` SSH-config alias — the apollo repo's
# own git auth is untouched). Read-only against prod (SELECT-only export SQL). Pushes only when a
# snapshot actually changed. Version-controlled here; a host cron calls it (see #194).
set -euo pipefail

APOLLO="${APOLLO_DIR:-/home/apollo/apollo_the_wise}"
DEST="${EXPORT_DIR:-/home/apollo/portfolio-app2-export}"
PG="apollo-postgres"

cd "$DEST"
BR="$(git rev-parse --abbrev-ref HEAD)"

# Always start from the current remote state (so a manual/operator push to portfolio-app2 is never clobbered).
git fetch -q origin
git reset -q --hard "origin/$BR"

# Regenerate both snapshots (read-only; the theme SQL carries the #194 e_code ecosystem join).
docker exec -i "$PG" psql -U apollo -d apollo -A -t -X -f - < "$APOLLO/scripts/export_theme_snapshot.sql"  > apollo_themes_snapshot.json
docker exec -i "$PG" psql -U apollo -d apollo -A -t -X -f - < "$APOLLO/scripts/export_trades_snapshot.sql" > apollo_trades_paper.json

# Sanity: both must be non-trivial JSON, else abort WITHOUT pushing (never publish a truncated/empty snapshot).
for f in apollo_themes_snapshot.json apollo_trades_paper.json; do
  if [ ! -s "$f" ] || [ "$(wc -c < "$f")" -lt 200 ]; then
    echo "auto-export: ABORT — $f is empty/truncated ($(wc -c < "$f") bytes); not pushing." >&2
    git checkout -q -- . ; exit 1
  fi
done

if git diff --quiet; then
  echo "auto-export: no snapshot change — nothing to push."
else
  git add apollo_themes_snapshot.json apollo_trades_paper.json
  git commit -q -m "auto-export dashboard snapshots $(date -u +%Y-%m-%dT%H:%MZ)"
  git push -q origin "$BR"
  echo "auto-export: pushed updated snapshots to $BR."
fi
