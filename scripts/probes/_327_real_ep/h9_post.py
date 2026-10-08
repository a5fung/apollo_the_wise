"""#327 H9 post-process — reads h9_rows.tsv only (no re-run): all-in paired totals per era on the fires scored under
every compared arm (winners + non-winners together), what the killed fires were worth on the other stops, and the
>= 3R tail per arm on that common set. Output: h9_post_out.txt. $0, measurement only."""
import csv
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
rows = list(csv.DictReader(open(HERE / "h9_rows.tsv"), delimiter="|"))
ARMS = ("inc_trail", "adr100_trail", "Q_ST", "Q_S", "P_ST", "P_S")
out = []


def say(s=""):
    print(s)
    out.append(s)


def f(x):
    return float(x) if x not in ("", None) else None


for era in ("A", "B"):
    E = [r for r in rows if r["era"] == era]
    common = [r for r in E if all(r[f"{a}_status"] == "scored" for a in ARMS)]
    say(f"ERA {era}: {len(E)} fires; scored under ALL six arms: {len(common)} ({sum(1 for r in common if r['winner'] == 'True')} winner fires)")
    for a in ARMS:
        R = [f(r[f"{a}_R"]) for r in common]
        D = [f(r[f"{a}_D"]) for r in common]
        by = defaultdict(float)
        for r in common:
            by[r["ticker"]] += f(r[f"{a}_R"])
        top = sorted(by.items(), key=lambda kv: -kv[1])[:2]
        d2 = sum(by.values()) - sum(v for _, v in top)
        byd = defaultdict(float)
        for r in common:
            byd[r["ticker"]] += f(r[f"{a}_D"])
        topd = sorted(byd.items(), key=lambda kv: -kv[1])[:2]
        dd2 = sum(byd.values()) - sum(v for _, v in topd)
        ge3 = sum(1 for x in R if x >= 3.0 - 1e-9)
        say(f"  {a:13s} all-in sum {sum(R):+7.1f}R (drop-best-2 names {d2:+7.1f}; {', '.join(f'{t} {v:+.1f}' for t, v in top)}) | "
            f"$-R sum {sum(D):+6.1f} (drop-best-2 {dd2:+6.1f}) | >=3R {ge3} ({100 * ge3 / len(R):.1f}%)")
    killed = [r for r in E if r["Q_ST_status"] == "killed"]
    say(f"  ladder-killed fires (entry below the gap fill): {len(killed)} on {len({r['ticker'] for r in killed})} names; "
        f"worth on the lane's stop {sum(f(r['inc_trail_R']) or 0 for r in killed if r['inc_trail_status'] == 'scored'):+.1f}R / "
        f"{sum(f(r['inc_trail_D']) or 0 for r in killed if r['inc_trail_status'] == 'scored'):+.1f} $-R; "
        f"on 1xADR {sum(f(r['adr100_trail_R']) or 0 for r in killed if r['adr100_trail_status'] == 'scored'):+.1f}R / "
        f"{sum(f(r['adr100_trail_D']) or 0 for r in killed if r['adr100_trail_status'] == 'scored'):+.1f} $-R; "
        f">= 3R on 1xADR: {sorted(r['ticker'] + ' ' + r['rung'].replace('ep_', '') for r in killed if r['adr100_trail_status'] == 'scored' and f(r['adr100_trail_R']) >= 3)}")
    kinds = Counter(r["rung"] for r in killed)
    say(f"  killed by pattern: {dict(kinds)}")
    say("")

(HERE / "h9_post_out.txt").write_text("\n".join(out) + "\n")
