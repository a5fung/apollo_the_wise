"""#714 stage 1b X1 — yfinance Ticker.info['floatShares'] for the prereg's fetch tiers.
The SAME field + vendor the live score reads (collector.get_fmp_profile). $0, no prod.
Writes one JSON line per ticker to out/x1_float.jsonl (fetched_at on every line). Resumable.
A ticker that returns nothing is UNKNOWN (float=null), never 0.
Usage: python3 s1b_fetch_float.py smoke | run [pace_seconds]
"""
import json, sys, time, datetime, os
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out", "x1_float.jsonl")

def sections(path):
    out, cur = {}, None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("=== "):
                cur = line[4:].strip(); out[cur] = []; continue
            if cur is None or not line or (line.startswith("(") and line.rstrip().endswith(("rows)", "row)"))):
                continue
            out[cur].append(line.split("|"))
    return out

def fetch_one(t, tries=4):
    err = None
    for k in range(tries):
        try:
            info = yf.Ticker(t).info or {}
            return {"ticker": t, "float": info.get("floatShares"), "shares_out": info.get("sharesOutstanding"),
                    "mcap": info.get("marketCap"), "qtype": info.get("quoteType"), "err": None}
        except Exception as e:  # noqa
            err = f"{type(e).__name__}: {str(e)[:120]}"
            time.sleep(5 * (k + 1))
    return {"ticker": t, "float": None, "shares_out": None, "mcap": None, "qtype": None, "err": err}

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "smoke"
    pace = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    s = sections(os.path.join(HERE, "out", "50_fetch_lists.out"))
    A = s["FETCH_A"][1:]; B = s["FETCH_B"][1:]
    tierA = sorted({r[0] for r in A if r[5] == "t"})
    tierB = sorted({r[0] for r in B})
    todo = tierA + [t for t in tierB if t not in set(tierA)]
    if mode == "smoke":
        for t in ["PENG", "MRNA", "BFLY"]:
            print(fetch_one(t))
        return
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT):
            try: done.add(json.loads(line)["ticker"])
            except Exception: pass
    print(f"todo {len(todo)} (tier A {len(tierA)}), already {len(done)}", flush=True)
    with open(OUT, "a") as f:
        for i, t in enumerate(todo):
            if t in done: continue
            r = fetch_one(t)
            r["fetched_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
            r["tier"] = "A" if t in set(tierA) else "B"
            f.write(json.dumps(r) + "\n"); f.flush()
            if i % 25 == 0: print(i, t, r["float"], r["err"], flush=True)
            time.sleep(pace)
    print("DONE", flush=True)

if __name__ == "__main__":
    main()
