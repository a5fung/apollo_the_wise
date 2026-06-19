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

from dataclasses import dataclass, field

# ── SIGNED band thresholds (safeguards.md #268b). Change ONLY via CHANGE_PROCESS. ──
_KILL_T20 = -1.05        # trailing-20 expectancy ≤ this (worse than worst healthy window −1.03)
_KILL_CUM_R = -30.0      # cumulative live R ≤ this (beyond the −24R healthy maxDD)
_REDUCE_T20 = -0.70      # trailing-20 expectancy ≤ this (below healthy p5 −0.63)
_REDUCE_STREAK = 16      # current losing streak ≥ this (exceeds worst observed 15)
_SCALE_MIN_TRADES = 40   # trailing-40 needs ≥ this many trades
_SCALE_T40 = 0.50        # trailing-40 expectancy ≥ this to scale up
_SAMPLE_FLOOR = 20       # no strategy-health band (expectancy/streak/cum-R) before this many

# Ordered worst→best for transition severity comparison.
BANDS = ("KILL", "REDUCE", "HOLD", "SCALE")
_SEVERITY = {b: i for i, b in enumerate(BANDS)}  # KILL=0 (most severe) … SCALE=3


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
    if new_band not in _SEVERITY:
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
        # Equity vs starting equity = earliest vs latest live snapshot (SCALE input).
        eq = await c.fetch(
            "SELECT equity FROM mi_account_equity_snapshots "
            "WHERE account_mode = $1 ORDER BY snapshot_date ASC", account_mode)

    rs = [float(t["total_pnl"]) / float(t["risk_dollars"]) for t in trades]
    # Map the persisted breaker state to a band tier; legacy TRIPPED → REDUCE (safeguards.md).
    tier = {"BLOCK": "BLOCK", "REDUCE": "REDUCE", "WATCH": "WATCH", "TRIPPED": "REDUCE"}.get(
        (dd or "OK").upper(), "OK")
    equity_above_start = (len(eq) >= 2 and float(eq[-1]["equity"]) > float(eq[0]["equity"]))
    return {"realized_rs": rs, "drawdown_tier": tier,
            "equity_above_start": equity_above_start, "account_mode": account_mode}


async def get_active_override(account_mode: str = "live") -> dict | None:
    """The most recent ACTIVE operator override (a `kill_scale_override` audit row not yet
    cleared by a later `kill_scale_override_cleared`) — so the verdict annotates instead of
    re-prompting weekly (safeguards.md operator condition #2)."""
    from agents.market_intelligence.db import get_pool
    import json
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
    except Exception:
        d = {}
    return {"direction": d.get("direction"), "reason": d.get("reason"),
            "since": row["created_at"].date().isoformat()}


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
