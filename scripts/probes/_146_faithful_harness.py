"""#146 FAITHFUL harness v2 (Block 4 T3) — replay-vs-replay, read-only.

v1 finding (2026-07-12): faithfulness-to-the-live-table is STRUCTURALLY IMPOSSIBLE — 20/21
live TRIGGERED events predate the 6/27-28 flag→HTF re-parameterization (90% runup gate,
Stage-2 200MA/52w, ADV/ADR floors, pole-volume) — the detector that produced them no longer
exists, and the CURRENT detector has N=1 live trigger. Friday's "incumbent +0.78R/N=19"
therefore describes the RETIRED detector.

The honest instrument for 0026-D2 ("drop the COILED conjunct") is REPLAY-VS-REPLAY: the
CURRENT classifier over the same historical days, two arms differing ONLY in the conjunct:
  arm WITH    — recent_stages from the DB (the live semantics)
  arm WITHOUT — recent_stages forced ['COILED']*5 (the conjunct neutralized)
Seed set = every ticker-day the old detector rated TIGHTENING/COILED/TRIGGERED (coverage
note: days the old detector rated only WATCH are not replayed — seed-set bias recorded).
Both arms settle identically (entry=base_high, stop=breakout-day low, 10 trading days,
break-day-EXCLUSIVE). D2's addressable set = WITHOUT-arm events absent from the WITH arm.

Run: docker cp → docker exec -w /app apollo-market python /tmp/_146_faithful_harness.py
"""
import asyncio
import re
import statistics
import sys

sys.path.insert(0, "/app")

from agents.market_intelligence import db
from agents.market_intelligence.flag_detector import (
    compute_flag_metrics, _HISTORY_DAYS, _COILED_LOOKBACK_DAYS,
)

FORCED = ["COILED"] * 5
HORIZON = 10
_REASON_RE = re.compile(r"close_([\d.]+)>base_high_close_([\d.]+)\s+vol_([\d.]+)x")


async def _live_inputs(conn, ticker, scan_date, forced_stages=None):
    """Replicate run_flag_scan's per-ticker inputs for ONE (ticker, scan_date)."""
    history = await db.get_recent_daily_history(ticker, _HISTORY_DAYS, end_date=scan_date)
    if not history or len(history) < 60:
        return None
    yesterday_map = await db.get_yesterday_flag_stages(scan_date)
    recent_map = await db.get_recent_flag_stages(scan_date, lookback_days=_COILED_LOOKBACK_DAYS)
    pivot_map = await db.get_yesterday_flag_pivots(scan_date)
    prior_pivot = pivot_map.get(ticker)
    return {
        "history": history,
        "yesterday_stage": yesterday_map.get(ticker),
        "recent_stages": forced_stages if forced_stages is not None else recent_map.get(ticker, []),
        "prior_pivot_date": prior_pivot[0] if prior_pivot else None,
        "prior_pivot_high": prior_pivot[1] if prior_pivot else None,
    }


def _replay(ticker, inputs):
    return compute_flag_metrics(
        inputs["history"], ticker=ticker,
        yesterday_stage=inputs["yesterday_stage"],
        recent_stages=inputs["recent_stages"],
        prior_pivot_date=inputs["prior_pivot_date"],
        prior_pivot_high=inputs["prior_pivot_high"],
    )


def settle(fwd_bars, entry, stop):
    risk = entry - stop
    if risk <= 0 or not fwd_bars:
        return None
    window = fwd_bars[:HORIZON]
    fwd_max_r = (max(b["high_price"] for b in window) - entry) / risk
    for b in window:
        if b["low_price"] is not None and float(b["low_price"]) <= stop:
            return (-1.0, fwd_max_r)
    return ((float(window[-1]["close"]) - entry) / risk, fwd_max_r)


def stats(rs, label):
    if not rs:
        return f"{label}: n=0"
    r = [x[0] for x in rs]
    winners = [v for v in r if v > 0]
    return (f"{label}: n={len(r)} median={statistics.median(r):+.2f}R mean={statistics.mean(r):+.2f}R "
            f"total={sum(r):+.1f}R win={100*len(winners)/len(r):.0f}% "
            f"avg-winner={statistics.mean(winners):+.2f}R" if winners else
            f"{label}: n={len(r)} median={statistics.median(r):+.2f}R mean={statistics.mean(r):+.2f}R "
            f"total={sum(r):+.1f}R win=0%")


