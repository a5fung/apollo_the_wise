import csv, statistics, numpy as np
from collections import defaultdict, Counter
from pathlib import Path
H = Path(__file__).parent
rows = list(csv.DictReader(open(H / "bothsides_rows.tsv"), delimiter="|"))
for r in rows:
    r["cap"] = float(r["cap"]); r["R"] = float(r["R"]) if r["R"] not in ("", "None") else None
    r["settled"] = r["settled"] == "True"
    for k in ("adv", "vol_raw", "px_raw"):
        r[k] = float(r[k]) if r[k] not in ("", "None") else None
out = open(H / "bothsides_stats_out.txt", "w")
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.write(s + "\n")
def boot(tr, seed=359):
    by = defaultdict(lambda: [0, 0, 0.0])
    for t in tr:
        b = by[t["t"]]; b[0] += 1; b[1] += t["R"] >= 3; b[2] += t["R"]
    if not by: return (None, None), (None, None)
    a = np.array(list(by.values())); rng = np.random.default_rng(seed)
    s = a[rng.integers(0, len(a), size=(10000, len(a)))].sum(axis=1)
    r3 = s[:, 1] / s[:, 0]; m = s[:, 2] / s[:, 0]
    return (np.percentile(r3, 5), np.percentile(r3, 95)), (np.percentile(m, 5), np.percentile(m, 95))
def band(c):
    for lo, hi, lab in ((0, 100e6, "<100M"), (100e6, 250e6, "100-250M"), (250e6, 500e6, "250-500M"),
                        (500e6, 1e9, "500M-1B"), (1e9, 2e9, "1-2B"), (2e9, 1e18, ">2B")):
        if lo <= c < hi: return lab
BANDS = ["<100M", "100-250M", "250-500M", "500M-1B", "1-2B", ">2B"]
def table(pop, label, OOS=None):
    P(f"\n## {label}")
    P("band | signals | walked(settled) | tickers | >=3R n (rate) [90% ticker boot] | >=8R | mean R [90%] | mean ex-best-2 | median R | top trades | median ADV$ | median $ traded by tick")
    for b in BANDS:
        sg = [r for r in pop if band(r["cap"]) == b]
        tr = [r for r in sg if r["settled"] and r["R"] is not None]
        if not sg: continue
        n = len(tr); R = sorted((t["R"] for t in tr), reverse=True)
        (l3, h3), (lm, hm) = boot(tr)
        k3 = sum(x >= 3 for x in R); k8 = sum(x >= 8 for x in R)
        exb = statistics.mean(R[2:]) if n > 2 else None
        top = ", ".join(f"{t['t']} {t['d']} {t['R']:+.1f}" for t in sorted(tr, key=lambda t: -t["R"])[:3])
        adv = statistics.median([r["adv"] for r in sg if r["adv"]]) if any(r["adv"] for r in sg) else None
        dv = statistics.median([r["vol_raw"] * r["px_raw"] for r in sg if r["vol_raw"] and r["px_raw"]])
        P(f"{b} | {len(sg)} | {n} | {len({t['t'] for t in tr})} | {k3} ({k3/max(1,n):.1%}) [{(l3 or 0):.1%}-{(h3 or 0):.1%}] | {k8} | "
          f"{statistics.mean(R) if R else float('nan'):+.2f} [{(lm or 0):+.2f},{(hm or 0):+.2f}] | {exb if exb is None else f'{exb:+.2f}'} | "
          f"{statistics.median(R) if R else float('nan'):+.2f} | {top} | ${(adv or 0)/1e6:.1f}M | ${dv/1e6:.2f}M")
    # funnel for the two bands at the floor
    for b in ("250-500M", "500M-1B"):
        sg = [r for r in pop if band(r["cap"]) == b]
        P(f"   funnel {b}: " + str(dict(Counter(r["outcome"] if r["outcome"] != "no_trade" else r["entry_status"] for r in sg))))
OOS = lambda r: r["d"] <= "2026-06-05"
table(rows, "P — every signal, both sides of the floor, whole window 2024-01-02..2026-09-03")
table([r for r in rows if OOS(r)], "P — out-of-sample 2024-01-02..2026-06-05")
table([r for r in rows if r["G_nocd"] == "True"], "Q — passes the live quality stack (ADV$ >= $1M, ATR <= 15%, not extended, pre-mkt shares) — whole window")
table([r for r in rows if r["G"] == "True"], "G — all five stamps incl. the cooldown proxy — whole window")
near = [r for r in rows if 400e6 <= r["cap"] < 600e6]
P(f"\nboundary: {len(near)} signals at $400-600M (Polygon dated shares x raw prior close; #624 C3 agreed with the live cap's side of $500M on 97.7%)")
pooled = lambda lo, hi, pop: [r for r in pop if lo <= r["cap"] < hi and r["settled"] and r["R"] is not None]
for lab, pop in (("P", rows), ("Q", [r for r in rows if r["G_nocd"] == "True"])):
    a, b = pooled(250e6, 5e8, pop), pooled(5e8, 1e9, pop)
    P(f"{lab}: 250-500M walked {len(a)} >=3R {sum(t['R']>=3 for t in a)}; 500M-1B walked {len(b)} >=3R {sum(t['R']>=3 for t in b)}")
out.close()
