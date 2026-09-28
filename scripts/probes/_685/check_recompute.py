"""#685 INDEPENDENT CHECK of docs/analysis/685_hybrid_trail_2026-09-28.md (study.py).

Written separately from study.py: its own loaders for the captures, its own forward walker
(A0 today's touch stop, A1 close-only, A2 slice signature k=2), its own SMA line and its own
permutation. It reuses ONLY the validated harness (ep_replay) for re-scoring and the day-0
walk (identical in every arm), and reads nothing study.py computed except to compare.
$0, no prod access — reads the captures already on disk. Outputs: check_*.txt beside it.
"""
from __future__ import annotations

import csv
import gzip
import json
import random
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO))
import ep_replay as ep  # noqa: E402
from agents.market_intelligence.broker.order_manager import profit_target_r_per_share  # noqa: E402

ET = ep._ET
HORIZON = date(2026, 9, 25)
SPLIT = date(2026, 8, 31)
OUT = {}


def w(name, *a):
    OUT.setdefault(name, []).append(" ".join(str(x) for x in a))


# ── loaders (own code) ─────────────────────────────────────────────────────────────

def sections(path):
    return ep.read_sections(path)   # a pure text splitter; nothing computed


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load():
    S = sections(HERE / "pull_main_out.txt")
    s2 = sections(ep.DATA / "_pull2_out.txt")
    s3 = sections(ep.DATA / "_pull3_out.txt")
    s5 = sections(ep.DATA / "_pull5_out.txt")
    conf = {r["id"]: r["confidence_multiplier"] for r in s5["CONF"]}
    raw = [dict(a, confidence_multiplier=conf.get(a["id"])) for a in s2["ALERTS"]] + list(S["ALERTS"])
    daily = defaultdict(dict)
    for r in S["DAILY"]:
        daily[r["ticker"]][date.fromisoformat(r["trade_date"])] = {
            "o": f(r["open_price"]), "h": f(r["high_price"]), "l": f(r["low_price"]),
            "c": f(r["close"]), "v": f(r["volume"])}
    regime = {r["regime_date"]: r for r in s2["REGIME"]}
    regime.update({r["regime_date"]: r for r in S["REGIME"]})
    adv = {(r["ticker"], r["score_date"]): f(r["adv_20"]) for r in s3["ADV"]}
    adv.update({(r["ticker"], r["score_date"]): f(r["adv_20"]) for r in S["ADV"]})
    # minute bars: every source into its own dict
    src = {}
    src["pull4"] = ep.load_minutes()
    bf = defaultdict(list)
    with gzip.open(REPO / "scripts/probes/_562bf_minute.tsv.gz", "rt") as fh:
        for line in fh:
            p = line.rstrip("\n").split("|")
            if len(p) != 8 or p[0] == "ticker":
                continue
            dt = datetime.fromtimestamp(int(p[2]) / 1000, tz=ET)
            if time(9, 30) <= dt.time() < time(16, 0):
                bf[(p[0], dt.date())].append({"m": dt, "o": float(p[3]), "h": float(p[4]), "l": float(p[5]), "c": float(p[6])})
    src["562bf"] = bf
    nw = defaultdict(dict)
    with gzip.open(HERE / "pull_min_out.tsv.gz", "rt") as fh:
        for line in fh:
            p = line.rstrip("\n").split("|")
            if len(p) != 7 or p[0] == "ticker" or p[0].startswith("==="):
                continue
            dt = datetime.strptime(p[1], "%Y-%m-%d %H:%M").replace(tzinfo=ET)
            if time(9, 30) <= dt.time() < time(16, 0):
                nw[(p[0], dt.date())][dt] = {"m": dt, "o": float(p[2]), "h": float(p[3]), "l": float(p[4]), "c": float(p[5])}
    src["new"] = {k: list(v.values()) for k, v in nw.items()}
    for s in src.values():
        for v in s.values():
            v.sort(key=lambda b: b["m"])
    mincov = {(r["ticker"], date.fromisoformat(r["d"])): int(r["n"]) for r in S["MINCOV"]}
    return S, raw, daily, regime, adv, src, mincov


def bars_for(src, key, day0):
    """day 0: the 09-01 capture first (the harness' own source), else the new pull.
    later days: the #562 backfill, else the new pull, else the 09-01 capture."""
    order = ("pull4", "new") if day0 else ("562bf", "new", "pull4")
    for s in order:
        b = src[s].get(key)
        if b:
            return b, s
    return [], None


# ── the forward walker (own code) ──────────────────────────────────────────────────

def sma_line(closes):
    s10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else None
    s20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
    if s20 is not None and s10 is not None:
        return max(s10, s20)
    return s10


def wnum(m):
    return (m.hour * 60 + m.minute - 570) // 5


