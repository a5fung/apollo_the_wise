"""#687 INDEPENDENT CHECK (5b) — the line-test table recomputed from line_tests.tsv, and the line-test days re-derived from MY
walker's A1 path. Writes check_linetests.txt."""
import csv, statistics, collections
from pathlib import Path
HERE = Path(__file__).resolve().parent
O = open(HERE / "check_linetests.txt", "w")
def P(*a):
    s = " ".join(str(x) for x in a); print(s); O.write(s + "\n")
L = list(csv.DictReader(open(HERE / "line_tests.tsv"), delimiter="|"))
for blk in ("ALL", "DISC", "HELD"):
    S = [r for r in L if blk == "ALL" or r["block"] == blk]
    rec = [r for r in S if r["cls"] == "RECLAIM"]; sl = [r for r in S if r["cls"] == "SLICE"]
    deep = [r for r in S if float(r["depth_adr"]) >= 1.0]
    P(f"   {blk}: days {len(S)} trades {len({(r['ticker'], r['entry_day']) for r in S})} reclaim {len(rec)} slice {len(sl)} | >=1ADR {len(deep)} reclaimed {sum(r['cls'] == 'RECLAIM' for r in deep)} "
      f"| A0 sold a reclaim day {sum(r['A0_action'] == 'stop_hit' for r in rec)} | D10 sold a reclaim day {sum(r['D10_action'] == 'stop_hit' for r in rec)} "
      f"| median depth reclaim {statistics.median(float(r['depth_adr']) for r in rec):.2f} ADR ({statistics.median(float(r['depth_pct']) for r in rec):.2f}%) "
      f"slice {statistics.median(float(r['depth_adr']) for r in sl):.2f} ({statistics.median(float(r['depth_pct']) for r in sl):.2f}%)")
b = collections.Counter(); rb = collections.Counter()
for r in L:
    x = float(r["depth_adr"]); k = "<1/4" if x < 0.25 else "1/4-1/2" if x < 0.5 else "1/2-1" if x < 1 else ">=1"
    b[k] += 1; rb[k] += r["cls"] == "RECLAIM"
P("   depth buckets (days, reclaimed):", {k: (b[k], rb[k]) for k in ("<1/4", "1/4-1/2", "1/2-1", ">=1")})
d10rec = [r for r in L if r["cls"] == "RECLAIM" and r["D10_action"] == "stop_hit"]
deep_d10 = [r for r in d10rec if float(r["depth_adr"]) >= 1.0]
P(f"   D10 reclaim-day sales {len(d10rec)}; of them >= 1 ADR deep {len(deep_d10)}: {[(r['ticker'], r['day'], r['A1_action']) for r in deep_d10]}")
P(f"   of those, A1 HELD: {[r['ticker'] for r in deep_d10 if r['A1_action'] == 'HELD']}")
O.close()
