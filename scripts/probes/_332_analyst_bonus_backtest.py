"""#332 analyst-bonus backtest probe — READ-ONLY (no writes, no scoring change).

Question (operator, gated on this backtest): the `_score_ep` analyst bonus
(`breakdown["analyst"] = min(analyst_upgrades * 2, 5) if analyst_upgrades >= 3 else 0`,
ep_detector.py ~1133) silently vanishes on cached-grade ticks (`upgrades_30d = 0`
hardcode, ep_detector.py ~1944). FIX (thread the real value every tick) vs
REMOVE (drop the bonus) vs KEEP?

This probe answers three things:
  A. LIVE MECHANISM — what does the production feed (`get_fmp_analyst_ratings`,
     collector.py: yfinance `Ticker.recommendations` + the line-2074 aggregation)
     actually return TODAY for real alerted tickers? (Runs the REAL function,
     not a lookalike — memory `rigor-before-paid-eval-spend`.)
  B. FIX IMPACT — which stored alerts were (a) inserted on a cached tick
     (identified from mi_ep_scan_log same-day trajectory: an earlier graded row
     exists before the passed row) and (b) sit within the bonus band of the
     HIGH threshold (ep_score + 5*mult >= ep_threshold for stored MODERATEs)?
  C. BONUS VALUE — reconstruct true upgrades-in-30d per alert as-of alert_date
     from yfinance `upgrades_downgrades` (dated events) and test whether
     bonus-eligible (>=3) alerts outperform on fwd_5d/fwd_10d outcomes
     (mi_ep_scan_outcomes join — same join as judge_review.py).

Fidelity limits (stated, not hidden):
  * The per-tick cached-vs-uncached score is NOT logged anywhere; score_breakdown
    is never persisted (in-memory only, ep_detector.py:3007). Part B therefore
    reconstructs "cached tick" from the scan-log trajectory. Blind spots:
    (1) pre-2026-04-30 scan_log was UPSERT (one row/ticker/day — no trajectory);
    (2) a container restart between the grade tick and the alert tick clears the
        in-memory cache -> the alert tick was actually uncached (rare, undetectable);
    (3) pre-#405 (2026-07-03) only filter-survivors were cached.
  * Part C's `upgrades_downgrades` is Yahoo's CURRENT snapshot of dated events —
    as-known-today, not as-served-on-alert-date. Counting is done with the live
    code's own grade set (code-faithful semantic) and a stricter Action=='up'
    semantic, both reported.
  * The live feed has returned 0 for every ticker since 2026-03-14 (yfinance
    0.2+/1.x `recommendations` is the AGGREGATE count table — integer counts
    never match the grade-string set; before 3/14 the FMP endpoint 403'd -> []).
    Part A verifies this against the real feed; Parts B/C therefore measure the
    LATENT exposure/value of the signal, not realized history.

Usage (from repo root):
  python scripts/probes/_332_analyst_bonus_backtest.py --print-sql   # queries only
  python scripts/probes/_332_analyst_bonus_backtest.py               # full run (ssh + yahoo)
  python scripts/probes/_332_analyst_bonus_backtest.py --skip-yahoo  # DB-only parts
  python scripts/probes/_332_analyst_bonus_backtest.py --ssh apollo@87.99.134.162

READ-ONLY: every SQL statement is a SELECT; nothing in the repo or DB is mutated.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import subprocess
import sys
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

DEFAULT_SSH_HOST = "apollo@87.99.134.162"
# NB: ssh joins argv with spaces and the REMOTE shell re-parses it — the field
# separator must be shell-quoted or `|` becomes a remote pipeline.
PSQL_CMD = ("docker exec -i apollo-postgres "
            "psql -U apollo -d apollo -tA -F '|' -v ON_ERROR_STOP=1")

# The live bonus's own positive-grade set (collector.py get_fmp_analyst_ratings)
GRADE_SET = {"strong buy", "buy", "outperform", "overweight"}
BONUS_RAW_PTS = 5          # min(upgrades*2, 5) — always exactly 5 once >= 3
BONUS_THRESHOLD = 3        # analyst_upgrades >= 3 fires the bonus
CACHE_DEFAULT = "/tmp/_332_yahoo_cache.json"

# ── The exact prod SQL (also emitted by --print-sql) ─────────────────────────
# Q1: every live EP alert + regime (threshold + Bull multiplier input) + outcomes.
# Join shapes follow judge_review.py (outcomes) and db.py LIVE_SOURCE_SQL (#268).
Q1_ALERTS = """
SELECT a.ticker,
       a.alert_date,
       ROUND(a.ep_score::numeric, 1)              AS ep_score,
       a.score_tier,
       COALESCE(a.baseline_floor_tier, a.score_tier) AS floor_tier,
       COALESCE(a.grade_engine_authority, 'floor')   AS authority,
       COALESCE(a.confidence_multiplier, 1.0)        AS conf_mult,
       to_char(COALESCE(a.detected_at, a.created_at) AT TIME ZONE 'America/New_York',
               'YYYY-MM-DD HH24:MI:SS')           AS detected_et,
       COALESCE(r.regime, 'unknown')              AS regime,
       COALESCE(r.ep_threshold, 70)               AS ep_threshold,
       o.fwd_5d_pct, o.fwd_10d_pct, o.n_sessions_10d
