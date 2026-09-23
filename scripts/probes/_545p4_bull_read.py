#!/usr/bin/env python3
"""exit_tune_bull_regime_read — run 1 at stamped-Bull n=10 (2026-09-02). OFFLINE, $0.

Reads ONLY the committed 09-01 capture (scripts/ep_replay_data/_pull2_out.txt + _pull4_min.tsv.gz):
26 closed live magna53 trades, exit legs, mi_market_regime, daily OHLC, alert-day RTH minute bars.
Writes _545p4_bull_read_out.txt beside itself. Doc: docs/analysis/exit_tune_bull_regime_read_2026-09-02.md.

NOT a new replay harness (v2 design doc §5: one owner per cell). The 34-candidate grid stays on
_508_exit_rule_replay.py, which needs the snapshot _545p4_bull_capture.sql produces. What this does
that needs no engine: the regime-stamp rule check, R on three bases, the partial priced on real exit
legs (hold-all-to-the-same-terminal), MFE from bars + in-hold daily highs, holding period, ADR20
tiers, and the floored-stop day-0 walk (minute) + forward touch/no-touch (daily) — the latter is
calibrated by reproducing the 08-06 stop-floor result (-14.00R, 0 wins) on the non-Bull 14.

Evidence only. THE LINE: nothing here changes a rule.
Run:  python3 scripts/probes/_545p4_bull_read.py
"""
from __future__ import annotations
import gzip, json, statistics
from collections import defaultdict, Counter
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
P2 = REPO / "scripts/ep_replay_data/_pull2_out.txt"
P4 = REPO / "scripts/ep_replay_data/_pull4_min.tsv.gz"

# ── parse the 09-01 capture ───────────────────────────────────────────────────
lines = P2.read_text().splitlines()
sec = {}
cur = None
for ln in lines:
    if ln.startswith("=== "):
        cur = ln.strip("= ").strip(); sec[cur] = []; continue
    if cur and ln and not ln.startswith("(") :
        sec[cur].append(ln)

def table(name):
    rows = sec[name]
    hdr = rows[0].split("|")
    return [dict(zip(hdr, r.split("|"))) for r in rows[1:]]

trades = [t for t in table("TRADES") if t["account_mode"] == "live"]
regime = {date.fromisoformat(r["regime_date"]): r["regime"] for r in table("REGIME")}
regime_dates = sorted(regime)
daily = defaultdict(dict)
for r in table("DAILY"):
    daily[r["ticker"]][date.fromisoformat(r["trade_date"])] = (
        float(r["open_price"]), float(r["high_price"]), float(r["low_price"]), float(r["close"]))

minute = defaultdict(list)   # (ticker, date) -> [(et_min, o,h,l,c)]
with gzip.open(P4, "rt") as fh:
    for ln in fh:
        if ln.startswith("===") or ln.startswith("ticker|"): continue
        p = ln.rstrip("\n").split("|")
        if len(p) < 7: continue
        d = date.fromisoformat(p[1][:10])
        minute[(p[0], d)].append((p[1][11:16], float(p[2]), float(p[3]), float(p[4]), float(p[5])))

def f(x):
    return None if x in ("", None) else float(x)

# stamps already known from prior docs/captures (validation set for the lag rule)
KNOWN = {"WULF":"Choppy","CRCL":"Choppy","WDFC":"Choppy","MANE":"Choppy","BLZE":"Choppy","BTDR":"Choppy",
         "TSEM":"Correcting","HUT":"Correcting","SMCI":"Correcting","NVCR":"Correcting","THC":"Correcting",
         "WKC":"Correcting","QBTS":"Correcting","FTNT":"Crisis",
         "NET":"Bull","FIGS":"Bull","TEAM":"Bull","FRMI":"Bull","BW":"Bull","ETON":"Bull",
         "PLTR":"Choppy","MRVL":"Bull"}
# recorder peaks from prior captures/docs (R units on the realized per-share basis unless price)
REC_PEAK_PRICE = {"PLTR": 180.18, "ETON": 59.79}                     # 08-24 capture highest_price_seen
REC_PEAK_R = {"NET":1.68,"FIGS":2.90,"TEAM":1.08,"FRMI":0.0,"BW":0.0,"MRVL":0.35,   # 08-17 / 08-22 docs
              "MANE":7.92,"QBTS":3.74,"SMCI":3.21,"NVCR":2.00,"CRCL":1.62,"HUT":0.0,"TSEM":0.0,
              "THC":0.64,"WKC":0.90,"FTNT":0.07}