def walk(c, arm, daily, src, k=2, horizon=HORIZON, line_seed=None, stop_rounding=True):
    """c: day-0 end state. arm in A0 (line rests), A1 (close only), A2 (slice k + close)."""
    entry, hard, tgt, bet = c["entry"], c["hard"], c["target"], c["be_trig"]
    rem, ptk, be = c["rem"], c["partial"], c["be"]
    pnl = c["pnl0"]
    ad, tk = c["ad"], c["ticker"]
    dmap = daily.get(tk, {})
    prior = [dmap[d]["c"] for d in sorted(dmap) if d < ad and dmap[d]["c"] is not None]
    held = []
    broker = round(entry, 2) if be else round(hard, 2)          # the A0 resting stop, live semantics
    if line_seed:
        broker = max(broker, line_seed)
    info = {"line_tests": [], "fires": [], "unreadable": [], "fallback": [], "gap": False,
            "exit_day": None, "exit_px": None, "reason": None, "exit_min": None}
    d = ad
    while True:
        d += timedelta(days=1)
        if d > horizon:
            mark = pnl + ((held[-1] if held else entry) - entry) * rem
            return "open", None, mark, info
        if d.weekday() >= 5:
            continue
        b = dmap.get(d)
        if not b or None in (b["o"], b["h"], b["l"], b["c"]):
            continue
        floor = entry if be else hard
        line = broker                                   # what A0 holds at the broker today
        governed = line > round(floor, 2) + 1e-9
        rest = line if arm == "A0" else round(floor, 2)
        mb, s_ = bars_for(src, (tk, d), False)
        if governed and b["l"] <= line:
            info["line_tests"].append((d, line, b["l"], b["c"], len(mb)))
            if not mb and arm == "A2":
                info["unreadable"].append(d)
        done = False
        # minute grain
        wins, order, breached, bw, run = {}, [], False, None, 0
        for i, x in enumerate(mb):
            # A2: a signal completed at the previous window's close executes at THIS bar's open
            if arm == "A2" and governed:
                wn = wnum(x["m"])
                if order and wn != order[-1]:
                    pw = order[-1]
                    W = wins[pw]
                    ok = breached and pw > bw and len(order) >= 2 and order[-2] == pw - 1
                    sl = ok and W["l"] < wins[order[-2]]["l"] and W["h"] > W["l"] and W["c"] <= W["l"] + (W["h"] - W["l"]) / 3
                    run = run + 1 if sl else 0
                    if run >= k and W["c"] < line:
                        pnl += (x["o"] - entry) * rem
                        info.update(exit_day=d, exit_px=x["o"], reason="slice", exit_min=x["m"].time())
                        info["fires"].append((d, x["m"].time(), x["o"], line, b["c"]))
                        rem = 0
                        done = True
                        break
            if not be and x["h"] >= bet:
                if rest < entry and x["l"] <= entry:
                    info["reason"] = f"abstain_be_same_bar {d}"
                    return "abstain", None, None, info
                be = True
                rest = max(rest, round(entry, 2))
                broker = max(broker, round(entry, 2))
            if x["l"] <= rest:
                px = min(x["o"], rest)
                info["gap"] |= px < rest
                pnl += (px - entry) * rem
                info.update(exit_day=d, exit_px=px, reason="stop", exit_min=x["m"].time())
                rem = 0
                done = True
                break
            if tgt is not None and not ptk and x["h"] >= tgt:
                q = rem / 3
                pnl += (tgt - entry) * q
                rem -= q
                ptk = True
                be = True
                rest = max(rest, round(entry, 2))
                broker = max(broker, round(entry, 2))
            if arm == "A2" and governed:
                if not breached and x["l"] <= line:
                    breached, bw = True, wnum(x["m"])
                wn = wnum(x["m"])
                if not order or order[-1] != wn:
                    order.append(wn)
                    wins[wn] = dict(o=x["o"], h=x["h"], l=x["l"], c=x["c"])
                else:
                    W = wins[wn]
                    W["h"] = max(W["h"], x["h"]); W["l"] = min(W["l"], x["l"]); W["c"] = x["c"]
        if not done and arm == "A2" and governed and order:
            pw = order[-1]
            W = wins[pw]
            ok = breached and pw > bw and len(order) >= 2 and order[-2] == pw - 1
            sl = ok and W["l"] < wins[order[-2]]["l"] and W["h"] > W["l"] and W["c"] <= W["l"] + (W["h"] - W["l"]) / 3
            run = run + 1 if sl else 0
            if run >= k and W["c"] < line:
                pnl += (W["c"] - entry) * rem
                info.update(exit_day=d, exit_px=W["c"], reason="slice_eod")
                info["fires"].append((d, "eod", W["c"], line, b["c"]))
                rem = 0
                done = True
        if done:
            return "settled", pnl, None, info
        if not mb:
            info["fallback"].append(d)
            if not be and b["h"] >= bet:
                if rest < entry and b["l"] <= entry:
                    info["reason"] = f"abstain_be_same_day {d}"
                    return "abstain", None, None, info
                be = True
                rest = max(rest, round(entry, 2))
                broker = max(broker, round(entry, 2))
            if tgt is not None and not ptk and b["h"] >= tgt:
                if b["l"] <= rest:
                    info["reason"] = f"abstain_tgt_same_day {d}"
                    return "abstain", None, None, info
                q = rem / 3
                pnl += (tgt - entry) * q
                rem -= q
                ptk = True
                be = True
                rest = max(rest, round(entry, 2))
                broker = max(broker, round(entry, 2))
            if b["l"] <= rest:
                px = min(b["o"], rest)
                info["gap"] |= px < rest
                pnl += (px - entry) * rem
                info.update(exit_day=d, exit_px=px, reason="stop_daily")
                return "settled", pnl, None, info
        # 16:45 job, live formula: eff = max(ORIGINAL hard stop, max(SMA10,SMA20) incl today, entry if BE)
        held.append(b["c"])
        tl = sma_line(prior + held)
        eff = hard
        if tl is not None and tl > eff:
            eff = tl
        if be and entry > eff:
            eff = entry
        if b["c"] < eff:
            pnl += (b["c"] - entry) * rem
            info.update(exit_day=d, exit_px=b["c"], reason="close_below")
            return "settled", pnl, None, info
        if stop_rounding:
            if eff > broker + 0.01:
                broker = round(eff, 2)
        else:
            broker = max(broker, eff)


