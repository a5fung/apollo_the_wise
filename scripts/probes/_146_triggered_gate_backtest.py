"""#146 C1 — direct TIGHTENING→TRIGGERED (drop the COILED prerequisite) backtest (read-only).

ADR 0026 §3 D2. The change under test: TRIGGERED = close>base_high_close AND vol≥1.5× from
TIGHTENING too (drop the `coiled_today or was_coiled_recent` conjunct). This is a FAITHFUL replay,
not an approximation — it calls the detector's own `compute_flag_metrics` with
`recent_stages=['COILED']*5`, which forces `was_coiled_recent=True` so the trigger reduces to pure
`breakout_now` (the detector's own vol-ratio computation; zero re-derivation).

Two cohorts, settled identically (entry=base_high, stop=breakout-day low, fixed-stop → 10-trading-day
horizon, break-day-EXCLUSIVE so no entry-day lookahead):
  A INCUMBENT — the real COILED-triggered events (from mi_flag_candidates, deduped to distinct
    ticker/pivot). The baseline the change must beat.
  B DIRECT-TRIGGER — TIGHTENING rows that would have TRIGGERED with the conjunct dropped (were
    blocked by COILED in reality). The change's addressable cohort.
Ship rule F1: direct-trigger median R ≥ −0.25R AND win-rate ≥ incumbent's, at N≥10.
Forward-max R is reported as the upper bound (perfect exit). Read-only; the sitting rules the flip.

Run: docker cp then docker exec -w /app apollo-market python /tmp/_146_triggered_gate_backtest.py
"""
import asyncio
import statistics
import sys

sys.path.insert(0, "/app")

from agents.market_intelligence.db import get_pool
from agents.market_intelligence.flag_detector import compute_flag_metrics

HORIZON = 10          # trading days
FORCED_COILED = ["COILED"] * 5


def settle(fwd_bars, entry, stop):
    """fwd_bars = bars STRICTLY AFTER the breakout day, ascending. Returns (r, fwd_max_r, exit)."""
    risk = entry - stop
    if risk <= 0 or not fwd_bars:
        return None
    window = fwd_bars[:HORIZON]
    fwd_max_r = (max(b["high_price"] for b in window) - entry) / risk
    for b in window:
        if b["low_price"] is not None and b["low_price"] <= stop:
            return (-1.0, fwd_max_r, "stop")
    return ((window[-1]["close"] - entry) / risk, fwd_max_r, "horizon")


def stats(rs):
    if not rs:
        return "n=  0"
    r = [x[0] for x in rs]
    fm = [x[1] for x in rs]
    winners = [v for v in r if v > 0]
    win = 100 * len(winners) / len(r)
    avg_win = statistics.mean(winners) if winners else 0.0
    return (f"n={len(r):>3}  median={statistics.median(r):+5.2f}R  mean={statistics.mean(r):+5.2f}R  "
            f"total={sum(r):+6.1f}R  win={win:>3.0f}%  avg-winner={avg_win:+4.2f}R  "
            f"|  fwd-max med={statistics.median(fm):+5.2f}R (upper)")


