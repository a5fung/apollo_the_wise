#!/usr/bin/env python3
"""The STARTING POINT table (his 11-02 method: "get as close as possible ... then work backwards"). For every watch night of
the frozen replay (the population stage's nights, eras A/B, nothing dated 2025+) and every listable pool member with a
strength rank >= RS_FLOOR (below the lowest of Qullamaggie's 269 breakout buys, 35.3), the live `breakout_v1.v1_gates`
VALUES (not just pass/fail) plus the candidate features the backward step needs (EMA10/EMA21, EMA21 rise across the base,
distance to the 52-week high, base depth). Captured ONCE; every rule is then applied post hoc.
Parity: the rows with rank >= 98 that v1 passes must reproduce the frozen list files exactly.
Usage: 10_feature_table.py [--limit-nights N] [--workers W]"""
import argparse, os, sys, time
from multiprocessing import get_context
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("BV1_SCRATCH", "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/qmbo1102")
PROBE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_v1_replay_1101"
sys.path.insert(0, PROBE); sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
import v1_replay as R  # noqa
from agents.market_intelligence import breakout_v1 as bv  # noqa
from agents.market_intelligence import consolidation_breakout as cb  # noqa
from scripts.probes._cb_backtest import runner  # noqa

RS_FLOOR = 30.0
OUTDIR = "/Users/alvinfung/apollo_data/qm_breakouts_1102"        # big table outside git; the summary + parity are committed
G = {}                                                             # set in the parent before fork, read by workers


def ema(x, n):
    a, out = 2 / (n + 1), np.empty(len(x))
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def nights_of(era, cal):
    d_lo = max(R.E_FIRST - pd.Timedelta(days=10).to_pytimedelta(), cal[0]) if era == "A" else R.ERA_B_D_FIRST
    d_hi = R.ERA_A_D_LAST if era == "A" else R.E_LAST
    out = []
    for ci, d in enumerate(cal):
        if d < d_lo or d > d_hi or ci + 1 >= len(cal):
            continue
        e = cal[ci + 1]
        if R.E_FIRST <= e <= R.E_LAST:
            out.append(ci)
    return out


def work(chunk):
    S, facts, rows_at, era = G["S"], G["facts"], G["rows_at"], G["era"]
    D = S.D; cal = D.cal
    bars_cache, ema_cache, rows = {}, {}, []
    for ci in chunk:
        members, _ = R.night_members(S, facts, ci, rows_at)
        rs_best, _, _, _ = cb.cross_section_one_date([m["r21"] for m in members], [m["r63"] for m in members],
                                                     [m["r126"] for m in members], [None] * len(members))
        for m, rb in zip(members, rs_best):
            if rb is None or rb < RS_FLOOR or not m["listable"] or not m["history"]:
                continue
            k = m["k"]
            if k not in bars_cache:
                bars_cache[k] = runner.bars_for(D, k)
                b = bars_cache[k][0]
                c = np.asarray(b.c, float)
                ema_cache[k] = (ema(c, 10), ema(c, 21), pd.Series(np.asarray(b.h, float)).rolling(252, min_periods=1).max().values)
            bars, cidx = bars_cache[k]
            Di = m["i"] - facts[k]["a"]
            try:
                g = bv.v1_gates(bars, Di, rs_best=rb, raw_close=m["raw_close"], cidx=cidx)
            except Exception as e:  # loud-ok: counted
                rows.append({"scan_date": cal[ci].isoformat(), "ticker": m["ticker"], "gate_error": f"{type(e).__name__}"})
                continue
            gg = g["gates"]
            e10, e21, h252 = ema_cache[k]
            pole = g.get("pole_date")
            P = None
            if pole:
                P = Di - int(gg["prior_move"]["value"].get("base_len") or 0)
            r = {"scan_date": cal[ci].isoformat(), "E": cal[ci + 1].isoformat(), "ticker": m["ticker"], "era": era,
                 "rs_best": float(rb), "ok_v1": int(g["ok"]), "failed": ",".join(g["failed"]),
                 "adr20": g.get("adr20"), "close": g.get("close"), "level": g.get("level"), "raw_close": m["raw_close"],
                 "prior_move": g.get("prior_move"), "pole_date": pole,
                 "e10": float(e10[Di]), "e21": float(e21[Di]), "hi252": float(h252[Di]),
                 "e21_rise_base": float(e21[Di] / e21[P] - 1) if P is not None and 0 <= P < Di else np.nan}
            for name, gv in gg.items():
                r["pass_" + name] = int(bool(gv.get("pass")))
                v = gv.get("value")
                if isinstance(v, dict):
                    for kk, vv in v.items():
                        if isinstance(vv, (int, float, bool, str)) or vv is None:
                            r[f"{name}.{kk}"] = vv
            rows.append(r)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-nights", type=int, default=None)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--eras", default="AB")
    a = ap.parse_args()
    os.makedirs(OUTDIR, exist_ok=True)
    for era in a.eras:
        t0 = time.time()
        S = R.load_store(era); D = S.D
        facts = [R.ticker_facts(S, k) for k in range(len(D.tickers))]
        row_tid = np.repeat(np.arange(len(D.tickers), dtype=np.int64), (D.stop - D.start).astype(np.int64))
        order = np.argsort(D.ci, kind="stable")
        rows_at = R._RowsAt(order, D.ci[order], row_tid)
        G.update(S=S, facts=facts, rows_at=rows_at, era=era)
        nights = nights_of(era, D.cal)
        if a.limit_nights:
            nights = nights[::max(1, len(nights) // a.limit_nights)][:a.limit_nights]
        chunks = [nights[i::a.workers * 4] for i in range(a.workers * 4)]
        print(f"era {era}: {len(nights)} nights, loaded in {time.time() - t0:.0f}s", flush=True)
        t1 = time.time()
        with get_context("fork").Pool(a.workers) as pool:
            parts = pool.map(work, chunks)
        df = pd.concat(parts, ignore_index=True).sort_values(["scan_date", "ticker"]); del parts
        tag = f"_limit{a.limit_nights}" if a.limit_nights else ""
        df.to_parquet(f"{OUTDIR}/features_era{era}{tag}.parquet", index=False)
        print(f"era {era}: {len(df)} rows ({len(df) / len(nights):.0f} a night) in {time.time() - t1:.0f}s; "
              f"gate errors {int(df.get('gate_error', pd.Series(dtype=object)).notna().sum())}", flush=True)
        G.clear(); del S, D, facts


if __name__ == "__main__":
    main()
