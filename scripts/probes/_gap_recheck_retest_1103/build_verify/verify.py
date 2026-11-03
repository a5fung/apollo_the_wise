#!/usr/bin/env python3
"""BLIND verifier — gap re-check retest (2026-11-03). Offline, $0, reads only the capture .out.

Written from the live code (agents/market_intelligence/broker/{order_manager,entry_pipeline,
live_tracker,exit_logic}.py) WITHOUT reading the builder's retest.py.

Conventions (stated, not hidden):
  E1 ORB = the 09:30 minute bar. stop = 2*L - H. planned risk = H - stop. ORB-R = entry - L.
  E2 live price at 09:31 = the 'last $X' in the stored skip text (main) | 09:30 close (sensitivity).
  E3 _pick_entry: live > H -> limit buy at round(live*1.002, 2), chase cap (limit-stop) <= 1.5*(H-stop);
     else stop-limit trigger H, limit max(H*1.005, H+0.02) rounded 2.
  E4 walk minute bars 09:32..09:59 (10:00 ET cancel). Sensitivity: start at 09:31.
     stop-limit: first bar with high >= H. Fill = max(open, H) if <= limit; else if low <= limit -> limit;
       else triggered-not-filled, keep walking for a bar with low <= limit (fill at min(open,limit)).
     limit: first bar with low <= limit, fill = min(open, limit).
  E5 ATR14 = mean of last 14 Wilder TRs over DAILY rows in [d-35, d) (the 09:31 live path has only prior days).
  X1 day 0: after the fill bar, minute bars: stop if low <= stop (fill at min(open, stop));
     BE arm if high >= entry + 3*(entry-L) -> stop to entry; +8 ORB-R partial (1/3) if high >= entry+8*(entry-L).
     The fill bar itself: events in it are ambiguous -> flagged.
     No close decision on day 0 (16:45 job skips today <= alert_date).
  X2 sessions j>=1 (DAILY only): open <= resting stop -> fill at open (gap). Else, with one daily bar the order of
     high-side events (BE arm, 8R) vs low-side (stop / entry) is unknown -> ABSTAIN when it matters.
     Close: line = max(SMA10,SMA20) on prior closes (dates < d, 40 cal days) + held closes 1..j (entry-day close
     excluded, as live). Arming (trail_arm_on_close_above): entry >= line(prior) OR entry-day close >= its own line
     OR some held close >= its line. eff = max(hard, line if armed, entry if BE). close < eff -> sell next open.
     Else resting stop = depth_stop_price(line=eff, hard, entry, BE, ADR20) raise-only.
  R = (exit - entry) / planned risk (budget R). Horizon 20 sessions.
"""
import math, re, sys, statistics
from datetime import date, timedelta

CAP = "/Users/alvinfung/apollo_the_wise/scripts/probes/_gap_recheck_retest_1103/capture/c1_c2.out"
S715 = "/Users/alvinfung/apollo_the_wise/scripts/probes/_715_study_1031/s2_rows.tsv"

def D(s): return date.fromisoformat(s)

def read():
    sec = None; hdr = {}; rows = {"POP": [], "MIN": [], "DAILY": [], "COUNTS": []}
    for line in open(CAP):
        line = line.rstrip("\n")
        m = re.match(r"^=== (\w+) ===$", line)
        if m: sec = m.group(1); hdr[sec] = None; continue
        if sec is None or "|" not in line: continue
        parts = line.split("|")
        if hdr[sec] is None: hdr[sec] = parts; continue
        if len(parts) != len(hdr[sec]):
            print("FIELD MISMATCH", sec, line[:80]); continue
        rows[sec].append(dict(zip(hdr[sec], parts)))
    return rows

R = read()
print(f"sections: POP={len(R['POP'])} MIN={len(R['MIN'])} DAILY={len(R['DAILY'])} COUNTS={R['COUNTS']}")
pop_all = R["POP"]
f = lambda x: float(x) if x not in ("", None) else None

mins = {}
for r in R["MIN"]:
    mins.setdefault((r["ticker"], r["d"]), []).append(r)
