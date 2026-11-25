"""Setup (entry / list rule) VERSIONS — the ONE place that answers "which buy rules produced this row".

WHY (operator 2026-11-25, "Go" on: "stamp every list row and trade with a setup version, bumped on every buy-rule
change, and split /trades and reviews by it"). The breakout book's first 23 paper trades were bought under three
different rule sets and pooled into one line; exits already have eras (`rule_eras.py`), entries did not.

WHAT A VERSION IS. One coherent set of BUY rules for one strategy: what gets on the nightly list, where the buy
point sits, what must be true in the minute of the buy, which names take the slots. Exits, labels (the 11-15
grades), bug fixes and plumbing are NOT versions. From 2026-11-25 on, EVERY change-log entry that changes a buy
rule bumps the version in the same commit (`docs/setups/CHANGE_PROCESS.md`).

TWO WAYS A ROW GETS ITS VERSION:
  * STAMPED at creation (from 2026-11-25): the nightly list row carries `gates.setup_version`, the trade row carries
    `mi_live_trades.setup_version` (written by the entry funnel in the row's own transaction). The stamp WINS.
  * READ-TIME for rows written before the stamp: `setup_version_as_of(strategy, alert_date)` against the registry's
    `first_session` dates. A version with `first_session = None` is never returned by date — it is reached by its
    stamp only (the narrow version is not deployed as this is written; dating it would relabel earlier trades).

HONESTY ABOUT THE PAST. Nothing stamped v1.0 .. v1.4 at the time. v1.0's two dates are written in the change log of
`docs/setups/consolidation_breakout.md`; v1.1 .. v1.4 are RECONSTRUCTED (`reconstructed=True`) from that change log,
the PLAN week notes and stored probe outputs. `changed_on` is the change-log date
(the day the rule was signed / built); `first_session` is the first session the paper book could have bought under
it, which is later and is the date trades are mapped by. Ten buy-rule changes are folded into five bumps: changes
that shipped in the same deploy, or that never acted on a paper session apart, share a version, and every one of
them is listed in that version's `changes`. NOT checked against production in this build (no prod read).

Pure: dates, strings and hashing only. No DB, no I/O, no import of any breakout or broker module.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

BREAKOUT_V1 = "breakout_v1"
BREAKOUT_SSOT = "docs/setups/consolidation_breakout.md"


@dataclass(frozen=True)
class SetupVersion:
    version: str                 # the stamp, e.g. "breakout_v1.5-narrow"
    short: str                   # two or three plain words for a phone line
    changed_on: date             # the change-log date of its (first) rule change
    first_session: Optional[date]  # first session the paper book could buy under it; None = reached by stamp only
    changes: tuple               # ((change-log heading prefix, what changed), ...) — every buy-rule change folded in
    reconstructed: bool          # True = dates / grouping rebuilt after the fact, nothing stamped it at the time
    note: str = ""


# Each `changes` heading is a PREFIX of a `### ` line in the SSoT change log (pinned by tests/test_setup_versions.py).
BREAKOUT_V1_VERSIONS: tuple = (
    SetupVersion(
        "breakout_v1.0", "first rules", date(2026, 10, 28), date(2026, 11, 2),
        (("### 2026-10-28 — breakout v1 FINAL for the Saturday 10-31 build",
          "the first rule set: level = the 5-day high, list ordered by RS"),
         ("### 2026-10-30 — breakout v1 PHASE 2 part A BUILT",
          "buy above the level and the opening 5-minute high on a 1.2x volume pace (50-day base), stop at the "
          "day's low when no wider than one daily range")),
        reconstructed=False,
        note="first list night 10-30, first paper session 11-02 (both in the change log). One trade: MTW 11-02. "
             "Paper was switched off 11-02 10:07 ET (scripts/probes/_717_d8_1107/q_switch.out)."),
    SetupVersion(
        "breakout_v1.1", "list rebuilt", date(2026, 11, 2), date(2026, 11, 3),
        (("### 2026-11-02 — breakout v1's list gains a DAILY-RANGE FLOOR",
          "daily-range floor 4.26% + a pinned-deal check (list nights 11-03 and 11-04: 8 names each)"),
         ("### 2026-11-02 — breakout v1's list REBUILT from Qullamaggie's own trades",
          "the list rebuilt from Qullamaggie's trades: 7 list rules, daily-range floor 2.1%, the order score, the "
          "10-day volume bar (list nights from 11-05)"),
         ("### 2026-11-07 — breakout v1 STAGE 2 (#717)",
          "paper slots filled by the order score, hold-only, the overflow waits for a slot")),
        reconstructed=True,
        note="three changes in one version: paper was OFF from 11-02 10:07 ET to 11-09 21:23 ET, so the only "
             "session any of them bought on is 11-10 (4 trades), with all three in force. Sub-dates from "
             "scripts/probes/_eve_1106/q717.out; paper off again 11-10 10:19 ET (_717_off_1110/off.out)."),
    SetupVersion(
        "breakout_v1.2", "price break only", date(2026, 11, 11), date(2026, 11, 12),
        (("### 2026-11-11 — breakout v1 INITIAL RULE SET",
          "list gates loosened to keep Qullamaggie's buys (prior move 20%, base depth to 11 daily ranges, 21-day "
          "line -0.9, the 50-day no longer a gate); level = the lower of the range high and the 5-day high; the "
          "wick rule"),
         ("### 2026-11-11 — breakout v1: VOLUME IS NO LONGER A BUY CONDITION",
          "the price break alone buys; volume pace recorded, not required")),
        reconstructed=True,
        note="deployed 11-11 21:16 ET with paper OFF (PLAN week note). No paper trade; the next version shipped "
             "before its first list night."),
    SetupVersion(
        "breakout_v1.3", "4% daily range", date(2026, 11, 12), date(2026, 11, 13),
        (("### 2026-11-12 — breakout v1: ADR floor 2.1% → 4%",
          "daily-range floor 2.1% -> 4%"),),
        reconstructed=True,
        note="deployed 11-12 noon ET with paper OFF (PLAN week note); list nights 11-12 and 11-13. No paper trade."),
    SetupVersion(
        "breakout_v1.4", "context checks", date(2026, 11, 14), date(2026, 11, 17),
        (("### 2026-11-14 — breakout v1: three CONTEXT gates on the nightly list",
          "off the list: more than 3% under a falling 50-day, a 6-month downtrend, a re-widening base on a flat "
          "or falling lower line"),
         ("### 2026-11-14 — breakout v1: SLOTS ON AN ACTUAL BREAK",
          "an order only in a minute that trades through the level; no resting buys on the top 5"),
         ("### 2026-11-14 — breakout v1: the PICK MODEL orders the nightly list",
          "the pick model sets the list order (which names take the 5 slots)")),
        reconstructed=True,
        note="one deploy (`b37ebd01`, CHANGELOG); first list night Mon 11-16, first paper session Tue 11-17 (PLAN "
             "week note). 18 trades 11-17..11-23, and every trade until the narrow version deploys. The moment "
             "paper was switched back on is not in the local records."),
    SetupVersion(
        "breakout_v1.5-narrow", "narrow only", date(2026, 11, 25), None,
        (("### 2026-11-25 — breakout v1 PAPER buys NARROW-list names only",
          "paper buys only list names that read narrow (swings over 40 sessions, ratio <= 0.6, unscored = "
          "narrow); the list itself is unchanged and the other names' breaks are recorded"),),
        reconstructed=False,
        note="not deployed as this is written: reached by its STAMP only. Fill `first_session` at verify-live."),
)

# strategy (= mi_live_trades.signal_type) -> its versions, oldest first. The LAST row is the current version.
REGISTRY: dict = {BREAKOUT_V1: BREAKOUT_V1_VERSIONS}
SSOT_FILE: dict = {BREAKOUT_V1: BREAKOUT_SSOT}


def versions_for(strategy: Optional[str]) -> tuple:
    return REGISTRY.get(strategy or "", ())


def current_setup_version(strategy: Optional[str]) -> Optional[str]:
    """The stamp a NEW list row / trade row of this strategy gets; None = the strategy is not versioned (no stamp,
    no extra write — MAGNA53 and every other strategy today)."""
    vs = versions_for(strategy)
    return vs[-1].version if vs else None


def setup_version_as_of(strategy: Optional[str], d: Optional[date]) -> Optional[str]:
    """READ-TIME version of an UNSTAMPED row by its session date: the newest version whose `first_session` <= d.
    None before the first version, for an unversioned strategy, or with no date. A version without a
    `first_session` is never returned here (its rows carry the stamp)."""
    if d is None:
        return None
    out = None
    for v in versions_for(strategy):
        if v.first_session is not None and v.first_session <= d:
            out = v.version
    return out


def setup_version_for_row(strategy: Optional[str], stamp: Optional[str], d: Optional[date]) -> Optional[str]:
    """THE one rule every reader uses: the row's own stamp wins; an unstamped row maps by its date."""
    return stamp or setup_version_as_of(strategy, d)


