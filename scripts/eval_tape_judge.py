"""#299 (1A) — TAPE-feature judge eval: with-vs-without delta surface for OPERATOR labeling.

READ-ONLY. No DB writes, no trade-state. Re-grades recent mi_ep_alerts through the holistic
judge TWICE per row — once with `tape=None` (today's behavior) and once with the point-in-time
tape dict (opening-range÷ATR, premarket vol-curve vs the name's own baseline, liquidity) — and
surfaces the rows whose verdict CHANGED, for the operator to label. The agent never self-scores
promote/demote (ADR 0011: the judge is load-bearing; the operator owns the flip gate).

WHY THIS EVAL (timing histogram, 2026-06-17, n=569 HIGH alerts 3/16–6/17):
  graded 9:35–9:44 (OR done AND ORB-tradeable) ... 79.1%   ← OR÷ATR available + decision-relevant
  graded <9:35 (OR=None at grade time) .......... 14.1%   ← only pm_vol_curve/liquidity available
  graded 9:45–9:59 (OR done, OUT-OF-ORB) ......... 5.4%
  graded >=10:00 (post-ORB) ...................... 1.4%
The opening-range feature is present for the LARGE majority of the tradeable cohort (the cluster
is the 5-min scan cadence landing at :35/:40, when the 9:30–9:34 OR is complete and the ORB
window is still open). The judge is load-bearing on ENTRY (ep_detector ~L2489 mutates score_tier
BEFORE the ORB entry), so a tape that shifts the judge verdict shifts tradeable selection.

DISCIPLINE (advisor 2026-06-17):
  • POINT-IN-TIME cut — minute bars truncated to t <= detected_at (the grade timestamp) before
    computing OR / premarket-cum-vol / liquidity-so-far. No lookahead. OR÷ATR is None pre-9:35
    BY CONSTRUCTION — that IS the tradeability segmentation, not a bolt-on.
  • tz — bar `t` is epoch-ms UTC; detected_at and the 9:30/9:35 ET cuts go through ZoneInfo(ET).
  • JUDGE NOISE FLOOR — --replicates runs the NO-TAPE judge K times to measure the judge's
    intrinsic run-to-run flip rate (adaptive thinking, no temperature → non-deterministic). A
    "tape changed the verdict" delta is only credible when the no-tape verdict was STABLE across
    the K replicates; a row whose no-tape verdict itself flips is noise-dominated, not a tape
    effect, and is reported separately.
  • SMOKE (small --limit) validates MACHINERY + feature PRESENCE rates, NOT efficacy. It cannot
    say tape helps — only the operator-labeled full run can. Keep that line bright.

CAVEAT for the operator: get_minute_volume_baseline is the CURRENT trailing baseline, not
  as-of-alert-date, so pm_vol_curve carries mild baseline lookahead (slow-moving; flag a flipped
  verdict that hinges only on it). OR÷ATR + liquidity are reconstructed strictly point-in-time.

Run (read-only, on the server — needs prod DB + Polygon minute bars):
  docker exec apollo-market python /app/scripts/eval_tape_judge.py --days 30 --limit 8 --replicates 3
  (full run, operator-triggered — costs ~ (K+1) Opus judge calls per row):
  docker exec apollo-market python /app/scripts/eval_tape_judge.py --days 95 --replicates 3
"""
import argparse
import asyncio
import os
from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from agents.market_intelligence.db import get_pool
from agents.market_intelligence.ep_grade_judge import format_tier_transition, grade_holistic
from agents.market_intelligence.tape_features import (
    build_tape, compute_liquidity_tag, compute_or_atr, compute_pm_vol_curve,
)
from scripts._judge_replay_common import REPLAY_SQL as _SQL
from scripts._judge_replay_common import (
    build_judge_payload, fetch_narratives_for, fetch_profile, resolve_grounded_text,
)

_ET = ZoneInfo("America/New_York")
PM_START_MIN = 4 * 60        # 04:00 ET — premarket cumulative anchor
SESSION_START_MIN = 9 * 60 + 30   # 09:30 ET — session open
OR_END_MIN = 9 * 60 + 35     # 09:35 ET — opening range (9:30–9:34) complete


# ── pure, unit-tested tape reconstruction (no I/O — fixtures in tests/test_tape_eval.py) ──

def _bar_et_minute(t_ms: int) -> int:
    """ET minute-of-day for a Polygon bar timestamp (epoch-ms UTC → ET wall clock)."""
    dt = datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).astimezone(_ET)
    return dt.hour * 60 + dt.minute


def slice_pit(bars: list, detected_at: datetime) -> list:
    """Minute bars (asc, {t epoch-ms, o,h,l,c,v}) truncated to t <= detected_at. The point-in-
    time cut: nothing after the grade timestamp is visible (no lookahead). detected_at is the
    tz-aware grade time; comparison is in epoch-ms so tz is irrelevant to the cut itself."""
    cut_ms = detected_at.timestamp() * 1000
    return [b for b in bars if b.get("t") is not None and b["t"] <= cut_ms]


