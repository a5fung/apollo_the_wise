"""
mi_ep_missed_outcomes — opportunity-cost telemetry for EPs the system saw but
did NOT enter (filtered, cooldown-blocked, MODERATE-tier, or HIGH-but-unfilled).

Three sources feed the table:

  1. `scan_filter` — rows in mi_ep_scan_log with a non-null filter_reason and
     no corresponding trade in mi_live_trades / mi_paper_trades.
  2. `moderate_alert` — mi_ep_alerts rows with score_tier='MODERATE' that
     never became a trade (no entry — MODERATEs only surface in morning briefing).
  3. `high_unentered` — mi_ep_alerts rows with score_tier='HIGH' that never
     became a trade (HIGH outside ORB window, stop_too_wide, infra failure).

Forward returns measured from open[alert_date] (the gap day open — what a
day-2 chaser would've paid) to close[d+N] and max(high[d0..dN]). Stored:

  - ret_1d / ret_5d / ret_20d  (close return)
  - max_high_5d / max_high_20d (max favorable excursion)

Refresh: nightly, sliding 30-day window. Old rows freeze in place once the
20d return is settled.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from agents.market_intelligence.db import get_pool

logger = logging.getLogger(__name__)

_REFRESH_WINDOW_DAYS = 30  # how far back nightly refresh recomputes returns
_MAX_FORWARD_DAYS = 25     # SQL LATERAL needs to look ≥20 trading days ahead


# ── Skip-reason → category normalizer ────────────────────────────────────────

def _categorize_skip_reason(source: str, raw: Optional[str]) -> str:
    """Bucket the free-form reason into a stable category for grouping."""
    if source == "moderate_alert":
        return "moderate_tier"
    if source == "high_unentered":
        return "high_unentered"
    # scan_filter — parse the free-form filter_reason
    if not raw:
        return "filter_other"
    s = raw.lower()
    if "cooldown" in s:
        return "cooldown"
    if "m&a" in s or "buyout" in s or "merger" in s:
        return "ma_filter"
    if "already scored" in s or "duplicate" in s:
        return "duplicate_scan"
    if "outside top-20" in s or "top-20 gap cap" in s:
        return "outside_top20"
    if "score" in s and "< 50" in s:
        return "score_below_50"
    if "pm_rvol" in s or "pre-market rvol" in s or "pre-mkt volume" in s:
        return "pm_rvol_low"
    if "session_rvol" in s or "session rvol" in s:
        return "session_rvol_low"
    if "adv" in s:
        return "adv_low"
    if "atr" in s:
        return "atr_high"
    if "mcap" in s or "market cap" in s:
        return "mcap_low"
    if "catalyst" in s and ("downgrade" in s or "routine" in s):
        return "catalyst_downgrade"
    if "extension" in s or "extended" in s:
        return "extension_gate"
    return "filter_other"


# ── Schema init ──────────────────────────────────────────────────────────────

async def ensure_missed_outcomes_schema() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_ep_missed_outcomes (
                id SERIAL PRIMARY KEY,
                ticker TEXT NOT NULL,
                alert_date DATE NOT NULL,
                source TEXT NOT NULL,
                skip_reason TEXT,
                skip_category TEXT NOT NULL,
                ep_score FLOAT,
                gap_pct FLOAT,
                rel_volume FLOAT,
                catalyst_quality TEXT,
                open_d0 FLOAT,
                close_d0 FLOAT,
                ret_1d FLOAT,
                ret_5d FLOAT,
                ret_20d FLOAT,
                max_high_5d FLOAT,
                max_high_20d FLOAT,
                last_refreshed_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (ticker, alert_date, source)
            );
            CREATE INDEX IF NOT EXISTS idx_missed_outcomes_alert_date
                ON mi_ep_missed_outcomes(alert_date DESC);
            CREATE INDEX IF NOT EXISTS idx_missed_outcomes_category
                ON mi_ep_missed_outcomes(skip_category, alert_date DESC);
        """)


