#!/usr/bin/env bash
# #146 unpark - DEPLOY-TIME check, run right after `bash scripts/deploy.sh market-agent` and BEFORE verify_live.sql.
#
# Why it exists: every SQL check in verify_live.sql reads what the scan WROTE. A stale image (the deploy shipped the wrong
# branch, or the container did not recreate) writes the OLD rule's rows - no stamp, no new path - and the SQL then reads
# as a quiet day, which is also what the working code reads on a quiet day. This asks the RUNNING container what rule it
# carries, which a stale image cannot fake. Read-only: it imports a module and prints.
#
#   bash scripts/probes/_146_unpark/verify_deploy.sh               # prod (container apollo-market)
#   HOST=... CONTAINER=... bash scripts/probes/_146_unpark/verify_deploy.sh
#   LOCAL=1 bash scripts/probes/_146_unpark/verify_deploy.sh       # self-test: the same assertion on THIS checkout
#                                                                  # (proves the check passes on the change and fails on a
#                                                                  # tree without it - verify_deploy_selftest.out)
#
# PASS: the licence tuple has exactly the three entries and the bucket vocabulary matches. FAIL (exit 1): anything else -
# including an AttributeError, which is what the pre-#146 image prints.
set -uo pipefail

HOST="${HOST:-apollo@87.99.134.162}"
CONTAINER="${CONTAINER:-apollo-market}"      # the intelligence-role container (docker/docker-compose.prod.yml container_name)
EXPECT="3 (('COILED', 'coiled'), ('TIGHTENING', 'tightening'), ('TRIGGERED', 'retrigger')) ('coiled', 'tightening', 'retrigger')"

PY='from agents.market_intelligence import flag_detector as f; print(len(f._TRIGGER_LICENCE), f._TRIGGER_LICENCE, f.TRIGGERED_FROM_BUCKETS)'
if [ "${LOCAL:-}" = "1" ]; then
  cd "${REPO:-$(dirname "$0")/../../..}" || exit 2            # REPO=<dir>: point the self-test at another checkout
  got="$(PYTHONPATH=. "${PYTHON:-python3}" -c "$PY" 2>&1 | tail -1)"
  CONTAINER="(local checkout)"
else
  got="$(ssh "$HOST" "docker exec $CONTAINER python -c \"$PY\"" 2>&1 | tail -1)"
fi

echo "container: $CONTAINER"
echo "expected : $EXPECT"
echo "got      : $got"
if [ "$got" = "$EXPECT" ]; then
  echo "PASS - the running image carries the #146 licence"
  exit 0
fi
echo "FAIL - the running image does NOT carry the #146 licence (stale image, wrong branch deployed, or the container did not recreate)"
exit 1
