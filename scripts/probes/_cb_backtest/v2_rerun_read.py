"""#705 v2 re-run - the four 2017-21 chain stages on the survivorship-corrected file `cb702_pre_v2`, as registered reads on the shared scaffold
(docs/analysis/cb_2017_21_rerun_v2_prereg_2026-10-25.md §3 / §4 B1, B2, B5, B6, B8). BUILT ON SYNTHETIC DATA plus a parity run on a scratch COPY of
the OLD file (`_705_rerun_v2_1023/v2_parity_old.py`); nothing here was run on v2.

Stages (dispatched by runner.py; `--data <cb702> --data-pre <cb702_pre_v2> --period pre`):
  v2-h60-step0   stage 0, BEFORE the freeze (doc=None: the scaffold's declared no-freeze path): the hourly-close STEP 0 on v2, entry-time facts
                 only, into its OWN dirs (`cb702_pre_v2/out/v2_step0_1025/`, `_cb_backtest/out/v2_1025/step0/`) with NO registered table
                 (`expected=None`); prints the §5 counts and the B8 split (shared / restored / removed) and writes them as a json beside the table
  v2-pre-read    stage 1: `run_pre_read`'s body - the registered minute engine, his carried-exit P5 walk, the cross-check; exit 3 BEFORE the report
                 when the data-abstain share is over 5% or the cross-check fails; B8 restored fills per cell equal stage 0's
  v2-h60-read    stage 2: `run_h60_read`'s body - first, with nothing written, the doc's §5 against stage 0's PINNED counts json and the tl rows
                 (exit 2: a typo in §5 never spends the once-only STEP 0 names); then STEP 0 against the doc's §5 (exit 2 before any exit is
                 walked), the ORH5 twin (exit 3), the exits,
                 the pairs, the report, the verdict; the 2025-26 stamps are NOT called (an old-versus-v2 note against cb702_pre's pre verdict instead)
  v2-exit-read   stage 3: `run_exit_read`'s body - the module hard pin, parity P1 / P2 (exit 3), every arm, the self-checks, the report, the verdict
Every body CALLS the finished stages' functions unchanged (the list is `V2_RUNNER_CALLS`, derived by an AST walk and pinned by a test); the one
exception is `h60_step0(expected=...)` (default unchanged). Every tag starts with `v2`. Small outputs go to `_cb_backtest/out/v2_1025/` (the finished
stages write fixed names to whatever small dir they are handed); the scaffold's own files go to `_cb_backtest/out/` under the v2 tags.
Every helper of the runner is reached through `ctx.rt`; this module imports no runner code (the runner imports it to register the reads).
"""
from __future__ import annotations

import argparse
import contextlib
import gzip
import csv
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

from scripts.probes._cb_backtest import registered_read as rr
from scripts.probes._cb_backtest import v2_chain as v2c

# ═════════════════════════════════════════════════════════════════════════════════════════════
# the registration's constants
# ═════════════════════════════════════════════════════════════════════════════════════════════
V2_DOC = "cb_2017_21_rerun_v2_prereg_2026-10-25.md"
PERIOD = "pre"
V2_NAME, OLD_NAME = v2c.V2_NAME, v2c.OLD_NAME
V2_EXPORT_SHA = "0d5d2d0eb027abc06e4186ddec7d1e8b1234fd86f92c26798a8e15f113db668d"     # cb702_pre_v2/daily_closes_all.csv.gz (hard pin)
MODULE_SHA = "e14027be38b24352dd3c19fd5a1dcd54bae2e1cf80fc58a064d1ea65c821861b"        # = runner.EXITPB_MODULE_SHA (asserted in the tests)
MODULE_REL = Path("agents/market_intelligence/consolidation_breakout.py")
SMALL_SUB = "v2_1025"                                       # _cb_backtest/out/v2_1025/ - the v2 stages' small dir
STEP0_OUT_SUB = "v2_step0_1025"                             # cb702_pre_v2/out/v2_step0_1025/ - stage 0's pinned copies
STEP0_SMALL_SUB = "v2_1025/step0"                           # _cb_backtest/out/v2_1025/step0/
STEP0_COUNTS = "h60_step0_pre_counts.json"
TAGS = {"step0": "v2_step0", "pre": "v2_pre", "h60": "v2_h60", "exit": "v2_exit"}
REFUSED = rr.REFUSED_DEFAULT + ("parity_only", "self_check")
WINDOWS = ("pre", "2020-21")                                # h60_windows_of("pre")
CELLS_STEP0 = ("C2", "C3", "C4", "C5", "C6", "C7")
READ_DIRS = v2c.READ_DIRS
READ_SCRIPTS = ("_702_winner_recall_1022/01_episodes.py", "_702_winner_recall_1022/02_catch.py", "_702_winner_recall_1022/03_report.py",
                "_702_breakout_definition_1022/02_build.py", "_702_breakout_definition_1022/03_report.py",
                "_702_entry_stop_retry_1022/esr_lib.py", "_702_entry_stop_retry_1022/02_build.py", "_702_entry_stop_retry_1022/03_report.py",
                "_702_trail_variants_1023/trail_lib.py", "_702_trail_variants_1023/02_build.py", "_702_trail_variants_1023/03_report.py")
V2_DATA_PINS = ("daily_closes_all.csv.gz", "daily_raw_close.csv.gz", "cb702_sic.psv", "small_pulls.psv", "symbol_guard.tsv", "sessions.txt",
                "dedupe_applied.tsv", "export_stats.tsv", "audit_1023/verdict.txt", "out/candidates_tl_com.tsv", "out/watch_tl_com.tsv.gz",
                "out/gap_in_bars_tl_com.tsv", "out/minute_fetch_list_tl_com.tsv", "minutes/_done.psv",
                "audit_1023/price/A_flags.tsv")                         # the price flags stage 4's G8 (trade_impact.py --flags) reads
G9_CONSOLE = "audit_1023/pit_calendar_minutes_1025.console.txt"   # the G9 scan's console (`pit_lint.py calendar --minutes`), written before the freeze

# The runner functions the bodies reach (`ctx.rt.<name>(...)` / `rt.<name>(...)`), DERIVED by an AST walk of this module; a test asserts the walk
# equals this tuple and that `h60_stamps` / `exitpb_stamps` / `run_*` are not on it (nor reachable from it inside runner.py).
V2_RUNNER_CALLS = ("_ci", "_num", "build_pre_rows", "exitpb_load_frame", "exitpb_parity", "exitpb_prepare", "exitpb_reach_text", "exitpb_report_rows",
                   "exitpb_report_text", "exitpb_self_checks", "exitpb_walk_all", "gz_content_sha", "h60_exits", "h60_load_frame", "h60_load_trade_side",
                   "h60_load_twin_side", "h60_pair_rows", "h60_pinned_fills", "h60_prepare", "h60_report_rows", "h60_report_text", "h60_sign", "h60_step0",
                   "h60_step0_counts", "h60_twin_check", "h60_twin_inputs", "load_p5_frame", "minute_data_gate", "out_suffix", "p5_crosscheck", "p5_walk",
                   "pre_cols", "pre_complete", "pre_inputs", "pre_report_text", "read_tsv", "run_minute_stage", "sha256_file", "write_tsv")


class Refuse(Exception):
    """A v2 check failed inside a body: (code, message). The body prints the message and returns the code; nothing more is written."""

    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code


# ═════════════════════════════════════════════════════════════════════════════════════════════
# paths
# ═════════════════════════════════════════════════════════════════════════════════════════════
def old_dir(ctx) -> Path:
    """The OLD file: the sibling `cb702_pre` of the v2 dir (read only: its symbol guard for B8, its pre verdicts for the old-versus-v2 note)."""
    return Path(ctx.data).parent / OLD_NAME


def small_dir(ctx) -> Path:
    return Path(ctx.small) / SMALL_SUB


