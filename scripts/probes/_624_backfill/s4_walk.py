"""#624 backfill — STAGE 4: walk the signals and compute prereg §4, apply §5 exactly as written.

  --pass1 : walk PRIMARY + S1 + S2 (daily-only S2) and emit ONLY the S2 line-test days to fetch (no totals read)
  --final : everything, with the S2 line-test-day minutes -> s4_results_out.txt, per_signal_P.tsv, s4_summary.json
"""
from __future__ import annotations

import csv
import json
import math
import pickle
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

import numpy as np

import lib624 as L
import walk624 as W
import s1s2

L.assert_frozen()
MODE = sys.argv[1]
W0, W1 = date(2024, 1, 2), date(2026, 9, 3)
OOS_END = date(2026, 6, 5)
MIN_FILES = [L.HERE / f for f in ("min_s1.tsv", "min_s2a.tsv", "min_s2b.tsv", "min_s2c.tsv")]
HELD_FILES = [L.HERE / "min_s2held.tsv"]
checks = json.load(open(L.HERE / "s3_checks.json"))
assert not checks["halt"], f"composition HALT: {checks['halt']}"

BLOCKS = {
    "OOS (verdict) 2024-01-02..2026-06-05": lambda d: d <= OOS_END,
    "DISC 2024": lambda d: d <= date(2024, 12, 31),
    "HELD 2025-01-02..2026-09-03": lambda d: d >= date(2025, 1, 2),
    "HELD-A 2025-01-02..2026-06-05": lambda d: date(2025, 1, 2) <= d <= OOS_END,
    "IN-SAMPLE 2026-06-08..09-03": lambda d: d >= date(2026, 6, 8),
    "ALL 2024-01-02..2026-09-03": lambda d: True,
}


def load_sig(name):
    out = []
    for s in json.load(open(L.HERE / f"signals_{name}.json")):
        s["d"] = date.fromisoformat(s["d"])
        hh, mm = map(int, s["T"].split(":")[:2])
        s["T"] = time(hh, mm)
        out.append(s)
    return out


P_sig = load_sig("P")
S3_sig = load_sig("S3_rt_volume")
S4_sig = load_sig("S4_cap_at_tick")
daily = L.load_daily()
keys = {(s["t"], s["d"]) for s in P_sig + S3_sig + S4_sig}
mins = L.load_minutes(MIN_FILES, keys=keys)
held_raw = L.load_minutes(HELD_FILES) if MODE == "--final" and HELD_FILES[0].exists() else {}
held = {k: L.as_dict_bars(k[1], v) for k, v in held_raw.items()}
daily_bf = {}
for t in {k[0] for k in keys}:
    dl = daily.get(t)
    if dl:
        daily_bf[t] = {x: dict(r) for x, r in dl["rows"].items() if x <= L.DATA_END}
daily_cut = {t: {"rows": {x: r for x, r in dl["rows"].items() if x <= L.DATA_END},
                 "dates": [x for x in dl["dates"] if x <= L.DATA_END]} for t, dl in daily.items() if t in daily_bf}

walked: dict[tuple, dict] = {}


def walk_all(sigs):
    for s in sigs:
        k = (s["t"], s["d"], s["T"])
        if k in walked:
            continue
        bars0 = L.as_dict_bars(s["d"], mins.get((s["t"], s["d"]), []))
        prim = W.walk_primary(s["t"], s["d"], s["T"], bars0, daily_cut.get(s["t"]))
        s1 = W.walk_primary(s["t"], s["d"], s["T"], bars0, daily_cut.get(s["t"]), entry_mode="live_order")
        s2 = None
        if prim.get("entry_status") == "filled" and prim.get("_fill"):
            s2 = s1s2.s2_walk(s["t"], s["d"], bars0, prim["orb_high"], prim["orb_low"], prim["_fill"], daily_bf, held)
        walked[k] = {"prim": prim, "s1": s1, "s2": s2}


walk_all(P_sig)
if MODE == "--pass1":
    lt = set()
    for k, w in walked.items():
        if w["s2"]:
            for x in w["s2"]["line_tests"]:
                lt.add((k[0], x["day"]))
    lst = sorted(lt, key=lambda x: (x[1], x[0]))
    open(L.HERE / "list_min_s2held.txt", "w").write("\n".join(f"{t}|{d}" for t, d in lst) + "\n")
    print(f"PASS 1 (no totals read): S2 line-test days {len(lst)} on {len({t for t, _ in lst})} tickers -> list_min_s2held.txt")
    raise SystemExit(0)

