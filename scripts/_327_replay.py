#!/usr/bin/env python3
"""#327 — 9M Day-2 ORB  vs  consolidation-entry  REPLAY  (the #326 directional read).

The #326 question: should we RETIRE the 9M Day-2 ORB entry in favour of a consolidation
(tightness->expansion) entry on the SAME 9M names? Live forward-shadow can't reach
decision-grade N by the ~7/7 call, so this replays BOTH entries over the historical
`mi_9m_day2_candidates` cohort and settles realized R on each through the SAME harvest
(anticipation.SETTLE_RULE) over the SAME forward window — a symmetric head-to-head.

Two arms on every 9M name (full-universe expectancy — a no-fill / never-consolidates name
scores 0R, never silently dropped; advisor 2026-06-18):
  ARM 1  DAY-2 ORB     entry day = alert_date+1; entry = break of the Day-2 opening-range
                       high; STOP = prior day's low (the 9M breakout-day low — the live
                       prepare_9m_day2_orb_order rule, NOT the ORB low). Skip if >15% wide.
  ARM 2  CONSOLIDATION the 9M day is the runup anchor; wait for a coil (tight/quiet base),
                       then take the intraday FIRST5-break on the first expansion day
                       (entry = first-5-min OR high, STOP = first-5-min OR low — tight).

Both harvested identically (anticipation.SETTLE_RULE: +1R/+3R 1/2-1/2, day-5 time stop) over
the same forward window; the realized-R math is anticipation.simulate / simulate_first5 /
build_mixed_path (REUSED — the same faithful day-0-minute scale-out the deployable uses, so
no daily-approximation MFE error). Median + ex-top-N reported (outlier-decomposed — the W2
skip-wide-open lesson). The consolidation UNIVERSE is measured BOTH ways — 9M-anchored AND
runup-canary-gated (>=1.15) — so the detection-criterion fork stays explicit (advisor).

PHASE 1 (daily-only): lifecycle -> each arm's entry day + the Arm-2 funnel + the minute-day
pull list (_327_minute_days.tsv). PHASE 3 (runs once _327_minute.tsv exists): settle both
arms, print the head-to-head. Gate-safe, read-only, runs locally off the pulled TSVs.
"""
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))                      # repo root for `agents.` imports

from agents.market_intelligence import anticipation as de  # noqa: E402  (pure; reused atoms)

COHORT = HERE / "_327_cohort.tsv"     # ticker|alert_date|open|close|high|low|volume|cir|status
DAILY = HERE / "_327_daily.tsv"       # ticker|trade_date|open|high|low|close|volume
MINUTE = HERE / "_327_minute.tsv"     # ticker|t_ms|o|h|l|c|v  (Phase 2 output; RTH+ext)
NEEDED_OUT = HERE / "_327_minute_days.tsv"   # Phase-2 pull list: ticker|date|arm

SETTLE_FWD = de.SETTLE_FORWARD_BARS   # forward trading bars needed to settle (5)
COIL_SCAN = 15                        # trading days after the 9M day to find a coil+breakout
RUNUP_CANARY = de.RUNUP_MIN           # 1.15 — the Family-A runup gate (canary-gated variant)
RTH_OPEN = de._RTH_OPEN               # 9:30 ET in minutes (reuse)


# ── loaders ──────────────────────────────────────────────────────────────────
def _f(x):
    return float(x) if x not in ("", None) else None


def load_cohort() -> list[dict]:
    out = []
    for ln in COHORT.read_text(encoding="utf-8").splitlines():
        p = ln.rstrip("\r").split("|")
        if len(p) < 8 or not p[0]:
            continue
        out.append({"ticker": p[0], "alert_date": p[1], "open": _f(p[2]), "close": _f(p[3]),
                    "high": _f(p[4]), "low": _f(p[5]), "volume": _f(p[6]),
                    "cir": _f(p[7]), "status": p[8] if len(p) > 8 else ""})
    return out


def load_daily() -> dict[str, list[dict]]:
    by = defaultdict(list)
    for ln in DAILY.read_text(encoding="utf-8").splitlines():
        p = ln.rstrip("\r").split("|")
        if len(p) < 7 or not p[0]:
            continue
        by[p[0]].append({"date": p[1], "o": _f(p[2]), "h": _f(p[3]),
                         "l": _f(p[4]), "c": _f(p[5]), "v": _f(p[6]) or 0.0})
    for tk in by:
        by[tk].sort(key=lambda b: b["date"])
    return by


