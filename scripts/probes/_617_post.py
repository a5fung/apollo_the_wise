#!/usr/bin/env python3
"""#617 STEP 1 — post-processing of `_617_replay_out.tsv`: (1) RE-DERIVE the two D-1 floors on the
RAW Alpaca prior-session close/volume — what the Polygon snapshot's prevDay carried ON THE DAY —
because mi_daily_closes is rewritten split-ADJUSTED after a reverse split (upsert_ticker_history),
so a stock that traded at $0.95 in June reads $118 in the capture (LGCL) and was mis-filed as
"passes_universe"; (2) the tick-bound-stop flag (entry < $1 or stop width < $0.05 — a one-tick slip
is a large fraction of R, the operator's "theoretically traded" bar); (3) the share of each band
that printed >= 9% inside 09:30-09:44 on raw minute bars — names today's real-time gap authority
(live since 2026-08-27) admits regardless of the open; (4) the per-band P14 cost.
Output: `_617_post_out.txt`. $0, offline."""
import csv, sys
from collections import Counter
from datetime import date, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from scripts.probes._617_replay import load_bars
rows = list(csv.DictReader(open(HERE / "_617_replay_out.tsv"), delimiter="\t"))
minutes, daily, dsplit, _ = load_bars(HERE / "_617_bars.psv.gz")
def f(v):
    try: return float(v)
    except (TypeError, ValueError): return None
def raw_prev(t, d):
    db = daily.get(t, {}); prior = [x for x in db if x < d]
    return (db[max(prior)]["c"], db[max(prior)]["v"]) if prior else (None, None)
def inwin_gap(t, d, pc):
    """(touch, sustain): touch = the 09:30-09:44 minute-bar HIGH vs raw prior close (an UPPER bound on
    real-time admission); sustain = the live #490 rule mirrored (ep_detector._sustain_ok, toggle
    ep_rt_sustain_enabled ON in prod since 2026-08-02): the best run of 3 CONSECUTIVE minute CLOSES
    all >= +9% inside the window -> True/False (None = no bars)."""
    bars = [b for b in minutes.get((t, d), []) if time(9, 30) <= b["m"].time() < time(9, 45)]
    if not bars or not pc:
        return None, None
    touch = max(b["h"] for b in bars) / pc * 100 - 100
    run, best = 0, 0
    for b in bars:
        run = run + 1 if (b["c"] - pc) / pc * 100 >= 9.0 else 0
        best = max(best, run)
    return touch, best >= 3
out = []
for r in rows:
    t, d = r["ticker"], date.fromisoformat(r["trade_date"])
    pc, pv = raw_prev(t, d)
    s = r["set"]
    if r["artifact"] == "True":
        s2 = "artifact_or_otc"
    elif pc is not None and pc < 5.0:
        s2 = "MIN_PREV_CLOSE"            # raw D-1 close under $5: the live floor's own verdict
    elif pv is not None and pv < 50_000:
        s2 = "MIN_PREV_DAY_VOLUME"
    elif s.startswith("gap_floor") or s == "silent_no_row":
        s2 = s
    else:
        s2 = "reclass_passes_floors:" + s  # filed under a floor by the adjusted capture, passes on raw
    e, st = f(r["entry_px_0931"]), f(r["stop_0931"])
    tick = (e is not None and (e < 1.0 or (e - st) < 0.05))
    touch, sustain = inwin_gap(t, d, pc)
    out.append({**r, "set2": s2, "raw_pc": pc, "raw_pv": pv, "tick_bound": tick,
                "inwin": touch, "sustain": sustain})
order = ["gap_floor_8_9", "gap_floor_7_8", "gap_floor_6_7", "gap_floor_5_6", "gap_floor_9to10_admitted_now",
         "silent_no_row", "MIN_PREV_CLOSE", "MIN_PREV_DAY_VOLUME", "artifact_or_otc"]
