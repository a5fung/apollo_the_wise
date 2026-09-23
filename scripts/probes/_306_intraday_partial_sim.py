#!/usr/bin/env python3
"""#306 — intraday partial-profit + breakeven-stop replay (ANALYSIS ONLY, offline).

Operator's rule under test: when an open position reaches trigger level L INTRADAY,
sell 1/3 at the trigger, move the stop on the remaining 2/3 to breakeven (entry).

Scope-add (operator, mid-card): the trigger BASIS is the central fork —
  fixed-%%  vs  R-multiple (already partially character-normalized: risk = entry−stop,
  stop derives from that day's ORB low / prior-day low)  vs  ADR-multiple
  (normalized to the stock's TYPICAL character: ADR20 = mean (high−low)/close over the
  20 sessions ENDING THE DAY BEFORE the fill — flag_detector's sourced-range convention
  shifted pre-entry so the gap day itself doesn't inflate the denominator).
Plus character segmentation (cap tier / ADR tier / gap size).

Inputs (all cached; sim is fully offline and re-runnable):
  _306_trades_live.tsv / _306_trades_paper.tsv — prod snapshots 2026-07-25 of
      mi_live_trades (account_mode live: all filled; paper: closed+filled).
  _306_bars_raw.tsv  — Polygon 1-min bars per trade (fill→exit ET dates) + daily bars
      per ticker (entry−400d → exit+14d), fetched via docker exec apollo-market with
      the same endpoints collector.get_minute_bars/get_index_history use.
  _306_caps.tsv      — Polygon v3 reference market_cap (AS OF FETCH DATE, not entry —
      tiering only).

Sim contract (conservative, stated in the doc):
  * Bars: RTH only (09:30 ≤ ET < 16:00). Trigger scan starts at the first bar with
    t >= filled_at (prod's track_open_position_extremes convention — the fill bar
    itself is EXCLUDED, so an entry-minute spike can't self-trigger).
  * Partial fills AT the trigger price (limit-at-level assumption; no slippage credit).
  * BE stop after trigger: first later bar with open <= entry fills at the OPEN
    (gap-through, e.g. a day-2 gap-down), else low <= entry fills AT entry.
  * Same-bar ambiguity (trigger bar also has low <= entry): resolved PESSIMISTICALLY —
    partial fills and the remainder scratches at entry that bar; occurrences counted.
  * Counterfactual exits for the un-scratched remainder replay the trade's REAL exit
    legs (exits jsonb) scaled to 2/3, cut off at the BE-touch time. A never-triggered
    trade is byte-identical to history.
  * R basis throughout = DEPLOYED risk (entry−hard_stop per share), matching #503 §4.
Run:  python3 scripts/probes/_306_intraday_partial_sim.py
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
HERE = Path(__file__).resolve().parent

PCT_LEVELS = [0.02, 0.03, 0.05, 0.08, 0.10, 0.15]
R_LEVELS = [0.5, 1.0, 1.5, 2.0, 3.0]
ADR_LEVELS = [0.5, 1.0, 1.5, 2.0]


# ── load ─────────────────────────────────────────────────────────────────────
def _parse_ts(s: str):
    s = (s or "").strip()
    if not s:
        return None
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:            # legacy 'at' legs are naive UTC
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt


def load_trades():
    trades = []
    for fname, cohort in (("_306_trades_live.tsv", "live"), ("_306_trades_paper.tsv", "paper")):
        for line in (HERE / fname).read_text().splitlines():
            if not line.strip():
                continue
            f = line.split("\t")
            t = {
                "id": int(f[0]), "ticker": f[1], "alert_date": f[2], "signal": f[3],
                "entry": float(f[4]), "hard_stop": float(f[5]),
                "orb_high": float(f[6]) if f[6] else None,
                "orb_low": float(f[7]) if f[7] else None,
                "shares": float(f[8]),
                "filled_at": _parse_ts(f[9]), "closed_at": _parse_ts(f[10]),
                "pnl": float(f[11]) if f[11] else 0.0,
                "hps": float(f[12]) if f[12] else None,
                "lps": float(f[13]) if f[13] else None,
                "status": f[14], "cohort": cohort,
                # normalize legacy leg shape {at, qty} -> {time, shares}
                "exits_all": sorted(
                    [{"time": e.get("time") or e.get("at"),
                      "shares": e.get("shares", e.get("qty")),
                      "price": e["price"]} for e in json.loads(f[15] or "[]")],
                    key=lambda e: e["time"]),
            }
            t["risk_ps"] = t["entry"] - t["hard_stop"]
            t["deployed_risk"] = t["shares"] * t["risk_ps"]
            t["actual_R"] = (t["pnl"] / t["deployed_risk"]) if t["deployed_risk"] > 0 else None
            # Multi-attempt rows (e.g. paper TEAM #57): exits jsonb + total_pnl merge a
            # PRIOR attempt's stop-out (leg time < filled_at of the final fill). The sim
            # replays the FINAL attempt only; prior-attempt pnl is a constant in both the
            # actual and counterfactual worlds, so all comparisons are done in DELTAS.
            t["exits"] = [e for e in t["exits_all"]
                          if _parse_ts(e["time"]) >= t["filled_at"]]
            t["prior_attempt_legs"] = len(t["exits_all"]) - len(t["exits"])
            legs_sum = sum(e["shares"] for e in t["exits"])
            if t["status"] == "closed" and abs(legs_sum - t["shares"]) > 0.5:
                print(f"⚠ {t['ticker']} #{t['id']}: final-attempt legs sum {legs_sum} "
                      f"!= shares {t['shares']} — leg bookkeeping suspect")
            # leg-based actual for the final attempt (per entry-share)
            t["sim_actual_R"] = (sum((e["shares"] / t["shares"]) * (e["price"] - t["entry"])
                                     for e in t["exits"]) / t["risk_ps"]
                                 if t["risk_ps"] > 0 else None)
            trades.append(t)
    return trades


def load_bars():
    minute, daily = {}, {}
    for line in (HERE / "_306_bars_raw.tsv").read_text().splitlines():
        f = line.split("\t")
        if f[0] == "MIN":
            tid = int(f[1])
            bar = {"t": int(f[3]), "o": float(f[4]), "h": float(f[5]),
                   "l": float(f[6]), "c": float(f[7])}
            dt = datetime.fromtimestamp(bar["t"] / 1000, tz=ET)
            bar["dt"] = dt
            bar["rth"] = (dt.hour, dt.minute) >= (9, 30) and dt.hour < 16
            minute.setdefault(tid, []).append(bar)
        elif f[0] == "DAY":
            tk = f[1]
            dt = datetime.fromtimestamp(int(f[2]) / 1000, tz=ET)
            daily.setdefault(tk, []).append({
                "date": dt.date(), "o": float(f[3]), "h": float(f[4]),
                "l": float(f[5]), "c": float(f[6])})
    caps = {}
    for line in (HERE / "_306_caps.tsv").read_text().splitlines():
        f = line.split("\t")
        if f[0] == "CAP" and f[2] != "None":
            caps[f[1]] = float(f[2])
    return minute, daily, caps


# ── character + structure ────────────────────────────────────────────────────
def enrich(trade, daily, caps):
    tk, d0 = trade["ticker"], trade["filled_at"].astimezone(ET).date()
    days = daily.get(tk, [])
    pre = [d for d in days if d["date"] < d0]
    trade["adr20"] = (statistics.mean((d["h"] - d["l"]) / d["c"] for d in pre[-20:])
                      if len(pre) >= 10 else None)
    entry_day = next((d for d in days if d["date"] == d0), None)
    trade["gap"] = ((entry_day["o"] - pre[-1]["c"]) / pre[-1]["c"]
                    if entry_day and pre else None)
    trade["cap"] = caps.get(tk)
    trade["prior_day_high"] = pre[-1]["h"] if pre else None
    trade["hi20_pre"] = max((d["h"] for d in pre[-20:]), default=None) if pre else None
    trade["hi252_pre"] = max((d["h"] for d in pre[-252:]), default=None) if pre else None
    trade["daily"] = days


# ── core replay ──────────────────────────────────────────────────────────────
def holding_walk(trade, bars):
    """RTH bars fully inside the holding period: bar start >= filled_at, bar END
    <= closed_at (the exit-minute bar is EXCLUDED — a trigger cannot be claimed
    from the same minute the real exit fired; pessimistic)."""
    filled_ms = int(trade["filled_at"].timestamp() * 1000)
    end_ms = int(trade["closed_at"].timestamp() * 1000) if trade["closed_at"] else None
    return [b for b in bars if b["rth"] and b["t"] >= filled_ms
            and (end_ms is None or b["t"] + 60_000 <= end_ms)]


def replay(trade, bars, trig_price):
    """Operator's rule at trigger price trig_price. Returns dict; see module doc."""
    entry, risk = trade["entry"], trade["risk_ps"]
    walk = holding_walk(trade, bars)
    out = {"triggered": False, "ambiguous": False, "cf_R": trade["sim_actual_R"],
           "delta_R": 0.0, "trig_dt": None, "be_dt": None, "be_price": None,
           "partial_R": 0.0, "pre_legs": 0, "open_remainder": False,
           "trig_day_idx": None, "be_day_idx": None}
    if not walk or trig_price <= entry:
        return out
    days_seq = sorted({b["dt"].date() for b in walk})
    trig_i = next((i for i, b in enumerate(walk) if b["h"] >= trig_price), None)
    if trig_i is None:
        return out
    tb = walk[trig_i]
    out.update(triggered=True, trig_dt=tb["dt"],
               trig_day_idx=days_seq.index(tb["dt"].date()) + 1)
    # trigger fills at the level; a bar OPENING above the level fills at the open
    fill_trig = max(trig_price, tb["o"]) if tb["o"] > trig_price else trig_price

    # BE-touch scan — pessimistic same-bar resolution
    be_dt, be_price = None, None
    if tb["l"] <= entry:
        be_dt, be_price = tb["dt"], entry
        out["ambiguous"] = True
    else:
        for b in walk[trig_i + 1:]:
            if b["o"] <= entry:
                be_dt, be_price = b["dt"], b["o"]
                break
            if b["l"] <= entry:
                be_dt, be_price = b["dt"], entry
                break
    out["be_dt"], out["be_price"] = be_dt, be_price
    if be_dt is not None:
        out["be_day_idx"] = days_seq.index(be_dt.date()) + 1

    # counterfactual P&L per entry-share.
    # Real legs BEFORE the trigger execute in full (the existing ladder still ran);
    # the trigger then sells 1/3 (capped by what remains); post-trigger legs are
    # scaled to the counterfactual remainder; the BE-touch scratches whatever is left.
    pnl_ps, sold_pre = 0.0, 0.0
    legs = [(_parse_ts(l["time"]), l["shares"] / trade["shares"], l["price"])
            for l in trade["exits"]]
    for lt, frac, price in legs:
        if lt >= tb["dt"]:
            break
        pnl_ps += frac * (price - entry)
        sold_pre += frac
        out["pre_legs"] += 1
    real_rem = 1.0 - sold_pre
    part = min(1.0 / 3.0, real_rem)
    pnl_ps += part * (fill_trig - entry)
    out["partial_R"] = part * (fill_trig - entry) / risk if risk > 0 else None
    cf_rem = real_rem - part
    scale = (cf_rem / real_rem) if real_rem > 1e-9 else 0.0
    for lt, frac, price in legs:
        if lt < tb["dt"]:
            continue
        if be_dt is not None and lt >= be_dt:
            break
        take = scale * frac
        pnl_ps += take * (price - entry)
        cf_rem -= take
    if be_dt is not None and cf_rem > 1e-9:
        pnl_ps += cf_rem * (be_price - entry)
        cf_rem = 0.0
    if trade["status"] != "closed" and cf_rem > 1e-9:
        out["open_remainder"] = True          # still-open counterfactual remainder
    out["cf_R"] = pnl_ps / risk if risk > 0 else None
    if out["cf_R"] is not None and trade["sim_actual_R"] is not None:
        out["delta_R"] = out["cf_R"] - trade["sim_actual_R"]
    return out


