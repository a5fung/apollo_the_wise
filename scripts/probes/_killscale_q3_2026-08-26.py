"""Kill/scale quarterly review — ONE read-only prod capture (2026-08-26).

Run: ssh apollo@87.99.134.162 "docker exec -i apollo-market python -" < this file
Output: scripts/probes/_killscale_q3_2026-08-26_out.txt.  NEVER re-run to re-read.

READ-ONLY: only SELECTs + the shipped pure evaluator.  Writes nothing, mutates nothing.
"""
import asyncio, json

from agents.market_intelligence.kill_scale_bands import (
    assemble_band_inputs, evaluate_kill_scale_bands, get_active_override,
    format_band_line, risk_placed, current_losing_streak,
    _SAMPLE_FLOOR, _REDUCE_T20, _REDUCE_STREAK, _KILL_T20, _KILL_CUM_R,
    _SCALE_MIN_TRADES, _SCALE_T40, CALIBRATION_ENVELOPE,
)


async def main():
    print("=== Q0 MODULE IDENTITY ===")
    import agents.market_intelligence.kill_scale_bands as m
    print("file:", m.__file__)
    print("thresholds:", dict(KILL_T20=_KILL_T20, KILL_CUM_R=_KILL_CUM_R,
                              REDUCE_T20=_REDUCE_T20, REDUCE_STREAK=_REDUCE_STREAK,
                              SCALE_MIN_TRADES=_SCALE_MIN_TRADES, SCALE_T40=_SCALE_T40,
                              SAMPLE_FLOOR=_SAMPLE_FLOOR))
    print("envelope:", CALIBRATION_ENVELOPE)

    print("\n=== Q1 REAL EVALUATOR (assemble_band_inputs + evaluate_kill_scale_bands) ===")
    inputs = await assemble_band_inputs("live")
    verdict = evaluate_kill_scale_bands(
        inputs["realized_rs"], equity_above_start=inputs["equity_above_start"],
        drawdown_tier=inputs["drawdown_tier"])
    override = await get_active_override()
    print("drawdown_tier:", inputs["drawdown_tier"],
          "| equity_above_start:", inputs["equity_above_start"])
    print("open_positions:", inputs["open_positions"])
    print("override:", override)
    print("BAND LINE:")
    print(format_band_line(verdict, override, inputs.get("open_positions")).replace("*", ""))
    print("VERDICT DICT:", json.dumps({
        "band": verdict.band, "action": verdict.action, "reasons": verdict.reasons,
        "n_trades": verdict.n_trades, "trailing_20": verdict.trailing_20,
        "trailing_40": verdict.trailing_40, "streak": verdict.streak,
        "cum_r": verdict.cum_r}, default=str))
    print("REALIZED_RS (chronological):", json.dumps([round(x, 6) for x in inputs["realized_rs"]]))

    from agents.market_intelligence.db import get_pool, OPEN_POSITION_STATUSES
    pool = await get_pool()
    async with pool.acquire() as c:
        # --- Q2: the three cohort definitions, reconciled -------------------------------
        print("\n=== Q2 COHORT LADDER ===")
        yaml_pred = await c.fetchval(
            "SELECT COUNT(*) FROM mi_live_trades WHERE status='closed' "
            "AND account_mode='live' AND total_pnl IS NOT NULL")
        print("yaml predicate (closed/live/total_pnl NOT NULL):", yaml_pred)
        all_closed = await c.fetchval(
            "SELECT COUNT(*) FROM mi_live_trades WHERE status='closed' AND account_mode='live'")
        print("all closed live rows:", all_closed)
        band_sql = await c.fetchval(
            "SELECT COUNT(*) FROM mi_live_trades WHERE status='closed' "
            "AND account_mode='live' AND pnl_attribution IS NULL")
        print("assemble_band_inputs SQL rows (adds pnl_attribution IS NULL, "
              "NO total_pnl guard):", band_sql)
        print("kept after python degenerate guard (len(realized_rs)):",
              len(inputs["realized_rs"]))
        attrib = await c.fetch(
            "SELECT id, ticker, alert_date, pnl_attribution, total_pnl FROM mi_live_trades "
            "WHERE status='closed' AND account_mode='live' AND pnl_attribution IS NOT NULL "
            "ORDER BY alert_date, id")
        print("closed live rows WITH pnl_attribution (excluded from bands, IN yaml count):",
              [dict(r) for r in attrib])
        nullpnl = await c.fetch(
            "SELECT id, ticker, alert_date FROM mi_live_trades WHERE status='closed' "
            "AND account_mode='live' AND total_pnl IS NULL ORDER BY alert_date, id")
        print("closed live rows with total_pnl NULL (would raise in assemble):",
              [dict(r) for r in nullpnl])

        # --- Q3: signal_type contamination ----------------------------------------------
        print("\n=== Q3 SIGNAL_TYPE / STRATEGY BREAKDOWN ===")
        for sql, label in [
            ("SELECT signal_type, COUNT(*) FROM mi_live_trades WHERE status='closed' "
             "AND account_mode='live' AND total_pnl IS NOT NULL GROUP BY 1 ORDER BY 1",
             "yaml predicate cohort"),
            ("SELECT signal_type, COUNT(*) FROM mi_live_trades WHERE status='closed' "
             "AND account_mode='live' AND pnl_attribution IS NULL GROUP BY 1 ORDER BY 1",
             "band cohort"),
            ("SELECT signal_type, status, account_mode, COUNT(*) FROM mi_live_trades "
             "GROUP BY 1,2,3 ORDER BY 1,2,3", "whole mi_live_trades table"),
        ]:
            print(f"-- {label}:")
            for r in await c.fetch(sql):
                print("   ", dict(r))
        print("-- entry_mode / strategy columns present?")
        cols = await c.fetch(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name='mi_live_trades' ORDER BY ordinal_position")
        print("   ", [r["column_name"] for r in cols])

        # --- Q4: per-row classification, kept vs dropped, branch, R ---------------------
        print("\n=== Q4 PER-ROW (band cohort, chronological — the exact SELECT) ===")
        rows = await c.fetch(
            """
            SELECT id, ticker, alert_date, regime, signal_type, pnl_attribution,
                   total_pnl, risk_dollars, risk_dollars_actual, entry_shares,
                   entry_price, hard_stop, stop_price, position_size, partial_taken,
                   to_char(filled_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI') AS filled_et,
                   to_char(closed_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI') AS closed_et
            FROM mi_live_trades
            WHERE status = 'closed' AND account_mode = 'live'
              AND pnl_attribution IS NULL
            ORDER BY alert_date ASC, id ASC
            """)
        print("hdr: seq|id|ticker|alert_date|filled_et|closed_et|regime|signal_type|"
              "total_pnl|risk_dollars|risk_dollars_actual|entry_shares|entry_price|hard_stop|"
              "risk_placed|branch|R|kept")
        recomputed = []
        seq = 0
        for r in rows:
            t = dict(r)
            rp = risk_placed(t)
            branch = ("actual" if t.get("risk_dollars_actual") is not None
                      else ("derived" if rp is not None else "none"))
            kept = rp is not None and rp > 0
            R = (float(t["total_pnl"]) / rp) if (kept and t["total_pnl"] is not None) else None
            if kept:
                seq += 1
                recomputed.append(R)
            print(f"row: {seq if kept else '-'}|{t['id']}|{t['ticker']}|{t['alert_date']}|"
                  f"{t['filled_et']}|{t['closed_et']}|{t['regime']}|{t['signal_type']}|"
                  f"{t['total_pnl']}|{t['risk_dollars']}|{t['risk_dollars_actual']}|"
                  f"{t['entry_shares']}|{t['entry_price']}|{t['hard_stop']}|"
                  f"{rp}|{branch}|{'' if R is None else round(R,6)}|{kept}")

        print("\n=== Q5 RECOMPUTE PARITY CHECK ===")
        ref = [float(x) for x in inputs["realized_rs"]]
        same = len(ref) == len(recomputed) and all(
            abs(a - b) < 1e-9 for a, b in zip(ref, recomputed))
        print("element-wise identical to inputs['realized_rs']:", same)
        print("len(evaluator)=", len(ref), " len(recomputed)=", len(recomputed))
        if not same:
            print("evaluator:", ref)
            print("recomputed:", recomputed)

        # --- Q6: distance to each trigger, via the REAL evaluator -----------------------
        print("\n=== Q6 DISTANCE TO TRIGGERS (real evaluator, synthetic -1.0R appends) ===")
        base = list(ref)
        for k in range(0, 25):
            v = evaluate_kill_scale_bands(
                base + [-1.0] * k, equity_above_start=inputs["equity_above_start"],
                drawdown_tier=inputs["drawdown_tier"])
            print(f"k={k:2d} n={v.n_trades:3d} band={v.band:6s} "
                  f"t20={'n/a' if v.trailing_20 is None else round(v.trailing_20,4)} "
                  f"t40={'n/a' if v.trailing_40 is None else round(v.trailing_40,4)} "
                  f"streak={v.streak:3d} cum={round(v.cum_r,3)} reasons={v.reasons}")
        print("-- and with synthetic BREAKEVEN (0.0R) appends (streak arm counts r<=0):")
        for k in range(0, 20):
            v = evaluate_kill_scale_bands(
                base + [0.0] * k, equity_above_start=inputs["equity_above_start"],
                drawdown_tier=inputs["drawdown_tier"])
            print(f"k={k:2d} band={v.band:6s} "
                  f"t20={'n/a' if v.trailing_20 is None else round(v.trailing_20,4)} "
                  f"streak={v.streak:3d} cum={round(v.cum_r,3)} reasons={v.reasons}")
        print("-- roll-off drift: what leaves the trailing-20 window next")
        for i in range(max(0, len(base) - 24), len(base)):
            in20 = i >= len(base) - 20
            print(f"   idx={i} R={round(base[i],4)} in_current_t20={in20}")

        # --- Q7: equity + safeguard state ------------------------------------------------
        print("\n=== Q7 EQUITY / SAFEGUARD STATE ===")
        for r in await c.fetch(
                "SELECT safeguard, account_mode, state, last_transition_at, updated_at "
                "FROM mi_safeguard_state ORDER BY safeguard, account_mode"):
            print("   ", dict(r))
        for r in await c.fetch(
                "SELECT snapshot_date, equity FROM mi_account_equity_snapshots "
                "WHERE account_mode='live' ORDER BY snapshot_date ASC"):
            print("   eq:", dict(r))

        # --- Q8: override / transition / band-eval audit history --------------------------
        print("\n=== Q8 BAND AUDIT HISTORY ===")
        for r in await c.fetch(
                "SELECT event_type, to_char(created_at AT TIME ZONE 'America/New_York',"
                "'YYYY-MM-DD HH24:MI') AS et, summary, detail FROM mi_audit_log "
                "WHERE event_type LIKE 'kill_scale%' ORDER BY created_at"):
            print("   ", dict(r))
        print("-- band eval errors:")
        for r in await c.fetch(
                "SELECT to_char(created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI') "
                "AS et, summary FROM mi_audit_log WHERE event_type='kill_scale_band_eval_error' "
                "ORDER BY created_at DESC LIMIT 20"):
            print("   ", dict(r))
        print("-- replay_regression snapshots (input (b)):")
        for r in await c.fetch(
                "SELECT to_char(created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD') AS et, "
                "summary, detail FROM mi_audit_log WHERE event_type='replay_regression_snapshot' "
                "ORDER BY created_at DESC LIMIT 8"):
            print("   ", dict(r))

        # --- Q9: open book detail (report-only) ------------------------------------------
        print("\n=== Q9 OPEN BOOK ===")
        for r in await c.fetch(
                """SELECT id, ticker, alert_date, status, regime, entry_price, entry_shares,
                          hard_stop, stop_price, remaining_shares, realized_pnl, total_pnl,
                          partial_taken, COALESCE(hold_days,0) AS hold_days,
                          risk_dollars, risk_dollars_actual
                   FROM mi_live_trades WHERE status = ANY($1) AND account_mode='live'
                   ORDER BY alert_date""", list(OPEN_POSITION_STATUSES)):
            print("   ", dict(r))

        # --- Q10: 2R era boundary evidence ------------------------------------------------
        print("\n=== Q10 2R ERA (hard_stop vs orb geometry) ===")
        for r in await c.fetch(
                """SELECT id, ticker, alert_date, status, orb_high, orb_low, hard_stop,
                          entry_price, entry_shares,
                          to_char(filled_at AT TIME ZONE 'America/New_York','YYYY-MM-DD') AS filled_d
                   FROM mi_live_trades WHERE account_mode='live' AND filled_at IS NOT NULL
                   ORDER BY filled_at"""):
            d = dict(r)
            try:
                two_r = 2 * float(d["orb_low"]) - float(d["orb_high"])
                d["2R_stop_would_be"] = round(two_r, 4)
                d["is_2R"] = abs(float(d["hard_stop"]) - two_r) < 0.02
            except Exception as e:
                d["2R_stop_would_be"] = f"err {e}"
                d["is_2R"] = None
            print("   ", d)

    print("\n=== DONE ===")


asyncio.run(main())
