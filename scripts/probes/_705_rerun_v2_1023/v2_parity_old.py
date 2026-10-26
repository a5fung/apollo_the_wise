#!/usr/bin/env python3
"""#705 v2 re-run, B1 PARITY (docs/analysis/cb_2017_21_rerun_v2_prereg_2026-10-25.md §4 B1): the four NEW v2 bodies, driven through this harness
(NOT the registered CLI - no guard of the real run is weakened), on a scratch COPY of the OLD file's inputs, must reproduce by decompressed content
`cb702_pre/out`'s trades_pre_tl_com, entries_pre_tl_com, trades_pre_p5, trades_pre_h60, trades_pre_h60twin, h60_pairs_pre, trades_pre_exitpb and
p5_report_pre.tsv, h60_report_pre.tsv, h60_verdict_pre.json, exitpb_report_pre.tsv, exitpb_deltas_pre.tsv, exitpb_verdict_pre.json. The old file's
outcomes are published, so this opens nothing new; nothing on v2 is opened.

What is injected (the harness only): the hard pin of the export -> the copy's sha (`v2_rerun_read.make_specs(export_sha=...)`, the one injection point),
`runner.REPO` / `runner.HERE` -> a scratch repo / small dir (so no repo file and no `_cb_backtest/out` printout is written). Everything else runs as on
the real chain: stage 0 with no table, §5 filled from its counts (the main loop's step, here mechanical), the freeze footer pinned by `pin_lines`, the
freeze check, the scaffold's guards, the manifest, the calendar guard (B6), the B8 restored counts. The restored set is made non-empty THROUGH THE DATA:
the scratch "old" guard leaves out every symbol starting with `B` (so B8's per-cell stage-1 = stage-0 check runs on real rows).

    python3 scripts/probes/_705_rerun_v2_1023/v2_parity_old.py SCRATCH_DIR [--workers N]     # receipt -> v2_parity_old.txt beside this file
Exit 0 = every file equal; 1 = a difference (reported as found, never normalised away); 2 = a stage refused / failed.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from scripts.probes._cb_backtest import registered_read as rr  # noqa: E402
from scripts.probes._cb_backtest import runner as rn  # noqa: E402
from scripts.probes._cb_backtest import v2_chain as v2c  # noqa: E402
from scripts.probes._cb_backtest import v2_rerun_read as v2  # noqa: E402

OLD = Path("/Users/alvinfung/apollo_data/cb702_pre")
RECEIPT = Path(__file__).resolve().parent / "v2_parity_old.txt"
COPY_INPUTS = ("daily_closes_all.csv.gz", "sessions.txt", "symbol_guard.tsv", "out/candidates_tl_com.tsv", "out/watch_tl_com.tsv.gz",
               "out/gap_in_bars_tl_com.tsv", "out/minute_fetch_list_tl_com.tsv", "daily_raw_close.csv.gz", "cb702_sic.psv", "small_pulls.psv",
               "export_stats.tsv")
TABLES = ("trades_pre_tl_com.tsv.gz", "entries_pre_tl_com.tsv.gz", "trades_pre_p5.tsv.gz", "trades_pre_h60.tsv.gz", "trades_pre_h60twin.tsv.gz",
          "h60_pairs_pre.tsv.gz", "trades_pre_exitpb.tsv.gz", "h60_step0_pre.tsv.gz")
FILES = ("p5_report_pre.tsv", "h60_report_pre.tsv", "exitpb_report_pre.tsv", "exitpb_deltas_pre.tsv")
JSONS = ("h60_verdict_pre.json", "exitpb_verdict_pre.json")
lines: list = []


def say(s=""):
    print(s, flush=True)
    lines.append(s)


def gz_sha(p: Path) -> str:
    h = hashlib.sha256()
    with gzip.open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def norm(text: str) -> str:
    """The golden harness's normaliser for the volatile tokens: wall times, `written <date>`, shas; and the data paths."""
    text = re.sub(r"written \d{4}-\d{2}-\d{2}", "written <DATE>", text)
    text = re.sub(r"[0-9a-f]{64}", "<SHA64>", text)
    return re.sub(r"(?<=[\[(:= ])\d+s(?=[\])]|\s|$)", "<N>s", text)