def trig_price_for(trade, basis, level):
    e = trade["entry"]
    if basis == "pct":
        return e * (1 + level)
    if basis == "R":
        return e + level * trade["risk_ps"] if trade["risk_ps"] > 0 else None
    if basis == "adr":
        return e * (1 + level * trade["adr20"]) if trade["adr20"] else None
    raise ValueError(basis)


# ── reporting ────────────────────────────────────────────────────────────────
def fmt_r(x):
    return "   —  " if x is None else f"{x:+6.2f}"


def path_table(live, minute):
    print("\n== 1. LIVE COHORT — intraday path anatomy (RTH bars, t >= filled_at) ==")
    hdr = (f"{'tkr':<5} {'fill ET':<12} {'hold':<7} {'MFE%':>6} {'MFE_R':>6} "
           f"{'min→peak':>8} {'peakday':>7} {'hps_db':>7} {'MFEvsDB':>8}  shape")
    print(hdr)
    for t in live:
        bars = holding_walk(t, minute.get(t["id"], []))
        if not bars:
            print(f"{t['ticker']:<5} {t['filled_at'].astimezone(ET).strftime('%m-%d %H:%M'):<12} "
                  f"hold < 1 bar — MFE unmeasurable at minute granularity (bounded ~0)")
            continue
        end = t["closed_at"] or bars[-1]["dt"]
        peak = max(bars, key=lambda b: b["h"])
        mfe_pct = (peak["h"] - t["entry"]) / t["entry"] * 100
        mfe_r = (peak["h"] - t["entry"]) / t["risk_ps"]
        mins = (peak["dt"] - t["filled_at"]).total_seconds() / 60
        days_seq = sorted({b["dt"].date() for b in bars})
        pk_day = days_seq.index(peak["dt"].date()) + 1
        hold = (end - t["filled_at"]).total_seconds() / 3600
        dbdiff = "" if t["hps"] is None else f"{(peak['h'] - float(t['hps'])):+7.3f}"
        # shape: minutes above entry before first re-touch of entry
        first_be = next((b for b in bars if b["l"] <= t["entry"]), None)
        shape = ("never>entry" if mfe_pct <= 0.05 else
                 f"BE-touch d{days_seq.index(first_be['dt'].date())+1} "
                 f"{first_be['dt'].strftime('%H:%M')}" if first_be is not None else
                 "never touched entry again")
        print(f"{t['ticker']:<5} {t['filled_at'].astimezone(ET).strftime('%m-%d %H:%M'):<12} "
              f"{hold:6.1f}h {mfe_pct:6.2f} {mfe_r:6.2f} {mins:8.0f} {pk_day:>7} "
              f"{t['hps'] or 0:7.2f} {dbdiff:>8}  {shape}")


