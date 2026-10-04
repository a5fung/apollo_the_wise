"""#687 CONVERGENCE TEST — the broker-facing paths match MAIN except a NAMED allow-list.

WHY (cut-back round, 2026-10-02). Three review rounds added defence-in-depth to SHARED broker code and
did not converge. The criterion that ended it: a change to these paths may differ from main ONLY where
a fix or an operator ruling says so, each difference named and pinned to its exact value.

HISTORY. Until 2026-10-03 the baseline was the pre-#687 code (97b08d51) and the allow-list named the
#687 fixes (a)-(f), the 61a6c479 sync hunk and the rulings (1)-(3), (ii), (iv) — 17 entries; that
version is in git (`git log -p -- tests/test_687_toggle_off_convergence.py`). #687 merged and deployed
2026-10-03 (a88a8043), so main IS that behaviour now: the baseline was RE-PINNED to origin/main
8e1329f0 and those entries left the list (each was now identical to the baseline). The list below
names only what the current change does differently from main.

HOW. `tests/_convergence_687_harness.py` drives 38 fixed scenarios (the 16:45 trail exit with and
without a resting +8R OCO third or a plain resting limit, the 16:45 job itself, a stop raise via
`update_stop`, the position sync with and without a queued sale, stream fill / cancel / expiry events,
the stop-ACK watchdog, the 17:00 coverage slot, the intraday coverage page, the stop refresh, a stop
that cannot be placed because the price is through it — at the failed-exit restore and, since ruling
(iii), at each of the six other stop-placing sites (s32-s38) — the daily-loss gate, and
`close_position(qty)` at the alpaca-py boundary) and records every broker-client call (method + bound
arguments), every Telegram page, the return value and the fake book's end state. The BASELINE log
was recorded by running the SAME harness on the pinned main commit
(`scripts/probes/_687/capture_toggle_off_baseline.sh`). This test runs it on the current tree and
asserts:

  * a component NOT in the allow-list equals the baseline exactly;
  * an allow-listed component equals its pinned expectation exactly (a stray call inside an allowed
    scenario still fails) AND differs from the baseline (the exception is real, not stale);
  * the two depth-only scenarios stay inert with the toggle OFF (no broker call, no page);
  * the fake book understood every SQL statement (`_unknown_sql` empty).

⚠ The baseline is PINNED to 8e1329f0 (the origin/main this change is built on), not "origin/main":
once a change merges, origin/main contains it and the comparison would be self-against-self. A later
change to these paths that is unrelated will show here as an unlisted difference — re-capture the
baseline (and re-pin) deliberately; never widen the allow-list to absorb it.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests" / "_convergence_687_harness.py"
BASELINE = ROOT / "tests" / "fixtures" / "687_toggle_off_main_baseline.json"
PINNED_BASELINE_SHA = "8e1329f0647872e148d3256090ef8aff60c70943"
COMPONENTS = ("broker_calls", "pages", "result", "raised", "book_after")

# The depth machinery (#687 B), merged with the toggle OFF: compared to the baseline like any other
# scenario AND held inert — no broker call, no page, this exact result.
INERT_WITH_THE_TOGGLE_OFF = {
    "s24_depth_1901_runner_with_no_marked_rows": [],     # the 19:01 runner finds no marked row
    "s25_depth_stamp_with_the_toggle_off": None,         # a new MAGNA53 row is not stamped 'depth'
}

# ── THE ALLOW-LIST. Every exception is tied to its scenario and names the ruling. ──────────────
# broker_calls / pages / result / raised = the exact branch value; book_after = the fields that
# differ from the baseline book (trades) or the whole exit-order list (orders).
ALLOWED = {
    's32_coverage_reconciler_place_through_the_price': {
        'why': "ruling (iii) 2026-10-02 — sell at market at the coverage reconciler (_ensure_stop_coverage's place branch)",
        'broker_calls': [
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "place_stop_order(account_mode='live', client_order_id='apollo_live_magna53_KOD_1', qty=10, side='sell', stop_price=58, ticker='KOD')",
            "get_position(account_mode='live', ticker='KOD')",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "close_position(account_mode='live', qty=10, ticker='KOD')",
        ],
        'pages': [
            '💰 LIVE-$ 🚨 <b>Price already below the stop:</b> KOD\nThe stop at $58.00 could not be placed — the broker refused it because the price is already below it. Selling 10 sh at market now (Order sell-1), as the triggered stop would have.\n<i>Confirms with real P&amp;L on fill.</i>',
        ],
        'result': '🚨 KOD: stop $58.00 is ABOVE market — the price is already through it, so 10 sh are being SOLD AT MARKET (order sell-1), as the triggered stop would have.',
        'book_after': {'orders': [{'exit_reason': 'stop_hit', 'id': 'sell-1', 'purpose': 'full_exit', 'qty': 10, 'status': 'accepted'}]},
    },
    's33_sync_orphan_remediation_through_the_price': {
        'why': "ruling (iii) 2026-10-02 — sell at market at the coverage reconciler (the sync's coverage pass, after its orphan repair failed)",
        'broker_calls': [
            "get_all_positions(account_mode='live', raise_on_error=False)",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "place_stop_order(account_mode='live', client_order_id='apollo_live_magna53_KOD_1', qty=10, side='sell', stop_price=58, ticker='KOD')",
            "place_stop_order(account_mode='live', client_order_id='apollo_live_magna53_KOD_2', qty=10, side='sell', stop_price=58, ticker='KOD')",
            "place_stop_order(account_mode='live', client_order_id='apollo_live_magna53_KOD_3', qty=10, side='sell', stop_price=58, ticker='KOD')",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "place_stop_order(account_mode='live', client_order_id='apollo_live_magna53_KOD_4', qty=10, side='sell', stop_price=58, ticker='KOD')",
            "get_position(account_mode='live', ticker='KOD')",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "close_position(account_mode='live', qty=10, ticker='KOD')",
        ],
        'pages': [
            '💰 LIVE-$ 🚨 <b>Price already below the stop:</b> KOD\nThe stop at $58.00 could not be placed — the broker refused it because the price is already below it. Selling 10 sh at market now (Order sell-1), as the triggered stop would have.\n<i>Confirms with real P&amp;L on fill.</i>',
            '💰 LIVE-$ ⚠️ *Position Sync Discrepancies (live):*\n  • ⚠️ Failed to remediate orphaned stop for KOD after 3 attempts: {"code":42210000,"message":"stop price must be less than current price"}\n  • 🚨 KOD: stop $58.00 is ABOVE market — the price is already through it, so 10 sh are being SOLD AT MARKET (order sell-1), as the triggered stop would have.',
        ],
        'result': ['⚠️ Failed to remediate orphaned stop for KOD after 3 attempts: {"code":42210000,"message":"stop price must be less than current price"}', '🚨 KOD: stop $58.00 is ABOVE market — the price is already through it, so 10 sh are being SOLD AT MARKET (order sell-1), as the triggered stop would have.'],
        'book_after': {'orders': [{'exit_reason': 'stop_hit', 'id': 'sell-1', 'purpose': 'full_exit', 'qty': 10, 'status': 'accepted'}]},
    },
    's34_update_stop_raise_through_the_price': {
        'why': 'ruling (iii) 2026-10-02 — sell at market at update_stop (a trail raise refused: the trail would have triggered)',
        'broker_calls': [
            "get_order(account_mode='live', order_id='stop-1', timeout=None)",
            "cancel_order(account_mode='live', order_id='stop-1')",
            "place_stop_order(account_mode='live', client_order_id='apollo_live_magna53_KOD_1', qty=10, side='sell', stop_price=61.5, ticker='KOD')",
            "place_stop_order(account_mode='live', client_order_id='apollo_live_magna53_KOD_2', qty=10, side='sell', stop_price=61.5, ticker='KOD')",
            "get_position(account_mode='live', ticker='KOD')",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "close_position(account_mode='live', qty=10, ticker='KOD')",
        ],
        'pages': [
            '💰 LIVE-$ 🚨 <b>Price already below the stop:</b> KOD\nThe stop at $61.50 could not be placed — the broker refused it because the price is already below it. Selling 10 sh at market now (Order sell-1), as the triggered stop would have.\nIt was a stop raise (from $58.00) — the trail would have triggered at the new level.\n<i>Confirms with real P&amp;L on fill.</i>',
        ],
        'result': 'STOP_SOLD_AT_MARKET',
        'book_after': {'orders': [{'exit_reason': 'stop_hit', 'id': 'sell-1', 'purpose': 'full_exit', 'qty': 10, 'status': 'accepted'}]},
    },
    's35_refresh_replace_through_the_price': {
        'why': "ruling (iii) 2026-10-02 — sell at market at update_stop (via the stop refresh's re-place; no 'No stop' page after the sale)",
        'broker_calls': [
            "get_order(account_mode='live', order_id='stop-1', timeout=None)",
            "get_order(account_mode='live', order_id='stop-1', timeout=None)",
            "cancel_order(account_mode='live', order_id='stop-1')",
            "place_stop_order(account_mode='live', client_order_id='apollo_live_magna53_KOD_1', qty=10, side='sell', stop_price=58, ticker='KOD')",
            "place_stop_order(account_mode='live', client_order_id='apollo_live_magna53_KOD_2', qty=10, side='sell', stop_price=58, ticker='KOD')",
            "get_position(account_mode='live', ticker='KOD')",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "close_position(account_mode='live', qty=10, ticker='KOD')",
        ],
        'pages': [
            '💰 LIVE-$ 🚨 <b>Price already below the stop:</b> KOD\nThe stop at $58.00 could not be placed — the broker refused it because the price is already below it. Selling 10 sh at market now (Order sell-1), as the triggered stop would have.\n<i>Confirms with real P&amp;L on fill.</i>',
        ],
        'book_after': {'orders': [{'exit_reason': 'stop_hit', 'id': 'sell-1', 'purpose': 'full_exit', 'qty': 10, 'status': 'accepted'}]},
    },
    's36_watchdog_fallback_through_the_price': {
        'why': "ruling (iii) 2026-10-02 — sell at market at the stop-ACK watchdog's fallback stop",
        'broker_calls': [
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "place_stop_order(account_mode='live', client_order_id=None, qty=10, side='sell', stop_price=57.5, ticker='KOD')",
            "get_position(account_mode='live', ticker='KOD')",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "close_position(account_mode='live', qty=10, ticker='KOD')",
        ],
        'pages': [
            '💰 LIVE-$ 🚨 <b>Price already below the stop:</b> KOD\nThe stop at $57.50 could not be placed — the broker refused it because the price is already below it. Selling 10 sh at market now (Order sell-1), as the triggered stop would have.\n<i>Confirms with real P&amp;L on fill.</i>',
        ],
        'book_after': {'orders': [{'exit_reason': 'stop_hit', 'id': 'sell-1', 'purpose': 'full_exit', 'qty': 10, 'status': 'accepted'}]},
    },
    's37_stream_partial_exit_cancelled_restore_through_the_price': {
        'why': "ruling (iii) 2026-10-02 — sell at market at the stream's partial-exit restore",
        'broker_calls': [
            "get_order(account_mode='live', order_id='stop-r', timeout=5)",
            "cancel_order(account_mode='live', order_id='stop-r')",
            "place_stop_order(account_mode='live', client_order_id=None, qty=10, side='sell', stop_price=58, ticker='KOD')",
            "get_position(account_mode='live', ticker='KOD')",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "close_position(account_mode='live', qty=10, ticker='KOD')",
        ],
        'pages': [
            '💰 LIVE-$ 🚨 <b>Price already below the stop:</b> KOD\nThe stop at $58.00 could not be placed — the broker refused it because the price is already below it. Selling 10 sh at market now (Order sell-1), as the triggered stop would have.\nThe partial sale did not fill (cancelled), and the stop for the remaining shares could not be put back.\n<i>Confirms with real P&amp;L on fill.</i>',
        ],
        'book_after': {'trades': {'401': {'stop_order_id': None}}, 'orders': [{'exit_reason': 'stop_hit', 'id': 'sell-1', 'purpose': 'full_exit', 'qty': 10, 'status': 'accepted'}, {'exit_reason': 'partial_profit', 'id': 'sell-p', 'purpose': 'partial_exit', 'qty': 3, 'status': 'cancelled'}]},
    },
    's38_oco_cancel_unfilled_restore_through_the_price': {
        'why': 'ruling (iii) 2026-10-02 — sell at market at the OCO-cancel handler (its re-protect runs through the coverage reconciler)',
        'broker_calls': [
            "get_order(account_mode='live', order_id='leg-1', timeout=None)",
            "get_position(account_mode='live', ticker='KOD')",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "place_stop_order(account_mode='live', client_order_id='apollo_live_magna53_KOD_1', qty=2, side='sell', stop_price=60, ticker='KOD')",
            "get_position(account_mode='live', ticker='KOD')",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "close_position(account_mode='live', qty=2, ticker='KOD')",
        ],
        'pages': [
            '💰 LIVE-$ 🚨 <b>Price already below the stop:</b> KOD\nThe stop at $60.00 could not be placed — the broker refused it because the price is already below it. Selling 2 sh at market now (Order sell-1), as the triggered stop would have.\n<i>Confirms with real P&amp;L on fill.</i>',
            "💰 LIVE-$ ⚠️ *OCO CANCELLED:* KOD\nThe carve-out third's OCO died unfilled (both legs terminal) — re-protecting from broker truth.\n🚨 KOD: stop $60.00 is ABOVE market — the price is already through it, so 2 sh are being SOLD AT MARKET (order sell-1), as the triggered stop would have.",
        ],
        'book_after': {'orders': [{'exit_reason': None, 'id': 'oco-1', 'purpose': 'partial_exit', 'qty': 2, 'status': 'cancelled'}, {'exit_reason': 'stop_hit', 'id': 'sell-1', 'purpose': 'full_exit', 'qty': 2, 'status': 'accepted'}]},
    },
}


def _call_str(c: dict) -> str:
    return c["method"] + "(" + ", ".join(f"{k}={v!r}" for k, v in sorted(c["args"].items())) + ")"


def _norm(component, value):
    if component == "broker_calls":
        return [_call_str(c) for c in value]
    return value


def _apply_delta(book: dict, delta: dict) -> dict:
    out = copy.deepcopy(book)
    for tid, fields in (delta.get("trades") or {}).items():
        out["trades"].setdefault(tid, {}).update(fields)
    if "orders" in delta:
        out["orders"] = delta["orders"]
    return out


_BASE = json.loads(BASELINE.read_text())
SCENARIOS = sorted(_BASE["scenarios"])


@pytest.fixture(scope="module")
def branch_log(tmp_path_factory):
    out = tmp_path_factory.mktemp("conv687") / "branch.json"
    r = subprocess.run([sys.executable, str(HARNESS), "--out", str(out)], cwd=ROOT,
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-4000:]
    return json.loads(out.read_text())


def test_the_baseline_is_the_pinned_commit_recorded_by_this_harness():
    assert _BASE["baseline_sha"] == PINNED_BASELINE_SHA
    assert _BASE["harness_sha256"] == hashlib.sha256(HARNESS.read_bytes()).hexdigest(), (
        "the harness changed since the baseline was captured — re-run "
        "scripts/probes/_687/capture_toggle_off_baseline.sh")


def test_every_scenario_ran_on_both_trees(branch_log):
    assert set(branch_log) == set(_BASE["scenarios"])
    assert len(SCENARIOS) >= 28


def test_the_allow_list_names_only_real_scenarios_and_says_why():
    for name, entry in ALLOWED.items():
        assert name in _BASE["scenarios"], name
        assert entry.get("why") and set(entry) - {"why"} <= set(COMPONENTS), name
        assert set(entry) - {"why"}, f"{name}: an allow-list entry must name a component"


def test_every_exception_from_main_is_ruling_iii():
    """The change built on this baseline is ONE ruling: #687 (iii), operator 2026-10-02 — ruling
    (3)'s sell-at-market extended to the other stop-placing sites. Nothing else may differ."""
    for name, entry in ALLOWED.items():
        assert entry["why"].startswith("ruling (iii) 2026-10-02 — sell at market at "), name


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_toggle_off_matches_the_baseline_except_the_named_exceptions(branch_log, scenario):
    base, here = _BASE["scenarios"][scenario], branch_log[scenario]
    assert here.get("_unknown_sql") == [], (
        f"{scenario}: the fake book did not understand {here.get('_unknown_sql')}")
    assert "absent" not in base and "absent" not in here, (base.get("absent"), here.get("absent"))
    if scenario in INERT_WITH_THE_TOGGLE_OFF:
        assert here["broker_calls"] == [] and here["pages"] == [], here
        assert (here["raised"] is None
                and here["result"] == INERT_WITH_THE_TOGGLE_OFF[scenario]), here
    allowed = ALLOWED.get(scenario, {})
    for comp in COMPONENTS:
        b, h = _norm(comp, base[comp]), _norm(comp, here[comp])
        if comp in allowed:
            expect = (_apply_delta(base[comp], allowed[comp]) if comp == "book_after"
                      else allowed[comp])
            assert h == expect, (f"{scenario}.{comp} [{allowed['why']}] - not the pinned "
                                 f"exception:\n  here:   {h!r}\n  expect: {expect!r}")
            assert b != expect, (f"{scenario}.{comp}: allow-listed but identical to the "
                                 f"baseline - stale entry")
        else:
            assert h == b, (f"{scenario}.{comp}: UNLISTED difference from the main "
                            f"baseline\n  baseline: {b!r}\n  here:     {h!r}")