def args_ns(root: Path, workers: int) -> argparse.Namespace:
    return argparse.Namespace(data=str(root / "cb702"), data_pre=str(root / v2.V2_NAME), period="pre", out=None, small_out=None, minutes=None,
                              workers=workers, dry_run=False, print_pins=False, prereg=None, no_freeze_check=False, keys=None, levels=None,
                              limit_dates=0, no_close=False, no_apollo=False, trades=None, parity_only=False, self_check=False)


def setup(root: Path) -> dict:
    if root.exists():
        sys.exit(f"REFUSED: {root} exists - the harness builds a fresh scratch tree")
    v2d, old, repo, here = root / v2.V2_NAME, root / v2.OLD_NAME, root / "repo", root / "hereroot"
    for d in (root / "cb702" / "out", v2d / "out", old / "out", repo / "docs" / "analysis", here / "out"):
        d.mkdir(parents=True)
    t = time.time()
    for rel in COPY_INPUTS:
        shutil.copyfile(OLD / rel, v2d / rel)
    shutil.copytree(OLD / "minutes", v2d / "minutes")
    guard = (OLD / "symbol_guard.tsv").read_text().splitlines(keepends=True)
    (old / "symbol_guard.tsv").write_text("".join([guard[0]] + [ln for ln in guard[1:] if not ln.startswith("B")]))
    for name in ("h60_verdict_pre.json", "exitpb_verdict_pre.json", "h60_step0_pre.tsv.gz"):
        shutil.copyfile(OLD / "out" / name, old / "out" / name)
    body = (REPO / "docs" / "analysis" / v2.V2_DOC).read_text(encoding="utf-8").split(rn.FREEZE_MARK)[0]
    (repo / "docs" / "analysis" / v2.V2_DOC).write_text(body + rn.FREEZE_MARK + "\n## Freeze record\n", encoding="utf-8")
    (repo / v2.MODULE_REL).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO / v2.MODULE_REL, repo / v2.MODULE_REL)
    say(f"SETUP: scratch copy of {OLD}'s inputs (export, sessions, guard, candidates, watch, minutes tree) -> {v2d} [{time.time() - t:.0f}s]; the scratch "
        f"old guard leaves out every symbol starting with B (the restored set for B8)")
    rn.REPO, rn.HERE = repo, here
    return {"root": root, "v2": v2d, "old": old, "repo": repo}


