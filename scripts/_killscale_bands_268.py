"""#268(b) scratch — kill/scale band statistics from the Phase B replay cohort.

Joins the simulated-trade CSV with the DB tier dump and computes, for the
POST-JUDGE system (judge_tier=HIGH, the live selection authority):
cumulative-R curve / max drawdown, monthly expectancy spread, trailing-20-trade
expectancy distribution, losing streaks. These feed the safeguards.md draft.
"""
import csv
from collections import defaultdict

trades = {}
with open("replay268_phaseB.csv", newline="") as f:
    for row in csv.DictReader(f):
        if row["skipped"] == "True":
            continue
        trades[(row["ticker"], row["alert_date"])] = float(row["r_multiple"])

tiers = {}
with open("replay268_tiers.csv", newline="") as f:
    for row in csv.DictReader(f):
        tiers[(row["ticker"], row["alert_date"])] = (
            row["baseline_floor_tier"], row["judge_tier"])


def cohort(pred):
    rows = sorted(
        (k[1], k[0], r) for k, r in trades.items()
        if k in tiers and pred(*tiers[k]))
    return rows


def stats(name, rows):
    rs = [r for _, _, r in rows]
    n = len(rs)
    if not n:
        print(f"{name}: empty")
        return
    exp = sum(rs) / n
    win = sum(1 for r in rs if r > 0) / n
    # cumulative curve + max drawdown in R
    cum = peak = maxdd = 0.0
    streak = worst_streak = 0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        maxdd = min(maxdd, cum - peak)
        streak = streak + 1 if r <= 0 else 0
        worst_streak = max(worst_streak, streak)
    # trailing-20 expectancy distribution
    t20 = [sum(rs[i:i + 20]) / 20 for i in range(0, n - 19)]
    t20.sort()
    def pct(p):
        return t20[min(len(t20) - 1, int(p * len(t20)))]
    # monthly expectancy
    months = defaultdict(list)
    for d, _, r in rows:
        months[d[:7]].append(r)
    mexps = sorted(sum(v) / len(v) for v in months.values())
    print(f"\n=== {name} ===")
    print(f"n={n} exp={exp:+.2f}R win={win:.0%} sum={sum(rs):+.1f}R")
    print(f"maxDD={maxdd:+.1f}R worst losing streak={worst_streak}")
    print(f"trailing-20 exp: p5={pct(.05):+.2f} p25={pct(.25):+.2f} "
          f"median={pct(.50):+.2f} p75={pct(.75):+.2f} min={t20[0]:+.2f}")
    neg20 = sum(1 for x in t20 if x < 0) / len(t20)
    print(f"share of trailing-20 windows with exp<0: {neg20:.0%}")
    print("monthly exp: " + " ".join(f"{m:+.2f}" for m in mexps))
    # R histogram
    buckets = defaultdict(int)
    for r in rs:
        if r <= -1:
            buckets["<=-1R"] += 1
        elif r < 0:
            buckets["-1..0"] += 1
        elif r < 1:
            buckets["0..1"] += 1
        elif r < 3:
            buckets["1..3"] += 1
        elif r < 6:
            buckets["3..6"] += 1
        else:
            buckets[">=6R"] += 1
    print("R hist: " + " ".join(
        f"{k}:{buckets[k]}" for k in ["<=-1R", "-1..0", "0..1", "1..3", "3..6", ">=6R"]))


stats("POST-JUDGE (judge-HIGH) — the live system", cohort(lambda f, j: j == "HIGH"))
stats("PRE-JUDGE (floor-HIGH) baseline", cohort(lambda f, j: f == "HIGH"))
