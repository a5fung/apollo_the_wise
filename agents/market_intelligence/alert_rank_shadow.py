"""2026-08-16 — ALERT-RANK SHADOW RECORDER.

docs/roadmap/ep_profitability_program.md §0d found a three-feature ranking rule (smaller
gap · tighter EP day · less MA-distance extension, averaged as three ascending percentile
ranks) that puts 16 of the 26 tradeable >=10R winners in its top quartile — a 2.5x lift.
But the three features were chosen ON the same data they were tested against, 13 of the 26
targets sit on ONE session, and a true time holdout is impossible today. Operator's own
framing (docs/analysis/expectedness_and_ranking_2026-08-16.txt SUMMARY, fork F-2):

    "log the rank next to each alert and re-read at N>=10 winner-sessions"

**RECORD THE RANK, NOT A RULE CHANGE.** This module writes one row per `mi_ep_alerts` row
(every alert, HIGH or not, filled or not — never just the ones we traded), scoring it two
ways:

  EOD    — exactly as tested: the full day's gap/range/extension, from `mi_daily_closes`
           once today's row exists. This is the version with the measured 2.5x lift.
  AS-OF-09:45 — the same three features computed from ONLY what a 09:45 ORB decision could
           have known: the opening print and the 09:30-09:45 range from `mi_intraday_bars`,
           never the full day's high/low. THE SUBTLETY THAT DEFINES THIS MODULE: the EOD
           rule's tightness feature is (day high - day low) / day high, which is NOT known
           until the close — the rule as validated cannot be evaluated at 09:45. Nobody has
           measured whether it survives being made real-time; this module is how we find out.

Mid-task addition (operator, via the coordinator, 2026-08-16): "can we pivot to intraday
tightness using similar criteria for the EP day?" — the live entry gate already computes one
intraday tightness measure (`backtester/filters.py::validate_orb_entry`'s ORB-range-over-ATR14
ratio, used ONLY to reject wide stops, never to rank). Four additional as-of-09:45 tightness
variants are recorded per alert (including REJECTED ones — the live gate never sees an alert
it rejects again, so this is the only place that population's shape gets measured):
  - `orb_range_over_atr14`  — the live gate's own ratio (duplicated formula, see below).
  - `orb_range_over_adr20`  — the same ratio in ADR20 units, comparable to every other
                               normalised figure in this program.
  - `open_range_position`   — where the 09:45 price sits within the opening range.
  - `bar_contraction`       — mean true range of the last 5 one-minute bars over the first
                               5, within the opening window. THIS IS OUR OWN DEFINITION, not
                               a house-derived one — no existing primitive in this repo
                               computes bar-level contraction at 1-minute resolution; see
                               `compute_bar_contraction`'s docstring for exactly what it is.
These four are recorded as STANDALONE columns, never folded into the ranked composite — the
composite must stay gap/tightness/extension exactly, or the shadow stops testing the
published rule.

THE LINE — read this before touching anything here. This module is a passive OBSERVER:
  - It has EXACTLY ONE write target: `mi_alert_rank_shadow` (plus `mi_audit_log` via the
    shared `log_audit_event` telemetry helper — never a trade-state or grading table).
  - It NEVER writes to `mi_ep_alerts`, `mi_live_trades`, or any column any grading, entry,
    sizing, or ordering decision reads. It never calls the Alpaca client, `order_manager`,
    `entry_pipeline`, `ep_detector`'s admission path, or the judge.
  - It reads `mi_ep_alerts`, `mi_ep_catalyst_metrics`, `mi_daily_closes`, `mi_intraday_bars`,
    and `mi_live_trades` (read-only) — all read paths already used elsewhere in this
    codebase for telemetry/backtesting.
  - It imports NOTHING from `broker/` — not even `entry_pipeline.py` or
    `backtester/filters.py`'s `validate_orb_entry`/`compute_atr_14`, even though
    `backtester/filters.py` is itself imported by the LIVE `broker/order_manager.py` (so it
    is not a safely "offline-only" module to lean on). `_atr14_prior` below DUPLICATES
    `compute_atr_14`'s Wilder-TR formula rather than importing it — pinned by a byte-parity
    test in tests/test_alert_rank_shadow.py that feeds both functions IDENTICAL prior-only
    rows (never `compute_atr_14(ticker, alert_date)` itself, which would fold in today's own
    gap TR once run after EOD — exactly the leak this module exists to keep out of the
    as-of-09:45 columns). `classify_expectedness` duplicates
    `scripts/probes/_expectedness_and_ranking.py::classify()` rather than importing it: that
    probe module reads multi-MB TSV caches at import time (its own docstring calls them
    "capture-once caches"), fine for a one-shot analysis run and wrong to pull into every
    scheduler tick.
  - Nothing in `broker/`, `ep_detector.py`, or any judge/grading module imports THIS module
    (grep `alert_rank_shadow` — the only hits outside this file + its tests are the
    `mi_alert_rank_shadow` CREATE TABLE in db.py and the one scheduler registration).
  - It runs as an INTELLIGENCE-owned job (see scheduler.py) — same class as
    `exit_path_shadow.py` / `giveback_shadow.py` / `pivot_stop_shadow.py`, which it follows
    in file shape and EOD-timing reasoning (see below).

WHY EOD, AND WHY THE CATCH-UP SCAN. The EOD columns need today's `mi_daily_closes` row,
which the 17:00 ET `nightly_data_pull` job writes — so this runs at 17:53 ET, after that pull
and the 17:xx shadow family (same reasoning as `exit_path_shadow`'s 17:50 slot: `mi_daily_closes`
has no row for today before then). Rather than a per-day walk, this scans for any
`mi_ep_alerts` row (source='live') NOT YET in `mi_alert_rank_shadow`, groups the misses by
`alert_date`, and — for EVERY alert on an affected date, not just the missing ones —
RECOMPUTES and UPSERTs the whole day, because the percentile ranks are a WITHIN-DAY
computation: a late-arriving or previously-unwritten alert changes every other alert's rank
that day. Idempotent (ON CONFLICT alert_id DO UPDATE), safe to re-run. On first deploy this
backfills every live `mi_ep_alerts` row back to the 2026-05-11 purge boundary — immediate N
on the same population `docs/analysis/expectedness_and_ranking_2026-08-16.txt` section [E]
scored, no new capture needed.

RETENTION: kept forever, explicitly absent from `purge_old_data` (db.py) — the exact evidence
class the 2026-08-15 capture audit found being deleted before it could be used, and the
record this ranking rule's out-of-sample validation cannot exist without.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any, Optional

from shared.dates import _ET

from agents.market_intelligence.db import get_pool, log_audit_event

logger = logging.getLogger(__name__)

# Prior-history floor for the MA-distance extension — matches
# scripts/probes/_expectedness_and_ranking.py `cohort_features`'s own gate EXACTLY
# (`if len(prior) < 50: return None`, which then drops the row from the WHOLE ranking pool
# in `score_and_catch`, not just from the extension term). A ticker with 40 prior daily
# closes is excluded from that day's ranking pool here too — never ranked on a fabricated
# or partial extension.
_MIN_PRIOR_BARS = 50
_ADR20_WINDOW = 20
_ATR14_LOOKBACK_DAYS = 35  # matches backtester/filters.py::compute_atr_14's own lookback
_BAR_CONTRACTION_MIN_BARS = 10


def _f(v) -> Optional[float]:
    """None-safe float (asyncpg NUMERIC arrives as Decimal)."""
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _et_0930(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 9, 30, tzinfo=_ET)


def _et_0945(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 9, 45, tzinfo=_ET)


# ═════════════════════════════ pure compute (fixture-testable, no IO) ═══════════════════


def _sma(vals: list[float], k: int) -> Optional[float]:
    """Mean of the LAST k values, None below k — matches
    scripts/probes/_expectedness_and_ranking.py `sma()` exactly."""
    return sum(vals[-k:]) / k if len(vals) >= k else None


def compute_adr20_frac(prior_hlc: list[tuple[float, float, float]]) -> Optional[float]:
    """House ADR20: mean((h-l)/c) over the 20 sessions ending D-1 (part 1 docstring of
    scripts/probes/_expectedness_and_ranking.py: "ADR20 = mean((h-l)/c) over the 20
    sessions ending D-1 (the _552 SQL definition)"). `prior_hlc`: (high, low, close) for
    prior trading days ONLY, oldest-first. A fraction (0.05 = 5%), not a percent — callers
    multiply by a price to get dollars. None below 20 rows or if every close is non-positive."""
    window = prior_hlc[-_ADR20_WINDOW:]
    if len(window) < _ADR20_WINDOW:
        return None
    vals = [(h - l) / c for h, l, c in window if c > 0]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _true_range(high: float, low: float, prev_close: float) -> float:
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def compute_atr14_prior(prior_hlc: list[tuple[float, float, float]]) -> Optional[float]:
    """Wilder ATR-14, a DUPLICATE of backtester/filters.py::compute_atr_14's formula — see
    module docstring for why this is never imported. `prior_hlc`: (high, low, close) for
    PRIOR trading days ONLY (the caller excludes alert_date itself, unlike
    `compute_atr_14(ticker, alert_date)` run post-EOD, which would fold in today's own gap
    TR — the STRL 2026-05-05 lesson cited in `compute_atr_14`'s own docstring, inverted:
    there the miss was UNDER-counting TR; here the risk is a leak of same-day information
    into a column that must answer "what could 09:45 have known"). Requires >=10 rows,
    matching `compute_atr_14`'s own floor exactly."""
    if len(prior_hlc) < 10:
        return None
    trs = []
    for i in range(1, len(prior_hlc)):
        h, l, _ = prior_hlc[i]
        _, _, prev_close = prior_hlc[i - 1]
        trs.append(_true_range(h, l, prev_close))
    if not trs:
        return None
    window = trs[-14:]
    return sum(window) / len(window)


def compute_gap_pct(open_price: Optional[float], prior_close: Optional[float]) -> Optional[float]:
    if open_price is None or prior_close is None or prior_close <= 0:
        return None
    return (open_price - prior_close) / prior_close * 100.0


def compute_tightness_pct(high: Optional[float], low: Optional[float]) -> Optional[float]:
    """(high-low)/high, as a percent. On the EOD version this is the FULL day's range —
    THE SUBTLETY: not knowable until the close. On the as-of-09:45 version, `high`/`low`
    are restricted to the 09:30-09:45 window before this function is ever called."""
    if high is None or low is None or high <= 0:
        return None
    return (high - low) / high * 100.0


def compute_ma_distance_extension(
    open_price: Optional[float], prior_closes: list[float], adr20_frac: Optional[float],
) -> tuple[Optional[float], Optional[bool]]:
    """Median distance of `open_price` above each SMA (10/20/50, computed on
    `prior_closes` through D-1) that sits BELOW the open, in ADR20 units — the definition
    in scripts/probes/_expectedness_and_ranking.py `cohort_features`
    (`median([(o-m)/o/adrf for m in below]) if below else None`), matched exactly.

    Returns (ext, no_ma_below):
      - (None, None)  — insufficient prior history (<50 closes) or invalid inputs; the
        CALLER must exclude this alert from the day's ranking pool entirely (not just
        zero-fill the extension term) — matches `cohort_features` returning None outright.
      - (None, True)  — full history available, but every SMA sits ABOVE the open (the
        stock hasn't extended past any of its own moving averages) — genuinely undefined,
        never silently zero. The PRIMARY "zero" ranking convention from the probe is applied
        ONLY at ranking time (`rank_day_pool`), never here.
      - (value, False) — the ordinary case.
    """
    if (
        len(prior_closes) < _MIN_PRIOR_BARS
        or adr20_frac is None or adr20_frac <= 0
        or open_price is None or open_price <= 0
    ):
        return None, None
    mas = [_sma(prior_closes, k) for k in (10, 20, 50)]
    below = [m for m in mas if m is not None and m < open_price]
    if not below:
        return None, True
    ext = median((open_price - m) / open_price / adr20_frac for m in below)
    return ext, False


def summarize_orb_window(
    bars: list[tuple[float, float, float, float]],
) -> Optional[dict[str, Any]]:
    """`bars`: (open, high, low, close) 1-minute bars, ascending, already restricted to
    [09:30, 09:45) ET by the caller's SQL. None if no bars exist (the coverage-gap case the
    caller flags via `minute_bars_available`)."""
    if not bars:
        return None
    return {
        "open": bars[0][0],
        "high": max(b[1] for b in bars),
        "low": min(b[2] for b in bars),
        "close": bars[-1][3],
        "n": len(bars),
    }


def compute_open_range_position(
    orb_high: Optional[float], orb_low: Optional[float], last_price: Optional[float],
) -> Optional[float]:
    """(last - ORB low) / ORB range at 09:45 — where price sits within the opening range.
    Closing near the high of a TIGHT range is the strength signature the operator named;
    a wide range with price mid-way is not. None on a zero/negative range or missing input."""
    if orb_high is None or orb_low is None or last_price is None:
        return None
    rng = orb_high - orb_low
    if rng <= 0:
        return None
    return (last_price - orb_low) / rng


def compute_orb_range_ratios(
    orb_high: Optional[float], orb_low: Optional[float],
    atr14_prior: Optional[float], adr20_frac: Optional[float], prior_close: Optional[float],
) -> tuple[Optional[float], Optional[float]]:
    """(orb_range/ATR14, orb_range/ADR20-in-dollars). The ATR14 ratio duplicates the LIVE
    entry gate's own formula (`backtester/filters.py::validate_orb_entry`:
    `orb_range > 1.5 * atr_14` rejects) — recorded here for EVERY alert including ones the
    live gate would reject, never read by it. ADR20-in-dollars = adr20_frac * prior_close
    (the last price known before today), for comparability with the extension feature's own
    ADR-unit convention."""
    if orb_high is None or orb_low is None:
        return None, None
    rng = orb_high - orb_low
    over_atr = (rng / atr14_prior) if atr14_prior and atr14_prior > 0 else None
    over_adr = None
    if adr20_frac and adr20_frac > 0 and prior_close and prior_close > 0:
        adr20_dollars = adr20_frac * prior_close
        if adr20_dollars > 0:
            over_adr = rng / adr20_dollars
    return over_atr, over_adr


def compute_bar_contraction(
    bars_hlc: list[tuple[float, float, float]], prior_close: Optional[float],
) -> tuple[Optional[float], int]:
    """OUR OWN definition (operator addition, 2026-08-16) — no existing primitive in this
    repo computes bar-level contraction at 1-minute resolution, so this is stated plainly
    rather than presented as house-derived: mean TRUE RANGE of the LAST 5 one-minute bars
    in the 09:30-09:45 window, over the mean true range of the FIRST 5. <1 = the bars are
    narrowing toward 09:45 (a tightening signature); >1 = widening. Per-bar true range uses
    the PRECEDING bar's close as the reference (prior day's close seeds the very first bar
    of the day) — the same TR anchor `compute_atr_14`/`compute_atr14_prior` use, just
    applied at 1-minute instead of daily resolution; no new convention invented.

    Requires >=10 bars so the first-5/last-5 windows never overlap. Returns (None, n) below
    that floor — `n` is always returned (never hidden) so a NULL is legible as "N bars
    short", not silently indistinguishable from a computed value.
    """
    n = len(bars_hlc)
    if n < _BAR_CONTRACTION_MIN_BARS or prior_close is None:
        return None, n
    trs = []
    prev_close = prior_close
    for h, l, c in bars_hlc:
        trs.append(_true_range(h, l, prev_close))
        prev_close = c
    mean_first = sum(trs[:5]) / 5
    mean_last = sum(trs[-5:]) / 5
    if mean_first <= 0:
        return None, n
    return mean_last / mean_first, n


def _pct_rank(sorted_vals: list[float], v: float) -> float:
    """Ascending percentile: fraction of the population strictly below + half of ties —
    matches scripts/probes/_expectedness_and_ranking.py `pct_rank()` exactly."""
    import bisect
    lo = bisect.bisect_left(sorted_vals, v)
    hi = bisect.bisect_right(sorted_vals, v)
    return (lo + (hi - lo) / 2) / len(sorted_vals)


def rank_day_pool(
    items: list[dict[str, Any]], gap_key: str, tight_key: str, ext_key: str,
    prior_bars_key: str, out_prefix: str, min_prior_bars: int = _MIN_PRIOR_BARS,
) -> int:
    """Mutates `items` in place, adding `{out_prefix}_rank_gap` / `_rank_tight` / `_rank_ext`
    / `_composite` / `_qualifies` keys — percentile ranks computed WITHIN this pool only
    (the tested rule is a WITHIN-DAY ranking; the probe's own [A2] section makes this
    explicit). Returns the qualifying pool size.

    An item qualifies only when gap/tight are both known AND its prior-bar count clears
    `min_prior_bars` — matching `cohort_features`'s all-or-nothing gate (a thin-history
    ticker is excluded from ranking entirely, not partially ranked). Among qualifiers, the
    extension term uses the PRIMARY "zero" convention from
    `score_and_catch(..., ext_mode='zero')` — `None` (no MA below the open) becomes 0.0 for
    ranking ONLY; the raw column stored elsewhere keeps the true `None`.
    """
    for it in items:
        it[f"{out_prefix}_rank_gap"] = None
        it[f"{out_prefix}_rank_tight"] = None
        it[f"{out_prefix}_rank_ext"] = None
        it[f"{out_prefix}_composite"] = None
        it[f"{out_prefix}_qualifies"] = False
    qualifying = [
        it for it in items
        if it[gap_key] is not None and it[tight_key] is not None
        and it[prior_bars_key] >= min_prior_bars
    ]
    for it in qualifying:
        it[f"{out_prefix}_qualifies"] = True
    if not qualifying:
        return 0
    gaps = sorted(it[gap_key] for it in qualifying)
    tights = sorted(it[tight_key] for it in qualifying)
    exts = sorted((it[ext_key] if it[ext_key] is not None else 0.0) for it in qualifying)
    for it in qualifying:
        ev = it[ext_key] if it[ext_key] is not None else 0.0
        rg = _pct_rank(gaps, it[gap_key])
        rt = _pct_rank(tights, it[tight_key])
        re_ = _pct_rank(exts, ev)
        it[f"{out_prefix}_rank_gap"] = rg
        it[f"{out_prefix}_rank_tight"] = rt
        it[f"{out_prefix}_rank_ext"] = re_
        it[f"{out_prefix}_composite"] = (rg + rt + re_) / 3
    return len(qualifying)


# ── expectedness axis — VERBATIM port of
# scripts/probes/_expectedness_and_ranking.py::classify() (2026-08-16), see module
# docstring for why duplicated rather than imported. Regex bodies copied unchanged. ──────

_SEC_RE = re.compile(r"\[SEC ([^ \]]+) filed (\d{4}-\d{2}-\d{2}), items ([^\]]*)\]")

_EARN_KW = re.compile(
    r"reported (?:its )?(?:record )?(?:q[1-4]|first|second|third|fourth)[- ]quarter"
    r"|q[1-4] (?:fy)?20\d\d (?:results|earnings|revenue)"
    r"|quarterly (?:results|report)|earnings (?:report|release|call|beat)"
    r"|reported earnings|eps of \$|vs\.? consensus|consensus estimate"
    r"|(?:beat|topped|exceeded)(?:\w|\s|,){0,40}(?:estimate|consensus|expectation)"
    r"|q[1-4] 20\d\d (?:record )?revenue|(?:record )?q[1-4] (?:20\d\d )?(?:revenue|sales|earnings|results)"
    r"|(?:upside )?earnings surprise|q[1-4] fy ?\d{2,4} report|in its q[1-4](?:\w|\s|,){0,20}report",
    re.I)

_FWD_KW = re.compile(
    r"fda[ -](?:granted|approv|clearance|accepted)|accelerated approval|510\(k\)|breakthrough (?:therapy|device)"
    r"|approval of|regulatory (?:approval|clearance)|marketing authori[sz]ation"
    r"|(?:phase (?:3|iii)|pivotal)(?:\w|\s|,){0,60}(?:met|positive|success|primary endpoint|endpoint met)"
    r"|primary (?:pfs )?endpoint (?:was )?met"
    r"|(?:contract|order|lease|agreement|deal)(?:\w|\s|,|\$|\.){0,50}(?:worth|valued|\$\d|million|billion|multi-year|\d+[- ]year)"
    r"|(?:awarded|wins?|won|secured|signed)(?:\w|\s|,){0,40}(?:contract|order|agreement|lease|deal)"
    r"|backlog(?:\w|\s|,){0,40}(?:surge|grew|growth|increase|record|x |times)"
    r"|(?:raised?|raising|hiked?|boosted|lifts?|increased)(?:\w|\s|,){0,30}(?:full[- ]year |fy ?20\d\d |annual )?(?:revenue |sales )?(?:guidance|outlook|forecast)"
    r"|guidance raise|to acquire|to be acquired|merger agreement|definitive (?:merger )?agreement"
    r"|acquisition of|agreed to (?:buy|acquire)|will replace(?:\w|\s|,){0,40}s&p"
    r"|inclusion in the s&p|joins? the s&p|added to the s&p"
    r"|commercial launch|launch of(?:\w|\s|,){0,30}(?:drug|product|platform|service)"
    r"|strategic (?:partnership|collaboration|investment)|partnership with|collaboration with"
    r"|equity (?:investment|stake)|takes? a stake"
    r"|received approval|approval from|regulator(?:\w|\s|,){0,30}approved|formally approved"
    r"|joint development agreement|development agreement|supply (?:agreement|deal|mou)"
    r"|\bmou\b|memorandum of understanding|letter of intent"
    r"|expanding its(?:\w|\s|,){0,50}(?:facility|production|capacity|plant|contract)",
    re.I)

_BWD_KW = re.compile(
    r"reported (?:record )?(?:revenue|net income|sales|eps|profit)"
    r"|(?:revenue|sales|net income|eps)s? (?:of|was|were|reached|came in at) \$"
    r"|record (?:quarter|quarterly|revenue|sales|q[1-4])"
    r"|(?:beat|topped|exceeded)(?:\w|\s|,){0,40}(?:estimate|consensus|expectation)"
    r"|(?:revenue|sales)(?:\w|\s|,){0,30}(?:up|grew|increased|rose) \d{1,4}(?:\.\d+)?%"
    r"|first profitable quarter|profitability milestone|swung to (?:a )?profit"
    r"|(?:upside )?earnings surprise",
    re.I)

_ANALYST_KW = re.compile(
    r"initiated coverage|price target|analyst|upgrad(?:ed?|es) (?:to|from|the)"
    r"|outperform|overweight rating|buy rating|coverage on",
    re.I)

_BEAT_KW = re.compile(
    r"(?:beat|topped|exceeded|above)(?:\w|\s|,|\$|\.){0,40}(?:estimate|consensus|expectation)"
    r"|revenue beat|earnings beat|\$[\d.,]+[mb]? vs\.? \$[\d.,]+[mb]? est"
    r"|(?:upside )?earnings surprise|stronger[- ]than[- ]expected",
    re.I)

_YOY_RE = re.compile(r"(?:up|grew|increased|rose|\+)\s?(\d{1,4}(?:\.\d+)?)%\s?(?:yoy|y/y|year[- ]over[- ]year)", re.I)


def classify_expectedness(
    catalyst: Optional[str], ctype_rationale: Optional[str], judge_rationale: Optional[str],
    grounded_text: Optional[str], yoy: Optional[float],
) -> dict[str, Any]:
    """Deterministic, no LLM, $0 — see module docstring for why this duplicates rather
    than imports `scripts/probes/_expectedness_and_ranking.py::classify()`."""
    text = " ".join([catalyst or "", ctype_rationale or "", judge_rationale or ""])
    gtext = grounded_text or ""
    full = text + " " + gtext[:1500]
    m = _SEC_RE.search(gtext)
    form, items = (m.group(1).upper(), m.group(3)) if m else ("", "")
    has202 = "2.02" in items
    if form.startswith(("10-Q", "10-K")) or (form.startswith(("8-K", "6-K")) and has202):
        sched, sched_src = "scheduled", "filing"
    elif form.startswith("8-K") and items.strip() and not has202:
        sched, sched_src = "unscheduled", "filing"
    elif form.startswith(("425", "S-4", "SC ")):
        sched, sched_src = "unscheduled", "filing"
    elif _EARN_KW.search(full):
        sched, sched_src = "scheduled", "keyword"
    elif _FWD_KW.search(full) or _ANALYST_KW.search(full):
        sched, sched_src = "unscheduled", "keyword"
    else:
        sched, sched_src = "unknown", "none"
    fwd, bwd = bool(_FWD_KW.search(full)), bool(_BWD_KW.search(full))
    if fwd and bwd:
        looking = "mixed_fwd"
    elif fwd:
        looking = "forward"
    elif bwd:
        looking = "backward"
    elif _ANALYST_KW.search(full):
        looking = "analyst_only"
    else:
        looking = "unknown"
    beat = bool(_BEAT_KW.search(full))
    growth = yoy
    growth_src = "stored" if growth is not None else "none"
    if growth is None:
        g = [float(x) for x in _YOY_RE.findall(full)]
        growth = max(g) if g else None
        growth_src = "regex" if g else "none"
    return dict(sched=sched, sched_src=sched_src, looking=looking, beat=beat,
                growth=growth, growth_src=growth_src, sec_form=form, sec_items=items)


# ═════════════════════════════ DB orchestration ═══════════════════════════════════════

_DATES_NEEDING_PROCESSING_SQL = """
    SELECT DISTINCT a.alert_date
    FROM mi_ep_alerts a
    LEFT JOIN mi_alert_rank_shadow s ON s.alert_id = a.id
    WHERE a.source = 'live' AND s.alert_id IS NULL AND a.alert_date <= $1
    ORDER BY a.alert_date
"""

_DAY_ALERTS_SQL = """
    SELECT a.id, a.ticker, a.alert_date, a.score_tier, a.catalyst,
           a.catalyst_type_rationale, a.judge_rationale, a.grounded_text,
           m.q_revenue_yoy_pct AS yoy
    FROM mi_ep_alerts a
    LEFT JOIN mi_ep_catalyst_metrics m
           ON m.ticker = a.ticker AND m.alert_date = a.alert_date
    WHERE a.alert_date = $1 AND a.source = 'live'
    ORDER BY a.id
"""

_TODAY_DAILY_BAR_SQL = """
    SELECT open_price, high_price, low_price, close FROM mi_daily_closes
    WHERE ticker = $1 AND trade_date = $2
"""

_PRIOR_DAILY_ROWS_SQL = """
    SELECT trade_date, close, high_price, low_price FROM mi_daily_closes
    WHERE ticker = $1 AND trade_date < $2 AND trade_date >= $2::date - 100
    ORDER BY trade_date ASC
"""

_ORB_WINDOW_BARS_SQL = """
    SELECT open, high, low, close FROM mi_intraday_bars
    WHERE ticker = $1 AND bar_time >= $2 AND bar_time < $3
    ORDER BY bar_time ASC
"""

_TRADE_STATUS_SQL = """
    SELECT COUNT(*) AS n, COUNT(*) FILTER (WHERE filled_at IS NOT NULL) AS n_filled,
           (ARRAY_AGG(account_mode ORDER BY filled_at NULLS LAST))[1] AS account_mode
    FROM mi_live_trades WHERE ticker = $1 AND alert_date = $2
"""

_UPSERT_COLS = (
    "alert_id", "ticker", "alert_date", "score_tier", "alerted_high",
    "trade_exists", "trade_filled", "account_mode",
    "prior_trading_day", "prior_close", "prior_bars_count",
    "sma10", "sma20", "sma50", "adr20_frac", "atr14_prior",
    "day_open", "day_high", "day_low", "day_close", "day_bar_source",
    "gap_pct_eod", "tightness_pct_eod", "ext_xadr_eod", "ext_no_ma_below_eod",
    "qualifies_for_rank_eod", "rank_gap_eod", "rank_tightness_eod", "rank_ext_eod",
    "composite_rank_eod", "pool_size_eod",
    "minute_bars_available", "minute_bar_count",
    "orb_open_0945", "orb_high_0945", "orb_low_0945", "orb_close_0945",
    "gap_pct_asof0945", "tightness_pct_asof0945", "ext_xadr_asof0945",
    "ext_no_ma_below_asof0945", "qualifies_for_rank_asof0945",
    "rank_gap_asof0945", "rank_tightness_asof0945", "rank_ext_asof0945",
    "composite_rank_asof0945", "pool_size_asof0945",
    "orb_range_over_atr14", "orb_range_over_adr20", "open_range_position",
    "bar_contraction", "bar_contraction_bar_count",
    "expct_scheduled", "expct_scheduled_src", "expct_looking",
    "expct_beat", "expct_growth_yoy_pct", "expct_growth_src",
)
_INSERT_COLS_SQL = ", ".join(_UPSERT_COLS)
_INSERT_PLACEHOLDERS_SQL = ", ".join(f"${i + 1}" for i in range(len(_UPSERT_COLS)))
_UPDATE_SET_SQL = ", ".join(f"{c} = EXCLUDED.{c}" for c in _UPSERT_COLS if c != "alert_id")
_UPSERT_SQL = f"""
    INSERT INTO mi_alert_rank_shadow ({_INSERT_COLS_SQL})
    VALUES ({_INSERT_PLACEHOLDERS_SQL})
    ON CONFLICT (alert_id) DO UPDATE SET {_UPDATE_SET_SQL}, computed_at = NOW()
"""


async def _fetch_daily_bar(
    conn, ticker: str, trading_day: date,
) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float], Optional[str]]:
    """(open, high, low, close, bar_source) for one trading day. `mi_daily_closes` primary;
    Polygon `get_index_history` fallback. All-None when neither source has the day —
    mirrors exit_path_shadow._fetch_daily_bar."""
    row = await conn.fetchrow(_TODAY_DAILY_BAR_SQL, ticker, trading_day)
    if row is not None and row["close"] is not None:
        return _f(row["open_price"]), _f(row["high_price"]), _f(row["low_price"]), float(row["close"]), "daily"
    from agents.market_intelligence.collector import get_index_history
    d_str = trading_day.strftime("%Y-%m-%d")
    try:
        bars = await get_index_history(ticker, d_str, d_str)
    except Exception as e:  # loud-ok: caller records the None outcome
        logger.warning(f"alert_rank_shadow: Polygon fallback failed for {ticker} {trading_day}: {e}")
        bars = []
    if not bars or bars[0].get("c") is None:
        return None, None, None, None, None
    b = bars[0]
    return b.get("o"), b.get("h"), b.get("l"), float(b["c"]), "polygon_fallback"


