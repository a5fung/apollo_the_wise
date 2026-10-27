#!/usr/bin/env python3
"""#705 as-is — the minute-pull list (his "Yes" 2026-10-26; regular hours only — his note the same evening: "he doesn't buy
premarket"). Every (session, bar symbol) pair that step 5's reachable sets read (wide windows excluded, as step 5 excludes them)
whose minute state is `missing` (a daily bar exists, no tree logged it ok or empty). Writes `fetch_list_asis_1026.tsv`
(`ticker|date`) for `scripts/probes/_cb_backtest/fetch_minutes.py`. Reads local files only; imports only this read's modules."""
import collections, importlib, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..")))
P = importlib.import_module("scripts.probes._705_asis_1026.01_points")
C = P.C

def main() -> int:
    tally = collections.Counter()
    L = P.load_all(lambda *a, **k: None, tally)
    pairs = set()
    for w in L["buys"] + L["sales"]:
        if w.wide or not w.reach:
            continue
        for d, _, _ in w.reach:
            pairs.add((d, w.bar_sym))
    L["store"].preload(sorted(pairs))
    state = collections.Counter()
    missing = []
    for d, tk in sorted(pairs):
        s = L["store"].state(d, tk)
        state[s.split(":")[0]] += 1
        if s.startswith("missing"):
            C.seal_date(d, "fetch list")
            missing.append((tk, d))
    out = os.path.join(HERE, "fetch_list_asis_1026.tsv")
    with open(out, "w") as fh:
        fh.write("ticker|date\n")
        for tk, d in missing:
            fh.write(f"{tk}|{d}\n")
    by_year = collections.Counter(d[:4] for _, d in missing)
    print(f"pairs read by step 5: {len(pairs):,}; states {dict(state)}; missing written {len(missing):,} over {len({d for _, d in missing})} dates; "
          f"by year {dict(sorted(by_year.items()))} -> {out}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
