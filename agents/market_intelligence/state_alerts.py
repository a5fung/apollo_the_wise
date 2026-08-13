"""
State-change alerts — detect meaningful changes in RS, themes, and technicals.

Fires after the nightly data pull, separate from evening briefing.
Alerts arrive ~4:30-5:00 PM ET via Telegram.

#479 (operator-specified 2026-08-12): THE MESSAGE IS ABOUT THEMES. It surfaces
only material theme changes — new themes, positive stage acceleration,
shadow→live graduations, GROUP-level RS deterioration, stage-downs, retirements.
Per-name RS deterioration, MA breaks, theme-composition churn, and nascent churn
are COLLAPSED to on-demand (never deleted — the 7/20 orphaning lesson): each is
written to mi_audit_log every night and reachable via the EXISTING audit-log
command ("show logs" / "audit log deterioration" / "audit log ma breaks");
composition state itself lives on `/themes`.

Noise thresholds (detection layer, unchanged):
- RS deterioration: drop > 15 points in ~10 trading days
- Theme transitions: only genuine stage changes (ticker-overlap matching to handle renames)
- MA breaks: RS >= 60, volume >= 1.5x ADV, only 20MA and 50MA
- Theme composition: only RS 70+ stocks joining/leaving
"""
from __future__ import annotations

import logging
import math
from datetime import date, timedelta

from agents.market_intelligence.collector import et_today
from agents.market_intelligence.db import get_pool, log_audit_event

logger = logging.getLogger(__name__)

# Minimum ticker overlap to consider two themes "the same" despite name differences
_THEME_MATCH_OVERLAP = 0.5  # 50% of tickers in common

# ── #479 group-deterioration rule (DERIVED, not picked — 2026-08-13) ──────────
# Operator rule: a single name deteriorating (DDOG alone) is a stock story —
# NOISE. Several names in the SAME theme deteriorating together is a theme
# story — SIGNAL. The threshold was derived from 89 trading days of prod data
# (2026-04-06..08-12, 3,902 theme-days, 929 distinct theme tickers):
#   * The per-name rule (drop > 15 RS in ~2wk) fires on 21% of theme members on
#     an AVERAGE day (high-RS names mean-revert) — so a raw count threshold is
#     chance-dominated at EVERY k: k≥2 lift 1.0x, k≥3 lift 1.1x, k≥4 lift 1.5x
#     vs a Binomial(n, day-base-rate) null. A fixed k alone cannot be justified
#     — chance scales with theme size and how red the whole tape is that day.
#   * The justified rule conditions on both: ≥3 names AND the binomial tail
#     P(X ≥ x | n members, day's base rate) ≤ 0.02. Measured: 1.69 fires/day
#     observed vs 0.16/day under the simulated null → 10.4x lift; 26 of 90
#     days fire zero. Fired examples are whole groups (Truckload carriers 7/7,
#     Network Security 9/9, Regional Banks 18/19) — exactly the operator's ask.
# Derivation capture: session scratchpad 2026-08-13; inputs mi_themes +
# mi_stock_scores, deterioration definition identical to _check_rs_deterioration.
_CLUSTER_MIN_NAMES = 3      # a "group" is ≥3 co-deteriorating members
_CLUSTER_MAX_CHANCE = 0.02  # binomial tail bound vs the day's base rate
_RS_DROP_POINTS = 15.0      # the signed per-name deterioration rule (unchanged)


def _binom_tail(n: int, p: float, k: int) -> float:
    """P(X >= k) for X ~ Binomial(n, p). Exact sum — n is a theme size (small)."""
    if k <= 0:
        return 1.0
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    return sum(math.comb(n, i) * p**i * (1.0 - p) ** (n - i) for i in range(k, n + 1))


