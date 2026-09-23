#!/usr/bin/env python3
"""#572 offline geometry sweep — many bracket variants against REAL captured minute bars.

READ-ONLY, $0. Consumes CSVs captured ONCE from prod (capture-once-read-many);
makes no DB connection, no API calls, no writes anywhere but stdout.

Capture (run 2026-08-18 against prod via `docker exec apollo-postgres psql`; the
first four files are the 2026-08-18 #482 capture, reused unchanged):

  live_all.csv           — mi_live_trades, all non-pending rows
  adr.csv                — per (ticker, alert_date): mean 20-day (high-low)/close %
  minute_bars_cohort.csv — mi_intraday_bars for the 43 filled-magna53 tickers,
                           bar_time rendered in ET ("YYYY-MM-DD HH24:MI")
  daily_closes_cohort.csv— mi_daily_closes (date, o, h, l, c) for the same tickers
                           from 2026-02-17 (>=20 prior sessions for every cohort row)

COHORT (the denominator, stated): the 46 CLOSED, FILLED live magna53 trades.
Minute-resolution lanes run on the 30 of them with a FULL captured day-0 session
(first bar <=09:31, last >=15:45, >=300 bars); 11 have only the 09:30 ORB bar and
5 have no bars — both excluded and listed. This is the population the live system
ENTERED: names it skipped (gates) or that never alerted are NOT here, so the sweep
answers only "on the trades we took, would geometry X have done better" — it says
nothing about selectivity.

DESIGN — sim-vs-sim, not sim-vs-live: every lane (including the baseline bracket)
is replayed through ONE engine with ONE exit policy on the SAME bars, so the
head-to-head is free of the sim-vs-live optimism asymmetry that poisoned raw
comparisons before (#482 read, SYRE). Live realized R is printed as a REFERENCE
lane only, and B0-vs-live is printed as the calibration gap.

  Entry anchor for B0/A/C lanes = the REAL live fill (entry_price @ filled_at) —
  real entry fills, simulated exits. Lane W simulates its own entry (we never
  traded that way; no real fill exists).

UNIFORM EXIT POLICY (era-C-like management, applied identically to every lane):
  +2R partial (half) in the lane's OWN R unit -> stop to breakeven on remainder ->
  SMA10/20-max daily-close trail (prior closes seeded from a 40-calendar-day
  window, mirroring live_tracker/exit_path_shadow) -> max hold 20 trading days.
  Day 0 at minute resolution (stop-before-target inside a bar = conservative);
  days 1+ at daily resolution with GAP-AT-OPEN realism: open below stop fills at
  the OPEN, not the stop (the SYRE lesson — the #482 sim could not lose >1R).

LANES:
  LIVE — actual realized R (reference; era-mixed, real fills, real slippage)
  B0   — baseline: real entry, stop = 1-min ORB low                (the control)
  A    — variant (a): B0 + re-entry up to 2x after a FULL stop-out. Re-trigger =
         ORB-high re-break; day 0 on minute bars (cutoff 15:30), days 1-3 on
         daily bars. Re-entry stop = ORB low (original unit). Daily-resolution
         days cannot sequence intraday order, so re-entry lanes print a
         [conservative, optimistic] bracket — the modes differ ONLY in the
         genuinely ambiguous both-touched case (low<=stop AND high>=target,
         no partial yet): cons books the full stop, opt books partial+breakeven.
  Apdl — variant (a), operator's-INTC shape: same re-entry trigger, but a
         DAILY re-entry stops at the PRIOR session's low (the day-0 low as the
         day-1 invalidation line, per the structure model) instead of ORB low.
  W    — variant (b): wait-for-established-intraday-low. Session low that holds
         un-breached 30 minutes = established; arm buy-stop at the
         high-of-day-so-far; a NEW session low dis-arms and must re-establish;
         entry cutoff 15:00; stop = the established low.
  C05  — variant (c): real entry, stop = entry - 0.5*ATR14
  C10  — variant (c): real entry, stop = entry - 1.0*ATR14
  CPDL — variant (c): real entry, stop = prior session's low (structure anchor;
         the other structure anchor — the EP-day low — is lookahead at entry
         time and is NOT simulated)

UNITS: R = per-share pnl / the lane's OWN stop distance (each lane's own risk);
ADR units = per-share pnl / (that lane's entry * 20-day ADR%) — the common
denominator that lets lanes with different stop widths be compared honestly.

LIMIT, stated every time: an offline sweep cannot model fills. B0/A/C entries are
real fills but every EXIT here is simulated; lane W's entry is simulated too.
Offline gives breadth; only a live arm gives fill realism.

Usage: python3 scripts/probes/geometry_sweep_572.py --data-dir <dir>
"""

