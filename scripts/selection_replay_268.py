"""#268 W1 — judge-era SELECTION REPLAY over reconstructed historical candidates.

THE question this answers (v1.1 roadmap, W1): what is the expectancy of the
POST-judge system (Opus judge, grounded corpus, lit theme axis) over a year of
candidates? The realized paper record only tests the pre-judge system (N≈30,
IEX-fill-skewed); this produces N=hundreds on the system we actually run.

Design (plan: ~/.claude/plans/selection-replay-268.md):
  outcomes are SELECTION-INDEPENDENT — simulate every candidate's ORB outcome
  once; cohort expectancy = filter those outcomes by floor/judge verdicts.

Stages (idempotent + resumable; run each as its own invocation, in order):
  --scan        backtester.historical_scan over the window → mi_ep_alerts rows
                tagged source='historical_scan' (isolated from every live KPI,
                which filter COALESCE(source,'live')='live').
  --grade       grounded catalyst grade per candidate (the LIVE
                _classify_catalyst_claude over the LIVE point-in-time corpus
                reconstruction) → catalyst_quality + claude_analysis +
                grounded_text + floor score via the LIVE _score_ep →
                baseline_floor_tier. Skips rows already graded.
  --judge       the LIVE judge (grade_holistic on JUDGE_MODEL=Opus) over the
                same payload assembly as production (_judge_replay_common),
                point-in-time Lane-2 narratives (NULL pre-#167 era → axis-dark,
                logged). Writes judge_* columns. Skips rows already judged.
  --simulate    backtester engine over the cohort (min_score=0: outcomes for
                ALL candidates; selection splits happen at --report) → CSV.
  --report      cohort expectancy table: floor-HIGH vs judge-HIGH vs the DELTA
                cohorts (judge-demoted floor-HIGHs / judge-promoted MODERATEs).
  --status      stage counts for the window (resume dashboard).

Cost control: --limit N per invocation; --grade/--judge print a projected-call
count and abort if it exceeds --max-calls (default 400) without --yes.

Run on prod (DB + Polygon + Anthropic):
  docker exec apollo-market python scripts/selection_replay_268.py --status \
      --from 2025-06-15 --to 2026-06-06

LOOKAHEAD HYGIENE: detected_at on historical rows is the INSERT time (wrong) —
this script pins the point-in-time bound to alert_date 09:35 ET for corpus +
narrative reconstruction. Residual caveats (logged in the analysis doc): FMP
profile/market-cap = current values; analyst_upgrades=0; pm_rvol/projection
axes unavailable (floor approximated — Phase A calibrates vs 90d of REAL
alerts); narratives dark before #167 (late May 2026).
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import sys
from datetime import date, datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_ET = ZoneInfo("America/New_York")
_SOURCE = "historical_scan"


def _pit_detected_at(alert_date: date) -> datetime:
    """Point-in-time bound for corpus/narrative reconstruction: the morning of
    the alert (09:35 ET), NOT the row's insert-time detected_at."""
    return datetime.combine(alert_date, dtime(9, 35), tzinfo=_ET)


async def _window_rows(conn, args, where_extra: str = "") -> list:
    return await conn.fetch(f"""
        SELECT id, ticker, alert_date, gap_pct, rel_volume, ep_score, score_tier,
               catalyst, catalyst_quality, claude_analysis, grounded_text,
               baseline_floor_tier, judge_tier, in_active_theme, in_narrative_cohort,
               pm_rvol, vol_percentile
        FROM mi_ep_alerts
        WHERE source = '{_SOURCE}'
          AND alert_date BETWEEN $1 AND $2
          {where_extra}
        ORDER BY alert_date, ticker
    """, args.date_from, args.date_to)


async def stage_status(args) -> None:
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(f"""
            SELECT COUNT(*) AS scanned,
                   COUNT(*) FILTER (WHERE catalyst_quality <> 'unknown') AS graded,
                   COUNT(*) FILTER (WHERE judge_tier IS NOT NULL) AS judged,
                   COUNT(*) FILTER (WHERE baseline_floor_tier = 'HIGH') AS floor_high,
                   COUNT(*) FILTER (WHERE judge_tier = 'HIGH') AS judge_high
            FROM mi_ep_alerts
            WHERE source = '{_SOURCE}' AND alert_date BETWEEN $1 AND $2
        """, args.date_from, args.date_to)
    print(f"window {args.date_from}..{args.date_to}: "
          f"scanned={row['scanned']} graded={row['graded']} judged={row['judged']} "
          f"floor_HIGH={row['floor_high']} judge_HIGH={row['judge_high']}")


