#!/usr/bin/env python3
"""#705 big-winner recall, step 2: what WE did on every episode — watched / which gate / triggered / kept — from the PUBLISHED
backtest tables (never re-run) and the module's own `explain_watch` for the gate attribution. Definitions: the doc's §D (frozen).

Per era and factor writes DATA/out/wrecall_catch_<era>_x<200|150>.tsv.gz (the episode table + the catch columns) and
DATA/out/wrecall_nights_<era>_x<200|150>.tsv.gz (one row per (episode, base night): in the watch table?, my rebuilt gate), and
HERE/02_catch_<era>.txt (the log + validation counts), HERE/02_reverse_<era>.txt (the reverse view).
HARD SCOPE: the 2022-24 export, watch, entry and trade tables are cut at 2024-12-31 at load (asserted); no *_holdout* file is opened;
nothing under DATA is modified; the runner is never imported."""
from __future__ import annotations
import re, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from agents.market_intelligence import consolidation_breakout as cb   # noqa: E402  (the frozen module; explain_watch only)
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("ep01", "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_winner_recall_1022/01_episodes.py")
ep01 = _ilu.module_from_spec(_spec); _spec.loader.exec_module(ep01)          # raw_close_wide / load_sectypes / ERAS (same universe as step 1)

HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_winner_recall_1022"
ERAS = {
    "2017-21": dict(data="/Users/alvinfung/apollo_data/cb702_pre", cut=None, watch=["out/watch_tl_com.tsv.gz"], wstart="2017-03-01", wend="2021-12-31",
                    trades="out/trades_pre_exitpb.tsv.gz", entries=["out/entries_pre_tl_com.tsv.gz"]),
    "2022-24": dict(data="/Users/alvinfung/apollo_data/cb702", cut="2024-12-31", watch=["out/watch.tsv.gz", "out/watch_com.tsv.gz"], wstart="2022-03-31", wend="2024-12-31",
                    trades="out/trades_discovery_exitpb.tsv.gz", entries=["out/entries_discovery.tsv.gz", "out/entries_discovery_com_comb.tsv.gz"]),
}
MIN_PRICE, MIN_DV, HIST = 5.0, 10_000_000.0, 130
PRE_WIN = 20                 # the window before the trough for episodes without a measurable breakout
NEAR = 5
REV_MARGIN = 83              # a fill is judgeable when E + 83 sessions <= the last session (trough <= E+20, qualifying window 63)
GATE_ORDER = ["universe_sectype", "universe_price", "universe_dv", "universe_history"] + list(cb.WATCH_GATES) + ["pass"]
log_lines: list[str] = []


def log(s):
    print(s, flush=True); log_lines.append(s)


def load_export(path, cut):
    df = pd.read_csv(path, header=None, names=["ticker", "date", "o", "h", "l", "c", "v"],
                     dtype={"ticker": str, "date": str, "o": "float32", "h": "float32", "l": "float32", "c": "float32", "v": "float64"}, keep_default_na=False)
    if cut:
        df = df[df.date <= cut]; assert df.date.max() <= cut
    return df


def wide(df, col, cal, tickers):
    return df.pivot(index="date", columns="ticker", values=col).reindex(index=cal, columns=tickers).astype("float32")


