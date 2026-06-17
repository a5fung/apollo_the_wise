"""P3 Management Judge (ADR 0014) — SHADOW, telemetry-only LLM second-opinion on the EXIT /
position-management decision.

Mirrors the grade-judge (ep_grade_judge): one Opus call per open position, a BOUNDED enum verdict
via a forced tool, fail-open (None on any error/timeout → caller writes nothing / audit-only). It
NEVER submits, cancels, or modifies an order — the mechanical exit system (stop trail, partials,
time-stop) stays the sole authority; P3 only observes and opines, accruing the agree/disagree-with-
mechanical evidence the real (load-bearing) P3 will need. Graduation = post-launch, own evidence +
CHANGE_PROCESS + sign-off.

R-math note (ADR 0014 / advisor 2026-06-17): the R denominator is the ORIGINAL entry risk
`entry − orb_low`, NEVER the trailed `stop_price` (which can sit ABOVE entry once profit is locked →
a negative denominator → garbage R that won't throw). R is None when orb_low is absent or >= entry.
"""
import asyncio
from typing import Optional

from agents.market_intelligence.judge_transport import invoke_forced_tool
from shared.llm_models import JUDGE_MODEL as MODEL

# The bounded management-verdict vocabulary (ADR 0014). An out-of-enum answer → fail-open (None).
VERDICTS = ("HOLD", "PARTIAL_TAKE", "TRAIL_TIGHTEN", "FORCE_EXIT")

_MGMT_TOOL = {
    "name": "manage_position",
    "description": "Give a single position-management verdict over the open position's full context.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": list(VERDICTS)},
            "rationale": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["verdict", "rationale"],
    },
}


def compute_position_metrics(position: dict, current_price: Optional[float]) -> dict:
    """Pure, testable. Returns {pct_from_entry, r_multiple, stop_above_entry, trailed_stop, orb_low}.

    r_multiple uses the ORIGINAL ORB-entry risk (entry − orb_low) — NOT the trailed stop_price.
    None when current_price/entry missing, or when orb_low is absent or >= entry (no valid initial
    risk reference; e.g. 9M Day-2 stops on the prior-day low — reconciled in part 2)."""
    def _f(v):
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    entry = _f(position.get("entry_price"))
    orb_low = _f(position.get("orb_low"))
    stop = _f(position.get("stop_price"))
    px = _f(current_price)

    pct = ((px - entry) / entry) if (px is not None and entry not in (None, 0)) else None
    r = None
    if px is not None and entry is not None and orb_low is not None and orb_low < entry:
        r = (px - entry) / (entry - orb_low)
    return {
        "pct_from_entry": round(pct, 4) if pct is not None else None,
        "r_multiple": round(r, 2) if r is not None else None,
        "stop_above_entry": (stop is not None and entry is not None and stop > entry),
        "trailed_stop": stop,
        "orb_low": orb_low,
    }


def assemble_mgmt_inputs(position: dict, current_price: Optional[float],
                         thesis: Optional[dict] = None) -> dict:
    """Pack one open position's signals into the management-judge payload. `thesis` = the original
    entry grade from mi_ep_alerts (catalyst, judge tier, ep_score) — None if not found."""
    m = compute_position_metrics(position, current_price)
    thesis = thesis or {}
    return {
        "ticker": position.get("ticker"),
        "hold_days": position.get("hold_days"),
        "current_price": float(current_price) if current_price is not None else None,
        "entry_price": position.get("entry_price"),
        "remaining_shares": position.get("remaining_shares"),
        "account_mode": position.get("account_mode"),
        **m,
        # mechanical posture — DESCRIPTIVE (agreement assessed at operator label time, not here)
        "partial_taken": bool(position.get("partial_taken")),
        # (time_stop_eligible deferred to part 2 — needs hold_days + peak excursion per #91; a
        #  hold_days-only proxy would falsely flag long WINNERS like FPS, so omit until computed)
        # original entry thesis
        "catalyst": (thesis.get("catalyst") or "")[:800],
        "entry_grade_tier": thesis.get("score_tier"),
        "ep_score": thesis.get("ep_score") or position.get("ep_score"),
        "catalyst_quality": thesis.get("catalyst_quality") or position.get("catalyst_quality"),
    }


def _b(v):
    return "yes" if v else "no"


def _build_mgmt_prompt(p: dict) -> str:
    r = p.get("r_multiple")
    pct = p.get("pct_from_entry")
    return f"""You are a disciplined momentum/EP swing trader managing an OPEN position at end of day.
Give ONE management verdict from: HOLD, PARTIAL_TAKE, TRAIL_TIGHTEN, FORCE_EXIT.

This is a SHADOW second opinion — it does NOT execute. Judge whether the position should be held,
de-risked, tightened, or exited, weighing: is the original thesis still intact, where is price
relative to entry and to the original risk, how long it has been held, and whether profit is already
protected by a stop above entry.

--- POSITION ---
Ticker: {p.get('ticker')}  |  held {p.get('hold_days')} day(s)  |  shares: {p.get('remaining_shares')}
Entry: {p.get('entry_price')}  |  Current: {p.get('current_price')}
Move from entry: {f'{pct * 100:+.1f}%' if pct is not None else 'n/a'}  |  R (vs original entry risk): {r if r is not None else 'n/a'}
Original entry stop (ORB low): {p.get('orb_low')}  |  Current trailed stop: {p.get('trailed_stop')}  |  Stop above entry (profit locked): {_b(p.get('stop_above_entry'))}
Partial already taken: {_b(p.get('partial_taken'))}

--- ORIGINAL ENTRY THESIS ---
Entry grade tier: {p.get('entry_grade_tier') or 'n/a'}  |  EP score: {p.get('ep_score')}  |  catalyst quality: {p.get('catalyst_quality')}
Catalyst: {p.get('catalyst') or 'n/a'}

Return the verdict + a one-sentence rationale citing the decisive factor."""


def _normalize_mgmt_verdict(raw: dict) -> Optional[dict]:
    """Validate the tool output: verdict in the bounded enum + a rationale. None → fail-open."""
    if not isinstance(raw, dict):
        return None
    verdict = raw.get("verdict")
    if verdict not in VERDICTS:
        return None
    rationale = (raw.get("rationale") or "").strip()
    if not rationale:
        return None
    out = {"verdict": verdict, "rationale": rationale[:600]}
    conf = raw.get("confidence")
    if isinstance(conf, (int, float)):
        out["confidence"] = float(conf)
    return out


async def manage_holistic(
    client,
    payload: dict,
    *,
    semaphore: Optional[asyncio.Semaphore] = None,
    timeout: float = 25.0,
    model: str = MODEL,
) -> Optional[dict]:
    """One management-judge call. Returns the bounded verdict dict, or None on any error/timeout
    (FAIL-OPEN — the caller writes nothing / audit-only, never executes). Transport (semaphore,
    timeout, tool_use extraction, credit-exhaustion alert + fail-open) is the shared
    judge_transport.invoke_forced_tool; only the prompt/tool/normalizer are management-specific."""
    return await invoke_forced_tool(
        client, _build_mgmt_prompt(payload),
        tool=_MGMT_TOOL, tool_name="manage_position",
        normalize=_normalize_mgmt_verdict, label="management judge",
        subject=payload.get("ticker") or "",
        semaphore=semaphore, timeout=timeout, model=model)