def sweep(trades, minute, label, levels_by_basis):
    print(f"\n== SWEEP — {label} (net cohort R, deployed-risk basis) ==")
    closed = [t for t in trades if t["status"] == "closed" and t["actual_R"] is not None]
    base = sum(t["actual_R"] for t in closed)
    print(f"cohort n={len(closed)} closed · actual net {base:+.2f}R")
    print(f"{'basis':<5} {'level':>6} {'trig_n':>6} {'BEscr':>5} {'ambig':>5} "
          f"{'netR':>8} {'ΔR':>7} {'bene':>6} {'cost':>6}  per-trade Δ (triggered only)")
    results = {}
    for basis, levels in levels_by_basis.items():
        for lv in levels:
            net, ntrig, nscr, namb, deltas = base, 0, 0, 0, []
            for t in closed:
                tp = trig_price_for(t, basis, lv)
                if tp is None:
                    continue
                r = replay(t, minute.get(t["id"], []), tp)
                net += r["delta_R"]
                if r["triggered"]:
                    ntrig += 1
                    namb += r["ambiguous"]
                    nscr += r["be_dt"] is not None
                    deltas.append((t["ticker"], r["delta_R"]))
            results[(basis, lv)] = net
            bene = sum(d for _, d in deltas if d > 0)
            cost = sum(d for _, d in deltas if d < 0)
            dstr = " ".join(f"{tk}{d:+.2f}" for tk, d in deltas)
            lvs = f"{lv*100:.0f}%" if basis in ("pct",) else (
                f"{lv:.1f}R" if basis == "R" else f"{lv:.1f}A")
            print(f"{basis:<5} {lvs:>6} {ntrig:>6} {nscr:>5} {namb:>5} "
                  f"{net:+8.2f} {net-base:+7.2f} {bene:+6.2f} {cost:+6.2f}  {dstr}")
    return results


