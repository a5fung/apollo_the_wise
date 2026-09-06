#!/usr/bin/env python3
"""#545 v3 (2026-09-05) — re-rank every Phase 3 cell on the TAIL first, then the median.

WHY: operator 2026-09-05 — "big tail is the key ingredient, median can be somewhat managed with
entry and exit" (docs/methodology/analysis_standard.md §THE STATISTIC). Phase 3
(docs/analysis/545p3_day1_stop_target_runner_sweep_2026-09-03.md) ranked its cells on paired sum R
and reported >=4R / P90 only on the pooled grid. This re-reads the SAME captured rows
(scripts/probes/_545p3_cells.tsv — nothing re-walked, nothing re-run) with the tail metrics on
every population cut: count of >=3R / >=5R outcomes and p90 FIRST, then median.

READ-ONLY, $0. No prod access. Input files are the 09-03 sweep's own output plus the 09-01 capture
(scripts/ep_replay_data/_pull2_out.txt, REGIME section) for the regime stamp.

Conventions, all stated:
  - R = campaign_r where present (the attempt-2 cells sum both legs) else realized_r; each cell's
    OWN unit at equal dollar risk — Phase 3 §1.
  - stop_width_pct < 0.5 rows are EXCLUDED (the #621/#623 near-zero-stop class). The count removed
    is printed; on this capture it is zero, which is itself reported rather than assumed.
  - "settled" only, unless the block says "settled + open marks": an open_at_horizon row carries a
    MARK, never a return. For the no-breakeven / long-hold runner cells the winners are BY
    CONSTRUCTION the open rows (a stop settles the instant it is hit), so the settled-only tail
    count is censored — the same trap the #327 lane carries — and both views are printed.
  - Regime = the row of mi_market_regime STRICTLY BEFORE the alert date (regime_date < alert_date),
    i.e. what was knowable at 09:31 — the same rule as broker/live_tracker.py:523 (the trade's
    stamp is the prior session's regime) and scripts/ep_replay.py::_score_one. A same-day join
    would be look-ahead (Phase 4, 09-02).
  - p90 = the value at index round(0.9*(n-1)) of the sorted sample (no interpolation).

Output: scripts/probes/_545v3_tail_rank_out.txt (captured once; the design doc reads the file).
"""
from __future__ import annotations

import csv
import statistics as st
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CELLS = HERE / "_545p3_cells.tsv"
PULL2 = HERE.parent / "ep_replay_data" / "_pull2_out.txt"
OUT = HERE / "_545v3_tail_rank_out.txt"

KEY_CELLS = [
    "orb_low/orb/live", "entry_minus_2r/orb/live", "adr_0.5/orb/live", "adr_0.75/orb/live",
    "adr_1.0/orb/live", "adr_1.25/orb/live",
    "entry_minus_2r/own/live", "adr_0.5/own/live", "adr_0.75/own/live",
    "entry_minus_2r/orb/breakeven", "entry_minus_2r/orb/hard", "entry_minus_2r/orb/live_trail_be",
    "entry_minus_2r/orb/sma10", "entry_minus_2r/orb/sma20", "entry_minus_2r/orb/atr1",
    "entry_minus_2r/orb/atr2", "entry_minus_2r/orb/gb25", "entry_minus_2r/orb/gb50",
    "entry_minus_2r/orb/t3", "entry_minus_2r/orb/t5", "entry_minus_2r/orb/t10",
    "entry_minus_2r/orb/t20",
    "adr_0.5/orb/t3", "adr_0.5/orb/t5", "adr_0.5/orb/atr2", "adr_0.5/orb/gb25",
    "adr_0.5/orb/sma10", "adr_0.5/orb/hard", "adr_0.5/orb/t20",
    "orb_low/orb/t3", "orb_low/orb/t5", "orb_low/orb/atr2", "orb_low/orb/hard", "orb_low/orb/t20",
    "entry_minus_2r/orb/live/x2:sd_5m_clear", "entry_minus_2r/orb/live/x2:ndo_o5l",
    "entry_minus_2r/orb/live/x2:ndo_pdl",
    "adr_0.5/orb/live/x2:sd_5m_clear", "adr_0.5/orb/live/x2:ndo_o5l", "adr_0.5/orb/live/x2:ndo_pdl",
    "orb_low/orb/live/x2:sd_5m_clear", "orb_low/orb/live/x2:ndo_o5l", "orb_low/orb/live/x2:ndo_pdl",
]
CENSOR_CELLS = [
    "entry_minus_2r/orb/live", "entry_minus_2r/orb/breakeven", "entry_minus_2r/orb/hard",
    "entry_minus_2r/orb/t3", "entry_minus_2r/orb/t20", "entry_minus_2r/orb/sma10",
    "adr_0.5/orb/live", "adr_0.5/orb/hard", "adr_0.5/orb/t3", "adr_0.5/orb/sma10",
    "orb_low/orb/live", "orb_low/orb/hard", "orb_low/orb/t3",
]
REGIME_CELLS = [
    "entry_minus_2r/orb/live", "orb_low/orb/live", "adr_0.5/orb/live",
    "entry_minus_2r/orb/t3", "adr_0.5/orb/t3", "orb_low/orb/t3", "entry_minus_2r/orb/hard",
]
OPERATOR_NAMES = [("PLTR", "2026-08-04"), ("TEAM", "2026-08-07"), ("HTFL", "2026-08-14"),
                  ("MRNA", "2026-08-19")]