def pin(tree: dict, specs: dict, args) -> None:
    """§5 filled from stage 0's counts, then the footer pinned (pinned code copied from the real repo where it exists, a stub otherwise)."""
    doc = tree["repo"] / "docs" / "analysis" / v2.V2_DOC
    counts = json.loads((tree["v2"] / "out" / v2.STEP0_OUT_SUB / v2.STEP0_COUNTS).read_text())
    body = v2.fill_section5(doc.read_text(encoding="utf-8"), counts).split(rn.FREEZE_MARK)[0]
    ctx = rr.resolve(specs["v2-pre-read"], args, rn)
    files = rr.frozen_map(specs["v2-pre-read"], ctx)
    for label, p in files.items():
        p = Path(p)
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            try:
                real = REPO / p.relative_to(tree["repo"])
            except ValueError:
                real = None
            if real is not None and real.is_file():
                shutil.copyfile(real, p)
            else:
                p.write_text(f"stub {label}\n")
    pins = rn.pin_lines(ctx.data, ctx.repo, files=rr.frozen_map(specs["v2-pre-read"], ctx))
    doc.write_text(body + rn.FREEZE_MARK + "\n## Freeze record\n" + "\n".join(pins + [f"- doc body sha256: `{rn.doc_body_sha(body)}`"]) + "\n", encoding="utf-8")
    exp, b8 = v2.parse_section5(doc.read_text(encoding="utf-8"))
    say(f"§5 (parity copy): filled from stage 0; B8 split {b8}")
    old_table = {w: {k: v for k, v in rn.H60_EXPECTED[w].items()} for w in ("pre", "2020-21")}
    same = all(exp[w].get(k) == v for w in old_table for k, v in old_table[w].items())
    say(f"STAGE 0 ON THE OLD COPY vs the OLD registered table H60_EXPECTED (pre + 2020-21, tl_rows included): {'EQUAL' if same else 'DIFFERS'}"
        + ("" if same else f" - {[(w, k, exp[w].get(k), v) for w in old_table for k, v in old_table[w].items() if exp[w].get(k) != v]}"))
    if not same:
        raise SystemExit(1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scratch")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2)))
    a = ap.parse_args()
    root = Path(a.scratch).resolve()
    T0 = time.time()
    say(f"#705 v2 B1 PARITY on a scratch copy of the OLD file - {time.strftime('%Y-%m-%d %H:%M')}; runner sha256 {rn.sha256_file(Path(rn.__file__))}, "
        f"spec module sha256 {rn.sha256_file(Path(v2.__file__))}, scaffold sha256 {rn.sha256_file(Path(rr.__file__))}")
    tree = setup(root)
    specs = v2.make_specs(export_sha=rn.sha256_file(tree["v2"] / "daily_closes_all.csv.gz"))
    args = args_ns(root, a.workers)
    for stage in ("v2-h60-step0", "v2-pre-read", "v2-h60-read", "v2-exit-read"):
        if stage == "v2-pre-read":
            pin(tree, specs, args)
        t = time.time()
        try:
            rc = rr.run_registered_read(specs[stage], args, rn)
        except SystemExit as ex:
            rc = int(ex.code or 0)
        say(f"STAGE {stage}: exit {rc} [{time.time() - t:.0f}s]")
        if rc != 0:
            say(f"PARITY NOT RUN TO THE END: {stage} exited {rc}")
            RECEIPT.write_text("\n".join(lines) + "\n")
            return 2
    out, ok = tree["v2"] / "out", []
    say("")
    say("COMPARE (new body on the old copy vs cb702_pre/out, as published):")
    for name in TABLES:
        a_, b_ = out / name, OLD / "out" / name
        r = gz_sha(a_) == gz_sha(b_)
        ok.append(r)
        say(f"  {'EQUAL ' if r else 'DIFFER'}  {name}  (decompressed content sha256 {gz_sha(a_)[:12]} vs {gz_sha(b_)[:12]})")
    for name in FILES:
        a_, b_ = (out / name).read_bytes(), (OLD / "out" / name).read_bytes()
        r = a_ == b_ or norm(a_.decode()) == norm(b_.decode())
        ok.append(r)
        say(f"  {'EQUAL ' if r else 'DIFFER'}  {name}  ({'bytes' if a_ == b_ else 'after the golden normaliser'})")
    for name in JSONS:
        r = json.loads((out / name).read_text()) == json.loads((OLD / "out" / name).read_text())
        ok.append(r)
        say(f"  {'EQUAL ' if r else 'DIFFER'}  {name}  (json)")
    tags = {"h60_verdict_pre.json": "v2_h60_verdict_pre.json", "exitpb_verdict_pre.json": "v2_exit_verdict_pre.json"}
    for name, tagged in tags.items():
        r = json.loads((out / tagged).read_text()) == json.loads((OLD / "out" / name).read_text())
        ok.append(r)
        say(f"  {'EQUAL ' if r else 'DIFFER'}  {tagged} (the scaffold's verdict file) vs the old {name}  (json)")
    s0 = out / v2.STEP0_OUT_SUB / "h60_step0_pre.tsv.gz"
    r = gz_sha(s0) == gz_sha(OLD / "out" / "h60_step0_pre.tsv.gz")
    ok.append(r)
    say(f"  {'EQUAL ' if r else 'DIFFER'}  stage 0's {v2.STEP0_OUT_SUB}/h60_step0_pre.tsv.gz vs the old h60_step0_pre.tsv.gz (decompressed)")
    rows = v2c.manifest_rows(out / v2c.MANIFEST_NAME)
    say(f"MANIFEST: {len(rows)} lines, chain intact, stages {sorted({r['stage'] for r in rows})}")
    say(f"\nPARITY: {sum(ok)} of {len(ok)} equal -> {'ALL EQUAL' if all(ok) else 'DIFFERENCES (reported as found)'}; WALL TIME {time.time() - T0:.0f}s")
    RECEIPT.write_text("\n".join(lines) + "\n")
    return 0 if all(ok) else 1


if __name__ == "__main__":
    sys.exit(main())
