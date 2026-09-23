"""EP Selectivity Phase 1 — Class A/B/C/Chop/Dead classifier (Block 3).

For every HIGH alert in `ep_cohort_alerts_60d.csv`, fetches 1-min bars
9:30-11:00 ET from Polygon via `collector.get_minute_bars()` and
classifies the intraday post-EP shape:

  CLASS_A      ORB-high broken within 14 min of open AND last-price holds
               above ORB-high for ≥5 min
  CLASS_B      ORB-high not broken in 9:30-9:45 window, THEN a later
               5-min high after 10:00 ET exceeds all preceding session
               highs (and ORB-low never breaks)
  CLASS_C      ORB-low broken, no recovery above ORB-high before 11:00
  AMBIGUOUS_CHOP   ORB-high broken, fails to hold ≥5 min, THEN ORB-low
                   broken within 9:30-11:00 window (whipsaw)
  AMBIGUOUS_DEAD   Neither ORB-high nor ORB-low broken between 9:30 and
                   11:00 ET (flatlines)

ORB high/low = the 9:30-9:31 ET bar's high/low (the 1-minute opening
range, matching live ORB mechanic).

Output: analysis/2026-05-16/classifier.csv
        analysis/2026-05-16/classifier_summary.md

Run on prod:
    docker exec apollo-market python -m scripts.classify_ep_shape
"""
from __future__ import annotations

import asyncio
import csv
import logging
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean, median
from zoneinfo import ZoneInfo

from agents.market_intelligence.collector import get_minute_bars

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

DATA_DIR = Path("analysis/2026-05-16")
ALERTS_CSV = DATA_DIR / "ep_cohort_alerts_60d.csv"
OUT_CSV = DATA_DIR / "classifier.csv"
OUT_MD = DATA_DIR / "classifier_summary.md"

FIXTURES = {  # expected class per user's qualitative read
    ("TRT", "2026-04-23"): "CLASS_B",     # 9M EP day; delayed breakout 5/15
    ("ONDS", "2026-05-14"): "CLASS_B",   # 1-min stopped 2x, 3rd worked late
    ("KLAR", "2026-05-14"): "CLASS_B",   # Class B variant (entered+stopped)
    ("CPA", "2026-05-14"): "CLASS_B",    # late EP fire + Class B
    ("CSCO", "2026-05-14"): "CLASS_A",   # ORB-high attempted, fundamentals don't support
}

CLASS_A = "CLASS_A"
CLASS_B = "CLASS_B"
CLASS_C = "CLASS_C"
AMB_CHOP = "AMBIGUOUS_CHOP"
AMB_DEAD = "AMBIGUOUS_DEAD"


def parse_bars(raw: list[dict], alert_date: date) -> list[dict]:
    """Filter to 9:30-11:00 ET on `alert_date`, return ET-tagged."""
    out = []
    for b in raw:
        t_utc = datetime.fromtimestamp(b["t"] / 1000, tz=timezone.utc)
        t_et = t_utc.astimezone(_ET)
        if t_et.date() != alert_date:
            continue
        hhmm = t_et.hour * 60 + t_et.minute
        if hhmm < 9 * 60 + 30 or hhmm > 11 * 60:
            continue
        out.append({
            "t_et": t_et,
            "minute": hhmm,
            "o": b.get("o"), "h": b.get("h"),
            "l": b.get("l"), "c": b.get("c"),
            "v": b.get("v"),
        })
    out.sort(key=lambda x: x["minute"])
    return out