walk_all(S3_sig)
walk_all(S4_sig)

out = open(L.HERE / "s4_results_out.txt", "w")


def P(*a):
    s = " ".join(str(x) for x in a)
    print(s); out.write(s + "\n")


def fmt(x, nd=2, pct=False):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x:.1%}" if pct else f"{x:+.{nd}f}"


# ── measures ─────────────────────────────────────────────────────────────────────────────

Z90 = 1.6448536269514722
BINS = [("<=-1.5", lambda x: x <= -1.5), ("-1.5..-1", lambda x: -1.5 < x <= -1), ("-1..-0.5", lambda x: -1 < x <= -0.5),
        ("-0.5..0", lambda x: -0.5 < x <= 0), ("0..0.5", lambda x: 0 < x < 0.5), ("0.5..1", lambda x: 0.5 <= x < 1),
        ("1..2", lambda x: 1 <= x < 2), ("2..3", lambda x: 2 <= x < 3), ("3..5", lambda x: 3 <= x < 5),
        ("5..8", lambda x: 5 <= x < 8), (">=8", lambda x: x >= 8)]


def wilson(k, n):
    if n == 0:
        return (None, None)
    p = k / n
    den = 1 + Z90 ** 2 / n
    c = (p + Z90 ** 2 / (2 * n)) / den
    h = Z90 * math.sqrt(p * (1 - p) / n + Z90 ** 2 / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))


def boot(trades):
    """Ticker bootstrap (all rows of a drawn ticker together), 10,000 draws, seed 624: 90% percentile intervals for
    the >=3R rate, the >=8R rate and the mean R."""
    by = defaultdict(lambda: [0, 0, 0, 0.0])
    for tr in trades:
        b = by[tr["t"]]
        b[0] += 1; b[1] += tr["R"] >= 3; b[2] += tr["R"] >= 8; b[3] += tr["R"]
    if not by:
        return {}
    arr = np.array(list(by.values()), dtype=float)
    rng = np.random.default_rng(624)
    idx = rng.integers(0, len(arr), size=(10000, len(arr)))
    s = arr[idx].sum(axis=1)
    n = s[:, 0]
    out = {}
    for name, col in (("r3", 1), ("r8", 2), ("mean", 3)):
        v = s[:, col] / n
        out[name] = (float(np.percentile(v, 5)), float(np.percentile(v, 95)))
    return out


def stats(trades, n_signals=None):
    Rs = sorted(tr["R"] for tr in trades)
    n = len(Rs)
    if n == 0:
        return {"n": 0}
    e3 = sum(1 for x in Rs if x >= 3); e8 = sum(1 for x in Rs if x >= 8)
    b = boot(trades)
    tot = sum(Rs)
    by_t = defaultdict(float)
    for tr in trades:
        by_t[tr["t"]] += tr["R"]
    top_t, top_R = max(by_t.items(), key=lambda kv: kv[1])
    pos = sum(v for v in by_t.values() if v > 0)
    dbt = Rs[:-2] if n > 2 else []
    st = {"n": n, "tickers": len(by_t), "e3": e3, "e8": e8, "r3": e3 / n, "r8": e8 / n,
          "r3_ci": b.get("r3"), "r8_ci": b.get("r8"), "r3_wilson": wilson(e3, n), "r8_wilson": wilson(e8, n),
          "mean": tot / n, "mean_ci": b.get("mean"), "median": statistics.median(Rs), "total": tot,
          "dbt_total": sum(dbt), "dbt_mean": (sum(dbt) / len(dbt)) if dbt else None,
          "dist": {lab: sum(1 for x in Rs if f(x)) for lab, f in BINS},
          "pct": {p: float(np.percentile(Rs, p)) for p in (10, 25, 50, 75, 90, 95)}, "max": Rs[-1], "min": Rs[0],
          "big_loss": sum(1 for x in Rs if x < -1.5), "forced": sum(1 for tr in trades if tr.get("forced")),
          "marked": sum(1 for tr in trades if tr.get("marked")),
          "top_ticker": top_t, "top_ticker_R": top_R, "top_share_total": (top_R / tot) if tot > 0 else None,
          "top_share_pos": (top_R / pos) if pos > 0 else None,
          "e3_tickers": len({tr["t"] for tr in trades if tr["R"] >= 3}),
          "top10": sorted(((tr["t"], tr["d"].isoformat(), round(tr["R"], 2)) for tr in trades), key=lambda x: -x[2])[:10],
          "worst": min(((tr["t"], tr["d"].isoformat(), round(tr["R"], 2)) for tr in trades), key=lambda x: x[2])}
    if n_signals:
        st["per_signal_r3"] = e3 / n_signals
        st["n_signals"] = n_signals
    return st


