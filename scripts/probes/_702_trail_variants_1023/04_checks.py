"""#705 Track B — step 4: own-code checks of the trail tables, no trail_lib / esr_lib walker import. (a) a plain per-trade Python walk of
every trigger × partial (DEFINITIONS.md, written independently of the lockstep code) on 300 random trades per cell per table (P-win, R1, the
control sample) per era, inputs at the frame's float32 prices; (b) the retry rule on every cell of the P-win table and two R1 cells, re-derived
from raw closes (an X4 level exit must never earn a retry); (c) the P-win still-in / kept-½ / kept-¼ / median kept share / median sessions
held recounted from the trade table for two new cells per era; (g) the matched-control file's per-cell means equal the JSON's control
per-base R. Writes 04_checks.txt."""
import json, sys
import numpy as np, pandas as pd

HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_trail_variants_1023"
DATA = {"2017-21": ("/Users/alvinfung/apollo_data/cb702_pre", None), "2022-24": ("/Users/alvinfung/apollo_data/cb702", "2024-12-31")}
lines = []


def log(s):
    print(s, flush=True); lines.append(s)


def naive_trail(o, h, l, c, sma, adr_b, fill, stop0, start_j, trigger, partial, horizon=120):
    """a plain per-trade walk of DEFINITIONS.md; arrays start at session 0 (the entry day). Returns (pnl per share, exit kind, exit session, trail kind)."""
    risk = fill - stop0; target = fill + 2 * risk; cut = fill + risk
    P1 = partial == "P1"
    stop = stop0; third = False; hit2 = False; rem = 1.0; pnl = 0.0; reached = False
    under_prev = False; watch = -1
    n = len(c)
    for j in range(start_j, horizon + 1):
        if j >= n:
            last = c[~np.isnan(c)][-1]
            return pnl + (last - fill) * rem, "degraded", j - 1, 0
        oj, hj, lj, cj = o[j], h[j], l[j], c[j]
        if np.isnan(cj):
            if j == horizon:
                last = c[:j + 1][~np.isnan(c[:j + 1])][-1]
                return pnl + (last - fill) * rem, "censored", j, 0
            continue
        done = third if P1 else hit2
        lvl = stop; x4 = False
        if trigger == "X4":
            sp = sma[j - 1]
            if (done or j >= 3) and np.isfinite(sp) and sp > stop:
                lvl = sp; x4 = True
        gap = (not done) and oj >= target
        if oj <= lvl or lj <= lvl:
            if gap and P1:
                pnl += (oj - fill) / 3; rem -= 1 / 3
            px = oj if oj <= lvl else lvl
            return pnl + (px - fill) * rem, ("trailed" if x4 else "stopped"), j, (5 if x4 else 0)
        new_stop = stop
        if gap or ((not done) and hj >= target):
            if P1:
                px = oj if gap else target
                pnl += (px - fill) / 3; rem -= 1 / 3; third = True
            hit2 = True; new_stop = max(stop, fill)
        if j <= 3 and hj >= cut:
            reached = True
        if j == 3 and not reached:
            return pnl + (cj - fill) * rem, "time_exit", j, 0
        if P1 and j == 3 and not third and cj > fill:
            pnl += (cj - fill) / 3; rem -= 1 / 3; third = True; new_stop = max(new_stop, fill)
        if trigger != "X4":
            live = (third if P1 else hit2) or j >= 3
            s = sma[j]; fin = np.isfinite(s); under = fin and cj < s
            sig = False; kind = 0
            if trigger == "X1":
                sig = live and under; kind = 1
            elif trigger == "X2":
                dec = fin and cj <= s * (1 - 0.5 * adr_b); two = under and under_prev
                sig = live and (dec or two); kind = 2 if dec else (3 if two else 0)
                under_prev = under
            else:
                if watch >= 0 and fin and cj >= s:
                    watch = -1
                elif watch >= 0 and j == watch + 2:
                    sig = True; kind = 4
                elif live and watch < 0 and under:
                    watch = j
            if sig:
                if j + 1 < n and np.isfinite(o[j + 1]):
                    return pnl + (o[j + 1] - fill) * rem, ("censored" if j == horizon else "trailed"), j + 1, kind
                return pnl + (cj - fill) * rem, "degraded", j, kind
        if j == horizon:
            return pnl + (cj - fill) * rem, "censored", j, 0
        stop = new_stop
    raise RuntimeError


