"""#624 backfill — STAGE 1 calibration and anchors (prereg §2 C1-C4, §5 A1/A2, W6). Outcome-blind EXCEPT A2, whose
outcomes are the LIVE window's (mi_lowcap_lane_replays), never the backfill's.

  --phase 1 : C1, C2, C3, C4, W6 + the input spot-check; picks k / the 09:30 price / the cap basis by the frozen
              rules; writes list_ref_s1b.txt (live-window free-term survivors still needing a reference read).
  --phase 2 : A1 (re-find the live signals) and A2 (re-price the live walks).
Output: s1_calib_out.txt (phase 1) / s1_anchor_out.txt (phase 2); decisions in s1_decisions.json.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

import lib624 as L
import screen624 as S

L.assert_frozen()
PHASE = 2 if "--phase" in sys.argv and sys.argv[sys.argv.index("--phase") + 1] == "2" else 1
log = open(L.HERE / ("s1_calib_out.txt" if PHASE == 1 else "s1_anchor_out.txt"), "w")


def P(*a):
    s = " ".join(str(x) for x in a)
    print(s); log.write(s + "\n")


daily = L.load_daily()
splits = L.load_splits()
sect = L.load_sectypes()
samp = json.load(open(L.HERE / "s1_samples.json"))
sig = json.load(open(L.HERE / "s0_lane_signals.json"))
mins = L.load_minutes([L.HERE / "min_s1.tsv"])
mlog = L.load_minlog([L.HERE / "log_min_s1.txt"])
refs = L.load_refs([L.HERE / "ref_s1a.jsonl", L.HERE / "ref_s1b.jsonl"])
P(f"# #624 Stage 1 phase {PHASE} — run {datetime.now(L.ET).isoformat(timespec='seconds')}")
P(f"minute pulls logged {len(mlog)} (errors {sum(1 for v in mlog.values() if v[2] != 'ok')}, zero-bar keys "
  f"{sum(1 for v in mlog.values() if v[1] == 0)}); keys with bars {len(mins)}; reference reads {len(refs)}")


def tick_of(ts: str) -> time:
    dt = datetime.fromisoformat(ts).astimezone(L.ET)
    return time(dt.hour, dt.minute)


L19 = []
for s in sig:
    d = date.fromisoformat(s["scan_date"])
    L19.append({"t": s["ticker"], "d": d, "T": tick_of(s["tick_wallclock_et"]), "vol": s["today_volume_delayed"],
                "vol_rt": s["today_volume_rt"], "px": s["current_price"], "pc": s["prev_close"], "cap": s["market_cap"],
                "pct": s["vol_percentile"], "hist_n": s["vol_history_n"], "gap": s["gap_pct"], "id": s["id"]})
F300 = []
for r in samp["F300"]:
    hh, mm = map(int, r["tick"].split(":"))
    F300.append({"t": r["t"], "d": date.fromisoformat(r["d"]), "T": time(hh, mm), "vol": r["vol"]})


def pct(t, d, vol_adj):
    h = L.vol_history(daily.get(t), d)
    return (L.LL._volume_percentile(vol_adj, h) if h else None), len(h)


if PHASE == 1:
    dec = {}
    # ── C1 volume cut-off ──
    P("\n## C1 — the acting (delayed) volume: proxy = Polygon minute volume in [04:00, T - k)")
    c1 = {}
    for k in S.K_SET:
        ratios, agree_f, n_f, agree_l, n_l, miss = [], 0, 0, 0, 0, 0
        for r in F300:
            bars = mins.get((r["t"], r["d"]), [])
            fd = L.fac_day(splits, r["t"], r["d"])
            prox = L.tick_volume(bars, r["T"], k)
            if not bars:
                miss += 1
            ratios.append(prox / fd / r["vol"] if r["vol"] else float("nan"))
            p1, _ = pct(r["t"], r["d"], prox)
            p2, _ = pct(r["t"], r["d"], r["vol"] * fd)
            n_f += 1
            agree_f += ((p1 or 0) >= 90.0) == ((p2 or 0) >= 90.0)
        for r in L19:
            bars = mins.get((r["t"], r["d"]), [])
            fd = L.fac_day(splits, r["t"], r["d"])
            prox = L.tick_volume(bars, r["T"], k)
            p1, _ = pct(r["t"], r["d"], prox)
            p2, _ = pct(r["t"], r["d"], r["vol"] * fd)
            n_l += 1
            agree_l += ((p1 or 0) >= 90.0) == ((p2 or 0) >= 90.0)
        rr = [x for x in ratios if not math.isnan(x)]
        med = statistics.median(rr)
        within = sum(1 for x in rr if 0.8 <= x <= 1.2) / len(ratios)
        ok = 0.90 <= med <= 1.10 and within >= 0.80 and agree_f / n_f >= 0.90 and agree_l >= 17
        c1[k] = {"median_ratio": med, "within20": within, "agree_f300": agree_f / n_f, "agree_l19": agree_l, "pass": ok}
        P(f"   k={k:2d}: F300 median ratio {med:.3f}, within ±20% {within:.1%}, p90-verdict agreement F300 "
          f"{agree_f}/{n_f} ({agree_f / n_f:.1%}), L19 {agree_l}/{n_l}; F300 rows with no minute bars {miss} -> {'PASS' if ok else 'fail'}")
    if c1[15]["pass"]:
        k_pick = 15
    else:
        passing = [k for k in c1 if c1[k]["pass"]]
        k_pick = min(passing, key=lambda k: abs(c1[k]["median_ratio"] - 1.0)) if passing else None
    P(f"   C1 -> {'k = ' + str(k_pick) if k_pick is not None else 'NO cut-off passes: HALT'}")
    dec["k"] = k_pick
    # per-tick ratio at k=15, descriptive
    byT = defaultdict(list)
    for r in F300:
        bars = mins.get((r["t"], r["d"]), [])
        fd = L.fac_day(splits, r["t"], r["d"])
        byT[r["T"].strftime("%H:%M")].append(L.tick_volume(bars, r["T"], 15) / fd / r["vol"])
    P("   k=15 median ratio by tick (F300): " + ", ".join(f"{T} {statistics.median(v):.3f} (n={len(v)})" for T, v in sorted(byT.items())))

    # ── C2 tick price ──
    P("\n## C2 — the price at the tick vs the stored live current_price (L19)")
    c2 = {}
    for mode in S.MODES:
        good, rows = 0, []
        for r in L19:
            bars = mins.get((r["t"], r["d"]), [])
            px = L.tick_price(bars, r["T"], mode)
            fd = L.fac_day(splits, r["t"], r["d"])
            rel = (px * fd / r["px"] - 1) if (px and r["px"]) else None
            ok = rel is not None and abs(rel) <= 0.01
            good += ok
            rows.append(f"{r['t']} {r['d']} {r['T'].strftime('%H:%M')} recon {px if px is None else round(px * fd, 4)} vs stored {r['px']} "
                        f"({'—' if rel is None else f'{rel:+.2%}'}){'' if ok else ' MISS'}")
        c2[mode] = good
        P(f"   mode {mode}: within 1% on {good}/19 -> {'PASS' if good >= 16 else 'fail'}")
        for x in rows:
            P("      " + x)
    mode_pick = "open930" if c2["open930"] >= 16 else ("close929" if c2["close929"] >= 16 else None)
    P(f"   C2 -> {mode_pick or 'HALT'}")
    dec["mode930"] = mode_pick

    # ── C4 history ──
    P("\n## C4 — the reconstructed history fed the STORED delayed volume (L19)")
    good = 0
    for r in L19:
        fd = L.fac_day(splits, r["t"], r["d"])
        p, n = pct(r["t"], r["d"], r["vol"] * fd)
        ok = n == r["hist_n"] and p is not None and abs(p - r["pct"]) <= 0.1
        good += ok
        P(f"   {r['t']} {r['d']}: history n {n} vs stored {r['hist_n']}; percentile {p} vs stored {r['pct']}{'' if ok else ' MISS'}")
    P(f"   C4 -> {good}/19 reproduced -> {'PASS' if good >= 17 else 'FAIL: HALT'}")
    dec["c4_pass"] = good >= 17

    # ── C3 cap ──
    P("\n## C3 — Polygon point-in-time shares x raw prior close vs the live cap (yfinance)")
    c3 = {}
    for basis in ("pc", "tick"):
        ag_s = n_s = unread_s = 0
        lr = []
        for r in samp["S300"]:
            ref = refs.get((r["t"], date.fromisoformat(r["d"])))
            sh = L.shares_of(ref)
            base = r["pc"] if basis == "pc" else r["px"]
            n_s += 1
            if sh is None or not base:
                unread_s += 1; continue
            cap = sh * base
            ag_s += (cap < 5e8) == (r["cap"] < 5e8)
            lr.append(abs(math.log(cap / r["cap"])))
        ag_l = unread_l = 0
        rows = []
        for r in L19:
            ref = refs.get((r["t"], r["d"]))
            sh = L.shares_of(ref)
            base = r["pc"] if basis == "pc" else r["px"]
            if sh is None:
                unread_l += 1; rows.append(f"{r['t']} {r['d']}: shares unreadable (http {ref and ref.get('http')})"); continue
            cap = sh * base
            ok = (cap < 5e8) == (r["cap"] < 5e8)
            ag_l += ok
            rows.append(f"{r['t']} {r['d']}: polygon {cap / 1e6:.1f}M vs live {r['cap'] / 1e6:.1f}M{'' if ok else ' DISAGREE'}")
        okb = ag_s / n_s >= 0.90 and ag_l >= 17
        c3[basis] = okb
        P(f"   basis {basis}: S300 agreement {ag_s}/{n_s} ({ag_s / n_s:.1%}; unreadable {unread_s}); L19 {ag_l}/19 "
          f"(unreadable {unread_l}); median |log ratio| S300 {statistics.median(lr):.3f} -> {'PASS' if okb else 'fail'}")
        if basis == "pc":
            for x in rows:
                P("      " + x)
    cap_pick = "pc" if c3["pc"] else ("tick" if c3["tick"] else None)
    P(f"   C3 -> {cap_pick or 'HALT'}  (S300 drew {len(samp['S300'])}: pool had {samp['S300_pool']['below']} below / "
      f"{samp['S300_pool']['above']} at-or-above $500M — 'up to 150' each)")
    dec["cap_basis"] = cap_pick

    # ── input spot-check (not a prereg gate): is Polygon's dated share count point-in-time? ──
    P("\n## INPUT CHECK (added, not a gate) — Polygon's own market_cap on D = dated shares x the RAW close on D?")
    hits = 0
    for x in samp["SPOT"]:
        t, d = x["t"], date.fromisoformat(x["d"])
        rr = (refs.get((t, d)) or {}).get("r") or {}
        sh, mc = L.shares_of(refs.get((t, d))), rr.get("market_cap")
        dl = daily.get(t)
        raw_close = dl["rows"][d]["c"] * L.fac_day(splits, t, d) if dl and d in dl["rows"] else None
        imp = mc / sh if (mc and sh) else None
        ok = imp and raw_close and abs(imp / raw_close - 1) < 0.01
        hits += bool(ok)
        P(f"   {t} {d} (a later {1 / x['fac']:.0f}:1 reverse split): implied px {imp and round(imp, 3)} vs raw close {raw_close and round(raw_close, 3)}"
          f" vs adjusted close {dl['rows'][d]['c'] if dl and d in dl['rows'] else None}{'' if ok else ' (no match)'}")
    P(f"   -> {hits}/{len(samp['SPOT'])} match the RAW close: the dated shares are in D's own (pre-split) units")

    # ── W6 prefilter safety ──
    P("\n## W6 — prefilter safety on F300 + L19")
    vbad = pbad = n = 0
    for r in F300 + L19:
        bars = mins.get((r["t"], r["d"]), [])
        dl = daily.get(r["t"])
        row = dl["rows"].get(r["d"]) if dl else None
        if not bars or not row:
            continue
        n += 1
        dg = S.digest(r["t"], r["d"], bars)
        if dg["vol_0400_0940"] > row["v"]:
            vbad += 1; P(f"   VOLUME: {r['t']} {r['d']} minute 04:00-09:40 {dg['vol_0400_0940']:.0f} > daily {row['v']:.0f}")
        if dg["hi_0400_0955"] is not None and dg["hi_0400_0955"] > row["h"] * 1.000001:
            pbad += 1
    cand = {(c["t"], c["d"]) for c in L.load_cand()}
    lw_pass = {(r["t"], date.fromisoformat(r["d"])) for r in samp["LW"]}
    l19_fail = [f"{r['t']} {r['d']} (in cand: {(r['t'], r['d']) in cand})" for r in L19 if (r["t"], r["d"]) not in lw_pass]
    P(f"   rows checked {n}: minute volume 04:00->09:40 above the day's mi_daily_closes volume on {vbad}; "
      f"minute high 04:00->09:55 above the daily high on {pbad} (binds only if C2 adopted the 09:29 close: {mode_pick})")
    P(f"   live rows failing the prefilter: {len(l19_fail)} {l19_fail}")
    w6_vol_ok = vbad == 0 and not l19_fail
    w6_px_widen = pbad > 0 and mode_pick == "close929"
    P(f"   W6 -> volume half {'SAFE' if w6_vol_ok else 'UNSAFE: drop the volume half, pull the full superset'}; "
      f"price half {'widen' if w6_px_widen else 'safe as written'}")
    dec["w6_volume_safe"] = w6_vol_ok
    dec["w6_price_widen"] = w6_px_widen

    halt = [x for x, ok in (("C1", k_pick is not None), ("C2", mode_pick is not None), ("C3", cap_pick is not None),
                            ("C4", dec["c4_pass"])) if not ok]
    dec["halt_phase1"] = halt
    P(f"\n## PHASE 1 VERDICT: {'HALT on ' + ', '.join(halt) if halt else 'C1-C4 pass'}; W6 volume safe {w6_vol_ok}")

    # live-window survivors needing a reference read
    if not halt:
        day_rows = defaultdict(list)
        cand_by = {(c["t"], c["d"]): c for c in L.load_cand()}
        for x in samp["LW"]:
            key = (x["t"], date.fromisoformat(x["d"]))
            day_rows[key[1]].append(cand_by[key])
        digests = {key: S.digest(key[0], key[1], mins.get(key, [])) for key in cand_by if key in lw_pass}
        res = S.screen(day_rows, digests, daily, splits, None, k=k_pick, mode930=mode_pick, cap_basis=cap_pick, sect=sect)
        need = sorted(res["need_ref"] - set(refs), key=lambda x: (x[1], x[0]))
        open(L.HERE / "list_ref_s1b.txt", "w").write("\n".join(f"{t}|{d}" for t, d in need) + "\n")
        P(f"live-window free-term survivors {len(res['need_ref'])}; still needing a reference read {len(need)} -> list_ref_s1b.txt")
        dec["lw_survivors"] = len(res["need_ref"])
    json.dump(dec, open(L.HERE / "s1_decisions.json", "w"), indent=1)
    log.close()

if PHASE == 2:
    import walk624 as W
    dec = json.load(open(L.HERE / "s1_decisions.json"))
    k, mode, basis = dec["k"], dec["mode930"], dec["cap_basis"]
    cand_by = {(c["t"], c["d"]): c for c in L.load_cand()}
    lw = [(x["t"], date.fromisoformat(x["d"])) for x in samp["LW"]]
    day_rows = defaultdict(list)
    for key in lw:
        day_rows[key[1]].append(cand_by[key])
    digests = {key: S.digest(key[0], key[1], mins.get(key, [])) for key in lw}
    res = S.screen(day_rows, digests, daily, splits, refs, k=k, mode930=mode, cap_basis=basis, sect=sect)
    P(f"\n## A1 — the full screen on the 19 live sessions (k={k}, 09:30 price {mode}, cap basis {basis})")
    P(f"   live-window prefilter rows {len(lw)}; screen counts {dict(res['counts'])}")
    bsig = {(s["t"], s["d"]): s for s in res["signals"]}
    TI = {T: i for i, T in enumerate(L.TICKS)}
    matched, missed = [], []
    for r in L19:
        b = bsig.get((r["t"], r["d"]))
        if b and abs(TI[b["T"]] - TI.get(r["T"], 99)) <= 1:
            matched.append(r)
            P(f"   RE-FOUND {r['t']} {r['d']}: live tick {r['T'].strftime('%H:%M')} / backfill {b['T'].strftime('%H:%M')}")
        else:
            why = res["disp"].get((r["t"], r["d"]), "not in prefilter")
            if b:
                why = f"backfill tick {b['T'].strftime('%H:%M')} vs live {r['T'].strftime('%H:%M')} (more than one tick apart)"
            missed.append((r, why))
            P(f"   MISSED  {r['t']} {r['d']} live tick {r['T'].strftime('%H:%M')}: {why}")
    P(f"   recall {len(matched)}/19 -> {'PASS' if len(matched) >= 16 else 'FAIL: HALT'}")
    # backfill-only signals: explained ONLY from the live records the prereg names
    audit = [line.rstrip("\n").split("\t") for line in open(L.HERE / "s0_audit.tsv")]
    s300cap = {}
    for line in list(open(L.HERE / "s0_s300_pool.tsv"))[1:]:
        p = line.rstrip("\n").split("|")
        s300cap[(p[0], date.fromisoformat(p[1]))] = float(p[2])
    live_keys = {(r["t"], r["d"]) for r in L19}
    unexplained = 0
    P("   backfill-only signals:")
    for s in sorted(res["signals"], key=lambda s: (s["d"], s["t"])):
        if (s["t"], s["d"]) in live_keys:
            continue
        ex = []
        for a in audit:
            if len(a) >= 4 and a[1][:10] == s["d"].isoformat() and a[2] in ("lowcap_lane_cap_unavailable", "lowcap_lane_tick_cap") \
                    and (a[3].startswith(s["t"] + ":") or f" {s['t']}," in a[3] + "," or a[3].endswith(" " + s["t"])):
                ex.append(f"{a[2]} @ {a[1][11:16]}")
        lc = s300cap.get((s["t"], s["d"]))
        if lc is not None and lc >= 5e8:
            ex.append(f"live cap ${lc / 1e6:.0f}M >= $500M (mi_ep_scan_log)")
        if not ex:
            unexplained += 1
        P(f"     {s['t']} {s['d']} @ {s['T'].strftime('%H:%M')} gap {s['gap']:.1f}% pct {s['pct']} polygon cap ${s['cap'] / 1e6:.0f}M "
          f"typed today {s['typed_today']}: {'; '.join(ex) if ex else 'UNEXPLAINED'}"
          + (f" (live cap on file ${lc / 1e6:.0f}M)" if lc is not None and lc < 5e8 else ""))
    P(f"   backfill-only signals {sum(1 for s in res['signals'] if (s['t'], s['d']) not in live_keys)}; unexplained {unexplained} "
      f"-> {'PASS' if unexplained <= 10 else 'FAIL: HALT'}")
    a1_ok = len(matched) >= 16 and unexplained <= 10

    # ── A2 ──
    P("\n## A2 — the primary walker re-prices the live walks (mi_lowcap_lane_replays), each at the live row's own tick, "
      "exit rules, as-of date and last session")
    rep = {(r["ticker"], date.fromisoformat(r["session_date"])): r for r in json.load(open(L.HERE / "s0_lane_replays.json"))}
    st_ag = st_n = px_ag = px_n = r_ag = r_n = 0
    for r in L19:
        lr = rep.get((r["t"], r["d"]))
        if lr is None:
            P(f"   {r['t']} {r['d']}: no live replay row"); continue
        is_matched = r in matched
        bars0 = L.as_dict_bars(r["d"], mins.get((r["t"], r["d"]), []))
        last = date.fromisoformat(lr["settled_session"])
        w = W.walk_primary(r["t"], r["d"], r["T"], bars0, daily.get(r["t"]), rules=lr["replay_exit_rules"],
                           run_date=date.fromisoformat(lr["replay_asof_date"]), last_session=last, data_end=last)
        live_R = lr["realized_r"] if lr["outcome"] == "settled" else lr["mark_r"]
        notes = []
        if is_matched:
            st_n += 1
            same_st = w["entry_status"] == lr["entry_status"]
            st_ag += same_st
            if not same_st:
                notes.append(f"entry status {w['entry_status']} vs live {lr['entry_status']} (ORB {w.get('orb_high')}/{w.get('orb_low')} "
                             f"vs live {lr['orb_high']}/{lr['orb_low']})")
            if w["entry_status"] == "filled" and lr["entry_status"] == "filled":
                px_n += 1
                okp = abs(w["entry_price"] / lr["entry_price"] - 1) <= 0.005
                px_ag += okp
                if not okp:
                    notes.append(f"entry {w['entry_price']} vs live {lr['entry_price']}")
            both_settled = w["outcome"] == lr["outcome"] == "settled"
            both_open = w["outcome"] in ("open", "horizon") and lr["outcome"] in ("open", "horizon")
            if both_settled or both_open:
                r_n += 1
                okr = w["R"] is not None and live_R is not None and abs(w["R"] - live_R) <= 0.05
                r_ag += okr
                if not okr:
                    notes.append(f"R {w['R'] if w['R'] is None else round(w['R'], 3)} vs live {live_R if live_R is None else round(live_R, 3)}")
            elif w["outcome"] != lr["outcome"]:
                notes.append(f"outcome {w['outcome']} vs live {lr['outcome']}")
        P(f"   {'' if is_matched else '(unmatched) '}{r['t']} {r['d']} tick {r['T'].strftime('%H:%M')}: mine {w['entry_status']}/{w['outcome']} "
          f"entry {w.get('entry_price')} R {None if w['R'] is None else round(w['R'], 3)} | live {lr['entry_status']}/{lr['outcome']} "
          f"entry {lr['entry_price']} R {None if live_R is None else round(live_R, 3)} (bars {lr['day0_bars_source']}, last {last})"
          + (" — " + "; ".join(notes) if notes else ""))
    ok_st = st_n and st_ag / st_n >= 0.90
    ok_px = (px_ag / px_n >= 0.90) if px_n else True
    ok_r = (r_ag / r_n >= 0.90) if r_n else True
    P(f"   entry status agree {st_ag}/{st_n}; entry price within 0.5% {px_ag}/{px_n}; R within 0.05R {r_ag}/{r_n} "
      f"-> {'PASS' if (ok_st and ok_px and ok_r) else 'FAIL: HALT'}")
    dec.update(a1_recall=len(matched), a1_unexplained=unexplained, a1_pass=a1_ok,
               a2=[st_ag, st_n, px_ag, px_n, r_ag, r_n], a2_pass=bool(ok_st and ok_px and ok_r))
    json.dump(dec, open(L.HERE / "s1_decisions.json", "w"), indent=1)
    P(f"\n## PHASE 2 VERDICT: A1 {'pass' if a1_ok else 'FAIL'}; A2 {'pass' if dec['a2_pass'] else 'FAIL'}")
    log.close()
