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
# file, so its history never grows. The branch name is HARD-CODED: no environment variable can point
# this script at the dashboard's default branch (the one Streamlit Cloud reloads on).
#
# Where it works: its OWN bare repo (logs/breadth_live/.push.git, created on first run), never the
# nightly export's clone — the two never share an object store or a ref, so a pusher retry can never
# collide with the nightly's `git fetch` (a contended refs/remotes lock under its `set -e` would have
# cost all four nightly snapshots). The push goes to the remote URL (read once from the nightly
# clone's config, or BREADTH_LIVE_REMOTE), so it updates no tracking ref anywhere. After a successful
# push the objects are pruned — the bare repo stays at a few KB.
#
# One at a time, bounded: the whole run holds an exclusive lock (flock -n; a second run while one is
# in progress exits 0 at once), and the push itself runs under `timeout` (a hung ssh ends after 50 s
# instead of piling one more process onto the host every minute). Both tools are util-linux /
# coreutils on the prod host; where either is missing (a macOS laptop) the script says so once per run
# and carries on without it.
#
# Status: push_status.json {ok, at, blob, commit, error} beside the live file. The intraday job
# reads it on its next refresh, audits a push that failed or never happened, and PAGES at the third
# straight refresh left unpublished (~45 min) — a host cron that was never installed is not silent.
# The retry is the next cron tick — nothing to do by hand.
#
# Host cron (every minute; the script exits at once when there is nothing new):
#   * * * * * /home/apollo/apollo_the_wise/scripts/push_breadth_live.sh >> /home/apollo/apollo_the_wise/logs/push_breadth_live.log 2>&1
set -uo pipefail

APOLLO="${APOLLO_DIR:-/home/apollo/apollo_the_wise}"
DEST="${EXPORT_DIR:-/home/apollo/portfolio-app2-export}"   # read ONLY for the remote URL — never worked in
LIVE_DIR="${BREADTH_LIVE_DIR:-$APOLLO/logs/breadth_live}"
LIVE_NAME=apollo_breadth_live.json
LIVE="$LIVE_DIR/$LIVE_NAME"
STATUS="$LIVE_DIR/push_status.json"
PUSH_GIT="$LIVE_DIR/.push.git"      # this script's own bare repo
LOCK="$LIVE_DIR/.push.lock"
BRANCH=live-breadth                 # hard-coded on purpose: see the header
PUSH_TIMEOUT_S=50                   # under the one-minute cron period

# Nothing written yet today (or ever): nothing to publish. Before the lock, so the quiet path costs nothing.
[ -s "$LIVE" ] || exit 0

# One run at a time: re-exec under flock when it exists (prod); a held lock means a run is in progress.
if [ -z "${PUSH_BREADTH_LIVE_LOCKED:-}" ]; then
  if command -v flock >/dev/null 2>&1; then
    PUSH_BREADTH_LIVE_LOCKED=1 exec flock -n -E 0 "$LOCK" bash "$0" "$@"
  else
    echo "push-breadth-live: flock not found — running unlocked" >&2
  fi
fi

TIMEOUT=()
if command -v timeout >/dev/null 2>&1; then
  TIMEOUT=(timeout -k 5 "$PUSH_TIMEOUT_S")
else
  echo "push-breadth-live: timeout not found — the push runs unbounded" >&2
fi

write_status() {  # ok at blob commit error
  local tmp="$STATUS.tmp"
  printf '{"ok": %s, "at": "%s", "blob": "%s", "commit": "%s", "error": "%s"}\n' \
    "$1" "$2" "$3" "$4" "$(printf '%s' "$5" | tr -d '"\\' | tr '\n' ' ' | cut -c1-300)" > "$tmp" \
    && mv -f "$tmp" "$STATUS"
}

now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# The remote: an explicit URL, else the nightly clone's origin (a config READ — no ref, no lock, no checkout).
REMOTE="${BREADTH_LIVE_REMOTE:-$(git -C "$DEST" config --get remote.origin.url 2>/dev/null)}"
if [ -z "$REMOTE" ]; then
  write_status false "$now" "" "" "no remote: BREADTH_LIVE_REMOTE unset and $DEST has no origin"
  echo "push-breadth-live: no remote URL (BREADTH_LIVE_REMOTE unset, no origin in $DEST)" >&2; exit 1
fi

# Our own bare repo, created on first run.
if [ ! -d "$PUSH_GIT" ]; then
  git -c init.defaultBranch=$BRANCH init -q --bare "$PUSH_GIT" || { echo "push-breadth-live: cannot create $PUSH_GIT" >&2; exit 1; }
fi
export GIT_DIR="$PUSH_GIT"

# The git blob id of the live file is the change detector: same bytes => same id => nothing to do.
blob="$(git hash-object -w -- "$LIVE")" || { echo "push-breadth-live: hash-object failed" >&2; exit 1; }
if [ -f "$STATUS" ] && grep -q "\"blob\": \"$blob\"" "$STATUS" && grep -q '"ok": true' "$STATUS"; then
  exit 0
fi

tree="$(printf '100644 blob %s\t%s\n' "$blob" "$LIVE_NAME" | git mktree)" \
  || { write_status false "$now" "$blob" "" "mktree failed"; exit 1; }
# commit-tree with no -p: an ORPHAN commit — the one commit the branch will hold.
commit="$(git commit-tree "$tree" -m "live breadth $now")" \
  || { write_status false "$now" "$blob" "" "commit-tree failed"; exit 1; }

# (${arr[@]+...}: an empty array is "unbound" to bash 3.2 under set -u — the laptop's bash; prod is bash 5.)
err="$(${TIMEOUT[@]+"${TIMEOUT[@]}"} git push -q --force "$REMOTE" "$commit:refs/heads/$BRANCH" 2>&1)"
rc=$?
if [ "$rc" -eq 0 ]; then
  write_status true "$now" "$blob" "$commit" ""
  echo "push-breadth-live: $now published $blob as $commit on $BRANCH"
  git prune --expire=now 2>/dev/null || true   # nothing here is reachable; the remote holds the commit
else
  [ "$rc" -eq 124 ] && err="push timed out after ${PUSH_TIMEOUT_S}s: $err"
  write_status false "$now" "$blob" "$commit" "$err"
  echo "push-breadth-live: $now push FAILED ($err)" >&2
  exit 1
fi
