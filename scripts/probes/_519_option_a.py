#!/usr/bin/env python3
"""#519 OPTION A — the paid chart-vision run: does a model reading a point-in-time chart lean
the way he does on his labelled charts? Operator sign-off: docs/analysis/519_paid_run_scoping_2026-09-24.md
§"Option A — outcomes declared BEFORE it runs" — READ THAT FILE FIRST. This probe implements
lines 1-8 of that table and the decision rules exactly as pre-registered; nothing here is
scored, tuned or interpreted after the fact.

THE LINE: this is measurement only. It never writes to a live table, never touches strategy,
sizing, safeguards or trade state. Any use of its result — as a supporting note, as a filter —
is the operator's call, made after he reads the scorecard.

RUNS ON THE PROD SERVER, inside the container (scripts/ + docs/ are baked into the image):
    docker exec apollo-market python /app/scripts/probes/_519_option_a.py                 # dry run, $0
    docker exec apollo-market python /app/scripts/probes/_519_option_a.py --paid --max-usd 20
    docker exec apollo-market python /app/scripts/probes/_519_option_a.py --paid --max-usd 20 --resume
    docker exec apollo-market python /app/scripts/probes/_519_option_a.py --score-only /app/_519/calls.jsonl

DEV-ONLY, offline, no DB/API (renders 3 preview charts from the free read's captured bars):
    python3 scripts/probes/_519_option_a.py --bars-psv <path to bars.psv>

POPULATION (same as the free read, docs/analysis/519_free_chart_read_2026-09-24.md): REAL_EP 30,
APPROVED 9, BAD_CHART 21, OTHER_REJECTED 4 (shown, never scored) — DATA_DEFECT and POINTED_AT are
excluded, exactly as `_519_free_read.populations()` derives them from the two fixtures. 64 dates
total. Total calls = 64 dates x 3 replicates x 2 arms (plain / books) = 384.

THE CHARTS are point-in-time (bars strictly before the alert date, plus the alert-day OPEN only —
never its high/low/close) and ANONYMISED (no ticker, no date text anywhere; synthetic x-axis so no
real calendar date can leak even as a hidden tick). See `render_point_in_time_charts` — it takes
no ticker and no date, which is what makes the anonymisation structural rather than a filter
applied after the fact.

THE PROMPT is verbatim from the pre-registration (SYSTEM_TEXT / BOOK_INTRO_TEXT below) — changing
either string after this probe has run once would invalidate the run against its own declared
method.

ARTIFACT REUSE (P15): the scale-defect detector and the clean-history trim are the SAME functions
`_519_free_read.py` uses (factored out of that module's `_load_bars`/`_clean_len` this session,
2026-09-24, behaviour verified unchanged — a rerun of that probe against its captured PSV produced
byte-identical output before and after). The run-up rule (ANCHOR-75, `runup_low_pct_20 >= 75`) that
defines "the 12 the run-up rule misses" reuses `_structure_read_v3.structure_read_v3` /
`anchor75_rejects`, again not re-implemented.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "scripts" / "probes")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _519_free_read as free_read          # noqa: E402  (detect_artifact_days, clean_len_for)
import _structure_read_v3 as V3              # noqa: E402  (ANCHOR-75, reused not re-implemented)

from shared.llm_models import effective_model, pricing_for   # noqa: E402
from shared.llm_response import first_text, is_truncated, stop_reason, usage_tokens  # noqa: E402

from tests.fixtures.must_not_miss_eps import MUST_NOT_MISS                    # noqa: E402
from tests.fixtures.must_not_trade_charts import CHART_RULINGS                # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_SCRATCH = Path("/tmp/_519_option_a")

# The live judge model — same resolution the EP grade judge uses (shared/llm_models.py's
# RESOLVED_ROLES; never a hardcoded id). Module-level, resolved once at import, same convention
# as agents/market_intelligence/ep_grade_judge.py.
MODEL = effective_model("JUDGE_MODEL")

REPLICATES = 3
ARMS = ("plain", "books")
CONCURRENCY = 6
CALL_TIMEOUT_S = 120.0

# ── render windows (declared, not tuned) ──────────────────────────────────────────────
DAILY_WINDOW_SESSIONS = 170        # "roughly the last 8 months"
WEEKLY_WINDOW_WEEKS = 156          # "up to 3 years"
WEEKLY_MIN_WEEKS = 30              # below this: "weekly chart unavailable"
MIN_RENDER_BARS = 20               # chart_render.py's own floor — too few bars for an MA stack
NA_SCORING_MIN_CLEAN = 60          # below this: shown, never scored, never a pass or a fail
DAILY_MA_WINDOWS = (10, 20, 50, 200)
WEEKLY_MA_WINDOWS = (10, 40)
RENDER_LOOKBACK_SESSIONS = 900     # comfortably covers 156 weeks (~780 sessions) + MA runway

# ══════════════════════════════════════════════════════════════════════════════════════
# THE PROMPT — verbatim, pre-registered. Do not edit after this probe has run for real.
# ══════════════════════════════════════════════════════════════════════════════════════
SYSTEM_TEXT = (
    "You are reviewing the chart of a US stock that is gapping up at today's open, for a "
    "momentum trader who buys strong gap-ups (episodic pivots) out of sound price structure. "
    "You see two charts, both ending at YESTERDAY's close — nothing after that is shown: (1) "
    "daily candles for roughly the last 8 months with the 10, 20, 50 and 200-day moving averages "
    "and volume; the dashed horizontal line marks TODAY's opening price, where the stock is "
    "gapping to; (2) weekly candles for up to 3 years with the 10 and 40-week moving averages. "
    "The ticker and dates are hidden on purpose. Judge the chart only; you have no news. Rate it "
    "with exactly one word — garbage: a chart you would never touch; bad: not a buy; ok: "
    "tradeable, with a clear reservation; good: a strong chart for this kind of buy — and give "
    "one short sentence of reason in plain trader's words."
)

BOOK_INTRO_TEXT = (
    "Below are 24 annotated charts from two trading books — leaders in their buy zones and at "
    "their tops — with the authors' notes. They show what these authors look at. They are from "
    "2020–21 and are NOT the stock you are rating."
)

RATE_THIS_CHART_TEXT = "Rate this chart."
WEEKLY_UNAVAILABLE_TEXT = "weekly chart unavailable"

RATINGS = ("garbage", "bad", "ok", "good")
BAD_SIDE = frozenset({"garbage", "bad"})

RATING_SCHEMA = {
    "type": "object",
    "properties": {
        "rating": {"type": "string", "enum": list(RATINGS)},
        "reason": {"type": "string"},
    },
    "required": ["rating", "reason"],
    "additionalProperties": False,
}
OUTPUT_CONFIG = {"format": {"type": "json_schema", "schema": RATING_SCHEMA}}

BOOK_SETS = (
    ("docs/methodology/traderlion_2020_leaders_2026-09-23.md",
     "docs/methodology/operator_shared_charts/2026-09-23_traderlion_2020_leaders"),
    ("docs/methodology/boik_monster_stock_lessons_2026-09-23.md",
     "docs/methodology/operator_shared_charts/2026-09-23_boik_monster_stock_lessons_2020_2021"),
)
EXPECTED_BOOK_IMAGES = 24


# ══════════════════════════════════════════════════════════════════════════════════════
# POPULATION — the same 4 groups (64 rows) the free read scores, derived from the fixtures,
# never hand-listed.
# ══════════════════════════════════════════════════════════════════════════════════════

def load_population() -> list[tuple[str, str, str, str]]:
    """[(pop, ticker, iso_date, verdict), ...] — REAL_EP 30, APPROVED 9, BAD_CHART 21,
    OTHER_REJECTED 4. DATA_DEFECT and POINTED_AT are excluded (shown-not-scored is OTHER_REJECTED
    only, per the pre-registration). Reuses `_519_free_read.populations()` — the SAME derivation
    the already-scored free read used, not a second hand-count of the fixtures."""
    pops = free_read.populations()
    keep = ("REAL_EP", "APPROVED", "BAD_CHART", "OTHER_REJECTED")
    out: list[tuple[str, str, str, str]] = []
    for pop in keep:
        for tk, d, verdict in pops[pop]:
            out.append((pop, tk, d, verdict))
    return out


def operator_words_for(ticker: str, iso_date: str) -> str:
    """His verbatim words for (ticker, date), from `must_not_trade_charts.py`. Empty for a
    REAL_EP row (evidence-sourced, not an opinion)."""
    for r in CHART_RULINGS:
        if (r.ticker, r.alert_date) == (ticker, iso_date):
            return r.operator_words or ""
    return ""


# ══════════════════════════════════════════════════════════════════════════════════════
# BARS — canonical shape used across this module: {"date","open","high","low","close","volume"}.
# Small adapters to the shapes `_519_free_read` and `_structure_read_v3` each expect (reuse, not
# re-implementation, of the artifact/run-up logic that already lives there).
# ══════════════════════════════════════════════════════════════════════════════════════

def _canonical_bar(row: dict) -> dict:
    """A `get_prior_daily_ohlcv` row (trade_date/open_price/high_price/low_price/close_price/
    volume) -> this module's canonical bar shape."""
    return {
        "date": row["trade_date"], "open": float(row["open_price"]),
        "high": float(row["high_price"]), "low": float(row["low_price"]),
        "close": float(row["close_price"]), "volume": float(row["volume"] or 0.0),
    }