def trades_of(sigs, arm="prim", settled_only=False):
    out = []
    for s in sigs:
        w = walked[(s["t"], s["d"], s["T"])][arm]
        if w is None:
            continue
        if arm == "s2":
            if w["R"] is None or w["status"] == "excluded":
                continue
            marked = w["status"] != "settled"
            if settled_only and marked:
                continue
            out.append({"t": s["t"], "d": s["d"], "R": w["R"], "marked": marked, "forced": w.get("forced")})
            continue
        if w["R"] is None or w["outcome"] not in ("settled", "horizon", "open", "delisted_forced_close"):
            continue
        if settled_only and w["outcome"] not in ("settled", "delisted_forced_close"):
            continue
        out.append({"t": s["t"], "d": s["d"], "R": w["R"], "marked": bool(w.get("marked")), "forced": bool(w.get("forced")),
                    "s": s})
    return out


def funnel(sigs, arm="prim"):
    c = Counter()
    for s in sigs:
        w = walked[(s["t"], s["d"], s["T"])][arm]
        es, oc = w.get("entry_status"), w.get("outcome")
        if es == "window_out_of_orb":
            c["out_of_window (tick >= 09:45)"] += 1
        elif es in ("no_day0_minute_bars", "no_930_bar_for_orb", "daily_row_split_adjusted"):
            c[f"unscoreable:{es}"] += 1
        elif es == "orb_invalid":
            c["orb_invalid"] += 1
        elif es == "no_entry":
            c[f"no_entry:{w.get('entry_reason')}"] += 1
        elif es == "abstain":
            c["entry_abstain (minute gaps)"] += 1
        elif es in ("chase_cap_skip",):
            c["chase_cap_skip"] += 1
        elif es == "filled":
            c["filled"] += 1
            if oc == "unscoreable":
                c[f"filled->unscoreable:{str(w.get('final_reason')).split(':')[0]}"] += 1
            else:
                c[f"filled->{oc}"] += 1
        else:
            c[f"other:{es}/{oc}"] += 1
    return dict(sorted(c.items()))


def line(label, st):
    if not st or st.get("n", 0) == 0:
        return f"   {label:44s} walked 0"
    ci = st["r3_ci"]; ci8 = st["r8_ci"]
    ratio = (ci[1] / ci[0]) if ci and ci[0] > 0 else None
    return (f"   {label:44s} walked {st['n']:4d} on {st['tickers']:3d} tickers | >=3R {st['e3']:3d} = {st['r3']:.1%} "
            f"[90% {ci[0]:.1%}–{ci[1]:.1%}; upper/lower {'—' if ratio is None else f'{ratio:.2f}'}; Wilson {st['r3_wilson'][0]:.1%}–{st['r3_wilson'][1]:.1%}] | "
            f">=8R {st['e8']} = {st['r8']:.1%} [{ci8[0]:.1%}–{ci8[1]:.1%}] | mean {st['mean']:+.3f}R [{st['mean_ci'][0]:+.3f}, {st['mean_ci'][1]:+.3f}] "
            f"median {st['median']:+.2f} total {st['total']:+.1f} | drop-best-2 total {st['dbt_total']:+.1f} mean {fmt(st['dbt_mean'], 3)}"
            + (f" | per-signal >=3R {st['per_signal_r3']:.1%} of {st['n_signals']}" if st.get("n_signals") else "")
            + (f" | marked {st['marked']}" if st.get("marked") else "") + (f" | forced closes {st['forced']}" if st.get("forced") else ""))


