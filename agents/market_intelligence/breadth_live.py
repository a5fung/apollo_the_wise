"""#723 — LIVE market breadth: the Today view of the dashboard's Market Breadth page, recounted every
15 minutes during the session from real-time Alpaca SIP snapshots against the nightly reference.

His ask (2026-11-08): "market breadth should be live" · "Only today needs to be live". So ONLY the
Today numbers move here — new highs / new lows, advances / declines, the ecosystem groups' and the
themes' 1-day returns. 1W / 1M / YTD and the Weinstein stages stay the nightly snapshot's.

SSoT: docs/architecture/market_breadth_snapshot.md §"Live breadth (#723)" — every rule, the file
contract, the delivery path. Design: docs/design/723_live_breadth_design_2026-11-09.md.

THE SHAPE
  reference  logs/apollo_breadth_reference.json — written by the nightly export
             (scripts/export_breadth_reference.sql via auto_export_snapshots.sh) and copied to the
             host's logs/ dir, which docker-compose.prod.yml bind-mounts at /app/logs. Per ticker:
             [prev_close, hi252, lo252, hl_eligible, in_universe, theme indexes] + the active themes
             and their groups. Stale (not as of the previous trading day) => this job writes NOTHING
             and audits why — an old reference would count every name against the wrong close.
  live       logs/breadth_live/apollo_breadth_live.json — written here, atomically, each refresh.
  push       scripts/push_breadth_live.sh on the HOST (cron, every minute; the container has no git,
             no ssh and no deploy key) force-pushes that one file as a single orphan commit to the
             `live-breadth` branch of portfolio-app2 and records push_status.json beside it; this job
             reads that status on its next refresh and audits a push that failed or never happened.

RULES (the nightly's, applied to today's bar)
  universe        the reference's in_universe names (CS + ADRC that closed >= $1.00 on as_of).
  missing         a universe name Alpaca did not return, or returned without a daily bar DATED
                  TODAY (ET) carrying a close. Counted (missing_n, adv_dec.missing), never guessed —
                  a stale bar from an earlier day would otherwise read as "unchanged".
  advance/decline today's bar close vs the REFERENCE prev_close (never Alpaca's previous_daily_bar,
                  which pre-open deterministically holds T-2 — the #490 finding). no_prior = a
                  universe name with no prev_close, as in the nightly.
  new high / low  today's high >= hi252 / today's low <= lo252, for names that are hl_eligible in the
                  reference AND have a usable bar today (high and low > 0) — the nightly's two halves.
  groups / themes equal-weighted 1-day return over today's members with both closes, counted once
                  per member (the reference's stocks map is one row per ticker), rounded to 2
                  decimals; n_1d = members that had the data; up_1d (groups) = positive returns.
                  Same field names as the nightly's Today fields.

FAILURE DISCIPLINE  every run writes ONE audit row (counts + timing); a failed refresh (fetch, compute,
write) is audited and counted; the THIRD straight failure in a session re-raises once so audit_wrap's
record_job_failure pages — never the first, never every run. A success resets the streak.

Display only. No money path: nothing here feeds a trade, a grade, an alert or any sizing.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
REPO = Path(__file__).resolve().parents[2]          # /app in the container, the repo on a laptop

JOB_ID = "breadth_live_refresh"
LIVE_NAME = "apollo_breadth_live.json"
REFERENCE_NAME = "apollo_breadth_reference.json"
STATUS_NAME = "push_status.json"
ENV_LIVE_DIR = "APOLLO_BREADTH_LIVE_DIR"
ENV_REFERENCE_PATH = "APOLLO_BREADTH_REFERENCE_PATH"

WINDOW_START = (9, 45)     # first refresh (the opening 15 minutes are too thin to count)
WINDOW_END = (16, 0)       # last refresh = the close
PAGE_AFTER_STRAIGHT_FAILURES = 3
PUSH_LAG_TOLERANCE_S = 5 * 60   # a live file older than this and not pushed => the pusher is down

# audit event names (one writer each; constants here rather than audit_events.py, which collects 2+-caller names)
EVT_REFRESH = "breadth_live_refresh"
EVT_REFRESH_FAILED = "breadth_live_refresh_failed"
EVT_REFERENCE_STALE = "breadth_live_reference_stale"
EVT_PUSH_LAGGING = "breadth_live_push_lagging"


class BreadthLiveError(RuntimeError):
    """A refresh that produced nothing — the reason is the message (audited by the caller)."""


class StaleReference(BreadthLiveError):
    """The reference is not as of the previous trading day (or is missing / unreadable)."""


# ── paths ────────────────────────────────────────────────────────────────────────────────────────

def live_dir() -> Path:
    return Path(os.environ.get(ENV_LIVE_DIR) or REPO / "logs" / "breadth_live")


def reference_path() -> Path:
    return Path(os.environ.get(ENV_REFERENCE_PATH) or REPO / "logs" / REFERENCE_NAME)


# ── schedule ─────────────────────────────────────────────────────────────────────────────────────

def in_refresh_window(now_et: datetime) -> bool:
    """09:45 <= hh:mm <= 16:00 ET. The cron slot (hour 9-16, every 15 min) fires wider; this is the
    rule, enforced in code — the repo's idiom (_position_coverage_check_job)."""
    hm = (now_et.hour, now_et.minute)
    return WINDOW_START <= hm <= WINDOW_END