daily = {}
for r in R["DAILY"]:
    daily.setdefault(r["ticker"], []).append(
        dict(d=D(r["trade_date"]), o=f(r["open_price"]), h=f(r["high_price"]), l=f(r["low_price"]), c=f(r["close"])))
for t in daily: daily[t].sort(key=lambda b: b["d"])

# ---------------- population ----------------
print("\n=== POPULATION ===")
print("stored fates:", sorted({(r['status'], (r['skip_reason'].split(':')[0] + ':' + r['skip_reason'].split(':')[1]) if ':' in r['skip_reason'] else r['skip_reason']) for r in pop_all}))
pop = [r for r in pop_all if r["skip_reason"].startswith("setup:gap_below_floor")]
print(f"n={len(pop)}:", ", ".join(f"{r['ticker']} {r['d']}" for r in pop))
print("all live/magna53 lane:", {r['account_mode'] for r in pop})
print("flip-up rows:", {r['ticker']: int(r['flip_up_rows']) for r in pop})
print("first alert ET:", {r['ticker']: r['first_alert_et'] for r in pop}, "all pre-open:", all(r['first_alert_et'] < '09:30' for r in pop))
s715 = set()
for i, line in enumerate(open(S715)):
    if i == 0: continue
    p = line.split("\t"); s715.add((p[1], p[0]))
print(f"10-31 study rows: {len(s715)}; overlap:", [r['ticker'] for r in pop if (r['ticker'], r['d']) in s715])
print("MIN bars per pop name:", {r['ticker']: len(mins.get((r['ticker'], r['d']), [])) for r in pop})
# per-ticker-day multiplicity
from collections import Counter
cnt = Counter((r['ticker'], r['d']) for r in pop_all)
print("ticker-days with >1 trade row:", [k for k, v in cnt.items() if v > 1])

# ---------------- helpers ----------------
def sma_line(closes):
    s10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else None
    s20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
    if s20 is not None: return s10 if s10 > s20 else s20
    return s10

def armed(prior, held, entry, entry_day_close):
    el = sma_line(prior)
    if entry and el is not None and entry >= el: return True
    if entry_day_close is not None:
        ln = sma_line(prior + [entry_day_close])
        if ln is not None and entry_day_close >= ln: return True
    for j, c in enumerate(held):
        ln = sma_line(prior + held[: j + 1])
        if ln is not None and c >= ln: return True
    return False

def depth_stop(line, hard, entry, be, adr):
    floor = max(hard, entry) if (be and entry) else hard
    ln = max(line, floor) if line is not None else floor
    line_r = round(ln, 2)
    gov = line_r > round(floor, 2) + 1e-9
    if gov and adr: return max(round(floor, 2), round(line_r - 1.0 * adr * line_r, 2))
    return round(floor, 2)

def atr14(t, d):
    rows = [b for b in daily[t] if d - timedelta(days=35) <= b["d"] < d]
    if len(rows) < 10: return None, len(rows)
    trs = [max(rows[i]["h"] - rows[i]["l"], abs(rows[i]["h"] - rows[i - 1]["c"]), abs(rows[i]["l"] - rows[i - 1]["c"])) for i in range(1, len(rows))]
    w = trs[-14:]; return sum(w) / len(w), len(rows)

def prior_bars(t, d):
    return [b for b in daily[t] if d - timedelta(days=40) <= b["d"] < d]

def adr20(pb):
    vals = [(b["h"] - b["l"]) / b["c"] for b in pb[-20:] if b["c"]]
    return sum(vals) / len(vals) if len(vals) >= 10 else None

def stop_limit_px(h): return round(max(h * 1.005, h + 0.02), 2)

