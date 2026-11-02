#!/usr/bin/env python3
"""Stage 0 check 1: the intraday volume pace (the live F1 rule) on Qullamaggie's buy days, minute by minute.
For each of his 269 buys (s0_buyfacts.tsv: the 5-day high to D, the 10/50-session average volume to D, the E bar), the
session E's minute bars from the replay's sealed minute stores (v1_replay.minute_index / held_in; the named
minutes_rev_1024 holds none of his buy days) are walked by the LIVE entry functions:
  HEADLINE ("live"): v1_replay.simulate_entry — the replay's tick-by-tick re-implementation around the live, imported
     breakout_v1_entry.evaluate / f1_permits / CUM_SHARE / _terminal_reason / stop_at_fill_decision: the order is placed
     only while F1 permits, cancelled for the day once F1 lapses, abstains when the day's range is too wide, the #500
     fallback when the price is already through the level; level = max(ORH5, list level). Bought = filled or
     sold-after-fill (it bought). Run with vol_bar = 0 (price only), OLD = 1.2 x the 50-session average, NEW = 1.2 x the
     10-session average (his ruling).
  LITERAL (cross-check): the first minute m whose tick (bars through m-1) says status ok AND F1 permits, and bar m's
     high reaches the level — no terminal cancel (a lapse may re-permit later).
No returns: only whether / when the buy happens. Writes s0_check1_buys.tsv and s0_check1.txt."""
import os, sys, time
from collections import Counter
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import s0_lib as L  # noqa
import v1_replay as R  # noqa
from scripts.probes._cb_backtest import runner  # noqa
from agents.market_intelligence.broker import breakout_v1_entry as bve  # noqa
from agents.market_intelligence.broker.breakout_v1_volume_curve import CUM_SHARE  # noqa
LOG = []
def say(s=""): print(s, flush=True); LOG.append(str(s))
clock = lambda m: "-" if m is None or (isinstance(m, float) and np.isnan(m)) else f"{9 + (30 + int(m)) // 60:02d}:{(30 + int(m)) % 60:02d}"

B = pd.read_csv(f"{HERE}/s0_buyfacts.tsv", sep="\t")
ent = pd.read_csv("/Users/alvinfung/apollo_data/cb702/qm_streams/holdings_1024/entries.tsv", sep="\t",
                  usecols=["eid", "first_clock_on_E", "flat_clock_on_E"])
B = B.merge(ent, on="eid", how="left")
say("=" * 100)
say("CHECK 1 — the intraday volume pace (live F1) on Qullamaggie's buy days")
say(f"  list level = the 5-day high to D from the daily store; equal to the feature table's v1 level on {int(np.isclose(B.level5, B.level_v1).sum())}/{len(B)}; "
    f"E is the next stored session on {int(B.E_next_bar.sum())}/{len(B)}")

rev = runner.load_done_pairs(R.CB / "minutes_rev_1024")
say(f"  coverage in the named store minutes_rev_1024 ({len(rev):,} pairs fetched): {sum((e, t) in rev for t, e in zip(B.ticker, B.E))} of his 269 buy days")
index = R.minute_index()
src = [R.held_in(index, e, t) for t, e in zip(B.ticker, B.E)]
say("  coverage in the replay's sealed minute stores (v1_replay.MINUTE_DIRS, < 2025 only): "
    f"{sum(s is not None for s in src)} of 269 — " + ", ".join(f"{k}: {v}" for k, v in Counter(str(s).split('apollo_data/')[-1] for s in src).items()))