def opening_range(bars_pit: list, detected_et_min: int):
    """(or_high, or_low) over the 9:30–9:34 ET bars, or None if the OR isn't complete at the
    grade cut (detected before 9:35 → OR not yet formed) or no bars fell in the window."""
    if detected_et_min < OR_END_MIN:
        return None
    hi = lo = None
    for b in bars_pit:
        m = _bar_et_minute(b["t"])
        if SESSION_START_MIN <= m < OR_END_MIN:
            h, l = b.get("h"), b.get("l")
            if h is not None:
                hi = h if hi is None else max(hi, h)
            if l is not None:
                lo = l if lo is None else min(lo, l)
    if hi is None or lo is None:
        return None
    return float(hi), float(lo)


def cum_volumes(bars_pit: list):
    """(premkt_cum_vol, session_cum_vol, dollar_vol_so_far) from the point-in-time bars, split
    at 9:30 ET (premarket = [04:00, 09:30); session = [09:30, cut]). Dollar volume sums v*close
    over all >=04:00 bars — the liquidity-so-far input."""
    pm = sess = 0
    dollars = 0.0
    for b in bars_pit:
        m = _bar_et_minute(b["t"])
        if m < PM_START_MIN:
            continue
        v = int(b.get("v") or 0)
        if m < SESSION_START_MIN:
            pm += v
        else:
            sess += v
        c = b.get("c")
        if c is not None:
            dollars += v * float(c)
    return pm, sess, dollars


def tradeability_bucket(detected_et_min: int) -> str:
    """Same buckets as the 6/17 timing histogram — which tape features are present + whether the
    name is still ORB-tradeable when graded."""
    if detected_et_min < SESSION_START_MIN:
        return "premarket(<9:30) OR=None"
    if detected_et_min < OR_END_MIN:
        return "OR-forming(9:30-9:34)"
    if detected_et_min < 9 * 60 + 45:
        return "OR+ORB-tradeable(9:35-9:44)"
    if detected_et_min < 10 * 60:
        return "OR,out-of-ORB(9:45-9:59)"
    return "post-ORB(>=10:00)"


# ── async reconstruction (I/O: Polygon minute bars + minute-volume baseline) ──

async def build_tape_for_row(row, prior_daily_rows):
    """(tape_dict|None, presence, bucket) — reconstruct the point-in-time tape for one alert."""
    from agents.market_intelligence.collector import get_minute_bars
    from agents.market_intelligence.minute_volume import compute_rvol_at_time

    detected = row["detected_at"]
    det_et = detected.astimezone(_ET)
    det_min = det_et.hour * 60 + det_et.minute
    d = row["alert_date"].isoformat()

    bars = await get_minute_bars(row["ticker"], d, d)
    pit = slice_pit(bars, detected)

    or_atr = None
    orr = opening_range(pit, det_min)
    if orr is not None:
        or_atr = compute_or_atr(orr[0], orr[1], prior_daily_rows)

    pm_cum, sess_cum, dollars = cum_volumes(pit)
    rvol = await compute_rvol_at_time(row["ticker"], det_et, pm_cum, sess_cum)
    pm_curve = compute_pm_vol_curve(rvol)
    liq = compute_liquidity_tag(dollar_vol=dollars or None)

    tape = build_tape(or_atr=or_atr, pm_vol_curve=pm_curve, liquidity=liq)
    presence = {
        "or_atr": or_atr is not None,
        "pm_vol_curve": pm_curve is not None,
        "liquidity": liq is not None,
    }
    return tape, presence, tradeability_bucket(det_min)


async def fetch_prior_daily(conn, ticker, alert_date, lookback=80):
    """Prior-session daily OHLC ascending (trade_date < alert_date) — the ATR-14 reference for
    OR÷ATR. STRICTLY before the alert date (ATR is a prior-day measure, never includes today)."""
    rows = await conn.fetch(
        """SELECT high_price, low_price, close FROM mi_daily_closes
           WHERE ticker = $1 AND trade_date < $2 ORDER BY trade_date DESC LIMIT $3""",
        ticker, alert_date, lookback)
    return [dict(r) for r in reversed(rows)]


async def _grade(client, sem, payload):
    async with sem:
        return await grade_holistic(client, payload, timeout=30)


