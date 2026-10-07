"""#624 backfill — STAGE 2/3: digest the minute capture, build the reference-read list, screen, compose, HALT-check.
OUTCOME-BLIND: nothing here walks a trade or reads an outcome table.

  --digest  : stream every minute capture -> digests.pkl; W4 pull errors; the historical basis check (split rows)
  --list    : free-term survivors under k=15 (primary) UNION k=0 (S3) still needing a reference read -> list_ref_s2.txt
  --compose : primary / S3 / S4 screens over 2024-01-02..2026-09-03, stamps, serial + cooldown flags, the composition
              table, W1 / W2 / W4(data) and the prereg HALT checks -> s3_compose_out.txt, signals_*.json
"""
from __future__ import annotations

import json
import pickle
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, time, timedelta

import lib624 as L
import screen624 as S

L.assert_frozen()
MODE = sys.argv[1]
W0, W1 = date(2024, 1, 2), date(2026, 9, 3)
MIN_FILES = [L.HERE / f for f in ("min_s1.tsv", "min_s2a.tsv", "min_s2b.tsv", "min_s2c.tsv")]
LOG_FILES = [L.HERE / f for f in ("log_min_s1.txt", "log_min_s2a.txt", "log_min_s2b.txt", "log_min_s2c.txt")]
REF_FILES = [L.HERE / f for f in ("ref_s1a.jsonl", "ref_s1b.jsonl", "ref_s2.jsonl")]
dec = json.load(open(L.HERE / "s1_decisions.json"))
K, MODE930, BASIS = dec["k"], dec["mode930"], dec["cap_basis"]


def block_of(d: date) -> str:
    return "DISC_2024" if d <= date(2024, 12, 31) else ("HELD_A_2025-0605" if d <= date(2026, 6, 5) else "INSAMPLE_0608-0903")


if MODE == "--digest":
    samp = json.load(open(L.HERE / "s1_samples.json"))
    want = {(r["t"], date.fromisoformat(r["d"])) for r in samp["BW"] + samp["LW"]}
    dg = {}
    for t, d, bars in L.iter_minutes([p for p in MIN_FILES]):
        if (t, d) in want:
            if (t, d) in dg:      # a key split across files: merge
                raise SystemExit(f"key {t} {d} appears twice in the captures")
            dg[(t, d)] = S.digest(t, d, bars)
    mlog = L.load_minlog(LOG_FILES)
    errs = Counter(v[2] for v in mlog.values() if v[2] != "ok")
    zero = sum(1 for k in want if k in mlog and mlog[k][1] == 0)
    for k in want:
        if k not in dg:
            dg[k] = {"n": 0}
    pickle.dump(dg, open(L.HERE / "digests.pkl", "wb"))
    out = open(L.HERE / "s2_digest_out.txt", "w")
    def P(*a):
        s = " ".join(str(x) for x in a); print(s); out.write(s + "\n")
    P(f"prefilter keys {len(want)}; logged pulls {sum(1 for k in want if k in mlog)}; pull errors {sum(errs.values())} {dict(errs)} "
      f"({sum(errs.values()) / max(1, len(want)):.2%} — W4 bar 2%); keys with zero bars 04:00-16:00 {zero}")
    # historical basis check: Polygon adjusted minutes vs mi_daily_closes on split-affected rows (fac != 1)
    daily = L.load_daily()
    splits = L.load_splits()
    rows = {"split": Counter(), "nosplit": Counter()}
    worst = []
    for (t, d), g in dg.items():
        if not g.get("n") or d > W1:
            continue
        dl = daily.get(t)
        r = dl["rows"].get(d) if dl else None
        if not r or not r["v"] or not g.get("o930") or not r["o"]:
            continue
        grp = "split" if L.fac_prior(splits, t, d) != 1.0 else "nosplit"
        c = rows[grp]
        c["n"] += 1
        vr = g["vol_full"] / r["v"]
        orr = g["o930"] / r["o"]
        c["vol_full_within_10pct"] += 0.9 <= vr <= 1.1
        c["vol_full_over_daily"] += vr > 1.0001
        c["open_within_0.5pct"] += abs(orr - 1) <= 0.005
        c["open_off_5pct"] += abs(orr - 1) > 0.05
        if grp == "split" and (abs(orr - 1) > 0.05 or not 0.5 <= vr <= 2):
            worst.append((t, d.isoformat(), round(vr, 3), round(orr, 3)))
    P(f"BASIS CHECK (Polygon adjusted minutes vs mi_daily_closes, same day): split-affected rows {dict(rows['split'])}; "
      f"others {dict(rows['nosplit'])}")
    P(f"   split rows with the 09:30 open > 5% off the daily open or full-day minute volume outside 0.5-2x the daily: {len(worst)} {worst[:15]}")
    out.close()

