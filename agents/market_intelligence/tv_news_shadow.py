"""#210 — TradingView news cross-reference SHADOW (2026-09-06).

THE MOTIVATING CASE: BFLY 2026-06-18 (operator-labelled real EP twice; see
`docs/methodology/ep_reference_bfly_2026-06-18.md`). Our own analysis said "no concrete,
verifiable company-specific catalyst" and was ACCURATE about the corpus we held — the
Midjourney partnership catalyst (40 Ultrasound-on-Chip modules/system, $74M/5yr) went
out on Business Wire and none of our four feeds (Polygon, Alpaca, FMP, Perplexity)
carried it. TradingView's aggregated headline feed did (25 items / 7 providers for
BFLY, business_wire among them). The operator uses TradingView personally and has
directed it be used as a backup / cross-reference source, with safeguards — that
decision is taken; this module builds it.

THE QUESTION THIS ANSWERS IN A MONTH: "on the days we found no catalyst, did
TradingView have one?" Single SQL, self-contained (no join needed):

    SELECT ticker, alert_date, tv_items_on_alert_date, tv_providers_on_alert_date,
           tv_items_we_missed
    FROM mi_tv_news_shadow
    WHERE tv_status = 'ok'
      AND tv_coverage_reaches_alert_date = true
      AND tv_items_on_alert_date > 0
    ORDER BY alert_date DESC;

🛑 THE LINE — DATA CAPTURE ONLY. Writes exactly ONE table (`mi_tv_news_shadow`) plus
`mi_audit_log` via the shared `log_audit_event`/`alert_endpoint_shape_anomaly`
telemetry helpers — never a grade, score, admission, or trade-state table. Read by NO
grading / entry / sizing / ordering / safeguard path. Acting on this later (feeding a
TradingView-sourced item into a live grade) is a separate CHANGE_PROCESS step with
operator sign-off — nothing here does that.

NEVER ON THE LIVE SCAN PATH. This is a POST-HOC NIGHTLY job (20:45 ET, mon-fri —
after every 18:xx EOD recorder and the 21:00 evening position backstop, before the
21:30 ET `#625` late silent-error sweep, and clear of the 21:15-22:15 ET after-hours
deploy window so a mid-run market-agent restart can't clip it). It never runs during
07:00-10:00 ET (the scan) or 09:31-09:44 ET (the ORB submission window) — there is no
latency budget question because it structurally cannot collide with either.

FAIL OPEN, ALWAYS. Every branch below — a non-200, a timeout, an unresolved exchange,
a malformed/absent `items` key, a JSON decode failure — degrades to a RECORDED reason
(`tv_status` + `tv_skip_reason`, or a run-level audit event) and moves on. Nothing here
ever raises into the scheduler; `run_tv_news_shadow` is the one function the job caller
touches and it is wrapped end to end.

THE BACKUP PLAN, PLAINLY (operator addendum, 2026-09-06: "make sure ... we know
immediately and have a backup plan"). This IS the backup plan's honest shape, because
it is a SHADOW that changes no grade: if the TradingView endpoint dies tomorrow, we
lose a cross-reference we were not yet acting on. Our four existing feeds (Polygon,
Alpaca, FMP, Perplexity) are completely untouched — nothing about live grading
degrades. The rows already recorded still answer the one-month question they were
collecting for; only the *rate* of new rows drops to zero, and that drop is exactly
what the degradation canary below pages on. A genuinely different-shaped fallback
worth NAMING (not building — the brief is explicit: no second fetcher) is Stocktwits:
the BFLY case doc (`ep_reference_bfly_2026-06-18.md`, "the causal chain") found a
Stocktwits piece — carried BY TradingView, not this endpoint — with the full Midjourney
story at 08:56 PDT / 11:56 ET, proving the information was public that morning through
a route this module does not fetch. If TradingView's headlines endpoint is ever
retired, Stocktwits directly is the next thing worth probing — a new card, not a
silent extension of this one.

DEGRADATION DETECTION — the five classes, and why each constant is what it is.
This endpoint has no auth and no plan tier to lose, so "degraded" here means the
SHAPE or VOLUME of what comes back, never a billing/quota signal:

  1. non-200 / timeout / connection failure ("fetch_error" tv_status). A SINGLE
     failed fetch among several healthy ones in the same run is ordinary network
     noise and must not page — `_TV_FAILURE_RATE_THRESHOLD` (0.5) requires a
     MAJORITY of this run's attempted fetches to fail before the run itself counts
     as degraded (see classify_run_degradation).
  2. "a zero-item response where we previously got items" (operator's own framing).
     This shadow fetches each ticker AT MOST ONCE EVER (the population query
     excludes tickers already recorded) — there is no per-ticker history to compare
     a ticker's zero against. The achievable equivalent, and what is actually built:
     this run's aggregate item-count trend against ITS OWN trailing norm (class 4).
  3. unparseable payload / schema change ("unparseable" tv_status — `items` key
     missing or not a list). Any occurrence this run is a candidate reason; the
     shared canary's own 3-in-72h sustained requirement (below) is what keeps a
     single garbled byte from paging.
  4. item-count collapse vs. this table's own trailing norm. `_TV_NORM_LOOKBACK_DAYS`
     (30) / `_TV_NORM_MIN_SAMPLES` (20 'ok' rows) is the same cold-start guard shape
     `health_checks.py`'s per-table liveness cadence uses (never trust a median built
     from a handful of rows) — read from mi_tv_news_shadow's OWN history
     (`db.get_tv_news_shadow_trailing_item_counts`), not parsed audit-log text.
     `_TV_COLLAPSE_RATIO` (0.3) — today's median well under a third of the trailing
     median — mirrors the self-audit L2 anomaly convention (CLAUDE.md: outside a
     trimmed baseline is the trigger, not any deviation) without inventing a new rule.
  5. EVERY candidate skipped for exchange resolution (`all_candidates_unresolved`).
     A single skip is a COVERAGE fact, not degradation (mi_security_types never
     classified this ticker, or its MIC is genuinely absent from the shared
     TradingView-prefix map) — but a run where population > 0 and NOTHING was even
     attempted looks "healthy" under classes 1-4 (no failures, no unparseable
     response, no item counts to collapse) while producing ZERO evidence. This is
     the quiet-zero the operator's own addendum named; caught explicitly rather than
     inferred from an absence of the other four signals.

ALL FIVE route through ONE shared, already-reviewed mechanism —
`llm_health.alert_endpoint_shape_anomaly` — exactly as that function's own module
comment invites ("a future FIXED-URL provider can reuse this ... only a new
audit_events constant"). It writes ONE audit row per run (`TV_NEWS_ENDPOINT_ERROR`,
which is deliberately RUN-scoped: at most one call per run here, with every reason
found this run joined into one string, so its lookback genuinely counts BAD NIGHTS,
not bad fetches) and Telegrams the operator only once the SAME (provider, event_type)
has fired >= 3 times within a 72h window — for a once-nightly job this reads as
"3 consecutive nightly runs, tolerant of one skipped night," which is a real state
CHANGE (healthy -> broken), never a single blip. `maybe_alert_api_failure`
(llm_health's OTHER canary) is deliberately NOT used here: its sustained-window
(6h) and time-spread requirement are sized for scan-cadence traffic (many calls an
hour) and would never accumulate correctly against a job that runs once a day.

POLITENESS. Sequential fetches only (never concurrent), `_TV_PACE_SECONDS` between
them, a real identifying User-Agent (`_TV_UA` — the same identity string this repo
already uses for SEC EDGAR, `collector._SEC_UA`, kept as its own constant here rather
than a shared import: TradingView has no plan tier or env-var-gated key to couple to
SEC's, and the analyst-estimates recorder's own lesson is exactly to avoid one name
silently governing two unrelated vendors). No retries — a failed fetch is recorded and
the run moves on to the next ticker, never retried within the same run.

EXCHANGE RESOLUTION — from what we already store, never a hardcoded ticker map.
`db.get_security_exchange_map` reads the MIC code Polygon reference data already
populates in `mi_security_types`; the MIC-to-TradingView-prefix table
(`friday_watchlist._TV_EXCHANGE_MAP`) is REUSED, not re-hardcoded — it is the exact
map `agent.py` already imports for TradingView chart-link buttons, so the two call
sites cannot silently drift apart. UNLIKE that display use (which defaults an
unmapped MIC to 'NASDAQ' — harmless for a clickable link), an unresolved exchange
here is a RECORDED SKIP, never a guessed prefix: a wrong prefix silently queries a
DIFFERENT company under the same ticker letters on another exchange.

THE ENDPOINT'S OWN SHAPE, verified empirically 2026-09-06 (not assumed):
`https://news-headlines.tradingview.com/v2/headlines?client=overview&lang=en&symbol=<EXCH>:<TICKER>`
returns `{"items": [...]}`, each item carrying (at least) `id`, `title`, `provider`,
`published` (unix seconds) — confirmed against a live BFLY fetch (25 items / 7
providers, exactly matching the brief's stated facts) and archived as
`tests/fixtures/tv_headlines_bfly_2026-09-06.json`. Two facts NOT in the original
brief, found while probing:
  - It is a ROLLING MOST-RECENT-~25-ITEM WINDOW, not date-scoped — a `to=`/`from=`
    style parameter is silently IGNORED (probed empirically). A heavily-covered
    ticker's window can roll PAST an older alert date entirely (BFLY's own June
    items are already gone as of this writing, crowded out by its August earnings
    print) — see `tv_coverage_reaches_alert_date`, the guard this forces.
  - An unresolved/invalid symbol, or a bare ticker with no exchange prefix, returns
    HTTP 200 with `{"items": []}` — NOT an error. A zero-item response is therefore
    a legitimate outcome (`tv_status='ok'`, `tv_item_count=0`), never `fetch_error`.
  - The User-Agent header is NOT enforced server-side (a request with none still
    returns 200) — sent anyway, because politeness does not depend on enforcement.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import statistics
from datetime import date, datetime, time as dt_time, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

from agents.market_intelligence.audit_events import TV_NEWS_ENDPOINT_ERROR, TV_NEWS_SHADOW_RUN
from agents.market_intelligence.db import (
    get_catalyst_metrics_raw_corpus,
    get_no_catalyst_alert_population,
    get_security_exchange_map,
    get_tv_news_shadow_trailing_item_counts,
    log_audit_event,
    upsert_tv_news_shadow_rows,
)
from shared.dates import last_trading_day

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

# ── population ─────────────────────────────────────────────────────────────────────
# How far back to look for un-recorded "thin/no-catalyst" alerts. Small on purpose:
# the endpoint is a ROLLING most-recent-N window (see module docstring), so an OLDER
# alert is LESS likely to still be reachable through it — freshness matters more than
# catching every possible miss. 3 covers a single missed run (weekend + a Monday
# holiday) without spending the fetch cap on tickers whose window has likely rolled
# past their alert date already; can be widened once real coverage data comes in.
_TV_LOOKBACK_DAYS = 3

# ── network / safeguards ───────────────────────────────────────────────────────────
# Per-fetch timeout. This runs once nightly with no latency budget to protect, so the
# bound is generous (the #210 IR-newsroom design's worst measured host, GRRR, took
# 8.6s under a similar honest-UA fetch) rather than tight.
_TV_FETCH_TIMEOUT_SECONDS = 10.0
# Hard cap on network fetches in one run. The nightly population is small (a handful
# of alerts a night, per the case doc's ~5-7% catalyst-less rate), but this bounds a
# pathological night (a sector-wide gap morning) from turning into an unbounded fetch
# storm. A ticker deferred past the cap is simply left unrecorded — the population
# query only excludes ALREADY-WRITTEN keys, so it is picked up again next run.
_TV_MAX_FETCHES_PER_RUN = 20
# Politeness pacing between SEQUENTIAL fetches (never concurrent) — a courtesy, not a
# documented rate limit (TradingView publishes none for this endpoint). At the cap,
# worst case is 20 * (10s timeout + 0.5s pace) = 210s, comfortably inside the 45-minute
# 20:45-21:30 ET window this job runs in.
_TV_PACE_SECONDS = 0.5
# One identifying UA, matching the identity string this repo already uses for SEC
# EDGAR (collector._SEC_UA) — kept as its OWN constant rather than a shared import:
# TradingView has no plan tier or env-var-gated key to couple to SEC's, and the
# analyst-estimates recorder module's own lesson (see its docstring) is exactly to
# avoid one name silently governing two unrelated vendors.
_TV_UA = {"User-Agent": "Apollo Research lastone99@gmail.com"}
_TV_BASE_URL = "https://news-headlines.tradingview.com/v2/headlines"

# ── degradation detection (see module docstring for the full rationale) ────────────
# A run's fetch-failure ratio must be a MAJORITY before it counts as a degradation
# candidate — a single stray timeout among several successes is ordinary network
# noise, not a signal; the shared canary's own 3-consecutive-run requirement (below)
# is the second, independent guard against a false positive.
_TV_FAILURE_RATE_THRESHOLD = 0.5
# Trailing baseline window + minimum sample size for the item-count-collapse check —
# same cold-start shape as health_checks.py's per-table liveness cadence (never trust
# a median built from a handful of rows).
_TV_NORM_LOOKBACK_DAYS = 30
_TV_NORM_MIN_SAMPLES = 20
# Today's median item count must fall below 30% of the trailing median to count as a
# collapse — mirrors the self-audit L2 anomaly convention (an outside-baseline trigger,
# not any deviation); loose enough that ordinary night-to-night population churn
# (different tickers, different natural news volume) does not false-positive.
_TV_COLLAPSE_RATIO = 0.3

# ET hour at/after which a PRIOR trading day's item still counts as "same day" for the
# alert (an after-close release is next morning's gap) — the #210 IR-newsroom design's
# own same-day rule (docs/design/210_ir_newsroom_fallback_2026-09-05.md §2.3), reused
# rather than re-derived so both sources agree on what "the alert's news day" means.
_TV_SAME_DAY_PRIOR_CLOSE_HOUR = 16


# ── pure core (mock-free, the house idiom) ────────────────────────────────────────

_TITLE_NORMALIZE_RE = re.compile(r"[^a-z0-9\s]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace — so the SAME headline
    rendered with a curly quote, a trailing period, or extra whitespace by two
    different pipelines still matches. Deliberately does NOT dedupe across
    PROVIDERS re-titling the same real story (a Dow Jones wire-blurb, a Business
    Wire full headline, and a Benzinga paraphrase all fired for BFLY's OWN Q2
    print, three different titles, one real event) — that is a harder problem,
    named as a documented upper bound on `tv_items_we_missed` in the DDL and the
    module docstring, not solved here."""
    t = title.lower()
    t = _TITLE_NORMALIZE_RE.sub(" ", t)
    return _WHITESPACE_RE.sub(" ", t).strip()


