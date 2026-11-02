#!/usr/bin/env python3
"""Big winners vs breakout v1, step 2 (2026-11-01): for EVERY big winner (both factors, both eras) and EVERY scan night D in its
window t <= D <= s50 (plus its anchor night, PLAN.md §4), rebuild the night exactly as the replay's population stage does — the
replay's own `load_store` / `ticker_facts` / `night_members` / `cb.cross_section_one_date` (IMPORTED, not re-implemented) — and
call the LIVE `breakout_v1.v1_gates` on the ticker's historical bars with that night's rs_best. Records the pool status, rs_best,
the FULL gate vector (every gate evaluated, no short-circuit), the gate values, the next session's daily-bar trigger facts, and
whether the replay's list file holds the name that night (the parity check, PLAN.md §3).

Writes  out/v1_nights.tsv.gz   one row per (ticker, scan night) over the union of the winners' windows (a night is evaluated once
                               even when two episodes of the same ticker cover it)
        out/qqq_nights.tsv     per scan night: QQQ close vs its 50-day SMA, and the replay's 10/20 phase
        02_run.log
No network, no DB, nothing written outside this folder and the study's scratch; the cb702 store is the SEALED copy (00_seal.py)."""
import os, sys, time, gzip, json
from collections import Counter
from datetime import date
import numpy as np, pandas as pd

HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_v1_replay_1101/big_winners_1101"
SCRATCH = "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/Cfollow/big_winners"
os.environ["BV1_SCRATCH"] = SCRATCH
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_v1_replay_1101")
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
import v1_replay as R                                     # noqa: E402  (the replay's loaders / pool; its __main__ is guarded)
from agents.market_intelligence import breakout_v1 as bv  # noqa: E402
from agents.market_intelligence import consolidation_breakout as cb  # noqa: E402
from scripts.probes._cb_backtest import runner  # noqa: E402

assert str(R.SCRATCH) == SCRATCH
LOG = []


def log(s):
    print(s, flush=True); LOG.append(s)


def iso(d):
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def load_episodes():
    eps = []
    for era in ("A", "B"):
        for tag in ("x200", "x150"):
            df = pd.read_csv(f"{HERE}/out/wrecall_episodes_{era}_{tag}.tsv.gz", sep="\t", dtype={"ticker": str}, keep_default_na=False)
            df = df[df.excluded == 0].copy()
            df["store"] = era; df["tag"] = tag
            eps.append(df)
    return pd.concat(eps, ignore_index=True)


def anchor_date(row, cal_by_store):
    """b-1 when a base breakout exists; gap_day-1 for an ep_gap without a base breakout; else s25-1. Returns (date iso, kind)."""
    cal = cal_by_store[row.store]
    if row.b_p >= 0:
        return cal[int(row.b_p) - 1], "b-1"
    if row.gap_day >= 0:
        return cal[int(row.gap_day) - 1], "gap-1"
    return cal[int(row.s25) - 1], "s25-1"


