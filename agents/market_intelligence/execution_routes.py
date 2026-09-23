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

from fastapi import Depends, HTTPException

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


def register_execution_routes(app) -> None:
    """Add POST /exec/{name} to `app`. Call only when runs_execution_jobs()."""
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

    logger.info(
        f"Execution routes registered: {len(_EXEC_HANDLERS)} /exec/* endpoints")
