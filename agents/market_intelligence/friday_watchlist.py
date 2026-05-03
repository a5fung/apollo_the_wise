"""Friday Curated Watchlist — weekly chart-review aggregator.

Combines best ideas from the week (EP HIGH, 9M sugar babies, themes,
wick fills, parabolic short, RS leaders) into a curated Telegram digest
with TradingView import block + per-ticker chart-link buttons.

Trade-idea radar — does NOT trigger entries. Apollo's auto-entry flow
unchanged.
"""

import logging
import os
from datetime import date, timedelta

import httpx

from agents.market_intelligence.collector import et_today, last_trading_day
from agents.market_intelligence.briefing import send_telegram_message
from agents.market_intelligence.db import (
    get_pool,
    get_ep_outcomes,
    get_eod_9m_sugar_babies,
    get_active_themes,
    get_rs_leaders,
    get_rs_for_tickers,
    get_wick_candidates_window,
    get_wick_pending_candidates,
    get_security_exchange_map,
    get_latest_regime,
    insert_weekly_watchlist,
)
from agents.market_intelligence.strategies.registry import should_run

logger = logging.getLogger(__name__)

# Lower priority value = higher precedence (drives section assignment + button order)
_PRIORITY = {
    "EP_HIGH":      1,
    "THEME":        2,
    "9M_SUGAR":     3,
    "WICK_PENDING": 4,
    "WICK":         5,
    "PARABOLIC":    6,
    "RS":           7,
}

# Forward-looking wick window — sessions, not calendar days. 3 sessions covers
# Mon→Wed visibility for a Friday wick without bleeding stale rows once the
# 5:45 PM sweep marks them filled/missed.
WICK_PENDING_LOOKBACK_SESSIONS = 3

# Polygon MIC -> TradingView prefix. Empty/missing -> omit prefix (TV resolves US equities).
_TV_EXCHANGE_MAP = {
    "XNYS": "NYSE",
    "XNAS": "NASDAQ",
    "ARCX": "AMEX",
    "BATS": "BATS",
    "IEXG": "IEX",
}

_MAX_TICKERS = 25
_MAX_KEYBOARD_BUTTONS = 8
_TG_SAFE_LIMIT = 3900  # margin under Telegram's 4096-char message ceiling

_SECTION_HEADERS = {
    "EP_HIGH":      ("⚡", "EP HIGH"),
    "9M_SUGAR":     ("🍬", "9M Sugar Babies"),
    "THEME":        ("🚀", "Themes — Accelerating"),
    "WICK_PENDING": ("🪝", "Wick Pending — break-of-prior-high"),
    "WICK":         ("🪝", "Wick Fill — settled w/ edge"),
    "PARABOLIC":    ("🚨", "Parabolic Climax"),
    "RS":           ("⭐", "Ambient RS Leaders"),
}


def _tv_prefix(mic: str) -> str:
    return _TV_EXCHANGE_MAP.get(mic, "")


def _tv_chart_url(ticker: str, mic: str) -> str:
    prefix = _tv_prefix(mic)
    sym = f"{prefix}:{ticker}" if prefix else ticker
    return f"https://www.tradingview.com/chart/?symbol={sym}"


def _tv_import_token(ticker: str, mic: str) -> str:
    prefix = _tv_prefix(mic)
    return f"{prefix}:{ticker}" if prefix else ticker


def _ep_outcome_chip(r: dict) -> str:
    status = r.get("trade_status")
    if status == "traded":
        pnl = r.get("total_pnl")
        if pnl is not None:
            try:
                return f"entered {float(pnl):+,.0f}"
            except (TypeError, ValueError):
                return "entered"
        return "entered"
    if status == "filtered":
        from agents.market_intelligence.broker.skip_reasons import humanize
        reason = r.get("skip_reason") or ""
        if reason:
            label = humanize(reason)
            return f"missed: {label[:24]}"
        return "missed"
    return ""


# ── per-source curators ─────────────────────────────────────────────────