FROM mi_ep_alerts a
LEFT JOIN mi_market_regime r    ON r.regime_date = a.alert_date
LEFT JOIN mi_ep_scan_outcomes o ON o.ticker = a.ticker AND o.scan_date = a.alert_date
WHERE COALESCE(a.source, 'live') = 'live'
ORDER BY a.alert_date, a.ticker;
"""

# Q2: same-day scan-log trajectory for every alerted (ticker, date) — used to
# classify whether the alert's passing tick had a PRIOR graded tick that day
# (=> the passing tick ran the cached-grade path, upgrades_30d hardcoded 0).
Q2_TRAJECTORY = """
SELECT s.ticker,
       s.scan_date,
       to_char(s.scan_time_et AT TIME ZONE 'America/New_York',
               'YYYY-MM-DD HH24:MI:SS')           AS tick_et,
       COALESCE(s.filter_reason, '')              AS filter_reason,
       s.ep_score,
       COALESCE(s.catalyst_quality, '')           AS catalyst_quality
FROM mi_ep_scan_log s
JOIN (SELECT DISTINCT ticker, alert_date FROM mi_ep_alerts
      WHERE COALESCE(source, 'live') = 'live') a
  ON a.ticker = s.ticker AND a.alert_date = s.scan_date
ORDER BY s.ticker, s.scan_date, s.scan_time_et NULLS FIRST, s.id;
"""

# Q3: phantom missed-alert band — graded scan ticks that never produced an
# alert that day and whose best score sits within the max bonus effect
# (5 raw * 1.2 Bull * 1.2 conf = 7.2 final pts) below the 50 insert bar.
# A working bonus (>=3 upgrades) could have crossed these into MODERATE.
# Approximation: per-tick confidence_multiplier is not in scan_log; the band
# uses the MAX possible effect, so this is an UPPER bound on candidates.
Q3_PHANTOM_BAND = """
SELECT s.ticker, s.scan_date, ROUND(MAX(s.ep_score)::numeric, 1) AS best_score
FROM mi_ep_scan_log s
LEFT JOIN mi_ep_alerts a
  ON a.ticker = s.ticker AND a.alert_date = s.scan_date
 AND COALESCE(a.source, 'live') = 'live'
WHERE s.catalyst_quality IS NOT NULL AND s.catalyst_quality <> ''
  AND s.ep_score IS NOT NULL
  AND a.ticker IS NULL
  AND s.ep_score >= 42.8 AND s.ep_score < 50
