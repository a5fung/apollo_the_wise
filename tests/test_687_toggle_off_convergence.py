"""#687 CONVERGENCE TEST — the broker-facing paths match MAIN except a NAMED allow-list.

WHY (cut-back round, 2026-10-02). Three review rounds added defence-in-depth to SHARED broker code and
did not converge. The criterion that ended it: a change to these paths may differ from main ONLY where
a fix or an operator ruling says so, each difference named and pinned to its exact value.

HISTORY. Until 2026-10-03 the baseline was the pre-#687 code (97b08d51) and the allow-list named the
#687 fixes (a)-(f), the 61a6c479 sync hunk and the rulings (1)-(3), (ii), (iv) — 17 entries; that
version is in git (`git log -p -- tests/test_687_toggle_off_convergence.py`). #687 merged and deployed
2026-10-03 (a88a8043), so main IS that behaviour now: the baseline was RE-PINNED to origin/main
8e1329f0 and those entries left the list (each was now identical to the baseline). Ruling (iii) then
merged 2026-10-04 → re-pinned to 76e2ce4b, its seven s32-s38 entries left the list the same way.
Ruling (i) merged later on 2026-10-04 (fa5bb191) → re-pinned to 4e454395 (the ruling (i) deploy
commit), and its s39-s42 entries left the list as identical to main — s41 entirely; s39, s40 and s42
re-enter below ONLY for what ruling (a) changes in them. The list below names only what the current
change — ruling (a), operator 2026-10-04: the coverage repair reads the broker before placing — does
differently from main.

HOW. `tests/_convergence_687_harness.py` drives 43 fixed scenarios (the 16:45 trail exit with and
without a resting +8R OCO third or a plain resting limit, the 16:45 job itself, a stop raise via
`update_stop`, the position sync with and without a queued sale, stream fill / cancel / expiry events,
the stop-ACK watchdog, the 17:00 coverage slot, the intraday coverage page, the stop refresh, a stop
that cannot be placed because the price is through it — at the failed-exit restore and at each of the
six other stop-placing sites (s32-s38) — the daily-loss gate, `close_position(qty)` at the alpaca-py
boundary, the failed-exit restore reading a FLAT broker at the 16:45 exit and at the stream's
dead-sale path, and an UNREADABLE one (s39-s41), the coverage reconciler on a flat broker (s42) and
— since ruling (a) — the 17:00 coverage slot on a flat broker (s43)) and records every broker-client
call (method + bound arguments), every Telegram page, the return value and the fake book's end state.
The BASELINE log was recorded by running the SAME harness on the pinned main commit
(`scripts/probes/_687/capture_toggle_off_baseline.sh`). This test runs it on the current tree and
asserts:

  * a component NOT in the allow-list equals the baseline exactly;
  * an allow-listed component equals its pinned expectation exactly (a stray call inside an allowed
    scenario still fails) AND differs from the baseline (the exception is real, not stale);
  * the two depth-only scenarios stay inert with the toggle OFF (no broker call, no page);
  * the fake book understood every SQL statement (`_unknown_sql` empty).

⚠ The baseline is PINNED to 4e454395 (the origin/main this change is built on), not "origin/main":
once a change merges, origin/main contains it and the comparison would be self-against-self. A later
change to these paths that is unrelated will show here as an unlisted difference — re-capture the
baseline (and re-pin) deliberately; never widen the allow-list to absorb it.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests" / "_convergence_687_harness.py"
BASELINE = ROOT / "tests" / "fixtures" / "687_toggle_off_main_baseline.json"
PINNED_BASELINE_SHA = "3b82b7c0b51eae18bfceae68f6ddae9019cf8441"
COMPONENTS = ("broker_calls", "pages", "result", "raised", "book_after")

# The depth machinery (#687 B), merged with the toggle OFF: compared to the baseline like any other
# scenario AND held inert — no broker call, no page, this exact result.
INERT_WITH_THE_TOGGLE_OFF = {
    "s24_depth_1901_runner_with_no_marked_rows": [],     # the 19:01 runner finds no marked row
    "s25_depth_stamp_with_the_toggle_off": None,         # a new MAGNA53 row is not stamped 'depth'
}

WATCHDOG_ET = ("2026-10-05 — the stop-ACK watchdog's pages print the fill time in ET "
               "(they printed the UTC clock labelled ET)")

# ── THE ALLOW-LIST. Every exception is tied to its scenario and names the change. ──────────────
# broker_calls / pages / result / raised = the exact branch value; book_after = the fields that
# differ from the baseline book (trades) or the whole exit-order list (orders).
# HISTORY: ruling (iii)'s s32-s38 left this list when it merged (baseline re-pinned to main); ruling (i)'s
# s39-s42 and ruling (a)'s s19/s32/s38/s42/s43 left it the same way on 2026-10-05 when the baseline was
# re-pinned to 3b82b7c0 (both rulings on main). What remains is the one change built on that baseline.
LAST_STOP_728 = ("2026-11-21 (#728, operator ruling 2026-11-20 (1)) — the stop-ACK watchdog's fallback goes at the "
                 "trade's own LAST stop ($58.00, the row's stop_price), not orb_low ($57.50)")
REPLACE_728 = ("2026-11-21 (#728, bug fix) — a price-only stop move is ONE atomic price-only replace_order on the "
               "live stop: same price, same share count, no cancel_order / place_stop_order")
ALLOWED = {
    's16_watchdog_fresh_entry_without_a_stop': {
        'why': WATCHDOG_ET + " (the page's fill time — a 09:31:05 ET fill read '13:31:05 ET'); " + LAST_STOP_728,
        'broker_calls': [
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "place_stop_order(account_mode='live', client_order_id=None, qty=10, side='sell', stop_price=58, ticker='KOD')",
        ],
        'pages': [
            "💰 LIVE-$ 🛡 *STOP-ACK TIMEOUT — REMEDIATED:* KOD\nTrade #401 filled at 09:31:05 ET, stop_order_id never populated.\nFallback stop placed at $58.00 (the trade’s last stop). Original OTO child stop-leg likely failed silently on Alpaca side.",
        ],
    },
    's36_watchdog_fallback_through_the_price': {
        'why': LAST_STOP_728 + " — refused through the price, the #687 ruling (iii) sale is unchanged",
        'broker_calls': [
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "place_stop_order(account_mode='live', client_order_id=None, qty=10, side='sell', stop_price=58, ticker='KOD')",
            "get_position(account_mode='live', ticker='KOD')",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "close_position(account_mode='live', qty=10, ticker='KOD')",
        ],
        'pages': [
            "💰 LIVE-$ 🚨 <b>Price already below the stop:</b> KOD\nThe stop at $58.00 could not be placed — the broker refused it because the price is already below it. Selling 10 sh at market now (Order sell-1), as the triggered stop would have.\n<i>Confirms with real P&amp;L on fill.</i>",
        ],
    },
    's27_1645_job_unstamped_trade_trail_raise': {
        'why': REPLACE_728 + " (the 16:45 trail raise 58.00 -> 70.50 on 10 sh)",
        'broker_calls': [
            "get_order(account_mode='live', order_id='stop-1', timeout=None)",
            "replace_order(account_mode='live', client_order_id='apollo_live_magna53_KOD_1', limit_price=None, order_id='stop-1', qty=None, stop_price=70.5)",
            "get_order(account_mode='live', order_id='replaced-stop-1', timeout=None)",
        ],
        # the same stop price (70.5) and share count (10) as main; only the stop order's id differs
        'book_after': {
            'trades': {'401': {'stop_order_id': 'replaced-stop-1'}},
            'orders': [{'exit_reason': 'stop_hit', 'id': 'replaced-stop-1', 'purpose': 'stop_loss', 'qty': 10,
                        'status': 'new'}],
        },
    },
    's35_refresh_replace_through_the_price': {
        'why': ("2026-11-21 (#728) — the stop refresh goes through move_stop_price_only: ONE more read of the dead "
                "stop (not live -> nothing to replace), then update_stop exactly as main, the ruling (iii) sale "
                "included"),
        'broker_calls': [
            "get_order(account_mode='live', order_id='stop-1', timeout=None)",
            "get_order(account_mode='live', order_id='stop-1', timeout=None)",
            "get_order(account_mode='live', order_id='stop-1', timeout=None)",
            "cancel_order(account_mode='live', order_id='stop-1')",
            "place_stop_order(account_mode='live', client_order_id='apollo_live_magna53_KOD_1', qty=10, side='sell', stop_price=58, ticker='KOD')",
            "place_stop_order(account_mode='live', client_order_id='apollo_live_magna53_KOD_2', qty=10, side='sell', stop_price=58, ticker='KOD')",
            "get_position(account_mode='live', ticker='KOD')",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "close_position(account_mode='live', qty=10, ticker='KOD')",
        ],
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


def test_every_exception_from_main_is_one_of_the_named_changes():
    """Three changes are built on this baseline, and nothing else may differ:
      * 2026-10-05 — the watchdog's pages show the fill time in ET (s16's page);
      * 2026-11-21, #728 ruling (1) — the watchdog's fallback goes at the trade's LAST stop (s16, s36): the same
        calls as main with ONE number changed, 57.5 -> 58;
      * 2026-11-21, #728 — a price-only stop move is one price-only replace (s27), and the refresh reads the dead
        stop once more before main's unchanged path (s35)."""
    assert sorted(ALLOWED) == [
        "s16_watchdog_fresh_entry_without_a_stop", "s27_1645_job_unstamped_trade_trail_raise",
        "s35_refresh_replace_through_the_price", "s36_watchdog_fallback_through_the_price"]
    base = _BASE["scenarios"]

    def _calls(name):
        return _norm("broker_calls", base[name]["broker_calls"])

    # the watchdog: main's calls and pages with the stop level 57.5 -> 58 (and s16's ET clock + source words)
    for name in ("s16_watchdog_fresh_entry_without_a_stop", "s36_watchdog_fallback_through_the_price"):
        entry = ALLOWED[name]
        assert set(entry) == {"why", "broker_calls", "pages"}
        assert entry["broker_calls"] == [c.replace("stop_price=57.5", "stop_price=58") for c in _calls(name)]
        assert entry["broker_calls"] != _calls(name)

    def _mask(pages):
        return [re.sub(r"\d{2}:\d{2}:\d{2} ET", "HH:MM:SS ET", p).replace(" (the trade’s last stop)", "")
                .replace("$58.00", "$57.50") for p in pages]
    for name in ("s16_watchdog_fresh_entry_without_a_stop", "s36_watchdog_fallback_through_the_price"):
        assert _mask(ALLOWED[name]["pages"]) == _mask(base[name]["pages"])

    # the 16:45 trail raise: main cancelled and placed; here ONE price-only replace at main's price, nothing else
    s27 = ALLOWED["s27_1645_job_unstamped_trade_trail_raise"]
    assert set(s27) == {"why", "broker_calls", "book_after"}
    main27 = _calls("s27_1645_job_unstamped_trade_trail_raise")
    assert any(c.startswith("cancel_order(") for c in main27)
    [main_place] = [c for c in main27 if c.startswith("place_stop_order(")]
    assert "qty=10" in main_place and "stop_price=70.5" in main_place
    assert not any(c.startswith(("cancel_order(", "place_stop_order(", "close_position(")) for c in s27["broker_calls"])
    [rep] = [c for c in s27["broker_calls"] if c.startswith("replace_order(")]
    assert "order_id='stop-1'" in rep and "stop_price=70.5" in rep and "qty=None" in rep and "limit_price=None" in rep
    assert set(s27["book_after"]["trades"]["401"]) == {"stop_order_id"}        # stop_price 70.5 = main's
    assert [o["qty"] for o in s27["book_after"]["orders"]] == [10]

    # the refresh after a dead stop: main's calls plus exactly one more read of that stop, in front
    s35 = ALLOWED["s35_refresh_replace_through_the_price"]
    assert set(s35) == {"why", "broker_calls"}
    main35 = _calls("s35_refresh_replace_through_the_price")
    assert s35["broker_calls"] == [main35[0]] + main35 and main35[0].startswith("get_order(")


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
