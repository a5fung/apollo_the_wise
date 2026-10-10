"""#655 scope — parse capture.raw.gz (the ONE prod pull) into plain Python structures. $0, offline."""
import csv, gzip, io, json, pickle
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
_CACHE = HERE / "_capture.pkl"


def _j(line):
    # COPY text format doubles backslashes; JSON escapes survive as single backslashes after this.
    return json.loads(line.replace("\\\\", "\\"))


def load():
    if _CACHE.exists():
        return pickle.load(open(_CACHE, "rb"))
    secs = defaultdict(list)
    cur = None
    for ln in gzip.open(HERE / "capture.raw.gz", "rt"):
        ln = ln.rstrip("\n")
        if ln.startswith("@@"):
            cur = ln[2:]
            continue
        if cur and ln:
            secs[cur].append(ln)
    out = {}
    out["correctness"] = [_j(x) for x in secs["AUDIT_CORRECTNESS"]]
    for r in out["correctness"]:
        r["detail"] = json.loads(r["detail"])
    out["events"] = [_j(x) for x in secs["AUDIT_THEME_EVENTS"]]
    th = [_j(x) for x in secs["THEMES"]]
    for r in th:
        r["d"] = date.fromisoformat(r["d"])
        r["tickers"] = list(r["tickers"] or [])
    out["themes"] = th
    out["eco"] = {r["theme"]: r["e"] for r in map(_j, secs["ECOSYSTEMS"])}
    out["industry"] = {r["t"]: r for r in map(_j, secs["INDUSTRY"])}
    scores = defaultdict(dict)
    for row in csv.reader(io.StringIO("\n".join(secs["SCORES"]))):
        d, t, rs, sec = row
        scores[date.fromisoformat(d)][t] = {"rs": float(rs) if rs else None, "sector": sec or None}
    out["scores"] = dict(scores)
    closes = defaultdict(dict)
    for t, d, c in csv.reader(io.StringIO("\n".join(secs["CLOSES"]))):
        closes[t][date.fromisoformat(d)] = float(c)
    out["closes"] = dict(closes)
    pickle.dump(out, open(_CACHE, "wb"))
    return out


if __name__ == "__main__":
    b = load()
    print("correctness rows", len(b["correctness"]), [r["et"] for r in b["correctness"]])
    print("events", len(b["events"]), "theme rows", len(b["themes"]), "eco", len(b["eco"]),
          "industry", len(b["industry"]), "score dates", sorted(b["scores"]), "close tickers", len(b["closes"]))
    d = b["correctness"][-1]["detail"]
    print(list(d.keys())); print(list(d["g3"].keys())); print(d["g3"]["themes"][:2]); print(d["g4"])
