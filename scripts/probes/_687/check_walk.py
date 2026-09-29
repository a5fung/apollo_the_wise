"""#687 INDEPENDENT CHECK (3)+(4) — my own entry and exit walkers, written from the stated rules and the LIVE code
(order_manager.submit_entry / _build_order_spec stop = 2L - H, stop_limit_buy_price, CHASE_RISK_INFLATION_CAP;
exit_logic.apply_daily_exit_step read, NOT imported). No import of backfill.py, study.py, ep_replay.py or exit_logic.py.
Reads captured files only (population.tsv, pull_daily_out.txt, minutes_*.tsv.gz, arms_per_trade.tsv, check_pull_out.txt).
Writes check_entry.txt, check_exit.txt, check_walks.txt (hand-walk logs) and check_mine_per_trade.tsv."""
from __future__ import annotations

import collections
import csv
import gzip
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
HZ = date(2026, 8, 31)
CHASE_CAP = 1.5          # order_manager.CHASE_RISK_INFLATION_CAP default
PARTIAL_R, BE_R = 8.0, 3.0
MUT_D0_CLOSE = False   # mutation switch for check (6): include the entry-day close in the trail (a plausible off-by-one)

def slb(h):              # order_manager.stop_limit_buy_price, re-typed
    return round(max(h * 1.005, h + 0.02), 2)

# ── data ──
def load_daily():
    out = collections.defaultdict(dict)
    for line in open(HERE / "pull_daily_out.txt"):
        p = line.rstrip("\n").split("|")
        if len(p) != 7 or p[0] == "ticker" or p[0].startswith("==="):
            continue
        try:
            d = date.fromisoformat(p[1])
            out[p[0]][d] = tuple(float(x) if x not in ("", None) else None for x in p[2:7])  # o h l c v
        except ValueError:
            continue
    return out

def load_min(names):
    by = collections.defaultdict(dict)
    for n in names:
        with gzip.open(HERE / n, "rt") as fh:
            for line in fh:
                p = line.rstrip("\n").split("|")
                if len(p) < 6:
                    continue
                dt = datetime.strptime(p[1], "%Y-%m-%d %H:%M")
                by[(p[0], dt.date())][dt.time()] = (float(p[2]), float(p[3]), float(p[4]), float(p[5]))
    return {k: sorted(v.items()) for k, v in by.items()}

def atr_from_pull():
    """My own ATR14 per (ticker, day) from check_pull_out.txt (SQL lateral), abs dollars; None under 10 rows."""
    out = {}; on = False; hdr = None
    for l in open(HERE / "check_pull_out.txt"):
        l = l.rstrip("\n")
        if l.startswith("=== "):
            on = l == "=== POP ==="; hdr = None; continue
        if not on:
            continue
        if hdr is None:
            hdr = l.split("|"); continue
        r = dict(zip(hdr, l.split("|")))
        n = int(r["atr_n"] or 0)
        out[(r["ticker"], date.fromisoformat(r["trade_date"]))] = float(r["atr14"]) if (n >= 10 and r["atr14"]) else None
    return out

# ── (3) entry: the live order path ──
def entry(bars, H, L, proxy="open931"):
    """bars: [(time, (o,h,l,c))] RTH. Returns dict(status, px, t, kind)."""
    stop = 2 * L - H
    sub = [(t, b) for t, b in bars if t >= time(9, 31)]
    if not sub:
        return {"status": "abstain", "why": "no_submit_bar"}
    t0, b0 = sub[0]
    if proxy == "open931":
        px = b0[0]
    else:   # the 09:30 bar's close (the last print strictly before 09:31:00)
        px = next(b for t, b in bars if t == time(9, 30))[3]
    if px > H:
        lim = round(px * 1.002, 2)
        if not (H - stop > 0 and lim - stop <= CHASE_CAP * (H - stop)):
            return {"status": "chase_cap_skip"}
        for t, b in sub:
            if t >= time(10, 0):
                break
            if b[2] <= lim:
                if t == t0:
                    return {"status": "filled", "px": min(b[0], lim), "t": t, "kind": "chase_open", "at_open": True}
                return {"status": "filled", "px": lim, "t": t, "kind": "chase_limit_later", "at_open": False}
        return {"status": "no_entry", "why": "limit_not_reached"}
    lim = slb(H); armed = False
    win = [(t, b) for t, b in sub if t < time(10, 0)]
    for t, b in win:
        o, h, l, c = b
        if armed:
            if l <= lim:
                return {"status": "filled", "px": lim, "t": t, "kind": "limit_pullback", "at_open": False}
            continue
        if o >= H:
            if o <= lim:
                return {"status": "filled", "px": o, "t": t, "kind": "open_in_band", "at_open": True}
            armed = True
            if l <= lim:
                return {"status": "filled", "px": lim, "t": t, "kind": "limit_pullback", "at_open": False}
        elif h >= H:
            return {"status": "filled", "px": H, "t": t, "kind": "cross", "at_open": False}
    if armed:
        return {"status": "no_entry", "why": "above_limit_never_back"}
    if len(win) < 29:
        return {"status": "abstain", "why": "entry_window_gaps"}
    return {"status": "no_entry", "why": "never_crossed"}