import argparse
import csv
import statistics as st
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bracket_geometry_read_482 import d, era_of, f, pctl  # noqa: E402

_ET = ZoneInfo("America/New_York")
_UTC = ZoneInfo("UTC")
MAX_HOLD = 20          # trading days, uniform time stop
REENTRY_MAX = 2        # additional attempts after the original
REENTRY_DAYS = 3       # daily-resolution re-entry window after day 0
DATA_END = date(2026, 8, 17)


# ── loading ──────────────────────────────────────────────────────────────────────


def load(data_dir: Path):
    live = list(csv.DictReader(open(data_dir / "live_all.csv")))
    adr = {(r["ticker"], r["alert_date"]): f(r["adr_pct"])
           for r in csv.DictReader(open(data_dir / "adr.csv"))
           if int(r["n_days"] or 0) >= 10}
    minute = {}
    for row in csv.reader(open(data_dir / "minute_bars_cohort.csv")):
        if len(row) != 7:
            continue
        t, bar_et = row[0], row[1]
        day, tm = bar_et.split(" ")
        minute.setdefault((t, day), []).append(
            (tm, float(row[2]), float(row[3]), float(row[4]), float(row[5])))
    for v in minute.values():
        v.sort()
    daily = {}
    for row in csv.reader(open(data_dir / "daily_closes_cohort.csv")):
        if len(row) != 6:
            continue
        daily.setdefault(row[0], []).append(
            (d(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5])))
    for v in daily.values():
        v.sort()
    return live, adr, minute, daily


def prior_closes(daily, ticker, alert_date):
    """Closes from the 40 calendar days strictly before alert_date, oldest-first —
    mirrors exit_path_shadow._fetch_prior_closes / live_tracker."""
    lo = alert_date - timedelta(days=40)
    return [c for (day, _o, _h, _l, c) in daily.get(ticker, [])
            if lo <= day < alert_date]


def sma_trail(closes):
    """MAX(SMA10, SMA20) — same formula as exit_path_shadow._sma_trail (itself
    byte-parity-pinned against broker/exit_logic)."""
    sma10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else None
    sma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
    if sma20 is not None:
        return sma10 if (sma10 is not None and sma10 > sma20) else sma20
    return sma10


def entry_minute_et(row):
    """live filled_at (UTC in the capture) -> ET HH:MM. Missing -> 09:31."""
    fa = (row.get("filled_at") or "").strip()
    if not fa:
        return "09:31"
    dt = datetime.fromisoformat(fa[:19]).replace(tzinfo=_UTC).astimezone(_ET)
    return dt.strftime("%H:%M")


# ── the one engine ───────────────────────────────────────────────────────────────