def display_name(version: str, strategy: Optional[str] = None) -> str:
    """'breakout_v1.5-narrow' -> 'v1.5-narrow' (the page already names the strategy)."""
    return version[len("breakout_"):] if version.startswith("breakout_") else version


# ── the bump gate's fingerprint ──────────────────────────────────────────────────────────────────────────────────
# A hash of the VALUES of the buy-rule constants, pinned to the current version. tests/test_setup_versions.py fails
# when the hash moves while the version does not. What it CANNOT see (say so, never imply otherwise): a rule changed
# inside a function body with no constant moving; `consolidation_breakout` constants `breakout_v1` does not
# re-export; the runtime ranking switch (`mi_safeguard_state('breakout_v1_ranking')` — each list row records
# `ranked_by`); the strategy row (`mi_strategies`) and the shared sizing / position limits (not setup rules).

# breakout_v1.py: EVERY module-level constant is in, except these (recorded on the row, gate nothing):
BV_NOT_BUY_RULES = frozenset({"VOL_WINDOW_50"})
BV_NOT_BUY_RULE_PREFIX = "SHAPE_"        # the shape readings gate nothing while ENFORCED_SHAPE_GATES == () (hashed)
# broker/breakout_v1_entry.py: mostly plumbing, so the buy rules are NAMED and every other constant is classified
# below — a new constant fails the test until it is put in one of the two sets.
ENTRY_BUY_RULES = frozenset({
    "N_SESSION_MINUTES", "OR_MINUTES", "FIRST_MINUTE", "EOD_MINUTE", "STOP_EPS", "VOLUME_PACE_GATE",
    "BREAK_LOOKBACK_MINUTES",
})
ENTRY_NOT_BUY_RULES = frozenset({
    "ACCOUNT_MODE", "STRATEGY_ID", "TOGGLE", "TOGGLE_ENV", "STRATEGY_LABEL", "COID_FAMILY_PREFIX",
    "CANCEL_POLL_ATTEMPTS", "CANCEL_POLL_S", "SNAPSHOT_FAILS_BEFORE_PAGE", "PLANNED_ENTRY_CANCEL", "BARS_CHUNK_MAX",
    "BARS_FAILS_BEFORE_PAGE", "HOLD_EVENT", "SLOTS_FULL_STATE", "SLOTS_UNREADABLE_STATE", "BREAK_LOOKBACK_EVENT",
    "NO_BREAK", "MISSED_BY_SLOTS", "ENTRY_ORDER_EVENT", "WOULD_BUY_EVENT", "NARROW_MISSING_EVENT",
    "ORIGINAL_ONLY_BREAK", "NOT_NARROW", "NARROW_MISSING", "DEFAULT_RANKED_BY", "RANKED_BY_SCORE",
    "STATE_OK", "STATE_SWITCHED_OFF", "STATE_REFUSED", "STATE_UNREADABLE",
    # after the fill (the one-minute low re-check): exit-side plumbing, no say in what is bought
    "FILL_STOP_CHECKED", "FILL_BAR_WAIT_MINUTES", "STOP_LOWER_VERIFY_POLLS", "STOP_LOWER_VERIFY_S",
})
# the list order decides which names take the slots: the default ranking and the frozen pick model are buy rules
LIST_BUY_RULES = frozenset({"DEFAULT_RANKING"})
PICK_MODEL_BUY_RULES = frozenset({"FEATURES", "INTERCEPT", "COEF", "RAW_FEATURES", "HALF_FILL"})
_BV_PRIVATE_RULES = ("_LEVERAGED_INVERSE", "_BASKET", "_UNDERLYINGS", "_CASE_SENSITIVE_UNDERLYINGS")  # the fund rule

