#!/usr/bin/env bash
# #723 — publish the intraday breadth file to portfolio-app2's `live-breadth` branch.
#
# The intraday job (agents/market_intelligence/breadth_live.py, apollo-market) writes
# logs/breadth_live/apollo_breadth_live.json every 15 min during the session. The container has
# no git, no ssh and no deploy key — the `github-p2` alias and the apollo_export_deploy key live on
# the HOST, where the nightly export (auto_export_snapshots.sh) already pushes from. So this script
# runs on the host, from a cron line that fires every minute, and is IDEMPOTENT: it hashes the live
# file, compares it with the last push recorded in push_status.json, and pushes only on a change.
#
# How it publishes: git PLUMBING only (hash-object → mktree → commit-tree with NO parent → push
# --force to refs/heads/live-breadth). The branch always holds exactly ONE commit with exactly ONE
# file, so its history never grows; the clone's checkout, index and HEAD are never touched, and
# nothing here names the dashboard's default branch — the branch Streamlit Cloud reloads on.
#
# Status: push_status.json {ok, at, blob, commit, error} beside the live file. The intraday job
# reads it on its next refresh and audits a push that failed or never happened (the retry is the
# next cron tick — nothing to do by hand).
#
# Host cron (every minute; the script exits at once when there is nothing new):
#   * * * * * /home/apollo/apollo_the_wise/scripts/push_breadth_live.sh >> /home/apollo/apollo_the_wise/logs/push_breadth_live.log 2>&1
set -uo pipefail

APOLLO="${APOLLO_DIR:-/home/apollo/apollo_the_wise}"
DEST="${EXPORT_DIR:-/home/apollo/portfolio-app2-export}"
LIVE_DIR="${BREADTH_LIVE_DIR:-$APOLLO/logs/breadth_live}"
LIVE_NAME=apollo_breadth_live.json
LIVE="$LIVE_DIR/$LIVE_NAME"
STATUS="$LIVE_DIR/push_status.json"
BRANCH="${BREADTH_LIVE_BRANCH:-live-breadth}"
REMOTE="${BREADTH_LIVE_REMOTE:-origin}"

# Nothing written yet today (or ever): nothing to publish.
[ -s "$LIVE" ] || exit 0

cd "$DEST" || exit 1

write_status() {  # ok at blob commit error
  local tmp="$STATUS.tmp"
  printf '{"ok": %s, "at": "%s", "blob": "%s", "commit": "%s", "error": "%s"}\n' \
    "$1" "$2" "$3" "$4" "$(printf '%s' "$5" | tr -d '"\\' | tr '\n' ' ' | cut -c1-300)" > "$tmp" \
    && mv -f "$tmp" "$STATUS"
}

# The git blob id of the live file is the change detector: same bytes => same id => nothing to do.
blob="$(git hash-object -w -- "$LIVE")" || { echo "push-breadth-live: hash-object failed" >&2; exit 1; }
if [ -f "$STATUS" ] && grep -q "\"blob\": \"$blob\"" "$STATUS" && grep -q '"ok": true' "$STATUS"; then
  exit 0
fi

now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
tree="$(printf '100644 blob %s\t%s\n' "$blob" "$LIVE_NAME" | git mktree)" \
  || { write_status false "$now" "$blob" "" "mktree failed"; exit 1; }
# commit-tree with no -p: an ORPHAN commit — the one commit the branch will hold.
commit="$(git commit-tree "$tree" -m "live breadth $now")" \
  || { write_status false "$now" "$blob" "" "commit-tree failed"; exit 1; }

err="$(git push -q --force "$REMOTE" "$commit:refs/heads/$BRANCH" 2>&1)"
rc=$?
if [ "$rc" -eq 0 ]; then
  write_status true "$now" "$blob" "$commit" ""
  echo "push-breadth-live: $now published $blob as $commit on $BRANCH"
else
  write_status false "$now" "$blob" "$commit" "$err"
  echo "push-breadth-live: $now push FAILED ($err)" >&2
  exit 1
fi