async def _fetch_theme_pair(today: date) -> tuple[list[dict], list[dict]]:
    """Fetch today's and prior day's themes once for reuse across checks."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        prior_date_row = await conn.fetchrow("""
            SELECT DISTINCT theme_date FROM mi_themes
            WHERE theme_date < $1
            ORDER BY theme_date DESC LIMIT 1
        """, today)
        if not prior_date_row:
            return [], []
        prior_date = prior_date_row["theme_date"]

        today_rows = await conn.fetch(
            "SELECT name, stage, tickers FROM mi_themes WHERE theme_date = $1", today
        )
        prior_rows = await conn.fetch(
            "SELECT name, stage, tickers FROM mi_themes WHERE theme_date = $1", prior_date
        )
    return [dict(r) for r in today_rows], [dict(r) for r in prior_rows]


async def detect_state_changes(
    trade_date: date | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Compare today's state to prior.

    Returns (alerts, today_themes, prior_themes) — themes are cached for
    reuse by send_state_alerts() to avoid redundant DB fetches.
    """
    today = trade_date or et_today()
    alerts: list[dict] = []

    # Fetch theme data once for all theme-related checks
    today_themes, prior_themes = await _fetch_theme_pair(today)

    try:
        alerts.extend(await _check_rs_deterioration(today))
    except Exception as e:
        logger.error(f"RS deterioration check failed: {e}")

    try:
        alerts.extend(_check_theme_transitions(today_themes, prior_themes))
    except Exception as e:
        logger.error(f"Theme transition check failed: {e}")

    try:
        alerts.extend(await _check_ma_breaks(today))
    except Exception as e:
        logger.error(f"MA break check failed: {e}")

    try:
        alerts.extend(await _check_theme_composition(today, today_themes, prior_themes))
    except Exception as e:
        logger.error(f"Theme composition check failed: {e}")

    try:
        alerts.extend(await _check_theme_rs_clusters(today, today_themes))
    except Exception as e:
        logger.error(f"Theme RS cluster check failed: {e}")

    return alerts, today_themes, prior_themes


async def _check_theme_rs_clusters(today: date, today_themes: list[dict]) -> list[dict]:
    """#479 group deterioration: for each of today's themes, count members whose
    RS dropped > _RS_DROP_POINTS vs ~10 trading days ago (same window as
    _check_rs_deterioration) and alert only when the co-deterioration beats
    chance for THAT theme size on THAT day: x >= _CLUSTER_MIN_NAMES and
    P(X >= x | n, day base rate) <= _CLUSTER_MAX_CHANCE. Derivation at the
    constants above. Population = theme members (not the tracked list) — the
    grouping IS the theme, per the operator's DDOG-in-software example."""
    if not today_themes:
        return []

    union: set[str] = set()
    for t in today_themes:
        union.update(t.get("tickers") or [])
    if not union:
        return []

    pool = await get_pool()
    async with pool.acquire() as conn:
        # $1::date casts are LOAD-BEARING (see _check_rs_deterioration).
        prior_date_row = await conn.fetchrow("""
            SELECT DISTINCT score_date FROM mi_stock_scores
            WHERE score_date <= $1::date - INTERVAL '12 days'
              AND score_date >= $1::date - INTERVAL '18 days'
            ORDER BY score_date DESC LIMIT 1
        """, today)
        if not prior_date_row:
            return []
        prior_date = prior_date_row["score_date"]

        today_scores = await conn.fetch("""
            SELECT ticker, rs_composite FROM mi_stock_scores
            WHERE score_date = $1 AND ticker = ANY($2) AND rs_composite IS NOT NULL
        """, today, list(union))
        today_map = {r["ticker"]: float(r["rs_composite"]) for r in today_scores}
        prior_scores = await conn.fetch("""
            SELECT ticker, rs_composite FROM mi_stock_scores
            WHERE score_date = $1 AND ticker = ANY($2) AND rs_composite IS NOT NULL
        """, prior_date, list(union))
        prior_map = {r["ticker"]: float(r["rs_composite"]) for r in prior_scores}

    return compute_rs_clusters(today_themes, today_map, prior_map)