def step0_dirs(ctx) -> tuple:
    return Path(ctx.out) / STEP0_OUT_SUB, Path(ctx.small) / STEP0_SMALL_SUB


def manifest_path(ctx) -> Path:
    return Path(ctx.out) / v2c.MANIFEST_NAME


def out_label(name: str) -> str:
    return f"{V2_NAME}/out/{name}"


def small_label(name: str) -> str:
    return f"_cb_backtest/out/{SMALL_SUB}/{name}"


def doc_path(ctx) -> Path:
    return Path(ctx.repo) / "docs" / "analysis" / V2_DOC


def _ns(ctx, **kw) -> argparse.Namespace:
    """A COPY of the run's arguments with `kw` set (a body never edits ctx.args)."""
    ns = argparse.Namespace(**vars(ctx.args))
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


# ═════════════════════════════════════════════════════════════════════════════════════════════
# §8: ONE freeze map for the three frozen reads
# ═════════════════════════════════════════════════════════════════════════════════════════════
def v2_frozen(ctx) -> dict:
    """{footer label: path}: the registration's §8 pin list (the driver adds the runner, the scaffold and this spec module). One function for
    v2-pre-read, v2-h60-read and v2-exit-read, so a label can never mean two paths (`freeze_check` takes the FIRST matching footer line)."""
    repo, d, old = Path(ctx.repo), Path(ctx.data), old_dir(ctx)
    probes = repo / "scripts" / "probes"
    files = {"module": repo / MODULE_REL}
    for label, rel in ctx.rt.FROZEN_CODE.items():                       # constants, anticipation, live_fill_counterfactuals, rule_eras, exit_logic
        files[label] = repo / rel
    files["code/v2_chain.py"] = Path(v2c.__file__).resolve()          # the manifest writer, its checks, the restored set, the receipt
    files["code/02_build_paths.py"] = probes / "_702_r_decomposition_1022" / "02_build_paths.py"
    for rel in READ_SCRIPTS:
        files[f"code/{rel}"] = probes / rel
    files["code/04_relaunch.sh"] = probes / "_705_rerun_v2_1023" / "04_relaunch.sh"
    files["code/trade_impact.py"] = repo / "scripts" / "backtest_data_audit" / "trade_impact.py"
    files["code/v2_compare.py"] = probes / "_705_rerun_v2_1023" / "v2_compare.py"
    files["code/v2_degraded.py"] = probes / "_705_rerun_v2_1023" / "v2_degraded.py"
    for rel in V2_DATA_PINS:
        files[f"{V2_NAME}/{rel}"] = d / rel
    files[f"{V2_NAME}/minutes (tree)"] = d / "minutes"
    out0, small0 = step0_dirs(ctx)
    for name in ("h60_step0_pre.tsv.gz", "h60_step0_pre.txt", STEP0_COUNTS):
        files[f"{V2_NAME}/out/{STEP0_OUT_SUB}/{name}"] = out0 / name
    files[f"_cb_backtest/out/{STEP0_SMALL_SUB}/h60_step0_pre.txt"] = small0 / "h60_step0_pre.txt"
    wr = d / "out" / "rerun_1023" / "winner_recall"
    for name in ("wrecall_episodes_2017-21_x200.tsv.gz", "wrecall_episodes_2017-21_x150.tsv.gz"):
        files[f"{V2_NAME}/out/rerun_1023/winner_recall/{name}"] = wr / name
    files[f"{V2_NAME}/{G9_CONSOLE}"] = d / G9_CONSOLE
    files[f"{OLD_NAME}/symbol_guard.tsv"] = old / "symbol_guard.tsv"
    files[f"{OLD_NAME}/out/h60_verdict_pre.json"] = old / "out" / "h60_verdict_pre.json"
    files[f"{OLD_NAME}/out/exitpb_verdict_pre.json"] = old / "out" / "exitpb_verdict_pre.json"
    files["_cb_backtest/out/p5_report_pre.tsv"] = Path(ctx.small) / "p5_report_pre.tsv"
    files["read1/03_report.md"] = probes / READ_DIRS[1] / "03_report.md"
    files["read1/03_numbers.json"] = probes / READ_DIRS[1] / "03_numbers.json"
    files["read2/03_numbers.json"] = probes / READ_DIRS[0] / "03_numbers.json"
    files["read3/03_headline.json"] = probes / READ_DIRS[2] / "03_headline.json"
    files["read4/03_headline.json"] = probes / READ_DIRS[3] / "03_headline.json"
    return files


def hard_pins(export_sha: str = V2_EXPORT_SHA) -> tuple:
    """The export pin (so the old file - or any other - is refused before anything opens) and the module pin the exit read requires."""
    return (("v2 export (cb702_pre_v2/daily_closes_all.csv.gz)", lambda ctx: Path(ctx.data) / "daily_closes_all.csv.gz", export_sha),
            ("module (consolidation_breakout.py)", lambda ctx: Path(ctx.repo) / MODULE_REL, MODULE_SHA))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# §5: parse the doc's v2 STEP 0 table (B2) / render it from stage 0's counts
# ═════════════════════════════════════════════════════════════════════════════════════════════
S5_ROWS = (("C0 bases / with ≥ 2 break days", ("C0", "C0_multi")),
           ("C1 bases / with ≥ 2 break days / opening-range C1 fills", ("C1", "C1_multi", "orh5_C1_fills")),
           ("C2 / C3 / C4 / C5 / C6 / C7", CELLS_STEP0),
           ("com C1 / tl rows", ("com_C1", "tl_rows")),
           ("C0 tl opening-range fills on shared / restored tickers (B8)", ("b8_shared", "b8_restored")))
S5_WHOLE_ONLY = ("com_C1", "tl_rows")


def _section5(text: str) -> str:
    body = text.split(rr_freeze_mark(), 1)[0]
    m = re.search(r"(?ms)^## 5\. .*?(?=^## 6\. )", body)
    if not m:
        raise Refuse(2, "the registration doc has no §5 (## 5. ... ## 6.) above the freeze marker")
    return m.group(0)


def rr_freeze_mark() -> str:
    return "<!-- FREEZE -->"


def _cells(row: str) -> list:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def _ints(cell: str, n: int, what: str) -> list:
    parts = [p.strip() for p in cell.split("/")]
    if len(parts) != n or not all(re.fullmatch(r"\d{1,3}(,\d{3})*|\d+", p) for p in parts):
        raise Refuse(2, f"§5 {what}: {cell!r} is not {n} count(s) 'a / b / ...' - the v2 table is not filled (B2) or not in the registered layout")
    return [int(p.replace(",", "")) for p in parts]


def parse_section5(text: str) -> tuple:
    """(expected, b8) from the doc's §5: expected = {"pre": {...H60_EXPECTED keys + tl_rows}, "2020-21": {...}} (the v2 columns), b8 = {window:
    {"shared": n, "restored": n}}. Refuse(2) while any v2 cell still reads (B2) or a row is missing."""
    sec = _section5(text)
    rows = {}
    for ln in sec.splitlines():
        if ln.startswith("|") and not set(ln.replace("|", "").strip()) <= set("-: "):
            c = _cells(ln)
            rows[c[0]] = c
    expected, b8 = {"pre": {}, "2020-21": {}}, {"pre": {}, "2020-21": {}}
    for label, keys in S5_ROWS:
        c = rows.get(label)
        if c is None or len(c) != 5:
            raise Refuse(2, f"§5 has no row {label!r} with five columns")
        for col, wname in ((2, "pre"), (4, "2020-21")):
            if wname == "2020-21" and keys[0] in S5_WHOLE_ONLY:
                continue
            vals = _ints(c[col], len(keys), f"row {label!r}, column {'v2, whole era' if col == 2 else 'v2, 2020-21'}")
            for k, v in zip(keys, vals):
                if k.startswith("b8_"):
                    b8[wname][k[3:]] = v
                else:
                    expected[wname][k] = v
    return expected, b8


