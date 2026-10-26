#!/usr/bin/env python3
"""#705 v2 re-run, B3 proofs (docs/analysis/cb_2017_21_rerun_v2_prereg_2026-10-25.md §4 B3) for `_702_r_decomposition_1022/02_build_paths.py`:

  1. DEFAULT PATH (no CB_PRE_* set): every resolved path equals today's literal - ERAS' data dirs and trades / watch tables, the log dir = the probe
     dir, the switch off (so the chain's checks never run) - imported, no build run; the write target of the checks file read off the source.
  2. PARITY on a scratch COPY of cb702_pre's inputs (never cb702_pre itself: its out/ holds the published tables): CB_PRE_DIR = the copy, CB_PRE_LOG =
     a scratch dir; the two tables must equal the published cb702_pre/out/r_decomp_{fills,control}_2017-21.tsv.gz by DECOMPRESSED bytes, and the
     checks file must equal the committed 02_build_checks_2017-21.txt line for line once the switch's own lines are dropped and timings / the data
     path masked. The copy carries what the switch requires (a manifest line for trades_pre_exitpb; a sibling `cb702_pre/symbol_guard.tsv` without
     the B* symbols, so B8's restored count is real).
  3. B3 guard: CB_PRE_DIR alone, CB_PRE_LOG = the probe dir, or CB_PRE_LOG alone -> exit 2 before anything is read; the committed checks file keeps
     its sha256. Round 2 (F6 / F13 / F2): on the REAL run (no V2_CHAIN_TEST) a scratch CB_PRE_DIR refuses; in test mode the real cb702_pre_v2 refuses
     and so does the real run's log dir (_702_r_decomposition_1022/rerun_v2_1025/, never created); a checks file already in the log dir refuses
     (once-only); a failing freeze re-check refuses - each before anything is read.
  4. B5: one flipped byte of the copy's trades_pre_exitpb makes the switched script exit 2 before it reads anything.
The parity run is in TEST MODE (V2_CHAIN_TEST=1, the freeze re-check = `true`): the scratch copy carries no frozen footer; the real re-check is the
runner's `v2-exit-read --dry-run` (tests/test_cb_v2_rerun.py).

    python3 scripts/probes/_705_rerun_v2_1023/v2_b3_checks.py SCRATCH_DIR      # receipt -> v2_b3_checks.txt beside this file; exit 0 = all pass
"""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from scripts.probes._cb_backtest import v2_chain as v2c  # noqa: E402

SCRIPT = REPO / "scripts/probes/_702_r_decomposition_1022/02_build_paths.py"
OLD = Path("/Users/alvinfung/apollo_data/cb702_pre")
RECEIPT = Path(__file__).resolve().parent / "v2_b3_checks.txt"
res, lines = [], []


def say(s=""):
    print(s, flush=True)
    lines.append(s)


def rec(label, ok, note=""):
    res.append(ok)
    say(f"{'PASS' if ok else 'FAIL'}  {label}{('  ' + note) if note else ''}")


def gz_sha(p) -> str:
    h = hashlib.sha256()
    with gzip.open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def default_path_check() -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("CB_PRE_")}
    code = ("import importlib.util,sys,json;sys.dont_write_bytecode=True;spec=importlib.util.spec_from_file_location('bp',%r);m=importlib.util.module_from_spec(spec);"
            "spec.loader.exec_module(m);print(json.dumps({'eras':m.ERAS,'log':m.LOG_DIR,'here':m.HERE,'switch':m.V2_SWITCH,'v2c':m._v2c is None}))") % str(SCRIPT)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True).stdout
    import json
    d = json.loads(out)
    rec("default: ERAS 2017-21 = cb702_pre, its trades / watch tables", d["eras"]["2017-21"] == {"data": str(OLD), "trades": "out/trades_pre_exitpb.tsv.gz",
                                                                                              "watch": "out/watch_tl_com.tsv.gz", "cut": None})
    rec("default: ERAS 2022-24 unchanged", d["eras"]["2022-24"] == {"data": "/Users/alvinfung/apollo_data/cb702", "trades": "out/trades_discovery_exitpb.tsv.gz",
                                                                    "watch": "out/watch.tsv.gz", "cut": "2024-12-31"})
    rec("default: log dir = the probe dir (HERE literal)", d["log"] == d["here"] == "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_r_decomposition_1022")
    rec("default: switch off, chain module not imported", d["switch"] is False and d["v2c"] is True)
    src = SCRIPT.read_text()
    rec("default: the checks file is written under LOG_DIR, the tables under {data}/out (source)",
        'with open(f"{LOG_DIR}/02_build_checks' in src and 'out_f = f"{data}/out/r_decomp_fills_{era}.tsv.gz"' in src
        and 'out_c = f"{data}/out/r_decomp_control_{era}.tsv.gz"' in src)
    top = [ln for ln in src.splitlines() if "_v2c." in ln and not ln.startswith(" ")]
    rec("default: every chain check sits under `if V2_SWITCH` (7 guarded blocks; no top-level use of the chain module)",
        src.count("if V2_SWITCH:") == 7 and not top, f"{src.count('if V2_SWITCH:')} blocks")


