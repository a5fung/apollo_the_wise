#!/usr/bin/env python3
"""BLIND verifier driver (2026-11-03): run the 10-16 recut.py, unchanged, against the PINNED code tree
(git archive 8fca6649 -> scratch) or HEAD, on the full Run-U population or a filtered one.

  python3 repro.py --tree pinned|head --pop full|kept|dropped --tag NAME

Writes everything under this verify folder only: NAME.out (stdout in main()'s --run layout),
NAME/run_rows.tsv + NAME/run_results.json (recut's own dumps), NAME.perarm.json (full-precision R per
trade per arm, for the independent measures in indep.py), NAME.modules.txt (where every module came from).
The open-floor filter used for --pop kept/dropped is THIS folder's own (floor.py), not the 1103 script's.
"""
import argparse
import hashlib
import importlib
import importlib.util
import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout

sys.dont_write_bytecode = True

REPO = "/Users/alvinfung/apollo_the_wise"
V = f"{REPO}/scripts/probes/_runner_recut_1103/verify"
PINNED_TREE = "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/pinned"
PIN_BLOBS = {"agents/market_intelligence/live_fill_counterfactuals.py": "e9098c36",
             "agents/market_intelligence/broker/exit_logic.py": "d5597612",
             "scripts/probes/_bt_replay.py": "727d5f84"}

ap = argparse.ArgumentParser()
ap.add_argument("--tree", choices=["pinned", "head"], required=True)
ap.add_argument("--pop", choices=["full", "kept", "dropped"], required=True)
ap.add_argument("--tag", required=True)
a = ap.parse_args()

root = PINNED_TREE if a.tree == "pinned" else REPO
sys.path.insert(0, root)
for m in ("agents.market_intelligence.broker.exit_logic", "agents.market_intelligence.live_fill_counterfactuals",
          "scripts.probes._bt_replay"):
    importlib.import_module(m)

# load the 10-16 recut.py (its bytes = 8fca6649's, sha256 24b2e70aa29e6427 checked separately)
rpath = f"{root}/scripts/probes/_runner_recut_1017/recut.py"
spec = importlib.util.spec_from_file_location("recut", rpath)
recut = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recut)
# recut.py inserted REPO at sys.path[0]; put the chosen tree back in front for any lazy import
while root in sys.path:
    sys.path.remove(root)
sys.path.insert(0, root)

outdir = f"{V}/{a.tag}"
os.makedirs(outdir, exist_ok=True)
recut.OUTDIR = outdir

sys.path.insert(0, V)
import floor  # noqa: E402  (this folder's own open-floor filter)

inp = recut.load_inputs()
if a.pop != "full":
    dropped_keys = floor.dropped_keys()
    if a.pop == "kept":
        inp.rows_u = [r for r in inp.rows_u if (r["t"], r["d"]) not in dropped_keys]
    else:
        inp.rows_u = [r for r in inp.rows_u if (r["t"], r["d"]) in dropped_keys]
trades, acct = recut.build_trades(inp)
rows = recut.run_population(trades)

buf_out = io.StringIO()
with redirect_stdout(buf_out):
    buf = []
    okg = recut.run_gates(inp, trades, rows, out=buf.append)
    if not okg:
        print("\n".join(buf))
        print("A GATE IS RED - no totals printed.")
    else:
        print("gates (re-run immediately before the run):")
        print("\n".join(buf))
        print()
        recut.do_run(inp, trades, acct, rows)
open(f"{V}/{a.tag}.out", "w").write(buf_out.getvalue())

# full-precision per-trade dump
per = []
for r in rows:
    d = {"t": r.tr.t, "d": r.tr.d.isoformat(), "week": list(r.tr.week), "entry": r.tr.entry, "risk": r.tr.risk,
         "ctrl_status": r.ctrl.status, "ctrl": r.ctrl.R,
         "trigA": "A" in r.copy0["trig"], "trigB": "B" in r.copy0["trig"],
         "FA": r.copy0["trig"].get("A", {}).get("F"), "FB": r.copy0["trig"].get("B", {}).get("F"),
         "arms": {f"{fr}|{ru}": r.arms[(fr, ru)].R for fr in recut.FRAMES for ru in recut.RULES},
         "arm_status": {f"{fr}|{ru}": r.arms[(fr, ru)].status for fr in recut.FRAMES for ru in recut.RULES},
         "refs": {n: r.refs[n].R for n in recut.REFS},
         "ref_status": {n: r.refs[n].status for n in recut.REFS}}
    per.append(d)
json.dump({"acct": dict(acct), "n_rows_u": len(inp.rows_u), "gates_ok": okg, "trades": per},
          open(f"{V}/{a.tag}.perarm.json", "w"), indent=0)

# provenance: where every project module came from
lines, bad = [], []
for name, mod in sorted(sys.modules.items()):
    if name.split(".")[0] in ("agents", "shared", "core", "scripts", "walker_cand", "recut"):
        f = getattr(mod, "__file__", None) or "(namespace)"
        lines.append(f"{name}\t{f}")
        if a.tree == "pinned" and name.split(".")[0] in ("agents", "shared", "core") and f != "(namespace)" \
                and not f.startswith(PINNED_TREE):
            bad.append(name)
        if a.tree == "pinned" and name == "scripts.probes._bt_replay" and not f.startswith(PINNED_TREE):
            bad.append(name)
blob_check = {}
for rel, pin in PIN_BLOBS.items():
    p = f"{root}/{rel}"
    h = subprocess.run(["git", "hash-object", p], capture_output=True, text=True, cwd=REPO).stdout.strip()
    blob_check[rel] = (h[:8], h.startswith(pin))
lines.append(f"# tree={a.tree} root={root}")
lines.append(f"# blobs of the files at the loaded root: {blob_check}")
lines.append(f"# modules from outside the pinned tree (pinned run only): {bad}")
open(f"{V}/{a.tag}.modules.txt", "w").write("\n".join(lines) + "\n")
print(f"{a.tag}: gates_ok={okg} acct={dict(acct)} n_rows_u={len(inp.rows_u)} outside_pinned={bad} blobs={blob_check}")
