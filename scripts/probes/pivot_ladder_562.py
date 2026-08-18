#!/usr/bin/env python3
"""#562 pivot-ladder delayed-entry probe — the operator's entry architecture, measured.

READ-ONLY, $0. Consumes CSVs captured ONCE from prod (capture-once-read-many); makes no
DB connection, no API calls, no writes anywhere but stdout.

PRE-REGISTRATION: every parameter here was fixed in
docs/analysis/pivot_ladder_delayed_entry_562_2026-08-18.md BEFORE any outcome data was
read. Do not tune this file against its own output.

Capture (run 2026-08-18 against prod via `docker exec apollo-postgres psql`; SQL files
q_*_562.sql kept beside the CSVs):
  alerts_562.csv — live mi_ep_alerts (COALESCE(source,'live')='live'), one row per
                   (ticker, alert_date), <= 2026-08-17           (252 name-days)
  missed_562.csv — mi_ep_missed_outcomes ticker/alert_date/source/skip_category/
                   skip_reason ONLY (outcome columns deliberately NOT captured)
  daily_562.csv  — mi_daily_closes for the alert tickers, 2026-02-02..2026-08-17
  adr_562.csv    — 20-day ADR%% per (ticker, alert_date), sessions strictly before
  live_all.csv   — mi_live_trades all non-pending (reused from the 08-18 #482 capture)
  bar_coverage.csv — mi_intraday_bars coverage census (ticker, day, n, first, last)

COHORT: live EP alert name-days -> EPISODES (a re-alert within 10 trading days of an
anchor is absorbed into it), EP-day open >= $5, EP-day daily row + ADR (n>=10) required.
ENTERED = a filled magna53 mi_live_trades row (status closed/filled, entry_price set) on
any absorbed alert day; DECLINED = everything else. Alert days only — names the system
never alerted on are not in any denominator here.

LADDER (fixed at the EP event): EPL=EP-day low · EPC=EP-day close · PDH=prior-day high ·
MA10=SMA10 of closes through the prior session (recomputed daily) · EPH=EP-day high.

ARMS (uniform per pivot class; window = 10 trading days after the EP day):
  touch-reclaim (support): first session S with low<P decides — close>P -> signal,
      close<=P -> dead. Entry next open (void if open<=P). Stop = low(S).
  zone (support): first session S with low <= P+0.5*ADR$ decides — close>P -> signal,
      else dead. Entry next open (void if open<=P). Stop = min(low(S), P).
  breakout (EPH): first session S with high>=P. Entry = max(open(S), P) same session.
      Stop = prior session's low.
PRIMARY CELL = EPL touch-reclaim. Alternatives (primary cell only): W5, W20, LENIENT
(any later session may reclaim), CLOSE-ENTRY (idealized, untradeable).

SIM: geometry_sweep_572.simulate reused (import, not copy) at daily resolution —
+2R partial (half) -> breakeven -> SMA10/20-max close trail -> 20-td time stop;
gap-at-open stop fills; ambiguous both-touched days print a [cons, opt] bracket.

UNITS: R = pnl / (entry-stop, the arm's own unit) AND ADR units = pnl/(entry*ADR%%/100).
FILL LIMIT (state it every time): EVERY fill here is simulated — entries and exits; for
declined names no real fill ever existed. Daily bars cannot sequence intraday order.

Usage: python3 scripts/probes/pivot_ladder_562.py --data-dir <dir>
"""

import argparse
import csv
import statistics as st
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bracket_geometry_read_482 import d, era_of, f, pctl                    # noqa: E402
from geometry_sweep_572 import simulate                                     # noqa: E402

WINDOW = 10          # trading days after the EP day (signal window)
MFE_DAYS = 20        # forward MFE horizon after the classifying session
BANDS = (0.25, 0.5)  # proximity bands, x ADR$
PRICE_FLOOR = 5.0
SUPPORT = ("EPL", "EPC", "PDH", "MA10")