def classify(bars: list[dict]) -> tuple[str, dict]:
    """Apply the 5-bucket classifier. Returns (class_label, debug_dict)."""
    if not bars:
        return AMB_DEAD, {"reason": "no_bars"}

    # ORB = 9:30-9:31 bar (first 1-min bar at minute 570)
    orb_bar = bars[0]
    orb_high = orb_bar["h"]
    orb_low = orb_bar["l"]
    if orb_high is None or orb_low is None:
        return AMB_DEAD, {"reason": "no_orb_hl"}

    minute_open = 9 * 60 + 30
    minute_945 = 9 * 60 + 45
    minute_1000 = 10 * 60

    # Walk bars in order, tracking events
    high_break_minute = None     # minute when high broke
    high_break_held = False      # whether held above ORB-high ≥5 min after break
    low_break_minute = None      # minute when low broke
    recovered_above_orb_high = False  # any bar after low-break closes > ORB-high

    minutes_above_high_after_break = 0
    session_high_pre = orb_high
    session_low_pre = orb_low
    late_breakout_after_1000 = False

    for i, b in enumerate(bars):
        if b["h"] is None or b["l"] is None:
            continue
        m = b["minute"]

        # Pre-window session running max (excluding ORB-high itself)
        if m > minute_open:
            session_high_pre = max(session_high_pre, b["h"])
            session_low_pre = min(session_low_pre, b["l"])

        # First high break
        if high_break_minute is None and b["h"] > orb_high:
            high_break_minute = m
        # First low break
        if low_break_minute is None and b["l"] < orb_low:
            low_break_minute = m
        # Hold tracking after high break
        if high_break_minute is not None and high_break_held is False:
            if b["l"] > orb_high:
                minutes_above_high_after_break += 1
                if minutes_above_high_after_break >= 5:
                    high_break_held = True
            else:
                # Held streak broken
                minutes_above_high_after_break = 0
        # Recovery: post low-break, any bar makes high > orb_high
        if (low_break_minute is not None and not recovered_above_orb_high
                and b["c"] is not None and b["c"] > orb_high):
            recovered_above_orb_high = True
        # Late breakout: after 10:00, 5-min high exceeds prior session highs
        if m >= minute_1000:
            if b["h"] > session_high_pre:
                late_breakout_after_1000 = True

    dbg = {
        "orb_high": round(orb_high, 4) if orb_high else None,
        "orb_low": round(orb_low, 4) if orb_low else None,
        "high_break_min": high_break_minute,
        "high_break_held": high_break_held,
        "low_break_min": low_break_minute,
        "recovered_after_low_break": recovered_above_orb_high,
        "late_breakout_after_1000": late_breakout_after_1000,
        "n_bars": len(bars),
    }

    # Priority order matters — the classifier asks: "could a trader
    # have taken a clean ORB-high entry within the window?" before
    # asking "did it eventually wash out?". A high-break-and-held
    # within 9:31-9:45 is CLASS_A regardless of late-session fade
    # (entry filled, stop trail handles the rest). A late fade is
    # captured in the per-trade pnl but not the entry-shape class.

    # CLASS_A — clean breakout within window (high broke in first 14
    # min AND held above for ≥5 min). Earliest-entry path.
    if (high_break_minute is not None
            and high_break_minute <= minute_open + 14
            and high_break_held):
        return CLASS_A, dbg

    # CLASS_B (late-window held): high broke at or after 9:45 ET and
    # held ≥5 min. ORB-low may or may not have broken before — what
    # matters is the LATER entry path resolved upward.
    if (high_break_minute is not None
            and high_break_minute >= minute_945
            and high_break_held):
        return CLASS_B, dbg

    # CLASS_B (no-break-then-late-rally): no break in window OR break
    # didn't hold, low intact, post-10:00 bar exceeds prior session
    # highs. Pradeep "delayed EP" intraday flavor.
    if ((high_break_minute is None or not high_break_held)
            and low_break_minute is None
            and late_breakout_after_1000):
        return CLASS_B, dbg

    # CLASS_C — washout: low broken, no recovery above ORB-high.
    # (Only reaches here if no clean A/B path — i.e. high never held.)
    if low_break_minute is not None and not recovered_above_orb_high:
        return CLASS_C, dbg

    # AMBIGUOUS_CHOP — high broken but failed to hold, AND low also
    # broken (in any order). Whipsaw.
    if (high_break_minute is not None and not high_break_held
            and low_break_minute is not None):
        return AMB_CHOP, dbg

    # AMBIGUOUS_DEAD — neither broken in window. Flatline.
    if high_break_minute is None and low_break_minute is None:
        return AMB_DEAD, dbg

    # Catch-all chop: high broke, never held, low never broke
    if high_break_minute is not None and not high_break_held \
            and low_break_minute is None:
        return AMB_CHOP, dbg

    return AMB_DEAD, dbg


def load_high_alerts() -> list[dict]:
    with ALERTS_CSV.open("r", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["score_tier"] == "HIGH"]
    return rows


def parse_float(v):
    try:
        return float(v) if v else None
    except ValueError:
        return None


def derive_outcome(row: dict) -> tuple[str, float | None]:
    """Return (state, decimal_ret). Mirrors breakdowns.py logic."""
    trade_status = row.get("trade_status", "")
    if row.get("trade_id") and trade_status == "closed":
        pnl = parse_float(row.get("total_pnl"))
        entry_px = parse_float(row.get("entry_price"))
        shares = parse_float(row.get("entry_shares"))
        if pnl is not None and entry_px and shares:
            return ("win" if pnl > 0 else "loss",
                    pnl / (entry_px * shares))
        if pnl is not None:
            return ("win" if pnl > 0 else "loss", None)
    ret_5d = parse_float(row.get("ret_5d"))
    if ret_5d is not None:
        return ("win" if ret_5d > 0.05 else "loss", ret_5d)
    fwd = parse_float(row.get("fwd_5d_pct"))
    if fwd is not None:
        return ("win" if fwd / 100.0 > 0.05 else "loss", fwd / 100.0)
    return ("pending", None)


