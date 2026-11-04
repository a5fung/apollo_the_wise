#!/usr/bin/env bash
# #194 — daily auto-export: regenerate the dashboard snapshots (themes + trades + funnel, and since #719
# the guarded market-breadth one) and push them to the portfolio-app2 repo, so the Streamlit dashboards
# stay fresh without a manual regen. The first three are all-or-nothing (any one failing aborts the push);
# the breadth export is guarded so its failure never blocks them.
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
# #589 (2026-09-07): the funnel page's snapshot was hand-made and uncommitted — the same
# ad-hoc-then-silently-stale failure export_trades_snapshot.sql exists to prevent. Joined here.
docker exec -i "$PG" psql -U apollo -d apollo -A -t -X -f - < "$APOLLO/scripts/export_funnel_snapshot.sql" > apollo_funnel_snapshot.json

# Sanity: both must be non-trivial JSON, else abort WITHOUT pushing (never publish a truncated/empty snapshot).
for f in apollo_themes_snapshot.json apollo_trades_paper.json apollo_funnel_snapshot.json; do
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
BREADTH_OK=0
rm -f "$BREADTH.tmp"
if docker exec -i "$PG" psql -U apollo -d apollo -A -t -X -v ON_ERROR_STOP=1 -f - \
     < "$APOLLO/scripts/export_breadth_snapshot.sql" > "$BREADTH.tmp" \
   && [ "$(wc -c < "$BREADTH.tmp")" -ge 200 ]; then
  mv -f "$BREADTH.tmp" "$BREADTH"
  BREADTH_OK=1
else
  echo "auto-export: breadth export FAILED or truncated ($(wc -c < "$BREADTH.tmp" 2>/dev/null || echo 0) bytes);" \
       "keeping the last published $BREADTH — the other three snapshots continue." >&2
  rm -f "$BREADTH.tmp"
fi

SNAPSHOTS="apollo_themes_snapshot.json apollo_trades_paper.json apollo_funnel_snapshot.json"
if [ "$BREADTH_OK" = 1 ]; then SNAPSHOTS="$SNAPSHOTS $BREADTH"; fi

# `git status --porcelain`, not `git diff --quiet`: the breadth file's FIRST publish is a new,
# untracked file, which `git diff` does not see.
# shellcheck disable=SC2086  # SNAPSHOTS is a space-separated list of fixed names
if [ -z "$(git status --porcelain -- $SNAPSHOTS)" ]; then
  echo "auto-export: no snapshot change — nothing to push."
else
  # shellcheck disable=SC2086
  git add $SNAPSHOTS
  git commit -q -m "auto-export dashboard snapshots $(date -u +%Y-%m-%dT%H:%MZ)"
  git push -q origin "$BR"
  echo "auto-export: pushed updated snapshots to $BR."
fi