async def main() -> int:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        # ── era report (v1's finding, kept as the header) ────────────────────
        known = await conn.fetch("""
            SELECT DISTINCT ON (ticker, pivot_high_date) ticker, scan_date
            FROM mi_flag_candidates
            WHERE stage='TRIGGERED' AND breakout_close IS NOT NULL AND base_high IS NOT NULL
            ORDER BY ticker, pivot_high_date, scan_date
        """)
        cur_era = [k for k in known if str(k["scan_date"]) >= "2026-06-27"]
        print(f"Era: {len(known)} live TRIGGERED events · {len(cur_era)} in the CURRENT (HTF) "
              f"detector era — the live table cannot validate the current classifier (v1 finding).")

        # ── two-arm replay over the seed set ─────────────────────────────────
        seed = await conn.fetch("""
            SELECT DISTINCT ticker, scan_date FROM mi_flag_candidates
            WHERE stage IN ('TIGHTENING','COILED','TRIGGERED')
            ORDER BY ticker, scan_date
        """)
        print(f"Seed set: {len(seed)} ticker-days (old-detector TIGHTENING+; coverage note: "
              f"old WATCH-only days not replayed).", flush=True)

        arm_with, arm_without = {}, {}
        for i, r in enumerate(seed):
            if (i + 1) % 300 == 0:
                print(f"  …{i+1}/{len(seed)}", flush=True)
            t, d = r["ticker"], r["scan_date"]
            base_inputs = await _live_inputs(conn, t, d)
            if base_inputs is None:
                continue
            m_with = _replay(t, base_inputs)
            if m_with.get("stage") == "TRIGGERED" and m_with.get("base_high") is not None:
                key = (t, m_with.get("pivot_high_date"))
                if key not in arm_with or d < arm_with[key][0]:
                    arm_with[key] = (d, float(m_with["base_high"]))
            inputs_f = dict(base_inputs, recent_stages=FORCED)
            m_wo = _replay(t, inputs_f)
            if m_wo.get("stage") == "TRIGGERED" and m_wo.get("base_high") is not None:
                key = (t, m_wo.get("pivot_high_date"))
                if key not in arm_without or d < arm_without[key][0]:
                    arm_without[key] = (d, float(m_wo["base_high"]))

        d2_extra = {k: v for k, v in arm_without.items() if k not in arm_with}
        print(f"\nArm WITH conjunct: {len(arm_with)} distinct trigger events "
              f"| arm WITHOUT: {len(arm_without)} | D2 addressable (extra): {len(d2_extra)}")

        async def settle_events(events):
            out, rows_out = [], []
            for (t, piv), (d, base_high) in sorted(events.items()):
                bars = await conn.fetch("""
                    SELECT trade_date, high_price::float, low_price::float, close
                    FROM mi_daily_closes WHERE ticker=$1 AND trade_date > $2
                    ORDER BY trade_date LIMIT $3
                """, t, d, HORIZON + 2)
                bd = await conn.fetchrow(
                    "SELECT low_price::float FROM mi_daily_closes WHERE ticker=$1 AND trade_date=$2", t, d)
                if not bd or bd["low_price"] is None:
                    continue
                s2 = settle([dict(b) for b in bars], base_high, bd["low_price"])
                if s2 is None:
                    continue
                out.append(s2)
                rows_out.append((t, str(d), s2[0], s2[1]))
            return out, rows_out

        with_settled, _ = await settle_events(arm_with)
        d2_settled, d2_rows = await settle_events(d2_extra)

        print("\n=== THE HONEST D2 TABLE (current classifier, replay-vs-replay) ===")
        print(stats(with_settled, "REPLAY-INCUMBENT (current rule WITH conjunct)"))
        print(stats(d2_settled, "D2 ADDRESSABLE   (extra events, conjunct dropped)"))
        if d2_settled:
            r = [x[0] for x in d2_settled]
            med = statistics.median(r)
            win = sum(1 for v in r if v > 0) / len(r)
            wr = ([x[0] for x in with_settled])
            wwin = (sum(1 for v in wr if v > 0) / len(wr)) if wr else 0.0
            f1 = len(r) >= 10 and med >= -0.25 and win >= wwin
            print(f"\nF1 SHIP RULE (N≥10 · median ≥ −0.25R · win ≥ replay-incumbent "
                  f"{100*wwin:.0f}%): N={len(r)} med={med:+.2f} win={100*win:.0f}% → "
                  f"{'SHIP-eligible' if f1 else 'NO-GO'}")
        print("\nD2 per-event (ticker date R fwd-max):")
        for t, d, rr, fm in sorted(d2_rows, key=lambda z: -z[2]):
            print(f"  {t:<6} {d}  {rr:+.2f}R  (fwd-max {fm:+.2f}R)")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