GROUP BY s.ticker, s.scan_date
ORDER BY s.scan_date, s.ticker;
"""

ALL_SQL = {"Q1_ALERTS": Q1_ALERTS, "Q2_TRAJECTORY": Q2_TRAJECTORY,
           "Q3_PHANTOM_BAND": Q3_PHANTOM_BAND}


def run_sql(host: str, sql: str) -> list[list[str]]:
    """Run a read-only SELECT on prod postgres via ssh + docker exec. -tA|-F'|'."""
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, PSQL_CMD],
        input=sql, capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"psql failed ({proc.returncode}): {proc.stderr[:500]}")
    return [line.split("|") for line in proc.stdout.splitlines() if line.strip()]


def _f(v: str) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── Part A: the LIVE mechanism ───────────────────────────────────────────────
async def live_mechanism_check(tickers: list[str]) -> dict[str, int]:
    """Run the REAL production feed + the exact ep_detector.py:2074 aggregation."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from agents.market_intelligence.collector import get_fmp_analyst_ratings

    out: dict[str, int] = {}
    for t in tickers:
        ratings = await get_fmp_analyst_ratings(t)
        # verbatim aggregation from ep_detector.py line ~2074:
        upgrades_30d = sum(1 for r in ratings if r.get("analystRatingsStrongBuy", 0) > 0)
        out[t] = upgrades_30d
        await asyncio.sleep(0.4)
    return out


# ── Part B helpers: cached-tick classification ───────────────────────────────
TRAJECTORY_ERA_START = date(2026, 4, 30)  # a61c9fa: scan_log upsert -> per-tick append


def classify_cached_tick(alert_rows: dict, traj: dict) -> None:
    """Annotate each alert with tick_class:
    cached        — an earlier same-day GRADED row (catalyst_quality set) precedes
                    the passing row -> the passing tick ran the cached path.
    first_tick    — the passing row is the first graded row of the day.
    no_trajectory — pre-2026-04-30 (upsert era) or no scan-log rows found.
    """
    for (ticker, d), a in alert_rows.items():
        rows = traj.get((ticker, d), [])
        if d < TRAJECTORY_ERA_START or not rows:
            a["tick_class"] = "no_trajectory"
            continue
        # passing row = first row with no filter_reason and a tier-bearing score
        pass_idx = next(
            (i for i, r in enumerate(rows) if not r["filter_reason"] and r["ep_score"] is not None),
            None,
        )
        if pass_idx is None:
            a["tick_class"] = "no_trajectory"
            continue
        earlier_graded = any(r["catalyst_quality"] for r in rows[:pass_idx])
        a["tick_class"] = "cached" if earlier_graded else "first_tick"


# ── Part C: as-of reconstruction from dated upgrade events ───────────────────
def fetch_upgrade_events(tickers: list[str], cache_path: str) -> dict[str, list]:
    """yfinance Ticker.upgrades_downgrades -> [[date_iso, to_grade, action], ...].
    Cached to disk so re-runs are free. Read-only w.r.t. the repo/DB."""
    import yfinance as yf  # deferred: --skip-yahoo must work without it

    cache_file = Path(cache_path)
    cache: dict[str, list] = {}
    if cache_file.exists():
        cache = json.loads(cache_file.read_text())
    missing = [t for t in tickers if t not in cache]
    for i, t in enumerate(missing):
        try:
            ud = yf.Ticker(t).upgrades_downgrades
            if ud is None or ud.empty:
                cache[t] = []
            else:
                cache[t] = [
                    [str(idx.date()), str(row.get("ToGrade", "")), str(row.get("Action", ""))]
                    for idx, row in ud.iterrows()
                ]
        except Exception as e:  # noqa: BLE001 — probe: record and continue
            print(f"    yahoo fetch failed {t}: {e}", file=sys.stderr)
            cache[t] = None  # explicit failure marker (distinct from "no events")
        if (i + 1) % 25 == 0:
            print(f"    ... {i + 1}/{len(missing)} tickers fetched")
            cache_file.write_text(json.dumps(cache))
        time.sleep(0.6)
    cache_file.write_text(json.dumps(cache))
    return cache


