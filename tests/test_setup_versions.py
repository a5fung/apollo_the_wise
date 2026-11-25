"""Setup (buy-rule) versions — operator 2026-11-25 ("Go": stamp every list row and trade with a setup version,
bumped on every buy-rule change, and split /trades by it).

THE BUMP GATE: `test_a_buy_rule_constant_cannot_change_without_a_version_bump` fails when a buy-rule constant of
breakout v1 changes while the version does not. Fix = a new `SetupVersion` row in `setup_versions.py` citing the
change-log entry + the new hash in `PINNED_FINGERPRINT`, same commit as the SSoT change-log entry.
WHAT IT CANNOT SEE: a rule changed inside a function body with no constant moving (see `setup_versions.py`).
"""
from __future__ import annotations

import ast
import asyncio
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

import numpy as np
import pytest

from agents.market_intelligence import breakout_v1 as bv
from agents.market_intelligence import breakout_v1_list as bl
from agents.market_intelligence import setup_versions as sv
from agents.market_intelligence import trades_by_strategy as tbs
from agents.market_intelligence.broker import breakout_v1_entry as be
from agents.market_intelligence.broker import entry_pipeline as ep

REPO = Path(__file__).resolve().parents[1]
SID = sv.BREAKOUT_V1
NOW = "breakout_v1.5-narrow"


def _constants() -> dict:
    return sv.breakout_v1_rule_constants(bv, be, bl, bl.pm)


def _fingerprint() -> str:
    return sv.fingerprint_of(_constants())


# ── the registry ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_the_registry_is_ordered_and_the_last_row_is_the_current_version():
    vs = sv.versions_for(SID)
    assert [v.version for v in vs] == ["breakout_v1.0", "breakout_v1.1", "breakout_v1.2", "breakout_v1.3",
                                       "breakout_v1.4", NOW]
    assert sv.current_setup_version(SID) == NOW == vs[-1].version
    assert len({v.version for v in vs}) == len(vs)
    dated = [v.first_session for v in vs[:-1]]
    assert all(d is not None for d in dated), "only the newest version may be undated (reached by stamp only)"
    assert dated == sorted(dated) and len(set(dated)) == len(dated)
    assert [v.changed_on for v in vs] == sorted(v.changed_on for v in vs)
    assert all(v.first_session is None or v.first_session >= v.changed_on for v in vs)
    assert all(v.changes and v.short for v in vs)


def test_every_version_cites_change_log_headings_that_exist():
    lines = (REPO / sv.SSOT_FILE[SID]).read_text().splitlines()
    log = lines[lines.index("## Change log"):]
    cited = set()
    for v in sv.versions_for(SID):
        assert v.changes[0][0].startswith(f"### {v.changed_on.isoformat()} — "), v.version
        for heading, what in v.changes:
            assert heading.startswith("### 2026-") and what
            hits = [ln for ln in log if ln.startswith(heading)]
            assert len(hits) == 1, f"{v.version}: {heading!r} matches {len(hits)} change-log headings"
            cited.add(hits[0])
    assert len(cited) == sum(len(v.changes) for v in sv.versions_for(SID)), "one heading cited twice"


# The book's 23 paper trades through 11-23 (scripts/probes/_vor_1125/q3.out): three rule sets, not one.
TRADES_THROUGH_1123 = {
    date(2026, 11, 2): (1, "breakout_v1.0"),
    date(2026, 11, 10): (4, "breakout_v1.1"),
    date(2026, 11, 17): (6, "breakout_v1.4"), date(2026, 11, 18): (4, "breakout_v1.4"),
    date(2026, 11, 19): (1, "breakout_v1.4"), date(2026, 11, 20): (3, "breakout_v1.4"),
    date(2026, 11, 23): (4, "breakout_v1.4"),
}


def test_the_23_unstamped_paper_trades_map_to_three_versions_by_date():
    assert sum(n for n, _ in TRADES_THROUGH_1123.values()) == 23
    for d, (_, want) in TRADES_THROUGH_1123.items():
        assert sv.setup_version_as_of(SID, d) == want, d
    assert sv.setup_version_as_of(SID, date(2026, 11, 1)) is None            # before the first paper session
    assert sv.setup_version_as_of(SID, None) is None
    # the two versions no paper trade was bought under still own their sessions
    assert sv.setup_version_as_of(SID, date(2026, 11, 12)) == "breakout_v1.2"
    assert sv.setup_version_as_of(SID, date(2026, 11, 13)) == "breakout_v1.3"
    assert sv.setup_version_as_of(SID, date(2026, 11, 16)) == "breakout_v1.3"


