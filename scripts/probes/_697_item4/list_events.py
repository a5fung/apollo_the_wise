import collections, sys
rows = [l.rstrip("\n").split("\t") for l in open(sys.argv[1])][1:]
first = [r for r in rows if r[8] == "FIRST"]
print("rows with the stamp:", len(rows), "| first-day events:", len(first))
by_t = collections.Counter(r[1] for r in first)
print("events per ticker (top):", by_t.most_common(15))
for r in first:
    src, t, d, stage, pdate, age, frm, days, _, stored = r
    print(f"{src:7} {t:5} {d} stage={stage:11} pivot={pdate} age={age:>3} from={frm} day={days} | stored: {stored}")