# ── (4) exits ──
class Abstain(Exception):
    pass

def adr20(db, before):
    pre = [db[d] for d in sorted(db) if d < before][-20:]
    v = [(b[1] - b[2]) / b[3] for b in pre if b[1] is not None and b[2] is not None and b[3]]
    return (sum(v) / len(v)) if len(v) >= 10 else None

def trail(prior, held_closes):
    xs = prior + held_closes
    s10 = sum(xs[-10:]) / 10 if len(xs) >= 10 else None
    s20 = sum(xs[-20:]) / 20 if len(xs) >= 20 else None
    if s20 is not None:
        return max(s10, s20)
    return s10

def walk(arm, T, D, f, H, L, db, m0, held, log=None):
    """One campaign under one arm. Returns (R, final, exit_day, info). Raises Abstain."""
    E = f["px"]; hard = 2 * L - H; rps = E - L
    tgt = E + PARTIAL_R * rps; bet = E + BE_R * rps
    risk = E - hard
    rem = 1.0; pnl = 0.0; partial = False; be = False; stop = hard
    def W(*a):
        if log is not None:
            log.append(" ".join(str(x) for x in a))
    # day 0
    idx = next(i for i, (t, _) in enumerate(m0) if t == f["t"])
    t, (o, h, l, c) = m0[idx]
    W(f"  D0 {D} fill {f['kind']} @{E:.4f} {t} | hard {hard:.4f} be@{bet:.4f} tgt@{tgt:.4f}")
    if l <= stop:
        if h >= tgt:
            raise Abstain("d0_fillbar_stop_tgt")
        if c < stop:
            W(f"  D0 fill bar {t} low {l} <= stop, closes below -> stopped @ {stop:.4f}")
            return (stop - E) / risk, "stop_hit", D, {"partial_day": None}
        raise Abstain("d0_fillbar_straddle")
    if h >= tgt and not f["at_open"]:
        pnl += (tgt - E) * rem / 3; rem -= rem / 3; partial = True; be = True; stop = max(stop, E)
        W(f"  D0 fill bar {t} partial 1/3 @ {tgt:.4f}")
    partial_day = D if partial else None
    if h >= bet:
        be = True; stop = max(stop, E)
    for t, (o, h, l, c) in m0[idx + 1:]:
        hs = l <= stop; ht = (not partial) and h >= tgt
        if hs and ht:
            raise Abstain("d0_stop_tgt")
        if (not be) and stop < E and h >= bet and l <= E:
            raise Abstain("d0_stop_be")
        if h >= bet and not be:
            be = True; stop = max(stop, E); W(f"  D0 {t} breakeven armed (high {h})")
        if hs:
            px = o if o < stop else stop
            pnl += (px - E) * rem
            W(f"  D0 {t} low {l} <= stop {stop:.4f} -> out @ {px:.4f}")
            return pnl / risk, "stop_hit", D, {"partial_day": partial_day}
        if ht:
            pnl += (tgt - E) * rem / 3; rem -= rem / 3; partial = True; be = True; stop = max(stop, E); partial_day = D
            W(f"  D0 {t} partial 1/3 @ {tgt:.4f}")
    if arm == "D0ONLY":
        return None, "reached_d1", None, {}
    # forward
    adr = adr20(db, D)
    prior = [db[d][3] for d in sorted(db) if (d <= D if MUT_D0_CLOSE else d < D) and db[d][3] is not None]
    hc = []
    line = hard if not be else max(hard, E)
    runner = arm.startswith(("T20", "S20"))
    post = None           # runner: sessions counted after P
    rfloor = None
    if runner and partial:          # the partial fired on day 0 -> runner rule from day 1
        rfloor = E if arm.endswith("_be") else hard
        post = 0
    d = D; last_close = None
    last_bar = max(db)
    while True:
        d += timedelta(days=1)
        if d > HZ:
            break
        if d.weekday() >= 5:
            continue
        b = db.get(d)
        if not b or b[3] is None or b[2] is None or b[1] is None:
            if d > last_bar:
                break
            continue
        o, h, l, c, v = b
        last_close = c
        # ── runner arm after the partial: daily grain, floor only ──
        if runner and post is not None:
            post += 1
            if l <= rfloor:
                px = o if (o is not None and o < rfloor) else rfloor
                pnl += (px - E) * rem
                W(f"  {d} runner floor {rfloor:.4f} touched (low {l}) -> out @ {px:.4f}")
                return pnl / risk, "stop_hit", d, {"partial_day": partial_day}
            if arm.startswith("T20") and post >= 20:
                pnl += (c - E) * rem
                W(f"  {d} 20th session after the partial -> sell the close {c}")
                return pnl / risk, "time_close", d, {"partial_day": partial_day}
            if arm.startswith("S20"):
                xs = [db[x][3] for x in sorted(db) if x <= d and db[x][3] is not None][-20:]
                if len(xs) == 20 and c < sum(xs) / 20:
                    pnl += (c - E) * rem
                    return pnl / risk, "sma20_close", d, {"partial_day": partial_day}
            continue
        floor = max(hard, E) if be else hard
        line = max(line, floor)
        lr = round(line, 2)
        gov = lr > round(floor, 2) + 1e-9
        if arm in ("A0",) or runner:
            rest = lr
        elif arm == "D10" and gov and adr:
            rest = max(round(floor, 2), round(lr - adr * lr, 2))
        else:
            rest = round(floor, 2)
        mb = held.get((T, d))
        stopped = None
        if mb:
            for t, (bo, bh, bl, bc) in mb:
                if (not be) and bh >= bet:
                    if rest < E and bl <= E:
                        raise Abstain(f"fwd_stop_be:{d}")
                    be = True; rest = max(rest, round(E, 2)); line = max(line, E)
                hs = bl <= rest; ht = (not partial) and bh >= tgt
                if hs and ht:
                    raise Abstain(f"fwd_stop_tgt:{d}")
                if hs:
                    px = bo if bo < rest else rest
                    stopped = (px, f"{d} {t}"); break
                if ht:
                    pnl += (tgt - E) * rem / 3; rem -= rem / 3; partial = True; be = True
                    rest = max(rest, round(E, 2)); line = max(line, E); partial_day = d
                    W(f"  {d} {t} partial 1/3 @ {tgt:.4f}")
                    if runner:
                        rfloor = E if arm.endswith("_be") else hard
                        post = 0
                        # rest of day P against the runner floor
                        for t2, (co, ch, cl, cc) in [x for x in mb if x[0] > t]:
                            if cl <= rfloor:
                                px = co if co < rfloor else rfloor
                                pnl += (px - E) * rem
                                W(f"  {d} {t2} runner floor touched on P -> out @ {px:.4f}")
                                return pnl / risk, "stop_hit", d, {"partial_day": partial_day}
                        break
            if runner and post is not None:
                hc.append(c)
                continue
        else:
            if (not be) and h >= bet:
                if rest < E and l <= E:
                    raise Abstain(f"fwd_stop_be_day:{d}")
                be = True; rest = max(rest, round(E, 2)); line = max(line, E)
            if (not partial) and h >= tgt:
                if l <= rest:
                    raise Abstain(f"fwd_stop_tgt_day:{d}")
                pnl += (tgt - E) * rem / 3; rem -= rem / 3; partial = True; be = True
                rest = max(rest, round(E, 2)); line = max(line, E); partial_day = d
                W(f"  {d} (daily) partial 1/3 @ {tgt:.4f}")
                if runner:
                    rfloor = E if arm.endswith("_be") else hard
                    post = 0
                    hc.append(c)
                    continue
            if l <= rest:
                px = o if (o is not None and o < rest) else rest
                stopped = (px, f"{d} daily")
        if stopped:
            pnl += (stopped[0] - E) * rem
            W(f"  {stopped[1]} low touched resting stop {rest:.2f} (line {lr}, floor {floor:.4f}) -> out @ {stopped[0]:.4f}")
            return pnl / risk, "stop_hit", d, {"partial_day": partial_day}
        # 16:45 job
        hc.append(c)
        sma = trail(prior, hc)
        eff = rest
        if sma is not None and sma > eff:
            eff = sma
        if be and E > eff:
            eff = E
        if c < eff:
            pnl += (c - E) * rem
            W(f"  {d} 16:45 close {c} < effective {eff:.4f} (sma {sma:.4f}, rest {rest:.2f}) -> sell the close")
            return pnl / risk, "close_below_line", d, {"partial_day": partial_day}
        if log is not None and (gov or l <= lr):
            W(f"  {d} held: o {o} l {l} c {c} | rest {rest:.2f} line {lr} -> next line {round(max(line, eff), 2)}")
        line = max(line, eff)
    lc = last_close if last_close is not None else E
    mark = (pnl + (lc - E) * rem) / risk
    if last_bar < HZ - timedelta(days=14):
        return mark, "delisted_forced_close", last_bar, {"partial_day": partial_day}
    return mark, "open_at_horizon", None, {"partial_day": partial_day}