def winners_cost(paper, minute):
    print("\n== 3. COST SIDE — paper WINNERS (would the rule have scratched them?) ==")
    winners = [t for t in paper if t["status"] == "closed" and t["pnl"] > 0]
    print(f"{'tkr':<6} {'hold_d':>6} {'actR':>6} {'risk%':>6} | per level: cfR (T=trig day, S=scratch day)")
    for basis, levels, tag in (("pct", [0.03, 0.05, 0.08, 0.10], "%"),
                               ("R", [1.0, 2.0, 3.0], "R"),
                               ("adr", [1.0, 2.0], "ADR")):
        print(f"--- basis {tag} ---")
        for t in winners:
            cells = []
            for lv in levels:
                tp = trig_price_for(t, basis, lv)
                if tp is None or t["actual_R"] is None:
                    cells.append("   n/a   ")
                    continue
                r = replay(t, minute.get(t["id"], []), tp)
                if not r["triggered"]:
                    cells.append("  no-trig ")
                else:
                    cf_disp = t["actual_R"] + r["delta_R"]   # db-actual + sim delta
                    s = f"{cf_disp:+5.2f}(T{r['trig_day_idx']}"
                    s += f",S{r['be_day_idx']})" if r["be_day_idx"] else ",-)"
                    cells.append(s)
            hold = (t["closed_at"] - t["filled_at"]).days
            act = fmt_r(t["actual_R"])
            print(f"{t['ticker']:<6} {hold:>6} {act:>6} {t['risk_ps']/t['entry']*100:5.1f}% | "
                  + " | ".join(cells))