# ── main ───────────────────────────────────────────────────────────────────────────

def main():
    S, raw, daily, regime, adv, src, mincov = load()
    regime_rows = sorted(regime.values(), key=lambda r: r["regime_date"])
    rs = ep.RULESETS["era_d"]

    # ── (1a) ANCHOR: the 09-06 originals vs today's regenerated files, and my own paired sum
    P = "check_anchor"
    for nm in ("intraday", "closeonly"):
        a = (ep.DATA / f"campaigns_era_c_rec_{nm}_uc0.tsv").read_bytes()
        b = (HERE / f"anchor_{nm}.tsv").read_bytes()
        w(P, f"09-06 original campaigns_era_c_rec_{nm}_uc0.tsv vs study anchor_{nm}.tsv: byte-identical={a == b} ({len(a)} vs {len(b)} bytes)")

    def rd(p):
        with open(p) as fh:
            return {(r["ticker"], r["alert_date"]): r for r in csv.DictReader(fh, delimiter="|")}
    A = rd(ep.DATA / "campaigns_era_c_rec_intraday_uc0.tsv")
    B = rd(ep.DATA / "campaigns_era_c_rec_closeonly_uc0.tsv")
    adm = [k for k in A if A[k]["admit"] == "admit"]
    both = [k for k in adm if A[k]["status"] == "settled" and B[k]["status"] == "settled"]
    sa = sum(float(A[k]["realized_r"]) for k in both); sb = sum(float(B[k]["realized_r"]) for k in both)
    dif = [k for k in both if abs(float(A[k]["realized_r"]) - float(B[k]["realized_r"])) > 1e-9]
    worse = sum(1 for k in dif if float(B[k]["realized_r"]) < float(A[k]["realized_r"]))
    w(P, f"09-06 ORIGINAL files, re-admitted, settled in both: n={len(both)} intraday {sa:+.2f} close-only {sb:+.2f} diff {sb - sa:+.2f}; differ {len(dif)}, close-only worse on {worse}")
    w(P, f"   intraday settled {sum(1 for k in adm if A[k]['status']=='settled')} / close-only settled {sum(1 for k in adm if B[k]['status']=='settled')} of {len(adm)} re-admitted")
    for k in sorted(dif, key=lambda k: float(B[k]['realized_r']) - float(A[k]['realized_r'])):
        w(P, f"   {k[0]:6s} {k[1]} intraday {float(A[k]['realized_r']):+.2f} close-only {float(B[k]['realized_r']):+.2f} ({float(B[k]['realized_r']) - float(A[k]['realized_r']):+.2f})")

    # ── (1b) POPULATION, re-derived
    P = "check_population"
    seen = {}
    for a in raw:
        kk = (a["ticker"], a["alert_date"])
        if kk not in seen or (a.get("detected_at_et") or "") < (seen[kk].get("detected_at_et") or ""):
            seen[kk] = a
    alerts = sorted((a for a in seen.values() if a["alert_date"] <= HORIZON.isoformat()), key=lambda a: (a["alert_date"], a["ticker"]))
    w(P, f"raw live-alert rows {len(raw)} -> ticker-days {len(seen)} -> <= {HORIZON}: {len(alerts)} ({alerts[0]['alert_date']} .. {alerts[-1]['alert_date']}); excluded after horizon: {sorted(k for k in seen if k[1] > HORIZON.isoformat())}")
    ep.LAST_SETTLED = HORIZON
    camps = {}
    for a in alerts:
        ad, sc = ep._score_one(a, rs, daily, adv, regime_rows)
        submit = time(9, 31)
        if a.get("detected_at_et"):
            t = datetime.fromisoformat(a["detected_at_et"]).time()
            submit = max(submit, time(t.hour, t.minute))
        mins0 = {(a["ticker"], ad): bars_for(src, (a["ticker"], ad), True)[0]}
        res = ep.walk_campaign(ticker=a["ticker"], alert_date=ad, rs=rs, minutes=mins0, daily=daily, submit=submit)
        res.update(admit=sc["admit"], tier=a.get("score_tier"), submit=submit, alert=a)
        camps[(a["ticker"], ad)] = res
    widened = {k for k, r in camps.items() if r["admit"] == "admit" or (r["admit"].startswith("abstain") and r["tier"] == "HIGH")}
    prereg = {k for k, r in camps.items() if r["admit"] == "admit"}
    w(P, f"re-admitted {len(prereg)}; + live HIGH straddling the bar {len(widened) - len(prereg)} = {len(widened)}")
    w(P, f"statuses (widened): {dict(Counter(camps[k]['status'] for k in widened))}")
    w(P, f"admit classes, all alerts: {dict(Counter(r['admit'] for r in camps.values()))}")
    # every real live MAGNA53 fill since 08-01 (the capture's TRADES) — is it in the population?
    live = [t for t in S["TRADES"] if t["status"] in ("closed", "filled")]
    w(P, "live MAGNA53 fills since 08-01 vs the replay population:")
    for t in live:
        kk = (t["ticker"], date.fromisoformat(t["alert_date"]))
        r = camps.get(kk)
        if r is None:
            w(P, f"   {t['ticker']:5s} {t['alert_date']} NOT AN ALERT IN THE WINDOW (live closed {t['closed_at_et'][:16]})")
            continue
        w(P, f"   {t['ticker']:5s} {t['alert_date']} in-widened={kk in widened} admit={r['admit']} tier={r['tier']} replay={r['status']}:{r['reason']} submit={r['submit']} score=[{r.get('score_lo')},{r.get('score_hi')}]")
    # ── day-0 end state (harness, horizon = the alert day) for every widened entered campaign
    states = {}
    day0_settled = {}
    for kk in sorted(widened, key=lambda k: (k[1], k[0])):
        r = camps[kk]
        if not r["entered"] or r["status"] in ("no_trade", "no_entry"):
            continue
        if r["status"] == "abstain" and not str(r["reason"]).startswith("fwd_"):
            continue
        tk, ad = kk
        b0 = bars_for(src, kk, True)[0]
        ep.LAST_SETTLED = ad
        r0 = ep.walk_campaign(ticker=tk, alert_date=ad, rs=rs, minutes={kk: b0}, daily=daily, submit=r["submit"])
        ep.LAST_SETTLED = HORIZON
        if r0["status"] == "settled":
            day0_settled[kk] = r0["realized_r"]
            continue
        if r0["status"] != "open_at_horizon":
            w(P, f"   day-0 odd status {kk}: {r0['status']} {r0['reason']}")
            continue
        orb = next(x for x in b0 if x["m"].time() == time(9, 30))
        entry, hard = r0["entry_px"], r0["stop"]
        rps = profit_target_r_per_share("magna53", entry, hard, orb["l"])
        bet = entry + 3.0 * rps
        fill = ep.entry_walk(b0, orb["h"], r["submit"], rs.entry_cancel)
        be = any(x["m"] >= fill["minute"] and x["h"] >= bet for x in b0)
        sh = 1.0 / (entry - hard)
        ex = r0["exits"]
        partial = any(e["reason"] == "partial_profit" for e in ex)
        states[kk] = dict(ticker=tk, ad=ad, entry=entry, hard=hard, target=r0["target"], be_trig=bet,
                          rem=sh - sum(e["shares"] for e in ex), partial=partial, be=be or partial,
                          pnl0=sum(e["pnl"] for e in ex), adr=r0["adr_pct"])
    w(P, f"entered + walkable: day-0 settled {len(day0_settled)}, reached day 1 {len(states)}, total {len(day0_settled) + len(states)}")

    # ── (3) RECOMPUTE A0 / A1 / A2k2 with the own walker
    P = "check_recompute"
    res = {a: {} for a in ("A0", "A1", "A2")}
    for kk, st in states.items():
        for a in res:
            res[a][kk] = walk(st, a, daily, src)
    study = {}
    with open(HERE / "arms_per_trade.tsv") as fh:
        for r in csv.DictReader(fh, delimiter="|"):
            study[(r["ticker"], date.fromisoformat(r["alert_date"]))] = r
    w(P, f"campaigns walked from day 1: {len(states)} (study: 51); day-0 settled {len(day0_settled)} (study: 35)")
    missing = set(study) - set(states) - set(day0_settled)
    extra = (set(states) | set(day0_settled)) - set(study)
    w(P, f"campaign-set agreement with the study: missing-from-mine {sorted(missing)} extra-in-mine {sorted(extra)}")
    col = {"A0": "A0", "A1": "A1", "A2": "A2k2"}
    mism = []
    for a in res:
        agree = 0
        for kk, (stt, R, mark, info) in res[a].items():
            s = study.get(kk)
            if s is None:
                continue
            sR = s[f"{col[a]}_R"]; sM = s[f"{col[a]}_markR"]
            mine = R if stt == "settled" else mark
            theirs = f(sR) if sR else f(sM)
            if mine is not None and theirs is not None and abs(mine - theirs) < 0.005 and (stt == "settled") == (s[f"{col[a]}_status"] == "settled"):
                agree += 1
            else:
                mism.append((a, kk, stt, mine, s[f"{col[a]}_status"], theirs, info["reason"], info["exit_day"], s[f"{col[a]}_final"], s[f"{col[a]}_exit_day"]))
        w(P, f"{a}: my walk agrees with study {col[a]} within 0.005R on {agree} of {len(res[a])}")
    for m in mism:
        w(P, "   DIFF", m[0], m[1][0], m[1][1], f"mine {m[2]} {m[3] if m[3] is None else round(m[3], 3)} ({m[6]} {m[7]})", f"study {m[4]} {m[5]} ({m[8]} {m[9]})")
    # paired totals A0 vs A2 over: every campaign settled in both + day-0 settled, excluding A2-unreadable
    for label, pop in (("WIDENED", widened), ("PRE-REGISTERED", prereg)):
        keys = [k for k in states if k in pop]
        d0 = [k for k in day0_settled if k in pop]
        paired = [k for k in keys if res["A0"][k][0] == "settled" and res["A2"][k][0] == "settled" and res["A1"][k][0] == "settled" and not res["A2"][k][3]["unreadable"]]
        R0 = {k: res["A0"][k][1] for k in paired}; R0.update({k: day0_settled[k] for k in d0})
        R1 = {k: res["A1"][k][1] for k in paired}; R1.update({k: day0_settled[k] for k in d0})
        R2 = {k: res["A2"][k][1] for k in paired}; R2.update({k: day0_settled[k] for k in d0})
        ks = sorted(R0, key=lambda k: (k[1], k[0]))
        ks_disc = [k for k in ks if k[1] <= SPLIT]
        for bl, kset in (("ALL", ks), ("DISC", ks_disc)):
            s0 = sum(R0[k] for k in kset); s1 = sum(R1[k] for k in kset); s2 = sum(R2[k] for k in kset)
            d2 = [R2[k] - R0[k] for k in kset]; d1 = [R1[k] - R0[k] for k in kset]
            wk = [f"{k[1].isocalendar()[1]}" for k in kset]
            w(P, f"{label} {bl}: paired n={len(kset)} A0 {s0:+.2f} A1 {s1:+.2f} ({s1 - s0:+.2f}, p {perm(d1, wk):.3f}, better/worse {sum(x > 1e-9 for x in d1)}/{sum(x < -1e-9 for x in d1)}) "
                 f"A2k2 {s2:+.2f} ({s2 - s0:+.2f}, p {perm(d2, wk):.3f}, better/worse {sum(x > 1e-9 for x in d2)}/{sum(x < -1e-9 for x in d2)})")
            for a_, RR in (("A0", R0), ("A1", R1), ("A2k2", R2)):
                orb = {k: RR[k] * 2.0 for k in kset}      # 1 money-R = 2 ORB-R (stop = entry - 2 ORB-R)
                big = sorted((round(RR[k], 2), k[0]) for k in kset if orb[k] >= 3)
                w(P, f"     {a_}: >=3 ORB-R {len(big)} {big}; >=8 ORB-R {sum(1 for k in kset if orb[k] >= 8)}; worst {min(RR[k] for k in kset):+.2f}; drop-best-2 {sum(sorted(RR[k] for k in kset)[:-2]):+.2f}")
        if label == "WIDENED":
            w(P, "per-trade where A0 / A1 / A2k2 differ (mine):")
            for k in paired:
                if abs(R2[k] - R0[k]) > 1e-9 or abs(R1[k] - R0[k]) > 1e-9:
                    i0, i1, i2 = res["A0"][k][3], res["A1"][k][3], res["A2"][k][3]
                    w(P, f"   {k[0]:6s} {k[1]} A0 {R0[k]:+.2f} ({i0['reason']} {i0['exit_day']} {i0['exit_min']} @{i0['exit_px']:.2f}) "
                         f"A1 {R1[k]:+.2f} ({i1['reason']} {i1['exit_day']}) A2k2 {R2[k]:+.2f} ({i2['reason']} {i2['exit_day']} {i2['exit_min']})")
            unread = sorted({k[0] for k in keys if res["A2"][k][3]["unreadable"]})
            w(P, f"A2-unreadable campaigns (a line-test day with no minute bars): {unread}")
    # ── (2) FIDELITY vs live, the line itself: OKTA's 14 stop moves
    P = "check_fidelity"
    ok = daily["OKTA"]; ad = date(2026, 8, 27)
    prior = [ok[d]["c"] for d in sorted(ok) if d < ad]
    orders = [r for r in S["OKTA_ORDERS"] if r.get("purpose") == "stop_loss"]
    live_moves = {r["submitted_et"][:10]: float(r["stop_price"]) for r in orders if r["submitted_et"][11:13] == "16"}
    held_x0, held_w0 = [], [ok[ad]["c"]]
    brk = 150.52
    w(P, "OKTA stop line, own SMA vs the live broker stop set at 16:45 (window without / with the entry-day close):")
    n_match = 0
    for d in sorted(x for x in ok if ad < x <= HORIZON):
        held_x0.append(ok[d]["c"]); held_w0.append(ok[d]["c"])
        a_ = sma_line(prior + held_x0); b_ = sma_line(prior + held_w0)
        lv = live_moves.get(d.isoformat())
        eff = max(150.52, a_, 167.879 if d >= date(2026, 9, 22) else 0)
        mv = round(eff, 2) if eff > brk + 0.01 else None
        if mv:
            brk = mv
        tag = ""
        if lv is not None:
            tag = "MATCH" if mv is not None and abs(mv - lv) < 0.005 else "MISMATCH"
            n_match += tag == "MATCH"
        w(P, f"   {d} close {ok[d]['c']:.2f} low {ok[d]['l']:.2f} line(no d0) {a_:.2f} line(with d0) {b_:.2f} -> my broker move {mv} | live move {lv} {tag}"
             + ("  <- close below the line: live 16:45 sale sent (rejected)" if ok[d]['c'] < a_ else ""))
    w(P, f"   OKTA live stop moves matched by the own line: {n_match} of {len(live_moves)}")
    # A0 exit vs the live exit on every live fill in the population
    w(P, "A0 (own walker) vs the live exit, every live fill since 08-01 that the replay walks:")
    for t in live:
        kk = (t["ticker"], date.fromisoformat(t["alert_date"]))
        ex = json.loads(t["exits_json"] or "[]")
        last = ex[-1] if ex else {}
        rk = f(t["entry_price"]) - f(t["hard_stop"]) if f(t["hard_stop"]) else None
        sh = sum(float(e.get("shares", 0)) for e in ex) or f(t["entry_shares"]) or 0
        rl = (f(t["total_pnl"]) / (rk * sh)) if (rk and sh and f(t["total_pnl"]) is not None) else float("nan")
        lv = f"live {t['status']} {str(last.get('time',''))[:16]} {last.get('reason','')} @{last.get('price','')} stop_price {t['stop_price']} hard {t['hard_stop']} R_live(own risk basis) {rl:+.2f}"
        if kk in day0_settled:
            w(P, f"   {kk[0]:5s} {kk[1]} replay: stopped day 0 {day0_settled[kk]:+.2f} | {lv}")
        elif kk in states:
            stt, R, mark, info = res["A0"][kk]
            w(P, f"   {kk[0]:5s} {kk[1]} replay A0: {stt} {R if R is None else round(R, 2)} {info['reason']} {info['exit_day']} {info['exit_min']} @{info['exit_px']} | {lv}")
        else:
            r = camps.get(kk)
            w(P, f"   {kk[0]:5s} {kk[1]} replay: not walked ({r['status'] if r else 'no alert'}:{r['reason'] if r else ''}) | {lv}")
    # OKTA 09-28 under A0 with the live broker stop 193.25 seeded, and under A2
    st_ok = dict(ticker="OKTA", ad=date(2026, 9, 25), entry=167.879, hard=150.52, target=167.879 + 8 * (167.879 - 159.20),
                 be_trig=167.879 + 3 * (167.879 - 159.20), rem=1 / (167.879 - 150.52), partial=False, be=True, pnl0=0.0)
    dd = dict(daily); bars = src["new"].get(("OKTA", date(2026, 9, 28)), [])
    dd["OKTA"] = dict(daily["OKTA"]); dd["OKTA"][date(2026, 9, 28)] = {"o": bars[0]["o"], "h": max(x["h"] for x in bars), "l": min(x["l"] for x in bars), "c": bars[-1]["c"], "v": None}
    for a in ("A0", "A2"):
        stt, R, mark, info = walk(st_ok, a, dd, src, horizon=date(2026, 9, 28), line_seed=193.25)
        w(P, f"OKTA 09-28 {a}: {stt} R={R if R is None else round(R, 3)} mark={mark if mark is None else round(mark, 3)} {info['reason']} {info['exit_min']} @{info['exit_px']} (live: 191.50 at 09:30:01 = {(191.5 - 167.879) / (167.879 - 150.52):+.3f}R); first bar {bars[0]}")

    # ── (4) would a BROKEN replay give the same headline?
    P = "check_broken"
    lt_all = [(k, x) for k in states for x in res["A1"][k][3]["line_tests"]]
    w(P, f"line-test days on the A1 path (own walker): {len(lt_all)} on {len({k for k, _ in lt_all})} campaigns; reclaim {sum(1 for _, x in lt_all if x[3] >= x[1])} / slice {sum(1 for _, x in lt_all if x[3] < x[1])}; with minute bars {sum(1 for _, x in lt_all if x[4])}")
    below = full = 0
    for k, (d, line, lo, cl, nb) in lt_all:
        mb, s_ = bars_for(src, (k[0], d), False)
        if not mb:
            w(P, f"   {k[0]:6s} {d} line {line:.2f} daily low {lo:.2f} close {cl:.2f} NO MINUTE BARS (prod MINCOV n={mincov.get((k[0], d))})")
            continue
        ml = min(x["l"] for x in mb)
        below += ml <= line
        full += len(mb) >= 385
        w(P, f"   {k[0]:6s} {d} line {line:.2f} daily low {lo:.2f} minute low {ml:.2f} ({'below' if ml <= line else 'NOT BELOW'}) close {cl:.2f} {'RECLAIM' if cl >= line else 'SLICE'} bars {len(mb)} [{s_}] first {mb[0]['m'].strftime('%H:%M')} last {mb[-1]['m'].strftime('%H:%M')}")
    w(P, f"minute bars reach the line on {below} of {sum(1 for _, x in lt_all if bars_for(src, (_[0], x[0]), False)[0])} readable line-test days; full sessions (>=385 bars) {full}")
    # prod coverage vs captured coverage on the unreadable days
    fires = [(k, x) for k in states for x in res["A2"][k][3]["fires"]]
    w(P, f"A2k2 fires (own walker): {len(fires)}, false sells (closed at/above the line) {sum(1 for _, x in fires if x[4] >= x[3])}")
    for k, x in fires:
        w(P, f"   {k[0]:6s} {x[0]} {x[1]} @{x[2]:.2f} line {x[3]:.2f} close {x[4]:.2f} {'FALSE' if x[4] >= x[3] else 'slice'}")
    # A3 catastrophic stop: reachable? (read the study's own per-trade output + my recompute of the level)
    sj = json.load(open(HERE / "arms_results.json"))
    a3 = [(kk, v) for kk, v in sj["A3"].items() if v["final_reason"] == "stop_hit" and v["exit_day"] and v["exit_day"] != kk.split("|")[1]]
    w(P, f"A3 stop_hit exits after day 0 in the study: {len(a3)}")
    for kk, v in a3:
        tk, ad_ = kk.split("|"); st = states.get((tk, date.fromisoformat(ad_)))
        if not st:
            continue
        a0v = sj["A0"][kk]
        w(P, f"   {kk} A3 {v['realized_r']:+.2f} on {v['exit_day']} (A0 {a0v['realized_r']:+.2f} {a0v['exit_day']}); floor {'entry' if st['be'] else 'hard'} adr {st['adr']}")

    extra_checks(S, daily, src, mincov, states, res, study, camps, live)

    for name, lines in OUT.items():
        (HERE / f"{name}.txt").write_text("\n".join(lines) + "\n")
        print(f"== {name} ==")
        print("\n".join(lines))


