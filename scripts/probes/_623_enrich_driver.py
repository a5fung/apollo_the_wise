"""#623 — server-side enrichment: REAL volume (both readings, clearly labeled) + regime, for the
FULL population (every mi_ep_scan_log ticker-day since bars exist, 2026-06-08+), not just the
sub-$500M rejected cohort #622 covered. Read-only against prod DB via the app's own pool.

Two volume readings computed per row, per the task's explicit instruction to label which is
which:
  EOD (lookahead -- characterization only):
    eod_volume_day0        : mi_daily_closes.volume on scan_date itself (full day, real)
    eod_vol_pctile_400d     : % of the trailing <=400 daily volumes (strictly before scan_date)
                              that are LESS than eod_volume_day0 -- literally the task's own SQL,
                              generalized to every row instead of one example ticker.
    eod_record_400d         : eod_volume_day0 > MAX(trailing <=400 daily volumes)

  PRE-09:31 (admission-relevant, no lookahead -- built ONLY from what would be known by 09:31):
    today_volume_0931       : passed in from the caller (today_volume column, or
                              rel_volume*adv when the column is absent and the derived value is
                              nonzero -- NEVER a fabricated zero; rows where neither is available
                              are passed through as null and reported missing, not defaulted)
    vol_pct_daily_bars      : _volume_percentile() (imported UNMODIFIED from ep_detector.py, the
                              live function) fed a rolling-20-trading-day mean-volume history
                              built from mi_daily_closes, matching #622's already-validated
                              method exactly (CHPT cross-check: 100.0)
    record_volume_400d_0931 : today_volume_0931 > MAX(trailing <=400 daily volumes, strictly
                              before scan_date) -- the operator's own CHPT framing ("42.9M vs a
                              prior 400-day max of 3.9M"), but using only PARTIAL, pre-09:31-known
                              volume against a fully-in-the-past historical max -- no lookahead.
                              A conservative signal: if PARTIAL volume already clears the full-day
                              historical max, that is unambiguous, no matter how the rest of the
                              day plays out.

Regime: nearest mi_market_regime row strictly before scan_date (same `<` convention as
#622sweep_driver -- that day's own regime is written that evening, after the gap).

CAPTURE ONCE: flushes each row immediately -- safe to interrupt/resume (skips ticker/scan_date
pairs already in OUT_PATH).

Run:
  docker cp scripts/probes/_623_enrich_driver.py apollo-market:/tmp/_623_enrich_driver.py
  docker cp scripts/probes/_623_tv_input.jsonl apollo-market:/tmp/_623_tv_input.jsonl
  docker exec -w /app apollo-market python /tmp/_623_enrich_driver.py
Output: /tmp/_623_enrich_out.jsonl
"""
import asyncio
import json
import sys
from datetime import date, timedelta

sys.path.insert(0, "/app")

from agents.market_intelligence import db  # noqa: E402
from agents.market_intelligence.ep_detector import _volume_percentile  # noqa: E402

IN_PATH = "/tmp/_623_tv_input.jsonl"
OUT_PATH = "/tmp/_623_enrich_out.jsonl"

_DAILY_SQL = """
    SELECT trade_date, volume FROM mi_daily_closes
    WHERE ticker=$1 AND trade_date < $2 AND trade_date >= $2 - 400 AND volume > 0
    ORDER BY trade_date DESC
"""
_DAY0_SQL = """
    SELECT volume, open_price FROM mi_daily_closes WHERE ticker=$1 AND trade_date=$2
"""
_REGIME_SQL = """
    SELECT regime FROM mi_market_regime WHERE regime_date < $1 ORDER BY regime_date DESC LIMIT 1
"""


def rolling20_history(daily_desc: list[dict], scan_date: date) -> list[float]:
    """Same shape as #622sweep_driver.rolling20_history: rolling 20-trading-day mean-volume
    series (matches adv_20's definition), oldest->newest, all strictly before scan_date
    (guaranteed by the SQL's own WHERE clause already, this is just the rolling transform)."""
    if len(daily_desc) < 20:
        return []
    asc = list(reversed(daily_desc))
    out = []
    for i in range(19, len(asc)):
        window = asc[i - 19:i + 1]
        out.append(sum(w["volume"] for w in window) / 20.0)
    return out


def eod_percentile(day0_vol: float, hist_volumes: list[float]) -> float | None:
    if not hist_volumes or day0_vol is None:
        return None
    below = sum(1 for v in hist_volumes if day0_vol > v)
    return round(below / len(hist_volumes) * 100, 1)


def _f(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


async def process_one(pool, ticker: str, scan_date_str: str, tv_0931):
    scan_date = date.fromisoformat(scan_date_str)
    rec = {"ticker": ticker, "scan_date": scan_date_str, "today_volume_0931": tv_0931}
    async with pool.acquire() as conn:
        hist_rows = await conn.fetch(_DAILY_SQL, ticker, scan_date)
        day0 = await conn.fetchrow(_DAY0_SQL, ticker, scan_date)
        regime_row = await conn.fetchrow(_REGIME_SQL, scan_date)

    hist = [{"trade_date": r["trade_date"], "volume": r["volume"]} for r in hist_rows]
    hist_volumes = [h["volume"] for h in hist]
    rec["n_hist_days"] = len(hist)

    day0_vol = _f(day0["volume"]) if day0 else None
    day0_open = _f(day0["open_price"]) if day0 else None
    rec["eod_volume_day0"] = day0_vol
    rec["day0_open_price"] = day0_open
    rec["eod_vol_pctile_400d"] = eod_percentile(day0_vol, hist_volumes)
    rec["eod_record_400d"] = (day0_vol > max(hist_volumes)) if (day0_vol and hist_volumes) else None
    rec["hist_max_400d"] = max(hist_volumes) if hist_volumes else None

    roll20 = rolling20_history(hist, scan_date)
    rec["n_roll20_points"] = len(roll20)
    if tv_0931 is not None and tv_0931 > 0:
        rec["vol_pct_daily_bars"] = _volume_percentile(tv_0931, roll20)
        rec["record_volume_400d_0931"] = (tv_0931 > max(hist_volumes)) if hist_volumes else None
    else:
        rec["vol_pct_daily_bars"] = None
        rec["record_volume_400d_0931"] = None

    rec["regime"] = regime_row["regime"] if regime_row else None
    return rec


async def main():
    with open(IN_PATH) as f:
        inputs = [json.loads(ln) for ln in f if ln.strip()]

    done = set()
    try:
        with open(OUT_PATH) as f:
            for ln in f:
                try:
                    r = json.loads(ln)
                    done.add((r["ticker"], r["scan_date"]))
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    print(f"{len(inputs)} rows, {len(done)} already done", file=sys.stderr, flush=True)

    pool = await db.get_pool()
    sem = asyncio.Semaphore(20)

    async def guarded(rec, i):
        key = (rec["ticker"], rec["scan_date"])
        if key in done:
            return None
        async with sem:
            try:
                out = await process_one(pool, rec["ticker"], rec["scan_date"], rec["today_volume_0931"])
            except Exception as e:
                out = {"ticker": rec["ticker"], "scan_date": rec["scan_date"], "error": str(e)}
        if i % 200 == 0:
            print(f"{i}/{len(inputs)}", file=sys.stderr, flush=True)
        return out

    with open(OUT_PATH, "a") as out_f:
        tasks = [guarded(rec, i) for i, rec in enumerate(inputs)]
        for coro in asyncio.as_completed(tasks):
            result = await coro
            if result is not None:
                out_f.write(json.dumps(result) + "\n")
                out_f.flush()
    print("DONE", file=sys.stderr, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
