#!/usr/bin/env python3
"""#705 v2 re-run, STAGE 7 (B7) - the comparison, written and pinned BEFORE the freeze (docs/analysis/cb_2017_21_rerun_v2_prereg_2026-10-25.md §7).

Every §7 line is read from the source §7's sources table names - OLD from the published location, NEW from the same file and key written by the chain
(read dirs: `<read dir>/rerun_v2_1025/`; data tables: `cb702_pre_v2/out/rerun_v2_1025/<read>/`; the runner's small report: `_cb_backtest/out/v2_1025/`;
the runner's verdicts: `cb702_pre_v2/out/`) - and the line's rule is applied mechanically:
  R1 an interval: class ABOVE (lo > 0) / SPANS / BELOW (hi < 0); holds = same class; "moved" = same class, the new point outside the old interval
  R2 a verdict word: holds = the same word
  R3 a share: tolerance = max(2, min(5, old share / 2)) points; holds = within it. Printed beside: the line's restored fraction and the
     restored-minus-survivor gap the band could detect (tolerance / restored fraction)
  R4 a best cell: holds = the old best is the new best, or within 2 points of it on the same share (named as a tie)
  R5 a median: holds = same sign and within 25% of the old; same sign but further = "moved" (counts as holds, named); a sign flip = changes
  R6 a count: never a test - old / new / ratio
A read's conclusion holds when every DECIDING line holds (a "moved" holds and is named); else it changes and the lines are named. A failed CHECK line
(2.0, 4.0) means that read's numbers are not compared at all. Beside lines and the restored-only values decide nothing.
Restored-only beside value (B8) on every deciding line: the point estimate on the restored tickers' rows only (v2 guard minus the old guard), computed
on the read's own row table, ENTRY SIDE (a matched control is not re-matched for a subset) and only when the same computation on ALL rows reproduces the
read's own published number (else "withheld: the method does not reproduce"). On the old file it reads "none (no restored row)".

A value that is not finite (NaN / inf, or a share of 0 rows) is never compared: the line reads NOT COMPARED and, on a deciding line, so does the
read's conclusion (a broken resample must never read "holds").

    python3 v2_compare.py        # THE REAL RUN, ONCE: old (published) vs new (the chain) -> v2_compare.txt beside this file. It takes NO option.
    python3 v2_compare.py --proofs --new-flat DIR [--old-flat DIR] --out FILE [--expect-episodes N] [--guards NEW OLD]   # the proofs only
The real run refuses (exit 2, nothing written) when: v2_compare.txt or its .partial exists (once-only); any of the five proof options is given
without --proofs; a new source is not a chain path (rerun_v2_1025/, v2_1025/, cb702_pre_v2/out/) or equals its old path; the §7 tables of the doc
(above the freeze marker) do not match this script's lines, roles and rules; an old source or this script's own code is not its §8 footer pin;
the full §8 freeze re-check (`runner.py v2-exit-read --dry-run`) fails; a new source is not its chain-manifest line (§8: stage 7 reads only what
the chain wrote); a source is missing. A failed source check (an old value read is not the value §7 quotes) writes a refusal record to
v2_compare.txt (the failure is the result) and exits 2 - no verdict is issued. Every source's sha256 is printed into the record.
--proofs never writes v2_compare.txt (its --out must be another file) and skips the freeze / pin / manifest checks (the proofs read flat copies).
Opens no price bar. Exit 0 = compared (the verdicts are the result); 2 = refused.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from scripts.probes._cb_backtest import v2_chain as v2c  # noqa: E402  (the 4.0 parity: one definition, shared with 04_relaunch.sh)
PROBES = REPO / "scripts" / "probes"
OLD_DATA, V2_DATA = Path("/Users/alvinfung/apollo_data/cb702_pre"), Path("/Users/alvinfung/apollo_data/cb702_pre_v2")
SUB = "rerun_v2_1025"
R1D, R2D, R3D, R4D = "_702_breakout_definition_1022", "_702_winner_recall_1022", "_702_entry_stop_retry_1022", "_702_trail_variants_1023"
OUT = Path(__file__).resolve().parent / "v2_compare.txt"
Q = "ADR decile x 63-session return quintile|"
R1KEY = "2017-21|R1 base-high close — entry at that close"
R2KEY = "2017-21|R2 expansion breakout — entry at that close"
FUNNEL = {"covered": "… whose base nights our watch covers", "watched": "… WATCHED (a watch row on some base night)",
          "triggered": "… TRIGGERED (a tl ORH5 fill, E in the catch window)", "still": "… triggered and STILL IN at s50 (half the gain made)",
          "kept": "… triggered and KEPT >= half of the episode's gain"}
TRAIL_CELLS = ("A20_X1_P1", "A10_X1_P1", "A10_X1_P0", "A10_X2_P1", "A10_X2_P0", "A10_X3_P1", "A10_X3_P0", "A10_X4_P1", "A10_X4_P0", "A20_X1_P0",
               "A20_X2_P1", "A20_X2_P0", "A20_X3_P1", "A20_X3_P0", "A20_X4_P1", "A20_X4_P0")
V2_EPISODES_N = 1181                                     # 2.0: the relaunch must reproduce the 10-23 v2 big-winner count


# ═══ the sources (§7's table) ═══════════════════════════════════════════════════════════════════════════════════════════════════════
LOGICAL = {   # logical name -> (old path, new path)
    "read1_03_numbers.json": (PROBES / R1D / "03_numbers.json", PROBES / R1D / SUB / "03_numbers.json"),
    "read1_03_report.md": (PROBES / R1D / "03_report.md", PROBES / R1D / SUB / "03_report.md"),
    "read2_03_numbers.json": (PROBES / R2D / "03_numbers.json", PROBES / R2D / SUB / "03_numbers.json"),
    "read3_03_headline.json": (PROBES / R3D / "03_headline.json", PROBES / R3D / SUB / "03_headline.json"),
    "read4_03_headline.json": (PROBES / R4D / "03_headline.json", PROBES / R4D / SUB / "03_headline.json"),
    "p5_report_pre.tsv": (PROBES / "_cb_backtest" / "out" / "p5_report_pre.tsv", PROBES / "_cb_backtest" / "out" / "v2_1025" / "p5_report_pre.tsv"),
    "h60_verdict_pre.json": (OLD_DATA / "out" / "h60_verdict_pre.json", V2_DATA / "out" / "h60_verdict_pre.json"),
    "exitpb_verdict_pre.json": (OLD_DATA / "out" / "exitpb_verdict_pre.json", V2_DATA / "out" / "exitpb_verdict_pre.json"),
    "bdef_fills_2017-21.tsv.gz": (OLD_DATA / "out" / "bdef_fills_2017-21.tsv.gz", V2_DATA / "out" / SUB / "breakout_definition" / "bdef_fills_2017-21.tsv.gz"),
    "bdef_r1_2017-21.tsv.gz": (OLD_DATA / "out" / "bdef_r1_2017-21.tsv.gz", V2_DATA / "out" / SUB / "breakout_definition" / "bdef_r1_2017-21.tsv.gz"),
    "wrecall_catch_2017-21_x200.tsv.gz": (OLD_DATA / "out" / "wrecall_catch_2017-21_x200.tsv.gz",
                                          V2_DATA / "out" / SUB / "winner_recall" / "wrecall_catch_2017-21_x200.tsv.gz"),
    "esr_win_2017-21.tsv.gz": (OLD_DATA / "out" / "esr_win_2017-21.tsv.gz", V2_DATA / "out" / SUB / "entry_stop_retry" / "esr_win_2017-21.tsv.gz"),
    "esr_r1_2017-21.tsv.gz": (OLD_DATA / "out" / "esr_r1_2017-21.tsv.gz", V2_DATA / "out" / SUB / "entry_stop_retry" / "esr_r1_2017-21.tsv.gz"),
    "trail_win_2017-21.tsv.gz": (OLD_DATA / "out" / "trail_win_2017-21.tsv.gz", V2_DATA / "out" / SUB / "trail_variants" / "trail_win_2017-21.tsv.gz"),
    "trail_r1_2017-21.tsv.gz": (OLD_DATA / "out" / "trail_r1_2017-21.tsv.gz", V2_DATA / "out" / SUB / "trail_variants" / "trail_r1_2017-21.tsv.gz"),
}
TABLES = tuple(k for k in LOGICAL if k.endswith(".tsv.gz"))
# where a NEW source may live: the chain's outputs only (never an old location, never a hand-made dir)
NEW_ROOTS = (V2_DATA / "out", PROBES / "_cb_backtest" / "out" / "v2_1025") + tuple(PROBES / d / SUB for d in (R1D, R2D, R3D, R4D))
# every OLD (non-table) source -> its §8 footer label (v2_rerun_read.v2_frozen): stage 7 re-proves each against the freeze before reading it. The
# old row tables are never read (the restored-only values are computed on the NEW side only).
OLD_PINS = {"read1_03_numbers.json": "read1/03_numbers.json", "read1_03_report.md": "read1/03_report.md", "read2_03_numbers.json": "read2/03_numbers.json",
            "read3_03_headline.json": "read3/03_headline.json", "read4_03_headline.json": "read4/03_headline.json",
            "p5_report_pre.tsv": "_cb_backtest/out/p5_report_pre.tsv", "h60_verdict_pre.json": "cb702_pre/out/h60_verdict_pre.json",
            "exitpb_verdict_pre.json": "cb702_pre/out/exitpb_verdict_pre.json"}
CODE_PINS = {"code/v2_compare.py": Path(__file__).resolve(), "code/v2_chain.py": Path(v2c.__file__).resolve()}
DOC = REPO / "docs" / "analysis" / "cb_2017_21_rerun_v2_prereg_2026-10-25.md"
PROOF_OPTS = ("old_flat", "new_flat", "out", "expect_episodes", "guards")
NC = "NOT COMPARED"


def logical_problems() -> list:
    """The sources table itself: every NEW path is a chain path (under NEW_ROOTS, with a manifest label) and differs from its OLD path; no OLD
    path lies under a chain root; every old non-table source carries a footer pin."""
    out = []
    for k, (o, n) in LOGICAL.items():
        o, n = Path(o), Path(n)
        if o == n or o.resolve() == n.resolve():
            out.append(f"{k}: the new path is the old path ({n})")
        if not any(n.is_relative_to(r) for r in NEW_ROOTS):
            out.append(f"{k}: the new path {n} is not under a chain output root {[str(r) for r in NEW_ROOTS]}")
        if any(o.is_relative_to(r) for r in NEW_ROOTS):
            out.append(f"{k}: the old path {o} lies under a chain output root")
        try:
            v2c.chain_label(n)
        except ValueError as exc:
            out.append(f"{k}: {exc}")
    for k in LOGICAL:
        if k not in TABLES and k not in OLD_PINS:
            out.append(f"{k}: an old source with no §8 footer pin")
    return out


class Src:
    def __init__(self, side: str, flat: "Path | None" = None):
        self.side, self.flat, self._c = side, flat, {}

    def path(self, name: str) -> Path:
        return (self.flat / name) if self.flat else LOGICAL[name][0 if self.side == "old" else 1]

    def json(self, name):
        if name not in self._c:
            self._c[name] = json.loads(self.path(name).read_text())
        return self._c[name]

    def text(self, name):
        if name not in self._c:
            self._c[name] = self.path(name).read_text()
        return self._c[name]

    def table(self, name, cols=None):
        key = (name, tuple(cols) if cols else None)
        if key not in self._c:
            self._c[key] = pd.read_csv(self.path(name), sep="\t", low_memory=False, usecols=cols, keep_default_na=False, na_values=[""])
        return self._c[key]

    def p5(self):
        if "p5" not in self._c:
            self._c["p5"] = pd.read_csv(self.path("p5_report_pre.tsv"), sep="\t", keep_default_na=False, na_values=[""], low_memory=False)
        return self._c["p5"]


# ═══ the getters: one per §7 line (the value as the source carries it) ════════════════════════════════════════════════════════════════
A_ROW = re.compile(r"^\| 2017-21 \| n = ([\d,]+) \| (-?[\d.]+) \| [^|]* \| [^|]* \| ([\d,]+) \(([\d.]+)%\) \|", re.M)


def sec_a(s: Src) -> dict:
    """Read 1's 03_report.md §A, the 2017-21 row: n fills, the median fill distance (ADR20), fills at/above the base high (count)."""
    m = A_ROW.search(s.text("read1_03_report.md"))
    if not m:
        raise ValueError(f"{s.path('read1_03_report.md')}: no §A 2017-21 row in the registered layout")
    return {"n": int(m.group(1).replace(",", "")), "median": float(m.group(2)), "at_above": int(m.group(3).replace(",", ""))}