async def _fetch_ep_high(window_days: int) -> list[dict]:
    rows = await get_ep_outcomes(days_back=window_days, tier="HIGH")
    rows.sort(key=lambda r: float(r.get("ep_score") or 0), reverse=True)
    out: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        t = r["ticker"]
        if t in seen:
            continue
        seen.add(t)
        outcome = _ep_outcome_chip(r)
        d = r["alert_date"]
        ds = d.strftime("%a") if hasattr(d, "strftime") else str(d)
        price = float(r.get("last_entry_price") or 0)
        chip = f"EP HIGH {ds}"
        if price:
            chip += f" ${price:.2f}"
        if outcome:
            chip += f" ({outcome})"
        out.append({
            "ticker": t,
            "source_tag": "EP_HIGH",
            "reason": chip,
            "priority": _PRIORITY["EP_HIGH"],
            "rank_within": float(r.get("ep_score") or 0),
        })
        if len(out) >= 5:
            break
    return out


async def _fetch_9m_sugar(window_days: int) -> list[dict]:
    today = last_trading_day()
    candidates: list[tuple[date, dict]] = []
    for offset in range(window_days):
        d = today - timedelta(days=offset)
        rows = await get_eod_9m_sugar_babies(d)
        for r in rows:
            cirp = r.get("close_in_range_pct")
            if cirp is None or float(cirp) < 0.85:
                continue
            candidates.append((d, r))
    candidates.sort(key=lambda x: float(x[1].get("volume") or 0), reverse=True)
    out: list[dict] = []
    seen: set[str] = set()
    for d, r in candidates:
        t = r["ticker"]
        if t in seen:
            continue
        seen.add(t)
        shape = r.get("shape_tag") or ""
        ds = d.strftime("%a")
        chip = f"9M sugar baby {ds}"
        if shape:
            chip += f" · {shape}"
        out.append({
            "ticker": t,
            "source_tag": "9M_SUGAR",
            "reason": chip,
            "priority": _PRIORITY["9M_SUGAR"],
            "rank_within": float(r.get("volume") or 0),
        })
        if len(out) >= 5:
            break
    return out


async def _fetch_themes() -> tuple[list[dict], list[dict]]:
    """Top 3 Accelerating themes × top 2 RS tickers each.

    Returns (per_ticker_rows, theme_meta) where theme_meta is the
    section-card data (theme name + RS rank + display tickers).
    """
    themes = await get_active_themes(stale_after_days=7)
    accel = [t for t in themes if t.get("stage") == "Accelerating"]
    if not accel:
        return [], []

    today = et_today()
    scored: list[tuple[float, dict, dict]] = []
    for t in accel:
        tickers = t.get("tickers") or []
        if not tickers:
            continue
        rs_map = await get_rs_for_tickers(today, list(tickers))
        comps = [v["rs_composite"] for v in rs_map.values()
                 if v.get("rs_composite") is not None]
        if not comps:
            continue
        scored.append((sum(comps) / len(comps), t, rs_map))
    scored.sort(key=lambda x: -x[0])
    top3 = scored[:3]

    per_ticker: list[dict] = []
    theme_meta: list[dict] = []
    for avg_rs, t, rs_map in top3:
        ranked = sorted(
            rs_map.items(),
            key=lambda kv: -(kv[1].get("rs_composite") or 0),
        )
        theme_meta.append({
            "name": t["name"],
            "rs": int(round(avg_rs)),
            "top_tickers": [tk for tk, _ in ranked[:3]],
        })
        for tk, rs in ranked[:2]:
            per_ticker.append({
                "ticker": tk,
                "source_tag": "THEME",
                "reason": f"Theme: {t['name']} (RS {int(round(avg_rs))})",
                "priority": _PRIORITY["THEME"],
                "rank_within": float(rs.get("rs_composite") or 0),
            })
    return per_ticker, theme_meta


async def _fetch_wick_pending(lookback_sessions: int = WICK_PENDING_LOOKBACK_SESSIONS) -> list[dict]:
    """Forward-looking wicks: prior_high not yet broken, sweep hasn't closed
    the row. Actionable for next-session entry. Sibling of `_fetch_wick`,
    which surfaces *settled* outcome telemetry — both gated by the same
    `should_run("wick_fill")` strategy phase."""
    if not await should_run("wick_fill"):
        return []
    rows = await get_wick_pending_candidates(lookback_sessions)
    out: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        t = r["ticker"]
        if t in seen:
            continue
        seen.add(t)
        d = r.get("alert_date")
        ds = d.strftime("%b %d") if hasattr(d, "strftime") else str(d)
        prior_high = float(r.get("prior_high") or 0)
        out.append({
            "ticker": t,
            "source_tag": "WICK_PENDING",
            "reason": f"Pending {ds}: break > ${prior_high:.2f}",
            "priority": _PRIORITY["WICK_PENDING"],
            "rank_within": float(r.get("volume") or 0),
        })
        if len(out) >= 5:
            break
    return out


