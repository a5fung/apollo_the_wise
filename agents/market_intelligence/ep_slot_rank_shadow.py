"""#533 WITHIN-DAY SLOT RANKING — the acting RS order + the seven-ranking watch record
(2026-08-30, OPERATOR-SIGNED: "switch to RS rank, but observe going forward if it
deteriorates or other ranking starts to do better"; sixth ranking — rank_vol_pct —
added 2026-09-04, #624; seventh — rank_shelf, the shelf distance — added 2026-11-21,
#594; both records only, see below).

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
theme stage / vol_percentile — never computed points, the #583 stale-derived-value
class) plus the 1-based rank the board's names take under each of SEVEN candidate
orderings (six written with the row, the seventh — rank_shelf — filled in afterwards,
see THE SHELF STEP below):
  rank_rs         — the acting order above (prior-day RS composite)
  rank_ep_score   — ep_score DESC (the post-08-22 score: ZERO settled multi-alert
                    days existed at ship — this column is how it gets its read)
  rank_composite  — the morning briefing's sort, briefing._ep_composite_key
                    (ep_score + theme bonus + capped RS bonus), imported so the
                    record tracks the briefing's definition, never a copy
  rank_adv        — ADV$ DESC (adv_20 x score-row close, the pre-gap-price
                    convention of ep_detector's large-cap floor)
  rank_alpha      — ticker ASC (the deposed incumbent — the control)
  rank_vol_pct    — vol_percentile DESC (2026-09-04). Raw input is `a["vol_percentile"]`,
                    already computed and persisted per candidate by ep_detector's
                    `_volume_percentile` (fed by `db.get_volume_history_daily_closes`
                    post-open since today, `get_volume_history`/adv_20 pre-open) and
                    carried straight off the mi_ep_alerts row this module reads —
                    NO new query. Provenance an analyst must know: it is whichever
                    mi_ep_alerts row survived the board query's own `DISTINCT ON
                    (ticker) ... ep_score DESC` dedup for that ticker, so a ticker
                    re-alerted intraday carries its max-ep_score row's percentile,
                    not necessarily its first or last. Operator ruling 2026-09-04: prioritize proving edge
                    on the universe we already trade before risking capital chasing
                    micro-caps. A same-day study found this rule strong on cap>=$500M
                    names (+1.31R, 7/7, n=7) and on admitted names (+1.54R, 3/3, n=3)
                    — TINY SAMPLES, STRIKING NOT SETTLED. This column exists to make
                    the question answerable on real data, nothing more; see the
                    ⚠ RECORDS-ONLY note below.
  rank_shelf      — shelf distance DESC (2026-11-21, #594): `dmin`, how far the last
                    two pullback lows sit from the top of the base the stock broke
                    out of before its run, in ADR units — higher (pullbacks held
                    nearer or above that top) ranks first; no reading ranks last;
                    ticker ASC breaks ties. See THE SHELF STEP below.
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

⚠ RECORDS ONLY — `rank_vol_pct` and `rank_shelf` (like their five siblings) change NO
slot allocation, admission, score or alert. They are read by no grading/entry/sizing/
safeguard path. Making any recorded ranking act would be a separate operator-signed
change under CHANGE_PROCESS (THE LINE) — nothing here does that.

THE SHELF STEP (2026-11-21, #594, operator: "Aligned, but we should keep testing this
idea"). Evidence: docs/analysis/ep_rank_v2_prereg_2026-11-03.md RESULT 6-9 (on his
labelled charts the good ones sit nearer their shelf than the bad ones about 3 times
in 4). The feature has ONE definition — `shelf_distance.py` — shared with the analysis
scripts that produced that evidence.
  WHEN IT RUNS. Unlike the other six, this ranking needs a query the entry path does
  not already make (each board name's daily bars), so it is NOT part of the row's
  INSERT. `live_tracker.process_new_alerts_live` starts `record_shelf_ranks` as a
  detached task as its LAST statement — after every entry task of THAT invocation has
  finished and the skip digest is sent — so it adds nothing to the function's return
  (the bar-stream handler awaits that return). The function is invoked several times
  a morning (once per first bar + the 09:31 cron), so a step that ran at once could
  overlap a LATER invocation's entries and hold one of the pool's five connections.
  To remove that entirely the task does NOT TOUCH THE DATABASE BEFORE 09:46 ET on
  the alert date (SHELF_NOT_BEFORE_ET — the ORB submission window shuts at 09:45):
  started earlier it sleeps until then; started later (or for a past date) it runs
  at once. Its inputs are prior-day bars, so waiting changes no number. Once it
  runs, the reads + write are bounded by SHELF_STEP_TIMEOUT_SEC.
  NOT COLLAPSED: each invocation's task fills its OWN rows (its own recorded_at) —
  a morning with four invocations before 09:46 runs four small passes at 09:46.
  Chosen over one merged pass because it needs no shared state and every pass is
  after the window anyway.
  ⚠ A DEPLOY OR RESTART BEFORE 09:46 DROPS THE SLEEPING TASKS — those rows keep NULL
  shelf columns and NO audit row is written (nothing ran to fail). Accepted: the
  record is recomputable from mi_daily_closes at any time.
  Registered in scripts/preflight_db_updates.py (prepared against the real schema
  at deploy).
  WHAT IT WRITES. One UPDATE per board name filling the shelf columns on the rows the
  INSERT just wrote, matched on (alert_date, ticker, recorded_at) — live_tracker stamps
  `recorded_at` once and passes it to both calls. This UPDATE of columns the INSERT
  leaves NULL is the ONE exception to "append-only"; it never touches another column.
  The INSERT below is unchanged, so a shelf failure — or a missing shelf column — can
  never cost the six-way row.
  THE DATA. `mi_daily_closes`, the table the evidence itself was computed from
  (scripts/probes/_594_sample10_1121/q2_bars.sql), bars STRICTLY BEFORE the alert
  date (the feature reads no bar on or after the gap day), bounded to
  SHELF_BARS_LOOKBACK_DAYS calendar days — more than the 355 sessions the rule can
  reach. A name whose last bar is not the table's latest session before the alert
  date gets NULL with `stale_last_bar(...)` rather than a number off shifted
  sessions.
  RAW INPUTS RECORDED: shelf_dmin, shelf_price, shelf_date, shelf_structure,
  shelf_adr20_pct, shelf_asof (the last bar used) and shelf_null (why there is no
  number: thin history, fewer than two pullback lows, a bad bar, a stale last bar).
  A name is ranked on its dmin whatever shelf_structure says (the evidence scored
  them that way). When NO board name has a number, rank_shelf stays NULL for all —
  an all-NULL board ranked would be the alphabet posing as a ranking.
  FAIL DIRECTION. Any error or the timeout: the shelf columns stay NULL, loudly
  (logger.exception + a `slot_rank_shelf_failed` audit row). SILENT otherwise.

SCHEMA. Every column the INSERT and the shelf UPDATE name is created by db.py's
`initialize_schema` at boot (`ADD COLUMN IF NOT EXISTS` beside the table's CREATE).
`mi_ep_slot_rank_shadow` is registered in `health_checks._DETECTOR_LIVENESS_TABLES`
so a dark table is not silent forever.

$0 AT RUNTIME — one small mi_stock_scores fetch (done by live_tracker, shared with
the acting sort so acting and recorded RS can never drift) + one mi_themes fetch
here + the shelf step's one bounded mi_daily_closes fetch after the entries are
done; no LLM, no API call. The recorder is fail-open (log only, returns 0) and its
table is read by NO grading / entry / sizing / safeguard path — comparison telemetry
only (the ep_shortlist_shadow contract). SILENT: no Telegram, ever; liveness is
watched by `health_checks._DETECTOR_LIVENESS_TABLES`.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Module-level for test patchability (the ep_shortlist_shadow convention) — but the
# writer takes the caller's POOL, so the money path's mocked pool bounds every read
# and write this module makes during that call.
from agents.market_intelligence.db import get_pool  # noqa: E402  (kept for parity/tests)

# The briefing's OWN composite sort key — imported, never copied, so rank_composite
# tracks whatever the briefing actually does (it IS the "briefing composite"
# candidate). _THEME_BONUS strength order is reused for strongest-stage-per-ticker.
from agents.market_intelligence.briefing import _ep_composite_key, _THEME_BONUS  # noqa: E402

# The shelf distance's ONE definition (shared with the analysis scripts, #594).
from agents.market_intelligence.shelf_distance import shelf_distance_from_prior_days  # noqa: E402

# Which orderings the watch records. Frozen tuple so a rename/drop breaks the pin in
# tests/test_533_slot_ranking.py instead of silently shrinking the record.
SLOT_RANK_KEYS: tuple[str, ...] = (
    "rank_rs", "rank_ep_score", "rank_composite", "rank_adv", "rank_alpha",
    "rank_vol_pct", "rank_shelf",
)

# ── the shelf step (#594) — see THE SHELF STEP in the module docstring ────────
# The whole step (bars fetch + compute + UPDATE) is cancelled after this long.
SHELF_STEP_TIMEOUT_SEC = 5.0
# The step's reads/write never start before this ET time on the alert date — one
# minute after the ORB submission window shuts (09:45), so it can never share the
# pool with an entry.
SHELF_NOT_BEFORE_ET = time(9, 46)
_ET = ZoneInfo("America/New_York")


def _now_et() -> datetime:
    """Seam for tests (a fake clock)."""
    return datetime.now(_ET)


async def _sleep(seconds: float) -> None:
    """Seam for tests (a fake clock)."""
    await asyncio.sleep(seconds)


def seconds_until_shelf_may_run(alert_date: date, now_et: datetime) -> float:
    """Seconds from `now_et` to SHELF_NOT_BEFORE_ET on `alert_date` (ET); 0.0 when
    that moment has passed. Pure."""
    not_before = datetime.combine(alert_date, SHELF_NOT_BEFORE_ET, tzinfo=_ET)
    return max(0.0, (not_before - now_et).total_seconds())


# Calendar days of bars fetched per name: ~550 sessions, above the 355 the rule can
# reach and the 504 the labelled evidence was computed on (deeper cannot change it).
SHELF_BARS_LOOKBACK_DAYS = 800
# Strong refs — a bare create_task can be garbage-collected mid-flight.
_SHELF_TASKS: "set[asyncio.Task]" = set()


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
    the six candidate orderings (see module docstring). Pure — no I/O.

    Every ordering ends in ticker ASC so each is a reproducible total order,
    never an input-order lottery (the Stage-0 nine-way-tie lesson)."""

    def _rs(t: str) -> dict:
        return rs_by_ticker.get(t) or {}

    def _adv_dollar(t: str) -> "float | None":
        adv, close = _rs(t).get("adv_20"), _rs(t).get("close")
        return float(adv) * float(close) if adv and close else None

    def _eps(a: dict) -> float:
        return float(a.get("ep_score") or 0.0)

    def _vol_pct(a: dict) -> "float | None":
        # Raw input carried straight off the alert row — ep_detector already
        # computed and persisted this per candidate (mi_ep_alerts.vol_percentile,
        # #605). No new query, no re-derivation.
        v = a.get("vol_percentile")
        return float(v) if v is not None else None

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
    # Nulls-last, same shape as rank_adv above: no reading earns no priority over
    # an evidenced one, but the name is never dropped from the permutation.
    rank_vol_pct = _rank_from_key(alerts, lambda a: (
        0 if _vol_pct(a) is not None else 1,
        -(_vol_pct(a) or 0.0),
        -_eps(a),
        a["ticker"],
    ))

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
            "vol_percentile": _vol_pct(a),
            # the decision record (what each ordering did on THIS board):
            "rank_rs": rank_rs[t],
            "rank_ep_score": rank_ep_score[t],
            "rank_composite": rank_composite[t],
            "rank_adv": rank_adv[t],
            "rank_alpha": rank_alpha[t],
            "rank_vol_pct": rank_vol_pct[t],
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
                    r["vol_percentile"],
                    r["rank_rs"], r["rank_ep_score"], r["rank_composite"],
                    r["rank_adv"], r["rank_alpha"], r["rank_vol_pct"],
                    r["acting_key"],
                )
                for r in rows
            ])
        return len(rows)
    except Exception as e:  # loud-ok: comparison telemetry only — never blocks the entry path
        logger.warning(f"slot-rank shadow: snapshot write failed — {e}")
        return 0