def interval(d: dict, dk="d", lo="lo", hi="hi", nk="n") -> dict:
    return {"d": float(d[dk]), "lo": float(d[lo]), "hi": float(d[hi]), "n": int(d[nk]) if nk in d else None}


def funnel(s: Src, key: str) -> dict:
    f = s.json("read2_03_numbers.json")["2017-21/x200/funnel"][FUNNEL[key]]
    return {"k": int(f[0]), "n": int(f[1])}


def h3(s: Src):
    return s.json("read3_03_headline.json")["2017-21"]


def h4(s: Src):
    return s.json("read4_03_headline.json")["2017-21"]


def p5row(s: Src, window: str, cell: str) -> dict:
    d = s.p5()
    r = d[(d["key"] == "spec") & (d["K"] == "tl") & (d["arm"] == "c3_p33_t20_cut3") & (d["slice"] == "all") & (d["window"] == window) & (d["cell"] == cell)]
    if len(r) != 1:
        raise ValueError(f"p5_report_pre.tsv: {len(r)} rows for window {window} cell {cell}")
    r = r.iloc[0]
    return {"n": int(r["n"]), "d": float(r["mean_r"]), "lo": float(r["ci_lo"]), "hi": float(r["ci_hi"]), "word": str(r["verdict"])}


def best_cell(cells: dict) -> dict:
    """cells = {name: {"k": still in at s50, "n": n}} -> the best by share, every share."""
    sh = {c: v["k"] / v["n"] for c, v in cells.items() if v["n"]}
    best = max(sh, key=lambda c: (sh[c], c))
    return {"best": best, "shares": sh}


# Each line: id, read, role, rule, what, get(src) -> value, doc_old (the value §7 quotes, for the source check), restored (fn(src, rest) -> beside)
def L(id_, read, role, rule, what, get, doc_old=None, restored=None, **kw):
    return dict(id=id_, read=read, role=role, rule=rule, what=what, get=get, doc_old=doc_old, restored=restored, **kw)


# ── restored-only beside values (entry side, reproduced on all rows first) ─────────────────────────────────────────────────────────────
def _fills(s):
    return s.table("bdef_fills_2017-21.tsv.gz", ["ticker", "dist_adr", "s_c", "sc_complete"])


def rb_dist(s, rest, kind):
    f = _fills(s)
    def val(g):
        if kind == "median":
            return float(g.dist_adr.median()), len(g)
        if kind == "at_above":
            return int((g.dist_adr <= 0).sum()), len(g)
        g = g[g.sc_complete == 1]
        return int(((g.s_c >= 0) & (g.s_c <= 60)).sum()), len(g)
    return val(f), val(f[f.ticker.isin(rest)])


def rb_r1(s, rest, key=R1KEY, meas="share >= 5 ADR within 60", r2=False):
    r = s.table("bdef_r1_2017-21.tsv.gz", ["ticker", "cl_c60", "cl_mfe60", "cl_ret60", "r2_exp"])
    if r2:
        r = r[r.r2_exp == 1]
    def val(g):
        g = g[g.cl_c60 == 1]
        return (float((g.cl_mfe60 >= 5).mean()) if meas.startswith("share") else float(g.cl_ret60.mean())), len(g)
    return val(r), val(r[r.ticker.isin(rest)])