t0 = time.time()
rows = []
files_of = {str(d): f for d, _, f in index}; done_of = {str(d): dn for d, dn, _ in index}
for r, s in zip(B.itertuples(), src):
    rec = {"eid": r.eid, "sym": r.sym, "ticker": r.ticker, "D": r.D, "E": r.E, "era": r.era, "big": r.big, "on_list": r.on_list,
           "store": str(s).split("apollo_data/")[-1] if s else None}
    if s is None:
        rec["state"] = "no_store"; rows.append(rec); continue
    blocks, _ = runner.read_minute_file(files_of[str(s)][r.E], {r.ticker})
    mb, state = runner.minutes_for(blocks, done_of[str(s)], r.E, r.ticker)
    rec["state"] = state
    if state != "ok" or mb is None or len(mb) == 0:
        rows.append(rec); continue
    mh, ml = float(mb.h.max()), float(mb.l.min())
    rec["mismatch"] = bool(abs(mh - r.E_h) / r.E_h > R.MISMATCH_MAX or abs(ml - r.E_l) / r.E_l > R.MISMATCH_MAX)
    rec["n_minutes"] = len(mb); rec["rth_vol_share"] = float(np.sum(mb.v)) / r.E_v
    mins = R.minutes_to_dict(mb)
    bars = {"price_only": 0.0, "OLD": 1.2 * r.vol50, "NEW": 1.2 * r.vol10}
    for name, vb in bars.items():
        tr = R.simulate_entry(mins, list_level=r.level5, adr20=r.adr20, vol_bar=vb)
        rec[f"{name}_outcome"] = tr["outcome"]; rec[f"{name}_reason"] = tr["reason"]
        rec[f"{name}_bought"] = tr["outcome"] in ("filled", "sold_after_fill")
        rec[f"{name}_minute"] = tr["fill_minute"]; rec[f"{name}_placed"] = tr["placed_m"]; rec[f"{name}_holds"] = tr["holds"]
        rec[f"{name}_level"] = tr["level"]
    for name in ("OLD", "NEW"):                                   # LITERAL
        vb, got, cur = bars[name], None, {}
        for m in range(bve.FIRST_MINUTE, bve.EOD_MINUTE):
            for k in (range(0, m) if m == bve.FIRST_MINUTE else (m - 1,)):
                if k in mins:
                    cur[k] = mins[k]
            st = bve.evaluate(cur, list_level=r.level5, adr20=r.adr20, vol_bar=vb, last_completed=m - 1)
            if st["status"] == "ok" and st["f1_ok"] and m in mins and mins[m]["high"] >= st["level"]:
                got = m; break
        rec[f"{name}_lit_minute"] = got; rec[f"{name}_lit_bought"] = got is not None
    # the F1 pace at his first sighting (the stream's first frame showing the position on E; he bought at or before it)
    if isinstance(r.first_clock_on_E, str):
        hh, mm = map(int, r.first_clock_on_E.split(":")); mh_ = (hh - 9) * 60 + mm - 30
        rec["his_minute"] = mh_
        lc = min(mh_ - 1, 389)
        cum = sum(b["volume"] for k, b in mins.items() if k <= lc) if lc >= 0 else 0.0
        for name in ("OLD", "NEW"):
            rec[f"{name}_f1_at_his"] = bool(lc >= 0 and bve.f1_permits(cum, bars[name], lc)[0])
    # the daily test (36) on the same day
    rec["daily_up"] = bool(r.E_h > r.level5); rec["daily_x10"] = r.E_v / r.vol10; rec["daily_x50"] = r.E_v / r.vol50
    rec["daily_NEW"] = rec["daily_up"] and rec["daily_x10"] >= 1.2; rec["daily_OLD"] = rec["daily_up"] and rec["daily_x50"] >= 1.2
    rows.append(rec)
T = pd.DataFrame(rows)
T.to_csv(f"{HERE}/s0_check1_buys.tsv", sep="\t", index=False)
say(f"  minute rows: {Counter(T.state)}; minute high/low off the daily bar by > 1% (excluded, as the replay's walk does): "
    f"{int(T.mismatch.fillna(False).sum())} ({', '.join(f'{a} {b}' for a, b in zip(T.sym[T.mismatch == True], T.E[T.mismatch == True]))}); "
    f"replayed in {time.time() - t0:.0f}s")
