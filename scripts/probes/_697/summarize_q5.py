"""Parity check: the PRODUCTION carry query (q5_carry_prod.out, run read-only on prod) through the real
`flag_carry_sources`, against the independent replay (q1_admit_replay.out, a different SQL). The per-date
carried-name counts must be IDENTICAL; any gap means the shipped query is not the rule the replay measured.
Run from the repo root:  PYTHONPATH=. python scripts/probes/_697/summarize_q5.py"""
import collections
import os

from agents.market_intelligence import db as db_mod

HERE = os.path.dirname(os.path.abspath(__file__))

sections: dict[str, list[dict]] = {}
cur = None
for ln in open(os.path.join(HERE, "q5_carry_prod.out")):
    ln = ln.rstrip("\n")
    if ln.startswith("## EXPLAIN"):
        break
    if ln.startswith("## "):
        cur = ln[3:]
        sections[cur] = []
        continue
    if cur is None or ln.startswith("ticker\t") or ln.startswith("("):
        continue
    t, stage, lag = ln.split("\t")
    sections[cur].append({"ticker": t, "stage": stage, "lag": int(lag)})

replay = {}
for ln in open(os.path.join(HERE, "q1_admit_replay.out")):
    p = ln.rstrip("\n").split("\t")
    if p[0] == "night":
        replay[p[1]] = int(p[4])             # new_carry

ok = True
for d, rows in sections.items():
    carried = db_mod.flag_carry_sources(rows)
    tags = collections.Counter(tg for v in carried.values() for tg in v)
    want = replay.get(d)
    flag = "" if want is None else (" == replay" if want == len(carried) else f" != replay {want}  <-- MISMATCH")
    ok &= want is None or want == len(carried)
    print(f"{d}: {len(rows)} stored rows -> {len(carried)} carried names {dict(tags)}{flag}")
    for who in ("WDAY", "GH", "CDNA", "CHYM"):
        if who in carried:
            print(f"    {who}: {carried[who]}")
print("PARITY:", "OK" if ok else "FAILED")
