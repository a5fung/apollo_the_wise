"""Theme BIRTH GATE — theme consolidation Phase 1 (operator-ruled 2026-07-27).

Design: docs/design/theme_system_consolidation_2026-07-27.md §3/§8 Phase 1.
Derivation of every threshold: docs/analysis/theme_birth_gate_derivation_2026-07-27.md
(254-birth replay, prod snapshot after the 17:05 ET nightly).

ONE gate in front of every live-theme birth — Lane-1 discovery AND the
`shadow_promoted` graduation path (which previously bypassed adjudication
entirely; the RS-38.7 / RS-49.1 graduates of 2026-07-27 entered there).

THREE-STATE toggle `theme_birth_gate` in mi_safeguard_state (db.BIRTH_GATE_MODES,
the broker_order_ingest off/dry_run/live idiom, FAIL-CLOSED 'off'):
  off     — this module is never invoked; behavior byte-identical to today
            (pinned by tests/test_theme_birth_gate.py).
  observe — the DEPLOY state: every would-be birth is evaluated and the verdict
            RECORDED (ledger row + audit JSON: outcome, deciding lever,
            member-avg RS, pre-birth Δ5-session, IoS vs board/ledger) but
            NOTHING is acted on — the theme is born exactly as today, promote
            untouched, retirements inactive, allowlist unchanged. Forward
            evidence accrues BEFORE the gate ever touches a live theme; the
            observe→on comparison is the data-gated review
            `theme_birth_gate_observe_calibration`.
  on      — the gate acts as designed (births filtered, lanes retired).

The gate, in order (each lever measured independently in the derivation):

1. JOIN-OR-NEW — a proposal whose members overlap >= 50% (intersection-over-
   smaller, coverage_probe's own cohort_overlap primitive) with a theme ALIVE
   on the board is a re-mint, not a birth → outcome `join` (suppressed; the bet
   is already on the board under the target's name). July replay: 50/106 births
   were this. SCOPE CARVE-OUT: a candidate whose member-majority is ALREADY
   COVERED by live themes is a refinement/sub-theme proposal (the elite-split
   path, ADR-0032 territory) — the join check is SKIPPED for those (the
   existing merge/Route-A machinery owns refinements; gating them here would
   regress live sub-theme discovery). Net-new cohorts get the full check.
2. LEDGER MATCH + TWO-SIGHTING BAR — the proposal resolves against the last 14
   days of `mi_theme_birth_candidates` (including quiet/held ones — the #476
   re-mint memory). A NEW cohort surfaces to the board only on its >= 2nd
   DISTINCT-DAY sighting. Costless delay: discovery is nightly and the earliest
   tradable signal (a member EP alert) is not gated on theme birth. July
   replay: kills the never-re-sighted 1-day class, delays the rest by ~1 day.
3. DERIVED FLOOR — member-avg RS >= 70 (BIRTH_GATE_RS_FLOOR) **OR** the cohort
   is RISING: 5-session RS trajectory >= 0 (BIRTH_GATE_TRAJ_MIN). The flat
   >=70 the operator adopted as a starting point was DERIVED AGAINST by the
   254-birth replay: matured-vs-died birth-RS medians are 90.8 vs 88.5 (no
   level separation), a flat >=70 blocks 26 of the 134 themes that ever
   matured (19.4% false-negative, 40% precision), and the weak-born-then-
   matured class the north star hunts is real (26/134 = 19% of all matured
   themes were born < 70). The TRAJECTORY separates where the level cannot:
   weak-born maturers' pre-birth 5-session delta median +2.5 (15/26 rising)
   vs weak-born corpses -5.3 (7/17 rising). The OR-cell halves the false
   negatives (26 → 11) at equal junk-kill. Unknown RS / unknown trajectory
   NEVER passes that arm (fail-closed per-arm; a candidate held on unknowns
   stays in the ledger and retries on its next sighting).

P3 EVIDENCE ANNOTATION (decision 2: coverage_probe retires, its market-adjusted
co-movement primitive survives): each evaluation annotates the ledger row with
whether the cohort co-moved with its RS-leader on the run date, SPY-adjusted
(market_adjust_moves + compute_co_movement — imported from their existing
homes). ANNOTATION ONLY — never a blocking criterion in Phase 1: a co-movement
threshold was not derived from the 254-birth replay, and underived gates are
exactly what the derive-don't-pick discipline forbids. The accrued column is
the derivation input for any future co-movement arm.

EXISTING LIVE THEMES ARE UNTOUCHED, by construction:
- the gate is consulted ONLY for would-be NEW births (Lane 1: freshly
  discovered names not already on the board; promote: first-ever crossings —
  a name with ANY prior mi_themes row bypasses the gate as maintenance);
- no code path here mutates mi_themes — a `join` outcome only suppresses an
  INSERT that hasn't happened yet;
- board survivors of the retired shadow_v2 funnel live on independently: once
  live, the daily engine re-scores and re-saves them as its own source='live'
  rows (get_active_themes reads all sources) — verified against prod 2026-07-27.

SHADOW-ADJACENT INVARIANT: this module writes ONLY mi_theme_birth_candidates
and mi_audit_log. It never touches mi_themes, grades, or trade state.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from agents.market_intelligence.coverage_probe import (
    MARKET_TICKER,
    cohort_overlap,
    market_adjust_moves,
)
from agents.market_intelligence.theme_axis_shadow import compute_co_movement

logger = logging.getLogger(__name__)

# ── Derived thresholds (docs/analysis/theme_birth_gate_derivation_2026-07-27.md;
# operator signs this cell per CHANGE_PROCESS before any live flip) ───────────
BIRTH_GATE_RS_FLOOR = 70.0      # level arm — the operator's adopted start, kept
BIRTH_GATE_TRAJ_MIN = 0.0       # rising arm — pre-birth 5-session cohort ΔRS >= 0
BIRTH_GATE_TRAJ_SESSIONS = 5    # trajectory lookback (trading sessions)
BIRTH_GATE_MIN_SIGHTINGS = 2    # two-sighting bar (distinct days)
BIRTH_GATE_JOIN_OVERLAP = 0.5   # intersection-over-smaller vs the live board
BIRTH_GATE_LEDGER_DAYS = 14     # join-or-new memory incl. quiet candidates
# Refinement carve-out: if > this share of members are already covered by live
# themes, the proposal is a sub-theme/refinement of existing coverage — the
# join suppression is skipped (merge/Route-A owns it). Strictly-greater-than
# 0.5 so an exactly-half-covered cohort still gets the full net-new check.
BIRTH_GATE_REFINEMENT_COVERED_SHARE = 0.5


# ── Pure decision logic (unit-tested; no I/O) ────────────────────────────────

def gate_decision(
    rs_avg: "float | None",
    traj5: "float | None",
    sightings: int,
) -> tuple[bool, str]:
    """The derived floor + two-sighting bar. Returns (passes, reason).
    Boundary semantics (pinned by tests): sightings == 2 passes the bar;
    rs_avg == 70.0 passes the level arm; traj5 == 0.0 passes the rising arm.
    Unknown (None) never satisfies an arm."""
    if sightings < BIRTH_GATE_MIN_SIGHTINGS:
        return False, "await_second_sighting"
    if rs_avg is not None and rs_avg >= BIRTH_GATE_RS_FLOOR:
        return True, "pass_rs_level"
    if traj5 is not None and traj5 >= BIRTH_GATE_TRAJ_MIN:
        return True, "pass_rs_rising"
    if rs_avg is None:
        return False, "held_no_rs"
    return False, "held_floor"


def find_join_target(
    tickers: list[str],
    live_themes: list[dict],
    covered_tickers: "set[str] | None" = None,
) -> tuple["str | None", "float | None"]:
    """Join-or-new vs the LIVE board: the best (highest-overlap) non-Retired
    theme with >= BIRTH_GATE_JOIN_OVERLAP member overlap. Returns
    (target_name, overlap) — (None, None) when no join. The overlap value is
    recorded (observe-review input), not just the verdict.
    Refinement carve-out: when the candidate's member-majority is already
    covered (covered_tickers given), return (None, None) — sub-theme proposals
    are the existing merge machinery's job, not a re-mint."""
    cand = {t.upper() for t in tickers or []}
    if not cand:
        return None, None
    if covered_tickers:
        covered_share = len(cand & {t.upper() for t in covered_tickers}) / len(cand)
        if covered_share > BIRTH_GATE_REFINEMENT_COVERED_SHARE:
            return None, None
    best_name, best_ov = None, 0.0
    for t in live_themes or []:
        if t.get("stage") == "Retired":
            continue
        ov = cohort_overlap(cand, {tk.upper() for tk in (t.get("tickers") or [])})
        if ov >= BIRTH_GATE_JOIN_OVERLAP and ov > best_ov:
            best_name, best_ov = t.get("name"), ov
    return best_name, (best_ov if best_name is not None else None)