# ── reference ────────────────────────────────────────────────────────────────────────────────────

def load_reference(path: Path | None = None) -> dict:
    p = path or reference_path()
    try:
        ref = json.loads(p.read_text())
    except FileNotFoundError:
        raise StaleReference(f"reference missing at {p} — the nightly export has not placed it")
    except Exception as e:  # loud-ok: a half-written or corrupt reference is reported as stale, never counted against
        raise StaleReference(f"reference unreadable at {p}: {type(e).__name__}: {e}")
    if not isinstance(ref, dict) or "as_of" not in ref or not isinstance(ref.get("stocks"), dict):
        raise StaleReference(f"reference at {p} lacks as_of / stocks")
    return ref


def reference_staleness(ref: dict, today: date) -> str | None:
    """None when the reference is as of the previous trading day before `today`; else the reason."""
    from agents.market_intelligence.trading_calendar import previous_trading_day
    want = previous_trading_day(today)
    as_of = str(ref.get("as_of") or "")
    if as_of == want.isoformat():
        return None
    return f"reference as_of {as_of or '?'} but the previous trading day before {today.isoformat()} is {want.isoformat()}"


# ── the arithmetic ───────────────────────────────────────────────────────────────────────────────

def _et_date_of(ts) -> date | None:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return (ts if ts.tzinfo else ts.replace(tzinfo=ZoneInfo("UTC"))).astimezone(_ET).date()
    try:
        s = str(ts).replace("Z", "+00:00")
        return _et_date_of(datetime.fromisoformat(s))
    except Exception:  # loud-ok: an unparseable stamp is "not today" — the name is counted missing, never guessed
        return None