def recon_upgrades_30d(events: list | None, as_of: date) -> tuple[int | None, int | None]:
    """(code_faithful, strict) counts of upgrade events in the 30d ending as_of.
    code_faithful: ToGrade in the live GRADE_SET (any Action) — what the bonus's
    own semantics count. strict: same AND Action == 'up' (a real upgrade)."""
    if events is None:
        return None, None
    lo = as_of - timedelta(days=30)
    faithful = strict = 0
    for d_iso, to_grade, action in events:
        d = date.fromisoformat(d_iso)
        if not (lo < d <= as_of):
            continue
        if to_grade.strip().lower() in GRADE_SET:
            faithful += 1
            if action.strip().lower() == "up":
                strict += 1
    return faithful, strict


# ── stats helpers (pure python — no scipy dependency) ────────────────────────
def median(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def perm_test_mean_diff(a: list[float], b: list[float], n_iter: int = 10000) -> float | None:
    """Two-sided permutation p-value for mean(a) - mean(b)."""
    if len(a) < 3 or len(b) < 3:
        return None
    rng = random.Random(332)
    obs = abs(sum(a) / len(a) - sum(b) / len(b))
    pool, na, hits = a + b, len(a), 0
    for _ in range(n_iter):
        rng.shuffle(pool)
        d = abs(sum(pool[:na]) / na - sum(pool[na:]) / (len(pool) - na))
        if d >= obs - 1e-12:
            hits += 1
    return hits / n_iter


def group_stats(rows: list[dict], key: str) -> str:
    xs5 = [r["fwd_5d"] for r in rows if r["fwd_5d"] is not None]
    xs10 = [r["fwd_10d"] for r in rows if r["fwd_10d"] is not None]
    win10 = sum(1 for x in xs10 if x > 0)
    return (f"N={len(rows)} (fwd10 N={len(xs10)}) | "
            f"med fwd5 {median(xs5):+.1f}% | med fwd10 {median(xs10):+.1f}% | "
            f"mean fwd10 {sum(xs10)/len(xs10):+.1f}% | win10 {win10}/{len(xs10)} "
            f"({100*win10/len(xs10):.0f}%)" if xs10 else f"N={len(rows)} (no fwd10 outcomes)")


# ── main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ssh", default=DEFAULT_SSH_HOST)
    ap.add_argument("--print-sql", action="store_true")
    ap.add_argument("--skip-yahoo", action="store_true",
                    help="skip Part A (live feed) and Part C (reconstruction)")
    ap.add_argument("--cache", default=CACHE_DEFAULT)
    ap.add_argument("--live-check-n", type=int, default=20,
                    help="alerted tickers to run through the REAL live feed in Part A")
    args = ap.parse_args()

    if args.print_sql:
        for name, sql in ALL_SQL.items():
            print(f"-- {name} (read-only; run via: ssh {DEFAULT_SSH_HOST} "
                  f"docker exec -i apollo-postgres psql -U apollo -d apollo)")
            print(sql)
        return

    # ── DB pull ──
    print("== Q1: live alerts + regime + outcomes ==")
    q1 = run_sql(args.ssh, Q1_ALERTS)
    alerts: dict[tuple[str, date], dict] = {}
    for r in q1:
        (ticker, alert_date, ep_score, score_tier, floor_tier, authority,
         conf_mult, detected_et, regime, ep_threshold, fwd5, fwd10, ns10) = r
        d = date.fromisoformat(alert_date)
        regime_mult = 1.2 if regime == "Bull" else 1.0   # ep_detector.py:1370
        mult = regime_mult * (float(conf_mult) or 1.0)
        alerts[(ticker, d)] = {
            "ticker": ticker, "date": d, "ep_score": float(ep_score),
            "tier": score_tier, "floor_tier": floor_tier, "authority": authority,
            "mult": mult, "detected_et": detected_et, "regime": regime,
            "threshold": float(ep_threshold),
            "bonus_pts": BONUS_RAW_PTS * mult,           # what +5 raw is worth post-multiplier
            "fwd_5d": _f(fwd5), "fwd_10d": _f(fwd10),
        }
    print(f"   {len(alerts)} live alerts "
          f"({min(a['date'] for a in alerts.values())} .. {max(a['date'] for a in alerts.values())})")

    print("== Q2: same-day scan trajectories ==")
    q2 = run_sql(args.ssh, Q2_TRAJECTORY)
    traj: dict[tuple[str, date], list[dict]] = defaultdict(list)
    for r in q2:
        ticker, scan_date, tick_et, filter_reason, ep_score, cq = r
        traj[(ticker, date.fromisoformat(scan_date))].append({
            "tick_et": tick_et, "filter_reason": filter_reason,
            "ep_score": _f(ep_score), "catalyst_quality": cq,
        })
    classify_cached_tick(alerts, traj)
    by_class = defaultdict(int)
    for a in alerts.values():
        by_class[a["tick_class"]] += 1
    print(f"   tick classes: {dict(by_class)}")

    print("== Q3: phantom missed-alert band (graded, no alert, 42.8 <= best < 50) ==")
    q3 = run_sql(args.ssh, Q3_PHANTOM_BAND)
    phantom = [{"ticker": r[0], "date": date.fromisoformat(r[1]), "best_score": float(r[2])}
               for r in q3]
    print(f"   {len(phantom)} (ticker, day) candidates in the band")

    # ── Part A: live mechanism ──
    live_result: dict[str, int] = {}
    if not args.skip_yahoo:
        controls = ["NVDA", "AAPL", "MSFT", "PLTR", "TSLA"]  # heaviest analyst coverage
        alerted = sorted({a["ticker"] for a in alerts.values()})
        sample = alerted[:: max(1, len(alerted) // args.live_check_n)][: args.live_check_n]
        print(f"== Part A: REAL live feed (collector.get_fmp_analyst_ratings + "
              f"ep_detector:2074 aggregation) over {len(controls)} controls + "
              f"{len(sample)} alerted tickers ==")
        live_result = asyncio.run(live_mechanism_check(controls + sample))
        nonzero = {t: v for t, v in live_result.items() if v != 0}
        print(f"   upgrades_30d nonzero: {nonzero or 'NONE — feed returns 0 for every ticker'}")
        print(f"   (all values: {live_result})")

    # ── Part C: reconstruction ──
    if not args.skip_yahoo:
        tickers = sorted({a["ticker"] for a in alerts.values()}
                         | {p["ticker"] for p in phantom})
        print(f"== Part C: as-of reconstruction (upgrades_downgrades) over "
              f"{len(tickers)} tickers ==")
        cache = fetch_upgrade_events(tickers, args.cache)
        failed = [t for t in tickers if cache.get(t) is None]
        for a in alerts.values():
            fa, st = recon_upgrades_30d(cache.get(a["ticker"]), a["date"])
            a["recon_faithful"], a["recon_strict"] = fa, st
        for p in phantom:
            fa, st = recon_upgrades_30d(cache.get(p["ticker"]), p["date"])
            p["recon_faithful"], p["recon_strict"] = fa, st
        if failed:
            print(f"   fetch failures (excluded): {failed}")
    else:
        for a in alerts.values():
            a["recon_faithful"] = a["recon_strict"] = None
        for p in phantom:
            p["recon_faithful"] = p["recon_strict"] = None

    # ── Report: FIX IMPACT ──
    print("\n===== FIX IMPACT (Part B) =====")
    cached_alerts = [a for a in alerts.values() if a["tick_class"] == "cached"]
    print(f"Alerts inserted on a CACHED tick (upgrades hardcoded 0 at scoring): "
          f"{len(cached_alerts)}/{len(alerts)}")
    print("Given the live feed returns 0 on UNCACHED ticks too (Part A), the "
          "realized cached-vs-uncached score delta is 0 for every retained alert.")
    borderline = [a for a in alerts.values()
                  if a["tier"] == "MODERATE"
                  and a["ep_score"] < a["threshold"] <= a["ep_score"] + a["bonus_pts"]]
    print(f"\nLATENT band — stored MODERATEs within +{BONUS_RAW_PTS}*mult of HIGH "
          f"(would flip if a real bonus had fired): {len(borderline)}")
    for a in sorted(borderline, key=lambda x: x["date"]):
        rec = (f" recon30d faithful={a['recon_faithful']} strict={a['recon_strict']}"
               if a["recon_faithful"] is not None else "")
        print(f"   {a['date']} {a['ticker']:<6} score {a['ep_score']:.1f} "
              f"thr {a['threshold']:.0f} (+{a['bonus_pts']:.1f}) tick={a['tick_class']}"
              f" auth={a['authority']}{rec}")
    flips = [a for a in borderline
             if (a["recon_faithful"] or 0) >= BONUS_THRESHOLD and a["tick_class"] == "cached"]
    print(f"\nWOULD-HAVE-FLIPPED under a WORKING feed + the cached-tick bug "
          f"(cached tick AND >= {BONUS_THRESHOLD} reconstructed 30d upgrades): {len(flips)}")
    for a in flips:
        print(f"   {a['date']} {a['ticker']} score {a['ep_score']:.1f} -> "
              f"{a['ep_score'] + a['bonus_pts']:.1f} (thr {a['threshold']:.0f})")

    ph_elig = [p for p in phantom if (p.get("recon_faithful") or 0) >= BONUS_THRESHOLD]
    print(f"\nPHANTOM missed-alert band (graded ticks, no alert, best score in "
          f"[42.8, 50)): {len(phantom)} candidate days; with >= {BONUS_THRESHOLD} "
          f"reconstructed 30d upgrades (a working bonus could have crossed the "
          f"50 insert bar): {len(ph_elig)}")
    for p in sorted(ph_elig, key=lambda x: x["date"]):
        print(f"   {p['date']} {p['ticker']:<6} best {p['best_score']:.1f} "
              f"recon faithful={p['recon_faithful']} strict={p['recon_strict']}")

    # ── Report: BONUS VALUE ──
    print("\n===== BONUS VALUE (Part C) =====")
    scored = [a for a in alerts.values() if a.get("recon_faithful") is not None]
    if not scored:
        print("(yahoo parts skipped — rerun without --skip-yahoo)")
        return
    for label, pred in (
        ("ALL alerts", lambda a: True),
        ("HIGH tier only", lambda a: a["tier"] == "HIGH"),
    ):
        rows = [a for a in scored if pred(a)]
        elig = [a for a in rows if a["recon_faithful"] >= BONUS_THRESHOLD]
        rest = [a for a in rows if a["recon_faithful"] < BONUS_THRESHOLD]
        print(f"\n-- {label} --")
        print(f"   bonus-eligible (recon faithful >= {BONUS_THRESHOLD}): {group_stats(elig, label)}")
        print(f"   not eligible:                                          {group_stats(rest, label)}")
        a10 = [a["fwd_10d"] for a in elig if a["fwd_10d"] is not None]
        b10 = [a["fwd_10d"] for a in rest if a["fwd_10d"] is not None]
        p = perm_test_mean_diff(a10, b10)
        if p is not None:
            print(f"   permutation p (mean fwd10 diff, 2-sided): {p:.3f}")
    print("\n-- threshold sensitivity (ALL alerts, strict semantic) --")
    for thr in (1, 2, 3):
        elig = [a for a in scored if (a["recon_strict"] or 0) >= thr]
        rest = [a for a in scored if (a["recon_strict"] or 0) < thr]
        print(f"   strict >= {thr}: eligible {group_stats(elig, '')}")
        print(f"              rest     {group_stats(rest, '')}")


if __name__ == "__main__":
    main()
