"""#327 hypothesis tests — H12 (620 turn near ANY pivot, operator) and H13 (close-based stops, operator) row
builders plus the TEAM 08-07 / 08-10 hand-walk. Pre-registration: hyptests.py docstring."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

import hyptests as H
from hyptests import (HERE, HORIZON, BPS, H13_RULES, PIVOT_K, _f, week_of, settle_both, fill_entry, walk_h13, sma_n,
                      load_reentry_attempt1)
import reentry
from agents.market_intelligence.delayed_entry_shadow import (_trading_days, macd_620, qualified_620_crosses,
                                                              WARMUP_SESSIONS_620, MIN_CROSS_IDX, BASING_BARS,
                                                              BASING_BAND_ADR, HOOK_SHORT, HOOK_LONG)

TEAM = ("TEAM", date(2026, 8, 7))


def sessions_after(d, n=20):
    return _trading_days(d + timedelta(days=1), HORIZON)[:n]


def w(path, rows):
    cols = []
    for r in rows:
        for c in r:
            if c not in cols:
                cols.append(c)
    with open(HERE / path, "w") as fh:
        fh.write("|".join(cols) + "\n")
        for r in rows:
            fh.write("|".join("" if r.get(c) is None else str(r.get(c)) for c in cols) + "\n")
    print(f"wrote {path}: {len(rows)} rows")


# ── H12 pivots (FIXED list, computed from daily bars, known at the session's open) ─────────────────────

def pivots_at(ctx, sess, s_idx):
    """{name: price} for session s_idx (1-based post-EP), using only bars strictly before that session."""
    bars, ep = ctx["bars"], ctx["ep"]
    pre = [d for d in ctx["ordered"] if d < ep and bars[d]["high_price"] is not None]
    piv = {"ep_low": ctx["gl"], "ep_close": ctx["gc"]}
    if len(pre) >= 20:
        piv["base20"] = max(bars[d]["high_price"] for d in pre[-20:])
    if len(pre) >= 40:
        piv["base60"] = max(bars[d]["high_price"] for d in pre[-60:])
    # completed post-EP swing lows: session j (1 <= j <= s-2), low_j < low_{j-1} and low_j < low_{j+1}; j-1 = 0 is the EP day
    lows = [ctx["gl"]] + [(bars[d]["low_price"] if d in bars and bars[d]["low_price"] is not None else None) for d in sess[:s_idx - 1]]
    for j in range(1, len(lows) - 1):
        a, b, c = lows[j - 1], lows[j], lows[j + 1]
        if None not in (a, b, c) and b < a and b < c:
            piv[f"swing_low_s{j}"] = b
    # SMA10 / SMA20 of closes through session s-1, when rising vs three sessions earlier
    closes_all = [bars[d]["close"] for d in ctx["ordered"] if d < ep and bars[d]["close"] is not None] + [ctx["gc"]] + \
                 [(bars[d]["close"] if d in bars else None) for d in sess[:s_idx - 1]]
    if None in closes_all:
        return piv
    for n in (10, 20):
        now, then = sma_n(closes_all, n), sma_n(closes_all[:-3], n)
        if now is not None and then is not None and now > then:
            piv[f"sma{n}_rising"] = now
    return piv


def crosses_with_guards(series, adr, start):
    """Every bullish MACD(6,20) cross in the session (for the hand-walk): the frozen guards evaluated one by one."""
    out = []
    closes = [b["c"] for b in series]
    macd, sig = macd_620(closes)
    for i in range(max(1, start), len(series)):
        if not (macd[i - 1] <= sig[i - 1] and macd[i] > sig[i]):
            continue
        g_idx = i >= MIN_CROSS_IDX
        g_neg = macd[i] < 0
        wnd = series[max(0, i - BASING_BARS):i]
        rng = (max(b["h"] for b in wnd) - min(b["l"] for b in wnd)) if wnd else None
        g_base = rng is not None and len(wnd) == BASING_BARS and rng <= BASING_BAND_ADR * adr
        g_hook = i >= HOOK_LONG and min(macd[i - HOOK_SHORT:i]) <= min(macd[i - HOOK_LONG:i]) + 1e-9
        out.append({"i": i, "m": series[i]["m"], "close": closes[i], "macd": macd[i], "sig": sig[i], "idx_ok": g_idx, "macd_neg": g_neg,
                    "basing_range": rng, "basing_ok": g_base, "hook_ok": g_hook, "qualified": g_idx and g_neg and g_base and g_hook})
    return out


def h12_fire(ctx, D, sess, adr):
    """First 620 turn within PIVOT_K x ADR$ of any pivot over sessions 1-20; stop = the session's low so far."""
    blind = 0
    n_qual = 0
    for s_idx, d in enumerate(sess, start=1):
        b5 = D["min5"].get((ctx["tkr"], d))
        if not b5:
            blind += 1
            continue
        warm = []
        for wd in [x for x in ctx["ordered"] if x < d][-WARMUP_SESSIONS_620:]:
            warm.extend(D["min5"].get((ctx["tkr"], wd), []))
        series = warm + b5
        piv = pivots_at(ctx, sess, s_idx)
        for i, close in qualified_620_crosses(series, adr, len(warm)):
            n_qual += 1
            near = {k: abs(close - v) / adr for k, v in piv.items() if abs(close - v) <= PIVOT_K * adr}
            if not near:
                continue
            stop = min(x["l"] for x in b5[:i - len(warm) + 1])
            if close <= stop:
                continue
            return {"fire_date": d, "session_idx": s_idx, "fire_minute": series[i]["m"], "entry": close, "stop": stop,
                    "pivots": ";".join(f"{k}@{v:.2f}" for k, v in sorted(near.items(), key=lambda kv: kv[1])),
                    "near_ep_close": int(abs(close - ctx["gc"]) <= PIVOT_K * adr), "n_qual_before": n_qual - 1, "blind": blind}
    return {"fire_date": None, "n_qual_before": n_qual, "blind": blind}