def load_minute() -> dict[tuple, list[dict]]:
    """{(ticker, et_date_iso): [raw {t,o,h,l,c,v}]} grouped per ET trading day. The harness
    converts to RTH bars per entry day via anticipation.polygon_to_rth_minutes (UTC->ET-4)."""
    if not MINUTE.exists():
        return {}
    from datetime import datetime, timedelta, timezone
    raw_by = defaultdict(list)
    for ln in MINUTE.read_text(encoding="utf-8").splitlines():
        p = ln.rstrip("\r").split("\t")
        if len(p) < 7 or p[0].startswith("#"):
            continue
        tk, tms = p[0], int(p[1])
        et = datetime.fromtimestamp(tms / 1000, timezone.utc) - timedelta(hours=4)
        raw_by[(tk, et.date().isoformat())].append(
            {"t": tms, "o": _f(p[2]), "h": _f(p[3]), "l": _f(p[4]), "c": _f(p[5]), "v": _f(p[6])})
    return raw_by


# ── Arm 2: daily consolidation breakout-day detector (the new logic) ──────────
# Family-A entry mode (deferred until now): after the 9M runup anchor, find the first COIL (a
# tight, quiet base day — reuse anticipation.TIGHT_RANGE / VOL_CONTRACT), then the first
# EXPANSION day = first subsequent bar whose close breaks above the base high (max high over
# the coil run) on above-quiet volume. That is where the intraday FIRST5-break fires (Phase 3).
def find_consolidation_breakout(bars: list[dict], anchor_idx: int, scan: int = COIL_SCAN):
    closes = [b["c"] for b in bars]
    vols = [b["v"] for b in bars]
    hi_end = min(anchor_idx + scan, len(bars) - 1)
    coil_start = base_high = None
    for i in range(anchor_idx + 1, hi_end + 1):
        b = bars[i]
        rng = (b["h"] - b["l"]) / b["c"] if b["c"] else 1.0
        adv = de._adv(vols, i)
        is_coil = rng <= de.TIGHT_RANGE and adv and b["v"] <= de.VOL_CONTRACT * adv
        if coil_start is None:
            if is_coil:
                coil_start, base_high = i, b["h"]
            continue
        if is_coil:
            base_high = max(base_high, b["h"])
            continue
        if b["c"] > base_high and b["v"] > adv:          # break above the coil base = expansion
            return {"coil_start_idx": coil_start, "breakout_idx": i, "base_high": base_high}
        base_high = max(base_high, b["h"])               # drift day: fold into the evolving base
    return None


def runup_ratio_at(bars, anchor_idx, window=de.RUNUP_WINDOW):
    closes = [b["c"] for b in bars]
    lo = min(closes[max(0, anchor_idx - window + 1):anchor_idx + 1])
    return (closes[anchor_idx] / lo) if lo else None


def idx_of_date(bars, d):
    for i, b in enumerate(bars):
        if b["date"] == d:
            return i
    return None


def analyze_name(c, daily) -> dict:
    """Per-name lifecycle (no minute bars) — the shared spine for the funnel AND settlement."""
    tk, ad = c["ticker"], c["alert_date"]
    r = {"ticker": tk, "alert_date": ad, "prior_low": c["low"], "anchor_found": False,
         "arm1_day": None, "arm1_idx": None, "arm1_fwd_ok": False,
         "runup": None, "canary": False, "base_high": None,
         "arm2_coil": None, "arm2_breakout": None, "arm2_idx": None, "arm2_fwd_ok": False}
    bars = daily.get(tk)
    if not bars:
        return r
    ai = idx_of_date(bars, ad)
    if ai is None:
        return r
    r["anchor_found"] = True
    last = len(bars) - 1
    if ai + 1 <= last:
        r["arm1_idx"] = ai + 1
        r["arm1_day"] = bars[ai + 1]["date"]
        r["arm1_fwd_ok"] = (last - (ai + 1)) >= SETTLE_FWD
    ru = runup_ratio_at(bars, ai)
    r["runup"] = round(ru, 3) if ru else None
    r["canary"] = bool(ru and ru >= RUNUP_CANARY)
    bo = find_consolidation_breakout(bars, ai)
    if bo:
        bi = bo["breakout_idx"]
        r["arm2_coil"] = bars[bo["coil_start_idx"]]["date"]
        r["arm2_breakout"] = bars[bi]["date"]
        r["arm2_idx"] = bi
        r["base_high"] = bo["base_high"]
        r["arm2_fwd_ok"] = (last - bi) >= SETTLE_FWD
    return r