def test_the_undeployed_narrow_version_is_reached_by_stamp_only():
    """WOULD FAIL IF an unstamped trade (bought before the narrow deploy, on any list name) were labelled narrow:
    that would mix the two arms he asked to compare."""
    far = date(2027, 1, 4)
    assert sv.versions_for(SID)[-1].first_session is None
    assert sv.setup_version_as_of(SID, far) == "breakout_v1.4"
    assert sv.setup_version_for_row(SID, None, far) == "breakout_v1.4"
    assert sv.setup_version_for_row(SID, NOW, date(2026, 11, 27)) == NOW                 # the stamp wins
    assert sv.setup_version_for_row(SID, "breakout_v1.9-x", date(2026, 11, 2)) == "breakout_v1.9-x"


def test_a_strategy_without_a_registry_is_not_versioned():
    for sig in ("magna53", "magna53_smallcap", "9m_day2", None, ""):
        assert sv.current_setup_version(sig) is None and sv.versions_for(sig) == ()
        assert sv.setup_version_for_row(sig, None, date(2026, 11, 20)) is None
    assert sv.display_name(NOW) == "v1.5-narrow" and sv.display_name("magna53_v2") == "magna53_v2"


# ── the bump gate ────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_buy_rule_constant_cannot_change_without_a_version_bump():
    version, pinned = sv.PINNED_FINGERPRINT[SID]
    assert version == sv.current_setup_version(SID), "the pinned hash must belong to the current version"
    assert _fingerprint() == pinned, (
        "a breakout v1 BUY-RULE constant changed (breakout_v1.py / broker/breakout_v1_entry.py / the list order). "
        "Bump the setup version: add a SetupVersion row to setup_versions.BREAKOUT_V1_VERSIONS citing the new "
        "change-log entry in docs/setups/consolidation_breakout.md, then set PINNED_FINGERPRINT to "
        f"(<new version>, {_fingerprint()!r}). Re-pinning under the SAME version is only for a constant "
        "that is not a buy rule — then classify it in setup_versions instead.")


@pytest.mark.parametrize("mod,name,value", [
    (bv, "ADR_MIN", 0.05), (bv, "NARROW_MAX", 0.7), (bv, "PRIOR_MOVE_MIN", 0.3), (bv, "CTX_UNDER_SMA50_MAX", -0.05),
    (bv, "ENFORCED_SHAPE_GATES", ("tight10",)), (bv, "_BASKET", ()), (be, "VOLUME_PACE_GATE", True),
    (be, "OR_MINUTES", 15), (be, "BREAK_LOOKBACK_MINUTES", 5), (bl, "DEFAULT_RANKING", "order_score"),
    (bl.pm, "INTERCEPT", -1.0), (bl.pm, "YEAR", 250), (bl.pm, "HISTORY_SESSIONS", 250),
    (bl, "PREFILTER_DOLLAR_VOL", 1.0), (bl, "HISTORY_SESSIONS", 150), (be, "DEFAULT_RANKED_BY", "x"),
])
def test_the_fingerprint_moves_when_a_buy_rule_moves(monkeypatch, mod, name, value):
    before = _fingerprint()
    assert getattr(mod, name) != value
    monkeypatch.setattr(mod, name, value)
    assert _fingerprint() != before


@pytest.mark.parametrize("mod,name,value", [
    (bv, "VOL_WINDOW_50", 60), (bv, "SHAPE_TIGHT_ADR_MAX", 9.0), (be, "CANCEL_POLL_S", 9.0),
    (be, "BARS_CHUNK_MAX", 50), (bl, "MESSAGE_TOP_N", 3), (bl, "GRADE_CUTOFFS", ()),
])
def test_the_fingerprint_ignores_what_is_not_a_buy_rule(monkeypatch, mod, name, value):
    before = _fingerprint()
    monkeypatch.setattr(mod, name, value)
    assert _fingerprint() == before


def _defined_constants(mod) -> set:
    """Public UPPERCASE names ASSIGNED at the module's top level (imports excluded) — derived from the source."""
    out = set()
    for node in ast.parse(Path(mod.__file__).read_text()).body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        for t in targets:
            if isinstance(t, ast.Name) and t.id.isupper() and not t.id.startswith("_"):
                out.add(t.id)
    return out


def test_every_entry_constant_is_classified_buy_rule_or_not():
    """A NEW constant in the entry module fails here until it is named a buy rule (hashed) or not one."""
    defined = _defined_constants(be)
    assert not (sv.ENTRY_BUY_RULES & sv.ENTRY_NOT_BUY_RULES)
    assert defined - sv.ENTRY_BUY_RULES - sv.ENTRY_NOT_BUY_RULES == set(), "classify it in setup_versions.py"
    assert (sv.ENTRY_BUY_RULES | sv.ENTRY_NOT_BUY_RULES) - defined == set(), "a classified name no longer exists"