async def _fetch_wick(window_days: int) -> list[dict]:
    if not await should_run("wick_fill"):
        return []
    rows = await get_wick_candidates_window(window_days)
    settled = []
    for r in rows:
        if not r.get("filled_wick"):
            continue
        drift = r.get("fwd_3d_from_high_pct")
        if drift is None or float(drift) > -0.03:
            continue
        settled.append(r)
    settled.sort(key=lambda r: float(r.get("fwd_3d_from_high_pct") or 0))
    out: list[dict] = []
    seen: set[str] = set()
    for r in settled:
        t = r["ticker"]
        if t in seen:
            continue
        seen.add(t)
        d = r.get("alert_date")
        ds = d.strftime("%b %d") if hasattr(d, "strftime") else str(d)
        drift_pct = float(r.get("fwd_3d_from_high_pct") or 0) * 100
        out.append({
            "ticker": t,
            "source_tag": "WICK",
            "reason": f"Wick fill {ds} · {drift_pct:+.1f}% drift",
            "priority": _PRIORITY["WICK"],
            "rank_within": -drift_pct,
        })
        if len(out) >= 3:
            break
    return out


async def _fetch_parabolic(window_days: int) -> list[dict]:
    if not await should_run("parabolic_short"):
        return []
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT ON (ticker) ticker, scan_date, score, roc_5d, roc_20d
            FROM mi_parabolic_candidates
            WHERE stage = 'climax'
              AND scan_date >= CURRENT_DATE - $1::int
              AND excluded_reason IS NULL
            ORDER BY ticker, scan_date DESC, score DESC NULLS LAST
        """, window_days)
    rows = sorted(rows, key=lambda r: float(r["score"] or 0), reverse=True)
    out: list[dict] = []
    for r in rows[:3]:
        ds = r["scan_date"].strftime("%a")
        roc5 = float(r["roc_5d"] or 0)
        roc20 = float(r["roc_20d"] or 0)
        ratio = (roc5 / roc20) if roc20 else 0
        chip = f"Parabolic climax {ds}"
        if ratio:
            chip += f" · roc_5d {ratio:.1f}× roc_20d"
        out.append({
            "ticker": r["ticker"],
            "source_tag": "PARABOLIC",
            "reason": chip,
            "priority": _PRIORITY["PARABOLIC"],
            "rank_within": float(r["score"] or 0),
        })
    return out


async def _fetch_rs_ambient(exclude: set[str]) -> list[dict]:
    today = last_trading_day()
    leaders = await get_rs_leaders(today, limit=30, min_adv=500_000, min_price=10.0)
    out: list[dict] = []
    rank = 0
    for r in leaders:
        rank += 1
        t = r["ticker"]
        if t in exclude:
            continue
        sector = (r.get("sector") or "").strip() or "Unknown"
        out.append({
            "ticker": t,
            "source_tag": "RS",
            "reason": f"RS rank {rank} · sector: {sector}",
            "priority": _PRIORITY["RS"],
            "rank_within": float(r.get("rs_composite") or 0),
        })
        if len(out) >= 5:
            break
    return out


# ── cross-source dedup ──────────────────────────────────────────────────


def _merge_sources(buckets: list[list[dict]]) -> list[dict]:
    """One row per ticker. Primary = lowest-priority source seen.

    Returns rows sorted by (priority asc, rank_within desc).
    """
    by_ticker: dict[str, dict] = {}
    for bucket in buckets:
        for row in bucket:
            t = row["ticker"]
            existing = by_ticker.get(t)
            if existing is None:
                by_ticker[t] = {
                    "ticker": t,
                    "primary": row["source_tag"],
                    "all_sources": [(row["source_tag"], row["reason"])],
                    "priority": row["priority"],
                    "rank_within": row.get("rank_within", 0),
                }
            else:
                existing["all_sources"].append((row["source_tag"], row["reason"]))
                if row["priority"] < existing["priority"]:
                    existing["priority"] = row["priority"]
                    existing["primary"] = row["source_tag"]
                    existing["rank_within"] = row.get("rank_within", 0)
    return sorted(by_ticker.values(), key=lambda r: (r["priority"], -r["rank_within"]))


def _format_chip(row: dict) -> str:
    """`[primary detail] | [secondary] | [tertiary]` — primary first, dups dropped."""
    primary_tag = row["primary"]
    primary_seen = False
    parts: list[str] = []
    for tag, reason in row["all_sources"]:
        if tag == primary_tag and not primary_seen:
            parts.append(f"[{reason}]")
            primary_seen = True
        else:
            parts.append(f"[{reason}]")
    seen: set[str] = set()
    deduped: list[str] = []
    for p in parts:
        if p in seen:
            continue
        seen.add(p)
        deduped.append(p)
    return " | ".join(deduped)


# ── digest formatting ───────────────────────────────────────────────────


def _build_digest(
    week_ending: date,
    rows: list[dict],
    theme_meta: list[dict],
    regime: dict | None,
    partial_rs: bool,
) -> tuple[str, str, list[str]]:
    """Returns (body_text, tv_block, top_tickers_for_keyboard)."""
    week_start = week_ending - timedelta(days=4)
    header_date = f"{week_start.strftime('%b %d')} – {week_ending.strftime('%b %d')}"
    rcount = len(rows)
    sources_used = sorted({r["primary"] for r in rows})

    lines = [f"🗓️ *Apollo Watchlist — Week of {header_date}*"]

    if regime:
        rname = regime.get("regime") or "?"
        breadth = regime.get("breadth_pct_above_40ma")
        if breadth is not None:
            lines.append(
                f"_Regime: {rname} (RS breadth {int(breadth)}%) · "
                f"{rcount} tickers across {len(sources_used)} sources_"
            )
        else:
            lines.append(
                f"_Regime: {rname} · {rcount} tickers across {len(sources_used)} sources_"
            )
    else:
        lines.append(f"_{rcount} tickers across {len(sources_used)} sources_")

    if partial_rs:
        lines.append("_RS data refreshing — partial watchlist_")

    if rcount < 3:
        lines.append("")
        lines.append("_Quiet week — minimal high-conviction setups._")
        return "\n".join(lines), "", []

    by_primary: dict[str, list[dict]] = {}
    for r in rows:
        by_primary.setdefault(r["primary"], []).append(r)

    section_order = ["EP_HIGH", "9M_SUGAR", "THEME", "WICK_PENDING", "WICK", "PARABOLIC", "RS"]
    for src in section_order:
        if src == "THEME":
            if theme_meta:
                lines.append("")
                emoji, name = _SECTION_HEADERS[src]
                lines.append(f"{emoji} *{name}* ({len(theme_meta)})")
                for tm in theme_meta:
                    tickers_str = ", ".join(tm["top_tickers"])
                    lines.append(f"• *{tm['name']}* (RS {tm['rs']}): {tickers_str}")
            continue
        bucket = by_primary.get(src) or []
        if not bucket:
            continue
        lines.append("")
        emoji, name = _SECTION_HEADERS[src]
        if src == "RS":
            tickers_str = ", ".join(r["ticker"] for r in bucket)
            lines.append(f"{emoji} *{name}* ({len(bucket)})")
            lines.append(tickers_str)
            continue
        lines.append(f"{emoji} *{name}* ({len(bucket)})")
        for r in bucket:
            lines.append(f"• *{r['ticker']}* — {_format_chip(r)}")

    body = "\n".join(lines)

    tv_tokens = [r["_tv_token"] for r in rows[:_MAX_TICKERS]]
    tv_block = (
        "──────────────\n"
        "📋 *TradingView Import* (copy → Watchlist → Import):\n"
        f"`{','.join(tv_tokens)}`"
    )

    keyboard_tickers = [r["ticker"] for r in rows[:_MAX_KEYBOARD_BUTTONS]]
    return body, tv_block, keyboard_tickers


# ── delivery ────────────────────────────────────────────────────────────


async def _send_with_keyboard(text: str, keyboard: list[list[dict]]) -> bool:
    """Direct Bot API POST so reply_markup attaches in one shot."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    allowed = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
    ids = [x.strip() for x in allowed.split(",") if x.strip()]
    if not bot_token or not ids:
        logger.error("friday_watchlist: TELEGRAM env vars missing")
        return False
    chat_id = int(ids[0])
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
        "reply_markup": {"inline_keyboard": keyboard},
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage", json=payload
            )
            if r.status_code == 400:
                logger.warning(f"friday_watchlist Markdown 400: {r.text[:300]}")
                payload.pop("parse_mode", None)
                r2 = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage", json=payload
                )
                r2.raise_for_status()
            else:
                r.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"friday_watchlist send failed: {e}")
        return False