def segments(live, paper, minute):
    print("\n== 4. CHARACTER SEGMENTATION (live closed 9; n per cell shown — most are too small) ==")
    closed = [t for t in live if t["status"] == "closed"]

    def seg_of(t):
        cap = t["cap"] or 0
        cap_t = "mega≥100B" if cap >= 1e11 else "large10-100B" if cap >= 1e10 else \
                "mid2-10B" if cap >= 2e9 else "small<2B"
        adr = t["adr20"] or 0
        adr_t = "ADR<4%" if adr < 0.04 else "ADR4-7%" if adr < 0.07 else "ADR≥7%"
        gap = t["gap"] or 0
        gap_t = "gap<5%" if gap < 0.05 else "gap5-10%" if gap < 0.10 else "gap≥10%"
        return cap_t, adr_t, gap_t

    print(f"{'tkr':<5} {'cap':>9} {'ADR20':>6} {'gap%':>6} {'risk%':>6} {'rsk/ADR':>7} "
          f"{'MFE%':>7} {'MFE/ADR':>7} {'MFE_R':>6}")
    for t in closed + [x for x in live if x["status"] != "closed"]:
        bars = holding_walk(t, minute.get(t["id"], []))
        mfe = max((b["h"] for b in bars), default=t["entry"])
        mfe_pct = (mfe - t["entry"]) / t["entry"]
        cap_s = f"{(t['cap'] or 0)/1e9:.1f}B"
        risk_pct = t["risk_ps"] / t["entry"]
        print(f"{t['ticker']:<5} {cap_s:>9} {(t['adr20'] or 0)*100:5.1f}% "
              f"{(t['gap'] or 0)*100:5.1f}% {risk_pct*100:5.1f}% "
              f"{risk_pct/(t['adr20'] or 1):7.2f} {mfe_pct*100:6.2f}% "
              f"{mfe_pct/(t['adr20'] or 1):6.2f} {(mfe-t['entry'])/t['risk_ps']:6.2f}"
              f"   {' / '.join(seg_of(t))}{' (OPEN)' if t['status']!='closed' else ''}")

    for axis, idx in (("cap", 0), ("ADR", 1), ("gap", 2)):
        groups = {}
        for t in closed:
            groups.setdefault(seg_of(t)[idx], []).append(t)
        print(f"\n-- by {axis} --")
        for g, ts in sorted(groups.items()):
            trig_frac = {}
            for lv in (0.03, 0.05, 0.08):
                n = 0
                for t in ts:
                    r = replay(t, minute.get(t["id"], []), trig_price_for(t, "pct", lv))
                    n += r["triggered"]
                trig_frac[lv] = n
            print(f"  {g:<14} n={len(ts)}  triggered@3/5/8%: "
                  f"{trig_frac[0.03]}/{trig_frac[0.05]}/{trig_frac[0.08]}"
                  f"   {'⚠ n too small for a level choice' if len(ts) < 6 else ''}")