SUMMARY = {}


def report(pop_label, sigs, arm="prim", detail=True):
    P(f"\n## {pop_label}")
    for blk, f in BLOCKS.items():
        ss = [s for s in sigs if f(s["d"])]
        tr = trades_of(ss, arm)
        st = stats(tr, n_signals=len(ss))
        SUMMARY[(pop_label, blk, arm)] = st
        P(line(f"{blk} (signals {len(ss)})", st))
        if detail and blk.startswith(("OOS", "ALL")):
            st2 = stats(trades_of(ss, arm, settled_only=True))
            P(line("   settled-only", st2))
            if st.get("n"):
                P(f"      distribution: {st['dist']}")
                P(f"      p10 {st['pct'][10]:+.2f} p25 {st['pct'][25]:+.2f} p50 {st['pct'][50]:+.2f} p75 {st['pct'][75]:+.2f} "
                  f"p90 {st['pct'][90]:+.2f} p95 {st['pct'][95]:+.2f} max {st['max']:+.2f}; worst {st['worst']}; losses beyond -1.5R {st['big_loss']}")
                P(f"      top ticker {st['top_ticker']} {st['top_ticker_R']:+.2f}R = {fmt(st['top_share_total'], pct=True)} of summed R "
                  f"({fmt(st['top_share_pos'], pct=True)} of the positive R); >=3R events on {st['e3_tickers']} tickers")
                P(f"      ten largest: {st['top10']}")
        if detail and arm == "prim":
            P(f"      funnel: {funnel(ss, arm)}")


# ── populations ──────────────────────────────────────────────────────────────────────────
E_sig = [s for s in P_sig if s["E"]]
G_sig = [s for s in P_sig if s["G"]]
XS_sig = [s for s in P_sig if not s["serial"]]
CD_sig = [s for s in P_sig if s["first_in_60d"]]
nsess = len(W.lfc._trading_days(W0, W1))
P(f"# #624 RESULTS — run {datetime.now(L.ET).isoformat(timespec='seconds')}; primary = the live lane walker under era D "
  f"({W.RULES_D}); R = money-R (pnl / (entry - stop)); data end {L.DATA_END}; sessions in window {nsess}")
P(f"populations: P {len(P_sig)} signals · E {len(E_sig)} · G {len(G_sig)} · P ex-serial {len(XS_sig)} · P first-in-60-days {len(CD_sig)}")
report("P — every lane signal (THE VERDICT POPULATION)", P_sig)
report("E — extension guard passed", E_sig)
report("G — all five stamps passed", G_sig)
report("P ex-serial (no ticker with >= 3 lane signals in the 60 days ending D)", XS_sig)
report("P with a 60-day cooldown (first lane signal per ticker per 60 days)", CD_sig, detail=False)

# ── §5 verdict ───────────────────────────────────────────────────────────────────────────
OOS = "OOS (verdict) 2024-01-02..2026-06-05"


def verdict(st):
    ci = st.get("r3_ci")
    if not ci:
        return "no trades", None
    lo, hi = ci
    pinned = lo > 0 and hi / lo < 2.0
    ratio = hi / lo if lo > 0 else None
    return ("PINNED" if pinned else "NOT PINNED"), ratio


st_v = SUMMARY[("P — every lane signal (THE VERDICT POPULATION)", OOS, "prim")]
v, ratio = verdict(st_v)
P(f"\n## §5 VERDICT (P, OUT-OF-SAMPLE, >=3R rate, ticker bootstrap 90%): {st_v['r3']:.1%} [{st_v['r3_ci'][0]:.1%}–{st_v['r3_ci'][1]:.1%}], "
  f"upper/lower {'—' if ratio is None else f'{ratio:.2f}'} (bar < 2.0, lower > 0) -> {v}")
lo, hi = st_v["r3_ci"]
P(f"   (i) vs the review's 5% refusal line: {'wholly ABOVE' if lo > 0.05 else ('wholly BELOW' if hi < 0.05 else 'STRADDLES')} "
  f"({lo:.1%}–{hi:.1%})")