def main():
    t_all = time.time()
    eps = load_episodes()
    log(f"episodes (kept): {len(eps)} rows; by store x tag {eps.groupby(['store', 'tag']).size().to_dict()}")
    # the replay's list files (the parity target) and the night tables
    lst = pd.concat([pd.read_csv(f"{R.OUT}/list_era{e}.tsv.gz", sep="\t", dtype={"ticker": str}) for e in ("A", "B")], ignore_index=True)
    in_list = {(t, d): int(r) for t, d, r in zip(lst.ticker, lst.scan_date, lst.list_rank)}
    log(f"list rows {len(lst)} on {lst.scan_date.nunique()} nights")
    stores = {e: R.load_store(e) for e in ("A", "B")}
    cal_by_store = {e: [iso(d) for d in stores[e].D.cal] for e in stores}
    # per-store calendars as iso lists; the episode indices (t, s25, s50, b_p, gap_day) index the SAME SPY calendar as the store
    # (01_episodes.py built its calendar from the same file's SPY rows) — asserted on a sample
    for e in stores:
        sub = eps[eps.store == e].head(50)
        for r in sub.itertuples():
            assert cal_by_store[e][int(r.t)] == r.trough_date, (e, r.ticker, r.trough_date, cal_by_store[e][int(r.t)])
    # the needed (ticker, night iso) set per store: t <= D <= s50 plus the anchor night
    need = {"A": {}, "B": {}}          # store -> {night iso: set(tickers)}
    anchors = []
    A_LAST, B_FIRST = R.ERA_A_D_LAST.isoformat(), R.ERA_B_D_FIRST.isoformat()
    def store_of(night):
        return "A" if night <= A_LAST else "B"
    n_pairs = 0
    for r in eps.itertuples():
        cal = cal_by_store[r.store]
        nights = cal[int(r.t): int(r.s50) + 1]
        a_iso, a_kind = anchor_date(r, cal_by_store)
        anchors.append(a_iso)
        for d in list(nights) + [a_iso]:
            if d > "2024-12-30":                      # the last scan night whose E <= 2024-12-31
                continue
            st = store_of(d)
            need[st].setdefault(d, set()).add(r.ticker)
    eps["anchor_date"] = anchors
    for st in need:
        n_pairs += sum(len(v) for v in need[st].values())
    log(f"(ticker, night) pairs to evaluate: {n_pairs} over {sum(len(v) for v in need.values())} nights (A {len(need['A'])}, B {len(need['B'])})")
    eps.to_csv(f"{HERE}/out/episodes_all.tsv.gz", sep="\t", index=False, float_format="%.7g")

    rows, qqq_rows = [], []
    for st in ("A", "B"):
        S = stores[st]; D = S.D; cal = D.cal
        cal_iso = cal_by_store[st]
        pos = {d: i for i, d in enumerate(cal_iso)}
        t0 = time.time()
        facts = [R.ticker_facts(S, k) for k in range(len(D.tickers))]
        log(f"store {st}: facts for {len(facts)} tickers in {time.time() - t0:.0f}s")
        row_tid = np.repeat(np.arange(len(D.tickers), dtype=np.int64), (D.stop - D.start).astype(np.int64))
        order = np.argsort(D.ci, kind="stable")
        rows_at = R._RowsAt(order, D.ci[order], row_tid)
        bars_cache = {}
        qqq, qcidx = runner.bars_for(D, D.tid["QQQ"])
        qpos = {iso(d): j for j, d in enumerate(qqq.dates)}
        # the replay's night set for this store
        d_lo = (R.E_FIRST.toordinal() - 10) if st == "A" else R.ERA_B_D_FIRST.toordinal()
        d_hi = R.ERA_A_D_LAST if st == "A" else R.E_LAST
        nights = sorted(need[st])
        t0 = time.time(); n_calls = 0; par = Counter()
        for n_i, d_iso in enumerate(nights):
            ci = pos.get(d_iso)
            if ci is None or ci + 1 >= len(cal) or cal[ci] > d_hi or cal[ci].toordinal() < d_lo:
                for t in need[st][d_iso]:
                    rows.append({"store": st, "scan_date": d_iso, "ticker": t, "night_in_replay": 0})
                continue
            e_iso = cal_iso[ci + 1]
            # QQQ at D: close vs SMA50, and the replay's 10/20 phase
            qj = qpos.get(d_iso)
            if qj is not None:
                s50 = cb._sma_at(qqq, qj, 50)
                qqq_rows.append({"scan_date": d_iso, "store": st, "qqq_close": float(qqq.c[qj]), "qqq_sma50": s50,
                                 "qqq_above_50d": int(s50 is not None and float(qqq.c[qj]) > s50),
                                 "qqq_phase_10_20": int(cb.phase_qqq_10_20(qqq, qj))})
            members, counts = R.night_members(S, facts, ci, rows_at)
            rs_best, _, _, _ = cb.cross_section_one_date([m["r21"] for m in members], [m["r63"] for m in members],
                                                         [m["r126"] for m in members], [None] * len(members))
            mem = {m["ticker"]: (m, rb) for m, rb in zip(members, rs_best)}
            rs_rank_n = len(members)
            for t in sorted(need[st][d_iso]):
                row = {"store": st, "scan_date": d_iso, "E": e_iso, "ticker": t, "night_in_replay": 1, "pool_n": rs_rank_n,
                       "in_list": int((t, d_iso) in in_list), "list_rank": in_list.get((t, d_iso), "")}
                k = D.tid.get(t)
                if k is None:
                    row.update(in_store=0, pool="not_in_store"); rows.append(row); continue
                row["in_store"] = 1
                f = facts[k]
                a, b = f["a"], f["b"]
                li_arr = np.where(f["cidx"] == ci)[0]
                if li_arr.size == 0:
                    row.update(has_bar=0, pool="no_bar"); rows.append(row); continue
                li = int(li_arr[0]); i = a + li
                row["has_bar"] = 1
                stype = S.types.get(t)
                adm, why = bv.security_admitted(t, stype, S.etv_names.get(t))
                row.update(security_type=stype or "", admitted=int(adm), admitted_reason=why)
                rb = None
                if t in mem:
                    m, rb = mem[t]
                    row["pool"] = "in_pool"
                    row.update(r21=m["r21"], r63=m["r63"], r126=m["r126"], listable=int(m["listable"]))
                else:
                    # replicate night_members' exclusion order for this one ticker
                    if why == "ticker":
                        row["pool"] = "excluded_ticker"
                    elif f["brk"][li]:
                        row["pool"] = "identity_break"
                    elif li + 1 < cb.DOLLAR_VOL_WINDOW:
                        row["pool"] = "short_history"
                    elif not (f["raw"][li] >= bv.MIN_PRICE and f["dv"][li] >= bv.MIN_DOLLAR_VOL):
                        row["pool"] = "below_floors"
                    elif np.isnan(f["r63"][li]):
                        row["pool"] = "no_r63"
                    else:
                        row["pool"] = "unexplained"
                    row["listable"] = int(adm)
                row["rs_best"] = rb
                row.update(raw_close=float(f["raw"][li]), dv20=float(f["dv"][li]) if np.isfinite(f["dv"][li]) else None)
                if k not in bars_cache:
                    bars_cache[k] = runner.bars_for(D, k)
                bars, cidx = bars_cache[k]
                try:
                    g = bv.v1_gates(bars, li, rs_best=rb, raw_close=float(f["raw"][li]), cidx=cidx)
                except Exception as ex:  # loud-ok: recorded per row
                    row.update(gate_error=f"{type(ex).__name__}: {ex}"); rows.append(row); continue
                n_calls += 1
                G = g["gates"]
                failed = list(g["failed"])
                row.update(ok=int(g["ok"]), would_list=int(g["ok"] and adm), failed=",".join(failed), n_failed=len(failed),
                           first_failed=failed[0] if failed else "")
                for name in bv.GATES:
                    row[f"pass_{name}"] = G[name]["pass"] if G[name]["pass"] is not None else ""
                if G["history"]["pass"]:
                    pv = G["prior_move"]["value"]; hv = G["higher_lows"]["value"]; sv = G["surf"]["value"]; tv = G["tightening"]["value"]; bvv = G["breakdown"]["value"]
                    row.update(prior_move=pv["prior_move"], pole_date=pv["pole_date"], pole_high=pv["pole_high"], pole_low=pv["pole_low"], base_len=pv["base_len"],
                               recent_low=hv["recent_low"], base_low=hv["base_low"], surf_run10=sv["run10"], surf_run20=sv["run20"], surf_run50=sv["run50"], surf_best=sv["best"],
                               tight_ratio=tv["ratio"], range_recent5=tv["range_recent5"], range_early5=tv["range_early5"],
                               sma10=bvv["sma10"], sma20=bvv["sma20"], sma50=bvv["sma50"], below_all_smas=int(bvv["below_all"]), new_low10=int(bvv["new_low"]),
                               adr20=g["adr20"], level=g["level"], vol_bar=g["vol_bar"], vol50=g.get("vol50"), close=g["close"])
                    # the next session on the ticker's own bars (must be the very next SPY session)
                    if li + 1 < len(cidx) and int(cidx[li + 1]) == ci + 1:
                        hE, vE, oE, cE, lE = float(bars.h[li + 1]), float(bars.v[li + 1]), float(bars.o[li + 1]), float(bars.c[li + 1]), float(bars.l[li + 1])
                        row.update(E_high=hE, E_vol=vE, E_open=oE, E_close=cE, E_low=lE,
                                   E_level_pass=int(hE > g["level"]), E_vol_pass=int(vE >= g["vol_bar"]),
                                   E_fired=int(hE > g["level"] and vE >= g["vol_bar"]),
                                   E_gap_pct=oE / g["close"] - 1.0, E_volx50=vE / g["vol50"] if g.get("vol50") else None,
                                   E_range_adr=((hE - lE) / cE / g["adr20"]) if (g["adr20"] and cE > 0) else None,
                                   E_close_loc=((cE - lE) / (hE - lE)) if hE > lE else None)
                    else:
                        row["E_bar"] = "missing"
                # parity against the replay's list file
                wl = int(bool(g["ok"]) and adm)
                par[("list" if row["in_list"] else "nolist", "pass" if wl else "fail")] += 1
                rows.append(row)
            if n_i % 200 == 0:
                log(f"  {st} night {n_i}/{len(nights)} {d_iso}: pool {rs_rank_n}, gate calls so far {n_calls} ({time.time() - t0:.0f}s)")
        log(f"store {st}: {len(nights)} nights, {n_calls} gate calls in {time.time() - t0:.0f}s; parity {dict(par)}")
    out = pd.DataFrame(rows)
    out.to_csv(f"{HERE}/out/v1_nights.tsv.gz", sep="\t", index=False, float_format="%.7g")
    pd.DataFrame(qqq_rows).drop_duplicates("scan_date").to_csv(f"{HERE}/out/qqq_nights.tsv", sep="\t", index=False, float_format="%.6g")
    log(f"wrote {len(out)} (ticker, night) rows; pool status {out.pool.value_counts(dropna=False).to_dict()}")
    if "would_list" in out:
        ok = out[out.would_list.notna()]
        a = int(((ok.would_list == 1) & (ok.in_list == 0)).sum()); b = int(((ok.would_list == 0) & (ok.in_list == 1)).sum())
        log(f"PARITY: my call passes but the list lacks the name: {a}; the list has it but my call fails: {b}; "
            f"agree pass {int(((ok.would_list == 1) & (ok.in_list == 1)).sum())}, agree fail {int(((ok.would_list == 0) & (ok.in_list == 0)).sum())}")
        if a or b:
            dis = ok[((ok.would_list == 1) & (ok.in_list == 0)) | ((ok.would_list == 0) & (ok.in_list == 1))]
            dis.to_csv(f"{HERE}/out/parity_disagreements.tsv", sep="\t", index=False)
            log("  disagreements -> out/parity_disagreements.tsv; " + dis[["store", "scan_date", "ticker", "pool", "rs_best", "failed", "in_list"]].head(12).to_string())
    log(f"done in {time.time() - t_all:.0f}s")
    open(f"{HERE}/02_run.log", "w").write("\n".join(LOG) + "\n")


if __name__ == "__main__":
    main()