def structural(live, paper, minute):
    print("\n== 5. STRUCTURAL TRIGGERS ==")
    print("-- 5a. where pre-entry structure sits vs entry (live cohort) --")
    print(f"{'tkr':<5} {'entry':>8} {'pdHigh%':>8} {'20dHi%':>8} {'52wHi%':>8}  (— = below entry, unusable as a profit trigger)")
    for t in live:
        def rel(x):
            if not x:
                return "     n/a"
            d = (x - t["entry"]) / t["entry"] * 100
            return f"{d:+7.2f}%"
        print(f"{t['ticker']:<5} {t['entry']:>8.2f} {rel(t['prior_day_high']):>8} "
              f"{rel(t['hi20_pre']):>8} {rel(t['hi252_pre']):>8}")

    print("\n-- 5b. 52wk-high as trigger where it is ABOVE entry (live closed) --")
    base = sum(t["actual_R"] for t in live if t["status"] == "closed")
    net = base
    for t in live:
        if t["status"] != "closed":
            continue
        hi = t["hi252_pre"]
        if hi and hi > t["entry"] * 1.005:
            r = replay(t, minute.get(t["id"], []), hi)
            net += r["delta_R"]
            if r["triggered"]:
                print(f"  {t['ticker']}: trigger {hi:.2f} hit d{r['trig_day_idx']} "
                      f"→ Δ{r['delta_R']:+.2f}R (act {t['actual_R']:+.2f}R)")
    print(f"  net {net:+.2f}R vs actual {base:+.2f}R "
          f"(structure above entry existed for "
          f"{sum(1 for t in live if t['status']=='closed' and t['hi252_pre'] and t['hi252_pre'] > t['entry']*1.005)} of 9)")

    print("\n-- 5c. day>=2 gap-up open trigger (sell 1/3 at open if open >= prior close×(1+G)) --")
    multiday = [t for t in live + paper
                if t["filled_at"] and (t["closed_at"] or datetime(2026, 7, 24, 21, tzinfo=ET))
                and t["status"] in ("closed", "filled")]
    for g in (0.02, 0.04):
        rows = []
        for t in multiday:
            days = t["daily"]
            d0 = t["filled_at"].astimezone(ET).date()
            d1 = (t["closed_at"].astimezone(ET).date() if t["closed_at"] else days[-1]["date"])
            hold = [d for d in days if d0 <= d["date"] <= d1]
            for i in range(1, len(hold)):
                gap = (hold[i]["o"] - hold[i - 1]["c"]) / hold[i - 1]["c"]
                if gap >= g and hold[i]["o"] > t["entry"]:
                    rows.append((t["ticker"], t["cohort"], i + 1, gap * 100,
                                 (hold[i]["o"] - t["entry"]) / t["risk_ps"]
                                 if t["risk_ps"] > 0 else float("nan")))
                    break
        print(f"  G={g*100:.0f}%: {len(rows)} of {len(multiday)} trades ever gap-up-opened above entry on d>=2:")
        for tk, coh, day, gp, r_at in rows:
            print(f"    {tk:<6}({coh}) d{day} open gap {gp:+.1f}% → sell level = {r_at:+.2f}R")