extra = sorted({x["set2"] for x in out} - set(order))
print("== reclassified on RAW D-1 close/volume (set -> set2 moves) ==")
mv = Counter((x["set"], x["set2"]) for x in out if x["set"] != x["set2"])
for k, v in mv.most_common(): print(f"  {k[0]} -> {k[1]}: {v}")
print("\n== per set (raw-basis): n | with_bars | settled | >=4R | >=4R ex tick-bound | >=2R | >0 | sumR | meanR | ORB-rule no_trade | no_entry | abstain | bar-rows TOUCHING >=9% in 09:30-09:44 (upper bound) | bar-rows SUSTAINING >=9% 3 consecutive closes (the live rule) ==")
for s in order + extra:
    sub = [x for x in out if x["set2"] == s]
    if not sub: continue
    wb = [x for x in sub if int(x["n_min_bars"]) > 0 and x["artifact"] != "True"]
    se = [x for x in sub if x["status_0931"] == "settled"]
    R = [f(x["realized_r_0931"]) for x in se]
    ge4 = [x for x in se if f(x["realized_r_0931"]) >= 4]
    ge4nt = [x for x in ge4 if not x["tick_bound"]]
    cross = [x for x in wb if (x["inwin"] or 0) >= 9.0]
    sus = [x for x in wb if x["sustain"]]
    st = Counter(x["status_0931"] for x in sub)
    print(f"  {s:30s} {len(sub):5d} | {len(wb):4d} | {len(se):4d} | {len(ge4)} | {len(ge4nt)} | {sum(1 for x in R if x >= 2):3d} | "
          f"{sum(1 for x in R if x > 0):3d} | {sum(R):+7.1f} | {(sum(R)/len(R) if R else 0):+.2f} | {st['no_trade']:3d} | {st['no_entry']:3d} | {st['abstain']:3d} | "
          f"{(len(cross)/len(wb)*100 if wb else 0):4.0f}% ({len(cross)}/{len(wb)}) | {(len(sus)/len(wb)*100 if wb else 0):4.0f}% ({len(sus)}/{len(wb)})")
    for x in sorted(ge4, key=lambda x: -f(x["realized_r_0931"])):
        print(f"      >=4R {x['ticker']:6s} {x['trade_date']} gap {f(x['cap_gap']):6.1f} raw_pc {x['raw_pc']:.3f} entry {f(x['entry_px_0931']):.3f} "
              f"stop_w {f(x['entry_px_0931'])-f(x['stop_0931']):.3f} ({(f(x['entry_px_0931'])-f(x['stop_0931']))/f(x['entry_px_0931'])*100:.2f}%) "
              f"R {f(x['realized_r_0931']):+.2f} tick_bound={x['tick_bound']} inwin touch {x['inwin'] or 0:.1f}% sustain={x['sustain']} final {x['final_0931']}")
# P14 cost per band: never-admitted per session (64 sessions), and est. alerts at the adjacent admitted band's conversion
print("\n== P14 cost per band (64 sessions Jun-Aug) ==")
for s in ("gap_floor_8_9", "gap_floor_7_8", "gap_floor_6_7", "gap_floor_5_6"):
    sub = [x for x in out if x["set2"] == s]
    wb = [x for x in sub if int(x["n_min_bars"]) > 0 and x["artifact"] != "True"]
    cross = sum(1 for x in wb if (x["inwin"] or 0) >= 9.0)
    sus = sum(1 for x in wb if x["sustain"])
    resid_t = len(sub) * (1 - (cross / len(wb) if wb else 0))
    resid_s = len(sub) * (1 - (sus / len(wb) if wb else 0))
    print(f"  {s:16s} never-admitted n={len(sub):4d} -> {len(sub)/64:5.1f}/session; bar-rows touching >=9% in-window {cross}/{len(wb)}, "
          f"sustaining (live rule) {sus}/{len(wb)} -> residual after today's RT admission ~{resid_s:5.0f} = {resid_s/64:4.1f}/session "
          f"(touch-basis lower bound {resid_t/64:4.1f}); est. alerts at 5.3% conversion ~{resid_s*0.053:4.1f}/quarter")
with open(HERE / "_617_post_rows.tsv", "w") as fh:
    cols = list(out[0].keys()); fh.write("\t".join(cols) + "\n")
    for x in out: fh.write("\t".join("" if x[c] is None else str(x[c]) for c in cols) + "\n")
