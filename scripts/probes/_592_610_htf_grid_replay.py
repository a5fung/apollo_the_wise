#!/usr/bin/env python3
"""#592 / #610 — replay the SHIPPED HTF detector over the stored candidate history
from RAW BARS, across the criteria grid the two PLAN lines ask about.

  runup ratio  {1.90 (sourced), 1.50 (the retired n=1)}
  pole window  {40 (sourced), 60 (the retired n=1)}
  ADR floor    {4.0% (shipped as STARTING), 3.5%, 3.0%}

NOTHING in flag_detector is changed by this script; every variant is a
monkeypatch of the module constants around the real `compute_flag_metrics`
(the #416 lesson: a replay built from lookalike logic is not evidence).

Inputs (pulled ONCE from prod on 2026-09-04, kept in the session scratchpad —
28 MB is too big for the repo; the SQL is here so the pull is reproducible):

  replay_bars.psv   ticker|trade_date|open|high|low|close|volume
      WITH t AS (SELECT DISTINCT ticker FROM mi_flag_candidates WHERE scan_date >= '2026-06-29')
      SELECT d.ticker, d.trade_date, d.open_price, d.high_price, d.low_price, d.close, d.volume
      FROM mi_daily_closes d JOIN t USING (ticker) WHERE d.trade_date >= '2025-06-01'
      ORDER BY d.ticker, d.trade_date;                       -- 594,955 rows / 2,174 tickers
  replay_pairs.psv  ticker|scan_date|stage|reason|pivot_high_date|pivot_high_price|runup_pct|base_age|held_from_stage
      SELECT ... FROM mi_flag_candidates WHERE scan_date >= '2026-06-29'   -- 27,446 rows
  replay_seed_pairs.psv  same columns, scan_date in [2026-06-15, 2026-06-29) for the same tickers
      -- the two weeks BEFORE the window so every variant threads its OWN prior
      -- pivot / stage state into 06-29 instead of borrowing prod's (4,978 rows).

Universe = the stored (ticker, scan_date) pairs. get_flag_universe is RS /
dollar-volume / burst gated, not threshold gated, so the same pairs are fair
to every variant.

State threading per variant mirrors the three prod queries EXACTLY, from the
variant's own prior outputs:
  get_yesterday_flag_pivots  -> most recent prior row in [d-5d, d) with a pivot
  get_yesterday_flag_stages  -> most recent prior row in [d-5d, d)
  get_recent_flag_stages     -> stages of prior rows in [d-5d, d), ascending
History per pair mirrors get_recent_daily_history(ticker, 380, end_date=d):
  bars with d-380 <= trade_date <= d.

Baseline reconciliation: the unmodified constants MUST reproduce the stored
stage on (near) every pair before any variant is read. Known legitimate
mismatches: `mna_filter:*` rows (applied AFTER compute on COILED/TRIGGERED
only, in flag_scan) and bars repaired/arrived after the 17:25 ET scan.

Usage:
  python scripts/probes/_592_610_htf_grid_replay.py --data-dir <scratchpad> --only-base
  python scripts/probes/_592_610_htf_grid_replay.py --data-dir <scratchpad>
"""
from __future__ import annotations

import argparse
import bisect
import csv
import pathlib
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import date, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from agents.market_intelligence import flag_detector as fd  # noqa: E402

ACTIONABLE = ("WATCH", "TIGHTENING", "COILED", "TRIGGERED")
BASELINE_MATCH_FLOOR = 0.95      # named floor — below this the harness is wrong, stop
WINDOW_START = date(2026, 6, 29)  # report from here; seed rows before it thread state only
CANARIES = ("CDNA", "HNGE")       # the only trader-labelled HTFs on disk (N=2)

GRID = [
    (1.90, 40, 0.040),   # BASELINE — shipped
    (1.90, 40, 0.035),
    (1.90, 40, 0.030),
    (1.90, 60, 0.040),
    (1.90, 60, 0.035),
    (1.90, 60, 0.030),
    (1.50, 40, 0.040),
    (1.50, 40, 0.035),
    (1.50, 40, 0.030),
    (1.50, 60, 0.040),
    (1.50, 60, 0.035),
    (1.50, 60, 0.030),
]


