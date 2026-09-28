"""#685 depth-trigger follow-up — INDEPENDENT CHECK (2026-09-28).

Checks the section "Follow-up 2026-09-28 — the slice rule as a depth trigger" of
docs/analysis/685_hybrid_trail_2026-09-28.md and its probe depth.py. Imports NOTHING from study.py or
depth.py: the loaders/SMA/permutation come from check_recompute.py (the earlier independent check,
51/51 against study.py), the day-0 end state is re-derived from the validated harness (ep_replay), and
the D05/D10 forward walker below is written fresh. Reads depth.py's / study.py's outputs only to compare.
$0, no prod access. Outputs: check_depth_*.txt beside it.
"""
from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_recompute as CR  # noqa: E402  (own loaders, not study.py)

ep = CR.ep
HORIZON = date(2026, 9, 25)
SPLIT = date(2026, 8, 31)
FTK = ("FTK", date(2026, 8, 3))
INFQ = ("INFQ", date(2026, 5, 21))
OUT: dict[str, list[str]] = defaultdict(list)


def w(name, *a):
    OUT[name].append(" ".join(str(x) for x in a))


def adr20(dmap, before, incl=False):
    """Own ADR20: mean (h-l)/c over the <=20 sessions strictly before `before` (incl=True adds `before`)."""
    pre = [dmap[d] for d in sorted(dmap) if (d <= before if incl else d < before)]
    vals = [(b["h"] - b["l"]) / b["c"] for b in pre[-20:]
            if b.get("h") is not None and b.get("l") is not None and b.get("c")]
    return (sum(vals) / len(vals)) if len(vals) >= 10 else None


# ── population + day-0 end state (harness), own code path ─────────────────────────────────

def build():
    S, raw, daily, regime, adv, src, mincov = CR.load()
    regime_rows = sorted(regime.values(), key=lambda r: r["regime_date"])
    rs = ep.RULESETS["era_d"]
    seen = {}
    for a in raw:
        kk = (a["ticker"], a["alert_date"])
        if kk not in seen or (a.get("detected_at_et") or "") < (seen[kk].get("detected_at_et") or ""):
            seen[kk] = a
    alerts = sorted((a for a in seen.values() if a["alert_date"] <= HORIZON.isoformat()),
                    key=lambda a: (a["alert_date"], a["ticker"]))
    ep.LAST_SETTLED = HORIZON
    camps = {}
    for a in alerts:
        ad, sc = ep._score_one(a, rs, daily, adv, regime_rows)
        submit = time(9, 31)
        if a.get("detected_at_et"):
            t = datetime.fromisoformat(a["detected_at_et"]).time()
            submit = max(submit, time(t.hour, t.minute))
        mins0 = {(a["ticker"], ad): CR.bars_for(src, (a["ticker"], ad), True)[0]}
        res = ep.walk_campaign(ticker=a["ticker"], alert_date=ad, rs=rs, minutes=mins0, daily=daily, submit=submit)
        res.update(admit=sc["admit"], tier=a.get("score_tier"), submit=submit, alert=a)
        camps[(a["ticker"], ad)] = res
    widened = {k for k, r in camps.items()
               if r["admit"] == "admit" or (r["admit"].startswith("abstain") and r["tier"] == "HIGH")}
    states, d0 = {}, {}
    for kk in sorted(widened, key=lambda k: (k[1], k[0])):
        r = camps[kk]
        if not r["entered"] or r["status"] in ("no_trade", "no_entry"):
            continue
        if r["status"] == "abstain" and not str(r["reason"]).startswith("fwd_"):
            continue
        tk, ad = kk
        b0 = CR.bars_for(src, kk, True)[0]
        ep.LAST_SETTLED = ad
        r0 = ep.walk_campaign(ticker=tk, alert_date=ad, rs=rs, minutes={kk: b0}, daily=daily, submit=r["submit"])
        ep.LAST_SETTLED = HORIZON
        if r0["status"] == "settled":
            d0[kk] = r0["realized_r"]
            continue
        if r0["status"] != "open_at_horizon":
            continue
        orb = next(x for x in b0 if x["m"].time() == time(9, 30))
        entry, hard = r0["entry_px"], r0["stop"]
        rps = CR.profit_target_r_per_share("magna53", entry, hard, orb["l"])
        bet = entry + 3.0 * rps
        fill = ep.entry_walk(b0, orb["h"], r["submit"], rs.entry_cancel)
        be = any(x["m"] >= fill["minute"] and x["h"] >= bet for x in b0)
        sh = 1.0 / (entry - hard)
        ex = r0["exits"]
        partial = any(e["reason"] == "partial_profit" for e in ex)
        states[kk] = dict(ticker=tk, ad=ad, entry=entry, hard=hard, target=r0["target"], be_trig=bet,
                          rem=sh - sum(e["shares"] for e in ex), partial=partial, be=be or partial,
                          pnl0=sum(e["pnl"] for e in ex), adr_h=r0["adr_pct"],
                          adr_own=adr20(daily.get(tk, {}), ad))
    return S, daily, src, mincov, states, d0