def _num(x) -> float | None:
    """A finite positive number, or None (a NaN / None / zero high never enters a test)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v > 0 else None


def compute_live(ref: dict, snaps: dict[str, dict], today: date) -> dict:
    """Pure: the reference + Alpaca snapshots + today's ET date -> the live file's numbers."""
    stocks: dict = ref["stocks"]
    themes: list = ref.get("themes") or []
    ecosystems: list = ref.get("ecosystems") or []

    universe_n = read_n = 0
    eligible_n = new_highs = new_lows = 0
    advances = declines = unchanged = no_prior = 0
    theme_members: dict[int, int] = {}            # idx -> distinct members (the reference lists each once)
    theme_rets: dict[int, list[float]] = {}
    ticker_ret: dict[str, float] = {}             # ticker -> today's 1-day return in percent
    ticker_idxs: dict[str, list[int]] = {}

    for ticker, row in stocks.items():
        prev_close, hi252, lo252, hl_eligible, in_universe, idxs = row
        idxs = list(idxs or [])
        ticker_idxs[ticker] = idxs
        for i in idxs:
            theme_members[i] = theme_members.get(i, 0) + 1

        sn = snaps.get(ticker) or {}
        close = _num(sn.get("daily_bar_close")) if _et_date_of(sn.get("daily_bar_ts")) == today else None
        high = _num(sn.get("daily_bar_high")) if close is not None else None
        low = _num(sn.get("daily_bar_low")) if close is not None else None
        prev = _num(prev_close)

        if close is not None and prev is not None:
            r = (close / prev - 1.0) * 100.0
            ticker_ret[ticker] = r
            for i in idxs:
                theme_rets.setdefault(i, []).append(r)

        if not in_universe:
            continue
        universe_n += 1
        if close is None:
            continue                                   # missing: counted below, never guessed
        read_n += 1
        if prev is None:
            no_prior += 1
        elif close > prev:
            advances += 1
        elif close < prev:
            declines += 1
        else:
            unchanged += 1
        if hl_eligible and high is not None and low is not None:
            eligible_n += 1
            h252, l252 = _num(hi252), _num(lo252)
            if h252 is not None and high >= h252:
                new_highs += 1
            if l252 is not None and low <= l252:
                new_lows += 1

    def _mean(xs: list[float]) -> float | None:
        return round(sum(xs) / len(xs), 2) if xs else None

    themes_1d = []
    for t in themes:
        i = int(t["idx"])
        rets = theme_rets.get(i, [])
        themes_1d.append({"idx": i, "name": t.get("name"), "n_members": theme_members.get(i, 0),
                          "ret_1d": _mean(rets), "n_1d": len(rets)})

    ecosystems_1d = []
    for e in ecosystems:
        wanted = set(int(i) for i in (e.get("theme_idx") or []))
        members = [tk for tk, idxs in ticker_idxs.items() if wanted.intersection(idxs)]   # unique by construction
        rets = [ticker_ret[tk] for tk in members if tk in ticker_ret]
        ecosystems_1d.append({"code": e.get("code"), "name": e.get("name"), "n_members": len(members),
                              "ret_1d": _mean(rets), "n_1d": len(rets),
                              "up_1d": sum(1 for r in rets if r > 0)})

    return {
        "universe_n": universe_n,
        "read_n": read_n,
        "missing_n": universe_n - read_n,
        "highs_lows": {"eligible_n": eligible_n, "new_highs": new_highs, "new_lows": new_lows},
        "adv_dec": {"advances": advances, "declines": declines, "unchanged": unchanged,
                    "no_prior": no_prior, "missing": universe_n - read_n},
        "ecosystems_1d": ecosystems_1d,
        "themes_1d": themes_1d,
    }


# ── the live file + the push status ──────────────────────────────────────────────────────────────

def blob_sha(data: bytes) -> str:
    """git's blob id for `data` — what push_breadth_live.sh records, so the two sides agree on 'pushed'."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def write_live(payload: dict, directory: Path | None = None) -> Path:
    d = directory or live_dir()
    d.mkdir(parents=True, exist_ok=True)
    out = d / LIVE_NAME
    tmp = d / f"{LIVE_NAME}.tmp"
    tmp.write_text(json.dumps(payload, separators=(",", ":"), default=str) + "\n")
    os.replace(tmp, out)
    return out


def push_problem(directory: Path | None = None, now_ts: float | None = None) -> str | None:
    """Did the LAST live file get published? None when it did (or when there is nothing yet / it is too
    fresh to judge); otherwise one line saying what is wrong, for the audit row."""
    d = directory or live_dir()
    live = d / LIVE_NAME
    if not live.exists():
        return None
    age = (now_ts if now_ts is not None else time.time()) - live.stat().st_mtime
    if age < PUSH_LAG_TOLERANCE_S:
        return None
    want = blob_sha(live.read_bytes())
    status_path = d / STATUS_NAME
    if not status_path.exists():
        return f"live file is {int(age // 60)} min old and no push has ever been recorded — is the host cron for push_breadth_live.sh installed?"
    try:
        st = json.loads(status_path.read_text())
    except Exception as e:  # loud-ok: an unreadable status is itself the finding
        return f"push_status.json unreadable: {type(e).__name__}: {e}"
    if st.get("blob") != want:
        return (f"live file is {int(age // 60)} min old but the last push ({st.get('at')}) was of an earlier file"
                + (f" — last error: {st.get('error')}" if st.get("error") else ""))
    if not st.get("ok"):
        return f"last push at {st.get('at')} FAILED: {st.get('error') or 'no error text'}"
    return None


# ── one refresh ──────────────────────────────────────────────────────────────────────────────────

async def _fetch_snapshots(tickers: list[str]) -> tuple[dict[str, dict], dict]:
    from agents.market_intelligence.collector import get_alpaca_snapshots_batch
    stats: dict = {}
    snaps = await get_alpaca_snapshots_batch(tickers, timeout_s=6.0, concurrency=1, stats=stats)
    return snaps, stats


