"""#697 item 4 (G3) - replay the SHIPPED `compute_flag_metrics` over every committed bar set, threaded the way
`run_flag_scan` threads it, and dump every field. Run it on the branch BEFORE and AFTER the change and diff the two
`--equiv` files: the post-breakout columns are telemetry, so the diff must be EMPTY (every stage, held_from_stage, reason,
score, pivot, triggered_from ... of every replayed row byte-identical). The `--events` file lists what the new columns say.

Populations (all committed, no prod read):
  corpus   tests/fixtures/htf_labelled_bars.psv          the labelled HTF corpus (CDNA, HNGE, MRNA, GH, HPE, NCI, ATAI, OUST, SHAZ, REPL)
  capture  scripts/probes/_697/q6_extra_bars.out         62 tickers, 2025-08 -> 2026-10-09, bars + the STORED prod rows
                                                          (stage, hold, reason, pivot) used here only to line events up with prod

State threading (what run_flag_scan reads, from the replay's own prior outputs):
  yesterday_stage / yesterday_was_held / recent_stages   prior rows in [d-5d, d)            (get_yesterday_flag_state / get_recent_flag_stages)
  prior_pivot_date / prior_pivot_high                    latest prior row with a pivot in [d-40d, d)   (get_yesterday_flag_pivots, _PIVOT_CARRY_DAYS)
  prior_post_breakout (NEW, if the detector takes it)    latest prior row with post_breakout_from in [d-40d, d)

Run from the repo root:
  PYTHONPATH=. python scripts/probes/_697_item4/replay_equiv.py --equiv OUT_equiv.jsonl --events OUT_events.tsv
"""
from __future__ import annotations

import argparse
import collections
import inspect
import json
from datetime import date, timedelta
from pathlib import Path

from agents.market_intelligence import flag_detector as fd

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "tests" / "fixtures" / "htf_labelled_bars.psv"
CAPTURE = ROOT / "scripts" / "probes" / "_697" / "q6_extra_bars.out"
REPLAY_FROM = date(2026, 5, 4)          # mi_flag_candidates starts here
NEW_KEYS = ("post_breakout_from", "days_since_breakout")
TAKES_CARRY = "prior_post_breakout" in inspect.signature(fd.compute_flag_metrics).parameters


def _bar(d, o, h, lo, c, v):
    return {"trade_date": date.fromisoformat(d), "open_price": float(o), "high_price": float(h),
            "low_price": float(lo), "close": float(c), "volume": float(v) if v not in ("", None) else 0.0}


def load_corpus():
    out = collections.defaultdict(list)
    for ln in CORPUS.read_text().splitlines():
        if ln.strip():
            t, d, o, h, lo, c, v = ln.split("|")
            out[t].append(_bar(d, o, h, lo, c, v))
    return out


def load_capture():
    bars, stored = collections.defaultdict(list), collections.defaultdict(dict)
    for ln in CAPTURE.read_text().splitlines():
        p = ln.split("\t")
        if p[0] == "bar":
            _, t, d, o, h, lo, c, v = p
            bars[t].append(_bar(d, o, h, lo, c, v))
        elif p[0] == "row":
            _, t, d, stage, held, reason, pdate, pprice = p
            stored[t][date.fromisoformat(d)] = (stage, held, reason, pdate, pprice)
    return bars, stored


def replay(ticker, bars):
    bars = sorted(bars, key=lambda r: r["trade_date"])
    dates = [r["trade_date"] for r in bars]
    out, prior = {}, []
    for i, d in enumerate(dates):
        if d < REPLAY_FROM or i + 1 < 60:
            continue
        rows = bars[max(0, i + 1 - fd._HISTORY_DAYS): i + 1]
        w5 = [m for m in prior if d - timedelta(days=5) <= m["scan_date"] < d]
        pw = [m for m in prior if d - timedelta(days=fd._PIVOT_CARRY_DAYS) <= m["scan_date"] < d]
        ppiv = next(((m["pivot_high_date"], m["pivot_high_price"]) for m in reversed(pw)
                     if m["pivot_high_date"] is not None and m["pivot_high_price"] is not None), None)
        kw = dict(
            ticker=ticker,
            yesterday_stage=w5[-1]["stage"] if w5 else None,
            yesterday_was_held=bool(w5[-1].get("held_from_stage")) if w5 else False,
            recent_stages=[m["stage"] for m in w5],
            prior_pivot_date=ppiv[0] if ppiv else None,
            prior_pivot_high=ppiv[1] if ppiv else None,
        )
        if TAKES_CARRY:
            kw["prior_post_breakout"] = next((m["post_breakout_from"] for m in reversed(pw)
                                              if m.get("post_breakout_from") is not None), None)
        m = fd.compute_flag_metrics(rows, **kw)
        m["scan_date"] = d
        prior.append(m)
        out[d] = m
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--equiv", required=True)
    ap.add_argument("--events", required=True)
    a = ap.parse_args()

    corpus = load_corpus()
    cap_bars, stored = load_capture()
    populations = [("corpus", t, b, {}) for t, b in sorted(corpus.items())] + \
                  [("capture", t, b, stored.get(t, {})) for t, b in sorted(cap_bars.items())]

    n_rows = n_post = 0
    ev_lines = ["src\tticker\tscan_date\tstage\tpivot_high_date\tbase_age\tpost_breakout_from\tdays_since_breakout\tfirst_day\tstored_prod_row"]
    with open(a.equiv, "w") as eq:
        for src, t, b, st in populations:
            res = replay(t, b)
            prev_pbo = None
            for d in sorted(res):
                m = res[d]
                n_rows += 1
                eq.write(json.dumps({"src": src, "t": t, "d": str(d),
                                     **{k: v for k, v in m.items() if k not in NEW_KEYS}},
                                    sort_keys=True, default=str) + "\n")
                pbo = m.get("post_breakout_from")
                if pbo is not None:
                    n_post += 1
                    first = prev_pbo != pbo
                    s = st.get(d)
                    ev_lines.append("\t".join(str(x) for x in (
                        src, t, d, m["stage"], m["pivot_high_date"], m["base_age"], pbo,
                        m.get("days_since_breakout"), "FIRST" if first else "",
                        "|".join(s) if s else "")))
                prev_pbo = pbo
    Path(a.events).write_text("\n".join(ev_lines) + "\n")
    print(f"rows replayed: {n_rows}; rows carrying post_breakout_from: {n_post}; detector takes carry: {TAKES_CARRY}")


if __name__ == "__main__":
    main()