class Gates:
    """my rebuilt funnel for one night: the universe first, then the module's explain_watch on the ticker's own contiguous bars"""

    def __init__(self, cal, tickers, O, H, L, C, V, DV, HISTok, sectype_of, RAW):
        self.cal, self.tickers = cal, tickers
        self.O, self.H, self.L, self.C, self.V, self.DV, self.HISTok, self.sectype_of, self.RAW = O, H, L, C, V, DV, HISTok, sectype_of, RAW
        self.tpos = {tk: k for k, tk in enumerate(tickers)}
        self._bars = {}

    def bars(self, tk):
        if tk not in self._bars:
            j = self.tpos[tk]
            ok = np.isfinite(self.C[:, j]) & np.isfinite(self.O[:, j]) & np.isfinite(self.H[:, j]) & np.isfinite(self.L[:, j]) & np.isfinite(self.V[:, j])
            idx = np.where(ok)[0]
            dates = [pd.Timestamp(self.cal[i]).date() for i in idx]
            b = cb.daily_bars_from_arrays(dates, self.O[idx, j].astype(float), self.H[idx, j].astype(float), self.L[idx, j].astype(float), self.C[idx, j].astype(float), self.V[idx, j].astype(float))
            self._bars[tk] = (b, {int(i): r for r, i in enumerate(idx)})
        return self._bars[tk]

    def first_gate(self, tk, ci) -> str:
        j = self.tpos[tk]
        st = self.sectype_of(tk)
        if (st and st not in ("CS", "ADRC")) or cb.is_test_symbol(tk):
            return "universe_sectype"
        if not (np.isfinite(self.RAW[ci, j]) and self.RAW[ci, j] >= MIN_PRICE):
            return "universe_price"
        if not (np.isfinite(self.DV[ci, j]) and self.DV[ci, j] >= MIN_DV):
            return "universe_dv"
        if not self.HISTok[ci, j]:
            return "universe_history"
        b, rowmap = self.bars(tk)
        if ci not in rowmap:
            return "universe_history"
        feats, gate = cb.explain_watch(b, rowmap[ci])
        return "pass" if feats is not None else gate


