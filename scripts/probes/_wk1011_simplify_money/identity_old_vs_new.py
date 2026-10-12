"""Identity proof for the two money-path dedups of the 2026-10-11 simplify pass (area: MONEY PATH).

Both edits claim "same behaviour, fewer lines"; this runs the OLD code (`git show <base>:<file>`, loaded
as a separate module) and the NEW code (the working tree) through the SAME scenario matrix and demands the
full transcript of every run be equal. $0, offline, no DB, no broker, no Telegram (every outward call is a
recorder). Run from the repo root:

    python3 scripts/probes/_wk1011_simplify_money/identity_old_vs_new.py > scripts/probes/_wk1011_simplify_money/identity_old_vs_new.out

  F5  order_manager.execute_depth_open_sale  - `words = _DEPTH_SALE_WORDS[vehicle]` (was a second
      `depth_sale_vehicle` call) and ONE `_place(...)` call (was two branches with identical arguments).
      Matrix: row account_mode {paper, live, None, '', 'weird'} x signal_type {None, magna53, smallcap} x
      sale order raises {no, yes} x row state {normal, not-filled, no-mark, stale-mark, resting-OCO-third,
      zero-shares, not-depth-rule} x process mode {paper, live} (the fallback for a NULL row mode).
      Transcript = return value, ordered broker/DB events, every INSERT/UPDATE, audit rows, pages,
      the order helper that was called and its arguments (client order id's epoch-ms suffix normalised).
  F7  entry_pipeline.submit_trade_entry / _skip - the page tag is computed ONCE (`_tag`) and used by the
      skip page and the CAP+1 page (was the same `strategy_mode_prefix(...)` expression twice).
      Matrix: registry {ok, dedup-lookup raises then recovers, always raises, unregistered} x phase
      {live, paper} x process mode {paper, live} x skip site {open-position guard, shadow phase, paper
      strategy on a live account, CAP, other safeguard block, no ORB bar} x aggregate_skips x
      page_cap_plus_one x catalyst {game_changer, strong} x skip-row INSERT raises x
      get_strategy_account_mode raises. Transcript = return value, every Telegram POST (chat + text),
      audit rows, every DB write.

The harness must also be able to FAIL: two deliberate mutants of the NEW code (the branch swapped; the
lookup-failed arm of the tag dropped) are run through the same matrix and each MUST be reported as
different, or this script exits 1. Prints `IDENTITY PASS` only when old == new on every run and both
mutants were caught.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import itertools
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from _pytest.monkeypatch import MonkeyPatch                                    # noqa: E402

OM_REL = "agents/market_intelligence/broker/order_manager.py"
EP_REL = "agents/market_intelligence/broker/entry_pipeline.py"
_MS = re.compile(r"_\d{13}\b")


def _norm(obj) -> str:
    """Stable text of a transcript: JSON with default=str, client-order-id epoch-ms suffix blanked."""
    return _MS.sub("_<ms>", json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False))


def _load(src: str, name: str):
    tmp = Path(tempfile.mkdtemp(prefix="wk1011_")) / f"{name}.py"
    tmp.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, tmp)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _git_show(base: str, rel: str) -> str:
    return subprocess.run(["git", "show", f"{base}:{rel}"], cwd=REPO, check=True,
                          capture_output=True, text=True).stdout


# ══════════════════════════════════════════════════════════════════════════════════════════
# F5 - execute_depth_open_sale
# ══════════════════════════════════════════════════════════════════════════════════════════

def _sale_matrix():
    for mode, sig, raises, state, proc in itertools.product(
            ["paper", "live", None, "", "weird"],
            [None, "magna53", "magna53_smallcap"],
            [False, True],
            ["normal", "not_filled", "no_mark", "stale_mark", "oco_third", "zero_shares", "not_depth"],
            ["paper", "live"]):
        yield dict(mode=mode, sig=sig, raises=raises, state=state, proc=proc)


async def _run_sale(om_variant, sc) -> dict:
    from tests import test_depth_exit_rule as tdr
    tdr.om = om_variant                      # `_sale_wire` patches whatever module `om` names
    mp = MonkeyPatch()
    try:
        fields = dict(account_mode=sc["mode"], signal_type=sc["sig"], remaining_shares=6,
                      stop_price=tdr.DEPTH_STOP, status="filled", depth_sell_pending_on=tdr.TODAY)
        rule = "depth"
        kw = {}
        st = sc["state"]
        if st == "not_filled":
            fields["status"] = "open"
        elif st == "no_mark":
            fields["depth_sell_pending_on"] = None
        elif st == "stale_mark":
            fields["depth_sell_pending_on"] = date(2026, 10, 2)
        elif st == "zero_shares":
            fields["remaining_shares"] = 0
        elif st == "not_depth":
            rule = None
        elif st == "oco_third":
            kw = dict(
                open_orders=[
                    {"id": "stop-1", "side": "sell", "type": "stop", "qty": 4, "filled_qty": 0,
                     "status": "new", "order_class": "simple"},
                    {"id": "oco-1", "side": "sell", "type": "limit", "qty": 2, "filled_qty": 0,
                     "status": "new", "order_class": "oco"}],
                pending_rows=[{"alpaca_order_id": "oco-1", "purpose": "partial_exit", "qty": 2}])
        row = tdr._row(rule, **fields)
        h = tdr._sale_wire(mp, row=row,
                           opg_raises=Exception("rejected: insufficient qty") if sc["raises"] else None,
                           **kw)
        mp.setattr(om_variant, "current_account_mode", lambda: sc["proc"])
        try:
            out = await om_variant.execute_depth_open_sale(501)
        except Exception as e:                                           # noqa: BLE001
            out = f"RAISED {type(e).__name__}: {e}"
        return {
            "out": out, "events": h["events"], "executed": h["executed"], "sent": h["sent"],
            "audit": [(c.args, c.kwargs) for c in h["audit"].await_args_list],
            "opg": h["opg_calls"], "day": h["day_calls"],
            "cancel": [(c.args, c.kwargs) for c in h["cancel"].await_args_list],
            "place_stop": [(c.args, c.kwargs) for c in h["place_stop"].await_args_list],
            "pos_calls": h["pos"].await_count, "orders_calls": h["orders"].await_count,
        }
    finally:
        mp.undo()


async def _sale_transcripts(om_variant) -> list[str]:
    return [_norm(await _run_sale(om_variant, sc)) for sc in _sale_matrix()]


def _sale_coverage(transcripts: list[str]) -> Counter:
    """What the matrix actually exercised - so 'identical' cannot be vacuous."""
    c = Counter()
    for t in transcripts:
        d = json.loads(t)
        c["runs"] += 1
        c["sale_accepted(True)"] += d["out"] is True
        c["sale_not_placed(False)"] += d["out"] is False
        c["opg_order_sent"] += bool(d["opg"])
        c["day_market_order_sent"] += bool(d["day"])
        c["rejected_audit_rows"] += sum(1 for a in d["audit"] if a[0][0] == "full_exit_rejected")
        c["placed_audit_rows"] += sum(1 for a in d["audit"] if a[0][0] == "depth_open_sale_placed")
        c["stale_mark_rows"] += sum(1 for a in d["audit"] if a[0][0] == "depth_sale_mark_stale")
        c["pages_naming_opening_auction"] += any("pening" in m and "uction" in m for m in d["sent"])
        c["pages_saying_at_the_open"] += any("at the open" in m for m in d["sent"])
    return c


# ══════════════════════════════════════════════════════════════════════════════════════════
# F7 - entry_pipeline._skip tag
# ══════════════════════════════════════════════════════════════════════════════════════════

def _funnel_matrix():
    for reg, phase, proc, site, agg, cap, cq, ins, mraise in itertools.product(
            ["ok", "dedup_raises_then_ok", "always_raises", "unregistered"],
            ["live", "paper"],
            ["paper", "live"],
            ["early", "shadow", "paper_on_live", "cap", "other_block", "no_bar"],
            [False, True],
            [False, True],
            ["game_changer", "strong"],
            [False, True],
            [False, True]):
        yield dict(reg=reg, phase=phase, proc=proc, site=site, agg=agg, cap=cap, cq=cq, ins=ins,
                   mraise=mraise)


async def _run_funnel(ep_variant, sc) -> dict:
    from types import SimpleNamespace
    import agents.market_intelligence.strategies.registry as registry
    from agents.market_intelligence import briefing, constants
    from agents.market_intelligence import exposure_family
    from agents.market_intelligence.broker import live_tracker as lt
    from agents.market_intelligence.broker.skip_reasons import BLOCK_MAX_POSITIONS
    from tests.conftest import make_mock_pool
    from tests.test_699_paper_chat_routing import MAIN, PAPER, _Router

    mp = MonkeyPatch()
    try:
        mp.setenv("TELEGRAM_BOT_TOKEN", "tok")
        mp.setenv("TELEGRAM_ALLOWED_USER_IDS", str(MAIN))
        mp.setenv("TELEGRAM_PAPER_CHAT_ID", str(PAPER))
        router = _Router()
        pool, conn = make_mock_pool()
        site = sc["site"]
        phase = {"shadow": "shadow"}.get(site, sc["phase"])
        # The strategy row's phase picks its book; "paper_on_live" = a paper strategy while the
        # process runs live.
        if site == "paper_on_live":
            phase, proc = "paper", "live"
        else:
            proc = sc["proc"]
        open_since = date(2026, 10, 5) if site == "early" else None
        conn.fetchval = AsyncMock(side_effect=[False, open_since])
        executed: list = []

        async def _exec(*a, **k):
            executed.append(a)
            if sc["ins"] and "INSERT INTO mi_live_trades" in a[0]:
                raise RuntimeError("skip-row insert boom")
            return "INSERT 0 1"

        conn.execute = _exec
        audit = AsyncMock()
        mp.setattr(ep_variant, "get_pool", AsyncMock(return_value=pool))
        mp.setattr(lt, "get_pool", AsyncMock(return_value=pool))
        mp.setattr(ep_variant, "log_audit_event", audit)
        mp.setattr(briefing, "log_audit_event", AsyncMock())
        mp.setattr(constants, "current_account_mode", lambda: proc)
        mp.setattr(ep_variant, "current_account_mode", lambda: proc)
        strat = SimpleNamespace(enabled=True, phase=phase, live_real_enabled=True,
                                position_size_multiplier=1.0, strategy_id="magna53")
        reg = sc["reg"]
        if reg == "ok":
            gs = AsyncMock(return_value=strat)
        elif reg == "dedup_raises_then_ok":
            gs = AsyncMock(side_effect=[RuntimeError("registry down"), strat])
        elif reg == "always_raises":
            gs = AsyncMock(side_effect=RuntimeError("registry down"))
        else:
            gs = AsyncMock(return_value=None)
        mp.setattr(registry, "get_strategy", gs)
        if sc["mraise"]:
            def _boom(_s):
                raise RuntimeError("mode resolve boom")
            mp.setattr(ep_variant, "get_strategy_account_mode", _boom)
        if site == "cap":
            sg = AsyncMock(return_value=(False, f"{BLOCK_MAX_POSITIONS}: 5/5 open", 1.0))
        elif site == "other_block":
            sg = AsyncMock(return_value=(False, "block:daily_loss_limit", 1.0))
        else:
            sg = AsyncMock(return_value=(True, None, 1.0))
        mp.setattr(lt, "_check_safeguards", sg)
        mp.setattr(exposure_family, "shadow_check_and_emit", AsyncMock())
        mp.setattr(ep_variant, "fetch_orb_bar_with_retry", AsyncMock(return_value=None))
        mp.setattr(briefing.httpx, "AsyncClient", router)

        async def _spec_builder(*_a, **_k):
            return ({}, "spec builder must not be reached")

        try:
            out = await ep_variant.submit_trade_entry(
                alert_context={"ticker": "OPN", "ep_score": 80, "catalyst_quality": sc["cq"],
                               "gap_pct": 12.0},
                spec_builder=_spec_builder, regime_record=None, strategy_label="ORB",
                signal_type="magna53", today=date(2026, 10, 12), atr_14=1.0,
                aggregate_skips=sc["agg"], page_cap_plus_one=sc["cap"])
        except Exception as e:                                           # noqa: BLE001
            out = f"RAISED {type(e).__name__}: {e}"
        return {"out": out, "posts": router.posts,
                "audit": [(c.args, c.kwargs) for c in audit.await_args_list],
                "executed": executed}
    finally:
        mp.undo()


async def _funnel_transcripts(ep_variant) -> list[str]:
    return [_norm(await _run_funnel(ep_variant, sc)) for sc in _funnel_matrix()]


def _funnel_coverage(transcripts: list[str]) -> Counter:
    c = Counter()
    for t in transcripts:
        d = json.loads(t)
        c["runs"] += 1
        texts = [p["text"] for p in d["posts"]]
        c["skip_pages"] += sum("skipped" in x for x in texts)
        c["cap_plus_one_pages"] += sum("CAP+1 CANDIDATE" in x for x in texts)
        c["pages_MODE_UNKNOWN"] += sum("MODE UNKNOWN" in x for x in texts)
        c["pages_PAPER_tag"] += sum(x.lstrip("*_`~ ").startswith("📄 PAPER") for x in texts)
        c["pages_LIVE_tag"] += sum("💰 LIVE-$" in x for x in texts)
        c["pages_to_paper_chat"] += sum(p["chat_id"] != 42 for p in d["posts"])
        c["pages_to_main_chat"] += sum(p["chat_id"] == 42 for p in d["posts"])
        c["skip_row_write_errors"] += sum(1 for a in d["audit"] if a[0][0] == "skip_row_write_error")
        c["strategy_mode_resolve_error_rows"] += sum(
            1 for a in d["audit"] if a[0][0] == "strategy_mode_resolve_error")
        c["raised_out_of_funnel"] += isinstance(d["out"], str)
    return c


# ══════════════════════════════════════════════════════════════════════════════════════════

def _diff(a: list[str], b: list[str]) -> int:
    assert len(a) == len(b)
    return sum(1 for x, y in zip(a, b) if x != y)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="a584b2c3", help="commit holding the OLD code")
    args = ap.parse_args()

    om_new_src = (REPO / OM_REL).read_text(encoding="utf-8")
    ep_new_src = (REPO / EP_REL).read_text(encoding="utf-8")
    om_old = _load(_git_show(args.base, OM_REL), "om_old")
    om_new = _load(om_new_src, "om_new")
    ep_old = _load(_git_show(args.base, EP_REL), "ep_old")
    ep_new = _load(ep_new_src, "ep_new")

    # Mutants of the NEW code: the harness must be able to tell they differ.
    swap = "if vehicle == DEPTH_SALE_VEHICLE_OPG\n                      else alpaca.place_market_sell"
    assert om_new_src.count(swap) == 1, "F5 mutation anchor not found (new code changed shape?)"
    om_mut = _load(om_new_src.replace(
        swap, "if vehicle != DEPTH_SALE_VEHICLE_OPG\n                      else alpaca.place_market_sell"),
        "om_mut")
    arm = "_tag = strategy_mode_prefix(None if _skip_mode_lookup_failed else _skip_mode)"
    assert ep_new_src.count(arm) == 1, "F7 mutation anchor not found (new code changed shape?)"
    ep_mut = _load(ep_new_src.replace(arm, "_tag = strategy_mode_prefix(_skip_mode)"), "ep_mut")

    loop = asyncio.new_event_loop()
    ok = True

    t_old = loop.run_until_complete(_sale_transcripts(om_old))
    t_new = loop.run_until_complete(_sale_transcripts(om_new))
    t_mut = loop.run_until_complete(_sale_transcripts(om_mut))
    d_new, d_mut = _diff(t_old, t_new), _diff(t_old, t_mut)
    print(f"F5 execute_depth_open_sale: {len(t_old)} runs  old-vs-new differences={d_new}  "
          f"mutant(branch swapped)-vs-old differences={d_mut} (must be > 0)")
    print("   coverage (old): " + ", ".join(f"{k}={v}" for k, v in sorted(_sale_coverage(t_old).items())))
    ok &= d_new == 0 and d_mut > 0

    f_old = loop.run_until_complete(_funnel_transcripts(ep_old))
    f_new = loop.run_until_complete(_funnel_transcripts(ep_new))
    f_mut = loop.run_until_complete(_funnel_transcripts(ep_mut))
    e_new, e_mut = _diff(f_old, f_new), _diff(f_old, f_mut)
    print(f"F7 entry_pipeline._skip tag: {len(f_old)} runs  old-vs-new differences={e_new}  "
          f"mutant(lookup-failed arm dropped)-vs-old differences={e_mut} (must be > 0)")
    print("   coverage (old): " + ", ".join(f"{k}={v}" for k, v in sorted(_funnel_coverage(f_old).items())))
    ok &= e_new == 0 and e_mut > 0

    loop.close()
    print("IDENTITY PASS" if ok else "IDENTITY FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