async def refresh_once(now_et: datetime, today: date, *, fetch=None, ref_path: Path | None = None,
                       out_dir: Path | None = None) -> dict:
    """The whole refresh: reference -> staleness -> snapshots -> numbers -> file. Returns the numbers plus
    timings; raises StaleReference (nothing written) or BreadthLiveError (fetch produced nothing)."""
    from agents.market_intelligence.db import log_audit_event

    t0 = time.monotonic()
    lag = push_problem(out_dir)
    if lag:
        await log_audit_event(EVT_PUSH_LAGGING, f"live breadth not published: {lag}"[:300],
                              json.dumps({"problem": lag, "dir": str(out_dir or live_dir())}))

    ref = load_reference(ref_path)
    stale = reference_staleness(ref, today)
    if stale:
        raise StaleReference(stale)

    tickers = sorted(ref["stocks"].keys())
    snaps, stats = await (fetch or _fetch_snapshots)(tickers)
    t_fetch = time.monotonic() - t0
    if not snaps:
        raise BreadthLiveError(f"Alpaca returned no snapshots for {len(tickers)} names "
                               f"(batches {stats.get('batches_failed', '?')}/{stats.get('batches_total', '?')} failed)")

    numbers = compute_live(ref, snaps, today)
    payload = {
        "version": 1,
        "as_of": now_et.astimezone(_ET).strftime("%Y-%m-%dT%H:%M:%S") + " ET",
        "reference_as_of": ref["as_of"],
        **numbers,
    }
    write_live(payload, out_dir)
    total = time.monotonic() - t0
    hl, ad = numbers["highs_lows"], numbers["adv_dec"]
    await log_audit_event(
        EVT_REFRESH,
        (f"{payload['as_of']} vs {ref['as_of']}: universe {numbers['universe_n']}, read {numbers['read_n']}, "
         f"missing {numbers['missing_n']}; highs {hl['new_highs']} lows {hl['new_lows']} of {hl['eligible_n']}; "
         f"adv {ad['advances']} dec {ad['declines']} unch {ad['unchanged']}; "
         f"{len(numbers['ecosystems_1d'])} groups, {len(numbers['themes_1d'])} themes; "
         f"fetch {t_fetch:.1f}s total {total:.1f}s, batches failed {stats.get('batches_failed', 0)}")[:300],
        json.dumps({"fetch_s": round(t_fetch, 2), "total_s": round(total, 2), "stats": stats,
                    "universe_n": numbers["universe_n"], "read_n": numbers["read_n"]}),
    )
    return {**numbers, "fetch_s": t_fetch, "total_s": total}


# ── the scheduled entry ──────────────────────────────────────────────────────────────────────────

_streak: dict = {"date": None, "n": 0}


def _streak_bump(today: date) -> int:
    if _streak["date"] != today:
        _streak["date"], _streak["n"] = today, 0
    _streak["n"] += 1
    return _streak["n"]


def _streak_reset(today: date) -> None:
    _streak["date"], _streak["n"] = today, 0


async def run_scheduled(now_et: datetime | None = None, **refresh_kwargs) -> int:
    """The job body under audit_wrap. Returns read_n (rows for mi_job_runs) or 0 when nothing ran.
    Raises ONLY on the third straight failure of the day — that one raise is the page."""
    from agents.market_intelligence.db import log_audit_event
    from agents.market_intelligence.trading_calendar import get_market_status
    from shared.dates import et_today

    now = now_et or datetime.now(_ET)
    if not in_refresh_window(now):
        return 0
    today = et_today()
    if not get_market_status(today).is_trading_day:
        return 0
    try:
        result = await refresh_once(now, today, **refresh_kwargs)
    except Exception as e:  # loud-ok: audited below; the third straight failure re-raises (the page)
        n = _streak_bump(today)
        reason = f"{type(e).__name__}: {e}"
        evt = EVT_REFERENCE_STALE if isinstance(e, StaleReference) else EVT_REFRESH_FAILED
        logger.warning(f"{JOB_ID}: refresh {n} straight failure(s) today — {reason}")
        await log_audit_event(evt, f"live breadth not refreshed ({n} straight): {reason}"[:300],
                              json.dumps({"straight_failures": n, "reason": reason[:500]}))
        if n == PAGE_AFTER_STRAIGHT_FAILURES:
            raise BreadthLiveError(
                f"{n} straight live-breadth refreshes failed today; last: {reason}. "
                f"The breadth page shows the last close until a refresh succeeds.") from e
        return 0
    _streak_reset(today)
    return int(result["read_n"])
