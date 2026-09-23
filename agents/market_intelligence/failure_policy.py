"""#259 — failure POLICY as a decorator, not a per-except-block re-decision.

The codebase has ~492 `except Exception` sites and exactly TWO intended
policies, which until now lived in comments and memory and were re-decided
(sometimes wrongly — gdrive backup, #173 theme-shadow, FLNC) at every new
block:

- ADVISORY / telemetry paths: an exception must never break the caller.
  Catch, log, optionally audit, return a default.  → @advisory_fail_open
- TRADE-STATE paths: every failure must surface (Telegram + audit row;
  memory feedback_no_silent_trading_failures) and propagate.
  → @trade_state_fail_loud

Declared > re-decided: a decorated function states its policy in one
greppable line, and an auditor can list every advisory path with one search.

Migration is OPPORTUNISTIC (task #259): required for NEW functions whose
whole body is one policy; existing code converts as touched. Do NOT wrap:
- functions whose except block does real work (remediation, fallbacks,
  per-exception branching) — the decorator is for policy-only blocks;
- entry_pipeline terminal failures — its humanize()/Telegram contract is
  richer than the generic loud-path message;
- scheduler jobs already inside audit_wrap (double-reporting).
"""
from __future__ import annotations

import functools
import inspect
import logging

logger = logging.getLogger(__name__)


def advisory_fail_open(default=None, *, audit_event: str | None = None,
                       label: str | None = None):
    """Decorator for ADVISORY/telemetry async functions: on any exception,
    log a warning, optionally write an `audit_event` row, and return
    `default` (called first if callable, so mutable defaults stay fresh).

    Async-only by design — every advisory path in this codebase is async;
    a sync function fails loudly at decoration time, not silently at runtime.
    """
    def deco(fn):
        if not inspect.iscoroutinefunction(fn):
            raise TypeError(
                f"advisory_fail_open wraps async functions only (got {fn!r})")
        name = label or fn.__qualname__

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except Exception as e:  # noqa: BLE001 — the policy IS catch-all
                logger.warning(
                    f"{name} failed (advisory fail-open): {e}", exc_info=True)
                if audit_event:
                    try:
                        from agents.market_intelligence.db import log_audit_event
                        await log_audit_event(
                            audit_event, f"{name}: {type(e).__name__}: {e}")
                    except Exception:
                        pass  # audit layer may share the original outage
                return default() if callable(default) else default
        return wrapper
    return deco


def trade_state_fail_loud(*, audit_event: str = "trade_state_failure",
                          label: str | None = None, reraise: bool = True):
    """Decorator for TRADE-STATE async functions: on any exception, log at
    ERROR with traceback, write an audit row, Telegram the operator (#121
    HTML surface — exception text is escaped), then RE-RAISE (default) so
    the caller's failure handling still runs. `reraise=False` only for
    fire-and-forget call sites that have nothing above them to handle it —
    the failure is still loud, just not propagated."""
    def deco(fn):
        if not inspect.iscoroutinefunction(fn):
            raise TypeError(
                f"trade_state_fail_loud wraps async functions only (got {fn!r})")
        name = label or fn.__qualname__

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except Exception as e:  # noqa: BLE001 — the policy IS catch-all
                logger.error(f"{name} FAILED (trade-state): {e}", exc_info=True)
                try:
                    from agents.market_intelligence.db import log_audit_event
                    await log_audit_event(
                        audit_event, f"{name}: {type(e).__name__}: {e}")
                except Exception:
                    pass
                try:
                    from agents.market_intelligence.briefing import send_telegram_message
                    from shared.telegram_format import b, esc
                    await send_telegram_message(
                        f"🔴 {b(name)} failed: {esc(f'{type(e).__name__}: {e}')}",
                        parse_mode="HTML")
                except Exception:
                    pass  # Telegram down must not mask the original error
                if reraise:
                    raise
                return None
        return wrapper
    return deco