def find_ledger_match(
    tickers: list[str], candidates: list[dict],
) -> tuple["dict | None", "float | None"]:
    """The same cohort re-sighted: best >= BIRTH_GATE_JOIN_OVERLAP overlap
    among recent ledger candidates (list from db.get_recent_birth_candidates,
    already windowed to BIRTH_GATE_LEDGER_DAYS). Returns (candidate, overlap)
    — (None, None) when no match."""
    cand = {t.upper() for t in tickers or []}
    if not cand:
        return None, None
    best, best_ov = None, 0.0
    for c in candidates or []:
        ov = cohort_overlap(cand, {tk.upper() for tk in (c.get("tickers") or [])})
        if ov >= BIRTH_GATE_JOIN_OVERLAP and ov > best_ov:
            best, best_ov = c, ov
    return best, (best_ov if best is not None else None)


# ── Evidence annotation (P3 primitive — NEVER blocking) ──────────────────────

async def _p3_annotation(
    tickers: list[str], today: Any, rs_by_ticker: "dict[str, float] | None",
) -> tuple["bool | None", "float | None"]:
    """Market-adjusted co-movement of the cohort vs its RS-leader on `today`
    (coverage_probe's P3, kept as the gate's evidence primitive). Returns
    (co_moving, spy_move); (None, None) on any failure — annotation must never
    block or break a birth decision."""
    try:
        from agents.market_intelligence.db import get_daily_moves, get_pool
        members = sorted({t.upper() for t in tickers or []})
        if len(members) < 2:
            return None, None
        # Subject = the cohort's RS leader (highest member RS when known,
        # else first alphabetically — deterministic either way).
        subject = members[0]
        if rs_by_ticker:
            subject = max(members, key=lambda t: rs_by_ticker.get(t, -1.0))
        pool = await get_pool()
        async with pool.acquire() as conn:
            raw = await get_daily_moves(conn, today, members + [MARKET_TICKER])
        spy_move = raw.get(MARKET_TICKER)
        adj = market_adjust_moves(raw, spy_move)
        cohort_moves = [adj[t] for t in members if t != subject and t in adj]
        _, co_moving = compute_co_movement(adj.get(subject), cohort_moves)
        return co_moving, spy_move
    except Exception as e:  # noqa: BLE001 — annotation-only; surfaced, never blocking
        logger.warning(f"[birth gate] P3 annotation failed (non-blocking): {e}")
        return None, None