# The row's ONE INSERT — unchanged by the shelf step (#594), which fills its own
# columns afterwards with _SHELF_UPDATE_SQL so it can never cost this row.
_INSERT_SQL = """
    INSERT INTO mi_ep_slot_rank_shadow (
        alert_date, ticker, recorded_at, trigger, board_n,
        ep_score, gap_pct, rs_composite, rs_rank, rs_score_date,
        adv_20, score_close, theme_stage, vol_percentile,
        rank_rs, rank_ep_score, rank_composite, rank_adv, rank_alpha, rank_vol_pct,
        acting_key
    ) VALUES ($1,$2,$3,$4,$5, $6,$7,$8,$9,$10, $11,$12,$13,$14, $15,$16,$17,$18,$19,$20, $21)
"""


# ── the shelf step (#594): the seventh ranking, RECORDS ONLY ──────────────────

_SHELF_LATEST_SESSION_SQL = """
    SELECT MAX(trade_date) FROM mi_daily_closes
    WHERE trade_date < $1 AND trade_date >= $2
"""

# Prior-day bars only (trade_date < the alert date), date-bounded (the #594 read-site rule).
_SHELF_BARS_SQL = """
    SELECT ticker, trade_date, open_price, high_price, low_price, close, volume
    FROM mi_daily_closes
    WHERE ticker = ANY($1) AND trade_date < $2 AND trade_date >= $3
    ORDER BY ticker, trade_date
"""

