"""#594 sample 11 draw: q1.out rows -> exclusions (ruled tickers, sample 10, names in his notes/labelled EPs) -> one row per ticker -> random.Random(1126).sample(12)."""
import re, random, sys
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from tests.fixtures import must_not_trade_charts as m
ruled = set()
for v in vars(m).values():
    if isinstance(v, (list, tuple, dict)):
        for x in (v.values() if isinstance(v, dict) else v):
            t = getattr(x, "ticker", None) or (x.get("ticker") if isinstance(x, dict) else None) or (x[0] if isinstance(x, tuple) and x and isinstance(x[0], str) else None)
            if t: ruled.add(t)
s10 = {l.split("|")[1] for l in open("../_594_sample10_1121/key_do_not_show.txt").read().strip().split("\n")[2:]}
words = set()
for f in ("docs/methodology/operator_shared_notes.md", "docs/methodology/operator_labelled_eps.md"):
    words |= set(re.findall(r"\b[A-Z]{1,5}\b", open("/Users/alvinfung/apollo_the_wise/" + f).read()))
rows, arm = [], None
for l in open("q1.out"):
    l = l.strip()
    if l.startswith("== "): arm = l.split()[1]
    elif arm and re.match(r"^[A-Z.]+\|20", l):
        p = l.split("|"); rows.append((p[0], p[1], arm, p[-1]))
elig, seen = [], set()
for r in sorted(rows, key=lambda r: (r[0], r[1])):
    if r[0] in ruled or r[0] in s10 or r[0] in words or r[0] in seen: continue
    seen.add(r[0]); elig.append(r)
print(f"rows {len(rows)} ruled-tickers {len(ruled)} eligible {len(elig)}", file=sys.stderr)
pick = random.Random(1126).sample(elig, min(12, len(elig)))
out = ["#594 sample #11 key: page letter -> arm and outcome. NOT shown to him (outcome-blind, his 10-10 ruling).",
       "RULE: sample 10's query with sample 10's 12 drawn pairs excluded; tickers already ruled (must_not_trade_charts), in sample 10, or named in his notes / labelled EPs (uppercase-word match) excluded; one row per ticker; 12 drawn AT RANDOM across both arms (seed 1126; random.Random(1126).sample over eligible rows sorted by (ticker,date), draw.py). Page: ~2 years of history, the gap day the last bar."]
for L, (t, d, a, p) in zip("ABCDEFGHIJKL", pick): out.append(f"{L}|{t}|{d}|{a}|pct_20d={p}")
open("key_do_not_show.txt", "w").write("\n".join(out) + "\n")
with open("q2_bars.sql", "w") as f:
    f.write("SET default_transaction_read_only = on;\n")
    for t, d, a, p in pick:
        f.write(f"\\echo == {t} {d}\nSELECT * FROM (SELECT trade_date, open_price, high_price, low_price, close AS close_price, volume FROM mi_daily_closes WHERE ticker = '{t}' AND trade_date <= DATE '{d}' ORDER BY trade_date DESC LIMIT 504) x ORDER BY trade_date;\n")
print("arms:", {a: sum(1 for r in pick if r[2] == a) for a in {r[2] for r in pick}}, file=sys.stderr)
