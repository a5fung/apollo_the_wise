"""Breakout v1 PAPER phase 1 — the nightly list job (B2), its one Telegram message and /bgrade (B3).

The job runs against in-memory fakes of its five DB reads/writes and the sender (no database, no network). The market:
the operator's ZCSH bars (stored mi_daily_closes pull, 2026-03-02..2026-10-28; v1 passes every shape rule at 10-28),
two copies of them wearing a leveraged fund's name and NO name, plus 60 common-stock fillers whose returns sit below
ZCSH's so ZCSH tops the night's RS cross-section. THE LINE is pinned at the end: no broker import beyond the pure
exit math `cb` already carries, nothing loaded by the execution image, no trade table in the module's SQL.
"""
from __future__ import annotations

import asyncio
import csv
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from agents.market_intelligence import breakout_v1 as bv
from agents.market_intelligence import breakout_v1_list as bl
from agents.market_intelligence import consolidation_breakout as cb

REPO = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures" / "breakout_v1_parity" / "operator_examples_bars.csv"
TODAY = date(2026, 10, 28)


def _zcsh_rows():
    return [r for r in csv.DictReader(open(FIX)) if r["ticker"] == "ZCSH"]


def build_market(n_fill: int = 60, *, seed: int = 7):
    """(calendar, bar rows (ticker, date, o, h, l, c, v) sorted by (ticker, date), security types {t: (type, name)})."""
    z = _zcsh_rows()
    cal = [date.fromisoformat(r["date"]) for r in z]
    rows = []
    for r in z:
        rows.append(("ZCSH", date.fromisoformat(r["date"]), float(r["o"]), float(r["h"]), float(r["l"]),
                     float(r["c"]), float(r["v"])))
    rng = np.random.default_rng(seed)
    # ZLEV / ZNON: funds the TYPE rule keeps off the list. Under his 2026-10-29 ruling (a) they still sit in the RS
    # pool, so they are drawn flat (a ZCSH clone would tie it at the top of a 63-name pool and push it under 98).
    for t in ("ZLEV", "ZNON"):
        px = 40.0
        for d in cal:
            px *= float(np.exp(rng.normal(0.0, 0.01)))
            rows.append((t, d, px, px * 1.01, px * 0.99, px, 1_000_000.0))
    for k in range(n_fill):
        t = "F" + "".join(chr(65 + (k // 26 ** j) % 26) for j in range(3))
        px = 50.0
        for d in cal:
            px *= float(np.exp(rng.normal(0.0, 0.01)))
            rows.append((t, d, px, px * 1.01, px * 0.99, px, 1_000_000.0))
    rows.sort(key=lambda r: (r[0], r[1]))
    types = {"ZCSH": ("ETV", "The Zcash ETF"), "ZLEV": ("ETV", "ProShares Ultra Zcash"), "ZNON": ("ETV", None)}
    types.update({r[0]: ("CS", None) for r in rows if r[0].startswith("F")})
    return cal, rows, types


class Fakes:
    def __init__(self, monkeypatch, *, cal=None, rows=None, types=None, send_ok=True, universe_exc=None):
        c0, r0, t0 = build_market()
        self.cal, self.rows, self.types = cal or c0, rows if rows is not None else r0, types or t0
        self.lists, self.audit, self.sent = {}, [], []
        self.universe_exc, self.send_ok = universe_exc, send_ok

        async def cal_f(upto, limit=400):
            return [d for d in self.cal if d <= upto][-limit:]

        async def uni_f(today, start, liq_start, *, min_price, prefilter_dollar_vol):
            assert min_price == bv.MIN_PRICE and prefilter_dollar_vol == 0.7 * bv.MIN_DOLLAR_VOL
            if self.universe_exc:
                raise self.universe_exc
            return [r for r in self.rows if start <= r[1] <= today]

        async def types_f(tickers):
            return {t: self.types[t] for t in tickers if t in self.types}

        async def splits_f(since=None, upto=None):
            return []

        async def replace_f(scan_date, rows):
            self.lists[scan_date] = [dict(r) for r in rows]
            return len(rows)

        async def audit_f(event, summary, detail=""):
            self.audit.append((event, summary, json.loads(detail) if detail else None))

        async def send_f(text, *a, **k):
            self.sent.append(text)
            return self.send_ok

        monkeypatch.setattr(bl, "cb_get_calendar", cal_f)
        monkeypatch.setattr(bl, "cb_get_universe_bars", uni_f)
        monkeypatch.setattr(bl, "bv1_get_security_types_named", types_f)
        monkeypatch.setattr(bl, "get_unapplied_splits", splits_f)
        monkeypatch.setattr(bl, "bv1_replace_list", replace_f)
        monkeypatch.setattr(bl, "log_audit_event", audit_f)
        from agents.market_intelligence import briefing
        monkeypatch.setattr(briefing, "send_telegram_message", send_f)


def test_the_night_lists_zcsh_only_and_keeps_out_the_leveraged_and_unnamed_funds(monkeypatch):
    f = Fakes(monkeypatch)
    out = asyncio.run(bl.run_breakout_v1_list(TODAY))
    rows = f.lists[TODAY]
    assert [r["ticker"] for r in rows] == ["ZCSH"]
    r = rows[0]
    assert r["list_rank"] == 1 and r["security_type"] == "ETV" and r["rs_best"] >= 98
    assert round(r["level"], 2) == 35.13 and round(r["vol_bar"]) == 1_922_869
    g = r["gates"]
    assert g["ok"] is True and g["failed"] == [] and all(v["pass"] for v in g["gates"].values())
    json.dumps(g, allow_nan=False)
    assert out["funds_kept"] == 1 and out["funds_excluded"] == 2 and out["funds_excluded_no_name"] == 1
    assert out["fund_excluded_tickers"] == {"fund_leveraged_or_inverse": ["ZLEV"], "fund_no_name": ["ZNON"]}
    assert out["universe_n"] == 63 and out["listable_n"] == 61                # ruling (a): the two funds are ranked, not listed
    assert out["passing"] == 1 and out["written"] == 1
    assert out["gate_fails"]["prior_move"] == 60                       # the flat fillers have no prior move
    ev = [a for a in f.audit if a[0] == "breakout_v1_list_run"]
    assert len(ev) == 1 and ev[0][2]["passing"] == 1 and not [a for a in f.audit if a[0].endswith("_error")]
    assert len(f.sent) == 1 and out["message"] == "sent"
    from agents.market_intelligence.constants import is_paper_message, mode_prefix
    assert f.sent[0].startswith(mode_prefix("paper")) and is_paper_message(f.sent[0])
    assert "ZCSH" in f.sent[0] and "35.13" in f.sent[0] and "/bgrade" in f.sent[0]


def test_a_rerun_is_idempotent(monkeypatch):
    f = Fakes(monkeypatch)
    asyncio.run(bl.run_breakout_v1_list(TODAY))
    first = json.dumps(f.lists[TODAY], default=str, sort_keys=True)
    asyncio.run(bl.run_breakout_v1_list(TODAY))
    assert json.dumps(f.lists[TODAY], default=str, sort_keys=True) == first


def test_an_empty_night_sends_nothing_but_writes_the_audit_row(monkeypatch):
    cal, rows, types = build_market()
    rows = [r for r in rows if r[0] != "ZCSH"]
    f = Fakes(monkeypatch, cal=cal, rows=rows, types=types)
    out = asyncio.run(bl.run_breakout_v1_list(TODAY))
    assert f.lists[TODAY] == [] and f.sent == [] and out["message"] == "not_needed"
    assert [a[0] for a in f.audit] == ["breakout_v1_list_run"]


def test_no_spy_bar_today_skips(monkeypatch):
    f = Fakes(monkeypatch)
    out = asyncio.run(bl.run_breakout_v1_list(date(2026, 10, 29)))
    assert out["skipped"] == "no_spy_bar_for_today" and f.lists == {} and f.sent == []
    assert f.audit[0][0] == "breakout_v1_list_run" and "skipped" in f.audit[0][1]


def test_a_failed_send_is_counted_not_raised(monkeypatch):
    f = Fakes(monkeypatch, send_ok=False)
    out = asyncio.run(bl.run_breakout_v1_list(TODAY))
    assert out["message"] == "send_failed" and f.audit[-1][2]["message"] == "send_failed"


def test_a_crash_writes_the_audit_row_then_raises(monkeypatch):
    f = Fakes(monkeypatch, universe_exc=RuntimeError("db down"))
    with pytest.raises(RuntimeError):
        asyncio.run(bl.run_breakout_v1_list(TODAY))
    assert f.audit and f.audit[-1][0] == "breakout_v1_list_run" and "db down" in f.audit[-1][1]
    assert f.sent == []


def test_the_budget_fails_open_with_an_error_row(monkeypatch):
    f = Fakes(monkeypatch)

    async def slow(*a, **k):
        await asyncio.sleep(5)
    monkeypatch.setattr(bl, "cb_get_universe_bars", slow)
    monkeypatch.setattr(bl, "BUDGET_S", 0.05)
    out = asyncio.run(bl.run_breakout_v1_list(TODAY))
    assert out["timed_out"] is True and f.sent == []
    assert [a[0] for a in f.audit] == ["breakout_v1_list_error", "breakout_v1_list_run"]


def test_the_rs_ranking_pool_is_every_security_at_the_floors_and_only_admitted_types_are_listable():
    """PINS the RS denominator the 17:55 job ranks against — HIS RULING 2026-10-29 ("Ok a"): EVERY security above
    $2 / $5M (funds and ETFs included), the pool the approved 2020 check ranked against (12 of 24; the stocks-only pool
    read 10 of 24). The TYPE rule decides only who is LISTABLE: an ETF or a leveraged fund is ranked, never listed."""
    n = 130
    days = [date(2026, 1, 1).fromordinal(date(2026, 1, 1).toordinal() + k) for k in range(n)]
    cidx = np.arange(n, dtype=np.int64)

    def series(gain):  # a straight line from 10 to 10*(1+gain), $10M a day
        c = np.linspace(10.0, 10.0 * (1.0 + gain), n)
        return (cb.daily_bars_from_arrays(days, c, c * 1.01, c * 0.99, c, np.full(n, 1_000_000.0)), cidx)

    gains = {"STKA": 0.50, "ADRB": 0.40, "UNKN": 0.30, "GOLD": 0.20, "ETFX": 3.00, "LEVF": 2.00, "ZERO": 0.10}
    types = {"STKA": ("CS", None), "ADRB": ("ADRC", None), "GOLD": ("ETV", "SPDR Gold Shares"),
             "ETFX": ("ETF", "Some Momentum ETF"), "LEVF": ("ETV", "ProShares Ultra Silver"), "ZERO": ("CS", None)}
    out = bl.scan_members({t: series(g) for t, g in gains.items()}, today_ci=n - 1, types=types, unapplied=set())
    pool = [m["ticker"] for m in out["members"]]
    assert sorted(pool) == sorted(gains)                                      # every type at the floors is ranked
    listable = sorted(m["ticker"] for m in out["members"] if m["listable"])
    assert listable == ["ADRB", "GOLD", "STKA", "UNKN", "ZERO"]               # ETFX (ETF) and LEVF (leveraged) never listed
    assert out["counts"]["rank_only_type_other"] == 1 and out["counts"]["rank_only_fund_leveraged_or_inverse"] == 1
    rs_best, _, _, _ = cb.cross_section_one_date([m["r21"] for m in out["members"]],
                                                 [m["r63"] for m in out["members"]],
                                                 [m["r126"] for m in out["members"]], [None] * len(pool))
    got = dict(zip(pool, rs_best))
    # STKA sits third of seven — ranked against the two funds that out-ran it, exactly the untyped percentile
    untyped = cb.percentile_ranks([bv.rs_returns_contiguous(series(g)[0], n - 1, cidx)[1] for g in gains.values()])
    assert got["STKA"] == pytest.approx(dict(zip(gains, untyped))["STKA"])
    assert got["STKA"] < max(got.values())
    # a pool-only member never reaches the gates, whatever its strength
    rows, fails, n_eval = bl.evaluate_members(out["members"], rs_best, TODAY)
    assert {r["ticker"] for r in rows}.isdisjoint({"ETFX", "LEVF"}) and n_eval <= len(listable)


def test_format_list_message_caps_and_is_none_when_empty():
    assert bl.format_list_message(TODAY, []) is None
    rows = bl.rank_rows([{"ticker": f"T{k:02d}"[:5], "level": 10.0 + k, "rs_best": 98.0 + k / 100} for k in range(45)])
    msg = bl.format_list_message(TODAY, rows)
    assert "45 names" in msg and "and 5 more" in msg and rows[0]["rs_best"] == max(r["rs_best"] for r in rows)


# ── /bgrade ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_parse_bgrade():
    assert bl.parse_bgrade("/bgrade") == {"list": True}
    assert bl.parse_bgrade("/bgrade zcsh a+ clean surf, tight") == {
        "list": False, "ticker": "ZCSH", "grade": "A+", "note": "clean surf, tight"}
    assert bl.parse_bgrade("/bgrade ODD skip")["grade"] == "skip"
    assert bl.parse_bgrade("/bgrade ODD") is None
    assert bl.parse_bgrade("/bgrade ODD D") is None
    assert bl.parse_bgrade("/bgrade BRK.B A") is None


def _fake_agent():
    fake = MagicMock()
    fake._ok = lambda request, *, result: result
    return fake


def test_bgrade_writes_the_latest_list_night_and_confirms_in_one_line(monkeypatch):
    from agents.market_intelligence import db
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    seen = {}

    async def latest(t):
        return date(2026, 10, 28) if t == "ZCSH" else None

    async def upsert(d, t, g, n):
        seen["row"] = (d, t, g, n)
    monkeypatch.setattr(db, "bv1_latest_list_date_for", latest)
    monkeypatch.setattr(db, "bv1_upsert_grade", upsert)
    req = MagicMock()
    req.task = "/bgrade zcsh A clean"
    out = asyncio.run(MarketIntelligenceAgent._handle_bgrade_command(_fake_agent(), req))
    assert seen["row"] == (date(2026, 10, 28), "ZCSH", "A", "clean")
    assert "\n" not in out and "ZCSH" in out and "2026-10-28" in out
    req.task = "/bgrade ODD A"
    seen.clear()
    out = asyncio.run(MarketIntelligenceAgent._handle_bgrade_command(_fake_agent(), req))
    assert "not on any breakout v1 list" in out and not seen


def test_bare_bgrade_lists_the_ungraded(monkeypatch):
    from agents.market_intelligence import db
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    asked = {}

    async def ungraded(n):
        asked["n"] = n
        return [{"scan_date": date(2026, 10, 28), "ticker": "ZCSH", "level": 35.13, "rs_best": 99.1, "list_rank": 1}]
    monkeypatch.setattr(db, "bv1_ungraded", ungraded)
    req = MagicMock()
    req.task = "/bgrade"
    out = asyncio.run(MarketIntelligenceAgent._handle_bgrade_command(_fake_agent(), req))
    assert asked["n"] == 5 and "ZCSH" in out and "1 ungraded name" in out


def test_bgrade_is_in_all_three_places():
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    fake = MagicMock()
    fake._handle_bgrade_command = AsyncMock(return_value="ok")
    req = MagicMock()
    req.task = "/bgrade ZCSH A"
    assert asyncio.run(MarketIntelligenceAgent._handle_slash_command(fake, req)) == "ok"
    # the BotCommand + CommandHandler half: the deploy gate's own parser (scripts/preflight_command_parity.py)
    from scripts.preflight_command_parity import TELEGRAM_FILE, parse_bot_commands, parse_command_handlers
    text = TELEGRAM_FILE.read_text(encoding="utf-8")
    assert "bgrade" in parse_bot_commands(text) and "bgrade" in parse_command_handlers(text)[1]
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "preflight_command_parity.py")],
                       capture_output=True, text=True, cwd=REPO)
    assert r.returncode == 0, r.stdout + r.stderr


