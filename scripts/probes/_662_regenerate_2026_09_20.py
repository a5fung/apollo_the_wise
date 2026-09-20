"""#662 — regenerate the 2026-09-20 weekly review OFFLINE from the one-time prod capture.

Drives the REAL `run_weekly_review` with every external edge stubbed from
`scripts/probes/_662_capture_2026-09-20.tsv` (captured ONCE, read-only SQL, Sun 2026-09-20 ~10:30
PDT): the stored `mi_system_reviews` row (metrics + the LLM summary it already paid for — the LLM
is NOT re-run), the closed-trade cohort every trailing-window section reads, the setup-review
rollup, the judge-divergence counts, the spend meter, the audit-error rows and the job ledger.
Nothing is sent, nothing is written: `send_telegram_message`, `insert_system_review` and
`log_audit_event` are captured, `get_pool` answers only the spend queries and raises on anything
else, so an unstubbed DB read shows up as a crash rather than a silent blank section.

Run it on the code BEFORE a generator change and again AFTER — the two outputs side by side ARE the
deliverable for a presentation change (the #662 task line). Writes to --out (default /tmp/662):
  <tag>.md      the message as assembled (legacy-Markdown, before the send-boundary conversion)
  <tag>.html    what `send_telegram_message` received
  <tag>.txt     line / char / chunk counts

  python scripts/probes/_662_regenerate_2026_09_20.py --tag old
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CAPTURE = ROOT / "scripts/probes/_662_capture_2026-09-20.tsv"
REVIEW_DATE = date(2026, 9, 20)
# The edition ran at 08:00 ET = 12:00 UTC on 2026-09-20; days_ago maths anchor here.
RUN_AT = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def load_capture(path: Path = CAPTURE) -> dict[str, list[list[str]]]:
    sections: dict[str, list[list[str]]] = {}
    cur = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("===") and raw.endswith("==="):
            cur = raw.strip("=")
            sections[cur] = []
            continue
        if cur is None or not raw.strip():
            continue
        sections[cur].append(raw.split("\t"))
    return sections


def _unesc(s: str) -> str:
    return s.replace("\\n", "\n").replace("\\t", "\t")


def _d(s: str) -> date | None:
    return date.fromisoformat(s) if s else None


def _ts(s: str) -> datetime | None:
    if not s:
        return None
    s = s.replace("+00", "+00:00") if s.endswith("+00") else s
    return datetime.fromisoformat(s)


def _num(s: str):
    return None if s in ("", None) else float(s)


def _dec(s: str):
    return None if s in ("", None) else Decimal(s)


def _fix_dates(obj):
    """The stored metrics JSON carries dates as ISO strings; the missed-opportunities renderer
    calls .strftime on `alert_date`, so restore those (and only those) to `date`."""
    if isinstance(obj, dict):
        return {k: (_d(v) if k == "alert_date" and isinstance(v, str) else _fix_dates(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_fix_dates(x) for x in obj]
    return obj


def build_fixture(sec: dict) -> dict:
    fx: dict = {}
    reviews = {r[1]: r for r in sec["SYSREV"]}
    row = reviews[REVIEW_DATE.isoformat()]
    fx["metrics"] = _fix_dates(json.loads(row[5]))
    fx["summary"] = _unesc(row[4])
    prior = reviews.get("2026-09-13")
    fx["prior"] = ({"review_date": prior[1], "window_days": int(prior[2]), "summary": _unesc(prior[4]),
                    "metrics": json.loads(prior[5]), "suggestions": json.loads(prior[6])}
                   if prior else None)

    trades = []
    for r in sec["TRADES"]:
        (tid, alert_date, signal_type, account_mode, status, total_pnl, risk_actual, shares, entry,
         hard_stop, exit_reason, attribution, peak_r, realized_r, stop_per_adr, peak_source,
         hold_days, ticker) = r
        trades.append({
            "id": int(tid), "alert_date": _d(alert_date), "signal_type": signal_type,
            "account_mode": account_mode, "status": status, "total_pnl": _dec(total_pnl),
            "risk_dollars_actual": _dec(risk_actual), "entry_shares": _num(shares),
            "entry_price": _dec(entry), "hard_stop": _dec(hard_stop), "exit_reason": exit_reason or None,
            "pnl_attribution": attribution or None, "peak_r": _num(peak_r),
            "realized_r": _num(realized_r), "stop_per_adr": _num(stop_per_adr),
            "peak_source": peak_source or None, "hold_days": int(hold_days or 0), "ticker": ticker,
        })
    fx["trades"] = trades

    fx["setup_review"] = []
    for r in sec["SETUP_REVIEW"]:
        (signal_type, account_mode, n, wins, total_pnl, top_exit, n_stop_hit, med_peak_r,
         med_realized_r, ran_then_lost, med_stop_per_adr, blind_peaks, phase) = r
        fx["setup_review"].append({
            "signal_type": signal_type, "account_mode": account_mode, "n": int(n), "wins": int(wins),
            "total_pnl": _dec(total_pnl), "top_exit": top_exit or None, "n_stop_hit": int(n_stop_hit),
            "med_peak_r": _num(med_peak_r), "med_realized_r": _num(med_realized_r),
            "ran_then_lost": int(ran_then_lost), "med_stop_per_adr": _num(med_stop_per_adr),
            "blind_peaks": int(blind_peaks), "phase": phase or None,
        })

    jd = sec["JUDGE_DIV"][0]
    fx["judge_div"] = {"n": int(jd[0]), "n_disagree": int(jd[1]), "n_stricter": int(jd[2]),
                       "n_looser": int(jd[3]), "secondary_model": jd[4] or None}
    total = next(r for r in sec["API_USAGE"] if r[0] == "total")
    fx["spend_total"] = {"calls": int(total[1]), "cost": Decimal(total[2])}
    fx["spend_callers"] = [{"caller": r[0], "cost": Decimal(r[2])}
                           for r in sec["API_USAGE"] if r[0] != "total"]
    fx["safeguards"] = {(r[0], r[1]): r[2] for r in sec["SAFEGUARD"]}
    fx["equity"] = {r[0]: (_dec(r[1]), _dec(r[2])) for r in sec["EQUITY"]}
    fx["err_rows"] = [{"id": int(r[0]), "created_at": _ts(r[1]), "event_type": r[2],
                       "summary": _unesc(r[3]), "detail": _unesc(r[4])} for r in sec["ERR_ROWS"]]
    fx["job_runs"] = [{"job_id": r[0], "started_at": _ts(r[1]), "finished_at": _ts(r[2]),
                       "status": r[3], "scheduled_for": _ts(r[4]), "error_message": r[5]}
                      for r in sec["JOB_RUNS"]]
    fx["budget"] = "150"   # prod ANTHROPIC_MONTHLY_BUDGET, read 2026-09-20 (not a secret)
    return fx


class _FakeConn:
    def __init__(self, fx):
        self.fx = fx

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def fetchrow(self, sql, *args):
        if "api_usage" in sql and "COUNT(*) AS calls" in sql:
            return {"calls": self.fx["spend_total"]["calls"], "cost": self.fx["spend_total"]["cost"]}
        raise RuntimeError(f"unstubbed fetchrow: {sql[:120]!r}")

    async def fetch(self, sql, *args):
        if "api_usage" in sql and "GROUP BY caller" in sql:
            return self.fx["spend_callers"]
        raise RuntimeError(f"unstubbed fetch: {sql[:120]!r}")

    async def fetchval(self, sql, *args):
        raise RuntimeError(f"unstubbed fetchval: {sql[:120]!r}")

    async def execute(self, sql, *args):
        raise RuntimeError(f"REFUSED write during offline regeneration: {sql[:120]!r}")


class _FakePool:
    def __init__(self, fx):
        self.fx = fx

    def acquire(self):
        return _FakeConn(self.fx)


def band_inputs_from(fx: dict, account_mode: str = "live") -> dict:
    """Mirror `kill_scale_bands.assemble_band_inputs` from the captured rows, using the REAL
    `risk_placed` so the R cohort is the one the bands read. Adds `realized_r_eras`/`_meta` for
    the post-#662 code (additive; ignored by the old code)."""
    from agents.market_intelligence.db import OPEN_POSITION_STATUSES
    from agents.market_intelligence.kill_scale_bands import risk_placed
    closed = [t for t in fx["trades"]
              if t["status"] == "closed" and t["account_mode"] == account_mode
              and t["pnl_attribution"] is None]
    closed.sort(key=lambda t: (t["alert_date"], t["id"]))
    rs, meta = [], []
    for t in closed:
        risk = risk_placed(t)
        if risk is None or risk <= 0:
            continue
        rs.append(float(t["total_pnl"]) / risk)
        meta.append({"alert_date": t["alert_date"], "signal_type": t["signal_type"]})
    dd = fx["safeguards"].get(("drawdown_breaker", account_mode))
    tier = {"BLOCK": "BLOCK", "REDUCE": "REDUCE", "WATCH": "WATCH", "TRIPPED": "REDUCE"}.get(
        (dd or "OK").upper(), "OK")
    first_eq, last_eq = fx["equity"].get(account_mode, (None, None))
    open_positions = [{"ticker": t["ticker"], "hold_days": t["hold_days"]}
                      for t in sorted(fx["trades"], key=lambda t: t["alert_date"])
                      if t["status"] in OPEN_POSITION_STATUSES and t["account_mode"] == account_mode]
    return {"realized_rs": rs, "realized_r_meta": meta, "drawdown_tier": tier,
            "equity_above_start": (first_eq is not None and last_eq is not None
                                   and float(last_eq) > float(first_eq)),
            "account_mode": account_mode, "open_positions": open_positions}