def d0_hs_continuation(T, D, f, H, L, db, m0):
    """For a trade that fired the +8 partial on day 0 and was then stopped at breakeven on day 0: what T20_hs would do
    (after the partial the floor is the HARD stop, so the breakeven touch does not stop it)."""
    E = f["px"]; hard = 2 * L - H; rps = E - L; tgt = E + PARTIAL_R * rps; risk = E - hard
    idx = next(i for i, (t, _) in enumerate(m0) if t == f["t"])
    rem, pnl, seen = 1.0, 0.0, False
    for i, (t, (o, h, l, c)) in enumerate(m0[idx:]):
        if not seen:
            if h >= tgt and (i > 0 or not f["at_open"]):
                pnl += (tgt - E) / 3; rem = 2 / 3; seen = True
            continue
        if l <= hard:
            return (pnl + ((o if o < hard else hard) - E) * rem) / risk, "stop_hit_d0"
    post = 0; d = D
    while True:
        d += timedelta(days=1)
        if d > HZ:
            break
        if d.weekday() >= 5 or d not in db or db[d][3] is None:
            if d > max(db): break
            continue
        o, h, l, c, v = db[d]
        post += 1
        if l <= hard:
            return (pnl + ((o if o < hard else hard) - E) * rem) / risk, "stop_hit"
        if post >= 20:
            return (pnl + (c - E) * rem) / risk, "time_close"
    return None, "open"


