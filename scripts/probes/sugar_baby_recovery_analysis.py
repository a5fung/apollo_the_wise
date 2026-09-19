"""P7.1a Sugar Baby Recovery Analysis (decision-only).

For each of the 76 Block D alpha names (MAGNA53 HIGH that failed Day-1
+ made +5% within 21d), apply the FULL sugar baby filter chain on
their MAGNA53 alert_date with the close_in_range_pct cutoff varied.

The 76 alpha names are parsed from
`analysis/2026-05-16/delayed_ep_audit.md` table.

Output: `analysis/2026-05-17/sugar_baby_analysis.md` with:
  - Recovery distribution table at cutoffs 0.75/0.65/0.50/0.35/none
  - Per-name admission status (sorted by MFE 21d desc)
  - Filter-failure breakdown for names rejected at 0.50

Verdict thresholds:
  - Recovery ≥ 50% at chosen cutoff → ship Option A (loosen)
  - Recovery 20-50% → ship Option B (build separate path)
  - Recovery < 20% → skip P7.1 (filter is doing its job)

Run on prod:
  docker exec apollo-market python -m scripts.sugar_baby_recovery_analysis
"""
from __future__ import annotations

import asyncio
import logging
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

from agents.market_intelligence.db import get_pool
from agents.market_intelligence.ninem_detector import (
    is_9m_directional, is_green_close
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUT_MD = Path("analysis/2026-05-17/sugar_baby_recovery_analysis.md")
AUDIT_MD = Path("analysis/2026-05-16/delayed_ep_audit.md")

# Cutoffs to evaluate (close_in_range_pct minimum). 0.0 = no cutoff.
CUTOFFS = [0.75, 0.65, 0.50, 0.35, 0.0]


def parse_alpha_names() -> list[tuple[str, date, float]]:
    """Parse (ticker, alert_date, mfe_21d) from the delayed_ep_audit
    markdown table. Returns 76 names."""
    if not AUDIT_MD.exists():
        raise SystemExit(f"Missing: {AUDIT_MD}. Run Block D audit first.")
    text = AUDIT_MD.read_text(encoding="utf-8")

    # The table rows have format:
    # | TICKER | 2026-MM-DD | STATUS | ... | +X.X% |
    pattern = re.compile(
        r"^\|\s*([A-Z]{1,6})\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|.*\|\s*([+\-]\d+\.\d+)%\s*\|$",
        re.MULTILINE,
    )
    rows = []
    in_alpha_section = False
    for line in text.splitlines():
        if "Failed-Day-1 alpha names" in line:
            in_alpha_section = True
            continue
        if not in_alpha_section:
            continue
        m = pattern.match(line)
        if m:
            ticker, ad_str, mfe_str = m.group(1), m.group(2), m.group(3)
            rows.append((ticker, date.fromisoformat(ad_str), float(mfe_str)))
    return rows


async def fetch_filter_state(ticker: str, alert_date: date) -> dict | None:
    """Pull all sugar-baby filter inputs for one (ticker, alert_date).

    Returns dict with the gate values, or None if no daily row exists.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Main row
        row = await conn.fetchrow("""
            SELECT
                d.ticker, d.trade_date, d.close, d.open_price,
                d.high_price, d.low_price, d.volume,
                st.security_type
            FROM mi_daily_closes d
            LEFT JOIN mi_security_types st ON st.ticker = d.ticker
            WHERE d.ticker = $1 AND d.trade_date = $2
        """, ticker, alert_date)
        if not row:
            return None

        # ADV-20 (median of trailing 20 sessions BEFORE alert_date)
        adv_row = await conn.fetchrow("""
            WITH prior_20 AS (
                SELECT volume
                FROM mi_daily_closes
                WHERE ticker = $1
                  AND trade_date < $2
                  AND volume IS NOT NULL
                ORDER BY trade_date DESC
                LIMIT 20
            )
            SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY volume) AS adv_20,
                   COUNT(*) AS n_sessions
            FROM prior_20
        """, ticker, alert_date)

        # Prior context: prev_close + sma_10 + sma_50 + 20d-ago close
        ctx_row = await conn.fetchrow("""
            WITH prior AS (
                SELECT trade_date, close, volume
                FROM mi_daily_closes
                WHERE ticker = $1
                  AND trade_date < $2
                ORDER BY trade_date DESC
                LIMIT 50
            )
            SELECT
                (SELECT close FROM prior ORDER BY trade_date DESC LIMIT 1) AS prev_close,
                (SELECT AVG(close) FROM (SELECT close FROM prior ORDER BY trade_date DESC LIMIT 10) p10) AS sma_10,
                (SELECT AVG(close) FROM (SELECT close FROM prior ORDER BY trade_date DESC LIMIT 50) p50) AS sma_50,
                (SELECT close FROM prior ORDER BY trade_date DESC OFFSET 19 LIMIT 1) AS close_20d_ago,
                (SELECT COUNT(*) FROM prior) AS n_prior_sessions,
                -- SMA50 from 5d ago, to compute slope
                (SELECT AVG(close) FROM (SELECT close FROM prior ORDER BY trade_date DESC OFFSET 5 LIMIT 50) p50b) AS sma_50_5d_ago
        """, ticker, alert_date)

    adv_20 = adv_row["adv_20"] if adv_row else None
    n_sessions = ctx_row["n_prior_sessions"] if ctx_row else 0

    return {
        "ticker": row["ticker"],
        "trade_date": row["trade_date"],
        "open": float(row["open_price"]) if row["open_price"] is not None else None,
        "high": float(row["high_price"]) if row["high_price"] is not None else None,
        "low": float(row["low_price"]) if row["low_price"] is not None else None,
        "close": float(row["close"]) if row["close"] is not None else None,
        "volume": int(row["volume"]) if row["volume"] is not None else None,
        "security_type": row["security_type"],
        "adv_20": float(adv_20) if adv_20 is not None else None,
        "n_prior_sessions": int(n_sessions),
        "prev_close": float(ctx_row["prev_close"]) if ctx_row and ctx_row["prev_close"] else None,
        "sma_10": float(ctx_row["sma_10"]) if ctx_row and ctx_row["sma_10"] else None,
        "sma_50": float(ctx_row["sma_50"]) if ctx_row and ctx_row["sma_50"] else None,
        "close_20d_ago": float(ctx_row["close_20d_ago"]) if ctx_row and ctx_row["close_20d_ago"] else None,
        "sma_50_5d_ago": float(ctx_row["sma_50_5d_ago"]) if ctx_row and ctx_row["sma_50_5d_ago"] else None,
    }


def apply_sugar_baby_filter(state: dict, close_in_range_min: float) -> tuple[bool, list[str]]:
    """Apply the full sugar baby filter chain with the specified
    close_in_range_pct minimum. Returns (passed, list_of_failed_gates).
    """
    failed = []

    # Gate 1: security_type IN ('CS', 'ADRC') OR NULL (passes conservatively)
    st = state.get("security_type")
    if st is not None and st not in ("CS", "ADRC"):
        failed.append(f"security_type={st}")

    # Gate 2: volume ≥ 9M shares
    if state["volume"] is None or state["volume"] < 9_000_000:
        failed.append(f"volume<9M (={state['volume']})")

    # Gate 3: close ≥ $5
    if state["close"] is None or state["close"] < 5.0:
        failed.append(f"close<$5 (={state['close']})")

    # Gate 4: dollar_volume ≥ $50M
    if state["volume"] and state["close"]:
        dv = state["volume"] * state["close"]
        if dv < 50_000_000:
            failed.append(f"dollar_vol<$50M (=${dv/1e6:.1f}M)")
    else:
        failed.append("dollar_vol_unknown")

    # Gate 5: open/high/low present
    if any(state.get(k) is None for k in ("open", "high", "low")):
        failed.append("ohlc_missing")
        return False, failed  # can't compute further

    # Gate 6: close > open
    if state["close"] is None or state["open"] is None:
        failed.append("close_or_open_null")
    elif state["close"] <= state["open"]:
        failed.append(f"close<=open ({state['close']:.2f}<={state['open']:.2f})")

    # Gate 7: range > 0 AND range ≥ 2% of close
    rng = state["high"] - state["low"]
    if rng <= 0:
        failed.append("range=0")
    elif state["close"] and rng < state["close"] * 0.02:
        failed.append(f"range<2% (={rng/state['close']*100:.1f}%)")

    # Gate 8: close_in_range_pct ≥ cutoff
    if rng > 0:
        cir = (state["close"] - state["low"]) / rng
        if cir < close_in_range_min:
            failed.append(f"close_in_range<{close_in_range_min:.2f} (={cir:.2f})")
    else:
        failed.append("range=0_for_cir")

    # Gate 9: ADV available + volume ≥ 3× ADV
    if state["adv_20"] is None:
        failed.append("adv_unknown")
    elif state["volume"] is None or state["volume"] < state["adv_20"] * 3:
        ratio = (state["volume"] or 0) / max(state["adv_20"], 1)
        failed.append(f"vol<3xADV (={ratio:.1f}x)")

    # Gate 10: ≥10 prior sessions
    if state["n_prior_sessions"] < 10:
        failed.append(f"prior_sessions<10 (={state['n_prior_sessions']})")

    # Gate 11: sma_10 available + prev_close ≤ 1.20× sma_10
    if state["sma_10"] is None:
        failed.append("sma_10_unknown")
    elif state["prev_close"] is None:
        failed.append("prev_close_unknown")
    elif state["prev_close"] > state["sma_10"] * 1.20:
        ext_ratio = state["prev_close"] / state["sma_10"]
        failed.append(f"extension>1.20xSMA10 ({ext_ratio:.2f})")

    # Gate 12: destroyed-trend filter — REJECT if ALL THREE fail
    prev_20d_pct = None
    if state["prev_close"] and state["close_20d_ago"] and state["close_20d_ago"] > 0:
        prev_20d_pct = (state["prev_close"] - state["close_20d_ago"]) / state["close_20d_ago"]
    prev_vs_sma50 = None
    if state["prev_close"] and state["sma_50"] and state["sma_50"] > 0:
        prev_vs_sma50 = state["prev_close"] / state["sma_50"]
    sma50_slope_pct = None
    if state["sma_50"] and state["sma_50_5d_ago"] and state["sma_50_5d_ago"] > 0:
        sma50_slope_pct = (state["sma_50"] - state["sma_50_5d_ago"]) / state["sma_50_5d_ago"]

    if (prev_20d_pct is not None and prev_20d_pct < -0.10
            and prev_vs_sma50 is not None and prev_vs_sma50 < 0.85
            and sma50_slope_pct is not None and sma50_slope_pct < 0):
        failed.append(
            f"destroyed_trend (20d={prev_20d_pct:.1%}, vs_sma50={prev_vs_sma50:.2f}, sma50_slope={sma50_slope_pct:.1%})"
        )

    # Gate 13: is_9m_directional + is_green_close
    if state["prev_close"] and state["open"] and state["close"]:
        if not is_9m_directional(state["prev_close"], state["open"], state["close"]):
            failed.append("not_9m_directional")
        if not is_green_close(state["prev_close"], state["close"]):
            failed.append("not_green_close (close < prev_close+3%)")

    return len(failed) == 0, failed


def fmt_pct(v):
    return f"{v*100:+.1f}%" if v is not None else "—"


async def main() -> None:
    alpha_names = parse_alpha_names()
    logger.info("loaded %d alpha names from %s", len(alpha_names), AUDIT_MD)

    results = []
    for ticker, alert_date, mfe in alpha_names:
        try:
            state = await fetch_filter_state(ticker, alert_date)
        except Exception as e:
            logger.warning("fetch failed for %s %s: %s", ticker, alert_date, e)
            results.append({
                "ticker": ticker,
                "alert_date": alert_date,
                "mfe_21d": mfe,
                "no_data": True,
            })
            continue
        if state is None:
            results.append({
                "ticker": ticker,
                "alert_date": alert_date,
                "mfe_21d": mfe,
                "no_data": True,
            })
            continue

        # Compute close_in_range_pct for transparency
        rng = (state["high"] or 0) - (state["low"] or 0)
        cir = ((state["close"] or 0) - (state["low"] or 0)) / rng if rng > 0 else None

        admissions = {}
        all_failed = {}
        for cut in CUTOFFS:
            passed, failed_list = apply_sugar_baby_filter(state, cut)
            admissions[cut] = passed
            all_failed[cut] = failed_list

        results.append({
            "ticker": ticker,
            "alert_date": alert_date,
            "mfe_21d": mfe,
            "close_in_range_pct": cir,
            "admissions": admissions,
            "failed_at_050": all_failed.get(0.50, []),
            "no_data": False,
        })

    # ─── Compose markdown report ──────────────────────────────────────
    n_total = len(results)
    n_with_data = sum(1 for r in results if not r["no_data"])

    lines = [
        "# P7.1a Sugar Baby Recovery Analysis",
        "",
        f"_Applied full sugar baby filter chain at varying close_in_range_pct "
        f"cutoffs to {n_total} Block D alpha names "
        f"(MAGNA53 HIGH failed Day-1 + made +5% within 21d)._",
        "",
        f"**Data coverage**: {n_with_data}/{n_total} alpha names had daily "
        f"OHLC/ADV data on their MAGNA53 alert_date.",
        "",
        "## Recovery distribution",
        "",
        "Counts the names ADMITTED by the FULL sugar baby filter chain "
        "with the close_in_range_pct minimum varied.",
        "",
        "| close_in_range_pct ≥ | Admitted | of total | Recovery rate |",
        "|---|---:|---:|---:|",
    ]
    for cut in CUTOFFS:
        cnt = sum(1 for r in results if not r["no_data"] and r["admissions"].get(cut))
        pct = cnt / n_total * 100
        label = f"{cut:.2f}" if cut > 0 else "no cutoff"
        lines.append(f"| {label} | {cnt} | {n_total} | {pct:.1f}% |")
    lines.append("")

    # ─── Per-name admission table ─────────────────────────────────────
    lines.append("## Per-name admission status (sorted by MFE 21d desc)")
    lines.append("")
    lines.append("| Ticker | Alert date | MFE 21d | close_in_range | @0.75 | @0.65 | @0.50 | @0.35 | no cutoff |")
    lines.append("|---|---|---:|---:|:---:|:---:|:---:|:---:|:---:|")
    for r in sorted(results, key=lambda x: -x["mfe_21d"]):
        if r["no_data"]:
            lines.append(
                f"| {r['ticker']} | {r['alert_date']} | "
                f"{r['mfe_21d']:+.1f}% | NO DATA | — | — | — | — | — |"
            )
            continue
        cir_s = f"{r['close_in_range_pct']:.2f}" if r['close_in_range_pct'] is not None else "—"
        flags = {cut: ("✓" if r["admissions"].get(cut) else "✗") for cut in CUTOFFS}
        lines.append(
            f"| {r['ticker']} | {r['alert_date']} | "
            f"{r['mfe_21d']:+.1f}% | {cir_s} | "
            f"{flags[0.75]} | {flags[0.65]} | {flags[0.50]} | {flags[0.35]} | {flags[0.0]} |"
        )
    lines.append("")

    # ─── Failure breakdown at 0.50 ─────────────────────────────────────
    lines.append("## Why names fail at close_in_range ≥ 0.50 (full filter chain)")
    lines.append("")
    lines.append("Tallies gate-failures across names rejected at the 0.50 cutoff. "
                 "Names with multiple failures count toward each.")
    lines.append("")
    failure_counts = defaultdict(int)
    for r in results:
        if r["no_data"]:
            continue
        if r["admissions"].get(0.50):
            continue  # admitted
        for f in r["failed_at_050"]:
            # Collapse to gate prefix
            key = f.split(" (")[0].split("=")[0].strip()
            failure_counts[key] += 1
    lines.append("| Failed gate | N names |")
    lines.append("|---|---:|")
    for gate, n in sorted(failure_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {gate} | {n} |")
    lines.append("")

    # ─── Verdict ───────────────────────────────────────────────────────
    # Use the 0.50 cutoff as the primary decision point.
    cnt_050 = sum(1 for r in results if not r["no_data"] and r["admissions"].get(0.50))
    rec_050 = cnt_050 / n_total * 100

    lines.append("## Verdict")
    lines.append("")
    if rec_050 >= 50:
        verdict = "**Option A (LOOSEN)** — recovery ≥50% at cutoff 0.50."
    elif rec_050 >= 20:
        verdict = "**Option B (BUILD SEPARATE PATH)** — recovery 20-50% at cutoff 0.50."
    else:
        verdict = (
            "**Option C (SKIP P7.1)** — recovery <20% at cutoff 0.50. "
            "Sugar baby filter is doing its job; rely on P7.2 flag carryforward."
        )

    lines.append(f"- Recovery at cutoff 0.50 (full filter chain): "
                 f"**{cnt_050}/{n_total} = {rec_050:.1f}%**")
    lines.append(f"- Verdict: {verdict}")
    lines.append("")
    lines.append("**Fatigue-mitigation note** (per plan): if verdict is marginal "
                 "(20-40% recovery), default to Option C to avoid shipping a "
                 "semantic change on weak evidence.")
    lines.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    logger.info("wrote %s", OUT_MD)
    logger.info("VERDICT: recovery at 0.50 = %.1f%% → %s", rec_050,
                "OPTION A" if rec_050 >= 50 else "OPTION B" if rec_050 >= 20 else "OPTION C")


if __name__ == "__main__":
    asyncio.run(main())
