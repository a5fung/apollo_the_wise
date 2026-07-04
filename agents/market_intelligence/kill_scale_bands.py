"""#275 — kill/scale band EVALUATION + transition alerts + override awareness.

Implements the SIGNED live-money bands (`docs/setups/safeguards.md` → "Kill / scale
criteria", #268b, operator-signed 2026-06-12). These are **operator DECISION triggers**,
NOT mechanical blocks — the mechanical guards stay the daily-loss limit (2%) and the tiered
drawdown breaker. This module:
  - EVALUATES the live closed-trade cohort against the bands (Sunday digest + on demand),
  - emits a band on each evaluation so a TRANSITION can Telegram immediately at trade close
    (deduped via persisted state, mirroring the drawdown-tier alerts), and
  - surfaces active operator OVERRIDES so the digest annotates rather than re-prompts.

Calibration envelope (#268 Phase B, n=399, +0.95R/30% healthy year). The bands sit OUTSIDE
the worst the healthy year produced, so a kill rule never fires on normal variance:
  trailing-20 expectancy p5 −0.63R / min −1.03R · worst losing streak 15 · maxDD −24.1R.

The pure evaluator here is the load-bearing piece (unit-tested against the envelope above).
Data plumbing (which trades, realized R) + digest/alert/override wiring live separately so
this stays dependency-free and testable.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── SIGNED band thresholds (safeguards.md #268b). Change ONLY via CHANGE_PROCESS. ──
_KILL_T20 = -1.05        # trailing-20 expectancy ≤ this (worse than worst healthy window −1.03)
_KILL_CUM_R = -30.0      # cumulative live R ≤ this (beyond the −24R healthy maxDD)
_REDUCE_T20 = -0.70      # trailing-20 expectancy ≤ this (below healthy p5 −0.63)
_REDUCE_STREAK = 16      # current losing streak ≥ this (exceeds worst observed 15)
_SCALE_MIN_TRADES = 40   # trailing-40 needs ≥ this many trades
_SCALE_T40 = 0.50        # trailing-40 expectancy ≥ this to scale up
_SAMPLE_FLOOR = 20       # no strategy-health band (expectancy/streak/cum-R) before this many

# ── #268b Phase-B calibration envelope — the healthy +0.95R year the bands sit OUTSIDE. ──
# SINGLE CODE SOURCE for the fingerprint (was prose-only in this module's docstring +
# duplicated in safeguards.md, docs/analysis/selection_replay_268_phaseB.md, and
# data_gated_reviews.yaml). The #302 replay-regression report compares the accruing LIVE
# distribution against this card. NB: expectancy/win_rate are per-trade (comparable at any
# N); max_dd_r/worst_streak are full-year PATH stats (a short live cohort can't reach them —
# NOT a low-N comparison, advisor 2026-06-19). Change ONLY via CHANGE_PROCESS.
CALIBRATION_ENVELOPE = {
    "source": "#268b Phase B, n=399",
    "n": 399,
    "expectancy_r": 0.95,
    "win_rate": 0.30,
    "max_dd_r": -24.1,
    "worst_streak": 15,
    "trailing20_p5_r": -0.63,
    "trailing20_min_r": -1.03,
}

# The four bands (severity worst→best). NB: transition alerting fires on ANY change
# (`is_transition` is a plain inequality), not on worsening only — the ordering is
# documentation, not gating logic.
BANDS = ("KILL", "REDUCE", "HOLD", "SCALE")


def _mean_tail(rs: list[float], n: int) -> float | None:
    """Mean of the last `n` realized-R values (the CURRENT trailing-n window); None if the
    cohort is shorter than n — matches the calibration's window definition."""
    return sum(rs[-n:]) / n if len(rs) >= n else None


def current_losing_streak(rs: list[float]) -> int:
    """Consecutive losses from the most recent trade backward. A breakeven (r ≤ 0) counts as
    a loss — same convention as the #268 calibration's worst-streak=15."""
    s = 0
    for r in reversed(rs):
        if r <= 0:
            s += 1
        else:
            break
    return s