async def classify_one(row: dict) -> dict:
    ticker = row["ticker"]
    alert_date = date.fromisoformat(row["alert_date"])
    raw = await get_minute_bars(ticker, row["alert_date"], row["alert_date"])
    bars = parse_bars(raw, alert_date)
    label, dbg = classify(bars)
    outcome, ret = derive_outcome(row)
    return {
        "ticker": ticker,
        "alert_date": row["alert_date"],
        "gap_pct": row.get("gap_pct"),
        "ep_score": row.get("ep_score"),
        "catalyst_quality": row.get("catalyst_quality"),
        "shape_class": label,
        "outcome": outcome,
        "ret": ret,
        "high_break_min": dbg.get("high_break_min"),
        "high_break_held": dbg.get("high_break_held"),
        "low_break_min": dbg.get("low_break_min"),
        "recovered": dbg.get("recovered_after_low_break"),
        "late_breakout_after_1000": dbg.get("late_breakout_after_1000"),
        "orb_high": dbg.get("orb_high"),
        "orb_low": dbg.get("orb_low"),
        "n_bars": dbg.get("n_bars"),
    }


async def main() -> None:
    rows = load_high_alerts()
    logger.info("loaded %d HIGH alerts to classify", len(rows))

    # Classify sequentially — Polygon semaphore handles rate limit
    results = []
    fixture_hits: dict[tuple[str, str], str] = {}
    for i, r in enumerate(rows):
        try:
            out = await classify_one(r)
        except Exception as e:
            logger.warning("classify failed for %s %s: %s",
                           r["ticker"], r["alert_date"], e)
            continue
        results.append(out)
        key = (out["ticker"], out["alert_date"])
        if key in FIXTURES:
            fixture_hits[key] = out["shape_class"]
        if (i + 1) % 25 == 0:
            logger.info("  classified %d/%d", i + 1, len(rows))

    # Write CSV
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)
    logger.info("wrote %s (%d rows)", OUT_CSV, len(results))

    # Summary
    by_class: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_class[r["shape_class"]].append(r)
    total = len(results)

    lines = [
        "# Class A/B/C/Chop/Dead — Classifier Summary",
        "",
        f"_N={total} HIGH alerts over 60d cohort._",
        "",
        "## Distribution + per-class outcomes",
        "",
        "| Class | N | Share | Win rate | Avg ret | Median ret | Pending |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for cls in [CLASS_A, CLASS_B, CLASS_C, AMB_CHOP, AMB_DEAD]:
        bucket = by_class.get(cls, [])
        n = len(bucket)
        if n == 0:
            lines.append(f"| {cls} | 0 | 0.0% | — | — | — | — |")
            continue
        rets = [r["ret"] for r in bucket if r["ret"] is not None]
        pending = sum(1 for r in bucket if r["outcome"] == "pending")
        wins = sum(1 for r in bucket if r["outcome"] == "win")
        evaluated = n - pending
        wr = wins / evaluated if evaluated else 0
        avg = mean(rets) if rets else None
        med = median(rets) if rets else None
        lines.append(
            f"| {cls} | {n} | {n / total * 100:.1f}% | "
            f"{wr * 100:.1f}% | "
            f"{f'{avg * 100:+.1f}%' if avg is not None else '—'} | "
            f"{f'{med * 100:+.1f}%' if med is not None else '—'} | "
            f"{pending} |"
        )
    lines.append("")
    ambiguous_share = (len(by_class.get(AMB_CHOP, [])) + len(by_class.get(AMB_DEAD, []))) / max(1, total)
    lines.append(f"**Ambiguous-share** (Chop + Dead) = "
                 f"{ambiguous_share * 100:.1f}%")
    if ambiguous_share > 0.2:
        lines.append("")
        lines.append("> ⚠ Above 20% gate (advisor caveat). ADR §9 parallel-"
                     "entry-path proposal must note classifier needs label "
                     "refinement before shipping a separate entry mechanic.")
    lines.append("")

    # Fixture verification
    lines.append("## Fixture verification")
    lines.append("")
    lines.append("| Ticker | Date | Expected | Got | Match |")
    lines.append("|---|---|---|---|:---:|")
    for key, expected in FIXTURES.items():
        got = fixture_hits.get(key, "NOT_IN_COHORT")
        match = "✓" if got == expected else "✗"
        lines.append(f"| {key[0]} | {key[1]} | {expected} | {got} | {match} |")
    lines.append("")

    # Class × catalyst_quality crosstab
    lines.append("## Class × catalyst quality (proxy for D1)")
    lines.append("")
    catq_keys = sorted({r["catalyst_quality"] or "(null)" for r in results})
    lines.append("| Class | " + " | ".join(catq_keys) + " | total |")
    lines.append("|---|" + "---|" * (len(catq_keys) + 1))
    for cls in [CLASS_A, CLASS_B, CLASS_C, AMB_CHOP, AMB_DEAD]:
        counts = defaultdict(int)
        for r in by_class.get(cls, []):
            counts[r["catalyst_quality"] or "(null)"] += 1
        row_total = sum(counts.values())
        lines.append(f"| {cls} | "
                     + " | ".join(str(counts[k]) for k in catq_keys)
                     + f" | {row_total} |")
    lines.append("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    logger.info("wrote %s", OUT_MD)


if __name__ == "__main__":
    asyncio.run(main())
