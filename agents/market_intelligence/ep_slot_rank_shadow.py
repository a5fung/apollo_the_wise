"""#533 WITHIN-DAY SLOT RANKING — the acting RS order + the five-ranking watch record
(2026-08-30, OPERATOR-SIGNED: "switch to RS rank, but observe going forward if it
deteriorates or other ranking starts to do better").

THE DEFECT THIS FIXES. `live_tracker.process_new_alerts_live` selected the day's HIGH
alerts with `DISTINCT ON (ticker) … ORDER BY ticker, ep_score DESC` — `DISTINCT ON`
forces the sort to start with ticker, so `ep_score DESC` only broke ties WITHIN one
ticker. Across tickers the surviving order was ALPHABETICAL: ticker name decided which
alerts got the five position slots. Evidence (docs/analysis/533_within_day_ranking_
2026-08-30.md, 15 multi-alert mornings): alphabetical +1.6% median top2-vs-rest edge,
8/15 mornings positive; prior-day RS composite +8.4%, 10/15 — surviving best-day
removal (+8.1%) and removal of the day that inspired it (+11.8%), and missing no more
day-best movers than the incumbent (4 vs 4, P14).

THE ACTING ORDER (this module's `rank_board_by_rs`, consumed by exactly ONE acting
site — live_tracker's flag-guarded re-sort, the ep_shortlist_shadow/ep_detector
precedent): prior-day `rs_composite` DESC, `ep_score` DESC tiebreak, ticker ASC final
(total-order determinism). A name with NO prior-day RS row (universe drift — 0 of 141
in the evidence window) is NEVER dropped: it ranks after every RS-scored name,
ordered by ep_score among its peers, and live_tracker logs it loudly. The dedup query
itself is untouched — ordering moved to Python (the ep_shortlist_prescore pattern).

🔁 THE REVERT FLAG — `ep_slot_rank_rs` runtime toggle / `EP_SLOT_RANK_RS_ENABLED`
env, default ON, read per invocation in `process_new_alerts_live` (instant
no-redeploy revert, ~60s cache lag). OFF → the board keeps the legacy query's own
order EXACTLY (the re-sort simply never runs; the SELECT is byte-identical either
way) — pinned by tests/test_533_slot_ranking.py. Revert SQL:
    INSERT INTO mi_safeguard_state (safeguard, account_mode, state, last_transition_at, updated_at)
    VALUES ('ep_slot_rank_rs', 'global', 'off', NOW(), NOW())
    ON CONFLICT (safeguard, account_mode) DO UPDATE SET state = EXCLUDED.state, updated_at = NOW();
Fail direction on ANY error in the ranking block (toggle read, RS fetch, sort): the
legacy order ACTS, loudly (logger.exception + `slot_rank_fallback` audit row) —
never a dead selection.

THE WATCH — the other half of the ruling. Every invocation with >=1 alert on the
board, one row per (invocation, ticker) into `mi_ep_slot_rank_shadow`: RAW INPUTS
(ep_score / gap_pct / prior-day rs_composite, rs_rank, adv_20, score-row close /
theme stage — never computed points, the #583 stale-derived-value class) plus the
1-based rank the board's names take under each of FIVE candidate orderings:
  rank_rs         — the acting order above (prior-day RS composite)
  rank_ep_score   — ep_score DESC (the post-08-22 score: ZERO settled multi-alert
                    days existed at ship — this column is how it gets its read)
  rank_composite  — the morning briefing's sort, briefing._ep_composite_key
                    (ep_score + theme bonus + capped RS bonus), imported so the
                    record tracks the briefing's definition, never a copy
  rank_adv        — ADV$ DESC (adv_20 x score-row close, the pre-gap-price
                    convention of ep_detector's large-cap floor)
  rank_alpha      — ticker ASC (the deposed incumbent — the control)
`acting_key` stamps which ordering ACTED that invocation ('rs' | 'legacy_alpha') —
never inferred from dates. Append-only BY DESIGN (no upsert): the board grows through
the morning (bar_stream + cron triggers), and per-invocation history with `trigger` +
`recorded_at` is what lets a reader reconstruct the 09:31 decision board; read-time
analysis dedups to each morning's earliest invocation. Outcomes are NOT stored:
they settle forward in `mi_daily_closes` and are joined at read time (ret5 from
day-0 open, the evidence doc's primary metric), so the record can never go stale.
The review that answers "deteriorates / other ranking does better" is
`ep_slot_ranking_watch_533` in data_gated_reviews.yaml (10 settled multi-alert
mornings).

$0 AT RUNTIME — one small mi_stock_scores fetch (done by live_tracker, shared with
the acting sort so acting and recorded RS can never drift) + one mi_themes fetch
here; no LLM, no API call. The recorder is fail-open (log only, returns 0) and its
table is read by NO grading / entry / sizing / safeguard path — comparison telemetry
only (the ep_shortlist_shadow contract). SILENT: no Telegram, ever; liveness is
watched by `health_checks._DETECTOR_LIVENESS_TABLES`.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Module-level for test patchability (the ep_shortlist_shadow convention) — but the
# writer takes the caller's POOL, so the money path's mocked pool bounds every read
# and write this module makes during that call.
from agents.market_intelligence.db import get_pool  # noqa: E402  (kept for parity/tests)

# The briefing's OWN composite sort key — imported, never copied, so rank_composite
# tracks whatever the briefing actually does (it IS the "briefing composite"
# candidate). _THEME_BONUS strength order is reused for strongest-stage-per-ticker.
from agents.market_intelligence.briefing import _ep_composite_key, _THEME_BONUS  # noqa: E402

# Which orderings the watch records. Frozen tuple so a rename/drop breaks the pin in
# tests/test_533_slot_ranking.py instead of silently shrinking the record.
SLOT_RANK_KEYS: tuple[str, ...] = (
    "rank_rs", "rank_ep_score", "rank_composite", "rank_adv", "rank_alpha",
)


def slot_rank_key(
    ticker: str, ep_score: "float | None", rs_composite: "float | None",
) -> tuple:
    """THE ACTING SORT KEY (operator-signed 2026-08-30): prior-day RS composite
    DESC -> ep_score DESC -> ticker ASC. A missing RS read (None) sorts AFTER
    every RS-scored name — no evidence of relative strength earns no priority
    over evidenced names — but the name stays on the board (never dropped; it
    competes for whatever slots remain, ordered by ep_score among its peers)."""
    has_rs = rs_composite is not None
    return (
        0 if has_rs else 1,                                  # RS-scored names first
        -(float(rs_composite) if has_rs else 0.0),           # RS composite DESC
        -(float(ep_score) if ep_score is not None else 0.0), # ep_score DESC tiebreak
        ticker,                                              # total order, deterministic
    )


def rank_board_by_rs(
    alerts: list[dict], rs_by_ticker: dict[str, dict],
) -> dict[str, int]:
    """Ticker -> 1-based rank under the acting RS key. Pure — no I/O, no mutation.
    Used by BOTH the acting re-sort in live_tracker AND the shadow record below,
    so what acted and what was recorded as acting cannot drift."""
    ordered = sorted(
        alerts,
        key=lambda a: slot_rank_key(
            a["ticker"], a.get("ep_score"),
            (rs_by_ticker.get(a["ticker"]) or {}).get("rs_composite"),
        ),
    )
    return {a["ticker"]: i + 1 for i, a in enumerate(ordered)}


def _rank_from_key(alerts: list[dict], keyfn) -> dict[str, int]:
    ordered = sorted(alerts, key=keyfn)
    return {a["ticker"]: i + 1 for i, a in enumerate(ordered)}


def compute_slot_rank_rows(
    alerts: list[dict],
    rs_by_ticker: dict[str, dict],
    rs_score_date: "date | None",
    theme_stage_by_ticker: dict[str, str],
    acting_key: str,
    trigger: str,
) -> list[dict]:
    """One row per board name: raw inputs + the name's 1-based rank under each of
    the five candidate orderings (see module docstring). Pure — no I/O.

    Every ordering ends in ticker ASC so each is a reproducible total order,
    never an input-order lottery (the Stage-0 nine-way-tie lesson)."""

    def _rs(t: str) -> dict:
        return rs_by_ticker.get(t) or {}

    def _adv_dollar(t: str) -> "float | None":
        adv, close = _rs(t).get("adv_20"), _rs(t).get("close")
        return float(adv) * float(close) if adv and close else None

    def _eps(a: dict) -> float:
        return float(a.get("ep_score") or 0.0)

    rank_rs = rank_board_by_rs(alerts, rs_by_ticker)
    rank_ep_score = _rank_from_key(alerts, lambda a: (-_eps(a), a["ticker"]))
    rank_composite = _rank_from_key(alerts, lambda a: (
        -_ep_composite_key(
            {**a, "rs_composite": _rs(a["ticker"]).get("rs_composite")},
            theme_stage_by_ticker,
        ),
        a["ticker"],
    ))
    rank_adv = _rank_from_key(alerts, lambda a: (
        0 if _adv_dollar(a["ticker"]) is not None else 1,
        -(_adv_dollar(a["ticker"]) or 0.0),
        -_eps(a),
        a["ticker"],
    ))
    rank_alpha = _rank_from_key(alerts, lambda a: a["ticker"])

    board_n = len(alerts)
    rows = []
    for a in alerts:
        t = a["ticker"]
        rows.append({
            "ticker": t,
            # raw inputs (the persisted record — replayable at $0 forever):
            "ep_score": a.get("ep_score"),
            "gap_pct": a.get("gap_pct"),
            "rs_composite": _rs(t).get("rs_composite"),
            "rs_rank": _rs(t).get("rs_rank"),
            "rs_score_date": rs_score_date,
            "adv_20": _rs(t).get("adv_20"),
            "score_close": _rs(t).get("close"),
            "theme_stage": theme_stage_by_ticker.get(t),
            # the decision record (what each ordering did on THIS board):
            "rank_rs": rank_rs[t],
            "rank_ep_score": rank_ep_score[t],
            "rank_composite": rank_composite[t],
            "rank_adv": rank_adv[t],
            "rank_alpha": rank_alpha[t],
            "acting_key": acting_key,
            "trigger": trigger,
            "board_n": board_n,
        })
    return rows


async def fetch_theme_stage_by_ticker(
    pool: Any, tickers: list[str], before_date: date,
) -> dict[str, str]:
    """Strongest theme stage per ticker from the latest mi_themes snapshot
    STRICTLY BEFORE `before_date` (snapshots are written nightly, so at 09:31
    this is yesterday's board — followable, the evidence doc's construction).
    Fail direction: {} on any error, loudly logged — the composite counterfactual
    then degrades to ep_score+RS, never blocks anything."""
    if not tickers:
        return {}
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT t.stage, x.tk
                FROM mi_themes t, LATERAL unnest(t.tickers) AS x(tk)
                WHERE t.theme_date = (
                    SELECT MAX(theme_date) FROM mi_themes WHERE theme_date < $1
                ) AND x.tk = ANY($2)
            """, before_date, tickers)
        out: dict[str, str] = {}
        for r in rows:
            tk, stage = r["tk"], r["stage"]
            if _THEME_BONUS.get(stage, 0) >= _THEME_BONUS.get(out.get(tk), 0):
                out[tk] = stage
        return out
    except Exception as e:  # loud-ok: telemetry input only — degrade to no-theme, never raise
        logger.warning(f"slot-rank shadow: theme-stage fetch failed — {e}")
        return {}