def _to_free_read_shape(bars: list[dict]) -> list[dict]:
    return [{"trade_date": b["date"], "open_price": b["open"], "close": b["close"],
             "volume": b["volume"]} for b in bars]


def _to_v3_shape(bars: list[dict]) -> list[dict]:
    return [{"trade_date": b["date"], "open_price": b["open"], "high_price": b["high"],
             "low_price": b["low"], "close": b["close"], "volume": b["volume"]} for b in bars]


def clean_trim(prior_bars: list[dict]) -> tuple[list[dict], int, list[date]]:
    """(clean_bars, clean_n, artifact_days) — `prior_bars` ascending, canonical shape, STRICTLY
    before the alert date. `clean_bars` is the suffix of `prior_bars` after the last scale-defect
    artifact day (see `_519_free_read`'s DATA ARTIFACTS rule); `clean_n == len(clean_bars)`."""
    fr_shape = _to_free_read_shape(prior_bars)
    artifact_days = free_read.detect_artifact_days(fr_shape)
    clean_n = free_read.clean_len_for(fr_shape, artifact_days)
    clean_bars = prior_bars[len(prior_bars) - clean_n:] if clean_n else []
    return clean_bars, clean_n, artifact_days


def anchor75_rejects_for(prior_bars: list[dict], alert_date: date, open_px: float,
                         clean_n: int) -> Optional[bool]:
    """Would ANCHOR-75 (the run-up rule already live/scored) reject this date? None when clean
    history is under the rule's own 20-session reach — 'cannot evaluate' is never a pass or a
    fail (`_519_free_read`'s own rule, applied identically here so 'the 12 the run-up rule
    misses' is the SAME 12, not a second cutline). Uses the FULL `prior_bars` (not the
    clean-trimmed slice) because `structure_read_v3` computes its own windows; only the runup
    field is nulled when clean history can't support it, mirroring `_519_free_read.measures()`."""
    if clean_n < 20:
        return None
    read = V3.structure_read_v3(_to_v3_shape(prior_bars), alert_date, open_px)
    v = read.get(V3.ANCHOR_75_METRIC)
    return None if v is None else bool(v >= V3.ANCHOR_75_CUTLINE)


# ══════════════════════════════════════════════════════════════════════════════════════
# RENDER — point-in-time, anonymised. Takes NO ticker, NO date: anonymisation is structural.
# ══════════════════════════════════════════════════════════════════════════════════════

def _synthetic_index(n: int, start: str = "2000-01-03"):
    import pandas as pd
    return pd.bdate_range(start, periods=n)


def _strip_identity(fig) -> None:
    """Clear every tick label / title on every axis. Called on the whole figure so a future
    mplfinance panel (there are 4: price, its twin, volume, its twin) can never grow an
    unhidden date axis by accident."""
    for ax in fig.axes:
        ax.set_xticks([])
        ax.set_title("")
    fig.suptitle("")


def _build_fig(df, mas: dict[int, Any], window: int, *, open_line: float | None = None):
    """One candle+volume+MA figure, built from a REAL-dated OHLCV DataFrame `df` (MAs already
    computed on the FULL `df` so a long MA has runway) but drawn against a SYNTHETIC sequential
    index — no real calendar date reaches the pixels, hidden ticks or not. Returns the matplotlib
    Figure, or None if there are too few bars to plot at all. Split out from the PNG-serialising
    wrapper below so a test can inspect `fig.texts` / axis tick labels directly (the anonymisation
    contract, #519's validity core) without decoding a PNG."""
    import matplotlib
    matplotlib.use("Agg")
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    import mplfinance as mpf

    view = df.tail(window)
    if len(view) < MIN_RENDER_BARS:
        return None
    view_mas = {w: s.reindex(view.index) for w, s in mas.items()}
    view_mas = {w: s for w, s in view_mas.items() if s.notna().any()}

    synth = _synthetic_index(len(view))
    view_r = view.copy()
    view_r.index = synth
    addplots = []
    for w, s in view_mas.items():
        sr = s.copy()
        sr.index = synth
        addplots.append(mpf.make_addplot(sr, width=0.9))

    style = mpf.make_mpf_style(base_mpf_style="charles", rc={"font.size": 9})
    kw = dict(type="candle", volume=True, style=style, figsize=(10, 7),
             returnfig=True, tight_layout=True)
    if addplots:
        kw["addplot"] = addplots
    fig, axes = mpf.plot(view_r, **kw)
    if open_line is not None:
        ax = axes[0]
        # A real gap can sit ABOVE every visible high (that is the whole point of an EP gap) —
        # mplfinance autoscales the y-axis from the OHLC data alone, so an axhline outside that
        # range would be drawn off-canvas and never seen. Widen the limits to include it before
        # drawing, rather than leaving the dashed line invisible on exactly the rows this chart
        # exists to show.
        lo, hi = ax.get_ylim()
        lo2, hi2 = min(lo, open_line), max(hi, open_line)
        if (lo2, hi2) != (lo, hi):
            pad = (hi2 - lo2) * 0.04
            ax.set_ylim(lo2 - pad, hi2 + pad)
        ax.axhline(open_line, linestyle="--", linewidth=1.0, color="black")
        va = "bottom" if open_line >= (lo + hi) / 2 else "top"
        ax.text(0.99, open_line, "today's open", ha="right", va=va, fontsize=8,
                transform=ax.get_yaxis_transform())
    _strip_identity(fig)
    return fig