_PLAIN = (bool, int, float, str, type(None))


def _is_const_name(name: str) -> bool:
    return name.isupper() and not name.startswith("_")


def _plain(v: Any) -> bool:
    if isinstance(v, _PLAIN):
        return True
    if isinstance(v, (tuple, list, frozenset, set)):
        return all(_plain(x) for x in v)
    if isinstance(v, dict):
        return all(isinstance(k, str) and _plain(x) for k, x in v.items())
    return False


def _canon(v: Any) -> Any:
    if isinstance(v, bool) or v is None or isinstance(v, (int, str)):
        return v
    if isinstance(v, float):
        return repr(v) if math.isfinite(v) else str(v)
    if isinstance(v, (tuple, list)):
        return [_canon(x) for x in v]
    if isinstance(v, (frozenset, set)):
        return sorted((_canon(x) for x in v), key=lambda x: json.dumps(x, sort_keys=True))
    if isinstance(v, dict):
        return {k: _canon(x) for k, x in sorted(v.items())}
    raise TypeError(f"not a plain constant: {type(v).__name__}")


def module_constants(mod) -> dict:
    """{NAME: value} for the module's public UPPERCASE names holding plain values (numbers, strings, tuples...)."""
    return {k: v for k, v in vars(mod).items() if _is_const_name(k) and _plain(v)}


