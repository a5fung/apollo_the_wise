"""Monday first-fire verify harness (2026-06-07) — READ-ONLY.

One command to check everything shipped this weekend on its first REAL fire, so
the Monday 7-10am verify cluster is turnkey instead of ad-hoc SQL:

  1. Scheduler jobs  — today's mi_job_runs: errors/aborts + the two new/changed
     EOD digest jobs (intraday_signals_eod_digest 16:00, 9m_pace_digest 16:20).
  2. Wave A (#231)   — grade DISTRIBUTION (game_changer/HIGH) vs trailing baseline
     (load-bearing: the gate is "didn't inflate", not "rows exist"). Full verdict:
     scripts/_wave_a_grade_inflation_check.py.
  3. Wave B (#232)   — ep_catalyst_provenance rows + has_direct_source breakdown +
     the 10:05 ep_provenance_daily KPI row (the self-verifier fired).
  4. #168 noise fix  — the 5 detector tables still got rows (detection alive) +
     the consolidated EOD digest job ran. Per-tick SILENCE is observational
     (operator confirms the ~23/day pings are gone).
  5. #97 low-vol-rest — first real fire of the 5th entry-technique detector.
  6. fire_status (#201/#189) — today's mi_ep_alerts fire_status baseline. This is
     the cohort the gap-alone-must-not-=-HIGH sign-off is gated on (do NOT flip
     the floor without it + CHANGE_PROCESS + operator sign-off).

This is READ-ONLY (SELECT only — no trade state). Safe via docker exec. It DEFERS
every verdict to the operator (hard-gate rule: no auto-"green").

  docker exec apollo-market python scripts/verify_monday_firstfire.py
  docker exec apollo-market python scripts/verify_monday_firstfire.py 2026-06-08
"""
import asyncio
import json
import sys
from datetime import date


def _hdr(title: str) -> None:
    print(f"\n{'─' * 72}\n{title}\n{'─' * 72}")


async def check_jobs(conn, target):
    _hdr("1. SCHEDULER JOBS (mi_job_runs, ET day)")
    rows = await conn.fetch(
        """
        SELECT job_id, started_at, status, rows_written, error_message
        FROM mi_job_runs
        WHERE started_at AT TIME ZONE 'America/New_York' >= $1::date
          AND started_at AT TIME ZONE 'America/New_York' <  $1::date + 1
        ORDER BY started_at
        """,
        target,
    )
    if not rows:
        print("   (no job runs recorded for this ET day yet)")
        return
    bad = [r for r in rows if (r["status"] or "").lower() in ("error", "failed", "aborted")]
    if bad:
        print(f"   ⚠️  {len(bad)} job(s) NOT clean — inspect:")
        for r in bad:
            print(f"        {r['job_id']:32} {r['status']:8} {r['error_message'] or ''}")
    else:
        print(f"   ✅ all {len(rows)} job runs clean (no error/aborted)")
    for jid, when in (("intraday_signals_eod_digest", "16:00"),
                      ("9m_pace_digest", "16:20")):
        hit = [r for r in rows if r["job_id"] == jid]
        if hit:
            r = hit[-1]
            print(f"   • {jid} ({when} ET): RAN {r['started_at']:%H:%M} "
                  f"status={r['status']} rows={r['rows_written']}")
        else:
            print(f"   • {jid} ({when} ET): not yet (fires {when}; run after that)")