LIVE = "entry_minus_2r/orb/live"


def _r(row):
    v = row["campaign_r"] if row["campaign_r"] not in ("", None) else row["realized_r"]
    return float(v) if v not in ("", None) else None


def _stop_width_pct(row):
    try:
        e = float(row["entry_px"]); s = float(row["stop"])
        return 100.0 * (e - s) / e
    except (ValueError, TypeError, ZeroDivisionError):
        return None


def _stats(xs):
    xs = sorted(xs); n = len(xs)
    if n == 0:
        return {"n": 0}
    return {
        "n": n, "sum": sum(xs), "mean": st.mean(xs), "med": st.median(xs),
        "p90": xs[int(round(0.9 * (n - 1)))],
        "ge2": sum(x >= 2 for x in xs), "ge3": sum(x >= 3 for x in xs),
        "ge4": sum(x >= 4 for x in xs), "ge5": sum(x >= 5 for x in xs),
        "max": max(xs), "win": sum(x > 0 for x in xs),
    }


def _fmt(d):
    if d["n"] == 0:
        return "n=0"
    return (f"n={d['n']:3d} sum={d['sum']:+7.1f} med={d['med']:+5.2f} p90={d['p90']:+5.2f} "
            f">=3R={d['ge3']:2d} >=5R={d['ge5']:2d} >=4R={d['ge4']:2d} max={d['max']:+5.1f} "
            f"win={d['win']:2d}")


def load_regimes():
    rows = []
    with open(PULL2) as fh:
        in_sec = False
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("=== "):
                in_sec = line.startswith("=== REGIME")
                continue
            if not in_sec or not line or line.startswith("regime_date") or line.startswith("("):
                continue
            p = line.split("|")
            if len(p) >= 2:
                rows.append((p[0], p[1]))
    rows.sort()
    return rows


def regime_before(regimes, alert_date):
    """Strictly-prior row — the entry-time stamp rule (live_tracker.py:523; ep_replay._score_one)."""
    best = None
    for d, r in regimes:
        if d < alert_date:
            best = r
        else:
            break
    return best