ERA_B = date(2026,8,5); ERA_C = date(2026,8,17)

def era_of(d):
    return "C" if d >= ERA_C else ("B" if d >= ERA_B else "A")

def adr20(tk, alert):
    pre = [v for d, v in sorted(daily[tk].items()) if d < alert][-20:]
    return statistics.mean((h-l)/c*100 for o,h,l,c in pre) if len(pre) >= 10 else None

def trading_days(tk, a, b):
    return [d for d in sorted(daily[tk]) if a <= d <= b]

rows = []
for t in trades:
    tk = t["ticker"]; alert = date.fromisoformat(t["alert_date"])
    filled = datetime.fromisoformat(t["filled_at_et"]); closed = datetime.fromisoformat(t["closed_at_et"])
    fd, cd = filled.date(), closed.date()
    entry = f(t["entry_price"]); sh = f(t["entry_shares"]); hs = f(t["hard_stop"])
    oh, ol = f(t["orb_high"]), f(t["orb_low"]); pnl = f(t["total_pnl"])
    rd, rda = f(t["risk_dollars"]), f(t["risk_dollars_actual"])
    legs = json.loads(t["exits_json"])
    for lg in legs:
        lg["_t"] = lg.get("time") or lg.get("at"); lg["_sh"] = float(lg.get("shares", lg.get("qty", 0)) or 0)
    legs.sort(key=lambda l: l["_t"])
    # stamp rule: latest regime row strictly BEFORE the fill day (today's row is written 17:00 ET)
    prev = max(d for d in regime_dates if d < fd)
    stamp = regime[prev]; join = regime.get(fd)
    rps = entry - hs                       # realized per-share risk (the recorder's unit)
    r_real = pnl / (sh * rps)
    r_plan = pnl / (sh * (oh - hs))        # = risk_dollars_actual reconstructed
    r_budget = pnl / (rda if rda else rd)  # the brief's COALESCE recipe
    a = adr20(tk, alert)
    stop_pct = rps / entry * 100
    # MFE reconstruction
    fill_min = filled.strftime("%H:%M")
    bars = minute.get((tk, fd), [])
    close_min = closed.strftime("%H:%M") if cd == fd else "16:00"
    after = [b for b in bars if fill_min < b[0] < close_min]
    d0_high = max((b[2] for b in after), default=None)
    mids = [daily[tk][d][1] for d in trading_days(tk, fd, cd) if fd < d < cd]
    term = legs[-1]["price"]; parts = [l["price"] for l in legs if l["reason"] == "partial_profit"]
    cands = [x for x in [d0_high] + mids + [term] + parts if x is not None]
    peak_bar = max(cands)
    peak_src = "bars" if (cd == fd or (peak_bar == d0_high)) else ("daily_mid" if peak_bar in mids else "leg_floor")
    rec_peak = REC_PEAK_PRICE.get(tk, entry + REC_PEAK_R[tk]*rps if tk in REC_PEAK_R else None)
    peak = max(peak_bar, rec_peak) if rec_peak else peak_bar
    hold = len(trading_days(tk, fd, cd))
    # partial arithmetic: hold ALL shares to the terminal leg price
    if tk == "ETON":
        term_hold = [l for l in legs if l["reason"] == "stop_hit"][-1]["price"]
    else:
        term_hold = term
    pnl_hold = sh * (term_hold - entry)
    rows.append(dict(tk=tk, id=int(t["id"]), alert=alert, fd=fd, cd=cd, era=era_of(fd), stamp=stamp, join=join,
                     known=KNOWN.get(tk), entry=entry, sh=sh, hs=hs, oh=oh, ol=ol, pnl=pnl, rd=rd, rda=rda,
                     rps=rps, r_real=r_real, r_plan=r_plan, r_budget=r_budget, adr=a, stop_pct=stop_pct,
                     stop_adr=stop_pct/a if a else None, peak=peak, peak_r=(peak-entry)/rps,
                     peak_adr=((peak-entry)/entry*100)/a if a else None, peak_src=peak_src,
                     rec_peak_r=((rec_peak-entry)/rps) if rec_peak else None, hold=hold, day0=(fd==cd),
                     partial=(t["partial_taken"]=="t"), legs=legs, term=term, pnl_hold=pnl_hold,
                     r_hold=pnl_hold/(sh*rps), exit_reason=legs[-1]["reason"],
                     stop_final=f(t["stop_price"]), fill_min=fill_min, mins=(closed-filled).total_seconds()/60))