def load(data_dir: Path):
    alerts = list(csv.DictReader(open(data_dir / "alerts_562.csv")))
    missed = {}
    for r in csv.DictReader(open(data_dir / "missed_562.csv")):
        missed.setdefault((r["ticker"], r["alert_date"]), []).append(r["skip_category"])
    adr = {(r["ticker"], r["alert_date"]): f(r["adr_pct"])
           for r in csv.DictReader(open(data_dir / "adr_562.csv"))
           if int(r["n_days"] or 0) >= 10}
    daily = {}
    for row in csv.reader(open(data_dir / "daily_562.csv")):
        if row[0] == "ticker" or len(row) != 6:
            continue
        try:
            daily.setdefault(row[0], []).append(
                (d(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5])))
        except (TypeError, ValueError):
            continue
    for v in daily.values():
        v.sort()
    live = list(csv.DictReader(open(data_dir / "live_all.csv")))
    coverage = set()
    for row in csv.reader(open(data_dir / "bar_coverage.csv")):
        if len(row) >= 2:
            coverage.add((row[0], row[1]))
    return alerts, missed, adr, daily, live, coverage


def build_episodes(alerts, daily):
    """Dedup alert name-days into episodes: a re-alert within WINDOW trading days of an
    anchor (in the ticker's own session series) is absorbed."""
    by_t = {}
    for a in alerts:
        by_t.setdefault(a["ticker"], []).append(a)
    episodes, absorbed = [], 0
    for t, rows in sorted(by_t.items()):
        rows.sort(key=lambda a: a["alert_date"])
        idx = {day: i for i, (day, *_r) in enumerate(daily.get(t, []))}
        anchor = None
        for a in rows:
            ad = d(a["alert_date"])
            if anchor is not None:
                ai, ci = idx.get(anchor["date"]), idx.get(ad)
                if ai is not None and ci is not None and ci - ai <= WINDOW:
                    anchor["absorbed"].append(ad)
                    absorbed += 1
                    continue
            anchor = dict(ticker=t, date=ad, tier=a["score_tier"] or "none",
                          absorbed=[ad])
            episodes.append(anchor)
    return episodes, absorbed


def classify_entered(episodes, live):
    filled = {}
    for r in live:
        if (r["signal_type"] == "magna53" and r["status"] in ("closed", "filled")
                and r["entry_price"]):
            filled[(r["ticker"], r["alert_date"])] = r
    for ep in episodes:
        ep["live_row"] = None
        for ad in ep["absorbed"]:
            row = filled.get((ep["ticker"], ad.isoformat()))
            if row is not None:
                ep["live_row"] = row
        ep["entered"] = ep["live_row"] is not None
    return episodes


def live_realized_r(row):
    pnl, shares = f(row["total_pnl"]), f(row["entry_shares"])
    entry = f(row["entry_price"])
    unit = (entry - (f(row["orb_low"]) or f(row["hard_stop"]) or 0)) if entry else 0
    if pnl is None or not shares or unit <= 0:
        return None
    return (pnl / shares) / unit


def sessions_after(daily, ticker, day):
    return [b for b in daily.get(ticker, []) if b[0] > day]


def sma10_at(daily, ticker, day):
    """SMA10 of the 10 closes ENDING the session strictly before `day`."""
    prev = [c for (dt, _o, _h, _l, c) in daily.get(ticker, []) if dt < day]
    return sum(prev[-10:]) / 10 if len(prev) >= 10 else None


def first_signal(ep, daily, pivot, arm, window=WINDOW, lenient=False):
    """Return (status, S) — status in signal/dead/none/no_pivot; S = deciding session.
    For MA10 the level moves; P used for entry/stop rules is the level ON S's day."""
    t, ad = ep["ticker"], ep["date"]
    fwd = sessions_after(daily, t, ad)[:window]
    for S in fwd:
        day, o, h, l, c = S
        P = sma10_at(daily, t, day) if pivot == "MA10" else ep[pivot]
        if P is None:
            return "no_pivot", None, None
        band = 0.5 * ep["adr_pct"] / 100 * P
        if arm == "touch":
            if l < P:
                if c > P:
                    return "signal", S, P
                if lenient:
                    continue
                return "dead", S, P
        elif arm == "zone":
            if l <= P + band:
                return ("signal", S, P) if c > P else ("dead", S, P)
        elif arm == "breakout":
            if h >= P:
                return "signal", S, P
    return "none", None, None


