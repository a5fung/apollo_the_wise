"""Side-by-side replay: existing range/vol-ratio COILED path vs proposed
"fresh-tightening" path that uses last-2-bar TR vs ATR-14.

Goal: validate that the new predicate fires on OKLO 5/4 (currently stuck WATCH)
and XNDU 4/29-4/30 (already COILED under existing logic — must not regress),
and does NOT fire on a control name during the same window.

Predicate under test:
  fresh_tight = (
      base_age >= 4
      AND max(TR% of last 2 bars) <= 0.6 * (ATR-14 / close * 100)
      AND max(vol of last 2 bars) <= ADV-20
  )

Promotion to COILED requires fresh_tight AND bodies_tight AND ma_aligned —
same shape as existing path, just swaps the contraction half.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime as _dt, timedelta as _td
from statistics import median as _median
from typing import Optional

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from agents.market_intelligence.flag_detector import (
    compute_flag_metrics,
    _wilder_tr,
    _atr_14,
    _find_pivot_high,
    _BODY_TIGHTNESS_MAX,
)
from agents.market_intelligence.parabolic_detector import _sma


FRESH_TIGHT_RATIO_MAX = 0.6
FRESH_TIGHT_BASE_AGE_MIN = 4


async def _fetch_yf_history(ticker: str, end_date: str, lookback_days: int = 130) -> list[dict]:
    import yfinance as yf

    def _fetch():
        end_dt = _dt.strptime(end_date, "%Y-%m-%d").date()
        start_dt = end_dt - _td(days=max(int(lookback_days * 1.6) + 30, 200))
        df = yf.Ticker(ticker).history(
            start=start_dt.isoformat(),
            end=(end_dt + _td(days=1)).isoformat(),
            auto_adjust=False,
        )
        return [{
            "trade_date": ts.date(),
            "open_price": float(r["Open"]),
            "high_price": float(r["High"]),
            "low_price":  float(r["Low"]),
            "close":      float(r["Close"]),
            "volume":     int(r["Volume"]) if r["Volume"] else 0,
        } for ts, r in df.iterrows()]

    return await asyncio.get_event_loop().run_in_executor(None, _fetch)


def compute_fresh_tighten(rows: list[dict]) -> dict:
    """Compute the proposed fresh-tightening metric on rows[-1] (today)."""
    out = {
        "fresh_2bar_max_tr_pct": None,
        "atr14_pct": None,
        "fresh_ratio": None,
        "fresh_2bar_max_vol": None,
        "adv20": None,
        "vol_dry_ok": None,
        "fresh_tight_fires": False,
    }
    if len(rows) < 21:
        return out
    today_idx = len(rows) - 1
    today = rows[today_idx]
    close_today = float(today["close"])

    # Need pivot + base_age
    pivot_idx, _ = _find_pivot_high(rows, today_idx)
    if pivot_idx is None:
        return out
    base_age = today_idx - pivot_idx - 1
    if base_age < FRESH_TIGHT_BASE_AGE_MIN:
        return out

    # Last 2 bars (today + yesterday) TR%
    trs_pct = []
    for i in (today_idx - 1, today_idx):
        prev_close = float(rows[i - 1]["close"]) if i > 0 else None
        tr = _wilder_tr(rows[i], prev_close)
        c = float(rows[i]["close"])
        trs_pct.append((tr / c * 100.0) if c > 0 else 0.0)
    fresh_max_tr_pct = max(trs_pct)
    out["fresh_2bar_max_tr_pct"] = fresh_max_tr_pct

    # ATR-14 → percent
    atr14 = _atr_14(rows, today_idx)
    if atr14 is None or close_today <= 0:
        return out
    atr14_pct = atr14 / close_today * 100.0
    out["atr14_pct"] = atr14_pct
    if atr14_pct <= 0:
        return out

    ratio = fresh_max_tr_pct / atr14_pct
    out["fresh_ratio"] = ratio

    # Last 2 bars max volume vs ADV-20
    vols = [float(rows[i]["volume"] or 0) for i in (today_idx - 1, today_idx)]
    fresh_max_vol = max(vols)
    adv20_window = [float(rows[i]["volume"] or 0)
                    for i in range(today_idx - 20, today_idx)]
    adv20 = sum(adv20_window) / 20 if len(adv20_window) == 20 else None
    out["fresh_2bar_max_vol"] = fresh_max_vol
    out["adv20"] = adv20
    if adv20 is None or adv20 <= 0:
        return out
    vol_dry_ok = fresh_max_vol <= adv20
    out["vol_dry_ok"] = vol_dry_ok

    out["fresh_tight_fires"] = (ratio <= FRESH_TIGHT_RATIO_MAX) and vol_dry_ok
    return out


GREEN = "\033[32m"; RED = "\033[31m"; YELLOW = "\033[33m"; CYAN = "\033[36m"
DIM = "\033[2m"; BOLD = "\033[1m"; RESET = "\033[0m"


def _stage_color(s: str) -> str:
    return {
        "TRIGGERED":   f"{BOLD}{RED}",
        "COILED":      f"{BOLD}{CYAN}",
        "TIGHTENING":  YELLOW,
        "WATCH":       GREEN,
        "INVALIDATED": RED,
        "unqualified": DIM,
    }.get(s, "") + f"{s:<11}" + RESET


def _proposed_stage(m: dict, fresh: dict) -> str:
    """What the stage WOULD be under the new combined logic."""
    if m["stage"] in ("INVALIDATED", "TRIGGERED", "unqualified"):
        return m["stage"]
    bodies_tight = (
        m.get("last_body_pct") is not None and m["last_body_pct"] <= _BODY_TIGHTNESS_MAX
        and m.get("prev_body_pct") is not None and m["prev_body_pct"] <= _BODY_TIGHTNESS_MAX
    )
    sma10 = m.get("sma_10"); sma20 = m.get("sma_20")
    ma_ok = sma10 is not None and sma20 is not None
    if not (bodies_tight and ma_ok):
        return m["stage"]
    if fresh["fresh_tight_fires"] and (m.get("base_age") or 0) >= FRESH_TIGHT_BASE_AGE_MIN:
        return "COILED*"  # asterisk = via fresh path
    return m["stage"]


async def replay(ticker: str, start: str, end: str) -> None:
    full = await _fetch_yf_history(ticker, end_date=end)
    if not full:
        print(f"{RED}No data for {ticker}{RESET}")
        return
    start_dt = _dt.strptime(start, "%Y-%m-%d").date()
    end_dt = _dt.strptime(end, "%Y-%m-%d").date()
    scan_dates = [r["trade_date"] for r in full if start_dt <= r["trade_date"] <= end_dt]

    print(f"\n{BOLD}{ticker}{RESET} fresh-tightening replay  "
          f"{DIM}({len(scan_dates)} scan dates){RESET}")
    print(f"  range: {scan_dates[0]} - {scan_dates[-1]}\n")

    print(f"{'date':<12}{'cur stage':<11}  {'NEW':<11}  "
          f"{'age':>4}  {'2bTR%':>6} {'ATR%':>6} {'ratio':>6}  "
          f"{'2bvol':>10} {'ADV20':>10} {'dry?':>5}  "
          f"{'body/prev':>11}  fires?")
    print("-" * 130)

    yesterday_stage: Optional[str] = None
    recent: list[str] = []
    for sd in scan_dates:
        idx = next((i for i, r in enumerate(full) if r["trade_date"] == sd), None)
        if idx is None:
            continue
        rows = full[: idx + 1]
        m = compute_flag_metrics(rows, ticker=ticker,
                                 yesterday_stage=yesterday_stage,
                                 recent_stages=recent.copy())
        fresh = compute_fresh_tighten(rows)
        new_stage = _proposed_stage(m, fresh)

        new_color = (f"{BOLD}{CYAN}{new_stage:<11}{RESET}"
                     if new_stage == "COILED*"
                     else _stage_color(new_stage.replace("*", "")))
        ratio_str = f"{fresh['fresh_ratio']:.2f}" if fresh["fresh_ratio"] else "—"
        atr_pct_str = f"{fresh['atr14_pct']:.1f}" if fresh["atr14_pct"] else "—"
        tr_pct_str = f"{fresh['fresh_2bar_max_tr_pct']:.1f}" if fresh["fresh_2bar_max_tr_pct"] else "—"
        vol_str = f"{int(fresh['fresh_2bar_max_vol']):>10,}" if fresh["fresh_2bar_max_vol"] else f"{'—':>10}"
        adv_str = f"{int(fresh['adv20']):>10,}" if fresh["adv20"] else f"{'—':>10}"
        dry_str = ("ok" if fresh["vol_dry_ok"] else "no") if fresh["vol_dry_ok"] is not None else "—"
        body_str = (f"{m['last_body_pct']:.2f}/{m['prev_body_pct']:.2f}"
                    if m.get("last_body_pct") is not None and m.get("prev_body_pct") is not None
                    else "—")
        fires = (f"{BOLD}{CYAN}YES{RESET}" if fresh["fresh_tight_fires"] else "no")

        print(f"{sd.isoformat():<12}{_stage_color(m['stage'])}  {new_color}  "
              f"{(m.get('base_age') or '—'):>4}  "
              f"{tr_pct_str:>6} {atr_pct_str:>6} {ratio_str:>6}  "
              f"{vol_str} {adv_str} {dry_str:>5}  "
              f"{body_str:>11}  {fires}")

        yesterday_stage = m["stage"]
        recent.append(m["stage"])
        if len(recent) > 10:
            recent.pop(0)


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tickers", default="OKLO,XNDU")
    p.add_argument("--start", default="2026-04-17")
    p.add_argument("--end", default="2026-05-04")
    args = p.parse_args()
    for t in args.tickers.split(","):
        await replay(t.strip(), args.start, args.end)
    print()


if __name__ == "__main__":
    asyncio.run(main())