# ── Refresh / backfill ───────────────────────────────────────────────────────

async def refresh_missed_outcomes(
    window_days: int = _REFRESH_WINDOW_DAYS,
    *,
    end_date: Optional[date] = None,
) -> dict:
    """Rebuild mi_ep_missed_outcomes for the last `window_days` from source tables.

    Idempotent — UPSERTs on (ticker, alert_date, source). Forward returns
    recompute on every refresh so newly-settled bars (alert_date+5, +20)
    flow into the row that was first written when the alert fired.

    Returns counts per source for the nightly audit event.
    """
    await ensure_missed_outcomes_schema()

    end = end_date or date.today()
    start = end - timedelta(days=window_days)

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Single SQL: build the base set from 3 sources, exclude actual trades,
        # then LEFT JOIN forward-return windows from mi_daily_closes.
        # UPSERT on (ticker, alert_date, source).
        await conn.execute("""
        WITH traded AS (
            SELECT ticker, alert_date FROM mi_live_trades
            WHERE alert_date >= $1 AND alert_date <= $2
            UNION
            SELECT ticker, alert_date FROM mi_paper_trades
            WHERE alert_date >= $1 AND alert_date <= $2
        ),
        scan_filtered AS (
            -- mi_ep_scan_log has no UNIQUE constraint — same ticker can be
            -- logged multiple times per day (each 5-min scan tick). Take
            -- the latest row per (ticker, scan_date) so ON CONFLICT doesn't
            -- trip on duplicate proposed inserts.
            SELECT DISTINCT ON (s.ticker, s.scan_date)
                s.ticker,
                s.scan_date AS alert_date,
                'scan_filter'::TEXT AS source,
                s.filter_reason AS skip_reason,
                s.ep_score,
                s.gap_pct,
                s.rel_volume,
                s.catalyst_quality
            FROM mi_ep_scan_log s
            WHERE s.scan_date >= $1 AND s.scan_date <= $2
              AND s.filter_reason IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM traded t
                  WHERE t.ticker = s.ticker AND t.alert_date = s.scan_date
              )
            ORDER BY s.ticker, s.scan_date, s.created_at DESC
        ),
        moderate AS (
            SELECT DISTINCT ON (a.ticker, a.alert_date)
                a.ticker,
                a.alert_date,
                'moderate_alert'::TEXT AS source,
                NULL::TEXT AS skip_reason,
                a.ep_score,
                a.gap_pct,
                NULL::FLOAT AS rel_volume,
                a.catalyst_quality
            FROM mi_ep_alerts a
            WHERE a.alert_date >= $1 AND a.alert_date <= $2
              AND a.score_tier = 'MODERATE'
              AND NOT EXISTS (
                  SELECT 1 FROM traded t
                  WHERE t.ticker = a.ticker AND t.alert_date = a.alert_date
              )
            ORDER BY a.ticker, a.alert_date, a.created_at DESC
        ),
        high_unentered AS (
            SELECT DISTINCT ON (a.ticker, a.alert_date)
                a.ticker,
                a.alert_date,
                'high_unentered'::TEXT AS source,
                NULL::TEXT AS skip_reason,
                a.ep_score,
                a.gap_pct,
                NULL::FLOAT AS rel_volume,
                a.catalyst_quality
            FROM mi_ep_alerts a
            WHERE a.alert_date >= $1 AND a.alert_date <= $2
              AND a.score_tier = 'HIGH'
              AND NOT EXISTS (
                  SELECT 1 FROM traded t
                  WHERE t.ticker = a.ticker AND t.alert_date = a.alert_date
              )
            ORDER BY a.ticker, a.alert_date, a.created_at DESC
        ),
        base AS (
            SELECT * FROM scan_filtered
            UNION ALL SELECT * FROM moderate
            UNION ALL SELECT * FROM high_unentered
        ),
        with_returns AS (
            SELECT
                b.*,
                d0.open_price AS open_d0,
                d0.close AS close_d0,
                d1.close AS close_d1,
                d5.close AS close_d5,
                d20.close AS close_d20,
                h5.h AS max_high_5d,
                h20.h AS max_high_20d
            FROM base b
            LEFT JOIN LATERAL (
                SELECT open_price, close FROM mi_daily_closes
                WHERE ticker = b.ticker AND trade_date = b.alert_date
            ) d0 ON TRUE
            LEFT JOIN LATERAL (
                SELECT close FROM mi_daily_closes
                WHERE ticker = b.ticker AND trade_date > b.alert_date
                ORDER BY trade_date ASC LIMIT 1
            ) d1 ON TRUE
            LEFT JOIN LATERAL (
                SELECT close FROM mi_daily_closes
                WHERE ticker = b.ticker AND trade_date > b.alert_date
                ORDER BY trade_date ASC OFFSET 4 LIMIT 1
            ) d5 ON TRUE
            LEFT JOIN LATERAL (
                SELECT close FROM mi_daily_closes
                WHERE ticker = b.ticker AND trade_date > b.alert_date
                ORDER BY trade_date ASC OFFSET 19 LIMIT 1
            ) d20 ON TRUE
            LEFT JOIN LATERAL (
                SELECT MAX(high_price) AS h FROM (
                    SELECT high_price FROM mi_daily_closes
                    WHERE ticker = b.ticker AND trade_date >= b.alert_date
                    ORDER BY trade_date ASC LIMIT 6
                ) x
            ) h5 ON TRUE
            LEFT JOIN LATERAL (
                SELECT MAX(high_price) AS h FROM (
                    SELECT high_price FROM mi_daily_closes
                    WHERE ticker = b.ticker AND trade_date >= b.alert_date
                    ORDER BY trade_date ASC LIMIT 21
                ) x
            ) h20 ON TRUE
        )
        INSERT INTO mi_ep_missed_outcomes (
            ticker, alert_date, source, skip_reason, skip_category,
            ep_score, gap_pct, rel_volume, catalyst_quality,
            open_d0, close_d0,
            ret_1d, ret_5d, ret_20d, max_high_5d, max_high_20d,
            last_refreshed_at
        )
        SELECT
            ticker, alert_date, source, skip_reason,
            -- skip_category derived in Python? No — keep DB-side for simplicity.
            -- Mirror _categorize_skip_reason mappings in SQL CASE.
            CASE
                WHEN source = 'moderate_alert' THEN 'moderate_tier'
                WHEN source = 'high_unentered' THEN 'high_unentered'
                WHEN skip_reason IS NULL THEN 'filter_other'
                WHEN skip_reason ILIKE '%cooldown%' THEN 'cooldown'
                WHEN skip_reason ILIKE '%m&a%'
                  OR skip_reason ILIKE '%buyout%'
                  OR skip_reason ILIKE '%merger%' THEN 'ma_filter'
                WHEN skip_reason ILIKE '%already scored%'
                  OR skip_reason ILIKE '%duplicate%' THEN 'duplicate_scan'
                WHEN skip_reason ILIKE '%outside top-20%'
                  OR skip_reason ILIKE '%top-20 gap cap%' THEN 'outside_top20'
                WHEN skip_reason ILIKE '%score%' AND skip_reason ILIKE '%< 50%' THEN 'score_below_50'
                -- Volume gates: cover both legacy free-form ("low rel volume
                -- 0.4x < 2.0x") and the new RVOL@T bounded prefixes. The
                -- legacy strings are dominant in scan_log before the 2026-05-06
                -- unification — bucket them together as session_rvol_low since
                -- 2.0x is the session-anchor threshold.
                WHEN skip_reason ILIKE '%pm_rvol%'
                  OR skip_reason ILIKE '%pre-market rvol%'
                  OR skip_reason ILIKE '%pre-mkt volume%'
                  OR skip_reason ILIKE '%pm volume%' THEN 'pm_rvol_low'
                WHEN skip_reason ILIKE '%session_rvol%'
                  OR skip_reason ILIKE '%session rvol%'
                  OR skip_reason ILIKE '%rel volume%'
                  OR skip_reason ILIKE '%rel_vol%'
                  OR skip_reason ILIKE '%low volume%'
                  OR skip_reason ILIKE '%projected%' THEN 'session_rvol_low'
                WHEN skip_reason ILIKE '%adv%' THEN 'adv_low'
                WHEN skip_reason ILIKE '%atr%' THEN 'atr_high'
                WHEN skip_reason ILIKE '%mcap%'
                  OR skip_reason ILIKE '%market cap%' THEN 'mcap_low'
                WHEN skip_reason ILIKE '%catalyst%'
                  AND (skip_reason ILIKE '%downgrade%'
                       OR skip_reason ILIKE '%routine%') THEN 'catalyst_downgrade'
                WHEN skip_reason ILIKE '%extension%'
                  OR skip_reason ILIKE '%extended%' THEN 'extension_gate'
                ELSE 'filter_other'
            END AS skip_category,
            ep_score, gap_pct, rel_volume, catalyst_quality,
            open_d0, close_d0,
            -- Return basis: open_d0 (gap day open) — what a day-2 chaser pays.
            CASE WHEN open_d0 > 0 AND close_d1 IS NOT NULL
                 THEN (close_d1 - open_d0) / open_d0 ELSE NULL END AS ret_1d,
            CASE WHEN open_d0 > 0 AND close_d5 IS NOT NULL
                 THEN (close_d5 - open_d0) / open_d0 ELSE NULL END AS ret_5d,
            CASE WHEN open_d0 > 0 AND close_d20 IS NOT NULL
                 THEN (close_d20 - open_d0) / open_d0 ELSE NULL END AS ret_20d,
            CASE WHEN open_d0 > 0 AND max_high_5d IS NOT NULL
                 THEN (max_high_5d - open_d0) / open_d0 ELSE NULL END AS max_high_5d,
            CASE WHEN open_d0 > 0 AND max_high_20d IS NOT NULL
                 THEN (max_high_20d - open_d0) / open_d0 ELSE NULL END AS max_high_20d,
            NOW() AS last_refreshed_at
        FROM with_returns
        ON CONFLICT (ticker, alert_date, source) DO UPDATE SET
            skip_reason       = EXCLUDED.skip_reason,
            skip_category     = EXCLUDED.skip_category,
            ep_score          = EXCLUDED.ep_score,
            gap_pct           = EXCLUDED.gap_pct,
            rel_volume        = EXCLUDED.rel_volume,
            catalyst_quality  = EXCLUDED.catalyst_quality,
            open_d0           = EXCLUDED.open_d0,
            close_d0          = EXCLUDED.close_d0,
            ret_1d            = EXCLUDED.ret_1d,
            ret_5d            = EXCLUDED.ret_5d,
            ret_20d           = EXCLUDED.ret_20d,
            max_high_5d       = EXCLUDED.max_high_5d,
            max_high_20d      = EXCLUDED.max_high_20d,
            last_refreshed_at = NOW()
        """, start, end)

        # Counts per source for the audit event
        counts = await conn.fetch("""
            SELECT source, COUNT(*)::INT AS n
            FROM mi_ep_missed_outcomes
            WHERE alert_date >= $1 AND alert_date <= $2
            GROUP BY source
        """, start, end)

    summary = {r["source"]: r["n"] for r in counts}
    summary["window_start"] = start.isoformat()
    summary["window_end"] = end.isoformat()
    logger.info(f"refresh_missed_outcomes: {summary}")
    return summary