def run_arm(ep, daily, pivot, arm, seq, window=WINDOW, lenient=False,
            close_entry=False):
    """Simulate one cell for one episode. Returns dict(status=..., res=..., ...)."""
    status, S, P = first_signal(ep, daily, pivot, arm, window, lenient)
    if status != "signal":
        return dict(status=status)
    t = ep["ticker"]
    day, o, h, l, c = S
    if arm == "breakout":
        entry, entry_day = max(o, P), day
        prev = [b for b in daily.get(t, []) if b[0] < day]
        stop = prev[-1][3] if prev else None
        if stop is None or stop >= entry:
            return dict(status="void")
    else:
        nxt = sessions_after(daily, t, day)
        if not nxt:
            return dict(status="no_next")
        if close_entry:
            entry, entry_day = c, nxt[0][0]
        else:
            entry, entry_day = nxt[0][1], nxt[0][0]   # next session OPEN
            if entry <= P:
                return dict(status="void")
        stop = l if arm == "touch" else min(l, P)
        if stop >= entry:
            return dict(status="void")
    res = simulate(entry, "09:30", stop, t, ep["date"], {}, daily,
                   seq=seq, entry_day=entry_day, skip_day0_minutes=True)
    if res is None:
        return dict(status="void")
    r_unit = entry - stop
    return dict(status="signal", sig_day=day, entry_day=entry_day, entry=entry,
                stop=stop, r=res["pnl_ps"] / r_unit,
                adr_u=res["pnl_ps"] / (ep["entry_adr_base"] * entry),
                horizon=res["horizon"], partial=res["partial_taken"],
                stop_pct=100 * r_unit / entry, exit_day=res["exit_day"],
                exit_reason=res["exit_reason"])


def stats_line(label, vals):
    n = len(vals)
    if n == 0:
        return f"    {label:<44} n=0 — not readable"
    if n < 4:
        return (f"    {label:<44} n={n} — not readable "
                f"(raw: {', '.join(f'{v:+.2f}' for v in sorted(vals))})")
    wins = sum(1 for v in vals if v > 0)
    return (f"    {label:<44} n={n:<3} sum={sum(vals):+8.2f} med={st.median(vals):+6.2f} "
            f"p90={pctl(vals, 90):+6.2f} max={max(vals):+6.2f} win={wins}/{n} "
            f">=+1:{sum(1 for v in vals if v >= 1)} >=+2:{sum(1 for v in vals if v >= 2)}")