async def _process_alert_date(conn, alert_date: date) -> int:
    """(Re)compute and UPSERT every `mi_ep_alerts` row for one date. Full pure-DB
    read/compute/write; no broker calls, no grading/trade mutation (THE LINE)."""
    rows = await conn.fetch(_DAY_ALERTS_SQL, alert_date)
    if not rows:
        return 0

    items: list[dict[str, Any]] = []
    for r in rows:
        alert = dict(r)
        ticker = alert["ticker"]

        prior_raw = await conn.fetch(_PRIOR_DAILY_ROWS_SQL, ticker, alert_date)
        # Closes-only series — matches the probe's own >=50 gate EXACTLY
        # (`prior = [bb[4] for bb in seq[:idx]]`, gated on `len(prior) < 50` — closes only,
        # no H/L requirement). Keeping this separate from the H/L series below means a
        # ticker with complete closes but sparse high_price/low_price (real: those columns
        # were backfilled 2026-04-25 via ALTER TABLE ADD COLUMN, so older rows can have a
        # close with NULL H/L) is never wrongly excluded from the ranking pool.
        prior_close_rows = [
            (pr["trade_date"], _f(pr["close"])) for pr in prior_raw if pr["close"] is not None
        ]
        prior_closes = [c for (_d, c) in prior_close_rows]
        prior_trading_day = prior_raw[-1]["trade_date"] if prior_raw else None
        prior_close = prior_close_rows[-1][1] if prior_close_rows else None
        prior_bars_count = len(prior_closes)

        # H/L+close series — needed for ADR20/ATR14 only; independently gated (each
        # returns None below its own floor), never shrinks the SMA/ranking-pool gate above.
        # Carries trade_date alongside each (h,l,c) tuple so the ATR cutoff filter below
        # stays correctly paired with its own row — a positional zip against the
        # close-only list would silently misalign dates once any row lacked H/L (found in
        # review before this shipped).
        prior_hlc_rows = [
            (pr["trade_date"], _f(pr["high_price"]), _f(pr["low_price"]), _f(pr["close"]))
            for pr in prior_raw
            if pr["close"] is not None and pr["high_price"] is not None and pr["low_price"] is not None
        ]
        prior_hlc = [(h, l, c) for (_d, h, l, c) in prior_hlc_rows]

        sma10 = _sma(prior_closes, 10)
        sma20 = _sma(prior_closes, 20)
        sma50 = _sma(prior_closes, 50)
        adr20_frac = compute_adr20_frac(prior_hlc)
        atr_cutoff = alert_date - timedelta(days=1) - timedelta(days=_ATR14_LOOKBACK_DAYS)
        atr_hlc = [(h, l, c) for (d, h, l, c) in prior_hlc_rows if d >= atr_cutoff]
        atr14_prior = compute_atr14_prior(atr_hlc)

        day_open, day_high, day_low, day_close, day_bar_source = await _fetch_daily_bar(
            conn, ticker, alert_date,
        )
        gap_eod = compute_gap_pct(day_open, prior_close)
        tight_eod = compute_tightness_pct(day_high, day_low)
        ext_eod, ext_no_ma_eod = compute_ma_distance_extension(day_open, prior_closes, adr20_frac)

        bars_raw = await conn.fetch(_ORB_WINDOW_BARS_SQL, ticker, _et_0930(alert_date), _et_0945(alert_date))
        bars = [
            (_f(b["open"]), _f(b["high"]), _f(b["low"]), _f(b["close"]))
            for b in bars_raw
            if b["open"] is not None and b["high"] is not None and b["low"] is not None and b["close"] is not None
        ]
        orb = summarize_orb_window(bars)
        minute_bars_available = orb is not None
        minute_bar_count = orb["n"] if orb else 0
        gap_asof = compute_gap_pct(orb["open"], prior_close) if orb else None
        tight_asof = compute_tightness_pct(orb["high"], orb["low"]) if orb else None
        ext_asof, ext_no_ma_asof = (
            compute_ma_distance_extension(orb["open"], prior_closes, adr20_frac) if orb
            else (None, None)
        )

        bars_hlc = [(h, l, c) for (_o, h, l, c) in bars]
        bar_contraction, bar_contraction_n = compute_bar_contraction(bars_hlc, prior_close)
        orb_range_over_atr14, orb_range_over_adr20 = compute_orb_range_ratios(
            orb["high"] if orb else None, orb["low"] if orb else None,
            atr14_prior, adr20_frac, prior_close,
        )
        open_range_position = compute_open_range_position(
            orb["high"] if orb else None, orb["low"] if orb else None, orb["close"] if orb else None,
        )

        cls = classify_expectedness(
            alert.get("catalyst"), alert.get("catalyst_type_rationale"),
            alert.get("judge_rationale"), alert.get("grounded_text"), _f(alert.get("yoy")),
        )

        tstat = await conn.fetchrow(_TRADE_STATUS_SQL, ticker, alert_date)
        trade_exists = bool(tstat["n"]) if tstat else False
        trade_filled = bool(tstat["n_filled"]) if tstat else False
        trade_account_mode = tstat["account_mode"] if tstat else None

        items.append({
            "alert_id": alert["id"], "ticker": ticker, "alert_date": alert_date,
            "score_tier": alert.get("score_tier"),
            "alerted_high": (alert.get("score_tier") == "HIGH"),
            "trade_exists": trade_exists, "trade_filled": trade_filled,
            "account_mode": trade_account_mode,
            "prior_trading_day": prior_trading_day, "prior_close": prior_close,
            "prior_bars_count": prior_bars_count,
            "sma10": sma10, "sma20": sma20, "sma50": sma50,
            "adr20_frac": adr20_frac, "atr14_prior": atr14_prior,
            "day_open": day_open, "day_high": day_high, "day_low": day_low,
            "day_close": day_close, "day_bar_source": day_bar_source,
            "gap_pct_eod": gap_eod, "tightness_pct_eod": tight_eod,
            "ext_xadr_eod": ext_eod, "ext_no_ma_below_eod": ext_no_ma_eod,
            "minute_bars_available": minute_bars_available, "minute_bar_count": minute_bar_count,
            "orb_open_0945": orb["open"] if orb else None,
            "orb_high_0945": orb["high"] if orb else None,
            "orb_low_0945": orb["low"] if orb else None,
            "orb_close_0945": orb["close"] if orb else None,
            "gap_pct_asof0945": gap_asof, "tightness_pct_asof0945": tight_asof,
            "ext_xadr_asof0945": ext_asof, "ext_no_ma_below_asof0945": ext_no_ma_asof,
            "orb_range_over_atr14": orb_range_over_atr14,
            "orb_range_over_adr20": orb_range_over_adr20,
            "open_range_position": open_range_position,
            "bar_contraction": bar_contraction, "bar_contraction_bar_count": bar_contraction_n,
            "expct_scheduled": cls["sched"], "expct_scheduled_src": cls["sched_src"],
            "expct_looking": cls["looking"], "expct_beat": cls["beat"],
            "expct_growth_yoy_pct": cls["growth"], "expct_growth_src": cls["growth_src"],
        })

    pool_size_eod = rank_day_pool(
        items, "gap_pct_eod", "tightness_pct_eod", "ext_xadr_eod", "prior_bars_count", "eod",
    )
    pool_size_asof = rank_day_pool(
        items, "gap_pct_asof0945", "tightness_pct_asof0945", "ext_xadr_asof0945",
        "prior_bars_count", "asof",
    )
    for it in items:
        it["qualifies_for_rank_eod"] = it.pop("eod_qualifies")
        it["rank_gap_eod"] = it.pop("eod_rank_gap")
        it["rank_tightness_eod"] = it.pop("eod_rank_tight")
        it["rank_ext_eod"] = it.pop("eod_rank_ext")
        it["composite_rank_eod"] = it.pop("eod_composite")
        it["pool_size_eod"] = pool_size_eod
        it["qualifies_for_rank_asof0945"] = it.pop("asof_qualifies")
        it["rank_gap_asof0945"] = it.pop("asof_rank_gap")
        it["rank_tightness_asof0945"] = it.pop("asof_rank_tight")
        it["rank_ext_asof0945"] = it.pop("asof_rank_ext")
        it["composite_rank_asof0945"] = it.pop("asof_composite")
        it["pool_size_asof0945"] = pool_size_asof

    written = 0
    for it in items:
        await conn.execute(_UPSERT_SQL, *(it[c] for c in _UPSERT_COLS))
        written += 1
    return written


