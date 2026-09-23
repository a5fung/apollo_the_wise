"""#622 REDO — Part 1 (honest point-in-time inputs) + feature capture for Part 2
(the sweep that was never done). READ-ONLY measurement. No threshold, filter,
scoring, or config change. Runs against prod DB via the app's own DB pool and
its own functions (`_volume_percentile`, `_score_ep`, ep_rubric weight tables)
-- nothing reimplemented.

WHAT WAS WRONG WITH THE PRIOR STUDY (_622score_driver.py), being fixed here:
  1. `vol_percentile` was hardcoded to 50.0 for all 48 sampled names. CHPT's
     true point-in-time volume conviction was never computed.
  2. `adv_dollar` fed to the scorer was actually the raw SHARE-based `adv`
     column with no `* prev_close` -- mislabeled, not actually dollars.
  3. `gap_pct` (and every other feature) came from each ticker's OWN
     MAX-of-day scan tick (whenever its gap happened to peak that morning --
     for CHPT that was 09:45 ET, gap 49.81%), not a single fixed decision
     moment. Different tickers were effectively measured at different times
     of day, which is not comparable and is lookahead relative to the 09:31
     decision this whole question is about.

THIS SCRIPT: for each of the 154 excluded (mcap_too_small) ticker-days in
`_622sweep_population.json`, reconstructs what the scan saw at ONE fixed
point in time -- the tick closest to 09:31 ET (`minutes_since_open = 1` in
`mi_ep_scan_log`, a real recorded tick, not an approximation) -- and separately
builds an honest volume-conviction percentile from `mi_daily_closes` (see
below for why `mi_stock_scores.adv_20`, the table `_volume_percentile` uses
live, cannot be used honestly here).

TICK SELECTION (documented per row as `tick_source`):
  - `exact_0931`: minutes_since_open = 1 row exists -- used.
  - `nearest_post_open`: no minute-1 row; smallest minutes_since_open > 1 used.
  - `last_premarket`: no post-open row at all; most recent pre-market
    (minutes_since_open IS NULL) row used instead.
  - `missing`: no scan_log row found at all for that ticker/date (should not
    happen for a population selected FROM this table, but checked and
    counted, not assumed).

VOLUME CONVICTION -- WHY mi_daily_closes, NOT mi_stock_scores:
  `ep_detector._volume_percentile` is fed `adv_history` from
  `db.get_volume_history()`, which reads `mi_stock_scores.adv_20` for the
  trailing 60 days. `mi_stock_scores` only carries the top ~2,400 RS-ranked
  names on a given day (CLAUDE.md, RS Scoring section) -- exactly the
  population this cohort is NOT in (that's why they're small-cap rejects, not
  scored control names). Checked directly: CHPT's last `mi_stock_scores` row
  is 2025-12-26/2026-06-15 depending on window -- ZERO rows in the 60 days
  before its 2026-09-03 scan. Feeding that into `_volume_percentile` returns
  50.0 from the function's OWN "unknown history -- neutral" branch (see its
  docstring), not from any default WE chose. That means: for a large slice of
  this exact cohort, the LIVE mechanism would ALSO silently return 50 --
  this is a coverage gap in mi_stock_scores for off-universe names, a second,
  previously-undiscovered problem, reported separately from the vol_percentile
  fix below (see the "instrumentation coverage" section of the summary).

  The brief calls for the INFORMATIVE percentile -- "what would volume
  conviction show if we could see it" -- so we build `adv_history` from
  `mi_daily_closes` directly (always populated, not gated by RS-universe
  membership): a rolling 20-trading-day mean-volume series (matching
  `adv_20`'s definition/shape, NOT raw daily volumes, which are noisier and
  would bias the percentile down), evaluated at each of the trailing ~60
  calendar days strictly BEFORE scan_date. `_volume_percentile` itself is
  used unmodified -- only its input source changes.

  Both readings are captured per row: `vol_pct_live_mechanism` (mi_stock_scores
  path, honest about coverage gaps) and `vol_pct_daily_bars` (the informative
  reconstruction, used in Part 2's sweep).

NO LOOKAHEAD:
  - `today_volume`, `gap_pct`, `rel_volume`, `adv` (shares), `prev_close`,
    `market_cap` all come from the SAME single tick row (the 09:31 tick
    itself, chosen above) -- one moment, not day-max.
  - `adv_history` (both readings) is built from rows STRICTLY BEFORE scan_date.
  - `prior_3m_change`: the EXACT SQL from `ep_detector.py` run_ep_scan
    (DISTINCT ON ticker, trade_date <= scan_date-90 AND >= scan_date-104),
    using the tick's own `prev_close`.
  - regime / theme: the SAME `<` (strictly before) SQL as `_622score_driver.py`
    (that day's own regime/theme rows are written that evening, after the gap).
  - `market_cap` is read from the scan_log tick row itself (computed by the
    SAME `check_filters` call that rejected the ticker that morning) --
    point-in-time by construction, no FMP re-fetch needed.
  - float_shares is a live FMP profile read (static-ish field; does not carry
    price/outcome information -- same simplification `_622score_driver.py`
    used, carried forward and named again here).

CAPTURE ONCE: each row is written to OUT_PATH the instant it's computed,
flushed immediately -- safe to interrupt and resume (skips ticker/dates
already present in OUT_PATH on restart).

Run:
  docker cp scripts/probes/_622sweep_driver.py apollo-market:/tmp/_622sweep_driver.py
  docker cp scripts/probes/_622sweep_population.json apollo-market:/tmp/_622sweep_population.json
  docker exec -w /app apollo-market python /tmp/_622sweep_driver.py
"""
import asyncio
import json
import re
import sys
import traceback
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, "/app")

