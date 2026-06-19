"""#344 late-source replay — the HARD 6/22 launch-gate evidence harness.

THE QUESTION (advisor 6/19): for EP catalyst grades that were decided on a
WEB-ONLY corpus (has_direct_source=False), did a PRIMARY-SUBJECT direct source
(SEC 8-K/6-K or a Benzinga press wire) land AFTER the grade but still inside the
ORB-actionable window — and if we had re-polled + re-graded on it, would the
grade recover a tier and FIRE THROUGH (a new HIGH alert → 9:31 ORB candidate)?

This is the BFLY 6/18 class: graded `routine` at 7:00 ET on web-only sourcing,
the BusinessWire/MidJourney PR hit Benzinga ~8:12 ET (72 min later), the per-day
catalyst cache pinned the stale routine grade all day → no alert. The fix (cache
surgery + re-poll on a has_direct_source False→True transition) is only worth
shipping if this replay shows the late source RECOVERS the grade for a non-trivial
slice. If it doesn't, the cache surgery isn't worth the hot-path risk.

WHY THIS IS LOOKAHEAD-FREE + READ-ONLY (zero hot-path risk, sprintable):
  - Cohort = `ep_catalyst_provenance` audit rows (has_direct_source=False).
  - The re-grade reconstructs the corpus the live re-poll WOULD have seen by the
    ORB cutoff: SEC filed ≤ cutoff + Benzinga created ≤ cutoff, NO WEB. Web search
    returns TODAY's results = lookahead — deliberately omitted. So a recovery
    WITHOUT web is conservative vs the production re-grade (which keeps web):
    recovery-without-web means the fix definitely helps.
  - The DELTA we measure is purely the direct source: we only re-grade tickers
    where a NEW primary-subject direct source arrived in (grade_time, cutoff].
    Comparing against the live stored routine grade would measure "web vs direct"
    (the already-settled #210 question) — we compare against the SAME no-web
    corpus minus the late source, so the only moving part is the late source.
  - Fire-through is BOUNDED, not recomputed from scratch: mi_ep_scan_log persists
    the routine ep_score (post-multiplier) + gap_pct for scored-but-<50 names.
    The catalyst raw delta (routine 0 → strong +15 / game_changer +25, _score_ep
    L688) times the alert-date regime multiplier (1.2 Bull / 1.0 else), plus the
    gap-driven conviction floor (gap IS persisted → exact), bounds the new final
    score vs the alert-date ep_threshold. We do NOT re-derive rvol/vol_pct (the
    lookahead trap). Catalyst CORRECTNESS (not P&L) is the precision metric — the
    per-case source text is surfaced for operator labeling.

Run read-only on the server (prod DB + API keys + LLM) via:
    docker exec apollo-market python scripts/_344_late_source_replay.py
    docker exec apollo-market python scripts/_344_late_source_replay.py --ticker BFLY --lookback-days 3
    docker exec apollo-market python scripts/_344_late_source_replay.py --orb-cutoff 09:45 --limit 50
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from agents.market_intelligence.collector import (
    get_alpaca_news, get_sec_recent_filings, is_primary_subject_news,
)
from agents.market_intelligence.ep_detector import (
    build_grounded_text, _classify_catalyst_claude,
    # #344 SSoT: the SAME corpus-assembly the live grade path uses (advisor #5 — no
    # validate-one-thing-ship-another divergence).
    assemble_grade_corpus, recent_filing_by_item, nearest_today_filing,
    recent_dilution_filing,
)
from scripts._grounded_reconstruct import _to_aware_utc
from scripts._judge_replay_common import fetch_profile

_ET = ZoneInfo("America/New_York")
_TIER_RANK = {"routine": 0, "strong": 1, "game_changer": 2, "mna": -1}
_CATALYST_RAW = {"routine": 0, "strong": 15, "game_changer": 25}


def _parse_args():
    ap = argparse.ArgumentParser(description="#344 late-source replay (read-only).")
    ap.add_argument("--lookback-days", type=int, default=12,
                    help="alert_date >= today - N (provenance exists since Wave B 6/7).")
    ap.add_argument("--orb-cutoff", default="09:45",
                    help="ET HH:MM — the ORB submission deadline; a direct source after "
                         "this can't rescue the trade. Default 09:45 (ORB window end).")
    ap.add_argument("--limit", type=int, default=60,
                    help="cap LLM re-grades (applied to the late-source subset only).")
    ap.add_argument("--ticker", default=None, help="single-case mode (e.g. BFLY).")
    ap.add_argument("--enrich", action="store_true",
                    help="ENRICHMENT mode (#344 fix eval): re-grade ALL graded gappers in "
                         "the window under corpus-enrichment arms (include_content / prior "
                         "item-1.01 8-K + revenue / both) vs a no-web baseline, and report "
                         "NET catalyst-correctness (distribution shift + per-rise detail for "
                         "operator labeling) — NOT BFLY-recovery (which the fix recovers by "
                         "construction).")
    return ap.parse_args()


def _conviction_floor(gap_pct: float | None, tier: str) -> int:
    """Mirror _score_ep's gap-driven conviction floors (raw, pre-multiplier)."""
    if gap_pct is None:
        return 0
    if gap_pct >= 15 and tier == "game_changer":
        return 80
    if gap_pct >= 20 and tier == "strong":
        return 80
    if gap_pct >= 15 and tier == "strong":
        return 70
    if gap_pct >= 10 and tier == "game_changer":
        return 60
    return 0


