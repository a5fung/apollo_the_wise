"""R4 stage 3a recount (blind): DISCOVERY outcomes only. The function that reads any forward bar asserts E <= 2020-12-31 AND era A;
no check-set outcome is computed anywhere. Window = calendar sessions ci(E)..ci(E)+60 of the era calendar; buy-point proxy = max(level(D), open(E));
ends early at the session before (i) a guard break dated E+1..E+60 or (ii) a close-to-close move >= +70% / <= -50% on a split date (era A: a
session where raw/adjusted close steps; tolerance STEP_TOL, looser/tighter variants counted)."""
import json, sys
from datetime import date
import numpy as np, pandas as pd
import r4_common as C
import v1_replay as R
from scripts.probes._cb_backtest import runner

DISC_LAST_E = date(2020, 12, 31)
STEP_TOL = 0.005
HORIZON = 60


def forward_outcome(Dd, factor, cidx, bars, ci_E, E_date, era, guard, ticker, level, oE, adr, step_tol=STEP_TOL):
    assert era == "A" and E_date <= DISC_LAST_E, f"FORWARD READ REFUSED for {ticker} {E_date} era {era}"
    c = np.asarray(bars.c, float); l = np.asarray(bars.l, float); h = np.asarray(bars.h, float)
    lo = int(np.searchsorted(cidx, ci_E, "left")); hi = int(np.searchsorted(cidx, ci_E + HORIZON, "right"))
    assert lo < len(cidx) and int(cidx[lo]) == ci_E, "E bar missing"
    cal = Dd.cal
    end_full = hi                                   # exclusive, un-truncated
    end = hi
    reason = ""
    gdates = [dk[0] for dk in guard.get(ticker, ()) if E_date < dk[0] <= cal[min(ci_E + HORIZON, len(cal) - 1)]]
    if gdates:
        gd = min(gdates)
        cut = lo
        while cut < end and cal[int(cidx[cut])] < gd: cut += 1
        if cut < end: end, reason = cut, "guard"
    # split-date move (era A): factor steps between consecutive bars AND the adjusted close moves >= +70% / <= -50%
    for j in range(max(lo, 1), end):
        f0, f1 = factor[j - 1], factor[j]
        if abs(f1 / f0 - 1.0) > step_tol:
            mv = c[j] / c[j - 1] - 1.0
            if mv >= 0.70 or mv <= -0.50:
                end, reason = j, "split_move"
                break
    return lo, end, end_full, reason


def outcomes_for(win_c, win_l, win_h, proxy, hiE_proxy, low_E, adr, c_after):
    mx = float(win_c.max())
    first = int(np.argmax(win_c >= 1.5 * proxy)) if (win_c >= 1.5 * proxy).any() else -1
    big = first >= 0
    clean = bool(big and (first == 0 or not (win_l[1:first + 1] < low_E).any()))
    return {"win": big, "monster": mx >= 2.0 * proxy, "clean": clean, "adr_tail": mx >= proxy * (1.0 + 8.0 * adr),
            "fail": mx < 1.10 * proxy, "maxc_ratio": mx / proxy}