def section5_from_counts(counts: dict) -> tuple:
    """(expected, b8) exactly as `parse_section5` returns them, built from stage 0's counts json - so stage 2 can check, BEFORE its STEP 0 writes
    anything, that the doc's §5 is the table stage 0 counted (a typo while pasting refuses with nothing spent)."""
    expected, b8 = {"pre": {}, "2020-21": {}}, {"pre": {}, "2020-21": {}}
    for _label, keys in S5_ROWS:
        for wname in WINDOWS:
            if wname == "2020-21" and keys[0] in S5_WHOLE_ONLY:
                continue
            for k in keys:
                if k.startswith("b8_"):
                    b8[wname][k[3:]] = int(counts["b8"][wname][k[3:]])
                else:
                    expected[wname][k] = int(counts["table"][wname][k])
    return expected, b8


def render_section5_cells(counts: dict) -> dict:
    """{row label: (v2 whole-era cell, v2 2020-21 cell)} from stage 0's counts json (`step0_count_table`)."""
    out = {}
    for label, keys in S5_ROWS:
        cells = []
        for wname in WINDOWS:
            if wname == "2020-21" and keys[0] in S5_WHOLE_ONLY:
                cells.append("—")
                continue
            src = counts["b8"][wname] if keys[0].startswith("b8_") else counts["table"][wname]
            cells.append(" / ".join(f"{src[k[3:] if k.startswith('b8_') else k]:,}" for k in keys))
        out[label] = tuple(cells)
    return out


def fill_section5(text: str, counts: dict) -> str:
    """The doc with §5's (B2) cells filled from stage 0's counts - every other byte unchanged (the freeze's diff rule). Raises when a cell to fill
    is not (B2) (filled twice) or a row is missing."""
    sec = _section5(text)
    cells = render_section5_cells(counts)
    new_lines = []
    for ln in sec.splitlines(keepends=True):
        c = _cells(ln) if ln.startswith("|") else None
        if c and c[0] in cells:
            parts = ln.rstrip("\n").split("|")              # ['', ' label ', ' old ', ' v2 ', ' old ', ' v2 ', '']
            v2w, v2b = cells[c[0]]
            for idx, val in ((3, v2w), (5, v2b)):
                if parts[idx].strip() == "(B2)" and val != "—":
                    parts[idx] = f" {val} "
                elif not (parts[idx].strip() == "—" and val == "—"):
                    raise ValueError(f"§5 row {c[0]!r}: column {idx} reads {parts[idx].strip()!r}, not (B2) - already filled (or a cell the table "
                                     f"has no value for)")
            ln = "|".join(parts) + ("\n" if ln.endswith("\n") else "")
        new_lines.append(ln)
    return text.replace(sec, "".join(new_lines), 1)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# B6: the calendar a body walks on equals sessions.txt
# ═════════════════════════════════════════════════════════════════════════════════════════════
@contextlib.contextmanager
def calendar_guard(rt, sessions: list, say):
    """Every `load_daily` the finished stages make inside the block is checked against sessions.txt the moment it returns - BEFORE any walk -
    and refuses (Refuse(2)) on a difference. The runner's function is restored on exit."""
    real = rt.load_daily

    def checked(path, *a, **k):
        D = real(path, *a, **k)
        problem = v2c.calendar_problem([d.isoformat() for d in D.cal], sessions)
        if problem:
            raise Refuse(2, f"CALENDAR (B6): {path}: {problem} - one calendar per record; the stage refuses before any walk")
        say(f"CALENDAR (B6): {Path(path).name} walks {len(D.cal)} sessions {D.cal[0]}..{D.cal[-1]} = sessions.txt")
        return D
    rt.load_daily = checked
    try:
        yield
    finally:
        rt.load_daily = real


# ═════════════════════════════════════════════════════════════════════════════════════════════
# B8: restored-name counts
# ═════════════════════════════════════════════════════════════════════════════════════════════
def restored(ctx) -> frozenset:
    return v2c.restored_set(Path(ctx.data) / "symbol_guard.tsv", old_dir(ctx) / "symbol_guard.tsv")


def step0_split_counts(rt, bases: dict, facts: dict, pick: dict, rest: frozenset) -> dict:
    """{"table": {window: the §5 keys}, "b8": {window: {"shared", "restored"}}, "cells": {window: {cell: {"shared", "restored"}}}}: the C0..C7 tl
    ORH5 entry-fact fills split by the ticker's side of the restored set (every cell, so stage 1 can check per cell)."""
    out = {"table": {}, "b8": {}, "cells": {}}
    sides = {"restored": {k: v for k, v in bases.items() if k[0] in rest}, "shared": {k: v for k, v in bases.items() if k[0] not in rest}}
    for wname, years in zip(WINDOWS, (None, (2020, 2021))):
        c = rt.h60_step0_counts(bases, facts, pick, years)
        t = {"C0": c.get(("tl", "C0"), 0), "C0_multi": c.get(("tl", "C0_multi"), 0), "C1": c.get(("tl", "C1"), 0),
             "C1_multi": c.get(("tl", "C1_multi"), 0), "orh5_C1_fills": c.get(("tl", "C1_orh5_fills"), 0), "com_C1": c.get(("com", "C1"), 0)}
        for cell in CELLS_STEP0:
            t[cell] = c.get(("tl", cell), 0)
        out["table"][wname] = t
        per = {}
        for side, bs in sides.items():
            cs = rt.h60_step0_counts(bs, facts, pick, years)
            for cell in rt.CELL_COLS:
                per.setdefault(cell, {})[side] = cs.get(("tl", cell + "_orh5_fills"), 0)
        out["cells"][wname] = per
        out["b8"][wname] = {"shared": per["C0"]["shared"], "restored": per["C0"]["restored"]}
    return out


def pinned_step0_restored(counts_json: Path) -> dict:
    """{(window, cell): restored ORH5 entry-fact fills} as stage 0 counted them, read back off its PINNED counts json (the STEP 0 row table carries
    the bar entries only - no orh5 row - so the json is the record). Zero cells are dropped."""
    c = json.loads(Path(counts_json).read_text())
    return {(w, cell): v["restored"] for w, per in c["cells"].items() for cell, v in per.items() if v["restored"]}


def restored_rows(rt, path: Path, rest: frozenset, where=None) -> tuple:
    """(rows on restored tickers, rows) of a trades table after `where(df)`."""
    df = rt.read_tsv(path)
    if where is not None:
        df = where(df)
    return int(df["ticker"].isin(rest).sum()), int(len(df))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# shared prepare pieces: own once-only scan of the small subdir, manifest checks on chain-made inputs
# ═════════════════════════════════════════════════════════════════════════════════════════════
def _existing(paths) -> list:
    return [q for p in paths for q in (Path(p), Path(str(p) + ".partial")) if q.exists()]


def _refuse_now(ctx, lines) -> None:
    for ln in lines:
        print(ln, file=sys.stderr)
    raise SystemExit(2)


def guard_small_and_manifest(ctx, small_names: tuple, upstream: tuple) -> dict:
    """The checks the scaffold cannot make: (a) once-only over the files a body writes under `_cb_backtest/out/v2_1025/` (scaffold: ctx.out and its
    own small files only); (b) every chain-made table the stage reads equals its last manifest line (B5; tables made BY the chain cannot be pinned in
    the freeze). On a real run either refuses now (exit 2); a dry run reports them."""
    existing = _existing(small_dir(ctx) / n for n in small_names)
    problems = v2c.manifest_problems(manifest_path(ctx), [(out_label(n), Path(ctx.out) / n) for n in upstream]) if upstream else []
    if not getattr(ctx.args, "dry_run", False):
        if problems:
            _refuse_now(ctx, ["REFUSED: a chain-made table this stage reads is not the one its stage wrote (B5):"] + [f"  - {p}" for p in problems])
        if existing:
            crashed = [q for q in existing if q.name.endswith(".partial")]
            _refuse_now(ctx, [f"REFUSED: {(crashed or existing)[0]} exists - the v2 stage is run ONCE; a small output under {small_dir(ctx)} is already on disk"])
    return {"existing_small": existing, "manifest_problems": problems}