def entry_walk(bars, H, L, live, start):
    stop = 2 * L - H; planned = H - stop
    if live is not None and live > H:
        lim = round(live * 1.002, 2)
        ratio = (lim - stop) / planned
        if ratio > 1.5: return dict(kind="chase_cap_skip", ratio=ratio, lim=lim)
        for b in bars:
            if b["hhmm"] < start or b["hhmm"] >= "10:00": continue
            if b["l"] <= lim: return dict(kind="limit", fill=min(b["o"], lim), minute=b["hhmm"], lim=lim, ratio=ratio, stop=stop)
        return dict(kind="limit_no_fill", lim=lim, ratio=ratio)
    lim = stop_limit_px(H); trig = False
    for b in bars:
        if b["hhmm"] < start or b["hhmm"] >= "10:00": continue
        if not trig and b["h"] >= H:
            trig = True; px = max(b["o"], H)
            if px <= lim: return dict(kind="stop_limit", fill=px, minute=b["hhmm"], lim=lim, stop=stop)
            if b["l"] <= lim: return dict(kind="stop_limit", fill=lim, minute=b["hhmm"], lim=lim, stop=stop, note="opened above limit")
            continue
        if trig and b["l"] <= lim: return dict(kind="stop_limit", fill=min(b["o"], lim), minute=b["hhmm"], lim=lim, stop=stop, note="late fill after trigger")
    return dict(kind="no_entry_triggered_unfilled" if trig else "never_crossed_orb_high", lim=lim)

def exit_walk(t, d, bars, ent, H, L, horizon=20, use_arming=True, arm_from=None, partial8=True):
    """Return dict(status, R, detail). arm_from: date from which arming applies (None=always if use_arming)."""
    entry = ent["fill"]; stop = 2 * L - H; planned = H - stop; orb_r = entry - L
    be_lvl = entry + 3 * orb_r; t8 = entry + 8 * orb_r
    log = []; be = False; rest = stop; rem = 1.0; realized = 0.0; partial = False
    amb = []
    after = [b for b in bars if b["hhmm"] > ent["minute"]]
    fb = [b for b in bars if b["hhmm"] == ent["minute"]][0]
    # fill-bar ambiguity
    if fb["l"] <= stop: amb.append(f"fill bar {ent['minute']} low {fb['l']} <= stop")
    if fb["h"] >= be_lvl: amb.append(f"fill bar high {fb['h']} >= BE {be_lvl:.2f}")
    for b in after:
        if b["l"] <= rest:
            px = min(b["o"], rest)
            realized += rem * (px - entry); rem = 0
            log.append(f"d0 {b['hhmm']} stop {px:.2f}{' (BE)' if be else ''}")
            return dict(status="settled", R=realized / planned, exit=px, detail="; ".join(log), sess=0, reason="stop_hit", amb=amb, be_lvl=be_lvl, t8=t8)
        if partial8 and not partial and b["h"] >= t8:
            realized += rem / 3 * (t8 - entry); rem *= 2 / 3; partial = True; log.append(f"d0 {b['hhmm']} 8R third {t8:.2f}")
        if not be and b["h"] >= be_lvl:
            be = True; rest = max(rest, entry); log.append(f"d0 {b['hhmm']} BE armed (high {b['h']})")
    entry_day_close = bars[-1]["c"] if bars and bars[-1]["hhmm"] >= "15:59" else None
    pb = prior_bars(t, d); prior = [b["c"] for b in pb]; adr = adr20(pb)
    fwd = [b for b in daily[t] if b["d"] > d]
    held = []; sell_next = False
    for j, b in enumerate(fwd[:horizon + 1], start=1):
        if sell_next:
            px = b["o"]; realized += rem * (px - entry); rem = 0
            log.append(f"s{j} {b['d']} depth sale at open {px:.2f}")
            return dict(status="settled", R=realized / planned, exit=px, detail="; ".join(log), sess=j, reason="depth_next_open", amb=amb, be_lvl=be_lvl, t8=t8)
        if j > horizon: break
        if b["o"] <= rest:
            px = b["o"]; realized += rem * (px - entry); rem = 0
            log.append(f"s{j} {b['d']} GAP stop at open {px:.2f} (rest {rest:.2f})")
            return dict(status="settled", R=realized / planned, exit=px, detail="; ".join(log), sess=j, reason="stop_hit_gap", amb=amb, be_lvl=be_lvl, t8=t8)
        hi_ev = (not be and b["h"] >= be_lvl) or (partial8 and not partial and b["h"] >= t8)
        lo_stop = b["l"] <= rest
        if hi_ev and lo_stop:
            return dict(status="abstain", R=None, detail="; ".join(log) + f"; s{j} {b['d']} high-side event and stop {rest:.2f} same bar", sess=j, amb=amb, be_lvl=be_lvl, t8=t8)
        if lo_stop:
            px = rest; realized += rem * (px - entry); rem = 0
            log.append(f"s{j} {b['d']} stop {px:.2f}")
            return dict(status="settled", R=realized / planned, exit=px, detail="; ".join(log), sess=j, reason="stop_hit", amb=amb, be_lvl=be_lvl, t8=t8)
        if hi_ev:
            # BE arm then possible touch of entry in the same bar -> ambiguous
            if not be and b["h"] >= be_lvl and b["l"] <= entry:
                return dict(status="abstain", R=None, detail="; ".join(log) + f"; s{j} {b['d']} BE trigger {be_lvl:.2f} and low {b['l']} <= entry {entry:.2f} same bar (o/h/l/c {b['o']}/{b['h']}/{b['l']}/{b['c']})", sess=j, amb=amb, be_lvl=be_lvl, t8=t8)
            if partial8 and not partial and b["h"] >= t8:
                realized += rem / 3 * (t8 - entry); rem *= 2 / 3; partial = True; log.append(f"s{j} 8R third {t8:.2f}")
            if not be and b["h"] >= be_lvl:
                be = True; rest = max(rest, entry); log.append(f"s{j} BE armed")
        held.append(b["c"])
        line = sma_line(prior + held)
        is_armed = armed(prior, held, entry, entry_day_close) if (use_arming and (arm_from is None or b["d"] >= arm_from)) else (True)
        act = line if (line is not None and is_armed) else None
        eff = stop
        if act and act > eff: eff = act
        if be and entry > eff: eff = entry
        if b["c"] < eff:
            sell_next = True; log.append(f"s{j} {b['d']} close {b['c']} < eff {eff:.2f} (line {line}, armed {is_armed}) -> sell next open")
            continue
        ds = depth_stop(eff, stop, entry, be, adr)
        if ds > rest + 1e-9: rest = ds
    last = fwd[min(len(fwd), horizon) - 1] if fwd else None
    mark = realized + rem * ((last["c"] if last else bars[-1]["c"]) - entry)
    return dict(status="open" if not sell_next else "pending_next_open", R=mark / planned, detail="; ".join(log), sess=len(fwd[:horizon]), amb=amb, be_lvl=be_lvl, t8=t8, mark_date=(last["d"] if last else None))