# ── registration + THE LINE ─────────────────────────────────────────────────────────────────────────────────
def test_the_job_is_intelligence_owned_at_1755_mon_fri(monkeypatch):
    from agents.market_intelligence import scheduler as sched
    from tests.test_job_partition import _CapturingScheduler
    assert "breakout_v1_list" in sched.INTELLIGENCE_OWNED_JOB_IDS
    assert "breakout_v1_list" not in sched.EXECUTION_OWNED_JOB_IDS
    monkeypatch.setattr(sched, "AsyncIOScheduler", _CapturingScheduler)
    holder = {}
    real = sched._apply_role_partition

    def spy(scheduler, role):
        holder["jobs"] = list(scheduler.get_jobs())
        return real(scheduler, role)
    monkeypatch.setattr(sched, "_apply_role_partition", spy)

    async def go():
        sched.start_scheduler()
    asyncio.run(go())
    job = next(j for j in holder["jobs"] if j.id == "breakout_v1_list")
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert (fields["hour"], fields["minute"], fields["day_of_week"]) == ("17", "55", "mon-fri")
    assert str(job.trigger.timezone) == "America/New_York"


def _fresh(code: str):
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=REPO)


def test_execution_does_not_load_the_breakout_modules():
    listed = (REPO / "scripts" / "exec_loaded_modules.txt").read_text()
    assert "breakout_v1" not in listed
    r = _fresh("import sys; import agents.market_intelligence.scheduler, agents.market_intelligence.agent; "
               "sys.exit(int(any(m.startswith('agents.market_intelligence.breakout_v1') for m in sys.modules)))")
    assert r.returncode == 0, r.stdout + r.stderr


