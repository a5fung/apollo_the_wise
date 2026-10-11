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

THE QUESTION THIS ANSWERS (#210 build, 2026-10-10 - docs/analysis/210_tv_miss_read_2026-10-10.md
§10): "of the stories TradingView carried for an alert, which did we NOT hold - and does the
window even reach back far enough to say?" One row per alert ticker-day (EVERY alert, not only
the thin ones - the no-catalyst cut is made at READ time off the RAW grade, with the acting
grade carried beside it). The readable rows:

    SELECT ticker, alert_date, our_acting_grade, catalyst_quality AS raw_grade,
           tv_items_before_grade, tv_items_in_repoll_window, tv_items_we_missed
    FROM mi_tv_news_shadow
    WHERE tv_status = 'ok' AND tv_items_we_missed IS NOT NULL
    ORDER BY alert_date DESC;

THE COMPARISON FRAME. `captured_at` = when the GRADE read its corpus (`mi_ep_grade_corpus`, one
row per graded candidate; the older `mi_ep_catalyst_metrics` row is the fallback and lags the
grade by minutes). Every TradingView item inside the alert's news day is put in ONE of three
buckets by publish time: before the grade (`<= captured_at`), the re-poll window (after the
grade, at/before 10:00 ET - still actionable: the #344 class) or after the cutoff
(informational). The news day starts 16:00 ET on the prior NYSE TRADING day (holiday-aware).

TWO LISTS, ONE RULE.
  - `tv_items_unmatched_seen`: the `none` and `class` items of the first two buckets, each
    tagged with its bucket and verdict. Written whenever a diff is possible (a corpus and its
    `captured_at`), whatever the window's reach - a miss we SAW is a miss even if the window
    rolled.
  - `tv_items_we_missed` (the DoD column): that same list when the window REACHES the period
    start (`oldest item of the WHOLE window <= period start` - NOT `<= captured_at`, which
    leaves 16:00-to-oldest unseen and would store `[]` over it), else NULL = "cannot tell".
    An empty list is an honest zero; it may never appear on a window that did not reach.
`tv_unseen_minutes_at_period_start` says by how much a window fell short. The story matcher
(`match_tv_item`) decides WHAT is shared, not HOW MUCH: title / story / event / move / class /
none - rules and proof in the ported block below.

READ THE `none` SHARE AS AN UPPER BOUND (three known biases, all by design of the verbatim port;
nothing here is tuned, so the readout - not the matcher - must carry them):
  1. The matcher compares TradingView only against our Polygon, Alpaca and FMP HEADLINES. The SEC
     filing title and the Perplexity text the grade ALSO read (`mi_ep_grade_corpus.sec_title`,
     `.perplexity_text`) are never shown to `match_tv_item`, so a `none` can be a story we held
     through those two. Before quoting the strict share, read each before-grade `none` item
     against that row's sec_title / perplexity_text and report how many were held that way.
  2. `captured_at` on a grade-corpus row is stamped when `write_grade_corpus` runs - AFTER the
     grade call returns (typically tens of seconds after the corpus was fetched). A TradingView item
     published in that gap lands in `tv_items_before_grade` and can read as a miss. Small, but it
     sits in the 07:00-09:35 press-release window.
  3. When a grade-corpus row and a metrics row both exist, the Polygon side comes from the metrics
     row's fetch (made up to ~10 min AFTER the grade) while `captured_at` is the grade time. A
     re-poll-window item can then match 'title'/'story' against a Polygon item the grade never
     had, which UNDERSTATES the re-poll bucket's misses. Report that bucket's Polygon-side
     matches separately, or drop Polygon items published after `captured_at`, before quoting it.
`our_polygon_count` is NULL exactly when the ticker-day has no `mi_ep_catalyst_metrics` row
(Polygon was never fetched); with a metrics row it is that row's Polygon item count, and 0 is an
honest zero (the row's Polygon list was NULL or empty). `our_acting_rule` is NULL whenever there
is no lattice tier-shadow row for the ticker-day (a LEFT JOIN in `db.get_tv_shadow_population`).

🛑 THE LINE - DATA CAPTURE ONLY. This module writes exactly ONE table (`mi_tv_news_shadow`) plus
`mi_audit_log` via the shared `log_audit_event`/`alert_endpoint_shape_anomaly`
telemetry helpers - never a grade, score, admission, or trade-state table. (The grade corpus the
frame diffs against, `mi_ep_grade_corpus`, is written by ep_detector through
`db.write_grade_corpus` - a fail-open INSERT beside the provenance audit INSERT.) Read by NO
grading / entry / sizing / ordering / safeguard path. Acting on this later (feeding a
TradingView-sourced item into a live grade) is a separate CHANGE_PROCESS step with
operator sign-off - nothing here does that.

NEVER ON THE LIVE SCAN PATH. This is a POST-HOC job: 10:10 ET, mon-fri - after the scan's last
tick (09:55 ET; the cron is */5 over hours 7-9), its 10:00 stop, the 10:00 unfilled-order cancel
and the 10:05 scan watchdog, so the before-grade and re-poll buckets are complete, and clear of
the 12:00-13:00 ET market-hours deploy window. (It was 20:45 ET until 2026-10-10: 3 of 10 captured windows had already rolled
past the period start by then, and a heavily covered name's 25-slot window spends most of its
slots on the day's later items.) It never runs during 07:00-10:00 ET (the scan) or
09:31-09:44 ET (the ORB submission window) - there is no latency budget question because it
structurally cannot collide with either.

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
found this run joined into one string, so its lookback genuinely counts BAD RUNS,
not bad fetches) and Telegrams the operator only once the SAME (provider, event_type)
has fired >= 3 times within a 72h window — for a once-per-weekday job this reads as
"3 consecutive weekday runs, tolerant of one skipped day," which is a real state
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
import math
import re
import statistics
from datetime import date, datetime, time as dt_time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from zoneinfo import ZoneInfo

from agents.market_intelligence.audit_events import TV_NEWS_ENDPOINT_ERROR, TV_NEWS_SHADOW_RUN
from agents.market_intelligence.db import (
    get_grade_corpus,
    get_security_exchange_map,
    get_tv_news_shadow_trailing_item_counts,
    get_tv_shadow_population,
    log_audit_event,
    upsert_tv_news_shadow_rows,
)

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

# ── population ─────────────────────────────────────────────────────────────────────
# How far back to look for un-recorded alerts (EVERY alert since #210's 2026-10-10 build —
# no raw-grade predicate; the no-catalyst cut is made at READ time). Small on purpose:
# the endpoint is a ROLLING most-recent-N window (see module docstring), so an OLDER
# alert is LESS likely to still be reachable through it — freshness matters more than
# catching every possible miss. 3 covers a single missed run (weekend + a Monday
# holiday) without spending the fetch cap on tickers whose window has likely rolled
# past their alert date already; can be widened once real coverage data comes in.
_TV_LOOKBACK_DAYS = 3

# ── network / safeguards ───────────────────────────────────────────────────────────
# Per-fetch timeout. This runs once per weekday (10:10 ET) with no latency budget to protect,
# so the bound is generous (the #210 IR-newsroom design's worst measured host, GRRR, took
# 8.6s under a similar honest-UA fetch) rather than tight.
_TV_FETCH_TIMEOUT_SECONDS = 10.0
# Hard cap on network fetches in one run. The population is small (EVERY alert not yet
# recorded: 1-3 a day over the three weeks to 2026-10-09, so at most ~9 inside the 3-day
# lookback), but this bounds a pathological day (a sector-wide gap morning) from turning
# into an unbounded fetch storm. A ticker deferred past the cap is simply left unrecorded — the population
# query only excludes ALREADY-WRITTEN keys, so it is picked up again next run.
_TV_MAX_FETCHES_PER_RUN = 20
# Politeness pacing between SEQUENTIAL fetches (never concurrent) — a courtesy, not a
# documented rate limit (TradingView publishes none for this endpoint). At the cap,
# worst case is 20 * (10s timeout + 0.5s pace) = 210s — a few minutes from the 10:10 ET start.
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
# not any deviation); loose enough that ordinary day-to-day population churn
# (different tickers, different natural news volume) does not false-positive.
_TV_COLLAPSE_RATIO = 0.3

# ET hour at/after which a PRIOR trading day's item still counts as "same day" for the
# alert (an after-close release is next morning's gap) — the #210 IR-newsroom design's
# own same-day rule (docs/design/210_ir_newsroom_fallback_2026-09-05.md §2.3), reused
# rather than re-derived so both sources agree on what "the alert's news day" means.
_TV_SAME_DAY_PRIOR_CLOSE_HOUR = 16
# The scan's stop (10:00 ET; its last tick is 09:55) and the 10:00 ET unfilled-cancel: a
# TradingView item published after our grade (`captured_at`) but at/before this instant was
# still ACTIONABLE — the #344 re-poll class — and is its own bucket
# (`tv_items_in_repoll_window`). Later items are informational only (`tv_items_after_cutoff`).
_TV_ACTIONABLE_CUTOFF_ET = dt_time(10, 0)


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


# ═══════════════════════════════════════════════════════════════════════════════════
# THE STORY MATCHER + COMPARISON FRAME (#210, 2026-10-10 build card).
# PORTED VERBATIM from scripts/probes/_wk1010_210/tv_story_matcher.py (names kept) and
# PROVEN against tests/fixtures/tv_shadow_210_cases_2026-10-10.json by
# tests/test_210_tv_news_shadow.py (the same 50 assertions run_fixture_proof.py makes).
# NEVER TUNE IN PLACE: a change here goes through the fixture first (add a case, re-run
# the proof, THEN change code). `normalize_title` and `is_same_day_item` above are the
# module's own and are not duplicated.
# ═══════════════════════════════════════════════════════════════════════════════════

# ── vocabularies (closed lists; the card may EXTEND, never remove) ─────────────────
STOPWORDS = frozenset("""
the a an of to in on for and is at by as with its it from this that are be or vs after before
into over up down out here there what why how who when which more than their his her our your
has have had will can does do did not no but also about amid says said say stock stocks share
shares inc corp ltd plc co nyse nasdaq update updated correction summary today tonight
monday tuesday wednesday thursday friday saturday sunday week month year years ago per via
""".split())

# Words that name a CLASS or a rating/target vocabulary — never an anchor.
CLASS_WORDS = frozenset("""
q1 q2 q3 q4 1q 2q 3q 4q quarter quarterly fiscal earnings eps revenue revenues sales results
result guidance outlook profit profits beat beats miss misses estimate estimates transcript
gaap non-gaap nongaap call highlights
price target targets pt maintains maintain maintained reiterates reiterate reiterated upgrades
upgrade upgraded downgrades downgrade downgraded initiates initiate initiated rating ratings
overweight underweight outperform underperform buy sell hold neutral raised raises raise lowers
lower lowered cut cuts keeps keep rates rated boosts boost hikes hike lifts lift trims trim
sees see starts start resumes resume reinstates reinstate assumes assume
appoints appoint appointed appointment names name named hires hire hired resigns resign
resigned resignation steps step stepped retires retire retiring retirement departure succeeds
succeed succeeded cfo ceo coo cto chief officer president chairman director effective immediately
acquires acquire acquired acquiring acquisition merger merge buyout takeover definitive
partnership partners partner collaborates collaborate collaboration agreement contract awarded
award selected signs sign teams team
offering priced private placement convertible notes due at-the-market warrants warrant dilution
dilutive shelf direct
fda approval approves approved clearance 510(k) phase trial topline pdufa breakthrough
lawsuit class action investigation settles settle settled settlement probe subpoena
launch launches launched unveils unveil unveiled introduces introduce introduced debuts debut
scheduled set report reports reported reporting ahead preview expect expected watch deck
volatility primer
market talk trades trade trading higher jumps jump jumped surges surge surged soars soar
soared rally rallies rallied pops pop climbs climb rising rises rise falls fall slips slip
drops drop plunges plunge best worst day 52-week high low premarket pre-market overnight
midday skyrocket skyrockets sympathy gaps gap gapped gapping movers mover moving focus
happening need know explain
""".split())

# Generic headline words that carry no story identity — never an anchor.
GENERIC_WORDS = frozenset("""
strong strongly record records growth demand business businesses company companies group
global market markets investors investor analysts analyst wall street report reports new
news big major key top first latest update higher lower after ahead following amid upbeat
surging signals faster future shape taking stake stakes deal deals client clients spending
costs cost shares stock stocks inc corp plc ltd
""".split())

# Catalyst classes, in PRIMARY-class precedence order (first hit wins for `class` storage).
CATALYST_CLASS_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("earnings", re.compile(
        r"\bq[1-4]\b|\b[1-4]q\b|\bquarter\b|\bfy ?\d{2,4}\b|\bfiscal\b|\bearnings\b|\beps\b|"
        r"\brevenues?\b|\bsales\b|\bresults\b|\bguidance\b|\boutlook\b|\bprofits?\b|\bbeats?\b|"
        r"\bmiss(es)?\b|\bestimates?\b|\btranscript\b|\bnon-gaap\b|\bgaap\b", re.I)),
    ("analyst", re.compile(
        r"\bprice targets?\b|\bpt\b|\bmaintains?\b|\bmaintained\b|\breiterates?\b|\breiterated\b|"
        r"\bupgrades?\b|\bupgraded\b|\bdowngrades?\b|\bdowngraded\b|\binitiates?\b|\binitiated\b|"
        r"\brating\b|\boverweight\b|\bunderweight\b|\boutperform\b|\bunderperform\b", re.I)),
    ("exec_change", re.compile(
        r"\bappoint(s|ed|ment)?\b|\bnames?\b.{0,40}\b(cfo|ceo|coo|cto|chief|president|chairman|"
        r"director)\b|\bhires?\b|\bhired\b|\bresign(s|ed|ation)?\b|\bsteps? down\b|\bstepped down\b|"
        r"\bretir(es|ing|ement)\b|\bdeparture\b|\bsucceed(s|ed)?\b|\bnew (cfo|ceo|coo|cto)\b|"
        r"\bas (cfo|ceo|coo|cto)\b|\bchief [a-z]+ officer\b|\beffective immediately\b", re.I)),
    ("mna", re.compile(
        r"\bacquir(es?|ed|ing)\b|\bacquisition\b|\bmerger\b|\bmerge\b|\bbuyout\b|\btakeover\b|"
        r"\bto buy\b|\bdefinitive agreement\b|\bbid for\b", re.I)),
    ("deal", re.compile(
        r"\bpartnership\b|\bpartners? with\b|\bcollaborat(es?|ion)\b|\bagreement\b|\bcontract\b|"
        r"\bawarded?\b|\bselected by\b|\bsigns?\b|\bteams? up\b", re.I)),
    ("financing", re.compile(
        r"\boffering\b|\bpriced\b|\bprivate placement\b|\bconvertible\b|\bnotes due\b|"
        r"\bat-the-market\b|\bwarrants?\b|\bdilut(ion|ive)\b|\bshelf\b", re.I)),
    ("regulatory", re.compile(
        r"\bfda\b|\bapprov(al|es|ed)\b|\bclearance\b|\b510\(k\)|\bphase [1-3]\b|\btrial\b|"
        r"\btopline\b|\bpdufa\b|\bbreakthrough\b", re.I)),
    ("legal", re.compile(
        r"\blawsuit\b|\bclass action\b|\binvestigation\b|\bsettle(s|d|ment)?\b|\bprobe\b|"
        r"\bsubpoena\b", re.I)),
    ("product", re.compile(
        r"\blaunch(es|ed)?\b|\bunveils?\b|\bunveiled\b|\bintroduces?\b|\bintroduced\b|\bdebuts?\b",
        re.I)),
)
CATALYST_CLASSES = frozenset(c for c, _ in CATALYST_CLASS_PATTERNS)

# STRONG commentary markers = a FORMAT (a roundup, a "why" explainer, a Market Talk blurb).
# They win over any catalyst keyword in the same title ("CEO Says Focus on Big Deals — Market
# Talk" is commentary, not a deal). WEAK markers (jumps, surges, premarket) make a title
# commentary only when it carries no catalyst class ("jumps premarket following strong Q4
# beat" stays earnings).
COMMENTARY_STRONG_RE = re.compile(
    r"market talk|here is why|here's why|what's going on|what you need to know|need to know|"
    r"stock market today|stocks to watch|\bmovers?\b|moving (premarket|pre-market|higher|lower|in)|"
    r"and more stocks|stocks that explain|what's happening|\bin focus\b|\bbig stocks\b", re.I)
COMMENTARY_WEAK_RE = re.compile(
    r"\bwhy\b|trades? up|trading (higher|lower)|\bjumps?\b|\bjumped\b|\bsurges?\b|\bsurged\b|"
    r"\bsoars?\b|\bsoared\b|\brall(y|ies|ied)\b|\bpops?\b|\bclimbs?\b|\brising\b|\brises?\b|"
    r"\bfalls?\b|\bslips?\b|\bdrops?\b|\bplunges?\b|\bbest day\b|\bworst day\b|52-week|"
    r"(month|year) high|(month|year) low|\bpremarket\b|\bpre-market\b|\bovernight\b|\bmidday\b|"
    r"\bskyrockets?\b|\bsympathy\b|\bgap(s|ped|ping)? (up|down)\b", re.I)
# An earnings PREVIEW is not a results item: it cannot anchor an `event` match and is not
# "a reason for the move" (correction 6: actual results vs our preview must stay visible).
PREVIEW_RE = re.compile(
    r"\bscheduled\b|\bset to report\b|\bahead of\b|\bpreview\b|\bwhat to expect\b|\bto watch\b|"
    r"\bto report\b|\bexpected to report\b|\bearnings week\b|\bearnings volatility\b|"
    r"\bwill report\b|\bon deck\b|\breports? (on|after|before|this|next)\b|\bshould know\b|"
    r"\bearnings (preview|watch)\b|\bprimer\b", re.I)

# Analyst-firm extraction: the capitalised run BEFORE an analyst verb at the start of the
# title, or AFTER "by/at/from" at its end. Company/class/stop words are stripped from the
# candidate; an empty remainder means "no firm here" (so "Penguin Solutions Price Target
# Raised ... by Stifel" yields Stifel from the tail, not the company from the head).
_ANALYST_VERBS = (r"maintains?|maintained|reiterates?|reiterated|upgrades?|upgraded|downgrades?|"
                  r"downgraded|initiates?|initiated|raises?|raised|lowers?|lowered|cuts?|keeps?|"
                  r"rates?|rated|boosts?|hikes?|lifts?|trims?|sees?|starts?|resumes?|reinstates?|"
                  r"assumes?")
_CAP = r"[A-Z][\w&.'’-]*"
_FIRM_HEAD_RE = re.compile(
    rf"^\s*(?P<firm>{_CAP}(?:\s+(?:(?:of|&|and|de)\s+)?{_CAP}){{0,3}})\s+(?i:{_ANALYST_VERBS})\b")
_FIRM_TAIL_RE = re.compile(
    rf"\b(?:by|at|from)\s+(?P<firm>{_CAP}(?:\s+(?:(?:of|&|and)\s+)?{_CAP}){{0,3}})\s*[.)]?\s*$")

# Numeric anchors: dollar amounts (with unit), percentages, fiscal years. Bare numbers and
# calendar years are deliberately NOT anchors (they are everywhere).
_USD_RE = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*(k|m|b|t|million|billion|trillion|thousand)?\b", re.I)
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s?%")
_FY_RE = re.compile(r"\bfy\s?(\d{2}|\d{4})\b|\bfiscal (\d{4})\b", re.I)
_UNIT = {"million": "m", "billion": "b", "trillion": "t", "thousand": "k"}


# ── classification ─────────────────────────────────────────────────────────────────

def catalyst_classes(title: str) -> set[str]:
    """Catalyst classes a title carries (possibly several). A STRONG commentary marker
    empties the set — the title is a format, not a catalyst."""
    if COMMENTARY_STRONG_RE.search(title):
        return set()
    return {c for c, rx in CATALYST_CLASS_PATTERNS if rx.search(title)}


def is_commentary(title: str) -> bool:
    if COMMENTARY_STRONG_RE.search(title):
        return True
    return bool(COMMENTARY_WEAK_RE.search(title)) and not catalyst_classes(title)


def is_preview(title: str) -> bool:
    return "earnings" in catalyst_classes(title) and bool(PREVIEW_RE.search(title))


def primary_class(title: str) -> str:
    """ONE label for storage on a `none`/`class` item: the first catalyst class in precedence
    order, else `commentary`, else `other`."""
    cats = catalyst_classes(title)
    for c, _ in CATALYST_CLASS_PATTERNS:
        if c in cats:
            return c
    return "commentary" if is_commentary(title) else "other"


def holds_a_catalyst(title: str) -> bool:
    """Our item is 'a reason for the move' when it carries a catalyst class and is not
    merely an earnings preview."""
    cats = catalyst_classes(title)
    if not cats:
        return False
    return not (cats == {"earnings"} and is_preview(title))


# ── anchors ────────────────────────────────────────────────────────────────────────

def company_tokens(company_name: Optional[str], ticker: str, our_titles: list[str]) -> set[str]:
    """Tokens that name the company — never anchors. From the stored company name when the
    grade-corpus row carries one (Part 3 stores profile['companyName']); otherwise the
    frequency fallback: a token present in >= 3 of our titles (>= 2 when we hold fewer than
    6). The fallback is what the metrics-only rows (ACN/PENG/ERO) get."""
    toks = {ticker.lower()}
    if company_name:
        toks |= {t for t in normalize_title(company_name).split() if t not in STOPWORDS}
        return toks
    n = len(our_titles)
    thr = 3 if n >= 6 else 2
    counts: dict[str, int] = {}
    for t in our_titles:
        for w in set(normalize_title(t).split()):
            if w.isalpha() and len(w) >= 3 and w not in STOPWORDS:
                counts[w] = counts.get(w, 0) + 1
    toks |= {w for w, c in counts.items() if c >= thr}
    return toks


def _num(s: str) -> str:
    try:
        return format(Decimal(s.replace(",", "")).normalize(), "f")
    except InvalidOperation:
        return s


def numeric_anchors(title: str) -> set[str]:
    out: set[str] = set()
    for m in _USD_RE.finditer(title):
        unit = (m.group(2) or "").lower()
        out.add(f"usd:{_num(m.group(1))}{_UNIT.get(unit, unit)}")
    for m in _PCT_RE.finditer(title):
        out.add(f"pct:{_num(m.group(1))}")
    for m in _FY_RE.finditer(title):
        y = m.group(1) or m.group(2)
        out.add(f"fy:{('20' + y) if len(y) == 2 else y}")
    return out


def alpha_anchors(title: str, company: set[str]) -> set[str]:
    return {w for w in normalize_title(title).split()
            if w.isalpha() and len(w) >= 4
            and w not in STOPWORDS and w not in CLASS_WORDS and w not in GENERIC_WORDS
            and w not in company}


def analyst_firm(title: str, company: set[str]) -> Optional[str]:
    for rx in (_FIRM_HEAD_RE, _FIRM_TAIL_RE):
        m = rx.search(title)
        if not m:
            continue
        toks = [w for w in normalize_title(m.group("firm")).split()
                if w not in STOPWORDS and w not in CLASS_WORDS and w not in GENERIC_WORDS
                and w not in company]
        if toks:
            return " ".join(toks)
    return None


# ── same-day frame (is_same_day_item above) ─────────────────────────────────────────


def period_start(alert_date: date, prior_trading_day: date) -> datetime:
    """The first instant of the alert's news day: 16:00:00 ET on the prior TRADING day
    (the same-day rule's own boundary, _TV_SAME_DAY_PRIOR_CLOSE_HOUR). The frame's
    window-reach test is `oldest item <= period_start`, never `oldest <= captured_at`:
    the latter leaves the stretch between 16:00 and the oldest item unseen and reads an
    empty list over it (ACN: oldest 09:31 vs capture 07:10 would have read "reaches")."""
    return datetime.combine(prior_trading_day, dt_time(_TV_SAME_DAY_PRIOR_CLOSE_HOUR, 0), tzinfo=_ET)


def prior_weekday(d: date) -> date:
    """Weekend-only step back — what `shared.dates.last_trading_day(d - 1 day)` does today.
    HOLIDAY-BLIND: for ERO 2026-09-08 (the Tuesday after Labor Day) it returns Monday
    09-07, so the period would start 16:00 on a day the market was shut. Kept only as
    the fallback when exchange_calendars is unavailable; production uses the function
    below."""
    p = d - timedelta(days=1)
    while p.weekday() >= 5:
        p -= timedelta(days=1)
    return p


def prior_trading_day_holiday_aware(d: date) -> tuple[date, str]:
    """(prior NYSE trading day strictly before d, which calendar decided it). Steps back
    one calendar day at a time until `trading_calendar.get_market_status(x).is_trading_day`
    (exchange_calendars XNYS: weekends + NYSE holidays; it logs one INFO line per call,
    which at one call per candidate is fine). Falls back to the weekend-only rule,
    saying so, when the calendar cannot be imported — the card ports the first branch."""
    try:
        from agents.market_intelligence.trading_calendar import get_market_status
    except Exception:  # loud-ok: in-band report - returns the "weekday_fallback" label and build_shadow_row logs a warning for any basis that is not "nyse_calendar"
        return prior_weekday(d), "weekday_fallback"
    p = d - timedelta(days=1)
    for _ in range(10):  # never more than a long weekend + holiday away
        if get_market_status(p).is_trading_day:
            return p, "nyse_calendar"
        p -= timedelta(days=1)
    return prior_weekday(d), "weekday_fallback"


# ── the matcher ────────────────────────────────────────────────────────────────────

def match_tv_item(tv_title: str, our_items: list[dict], *, alert_date: date,
                  prior_trading_day: date, company: set[str]) -> tuple[str, Optional[str]]:
    """(verdict, the title of ours it matched or None). `our_items` = [{title, published}]
    where `published` is an ET-aware datetime or None (undated FMP items count as same-day:
    they came from the grade-time fetch)."""
    tv_norm = normalize_title(tv_title)
    for o in our_items:
        if normalize_title(o["title"]) == tv_norm:
            return "title", o["title"]

    tv_cats = catalyst_classes(tv_title)
    tv_alpha = alpha_anchors(tv_title, company)
    tv_num = numeric_anchors(tv_title)
    tv_usd = {a for a in tv_num if a.startswith("usd:")}
    tv_firm = analyst_firm(tv_title, company) if "analyst" in tv_cats else None

    # story — same catalyst class + a shared anchor; analyst notes need the FIRM; two items
    # that both carry dollar figures and share none are not the same story.
    best: tuple[int, str] | None = None
    for o in our_items:
        shared_cls = (tv_cats & catalyst_classes(o["title"])) - {"earnings"}
        if not shared_cls:
            continue
        o_alpha = alpha_anchors(o["title"], company)
        o_num = numeric_anchors(o["title"])
        shared_alpha, shared_num = tv_alpha & o_alpha, tv_num & o_num
        if "analyst" in shared_cls:
            ok = tv_firm is not None and tv_firm == analyst_firm(o["title"], company)
        else:
            ok = bool(shared_alpha or shared_num)
        o_usd = {a for a in o_num if a.startswith("usd:")}
        if ok and tv_usd and o_usd and not (tv_usd & o_usd):
            ok = False
        if ok:
            score = len(shared_alpha) + len(shared_num) + (1 if "analyst" in shared_cls else 0)
            if best is None or score > best[0]:
                best = (score, o["title"])
    if best:
        return "story", best[1]

    same_day = [o for o in our_items
                if o.get("published") is None
                or is_same_day_item(o["published"], alert_date, prior_trading_day)]

    # event — one company, one results event per day; a preview on our side does not count.
    if "earnings" in tv_cats:
        for o in same_day:
            if "earnings" in catalyst_classes(o["title"]) and not is_preview(o["title"]):
                return "event", o["title"]

    # move — commentary on a day we held a reason for the move.
    if not tv_cats and is_commentary(tv_title):
        for o in same_day:
            if holds_a_catalyst(o["title"]):
                return "move", o["title"]

    # class — same class held today, but nothing proves the same story.
    for o in same_day:
        if tv_cats & catalyst_classes(o["title"]):
            return "class", o["title"]

    return "none", None


# ── the row frame (what build_shadow_row computes from these pieces) ───────────────

def build_frame(*, alert_date: date, prior_trading_day: date, captured_at: Optional[datetime],
                our_items: Optional[list[dict]], tv_items: list[dict], company: set[str]) -> dict:
    """tv_items = [{title, provider, published(unix s)}] — the whole returned window.
    our_items = None when no corpus exists. Returns the new columns of the shadow row.
    Column semantics: module docstring, "TWO STORED LISTS, ONE RULE"."""
    ps = period_start(alert_date, prior_trading_day)
    cutoff = datetime.combine(alert_date, _TV_ACTIONABLE_CUTOFF_ET, tzinfo=_ET)
    out: dict[str, Any] = {
        "our_captured_at": captured_at,
        "tv_coverage_reaches_period_start": None, "tv_unseen_minutes_at_period_start": None,
        "tv_items_before_grade": None, "tv_items_in_repoll_window": None,
        "tv_items_after_cutoff": None, "tv_match_summary": None,
        "tv_items_unmatched_seen": None, "tv_items_we_missed": None,
    }
    if tv_items:
        oldest = datetime.fromtimestamp(min(it["published"] for it in tv_items), tz=_ET)
        out["tv_coverage_reaches_period_start"] = oldest <= ps
        out["tv_unseen_minutes_at_period_start"] = (
            0 if oldest <= ps else math.ceil((oldest - ps).total_seconds() / 60))
    else:
        out["tv_coverage_reaches_period_start"] = False

    def bucket(it: dict) -> Optional[str]:
        t = datetime.fromtimestamp(it["published"], tz=_ET)
        if not is_same_day_item(t, alert_date, prior_trading_day):
            return None
        if captured_at is not None and t <= captured_at:
            return "before_grade"
        if t <= cutoff:
            return "repoll_window" if captured_at is not None else None
        return "after_cutoff"

    if captured_at is not None:
        counts = {"before_grade": 0, "repoll_window": 0, "after_cutoff": 0}
        for it in tv_items:
            b = bucket(it)
            if b:
                counts[b] += 1
        out["tv_items_before_grade"] = counts["before_grade"]
        out["tv_items_in_repoll_window"] = counts["repoll_window"]
        out["tv_items_after_cutoff"] = counts["after_cutoff"]

    if our_items is None or captured_at is None:
        return out  # cannot bucket or cannot diff: every diff column stays NULL

    summary = {b: {} for b in ("before_grade", "repoll_window", "after_cutoff")}
    unmatched_seen: list[dict] = []
    verdicts: dict[str, tuple[str, str, Optional[str]]] = {}
    for it in tv_items:
        b = bucket(it)
        if not b:
            continue
        v, matched = match_tv_item(it["title"], our_items, alert_date=alert_date,
                                   prior_trading_day=prior_trading_day, company=company)
        verdicts[it["title"]] = (b, v, matched)
        summary[b][v] = summary[b].get(v, 0) + 1
        if v in ("none", "class") and b in ("before_grade", "repoll_window"):
            unmatched_seen.append({"title": it["title"], "provider": it["provider"],
                                   "published": it["published"], "bucket": b,
                                   "class": primary_class(it["title"]), "match": v})
    out["tv_match_summary"] = summary
    out["_verdicts"] = verdicts  # proof-only; not a column
    out["tv_items_unmatched_seen"] = unmatched_seen
    # The DoD column: a list ONLY when the window reaches the period start. A rolled window
    # keeps NULL here even when unmatched_seen is non-empty — the reader takes confirmed
    # misses on rolled windows from tv_items_unmatched_seen, reported separately.
    out["tv_items_we_missed"] = (unmatched_seen if out["tv_coverage_reaches_period_start"]
                                 else None)
    return out


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


# Which key carries the publish time in each source's stored item (collector.py):
# get_polygon_news -> `published_utc`, get_alpaca_news -> `created_at` (both ISO strings),
# get_fmp_news (a yfinance wrapper; FMP itself is paywalled) -> NO date at all. An item with no
# usable date is `published=None`, and the matcher treats an undated item as same-day (it came
# from the grade-time fetch) - see match_tv_item.
_RAW_PUBLISHED_KEY = {"polygon": "published_utc", "alpaca": "created_at", "fmp": None}


def _published_et(v: Any) -> Optional[datetime]:
    """An ISO-8601 string off a stored news item -> ET-aware datetime, or None when it is
    absent / not a string / unparseable. A naive value is read as UTC (every stored source
    writes UTC). Never raises."""
    if not isinstance(v, str) or not v.strip():
        return None
    try:
        dt = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_ET)