rows.sort(key=lambda r: (r["fd"], r["tk"]))
out = []
P = out.append

P("=== 0. STAMP RULE VALIDATION (stamp = latest regime row strictly before the fill day) ===")
ok = 0; tot = 0
for r in rows:
    if r["known"]:
        tot += 1; ok += (r["known"] == r["stamp"])
        if r["known"] != r["stamp"]: P(f"  MISMATCH {r['tk']} known {r['known']} rule {r['stamp']}")
P(f"  known stamps reproduced: {ok}/{tot}")
P("  inferred (no prior record): " + ", ".join(f"{r['tk']}={r['stamp']}" for r in rows if not r["known"]))
P("  stamp counts: " + str(dict(Counter(r["stamp"] for r in rows))))
P("  join  counts: " + str(dict(Counter(r["join"] for r in rows))))
P("  disagreements (stamp -> join): " + ", ".join(f"{r['tk']} {r['fd']} {r['stamp']}->{r['join']}" for r in rows if r["stamp"] != r["join"]))

P("\n=== 1. BRIEF FACT CHECK (26 closed live) ===")
P(f"  n={len(rows)}  winners={sum(1 for r in rows if r['pnl']>0)}  cash={sum(r['pnl'] for r in rows):+.2f}")
for k in ("r_real","r_plan","r_budget"):
    b = max(rows, key=lambda r: r[k]); w = min(rows, key=lambda r: r[k])
    P(f"  {k:<9} sum {sum(r[k] for r in rows):+.2f}  best {b['tk']} {b[k]:+.2f}  worst {w['tk']} {w[k]:+.2f}  >=4R: {sum(1 for r in rows if r[k]>=4)}")
P("  capped rows where the BUDGET basis misstates a full stop-out (r_real <= -0.95 but r_budget > -0.6): "
  + ", ".join(f"{r['tk']} real {r['r_real']:+.2f} budget {r['r_budget']:+.2f}" for r in rows if r["r_real"] <= -0.95 and r["r_budget"] > -0.6))
P("  risk_dollars_actual reconstruction check: " + ", ".join(f"{r['tk']} col {r['rda']} vs sh*(orb_high-hard_stop) {r['sh']*(r['oh']-r['hs']):.2f}" for r in rows if r["rda"]))

P("\n=== 2. PER-TRADE FORENSIC (a) — all 26, sorted by fill ===")
P(f"  {'tkr':<5}{'fill':<7}{'era':<4}{'stamp':<11}{'join':<11}{'entry':>8}{'stop':>8}{'stop%':>6}{'s/ADR':>6}{'ADR%':>5}{'R_real':>7}{'R_bud':>7}{'peakR':>7}{'pkADR':>6}{'src':<10}{'hold':>5}{'d0':>3}{'part':>5}  exit")
for r in rows:
    P(f"  {r['tk']:<5}{r['fd'].strftime('%m-%d'):<7}{r['era']:<4}{r['stamp']:<11}{r['join']:<11}{r['entry']:>8.2f}{r['hs']:>8.2f}{r['stop_pct']:>6.1f}{r['stop_adr']:>6.2f}{r['adr']:>5.1f}{r['r_real']:>7.2f}{r['r_budget']:>7.2f}{r['peak_r']:>7.2f}{r['peak_adr']:>6.2f}{r['peak_src']:<10}{r['hold']:>5}{'Y' if r['day0'] else '':>3}{'Y' if r['partial'] else '':>5}  {r['exit_reason']} ({r['mins']:.0f}m)")

def cell(label, sub):
    n = len(sub)
    if n == 0: P(f"  {label:<34} n=0"); return
    rr = [r["r_real"] for r in sub]; pk = [r["peak_r"] for r in sub]; pa = [r["peak_adr"] for r in sub if r["peak_adr"] is not None]
    hd = [r["hold"] for r in sub]
    P(f"  {label:<34} n={n:<3} sumR {sum(rr):+6.2f} meanR {sum(rr)/n:+5.2f} medR {statistics.median(rr):+5.2f} wins {sum(1 for x in rr if x>0)}/{n} "
      f"day0 {sum(1 for r in sub if r['day0'])}/{n} hold med {statistics.median(hd):.0f}d max {max(hd)}d | peakR mean {sum(pk)/n:+.2f} max {max(pk):+.2f} >=2R {sum(1 for x in pk if x>=2)} >=4R {sum(1 for x in pk if x>=4)} | peakADR med {statistics.median(pa):.2f} >=1.5ADR {sum(1 for x in pa if x>=1.5)}")
    P(f"  {'':<34} eras {dict(sorted(Counter(r['era'] for r in sub).items()))}  " + " ".join(f"{r['tk']}{r['r_real']:+.2f}" for r in sub))

