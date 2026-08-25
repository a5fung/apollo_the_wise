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

Refresh: nightly, sliding 30-day window (`refresh_missed_outcomes`) handles
new alerts and maturing forward returns. #583: that window ONLY ever writes
rows whose alert_date falls inside it — a row that ages out, or that a later
WHERE-clause fix (e.g. #268's `source='live'` filter) newly excludes, was
never re-touched and sat with its original classification forever (279/298
`high_unentered` rows and 19/57 `window_missed` rows were exactly this —
orphaned rows from a 2026-06-11 `historical_scan` replay batch #268 excluded
going forward but never pruned retroactively). `reconcile_missed_outcomes_categories`
is the guard: a full-history diff against the CURRENT categorisation/
inclusion logic that prunes rows the logic no longer produces, corrects rows
whose category drifted, and backfills rows a since-shipped fix should have
captured but couldn't because they'd already aged out of the window when it
shipped (the 2026-08-15 cancelled/order_failed fix's own capture hole).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from agents.market_intelligence.db import get_pool

logger = logging.getLogger(__name__)

_REFRESH_WINDOW_DAYS = 30  # how far back nightly refresh recomputes returns
_MAX_FORWARD_DAYS = 25     # SQL LATERAL needs to look ≥20 trading days ahead

# mi_live_trades statuses that mean "this row never became a trade" — no fill
# ever occurred, so the alert belongs in the DECLINED population, not the
# traded one. Single source of truth for BOTH: (1) the `traded` CTE exclusion
# below, and (2) the skip_reason LATERAL attribution in `high_unentered`.
#
#   skipped       — entry-pipeline decided not to attempt at all (block:*/
#                    window:*/setup:*/infra:* — #199).
#   cancelled     — an order WAS placed then cancelled before any fill: the
#                    chase cap (order_manager._skip_chase_capped), the 10:00 ET
#                    unfilled-ORB-window sweep, or a broker-side cancel/reject/
#                    expire surfaced via check_fills. (2026-08-15 fix — this
#                    status previously satisfied `status IS DISTINCT FROM
#                    'skipped'` and was silently counted as TRADED, so these
#                    alerts got no outcome row in EITHER population. EROC
#                    2026-08-12, setup:chase_cap_exceeded, is the case that
#                    surfaced it — see docs/roadmap/ep_profitability_program.md
#                    "STOP-GEOMETRY SWEEP" 2026-08-15.)
#   order_failed  — submission failed after the one retry (infra error) —
#                    same "never filled" class as cancelled; the chase-cap
#                    check on the retry branch (order_manager.py `_submit`
#                    exception handler) sets THIS status instead of
#                    'cancelled' for the identical chase-cap-exceeded event,
#                    so excluding one without the other would leave half of
#                    the chase-cap population still miscounted.
#
# NOTE: 'closed' is intentionally NOT here — a trade that filled (even on a
# prior entry_attempt) and was later closed (stop-out, EOD flatten, or a
# failed re-entry preserved via the 10:00 ET cleanup's exits-non-empty branch)
# is a REAL trade with REAL P&L and must stay in `traded`. 'expired' (a staged
# paper-confirmation proposal that timed out with no broker order) is also
# NOT here — that is a distinct staged-approval flow, out of scope for this
# fix (not one of the three trigger paths named above; no order was placed).
#
# Interpolated directly into the SQL below via Python tuple repr — the SAME
# f-string idiom this file already uses for _UNTRADEABLE_CATEGORIES /
# _SHOULDVE_ENTERED_CATEGORIES (see top_missed_winners / top_shouldve_entered_gaps
# below). Safe: a fixed internal constant, never external/user input.
DECLINED_NEVER_FILLED_STATUSES = ("skipped", "cancelled", "order_failed")


# ── Skip-reason → category normalizer ────────────────────────────────────────

def _categorize_skip_reason(source: str, raw: Optional[str]) -> str:
    """Bucket the free-form reason into a stable category for grouping."""
    if source == "moderate_alert":
        return "moderate_tier"
    s = (raw or "").lower()
    # #199: entry-pipeline skip attribution (block:*/window:*/setup:*) — these
    # apply to attributed high_unentered rows and scan_filter alike, so they
    # must be checked before the bare high_unentered fallthrough.
    if s.startswith("block:max_positions"):
        return "cap_blocked"
    if s.startswith("block:circuit_breaker"):
        return "breaker_blocked"
    if s.startswith("block:"):
        return "block_other"
    if s.startswith("window:"):
        return "window_missed"
    if s.startswith("setup:stop_too_wide"):
        return "stop_too_wide"
    if s.startswith("setup:faded"):
        return "faded_from_orb"
    if s.startswith("setup:account_fetch") or s.startswith("infra:"):
        return "infra_skip"
    if s.startswith("setup:"):
        return "setup_other"
    if source == "high_unentered":
        return "high_unentered"
    # scan_filter — parse the free-form filter_reason
    if not raw:
        return "filter_other"
    # #570 (2026-08-22): the two silent D-1 universe floors — checked early, ahead of the
    # generic substring chain below, so this class stays its OWN isolable category (what
    # #584's same-day liquidity re-check iterates over) instead of falling through to
    # filter_other and getting mixed with unrelated filters.
    if s.startswith("filter:universe_prev_close_too_low") or s.startswith("filter:universe_prev_day_illiquid"):
        return "d1_universe_floor"
    if "cooldown" in s:
        return "cooldown"
    if "m&a" in s or "buyout" in s or "merger" in s:
        return "ma_filter"
    if "already scored" in s or "duplicate" in s:
        return "duplicate_scan"
    if "outside top-20" in s or "top-20 gap cap" in s:
        return "outside_top20"
    # Bucket name kept stable across the #533 rescale (2026-08-22): "< 50" is
    # the legacy-side form, "< bar" the separation side's presented-scale form
    # ("score 55 < bar 65 (...)") — same class: scored but below the cutline/bar.
    if "score" in s and ("< 50" in s or "< bar" in s):
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


# #583 / #570-followup (2026-08-25): the single SQL-side skip_category mapping —
# mirrors _categorize_skip_reason above (kept DB-side for simplicity per the
# original design; NOT auto-synced with the Python function, so the two CAN
# drift — #570 shipped the d1_universe_floor branch in _categorize_skip_reason
# but never added the matching WHEN clause here, so every floor row landed in
# 'filter_other' in prod for three days (213/222 rows on 08-24) instead of the
# structural bucket that keeps it out of default /missed. Fixed here. Because a
# generated single source of truth would have to resolve pre-existing SQL-only
# substrings (pm volume / rel volume / rel_vol / low volume / projected — see
# session_rvol_low / pm_rvol_low below) that Python's version doesn't match,
# and neither narrowing SQL nor widening Python is in scope for this fix, the
# two implementations stay hand-mirrored and agreement is pinned by
# tests/test_missed_outcomes_categorizer_agreement.py instead — it fails if a
# WHEN clause is added to one side and not the other, across a named
# vocabulary (see that file for the documented exceptions). Used by BOTH
# refresh_missed_outcomes's write path and reconcile_missed_outcomes_categories's
# diff/backfill below, so the two can never classify the same skip_reason
# differently at RUNTIME — the EXACT drift class that let #583's bug hide (a
# WHERE-clause fix landed in one place, #268's `source='live'` filter, but old
# rows categorized before it never got re-checked against it).
_SKIP_CATEGORY_CASE_SQL = """
            CASE
                WHEN source = 'moderate_alert' THEN 'moderate_tier'
                -- #199: entry-pipeline skip attribution. Specific prefixes
                -- first (they apply to attributed high_unentered rows); the
                -- bare 'high_unentered' fallthrough is now only for truly
                -- unfilled HIGHs with no skip row (skip_reason IS NULL).
                WHEN skip_reason ILIKE 'block:max_positions%' THEN 'cap_blocked'
                WHEN skip_reason ILIKE 'block:circuit_breaker%' THEN 'breaker_blocked'
                WHEN skip_reason ILIKE 'block:%' THEN 'block_other'
                WHEN skip_reason ILIKE 'window:%' THEN 'window_missed'
                WHEN skip_reason ILIKE 'setup:stop_too_wide%' THEN 'stop_too_wide'
                WHEN skip_reason ILIKE 'setup:faded%' THEN 'faded_from_orb'
                WHEN skip_reason ILIKE 'setup:account_fetch%'
                  OR skip_reason ILIKE 'infra:%' THEN 'infra_skip'
                WHEN skip_reason ILIKE 'setup:%' THEN 'setup_other'
                WHEN source = 'high_unentered' THEN 'high_unentered'
                WHEN skip_reason IS NULL THEN 'filter_other'
                -- #570 follow-up (2026-08-25): the two silent D-1 universe floors —
                -- mirrors _categorize_skip_reason's d1_universe_floor branch above at
                -- the SAME ordinal (checked early, ahead of the generic substring
                -- chain) so this class stays its own isolable category instead of
                -- falling through to filter_other and swamping it (~200 rows/day).
                WHEN skip_reason ILIKE 'filter:universe_prev_close_too_low%'
                  OR skip_reason ILIKE 'filter:universe_prev_day_illiquid%' THEN 'd1_universe_floor'
                WHEN skip_reason ILIKE '%cooldown%' THEN 'cooldown'
                WHEN skip_reason ILIKE '%m&a%'
                  OR skip_reason ILIKE '%buyout%'
                  OR skip_reason ILIKE '%merger%' THEN 'ma_filter'
                WHEN skip_reason ILIKE '%already scored%'
                  OR skip_reason ILIKE '%duplicate%' THEN 'duplicate_scan'
                WHEN skip_reason ILIKE '%outside top-20%'
                  OR skip_reason ILIKE '%top-20 gap cap%' THEN 'outside_top20'
                WHEN skip_reason ILIKE '%score%' AND (skip_reason ILIKE '%< 50%'
                  OR skip_reason ILIKE '%< bar%') THEN 'score_below_50'
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
            END
"""


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

            -- #197 cap+1 slot-admission SHADOW ledger (durable, append-only).
            -- mi_ep_missed_outcomes is a 30d ROLLING window that gets rebuilt,
            -- so a cap_blocked decision would age out of it. This ledger
            -- PERSISTS every cap_blocked decision permanently so the "what would
            -- bending the max_positions rule have produced over time" record is
            -- lossless. Captures ALL qualities (policy filter applied at read
            -- time) so a future widen game_changer->strong keeps full history.
            -- Outcomes backfilled while the source row is still in-window;
            -- COALESCE preserves a settled value after roll-off.
            CREATE TABLE IF NOT EXISTS mi_cap_plus_one_shadow (
                ticker            TEXT NOT NULL,
                alert_date        DATE NOT NULL,
                ep_score          FLOAT,
                catalyst_quality  TEXT,
                ret_5d            FLOAT,
                max_high_5d       FLOAT,
                first_seen_at     TIMESTAMPTZ DEFAULT NOW(),
                outcome_updated_at TIMESTAMPTZ,
                PRIMARY KEY (ticker, alert_date)
            );
            CREATE INDEX IF NOT EXISTS idx_cap_plus_one_shadow_date
                ON mi_cap_plus_one_shadow(alert_date DESC);
        """)


# ── #197 cap+1 shadow ledger recorder ────────────────────────────────────────

async def record_cap_plus_one_shadow() -> dict:
    """Persist every `cap_blocked` decision from the rolling missed-outcomes
    window into the durable mi_cap_plus_one_shadow ledger (telemetry-only — no
    trade-state). INSERTs new decisions; UPSERTs settled outcomes (COALESCE so a
    settled ret_5d is never clobbered back to NULL after the source row rolls out
    of the 30d window). Idempotent — safe to run daily. Call AFTER
    refresh_missed_outcomes so outcomes are as fresh as possible.

    Returns {'inserted_or_updated': N, 'total_ledger': M}.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_cap_plus_one_shadow
                (ticker, alert_date, ep_score, catalyst_quality,
                 ret_5d, max_high_5d, outcome_updated_at)
            SELECT ticker, alert_date, ep_score, catalyst_quality,
                   ret_5d, max_high_5d,
                   CASE WHEN ret_5d IS NOT NULL OR max_high_5d IS NOT NULL
                        THEN NOW() ELSE NULL END
            FROM mi_ep_missed_outcomes
            WHERE skip_category = 'cap_blocked'
            ON CONFLICT (ticker, alert_date) DO UPDATE SET
                ep_score          = COALESCE(EXCLUDED.ep_score, mi_cap_plus_one_shadow.ep_score),
                catalyst_quality  = COALESCE(EXCLUDED.catalyst_quality, mi_cap_plus_one_shadow.catalyst_quality),
                ret_5d            = COALESCE(EXCLUDED.ret_5d, mi_cap_plus_one_shadow.ret_5d),
                max_high_5d       = COALESCE(EXCLUDED.max_high_5d, mi_cap_plus_one_shadow.max_high_5d),
                outcome_updated_at = CASE
                    WHEN EXCLUDED.ret_5d IS NOT NULL OR EXCLUDED.max_high_5d IS NOT NULL
                    THEN NOW() ELSE mi_cap_plus_one_shadow.outcome_updated_at END
        """)
        n = await conn.fetchval("""
            SELECT COUNT(*) FROM mi_cap_plus_one_shadow
            WHERE alert_date >= CURRENT_DATE - INTERVAL '30 days'
        """)
        total = await conn.fetchval("SELECT COUNT(*) FROM mi_cap_plus_one_shadow")
    return {"recent_window": int(n or 0), "total_ledger": int(total or 0)}


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

    if end_date is None:
        from agents.market_intelligence.collector import et_today
        end = et_today()
    else:
        end = end_date
    start = end - timedelta(days=window_days)

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Single SQL: build the base set from 3 sources, exclude actual trades,
        # then LEFT JOIN forward-return windows from mi_daily_closes.
        # UPSERT on (ticker, alert_date, source).
        await conn.execute(f"""
        WITH traded AS (
            -- #199 + 2026-08-15 fix: statuses in DECLINED_NEVER_FILLED_STATUSES
            -- are NOT trades — no fill ever occurred. Originally only
            -- 'skipped' was excluded here (status IS DISTINCT FROM 'skipped'),
            -- which silently counted 'cancelled' (chase cap, 10:00 ET unfilled
            -- sweep, broker cancel) and 'order_failed' (submit failed after
            -- retry) rows as TRADED — those alerts then got no outcome row in
            -- EITHER population. See DECLINED_NEVER_FILLED_STATUSES docstring.
            SELECT ticker, alert_date FROM mi_live_trades
            WHERE alert_date >= $1 AND alert_date <= $2
              AND status NOT IN {DECLINED_NEVER_FILLED_STATUSES}
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
              AND COALESCE(a.source, 'live') = 'live'  -- #268: replay rows are not missed opportunities
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
                -- #199 + 2026-08-15 fix: attribute WHY the HIGH wasn't
                -- entered from the entry-pipeline skip/cancel/fail row
                -- (block:*/window:*/setup:*/infra:*). Previously only
                -- status='skipped' rows fed skip_reason here, so a
                -- cancelled-without-fill row's reason (e.g.
                -- setup:chase_cap_exceeded) came back NULL even though it
                -- WAS recorded on the row (order_manager._update_trade_status
                -- writes skip_reason on every 'cancelled'/'order_failed'
                -- terminal transition too). NULL now only when truly
                -- unfilled with no matching row at all. Precedence when a
                -- ticker+alert_date has more than one mi_live_trades row
                -- (only possible across different account_modes — the
                -- ticker/alert_date/account_mode UNIQUE constraint means at
                -- most one row per mode, reused in place across re-entry
                -- attempts, never duplicated): ORDER BY lt.id DESC LIMIT 1,
                -- unchanged from before this fix — the most recently WRITTEN
                -- qualifying row wins, whichever of skipped/cancelled/
                -- order_failed it is. This doesn't privilege one kind over
                -- another; it reflects which decision was recorded last.
                sk.skip_reason,
                a.ep_score,
                a.gap_pct,
                NULL::FLOAT AS rel_volume,
                a.catalyst_quality
            FROM mi_ep_alerts a
            LEFT JOIN LATERAL (
                SELECT skip_reason FROM mi_live_trades lt
                WHERE lt.ticker = a.ticker AND lt.alert_date = a.alert_date
                  AND lt.status IN {DECLINED_NEVER_FILLED_STATUSES}
                ORDER BY lt.id DESC LIMIT 1
            ) sk ON TRUE
            WHERE a.alert_date >= $1 AND a.alert_date <= $2
              AND a.score_tier = 'HIGH'
              AND COALESCE(a.source, 'live') = 'live'  -- #268: replay rows are not missed opportunities
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
            -- #583: this CASE now lives ONCE, in _SKIP_CATEGORY_CASE_SQL,
            -- shared with reconcile_missed_outcomes_categories below — a
            -- second copy is exactly how this file's categorisation logic
            -- could silently drift out of sync with itself.
            {_SKIP_CATEGORY_CASE_SQL} AS skip_category,
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


# ── #583 guard: full-history reconcile against CURRENT categorisation ───────
#
# Lightweight "current truth" query — the SAME three source lineages as
# refresh_missed_outcomes's base CTE and the SAME categorisation
# (_SKIP_CATEGORY_CASE_SQL), but unbounded (only an upper date bound, no
# rolling lower bound — that lower bound IS the #583 bug) and WITHOUT the
# mi_daily_closes forward-return LATERAL joins. That omission is what keeps
# this cheap at any table size: the expensive fanout only ever runs (in
# refresh_missed_outcomes) over the last `window_days`, or (in the backfill
# statement below) over the handful of rows this query finds missing — never
# over full history.
_MISSED_OUTCOMES_TRUTH_SQL = f"""
    WITH traded AS (
        SELECT ticker, alert_date FROM mi_live_trades
        WHERE status NOT IN {DECLINED_NEVER_FILLED_STATUSES}
        UNION
        SELECT ticker, alert_date FROM mi_paper_trades
    ),
    scan_filtered AS (
        SELECT DISTINCT ON (s.ticker, s.scan_date)
            s.ticker,
            s.scan_date AS alert_date,
            'scan_filter'::TEXT AS source,
            s.filter_reason AS skip_reason
        FROM mi_ep_scan_log s
        WHERE s.scan_date <= $1
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
            NULL::TEXT AS skip_reason
        FROM mi_ep_alerts a
        WHERE a.alert_date <= $1
          AND a.score_tier = 'MODERATE'
          AND COALESCE(a.source, 'live') = 'live'  -- #268
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
            sk.skip_reason
        FROM mi_ep_alerts a
        LEFT JOIN LATERAL (
            SELECT skip_reason FROM mi_live_trades lt
            WHERE lt.ticker = a.ticker AND lt.alert_date = a.alert_date
              AND lt.status IN {DECLINED_NEVER_FILLED_STATUSES}
            ORDER BY lt.id DESC LIMIT 1
        ) sk ON TRUE
        WHERE a.alert_date <= $1
          AND a.score_tier = 'HIGH'
          AND COALESCE(a.source, 'live') = 'live'  -- #268
          AND NOT EXISTS (
              SELECT 1 FROM traded t
              WHERE t.ticker = a.ticker AND t.alert_date = a.alert_date
          )
        ORDER BY a.ticker, a.alert_date, a.created_at DESC
    ),
    truth AS (
        SELECT * FROM scan_filtered
        UNION ALL SELECT * FROM moderate
        UNION ALL SELECT * FROM high_unentered
    )
    SELECT ticker, alert_date, source, skip_reason,
        {_SKIP_CATEGORY_CASE_SQL} AS skip_category
    FROM truth
"""

# Backfill INSERT for rows the truth query finds but the table doesn't have
# yet. Mirrors refresh_missed_outcomes's base/with_returns/INSERT shape
# exactly (same source lineages, same categorisation, same return basis) but
# unbounded AND gated by NOT EXISTS(already stored) in every lineage CTE —
# that gate runs BEFORE the mi_daily_closes LATERAL fanout, so the fanout
# only ever touches genuinely-missing rows (a handful), never full history.
_MISSED_OUTCOMES_BACKFILL_SQL = f"""
    WITH traded AS (
        SELECT ticker, alert_date FROM mi_live_trades
        WHERE status NOT IN {DECLINED_NEVER_FILLED_STATUSES}
        UNION
        SELECT ticker, alert_date FROM mi_paper_trades
    ),
    scan_filtered AS (
        SELECT DISTINCT ON (s.ticker, s.scan_date)
            s.ticker, s.scan_date AS alert_date,
            'scan_filter'::TEXT AS source, s.filter_reason AS skip_reason,
            s.ep_score, s.gap_pct, s.rel_volume, s.catalyst_quality
        FROM mi_ep_scan_log s
        WHERE s.scan_date <= $1
          AND s.filter_reason IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM traded t WHERE t.ticker = s.ticker AND t.alert_date = s.scan_date
          )
          AND NOT EXISTS (
              SELECT 1 FROM mi_ep_missed_outcomes existing
              WHERE existing.ticker = s.ticker AND existing.alert_date = s.scan_date
                AND existing.source = 'scan_filter'
          )
        ORDER BY s.ticker, s.scan_date, s.created_at DESC
    ),
    moderate AS (
        SELECT DISTINCT ON (a.ticker, a.alert_date)
            a.ticker, a.alert_date,
            'moderate_alert'::TEXT AS source, NULL::TEXT AS skip_reason,
            a.ep_score, a.gap_pct, NULL::FLOAT AS rel_volume, a.catalyst_quality
        FROM mi_ep_alerts a
        WHERE a.alert_date <= $1
          AND a.score_tier = 'MODERATE'
          AND COALESCE(a.source, 'live') = 'live'
          AND NOT EXISTS (
              SELECT 1 FROM traded t WHERE t.ticker = a.ticker AND t.alert_date = a.alert_date
          )
          AND NOT EXISTS (
              SELECT 1 FROM mi_ep_missed_outcomes existing
              WHERE existing.ticker = a.ticker AND existing.alert_date = a.alert_date
                AND existing.source = 'moderate_alert'
          )
        ORDER BY a.ticker, a.alert_date, a.created_at DESC
    ),
    high_unentered AS (
        SELECT DISTINCT ON (a.ticker, a.alert_date)
            a.ticker, a.alert_date,
            'high_unentered'::TEXT AS source, sk.skip_reason,
            a.ep_score, a.gap_pct, NULL::FLOAT AS rel_volume, a.catalyst_quality
        FROM mi_ep_alerts a
        LEFT JOIN LATERAL (
            SELECT skip_reason FROM mi_live_trades lt
            WHERE lt.ticker = a.ticker AND lt.alert_date = a.alert_date
              AND lt.status IN {DECLINED_NEVER_FILLED_STATUSES}
            ORDER BY lt.id DESC LIMIT 1
        ) sk ON TRUE
        WHERE a.alert_date <= $1
          AND a.score_tier = 'HIGH'
          AND COALESCE(a.source, 'live') = 'live'
          AND NOT EXISTS (
              SELECT 1 FROM traded t WHERE t.ticker = a.ticker AND t.alert_date = a.alert_date
          )
          AND NOT EXISTS (
              SELECT 1 FROM mi_ep_missed_outcomes existing
              WHERE existing.ticker = a.ticker AND existing.alert_date = a.alert_date
                AND existing.source = 'high_unentered'
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
        {_SKIP_CATEGORY_CASE_SQL} AS skip_category,
        ep_score, gap_pct, rel_volume, catalyst_quality,
        open_d0, close_d0,
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
    ON CONFLICT (ticker, alert_date, source) DO NOTHING
"""


async def reconcile_missed_outcomes_categories(as_of: Optional[date] = None) -> dict:
    """#583 guard: heal every row refresh_missed_outcomes's rolling window
    can't reach.

    Three things the windowed UPSERT structurally cannot do, because it only
    ever looks at `alert_date` inside `[end - window_days, end]`:

      1. PRUNE an "orphan" — a stored row whose (ticker, alert_date, source)
         the CURRENT logic no longer produces at all (its mi_ep_alerts /
         mi_ep_scan_log source row aged out of retention, or a since-shipped
         WHERE-clause fix — #268's `source='live'` — now excludes it). Left
         alone, an orphan sits with its ORIGINAL classification forever and
         gets silently counted by anything that reads this table (the
         2026-08-21 gate-ranking table's "5 doublers" in both
         `high_unentered` and `window_missed` were entirely this — the true
         count for both was zero).
      2. CORRECT a "miscategorized" row — still reproducible, but the
         CURRENT categorisation logic now buckets it differently than what's
         stored (e.g. a future _SKIP_CATEGORY_CASE_SQL edit). Empirically
         zero of these exist today (verified against prod 2026-08-22 — every
         still-derivable row's stored skip_category already matches a fresh
         recompute) but the mechanism must exist for the NEXT categorisation
         fix, which is the whole point of #583.
      3. BACKFILL a "missing" row — the current logic says a row should
         exist but the table has none, because it aged out of the window
         before a fix that would have captured it ever shipped (all 27 of
         the `high_unentered` backfill rows found 2026-08-22 are exactly
         this: `status='cancelled'` HIGHs dated 2026-05-11 to 2026-07-15,
         silently miscounted as TRADED until the 2026-08-15 cancelled/
         order_failed fix — by then they were 30+ days old and the windowed
         UPSERT could never reach them).

    Every action is counted and logged (and returned, so a caller can put it
    in an audit event) — a prune must be OBSERVABLE, never a silent mass
    delete: if mi_ep_alerts or mi_ep_scan_log ever lost rows it shouldn't
    have, the very next run of this function would show a spike in
    `orphaned_pruned` rather than quietly erasing history.

    Cheap by construction regardless of source-table growth: the truth/diff
    query never joins mi_daily_closes, and the backfill INSERT's own
    NOT EXISTS(already stored) guard runs BEFORE that join — see
    `_MISSED_OUTCOMES_TRUTH_SQL` / `_MISSED_OUTCOMES_BACKFILL_SQL` docstrings.

    Idempotent — safe to run every night immediately after
    refresh_missed_outcomes, or ad hoc.
    """
    await ensure_missed_outcomes_schema()

    if as_of is None:
        from agents.market_intelligence.collector import et_today
        end = et_today()
    else:
        end = as_of

    pool = await get_pool()
    async with pool.acquire() as conn:
        truth_rows = await conn.fetch(_MISSED_OUTCOMES_TRUTH_SQL, end)
        stored_rows = await conn.fetch(
            """
            SELECT id, ticker, alert_date, source, skip_reason, skip_category
            FROM mi_ep_missed_outcomes
            WHERE alert_date <= $1
            """,
            end,
        )

        truth_by_key = {
            (r["ticker"], r["alert_date"], r["source"]): r for r in truth_rows
        }
        stored_by_key = {
            (r["ticker"], r["alert_date"], r["source"]): r for r in stored_rows
        }

        orphan_ids = [
            r["id"] for r in stored_rows
            if (r["ticker"], r["alert_date"], r["source"]) not in truth_by_key
        ]
        miscategorized = [
            (r["id"], truth_by_key[key]["skip_category"], truth_by_key[key]["skip_reason"])
            for r in stored_rows
            if (key := (r["ticker"], r["alert_date"], r["source"])) in truth_by_key
            and (
                r["skip_category"] != truth_by_key[key]["skip_category"]
                or r["skip_reason"] != truth_by_key[key]["skip_reason"]
            )
        ]
        missing_expected = sum(1 for k in truth_by_key if k not in stored_by_key)

        if orphan_ids:
            await conn.execute(
                "DELETE FROM mi_ep_missed_outcomes WHERE id = ANY($1::int[])",
                orphan_ids,
            )

        if miscategorized:
            ids = [m[0] for m in miscategorized]
            cats = [m[1] for m in miscategorized]
            reasons = [m[2] for m in miscategorized]
            await conn.execute(
                """
                UPDATE mi_ep_missed_outcomes m
                SET skip_category = v.skip_category,
                    skip_reason = v.skip_reason,
                    last_refreshed_at = NOW()
                FROM (
                    SELECT UNNEST($1::int[]) AS id,
                           UNNEST($2::text[]) AS skip_category,
                           UNNEST($3::text[]) AS skip_reason
                ) v
                WHERE m.id = v.id
                """,
                ids, cats, reasons,
            )

        # #583 review note: ON CONFLICT DO NOTHING means "expected" and
        # "actually inserted" can differ (e.g. a row landed between the
        # fetches above and this INSERT) — parse the real asyncpg "INSERT 0
        # N" result so the returned/audited count is what actually happened,
        # not just what we predicted.
        missing_backfilled = 0
        if missing_expected:
            insert_result = await conn.execute(_MISSED_OUTCOMES_BACKFILL_SQL, end)
            if isinstance(insert_result, str) and insert_result:
                try:
                    missing_backfilled = int(insert_result.split()[-1])
                except ValueError:
                    missing_backfilled = missing_expected  # mocked/non-numeric result

    result = {
        "orphaned_pruned": len(orphan_ids),
        "miscategorized_fixed": len(miscategorized),
        "missing_backfilled": missing_backfilled,
        "missing_expected": missing_expected,
        "as_of": end.isoformat(),
    }
    logger.info(f"reconcile_missed_outcomes_categories: {result}")
    return result


# ── Query helpers (Telegram + weekly review) ────────────────────────────────

# Skip categories that represent CORRECTLY filtered names (size / illiquidity
# / structural M&A noise / volatility too high / already extended). These
# rejections say "not in our trade universe" — they didn't bleed tradeable
# opportunity, they did their job. Hidden from /missed by default; visible
# via `/missed all`.
_UNTRADEABLE_CATEGORIES = (
    "mcap_low",          # market cap below floor
    "adv_low",           # avg dollar volume below floor
    "ma_filter",         # M&A target / deal-pinned shell
    "atr_high",          # volatility above tradeable threshold
    "extension_gate",    # price already extended (parabolic-shape rejection)
    "d1_universe_floor", # #570: prior-day close<$5 / volume<50k — correctly filtered
                         # by design, not a should've-entered miss; same treatment as
                         # the other structural universe floors above
)

# The 'should've-entered' cohort (#219): categories where the system SCORED the
# name tradeable / WANTED in, but a safeguard, timing, setup-at-entry, cooldown,
# or infra gate stopped it (or it scored but stayed below the entry bar, or
# didn't fill). This is the FTNT(cap_blocked)/INOD(breaker_blocked) class — the
# genuine gaps. Deliberately EXCLUDES universe/quality FILTER rejections
# (pm_rvol_low / session_rvol_low / outside_top20 / score_below_50 /
# catalyst_downgrade / duplicate_scan + the structural set): a filter passing on
# a micro-cap that then mooned is a FILTER-CALIBRATION question (the by-category
# roll-up already surfaces those) — flat-ranking the whole non-structural set by
# peak just lets penny rockets bury the safeguard-blocked names we actually wanted.
_SHOULDVE_ENTERED_CATEGORIES = (
    "cap_blocked",      # #199 max-positions cap full (FTNT 5/07)
    "breaker_blocked",  # #199 circuit-breaker cooldown (INOD 5/08)
    "block_other",      # #199 other safeguard block
    "window_missed",    # #199 missed ORB submission window
    "stop_too_wide",    # #199 setup reject at entry (ATR stop too wide)
    "faded_from_orb",   # #199 faded below ORB before fill
    "setup_other",      # #199 other entry-setup reject
    "infra_skip",       # infra / auth failure aborted an intended entry
    "high_unentered",   # HIGH that never filled
    "moderate_tier",    # scored MODERATE — below the entry bar, not entered
    "cooldown",         # EP in cooldown (the #170 re-setup-admission class)
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
    "d1_universe_floor":   "structural",  # #570
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
    # Entry-pipeline blocks (#199) — system WANTED the HIGH but a safeguard /
    # timing / setup gate stopped it. The should've-entered-winners cohort —
    # must surface (NOT structural). cap/breaker/window = operational;
    # stop-too-wide/faded = signal; infra = other.
    "cap_blocked":         "operational",
    "breaker_blocked":     "operational",
    "block_other":         "operational",
    "window_missed":       "operational",
    "stop_too_wide":       "signal",
    "faded_from_orb":      "signal",
    "setup_other":         "signal",
    "infra_skip":          "other",
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

# Shared predicate (#222): suppress a `duplicate_scan` row when a NON-duplicate
# sibling exists for the same ticker+date — the dedup path records ep_score=NULL
# by design, so surfacing it beside the real moderate/high row is redundant noise.
# Stand-alone duplicate_scan rows (no sibling) still surface. DRY-extracted from
# 3 identical inline copies; interpolated into each query's f-string. The main
# table MUST be aliased `m` at every call site.
_SUPPRESS_DUP_SIBLING_SQL = """
                  AND NOT (
                      m.skip_category = 'duplicate_scan'
                      AND EXISTS (
                          SELECT 1 FROM mi_ep_missed_outcomes sib
                          WHERE sib.ticker = m.ticker
                            AND sib.alert_date = m.alert_date
                            AND sib.skip_category <> 'duplicate_scan'
                      )
                  )"""


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
                  -- duplicate_scan sibling suppression (#222 shared predicate)
                  {_SUPPRESS_DUP_SIBLING_SQL}
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
        rows = await conn.fetch(f"""
            WITH base AS (
                SELECT skip_category, ticker, alert_date,
                       ret_5d, max_high_5d
                FROM mi_ep_missed_outcomes m
                WHERE alert_date >= CURRENT_DATE - $1::INT
                  -- duplicate_scan sibling suppression (#222 shared predicate)
                  {_SUPPRESS_DUP_SIBLING_SQL}
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


async def top_shouldve_entered_gaps(
    window_days: int = 30,
    limit: int = 8,
    min_peak: float = 0.05,
) -> list[dict]:
    """The 'should've-entered' cohort — actionable misses flat-ranked by PEAK
    missed upside (max_high_5d). (#219, operator 2026-06-06: leverage /missed for
    recurring gap analysis — why FTNT/INOD missed.)

    Cohort = every NON-structural miss: a safeguard/timing block the system hit
    after wanting in (#199 cap_blocked / breaker_blocked / window_missed /
    stop_too_wide / faded_from_orb), a scored-but-not-entered tier
    (high_unentered / moderate_tier), or a tunable filter that rejected a name
    that then ran. Structural rejections (mcap / adv / atr / M&A / extension) are
    EXCLUDED — they did their job, they are not gaps.

    'Verified first' = each row carries its KIND (safeguard block vs weak signal
    vs scored-not-entered) + the verified reason; the section SURFACES the cohort
    and the evidence (peak %, reason), it does NOT prescribe a fix (the operator
    verifies — see feedback_weekly_review_surface_not_prescribe). Ranked by
    max_high_5d so a real, sized opportunity outranks a barely-green name;
    min_peak drops trivially-small 'misses' (default >= 5% peak).
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT ticker, alert_date, source, skip_category, skip_reason,
                   ep_score, catalyst_quality, open_d0, ret_5d, max_high_5d
            FROM mi_ep_missed_outcomes m
            WHERE m.alert_date >= CURRENT_DATE - $1::INT
              AND m.skip_category IN {_SHOULDVE_ENTERED_CATEGORIES}
              AND COALESCE(m.open_d0, 0) >= {_DEFAULT_PRICE_FLOOR}
              AND m.max_high_5d >= $2
              -- duplicate_scan sibling suppression (#222 shared predicate)
              {_SUPPRESS_DUP_SIBLING_SQL}
            ORDER BY m.max_high_5d DESC NULLS LAST
            LIMIT $3
        """, window_days, min_peak, limit)
    return [dict(r) for r in rows]


async def aggregate_missed_for_weekly(window_days: int = 7) -> dict:
    """Weekly review input: should've-entered gaps + top winners + roll-up."""
    top = await top_missed_winners(
        window_days=window_days, horizon="5d", per_category=2,
    )
    cats = await missed_by_category(window_days=window_days)
    # Gaps use a 30d window (the weekly 7d window is too thin a cohort for a
    # ranked gap list); it's clearly labeled 30d in the section header.
    gaps = await top_shouldve_entered_gaps(window_days=30, limit=8)
    return {
        "window_days": window_days,
        "top_winners": top,
        "by_category": cats,
        "gaps": gaps,
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
    "d1_universe_floor":  "D-1 price/volume floor",  # #570 follow-up
    "moderate_tier":      "MODERATE — not entered",
    "high_unentered":     "HIGH — no fill",
    # #199 entry-pipeline blocks (should've-entered cohort)
    "cap_blocked":        "Max positions (cap full)",
    "breaker_blocked":    "Circuit breaker cooldown",
    "block_other":        "Other safeguard block",
    "window_missed":      "Missed ORB window",
    "stop_too_wide":      "Stop too wide",
    "faded_from_orb":     "Faded from ORB",
    "setup_other":        "Other setup reject",
    "infra_skip":         "Infra / auth failure",
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


def format_gaps_section_for_weekly(gaps: list[dict]) -> str:
    """Prominent '🚨 Should've-entered gaps' section (#219) — the actionable
    missed cohort ranked by peak upside, each row with its verified reason.
    Facts only, no prescription (feedback_weekly_review_surface_not_prescribe)."""
    if not gaps:
        return ""
    parts = [
        "🚨 *Should've-entered gaps (30d)* — ranked by peak missed upside",
        "_The system wanted in but a gate stopped it: safeguard/timing/setup_",
        "_blocks · cooldown · scored-not-entered. Verify before acting._",
        "```",
        "tckr  date   peak    5d   reason",
    ]
    for r in gaps:
        tk = r["ticker"][:5].ljust(5)
        d = r["alert_date"].strftime("%m/%d") if r.get("alert_date") else "  —  "
        peak = _fmt_pct_fixed(r.get("max_high_5d"))
        c5 = _fmt_pct_fixed(r.get("ret_5d"))
        reason = _humanize_category(r.get("skip_category"))[:24]
        parts.append(f"{tk} {d}  {peak}  {c5}  {reason}")
    parts.append("```")
    return "\n".join(parts)


def format_missed_section_for_weekly(missed: dict) -> str:
    """Weekly review: should've-entered gaps (prominent) + top winners + roll-up.

    Same grouping/monospace shape as `/missed` so the visual rhythm is
    consistent across the two surfaces (digest is just shorter).
    """
    top = missed.get("top_winners") or []
    cats = missed.get("by_category") or []
    gaps_section = format_gaps_section_for_weekly(missed.get("gaps") or [])
    if not top and not cats and not gaps_section:
        return ""
    window_days = missed.get("window_days", 7)
    parts: list[str] = []
    if gaps_section:
        parts.append(gaps_section)
        if top or cats:
            parts.append("")  # spacer before the broader appendix
    if top or cats:
        parts.append(f"🔍 *Missed Opportunities ({window_days}d):*")

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