def rb_catch(s, rest, key):
    c = s.table("wrecall_catch_2017-21_x200.tsv.gz", ["ticker", "class_p", "covered", "watched", "triggered", "still_in_s50", "kept_half_episode"])
    def val(g):
        cov = g[(g.class_p == "measurable_breakout") & (g.covered == 1)]
        col = {"covered": None, "watched": "watched", "triggered": "triggered", "still": "still_in_s50", "kept": "kept_half_episode"}[key]
        return int(cov[col].fillna(0).astype(float).astype(bool).sum()) if col else len(cov), len(cov)
    return val(c), val(c[c.ticker.isin(rest)])


def _win_cells(df, T, selector):
    """still in at s50 / kept half per base for retries <= T, the read's own rule (02_build: e <= s50 <= exit_idx on any attempt; kept = the chain's
    pnl per share over the episode's gain), over the valid bases."""
    out = {}
    for name, g in df.groupby(selector):
        f0 = g[g.attempt == 0].set_index("base")
        valid = f0.index[f0["valid"] == 1]
        d = g[(g.attempt <= T) & (g.status >= 0)]
        inat = (d.e <= d.s50) & (d.exit_idx >= d.s50)
        still = inat.groupby(d.base).any().reindex(valid).fillna(False)
        gain = (f0.close_p - f0.close_t).reindex(valid)
        kept = d.groupby("base").pnl_ps.sum().reindex(valid) / gain
        out[name] = {"bases": valid, "still": still, "kept": kept, "ticker": f0.ticker.reindex(valid)}
    return out


def rb_win(s, rest, table, selector, name, what):
    cols = ["base", "attempt", "e", "exit_idx", "status", "s50", "valid", "pnl_ps", "close_p", "close_t", "ticker"] + list(selector)
    df = s.table(table, cols + (["variant"] if table.startswith("esr") else []))
    if table.startswith("esr"):
        df = df[df.variant == "close"]
    cells = _win_cells(df, 2, selector[0])
    c = cells[name]
    def val(mask):
        st, kp = c["still"][mask], c["kept"][mask]
        return (int(st.sum()) if what == "still" else int((kp >= 0.5).sum())), int(mask.sum())
    allm = pd.Series(True, index=c["bases"])
    return val(allm), val(c["ticker"].isin(rest))


def rb_gap(s, rest):
    """4.2c: kept-half doublers, A20_X3_P0 minus pp, on all rows / on the restored rows."""
    (xa, na), (xr, nr) = rb_win(s, rest, "trail_win_2017-21.tsv.gz", ("cell",), "A20_X3_P0", "kept")
    (pa, _n), (pr, _r) = rb_win(s, rest, "trail_win_2017-21.tsv.gz", ("cell",), "A20_X1_P1", "kept")
    return (xa - pa, na), (xr - pr, nr)


def rb_r1walk(s, rest, table, sel: dict, what):
    """Entry side of an R1 line: per complete base, the first attempt (T0): mean R and >= 5R per 100 bases."""
    cols = ["base", "attempt", "status", "realized_r", "complete120", "valid", "ticker"] + list(sel)
    df = s.table(table, cols)
    for k, v in sel.items():
        df = df[df[k] == v]
    f0 = df[(df.attempt == 0) & (df.valid == 1) & (df.complete120 == 1)]
    def val(g):
        r = g.realized_r.where(g.status >= 0)
        return (float(r.mean()) if what == "r" else 100.0 * float((r >= 5).mean())), len(g)
    return val(f0), val(f0[f0.ticker.isin(rest)])


