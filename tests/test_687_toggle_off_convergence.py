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
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests" / "_convergence_687_harness.py"
BASELINE = ROOT / "tests" / "fixtures" / "687_toggle_off_main_baseline.json"
PINNED_BASELINE_SHA = "4e4543957c1be082ebae59b46698ba8d9420c67b"
COMPONENTS = ("broker_calls", "pages", "result", "raised", "book_after")

# The depth machinery (#687 B), merged with the toggle OFF: compared to the baseline like any other
# scenario AND held inert — no broker call, no page, this exact result.
INERT_WITH_THE_TOGGLE_OFF = {
    "s24_depth_1901_runner_with_no_marked_rows": [],     # the 19:01 runner finds no marked row
    "s25_depth_stamp_with_the_toggle_off": None,         # a new MAGNA53 row is not stamped 'depth'
}

RULING_A = "ruling (a) 2026-10-04 — the coverage repair reads the broker before placing"

# The ONE sentence both flat pages (s39, s40) now end with — ruling (a) replaced the warning that
# the coverage repair "may re-place a stop from the books".
_FLAT_PAGE_TAIL = (
    "No stop placed: the broker shows no position, so there is nothing to protect. Our books still "
    "show the trade open — run /syncnow to book the exit from the broker, and reconcile the row by "
    "hand if it is still open (if this was the only open position, the sync will not act). The "
    "after-close coverage repair (17:00 / 19:00 ET) also reads the broker and will not re-place a "
    "stop while it shows no position."
)