def parse_tv_item(raw: Any) -> Optional[dict]:
    """One TradingView headline item -> {"title","provider","published"}, or None if
    a required field is missing/wrong-typed (the brief names id/title/provider/
    published as load-bearing; only the three we actually use are asserted here).
    Every other field the live payload carries (link, urgency, relatedSymbols,
    sourceLogoId, storyPath, is_flash, permission, source) is deliberately ignored —
    this is a headline cross-reference, not a full-payload archive."""
    if not isinstance(raw, dict):
        return None
    title = raw.get("title")
    provider = raw.get("provider")
    published = raw.get("published")
    if not isinstance(title, str) or not title.strip():
        return None
    if not isinstance(provider, str) or not provider.strip():
        return None
    if isinstance(published, bool) or not isinstance(published, (int, float)):
        return None
    return {"title": title, "provider": provider, "published": int(published)}


def parse_tv_response(payload: Any) -> "tuple[list[dict], int]":
    """The raw decoded JSON body -> (parsed items, malformed_item_count).

    Returns `([], -1)` — the SCHEMA-CHANGE sentinel — when `items` is absent or not a
    list: that is the endpoint's shape breaking, not an empty result. A present-but-
    EMPTY list (`{"items": []}`) is a LEGITIMATE, verified-live response (an
    unresolved symbol or a bare ticker with no exchange prefix returns exactly this,
    HTTP 200) and returns `([], 0)` — callers must never conflate the two."""
    if not isinstance(payload, dict) or "items" not in payload:
        return [], -1
    raw_items = payload["items"]
    if not isinstance(raw_items, list):
        return [], -1
    parsed: list[dict] = []
    malformed = 0
    for r in raw_items:
        item = parse_tv_item(r)
        if item is None:
            malformed += 1
        else:
            parsed.append(item)
    return parsed, malformed


