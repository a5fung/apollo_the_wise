"""#580 probe (READ-ONLY): what does the operator's live Themes dashboard snapshot carry,
and how do the dashboard's ranking rules order themes vs the /theme rule?

Input: the committed snapshot pulled from portfolio-app2 origin/main (saved beside this file).
No DB, no writes to tracked files. Replicates portfolio-app2 theme_data.py rules in pandas:
  - Grid rank      : theme_data._weekly_universe  (last row per (name, ISO week); rank by rs_avg desc)
  - Ecosystems rank: theme_data.get_ecosystem_board (latest row per name in 7d, non-Retired, non-Fading,
                     comp = trimmed_mean(rs_composite of CURRENT members from snapshot stock_scores))
  - /theme rule    : latest stored row per name, non-Retired, non-Fading (ordering field varies -> compare
                     rs_avg, stored score, recomputed comp).
"""
import json
import sys
from collections import Counter
from datetime import date, timedelta

import pandas as pd

P = "/Users/alvinfung/apollo_the_wise/scripts/probes/_580/snapshot_origin_main_e4a7ef6.json"
raw = json.load(open(P))
th = pd.DataFrame(raw["themes"])
th["theme_date"] = pd.to_datetime(th["theme_date"]).dt.date
th["tickers"] = th["tickers"].apply(lambda t: list(t) if t else [])
th["n_members"] = th["tickers"].apply(len)
sc = pd.DataFrame(raw["stock_scores"])
rs_by = dict(zip(sc["ticker"], sc["rs_composite"]))

print("generated_at:", raw["generated_at"], "| score_date:", raw["score_date"], "| window_weeks:", raw["window_weeks"])
print("theme rows:", len(th), "| stock_scores rows:", len(sc))
print("theme_date range:", th["theme_date"].min(), "->", th["theme_date"].max(), "| distinct dates:", th["theme_date"].nunique())
print("columns:", list(th.columns))

latest_date = th["theme_date"].max()
L = th[th["theme_date"] == latest_date]
print(f"\n== latest theme_date {latest_date}: {len(L)} rows; by stage:", dict(Counter(L["stage"])))
for col in ["pct_above_20sma", "rs_avg", "score", "e_code"]:
    print(f"   NULL {col}: total={L[col].isna().sum()}  | non-Retired={L[L.stage!='Retired'][col].isna().sum()}"
          f" of {(L.stage!='Retired').sum()}")
print("   NULL pct_above_20sma by stage:", dict(L[L.pct_above_20sma.isna()].groupby("stage").size()))
print("   pct_above_20sma value range (stored 0-1):", L["pct_above_20sma"].min(), L["pct_above_20sma"].max())

# NULL pct over history
print("\n== NULL pct_above_20sma over all snapshot rows, non-Retired, by date (last 12 dates):")
nr = th[th.stage != "Retired"]
g = nr.groupby("theme_date").agg(rows=("name", "size"), null_pct=("pct_above_20sma", lambda s: int(s.isna().sum())))
print(g.tail(12).to_string())

# ---- Rule A: Grid (weekly bucket, rs_avg) ----
w = th.copy()
w["week_start"] = pd.to_datetime(w["theme_date"]).dt.to_period("W").dt.start_time.dt.date
w = w.sort_values(["name", "week_start", "theme_date"]).drop_duplicates(["name", "week_start"], keep="last")
w["week_rank"] = w.groupby("week_start")["rs_avg"].rank(method="min", ascending=False, na_option="keep")
lw = w["week_start"].max()
grid_now = w[w["week_start"] == lw].sort_values("week_rank")
print(f"\n== Grid latest ISO week {lw}: {len(grid_now)} rows; theme_date of those rows:", dict(Counter(grid_now['theme_date'])))
print("   stages in that week:", dict(Counter(grid_now["stage"])))
# default stage filter: Nascent/Accelerating/Mainstream/Fading (Retired excluded)
gd = grid_now[grid_now.stage.isin(["Nascent", "Accelerating", "Mainstream", "Fading"])]
print(f"   default stage filter keeps {len(gd)} (Retired dropped: {len(grid_now)-len(gd)}). NOTE Grid ranks span the UNFILTERED universe (adapter rank) unless dedup on.")