@dataclass
class BandVerdict:
    band: str                       # one of BANDS
    action: str                     # the pre-committed action phrase for `band`
    reasons: list[str] = field(default_factory=list)
    n_trades: int = 0
    trailing_20: float | None = None
    trailing_40: float | None = None
    streak: int = 0
    cum_r: float = 0.0


_ACTION = {
    "SCALE": "Raise risk/trade one notch (operator confirm at each notch)",
    "HOLD": "No change",
    "REDUCE": "Halve risk/trade until trailing-20 expectancy ≥ 0",
    "KILL": "Stop live entries; revert to paper; postmortem + operator re-arm",
}


def evaluate_kill_scale_bands(realized_rs, *, equity_above_start: bool,
                              drawdown_tier: str = "OK") -> BandVerdict:
    """Evaluate the SIGNED kill/scale bands against a chronological (oldest→newest) list of
    realized-R values for the live closed-trade cohort.

    Precedence: the drawdown-breaker BLOCK equity guard (binds from day 1) → KILL → REDUCE →
    SCALE → HOLD. Strategy-health triggers (trailing-20 expectancy, losing streak, cumulative
    R) are gated behind the `_SAMPLE_FLOOR` (20 trades); before that only the equity guards
    bind, per safeguards.md.
    """
    rs = [float(r) for r in realized_rs if r is not None]
    n = len(rs)
    t20 = _mean_tail(rs, 20)
    t40 = _mean_tail(rs, 40)
    streak = current_losing_streak(rs)
    cum_r = sum(rs)
    tier = (drawdown_tier or "OK").upper()

    def verdict(band: str, reasons: list[str]) -> BandVerdict:
        return BandVerdict(band, _ACTION[band], reasons, n, t20, t40, streak, cum_r)

    # Equity guard — the drawdown breaker's BLOCK tier (−12% equity) binds from day 1.
    if tier == "BLOCK":
        return verdict("KILL", ["drawdown breaker BLOCK tier (−12% equity)"])

    # Strategy-health bands require the sample-size floor.
    if n < _SAMPLE_FLOOR:
        return verdict("HOLD", [f"{n} closed trades < {_SAMPLE_FLOOR} sample floor — "
                                f"only equity guards bind"])

    kill = []
    if t20 is not None and t20 <= _KILL_T20:
        kill.append(f"trailing-20 {t20:+.2f}R ≤ {_KILL_T20:+.2f}R")
    if cum_r <= _KILL_CUM_R:
        kill.append(f"cumulative {cum_r:+.1f}R ≤ {_KILL_CUM_R:+.0f}R")
    if kill:
        return verdict("KILL", kill)

    reduce_ = []
    if t20 is not None and t20 <= _REDUCE_T20:
        reduce_.append(f"trailing-20 {t20:+.2f}R ≤ {_REDUCE_T20:+.2f}R")
    if streak >= _REDUCE_STREAK:
        reduce_.append(f"losing streak {streak} ≥ {_REDUCE_STREAK}")
    if reduce_:
        return verdict("REDUCE", reduce_)

    if n >= _SCALE_MIN_TRADES and t40 is not None and t40 >= _SCALE_T40 and equity_above_start:
        return verdict("SCALE", [f"{n} trades · trailing-40 {t40:+.2f}R ≥ +{_SCALE_T40:.2f}R "
                                 f"· equity > start"])

    return verdict("HOLD", ["within bands"])


def is_transition(prev_band: str | None, new_band: str) -> bool:
    """A band TRANSITION worth an immediate alert: any change from the last-evaluated band
    (first observation of a non-HOLD band also counts). prev_band None = no prior eval."""
    if new_band not in BANDS:
        return False
    return prev_band != new_band


# ── Data source + presentation (DB-sourced; the pure core above stays import-free) ──────

