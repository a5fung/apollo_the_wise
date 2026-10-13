"""Cells for the alert-rank running read, from a verify_rank_shadow_*.out (pipe format, psql or run_read.py).
Same measure as the 09-30..10-11 resolutions: 5-day best high from the EP-day OPEN in multiples of ADR20
(h over the first 6 sessions incl. the EP day); BAR = 8x; 'broke low' = min low of the next 5 sessions < EP-day low;
matured-5d = 6 sessions on record; top quartile = rank <= 0.25. 20-day = h over 21 sessions, matured at >=21."""
import sys, csv

def load(path):
    rows = []
    with open(path) as f:
        lines = [l.rstrip("\n") for l in f if l.strip() and not l.startswith("(")]
    for l in lines[1:]:
        p = l.split("|")
        if len(p) != 15: continue
        t = lambda x: None if x == "" else float(x)
        rows.append(dict(ticker=p[0], date=p[1], adr=float(p[2]), filled=p[3] in ("t", "True"), tier=p[4],
                         r_eod=float(p[5]), pool_eod=int(p[6]), r_0945=float(p[7]), pool_0945=int(p[8]),
                         open=t(p[9]), low=t(p[10]), sess=int(p[11]), h5=t(p[12]), h20=t(p[13]), l5=t(p[14])))
    return rows

def x(r, h):  # multiple of ADR20 from the EP-day open
    return (h - r["open"]) / r["open"] / r["adr"]

def cells(rows, rk, label):
    m = [r for r in rows if r["sess"] >= 6 and r["h5"] is not None]
    out = []
    for name, sel in (("top quartile (<=0.25)", lambda r: r[rk] <= 0.25), ("the rest", lambda r: r[rk] > 0.25)):
        c = [r for r in m if sel(r)]
        hit = [r for r in c if x(r, r["h5"]) >= 8]
        brk = [r for r in c if r["l5"] is not None and r["l5"] < r["low"]]
        out.append(f"  {label:6s} {name:22s} matured={len(c):2d}  reached8x={len(hit)} {[h['ticker'] for h in hit]}  broke_low={len(brk)}")
    return out

def main(path, want_arg=None):
    rows = load(path)
    sessions = sorted({r["date"] for r in rows})
    m5 = [r for r in rows if r["sess"] >= 6 and r["h5"] is not None]
    m20 = [r for r in rows if r["sess"] >= 21 and r["h20"] is not None]
    print(f"FILE {path}\nrows={len(rows)} sessions={len(sessions)} latest={sessions[-1]} filled={sum(r['filled'] for r in rows)} matured5d={len(m5)} matured20d={len(m20)}")
    print("5-DAY cells:")
    for l in cells(rows, "r_eod", "EOD"): print(l)
    for l in cells(rows, "r_0945", "09:45"): print(l)
    print("20-DAY (secondary; only rows with 21 sessions):")
    for rk, lab in (("r_eod", "EOD"), ("r_0945", "09:45")):
        for name, sel in (("top", lambda r: r[rk] <= 0.25), ("rest", lambda r: r[rk] > 0.25)):
            c = [r for r in m20 if sel(r)]
            hit = [r for r in c if x(r, r["h20"]) >= 8]
            print(f"  {lab:6s} {name:5s} matured={len(c):2d} reached8x={len(hit)} {[h['ticker'] for h in hit]}")
    if want_arg:
        want = set(want_arg.split(","))
        print("ROWS of interest (5d x-ADR / broke low / sess / EOD rank,pool / 09:45 rank,pool / filled):")
        for r in rows:
            if r["ticker"] in want or r["date"] in want:
                x5 = x(r, r["h5"]) if r["h5"] else float("nan")
                print(f"  {r['date']} {r['ticker']:5s} sess={r['sess']} x5={x5:5.2f} broke_low={r['l5'] is not None and r['l5'] < r['low']} eod={r['r_eod']:.3f}/{r['pool_eod']} 0945={r['r_0945']:.3f}/{r['pool_0945']} filled={r['filled']} tier={r['tier']}")
    print("TOP-QUARTILE rows (EOD rank<=0.25) matured:", [(r['ticker'], r['date'], round(x(r, r['h5']), 2), r['l5'] < r['low']) for r in m5 if r['r_eod'] <= 0.25])
    print("big winners (>=8x 5d, any rank):", [(r['ticker'], r['date'], round(x(r, r['h5']), 2), r['r_eod'], r['pool_eod']) for r in m5 if x(r, r['h5']) >= 8])

main(*sys.argv[1:3]) if len(sys.argv) > 1 else None