# ---- Rule B: Ecosystems (latest row per name within 7d, non-Retired; Fading excluded from scored; comp=trimmed mean of current members) ----
def trimmed_mean(values):
    if not values:
        return 0.0
    if len(values) < 3:
        return sum(values) / len(values)
    s = sorted(values)
    n = len(s)
    drop = 1 if n <= 5 else (2 if n <= 10 else max(1, int(n * 0.2)))
    t = s[drop:]
    return sum(t) / len(t)

cut = latest_date - timedelta(days=7)  # app uses date.today(); snapshot is <=1 day old at export
win = th[(th.theme_date >= cut) & (th.stage != "Retired")]
lat = win.sort_values("theme_date").groupby("name").tail(1)
rows = []
for _, r in lat.iterrows():
    if r["stage"] == "Fading":
        continue
    comps = [rs_by[t] for t in r["tickers"] if t in rs_by and rs_by[t] is not None and pd.notna(rs_by[t])]
    if not comps:
        continue
    rows.append(dict(name=r["name"], stage=r["stage"], theme_date=r["theme_date"], comp=trimmed_mean(comps),
                     n_members=r["n_members"], n_scored=len(comps), rs_avg=r["rs_avg"], score=r["score"],
                     pct=r["pct_above_20sma"]))
E = pd.DataFrame(rows).sort_values("comp", ascending=False).reset_index(drop=True)
E["eco_rank"] = E.index + 1
print(f"\n== Ecosystems rule: {len(E)} scored themes (latest row per name in 7d, non-Retired, non-Fading, with >=1 scored member)")
print("   row date mix of those latest rows:", dict(Counter(E["theme_date"])))
print("   themes whose n_scored < n_members (snapshot stock_scores slice/coverage gap):", int((E.n_scored < E.n_members).sum()))

# ---- Rule C: stored-score/rs_avg on latest-row-per-name, non-Retired non-Fading ----
C = lat[lat.stage != "Fading"].copy()
C["rank_rs_avg"] = C["rs_avg"].rank(method="min", ascending=False)
C["rank_score"] = C["score"].rank(method="min", ascending=False)
M = E.merge(C[["name", "rank_rs_avg", "rank_score"]], on="name", how="left")
show = M.head(15)[["eco_rank", "name", "stage", "comp", "rs_avg", "score", "pct", "n_members", "n_scored", "rank_rs_avg", "rank_score"]]
pd.set_option("display.width", 250)
pd.set_option("display.max_colwidth", 46)
print("\n== TOP 15 by the dashboard's DEFAULT (Ecosystems) rule, with the same themes' rank under stored rs_avg / stored score")
print(show.to_string(index=False))

# top-10 set overlap / order disagreement
top = lambda col, n=10: list(M.sort_values(col)["name"].head(n)) if col.startswith("rank") else list(M.sort_values(col, ascending=False)["name"].head(n))
a = top("comp"); b = top("rank_rs_avg"); c = top("rank_score")
print("\ntop10 comp vs rs_avg overlap:", len(set(a) & set(b)), "| identical order:", a == b)
print("top10 comp vs stored score overlap:", len(set(a) & set(c)), "| identical order:", a == c)
def spearmanr(a,b,nan_policy=None):
    df=pd.concat([pd.Series(list(a)),pd.Series(list(b))],axis=1).dropna()
    return (df.iloc[:,0].rank().corr(df.iloc[:,1].rank()),)
print("spearman comp~rs_avg:", round(spearmanr(M['comp'], M['rs_avg'], nan_policy='omit')[0], 3),
      "| comp~score:", round(spearmanr(M['comp'], M['score'], nan_policy='omit')[0], 3))

# ---- Grid vs Ecosystems for the same latest ISO week (both non-Retired non-Fading, contiguous re-rank) ----
G = grid_now[grid_now.stage.isin(["Nascent", "Accelerating", "Mainstream"])][["name", "week_rank", "rs_avg"]]
G = G.merge(E[["name", "eco_rank", "comp"]], on="name", how="outer", indicator=True)
print("\n== Grid (rs_avg, latest ISO week, N/A/M) vs Ecosystems (comp): membership:", dict(Counter(G["_merge"])))
both = G[G["_merge"] == "both"]
print("   spearman(week_rank, eco_rank) over shared:", round(spearmanr(both['week_rank'], both['eco_rank'])[0], 3))
print("   Grid top10:", list(G.sort_values('week_rank')['name'].head(10)))
print("   Eco  top10:", list(E['name'].head(10)))

