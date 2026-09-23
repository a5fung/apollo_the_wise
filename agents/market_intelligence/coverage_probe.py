"""Coverage probe (S2, EP↔theme coverage loop — design 2026-07-13 §3).

⚠ JOB RETIRED behind the `theme_birth_gate` toggle (theme consolidation Phase 1,
operator-ruled 2026-07-27, decision 2 — 0 confirmed cohorts / 0 candidates
lifetime): in mode 'on', scheduler._coverage_probe_job skips run_coverage_probe
(audited `coverage_probe_retired`). This MODULE stays: its pure helpers —
market_adjust_moves (P3 market-adjusted co-movement), cohort_overlap — are the
birth gate's kept evidence primitives (theme_birth_gate.py imports them). Modes
'off' AND 'observe' ⇒ the job runs exactly as documented below (byte-identical).

ONE EOD SHADOW job: for each of the day's THEMELESS EP alerts (HIGH + MODERATE — fork
F-A: ALL themeless alerts, never judge-gated), build a candidate peer cohort from three
DETERMINISTIC, zero-LLM evidence sources and log it to `mi_coverage_probe`:

  P1 — named entities (structural): invert theme_axis_shadow.compute_name_attribution —
       match the CACHED company names (`mi_ticker_overrides.company_name`, same
       `_normalize_company_name` rule) of a bounded peer universe (EP-alerted / scan-log
       tickers in the trailing ~10 sessions + the subject's industry peers) against the
       alert's `grounded_text`. The catalyst naming a peer company is the strongest
       theme-as-driver evidence (the #369 finding).
  P2 — co-gap (tape): the day's OTHER EP alerts, tagged same-sector or not.
  P3 — co-movement (tape): compute_co_movement of the subject vs the P1∪P2 candidates
       on alert day, MARKET-ADJUSTED (fork F-D: SPY's same-day open→close move is
       subtracted from every leg before the 1% floor — kills the everything-rallies
       confound).

Confirmation bar (§3.3) — a cohort is `confirmed` ONLY when ALL of:
  1. >=2 signal FAMILIES agree — at least one P1 structural hit AND P3 co-movement True
     (P2 co-gap alone never confirms — calendar coincidence).
  2. Persistence — an overlapping cohort (>= COHORT_OVERLAP_FLOOR ticker overlap) also
     hit families-agree on >=1 PRIOR distinct day within the trailing 5 sessions
     (>=2 distinct days total, mirroring the promote lane's own window).
  3. Not excluded — active `mi_validation_cooldowns` tickers are dropped from the
     cohort; `mi_theme_exclusions` pairs are honored at the S3 candidate write.
Below-bar rows are STILL logged (evidence accrual), marked unconfirmed.

Anti-circularity (§3.4, THE three walls):
  • Signal wall — the judge appears NOWHERE in detect/confirm. The alert row's
    `fire_axes` is copied onto the probe row as a READ-ONLY CALIBRATION column only
    (independent-evidence-vs-judge agreement is a health gauge, never an input).
    No LLM anywhere in this module.
  • Source wall — confirmed cohorts write `mi_theme_candidates_shadow` with
    source='coverage_probe', which is (a) invisible to the judge payload
    (get_narrative_theme_candidates filters sources) and (b) CARVED OUT of the nightly
    auto-promote (get_shadow_theme_candidates excludes it by default — fork F-C
    surface-only). They surface in /themes and are promotable ONLY via the operator's
    /promotetheme one-tap.
  • Time wall — the probe runs EOD; the revealing alert's grade is long settled and is
    NEVER touched. Membership is never applied retroactively.

SHADOW INVARIANT: this module writes ONLY `mi_coverage_probe`,
`mi_theme_candidates_shadow` (source='coverage_probe') and `mi_audit_log` (plus the
additive mi_ticker_overrides company-name CACHE via the shared resolver). It never
touches mi_themes / mi_ep_alerts / any grade, tier, strategy or trade state, and it
NEVER raises into the EOD chain — every failure is swallowed to an audit event.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from agents.market_intelligence.db import (
    get_active_cooldown_tickers,
    get_company_names_batch,
    get_coverage_probe_peer_universe,
    get_daily_moves,
    get_industries_for_tickers,
    get_industry_peers,
    get_pool,
    get_recent_probe_cohorts,
    get_sectors_batch,
    get_theme_excluded_tickers,
    get_theme_heat_asof,
    get_today_ep_alerts,
    log_audit_event,
    upsert_coverage_probe_candidate,
    upsert_coverage_probe_row,
)
from agents.market_intelligence.theme_axis_shadow import (
    _ensure_company_names,
    compute_co_movement,
    compute_name_attribution,
)

logger = logging.getLogger(__name__)

# ── Tunables (starting rules, telemetry-side — NOT detection criteria; the probe drives
# nothing live, so these are health-gauge knobs, documented not tuned) ──────────────────
PEER_UNIVERSE_SESSIONS = 10   # P1 universe: EP/scan-log tickers in trailing ~10 sessions
PERSISTENCE_SESSIONS = 5      # §3.3 bar 2: cohort re-confirms within 5 sessions
COHORT_OVERLAP_FLOOR = 0.5    # "same cohort" = >=50% ticker overlap (see _cohort_overlap)
INDUSTRY_PEER_LIMIT = 40      # bound on the subject's industry-peer leg of the universe
MIN_COHORT_MEMBERS = 2        # subject + >=1 evidenced peer before an S3 candidate write
MARKET_TICKER = "SPY"         # fork F-D: the market leg subtracted from every move

_PROBE_TIERS = ("HIGH", "MODERATE")


# ── Pure helpers (unit-tested; no I/O) ──────────────────────────────────────────────────

def market_adjust_moves(moves: dict[str, float], spy_move: "float | None") -> dict[str, float]:
    """Fork F-D: subtract SPY's same-day open→close move from every ticker's move. When the
    SPY row is missing (spy_move None) the RAW moves pass through unchanged — a degraded but
    honest read; the probe row records p3_spy_move NULL so the health read can tell."""
    if spy_move is None:
        return dict(moves)
    return {t: v - spy_move for t, v in moves.items()}


def cohort_overlap(a: "set[str]", b: "set[str]") -> float:
    """Ticker overlap between two cohorts: |A∩B| / min(|A|,|B|). Intersection-over-smaller
    (not Jaccard) so a stable core cohort still matches when one day's probe picked up an
    extra straggler — the documented starting rule for §3.3's ">=50% overlap"."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def matched_name_tickers(matched: "list[str]") -> "set[str]":
    """Extract peer tickers from compute_name_attribution's tagged matches
    ('name:TICK:normalized phrase' → 'TICK')."""
    out = set()
    for m in matched or []:
        parts = m.split(":", 2)
        if len(parts) >= 2 and parts[0] == "name" and parts[1]:
            out.add(parts[1])
    return out