async def check_wave_a(conn, target):
    _hdr("2. WAVE A (#231) — grade distribution vs trailing baseline")
    base = await conn.fetch(
        """
        SELECT alert_date,
               COUNT(*) FILTER (WHERE catalyst_quality = 'game_changer') gc,
               COUNT(*) FILTER (WHERE score_tier = 'HIGH')               high
        FROM mi_ep_alerts
        WHERE alert_date >= $1::date - 9 AND alert_date < $1::date
        GROUP BY alert_date
        """,
        target,
    )
    tgt = await conn.fetchrow(
        """
        SELECT COUNT(*) FILTER (WHERE catalyst_quality = 'game_changer') gc,
               COUNT(*) FILTER (WHERE score_tier = 'HIGH')               high,
               COUNT(*) total
        FROM mi_ep_alerts WHERE alert_date = $1
        """,
        target,
    )
    n = max(len(base), 1)
    avg_gc = sum(r["gc"] for r in base) / n
    avg_high = sum(r["high"] for r in base) / n
    max_gc = max((r["gc"] for r in base), default=0)
    max_high = max((r["high"] for r in base), default=0)
    print(f"   baseline (prior {len(base)} trading days):  "
          f"game_changer avg {avg_gc:.1f}/max {max_gc}  ·  HIGH avg {avg_high:.1f}/max {max_high}")
    print(f"   {target}:  game_changer {tgt['gc']}  ·  HIGH {tgt['high']}  "
          f"(total alerts {tgt['total']})")
    if tgt["total"] == 0:
        print("   ℹ️  no alerts yet — re-run after the morning EP scan.")
    elif tgt["gc"] > max_gc or tgt["high"] > max_high:
        print("   ⚠️  above trailing max — run scripts/_wave_a_grade_inflation_check.py "
              "for the benzinga-concentration verdict (operator call).")
    else:
        print("   ✅ within trailing baseline (full verdict: _wave_a_grade_inflation_check.py)")


async def check_wave_b(conn, target):
    _hdr("3. WAVE B (#232) — corpus provenance + self-verifier")
    prov = await conn.fetch(
        """
        SELECT detail FROM mi_audit_log
        WHERE event_type = 'ep_catalyst_provenance'
          AND created_at AT TIME ZONE 'America/New_York' >= $1::date
          AND created_at AT TIME ZONE 'America/New_York' <  $1::date + 1
        """,
        target,
    )
    graded = direct = 0
    by_class: dict = {}
    for r in prov:
        try:
            d = json.loads(r["detail"] or "{}")
        except (ValueError, TypeError):
            continue
        graded += 1
        if d.get("has_direct_source"):
            direct += 1
        for cls in (d.get("sources") or {}):
            by_class[cls] = by_class.get(cls, 0) + 1
    if not prov:
        print("   ℹ️  no ep_catalyst_provenance rows yet — re-run after the EP scan.")
    else:
        print(f"   graded tickers w/ provenance: {graded}   has_direct_source: {direct}")
        print(f"   by source-class: " +
              (", ".join(f"{k}={v}" for k, v in sorted(by_class.items())) or "—"))
        if "benzinga_pr" in by_class:
            print(f"   ✅ benzinga_pr present ({by_class['benzinga_pr']}) — Wave-A wiring fired end-to-end")
        else:
            print("   ⚠️  no benzinga_pr in any corpus today — confirm the Alpaca-news fetch fired "
                  "(could be a genuinely PR-less day; cross-check a known-PR ticker)")
    kpi = await conn.fetchrow(
        """
        SELECT summary, created_at FROM mi_audit_log
        WHERE event_type = 'ep_provenance_daily'
          AND created_at AT TIME ZONE 'America/New_York' >= $1::date
          AND created_at AT TIME ZONE 'America/New_York' <  $1::date + 1
        ORDER BY created_at DESC LIMIT 1
        """,
        target,
    )
    if kpi:
        print(f"   • self-verifier (10:05): ep_provenance_daily RAN {kpi['created_at']:%H:%M} — {kpi['summary']}")
    else:
        print("   • self-verifier (10:05): no ep_provenance_daily row yet (fires 10:05 ET in-market)")