def compute_rs_clusters(
    today_themes: list[dict],
    today_map: dict[str, float],
    prior_map: dict[str, float],
) -> list[dict]:
    """Pure #479 cluster rule (unit-tested; the async check above only fetches).
    x >= _CLUSTER_MIN_NAMES co-deteriorating members AND binomial-tail
    P(X >= x | n, day base rate) <= _CLUSTER_MAX_CHANCE."""
    union: set[str] = set()
    for t in today_themes:
        union.update(t.get("tickers") or [])
    eligible = [tk for tk in union if tk in today_map and tk in prior_map]
    if not eligible:
        return []
    deteriorated = {tk for tk in eligible if prior_map[tk] - today_map[tk] > _RS_DROP_POINTS}
    base_rate = len(deteriorated) / len(eligible)

    alerts: list[dict] = []
    for t in today_themes:
        members = [tk for tk in (t.get("tickers") or []) if tk in today_map and tk in prior_map]
        if len(members) < 2:
            continue
        hit = [tk for tk in members if tk in deteriorated]
        if len(hit) < _CLUSTER_MIN_NAMES:
            continue
        chance = _binom_tail(len(members), base_rate, len(hit))
        if chance > _CLUSTER_MAX_CHANCE:
            continue
        hit.sort(key=lambda tk: -(prior_map[tk] - today_map[tk]))
        alerts.append({
            "type": "theme_rs_deterioration",
            "theme": t["name"],
            "stage": t.get("stage"),
            "n_members": len(members),
            "names": [
                {"ticker": tk, "rs_prior": int(prior_map[tk]), "rs_now": int(today_map[tk]),
                 "drop": int(prior_map[tk] - today_map[tk])}
                for tk in hit
            ],
            "chance": chance,
        })
    alerts.sort(key=lambda a: a["chance"])
    return alerts


async def _check_rs_deterioration(today: date) -> list[dict]:
    """
    For active tracked stocks: compare today's rs_composite to 10 trading days ago.
    Alert if drop > 15 points.
    """
    pool = await get_pool()
    alerts = []

    async with pool.acquire() as conn:
        # $1::date casts are LOAD-BEARING: bare `$1 - INTERVAL` lets Postgres
        # type-infer $1 as interval → `date <= interval` prepare error
        # (caught 2026-06-10: RS-deterioration check silently dead).
        prior_date_row = await conn.fetchrow("""
            SELECT DISTINCT score_date FROM mi_stock_scores
            WHERE score_date <= $1::date - INTERVAL '12 days'
              AND score_date >= $1::date - INTERVAL '18 days'
            ORDER BY score_date DESC LIMIT 1
        """, today)
        if not prior_date_row:
            return []
        prior_date = prior_date_row["score_date"]

        tracked = await conn.fetch(
            "SELECT ticker FROM mi_tracked_stocks WHERE active = TRUE AND (quote_type IS NULL OR quote_type = 'EQUITY')"
        )
        if not tracked:
            return []
        tickers = [r["ticker"] for r in tracked]

        today_scores = await conn.fetch("""
            SELECT ticker, rs_composite FROM mi_stock_scores
            WHERE score_date = $1 AND ticker = ANY($2) AND rs_composite IS NOT NULL
        """, today, tickers)
        today_map = {r["ticker"]: r["rs_composite"] for r in today_scores}

        prior_scores = await conn.fetch("""
            SELECT ticker, rs_composite FROM mi_stock_scores
            WHERE score_date = $1 AND ticker = ANY($2) AND rs_composite IS NOT NULL
        """, prior_date, tickers)
        prior_map = {r["ticker"]: r["rs_composite"] for r in prior_scores}

        for ticker in tickers:
            if ticker in today_map and ticker in prior_map:
                drop = prior_map[ticker] - today_map[ticker]
                if drop > 15:
                    alerts.append({
                        "type": "rs_deterioration",
                        "ticker": ticker,
                        "rs_now": int(today_map[ticker]),
                        "rs_prior": int(prior_map[ticker]),
                        "drop": int(drop),
                    })

    return alerts