def simulate(entry_px, entry_tm, stop_px, ticker, alert_date, minute, daily,
             *, seq="cons", entry_day=None, skip_day0_minutes=False):
    """Replay one attempt under the uniform exit policy. Returns dict:
    pnl_ps (per-share P&L), r_unit, exit_day, exit_reason, partial_taken,
    stopped_full (full stop-out, no partial), stop_time (day-0 minute or None),
    horizon (True if closed by time/data stop).

    seq: daily-resolution intra-day ordering when both stop and target are
    touchable — "cons" checks the stop first, "opt" the target first.
    entry_day: the day the attempt fills (defaults to alert_date). Minute bars
    are only used when entry_day == alert_date and a session was captured.
    """
    entry_day = entry_day or alert_date
    r_unit = entry_px - stop_px
    if r_unit <= 0:
        return None
    target = entry_px + 2 * r_unit
    stop, partial, pnl = stop_px, False, 0.0
    size = 1.0  # per-share basis

    def done(fill, day, reason, tm=None, horizon=False):
        return dict(pnl_ps=pnl + size * (fill - entry_px), r_unit=r_unit,
                    exit_day=day, exit_reason=reason, partial_taken=partial,
                    stopped_full=(not partial and reason in
                                  ("hard_stop", "gap_open_stop")),
                    stop_time=tm, horizon=horizon)

    day0_minutes = (not skip_day0_minutes and entry_day == alert_date
                    and (ticker, alert_date.isoformat()) in minute)

    # day 0 at minute resolution
    if day0_minutes:
        for (tm, o, h, l, _c) in minute[(ticker, alert_date.isoformat())]:
            if tm < entry_tm:
                continue
            if l <= stop:  # stop before target inside a bar — conservative
                fill = o if o < stop else stop
                return done(fill, entry_day,
                            "breakeven_stop" if partial else "hard_stop", tm=tm)
            if not partial and h >= target:
                fill = max(o, target)
                pnl += 0.5 * (fill - entry_px)
                size, partial, stop = 0.5, True, entry_px
        # survived the session -> continue on dailies

    # daily resolution
    series = daily.get(ticker, [])
    closes = prior_closes(daily, ticker, entry_day)
    held = 0
    for (day, o, h, l, c) in series:
        if day < entry_day:
            continue
        if day == entry_day and day0_minutes:
            closes.append(c)   # day-0 already replayed at minute level
            continue
        first = (day == entry_day)
        # ordering: gap-at-open, then stop/target, then trail at close.
        # No gap check on the entry day itself — a within-day fill at
        # max(open, trigger) post-dates the open by construction.
        if not first and o <= stop:
            return done(o, day, "gap_open_be" if partial else "gap_open_stop")
        # Intraday order is unknowable at daily resolution. cons and opt differ
        # ONLY in the genuinely ambiguous case (low<=stop AND high>=target, no
        # partial yet): cons books the full stop, opt books partial+breakeven.
        # A post-partial low at/below breakeven ends the remainder in BOTH modes
        # (every ordering with the low after the high does; the low-first
        # ordering is the full stop, i.e. worse — so this IS the optimistic
        # branch of that pair, and the conservative one too once the ambiguous
        # case above is resolved).
        both = (not partial and l <= stop and h >= target)
        if both and seq == "cons":
            return done(stop, day, "hard_stop")
        if not partial and h >= target:
            fill = max(o, target)
            pnl += 0.5 * (fill - entry_px)
            size, partial, stop = 0.5, True, entry_px
            if l <= stop:
                return done(stop, day, "breakeven_stop")
        elif l <= stop:
            return done(stop, day, "breakeven_stop" if partial else "hard_stop")
        closes.append(c)
        trail = sma_trail(closes)
        if not first and trail is not None and c < trail:
            return done(c, day, "sma_trail")
        held += 1
        if held >= MAX_HOLD:
            return done(c, day, "time_stop", horizon=True)
    # ran off the end of data
    if series:
        return done(series[-1][4], series[-1][0], "data_end", horizon=True)
    return done(entry_px, entry_day, "data_end", horizon=True)


# ── lanes ────────────────────────────────────────────────────────────────────────


def lane_b0(row, minute, daily):
    entry, orb_low = f(row["entry_price"]), f(row["orb_low"])
    return simulate(entry, entry_minute_et(row), orb_low, row["ticker"],
                    d(row["alert_date"]), minute, daily)