elif MODE == "--list":
    dg = pickle.load(open(L.HERE / "digests.pkl", "rb"))
    samp = json.load(open(L.HERE / "s1_samples.json"))
    cand_by = {(c["t"], c["d"]): c for c in L.load_cand()}
    daily, splits, sect = L.load_daily(), L.load_splits(), L.load_sectypes()
    refs = L.load_refs(REF_FILES)
    day_rows = defaultdict(list)
    for r in samp["BW"]:
        key = (r["t"], date.fromisoformat(r["d"]))
        day_rows[key[1]].append(cand_by[key])
    need = set()
    for k in (K, 0):
        res = S.screen(day_rows, dg, daily, splits, None, k=k, mode930=MODE930, cap_basis=BASIS, sect=sect)
        print(f"k={k}: free-term survivors {len(res['need_ref'])}; counts {dict(res['counts'])}")
        need |= res["need_ref"]
    todo = sorted(need - set(refs), key=lambda x: (x[1], x[0]))
    open(L.HERE / "list_ref_s2.txt", "w").write("\n".join(f"{t}|{d}" for t, d in todo) + "\n")
    print(f"union {len(need)}; to read {len(todo)} -> list_ref_s2.txt")

elif MODE == "--compose":
    out = open(L.HERE / "s3_compose_out.txt", "w")
    def P(*a):
        s = " ".join(str(x) for x in a); print(s); out.write(s + "\n")
    dg = pickle.load(open(L.HERE / "digests.pkl", "rb"))
    samp = json.load(open(L.HERE / "s1_samples.json"))
    cand_by = {(c["t"], c["d"]): c for c in L.load_cand()}
    daily, splits, sect = L.load_daily(), L.load_splits(), L.load_sectypes()
    refs = L.load_refs(REF_FILES)
    day_rows = defaultdict(list)
    for r in samp["BW"]:
        key = (r["t"], date.fromisoformat(r["d"]))
        day_rows[key[1]].append(cand_by[key])
    P(f"# #624 COMPOSITION (no outcome computed) — k={K}, 09:30 price {MODE930}, cap basis {BASIS}; "
      f"window {W0}..{W1}; prefilter rows {sum(len(v) for v in day_rows.values())} on {len(day_rows)} sessions")
    pref = samp["prefilter"]
    P(f"PREFILTER (s1_lists): {pref}")

    runs = {"P": (K, BASIS), "S3_rt_volume": (0, BASIS), "S4_cap_at_tick": (K, "tick")}
    allsig = {}
    for name, (k, basis) in runs.items():
        res = S.screen(day_rows, dg, daily, splits, refs, k=k, mode930=MODE930, cap_basis=basis, sect=sect)
        allsig[name] = res
        P(f"SCREEN {name} (k={k}, cap {basis}): {dict(res['counts'])}; reference reads missing for survivors {len(res['need_ref'])}")

    def stamp(sigs: list[dict]) -> list[dict]:
        by_t = defaultdict(list)
        for s in sigs:
            by_t[s["t"]].append(s["d"])
        for s in sigs:
            t, d = s["t"], s["d"]
            dl = daily.get(t)
            prior = [x for x in by_t[t] if d - timedelta(days=L.EP_COOLDOWN_DAYS) <= x < d]
            win = [x for x in by_t[t] if d - timedelta(days=60) < x <= d]
            s["ext"] = L.extension_pct(dl, d, s["pc_adj"])
            s["adv"] = L.adv_dollar(dl, d)
            s["atr_pct"] = L.atr_pct_stamp(dl, d) if (s["adv"] is not None and s["adv"] >= L.MIN_ADV_DOLLAR_VOLUME) else None
            s["cooldown"] = bool(prior)
            s["days_since_prior"] = (d - max(prior)).days if prior else None
            s["stamps"] = L.blocking_stamps(ext=s["ext"], cooldown=s["cooldown"], days_since=s["days_since_prior"],
                                            adv=s["adv"], atr_pct=s["atr_pct"], vol_raw=s["vol_raw"])
            gates = {x["gate"] for x in s["stamps"]}
            s["E"] = "extended" not in gates
            s["G"] = not gates
            s["serial"] = len(win) >= 3
            s["first_in_60d"] = not prior
            s["block"] = block_of(d)
            s["walkable"] = s["T"] < time(9, 45)
            s["last_row"] = dl["dates"][-1] if dl else None
        return sigs

    P_sig = stamp([s for s in allsig["P"]["signals"] if W0 <= s["d"] <= W1])
    for name in ("S3_rt_volume", "S4_cap_at_tick"):
        stamp([s for s in allsig[name]["signals"] if W0 <= s["d"] <= W1])
    n = len(P_sig)
    tick_n = Counter(s["t"] for s in P_sig)
    month_n = Counter(s["d"].strftime("%Y-%m") for s in P_sig)
    P(f"\n## POPULATION P: {n} signals on {len(tick_n)} tickers over {len({s['d'] for s in P_sig})} sessions "
      f"(expected ~670, plausible 300-1,500)")
    for blk in ("DISC_2024", "HELD_A_2025-0605", "INSAMPLE_0608-0903"):
        b = [s for s in P_sig if s["block"] == blk]
        P(f"   {blk}: signals {len(b)}, walkable (tick < 09:45) {sum(s['walkable'] for s in b)}, tickers {len({s['t'] for s in b})}")
    P(f"   OUT-OF-SAMPLE (2024-01-02..2026-06-05): {sum(1 for s in P_sig if s['d'] <= date(2026, 6, 5))}")
    P("   by tick: " + ", ".join(f"{T.strftime('%H:%M')} {c}" for T, c in sorted(Counter(s['T'] for s in P_sig).items())))
    bands = lambda v, cuts, labels: next(lab for c, lab in zip(cuts + [float('inf')], labels) if v < c)
    P("   cap band: " + str(dict(Counter(bands(s["cap"], [25e6, 100e6, 200e6], ["<25M", "25-100M", "100-200M", "200-500M"]) for s in P_sig))))
    P("   prior close (raw): " + str(dict(Counter(bands(s["pc_raw"], [10, 20, 50], ["5-10", "10-20", "20-50", "50+"]) for s in P_sig))))
    P("   gap at the tick: " + str(dict(Counter(bands(s["gap"], [20, 30, 50, 100], ["15-20", "20-30", "30-50", "50-100", "100+"]) for s in P_sig))))
    P("   typed today: " + str(dict(Counter(s["typed_today"] for s in P_sig))) + "; Polygon type on D: " + str(dict(Counter(s["poly_type"] for s in P_sig))))
    gate_n = Counter(g["gate"] for s in P_sig for g in s["stamps"])
    P(f"   stamps: {dict(gate_n)}; E (extension passed) {sum(s['E'] for s in P_sig)}; G (all five passed) {sum(s['G'] for s in P_sig)}")
    P(f"   serial rows (>= 3 lane signals in 60 days ending D) {sum(s['serial'] for s in P_sig)}; first-in-60-days rows {sum(s['first_in_60d'] for s in P_sig)}")
    ser = defaultdict(list)
    for s in P_sig:
        ser[s["t"]].append(s["d"])
    serial_names = sorted(t for t, ds in ser.items() if any(sum(1 for y in ds if x <= y < x + timedelta(days=60)) >= 3 for x in ds))
    P(f"   tickers with >= 3 signals in any 60-day span ({len(serial_names)}): {', '.join(serial_names)}")
    P(f"   top tickers by signal count: {tick_n.most_common(12)}")
    P(f"   top months: {month_n.most_common(6)}")

    # exclusions (P screen, whole window)
    disp = allsig["P"]["disp"]
    dc = Counter(v.split(":")[0] if not v.startswith("signal") else "signal" for (t, d), v in disp.items() if W0 <= d <= W1)
    P(f"\n## EXCLUSIONS (P screen, per ticker-day): {dict(dc)}")
    P(f"   non-common detail: {dict(Counter(v for (t, d), v in disp.items() if W0 <= d <= W1 and v.startswith('non_common')))}")
    P(f"   cap unavailable detail: {dict(Counter(v for (t, d), v in disp.items() if W0 <= d <= W1 and v.startswith('cap_unavailable')))}")
    P(f"   untyped-today names in P: {sum(1 for s in P_sig if s['typed_today'] == 'untyped_today')} rows on "
      f"{len({s['t'] for s in P_sig if s['typed_today'] == 'untyped_today'})} tickers")

    # W1 / W2 / W4 (data) and the HALT checks
    stopped = {t for t in tick_n if (daily.get(t) or {}).get("dates", [date.max])[-1] < date(2026, 9, 1)}
    w1_share = len(stopped) / max(1, len(tick_n))
    w1_untyped = sum(1 for s in P_sig if s["typed_today"] == "untyped_today")
    w1_fail = w1_share < 0.05 or w1_untyped == 0
    surv = sum(c for k2, c in dc.items() if k2 in ("signal", "rejected_cap", "cap_unavailable"))
    w2 = dc.get("cap_unavailable", 0) / max(1, surv)
    walk = [s for s in P_sig if s["walkable"]]
    bad930 = sum(1 for s in walk if not dg[(s["t"], s["d"])].get("has930"))
    cov_bad = 0
    for s in walk:
        g = dg[(s["t"], s["d"])]
        if not g.get("has930"):
            continue
        sub = max(s["T"], time(9, 31))
        sm = sub.hour * 60 + sub.minute
        if sum(1 for m in g["mods_0930_1000"] if m >= sm) < 600 - sm:
            cov_bad += 1
    w4_share = (bad930 + cov_bad) / max(1, len(walk))
    mlog = L.load_minlog(LOG_FILES)
    errs = sum(1 for (t, d), v in mlog.items() if v[2] != "ok" and W0 <= d <= W1)
    w4_err = errs / max(1, sum(1 for (t, d) in mlog if W0 <= d <= W1))
    P(f"\n## VOID / HALT CHECKS (before any outcome)")
    P(f"   W1 survivorship: {len(stopped)} of {len(tick_n)} signal tickers ({w1_share:.1%}) stopped trading before 2026-09-01 "
      f"(bar >= 5%); untyped-today rows in P {w1_untyped} (bar > 0) -> {'VOID' if w1_fail else 'ok'}")
    P(f"   W2 cap coverage: unreadable {dc.get('cap_unavailable', 0)} of {surv} free-term survivors that reached a cap read "
      f"({w2:.1%}; bar 20%) -> {'VOID + HALT' if w2 > 0.20 else 'ok'}")
    P(f"   W4 data: walkable signals {len(walk)}; no 09:30 bar {bad930}; signals with a gap in the minute record between "
      f"their submit and 10:00 {cov_bad} -> {w4_share:.1%} (bar 15%); minute-pull errors {errs} ({w4_err:.2%}; bar 2%)")
    halt = []
    if not 150 <= n <= 3000:
        halt.append(f"signals {n} outside 150-3,000")
    top_t, top_c = tick_n.most_common(1)[0] if tick_n else ("", 0)
    if n and top_c / n > 0.03:
        halt.append(f"ticker {top_t} carries {top_c}/{n} = {top_c / n:.1%} of signals (> 3%)")
    top_m, top_mc = month_n.most_common(1)[0] if month_n else ("", 0)
    if n and top_mc / n > 0.12:
        halt.append(f"month {top_m} carries {top_mc}/{n} = {top_mc / n:.1%} of signals (> 12%)")
    if w2 > 0.20:
        halt.append(f"W2 cap unreadable {w2:.1%} > 20%")
    P(f"   HALT checks: top ticker {top_t} {top_c}/{n} ({top_c / max(1, n):.1%}); top month {top_m} {top_mc}/{n} ({top_mc / max(1, n):.1%}) "
      f"-> {'HALT: ' + '; '.join(halt) if halt else 'no halt'}")
    for name in allsig:
        sigs = [s for s in allsig[name]["signals"] if W0 <= s["d"] <= W1]
        json.dump([{k2: (v.isoformat() if isinstance(v, (date, time)) else v) for k2, v in s.items()} for s in sigs],
                  open(L.HERE / f"signals_{name}.json", "w"), default=str)
    json.dump({f"{t}|{d}": v for (t, d), v in allsig["P"]["disp"].items()}, open(L.HERE / "disp_P.json", "w"))
    json.dump({"halt": halt, "w1_void": w1_fail, "w2": w2, "w4_data_share": w4_share, "w4_err": w4_err, "n": n},
              open(L.HERE / "s3_checks.json", "w"), indent=1)
    out.close()