# Fills ONLY the shelf columns on the rows this invocation's INSERT wrote.
_SHELF_UPDATE_SQL = """
    UPDATE mi_ep_slot_rank_shadow
    SET shelf_dmin = $4, shelf_price = $5, shelf_date = $6, shelf_structure = $7,
        shelf_null = $8, shelf_adr20_pct = $9, shelf_asof = $10, rank_shelf = $11
    WHERE alert_date = $1 AND ticker = $2 AND recorded_at = $3
"""


def rank_board_by_shelf(
    tickers: list[str], dmin_by_ticker: dict[str, "float | None"],
) -> dict[str, "int | None"]:
    """Ticker -> 1-based rank by shelf distance: dmin DESC, no reading last, ticker
    ASC tiebreak. Pure. When NO name has a reading every rank is None — an all-NULL
    board ranked would be the alphabet posing as a ranking."""
    if all(dmin_by_ticker.get(t) is None for t in tickers):
        return {t: None for t in tickers}
    ordered = sorted(tickers, key=lambda t: (
        0 if dmin_by_ticker.get(t) is not None else 1,
        -(float(dmin_by_ticker[t]) if dmin_by_ticker.get(t) is not None else 0.0),
        t,
    ))
    return {t: i + 1 for i, t in enumerate(ordered)}