# where does breadth sit for the top-10 (NULL?)
print("\n== breadth on the top-15 (Ecosystems rule):", [(r['name'][:28], None if pd.isna(r['pct']) else round(r['pct'], 2)) for _, r in M.head(15).iterrows()])
E.to_csv("/Users/alvinfung/apollo_the_wise/scripts/probes/_580/ecosystems_rule_latest.csv", index=False)

# ---- extra: Retired-filter-before-latest-row bug check (Ecosystems / get_active_themes / get_themes_for_ticker / get_theme_members) ----
allw = th[th.theme_date >= cut]
last_any = allw.sort_values("theme_date").groupby("name").tail(1)
retired_latest = set(last_any[last_any.stage == "Retired"]["name"])
resurrected = set(lat["name"]) & retired_latest   # names the dashboard lists although their newest row is Retired
print("\n== names whose NEWEST row (7d) is Retired yet still listed by the dashboard's filter-then-latest logic:", len(resurrected))
for n in sorted(resurrected):
    r = lat[lat.name == n].iloc[0]
    print("   ", n[:60], "| shown row:", r["theme_date"], r["stage"])
print("   of which would be in the Ecosystems scored list:", len(set(E['name']) & resurrected))
# engine-dropped (no row on latest date, not Retired) still shown via 7d window
stale = lat[lat.theme_date < latest_date]
print("== themes shown from a row OLDER than the latest theme_date (7d recency window):", len(stale),
      "| by stage:", dict(Counter(stale['stage'])))

# ============================================================================================
# PART 2 — corrected rule (Apollo db.get_active_themes: latest row per name FIRST, then drop Retired-latest)
#          vs the dashboard's default Ecosystems ordering, and vs the default Grid ordering.
# ============================================================================================
print("\n\n######## PART 2 ########")
lat_all = th[th.theme_date >= cut].sort_values("theme_date").groupby("name").tail(1)          # latest row per name, THEN filter
fixed = lat_all[lat_all.stage != "Retired"]
fixed_scored = []
for _, r in fixed.iterrows():
    if r["stage"] == "Fading":
        continue
    comps = [rs_by[t] for t in r["tickers"] if t in rs_by and pd.notna(rs_by[t])]
    if not comps:
        continue
    fixed_scored.append(dict(name=r["name"], stage=r["stage"], comp=trimmed_mean(comps), n_members=r["n_members"],
                             n_scored=len(comps), pct=r["pct_above_20sma"], theme_date=r["theme_date"]))
F = pd.DataFrame(fixed_scored).sort_values("comp", ascending=False).reset_index(drop=True)
F["fixed_rank"] = F.index + 1
print(f"dashboard Ecosystems list: {len(E)} themes | corrected (Retired-after-latest) list: {len(F)} themes | removed: {len(E)-len(F)}")
ghosts = E[~E["name"].isin(F["name"])].copy()
print("ghost (Retired-newest) themes the dashboard ranks today, with their dashboard global rank:")
print(ghosts[["eco_rank", "name", "stage", "theme_date", "comp", "n_members"]].to_string(index=False))
mm = E.merge(F[["name", "fixed_rank"]], on="name", how="left")
print("\nTop-15 dashboard rank vs corrected rank:")
print(mm.head(15)[["eco_rank", "fixed_rank", "name"]].to_string(index=False))
print("top10 same SET after correction:", set(E.head(10)["name"]) == set(F.head(10)["name"]),
      "| top10 same ORDER:", list(E.head(10)["name"]) == list(F.head(10)["name"]))
print("ghosts inside dashboard top-10:", int((ghosts["eco_rank"] <= 10).sum()), "| top-30:", int((ghosts["eco_rank"] <= 30).sum()))