def h12_rows(D):
    a1 = load_reentry_attempt1()
    rows = []
    fires_by_c = defaultdict(list)
    for f in D["fires"]:
        fires_by_c[(f["ticker"], f["ep_date"])].append(f)
    for a in D["alerts"]:
        k = (a["ticker"], a["ep_date"])
        c = D["camps"][k]
        adr = c["adr_dollar"]
        f0 = {"ticker": a["ticker"], "ep_date": a["ep_date"], "ep_low": None, "ep_close": None, "ep_high": None, "adr_dollar": adr}
        bars = D["daily"].get(a["ticker"], {})
        epb = bars.get(a["ep_date"])
        if not epb or epb["close"] is None or adr is None:
            rows.append({"ticker": a["ticker"], "ep_date": a["ep_date"].isoformat(), "era": a["era"], "status": "no_ep_bar"})
            continue
        f0.update({"ep_low": epb["low_price"], "ep_close": epb["close"], "ep_high": epb["high_price"]})
        ctx = reentry.make_ctx(f0, D["daily"])
        sess = sessions_after(a["ep_date"], 20)
        hit = h12_fire(ctx, D, sess, adr)
        row = {"ticker": a["ticker"], "ep_date": a["ep_date"].isoformat(), "era": a["era"], "split": H.split_of(a["ep_date"], a["era"]),
               "adr": adr, "blind_sessions": hit["blind"], "n_qual_crosses_skipped": hit["n_qual_before"], "h12_fire_date": hit["fire_date"]}
        # the lane's FIRST fire on this campaign (earliest date, then minute), own stop, trail / none, recorded + fillable
        lf = sorted(fires_by_c.get(k, []), key=lambda f: (f["fire_date"], f["fire_minute"] if f["fire_minute"] is not None else -1))
        if lf:
            f = lf[0]
            ref_t = a1.get((f["ticker"], f["ep_date"].isoformat(), f["rung"], "incumbent", "trail"))
            ref_n = a1.get((f["ticker"], f["ep_date"].isoformat(), f["rung"], "incumbent", "none"))
            row.update({"lane_first_rung": f["rung"], "lane_first_date": f["fire_date"].isoformat(), "lane_first_minute": f["fire_minute"],
                        "lane_trail_r": ref_t["r_gap"] if ref_t and ref_t["status"] in ("settled", "marked") else None,
                        "lane_none_r": ref_n["r_gap"] if ref_n and ref_n["status"] in ("settled", "marked") else None,
                        "lane_n_fires": len(lf)})
            d0 = (f["day0_resolved"], f["day0_post_low"], f["day0_post_high"]) if f["source"] == "lane_recorded" else None
            sb = settle_both(ctx, D["min5"], f, lambda e, s=f["stop"]: s, d0)
            fl = sb["fill"]
            row["lane_fill_trail_r"] = fl["trail"][1] if fl.get("status") in ("settled", "marked") else None
            row["lane_fill_none_r"] = fl["none"][1] if fl.get("status") in ("settled", "marked") else None
            # the lane's BEST first fire on the campaign (descriptive: max trail R across its patterns)
            best = [a1.get((x["ticker"], x["ep_date"].isoformat(), x["rung"], "incumbent", "trail")) for x in lf]
            best = [b["r_gap"] for b in best if b and b["status"] in ("settled", "marked")]
            row["lane_best_trail_r"] = max(best) if best else None
        if hit["fire_date"] is None:
            row["status"] = "no_h12_fire"
            row["week"] = week_of(lf[0]["fire_date"]) if lf else week_of(a["ep_date"])
            rows.append(row)
            continue
        row["week"] = week_of(hit["fire_date"])
        row.update({"session_idx": hit["session_idx"], "fire_minute": hit["fire_minute"], "entry": hit["entry"], "stop": hit["stop"],
                    "stop_w": (hit["entry"] - hit["stop"]) / hit["entry"] * 100, "pivots": hit["pivots"], "near_ep_close": hit["near_ep_close"]})
        fake = {"ticker": a["ticker"], "ep_date": a["ep_date"], "fire_date": hit["fire_date"], "fire_minute": hit["fire_minute"],
                "entry": hit["entry"], "stop": hit["stop"], "source": "replay", "adr_dollar": adr}
        for lab, sfn in (("turnlow", lambda e, s=hit["stop"]: s), ("adr100", lambda e, adr=adr: e - adr)):
            sb = settle_both(ctx, D["min5"], fake, sfn, None)
            for ek in ("rec", "fill"):
                r_ = sb[ek]
                row[f"{lab}_{ek}_status"] = r_.get("status")
                for arm in ("trail", "none"):
                    row[f"{lab}_{ek}_{arm}_r"] = r_[arm][1] if r_.get("status") in ("settled", "marked") else None
                    row[f"{lab}_{ek}_{arm}_outcome"] = r_[arm][0] if r_.get("status") in ("settled", "marked") else None
        row["status"] = "fired"
        rows.append(row)
    return rows