def lane_reentry(row, minute, daily, seq, restop="orb"):
    """B0 plus up to REENTRY_MAX re-entries after FULL stop-outs.

    restop — the stop of a DAILY-resolution (next-day) re-entry:
      "orb" = the original 1-min ORB low (same R unit as the first attempt)
      "pdl" = the session low of the day BEFORE the re-entry day (the structure
              anchor; this is the shape of the operator's INTC example — the
              day-0 low becomes the invalidation line for a day-1 re-entry)
    Same-day re-entries always keep the ORB-low stop.
    """
    ticker, ad = row["ticker"], d(row["alert_date"])
    orb_high, orb_low = f(row["orb_high"]), f(row["orb_low"])
    attempts = [simulate(f(row["entry_price"]), entry_minute_et(row), orb_low,
                         ticker, ad, minute, daily, seq=seq)]
    while (len(attempts) <= REENTRY_MAX and attempts[-1]
           and attempts[-1]["stopped_full"]):
        prev = attempts[-1]
        nxt = None
        # same-day re-break of the ORB high on minute bars
        if prev["exit_day"] == ad and prev["stop_time"]:
            for (tm, o, h, _l, _c) in minute.get((ticker, ad.isoformat()), []):
                if tm <= prev["stop_time"] or tm > "15:30":
                    continue
                if h >= orb_high:
                    nxt = simulate(max(o, orb_high), tm, orb_low, ticker, ad,
                                   minute, daily, seq=seq)
                    break
        if nxt is None:
            # daily-resolution re-entry, next REENTRY_DAYS trading days
            series = [b for b in daily.get(ticker, []) if b[0] > prev["exit_day"]]
            for (day, o, h, _l, _c) in series[:REENTRY_DAYS]:
                if h >= orb_high:
                    stop_px = (prior_day_low(daily, ticker, day)
                               if restop == "pdl" else orb_low)
                    fill = max(o, orb_high)
                    if stop_px is None or stop_px >= fill:
                        break
                    nxt = simulate(fill, "09:30", stop_px, ticker, ad,
                                   minute, daily, seq=seq, entry_day=day,
                                   skip_day0_minutes=True)
                    break
        if nxt is None:
            break
        attempts.append(nxt)
    return [a for a in attempts if a]


def lane_wait_low(row, minute, daily, hold_min=30, cutoff="15:00"):
    """Established-low entry: session low un-breached hold_min minutes arms a
    buy-stop at the high-of-day-so-far; a new low dis-arms; stop = that low."""
    ticker, ad = row["ticker"], d(row["alert_date"])
    bars = minute.get((ticker, ad.isoformat()), [])
    if not bars:
        return None
    lo, lo_i, hod, armed, level = None, 0, None, False, None
    for i, (tm, o, h, l, _c) in enumerate(bars):
        hod = h if hod is None else max(hod, h)
        if lo is None or l < lo:
            lo, lo_i, armed = l, i, False  # a lower low dis-arms; re-establish
            continue
        if armed and tm <= cutoff and h >= level:
            entry = max(o, level)
            return simulate(entry, tm, lo, ticker, ad, minute, daily)
        if not armed and (i - lo_i) >= hold_min and tm <= cutoff:
            armed, level = True, hod
    return "no_entry"


def lane_stop_variant(row, minute, daily, stop_px):
    entry = f(row["entry_price"])
    if stop_px is None or stop_px >= entry:
        return None
    return simulate(entry, entry_minute_et(row), stop_px, row["ticker"],
                    d(row["alert_date"]), minute, daily)


def prior_day_low(daily, ticker, alert_date):
    prev = [b for b in daily.get(ticker, []) if b[0] < alert_date]
    return prev[-1][3] if prev else None


# ── reporting ────────────────────────────────────────────────────────────────────


