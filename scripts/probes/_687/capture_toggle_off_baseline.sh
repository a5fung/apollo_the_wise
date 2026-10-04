#!/usr/bin/env bash
# #687 cut-back round — re-capture tests/fixtures/687_toggle_off_main_baseline.json.
#
# Runs tests/_convergence_687_harness.py inside a TEMPORARY `git worktree` of the pinned main
# baseline (re-pinned 2026-10-04 to 4e454395, the origin/main ruling (a) is built on — ruling (i)
# merged; 76e2ce4b for ruling (i), 8e1329f0 for ruling (iii) and 97b08d51, the pre-#687 main, before
# that), records the log, and removes the worktree. (`git archive <sha> | tar -x` into a scratch dir is an equivalent source
# tree — the 2026-10-04 capture was made that way from an isolated worktree.)
# tests/test_687_toggle_off_convergence.py then runs the same harness on the current tree and asserts
# it matches this log except the named allow-list.
#
# Re-run it whenever the harness changes (the fixture stores the harness's sha256 and the test
# refuses a mismatch). Usage: bash scripts/probes/_687/capture_toggle_off_baseline.sh [<sha>]
set -euo pipefail
BASE="${1:-4e4543957c1be082ebae59b46698ba8d9420c67b}"
REPO="$(git rev-parse --show-toplevel)"
TMP="$(mktemp -d)"
cleanup() {
  git -C "$REPO" worktree remove --force "$TMP/base" >/dev/null 2>&1 || true
  rm -rf "$TMP"
}
trap cleanup EXIT
git -C "$REPO" worktree add --detach "$TMP/base" "$BASE" >/dev/null 2>&1
cp "$REPO/tests/_convergence_687_harness.py" "$TMP/base/tests/"
(cd "$TMP/base" && "${PYTHON:-python3}" tests/_convergence_687_harness.py --out "$TMP/raw.json")
"${PYTHON:-python3}" - "$TMP/raw.json" "$BASE" "$REPO" <<'PY'
import hashlib
import json
import sys

raw, base, repo = sys.argv[1:]
harness = f"{repo}/tests/_convergence_687_harness.py"
out = {
    "baseline_sha": base,
    "harness_sha256": hashlib.sha256(open(harness, "rb").read()).hexdigest(),
    "captured_by": "scripts/probes/_687/capture_toggle_off_baseline.sh",
    "scenarios": json.load(open(raw)),
}
with open(f"{repo}/tests/fixtures/687_toggle_off_main_baseline.json", "w") as f:
    f.write(json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
PY
echo "baseline captured from ${BASE} (worktree removed)"