_BAND_EMOJI = {"SCALE": "🟢", "HOLD": "⚪", "REDUCE": "🟠", "KILL": "🔴"}


async def assemble_band_inputs(account_mode: str = "live") -> dict:
    """Gather the live closed-trade cohort + equity/drawdown inputs for the band evaluator.
    DB-sourced only (no Alpaca call) so it runs anywhere, anytime — pre-launch it returns an
    empty cohort → the evaluator HOLDs below the sample floor.

    realized R = `total_pnl / risk_dollars` over `status='closed'` methodology trades
    (`pnl_attribution IS NULL`), chronological — the SAME definition as the #291 GATE-3
    cohort (`scripts/sip_replay_r_cohort.py`); keep them in lockstep if either changes.
    """
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as c:
        trades = await c.fetch(
            """
            SELECT total_pnl, risk_dollars
            FROM mi_live_trades
            WHERE status = 'closed' AND account_mode = $1
              AND pnl_attribution IS NULL
              AND risk_dollars IS NOT NULL AND risk_dollars <> 0
            ORDER BY alert_date ASC, id ASC
            """, account_mode)
        # Persisted drawdown tier (NOT a live Alpaca call — the recompute cron owns it).
        dd = await c.fetchval(
            "SELECT state FROM mi_safeguard_state "
            "WHERE safeguard = 'drawdown_breaker' AND account_mode = $1", account_mode)
        # Equity vs starting equity = earliest vs latest live snapshot (SCALE input). Read
        # only the two endpoints — the snapshot table grows ~252 rows/yr/mode forever.
        eq = await c.fetchrow(
            """
            SELECT (SELECT equity FROM mi_account_equity_snapshots
                    WHERE account_mode = $1 ORDER BY snapshot_date ASC  LIMIT 1) AS first_eq,
                   (SELECT equity FROM mi_account_equity_snapshots
                    WHERE account_mode = $1 ORDER BY snapshot_date DESC LIMIT 1) AS last_eq
            """, account_mode)

    rs = [float(t["total_pnl"]) / float(t["risk_dollars"]) for t in trades]
    # Map the persisted breaker state to a band tier; legacy TRIPPED → REDUCE (safeguards.md).
    tier = {"BLOCK": "BLOCK", "REDUCE": "REDUCE", "WATCH": "WATCH", "TRIPPED": "REDUCE"}.get(
        (dd or "OK").upper(), "OK")
    equity_above_start = (eq["first_eq"] is not None and eq["last_eq"] is not None
                          and float(eq["last_eq"]) > float(eq["first_eq"]))
    return {"realized_rs": rs, "drawdown_tier": tier,
            "equity_above_start": equity_above_start, "account_mode": account_mode}


async def get_active_override() -> dict | None:
    """The most recent ACTIVE operator override (a `kill_scale_override` audit row not yet
    cleared by a later `kill_scale_override_cleared`) — so the verdict annotates instead of
    re-prompting weekly (safeguards.md operator condition #2). Overrides are GLOBAL, not
    per-account-mode: the bands are a single live-money concept and the override is one
    operator decision (if per-mode override ever becomes real, give it structured storage)."""
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as c:
        row = await c.fetchrow(
            """
            SELECT detail, created_at FROM mi_audit_log
            WHERE event_type = 'kill_scale_override'
            ORDER BY created_at DESC LIMIT 1
            """)
        if not row:
            return None
        cleared = await c.fetchval(
            "SELECT 1 FROM mi_audit_log WHERE event_type = 'kill_scale_override_cleared' "
            "AND created_at > $1 LIMIT 1", row["created_at"])
    if cleared:
        return None
    try:
        d = json.loads(row["detail"])
    except Exception as e:
        logger.warning("get_active_override: malformed detail JSON on %s row "
                        "(direction/reason lost): %s", row["created_at"], e)
        d = {}
    return {"direction": d.get("direction"), "reason": d.get("reason"),
            "since": row["created_at"].date().isoformat()}


