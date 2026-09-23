"""#622 follow-on ("does our catalyst/EP scorer separate small-cap winners from
small-cap garbage?") -- READ-ONLY measurement, no threshold/filter/scoring-code
changes. Operator's own idea: score the 90 days we already have, at end of day,
with point-in-time inputs, instead of waiting 60 days for a forward sample.

WHY THIS SCRIPT EXISTS: rejected (<$500M market cap) EP candidates are NEVER
SCORED live -- the quality filter drops them before the catalyst grader or the
rubric ever runs, so `ep_score` is empty on all of them. This reconstructs, for
a balanced winner/loser sample, EXACTLY what our own scorer would have said,
using ONLY information knowable at 09:31 ET on the scan date.

NO LOOKAHEAD:
  - Catalyst grounded text: `scripts._grounded_reconstruct.reconstruct_grounded_text`
    (the #250 judge-validation tool) -- SEC 8-K/6-K filed <= alert_date, Alpaca/
    Benzinga wires created_at <= detected_at (09:31 ET that morning). Web/
    Perplexity synthesis is NOT run at all (can't be pinned to a past date --
    task constraint #2) -- so there is no "contaminated" leg to flag; it's
    simply absent from every row.
  - SEC's own filter is DATE-granular (filed <= cutoff date), not time-of-day --
    a same-day 8-K accepted at 2pm would pass it. We additionally fetch each
    filing's real `accepted` timestamp (SEC submissions API exposes it) and flag
    `sec_same_day_risk=True` whenever the SELECTED filing is dated == scan_date
    AND its acceptance time is missing or after 09:31 ET, so those rows can be
    read with that caveat rather than silently trusted.
  - Market cap fed to the grader/scorer is the POINT-IN-TIME `mcap_m` column
    from `_622_features_out.txt` (captured during the #622 replay), NOT a live
    FMP lookup -- avoids feeding the "is this catalyst material vs company
    size" judgment a market cap the stock only reached after the fact.
  - Regime multiplier and theme membership are read from `mi_market_regime` /
    `mi_themes` STRICTLY BEFORE scan_date. Both jobs run in the evening nightly
    pull (theme ~18:05 ET, regime earlier in the same pull) -- the scan_date's
    OWN row for either table is written that EVENING, after the gap; at 09:31 ET
    that morning only the PRIOR day's row exists. This mirrors live exactly:
    `ep_detector.get_latest_regime()` takes MAX(regime_date) with no filter,
    which at premarket-scan time can only resolve to yesterday's row for the
    same reason.
  - Company name/sector/description (FMP, live) are the only "now" reads --
    used purely as descriptive context for the grading prompt (what business
    is this), which does not leak future price/outcome information.

REAL ENTRY POINTS USED, NOT REIMPLEMENTED:
  - `ep_detector._classify_catalyst_claude` -- the actual `ep_catalyst_grade`
    LLM call (GROUNDED_GRADE_MODEL, tool-forced, fail-open to "routine" with
    `_CLASSIFY_FAIL_SENTINEL` in the analysis text on a real transport failure --
    tracked separately as `grade_failed=True`, never silently counted as a
    genuine "routine" verdict).
  - `ep_detector._score_ep` -- computed against BOTH `ep_rubric.SCORE_WEIGHTS`
    (current live table, separation ON, #533 2026-08-22) as `ep_score`, AND
    `ep_rubric.SCORE_WEIGHTS_LEGACY` (the table live before 8/22) as
    `ep_score_legacy` -- free (pure function), and 46 of 48 sampled scan dates
    predate 8/22, so this answers both "does TODAY's scorer separate them" and
    "would the scorer that was ACTUALLY live on each date have separated them"
    from the one paid grade.

CAPTURE ONCE: the raw grade (ticker, scan_date, quality, analysis, grounded-text
provenance) is written to `_622score_raw.jsonl` the INSTANT the paid call
returns, before any further processing that could raise and lose it. The full
per-row record (adds score/breakdown/regime/theme) goes to `_622score_out.jsonl`.

SIMPLIFICATIONS (documented, not hidden):
  - `vol_percentile` defaults to 50.0 (no bonus either way) -- we don't have
    the historical ADV-distribution percentile the live scan computes;
    max effect on the rubric is +/-5 pts and is not directionally biased
    toward winners or losers.
  - `catalyst_metrics_extractor` (the earnings Q-rev rubric gate) is NOT run
    -- it only fires on earnings-day strong/game_changer catalysts and can
    only DOWNGRADE; skipping it means a small number of earnings-catalyst
    scores may be a slight upper bound. Not expected to change the headline.
  - The LOAD-BEARING holistic judge (`ep_grade_judge.grade_holistic`), which
    can override score_tier including all the way to suppression ('none'),
    is OUT OF SCOPE here -- this measures the SCORE (the artifact named in
    the task), not the full live judge override chain. Flagged in the report
    as a possible next step, not decided here.

Run:
  docker cp scripts/probes/_622score_driver.py apollo-market:/tmp/_622score_driver.py
  docker cp scripts/probes/_622score_sample.json apollo-market:/tmp/_622score_sample.json
  docker cp scripts/probes/_622_features_out.txt apollo-market:/tmp/_622_features_out.txt
  docker exec -w /app apollo-market python /tmp/_622score_driver.py
"""
import asyncio
import json
import sys
import traceback
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, "/app")

