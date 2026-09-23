#!/usr/bin/env python3
"""#331 gap-alignment VISUAL dig-in (operator 2026-07-21). Renders annotated candlestick charts of
the extreme cases (biggest fwd-5d winners/losers per alignment class) and sends mosaics to Telegram:
as-of-alert-date structure with the alert day marked (blue) + the two levels drawn — trailing_high
(red = overhead ceiling) + base_high_15 (orange = the congestion top). So the structures the axis
scores can be eyeballed.

READ-ONLY (SELECTs) + sends Telegram photos. Re-run as the shadow cohort accrues.
Usage: docker exec apollo-market python scripts/probes/_331_gap_alignment_charts.py [n_per_side]
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
from collections import defaultdict
from pathlib import Path

import httpx
import matplotlib
matplotlib.use("Agg")
import mplfinance as mpf   # noqa: E402
import pandas as pd        # noqa: E402
from PIL import Image      # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agents.market_intelligence.db import get_pool  # noqa: E402

_BASE_HIGH_LOOKBACK = 15
_PRE, _POST = 65, 18          # sessions before / after the alert to plot
_CELL = (620, 460)            # mosaic cell size

_COHORT_SQL = """
    SELECT s.ticker, s.alert_date, o.fwd_5d_pct, o.fwd_10d_pct, COALESCE(r.regime,'?') AS regime
    FROM mi_theme_axis_shadow s
    LEFT JOIN mi_ep_scan_outcomes o ON o.ticker=s.ticker AND o.scan_date=s.alert_date
    LEFT JOIN mi_market_regime r ON r.regime_date=s.alert_date
    ORDER BY s.alert_date, s.ticker
"""
_BARS_SQL = """
    SELECT ticker, trade_date, open_price, high_price, low_price, close, volume
    FROM mi_daily_closes WHERE ticker=ANY($1::text[]) AND high_price IS NOT NULL
    ORDER BY ticker, trade_date
"""


def _prior_idx(bars, alert_date):
    idx = None
    for i, b in enumerate(bars):
        if b["trade_date"] < alert_date:
            idx = i
        else:
            break
    return idx


def classify(bars, alert_date):
    pidx = _prior_idx(bars, alert_date)
    if pidx is None:
        return {}
    prior_close = bars[pidx]["close"]
    L = next((b["open_price"] for b in bars if b["trade_date"] == alert_date), None)
    if not L or not prior_close:
        return {}
    gap = (float(L) / float(prior_close) - 1) * 100
    if pidx + 1 < _BASE_HIGH_LOOKBACK:
        return {}
    base_high_15 = float(max(b["high_price"] for b in bars[pidx - _BASE_HIGH_LOOKBACK + 1: pidx + 1]))
    trailing_high = float(max(b["high_price"] for b in bars[: pidx + 1]))
    marker = ("punch_through" if float(L) > trailing_high
              else "clears_base_near_miss" if float(L) > base_high_15
              else "fades_into_congestion")
    return {"marker": marker, "gap_pct": gap, "pidx": pidx,
            "base_high_15": base_high_15, "trailing_high": trailing_high}


def _chart_png(bars, r) -> "bytes | None":
    pidx = r["pidx"]
    lo, hi = max(0, pidx - _PRE), min(len(bars), pidx + 1 + _POST)
    window = bars[lo:hi]
    if len(window) < 20:
        return None
    df = pd.DataFrame([{
        "Date": pd.Timestamp(b["trade_date"]),
        "Open": float(b["open_price"]) if b["open_price"] else float(b["close"]),
        "High": float(b["high_price"]), "Low": float(b["low_price"]),
        "Close": float(b["close"]), "Volume": float(b["volume"] or 0),
    } for b in window]).set_index("Date")

    f5 = r["fwd_5d_pct"]
    f5s = f"{f5:+.0f}%" if f5 is not None else "n/a"
    title = (f"{r['ticker']} {r['alert_date']} {r['regime']}\n{r['marker']}  "
             f"gap{r['gap_pct']:+.0f}%  fwd5d {f5s}")
    hl = [h for h in (r["trailing_high"], r["base_high_15"]) if h]
    colors = (["red", "orange"])[:len(hl)]
    buf = io.BytesIO()
    try:
        mpf.plot(
            df, type="candle", volume=True, style="yahoo",
            hlines=dict(hlines=hl, colors=colors, linewidths=0.9, linestyle="--"),
            vlines=dict(vlines=[pd.Timestamp(r["alert_date"])], colors=["blue"], linewidths=1.1, alpha=0.5),
            title=title, figsize=(6.2, 4.6),
            savefig=dict(fname=buf, dpi=95),
        )
    except Exception as e:  # loud-ok: one un-plottable case shouldn't sink the mosaic
        print(f"  chart failed for {r['ticker']} {r['alert_date']}: {e}")
        return None
    buf.seek(0)
    return buf.getvalue()


def _mosaic(pngs) -> "bytes | None":
    if not pngs:
        return None
    imgs = [Image.open(io.BytesIO(p)).convert("RGB").resize(_CELL) for p in pngs]
    cols = 2
    rows = (len(imgs) + cols - 1) // cols
    canvas = Image.new("RGB", (_CELL[0] * cols, _CELL[1] * rows), "white")
    for i, im in enumerate(imgs):
        canvas.paste(im, ((i % cols) * _CELL[0], (i // cols) * _CELL[1]))
    out = io.BytesIO()
    canvas.save(out, "PNG")
    return out.getvalue()


async def _send(png, caption):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    ids = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").split(",")
    if not token or not ids or not ids[0].strip():
        print("  no telegram creds — skipping send")
        return
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"https://api.telegram.org/bot{token}/sendPhoto",
                         data={"chat_id": ids[0].strip(), "caption": caption},
                         files={"photo": ("gap_alignment.png", png, "image/png")})
        print(f"  sendPhoto -> {r.status_code}")


async def main():
    npc = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    pool = await get_pool()
    async with pool.acquire() as conn:
        cohort = [dict(r) for r in await conn.fetch(_COHORT_SQL)]
        tickers = sorted({r["ticker"] for r in cohort})
        bar_rows = await conn.fetch(_BARS_SQL, tickers)
    bars_by = defaultdict(list)
    for r in bar_rows:
        bars_by[r["ticker"]].append(dict(r))
    for t in bars_by:
        bars_by[t].sort(key=lambda b: b["trade_date"])

    rows = []
    for row in cohort:
        det = classify(bars_by.get(row["ticker"], []), row["alert_date"])
        if det.get("marker") and row["fwd_5d_pct"] is not None:
            rows.append({**row, **det})

    for m, cap in (("punch_through", "PUNCH-THROUGH (gap cleared all overhead → blue sky)"),
                   ("fades_into_congestion", "FADES-INTO-CONGESTION (gap landed back inside its base)")):
        sub = sorted([r for r in rows if r["marker"] == m], key=lambda r: r["fwd_5d_pct"])
        picks = sub[-npc:][::-1] + sub[:npc]     # top-N winners, then bottom-N losers
        pngs = [p for p in (_chart_png(bars_by[r["ticker"]], r) for r in picks) if p]
        mosaic = _mosaic(pngs)
        if mosaic:
            await _send(mosaic, f"#331 gap-alignment · {cap}\nTop {npc} winners + bottom {npc} losers by fwd-5d. "
                                f"red=trailing_high · orange=base_high_15 · blue=alert day.")
        print(f"{m}: {len(pngs)} charts")


if __name__ == "__main__":
    asyncio.run(main())
