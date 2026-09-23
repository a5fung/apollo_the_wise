#!/usr/bin/env python3
"""orb_5m_reentry_hybrid_replay — SD-5mclear re-run over the FULL 17-trade Day-1
stop-out set (extends the 08-07 `_545_reentry_sweep.py` N=15 run, which predated
NET (id 328) and FIGS (id 332), and had THC/TEAM settle mid-flight).

READ-ONLY EVIDENCE. Reuses `_545_reentry_sweep.sig_5m_clear` / `build_ctx` / `run_leg`
and every guard constant BYTE-IDENTICAL (WINNER_PEAK_R, HELD_R, LOSER_LEG_R,
MIN_R_UNIT_FRAC) — no threshold touched, only the population + the closing of two
stale data gaps:
  * NET, FIGS added (missing from the 08-07 run entirely — not degenerate-skipped,
    just never loaded).
  * THC's `_stop_floor_fwd_daily.tsv` / minute cache lacked session 10 (08-07,
    fetched before that day's close) — the time-stop settlement was unknown.
  * TEAM's day-0 (08-07) minute cache was captured mid-session (~15:36 ET) —
    refetched complete.
New data pulled 2026-08-09 via the same read-only psql / in-container Polygon
paths as every other _545/_stop_floor probe (SELECT-only; Polygon marginal $0).

THE LINE: evidence only. Nothing changed, nothing proposed. Entry/exit/stop
discipline is the operator's sole authority.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _stop_floor_forward_replay as sfr        # noqa: E402  (frozen contract)
import _545_reentry_sweep as sweep              # noqa: E402  (frozen SD-5mclear signal)

ET = sfr.ET

NET_FIGS_TRADE = HERE / "_545_net_figs_trade.tsv"
NET_FIGS_DAILY = HERE / "_545_net_figs_daily.tsv"
TEAM_TRADE = HERE / "_545_team_trade.tsv"
TEAM_DAILY = HERE / "_545_team_daily.tsv"
EXTEND_MINUTE = HERE / "_545_extend_minute.tsv"   # fresh NET/FIGS + refetched THC/TEAM


def load_minute_dedup() -> dict[str, list[dict]]:
    """Base cache (14 orig + old TEAM) with the fresh extend-pull OVERLAID by
    (ticker, t) — extend wins on any timestamp collision (it is the newer fetch:
    THC now carries 08-07, TEAM's 08-07 is now complete)."""
    by: dict[str, dict[int, dict]] = {}

    def ingest(bars_by_ticker):
        for tk, bars in bars_by_ticker.items():
            slot = by.setdefault(tk, {})
            for b in bars:
                slot[b["t"]] = b

    ingest(sfr.load_minute())                                  # 14 orig
    old = sfr.MINUTE
    sfr.MINUTE = HERE / "_545_team_minute.tsv"
    ingest(sfr.load_minute())                                  # old TEAM (partial day)
    sfr.MINUTE = old

    old = sfr.MINUTE
    sfr.MINUTE = EXTEND_MINUTE
    ingest(sfr.load_minute())                                  # NET, FIGS, fresh THC/TEAM (wins ties)
    sfr.MINUTE = old

    out: dict[str, list[dict]] = {}
    for tk, slot in by.items():
        out[tk] = sorted(slot.values(), key=lambda b: b["t"])
    return out


def load_all():
    trades = sfr.load_trades()                                  # 14 orig
    old = sfr.TRADES
    sfr.TRADES = TEAM_TRADE
    trades += sfr.load_trades()
    sfr.TRADES = NET_FIGS_TRADE
    trades += sfr.load_trades()
    sfr.TRADES = old
    assert len(trades) == 17, f"expected 17 trades, got {len(trades)}"

    minute = load_minute_dedup()

    daily = sfr.load_daily()
    for extra in (TEAM_DAILY, NET_FIGS_DAILY):
        for tk, rows in sfr.load_daily(extra).items():
            daily.setdefault(tk, []).extend(rows)
            daily[tk] = sorted({(r["date"], r["c"]): r for r in daily[tk]}.values(),
                                key=lambda d: d["date"])
    fwd_daily = sfr.load_daily(sfr.FWD_DAILY)                    # now carries THC 08-07
    return trades, minute, daily, fwd_daily


def main():
    trades, minute, daily, fwd_daily = load_all()
    for t in trades:
        t["adr20"] = sfr.adr20_pct(daily.get(t["ticker"], []), t["alert_date"])
        t["ctx"] = sweep.build_ctx(t, minute.get(t["ticker"], []))
        if t["ctx"] is None:
            sys.exit(f"{t['ticker']}: no entry-day bars — cache broken")

    print(f"orb_5m_reentry_hybrid_replay — SD-5mclear over {len(trades)} live Day-1 "
          f"stop-outs (full set; READ-ONLY EVIDENCE; THE LINE: nothing changed)")

    # contract check — leg-1 stop-only replay still reconciles at n=17
    tot_sim = tot_act = 0.0
    for t in trades:
        r = sfr.replay(t, minute[t["ticker"]], t["hard_stop"], partial_on=False)
        if not r.get("error"):
            tot_sim += r["r"]
        tot_act += t["pnl"] / (t["shares"] * (t["entry"] - t["hard_stop"]))
    print(f"contract check — leg-1 stop-only sim {tot_sim:+.2f}R vs actual "
          f"{tot_act:+.2f}R on n={len(trades)}")

    print("\n== population reference (POST-stop-out, in the ORIGINAL trade's r-unit) ==")
    print(f"{'tkr':<5} {'stop@ET':>16} {'d':>2} {'peak5R':>7} {'green':>6}  class")
    winners, nevergreen = set(), set()
    for t in sorted(trades, key=lambda x: -(x["ctx"]["peak5_r"] or -9)):
        c = t["ctx"]
        cls = ""
        if c["peak5_r"] is not None and c["peak5_r"] >= sweep.WINNER_PEAK_R:
            winners.add(t["ticker"]); cls = "BIG WINNER (peak, not close)"
        if not c["green"]:
            nevergreen.add(t["ticker"]); cls = "NEVER GREEN"
        print(f"{t['ticker']:<5} {c['stop_dt'].strftime('%m-%d %H:%M'):>16} "
              f"{c['stop_di']:>2} {c['peak5_r']:>+7.2f} {str(c['green']):>6}  {cls}")
    print(f"big winners (peak5 >= +{sweep.WINNER_PEAK_R:.0f}R): {sorted(winners)}")
    print(f"never green: {sorted(nevergreen)}")

    print("\n== SD-5mclear (orb_5m_reentry_hybrid_replay) per-trade ==")
    rows = {}
    fires = na = never_fires_no_window = 0
    for t in trades:
        bars = minute[t["ticker"]]
        leg, reason = sweep.sig_5m_clear(t, bars, t["ctx"])
        if leg is None:
            rows[t["ticker"]] = {"skip": reason}
            if reason == "no_signal:no_post_stop_window":
                never_fires_no_window += 1
            continue
        r = sweep.run_leg(t, bars, leg)
        rg = sweep.run_leg(t, bars, leg, gap_aware=True)
        rows[t["ticker"]] = {"leg": leg, "r": r, "r_gap": rg}
        fires += 1

    # ── corroborate every STOP exit against the official mi_daily_closes low ──
    fwd_daily_ext = dict(fwd_daily)
    for tk, rows_ in sfr.load_daily(NET_FIGS_DAILY).items():
        fwd_daily_ext.setdefault(tk, [])
        seen = {d["date"] for d in fwd_daily_ext[tk]}
        fwd_daily_ext[tk] += [d for d in rows_ if d["date"] not in seen]

    for t in trades:
        c = rows[t["ticker"]]
        if "skip" in c:
            print(f"{t['ticker']:<5} NO FIRE  ({c['skip']})")
        else:
            r = c["r"]; lg = c["leg"]
            settle = "" if r["settled"] else "  ⚠ UNSETTLED (mark-to-last)"
            leg_dollars = r["r"] * t["risk_dollars"]
            corrob = ""
            if r["exit_via"] == "stop":
                old_fwd = sfr.FWD_DAILY
                # official_low_check reads module-level fwd via the `fwd_daily` param name
                # collision workaround: call it directly with our extended table
                hit_dt, _ = r["stop_hit_bar"]
                day = next((d for d in fwd_daily_ext.get(t["ticker"], [])
                            if d["date"] == hit_dt.date().isoformat()), None)
                if day is None:
                    corrob = "  ⚠no-official-day (uncorroborated)"
                elif day["l"] > lg["stop"] + 1e-6:
                    corrob = f"  ⚠MINUTE-ONLY-PRINT (official low {day['l']} > stop {lg['stop']:.2f})"
                else:
                    corrob = f"  official-low OK (day low {day['l']} <= stop {lg['stop']:.2f})"
            mech = {"stop": "SECOND FULL STOP", "be_stop": "partial-then-scratch (+2R banked 1/3, BE rest)",
                    "time_stop_s10": "held to time-stop", "be_stop_samebar": "same-bar scratch"}.get(
                r["exit_via"], r["exit_via"])
            print(f"{t['ticker']:<5} fired d{lg['fire_day']} {lg['fill_dt'].strftime('%H:%M')} "
                  f"@{lg['entry']:.2f} stop {lg['stop']:.2f} (range {lg['note']}) "
                  f"-> realized {r['r']:+.2f}R (${leg_dollars:+.2f}) [{mech}] "
                  f"close_day={r['close_day']}{settle}{corrob}")

    denom = len(trades)
    fired_rows = {tk: c for tk, c in rows.items() if "leg" in c}
    rs = {tk: c["r"]["r"] for tk, c in fired_rows.items()}
    ds = {tk: c["r"]["r"] * next(x for x in trades if x["ticker"] == tk)["risk_dollars"]
          for tk, c in fired_rows.items()}
    held = sum(1 for tk in winners if rs.get(tk, 0) >= sweep.HELD_R)
    fired_on_winners = sorted(tk for tk in winners if tk in fired_rows)
    avoided = sum(1 for tk in nevergreen if rs.get(tk, 0) > sweep.LOSER_LEG_R)
    exit_via = {tk: c["r"]["exit_via"] for tk, c in fired_rows.items()}
    genuine_held = [tk for tk, ev in exit_via.items() if ev == "time_stop_s10" and rs[tk] > 0]
    partial_scratch = [tk for tk, ev in exit_via.items() if ev == "be_stop"]
    second_stops = [tk for tk, ev in exit_via.items() if ev == "stop" and rs[tk] < 0]
    net = sum(rs.values())
    net_d = sum(ds.values())
    ex_best = net - max(rs.values(), default=0)
    ex_best_d = net_d - max(ds.values(), default=0)
    unsettled = [tk for tk, c in fired_rows.items() if not c["r"]["settled"]]
    print(f"\n== SCORING ==")
    print(f"fill rate: {fires}/{denom} fired "
          f"({never_fires_no_window} of the non-fires had NO post-stop 5-min window at all — "
          f"mechanical non-fire, not an absent signal; the rest are genuine never_cleared)")
    print(f"of the 4 big forward movers {sorted(winners)}: fired on {fired_on_winners}, "
          f"never fired on {sorted(winners - set(fired_on_winners))}")
    print(f"  -> genuinely HELD (time-stop, still positive): {genuine_held}")
    print(f"  -> partial-then-scratch (+2R banked 1/3, breakeven on rest): {partial_scratch}")
    print(f"losers avoided (never fired / scratched, not a 2nd stop): {avoided}/{len(nevergreen)} "
          f"of the never-green names {sorted(nevergreen)}")
    print(f"SECOND FULL STOPS paid: {len(second_stops)}/{fires} fires -> {sorted(second_stops)}")
    print(f"net R (all fired legs): {net:+.2f}R (${net_d:+.2f})   "
          f"ex-best-trade: {ex_best:+.2f}R (${ex_best_d:+.2f})")
    print(f"unsettled (mark-to-last, not a final number): {unsettled}")

    print("\n(EVIDENCE ONLY — no change made or proposed; entry/exit/stop discipline is "
          "the operator's sole authority. THE LINE.)")


if __name__ == "__main__":
    main()
