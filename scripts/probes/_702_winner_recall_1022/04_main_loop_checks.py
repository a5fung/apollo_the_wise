#!/usr/bin/env python3
"""#705 big-winner recall, step 4: main-loop adversarial checks, own code (no import of 01/02): (a) recount the x200 funnel by a pandas
merge of the published trades onto the episode windows; (b) recompute base / breakout day / s50 from the raw export for 6 named
episodes and print what the backtest did on them; (c) the triggered-but-not-watched-on-a-base-night rows must all be late fills (E > b);
(d) list every catch that kept >= half, and every still-in-at-s50 catch. Writes HERE/04_main_loop_checks.txt."""
import numpy as np, pandas as pd

HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_winner_recall_1022"
DATA = {"2017-21": ("/Users/alvinfung/apollo_data/cb702_pre", "out/trades_pre_exitpb.tsv.gz", None), "2022-24": ("/Users/alvinfung/apollo_data/cb702", "out/trades_discovery_exitpb.tsv.gz", "2024-12-31")}
out = []


def p(s=""):
    print(s); out.append(s)


for era, (d, tf, cut) in DATA.items():
    p(f"== {era}")
    c = pd.read_csv(f"{d}/out/wrecall_catch_{era}_x200.tsv.gz", sep="\t", keep_default_na=False, na_values=[""])
    e = pd.read_csv(f"{d}/out/wrecall_episodes_{era}_x200.tsv.gz", sep="\t", keep_default_na=False, na_values=[""]); e = e[e.excluded == 0].reset_index(drop=True)
    ex = pd.read_csv(f"{d}/daily_closes_all.csv.gz", header=None, names=["ticker", "date", "o", "h", "l", "c", "v"], dtype={"ticker": str, "date": str}, keep_default_na=False)
    if cut: ex = ex[ex.date <= cut]
    cal = sorted(ex[ex.ticker == "SPY"].date); cidx = {dd: i for i, dd in enumerate(cal)}
    t = pd.read_csv(f"{d}/{tf}", sep="\t", low_memory=False)
    t = t[(t.arm == "pp") & (t.entry == "orh5") & (t.K == "tl") & (t.C0 == 1)].copy()
    if cut: t = t[t.E <= cut]
    t["ci"] = t.E.map(cidx)
    # (a) recount by merge
    mb = c[(c.class_p == "measurable_breakout") & (c.covered == 1)].copy()
    keep = ["ticker", "t", "s50", "b", "win_start", "win_end", "gain"]
    m = mb[keep].merge(t[["ticker", "ci", "E", "exit_session", "status", "pnl_adr", "adr20", "fill", "realized_r"]], on="ticker", how="left")
    m = m[(m.ci >= m.win_start) & (m.ci <= m.win_end)].sort_values(["ticker", "t", "ci"])
    first = m.groupby(["ticker", "t"]).head(1).copy()
    first["exit_ci"] = first.ci + first.exit_session
    ep = e.set_index(["ticker", "t"])
    first["close_t"] = [ep.loc[(a, b), "close_t"] for a, b in zip(first.ticker, first.t)]
    first["close_p"] = [ep.loc[(a, b), "close_p"] for a, b in zip(first.ticker, first.t)]
    first["kept"] = first.pnl_adr / ((first.close_p - first.close_t) / (first.adr20 * first.fill))
    p(f"  (a) recount: covered MB {len(mb)} (report {len(mb)}); triggered {first.groupby(['ticker','t']).ngroups} (report {int(mb.triggered.sum())}); "
      f"still in at s50 {int((first.exit_ci >= first.s50).sum())} (report {int(mb.still_in_s50.sum())}); kept >= half {int((first.kept >= 0.5).sum())} (report {int(mb.kept_half_episode.sum())}); "
      f"near b {int((first.ci - first.b).abs().le(5).sum())} (report {int(mb.near_b.sum())}); stopped before s50 {int((first.status.isin(['stopped','stopped_day0']) & (first.exit_ci < first.s50)).sum())} (report {int(mb.stopped_before_s50.sum())}); "
      f"mean R {first.realized_r.mean():+.3f} (report {mb.loc[mb.triggered==1,'realized_r'].mean():+.3f})")
    # (c) triggered but not watched on a base night -> E must be > b
    tnw = mb[(mb.triggered == 1) & (mb.watched == 0)]
    p(f"  (c) triggered but not watched on a base night: n = {len(tnw)}; all E > b: {bool((tnw.E_minus_b > 0).all())}; E - b median {tnw.E_minus_b.median():.0f}; of the triggered {int(mb.triggered.sum())}, watched-and-triggered {int(((mb.triggered==1)&(mb.watched==1)).sum())}")
    # (d) the catches that kept >= half / still in at s50
    kh = mb[(mb.triggered == 1) & (mb.kept_half_episode == 1)][["ticker", "trough_date", "b", "E", "E_minus_b", "realized_r", "pnl_adr", "gain_adr", "kept_share_episode", "status", "exit_session"]]
    p(f"  (d) kept >= half of the episode's gain (n = {len(kh)}):\n" + kh.to_string(index=False))
    si = mb[(mb.triggered == 1) & (mb.still_in_s50 == 1)]
    p(f"  (d) still in at s50 (n = {len(si)}): realized R median {si.realized_r.median():.2f}, mean {si.realized_r.mean():.2f}; kept share median {si.kept_share_episode.median():.3f}; status {si.status.value_counts().to_dict()}; "
      f"tickers: {', '.join(si.ticker.head(25))}")
    # (b) named episodes recomputed from the raw export
    names = {"2017-21": ["MSTR", "NVAX", "PLUG", "TSLA", "ENPH", "ZM"], "2022-24": ["MSTR", "SMCI", "APP", "GME", "NVDA", "TSLA"]}[era]
    for tk in names:
        rows = c[(c.ticker == tk) & (c.class_p == "measurable_breakout")]
        if rows.empty: continue
        r = rows.iloc[0]
        g = ex[ex.ticker == tk].set_index("date").reindex(cal)
        H, L, C = g.h.to_numpy(float), g.l.to_numpy(float), g.c.to_numpy(float)
        tt, pp_, b, Lw = int(r.t), int(r.p), int(r.b), int(r.L)
        adr60 = np.nanmean(((H - L) / C)[b - 60: b])                                 # ADR60 at b-1
        span = (np.nanmax(H[b - Lw: b]) - np.nanmin(L[b - Lw: b])) / (adr60 * C[b - 1])
        sw = abs(np.nanmean(C[b - Lw: b - Lw + 5]) - np.nanmean(C[b - 5: b])) / (adr60 * C[b - 1])
        gain = C[pp_] / C[tt] - 1
        s50 = tt + 1 + int(np.argmax(C[tt + 1: pp_ + 1] >= C[tt] * (1 + 0.5 * gain)))
        p(f"  (b) {tk}: trough {cal[tt]} ${C[tt]:.2f} -> peak {cal[pp_]} ${C[pp_]:.2f} (+{100*gain:.0f}%); base [{cal[b-Lw]}..{cal[b-1]}] L={Lw} span {span:.2f} ADR60 (<=5 {span<=5.0}), sideways {sw:.2f} (<=2 {sw<=2.0}), "
          f"base high {np.nanmax(H[b-Lw:b]):.2f}, breakout close {cal[b]} ${C[b]:.2f} (> high {C[b] > np.nanmax(H[b-Lw:b])}); s50 {cal[s50]} (table {cal[int(r.s50)]}); "
          f"watched {int(r.watched)} (first watch night - b {r.first_watch_night_minus_b}); triggered {int(r.triggered)}" +
          (f" E {r.E} (E-b {r.E_minus_b:+.0f}) fill {r.fill:.2f} stop {r.stop:.2f} status {r.status} R {r.realized_r:+.2f} exit session {int(r.exit_session)} still in s50 {int(r.still_in_s50)} kept {r.kept_share_episode:+.3f}" if r.triggered == 1 else f" gate at b-1: {r.gate_bprev}, furthest {r.furthest_gate}"))
with open(f"{HERE}/04_main_loop_checks.txt", "w") as fh:
    fh.write("\n".join(out) + "\n")
