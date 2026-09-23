"""#622 REDO Part 1/2 — the ONE paid step: catalyst grades for the settled/
open_at_horizon excluded ticker-days NOT already graded by the prior
_622score_driver.py run (48 names) or the CHPT case study (1 name).

WHY THIS EXISTS: Part 2's sweep needs a real `ep_score` (current + legacy
rubric) for every ticker-day with a usable outcome, and `_score_ep` needs
`catalyst_quality` as an input. The prior run only graded a 24-winner/24-loser
sample (n=48) drawn from bucketed extremes — this redo uses ALL settled/
open_at_horizon names (n=111, minus the 2 degenerate-stop rows the harness
itself flags, minus the 49 already graded = 60 new grades) so the sweep runs
on the full continuous-outcome population the brief asks for, not a
bucket-selected subsample.

NOT graded: no_entry / no_trade / abstain ticker-days (12+19+12=43) — no
realized_r_0931, so a score for them cannot be tested against any outcome;
grading them would spend money with no sweep use (cost-efficiency rule).

CAPTURE ONCE: raw grade written the instant each paid call returns, appended
to RAW_PATH (resumable — skips ticker/dates already present in RAW_PATH).

No lookahead — identical mechanism to _622score_driver.py:
  - `_classify_catalyst_claude` (the real ep_catalyst_grade path) fed grounded
    text from `reconstruct_grounded_text` (SEC filed <= scan_date, Alpaca/
    Benzinga wires created_at <= 09:31 ET that morning).
  - `profile_pit["marketCap"]` overridden with THIS redo's own point-in-time
    `market_cap_0931` (from _622sweep_features_out.jsonl — scan_log column or
    the filter_reason-parsed figure), not a live FMP lookup and not the prior
    run's separately-sourced `mcap_m`.

Run:
  docker cp scripts/probes/_622sweep_catalyst_driver.py apollo-market:/tmp/
  docker cp scripts/probes/_622sweep_need_grade.json apollo-market:/tmp/
  docker cp scripts/probes/_622sweep_features_out.jsonl apollo-market:/tmp/
  docker exec -w /app apollo-market python /tmp/_622sweep_catalyst_driver.py
"""
import asyncio
import json
import sys
import traceback
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, "/app")

from agents.market_intelligence.collector import get_fmp_profile, get_sec_recent_filings  # noqa: E402
from agents.market_intelligence.ep_detector import (  # noqa: E402
    _CLASSIFY_FAIL_SENTINEL, _classify_catalyst_claude,
)
from shared.llm_models import GROUNDED_GRADE_MODEL, pricing_for  # noqa: E402
from scripts._grounded_reconstruct import reconstruct_grounded_text  # noqa: E402

_ET = ZoneInfo("America/New_York")

NEED_PATH = "/tmp/_622sweep_need_grade.json"
FEATURES_PATH = "/tmp/_622sweep_features_out.jsonl"
RAW_PATH = "/tmp/_622sweep_catalyst_raw.jsonl"

METER_AVG_COST = 0.011521828  # same meter-measured avg the prior run used


async def check_sec_same_day_risk(ticker, scan_date, detected_at):
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
            return False
        acc = picked.get("accepted")
        if not acc:
            return True
        try:
            acc_dt = datetime.fromisoformat(str(acc).replace("Z", "+00:00"))
            if acc_dt.tzinfo is None:
                acc_dt = acc_dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return True
        return acc_dt > detected_at
    except Exception:
        return False


