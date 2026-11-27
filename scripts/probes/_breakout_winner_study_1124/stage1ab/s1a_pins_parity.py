"""Stage 1a: assert prereg sha, record+assert the pin (commit + file sha256s of 1.1), re-run the 11-01 parity stage at it."""
import json, sys
from common import *
assert_prereg()
head = git("rev-parse", "HEAD")
dirty = git("status", "--porcelain", "--untracked-files=no")
pins = {"prereg_sha256": PREREG_SHA, "commit": head, "tracked_tree_clean": dirty == "", "files": {}, "extra_files": {}}
bad = []
for f in PIN_FILES + EXTRA_PIN_FILES:
    disk = sha256(REPO / f)
    blob = git("show", f"HEAD:{f}")
    import hashlib
    blob_sha = hashlib.sha256(subprocess.run(["git", "-C", str(REPO), "show", f"HEAD:{f}"], capture_output=True, check=True).stdout).hexdigest()
    (pins["files"] if f in PIN_FILES else pins["extra_files"])[f] = disk
    if disk != blob_sha:
        bad.append(f)
pins["disk_equals_HEAD_blob_all"] = not bad
pins["mismatch"] = bad
(HERE / "pins.json").write_text(json.dumps(pins, indent=1) + "\n")
print(f"PINS commit {head} tracked-tree-clean={dirty == ''} files={len(PIN_FILES)}+{len(EXTRA_PIN_FILES)} mismatches={bad}")
assert dirty == "" and not bad, "pin assertion failed"
import v1_replay as R
r = R.run_parity(HERE, )   # writes HERE/parity.txt
print("PARITY bad =", r["bad"])
(HERE / "1a_result.json").write_text(json.dumps({"pins_ok": True, "parity_bad": r["bad"]}) + "\n")
sys.exit(1 if r["bad"] else 0)
