"""#562/#327 — the operator's POPULATION RULING applied: theoretical day-1 population + sim.

RULING (operator, 2026-09-01, verbatim): "the names we didn't enter can be for reasons beyond
the stock itself, like we hit our cap, or the window beyond 9:45 like you said, etc. we should
consider them as EPs we theoretically would've traded in day 1 as well, so we should just look
at all EPs that meet our criteria."

This probe therefore REPLACES the did-we-enter split of `_562_stop_population_probe.py`
phase_classify with:

  POP  — every caught EP that MET OUR ENTRY CRITERIA, derived from CODE, not from whether an
         order row exists. The criteria applied, with their source:
           * score_tier = 'HIGH' — the ONLY tier the ORB job submits
             (broker/live_tracker.py:375 `WHERE alert_date = $1 AND score_tier = 'HIGH'`).
             MODERATE never routes to entry; score_tier NULL is a suppressed row.
           * the gap floor — a HIGH alert already passed MIN_GAP_PCT at detection; at
             submission the gap is RE-CHECKED on real-time price (entry_pipeline.py
             check_rt_gap_floor, toggle `ep_rt_entry_gap_recheck` on since 2026-08-02).
             Recorded `setup:gap_below_floor` skips are stock-level → OUT. For pairs the
             live system never re-checked (window-late / no attempt), the same test is
             applied uniformly from stored bars: first-minute close vs prev close under
             the era floor (10% before 2026-08-19, 9% after — MIN_GAP_PCT change log).
             Fail-OPEN when the data to check is absent (matches check_rt_gap_floor's
             silent-on-data-failure direction).
           * setup-level ORB gates (order_manager.prepare_orb_order → backtester/
             filters.py:207 validate_orb_entry): zero_range (ORB high==low) and
             stop_too_wide (ORB range > 1.5×ATR14, Wilder TR mean of last 14, daily bars
             strictly before the EP day, ≥10 bars else fail-open — filters.py:96).
             Recorded skips → OUT; for never-checked pairs the gate is computed uniformly
             from stored bars. Pairs with a REAL order (filled/cancelled) passed the live
             gates and are never re-litigated with locally computed ATR.
         Infrastructure/capacity skips are IN, each reported as its own route:
           window:out_of_orb, no-attempt (detected outside 9:31-9:44), block:max_positions,
           block:circuit_breaker, setup:account_fetch_failed (semantically infra — the
           account fetch says nothing about the stock), infra:*, setup:size_too_small and
           setup:price_exceeds_cap (account-size capacity), setup:chase_cap_exceeded
           (detection-timing), cancelled-unfilled orders, broker rejects.

  SIM  — the day-1 trade simulated for every population member under the REAL mechanics
         read from code (NOT the 15-minute ORB the earlier classify phase used):
           * ORB = the FIRST 1-MINUTE bar of the day (earliest bar in 09:30-09:35 —
             alpaca_client.get_first_bar:812, entry_pipeline.fetch_orb_bar_with_retry:82;
             validated: stored orb_high == the 09:30 mi_intraday_bars high on 13/13
             filled trades, _587_q6c_conv.psv).
           * entry = stop-buy at the ORB high, booked AT the level (order_manager:565).
           * protective stop, era-correct — boundary read from the trades themselves
             (hard_stop ≡ orb_low through 2026-08-14 fills; ≡ 2·orb_low − orb_high from
             2026-08-18; no fills 08-15..08-17): EP day ≤ 08-14 → ORB low;
             ≥ 08-17 → 2·orb_low − orb_high (order_manager.py:498, operator-signed 08-16).
           * trade-row orb_high/orb_low used when a real order recorded them (the live
             system's own levels); else the stored first-minute bar.
           * classification is BY WHAT THE STOCK DID (the ruling): (i) never_triggered —
             the ORB high never broke after the ORB bar; (ii) stopped_day1 — triggered,
             then touched the stop level later on day 1; (iii) survived_day1. The 10:00 ET
             unfilled-order cancel is a WE-mechanic, reported as a count (fills whose break
             came at/after 10:00), never a classifier.
           * ABSTAIN, never fabricate: minute-resolution decisions with missing minutes
             fall back to the VALIDATED daily authority (daily high ≡ RTH minute max, and
             daily low ≡ minute min: 0 low / 1 high mismatches > 0.2% on 142 full-coverage
             EP days — checked before this probe was written) —
               daily_high ≤ orb_high         → never_triggered  (decidable without minutes)
               triggered AND daily_low > stop → survived_day1   (decidable without minutes)
               triggered AND daily_low ≤ stop → ABSTAIN (ordering unknowable; in the
                 ORB-low era daily_low ≤ stop is true BY CONSTRUCTION, so one-bar pairs
                 that triggered always abstain — counted, stated)

  AGREE — the simulator cross-checked against every REAL day-1 fill (the ~41 stopped +
         ~4 not-stopped): sim must say triggered, and sim's day-1 class must match the
         real trade's day-1 outcome (final exit stop_hit dated the alert day vs later/open).
         Poor agreement ⇒ the card is unsound — the analysis doc says so and stops.

  TABLE — the delayed-entry per-rung table (`_562bf_triggers.tsv`, the lane's own recorded
         fires and settlements) re-grouped by the SIMULATED day-1 class. Mature fires only,
         both exit arms (M-none / M-trail), ERA SPLIT BY MONTH — the backfill's discipline
         inherited unchanged.

Data (captured once, read-only; never re-fetch what is captured):
    _562bf_alerts.tsv / _562bf_daily.tsv / _562bf_minute.tsv.gz / _562bf_triggers.tsv
        — the 2026-09-01 backfill capture (the harness this extends)
    _562sp_trades.tsv — magna53 rows incl. skips (the stop/population probe capture)
    _562td_capture.sql → _562td_alerttimes.tsv (mi_ep_alerts detected_at for the 267)
        + _562td_epminutes.tsv (EP-day RTH minутes for the 42 pairs the backfill capture
        lacked — prod holds only the 09:30 bar for most; captured 2026-09-01)

Usage:
    python scripts/probes/_562_theoretical_day1_probe.py pop     # → _562td_population.tsv
    python scripts/probes/_562_theoretical_day1_probe.py sim     # → _562td_day1_sim.tsv
    python scripts/probes/_562_theoretical_day1_probe.py agree   # fidelity gate
    python scripts/probes/_562_theoretical_day1_probe.py table   # per-group delayed entry
    python scripts/probes/_562_theoretical_day1_probe.py all

Throwaway diagnostic (scripts/probes/ convention). Read-only; writes only its own TSVs.
No thresholds touched, no live code, THE LINE intact.
"""
from __future__ import annotations

