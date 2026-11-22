#!/usr/bin/env python3
"""STAGE 1 / step 1a — population asserts of prereg §1 and §3, Q-suffix list, last-bar and fund counts. OUTCOME-FREE.
Run: python3 01_population.py > 01_population.txt"""
import numpy as np
import pandas as pd
import common as C

print("# EP big-winner study — STAGE 1 / 01 population (prereg §1, §3). No outcome is read.")
print(f"prereg sha256 (as read, before any stage-1 output): {C.sha(C.PREREG)}")
ev = C.build_population()
cal = C.calendars()

# tickers
per_t = ev.groupby("ticker").size()
per_et = ev.groupby(["era", "ticker"]).size()
print(f"tickers (distinct symbols, eras pooled): {len(per_t)}; events per ticker median {per_t.median():g}, max {per_t.max()}"
      f" | distinct (era, ticker): {len(per_et)}, median {per_et.median():g}, max {per_et.max()}")
assert len(per_t) == 1977 and per_t.median() == 2 and per_t.max() == 19, (len(per_t), per_t.median(), per_t.max())

# per year
exp_year = {"2016": (326, 0), "2017": (378, 0), "2018": (455, 0), "2019": (484, 0), "2020": (771, 0), "2021": (707, 0),
            "2022": (160, 344), "2023": (0, 527), "2024": (0, 513)}
print("per year (era A / era B):")
for y in sorted(exp_year):
    a = int(((ev.year == y) & (ev.era == "A")).sum()); b = int(((ev.year == y) & (ev.era == "B")).sum())
    print(f"  {y}: {a}/{b}")
    assert (a, b) == exp_year[y], (y, a, b)
assert set(ev.year) == set(exp_year)
st = ev.sectype.value_counts().to_dict()
print(f"security type: CS {st.get('CS', 0)} · ADR(ADRC) {st.get('ADRC', 0)} · untyped {st.get('', 0)}")
assert (st.get("CS", 0), st.get("ADRC", 0), st.get("", 0)) == (3541, 211, 913)

# §3 table
print("\n§3 DISCOVERY / CONFIRM (by event date):")
exp3 = {"DISC": (2414, 2195, 54, 680), "CONF": (2251, 2178, 45, 233)}
for s in ("DISC", "CONF"):
    g = ev[ev.set == s]
    h = g[g.hist_n >= 130]
    assert (g.b_hist130 == (g.hist_n >= 130)).all()
    grp = h.groupby(["era", "month"]).size()
    n6 = int((grp >= 6).sum())
    unt = int((g.sectype == "").sum())
    print(f"  {s}: events {len(g)} (A {int((g.era == 'A').sum())} · B {int((g.era == 'B').sum())}) | with >= 130 bars of history {len(h)}"
          f" | (era, month) groups with >= 6 such events {n6} | untyped (fund proxy, #705) {unt}")
    assert (len(g), len(h), n6, unt) == exp3[s], (s, len(g), len(h), n6, unt)
g = ev[ev.set == "CONF"]
assert (int((g.era == "A").sum()), int((g.era == "B").sum())) == (867, 1384)
assert (ev[ev.set == "DISC"].era == "A").all()
print("  every §1 and §3 count asserted equal to the frozen text.")

# Q-suffix symbols (later bankruptcy marker)
q = ev[(ev.era == "A") & ev.ticker.str.fullmatch(r"[A-Z]{4}Q")]
print(f"\nera-A events whose symbol is 5 letters ending in Q: {len(q)} events, {q.ticker.nunique()} symbols")
for t, g in q.groupby("ticker"):
    print(f"  {t}: {len(g)} event(s): {', '.join(g.E)}")
qb = ev[(ev.era == "B") & ev.ticker.str.fullmatch(r"[A-Z]{4}Q")]
print(f"(beside) era-B events with such a symbol: {len(qb)} events, {qb.ticker.nunique()} symbols: {sorted(set(qb.ticker))}")

# last bar before the era file's end (outcome-free count; the bar VALUES after E are not read, only the last bar DATE per ticker)
bars = C.bars_cached(ev, cal)
print("\nevent tickers whose last bar is before the era file's end (era A file end 2022-06-30; era B read end 2024-12-31):")
for e in "AB":
    tk = sorted(set(ev.loc[ev.era == e, "ticker"]))
    end = cal[e][-1]
    miss = [t for t in tk if (e, t) not in bars]
    assert not miss, miss
    early = [t for t in tk if bars[(e, t)][0][-1] < end]
    n_ev = int(ev[(ev.era == e) & ev.ticker.isin(early)].shape[0])
    print(f"  era {e}: {len(early)} of {len(tk)} event tickers (carrying {n_ev} events); calendar end {end}")
# sanity: every event has its E bar and the E-1 bar on the previous calendar session, and open matches the event list
bad = 0
for r in ev.itertuples(index=False):
    d, ci, o, h, l, c, v = bars[(r.era, r.ticker)]
    iE = int(np.searchsorted(cal[r.era], r.E))
    assert cal[r.era][iE] == r.E and iE == r.iE
    i = int(np.searchsorted(ci, iE))
    assert ci[i] == iE and ci[i - 1] == iE - 1 and d[i - 1] == r.D
    if abs(o[i] / r.open - 1) > 1e-4 or abs(c[i - 1] / r.prev_close_adj - 1) > 1e-4:
        bad += 1
    assert i >= 20 and ci[i - 20] == iE - 20              # the population's 20 consecutive baseline sessions
print(f"\nevent rows checked against bars: E bar present, E-1 on the previous session, 20 consecutive prior sessions: all {len(ev)};"
      f" open(E)/close(E-1) differing from the event list by > 1e-4: {bad}")
assert bad == 0
assert ("A", "SPY") in bars and ("B", "SPY") in bars
print(f"fund count (untyped events = the #705 fund proxy): DISC {int(((ev.set == 'DISC') & (ev.sectype == '')).sum())} · CONF {int(((ev.set == 'CONF') & (ev.sectype == '')).sum())}")
cols = ["era", "ticker", "E", "D", "iE", "hist_n", "prev_close_adj", "prev_close_raw", "open", "gap_pct", "vr20_mean", "med_dv20", "sectype", "set", "year", "month", "quarter"]
ev[cols].to_csv(C.HERE / "population.tsv", sep="\t", index=False)
print(f"population.tsv written ({len(ev)} rows; identifying + outcome-free event-list columns only) sha256 {C.sha(C.HERE / 'population.tsv')}")