d_st = SUMMARY[("P — every lane signal (THE VERDICT POPULATION)", "DISC 2024", "prim")]
h_st = SUMMARY[("P — every lane signal (THE VERDICT POPULATION)", "HELD 2025-01-02..2026-09-03", "prim")]
in1 = h_st["r3_ci"][0] <= d_st["r3"] <= h_st["r3_ci"][1]
in2 = d_st["r3_ci"][0] <= h_st["r3"] <= d_st["r3_ci"][1]
P(f"   (ii) stability: discovery {d_st['r3']:.1%} [{d_st['r3_ci'][0]:.1%}–{d_st['r3_ci'][1]:.1%}] vs held-out {h_st['r3']:.1%} "
  f"[{h_st['r3_ci'][0]:.1%}–{h_st['r3_ci'][1]:.1%}]: discovery inside held-out's {in1}, held-out inside discovery's {in2} "
  f"-> {'STABLE' if in1 and in2 else 'UNSTABLE'}")
for lab, key in (("E", ("E — extension guard passed", OOS, "prim")),
                 ("P ex-serial", ("P ex-serial (no ticker with >= 3 lane signals in the 60 days ending D)", OOS, "prim")),
                 ("P ALL window", ("P — every lane signal (THE VERDICT POPULATION)", "ALL 2024-01-02..2026-09-03", "prim"))):
    s_ = SUMMARY[key]
    vv, rr = verdict(s_)
    P(f"   (iii) {lab}: {s_['r3']:.1%} [{s_['r3_ci'][0]:.1%}–{s_['r3_ci'][1]:.1%}] ratio {'—' if rr is None else f'{rr:.2f}'} -> {vv} (beside, never substituted)")

# W checks
w7_share = st_v["top_share_total"] if st_v["top_share_total"] is not None else st_v["top_share_pos"]
w7 = (w7_share is not None and w7_share > 0.40) or st_v["e3_tickers"] <= 2
dec = json.load(open(L.HERE / "s1_decisions.json"))
P(f"\n## WOULD-FAIL-IF")
P(f"   W1 survivorship: {'VOID' if checks['w1_void'] else 'ok'} (s3_compose_out.txt)")
P(f"   W2 cap coverage: unreadable {checks['w2']:.1%} of survivors -> {'VOID' if checks['w2'] > 0.2 else 'ok'}")
P(f"   W3 instruments: C1-C4 / A1 / A2 all passed in Stage 1 -> ok" if dec.get("a1_pass") and dec.get("a2_pass") and not dec.get("halt_phase1") else "   W3: FAILED")
walk_P = [s for s in P_sig if s["walkable"]]
w4_n = sum(1 for s in walk_P if walked[(s["t"], s["d"], s["T"])]["prim"].get("entry_status") in ("no_930_bar_for_orb", "no_day0_minute_bars")
           or (walked[(s["t"], s["d"], s["T"])]["prim"].get("entry_status") == "abstain"
               and str(walked[(s["t"], s["d"], s["T"])]["prim"].get("entry_reason", "")).startswith("entry_window_gaps")))
w4_share = w4_n / max(1, len(walk_P))
P(f"   W4 data (D9: the walker's own states): no 09:30 bar / no day-0 bars / entry_window_gaps abstain on {w4_n} of {len(walk_P)} walkable "
  f"signals = {w4_share:.1%} (bar 15%); pull errors {checks['w4_err']:.2%} (bar 2%) -> {'VOID' if w4_share > 0.15 or checks['w4_err'] > 0.02 else 'ok'}"
  f"   [beside: any empty minute between submit and 10:00 {checks['w4_data_share']:.1%} — trading pauses, w4_profile_out.txt]")
P(f"   W5 look-ahead: test_w5.py -> {open(L.HERE / 'test_w5_out.txt').read().splitlines()[3]}")
P(f"   W6 prefilter: volume half safe {dec['w6_volume_safe']}, price half widen {dec['w6_price_widen']} -> ok")
P(f"   W7 one name (P, OOS): top ticker {st_v['top_ticker']} {fmt(w7_share, pct=True)} of summed R (bar 40%); >=3R events on "
  f"{st_v['e3_tickers']} tickers (bar > 2) -> {'VOID' if w7 else 'ok'}")
void = checks["w1_void"] or checks["w2"] > 0.2 or w4_share > 0.15 or checks["w4_err"] > 0.02 or w7
P(f"   -> the verdict above is {'NOT citable as pinned (a WOULD-FAIL-IF fired)' if void else 'citable as stated'}")