def _fig_to_png(fig) -> bytes:
    import io
    import matplotlib.pyplot as plt
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def _render_one(df, mas: dict[int, Any], window: int, *, open_line: float | None = None):
    """PNG bytes (or None) for one candle+volume+MA panel — see `_build_fig`."""
    fig = _build_fig(df, mas, window, open_line=open_line)
    return None if fig is None else _fig_to_png(fig)


def render_point_in_time_charts(
    clean_bars: list[dict], open_px: float, *,
    daily_window: int = DAILY_WINDOW_SESSIONS, weekly_window: int = WEEKLY_WINDOW_WEEKS,
    weekly_min_weeks: int = WEEKLY_MIN_WEEKS,
) -> tuple[Optional[bytes], Optional[bytes], dict]:
    """(daily_png, weekly_png_or_None, meta). `clean_bars` — ascending, canonical shape, already
    trimmed to clean (post-artifact) history strictly before the alert date by the caller. NO
    ticker and NO date are parameters here; that is deliberate (#519's validity core) — this
    function cannot leak identity because it never receives any."""
    meta: dict = {"n_clean_sessions": len(clean_bars)}
    if len(clean_bars) < MIN_RENDER_BARS:
        meta["render_failed"] = True
        return None, None, meta

    import pandas as pd
    df = pd.DataFrame(clean_bars)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df = df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                            "close": "Close", "volume": "Volume"})

    daily_mas = {w: df["Close"].rolling(w).mean() for w in DAILY_MA_WINDOWS if len(df) >= w}
    meta["daily_mas_available"] = sorted(daily_mas)
    daily_png = _render_one(df, daily_mas, daily_window, open_line=open_px)

    weekly = df.resample("W-FRI").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()
    meta["n_weeks_all"] = len(weekly)
    weekly_png = None
    if len(weekly) >= weekly_min_weeks:
        weekly_mas = {w: weekly["Close"].rolling(w).mean() for w in WEEKLY_MA_WINDOWS
                      if len(weekly) >= w}
        meta["weekly_mas_available"] = sorted(weekly_mas)
        weekly_png = _render_one(weekly, weekly_mas, weekly_window, open_line=None)
    else:
        meta["weekly_unavailable"] = True
    return daily_png, weekly_png, meta


# ══════════════════════════════════════════════════════════════════════════════════════
# BOOK CONTENT (arm 2) — 24 annotated charts, matched image<->annotation by filename stem.
# ══════════════════════════════════════════════════════════════════════════════════════

_HEADER_RE = re.compile(r"^### (\d+)\s+(\S+)")


def _parse_annotations(md_text: str) -> dict[str, str]:
    """{'NN_TICKER' -> the section's verbatim body} for every '### NN TICKER (...)' header
    through the next '### ' header (or end of file)."""
    lines = md_text.splitlines()
    headers: list[tuple[int, str, str]] = []
    for i, ln in enumerate(lines):
        m = _HEADER_RE.match(ln)
        if m:
            ticker = m.group(2).strip("()").upper()
            headers.append((i, m.group(1), ticker))
    out: dict[str, str] = {}
    for idx, (i, num, ticker) in enumerate(headers):
        end = headers[idx + 1][0] if idx + 1 < len(headers) else len(lines)
        body = "\n".join(l for l in lines[i + 1:end] if l.strip() and l.strip() != "---")
        out[f"{num}_{ticker}"] = body.strip()
    return out


def load_book_content(repo: Path = REPO) -> tuple[list[dict], int]:
    """(content_blocks, n_images) — arm 2's prefix: the intro text, then image+annotation pairs
    for all 24 book charts, cache_control on the LAST block (so system+this prefix is cached
    across every arm-2 call). FAILS LOUDLY if any image has no annotation or vice versa — a
    silent drop would show the model an unexplained picture or a caption with no chart, neither
    of which is the worked-example arm the pre-registration describes."""
    blocks: list[dict] = [{"type": "text", "text": BOOK_INTRO_TEXT}]
    n_images = 0
    for md_rel, img_rel in BOOK_SETS:
        md_text = (repo / md_rel).read_text()
        annotations = _parse_annotations(md_text)
        img_files = sorted((repo / img_rel).glob("*.jpg"))
        img_stems = {p.stem for p in img_files}
        ann_stems = set(annotations)
        missing_ann = sorted(img_stems - ann_stems)
        missing_img = sorted(ann_stems - img_stems)
        if missing_ann or missing_img:
            raise RuntimeError(
                f"{img_rel}: image(s) with no annotation {missing_ann}; "
                f"annotation(s) with no image {missing_img}")
        for p in img_files:
            b64 = base64.standard_b64encode(p.read_bytes()).decode("ascii")
            blocks.append({"type": "image",
                           "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}})
            blocks.append({"type": "text", "text": annotations[p.stem]})
            n_images += 1
    blocks[-1] = dict(blocks[-1])
    blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks, n_images


# ══════════════════════════════════════════════════════════════════════════════════════
# REQUEST BUILDING — identical stock-chart content in both arms; arm 2 prepends the (cached)
# book block. `system` carries ONLY the plain reviewer text, in BOTH arms.
# ══════════════════════════════════════════════════════════════════════════════════════

def _image_block(png: bytes) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                        "data": base64.standard_b64encode(png).decode("ascii")}}


def build_user_content(arm: str, daily_png: bytes, weekly_png: Optional[bytes],
                       book_blocks: Optional[list[dict]]) -> list[dict]:
    content: list[dict] = []
    if arm == "books":
        if book_blocks is None:
            raise ValueError("arm='books' requires book_blocks")
        content.extend(book_blocks)
    content.append(_image_block(daily_png))
    if weekly_png is not None:
        content.append(_image_block(weekly_png))
    else:
        content.append({"type": "text", "text": WEEKLY_UNAVAILABLE_TEXT})
    content.append({"type": "text", "text": RATE_THIS_CHART_TEXT})
    return content


def build_request_kwargs(model: str, arm: str, daily_png: bytes, weekly_png: Optional[bytes],
                         book_blocks: Optional[list[dict]], *,
                         max_tokens: Optional[int] = None) -> dict:
    """The exact kwargs sent to `messages.create` (or `messages.count_tokens`, minus
    `max_tokens`, which that endpoint does not accept)."""
    kw: dict = {
        "model": model,
        "system": SYSTEM_TEXT,
        "messages": [{"role": "user", "content": build_user_content(
            arm, daily_png, weekly_png, book_blocks)}],
        "output_config": OUTPUT_CONFIG,
    }
    if max_tokens is not None:
        kw["max_tokens"] = max_tokens
    return kw


