"""INDEPENDENT re-derivation of the #577b band replay. Read-only. No prod writes."""
import sys, csv
from collections import defaultdict
from datetime import datetime, timezone, timedelta
P = "/Users/alvinfung/apollo_the_wise/scripts/probes"

BAND = [  # derived from prod query (pasted), ticker, date, ext
 ("WSHP","2026-04-16",55),("JLHL","2026-04-21",60),("BTM","2026-04-21",74),
 ("POET","2026-04-22",53),("HCAI","2026-04-22",51),("MXL","2026-04-24",59),
 ("SILC","2026-05-05",50),("ERNA","2026-05-07",64),("BRUNW","2026-05-15",72),
 ("AKTX","2026-05-22",68),("AKAN","2026-05-22",73),("SIDU","2026-05-27",72),
 ("MX","2026-05-29",58),("BGDE","2026-06-18",52),("SKYQ","2026-07-24",66),
 ("WYHG","2026-08-11",71),("FIEE","2026-08-17",51),("AEHL","2026-09-03",53)]

daily = defaultdict(list); minute = defaultdict(list)
for ln in open(f"{P}/_ext_daily.tsv"):
    p = ln.rstrip("\n").split("\t")
    if len(p) < 7: continue
    daily[p[0]].append({"date":p[1],"o":float(p[2]),"h":float(p[3]),"l":float(p[4]),"c":float(p[5])})
for ln in open(f"{P}/_ext_minute.tsv"):
    p = ln.rstrip("\n").split("\t")
    if len(p) < 7: continue
    et = datetime.fromtimestamp(int(p[1])/1000, timezone.utc) - timedelta(hours=4)
    minute[(p[0], et.date().isoformat())].append({"m":et.hour*60+et.minute,"o":float(p[2]),
        "h":float(p[3]),"l":float(p[4]),"c":float(p[5])})
for ln in open(f"{P}/_577b_extra_bars.tsv"):
    p = ln.rstrip("\n").split("\t")
    if len(p) < 8 or p[0].startswith("#"): continue
    if p[0]=="D":
        daily[p[1]].append({"date":p[2],"o":float(p[3]),"h":float(p[4]),"l":float(p[5]),"c":float(p[6])})
    elif p[0]=="M":
        et = datetime.fromtimestamp(int(p[2])/1000, timezone.utc) - timedelta(hours=4)
        minute[(p[1], et.date().isoformat())].append({"m":et.hour*60+et.minute,"o":float(p[3]),
            "h":float(p[4]),"l":float(p[5]),"c":float(p[6])})
for tk in daily:
    seen, keep = set(), []
    for b in sorted(daily[tk], key=lambda x: x["date"]):
        if b["date"] in seen: continue
        seen.add(b["date"]); keep.append(b)
    daily[tk] = keep

def atr14(bars, i):
    if i < 15: return None
    trs = []
    for k in range(i-14, i):
        b, pc = bars[k], bars[k-1]["c"]
        trs.append(max(b["h"]-b["l"], abs(b["h"]-pc), abs(b["l"]-pc)))
    return sum(trs)/len(trs)

print(f"{'tk':6}{'date':12}{'ORBhi':>9}{'ORBlo':>9}{'ATR14':>8}{'wide?':>7}{'fill@m':>8}{'entry':>9}"
      f"{'R$':>8}{'stopMIN':>9}{'+2Rmin':>8}{'+3Rmin':>8}{'stopDAY':>9}{'+2Rday':>8}{'+3Rday':>8}{'MFE5R':>9}")