# ── settlement (Phase 3) ──────────────────────────────────────────────────────
def _daily_forward(bars, entry_idx, n=SETTLE_FWD):
    return bars[entry_idx + 1: entry_idx + 1 + n]


def settle_arm1(minute_rth, prior_low, daily_forward):
    """Day-2 ORB: entry = break of first-5-min OR high, STOP = prior_day_low (NOT OR-low).
    Returns (realized_r, entry, stop) or None (no minute data / no break / invalid / too-wide)."""
    or5 = [b for b in minute_rth if RTH_OPEN <= b["m"] < RTH_OPEN + 5]
    if not or5 or prior_low is None:
        return None
    hi = max(b["h"] for b in or5)
    if prior_low >= hi or (hi - prior_low) / hi > 0.15:           # live invalid / >15% guards
        return None
    for i, b in enumerate(minute_rth):
        if b["m"] < RTH_OPEN + 5:
            continue
        if b["h"] > hi:                                            # stop-buy fills
            path = de.build_mixed_path(minute_rth, i, daily_forward)
            if not path:
                return None
            out = de.simulate(hi, prior_low, path, de.SETTLE_RULE, "pess")
            return (out[0], hi, prior_low) if out else None
    return None                                                    # never triggered = clean miss


def settle_arm2(minute_rth, base_high, daily_forward):
    """Consolidation: intraday FIRST5-break above the coil base; STOP = first-5-min OR low.
    Returns (realized_r, entry, stop) or None."""
    res = de.detect_first5_break(minute_rth, gdl=base_high or 0.0)
    if not res:
        return None
    entry, stop, bi = res
    out = de.simulate_first5(entry, stop, minute_rth, bi, daily_forward, rule=de.SETTLE_RULE)
    return (out["realized_r"], entry, stop) if out else None


# ── aggregation helpers ─────────────────────────────────────────────────────
def _median(xs):
    s = sorted(xs)
    if not s:
        return float("nan")
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def _stats(rs):
    """rs = list of realized R (filled). Returns dict incl ex-top-N decomposition."""
    if not rs:
        return {"n": 0}
    s = sorted(rs, reverse=True)
    tot = sum(s)
    ext = sum(s[3:])               # ex-top-3
    return {"n": len(s), "median": _median(s), "mean": tot / len(s), "total": tot,
            "win%": 100 * sum(1 for r in s if r > 0) / len(s),
            "top3_share%": (100 * (tot - ext) / tot) if tot else float("nan"),
            "ex_top3_mean": (ext / max(len(s) - 3, 1))}


def _fmt(d):
    if d.get("n", 0) == 0:
        return "n=0"
    return (f"n={d['n']}  median {d['median']:+.2f}R  mean {d['mean']:+.2f}R  "
            f"win {d['win%']:.0f}%  total {d['total']:+.1f}R  "
            f"top3 {d['top3_share%']:.0f}%  ex-top3 mean {d['ex_top3_mean']:+.2f}R")