def main():
    trades = load_trades()
    minute, daily, caps = load_bars()
    for t in trades:
        enrich(t, daily, caps)
    live = [t for t in trades if t["cohort"] == "live"]
    paper = [t for t in trades if t["cohort"] == "paper"]
    bad = [t for t in paper if t["risk_ps"] <= 0]
    if bad:
        print(f"⚠ excluded from R aggregates (risk_ps<=0 — inverted/absent stop): "
              f"{[t['ticker'] for t in bad]}")
    paper = [t for t in paper if t["risk_ps"] > 0]

    path_table(live, minute)

    # sanity: leg-based sim actual vs DB actual (live 9 should match closely)
    print("\n-- sanity: leg-sim actual vs DB actual R (live closed) --")
    for t in live:
        if t["status"] == "closed":
            d = t["sim_actual_R"] - t["actual_R"]
            flag = "  ⚠" if abs(d) > 0.05 else ""
            print(f"  {t['ticker']:<5} db {t['actual_R']:+.3f}  legs {t['sim_actual_R']:+.3f}"
                  f"  diff {d:+.3f}{flag}")

    levels = {"pct": PCT_LEVELS, "R": R_LEVELS, "adr": ADR_LEVELS}
    sweep(live, minute, "LIVE closed 9", levels)

    print("\n-- 2b. LIVE per-trade trigger detail (representative levels) --")
    for t in live:
        if t["status"] != "closed":
            continue
        cells = []
        for basis, lv in (("pct", 0.03), ("pct", 0.08), ("R", 1.0), ("R", 2.0), ("adr", 1.0)):
            tp = trig_price_for(t, basis, lv)
            r = replay(t, minute.get(t["id"], []), tp) if tp else None
            lvs = f"{lv*100:.0f}%" if basis == "pct" else (f"{lv:.0f}R" if basis == "R" else "1ADR")
            if not r or not r["triggered"]:
                cells.append(f"{lvs}:–")
            else:
                cells.append(f"{lvs}:d{r['trig_day_idx']}{r['trig_dt'].strftime('%H:%M')}"
                             f"→Δ{r['delta_R']:+.2f}")
        print(f"  {t['ticker']:<5} " + "  ".join(cells))

    # SMCI open — report separately
    smci = next(t for t in live if t["status"] != "closed")
    print("\n-- SMCI (OPEN) counterfactual --")
    last_day = [d for d in smci["daily"] if d["date"] <= smci["filled_at"].astimezone(ET).date() + timedelta(days=30)][-1]
    print(f"  actual state: OPEN, stop {smci['hard_stop']} (−1R live), "
          f"{last_day['date']} close {last_day['c']:.2f} = "
          f"{(last_day['c'] - smci['entry']) / smci['risk_ps']:+.2f}R unrealized")
    for basis, lv in (("pct", 0.03), ("pct", 0.05), ("pct", 0.08), ("R", 1.0),
                      ("R", 2.0), ("R", 3.0), ("adr", 1.0)):
        tp = trig_price_for(smci, basis, lv)
        r = replay(smci, minute.get(smci["id"], []), tp)
        state = ("no-trigger" if not r["triggered"] else
                 f"trig d{r['trig_day_idx']} {r['trig_dt'].strftime('%m-%d %H:%M')} "
                 f"banked {r['partial_R']:+.2f}R, "
                 + (f"BE-scratched d{r['be_day_idx']} {r['be_dt'].strftime('%m-%d %H:%M')} "
                    f"→ locked {r['cf_R']:+.2f}R total, position CLOSED"
                    if r["be_dt"] else "remainder still OPEN with BE stop"))
        lvs = f"{lv*100:.0f}%" if basis == "pct" else (f"{lv}R" if basis == "R" else f"{lv}×ADR")
        print(f"  {lvs:>6}: trig={tp:.2f}  {state}")

    sweep(paper, minute, "PAPER closed (risk_ps>0)", levels)

    # R-basis fairness check: the early paper cohort contains degenerate stop
    # conventions (risk < 1.5% of entry: KURA 0.8%, GOOGL 0.8%, DELL 1.0%) where an
    # R-multiple trigger fires on noise. Live stops (ORB low / prior-day low) are
    # 1.1-6%. Re-run R-basis without the degenerate-stop trades.
    tight = [t for t in paper if t["risk_ps"] / t["entry"] < 0.015]
    print(f"\n-- R-basis re-run excluding degenerate stops (risk<1.5%: "
          f"{[t['ticker'] for t in tight]}) --")
    sweep([t for t in paper if t not in tight], minute,
          "PAPER excl. sub-1.5%-risk stops", {"R": R_LEVELS, "pct": [0.03, 0.05, 0.10]})

    winners_cost(paper, minute)
    segments(live, paper, minute)
    structural(live, paper, minute)

    # combined frontier
    print("\n== 6. COMBINED (live 9 + paper closed) net-R frontier ==")
    both = [t for t in live if t["status"] == "closed"] + paper
    base = sum(t["actual_R"] for t in both)
    print(f"n={len(both)} · actual {base:+.2f}R")
    for basis, lvls in levels.items():
        row = []
        for lv in lvls:
            net = base
            for t in both:
                tp = trig_price_for(t, basis, lv)
                if tp:
                    net += replay(t, minute.get(t["id"], []), tp)["delta_R"]
            lvs = f"{lv*100:.0f}%" if basis == "pct" else (
                f"{lv}R" if basis == "R" else f"{lv}A")
            row.append(f"{lvs}:{net:+.1f}")
        print(f"  {basis:<4} " + "  ".join(row))


if __name__ == "__main__":
    main()
