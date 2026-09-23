"""Capture Friday 2026-09-18's watchlist body WITHOUT sending it (#677 follow-up)."""

import asyncio, datetime as _dt, sys

TARGET = _dt.date(2026, 9, 18)

# ── THE DATE PIN, and why it is a sys.modules walk and not one assignment ──────────────
# `et_today()` is defined in shared/dates.py and RE-EXPORTED widely. MEASURED in the running
# container on 2026-09-19: **10 modules hold their own `et_today` binding** — shared.dates,
# collector, rs_engine, regime, theme_engine, ep_detector, outcome_tracker, state_alerts and
# two more. A module that did `from ... import et_today` at import time keeps its OWN
# reference, so patching `collector.et_today` alone reaches ONE of the ten and the other nine
# still return Saturday. The first draft of this script did exactly that and would have
# recorded 09-19 while reporting success.
#
# So: import everything the jobs touch FIRST, then rebind every binding that exists, then
# ASSERT none is left. The assert is the point — a pin that silently half-applies is worse
# than no pin, because the rows look right until someone checks their date.
import agents.market_intelligence.scheduler          # noqa: F401  (pulls the graph in)
import agents.market_intelligence.db                 # noqa: F401
import agents.market_intelligence.theme_engine       # noqa: F401
import agents.market_intelligence.briefing           # noqa: F401
import shared.dates as _SD


def _pinned_today():
    return TARGET


def pin_the_clock() -> int:
    """Rebind et_today everywhere it is held. Returns how many bindings were pinned."""
    _SD.et_today = _pinned_today          # the source, so any LATER `from ... import` is pinned too
    n = 0
    for mod in list(sys.modules.values()):
        if mod is not None and callable(getattr(mod, "et_today", None)):
            setattr(mod, "et_today", _pinned_today)
            n += 1
    return n


def assert_pinned() -> None:
    bad = {}
    for name, mod in list(sys.modules.items()):
        f = getattr(mod, "et_today", None) if mod is not None else None
        if callable(f):
            try:
                v = f()
            except Exception as e:                      # pragma: no cover
                v = f"ERR {e}"
            if v != TARGET:
                bad[name] = v
    if bad:
        raise SystemExit(f"REFUSING TO RUN — {len(bad)} et_today binding(s) still not {TARGET}: {bad}")
    if _SD.last_trading_day() != TARGET:
        raise SystemExit(f"REFUSING TO RUN — last_trading_day() is {_SD.last_trading_day()}, not {TARGET}")
    # operator_today() is deliberately NOT pinned: it is the OPERATOR's clock, not market logic.


from agents.market_intelligence import scheduler as sch
from agents.market_intelligence.db import get_pool


JOBS = [("friday_watchlist", "_friday_watchlist_job")]

# ── CAPTURE EVERY OUTBOUND MESSAGE INSTEAD OF SENDING IT ───────────────────────────────
# Patched on the MODULES that own the senders, before any job runs. Same reasoning as the
# date pin: a caller that did `from ... import send_telegram_message` holds its own binding,
# so patch the source AND every module that already imported it, then report the count.
CAPTURED = []


def muzzle() -> int:
    import sys as _sys

    async def _cap_send(text, *a, **kw):
        CAPTURED.append(("send_telegram_message", str(text)))
        return True

    async def _cap_notify(text, *a, **kw):
        CAPTURED.append(("notify_owner", str(text)))
        return True

    n = 0
    for mod in list(_sys.modules.values()):
        if mod is None:
            continue
        if callable(getattr(mod, "send_telegram_message", None)):
            setattr(mod, "send_telegram_message", _cap_send); n += 1
        if callable(getattr(mod, "notify_owner", None)):
            setattr(mod, "notify_owner", _cap_notify); n += 1
    return n




async def main():
    n = pin_the_clock(); assert_pinned(); m = muzzle()
    # ⚠ THE LEAK: friday_watchlist has a SECOND sender, `_send_with_keyboard`, which POSTs to the
    # Bot API with its own httpx client and never touches `send_telegram_message`. The first muzzle
    # missed it entirely. Patch it too, and RECORD which path the job actually takes.
    import agents.market_intelligence.friday_watchlist as _fw
    async def _cap_kb(text, keyboard):
        CAPTURED.append(("_send_with_keyboard", str(text)))
        return True
    _fw._send_with_keyboard = _cap_kb
    print(f"pinned to {TARGET} across {n}; muzzled {m} send binding(s)")
    from agents.market_intelligence.friday_watchlist import run_friday_watchlist
    try:
        res = await asyncio.wait_for(run_friday_watchlist(window_days=7, persist=False), timeout=600)
        print("RESULT:", res)
    except Exception as e:
        print("JOB ERROR", type(e).__name__, str(e)[:200])
    print(f"\n=== {len(CAPTURED)} MESSAGE(S) CAPTURED, NOTHING SENT ===")
    for who, text in CAPTURED:
        print(f"\n----- via {who}, {len(text)} chars -----")
        print(text[:2600])

if __name__ == "__main__":
    asyncio.run(main())