async def _gather_direct_sources(ticker, alert_date, company, first_grade_ts, cutoff_ts):
    """Return (in_window_sec, in_window_benzinga, all_events) — primary-subject
    direct sources bucketed by arrival vs first_grade_ts and cutoff_ts.

    `all_events` = list of (kind, arrival_dt|date, bucket, headline) for the report.
    Buckets: 'pre_grade' (≤ grade), 'in_window' (grade<arr≤cutoff), 'late' (>cutoff)."""
    events = []
    in_window_benzinga, in_window_sec = [], None

    # ── Benzinga press wires (Alpaca news), primary-subject only ──
    try:
        news = await get_alpaca_news(ticker, to_date=alert_date, lookback_days=10, limit=30)
    except Exception:
        news = []
    for n in news or []:
        if not is_primary_subject_news(n, ticker, company or ""):
            continue
        ca = _to_aware_utc(n.get("created_at"))
        if ca is None:
            continue
        if ca <= first_grade_ts:
            bucket = "pre_grade"
        elif ca <= cutoff_ts:
            bucket = "in_window"
        else:
            bucket = "late"
        hl = (n.get("headline") or n.get("title") or "")[:120]
        events.append(("benzinga", ca, bucket, hl))
        if bucket == "in_window":
            in_window_benzinga.append(n)

    # ── SEC 8-K / 6-K (date-granular; the catalyst filing) ──
    lb = max((date.today() - alert_date).days + 12, 12)
    try:
        filings = await get_sec_recent_filings(
            ticker, forms=("8-K", "6-K"), lookback_days=lb, max_filings=12, want_text=True)
    except Exception:
        filings = []
    sec_cands = []
    for f in filings or []:
        try:
            fd = date.fromisoformat(f["filed"])
        except (ValueError, TypeError, KeyError):
            continue
        if not f.get("text"):
            continue
        # Date-granular: a filing dated == alert_date can't be timed vs the grade.
        # Conservative bucket: filed < alert_date → pre_grade; filed == alert_date
        # → in_window (filed sometime on the day, treated as available by cutoff,
        # flagged as date-granular); filed > alert_date → late (post-day).
        if fd < alert_date:
            bucket = "pre_grade"
        elif fd == alert_date:
            bucket = "in_window"
        else:
            bucket = "late"
        events.append(("sec", fd, bucket, f"{f.get('form')} items={f.get('items')}"))
        if bucket == "in_window":
            sec_cands.append((fd, f))
    if sec_cands:
        sec_cands.sort(key=lambda x: x[0], reverse=True)
        in_window_sec = sec_cands[0][1]

    return in_window_sec, in_window_benzinga[:3], events


