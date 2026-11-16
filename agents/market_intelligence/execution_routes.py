"""#256 W2 commit 5a — apollo-execution HTTP routes (server side of the
execution_client http transport).

Mounted on the shared agent app, but REGISTERED only when this process runs
execution jobs (SERVICE_ROLE in combined/execution). The intelligence service is
the CLIENT — it never serves these.

Handlers call execution_client's `_<name>_inprocess` bodies DIRECTLY (never the
dispatcher) so an inbound http request can't loop back out as another http call
(advisor 6/13 #3). This module imports only execution_client (allowlisted for the
[5j] boundary gate) + the base auth dependency — NO broker imports here.
"""
from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Response

from agents.base import verify_internal_secret
from agents.market_intelligence import execution_client as _ec

logger = logging.getLogger(__name__)

# Wire name → in-process implementation — DERIVED from execution_client._CROSS_FNS
# (#279; was a hand-written 16-entry mirror + a registration-time parity assert).
# CONVENTION CONTRACT: every cross-listed wire name `<name>` has a
# `_<name>_inprocess` body in execution_client (its module docstring is the
# contract's home). Deriving the map makes route↔client drift impossible by
# construction: a cross-listed name without a matching `_<name>_inprocess` body
# fails the getattr RIGHT HERE at import — same fail-loud-at-boot semantics as
# the old mirror assert, minus the hand-sync.
_EXEC_HANDLERS = {
    name: getattr(_ec, f"_{name}_inprocess") for name in sorted(_ec._CROSS_FNS)
}


def research_blocked_now(now=None) -> bool:
    """True 09:20-10:05 ET Mon-Fri: research bar pulls stay off the Alpaca data
    budget while the ORB entries run (2026-11-15). It starts 5 minutes BEFORE the
    09:25 pre-open work as a lead margin: one request may run up to 120 s, so a
    pull admitted at 09:24 could still be on Alpaca's rate limit at 09:26.
    Holidays are not excluded — a refusal on a closed day costs a re-run, nothing
    more."""
    from datetime import datetime, time
    from zoneinfo import ZoneInfo
    n = (now or datetime.now(ZoneInfo("America/New_York"))).astimezone(ZoneInfo("America/New_York"))
    return n.weekday() < 5 and time(9, 20) <= n.time() < time(10, 5)


def register_execution_routes(app) -> None:
    """Add POST /exec/{name} and POST /data/bars to `app`. Call only when
    runs_execution_jobs()."""
    # Route↔client parity holds by construction — _EXEC_HANDLERS is derived from
    # _CROSS_FNS at import, and a convention break fails the getattr there.

    @app.post("/exec/{name}")
    async def _exec_call(name: str, payload: dict,
                         _: str = Depends(verify_internal_secret)):
        fn = _EXEC_HANDLERS.get(name)
        if fn is None:
            raise HTTPException(status_code=404,
                                detail=f"unknown execution function: {name}")
        args = payload.get("args") or []
        kwargs = payload.get("kwargs") or {}
        try:
            result = await fn(*args, **kwargs)
        except Exception as e:  # loud-ok: re-shaped into a typed 500 the client re-raises (F18)
            # F18 (7/2 review): without this, a REAL execution-side failure (an
            # Alpaca rejection inside trigger_orb_entry, a DB error) became a
            # bare FastAPI 500 that the client collapsed into ExecutionUnreachable
            # — "couldn't reach" and "ran and failed" are different operator
            # responses (module invariant, execution_client docstring). The
            # marker lets the client re-raise the ORIGINAL type+message as
            # ExecutionCallFailed, matching in-process propagation semantics.
            logger.exception(f"execution call {name!r} raised")
            raise HTTPException(status_code=500, detail={
                "execution_error": True,
                "error_type": type(e).__name__,
                "error_message": str(e)[:2000],
            })
        return {"result": result}

    @app.post("/data/bars")
    async def _research_bars(payload: dict,
                             _: str = Depends(verify_internal_secret)):
        """READ-ONLY historical bars for research scripts (2026-11-15). Same
        internal-secret gate as /exec/*; the body reads market data only
        (execution_client._research_bars_inprocess -> broker/research_bars.py).
        Contract: docs/architecture/dual_account.md §Research market data.
        Refused 09:20-10:05 ET on weekdays (the ORB entry window plus a 5-minute
        lead, where live entries share the Alpaca data rate limit) — 429
        `orb_window`, which the helper does NOT retry."""
        if research_blocked_now():
            raise HTTPException(status_code=429, detail={
                "code": "orb_window",
                "message": "research data is refused 09:20-10:05 ET on weekdays (ORB entries); run it again after 10:05 ET"})
        try:
            # Already-encoded JSON bytes (built on the research thread): handed
            # back as-is so a large answer is never encoded on this event loop.
            body = await _ec._research_bars_inprocess(payload)
        except _ec.ResearchBarsRequestError as e:
            raise HTTPException(status_code=e.status,
                                detail={"code": e.code, "message": e.message})
        return Response(content=body, media_type="application/json")

    logger.info(
        f"Execution routes registered: {len(_EXEC_HANDLERS)} /exec/* endpoints")
