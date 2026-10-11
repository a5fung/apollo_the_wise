"""#687 / #482 flip-day duty (2026-10-11) — PROOF that the depth-era change is byte-identical on
today's data: the #482 recorder's walk, origin/main's module vs this branch's, on the SAME
captured prod inputs (q2_replay_inputs.out — the 15 live MAGNA53 fills since 2026-08-16, their
day-0 minute bars, 400 days of daily rows, the mi_strategies overrides), every arm, every field.

No toggle row exists in prod (q1_state.out), no row is stamped `exit_rule`, so the branch MUST
reproduce origin/main's rows exactly. Also:
  * rule_eras (origin/main vs branch): exit_rules_as_of / exit_era_label swept over every date
    2026-07-01..2026-12-31 x {None, magna53, magna53_smallcap, magna53_lowcap, parabolic_short}
    — the dated record is None, so the labels and dicts must be identical everywhere;
  * the branch's re-walk vs the 144 STORED prod rows (informational — the stored rows were
    written on earlier nights; a settled arm must still agree on realized_r / final_reason /
    exit_session unless a daily row was rewritten since). RESULT (2026-10-11): 120 identical,
    14 different — every one of the 14 is an era-C fill whose stored follows-live rows were walked
    at the +2R / no-arm levels live at the time, while this probe re-walks each fill FRESH
    (written=(), no pinned levels) and so frames it at today's +8R / +3R — the documented
    "brand-new fill is framed by today's rule" path (#631, tests/test_631_era_framing_fallback.py).
    origin/main and the branch agree on all 14, which is the point of this file.

$0, offline, SELECT-only captures read from disk. Run from the repo root:
    python scripts/probes/_wk1011_depth_era/before_after_replay.py > scripts/probes/_wk1011_depth_era/before_after_replay.out
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))
_ET = ZoneInfo("America/New_York")
LAST_SESSION = date(2026, 10, 9)           # the last settled session in the capture
STAMP = {"rubric_version": "v4", "score_tier": "HIGH", "ep_score": 70.0, "judge_grade": "strong",
         "judge_tier": "A", "grade_engine_authority": "lattice", "setup_class": "ep",
         "baseline_floor_tier": "B", "alert_source": "live"}   # pass-through text; same for both


def _sections(path: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    cur, header = None, None
    for line in path.read_text().splitlines():
        if line.startswith("=== "):
            cur, header = line[4:].strip(), None
            out[cur] = []
            continue
        if cur is None or line.startswith("(") and line.endswith(" rows)") or line.endswith(" row)"):
            continue
        cells = line.split("\t")
        if header is None:
            header = cells
            continue
        out[cur].append(dict(zip(header, cells)))
    return out


def _f(s):
    return None if s in ("", None) else float(s)


def _ts(s):
    if not s:
        return None
    s = s.replace(" ", "T")
    if s.endswith("+00"):
        s = s[:-3] + "+00:00"
    return datetime.fromisoformat(s)


_TMP = Path(tempfile.mkdtemp(prefix="wk1011_depth_era_"))


def _load(name: str, src: str):
    """Import origin/main's module text under its own name (written to a temp dir, never into
    the repo — the branch's own module is imported normally beside it)."""
    p = _TMP / f"_{name}.py"
    p.write_text(src)
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    data = _sections(HERE / "q2_replay_inputs.out")
    trades = []
    for r in data["TRADES"]:
        trades.append({
            "id": int(r["id"]), "ticker": r["ticker"], "alert_date": date.fromisoformat(r["alert_date"]),
            "account_mode": r["account_mode"], "signal_type": r["signal_type"],
            "entry_attempt": int(r["entry_attempt"]) if r["entry_attempt"] else None,
            "status": r["status"], "entry_price": _f(r["entry_price"]), "entry_shares": _f(r["entry_shares"]),
            "orb_high": _f(r["orb_high"]), "orb_low": _f(r["orb_low"]), "hard_stop": _f(r["hard_stop"]),
            "regime": r["regime"] or None, "exits": json.loads(r["exits"] or "[]"),
            "partial_taken": r["partial_taken"] == "t", "total_pnl": _f(r["total_pnl"]),
            "pnl_attribution": r["pnl_attribution"] or None,
            "filled_at": _ts(r["filled_at"]), "closed_at": _ts(r["closed_at"]),
            "exit_rule": r["exit_rule"] or None,
        })
    minutes: dict[str, list[dict]] = {}
    for r in data["MINUTES"]:
        minutes.setdefault(r["ticker"], []).append(
            {"bar_time": _ts(r["bar_time"]), "open": _f(r["open"]), "high": _f(r["high"]),
             "low": _f(r["low"]), "close": _f(r["close"])})
    daily: dict[str, list[dict]] = {}
    for r in data["DAILY"]:
        daily.setdefault(r["ticker"], []).append(
            {"trade_date": date.fromisoformat(r["trade_date"]), "open_price": _f(r["open_price"]),
             "high_price": _f(r["high_price"]), "low_price": _f(r["low_price"]),
             "close": _f(r["close"]), "volume": _f(r["volume"])})
    overrides = [{"signal_type": r["signal_type"], "profit_trigger_r": _f(r["profit_trigger_r"]),
                  "breakeven_arm_r": _f(r["breakeven_arm_r"])} for r in data["OVERRIDES"]]
    stored = {(int(r["trade_id"]), r["arm"]): r for r in data["CF_ROWS"]}
    print(f"# inputs: {len(trades)} trades, {sum(map(len, minutes.values()))} minute bars, "
          f"{sum(map(len, daily.values()))} daily rows, {len(overrides)} overrides, {len(stored)} stored rows")
    assert all(t["exit_rule"] is None for t in trades), "a stamped row exists — this proof is for the no-toggle world"

    def make_conn():
        async def fetch(sql, *args):
            if "FROM mi_live_fill_counterfactuals WHERE trade_id" in sql:
                return []
            if "FROM mi_daily_closes" in sql:
                t, lo, hi = args[0], args[1], args[2]
                return [dict(r) for r in daily.get(t, []) if lo <= r["trade_date"] <= hi]
            if "FROM mi_intraday_bars" in sql:
                t, lo, hi = args[0], args[1], args[2]
                return [dict(r) for r in minutes.get(t, []) if lo <= r["bar_time"] <= hi]
            if "FROM mi_strategies" in sql:
                return [dict(r) for r in overrides]
            raise AssertionError(f"unexpected fetch: {sql[:80]}")

        async def fetchrow(sql, *args):
            if "FROM mi_ep_alerts" in sql:
                return dict(STAMP)
            raise AssertionError(f"unexpected fetchrow: {sql[:80]}")
        conn = MagicMock()
        conn.fetch, conn.fetchrow = fetch, fetchrow
        conn.execute = AsyncMock(side_effect=AssertionError("no writes expected"))
        return conn

    async def run(mod):
        inserts: dict[tuple, dict] = {}
        audits: list = []

        async def ins(fields):
            inserts[(fields["trade_id"], fields["arm"])] = dict(fields)
            return True

        async def audit(ev, summary, detail=""):
            audits.append((ev, summary))

        async def no_fallback(conn_, ticker, d):
            return None, None, None, None, None
        mod.insert_live_fill_counterfactual = ins
        mod.log_audit_event = audit
        mod.get_daily_bar_with_fallback = no_fallback
        out = {"population": 0, "fills_considered": 0, "arms_considered": 0, "written": 0,
               "settled": 0, "abstained": 0, "unscoreable": 0, "horizon": 0, "pending": 0, "errors": 0}
        conn = make_conn()
        ovr = {o["signal_type"]: {"profit_trigger_r": o["profit_trigger_r"],
                                  "breakeven_arm_r": o["breakeven_arm_r"]} for o in overrides}
        for t in trades:
            await mod._record_one_fill(conn, dict(t), LAST_SESSION, out, ovr)
        return inserts, audits, out

    main_src = subprocess.check_output(
        ["git", "show", "origin/main:agents/market_intelligence/live_fill_counterfactuals.py"],
        cwd=REPO, text=True)
    main_eras_src = subprocess.check_output(
        ["git", "show", "origin/main:agents/market_intelligence/rule_eras.py"], cwd=REPO, text=True)
    lfc_main = _load("lfc_origin_main", main_src)
    eras_main = _load("rule_eras_origin_main", main_eras_src)
    from agents.market_intelligence import live_fill_counterfactuals as lfc_branch
    from agents.market_intelligence import rule_eras as eras_branch

    # 1. rule_eras sweep — the dated record is None, so every date-only answer must be identical
    diffs = 0
    d = date(2026, 7, 1)
    while d <= date(2026, 12, 31):
        for sig in (None, "magna53", "magna53_smallcap", "magna53_lowcap", "parabolic_short"):
            if (eras_main.exit_rules_as_of(d, sig) != eras_branch.exit_rules_as_of(d, sig)
                    or eras_main.exit_era_label(d, sig) != eras_branch.exit_era_label(d, sig)):
                diffs += 1
                print(f"ERA DIFF {d} {sig}")
        d += timedelta(days=1)
    print(f"# rule_eras sweep 2026-07-01..2026-12-31 x 5 signal types: {diffs} difference(s)"
          f" (EXIT_SWITCHES main={len(eras_main.EXIT_SWITCHES)} branch={len(eras_branch.EXIT_SWITCHES)};"
          f" DEPTH_EXIT_LIVE_DATE={eras_branch.DEPTH_EXIT_LIVE_DATE})")

    # 2. the recorder: origin/main vs branch on identical inputs
    ins_a, aud_a, out_a = asyncio.run(run(lfc_main))
    ins_b, aud_b, out_b = asyncio.run(run(lfc_branch))
    print(f"# origin/main: {len(ins_a)} rows written, counters {out_a}")
    print(f"# branch     : {len(ins_b)} rows written, counters {out_b}")
    keys = sorted(set(ins_a) | set(ins_b))
    field_diffs = 0
    for k in keys:
        a, b = ins_a.get(k), ins_b.get(k)
        if a is None or b is None:
            field_diffs += 1
            print(f"ROW ONLY IN {'branch' if a is None else 'origin/main'}: {k}")
            continue
        for fld in sorted(set(a) | set(b)):
            if a.get(fld) != b.get(fld):
                field_diffs += 1
                print(f"FIELD DIFF {k} {fld}: main={a.get(fld)!r} branch={b.get(fld)!r}")
    print(f"# recorder before/after: {len(keys)} (trade, arm) rows compared field-by-field "
          f"({len(keys) and len(set().union(*[set(v) for v in ins_b.values()]))} fields each): "
          f"{field_diffs} difference(s); audit rows main={len(aud_a)} branch={len(aud_b)}")

    # 3. informational — the branch's re-walk vs the STORED prod rows (written on earlier nights)
    agree = disagree = 0
    for k, b in ins_b.items():
        s = stored.get(k)
        if s is None or s["outcome"] != "settled" or b["outcome"] != "settled":
            continue
        same = (abs(float(s["realized_r"]) - float(b["realized_r"])) < 1e-9
                and s["final_reason"] == b["final_reason"]
                and int(s["exit_session"] or 0) == int(b["exit_session"] or 0))
        if same:
            agree += 1
        else:
            disagree += 1
            print(f"STORED-vs-REWALK {k}: stored r={s['realized_r']} {s['final_reason']} s{s['exit_session']}"
                  f" | rewalk r={b['realized_r']} {b['final_reason']} s{b['exit_session']}")
    print(f"# informational: settled stored rows re-walked identically {agree}, differently {disagree}")
    return 0 if (diffs == 0 and field_diffs == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