from agents.market_intelligence import db  # noqa: E402
from agents.market_intelligence.collector import get_fmp_profile  # noqa: E402
from agents.market_intelligence.ep_detector import _volume_percentile  # noqa: E402

_ET = ZoneInfo("America/New_York")

POP_PATH = "/tmp/_622sweep_population.json"
OUT_PATH = "/tmp/_622sweep_features_out.jsonl"

_REGIME_SQL = """
    SELECT regime FROM mi_market_regime
    WHERE regime_date < $1
    ORDER BY regime_date DESC LIMIT 1
"""
_THEME_SQL = """
    SELECT stage, tickers FROM (
        SELECT DISTINCT ON (name) name, stage, tickers, theme_date
        FROM mi_themes
        WHERE theme_date < $1
          AND theme_date >= ($1::date - INTERVAL '7 days')
        ORDER BY name, theme_date DESC
    ) latest
    WHERE stage IN ('Accelerating', 'Mainstream')
"""

_MCAP_RE = re.compile(r"\$(\d+)M\s*<\s*\$500M")

# Nearest-in-wall-clock-time tick to 09:31:00 ET on scan_date. NOT
# minutes_since_open=1 -- that column floors via `max(1, ...)`, so BOTH the
# 09:30:00 market-open-instant tick and the actual 09:31:00 confirmation tick
# read minutes_since_open=1 (discovered on CHPT: two same-minute rows, gap
# 32.95 at 09:30:00 vs 34.68 at 09:31:00) -- an ambiguity real time-distance
# resolves directly. Works for pre-market-only ticker/days too (picks the
# closest pre-market tick; `dist_sec` records how far away it actually was).
_TICK_NEAREST_0931 = """
    SELECT *,
           ABS(EXTRACT(EPOCH FROM (
               (scan_time_et AT TIME ZONE 'America/New_York')
               - ($2::date + TIME '09:31:00')
           ))) AS dist_sec
    FROM mi_ep_scan_log
    WHERE ticker=$1 AND scan_date=$2
    ORDER BY dist_sec ASC, scan_time_et ASC
    LIMIT 1
"""

_DAILY_VOL_SQL = """
    SELECT trade_date, volume FROM mi_daily_closes
    WHERE ticker=$1 AND trade_date < $2
    ORDER BY trade_date DESC LIMIT 140
"""

_PRIOR_3M_SQL = """
    SELECT close FROM mi_daily_closes
    WHERE ticker=$1 AND trade_date <= $2 AND trade_date >= $3
    ORDER BY trade_date DESC LIMIT 1
"""

_STOCK_SCORES_ADV20_SQL = """
    SELECT adv_20 FROM mi_stock_scores
    WHERE ticker=$1 AND score_date >= $2 AND score_date < $3 AND adv_20 IS NOT NULL
    ORDER BY score_date
"""