def compute_shelf_rows(
    tickers: list[str], bars_by_ticker: dict[str, list],
    latest_session: "date | None",
) -> list[dict]:
    """One dict per board name: the shelf raw inputs + rank_shelf. Pure — no I/O.
    `bars_by_ticker[t]` = daily (date, o, h, l, c, v) oldest-first, all before the
    alert date. A name with no bars, or whose last bar is not `latest_session`, gets
    no number and a reason — never a number computed off shifted sessions."""
    feats: dict[str, dict] = {}
    for t in tickers:
        days = bars_by_ticker.get(t) or []
        if not days:
            feats[t] = {"null": "no_bars"}
        elif latest_session is not None and days[-1][0] != latest_session:
            feats[t] = {"null": f"stale_last_bar({days[-1][0]}<{latest_session})",
                        "asof": days[-1][0]}
        else:
            feats[t] = shelf_distance_from_prior_days(days)
    ranks = rank_board_by_shelf(tickers, {t: feats[t].get("dmin") for t in tickers})
    return [{
        "ticker": t,
        "shelf_dmin": feats[t].get("dmin"),
        "shelf_price": feats[t].get("shelf"),
        "shelf_date": feats[t].get("shelf_date"),
        "shelf_structure": feats[t].get("structure"),
        "shelf_null": feats[t].get("null"),
        "shelf_adr20_pct": feats[t].get("adr"),
        "shelf_asof": feats[t].get("asof"),
        "rank_shelf": ranks[t],
    } for t in tickers]