def stats_line(label, vals):
    n = len(vals)
    if n == 0:
        return f"  {label:<34} n=0 — not readable"
    if n < 4:
        return (f"  {label:<34} n={n} — not readable "
                f"(raw: {', '.join(f'{v:+.2f}' for v in sorted(vals))})")
    wins = sum(1 for v in vals if v > 0)
    return (f"  {label:<34} n={n:<3} sum={sum(vals):+8.2f} med={st.median(vals):+6.2f} "
            f"mean={st.fmean(vals):+6.2f} p90={pctl(vals, 90):+6.2f} "
            f"max={max(vals):+6.2f} win={wins}/{n} "
            f">=+1:{sum(1 for v in vals if v >= 1)} >=+2:{sum(1 for v in vals if v >= 2)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    args = ap.parse_args()
    data_dir = Path(args.data_dir)
    live, adr, minute, daily = load(data_dir)

    m53 = [r for r in live if r["signal_type"] == "magna53"
           and r["status"] == "closed" and r["entry_price"]]
    full, thin, none = [], [], []
    for r in m53:
        bars = minute.get((r["ticker"], r["alert_date"]), [])
        times = [b[0] for b in bars]
        if not times:
            none.append(r)
        elif min(times) <= "09:31" and max(times) >= "15:45" and len(times) >= 300:
            full.append(r)
        else:
            thin.append(r)

    print("=" * 104)
    print("#572 OFFLINE GEOMETRY SWEEP — re-entry / established-low / ATR+structure "
          "stops vs the live 1-min bracket")
    print("=" * 104)
    print(f"DENOMINATOR: {len(m53)} closed FILLED live magna53 trades. Minute-resolution "
          f"sweep runs on the {len(full)} with a full captured day-0 session; "
          f"{len(thin)} have only the 09:30 ORB bar and {len(none)} have no bars "
          f"(all excluded, listed below). Names the live system SKIPPED are not in "
          f"this cohort at all — this sweep measures geometry on trades TAKEN, "
          f"not selectivity.")
    print(f"  excluded (ORB-bar only): "
          f"{', '.join(r['ticker'] + ' ' + r['alert_date'] for r in thin)}")
    print(f"  excluded (no bars):      "
          f"{', '.join(r['ticker'] + ' ' + r['alert_date'] for r in none)}")
    eras = sorted(era_of(d(r["alert_date"])) for r in full)
    print(f"  era mix of the {len(full)}: "
          f"A={eras.count('A')} B={eras.count('B')} C={eras.count('C')} "
          f"(era = live-side exit-rule regime at alert time; the SIM applies ONE "
          f"uniform era-C-like policy to every lane, so era is a robustness slice "
          f"here, not a correction)")
    print(f"FILL LIMIT (state it every time): B0/A/C lanes use the REAL live entry "
          f"fill; every EXIT is simulated; lane W's entry is simulated too. "
          f"Daily-resolution days use gap-at-open stop fills (open below stop "
          f"fills at the open), so worse-than-full losses ARE expressible.")

    # per-row lane results
    results = {}  # lane -> list of (row, res)
    lanes_meta = [
        ("B0", "baseline sim: real entry, ORB-low stop"),
        ("A_cons", "re-entry <=2x, ORB-low stop (cons seq)"),
        ("A_opt", "re-entry <=2x, ORB-low stop (opt seq)"),
        ("Apdl_c", "re-entry <=2x, prior-day-low stop (cons)"),
        ("Apdl_o", "re-entry <=2x, prior-day-low stop (opt)"),
        ("W", "established-low entry (30-min low, HOD trigger)"),
        ("C05", "stop = entry - 0.5*ATR14"),
        ("C10", "stop = entry - 1.0*ATR14"),
        ("CPDL", "stop = prior day's low"),
    ]
    w_no_entry, cpdl_invalid = [], []
    for r in full:
        key = (r["ticker"], r["alert_date"])
        entry, atr = f(r["entry_price"]), f(r["atr_14"])
        results.setdefault("B0", []).append((r, [lane_b0(r, minute, daily)]))
        results.setdefault("A_cons", []).append((r, lane_reentry(r, minute, daily, "cons")))
        results.setdefault("A_opt", []).append((r, lane_reentry(r, minute, daily, "opt")))
        results.setdefault("Apdl_c", []).append((r, lane_reentry(r, minute, daily, "cons", restop="pdl")))
        results.setdefault("Apdl_o", []).append((r, lane_reentry(r, minute, daily, "opt", restop="pdl")))
        w = lane_wait_low(r, minute, daily)
        if w == "no_entry" or w is None:
            w_no_entry.append(key)
            results.setdefault("W", []).append((r, []))
        else:
            results.setdefault("W", []).append((r, [w]))
        results.setdefault("C05", []).append((r, [lane_stop_variant(r, minute, daily, entry - 0.5 * atr)]))
        results.setdefault("C10", []).append((r, [lane_stop_variant(r, minute, daily, entry - 1.0 * atr)]))
        pdl = prior_day_low(daily, r["ticker"], d(r["alert_date"]))
        res = lane_stop_variant(r, minute, daily, pdl)
        if res is None:
            cpdl_invalid.append(key)
        results.setdefault("CPDL", []).append((r, [res] if res else []))

    def rollup(row, attempts):
        """One name-day in one lane -> (R, adr_units, aux). R = total per-share
        pnl / the FIRST attempt's own stop distance; ADR = pnl / entry*ADR%."""
        if not attempts or attempts[0] is None:
            return None
        pnl = sum(a["pnl_ps"] for a in attempts)
        r_unit = attempts[0]["r_unit"]
        adr_pct = adr.get((row["ticker"], row["alert_date"]))
        entry = f(row["entry_price"])
        return dict(
            r=pnl / r_unit, pnl_ps=pnl,
            adr_u=(pnl / (entry * adr_pct / 100)) if adr_pct else None,
            n_attempts=len(attempts),
            partial=any(a["partial_taken"] for a in attempts),
            horizon=any(a["horizon"] for a in attempts),
            stop_pct=100 * r_unit / entry)

    # live reference on the same 30
    live_ref = []
    for r in full:
        pnl, shares = f(r["total_pnl"]), f(r["entry_shares"])
        entry, orb_low, hard = f(r["entry_price"]), f(r["orb_low"]), f(r["hard_stop"])
        unit = entry - (orb_low if orb_low else hard)
        if pnl is not None and shares and unit > 0:
            adr_pct = adr.get((r["ticker"], r["alert_date"]))
            live_ref.append((r, dict(r=(pnl / shares) / unit,
                                     adr_u=(pnl / shares) / (entry * adr_pct / 100) if adr_pct else None,
                                     stop_pct=100 * unit / entry)))

    # ── calibration: B0 sim vs live realized on identical trades ────────────────
    print()
    print("-" * 104)
    print("1. CALIBRATION — B0 (baseline SIM, uniform policy) vs LIVE realized on the "
          "SAME trades, same entries")
    print("   The gap = simulated-exit optimism + era-A/B live rules differing from "
          "the uniform sim policy. Every")
    print("   variant below is judged against B0, never against live, so this gap "
          "does not contaminate the verdict.")
    print("-" * 104)
    b0_by_key = {(r["ticker"], r["alert_date"]): rollup(r, a) for r, a in results["B0"]}
    deltas = []
    for r, ref in live_ref:
        b = b0_by_key.get((r["ticker"], r["alert_date"]))
        if b:
            deltas.append(b["r"] - ref["r"])
    print(stats_line("LIVE realized R (reference)", [x["r"] for _, x in live_ref]))
    print(stats_line("B0 sim R (same trades)", [v["r"] for v in b0_by_key.values() if v]))
    print(f"  per-trade (B0 sim - live) R: sum {sum(deltas):+.2f}  "
          f"median {st.median(deltas):+.2f}  (n={len(deltas)})")

    # ── the sweep tables ────────────────────────────────────────────────────────
    for unit, label in (("r", "realized R (each lane's OWN stop unit)"),
                        ("adr_u", "ADR units (per-share pnl / entry * 20d-ADR — "
                                  "common denominator across lanes)")):
        print()
        print("-" * 104)
        print(f"2. SWEEP — {label}")
        print("-" * 104)
        for lane, desc in lanes_meta:
            rolled = [rollup(r, a) for r, a in results[lane]]
            vals = [x[unit] for x in rolled if x and x[unit] is not None]
            print(stats_line(f"{lane:<7} {desc}", vals))
        print(stats_line("LIVE    realized (reference, era-mixed)",
                         [x[unit] for _, x in live_ref if x.get(unit) is not None]))

    # ── paired vs B0 ────────────────────────────────────────────────────────────
    print()
    print("-" * 104)
    print("3. PAIRED vs B0 (sim-vs-sim, same name-days) — dR and dADR per pair; "
          "|d|<=0.05 = tie")
    print("-" * 104)
    for lane, desc in lanes_meta[1:]:
        drs, dadrs = [], []
        for r, a in results[lane]:
            v, b = rollup(r, a), b0_by_key.get((r["ticker"], r["alert_date"]))
            if v and b:
                drs.append(v["r"] - b["r"])
                if v["adr_u"] is not None and b["adr_u"] is not None:
                    dadrs.append(v["adr_u"] - b["adr_u"])
        if not drs:
            print(f"  {lane:<7} no pairs")
            continue
        bet = sum(1 for x in drs if x > 0.05)
        wor = sum(1 for x in drs if x < -0.05)
        print(f"  {lane:<7} n={len(drs):<3} dR sum {sum(drs):+8.2f} med {st.median(drs):+6.2f} | "
              f"dADR sum {sum(dadrs):+8.2f} med {st.median(dadrs):+6.2f} | "
              f"better {bet} / worse {wor} / tied {len(drs) - bet - wor}")

    # W as a PORTFOLIO over all name-days: a no-entry day scores 0 (it did not
    # trade), against B0's realized R on those same days. This is the honest
    # read of W-as-discipline: most of its effect is the days it DECLINES.
    w_port, b0_port, declined_b0 = [], [], []
    w_adr, b0_adr, declined_b0_adr = [], [], []
    for r, a in results["W"]:
        b = b0_by_key.get((r["ticker"], r["alert_date"]))
        if not b:
            continue
        v = rollup(r, a)
        w_port.append(v["r"] if v else 0.0)
        b0_port.append(b["r"])
        if b["adr_u"] is not None:
            w_adr.append(v["adr_u"] if v and v["adr_u"] is not None else 0.0)
            b0_adr.append(b["adr_u"])
        if not v:
            declined_b0.append(b["r"])
            if b["adr_u"] is not None:
                declined_b0_adr.append(b["adr_u"])
    print(f"\n  W PORTFOLIO (no-entry = 0) over the same {len(b0_port)} name-days:")
    print(f"    R units:   B0 sum {sum(b0_port):+.2f}  vs  W sum {sum(w_port):+.2f}   "
          f"(B0 on the {len(declined_b0)} days W declined: sum "
          f"{sum(declined_b0):+.2f}, {sum(1 for x in declined_b0 if x < 0)} losers)")
    print(f"    ADR units: B0 sum {sum(b0_adr):+.2f}  vs  W sum {sum(w_adr):+.2f}   "
          f"(B0 on declined days: {sum(declined_b0_adr):+.2f}) — the R-unit view "
          f"flatters W (its wider stops shrink R multiples); ADR is the leveller.")
    print(f"    NOTE: the 0 days make this a discipline read, not a pure geometry "
          f"read — the established-low CONDITION is doing selectivity work.")

    # ── mechanism 5 ─────────────────────────────────────────────────────────────
    print()
    print("-" * 104)
    print("4. MECHANISM 5 — the wider R unit vs the +2R partial (per lane: partial "
          "fired within the sim; and pairs where B0's partial fired but the lane's never)")
    print("-" * 104)
    b0_partial = {(r["ticker"], r["alert_date"]): (v["partial"] if (v := rollup(r, a)) else None)
                  for r, a in results["B0"]}
    for lane, desc in lanes_meta:
        rolled = [(r, rollup(r, a)) for r, a in results[lane]]
        have = [(r, v) for r, v in rolled if v]
        fired = sum(1 for _, v in have if v["partial"])
        destroyed = [r["ticker"] + " " + r["alert_date"] for r, v in have
                     if not v["partial"] and b0_partial.get((r["ticker"], r["alert_date"]))]
        med_stop = st.median(v["stop_pct"] for _, v in have) if have else 0
        print(f"  {lane:<7} partial fired {fired}/{len(have)}  "
              f"median stop width {med_stop:4.1f}% of entry  "
              f"B0-partial-but-not-here: {len(destroyed)}"
              + (f"  ({', '.join(destroyed)})" if destroyed and lane != 'B0' else ""))

    # ── lane-specific notes ─────────────────────────────────────────────────────
    print()
    print("-" * 104)
    print("5. LANE NOTES")
    print("-" * 104)
    re_extra = [(r["ticker"], r["alert_date"], len(a)) for r, a in results["A_cons"] if len(a) > 1]
    print(f"  A: re-entry triggered on {len(re_extra)}/{len(full)} name-days "
          f"(attempts>1): {', '.join(f'{t} {d0}({n})' for t, d0, n in re_extra)}")
    for tag in ("A_cons", "A_opt", "Apdl_c", "Apdl_o"):
        re_only = []
        for r, a in results[tag]:
            if len(a) > 1:
                extra = sum(x["pnl_ps"] for x in a[1:])
                re_only.append((r["ticker"], extra / a[0]["r_unit"]))
        print(f"     {tag}: R from re-entry attempts alone (first-attempt unit): "
              f"{', '.join(f'{t} {v:+.2f}' for t, v in re_only) or 'none'} "
              f"(sum {sum(v for _, v in re_only):+.2f})")
    print(f"  W: no qualifying entry on {len(w_no_entry)}/{len(full)} name-days "
          f"({', '.join(t + ' ' + d0 for t, d0 in w_no_entry) or 'none'})")
    print(f"  CPDL: prior-day-low above entry (uninvestable) on "
          f"{len(cpdl_invalid)} name-days: "
          f"{', '.join(t + ' ' + d0 for t, d0 in cpdl_invalid) or 'none'}")
    odd = [(r["ticker"], r["alert_date"]) for r in full
           if f(r["entry_price"]) <= f(r["orb_low"] or 0)]
    print(f"  ORB-anchored lanes (B0/A): rows dropped because the REAL fill was at "
          f"or below the ORB low (r-unit <=0, an odd live fill): "
          f"{', '.join(t + ' ' + d0 for t, d0 in odd) or 'none'}")
    horizon_ct = {lane: sum(1 for r, a in results[lane] if (v := rollup(r, a)) and v["horizon"])
                  for lane, _ in lanes_meta}
    print(f"  positions still open at the 20-day/data horizon (marked to last "
          f"close): {horizon_ct}")

    # era slices, R unit, primary lanes only
    print()
    print("-" * 104)
    print("6. ERA SLICES (R unit; sim policy is uniform — this checks the verdict "
          "isn't carried by one regime)")
    print("-" * 104)
    for era in ("A", "B"):
        print(f"  era {era}:")
        for lane, _ in lanes_meta:
            rolled = [rollup(r, a) for r, a in results[lane]
                      if era_of(d(r["alert_date"])) == era]
            vals = [x["r"] for x in rolled if x]
            print(stats_line(f"  {lane}", vals))

    print()
    print("=" * 104)
    print("END OF PROBE OUTPUT — interpretation lives in "
          "docs/analysis/geometry_sweep_572_2026-08-18.md")
    print("=" * 104)


if __name__ == "__main__":
    main()