res = []
for tk, d, ext in BAND:
    db = daily.get(tk, []); idx = next((i for i,b in enumerate(db) if b["date"]==d), None)
    rth = sorted(minute.get((tk,d),[]), key=lambda x:x["m"])
    rth = [b for b in rth if 570 <= b["m"] < 960]
    if idx is None or not rth:
        print(f"{tk:6}{d:12}  NO BARS (idx={idx}, minutes={len(rth)})"); continue
    orbc = [b for b in rth if 570 <= b["m"] < 575]
    if not orbc: print(f"{tk:6}{d:12}  NO ORB BAR"); continue
    orb = orbc[0]; hi, lo = orb["h"], orb["l"]
    a = atr14(db, idx)
    wide = bool(a and a>0 and (hi-lo) > 1.5*a)
    zero = (hi-lo) <= 0
    limit = round(max(hi*1.005, hi+0.02), 2)
    fill_m = fill_px = None
    if not wide and not zero:
        armed = False
        for b in rth:
            if b["m"] < max(571, orb["m"]+1): continue
            if b["m"] >= 600: break
            if armed:
                if b["l"] <= limit: fill_px, fill_m = limit, b["m"]; break
                continue
            if b["h"] >= hi:
                if b["o"] <= hi: fill_px, fill_m = hi, b["m"]
                elif b["o"] <= limit: fill_px, fill_m = b["o"], b["m"]
                else: armed = True; continue
                break
    if fill_px is None:
        print(f"{tk:6}{d:12}{hi:>9.3f}{lo:>9.3f}{(a or 0):>8.3f}{('WIDE' if wide else ('ZERO' if zero else 'no')):>7}"
              f"{'-':>8}{'-':>9}{'-':>8}{'-':>9}{'-':>8}{'-':>8}{'-':>9}{'-':>8}{'-':>8}{'-':>9}")
        res.append((tk,d,None)); continue
    R = fill_px - lo
    after = [b for b in rth if b["m"] >= fill_m]
    stop_m = next((b["m"] for b in after if b["l"] <= lo), None)
    r2_m  = next((b["m"] for b in after if b["h"] >= fill_px + 2*R), None)
    r3_m  = next((b["m"] for b in after if b["h"] >= fill_px + 3*R), None)
    fwd = db[idx+1:idx+6]
    stop_d = r2_d = r3_d = None
    for j,b in enumerate(fwd,1):
        if stop_d is None and b["l"] <= lo: stop_d = j
        if r2_d is None and b["h"] >= fill_px+2*R: r2_d = j
        if r3_d is None and b["h"] >= fill_px+3*R: r3_d = j
    mfe = max([b["h"] for b in after] + [b["h"] for b in fwd])
    mfe_r = (mfe - fill_px)/R
    print(f"{tk:6}{d:12}{hi:>9.3f}{lo:>9.3f}{(a or 0):>8.3f}{'no':>7}{fill_m:>8}{fill_px:>9.3f}{R:>8.3f}"
          f"{(stop_m if stop_m else '-'):>9}{(r2_m if r2_m else '-'):>8}{(r3_m if r3_m else '-'):>8}"
          f"{(stop_d if stop_d else '-'):>9}{(r2_d if r2_d else '-'):>8}{(r3_d if r3_d else '-'):>8}{mfe_r:>9.2f}")
    res.append((tk,d,{"stop_m":stop_m,"r2_m":r2_m,"r3_m":r3_m,"stop_d":stop_d,"r2_d":r2_d,"r3_d":r3_d,"mfe_r":mfe_r}))

fills = [r for r in res if r[2]]
print(f"\nFILLED {len(fills)}/{len(res)}")
day0_stop_first = sum(1 for _,_,x in fills if x["stop_m"] is not None and (x["r2_m"] is None or x["stop_m"] <= x["r2_m"]))
print("day-0 stop touched BEFORE +2R (or +2R never on day0):", day0_stop_first, "of", len(fills))
amb = [(t,d,x) for t,d,x in fills if x["stop_m"] is None]
print("no day-0 stop touch (resolved on a forward DAILY bar):", len(amb), [t for t,_,_ in amb])
for t,d,x in fills:
    if x["stop_m"] is None:
        print(f"   {t} {d}: stop_day={x['stop_d']} r2_day={x['r2_d']} r3_day={x['r3_d']} -> SAME-BAR TIE" if x["stop_d"] and x["r2_d"] and x["stop_d"]==x["r2_d"] else f"   {t} {d}: stop_day={x['stop_d']} r2_day={x['r2_d']} r3_day={x['r3_d']}")

# ── ADVERSARIAL VERIFY 2026-09-21 — what this found (read-only; THE LINE holds) ──
# Independently re-derived population + fill set of #577b. 9/18 fills reproduce EXACTLY,
# same 9 names, same stop_too_wide rejections (MXL/WSHP — a REAL live rule,
# order_manager.py:568 -> backtester/filters.py:207).
# ORDER: 8 of 9 stop unambiguously before any +2R; WYHG's fill bar (m=571) opened AT the
# entry, high==entry, low 7.895 < stop 7.9801 -> also unambiguous. 9/9 -1R stands.
# DEFECT FOUND: `ret_5d IS NOT NULL` drops UBXG 2026-07-14 (band 57%, setup_at_open TRUE,
# max_high_5d=+32.2% so forward bars EXIST). It fills, reaches +2.94R BEFORE its stop, and
# pays +0.67R under the 08-16 ladder -> "zero winners under all three ladders" is false.
# This is the 4th method error the 08-29 doc recorded as caught, repeated.