async def record_alert_rank_shadow(today: Optional[date] = None) -> int:
    """Write/refresh one `mi_alert_rank_shadow` row per `mi_ep_alerts` row (source='live'),
    grouping catch-up work by alert_date so within-day percentile ranks stay consistent.
    Pure DB read/compute/write; no broker calls, no grading/trade mutation (THE LINE — see
    module docstring). Returns rows written/updated."""
    if today is None:
        from agents.market_intelligence.collector import et_today
        today = et_today()

    pool = await get_pool()
    written = 0
    dates: list[date] = []
    async with pool.acquire() as conn:
        date_rows = await conn.fetch(_DATES_NEEDING_PROCESSING_SQL, today)
        dates = [r["alert_date"] for r in date_rows]
        for d in dates:
            try:
                written += await _process_alert_date(conn, d)
            except Exception as e:
                logger.error(f"alert_rank_shadow: alert_date {d} failed: {e}")
                try:
                    await log_audit_event(
                        "alert_rank_shadow_error", f"{d}: {type(e).__name__}: {e}",
                    )
                except Exception:  # loud-ok: log_audit_event self-catches; logger.error above already fired
                    pass
    if written:
        try:
            await log_audit_event(
                "alert_rank_shadow_recorded",
                f"recorded/updated {written} row(s) across {len(dates)} date(s)",
            )
        except Exception as _e:  # loud-ok: telemetry-of-telemetry; the rows are already durable
            logger.warning(f"alert_rank_shadow audit emit failed (non-fatal): {_e}")
    return written