LINES = [
    # Read 1
    L("1.1", 1, "deciding", "R5", "our fill's median distance below the base high, ADR20 units", lambda s: sec_a(s)["median"], 1.16,
      restored=lambda s, r: rb_dist(s, r, "median"), reproduce=lambda s: sec_a(s)["median"], fmt="r2"),
    L("1.2", 1, "deciding", "R3", "share of those fills at or above the base high", lambda s: {"k": sec_a(s)["at_above"], "n": sec_a(s)["n"]}, (1098, 13363),
      restored=lambda s, r: rb_dist(s, r, "at_above"), reproduce=lambda s: (sec_a(s)["at_above"], sec_a(s)["n"])),
    L("1.3", 1, "deciding", "R3", "share that close above the base high within 60 sessions",
      lambda s: {"k": s.json("read1_03_numbers.json")["A_sc_2017-21"]["by60"], "n": s.json("read1_03_numbers.json")["A_sc_2017-21"]["n"]}, (10214, 13363),
      restored=lambda s, r: rb_dist(s, r, "by60"), reproduce=lambda s: (s.json("read1_03_numbers.json")["A_sc_2017-21"]["by60"],
                                                                         s.json("read1_03_numbers.json")["A_sc_2017-21"]["n"])),
    L("1.4", 1, "beside", "R6", "first close above it on the fill day / by 5 / by 20 / never",
      lambda s: tuple(s.json("read1_03_numbers.json")["A_sc_2017-21"][k] for k in ("by0", "by5", "by20", "never")), (1548, 4989, 8110, 3149)),
    L("1.5", 1, "beside", "R3", "+5 ADR movers that cleared the base high first",
      lambda s: {"k": s.json("read1_03_numbers.json")["A_big_2017-21_5"]["before"], "n": s.json("read1_03_numbers.json")["A_big_2017-21_5"]["n"]}, (5675, 5756)),
    L("1.6", 1, "deciding", "R1", "R1: share reaching +5 ADR within 60, entries minus matched control",
      lambda s: interval(s.json("read1_03_numbers.json")[R1KEY][Q + "share >= 5 ADR within 60"]), (0.0109, -0.0069, 0.0292),
      restored=lambda s, r: rb_r1(s, r), reproduce=lambda s: s.json("read1_03_numbers.json")[R1KEY][Q + "share >= 5 ADR within 60"]["e"], entry_side=True),
    L("1.7", 1, "beside", "R1", "R1 mean close return at +60 sessions, ADR, difference",
      lambda s: interval(s.json("read1_03_numbers.json")[R1KEY][Q + "mean close return +60 (ADR)"]), (0.1749, 0.0013, 0.3904)),
    L("1.8", 1, "beside", "R1", "R2 expansion-day breakouts: +5 ADR share, difference",
      lambda s: interval(s.json("read1_03_numbers.json")[R2KEY][Q + "share >= 5 ADR within 60"]), (0.0310, 0.0055, 0.0554)),
    # Read 2
    L("2.0", 2, "check", "CHECK", "big winners kept (the relaunch must reproduce 1,181)", lambda s: s.json("read2_03_numbers.json")["2017-21/x200/composition"]["n"], 994),
    L("2.1", 2, "beside", "R6", "measurable breakouts whose base nights our watch tables cover", lambda s: (funnel(s, "covered")["k"],), (481,)),
    L("2.2", 2, "deciding", "R3", "of those, WATCHED", lambda s: funnel(s, "watched"), (240, 481), restored=lambda s, r: rb_catch(s, r, "watched"),
      reproduce=lambda s: (funnel(s, "watched")["k"], funnel(s, "watched")["n"])),
    L("2.3", 2, "deciding", "R3", "TRIGGERED (a tl opening-range fill in the catch window)", lambda s: funnel(s, "triggered"), (237, 481),
      restored=lambda s, r: rb_catch(s, r, "triggered"), reproduce=lambda s: (funnel(s, "triggered")["k"], funnel(s, "triggered")["n"])),
    L("2.4", 2, "deciding", "R3", "still in the trade when the stock had made half its gain", lambda s: funnel(s, "still"), (25, 481),
      restored=lambda s, r: rb_catch(s, r, "still"), reproduce=lambda s: (funnel(s, "still")["k"], funnel(s, "still")["n"])),
    L("2.5", 2, "deciding", "R3", "kept at least half of the episode's gain", lambda s: funnel(s, "kept"), (3, 481),
      restored=lambda s, r: rb_catch(s, r, "kept"), reproduce=lambda s: (funnel(s, "kept")["k"], funnel(s, "kept")["n"])),
    # Read 3
    L("3.1", 3, "deciding", "R4+R3", "best-holding cell on the doublers: S2 with two retries, still in at half the move",
      lambda s: {**best_cell({k[4:]: {"k": v["still_in_s50"], "n": v["n"]} for k, v in h3(s).items() if k.startswith("win_")}), "named": "S2_T2",
                 "k": h3(s)["win_S2_T2"]["still_in_s50"], "n": h3(s)["win_S2_T2"]["n"]}, (213, 481),
      restored=lambda s, r: rb_win(s, r, "esr_win_2017-21.tsv.gz", ("kind",), "S2", "still"),
      reproduce=lambda s: (h3(s)["win_S2_T2"]["still_in_s50"], h3(s)["win_S2_T2"]["n"])),
    L("3.2", 3, "beside", "R3", "the same cell: kept half", lambda s: {"k": h3(s)["win_S2_T2"]["kept_half"], "n": h3(s)["win_S2_T2"]["n"]}, (8, 481)),
    L("3.2b", 3, "beside", "R3", "the same cell: kept a quarter", lambda s: {"k": h3(s)["win_S2_T2"]["kept_quarter"], "n": h3(s)["win_S2_T2"]["n"]}, (121, 481)),
    L("3.2c", 3, "beside", "R6", "the same cell: retries used, mean", lambda s: (round(h3(s)["win_S2_T2"]["retries_mean"], 6),), (0.657,)),
    L("3.3", 3, "deciding", "R1", "R1, S2, no retry: mean R per base, entries minus control", lambda s: interval(h3(s)["all_S2_T0"]["diff_r_per_base"], "diff"),
      (0.0054, -0.0355, 0.0496), restored=lambda s, r: rb_r1walk(s, r, "esr_r1_2017-21.tsv.gz", {"kind": "S2", "variant": "close"}, "r"),
      reproduce=lambda s: h3(s)["all_S2_T0"]["r_per_base"], entry_side=True),
    L("3.4", 3, "deciding", "R1", "R1, S2, no retry: bases with a >= 5R trade per 100, entries minus control", lambda s: interval(h3(s)["all_S2_T0"]["diff_any5"], "diff"),
      (0.478, 0.138, 0.857), restored=lambda s, r: rb_r1walk(s, r, "esr_r1_2017-21.tsv.gz", {"kind": "S2", "variant": "close"}, "any5"),
      reproduce=lambda s: h3(s)["all_S2_T0"]["any5"], entry_side=True),
    L("3.5", 3, "beside", "R1", "R1, S2, two retries: mean R per base difference", lambda s: interval(h3(s)["all_S2_T2"]["diff_r_per_base"], "diff"), (0.0712, 0.0156, 0.1356)),
    L("3.6", 3, "beside", "R1", "R1, S2, two retries: >= 5R bases per 100", lambda s: interval(h3(s)["all_S2_T2"]["diff_any5"], "diff"), (1.383, 0.995, 1.829)),
    L("3.7", 3, "beside", "R3d", "R1, S2, no retry: share reaching +5R before the stop, entries minus control",
      lambda s: {"e": h3(s)["all_S2_T0"]["race5_hit"], "c": h3(s)["all_S2_T0"]["ctl_race5_hit"]}, (0.1782, 0.1871)),
    # Read 4
    L("4.0", 4, "check", "CHECK", "the pp cell (A20_X1_P1) equals read 3's S2 two-retry cell (win) and S2 no-retry R1, to 1e-9 (v2_chain.pp_parity_problems)",
      lambda s: v2c.pp_parity_problems(s.json("read3_03_headline.json"), s.json("read4_03_headline.json")), None),
    L("4.1", 4, "deciding", "R4+R3", "best-holding cell on the doublers: A20_X3_P0, still in at half",
      lambda s: {**best_cell({c: {"k": h4(s)[c]["win_T2"]["still_in_s50"], "n": h4(s)[c]["win_T2"]["n"]} for c in TRAIL_CELLS}), "named": "A20_X3_P0",
                 "k": h4(s)["A20_X3_P0"]["win_T2"]["still_in_s50"], "n": h4(s)["A20_X3_P0"]["win_T2"]["n"]}, (256, 481),
      restored=lambda s, r: rb_win(s, r, "trail_win_2017-21.tsv.gz", ("cell",), "A20_X3_P0", "still"),
      reproduce=lambda s: (h4(s)["A20_X3_P0"]["win_T2"]["still_in_s50"], h4(s)["A20_X3_P0"]["win_T2"]["n"])),
    L("4.2", 4, "deciding", "R3", "kept at least half: A20_X3_P0", lambda s: {"k": h4(s)["A20_X3_P0"]["win_T2"]["kept_half"], "n": h4(s)["A20_X3_P0"]["win_T2"]["n"]},
      (92, 481), restored=lambda s, r: rb_win(s, r, "trail_win_2017-21.tsv.gz", ("cell",), "A20_X3_P0", "kept"),
      reproduce=lambda s: (h4(s)["A20_X3_P0"]["win_T2"]["kept_half"], h4(s)["A20_X3_P0"]["win_T2"]["n"])),
    L("4.2b", 4, "deciding", "R3", "kept at least half: pp (A20_X1_P1)", lambda s: {"k": h4(s)["A20_X1_P1"]["win_T2"]["kept_half"], "n": h4(s)["A20_X1_P1"]["win_T2"]["n"]},
      (8, 481), restored=lambda s, r: rb_win(s, r, "trail_win_2017-21.tsv.gz", ("cell",), "A20_X1_P1", "kept"),
      reproduce=lambda s: (h4(s)["A20_X1_P1"]["win_T2"]["kept_half"], h4(s)["A20_X1_P1"]["win_T2"]["n"])),
    L("4.2c", 4, "deciding", "SIGN", "the sign of the gap: kept half A20_X3_P0 minus pp",
      lambda s: h4(s)["A20_X3_P0"]["win_T2"]["kept_half"] - h4(s)["A20_X1_P1"]["win_T2"]["kept_half"], 84,
      restored=lambda s, r: rb_gap(s, r), reproduce=lambda s: h4(s)["A20_X3_P0"]["win_T2"]["kept_half"] - h4(s)["A20_X1_P1"]["win_T2"]["kept_half"]),
    L("4.3", 4, "beside", "R5", "median share of the gain kept, A20_X3_P0", lambda s: float(h4(s)["A20_X3_P0"]["win_T2"]["kept_share_q"][1]), 0.0863, fmt="r4"),
    L("4.3b", 4, "beside", "R5", "median share of the gain kept, pp", lambda s: float(h4(s)["A20_X1_P1"]["win_T2"]["kept_share_q"][1]), 0.054, fmt="r4"),
    L("4.3c", 4, "beside", "R5", "median sessions held, A20_X3_P0", lambda s: float(h4(s)["A20_X3_P0"]["win_T2"]["held_chain_q"][1]), 25.0, fmt="r1"),
    L("4.3d", 4, "beside", "R5", "median sessions held, pp", lambda s: float(h4(s)["A20_X1_P1"]["win_T2"]["held_chain_q"][1]), 18.0, fmt="r1"),
    L("4.4", 4, "deciding", "R1", "R1, no retry: mean R per base, entries minus control - pp", lambda s: interval(h4(s)["A20_X1_P1"]["R1_T0"]["diff"], "diff"),
      (0.0054, -0.0355, 0.0496), restored=lambda s, r: rb_r1walk(s, r, "trail_r1_2017-21.tsv.gz", {"cell": "A20_X1_P1"}, "r"),
      reproduce=lambda s: h4(s)["A20_X1_P1"]["R1_T0"]["r_trade"], entry_side=True),
    L("4.4b", 4, "deciding", "R1", "R1, no retry: mean R per base, entries minus control - A20_X3_P0", lambda s: interval(h4(s)["A20_X3_P0"]["R1_T0"]["diff"], "diff"),
      (0.0095, -0.0505, 0.0762), restored=lambda s, r: rb_r1walk(s, r, "trail_r1_2017-21.tsv.gz", {"cell": "A20_X3_P0"}, "r"),
      reproduce=lambda s: h4(s)["A20_X3_P0"]["R1_T0"]["r_trade"], entry_side=True),
    L("4.5", 4, "beside", "R1", "R1, no retry: >= 5R bases per 100, difference - pp", lambda s: interval(h4(s)["A20_X1_P1"]["R1_T0"]["any5_diff"], "diff"), (0.478, 0.138, 0.857)),
    L("4.5b", 4, "beside", "R1", "R1, no retry: >= 5R bases per 100, difference - A20_X3_P0", lambda s: interval(h4(s)["A20_X3_P0"]["R1_T0"]["any5_diff"], "diff"),
      (0.600, 0.224, 1.033)),
    # the chain's own stages (S lines; their reads decide nothing new)
    L("S1", "S", "stage", "R2+R1", "pre-read, whole era, C1 (tl, his exit with the staller cut)", lambda s: p5row(s, "era", "C1"), ("CAN'T TELL", 180, 0.277, -0.24, 0.99)),
    L("S2", "S", "stage", "R1", "pre-read, whole era, C0 baseline", lambda s: p5row(s, "era", "C0"), (0.024, -0.12, 0.17)),
    L("S3", "S", "stage", "R2", "pre-read, whole era, C4", lambda s: p5row(s, "era", "C4")["word"], "FAIL"),
    L("S4", "S", "stage", "R2", "pre-read, 2020-21 alone, C1", lambda s: p5row(s, "2020-21", "C1")["word"], "CAN'T TELL"),
    L("S5", "S", "stage", "R2", "hourly-close read, pre, C1 verdict | paired entry verdict",
      lambda s: f"{s.json('h60_verdict_pre.json')['windows']['pre']['c1_verdict']} | {s.json('h60_verdict_pre.json')['windows']['pre']['pair_verdict_c1']}",
      "CAN'T TELL | can't tell"),
    L("S6", "S", "stage", "R2+R1", "exit read, pre, C1: whole-trade breakeven minus pp",
      lambda s: {**interval(s.json("exitpb_verdict_pre.json")["delta_c1"], "mean"), "word": s.json("exitpb_verdict_pre.json")["delta_c1"]["verdict"]},
      ("loss", -0.1221, -0.19, -0.05)),
    L("S7", "S", "stage", "R2", "exit read, pre, C0: the same delta", lambda s: s.json("exitpb_verdict_pre.json")["delta_c0"]["verdict"], "can't tell"),
]
# §7's sources table, per line: (logical source(s), the key read) - printed under every line (§3 row 7: "... and the source it read")
SRC_OF = {
    "1.1": (("read1_03_report.md",), "§A, the 2017-21 row: fill distance below the base high, median"),
    "1.2": (("read1_03_report.md",), "§A, the 2017-21 row: fill already at/above the base high (count) / n"),
    "1.3": (("read1_03_numbers.json",), 'A_sc_2017-21: by60 / n'), "1.4": (("read1_03_numbers.json",), "A_sc_2017-21: by0, by5, by20, never"),
    "1.5": (("read1_03_numbers.json",), "A_big_2017-21_5: before / n"),
    "1.6": (("read1_03_numbers.json",), f"{R1KEY} / {Q}share >= 5 ADR within 60: d, lo, hi, n"),
    "1.7": (("read1_03_numbers.json",), f"{R1KEY} / {Q}mean close return +60 (ADR)"),
    "1.8": (("read1_03_numbers.json",), f"{R2KEY} / {Q}share >= 5 ADR within 60"),
    "2.0": (("read2_03_numbers.json",), "2017-21/x200/composition: n"), "2.1": (("read2_03_numbers.json",), "2017-21/x200/funnel: " + FUNNEL["covered"]),
    "2.2": (("read2_03_numbers.json",), "2017-21/x200/funnel: " + FUNNEL["watched"]), "2.3": (("read2_03_numbers.json",), "2017-21/x200/funnel: " + FUNNEL["triggered"]),
    "2.4": (("read2_03_numbers.json",), "2017-21/x200/funnel: " + FUNNEL["still"]), "2.5": (("read2_03_numbers.json",), "2017-21/x200/funnel: " + FUNNEL["kept"]),
    "3.1": (("read3_03_headline.json",), '2017-21 / win_S2_T2: still_in_s50, n; R4 over every win_* cell'),
    "3.2": (("read3_03_headline.json",), "2017-21 / win_S2_T2: kept_half"), "3.2b": (("read3_03_headline.json",), "2017-21 / win_S2_T2: kept_quarter"),
    "3.2c": (("read3_03_headline.json",), "2017-21 / win_S2_T2: retries_mean"),
    "3.3": (("read3_03_headline.json",), "2017-21 / all_S2_T0: diff_r_per_base"), "3.4": (("read3_03_headline.json",), "2017-21 / all_S2_T0: diff_any5"),
    "3.5": (("read3_03_headline.json",), "2017-21 / all_S2_T2: diff_r_per_base"), "3.6": (("read3_03_headline.json",), "2017-21 / all_S2_T2: diff_any5"),
    "3.7": (("read3_03_headline.json",), "2017-21 / all_S2_T0: race5_hit - ctl_race5_hit"),
    "4.0": (("read3_03_headline.json", "read4_03_headline.json"), "A20_X1_P1 win_T2 vs win_S2_T2; A20_X1_P1 R1_T0 vs all_S2_T0"),
    "4.1": (("read4_03_headline.json",), "2017-21 / <cell> / win_T2: still_in_s50 over all 16 cells"),
    "4.2": (("read4_03_headline.json",), "2017-21 / A20_X3_P0 / win_T2: kept_half"), "4.2b": (("read4_03_headline.json",), "2017-21 / A20_X1_P1 / win_T2: kept_half"),
    "4.2c": (("read4_03_headline.json",), "2017-21 / A20_X3_P0 and A20_X1_P1 / win_T2: kept_half"),
    "4.3": (("read4_03_headline.json",), "2017-21 / A20_X3_P0 / win_T2: kept_share_q[1]"), "4.3b": (("read4_03_headline.json",), "2017-21 / A20_X1_P1 / win_T2: kept_share_q[1]"),
    "4.3c": (("read4_03_headline.json",), "2017-21 / A20_X3_P0 / win_T2: held_chain_q[1]"), "4.3d": (("read4_03_headline.json",), "2017-21 / A20_X1_P1 / win_T2: held_chain_q[1]"),
    "4.4": (("read4_03_headline.json",), "2017-21 / A20_X1_P1 / R1_T0: diff"), "4.4b": (("read4_03_headline.json",), "2017-21 / A20_X3_P0 / R1_T0: diff"),
    "4.5": (("read4_03_headline.json",), "2017-21 / A20_X1_P1 / R1_T0: any5_diff"), "4.5b": (("read4_03_headline.json",), "2017-21 / A20_X3_P0 / R1_T0: any5_diff"),
    "S1": (("p5_report_pre.tsv",), "key spec, K tl, arm c3_p33_t20_cut3, slice all, window era, cell C1: n, mean_r, ci_lo, ci_hi, verdict"),
    "S2": (("p5_report_pre.tsv",), "the same, cell C0"), "S3": (("p5_report_pre.tsv",), "the same, cell C4"),
    "S4": (("p5_report_pre.tsv",), "the same, window 2020-21, cell C1"),
    "S5": (("h60_verdict_pre.json",), 'windows / pre: c1_verdict, pair_verdict_c1'),
    "S6": (("exitpb_verdict_pre.json",), "delta_c1: verdict, n, mean, lo, hi"), "S7": (("exitpb_verdict_pre.json",), "delta_c0: verdict"),
}
READ_NAMES = {1: "Read 1 - was our trigger early, and does a real breakout follow through?", 2: "Read 2 - of the big winners, how many did we catch?",
              3: "Read 3 - entry at the breakout close x four stops x up to two retries", 4: "Read 4 - the trail exit, sixteen ways"}