def _match_themes_by_tickers(
    today_themes: list[dict],
    prior_themes: list[dict],
) -> dict[str, str]:
    """
    Match today's themes to prior themes by ticker overlap, not name.
    Returns {today_name: prior_name} for matched themes.
    Handles the theme engine renaming themes via Claude each day.
    """
    matches: dict[str, str] = {}
    used_prior: set[str] = set()

    for t in today_themes:
        today_tickers = set(t.get("tickers") or [])
        if not today_tickers:
            continue

        best_match = None
        best_overlap = 0.0

        for p in prior_themes:
            p_name = p["name"]
            if p_name in used_prior:
                continue
            prior_tickers = set(p.get("tickers") or [])
            if not prior_tickers:
                continue

            intersection = len(today_tickers & prior_tickers)
            # Overlap = fraction of the smaller set that's shared
            overlap = intersection / min(len(today_tickers), len(prior_tickers))

            if overlap > best_overlap:
                best_overlap = overlap
                best_match = p_name

        if best_match and best_overlap >= _THEME_MATCH_OVERLAP:
            matches[t["name"]] = best_match
            used_prior.add(best_match)

    return matches


def _check_theme_transitions(
    today_themes: list[dict], prior_themes: list[dict],
) -> list[dict]:
    """
    Compare today's themes to yesterday's using ticker-overlap matching.
    Only alert on genuine stage changes, not theme renames.
    """
    if not today_themes or not prior_themes:
        return []

    name_map = _match_themes_by_tickers(today_themes, prior_themes)
    prior_stage_map = {t["name"]: t["stage"] for t in prior_themes}
    alerts = []

    for t in today_themes:
        today_name = t["name"]
        matched_prior = name_map.get(today_name)
        if not matched_prior:
            continue

        prior_stage = prior_stage_map.get(matched_prior)
        if prior_stage and prior_stage != t["stage"]:
            alerts.append({
                "type": "theme_transition",
                "theme": today_name,
                "from_stage": prior_stage,
                "to_stage": t["stage"],
            })

    return alerts


async def _check_ma_breaks(today: date) -> list[dict]:
    """
    For active tracked stocks with RS >= 60:
    - Today: close < sma_20 (or sma_50)
    - Yesterday: close >= sma_20 (or sma_50) — broke TODAY
    - Volume today > 1.5x ADV-20
    """
    pool = await get_pool()
    alerts = []

    async with pool.acquire() as conn:
        prior_date_row = await conn.fetchrow("""
            SELECT DISTINCT score_date FROM mi_stock_scores
            WHERE score_date < $1
            ORDER BY score_date DESC LIMIT 1
        """, today)
        if not prior_date_row:
            return []
        prior_date = prior_date_row["score_date"]

        tracked = await conn.fetch(
            "SELECT ticker FROM mi_tracked_stocks WHERE active = TRUE AND (quote_type IS NULL OR quote_type = 'EQUITY')"
        )
        if not tracked:
            return []
        tickers = [r["ticker"] for r in tracked]

        today_data = await conn.fetch("""
            SELECT ticker, rs_composite, close, sma_20, sma_50, adv_20
            FROM mi_stock_scores
            WHERE score_date = $1 AND ticker = ANY($2)
              AND rs_composite >= 60
              AND close IS NOT NULL
        """, today, tickers)

        prior_data = await conn.fetch("""
            SELECT ticker, close, sma_20, sma_50
            FROM mi_stock_scores
            WHERE score_date = $1 AND ticker = ANY($2) AND close IS NOT NULL
        """, prior_date, tickers)
        prior_map = {r["ticker"]: dict(r) for r in prior_data}

        today_vol = await conn.fetch("""
            SELECT ticker, volume FROM mi_daily_closes
            WHERE trade_date = $1 AND ticker = ANY($2) AND volume > 0
        """, today, tickers)
        vol_map = {r["ticker"]: r["volume"] for r in today_vol}

        for row in today_data:
            ticker = row["ticker"]
            close = row["close"]
            prior = prior_map.get(ticker)
            if not prior:
                continue

            adv = row["adv_20"] or 0
            today_volume = vol_map.get(ticker, 0)
            vol_ratio = today_volume / adv if adv > 0 else 0

            if vol_ratio < 1.5:
                continue

            for ma_col, ma_label in [("sma_20", "20MA"), ("sma_50", "50MA")]:
                today_ma = row[ma_col]
                prior_ma = prior.get(ma_col)
                prior_close = prior.get("close")

                if not today_ma or not prior_ma or not prior_close:
                    continue

                if prior_close >= prior_ma and close < today_ma:
                    alerts.append({
                        "type": "ma_break",
                        "ticker": ticker,
                        "ma": ma_label,
                        "rs": int(row["rs_composite"]),
                        "vol_ratio": round(vol_ratio, 1),
                    })

    return alerts