def test_every_rules_module_constant_is_hashed_or_named_out():
    """breakout_v1.py is the rules module: every constant is hashed unless named out. The SHAPE readings are out
    only because none is enforced — enforcing one moves ENFORCED_SHAPE_GATES, which IS hashed."""
    defined = _defined_constants(bv)
    hashed = {k.split(".", 1)[1] for k in _constants() if k.startswith("breakout_v1.")}
    out = {k for k in defined if k in sv.BV_NOT_BUY_RULES or k.startswith(sv.BV_NOT_BUY_RULE_PREFIX)}
    assert defined - hashed - out == set(), "a breakout_v1 constant the hash cannot represent (not a plain value)"
    assert bv.ENFORCED_SHAPE_GATES == () and "ENFORCED_SHAPE_GATES" in hashed
    assert {"ADR_MIN", "NARROW_MAX", "NARROW_WINDOW", "RS_MIN", "GATES", "CONTEXT_GATES", "LEVEL_WICK_MIN"} <= hashed
    assert sv.BV_NOT_BUY_RULES <= defined
    for name in ("FEATURES", "INTERCEPT", "COEF", "RAW_FEATURES", "HALF_FILL"):
        assert f"breakout_v1_pick_model.{name}" in _constants()


def test_every_list_and_pick_model_constant_is_classified_buy_rule_or_not():
    """Same classify-or-fail as the entry module: a NEW constant in the list job or the pick model fails here until
    it is named a buy rule (hashed) or not one."""
    for mod, buy, not_buy in ((bl, sv.LIST_BUY_RULES, sv.LIST_NOT_BUY_RULES),
                              (bl.pm, sv.PICK_MODEL_BUY_RULES, sv.PICK_MODEL_NOT_BUY_RULES)):
        defined = _defined_constants(mod)
        assert not (buy & not_buy)
        assert defined - buy - not_buy == set(), f"classify it in setup_versions.py ({mod.__name__})"
        assert (buy | not_buy) - defined == set(), "a classified name no longer exists"


def test_the_extra_list_and_pick_model_buy_constants_are_hashed():
    c = _constants()
    for k in ("breakout_v1_pick_model.YEAR", "breakout_v1_pick_model.HISTORY_SESSIONS",
              "breakout_v1_list.PREFILTER_DOLLAR_VOL", "breakout_v1_list.HISTORY_SESSIONS",
              "breakout_v1_entry.DEFAULT_RANKED_BY"):
        assert k in c, k
    assert "DEFAULT_RANKED_BY" in sv.ENTRY_BUY_RULES and "DEFAULT_RANKED_BY" not in sv.ENTRY_NOT_BUY_RULES


def test_the_registry_strategy_id_is_the_one_the_database_layer_uses():
    from agents.market_intelligence import db
    assert sv.BREAKOUT_V1 == db.BREAKOUT_V1_STRATEGY_ID


# ── the stamps ───────────────────────────────────────────────────────────────────────────────────────────────────

class _Bars:
    def __init__(self, n):
        self.h = self.l = self.c = np.ones(n)

    def __len__(self):
        return len(self.c)


def test_every_nightly_list_row_carries_the_current_version_in_its_gates(monkeypatch):
    g = {"ok": True, "failed": [], "level": 10.0, "vol_bar": 1e6, "adr20": 0.05, "close": 9.9, "gates": {},
         "narrow": {"pass": True}}
    monkeypatch.setattr(bl.bv, "v1_gates", lambda bars, D, rs_best, cidx: dict(g))
    monkeypatch.setattr(bl.bv, "order_inputs", lambda bars, D, adr: {"runup6m_adr": 5.0, "spread10_adr": 1.0})
    members = [{"ticker": t, "security_type": "CS", "listable": True, "history": True, "bars": _Bars(200),
                "cidx": None} for t in ("AAA", "BBB")]
    rows, _fails, n = bl.evaluate_members(members, [90.0, 80.0], date(2026, 11, 27))
    assert n == 2 and [r["gates"]["setup_version"] for r in rows] == [NOW, NOW]
    assert rows[0]["gates"]["narrow"] == {"pass": True} and rows[0]["level"] == 10.0      # the row is otherwise as before
    from agents.market_intelligence import db
    assert "gates" in db.BV1_LIST_COLS and "setup_version" not in db.BV1_LIST_COLS          # jsonb, no new list column


