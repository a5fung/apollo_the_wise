"""#705 entry/stop/retry — step 4: own-code checks of the chain tables (no esr_lib walker import): a naive per-trade Python `pp` walk on random
R1 and control-sample trades, the retry rule re-derived from raw closes, the P-win still-in-at-s50 flag recounted, the race recounted, the
matched cell mean recomputed by a merge for one cell, and the nopen fill = the next open. Writes 04_checks.txt."""
import json, sys
import numpy as np, pandas as pd

HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_entry_stop_retry_1022"
DATA = {"2017-21": ("/Users/alvinfung/apollo_data/cb702_pre", None), "2022-24": ("/Users/alvinfung/apollo_data/cb702", "2024-12-31")}
lines = []


def log(s):
    print(s, flush=True); lines.append(s)


def naive_pp(o, h, l, c, sma, fill, stop0, start_j, horizon=120, reached0=False):
    """a plain per-trade walk of the §D exit; o/h/l/c/sma are the ticker's arrays from the entry day (index 0 = session 0)"""
    risk = fill - stop0; target = fill + 2 * risk; cut = fill + risk
    stop = stop0; third = False; rem = 1.0; pnl = 0.0; reached = reached0
    n = len(c)
    for j in range(start_j, horizon + 1):
        if j >= n:
            last = c[~np.isnan(c)][-1]
            return pnl + (last - fill) * rem, "degraded", j - 1
        oj, hj, lj, cj = o[j], h[j], l[j], c[j]
        if np.isnan(cj):
            if j == horizon:
                last = c[:j + 1][~np.isnan(c[:j + 1])][-1]
                return pnl + (last - fill) * rem, "censored", j
            continue
        gap = (not third) and oj >= target
        if oj <= stop or lj <= stop:
            if gap:
                pnl += (oj - fill) / 3; rem -= 1 / 3
            px = oj if oj <= stop else stop
            return pnl + (px - fill) * rem, "stopped", j
        new_stop = stop
        if gap or ((not third) and hj >= target):
            px = oj if gap else target
            pnl += (px - fill) / 3; rem -= 1 / 3; third = True; new_stop = max(stop, fill)
        if j <= 3 and hj >= cut:
            reached = True
        if j == 3 and not reached:
            return pnl + (cj - fill) * rem, "time_exit", j
        if j == 3 and not third and cj > fill:
            pnl += (cj - fill) / 3; rem -= 1 / 3; third = True; new_stop = max(new_stop, fill)
        if (third or j >= 3) and np.isfinite(sma[j]) and cj < sma[j]:
            if j + 1 < n and np.isfinite(o[j + 1]):
                return pnl + (o[j + 1] - fill) * rem, ("censored" if j == horizon else "trailed"), j + 1
            return pnl + (cj - fill) * rem, "degraded", j
        if j == horizon:
            return pnl + (cj - fill) * rem, "censored", j
        stop = new_stop
    raise RuntimeError