async def _check_theme_composition(
    today: date, today_themes: list[dict], prior_themes: list[dict],
) -> list[dict]:
    """
    For each theme on both today and yesterday:
    - Match themes by ticker overlap (handles renames)
    - Compare tickers[] arrays
    - Alert for RS 70+ stocks joining/leaving
    """
    if not today_themes or not prior_themes:
        return []

    name_map = _match_themes_by_tickers(today_themes, prior_themes)
    prior_ticker_map = {t["name"]: set(t.get("tickers") or []) for t in prior_themes}

    # Get RS scores for filtering
    all_tickers = set()
    for t in today_themes:
        all_tickers.update(t.get("tickers") or [])
    for tks in prior_ticker_map.values():
        all_tickers.update(tks)

    if not all_tickers:
        return []

    pool = await get_pool()
    async with pool.acquire() as conn:
        rs_rows = await conn.fetch("""
            SELECT ticker, rs_composite FROM mi_stock_scores
            WHERE score_date = $1 AND ticker = ANY($2) AND rs_composite IS NOT NULL
        """, today, list(all_tickers))
    rs_map = {r["ticker"]: r["rs_composite"] for r in rs_rows}

    alerts = []
    for t in today_themes:
        today_name = t["name"]
        matched_prior = name_map.get(today_name)
        if not matched_prior:
            continue

        today_set = set(t.get("tickers") or [])
        prior_set = prior_ticker_map.get(matched_prior, set())

        added = today_set - prior_set
        removed = prior_set - today_set

        added_strong = [tk for tk in added if rs_map.get(tk, 0) >= 70]
        removed_strong = [tk for tk in removed if rs_map.get(tk, 0) >= 70]

        if added_strong or removed_strong:
            alerts.append({
                "type": "theme_composition",
                "theme": today_name,
                "added": sorted(added_strong),
                "removed": sorted(removed_strong),
            })

    return alerts


def _esc_md(s: str) -> str:
    """Strip Markdown entity chars from free text (theme names) — one bare `_`
    flips the entity parity of the whole Telegram chunk (#477 class)."""
    return (s or "").replace("*", "").replace("_", "").replace("`", "").replace("[", "").replace("]", "").strip()