from agents.market_intelligence import db  # noqa: E402
from agents.market_intelligence.collector import (  # noqa: E402
    get_fmp_profile, get_sec_recent_filings,
)
from agents.market_intelligence.ep_detector import (  # noqa: E402
    _CLASSIFY_FAIL_SENTINEL, _classify_catalyst_claude, _score_ep,
)
from agents.market_intelligence.ep_rubric import (  # noqa: E402
    SCORE_WEIGHTS, SCORE_WEIGHTS_LEGACY,
)
from shared.llm_models import GROUNDED_GRADE_MODEL, pricing_for  # noqa: E402
from scripts._grounded_reconstruct import reconstruct_grounded_text  # noqa: E402

_ET = ZoneInfo("America/New_York")

FEATURES_PATH = "/tmp/_622_features_out.txt"
SAMPLE_PATH = "/tmp/_622score_sample.json"
RAW_PATH = "/tmp/_622score_raw.jsonl"
OUT_PATH = "/tmp/_622score_out.jsonl"

# ── the exact point-in-time DB reads (both free, no LLM cost) ──
# `<` not `<=`: both mi_market_regime and mi_themes get their scan_date row
# written THAT EVENING (the nightly pull, theme ~18:05 ET) -- at 09:31 ET the
# newest row for either table is still the PRIOR day's.

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