def fingerprint_of(constants: dict) -> str:
    """The hash of a {"module.NAME": value} map (order-free; floats by repr; sets sorted)."""
    blob = json.dumps({k: _canon(v) for k, v in constants.items()}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def breakout_v1_rule_constants(bv, be, bl, pm) -> dict:
    """The buy-rule constants the fingerprint covers, as {"module.NAME": value}. The four modules (breakout_v1, the
    broker's breakout_v1_entry, breakout_v1_list, breakout_v1_pick_model) are PASSED IN: this module must not import
    broker code (the execution boundary), so the caller — the bump gate in tests/test_setup_versions.py — does."""
    out: dict = {}
    for k, v in module_constants(bv).items():
        if k not in BV_NOT_BUY_RULES and not k.startswith(BV_NOT_BUY_RULE_PREFIX):
            out[f"breakout_v1.{k}"] = v
    for k in _BV_PRIVATE_RULES:
        out[f"breakout_v1.{k}"] = getattr(bv, k)
    for k in sorted(ENTRY_BUY_RULES):
        out[f"breakout_v1_entry.{k}"] = getattr(be, k)
    for k in sorted(LIST_BUY_RULES):
        out[f"breakout_v1_list.{k}"] = getattr(bl, k)
    for k in sorted(PICK_MODEL_BUY_RULES):
        out[f"breakout_v1_pick_model.{k}"] = getattr(pm, k)
    return out


# strategy -> (the version this hash belongs to, the hash). A buy-rule constant change moves the hash: bump the
# version (a new registry row citing the change-log entry) AND re-pin here, in the same commit.
# The failing test prints the new hash.
PINNED_FINGERPRINT: dict = {BREAKOUT_V1: ("breakout_v1.5-narrow", "8189b528782a99f2")}