def redact_for_json(obj: Any) -> Any:
    """Deep-copy `obj`, replacing every image block's base64 `data` with a byte-count
    placeholder — for writing request payloads to disk without embedding megabytes of image
    bytes (or the book images' identity) in a readable file."""
    if isinstance(obj, dict):
        if obj.get("type") == "image" and isinstance(obj.get("source"), dict) \
                and "data" in obj["source"]:
            out = {k: (redact_for_json(v) if k != "source" else {
                **{kk: vv for kk, vv in v.items() if kk != "data"},
                "data": f"<omitted: {len(v['data'])} b64 chars>",
            }) for k, v in obj.items()}
            return out
        return {k: redact_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_for_json(v) for v in obj]
    return obj


# ══════════════════════════════════════════════════════════════════════════════════════
# PRICING — pure, testable without a client or DB.
# ══════════════════════════════════════════════════════════════════════════════════════

def price_whole_run(*, n_dates: int, replicates: int, arm1_input_tokens: int,
                    arm2_input_tokens_total: int, out_mean_tokens: float, model: str) -> dict:
    """Whole-run $ estimate BEFORE any paid call.

    `arm1_input_tokens` = count_tokens() on arm 1's full request (one representative row).
    `arm2_input_tokens_total` = count_tokens() on arm 2's full request (book prefix + the SAME
    stock charts) for the SAME row. The book prefix's own size is the difference between the
    two — the only thing that differs between the requests, since both carry an identical
    stock-chart suffix — so it needs no separate call.

    Arm 2 prices as ONE cache WRITE (the book prefix, first call) + cache READS (every later
    call) + the per-call marginal (fresh stock charts) at the regular rate on EVERY call — the
    stock charts differ per (ticker, date, replicate) and are never cached. Rates: cache write
    1.25x base input, cache read 0.10x base input — the same multipliers
    `spend_tracker._cost_for_call` uses in production, kept in sync by inspection rather than
    import (that function needs a live response object, not a token count)."""
    prices = pricing_for(model)
    price_in, price_out = prices["input"], prices["output"]
    n_calls_per_arm = max(n_dates, 0) * max(replicates, 0)

    arm1_cost = n_calls_per_arm * (arm1_input_tokens * price_in / 1e6
                                   + out_mean_tokens * price_out / 1e6)

    book_tokens = max(arm2_input_tokens_total - arm1_input_tokens, 0)
    marginal_tokens = max(arm2_input_tokens_total - book_tokens, 0)
    if n_calls_per_arm <= 0:
        arm2_input_cost = 0.0
    else:
        write_cost = book_tokens * 1.25 * price_in / 1e6
        read_cost = book_tokens * 0.10 * price_in / 1e6 * max(n_calls_per_arm - 1, 0)
        marginal_cost = marginal_tokens * price_in / 1e6 * n_calls_per_arm
        arm2_input_cost = write_cost + read_cost + marginal_cost
    arm2_output_cost = n_calls_per_arm * out_mean_tokens * price_out / 1e6
    arm2_cost = arm2_input_cost + arm2_output_cost

    total = arm1_cost + arm2_cost
    return {
        "model": model, "price_in_per_m": price_in, "price_out_per_m": price_out,
        "n_dates": n_dates, "replicates": replicates, "n_calls_per_arm": n_calls_per_arm,
        "n_calls_total": n_calls_per_arm * 2,
        "arm1_input_tokens": arm1_input_tokens, "arm2_input_tokens_total": arm2_input_tokens_total,
        "arm2_book_tokens": book_tokens, "arm2_marginal_tokens": marginal_tokens,
        "out_mean_tokens": out_mean_tokens,
        "arm1_cost_usd": round(arm1_cost, 4), "arm2_cost_usd": round(arm2_cost, 4),
        "total_usd": round(arm1_cost + arm2_cost, 4),
    }


def _resp_value(resp: Any, name: str):
    return resp.get(name) if isinstance(resp, dict) else getattr(resp, name, None)


async def count_tokens_for_arm(client, model: str, arm: str, daily_png: bytes,
                               weekly_png: Optional[bytes],
                               book_blocks: Optional[list[dict]]) -> int:
    """ONE free `messages.count_tokens` call for `arm`'s full request shape on a representative
    row."""
    kw = build_request_kwargs(model, arm, daily_png, weekly_png, book_blocks)
    resp = await client.messages.count_tokens(**kw)
    return int(_resp_value(resp, "input_tokens") or 0)


async def mean_output_tokens(model: str, *, min_n: int = 10) -> tuple[float, int]:
    """(mean, n) of REAL measured output tokens from recent opus-tier judge calls in
    `api_usage`, non-truncated, last 14 days. This exact model id first; widens to any
    `claude-opus%` id when there are too few rows for the exact id (a brand-new model has no
    history of its own yet). Never raises the count of a query that finds nothing — returns
    (0.0, 0)."""
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT avg(output_tokens) AS mean, count(*) AS n FROM api_usage
               WHERE model = $1 AND stop_reason IS DISTINCT FROM 'max_tokens'
                 AND created_at > NOW() - INTERVAL '14 days'""", model)
        n = int(row["n"] or 0) if row else 0
        mean = float(row["mean"] or 0.0) if row and row["mean"] is not None else 0.0
        if n < min_n:
            row2 = await conn.fetchrow(
                """SELECT avg(output_tokens) AS mean, count(*) AS n FROM api_usage
                   WHERE model LIKE 'claude-opus%' AND stop_reason IS DISTINCT FROM 'max_tokens'
                     AND created_at > NOW() - INTERVAL '14 days'""")
            n2 = int(row2["n"] or 0) if row2 else 0
            if n2 > n:
                logger.info("mean_output_tokens: widened %s (n=%d) -> claude-opus%% (n=%d)",
                           model, n, n2)
                return float(row2["mean"] or 0.0) if row2["mean"] is not None else 0.0, n2
    return mean, n


# ══════════════════════════════════════════════════════════════════════════════════════
# SCORING — lines 1-8 of the pre-registration, decision rules fixed there. Pure over `calls`.
# ══════════════════════════════════════════════════════════════════════════════════════

def modal_rating(ratings: list[Optional[str]]) -> Optional[str]:
    """The date's read: a rating reaching a MAJORITY (>=2) of the valid (non-error) replicates.
    A split with no majority (e.g. one of each of 3 different ratings) 'reads nothing' — None,
    per the pre-registration's own framing of a chart read as a lean, never a single-vote
    verdict."""
    valid = [r for r in ratings if r]
    if not valid:
        return None
    top, n = Counter(valid).most_common(1)[0]
    return top if n >= 2 else None


def all_three_agree(ratings: list[Optional[str]]) -> bool:
    """Line 6's per-date 'stable' — ALL 3 replicates identical (stricter than the majority
    `modal_rating` uses for lines 1/2/5/8's counting)."""
    valid = [r for r in ratings if r]
    return len(valid) == 3 and len(set(valid)) == 1


def garbage_all_three(ratings: list[Optional[str]]) -> bool:
    """Line 8's bar: 'garbage' in ALL 3 reads, not a majority."""
    valid = [r for r in ratings if r]
    return len(valid) == 3 and all(r == "garbage" for r in valid)