# ═══ the rules ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
def r1_class(v: dict) -> str:
    return "ABOVE" if v["lo"] > 0 else ("BELOW" if v["hi"] < 0 else "SPANS")


R3D_TOL = 2.0                                            # 3.7: "R3 on the difference (±2)"


def r3_tol(old_share_pts: float) -> float:
    return max(2.0, min(5.0, old_share_pts / 2.0))


def share(v: dict) -> float:
    return 100.0 * v["k"] / v["n"] if v["n"] else float("nan")


def _finite(*xs) -> bool:
    try:
        return all(math.isfinite(float(x)) for x in xs)
    except (TypeError, ValueError):
        return False


def not_finite(rule: str, old, new) -> "str | None":
    """Why the line cannot be compared (a value that is not finite, a share of 0 rows, a missing verdict word), else None."""
    def iv(v):
        return (v["d"], v["lo"], v["hi"])
    try:
        if rule in ("R1", "R2+R1"):
            ok = _finite(*iv(old), *iv(new))
        elif rule in ("R3", "R4+R3"):
            ok = _finite(old["k"], old["n"], new["k"], new["n"]) and float(old["n"]) > 0 and float(new["n"]) > 0
            if rule == "R4+R3":
                ok = ok and bool(new["shares"]) and _finite(*new["shares"].values())
        elif rule == "R3d":
            ok = _finite(old["e"], old["c"], new["e"], new["c"])
        elif rule in ("R5", "SIGN"):
            ok = _finite(old, new)
        else:
            ok = True
        if rule in ("R2", "R2+R1"):
            wo, wn = (old, new) if rule == "R2" else (old["word"], new["word"])
            ok = ok and isinstance(wo, str) and isinstance(wn, str) and bool(wo) and bool(wn) and wn not in ("nan", "None")
    except (KeyError, TypeError, ValueError) as exc:
        return f"not comparable ({exc!r})"
    if ok:
        return None
    try:
        shown = f"old {fmt(old)} | new {fmt(new)}"
    except Exception:                                  # noqa: BLE001 - the reason is printed, never raised
        shown = f"old {old!r} | new {new!r}"
    return f"a value is not finite (or a share of 0 rows / no verdict word): {shown}"


