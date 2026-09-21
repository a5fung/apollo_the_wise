"""ADVERSARIAL RE-RUN of #577b with the ACTUAL live stop (order_manager.py:617,
stop = 2*orb_low - orb_high, live since 2026-08-16, confirmed in prod 2026-08-23).
Read-only. Changes nothing."""
import sys, json
from pathlib import Path
HERE = Path("/Users/alvinfung/apollo_the_wise/scripts/probes")
sys.path.insert(0, str(HERE)); sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
import _468_moderate_realized_r as M

BAND = [l.split("|") for l in (HERE/"_577b_cohort.psv").read_text().splitlines() if l.strip()]
band = [{"ticker":p[0],"alert_date":p[1],"ext":float(p[2]),"ret_5d":float(p[3]),
         "mfe_5d":float(p[4])} for p in BAND if len(p)>=6]

# bars: same merge the review used
def load_bars():
    M.DAILY, M.MINUTE = HERE/"_ext_daily.tsv", HERE/"_ext_minute.tsv"
    daily, minute = M.load_daily(), M.load_minute()
    from datetime import datetime, timedelta, timezone
    for ln in (HERE/"_577b_extra_bars.tsv").read_text().splitlines():
        p = ln.split("\t")
        if len(p) < 8 or p[0].startswith("#"): continue
        if p[0] == "D":
            daily[p[1]].append({"date":p[2],"o":float(p[3]),"h":float(p[4]),"l":float(p[5]),"c":float(p[6]),"v":float(p[7])})
        elif p[0] == "M":
            tms = int(p[2]); et = datetime.fromtimestamp(tms/1000, timezone.utc) - timedelta(hours=4)
            minute[(p[1], et.date().isoformat())].append({"t":tms,"o":float(p[3]),"h":float(p[4]),"l":float(p[5]),"c":float(p[6]),"v":float(p[7])})
    for tk in daily:
        seen, keep = set(), []
        for b in sorted(daily[tk], key=lambda x:x["date"]):
            if b["date"] in seen: continue
            seen.add(b["date"]); keep.append(b)
        daily[tk] = keep
    return daily, minute

def sim(entry, stop0, orb_r, day0_after, fwd, *, partial_r, be_arm_r, frac=1/3, horizon=20):
    """R reported in TRADE-RISK units (entry-stop0) == equal dollar risk.
    partial_r / be_arm_r are in ORB-R (order_manager pins the target frame off entry-orb_low)."""
    risk = entry - stop0
    if risk <= 0: return None
    held, banked, stop = 1.0, 0.0, stop0
    tgt = entry + partial_r*orb_r if partial_r else None
    be  = entry + be_arm_r*orb_r if be_arm_r else None
    for b in day0_after:
        if b["l"] <= stop: return banked + held*(stop-entry)/risk, "stopped_d0"
        if be and b["h"] >= be: stop = max(stop, entry)
        if tgt and held == 1.0 and b["h"] >= tgt:
            banked += frac*(tgt-entry)/risk; held -= frac; stop = max(stop, entry)
    for d in fwd[:horizon]:
        if d["l"] <= stop: return banked + held*(stop-entry)/risk, "stopped"
        if be and d["h"] >= be: stop = max(stop, entry)
        if tgt and held == 1.0 and d["h"] >= tgt:
            banked += frac*(tgt-entry)/risk; held -= frac; stop = max(stop, entry)
    last = (fwd[:horizon][-1]["c"] if fwd[:horizon] else (day0_after[-1]["c"] if day0_after else entry))
    return banked + held*(last-entry)/risk, "open_at_horizon"

daily, minute = load_bars()
rows=[]
for r in band:
    tk, ad = r["ticker"], r["alert_date"]
    db = daily.get(tk, []); i = M.idx_of_date(db, ad); raw = minute.get((tk,ad),[])
    if i is None or not raw: rows.append({**r,"out":"no_bars"}); continue
    rth = M.de.polygon_to_rth_minutes(raw, ad)
    if not rth: rows.append({**r,"out":"no_rth"}); continue
    rec = M.reconstruct(rth, M.SUBMIT_MIN, M.atr14_prior_close(db,i), db[i:])
    if rec.get("outcome") != "filled":
        rows.append({**r,"out":rec.get("outcome")}); continue
    hi, lo, entry = rec["orb_high"], rec["orb_low"], rec["entry"]
    orb_r = entry - lo
    stop_live = 2*lo - hi
    fwd = db[i+1:]; after=[b for b in rth if b["m"]>=rec["fill_minute"]]
    # did the LIVE stop ever get touched?
    lows5 = [b["l"] for b in after] + [d["l"] for d in fwd[:5]]
    lows20 = [b["l"] for b in after] + [d["l"] for d in fwd[:20]]
    hit5 = min(lows5) <= stop_live if lows5 else None
    hit20 = min(lows20) <= stop_live if lows20 else None
    plain = sim(entry, stop_live, orb_r, after, fwd, partial_r=None, be_arm_r=None)
    erad  = sim(entry, stop_live, orb_r, after, fwd, partial_r=8.0, be_arm_r=3.0)
    erac  = sim(entry, stop_live, orb_r, after, fwd, partial_r=2.0, be_arm_r=None)
    rows.append({**r,"out":"filled","entry":entry,"orb_low":lo,"orb_hi":hi,
                 "stop_live":stop_live,"stop_oldera":lo,
                 "hit_live_stop_5d":hit5,"hit_live_stop_20d":hit20,
                 "plain":plain[0],"plain_end":plain[1],
                 "erad":erad[0],"erad_end":erad[1],"erac":erac[0],"erac_end":erac[1]})

f=[r for r in rows if r["out"]=="filled"]
print(f"band n={len(band)}  filled={len(f)}  (fill rule unchanged)")
print(f"{'tk':7}{'date':12}{'entry':>8}{'orbLo':>8}{'LIVEstop':>9}{'hit5d':>7}{'hit20d':>7}{'plain':>8}{'eraD':>8}{'eraC':>8}  end")
for r in sorted(f,key=lambda x:x['alert_date']):
    print(f"{r['ticker']:7}{r['alert_date']:12}{r['entry']:>8.2f}{r['orb_low']:>8.2f}{r['stop_live']:>9.2f}"
          f"{str(r['hit_live_stop_5d']):>7}{str(r['hit_live_stop_20d']):>7}"
          f"{r['plain']:>+8.2f}{r['erad']:>+8.2f}{r['erac']:>+8.2f}  {r['erad_end']}")
for k,lbl in (("plain","no ladder, hard 2R stop"),("erad","era D LIVE 1/3@+8 ORB-R, BE arms +3 ORB-R"),("erac","era C 1/3@+2 ORB-R, BE at partial")):
    v=[r[k] for r in f]
    print(f"{lbl:46} n={len(v)} mean {sum(v)/len(v):+.2f} median {sorted(v)[len(v)//2]:+.2f} best {max(v):+.2f} SUM {sum(v):+.1f} winners {sum(1 for x in v if x>0)}/{len(v)}")
print("stop TOUCHED within 5d:", sum(1 for r in f if r['hit_live_stop_5d']), "/", len(f),
      "  within 20d:", sum(1 for r in f if r['hit_live_stop_20d']), "/", len(f))