async def stage_scan(args) -> None:
    from agents.market_intelligence.backtester.historical_scan import run_historical_scan
    res = await run_historical_scan(args.date_from, args.date_to)
    print(f"scan: {res}")


async def stage_grade(args) -> None:
    from agents.market_intelligence.collector import get_fmp_profile
    from agents.market_intelligence.db import get_pool
    from agents.market_intelligence.ep_detector import _classify_catalyst_claude, _score_ep
    from scripts._judge_replay_common import resolve_grounded_text

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await _window_rows(conn, args, "AND catalyst_quality = 'unknown'")
    rows = rows[: args.limit] if args.limit else rows
    if len(rows) > args.max_calls and not args.yes:
        print(f"ABORT: {len(rows)} grade calls projected > --max-calls {args.max_calls} "
              f"(use --limit or --yes)")
        return
    print(f"grading {len(rows)} candidates …")

    # Concurrency 3 (Phase A ran sequential at ~21s/row → 12h projected for the
    # 12-month window; sem-3 ≈ 4h). SEC fair-use comfortably holds at 3.
    sem = asyncio.Semaphore(3)
    done = 0

    async def _grade_one(r) -> None:
        nonlocal done
        try:
            profile = await get_fmp_profile(r["ticker"]) or {}
            company = profile.get("companyName") or r["ticker"]
            pit_row = dict(r)
            pit_row["detected_at"] = _pit_detected_at(r["alert_date"])
            grounded_text, _ginfo = await resolve_grounded_text(pit_row, company, True)
            quality, analysis = await _classify_catalyst_claude(
                r["ticker"], [], profile, grounded_text=grounded_text)

            # Floor via the LIVE scorer + the day's stored historical regime.
            async with pool.acquire() as conn:
                reg = await conn.fetchrow(
                    "SELECT regime, ep_threshold FROM mi_market_regime "
                    "WHERE regime_date <= $1 ORDER BY regime_date DESC LIMIT 1",
                    r["alert_date"])
                in_theme = await conn.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM mi_themes WHERE theme_date = $1 "
                    "AND stage IN ('Accelerating','Mainstream') AND $2 = ANY(tickers))",
                    r["alert_date"], r["ticker"])
            regime_label = (reg["regime"] if reg else None) or "Unknown"
            threshold = (reg["ep_threshold"] if reg else None) or 70
            mult = 1.2 if regime_label == "Bull" else 1.0
            score, _bd = _score_ep(
                gap_pct=float(r["gap_pct"] or 0),
                rel_volume=float(r["rel_volume"] or 0),
                catalyst_quality=quality,
                profile=profile,
                analyst_upgrades=0,
                regime_multiplier=mult,
                vol_percentile=50.0,
                prior_3m_change=None,
                projected_vol_multiple=None,
                in_active_theme=bool(in_theme),
            )
            floor_tier = "HIGH" if score >= threshold else ("MODERATE" if score >= 50 else "none")

            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE mi_ep_alerts SET
                        catalyst_quality = $2, claude_analysis = $3,
                        grounded_text = $4, ep_score = $5,
                        baseline_floor_tier = $6, in_active_theme = $7,
                        detected_at = $8
                    WHERE id = $1
                """, r["id"], quality, analysis[:2000], (grounded_text or "")[:8000],
                    float(score), floor_tier, bool(in_theme),
                    _pit_detected_at(r["alert_date"]))
            done += 1
            if done % 25 == 0:
                print(f"  graded {done}/{len(rows)}")
        except Exception as e:
            print(f"  GRADE FAIL {r['ticker']} {r['alert_date']}: {type(e).__name__}: {e}")

    async def _bounded(r) -> None:
        async with sem:
            await _grade_one(r)

    await asyncio.gather(*[_bounded(r) for r in rows])
    print(f"grade stage: {done}/{len(rows)} done")


async def stage_judge(args) -> None:
    import anthropic
    import os
    from agents.market_intelligence.db import get_pool
    from agents.market_intelligence.ep_grade_judge import RUBRIC_VERSION, grade_holistic
    from scripts._judge_replay_common import (
        build_judge_payload, fetch_narratives_for, fetch_profile)

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await _window_rows(
            conn, args, "AND catalyst_quality <> 'unknown' AND judge_tier IS NULL")
    rows = rows[: args.limit] if args.limit else rows
    if len(rows) > args.max_calls and not args.yes:
        print(f"ABORT: {len(rows)} judge calls projected > --max-calls {args.max_calls}")
        return
    print(f"judging {len(rows)} candidates …")

    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    sem = asyncio.Semaphore(3)
    done = 0
    # Run-scoped memos: tickers repeat across a 12-month window and narratives
    # are keyed by date only — without these, gather() stampedes yfinance/DB
    # with ~90% duplicate fetches at start-of-run (429 risk degrades profiles).
    _profile_memo: dict = {}
    _narrative_memo: dict = {}

    async def _one(r) -> None:
        nonlocal done
        try:
            # Whole body inside the semaphore (same pattern as stage_grade):
            # the prefetches must not fan out unbounded across all N rows.
            async with sem:
                if r["ticker"] not in _profile_memo:
                    _profile_memo[r["ticker"]] = await fetch_profile(r["ticker"])
                mc, sector, _company = _profile_memo[r["ticker"]]
                if r["alert_date"] not in _narrative_memo:
                    _narrative_memo[r["alert_date"]] = await fetch_narratives_for(r["alert_date"])
                narratives = _narrative_memo[r["alert_date"]]
                pit_row = dict(r)
                pit_row["score_tier"] = r["baseline_floor_tier"]  # floor drives payload tier
                payload, _rm = build_judge_payload(
                    pit_row, r["grounded_text"], mc, sector, active_narratives=narratives)
                # Retry-with-backoff (Phase B postmortem 6/11: 1307 grades then
                # 1307 Opus judges back-to-back tripped org rate limits —
                # grade_holistic swallows 429s into None, so 2,122 silent
                # fail-opens. None → wait and retry; the stage stays idempotent
                # for anything that still fails.)
                v = None
                for attempt in range(4):
                    v = await grade_holistic(client, payload, timeout=30)
                    if v is not None:
                        break
                    await asyncio.sleep(20 * (attempt + 1))
            if v is None:
                print(f"  JUDGE NULL {r['ticker']} {r['alert_date']} (fail-open after retries)")
                return
            # Persist verdict columns ONLY — never score_tier/authority (the
            # floor must stay readable beside the verdict). UPDATE BY ID
            # (PK — cannot resolve to a live twin, unlike the live writer's
            # ticker+date key).
            async with pool.acquire() as conn:
                await conn.execute(f"""
                    UPDATE mi_ep_alerts SET
                        judge_tier = $2, judge_direction = $3,
                        judge_rationale = $4, judge_materiality_tier = $5,
                        fire_axes = $6, rubric_version = $7
                    WHERE id = $1 AND source = '{_SOURCE}'
                """, r["id"], v.get("tier"), v.get("direction_vs_floor"),
                    (v.get("rationale") or "")[:1000], v.get("materiality_tier"),
                    v.get("fire_axes"), RUBRIC_VERSION)
            done += 1
            if done % 25 == 0:
                print(f"  judged {done}")
        except Exception as e:
            print(f"  JUDGE FAIL {r['ticker']} {r['alert_date']}: {type(e).__name__}: {e}")

    await asyncio.gather(*[_one(r) for r in rows])
    try:
        await client.close()
    except Exception:
        pass
    print(f"judge stage: {done}/{len(rows)} done")


async def stage_simulate(args) -> None:
    from agents.market_intelligence.backtester.engine import run_backtest
    result = await run_backtest(
        from_date=args.date_from, to_date=args.date_to,
        position_size=10_000, min_score=0, initial_capital=1_000_000,
        source_filter=_SOURCE,
        or_window_bars=args.or_window,
        wide_open_atr_mult=args.wide_open_atr,
    )
    # Custom per-trade CSV with computed R: risk basis = Σ shares×(entry−stop)
    # over actual entries (re-entries included). Consistent across cohorts —
    # the comparison is cohort-vs-cohort, not absolute-R-precise.
    out = args.csv
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ticker", "alert_date", "skipped", "skip_reason",
                "total_pnl", "risk_dollars", "r_multiple", "hold_days"])
    for t in list(result.trades) + list(result.skipped_trades):
        risk = sum(e.shares * max(e.entry_price - e.stop_price, 0.0001)
                   for e in t.entries)
        r_mult = (t.total_pnl / risk) if risk and not t.skipped else 0.0
        w.writerow([t.ticker, t.alert_date, t.skipped, t.skip_reason or "",
                    f"{t.total_pnl:.2f}", f"{risk:.2f}", f"{r_mult:.3f}",
                    t.hold_days])
    Path(out).write_text(buf.getvalue(), encoding="utf-8")
    print(f"simulated {len(result.trades)} trades "
          f"(+{len(result.skipped_trades)} skipped) → {out}")


async def stage_report(args) -> None:
    """Join verdicts × simulated outcomes (CSV from --simulate) → cohort table."""
    from agents.market_intelligence.db import get_pool
    src = args.csv
    trades: dict[tuple, dict] = {}
    with io.open(src, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                trades[(row["ticker"], row["alert_date"])] = {
                    "r": float(row.get("r_multiple") or 0),
                    "skipped": (row.get("skipped") or "").lower() in ("true", "1"),
                }
            except (KeyError, ValueError):
                continue

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await _window_rows(conn, args, "AND judge_tier IS NOT NULL")

    def _stats(keys) -> str:
        rs = [trades[k]["r"] for k in keys if k in trades and not trades[k]["skipped"]]
        if not rs:
            return "n=0"
        wins = sum(1 for r in rs if r > 0)
        return (f"n={len(rs)} exp={sum(rs)/len(rs):+.2f}R win={wins/len(rs):.0%} "
                f"sum={sum(rs):+.1f}R")

    def _k(r) -> tuple:
        return (r["ticker"], str(r["alert_date"]))

    floor_high = [_k(r) for r in rows if r["baseline_floor_tier"] == "HIGH"]
    judge_high = [_k(r) for r in rows if r["judge_tier"] == "HIGH"]
    demoted = [_k(r) for r in rows
               if r["baseline_floor_tier"] == "HIGH" and r["judge_tier"] != "HIGH"]
    promoted = [_k(r) for r in rows
                if r["baseline_floor_tier"] != "HIGH" and r["judge_tier"] == "HIGH"]

    print(f"=== SELECTION REPLAY #268 — {args.date_from}..{args.date_to} "
          f"({len(rows)} judged candidates, {len(trades)} simulated) ===")
    print(f"  PRE-JUDGE system (floor-HIGH):        {_stats(floor_high)}")
    print(f"  POST-JUDGE system (judge-HIGH):       {_stats(judge_high)}")
    print(f"  judge-DEMOTED floor-HIGHs (avoided):  {_stats(demoted)}")
    print(f"  judge-PROMOTED moderates (added):     {_stats(promoted)}")
    print("Read: the post-judge line is the 6/22 evidence; demoted with negative "
          "exp = the judge removing losers; promoted with positive exp = adding winners.")


def main() -> None:
    ap = argparse.ArgumentParser(description="#268 selection replay")
    ap.add_argument("--from", dest="date_from", type=date.fromisoformat, required=True)
    ap.add_argument("--to", dest="date_to", type=date.fromisoformat, required=True)
    for s in ("scan", "grade", "judge", "simulate", "report", "status"):
        ap.add_argument(f"--{s}", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-calls", dest="max_calls", type=int, default=400)
    ap.add_argument("--csv", default=None)
    ap.add_argument("--yes", action="store_true")
    # W2 entry-geometry variants (defaults = live behavior; study #1 2026-06-12)
    ap.add_argument("--or-window", dest="or_window", type=int, default=1,
                    help="opening-range window in 1-min bars (1 = live)")
    ap.add_argument("--wide-open-atr", dest="wide_open_atr", type=float, default=None,
                    help="skip when OR range > this multiple of ATR14 (e.g. 0.275)")
    args = ap.parse_args()
    # Resolve the CSV path ONCE — simulate writes it, report reads it.
    # Geometry variants get their own CSV so the baseline is never clobbered.
    variant = ""
    if args.or_window != 1:
        variant += f"_orw{args.or_window}"
    if args.wide_open_atr is not None:
        variant += f"_woatr{args.wide_open_atr}"
    args.csv = args.csv or f"/tmp/selection_replay_268_{args.date_from}_{args.date_to}{variant}.csv"

    stages = [(args.scan, stage_scan), (args.grade, stage_grade),
              (args.judge, stage_judge), (args.simulate, stage_simulate),
              (args.report, stage_report), (args.status, stage_status)]
    ran = False
    for flag, fn in stages:
        if flag:
            asyncio.run(fn(args))
            ran = True
    if not ran:
        asyncio.run(stage_status(args))


if __name__ == "__main__":
    main()