async def _fetch_benzinga(ticker, alert_date, include_content):
    """Primary-subject Benzinga items via Alpaca News, with optional full bodies.
    get_alpaca_news() does NOT pass include_content=True (arm-(a) gap), so call the
    NewsClient directly here to compare headline-only vs full-body corpora."""
    import os
    from alpaca.data.historical.news import NewsClient
    from alpaca.data.requests import NewsRequest
    api_key = os.environ.get("ALPACA_PAPER_API_KEY") or os.environ.get("ALPACA_API_KEY", "")
    secret = os.environ.get("ALPACA_PAPER_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY", "")
    start = datetime(alert_date.year, alert_date.month, alert_date.day, tzinfo=timezone.utc) \
        - timedelta(days=10)
    end = datetime(alert_date.year, alert_date.month, alert_date.day, 23, 59, 59, tzinfo=timezone.utc)
    out = []
    try:
        client = NewsClient(api_key=api_key, secret_key=secret)
        req = NewsRequest(symbols=ticker, start=start, end=end, limit=30,
                          include_content=include_content)
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(None, lambda: client.get_news(req))
        items = resp.dict().get("news", []) if hasattr(resp, "dict") else resp.model_dump().get("news", [])
        for n in items:
            ca = n.get("created_at", "")
            out.append({
                "title": n.get("headline", "") or "", "headline": n.get("headline", "") or "",
                "summary": n.get("summary", "") or "", "content": n.get("content", "") or "",
                "symbols": list(n.get("symbols", []) or []),
                "created_at": ca.isoformat() if hasattr(ca, "isoformat") else str(ca),
            })
    except Exception:
        pass
    return out


# Corpus-assembly helpers (assemble_grade_corpus / recent_filing_by_item /
# nearest_today_filing) are imported from ep_detector — the SINGLE source of truth so the
# replay validates the EXACT code the live grade path ships (advisor #5).
_TODAY_WINDOW_DAYS = 10  # mirror ep_detector._GRADE_TODAY_WINDOW_DAYS for the prior cutoff