async def check_168(conn, target):
    _hdr("4. #168 — detector tables alive + consolidated EOD digest")
    from agents.market_intelligence.flag_detector import _INTRADAY_SIGNAL_TABLES
    any_rows = False
    for table, datecol, emoji, label in _INTRADAY_SIGNAL_TABLES:
        try:
            n = await conn.fetchval(
                f"SELECT COUNT(*) FROM {table} WHERE {datecol} = $1", target
            )
        except Exception as e:
            print(f"   {emoji} {label:14} table check errored: {e}")
            continue
        any_rows = any_rows or bool(n)
        print(f"   {emoji} {label:14} {n} rows today")
    if not any_rows:
        print("   ℹ️  no detector rows yet — re-run after the morning scans (9:35+ ET).")
    print("   (Per-tick SILENCE is observational: operator confirms the ~23/day pings are gone;"
          " the EOD digest job presence is checked in section 1.)")


async def check_97(conn, target):
    _hdr("5. #97 LOW-VOL-REST — first real fire")
    try:
        n = await conn.fetchval(
            "SELECT COUNT(*) FROM mi_flag_low_vol_rests WHERE rest_date = $1", target
        )
        sample = await conn.fetch(
            "SELECT ticker FROM mi_flag_low_vol_rests WHERE rest_date = $1 LIMIT 8", target
        )
    except Exception as e:
        print(f"   ⚠️  check errored: {e}")
        return
    if n:
        print(f"   ✅ {n} low-vol-rest signal(s) today: {', '.join(r['ticker'] for r in sample)}")
    else:
        print("   ℹ️  0 today — fine if no name qualified (rare pattern); confirm the scan job ran (section 1).")


async def check_firestatus(conn, target):
    _hdr("6. fire_status (#201/#189) BASELINE — the gap-alone-≠-HIGH sign-off cohort")
    rows = await conn.fetch(
        """
        SELECT COALESCE(fire_status, 'NULL') fs, score_tier,
               COUNT(*) n
        FROM mi_ep_alerts WHERE alert_date = $1
        GROUP BY fire_status, score_tier ORDER BY fire_status, score_tier
        """,
        target,
    )
    if not rows:
        print("   ℹ️  no alerts yet — re-run after the EP scan; this is the #189/#201 baseline.")
        return
    by_fs: dict = {}
    for r in rows:
        by_fs.setdefault(r["fs"], {})[r["score_tier"] or "—"] = r["n"]
    print("   fire_status × score_tier (today):")
    for fs, tiers in by_fs.items():
        tier_str = ", ".join(f"{t}:{c}" for t, c in tiers.items())
        print(f"      {fs:18} {tier_str}")
    # The load-bearing signal: HIGH alerts whose fire was NOT seen = gap floated
    # them up without a named fire (exactly the cohort the directive targets).
    high_nonfire = await conn.fetchval(
        """
        SELECT COUNT(*) FROM mi_ep_alerts
        WHERE alert_date = $1 AND score_tier = 'HIGH'
          AND (fire_status IS NULL OR fire_status IN ('real_unknown', 'no_fire_confirmed'))
        """,
        target,
    )
    print(f"\n   ► HIGH alerts WITHOUT a seen fire today: {high_nonfire}")
    print("     (these are the gap-floated-HIGH-without-named-fire cohort the North Star")
    print("      directive targets — advisory only today; flip is HARD-gated.)")


async def main():
    target = (
        date(*(int(x) for x in sys.argv[1].split("-"))) if len(sys.argv) > 1 else None
    )
    from agents.market_intelligence.db import get_pool
    if target is None:
        from agents.market_intelligence.collector import et_today
        target = et_today()

    print(f"\n╔══ MONDAY FIRST-FIRE VERIFY — {target} ══╗")
    print("   READ-ONLY · verdicts are the operator's (no auto-green).")
    pool = await get_pool()
    async with pool.acquire() as conn:
        for check in (check_jobs, check_wave_a, check_wave_b,
                      check_168, check_97, check_firestatus):
            try:
                await check(conn, target)
            except Exception as e:
                print(f"\n   ⚠️  {check.__name__} errored (non-fatal): {e}")
    print(f"\n{'═' * 72}\nDone. Cross-checks: /detectors · /audit ep_provenance_daily · "
          "_wave_a_grade_inflation_check.py\n")


if __name__ == "__main__":
    asyncio.run(main())
