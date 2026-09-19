#!/usr/bin/env python3
"""#610 — the four-reading observer is NOT a gate: old-vs-new replay over prod's stored rows.

WHAT SHIPPED (2026-09-19). `compute_flag_metrics` now RECORDS, per candidate-day, the margin under
each depth/trend reading still on the table — `depth_on_low`, `depth_on_close`, `sma20_margin`,
`ma_stack_margin` (definitions: the CREATE TABLE comment on mi_flag_candidates, db.py). The live
admission gate is unchanged. PLAN #610's DONE-WHEN demands that a replay of 2026-08-17 → 09-17
reproduces the stage and reason of every stored row byte-identically, and its WOULD-FAIL-IF is the
acting stage/reason moving for ANY candidate-day — an observer that became a gate.

WHAT THIS PROBE MEASURES, on every (ticker, scan_date) prod actually scanned in the window:
  A. OLD function vs NEW function, same bars, each threading state from ITS OWN prior outputs
     (prod-style: yesterday's stage, the 5-day recent stages, the prior pivot) so a divergence
     would COMPOUND and show. Compared: stage, reason, score, held_from_stage. Expected: 0 diffs.
     The OLD function is the pre-change `compute_flag_metrics` source (`git show <sha>:...`)
     compiled into a copy of the CURRENT module namespace — valid only if every OTHER top-level
     definition in the file is byte-identical between the two versions, which is ASSERTED first.
  B. NEW function vs the STORED prod rows (stage + reason), two ways: (i) own-output threading,
     (ii) threading from the STORED rows (what prod itself read on the day). Mismatch families are
     classified; the expected residue is bars revised by the vendor since the scan (0 rows carry an
     `mna_filter:` rewrite in this window — checked 2026-09-19).
  C. Gate agreement on every replayed row (a `flag_low_` reject reads depth_on_low < 0.75, etc.)
     and the population of each reading. Plus MRNA's four readings on 09-16/09-17 from PROD bars.

INPUTS (pulled ONCE from prod 2026-09-19, read-only; scratchpad, ~23 MB — not for the repo):
  replay_pairs.psv  ticker|scan_date|stage|reason|pivot_high_date|pivot_high_price|runup_pct|base_age|held_from_stage
      SELECT ticker, scan_date, stage, COALESCE(reason,''), COALESCE(pivot_high_date::text,''),
             COALESCE(pivot_high_price::text,''), COALESCE(runup_pct::text,''), COALESCE(base_age::text,''),
             COALESCE(held_from_stage,'')
      FROM mi_flag_candidates WHERE scan_date BETWEEN '2026-08-03' AND '2026-09-17' ORDER BY ticker, scan_date;
      -- 18,073 rows; 08-03 → 08-16 thread state only, the DoD window is 08-17 → 09-17 (12,657 rows)
  replay_bars.psv   ticker|trade_date|open|high|low|close|volume
      WITH t AS (SELECT DISTINCT ticker FROM mi_flag_candidates WHERE scan_date BETWEEN '2026-08-03' AND '2026-09-17')
      SELECT d.ticker, d.trade_date, d.open_price, d.high_price, d.low_price, d.close, d.volume
      FROM mi_daily_closes d JOIN t USING (ticker) WHERE d.trade_date BETWEEN '2025-04-01' AND '2026-09-17'
      ORDER BY d.ticker, d.trade_date;                          -- 487,708 rows
  flag_detector_old.py   `git show <pre-change sha>:agents/market_intelligence/flag_detector.py`

History per pair = the last `fd._HISTORY_DAYS` TRADING rows ending at the scan date (row-count
slice, matching `get_recent_daily_history`). Loaders + the own-output replay are REUSED from the
2026-09-18 probe (`_610_htf_depth_sma20_replay.py`) — no second copy of the threading logic.

USAGE
  python scripts/probes/_610_four_reading_observer_replay.py --data-dir <dir> --old-file <dir>/flag_detector_old.py
Per-pair readings + every diff/mismatch land as CSVs in <dir>/out/.
"""
from __future__ import annotations

import argparse
import ast
import bisect
import csv
import importlib.util
import pathlib
import sys
import time
from collections import Counter
from datetime import date, timedelta

_HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[2]))

from agents.market_intelligence import flag_detector as fd  # noqa: E402

WINDOW_START = date(2026, 8, 17)     # the DoD window; earlier pairs thread state only
WINDOW_END = date(2026, 9, 17)
COMPARE_KEYS = ("stage", "reason", "score", "held_from_stage")
READINGS = ("depth_on_low", "depth_on_close", "sma20_margin", "ma_stack_margin")
ACTIONABLE = ("WATCH", "TIGHTENING", "COILED", "TRIGGERED")