P("\n=== 3. REGIME CELLS (c0) — ENTRY-STAMPED, realized per-share R ===")
bull = [r for r in rows if r["stamp"]=="Bull"]; nonb = [r for r in rows if r["stamp"]!="Bull"]
cell("Bull (stamped)", bull); cell("non-Bull (stamped)", nonb)
for rg in ("Choppy","Correcting","Crisis"): cell(f"  {rg}", [r for r in rows if r["stamp"]==rg])
P("  -- era inside each cell --")
for e in "ABC":
    cell(f"Bull era {e}", [r for r in bull if r["era"]==e]); cell(f"non-Bull era {e}", [r for r in nonb if r["era"]==e])
P("  -- era-A non-bull excl PLTR (the 08-06 baseline) --")
cell("non-Bull era A excl PLTR", [r for r in nonb if r["era"]=="A" and r["tk"]!="PLTR"])
P("  -- sensitivity: DATE-JOIN basis --")
cell("Bull (date-join)", [r for r in rows if r["join"]=="Bull"]); cell("non-Bull (date-join)", [r for r in rows if r["join"]!="Bull"])

P("\n=== 4. THE PARTIAL, PRICED ON REAL FILLS (b) — every trade whose partial fired live ===")
P(f"  {'tkr':<5}{'stamp':<11}{'era':<4}{'peakR':>7}{'actualR':>8}{'holdAllR':>9}{'partial_effect':>15}  legs")
for r in rows:
    if r["partial"] or r["tk"] in ("PLTR",):
        eff = r["r_real"] - r["r_hold"]
        legs = "; ".join(f"{l['reason']}@{l['price']}x{l['_sh']:.0f}" for l in r["legs"])
        P(f"  {r['tk']:<5}{r['stamp']:<11}{r['era']:<4}{r['peak_r']:>7.2f}{r['r_real']:>8.2f}{r['r_hold']:>9.2f}{eff:>+15.2f}  {legs}")
P("  holdAllR = every share exits at the SAME terminal leg price (the trailed stop / the stop) — the partial's exact cost or benefit, no sim.")
P("  ETON: terminal for hold-all = the 55.05 stop_hit leg; its 59.58 'partial' was the #566 defect fill six hours after the position was flat.")

P("\n=== 5. RUNNERS (peak >= +2R) by cell — what each stack kept ===")
for r in sorted(rows, key=lambda r: -r["peak_r"]):
    if r["peak_r"] >= 2:
        P(f"  {r['tk']:<5} {r['stamp']:<11} era {r['era']} peak {r['peak_r']:+.2f}R ({r['peak_adr']:.2f} ADR) kept {r['r_real']:+.2f}R capture {r['r_real']/r['peak_r']*100:+.0f}%  src={r['peak_src']}")

P("\n=== 6. HOLDING PERIOD (d) ===")
for label, sub in (("Bull", bull), ("non-Bull", nonb)):
    hc = Counter(r["hold"] for r in sub)
    P(f"  {label:<9} " + " ".join(f"{k}d×{v}" for k,v in sorted(hc.items())) + f"   day0 exits {sum(1 for r in sub if r['day0'])}/{len(sub)}   <10min {sum(1 for r in sub if r['mins']<10)}/{len(sub)}")

P("\n=== 7. CHARACTER (c) — ADR20 tiers, Bull vs non-Bull ===")
for lo, hi, lab in ((0,3.5,"slow <3.5%"),(3.5,6.5,"mid 3.5-6.5%"),(6.5,99,"fast >6.5%")):
    for label, sub in (("Bull", bull), ("non-Bull", nonb)):
        cell(f"{lab} {label}", [r for r in sub if r["adr"] is not None and lo <= r["adr"] < hi])