# ── the forward walker (own code): A0 / A1 / D(mult) ─────────────────────────────────────

def walk(c, arm, daily, src, *, mult=None, daily_low="all", line_mode="ok", adr_mode="entry", fill="touch"):
    """arm: 'A0' (line rests), 'A1' (close only), 'D' (resting depth stop at line - mult*ADR*line).
    daily_low: 'all'  = a daily-low touch of the resting stop is booked on EVERY day (study semantics, via
                        apply_daily_exit_step step 1), 'nobars' = only on days with no minute bars.
    line_mode: 'ok' = yesterday-evening's broker line; 'lookahead' = the 16:45 SMA incl. TODAY's close.
    adr_mode: 'entry' (harness adr20 at the alert), 'asof' (20 sessions before day d), 'incl' (incl. day d),
              'none' (D never fires: a broken replay).
    fill: 'touch' = fill at the stop (or the open on a gap); 'barlow' = a depth fire fills at the bar's low."""
    entry, hard, tgt, bet = c["entry"], c["hard"], c["target"], c["be_trig"]
    rem, ptk, be, pnl = c["rem"], c["partial"], c["be"], c["pnl0"]
    tk, ad = c["ticker"], c["ad"]
    dmap = daily.get(tk, {})
    prior = [dmap[d]["c"] for d in sorted(dmap) if d < ad and dmap[d]["c"] is not None]
    held = []
    broker = round(entry, 2) if be else round(hard, 2)
    info = {"line_tests": [], "fires": [], "exit_day": None, "exit_px": None, "reason": None}
    d = ad
    while True:
        d += timedelta(days=1)
        if d > HORIZON:
            mark = pnl + ((held[-1] if held else entry) - entry) * rem
            return "open", None, mark, info
        if d.weekday() >= 5:
            continue
        b = dmap.get(d)
        if not b or None in (b["o"], b["h"], b["l"], b["c"]):
            continue
        floor = entry if be else hard
        line = broker
        governed = line > round(floor, 2) + 1e-9
        if governed and b["l"] <= line:
            info["line_tests"].append((d, line, b["l"], b["c"]))
        dline = line
        if line_mode == "lookahead":
            tl_la = CR.sma_line(prior + held + [b["c"]])
            dline = round(max(floor, tl_la if tl_la is not None else floor), 2)
        dgov = dline > round(floor, 2) + 1e-9
        if arm == "A0":
            rest = line
        elif arm == "D" and dgov and adr_mode != "none":
            adr = {"entry": c["adr_h"], "asof": adr20(dmap, d), "incl": adr20(dmap, d, incl=True)}[adr_mode]
            rest = max(round(floor, 2), round(dline - mult * adr * dline, 2)) if adr else round(floor, 2)
        else:
            rest = round(floor, 2)
        depth_rest = rest if (arm == "D" and rest > round(floor, 2) + 1e-9) else None
        mb, s_ = CR.bars_for(src, (tk, d), False)
        done = False
        for x in mb:
            if not be and x["h"] >= bet:
                if rest < entry and x["l"] <= entry:
                    info["reason"] = f"abstain_be_same_bar {d}"
                    return "abstain", None, None, info
                be = True
                floor = entry
                rest = max(rest, round(entry, 2))
                broker = max(broker, round(entry, 2))
                if depth_rest is not None and rest > depth_rest:
                    depth_rest = None
            hit_stop = x["l"] <= rest
            hit_tgt = tgt is not None and not ptk and x["h"] >= tgt
            if hit_stop and hit_tgt:
                info["reason"] = f"abstain_tgt_same_bar {d}"
                return "abstain", None, None, info
            if hit_stop:
                px = min(x["o"], rest)
                is_depth = depth_rest is not None and abs(rest - depth_rest) < 1e-9
                if fill == "barlow" and is_depth:
                    px = min(x["o"], x["l"])
                pnl += (px - entry) * rem
                info["fires"].append(dict(day=d, minute=x["m"].strftime("%H:%M"), px=px, rest=rest,
                                          depth=is_depth, line=line, bar=(x["o"], x["h"], x["l"], x["c"]),
                                          first_bar=mb[0]["m"].strftime("%H:%M"), n_bars=len(mb), src=s_,
                                          day_open=b["o"], close=b["c"], grain="minute", gap=px < rest))
                info.update(exit_day=d, exit_px=px, reason="stop")
                rem = 0
                done = True
                break
            if hit_tgt:
                q = rem / 3
                pnl += (tgt - entry) * q
                rem -= q
                ptk = True
                be = True
                floor = entry
                rest = max(rest, round(entry, 2))
                broker = max(broker, round(entry, 2))
                if depth_rest is not None and rest > depth_rest:
                    depth_rest = None
        if done:
            return "settled", pnl, None, info
        if not mb:
            if not be and b["h"] >= bet:
                if rest < entry and b["l"] <= entry:
                    info["reason"] = f"abstain_be_same_day {d}"
                    return "abstain", None, None, info
                be = True
                floor = entry
                rest = max(rest, round(entry, 2))
                broker = max(broker, round(entry, 2))
                if depth_rest is not None and rest > depth_rest:
                    depth_rest = None
            if tgt is not None and not ptk and b["h"] >= tgt:
                if b["l"] <= rest:
                    info["reason"] = f"abstain_tgt_same_day {d}"
                    return "abstain", None, None, info
                q = rem / 3
                pnl += (tgt - entry) * q
                rem -= q
                ptk = True
                be = True
                floor = entry
                rest = max(rest, round(entry, 2))
                broker = max(broker, round(entry, 2))
                if depth_rest is not None and rest > depth_rest:
                    depth_rest = None
        if (daily_low == "all" or not mb) and b["l"] <= rest:
            px = min(b["o"], rest)
            is_depth = depth_rest is not None and abs(rest - depth_rest) < 1e-9
            if fill == "barlow" and is_depth:
                px = b["l"]
            pnl += (px - entry) * rem
            info["fires"].append(dict(day=d, minute="daily", px=px, rest=rest, depth=is_depth, line=line,
                                      bar=(b["o"], b["h"], b["l"], b["c"]),
                                      first_bar=(mb[0]["m"].strftime("%H:%M") if mb else "-"),
                                      n_bars=len(mb), src=s_, day_open=b["o"], close=b["c"],
                                      grain="DAILY-LOW (not seen in any minute bar)" if mb else "daily (no bars)",
                                      gap=px < rest))
            info.update(exit_day=d, exit_px=px, reason="stop_daily")
            return "settled", pnl, None, info
        # 16:45 job: eff = max(hard, max(SMA10, SMA20) incl today, entry if breakeven)
        held.append(b["c"])
        tl = CR.sma_line(prior + held)
        eff = hard
        if tl is not None and tl > eff:
            eff = tl
        if be and entry > eff:
            eff = entry
        if b["c"] < eff:
            pnl += (b["c"] - entry) * rem
            info.update(exit_day=d, exit_px=b["c"], reason="close_below")
            return "settled", pnl, None, info
        if eff > broker + 0.01:
            broker = round(eff, 2)