# ---- Default Grid ordering: dedup(min_shared=3) + stage filter N/A/M/F + min_age>=2 weeks + rank recomputed over survivors ----
def dedup_themes(theme_tickers, threshold=0.50, min_shared=3):   # verbatim from portfolio-app2 theme_data.py:436-480
    if not theme_tickers:
        return {}
    by_size = sorted(theme_tickers.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    parent_of = {name: name for name, _ in by_size}
    sets = {name: set(tickers) for name, tickers in by_size}
    for i, (s_name, _s) in enumerate(by_size):
        s_set = sets[s_name]
        if not s_set:
            continue
        cands = []
        for j in range(i):
            l_name = by_size[j][0]
            if parent_of[l_name] != l_name:
                continue
            l_set = sets[l_name]
            shared = len(s_set & l_set)
            if shared < min_shared:
                continue
            if shared / len(s_set) >= threshold:
                cands.append((l_name, shared / len(s_set | l_set)))
        if cands:
            parent_of[s_name] = max(cands, key=lambda kv: kv[1])[0]
    return parent_of

weeks12 = w[w["theme_date"] >= (date.today() - timedelta(weeks=12))]
# get_weekly_grid recomputes universe on the 12-week window (same result for latest week)
latest_wk = weeks12[weeks12.week_start == weeks12.week_start.max()].set_index("name")
lt = {n: tuple(r["tickers"]) for n, r in latest_wk.iterrows() if r["tickers"]}
po = dedup_themes(lt, 0.5, 3)
reps = {n for n, p in po.items() if n == p}
gdf = weeks12[weeks12["name"].isin(reps) | ~weeks12["name"].isin(po)]
keep_names = latest_wk[latest_wk.stage.isin(["Nascent", "Accelerating", "Mainstream", "Fading"])].index
gdf = gdf[gdf["name"].isin(keep_names)]
wpt = gdf.groupby("name")["week_start"].nunique()
gdf = gdf[gdf["name"].isin(wpt[wpt >= 2].index)]
piv = gdf.pivot_table(index="name", columns="week_start", values="rs_avg", aggfunc="first").rank(axis=0, method="min", ascending=False, na_option="keep")
cur = piv[piv.columns.max()].dropna().sort_values()
print(f"\nDEFAULT Grid 'Now' list (dedup=3, N/A/M/F, min_age 2, hide unranked): {len(cur)} themes; Fading inside it: "
      f"{int(latest_wk.loc[cur.index,'stage'].eq('Fading').sum())}")
print("Grid top-12 (Now rank, name, stage, rs_avg, members, breadth):")
for nm, rk in cur.head(12).items():
    r = latest_wk.loc[nm]
    print(f"  #{int(rk):>3} {nm[:58]:<58} {r['stage']:<12} rs_avg={r['rs_avg']} n={r['n_members']} pct={r['pct_above_20sma']}")
gtop = list(cur.head(10).index); ftop = list(F.head(10)["name"])
print("Grid top10 vs corrected-/theme-rule top10: same set:", set(gtop) == set(ftop), "| overlap:", len(set(gtop) & set(ftop)), "| same order:", gtop == ftop)
# the biotech precedent: any Fading theme sitting inside the Grid top 30?
fg = [(int(rk), nm) for nm, rk in cur.items() if latest_wk.loc[nm, 'stage'] == 'Fading' and rk <= 30]
print("Fading themes ranked <=30 on default Grid:", fg[:10])

# ============================================================================================
# PART 3 — the ACTUAL /themes rule (agent.py:5023 -> theme_engine.get_today_themes:9516):
#          ALL mi_themes rows on the single latest theme_date (no 7d window, no stage filter),
#          _compute_scored_themes drops empty-ticker rows + Fading, comp = trimmed_mean over current members.
# ============================================================================================
print("\n\n######## PART 3 ########")
R = th[th.theme_date == latest_date]
print("Retired rows on latest date:", len(R[R.stage == 'Retired']), "| with non-empty tickers:", int((R[R.stage == 'Retired'].n_members > 0).sum()))
T = []
for _, r in R.iterrows():
    if r["stage"] == "Fading" or not r["tickers"]:
        continue
    comps = [rs_by[t] for t in r["tickers"] if t in rs_by and pd.notna(rs_by[t])]
    if not comps:
        continue
    T.append(dict(name=r["name"], stage=r["stage"], comp=trimmed_mean(comps), n_members=r["n_members"], n_scored=len(comps)))
T = pd.DataFrame(T).sort_values("comp", ascending=False).reset_index(drop=True)
T["themes_rank"] = T.index + 1
print(f"/themes rule (latest theme_date only): {len(T)} scored themes | dashboard Ecosystems: {len(E)} | corrected latest-per-name: {len(F)}")
X = E.merge(T[["name", "themes_rank"]], on="name", how="left")
print("dashboard-only themes (not in /themes list):", int(X.themes_rank.isna().sum()), "| /themes-only themes:", len(set(T.name) - set(E.name)))
print("Top-12 side by side (dashboard global rank | /themes rank | name):")
for _, r in X.head(12).iterrows():
    print(f"  {int(r.eco_rank):>3} | {'--' if pd.isna(r.themes_rank) else int(r.themes_rank):>3} | {r['name'][:60]}")
d10 = list(E.head(10)["name"]); t10 = list(T.head(10)["name"])
print("top10 identical set:", set(d10) == set(t10), "| identical order:", d10 == t10)
common = [n for n in E["name"] if n in set(T["name"])]
print("relative order of shared themes identical:", common == list(T["name"]))
# pure rank-number displacement among shared themes
disp = X.dropna(subset=["themes_rank"]).assign(d=lambda d: d.eco_rank - d.themes_rank)
print("shared themes whose rank NUMBER differs:", int((disp.d != 0).sum()), "of", len(disp), "| max shift:", int(disp.d.max()))
print("rows of the dashboard list not dated on latest date:", int((E.theme_date < latest_date).sum()))

# ---- where does the relative order of shared themes differ? (expect only exact-comp ties) ----
Tn = list(T["name"]); Cn = common
diff = [(i, a, b) for i, (a, b) in enumerate(zip(Cn, Tn)) if a != b]
print("\nfirst differing positions among shared themes:", [(i, a[:34], b[:34]) for i, a, b in diff[:6]], "| count:", len(diff))
comp_of = dict(zip(E["name"], E["comp"]))
print("all differing pairs are exact comp ties:", all(abs(comp_of[a] - comp_of[b]) < 1e-9 for _, a, b in diff))

# ============================================================================================
# PART 4 — NULL breadth as the dashboard sees it (non-Retired rows), last 12 theme_dates
# ============================================================================================
print("\n\n######## PART 4 ########")
dates = sorted(th.theme_date.unique())[-12:]
S = th[th.theme_date.isin(dates) & (th.stage != "Retired")]
N = S[S.pct_above_20sma.isna()]
print("NULL-breadth non-Retired rows, last 12 dates:", len(N), "of", len(S))
print(" by stage:", dict(Counter(N.stage)))
print(" by days_active (top):", dict(sorted(Counter(N.days_active).items())[:12]))
print(" score==rs_avg rows among NULL (different write path?):", int((N.score.round(3) == N.rs_avg.round(3)).sum()), "of", len(N))
print(" score==rs_avg among NON-NULL breadth rows:", int((S[S.pct_above_20sma.notna()].score.round(3) == S[S.pct_above_20sma.notna()].rs_avg.round(3)).sum()), "of", int(S.pct_above_20sma.notna().sum()))
# for the dashboard's default top-20 (Ecosystems rule) on the latest date: how many lack breadth?
top20 = E.head(20)
print(" top-20 (Ecosystems rule) with NULL breadth:", int(top20.pct.isna().sum()))
# does a NULL row's next-day row carry breadth? (fill-in rate)
nxt = []
for _, r in N[N.theme_date < latest_date].iterrows():
    later = th[(th.name == r["name"]) & (th.theme_date > r["theme_date"])].sort_values("theme_date")
    nxt.append(None if later.empty else (not pd.isna(later.iloc[0]["pct_above_20sma"])))
print(" NULL rows with a later row:", sum(x is not None for x in nxt), "| of those, next row has breadth:", sum(bool(x) for x in nxt if x is not None))
# how the current pages render a NULL breadth
print(" render of NULL: Grid _format_value -> '' (theme_grid.py:77-78); Detail metric -> '—' (theme_detail.py:139-140)")