# ── Query helpers (Telegram + weekly review) ────────────────────────────────

# Skip categories that represent CORRECTLY filtered names (size / illiquidity
# / structural M&A noise / volatility too high / already extended). These
# rejections say "not in our trade universe" — they didn't bleed tradeable
# opportunity, they did their job. Hidden from /missed by default; visible
# via `/missed all`.
_UNTRADEABLE_CATEGORIES = (
    "mcap_low",        # market cap below floor
    "adv_low",         # avg dollar volume below floor
    "ma_filter",       # M&A target / deal-pinned shell
    "atr_high",        # volatility above tradeable threshold
    "extension_gate",  # price already extended (parabolic-shape rejection)
)

# Conceptual taxonomy of skip kinds — surfaced in /missed section headers so
# the user can tell at a glance whether a bucket is a "genuine miss" vs a
# "signal-weak skip" vs a "scored-but-not-entered" case. Structural kinds
# are excluded from default view anyway (see _UNTRADEABLE_CATEGORIES) but
# kept here for documentation parity.
_CATEGORY_KIND: dict[str, str] = {
    # Structural — system correctly said "not our universe"
    "mcap_low":           "structural",
    "adv_low":            "structural",
    "ma_filter":           "structural",
    "atr_high":            "structural",
    "extension_gate":      "structural",
    # Operational — budget / housekeeping; would've been evaluated otherwise
    "outside_top20":       "operational",
    "cooldown":            "operational",
    "duplicate_scan":      "operational",
    "score_below_50":      "operational",
    # Signal — trade-time conditions said "no follow-through"
    "pm_rvol_low":         "signal",
    "session_rvol_low":    "signal",
    "catalyst_downgrade":  "signal",
    # Scored-and-passed-to-user but not entered
    "moderate_tier":       "tier",
    "high_unentered":      "tier",
    # Unknown
    "filter_other":        "other",
}

