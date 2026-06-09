"""Point-in-time grounded-corpus reconstruction for judge validation (#250 / North Star).

Rebuilds the grounded catalyst corpus the LIVE judge WOULD have seen at grade time, for a
historical alert, WITHOUT lookahead — so judge_backfill_replay / eval_judge_models can grade
on FAITHFUL grounded input instead of the thin 500-char stored catalyst (closes #252's
thin-input caveat). READ-ONLY; the reconstructed text is NEVER persisted back to
mi_ep_alerts (reconstructed-after-the-fact ≠ live-captured — #167 hindsight-segregation).

LOOKAHEAD BOUNDARY = detected_at (the grade timestamp), NOT end-of-alert-day. The naive
to_date=alert_date pulls the whole post-gap day (analyst "why X is up" recaps) → inflates
catalyst clarity beyond what was knowable at ~9:45. So:
  - SEC: get_sec_recent_filings, keep filed <= detected_at.date() (date-granular; the
    catalyst 8-K/6-K is filed T-1 eve / T pre-market), nearest filing to the alert.
  - Benzinga (Alpaca news): get_alpaca_news(to_date=alert_date) then DROP any created_at >
    detected_at — the precise pre-grade cut.
  - Web/Perplexity: OMITTED — sonar-pro searches TODAY's web = lookahead.
Mirrors build_grounded_text (SEC body + primary-subject wires) exactly, minus the web layer.

NOTE: this validates GRADE faithfulness, not the live run_ep_scan→_judge_shadow write path
(callers still invoke grade_holistic directly). The integration dimension needs a live alert.
"""
from datetime import date, datetime, timedelta, timezone

from agents.market_intelligence.collector import (
    et_today, get_alpaca_news, get_sec_recent_filings, is_primary_subject_news,
)
from agents.market_intelligence.ep_detector import build_grounded_text


def _to_aware_utc(v):
    """alpaca created_at (ISO str or datetime) → aware UTC datetime, or None."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


async def reconstruct_grounded_text(ticker, alert_date, detected_at, company_name=""):
    """Return (grounded_text|None, info dict). Point-in-time, no lookahead, no web.
    `detected_at` is the tz-aware grade timestamp (mi_ep_alerts.detected_at); when None,
    falls back to end-of-alert-day SEC date only (and no Benzinga time-cut — flagged)."""
    cutoff_date = detected_at.date() if detected_at else alert_date

    # ── SEC (filed <= cutoff_date), nearest filing to the alert ──
    sec_filing = None
    try:
        lb = max((et_today() - alert_date).days + 5, 5)
        filings = await get_sec_recent_filings(
            ticker, forms=("8-K", "6-K"), lookback_days=lb, max_filings=12, want_text=True)
        cands = []
        for f in filings or []:
            try:
                fd = date.fromisoformat(f["filed"])
            except (ValueError, TypeError, KeyError):
                continue
            if alert_date - timedelta(days=10) <= fd <= cutoff_date and f.get("text"):
                cands.append((fd, f))
        if cands:
            cands.sort(key=lambda x: x[0], reverse=True)
            sec_filing = cands[0][1]
    except Exception:
        pass

    # ── Benzinga via Alpaca news, dropping anything created AFTER detected_at ──
    benzinga_items = []
    try:
        news = await get_alpaca_news(ticker, to_date=alert_date, lookback_days=10, limit=30)
        kept = []
        for n in news or []:
            ca = _to_aware_utc(n.get("created_at"))
            if detected_at is not None and ca is not None and ca > detected_at:
                continue  # post-grade lookahead — drop
            if is_primary_subject_news(n, ticker, company_name or ""):
                kept.append(n)
        benzinga_items = kept[:3]
    except Exception:
        pass

    gt = build_grounded_text(sec_filing, benzinga_items, None)  # None = no web (lookahead)
    info = {
        "has_sec": sec_filing is not None,
        "n_benzinga": len(benzinga_items),
        "cutoff": str(detected_at) if detected_at else f"{alert_date} (EOD — no detected_at)",
    }
    return gt, info