def _lean_ratio(bad_rate: Optional[float], good_pop_rate: Optional[float]) -> Optional[float]:
    """line1_rate / line2_rate (or the equivalent pair) — None when the good-population rate is
    undefined; +inf when the good population never reads bad but the target population does
    (a genuine, unbounded lean, per the pre-registration's own '∞' framing); None (undefined)
    when BOTH rates are exactly zero."""
    if bad_rate is None or good_pop_rate is None:
        return None
    if good_pop_rate == 0:
        return None if bad_rate == 0 else math.inf
    return bad_rate / good_pop_rate


def stable_bar(n: int) -> int:
    """The 'n or more' bar for a '2 of 3 (or more)' proportion — ceil(2n/3)."""
    return math.ceil(2 * n / 3)


@dataclass
class RowRead:
    pop: str
    ticker: str
    date: str
    verdict: str
    ratings: list[Optional[str]] = field(default_factory=lambda: [None, None, None])
    reasons: list[Optional[str]] = field(default_factory=lambda: [None, None, None])
    na: bool = False

    @property
    def modal(self) -> Optional[str]:
        return modal_rating(self.ratings)

    @property
    def stable(self) -> bool:
        return all_three_agree(self.ratings)

    @property
    def garbage3(self) -> bool:
        return garbage_all_three(self.ratings)


def build_rows(calls: list[dict], population: list[tuple[str, str, str, str]],
              na_keys: frozenset = frozenset()) -> dict[str, dict[tuple[str, str], RowRead]]:
    """{arm -> {(ticker, date) -> RowRead}} — every population row, both arms, ratings/reasons
    filled from `calls` (a list of {"arm","ticker","date","replicate","rating","reason"} dicts;
    a missing or errored replicate leaves that slot None)."""
    out: dict[str, dict[tuple[str, str], RowRead]] = {arm: {} for arm in ARMS}
    for pop, tk, d, verdict in population:
        for arm in ARMS:
            out[arm][(tk, d)] = RowRead(pop=pop, ticker=tk, date=d, verdict=verdict,
                                        na=(tk, d) in na_keys)
    for c in calls:
        arm, tk, d = c.get("arm"), c.get("ticker"), c.get("date")
        idx = c.get("replicate")
        if arm not in out or (tk, d) not in out[arm] or not isinstance(idx, int) or not (0 <= idx < REPLICATES):
            continue
        row = out[arm][(tk, d)]
        row.ratings[idx] = c.get("rating")
        row.reasons[idx] = c.get("reason")
    return out


def score_arm(rows: dict[tuple[str, str], RowRead],
             not_extended_keys: frozenset[tuple[str, str]]) -> dict:
    """Lines 1-8 + the decision, for ONE arm's rows dict (see `build_rows`)."""
    def group(pop: str) -> list[RowRead]:
        return [r for r in rows.values() if r.pop == pop and not r.na]

    condemned = group("BAD_CHART")
    worked = group("REAL_EP") + group("APPROVED")
    twelve = [r for r in condemned if (r.ticker, r.date) in not_extended_keys]
    all64 = [r for r in rows.values() if not r.na]  # line 6/7 denominator includes OTHER_REJECTED

    def bad_rate(rs: list[RowRead]) -> tuple[int, int, Optional[float]]:
        n = sum(1 for r in rs if r.modal in BAD_SIDE)
        return n, len(rs), (n / len(rs) if rs else None)

    def good_rate(rs: list[RowRead]) -> tuple[int, int, Optional[float]]:
        n = sum(1 for r in rs if r.modal == "good")
        return n, len(rs), (n / len(rs) if rs else None)

    l1_n, l1_d, l1_rate = bad_rate(condemned)
    l2_n, l2_d, l2_rate = bad_rate(worked)
    l3 = _lean_ratio(l1_rate, l2_rate)

    l4num_n, l4num_d, l4num_rate = bad_rate(twelve)
    l4 = _lean_ratio(l4num_rate, l2_rate)

    l5worked_n, l5worked_d, l5worked_rate = good_rate(worked)
    l5cond_n, l5cond_d, l5cond_rate = good_rate(condemned)

    stable_n = sum(1 for r in all64 if r.stable)
    l6_bar = stable_bar(len(all64))
    stable_fraction = (stable_n / len(all64)) if all64 else None

    l8cond_rows = [r for r in twelve if r.garbage3]
    l8worked_rows = [r for r in worked if r.garbage3]
    l8_met = len(l8cond_rows) >= 3 and len(l8worked_rows) <= 1

    if l3 is None or l3 < 1.5 or (stable_fraction is not None and stable_fraction < 0.5):
        decision = "NO_LEAN"
    elif l3 >= 3.0 and l4 is not None and l4 >= 2.0 and stable_n >= l6_bar:
        decision = "USEFUL_SUPPORT"
    else:
        decision = "WEAK"

    return {
        "line1_bad_condemned": {"n": l1_n, "of": l1_d, "rate": l1_rate},
        "line2_bad_worked": {"n": l2_n, "of": l2_d, "rate": l2_rate},
        "line3_lean": l3,
        "line4_lean_on_the_12": {"n": l4num_n, "of": l4num_d, "rate": l4num_rate, "ratio": l4},
        "line5_good": {"worked": {"n": l5worked_n, "of": l5worked_d, "rate": l5worked_rate},
                       "condemned": {"n": l5cond_n, "of": l5cond_d, "rate": l5cond_rate}},
        "line6_stable": {"n": stable_n, "of": len(all64), "bar": l6_bar,
                         "met": stable_n >= l6_bar},
        "line8_garbage_filter": {
            "of_12": len(l8cond_rows), "of_12_names": [(r.ticker, r.date) for r in l8cond_rows],
            "of_39": len(l8worked_rows), "of_39_names": [(r.ticker, r.date) for r in l8worked_rows],
            "met": l8_met,
        },
        "decision": decision,
        "n_condemned": len(condemned), "n_worked": len(worked), "n_twelve": len(twelve),
        "n_all64": len(all64),
    }


def score_run(calls: list[dict], population: list[tuple[str, str, str, str]],
             not_extended_keys: frozenset[tuple[str, str]],
             na_keys: frozenset[tuple[str, str]] = frozenset()) -> dict[str, dict]:
    rows_by_arm = build_rows(calls, population, na_keys)
    return {arm: score_arm(rows_by_arm[arm], not_extended_keys) for arm in ARMS}


# ══════════════════════════════════════════════════════════════════════════════════════
# I/O — calls.jsonl (append-only, crash-safe), reads.psv, scorecard.md
# ══════════════════════════════════════════════════════════════════════════════════════

def load_calls_jsonl(path: Path) -> list[dict]:
    out = []
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _resumed_terminal(rec: dict) -> bool:
    """A record `--resume` should treat as already bought: a rating, OR a truncation (retrying
    would just truncate again at the same max_tokens — buying the same failure twice)."""
    return rec.get("rating") is not None or rec.get("truncated") is True


def completed_keys(path: Path) -> set[tuple]:
    return {(r["arm"], r["ticker"], r["date"], r["replicate"])
            for r in load_calls_jsonl(path) if _resumed_terminal(r)}