import csv
import gzip
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import _562_backfill_replay as bf  # noqa: E402  (the harness this card extends)
import _562_stop_population_probe as sp  # noqa: E402  (_mature, _stats reused verbatim)

_ET = ZoneInfo("America/New_York")

# era boundaries — read from the DATA (hard_stop ≡ orb_low through 08-14 fills,
# ≡ 2·orb_low−orb_high from 08-18; 08-15..16 weekend) and the signed change logs
ORBLOW_ERA_LAST = date(2026, 8, 14)     # last EP day whose stop was the ORB low
TWO_R_ERA_FIRST = date(2026, 8, 17)     # first EP day under entry−2R (signed 08-16)
FLOOR_CHANGE = date(2026, 8, 19)        # MIN_GAP_PCT 10.0 → 9.0 (operator-signed)

STOCK_SKIPS = ("setup:gap_below_floor", "setup:stop_too_wide", "setup:zero_range")
TEN_AM = 10 * 60


def _gap_floor(ep: date) -> float:
    return 10.0 if ep < FLOOR_CHANGE else 9.0


def _stop_level(ep: date, orb_high: float, orb_low: float) -> tuple[float, str]:
    if ep <= ORBLOW_ERA_LAST:
        return orb_low, "orb_low"
    if ep >= TWO_R_ERA_FIRST:
        return 2 * orb_low - orb_high, "2r"
    raise AssertionError(f"EP day {ep} falls between stop eras")


# ── loaders ───────────────────────────────────────────────────────────────────────────


def load_alert_rows():
    return bf.read_tsv("_562bf_alerts.tsv")


def load_alert_times():
    """(ticker, alert_date) -> earliest detected_et string (or created_et fallback)."""
    out = {}
    for r in bf.read_tsv("_562td_alerttimes.tsv"):
        k = (r["ticker"], r["alert_date"])
        t = r["detected_et"] or r["created_et"] or ""
        if k not in out or (t and t < out[k]):
            out[k] = t
    return out


def load_acting_trades():
    """(ticker, alert_date) -> the ACTING lane's magna53 rows (live if any live rows
    exist for the pair, else paper — the stop/population probe's rule, reused)."""
    rows = [t for t in sp._read_sp("_562sp_trades.tsv") if t["signal_type"] == "magna53"]
    bypair = defaultdict(list)
    for t in rows:
        bypair[(t["ticker"], t["alert_date"])].append(t)
    out = {}
    for k, rs in bypair.items():
        live = [r for r in rs if r["account_mode"] == "live"]
        out[k] = live if live else [r for r in rs if r["account_mode"] == "paper"]
    return out