_LAST_BAND_SAFEGUARD = "kill_scale_band"  # mi_safeguard_state PK with account_mode


async def get_last_band(account_mode: str = "live") -> tuple[str | None, str | None]:
    """The last-evaluated band + its transition date (for dedup + the 'since' on the alert)."""
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT state, last_transition_at FROM mi_safeguard_state "
            "WHERE safeguard = $1 AND account_mode = $2", _LAST_BAND_SAFEGUARD, account_mode)
    if not row:
        return None, None
    since = row["last_transition_at"].date().isoformat() if row["last_transition_at"] else None
    return row["state"], since


async def set_last_band(account_mode: str, band: str) -> bool:
    """Atomically CLAIM the band transition, returning True only if THIS call's write actually
    changed the persisted state (F21 — the old read-then-write was a TOCTOU: `get_last_band()`
    then `set_last_band()` unlocked let a concurrent scheduled + on-demand evaluation both
    observe `transitioned=True` and both alert). Only the winner should audit/alert; the loser
    sees `False` and skips (see `run_band_evaluation`).

    Delegates to `db.claim_safeguard_state_transition` (simplify GROUP 4, 2026-07-03) — the
    single-winner UPSERT primitive this function originally introduced is now shared with
    `broker/drawdown_breaker.py`'s `recompute_drawdown_state`, which had the same TOCTOU."""
    from agents.market_intelligence.db import claim_safeguard_state_transition
    return await claim_safeguard_state_transition(_LAST_BAND_SAFEGUARD, account_mode, band)


async def record_override(direction: str, reason: str) -> None:
    """Write a `kill_scale_override` audit row (safeguards.md operator condition #2; GLOBAL).
    The verdict reader (get_active_override) then annotates instead of re-prompting."""
    from agents.market_intelligence.db import log_audit_event
    await log_audit_event("kill_scale_override",
                          f"operator override: {direction}",
                          json.dumps({"direction": direction, "reason": reason}))


async def clear_override() -> None:
    """Write a `kill_scale_override_cleared` audit row — ends the active (global) override."""
    from agents.market_intelligence.db import log_audit_event
    await log_audit_event("kill_scale_override_cleared", "operator cleared override", "{}")


async def assess_bands(account_mode: str = "live") -> tuple[dict, BandVerdict, dict | None]:
    """Shared assemble→evaluate→override pipeline. The digest, the EOD alert, and the
    on-demand script all go through here, so the inputs-dict → evaluator-kwargs mapping lives
    in ONE place (a change to assemble_band_inputs or evaluate_kill_scale_bands lands once)."""
    inputs = await assemble_band_inputs(account_mode)
    verdict = evaluate_kill_scale_bands(
        inputs["realized_rs"], equity_above_start=inputs["equity_above_start"],
        drawdown_tier=inputs["drawdown_tier"])
    return inputs, verdict, await get_active_override()