def write_reads_psv(path: Path, population: list[tuple[str, str, str, str]],
                    rows_by_arm: dict[str, dict[tuple[str, str], RowRead]]) -> None:
    cols = ["pop", "ticker", "date", "verdict", "operator_words", "arm", "na",
            "rating_1", "rating_2", "rating_3", "modal", "stable", "garbage3",
            "reason_1", "reason_2", "reason_3"]
    lines = ["|".join(cols)]
    for pop, tk, d, verdict in population:
        words = operator_words_for(tk, d)
        for arm in ARMS:
            r = rows_by_arm[arm][(tk, d)]
            vals = [pop, tk, d, verdict, words.replace("|", "/"), arm, "T" if r.na else "F",
                    r.ratings[0] or "", r.ratings[1] or "", r.ratings[2] or "",
                    r.modal or "", "T" if r.stable else "F", "T" if r.garbage3 else "F",
                    (r.reasons[0] or "").replace("|", "/"),
                    (r.reasons[1] or "").replace("|", "/"),
                    (r.reasons[2] or "").replace("|", "/")]
            lines.append("|".join(vals))
    path.write_text("\n".join(lines) + "\n")


def write_scorecard_md(path: Path, scores: dict[str, dict], meta: dict) -> None:
    lines = ["# #519 option A — scorecard", ""]
    lines.append(f"Model: `{meta.get('model')}`  ·  n dates: {meta.get('n_dates')}  ·  "
                f"replicates: {REPLICATES}  ·  calls: {meta.get('n_calls_total')}")
    if "price" in meta:
        lines.append(f"Priced whole-run estimate: ${meta['price']['total_usd']:.2f}")
    lines.append("")
    for arm in ARMS:
        s = scores[arm]
        lines.append(f"## Arm: {arm}")
        lines.append("")
        lines.append(f"- Line 1 — bad on condemned: {s['line1_bad_condemned']['n']} of "
                    f"{s['line1_bad_condemned']['of']}")
        lines.append(f"- Line 2 — bad on worked (real EPs + approved): "
                    f"{s['line2_bad_worked']['n']} of {s['line2_bad_worked']['of']}")
        l3 = s["line3_lean"]
        lines.append(f"- Line 3 — the lean: {'undefined' if l3 is None else ('inf' if math.isinf(l3) else f'{l3:.2f}x')} "
                    f"(bar: 3x or more)")
        l4 = s["line4_lean_on_the_12"]["ratio"]
        lines.append(f"- Line 4 — lean on the 12 the run-up rule misses: "
                    f"{'undefined' if l4 is None else ('inf' if math.isinf(l4) else f'{l4:.2f}x')} "
                    f"(bar: 2x or more)")
        l5 = s["line5_good"]
        lines.append(f"- Line 5 — good rate: worked {l5['worked']['n']} of {l5['worked']['of']}, "
                    f"condemned {l5['condemned']['n']} of {l5['condemned']['of']}")
        l6 = s["line6_stable"]
        lines.append(f"- Line 6 — stable (all 3 agree): {l6['n']} of {l6['of']} "
                    f"(bar: {l6['bar']} or more) — {'MET' if l6['met'] else 'NOT MET'}")
        l8 = s["line8_garbage_filter"]
        lines.append(f"- Line 8 — garbage filter: {l8['of_12']} of 12 named "
                    f"({', '.join(f'{t}/{d}' for t, d in l8['of_12_names']) or 'none'}); "
                    f"{l8['of_39']} of 39 named "
                    f"({', '.join(f'{t}/{d}' for t, d in l8['of_39_names']) or 'none'}) — "
                    f"{'MET' if l8['met'] else 'NOT MET'}")
        lines.append(f"- **Decision: {s['decision']}**")
        lines.append("")
    path.write_text("\n".join(lines) + "\n")


# ══════════════════════════════════════════════════════════════════════════════════════
# ORCHESTRATION — DB + API touching. Runs only inside the container (or against a real client).
# ══════════════════════════════════════════════════════════════════════════════════════

async def fetch_row_bars(ticker: str, alert_date: date) -> tuple[list[dict], Optional[float]]:
    """(prior_bars canonical-shape ascending strictly-before alert_date, alert-day OPEN or None).
    The open query selects ONLY open_price — never high/low/close — so the alert-day contract
    (no lookahead beyond the open) is enforced at the SQL level, not just by convention."""
    from agents.market_intelligence.db import get_pool, get_prior_daily_ohlcv
    prior_rows = await get_prior_daily_ohlcv(ticker, alert_date, lookback=RENDER_LOOKBACK_SESSIONS)
    prior = [_canonical_bar(r) for r in prior_rows]
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT open_price FROM mi_daily_closes WHERE ticker = $1 AND trade_date = $2",
            ticker, alert_date)
    open_px = float(row["open_price"]) if row and row["open_price"] is not None else None
    return prior, open_px


def _iso_to_date(iso: str) -> date:
    y, m, d = iso.split("-")
    return date(int(y), int(m), int(d))


async def prepare_row(ticker: str, iso_date: str) -> dict:
    """Fetch, trim, derive ANCHOR-75, render — everything DB/render-side for one (ticker, date).
    Returns a dict the caller threads through to request-building + scoring."""
    ad = _iso_to_date(iso_date)
    prior, open_px = await fetch_row_bars(ticker, ad)
    # NO LOOKAHEAD, asserted rather than trusted (mirrors `structure_read_v2`'s own assertion on
    # the same contract): every bar this row ever touches — clean-trim, ANCHOR-75, the render —
    # must be strictly before the alert date. `get_prior_daily_ohlcv`'s SQL already guarantees
    # this; this line catches a future change to that contract before a leaked bar could reach
    # the chart the model sees.
    assert all(b["date"] < ad for b in prior), (
        f"lookahead: a bar dated >= {ad} reached prepare_row for {ticker}")
    out: dict = {"ticker": ticker, "date": iso_date, "n_prior_sessions": len(prior)}
    if not prior or open_px is None:
        out.update(render_failed=True, daily_png=None, weekly_png=None, anchor75=None)
        return out
    clean_bars, clean_n, artifact_days = clean_trim(prior)
    out["clean_n"] = clean_n
    out["na_scoring"] = clean_n < NA_SCORING_MIN_CLEAN
    out["anchor75"] = anchor75_rejects_for(prior, ad, open_px, clean_n)
    daily_png, weekly_png, render_meta = render_point_in_time_charts(clean_bars, open_px)
    out["daily_png"] = daily_png
    out["weekly_png"] = weekly_png
    out["render_failed"] = daily_png is None
    out["render_meta"] = render_meta
    return out


async def prepare_all_rows(population: list[tuple[str, str, str, str]]) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for pop, tk, d, verdict in population:
        out[(tk, d)] = await prepare_row(tk, d)
    return out


def not_extended_keys_from(population: list[tuple[str, str, str, str]],
                          rendered: dict[tuple[str, str], dict]) -> frozenset[tuple[str, str]]:
    """The '12' — condemned dates ANCHOR-75 does NOT reject (R7_anchor75 is False, not None)."""
    out = set()
    for pop, tk, d, verdict in population:
        if pop != "BAD_CHART":
            continue
        r = rendered.get((tk, d), {})
        if r.get("anchor75") is False:
            out.add((tk, d))
    return frozenset(out)


