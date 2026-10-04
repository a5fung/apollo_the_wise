"""#655 fix study (2026-10-04) — capture tonight's theme-correctness INPUTS from prod, read-only.

Loads exactly what `theme_correctness.run_theme_correctness_check` loads (the live board via
`get_active_themes(stale_after_days=7)`, the closes -> excess-return vectors, the scored universe,
the theme history), plus each board row's lifecycle columns (source, days_active, stage, score,
rs_avg, parent_theme, pct_above_20sma) and 60 days of theme history, then pickles it so the G1-G4
checks can be replayed offline under candidate engine rules. Writes NOTHING to the database.

Run inside apollo-market:  python scripts/probes/_655/fix_capture.py /tmp/655_capture.pkl
"""
from __future__ import annotations

import asyncio
import pickle
import sys
from collections import defaultdict
from datetime import timedelta

from agents.market_intelligence import ep_theme_belonging as etb
from agents.market_intelligence import market_adjusted_correlation as mac
from agents.market_intelligence import theme_correctness as tc
from agents.market_intelligence.db import get_active_themes, get_pool
from shared.dates import et_today


async def main(out_path: str) -> None:
    today = et_today()
    pool = await get_pool()
    board_rows = await get_active_themes(stale_after_days=7)
    themes = [{"name": r["name"], "stage": r["stage"], "tickers": list(r["tickers"] or [])}
              for r in board_rows]
    board_meta = [{k: r.get(k) for k in ("name", "stage", "score", "rs_avg", "parent_theme",
                                          "days_active", "pct_above_20sma", "source", "theme_date",
                                          "description")} for r in board_rows]
    board_tickers = {t for th in themes for t in th["tickers"]}
    async with pool.acquire() as c:
        sd = await c.fetchrow(
            "SELECT MAX(score_date) AS d FROM mi_stock_scores WHERE score_date <= $1", today)
        score_date = sd["d"] if sd else None
        scores_rows = await c.fetch(
            "SELECT ticker, rs_composite, sector FROM mi_stock_scores WHERE score_date = $1",
            score_date) if score_date else []
        hist = await c.fetch(
            "SELECT theme_date, name, stage, tickers, source FROM mi_themes WHERE theme_date >= $1 "
            "ORDER BY theme_date, id", today - timedelta(days=60))
    scores = {r["ticker"]: {"rs": r["rs_composite"], "sector": r["sector"]} for r in scores_rows}
    sector = {t: v["sector"] for t, v in scores.items() if v["sector"]}
    lookback = max(mac.CALENDAR_DAYS_FOR_LOOKBACK,
                   tc.LATENCY_WINDOW_DAYS + tc.LATENCY_LOOKBACK_SESSIONS + 30)
    all_tickers = board_tickers | set(scores) | {mac.MARKET_TICKER}
    closes, _n = await etb.fetch_closes(all_tickers, today - timedelta(days=lookback), today)
    sessions = mac.session_index(closes.get(mac.MARKET_TICKER, {}), today,
                                 mac.BELONGING_LOOKBACK_SESSIONS)
    market = mac.log_returns(closes.get(mac.MARKET_TICKER, {}), sessions)
    excess = mac.excess_returns(closes, sessions, market)
    history_by_name: dict = defaultdict(dict)
    for r in hist:
        history_by_name[r["name"]][r["theme_date"]] = set(r["tickers"] or [])
    report = tc.build_correctness_report(themes, excess, scores, sector,
                                         history=dict(history_by_name), latency=None)
    blob = {
        "captured_for": str(today), "score_date": str(score_date),
        "themes": themes, "board_meta": board_meta, "scores": scores, "sector": sector,
        "excess": excess, "sessions": [str(s) for s in sessions],
        "history": [dict(r) for r in hist], "report": report,
    }
    with open(out_path, "wb") as f:
        pickle.dump(blob, f)
    g3, g4 = report["g3"], report["g4"]
    print(f"captured {len(themes)} themes, {len(excess)} excess vectors, score_date {score_date}; "
          f"G3 {g3.get('rate_pct')}% ({g3.get('pass')}/{g3.get('n_judgeable')}), "
          f"G4 {g4.get('rate_pct')}% ({g4.get('small')} small) -> {out_path}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/655_capture.pkl"))