def run(era, cfg):
    data = cfg["data"]; cut = cfg["cut"]
    t0 = time.time()
    ex = load_export(f"{data}/daily_closes_all.csv.gz", cut)
    cal = pd.Index(ex[ex.ticker == "SPY"].date.sort_values().values)
    ex = ex[ex.date.isin(cal)]
    tickers = pd.Index(sorted(ex.ticker.unique()))
    Ow, Hw, Lw, Cw, Vw = (wide(ex, c, cal, tickers) for c in ("o", "h", "l", "c", "v"))
    del ex
    DV = (Cw * Vw).rolling(20, min_periods=20).median().to_numpy()
    HISTok = (Cw.notna().astype("float32").rolling(HIST, min_periods=HIST).sum() == HIST).to_numpy()
    O, H, L, C, V = (x.to_numpy() for x in (Ow, Hw, Lw, Cw, Vw))
    last = len(cal) - 1; cidx = {d: i for i, d in enumerate(cal)}
    sectype_of = ep01.load_sectypes(data)
    RAW = ep01.raw_close_wide(data, ep01.ERAS[era], Cw, cal, tickers, log)
    G = Gates(cal, tickers, O, H, L, C, V, DV, HISTok, sectype_of, RAW)
    log(f"  export loaded: {len(cal)} sessions {cal[0]}..{cal[-1]}; {time.time()-t0:.0f}s")

    # ── the watch tables (cut) ───────────────────────────────────────────────────────────────────
    wrows = {}
    for wf in cfg["watch"]:
        cols = ["ticker", "watch_date"] + [c for c in ("C0_tl", "C0_com") if c in pd.read_csv(f"{data}/{wf}", sep="\t", nrows=0).columns]
        w = pd.read_csv(f"{data}/{wf}", sep="\t", usecols=cols)
        n0 = len(w)
        if cut:
            w = w[w.watch_date <= cut]; assert w.watch_date.max() <= cut
        log(f"  watch {wf}: {n0:,} rows, kept {len(w):,} (cut {cut}); nights {w.watch_date.min()}..{w.watch_date.max()}; cols {cols[2:]}")
        for r in w.itertuples(index=False):
            key = (r.ticker, cidx.get(r.watch_date, -1))
            d = wrows.setdefault(key, {"tl": 0, "com": 0})
            if "C0_tl" in cols: d["tl"] = max(d["tl"], int(r.C0_tl))
            if "C0_com" in cols: d["com"] = max(d["com"], int(r.C0_com))
    ws_i, we_i = cidx[cfg["wstart"]], cidx[cfg["wend"]]
    log(f"  watch coverage idx {ws_i}..{we_i} ({cfg['wstart']}..{cfg['wend']}); {len(wrows):,} (ticker, night) keys")

    # ── the published trades (pp / orh5 / tl / C0), retriggers and non-mature included ───────────
    t = pd.read_csv(f"{data}/{cfg['trades']}", sep="\t", low_memory=False)
    t = t[(t.arm == "pp") & (t.entry == "orh5") & (t.K == "tl") & (t.C0 == 1)].copy()
    n0 = len(t)
    if cut:
        t = t[t.E <= cut]
    t["ci"] = t.E.map(cidx)
    assert t.ci.notna().all()
    t["ci"] = t.ci.astype(int)
    log(f"  trades pp/orh5/tl/C0: {n0} rows, kept {len(t)} (E <= cut); mature {int(t.mature.sum())}; retrigger rows {int((t.retrigger_chain > 0).sum())}; E {t.E.min()}..{t.E.max()}")
    trades_by = {tk: g.sort_values("ci") for tk, g in t.groupby("ticker")}
    # the entry tables: ORH5 filled C0 rows per K
    ent = []
    for ef in cfg["entries"]:
        e = pd.read_csv(f"{data}/{ef}", sep="\t", usecols=["ticker", "D", "E", "K", "variant", "status", "C0", "fill", "stop", "retrigger"], low_memory=False)
        e = e[(e.variant == "orh5") & (e.status == "filled") & (e.C0 == 1)]
        if cut:
            e = e[e.E <= cut]
        ent.append(e)
    ent = pd.concat(ent, ignore_index=True)
    ent["ci"] = ent.E.map(cidx).astype(int)
    Ks = sorted(ent.K.unique())
    log(f"  entry tables ORH5 filled C0 (E <= cut): {len(ent)} rows; per K {ent.groupby('K').size().to_dict()}")
    ent_by = {(tk, K): g.sort_values("ci") for (tk, K), g in ent.groupby(["ticker", "K"])}

    for tag in ("x200", "x150"):
        t1 = time.time()
        ep = pd.read_csv(f"{data}/out/wrecall_episodes_{era}_{tag}.tsv.gz", sep="\t", keep_default_na=False, na_values=[""])
        ep = ep[ep.excluded == 0].reset_index(drop=True)
        out_rows = []; night_rows = []
        val = dict(in_table_pass=0, in_table_fail=0, not_in_table_fail=0, not_in_table_pass=0)
        for r in ep.itertuples(index=False):
            tk = r.ticker; tt, pp_, s25, s50 = int(r.t), int(r.p), int(r.s25), int(r.s50)
            mb = r.class_p == "measurable_breakout"
            b = int(r.b_p) if mb else -1
            if mb:
                nights = list(range(b - int(r.L_p), b))           # the base nights [b-L, b-1]
                win = (b - int(r.L_p) + 1, s25)                     # the catch window for E
            else:
                nights = list(range(max(tt - PRE_WIN, 0), s25))
                win = (max(tt - PRE_WIN, 0), s25)
            covered = int(nights[0] >= ws_i and nights[-1] <= we_i)
            part_cov = int(any(ws_i <= d <= we_i for d in nights))
            row = dict(ticker=tk, t=tt, trough_date=r.trough_date, p=pp_, gain=r.gain, class_p=r.class_p, b=b, L=int(r.L_p) if mb else -1, s25=s25, s50=s50,
                       win_start=win[0], win_end=win[1], covered=covered, partly_covered=part_cov, n_nights=len(nights))
            # WATCHED
            hits = [(d, wrows[(tk, d)]) for d in nights if (tk, d) in wrows]
            row["watched"] = int(bool(hits)); row["n_watch_nights"] = len(hits)
            row["watched_tl"] = int(any(h["tl"] for _, h in hits)); row["watched_com"] = int(any(h["com"] for _, h in hits))
            row["watched_bprev"] = int(mb and (tk, b - 1) in wrows); row["watched_bprev_tl"] = int(mb and (tk, b - 1) in wrows and wrows[(tk, b - 1)]["tl"] == 1)
            row["first_watch_night_minus_b"] = (hits[0][0] - b) if (hits and mb) else np.nan
            # GATES — my rebuilt funnel on every base night (covered nights carry the validation against the table)
            furthest = -1; gate_bprev = ""; any_pass = 0
            for d in nights:
                if d > last: continue
                g = G.first_gate(tk, d)
                in_tab = int((tk, d) in wrows)
                if ws_i <= d <= we_i:
                    if in_tab and g == "pass": val["in_table_pass"] += 1
                    elif in_tab: val["in_table_fail"] += 1
                    elif g == "pass": val["not_in_table_pass"] += 1
                    else: val["not_in_table_fail"] += 1
                night_rows.append(dict(ticker=tk, t=tt, night=d, night_date=cal[d], in_watch_table=in_tab, my_gate=g, covered=int(ws_i <= d <= we_i)))
                furthest = max(furthest, GATE_ORDER.index(g)); any_pass |= int(g == "pass")
                if mb and d == b - 1: gate_bprev = g
            row["gate_bprev"] = gate_bprev; row["furthest_gate"] = GATE_ORDER[furthest] if furthest >= 0 else ""; row["any_night_passes_mine"] = any_pass
            # TRIGGERED (tl, published rows) — the first fill with E in the window
            g = trades_by.get(tk)
            fills = g[(g.ci >= win[0]) & (g.ci <= win[1])] if g is not None else None
            row["n_fills_win"] = 0 if fills is None else len(fills)
            row["triggered"] = int(fills is not None and len(fills) > 0)
            if row["triggered"]:
                f = fills.iloc[0]
                e_ci = int(f.ci)
                row.update(E=f.E, E_minus_b=(e_ci - b) if mb else np.nan, E_minus_t=e_ci - tt, near_b=int(mb and abs(e_ci - b) <= NEAR), fill=f.fill, stop=f.stop, adr20_D=f.adr20,
                           retrigger=int(f.retrigger_chain > 0), mature=int(f.mature), status=f.status, realized_r=f.realized_r, pnl_adr=f.pnl_adr, exit_session=int(f.exit_session) if pd.notna(f.exit_session) else -1,
                           sessions_held=f.sessions_held, exit_kind=f.exit_kind)
                row["gain_made_at_fill"] = (f.fill - r.close_t) / (r.close_p - r.close_t)
                u = f.adr20 * f.fill
                row["gain_adr"] = (r.close_p - r.close_t) / u; row["avail_adr"] = (r.close_p - f.fill) / u
                row["kept_share_episode"] = f.pnl_adr / row["gain_adr"]; row["kept_share_avail"] = f.pnl_adr / row["avail_adr"] if row["avail_adr"] > 0 else np.nan
                ex_ci = e_ci + row["exit_session"] if row["exit_session"] >= 0 else 10**6
                row["exit_ci"] = ex_ci
                row["still_in_b"] = int(mb and ex_ci >= b); row["still_in_s25"] = int(ex_ci >= s25); row["still_in_s50"] = int(ex_ci >= s50)
                stopped = f.status in ("stopped", "stopped_day0")
                row["stopped"] = int(stopped); row["stopped_before_s50"] = int(stopped and ex_ci < s50); row["stopped_before_b"] = int(mb and stopped and ex_ci < b)
                row["exited_before_s50_not_stop"] = int((not stopped) and ex_ci < s50)
                row["kept_half_episode"] = int(row["kept_share_episode"] >= 0.5); row["kept_half_avail"] = int(pd.notna(row["kept_share_avail"]) and row["kept_share_avail"] >= 0.5)
                row["any_fill_still_in_s50"] = int(any((int(x.ci) + (int(x.exit_session) if pd.notna(x.exit_session) else 10**6)) >= s50 for x in fills.itertuples()))
                row["best_fill_kept_share_episode"] = float((fills.pnl_adr / ((r.close_p - r.close_t) / (fills.adr20 * fills.fill))).max())
            # any-K view from the entry tables
            for K in Ks:
                gk = ent_by.get((tk, K))
                fk = gk[(gk.ci >= win[0]) & (gk.ci <= win[1])] if gk is not None else None
                row[f"trig_{K}"] = int(fk is not None and len(fk) > 0)
                row[f"E_minus_b_{K}"] = (int(fk.iloc[0].ci) - b) if (row[f"trig_{K}"] and mb) else np.nan
            row["trig_anyK"] = int(any(row[f"trig_{K}"] for K in Ks))
            # a tl fill ANYWHERE in [t-20, p] (the loosest reading of "did we trade this winner at all")
            row["any_fill_t20_to_p"] = int(g is not None and ((g.ci >= max(tt - PRE_WIN, 0)) & (g.ci <= pp_)).any())
            out_rows.append(row)
        out = pd.DataFrame(out_rows)
        out.to_csv(f"{data}/out/wrecall_catch_{era}_{tag}.tsv.gz", sep="\t", index=False, float_format="%.7g")
        pd.DataFrame(night_rows).to_csv(f"{data}/out/wrecall_nights_{era}_{tag}.tsv.gz", sep="\t", index=False)
        log(f"  [{tag}] {len(out)} episodes; covered {int(out.covered.sum())}; watched {int(out.watched.sum())}; triggered {int(out.triggered.sum())}; "
            f"validation on covered nights {val} (in_table_fail + not_in_table_pass should be ~0); {time.time()-t1:.0f}s")

    # ── the reverse view: of our fills, how many sit inside a big-winner episode's catch window ─────
    rev = []
    for tag in ("x200", "x150"):
        c = pd.read_csv(f"{data}/out/wrecall_catch_{era}_{tag}.tsv.gz", sep="\t", usecols=["ticker", "win_start", "win_end", "t", "p"])
        wins = {}
        for r in c.itertuples(index=False):
            wins.setdefault(r.ticker, []).append((int(r.win_start), int(r.win_end), int(r.t), int(r.p)))
        judge = t[(t.ci >= ws_i + 1) & (t.ci <= min(we_i + 1, last - REV_MARGIN))]
        n_unj = len(t[(t.ci >= ws_i + 1) & (t.ci <= we_i + 1)]) - len(judge)
        inwin = judge.apply(lambda f: int(any(a <= f.ci <= b_ for a, b_, _, _ in wins.get(f.ticker, []))), axis=1)
        inrun = judge.apply(lambda f: int(any(tt - PRE_WIN <= f.ci <= pp_ for _, _, tt, pp_ in wins.get(f.ticker, []))), axis=1)
        line = (f"  [{tag}] reverse view: {len(judge)} judgeable fills (E in the watch window and E <= last session - {REV_MARGIN}; {n_unj} later fills unjudgeable): "
                f"in a big-winner catch window {int(inwin.sum())} ({100*inwin.mean():.1f}%); anywhere in [trough-20, peak] of a big winner {int(inrun.sum())} ({100*inrun.mean():.1f}%)")
        log(line); rev.append(line)
    with open(f"{HERE}/02_reverse_{era}.txt", "w") as fh:
        fh.write("\n".join(rev) + "\n")


if __name__ == "__main__":
    eras = sys.argv[1:] or list(ERAS)
    for era in eras:
        log(f"== {era}")
        run(era, ERAS[era])
        with open(f"{HERE}/02_catch_{era}.txt", "w") as fh:
            fh.write("\n".join(log_lines) + "\n")
        log_lines.clear()