def format_state_alerts(
    alerts: list[dict],
    theme_changelog: list[dict],
    renamed_themes: dict[str, str],
    today_themes: list[dict] | None = None,
) -> tuple[str | None, dict]:
    """#479 pure formatter: (message text or None, suppressed-detail dict).

    THE MESSAGE = material THEME changes only (operator-specified 2026-08-12):
    new themes · positive stage acceleration · shadow→live graduations ·
    GROUP-level RS deterioration (cluster rule, singletons suppressed) ·
    stage-downs · retirements. Formatting: bullets, blank line between
    sections, every drill-down at the END of its own line, no pipe tables.

    SUPPRESSED (returned for the caller to persist to mi_audit_log — collapsed
    to on-demand, never deleted): per-name RS deterioration, MA breaks,
    composition adds/prunes, nascent churn counts.
    """
    theme_changelog = theme_changelog or []

    # Group alerts by type
    rs_alerts = [a for a in alerts if a["type"] == "rs_deterioration"]
    theme_alerts = [a for a in alerts if a["type"] == "theme_transition"]
    ma_alerts = [a for a in alerts if a["type"] == "ma_break"]
    comp_alerts = [a for a in alerts if a["type"] == "theme_composition"]
    cluster_alerts = [a for a in alerts if a["type"] == "theme_rs_deterioration"]
    graduated = [c for c in theme_changelog if c["type"] == "theme_graduated"]

    # Group changelog by type — filter out rename noise
    all_renamed_names = set(renamed_themes.keys()) | set(renamed_themes.values())

    pruned = [c for c in theme_changelog if c["type"] == "ticker_pruned"
              and c.get("theme") not in all_renamed_names]
    assigned = [c for c in theme_changelog if c["type"] == "ticker_assigned"
                and c.get("theme") not in all_renamed_names]
    new_themes = [c for c in theme_changelog if c["type"] == "theme_new"
                  and c.get("theme") not in renamed_themes]
    retired_themes = [c for c in theme_changelog if c["type"] == "theme_retired"
                      and c.get("theme") not in renamed_themes.values()]

    # Suppress same-run round-trips: when a (theme, ticker) appears in BOTH assigned and
    # pruned within one run (post-assignment validation reverses the LLM's call), the net
    # DB state is unchanged. Surfacing both lines is pure noise.
    assigned_keys = {(c["theme"], c["ticker"]) for c in assigned}
    pruned_keys = {(c["theme"], c["ticker"]) for c in pruned}
    round_trip_keys = assigned_keys & pruned_keys
    if round_trip_keys:
        assigned = [c for c in assigned if (c["theme"], c["ticker"]) not in round_trip_keys]
        pruned = [c for c in pruned if (c["theme"], c["ticker"]) not in round_trip_keys]
        logger.info(f"State alerts: suppressed {len(round_trip_keys)} same-run round-trip(s)")

    # Stage-gate: itemize changes only for Mainstream/Accelerating themes —
    # these are tradeable. Nascent membership churn is expected and non-actionable;
    # its counts roll into the churn audit row (#479). theme_new/theme_retired stay
    # unfiltered (creation/retirement of any theme is signal regardless of stage).
    today_stage_map = {t["name"]: t.get("stage") for t in (today_themes or [])}
    _SURFACE_STAGES = {"Mainstream", "Accelerating"}

    def _is_actionable(theme_name: str) -> bool:
        # Default to True when we don't know the stage (stay safe — surface the change).
        stage = today_stage_map.get(theme_name)
        if stage is None:
            return True
        return stage in _SURFACE_STAGES

    nascent_pruned_count = sum(1 for c in pruned if not _is_actionable(c["theme"]))
    nascent_assigned_count = sum(1 for c in assigned if not _is_actionable(c["theme"]))
    pruned = [c for c in pruned if _is_actionable(c["theme"])]
    assigned = [c for c in assigned if _is_actionable(c["theme"])]
    theme_alerts = [a for a in theme_alerts if _is_actionable(a["theme"])]
    comp_alerts = [a for a in comp_alerts if _is_actionable(a["theme"])]

    # Dedup: remove tickers from composition alerts already in changelog
    changelog_tickers = set()
    for c in pruned:
        changelog_tickers.add((c["theme"], c["ticker"], "removed"))
    for c in assigned:
        changelog_tickers.add((c["theme"], c["ticker"], "added"))

    if comp_alerts:
        deduped_comp = []
        for a in comp_alerts:
            added = [tk for tk in a.get("added", [])
                     if (a["theme"], tk, "added") not in changelog_tickers]
            removed = [tk for tk in a.get("removed", [])
                       if (a["theme"], tk, "removed") not in changelog_tickers]
            if added or removed:
                deduped_comp.append({**a, "added": added, "removed": removed})
        comp_alerts = deduped_comp

    # --- Render sections (#479: themes are the purpose; bullets; blank line
    # between sections; drill-down at the END of its own line) ---

    _stage_rank = {"Fading": 0, "Nascent": 1, "Mainstream": 2, "Accelerating": 3}
    positive = [a for a in theme_alerts
                if _stage_rank.get(a["to_stage"], 0) > _stage_rank.get(a["from_stage"], 0)]
    negative = [a for a in theme_alerts
                if _stage_rank.get(a["to_stage"], 0) < _stage_rank.get(a["from_stage"], 0)]

    lines = ["*THEMES — STATE CHANGES*"]

    if new_themes:
        lines.append("")
        lines.append("🆕 *New themes*")
        for a in new_themes[:10]:
            tks = a.get("tickers", [])
            tk_str = ", ".join(tks[:5]) + (f" +{len(tks) - 5}" if len(tks) > 5 else "")
            lines.append(f"• {_esc_md(a['theme'])} — {tk_str}")

    if positive:
        lines.append("")
        lines.append("⚡ *Accelerating (stage up)*")
        for a in positive[:10]:
            lines.append(f"• {_esc_md(a['theme'])}: {a['from_stage']} → {a['to_stage']}")

    if graduated:
        lines.append("")
        lines.append("🎓 *Graduated shadow→live*")
        for c in graduated[:10]:
            lines.append(f"• {_esc_md(c['theme'])}")

    if cluster_alerts:
        lines.append("")
        lines.append("📉 *Group deterioration — beyond chance for the day*")
        for a in cluster_alerts[:5]:
            names = a["names"]
            shown = " ".join(n["ticker"] for n in names[:4])
            more = f" +{len(names) - 4}" if len(names) > 4 else ""
            lines.append(
                f"• {_esc_md(a['theme'])}: {len(names)}/{a['n_members']} members "
                f"down >{_RS_DROP_POINTS:.0f} RS in 2wk — {shown}{more}"
            )
        if len(cluster_alerts) > 5:
            n_more = len(cluster_alerts) - 5
            lines.append(f"  _+{n_more} more theme{'s' if n_more != 1 else ''}_")

    if negative:
        lines.append("")
        lines.append("🔻 *Stage down*: " + " · ".join(
            f"{_esc_md(a['theme'])} ({a['from_stage']} → {a['to_stage']})"
            for a in negative[:10]))

    if retired_themes:
        lines.append("")
        lines.append("🪦 *Retired*: " + " · ".join(
            _esc_md(a["theme"]) for a in retired_themes[:10]))

    # Suppressed (collapsed-to-on-demand) detail — the caller persists it to
    # mi_audit_log so every cited command below actually holds the content.
    suppressed = {
        "rs_names": rs_alerts,
        "ma_breaks": ma_alerts,
        "assigned": assigned,
        "pruned": pruned,
        "composition": comp_alerts,
        "nascent_assigned": nascent_assigned_count,
        "nascent_pruned": nascent_pruned_count,
    }

    # Only send if there's actual content beyond the header
    if len(lines) <= 1:
        return None, suppressed

    # On-demand footer — every command verified against the live dispatch
    # (tests/test_state_alerts_479.py pins each one).
    lines.append("")
    lines.append(
        "_on demand: composition `/themes` · MA breaks \"audit log ma breaks\" · "
        "per-name RS drops \"audit log deterioration\" · churn \"show logs\"_"
    )
    return "\n".join(lines), suppressed