# ── The gate (DB-backed evaluation; callers hold the flag check) ─────────────

async def evaluate_birth(
    name: str,
    tickers: list[str],
    source: str,
    today: Any,
    live_themes: list[dict],
    *,
    mode: str = "on",
    covered_tickers: "set[str] | None" = None,
    ledger: "list[dict] | None" = None,
    rs_by_ticker: "dict[str, float] | None" = None,
) -> dict:
    """Evaluate ONE would-be birth. Returns
    {outcome: 'birth'|'join'|'await_second_sighting'|'held_floor'|'held_no_rs',
     reason, join_target, join_overlap, ledger_overlap, sightings, rs_avg,
     traj5, mode, candidate_id}.
    `mode` ('observe'|'on') is RECORD-KEEPING ONLY here — the verdict is
    computed identically in both; ACTING on it is the caller's branch. Every
    evaluation is recorded in the ledger with the deciding lever (`reason`)
    and its inputs, so an observe period is judgeable from stored rows alone.
    `ledger` may be passed in by batch callers to avoid N re-fetches — pass the
    SAME list across one run so two same-run proposals of one cohort match."""
    from agents.market_intelligence.db import (
        get_cohort_rs_snapshot,
        get_recent_birth_candidates,
        record_birth_candidate_sighting,
    )
    if ledger is None:
        ledger = await get_recent_birth_candidates(days=BIRTH_GATE_LEDGER_DAYS)

    join_target, join_overlap = find_join_target(tickers, live_themes, covered_tickers)

    match, ledger_overlap = find_ledger_match(tickers, ledger)
    prior_sightings = int(match["sightings"]) if match else 0
    today_d = today
    seen_today = bool(match) and match.get("last_seen") == today_d
    sightings = prior_sightings if seen_today else prior_sightings + 1

    rs_now, rs_prior = await get_cohort_rs_snapshot(
        tickers, sessions_back=BIRTH_GATE_TRAJ_SESSIONS)
    traj5 = (rs_now - rs_prior) if (rs_now is not None and rs_prior is not None) else None

    if join_target is not None:
        ok, reason = False, "join"
        outcome = "join"
    else:
        ok, reason = gate_decision(rs_now, traj5, sightings)
        outcome = "birth" if ok else reason

    co_moving, spy_move = await _p3_annotation(tickers, today, rs_by_ticker)

    cand_id = await record_birth_candidate_sighting(
        match["id"] if match else None,
        (match["name"] if match else name),  # ledger identity = first-seen name
        tickers, source, today,
        outcome=outcome, reason=reason, mode=mode,
        rs_avg=rs_now, rs_traj5=traj5,
        join_overlap=join_overlap, ledger_overlap=ledger_overlap,
        p3_co_moving=co_moving, p3_spy_move=spy_move, join_target=join_target)
    # Keep the in-run ledger list coherent for subsequent same-run proposals.
    if match:
        match["sightings"] = sightings
        match["last_seen"] = today_d
        match["tickers"] = sorted({*(match.get("tickers") or []), *tickers})
    else:
        ledger.append({
            "id": cand_id, "name": name, "first_seen": today_d, "last_seen": today_d,
            "sightings": sightings, "tickers": sorted(set(tickers)), "source": source,
            "status": "born" if outcome == "birth" else "watching",
        })

    return {
        "outcome": outcome, "reason": reason,
        "join_target": join_target, "join_overlap": join_overlap,
        "ledger_overlap": ledger_overlap,
        "sightings": sightings, "rs_avg": rs_now, "traj5": traj5,
        "mode": mode, "candidate_id": cand_id,
    }