def na_keys_from(rendered: dict[tuple[str, str], dict]) -> frozenset[tuple[str, str]]:
    return frozenset(k for k, r in rendered.items() if r.get("na_scoring") or r.get("render_failed"))


async def _write_line(f, lock: asyncio.Lock, rec: dict) -> None:
    async with lock:
        f.write(json.dumps(rec) + "\n")
        f.flush()


async def one_call(client, sem: asyncio.Semaphore, model: str, arm: str, tk: str, d: str,
                   replicate: int, daily_png: bytes, weekly_png: Optional[bytes],
                   book_blocks: Optional[list[dict]], max_tokens: int,
                   f, lock: asyncio.Lock) -> dict:
    rec: dict = {"arm": arm, "ticker": tk, "date": d, "replicate": replicate, "model": model}
    kw = build_request_kwargs(model, arm, daily_png, weekly_png, book_blocks, max_tokens=max_tokens)
    async with sem:
        try:
            resp = await asyncio.wait_for(client.messages.create(**kw), timeout=CALL_TIMEOUT_S)
        except Exception as e:  # noqa: BLE001 — record and move on, never crash the batch
            rec["error"] = f"{type(e).__name__}: {e}"
            await _write_line(f, lock, rec)
            return rec
    try:
        from agents.market_intelligence.spend_tracker import log_anthropic_call_safe
        await log_anthropic_call_safe(model=model, caller="eval_519_option_a", response=resp)
    except Exception as e:  # noqa: BLE001 — cost logging must never break the run
        logger.warning("eval_519_option_a: spend log failed: %s", e)
    rec["usage"] = usage_tokens(resp)
    rec["stop_reason"] = stop_reason(resp)
    if is_truncated(resp):
        rec["truncated"] = True
        await _write_line(f, lock, rec)
        return rec
    text = first_text(resp)
    try:
        parsed = json.loads(text)
        rating = parsed.get("rating")
        if rating not in RATINGS:
            raise ValueError(f"rating {rating!r} not in {RATINGS}")
        rec["rating"] = rating
        rec["reason"] = parsed.get("reason")
    except Exception as e:  # noqa: BLE001
        rec["error"] = f"unparseable structured output: {e}: {text[:200]!r}"
    await _write_line(f, lock, rec)
    return rec


async def run_dry(out_dir: Path, client=None) -> dict:
    """Default mode. $0 except (when a client is supplied) two free `count_tokens` calls."""
    population = load_population()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "charts").mkdir(exist_ok=True)

    rendered = await prepare_all_rows(population)
    for (tk, d), r in rendered.items():
        if r.get("daily_png"):
            (out_dir / "charts" / f"{tk}_{d}_daily.png").write_bytes(r["daily_png"])
        if r.get("weekly_png"):
            (out_dir / "charts" / f"{tk}_{d}_weekly.png").write_bytes(r["weekly_png"])

    not_extended = not_extended_keys_from(population, rendered)
    na_keys = na_keys_from(rendered)
    print(f"population: {len(population)} rows; render_failed: "
         f"{sum(1 for r in rendered.values() if r.get('render_failed'))}; "
         f"na (clean<{NA_SCORING_MIN_CLEAN}): {len(na_keys)}; "
         f"derived '12 the run-up rule misses': {sorted(not_extended)}")

    book_blocks, n_images = load_book_content()
    if n_images != EXPECTED_BOOK_IMAGES:
        print(f"WARNING: loaded {n_images} book images, expected {EXPECTED_BOOK_IMAGES}")

    callable_rows = [(tk, d) for (tk, d), r in rendered.items() if not r.get("render_failed")]
    payloads = []
    rep = None
    for tk, d in callable_rows:
        r = rendered[(tk, d)]
        for arm in ARMS:
            kw = build_request_kwargs(MODEL, arm, r["daily_png"], r.get("weekly_png"),
                                      book_blocks if arm == "books" else None,
                                      max_tokens=2048)
            payloads.append({"arm": arm, "ticker": tk, "date": d, "request": redact_for_json(kw)})
        if rep is None and r.get("weekly_png") is not None:
            rep = r
    if rep is None and callable_rows:
        rep = rendered[callable_rows[0]]
    (out_dir / "request_payloads.json").write_text(json.dumps(payloads, indent=2))

    result: dict = {"population": population, "rendered": rendered, "not_extended": not_extended,
                    "na_keys": na_keys, "book_blocks": book_blocks, "n_book_images": n_images,
                    "callable_rows": callable_rows}
    if client is None or rep is None:
        print("no client / no renderable row — skipping count_tokens + price estimate "
             "(this is expected off-server; run inside the container for a live price).")
        return result

    t1 = await count_tokens_for_arm(client, MODEL, "plain", rep["daily_png"], rep.get("weekly_png"), None)
    t2 = await count_tokens_for_arm(client, MODEL, "books", rep["daily_png"], rep.get("weekly_png"), book_blocks)
    out_mean, out_n = await mean_output_tokens(MODEL)
    price = price_whole_run(n_dates=len(callable_rows), replicates=REPLICATES,
                            arm1_input_tokens=t1, arm2_input_tokens_total=t2,
                            out_mean_tokens=out_mean, model=MODEL)
    print(f"count_tokens: arm1={t1} arm2={t2} (book prefix ~{price['arm2_book_tokens']} tok)")
    print(f"output tokens: mean={out_mean:.0f} over n={out_n} recent {MODEL} judge calls")
    print(f"PRICED WHOLE RUN: ${price['total_usd']:.2f}  "
         f"(arm1 ${price['arm1_cost_usd']:.2f} + arm2 ${price['arm2_cost_usd']:.2f}, "
         f"{price['n_calls_total']} calls)")
    (out_dir / "price_estimate.json").write_text(json.dumps(price, indent=2))
    result["price"] = price
    return result