def main():
    C.assert_pins()
    FT = pd.read_parquet(C.BIG / f"r4_feature_table{C.SUF}.parquet")
    K = pd.read_parquet(C.BIG / f"r4_events_kept{C.SUF}.parquet")
    D_ = FT[(FT.set == "DISC")].merge(K[["era", "ticker", "D", "level", "raw_src", "Di", "bars_end_in_window", "guard_in_window"]],
                                      on=["era", "ticker", "D"], suffixes=("", "_k"))
    assert (D_.era == "A").all() and D_.E.max() <= DISC_LAST_E.isoformat()
    S = R.load_store("A"); Dd = S.D
    guard, _ = C.load_guard(C.GUARD_A, "A")
    rows = []
    cache = {}
    variants = {0.0001: [], STEP_TOL: [], 0.02: []}
    for r in D_.itertuples():
        k = Dd.tid[r.ticker]
        if k not in cache:
            a, b = int(Dd.start[k]), int(Dd.stop[k])
            cache[k] = (runner.bars_for(Dd, k), S.raw_factor[a:b])
        (bars, cidx), factor = cache[k]
        Di = int(np.searchsorted(cidx, r.ci))
        E_date = date.fromisoformat(r.E)
        o = np.asarray(bars.o, float); h = np.asarray(bars.h, float); l = np.asarray(bars.l, float); c = np.asarray(bars.c, float)
        proxy = max(r.level, float(o[Di + 1]))
        res = {}
        for tol in variants:
            lo, end, endf, reason = forward_outcome(Dd, factor, cidx, bars, r.ci + 1, E_date, "A", guard, r.ticker, r.level, float(o[Di + 1]), r.adr20, tol)
            variants[tol].append((lo, end, reason))
            if tol == STEP_TOL:
                res = dict(lo=lo, end=end, endf=endf, reason=reason)
        lo, end, endf, reason = res["lo"], res["end"], res["endf"], res["reason"]
        wc, wl, wh = c[lo:end], l[lo:end], h[lo:end]
        out = outcomes_for(wc, wl, wh, proxy, None, float(l[lo]), r.adr20, None)
        # un-truncated (calendar window only)
        u = outcomes_for(c[lo:endf], l[lo:endf], h[lo:endf], proxy, None, float(l[lo]), r.adr20, None)
        proxy2 = max(r.level, float(h[lo]))
        out2 = outcomes_for(wc, wl, wh, proxy2, None, float(l[lo]), r.adr20, None)
        # E+1..E+60 : E's own close excluded
        if end - lo > 1:
            out3 = outcomes_for(c[lo + 1:end], l[lo + 1:end], h[lo + 1:end], proxy, None, float(l[lo]), r.adr20, None)
            win_e1 = out3["win"]
        else:
            win_e1 = False
        nwin = end - lo
        rows.append({"era": r.era, "ticker": r.ticker, "D": r.D, "E": r.E, "proxy": proxy, "win": out["win"], "monster": out["monster"], "clean": out["clean"],
                     "adr_tail": out["adr_tail"], "fail": out["fail"], "win_untrunc": u["win"], "win_hiE": out2["win"], "win_E1": win_e1,
                     "truncated": reason != "", "trunc_reason": reason, "nbars": nwin, "full_window": bool(reason == "" and nwin == HORIZON + 1 and not r.bars_end_in_window),
                     "end_in_window": bool(r.bars_end_in_window)})
    O = pd.DataFrame(rows)
    O.to_parquet(C.BIG / f"r4_outcomes_disc{C.SUF}.parquet", index=False)
    log = open(C.OUTD / f"stage3a_outcomes{C.SUF}.log", "w")

    def P(*a):
        s = " ".join(str(x) for x in a); print(s, flush=True); log.write(s + "\n")
    P(f"discovery events {len(O)}; assert E<= {DISC_LAST_E}: max E {O.E.max()}")
    O["year"] = [int(x[:4]) for x in O.E]
    P("winners (>=1.5x):", int(O.win.sum()), f"rate {O.win.mean():.4%}; 2017-19 rate {O[O.year <= 2019].win.mean():.4%} (n={int((O.year <= 2019).sum())}, w={int(O[O.year <= 2019].win.sum())}); "
      f"2020 rate {O[O.year == 2020].win.mean():.4%} (n={int((O.year == 2020).sum())}, w={int(O[O.year == 2020].win.sum())})")
    P("per year win:", {int(y): (int(g.win.sum()), len(g)) for y, g in O.groupby("year")})
    P("monsters (>=2.0x):", int(O.monster.sum()), "clean winners:", int(O.clean.sum()), "adr-scaled tail:", int(O.adr_tail.sum()), "failed (<1.10x):", int(O.fail.sum()))
    P("truncated windows:", int(O.truncated.sum()), O.trunc_reason.value_counts().to_dict(), "| win_untrunc", int(O.win_untrunc.sum()), "win_hiE", int(O.win_hiE.sum()), "win_E1", int(O.win_E1.sum()),
      "| full-window only n", int(O.full_window.sum()))
    for tol, v in variants.items():
        base = variants[STEP_TOL]
        P(f"split-step tolerance {tol}: events whose window end differs from tol {STEP_TOL}: {sum(1 for a, b in zip(v, base) if a[1] != b[1])}; split_move truncations {sum(1 for a in v if a[2] == 'split_move')}")
    json.dump({"n": len(O), "win": int(O.win.sum()), "monster": int(O.monster.sum()), "clean": int(O.clean.sum()), "adr_tail": int(O.adr_tail.sum()),
               "fail": int(O.fail.sum()), "rate_all": float(O.win.mean()), "rate_1719": float(O[O.year <= 2019].win.mean()),
               "n_1719": int((O.year <= 2019).sum()), "w_1719": int(O[O.year <= 2019].win.sum()),
               "truncated": int(O.truncated.sum()), "trunc_reasons": O.trunc_reason.value_counts().to_dict(), "full_window": int(O.full_window.sum()),
               "win_untrunc": int(O.win_untrunc.sum()), "win_hiE": int(O.win_hiE.sum()), "win_E1": int(O.win_E1.sum())},
              open(C.OUTD / f"stage3a_results_r4{C.SUF}.json", "w"), indent=1)


if __name__ == "__main__":
    main()
