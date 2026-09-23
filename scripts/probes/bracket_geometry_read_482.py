#!/usr/bin/env python3
"""#482 bracket-geometry read — 5-min ORB shadow lane vs the live 1-min bracket.

READ-ONLY, $0. Consumes CSVs captured ONCE from prod (capture-once-read-many);
makes no DB connection, no API calls, no writes anywhere but stdout.

Capture (run on 2026-08-18 against prod via `docker exec apollo-postgres psql`;
each file below states its exact WHERE clause so the pull is reproducible):

  shadow_closed.csv  — mi_orb_shadow_trades WHERE bar_size_minutes=5
                       AND status='closed' AND NOT quarantined   (42 rows)
  shadow_open.csv    — same, status='open'                        (10 rows)
  live_all.csv       — mi_live_trades, all non-pending rows       (316 rows)
  adr.csv            — per (ticker, alert_date): mean 20-day (high-low)/close %
                       from mi_daily_closes, days strictly before alert_date
  daily_bars.csv     — daily OHLC for every cohort ticker since 2026-04-01

Quarantine rule: the 28 fabricated rows are excluded IN THE CAPTURE SQL
(`AND NOT quarantined`) and re-asserted here — they never enter any number.

Era boundaries (live-side exit-rule changes; alert_date basis):
  A  < 2026-08-05             no +2R partial, ORB-low stop
  B  2026-08-05 .. 2026-08-16 +2R partial live, ORB-low stop
  C  >= 2026-08-17            stop = entry-2R at half size (R unit redefined)

Signal split: only magna53 rows carry the 1-min-vs-5-min STOP contrast.
9m_day2 rows use the prior-day-low stop in BOTH lanes (only the entry level
differs), so they are reported separately and never pooled into the
stop-geometry verdict.

Usage: python3 scripts/probes/bracket_geometry_read_482.py --data-dir <dir>
"""

import argparse
import csv
import json
import statistics as st
from datetime import date
from pathlib import Path

ERA_B_START = date(2026, 8, 5)
ERA_C_START = date(2026, 8, 17)


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def d(x):
    return date.fromisoformat(x)


def era_of(ad: date) -> str:
    if ad < ERA_B_START:
        return "A"
    if ad < ERA_C_START:
        return "B"
    return "C"


def pctl(vals, p):
    """Nearest-rank percentile (no interpolation invented for tiny n)."""
    if not vals:
        return None
    s = sorted(vals)
    k = max(0, min(len(s) - 1, round(p / 100 * (len(s) - 1))))
    return s[k]


def load(data_dir: Path):
    def rows(name):
        with open(data_dir / name) as fh:
            return list(csv.DictReader(fh))

    shadow = rows("shadow_closed.csv")
    shadow_open = rows("shadow_open.csv")
    live = rows("live_all.csv")
    adr = {(r["ticker"], r["alert_date"]): f(r["adr_pct"])
           for r in rows("adr.csv") if int(r["n_days"] or 0) >= 10}
    bars = {}
    for r in rows("daily_bars.csv"):
        bars.setdefault(r["ticker"], []).append(
            (d(r["trade_date"]), f(r["high_price"]), f(r["low_price"])))
    for v in bars.values():
        v.sort()
    return shadow, shadow_open, live, adr, bars