CODE = {"stopped": 1, "time_exit": 2, "trailed": 3, "censored": 4, "degraded": 5}
rng = np.random.default_rng(23)
ok_all = True
for era, (data, cut) in DATA.items():
    log(f"== {era}")
    J = json.load(open(f"{HERE}/02_numbers_{era}.json"))
    ex = pd.read_csv(f"{data}/daily_closes_all.csv.gz", header=None, names=["ticker", "date", "o", "h", "l", "c", "v"], dtype={"ticker": str, "date": str}, keep_default_na=False)
    if cut:
        ex = ex[ex.date <= cut]; assert ex.date.max() <= cut
    cal = pd.Index(ex[ex.ticker == "SPY"].date.sort_values().values)
    ex = ex[ex.date.isin(cal)]
    r1 = pd.read_csv(f"{data}/out/trail_r1_{era}.tsv.gz", sep="\t", low_memory=False)
    sm = pd.read_csv(f"{data}/out/trail_ctlsample_{era}.tsv.gz", sep="\t", low_memory=False)
    win = pd.read_csv(f"{data}/out/trail_win_{era}.tsv.gz", sep="\t", low_memory=False)
    cells = J["cells"]
    assert set(r1.cell) == set(cells) == set(win.cell) == set(sm.cell), "a table is missing a cell"
    need = set(r1.ticker) | set(sm.ticker) | set(win.ticker)
    ex = ex[ex.ticker.isin(need)]
    arr = {}
    for tk, d in ex.groupby("ticker"):
        full = pd.DataFrame(index=cal).join(d.set_index("date")[["o", "h", "l", "c"]]).astype("float32")
        full["sma20"] = full.c.rolling(20, min_periods=20).mean().astype("float32")
        full["sma10"] = full.c.rolling(10, min_periods=10).mean().astype("float32")
        arr[tk] = {k: full[k].to_numpy().astype("float64") for k in ("o", "h", "l", "c", "sma20", "sma10")}
    # (a) naive re-walk, 300 random valid trades per cell per table
    for name, T in (("R1", r1), ("control sample", sm), ("P-win", win)):
        tot_bad = 0; tot_ties = 0; tot_n = 0; maxd_all = 0.0; per_cell = []
        for cell in cells:
            v = T[(T.status >= 0) & (T.cell == cell)]
            pick = v.sample(min(300, len(v)), random_state=int(rng.integers(1e9)))
            bad = 0; ties = 0; maxd = 0.0
            for r in pick.itertuples():
                a = arr[r.ticker]; e = int(r.e); start_j = 1
                sma = a["sma20"] if int(r.sma_n) == 20 else a["sma10"]
                seg = {k: a[k][e:] for k in ("o", "h", "l", "c")}; seg["sma"] = sma[e:]
                # the fill = the frame's float32 close of the entry day; the stop = fill × (1 − ADR20) in float32, as stop_levels does (the table's 7-digit text can move a 1-cent stop's R by 1e-3)
                fill32 = np.float32(a["c"][e]); stop32 = np.float32(fill32 * (1.0 - 1.0 * np.float32(r.adr_b)))
                assert abs(float(fill32) - r.fill) <= 1e-5 * r.fill and abs(float(stop32) - r.stop0) <= 1e-5 * r.stop0, (r.ticker, e, fill32, r.fill, stop32, r.stop0)
                fill, stop0 = float(fill32), float(stop32)
                pnl, st, xj, tk = naive_trail(seg["o"], seg["h"], seg["l"], seg["c"], seg["sma"], float(r.adr_b), fill, stop0, start_j, r.trigger, r.partial)
                R = pnl / (fill - stop0)
                d = abs(R - r.realized_r); maxd = max(maxd, d)
                if d > 1e-3 or CODE[st] != r.status or xj != r.exit_j or (tk != r.trail_kind and r.status in (3, 4, 5)):
                    tgt = fill + 2 * (fill - stop0); cut_ = fill + (fill - stop0); w = slice(max(start_j - 1, 0), max(xj, int(r.exit_j)) + 2)
                    near = lambda x, lvl: np.nanmin(np.abs(x[w] - lvl)) / abs(lvl) < 2e-6
                    rel = np.nanmin(np.abs(seg["c"][w] - seg["sma"][w]) / seg["sma"][w]) if np.isfinite(seg["sma"][w]).any() else 1.0
                    sp = np.roll(seg["sma"], 1); sp[0] = np.nan          # the prior session's average, aligned to the session (X4's level)
                    rel4 = np.nanmin(np.minimum(np.abs(seg["l"][w] - sp[w]), np.abs(seg["o"][w] - sp[w])) / sp[w]) if np.isfinite(sp[w]).any() else 1.0
                    rel2 = np.nanmin(np.abs(seg["c"][w] - seg["sma"][w] * (1 - 0.5 * float(r.adr_b))) / seg["sma"][w]) if np.isfinite(seg["sma"][w]).any() else 1.0
                    tie = near(seg["h"], tgt) or near(seg["o"], tgt) or near(seg["l"], stop0) or near(seg["o"], stop0) or near(seg["h"], cut_) or near(seg["l"], fill) or near(seg["o"], fill) or rel < 2e-6 or rel2 < 2e-6 or rel4 < 2e-6
                    if tie:
                        ties += 1
                    else:
                        bad += 1
                        if tot_bad + bad <= 4:
                            log(f"    MISMATCH {name} {cell} {r.ticker} e={e} att {r.attempt}: mine R {R:+.4f} {st} exit {xj} kind {tk} vs table {r.realized_r:+.4f} status {r.status} exit {r.exit_j} kind {r.trail_kind}")
            per_cell.append(f"{cell} {bad}/{ties}")
            tot_bad += bad; tot_ties += ties; tot_n += len(pick); maxd_all = max(maxd_all, maxd)
        log(f"  (a) naive trail re-walk, {name}: {tot_n} random trades over {len(cells)} cells, mismatches beyond text rounding and not a float32 knife edge {tot_bad}; knife-edge ties {tot_ties}; max |ΔR| {maxd_all:.1e}; per cell (bad/ties): {', '.join(per_cell)}")
        ok_all &= tot_bad == 0
    # (b) the retry rule: every attempt >= 1 follows a STOP exit (status 1, never an X4 level exit) and enters at the first close above the base high within 20 sessions
    for name, T, hi_col, cell_list in (("P-win", win, "base_high_p", cells), ("R1", r1, "pivot_full", ["A20_X4_P0", "A10_X3_P1"])):
        bad = 0; n = 0; not_stop = 0; unused = 0
        for cell in cell_list:
            ch = T[T.cell == cell].sort_values(["base", "attempt"])
            for b, g in ch.groupby("base"):
                g = g.reset_index(drop=True)
                lvl = np.float32(g[hi_col].iloc[0])
                for i in range(1, len(g)):
                    prev, cur = g.iloc[i - 1], g.iloc[i]
                    n += 1
                    if prev.status != 1:
                        not_stop += 1; bad += 1; continue
                    a = arr[cur.ticker]["c"].astype("float32"); x = int(prev.exit_idx)
                    win_ = a[x + 1: x + 21]
                    hit = np.where(np.isfinite(win_) & (win_ > lvl))[0]
                    exp_b = x + 1 + hit[0] if hit.size else -1
                    if exp_b != int(cur.bday):
                        bad += 1
                last = g.iloc[-1]
                if last.status == 1 and last.attempt < 2:
                    a = arr[last.ticker]["c"].astype("float32"); x = int(last.exit_idx)
                    win_ = a[x + 1: x + 21]
                    if (np.isfinite(win_) & (win_ > lvl)).any():
                        unused += 1
        log(f"  (b) retry rule, {name} ({len(cell_list)} cells): {n} retries checked, {bad} not the first close above the base high within 20 sessions of a STOP exit ({not_stop} followed a non-stop exit); stopped chains with an unused retry {unused}")
        ok_all &= bad == 0 and unused == 0
    # (c) P-win recount for two new cells (T2)
    for cell in ("A20_X3_P0", "A10_X4_P1"):
        d = win[(win.cell == cell) & (win.status >= 0)]
        nb = int(win[(win.cell == cell) & (win.attempt == 0)].base.nunique())
        inat = (d.e <= d.s50) & (d.exit_idx >= d.s50)
        still = int(inat.groupby(d.base).any().sum())
        kept = d.groupby("base").pnl_ps.sum() / (d.close_p - d.close_t).groupby(d.base).first()      # the episode gain PER SHARE (the table's `gain` is the fraction)
        held = (d.exit_idx - d.e).groupby(d.base).sum()
        G = J["grid"][cell]["win"]["T2"]
        log(f"  (c) P-win {cell} T2 recount from the trade table: bases {nb} (json {G['n']}); still in at s50 {still} (json {G['still_in_s50']}); kept ≥ ½ {int((kept >= 0.5).sum())} (json {G['kept_half']}); "
            f"kept ≥ ¼ {int((kept >= 0.25).sum())} (json {G['kept_quarter']}); median kept share {kept.median():.4f} (json {G['kept_share_q'][1]:.4f}); median sessions held {held.median():.1f} (json {G['held_chain_q'][1]:.1f})")
        ok_all &= (nb == G["n"] and still == G["still_in_s50"] and int((kept >= 0.5).sum()) == G["kept_half"] and int((kept >= 0.25).sum()) == G["kept_quarter"]
                   and abs(kept.median() - G["kept_share_q"][1]) < 1e-6 and abs(held.median() - G["held_chain_q"][1]) < 1e-9)
    # (g) the matched-control file vs the JSON
    MR = pd.read_parquet(f"{data}/out/trail_ctlmatch_{era}.parquet")
    worst = 0.0; nchk = 0
    for cell in cells:
        for es in ("R1", "R2"):
            for T in (0, 2):
                m = MR[(MR.cell == cell) & (MR.es == es) & (MR["T"] == T)]
                ref = J["grid"][cell][f"{es}_T{T}_complete"]["control"]
                worst = max(worst, abs(m.r_sum.mean() - ref["r_per_base"]), abs(100 * m.any5.mean() - ref["any5_per100"])); nchk += 2
                assert len(m) == J["grid"][cell][f"{es}_T{T}_complete"]["entries"]["n"]
    log(f"  (g) trail_ctlmatch per-cell means vs the JSON's control per-base R and ≥ 5R per 100 bases: {nchk} numbers over {len(cells)} cells × R1/R2 × T0/T2, max |diff| {worst:.1e}; row counts equal the entries' n")
    ok_all &= worst < 1e-9
log(f"CHECKS {'PASS' if ok_all else 'FAIL'}")
open(f"{HERE}/04_checks.txt", "w").write("\n".join(lines) + "\n")
sys.exit(0 if ok_all else 1)
