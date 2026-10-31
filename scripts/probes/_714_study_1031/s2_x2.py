"""#714 X2 (prereg §9) — analyst rating-event pace for his 8 EPs vs their scored rivals, INSIDE market-cap bands. Leg L only; no verdict beyond
'a lead for a wider pull'. Source: yfinance upgrades_downgrades (a CURRENT snapshot of dated events; thin for small caps — 'no events' can mean 'no coverage'),
fetched 2026-10-31 (out/x2_upgrades.jsonl). $0. Outcome-free."""
import sys, os, json, datetime as dt
import numpy as np, pandas as pd
import importlib.util
HERE = os.path.dirname(os.path.abspath(__file__))
sys.argv = [sys.argv[0]]
spec = importlib.util.spec_from_file_location("s2", os.path.join(HERE, "s2_read.py"))
s2 = importlib.util.module_from_spec(spec); spec.loader.exec_module(s2)
import io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    S, B, popB, labun = s2.step0_1()
    popB, ba = s2.step1(S, B, popB)
ev = {}
meta = {}
for l in open(os.path.join(HERE, "out", "x2_upgrades.jsonl")):
    r = json.loads(l); ev[r["ticker"]] = r["events"]; meta[r["ticker"]] = r
print(f"X2: fetched {len(ev)} tickers on {min(m['fetched_at'] for m in meta.values())}..{max(m['fetched_at'] for m in meta.values())} UTC;"
      f" fetch failed (None): {sum(1 for v in ev.values() if v is None)}; fetched but empty (no events on file): {sum(1 for v in ev.values() if v == [])}")
def feats(tk, d):
    e = ev.get(tk)
    if e is None:
        return dict(n365=np.nan, up90=np.nan, decel=np.nan)
    D = dt.date.fromisoformat(d)
    n365 = up90 = upprior = 0
    for x in e:
        xd = dt.date.fromisoformat(x["date"])
        if D - dt.timedelta(days=365) <= xd <= D - dt.timedelta(days=1):
            n365 += 1
            if x["action"] == "up":
                if xd >= D - dt.timedelta(days=90): up90 += 1
                else: upprior += 1
    return dict(n365=n365, up90=up90, decel=upprior * 90.0 / 275.0 - up90)
rm_ = None
F = pd.DataFrame([feats(r.ticker, r.scan_date) for r in ba.itertuples()])
ba = pd.concat([ba.reset_index(drop=True), F], axis=1)
x1 = {}
for l in open(os.path.join(HERE, "out", "x1_float.jsonl")):
    r = json.loads(l); x1[r["ticker"]] = r.get("mcap")
# market cap source, in order: scan-log value at the time, mi_market_caps snapshot, yfinance marketCap fetched 2026-10-31 (POST-HOC fallback: a CURRENT value)
mc = ba.market_cap.where(ba.market_cap > 0, ba.market_cap_snapshot)
mc = mc.where(mc.notna(), pd.Series([x1.get(t) for t in ba.ticker], dtype=float))
print("market-cap band source on R1+EPs rows: scan-log", int((ba[(rm_ | (ba.is_labelled == 't'))].market_cap > 0).sum()) if False else "mixed (scan-log / mi_market_caps snapshot / yfinance now)")
ba["band"] = pd.cut(mc, [0, 2e9, 10e9, 1e13], labels=["<2B", "2-10B", ">=10B"]).astype(object)
rm = s2.rival_mask(ba, "R1")
rows = []
for tk, d in s2.LABELLED:
    ep = ba[(ba.ticker == tk) & (ba.scan_date == d) & (ba.is_labelled == "t")].iloc[0]
    riv = ba[rm & (ba.scan_date == d) & (ba.band == ep.band)]
    rec = dict(ticker=tk, band=ep.band, n_events_365=ep.n365, n_up_90=ep.up90, decel=round(ep.decel, 2) if np.isfinite(ep.decel) else np.nan, rivals_same_band=len(riv))
    for col, orient in (("n365", -1), ("up90", -1), ("decel", +1)):
        rv = (orient * riv[col]).to_numpy(float); rv = rv[np.isfinite(rv)]
        v = orient * ep[col] if np.isfinite(ep[col]) else np.nan
        rec[f"place_{col}"] = ((rv < v).sum() + 0.5 * (rv == v).sum()) / len(rv) if (np.isfinite(v) and len(rv) >= 4) else np.nan
    rec["rival_median_events_365"] = float(np.nanmedian(riv.n365)) if len(riv) else np.nan
    rows.append(rec)
df = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(df.to_string(index=False, float_format=lambda x: f"{x:.2f}"))
for col, name in (("place_n365", "fewer rating events in the prior year"), ("place_up90", "no upgrade in the last 90 days"), ("place_decel", "upgrade pace slowing")):
    ok = df[col].dropna()
    print(f"  {name}: readable EPs (>=4 same-band rivals with a value) {len(ok)} of 8; mean place {ok.mean():.2f}" if len(ok) else f"  {name}: no EP has >=4 same-band rivals with a value -> NOT READ", "| n_eligible<5 -> NOT READ" if len(ok) < 5 else "")