CODE = {"stopped": 1, "time_exit": 2, "trailed": 3, "censored": 4, "degraded": 5}
rng = np.random.default_rng(11)
for era, (data, cut) in DATA.items():
    log(f"== {era}")
    ex = pd.read_csv(f"{data}/daily_closes_all.csv.gz", header=None, names=["ticker", "date", "o", "h", "l", "c", "v"], dtype={"ticker": str, "date": str}, keep_default_na=False)
    if cut:
        ex = ex[ex.date <= cut]; assert ex.date.max() <= cut
    cal = pd.Index(ex[ex.ticker == "SPY"].date.sort_values().values); cidx = {d: i for i, d in enumerate(cal)}
    ex = ex[ex.date.isin(cal)]
    r1 = pd.read_csv(f"{data}/out/esr_r1_{era}.tsv.gz", sep="\t", low_memory=False)
    sm = pd.read_csv(f"{data}/out/esr_ctlsample_{era}.tsv.gz", sep="\t", low_memory=False)
    win = pd.read_csv(f"{data}/out/esr_win_{era}.tsv.gz", sep="\t", low_memory=False)
    need = set(r1.ticker) | set(sm.ticker) | set(win.ticker)
    ex = ex[ex.ticker.isin(need)]
    arr = {}
    for tk, d in ex.groupby("ticker"):
        full = pd.DataFrame(index=cal).join(d.set_index("date")[["o", "h", "l", "c"]]).astype("float32")
        full["sma"] = full.c.rolling(20, min_periods=20).mean().astype("float32")
        arr[tk] = {k: full[k].to_numpy().astype("float64") for k in ("o", "h", "l", "c", "sma")}
    # (a) naive re-walk of 400 random valid trades per table (all stops / variants / attempts)
    for name, T in (("R1", r1), ("control sample", sm), ("P-win", win)):
        v = T[T.status >= 0]
        pick = v.sample(min(400, len(v)), random_state=int(rng.integers(1e9)))
        bad = 0; ties = 0; maxd = 0.0
        for r in pick.itertuples():
            a = arr[r.ticker]; e = int(r.e); start_j = 1 if r.variant == "close" else 0
            seg = {k: a[k][e:] for k in a}
            fill, stop0 = float(np.float32(r.fill)), float(np.float32(r.stop0))        # the table's 7-digit text of float32 prices, back to float32
            pnl, st, xj = naive_pp(seg["o"], seg["h"], seg["l"], seg["c"], seg["sma"], fill, stop0, start_j)
            R = pnl / (fill - stop0)
            d = abs(R - r.realized_r); maxd = max(maxd, d)
            if d > 1e-3 or CODE[st] != r.status or xj != r.exit_j:
                # a knife edge: a high / open within 1e-6 of the +2R target or of +1R, or a low / open within 1e-6 of the stop, inside the walked window
                tgt = fill + 2 * (fill - stop0); cut = fill + (fill - stop0); w = slice(start_j, max(xj, r.exit_j) + 2)
                near = lambda x, lvl: np.nanmin(np.abs(x[w] - lvl)) / lvl < 2e-6
                tie = near(seg["h"], tgt) or near(seg["o"], tgt) or near(seg["l"], stop0) or near(seg["o"], stop0) or near(seg["h"], cut) or near(seg["l"], fill) or near(seg["o"], fill)
                if tie:
                    ties += 1
                else:
                    bad += 1
                    if bad <= 3:
                        log(f"    MISMATCH {name} {r.ticker} e={e} {r.kind}/{r.variant} att {r.attempt}: mine R {R:+.4f} {st} exit {xj} vs table {r.realized_r:+.4f} status {r.status} exit {r.exit_j}")
            elif d > 1e-4:
                ties += 0   # rounding of the 7-digit text only
        log(f"  (a) naive pp re-walk, {name}: {len(pick)} random trades, mismatches beyond text rounding and not a float32 knife edge {bad}; knife-edge ties (a bar exactly at the target / stop / fill at float32 precision) {ties}; max |ΔR| {maxd:.1e}")
    # (b) the retry rule: every attempt >= 1 row's entry day is the FIRST close above the base high within 20 sessions after a STOP exit
    for name, T, hi_col in (("R1", r1, "pivot_full"), ("P-win", win, "base_high_p")):
        ch = T.sort_values(["kind", "variant", "base", "attempt"])
        bad = 0; n = 0; nfalse = 0
        for (k, var, b), g in ch.groupby(["kind", "variant", "base"]):
            g = g.reset_index(drop=True)
            lvl = np.float32(g[hi_col].iloc[0]) if hi_col in g else None
            for i in range(1, len(g)):
                prev, cur = g.iloc[i - 1], g.iloc[i]
                n += 1
                if prev.status != 1:
                    bad += 1; continue
                a = arr[cur.ticker]["c"].astype("float32"); x = int(prev.exit_idx)
                win_ = a[x + 1: x + 21]
                hit = np.where(np.isfinite(win_) & (win_ > lvl))[0]
                exp_b = x + 1 + hit[0] if hit.size else -1
                if exp_b != int(cur.bday):
                    bad += 1
            # a stopped last attempt (< 2) with NO retry must have no close above the level in its window
            lastrow = g.iloc[-1]
            if lastrow.status == 1 and lastrow.attempt < 2:
                a = arr[lastrow.ticker]["c"].astype("float32"); x = int(lastrow.exit_idx)
                win_ = a[x + 1: x + 21]
                if (np.isfinite(win_) & (win_ > lvl)).any():
                    # a retry existed but was skipped only if its entry was impossible (status -1 row would be present)
                    nfalse += 1
        log(f"  (b) retry rule, {name}: {n} retries checked, {bad} not the first close above the base high within 20 sessions of a stop; stopped chains with an unused retry (none expected) {nfalse}")
    # (c) P-win still-in-at-s50 recount for S1 close T2 and S2 close T0
    for k, T in (("S1", 2), ("S2", 0)):
        g = win[(win.kind == k) & (win.variant == "close") & (win.attempt <= T) & (win.status >= 0)]
        still = ((g.e <= g.s50) & (g.exit_idx >= g.s50)).groupby(g.base).any()
        kept = g.groupby("base").pnl_ps.sum() / (g.groupby("base").close_p.first() - g.groupby("base").close_t.first())
        J = json.load(open(f"{HERE}/02_numbers_{era}.json"))["grid"][f"{k}_close"]["win"][f"T{T}"]
        log(f"  (c) P-win {k} close T{T}: still in at s50 {int(still.sum())} (report {J['still_in_s50']}); kept ≥ half {int((kept >= 0.5).sum())} (report {J['kept_half']}); kept ≥ quarter {int((kept >= 0.25).sum())} (report {J['kept_quarter']})")
    # (d) the race, naive, on 300 random first trades of R1 (S2 close)
    g = r1[(r1.kind == "S2") & (r1.variant == "close") & (r1.attempt == 0) & (r1.status >= 0) & (r1.race_complete == 1)].sample(300, random_state=3)
    bad = 0
    for r in g.itertuples():
        a = arr[r.ticker]; e = int(r.e); fill, stop = float(r.fill), float(r.stop0); R = fill - stop
        hs = a["h"][e + 1: e + 61]; ls = a["l"][e + 1: e + 61]
        fs = np.where(ls <= stop)[0]; fs = fs[0] if fs.size else 999
        for k in (2, 5, 10):
            fh = np.where(hs >= fill + k * R)[0]; fh = fh[0] if fh.size else 999
            hit = int(fh < fs and fh != 999)
            if hit != int(getattr(r, f"race{k}_hit")):
                bad += 1
    log(f"  (d) race on 300 random R1 S2 first trades, 3 thresholds each: mismatches {bad}")
    # (e) nopen fill = next open; close fill = the day's close
    g = r1[(r1.variant == "nopen") & (r1.attempt == 0) & (r1.status >= 0)].sample(200, random_state=5)
    bad = sum(abs(arr[r.ticker]["o"][int(r.e)] - r.fill) > 1e-3 * r.fill or int(r.e) != int(r.bday) + 1 for r in g.itertuples())
    g2 = r1[(r1.variant == "close") & (r1.attempt == 0) & (r1.status >= 0)].sample(200, random_state=5)
    bad2 = sum(abs(arr[r.ticker]["c"][int(r.e)] - r.fill) > 1e-3 * r.fill or int(r.e) != int(r.bday) for r in g2.itertuples())
    log(f"  (e) nopen fill = the next session's open: {200 - bad} of 200; close fill = the breakout close: {200 - bad2} of 200")
    # (f) the matched cell mean, recomputed by a merge for S2 close T0, R1 complete — per-base R
    J = json.load(open(f"{HERE}/02_numbers_{era}.json"))
    cuts = J["ctl"]["cells"]["R1"]
    ct = pd.read_parquet(f"{data}/out/esr_ctl_{era}.parquet", filters=[("kind", "==", "S2"), ("variant", "==", "close"), ("T", "==", 0)])
    ct = ct[ct.f_valid == 1]
    bdef = pd.read_csv(f"{data}/out/bdef_control_{era}.tsv.gz", sep="\t", usecols=["t", "ticker", "adr20", "ret63"])
    ct["t"] = cal.to_numpy()[ct.ci.to_numpy()]
    ct = ct.merge(bdef, on=["t", "ticker"], how="left")
    assert ct.adr20.notna().all()
    ct["dec"] = np.searchsorted(cuts["adr_cuts"], ct.adr20); ct["quin"] = np.searchsorted(cuts["ret_cuts"], ct.ret63)
    e = r1[(r1.kind == "S2") & (r1.variant == "close") & (r1.attempt == 0) & (r1.status >= 0) & (r1.complete120 == 1)].copy()
    e["dec"] = np.searchsorted(cuts["adr_cuts"], e.adr_t1); e["quin"] = np.searchsorted(cuts["ret_cuts"], e.ret63_t1)
    m3 = ct.groupby(["ci", "dec", "quin"]).r_sum.mean().rename("m3"); m2 = ct.groupby(["ci", "dec"]).r_sum.mean().rename("m2"); m1 = ct.groupby("ci").r_sum.mean().rename("m1")
    e = e.rename(columns={"t": "ci"}).merge(m3, left_on=["ci", "dec", "quin"], right_index=True, how="left").merge(m2, left_on=["ci", "dec"], right_index=True, how="left").merge(m1, left_on="ci", right_index=True, how="left")
    mv = e.m3.fillna(e.m2).fillna(e.m1)
    rep = J["grid"]["S2_close"]["R1_T0_complete"]
    log(f"  (f) S2 close T0 R1 complete, matched control mean R per base by merge: {mv.mean():+.4f} (report {rep['control']['r_per_base']:+.4f}); entries {e.realized_r.mean():+.4f} (report {rep['entries']['r_per_base']:+.4f}); n {len(e)} (report {rep['entries']['n']}); fell back to decile {int(e.m3.isna().sum())} (report {rep['fallback']['to_decile']})")
open(f"{HERE}/04_checks.txt", "w").write("\n".join(lines) + "\n")