async def run_band_evaluation(account_mode: str = "live", *, send: bool = True) -> dict:
    """Daily EOD evaluation (mirrors the drawdown-tier alert cadence — the band inputs only
    refresh at the 16:12 equity snapshot, so daily-resolution is correct). Evaluates the
    SIGNED bands, and on a TRANSITION from the last-persisted band emits an immediate Telegram
    (transition-only, deduped via mi_safeguard_state) + a `kill_scale_band_transition` audit
    row. Fully error-wrapped — telemetry must never break the EOD chain. Returns a summary.

    F21 dedup: `is_transition(prev_band, ...)` is a cheap LOCAL pre-check on a plain (unlocked)
    read — under concurrency it can be stale, so it is NOT what prevents duplicate alerts. The
    actual dedup is `set_last_band`'s ATOMIC claim: it is only attempted when the local check
    says a transition might be happening, and the audit/Telegram below only fire when that
    claim is actually won (`claimed is True`). A concurrent duplicate evaluation may also see
    `locally_transitioned=True`, but loses the atomic claim and returns `transitioned=False`."""
    try:
        _, verdict, override = await assess_bands(account_mode)
        prev_band, _ = await get_last_band(account_mode)
        locally_transitioned = is_transition(prev_band, verdict.band)

        claimed = False
        if locally_transitioned:
            claimed = await set_last_band(account_mode, verdict.band)

        if claimed:
            from agents.market_intelligence.db import log_audit_event
            await log_audit_event(
                "kill_scale_band_transition",
                f"{account_mode} {prev_band or '∅'} → {verdict.band}",
                json.dumps({"account_mode": account_mode, "prev_band": prev_band,
                            "band": verdict.band, "n_trades": verdict.n_trades,
                            "trailing_20": verdict.trailing_20, "cum_r": verdict.cum_r,
                            "reasons": verdict.reasons}))
            # Don't ping for the very first HOLD baseline (∅→HOLD pre-launch) — only real signal.
            notable = not (prev_band is None and verdict.band == "HOLD")
            if send and notable:
                from agents.market_intelligence.briefing import send_telegram_message
                arrow = f"{prev_band or '∅'} → {verdict.band}"
                await send_telegram_message(
                    f"📊 *Kill/scale band change* ({account_mode}): {arrow}\n"
                    + format_band_line(verdict, override))
        return {"band": verdict.band, "prev_band": prev_band, "transitioned": claimed,
                "n_trades": verdict.n_trades, "override_active": override is not None}
    except Exception as e:  # noqa: BLE001 — telemetry must never break the EOD chain
        logger.warning(f"run_band_evaluation({account_mode}) skipped: {e}")
        # Don't let a persistent failure silently FREEZE the band (audit_wrap sees a clean
        # return, not a raise) — emit a *_error row so the nightly error-check + morning
        # banner surface it (feedback_no_silent_trading_failures). Best-effort: if the DB
        # itself is down the log.warning above is the trail.
        try:
            from agents.market_intelligence.db import log_audit_event
            await log_audit_event(
                "kill_scale_band_eval_error",
                f"band eval failed ({account_mode}): {e}",
                json.dumps({"account_mode": account_mode, "error": str(e)}))
        except Exception:  # loud-ok: fallback-of-the-fallback — the log.warning two
            # lines above already captured the real failure (comment at the top of
            # this except block); this inner guard only protects the *_error audit
            # write itself, and there's nothing left above it to escalate to.
            pass
        return {"error": str(e)}


async def band_digest_section(account_mode: str = "live") -> list[str]:
    """The weekly-review section (a SECTION of the existing digest, not a new surface —
    feedback_consolidate_surfaces). SURFACES the verdict + numbers; never prescribes code."""
    try:
        _, verdict, override = await assess_bands(account_mode)
        return ["", "*🎚️ Kill/scale bands* (live-money, #268b):", format_band_line(verdict, override)]
    except Exception as e:  # noqa: BLE001
        logger.warning("band_digest_section(%s) failed: %s", account_mode, e)
        return ["", f"_kill/scale band eval unavailable: {e}_"]


def format_band_line(v: BandVerdict, override: dict | None = None) -> str:
    """One-line Telegram/digest verdict — band + the numbers that drove it, override-aware."""
    emoji = _BAND_EMOJI.get(v.band, "⚪")
    t20 = f"{v.trailing_20:+.2f}R" if v.trailing_20 is not None else "n/a"
    t40 = f"{v.trailing_40:+.2f}R" if v.trailing_40 is not None else "n/a"
    head = (f"{emoji} *Kill/scale band: {v.band}* — {v.action}\n"
            f"  n={v.n_trades} · t20={t20} · t40={t40} · streak={v.streak} · cum={v.cum_r:+.1f}R\n"
            f"  {'; '.join(v.reasons)}")
    if override:
        head += (f"\n  ⚠️ operator OVERRIDE ACTIVE since {override['since']} "
                 f"({override.get('direction') or '?'}): {override.get('reason') or ''}")
    return head
