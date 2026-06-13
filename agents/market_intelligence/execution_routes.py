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

# Wire name → in-process implementation. Must mirror execution_client._CROSS_FNS
# exactly (asserted at registration).
_EXEC_HANDLERS = {
    "get_account": _ec._get_account_inprocess,
    "get_position": _ec._get_position_inprocess,
    "get_all_positions": _ec._get_all_positions_inprocess,
    "get_open_orders": _ec._get_open_orders_inprocess,
    "get_first_bar": _ec._get_first_bar_inprocess,
    "get_stream_status": _ec._get_stream_status_inprocess,
    "trigger_orb_entry": _ec._trigger_orb_entry_inprocess,
    "subscribe_orb_candidate": _ec._subscribe_orb_candidate_inprocess,
    "reset_bar_stream_daily_state": _ec._reset_bar_stream_daily_state_inprocess,
    "record_skipped_trade": _ec._record_skipped_trade_inprocess,
    "submit_9m_day2_trade": _ec._submit_9m_day2_trade_inprocess,
    "execute_partial_exit": _ec._execute_partial_exit_inprocess,
    "sync_positions": _ec._sync_positions_inprocess,
    "sync_positions_for_mode": _ec._sync_positions_for_mode_inprocess,
    "place_timestop_sell": _ec._place_timestop_sell_inprocess,
}


def register_execution_routes(app) -> None:
    """Add POST /exec/{name} to `app`. Call only when runs_execution_jobs()."""
    # The handler map and the client's cross list must match exactly, or a
    # client call 404s (or an exposed route has no client). Fail loud at boot.
    missing = _ec._CROSS_FNS - set(_EXEC_HANDLERS)
    extra = set(_EXEC_HANDLERS) - _ec._CROSS_FNS
    if missing or extra:
        raise RuntimeError(
            f"execution route/handler mismatch vs execution_client._CROSS_FNS: "
            f"missing={sorted(missing)} extra={sorted(extra)}. Refusing to boot."
        )

    @app.post("/exec/{name}")
    async def _exec_call(name: str, payload: dict,
                         _: str = Depends(verify_internal_secret)):
        fn = _EXEC_HANDLERS.get(name)
        if fn is None:
            raise HTTPException(status_code=404,
                                detail=f"unknown execution function: {name}")
        args = payload.get("args") or []
        kwargs = payload.get("kwargs") or {}
        result = await fn(*args, **kwargs)
        return {"result": result}

    logger.info(
        f"Execution routes registered: {len(_EXEC_HANDLERS)} /exec/* endpoints")