async def snapshot_slot_rank_board(
    pool: Any,
    alerts: list[dict],
    rs_by_ticker: dict[str, dict],
    rs_score_date: "date | None",
    acting_key: str,
    trigger: str,
    alert_date: date,
    recorded_at: "datetime | None" = None,
) -> int:
    """The single writer's entry point, called fire-and-forget from
    `process_new_alerts_live` (both toggle sides — a revert must not kill the
    watch, it IS the revert's evidence). Never raises; returns rows written
    (0 on any failure). SILENT — no Telegram on any path."""
    try:
        if not alerts:
            return 0
        if recorded_at is None:
            from zoneinfo import ZoneInfo
            recorded_at = datetime.now(ZoneInfo("America/New_York"))
        themes = await fetch_theme_stage_by_ticker(
            pool, [a["ticker"] for a in alerts], alert_date)
        rows = compute_slot_rank_rows(
            alerts, rs_by_ticker, rs_score_date, themes, acting_key, trigger)
        async with pool.acquire() as conn:
            await conn.executemany(_INSERT_SQL, [
                (
                    alert_date, r["ticker"], recorded_at, r["trigger"],
                    r["board_n"],
                    r["ep_score"], r["gap_pct"],
                    r["rs_composite"], r["rs_rank"], r["rs_score_date"],
                    r["adv_20"], r["score_close"], r["theme_stage"],
                    r["rank_rs"], r["rank_ep_score"], r["rank_composite"],
                    r["rank_adv"], r["rank_alpha"],
                    r["acting_key"],
                )
                for r in rows
            ])
        return len(rows)
    except Exception as e:  # loud-ok: comparison telemetry only — never blocks the entry path
        logger.warning(f"slot-rank shadow: snapshot write failed — {e}")
        return 0


_INSERT_SQL = """
    INSERT INTO mi_ep_slot_rank_shadow (
        alert_date, ticker, recorded_at, trigger, board_n,
        ep_score, gap_pct, rs_composite, rs_rank, rs_score_date,
        adv_20, score_close, theme_stage,
        rank_rs, rank_ep_score, rank_composite, rank_adv, rank_alpha,
        acting_key
    ) VALUES ($1,$2,$3,$4,$5, $6,$7,$8,$9,$10, $11,$12,$13, $14,$15,$16,$17,$18, $19)
"""