def vname(ratio, win, adr):
    return f"r{ratio:.2f}_w{win}_adr{adr*100:.1f}"


# ── loading ──────────────────────────────────────────────────────────────────

def _f(x):
    return float(x) if x not in ("", None) else None


def load_bars(path: pathlib.Path):
    bars: dict[str, list[dict]] = defaultdict(list)
    with path.open() as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            t, d, o, h, l, c, v = line.split("|")
            bars[t].append({
                "trade_date": date.fromisoformat(d),
                "open_price": _f(o), "high_price": _f(h), "low_price": _f(l),
                "close": _f(c), "volume": _f(v),
            })
    for t in bars:
        bars[t].sort(key=lambda r: r["trade_date"])
    return bars


def load_pairs(path: pathlib.Path):
    pairs: dict[str, list[dict]] = defaultdict(list)
    with path.open() as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            t, d, stage, reason, pd_, pp, ru, ba, held = line.split("|")
            pairs[t].append({
                "scan_date": date.fromisoformat(d), "stage": stage, "reason": reason,
                "pivot_high_date": date.fromisoformat(pd_) if pd_ else None,
                "pivot_high_price": _f(pp), "runup_pct": _f(ru),
                "base_age": int(ba) if ba else None, "held_from_stage": held or None,
            })
    for t in pairs:
        pairs[t].sort(key=lambda r: r["scan_date"])
    return pairs


# ── one variant over the whole history ───────────────────────────────────────

def run_variant(ratio, win, adr, bars, pairs, *, dates_index):
    fd._RUNUP_MIN_RATIO = ratio
    fd._RUNUP_LOOKBACK_DAYS = win
    fd._HTF_MIN_ADR_PCT = adr
    out: dict[str, list[dict]] = {}
    stale_last_bar = 0
    missing = 0
    for ticker, plist in pairs.items():
        tb = bars.get(ticker)
        if not tb:
            missing += len(plist)
            continue
        tdates = dates_index[ticker]
        prior: list[dict] = []          # this variant's own prior outputs for the ticker
        results = []
        for p in plist:
            d = p["scan_date"]
            lo = bisect.bisect_left(tdates, d - timedelta(days=fd._HISTORY_DAYS))
            hi = bisect.bisect_right(tdates, d)
            rows = tb[lo:hi]
            if not rows or len(rows) < 60:
                # prod: `if not history or len(history) < 60: return None` (no row written)
                missing += 1
                continue
            if rows[-1]["trade_date"] != d:
                stale_last_bar += 1
            cutoff = d - timedelta(days=5)
            window = [r for r in prior if cutoff <= r["scan_date"] < d]
            ystage = window[-1]["stage"] if window else None
            recent = [r["stage"] for r in window]
            ppiv = next(((r["pivot_high_date"], r["pivot_high_price"])
                         for r in reversed(window) if r["pivot_high_date"] is not None), None)
            m = fd.compute_flag_metrics(
                rows, ticker=ticker, yesterday_stage=ystage, recent_stages=recent,
                prior_pivot_date=ppiv[0] if ppiv else None,
                prior_pivot_high=ppiv[1] if ppiv else None,
            )
            m["scan_date"] = d
            prior.append(m)
            results.append(m)
        out[ticker] = results
    return out, stale_last_bar, missing


# ── outcomes ─────────────────────────────────────────────────────────────────

def fwd(bars_t, dates_t, d, k):
    """Close-to-close return k sessions after d (None if the window is truncated)."""
    i = bisect.bisect_left(dates_t, d)
    if i >= len(dates_t) or dates_t[i] != d or i + k >= len(bars_t):
        return None
    c0 = bars_t[i]["close"]
    return bars_t[i + k]["close"] / c0 - 1.0 if c0 else None


def excursion(bars_t, dates_t, d, k=20):
    """(MFE, MAE) over the next k sessions from d's close; None if truncated."""
    i = bisect.bisect_left(dates_t, d)
    if i >= len(dates_t) or dates_t[i] != d or i + k >= len(bars_t):
        return None, None
    c0 = bars_t[i]["close"]
    seg = bars_t[i + 1:i + 1 + k]
    return max(r["high_price"] for r in seg) / c0 - 1.0, min(r["low_price"] for r in seg) / c0 - 1.0