def _f(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def rolling20_history(daily_rows: list[dict], scan_date: date) -> list[float]:
    """Rolling 20-trading-day mean-volume series (matches adv_20's shape),
    evaluated at each end-date within the 60 calendar days strictly before
    scan_date. `daily_rows` is DESC by trade_date (most recent first)."""
    if len(daily_rows) < 20:
        return []
    asc = list(reversed(daily_rows))  # oldest -> newest
    cutoff = scan_date - timedelta(days=60)
    out = []
    for i in range(19, len(asc)):
        end_date = asc[i]["trade_date"]
        if end_date >= scan_date:
            continue
        if end_date < cutoff:
            continue
        window = asc[i - 19:i + 1]
        out.append(sum(w["volume"] for w in window) / 20.0)
    return out


async def process_one(pool, scan_date_str: str, ticker: str) -> dict:
    scan_date = date.fromisoformat(scan_date_str)
    rec = {"scan_date": scan_date_str, "ticker": ticker}

    async with pool.acquire() as conn:
        row = await conn.fetchrow(_TICK_NEAREST_0931, ticker, scan_date)
        if row is None:
            rec["tick_source"] = "missing"
            return rec

        dist_sec = float(row["dist_sec"]) if row["dist_sec"] is not None else None
        rec["tick_dist_from_0931_sec"] = dist_sec
        rec["tick_source"] = (
            "exact_0931" if dist_sec is not None and dist_sec <= 30
            else "nearest_other_tick"
        )
        rec["scan_time_et"] = row["scan_time_et"].astimezone(_ET).isoformat() if row["scan_time_et"] else None
        rec["minutes_since_open"] = row["minutes_since_open"]
        rec["gap_pct_0931"] = _f(row["gap_pct"])
        rec["prev_close_0931"] = _f(row["prev_close"])
        rec["rel_volume_0931"] = _f(row["rel_volume"])

        # `today_volume` the dedicated column only started being persisted
        # 2026-08-31 (same ship as `market_cap`) -- but `rel_volume` and `adv`
        # (shares) were ALREADY being written from day one of this population
        # (2026-06-08), and rel_volume IS `round(today_volume / adv, 2)`
        # computed live (ep_detector.py ~3792) -- so for earlier rows the
        # exact same point-in-time volume is recoverable by inverting that
        # rounding: today_volume = rel_volume * adv. Precision loss is the
        # 2-decimal rounding on rel_volume (worst case ~1% of adv, a few
        # thousand shares on this cohort's ADVs) -- immaterial for ranking
        # against ADV history that spans orders of magnitude.
        _tv_col = row["today_volume"]
        _rv, _advs = _f(row["rel_volume"]), _f(row["adv"])
        if _tv_col is not None:
            rec["today_volume_0931"] = _tv_col
            rec["today_volume_source"] = "column"
        elif _rv is not None and _advs:
            rec["today_volume_0931"] = round(_rv * _advs)
            rec["today_volume_source"] = "derived_from_relvol_x_adv"
        else:
            rec["today_volume_0931"] = None
            rec["today_volume_source"] = "missing"
        rec["projected_vol_multiple_0931"] = _f(row["projected_vol_multiple"])
        rec["adv_shares_0931"] = _f(row["adv"])
        rec["float_shares_scanlog_0931"] = _f(row["float_shares"])
        rec["filter_reason"] = row["filter_reason"]

        # market_cap column only populated from 2026-08-31 (#605) -- for
        # earlier dates (most of this population), parse the exact same
        # point-in-time dollar figure `check_filters` already put into the
        # filter_reason string it wrote that morning (rounded to the nearest
        # $1M -- e.g. "$134M < $500M"). Cross-checked against the dedicated
        # column on rows that have both: exact match (CHPT $134,408,704 ->
        # "$134M", 134.4 rounds to 134).
        mcap_col = _f(row["market_cap"])
        mcap_parsed = None
        m = _MCAP_RE.search(row["filter_reason"] or "")
        if m:
            mcap_parsed = float(m.group(1)) * 1e6
        mcap_source = (
            "scan_log_column" if mcap_col is not None
            else ("filter_reason_parsed" if mcap_parsed is not None else None)
        )
        # Fallback: the tick nearest 09:31 sometimes failed a DIFFERENT filter
        # (session_rvol_too_low, top-20 gap cap, ...) before check_filters
        # even reached the mcap check that specific moment, even though this
        # ticker/day qualified for the population via SOME tick that day.
        # Market cap does not move materially intraday (same shares
        # outstanding, price moves a few % at most) -- reuse the nearest-in-
        # time SAME-DAY row that DID carry the mcap string.
        if mcap_col is None and mcap_parsed is None:
            other_rows = await conn.fetch(
                "SELECT market_cap, filter_reason, "
                "ABS(EXTRACT(EPOCH FROM ((scan_time_et AT TIME ZONE 'America/New_York') "
                "- ($2::date + TIME '09:31:00')))) AS dist_sec "
                "FROM mi_ep_scan_log WHERE ticker=$1 AND scan_date=$2 ORDER BY dist_sec ASC",
                ticker, scan_date,
            )
            for orow in other_rows:
                oc = _f(orow["market_cap"])
                if oc is not None:
                    mcap_col, mcap_source = oc, "scan_log_column_other_tick_same_day"
                    break
                om = _MCAP_RE.search(orow["filter_reason"] or "")
                if om:
                    mcap_parsed = float(om.group(1)) * 1e6
                    mcap_source = "filter_reason_parsed_other_tick_same_day"
                    break
        rec["market_cap_0931"] = mcap_col if mcap_col is not None else mcap_parsed
        rec["market_cap_source"] = mcap_source or "missing"
        rec["adv_dollar_0931"] = (
            round(rec["adv_shares_0931"] * rec["prev_close_0931"], 2)
            if rec["adv_shares_0931"] and rec["prev_close_0931"] else None
        )

        # ── volume conviction: two readings ──
        daily_rows = await conn.fetch(_DAILY_VOL_SQL, ticker, scan_date)
        daily_rows = [dict(r) for r in daily_rows]
        rec["n_daily_bars_before"] = len(daily_rows)
        adv_hist_daily = rolling20_history(daily_rows, scan_date)
        rec["n_adv20_windows_daily_bars"] = len(adv_hist_daily)
        tv = rec["today_volume_0931"] or 0
        rec["vol_pct_daily_bars"] = _volume_percentile(tv, adv_hist_daily) if tv else None

        cutoff60 = scan_date - timedelta(days=60)
        ss_rows = await conn.fetch(_STOCK_SCORES_ADV20_SQL, ticker, cutoff60, scan_date)
        adv_hist_live = [float(r["adv_20"]) for r in ss_rows]
        rec["n_adv20_rows_mi_stock_scores"] = len(adv_hist_live)
        rec["vol_pct_live_mechanism"] = _volume_percentile(tv, adv_hist_live) if tv else None

        # ── prior 3-month change (exact ep_detector.py SQL) ──
        target = scan_date - timedelta(days=90)
        p3 = await conn.fetchrow(_PRIOR_3M_SQL, ticker, target, target - timedelta(days=14))
        if p3 and p3["close"] and rec["prev_close_0931"]:
            rec["prior_3m_change_0931"] = round(
                (rec["prev_close_0931"] - float(p3["close"])) / float(p3["close"]) * 100, 2)
        else:
            rec["prior_3m_change_0931"] = None

        # ── regime / theme, strictly before scan_date ──
        rg = await conn.fetchrow(_REGIME_SQL, scan_date)
        rec["regime_label"] = rg["regime"] if rg else None
        rec["regime_multiplier"] = 1.2 if rec["regime_label"] == "Bull" else 1.0

        th_rows = await conn.fetch(_THEME_SQL, scan_date)
        rec["in_active_theme"] = any(ticker in (r["tickers"] or []) for r in th_rows)

    # ── float (FMP, live read — static-ish field, no outcome leak; see module docstring) ──
    try:
        profile = await get_fmp_profile(ticker) or {}
    except Exception:
        profile = {}
    try:
        rec["float_shares_fmp_now"] = float(profile["floatShares"]) if profile.get("floatShares") is not None else None
    except (TypeError, ValueError):
        rec["float_shares_fmp_now"] = None
    rec["company_name"] = profile.get("companyName", "")

    return rec


async def main():
    with open(POP_PATH) as f:
        population = json.load(f)

    done = set()
    try:
        with open(OUT_PATH) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    done.add((r["scan_date"], r["ticker"]))
                except Exception:
                    pass
    except FileNotFoundError:
        pass

    pool = await db.get_pool()
    n_ok, n_err, n_skip = 0, 0, 0
    with open(OUT_PATH, "a") as out:
        for i, item in enumerate(population):
            key = (item["scan_date"], item["ticker"])
            if key in done:
                n_skip += 1
                continue
            try:
                rec = await process_one(pool, item["scan_date"], item["ticker"])
                out.write(json.dumps(rec, default=str) + "\n")
                out.flush()
                n_ok += 1
                print(f"[{i+1}/{len(population)}] {item['ticker']} {item['scan_date']}: "
                      f"tick={rec.get('tick_source')} dist={rec.get('tick_dist_from_0931_sec')} "
                      f"gap={rec.get('gap_pct_0931')} "
                      f"vol_pct_daily={rec.get('vol_pct_daily_bars')} "
                      f"vol_pct_live={rec.get('vol_pct_live_mechanism')} "
                      f"mcap={rec.get('market_cap_0931')} ({rec.get('market_cap_source')})")
            except Exception as e:
                n_err += 1
                print(f"[{i+1}/{len(population)}] ERROR {item['ticker']} {item['scan_date']}: {e}")
                traceback.print_exc()

    print(f"DONE ok={n_ok} err={n_err} skip={n_skip} total={len(population)} -> {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