def load_ep_minutes(high_pairs):
    """(ticker, ep_date_str) -> sorted 1-min RTH bars [{m,o,h,l,c}] from the backfill
    capture plus the _562td EP-day pull. Raw 1-minute — the day-1 walk needs the
    sequencing, not the lane's 5-min view."""
    bars = defaultdict(list)
    with gzip.open(HERE / "_562bf_minute.tsv.gz", "rt") as fh:
        rows = csv.reader(fh, delimiter="|")
        hdr = next(rows)
        ti, di, tmi = hdr.index("ticker"), hdr.index("d"), hdr.index("t_ms")
        oi, hi, li, ci = hdr.index("o"), hdr.index("h"), hdr.index("l"), hdr.index("c")
        for r in rows:
            if len(r) != len(hdr):
                continue
            k = (r[ti], r[di])
            if k not in high_pairs:
                continue
            t = datetime.fromtimestamp(int(float(r[tmi])) / 1000,
                                       tz=timezone.utc).astimezone(_ET)
            m = t.hour * 60 + t.minute
            if not (570 <= m < 960):
                continue
            bars[k].append({"m": m, "o": float(r[oi]), "h": float(r[hi]),
                            "l": float(r[li]), "c": float(r[ci])})
    p = HERE / "_562td_epminutes.tsv"
    if p.exists():
        for r in bf.read_tsv("_562td_epminutes.tsv"):
            k = (r["ticker"], r["d"])
            if k not in high_pairs:
                continue
            hh, mm = r["bar_et"].split(":")
            m = int(hh) * 60 + int(mm)
            if not (570 <= m < 960):
                continue
            bars[k].append({"m": m, "o": float(r["open"]), "h": float(r["high"]),
                            "l": float(r["low"]), "c": float(r["close"])})
    out = {}
    for k, bs in bars.items():
        dedup = {b["m"]: b for b in bs}   # the two captures overlap on nothing today,
        out[k] = [dedup[m] for m in sorted(dedup)]  # but a minute must never double
    return out