def enrich(r, adr, *, lane):
    """Compute per-row R, ADR-unit outcome, era, flags. Returns None if unusable."""
    out = dict(r)
    out["alert_date_d"] = d(r["alert_date"])
    out["era"] = era_of(out["alert_date_d"])
    pnl, risk = f(r["total_pnl"]), f(r["risk_dollars"])
    entry, shares = f(r["entry_price"]), f(r["entry_shares"])
    hard = f(r["hard_stop"])
    if pnl is None or not risk or not entry or not shares or not hard:
        return None
    # PRIMARY unit — per-share stop-distance R: (pnl/share) / (entry - hard_stop).
    # This is the geometry question itself (how far price went vs the stop width)
    # and is immune to the position-size cap, which binds on most rows and makes
    # pnl/risk_dollars (planned-risk R) UNDERSTATE outcomes non-uniformly.
    out["r"] = (pnl / shares) / (entry - hard)
    # SECONDARY unit — the system's own convention (get_shadow_outcomes_window,
    # kill_scale_bands): pnl / PLANNED risk dollars.
    out["r_planned"] = pnl / risk
    out["cap_ratio"] = (shares * (entry - hard)) / risk  # <1 = size cap bound
    adr_pct = adr.get((r["ticker"], r["alert_date"]))
    out["adr_pct"] = adr_pct
    out["adr_units"] = (pnl / shares) / (entry * adr_pct / 100) if adr_pct else None
    out["stop_dist"] = entry - hard
    out["stop_dist_pct"] = 100 * (entry - hard) / entry
    out["lane"] = lane
    out["reconstructed"] = bool(r.get("replayed_at"))
    return out


def block(label, rows, unit="r"):
    vals = [r[unit] for r in rows if r.get(unit) is not None]
    n = len(vals)
    if n == 0:
        return f"  {label:<44} n=0   — not readable"
    if n < 4:
        detail = ", ".join(f"{v:+.2f}" for v in sorted(vals))
        return f"  {label:<44} n={n}   — not readable (raw: {detail})"
    wins = sum(1 for v in vals if v > 0)
    ge1 = sum(1 for v in vals if v >= 1)
    ge2 = sum(1 for v in vals if v >= 2)
    return (f"  {label:<44} n={n:<3} sum={sum(vals):+7.2f}  med={st.median(vals):+6.2f}  "
            f"mean={st.fmean(vals):+6.2f}  p90={pctl(vals, 90):+6.2f}  "
            f"max={max(vals):+6.2f}  win={wins}/{n}  >=+1:{ge1}  >=+2:{ge2}")


