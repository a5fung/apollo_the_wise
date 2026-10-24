"""#705 (2026-10-24): do the replays of his calls beat simply holding the market? His bar (verbatim): "at the very least the test
needs to show real alpha and strong market outperformance, otherwise the strategy is DOA". Reads the STORED daily account curves of
the three frozen replays (no re-walk, no new outcome) and the QQQ / SPY closes of the rebuilt 2017-21 file (split-adjusted price
only: dividends are NOT included, ~0.6-1.5% a year, which flatters the strategy slightly). For each curve and window: total return,
CAGR, the same for QQQ and SPY held over the same dates, max drawdown, Sharpe (daily, rf = 0, x sqrt 252), and a daily regression
of strategy returns on QQQ returns -> beta and annualised alpha (intercept x 252) with a t-stat. Descriptive; decides nothing."""
import numpy as np, pandas as pd
D = "/Users/alvinfung/apollo_data/cb702/qm_streams"
curves = []
for f, key in ((f"{D}/qm_replay_1023/account_his.tsv", "config"), (f"{D}/qm_round3_1024/account_his.tsv", "variant")):
    t = pd.read_csv(f, sep="\t"); t = t.rename(columns={key: "name"}); curves.append(t)
c = pd.concat(curves)
keep = {"primary": "his rules, 20% cap (first replay)", "B0": "his rules, 30% cap", "W2": "+ speed trail", "W2b": "no partial, 10-day trail",
        "W4m_B0": "his rules, 30% cap, 2x margin", "COMBINED": "round-3 combined"}
c = c[c.name.isin(keep)]
px = pd.read_csv("/Users/alvinfung/apollo_data/cb702_pre_v2/daily_closes_all.csv.gz", names=list("tdohlcv"), usecols=[0, 1, 5])
px = px[px.t.isin(["QQQ", "SPY"])].pivot(index="d", columns="t", values="c")
def stats(eq, dates):
    r = eq.pct_change().dropna(); q = px.loc[dates, "QQQ"].pct_change().dropna(); s = px.loc[dates, "SPY"].pct_change().dropna()
    yrs = len(dates) / 252
    tot = eq.iloc[-1] / eq.iloc[0] - 1; qt = px.loc[dates[-1], "QQQ"] / px.loc[dates[0], "QQQ"] - 1; st = px.loc[dates[-1], "SPY"] / px.loc[dates[0], "SPY"] - 1
    dd = (eq / eq.cummax() - 1).min(); qdd = (px.loc[dates, "QQQ"] / px.loc[dates, "QQQ"].cummax() - 1).min()
    sh = r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else np.nan; qsh = q.mean() / q.std() * np.sqrt(252)
    X = np.vstack([np.ones(len(q)), q.values]).T; b, res, *_ = np.linalg.lstsq(X, r.loc[q.index].values, rcond=None)
    e = r.loc[q.index].values - X @ b; se = np.sqrt((e @ e) / (len(e) - 2) * np.linalg.inv(X.T @ X)[0, 0])
    return dict(total=tot, cagr=(1 + tot) ** (1 / yrs) - 1, qqq=qt, spy=st, maxdd=dd, qqq_dd=qdd, sharpe=sh, qqq_sharpe=qsh,
                beta=b[1], alpha_ann=b[0] * 252, alpha_t=b[0] / se, days=len(dates))
rows = []
for name, g in c.groupby("name"):
    g = g.set_index("date").equity.sort_index(); g = g[g.index.isin(px.index)]
    for win, lo, hi in (("2017-03..2021-12 (full)", "2017-03-01", "2021-12-31"), ("2020-2021", "2020-01-01", "2021-12-31")):
        e = g[(g.index >= lo) & (g.index <= hi)]
        st = stats(e / e.iloc[0], list(e.index)); st.update(variant=keep[name], window=win); rows.append(st)
out = pd.DataFrame(rows)[["window", "variant", "days", "total", "qqq", "spy", "cagr", "maxdd", "qqq_dd", "sharpe", "qqq_sharpe", "beta", "alpha_ann", "alpha_t"]]
pd.set_option("display.width", 250)
fmt = out.copy()
for k in ("total", "qqq", "spy", "cagr", "maxdd", "qqq_dd", "alpha_ann"): fmt[k] = (100 * fmt[k]).round(1).astype(str) + "%"
for k in ("sharpe", "qqq_sharpe", "beta", "alpha_t"): fmt[k] = fmt[k].round(2)
print(fmt.sort_values(["window", "variant"]).to_string(index=False))
