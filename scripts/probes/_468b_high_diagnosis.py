#!/usr/bin/env python3
"""#468b — WHY is live MAGNA53 HIGH realized-R negative? (READ-ONLY diagnosis).

Decomposes the -19.1R (31 closed magna53 trades, mean -0.62R) into attributable
buckets: SELECTION / ENTRY / STOP-GEOMETRY / STOP-EXECUTION / EXIT-MANAGEMENT.
Pure local computation over the #468 TSVs (no prod access, no code change — THE
LINE holds). Reuses _468_moderate_realized_r loaders + reconstruction verbatim.

Findings doc: docs/analysis/468b_high_realized_r_diagnosis_2026-07-18.md
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))

import _468_moderate_realized_r as p               # noqa: E402 (probe module, reused)
from agents.market_intelligence import anticipation as de  # noqa: E402


def _median(xs):
    s = sorted(xs)
    if not s:
        return float("nan")
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def main() -> None:
    cohort = p.load_cohort()
    daily = p.load_daily()
    minute = p.load_minute()
    trades = p.load_trades()

    coh_by = {(r["ticker"], r["alert_date"]): r for r in cohort if r["tier"] == "HIGH"}

    # ── reconstruct HIGH as-if (same machinery as the probe's settle_tier) ──
    recon_by: dict[tuple, dict] = {}
    for r in cohort:
        if r["tier"] != "HIGH":
            continue
        gate, sub_m = p.eligibility(r)
        if gate != "ok":
            recon_by[(r["ticker"], r["alert_date"])] = {"outcome": gate}
            continue
        bars = daily.get(r["ticker"])
        ai = p.idx_of_date(bars, r["alert_date"]) if bars else None
        if ai is None or len(bars) - 1 - ai < p.SETTLE_FWD:
            recon_by[(r["ticker"], r["alert_date"])] = {"outcome": "no_daily"}
            continue
        raw = minute.get((r["ticker"], r["alert_date"]))
        if not raw:
            recon_by[(r["ticker"], r["alert_date"])] = {"outcome": "no_minute"}
            continue
        rth = de.polygon_to_rth_minutes(raw, r["alert_date"])
        rec = p.reconstruct(rth, sub_m, p.atr14_prior_close(bars, ai),
                            bars[ai + 1: ai + 1 + p.SETTLE_FWD])
        recon_by[(r["ticker"], r["alert_date"])] = rec

    # ── per-trade table for the 31 closed ──
    closed = [t for t in trades if t["status"] == "closed"
              and t["total_pnl"] is not None and (t["risk_dollars"] or 0) > 0]
    rows = []
    for t in closed:
        key = (t["ticker"], t["alert_date"])
        c = coh_by.get(key, {})
        rec = recon_by.get(key, {"outcome": "absent"})
        r_act = t["total_pnl"] / t["risk_dollars"]
        day0 = bool(t["closed_at"]) and t["closed_at"][:10] == t["alert_date"]
        hold_d = None
        hold_min = None
        if t["filled_at"] and t["closed_at"]:
            f = datetime.fromisoformat(t["filled_at"])
            cl = datetime.fromisoformat(t["closed_at"])
            hold_d = (cl.date() - f.date()).days
            hold_min = (cl - f).total_seconds() / 60
        stop_dist = (100 * (t["entry_price"] - t["orb_low"]) / t["entry_price"]
                     if t["entry_price"] and t["orb_low"] and t["entry_price"] > t["orb_low"]
                     else None)
        entry_slip = (100 * (t["entry_price"] - t["orb_high"]) / t["orb_high"]
                      if t["entry_price"] and t["orb_high"] else None)
        rows.append({
            "ticker": t["ticker"], "date": t["alert_date"], "mode": t["account_mode"],
            "r": r_act, "pnl": t["total_pnl"], "risk": t["risk_dollars"],
            "day0": day0, "hold_d": hold_d, "hold_min": hold_min,
            "r3": "r3" in (t["skip_reason"] or ""),
            "stop_dist": stop_dist, "entry_slip": entry_slip,
            "ep_score": c.get("ep_score"), "cq": c.get("cq", ""),
            "auth": c.get("authority", ""), "fwd_5d": c.get("fwd_5d"),
            "recon": rec.get("r") if rec.get("outcome") == "filled" else None,
            "recon_outcome": rec.get("outcome"),
            "period": p.period_of(t["alert_date"]),
        })
    rows.sort(key=lambda x: x["r"])

    tot = sum(x["r"] for x in rows)
    print(f"#468b — 31 closed magna53 diagnosis · total {tot:+.1f}R · "
          f"mean {tot/len(rows):+.2f}R · median {_median([x['r'] for x in rows]):+.2f}R")
    mean = tot / len(rows)
    var = sum((x["r"] - mean) ** 2 for x in rows) / (len(rows) - 1)
    print(f"  std {var ** 0.5:.2f}R · SE(mean) {(var / len(rows)) ** 0.5:.2f}R\n")

    def _s(v, fmt):
        return format(v, fmt) if v is not None else "?"

    print(f"{'ticker':<6} {'date':<11} {'mode':<6} {'R':>6} {'pnl$':>9} {'risk$':>8} "
          f"{'d0':>3} {'hold':>5} {'min':>6} {'r3':>3} {'stop%':>6} {'slip%':>6} "
          f"{'score':>6} {'cq':<8} {'fwd5d%':>7} {'recon':>7} {'Da-r':>6} {'per':<9}")
    for x in rows:
        d = (x["r"] - x["recon"]) if x["recon"] is not None else None
        recon_s = _s(x["recon"], "+.2f") if x["recon"] is not None else x["recon_outcome"][:7]
        print(f"{x['ticker']:<6} {x['date']:<11} {x['mode']:<6} {x['r']:>+6.2f} "
              f"{x['pnl']:>9.0f} {x['risk']:>8.0f} "
              f"{'Y' if x['day0'] else '.':>3} "
              f"{_s(x['hold_d'], 'd'):>5} "
              f"{_s(x['hold_min'], '.0f'):>6} "
              f"{'Y' if x['r3'] else '.':>3} "
              f"{_s(x['stop_dist'], '.1f'):>6} "
              f"{_s(x['entry_slip'], '+.2f'):>6} "
              f"{_s(x['ep_score'], '.0f'):>6} "
              f"{x['cq'][:8]:<8} "
              f"{_s(x['fwd_5d'], '+.1f'):>7} "
              f"{recon_s:>7} "
              f"{_s(d, '+.2f') if d is not None else '':>6} "
              f"{x['period']:<9}")

    # ── outcome classes ──
    win = [x for x in rows if x["r"] > 0.05]
    scr = [x for x in rows if -0.05 <= x["r"] <= 0.05]
    los = [x for x in rows if x["r"] < -0.05]
    print(f"\nclasses: winners {len(win)} ({sum(x['r'] for x in win):+.1f}R) · "
          f"scratch {len(scr)} ({sum(x['r'] for x in scr):+.1f}R) · "
          f"losers {len(los)} ({sum(x['r'] for x in los):+.1f}R)")
    d0stops = [x for x in rows if x["day0"] and x["r"] < 0]
    print(f"day-0 negative exits: {len(d0stops)} trades, {sum(x['r'] for x in d0stops):+.1f}R "
          f"(median hold {_median([x['hold_min'] for x in d0stops if x['hold_min'] is not None]):.0f} min)")

    # ── the bucket decomposition ──
    print("\n── BUCKETS ──")
    # (1) STOP-EXECUTION: loss beyond -1R (gap-through / slippage past the stop)
    exc = [(x, x["r"] + 1) for x in rows if x["r"] < -1]
    e1 = sum(v for _, v in exc)
    print(f"[E1] STOP-EXECUTION (loss beyond -1R): {e1:+.1f}R over {len(exc)} trades — "
          + ", ".join(f"{x['ticker']} {v:+.2f}" for x, v in exc))

    # (2) EXIT-MANAGEMENT: paired trades where recon settled positive but live gave it back
    give = [x for x in rows if x["recon"] is not None and x["recon"] > 0
            and x["r"] < x["recon"]]
    e2 = sum(x["r"] - x["recon"] for x in give)
    print(f"[E2] EXIT-MGMT giveback (recon>0, actual<recon): {e2:+.1f}R over {len(give)} — "
          + ", ".join(f"{x['ticker']} {x['r']-x['recon']:+.2f}" for x in give))
    beat = [x for x in rows if x["recon"] is not None and x["r"] > x["recon"]]
    print(f"     (live BEAT recon on {len(beat)}: "
          + ", ".join(f"{x['ticker']} {x['r']-x['recon']:+.2f}" for x in beat) + ")")

    # (3) full actual-vs-recon reconciliation
    paired = [x for x in rows if x["recon"] is not None]
    unpaired = [x for x in rows if x["recon"] is None]
    print(f"\nreconciliation: paired n={len(paired)} — recon sum "
          f"{sum(x['recon'] for x in paired):+.1f}R · actual sum "
          f"{sum(x['r'] for x in paired):+.1f}R · delta "
          f"{sum(x['r']-x['recon'] for x in paired):+.1f}R")
    print(f"  unpaired n={len(unpaired)} actual {sum(x['r'] for x in unpaired):+.1f}R — "
          + ", ".join(f"{x['ticker']}({x['recon_outcome']},{x['r']:+.2f})" for x in unpaired))

    # (4) SELECTION vs GEOMETRY via the fwd_5d counterfactual
    geom = [x for x in los if x["fwd_5d"] is not None and x["fwd_5d"] > 0]
    sel = [x for x in los if x["fwd_5d"] is not None and x["fwd_5d"] <= 0]
    nofwd = [x for x in los if x["fwd_5d"] is None]
    print(f"\nlosers split by what the STOCK did next (fwd_5d):")
    print(f"  stock went UP  (geometry victim): {len(geom)} trades {sum(x['r'] for x in geom):+.1f}R — "
          + ", ".join(f"{x['ticker']}(+{x['fwd_5d']:.0f}%)" for x in geom))
    print(f"  stock went DOWN (selection fail) : {len(sel)} trades {sum(x['r'] for x in sel):+.1f}R — "
          + ", ".join(f"{x['ticker']}({x['fwd_5d']:.0f}%)" for x in sel))
    print(f"  fwd_5d missing                   : {len(nofwd)} trades {sum(x['r'] for x in nofwd):+.1f}R — "
          + ", ".join(x["ticker"] for x in nofwd))

    # ── cuts ──
    def cut(label, keyfn):
        agg = defaultdict(list)
        for x in rows:
            agg[keyfn(x)].append(x["r"])
        print(f"\n{label}:")
        for k in sorted(agg, key=lambda k: str(k)):
            rs = agg[k]
            print(f"  {str(k):<12} n={len(rs):<3} total {sum(rs):+6.1f}R  mean {sum(rs)/len(rs):+.2f}R  "
                  f"win {100*sum(1 for r in rs if r>0)/len(rs):.0f}%")

    def band(x):
        s = x["ep_score"]
        if s is None:
            return "?"
        if s < 70:
            return "65-69"
        if s < 80:
            return "70-79"
        if s < 90:
            return "80-89"
        return "90+"
    cut("ep_score band (B6 cross-check)", band)
    cut("catalyst_quality", lambda x: x["cq"] or "?")
    cut("authority", lambda x: x["auth"] or "?")
    cut("period (judge window)", lambda x: x["period"])
    cut("account_mode", lambda x: x["mode"])
    cut("month", lambda x: x["date"][:7])
    cut("stop distance (entry→ORB-low)", lambda x: ("<2%" if x["stop_dist"] and x["stop_dist"] < 2
                                                    else "2-4%" if x["stop_dist"] and x["stop_dist"] < 4
                                                    else ">=4%" if x["stop_dist"] else "?"))

    # $ view (sizing shrank over time — R-weighting vs $-weighting)
    print(f"\n$ view: sum(pnl) ${sum(x['pnl'] for x in rows):+,.0f} · "
          f"paper ${sum(x['pnl'] for x in rows if x['mode']=='paper'):+,.0f} · "
          f"live ${sum(x['pnl'] for x in rows if x['mode']=='live'):+,.0f}")


if __name__ == "__main__":
    main()