def _funnel(monkeypatch):
    """The REAL submit_trade_entry over the #461 FakeDB; records every setup-version stamp it issues."""
    import tests.test_461_cap_toctou_race as t461
    stamps, sqls = [], []
    orig = t461.FakeConn.execute

    async def _execute(self, sql, *args):
        s = " ".join(sql.split())
        sqls.append(s)
        if "SET setup_version" in s:
            assert s == "UPDATE mi_live_trades SET setup_version = $2 WHERE id = $1"
            stamps.append({"trade_id": args[0], "version": args[1], "inside_txn_lock": bool(self._xact_locks)})
            for r in self.db.rows:
                if r["id"] == args[0]:
                    r["setup_version"] = args[1]
            return "UPDATE 1"
        if "SET exit_rule" in s:
            return "UPDATE 1"
        return await orig(self, sql, *args)

    monkeypatch.setattr(t461.FakeConn, "execute", _execute)
    return t461, stamps, sqls


@pytest.mark.asyncio
async def test_a_magna53_entry_gets_no_version_stamp_and_no_extra_statement(monkeypatch):
    """The stamp is a pure lookup: None for MAGNA53, so the shared funnel issues nothing new for it."""
    from agents.market_intelligence.broker import order_manager as om
    t461, stamps, sqls = _funnel(monkeypatch)
    fdb = t461.FakeDB()
    t461._wire(monkeypatch, fdb)
    monkeypatch.setattr(om, "_magna53_depth_exit_enabled", AsyncMock(return_value=False))
    res = await asyncio.wait_for(t461._submit("KOD"), timeout=10)
    assert res["action"] == "auto_entered", res
    assert stamps == [] and not any("setup_version" in s for s in sqls)
    assert next(r for r in fdb.rows if r["ticker"] == "KOD").get("setup_version") is None


@pytest.mark.asyncio
async def test_a_breakout_paper_entry_is_stamped_with_the_current_version_in_its_own_transaction(monkeypatch):
    from agents.market_intelligence.broker import live_tracker as lt
    t461, stamps, _ = _funnel(monkeypatch)
    fdb = t461.FakeDB()
    t461._wire(monkeypatch, fdb, phase="paper", live_real_enabled=False)
    monkeypatch.setattr(ep, "get_pool", AsyncMock(return_value=t461.FakePool(fdb)))
    monkeypatch.setattr(lt, "get_pool", AsyncMock(return_value=t461.FakePool(fdb)))

    async def _spec(alert_ctx, orb_bar, regime, account_mode):
        return ({"orb_high": 10.0, "orb_low": 9.8, "entry_price": 10.0, "stop_loss_price": 9.8, "shares": 100,
                 "position_size": 1000.0, "risk_dollars": 20.0, "risk_per_share": 0.2}, None)

    async def _bar(*a):
        return {"open": 9.9, "high": 9.95, "low": 9.8}

    today = date(2026, 11, 27)
    res = await ep.submit_trade_entry(
        alert_context={"ticker": "BRKO", "alert_date": today}, spec_builder=_spec, regime_record=None,
        strategy_label="Breakout v1 (paper)", signal_type=SID, today=today, fade_midpoint_ratio=None,
        aggregate_skips=True, require_account_mode="paper", page_cap_plus_one=False, bar_fetcher=_bar)
    assert res["action"] == ep.ACTION_AUTO_ENTERED, res
    row = fdb.rows[-1]
    assert row["account_mode"] == "paper" and row["signal_type"] == SID and row["setup_version"] == NOW
    assert len(stamps) == 1 and stamps[0]["inside_txn_lock"], "the stamp must land atomically with the row's insert"


def test_the_trade_stamp_is_prepared_at_the_deploy_gate_and_has_one_allowed_writer():
    """The deploy gate PREPAREs the funnel's exact stamp statement against the real schema (a deploy whose database
    lacks the column fails there, not on the first paper buy), and the column has the same single writer as
    exit_rule."""
    from scripts import audit_column_writes as acw
    from scripts import preflight_db_updates as pre
    prepared = {" ".join(sql.split()) for _label, sql in pre.TRADE_LIFECYCLE_UPDATES}
    assert "UPDATE mi_live_trades SET setup_version = $2 WHERE id = $1" in prepared
    assert acw.ALLOWED_WRITERS["setup_version"] == acw.ALLOWED_WRITERS["exit_rule"]


# ── /trades: the split by version ────────────────────────────────────────────────────────────────────────────────

def _row(d, pnl, r, *, stamp=None, status="closed", remaining=0):
    return {"alert_date": d, "setup_version": stamp, "status": status, "total_pnl": pnl,
            "remaining_shares": remaining, "r": r}


