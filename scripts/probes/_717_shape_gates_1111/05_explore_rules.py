"""Round 2 EXPLORATION (in-sample, declared in amendment 2): for candidate night-before rules, how many of Qullamaggie's
263 listed buys (and 26 big winners) each would BLOCK, and which of his 17 `no` / 11 good-ok it rejects. Uses the
feature table of 04_diagnose.py. Output is a menu, not a score.
    python3 scripts/probes/_717_shape_gates_1111/05_explore_rules.py > scripts/probes/_717_shape_gates_1111/05_explore_rules.out"""
import contextlib
import io
import runpy

with contextlib.redirect_stdout(io.StringIO()):
    ns = runpy.run_path("scripts/probes/_717_shape_gates_1111/04_diagnose.py")
G, Q = ns["rowsG"], ns["rowsQ"]
RULES = {  # name: predicate that is True when the chart is REJECTED
    "above_base   c_vs_basehigh > 0": lambda f: f["c_vs_basehigh"] > 0,
    "above_base   c_vs_basehigh > 1": lambda f: f["c_vs_basehigh"] > 1,
    "bottom_today since_bottom == 0": lambda f: f["since_bottom"] == 0,
    "bottom<=1    since_bottom <= 1": lambda f: f["since_bottom"] <= 1,
    "bottom<=2    since_bottom <= 2": lambda f: f["since_bottom"] <= 2,
    "stack21_50   e21_vs_s50 < -1.0": lambda f: f["e21_vs_s50"] < -1.0,
    "stack21_50   e21_vs_s50 < -0.5": lambda f: f["e21_vs_s50"] < -0.5,
    "stack21_50   e21_vs_s50 < 0": lambda f: f["e21_vs_s50"] < 0,
    "fall21       e10<e21 & de21_10<0": lambda f: f["e10_vs_e21"] < 0 and f["de21_10"] < 0,
    "fall21b      e10<e21 & de21_5<0": lambda f: f["e10_vs_e21"] < 0 and f["de21_5"] < 0,
    "fall21c      de21_5<0 & de21_10<0 & de21_20<0": lambda f: f["de21_5"] < 0 and f["de21_10"] < 0 and f["de21_20"] < 0,
    "fall21d      de21_20 < -0.4": lambda f: f["de21_20"] < -0.4,
    "channel      lowslope<0 & highslope<0 & e10<e21": lambda f: f["lowslope10"] < 0 and f["highslope10"] < 0 and f["e10_vs_e21"] < 0,
    "channel2     lowslope<-0.1 & highslope<-0.1": lambda f: f["lowslope10"] < -0.1 and f["highslope10"] < -0.1,
    "pullback     de10_5<0 & c<e10": lambda f: f["de10_5"] < 0 and f["c_vs_e10"] < 0,
    "pullback2    de10_5<-0.15 & c_vs_e10<-0.2": lambda f: f["de10_5"] < -0.15 and f["c_vs_e10"] < -0.2,
    "ext10        c_vs_e10 > 1.0": lambda f: f["c_vs_e10"] > 1.0,
    "ext10        c_vs_e10 > 1.5": lambda f: f["c_vs_e10"] > 1.5,
    "ext50        max10_vs_s50 > 6": lambda f: f["max10_vs_s50"] > 6,
    "ext50        c_vs_s50 > 3": lambda f: f["c_vs_s50"] > 3,
    "offhigh      max10-c > 2 (daily ranges)": lambda f: f["max10_vs_s50"] - f["c_vs_s50"] > 2,
    "offhigh      max10-c > 2.5": lambda f: f["max10_vs_s50"] - f["c_vs_s50"] > 2.5,
    "lowerlow     low5_vs_prev5 < -2": lambda f: f["low5_vs_prev5"] < -2,
    "tight        spread10 > 4": lambda f: f["spread10"] > 4,
}
print(f"{'rule':52s} QM blocked /263  big/26  okb/39 | no rejected /17 | good-ok dropped /11")
for name, rej in RULES.items():
    qb = [x for x in Q if rej(x[3])]
    big = sum(x[1].startswith("BIG") for x in qb)
    okb = sum(x[1].replace("BIG ", "").split(",")[0].strip() in ("good", "ok", "okish", "decent") for x in qb)
    no = [x[0] for x in G if x[1] == "no" and rej(x[3])]
    ok = [x[0] for x in G if x[1] in ("good", "ok") and rej(x[3])]
    print(f"{name:52s} {len(qb):4d} ({len(qb) / len(Q):4.0%})   {big:3d}    {okb:3d}   | {len(no):2d} {no} | {len(ok)} {ok}")
