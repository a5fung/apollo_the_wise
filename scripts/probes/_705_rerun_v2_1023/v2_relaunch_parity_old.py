#!/usr/bin/env python3
"""#705 v2 re-run, B4 end to end on the OLD file: the NEW `04_relaunch.sh` (manifest pre-check, rerun_v2_1025 dirs, the episode equality, the calendar
checks, the B8 restored counts, the manifest appends, stage 4 = G8 + B9) run on a scratch COPY of cb702_pre's inputs and a scratch copy of the code
(so no real rerun_v2_1025/ dir is created - those would block the real run's once-only check), then every read table / numbers file compared with
what the four docs cite (cb702_pre/out and the read dirs' committed files) - the 10-23 parity, repeated through the new script.

The copy: the export and its sidecars, the five chain-made tables the script needs (entries_pre_tl_com, trades_pre_exitpb, r_decomp_fills /
control) with a manifest naming them, the OLD episode tables in place of the 10-23 v2 ones (the episode-equality check then has a real target), the
old file's price flags for G8, and a sibling `cb702_pre/symbol_guard.tsv` without the B* symbols (B8's restored set). The old file's outcomes are
published; nothing on v2 is opened. The relaunch runs in TEST MODE (V2_CHAIN_TEST=1: the scratch paths; the freeze re-check = `true`, since the
scratch copy carries no frozen footer - the real re-check is the runner's `v2-exit-read --dry-run`, tested in tests/test_cb_v2_rerun.py).
    python3 scripts/probes/_705_rerun_v2_1023/v2_relaunch_parity_old.py SCRATCH_DIR     # receipt -> v2_relaunch_parity_old.txt beside this file
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from scripts.probes._cb_backtest import v2_chain as v2c  # noqa: E402

OLD = Path("/Users/alvinfung/apollo_data/cb702_pre")
FLAGS = Path("/Users/alvinfung/apollo_data/audit_runs_2026-10-23/A_flags.tsv")
RECEIPT = Path(__file__).resolve().parent / "v2_relaunch_parity_old.txt"
READS = {"winner_recall": "_702_winner_recall_1022", "breakout_definition": "_702_breakout_definition_1022", "entry_stop_retry": "_702_entry_stop_retry_1022",
         "trail_variants": "_702_trail_variants_1023"}
lines, res = [], []


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


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    if root.exists():
        sys.exit(f"REFUSED: {root} exists")
    v, sib, code = root / "data" / v2c.V2_NAME, root / "data" / v2c.OLD_NAME, root / "scripts" / "probes"
    for d in (v / "out" / "rerun_1023" / "winner_recall", v / "audit_1023" / "price", sib, code / "_cb_backtest", code / "_705_rerun_v2_1023",
              root / "scripts" / "backtest_data_audit"):
        d.mkdir(parents=True)
    for rel in ("daily_closes_all.csv.gz", "daily_raw_close.csv.gz", "symbol_guard.tsv", "small_pulls.psv", "cb702_sic.psv", "sessions.txt",
                "out/watch_tl_com.tsv.gz", "out/entries_pre_tl_com.tsv.gz", "out/trades_pre_p5.tsv.gz", "out/trades_pre_exitpb.tsv.gz", "out/r_decomp_fills_2017-21.tsv.gz",
                "out/r_decomp_control_2017-21.tsv.gz"):
        shutil.copyfile(OLD / rel, v / rel)
    for t in ("x200", "x150"):
        shutil.copyfile(OLD / "out" / f"wrecall_episodes_2017-21_{t}.tsv.gz", v / "out" / "rerun_1023" / "winner_recall" / f"wrecall_episodes_2017-21_{t}.tsv.gz")
    shutil.copyfile(FLAGS, v / "audit_1023" / "price" / "A_flags.tsv")
    g = (OLD / "symbol_guard.tsv").read_text().splitlines(keepends=True)
    (sib / "symbol_guard.tsv").write_text("".join([g[0]] + [ln for ln in g[1:] if not ln.startswith("B")]))
    v2c.manifest_append(v / "out" / v2c.MANIFEST_NAME, "parity copy (stages 1-3, 5 as published)",
                        [(f"{v2c.V2_NAME}/out/{n}", v / "out" / n) for n in ("entries_pre_tl_com.tsv.gz", "trades_pre_p5.tsv.gz", "trades_pre_exitpb.tsv.gz",
                                                                          "r_decomp_fills_2017-21.tsv.gz", "r_decomp_control_2017-21.tsv.gz")])
    probes = REPO / "scripts" / "probes"
    for d in READS.values():
        (code / d).mkdir()
        for f in (probes / d).glob("*.py"):
            shutil.copyfile(f, code / d / f.name)
    shutil.copyfile(probes / "_cb_backtest" / "v2_chain.py", code / "_cb_backtest" / "v2_chain.py")
    (code / "_702_r_decomposition_1022" / "rerun_v2_1025").mkdir(parents=True)          # stage 5's log: the committed checks file of the old file's run
    shutil.copyfile(probes / "_702_r_decomposition_1022" / "02_build_checks_2017-21.txt",
                    code / "_702_r_decomposition_1022" / "rerun_v2_1025" / "02_build_checks_2017-21.txt")
    for f in ("04_relaunch.sh", "v2_degraded.py"):
        shutil.copyfile(probes / "_705_rerun_v2_1023" / f, code / "_705_rerun_v2_1023" / f)
    shutil.copyfile(REPO / "scripts" / "backtest_data_audit" / "trade_impact.py", root / "scripts" / "backtest_data_audit" / "trade_impact.py")
    say(f"#705 v2 B4 end to end on a copy of the OLD file - {time.strftime('%Y-%m-%d %H:%M')}; 04_relaunch.sh sha256 "
        f"{v2c.sha256_file(probes / '_705_rerun_v2_1023' / '04_relaunch.sh')}, v2_chain.py sha256 {v2c.sha256_file(probes / '_cb_backtest' / 'v2_chain.py')}, "
        f"v2_degraded.py sha256 {v2c.sha256_file(probes / '_705_rerun_v2_1023' / 'v2_degraded.py')}; TEST MODE (V2_CHAIN_TEST=1, freeze re-check = `true`)")
    env = {**{k: x for k, x in os.environ.items() if not k.startswith(("CB_PRE_", "V2_"))}, "V2_DIR": str(v), "PROBES": str(code), "V2_CHAIN_TEST": "1",
           "V2_TEST_FREEZE_CMD": "true"}
    t = time.time()
    p = subprocess.run(["bash", str(code / "_705_rerun_v2_1023" / "04_relaunch.sh")], capture_output=True, text=True, env=env)
    (root / "relaunch.log").write_text(p.stdout + "\n--- stderr ---\n" + p.stderr)
    rec("04_relaunch.sh exits 0 on the old copy", p.returncode == 0, f"exit {p.returncode} [{time.time() - t:.0f}s]; log {root / 'relaunch.log'}")
    if p.returncode != 0:
        say(p.stdout[-3000:] + p.stderr[-3000:])
        RECEIPT.write_text("\n".join(lines) + "\n")
        return 2
    out = p.stdout
    rec("the six calendar checks passed (stage 5's log, read 2's episodes and catch, reads 1 / 3 / 4's builds: CALENDAR OK x6)", out.count("CALENDAR OK") == 6)
    rec("read 4's pp cell = read 3's S2 cell to 1e-9 (PP PARITY OK)", "PP PARITY OK" in out)
    rec("the episode step reproduced its target (EQUAL x2)", out.count("EQUAL:") == 2)
    rec("every B8 restored count printed and > 0 (B8 RESTORED x7)", out.count("B8 RESTORED:") == 7 and " 0 of " not in "".join(l for l in out.splitlines() if "B8 RESTORED" in l))
    rec("stage 4 ran: G8 consoles and the B9 report on both tables", out.count("B9 DEGRADED-WALK REPORT") == 2 and out.count("published C0 trades") + out.count("r1 A20_") >= 3)
    b9 = [ln for ln in out.splitlines() if ln.startswith("B9 DEGRADED-WALK REPORT")]
    rec("B9 on the old copy reproduces the data standard's C1 count: 5 degraded C0 walks, all endings, on each table",
        len(b9) == 2 and all("13,368 rows, 13,363 mature, 5 degraded = 5 endings (" in ln and "+ 0 holes" in ln for ln in b9), " | ".join(b9))
    rec("B9 mark check: every ending's mark = the ticker's last close (both tables)", out.count("MARK CHECK (an ending's mark = the ticker's last close): ok") == 2)
    rows = v2c.manifest_rows(v / "out" / v2c.MANIFEST_NAME)
    rec("the manifest grew by the reads' tables and their 03_* numbers / reports, chain intact, one line per label",
        len(rows) == 5 + 5 + 5 + 4 + 4 and len({r["label"] for r in rows}) == len(rows), f"{len(rows)} lines")
    rec("every manifest line names the file as it is now (what stage 7 checks)", v2c.manifest_problems(v / "out" / v2c.MANIFEST_NAME,
                                                                                                     [(r["label"], r["path"]) for r in rows]) == [])
    k = "the freeze re-check runs V2_TEST_FREEZE_CMD="
    rec("the freeze re-check ran first (test mode: its line before the manifest check)", k in out and "MANIFEST OK" in out and out.index(k) < out.index("MANIFEST OK"))
    R = v / "out" / "rerun_v2_1025"
    for read, d in READS.items():
        for f in sorted((R / read).glob("*.tsv.gz")):
            if f.is_symlink():
                continue
            o = OLD / "out" / f.name
            rec(f"{read}/{f.name} = the published table", o.exists() and gz_sha(f) == gz_sha(o), "decompressed bytes")
        for f in sorted((R / read).glob("*.parquet")):
            rec(f"{read}/{f.name} = the published table", v2c.sha256_file(f) == v2c.sha256_file(OLD / "out" / f.name), "sha256")
    sub = lambda dd: {k: x for k, x in dd.items() if "2017-21" in k}
    for read, d, name, cut in (("winner_recall", READS["winner_recall"], "03_numbers.json", sub), ("breakout_definition", READS["breakout_definition"], "03_numbers.json", sub),
                               ("entry_stop_retry", READS["entry_stop_retry"], "03_headline.json", lambda dd: {"2017-21": dd["2017-21"]}),
                               ("trail_variants", READS["trail_variants"], "03_headline.json", lambda dd: {"2017-21": dd["2017-21"]}),
                               ("entry_stop_retry", READS["entry_stop_retry"], "02_numbers_2017-21.json", lambda dd: dd),
                               ("trail_variants", READS["trail_variants"], "02_numbers_2017-21.json", lambda dd: dd)):
        new = json.loads((code / d / "rerun_v2_1025" / name).read_text())
        old = cut(json.loads((probes / d / name).read_text()))
        rec(f"{read}/{name} = the committed file (2017-21 part)", new == old, "json")
    RECEIPT.write_text("\n".join(lines) + "\n")
    say(f"\nB4 END TO END: {sum(res)} of {len(res)} pass -> {'ALL PASS' if all(res) else 'FAILURES'}")
    RECEIPT.write_text("\n".join(lines) + "\n")
    return 0 if all(res) else 1


if __name__ == "__main__":
    sys.exit(main())