def _opens(ctx) -> list:
    old = old_dir(ctx)
    return [Path(ctx.data) / "symbol_guard.tsv", old / "symbol_guard.tsv", Path(ctx.data) / "sessions.txt"]


def _dry(ctx, prep, existing, what: str) -> str:
    return (f"{what} DRY RUN (freeze check {ctx.freeze}; counts only - no daily bar, minute row or outcome was opened): {len(prep['rows']):,} rows; "
            f"{len(prep['inp']['pairs']) if prep.get('inp') else 0:,} (date, ticker) pairs, NOT logged {len(prep['inp']['missing']) if prep.get('inp') else 0:,}; "
            f"restored tickers {len(prep['restored']):,}; outputs on disk: {[q.name for q in existing] or 'none'}; small outputs on disk: "
            f"{[q.name for q in prep['existing_small']] or 'none'}; manifest problems: {prep['manifest_problems'] or 'none'}")


def _sessions(ctx) -> list:
    return v2c.read_sessions(Path(ctx.data) / "sessions.txt")


def _finish(ctx, stage: str, out_names: tuple, small_names: tuple, say) -> None:
    items = [(out_label(n), Path(ctx.out) / n) for n in out_names] + [(small_label(n), small_dir(ctx) / n) for n in small_names]
    for r in v2c.manifest_append(manifest_path(ctx), stage, [(lbl, p) for lbl, p in items if p.exists()]):
        say(f"MANIFEST + {r['label']} {r['sha256'][:12]}...")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# stage 0: v2-h60-step0 (before the freeze; doc=None)
# ═════════════════════════════════════════════════════════════════════════════════════════════
STEP0_OUTPUTS = (f"{STEP0_OUT_SUB}/h60_step0_pre.tsv.gz", f"{STEP0_OUT_SUB}/h60_step0_pre.txt", f"{STEP0_OUT_SUB}/{STEP0_COUNTS}")
STEP0_SMALL = ("step0/h60_step0_pre.txt",)


def step0_prepare(ctx) -> dict:
    rt = ctx.rt
    g = guard_small_and_manifest(ctx, STEP0_SMALL, ())
    prep = rt.h60_prepare(_ns(ctx, out=None), ctx.dirs, PERIOD)
    rows = [r for rs in prep["bases"].values() for r in rs]
    return {"rows": rows, "inp": prep["inp"], "path": Path(ctx.out) / "candidates_tl_com.tsv", "opens": _opens(ctx), "h60": prep,
            "restored": restored(ctx), **g}


def step0_outputs(ctx) -> tuple:
    return STEP0_OUTPUTS


def step0_dry_run(ctx, prep, existing) -> str:
    return _dry(ctx, prep, existing, "V2-H60-STEP0")


def removed_counts(rt, old: Path, bases: dict) -> dict:
    """B8 'removed': the OLD file's C0 tl BASES (its published STEP 0 table - entry-time facts only, one first-break row per base) whose (ticker,
    pole_date) does not exist on v2 - the dedupe twins and the names newly typed as non-stocks. Bases, not fills: the old STEP 0 table carries the
    bar entries only (no ORH5 row). {window: n}; None when the table is absent."""
    p = old / "out" / "h60_step0_pre.tsv.gz"
    if not p.is_file():
        return {w: None for w in WINDOWS}
    df = rt.read_tsv(p, usecols=["ticker", "pole_date", "E", "K", "row_no", "variant", "C0"])
    df = df[(df["K"] == "tl") & (df["variant"] == rt.H60_ENTRY) & (df["row_no"] == 0) & (df["C0"] == 1)]
    have = {(k[0], k[1]) for k in bases if k[2] == "tl"}
    gone = [(t, str(e)) for t, pd_, e in df[["ticker", "pole_date", "E"]].itertuples(index=False) if (t, str(pd_)) not in have]
    return {"pre": len(gone), "2020-21": sum(1 for _t, e in gone if int(e[:4]) in (2020, 2021)), "old_bases": int(len(df))}


