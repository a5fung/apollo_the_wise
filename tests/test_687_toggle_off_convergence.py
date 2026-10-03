"""#687 CONVERGENCE TEST — the toggle-OFF path matches the pre-#687 code except a NAMED allow-list.

WHY (cut-back round, 2026-10-02). Three review rounds added defence-in-depth to SHARED broker code and
did not converge. A feature behind an OFF toggle (`magna53_depth_exit`) must change NOTHING for
toggle-OFF trades except the six named fixes to today's close-below exit — #687 (a)-(f) — the cited
sync hunk (61a6c479), the operator's rulings of 2026-10-01 (1)-(3), and his 2026-10-02 ruling (ii). This test is that criterion.

HOW. `tests/_convergence_687_harness.py` drives 29 fixed scenarios (the 16:45 trail exit with and
without a resting +8R OCO third or a plain resting limit, the 16:45 job itself, a stop raise via `update_stop`, the position
sync with and without a queued sale, stream fill / cancel / expiry events, the stop-ACK watchdog,
the 17:00 coverage slot, the intraday coverage page, the stop refresh, a stop that cannot be placed because the price is through
it, the daily-loss gate, and `close_position(qty)` at the alpaca-py boundary) and records every
broker-client call (method + bound arguments), every Telegram page, the return value and the fake
book's end state. The BASELINE log was recorded by running the SAME harness inside a temporary git
worktree of the pinned pre-#687 commit (`scripts/probes/_687/capture_toggle_off_baseline.sh`; the
worktree is removed after the capture). This test runs it on the current tree and asserts:

  * a component NOT in the allow-list equals the baseline exactly;
  * an allow-listed component equals its pinned expectation exactly (a stray call inside an allowed
    scenario still fails) AND differs from the baseline (the exception is real, not stale);
  * the two depth-only scenarios are absent from the baseline and inert here (no broker call, no page);
  * the fake book understood every SQL statement (`_unknown_sql` empty).

⚠ The baseline is PINNED to 97b08d51 (the origin/main #687 is rebased on; 90d02459 before the 2026-10-02 rebase), not "origin/main": once the
branch merges, origin/main contains it and the comparison would be self-against-self. A later change
to these paths that is unrelated to #687 will show here as an unlisted difference — re-capture the
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
PINNED_BASELINE_SHA = "97b08d51380e60f33f8f4ef545afe35289b23a88"
COMPONENTS = ("broker_calls", "pages", "result", "raised", "book_after")

# Scenarios that exist only on the branch: the depth machinery, inert with the toggle OFF.
BRANCH_ONLY = {
    "s24_depth_1901_runner_with_no_marked_rows": [],     # the 19:01 runner finds no marked row
    "s25_depth_stamp_with_the_toggle_off": None,         # a new MAGNA53 row is not stamped 'depth'
}

# ── THE ALLOW-LIST. Every exception is tied to its scenario and names the fix or ruling. ─────
# broker_calls / pages / result / raised = the exact branch value; book_after = the fields that
# differ from the baseline book (trades) or the whole exit-order list (orders).
ALLOWED = {
    's02_1645_exit_sale_rejected_restored': {
        'why': '#687 (c): the failed-exit restore is sized from the broker (reads the position + live resting orders)',
        'broker_calls': [
            "cancel_order(account_mode='live', order_id='stop-1')",
            "get_position(account_mode='live', ticker='KOD')",
            "close_position(account_mode='live', qty=None, ticker='KOD')",
            "get_position(account_mode='live', ticker='KOD')",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "place_stop_order(account_mode='live', client_order_id=None, qty=10, side='sell', stop_price=58, ticker='KOD')",
        ],
    },
    's03_1645_exit_restore_through_the_price': {
        'why': '#687 (c) restore sizing + RULING (3): the restore is through the price, so the free shares are sold at market',
        'broker_calls': [
            "cancel_order(account_mode='live', order_id='stop-1')",
            "get_position(account_mode='live', ticker='KOD')",
            "close_position(account_mode='live', qty=None, ticker='KOD')",
            "get_position(account_mode='live', ticker='KOD')",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "place_stop_order(account_mode='live', client_order_id=None, qty=10, side='sell', stop_price=58, ticker='KOD')",
            "close_position(account_mode='live', qty=10, ticker='KOD')",
        ],
        'pages': [
            '💰 LIVE-$ ⚠️ Full exit FAILED for KOD: insufficient qty available: available 0, held_for_orders 10\nThe price is already through the stop ($58.00), so it could not be re-placed — the shares it covered are being SOLD AT MARKET, as the triggered stop would have. Confirms with real P&amp;L on fill.',
        ],
        'book_after': {'orders': [{'exit_reason': 'sma_trail_stop', 'id': 'sell-1', 'purpose': 'full_exit', 'qty': 10, 'status': 'accepted'}]},
    },
    's04_1645_exit_beside_resting_oco_third': {
        'why': '#687 (a): a resting +8R OCO third no longer skips the sale; the two thirds sell, the third keeps its OCO',
        'broker_calls': [
            "get_position(account_mode='live', ticker='KOD')",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "cancel_order(account_mode='live', order_id='stop-1')",
            "get_position(account_mode='live', ticker='KOD')",
            "close_position(account_mode='live', qty=4, ticker='KOD')",
        ],
        'pages': [
            '💰 LIVE-$ 📋 *Closing order placed:* KOD — sma_trail_stop\nMarket sell 4 sh — pending fill (Order sell-1)\n_Confirms with real P&L on fill._\n2 sh stay under the resting profit-take (its own target and breakeven stop).',
        ],
        'result': True,
        'book_after': {'orders': [{'exit_reason': None, 'id': 'oco-1', 'purpose': 'partial_exit', 'qty': 2, 'status': 'new'}, {'exit_reason': 'sma_trail_stop', 'id': 'sell-1', 'purpose': 'full_exit', 'qty': 4, 'status': 'accepted'}]},
    },
    's05_1645_exit_closing_order_already_queued': {
        'why': '#687 (a): a skip that remains is paged (main skipped silently)',
        'pages': [
            '💰 LIVE-$ ⚠️ Full exit NOT placed for KOD (sma_trail_stop): a closing order (sell-q) is already queued for this position.',
        ],
    },
    's28_1645_exit_beside_a_plain_resting_limit': {
        'why': 'ruling (ii) 2026-10-02: a plain resting profit-take limit (no stop of its own) is left '
               'resting and the free shares are sold, as beside the OCO third (main skipped the whole '
               'sale); only the trade\'s stop is cancelled, the limit is never touched',
        'broker_calls': [
            "get_position(account_mode='live', ticker='KOD')",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "cancel_order(account_mode='live', order_id='stop-1')",
            "get_position(account_mode='live', ticker='KOD')",
            "close_position(account_mode='live', qty=4, ticker='KOD')",
        ],
        'pages': [
            '💰 LIVE-$ 📋 *Closing order placed:* KOD — sma_trail_stop\nMarket sell 4 sh — pending fill '
            '(Order sell-1)\n_Confirms with real P&L on fill._\n2 sh stay under the resting profit-take '
            '(a plain limit with no stop of its own — left resting, as ruled 2026-10-02).',
        ],
        'result': True,
        'book_after': {'orders': [{'exit_reason': None, 'id': 'lim-1', 'purpose': 'partial_exit', 'qty': 2, 'status': 'new'}, {'exit_reason': 'sma_trail_stop', 'id': 'sell-1', 'purpose': 'full_exit', 'qty': 4, 'status': 'accepted'}]},
    },
    's09_sync_under_a_queued_sale_paper_soft_reservation': {
        'why': '61a6c479 sync hunk: the books are not lowered under a queued sale (paper soft-reservation)',
        'pages': [
            '📄 PAPER ⚠️ *Position Sync Discrepancies (paper):*\n  • Qty mismatch KOD: DB=10 Alpaca=3 — books kept (a closing order is queued, or its reservation is unreadable)',
        ],
        'result': ['Qty mismatch KOD: DB=10 Alpaca=3 — books kept (a closing order is queued, or its reservation is unreadable)'],
        'book_after': {'trades': {'401': {'remaining_shares': 10}}},
    },
    's11_stream_fill_beside_resting_oco_third': {
        'why': '#687 (b): the full-exit fill decrements and keeps the row open under the resting third',
        'pages': [
            '💰 LIVE-$ 📤 *Sold:* KOD — sma_trail_stop\nExit @$66.00 × 4 shares\n2 sh remain under the resting profit-take (its own target and breakeven stop) — the trade stays open until they exit.\nP&L so far: $+84.00',
        ],
        'book_after': {'trades': {'401': {'closed_at': None, 'closed_on': None, 'remaining_shares': 2, 'status': 'filled', 'stop_order_id': 'stop-1'}}},
    },
    's12_stream_stop_cancelled_by_the_planned_sale': {
        'why': "RULING (2)(i): the stop our own planned sale cancelled is not paged 'unprotected'",
        'pages': [
            '💰 LIVE-$ 📋 *Closing order placed:* KOD — sma_trail_stop\nMarket sell 10 sh — pending fill (Order sell-1)\n_Confirms with real P&L on fill._',
        ],
    },
    's14_stream_queued_sale_cancelled_stop_restored': {
        'why': '#687 (c): the stream restore is sized from the broker; the page names the size',
        'broker_calls': [
            "get_position(account_mode='live', ticker='KOD')",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "place_stop_order(account_mode='live', client_order_id=None, qty=10, side='sell', stop_price=58, ticker='KOD')",
        ],
        'pages': [
            '💰 LIVE-$ ⚠️ *Close order CANCELLED:* KOD\nPosition still open. Stop re-placed @$58.00 for 10 sh.',
        ],
    },
    's15_stream_queued_sale_expired_restore_through_the_price': {
        'why': '#687 (c) restore sizing + RULING (3): the restore is through the price, so the shares are sold at market',
        'broker_calls': [
            "get_position(account_mode='live', ticker='KOD')",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "place_stop_order(account_mode='live', client_order_id=None, qty=10, side='sell', stop_price=58, ticker='KOD')",
            "close_position(account_mode='live', qty=10, ticker='KOD')",
        ],
        'pages': [
            '💰 LIVE-$ 🚨 *Close order EXPIRED:* KOD\nThe price is already below the stop $58.00, so no stop could be re-placed — selling 10 sh at market now (Order sell-1), as the triggered stop would have. _Confirms with real P&L on fill._',
        ],
        'book_after': {'orders': [{'exit_reason': 'sma_trail_stop', 'id': 'sell-1', 'purpose': 'full_exit', 'qty': 10, 'status': 'accepted'}, {'exit_reason': 'sma_trail_stop', 'id': 'sell-q', 'purpose': 'full_exit', 'qty': 10, 'status': 'expired'}]},
    },
    's17_watchdog_while_an_exit_holds_the_trade_lock': {
        'why': '#687 (e): the stop-ACK watchdog defers to an exit holding the per-trade lock',
        'broker_calls': [
        ],
        'pages': [
        ],
        'book_after': {'trades': {'401': {'stop_order_id': None}}},
    },
    's18_coverage_1700_slot_after_a_queued_sale': {
        'why': '#687 (f): OUR queued closing order counts as coverage (no 17:00 UNPROTECTED page, no repair read)',
        'broker_calls': [
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
        ],
        'pages': [
        ],
    },
    's20_refresh_row_held_only_by_oco_third': {
        'why': "RULING (2)(ii): a position held only by its OCO third is not paged 'No stop' (one broker read)",
        'broker_calls': [
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
        ],
        'pages': [
        ],
    },
    's21_refresh_genuinely_uncovered': {
        'why': 'RULING (2)(ii): the one extra broker read; the genuine gap still pages',
        'broker_calls': [
            "place_stop_order(account_mode='live', client_order_id='apollo_live_magna53_KOD_1', qty=10, side='sell', stop_price=58, ticker='KOD')",
            "place_stop_order(account_mode='live', client_order_id='apollo_live_magna53_KOD_2', qty=10, side='sell', stop_price=58, ticker='KOD')",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
        ],
    },
    's22_safeguards_partial_sale_loss_today': {
        'why': 'RULING (1): a loss on a partial sale counts toward the 2% daily loss limit at once',
        'result': [False, 'block:daily_loss: $-110 >= $100 (mode=paper)', 0],
    },
    's23_sdk_close_position_with_qty': {
        'why': '#687 (d): close_position(qty) hands alpaca-py a ClosePositionRequest, not a dict',
        'broker_calls': [
            "TradingClient.close_position(close_options={'__type__': 'ClosePositionRequest', 'built_with': {'qty': '2'}}, symbol_or_asset_id='KOD')",
        ],
        'result': {'client_order_id': 'c-1', 'created_at': None, 'filled_at': None, 'filled_avg_price': None, 'filled_qty': 0, 'id': 'sdk-1', 'legs': [], 'limit_price': None, 'order_class': 'simple', 'qty': 2, 'side': 'sell', 'status': 'accepted', 'stop_price': None, 'symbol': 'KOD', 'type': 'market'},
        'raised': None,
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


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_toggle_off_matches_the_baseline_except_the_named_exceptions(branch_log, scenario):
    base, here = _BASE["scenarios"][scenario], branch_log[scenario]
    assert here.get("_unknown_sql") == [], (
        f"{scenario}: the fake book did not understand {here.get('_unknown_sql')}")
    if scenario in BRANCH_ONLY:
        assert "absent" in base, f"{scenario}: expected to be branch-only"
        assert here["broker_calls"] == [] and here["pages"] == [], here
        assert here["raised"] is None and here["result"] == BRANCH_ONLY[scenario], here
        return
    assert "absent" not in base and "absent" not in here, (base.get("absent"), here.get("absent"))
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
            assert h == b, (f"{scenario}.{comp}: UNLISTED difference from the pre-#687 "
                            f"baseline\n  baseline: {b!r}\n  here:     {h!r}")
