"""#677 — the TWELVE Friday 2026-09-18 jobs the first recovery never considered.

⚠ THIS EXISTS BECAUSE THE FIRST RECOVERY'S POPULATION WAS HAND-DERIVED. `_672_rerun_missed_2026_09_18.py`
ran 14 jobs and documented 7 deliberate exclusions (they Telegram the operator, or are weekend-guarded,
or self-correct). That accounting was honest as far as it went — but it was built from a hand-listed
set of "21 missed jobs", and the real window held more.

DERIVED, not listed, on 2026-09-20: every `add_job` in scheduler.py with a FIXED ET hour inside the
stall (nightly_data_pull ran 17:00 -> 00:16) that fires on a Friday = 28 jobs. Exactly ONE
(evening_position_backstop) has a 2026-09-18 `mi_job_runs` row. Subtract the 14 recovered and the
documented exclusions and TWELVE jobs were never considered at all — including `friday_watchlist`,
which is Friday-ONLY and therefore cannot self-heal until 2026-09-25.
[[derive-the-population-never-hand-list-it]]

SENDS ARE CAPTURED, NOT FIRED. Re-running these on a Sunday would push Friday-dated alerts at the
operator two days late — the same reason the first script excluded its Telegram jobs. So
`send_telegram_message` and `notify_owner` are stubbed to RECORD what would have gone out. The data
is recovered; the messages are shown to him and he decides which, if any, to deliver. `friday_watchlist`
is the one whose Telegram IS its product, so its captured body is printed in full.

Everything else is inherited from the 09-19 runner unchanged: the sys.modules date pin across every
`et_today` binding with a hard assert, a row-count snapshot of every mi_* table, an mi_live_trades
fingerprint (THE LINE — this must not move), and a 600 s bound per job.

Run: docker cp into apollo-market, then `docker exec apollo-market python <path>`.
"""
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

JOBS = [
    # the twelve never considered by the first pass, in scheduled order
    ("htf_management_shadow",        "_htf_management_shadow_job"),
    ("chart_axis_shadow",            "_chart_axis_shadow_job"),
    ("drift_check",                  "_post_drift_check_job"),
    ("theme_axis_bounded_sweep",     "_theme_axis_bounded_sweep_job"),
    ("analyst_estimates_snapshot",   "_analyst_estimates_snapshot_job"),
    ("sustain_reject_replay",        "_sustain_reject_replay_job"),
    ("gap_near_miss_replay",         "_gap_near_miss_replay_job"),
    ("lowcap_lane_replay",           "_lowcap_lane_replay_job"),
    ("judge_named_themes_extract",   "_judge_named_themes_extract_job"),
    ("minute_volume_curves_refresh", "_minute_volume_curves_refresh_job"),
    ("tv_news_shadow",               "_tv_news_shadow_job"),
    ("friday_watchlist",             "_friday_watchlist_job"),
]

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

    async def _cap_kb(text, keyboard=None, *a, **kw):
        CAPTURED.append(("_send_with_keyboard", str(text)))
        return True

    # 🔴 DERIVE the sender set; do NOT hand-list it. The first version of this muzzle patched
    # `send_telegram_message` and `notify_owner` by name and reported "nothing will be sent" —
    # and `friday_watchlist` sent anyway, because it owns a SECOND sender, `_send_with_keyboard`,
    # which POSTs to the Bot API with its own httpx client and never touches either name. The
    # operator's Friday watchlist went to his phone twice on 2026-09-20 behind a banner saying it
    # could not. Same defect as the incident this script exists to recover from: a property
    # asserted over a hand-listed population. [[derive-the-population-never-hand-list-it]]
    SENDERS = {
        "send_telegram_message": _cap_send,
        "notify_owner": _cap_notify,
        "_send_with_keyboard": _cap_kb,
        "send_trade_proposal": _cap_send,
        "edit_telegram_message": _cap_send,
    }
    n = 0
    for mod in list(_sys.modules.values()):
        if mod is None:
            continue
        for name, stub in SENDERS.items():
            if callable(getattr(mod, name, None)):
                setattr(mod, name, stub); n += 1

    # The real backstop: anything that still reaches api.telegram.org is a sender nobody listed.
    try:
        import httpx as _httpx
        _real_post = _httpx.AsyncClient.post

        async def _guard_post(self, url, *a, **kw):
            if "api.telegram.org" in str(url):
                CAPTURED.append(("UNLISTED-SENDER httpx", str(kw.get("json", {}))[:400]))
                raise RuntimeError("refusing to send: an unlisted Telegram sender was reached")
            return await _real_post(self, url, *a, **kw)

        _httpx.AsyncClient.post = _guard_post
        n += 1
    except Exception:
        pass
    return n