def tv_item_et_datetime(published: int) -> datetime:
    """Unix seconds -> ET-aware datetime. `fromtimestamp(..., tz=_ET)` — never
    `utcfromtimestamp` (naive, banned in agents/ by deploy gate [5h/7])."""
    return datetime.fromtimestamp(published, tz=_ET)


def is_same_day_item(item_et: datetime, alert_date: date, prior_trading_day: date) -> bool:
    """Same-day rule (docs/design/210_ir_newsroom_fallback_2026-09-05.md §2.3, reused
    verbatim): an item counts toward `alert_date` if its ET calendar date IS
    alert_date, OR it is dated the PRIOR TRADING day at/after 16:00 ET (an
    after-close release is the next morning's gap)."""
    d = item_et.date()
    if d == alert_date:
        return True
    return d == prior_trading_day and item_et.time() >= dt_time(_TV_SAME_DAY_PRIOR_CLOSE_HOUR, 0)


def resolve_tv_symbol(ticker: str, mic: str) -> "tuple[Optional[str], Optional[str]]":
    """(symbol, skip_reason) — exactly one is None. Resolves the MIC code (read from
    what we already store, `mi_security_types` via `db.get_security_exchange_map` —
    NEVER a hardcoded ticker->exchange table) to a TradingView prefix via the SAME
    map `agent.py` already uses for TradingView chart-link buttons
    (`friday_watchlist._TV_EXCHANGE_MAP`) — reused, not re-hardcoded, so this module
    and that display surface can never silently drift apart.

    UNLIKE that display use (which defaults an unmapped MIC to 'NASDAQ' — harmless
    for a clickable chart link a human will glance at), an unresolved exchange here is
    a RECORDED SKIP, never a guessed prefix: querying the wrong exchange silently
    returns a DIFFERENT company that happens to share the ticker letters.

    `mi_security_types.exchange` maps BOTH "ticker absent from the table" and
    "ticker present with an empty exchange string" to `''` (see
    `get_security_exchange_map`'s own docstring) — this function cannot and does not
    try to tell those two apart; both are recorded as `no_exchange_on_file`."""
    from agents.market_intelligence.friday_watchlist import _TV_EXCHANGE_MAP
    if not mic:
        return None, "no_exchange_on_file"
    prefix = _TV_EXCHANGE_MAP.get(mic)
    if not prefix:
        return None, f"mic_unmapped:{mic}"
    return f"{prefix}:{ticker}", None