async def main() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        # --- fetch all bars for every ticker we'll touch (one pass) ---
        incumbent = await conn.fetch("""
            SELECT DISTINCT ON (ticker, pivot_high_date)
                   ticker, scan_date, pivot_high_date, base_high::float AS base_high,
                   pivot_high_price::float AS pivot_high_price
            FROM mi_flag_candidates
            WHERE stage='TRIGGERED' AND breakout_close IS NOT NULL AND base_high IS NOT NULL
            ORDER BY ticker, pivot_high_date, scan_date
        """)
        tightening = await conn.fetch("""
            SELECT ticker, scan_date, pivot_high_date, pivot_high_price::float AS pivot_high_price
            FROM mi_flag_candidates
            WHERE stage='TIGHTENING' ORDER BY ticker, scan_date
        """)
        tickers = sorted({r["ticker"] for r in incumbent} | {r["ticker"] for r in tightening})
        bars_by_ticker = {}
        for t in tickers:
            rows = await conn.fetch("""
                SELECT trade_date, open_price::float, high_price::float, low_price::float,
                       close::float, volume::float
                FROM mi_daily_closes WHERE ticker=$1 ORDER BY trade_date
            """, t)
            bars_by_ticker[t] = [dict(r) for r in rows]

    def bars_after(t, d):
        return [b for b in bars_by_ticker.get(t, []) if b["trade_date"] > d]

    def bar_on(t, d):
        for b in bars_by_ticker.get(t, []):
            if b["trade_date"] == d:
                return b
        return None

    # ---- Cohort A: incumbent COILED-triggered, settled ----
    a_settled, a_skip = [], 0
    for r in incumbent:
        bd = bar_on(r["ticker"], r["scan_date"])
        if not bd or bd["low_price"] is None:
            a_skip += 1
            continue
        s = settle(bars_after(r["ticker"], r["scan_date"]), r["base_high"], bd["low_price"])
        if s:
            a_settled.append(s)
        else:
            a_skip += 1

    # ---- Cohort B: direct-trigger via faithful drop-COILED replay ----
    b_events = {}   # (ticker, pivot_high_date) -> (scan_date, base_high)
    for r in tightening:
        t, d = r["ticker"], r["scan_date"]
        hist = [b for b in bars_by_ticker.get(t, []) if b["trade_date"] <= d]
        if len(hist) < 60:
            continue
        rows = [{"trade_date": b["trade_date"], "open_price": b["open_price"],
                 "high_price": b["high_price"], "low_price": b["low_price"],
                 "close": b["close"], "volume": b["volume"]} for b in hist[-120:]]
        try:
            m = compute_flag_metrics(rows, ticker=t, recent_stages=FORCED_COILED,
                                     yesterday_stage="TIGHTENING",
                                     prior_pivot_date=r["pivot_high_date"], prior_pivot_high=r["pivot_high_price"])
        except Exception:
            continue
        if m.get("stage") != "TRIGGERED" or m.get("base_high") is None:
            continue
        key = (t, m.get("pivot_high_date"))
        if key not in b_events or d < b_events[key][0]:
            b_events[key] = (d, float(m["base_high"]))

    b_settled, b_skip = [], 0
    for (t, _piv), (d, base_high) in b_events.items():
        bd = bar_on(t, d)
        if not bd or bd["low_price"] is None:
            b_skip += 1
            continue
        s = settle(bars_after(t, d), base_high, bd["low_price"])
        if s:
            b_settled.append(s)
        else:
            b_skip += 1

    # ---- Validation: does the drop-COILED replay reproduce the KNOWN incumbent triggers? ----
    # (faithfulness + confound check: replay base_high vs table base_high on the same 21 events)
    repro, base_match, base_div = 0, 0, []
    for r in incumbent:
        t, d = r["ticker"], r["scan_date"]
        hist = [b for b in bars_by_ticker.get(t, []) if b["trade_date"] <= d]
        if len(hist) < 60:
            continue
        rows = [{"trade_date": b["trade_date"], "open_price": b["open_price"],
                 "high_price": b["high_price"], "low_price": b["low_price"],
                 "close": b["close"], "volume": b["volume"]} for b in hist[-120:]]
        try:
            m = compute_flag_metrics(rows, ticker=t, recent_stages=FORCED_COILED, yesterday_stage="COILED",
                                     prior_pivot_date=r["pivot_high_date"], prior_pivot_high=r["pivot_high_price"])
        except Exception:
            continue
        if m.get("stage") == "TRIGGERED":
            repro += 1
            rbh = m.get("base_high")
            if rbh is not None and abs(float(rbh) - r["base_high"]) / r["base_high"] < 0.01:
                base_match += 1
            else:
                base_div.append((t, round(r["base_high"], 2), round(float(rbh), 2) if rbh else None))
    print(f"Replay validation: reproduced {repro}/{len(incumbent)} known incumbent triggers as TRIGGERED; "
          f"base_high match {base_match}/{repro} (±1%)")
    if base_div:
        print(f"  base_high divergences (ticker, table, replay): {base_div[:6]}")
    print()

    print(f"Cohort A (incumbent COILED-triggered): {len(incumbent)} events, {len(a_settled)} settled, {a_skip} skipped")
    print(f"  {stats(a_settled)}\n")
    print(f"Cohort B (direct-trigger, COILED dropped): {len(b_events)} distinct events, {len(b_settled)} settled, {b_skip} skipped")
    print(f"  {stats(b_settled)}\n")

    if a_settled and b_settled:
        a_r = [x[0] for x in a_settled]
        b_r = [x[0] for x in b_settled]
        a_win = sum(1 for v in a_r if v > 0) / len(a_r)
        b_win = sum(1 for v in b_r if v > 0) / len(b_r)
        b_med = statistics.median(b_r)
        f1 = (len(b_r) >= 10) and (b_med >= -0.25) and (b_win >= a_win)
        print("=== SHIP-RULE F1 (direct-trigger median ≥ −0.25R AND win ≥ incumbent, N≥10) ===")
        print(f"  N={len(b_r)} (≥10: {len(b_r)>=10}) · median={b_med:+.2f}R (≥−0.25: {b_med>=-0.25}) · "
              f"win={100*b_win:.0f}% vs incumbent {100*a_win:.0f}% ({b_win>=a_win})")
        print(f"  VERDICT: {'SHIP (rec GO to sitting)' if f1 else 'NO-GO / insufficient'}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