def main():
    sys.path.insert(0, str(HERE.parents[2]))
    daily = load_daily()
    m_entry = load_min(["minutes_entry.tsv.gz", "minutes_entry2.tsv.gz"])
    m_held = load_min(["minutes_held.tsv.gz"])
    atr = atr_from_pull()
    pop = []
    with open(HERE / "population.tsv") as fh:
        for r in csv.DictReader(fh, delimiter="|"):
            pop.append((r["ticker"], date.fromisoformat(r["trade_date"]), float(r["o"])))
    theirs = {}
    with open(HERE / "arms_per_trade.tsv") as fh:
        for r in csv.DictReader(fh, delimiter="|"):
            theirs[(r["ticker"], date.fromisoformat(r["entry_day"]))] = r
    OE = open(HERE / "check_entry.txt", "w")
    def PE(*a):
        s = " ".join(str(x) for x in a); print(s); OE.write(s + "\n")
    # ── ENTRY on all 2,607 ──
    funnel = collections.Counter(); fills = {}; alt = collections.Counter(); joinbad = []
    for T, D, o_daily in pop:
        bars = m_entry.get((T, D))
        if not bars:
            funnel["abstain:no_bars"] += 1; continue
        b930 = next((b for t, b in bars if t == time(9, 30)), None)
        if b930 is None:
            funnel["abstain:no_930_bar"] += 1; continue
        if abs(b930[0] - o_daily) / o_daily > 0.02:
            funnel["abstain:minute_open_vs_daily_open>2%"] += 1; joinbad.append((T, str(D), b930[0], o_daily)); continue
        H, L = b930[1], b930[2]
        a = atr.get((T, D), "missing")
        if H - L <= 0:
            funnel["no_trade:zero_range"] += 1; continue
        if a not in (None, "missing") and a > 0 and H - L > 1.5 * a:
            funnel["no_trade:orb>1.5xATR"] += 1; continue
        if a == "missing":
            funnel["note:atr_missing_from_my_pull"] += 1
        e = entry(bars, H, L)
        e2 = entry(bars, H, L, proxy="close930")
        if e["status"] != e2["status"] or (e["status"] == "filled" and abs(e["px"] - e2["px"]) > 0.01):
            alt[f"{e['status']}->{e2['status']}" if e["status"] != e2["status"] else "px_differs"] += 1
        if e["status"] != "filled":
            funnel[f"{e['status']}:{e.get('why', '')}"] += 1; continue
        funnel[f"filled:{e['kind']}"] += 1
        fills[(T, D)] = (e, H, L)
    PE(f"# #687 CHECK (3) ENTRY — my own live-order-path walker on all {len(pop)} gap-days (captured Polygon minute bars; my own ATR14 from the check pull)")
    PE("   funnel:", dict(sorted(funnel.items())), "| filled", len(fills))
    PE("   doc funnel: no readable open 165 (96 no 09:30 bar + 68 window gaps + 1 join) | ORB > 1.5xATR 349 | zero range 59 | chase-cap skip 27 | "
       "never crossed 390 | filled 1,617 (1,470 cross, 116 chase at 09:31, 22 open in band, 9 pullback)")
    PE(f"   verdict flips if 'latest trade at 09:31' = the 09:30 bar's CLOSE instead of the 09:31 bar's OPEN: {dict(alt)} (doc: 55)")
    # compare with arms_per_trade on the campaigns
    cmp_ = collections.Counter(); diffs = []
    for k, r in theirs.items():
        if k not in fills:
            cmp_["theirs_campaign_not_filled_by_me"] += 1; diffs.append((k, "not filled by me")); continue
        e, H, L = fills[k]
        ok = (abs(e["px"] - float(r["entry"])) < 1e-3 and abs((2 * L - H) - float(r["hard"])) < 1e-3
              and abs(H - float(r["orb_high"])) < 1e-3 and abs(L - float(r["orb_low"])) < 1e-3 and e["kind"] == r["kind"])
        cmp_["match" if ok else "differs"] += 1
        if not ok:
            diffs.append((k, e["px"], r["entry"], e["kind"], r["kind"]))
    chase = [k for k, r in theirs.items() if r["kind"].startswith("chase")]
    bad_stop = [k for k in chase if abs(float(theirs[k]["hard"]) - (2 * float(theirs[k]["orb_low"]) - float(theirs[k]["orb_high"]))) > 1e-3]
    PE(f"   per-campaign vs arms_per_trade.tsv ({len(theirs)} campaigns): {dict(cmp_)}; first diffs {diffs[:10]}")
    PE(f"   chase fills in the TSV {len(chase)}: stop = 2L - H (the live order's stop, not re-anchored to the fill) on {len(chase) - len(bad_stop)} of {len(chase)}")
    # 25 listed trades
    PE("   25 trades, my walk of the live order vs the TSV (ticker day | ORB H/L | kind px | TSV kind px | stop):")
    import random
    rng = random.Random(29)
    sample = sorted(rng.sample(sorted(theirs), 20) + [k for k in theirs if k[0] in ("BE", "HL", "FCEL", "EPSM", "SEZL") and k[1].year >= 2025][:5])
    for k in sample:
        e, H, L = fills.get(k, ({"kind": "-", "px": float("nan")}, float("nan"), float("nan")))
        r = theirs[k]
        PE(f"     {k[0]:6s} {k[1]} | H {H:.4f} L {L:.4f} | mine {e['kind']:14s} {e['px']:.4f} | tsv {r['kind']:14s} {float(r['entry']):.4f} | stop {2 * L - H:.4f} vs {float(r['hard']):.4f}")
    OE.close()
    return daily, m_entry, m_held, fills, theirs


if __name__ == "__main__":
    main()