def team_handwalk(D):
    """TEAM 08-07 (day 0: the EP day itself, outside the lane's day-2+ boundary) and 08-10 (session 1)."""
    lines = []
    a = next(x for x in D["alerts"] if (x["ticker"], x["ep_date"]) == TEAM)
    c = D["camps"][TEAM]
    adr = c["adr_dollar"]
    bars = D["daily"]["TEAM"]
    epb = bars[TEAM[1]]
    f0 = {"ticker": "TEAM", "ep_date": TEAM[1], "ep_low": epb["low_price"], "ep_close": epb["close"], "ep_high": epb["high_price"], "adr_dollar": adr}
    ctx = reentry.make_ctx(f0, D["daily"])
    sess = sessions_after(TEAM[1], 20)
    lines.append(f"TEAM {TEAM[1]}: ADR$ {adr:.2f} -> pivot band {PIVOT_K}xADR = ${PIVOT_K*adr:.2f}; basing band {BASING_BAND_ADR}xADR = ${BASING_BAND_ADR*adr:.2f}; "
                 f"EP day O {epb['open_price']} H {epb['high_price']} L {epb['low_price']} C {epb['close']}")
    for label, d, s_idx in (("DAY 0 (08-07, the EP day — outside the lane by his 08-30 ruling; his entry ~12:05 ET ~$144.39)", TEAM[1], 0),
                            ("SESSION 1 (08-10)", sess[0], 1)):
        b5 = D["min5"].get(("TEAM", d))
        if not b5:
            lines.append(f"  {label}: no 5-min bars on disk")
            continue
        warm = []
        wd = [x for x in ctx["ordered"] if x < d][-WARMUP_SESSIONS_620:]
        for x in wd:
            warm.extend(D["min5"].get(("TEAM", x), []))
        lines.append(f"  {label}: {len(b5)} buckets; warm-up sessions {[x.isoformat() for x in wd]} on disk: {[x.isoformat() for x in wd if ('TEAM', x) in D['min5']]} "
                     f"({len(warm)} warm buckets; MIN_CROSS_IDX={MIN_CROSS_IDX} is the binding guard when the seed is short)")
        series = warm + b5
        if s_idx == 0:
            # day-0 pivots known intraday: the low so far (evaluated per cross), the pre-EP base edges and SMAs; the EP close is unknown
            piv = {k: v for k, v in pivots_at(ctx, sess, 1).items() if k not in ("ep_low", "ep_close")}
            lines.append(f"    pivots known on day 0 (EP close/low not yet known): {', '.join(f'{k}={v:.2f}' for k, v in piv.items())}")
        else:
            piv = pivots_at(ctx, sess, s_idx)
            lines.append(f"    pivots at the open of session {s_idx}: {', '.join(f'{k}={v:.2f}' for k, v in piv.items())}")
        closes = [b["c"] for b in series]
        macd, sig = macd_620(closes)
        if s_idx == 0:
            for m_ in (670, 675, 700, 725):
                i = next((j for j, b in enumerate(series) if b["m"] == m_), None)
                if i is not None:
                    lines.append(f"    {m_//60:02d}:{m_%60:02d}  close {closes[i]:.2f}  MACD {macd[i]:+.2f}  signal {sig[i]:+.2f}  (620_chart.md: 11:10 -1.86/-1.28, 11:15 -1.72/-1.37, 11:40 -1.54/-1.58, ~12:05 -0.89/-1.27)")
        for cr in crosses_with_guards(series, adr, len(warm)):
            m_ = cr["m"]
            j = cr["i"] - len(warm)
            low_so_far = min(x["l"] for x in b5[:j + 1])
            pv = dict(piv)
            if s_idx == 0:
                pv["day_low_so_far"] = low_so_far
            dists = sorted(((abs(cr["close"] - v) / adr, k, v) for k, v in pv.items()), key=lambda t: t[0])
            near = [f"{k}={v:.2f} ({dd:.2f} ADR)" for dd, k, v in dists if dd <= PIVOT_K]
            lines.append(f"    cross {m_//60:02d}:{m_%60:02d} close {cr['close']:.2f} MACD {cr['macd']:+.2f} sig {cr['sig']:+.2f} | idx>={MIN_CROSS_IDX} {cr['idx_ok']} MACD<0 {cr['macd_neg']} "
                         f"basing {fmt_(cr['basing_range'])}<= {BASING_BAND_ADR*adr:.2f} {cr['basing_ok']} hook {cr['hook_ok']} => QUALIFIED {cr['qualified']} | "
                         f"low so far {low_so_far:.2f} (stop; {((cr['close']-low_so_far)/cr['close']*100):.2f}% wide) | nearest {dists[0][1]}={dists[0][2]:.2f} at {dists[0][0]:.2f} ADR | "
                         f"within {PIVOT_K} ADR: {near or 'none'}")
        if s_idx == 0:
            # hypothetical day-0 entry at the first qualified cross, stop under the day low so far, through the lane's settlement
            q = [cr for cr in crosses_with_guards(series, adr, len(warm)) if cr["qualified"]]
            for cr in q[:2]:
                j = cr["i"] - len(warm)
                stop = min(x["l"] for x in b5[:j + 1])
                fake = {"ticker": "TEAM", "ep_date": TEAM[1], "fire_date": d, "fire_minute": cr["m"], "entry": cr["close"], "stop": stop, "source": "replay", "adr_dollar": adr}
                sb = settle_both(ctx, D["min5"], fake, lambda e, s=stop: s, None)
                r = sb["rec"]
                fl = sb["fill"]
                lines.append(f"    IF entered at the {cr['m']//60:02d}:{cr['m']%60:02d} cross {cr['close']:.2f}, stop {stop:.2f} (his: 144.39 / 141.51): "
                             f"recorded trail {fmt_(r['trail'][1] if r.get('status') in ('settled','marked') else None)}R none {fmt_(r['none'][1] if r.get('status') in ('settled','marked') else None)}R "
                             f"(status {r.get('status')}, mfe {fmt_(r.get('mfe'))}); fillable (next bucket open+5bps) trail {fmt_(fl['trail'][1] if fl.get('status') in ('settled','marked') else None)}R")
    # what the lane's own patterns did on TEAM (from reentry_rows)
    a1 = load_reentry_attempt1()
    for f in [x for x in D["fires"] if (x["ticker"], x["ep_date"]) == TEAM]:
        ref = a1.get(("TEAM", TEAM[1].isoformat(), f["rung"], "incumbent", "trail"))
        lines.append(f"  lane {f['rung']}: fired {f['fire_date']} min {f['fire_minute']} entry {f['entry']} stop {f['stop']} -> own stop, trail: {ref['outcome'] if ref else None} {fmt_(ref['r_gap'] if ref else None)}R")
    return "\n".join(lines)