# ── sensitivities ────────────────────────────────────────────────────────────────────────
P("\n## SENSITIVITIES (beside, never the verdict)")
for lab, arm in (("S1 the live #500 order (chase-or-skip above the ORB high)", "s1"), ("S2 the #685 forward walk (A0)", "s2")):
    for blk in (OOS, "ALL 2024-01-02..2026-09-03"):
        ss = [s for s in P_sig if BLOCKS[blk](s["d"])]
        st = stats(trades_of(ss, arm), n_signals=len(ss))
        SUMMARY[(lab, blk, arm)] = st
        P(line(f"{lab} — {blk.split(' ')[0]}", st) + (f"  verdict-shape: {verdict(st)[0]}" if st.get("n") else ""))
    if arm == "s1":
        P(f"      S1 funnel (ALL): {funnel(P_sig, 's1')}")
    else:
        P(f"      S2 exclusions (ALL): {dict(Counter(w['s2']['why'] for w in walked.values() if w['s2'] and w['s2']['status'] == 'excluded'))}; "
          f"S2 status: {dict(Counter(w['s2']['status'] for w in walked.values() if w['s2']))} (abstain / no-R rows are outside the S2 denominator)")
for lab, sigs in (("S3 real-time volume (k = 0)", S3_sig), ("S4 cap at the tick price", S4_sig)):
    pk = {(s["t"], s["d"]) for s in P_sig}
    sk = {(s["t"], s["d"]) for s in sigs}
    P(f"   {lab}: signals {len(sigs)} (vs P {len(P_sig)}: {len(sk - pk)} added, {len(pk - sk)} dropped)")
    for blk in (OOS, "ALL 2024-01-02..2026-09-03"):
        ss = [s for s in sigs if BLOCKS[blk](s["d"])]
        st = stats(trades_of(ss), n_signals=len(ss))
        SUMMARY[(lab, blk, "prim")] = st
        P(line(f"   {blk.split(' ')[0]}", st) + (f"  verdict-shape: {verdict(st)[0]}" if st.get("n") else ""))

# ── descriptive splits ───────────────────────────────────────────────────────────────────
P("\n## DESCRIPTIVE SPLITS (P, ALL window, primary walker)")
bands = lambda v, cuts, labels: next(lab for c, lab in zip(cuts + [float('inf')], labels) if v < c)
splits_def = {
    "cap band": lambda s: bands(s["cap"], [25e6, 100e6, 200e6], ["<$25M", "$25-100M", "$100-200M", "$200-500M"]),
    "prior close": lambda s: bands(s["pc_raw"], [10, 20, 50], ["$5-10", "$10-20", "$20-50", "$50+"]),
    "gap at tick": lambda s: bands(s["gap"], [20, 30, 50, 100], ["15-20%", "20-30%", "30-50%", "50-100%", "100%+"]),
    "tick": lambda s: s["T"].strftime("%H:%M"),
    "extension stamp": lambda s: "extended" if not s["E"] else "not extended",
    "serial": lambda s: "serial" if s["serial"] else "not serial",
}
for name, f in splits_def.items():
    grp = defaultdict(list)
    for tr in trades_of(P_sig):
        grp[f(tr["s"])].append(tr)
    P(f"   {name}: " + " · ".join(f"{k} n={len(v)} >=3R {sum(1 for x in v if x['R'] >= 3)} ({sum(1 for x in v if x['R'] >= 3) / len(v):.0%}) "
                              f"mean {sum(x['R'] for x in v) / len(v):+.2f}" for k, v in sorted(grp.items())))

# ── beside: live rows, n=46 ──────────────────────────────────────────────────────────────
rep = json.load(open(L.HERE / "s0_lane_replays.json"))
filled = [r for r in rep if r["entry_status"] == "filled"]
settled = [r for r in rep if r["outcome"] == "settled" and r["realized_r"] is not None]
P(f"\n## BESIDE — the live shadow (mi_lowcap_lane_replays as of {max(r['replay_asof_date'] for r in rep)}): signals {len(rep)}, "
  f"filled {len(filled)}, settled {len(settled)}, >=3R {sum(1 for r in settled if r['realized_r'] >= 3)}, "
  f"mean {statistics.mean(r['realized_r'] for r in settled):+.3f}R, open {sum(1 for r in rep if r['outcome'] in ('open', 'horizon'))}")