def _titles_from_raw(raw: Any) -> list[str]:
    """One of mi_ep_catalyst_metrics' raw_{polygon,alpaca,fmp}_news_json columns ->
    the titles it holds. All three are stored VERBATIM from collector.get_polygon_news
    / get_alpaca_news / get_fmp_news (catalyst_metrics_extractor.py), which already
    normalize every source to a `title` key — one extraction shape suffices for all
    three. Defensive against every shape surprise (NULL column, a JSON-encoded string
    the codec didn't auto-decode, a non-list, a non-dict item, a missing/blank title):
    each degrades to being skipped, never a guess."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    if not isinstance(raw, list):
        return []
    out = []
    for r in raw:
        if isinstance(r, dict):
            t = r.get("title")
            if isinstance(t, str) and t.strip():
                out.append(t)
    return out


def _provider_counts(items: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for it in items:
        counts[it["provider"]] = counts.get(it["provider"], 0) + 1
    return counts


def build_shadow_row(
    alert: dict, corpus: Optional[dict], mic: str, symbol: Optional[str],
    skip_reason: Optional[str], fetch_result: "tuple[Any, Optional[Exception]] | None",
) -> dict:
    """Pure assembly of ONE mi_tv_news_shadow row from already-fetched inputs — kept
    separate from the I/O (snapshot_ticker) so the whole comparison/classification
    logic is unit-testable without a network or a DB. `fetch_result` is
    `(payload, None)` on a successful GET, `(None, exc)` on a raised exception, or
    `None` when no fetch was attempted at all (the exchange never resolved)."""
    ticker, alert_date = alert["ticker"], alert["alert_date"]
    row: dict[str, Any] = {
        "ticker": ticker,
        "alert_date": alert_date,
        "catalyst_quality": alert.get("catalyst_quality"),
        "our_has_direct_source": alert.get("has_direct_source"),
        "our_source_class_count": alert.get("source_class_count"),
        "exchange_mic": mic,
        "tv_symbol": symbol,
    }

    our_titles_norm: set = set()
    if corpus is None:
        row["our_corpus_available"] = False
        row["our_polygon_count"] = None
        row["our_alpaca_count"] = None
        row["our_fmp_count"] = None
        row["our_perplexity_present"] = None
        row["our_total_item_count"] = None
    else:
        polygon_titles = _titles_from_raw(corpus.get("raw_polygon_news_json"))
        alpaca_titles = _titles_from_raw(corpus.get("raw_alpaca_news_json"))
        fmp_titles = _titles_from_raw(corpus.get("raw_fmp_news_json"))
        row["our_corpus_available"] = True
        row["our_polygon_count"] = len(polygon_titles)
        row["our_alpaca_count"] = len(alpaca_titles)
        row["our_fmp_count"] = len(fmp_titles)
        row["our_perplexity_present"] = bool((corpus.get("raw_perplexity_text") or "").strip())
        row["our_total_item_count"] = len(polygon_titles) + len(alpaca_titles) + len(fmp_titles)
        our_titles_norm = {normalize_title(t) for t in (*polygon_titles, *alpaca_titles, *fmp_titles)}

    _empty_tv = dict(
        tv_item_count=None, tv_providers=None, tv_oldest_item_published=None,
        tv_coverage_reaches_alert_date=None, tv_items_on_alert_date=None,
        tv_providers_on_alert_date=None, tv_items_we_missed=None,
    )

    if symbol is None:
        row.update(tv_status="skipped_exchange", tv_skip_reason=skip_reason, **_empty_tv)
        return row

    if fetch_result is None or fetch_result[1] is not None:
        exc = fetch_result[1] if fetch_result else RuntimeError("no fetch attempted")
        row.update(tv_status="fetch_error",
                    tv_skip_reason=f"{type(exc).__name__}: {str(exc)[:150]}", **_empty_tv)
        return row

    payload = fetch_result[0]
    items, malformed = parse_tv_response(payload)
    if malformed == -1:
        row.update(tv_status="unparseable", tv_skip_reason="missing_or_non_list_items_key",
                    **_empty_tv)
        return row

    row["tv_status"] = "ok"
    row["tv_skip_reason"] = f"{malformed} malformed item(s) ignored" if malformed else None
    row["tv_item_count"] = len(items)
    row["tv_providers"] = _provider_counts(items)

    if items:
        oldest_dt = tv_item_et_datetime(min(it["published"] for it in items))
        row["tv_oldest_item_published"] = oldest_dt
        row["tv_coverage_reaches_alert_date"] = oldest_dt.date() <= alert_date
    else:
        # Genuinely nothing returned (a resolved, valid symbol with no news at all is
        # indistinguishable, from this response alone, from a rolled-off window) — the
        # conservative call is "cannot confirm reach," never "trivially covers it."
        row["tv_oldest_item_published"] = None
        row["tv_coverage_reaches_alert_date"] = False

    prior_day = last_trading_day(alert_date - timedelta(days=1))
    same_day = [it for it in items
                if is_same_day_item(tv_item_et_datetime(it["published"]), alert_date, prior_day)]
    row["tv_items_on_alert_date"] = len(same_day)
    row["tv_providers_on_alert_date"] = _provider_counts(same_day)

    if row["our_corpus_available"]:
        row["tv_items_we_missed"] = [
            {"title": it["title"], "provider": it["provider"], "published": it["published"]}
            for it in same_day if normalize_title(it["title"]) not in our_titles_norm
        ]
    else:
        row["tv_items_we_missed"] = None  # nothing stored to diff against — see module docstring

    return row


def classify_run_degradation(summary: dict, trailing_item_counts: list[int]) -> list[str]:
    """Pure decision: which degradation reasons (if any) apply to THIS run. Returns a
    list of short reason strings (possibly empty); the caller joins them into ONE
    `alert_endpoint_shape_anomaly` call per run — see the module docstring's
    "DEGRADATION DETECTION" section for why each threshold is what it is."""
    reasons: list[str] = []

    # A skip is a COVERAGE fact, never a degradation on its own (see
    # `exchange_skip_reasons`'s comment in _run_over_population) — a night where every
    # candidate happens to be off an exchange we resolve is plausible. But a run where
    # population > 0 and NOTHING was even ATTEMPTED (every candidate skipped) means
    # this shadow produced ZERO evidence while looking "healthy" (no failures, no
    # unparseable, no collapse to compare) — exactly the quiet-zero the operator's
    # addendum said must not happen silently. One candidate reason, not a per-skip one.
    attempted = summary.get("fetches_ok", 0) + summary.get("fetches_failed", 0)
    if summary.get("population", 0) > 0 and attempted == 0:
        reasons.append(
            f"all_candidates_unresolved(population={summary['population']},"
            f"skipped_exchange={summary.get('skipped_exchange', 0)},"
            f"reasons={summary.get('exchange_skip_reasons', {})})"
        )

    if summary.get("unparseable", 0) > 0:
        reasons.append(f"unparseable_response(n={summary['unparseable']})")

    if attempted > 0:
        failure_rate = summary.get("fetches_failed", 0) / attempted
        if failure_rate >= _TV_FAILURE_RATE_THRESHOLD:
            reasons.append(
                f"fetch_failure_rate={failure_rate:.2f}(failed={summary.get('fetches_failed', 0)}"
                f"/{attempted})"
            )

    ok_counts = summary.get("ok_item_counts") or []
    if ok_counts and len(trailing_item_counts) >= _TV_NORM_MIN_SAMPLES:
        today_median = statistics.median(ok_counts)
        trailing_median = statistics.median(trailing_item_counts)
        if trailing_median > 0 and today_median < _TV_COLLAPSE_RATIO * trailing_median:
            reasons.append(
                f"item_count_collapse(today_median={today_median:.0f},"
                f"trailing_median={trailing_median:.0f},trailing_n={len(trailing_item_counts)})"
            )

    return reasons


# ── I/O ─────────────────────────────────────────────────────────────────────────────

async def _fetch_tv_headlines(symbol: str) -> Any:
    """One GET, raises on timeout/connect/HTTP-error — the caller (snapshot_ticker)
    catches and records. No retry: a failed fetch is recorded and the run moves on
    (see the module docstring's POLITENESS section)."""
    import httpx
    async with httpx.AsyncClient(timeout=_TV_FETCH_TIMEOUT_SECONDS, headers=_TV_UA) as client:
        r = await client.get(_TV_BASE_URL,
                             params={"client": "overview", "lang": "en", "symbol": symbol})
        r.raise_for_status()
        return r.json()


async def snapshot_ticker(alert: dict, mic: str, symbol: Optional[str],
                          skip_reason: Optional[str]) -> dict:
    """One (ticker, alert_date) -> one mi_tv_news_shadow row. Fetches our own stored
    corpus (always, regardless of exchange resolution — a skipped-exchange row still
    records what WE held) and, only when an exchange resolved, the TradingView
    headlines. Never raises — a transport failure here becomes a `fetch_error` row via
    build_shadow_row, and any OTHER exception (a code bug) is the caller's problem to
    isolate (per-ticker try/except lives in `_run_over_population`, matching the house
    per-item-isolation idiom)."""
    ticker, alert_date = alert["ticker"], alert["alert_date"]
    try:
        corpus = await get_catalyst_metrics_raw_corpus(ticker, alert_date)
    except Exception as e:
        logger.warning(f"tv_news_shadow: corpus read failed for {ticker}/{alert_date}: {e}")
        corpus = None

    fetch_result: "tuple[Any, Optional[Exception]] | None" = None
    if symbol is not None:
        try:
            payload = await _fetch_tv_headlines(symbol)
            fetch_result = (payload, None)
        except Exception as e:  # loud-ok: captured as DATA, not logged per-fetch — the
            # exception becomes this row's tv_status='fetch_error' + tv_skip_reason (written
            # to mi_tv_news_shadow), is counted in the run summary log_audit_event always
            # writes, and feeds classify_run_degradation's failure-rate check; logging every
            # one of up to _TV_MAX_FETCHES_PER_RUN individually would be log noise for a
            # condition the row itself already records.
            fetch_result = (None, e)

    return build_shadow_row(alert, corpus, mic, symbol, skip_reason, fetch_result)


async def _run_over_population(population: list[dict], exchange_map: dict[str, str]) -> "tuple[list[dict], dict]":
    """Sequential (never concurrent — POLITENESS) walk over the population, respecting
    `_TV_MAX_FETCHES_PER_RUN`. A ticker deferred past the cap is left OUT of both the
    returned rows and the write — the population query only excludes already-WRITTEN
    keys, so it is a candidate again next run, automatically."""
    summary: dict[str, Any] = {
        "population": len(population), "fetches_ok": 0, "fetches_failed": 0,
        "skipped_exchange": 0, "unparseable": 0, "cap_deferred": 0, "errors": 0,
        "ok_item_counts": [],
        # {tv_skip_reason: count} — e.g. "no_exchange_on_file" vs "mic_unmapped:XASE".
        # Visibility the operator asked for on night 1: a skip is a COVERAGE fact
        # (mi_security_types never classified this ticker, or its MIC isn't in the
        # shared TradingView-prefix map), not itself a degradation — but WHICH reason
        # dominates tells him whether it's worth a one-line fix (adding a missing MIC
        # to friday_watchlist._TV_EXCHANGE_MAP) or just the expected shape of a
        # small-cap population.
        "exchange_skip_reasons": {},
    }
    rows: list[dict] = []
    fetches_this_run = 0

    for alert in population:
        # The WHOLE per-alert body is one try/except — belt-and-braces per-ticker
        # isolation. A malformed population row (a missing key — a code bug, not a
        # data condition) must be counted and skipped exactly like a bad fetch, never
        # allowed to kill the rest of the run.
        try:
            ticker = alert["ticker"]
            mic = exchange_map.get(ticker, "") or ""
            symbol, skip_reason = resolve_tv_symbol(ticker, mic)

            if symbol is not None and fetches_this_run >= _TV_MAX_FETCHES_PER_RUN:
                summary["cap_deferred"] += 1
                continue

            row = await snapshot_ticker(alert, mic, symbol, skip_reason)
        except Exception as e:  # per-ticker isolation — one bad name never kills the run
            summary["errors"] += 1
            logger.warning(f"tv_news_shadow: a population row failed: {type(e).__name__}: {e}")
            continue

        if symbol is not None:
            fetches_this_run += 1
            await asyncio.sleep(_TV_PACE_SECONDS)

        rows.append(row)
        status = row["tv_status"]
        if status == "ok":
            summary["fetches_ok"] += 1
            summary["ok_item_counts"].append(row["tv_item_count"])
        elif status == "fetch_error":
            summary["fetches_failed"] += 1
        elif status == "unparseable":
            summary["unparseable"] += 1
        elif status == "skipped_exchange":
            summary["skipped_exchange"] += 1
            reason = row.get("tv_skip_reason") or "unknown"
            summary["exchange_skip_reasons"][reason] = (
                summary["exchange_skip_reasons"].get(reason, 0) + 1)

    return rows, summary


async def run_tv_news_shadow(today: date) -> dict:
    """The 20:45 ET nightly entry point. Never raises — every stage is wrapped; a
    failure at any stage degrades to a recorded reason and an empty/partial result,
    never an exception into the scheduler (see `_tv_news_shadow_job` in scheduler.py,
    which is belt-and-braces on top of this)."""
    since = today - timedelta(days=_TV_LOOKBACK_DAYS)
    try:
        population = await get_no_catalyst_alert_population(since, today)
    except Exception as e:
        logger.error(f"tv_news_shadow: population query failed: {e}", exc_info=True)
        try:
            await log_audit_event(TV_NEWS_SHADOW_RUN, f"population query failed: {e}"[:400])
        except Exception:  # loud-ok: logger.error above already fired
            pass
        return {"population": 0, "fetches_ok": 0, "fetches_failed": 0, "rows_written": 0,
                "errors": 1}

    exchange_map: dict[str, str] = {}
    if population:
        try:
            exchange_map = await get_security_exchange_map([a["ticker"] for a in population])
        except Exception as e:
            logger.warning(f"tv_news_shadow: exchange map read failed: {e}")

    rows, summary = await _run_over_population(population, exchange_map)

    try:
        summary["rows_written"] = await upsert_tv_news_shadow_rows(rows)
    except Exception as e:
        summary["rows_written"] = 0
        summary["errors"] = summary.get("errors", 0) + 1
        logger.error(f"tv_news_shadow: write failed: {e}", exc_info=True)

    try:
        trailing = await get_tv_news_shadow_trailing_item_counts(_TV_NORM_LOOKBACK_DAYS, today)
    except Exception as e:
        logger.warning(f"tv_news_shadow: trailing-baseline read failed: {e}")
        trailing = []

    degradation_reasons = classify_run_degradation(summary, trailing)
    summary["degradation_reasons"] = degradation_reasons
    if degradation_reasons:
        try:
            from agents.market_intelligence.llm_health import alert_endpoint_shape_anomaly
            await alert_endpoint_shape_anomaly(
                "tradingview", TV_NEWS_ENDPOINT_ERROR, "+".join(degradation_reasons),
                json.dumps({k: v for k, v in summary.items() if k != "ok_item_counts"},
                          default=str)[:400],
            )
        except Exception as e:  # loud-ok: the run summary audit row below still lands
            logger.warning(f"tv_news_shadow: degradation canary failed: {e}")

    try:
        await log_audit_event(
            TV_NEWS_SHADOW_RUN,
            f"{summary.get('rows_written', 0)} row(s) across {summary['population']} "
            f"candidate(s); {summary['fetches_ok']} ok, {summary['skipped_exchange']} "
            f"skipped-exchange, {summary['fetches_failed']} fetch-error, "
            f"{summary['unparseable']} unparseable, {summary['cap_deferred']} cap-deferred, "
            f"{summary.get('errors', 0)} error(s)"
            + (f"; skip reasons: {summary['exchange_skip_reasons']}"
               if summary.get("exchange_skip_reasons") else "")
            + (f"; DEGRADED: {', '.join(degradation_reasons)}" if degradation_reasons else ""),
        )
    except Exception as e:  # loud-ok: the return value still carries every counter
        logger.warning(f"tv_news_shadow: run-summary audit write failed: {e}")

    return summary