# the book through 11-23 (dollars from scripts/probes/_vor_1125/q3.out; R illustrative) + two stamped narrow trades
VERSION_ROWS = (
    [_row(date(2026, 11, 2), 150.0, 0.3)]
    + [_row(date(2026, 11, 10), p, r) for p, r in ((-322.0, -0.6), (-1082.0, -1.9), (-904.0, -1.6), (-711.0, -1.3))]
    + [_row(date(2026, 11, 17), p, r) for p, r in ((-445.0, -0.9), (-529.0, -1.0), (-365.0, -0.7), (-536.0, -1.0),
                                                   (-550.0, -1.0), (225.0, 0.5))]
    + [_row(date(2026, 11, 23), -271.0, -0.5), _row(date(2026, 11, 24), 90.0, None, status="filled", remaining=40)]
    + [_row(date(2026, 11, 27), 410.0, 0.8, stamp=NOW), _row(date(2026, 11, 30), 0.0, None, stamp=NOW,
                                                             status="filled", remaining=120)]
)


class _VConn:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    async def fetch(self, sql, *args):
        self.calls.append((sql, args))
        return self.rows


def _versions(rows=VERSION_ROWS, sig=SID, book="paper"):
    conn = _VConn(rows)
    return asyncio.run(tbs.load_version_stats(conn, book, sig)), conn


def test_the_strategy_page_splits_breakout_by_version_newest_first():
    stats, conn = _versions()
    text = tbs.render_versions(stats)
    assert text.splitlines() == [
        "*By rule version* (the buy rules each trade was bought under)",
        "  `v1.5-narrow` narrow only · now (Nov 27–30) · 1 closed +$410 · win 100% · avg +0.8R · 1 open",
        "  `v1.4` context checks (Nov 17–24) · 7 closed -$2,471 · win 14% · avg -0.7R · 1 open",
        "  `v1.1` list rebuilt (Nov 10) · 4 closed -$3,019 · win 0% · avg -1.4R",
        "  `v1.0` first rules (Nov 2) · 1 closed +$150 · win 100% · avg +0.3R",
    ]
    (sql, args), = conn.calls
    assert args == ("paper", [SID])                                   # the book is BOUND, first (dual-account)
    assert "account_mode = $1" in sql and "ANY($2::text[])" in sql and "GROUP BY" not in sql


def test_the_version_lines_add_up_to_the_strategy_line():
    stats, _ = _versions()
    closed = [r for r in VERSION_ROWS if r["status"] == "closed"]
    assert sum(g["closed_n"] for g in stats) == len(closed)
    assert sum(g["realized"] for g in stats) == pytest.approx(sum(r["total_pnl"] for r in closed))
    assert sum(g["wins"] for g in stats) == sum(1 for r in closed if r["total_pnl"] > 0)
    assert sum(g["open_n"] for g in stats) == 2
    # the same R rule as the strategy line's SQL (a trade with no risk figure is left out of the average)
    assert "NULLIF(COALESCE(NULLIF(risk_dollars_actual, 0), NULLIF(risk_dollars, 0)), 0)" in " ".join(
        tbs._VERSION_ROWS_SQL.split())
    assert "NULLIF(COALESCE(NULLIF(risk_dollars_actual, 0), NULLIF(risk_dollars, 0)), 0)" in " ".join(
        tbs._STATS_SQL.split())


def test_the_current_version_shows_before_its_first_trade_and_other_strategies_get_no_split():
    stats, _ = _versions(rows=[r for r in VERSION_ROWS if r["setup_version"] is None])
    assert tbs.render_versions(stats).splitlines()[1] == "  `v1.5-narrow` narrow only · now · 0 closed"
    stats, conn = _versions(sig="magna53", book="live")
    assert stats == [] and conn.calls == [] and tbs.render_versions(stats) == ""       # no query, no block
    stats, _ = _versions(rows=[_row(date(2026, 11, 20), -50.0, -0.1, stamp="breakout_v9-test"),
                               _row(date(2026, 10, 20), -10.0, -0.1)])
    assert [g["name"] for g in stats] == ["v1.5-narrow", "v9-test", "before v1"]       # unknown stamp kept, never dropped
    stats, _ = _versions(rows=list(VERSION_ROWS) + [_row(date(2026, 11, 20), -50.0, -0.1, stamp="breakout_v9-test")])
    assert [g["name"] for g in stats] == ["v1.5-narrow", "v1.4", "v1.1", "v1.0", "v9-test"]   # ... and under the known ones
