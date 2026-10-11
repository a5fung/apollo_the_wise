"""#146 detection page — is the q1 pre-filter a SUPERSET of what prod admitted? $0, reads captured files only.

A ticker with a stored WATCH-or-better row (q3, all tickers, since 2026-06-29) that is absent from q1_candidates.out
is a name the population lost. Also lists what the stored table holds, so the validity step has its denominator.
Run from the repo root:  python scripts/probes/_146_page/leak_check.py > scripts/probes/_146_page/leak_check.out
"""
import collections
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ACTIONABLE = ("WATCH", "TIGHTENING", "COILED", "TRIGGERED")


def read(path):
    rows = []
    hdr = None
    for ln in open(os.path.join(HERE, path)):
        p = ln.rstrip("\n").split("\t")
        if hdr is None:
            hdr = p
            continue
        if len(p) != len(hdr) or p[0].startswith("("):
            continue
        rows.append(dict(zip(hdr, p)))
    return rows


def main():
    cand = {r["ticker"] for r in read("q1_candidates.out")}
    stored = read("q3_stored_rows.out")
    print(f"q1 candidates: {len(cand)} tickers")
    print(f"q3 stored rows since 2026-06-29: {len(stored)} rows, {len({r['ticker'] for r in stored})} tickers, "
          f"{len({r['scan_date'] for r in stored})} scan dates ({min(r['scan_date'] for r in stored)} .. {max(r['scan_date'] for r in stored)})")
    by_stage = collections.Counter(r["stage"] for r in stored)
    print("stored rows by stage:", dict(by_stage))
    raw_by = collections.Counter((r["held_from_stage"] or r["stage"]) for r in stored)
    print("stored rows by RAW read (held_from_stage when a hold):", dict(raw_by))

    leaks = collections.defaultdict(list)
    for r in stored:
        if r["stage"] in ACTIONABLE and r["ticker"] not in cand:
            leaks[r["ticker"]].append((r["scan_date"], r["stage"], r["reason"][:60]))
    print(f"\nLEAK CHECK: stored WATCH-or-better tickers absent from q1: {len(leaks)}")
    for t, rows in sorted(leaks.items()):
        print(f"  {t}: {len(rows)} rows, first {rows[0]}, last {rows[-1]}")
    # stage-level view of the leak
    leak_rows = sum(len(v) for v in leaks.values())
    act_rows = sum(1 for r in stored if r["stage"] in ACTIONABLE)
    print(f"leaked WATCH+ rows: {leak_rows} of {act_rows}")
    for s in ACTIONABLE:
        n_all = sum(1 for r in stored if r["stage"] == s)
        n_leak = sum(1 for r in stored if r["stage"] == s and r["ticker"] not in cand)
        print(f"  {s:10} {n_leak} of {n_all} rows belong to a ticker the pre-filter lost")


if __name__ == "__main__":
    main()
