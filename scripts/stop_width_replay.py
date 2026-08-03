#!/usr/bin/env python3
"""Stop-width replay — would a WIDER stop have produced a better result on EP trades?

READ-ONLY EVIDENCE probe (2026-08-03). Changes nothing; the output feeds
docs/analysis/stop_width_replay_2026-08-03.md. Any stop-geometry change is a criteria
change: operator sign-off + CHANGE_PROCESS + N>=10 backtest required before anything here
touches live behaviour.

Question: current MAGNA53 EP stop = ORB low (entry = stop-limit buy at ORB high).
Operator suspicion: that stop sits at ~half a typical day's range, so ordinary morning
noise stops us out of trades that later work.

DESIGN (the three constraints that make the answer trustworthy):
  1. RISK HELD CONSTANT — every variant is scored in R-multiples of ITS OWN stop
     distance (risk budget / distance = shares), so "wider stop" never degenerates
     into "bigger bet". A full stop-out is -1R under EVERY variant.
  2. BOTH ARMS ALWAYS — for every width: how many baseline losers are RESCUED and
     where they END (day-0 close, day-5 settle), and how much surviving winners
     SHRINK in R (same price move / bigger denominator).
  3. COHORTS NEVER MERGED — A = real closed trades with full entry-day minute bars
     (what actually happened); B = distinct HIGH alerts replayed as simulated ORB
     entries (bigger N, weaker evidence about live behaviour).

MECHANICS (identical for every variant — apples to apples):
  Entry: cohort A = actual entry_price at the bar containing filled_at
         (fallback: first 9:31-9:45 bar whose high >= entry_price).
         cohort B = ORB high, triggered by the first 9:31-9:44 ET bar whose
         high >= ORB high (live submission window: minute < 45); no trigger = no trade.
         ORB = the 9:30 ET 1-minute bar (matches live + orb_sim_filtered_candidates).
  Stop walk, day 0 (minute bars): a stop counts as FILLED when a bar's LOW touches it
         (bar-low touch, tick sequence unknown — the conservative assumption for the
         wider-stop case: wide stops get stopped as often as the data allows).
         Fill price = stop, or the bar OPEN when the bar opens through the stop.
         Entry-bar ambiguity resolved pessimistically (stop-first).
  Day-0 settle: not stopped -> exit at the last RTH bar close.
  Day-5 settle: survivors walk daily bars day1..day5: open <= stop -> fill at OPEN
         (gap-through — you do NOT get the stop price), low <= stop -> fill at stop,
         else day-5 close. No profit-taking rule in either arm (stated in the doc).
  R = (exit - entry) / (entry - stop_variant).

VARIANTS (stop below entry):
  orb_1.0x (BASELINE = current geometry: stop = ORB low; D0 = entry - ORB low)
  orb_1.25x / 1.5x / 2.0x : stop = entry - k*D0
  atr_0.5 / 0.75 / 1.0    : stop = entry - m*ATR14 (cohort A: the recorded atr_14 the
                            live sizing used; cohort B: mean of last 14 Wilder TRs from
                            mi_daily_closes STRICTLY BEFORE alert day — what the 9:31
                            live path can see)
  pdl                     : stop = prior day's low (can be tighter OR wider; the 9M
                            geometry). Skipped when >= entry.
Every variant row is compared PAIRED against the baseline on the SAME subset of trades,
so ATR/PDL skips can't tilt the totals.

Inputs (pulled 2026-08-03 from prod, gitignored):
  scripts/_stopw_trades.tsv  46 closed mi_live_trades rows
  scripts/_stopw_alerts.tsv  327 distinct (ticker, alert_date) HIGH mi_ep_alerts
  scripts/_stopw_minute.tsv  all RTH mi_intraday_bars rows (ticker|date|HH:MM|o|h|l|c, ET)
  scripts/_stopw_daily.tsv   mi_daily_closes OHLC for cohort tickers since 2026-02-15

Run:  python scripts/stop_width_replay.py
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
_ET = ZoneInfo("America/New_York")

TRADES = HERE / "_stopw_trades.tsv"
ALERTS = HERE / "_stopw_alerts.tsv"
MINUTE = HERE / "_stopw_minute.tsv"
DAILY = HERE / "_stopw_daily.tsv"

FWD_DAYS = 5                      # extension horizon (matches _327 SETTLE_FORWARD_BARS)
SUBMIT_LAST_MIN = "09:44"         # live window: hour==9 and minute<45
CLOSE_MIN = "15:55"               # a day needs a bar at/after this to have a real close


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ── loaders ──────────────────────────────────────────────────────────────────
def load_minute():
    by = defaultdict(list)
    for ln in MINUTE.read_text().splitlines():
        p = ln.split("|")
        if len(p) < 7:
            continue
        by[(p[0], p[1])].append(
            {"t": p[2], "o": _f(p[3]), "h": _f(p[4]), "l": _f(p[5]), "c": _f(p[6])})
    for k in by:
        by[k].sort(key=lambda b: b["t"])
    return by


def load_daily():
    by = defaultdict(list)
    for ln in DAILY.read_text().splitlines():
        p = ln.split("|")
        if len(p) < 6:
            continue
        by[p[0]].append({"d": p[1], "o": _f(p[2]), "h": _f(p[3]),
                         "l": _f(p[4]), "c": _f(p[5])})
    for k in by:
        by[k].sort(key=lambda b: b["d"])
    return by


def load_trades():
    out = []
    for ln in TRADES.read_text().splitlines():
        p = ln.split("|")
        if len(p) < 17:
            continue
        out.append({"mode": p[0], "ticker": p[1], "date": p[2], "filled_at": p[3],
                    "entry": _f(p[4]), "stop_rec": _f(p[5]), "shares": _f(p[6]),
                    "atr": _f(p[7]) or None, "orb_h": _f(p[8]), "orb_l": _f(p[9]),
                    "risk": _f(p[10]), "pnl": _f(p[11]), "sig": p[12]})
    return out


def load_alerts():
    out = []
    for ln in ALERTS.read_text().splitlines():
        p = ln.split("|")
        if len(p) < 4:
            continue
        out.append({"ticker": p[0], "date": p[1], "score": _f(p[2]), "gap": _f(p[3])})
    return out


# ── daily-bar helpers ────────────────────────────────────────────────────────
def prior_day_low(daily, ticker, date):
    prev = [b for b in daily.get(ticker, []) if b["d"] < date and b["l"] is not None]
    return prev[-1]["l"] if prev else None


def atr14_prior(daily, ticker, date):
    """Mean of the last 14 Wilder TRs using bars STRICTLY BEFORE `date`
    (what the 9:31 live path can see — compute_atr_14's live asymmetry note)."""
    bars = [b for b in daily.get(ticker, []) if b["d"] < date]
    if len(bars) < 15:
        return None
    trs = []
    for i in range(1, len(bars)):
        h, low, pc = bars[i]["h"], bars[i]["l"], bars[i - 1]["c"]
        if None in (h, low, pc):
            continue
        trs.append(max(h - low, abs(h - pc), abs(low - pc)))
    return statistics.fmean(trs[-14:]) if len(trs) >= 14 else None


def forward_days(daily, ticker, date, n=FWD_DAYS):
    return [b for b in daily.get(ticker, []) if b["d"] > date][:n]


# ── the replay core (identical mechanics for every variant) ──────────────────
def walk(bars, entry_idx, entry, stop, fwd):
    """Replay one trade under one stop level. Returns dict:
      d0_stopped, d0_exit, d0_time  (day-0 settle: stop fill or last-bar close)
      d5_stopped, d5_exit, d5_day   (day-5 settle for day-0 survivors; day counts
                                     1..5, day 0 if stopped intraday)
      truncated (fewer than FWD_DAYS forward daily bars existed)"""
    r = {"d0_stopped": False, "d0_exit": None, "d0_time": None,
         "d5_stopped": False, "d5_exit": None, "d5_day": None, "truncated": False}
    for i in range(entry_idx, len(bars)):
        b = bars[i]
        if b["l"] is None:
            continue
        if i > entry_idx and b["o"] is not None and b["o"] <= stop:
            fill = b["o"]                       # minute bar OPENS through the stop
        elif b["l"] <= stop:
            fill = stop                         # bar-low touch (entry bar: pessimistic)
        else:
            continue
        r.update(d0_stopped=True, d0_exit=fill, d0_time=b["t"],
                 d5_stopped=True, d5_exit=fill, d5_day=0)
        return r
    r["d0_exit"] = bars[-1]["c"]                # day-0 close settle
    # extension: day 1..FWD_DAYS on daily bars
    if len(fwd) < FWD_DAYS:
        r["truncated"] = True
    exit_px, stopped, day = (fwd[-1]["c"] if fwd else bars[-1]["c"]), False, None
    for di, b in enumerate(fwd, start=1):
        if b["o"] is not None and b["o"] <= stop:
            exit_px, stopped, day = b["o"], True, di      # overnight gap-through: get the OPEN
            break
        if b["l"] is not None and b["l"] <= stop:
            exit_px, stopped, day = stop, True, di
            break
    r.update(d5_stopped=stopped, d5_exit=exit_px, d5_day=day)
    return r


VARIANTS = [("orb_1.0x", "orb", 1.0), ("orb_1.25x", "orb", 1.25),
            ("orb_1.5x", "orb", 1.5), ("orb_2.0x", "orb", 2.0),
            ("atr_0.5", "atr", 0.5), ("atr_0.75", "atr", 0.75),
            ("atr_1.0", "atr", 1.0), ("pdl", "pdl", None)]


def stop_for(variant, entry, d0, atr, pdl):
    name, kind, k = variant
    if kind == "orb":
        return entry - k * d0
    if kind == "atr":
        return None if atr is None else entry - k * atr
    return pdl if (pdl is not None and pdl < entry) else None


def replay_trade(bars, entry_idx, entry, orb_l, atr, pdl, fwd):
    """All variants for one trade. Returns {variant: result} for variants with a
    valid stop (0 < stop < entry)."""
    d0 = entry - orb_l
    if d0 <= 0:
        return None
    out = {}
    for v in VARIANTS:
        stop = stop_for(v, entry, d0, atr, pdl)
        if stop is None or stop <= 0 or stop >= entry:
            continue
        res = walk(bars, entry_idx, entry, stop, fwd)
        dist = entry - stop
        res.update(stop=stop, dist=dist, dist_pct=100 * dist / entry,
                   r0=(res["d0_exit"] - entry) / dist,
                   r5=(res["d5_exit"] - entry) / dist)
        out[v[0]] = res
    return out


# ── cohort builders ──────────────────────────────────────────────────────────
def session_ok(bars):
    return bool(bars) and bars[0]["t"] == "09:30" and bars[-1]["t"] >= CLOSE_MIN


def build_cohort_a(trades, minute, daily):
    rows, excl = [], defaultdict(int)
    for t in trades:
        bars = minute.get((t["ticker"], t["date"]))
        if not bars or len(bars) < 100:
            excl["no/partial minute bars on entry day"] += 1
            continue
        if not session_ok(bars):
            excl["session missing 9:30 ORB bar or close"] += 1
            continue
        if t["entry"] is None or t["orb_l"] is None or t["entry"] - t["orb_l"] <= 0:
            excl["entry <= ORB low (unreplayable geometry)"] += 1
            continue
        # entry bar: the bar containing filled_at (ET), else first bar whose high >= entry
        entry_idx = None
        if t["filled_at"]:
            ts = datetime.fromisoformat(t["filled_at"].replace(" ", "T"))
            ts = ts.astimezone(_ET) if ts.tzinfo else ts.replace(tzinfo=timezone.utc).astimezone(_ET)
            hhmm = ts.strftime("%H:%M")
            entry_idx = next((i for i, b in enumerate(bars) if b["t"] >= hhmm), None)
        if entry_idx is None:
            entry_idx = next((i for i, b in enumerate(bars)
                              if b["t"] >= "09:31" and b["h"] is not None
                              and b["h"] >= t["entry"]), None)
        if entry_idx is None:
            excl["no locatable entry bar"] += 1
            continue
        res = replay_trade(bars, entry_idx, t["entry"], t["orb_l"], t["atr"],
                           prior_day_low(daily, t["ticker"], t["date"]),
                           forward_days(daily, t["ticker"], t["date"]))
        if not res or "orb_1.0x" not in res:
            excl["baseline unreplayable"] += 1
            continue
        rows.append({**t, "res": res,
                     "actual_r": (t["pnl"] / t["risk"]) if t["risk"] else None})
    return rows, excl


def build_cohort_b(alerts, minute, daily, trade_keys):
    rows, excl = [], defaultdict(int)
    n_overlap = 0
    for a in alerts:
        key = (a["ticker"], a["date"])
        if key in trade_keys:
            n_overlap += 1                      # counted, NOT excluded (noted in doc)
        bars = minute.get(key)
        if not bars:
            excl["no minute bars"] += 1
            continue
        if not session_ok(bars):
            excl["missing 9:30 ORB bar or close (partial capture)"] += 1
            continue
        orb = bars[0]
        orb_h, orb_l = orb["h"], orb["l"]
        if orb_h is None or orb_l is None or orb_h - orb_l <= 0:
            excl["degenerate ORB (zero range)"] += 1
            continue
        entry_idx = next((i for i, b in enumerate(bars)
                          if "09:31" <= b["t"] <= SUBMIT_LAST_MIN
                          and b["h"] is not None and b["h"] >= orb_h), None)
        if entry_idx is None:
            excl["never triggered in 9:31-9:44 window"] += 1
            continue
        res = replay_trade(bars, entry_idx, orb_h, orb_l,
                           atr14_prior(daily, a["ticker"], a["date"]),
                           prior_day_low(daily, a["ticker"], a["date"]),
                           forward_days(daily, a["ticker"], a["date"]))
        if not res or "orb_1.0x" not in res:
            excl["baseline unreplayable"] += 1
            continue
        rows.append({**a, "entry": orb_h, "res": res})
    return rows, excl, n_overlap


# ── reporting ────────────────────────────────────────────────────────────────
def _med(xs):
    return statistics.median(xs) if xs else float("nan")


def sweep_table(rows, label):
    print(f"\n{'=' * 100}\nSWEEP — {label}  (N={len(rows)} replayed entries)\n{'=' * 100}")
    base_all = {id(r): r["res"]["orb_1.0x"] for r in rows}
    for horizon, rk, sk in (("DAY-0 settle (intraday only)", "r0", "d0_stopped"),
                            (f"DAY-{FWD_DAYS} settle (daily-bar extension, gap-through honest)",
                             "r5", "d5_stopped")):
        print(f"\n--- {horizon} ---")
        hdr = (f"{'variant':<10} {'n':>3} {'medDist%':>8} {'stopped':>7} "
               f"{'rescued':>7} {'rescEndR':>8} {'shrink':>6} "
               f"{'win%':>5} {'medR':>6} {'meanR':>7} {'totR':>7} {'baseTotR':>8} {'dTotR':>7}")
        print(hdr)
        print("-" * len(hdr))
        for vname, _k, _m in VARIANTS:
            sub = [r for r in rows if vname in r["res"]]
            if not sub:
                continue
            v = [r["res"][vname] for r in sub]
            b = [base_all[id(r)] for r in sub]
            n = len(sub)
            stopped = sum(1 for x in v if x[sk])
            rescued = [x[rk] for x, y in zip(v, b) if y[sk] and not x[sk]]
            # winners surviving under BOTH stops: R shrink factor = base dist / var dist
            shrink = [y["dist"] / x["dist"] for x, y in zip(v, b)
                      if not y[sk] and not x[sk]]
            rs = [x[rk] for x in v]
            brs = [y[rk] for y in b]
            print(f"{vname:<10} {n:>3} {_med([x['dist_pct'] for x in v]):>8.1f} "
                  f"{stopped:>7} {len(rescued):>7} "
                  f"{(_med(rescued) if rescued else float('nan')):>8.2f} "
                  f"{(_med(shrink) if shrink else float('nan')):>6.2f} "
                  f"{100 * sum(1 for x in rs if x > 0) / n:>4.0f}% "
                  f"{_med(rs):>6.2f} {statistics.fmean(rs):>7.2f} {sum(rs):>7.1f} "
                  f"{sum(brs):>8.1f} {sum(rs) - sum(brs):>+7.1f}")
        print("  rescued = baseline stopped at this horizon, variant not; rescEndR = the")
        print("  rescued trades' MEDIAN end R (in the variant's own R units).")
        print("  shrink = base/variant stop distance on trades BOTH survive (winner R divides by it).")
        print("  dTotR = variant total R minus BASELINE total R on the SAME subset (paired).")


def rescue_detail(rows, label, vname="orb_2.0x"):
    print(f"\nRESCUE ROSTER — {label} — {vname} vs baseline (day-0 horizon)")
    for r in rows:
        if vname not in r["res"]:
            continue
        v, b = r["res"][vname], r["res"]["orb_1.0x"]
        if b["d0_stopped"] and not v["d0_stopped"]:
            print(f"  {r['ticker']:<6} {r['date']}  base stopped {b['d0_time']}  "
                  f"-> {vname}: day0 {v['r0']:+.2f}R, day{FWD_DAYS} {v['r5']:+.2f}R"
                  f"{' [truncated fwd]' if v['truncated'] else ''}"
                  f"{'  (later stopped day ' + str(v['d5_day']) + ')' if v['d5_stopped'] else ''}")


def stop_time_hist(rows, label):
    times = [r["res"]["orb_1.0x"]["d0_time"] for r in rows
             if r["res"]["orb_1.0x"]["d0_stopped"]]
    if not times:
        return
    buckets = defaultdict(int)
    for t in times:
        h, m = int(t[:2]), int(t[3:5])
        mins = h * 60 + m - (9 * 60 + 30)
        buckets["<30min" if mins < 30 else "30-60" if mins < 60 else
                "60-120" if mins < 120 else ">120min"] += 1
    total = len(times)
    parts = "  ".join(f"{k} {buckets[k]} ({100*buckets[k]/total:.0f}%)"
                      for k in ["<30min", "30-60", "60-120", ">120min"] if k in buckets)
    print(f"\nBASELINE day-0 stop-out timing — {label}: n={total}  {parts}")


def main():
    minute, daily = load_minute(), load_daily()
    trades, alerts = load_trades(), load_alerts()
    closed_keys = {(t["ticker"], t["date"]) for t in trades}

    print("STOP-WIDTH REPLAY — evidence only; no live change is authorised by this output.")
    print(f"data: {len(trades)} closed trades | {len(alerts)} distinct HIGH alert-days | "
          f"{sum(len(v) for v in minute.values())} RTH minute bars | "
          f"{sum(len(v) for v in daily.values())} daily bars")

    # ---- cohort A: real closed trades ----
    a_rows, a_excl = build_cohort_a(trades, minute, daily)
    live = [r for r in a_rows if r["mode"] == "live"]
    paper = [r for r in a_rows if r["mode"] == "paper"]
    print(f"\nCOHORT A — real closed trades replayable: {len(a_rows)} "
          f"({len(live)} live + {len(paper)} paper) of {len(trades)} closed")
    for k, v in sorted(a_excl.items()):
        print(f"  excluded: {v:>2}  {k}")
    sigs = {r["sig"] for r in a_rows}
    print(f"  signal types in replayable set: {sigs}")

    # ORB fidelity check: stored orb_high/low vs the 9:30 bar in mi_intraday_bars
    print("\nORB fidelity (stored trade ORB vs 9:30 bar), mismatches > 1c:")
    n_mismatch = 0
    for r in a_rows:
        b0 = minute[(r["ticker"], r["date"])][0]
        dh, dl = abs((r["orb_h"] or 0) - (b0["h"] or 0)), abs((r["orb_l"] or 0) - (b0["l"] or 0))
        if dh > 0.011 or dl > 0.011:
            n_mismatch += 1
            print(f"  {r['ticker']:<6} {r['date']}  stored {r['orb_h']}/{r['orb_l']} "
                  f"vs bar {b0['h']}/{b0['l']}")
    if not n_mismatch:
        print("  none — stored ORB matches the 9:30 bar on every replayable trade")

    # operator suspicion: current stop distance as a fraction of ATR14
    fr = [(r["entry"] - r["orb_l"]) / r["atr"] for r in a_rows if r["atr"]]
    print(f"\nOperator suspicion check — current stop distance / ATR14, cohort A: "
          f"median {_med(fr):.2f}x (n={len(fr)})")

    # replay fidelity: actual realized R vs replayed baseline R
    print("\nReplay fidelity — actual realized R (total_pnl/risk_dollars) vs replayed "
          "baseline (day-0 / day-5):")
    for r in a_rows:
        b = r["res"]["orb_1.0x"]
        print(f"  {r['mode']:<5} {r['ticker']:<6} {r['date']}  actual {r['actual_r']:+6.2f}R"
              f"   replay d0 {b['r0']:+6.2f}R  d5 {b['r5']:+6.2f}R"
              f"{'  [fwd truncated]' if b['truncated'] else ''}")

    for rows, label in ((live, "COHORT A / LIVE (12 real-money trades)"),
                        (paper, "COHORT A / PAPER (full-bar paper trades)"),
                        (a_rows, "COHORT A / ALL (live+paper pooled — context only)")):
        if rows:
            sweep_table(rows, label)
            stop_time_hist(rows, label)
    rescue_detail(a_rows, "COHORT A (live+paper)")

    # ---- cohort B: simulated entries on HIGH alerts ----
    b_rows, b_excl, n_overlap = build_cohort_b(alerts, minute, daily, closed_keys)
    print(f"\n\nCOHORT B — HIGH alerts replayed as simulated ORB entries: {len(b_rows)} "
          f"of {len(alerts)} distinct alert-days ({n_overlap} overlap a closed real trade)")
    for k, v in sorted(b_excl.items()):
        print(f"  excluded: {v:>3}  {k}")
    trunc = sum(1 for r in b_rows if r["res"]["orb_1.0x"]["truncated"])
    fr_b = [(r["res"]["orb_1.0x"]["dist"]) for r in b_rows]
    atr_b = [r["res"]["orb_1.0x"]["dist"] / (r["entry"] - r["res"]["atr_1.0"]["stop"])
             for r in b_rows if "atr_1.0" in r["res"]]
    print(f"  forward window truncated (<{FWD_DAYS} daily bars): {trunc}")
    print(f"  current stop distance / ATR14, cohort B: median "
          f"{_med(atr_b):.2f}x (n={len(atr_b)})")
    sweep_table(b_rows, "COHORT B / SIMULATED HIGH-ALERT ENTRIES")
    stop_time_hist(b_rows, "COHORT B")

    print("\nFIDELITY LIMITS (also stated in the doc): minute-bar lows, not ticks; stop "
          "fills on a bar-low touch; sim entries fill at ORB high with zero slippage; no "
          "profit-taking rule in any arm; day-5 settle uses daily bars with overnight "
          "gap-through filled at the OPEN; replays structurally flatter wider stops.")


if __name__ == "__main__":
    main()
