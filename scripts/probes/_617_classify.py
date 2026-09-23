#!/usr/bin/env python3
"""#617 STEP 1 — classify the Jun-Aug 2026 gapper population by the UNIVERSE filter that kept it
out of the funnel, from the read-only capture `_617_population_out.txt` (see `_617_population.sql`).

$0, offline. Mirrors the live universe loop's ORDER (ep_detector.run_ep_scan, lines ~3074-3150):
  ticker shape -> security type (P2.0b) -> MIN_PREV_CLOSE -> MIN_PREV_DAY_VOLUME -> gap floor.
Everything after the gap floor (rvol gate, shortlist cap, extension, quality filters, grading,
score bar, post-grade filters) leaves a scan_log row and was measured by #545 Phase 2 — NOT
re-reviewed here (the operator's wasted-resources warning, 2026-09-03).

Gap basis: the capture's gap is SESSION OPEN vs strictly-prior close (mi_daily_closes). The live
scan decides on a 09:30-09:45 price (delayed Polygon before 08-27, real-time SIP after), so a row
in mi_ep_scan_log is the ground truth for "entered the funnel"; the open-gap band is the proxy for
WHY a row-less name never entered.

Floor as-of: MIN_GAP_PCT was 10.0 from 2026-05-17, 9.0 from 2026-08-19 (docs/setups/magna53_ep.md).

Usage: python scripts/probes/_617_classify.py  [--write-sets]   (writes _617_replay_sets.tsv)
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO))
from scripts.ep_replay import read_sections  # noqa: E402

CAP = HERE / "_617_population_out.txt"
FLOOR_CHANGE = date(2026, 8, 19)
STOCK_TYPES = {"CS", "ADRC"}                 # db.COMMON_STOCK_TYPES
MIN_PREV_CLOSE, MIN_PREV_DAY_VOLUME = 5.0, 50_000
MAX_TICKER_LEN = 5


def _f(v):
    try:
        return float(v) if v not in ("", None) else None
    except ValueError:
        return None


def floor_as_of(d: date) -> float:
    return 9.0 if d >= FLOOR_CHANGE else 10.0


def band(g: float | None) -> str:
    if g is None:
        return "?"
    for lo, hi in ((5, 6), (6, 7), (7, 8), (8, 9), (9, 10), (10, 12), (12, 15), (15, 20)):
        if lo <= g < hi:
            return f"[{lo},{hi})"
    return ">=20" if g >= 20 else "<5"


def stage_of(scan_row: dict) -> str:
    """The funnel stage a scan_log row records — #605 reject_stage when present, else the
    filter_reason string family (pre-08-29 rows carry the stage only in the string)."""
    st = scan_row.get("reject_stage") or ""
    if st:
        return st
    r = scan_row.get("filter_reason") or ""
    if not r:
        return "scored"
    for key, tag in (("universe_below_gap_floor", "gap_floor"), ("universe_prev_close", "universe_floor"),
                     ("universe_prev_day", "universe_floor"), ("outside top-", "shortlist_cap"),
                     ("already up", "extension"), ("pre-mkt volume", "post_grade_filter"),
                     ("routine catalyst", "post_grade_filter"), ("score ", "score_bar"),
                     ("cooldown", "cooldown"), ("already scored", "duplicate"),
                     ("RVOL", "rvol_gate"), ("rvol", "rvol_gate"), ("ADV", "quality_filter"),
                     ("ATR", "quality_filter"), ("market cap", "quality_filter"),
                     ("Market cap", "quality_filter"), ("M&A", "post_grade_filter"),
                     ("acqui", "post_grade_filter")):
        if key in r:
            return tag
    return "other:" + r[:30]


def main() -> None:
    S = read_sections(CAP)
    pop, scan, alerts, trades, sect = S["POP"], S["SCAN"], S["ALERTS"], S["TRADES"], S["SECTYPES"]
    scandays = {r["scan_date"] for r in S["SCANDAYS"]}
    barscov = {(r["ticker"], r["trade_date"]): (int(r["rth_bars"]), r["has_930"] == "t")
               for r in S["BARSCOV"]}
    sectype = {r["ticker"]: r["security_type"] for r in sect}
    scan_by = defaultdict(list)
    for r in scan:
        scan_by[(r["ticker"], r["scan_date"])].append(r)
    alert_by = {(r["ticker"], r["alert_date"]) for r in alerts}
    trade_by = {(r["ticker"], r["alert_date"]) for r in trades}
    print(f"capture: POP {len(pop)} rows, SCAN {len(scan)}, ALERTS {len(alerts)}, TRADES {len(trades)}, "
          f"SECTYPES {len(sect)}, scan days {len(scandays)}, pop pairs with stored RTH bars {len(barscov)}")

    rows = []
    for r in pop:
        t, d = r["ticker"], r["trade_date"]
        dd = date.fromisoformat(d)
        og, hg = _f(r["open_gap_pct"]), _f(r["high_gap_pct"])
        pc, pv = _f(r["prev_close"]), _f(r["prev_volume"])
        srows = scan_by.get((t, d), [])
        stages = sorted({stage_of(x) for x in srows})
        # the DEEPEST stage a row reached (scored/alert beats a gap_floor row for the same day)
        deepest = ("alert" if (t, d) in alert_by else
                   "scored" if any(s == "scored" for s in stages) else
                   ",".join(s for s in stages if s not in ("gap_floor", "universe_floor")) or
                   ",".join(stages) or "no_row")
        # universe filter, in LIVE ORDER, judged on the D-1 inputs the loop reads
        if len(t) > MAX_TICKER_LEN or "." in t:
            uf = "ticker_shape"
        elif t not in sectype:
            uf = "unclassified_security_type"
        elif sectype[t] not in STOCK_TYPES:
            uf = "non_stock:" + sectype[t]
        elif pc is None or pc < MIN_PREV_CLOSE:
            uf = "MIN_PREV_CLOSE"
        elif pv is None or pv < MIN_PREV_DAY_VOLUME:
            uf = "MIN_PREV_DAY_VOLUME"
        elif og is not None and og < floor_as_of(dd):
            uf = "MIN_GAP_PCT_asof" if og < 9.0 else "MIN_GAP_PCT_10_then_9_now"
        else:
            uf = "passes_universe"
        rows.append({**r, "og": og, "hg": hg, "pc": pc, "pv": pv, "dd": dd, "uf": uf,
                     "deepest": deepest, "n_scan": len(srows), "scan_day": d in scandays,
                     "bars": barscov.get((t, d), (0, False))})

    # ── 1. universe-filter census over the whole population ─────────────────────────
    print("\n== 1. population by universe filter (live order) x deepest funnel stage reached ==")
    tab = Counter((x["uf"], x["deepest"]) for x in rows)
    ufs = Counter(x["uf"] for x in rows)
    for uf, n in ufs.most_common():
        deep = Counter(x["deepest"] for x in rows if x["uf"] == uf)
        print(f"  {uf:34s} n={n:6d}  " + "  ".join(f"{k}:{v}" for k, v in deep.most_common(6)))

    # ── 2. the gap-floor band read, floors passed (the MIN_GAP_PCT exclusion set) ────
    print("\n== 2. names passing every non-gap universe floor, by OPEN-gap band x funnel outcome ==")
    ok = [x for x in rows if x["uf"] in ("MIN_GAP_PCT_asof", "MIN_GAP_PCT_10_then_9_now", "passes_universe")]
    for b in ("[5,6)", "[6,7)", "[7,8)", "[8,9)", "[9,10)", "[10,12)", "[12,15)", "[15,20)", ">=20", "<5"):
        sub = [x for x in ok if band(x["og"]) == b]
        if not sub:
            continue
        deep = Counter(x["deepest"] for x in sub)
        stored = sum(1 for x in sub if x["bars"][0] >= 350 and x["bars"][1])
        print(f"  open gap {b:8s} n={len(sub):5d}  no_row={deep['no_row']:5d}  gap_floor_row="
              f"{deep['gap_floor']:4d}  scored={deep['scored']:4d}  alert={deep['alert']:3d}  "
              f"other={len(sub)-deep['no_row']-deep['gap_floor']-deep['scored']-deep['alert']:4d}  "
              f"full_day0_bars_stored={stored}")

    # ── 3. per-month view of the never-admitted [5,9) band + the 9-10 band ─────────
    print("\n== 3. never-admitted (no row / gap_floor row only), floors passed, by month x band ==")
    never = [x for x in ok if x["deepest"] in ("no_row", "gap_floor")]
    bym = Counter((x["dd"].strftime("%Y-%m"), band(x["og"])) for x in never)
    for m in ("2026-06", "2026-07", "2026-08"):
        print(f"  {m}: " + "  ".join(f"{b}:{bym[(m, b)]}" for b in
                                     ("[5,6)", "[6,7)", "[7,8)", "[8,9)", "[9,10)", "[10,12)", "[12,15)", "[15,20)", ">=20")))

    # ── 4. the silent set: floors passed, open gap >= as-of floor, NO scan row at all ──
    print("\n== 4. SILENT: open gap >= the as-of floor, every universe floor passed, no scan_log row ==")
    silent = [x for x in ok if x["uf"] == "passes_universe" and x["deepest"] == "no_row"]
    print(f"  n={len(silent)}  on scan-days={sum(1 for x in silent if x['scan_day'])}  "
          f"off-scan-days={sum(1 for x in silent if not x['scan_day'])}")
    c = Counter(band(x["og"]) for x in silent)
    print("  by band: " + "  ".join(f"{k}:{v}" for k, v in sorted(c.items())))
    print("  first 40 (ticker date open_gap high_gap prev_close prev_vol adv20$ ext5):")
    for x in sorted(silent, key=lambda x: -x["og"])[:40]:
        print(f"    {x['ticker']:6s} {x['trade_date']} og={x['og']:6.1f} hg={x['hg']:6.1f} "
              f"pc={x['pc']:8.2f} pv={x['pv']:>12,.0f} adv={_f(x['adv20_dollar']) or 0:>14,.0f} ext5={x['ext5_pct']}")

    # ── 5. D-1 floor exclusions with open gap >= 9 ─────────────────────────────────
    print("\n== 5. D-1 floor / shape / security-type exclusions with OPEN gap >= 9% ==")
    for uf in ("MIN_PREV_CLOSE", "MIN_PREV_DAY_VOLUME", "unclassified_security_type", "ticker_shape"):
        sub = [x for x in rows if x["uf"] == uf and x["og"] is not None and x["og"] >= 9.0]
        deep = Counter(x["deepest"] for x in sub)
        print(f"  {uf:28s} n={len(sub):5d}  " + "  ".join(f"{k}:{v}" for k, v in deep.most_common(5)))
    ns = [x for x in rows if x["uf"].startswith("non_stock") and x["og"] is not None and x["og"] >= 9.0]
    print(f"  non_stock (all types)        n={len(ns)}  " +
          "  ".join(f"{k}:{v}" for k, v in Counter(x['uf'] for x in ns).most_common(8)))

    if "--write-sets" in sys.argv:
        out = HERE / "_617_replay_sets.tsv"
        cols = ["set", "ticker", "trade_date", "open_gap_pct", "high_gap_pct", "prev_close",
                "prev_volume", "adv20_dollar", "ext5_pct", "deepest", "uf", "rth_bars_stored", "has_930"]
        with open(out, "w") as fh:
            fh.write("\t".join(cols) + "\n")
            for x in rows:
                s = None
                if x["uf"] in ("MIN_GAP_PCT_asof", "MIN_GAP_PCT_10_then_9_now") and x["deepest"] in ("no_row", "gap_floor"):
                    s = "gap_floor_" + ("9to10_admitted_now" if x["uf"] == "MIN_GAP_PCT_10_then_9_now" else band(x["og"]).strip("[)").replace(",", "_"))
                elif x["uf"] == "passes_universe" and x["deepest"] == "no_row":
                    s = "silent_no_row"
                elif x["uf"] in ("MIN_PREV_CLOSE", "MIN_PREV_DAY_VOLUME", "unclassified_security_type") \
                        and x["og"] is not None and x["og"] >= 9.0 and x["deepest"] == "no_row":
                    s = x["uf"]
                if s:
                    fh.write("\t".join(str(v) for v in (
                        s, x["ticker"], x["trade_date"], x["og"], x["hg"], x["pc"], x["pv"],
                        x["adv20_dollar"], x["ext5_pct"], x["deepest"], x["uf"], x["bars"][0], x["bars"][1])) + "\n")
        print(f"\nwritten: {out}")


if __name__ == "__main__":
    main()
