"""#580 probe: diff the dashboard-rule list (recomputed from the committed snapshot) against the REAL /themes
render path replayed by the sibling probe (replay_themes_output.txt, real repo functions on captured prod rows).
READ-ONLY."""
import re, json, pandas as pd
from datetime import timedelta
here = "/Users/alvinfung/apollo_the_wise/scripts/probes/_580/"
txt = open(here + "replay_themes_output.txt").read()
blk = txt.split("== TOP 20 by /themes flat rank")[1].split("top15 overlap")[0]
rep = []
for line in blk.splitlines():
    m = re.match(r"\s*(\d+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d.]+)\s+\w+\s*/\s*(.+)$", line)
    if m:
        rep.append(dict(rank=int(m[1]), comp=float(m[2]), n_tk=int(m[5]), n_sc=int(m[6]), name=m[8].strip()))
rep = pd.DataFrame(rep)
E = pd.read_csv(here + "ecosystems_rule_latest.csv")            # dashboard default rule (Retired filtered BEFORE latest-per-name)
raw = json.load(open(here + "snapshot_origin_main_e4a7ef6.json"))
th = pd.DataFrame(raw["themes"]); th["theme_date"] = pd.to_datetime(th.theme_date).dt.date
latest_date = th.theme_date.max()
lat_all = th[th.theme_date >= latest_date - timedelta(days=7)].sort_values("theme_date").groupby("name").tail(1)
alive = set(lat_all[lat_all.stage != "Retired"].name)
Ef = E[E.name.isin(alive)].reset_index(drop=True); Ef["fixed_rank"] = Ef.index + 1     # dashboard list with the #214 order fixed
print("replay rows parsed:", len(rep))
m = rep.merge(Ef[["name", "fixed_rank", "comp", "n_scored", "n_members"]], on="name", how="left", suffixes=("_themes", "_dash"))
m["comp_diff"] = (m.comp_themes - m.comp_dash).abs()
print(m[["rank", "fixed_rank", "name", "comp_themes", "comp_dash", "n_sc", "n_scored", "n_tk", "n_members"]].to_string(index=False))
print("\ntop20 rank identical (dashboard-with-#214-fix vs real /themes replay):", bool((m["rank"] == m["fixed_rank"]).all()))
print("max |comp diff| (replay is rounded to 0.1):", round(m.comp_diff.max(), 3))
print("n_scored / n_members agree on all 20:", bool((m.n_sc == m.n_scored).all() and (m.n_tk == m.n_members).all()))
raw_rank = E.reset_index(drop=True); raw_rank["dash_rank_today"] = raw_rank.index + 1
mm = rep.merge(raw_rank[["name", "dash_rank_today"]], on="name", how="left")
print("top20 rank identical on the dashboard AS DEPLOYED today:", bool((mm["rank"] == mm["dash_rank_today"]).all()),
      "| positions that differ:", int((mm["rank"] != mm["dash_rank_today"]).sum()), "of", len(mm))
# cutoff sensitivity: app uses cloud-server date.today()-7 (2026-09-30 -> 09-23), probe used latest_date-7 (09-22)
for cut_date in (latest_date - timedelta(days=7), latest_date - timedelta(days=6)):
    w = th[(th.theme_date >= cut_date) & (th.stage != "Retired")]
    names = set(w.sort_values("theme_date").groupby("name").tail(1).name)
    la = th[th.theme_date >= cut_date].sort_values("theme_date").groupby("name").tail(1)
    ghosts = set(la[la.stage == "Retired"].name) & names
    ghost_scored = [n for n in ghosts if n in set(E.name)]
    print(f"cutoff {cut_date}: ghost themes (Retired-newest shown anyway) = {len(ghosts)}; of which in scored Ecosystems list ~{len(ghost_scored)}")
