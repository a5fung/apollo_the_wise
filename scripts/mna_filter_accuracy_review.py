"""M&A filter accuracy review — recurring operator-judgment surfacer.

WHY: the M&A pin filter drops candidates entirely (HARD gate, no fallback), so
both error directions cost us:
  - over-fire  -> a real mover suppressed (ONDS +24%, SUNE +216% — the 6/14 dig)
  - under-fire -> a genuine target let through. Since #692 (2026-10-02) the filter asks
    whether the ticker is the TARGET of a SIGNED deal that fixes its price. Two streams make up
    the under-fire surface now:
      * `mna_filter_released` — every name the OLD rule would have blocked but the answer
        released, plus every name whose grader answered a deal that does not pin (buyer,
        proposal, all-stock...) — it replaced the #284 `mna_acquirer_title_skipped` stream;
      * `mna_headline_unanswered` rows that PASSED (ruling 4: the headline question got no
        answer — error, budget, the EP scan's 9:30-9:45 window, the 3-article cap — and the
        name went through unasked).
    Remaining blind spot: a target with no keyword-candidate headline and no grader answer
    (non-EP callers) leaves no row at all.

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
import json
import sys

# peak-gain that flags a suppression as a MATERIAL-MISS CANDIDATE for operator review
_MATERIAL_PEAK_PCT = 20.0


async def _fwd_rows(conn, event_type: str, ticker_expr: str, lookback_days: int,
                    summary_like: str = "%"):
    """Distinct (ticker, fire_day) for an event type (optionally narrowed by a summary LIKE),
    with forward peak high over [fire_day .. +7 cal days] vs fire-day open and low."""
    # DISTINCT ON (ticker, fire-day) — one row per ticker per ET day (#59 dedup
    # hygiene). A container restart re-fires the same audit event, and the prior
    # `DISTINCT ... , detail` kept each as a separate row (RGTI ×5 in the 6/20
    # smoke) → duplicate surfacing inflates the digest. Keep the most recent detail.
    return await conn.fetch(f"""
        WITH fires AS (
            SELECT DISTINCT ON ({ticker_expr}, (created_at AT TIME ZONE 'America/New_York')::date)
                {ticker_expr} AS ticker,
                (created_at AT TIME ZONE 'America/New_York')::date AS d,
                left(regexp_replace(detail::text, '\\s+', ' ', 'g'), 130) AS detail,
                detail::text AS detail_full
            FROM mi_audit_log
            WHERE event_type = $1
              AND created_at >= now() - ($2 || ' days')::interval
              AND summary LIKE $3
            ORDER BY {ticker_expr}, (created_at AT TIME ZONE 'America/New_York')::date, created_at DESC
        )
        SELECT f.ticker, f.d AS fire_day, f.detail, f.detail_full,
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
    """, event_type, str(lookback_days), summary_like)


def _answer(detail_full) -> str:
    """#692: the deal answer the row carries (role/status/consideration), '' for older rows.
    Released rows carry it under 'grader' and/or 'headlines'; fired rows at the top level."""
    try:
        d = json.loads(detail_full or "")
    except (TypeError, ValueError):
        return ""
    if not isinstance(d, dict):
        return ""

    def _pin(p) -> str:
        # 2026-10-03: the price reading that decided a nominated name (fired: `pin` at the top
        # level; released: `pin_release.pin`; held: `pin`).
        if not isinstance(p, dict) or not p:
            return ""
        if not p.get("readable"):
            return f"; price unreadable ({p.get('why')})"
        return (f"; {p.get('window')} range {p.get('range_pct')}% vs {p.get('threshold_pct')}% -> "
                f"{'PINNED' if p.get('pinned') else 'FREE'}")
    if d.get("role"):
        return f"{d['role']}/{d.get('status')}/{d.get('consideration')}" + _pin(d.get("pin"))
    a = d.get("answer") or {}
    if a.get("role") and d.get("pin") is not None:   # a HELD row
        return f"held {a['role']}/{a.get('status')}/{a.get('consideration')}" + _pin(d.get("pin"))
    pr = d.get("pin_release") or {}
    if pr.get("answer", {}).get("role"):
        pa = pr["answer"]
        return (f"nominated {pa['role']}/{pa.get('status')}/{pa.get('consideration')} via {pr.get('source')}"
                + _pin(pr.get("pin")))
    un = d.get("unanswered") or []
    if un and isinstance(un[0], dict):
        return f"unanswered ({un[0].get('why')}), {d.get('unanswered_n', len(un))} article(s)"
    g = d.get("grader") or {}
    if g.get("role"):
        return f"grader {g['role']}/{g.get('status')}/{g.get('consideration')}"
    hs = d.get("headlines") or []
    if hs and hs[0].get("role"):
        return f"headline {hs[0]['role']}/{hs[0].get('status')}/{hs[0].get('consideration')}"
    return ""


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
        ans = _answer(r["detail_full"])
        ans = f"  [{ans}]" if ans else ""
        print(f"  {r['ticker']:7} {str(r['fire_day']):10} {po:>8} {pl:>8}{ans}{flag}")
    if flag_material and n_material:
        print(f"\n  {n_material} suppression(s) ran >= +{_MATERIAL_PEAK_PCT:.0f}% post-fire -> "
              "operator: confirm each was a genuine M&A target, not a missed mover.")


async def main(lookback_days: int) -> int:
    from agents.market_intelligence.db import get_pool
    from agents.market_intelligence.audit_events import (
        MNA_FILTER_FIRED, MNA_FILTER_RELEASED, MNA_HEADLINE_UNANSWERED, MNA_PIN_PENDING,
    )
    pool = await get_pool()
    async with pool.acquire() as conn:
        suppressed = await _fwd_rows(
            conn, MNA_FILTER_FIRED, "split_part(summary,' via',1)", lookback_days)
        released = await _fwd_rows(
            conn, MNA_FILTER_RELEASED, "split_part(summary,':',1)", lookback_days)
        # ruling 4: the unanswered rows that PASSED (summary ends "— passed"; a BLOCKED one
        # only exists if the toggle was ON, and it already shows as a suppression).
        unanswered_passed = await _fwd_rows(
            conn, MNA_HEADLINE_UNANSWERED, "split_part(summary,':',1)", lookback_days,
            summary_like="%passed")
        # 2026-10-03: nominated names HELD because the price window could not be read. A hold
        # writes no fired row, so a name held all day (the window never became readable) is a
        # suppression this section alone can show.
        held = await _fwd_rows(
            conn, MNA_PIN_PENDING, "split_part(summary,':',1)", lookback_days)

    print(f"M&A FILTER ACCURACY REVIEW  (lookback {lookback_days}d)")
    print("Surfaces filter decisions + forward returns for OPERATOR judgment.")
    print("The agent does NOT classify FP/TP (HARD-gate rules #3/#4).")

    # Direction 1 — over-fire: suppressed names that then ran (missed movers).
    _print_section(
        "SUPPRESSED by the M&A filter (verify none were missed movers)",
        suppressed, flag_material=True)
    # Direction 2 — under-fire: names the OLD rule would have blocked that the deal question
    # RELEASED (#692) — verify none was a genuine target of a signed deal.
    _print_section(
        "RELEASED by the deal question - the old rule would have blocked, or the grader answered "
        "a deal that does not pin (verify none were real targets)",
        released, flag_material=False)
    if released:
        print("\n  operator: each RELEASED name was answered as buyer / proposal / speculation / "
              "no deal / all-stock. Confirm none was actually the target of a signed deal "
              "(would mean a price-capped name slipped through).")
    _print_section(
        "PASSED UNANSWERED - the headline question got no answer and the name went through "
        "(ruling 4; verify none were real targets)",
        unanswered_passed, flag_material=False)
    if unanswered_passed:
        print("\n  operator: these passed WITHOUT an answer (error / budget / the EP scan's "
              "9:30-9:45 window / the 3-article cap). Confirm none was the target of a signed deal.")
    _print_section(
        "HELD - deal-nominated, the price window could not be read (pre-market hold is normal; "
        "a name that stayed held past 09:35 had no readable window and never alerted)",
        held, flag_material=True)
    if held:
        print("\n  operator: a hold is not a verdict. A name here with a fired or released row later "
              "the same day was decided at the open; one with neither was held all day — check "
              "why its window stayed unreadable (bars / fetch).")
    print("\nSSoT: docs/setups/magna53_ep.md (M&A filter change log).")
    return 0


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 35
    sys.exit(asyncio.run(main(days)))