def main():
    rows = list(csv.DictReader(open(CELLS), delimiter="|"))
    regimes = load_regimes()
    thin = 0
    by = defaultdict(dict)   # cell -> (ticker,date) -> record
    for r in rows:
        w = _stop_width_pct(r)
        if w is not None and w < 0.5:
            thin += 1
            continue
        key = (r["ticker"], r["alert_date"])
        by[r["cell"]][key] = {
            "R": _r(r) if r["status"] == "settled" else None,
            "mark": float(r["mark_r"]) if (r["status"] == "open_at_horizon" and r["mark_r"]) else None,
            "status": r["status"], "admit": r["admit"], "month": r["alert_date"][:7],
            "regime": regime_before(regimes, r["alert_date"]),
        }
    live = by[LIVE]
    out = []
    P = out.append
    P("#545 v3 tail-first re-rank of the Phase 3 cells — generated by scripts/probes/_545v3_tail_rank.py")
    P(f"input rows: {len(rows)}   rows excluded for stop_width_pct < 0.5: {thin}   regime rows: {len(regimes)}")
    P("R = each cell's OWN unit at equal dollar risk. settled only unless stated. p90 = sorted[round(0.9*(n-1))].")
    cuts = [
        ("ALL ALERTS (267 campaigns; includes names the current scorer REJECTS)", lambda v: True),
        ("ADMITTED by the current scorer", lambda v: v["admit"] == "admit"),
        ("ADMITTED ex-May (May = the era the operator ruled stale)",
         lambda v: v["admit"] == "admit" and v["month"] != "2026-05"),
    ]
    for title, f in cuts:
        P(""); P(f"===== {title} =====")
        P(f"{'cell':40s} own settled | paired on the live cell's common settled rows: dSum d>=3R d>=5R dP90 dMed")
        for c in KEY_CELLS:
            d = by.get(c, {})
            xs = [v["R"] for v in d.values() if v["R"] is not None and f(v)]
            s = _stats(xs)
            common = [k for k, v in d.items() if v["R"] is not None and f(v)
                      and k in live and live[k]["R"] is not None]
            if common and c != LIVE:
                a = _stats([d[k]["R"] for k in common]); b = _stats([live[k]["R"] for k in common])
                pair = (f"n={len(common):3d} dSum={a['sum']-b['sum']:+6.1f} d>=3R={a['ge3']-b['ge3']:+d} "
                        f"d>=5R={a['ge5']-b['ge5']:+d} dP90={a['p90']-b['p90']:+.2f} dMed={a['med']-b['med']:+.2f}")
            else:
                pair = "(baseline)" if c == LIVE else ""
            P(f"{c:40s} {_fmt(s)} | {pair}")

    P(""); P("===== CENSORING — settled vs open-at-horizon MARKS, ADMITTED (the tail of a no-breakeven / long-hold rule lives in the OPEN rows) =====")
    P(f"{'cell':32s} settled  sumR  >=3R | open  markSum  marks>=3R | settled+marks: sum  >=3R | open names (mark)")
    for c in CENSOR_CELLS:
        d = by.get(c, {})
        s = [v["R"] for v in d.values() if v["R"] is not None and v["admit"] == "admit"]
        m = [(k, v["mark"]) for k, v in d.items() if v["mark"] is not None and v["admit"] == "admit"]
        mv = [x for _, x in m]
        names = ", ".join(f"{k[0]} {x:+.1f}" for k, x in sorted(m, key=lambda t: -t[1]))
        P(f"{c:32s} n={len(s):3d} {sum(s):+7.1f} {sum(x >= 3 for x in s):3d} | {len(mv):3d} {sum(mv):+7.1f} "
          f"{sum(x >= 3 for x in mv):3d} | {sum(s)+sum(mv):+7.1f} {sum(x >= 3 for x in s)+sum(x >= 3 for x in mv):3d} | {names}")

    P(""); P("===== REGIME (entry-time stamp = prior session's mi_market_regime row), ADMITTED, settled =====")
    P("Bull vs non-Bull for the key cells; n is small — report, do not conclude.")
    for c in REGIME_CELLS:
        d = by.get(c, {})
        for label, f in [("Bull", lambda v: v["regime"] == "Bull"), ("non-Bull", lambda v: v["regime"] != "Bull")]:
            xs = [v["R"] for v in d.values() if v["R"] is not None and v["admit"] == "admit" and f(v)]
            P(f"{c:32s} {label:9s} {_fmt(_stats(xs))}")
    P("")
    P("regime mix of ADMITTED settled campaigns under the live cell: " + str({
        reg: sum(1 for v in live.values() if v["R"] is not None and v["admit"] == "admit" and v["regime"] == reg)
        for reg in ("Bull", "Choppy", "Correcting", "Crisis", None)}))

    P(""); P("===== TAIL NAMES (>=3R), ADMITTED, settled — which names carry each cell =====")
    for c in ["entry_minus_2r/orb/live", "orb_low/orb/live", "adr_0.5/orb/live", "adr_0.75/orb/live",
              "entry_minus_2r/orb/t3", "entry_minus_2r/orb/t5", "entry_minus_2r/orb/atr2",
              "adr_0.5/orb/t3", "adr_0.5/orb/t5", "adr_0.5/orb/atr2", "orb_low/orb/t3",
              "adr_0.5/orb/live/x2:ndo_o5l"]:
        d = by.get(c, {})
        names = sorted([(round(v["R"], 1), k[0], k[1][5:], v["regime"]) for k, v in d.items()
                        if v["R"] is not None and v["admit"] == "admit" and v["R"] >= 3], reverse=True)
        P(f"{c:36s} {names}")

    P(""); P("===== OPERATOR-LABELLED EPs per cell (docs/methodology/operator_labelled_eps.md; ground truth) =====")
    for c in KEY_CELLS:
        d = by.get(c, {})
        vals = {}
        for t, dt in OPERATOR_NAMES:
            v = d.get((t, dt))
            if v is None:
                continue
            vals[t] = (f"{v['R']:+.2f}" if v["R"] is not None
                       else (f"open mark {v['mark']:+.2f}" if v["mark"] is not None else v["status"]))
        P(f"{c:40s} {vals}")

    P(""); P("===== THE 26 LIVE TRADES RE-WALKED (live26/* cells; Phase 3 §2 population, first attempts) =====")
    for c in ["live26/era_matched", "live26/orb_low", "live26/entry_minus_2r", "live26/adr_0.5",
              "live26/adr_0.75", "live26/adr_1.0", "live26/adr_1.25"]:
        d = by.get(c, {})
        xs = [v["R"] for v in d.values() if v["R"] is not None]
        P(f"{c:28s} {_fmt(_stats(xs))}")

    OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    print(f"\nwritten: {OUT}")


if __name__ == "__main__":
    main()