def _stats(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return "n=0"
    med = statistics.median(vals)
    mean = statistics.fmean(vals)
    hit5 = sum(v >= 0.05 for v in vals) / len(vals)
    hit10 = sum(v >= 0.10 for v in vals) / len(vals)
    neg = sum(v < 0 for v in vals) / len(vals)
    return f"n={len(vals)} med={med:+.1%} mean={mean:+.1%} >=+5%:{hit5:.0%} >=+10%:{hit10:.0%} <0:{neg:.0%}"


def episodes(results_t):
    """Group a ticker's rows into setup EPISODES: a maximal run of consecutive rows
    at an actionable stage sharing one pivot_high_date. Returns list of dicts."""
    eps = []
    cur = None
    for m in results_t:
        if m["scan_date"] < WINDOW_START:
            continue
        act = m["stage"] in ACTIONABLE
        key = m["pivot_high_date"]
        if act and cur is not None and cur["pivot"] == key:
            cur["rows"].append(m)
        elif act:
            cur = {"pivot": key, "rows": [m]}
            eps.append(cur)
        else:
            cur = None
    for e in eps:
        e["first"] = e["rows"][0]
        e["trig"] = next((r for r in e["rows"] if r["stage"] == "TRIGGERED"), None)
        e["max_stage"] = max(e["rows"], key=lambda r: ACTIONABLE.index(r["stage"]))["stage"]
    return eps


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--only-base", action="store_true")
    ap.add_argument("--out", default=None, help="results dir (default: <data-dir>/grid_out)")
    args = ap.parse_args()
    dd = pathlib.Path(args.data_dir)
    out_dir = pathlib.Path(args.out) if args.out else dd / "grid_out"
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    bars = load_bars(dd / "replay_bars.psv")
    pairs_main = load_pairs(dd / "replay_pairs.psv")
    pairs_seed = load_pairs(dd / "replay_seed_pairs.psv")
    pairs: dict[str, list[dict]] = defaultdict(list)
    for t, pl in pairs_seed.items():
        pairs[t].extend(pl)
    for t, pl in pairs_main.items():
        pairs[t].extend(pl)
    for t in pairs:
        pairs[t].sort(key=lambda r: r["scan_date"])
    n_pairs = sum(len(v) for v in pairs_main.values())
    n_seed = sum(len(v) for v in pairs_seed.values())
    if n_pairs < 20000 or len(bars) < 2000:
        raise SystemExit(f"input looks truncated: {n_pairs} pairs / {len(bars)} tickers of bars")
    dates_index = {t: [r["trade_date"] for r in tb] for t, tb in bars.items()}
    print(f"loaded {sum(len(v) for v in bars.values()):,} bars / {len(bars):,} tickers; "
          f"{n_pairs:,} pairs + {n_seed:,} seed rows  ({time.time()-t0:.0f}s)")

    stored = {(t, p["scan_date"]): p for t, pl in pairs_main.items() for p in pl}
    scan_dates = sorted({p["scan_date"] for pl in pairs_main.values() for p in pl})
    n_days = len(scan_dates)
    grid = GRID[:1] if args.only_base else GRID
    base_name = vname(*GRID[0])
    saved = dict(ratio=fd._RUNUP_MIN_RATIO, win=fd._RUNUP_LOOKBACK_DAYS, adr=fd._HTF_MIN_ADR_PCT)
    assert (saved["ratio"], saved["win"], saved["adr"]) == GRID[0], "GRID[0] must equal the shipped constants"

    summaries = {}
    per_variant = {}
    try:
        for (ratio, win, adr) in grid:
            name = vname(ratio, win, adr)
            t1 = time.time()
            res, stale, missing = run_variant(ratio, win, adr, bars, pairs, dates_index=dates_index)
            per_variant[name] = res
            # ── write per-pair rows (window only) with outcomes
            fn = out_dir / f"{name}.csv"
            n_rows = 0
            with fn.open("w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["ticker", "scan_date", "stage", "reason", "pivot_date", "pivot_price", "runup",
                            "base_age", "base_high", "base_low", "fwd5", "fwd10", "fwd20", "mfe20", "mae20"])
                for t, rl in res.items():
                    tb, td = bars[t], dates_index[t]
                    for m in rl:
                        if m["scan_date"] < WINDOW_START:
                            continue
                        d = m["scan_date"]
                        mfe, mae = excursion(tb, td, d)
                        w.writerow([t, d, m["stage"], m["reason"], m["pivot_high_date"], m["pivot_high_price"],
                                    None if m["runup_pct"] is None else round(m["runup_pct"], 4),
                                    m["base_age"], m["base_high"], m["base_low"],
                                    *(None if v is None else round(v, 4)
                                      for v in (fwd(tb, td, d, 5), fwd(tb, td, d, 10), fwd(tb, td, d, 20), mfe, mae))])
                        n_rows += 1
            if n_rows == 0:
                raise SystemExit(f"variant {name} produced ZERO rows — harness broken")

            # ── baseline reconciliation against the stored rows
            if name == base_name:
                match = mism = 0
                mism_kinds = Counter()
                mism_examples = []
                for t, rl in res.items():
                    for m in rl:
                        s = stored.get((t, m["scan_date"]))
                        if s is None:
                            continue
                        if s["stage"] == m["stage"]:
                            match += 1
                        else:
                            mism += 1
                            kind = ("mna_filter" if (s["reason"] or "").startswith("mna_filter")
                                    else f"{s['stage']}->{m['stage']}")
                            mism_kinds[kind] += 1
                            if len(mism_examples) < 12:
                                mism_examples.append((t, m["scan_date"], s["stage"], s["reason"], m["stage"], m["reason"]))
                rate = match / max(1, match + mism)
                print(f"\nBASELINE RECONCILIATION: {match:,} match / {mism:,} mismatch = {rate:.2%} "
                      f"(stale-last-bar pairs {stale}, skipped<60rows {missing})")
                print("  mismatch kinds:", dict(mism_kinds.most_common(12)))
                for ex in mism_examples:
                    print("   ", ex)
                if rate < BASELINE_MATCH_FLOOR:
                    raise SystemExit(f"baseline match {rate:.2%} < floor {BASELINE_MATCH_FLOOR:.0%} — do NOT read the grid")

            # ── summary
            stage_rows = Counter()
            act_tickers = set()
            trig_events = []      # (ticker, date)
            ep_list = []
            reject_fam = Counter()
            for t, rl in res.items():
                for m in rl:
                    if m["scan_date"] < WINDOW_START:
                        continue
                    stage_rows[m["stage"]] += 1
                    if m["stage"] in ACTIONABLE:
                        act_tickers.add(t)
                    if m["stage"] == "unqualified":
                        r = m["reason"] or "null"
                        fam = ("adr" if r.startswith("adr_") else "adv" if r.startswith("adv_") else
                               "runup" if r.startswith("runup_") else "base_age" if r.startswith("base_age") else
                               "flag_depth" if r.startswith("flag_low") else "not_stage2" if r.startswith("pole_") else
                               "ma_stack" if r.startswith("ma_stack") else "flagpole_vol" if r.startswith("flagpole") else
                               r.split("_")[0])
                        reject_fam[fam] += 1
                for e in episodes(rl):
                    e["ticker"] = t
                    ep_list.append(e)
                    if e["trig"] is not None:
                        trig_events.append((t, e["trig"]["scan_date"]))
            # outcomes
            first_watch_f10 = [fwd(bars[e["ticker"]], dates_index[e["ticker"]], e["first"]["scan_date"], 10) for e in ep_list]
            first_watch_f20 = [fwd(bars[e["ticker"]], dates_index[e["ticker"]], e["first"]["scan_date"], 20) for e in ep_list]
            trig_f5 = [fwd(bars[t], dates_index[t], d, 5) for t, d in trig_events]
            trig_f10 = [fwd(bars[t], dates_index[t], d, 10) for t, d in trig_events]
            trig_f20 = [fwd(bars[t], dates_index[t], d, 20) for t, d in trig_events]
            trig_mfe = [excursion(bars[t], dates_index[t], d)[0] for t, d in trig_events]
            trig_mae = [excursion(bars[t], dates_index[t], d)[1] for t, d in trig_events]
            act_rows = sum(stage_rows[s] for s in ACTIONABLE)
            summaries[name] = dict(
                stage_rows=dict(stage_rows), act_rows=act_rows, act_per_day=act_rows / n_days,
                act_tickers=len(act_tickers), episodes=len(ep_list), trig=len(trig_events),
                trig_events=trig_events, ep_keys={(e["ticker"], e["pivot"]) for e in ep_list},
                reject_fam=dict(reject_fam.most_common()),
                o_first_f10=_stats(first_watch_f10), o_first_f20=_stats(first_watch_f20),
                o_trig_f5=_stats(trig_f5), o_trig_f10=_stats(trig_f10), o_trig_f20=_stats(trig_f20),
                o_trig_mfe=_stats(trig_mfe), o_trig_mae=_stats(trig_mae),
            )
            print(f"\n== {name}  ({time.time()-t1:.0f}s) ==")
            print(f"  rows by stage: {dict(stage_rows)}")
            print(f"  actionable rows {act_rows:,} ({act_rows/n_days:.1f}/day) | tickers {len(act_tickers)} | "
                  f"episodes {len(ep_list)} | TRIGGERED events {len(trig_events)}")
            print(f"  reject families: {dict(reject_fam.most_common(8))}")
            print(f"  first-WATCH fwd10: {summaries[name]['o_first_f10']}")
            print(f"  first-WATCH fwd20: {summaries[name]['o_first_f20']}")
            print(f"  TRIGGERED fwd5 : {summaries[name]['o_trig_f5']}")
            print(f"  TRIGGERED fwd10: {summaries[name]['o_trig_f10']}")
            print(f"  TRIGGERED fwd20: {summaries[name]['o_trig_f20']}")
            print(f"  TRIGGERED mfe20: {summaries[name]['o_trig_mfe']}   mae20: {summaries[name]['o_trig_mae']}")
            # canaries
            for c in CANARIES:
                rl = [m for m in res.get(c, []) if m["scan_date"] >= WINDOW_START]
                acts = [(m["scan_date"].isoformat(), m["stage"], f"{m['runup_pct']:+.0%}" if m["runup_pct"] is not None else "-",
                         str(m["pivot_high_date"])) for m in rl if m["stage"] in ACTIONABLE]
                print(f"  canary {c}: {len(acts)} actionable rows"
                      + (f"; first {acts[0]} last {acts[-1]}" if acts else "; NEVER actionable")
                      + f"; runup on 08-21: " + next((f"{m['runup_pct']:+.0%}" for m in rl
                                                       if m["scan_date"] == date(2026, 8, 21) and m["runup_pct"] is not None), "n/a"))
    finally:
        fd._RUNUP_MIN_RATIO = saved["ratio"]
        fd._RUNUP_LOOKBACK_DAYS = saved["win"]
        fd._HTF_MIN_ADR_PCT = saved["adr"]

    # ── incremental vs baseline (both directions)
    if len(grid) > 1:
        b = summaries[base_name]
        print("\n== INCREMENTAL vs BASELINE (rows/day = actionable rows per scan day) ==")
        print(f"{'variant':24} {'act/day':>8} {'tickers':>8} {'episodes':>9} {'TRIG':>5} {'+episodes':>10} {'+TRIG':>6}  "
              f"{'new-TRIG fwd10':<44} {'new-TRIG fwd20'}")
        for (ratio, win, adr) in grid:
            name = vname(ratio, win, adr)
            s = summaries[name]
            new_eps = s["ep_keys"] - b["ep_keys"]
            new_trig = [e for e in s["trig_events"] if e not in set(b["trig_events"])]
            lost_trig = [e for e in b["trig_events"] if e not in set(s["trig_events"])]
            nf10 = _stats([fwd(bars[t], dates_index[t], d, 10) for t, d in new_trig])
            nf20 = _stats([fwd(bars[t], dates_index[t], d, 20) for t, d in new_trig])
            print(f"{name:24} {s['act_per_day']:8.1f} {s['act_tickers']:8d} {s['episodes']:9d} {s['trig']:5d} "
                  f"{len(new_eps):+10d} {len(new_trig):+6d}  {nf10:<44} {nf20}"
                  + (f"  (lost {len(lost_trig)} baseline TRIG)" if lost_trig else ""))
        # list the new TRIGGERED names per variant (distinct tickers) with fwd20
        print("\n== NEW TRIGGERED events per variant (ticker date fwd10 fwd20 mfe20) ==")
        for (ratio, win, adr) in grid[1:]:
            name = vname(ratio, win, adr)
            s = summaries[name]
            new_trig = sorted(e for e in s["trig_events"] if e not in set(b["trig_events"]))
            items = []
            for t, d in new_trig:
                f10 = fwd(bars[t], dates_index[t], d, 10)
                f20 = fwd(bars[t], dates_index[t], d, 20)
                mfe = excursion(bars[t], dates_index[t], d)[0]
                items.append(f"{t} {d.isoformat()[5:]} "
                             f"{'' if f10 is None else f'{f10:+.0%}'}/{'' if f20 is None else f'{f20:+.0%}'}/{'' if mfe is None else f'{mfe:+.0%}'}")
            print(f"  {name}: " + ("; ".join(items) if items else "none"))

    # ── re-anchor defect measurement (baseline): a pivot walk onto a MARGINAL new high
    #    that was NOT a closing breakout, dropping runup from >=90% to <90%.
    base = per_variant[base_name]
    fd._RUNUP_MIN_RATIO, fd._RUNUP_LOOKBACK_DAYS, fd._HTF_MIN_ADR_PCT = saved["ratio"], saved["win"], saved["adr"]
    wick, brk, lower = [], [], []
    for t, rl in base.items():
        tb, td = bars[t], dates_index[t]
        prev_act = None
        for m in rl:
            if m["scan_date"] < WINDOW_START:
                prev_act = m if (m["stage"] in ACTIONABLE and m["runup_pct"] is not None and m["runup_pct"] >= 0.9) else prev_act
                continue
            if (prev_act is not None and m["stage"] == "unqualified" and (m["reason"] or "").startswith("runup_")
                    and m["pivot_high_date"] is not None and prev_act["pivot_high_date"] is not None
                    and m["pivot_high_date"] > prev_act["pivot_high_date"]
                    and (m["scan_date"] - prev_act["scan_date"]).days <= 7):
                beat = m["pivot_high_price"] / prev_act["pivot_high_price"] - 1.0
                if beat <= 0:
                    lower.append((t, m["scan_date"], beat))
                else:
                    # was the new pivot bar a closing breakout of the prior flag (state-machine definition)?
                    i = bisect.bisect_left(td, m["pivot_high_date"])
                    j = bisect.bisect_left(td, prev_act["pivot_high_date"])
                    seg = tb[j + 1:i]
                    bh_close = max((r["close"] for r in seg), default=None)
                    v20 = [r["volume"] or 0 for r in tb[max(0, i - 20):i]]
                    vr = (tb[i]["volume"] or 0) / (sum(v20) / len(v20)) if v20 and sum(v20) > 0 else None
                    is_brk = bh_close is not None and tb[i]["close"] > bh_close and vr is not None and vr >= fd._BREAKOUT_VOL_RATIO
                    (brk if is_brk else wick).append((t, m["scan_date"], beat, prev_act["runup_pct"], m["runup_pct"]))
            if m["stage"] in ACTIONABLE and m["runup_pct"] is not None and m["runup_pct"] >= 0.9:
                prev_act = m
            elif m["stage"] in ACTIONABLE:
                prev_act = None
            elif not (m["reason"] or "").startswith("base_age"):
                prev_act = None
    print("\n== RE-ANCHOR DEFECT (baseline): pivot walked onto a higher bar within 7 days of a >=90% actionable row, runup then rejected ==")
    print(f"  onto a marginal high that was NOT a closing breakout (the defect): {len(wick)} rows / {len({t for t,*_ in wick})} tickers")
    for row in sorted(wick):
        print(f"    {row[0]} {row[1]} beat {row[2]:+.1%}  runup {row[3]:+.0%} -> {row[4]:+.0%}")
    print(f"  onto a bar that WAS a closing breakout (legit — the flag resolved): {len(brk)} rows / {len({t for t,*_ in brk})} tickers")
    print(f"  onto a LOWER high (stale flag aged out of the 25-session pivot lookback — by design): {len(lower)} rows / {len({t for t,*_ in lower})} tickers")
    print(f"\ntotal {time.time()-t0:.0f}s; per-pair CSVs in {out_dir}")


if __name__ == "__main__":
    main()