async def send_state_alerts(
    alerts: list[dict],
    theme_changelog: list[dict] | None = None,
    today_themes: list[dict] | None = None,
    prior_themes: list[dict] | None = None,
) -> None:
    """Format + send the themes state-change message, then persist the
    collapsed sections to mi_audit_log (#479: collapse ≠ delete — the audit
    rows are what "audit log deterioration" / "audit log ma breaks" /
    "show logs" surface on demand)."""
    from agents.market_intelligence.briefing import send_telegram_message

    theme_changelog = theme_changelog or []
    if not alerts and not theme_changelog:
        return

    # Detect theme renames from cached data (or fetch if not provided)
    if today_themes is not None and prior_themes is not None:
        renamed_themes = _match_themes_by_tickers(today_themes, prior_themes)
    else:
        renamed_themes = await _get_renamed_themes()

    text, suppressed = format_state_alerts(
        alerts, theme_changelog, renamed_themes, today_themes)

    # Persist collapsed detail FIRST — the on-demand surface must exist even if
    # the send fails (send_telegram_message returns False, never raises).
    try:
        await _persist_suppressed_detail(suppressed)
    except Exception as e:
        logger.error(f"State alerts: persisting suppressed detail failed: {e}")

    if text is None:
        logger.info("State changes: nothing material for the message "
                    "(collapsed detail persisted to audit log)")
        return
    await send_telegram_message(text)
    logger.info(f"Sent state-change message ({len(alerts)} alerts, "
                f"{len(theme_changelog)} changelog entries)")