async def run_enrich_mode(c, args, since, cutoff_t):
    """#344 combined-fix eval — re-poll (ORB-cutoff corpus) + enrichment (prior-agreement
    context). Baseline = today's sources at the ORB cutoff (what a cache re-poll alone
    sees); fix = that PLUS include_content + dated prior-agreement/revenue context. The
    delta isolates the enrichment; both sit at the ORB cutoff so the cache re-poll's
    contribution (today's late PR is present) is held constant (advisor #1/#2)."""
    rows = await c.fetch(
        """
        SELECT DISTINCT ON (d.ticker, d.alert_date)
               d.ticker, d.alert_date::date AS alert_date, l.created_at AS grade_ts,
               d.catalyst_quality AS live_q
        FROM mi_audit_log l
        CROSS JOIN LATERAL (
            SELECT (l.detail::jsonb->>'ticker') AS ticker,
                   (l.detail::jsonb->>'alert_date') AS alert_date,
                   (l.detail::jsonb->>'catalyst_quality') AS catalyst_quality
        ) d
        WHERE l.event_type = 'ep_catalyst_provenance'
          AND (l.detail::jsonb->>'alert_date')::date >= $1
          AND ($2::text IS NULL OR d.ticker = $2)
        ORDER BY d.ticker, d.alert_date, l.created_at ASC
        """, since, args.ticker)

    print(f"\n{'='*78}")
    print(f"#344 COMBINED-FIX EVAL (re-poll@ORB + prior-agreement enrichment) — "
          f"{len(rows)} graded gappers")
    print(f"  baseline = today's sources @ {args.orb_cutoff} ET (re-poll alone) · "
          f"fix = +include_content +dated prior 1.01/2.02 context")
    print(f"{'='*78}")

    dist = {a: {"game_changer": 0, "strong": 0, "routine": 0, "mna": 0}
            for a in ("baseline", "fix")}
    rises = []
    for r in rows[: args.limit]:
        ticker, alert_date = r["ticker"], r["alert_date"]
        cutoff_ts = datetime.combine(alert_date, cutoff_t, tzinfo=_ET)
        mc, sector, company = await fetch_profile(ticker)
        profile = {"companyName": company or "", "sector": sector or "",
                   "marketCap": mc, "description": ""}
        filings = await get_sec_recent_filings(
            ticker, forms=("8-K", "6-K"), lookback_days=400, max_filings=30, want_text=True)
        today_sec = nearest_today_filing(filings, alert_date)
        # PRIOR context must be strictly older than the today-window (don't relabel
        # today's own filing as "prior").
        prior_before = alert_date - timedelta(days=_TODAY_WINDOW_DAYS + 1)
        prior_agreement = recent_filing_by_item(filings, "1.01", prior_before)
        recent_earnings = recent_filing_by_item(filings, "2.02", alert_date)
        # #238 dilution overhang — SEPARATE fetch so a 424B5 never pollutes today_sec/prior
        # (nearest_today_filing would otherwise grab a same-day prospectus as "today's news"
        # on exactly the inverse-BTQ canary). NOTE (advisor 6/19): get_sec_recent_filings
        # anchors its cutoff on et_today(), NOT alert_date — a tight 21d lookback would
        # exclude every historical alert's offering (cutoff = today−21d) → dilution=none
        # cohort-wide, a silent no-op. Use the 400d reach; recent_dilution_filing's own
        # 21d-of-alert window does the recency constraint. (The LIVE path uses a tight 21d
        # fetch because there et_today()==grade day.) Fed to the FIX arm only.
        dil_filings = await get_sec_recent_filings(
            ticker, forms=("424B5", "8-K"), lookback_days=400, max_filings=30, want_text=True)
        dilution = recent_dilution_filing(dil_filings, alert_date)
        # Today's Benzinga (include_content) up to the ORB cutoff = what the re-poll sees.
        today_benz = [n for n in await _fetch_benzinga(ticker, alert_date, True)
                      if is_primary_subject_news(n, ticker, company or "")
                      and (_to_aware_utc(n.get("created_at")) or cutoff_ts) <= cutoff_ts]

        grades, analyses, corpora = {}, {}, {}
        for arm, enrich in (("baseline", False), ("fix", True)):
            corpus = assemble_grade_corpus(alert_date, today_sec, today_benz,
                                           prior_agreement, recent_earnings, enrich=enrich,
                                           dilution_filing=dilution if enrich else None)
            corpora[arm] = corpus
            q, an = await _classify_catalyst_claude(ticker, [], profile, grounded_text=corpus)
            grades[arm], analyses[arm] = q, an
            dist[arm][q] = dist[arm].get(q, 0) + 1

        if args.ticker:  # single-case diagnostic
            print(f"\n--- DIAG {ticker} {alert_date} ---")
            print(f"  today_sec={'yes' if today_sec else 'no'}  today_benz≤cutoff={len(today_benz)}"
                  f"  prior_1.01={prior_agreement.get('filed') if prior_agreement else 'none'}"
                  f"  earnings_2.02={recent_earnings.get('filed') if recent_earnings else 'none'}"
                  f"  dilution={dilution.get('form') + '@' + dilution.get('filed') if dilution else 'none'}")
            print(f"  FIX corpus ({len(corpora['fix'])}c):\n    "
                  + corpora['fix'][:1400].replace(chr(10), chr(10) + '    '))
            for arm in ("baseline", "fix"):
                print(f"  [{arm}] → {grades[arm]}: {analyses[arm][:320]}")

        if _TIER_RANK.get(grades["fix"], 0) != _TIER_RANK.get(grades["baseline"], 0):
            rises.append({
                "ticker": ticker, "alert_date": str(alert_date), "live_q": r["live_q"],
                "base": grades["baseline"], "fix": grades["fix"],
                "dir": "↑ RISE" if _TIER_RANK.get(grades["fix"], 0) > _TIER_RANK.get(grades["baseline"], 0) else "↓ fall",
                "prior_1_01": prior_agreement.get("filed") if prior_agreement else None,
                "dilution": (dilution.get("form") + "@" + dilution.get("filed")) if dilution else None,
                "fix_reason": analyses["fix"][:240],
            })

    print(f"\nGRADE DISTRIBUTION  (baseline @ORB → fix):")
    for tier in ("game_changer", "strong", "routine", "mna"):
        print(f"  {tier:>12}: {dist['baseline'][tier]:>3}  →  {dist['fix'][tier]:>3}")
    print(f"\nGRADE CHANGES under the fix: {len(rises)} of {len(rows[:args.limit])}")
    print(f"{'-'*78}\n⚖️ operator labels each: TRUE catalyst, or INFLATION (should stay routine)?"
          f"\n{'-'*78}")
    for x in rises:
        print(f"  {x['dir']}  {x['ticker']:6} {x['alert_date']}  base={x['base']} → fix={x['fix']}  "
              f"(live was {x['live_q']})  prior_1.01={x['prior_1_01'] or 'none'}  "
              f"dilution={x['dilution'] or 'none'}")
        print(f"      fix reasoning: {x['fix_reason']}")
    print(f"\n{'='*78}")
    print("GATE READ: net-positive iff RISES are true catalysts AND nothing that should "
          "stay routine got lifted (the BTQ-class ATM-dilution canary MUST stay routine). "
          "Baseline=today's sources @ORB (re-poll alone); fix adds dated prior context. "
          "Live flip = port assemble_grade_corpus to ep_detector + CHANGE_PROCESS + sign-off.")
    print(f"{'='*78}\n")