def era_trades_from(fx: dict, lookback_days: int = 90) -> list[dict]:
    since = date(2026, 9, 20)  # CURRENT_DATE at capture
    from datetime import timedelta
    since = since - timedelta(days=lookback_days)
    return [{"signal_type": t["signal_type"], "account_mode": t["account_mode"],
             "alert_date": t["alert_date"], "exit_reason": t["exit_reason"], "peak_r": t["peak_r"],
             "realized_r": t["realized_r"], "stop_per_adr": t["stop_per_adr"]}
            for t in fx["trades"] if t["status"] == "closed" and t["alert_date"] >= since]


async def get_audit_log_from(fx: dict, limit=500, since_hours=48, event_type=None,
                             event_type_like=None):
    cutoff = RUN_AT.timestamp() - since_hours * 3600
    rows = [r for r in fx["err_rows"] if r["created_at"].timestamp() >= cutoff
            and r["created_at"] <= RUN_AT]
    if event_type:
        rows = [r for r in rows if r["event_type"] == event_type]
    elif event_type_like:
        import re
        pat = "^" + re.escape(event_type_like).replace("%", ".*") + "$"
        rows = [r for r in rows if re.match(pat, r["event_type"], re.I)]
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return rows[:limit]


def install_stubs(fx: dict, ledger_as_of: datetime | None = None) -> dict:
    """Patch every edge. Returns the capture dict the run fills in."""
    import os
    import agents.market_intelligence.collector as collector
    import agents.market_intelligence.db as db
    import agents.market_intelligence.kill_scale_bands as ksb
    import agents.market_intelligence.system_review as sr
    import shared.telegram_format as tf

    cap: dict = {"sent": [], "inserted": [], "md": [], "audit": []}
    os.environ["ANTHROPIC_MONTHLY_BUDGET"] = fx["budget"]
    collector.et_today = lambda: REVIEW_DATE

    sr._gather_and_aggregate = AsyncMock(return_value=fx["metrics"])
    sr.get_latest_system_review = AsyncMock(return_value=fx["prior"])
    sr._synthesize = AsyncMock(return_value=fx["summary"])
    sr.insert_system_review = AsyncMock(side_effect=lambda review: cap["inserted"].append(review))
    sr.send_telegram_message = AsyncMock(
        side_effect=lambda text, **kw: cap["sent"].append((text, kw)) or True)
    sr.get_setup_performance_review = AsyncMock(return_value=fx["setup_review"])
    sr.get_setup_era_trades = AsyncMock(side_effect=lambda lookback_days=90: era_trades_from(fx, lookback_days))
    sr.get_audit_log = lambda **kw: get_audit_log_from(fx, **kw)
    ksb.assemble_band_inputs = AsyncMock(side_effect=lambda account_mode="live": band_inputs_from(fx, account_mode))
    ksb.get_active_override = AsyncMock(return_value=None)
    db.get_judge_divergence_stats = AsyncMock(return_value=fx["judge_div"])
    db.log_audit_event = AsyncMock(side_effect=lambda *a, **k: cap["audit"].append(a))
    db.get_pool = AsyncMock(return_value=_FakePool(fx))
    # post-#662 edges (absent on the old code — getattr keeps this driver version-agnostic)
    if hasattr(db, "get_job_runs_for"):
        as_of = ledger_as_of or datetime(2026, 9, 20, 17, 45, tzinfo=timezone.utc)

        async def _runs(job_ids, since_hours=240):
            return [r for r in fx["job_runs"] if r["job_id"] in set(job_ids)
                    and r["started_at"] <= as_of]
        db.get_job_runs_for = _runs
    if hasattr(sr, "_utcnow"):
        sr._utcnow = lambda: RUN_AT

    real_md_to_html = tf.md_to_html

    def _rec(text):
        cap["md"].append(text)
        return real_md_to_html(text)
    tf.md_to_html = _rec
    return cap


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="old")
    ap.add_argument("--out", default="/tmp/662")
    ap.add_argument("--ledger-as-of", default=None,
                    help="ISO UTC timestamp; job-ledger rows after it are hidden (default: capture time)")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    fx = build_fixture(load_capture())
    as_of = datetime.fromisoformat(a.ledger_as_of) if a.ledger_as_of else None
    cap = install_stubs(fx, as_of)

    import agents.market_intelligence.system_review as sr
    from shared.telegram_format import chunk_html
    review = asyncio.run(sr.run_weekly_review(window_days=7))

    assert len(cap["sent"]) == 1, cap["sent"]
    html, kw = cap["sent"][0]
    md = "\n\n<<<FOLD>>>\n\n".join(cap["md"]) if len(cap["md"]) > 1 else (cap["md"][0] if cap["md"] else "")
    (out / f"{a.tag}.md").write_text(md, encoding="utf-8")
    (out / f"{a.tag}.html").write_text(html, encoding="utf-8")
    chunks = chunk_html(html)
    stats = {
        "tag": a.tag, "parse_mode": kw.get("parse_mode"),
        "md_lines": md.count("\n") + 1, "md_chars": len(md),
        "html_chars": len(html), "chunks": len(chunks),
        "report_meta": (review.get("metrics") or {}).get("report"),
        "suggestions": review.get("suggestions"),
        "audit_writes_attempted": len(cap["audit"]),
    }
    (out / f"{a.tag}.txt").write_text(json.dumps(stats, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in stats.items() if k != "report_meta"}, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
