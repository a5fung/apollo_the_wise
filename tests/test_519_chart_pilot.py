"""#519 PILOT -- scripts/probes/_519/chart_pilot.py, the cheap B-vs-C chart test on the closed live trades.

The pilot cannot be run end-to-end from here (it needs the prod DB, mplfinance and the Anthropic
API), so this pins everything around the paid call: the direction-scoring rule and the verdict
rule (the two things the operator will act on), that the cost estimate is printed BEFORE the first
judge call and enforced, that a dry run calls nothing, that a judge returning nothing on the first
trade aborts instead of burning the rest, that the per-row prep matches eval_chart_judge.eval_one
call-for-call, and that the file can write nothing but the judge's own telemetry.
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import contextlib
import importlib.util
import io
import json
import pathlib
import re
import struct
import zlib
from datetime import date
from types import SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "probes" / "_519" / "chart_pilot.py"
EVAL = ROOT / "scripts" / "eval_chart_judge.py"


def _load():
    spec = importlib.util.spec_from_file_location("chart_pilot_519", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load()


# ── direction scoring: the rule he will act on ───────────────────────────────

@pytest.mark.parametrize("r, move, expected", [
    (+1.5, +1, "right"),     # a winner the chart moved UP
    (+1.5, -1, "wrong"),     # a winner the chart moved DOWN
    (-1.0, -1, "right"),     # a loser the chart moved DOWN
    (-1.0, +1, "wrong"),     # a loser the chart moved UP
    (+1.5, 0, None),         # no change -> nothing to score
    (-1.0, None, None),      # a judge call that returned nothing
    (0.0, +1, None),         # break-even: no side to be right about
    (0.0, -1, None),
    (None, +1, None),        # no realized R
])
def test_score_move(r, move, expected):
    assert M.score_move(r, move) == expected


@pytest.mark.parametrize("b, c, expected", [
    ("HIGH", "MODERATE", -1), ("HIGH", "none", -1), ("MODERATE", "none", -1),
    ("none", "HIGH", +1), ("MODERATE", "HIGH", +1),
    ("HIGH", "HIGH", 0), ("none", "none", 0),
    (None, "HIGH", None), ("HIGH", None, None), ("HIGH", "bogus", None),
])
def test_tier_move(b, c, expected):
    assert M.rank_move(M.TIER_RANK, b, c) == expected


def test_grade_move_leaves_mna_unranked():
    assert M.rank_move(M.GRADE_RANK, "routine", "strong") == +1
    assert M.rank_move(M.GRADE_RANK, "game_changer", "routine") == -1
    assert M.rank_move(M.GRADE_RANK, "strong", "mna") is None     # a category, not a level
    assert M.rank_move(M.GRADE_RANK, "mna", "mna") is None


def _rec(r, move, gmove=0):
    return {"r": r, "tier_move": move, "grade_move": gmove}


def test_summarize_splits_all_big_winners_and_big_losers():
    recs = [
        _rec(+3.0, +1),    # big winner, moved up      -> right
        _rec(+2.0, -1),    # big winner (R>=2 boundary), moved down -> wrong
        _rec(+0.5, +1),    # small winner, moved up    -> right
        _rec(-1.0, -1),    # big loser (R<=-1 boundary), moved down -> right
        _rec(-1.5, +1),    # big loser, moved up       -> wrong
        _rec(-0.4, -1),    # small loser, moved down   -> right
        _rec(-1.0, 0),     # unchanged
        _rec(+1.0, None),  # judge returned nothing: not graded
        _rec(0.0, +1),     # break-even changed: counted as changed, scored neither way
    ]
    s = M.summarize(recs)
    a = s["all"]
    assert (a["trades"], a["graded"], a["changed"]) == (9, 8, 7)
    assert (a["right"], a["wrong"], a["unscored"]) == (4, 2, 1)
    assert (a["up"], a["down"]) == (4, 3)
    bw, bl = s["big_winners"], s["big_losers"]
    assert (bw["trades"], bw["changed"], bw["right"], bw["wrong"]) == (2, 2, 1, 1)
    assert (bl["trades"], bl["changed"], bl["right"], bl["wrong"]) == (3, 2, 1, 1)


def test_summarize_on_grade_moves_uses_the_same_rule():
    recs = [_rec(+1.0, 0, +1), _rec(-1.0, 0, +1), _rec(-1.0, 0, -1)]
    s = M.summarize(recs, "grade_move")
    assert (s["all"]["right"], s["all"]["wrong"]) == (2, 1)


def test_summarize_ignores_trades_with_no_r():
    assert M.summarize([_rec(None, +1)])["all"]["trades"] == 0


# ── the verdict rule, declared before any run ────────────────────────────────

@pytest.mark.parametrize("right, wrong, label", [
    (0, 0, "no signal"),
    (3, 0, "no signal"),     # only 3 scored moves: below the 5 minimum
    (4, 1, "helps"),         # 5 scored, lead 3, 80%
    (5, 2, "helps"),         # 7 scored, lead 3, 71%
    (4, 2, "no signal"),     # lead only 2
    (7, 4, "no signal"),     # lead 3 but 64% < two thirds
    (8, 4, "helps"),         # exactly two thirds, lead 4
    (1, 4, "hurts"),
    (2, 5, "hurts"),
    (4, 7, "no signal"),
    (3, 3, "no signal"),
])
def test_verdict_label(right, wrong, label):
    assert M.verdict_label(right, wrong) == label


@pytest.mark.parametrize("right, wrong, p", [(0, 0, 1.0), (5, 0, 0.0625), (4, 1, 0.375),
                                              (3, 3, 1.0), (1, 4, 0.375)])
def test_sign_test_p(right, wrong, p):
    assert M.sign_test_p(right, wrong) == pytest.approx(p)


def test_verdict_line_is_labelled_directional_only_and_carries_the_counts():
    recs = [_rec(+1.0, +1)] * 4 + [_rec(-1.0, +1)]
    line = M.verdict_line(M.summarize(recs), 43)
    assert "DIRECTIONAL ONLY" in line and "n=43" in line and "HELPS" in line
    assert "changed 5 of 5" in line and "4 moved toward the right side" in line
    assert "1 toward the wrong side" in line


# ── population + R ───────────────────────────────────────────────────────────

def _trade(**kw):
    base = {"id": 1, "ticker": "AAA", "alert_date": date(2026, 9, 1), "signal_type": "magna53",
            "pnl_attribution": None, "total_pnl": 100.0, "risk_dollars_actual": 100.0,
            "entry_shares": 10.0, "entry_price": 20.0, "hard_stop": 10.0}
    base.update(kw)
    return base


def _risk():
    from agents.market_intelligence.kill_scale_bands import risk_placed
    return risk_placed


def test_realized_r_uses_the_repos_risk_placed_not_the_pre_cap_budget():
    # risk_dollars (the pre-cap budget) would give 300/300 = 1.0R; the risk PLACED is 100 -> 3.0R
    t = _trade(total_pnl=300.0, risk_dollars=300.0, risk_dollars_actual=100.0, entry_shares=10.0,
               entry_price=20.0, hard_stop=10.0)
    assert M.realized_r(t, _risk()) == pytest.approx(3.0)


def test_realized_r_falls_back_to_the_derived_risk_and_refuses_a_missing_one():
    derived = _trade(risk_dollars_actual=None, total_pnl=-50.0)     # 10 * (20 - 10) = 100 risk
    assert M.realized_r(derived, _risk()) == pytest.approx(-0.5)
    assert M.realized_r(_trade(risk_dollars_actual=None, entry_shares=None), _risk()) is None
    assert M.realized_r(_trade(risk_dollars_actual=0.0), _risk()) is None
    assert M.realized_r(_trade(total_pnl=None), _risk()) is None


def test_split_population_says_what_was_left_out_and_why():
    rows = [
        _trade(id=1),
        _trade(id=2, total_pnl=-100.0),
        _trade(id=3, pnl_attribution="stop_bug"),                       # bug-distorted P&L
        _trade(id=4, risk_dollars_actual=None, entry_shares=None),      # no usable risk
        _trade(id=5, signal_type="htf_breakout"),                       # not MAGNA53
        _trade(id=6, signal_type=None),
    ]
    pop = M.split_population(rows, _risk())
    assert pop["closed_live_total"] == 6
    assert pop["magna53"] == 4
    assert (pop["bug_distorted"], pop["no_risk"]) == (1, 1)
    assert [t["id"] for t in pop["eligible"]] == [1, 2]
    assert pop["by_signal"] == {"magna53": 4, "htf_breakout": 1, "(none)": 1}
    assert [round(t["r"], 2) for t in pop["eligible"]] == [1.0, -1.0]


def test_population_lines_state_n_span_and_distribution():
    pop = M.split_population([_trade(id=1, total_pnl=300.0),
                              _trade(id=2, alert_date=date(2026, 8, 1), total_pnl=-100.0),
                              _trade(id=3, total_pnl=-50.0)], _risk())
    text = "\n".join(M.population_lines(pop))
    assert "SCORED POPULATION: 3 trades" in text
    assert "2026-08-01 .. 2026-09-01" in text
    assert "1 winners (R>0), 2 losers (R<0), 0 break-even; 1 big winners (R>=2), 1 big losers (R<=-1)" in text


# ── cost ─────────────────────────────────────────────────────────────────────

def _png(w, h):
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IEND", b""))


def test_image_tokens_come_from_the_png_header():
    assert M.png_dims(_png(1047, 743)) == (1047, 743)
    assert M.image_tokens(_png(1047, 743)) == 1037        # the 09-12 cost doc's measured figure
    assert M.image_tokens(b"not a png") == M.DEFAULT_IMAGE_TOKENS


def test_estimate_run_is_priced_from_the_given_rates():
    items = [{"b_chars": 7000, "c_chars": 7100, "img_tokens": 1000}] * 2
    price = {"input": 5.0, "output": 25.0}
    est = M.estimate_run(items, price, schema_chars=1000, max_out=1500, expected_out=700)
    in_tok = 2 * (M.est_tokens(7000) + M.est_tokens(1000) + M.est_tokens(7100) + M.est_tokens(1000)
                  + 1000)
    assert est["calls"] == 4 and est["in_tokens"] == in_tok
    assert est["expected_usd"] == pytest.approx((in_tok * 5 + 4 * 700 * 25) / 1e6)
    assert est["worst_usd"] == pytest.approx((in_tok * 5 + 4 * 1500 * 25) / 1e6)
    assert est["worst_usd"] > est["expected_usd"]
    # the pilot's size: ~43 trades -> ~86 calls at ~$0.03 each lands in the $2-3 he was quoted
    full = M.estimate_run([{"b_chars": 7500, "c_chars": 7650, "img_tokens": 1037}] * 43, price,
                          schema_chars=1000, max_out=1500)
    assert full["calls"] == 86 and 1.5 < full["expected_usd"] < 4.0


def test_spend_tap_counts_tokens_and_dollars_and_stops_at_the_cap():
    class Client:
        def __init__(self):
            self.messages = SimpleNamespace(create=self.create)
            self.n = 0

        async def create(self, **kw):
            self.n += 1
            return SimpleNamespace(usage=SimpleNamespace(input_tokens=1000, output_tokens=500))

    cost = lambda m, i, o, cc, cr: (i * 5 + o * 25) / 1e6      # $0.0175 per call
    client = Client()
    tap = M.SpendTap(client, cost, max_usd=0.03)

    async def go():
        await tap.messages.create(model="m")
        await tap.messages.create(model="m")           # 0.035 >= cap now
        assert tap.over_budget
        with pytest.raises(M.BudgetExceeded):
            await tap.messages.create(model="m")
    asyncio.run(go())
    assert client.n == 2 and tap.calls == 2
    assert (tap.in_tok, tap.out_tok) == (2000, 1000)
    assert tap.usd == pytest.approx(0.035) and tap.models == {"m"}


# ── the run: dry-run, cost-before-calls, abort, scoring end to end ───────────

class _Acq:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *a):
        return False


class _Conn:
    def __init__(self, trades, alerts):
        self.trades, self.alerts = trades, alerts

    async def fetch(self, sql):
        assert sql.lstrip().upper().startswith("SELECT")
        return self.trades

    async def fetchrow(self, sql, ticker, d):
        assert sql == "ALERT_SQL"
        return self.alerts.get(ticker)


class _Pool:
    def __init__(self, trades, alerts):
        self.conn = _Conn(trades, alerts)

    def acquire(self):
        return _Acq(self.conn)

    async def close(self):
        pass


def _verdict(tier, grade="strong"):
    return {"tier": tier, "grade": grade, "direction_vs_floor": "hold", "confidence": 0.7,
            "rationale": "because"}


def _make_rt(trades, *, tiers, no_chart=(), no_alert=(), err_buf=None, none_for=(),
             usage=(2000, 600)):
    """A runtime stub: `tiers` maps ticker -> (B tier, C tier). Records every judge call."""
    alerts = {t["ticker"]: {"floor_tier": "HIGH"} for t in trades if t["ticker"] not in no_alert}
    calls = []

    async def render(ticker, d):
        return (None, 5) if ticker in no_chart else (_png(1047, 743), 160)

    async def profile(ticker):
        return 1e9, "Tech", "Co"

    async def grounded(row, company, grounded):
        assert grounded is False
        return "text", None

    async def grade_b_c(client, sem, payload, png, replicates, log_caller):
        assert replicates == 1 and log_caller == "chart_axis_pilot"
        calls.append({"ticker": payload["ticker"],
                      "err_at_call": err_buf.getvalue() if err_buf else ""})
        # exercise the spend tap exactly as the judge transport does -- which FAILS OPEN on any
        # error (grade_holistic returns None), so a refused call is a missing verdict, not a crash
        try:
            await client.messages.create(model="claude-opus-5-5", max_tokens=1500)
        except Exception:
            return {"b_verdict": None, "c_verdict": None}
        if payload["ticker"] in none_for:
            return {"b_verdict": None, "c_verdict": None}
        b, c = tiers[payload["ticker"]]
        return {"b_verdict": _verdict(b), "c_verdict": _verdict(c)}

    class Client:
        def __init__(self):
            self.messages = SimpleNamespace(create=self.create)

        async def create(self, **kw):
            return SimpleNamespace(usage=SimpleNamespace(input_tokens=usage[0],
                                                         output_tokens=usage[1]))

        async def close(self):
            pass

    rt = SimpleNamespace(
        ALERT_ROW_SQL="ALERT_SQL", render_prior_day_chart=render, fetch_profile=profile,
        resolve_grounded_text=grounded,
        build_judge_payload=lambda row, g, mc, sector: ({"ticker": row["_t"]}, None),
        grade_b_c=grade_b_c, note_b="B" * 900, note_c="C" * 800,
        build_prompt=lambda payload: "p" * 6500, judge_tool=lambda inc: {"name": "grade_ep"},
        MODEL="claude-opus-5-5", get_pool=None, risk_placed=_risk(),
        make_client=lambda api_key: Client(), pricing_for=lambda m: {"input": 5.0, "output": 25.0},
        max_out=1500, cost_for_call=None, capture_disabled=contextlib.nullcontext)
    for t in trades:
        if t["ticker"] in alerts:
            alerts[t["ticker"]]["_t"] = t["ticker"]

    async def get_pool():
        return _Pool(trades, alerts)

    rt.get_pool = get_pool
    return rt, calls


def _args(**kw):
    return argparse.Namespace(**{"dry_run": False, "max_usd": 5.0, "outdir": "", **kw})


def _drive(rt, args):
    out, err = io.StringIO(), io.StringIO()
    rc = asyncio.run(M.run(args, rt=rt, out=out, err=err))
    return rc, out.getvalue(), err.getvalue()


TRADES = [
    _trade(id=1, ticker="WIN1", total_pnl=300.0),     # R +3.0  big winner
    _trade(id=2, ticker="WIN2", total_pnl=100.0),     # R +1.0
    _trade(id=3, ticker="LOS1", total_pnl=-100.0),    # R -1.0  big loser
    _trade(id=4, ticker="LOS2", total_pnl=-50.0),     # R -0.5
    _trade(id=5, ticker="LOS3", total_pnl=-100.0),     # R -1.0  big loser
    _trade(id=6, ticker="NOCH", total_pnl=-100.0),    # no chart -> skipped
    _trade(id=7, ticker="NOAL", total_pnl=-100.0),    # no alert row -> skipped
]
TIERS = {
    "WIN1": ("HIGH", "MODERATE"),     # winner moved down -> wrong
    "WIN2": ("MODERATE", "HIGH"),     # winner moved up   -> right
    "LOS1": ("HIGH", "none"),         # loser moved down  -> right
    "LOS2": ("HIGH", "HIGH"),         # unchanged
    "LOS3": ("HIGH", "MODERATE"),     # a second big loser moved down -> right
}


def test_dry_run_prices_everything_and_calls_the_judge_never(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    rt, calls = _make_rt(TRADES, tiers=TIERS, no_chart={"NOCH"}, no_alert={"NOAL"})
    rc, out, err = _drive(rt, _args(dry_run=True))
    assert rc == 0 and calls == [] and out == ""
    assert "COST ESTIMATE" in err and "DRY RUN" in err and "SCORED POPULATION: 7 trades" in err
    assert "SKIPPED before any judge call: 2 of 7" in err
    assert "no_chart:1" in err and "no_alert_row:1" in err and "GRADABLE: 5 trades" in err


def test_the_estimate_is_printed_before_the_first_judge_call(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    buf = io.StringIO()
    rt, calls = _make_rt(TRADES, tiers=TIERS, no_chart={"NOCH"}, no_alert={"NOAL"}, err_buf=buf)
    out, err = io.StringIO(), buf
    rc = asyncio.run(M.run(_args(), rt=rt, out=out, err=err))
    assert rc == 0 and len(calls) == 5
    assert all("COST ESTIMATE (before any judge call)" in c["err_at_call"] for c in calls)
    assert "POPULATION" in calls[0]["err_at_call"]          # composition printed first


def test_abort_above_the_cap_spends_nothing(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    rt, calls = _make_rt(TRADES, tiers=TIERS)
    rc, out, err = _drive(rt, _args(max_usd=0.001))
    assert rc == 3 and calls == [] and "ABORT" in err and "Nothing was spent" in err


def test_missing_api_key_aborts_before_any_call(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rt, calls = _make_rt(TRADES, tiers=TIERS)
    rc, out, err = _drive(rt, _args())
    assert rc == 2 and calls == [] and "ANTHROPIC_API_KEY" in err


def test_a_judge_that_returns_nothing_on_the_first_trade_aborts_the_run(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    rt, calls = _make_rt(TRADES, tiers=TIERS, none_for={"WIN1"})
    rc, out, err = _drive(rt, _args())
    assert rc == 4 and len(calls) == 1 and "NO verdict on the first trade" in err
    assert len(out.strip().splitlines()) == 1


def test_a_full_run_scores_each_move_by_realized_r(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    rt, calls = _make_rt(TRADES, tiers=TIERS, no_chart={"NOCH"}, no_alert={"NOAL"})
    rc, out, err = _drive(rt, _args())
    assert rc == 0 and len(calls) == 5
    lines = [json.loads(x) for x in out.strip().splitlines()]
    assert len(lines) == 7                                   # one JSON line per trade, skips included
    by = {x["ticker"]: x for x in lines}
    assert by["NOCH"]["skip"] == "no_chart" and by["NOAL"]["skip"] == "no_alert_row"
    assert (by["WIN1"]["tier_move"], by["WIN1"]["score"]) == (-1, "wrong")
    assert (by["WIN2"]["tier_move"], by["WIN2"]["score"]) == (+1, "right")
    assert (by["LOS1"]["tier_move"], by["LOS1"]["score"]) == (-1, "right")
    assert (by["LOS2"]["tier_move"], by["LOS2"]["score"]) == (0, None)
    assert by["WIN2"]["b"]["tier"] == "MODERATE" and by["WIN2"]["c"]["grade"] == "strong"
    assert by["WIN1"]["r"] == 3.0
    assert "RESULT" in err and "DIRECTIONAL ONLY" in err and "NO SIGNAL" in err    # 4 scored < 5
    assert "changed 4 of 5 calls; 3 moved toward the right side, 1 toward the wrong side" in err
    # actual spend is reported: each fake call is (2000 in, 600 out) at $5/$25 per Mtok = $0.025;
    # the fake makes one tap call per trade, so 5 calls = $0.125
    assert "ACTUAL $0.12 over 5 calls" in err or "ACTUAL $0.13 over 5 calls" in err
    assert "SUMMARY_JSON" in err


def test_summary_counts_in_a_full_run_match_the_hand_count(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    rt, _ = _make_rt(TRADES, tiers=TIERS, no_chart={"NOCH"}, no_alert={"NOAL"})
    rc, out, err = _drive(rt, _args())
    summary = json.loads(next(x for x in err.splitlines() if x.startswith("SUMMARY_JSON "))[13:])
    a = summary["tier"]["all"]
    assert (a["changed"], a["right"], a["wrong"]) == (4, 3, 1)       # WIN1 wrong; WIN2/LOS1/LOS3 right
    assert summary["tier"]["big_winners"]["wrong"] == 1 and summary["tier"]["big_winners"]["right"] == 0
    assert summary["tier"]["big_losers"]["right"] == 2               # LOS1 and LOS3 (both R=-1.0)
    assert summary["n_graded"] == 5 and summary["failed"] == 0 and summary["calls"] == 5


def test_the_spend_cap_stops_new_calls_mid_run(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    # the pre-flight estimate (~$0.3) clears a $1.00 cap, but each fake call REALLY costs ~$1.25
    # (50,000 output tokens): after the first trade the running counter is over the cap, so the
    # rest are not sent -- recorded as failed, with no further judge calls.
    rt, calls = _make_rt(TRADES, tiers=TIERS, no_chart={"NOCH"}, no_alert={"NOAL"},
                         usage=(2000, 50000))
    rc, out, err = _drive(rt, _args(max_usd=1.0))
    assert rc == 0 and len(calls) == 1
    lines = [json.loads(x) for x in out.strip().splitlines()]
    cut = [x for x in lines if "spend cap reached" in (x.get("failed") or "")]
    assert len(cut) == 4 and all(x["b"] is None and x["c"] is None for x in cut)
    assert "judge returned nothing on at least one arm: 4" in err


# ── structure pins ───────────────────────────────────────────────────────────

def _call_names(fn_node, wanted):
    names = []
    for node in ast.walk(fn_node):
        if isinstance(node, ast.Call):
            f = node.func
            n = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if n in wanted:
                names.append((node.lineno, n))
    return [n for _, n in sorted(names)]


def _fn(path, name):
    tree = ast.parse(path.read_text())
    return next(n for n in ast.walk(tree)
                if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == name)


def test_the_per_row_prep_matches_eval_one_call_for_call():
    # source-pin-ok: the pilot repeats eval_one's prep (the deployed eval cannot be refactored under it), and parity of the helper-call sequence between two files is only checkable from their text
    """The pilot repeats eval_one's prep (it cannot call a refactor of it: the running image has
    the deployed eval). This pins that the two stay the SAME sequence of helper calls, so the pilot
    grades the byte-identical payload + chart the eval does."""
    wanted = {"render_prior_day_chart", "fetch_profile", "resolve_grounded_text",
              "build_judge_payload"}
    assert _call_names(_fn(SCRIPT, "prepare_trade"), wanted) == \
        _call_names(_fn(EVAL, "eval_one"), wanted) == \
        ["render_prior_day_chart", "fetch_profile", "resolve_grounded_text", "build_judge_payload"]
    for path, name in ((SCRIPT, "prepare_trade"), (EVAL, "eval_one")):
        grounded = [kw for n in ast.walk(_fn(path, name)) if isinstance(n, ast.Call)
                    and getattr(n.func, "attr", getattr(n.func, "id", None)) == "resolve_grounded_text"
                    for kw in n.keywords if kw.arg == "grounded"]
        assert len(grounded) == 1 and grounded[0].value.value is False, f"{path.name}: grounded=False"


def test_the_runtime_wires_the_adapter_factory_and_the_evals_own_functions(monkeypatch):
    """_load_runtime against the REAL modules: every name it reaches for exists, the judge client
    is the adapter factory (opus-5-5 rejects a forced tool_choice -- a raw client 400s every call),
    and the alert SQL / render / payload / B-C core are the eval's own objects, not copies."""
    monkeypatch.setenv("APOLLO_CALL_ORIGIN", "test")      # _load_runtime setdefaults it; keep the test env clean
    from agents.market_intelligence import chart_axis
    from agents.market_intelligence.kill_scale_bands import risk_placed
    from scripts import eval_chart_judge as ev
    from shared import llm_client
    rt = M._load_runtime()
    assert rt.make_client is llm_client.make_async_anthropic
    assert rt.ALERT_ROW_SQL is ev._ALERT_ROW_SQL
    assert rt.render_prior_day_chart is ev.render_prior_day_chart
    assert rt.fetch_profile is ev.fetch_profile
    assert rt.resolve_grounded_text is ev.resolve_grounded_text
    assert rt.build_judge_payload is ev.build_judge_payload
    assert rt.grade_b_c is ev.grade_b_c is chart_axis.grade_b_c
    assert rt.note_b is chart_axis.CHART_AXIS_NOTE_TEXT_ONLY and rt.note_c is chart_axis.CHART_AXIS_NOTE
    assert rt.risk_placed is risk_placed
    # priced from the model the judge actually binds, at a real positive rate
    p = rt.pricing_for(rt.MODEL)
    assert p["input"] > 0 and p["output"] > p["input"] and rt.max_out >= 1000
    # the real prompt is what the estimate measures: non-trivial text, plus the forced-tool schema
    assert len(rt.build_prompt({"ticker": "T", "score_tier": "HIGH", "catalyst": "c"})) > 3000
    assert rt.judge_tool(False)["name"] == "grade_ep"


def test_the_pure_parts_import_without_any_prod_only_module():
    """Behavioural: load the script in a fresh interpreter where agents/shared/scripts/anthropic/
    asyncpg cannot be imported at all, and use a pure function."""
    import subprocess
    import sys
    code = (
        "import sys, importlib.util\n"
        "for m in ('agents', 'shared', 'scripts', 'anthropic', 'asyncpg'):\n"
        "    sys.modules[m] = None\n"
        f"spec = importlib.util.spec_from_file_location('p', {str(SCRIPT)!r})\n"
        "mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)\n"
        "assert mod.verdict_label(5, 0) == 'helps'\n"
        "print('ok')\n")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr


def test_it_is_read_only_on_the_database():
    """The one query is a SELECT; and every end-to-end test above ran against a connection that
    has `fetch`/`fetchrow` and NOTHING else -- any execute/insert path would have raised."""
    assert M._TRADES_SQL.lstrip().upper().startswith("SELECT")
    assert "account_mode = 'live'" in M._TRADES_SQL and "status = 'closed'" in M._TRADES_SQL
    assert not hasattr(_Conn, "execute") and not hasattr(_Conn, "executemany")
    assert not hasattr(_Pool, "execute")