async def main():
    args = _parse_args()
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()

    cutoff_t = time.fromisoformat(args.orb_cutoff)
    today = datetime.now(_ET).date()
    since = today - timedelta(days=args.lookback_days)

    async with pool.acquire() as c:
        if args.enrich:
            await run_enrich_mode(c, args, since, cutoff_t)
            return
        # ── Cohort: web-only grades, deduped to the EARLIEST grade per ticker/day
        # (container-restart re-fires log a 2nd provenance row later in the day —
        # 6/15's 118 is almost all re-fires; min(created_at) is the real grade). ──
        rows = await c.fetch(
            """
            SELECT DISTINCT ON (d.ticker, d.alert_date)
                   d.ticker, d.alert_date::date AS alert_date,
                   l.created_at AS grade_ts, d.catalyst_quality, d.sources
            FROM mi_audit_log l
            CROSS JOIN LATERAL (
                SELECT (l.detail::jsonb->>'ticker')          AS ticker,
                       (l.detail::jsonb->>'alert_date')      AS alert_date,
                       (l.detail::jsonb->>'catalyst_quality') AS catalyst_quality,
                       (l.detail::jsonb->'sources')          AS sources,
                       (l.detail::jsonb->>'has_direct_source') AS hds
            ) d
            WHERE l.event_type = 'ep_catalyst_provenance'
              AND d.hds = 'false'
              AND (l.detail::jsonb->>'alert_date')::date >= $1
              AND ($2::text IS NULL OR d.ticker = $2)
            ORDER BY d.ticker, d.alert_date, l.created_at ASC
            """,
            since, args.ticker,
        )

        total = len(rows)
        by_grade: dict[str, int] = {}
        for r in rows:
            by_grade[r["catalyst_quality"]] = by_grade.get(r["catalyst_quality"], 0) + 1

        print(f"\n{'='*78}")
        print(f"#344 LATE-SOURCE REPLAY — web-only catalyst grades, {since}..{today}")
        print(f"  ORB-actionable cutoff = {args.orb_cutoff} ET   (source after this = unrescuable)")
        print(f"{'='*78}")
        print(f"\nFUNNEL stage 0 — web-only grades (deduped ticker/day): {total}")
        print(f"  grade mix: " + ", ".join(f"{k}={v}" for k, v in sorted(by_grade.items())))

        # Stage the cohort: find which had a late-in-window primary-subject source.
        n_any_direct = n_in_window = n_regraded_up = n_fires_new = 0
        late_subset = []   # (row, company, mc, sector, sec, benzinga, events)
        had_source = []    # (ticker, alert_date, grade_ts, events) for any-source members
        for r in rows:
            ticker, alert_date = r["ticker"], r["alert_date"]
            grade_ts = r["grade_ts"]
            if grade_ts.tzinfo is None:
                grade_ts = grade_ts.replace(tzinfo=timezone.utc)
            cutoff_ts = datetime.combine(alert_date, cutoff_t, tzinfo=_ET)

            mc, sector, company = await fetch_profile(ticker)
            sec, benzinga, events = await _gather_direct_sources(
                ticker, alert_date, company, grade_ts, cutoff_ts)
            if events:
                n_any_direct += 1
                had_source.append((ticker, alert_date, grade_ts, events))
            if sec is not None or benzinga:
                n_in_window += 1
                late_subset.append((r, company, mc, sector, sec, benzinga, events))

        print(f"FUNNEL stage 1 — had ANY primary-subject direct source (any time): {n_any_direct}")
        print(f"FUNNEL stage 2 — direct source IN (grade, cutoff] window:          {n_in_window}")

        # ── Re-grade ONLY the late-in-window subset (LLM cost pruned) ──
        late_subset = late_subset[: args.limit]
        recovered = []
        regrades = []  # EVERY late-subset re-grade (recovered or not) for inspection
        for (r, company, mc, sector, sec, benzinga, events) in late_subset:
            ticker, alert_date = r["ticker"], r["alert_date"]
            profile = {"companyName": company or "", "sector": sector or "",
                       "marketCap": mc, "description": ""}
            grounded = build_grounded_text(sec, benzinga, None)  # None = no web (lookahead)
            in_window_evts = [(k, str(a), b, h) for (k, a, b, h) in events if b == "in_window"]
            if not grounded:
                regrades.append({"ticker": ticker, "alert_date": str(alert_date),
                                 "old": r["catalyst_quality"], "new": "(empty grounded)",
                                 "events": in_window_evts, "grounded_lead": "", "analysis": ""})
                continue
            new_q, new_analysis = await _classify_catalyst_claude(
                ticker, [], profile, grounded_text=grounded)
            old_q = r["catalyst_quality"]
            regrades.append({"ticker": ticker, "alert_date": str(alert_date),
                             "old": old_q, "new": new_q, "events": in_window_evts,
                             "grounded_lead": grounded[:500], "analysis": new_analysis[:400]})
            if _TIER_RANK.get(new_q, -1) <= _TIER_RANK.get(old_q, 0):
                continue  # no recovery (or M&A) — corpus didn't lift the grade
            n_regraded_up += 1

            # ── Fire-through (bounded) — base from mi_ep_scan_log + regime ──
            srow = await c.fetchrow(
                """
                SELECT ep_score, gap_pct FROM mi_ep_scan_log
                WHERE ticker = $1 AND scan_date = $2::date AND ep_score IS NOT NULL
                ORDER BY scan_time_et DESC LIMIT 1
                """, ticker, alert_date)
            rreg = await c.fetchrow(
                "SELECT regime, ep_threshold FROM mi_market_regime WHERE regime_date = $1::date",
                alert_date)
            ep_threshold = (rreg["ep_threshold"] if rreg and rreg["ep_threshold"] else 70)
            mult = 1.2 if (rreg and rreg["regime"] == "Bull") else 1.0

            already_high = await c.fetchrow(
                "SELECT 1 FROM mi_ep_alerts WHERE ticker=$1 AND alert_date=$2::date "
                "AND score_tier='HIGH'", ticker, alert_date)

            if srow and srow["ep_score"] is not None:
                base = float(srow["ep_score"])
                gap = srow["gap_pct"]
                delta_raw = _CATALYST_RAW[new_q] - _CATALYST_RAW.get(old_q, 0)
                floor = _conviction_floor(gap, new_q)
                est = max(base + delta_raw * mult, floor * mult)
                fires_high = est >= ep_threshold
                fires_mod = est >= 50
                ft = (f"base={base:.0f} gap={gap:.1f}% x{mult} thr={ep_threshold} "
                      f"→ est≈{est:.0f}  "
                      + ("HIGH" if fires_high else "MOD" if fires_mod else "no-fire"))
                new_fire = fires_high and not already_high
            else:
                ft = "indeterminate (no scored mi_ep_scan_log row — routine gap<12 skip)"
                new_fire = False
            if new_fire:
                n_fires_new += 1

            recovered.append({
                "ticker": ticker, "alert_date": str(alert_date),
                "old": old_q, "new": new_q, "fire": ft, "new_fire": new_fire,
                "analysis": new_analysis, "company": company,
                "events": [(k, str(a), b, h) for (k, a, b, h) in events
                           if b in ("in_window",)],
                "grounded_lead": grounded[:400],
            })

        print(f"FUNNEL stage 3 — re-grades to a HIGHER tier on the late source:    {n_regraded_up}")
        print(f"FUNNEL stage 4 — fires a NEW HIGH (not already HIGH-alerted):      {n_fires_new}")

        # ── EVERY late-subset re-grade (incl. stayed-routine) — diagnostic ──
        print(f"\n{'-'*78}\nALL late-source re-grades ({len(regrades)}) — incl. stayed-flat (why?)\n{'-'*78}")
        for g in regrades:
            arrow = "↑" if _TIER_RANK.get(g["new"], -1) > _TIER_RANK.get(g["old"], 0) else "="
            print(f"\n{arrow} {g['ticker']} {g['alert_date']}  {g['old']} → {g['new']}")
            for (k, a, b, h) in g["events"]:
                print(f"   in-window [{k} @ {a}]: {h}")
            if g["analysis"]:
                print(f"   grade reasoning: {g['analysis']}")
            if g["grounded_lead"]:
                print(f"   grounded lead: {g['grounded_lead'][:300].strip()}")

        # ── Per-case detail for operator catalyst-CORRECTNESS labeling ──
        print(f"\n{'='*78}\nRECOVERED CASES (operator labels each: correct catalyst? Y/N)\n{'='*78}")
        if not recovered:
            print("  (none — no late direct source recovered a grade in this window)")
        for x in recovered:
            flag = "🔥 NEW FIRE" if x["new_fire"] else "↑ recovered"
            print(f"\n{flag}  {x['ticker']} {x['alert_date']}  "
                  f"{x['old']} → {x['new']}   ({x['company']})")
            print(f"   fire-through: {x['fire']}")
            for (k, a, b, h) in x["events"]:
                print(f"   in-window source [{k} @ {a}]: {h}")
            print(f"   new grade reasoning: {x['analysis'][:300]}")
            print(f"   grounded corpus lead: {x['grounded_lead'][:240].strip()}")

        # ── CHECK A (advisor 6/19): the cache-fix NATURAL EXPERIMENT ──
        # A container restart clears _catalyst_cache → the next scan re-grades with
        # the FULL web+direct corpus = exactly what the #344 re-poll would do. So a
        # LATER same-day provenance row IS a real production re-grade. For each
        # ticker/day with >=2 rows: did any later row grade HIGHER than the earliest,
        # with has_direct_source flipping false->true? This tests PRODUCTION's actual
        # web-inclusive behavior — stronger than the no-web reconstruction above.
        # (catalyst_quality here is the raw Claude grade, logged pre-earnings-boost.)
        multi = await c.fetch(
            """
            WITH prov AS (
                SELECT (detail::jsonb->>'ticker')           AS ticker,
                       (detail::jsonb->>'alert_date')::date AS alert_date,
                       created_at,
                       (detail::jsonb->>'catalyst_quality') AS q,
                       (detail::jsonb->>'has_direct_source') AS hds
                FROM mi_audit_log
                WHERE event_type = 'ep_catalyst_provenance'
                  AND (detail::jsonb->>'alert_date')::date >= $1
            )
            SELECT ticker, alert_date, count(*) AS n,
                   array_agg(q   ORDER BY created_at) AS q_seq,
                   array_agg(hds ORDER BY created_at) AS hds_seq
            FROM prov GROUP BY ticker, alert_date HAVING count(*) >= 2
            ORDER BY alert_date, ticker
            """, since)
        # ELIGIBLE denominator: only a day whose FIRST grade was has_direct_source=false
        # could possibly flip false->true on a later re-grade. A day that started 'true'
        # was never a candidate — reporting flips over all multi-row days inflates the
        # denominator (advisor 6/19). Check A is restart-TIMED corroboration only, not
        # the spine: the load-bearing evidence is the complete enumeration (stage-2 = a
        # full census via production's own source funcs) + the hand-read of each case.
        eligible = [m for m in multi if m["hds_seq"][0] == "false"]
        n_flip = n_flip_up = 0
        flip_up_detail = []
        for m in eligible:
            qs, hs = m["q_seq"], m["hds_seq"]
            first_q = qs[0]
            best_later = max(qs[1:], key=lambda q: _TIER_RANK.get(q, 0))
            flipped = any(h == "true" for h in hs[1:])
            increased = _TIER_RANK.get(best_later, 0) > _TIER_RANK.get(first_q, 0)
            if flipped:
                n_flip += 1
            if flipped and increased:
                n_flip_up += 1
                flip_up_detail.append((m["ticker"], str(m["alert_date"]), qs, hs))
        print(f"\n{'-'*78}\nCHECK A — cache-fix natural experiment (restart re-grades; "
              f"corroboration only)\n{'-'*78}")
        print(f"  ticker/days with >=2 provenance rows: {len(multi)}")
        print(f"  ...of which ELIGIBLE (first grade had has_direct_source=false): {len(eligible)}")
        print(f"  of eligible, has_direct_source flipped false->true on a later row: {n_flip}")
        print(f"  ...AND that later row graded a HIGHER tier (fix would have value): {n_flip_up}")
        for (tk, ad, qs, hs) in flip_up_detail:
            print(f"     ↑ {tk} {ad}: grade_seq={qs}  hds_seq={hs}")
        if n_flip_up == 0:
            print(f"  → across {len(eligible)} eligible production re-grades, none flipped "
                  "false->true with a tier increase: corroborates that the staleness "
                  "surface, while real, recovers no alert in this window.")

        # ── CHECK B (advisor 6/19): any SAME-DAY before-grade direct source? ──
        # stage1-minus-stage2 = members with a direct source NOT in-window. If any is
        # same-day AND before the grade, production graded web-only DESPITE an available
        # direct source = a live #210 SOURCING gap (not cache-timing). Confirm none.
        print(f"\n{'-'*78}\nCHECK B — same-day, pre-grade primary-subject source (would be "
              f"a live #210 gap)\n{'-'*78}")
        b_hits = 0
        for (ticker, alert_date, grade_ts, events) in had_source:
            for (k, a, bucket, h) in events:
                if bucket != "pre_grade":
                    continue
                # benzinga arrival is a datetime; SEC is a date (granular)
                same_day = (a.date() == alert_date) if isinstance(a, datetime) else (a == alert_date)
                if same_day and k == "benzinga":  # only benzinga is time-precise pre-grade
                    b_hits += 1
                    print(f"  ⚠️ {ticker} {alert_date}: [{k} @ {a}] graded web-only despite "
                          f"this same-day pre-grade source: {h}")
        if b_hits == 0:
            print("  → none. Every not-in-window direct source is a PRIOR-day filing "
                  "(stale), not a same-day source the grade missed. Flank is clean.")

        print(f"\n{'='*78}")
        print("GATE READ — load-bearing evidence = the ENUMERATION (stage-2): a COMPLETE "
              "census of the addressable surface via production's own source funcs "
              "(web-independent), plus the hand-read of each in-window case. The no-web "
              "re-grade can only UNDERCOUNT recoveries, and Check A only samples "
              "restart-TIMED re-grades — both are CORROBORATION, not the spine. The "
              "BFLY/BTQ catalyst-correctness labels are the operator's call (HARD gate).")
        print(f"{'='*78}\n")


if __name__ == "__main__":
    asyncio.run(main())