async def _count_delayed_births() -> int:
    """Candidates the gate HELD that later re-presented and passed — the forward false-negative
    signal. Zero is the healthy reading. Fails to 0 rather than breaking the run: a counter that
    takes the nightly pull down would repeat the 2026-07-28 crash this gate already caused once."""
    try:
        from agents.market_intelligence.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            return int(await conn.fetchval("""
                SELECT COUNT(*) FROM mi_theme_birth_candidates
                WHERE status = 'born'
                  AND last_reason IN ('pass_rs_level', 'pass_rs_rising')
                  AND sightings > 1
            """) or 0)
    except Exception as e:  # loud-ok: logged; a counter must never break the gate it observes
        logger.warning(f"[birth gate] delayed-birth count failed (reporting 0): {e}")
        return 0


async def audit_gate_outcomes(
    lane: str, outcomes: list[dict], today: Any, mode: str = "on",
) -> None:
    """The Phase-1 counter-only observability line (design §7): ONE durable
    mi_audit_log row per gated run — births / joins / awaiting / held, no
    thresholds. The summary carries `[{lane}/{mode}]` (the observe-review
    predicate keys on it) and the JSON detail carries per-candidate verdict +
    deciding lever + inputs — the stored record the operator judges the
    observe period from. Never raises into the caller."""
    try:
        from agents.market_intelligence.db import log_audit_event
        n = {"birth": 0, "join": 0, "await_second_sighting": 0,
             "held_floor": 0, "held_no_rs": 0}
        for o in outcomes:
            n[o["outcome"]] = n.get(o["outcome"], 0) + 1
        # ⚠ THE FALSE-NEGATIVE COUNT (added 2026-08-03, operator asked what would monitor a bad
        # flip). A held candidate that LATER re-presents and passes is a theme this gate delayed —
        # the only forward measure of the cost the operator actually cares about, because his north
        # star is spotting a theme EARLY. The replay showed the risk is real: 21 of 44 sub-70 births
        # matured, and Domestic Steel was born at RS 27.8 and reached 92.
        #
        # It was already captured in mi_theme_birth_candidates and rendered NOWHERE — you had to
        # know to ask. Surfacing it on the line that already reports every run makes the observe
        # period judgeable instead of trusted. Counter-only; it changes no decision.
        delayed = await _count_delayed_births()
        await log_audit_event(
            "theme_birth_gate",
            summary=(f"{today} [{lane}/{mode}] birth-gate: {n['birth']} birth / {n['join']} join / "
                     f"{n['await_second_sighting']} awaiting-2nd-sighting / "
                     f"{n['held_floor'] + n['held_no_rs']} held-floor"
                     + (f" · ⚠ {delayed} previously-held later PASSED" if delayed else "")),
            detail=json.dumps([
                {k: (str(v) if k == "join_target" and v else v)
                 for k, v in o.items() if k != "candidate_id"}
                for o in outcomes
            ], default=str),
        )
    except Exception as e:  # noqa: BLE001 — observability must never break the run
        logger.warning(f"[birth gate] audit emit failed (non-fatal): {e}")