async def _persist_suppressed_detail(suppressed: dict) -> None:
    """One audit row per collapsed section per night (only when non-empty).
    Event types are filterable via the EXISTING audit-log command
    (agent._handle_audit_log: "audit log deterioration" / "audit log ma breaks";
    unfiltered "show logs" lists them all)."""
    rs = suppressed.get("rs_names") or []
    if rs:
        items = " · ".join(
            f"{a['ticker']} {a['rs_prior']}→{a['rs_now']} (-{a['drop']})"
            for a in rs[:25])
        more = f" · +{len(rs) - 25} more" if len(rs) > 25 else ""
        await log_audit_event(
            "rs_deterioration",
            summary=f"RS deterioration (per-name, on-demand): {items}{more}",
        )
    ma = suppressed.get("ma_breaks") or []
    if ma:
        items = " · ".join(
            f"{a['ticker']} {a['ma']} {a['vol_ratio']}x (RS {a['rs']})" for a in ma[:25])
        more = f" · +{len(ma) - 25} more" if len(ma) > 25 else ""
        await log_audit_event(
            "ma_break",
            summary=f"MA breaks (on-demand): {items}{more}",
        )
    comp_bits = []
    for c in (suppressed.get("assigned") or [])[:25]:
        comp_bits.append(f"+{c['ticker']}→{c['theme']}")
    for c in (suppressed.get("pruned") or [])[:25]:
        comp_bits.append(f"-{c['ticker']} from {c['theme']}")
    for a in (suppressed.get("composition") or [])[:25]:
        adds = " ".join(f"+{tk}" for tk in a.get("added", []))
        rems = " ".join(f"-{tk}" for tk in a.get("removed", []))
        comp_bits.append(f"{a['theme']}: {adds} {rems}".strip())
    n_asn = suppressed.get("nascent_assigned") or 0
    n_prn = suppressed.get("nascent_pruned") or 0
    if comp_bits or n_asn or n_prn:
        await log_audit_event(
            "theme_composition_churn",
            summary=(f"Composition churn (on-demand): {' · '.join(comp_bits)}"
                     f" · nascent +{n_asn}/-{n_prn}").strip(" ·"),
        )


async def _get_renamed_themes() -> dict[str, str]:
    """Get {today_name: prior_name} for themes that were just renamed (high ticker overlap).
    Used to suppress noise in changelog."""
    today = et_today()
    pool = await get_pool()
    async with pool.acquire() as conn:
        prior_date_row = await conn.fetchrow("""
            SELECT DISTINCT theme_date FROM mi_themes
            WHERE theme_date < $1
            ORDER BY theme_date DESC LIMIT 1
        """, today)
        if not prior_date_row:
            return {}
        prior_date = prior_date_row["theme_date"]

        today_themes = await conn.fetch(
            "SELECT name, tickers FROM mi_themes WHERE theme_date = $1", today
        )
        prior_themes = await conn.fetch(
            "SELECT name, tickers FROM mi_themes WHERE theme_date = $1", prior_date
        )

    return _match_themes_by_tickers(
        [dict(r) for r in today_themes],
        [dict(r) for r in prior_themes],
    )