_KIND_LABELS: dict[str, str] = {
    "operational": "operational miss",
    "signal":      "weak signal",
    "tier":        "scored, not entered",
    "structural":  "structurally filtered",
    "other":       "uncategorized",
}

# Open-price floor for the default view. Apollo's strategies don't trade
# sub-$5 names; surfacing penny-stock rockets just creates noise.
_DEFAULT_PRICE_FLOOR = 5.0


async def top_missed_winners(
    window_days: int = 30,
    horizon: str = "5d",
    per_category: int = 3,
    include_untradeable: bool = False,
) -> list[dict]:
    """Top N misses per skip category — guarantees each bucket shows up.

    Why per-category instead of global top-N: global sort by 5d return is
    dominated by small-cap rockets (AKAN/XNDU/POEL +200%+), drowning out
    actionable misses like HIMX/BAND (+30-40% in the user's actual trade
    universe). Per-category surfaces the top miss within each skip reason
    so methodology-tuning context is preserved across the whole output.

    Default view excludes correctly-filtered categories (mcap_low / adv_low /
    ma_filter) and rows whose gap-day open was < $5 (Apollo doesn't trade
    sub-$5). Pass `include_untradeable=True` (or `/missed all`) to see them.
    """
    col = {"1d": "ret_1d", "5d": "ret_5d", "20d": "ret_20d"}.get(horizon, "ret_5d")
    max_col = "max_high_5d" if horizon != "20d" else "max_high_20d"
    untradeable_clause = "" if include_untradeable else (
        f"AND m.skip_category NOT IN {_UNTRADEABLE_CATEGORIES} "
        f"AND COALESCE(m.open_d0, 0) >= {_DEFAULT_PRICE_FLOOR} "
    )
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            WITH base AS (
                SELECT ticker, alert_date, source, skip_reason, skip_category,
                       ep_score, gap_pct, catalyst_quality, open_d0,
                       ret_1d, ret_5d, ret_20d, max_high_5d, max_high_20d,
                       ROW_NUMBER() OVER (
                           PARTITION BY skip_category
                           ORDER BY COALESCE({col}, {max_col}) DESC NULLS LAST,
                                    {max_col} DESC NULLS LAST
                       ) AS rn,
                       MAX(COALESCE({col}, {max_col})) OVER (
                           PARTITION BY skip_category
                       ) AS cat_rank_metric
                FROM mi_ep_missed_outcomes m
                WHERE m.alert_date >= CURRENT_DATE - $1::INT
                  AND ({col} IS NOT NULL OR {max_col} IS NOT NULL)
                  -- Suppress duplicate_scan rows when a non-duplicate sibling
                  -- exists for the same ticker+date — the dedup path records
                  -- ep_score=NULL by design (the alert already scored on an
                  -- earlier scan tick); surfacing it alongside the real
                  -- moderate_alert / high_unentered row is redundant noise.
                  -- Stand-alone duplicate_scan rows (no sibling) still surface
                  -- so legitimately suppressed-only cases remain visible.
                  AND NOT (
                      m.skip_category = 'duplicate_scan'
                      AND EXISTS (
                          SELECT 1 FROM mi_ep_missed_outcomes sib
                          WHERE sib.ticker = m.ticker
                            AND sib.alert_date = m.alert_date
                            AND sib.skip_category <> 'duplicate_scan'
                      )
                  )
                  {untradeable_clause}
            )
            SELECT * FROM base
            WHERE rn <= $2
            ORDER BY cat_rank_metric DESC NULLS LAST,
                     skip_category,
                     rn
        """, window_days, per_category)
    return [dict(r) for r in rows]


async def missed_by_category(window_days: int = 30) -> list[dict]:
    """Per-category roll-up: count, avg/top of ret_5d AND max_high_5d.

    Both metrics returned because ret_5d (close[alert+5d] / open[alert] - 1)
    is NULL for any alert < 5 trading days old — Postgres returns NULL when
    the future close doesn't exist yet, so a 7-day window produces all-NULL
    ret_5d aggregates. max_high_5d uses LIMIT 6 on existing bars; partial
    windows still produce a value. Surface BOTH so the weekly digest is
    actionable on recent alerts (#109).

    Ranking uses COALESCE(ret_5d, max_high_5d) so the top ticker is
    meaningful even when ret_5d hasn't matured.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            WITH base AS (
                SELECT skip_category, ticker, alert_date,
                       ret_5d, max_high_5d
                FROM mi_ep_missed_outcomes m
                WHERE alert_date >= CURRENT_DATE - $1::INT
                  -- Suppress redundant duplicate_scan sibling rows; see
                  -- top_missed_winners for full rationale.
                  AND NOT (
                      m.skip_category = 'duplicate_scan'
                      AND EXISTS (
                          SELECT 1 FROM mi_ep_missed_outcomes sib
                          WHERE sib.ticker = m.ticker
                            AND sib.alert_date = m.alert_date
                            AND sib.skip_category <> 'duplicate_scan'
                      )
                  )
            ),
            ranked AS (
                SELECT skip_category, ticker, alert_date, ret_5d, max_high_5d,
                       ROW_NUMBER() OVER (
                           PARTITION BY skip_category
                           ORDER BY COALESCE(ret_5d, max_high_5d) DESC NULLS LAST
                       ) AS rn
                FROM base
            )
            SELECT
                b.skip_category,
                COUNT(*)::INT AS n,
                COUNT(*) FILTER (WHERE b.ret_5d > 0)::INT AS n_winners,
                COUNT(*) FILTER (WHERE b.ret_5d > 0.10)::INT AS n_10pct_plus,
                COUNT(*) FILTER (WHERE b.ret_5d > 0.20)::INT AS n_20pct_plus,
                COUNT(*) FILTER (WHERE b.max_high_5d > 0.10)::INT AS n_peak_10pct_plus,
                AVG(b.ret_5d) AS avg_ret_5d,
                MAX(b.ret_5d) AS max_ret_5d,
                AVG(b.max_high_5d) AS avg_max_high_5d,
                MAX(r.ticker) FILTER (WHERE r.rn = 1) AS top_ticker,
                MAX(r.ret_5d) FILTER (WHERE r.rn = 1) AS top_ret_5d,
                MAX(r.max_high_5d) FILTER (WHERE r.rn = 1) AS top_max_high_5d
            FROM base b
            LEFT JOIN ranked r
              ON r.skip_category = b.skip_category AND r.rn = 1
            GROUP BY b.skip_category
            ORDER BY n_peak_10pct_plus DESC, avg_max_high_5d DESC NULLS LAST
        """, window_days)
    return [dict(r) for r in rows]


async def aggregate_missed_for_weekly(window_days: int = 7) -> dict:
    """Weekly review input: top winners + per-category roll-up."""
    top = await top_missed_winners(
        window_days=window_days, horizon="5d", per_category=2,
    )
    cats = await missed_by_category(window_days=window_days)
    return {
        "window_days": window_days,
        "top_winners": top,
        "by_category": cats,
    }


# ── Telegram formatting ──────────────────────────────────────────────────────

# Human-readable labels for each skip_category. Keep them short enough to
# fit on one mobile line alongside count + numbers (≤ 28 chars).
_CATEGORY_LABELS: dict[str, str] = {
    "cooldown":           "60-day cooldown",
    "ma_filter":          "M&A / buyout (no momentum)",
    "score_below_50":     "Score below 50",
    "pm_rvol_low":        "Pre-mkt volume light",
    "session_rvol_low":   "Volume below 2× (post-open)",
    "adv_low":            "Avg volume too low",
    "atr_high":           "Volatility too high",
    "mcap_low":           "Market cap too small",
    "catalyst_downgrade": "Catalyst downgraded",
    "extension_gate":     "Already extended",
    "outside_top20":      "Outside top-20 gap rank",
    "duplicate_scan":     "Already scored today",
    "filter_other":       "Other filter",
    "moderate_tier":      "MODERATE — not entered",
    "high_unentered":     "HIGH — no fill",
}


def _humanize_category(cat: Optional[str]) -> str:
    if not cat:
        return "Other"
    return _CATEGORY_LABELS.get(cat, cat.replace("_", " ").capitalize())


def _fmt_pct(v: Optional[float], digits: int = 1, sign: bool = True) -> str:
    if v is None:
        return "—"
    fmt = f"{{:+.{digits}f}}%" if sign else f"{{:.{digits}f}}%"
    return fmt.format(v * 100)


def _fmt_pct_fixed(v: Optional[float], width: int = 5) -> str:
    """Right-padded percent for monospace column alignment. '   —' if NULL."""
    if v is None:
        return "—".rjust(width)
    s = f"{v*100:+.0f}%"
    return s.rjust(width)


def format_missed_telegram(
    rows: list[dict],
    horizon: str,
    window_days: int,
    *,
    include_untradeable: bool = False,
) -> str:
    """`/missed [days]` output — top winners grouped by skip reason.

    Columns: ticker · date · 5d close · 5d max · 20d close · 20d max.
    - "close" = return from gap-day open to close[alert+N], measured EOD.
    - "max"   = max intraday excursion over the same window (gap-day open
                base, max(high) over alert..alert+N).
    - Either may be "—" if the horizon window hasn't elapsed yet; we still
      show the row because the max-excursion column gives a running peak.
    """
    if not rows:
        if not include_untradeable:
            return (
                f"🔍 *Missed EPs (last {window_days}d)* — no tradeable misses found.\n"
                f"_Try `/missed all` to include sub-$5 / mcap_low / adv_low rows._"
            )
        return f"🔍 *Missed EPs (last {window_days}d)* — no data yet."

    from collections import OrderedDict
    grouped: "OrderedDict[str, list[dict]]" = OrderedDict()
    for r in rows:
        grouped.setdefault(r.get("skip_category") or "filter_other", []).append(r)

    horizon_label = {"1d": "1-day", "5d": "5-day", "20d": "20-day"}.get(horizon, "5-day")
    scope_note = "all alerts" if include_untradeable else "tradeable only ≥$5"
    parts = [
        f"🔍 *Missed EPs — top per skip reason (last {window_days}d)*",
        f"_Ranked by {horizon_label} return from gap-day open · {scope_note}_",
        "_close = EOD return · max = peak intraday excursion_",
        "",
    ]

    for cat, items in grouped.items():
        kind_label = _KIND_LABELS.get(_CATEGORY_KIND.get(cat, "other"), "")
        kind_suffix = f" — _{kind_label}_" if kind_label else ""
        parts.append(f"*{_humanize_category(cat)}*{kind_suffix} ({len(items)})")
        parts.append("```")
        parts.append("           5d           20d")
        parts.append("tckr  date  close  max   close  max")
        for r in items:
            tk = r["ticker"][:5].ljust(5)
            d = r["alert_date"].strftime("%m/%d") if r.get("alert_date") else "  —  "
            c5 = _fmt_pct_fixed(r.get("ret_5d"))
            m5 = _fmt_pct_fixed(r.get("max_high_5d"))
            c20 = _fmt_pct_fixed(r.get("ret_20d"))
            m20 = _fmt_pct_fixed(r.get("max_high_20d"))
            parts.append(f"{tk} {d}  {c5} {m5}   {c20} {m20}")
        parts.append("```")
    return "\n".join(parts)


def format_missed_section_for_weekly(missed: dict) -> str:
    """Weekly review appendix: top 5 winners + per-category roll-up.

    Same grouping/monospace shape as `/missed` so the visual rhythm is
    consistent across the two surfaces (digest is just shorter).
    """
    top = missed.get("top_winners") or []
    cats = missed.get("by_category") or []
    if not top and not cats:
        return ""
    window_days = missed.get("window_days", 7)
    parts = [f"🔍 *Missed Opportunities ({window_days}d):*"]

    if top:
        parts.append("")
        parts.append("_Top winners we didn't enter:_")
        parts.append("```")
        for r in top[:5]:
            tk = r["ticker"][:5].ljust(5)
            d = r["alert_date"].strftime("%m/%d") if r.get("alert_date") else "  —  "
            ret_s = _fmt_pct_fixed(r.get("ret_5d"))
            max_s = _fmt_pct_fixed(r.get("max_high_5d"))
            cat = _humanize_category(r.get("skip_category"))[:22].ljust(22)
            parts.append(f"{tk} {d}  5d {ret_s}  max {max_s}  {cat}")
        parts.append("```")

    if cats:
        parts.append("")
        parts.append("_By skip reason (peak = max intraday high over 5 days):_")
        parts.append("```")
        parts.append("reason                  n  peak-avg  ≥10%  top")
        for c in cats[:6]:
            n = c.get("n") or 0
            # Prefer peak metrics — ret_5d is NULL for alerts <5 trading days
            # old (close[+5d] doesn't exist yet), so at 7d window almost
            # everything aggregates to NULL. max_high_5d uses LIMIT 6 on
            # existing bars, populates faster (#109).
            peak_avg = _fmt_pct_fixed(c.get("avg_max_high_5d"))
            n10 = c.get("n_peak_10pct_plus") or 0
            top_t = (c.get("top_ticker") or "—")[:5]
            top_v = _fmt_pct_fixed(
                c.get("top_max_high_5d") or c.get("top_ret_5d")
            )
            label = _humanize_category(c.get("skip_category"))[:22].ljust(22)
            parts.append(f"{label}  {n:>3}  {peak_avg}     {n10:>3}   {top_t} {top_v}")
        parts.append("```")
        return "\n".join(parts)
    return "\n".join(parts)