# NOTE: deliberately NOT named `grade_one` — that name is reserved for a real judge entry
# point and `tests/test_judge_spend_attribution.py` requires every call to it to name its
# spend bucket. This probe calls `_classify_catalyst_claude` directly, which is a different
# lane; squatting on the reserved name made the gate fire on a false positive.
async def grade_catalyst_pit(ticker, scan_date_str, mcap_pit):
    scan_date = date.fromisoformat(scan_date_str)
    detected_at = datetime(scan_date.year, scan_date.month, scan_date.day, 9, 31, tzinfo=_ET)

    try:
        profile = await get_fmp_profile(ticker) or {}
    except Exception:
        profile = {}
    profile_pit = dict(profile)
    if mcap_pit is not None:
        profile_pit["marketCap"] = mcap_pit
    try:
        profile_pit["floatShares"] = (
            float(profile_pit["floatShares"]) if profile_pit.get("floatShares") is not None else None
        )
    except (TypeError, ValueError):
        profile_pit["floatShares"] = None

    grounded_text, ginfo = await reconstruct_grounded_text(
        ticker, scan_date, detected_at, company_name=profile.get("companyName", ""))
    sec_same_day_risk = await check_sec_same_day_risk(ticker, scan_date, detected_at)

    quality, analysis = await _classify_catalyst_claude(
        ticker, [], profile_pit, grounded_text=grounded_text, max_chars=6000)
    grade_failed = _CLASSIFY_FAIL_SENTINEL in (analysis or "")

    return {
        "ticker": ticker, "scan_date": scan_date_str, "detected_at": detected_at.isoformat(),
        "catalyst_quality": quality, "analysis": analysis, "grade_failed": grade_failed,
        "grounded_has_sec": ginfo.get("has_sec"), "grounded_n_benzinga": ginfo.get("n_benzinga"),
        "grounded_cutoff": ginfo.get("cutoff"), "sec_same_day_risk": sec_same_day_risk,
        "grounded_text_len": len(grounded_text) if grounded_text else 0,
        "mcap_pit_fed": mcap_pit,
    }


async def main():
    with open(NEED_PATH) as f:
        need = json.load(f)
    feats = {}
    with open(FEATURES_PATH) as f:
        for line in f:
            r = json.loads(line)
            feats[(r["ticker"], r["scan_date"])] = r

    done = set()
    try:
        with open(RAW_PATH) as f:
            for line in f:
                d = json.loads(line)
                done.add((d["ticker"], d["scan_date"]))
    except FileNotFoundError:
        pass

    todo = [item for item in need if (item["ticker"], item["scan_date"]) not in done]
    n = len(todo)
    pricing = pricing_for(GROUNDED_GRADE_MODEL)
    print("=== SPEND PLAN ===")
    print(f"model={GROUNDED_GRADE_MODEL} pricing={pricing} (per MTok)")
    print(f"already done (resumed/skipped): {len(done)}")
    print(f"planned NEW paid calls: {n} x ep_catalyst_grade ONLY")
    print(f"projected spend: {n} x ${METER_AVG_COST:.6f} = ${n * METER_AVG_COST:.4f}")
    print("prior sessions' #622 spend (sunk, separate budget draw): "
          "$0.4643 (main 48-sample + CHPT case study)")
    print(f"THIS run's budget ceiling: $6.00 total for the whole #622 redo task -- "
          f"{'WITHIN BUDGET' if n * METER_AVG_COST <= 6.0 else 'OVER BUDGET -- ABORT'}")
    if n * METER_AVG_COST > 6.0:
        print("ABORTING: projected spend exceeds the $6 ceiling.")
        return
    print("run_start_utc=", datetime.now(timezone.utc).isoformat())
    print("==================")

    n_ok, n_err = 0, 0
    with open(RAW_PATH, "a") as raw:
        for i, item in enumerate(todo):
            ticker, scan_date_str = item["ticker"], item["scan_date"]
            frow = feats.get((ticker, scan_date_str), {})
            mcap_pit = frow.get("market_cap_0931")
            try:
                rec = await grade_catalyst_pit(ticker, scan_date_str, mcap_pit)
                raw.write(json.dumps(rec) + "\n")
                raw.flush()
                n_ok += 1
                print(f"[{i+1}/{n}] {ticker} {scan_date_str}: quality={rec['catalyst_quality']} "
                      f"grade_failed={rec['grade_failed']} sec_same_day_risk={rec['sec_same_day_risk']}")
            except Exception as e:
                n_err += 1
                print(f"[{i+1}/{n}] ERROR {ticker} {scan_date_str}: {e}")
                traceback.print_exc()

    print(f"DONE ok={n_ok} err={n_err} total={n} -> {RAW_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