P("\n=== 8. STOP GEOMETRY (e) — width vs ADR20; floored-stop DAY-0 survival on the Bull ORB-low trades ===")
for label, sub in (("Bull ORB-low (era B)", [r for r in bull if r["era"]=="B"]), ("non-Bull ORB-low (era A)", [r for r in nonb if r["era"]=="A"]), ("Bull 2R-stop (era C)", [r for r in bull if r["era"]=="C"]), ("non-Bull 2R-stop (era C)", [r for r in nonb if r["era"]=="C"])):
    v = sorted(r["stop_adr"] for r in sub)
    if v: P(f"  {label:<26} n={len(v)} stop/ADR min {v[0]:.2f} med {statistics.median(v):.2f} max {v[-1]:.2f}  <1.0: {sum(1 for x in v if x<1)}/{len(v)}")

def day0_walk(r, stop):
    bars = minute.get((r["tk"], r["fd"]), [])
    for b in bars:
        if b[0] < r["fill_min"]: continue
        if b[0] == r["fill_min"]:
            if b[4] <= stop: return b[0]
            continue
        if b[3] <= stop: return b[0]
    return None

def fwd_touch(r, stop):
    days = [d for d in sorted(daily[r["tk"]]) if d > r["fd"]][:10]
    for i, d in enumerate(days, 1):
        if daily[r["tk"]][d][2] <= stop: return i, d
    return None, days[-1] if days else None

P("  floored stop = min(hard_stop, entry*(1-k*ADR20/100)) — may only WIDEN. Day 0 on minute bars (fill bar needs a CLOSE below); forward = first session whose daily low <= stop (floor alone, partial off), else session-10 close.")
for r in [x for x in bull if x["era"]=="B"]:
    line = f"  {r['tk']:<5} entry {r['entry']:.2f} ORB-low stop {r['hs']:.2f} ({r['stop_adr']:.2f} ADR) actual {r['r_real']:+.2f}R |"
    for k in (0.5, 0.75, 1.0):
        sk = min(r["hs"], r["entry"]*(1-k*r["adr"]/100)); ru = r["entry"]-sk
        d0 = day0_walk(r, sk)
        if d0: line += f" k{k}: d0 stop {d0}"
        else:
            i, d = fwd_touch(r, sk)
            if i: line += f" k{k}: survives d0, stopped s{i}"
            else:
                c10 = daily[r["tk"]][d][3] if d else None
                line += f" k{k}: survives d0, s10 close {((c10-r['entry'])/ru):+.2f}R(k-unit)" if c10 else f" k{k}: survives, unsettled"
    P(line)

def floor_sweep(label, sub):
    P(f"  -- {label} n={len(sub)}: floor ALONE (partial off), R in the WIDENED unit; exit = stop or session-10 close --")
    for k in (0.0, 0.5, 0.75, 1.0):
        tot = 0.0; d0s = 0; later = 0; wins = 0; det = []
        for r in sub:
            sk = min(r["hs"], r["entry"]*(1-k*r["adr"]/100)); ru = r["entry"]-sk
            if day0_walk(r, sk): rr = -1.0; d0s += 1; tag = "d0"
            else:
                i, d = fwd_touch(r, sk)
                if i: rr = -1.0; later += 1; tag = f"s{i}"
                else:
                    rr = (daily[r["tk"]][d][3]-r["entry"])/ru; tag = "s10"
            tot += rr; wins += rr > 0; det.append(f"{r['tk']}{rr:+.2f}({tag})")
        P(f"    k={k:<4} sumR {tot:+6.2f}  wins {wins}/{len(sub)}  day0-stops {d0s}  later-stops {later}   " + " ".join(det))
floor_sweep("Bull ORB-low era B", [x for x in bull if x["era"]=="B"])
floor_sweep("non-Bull ORB-low era A excl PLTR (08-06 calibration set)", [x for x in nonb if x["era"]=="A" and x["tk"]!="PLTR"])
P("  daily closes, sanity: " + " | ".join(f"{tk} " + " ".join(f"{d.strftime('%m-%d')}:{daily[tk][d][3]:.2f}" for d in [dd for dd in sorted(daily[tk]) if dd >= date(2026,8,7)][:12]) for tk in ("TEAM","ABCL","ETON")))

P("\n=== 9. THE ERA-C MATCHED CELL (the only era-clean contrast) ===")
for r in [x for x in rows if x["era"]=="C"]:
    P(f"  {r['tk']:<5} stamp {r['stamp']:<10} join {r['join']:<10} R {r['r_real']:+.2f} peak {r['peak_r']:+.2f}R ({r['peak_adr']:.2f} ADR) hold {r['hold']}d stop/ADR {r['stop_adr']:.2f} exit {r['exit_reason']}")

Path(__file__).with_name("_545p4_bull_read_out.txt").write_text("\n".join(out))
print("\n".join(out))