def apply(rule: str, old, new) -> tuple:
    """(verdict, note): verdict in holds / moved / changes / reported / passes / FAILS / NOT COMPARED (a non-finite value: never a holds)."""
    why = not_finite(rule, old, new) if rule not in ("R6", "CHECK") else None
    if why:
        return NC, why
    if rule == "R1":
        a, b = r1_class(old), r1_class(new)
        if a != b:
            return "changes", f"class {a} -> {b}"
        moved = not (old["lo"] <= new["d"] <= old["hi"])
        return ("moved" if moved else "holds"), f"class {a} -> {b}" + (" (the new point is outside the old interval)" if moved else "")
    if rule == "R2":
        return ("holds" if old == new else "changes"), f"{old!r} -> {new!r}"
    if rule == "R3":
        o, n = share(old), share(new)
        tol = r3_tol(o)
        return ("holds" if abs(n - o) <= tol + 1e-12 else "changes"), f"{o:.2f}% -> {n:.2f}% (|diff| {abs(n - o):.2f} vs tolerance +-{tol:.2f} points)"
    if rule == "R3d":
        o, n = 100 * (old["e"] - old["c"]), 100 * (new["e"] - new["c"])
        return ("holds" if abs(n - o) <= R3D_TOL + 1e-12 else "changes"), f"difference {o:+.2f} -> {n:+.2f} points (tolerance +-{R3D_TOL:.2f})"
    if rule == "R4+R3":
        v3, note3 = apply("R3", old, new)
        nb = new["best"]
        if nb == new["named"]:
            v4, note4 = "holds", f"best cell {new['named']} is still the best"
        else:
            gap = 100 * (new["shares"][nb] - new["shares"][new["named"]])
            v4, note4 = ("holds", f"a TIE: {nb} leads {new['named']} by {gap:.2f} points (<= 2)") if gap <= 2.0 + 1e-12 else ("changes", f"best cell now {nb} (+{gap:.2f} points over {new['named']})")
        return ("holds" if v3 == "holds" and v4 == "holds" else "changes"), f"{note4}; {note3}"
    if rule == "R5":
        o, n = float(old), float(new)
        if (o > 0) != (n > 0) or o == 0:
            return "changes", f"{o:+.4g} -> {n:+.4g} (the direction flips)"
        return ("holds" if abs(n - o) <= 0.25 * abs(o) + 1e-12 else "moved"), f"{o:+.4g} -> {n:+.4g} ({100 * (n - o) / abs(o):+.1f}%; band +-25%)"
    if rule == "R6":
        o, n = (old if isinstance(old, tuple) else (old,)), (new if isinstance(new, tuple) else (new,))
        return "reported", " / ".join(f"{a} -> {b} (x{(b / a) if a else float('nan'):.3f})" for a, b in zip(o, n))
    if rule == "R2+R1":
        w = apply("R2", old["word"], new["word"])
        i = apply("R1", old, new)
        return ("changes" if "changes" in (w[0], i[0]) else ("moved" if i[0] == "moved" else "holds")), f"{w[1]}; {i[1]}; n {old['n']} -> {new['n']}"
    if rule == "SIGN":
        return ("holds" if (old > 0) == (new > 0) else "changes"), f"{old:+} -> {new:+}"
    raise ValueError(rule)


EXPECT = {"episodes": V2_EPISODES_N}


# ═══ F10: the lines, roles and rules are §7's - parsed from the doc above the freeze marker, never trusted as typed ══════════════════════
S7_EXPAND = {"3.2": ("3.2", "3.2b", "3.2c"), "4.2": ("4.2", "4.2b", "4.2c"), "4.3": ("4.3", "4.3b", "4.3c", "4.3d"), "4.4": ("4.4", "4.4b"),
             "4.5": ("4.5", "4.5b")}
S7_RULES = {"R1": ("R1",), "R2": ("R2",), "R3": ("R3",), "R5": ("R5",), "R6": ("R6",), "R2 + R1": ("R2+R1",), "R4 + R3": ("R4+R3",),
            "R3 / R3 / R6": ("R3", "R3", "R6"), "R3 on the difference": ("R3d",), "R3 each + the sign of the gap": ("R3", "R3", "SIGN"),
            "must pass": ("CHECK",), "R6 + the relaunch must reproduce 1,181 and the 10-23 v2 tables by decompressed bytes": ("CHECK",)}


def _norm_rule(cell: str) -> tuple:
    """(the rule text with every '(±...)' removed, the stated tolerances in order)."""
    tols = [float(x) for grp in re.findall(r"\(([^)]*±[^)]*)\)", cell) for x in re.findall(r"±\s*([\d.]+)", grp)]
    return re.sub(r"\s+", " ", re.sub(r"\s*\([^)]*±[^)]*\)", "", cell)).strip(), tols


def section7(text: str) -> dict:
    """{line id: (role, rule)} from the doc's §7 tables above the freeze marker (the per-read tables: line | number | old | rule | role; the
    stage table: line | number | old | rule, role `stage`), each doc line expanded by S7_EXPAND, and the stated R3 tolerances {id: ±}."""
    body = text.split("<!-- FREEZE -->", 1)[0]
    m = re.search(r"(?ms)^## 7\. .*?(?=^## 8\. )", body)
    if not m:
        raise ValueError("the doc has no §7 (## 7. ... ## 8.) above the freeze marker")
    sec = m.group(0).split("**Sources —", 1)
    if len(sec) != 2:
        raise ValueError("§7 has no '**Sources —' paragraph after its rule tables")
    lines, tols = {}, {}
    for ln in sec[0].splitlines():
        if not ln.startswith("|"):
            continue
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if not re.fullmatch(r"\d\.\d|S\d", c[0]):
            continue
        if len(c) == 5:
            rule_cell, role = c[3], c[4].split()[0].strip("(\"").lower()
        elif len(c) == 4 and c[0].startswith("S"):
            rule_cell, role = c[3], "stage"
        else:
            raise ValueError(f"§7 row {c[0]}: {len(c)} columns")
        text_, stated = _norm_rule(rule_cell)
        if text_ not in S7_RULES:
            raise ValueError(f"§7 row {c[0]}: rule {rule_cell!r} ({text_!r}) is not one this script knows")
        ids = S7_EXPAND.get(c[0], (c[0],))
        rules = S7_RULES[text_]
        if len(rules) == 1:
            rules = rules * len(ids)
        if len(rules) != len(ids):
            raise ValueError(f"§7 row {c[0]}: {len(rules)} rules for {len(ids)} lines {ids}")
        for k, (lid, rl) in enumerate(zip(ids, rules)):
            if lid in lines:
                raise ValueError(f"§7: line {lid} twice")
            lines[lid] = (role, rl)
        r3 = [lid for lid, rl in zip(ids, rules) if rl in ("R3", "R4+R3", "R3d")]
        if stated and len(stated) == len(r3):
            tols.update(zip(r3, stated))
        elif stated:
            raise ValueError(f"§7 row {c[0]}: {len(stated)} stated tolerance(s) for {len(r3)} R3 line(s)")
    return {"lines": lines, "tols": tols}