def build_stub_name(industry_label: "str | None", anchor_date: Any) -> str:
    """Deterministic S3 stub name (design §3.5): dominant industry + the cohort's ANCHOR
    date (its earliest families-agree day in the persistence window — stable across the
    following confirm days, so one cohort doesn't mint a new candidate name per day). The
    theme engine's own canonicalization/validation names it properly if promoted."""
    label = (industry_label or "Uncovered").strip() or "Uncovered"
    anchor = anchor_date.isoformat() if hasattr(anchor_date, "isoformat") else str(anchor_date)
    return f"Probe: {label} {anchor}"[:80]


def _families_agree(p1_score: int, co_moving: "bool | None") -> bool:
    """§3.3 bar 1: >=1 P1 structural hit AND P3 co-movement measured True. A None co_moving
    (not computable) is NOT agreement — unknown never confirms."""
    return p1_score >= 1 and co_moving is True


# ── Per-alert probe ─────────────────────────────────────────────────────────────────────

async def _probe_one_alert(
    conn: Any,
    alert: dict,
    day_alert_tickers: "set[str]",
    peer_universe: "set[str]",
    cooldown_tickers: "set[str]",
    prior_cohorts: "list[dict]",
) -> "dict | None":
    """Run P1/P2/P3 + the §3.3 bar for ONE themeless alert. Returns the probe row dict
    (already persisted), or None when the subject is theme-tracked (not a blind spot).
    Raises nothing past the caller's per-alert guard."""
    subject = (alert.get("ticker") or "").upper()
    alert_date = alert.get("alert_date")

    # Themeless test — the 7d-bounded as-of variant (design C2): matches the live credit
    # path's membership recency, so "blind spot" here means what the grade path means.
    heat = await get_theme_heat_asof(conn, subject, alert_date, recency_days=7)
    if heat is not None:
        return None  # tracked → not a blind spot; the theme-axis shadow already covers it

    grounded_text = alert.get("grounded_text")

    # ── P1 — named entities (structural) ────────────────────────────────────────────
    cogap = {t for t in day_alert_tickers if t != subject}
    industry_peers = set(await get_industry_peers(conn, subject, limit=INDUSTRY_PEER_LIMIT))
    universe = (peer_universe | industry_peers | cogap) - {subject}
    # Names: warm-fetch (cache-first, yfinance for misses, persisted) ONLY the small
    # co-gap set; the wide scan-log universe + industry peers read the cache only —
    # bounded cost, and the cache self-fills across days.
    names = await get_company_names_batch(conn, sorted(universe))
    warm = await _ensure_company_names(conn, sorted(cogap))
    names.update(warm)
    p1_score, _p1_attr, p1_matched = compute_name_attribution(
        grounded_text, subject_ticker=subject,
        cohort_tickers=sorted(universe), names_by_ticker=names,
    )
    p1_tickers = matched_name_tickers(p1_matched)

    # ── P2 — co-gap (tape) ──────────────────────────────────────────────────────────
    sectors = await get_sectors_batch(
        [t.upper() for t in [subject] + sorted(cogap)], conn=conn)
    subject_sector = sectors.get(subject)
    same_sector = {
        t for t in cogap
        if subject_sector and sectors.get(t) == subject_sector
    }

    # ── P3 — co-movement (tape), market-adjusted (F-D) ──────────────────────────────
    candidates = sorted(p1_tickers | cogap)
    raw_moves = await get_daily_moves(
        conn, alert_date, [subject] + candidates + [MARKET_TICKER])
    spy_move = raw_moves.get(MARKET_TICKER)
    adj_moves = market_adjust_moves(raw_moves, spy_move)
    ticker_move = adj_moves.get(subject)
    cohort_moves = [adj_moves[t] for t in candidates if t in adj_moves]
    cohort_move, co_moving = compute_co_movement(ticker_move, cohort_moves)

    # ── Evidence cohort + §3.3 bar 3 (not excluded) ─────────────────────────────────
    # Cohort = subject + P1 structural matches + P2 same-sector co-gaps (cross-sector
    # co-gaps stay probed-but-uncohorted — calendar coincidence without the sector tie).
    cohort = ({subject} | p1_tickers | same_sector)
    excluded = sorted(cohort & cooldown_tickers)
    cohort -= cooldown_tickers

    families_agree = _families_agree(p1_score, co_moving)

    # ── §3.3 bar 2 — persistence (>=2 distinct days within 5 sessions) ──────────────
    persistence_met = False
    anchor_date = alert_date
    if families_agree:
        for prior in prior_cohorts:
            prior_cohort = set(prior.get("cohort_tickers") or []) | {prior.get("ticker")}
            prior_cohort.discard(None)
            if cohort_overlap(cohort, prior_cohort) >= COHORT_OVERLAP_FLOOR:
                persistence_met = True
                pd = prior.get("alert_date")
                if pd is not None and pd < anchor_date:
                    anchor_date = pd

    confirmed = (
        families_agree and persistence_met and len(cohort) >= MIN_COHORT_MEMBERS
    )

    row = {
        "ticker": subject,
        "alert_date": alert_date,
        "tier": alert.get("score_tier"),
        "candidate_tickers": candidates,
        "cohort_tickers": sorted(cohort),
        "p1_name_score": p1_score,
        "p1_matched_names": p1_matched,
        "p2_cogap_tickers": sorted(cogap),
        "p2_same_sector_count": len(same_sector),
        "p3_ticker_move": ticker_move,
        "p3_cohort_move": cohort_move,
        "p3_spy_move": spy_move,
        "p3_co_moving": co_moving,
        "families_agree": families_agree,
        "persistence_met": persistence_met,
        "confirmed": confirmed,
        "excluded_tickers": excluded,
        # READ-ONLY CALIBRATION column (anti-circularity wall 1): the judge's verdict at
        # alert time, stored ONLY so the health read can ask "does independent evidence
        # agree with the judge's blind-spot flag?" — never consulted above this line.
        "judge_fire_axes": alert.get("fire_axes"),
        "anchor_date": anchor_date,  # not persisted; used for the S3 stub name
    }
    # anchor_date is an internal field (the caller uses it for the S3 stub name) — strip it so it
    # never reaches the writer, a guarded contract (test_probe_unconfirmed_row_still_logged) that
    # defends against a future writer doing **row / adding an anchor_date column.
    persisted = {k: v for k, v in row.items() if k != "anchor_date"}
    await upsert_coverage_probe_row(conn, persisted)
    return row