ok = T[(T.state == "ok") & (T.mismatch == False)].copy()
say(f"  regular-hours minute volume / the day's full daily volume: median {ok.rth_vol_share.median():.2f} "
    f"(the F1 curve's pooled end-of-day share is {CUM_SHARE[389]:.2f}; no rescale)")
say(f"  REPLAYED: {len(ok)} of 269 buys ({int(ok.on_list.sum())} on the rebuilt list; {int(ok.big.sum())} of the 26 big winners)")

def pops(df):
    return [("all his covered buys", df), ("his buys on the rebuilt list", df[df.on_list]),
            ("  era A on the list (36's 245)", df[df.on_list & (df.era == "A")]), ("  era B on the list", df[df.on_list & (df.era == "B")]),
            ("big winners", df[df.big])]

say("\n  BOUGHT ON HIS BUY DAY E (live replay; bought = filled or sold-after-fill):")
for name, d in pops(ok):
    n = len(d)
    say(f"    {name:32s} n={n:3d} | price only {int(d.price_only_bought.sum()):3d} | OLD 1.2x 50-day {int(d.OLD_bought.sum()):3d} | "
        f"NEW 1.2x 10-day {int(d.NEW_bought.sum()):3d} || literal OLD {int(d.OLD_lit_bought.sum()):3d}, NEW {int(d.NEW_lit_bought.sum()):3d} || "
        f"daily-bar test OLD {int(d.daily_OLD.sum()):3d}, NEW {int(d.daily_NEW.sum()):3d}")

say("\n  THE MINUTE OF THE BUY (live replay, clock ET):")
for name in ("price_only", "OLD", "NEW"):
    for pn, d in (("on the list", ok[ok.on_list]), ("big winners", ok[ok.big])):
        m = d.loc[d[f"{name}_bought"], f"{name}_minute"].astype(float)
        if len(m):
            say(f"    {name:10s} {pn:12s} bought {len(m):3d}: median {clock(m.median())}, quartiles {clock(m.quantile(.25))}-{clock(m.quantile(.75))}, "
                f"by 09:45 {int((m <= 15).sum())}, by 10:00 {int((m <= 30).sum())}, by 10:30 {int((m <= 60).sum())}, by 12:00 {int((m <= 150).sum())}, after 12:00 {int((m > 150).sum())}")

def why(r, name):
    o, rs = r[f"{name}_outcome"], str(r[f"{name}_reason"])
    if o in ("filled", "sold_after_fill"):
        return "bought"
    if "volume_below_curve" in rs:
        return "order placed, volume pace lapsed before the price reached the level (cancelled)"
    if o == "never_placed" and r[f"{name}_holds"] > 0:
        return "volume pace never met while the price setup held (never placed)"
    if o == "never_placed":
        return "never placed (no tick)"
    if "chase_cap" in rs or "stop_too_wide: fallback" in rs:
        return "price already past the level when the pace was met (#500 fallback: chase cap / width)"
    if "stop_too_wide" in rs:
        return "day low to level wider than the daily range (stop too wide)"
    if "unfilled_eod" in rs or "unfilled" in rs:
        return "placed, the high never reached the level = max(5-minute opening-range high, 5-day high)"
    return f"{o}: {rs[:60]}"
say("\n  WHY NOT BOUGHT (his buys on the rebuilt list):")
d = ok[ok.on_list]
for name in ("price_only", "OLD", "NEW"):
    c = Counter(why(r, name) for _, r in d.iterrows())
    say(f"    {name:10s} " + " | ".join(f"{k}: {v}" for k, v in c.most_common()))
nr = d[[why(d.loc[i], "price_only").startswith("placed, the high never") for i in d.index]]
say(f"    price_only 'never reached': {len(nr)}, of which the day's high cleared the 5-day high but not the 5-minute opening-range high: "
    f"{int(nr.daily_up.astype(bool).sum())} (" + ", ".join(f"{r.sym} {r.E}" for r in nr[nr.daily_up.astype(bool)].sort_values('E').itertuples()) + ")")
db = ok[ok.big]
c = Counter(why(r, "NEW") for _, r in db.iterrows())
say(f"    NEW, big winners: " + " | ".join(f"{k}: {v}" for k, v in c.most_common()))

