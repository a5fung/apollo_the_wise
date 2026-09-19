"""#468 — MODERATE-vs-HIGH EP realized-R study (operator "queue r study" 7/13).

Q4 (coverage-loop §5) showed MODERATE ≈ HIGH on RAW 5d forward return — but a
raw return isn't a TRADE: HIGH gets an ORB bracket entry, MODERATE gets a
briefing line. This study reconstructs a uniform bracket-trade simulation for
BOTH tiers and compares realized-R distributions.

BARS SOURCE (the honesty seam):
- `daily_proxy` (default, runs anywhere): yfinance daily OHLC. Entry proxy =
  open×1.005 when day-0 high clears it ("broke above the open" ≈ ORB break);
  stop = entry×(1−0.035) — 3.5% is the MEDIAN stop distance of the system's 71
  REAL bracket fills (mi_live_trades), so the proxy is anchored in actual
  ORB-low geometry, not a guess. Day-0 high/low ordering is unknowable from
  daily bars → a day-0 stop-touch counts as stopped (−1R), CONSERVATIVE and
  applied identically to both tiers — the COMPARISON is what survives the
  proxy; absolute R is understated.
- `polygon_minute` (stub): the precise ORB(9:30-9:31) reconstruction — run on
  a machine with POLYGON_API_KEY if the proxy read is borderline.

Exit: stop-hit (any day's low ≤ stop, days 0-5) else close of the 5th trading
day. No partials/trails — the raw bracket, same for both tiers.

Usage: python scripts/_468_realized_r_study.py <data_dir> [--out doc.md]
Read-only analysis; the tier-threshold / MODERATE-entry decision is the
OPERATOR's (THE LINE).
"""
from __future__ import annotations

import argparse
import json
import pickle
import statistics
import sys
import time
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

ENTRY_BREAK = 1.005          # day-0 high must clear open×this; entry at this
STOP_FRAC = 0.035            # median real bracket stop distance (n=71 live fills)
HOLD_DAYS = 5


def _fetch_daily(tickers: list[str], start: date, end: date, cache: Path) -> dict:
    out: dict = {}
    if cache.exists():
        with open(cache, "rb") as f:
            out = pickle.load(f)
    missing = [t for t in tickers if t not in out]
    if missing:
        import yfinance as yf
        print(f"fetching daily bars for {len(missing)} ticker(s)…")
        for i, t in enumerate(missing):
            try:
                h = yf.Ticker(t).history(start=start.isoformat(),
                                         end=end.isoformat(), auto_adjust=False)
                out[t] = None if h is None or h.empty else {
                    ts.date().isoformat(): (float(r["Open"]), float(r["High"]),
                                            float(r["Low"]), float(r["Close"]))
                    for ts, r in h.iterrows()}
            except Exception as e:
                print(f"  fetch failed {t}: {e}")
                out[t] = None
            if i % 25 == 24:
                print(f"  {i + 1}/{len(missing)}")
            time.sleep(0.15)
        with open(cache, "wb") as f:
            pickle.dump(out, f)
    return out


def simulate(bars: dict[str, tuple], alert_date: str) -> dict | None:
    """One bracket trade from daily bars. Returns None when day-0 bar is
    missing or the entry never triggers."""
    days = sorted(d for d in bars if d >= alert_date)
    if not days or days[0] != alert_date:
        return None
    o0, h0, l0, _ = bars[days[0]]
    if not o0 or o0 <= 0:
        return None
    entry = o0 * ENTRY_BREAK
    if h0 < entry:
        return {"triggered": False}
    stop = entry * (1 - STOP_FRAC)
    risk = entry - stop
    # day 0: ordering unknowable → stop-touch = stopped (conservative, both tiers)
    if l0 <= stop:
        return {"triggered": True, "r": -1.0, "exit": "stop_d0"}
    window = days[1:1 + HOLD_DAYS]
    for i, d in enumerate(window, 1):
        _, _, lo, cl = bars[d]
        if lo <= stop:
            return {"triggered": True, "r": -1.0, "exit": f"stop_d{i}"}
        if i == len(window):
            return {"triggered": True, "r": (cl - entry) / risk, "exit": f"close_d{i}"}
    return {"triggered": True, "r": 0.0, "exit": "open_window"}  # <5 settled days