# ── THE ALLOW-LIST. Every exception is tied to its scenario and names the ruling. ──────────────
# broker_calls / pages / result / raised = the exact branch value; book_after = the fields that
# differ from the baseline book (trades) or the whole exit-order list (orders).
ALLOWED = {
    # ── the place branch now reads the broker (HELD here): one `get_position` before the stop ──
    's19_coverage_1700_slot_genuine_gap_repair_fails': {
        'why': RULING_A + " (the 17:00 slot's repair, broker HELD: one position read before the place; same stop, same refusal, same page as main)",
        'broker_calls': [
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "get_position(account_mode='live', ticker='KOD')",
            "place_stop_order(account_mode='live', client_order_id='apollo_live_magna53_KOD_1', qty=10, side='sell', stop_price=58, ticker='KOD')",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
        ],
    },
    's32_coverage_reconciler_place_through_the_price': {
        'why': RULING_A + " (the reconciler's place branch, broker HELD: one position read before the place; ruling (iii)'s refusal → sale is unchanged after it)",
        'broker_calls': [
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "get_position(account_mode='live', ticker='KOD')",
            "place_stop_order(account_mode='live', client_order_id='apollo_live_magna53_KOD_1', qty=10, side='sell', stop_price=58, ticker='KOD')",
            "get_position(account_mode='live', ticker='KOD')",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "close_position(account_mode='live', qty=10, ticker='KOD')",
        ],
    },
    's38_oco_cancel_unfilled_restore_through_the_price': {
        'why': RULING_A + " (the OCO-cancel handler reaches the reconciler's place branch, broker HELD: one position read before the place; the rest as main)",
        'broker_calls': [
            "get_order(account_mode='live', order_id='leg-1', timeout=None)",
            "get_position(account_mode='live', ticker='KOD')",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "get_position(account_mode='live', ticker='KOD')",
            "place_stop_order(account_mode='live', client_order_id='apollo_live_magna53_KOD_1', qty=2, side='sell', stop_price=60, ticker='KOD')",
            "get_position(account_mode='live', ticker='KOD')",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "close_position(account_mode='live', qty=2, ticker='KOD')",
        ],
    },
    # ── a FLAT broker at the place branch: nothing placed ──
    's42_coverage_reconciler_refused_stop_broker_flat': {
        'why': RULING_A + " (the reconciler on a FLAT broker: the read comes first, so the stop is never sent — main sent it, had it refused as through the price, and returned 'position breached the stop. Operator decision needed' on an empty account; the branch places nothing and says the broker shows no position, /syncnow then by hand)",
        'broker_calls': [
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "get_position(account_mode='live', ticker='KOD')",
            "get_all_positions(account_mode='live', raise_on_error=True)",
        ],
        'result': "⚠️ KOD: the broker shows no position, so no stop was placed. Our records still show the trade open (10 sh) — run /syncnow to book the exit from the broker, and reconcile the row by hand if it is still open.",
    },
    's43_coverage_1700_slot_broker_flat': {
        'why': RULING_A + " (the 17:00 slot on a FLAT broker: main placed a 10-sh sell stop on the empty account, re-read it as covered and stayed silent; the branch places nothing, the slot's own re-check still reads the books and pages UNPROTECTED — its 'holds 10 sh' is the row, not the broker — and the row keeps no stop pointer)",
        'broker_calls': [
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
            "get_position(account_mode='live', ticker='KOD')",
            "get_all_positions(account_mode='live', raise_on_error=True)",
            "get_open_orders(account_mode='live', raise_on_error=True, ticker='KOD')",
        ],
        'pages': [
            "🚨 *UNPROTECTED AFTER THE CLOSE*\n• KOD: holds 10 sh, live stop covers 0 sh\n\nExtended hours are still trading, and the automatic repair above did not hold.\n`/syncnow live` re-runs the same repair now.",
        ],
        'book_after': {'trades': {'401': {'stop_order_id': None}}},
    },
    # ── the two flat PAGES of ruling (i): only their last sentence changes ──
    's39_1645_exit_sale_rejected_broker_flat': {
        'why': RULING_A + " (ruling (i)'s failed-exit flat page: the last sentence no longer warns that the repair may re-place a stop from the books — it says the repair reads the broker too; same calls, same book)",
        'pages': [
            '💰 LIVE-$ ⚠️ Full exit FAILED for KOD: {"code":40410000,"message":"position does not exist"}\n' + _FLAT_PAGE_TAIL,
        ],
    },
    's40_stream_queued_sale_cancelled_broker_flat': {
        'why': RULING_A + " (ruling (i)'s stream dead-sale flat page: the same last-sentence change; same calls, same book)",
        'pages': [
            '💰 LIVE-$ ⚠️ *Close order CANCELLED:* KOD\n' + _FLAT_PAGE_TAIL,
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


def test_every_exception_from_main_is_ruling_a():
    """The change built on this baseline is ONE ruling: #687 (a), operator 2026-10-04 — the coverage
    repair reads the broker before placing (FLAT → nothing placed; HELD / UNREADABLE → exactly as
    main). Nothing else may differ, and each entry's shape must be the ruling's own:
      * a scenario that reaches the place branch with the broker HELD differs from main by EXACTLY
        one `get_position` inserted immediately before its (first) `place_stop_order` — nothing else;
      * a FLAT scenario sends NO stop and NO sale, and its read ends in the confirming list read;
      * ruling (i)'s two flat pages differ only in the page, which ends with the new sentence and no
        longer warns of a re-placed stop."""
    for name, entry in ALLOWED.items():
        assert entry["why"].startswith(RULING_A + " ("), name

    held = ["s19_coverage_1700_slot_genuine_gap_repair_fails",
            "s32_coverage_reconciler_place_through_the_price",
            "s38_oco_cancel_unfilled_restore_through_the_price"]
    for n in held:
        assert set(ALLOWED[n]) == {"why", "broker_calls"}, n
        here = list(ALLOWED[n]["broker_calls"])
        base = _norm("broker_calls", _BASE["scenarios"][n]["broker_calls"])
        i = next(k for k, c in enumerate(here) if c.startswith("place_stop_order("))
        assert here[i - 1] == "get_position(account_mode='live', ticker='KOD')", (n, here)
        assert here[:i - 1] + here[i:] == base, (n, "more than the one read differs from main")

    flat = ["s42_coverage_reconciler_refused_stop_broker_flat", "s43_coverage_1700_slot_broker_flat"]
    for n in flat:
        calls = ALLOWED[n]["broker_calls"]
        assert not any(c.startswith(("place_stop_order(", "close_position(")) for c in calls), n
        assert "get_all_positions(account_mode='live', raise_on_error=True)" in calls, n
        base = _norm("broker_calls", _BASE["scenarios"][n]["broker_calls"])
        assert any(c.startswith("place_stop_order(") for c in base), (n, "main placed a stop here")

    pages_only = ["s39_1645_exit_sale_rejected_broker_flat",
                  "s40_stream_queued_sale_cancelled_broker_flat"]
    for n in pages_only:
        assert set(ALLOWED[n]) == {"why", "pages"}, n
        [page] = ALLOWED[n]["pages"]
        assert page.endswith(_FLAT_PAGE_TAIL) and "may re-place" not in page, n

    assert sorted(ALLOWED) == sorted(held + flat + pages_only)


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
