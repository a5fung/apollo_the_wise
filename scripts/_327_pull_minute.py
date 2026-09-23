#!/usr/bin/env python3
"""#327 Phase 2 — pull the minute-days both arms need, reusing the _270_intraday_pull
pattern (Polygon 1-min aggs, POLYGON_API_KEY lives in the apollo-market container env).

Local driver: reads _327_minute_days.tsv (ticker|date|arm from Phase 1), runs ONE in-
container python fetch over the deduped (ticker,date) pairs via the operator-authorized
`ssh ... docker exec apollo-market python` read path, and writes _327_minute.tsv:
  ticker<TAB>t_ms<TAB>o<TAB>h<TAB>l<TAB>c<TAB>v   (RTH+ext; the harness filters to RTH).

Read-only (Polygon market data). No trade state. The remote program uses ONLY double
quotes so it nests safely inside the remote single-quoted `-c '...'`.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NEEDED = HERE / "_327_minute_days.tsv"
OUT = HERE / "_327_minute.tsv"
ERR = HERE / "_327_minute.err"
HOST = "apollo@87.99.134.162"

pairs = sorted({(p[0], p[1]) for p in
                (ln.split("|") for ln in NEEDED.read_text(encoding="utf-8").splitlines() if ln)})
print(f"pulling {len(pairs)} (ticker,date) minute-days …")

pairs_lit = "[" + ",".join(f'("{t}","{d}")' for t, d in pairs) + "]"
pycode = (
    "import json,os,sys,time,urllib.request\n"
    "KEY=os.environ[\"POLYGON_API_KEY\"]\n"
    f"PAIRS={pairs_lit}\n"
    "for t,d in PAIRS:\n"
    "    url=f\"https://api.polygon.io/v2/aggs/ticker/{t}/range/1/minute/{d}/{d}?adjusted=true&sort=asc&limit=50000&apiKey={KEY}\"\n"
    "    try:\n"
    "        rr=json.load(urllib.request.urlopen(url,timeout=25))\n"
    "        for b in rr.get(\"results\",[]):\n"
    "            tt=b[\"t\"];o=b[\"o\"];h=b[\"h\"];lo=b[\"l\"];cl=b[\"c\"];vv=b[\"v\"]\n"
    "            print(f\"{t}\\t{tt}\\t{o}\\t{h}\\t{lo}\\t{cl}\\t{vv}\")\n"
    "    except Exception as e:\n"
    "        print(f\"# ERR {t} {d}: {e}\",file=sys.stderr)\n"
    "    time.sleep(0.12)\n"
)
remote = "docker exec apollo-market python -c '" + pycode + "'"

res = subprocess.run(["ssh", HOST, remote], capture_output=True, text=True, timeout=600)
OUT.write_text(res.stdout, encoding="utf-8")
ERR.write_text(res.stderr, encoding="utf-8")

n_rows = sum(1 for _ in res.stdout.splitlines())
got = {ln.split("\t", 1)[0] for ln in res.stdout.splitlines() if "\t" in ln}
errs = [ln for ln in res.stderr.splitlines() if ln.startswith("# ERR")]
print(f"exit={res.returncode}  rows={n_rows}  tickers_with_data={len(got)}  errs={len(errs)}")
for e in errs[:15]:
    print("  " + e)
if res.returncode != 0 and not n_rows:
    print("STDERR (head):\n" + "\n".join(res.stderr.splitlines()[:10]), file=sys.stderr)
