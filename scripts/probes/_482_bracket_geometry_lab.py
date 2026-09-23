#!/usr/bin/env python3
"""#482 — bracket-geometry lab FIRST READ (READ-ONLY; STUDY ONLY; THE LINE holds).

Operator ruling 7/18: KEEP the live 1-min ORB bracket, SHADOW alternatives, decide from
evidence. This probe is the first backtest read: it reconstructs realized-R for four
bracket-geometry variants against the live 1-min-ORB baseline over the ALREADY-PULLED
#468 TSVs (no prod access, no re-pull, no live code change).

Variants (HIGH cohort, identical alert universe + eligibility as #468 primary):
  BASE      live 1-min ORB bracket (entry stop-limit @ ORB-high, stop @ ORB-low)
            — reconstruct2() mirrors _468_moderate_realized_r.reconstruct and is
            PARITY-ASSERTED against it row-by-row (anti-drift).
  V-5M      5-min ORB bar: hi/lo over 9:30-9:34 bars, arm at 9:35, same limit buffer,
            same 1.5x-ATR width gate, same 10:00 fill cutoff (mirrors
            broker/shadow_orb_tracker.py geometry, #94 lane).
  V-ATR(k)  same fills as BASE, stop re-based to entry - k*ATR14 (pure/wider form) and
            max(ORB-low, entry - k*ATR14) (the capped/tighter-of form). Isolates the
            STOP lever from the entry lever.
  V-STRUCT  same fills as BASE, stop = prior day's low (the 9M-style structure stop).
  V-REENTRY day-0-limited v0: after a FULL day-0 stop, re-enter on a same-day re-break
            of the 1-min ORB-high (stop = pullback low between stop-out and re-break),
            up to 2 re-entries, fills allowed until 15:30 ET. Day-1+ stops NOT chained
            (needs the fuller minute pull — see the doc).
  V-ESTLOW  day-0-limited v0: wait for an ESTABLISHED intraday low (a running low that
            holds >= 15 minutes un-undercut), then enter on the first bar at/above the
            1-min ORB-high (market at open if already above), stop = the established
            low, fills until 15:30 ET. Day-0 only (day-1 reclaims need the fuller pull).

Exit frame for every arm: anticipation.SETTLE_RULE (+1R/+3R halves, day-5 time stop),
'pess' intrabar bound, over build_mixed_path (day-0 minute + daily forward) — the #327
primitives, REUSED not reinvented. Identical rule across arms = the comparison is pure
geometry.

Findings doc: docs/analysis/482_bracket_geometry_lab_2026-07-18.md
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))

import _468_moderate_realized_r as p                       # noqa: E402 (reused verbatim)
from agents.market_intelligence import anticipation as de  # noqa: E402

RTH_OPEN = p.RTH_OPEN            # 570 = 9:30
ORB5_END = RTH_OPEN + 5          # 575 = 9:35 — 5-min ORB completes
FILL_END = p.FILL_END            # 600 = 10:00 — live unfilled-cancel
LATE_CUTOFF = 15 * 60 + 30       # 930 = 15:30 ET — re-entry / est-low fill cutoff
ESTLOW_HOLD_MIN = 15             # minutes a low must hold un-undercut to be "established"
MAX_ATTEMPTS = 3                 # 1 original + up to 2 re-entries
ATR_KS = (0.5, 1.0, 1.5, 2.0)


# ── shared fill engine (mirrors p.reconstruct's stop-limit loop exactly) ─────

def fill_scan(rth, scan_from_m, trigger, limit, fill_end_m, start_idx=0):
    """(fill_px, fill_idx) or (None, None). Stop-limit buy: crossed-in-bar → trigger px;
    opened between trigger and limit → open; gapped past limit → arm and wait for a
    pullback into the limit (the armed_passthrough branch of p.reconstruct)."""
    armed = False
    for i, b in enumerate(rth):
        if i < start_idx or b["m"] < scan_from_m:
            continue
        if b["m"] >= fill_end_m:
            break
        if armed:
            if b["l"] <= limit:
                return limit, i
            continue
        if b["h"] >= trigger:
            if b["o"] <= trigger:
                return trigger, i
            if b["o"] <= limit:
                return b["o"], i
            armed = True
    return None, None


def settle(entry, stop, rth, fill_idx, daily_fwd):
    """SETTLE_RULE/pess harvest from fill_idx. {r, fills, stop_day} or None."""
    if entry - stop <= 0:
        return None
    path = de.build_mixed_path(rth, fill_idx, daily_fwd)
    if not path:
        return None
    out = de.simulate(entry, stop, path, de.SETTLE_RULE, "pess")
    if out is None:
        return None
    r, _cap, fills = out
    return {"r": r, "fills": fills, "stop_day": fills[-1][0] if fills else None}


# ── variant reconstructions ──────────────────────────────────────────────────

def reconstruct2(rth, sub_m, atr14, daily_fwd):
    """BASE — p.reconstruct mirror that ALSO returns fill_idx + fills (needed by the
    re-entry chain). Parity with p.reconstruct asserted by the caller."""
    orb_cand = [b for b in rth if RTH_OPEN <= b["m"] < p.ORB_FETCH_END]
    if not orb_cand:
        return {"outcome": "no_orb_bar"}
    orb = orb_cand[0]
    hi, lo = orb["h"], orb["l"]
    ok, reason = p.validate_orb_entry(hi, lo, atr14)
    if not ok:
        return {"outcome": reason.split(":")[1]}
    limit = p.stop_limit_buy_price(hi)
    fill_px, fill_idx = fill_scan(rth, max(sub_m, orb["m"] + 1), hi, limit, FILL_END)
    if fill_px is None:
        return {"outcome": "no_fill", "orb_high": hi, "orb_low": lo}
    s = settle(fill_px, lo, rth, fill_idx, daily_fwd)
    if s is None:
        return {"outcome": "invalid_risk", "orb_high": hi, "orb_low": lo}
    return {"outcome": "filled", "entry": fill_px, "stop": lo, "orb_high": hi,
            "orb_low": lo, "fill_idx": fill_idx, "fill_minute": rth[fill_idx]["m"], **s}


def reconstruct_5m(rth, sub_m, atr14, daily_fwd):
    """V-5M — ORB hi/lo over ALL 9:30-9:34 bars (shadow_orb_tracker geometry), armed
    from 9:35, same width gate + limit buffer + 10:00 cutoff."""
    orb_bars = [b for b in rth if RTH_OPEN <= b["m"] < ORB5_END]
    if not orb_bars:
        return {"outcome": "no_orb_bar"}
    hi = max(b["h"] for b in orb_bars)
    lo = min(b["l"] for b in orb_bars)
    ok, reason = p.validate_orb_entry(hi, lo, atr14)
    if not ok:
        return {"outcome": reason.split(":")[1]}
    limit = p.stop_limit_buy_price(hi)
    fill_px, fill_idx = fill_scan(rth, max(sub_m, ORB5_END), hi, limit, FILL_END)
    if fill_px is None:
        return {"outcome": "no_fill", "orb_high": hi, "orb_low": lo}
    s = settle(fill_px, lo, rth, fill_idx, daily_fwd)
    if s is None:
        return {"outcome": "invalid_risk", "orb_high": hi, "orb_low": lo}
    return {"outcome": "filled", "entry": fill_px, "stop": lo, "orb_high": hi,
            "orb_low": lo, "fill_idx": fill_idx, "fill_minute": rth[fill_idx]["m"], **s}


def is_full_day0_stop(rec):
    f = rec.get("fills")
    return (rec.get("outcome") == "filled" and f and len(f) == 1
            and f[0][0] == 0 and abs(f[0][1] - 1.0) < 1e-9 and rec["r"] < 0)


def reentry_chain(rth, base, daily_fwd):
    """V-REENTRY v0 — list of per-attempt R (attempt 1 = BASE). Chains only after a
    FULL day-0 stop; re-break of the ORIGINAL 1-min ORB-high; stop = pullback low
    between the stop-out bar and the re-break bar; fills until 15:30. Equal $-risk per
    attempt assumed (sum of R = the chain's R)."""
    attempts = [base["r"]]
    cur = base
    while len(attempts) < MAX_ATTEMPTS and is_full_day0_stop(cur):
        stop_idx = next((i for i in range(cur["fill_idx"] + 1, len(rth))
                         if rth[i]["l"] <= cur["stop"]), None)
        if stop_idx is None:
            break
        trigger = base["orb_high"]
        limit = p.stop_limit_buy_price(trigger)
        fill_px, fill_idx = fill_scan(rth, rth[stop_idx]["m"] + 1, trigger, limit,
                                      LATE_CUTOFF, start_idx=stop_idx + 1)
        if fill_px is None:
            break
        pullback_low = min(b["l"] for b in rth[stop_idx:fill_idx])
        s = settle(fill_px, pullback_low, rth, fill_idx, daily_fwd)
        if s is None:
            break
        cur = {"outcome": "filled", "entry": fill_px, "stop": pullback_low,
               "orb_high": trigger, "fill_idx": fill_idx, **s}
        attempts.append(s["r"])
    return attempts


def reconstruct_estlow(rth, sub_m, daily_fwd):
    """V-ESTLOW v0 — running intraday low; established when un-undercut for
    ESTLOW_HOLD_MIN minutes; then first bar at/above the 1-min ORB-high fills (open if
    already above, else the trigger px), stop = the established low, until 15:30.
    Pess ordering: a bar that undercuts the low resets state and cannot also fill."""
    orb_cand = [b for b in rth if RTH_OPEN <= b["m"] < p.ORB_FETCH_END]
    if not orb_cand:
        return {"outcome": "no_orb_bar"}
    trigger = orb_cand[0]["h"]
    lo_v = lo_m = None
    established = False
    for i, b in enumerate(rth):
        if b["m"] >= LATE_CUTOFF:
            break
        if lo_v is None or b["l"] < lo_v:
            lo_v, lo_m, established = b["l"], b["m"], False
            continue
        if not established and b["m"] > lo_m + ESTLOW_HOLD_MIN:
            established = True
        if established and b["m"] >= sub_m and b["h"] >= trigger:
            fill_px = b["o"] if b["o"] >= trigger else trigger
            s = settle(fill_px, lo_v, rth, i, daily_fwd)
            if s is None:
                return {"outcome": "invalid_risk"}
            return {"outcome": "filled", "entry": fill_px, "stop": lo_v,
                    "fill_idx": i, "fill_minute": b["m"], **s}
    return {"outcome": "no_fill"}


# ── report helpers ───────────────────────────────────────────────────────────

def block(label, recs, keys_note=""):
    fills = [x for x in recs if x["outcome"] == "filled"]
    evaluable = fills + [x for x in recs if x["outcome"] == "no_fill"]
    funnel = defaultdict(int)
    for x in recs:
        funnel[x["outcome"]] += 1
    print(f"── {label} ──{keys_note}")
    print("  funnel: " + "  ".join(f"{k}={v}" for k, v in sorted(funnel.items())))
    if evaluable:
        print(f"  fill rate: {len(fills)}/{len(evaluable)} "
              f"({100 * len(fills) / len(evaluable):.0f}%)")
    print(f"  filled-only   : {p._fmt(p._stats([x['r'] for x in fills]))}")
    if evaluable:
        fu = [x["r"] if x["outcome"] == "filled" else 0.0 for x in evaluable]
        print(f"  full universe : n={len(fu)} mean {sum(fu)/len(fu):+.2f}R (no-fill = 0R)")
    for per in ("clean", "polluted"):
        sub = [x["r"] for x in fills if x.get("period") == per]
        if sub:
            print(f"    {per:<9}filled: {p._fmt(p._stats(sub))}")
    if fills:
        d0 = [x for x in fills if x.get("stop_day") == 0]
        d0n = [x for x in d0 if x["r"] < 0]
        spct = [100 * (x["entry"] - x["stop"]) / x["entry"] for x in fills
                if x.get("entry") and x.get("stop")]
        print(f"  day-0 full exits: {len(d0)}/{len(fills)} (negative {len(d0n)}) · "
              f"stop distance median {p._median(spct):.1f}% of entry")
    print()
    return fills


def paired_delta(label, fills_v, base_by_key):
    pairs = [(x["r"], base_by_key[x["key"]]["r"]) for x in fills_v
             if x["key"] in base_by_key]
    if not pairs:
        print(f"  {label}: no paired keys\n")
        return
    d = [a - b for a, b in pairs]
    print(f"  paired vs BASE (n={len(d)} common fills): "
          f"delta median {p._median(d):+.2f}R mean {sum(d)/len(d):+.2f}R "
          f"(+ = variant better)\n")


MINUTE_FWD = HERE / "_482_minute_fwd.tsv"   # ticker \t t_ms \t o h l c v (day0..day0+9cal)


def pull_minute_fwd() -> None:
    """Fuller minute pull: day-0 THROUGH day+9 CALENDAR days (covers the 5 forward
    trading bars + pad) per (ticker, alert_date) pair — unlocks re-entry chains after
    day-1+ stops, est-low day-1 reclaims, and minute-fidelity day-1..5 exits for every
    variant. ~245 Polygon range calls via the in-container read path (the #468
    _ssh_polygon shape). WRITTEN for the orchestrator to run — NOT run by the #482
    first-read session (operator-directed measure-before-wire)."""
    from datetime import datetime as _dt, timedelta as _td
    rows = p.load_cohort()
    if not rows:
        sys.exit(f"run _468 --pull-cohort first ({p.COHORT.name} missing/empty)")
    pairs = sorted({(r["ticker"], r["alert_date"]) for r in rows})
    print(f"pulling minute day-0..+9cal for {len(pairs)} (ticker,date) pairs …")
    pairs_lit = "[" + ",".join(
        f'("{t}","{d}","{(_dt.fromisoformat(d) + _td(days=9)).date().isoformat()}")'
        for t, d in pairs) + "]"
    minute_code = (
        "import json,os,sys,time,urllib.request\n"
        "KEY=os.environ[\"POLYGON_API_KEY\"]\n"
        f"PAIRS={pairs_lit}\n"
        "for t,d,e in PAIRS:\n"
        "    url=f\"https://api.polygon.io/v2/aggs/ticker/{t}/range/1/minute/{d}/{e}?adjusted=true&sort=asc&limit=50000&apiKey={KEY}\"\n"
        "    try:\n"
        "        rr=json.load(urllib.request.urlopen(url,timeout=25))\n"
        "        for bar in rr.get(\"results\",[]):\n"
        "            tt=bar[\"t\"];o=bar[\"o\"];h=bar[\"h\"];lo=bar[\"l\"];c=bar[\"c\"];v=bar[\"v\"]\n"
        "            print(f\"{t}\\t{tt}\\t{o}\\t{h}\\t{lo}\\t{c}\\t{v}\")\n"
        "    except Exception as e2:\n"
        "        print(f\"# ERR {t} {d}: {e2}\",file=sys.stderr)\n"
        "    time.sleep(0.12)\n"
    )
    p._ssh_polygon(minute_code, MINUTE_FWD, timeout=1800)


def main() -> None:
    if "--pull-minute-fwd" in sys.argv:
        pull_minute_fwd()
        return
    cohort = p.load_cohort()
    daily = p.load_daily()
    minute = p.load_minute()
    if not cohort or not daily or not minute:
        sys.exit("missing #468 TSVs — they are the required input (do NOT re-pull)")

    highs = [r for r in cohort if r["tier"] == "HIGH"]
    print("#482 — bracket-geometry lab FIRST READ (HIGH cohort, SETTLE_RULE/pess, "
          "same #468 machinery)\n")

    # assemble the evaluable per-alert context ONCE (same gates as #468 primary)
    ctx = []
    gate_funnel = defaultdict(int)
    parity_fail = 0
    for r in highs:
        gate_funnel["alerts"] += 1
        gate, sub_m = p.eligibility(r)
        if gate != "ok":
            gate_funnel[gate] += 1
            continue
        bars = daily.get(r["ticker"])
        ai = p.idx_of_date(bars, r["alert_date"]) if bars else None
        if ai is None:
            gate_funnel["no_daily_bars"] += 1
            continue
        if len(bars) - 1 - ai < p.SETTLE_FWD:
            gate_funnel["not_settleable"] += 1
            continue
        raw = minute.get((r["ticker"], r["alert_date"]))
        if not raw:
            gate_funnel["no_minute_data"] += 1
            continue
        rth = de.polygon_to_rth_minutes(raw, r["alert_date"])
        atr = p.atr14_prior_close(bars, ai)
        c = {"key": (r["ticker"], r["alert_date"]), "rth": rth, "sub_m": sub_m,
             "atr": atr, "daily_fwd": bars[ai + 1: ai + 1 + p.SETTLE_FWD],
             "prior_day_low": bars[ai - 1]["l"] if ai >= 1 else None,
             "period": p.period_of(r["alert_date"])}
        # parity: reconstruct2 must equal p.reconstruct on outcome + r
        ref = p.reconstruct(rth, sub_m, atr, c["daily_fwd"])
        mine = reconstruct2(rth, sub_m, atr, c["daily_fwd"])
        if (ref["outcome"] != mine["outcome"]
                or abs(ref.get("r", 0.0) - mine.get("r", 0.0)) > 1e-9):
            parity_fail += 1
        c["base"] = mine
        ctx.append(c)
    print("eligibility funnel: " + "  ".join(f"{k}={v}" for k, v in sorted(gate_funnel.items()))
          + f"  → evaluable {len(ctx)}")
    print(f"parity check reconstruct2 vs #468 reconstruct: "
          f"{'OK — 0 mismatches' if parity_fail == 0 else f'{parity_fail} MISMATCHES'}\n")

    def tag(rec, c):
        rec["key"], rec["period"] = c["key"], c["period"]
        return rec

    # ── BASE ──
    base_recs = [tag(dict(c["base"]), c) for c in ctx]
    base_fills = block("BASE — live 1-min ORB bracket (the #468 reconstruction)", base_recs)
    base_by_key = {x["key"]: x for x in base_fills}

    # ── V-5M ──
    v5_recs = [tag(reconstruct_5m(c["rth"], c["sub_m"], c["atr"], c["daily_fwd"]), c)
               for c in ctx]
    v5_fills = block("V-5M — 5-min ORB bar (shadow_orb_tracker geometry)", v5_recs)
    paired_delta("V-5M", v5_fills, base_by_key)

    # ── V-ATR grid (same fills as BASE, stop re-based; needs known ATR) ──
    for k in ATR_KS:
        for form, name in (("pure", f"V-ATR {k}x pure (stop = entry - {k}*ATR14)"),
                           ("cap", f"V-ATR {k}x capped (stop = max(ORB-low, entry - {k}*ATR14))")):
            recs = []
            for c in ctx:
                b = c["base"]
                if b["outcome"] != "filled":
                    recs.append(tag({"outcome": b["outcome"]}, c))
                    continue
                if c["atr"] is None:
                    recs.append(tag({"outcome": "no_atr"}, c))
                    continue
                stop_v = b["entry"] - k * c["atr"]
                if form == "cap":
                    stop_v = max(b["orb_low"], stop_v)
                s = settle(b["entry"], stop_v, c["rth"], b["fill_idx"], c["daily_fwd"])
                if s is None:
                    recs.append(tag({"outcome": "invalid_risk"}, c))
                    continue
                recs.append(tag({"outcome": "filled", "entry": b["entry"],
                                 "stop": stop_v, **s}, c))
            fills = block(name, recs)
            paired_delta(name, fills, base_by_key)

    # ── V-STRUCT (same fills as BASE, stop = prior day's low) ──
    recs = []
    for c in ctx:
        b = c["base"]
        if b["outcome"] != "filled":
            recs.append(tag({"outcome": b["outcome"]}, c))
            continue
        pdl = c["prior_day_low"]
        if pdl is None or pdl >= b["entry"]:
            recs.append(tag({"outcome": "invalid_risk"}, c))
            continue
        s = settle(b["entry"], pdl, c["rth"], b["fill_idx"], c["daily_fwd"])
        recs.append(tag({"outcome": "filled", "entry": b["entry"], "stop": pdl, **s}
                        if s else {"outcome": "invalid_risk"}, c))
    fills = block("V-STRUCT — stop = prior day's low (9M-style structure stop)", recs)
    paired_delta("V-STRUCT", fills, base_by_key)

    # ── V-REENTRY (day-0-limited v0 on BASE geometry) ──
    recs, n_chained, extra_r, att_hist = [], 0, 0.0, defaultdict(int)
    for c in ctx:
        b = c["base"]
        if b["outcome"] != "filled":
            recs.append(tag({"outcome": b["outcome"]}, c))
            continue
        attempts = reentry_chain(c["rth"], b, c["daily_fwd"])
        att_hist[len(attempts)] += 1
        if len(attempts) > 1:
            n_chained += 1
            extra_r += sum(attempts[1:])
        recs.append(tag({"outcome": "filled", "r": sum(attempts),
                         "entry": b["entry"], "stop": b["stop"],
                         "stop_day": b["stop_day"] if len(attempts) == 1 else None}, c))
    fills = block("V-REENTRY — BASE + same-day re-break re-entry (max 2 re-entries, "
                  "day-0 stops only)", recs)
    print(f"  chains: {n_chained} names re-entered · attempt histogram "
          f"{dict(sorted(att_hist.items()))} · re-entry attempts net {extra_r:+.1f}R\n")
    paired_delta("V-REENTRY", fills, base_by_key)

    # ── V-ESTLOW (day-0-limited v0) ──
    recs = [tag(reconstruct_estlow(c["rth"], c["sub_m"], c["daily_fwd"]), c) for c in ctx]
    fills = block(f"V-ESTLOW — wait-for-established-low (hold {ESTLOW_HOLD_MIN} min, "
                  f"reclaim 1-min ORB-high, stop = established low)", recs)
    paired_delta("V-ESTLOW", fills, base_by_key)
    fm = [x["fill_minute"] for x in fills if x.get("fill_minute") is not None]
    if fm:
        print(f"  est-low fill minute: median {p._median(fm):.0f} "
              f"({int(p._median(fm)) // 60}:{int(p._median(fm)) % 60:02d} ET)\n")

    print("(READ-ONLY study over the #468 TSVs — day-0-minute-limited; re-entry after "
          "day-1+ stops and day-1+ est-low reclaims need the fuller minute pull. "
          "THE LINE holds: no live entry/stop change.)")


if __name__ == "__main__":
    main()