m46 = [json.loads(x) for x in open(L.REPO / "scripts/probes/_623_master.jsonl")]
c46 = [r for r in m46 if r.get("market_cap") is not None and r["market_cap"] < 5e8 and (r.get("gap_pct") or 0) >= 15
       and (r.get("vol_pct_daily_bars") or 0) >= 90 and r.get("status") == "settled" and str(r.get("artifact")) == "False"
       and not r.get("degenerate_stop")]
R46 = [r["realized_r"] for r in c46]
ex2 = [r["realized_r"] for r in c46 if (r["ticker"], r["scan_date"]) not in (("WETO", "2026-08-17"), ("FBRX", "2026-07-09"))]
P(f"   n=46 cell as published (era C bracket, submit 09:31): n {len(c46)}, >=3R {sum(1 for x in R46 if x >= 3)}, mean {statistics.mean(R46):+.3f}R, "
  f"ex the WETO 08-17 + FBRX 07-09 trades n {len(ex2)} mean {statistics.mean(ex2):+.3f}R")
era = {}
with open(L.REPO / "scripts/probes/_545p2_623_era_walk.tsv") as fh:
    for r in csv.DictReader(fh, delimiter="|"):
        if r["cell"] == "era_d_ladder":
            era[(r["ticker"], r["alert_date"])] = r
ed = [era.get((r["ticker"], r["scan_date"])) for r in c46]
edR = [float(x["realized_r"]) for x in ed if x and x["status"] == "settled" and x["realized_r"] not in ("", "None")]
P(f"   n=46 cell re-walked under era D (_545p2_623_era_walk.tsv, submit 09:31): joined {sum(1 for x in ed if x)}, settled {len(edR)}, "
  f">=3R {sum(1 for x in edR if x >= 3)}, >=8R {sum(1 for x in edR if x >= 8)}, mean {statistics.mean(edR):+.3f}R" if edR else "   era D re-walk: none joined")

# ── A3 (report only) ────────────────────────────────────────────────────────────────────
pk = {(s["t"], s["d"]): s for s in P_sig}
cand_by = {(c["t"], c["d"]): c for c in L.load_cand()}
sect = L.load_sectypes()
disp = json.load(open(L.HERE / "disp_P.json"))
a3 = Counter(); a3_rows = []
for r in c46:
    k = (r["ticker"], date.fromisoformat(r["scan_date"]))
    if k in pk:
        a3["re-found"] += 1
    else:
        why = disp.get(f"{k[0]}|{k[1]}")
        if why is None:
            c = cand_by.get(k)
            if c is None:
                why = "not a prefilter row: daily high < +15% over the prior close, or a raw floor ($5 / 50k) failed"
            elif k[0] in L.SKIP_TICKERS or sect.get(k[0]) in L.NONSTOCK_TODAY:
                why = f"typed non-stock today ({sect.get(k[0])})"
            else:
                h = L.vol_history(daily.get(k[0]), k[1])
                why = ("no volume history" if not h else
                       f"full-day volume below p90 of its history ({L.LL._volume_percentile(c['v'], h)})")
        a3[why.split(":")[0] if not why.startswith("not in") else why] += 1
        extra = ""
        if why == "never_passed_free_terms":
            import pickle as _pk
            global _DG
            try:
                _DG
            except NameError:
                _DG = _pk.load(open(L.HERE / "digests.pkl", "rb"))
            g = _DG[k]; c = cand_by[k]
            sp = L.load_splits() if "_SP" not in globals() else _SP
            globals()["_SP"] = sp
            h = L.vol_history(daily.get(k[0]), k[1])
            parts = []
            for T in L.TICKS:
                Ts = T.strftime("%H:%M")
                gp = L.gap_pct(g["px"]["open930"][Ts], c["pc"])
                pc_ = L.LL._volume_percentile(g["vol"][15][Ts], h) if h else None
                parts.append(f"{Ts} gap {gp} pct {pc_}")
            extra = "; backfill ticks: " + ", ".join(parts)
        elif why.startswith("not a prefilter row"):
            dl = daily.get(k[0]); rows_ = dl["rows"] if dl else {}
            prev = [x for x in (dl["dates"] if dl else []) if x < k[1]]
            if prev and k[1] in rows_:
                pr = rows_[prev[-1]]; f = L.fac_prior(L.load_splits() if "_SP" not in globals() else _SP, k[0], k[1])
                extra = (f"; daily high / prior close {rows_[k[1]]['h'] / pr['c']:.3f}, raw prior close ${pr['c'] * f:.2f}, "
                         f"raw prior-day volume {pr['v'] / f:,.0f}")
        a3_rows.append(f"{k[0]} {k[1]} ({why}; n=46 cap ${r['market_cap'] / 1e6:.0f}M, gap {r['gap_pct']:.1f}, R {r['realized_r']:+.2f}){extra}")