async def eval_one(client, sem, conn, row, replicates: int):
    """Re-grade one row no-tape (×K replicates for the noise floor) vs with-tape (×1). Read-only.
    Returns the per-row record the delta surface + presence summary are built from."""
    ticker = row["ticker"]
    _mc, sector, company = await fetch_profile(ticker)
    grounded_text, _ = await resolve_grounded_text(row, company, grounded=False)
    prior = await fetch_prior_daily(conn, ticker, row["alert_date"])
    tape, presence, bucket = await build_tape_for_row(row, prior)

    base_payload, _ = build_judge_payload(row, grounded_text, _mc, sector, tape=None)
    tape_payload, _ = build_judge_payload(row, grounded_text, _mc, sector, tape=tape)

    # No-tape replicates (noise floor) + one with-tape, all concurrent under the shared sem.
    no_tape = await asyncio.gather(*[_grade(client, sem, base_payload) for _ in range(replicates)])
    with_tape = await _grade(client, sem, tape_payload)

    def _tier(v):
        return v["tier"] if v else None
    nt_tiers = [_tier(v) for v in no_tape]
    nt_stable = len(set(nt_tiers)) == 1 and nt_tiers[0] is not None
    nt_modal = Counter(t for t in nt_tiers if t).most_common(1)
    nt_modal = nt_modal[0][0] if nt_modal else None
    wt_tier = _tier(with_tape)

    return {
        "ticker": ticker, "alert_date": row["alert_date"], "floor": row["floor_tier"],
        "bucket": bucket, "presence": presence, "tape": tape,
        "nt_tiers": nt_tiers, "nt_stable": nt_stable, "nt_modal": nt_modal,
        "wt_tier": wt_tier, "wt_verdict": with_tape,
        "tape_changed": (nt_modal is not None and wt_tier is not None and wt_tier != nt_modal),
    }


async def main(days: int, limit: int | None, replicates: int, ticker: str | None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SQL, days)
        rows = [r for r in rows if (not ticker or r["ticker"] == ticker.upper())]
        if limit:
            rows = rows[:limit]

        print("=" * 80)
        print(f"#299 TAPE JUDGE EVAL — last {days}d, {len(rows)} row(s), "
              f"{replicates}× no-tape replicates (noise floor) + 1× with-tape")
        print("READ-ONLY · operator labels the deltas · SMOKE = machinery+presence, NOT efficacy")
        print("=" * 80)
        if not rows:
            print("  No HIGH/MODERATE alerts in window — nothing to eval.")
            return

        client = None
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=api_key)
        sem = asyncio.Semaphore(3)

        results = []
        try:
            for r in rows:  # sequential per-row (each row fans out its own K+1 judge calls)
                results.append(await eval_one(client, sem, conn, r, replicates))
        finally:
            if client is not None:
                try:
                    await client.close()
                except Exception:
                    pass

    # ── presence rates (the smoke's real product) ──
    n = len(results)
    pres = {k: sum(1 for r in results if r["presence"][k]) for k in ("or_atr", "pm_vol_curve", "liquidity")}
    print("\nFEATURE PRESENCE at grade time (point-in-time):")
    for k in ("or_atr", "pm_vol_curve", "liquidity"):
        print(f"  {k:14} present on {pres[k]:3}/{n}  ({pres[k]/n*100:4.0f}%)")
    print("\n  by tradeability bucket:")
    for b, c in sorted(Counter(r["bucket"] for r in results).items()):
        print(f"    {b:32} {c}")

    # ── judge noise floor ──
    unstable = [r for r in results if not r["nt_stable"]]
    print(f"\nJUDGE NOISE FLOOR ({replicates}× no-tape): "
          f"{n - len(unstable)}/{n} rows STABLE, {len(unstable)} flipped across replicates.")
    for r in unstable:
        print(f"    ~ {r['ticker']:6} {r['alert_date']}  no-tape tiers={r['nt_tiers']} "
              f"(noise-dominated — exclude from tape-delta read)")

    # ── tape deltas (operator-labeling surface) — only credible where no-tape was stable ──
    deltas = [r for r in results if r["tape_changed"] and r["nt_stable"]]
    noisy_deltas = [r for r in results if r["tape_changed"] and not r["nt_stable"]]
    print(f"\nTAPE DELTAS (no-tape STABLE, with-tape differs): {len(deltas)}  "
          f"[+{len(noisy_deltas)} more but noise-dominated — not credible]")
    for r in deltas:
        present = ",".join(k for k, v in r["presence"].items() if v) or "none"
        v = r["wt_verdict"] or {}
        print(f"\n  {r['ticker']:6} {r['alert_date']}  [{r['bucket']}]  features:{present}")
        print(f"     no-tape={r['nt_modal']}  →  with-tape={format_tier_transition(r['nt_modal'], r['wt_tier'])}")
        if r["tape"]:
            print(f"     tape: OR÷ATR={r['tape'].get('opening_range_atr')} "
                  f"pmvol={r['tape'].get('pm_vol_curve')} liq={r['tape'].get('liquidity')}")
        print(f"     judge: {(v.get('rationale') or '')[:240]}")

    print("\n" + "-" * 80)
    print("HARD gate (ADR 0011): the OPERATOR labels these deltas right/wrong — the agent does "
          "NOT self-certify. This is a smoke: it proves the tape flows through + how often each "
          "feature is present; it does NOT establish that tape improves grades. Full run +"
          " operator labeling decides ship.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--limit", type=int, default=8, help="cap rows (0 = no cap / full run)")
    ap.add_argument("--replicates", type=int, default=3,
                    help="no-tape judge runs for the noise floor (>=2 to measure flip rate)")
    ap.add_argument("--ticker", type=str, default=None)
    args = ap.parse_args()
    asyncio.run(main(args.days, args.limit or None, args.replicates, args.ticker))