# ── drivers ──────────────────────────────────────────────────────────────────
def phase1(rows):
    n = len(rows)
    anchored = [r for r in rows if r["anchor_found"]]
    a1_settle = [r for r in anchored if r["arm1_fwd_ok"]]
    a2_setup = [r for r in anchored if r["arm2_breakout"]]
    a2_settle = [r for r in a2_setup if r["arm2_fwd_ok"]]
    a2_canary = [r for r in a2_setup if r["canary"]]
    print(f"#327 PHASE 1 — daily lifecycle funnel  (cohort N={n})\n")
    print(f"  anchor (9M day) found              : {len(anchored)}/{n}")
    print(f"  ARM 1  >= {SETTLE_FWD} fwd bars (settleable) : {len(a1_settle)}")
    print(f"  ARM 2  set up (9M-anchored, any runup): {len(a2_setup)}/{len(anchored)}"
          f"  ({len(a2_setup)/max(len(anchored),1)*100:.0f}%)  · settleable {len(a2_settle)}")
    print(f"  ARM 2  set up (canary-gated >=1.15)  : {len(a2_canary)}")
    needed = []
    for r in rows:
        if r["arm1_day"]:
            needed.append((r["ticker"], r["arm1_day"], "day2"))
        if r["arm2_breakout"]:
            needed.append((r["ticker"], r["arm2_breakout"], "consol"))
    NEEDED_OUT.write_text("\n".join(f"{t}|{d}|{a}" for t, d, a in sorted(set(needed))) + "\n",
                          encoding="utf-8")
    print(f"  minute-days to pull (Phase 2)        : {len(set(needed))}  -> {NEEDED_OUT.name}")