P(f"\n## A3 (report only): the frozen replay re-finds {a3['re-found']} of the {len(c46)} n=46 rows; the rest: "
  f"{ {k: v for k, v in a3.items() if k != 're-found'} }")
for x in a3_rows:
    P("      " + x)

# ── graduation criteria 2-5, for information ─────────────────────────────────────────────
st_all = SUMMARY[("P — every lane signal (THE VERDICT POPULATION)", "ALL 2024-01-02..2026-09-03", "prim")]
settled_all = stats(trades_of(P_sig, settled_only=True))
per_day = Counter(s["d"] for s in P_sig)
P(f"\n## FOR INFORMATION — lowcap_lane_graduation_624 criteria 2-5 on the backfill (P, ALL window; NOT a graduation)")
P(f"   2. settled walks >= 3R: {settled_all['e3']} (bar >= 4)")
P(f"   3. mean R without the top two: {fmt(settled_all['dbt_mean'], 3)} (bar >= 0)")
P(f"   4. top ticker {settled_all['top_ticker']} {settled_all['top_ticker_R']:+.2f}R; summed R is {settled_all['total']:+.1f}, so a share of it is undefined — "
  f"{fmt(settled_all['top_share_pos'], pct=True)} of the positive R (bar <= 40%); distinct tickers {settled_all['tickers']} (bar >= 20)")
P(f"   5. signals per session: mean {len(P_sig) / nsess:.2f} over {nsess} sessions, max {max(per_day.values())} (live shadow: 19 in 19 sessions)")

# per-signal table
with open(L.HERE / "per_signal_P.tsv", "w") as fh:
    cols = ["ticker", "d", "tick", "block", "gap", "pc_raw", "cap", "pct", "vol_raw", "ext", "adv", "atr_pct", "stamps", "E", "G",
            "serial", "first_in_60d", "typed_today", "poly_type", "entry_status", "outcome", "entry", "stop", "R", "final",
            "s1_status", "s1_outcome", "s1_R", "s2_status", "s2_R"]
    fh.write("|".join(cols) + "\n")
    for s in sorted(P_sig, key=lambda s: (s["d"], s["t"])):
        w = walked[(s["t"], s["d"], s["T"])]
        pr, a1, a2 = w["prim"], w["s1"], w["s2"] or {}
        row = [s["t"], s["d"].isoformat(), s["T"].strftime("%H:%M"), s["block"], s["gap"], round(s["pc_raw"], 4), round(s["cap"]),
               s["pct"], round(s["vol_raw"]), s["ext"], None if s["adv"] is None else round(s["adv"]), None if s["atr_pct"] is None else round(s["atr_pct"], 2),
               ",".join(g["gate"] for g in s["stamps"]), s["E"], s["G"], s["serial"], s["first_in_60d"], s["typed_today"], s["poly_type"],
               pr.get("entry_status"), pr.get("outcome"), pr.get("entry_price"), pr.get("stop"),
               None if pr.get("R") is None else round(pr["R"], 4), pr.get("final_reason"),
               a1.get("entry_status"), a1.get("outcome"), None if a1.get("R") is None else round(a1["R"], 4),
               a2.get("status"), None if a2.get("R") is None else round(a2["R"], 4)]
        fh.write("|".join("" if x is None else str(x) for x in row) + "\n")
json.dump({f"{k[0]} || {k[1]} || {k[2]}": v for k, v in SUMMARY.items()}, open(L.HERE / "s4_summary.json", "w"), default=str, indent=0)
out.close()