def mfe_adr(ep, daily, S_day):
    """MFE in ADR units over MFE_DAYS sessions after S_day, from the NEXT session's
    open. None if no next session."""
    fwd = sessions_after(daily, ep["ticker"], S_day)[:MFE_DAYS]
    if not fwd:
        return None
    base_open = fwd[0][1]
    hi = max(b[2] for b in fwd)
    return (hi - base_open) / (ep["entry_adr_base"] * base_open)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    args = ap.parse_args()
    data_dir = Path(args.data_dir)
    alerts, missed, adr, daily, live, coverage = load(data_dir)

    episodes, absorbed = build_episodes(alerts, daily)
    classify_entered(episodes, live)

    # eligibility
    excl = dict(no_daily=0, sub5=0, no_adr=0, no_fwd=0)
    cohort = []
    for ep in episodes:
        t, ad = ep["ticker"], ep["date"]
        row0 = next((b for b in daily.get(t, []) if b[0] == ad), None)
        if row0 is None:
            excl["no_daily"] += 1
            continue
        _dt, o, h, l, c = row0
        if o < PRICE_FLOOR:
            excl["sub5"] += 1
            continue
        a = adr.get((t, ad.isoformat()))
        if not a:
            excl["no_adr"] += 1
            continue
        fwd = sessions_after(daily, t, ad)
        if not fwd:
            excl["no_fwd"] += 1
            continue
        prev = [b for b in daily.get(t, []) if b[0] < ad]
        ep.update(EPL=l, EPC=c, EPH=h, PDH=prev[-1][2] if prev else None,
                  MA10="dynamic", adr_pct=a, adr_dollar=a / 100 * l,
                  entry_adr_base=a / 100,  # multiply by entry px at use
                  truncated=len(fwd) < WINDOW,
                  skip_cats=sorted({c2 for ad2 in ep["absorbed"]
                                    for c2 in missed.get((t, ad2.isoformat()), [])}))
        cohort.append(ep)

    n_ent = sum(1 for ep in cohort if ep["entered"])
    print("=" * 100)
    print("#562 PIVOT-LADDER DELAYED-ENTRY PROBE — pre-registered; every cell reported")
    print("=" * 100)
    print(f"DENOMINATOR: {len(alerts)} live EP alert name-days -> {len(episodes)} episodes "
          f"({absorbed} re-alerts absorbed) -> {len(cohort)} eligible "
          f"(excluded: {excl['no_daily']} no EP-day daily row, {excl['sub5']} sub-$5 open, "
          f"{excl['no_adr']} no 20d ADR, {excl['no_fwd']} no forward sessions).")
    print(f"  split: ENTERED {n_ent} / DECLINED {len(cohort) - n_ent}; "
          f"truncated windows (alert within {WINDOW} td of 08-17): "
          f"{sum(1 for ep in cohort if ep['truncated'])}")
    print(f"  tiers: HIGH {sum(1 for ep in cohort if ep['tier'] == 'HIGH')} / "
          f"MODERATE+none {sum(1 for ep in cohort if ep['tier'] != 'HIGH')}")
    print("  FILL LIMIT: every fill below is SIMULATED (entries and exits); declined "
          "names never had a real fill. Daily bars cannot sequence intraday order; "
          "ambiguous days print a [cons, opt] bracket.")
    print("  Alert-day cohort only: names the system never alerted on are outside every "
          "denominator here.")

    # ── proximity classification (the deliverable) ──────────────────────────────
    print()
    print("-" * 100)
    print("1. PROXIMITY / BASE RATES — per support pivot, 10-td window, first-touch "
          "decides; near-miss = entered the band, never traded below P")
    print("-" * 100)
    prox = {}
    for pivot in SUPPORT:
        for band in BANDS:
            cls = dict(never=[], near=[], reclaimed=[], dead=[], no_pivot=[])
            for ep in cohort:
                t, ad = ep["ticker"], ep["date"]
                fwd = sessions_after(daily, t, ad)[:WINDOW]
                touched = near_S = None
                status = "never"
                for S in fwd:
                    day, o, h, l, c = S
                    P = sma10_at(daily, t, day) if pivot == "MA10" else ep[pivot]
                    if P is None:
                        status = "no_pivot"
                        break
                    bd = band * ep["adr_pct"] / 100 * P
                    if l < P:
                        touched = S
                        status = "reclaimed" if c > P else "dead"
                        break
                    if near_S is None and l <= P + bd:
                        near_S = S
                if status == "never" and near_S is not None:
                    status, touched = "near", near_S
                elif status == "never":
                    touched = next((b for b in daily.get(t, []) if b[0] == ad), None)
                cls[status].append((ep, touched))
            prox[(pivot, band)] = cls
            n_ok = len(cohort) - len(cls["no_pivot"])
            line = f"  {pivot:<5} band {band:>4}xADR  (n={n_ok}):"
            for k in ("never", "near", "reclaimed", "dead"):
                rows = cls[k]
                mfes = [m for ep, S in rows if S is not None
                        and (m := mfe_adr(ep, daily, S[0])) is not None]
                pct8 = (100 * sum(1 for m in mfes if m >= 8) / len(mfes)) if mfes else 0
                line += (f"\n      {k:<10} n={len(rows):<3} "
                         f"({100 * len(rows) / max(n_ok, 1):4.1f}%)  fwd-MFE/ADR "
                         f"med={st.median(mfes):+5.1f} p90={pctl(mfes, 90):+5.1f} "
                         f">=8x: {pct8:4.1f}%  (n_mfe={len(mfes)})"
                         if mfes else
                         f"\n      {k:<10} n={len(rows):<3} "
                         f"({100 * len(rows) / max(n_ok, 1):4.1f}%)  fwd-MFE n=0")
            print(line)

    # ── the ladder grid ─────────────────────────────────────────────────────────
    cells = [(p, "touch") for p in SUPPORT] + [(p, "zone") for p in SUPPORT] \
        + [("EPH", "breakout")]
    print()
    print("-" * 100)
    print("2. LADDER GRID — realized R (own unit) and ADR units, [cons, opt]; "
          "PRIMARY CELL = EPL touch-reclaim; split DECLINED vs ENTERED")
    print("-" * 100)
    grid = {}
    for pivot, arm in cells:
        for seq in ("cons", "opt"):
            outs = [(ep, run_arm(ep, daily, pivot, arm, seq)) for ep in cohort]
            grid[(pivot, arm, seq)] = outs
    for pivot, arm in cells:
        outs_c = grid[(pivot, arm, "cons")]
        outs_o = grid[(pivot, arm, "opt")]
        sig = [(ep, o) for ep, o in outs_c if o["status"] == "signal"]
        counts = {}
        for _ep, o in outs_c:
            counts[o["status"]] = counts.get(o["status"], 0) + 1
        n_base = len(cohort) - counts.get("no_pivot", 0)
        print(f"\n  {pivot} {arm}{'  << PRIMARY' if (pivot, arm) == ('EPL', 'touch') else ''}"
              f"  — fires {len(sig)}/{n_base} "
              f"({100 * len(sig) / max(n_base, 1):.0f}% base rate; "
              f"dead {counts.get('dead', 0)}, none {counts.get('none', 0)}, "
              f"void {counts.get('void', 0)}, no_next {counts.get('no_next', 0)})")
        for label, pick in (("DECLINED", False), ("ENTERED", True)):
            for unit in ("r", "adr_u"):
                vc = [o[unit] for ep, o in outs_c
                      if o["status"] == "signal" and ep["entered"] == pick]
                vo = [o[unit] for ep, o in outs_o
                      if o["status"] == "signal" and ep["entered"] == pick]
                u = "R  " if unit == "r" else "ADR"
                print(stats_line(f"{label:<9} {u} cons", vc))
                if any(abs(a - b) > 1e-9 for a, b in zip(sorted(vc), sorted(vo))):
                    print(stats_line(f"{label:<9} {u} opt ", vo))
        hz = sum(1 for _ep, o in sig if o["horizon"])
        med_stop = st.median(o["stop_pct"] for _ep, o in sig) if sig else 0
        pf = sum(1 for _ep, o in sig if o["partial"])
        print(f"    open-at-horizon {hz}/{len(sig)} · median stop width "
              f"{med_stop:.1f}% · partial fired {pf}/{len(sig)}")

    # ── primary-cell alternatives ───────────────────────────────────────────────
    print()
    print("-" * 100)
    print("3. PRIMARY-CELL ALTERNATIVES (EPL touch-reclaim; pre-registered; cons seq) — "
          "side by side, NEVER best-of")
    print("-" * 100)
    alts = [("PRIMARY W10 next-open", dict()),
            ("W5  window=5", dict(window=5)),
            ("W20 window=20", dict(window=20)),
            ("LENIENT reclaim-any-session", dict(lenient=True)),
            ("CLOSE-ENTRY (untradeable bound)", dict(close_entry=True))]
    for label, kw in alts:
        outs = [(ep, run_arm(ep, daily, "EPL", "touch", "cons", **kw)) for ep in cohort]
        sig = [(ep, o) for ep, o in outs if o["status"] == "signal"]
        for unit, u in (("r", "R  "), ("adr_u", "ADR")):
            print(stats_line(f"{label:<34} {u} (fires {len(sig)}/{len(cohort)})",
                             [o[unit] for _ep, o in sig]))

    # ── era + tier slices, primary cell ─────────────────────────────────────────
    print()
    print("-" * 100)
    print("4. PRIMARY CELL SLICES (cons) — era A/B/C (alert-date basis) and tier")
    print("-" * 100)
    outs = [(ep, run_arm(ep, daily, "EPL", "touch", "cons")) for ep in cohort]
    sig = [(ep, o) for ep, o in outs if o["status"] == "signal"]
    for era in ("A", "B", "C"):
        vals = [o["r"] for ep, o in sig if era_of(ep["date"]) == era]
        print(stats_line(f"era {era} R", vals))
    for lab, pick in (("HIGH", True), ("MODERATE+none", False)):
        vals = [o["r"] for ep, o in sig if (ep["tier"] == "HIGH") == pick]
        print(stats_line(f"tier {lab} R", vals))

    # NET + ENTERED live baseline
    print()
    print("-" * 100)
    print("5. NET IN THE COHORT · ENTERED-NAMES LIVE BASELINE")
    print("-" * 100)
    for ep, o in outs:
        if ep["ticker"] == "NET":
            print(f"  NET episode {ep['date']} entered={ep['entered']} -> "
                  f"{o['status']}"
                  + (f" sig {o['sig_day']} entry {o['entry_day']} @{o['entry']:.2f} "
                     f"stop {o['stop']:.2f} ({o['stop_pct']:.1f}%) -> "
                     f"R {o['r']:+.2f} / ADR {o['adr_u']:+.2f} "
                     f"exit {o['exit_day']} {o['exit_reason']}"
                     f"{' [OPEN AT HORIZON]' if o['horizon'] else ''}"
                     if o["status"] == "signal" else ""))
    ent = [(ep, o) for ep, o in outs if ep["entered"]]
    both = [(live_realized_r(ep["live_row"]), o) for ep, o in ent]
    both = [(lv, o) for lv, o in both if lv is not None]
    print(f"  ENTERED episodes with a live realized R: {len(both)}; live sum "
          f"{sum(lv for lv, _o in both):+.2f}R vs primary-cell sim on the same episodes "
          f"sum {sum(o['r'] for _lv, o in both if o['status'] == 'signal'):+.2f}R "
          f"(fires on {sum(1 for _lv, o in both if o['status'] == 'signal')}"
          f"/{len(both)}; a non-firing episode adds 0)")

    # ── 620 prerequisite costing ────────────────────────────────────────────────
    print()
    print("-" * 100)
    print("6. 620 PREREQUISITE — minute bars needed for a proximity+620 replay "
          "(zone signals, 0.5xADR band, all support pivots)")
    print("-" * 100)
    need = set()
    for pivot in SUPPORT:
        for ep, o in grid[(pivot, "zone", "cons")]:
            if o["status"] == "signal":
                need.add((ep["ticker"], o["sig_day"].isoformat()))
                need.add((ep["ticker"], o["entry_day"].isoformat()))
    have = need & coverage
    print(f"  distinct approach/entry ticker-days: {len(need)}; already in "
          f"mi_intraday_bars: {len(have)}; needing a targeted Polygon minute pull: "
          f"{len(need - have)} (one bars request per ticker-day, $0 under the current "
          f"Polygon subscription)")

    print()
    print("=" * 100)
    print("END OF PROBE OUTPUT — interpretation lives in "
          "docs/analysis/pivot_ladder_delayed_entry_562_2026-08-18.md")
    print("=" * 100)


if __name__ == "__main__":
    main()