def max_high(bars, ticker, start: date, hold_days: int):
    """Max daily high from alert day through alert+hold (calendar walk over bars)."""
    series = bars.get(ticker, [])
    highs = [h for (day, h, _l) in series
             if h is not None and start <= day and
             sum(1 for (d2, _h, _l2) in series if start <= d2 <= day) <= hold_days + 1]
    return max(highs) if highs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    args = ap.parse_args()
    data_dir = Path(args.data_dir)

    shadow_raw, shadow_open, live_raw, adr, bars = load(data_dir)

    # ── hard assertions ──────────────────────────────────────────────────────
    assert all(r["quarantined"] in ("f", "false", "False") for r in shadow_raw), \
        "quarantined row leaked into the closed capture"
    assert len(shadow_raw) == 42, f"expected 42 closed shadow rows, got {len(shadow_raw)}"

    live_closed = [r for r in live_raw if r["status"] == "closed"]
    excluded_attr = [r for r in live_closed if r["pnl_attribution"]]
    live_closed = [r for r in live_closed if not r["pnl_attribution"]]

    shadow = [e for e in (enrich(r, adr, lane="5m") for r in shadow_raw) if e]
    live = [e for e in (enrich(r, adr, lane="1m") for r in live_closed) if e]

    print("=" * 100)
    print("#482 BRACKET-GEOMETRY READ — 5-min ORB shadow vs live 1-min bracket "
          "(captured 2026-08-18, read-only)")
    print("=" * 100)
    print(f"shadow closed (NOT quarantined): {len(shadow_raw)}  "
          f"(usable after R computation: {len(shadow)}; "
          f"reconstructed via replay: {sum(1 for s in shadow if s['reconstructed'])}; "
          f"open still accruing: {len(shadow_open)})")
    print(f"live closed: {len(live_closed)} usable "
          f"({len(excluded_attr)} excluded for non-NULL pnl_attribution: "
          f"{sorted(set(r['pnl_attribution'] for r in excluded_attr))})")
    capped = [r for r in shadow + live if r["cap_ratio"] < 0.85]
    print(f"UNIT NOTE: the position-size cap binds on {len(capped)}/{len(shadow) + len(live)} "
          f"rows (actual $risk < planned risk_dollars; median actual/planned "
          f"{st.median(r['cap_ratio'] for r in shadow + live):.2f}). "
          f"Planned-risk R understates outcomes non-uniformly, so the PRIMARY unit "
          f"below is per-share stop-distance R = (pnl/share)/(entry-hard_stop); "
          f"planned-risk R is shown as the secondary, system-convention unit.")
    no_adr = [r for r in shadow + live if r["adr_units"] is None]
    print(f"ADR coverage: {len(shadow) + len(live) - len(no_adr)}/{len(shadow) + len(live)} "
          f"rows have a 20-day ADR (missing: "
          f"{', '.join(r['ticker'] + ' ' + r['alert_date'] for r in no_adr) or 'none'})")

    m53_s = [r for r in shadow if r["signal_type"] == "magna53"]
    m53_l = [r for r in live if r["signal_type"] == "magna53"]
    n9m_s = [r for r in shadow if r["signal_type"] == "9m_day2"]
    n9m_l = [r for r in live if r["signal_type"] == "9m_day2"]

    # ── PAIRED (primary) ─────────────────────────────────────────────────────
    live_by_key = {(r["ticker"], r["alert_date"]): r for r in live}
    pairs = [(s, live_by_key[(s["ticker"], s["alert_date"])])
             for s in shadow if (s["ticker"], s["alert_date"]) in live_by_key]
    pairs_m53 = [(s, l) for (s, l) in pairs if s["signal_type"] == "magna53"]
    pairs_9m = [(s, l) for (s, l) in pairs if s["signal_type"] == "9m_day2"]

    print()
    print("-" * 100)
    print("1. PAIRED COMPARISON (PRIMARY) — same ticker, same day, both lanes closed")
    print("-" * 100)
    for tag, ps in (("magna53 (the stop-geometry contrast)", pairs_m53),
                    ("9m_day2 (SAME stop both lanes — entry-level contrast only)", pairs_9m)):
        print(f"\n  {tag}: paired n={len(ps)}")
        for s, l in sorted(ps, key=lambda p: p[0]["alert_date"]):
            dr = s["r"] - l["r"]
            da = (s["adr_units"] - l["adr_units"]
                  if s["adr_units"] is not None and l["adr_units"] is not None else None)
            print(f"    {s['ticker']:<6} {s['alert_date']}  era={s['era']}  "
                  f"R(1m)={l['r']:+6.2f} R(5m)={s['r']:+6.2f} dR={dr:+6.2f}   "
                  f"ADR(1m)={l['adr_units']:+6.2f} ADR(5m)={s['adr_units']:+6.2f} "
                  f"dADR={f'{da:+6.2f}' if da is not None else '   n/a'}   "
                  f"[{'replayed' if s['reconstructed'] else 'accrued'}"
                  f"/{l['account_mode']}]")
        if ps:
            sr = [s["r"] for s, _ in ps]
            lr = [l["r"] for _, l in ps]
            deltas = [s["r"] - l["r"] for s, l in ps]
            sa = [s["adr_units"] for s, _ in ps if s["adr_units"] is not None]
            la = [l["adr_units"] for _, l in ps if l["adr_units"] is not None]
            better = sum(1 for x in deltas if x > 0.05)
            worse = sum(1 for x in deltas if x < -0.05)
            print(f"    SUM R:   1m {sum(lr):+.2f}  vs 5m {sum(sr):+.2f}   "
                  f"(paired delta sum {sum(deltas):+.2f})")
            print(f"    MEDIAN:  1m {st.median(lr):+.2f}  vs 5m {st.median(sr):+.2f}   "
                  f"median pair-delta {st.median(deltas):+.2f}")
            print(f"    ADR SUM: 1m {sum(la):+.2f}  vs 5m {sum(sa):+.2f}")
            lrp = [l["r_planned"] for _, l in ps]
            srp = [s["r_planned"] for s, _ in ps]
            print(f"    (planned-risk unit, system convention: 1m sum {sum(lrp):+.2f} "
                  f"med {st.median(lrp):+.2f}  vs 5m sum {sum(srp):+.2f} "
                  f"med {st.median(srp):+.2f})")
            print(f"    5m better on {better}, worse on {worse}, "
                  f"~tied on {len(deltas) - better - worse} of {len(deltas)} pairs "
                  f"(|dR|<=0.05 = tie)")

    unpaired_s = [s for s in shadow if (s["ticker"], s["alert_date"]) not in live_by_key]
    print(f"\n  Shadow-closed rows with NO closed live twin: {len(unpaired_s)} "
          f"(live never filled / skipped / still open that name-day)")

    # ── BY EXIT ERA ──────────────────────────────────────────────────────────
    print()
    print("-" * 100)
    print("2. BY EXIT ERA (era = live-side exit-rule regime; alert_date basis)")
    print("   A < 08-05: no +2R partial, ORB-low stop | B 08-05..08-16: +2R partial, "
          "ORB-low stop | C >= 08-17: entry-2R stop")
    print("-" * 100)
    for era in ("A", "B", "C"):
        print(f"\n  era {era} — realized R:")
        print(block(f"live 1-min magna53", [r for r in m53_l if r["era"] == era]))
        print(block(f"shadow 5-min magna53", [r for r in m53_s if r["era"] == era]))
        ps = [p for p in pairs_m53 if p[0]["era"] == era]
        if len(ps) >= 4:
            deltas = [s["r"] - l["r"] for s, l in ps]
            print(f"  paired magna53 in era {era}: n={len(ps)}  "
                  f"delta sum {sum(deltas):+.2f}  median delta {st.median(deltas):+.2f}")
        else:
            print(f"  paired magna53 in era {era}: n={len(ps)} — not readable")

    # ── COHORT vs COHORT (secondary) ─────────────────────────────────────────
    print()
    print("-" * 100)
    print("3. COHORT vs COHORT (SECONDARY — different populations, different gates; "
          "labelled as such)")
    print("-" * 100)
    print("\n  realized R (PRIMARY: per-share stop-distance units):")
    print(block("live 1-min magna53 (all eras)", m53_l))
    print(block("shadow 5-min magna53 (all eras)", m53_s))
    print(block("live 1-min 9m_day2", n9m_l))
    print(block("shadow 5-min 9m_day2", n9m_s))
    print("\n  realized R (secondary: pnl / planned risk_dollars — system convention):")
    print(block("live 1-min magna53 (all eras)", m53_l, unit="r_planned"))
    print(block("shadow 5-min magna53 (all eras)", m53_s, unit="r_planned"))
    print(block("live 1-min 9m_day2", n9m_l, unit="r_planned"))
    print(block("shadow 5-min 9m_day2", n9m_s, unit="r_planned"))
    print("\n  ADR units (per-share pnl / stock's own 20-day average daily range):")
    print(block("live 1-min magna53 (all eras)", m53_l, unit="adr_units"))
    print(block("shadow 5-min magna53 (all eras)", m53_s, unit="adr_units"))
    print(block("live 1-min 9m_day2", n9m_l, unit="adr_units"))
    print(block("shadow 5-min 9m_day2", n9m_s, unit="adr_units"))
    print("\n  stop distance as % of entry (the geometry itself):")
    for tag, rows in (("live 1-min magna53", m53_l), ("shadow 5-min magna53", m53_s)):
        v = [r["stop_dist_pct"] for r in rows if r["stop_dist_pct"]]
        if v:
            print(f"  {tag:<44} n={len(v):<3} med={st.median(v):5.2f}%  "
                  f"mean={st.fmean(v):5.2f}%  max={max(v):5.2f}%")

    # ── MECHANISM 5 — the wider R unit vs the +2R partial ───────────────────
    print()
    print("-" * 100)
    print("4. MECHANISM 5 — does the wider 5-min R unit push the +2R partial above "
          "where price went?")
    print("   For every magna53 row in each lane: +2R target in the lane's own unit vs "
          "max daily high over the hold window.")
    print("   (Daily-bar granularity — 'reached' is optimistic for both lanes equally; "
          "sequencing vs the stop is not resolvable from daily bars.)")
    print("-" * 100)
    for tag, rows in (("live 1-min", m53_l), ("shadow 5-min", m53_s)):
        reached = missed = nodata = 0
        for r in rows:
            entry, hard = f(r["entry_price"]), f(r["hard_stop"])
            if not entry or not hard:
                nodata += 1
                continue
            # era C live rows: hard_stop is already entry-2R; the R unit (and the
            # UNMOVED target) is entry-orb_low. Use orb_low when present.
            orb_low = f(r.get("orb_low"))
            r_unit = (entry - orb_low) if (r["era"] == "C" and r["lane"] == "1m"
                                           and orb_low) else (entry - hard)
            target = entry + 2 * r_unit
            hi = max_high(bars, r["ticker"], r["alert_date_d"],
                          int(r["hold_days"] or 0))
            if hi is None:
                nodata += 1
            elif hi >= target:
                reached += 1
            else:
                missed += 1
        n = reached + missed
        print(f"  {tag:<14} +2R (own unit) reached within hold: {reached}/{n}"
              f"  ({100 * reached / n:.0f}%)" + (f"  [no-bar: {nodata}]" if nodata else ""))
    print("\n  Paired head-to-head (same name-day, each lane's own +2R target):")
    flips = 0
    for s, l in pairs_m53:
        e_l, h_l = f(l["entry_price"]), f(l["hard_stop"])
        e_s, h_s = f(s["entry_price"]), f(s["hard_stop"])
        orb_low_l = f(l.get("orb_low"))
        r_l = (e_l - orb_low_l) if (l["era"] == "C" and orb_low_l) else (e_l - h_l)
        t_l, t_s = e_l + 2 * r_l, e_s + 2 * (e_s - h_s)
        hold = max(int(l["hold_days"] or 0), int(s["hold_days"] or 0))
        hi = max_high(bars, s["ticker"], s["alert_date_d"], hold)
        if hi is None:
            continue
        r1, r5 = hi >= t_l, hi >= t_s
        if r1 and not r5:
            flips += 1
            print(f"    {s['ticker']:<6} {s['alert_date']}  1m +2R target "
                  f"{t_l:.2f} REACHED (hi {hi:.2f}) but 5m +2R target {t_s:.2f} NOT "
                  f"— the wider unit destroyed the partial here")
    print(f"    pairs where 1m's +2R was touched but 5m's was not: {flips}/{len(pairs_m53)}")

    # ── RECONSTRUCTED vs LIVED ───────────────────────────────────────────────
    print()
    print("-" * 100)
    print("5. RECONSTRUCTED vs LIVED — same lane, split by provenance (shadow magna53)")
    print("-" * 100)
    print(block("shadow 5m magna53 — replayed (daily-bar sim)",
                [r for r in m53_s if r["reconstructed"]]))
    print(block("shadow 5m magna53 — accrued in real time",
                [r for r in m53_s if not r["reconstructed"]]))
    print("  (Both are DAILY-BAR simulations at exit; 'accrued' rows differ only in "
          "being stepped one real day at a time. NO shadow row is a real fill. "
          "Live rows are actual Alpaca fills — paper account before the cutover, "
          "real money after.)")
    lm = sorted(set(r["account_mode"] for r in live))
    print(f"  live rows account_mode present: {lm}; "
          f"real-money closed magna53: "
          f"{sum(1 for r in m53_l if r['account_mode'] == 'live')}")

    print()
    print("=" * 100)
    print("END OF PROBE OUTPUT — interpretation lives in "
          "docs/analysis/bracket_geometry_read_482_2026-08-18.md")
    print("=" * 100)


if __name__ == "__main__":
    main()