def test_no_broker_code_beyond_the_pure_exit_math():
    r = _fresh("import sys; import agents.market_intelligence.breakout_v1_list; "
               "got = sorted(m for m in sys.modules if m.startswith('agents.market_intelligence.broker')); "
               "print(got); sys.exit(0 if got == ['agents.market_intelligence.broker', "
               "'agents.market_intelligence.broker.exit_logic'] else 1)")
    assert r.returncode == 0, r.stdout + r.stderr



def test_the_ddl_is_idempotent_and_writes_only_its_own_tables():
    import re
    from agents.market_intelligence import db
    ddl = db._BREAKOUT_V1_DDL
    creates = re.findall(r"CREATE\s+TABLE\s+(IF NOT EXISTS)?\s*(\w+)", ddl)
    assert {c[1] for c in creates} == {"mi_breakout_v1_list", "mi_breakout_v1_grades"}
    assert all(c[0] for c in creates)
    assert "ADD COLUMN IF NOT EXISTS name TEXT" in ddl
    assert not re.search(r"\bDROP\b|\bTRUNCATE\b", ddl)
    assert "mi_breakout_v1_list" in db.BV1_LIST_INSERT_SQL and "$9::jsonb" in db.BV1_LIST_INSERT_SQL
    assert "COALESCE(EXCLUDED.name, mi_security_types.name)" in db.SECURITY_TYPES_UPSERT_SQL