def rd(path):
    with open(path) as fh:
        return {(r["ticker"], date.fromisoformat(r["alert_date"])): r for r in csv.DictReader(fh, delimiter="|")}


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main():
    S, daily, src, mincov, states, d0 = build()
    stored = rd(HERE / "arms_per_trade.tsv")
    dpt = rd(HERE / "depth_per_trade.tsv")
    orig = ("A0", "A1", "A2k2", "A2k3", "A3")
    keys79 = sorted((k for k, r in stored.items()
                     if all(r[f"{a}_status"] == "settled" and r[f"{a}_unreadable"] == "False" for a in orig)),
                    key=lambda k: (k[1], k[0]))

    # ── (1) RECOMPUTE ──────────────────────────────────────────────────────────────────
    P = "check_depth_recompute"
    w(P, f"population: reached day 1 {len(states)} (probe 51), settled day 0 {len(d0)} (probe 35); "
         f"set == arms_per_trade.tsv: {set(states) | set(d0) == set(stored)}; 79-paired keys from arms_per_trade.tsv {len(keys79)}")
    adr_bad = [(k, s["adr_h"], s["adr_own"]) for k, s in states.items()
               if (s["adr_h"] is None) != (s["adr_own"] is None) or (s["adr_h"] and abs(s["adr_h"] - s["adr_own"]) > 1e-9)]
    w(P, f"ADR20 at entry: harness adr_pct vs own ADR20 (20 sessions strictly before the alert date) disagree on {len(adr_bad)} of {len(states)} {adr_bad[:5]}")

    VAR = {"A0": dict(arm="A0"), "A1": dict(arm="A1"),
           "D05": dict(arm="D", mult=0.5), "D10": dict(arm="D", mult=1.0)}
    res = {a: {k: walk(st, daily=daily, src=src, **kw) for k, st in states.items()} for a, kw in VAR.items()}

    def R(a, k, table=res):
        if k in d0:
            return d0[k]
        stt, r, mark, info = table[a][k]
        return r if stt == "settled" else None

    for a in ("A0", "A1"):
        agree = sum(1 for k in stored if R(a, k) is not None and fnum(stored[k][f"{a}_R"]) is not None
                    and abs(R(a, k) - float(stored[k][f"{a}_R"])) < 0.005)
        nset = sum(1 for k in stored if fnum(stored[k][f"{a}_R"]) is not None)
        w(P, f"{a}: own walk agrees with arms_per_trade.tsv within 0.005R on {agree} of {nset} settled")
    for a in ("D05", "D10"):
        mm = [(k, R(a, k), fnum(dpt[k][f"{a}_R"])) for k in keys79 if R(a, k) is None or abs(R(a, k) - float(dpt[k][f"{a}_R"])) >= 0.00006]
        w(P, f"{a}: own walk vs depth_per_trade.tsv on the 79: {79 - len(mm)} of 79 agree to 4 dp; mismatches {mm}")

    def tot(a, ks):
        return sum(R(a, k) for k in ks)
    blocks = {"ALL": keys79, "ALL_ex": [k for k in keys79 if k not in (FTK, INFQ)],
              "DISC": [k for k in keys79 if k[1] <= SPLIT], "HELD": [k for k in keys79 if k[1] > SPLIT]}
    for bl, ks in blocks.items():
        a0 = tot("A0", ks)
        w(P, f"BLOCK {bl} n={len(ks)}: A0 {a0:+.2f}")
        for a in ("A1", "D05", "D10"):
            diffs = [R(a, k) - R("A0", k) for k in ks]
            wk = [f"{k[1].isocalendar()[0]}-{k[1].isocalendar()[1]}" for k in ks]
            p = CR.perm(diffs, wk, n=5000, seed=11)
            bw_raw = (sum(x > 1e-9 for x in diffs), sum(x < -1e-9 for x in diffs))
            bw = (sum(x > 5e-4 for x in diffs), sum(x < -5e-4 for x in diffs))
            w(P, f"   {a:4s} total {tot(a, ks):+.2f} vs A0 {sum(diffs):+.2f} p(own perm, seed 11) {p:.3f} "
                 f"better/worse (|diff|>0.0005R) {bw[0]}/{bw[1]}  [at 1e-9, full precision own walk: {bw_raw[0]}/{bw_raw[1]}]")
    # rounding artifact: the probe compares full-precision D walks against 4-dp stored A0
    for bl, ks in (("ALL", blocks["ALL"]), ("ALL_ex", blocks["ALL_ex"])):
        for a in ("D05", "D10"):
            art = [x for x in (R(a, k) - float(stored[k]["A0_R"]) for k in ks)]
            w(P, f"   probe-style better/worse ({a} full precision vs 4-dp stored A0, 1e-9): {bl} "
                 f"{sum(x > 1e-9 for x in art)}/{sum(x < -1e-9 for x in art)}; of which |diff| < 0.0005R (rounding only): "
                 f"{sum(1 for x in art if 1e-9 < abs(x) < 5e-4)}")
    w(P, "per-trade: every one of the 79 where D05 or D10 differs from close-only (A1), own walk:")
    for k in keys79:
        a1, d5, d10, a0 = R("A1", k), R("D05", k), R("D10", k), R("A0", k)
        if abs(d5 - a1) > 5e-4 or abs(d10 - a1) > 5e-4:
            f5 = [f for f in res["D05"][k][3]["fires"]] if k in states else []
            f5s = "; ".join(f"{f['day']} {f['minute']} @{f['px']:.2f} depth={f['depth']} close {f['close']:.2f} line {f['line']:.2f}" for f in f5)
            w(P, f"   {k[0]:5s} {k[1]} A0 {a0:+.2f} A1 {a1:+.2f} D05 {d5:+.2f} ({d5 - a1:+.2f} vs A1) D10 {d10:+.2f} ({d10 - a1:+.2f} vs A1) | D05 fire: {f5s}")
    ex = blocks["ALL_ex"]
    w(P, f"D05 vs close-only on the 77 (FTK/INFQ out): {tot('D05', ex) - tot('A1', ex):+.2f}R; D10 vs close-only on the 77: {tot('D10', ex) - tot('A1', ex):+.4f}R")
    for nm, k in (("FTK", FTK), ("INFQ", INFQ)):
        w(P, f"{nm}: A0 {R('A0', k):+.2f} A1 {R('A1', k):+.2f} D05 {R('D05', k):+.2f} D10 {R('D10', k):+.2f}")
    for a in ("A2k2", "A3"):   # not rewalked here — arithmetic on the stored file only
        s79 = sum(float(stored[k][f"{a}_R"]) for k in keys79)
        s77 = sum(float(stored[k][f"{a}_R"]) for k in ex)
        a079 = sum(float(stored[k]["A0_R"]) for k in keys79)
        a077 = sum(float(stored[k]["A0_R"]) for k in ex)
        w(P, f"stored {a} (arithmetic only, not rewalked): 79 {s79:+.2f} (vs A0 {s79 - a079:+.2f}); 77 {s77:+.2f} (vs A0 {s77 - a077:+.2f}); "
             f"worst {min(float(stored[k][f'{a}_R']) for k in keys79):+.2f}")
    for a in ("A0", "A1", "D05", "D10"):
        w(P, f"{a}: worst trade on the 79 {min(R(a, k) for k in keys79):+.2f}; losses beyond -1.5R {sum(1 for k in keys79 if R(a, k) < -1.5)}")

    # false sells: A1-path line tests, reclaim = close >= that day's line
    lts = [(k, x) for k in states for x in res["A1"][k][3]["line_tests"]]
    rec = [(k, x) for k, x in lts if x[3] >= x[1]]
    rec79 = [(k, x) for k, x in rec if k in set(keys79)]
    w(P, f"A1-path line tests {len(lts)} on {len({k for k, _ in lts})} trades; RECLAIM days {len(rec)} ({len(rec79)} on the 79)")
    for a in ("D05", "D10"):
        fires = [(k, f) for k in states for f in res[a][k][3]["fires"] if f["depth"]]
        fires79 = [(k, f) for k, f in fires if k in set(keys79)]
        fs = [(k, f) for k, f in fires if f["close"] >= f["line"]]
        fs79 = [(k, f) for k, f in fs if k in set(keys79)]
        a1same = [(k[0], str(f["day"])) for k, f in fs if res["A1"][k][3]["exit_day"] == f["day"]]
        w(P, f"{a}: depth fires {len(fires)} ({len(fires79)} on the 79); fires on a day that closed at/above the line {len(fs)} "
             f"({len(fs79)} on the 79): {[(k[0], str(f['day'])) for k, f in fs]}; of those, close-only ALSO sold that same day (close below the 16:45 line): {a1same}")

    # ── (2) CAUSALITY / FILLABILITY ──────────────────────────────────────────────────
    P = "check_depth_causality"
    w(P, "every D05/D10 exit after day 0 (own walk, study semantics: a daily-low touch is booked on every day):")
    for a in ("D05", "D10"):
        for k in sorted(states, key=lambda k: (k[1], k[0])):
            for f in res[a][k][3]["fires"]:
                o, h, l, c = f["bar"]
                w(P, f"   {a} {k[0]:5s} {k[1]} exit {f['day']} {f['minute']} @{f['px']:.2f} rest {f['rest']:.2f} depth-trigger={f['depth']} "
                     f"line {f['line']:.2f} | fill bar o/h/l/c {o}/{h}/{l}/{c} | day open {f['day_open']} close {f['close']} | "
                     f"bars {f['n_bars']} first {f['first_bar']} [{f['src']}] grain {f['grain']} gap {f['gap']} in79 {k in set(keys79)}")
    for a in ("D05", "D10"):
        bad = []
        for k in states:
            for f in res[a][k][3]["fires"]:
                if not f["depth"]:
                    continue
                o = f["bar"][0]
                if f["px"] > o + 1e-9:
                    bad.append((k[0], str(f["day"]), "fill above the bar open"))
                if f["px"] < f["bar"][2] - 1e-9:
                    bad.append((k[0], str(f["day"]), "fill below the bar low"))
                if f["minute"] not in ("daily",) and f["first_bar"] != "09:30" and f["minute"] == f["first_bar"] and f["day_open"] < f["rest"]:
                    bad.append((k[0], str(f["day"]), f"gap day but first stored bar {f['first_bar']} not 09:30"))
                if f["grain"].startswith("DAILY-LOW"):
                    bad.append((k[0], str(f["day"]), "touch seen only in the daily low, not in any stored minute bar"))
        w(P, f"{a} depth fires failing a causality/fill check: {bad if bad else 'none'}")
    # variants: minute-only daily-low check, and worst-case bar-low fills
    VAR2 = {"D05_minonly": dict(arm="D", mult=0.5, daily_low="nobars"), "D10_minonly": dict(arm="D", mult=1.0, daily_low="nobars"),
            "D05_barlow": dict(arm="D", mult=0.5, fill="barlow"), "D10_barlow": dict(arm="D", mult=1.0, fill="barlow")}
    res2 = {a: {k: walk(st, daily=daily, src=src, **kw) for k, st in states.items()} for a, kw in VAR2.items()}
    for a in VAR2:
        for bl in ("ALL", "ALL_ex"):
            ks = blocks[bl]
            t = sum(R(a, k, res2) for k in ks)
            w(P, f"{a:12s} {bl:6s}: total {t:+.2f} vs A0 {t - tot('A0', ks):+.2f} vs A1 {t - tot('A1', ks):+.2f}")
        w(P, f"   {a}: FTK {R(a, FTK, res2):+.2f} INFQ {R(a, INFQ, res2):+.2f} (A1: FTK {R('A1', FTK):+.2f} INFQ {R('A1', INFQ):+.2f})")
    for nm, k, d in (("FTK", FTK, date(2026, 8, 17)), ("INFQ", INFQ, date(2026, 6, 5))):
        mb, s_ = CR.bars_for(src, (k[0], d), False)
        w(P, f"{nm} {d} first 6 minute bars [{s_}] (o/h/l/c): " + "; ".join(f"{x['m'].strftime('%H:%M')} {x['o']}/{x['h']}/{x['l']}/{x['c']}" for x in mb[:6])
             + f" | daily o/h/l/c {daily[k[0]][d]['o']}/{daily[k[0]][d]['h']}/{daily[k[0]][d]['l']}/{daily[k[0]][d]['c']}")

    # ── (3) NO LINE TEST → identical across arms ───────────────────────────────────────
    P = "check_depth_nolinetest"
    nolt = [k for k in keys79 if k in d0 or not res["A1"][k][3]["line_tests"]]
    bad = []
    for k in nolt:
        vals = {a: R(a, k) for a in ("A0", "A1", "D05", "D10")}
        vals.update({a: float(stored[k][f"{a}_R"]) for a in orig})
        vals.update({f"probe_{a}": float(dpt[k][f"{a}_R"]) for a in ("D05", "D10")})
        if max(vals.values()) - min(vals.values()) > 5e-4:
            bad.append((k, vals))
    w(P, f"trades in the 79 with no line test on the close-only path: {len(nolt)} ({sum(1 for k in nolt if k in d0)} stopped on day 0); "
         f"all of A0/A1/A2k2/A2k3/A3 (stored) + own A0/A1/D05/D10 + probe D05/D10 within 0.0005R: {'YES' if not bad else 'NO'}")
    for k, v in bad:
        w(P, f"   DIFFERS {k}: {v}")
    held = blocks["HELD"]
    w(P, f"held-out trades in the 79: {[(k[0], str(k[1])) for k in held]}; with no line test: {sum(1 for k in held if k in nolt)} of {len(held)}; "
         f"day-0 stops {sum(1 for k in held if k in d0)}")
    lt79 = [k for k in keys79 if k not in nolt]
    w(P, f"trades in the 79 WITH a line test: {len(lt79)}: {[k[0] for k in lt79]}")

    # ── (4) BROKEN-REPLAY DISCRIMINATION ────────────────────────────────────────────────
    P = "check_depth_broken"
    dlt = {}
    with open(HERE / "depth_line_tests.tsv") as fh:
        for r in csv.DictReader(fh, delimiter="|"):
            dlt[(r["ticker"], r["day"])] = r
    mism = 0
    rows = []
    for k, (d, line, lo, cl) in lts:
        adr = states[k]["adr_own"]
        dep = (line - lo) / (adr * line) if adr else None
        pr = dlt.get((k[0], d.isoformat()))
        ok = pr is not None and abs(float(pr["line"]) - line) < 0.005 and (dep is None or abs(float(pr["depth_adr"] or 0) - dep) < 0.002)
        mism += not ok
        rows.append((k, d, line, lo, cl, dep, pr))
    w(P, f"own line + own ADR20 vs depth_line_tests.tsv: {len(lts) - mism} of {len(lts)} line-test days match (line to the cent, depth to 0.002 ADR); "
         f"probe rows {len(dlt)}")
    w(P, "max depth below the line on every line-test day, in ADR multiples (own line, own ADR20 at entry), >= 0.5 flagged:")
    for k, d, line, lo, cl, dep, pr in sorted(rows, key=lambda r: -(r[5] or 0)):
        st = states[k]
        fl = round(st["entry"], 2)
        lvl10 = line - 1.0 * st["adr_own"] * line
        lvl05 = line - 0.5 * st["adr_own"] * line
        tag = ">=1.0" if dep >= 1.0 else (">=0.5" if dep >= 0.5 else "")
        w(P, f"   {k[0]:5s} {d} in79={k in set(keys79)} line {line:.2f} low {lo} close {cl} depth {dep:.3f} ADR ({(line - lo) / line * 100:.2f}% low, "
             f"{(line - cl) / line * 100:+.2f}% close) {tag} | D10 level {lvl10:.2f} D05 level {lvl05:.2f} entry {fl} hard {st['hard']:.2f}")
    # broken variants
    BRK = {"D10_lookahead_line": dict(arm="D", mult=1.0, line_mode="lookahead"),
           "D05_lookahead_line": dict(arm="D", mult=0.5, line_mode="lookahead"),
           "D10_adr_asof_day": dict(arm="D", mult=1.0, adr_mode="asof"),
           "D05_adr_asof_day": dict(arm="D", mult=0.5, adr_mode="asof"),
           "D10_adr_incl_today": dict(arm="D", mult=1.0, adr_mode="incl"),
           "D05_adr_incl_today": dict(arm="D", mult=0.5, adr_mode="incl"),
           "D_never_fires": dict(arm="D", mult=1.0, adr_mode="none")}
    res3 = {a: {k: walk(st, daily=daily, src=src, **kw) for k, st in states.items()} for a, kw in BRK.items()}
    w(P, "broken / alternative replays (paired on the same 79 keys):")
    for a in ("D05", "D10"):
        w(P, f"   {a:20s} CORRECT: 79 {tot(a, keys79):+.2f} (vs A0 {tot(a, keys79) - tot('A0', keys79):+.2f}); 77 {tot(a, ex):+.2f} (vs A0 {tot(a, ex) - tot('A0', ex):+.2f}); "
             f"FTK {R(a, FTK):+.2f} INFQ {R(a, INFQ):+.2f}")
    for a in BRK:
        t79 = sum(R(a, k, res3) for k in keys79)
        t77 = sum(R(a, k, res3) for k in ex)
        base = "D10" if "D10" in a or a == "D_never_fires" else "D05"
        ndiff = sum(1 for k in keys79 if abs(R(a, k, res3) - R(base, k)) > 5e-4)
        w(P, f"   {a:20s} 79 {t79:+.2f} (vs A0 {t79 - tot('A0', keys79):+.2f}); 77 {t77:+.2f} (vs A0 {t77 - tot('A0', ex):+.2f}); "
             f"FTK {R(a, FTK, res3):+.2f} INFQ {R(a, INFQ, res3):+.2f}; trades differing from correct {base}: {ndiff}")

    for name, lines in OUT.items():
        (HERE / f"{name}.txt").write_text("\n".join(lines) + "\n")
        print(f"== {name} ==")
        print("\n".join(lines))


if __name__ == "__main__":
    main()
