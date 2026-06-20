"""M&A filter accuracy review — recurring operator-judgment surfacer.

WHY: the M&A pin filter drops candidates entirely (HARD gate, no fallback), so
both error directions cost us:
  - over-fire  -> a real mover suppressed (ONDS +24%, SUNE +216% — the 6/14 dig)
  - under-fire -> a genuine target let through as "acquirer-side" (the #284
    acquirer-direction change could mis-pass a target)

This script SURFACES both, with forward returns, for OPERATOR judgment. It does
NOT classify FP/TP itself (CHANGE_PROCESS rules #3/#4 — the agent never
self-certifies the filter list). Productizes the 6/14 materiality dig into a
repeatable review.

CADENCE: registered in data_gated_reviews.yaml (`mna_filter_accuracy_review`),
surfaced by the Sunday weekly review when its floor ripens (monthly during the
#284 validation window, relax to quarterly once stable). Run on the box:
    docker exec apollo-market python -m scripts.mna_filter_accuracy_review [days]

Read-only. ASCII output (cp1252 console safety).
"""
import asyncio
import sys

# peak-gain that flags a suppression as a MATERIAL-MISS CANDIDATE for operator review
_MATERIAL_PEAK_PCT = 20.0


async def _fwd_rows(conn, event_type: str, ticker_expr: str, lookback_days: int):
    """Distinct (ticker, fire_day) for an event type, with forward peak high
    over [fire_day .. +7 cal days] vs fire-day open and low."""
    # DISTINCT ON (ticker, fire-day) — one row per ticker per ET day (#59 dedup
    # hygiene). A container restart re-fires the same audit event, and the prior
    # `DISTINCT ... , detail` kept each as a separate row (RGTI ×5 in the 6/20
    # smoke) → duplicate surfacing inflates the digest. Keep the most recent detail.
    return await conn.fetch(f"""
        WITH fires AS (
            SELECT DISTINCT ON ({ticker_expr}, (created_at AT TIME ZONE 'America/New_York')::date)
                {ticker_expr} AS ticker,
                (created_at AT TIME ZONE 'America/New_York')::date AS d,
                left(regexp_replace(detail::text, '\\s+', ' ', 'g'), 130) AS detail
            FROM mi_audit_log
            WHERE event_type = $1
              AND created_at >= now() - ($2 || ' days')::interval
            ORDER BY {ticker_expr}, (created_at AT TIME ZONE 'America/New_York')::date, created_at DESC
        )
        SELECT f.ticker, f.d AS fire_day, f.detail,
               c0.open_price, c0.low_price, w.peak_high,
               round((((w.peak_high / NULLIF(c0.open_price,0)) - 1) * 100)::numeric, 1) AS pk_vs_open,
               round((((w.peak_high / NULLIF(c0.low_price,0))  - 1) * 100)::numeric, 1) AS pk_vs_low
        FROM fires f
        LEFT JOIN mi_daily_closes c0 ON c0.ticker = f.ticker AND c0.trade_date = f.d
        LEFT JOIN LATERAL (
            SELECT max(high_price) AS peak_high
            FROM mi_daily_closes c1
            WHERE c1.ticker = f.ticker AND c1.trade_date >= f.d AND c1.trade_date <= f.d + 7
        ) w ON true
        ORDER BY pk_vs_open DESC NULLS LAST
    """, event_type, str(lookback_days))


def _print_section(title: str, rows, flag_material: bool):
    print(f"\n=== {title} (n={len(rows)}) ===")
    if not rows:
        print("  (none)")
        return
    print(f"  {'ticker':7} {'fire_day':10} {'vs_open':>8} {'vs_low':>8}  note")
    n_material = 0
    for r in rows:
        pk_open = r["pk_vs_open"]
        flag = ""
        if flag_material and pk_open is not None and pk_open >= _MATERIAL_PEAK_PCT:
            flag = "  <-- MATERIAL-MISS CANDIDATE (verify FP)"
            n_material += 1
        po = f"{pk_open:+.1f}%" if pk_open is not None else "   n/a"
        pl = f"{r['pk_vs_low']:+.1f}%" if r["pk_vs_low"] is not None else "   n/a"
        print(f"  {r['ticker']:7} {str(r['fire_day']):10} {po:>8} {pl:>8}{flag}")
    if flag_material and n_material:
        print(f"\n  {n_material} suppression(s) ran >= +{_MATERIAL_PEAK_PCT:.0f}% post-fire -> "
              "operator: confirm each was a genuine M&A target, not a missed mover.")


async def main(lookback_days: int) -> int:
    from agents.market_intelligence.db import get_pool
    from agents.market_intelligence.audit_events import (
        MNA_FILTER_FIRED, MNA_ACQUIRER_TITLE_SKIPPED,
    )
    pool = await get_pool()
    async with pool.acquire() as conn:
        suppressed = await _fwd_rows(
            conn, MNA_FILTER_FIRED, "split_part(summary,' via',1)", lookback_days)
        passed = await _fwd_rows(
            conn, MNA_ACQUIRER_TITLE_SKIPPED, "split_part(summary,' ',1)", lookback_days)

    print(f"M&A FILTER ACCURACY REVIEW  (lookback {lookback_days}d)")
    print("Surfaces filter decisions + forward returns for OPERATOR judgment.")
    print("The agent does NOT classify FP/TP (HARD-gate rules #3/#4).")

    # Direction 1 — over-fire: suppressed names that then ran (missed movers).
    _print_section(
        "SUPPRESSED by the M&A filter (verify none were missed movers)",
        suppressed, flag_material=True)
    # Direction 2 — under-fire: acquirer-passes (#284) — verify none were targets.
    _print_section(
        "PASSED as ACQUIRER-side by #284 (verify none were genuine targets)",
        passed, flag_material=False)
    if passed:
        print("\n  operator: each PASSED name is a title the #284 check read as the "
              "filing ticker BUYING. Confirm none was actually the target being bought "
              "(would mean a price-capped name slipped through).")
    print("\nSSoT: docs/setups/magna53_ep.md (M&A filter change log). "
          "Deferred bleed class: data_gated_reviews `mna_filter_direction_blindness_path_a`.")
    return 0


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 35
    sys.exit(asyncio.run(main(days)))