def extra_checks(S, daily, src, mincov, states, res, study, camps, live):
    # ── (3b) how much of the headline is FTK + INFQ? paired totals with the two removed ─────
    P = "check_recompute"
    arms = ("A0", "A1", "A2k2", "A2k3", "A3")
    pk = [k for k, r in study.items() if all(r[f"{a}_status"] == "settled" and r[f"{a}_unreadable"] == "False" for a in arms)]
    w(P, f"LEAVE-TWO-OUT on the study's own per-trade file (paired n={len(pk)}; FTK 08-03 and INFQ 05-21 removed from the PAIRING, not per-arm drop-best-two):")
    for a in arms[1:]:
        dall = sum(float(study[k][f"{a}_R"]) - float(study[k]["A0_R"]) for k in pk)
        two = [k for k in pk if k[0] in ("FTK", "INFQ")]
        dtwo = sum(float(study[k][f"{a}_R"]) - float(study[k]["A0_R"]) for k in two)
        w(P, f"   {a:5s} vs A0: all {dall:+.2f} | FTK+INFQ alone {dtwo:+.2f} | the other {len(pk) - len(two)} trades {dall - dtwo:+.2f}")
    # FTK 08-17: the A0 fill in a 35.60 -> 31.20 first minute
    ftk = states[("FTK", date(2026, 8, 3))]
    b = src["562bf"][("FTK", date(2026, 8, 17))][:3]
    w(P, "FTK 08-17 first minutes (o/h/l/c): " + "; ".join(f"{x['m'].strftime('%H:%M')} {x['o']}/{x['h']}/{x['l']}/{x['c']}" for x in b) + " | daily open " + str(daily["FTK"][date(2026, 8, 17)]["o"]))
    rk = ftk["entry"] - ftk["hard"]
    part = 1.0 / 3 * (ftk["target"] - ftk["entry"]) / rk     # the +8 ORB-R partial A0 took before 08-17
    for px in (34.35, 33.50, 32.70, 32.11, 31.20):
        r0 = part + 2.0 / 3 * (px - ftk["entry"]) / rk
        w(P, f"   A0 FTK if the resting stop at 34.35 filled at {px:.2f}: {r0:+.2f}R (booked +6.27); close-only (28.66) +3.22 -> A1-A0 on FTK {3.2151 - r0:+.2f}"
             + ("  [= the A3 catastrophic stop level, same minute]" if px == 32.11 else "") + ("  [= the minute's low]" if px == 31.20 else ""))
    for px in (32.70, 31.20):
        r0 = part + 2.0 / 3 * (px - ftk["entry"]) / rk
        d1 = -4.08 + (6.2742 - r0)
        d2 = -4.02 + (6.2742 - r0)
        w(P, f"   => headline if FTK's A0 fill were {px:.2f}: A1 vs A0 {d1:+.2f} (was -4.08), A2k2 vs A0 {d2:+.2f} (was -4.02)")
    # THC / U bound (prod HAS the bars; the capture does not)
    for k in (("THC", date(2026, 7, 24)), ("U", date(2026, 8, 6))):
        r = res["A1"].get(k); r0 = res["A0"].get(k)
        if r and r0:
            w(P, f"   capture-gap trade {k[0]} {k[1]}: A0 {r0[1]:+.2f} close-only {r[1]:+.2f} ({r[1] - r0[1]:+.2f}) — the 5-arm pairing excludes it; the signature arms land between A0's exit and the close-only exit only if they fire on the same day")

    # ── (4b) coverage of the 'readable' line-test days
    P = "check_broken"
    lt = [(k, x) for k in states for x in res["A1"][k][3]["line_tests"]]
    part_days = []
    for k, (d, line, lo, cl, nb) in lt:
        mb, _ = bars_for(src, (k[0], d), False)
        if mb and len(mb) < 385:
            part_days.append((k[0], d, len(mb)))
    w(P, f"PARTIAL SESSIONS among the readable line-test days (< 385 of 390 one-minute bars): {len(part_days)} — {part_days}")
    fires = [(k, x) for k in states for x in res["A2"][k][3]["fires"]]
    on_part = [(k[0], x[0], 'FALSE' if x[4] >= x[3] else 'slice') for k, x in fires if any(p[0] == k[0] and p[1] == x[0] for p in part_days)]
    w(P, f"A2k2 fires on partial sessions: {on_part}")
    unread = [(k[0], d, mincov.get((k[0], d))) for k, (d, line, lo, cl, nb) in lt if not bars_for(src, (k[0], d), False)[0]]
    w(P, f"UNREADABLE line-test days {len(unread)}; prod (MINCOV, pulled 16:57Z) HAS bars on {sum(1 for u in unread if u[2])}: {[u for u in unread if u[2]]}; truly absent in prod: {[u for u in unread if not u[2]]}")

    # ── (2b) the two HELD-OUT live positions the replay does not reproduce
    P = "check_fidelity"
    import ep_replay as _ep
    w(P, f"HOOD 09-03: alert detected 09:35 (submit 09:35); harness entry = stop-limit at ORB high 115.90 capped at {_ep.stop_limit_buy_price(115.9)} -> "
         f"'{camps[('HOOD', date(2026, 9, 3))]['reason']}'; live FILLED 118.37 at 09:36:09 (above the harness cap) — a real live trade the replay cannot enter")
    for tk, ad, entry, hard, orb_low in (("SEI", date(2026, 9, 8), 62.8078, 57.82, 60.30), ("HOOD", date(2026, 9, 3), 118.37, 110.18, 113.04)):
        rps = entry - orb_low
        st = dict(ticker=tk, ad=ad, entry=entry, hard=hard, target=entry + 8 * rps, be_trig=entry + 3 * rps,
                  rem=1 / (entry - hard), partial=False, be=False, pnl0=0.0)
        w(P, f"LIVE-PATH READ {tk} (seeded with the LIVE fill {entry} and hard stop {hard}; +3R arm {entry + 3 * rps:.2f}) — what the live position would have done under each arm, NOT a population result:")
        for a in ("A0", "A1", "A2"):
            stt, R, mark, info = walk(st, a, daily, src)
            lts = [(str(x[0]), round(x[1], 2), x[2], x[3], x[4]) for x in info["line_tests"]]
            w(P, f"   {a}: {stt} R={R if R is None else round(R, 2)} mark={mark if mark is None else round(mark, 2)} {info['reason']} {info['exit_day']} {info['exit_min']} @{info['exit_px']}; line tests (day, line, low, close, bars) {lts}")
    ex = {t["ticker"]: t for t in live}
    for tk in ("SEI", "HOOD"):
        t = ex[tk]
        w(P, f"   live {tk}: closed {t['closed_at_et'][:16]} exits {t['exits_json'][:160]} stop_price {t['stop_price']} breakeven_active {t['breakeven_active']}")
    for d in ("2026-09-11", "2026-09-14", "2026-09-18", "2026-09-22"):
        b = daily["SEI"][date.fromisoformat(d)]
        w(P, f"   SEI {d} o/h/l/c {b['o']}/{b['h']}/{b['l']}/{b['c']}  (replay +3R arm 70.22 from the ORB-high entry 62.78; live arm 70.33 from the 62.8078 fill)")
    for d in ("2026-09-12", "2026-09-15", "2026-09-16", "2026-09-17"):
        b = daily["HOOD"].get(date.fromisoformat(d))
        if b:
            w(P, f"   HOOD {d} o/h/l/c {b['o']}/{b['h']}/{b['l']}/{b['c']}")


def perm(diffs, weeks, n=5000, seed=7):
    obs = abs(sum(diffs))
    if obs == 0:
        return 1.0
    g = defaultdict(float)
    for x, wk in zip(diffs, weeks):
        g[wk] += x
    vals = list(g.values())
    rng = random.Random(seed)
    hit = 0
    for _ in range(n):
        s = sum(v if rng.random() < 0.5 else -v for v in vals)
        hit += abs(s) >= obs - 1e-12
    return hit / n


if __name__ == "__main__":
    main()