def _sibling(name: str):
    """Import a sibling probe by file (scripts/probes is not a package)."""
    spec = importlib.util.spec_from_file_location(name, _HERE.parent / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_prev = _sibling("_610_htf_depth_sma20_replay")
load_bars, load_pairs, replay_ticker, reason_family = (
    _prev.load_bars, _prev.load_pairs, _prev.replay_ticker, _prev.reason_family,
)


# ── the OLD function, honestly ───────────────────────────────────────────────

def _top_level_segments(src: str) -> tuple[list[str], str]:
    """(source of every top-level node EXCEPT compute_flag_metrics, in order; the source of
    compute_flag_metrics itself)."""
    tree = ast.parse(src)
    others, target = [], None
    for node in tree.body:
        seg = ast.get_source_segment(src, node)
        if isinstance(node, ast.FunctionDef) and node.name == "compute_flag_metrics":
            target = seg
        else:
            others.append(seg)
    assert target is not None, "compute_flag_metrics not found at top level"
    return others, target


def build_old_function(old_path: pathlib.Path):
    old_src = old_path.read_text()
    new_src = pathlib.Path(fd.__file__).read_text()
    old_others, old_fn = _top_level_segments(old_src)
    new_others, new_fn = _top_level_segments(new_src)
    assert old_others == new_others, (
        "a top-level definition OTHER than compute_flag_metrics differs between the old and new "
        "file — the old function would run on new helpers; this probe's 0-diff claim needs a "
        "per-helper old namespace instead"
    )
    assert old_fn != new_fn, "old and new compute_flag_metrics are identical — nothing to compare"
    ns = dict(vars(fd))                                   # a COPY; the live module is untouched
    exec(compile(old_fn, str(old_path), "exec"), ns)
    fn = ns["compute_flag_metrics"]
    assert fn is not fd.compute_flag_metrics
    return fn, len(old_others)


# ── stored-row threading (what prod read on the day) ─────────────────────────

def replay_stored_threading(fn, ticker: str, tb: list[dict], plist: list[dict]) -> list[dict]:
    tdates = [r["trade_date"] for r in tb]
    out = []
    for p in plist:
        d = p["scan_date"]
        hi = bisect.bisect_right(tdates, d)
        lo = max(0, hi - fd._HISTORY_DAYS)
        rows = tb[lo:hi]
        if not rows or len(rows) < 60:
            continue
        cutoff = d - timedelta(days=5)
        window = [q for q in plist if cutoff <= q["scan_date"] < d]
        ppiv = next(((q["pivot_high_date"], q["pivot_high_price"])
                     for q in reversed(window) if q["pivot_high_date"] is not None), None)
        m = fn(rows, ticker=ticker,
               yesterday_stage=window[-1]["stage"] if window else None,
               recent_stages=[q["stage"] for q in window],
               prior_pivot_date=ppiv[0] if ppiv else None,
               prior_pivot_high=ppiv[1] if ppiv else None)
        m["scan_date"] = d
        out.append(m)
    return out


def _in_window(d: date) -> bool:
    return WINDOW_START <= d <= WINDOW_END


def _fmt(v):
    return "" if v is None else f"{v:.6f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--old-file", required=True, help="pre-change flag_detector.py (git show <sha>:path)")
    args = ap.parse_args()
    data = pathlib.Path(args.data_dir)
    out_dir = data / "out"
    out_dir.mkdir(exist_ok=True)
    t0 = time.time()

    old_fn, n_helpers = build_old_function(pathlib.Path(args.old_file))
    new_fn = fd.compute_flag_metrics
    print(f"old function built: {n_helpers} other top-level definitions byte-identical old↔new; "
          f"compute_flag_metrics source differs (expected)")

    bars = load_bars(data / "replay_bars.psv")
    pairs = load_pairs(data / "replay_pairs.psv")
    n_pairs_all = sum(len(v) for v in pairs.values())
    n_window = sum(1 for v in pairs.values() for p in v if _in_window(p["scan_date"]))
    print(f"loaded {n_pairs_all} stored pairs / {len(pairs)} tickers; DoD window {WINDOW_START} → {WINDOW_END}: "
          f"{n_window} pairs; bars for {len(bars)} tickers")

    # ── A. old vs new, own-output threading each ─────────────────────────
    diffs, compared, skipped_no_bars = [], 0, 0
    new_rows: dict[tuple[str, date], dict] = {}
    for ticker, plist in pairs.items():
        tb = bars.get(ticker)
        if not tb:
            skipped_no_bars += sum(1 for p in plist if _in_window(p["scan_date"]))
            continue
        scan_dates = [p["scan_date"] for p in plist]
        o_out, _, _ = replay_ticker(old_fn, ticker, tb, scan_dates)
        n_out, _, _ = replay_ticker(new_fn, ticker, tb, scan_dates)
        assert len(o_out) == len(n_out)
        for o, n in zip(o_out, n_out):
            assert o["scan_date"] == n["scan_date"]
            if not _in_window(n["scan_date"]):
                continue
            compared += 1
            new_rows[(ticker, n["scan_date"])] = n
            if any(o[k] != n[k] for k in COMPARE_KEYS):
                diffs.append((ticker, n["scan_date"], {k: (o[k], n[k]) for k in COMPARE_KEYS if o[k] != n[k]}))
    with (out_dir / "old_vs_new_diffs.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "scan_date", "diff"])
        for t, d, dd in diffs:
            w.writerow([t, d, dd])
    print(f"\nA. OLD vs NEW (own-output threading, {compared} candidate-days compared, "
          f"{skipped_no_bars} skipped for missing bars): {len(diffs)} diffs on {COMPARE_KEYS}")
    for t, d, dd in diffs[:20]:
        print(f"   {t} {d} {dd}")

    # ── C. population + gate agreement on the NEW rows ───────────────────
    pop = Counter()
    disagree = []
    fam_seen = Counter()
    with (out_dir / "observer_readings_new.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "scan_date", "stage", "reason", *READINGS])
        for (t, d), m in sorted(new_rows.items()):
            w.writerow([t, d, m["stage"], m["reason"] or "", *[_fmt(m[k]) for k in READINGS]])
            for k in READINGS:
                if m[k] is not None:
                    pop[k] += 1
            reason = m["reason"] or ""
            if reason.startswith("flag_low_"):
                fam_seen["flag_low"] += 1
                if not (m["depth_on_low"] is not None and m["depth_on_low"] < fd._FLAG_DEPTH_MIN):
                    disagree.append((t, d, "flag_low", m["depth_on_low"]))
            if "_below_sma20_" in reason:
                fam_seen["sma20"] += 1
                if not (m["sma20_margin"] is not None and m["sma20_margin"] < 0):
                    disagree.append((t, d, "sma20", m["sma20_margin"]))
            if reason.startswith("ma_stack_not_stage2"):
                fam_seen["ma_stack"] += 1
                if not (m["ma_stack_margin"] is not None and m["ma_stack_margin"] < 0):
                    disagree.append((t, d, "ma_stack", m["ma_stack_margin"]))
            if m["stage"] in ACTIONABLE:
                fam_seen["actionable"] += 1
                ok = (m["depth_on_low"] is not None and m["depth_on_low"] >= fd._FLAG_DEPTH_MIN - 1e-12
                      and m["sma20_margin"] is not None and m["sma20_margin"] >= 0
                      and (m["ma_stack_margin"] is None or m["ma_stack_margin"] >= 0))
                if not ok:
                    disagree.append((t, d, "actionable", {k: m[k] for k in READINGS}))
    print(f"\nC. readings populated on the {len(new_rows)} NEW rows: "
          + ", ".join(f"{k} {pop[k]}" for k in READINGS))
    print(f"   gate agreement — families seen {dict(fam_seen)}; disagreements: {len(disagree)}")
    for row in disagree[:20]:
        print("   ", row)

    # ── B. new vs STORED ─────────────────────────────────────────────────
    def compare_to_stored(rows_by_key: dict[tuple[str, date], dict], label: str):
        match = mism = 0
        fams = Counter()
        detail = []
        for ticker, plist in pairs.items():
            for p in plist:
                if not _in_window(p["scan_date"]):
                    continue
                m = rows_by_key.get((ticker, p["scan_date"]))
                if m is None:
                    continue
                if m["stage"] == p["stage"] and (m["reason"] or "") == (p["reason"] or ""):
                    match += 1
                else:
                    mism += 1
                    fams[(p["stage"], reason_family(p["reason"]), m["stage"], reason_family(m["reason"]))] += 1
                    detail.append((ticker, p["scan_date"], p["stage"], p["reason"], m["stage"], m["reason"]))
        total = match + mism
        print(f"\nB({label}). NEW vs STORED on stage+reason: {match}/{total} = {match / total:.2%} identical; "
              f"{mism} mismatches")
        for fam, n in fams.most_common(12):
            print(f"   {n:5d}  stored {fam[0]}/{fam[1]:<18} → replay {fam[2]}/{fam[3]}")
        with (out_dir / f"new_vs_stored_{label}.csv").open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["ticker", "scan_date", "stored_stage", "stored_reason", "replay_stage", "replay_reason"])
            w.writerows(detail)
        return match, mism

    compare_to_stored(new_rows, "own_threading")
    stored_rows: dict[tuple[str, date], dict] = {}
    for ticker, plist in pairs.items():
        tb = bars.get(ticker)
        if not tb:
            continue
        for m in replay_stored_threading(new_fn, ticker, tb, plist):
            if _in_window(m["scan_date"]):
                stored_rows[(ticker, m["scan_date"])] = m
    compare_to_stored(stored_rows, "stored_threading")

    # ── MRNA from PROD bars — the four hand-measured values ──────────────
    print("\nMRNA from prod bars (PLAN #610 EXPECT: 72.8% / 75.5% / 0.03% on 09-16 / 0.24% on 09-17; margins SIGNED):")
    for d in (date(2026, 9, 16), date(2026, 9, 17)):
        m = new_rows.get(("MRNA", d))
        if m is None:
            print(f"   {d}: no stored pair")
            continue
        print(f"   {d} {m['stage']} {m['reason']}  depth_on_low {m['depth_on_low'] * 100:.1f}%  "
              f"depth_on_close {m['depth_on_close'] * 100:.1f}%  sma20_margin {m['sma20_margin'] * 100:+.3f}%  "
              f"ma_stack_margin {m['ma_stack_margin'] * 100:+.3f}%")
    print(f"\ntotal {time.time() - t0:.0f}s; CSVs in {out_dir}")


if __name__ == "__main__":
    main()
