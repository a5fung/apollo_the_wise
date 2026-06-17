"""Daily chart renderer for the judge chart-vision axis (#267, W4).

Renders a point-in-time daily OHLCV chart (candles + 10/20/50 SMA stack + volume
pane) to PNG bytes — the image the grade judge "sees" so it can read the
methodology signal (MA-stack, contraction/tight consolidation, volume dry-up).

LOOKAHEAD CONTRACT (advisor 2026-06-17, blocks eval validity): the caller MUST
pass bars only through the **prior trading day** (alert_date − 1). The alert-day
daily candle contains the breakout-day range — the very outcome the judge is
asked to predict — so it must NOT appear in the chart. Alert-day intraday is the
tape-features domain (#299), separate. This module renders exactly the rows it is
given; it does not fetch, so the point-in-time cut lives at the data-fetch
boundary in the caller. The rendered title shows the last bar's date so a human
labeling the eval can SEE there is no alert-day bar.

mplfinance is the renderer (price + MA + volume in a few lines, vs hand-rolling
worse in PIL); pandas is already a dep. Both are import-guarded so a missing
install degrades to None (callers treat None as "no chart this row"), never a
hard crash on the judge path.
"""
from __future__ import annotations

import io
import logging
from datetime import date
from typing import Optional, Sequence

logger = logging.getLogger(__name__)

# Last N daily bars to show — ~6 months, enough to read the prior runup + the
# consolidation base without cramming the MAs.
_LOOKBACK_BARS = 130

# OHLCV column order expected from a mi_daily_closes-style row tuple/dict.
_OHLCV_KEYS = ("open_price", "high_price", "low_price", "close_price", "volume")


def bars_to_df(rows: Sequence[dict]):
    """Adapt mi_daily_closes-style rows → an mplfinance-ready OHLCV DataFrame
    (DatetimeIndex, columns Open/High/Low/Close/Volume), sorted ascending by
    date. Returns None if pandas is missing or no usable rows. Rows missing any
    OHLC field are dropped (a gap is better than a fabricated candle)."""
    try:
        import pandas as pd
    except ImportError:
        logger.error("pandas not installed — cannot build chart DataFrame")
        return None

    recs = []
    for r in rows:
        o, h, l, c, v = (r.get(k) for k in _OHLCV_KEYS)
        if None in (o, h, l, c):
            continue
        d = r.get("date") or r.get("close_date") or r.get("trade_date")
        if d is None:
            continue
        recs.append((d, float(o), float(h), float(l), float(c), float(v or 0)))
    if not recs:
        return None
    df = pd.DataFrame(recs, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    df["Date"] = pd.to_datetime(df["Date"])
    return df.set_index("Date").sort_index()


def render_daily_chart_png(
    df, ticker: str, as_of: Optional[date] = None, *, lookback_bars: int = _LOOKBACK_BARS,
) -> Optional[bytes]:
    """Render the last `lookback_bars` of `df` (an OHLCV DataFrame from
    `bars_to_df`, ALREADY cut to ≤ prior trading day by the caller) to a PNG.

    Returns PNG bytes, or None on any failure (missing dep / too few bars /
    render error) — the judge path treats None as "no chart for this row" and
    falls back to the text-only call. `as_of` is cosmetic (title only); the real
    point-in-time guarantee is which rows the caller put in `df`."""
    if df is None or len(df) < 20:  # too few bars to show an MA stack meaningfully
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")  # headless — no display in container/CI
        # The "charles" style requests medium/semibold weights absent from the
        # default font → a findfont WARNING per glyph (66× spam in the eval).
        # Harmless fallback to 400/700; quiet it.
        logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
        import mplfinance as mpf
    except ImportError:
        logger.error("mplfinance/matplotlib not installed — cannot render chart")
        return None

    try:
        view = df.tail(lookback_bars)
        last_bar = view.index[-1].date()
        title = f"\n{ticker}  daily  (as of {last_bar.isoformat()}, pre-alert)"
        style = mpf.make_mpf_style(base_mpf_style="charles", rc={"font.size": 9})
        buf = io.BytesIO()
        mpf.plot(
            view,
            type="candle",
            mav=(10, 20, 50),     # the methodology MA stack
            volume=True,          # volume dry-up is part of the signal
            style=style,
            title=title,
            figsize=(10, 7),
            tight_layout=True,
            savefig=dict(fname=buf, dpi=110, bbox_inches="tight"),
        )
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:  # noqa: BLE001 — render must never crash the judge path
        logger.warning(f"chart render failed for {ticker} as_of={as_of}: {e}")
        return None