def fmt_(x):
    return "—" if x is None else f"{x:+.2f}" if isinstance(x, float) else str(x)


# ── H13 ───────────────────────────────────────────────────────────────────────────────────────────────

def h13_rows(D):
    rows = []
    for f in D["fires"]:
        ctx = reentry.make_ctx(f, D["daily"])
        adr = f["adr_dollar"] or 0.0
        d0 = (f["day0_resolved"], f["day0_post_low"], f["day0_post_high"]) if f["source"] == "lane_recorded" else None
        fe = fill_entry(f, D["min5"], ctx)
        base = {"ticker": f["ticker"], "ep_date": f["ep_date"].isoformat(), "era": f["era"], "split": f["split"], "week": f["week"],
                "rung": f["rung"], "fire_date": f["fire_date"].isoformat(), "fire_minute": f["fire_minute"], "source": f["source"],
                "entry": f["entry"], "stop": f["stop"], "adr": adr}
        for level in ("lane", "sma10"):
            for rule in ("touch",) + H13_RULES:
                for arm in ("none", "trail"):
                    for ek in ("rec", "fill"):
                        r = dict(base, level=level, rule=rule, arm=arm, entry_kind=ek)
                        if ek == "rec":
                            res = walk_h13(ctx, D["min5"], f["entry"], f["fire_minute"], f["fire_date"], f["stop"], rule, arm, adr,
                                           level_kind="fixed" if level == "lane" else "sma10", d0=d0)
                            e_used = f["entry"]
                        elif fe is None:
                            res = {"status": "no_fill"}
                            e_used = None
                        else:
                            res = walk_h13(ctx, D["min5"], fe["entry"], fe["fm"], fe["fire_date"], f["stop"], rule, arm, adr,
                                           level_kind="fixed" if level == "lane" else "sma10", d0=None, post5_override=fe["post5"], fill_bps=BPS)
                            e_used = fe["entry"]
                        r["status"] = res.get("status")
                        r["why"] = res.get("why")
                        if res.get("status") in ("settled", "marked"):
                            r.update({"outcome": res["outcome"], "r": res["r"], "exit_idx": res["exit_idx"], "blind": res["blind"],
                                      "mfe": res["mfe"], "mae": res["mae"], "level0": res["level0"], "risk": res["risk"], "exit_px": res["exit_px"],
                                      "r_lane_units": round(res["r"] * res["risk"] / (e_used - f["stop"]), 4) if (e_used and f["stop"] and e_used > f["stop"]) else None})
                        rows.append(r)
    return rows


def run_h12_h13(D):
    rows = h12_rows(D)
    w("hyp_rows_h12.tsv", rows)
    (HERE / "hyp_team_handwalk.txt").write_text(team_handwalk(D) + "\n")
    print("wrote hyp_team_handwalk.txt")
    rows = h13_rows(D)
    w("hyp_rows_h13.tsv", rows)
