#!/usr/bin/env python3
"""Stop-floor FORWARD replay — realized R per trade/cohort for a volatility floor (EVIDENCE ONLY).

Follow-on to docs/analysis/live_cohort_day0_stopout_2026-08-06.md §D, which showed a floored stop
(stop_k = MIN(orb-low stop, entry*(1 - k*ADR20/100)) — MIN in PRICE terms = whichever gives MORE
room; the floor may only WIDEN a stop, never tighten one) rescues 4 of 14 live trades on their
ENTRY DAY. This card answers the question §D could not: do those trades FINISH profitably?

THE LINE: read-only evidence. No live parameter, no strategy, no stop placement is changed here.
Stop placement is the operator's sole authority (CHANGE_PROCESS + sign-off before any live flip).

WHAT IS MODELED (exactly three mechanisms, uniformly at every k):
  1. Hard stop at stop_k, filling AT stop_k (slippage ignored — stated simplification; actual
     fills slipped 0-1.4c below the stop on 12 of 14).
  2. The +2R partial (live since 2026-08-05 — ALL 14 of these ran WITHOUT it): when price trades
     at entry + 2*r_unit (r_unit = entry - stop_k, i.e. R is measured against the WIDENED stop),
     sell 1/3 AT that price (limit-style — no fill below the level), move the stop on the
     remainder to breakeven (entry).
  3. Remainder exits at its stop or at the close of the 10th session after entry (entry day =
     session 0, exit at close of session 10), whichever comes first.

WHAT IS DELIBERATELY NOT MODELED (they exist live; modeling them would confound the one variable
under test — the floor): the time-stop, the 15:45 partial window, the giveback peak-lock, the
daily SMA10/20-trail / hard-stop-ladder management step (broker/exit_logic.py), re-entries,
slippage, commissions. Consequence, found in the k=0 reconciliation: MANE and SMCI actually
exited at stops RAISED by that daily management engine (exit 119.04 vs initial stop 118.02;
28.79 vs 28.50) — the stop-only model diverges from history on exactly those two, and the
divergence is reported per-trade rather than papered over.

SIM CONVENTIONS (the #306 sim contract where they overlap):
  * Minute bars, RTH only (09:30 <= ET < 16:00). Within a bar the LOW is reached before the
    HIGH (pessimistic — it stops you out before it pays you).
  * Stop scan INCLUDES the bar containing the fill, but on THAT bar a stop-out requires the
    bar to CLOSE at/below the stop — the bar's low can predate the fill second (MANE's live
    118.02 stop sat through day 0 untriggered while the fill minute's low printed below it),
    while a close below proves post-fill weakness (HUT really died 51s after filling).
    Partial-trigger scan starts at the first bar AFTER the fill bar (#306: an entry-minute
    spike cannot self-trigger).
  * Every simulated stop-hit is CROSS-CHECKED against the official mi_daily_closes low of
    that session (_stop_floor_fwd_daily.tsv); a stop-hit the official daily low does not
    corroborate is flagged (minute-aggregate-only print — thin-name risk).
  * Same-bar ambiguity (partial-trigger bar also has low <= entry): pessimistic — the partial
    fills and the remainder scratches at breakeven that same bar; occurrences counted.
  * Stops fill AT the stop level even when a bar OPENS below it (per the card spec); every
    gap-through open is counted and a gap-aware sensitivity line (fill at min(open, stop))
    is reported so the optimism is bounded.
  * Trades whose 10th forward session is beyond the data end (entered too recently) settle
    only if stopped; otherwise they mark-to-last-available-close and are FLAGGED unsettled.

R BASIS: r_unit = entry - stop_k. Sizing is risk-based (shares = risk_dollars / r_unit), so R is
normalized across k and dollar P&L at the trade's actual budget = R * risk_dollars.
⚠ Two "actual R" bases exist and they differ: the doc's cohort -11.5R divides pnl by the PLANNED
risk_dollars; the replay's unit is the REALIZED per-share risk (entry - stop) * shares. The
reconciliation compares on the realized basis (apples-to-apples with the sim); both cohort
totals are printed.

INPUTS (capture once, read many — COST EFFICIENCY):
  _stop_floor_trades.tsv  prod mi_live_trades, status='closed' AND account_mode='live' (n=14),
                          pulled 2026-08-06 via read-only psql (scratchpad sfr_trades.sql).
  _stop_floor_daily.tsv   prod mi_daily_closes OHLC, alert_date-45..alert_date per ticker
                          (the doc's ADR20 source), same pull.
  _stop_floor_minute.tsv  Polygon 1-min bars, alert_date..alert_date+16d per ticker, fetched
                          ONCE via --pull-bars (reuses _468_moderate_realized_r._ssh_polygon —
                          the in-container read path; Polygon already subscribed, $0 marginal).

RUN:
  python3 scripts/probes/_stop_floor_forward_replay.py --pull-bars   # once, then never again
  python3 scripts/probes/_stop_floor_forward_replay.py               # offline sim + report
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
HERE = Path(__file__).resolve().parent

TRADES = HERE / "_stop_floor_trades.tsv"
DAILY = HERE / "_stop_floor_daily.tsv"
FWD_DAILY = HERE / "_stop_floor_fwd_daily.tsv"
MINUTE = HERE / "_stop_floor_minute.tsv"

K_SWEEP = [0.0, 0.5, 0.75, 1.0]
TIME_STOP_SESSION = 10          # exit at close of the 10th session after entry (entry = 0)
FWD_CAL_DAYS = 16               # calendar days of minute data after alert_date


# ── loaders ──────────────────────────────────────────────────────────────────

def _f(x):
    try:
        return float(x) if x not in ("", None, r"\N") else None
    except ValueError:
        return None


def _parse_ts(s: str):
    s = (s or "").strip()
    if not s or s == r"\N":
        return None
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def load_trades() -> list[dict]:
    trades = []
    for ln in TRADES.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        f = ln.split("\t")
        t = {
            "id": int(f[0]), "ticker": f[1], "alert_date": f[2],
            "entry": _f(f[3]), "shares": _f(f[4]),
            "stop_price": _f(f[5]), "hard_stop": _f(f[6]),
            "orb_high": _f(f[7]), "orb_low": _f(f[8]),
            "risk_dollars": _f(f[9]), "pnl": _f(f[10]),
            "filled_at": _parse_ts(f[11]), "closed_at": _parse_ts(f[12]),
            "status": f[13], "exits": json.loads(f[14] or "[]"),
        }
        t["actual_R"] = (t["pnl"] / t["risk_dollars"]) if t["risk_dollars"] else None
        t["actual_close_day"] = None  # filled in once sessions are known
        trades.append(t)
    return trades


def load_daily(path: Path = DAILY) -> dict[str, list[dict]]:
    by = defaultdict(list)
    for ln in path.read_text(encoding="utf-8").splitlines():
        p = ln.split("\t")
        if len(p) < 7 or not p[0]:
            continue
        by[p[0]].append({"date": p[1], "o": _f(p[2]), "h": _f(p[3]),
                         "l": _f(p[4]), "c": _f(p[5])})
    for tk in by:
        by[tk].sort(key=lambda b: b["date"])
    return by


def load_minute() -> dict[str, list[dict]]:
    by = defaultdict(list)
    if not MINUTE.exists():
        return by
    for ln in MINUTE.read_text(encoding="utf-8").splitlines():
        p = ln.split("\t")
        if len(p) < 7 or p[0].startswith("#"):
            continue
        t_ms = int(p[1])
        dt = datetime.fromtimestamp(t_ms / 1000, tz=ET)
        if not ((dt.hour, dt.minute) >= (9, 30) and dt.hour < 16):
            continue                                   # RTH only
        by[p[0]].append({"t": t_ms, "dt": dt, "o": _f(p[2]), "h": _f(p[3]),
                         "l": _f(p[4]), "c": _f(p[5])})
    for tk in by:
        by[tk].sort(key=lambda b: b["t"])
    return by


# ── ADR20 (the doc's convention: mi_daily_closes, sessions before alert_date) ─

def adr20_pct(daily: list[dict], alert_date: str) -> float | None:
    pre = [d for d in daily
           if d["date"] < alert_date and d["h"] and d["l"] and d["c"]]
    last20 = pre[-20:]
    if len(last20) < 10:
        return None
    return statistics.mean((d["h"] - d["l"]) / d["c"] * 100 for d in last20)


# ── the replay ───────────────────────────────────────────────────────────────

def replay(trade: dict, bars: list[dict], stop_k: float, partial_on: bool,
           gap_aware: bool = False) -> dict:
    """One trade under the 3-mechanism model. Returns realized R (basis entry-stop_k),
    close session index, partial info, and data-quality flags."""
    entry = trade["entry"]
    r_unit = entry - stop_k
    assert r_unit > 0, f"{trade['ticker']}: stop_k {stop_k} not below entry {entry}"
    target = entry + 2.0 * r_unit
    filled_ms = int(trade["filled_at"].timestamp() * 1000)
    alert = trade["alert_date"]

    sessions = sorted({b["dt"].date().isoformat() for b in bars
                       if b["dt"].date().isoformat() >= alert})
    if not sessions or sessions[0] != alert:
        return {"error": "no_entry_day_bars"}
    day_of = {d: i for i, d in enumerate(sessions)}
    horizon = [b for b in bars if alert <= b["dt"].date().isoformat()
               and day_of[b["dt"].date().isoformat()] <= TIME_STOP_SESSION]
    # stop scan includes the fill bar; partial scan starts strictly after it
    walk = [b for b in horizon if b["t"] + 60_000 > filled_ms]
    if not walk:
        return {"error": "no_bars_after_fill"}
    have_ts = len(sessions) > TIME_STOP_SESSION       # session 10 exists in the data

    pos, stop = 1.0, stop_k
    pnl_ps = 0.0
    out = {"error": None, "partial_day": None, "close_day": None, "ambiguous": False,
           "gap_throughs": 0, "settled": True, "exit_via": None, "stop_hit_bar": None}
    last_bar = walk[-1]
    for b in walk:
        di = day_of[b["dt"].date().isoformat()]
        # pessimistic: LOW first. On the FILL bar the low can predate the fill second,
        # so a stop-out there requires the bar to CLOSE at/below the stop.
        is_fill_bar = b["t"] <= filled_ms
        stopped = (b["c"] <= stop) if is_fill_bar else (b["l"] <= stop)
        if stopped:
            if b["o"] < stop:
                out["gap_throughs"] += 1
            px = min(b["o"], stop) if gap_aware else stop
            pnl_ps += pos * (px - entry)
            pos = 0.0
            out["close_day"], out["exit_via"] = di, ("stop" if stop == stop_k else "be_stop")
            out["stop_hit_bar"] = (b["dt"], stop)
            break
        if (partial_on and out["partial_day"] is None
                and b["t"] > filled_ms and b["h"] >= target):
            pnl_ps += (1.0 / 3.0) * (target - entry)
            pos -= 1.0 / 3.0
            stop = entry                               # breakeven on the remainder
            out["partial_day"] = di
            if b["l"] <= entry:                        # same-bar ambiguity: pessimistic scratch
                pnl_ps += pos * (entry - entry)
                pos = 0.0
                out["close_day"], out["exit_via"] = di, "be_stop_samebar"
                out["ambiguous"] = True
                break
        if have_ts and di == TIME_STOP_SESSION and b is last_bar:
            pnl_ps += pos * (b["c"] - entry)
            pos = 0.0
            out["close_day"], out["exit_via"] = di, "time_stop_s10"
            break
    if pos > 1e-9:                                     # data ran out with position open
        out["settled"] = False
        out["close_day"] = day_of[last_bar["dt"].date().isoformat()]
        out["exit_via"] = "UNSETTLED_mtm_data_end"
        pnl_ps += pos * (last_bar["c"] - entry)
    out["r"] = pnl_ps / r_unit
    out["r_unit"] = r_unit
    return out


# ── phase: minute-bar fetch (reuses the _468 in-container Polygon read path) ──

def pull_bars() -> None:
    sys.path.insert(0, str(HERE))
    import _468_moderate_realized_r as base            # reuse, don't rebuild
    trades = load_trades()
    ranges = sorted(
        (t["ticker"], t["alert_date"],
         (datetime.fromisoformat(t["alert_date"]) + timedelta(days=FWD_CAL_DAYS))
         .date().isoformat())
        for t in trades)
    print(f"pulling minute bars for {len(ranges)} (ticker, d0, d0+{FWD_CAL_DAYS}d) ranges …")
    lit = "[" + ",".join(f'("{t}","{a}","{b}")' for t, a, b in ranges) + "]"
    code = (
        "import json,os,sys,time,urllib.request\n"
        "KEY=os.environ[\"POLYGON_API_KEY\"]\n"
        f"RANGES={lit}\n"
        "for t,a,b in RANGES:\n"
        "    url=f\"https://api.polygon.io/v2/aggs/ticker/{t}/range/1/minute/{a}/{b}?adjusted=true&sort=asc&limit=50000&apiKey={KEY}\"\n"
        "    try:\n"
        "        rr=json.load(urllib.request.urlopen(url,timeout=30))\n"
        "        for bar in rr.get(\"results\",[]):\n"
        "            tt=bar[\"t\"];o=bar[\"o\"];h=bar[\"h\"];lo=bar[\"l\"];c=bar[\"c\"];v=bar[\"v\"]\n"
        "            print(f\"{t}\\t{tt}\\t{o}\\t{h}\\t{lo}\\t{c}\\t{v}\")\n"
        "    except Exception as e:\n"
        "        print(f\"# ERR {t} {a}: {e}\",file=sys.stderr)\n"
        "    time.sleep(0.12)\n"
    )
    base._ssh_polygon(code, MINUTE)


# ── report ───────────────────────────────────────────────────────────────────

def main() -> None:
    if "--pull-bars" in sys.argv:
        pull_bars()
        return

    trades = load_trades()
    daily = load_daily()
    fwd_daily = load_daily(FWD_DAILY)
    minute = load_minute()
    if not minute:
        sys.exit("no minute bars — run --pull-bars once first")

    def official_low_check(t, r, stop_level):
        """Does the official mi_daily_closes low of the sim's stop-hit session corroborate
        the minute-print stop-hit? Returns a flag string or ''."""
        if not r.get("stop_hit_bar"):
            return ""
        hit_dt, _ = r["stop_hit_bar"]
        day = next((d for d in fwd_daily.get(t["ticker"], [])
                    if d["date"] == hit_dt.date().isoformat()), None)
        if day is None:
            return " ⚠no-official-day"
        if day["l"] > stop_level + 1e-6:
            return f" ⚠MINUTE-ONLY-PRINT(official low {day['l']} > stop {stop_level:.2f})"
        return ""

    # enrich: ADR20, floor stops, per-trade sanity
    problems = []
    for t in trades:
        t["adr20"] = adr20_pct(daily.get(t["ticker"], []), t["alert_date"])
        if t["adr20"] is None:
            problems.append(f"{t['ticker']}: <10 daily sessions before alert — no ADR20")
        stop0 = t["hard_stop"]
        t["stop_ratio"] = ((t["entry"] - stop0) / t["entry"] * 100) / t["adr20"] \
            if t["adr20"] else None
        bars = minute.get(t["ticker"], [])
        d0 = [b for b in bars if b["dt"].date().isoformat() == t["alert_date"]]
        if not d0:
            problems.append(f"{t['ticker']}: no entry-day minute bars")
        else:
            lo, hi = min(b["l"] for b in d0), max(b["h"] for b in d0)
            if not (lo <= t["entry"] <= hi * 1.001):
                problems.append(f"{t['ticker']}: entry {t['entry']} outside day-0 bar range "
                                f"[{lo}, {hi}] — split/adjustment mismatch?")
        # actual close session index (for the reconciliation table)
        sess = sorted({b["dt"].date().isoformat() for b in bars
                       if b["dt"].date().isoformat() >= t["alert_date"]})
        cd = t["closed_at"].astimezone(ET).date().isoformat()
        t["actual_close_day"] = sess.index(cd) if cd in sess else None
        t["actual_exit_px"] = t["exits"][0]["price"] if t["exits"] else None

    n_budget = statistics.mean(t["risk_dollars"] for t in trades)
    for t in trades:                       # realized-unit actual R (apples-to-apples w/ sim)
        t["actual_R_unit"] = t["pnl"] / (t["shares"] * (t["entry"] - t["hard_stop"]))
    print(f"cohort n={len(trades)} · actual total {sum(t['actual_R'] for t in trades):+.2f}R "
          f"(doc basis: pnl/planned risk_dollars) · "
          f"{sum(t['actual_R_unit'] for t in trades):+.2f}R (realized entry-stop unit — the "
          f"replay's basis) · avg risk budget ${n_budget:.2f}/trade")
    for p in problems:
        print(f"⚠ DATA: {p}")

    # ── 1. k=0 reconciliation (stop-only, partial OFF — the world these 14 ran in) ──
    print("\n== 1. k=0 RECONCILIATION — stop-only replay vs actual (partial OFF: the "
          "+2R rule was not live for any of these; actual_R on the realized "
          "entry-stop unit) ==")
    print(f"{'tkr':<5} {'actual_R':>8} {'sim_R':>7} {'diff':>6} {'act_day':>7} {'sim_day':>7} "
          f"{'act_exit':>9} {'init_stop':>9}  note")
    recon_ok = True
    for t in trades:
        r = replay(t, minute.get(t["ticker"], []), t["hard_stop"], partial_on=False)
        t["recon"] = r
        if r.get("error"):
            print(f"{t['ticker']:<5} REPLAY FAILED: {r['error']}")
            recon_ok = False
            continue
        diff = r["r"] - t["actual_R_unit"]
        raised = (t["actual_exit_px"] is not None
                  and t["actual_exit_px"] > t["hard_stop"] * 1.002)
        note = ("stop RAISED live (daily mgmt engine) — model diverges by design"
                if raised else
                "slippage only" if abs(diff) <= 0.08 else "⚠ UNEXPLAINED")
        note += official_low_check(t, r, t["hard_stop"])
        if not raised and abs(diff) > 0.08:
            recon_ok = False
        if not raised and t["actual_close_day"] != r["close_day"]:
            note += " ⚠ close-day mismatch"
            recon_ok = False
        print(f"{t['ticker']:<5} {t['actual_R_unit']:>+8.2f} {r['r']:>+7.2f} {diff:>+6.2f} "
              f"{t['actual_close_day']:>7} {r['close_day']:>7} "
              f"{t['actual_exit_px']:>9.2f} {t['hard_stop']:>9.2f}  {note}")
    clean = [t for t in trades if not t["recon"].get("error")
             and t["actual_exit_px"] <= t["hard_stop"] * 1.002]
    print(f"\nreconciliation on the {len(clean)} trades that actually exited AT their initial "
          f"stop: sim {sum(t['recon']['r'] for t in clean):+.2f}R vs actual "
          f"{sum(t['actual_R_unit'] for t in clean):+.2f}R "
          f"(max per-trade |diff| "
          f"{max(abs(t['recon']['r'] - t['actual_R_unit']) for t in clean):.3f}R)")
    print(f"VERDICT: {'RECONCILED (divergences named above are the excluded live mechanisms)' if recon_ok else '⚠ FAILED — do not trust the sweep'}")

    # ── ADR cross-check vs the doc's §A ratios ──
    print("\n== ADR20 cross-check (stop ÷ range vs doc §A) ==")
    doc_ratio = {"MANE": 0.15, "HUT": 0.20, "CRCL": 0.27, "BTDR": 0.29, "QBTS": 0.35,
                 "WULF": 0.39, "TSEM": 0.41, "SMCI": 0.52, "BLZE": 0.87, "FTNT": 0.93,
                 "THC": 0.95, "WKC": 1.12, "WDFC": 1.12, "NVCR": 1.18}
    for t in sorted(trades, key=lambda x: x["stop_ratio"] or 9):
        d = doc_ratio.get(t["ticker"])
        flag = "" if d is None or abs(t["stop_ratio"] - d) <= 0.03 else "  ⚠ off vs doc"
        print(f"  {t['ticker']:<5} adr20 {t['adr20']:5.2f}%  stop/range {t['stop_ratio']:.2f} "
              f"(doc {d}){flag}")

    # ── 2-3. the sweep (partial ON — the deployed-today exit ruleset) ──
    for label, partial_on in (("partial ON (the ruleset deployed today)", True),
                              ("partial OFF (floor alone, isolation view)", False)):
        print(f"\n== SWEEP — {label} ==")
        hdr = f"{'tkr':<5} {'ratio':>5} "
        for k in K_SWEEP:
            hdr += f"| {'k=' + str(k):>7}{'P@':>4}{'cls':>4} "
        print(hdr + "  (P@ = partial-fire session, cls = close session; * floor bound, "
              "! unsettled at data end, ? official daily low does not corroborate)")
        results = {k: [] for k in K_SWEEP}
        for t in trades:
            row = f"{t['ticker']:<5} {t['stop_ratio'] or 0:5.2f} "
            base_r = None
            for k in K_SWEEP:
                floor_px = t["entry"] * (1 - k * (t["adr20"] or 0) / 100)
                stop_k = min(t["hard_stop"], floor_px)   # MIN in price = wider stop only
                bound = stop_k < t["hard_stop"] - 1e-9
                r = replay(t, minute.get(t["ticker"], []), stop_k, partial_on=partial_on)
                if r.get("error"):
                    row += f"| {'ERR':>7}{'':>4}{'':>4} "
                    continue
                if k == 0.0:
                    base_r = r["r"]
                if not bound:                            # identity assertion: floor must be a no-op
                    assert base_r is None or abs(r["r"] - base_r) < 1e-9, \
                        f"{t['ticker']} k={k}: unbound floor changed the result"
                results[k].append((t, r, bound))
                pd = "-" if r["partial_day"] is None else str(r["partial_day"])
                oflag = official_low_check(t, r, stop_k if r["exit_via"] == "stop"
                                           else t["entry"])
                row += (f"| {r['r']:>+7.2f}{pd:>4}{r['close_day']:>3}"
                        f"{'*' if bound else ' '}{'!' if not r['settled'] else ''}"
                        f"{'?' if oflag else ''} ")
            print(row)
        print()
        for k in K_SWEEP:
            rs = [r["r"] for _, r, _ in results[k]]
            n = len(rs)
            tot = sum(rs)
            wins = sum(1 for x in rs if x > 0)
            d0 = sum(1 for _, r, _ in results[k] if r["close_day"] == 0)
            bound_n = sum(1 for _, _, b in results[k] if b)
            part_n = sum(1 for _, r, _ in results[k] if r["partial_day"] is not None)
            unset = sum(1 for _, r, _ in results[k] if not r["settled"])
            dollars = sum(r["r"] * t["risk_dollars"] for t, r, _ in results[k])
            top = max(results[k], key=lambda x: x[1]["r"])
            ex_top = tot - top[1]["r"]
            print(f"  k={k:<4} total {tot:+7.2f}R (${dollars:+8.2f} at actual budgets) · "
                  f"win {wins}/{n} · day-0 closes {d0} · floor bound {bound_n} · "
                  f"partial fired {part_n} · unsettled {unset} · "
                  f"ex-best({top[0]['ticker']}) {ex_top:+.2f}R")
        # gap-aware sensitivity (stop fills at min(open, stop))
        line = "  gap-aware stop fills (min(open,stop)): "
        for k in K_SWEEP:
            tot = 0.0
            for t in trades:
                stop_k = min(t["hard_stop"], t["entry"] * (1 - k * (t["adr20"] or 0) / 100))
                r = replay(t, minute.get(t["ticker"], []), stop_k,
                           partial_on=partial_on, gap_aware=True)
                if not r.get("error"):
                    tot += r["r"]
            line += f"k={k}: {tot:+.2f}R  "
        print(line)

    print("\n(EVIDENCE ONLY — no change made or proposed; stop placement is the operator's "
          "sole authority. THE LINE.)")


if __name__ == "__main__":
    main()