def mask(s: str, data: str) -> str:
    s = s.replace(data, "<DATA>").replace(str(OLD), "<DATA>")
    return re.sub(r"(?<=[\s;(])\d+s(?=[;)\s]|$)", "Ns", s)


def parity(root: Path) -> None:
    if root.exists():
        sys.exit(f"REFUSED: {root} exists")
    data, sib, logd = root / v2c.V2_NAME, root / v2c.OLD_NAME, root / "log"
    for d in (data / "out", sib, logd):
        d.mkdir(parents=True)
    for rel in ("daily_closes_all.csv.gz", "sessions.txt", "symbol_guard.tsv", "out/trades_pre_exitpb.tsv.gz", "out/watch_tl_com.tsv.gz"):
        shutil.copyfile(OLD / rel, data / rel)
    g = (OLD / "symbol_guard.tsv").read_text().splitlines(keepends=True)
    (sib / "symbol_guard.tsv").write_text("".join([g[0]] + [ln for ln in g[1:] if not ln.startswith("B")]))
    man = data / "out" / v2c.MANIFEST_NAME
    v2c.manifest_append(man, "v2-exit-read (parity copy)", [(f"{v2c.V2_NAME}/out/trades_pre_exitpb.tsv.gz", data / "out" / "trades_pre_exitpb.tsv.gz")])
    base_env = {k: v for k, v in os.environ.items() if not k.startswith(("CB_PRE_", "V2_"))}
    test_env = {"V2_CHAIN_TEST": "1", "V2_TEST_FREEZE_CMD": "true"}
    fixed = SCRIPT.parent / "rerun_v2_1025"
    fixed_existed = fixed.exists()
    committed = SCRIPT.parent / "02_build_checks_2017-21.txt"
    before = v2c.sha256_file(committed)
    for label, extra in (("CB_PRE_DIR alone (CB_PRE_LOG unset)", {"CB_PRE_DIR": str(data)}),
                         ("CB_PRE_LOG = the probe dir", {"CB_PRE_DIR": str(data), "CB_PRE_LOG": str(SCRIPT.parent)}),
                         ("CB_PRE_LOG alone (CB_PRE_DIR unset)", {"CB_PRE_LOG": str(logd)})):
        p = subprocess.run([sys.executable, str(SCRIPT), "2017-21"], capture_output=True, text=True, env={**base_env, **extra}, cwd=SCRIPT.parent)
        rec(f"B3 guard: {label} -> exit 2 before anything is read, the committed checks file untouched",
            p.returncode == 2 and "REFUSED (B3)" in p.stderr and v2c.sha256_file(committed) == before and not any(logd.iterdir())
            and not (data / "out" / "r_decomp_fills_2017-21.tsv.gz").exists(), f"exit {p.returncode}")
    pre_log = root / "log_once"
    pre_log.mkdir()
    (pre_log / "02_build_checks_2017-21.txt").write_text("an earlier run's checks file\n")
    for label, extra, want in (("REAL run (no test mode) with a scratch CB_PRE_DIR", {"CB_PRE_DIR": str(data), "CB_PRE_LOG": str(fixed)},
                                "is not /Users/alvinfung/apollo_data/cb702_pre_v2"),
                               ("test mode with the REAL cb702_pre_v2", {**test_env, "CB_PRE_DIR": str(v2c.REAL_V2), "CB_PRE_LOG": str(logd)},
                                "with the REAL data dir"),
                               ("test mode with the real run's log dir rerun_v2_1025/", {**test_env, "CB_PRE_DIR": str(data), "CB_PRE_LOG": str(fixed)},
                                "CB_PRE_LOG = the real run's"),
                               ("a checks file already in the log dir (once-only)", {**test_env, "CB_PRE_DIR": str(data), "CB_PRE_LOG": str(pre_log)},
                                "stage 5 runs ONCE"),
                               ("the freeze re-check fails", {**test_env, "V2_TEST_FREEZE_CMD": "false", "CB_PRE_DIR": str(data), "CB_PRE_LOG": str(logd)},
                                "the freeze re-check (V2_TEST_FREEZE_CMD) exited 1")):
        p = subprocess.run([sys.executable, str(SCRIPT), "2017-21"], capture_output=True, text=True, env={**base_env, **extra}, cwd=SCRIPT.parent)
        rec(f"round-2 guard: {label} -> exit 2 before anything is read", p.returncode == 2 and want in p.stderr and v2c.sha256_file(committed) == before
            and not any(logd.iterdir()) and fixed.exists() == fixed_existed and not (data / "out" / "r_decomp_fills_2017-21.tsv.gz").exists(),
            f"exit {p.returncode}: {p.stderr.strip()[-120:]}")
    env = {**base_env, **test_env, "CB_PRE_DIR": str(data), "CB_PRE_LOG": str(logd)}
    t = time.time()
    p = subprocess.run([sys.executable, str(SCRIPT), "2017-21"], capture_output=True, text=True, env=env, cwd=SCRIPT.parent)
    (logd / "run.log").write_text(p.stdout + p.stderr)
    rec("parity run exits 0", p.returncode == 0, f"[{time.time() - t:.0f}s] exit {p.returncode}")
    for n in ("fills", "control"):
        a, b = data / "out" / f"r_decomp_{n}_2017-21.tsv.gz", OLD / "out" / f"r_decomp_{n}_2017-21.tsv.gz"
        rec(f"parity: r_decomp_{n}_2017-21.tsv.gz = the published table", a.exists() and gz_sha(a) == gz_sha(b), "decompressed bytes")
    new = [ln for ln in (logd / "02_build_checks_2017-21.txt").read_text().splitlines() if "v2 switch:" not in ln and "B8 restored-ticker" not in ln
           and "manifest +" not in ln]
    old = (SCRIPT.parent / "02_build_checks_2017-21.txt").read_text().splitlines()
    rec("parity: 02_build_checks_2017-21.txt = the committed file (switch lines dropped; timings and the data path masked)",
        [mask(x, str(data)) for x in new] == [mask(x, str(data)) for x in old], f"{len(new)} vs {len(old)} lines")
    b8 = [ln for ln in (logd / "02_build_checks_2017-21.txt").read_text().splitlines() if "B8 restored-ticker" in ln]
    rec("parity: B8 restored-ticker rows printed for both tables, > 0", len(b8) == 2 and all(not re.search(r": 0 of", x) for x in b8), "; ".join(x.strip() for x in b8))
    rows = v2c.manifest_rows(man)
    rec("parity: the two tables appended to the manifest, chain intact", [r["label"] for r in rows[1:]] ==
        [f"{v2c.V2_NAME}/out/r_decomp_fills_2017-21.tsv.gz", f"{v2c.V2_NAME}/out/r_decomp_control_2017-21.tsv.gz"])
    cal = v2c.log_calendar_problems(logd / "run.log")
    rec("parity: the run log's calendar line = 1635 sessions 2016-01-04..2022-06-30 (B6)", not cal, "; ".join(cal))
    # B5: a one-byte flip of the input -> exit 2 before anything is read
    f = data / "out" / "trades_pre_exitpb.tsv.gz"
    raw = bytearray(f.read_bytes())
    raw[len(raw) // 2] ^= 0x01
    f.write_bytes(bytes(raw))
    env = {**env, "CB_PRE_LOG": str(root / "log_flip")}                      # a fresh log dir: the once-only check must not answer first
    p = subprocess.run([sys.executable, str(SCRIPT), "2017-21"], capture_output=True, text=True, env=env, cwd=SCRIPT.parent)
    rec("B5: a flipped byte of trades_pre_exitpb -> exit 2 (manifest)", p.returncode == 2 and "is not the manifest's" in p.stderr, p.stderr.strip()[:160])


def main() -> int:
    say(f"#705 v2 B3 checks - {time.strftime('%Y-%m-%d %H:%M')}; 02_build_paths.py sha256 {v2c.sha256_file(SCRIPT)}, v2_chain.py sha256 "
        f"{v2c.sha256_file(Path(v2c.__file__))}; the parity run in TEST MODE (V2_CHAIN_TEST=1, freeze re-check = `true`)")
    default_path_check()
    parity(Path(sys.argv[1]).resolve())
    say(f"\nB3: {sum(res)} of {len(res)} pass -> {'ALL PASS' if all(res) else 'FAILURES'}")
    RECEIPT.write_text("\n".join(lines) + "\n")
    return 0 if all(res) else 1


if __name__ == "__main__":
    sys.exit(main())