async def _feed_confirmed_cohort(conn: Any, row: dict) -> "str | None":
    """S3: upsert one CONFIRMED cohort into mi_theme_candidates_shadow
    (source='coverage_probe' — surface-only per the get_shadow_theme_candidates
    carve-out). Honors mi_theme_exclusions against the stub name. Returns the candidate
    name written, or None when exclusions shrank the cohort below the floor."""
    cohort = set(row["cohort_tickers"])
    industries = await get_industries_for_tickers(conn, sorted(cohort))
    dominant = None
    if industries:
        dominant = Counter(industries.values()).most_common(1)[0][0]
    else:
        sectors = await get_sectors_batch(
            [t.upper() for t in sorted(cohort)], conn=conn)
        if sectors:
            dominant = Counter(sectors.values()).most_common(1)[0][0]
    name = build_stub_name(dominant, row["anchor_date"])

    banned = await get_theme_excluded_tickers(conn, name, sorted(cohort))
    members = sorted(cohort - banned)
    if len(members) < MIN_COHORT_MEMBERS:
        return None
    thesis = (
        f"Coverage-probe blind-spot cohort around {row['ticker']} "
        f"(P1 name-match x{row['p1_name_score']} + market-adjusted co-movement, "
        f"persistent since {row['anchor_date']}). Deterministic stub — zero-LLM; "
        f"validation/canonicalization applies at promote."
    )
    await upsert_coverage_probe_candidate(conn, row["alert_date"], name, members, thesis)
    await log_audit_event(
        "coverage_probe_candidate_written",
        f"{name}: {len(members)} member(s) ({', '.join(members[:8])})"
        f" — surface-only (source='coverage_probe'; /promotetheme to graduate)",
    )
    return name