def phase3(rows, daily, minute):
    print("\n" + "=" * 78)
    print("#327 PHASE 3 — realized-R head-to-head (anticipation.SETTLE_RULE, pess)\n")
    for r in rows:
        bars = daily.get(r["ticker"])
        # ARM 1
        if r["arm1_idx"] is not None:
            raw = minute.get((r["ticker"], r["arm1_day"]))
            r["arm1_data"] = raw is not None
            if raw:
                rth = de.polygon_to_rth_minutes(raw, r["arm1_day"])
                s = settle_arm1(rth, r["prior_low"], _daily_forward(bars, r["arm1_idx"]))
                r["arm1_r"] = s[0] if s else (0.0 if rth else None)   # had data, no trigger = 0R
            else:
                r["arm1_r"] = None
        # ARM 2 (only names that set up; non-setups = 0R in the full-universe view)
        r["arm2_data"] = None
        if r["arm2_idx"] is not None:
            raw = minute.get((r["ticker"], r["arm2_breakout"]))
            r["arm2_data"] = raw is not None
            if raw:
                rth = de.polygon_to_rth_minutes(raw, r["arm2_breakout"])
                s = settle_arm2(rth, r["base_high"], _daily_forward(bars, r["arm2_idx"]))
                r["arm2_r"] = s[0] if s else (0.0 if rth else None)
            else:
                r["arm2_r"] = None

    # ---- ARM 1 over its settleable universe (no-trigger = 0R; data-missing excluded) ----
    a1 = [r for r in rows if r["arm1_fwd_ok"] and r.get("arm1_r") is not None]
    a1_fills = [r["arm1_r"] for r in a1 if r["arm1_r"] != 0.0]
    a1_missing = sum(1 for r in rows if r["arm1_fwd_ok"] and r.get("arm1_r") is None)
    print(f"ARM 1  Day-2 ORB  (universe {len(a1)} settleable, {a1_missing} minute-data-missing)")
    print(f"  fills (triggered): {len(a1_fills)}/{len(a1)}  ({len(a1_fills)/max(len(a1),1)*100:.0f}%)")
    print(f"  filled-only      : {_fmt(_stats(a1_fills))}")
    print(f"  FULL universe (0R for clean miss): {_fmt(_stats([r['arm1_r'] for r in a1]))}")

    # ---- ARM 2, 9M-anchored: full universe = the SAME settleable names; non-setup = 0R ----
    def arm2_universe(name_filter):
        uni = [r for r in rows if r["arm1_fwd_ok"] and name_filter(r)]
        evaluable, fills, pending, missing = [], [], 0, 0
        for r in uni:
            if r["arm2_idx"] is None:
                evaluable.append(0.0)                       # never consolidated = 0R
            elif not r["arm2_fwd_ok"]:
                pending += 1                                # set up too recently to settle
            elif r.get("arm2_r") is None:
                missing += 1                                # set up + settleable but no minute data
            else:
                evaluable.append(r["arm2_r"])
                if r["arm2_r"] != 0.0:
                    fills.append(r["arm2_r"])
        return uni, evaluable, fills, pending, missing

    for label, nf in (("9M-anchored (all)", lambda r: True),
                      ("canary-gated >=1.15", lambda r: r["canary"])):
        uni, ev, fills, pending, missing = arm2_universe(nf)
        print(f"\nARM 2  consolidation [{label}]  (universe {len(uni)}; "
              f"{pending} pending, {missing} minute-data-missing)")
        print(f"  set-up+filled    : {_fmt(_stats(fills))}")
        print(f"  FULL universe (0R for no-setup/miss): {_fmt(_stats(ev))}")

    # ---- PAIRED head-to-head: names where BOTH arms are evaluable ----
    paired = []
    for r in rows:
        if not r["arm1_fwd_ok"] or r.get("arm1_r") is None:
            continue
        a2 = 0.0 if r["arm2_idx"] is None else (r.get("arm2_r") if r["arm2_fwd_ok"] else None)
        if a2 is None:
            continue                                        # arm2 pending/missing -> not comparable
        paired.append((r["ticker"], r["arm1_r"], a2))
    if paired:
        d1 = _stats([p[1] for p in paired])
        d2 = _stats([p[2] for p in paired])
        a1w = sum(1 for _, x, y in paired if x > y)
        a2w = sum(1 for _, x, y in paired if y > x)
        tie = sum(1 for _, x, y in paired if x == y)
        print(f"\nPAIRED head-to-head  (N={len(paired)} names both arms evaluable)")
        print(f"  ARM 1 Day-2 ORB     : {_fmt(d1)}")
        print(f"  ARM 2 consolidation : {_fmt(d2)}")
        print(f"  per-name wins        : Day-2 {a1w}  ·  consolidation {a2w}  ·  tie {tie}")
        print(f"  delta (consol-Day2) median {d2['median']-d1['median']:+.2f}R  "
              f"mean {d2['mean']-d1['mean']:+.2f}R")

    # ---- WITHIN-NAME (advisor): on the SAME names where consolidation FIRED, what did
    # Day-2 ORB return? Collapses the different-subset confound — the apples-to-apples delta. ----
    wn = []
    for r in rows:
        a2 = r.get("arm2_r")
        if r["arm2_idx"] is None or not r["arm2_fwd_ok"] or a2 in (None, 0.0):
            continue                                        # only names consolidation actually fired on
        a1 = r.get("arm1_r")
        if a1 is None:
            continue                                        # Day-2 minute data missing -> not comparable
        wn.append((r["ticker"], a1, a2))                    # a1=0.0 = Day-2 didn't trigger (legit outcome)
    if wn:
        d1 = _stats([x[1] for x in wn])
        d2 = _stats([x[2] for x in wn])
        w1 = sum(1 for _, x, y in wn if x > y)
        w2 = sum(1 for _, x, y in wn if y > x)
        nofire1 = sum(1 for _, x, _ in wn if x == 0.0)
        print(f"\nWITHIN-NAME head-to-head  (N={len(wn)} names where CONSOLIDATION fired)")
        print(f"  ARM 1 Day-2 ORB on these : {_fmt(d1)}   ({nofire1} of {len(wn)} no Day-2 trigger=0R)")
        print(f"  ARM 2 consolidation       : {_fmt(d2)}")
        print(f"  per-name wins             : Day-2 {w1}  ·  consolidation {w2}")
        print(f"  within-name delta (consol-Day2) median {d2['median']-d1['median']:+.2f}R  "
              f"mean {d2['mean']-d1['mean']:+.2f}R")

    print("\n(MFE-free: realized R via the day-0 minute scale-out + daily trail to the day-5 "
          "time stop, both arms identical. N small -> DIRECTIONAL; read median + ex-top3. "
          "Arm-2 magnitude is UPWARD-biased: breakout days are daily-close-confirmed, so weak-"
          "close failed breakouts a live watcher would take are excluded — Phase B measures it.)")


def main():
    cohort = load_cohort()
    daily = load_daily()
    rows = [analyze_name(c, daily) for c in cohort]
    phase1(rows)
    minute = load_minute()
    if minute:
        phase3(rows, daily, minute)
    else:
        print(f"\n(Phase 3 waits on {MINUTE.name} — run scripts/_327_pull_minute.py)")


if __name__ == "__main__":
    main()