def _f(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def load_features(path):
    feats = {}
    header = None
    with open(path) as fh:
        for line in fh:
            line = line.rstrip("\n")
            if "|" not in line:
                continue  # skips the "Pager usage is off." line
            parts = line.split("|")
            if parts[0] == "scan_date":
                header = parts
                continue
            row = dict(zip(header, parts))
            feats[(row["ticker"], row["scan_date"])] = row
    return feats


async def get_regime_multiplier(conn, scan_date):
    row = await conn.fetchrow(_REGIME_SQL, scan_date)
    label = row["regime"] if row else None
    return (1.2 if label == "Bull" else 1.0), label


async def get_in_active_theme(conn, ticker, scan_date):
    rows = await conn.fetch(_THEME_SQL, scan_date)
    for r in rows:
        if ticker in (r["tickers"] or []):
            return True
    return False


async def check_sec_same_day_risk(ticker, scan_date, detected_at):
    """True if the nearest SEC 8-K/6-K reconstruct_grounded_text would pick is
    DATED scan_date and its real acceptance time is unknown or after 09:31 ET
    (reconstruct_grounded_text's own filter is date-granular -- see module
    docstring). Mirrors its candidate-selection window exactly so "the filing
    it would pick" is the same filing. Fail-open to False (informational flag
    only; a fetch failure here must never block or alter the grade)."""
    try:
        from agents.market_intelligence.collector import et_today
        lb = max((et_today() - scan_date).days + 5, 5)
        filings = await get_sec_recent_filings(
            ticker, forms=("8-K", "6-K"), lookback_days=lb, max_filings=12, want_text=False)
        cands = []
        for f in filings or []:
            try:
                fd = date.fromisoformat(f["filed"])
            except (ValueError, TypeError, KeyError):
                continue
            from datetime import timedelta
            if scan_date - timedelta(days=10) <= fd <= scan_date and f.get("filed"):
                cands.append((fd, f))
        if not cands:
            return False
        cands.sort(key=lambda x: x[0], reverse=True)
        picked_date, picked = cands[0]
        if picked_date != scan_date:
            return False  # picked an earlier filing -- no same-day timing risk
        acc = picked.get("accepted")
        if not acc:
            return True  # same-day filing, no timestamp to clear it -- flag
        try:
            acc_dt = datetime.fromisoformat(str(acc).replace("Z", "+00:00"))
            if acc_dt.tzinfo is None:
                acc_dt = acc_dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return True
        return acc_dt > detected_at
    except Exception:
        return False  # fail-open: informational flag, never blocks the grade


async def score_one(pool, ticker, scan_date_str, row):
    scan_date = date.fromisoformat(scan_date_str)
    detected_at = datetime(scan_date.year, scan_date.month, scan_date.day, 9, 31, tzinfo=_ET)

    try:
        profile = await get_fmp_profile(ticker) or {}
    except Exception:
        profile = {}

    mcap_m = _f(row.get("mcap_m"))
    profile_pit = dict(profile)
    if mcap_m is not None:
        profile_pit["marketCap"] = mcap_m * 1e6  # point-in-time override (see module docstring)
    # #173-class trap (FMP can return numeric fields as strings) -- coerce defensively;
    # `_score_ep` does `float_shares > 0` on this raw, uncoerced by the live code either,
    # so a string here would TypeError mid-scoring for this ticker only.
    try:
        profile_pit["floatShares"] = (
            float(profile_pit["floatShares"]) if profile_pit.get("floatShares") is not None else None
        )
    except (TypeError, ValueError):
        profile_pit["floatShares"] = None

    grounded_text, ginfo = await reconstruct_grounded_text(
        ticker, scan_date, detected_at, company_name=profile.get("companyName", ""))

    sec_same_day_risk = await check_sec_same_day_risk(ticker, scan_date, detected_at)

    # ── the ONE paid call: ep_catalyst_grade ──
    quality, analysis = await _classify_catalyst_claude(
        ticker, [], profile_pit, grounded_text=grounded_text, max_chars=6000)
    grade_failed = _CLASSIFY_FAIL_SENTINEL in (analysis or "")

    # CAPTURE ONCE: write the raw grade before any further processing that could raise.
    with open(RAW_PATH, "a") as raw:
        raw.write(json.dumps({
            "ticker": ticker, "scan_date": scan_date_str, "detected_at": detected_at.isoformat(),
            "catalyst_quality": quality, "analysis": analysis, "grade_failed": grade_failed,
            "grounded_has_sec": ginfo.get("has_sec"), "grounded_n_benzinga": ginfo.get("n_benzinga"),
            "grounded_cutoff": ginfo.get("cutoff"), "sec_same_day_risk": sec_same_day_risk,
            "grounded_text_len": len(grounded_text) if grounded_text else 0,
        }) + "\n")
        raw.flush()

    async with pool.acquire() as conn:
        regime_mult, regime_label = await get_regime_multiplier(conn, scan_date)
        in_theme = await get_in_active_theme(conn, ticker, scan_date)

    gap_pct = _f(row.get("max_gap"))
    rel_volume = _f(row.get("rel_vol"))
    proj_vol = _f(row.get("proj_vol"))
    adv_dollar = _f(row.get("adv"))

    _score_kwargs = dict(
        gap_pct=gap_pct,
        rel_volume=rel_volume,
        catalyst_quality=quality,
        profile=profile_pit,
        regime_multiplier=regime_mult,
        vol_percentile=50.0,
        prior_3m_change=None,
        projected_vol_multiple=proj_vol,
        in_active_theme=in_theme,
        adv_dollar=adv_dollar,
    )
    ep_score, breakdown = _score_ep(weights=SCORE_WEIGHTS, **_score_kwargs)
    ep_score_legacy, breakdown_legacy = _score_ep(weights=SCORE_WEIGHTS_LEGACY, **_score_kwargs)

    return {
        "ticker": ticker, "scan_date": scan_date_str,
        "catalyst_quality": quality, "analysis": analysis, "grade_failed": grade_failed,
        "grounded_has_sec": ginfo.get("has_sec"), "grounded_n_benzinga": ginfo.get("n_benzinga"),
        "grounded_cutoff": ginfo.get("cutoff"), "sec_same_day_risk": sec_same_day_risk,
        "gap_pct": gap_pct, "rel_volume": rel_volume, "proj_vol": proj_vol, "adv_dollar": adv_dollar,
        "mcap_m": mcap_m, "regime_label": regime_label, "regime_multiplier": regime_mult,
        "in_active_theme": in_theme,
        "ep_score": ep_score, "breakdown": breakdown,
        "ep_score_legacy": ep_score_legacy, "breakdown_legacy": breakdown_legacy,
    }


async def main():
    feats = load_features(FEATURES_PATH)
    with open(SAMPLE_PATH) as fh:
        sample = json.load(fh)

    keys = [(t, d, "winner") for t, d in sample["winners"]] + \
           [(t, d, "loser") for t, d in sample["losers"]]

    n = len(keys)
    pricing = pricing_for(GROUNDED_GRADE_MODEL)
    # Meter-measured average (last 14 days, `ep_catalyst_grade`, 2026-09-04): $0.011521828/call,
    # 4032 input / 313 output tokens avg -- this IS the only paid call this script makes.
    METER_AVG_COST = 0.011521828
    print(f"=== SPEND PLAN ===")
    print(f"model={GROUNDED_GRADE_MODEL} pricing={pricing} (per MTok)")
    print(f"planned paid calls: {n} x ep_catalyst_grade ONLY "
          f"(no perplexity, no catalyst_metrics_extractor, no ep_grade_judge)")
    print(f"projected spend: {n} x ${METER_AVG_COST:.6f} (14d meter avg) "
          f"= ${n * METER_AVG_COST:.4f}")
    print(f"budget ceiling: $6.00 -- {'WITHIN BUDGET' if n * METER_AVG_COST <= 6.0 else 'OVER BUDGET -- ABORT'}")
    if n * METER_AVG_COST > 6.0:
        print("ABORTING: projected spend exceeds the $6 ceiling.")
        return
    print("run_start_utc=", datetime.now(timezone.utc).isoformat())
    print("==================")

    pool = await db.get_pool()
    results = []
    n_ok, n_err = 0, 0
    with open(OUT_PATH, "w") as out:
        for i, (ticker, scan_date_str, label) in enumerate(keys):
            row = feats.get((ticker, scan_date_str))
            if row is None:
                print(f"[{i+1}/{n}] SKIP {ticker} {scan_date_str}: no features row")
                n_err += 1
                continue
            try:
                rec = await score_one(pool, ticker, scan_date_str, row)
                rec["label"] = label
                results.append(rec)
                out.write(json.dumps(rec) + "\n")
                out.flush()
                n_ok += 1
                print(f"[{i+1}/{n}] {ticker} {scan_date_str} ({label}): "
                      f"quality={rec['catalyst_quality']} ep_score={rec['ep_score']} "
                      f"ep_score_legacy={rec['ep_score_legacy']} "
                      f"grade_failed={rec['grade_failed']} sec_same_day_risk={rec['sec_same_day_risk']}")
            except Exception as e:
                n_err += 1
                print(f"[{i+1}/{n}] ERROR {ticker} {scan_date_str}: {e}")
                traceback.print_exc()

    print(f"DONE ok={n_ok} err={n_err} total={n} -> {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