# ── main entrypoint ─────────────────────────────────────────────────────


async def run_friday_watchlist(window_days: int = 7, persist: bool = True) -> dict:
    """Aggregate, curate, render, deliver the Friday watchlist.

    Returns: {"row_count": int, "delivered": bool}.
    """
    week_ending = last_trading_day()

    pool = await get_pool()
    async with pool.acquire() as conn:
        running = await conn.fetchval("""
            SELECT 1 FROM mi_job_runs
            WHERE job_id = 'nightly_data_pull'
              AND status = 'running'
              AND started_at >= CURRENT_DATE
            LIMIT 1
        """)
        partial_rs = bool(running)

    ep_rows = await _fetch_ep_high(window_days)
    nm_rows = await _fetch_9m_sugar(window_days)
    th_rows, theme_meta = await _fetch_themes()
    wp_rows = await _fetch_wick_pending()
    wk_rows = await _fetch_wick(window_days)
    pb_rows = await _fetch_parabolic(window_days)

    pre_rs_tickers = {
        r["ticker"]
        for bucket in (ep_rows, nm_rows, th_rows, wp_rows, wk_rows, pb_rows)
        for r in bucket
    }
    rs_rows = await _fetch_rs_ambient(pre_rs_tickers)

    merged = _merge_sources([ep_rows, nm_rows, th_rows, wp_rows, wk_rows, pb_rows, rs_rows])
    merged = merged[:_MAX_TICKERS]

    tickers = [r["ticker"] for r in merged]
    ex_map = await get_security_exchange_map(tickers)
    for r in merged:
        mic = ex_map.get(r["ticker"], "")
        r["_tv_token"] = _tv_import_token(r["ticker"], mic)
        r["_tv_url"] = _tv_chart_url(r["ticker"], mic)

    regime = await get_latest_regime()

    body, tv_block, keyboard_tickers = _build_digest(
        week_ending, merged, theme_meta, regime, partial_rs
    )

    keyboard: list[list[dict]] = []
    if keyboard_tickers:
        url_by_ticker = {r["ticker"]: r["_tv_url"] for r in merged}
        row_a, row_b = [], []
        for i, t in enumerate(keyboard_tickers):
            btn = {"text": f"📈 {t}", "url": url_by_ticker[t]}
            (row_a if i < 4 else row_b).append(btn)
        if row_a:
            keyboard.append(row_a)
        if row_b:
            keyboard.append(row_b)

    if not tv_block:
        delivered = await send_telegram_message(body)
    elif len(body) + len(tv_block) + 2 <= _TG_SAFE_LIMIT:
        full = body + "\n\n" + tv_block
        if keyboard:
            delivered = await _send_with_keyboard(full, keyboard)
        else:
            delivered = await send_telegram_message(full)
    else:
        body_ok = await send_telegram_message(body)
        if keyboard:
            tv_ok = await _send_with_keyboard(tv_block, keyboard)
        else:
            tv_ok = await send_telegram_message(tv_block)
        delivered = bool(body_ok and tv_ok)

    if persist and merged:
        rows_to_persist = [
            {
                "ticker": r["ticker"],
                "sources": [tag for tag, _ in r["all_sources"]],
                "composite_priority": r["priority"],
                "reason_chip": _format_chip(r),
            }
            for r in merged
        ]
        try:
            await insert_weekly_watchlist(week_ending, rows_to_persist)
        except Exception as e:
            logger.exception(f"friday_watchlist persistence failed: {e}")

    return {"row_count": len(merged), "delivered": delivered}
