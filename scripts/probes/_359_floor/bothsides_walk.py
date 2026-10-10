"""#359 Read A (both sides) — the #624 backfill screen re-run with the $500M cap ceiling LIFTED, so names on BOTH sides of the
floor pass the identical rule (gap >= 15% at a post-open tick, volume >= 90th pct, prior close >= $5) and are walked by
the identical walker (walk624.walk_primary, era D as of 2026-10-06). $0: reads only the captured #624 files.
Deviation: lib624.assert_frozen() NOT called — ep_detector.py drifted since 10-06 (shortlist ranking #694, audit
thresholds); the five constants lib624 imports from it are re-checked below.
Output: bothsides_rows.tsv (one row per signal, every band) + bothsides_out.txt."""
from __future__ import annotations
import sys, json, pickle, csv
from collections import defaultdict, Counter
from datetime import date, time, timedelta
from pathlib import Path
BF = Path(__file__).resolve().parents[1] / "_624_backfill"
sys.path.insert(0, str(BF))
import lib624 as L
import screen624 as S
import walk624 as W

assert (L.MIN_PREV_CLOSE, L.MIN_PREV_DAY_VOLUME, L.MIN_PREMARKET_SHARES, L.MAX_EXTENSION_PCT, L.EP_COOLDOWN_DAYS,
        L.MIN_ADV_DOLLAR_VOLUME, L.MAX_ATR_PCT) == (5.0, 50_000, 25_000, 50.0, 60, 1_000_000, 15.0)
assert float(L.LL.LANE_MAX_MARKET_CAP) == 5e8
L.LL.LANE_MAX_MARKET_CAP = float("inf")          # lift the ceiling: every cap read becomes a signal

W0, W1 = date(2024, 1, 2), date(2026, 9, 3)
dec = json.load(open(BF / "s1_decisions.json"))
K, MODE930, BASIS = dec["k"], dec["mode930"], dec["cap_basis"]
dg = pickle.load(open(BF / "digests.pkl", "rb"))
samp = json.load(open(BF / "s1_samples.json"))
cand_by = {(c["t"], c["d"]): c for c in L.load_cand()}
daily, splits, sect = L.load_daily(), L.load_splits(), L.load_sectypes()
refs = L.load_refs([BF / f for f in ("ref_s1a.jsonl", "ref_s1b.jsonl", "ref_s2.jsonl")])
day_rows = defaultdict(list)
for r in samp["BW"]:
    key = (r["t"], date.fromisoformat(r["d"]))
    day_rows[key[1]].append(cand_by[key])
res = S.screen(day_rows, dg, daily, splits, refs, k=K, mode930=MODE930, cap_basis=BASIS, sect=sect)
sigs = [s for s in res["signals"] if W0 <= s["d"] <= W1]
out = open(Path(__file__).parent / "bothsides_out.txt", "w")
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.write(s + "\n")
P(f"screen counts (ceiling lifted): {dict(res['counts'])}; signals in window {len(sigs)}")
P(f"   below $500M {sum(s['cap'] < 5e8 for s in sigs)} (the #624 P population was 768 — must match)")

by_t = defaultdict(list)
for s in sigs:
    by_t[s["t"]].append(s["d"])
for s in sigs:
    t, d = s["t"], s["d"]; dl = daily.get(t)
    prior = [x for x in by_t[t] if d - timedelta(days=L.EP_COOLDOWN_DAYS) <= x < d]
    s["ext"] = L.extension_pct(dl, d, s["pc_adj"])
    s["adv"] = L.adv_dollar(dl, d)
    s["atr_pct"] = L.atr_pct_stamp(dl, d) if (s["adv"] is not None and s["adv"] >= L.MIN_ADV_DOLLAR_VOLUME) else None
    st = L.blocking_stamps(ext=s["ext"], cooldown=bool(prior), days_since=(d - max(prior)).days if prior else None,
                           adv=s["adv"], atr_pct=s["atr_pct"], vol_raw=s["vol_raw"])
    s["stamps"] = ",".join(sorted({x["gate"] for x in st}))
    s["G"] = not st
    s["E"] = "extended" not in s["stamps"]
    s["G_nocd"] = not [x for x in st if x["gate"] != "cooldown"]     # quality + extension + pm shares, cooldown ignored

keys = {(s["t"], s["d"]) for s in sigs}
mins = L.load_minutes([BF / f for f in ("min_s1.tsv", "min_s2a.tsv", "min_s2b.tsv", "min_s2c.tsv")], keys=keys)
daily_cut = {t: {"rows": {x: r for x, r in dl["rows"].items() if x <= L.DATA_END},
                 "dates": [x for x in dl["dates"] if x <= L.DATA_END]} for t, dl in daily.items() if t in {k[0] for k in keys}}
cols = ["t", "d", "T", "cap", "gap", "pc_raw", "px_raw", "vol_raw", "pct", "ext", "adv", "atr_pct", "stamps", "E", "G",
        "G_nocd", "typed_today", "poly_type", "entry_status", "outcome", "R", "settled", "partial_fired", "final_reason"]
w = csv.writer(open(Path(__file__).parent / "bothsides_rows.tsv", "w"), delimiter="|")
w.writerow(cols)
for s in sigs:
    bars0 = L.as_dict_bars(s["d"], mins.get((s["t"], s["d"]), []))
    p = W.walk_primary(s["t"], s["d"], s["T"], bars0, daily_cut.get(s["t"]))
    row = dict(s, **{k: p.get(k) for k in ("entry_status", "outcome", "R", "settled", "partial_fired", "final_reason")})
    row["T"] = s["T"].strftime("%H:%M"); row["d"] = s["d"].isoformat()
    w.writerow([row.get(c) for c in cols])
P("rows written")
out.close()