def section7_problems(text: str) -> list:
    """[] when LINES carries exactly §7's lines with §7's roles and rules (and every stated R3 tolerance is the rule's own), else what differs."""
    try:
        s7 = section7(text)
    except ValueError as exc:
        return [str(exc)]
    have = {ln["id"]: (ln["role"], ln["rule"]) for ln in LINES}
    out = [f"line {k}: §7 says {s7['lines'].get(k)}, the script has {have.get(k)}" for k in sorted(set(have) | set(s7["lines"]))
           if have.get(k) != s7["lines"].get(k)]
    by_id = {ln["id"]: ln for ln in LINES}
    for lid, tol in s7["tols"].items():
        q = by_id[lid]["doc_old"]
        got = R3D_TOL if by_id[lid]["rule"] == "R3d" else r3_tol(100.0 * q[0] / q[1])
        if abs(got - tol) > 0.051:
            out.append(f"line {lid}: §7 states ±{tol}, the rule gives ±{got:.2f} on the old share")
    m = re.search(r"must reproduce ([\d,]+)", text.split("<!-- FREEZE -->", 1)[0])
    if not m or int(m.group(1).replace(",", "")) != V2_EPISODES_N:
        out.append(f"line 2.0: §7's episode target {m.group(1) if m else None} is not V2_EPISODES_N {V2_EPISODES_N}")
    return out


def check_line(line: dict, new) -> tuple:
    if line["id"] == "2.0":
        n = EXPECT["episodes"]
        try:
            ok = _finite(new) and float(new) == int(new) and int(new) == n
        except (TypeError, ValueError, OverflowError):
            ok = False
        return ("passes" if ok else "FAILS"), f"big winners {new} (must be {n:,}" + (", the 10-23 v2 table)" if n == V2_EPISODES_N else ")")
    return ("passes" if not new else "FAILS"), ("every value equal to 1e-9" if not new else f"{len(new)} value(s) differ: " + "; ".join(new[:5]))


def fmt(v) -> str:
    if isinstance(v, list):
        return "every value equal" if not v else f"{len(v)} value(s) differ"
    if isinstance(v, dict):
        if "d" in v and "lo" in v:
            return f"{v['d']:+.4f} ({v['lo']:+.4f} .. {v['hi']:+.4f}) {r1_class(v)}" + (f", n {v['n']:,}" if v.get("n") else "") + (f", {v['word']}" if "word" in v else "")
        if "best" in v:
            return f"{v['named']} {v['k']} of {v['n']} = {share(v):.1f}%; best {v['best']} {100 * v['shares'][v['best']]:.1f}%"
        if "k" in v:
            return f"{v['k']:,} of {v['n']:,} = {share(v):.2f}%"
        if "e" in v:
            return f"{100 * v['e']:.2f}% vs {100 * v['c']:.2f}% (difference {100 * (v['e'] - v['c']):+.2f} points)"
        return json.dumps(v)
    if isinstance(v, float):
        return f"{v:+.4g}"
    return str(v)


def doc_old_problem(line: dict, old) -> "str | None":
    """The old value read from the source against the value §7 quotes (rounded as quoted) - a source check, not a rule."""
    q = line["doc_old"]
    if q is None or line["rule"] == "CHECK" and line["id"] == "4.0":
        return None
    try:
        if line["rule"] in ("R3",) or (line["rule"] == "R4+R3"):
            ok = (old["k"], old["n"]) == tuple(q)
        elif line["rule"] == "R1":
            ok = all(abs(a - b) <= 0.6 * 10 ** -(len(str(b).split(".")[-1])) + 1e-12 for a, b in zip((old["d"], old["lo"], old["hi"]), q))
        elif line["rule"] == "R2+R1":
            ok = old["word"] == q[0] and (len(q) < 5 or old["n"] == q[1])
        elif line["rule"] == "R3d":
            ok = abs(old["e"] - q[0]) < 6e-5 and abs(old["c"] - q[1]) < 6e-5
        elif line["rule"] == "R5":
            ok = abs(float(old) - q) <= 0.006
        elif line["rule"] == "R6":
            o = old if isinstance(old, tuple) else (old,)
            ok = all(abs(float(a) - float(b)) <= (0.0006 if isinstance(b, float) else 0) for a, b in zip(o, q))
        elif line["rule"] in ("CHECK", "SIGN"):
            ok = old == q
        else:
            ok = old == q
    except Exception as exc:                           # noqa: BLE001 - a source check reports, never raises
        return f"source check could not run: {exc!r}"
    return None if ok else f"SOURCE CHECK: the old value read ({fmt(old)}) is not §7's quoted {q} - the source or the key is wrong"


def restored_text(line: dict, new: Src, rest: frozenset) -> str:
    fn = line.get("restored")
    if fn is None:
        return ""
    try:
        (all_v, all_n), (r_v, r_n) = fn(new, rest)
    except Exception as exc:                           # noqa: BLE001
        return f"restored-only: not computed ({exc!r})"
    want = line["reproduce"](new)
    want_v = want[0] if isinstance(want, tuple) else want
    tol = 0.0051 if line.get("fmt") == "r2" else (0 if isinstance(want_v, int) else 1e-6 * max(1.0, abs(float(want_v))))   # float32 tables: 1e-6 relative
    ok = (abs(float(all_v) - float(want_v)) <= tol) and (not isinstance(want, tuple) or all_n == want[1])
    if not ok:
        return f"restored-only: withheld - the method gives {all_v} on all rows, not the read's {want} (does not reproduce)"
    if r_n == 0:
        return "restored-only: none (no restored row)"
    side = " (entry side; the control is not re-matched)" if line.get("entry_side") else ""
    if isinstance(r_v, int) and line["rule"] in ("R3", "R4+R3"):
        frac = r_n / all_n
        tol = r3_tol(100.0 * all_v / all_n) if all_n else float("nan")
        return (f"restored-only: {r_v:,} of {r_n:,} = {100 * r_v / r_n:.2f}% vs all {100 * all_v / all_n:.2f}%; restored fraction {100 * frac:.1f}% -> the band "
                f"(+-{tol:.2f} points) detects a restored-minus-survivor gap of about {tol / frac:.0f} points or more")
    if line["rule"] == "SIGN":
        return f"restored-only: gap {r_v:+d} doublers on {r_n:,} restored doublers vs {all_v:+d} on all {all_n:,}; restored fraction {100 * r_n / all_n:.1f}%"
    return f"restored-only: {r_v:+.4f} on {r_n:,} rows vs all {all_v:+.4f} on {all_n:,}{side}; restored fraction {100 * r_n / all_n:.1f}%"


def restored_symbols(new_guard=V2_DATA / "symbol_guard.tsv", old_guard=OLD_DATA / "symbol_guard.tsv") -> frozenset:
    def syms(p):
        with open(p, newline="") as fh:
            return {r["symbol"] for r in csv.DictReader(fh, delimiter="\t")}
    return frozenset(syms(new_guard) - syms(old_guard))


def compare(old: Src, new: Src, rest: frozenset) -> tuple:
    missing = [ln["id"] for ln in LINES if ln["id"] not in SRC_OF]
    if missing:
        raise ValueError(f"lines without a §7 source: {missing}")
    rows, out = [], []
    for line in LINES:
        o = line["get"](old)
        n = line["get"](new)
        if line["rule"] == "CHECK":
            v, note = check_line(line, n)
        else:
            v, note = apply(line["rule"], o, n)
        rows.append({**{k: line[k] for k in ("id", "read", "role", "rule", "what")}, "old": o, "new": n, "verdict": v, "note": note,
                     "source_check": doc_old_problem(line, o), "restored": restored_text(line, new, rest) if line["role"] == "deciding" else "",
                     "src_old": None, "src_new": None})
    concl = {}
    for rd in (1, 2, 3, 4):
        rr_ = [r for r in rows if r["read"] == rd]
        failed = [r["id"] for r in rr_ if r["role"] == "check" and r["verdict"] != "passes"]
        if failed:
            concl[rd] = ("NOT COMPARED", f"check {', '.join(failed)} failed - the failure is the result")
            continue
        nc = [r["id"] for r in rr_ if r["role"] == "deciding" and r["verdict"] == NC]
        if nc:
            concl[rd] = (NC, f"deciding line(s) {', '.join(nc)} carry a value that is not finite - not compared, never a holds")
            continue
        ch = [r["id"] for r in rr_ if r["role"] == "deciding" and r["verdict"] == "changes"]
        mv = [r["id"] for r in rr_ if r["role"] == "deciding" and r["verdict"] == "moved"]
        concl[rd] = ("changes", f"lines that changed: {', '.join(ch)}") if ch else ("holds", ("moved (named, counts as holds): " + ", ".join(mv)) if mv else "every deciding line holds")
    return rows, concl


