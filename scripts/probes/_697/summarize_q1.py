"""Summarise q1_admit_replay.out (the #697 item-2 admit-count replay). Read-only; no prod access."""
import collections
import os
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
rows = [ln.rstrip("\n").split("\t") for ln in open(os.path.join(HERE, "q1_admit_replay.out"))]
nights = [r for r in rows if r[0] == "night"]
extras = [r for r in rows if r[0] == "extra"]


def summarize(lo: str, label: str) -> None:
    ns = [r for r in nights if r[1] >= lo]
    ex = [int(r[5]) for r in ns]
    print(f"{label}: nights={len(ns)} extra median={st.median(ex)} min={min(ex)} max={max(ex)} mean={st.mean(ex):.1f}")
    print(f"  rows_D median={st.median([int(r[2]) for r in ns])} "
          f"old_carry median={st.median([int(r[3]) for r in ns])} "
          f"new_carry median={st.median([int(r[4]) for r in ns])}")
    cc = collections.defaultdict(list)
    for d in sorted({r[1] for r in ns}):
        c = collections.Counter(e[3] for e in extras if e[1] == d)
        for k in ("trig5", "tight5", "watch5", "tight25"):
            cc[k].append(c.get(k, 0))
    for k, v in cc.items():
        print(f"   {k}: median={st.median(v)} max={max(v)} mean={st.mean(v):.1f}")


summarize("2026-07-16", "ALL60 (07-16 ->)")
summarize("2026-08-04", "CLEAN-ERA (08-04 ->, the 25-session lookback sits wholly inside the 06-27 HTF rule)")
summarize("2026-09-08", "POST-LABOR-DAY (09-08 ->)")
print("distinct extra tickers 08-04->:", len({e[2] for e in extras if e[1] >= "2026-08-04"}))
print("distinct extra tickers 09-08->:", len({e[2] for e in extras if e[1] >= "2026-09-08"}))