def _atr14(daily_by_date: dict, ep: date) -> float | None:
    """Mirror backtester/filters.py:96 compute_atr_14 AS THE 9:31 LIVE PATH SEES IT:
    daily bars strictly BEFORE the EP day (today's row is not in mi_daily_closes at
    9:31 — the function's own docstring), ≥10 rows in the 35-calendar-day lookback,
    Wilder TR, simple mean of the last 14."""
    lo = ep.toordinal() - 35
    ds = [d for d in sorted(daily_by_date) if d < ep and d.toordinal() >= lo]
    rows = [daily_by_date[d] for d in ds
            if daily_by_date[d]["high_price"] is not None
            and daily_by_date[d]["low_price"] is not None
            and daily_by_date[d]["close"] is not None]
    if len(rows) < 10:
        return None
    trs = []
    for i in range(1, len(rows)):
        h, l, pc = rows[i]["high_price"], rows[i]["low_price"], rows[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not trs:
        return None
    w = trs[-14:]
    return sum(w) / len(w)


def _prev_close(daily_by_date: dict, ep: date) -> float | None:
    prior = [d for d in sorted(daily_by_date) if d < ep]
    if not prior:
        return None
    return daily_by_date[prior[-1]]["close"]


def _first_bar(bars5: list) -> dict | None:
    """Mirror get_first_bar: the EARLIEST minute bar in the 09:30-09:35 window."""
    for b in bars5:
        if 570 <= b["m"] < 575:
            return b
    return None


def _trade_orb(rows) -> tuple[float, float] | None:
    """The live system's own ORB levels off any order row that recorded them."""
    for r in rows:
        oh, ol = bf._f(r.get("orb_high")), bf._f(r.get("orb_low"))
        if oh and ol:
            return oh, ol
    return None


# ── phase POP ─────────────────────────────────────────────────────────────────────────


def _route_and_membership(tier, rows, minute_bars, daily_t, ep, at):
    """Return (route, in_pop, excl_reason, extras). Stock-level facts exclude;
    infra/capacity facts only pick the route."""
    if tier != "HIGH":
        return (("tier_moderate", False, "not_high_tier", {}) if tier == "MODERATE"
                else ("tier_suppressed", False, "score_tier_null", {}))

    statuses = {r["status"] for r in rows}
    reasons = [r["skip_reason"] or "" for r in rows]

    # a stock-level setup skip recorded by the live system wins (the stock failed
    # the criteria when actually checked), EXCEPT when the pair also has a real
    # order (a later attempt passed) — none such exist, asserted in phase_pop
    stock_hits = [x for x in reasons for s in STOCK_SKIPS if x.startswith(s)]
    if stock_hits and not ({"filled", "closed", "cancelled"} & statuses):
        return "gate_recorded", False, stock_hits[0].split(":")[1], {}

    if {"filled", "closed"} & statuses:
        return "entered", True, "", {}
    if "cancelled" in statuses:
        why = next((x for x in reasons if x), "")
        if why.startswith("setup:chase_cap_exceeded"):
            return "order_chase_capped", True, "", {}
        if why.startswith("broker:"):
            return "order_broker_reject", True, "", {}
        return "order_unfilled", True, "", {}
    if any(x.startswith("window:out_of_orb") for x in reasons):
        return "window_late", True, "", {}
    if any(x.startswith("block:max_positions") for x in reasons):
        return "blocked_cap", True, "", {}
    if any(x.startswith("block:circuit_breaker") for x in reasons):
        return "blocked_breaker", True, "", {}
    if any(x.startswith("setup:account_fetch_failed") for x in reasons):
        return "infra_account_fetch", True, "", {}
    if any(x.startswith("infra:") for x in reasons):
        return "infra_no_bar", True, "", {}
    if any(x.startswith(("setup:size_too_small", "setup:price_exceeds_cap"))
           for x in reasons):
        return "capacity_size", True, "", {}
    if rows:
        return "other_skip", True, "", {"raw": reasons[0][:60]}
    # no magna53 row at all — the scan never handed it to the ORB job in-window
    hh = (at or "")[11:16]
    return "no_attempt", True, "", {"detected": hh}


def phase_pop():
    alerts = load_alert_rows()
    times = load_alert_times()
    trades = load_acting_trades()
    daily = bf.load_daily()
    high_pairs = {(r["ticker"], r["alert_date"]) for r in alerts
                  if r["score_tier"] == "HIGH"}
    minutes = load_ep_minutes(high_pairs)

    # sanity: no pair may carry BOTH a stock-level skip and a real order
    for k, rs in trades.items():
        if k in high_pairs:
            has_order = any(r["status"] in ("filled", "closed", "cancelled") for r in rs)
            has_stock = any((r["skip_reason"] or "").startswith(STOCK_SKIPS) for r in rs)
            assert not (has_order and has_stock), f"mixed stock-skip + order: {k}"

    out = []
    for a in alerts:
        k = (a["ticker"], a["alert_date"])
        ep = date.fromisoformat(a["alert_date"])
        rows = trades.get(k, [])
        route, in_pop, excl, extras = _route_and_membership(
            a["score_tier"], rows, minutes.get(k, []), daily.get(a["ticker"], {}),
            ep, times.get(k))

        gate_src = ""
        orb_src, oh, ol = "", None, None
        if in_pop:
            mbars = minutes.get(k, [])
            t_orb = _trade_orb(rows)
            fb = _first_bar(mbars)
            if t_orb:
                orb_src, (oh, ol) = "trade_row", t_orb
            elif fb:
                orb_src, oh, ol = "minute_930", fb["h"], fb["l"]
            # uniform stock-level gates — ONLY for pairs without a real order
            # (a real order means the live gates already ran and passed)
            if route in ("window_late", "blocked_cap", "blocked_breaker",
                         "infra_account_fetch", "infra_no_bar", "capacity_size",
                         "other_skip", "no_attempt"):
                dby = daily.get(a["ticker"], {})
                if oh is not None and ol is not None:
                    if oh - ol <= 0:
                        in_pop, excl, gate_src = False, "zero_range", "computed"
                    else:
                        atr = _atr14(dby, ep)
                        if atr and atr > 0 and (oh - ol) > 1.5 * atr:
                            in_pop, excl, gate_src = False, "stop_too_wide", "computed"
                if in_pop and fb is not None:
                    pc = _prev_close(dby, ep)
                    # the live recheck runs at SOME submission tick inside 09:31-09:44
                    # (5-min cron + RT overlay), so the theoretical trade exists if ANY
                    # in-window minute close clears the era floor — a single-moment
                    # proxy would be stricter than the mechanic it mirrors
                    win = [b["c"] for b in mbars if 570 <= b["m"] <= 583]
                    if pc and win:
                        rt_gap = (max(win) - pc) / pc * 100.0
                        if rt_gap < _gap_floor(ep):
                            in_pop, excl, gate_src = False, "gap_below_floor", "computed"
                            extras["rt_gap"] = f"{rt_gap:.1f}"
                # data absent → fail-open (check_rt_gap_floor's own direction)
        out.append({
            "ticker": k[0], "ep_date": k[1], "mon": k[1][:7], "tier": a["score_tier"],
            "route": route, "in_pop": in_pop, "excl_reason": excl,
            "gate_src": gate_src or ("recorded" if route == "gate_recorded" else ""),
            "orb_src": orb_src,
            "orb_high": oh, "orb_low": ol,
            "detected_et": (times.get(k) or "")[11:19],
            "extras": json.dumps(extras) if extras else "",
        })

    cols = ["ticker", "ep_date", "mon", "tier", "route", "in_pop", "excl_reason",
            "gate_src", "orb_src", "orb_high", "orb_low", "detected_et", "extras"]
    with open(HERE / "_562td_population.tsv", "w") as fh:
        fh.write("|".join(cols) + "\n")
        for r in out:
            fh.write("|".join("" if r[c] is None else str(r[c]) for c in cols) + "\n")

    inp = [r for r in out if r["in_pop"]]
    print(f"== POP: {len(out)} caught EPs → population (met entry criteria) = {len(inp)} ==")
    print("\nroutes INTO the population (the operator's 'theoretical' visible):")
    for route, n in Counter(r["route"] for r in inp).most_common():
        mons = Counter(r["mon"][-2:] for r in inp if r["route"] == route)
        print(f"  {route:20s} {n:4d}   by month {dict(sorted(mons.items()))}")
    print("\nexcluded (stock-level / criteria):")
    for key, n in Counter((r["route"], r["excl_reason"], r["gate_src"])
                          for r in out if not r["in_pop"]).most_common():
        print(f"  {key[0]:16s} {key[1]:18s} [{key[2] or '-'}] {n:4d}")
    print("\nno-attempt pairs — detection times (all should be outside 09:31-09:44):")
    for r in inp:
        if r["route"] == "no_attempt":
            print(f"  {r['ticker']:6s} {r['ep_date']} detected {r['detected_et'] or '?'}")


# ── phase SIM ─────────────────────────────────────────────────────────────────────────


def _read_pop():
    rows = bf.read_tsv("_562td_population.tsv")
    for r in rows:
        r["in_pop"] = r["in_pop"] == "True"
        r["orb_high"] = bf._f(r["orb_high"])
        r["orb_low"] = bf._f(r["orb_low"])
    return rows


def phase_sim():
    pop = _read_pop()
    daily = bf.load_daily()
    trades = load_acting_trades()
    high_pairs = {(r["ticker"], r["ep_date"]) for r in pop if r["tier"] == "HIGH"}
    minutes = load_ep_minutes(high_pairs)

    out = []
    for r in pop:
        if not r["in_pop"]:
            continue
        k = (r["ticker"], r["ep_date"])
        ep = date.fromisoformat(r["ep_date"])
        oh, ol = r["orb_high"], r["orb_low"]
        rec = {"ticker": k[0], "ep_date": k[1], "mon": r["mon"], "route": r["route"],
               "orb_src": r["orb_src"], "orb_high": oh, "orb_low": ol,
               "stop": None, "stop_era": None, "stop_w_pct": None,
               "klass": None, "evidence": None, "sim_klass": None,
               "sim_evidence": None, "fill_minute": None,
               "fill_after_1000": None, "flags": []}
        if oh is None or ol is None:
            rec["sim_klass"], rec["sim_evidence"] = "abstain", "no_orb_basis"
            rec["flags"].append("no_levels")
        else:
            stop, era = _stop_level(ep, oh, ol)
            rec["stop"], rec["stop_era"] = stop, era
            rec["stop_w_pct"] = (oh - stop) / oh * 100.0

            d = daily.get(k[0], {}).get(ep)
            dh = d["high_price"] if d else None
            dl = d["low_price"] if d else None
            bars = minutes.get(k, [])
            fb = _first_bar(bars)
            walk = ([b for b in bars if fb and b["m"] > fb["m"]]
                    if r["orb_src"] != "trade_row" or fb
                    else [b for b in bars if b["m"] >= 571])
            full_path = len(walk) >= 20  # enough post-open prints to walk the day

            # daily authority first — decidable regardless of minute holes (validated).
            # TOUCH semantics: a stop-buy AT the level fills on a touch (BW 08-11:
            # daily high == orb_high == the real fill). But daily_high == orb_high is
            # AMBIGUOUS from the daily bar alone — the touch may sit entirely inside
            # the 09:30 bar (no order live yet) or be a later retest. So: strictly
            # below → never; equal (±0.01%) → abstain unless minutes/reality resolve
            # it; above → triggered. The minute walk below (bars AFTER the ORB bar)
            # carries exact semantics on its own.
            if dh is not None and dh < oh * (1 - 1e-4):
                if walk and max(b["h"] for b in walk) >= oh:
                    rec["flags"].append("minute_daily_conflict")
                rec["sim_klass"], rec["sim_evidence"] = "never_triggered", "daily"
            elif full_path:
                fill = next((b for b in walk if b["h"] >= oh), None)
                if fill is None:
                    # minutes show no touch though the daily high exceeds the level
                    if dh is not None and dh > oh * 1.002:
                        rec["sim_klass"] = "abstain"
                        rec["sim_evidence"] = "minute_daily_conflict"
                        rec["flags"].append("acmr_class")
                    else:
                        rec["sim_klass"], rec["sim_evidence"] = "never_triggered", "minute"
                else:
                    rec["fill_minute"] = fill["m"]
                    rec["fill_after_1000"] = fill["m"] >= TEN_AM
                    post = [b for b in walk if b["m"] > fill["m"]]
                    if fill["l"] <= stop:
                        rec["sim_klass"], rec["sim_evidence"] = "stopped_day1", "minute"
                        rec["flags"].append("pess_fill_bar")  # intra-bar order unknowable
                    elif any(b["l"] <= stop for b in post):
                        rec["sim_klass"], rec["sim_evidence"] = "stopped_day1", "minute"
                    else:
                        rec["sim_klass"], rec["sim_evidence"] = "survived_day1", "minute"
            # thin/no minutes: daily authority only
            elif dh is None:
                rec["sim_klass"], rec["sim_evidence"] = "abstain", "no_daily_bar"
            elif dh <= oh * (1 + 1e-4):
                # touch-at-the-level only: inside-ORB-bar or retest — unknowable
                rec["sim_klass"], rec["sim_evidence"] = "abstain", "daily_touch_ambiguous"
            elif dl is not None and dl > stop:
                rec["sim_klass"], rec["sim_evidence"] = "survived_day1", "daily"
            else:
                rec["sim_klass"], rec["sim_evidence"] = "abstain", "daily_ambiguous"

        # REAL-OUTCOME PRECEDENCE: where a real day-1 fill exists, the recorded trade
        # is the best evidence of what the stock did — a fill proves the trigger, a
        # day-1 stop_hit proves the stop touch. The bar-sim stays in sim_klass so the
        # AGREE phase can measure fidelity where both exist. Never fabricated: this
        # is the broker's own record. CRMD 05-14 is excepted (manual emergency close —
        # its exit reason describes the incident, not the stock).
        real, detail = _real_day1(trades.get(k, []))
        if real != "none" and k != ("CRMD", "2026-05-14"):
            rec["klass"], rec["evidence"] = real, "real"
            if rec["fill_minute"] is None:
                ft = next((t["filled_et"] for t in trades.get(k, [])
                           if t.get("filled_et")), "")
                if len(ft) >= 16:
                    rec["fill_minute"] = int(ft[11:13]) * 60 + int(ft[14:16])
                    rec["fill_after_1000"] = rec["fill_minute"] >= TEN_AM
        else:
            rec["klass"], rec["evidence"] = rec["sim_klass"], rec["sim_evidence"]
        out.append(rec)

    cols = ["ticker", "ep_date", "mon", "route", "orb_src", "orb_high", "orb_low",
            "stop", "stop_era", "stop_w_pct", "klass", "evidence", "sim_klass",
            "sim_evidence", "fill_minute", "fill_after_1000", "flags"]
    with open(HERE / "_562td_day1_sim.tsv", "w") as fh:
        fh.write("|".join(cols) + "\n")
        for r in out:
            r["flags"] = ",".join(r["flags"])
            fh.write("|".join("" if r[c] is None else str(r[c]) for c in cols) + "\n")

    print(f"== SIM: {len(out)} population members classified by what the STOCK did ==")
    for klass, n in Counter(r["klass"] for r in out).most_common():
        mons = Counter(r["mon"][-2:] for r in out if r["klass"] == klass)
        print(f"  {klass:16s} {n:4d}   by month {dict(sorted(mons.items()))}")
    print("\nevidence grade:", dict(Counter(r["evidence"] for r in out)))
    ws = [r["stop_w_pct"] for r in out if r["stop_w_pct"]]
    print(f"stop width (entry→stop): median {statistics.median(ws):.1f}% (n={len(ws)})")
    late = [r for r in out if r["fill_after_1000"] is True]
    print(f"triggered at/after 10:00 ET (the real 10:00 cancel would have dropped these "
          f"fills): {len(late)} of {sum(1 for r in out if r['klass'] in ('stopped_day1', 'survived_day1') and r['evidence'] == 'minute')} minute-graded fills")
    for era in ("orb_low", "2r"):
        er = [r for r in out if r["stop_era"] == era]
        print(f"  stop era {era}: {dict(Counter(r['klass'] for r in er))}")
    ab = [r for r in out if r["klass"] == "abstain"]
    print(f"\nabstained ({len(ab)}) — counted, never guessed:")
    for why, n in Counter(r["evidence"] for r in ab).most_common():
        print(f"  {why}: {n}")


# ── phase AGREE ───────────────────────────────────────────────────────────────────────


def _real_day1(rows) -> tuple[str, str]:
    """(real_class, detail) for a pair with a filled trade on the acting lane."""
    t = next((r for r in rows if r["status"] in ("closed", "filled")), None)
    if t is None:
        return "none", ""
    if t["status"] == "filled" or bf._f(t["remaining_shares"]):
        return "survived_day1", "still_open"
    try:
        exits = json.loads(t["exits"]) if t["exits"] not in ("", "\\N") else []
    except ValueError:
        exits = []
    if not exits:
        return "survived_day1", "closed_no_exit_rows"
    last = exits[-1]
    when = last.get("time", "")
    try:
        d_et = (datetime.fromisoformat(when).astimezone(_ET).date().isoformat()
                if when else "")
    except ValueError:
        d_et = when[:10]
    if last.get("reason") == "stop_hit" and d_et == t["alert_date"]:
        return "stopped_day1", f"stop {when[11:16]}Z"
    return "survived_day1", f"{last.get('reason')} on {d_et}"


def phase_agree():
    sim = {(r["ticker"], r["ep_date"]): r for r in bf.read_tsv("_562td_day1_sim.tsv")}
    trades = load_acting_trades()

    comparable = agree = 0
    no_indep, mism = [], []
    excluded = []
    for k, rows in sorted(trades.items()):
        if k not in sim:
            continue
        real, detail = _real_day1(rows)
        if real == "none":
            continue
        if k == ("CRMD", "2026-05-14"):
            excluded.append((k, "manual emergency close — the incident row"))
            continue
        s = sim[k]
        if s["sim_evidence"] != "minute":
            # one-bar EP days (or daily-only) — no independent bar path exists, so
            # reality classified the pair directly; nothing to cross-check
            no_indep.append((k, s, real))
            continue
        comparable += 1
        if s["sim_klass"] == real:
            agree += 1
        else:
            mism.append((k, s, real, detail))

    n_fills = comparable + len(no_indep)
    print(f"== AGREE: {n_fills} real day-1 fills on the acting lane ==")
    print(f"  independent minute-path sim exists for {comparable}; "
          f"agreement {agree}/{comparable} "
          f"({agree / comparable * 100:.0f}%)" if comparable else "  none comparable")
    for k, s, real, detail in mism:
        print(f"  ✗ {k[0]} {k[1]}: bar-sim={s['sim_klass']} (stop_era={s['stop_era']}, "
              f"flags={s['flags']}) real={real} ({detail})")
    print(f"  no independent bar path (reality classified directly): {len(no_indep)}")
    for k, s, real in no_indep:
        print(f"    {k[0]:6s} {k[1]} bar-evidence={s['sim_evidence']:16s} real={real}")
    for k, why in excluded:
        print(f"  excluded from the denominator: {k[0]} {k[1]} — {why}")

    # secondary consistency: cancelled-unfilled orders should show no pre-10:00 break
    n_c = n_ok = 0
    weird = []
    for k, rows in sorted(trades.items()):
        if k not in sim:
            continue
        if any(r["status"] in ("closed", "filled") for r in rows):
            continue
        if not any(r["status"] == "cancelled" for r in rows):
            continue
        s = sim[k]
        n_c += 1
        fm = bf._f(s["fill_minute"])
        if s["klass"] == "never_triggered" or (fm is not None and fm >= TEN_AM):
            n_ok += 1
        elif s["klass"] == "abstain":
            n_ok += 1  # no evidence either way
        else:
            weird.append((k, s))
    print(f"\n  cancelled-unfilled orders whose sim shows no pre-10:00 break (or "
          f"abstains): {n_ok}/{n_c}")
    for k, s in weird:
        fm = s["fill_minute"]
        print(f"    · {k[0]} {k[1]}: sim touch at minute {fm} (<10:00) though the real "
              f"order died unfilled — order-lifecycle (submission latency / ask-aware "
              f"cancel), NOT level drift: trade-row orb_high == the stored 09:30 bar "
              f"high exactly on every such pair (checked 2026-09-01); the STOCK touched "
              f"the level, the ORDER was not alive/armed for it")


# ── phase TABLE ───────────────────────────────────────────────────────────────────────


def phase_table():
    sim = {(r["ticker"], r["ep_date"]): r["klass"]
           for r in bf.read_tsv("_562td_day1_sim.tsv")}
    pop = {(r["ticker"], r["ep_date"]): r for r in _read_pop()}
    trigs = bf.read_tsv("_562bf_triggers.tsv")
    for t in trigs:
        t["realized_r"] = bf._f(t["realized_r"])
        t["realized_r_trail"] = bf._f(t["realized_r_trail"])
        t["mature"] = sp._mature(date.fromisoformat(t["fire_date"]))
        k = (t["ticker"], t["ep_date"])
        if k in sim:
            t["group"] = sim[k]
        elif k in pop and not pop[k]["in_pop"]:
            t["group"] = "out_of_population"
        else:
            t["group"] = "?"
    rungs = ("ep_low_reclaim", "ep_close_reclaim", "ep_high_break", "ep_close_620_prox")

    order = (("stopped_day1", "(ii) day-1 trade SIMULATED: triggered and stopped out"),
             ("never_triggered", "(i) the ORB high never broke — no day-1 trade existed"),
             ("survived_day1", "(iii) triggered and survived day 1"),
             ("abstain", "sim abstained (bars cannot establish the day-1 outcome)"),
             ("out_of_population", "did NOT meet entry criteria (reference only)"))
    for g, label in order:
        camps = [k for k, v in sim.items() if v == g] if g != "out_of_population" else \
                [k for k, r in pop.items() if not r["in_pop"]]
        gt = [t for t in trigs if t["group"] == g]
        mt = [t for t in gt if t["mature"] and t["settle_status"] == "settled"]
        print(f"\n== {label} — campaigns n={len(camps)} ==")
        print(f"  family: {len({(t['ticker'], t['ep_date']) for t in gt})} campaigns "
              f"fired; {len(gt)} fires, {len(mt)} mature settled")
        print(f"    M-none : {sp._stats([t['realized_r'] for t in mt])}")
        print(f"    M-trail: {sp._stats([t['realized_r_trail'] for t in mt])}")
        for mon in ("2026-05", "2026-06", "2026-07", "2026-08"):
            ms = [t["realized_r"] for t in mt if t["ep_date"][:7] == mon]
            n_im = sum(1 for t in gt if t["ep_date"][:7] == mon and not t["mature"])
            n_c = sum(1 for c in camps if c[1][:7] == mon)
            print(f"      {mon}: campaigns {n_c}  M-none {sp._stats(ms)}  immature={n_im}")
        for rung in rungs:
            rt = [t for t in mt if t["rung"] == rung]
            fired = len({(t["ticker"], t["ep_date"]) for t in gt if t["rung"] == rung})
            print(f"    {rung:20s} fired {fired}/{len(camps)}  "
                  f"M-none {sp._stats([t['realized_r'] for t in rt])}  "
                  f"M-trail {sp._stats([t['realized_r_trail'] for t in rt])}")
        tail = [t for t in mt if (t["realized_r"] or -9) >= 4
                or (t["realized_r_trail"] or -9) >= 4]
        if tail:
            print("    >=4R fires: " + "; ".join(
                f"{t['ticker']} {t['ep_date'][:7]} {t['rung']} "
                f"(none {t['realized_r']:+.1f}/trail {t['realized_r_trail']:+.1f})"
                for t in sorted(tail, key=lambda x: -(x["realized_r"] or -9))))

    # the head-to-head the card exists to answer, with the adversarial cut
    print("\n== the question: go back into (ii) sim-stopped vs (i) never-triggered ==")
    for g in ("stopped_day1", "never_triggered"):
        mt = [t for t in trigs if t["group"] == g and t["mature"]
              and t["settle_status"] == "settled"]
        ex_may = [t for t in mt if t["ep_date"][:7] != "2026-05"]
        print(f"  {g:16s} all-months M-none {sp._stats([t['realized_r'] for t in mt])}")
        print(f"  {g:16s} ex-May     M-none {sp._stats([t['realized_r'] for t in ex_may])}")


if __name__ == "__main__":
    phases = {"pop": phase_pop, "sim": phase_sim, "agree": phase_agree,
              "table": phase_table}
    if sys.argv[1] == "all":
        for name, fn in phases.items():
            print(f"\n{'=' * 78}\nPHASE {name}\n{'=' * 78}")
            fn()
    else:
        phases[sys.argv[1]]()