def render(rows, concl, old: Src, new: Src, shas: "dict | None" = None) -> str:
    out = [f"#705 v2 COMPARISON (§7 rules, mechanical) - old: {'flat ' + str(old.flat) if old.flat else 'the published sources'}; new: "
           f"{'flat ' + str(new.flat) if new.flat else 'the chain outputs (rerun_v2_1025 / v2_1025 / cb702_pre_v2/out)'}"]
    for rd in (1, 2, 3, 4, "S"):
        out.append("")
        out.append(READ_NAMES.get(rd, "The chain's own stages (decide nothing new)") + (f" -> CONCLUSION {concl[rd][0].upper()}: {concl[rd][1]}" if rd in concl else ""))
        for r in [x for x in rows if x["read"] == rd]:
            out.append(f"  {r['id']:<5} [{r['role']}, {r['rule']}] {r['what']}")
            out.append(f"        old {fmt(r['old'])}  |  new {fmt(r['new'])}  ->  {r['verdict'].upper()}: {r['note']}")
            names, key = SRC_OF[r["id"]]
            out.append("        source: " + "; ".join(f"old {old.path(n)} | new {new.path(n)}" for n in names) + f" [{key}]")
            if r["restored"]:
                out.append(f"        {r['restored']}")
            if r["source_check"]:
                out.append(f"        {r['source_check']}")
    out.append("")
    out.append("SOURCES: " + "; ".join(f"{k}: old {old.path(k)} | new {new.path(k)}" for k in LOGICAL if not k.endswith(".tsv.gz")))
    out.append("TABLES (restored-only values, new side): " + "; ".join(str(new.path(k)) for k in TABLES))
    if shas:
        out.append("SOURCE SHA256 (every file this run read, as read):")
        out += [f"  {h}  {pth}" for pth, h in shas.items()]
    return "\n".join(out)


def _shas(old: Src, new: Src) -> dict:
    out = {}
    for side, src in (("old", old), ("new", new)):
        for k in LOGICAL:
            if side == "old" and k in TABLES:
                continue                                   # never read (the restored-only values are new-side only)
            pth = src.path(k)
            out[f"{side} {pth}"] = v2c.sha256_file(pth) if Path(pth).is_file() else "MISSING"
    return out


def _refuse(lines) -> int:
    for ln in lines:
        print(f"REFUSED: {ln}", file=sys.stderr)
    return 2


def _reserve(path: Path) -> None:
    """Create `<record>.partial` ("x": never over an existing one) BEFORE the comparison is computed, so a crash mid-way leaves it behind and the
    once-only check refuses a second run (the scaffold's protocol)."""
    with open(str(path) + ".partial", "x", encoding="utf-8"):
        pass


def _write_once(path: Path, text: str) -> None:
    part = Path(str(path) + ".partial")
    if not part.is_file():
        raise RuntimeError(f"{part} was not reserved - the record is written only through its reserved .partial")
    part.write_text(text, encoding="utf-8")
    os.replace(part, path)


def real_run_checks(say=print) -> list:
    """The real run's refusals, cheapest first; the full freeze re-check (a subprocess) runs only once every in-process check passes."""
    if OUT.exists() or Path(str(OUT) + ".partial").exists():
        return [f"{OUT} (or its .partial) exists - stage 7 runs ONCE (the operator inspects; nothing is rewritten)"]
    pr = logical_problems()
    if pr:
        return pr
    doc_text = DOC.read_text(encoding="utf-8") if DOC.is_file() else ""
    pr = section7_problems(doc_text) if doc_text else [f"registration doc missing: {DOC}"]
    if pr:
        return ["the §7 tables are not this script's lines / roles / rules: " + p for p in pr]
    pr = v2c.footer_pin_problems(DOC, [(OLD_PINS[k], LOGICAL[k][0]) for k in OLD_PINS] + list(CODE_PINS.items()))
    if pr:
        return ["an old source or this script is not its §8 footer pin: " + p for p in pr]
    pr = v2c.freeze_recheck(V2_DATA, say=say)
    if pr:
        return pr
    pr = v2c.manifest_problems(V2_DATA / "out" / v2c.MANIFEST_NAME, [(v2c.chain_label(n), n) for _o, n in LOGICAL.values()])
    if pr:
        return ["a new source is not the file the chain wrote (manifest): " + p for p in pr]
    return []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--proofs", action="store_true", help="the B7 proofs only: enables the five options below; never writes v2_compare.txt")
    ap.add_argument("--old-flat")
    ap.add_argument("--new-flat")
    ap.add_argument("--out")
    ap.add_argument("--expect-episodes", type=int, help="the proofs only: check 2.0's target (old vs old = 994)")
    ap.add_argument("--guards", nargs=2, metavar=("NEW", "OLD"), help="the proofs only: the two symbol guards the restored set is taken from")
    a = ap.parse_args(argv)
    given = [o for o in PROOF_OPTS if getattr(a, o) is not None]
    if not a.proofs and given:
        return _refuse([f"--{', --'.join(o.replace('_', '-') for o in given)}: the proofs' options only (with --proofs); the real run takes none"])
    if a.proofs:
        if not a.out or Path(a.out).resolve() in (OUT.resolve(), Path(str(OUT) + ".partial").resolve()):
            return _refuse([f"--proofs needs --out FILE, and never {OUT} (the real run's record)"])
        if not a.new_flat:
            return _refuse(["--proofs needs --new-flat DIR"])
        out_path = Path(a.out)
        EXPECT["episodes"] = a.expect_episodes if a.expect_episodes is not None else V2_EPISODES_N
        print(f"PROOFS MODE: flat sources, --out {out_path}; the freeze / pin / manifest checks are skipped (flat copies are not chain outputs)")
    else:
        out_path = OUT
        EXPECT["episodes"] = V2_EPISODES_N
        pr = real_run_checks()
        if pr:
            return _refuse(pr)
    old, new = Src("old", Path(a.old_flat) if a.old_flat else None), Src("new", Path(a.new_flat) if a.new_flat else None)
    missing = [f"{side}: {s.path(k)}" for side, s in (("old", old), ("new", new)) for k in LOGICAL if not k.endswith(".tsv.gz") and not s.path(k).is_file()]
    if missing:
        return _refuse(["a §7 source is missing:"] + missing)
    if not a.proofs:
        _reserve(out_path)                                     # from here on the run is spent: a crash leaves the .partial (once-only)
    shas = _shas(old, new)
    rows, concl = compare(old, new, restored_symbols(*a.guards) if a.guards else restored_symbols())
    bad = [f"{r['id']}: {r['source_check']}" for r in rows if r["source_check"]]
    if bad:
        text = "\n".join(["#705 v2 COMPARISON REFUSED - a source check failed (an old value read is not the value §7 quotes): the source or the key is "
                          "wrong, so NO verdict is issued; the failure is the result"] + [f"  {b}" for b in bad]
                         + ["SOURCE SHA256:"] + [f"  {h}  {pth}" for pth, h in shas.items()])
        _write_once(out_path, text + "\n") if not a.proofs else out_path.write_text(text + "\n")
        print(text, file=sys.stderr)
        return 2
    text = render(rows, concl, old, new, shas)
    if a.proofs:
        out_path.write_text(text + "\n")
    else:
        _write_once(out_path, text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