async def snapshot(conn):
    tabs = [r["table_name"] for r in await conn.fetch(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name LIKE 'mi\\_%' ORDER BY 1")]
    out = {}
    for t in tabs:
        try:
            out[t] = await conn.fetchval(f'SELECT count(*) FROM "{t}"')
        except Exception:
            out[t] = None
    return out


async def trade_fingerprint(conn):
    return await conn.fetchval(
        "SELECT md5(string_agg(id::text||coalesce(status,'')||coalesce(stop_order_id,''), '|' "
        "ORDER BY id)) FROM mi_live_trades")


async def main():
    n = pin_the_clock()
    assert_pinned()
    m = muzzle()
    print(f"clock pinned to {TARGET} across {n} binding(s); last_trading_day()={_SD.last_trading_day()}")
    print(f"outbound messages MUZZLED across {m} binding(s) — nothing will be sent")
    pool = await get_pool()
    async with pool.acquire() as conn:
        before, fp_before = await snapshot(conn), await trade_fingerprint(conn)
    print(f"snapshot: {len(before)} mi_* tables; live-trade fingerprint {fp_before}")

    results = []
    for jid, fn in JOBS:
        f = getattr(sch, fn, None)
        if f is None:
            results.append((jid, "NO SUCH FN")); print(f"  {jid:30s} NO SUCH FN"); continue
        try:
            r = await asyncio.wait_for(f(), timeout=600)
            results.append((jid, f"ok ({r})")); print(f"  {jid:30s} ok -> {r}")
        except asyncio.TimeoutError:
            results.append((jid, "TIMEOUT 600s")); print(f"  {jid:30s} TIMEOUT at 600s")
        except Exception as e:
            results.append((jid, f"ERR {type(e).__name__}: {e}"))
            print(f"  {jid:30s} ERROR {type(e).__name__}: {str(e)[:120]}")

    async with pool.acquire() as conn:
        after, fp_after = await snapshot(conn), await trade_fingerprint(conn)

    print("\n=== ROW-COUNT DELTAS ===")
    seen = False
    for t in sorted(after):
        b, a = before.get(t), after.get(t)
        if b is not None and a is not None and a != b:
            seen = True; print(f"  {t:44s} {b:>7} -> {a:>7}  ({a - b:+d})")
    if not seen:
        print("  (no row-count change in any mi_* table)")

    print("\n=== LIVE TRADE STATE ===")
    print("  UNCHANGED" if fp_before == fp_after else f"  CHANGED {fp_before} -> {fp_after}")

    print(f"\n=== MESSAGES CAPTURED (NOT SENT): {len(CAPTURED)} ===")
    for who, text in CAPTURED:
        flat = " ".join(text.split())
        print(f"  [{who}] {flat[:160]}")
    fw = [t for w, t in CAPTURED if "watchlist" in t.lower() or "Watchlist" in t]
    if fw:
        print("\n=== friday_watchlist BODY IN FULL (its Telegram IS its product) ===")
        print(fw[0][:3000])

    print("\n=== PER-JOB ===")
    for j, r in results:
        print(f"  {j:30s} {r}")


if __name__ == "__main__":
    asyncio.run(main())
