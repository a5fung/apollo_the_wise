"""R4: prereg 5.5 population / outcome readings for the carried features, from the same thirds; compared to stage 3's printed lines. Also seed-2411 + 30/90-session base rates (discovery only)."""
import re, json
from datetime import date
import numpy as np, pandas as pd
import r4_common as C, r4_stats as S, r4_keep as K
import v1_replay as R
from scripts.probes._cb_backtest import runner
import r4_outcomes as OU
D = pd.read_parquet(C.OUTD / f"r4_disc_frame{C.SUF}.parquet")
O = pd.read_parquet(C.BIG / f"r4_outcomes_disc{C.SUF}.parquet")
Kp = pd.read_parquet(C.BIG / f"r4_events_kept{C.SUF}.parquet"); W = pd.read_parquet(C.BIG / f"r4_events_postdrop{C.SUF}.parquet")
D = D.merge(O[["era", "ticker", "D", "monster", "clean", "adr_tail", "fail", "win_untrunc", "win_hiE", "win_E1", "full_window", "proxy"]], on=["era", "ticker", "D"], suffixes=("", "_o"))
D = D.merge(Kp[["era", "ticker", "D", "stype"]], on=["era", "ticker", "D"], how="left")
# first break after 60 quiet sessions over ALL post-drop break rows
fq60 = K.first_after_quiet(W.ikey.to_numpy(), W.uD.to_numpy(), 60, False)
W["fq60"] = fq60
D = D.merge(W[["era", "ticker", "D", "fq60"]], on=["era", "ticker", "D"], how="left")
# QQQ above its 50-day at D (era A store)
Sa = R.load_store("A"); Dd = Sa.D
q = Dd.tid["QQQ"]; bars, cidx = runner.bars_for(Dd, q)
c = np.asarray(bars.c, float); cs = np.concatenate(([0], np.cumsum(c)))
qab = {}
for i in range(49, len(c)):
    qab[Dd.cal[int(cidx[i])].isoformat()] = bool(c[i] >= (cs[i + 1] - cs[i - 49]) / 50)
D["qqq_above"] = [qab.get(d) for d in D.D]
D = D.sort_values(["era", "E", "ticker"]).reset_index(drop=True)
sc = pd.factorize(D.era + "|" + D.month)[0]; y = D.win.to_numpy(float); yr = np.array([int(x[:4]) for x in D.E])
txt = open("/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_winner_study_1124/stage3/3_discovery.txt").read()
sec = txt[txt.index("## 5.5 EXTRA READINGS"):]
subsets = {"first breaks (after 10 quiet sessions)": D.first_break.to_numpy(bool), "later breaks": ~D.first_break.to_numpy(bool),
           "first break after 60 quiet sessions": D.fq60.fillna(False).to_numpy(bool), "common stock only": (D.stype == "CS").to_numpy(),
           "price >= $5": (D.f2 >= 5).to_numpy(), "embargoed discovery (E <= 2020-10-06)": (D.E <= "2020-10-06").to_numpy(), "2019-20 alone": yr >= 2019,
           "full 60-session windows only": D.full_window.to_numpy(bool), "QQQ above its 50-day at D": D.qqq_above.fillna(False).to_numpy(bool),
           "QQQ below its 50-day at D": (~D.qqq_above.fillna(True).astype(bool)).to_numpy()}
alt = {"un-truncated window": D.win_untrunc.to_numpy(float), "from max(level, high of E)": D.win_hiE.to_numpy(float), "E+1..E+60": D.win_E1.to_numpy(float)}
bad = 0; tot = 0; lines = []
for f, tk in (("f1", "f01"), ("f2", "f02"), ("f4", "f04"), ("f9", "f09")):
    v = D[f].to_numpy(float); a = S.thirds_assign(v, sc)
    tb = re.search(rf"\n   {tk} .*?(?=\n   f\d\d |\n\n|\Z)", sec, re.S)
    block = sec[sec.index(f"   {tk} "):]
    block = block[:block.find("\n\n   f", 10) if "\n\n   f" in block[10:] else len(block)]
    for name, m in subsets.items():
        a_s = S.thirds_assign(np.where(m, v, np.nan), sc)      # own thirds inside the subset (months holding >= 6 subset events)
        top, bot = (a_s == 2), (a_s == 0)
        wt, wb = int(y[top].sum()), int(y[bot].sum()); nt, nb = int(top.sum()), int(bot.sum())
        r = (wt / nt) / (wb / nb) if nt and nb and wb else float("nan")
        mm = re.search(rf"{re.escape(name)}\s+n\(top\+bottom\)\s+(\d+) \| winners top:bottom (\d+):(\d+) \| ratio ([\d.]+)", block)
        ok = bool(mm and int(mm.group(1)) == nt + nb and int(mm.group(2)) == wt and int(mm.group(3)) == wb and abs(float(mm.group(4)) - r) < 0.0015)
        tot += 1; bad += (not ok)
        lines.append((f, name, nt + nb, f"{wt}:{wb}", round(r, 3), mm.groups() if mm else None, ok))
    for name, lab in alt.items():
        top, bot = (a == 2), (a == 0)
        wt, wb = int(lab[top].sum()), int(lab[bot].sum()); r = (wt / top.sum()) / (wb / bot.sum())
        mm = re.search(rf"{re.escape(name)}.*?ratio ([\d.]+)", block)
        if mm is None and name == "E+1..E+60": mm = re.search(r"E\+1.*?ratio ([\d.]+)", block)
        lines.append((f, name, "-", f"{wt}:{wb}", round(r, 3), mm.group(1) if mm else None, bool(mm and abs(float(mm.group(1)) - r) < 0.0015)))
for l in lines: print(l)
print("population lines compared:", tot, "mismatching:", bad)
json.dump([list(map(str, l)) for l in lines], open(C.OUTD / f"r4_extras55{C.SUF}.json", "w"))