def step0_body(ctx, prep, say) -> int:
    rt = ctx.rt
    out0, small0 = step0_dirs(ctx)
    h = prep["h60"]
    bases, inp, rest = h["bases"], prep["inp"], prep["restored"]
    say(f"V2 STAGE 0 (before the freeze; no registered table): {len(bases):,} bases, {len(prep['rows']):,} rows; restored tickers {len(rest):,}; writes "
        f"{out0} and {small0} only (never out/h60_step0_pre.*)")
    s0 = rt.h60_step0(bases, inp, ctx.workers, PERIOD, out0, small0, None, expected=None)
    print(s0["text"])
    counts = step0_split_counts(rt, bases, s0["facts"], s0["pick"], rest)
    counts["table"]["pre"]["tl_rows"] = h["label_rows"]
    counts["removed"] = removed_counts(rt, old_dir(ctx), bases)
    counts["early_problems"] = s0["early_problems"]
    counts["data_share"] = s0["data_share"]
    counts["missing_pairs"] = len(inp["missing"]) + len(inp["lost"])
    with ctx.partial_write(STEP0_COUNTS, under=out0) as fh:
        fh.write((json.dumps(counts, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    say(f"TL ROWS by label / file: {h['label_rows']}")
    for wname in WINDOWS:
        b = counts["b8"][wname]
        say(f"B8 C0 tl ORH5 entry-fact fills, window {wname}: shared {b['shared']:,} / restored {b['restored']:,}; removed: {counts['removed'][wname]} of the "
            f"old file's {counts['removed'].get('old_bases')} C0 tl bases have no v2 base (ticker, pole date)")
    say("§5 (B2) - the v2 cells, to paste (python3 scripts/probes/_cb_backtest/v2_rerun_read.py fill-section5 fills the doc's (B2) cells from "
        f"{out0 / STEP0_COUNTS}):")
    for label, (w, b) in render_section5_cells(counts).items():
        say(f"  {label}: whole era {w} | 2020-21 {b}")
    if counts["b8"]["pre"]["restored"] == 0:
        say("B8 REFUSES: 0 C0 fills on restored tickers - the restored names were dropped (a stale path, a filter or the wrong data dir)")
        return 3
    if s0["early_problems"]:
        say("EARLY-CLOSE CHECK FAILED: " + "; ".join(s0["early_problems"]))
        return 3
    say(f"WROTE {out0 / 'h60_step0_pre.tsv.gz'}, {out0 / 'h60_step0_pre.txt'}, {out0 / STEP0_COUNTS}, {small0 / 'h60_step0_pre.txt'}")
    return 0


# ═════════════════════════════════════════════════════════════════════════════════════════════
# stage 1: v2-pre-read
# ═════════════════════════════════════════════════════════════════════════════════════════════
PRE_OUTPUTS = ("trades_pre_tl_com.tsv.gz", "entries_pre_tl_com.tsv.gz", "trades_pre_p5.tsv.gz", "p5_report_pre.tsv")
PRE_SMALL = ("minute_summary_pre_tl_com.txt", "p5_report_pre.tsv", "p5_report_pre.txt", "p5_summary_pre.txt")


def pre_prepare(ctx) -> dict:
    rt = ctx.rt
    g = guard_small_and_manifest(ctx, PRE_SMALL, ())
    inp = rt.pre_inputs(_ns(ctx, data=str(ctx.data), out=None, minutes=None))
    out0, _s = step0_dirs(ctx)
    return {"rows": inp["cands"], "inp": inp, "path": inp["path"], "opens": _opens(ctx) + [out0 / "h60_step0_pre.tsv.gz", out0 / STEP0_COUNTS], "pre": inp,
            "restored": restored(ctx), **g}


def pre_outputs(ctx) -> tuple:
    return PRE_OUTPUTS


def pre_dry_run(ctx, prep, existing) -> str:
    return _dry(ctx, prep, existing, "V2-PRE-READ")


def pre_body(ctx, prep, say) -> int:
    try:
        with calendar_guard(ctx.rt, _sessions(ctx), say):
            return _pre_body(ctx, prep, say)
    except Refuse as r:
        say(f"REFUSED: {r}")
        return r.code


def _pre_body(ctx, prep, say) -> int:
    rt = ctx.rt
    small = small_dir(ctx)
    small.mkdir(parents=True, exist_ok=True)
    rest = prep["restored"]
    inp = rt.pre_complete(prep["pre"])
    by_k = Counter(c["K"] for c in inp["cands"])
    keys = ("tl", "com")
    say(f"V2-PRE-READ: {len(inp['cands']):,} first-break rows ({', '.join(f'{k} {by_k[k]:,}' for k in keys)}), {len(inp['pairs']):,} pairs all logged; "
        f"restored tickers {len(rest):,}")
    margs = _ns(ctx, keys=",".join(keys), no_close=False, no_apollo=False, limit_dates=0, small_out=str(small), out=None, minutes=None, data=str(ctx.data))
    rt.run_minute_stage(margs, "pre", inp)                       # the registered minute engine, on the era's first breaks
    tp, tally, n_rows = rt.p5_walk(inp, ctx.workers, "pre", say)
    states = {k[1]: n for k, n in tally.items() if k[0] == "minutes_state"}
    say(f"COVERAGE: candidates with minutes fetched {sum(n for s, n in states.items() if s != 'pending'):,} "
        f"(by state {dict(sorted(states.items()))}); PENDING fetch (skipped) {states.get('pending', 0):,}")
    ent = {(k[1], k[2]): n for k, n in tally.items() if k[0] == "entry"}
    say("ENTRY (orh5, all levels): " + "; ".join(f"{st}{(' ' + r) if r else ''} {n:,}" for (st, r), n in sorted(ent.items())))
    gate = Counter()
    for k, n in tally.items():
        if k[0] == "entry":
            gate[("data_abstain", k[2] if k[2] in rt.DATA_ABSTAINS else "none")] += n
    share, gtext = rt.minute_data_gate(gate)
    gate_text = gtext.replace("DATA GATE", "DATA GATE (orh5)")
    say(gate_text)
    say(f"WROTE {tp} ({n_rows:,} rows)")
    if share > rt.DATA_ABSTAIN_MAX:
        say(f"DATA GATE BLOCKS THE READ ({share:.2%} > {rt.DATA_ABSTAIN_MAX:.0%}) - exit 3 BEFORE the report (§3 row 1; F6); the tables stay for inspection")
        return 3
    ref = Path(ctx.out) / f"trades_pre{rt.out_suffix(keys)}.tsv.gz"
    n_cmp, problems = rt.p5_crosscheck(tp, ref, keys)
    if problems:
        say(f"CROSS-CHECK tl/com FAILED against {ref.name}: " + "; ".join(problems) + " - exit 3 before the report")
        return 3
    cross = (f"CROSS-CHECK tl/com: {n_cmp:,} paired p33_s3_t10 rows equal {ref.name}'s orh5 rows (status, maturity, realized R to 1e-09)")
    say(cross)
    # B8: restored fills > 0, and per cell equal to stage 0's restored entry-fact fills on the same bases (window by first-break E year)
    out0, _s = step0_dirs(ctx)
    want = pinned_step0_restored(out0 / STEP0_COUNTS)
    got = {k: n for k, n in rt.h60_pinned_fills(Path(ctx.out), PERIOD, step0_first_rows(rt, out0 / "h60_step0_pre.tsv.gz", rest)).items() if n}
    n_rest, n_all = restored_rows(rt, tp, rest, lambda d: d[(d["arm"] == rt.P5_PRIMARY) & (d["K"] == "tl")])
    say(f"B8 RESTORED (stage 1): {n_rest:,} of {n_all:,} tl fills (arm {rt.P5_PRIMARY}) sit on restored tickers")
    diff = sorted(k for k in set(want) | set(got) if want.get(k, 0) != got.get(k, 0))
    if n_rest == 0 or not want.get(("pre", "C0")):
        say(f"B8 REFUSES: {n_rest} stage-1 fills / {want.get(('pre', 'C0'), 0)} stage-0 C0 fills on restored tickers - the per-cell check would be vacuous")
        return 3
    if diff:
        say("B8 REFUSES: stage 1's restored tl ORH5 fills differ from stage 0's (window, cell: stage 0 / stage 1): "
            + "; ".join(f"{w} {c}: {want.get((w, c), 0)} / {got.get((w, c), 0)}" for w, c in diff))
        return 3
    say(f"B8 RESTORED (stage 1 = stage 0, per window and cell): " + ", ".join(f"{w} {c} {n}" for (w, c), n in sorted(got.items()) if c in ("C0", "C1")))
    df = rt.load_p5_frame(tp, {})
    rows = rt.build_pre_rows(df)
    cols = rt.pre_cols()
    rt.write_tsv(Path(ctx.out) / "p5_report_pre.tsv", rows, cols)
    compact = [{k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()} for r in rows if r["slice"] == "all"]
    rt.write_tsv(small / "p5_report_pre.tsv", compact, cols)
    text = rt.pre_report_text(rows, tp, n_rows, [cross, gate_text])
    (small / "p5_report_pre.txt").write_text(text + "\n")
    print(text)
    say(f"WROTE {Path(ctx.out) / 'p5_report_pre.tsv'} ({len(rows):,} rows), {small / 'p5_report_pre.tsv'}, {small / 'p5_report_pre.txt'}")
    (small / "p5_summary_pre.txt").write_text("\n".join(ctx.log) + "\n")
    _finish(ctx, "v2-pre-read", PRE_OUTPUTS, PRE_SMALL, say)
    return 0


def step0_first_rows(rt, path: Path, rest: frozenset) -> dict:
    """Stage 0's tl bases on restored tickers, read back off its PINNED table as `h60_pinned_fills` takes them: {(ticker, pole_date, "tl"): [the
    first-break row (ticker, D, E)]} - so stage 1 counts its P5 fills on exactly the bases stage 0 counted (first-break E <= 2021-12-31)."""
    df = rt.read_tsv(path, usecols=["ticker", "D", "E", "K", "pole_date", "row_no", "variant"])
    df = df[(df["K"] == "tl") & (df["variant"] == rt.H60_ENTRY) & (df["row_no"] == 0) & df["ticker"].isin(rest)]     # one row per base
    return {(t, str(pd_), "tl"): [{"ticker": t, "D": str(d), "E": str(e)}] for t, d, e, pd_ in df[["ticker", "D", "E", "pole_date"]].itertuples(index=False)}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# stage 2: v2-h60-read
# ═════════════════════════════════════════════════════════════════════════════════════════════
H60_OUTPUTS = ("h60_step0_pre.tsv.gz", "h60_step0_pre.txt", "trades_pre_h60twin.tsv.gz", "trades_pre_h60.tsv.gz", "h60_pairs_pre.tsv.gz",
               "h60_report_pre.tsv", "h60_report_pre.txt", "h60_verdict_pre.json", "h60_verdict_pre.txt")
H60_SMALL = ("h60_step0_pre.txt", "h60_report_pre.tsv", "h60_report_pre.txt", "h60_verdict_pre.txt", "h60_summary_pre.txt")


def h60_prepare(ctx) -> dict:
    rt = ctx.rt
    g = guard_small_and_manifest(ctx, H60_SMALL, ("trades_pre_p5.tsv.gz",))
    prep = rt.h60_prepare(_ns(ctx, out=None), ctx.dirs, PERIOD)
    rows = [r for rs in prep["bases"].values() for r in rs]
    return {"rows": rows, "inp": prep["inp"], "path": Path(ctx.out) / "candidates_tl_com.tsv",
            "opens": _opens(ctx) + [Path(ctx.out) / "watch_tl_com.tsv.gz", old_dir(ctx) / "out" / "h60_verdict_pre.json",
                                    step0_dirs(ctx)[0] / STEP0_COUNTS], "h60": prep,
            "restored": restored(ctx), **g}


def h60_outputs(ctx) -> tuple:
    return H60_OUTPUTS


def h60_dry_run(ctx, prep, existing) -> str:
    return _dry(ctx, prep, existing, "V2-H60-READ")


def old_note(old_json: Path, pairs: tuple, rt) -> list:
    """The old-versus-v2 note (decides nothing) against the OLD file's pre verdict - the 2025-26 verdicts are never opened (§4 (e))."""
    if not old_json.is_file():
        return [f"old file ({OLD_NAME}) pre: no verdict file at {old_json} - no note"]
    o = json.loads(old_json.read_text())
    out = []
    for what, old_v, new_v in pairs(o):
        out.append(f"old file ({OLD_NAME}) pre: {what} {rt.h60_sign(old_v)} vs v2 {rt.h60_sign(new_v)} -> "
                   f"{'same sign' if rt.h60_sign(old_v) == rt.h60_sign(new_v) else 'sign differs'} (decides nothing)")
    return out


def h60_body(ctx, prep, say):
    try:
        with calendar_guard(ctx.rt, _sessions(ctx), say):
            return _h60_body(ctx, prep, say)
    except Refuse as r:
        say(f"REFUSED: {r}")
        return r.code


def _h60_body(ctx, prep, say):
    rt = ctx.rt
    small = small_dir(ctx)
    small.mkdir(parents=True, exist_ok=True)
    out = Path(ctx.out)
    h = prep["h60"]
    bases, inp, rest = h["bases"], prep["inp"], prep["restored"]
    expected, b8 = parse_section5(doc_path(ctx).read_text(encoding="utf-8"))
    say(f"V2-H60-READ: {len(bases):,} bases, {sum(len(rs) for rs in bases.values()):,} rows, {len(inp['pairs']):,} pairs all logged; STEP 0 against the "
        f"doc's §5 v2 table; restored tickers {len(rest):,}")
    # BEFORE STEP 0 writes anything (its names are once-only): the doc's §5 must be stage 0's pinned counts, and the tl rows must be §5's
    counts_json = step0_dirs(ctx)[0] / STEP0_COUNTS
    s5_exp, s5_b8 = section5_from_counts(json.loads(counts_json.read_text()))
    pre = [f"{w} {k}: §5 {expected[w].get(k)} vs stage 0 {v}" for w in WINDOWS for k, v in s5_exp[w].items() if expected[w].get(k) != v]
    pre += [f"{w} {k}: §5 {expected[w][k]} is not a stage-0 key" for w in WINDOWS for k in expected[w] if k not in s5_exp[w]]
    pre += [f"{w} B8 {k}: §5 {b8[w].get(k)} vs stage 0 {v}" for w in WINDOWS for k, v in s5_b8[w].items() if b8[w].get(k) != v]
    if h["label_rows"] != expected["pre"].get("tl_rows"):
        pre.append(f"TL ROWS by label / file {h['label_rows']} != §5 {expected['pre'].get('tl_rows')}")
    if pre:
        say(f"REFUSED before STEP 0 (nothing written): the doc's §5 is not stage 0's pinned counts ({counts_json.name}) or the tl rows differ: "
            + "; ".join(pre))
        return 2
    say(f"§5 = stage 0's pinned counts ({counts_json.name}) in every cell; TL ROWS by label / file {h['label_rows']} = §5 -> STEP 0 may run")
    t = time.time()
    s0 = rt.h60_step0(bases, inp, ctx.workers, PERIOD, out, small, rt.h60_pinned_fills(out, PERIOD, bases), expected=expected)
    say(f"[STEP 0: {time.time() - t:.0f}s]")
    print(s0["text"])
    refuse = []
    for wname, pr in s0["problems"].items():
        refuse += [f"{wname}: {p}" for p in (pr if pr is not None else ["no registered table was compared"])]
    split = step0_split_counts(rt, bases, s0["facts"], s0["pick"], rest)["b8"]
    for wname in WINDOWS:
        if split[wname] != b8[wname]:
            refuse.append(f"{wname}: B8 split shared / restored {split[wname]['shared']} / {split[wname]['restored']} != §5 {b8[wname].get('shared')} / "
                          f"{b8[wname].get('restored')}")
    if s0["early_problems"]:
        refuse += s0["early_problems"]
    if s0["data_share"] > rt.H60_DATA_ABSTAIN_MAX:
        refuse.append(f"data-abstain share {s0['data_share']:.2%} > {rt.H60_DATA_ABSTAIN_MAX:.0%}")
    if refuse:
        say("REFUSED before any exit: STEP 0 does not pass the registered checks: " + "; ".join(refuse))
        return 2
    say(f"STEP 0 CHECKS: the §5 v2 table EQUAL in every window (and the B8 split); early-close ok; data-abstain share {s0['data_share']:.2%}; 0 missing pairs")
    t = time.time()
    tin = rt.h60_twin_inputs(_ns(ctx), ctx.dirs, PERIOD)
    twin, _tally, n_tw = rt.p5_walk(tin, ctx.workers, PERIOD, say, name=rt.H60_TWIN)
    pinned = out / "trades_pre_p5.tsv.gz"
    tw_problems = rt.h60_twin_check(twin, pinned)
    if tw_problems:
        say(f"TWIN CHECK FAILED - the ORH5 re-walk ({twin.name}, {n_tw:,} rows) is not {pinned.name}: " + "; ".join(tw_problems) + " - the report is NOT written")
        return 3
    say(f"TWIN CHECK: {twin.name} ({n_tw:,} rows) equals {pinned.name} in content (sha256 {rt.gz_content_sha(twin)[:12]}) [{time.time() - t:.0f}s]")
    tp, tally = rt.h60_exits(bases, inp, s0["pick"], rt._G["D"], ctx.workers, PERIOD, out, say)
    ent = Counter()
    for (v, sv, st, rs), n in tally.items():
        ent[(v, sv, st + ((" " + rs) if rs else ""))] += n
    say("ENTRIES WALKED (entry / stop: status n): " + "; ".join(f"{v}/{sv} {st} {n:,}" for (v, sv, st), n in sorted(ent.items())))
    say(f"WROTE {tp}")
    n_rest, n_all = restored_rows(rt, tp, rest, lambda d: d[(d["arm"] == rt.H60_ARM) & (d["K"] == "tl")])
    say(f"B8 RESTORED (stage 2): {n_rest:,} of {n_all:,} tl h60-table walks (arm {rt.H60_ARM}) sit on restored tickers")
    if n_rest == 0:
        say("B8 REFUSES: 0 stage-2 rows on restored tickers - the report is NOT written")
        return 3
    pairs_rows = rt.h60_pair_rows(bases, s0["facts"], s0["pick"], rt.h60_load_twin_side(twin), rt.h60_load_trade_side(tp), PERIOD)
    pp = out / "h60_pairs_pre.tsv.gz"
    rt.write_tsv(pp, pairs_rows, rt.H60_PAIR_COLS, gz=True)
    say(f"WROTE {pp} ({len(pairs_rows):,} bases)")
    df, pf = rt.h60_load_frame(tp, pp)
    rows, verdicts = rt.h60_report_rows(df, pf, PERIOD)
    twin_c0 = None
    try:
        tw = rt.read_tsv(twin, usecols=["K", "arm", "C0", "realized_r", "mature"])
        tw = tw[(tw["K"] == "tl") & (tw["arm"] == rt.H60_ARM) & (tw["C0"] == 1) & (tw["mature"] == 1)]
        r = tw["realized_r"].to_numpy(dtype=float)
        twin_c0 = {"mean_r": float(r.mean()), "win_rate": float((r > 0).mean()), "share_ge10": float((r >= 10).mean())} if len(r) else None
    except Exception as exc:                       # the baseline line is informative only; the twin itself was checked above
        say(f"  ! ORH5 C0 baseline not read from the twin: {exc!r}")
    main_w = verdicts.get(PERIOD, {})
    c1m, dm = main_w.get("c1", {}).get("mean_r"), main_w.get("pairs", {}).get("C1", {}).get("mean")
    stamps = old_note(old_dir(ctx) / "out" / "h60_verdict_pre.json",
                      lambda o: (("C1 mean R", o.get("windows", {}).get("pre", {}).get("c1_mean_r"), c1m),
                                 ("paired delta", o.get("windows", {}).get("pre", {}).get("delta_c1"), dm)), rt)
    notes = [f"DATA CHECKS: freeze {ctx.freeze}; STEP 0 equal to the doc's §5 v2 table; early-close ok; data-abstain share {s0['data_share']:.2%}; twin "
             f"equal in content to {pinned.name}; rows walked {sum(tally.values()):,}; B8 restored rows {n_rest:,}"]
    text = rt.h60_report_text(PERIOD, rows, verdicts, notes, twin_c0, stamps, df)
    name = "h60_report_pre"
    rt.write_tsv(out / f"{name}.tsv", rows, rt.H60_REPORT_COLS)
    compact = [{k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()} for r in rows if r["slice"] in ("all", "own_C1", "no_gap")]
    rt.write_tsv(small / f"{name}.tsv", compact, rt.H60_REPORT_COLS)
    (small / f"{name}.txt").write_text(text + "\n")
    (out / f"{name}.txt").write_text(text + "\n")
    print(text)
    vj = {"period": PERIOD, "windows": {}}
    vlines = [f"#702 h60 C1 VERDICT FILE - period {PERIOD} - written {time.strftime('%Y-%m-%d')}"]
    for wname, v in verdicts.items():
        c1, pv = v["c1"], v["pairs"]
        p1 = pv.get("C1", {})
        vj["windows"][wname] = {"c1_verdict": c1.get("verdict"), "c1_why": c1.get("why"), "c1_n": c1.get("n"), "c1_mean_r": c1.get("mean_r"),
                                "c1_ci": [c1.get("ci_lo"), c1.get("ci_hi")], "delta_c1": p1.get("mean"), "delta_c1_ci": [p1.get("lo"), p1.get("hi")],
                                "pair_verdict_c1": p1.get("verdict"), "stop_carry_c1": p1.get("stop", {}).get("carry"),
                                "delta_c0_lo": pv.get("C0", {}).get("lo"), "consequence": "decides nothing"}
        w = vj["windows"][wname]
        vlines.append(f"{wname}: C1 {w['c1_verdict']} ({w['c1_why']}); n {w['c1_n']}; mean R {rt._num(w['c1_mean_r'])} {rt._ci({'ci_lo': w['c1_ci'][0], 'ci_hi': w['c1_ci'][1]})}; "
                      f"paired entry {w['pair_verdict_c1']} (delta {rt._num(w['delta_c1'])}); stop carried {w['stop_carry_c1']}; consequence: {w['consequence']}")
    (out / "h60_verdict_pre.json").write_text(json.dumps(vj, indent=1) + "\n")
    (out / "h60_verdict_pre.txt").write_text("\n".join(vlines) + "\n")
    (small / "h60_verdict_pre.txt").write_text("\n".join(vlines) + "\n")
    say(f"WROTE {out / (name + '.tsv')} ({len(rows):,} rows), {small / (name + '.txt')}, {out / 'h60_verdict_pre.json'}")
    (small / "h60_summary_pre.txt").write_text("\n".join(ctx.log) + "\n")
    _finish(ctx, "v2-h60-read", H60_OUTPUTS, H60_SMALL, say)
    return rr.Verdict(vj, tuple(vlines))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# stage 3: v2-exit-read
# ═════════════════════════════════════════════════════════════════════════════════════════════
EXIT_OUTPUTS = ("trades_pre_exitpb.tsv.gz", "exitpb_report_pre.tsv", "exitpb_deltas_pre.tsv", "exitpb_report_pre.txt", "exitpb_verdict_pre.json",
                "exitpb_verdict_pre.txt")
EXIT_SMALL = ("exitpb_report_pre.tsv", "exitpb_deltas_pre.tsv", "exitpb_report_pre.txt", "exitpb_verdict_pre.txt", "exitpb_summary_pre.txt")


def exit_prepare(ctx) -> dict:
    rt = ctx.rt
    g = guard_small_and_manifest(ctx, EXIT_SMALL, ("trades_pre_p5.tsv.gz", "trades_pre_h60.tsv.gz"))
    if g["manifest_problems"]:                       # a dry run with a broken upstream: report it, do not open the tables
        return {"rows": [], "inp": None, "opens": _opens(ctx), "restored": restored(ctx), "exit": None, **g}
    prep = rt.exitpb_prepare(ctx.dirs, PERIOD)
    return {"rows": prep["trades"], "inp": prep["inp"], "opens": _opens(ctx) + [old_dir(ctx) / "out" / "exitpb_verdict_pre.json"], "exit": prep,
            "restored": restored(ctx), **g}


def exit_outputs(ctx) -> tuple:
    return EXIT_OUTPUTS


def exit_dry_run(ctx, prep, existing) -> str:
    return _dry(ctx, prep, existing, "V2-EXIT-READ")


def exit_body(ctx, prep, say):
    try:
        with calendar_guard(ctx.rt, _sessions(ctx), say):
            return _exit_body(ctx, prep, say)
    except Refuse as r:
        say(f"REFUSED: {r}")
        return r.code


def _exit_body(ctx, prep, say):
    rt = ctx.rt
    small = small_dir(ctx)
    small.mkdir(parents=True, exist_ok=True)
    xp = prep["exit"]
    out, trades, inp, rest = xp["out"], xp["trades"], xp["inp"], prep["restored"]
    counts = Counter((t["entry"], t["K"]) for t in trades)
    pop = ", ".join(f"{e}/{k} {n:,}" for (e, k), n in sorted(counts.items()))
    n_rest = sum(1 for t in trades if t["ticker"] in rest and t["entry"] == "orh5" and t["K"] == "tl")
    say(f"V2-EXIT-READ: {len(trades):,} pinned fills ({pop}) on {len(inp['by_date']):,} dates; module sha256 {rt.sha256_file(Path(ctx.repo) / MODULE_REL)} "
        f"(hard pin); B8 restored orh5 / tl fills {n_rest:,}")
    if n_rest == 0:
        say("B8 REFUSES: 0 exit-read fills on restored tickers")
        return 3
    pc, problems, reach = rt.exitpb_parity(xp, ctx.workers, say)
    n_par = sum(pc.values())
    if problems:
        say(f"PARITY FAILED: {len(problems):,} mismatches over {n_par:,} fills - nothing is written. First 20:")
        for p in problems[:20]:
            say("  - " + p)
        return 3
    say("PARITY: " + "; ".join(f"P{1 if e == 'orh5' else 2} {e}/{k}: {n:,} match, 0 mismatch" for (e, k), n in sorted(pc.items())))
    say(rt.exitpb_reach_text(reach, PERIOD))
    tp, tally, problems = rt.exitpb_walk_all(xp, ctx.workers, PERIOD, say)
    if problems or tp is None:
        say(f"PARITY FAILED in the full walk: {len(problems):,} mismatches - nothing kept")
        return 3
    say(f"WROTE {tp} ({sum(n for k, n in tally.items() if k[0] == 'walked'):,} fills x {len(rt.EXITPB_ARMS)} arms)")
    df = rt.exitpb_load_frame(tp)
    cp, check_lines = rt.exitpb_self_checks(df, PERIOD)
    for ln in check_lines:
        say("  " + ln)
    if cp:
        say(f"IMPLEMENTATION CHECK FAILED ({len(cp)}): " + "; ".join(cp) + " - the report is NOT written")
        return 3
    rows, deltas, verdicts = rt.exitpb_report_rows(df, PERIOD)
    main_v = verdicts.get(rt.EXITPB_ENTRY, {})
    d1 = main_v.get("deltas", {}).get(("C1", rt.EXITPB_PRIMARY, rt.EXITPB_RULED), {})
    d0 = main_v.get("deltas", {}).get(("C0", rt.EXITPB_PRIMARY, rt.EXITPB_RULED), {})
    stamps = old_note(old_dir(ctx) / "out" / "exitpb_verdict_pre.json", lambda o: (("C1 delta(pp_wbe - pp)", o.get("delta_c1", {}).get("mean"), d1.get("mean")),), rt)
    notes = [f"DATA CHECKS: freeze {ctx.freeze}; module {MODULE_SHA[:12]}... equal; parity P1 / P2 {n_par:,} fills, 0 mismatches; implementation checks "
             f"passed; rows walked {sum(n for k, n in tally.items() if k[0] == 'walked'):,} x {len(rt.EXITPB_ARMS)} arms; B8 restored fills {n_rest:,}"]
    text = rt.exitpb_report_text(PERIOD, rows, verdicts, notes, check_lines, stamps)
    name = "exitpb_report_pre"
    rt.write_tsv(out / f"{name}.tsv", rows, rt.EXITPB_REPORT_COLS)
    rt.write_tsv(out / "exitpb_deltas_pre.tsv", deltas, rt.EXITPB_DELTA_COLS)
    compact = [{k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()} for r in rows if r["slice"] == "all"]
    rt.write_tsv(small / f"{name}.tsv", compact, rt.EXITPB_REPORT_COLS)
    rt.write_tsv(small / "exitpb_deltas_pre.tsv", [{k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()} for r in deltas], rt.EXITPB_DELTA_COLS)
    (small / f"{name}.txt").write_text(text + "\n")
    (out / f"{name}.txt").write_text(text + "\n")
    print(text)
    c1 = main_v.get("c1", {})
    carried, ctext = None, "decides nothing"
    vj = {"period": PERIOD, "delta_c1": {k: d1.get(k) for k in ("n", "mean", "lo", "hi", "verdict", "n_excluded_open", "n_differ")},
          "delta_c0": {k: d0.get(k) for k in ("n", "mean", "lo", "hi", "verdict", "n_excluded_open", "n_differ")},
          "cell_c1_pp_wbe": {"n": c1.get("n"), "mean_r": c1.get("mean_r"), "ci": [c1.get("ci_lo"), c1.get("ci_hi")], "verdict": c1.get("verdict"), "why": c1.get("why")},
          "consequence": ctext, "carried_exit": carried}
    vlines = [f"#702 EXIT READ VERDICT FILE - period {PERIOD} - written {time.strftime('%Y-%m-%d')}",
              f"C1 delta(pp_wbe - pp): {d1.get('verdict')} (n {d1.get('n')}, mean {rt._num(d1.get('mean'), 4)} {rt._ci({'ci_lo': d1.get('lo'), 'ci_hi': d1.get('hi')})}); "
              f"C0: {d0.get('verdict')} (n {d0.get('n')}, mean {rt._num(d0.get('mean'), 4)} {rt._ci({'ci_lo': d0.get('lo'), 'ci_hi': d0.get('hi')})}); "
              f"C1 cell under pp_wbe: {c1.get('verdict')} ({c1.get('why')}); consequence: {ctext}; carried exit: {carried}"]
    (out / "exitpb_verdict_pre.json").write_text(json.dumps(vj, indent=1) + "\n")
    (out / "exitpb_verdict_pre.txt").write_text("\n".join(vlines) + "\n")
    (small / "exitpb_verdict_pre.txt").write_text("\n".join(vlines) + "\n")
    say(f"WROTE {out / (name + '.tsv')} ({len(rows):,} rows), {out / 'exitpb_deltas_pre.tsv'} ({len(deltas):,} rows), {small / (name + '.txt')}, "
        f"{out / 'exitpb_verdict_pre.json'}")
    (small / "exitpb_summary_pre.txt").write_text("\n".join(ctx.log) + "\n")
    _finish(ctx, "v2-exit-read", EXIT_OUTPUTS, EXIT_SMALL, say)
    return rr.Verdict(vj, tuple(vlines))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the four specs
# ═════════════════════════════════════════════════════════════════════════════════════════════
def make_specs(export_sha: str = V2_EXPORT_SHA) -> dict:
    """The four reads. `export_sha` is the ONE injection point (the parity harness on the old file's copy passes that copy's sha; the registered
    reads below use the v2 export's)."""
    pins = hard_pins(export_sha)
    common = dict(periods=(PERIOD,), refused=REFUSED, hard_pins=pins)
    specs = [rr.RegisteredRead(name="v2-h60-step0", tag=TAGS["step0"], doc=None, frozen=v2_frozen, prepare=step0_prepare, outputs=step0_outputs,
                               dry_run=step0_dry_run, body=step0_body, **common),
             rr.RegisteredRead(name="v2-pre-read", tag=TAGS["pre"], doc=V2_DOC, frozen=v2_frozen, prepare=pre_prepare, outputs=pre_outputs,
                               dry_run=pre_dry_run, body=pre_body, **common),
             rr.RegisteredRead(name="v2-h60-read", tag=TAGS["h60"], doc=V2_DOC, frozen=v2_frozen, prepare=h60_prepare, outputs=h60_outputs,
                               dry_run=h60_dry_run, body=h60_body, **common),
             rr.RegisteredRead(name="v2-exit-read", tag=TAGS["exit"], doc=V2_DOC, frozen=v2_frozen, prepare=exit_prepare, outputs=exit_outputs,
                               dry_run=exit_dry_run, body=exit_body, **common)]
    return {s.name: s for s in specs}


REGISTERED = make_specs()


def runner_calls(src: str) -> list:
    """B1 / §8: the runner functions this module's bodies reach - every call `rt.<name>(...)` / `ctx.rt.<name>(...)`, by an AST walk of the source
    (never typed by hand; `V2_RUNNER_CALLS` is asserted equal to it in the tests). Sorted."""
    import ast
    names = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            v = n.func.value
            if (isinstance(v, ast.Name) and v.id == "rt") or (isinstance(v, ast.Attribute) and v.attr == "rt"):
                names.add(n.func.attr)
    return sorted(names)


def main(argv=None) -> int:
    """`fill-section5 COUNTS.json [DOC]`: print the doc with §5's (B2) cells filled from stage 0's counts json (the main loop reviews and writes it).
    `print-calls`: the runner functions the v2 bodies call (the AST walk of this module) - pasted below the doc's freeze marker (§8)."""
    a = list(sys.argv[1:] if argv is None else argv)
    if a[:1] == ["print-calls"]:
        calls = runner_calls(Path(__file__).read_text(encoding="utf-8"))
        print(f"- v2 bodies' runner calls (AST walk of {Path(__file__).name}, sha256 {rr.sha256_file(Path(__file__))[:16]}): " + ", ".join(f"`{c}`" for c in calls))
        return 0
    if len(a) >= 2 and a[0] == "fill-section5":
        doc = Path(a[2]) if len(a) > 2 else Path(__file__).resolve().parents[3] / "docs" / "analysis" / V2_DOC
        sys.stdout.write(fill_section5(doc.read_text(encoding="utf-8"), json.loads(Path(a[1]).read_text())))
        return 0
    print(main.__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