def _dist(rs: list[float]) -> str:
    if not rs:
        return "n=0"
    return (f"n={len(rs):>3}  mean {statistics.mean(rs):+5.2f}R  "
            f"med {statistics.median(rs):+5.2f}R  win {sum(1 for r in rs if r > 0) / len(rs) * 100:3.0f}%  "
            f"expectancy {statistics.mean(rs):+5.2f}R")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    d = args.data_dir

    cohort = [json.loads(l) for l in open(d / "cohort.jsonl")]
    dates = [date.fromisoformat(r["alert_date"]) for r in cohort]
    tickers = sorted({r["ticker"] for r in cohort})
    bars_all = _fetch_daily(tickers, min(dates) - timedelta(days=3),
                            max(dates) + timedelta(days=14), d / "daily_cache.pkl")

    rows = []
    for r in cohort:
        b = bars_all.get(r["ticker"])
        sim = simulate(b, r["alert_date"]) if b else None
        rows.append({**r, "sim": sim})

    def tier_rows(tier):
        return [r for r in rows if r["score_tier"] == tier]

    L = [f"# #468 MODERATE-vs-HIGH realized-R study — {date.today().isoformat()}",
         "",
         f"Cohort: {len(rows)} alerts (mi_ep_alerts, all-time), bracket-sim on "
         f"daily-proxy bars (entry open×{ENTRY_BREAK}, stop −{STOP_FRAC:.1%} = the "
         f"median REAL fill stop distance n=71, exit stop-or-close-d5, no "
         f"partials). Day-0 stop-touch counts −1R (conservative, both tiers). "
         f"The COMPARISON is the deliverable; absolute R is understated."]
    for tier in ("HIGH", "MODERATE"):
        tr = tier_rows(tier)
        sims = [r["sim"] for r in tr if r["sim"]]
        trig = [s for s in sims if s.get("triggered")]
        settled = [s["r"] for s in trig if s.get("exit") != "open_window"]
        stopped = sum(1 for s in trig if s["r"] == -1.0)
        L.append(f"\n## {tier}")
        L.append(f"- alerts {len(tr)} · day-0 bar found {len(sims)} · "
                 f"triggered {len(trig)} ({len(trig) / len(sims) * 100:.0f}%) · "
                 f"stopped {stopped}/{len(trig)} ({stopped / max(1, len(trig)) * 100:.0f}%)")
        L.append(f"- realized-R: {_dist(settled)}")

    # score bands ACROSS tiers (ep_score is the raw score; final tier can be
    # judge-promoted above it, so bands deliberately ignore tier — this asks
    # whether the SCORE separates tradeable outcomes around the ~70 boundary)
    L.append("\n## Raw ep_score bands (tier-agnostic, same sim)")
    for name, lo, hi in (("score 80+", 80, 999), ("score 70-79", 70, 80),
                         ("score 60-69", 60, 70), ("score 50-59", 50, 60)):
        band = [r["sim"]["r"] for r in rows
                if lo <= (r["ep_score"] or 0) < hi and r["sim"]
                and r["sim"].get("triggered") and r["sim"].get("exit") != "open_window"]
        L.append(f"- {name:<13} {_dist(band)}")

    L.append("\n## Read")
    L.append("(filled by the analyst — see the summary line in the session log)")
    L.append("\nLimitations: daily-proxy (no true ORB range; day-0 ordering "
             "conservative); yfinance adjusted-history quirks on delistings; "
             "re-run with bars_source=polygon_minute for the precise version "
             "if the read is borderline.")

    report = "\n".join(L)
    out = args.out or (REPO / "docs" / "analysis"
                       / f"468_realized_r_study_{date.today().isoformat()}.md")
    out.write_text(report)
    print(report)
    print(f"\nreport → {out}")


if __name__ == "__main__":
    main()