say("\n  NEW (1.2x the last 10 days): live intraday vs the daily-bar test, his buys on the rebuilt list:")
for pn, dd in (("on the list", d), ("era A on the list", d[d.era == "A"]), ("big winners", db)):
    a, b = dd.NEW_bought.astype(bool), dd.daily_NEW.astype(bool)
    say(f"    {pn:18s} both {int((a & b).sum())} | intraday only {int((a & ~b).sum())} | daily only {int((~a & b).sum())} | neither {int((~a & ~b).sum())}")
do_ = d[~d.NEW_bought.astype(bool) & d.daily_NEW.astype(bool)]
say("    daily only, why the live replay did not buy: " + " | ".join(f"{k}: {v}" for k, v in Counter(why(do_.loc[i], "NEW") for i in do_.index).most_common()))
say("    daily only: " + ", ".join(f"{r.sym} {r.E}{' BIG' if r.big else ''}" for r in do_.sort_values("E").itertuples()))
io_ = d[d.NEW_bought.astype(bool) & ~d.daily_NEW.astype(bool)]
say(f"    intraday only, why the daily test did not fire: high not above the 5-day high {int((~io_.daily_up.astype(bool)).sum())} | "
    f"full-day volume under 1.2x the 10-day {int((io_.daily_x10 < 1.2).sum())} (median {io_.daily_x10.median():.2f}x)")
say("    intraday only: " + ", ".join(f"{r.sym} {r.E}{' BIG' if r.big else ''}" for r in io_.sort_values("E").itertuples()))
say("    big winners not bought under NEW: " + "; ".join(f"{db.sym[i]} {db.E[i]} ({why(db.loc[i], 'NEW')})" for i in db[~db.NEW_bought.astype(bool)].sort_values("E").index))

h = ok[ok.his_minute.notna() & ok.on_list]
say(f"\n  AT HIS OWN BUY TIME ({len(h)} of his on-list buys have a first-sighting clock on E in his stream; he bought at or before it):")
say(f"    first sighting: median {clock(h.his_minute.median())}, by 10:00 {int((h.his_minute <= 30).sum())}, before 09:35 (no tick yet) {int((h.his_minute < 5).sum())}")
for name in ("OLD", "NEW"):
    bo = h[f"{name}_bought"].astype(bool)
    say(f"    {name}: volume pace met by the minute before his sighting {int(h[f'{name}_f1_at_his'].sum())}/{len(h)} | "
        f"our replay bought at or before his sighting {int((bo & (h[f'{name}_minute'] <= h.his_minute)).sum())}, later the same day {int((bo & (h[f'{name}_minute'] > h.his_minute)).sum())}, not at all {int((~bo).sum())}")

say("\n  SIMPLIFICATIONS (stated, per the task):")
for s_ in ("broker mechanics are v1_replay.simulate_entry's re-implementation (stop-limit triggers on the first bar whose high >= level; "
           "the #500 fallback limit; cancel + re-place instantaneous; no partial fills; every minute bar published on time, so the 09:35 'wait for the 09:34 bar' never binds)",
           "one name alone: no 5-slot cap, no other strategy owning the ticker, no pre-flight, no sizing (the 'under 1 share' cancel is not modelled), switch on",
           "the list level / adr20 / volume averages come from the replay's daily stores (era A cb702_pre_v2, era B the sealed < 2025 cb702 copy), "
           "the live list reads mi_daily_closes; the minute bars are the replay's SIP minute stores on the same adjusted scale (checked: high/low within 1% of the daily bar)",
           "F1's curve (CUM_SHARE) is used unchanged with the NEW bar: the build changes only vol_bar to 1.2x the 10-session average",
           "his buy time is the first stream frame showing the position on E (an upper bound on when he bought), available for some buys only"):
    say(f"    - {s_}")
open(f"{HERE}/s0_check1.txt", "w").write("\n".join(LOG) + "\n")