def fixed_check(t, d, bars, ent, H, L, horizon=20):
    entry = ent["fill"]; stop = 2 * L - H; planned = H - stop; tgt = entry + 3 * planned
    first = None; best = entry
    for b in [x for x in bars if x["hhmm"] > ent["minute"]]:
        best = max(best, b["h"])
        if first is None:
            if b["l"] <= stop: first = "stop_first"
            elif b["h"] >= tgt: first = "target_first"
    fwd = [b for b in daily[t] if b["d"] > d][:horizon]
    for b in fwd:
        best = max(best, b["h"])
        if first is None:
            if b["l"] <= stop and b["h"] >= tgt: first = "same_bar"
            elif b["l"] <= stop: first = "stop_first"
            elif b["h"] >= tgt: first = "target_first"
    return first, (best - entry) / planned, len(fwd)

# ---------------- per name ----------------
print("\n=== PER NAME ===")
results = {}
for r in pop:
    t, d = r["ticker"], r["d"]; dd = D(d)
    bars = [dict(hhmm=b["hhmm"], o=float(b["open"]), h=float(b["high"]), l=float(b["low"]), c=float(b["close"])) for b in mins.get((t, d), [])]
    b0 = bars[0]; H, L = b0["h"], b0["l"]; stop = 2 * L - H; planned = H - stop
    m = re.search(r"rt ([\d.]+)% < 9% floor .*last \$([\d.]+) vs prev close \$([\d.]+)", r["skip_reason"])
    rt_txt, live, pc_txt = float(m.group(1)), float(m.group(2)), float(m.group(3))
    pc_daily = [b for b in daily[t] if b["d"] < dd][-1]["c"]
    floor = pc_txt * 1.09
    atr, nrows = atr14(t, dd)
    print(f"{t:5} {d} flip={r['flip_up_rows']} pc scan/text/daily {r['scan_prev_close']}/{pc_txt}/{pc_daily} floor {floor:.2f} "
          f"ORB O/H/L/C {b0['o']}/{H}/{L}/{b0['c']} stop {stop:.2f} planned {planned:.2f} live {live} rt_calc {(live-pc_txt)/pc_txt*100:.2f}% (text {rt_txt}) "
          f"ATR14 {atr:.3f}({nrows}) range {H-L:.2f} vs 1.5xATR {1.5*atr:.2f} bars {len(bars)} last {bars[-1]['hhmm']}")
    if len(bars) < 2:
        print(f"      NOT EVALUABLE: {len(bars)} minute bar(s)"); results[t] = dict(status="unknown"); continue
    if (H - L) > 1.5 * atr: print("      stop_too_wide!"); results[t] = dict(status="stop_too_wide"); continue
    out = {}
    for arm_name, lv, start in (("main", live, "09:32"), ("proxy0930", b0["c"], "09:32"), ("main_from0931", live, "09:31"), ("proxy_from0931", b0["c"], "09:31")):
        ent = entry_walk(bars, H, L, lv, start)
        out[arm_name] = ent
        line = f"   [{arm_name}] {ent['kind']}"
        if "fill" in ent:
            ex = exit_walk(t, dd, bars, ent, H, L)
            ex40 = exit_walk(t, dd, bars, ent, H, L, horizon=40)
            exna = exit_walk(t, dd, bars, ent, H, L, use_arming=False)
            ex_no8 = exit_walk(t, dd, bars, ent, H, L, partial8=False)
            fc = fixed_check(t, dd, bars, ent, H, L)
            ent["exit"] = ex; ent["exit40"] = ex40; ent["exit_noarm"] = exna; ent["fixed"] = fc
            line += (f" fill {ent['fill']:.2f} @ {ent['minute']} lim {ent['lim']}{' ratio %.2fx' % ent['ratio'] if 'ratio' in ent else ''} {ent.get('note','')}"
                     f" | BE lvl {ex['be_lvl']:.2f} 8R {ex['t8']:.2f} | 20s: {ex['status']} R={'%.2f' % ex['R'] if ex['R'] is not None else '-'} [{ex['detail']}] amb={ex['amb']}"
                     f" | 40s: {ex40['status']} {'%.2f' % ex40['R'] if ex40['R'] is not None else '-'} | no-arm: {exna['status']} {'%.2f' % exna['R'] if exna['R'] is not None else '-'}"
                     f" | no-8R: {ex_no8['status']} | fixed: {fc[0]} best {fc[1]:+.2f}R n={fc[2]}")
        print(line)
    results[t] = out

# ---------------- sums ----------------
print("\n=== SUMS ===")
for arm in ("main", "proxy0930", "main_from0931", "proxy_from0931"):
    ent = [(t, o[arm]) for t, o in results.items() if isinstance(o, dict) and arm in o and "fill" in o[arm]]
    sett = [(t, e["exit"]["R"]) for t, e in ent if e["exit"]["status"] == "settled"]
    other = [(t, e["exit"]["status"]) for t, e in ent if e["exit"]["status"] != "settled"]
    print(f"{arm}: entered {len(ent)} {[t for t,_ in ent]} | settled {len(sett)} sum {sum(r for _,r in sett):+.2f}R "
          f"{[(t, round(r,2)) for t,r in sett]} wins {sum(1 for _,r in sett if r>0.005)} losses {sum(1 for _,r in sett if r<-0.005)} big>=3R {sum(1 for _,r in sett if r>=3)} | other {other}")