def _items_from_raw(raw: Any, published_key: Optional[str]) -> list[dict]:
    """One of the stored raw_{polygon,alpaca,fmp}_news_json columns (mi_ep_catalyst_metrics, or
    mi_ep_grade_corpus's alpaca_json / fmp_json) -> [{"title", "published"}], `published` an
    ET-aware datetime or None. All three are stored VERBATIM from collector.get_polygon_news /
    get_alpaca_news / get_fmp_news, which already normalize every source to a `title` key.
    Defensive against every shape surprise (NULL column, a JSON-encoded string the codec didn't
    auto-decode, a non-list, a non-dict item, a missing/blank title): each degrades to being
    skipped, never a guess. `published_key` is the source's date key (`_RAW_PUBLISHED_KEY`), or
    None for a source that carries no dates."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for r in raw:
        if isinstance(r, dict):
            t = r.get("title")
            if isinstance(t, str) and t.strip():
                out.append({"title": t,
                            "published": _published_et(r.get(published_key)) if published_key else None})
    return out


def _provider_counts(items: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for it in items:
        counts[it["provider"]] = counts.get(it["provider"], 0) + 1
    return counts


# The columns `build_frame` computes (besides `our_captured_at`, which comes straight from the
# corpus). All NULL whenever no frame can be computed.
_FRAME_COLS = (
    "tv_coverage_reaches_period_start", "tv_unseen_minutes_at_period_start",
    "tv_items_before_grade", "tv_items_in_repoll_window", "tv_items_after_cutoff",
    "tv_match_summary", "tv_items_unmatched_seen", "tv_items_we_missed",
)


def build_shadow_row(
    alert: dict, corpus: Optional[dict], mic: str, symbol: Optional[str],
    skip_reason: Optional[str], fetch_result: "tuple[Any, Optional[Exception]] | None",
) -> dict:
    """Pure assembly of ONE mi_tv_news_shadow row from already-fetched inputs — kept
    separate from the I/O (snapshot_ticker) so the whole comparison/classification
    logic is unit-testable without a network or a DB. `fetch_result` is
    `(payload, None)` on a successful GET, `(None, exc)` on a raised exception, or
    `None` when no fetch was attempted at all (the exchange never resolved).

    `alert` = a `db.get_tv_shadow_population` row: `catalyst_quality` is the RAW grade (None
    when the provenance row is absent); `acting_grade` / `acting_rule` are the grade that
    acted and the lattice rule behind it. `corpus` = a `db.get_grade_corpus` dict (or None):
    besides the raw news columns it carries `captured_at` (when the grade read this corpus),
    `company_name`, `polygon_available` and `source` ('grade_corpus' | 'metrics').

    The comparison frame (module docstring, "TWO LISTS, ONE RULE") is computed only when a
    corpus AND its `captured_at` exist. Without them every frame column is NULL ("cannot
    tell"), never a zero."""
    ticker, alert_date = alert["ticker"], alert["alert_date"]
    row: dict[str, Any] = {
        "ticker": ticker,
        "alert_date": alert_date,
        "catalyst_quality": alert.get("catalyst_quality"),
        "our_has_direct_source": alert.get("has_direct_source"),
        "our_source_class_count": alert.get("source_class_count"),
        # The grade that ACTED and the lattice rule behind it are properties of the ALERT, not
        # of the diff - carried whether or not a corpus exists.
        "our_acting_grade": alert.get("acting_grade"),
        "our_acting_rule": alert.get("acting_rule"),
        "our_captured_at": None,
        "our_corpus_source": None,
        "exchange_mic": mic,
        "tv_symbol": symbol,
    }

    our_items: Optional[list[dict]] = None
    captured_at: Optional[datetime] = None
    company: set[str] = set()
    if corpus is None:
        row["our_corpus_available"] = False
        row["our_polygon_count"] = None
        row["our_alpaca_count"] = None
        row["our_fmp_count"] = None
        row["our_perplexity_present"] = None
        row["our_total_item_count"] = None
    else:
        polygon_items = _items_from_raw(corpus.get("raw_polygon_news_json"),
                                        _RAW_PUBLISHED_KEY["polygon"])
        alpaca_items = _items_from_raw(corpus.get("raw_alpaca_news_json"),
                                       _RAW_PUBLISHED_KEY["alpaca"])
        fmp_items = _items_from_raw(corpus.get("raw_fmp_news_json"), _RAW_PUBLISHED_KEY["fmp"])
        # A grade-corpus row has NO Polygon side of its own (Polygon is fetched only inside
        # extract_earnings_metrics): its Polygon list is borrowed from that ticker-day's
        # mi_ep_catalyst_metrics row, and `polygon_available` is False exactly when there is no such
        # row. "Not captured" is NULL, never 0 - a 0 would read as "Polygon was checked and held
        # nothing". WITH a metrics row the count is that row's Polygon item count and 0 is an
        # honest zero (its list was NULL or empty). Metrics-only rows keep today's behaviour.
        polygon_available = bool(corpus.get("polygon_available", True))
        row["our_corpus_available"] = True
        row["our_polygon_count"] = len(polygon_items) if polygon_available else None
        row["our_alpaca_count"] = len(alpaca_items)
        row["our_fmp_count"] = len(fmp_items)
        row["our_perplexity_present"] = bool((corpus.get("raw_perplexity_text") or "").strip())
        row["our_total_item_count"] = (
            (len(polygon_items) if polygon_available else 0) + len(alpaca_items) + len(fmp_items))
        row["our_corpus_source"] = corpus.get("source")
        captured_at = corpus.get("captured_at")
        row["our_captured_at"] = captured_at
        if captured_at is None:
            logger.warning(f"tv_news_shadow: corpus for {ticker}/{alert_date} carries no "
                           f"captured_at - the comparison frame is left NULL")
        else:
            our_items = (polygon_items if polygon_available else []) + alpaca_items + fmp_items
            company = company_tokens(corpus.get("company_name"), ticker,
                                     [o["title"] for o in our_items])

    _empty_tv = dict(
        tv_item_count=None, tv_providers=None, tv_oldest_item_published=None,
        tv_coverage_reaches_alert_date=None, tv_items_on_alert_date=None,
        tv_providers_on_alert_date=None, tv_items_we_missed=None,
        tv_coverage_reaches_period_start=None, tv_unseen_minutes_at_period_start=None,
        tv_items_before_grade=None, tv_items_in_repoll_window=None,
        tv_items_after_cutoff=None, tv_match_summary=None, tv_items_unmatched_seen=None,
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

    # HOLIDAY-AWARE prior trading day - NOT shared.dates.last_trading_day, which is weekend-only
    # (for the Tuesday after Labor Day it returns the closed Monday). ONE rule for the same-day
    # count, the period start and the three buckets, so the buckets always sum to
    # tv_items_on_alert_date.
    prior_day, prior_how = prior_trading_day_holiday_aware(alert_date)
    if prior_how != "nyse_calendar":
        logger.warning(f"tv_news_shadow: {ticker}/{alert_date} prior trading day came from the "
                       f"{prior_how} rule, not the NYSE calendar")
    same_day = [it for it in items
                if is_same_day_item(tv_item_et_datetime(it["published"]), alert_date, prior_day)]
    row["tv_items_on_alert_date"] = len(same_day)
    row["tv_providers_on_alert_date"] = _provider_counts(same_day)

    if our_items is not None and captured_at is not None:
        frame = build_frame(alert_date=alert_date, prior_trading_day=prior_day,
                            captured_at=captured_at, our_items=our_items, tv_items=items,
                            company=company)
        frame.pop("_verdicts", None)        # proof-only, not a column
        frame.pop("our_captured_at", None)  # already set from the corpus above
        row.update(frame)
    else:
        # Nothing stored to diff against: every frame column is NULL ("cannot tell"). An empty
        # list here would read as "we checked and missed nothing" (the 2026-09-08 false zero).
        row.update({k: None for k in _FRAME_COLS})

    return row


def classify_run_degradation(summary: dict, trailing_item_counts: list[int]) -> list[str]:
    """Pure decision: which degradation reasons (if any) apply to THIS run. Returns a
    list of short reason strings (possibly empty); the caller joins them into ONE
    `alert_endpoint_shape_anomaly` call per run — see the module docstring's
    "DEGRADATION DETECTION" section for why each threshold is what it is."""
    reasons: list[str] = []

    # A skip is a COVERAGE fact, never a degradation on its own (see
    # `exchange_skip_reasons`'s comment in _run_over_population) — a run where every
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
        corpus = await get_grade_corpus(ticker, alert_date)
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
    """The 10:10 ET mon-fri entry point. Never raises — every stage is wrapped; a
    failure at any stage degrades to a recorded reason and an empty/partial result,
    never an exception into the scheduler (see `_tv_news_shadow_job` in scheduler.py,
    which is belt-and-braces on top of this)."""
    since = today - timedelta(days=_TV_LOOKBACK_DAYS)
    try:
        population = await get_tv_shadow_population(since, today)
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