# ── The EOD job core (date-parameterized; scheduler wrapper passes et_today()) ──────────

async def run_coverage_probe(today: Any) -> dict:
    """Run the coverage probe for `today`'s EP alerts. DEFENSIVELY WRAPPED — never raises
    (a probe failure must never break the EOD chain): job-level errors → the
    'coverage_probe_error' audit event; per-alert errors → 'coverage_probe_alert_error'
    (both END in _error so the nightly %error% Telegram sweep + the %_error weekly
    surfacer catch a silent detection-path failure — #173/#381 class) and the loop
    continues. Returns a summary dict for logs/verify-live."""
    out = {
        "date": str(today), "alerts": 0, "themeless": 0, "families_agree": 0,
        "confirmed": 0, "candidates_written": 0, "error": None,
    }
    try:
        from agents.market_intelligence.collector import prev_trading_days

        alerts = await get_today_ep_alerts(today)
        subjects = [a for a in alerts if a.get("score_tier") in _PROBE_TIERS]
        out["alerts"] = len(subjects)
        if not subjects:
            await log_audit_event(
                "coverage_probe_ran", f"{today}: no HIGH/MODERATE alerts — no-op")
            return out

        day_alert_tickers = {(a.get("ticker") or "").upper() for a in alerts}
        universe_start = prev_trading_days(PEER_UNIVERSE_SESSIONS, today)[-1]
        persistence_start = prev_trading_days(PERSISTENCE_SESSIONS, today)[-1]

        pool = await get_pool()
        async with pool.acquire() as conn:
            peer_universe = set(
                await get_coverage_probe_peer_universe(conn, today, universe_start))
            cooldown_tickers = await get_active_cooldown_tickers(conn)
            prior_cohorts = await get_recent_probe_cohorts(conn, today, persistence_start)

            for alert in subjects:
                try:
                    row = await _probe_one_alert(
                        conn, alert, day_alert_tickers, peer_universe,
                        cooldown_tickers, prior_cohorts)
                    if row is None:
                        continue  # theme-tracked — not a blind spot
                    out["themeless"] += 1
                    if row["families_agree"]:
                        out["families_agree"] += 1
                    if row["confirmed"]:
                        out["confirmed"] += 1
                        name = await _feed_confirmed_cohort(conn, row)
                        if name:
                            out["candidates_written"] += 1
                except Exception as _ae:
                    logger.warning(
                        f"coverage probe: alert {alert.get('ticker')} failed: {_ae}")
                    await log_audit_event(
                        "coverage_probe_alert_error",
                        f"{alert.get('ticker')} {today}: {type(_ae).__name__}: {_ae}",
                    )

        await log_audit_event(
            "coverage_probe_ran",
            f"{today}: {out['alerts']} alert(s), {out['themeless']} themeless, "
            f"{out['families_agree']} families-agree, {out['confirmed']} confirmed, "
            f"{out['candidates_written']} candidate(s) written",
        )
        logger.info(f"coverage probe: {out}")
        return out
    except Exception as _e:
        # SHADOW: the EOD chain must never see this. Counted, never silent.
        logger.error(f"coverage probe failed: {_e}", exc_info=True)
        out["error"] = str(_e)[:200]
        try:
            await log_audit_event(
                "coverage_probe_error", f"{today}: {type(_e).__name__}: {_e}")
        except Exception:  # loud-ok: audit-of-audit best-effort; logger.error above already surfaced it
            pass
        return out