async def _shelf_step(
    pool: Any, tickers: list[str], alert_date: date, recorded_at: datetime,
) -> int:
    floor = alert_date - timedelta(days=SHELF_BARS_LOOKBACK_DAYS)
    async with pool.acquire() as conn:
        latest_session = await conn.fetchval(
            _SHELF_LATEST_SESSION_SQL, alert_date, floor)
        bar_rows = await conn.fetch(_SHELF_BARS_SQL, tickers, alert_date, floor)
    # The connection is released before the arithmetic and re-taken for the write.
    bars: dict[str, list] = {}
    for r in bar_rows:
        bars.setdefault(r["ticker"], []).append((
            r["trade_date"], r["open_price"], r["high_price"], r["low_price"],
            r["close"], r["volume"],
        ))
    rows = compute_shelf_rows(tickers, bars, latest_session)
    async with pool.acquire() as conn:
        await conn.executemany(_SHELF_UPDATE_SQL, [
            (
                alert_date, r["ticker"], recorded_at,
                r["shelf_dmin"], r["shelf_price"], r["shelf_date"],
                r["shelf_structure"], r["shelf_null"], r["shelf_adr20_pct"],
                r["shelf_asof"], r["rank_shelf"],
            )
            for r in rows
        ])
    return len(rows)


async def record_shelf_ranks(
    pool: Any, tickers: list[str], alert_date: date, recorded_at: datetime,
    trigger: str = "",
) -> int:
    """The shelf step's entry point (#594) — fills rank_shelf + its raw inputs on the
    rows `snapshot_slot_rank_board` wrote for this invocation. RECORDS ONLY. Never
    raises. It does not touch the pool before SHELF_NOT_BEFORE_ET (09:46 ET) on the
    alert date — it sleeps until then; after that its reads + write are bounded by
    SHELF_STEP_TIMEOUT_SEC. On any error or the timeout the shelf columns stay
    NULL, loudly (logger.exception + `slot_rank_shelf_failed` audit row). Returns
    names written (0 on failure). SILENT — no Telegram on any path."""
    try:
        if not tickers:
            return 0
        wait = seconds_until_shelf_may_run(alert_date, _now_et())
        if wait > 0:
            await _sleep(wait)
        return await asyncio.wait_for(
            _shelf_step(pool, list(tickers), alert_date, recorded_at),
            timeout=SHELF_STEP_TIMEOUT_SEC,
        )
    except Exception as e:  # loud-ok: records-only telemetry — shelf columns stay NULL; audit row below
        logger.exception(
            f"slot-rank shelf [{trigger}]: step failed — shelf columns stay NULL "
            f"for {alert_date}: {type(e).__name__}: {e}")
        try:
            from agents.market_intelligence.db import log_audit_event
            await log_audit_event(
                "slot_rank_shelf_failed",
                f"[{trigger}] {alert_date} {type(e).__name__}: {str(e)[:200]}",
            )
        except Exception:  # loud-ok: log_audit_event never raises; belt+braces
            pass
        return 0


def schedule_shelf_ranks(
    pool: Any, tickers: list[str], alert_date: date, recorded_at: datetime,
    trigger: str = "",
) -> "asyncio.Task | None":
    """Start `record_shelf_ranks` as a detached task and return at once — the caller
    never waits on it. Never raises (returns None when it could not be started)."""
    try:
        task = asyncio.get_running_loop().create_task(
            record_shelf_ranks(pool, tickers, alert_date, recorded_at, trigger))
        _SHELF_TASKS.add(task)
        task.add_done_callback(_SHELF_TASKS.discard)
        return task
    except Exception as e:  # loud-ok: records-only telemetry — never blocks the entry path's return
        logger.warning(f"slot-rank shelf [{trigger}]: could not start the step — {e}")
        return None
