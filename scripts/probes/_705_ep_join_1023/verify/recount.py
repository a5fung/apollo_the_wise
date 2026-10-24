#!/usr/bin/env python3
"""Independent recount of three label-matched EP events straight from the daily CSV lines (no pandas, no shared code):
gap = open(E) / close(E-1) - 1; mean20 = mean volume over the 20 rows E-20..E-1; med$vol20 = median close x volume over the same rows.
Must equal ep_events_{A,B}.tsv.gz to 4 significant figures."""
import gzip, statistics, sys
D = "/Users/alvinfung/apollo_data"
def recount(f, t, d):
    rows = []
    with gzip.open(f, "rt") as fh:
        for line in fh:
            if line.startswith(t + ","):
                p = line.strip().split(",")
                if p[1] <= d:
                    rows.append(p)
    rows.sort(key=lambda r: r[1])
    E, prev, base = rows[-1], rows[-2], rows[-21:-1]
    assert len(base) == 20 and base[-1] is prev
    mean20 = sum(float(r[6]) for r in base) / 20
    meddv = statistics.median(float(r[5]) * float(r[6]) for r in base)
    print(f"{t} E {E[1]} open {E[2]} prev {prev[1]} close {prev[5]} gap {100 * (float(E[2]) / float(prev[5]) - 1):.4f}% vol {E[6]} mean20 {mean20:.0f}"
          f" vr {float(E[6]) / mean20:.4f} med$vol20 {meddv:.6g} base {base[0][1]}..{base[-1][1]}")
recount(f"{D}/cb702_pre_v2/daily_closes_all.csv.gz", "MRNA", "2020-11-30")
recount(f"{D}/cb702_pre_v2/daily_closes_all.csv.gz", "DKNG", "2020-04-27")
recount(f"{D}/cb702/daily_closes_all.csv.gz", "KWEB", "2022-03-16")
print("--- the script's rows (ticker E D iE hist prev_adj prev_raw open gap vol mean_v20 med_v20 vr20_mean vr20_med vr50 med_dv20 ext5):")
import subprocess
for era, t, d in (("A", "MRNA", "2020-11-30"), ("A", "DKNG", "2020-04-27"), ("B", "KWEB", "2022-03-16")):
    out = subprocess.run(f"gzcat {D}/cb702/qm_streams/ep_join_1023/ep_events_{era}.tsv.gz | awk -F'\\t' '$1==\"{t}\" && $2==\"{d}\"' | cut -f1-17", shell=True, capture_output=True, text=True).stdout.strip()
    print(out)