async def run_paid(client, out_dir: Path, *, max_usd: float, resume: bool,
                   mean_output_tokens_fn=mean_output_tokens) -> Optional[dict]:
    """`--paid --max-usd N`. Recomputes the price FIRST; if it exceeds `max_usd`, aborts before
    a single `messages.create` call. `mean_output_tokens_fn` is injectable (tests supply a stub
    with no DB)."""
    dry = await run_dry(out_dir, client=None)  # renders + derives population, $0
    population, rendered = dry["population"], dry["rendered"]
    not_extended, na_keys = dry["not_extended"], dry["na_keys"]
    book_blocks = dry["book_blocks"]
    callable_rows = dry["callable_rows"]
    if not callable_rows:
        print("ABORT: no renderable row at all — nothing to price or call.")
        return None
    rep = rendered[callable_rows[0]]
    for tk, d in callable_rows:
        if rendered[(tk, d)].get("weekly_png") is not None:
            rep = rendered[(tk, d)]
            break

    t1 = await count_tokens_for_arm(client, MODEL, "plain", rep["daily_png"], rep.get("weekly_png"), None)
    t2 = await count_tokens_for_arm(client, MODEL, "books", rep["daily_png"], rep.get("weekly_png"), book_blocks)
    out_mean, out_n = await mean_output_tokens_fn(MODEL)
    price = price_whole_run(n_dates=len(callable_rows), replicates=REPLICATES,
                            arm1_input_tokens=t1, arm2_input_tokens_total=t2,
                            out_mean_tokens=out_mean, model=MODEL)
    print(f"PRICED WHOLE RUN: ${price['total_usd']:.2f} vs --max-usd {max_usd:.2f}")
    if price["total_usd"] > max_usd:
        print(f"ABORT: ${price['total_usd']:.2f} exceeds --max-usd {max_usd:.2f} — "
             "NO calls made.")
        return None

    jsonl_path = out_dir / "calls.jsonl"
    done = completed_keys(jsonl_path) if resume else set()
    max_tokens = max(2 * int(math.ceil(out_mean)) if out_mean else 0, 2048)
    sem = asyncio.Semaphore(CONCURRENCY)
    lock = asyncio.Lock()
    with jsonl_path.open("a" if resume else "w") as f:
        tasks = []
        for tk, d in callable_rows:
            r = rendered[(tk, d)]
            for arm in ARMS:
                bb = book_blocks if arm == "books" else None
                for rep_i in range(REPLICATES):
                    if (arm, tk, d, rep_i) in done:
                        continue
                    tasks.append(one_call(client, sem, MODEL, arm, tk, d, rep_i,
                                          r["daily_png"], r.get("weekly_png"), bb,
                                          max_tokens, f, lock))
        results = await asyncio.gather(*tasks) if tasks else []
    print(f"{len(results)} calls made ({len(done)} already resumed)")

    calls = load_calls_jsonl(jsonl_path)
    scores = score_run(calls, population, not_extended, na_keys)
    rows_by_arm = build_rows(calls, population, na_keys)
    write_reads_psv(out_dir / "reads.psv", population, rows_by_arm)
    write_scorecard_md(out_dir / "scorecard.md", scores,
                       {"model": MODEL, "n_dates": len(callable_rows),
                        "n_calls_total": price["n_calls_total"], "price": price})
    print(f"scored -> {out_dir / 'scorecard.md'}")
    return {"scores": scores, "price": price}


def score_only(jsonl_path: Path, out_dir: Path) -> dict:
    population = load_population()
    calls = load_calls_jsonl(jsonl_path)
    # re-derive '12' + na without touching the network — needs the SAME bars the run used,
    # which aren't in calls.jsonl by design (labels never sent). If a prior dry-run's rendered
    # meta was captured alongside, use it; otherwise score with an empty not-extended/na set and
    # say so loudly rather than guess.
    not_extended: frozenset = frozenset()
    na_keys: frozenset = frozenset()
    meta_path = jsonl_path.parent / "run_meta.json"
    if meta_path.exists():
        m = json.loads(meta_path.read_text())
        not_extended = frozenset(tuple(x) for x in m.get("not_extended", []))
        na_keys = frozenset(tuple(x) for x in m.get("na_keys", []))
    else:
        print("WARNING: no run_meta.json beside the jsonl — line 4 ('the 12') and any n/a "
             "exclusions cannot be re-derived offline; scoring with an EMPTY set for both.")
    scores = score_run(calls, population, not_extended, na_keys)
    rows_by_arm = build_rows(calls, population, na_keys)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_reads_psv(out_dir / "reads.psv", population, rows_by_arm)
    write_scorecard_md(out_dir / "scorecard.md", scores,
                       {"model": MODEL, "n_dates": len({(c['ticker'], c['date']) for c in calls}),
                        "n_calls_total": len(calls)})
    return scores


# ══════════════════════════════════════════════════════════════════════════════════════
# DEV-ONLY local preview — offline, no DB/API. Renders 3 representative charts from the free
# read's captured bars.psv so the operator can eyeball what the model will see.
# ══════════════════════════════════════════════════════════════════════════════════════

def _load_bars_psv(path: Path) -> dict[str, list[dict]]:
    bars: dict[str, list[dict]] = defaultdict(list)
    for ln in path.read_text().splitlines():
        if not ln.strip():
            continue
        tk, d, o, h, l, c, v = ln.split("|")
        bars[tk].append({"date": _iso_to_date(d), "open": float(o), "high": float(h),
                         "low": float(l), "close": float(c), "volume": float(v) if v else 0.0})
    for t in bars:
        bars[t].sort(key=lambda b: b["date"])
    return bars


def preview_from_bars_psv(psv_path: Path, out_dir: Path) -> list[Path]:
    all_bars = _load_bars_psv(psv_path)
    population = load_population()
    written: list[Path] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    wanted = [("REAL_EP", None), ("APPROVED", None), ("BAD_CHART", None)]
    for pop, tk, d, verdict in population:
        for i, (want_pop, chosen) in enumerate(wanted):
            if chosen is not None or pop != want_pop:
                continue
            bars = all_bars.get(tk)
            if not bars:
                continue
            ad = _iso_to_date(d)
            prior = [b for b in bars if b["date"] < ad]
            on = [b for b in bars if b["date"] == ad]
            if not prior or not on:
                continue
            open_px = on[0]["open"]
            clean_bars, clean_n, _ = clean_trim(prior)
            if clean_n < MIN_RENDER_BARS:
                continue
            daily_png, weekly_png, meta = render_point_in_time_charts(clean_bars, open_px)
            if daily_png is None:
                continue
            wanted[i] = (want_pop, (tk, d))
            (out_dir / f"{tk}_{d}_daily.png").write_bytes(daily_png)
            written.append(out_dir / f"{tk}_{d}_daily.png")
            if weekly_png is not None:
                (out_dir / f"{tk}_{d}_weekly.png").write_bytes(weekly_png)
                written.append(out_dir / f"{tk}_{d}_weekly.png")
            print(f"{want_pop}: {tk} {d} -> {out_dir / f'{tk}_{d}_daily.png'}  ({meta})")
    return written


# ══════════════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════════════

def _build_client():
    from shared.llm_client import make_async_anthropic
    return make_async_anthropic()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=str, default=str(DEFAULT_SCRATCH))
    ap.add_argument("--paid", action="store_true")
    ap.add_argument("--max-usd", type=float, default=None)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--score-only", type=str, default=None)
    ap.add_argument("--bars-psv", type=str, default=None, help="dev-only: local render preview")
    args = ap.parse_args()

    out_dir = Path(args.out)

    if args.bars_psv:
        preview_from_bars_psv(Path(args.bars_psv), out_dir)
        return

    if args.score_only:
        score_only(Path(args.score_only), out_dir)
        return

    if args.paid:
        if args.max_usd is None:
            ap.error("--paid requires --max-usd")
        client = _build_client()
        asyncio.run(run_paid(client, out_dir, max_usd=args.max_usd, resume=args.resume))
        return

    client = None
    try:
        client = _build_client()
    except Exception as e:  # noqa: BLE001 — dry run still renders + derives population w/o a key
        logger.warning("no Anthropic client available (%s) — dry run continues without pricing", e)
    asyncio.run(run_dry(out_dir, client=client))


if __name__ == "__main__":
    main()
