"""#705 (c) - tests for the RS-leadership-ALONE read (scripts/probes/_cb_backtest/rs_alone_read.py, rs_alone_fixtures.py and the `rederive_alone_c3` path of
aplus_rederive.py) on SYNTHETIC data only: the precondition's refusals, the once-only refusals, the artefact-name separation (no `aplus_*holdout*` is ever
written), the golden TIE fixtures by hand, the engine against a brute-force definition on tied data, the integer outlier bar at its boundary, the
consequence cells, STEP 0 with no outcome column opened, every look-ahead / later-fill / counts / pool / shuffle check's failing case, the independent
re-derivation (VERDICT MATCH and a mismatch that writes nothing). No real outcome: every number here is a synthetic bar.
"""
from __future__ import annotations

import ast
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from scripts.probes._cb_backtest import aplus_read as ap
from scripts.probes._cb_backtest import aplus_rederive as rd
from scripts.probes._cb_backtest import registered_read as rr
from scripts.probes._cb_backtest import rs_alone_fixtures as fxr
from scripts.probes._cb_backtest import rs_alone_read as rs
from scripts.probes._cb_backtest import runner as rn

try:                                                         # the synthetic tree builders of the A+ read's own test file (pytest's module name)
    import test_cb_backtest_aplus as TA
except ImportError:                                          # pragma: no cover - the repo-root spelling
    from tests import test_cb_backtest_aplus as TA
fx = TA.fx


# ═══ the synthetic tree: the A+ read's golden population, the parent verdicts, the RS-alone registration doc ═══════════════════════════
def parent_row(ge10, mean, t=3, m=3, n=100):
    return {"n": n, "mean_r": mean, "ci_lo": -0.1, "ci_hi": 0.5, "ge5_per100": 3.0, "ge10_per100": ge10, "count_ge10": 5, "tail_tickers": t, "tail_months": m,
            "verdict": "CAN'T TELL"}


def parent_verdict(period, verdict="CAN'T TELL", paired="can't tell", rows=None):
    rows = rows if rows is not None else {"alone_c3|3": parent_row(1.75, 0.2, 7, 5), "alone_c7|3": parent_row(1.26, 0.1, 6, 6), "alone_c1|3": parent_row(0.8, 0.0, 1, 1)}
    return {"period": period, "verdict": verdict, "why": "x", "paired": {"reading": paired}, "grp": {"reading": "CAN'T TELL"}, "rows": rows}


def write_parents(tree, pre=None, disc=None):
    (tree["cb702_pre"] / "out" / "aplus_verdict_pre.json").write_text(json.dumps(pre or parent_verdict("pre")))
    (tree["cb702"] / "out" / "aplus_verdict_discovery.json").write_text(json.dumps(disc or parent_verdict("discovery")))


def rs_doc(tree, body: str = "Method / population. What this does not answer. n=1.\n") -> Path:
    spec = rs.RS_ALONE_READ
    p = tree["repo"] / "docs" / "analysis" / spec.doc
    p.write_text(body + rn.FREEZE_MARK + "\n## Freeze record\n")
    ctx = rr.resolve(spec, TA.ns(tree), rn)
    pins = rn.pin_lines(tree["cb702"], tree["repo"], files=rr.frozen_map(spec, ctx)) + [f"- doc body sha256: `{rn.doc_body_sha(p.read_text())}`"]
    p.write_text(p.read_text() + "\n".join(pins) + "\n")
    return p


def rs_tree(tmp_path, monkeypatch, rows=None, **kw):
    tree = TA.aplus_tree(tmp_path, monkeypatch, period="holdout", rows=rows, **kw)
    exp = TA.set_expected(monkeypatch, tree)
    monkeypatch.setattr(rs, "RS_EXPECTED", {k: exp[k] for k in rs.RS_EXPECTED})
    rs.clear_calendar_cache()
    write_parents(tree)
    rs_doc(tree)
    return tree


def main(tree, *extra, period="unset"):
    return TA.main(tree, "rs-alone-read", *extra, period=period)


def _prep(tree):
    ctx = rr.resolve(rs.RS_ALONE_READ, TA.ns(tree), rn)
    prep = rs.rs_prepare(ctx)
    cols, res, ties, c, problems = rs.rs_step0(ctx, prep, lambda *a: None)
    return ctx, prep, cols, res, ties


def out_files(tree) -> list:
    return sorted(p.as_posix() for d in (tree["cb702"], tree["cb702_pre"], rn.HERE) for p in d.rglob("*") if p.is_file())


# ═══ the registration and the pins ══════════════════════════════════════════════════════════════════════════════════════════════════════
class TestRegistration:
    def test_the_stage_is_a_registered_read_with_its_own_artefact_names(self):
        s = rs.RS_ALONE_READ
        assert rn.REGISTERED_READS["rs-alone-read"] is s and s.periods == ("holdout",) and s.tag == "rs_alone" and s.order == rr.DEFAULT_ORDER
        assert rs.RS_EXPECTED == {"joined": 7570, "fills": 7547, "open": 39, "weeks": 93, "dropped": 23}
        assert rs.RS_SPEC == "alone_c3" and rs.RS_N == 3 and ap.CUTOFF_RANK[rs.RS_N] == 12
        ctx = type("C", (), {"period": "holdout"})()
        assert rs.rs_outputs(ctx) == ("trades_holdout_rs_alone.tsv.gz", "rs_alone_report_holdout.tsv", "rs_alone_report_holdout.txt")
        names = set(rs.rs_outputs(ctx)) | {f"rs_alone_verdict_holdout.{x}" for x in ("json", "txt")} | {"rs_alone_summary_holdout.txt"}
        parent = {"trades_holdout_aplus.tsv.gz", "aplus_verdict_holdout.json", "aplus_verdict_holdout.txt", "aplus_report_holdout.tsv", "aplus_report_holdout.txt"}
        assert not names & parent and not any(n.startswith("aplus") for n in names)

    def test_print_pins_carries_the_registrations_list(self, tmp_path, monkeypatch, capsys):
        tree = rs_tree(tmp_path, monkeypatch)
        assert main(tree, "--print-pins", period=None) is None
        pins = capsys.readouterr().out
        for label in ("cb702/out/trades_discovery_exitpb.tsv.gz", "cb702/out/trades_holdout_exitpb.tsv.gz", "cb702/out/trades_discovery_p5.tsv.gz",
                      "cb702/out/trades_holdout_p5.tsv.gz", "cb702/out/candidates.tsv", "cb702/out/watch.tsv.gz", "cb702/daily_closes_all.csv.gz", "runner", "scaffold",
                      "spec module", "aplus module", "rederivation module", "golden fixtures module", "doc body"):
            assert f"- {label} sha256: `" in pins, label
        assert "MISSING" not in pins
        assert not any("minutes" in ln for ln in pins.splitlines())                       # the stage opens no minute tree and pins none

    def test_the_pins_cover_every_input_the_stage_opens(self, tmp_path, monkeypatch):
        tree = rs_tree(tmp_path, monkeypatch)
        ctx = rr.resolve(rs.RS_ALONE_READ, TA.ns(tree), rn)
        prep = rs.rs_prepare(ctx)
        assert rr.uncovered_inputs(rs.RS_ALONE_READ, ctx, prep) == []
        assert prep["inp"] is None and len(prep["rows"]) == 108

    def test_only_one_score_is_ever_computed(self, tmp_path, monkeypatch):
        tree = rs_tree(tmp_path, monkeypatch)
        ctx, prep, cols, res, ties = _prep(tree)
        assert set(res["score"]) == {"alone_c3"} and set(res["flag"]) == {("alone_c3", 3)}
        for c in rs.NOT_COMPUTED:
            assert all(x is None for x in cols[c]), c
        assert any(x is not None for x in cols["rs_best"])
        other = np.delete(res["pct"], ap.KEY_IDX["c3"], axis=1)
        assert np.isnan(other).all() and not np.isnan(res["pct"][:, ap.KEY_IDX["c3"]]).all()
        assert rs.not_computed_problems(cols, res) == []
        cols["prior_move"][3] = 0.5                                                       # a score that is not alone_c3's, computed: caught
        assert any("prior_move" in x for x in rs.not_computed_problems(cols, res))


# ═══ the golden tie fixtures (check 9), by hand ═════════════════════════════════════════════════════════════════════════════════════════════
class TestGoldenTies:
    def test_the_fixtures_pass_on_the_committed_code(self):
        assert fxr.run_golden() == []

    def test_the_hand_numbers(self):
        # T1: the 12th-highest reference score is the member at 78.0 (28 worse of 39 others); the fill AT 78.0 scores 28.5 / 40 = 0.7125 < 28/39 = 0.71795
        h = fxr.hand_day("T1")
        assert h["cutoff"] == 28 / 39 and h["fills"]["T1A"] == 28.5 / 40 and h["fills"]["T1B"] == 29 / 40 and h["fills"]["T1A"] < h["cutoff"] < h["fills"]["T1B"]
        assert abs(h["fills"]["T1A"] + (h["fills"]["T1A"] - 0.5) / 39 - h["cutoff"]) < 1e-15                    # p + (p - 1/2) / (n - 1)
        # T2: six members share the cutoff value: 28.5 / 39; the fill at that value 29 / 40 = 0.725 < 0.73077; one above the group 32 / 40
        h = fxr.hand_day("T2")
        assert h["cutoff"] == 28.5 / 39 and h["fills"]["T2A"] == 29 / 40 < h["cutoff"] and h["fills"]["T2C"] == 32 / 40 > h["cutoff"]
        # T3: fourteen members at the maximum: 32.5 / 39; a fill at 100.0 scores 33 / 40 = 0.825 < 0.8333
        h = fxr.hand_day("T3")
        assert h["cutoff"] == 32.5 / 39 and h["fills"]["T3A"] == 33 / 40 < h["cutoff"]

    def test_the_flags_the_hand_computation_gives(self):
        rows = fxr.golden_rows()
        cols = fxr.cols_of(rows)
        res = rs.rate_alone(cols)
        idx = {t: i for i, t in enumerate(cols["ticker"])}
        fl = rs.flags(res)
        got = {f"{d}{t}": fl[idx[f"{d}{t}"]] for d in fxr.E_OF for t, *_ in fxr.FILLS[d]}
        want = {f"{d}{t}": f for d in fxr.E_OF for t, _fm, _v, f in fxr.FILLS[d]}
        assert got == want
        assert got["T1A"] == "rest" and got["T1B"] == "aplus" and got["T1E"] == "capped"             # the fill AT the cutoff value is not A+; just above is; the 4th is capped
        assert all(got[f"T3{t}"] == "rest" for t in "ABC")                                           # the maximum, shared by 14 members: nobody is A+
        ties = rs.ties_at_cutoff(cols, res)
        assert ties["problems"] == [] and int(ties["tie"].sum()) == sum(fxr.TIES.values())
        assert {fxr.CUTOFF_VALUE[d] for d in fxr.E_OF} == {78.0, 81.0, 100.0}

    def test_a_fill_below_one_half_scores_above_its_tied_member(self):
        h = fxr.hand_day("T1")["fills"]["T1G"]
        assert h == 10.5 / 40 and h > fxr.hand_pct(fxr.pool_values("T1"), 60.0, exclude_self=True) == 10 / 39

    def test_an_engine_without_the_leave_one_out_reference_is_caught(self, monkeypatch):
        """The mutation the fixtures exist for: the member's reference score taken against the WHOLE pool (itself in it) makes the fill at the cutoff
        value tie its own cutoff and pass - the run would flag 78.0 / 81.0 / 100.0 as A+."""
        real = ap.pool_percentiles

        def no_loo(X, pool, day, floor=ap.POOL_FLOOR):
            own, ref = real(X, pool, day, floor)
            own2, _ = real(X, pool, pool, floor)                                            # the members against the whole pool: no "minus itself"
            return own, own2[:, :] if own2.shape == ref.shape else ref
        monkeypatch.setattr(ap, "pool_percentiles", no_loo)
        problems = fxr.run_golden()
        assert problems and any("T1" in x for x in problems) and any("rest" in x or "hand" in x for x in problems)

    def test_a_flipped_direction_is_caught(self, monkeypatch):
        monkeypatch.setitem(ap.FEATURES, "c3", ("rs_best", -1))
        assert fxr.run_golden()

    def test_a_pool_that_includes_the_days_own_fills_is_caught(self, monkeypatch):
        real = ap.pool_percentiles
        monkeypatch.setattr(ap, "pool_percentiles", lambda X, pool, day, floor=ap.POOL_FLOOR: real(X, np.concatenate([pool, day]), day, floor))
        assert fxr.run_golden()


# ═══ the engine against the definition, on tied data ═════════════════════════════════════════════════════════════════════════════════════
def _brute(rows):
    """The A+ flag of every row by the DEFINITION (python lists, no numpy ranking): pool = every row with E' in [E - 20, E - 1]; pct = (worse + 0.5
    equal) / |S|; a member's reference = the same against S minus itself; the cutoff = the 12th-highest reference score; the weekly cap in fill order."""
    n = len(rows)
    order = sorted(range(n), key=lambda i: (rows[i][1], rows[i][2], rows[i][0]))
    taken, out, day_cache = Counter(), {}, {}
    for i in order:
        t, e, fm, v, wk, el = rows[i]
        if e not in day_cache:
            pool = [rows[j] for j in range(n) if e - 20 <= rows[j][1] <= e - 1]
            S = [r[3] for r in pool if r[3] is not None]
            refs = []
            if len(S) - 1 >= 30:
                for r in pool:
                    if r[3] is None:
                        continue
                    S2 = list(S)
                    S2.remove(r[3])
                    refs.append((sum(x < r[3] for x in S2) + 0.5 * sum(x == r[3] for x in S2)) / len(S2))
            day_cache[e] = (S, sorted(refs, reverse=True)[11] if len(refs) >= 12 else None)
        S, cut = day_cache[e]
        if not el:
            out[t] = ""
        elif v is None or len(S) < 30 or cut is None:
            out[t] = "unrated"
        else:
            p = (sum(x < v for x in S) + 0.5 * sum(x == v for x in S)) / len(S)
            if p >= cut:
                taken[wk] += 1
                out[t] = "aplus" if taken[wk] <= 3 else "capped"
            else:
                out[t] = "rest"
    return out


class TestEngine:
    @pytest.mark.parametrize("seed", [3, 11])
    def test_rate_alone_equals_the_definition_on_random_tied_data(self, seed):
        rng = np.random.default_rng(seed)
        rows = []
        for s in range(60):
            for k in range(10):
                v = round(float(rng.integers(900, 1001)) / 10, 1) if rng.random() > 0.04 else None          # a 0.1 grid: many ties; a few missing
                e = fxr.CAL[s]
                rows.append((f"T{s:03d}{k}", s, int(rng.integers(5, 390)), v, ap.iso_week(e), s >= 22))
        base = {"ticker": [r[0] for r in rows], "E": [fxr.CAL[r[1]] for r in rows], "E_ci": [r[1] for r in rows], "fill_minute": [r[2] for r in rows],
                "week": [r[4] for r in rows], "eligible": [r[5] for r in rows]}
        cols = rs.engine_cols(base, [r[3] for r in rows])
        res = rs.rate_alone(cols)
        want = _brute(rows)
        got = {t: res["flag"][("alone_c3", 3)][i] for i, t in enumerate(cols["ticker"])}
        assert got == want
        assert sum(1 for f in got.values() if f == "aplus") > 15 and sum(1 for f in got.values() if f == "capped") > 0 and sum(1 for f in got.values() if f == "unrated") > 0

    def test_rs_best_missing_is_never_read_as_zero(self):
        rows = fxr.golden_rows()
        cols = fxr.cols_of(rows)
        i = cols["ticker"].index("T1B")
        res0 = rs.rate_alone(cols)
        assert rs.flags(res0)[i] == "aplus"
        cols["rs_best"][i] = None
        res = rs.rate_alone(cols)
        assert rs.flags(res)[i] == "unrated" and np.isnan(res["score"]["alone_c3"][i])


# ═══ the bar at its boundary, the consequence cells ═════════════════════════════════════════════════════════════════════════════════════════
C0_REAL = {"mean_r": -0.129, "ge5_per100": 2.95, "median_width_adr": 0.5}


def _group(r, width=0.5, tickers=None, months=None):
    r = np.asarray(r, dtype=float)
    n = len(r)
    return ap.group_stats(r, np.full(n, 0.1), np.full(n, width), tickers or [f"T{i % 7}" for i in range(n)], months or [f"2025-{1 + i % 6:02d}" for i in range(n)],
                          "k", rn.block_bootstrap_ci)


class TestBar:
    def test_the_registered_c0_constants_are_the_published_ones(self):
        pub = ap.C0_PUBLISHED["holdout"]
        assert (pub["n"], pub["ge10"], pub["mean_r"], pub["ge5_per100"]) == (7531, 89, -0.129, 2.95)

    @pytest.mark.parametrize("n, tail, passes", [(253, 6, True), (253, 5, False), (254, 6, False), (254, 7, True)])
    def test_the_integer_outlier_bar_at_its_boundary(self, n, tail, passes):
        """count_ge10 x 7,531 >= 2 x 89 x n: n = 253 needs 6 (6 x 7531 = 45,186 >= 45,034), n = 254 needs 7 (6 x 7531 < 2 x 89 x 254 = 45,212)."""
        g = _group([12.0] * tail + [6.0] * 11 + [0.6] * (n - tail - 11))
        assert g["n"] == n and g["count_ge10"] == tail
        v, why = rs.alone_verdict(g, C0_REAL)
        o = rs.outlier_test(g)
        assert o["met"] is passes and o["lhs"] == tail * 7531 and o["rhs"] == 2 * 89 * n
        assert v == ("PASS" if passes else "CAN'T TELL (positive, no tail)"), (v, why)
        if not passes:
            assert f"{tail * 7531} < 2 x 89 x {n} = {2 * 89 * n}" in why

    def test_the_other_branches_of_the_bar(self):
        assert rs.alone_verdict(_group([-1.0] * 40), C0_REAL)[0] == "FAIL"
        assert rs.alone_verdict(_group([0.5] * 29), C0_REAL) == ("CAN'T TELL", "n = 29 < 30")
        v, why = rs.alone_verdict(_group([12.0] * 8 + [6.0] * 10 + [0.6] * 240, width=0.1), C0_REAL)               # the spread counts stops >= 0.25 ADR only
        assert v == "CAN'T TELL (positive, no tail)" and "0 tickers / 0 months" in why
        v, why = rs.alone_verdict(_group([12.0] * 8 + [6.0] * 10 + [0.6] * 240, tickers=["A"] * 258), C0_REAL)
        assert v == "CAN'T TELL (positive, no tail)" and "1 tickers" in why

    @pytest.mark.parametrize("verdict, paired, cell, record", [
        ("PASS", "separates", "RECORD", True), ("PASS", "can't tell", "RECORD", True), ("PASS", "picks worse", "NOT RECORDED", False),
        ("CAN'T TELL", "can't tell", "NOT RECORDED", False), ("CAN'T TELL (positive, no tail)", "separates", "NOT RECORDED", False),
        ("FAIL", "can't tell", "NOT RECORDED", False), ("FAIL", "picks worse", "NOT RECORDED", False)])
    def test_the_three_cell_consequence_table(self, verdict, paired, cell, record):
        c = rs.rs_consequence(verdict, paired)
        assert c["cell"] == cell and c["record"] is record
        if record:
            assert "forward shadow stores the rs_best-alone score, cutoff, pool size and flag" in c["text"] and "THE LINE" in c["text"] and "no order path, no money" in c["text"]
        elif paired == "picks worse":
            assert "veto" in c["text"]
        else:
            assert "ENDS" in c["text"]


# ═══ the precondition (check 2) and the once-only refusals ══════════════════════════════════════════════════════════════════════════════════
class TestRefusals:
    def test_a_missing_parent_verdict_refuses_with_exit_3_and_writes_nothing(self, tmp_path, monkeypatch, capsys):
        tree = rs_tree(tmp_path, monkeypatch)
        before = out_files(tree)
        (tree["cb702_pre"] / "out" / "aplus_verdict_pre.json").unlink()
        for extra in ((), ("--dry-run",)):
            with pytest.raises(SystemExit) as ex:
                main(tree, *extra)
            assert ex.value.code == 3 and "deciding verdicts are on file" in capsys.readouterr().err
        assert out_files(tree) == [p for p in before if not p.endswith("aplus_verdict_pre.json")]

    def test_a_cell_other_than_not_recorded_refuses(self, tmp_path, monkeypatch, capsys):
        tree = rs_tree(tmp_path, monkeypatch)
        write_parents(tree, pre=parent_verdict("pre", "PASS", "separates"), disc=parent_verdict("discovery", "PASS", "separates"))
        with pytest.raises(SystemExit) as ex:
            main(tree)
        assert ex.value.code == 3 and "reads RECORD" in capsys.readouterr().err
        write_parents(tree, pre=parent_verdict("pre", "PASS", "can't tell"))                  # a LEAD is not NOT RECORDED either
        with pytest.raises(SystemExit) as ex:
            main(tree)
        assert ex.value.code == 3 and "reads LEAD" in capsys.readouterr().err

    def test_a_next_registration_other_than_alone_c3_refuses(self, tmp_path, monkeypatch, capsys):
        tree = rs_tree(tmp_path, monkeypatch)
        rows = {"alone_c3|3": parent_row(1.0, 0.2, 7, 5), "alone_c7|3": parent_row(2.5, 0.1, 6, 6)}
        write_parents(tree, pre=parent_verdict("pre", rows=rows), disc=parent_verdict("discovery", rows=rows))
        with pytest.raises(SystemExit) as ex:
            main(tree)
        assert ex.value.code == 3 and "'alone_c7', not 'alone_c3'" in capsys.readouterr().err
        write_parents(tree, pre=parent_verdict("pre", rows={}), disc=parent_verdict("discovery", rows={}))      # no eligible row at all
        with pytest.raises(SystemExit) as ex:
            main(tree)
        assert ex.value.code == 3 and "None, not 'alone_c3'" in capsys.readouterr().err

    def test_an_a_plus_artefact_of_the_sealed_era_on_disk_refuses(self, tmp_path, monkeypatch, capsys):
        tree = rs_tree(tmp_path, monkeypatch)
        (tree["cb702"] / "out" / "trades_holdout_aplus.tsv.gz").write_bytes(b"x")
        with pytest.raises(SystemExit) as ex:
            main(tree)
        assert ex.value.code == 3 and "an A+ artefact of the sealed era is on disk" in capsys.readouterr().err

    def test_the_period_options_and_the_freeze(self, tmp_path, monkeypatch, capsys):
        tree = rs_tree(tmp_path, monkeypatch)
        before = out_files(tree)
        with pytest.raises(SystemExit) as ex:
            main(tree, period=None)
        assert ex.value.code == 2 and "--period is required" in capsys.readouterr().err
        for per in ("pre", "discovery"):                                                   # only the sealed era
            with pytest.raises(SystemExit) as ex:
                main(tree, period=per)
            assert ex.value.code == 2 and "--period is required: one of ('holdout',)" in capsys.readouterr().err
        for extra, needle in ((["--out", str(tmp_path / "x")], "--out"), (["--minutes", str(tree["cb702_pre"] / "minutes")], "--minutes"),
                              (["--prereg", "x.md"], "--prereg is honoured only"), (["--no-freeze-check"], "only together with --dry-run"), (["--keys", "com"], "--keys com")):
            with pytest.raises(SystemExit) as ex:
                main(tree, *extra)
            assert ex.value.code == 2 and needle in capsys.readouterr().err, extra
        for rel, label in (("cb702/out/candidates.tsv", "cb702/out/candidates.tsv"), ("cb702/daily_closes_all.csv.gz", "cb702/daily_closes_all.csv.gz"),
                           ("cb702/out/trades_holdout_exitpb.tsv.gz", "trades_holdout_exitpb.tsv.gz")):
            p = tmp_path / rel
            keep = p.read_bytes()
            p.write_bytes(keep + b"\n")
            with pytest.raises(SystemExit) as ex:
                main(tree)
            assert ex.value.code == 2 and f"{label} sha256 mismatch" in capsys.readouterr().err, rel
            p.write_bytes(keep)
        assert out_files(tree) == before                                                   # nothing was written by any refusal

    def test_the_engine_module_the_stage_rests_on_is_pinned(self, tmp_path, monkeypatch, capsys):
        tree = rs_tree(tmp_path, monkeypatch)
        ctx = rr.resolve(rs.RS_ALONE_READ, TA.ns(tree), rn)
        files = rr.frozen_map(rs.RS_ALONE_READ, ctx)
        assert files["aplus module"].name == "aplus_read.py" and files["spec module"].name == "rs_alone_read.py" and files["golden fixtures module"].name == "rs_alone_fixtures.py"
        assert files["rederivation module"].name == "aplus_rederive.py" and not any("minutes" in k or "profile" in k for k in files)


# ═══ STEP 0 and the dry run: features only ═════════════════════════════════════════════════════════════════════════════════════════════════
def guard_outcomes(monkeypatch):
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("an outcome column was opened"))      # noqa: E731
    monkeypatch.setattr(ap, "read_outcomes", boom)
    real_read = ap.read_table

    def guarded(path, usecols):
        if usecols is None or set(usecols) & set(ap.OUTCOME_COLS):
            raise AssertionError(f"an outcome column was opened: {path} {usecols}")
        return real_read(path, usecols)
    monkeypatch.setattr(ap, "read_table", guarded)
    real_rd = rd._read

    def guarded_rd(path, usecols):
        if set(usecols) & set(ap.OUTCOME_COLS):
            raise AssertionError(f"the re-derivation opened an outcome column: {path} {usecols}")
        return real_rd(path, usecols)
    monkeypatch.setattr(rd, "_read", guarded_rd)


class TestStep0:
    def test_dry_run_counts_the_census_and_opens_no_outcome(self, tmp_path, monkeypatch, capsys):
        tree = rs_tree(tmp_path, monkeypatch)
        guard_outcomes(monkeypatch)
        before = out_files(tree)
        assert main(tree, "--dry-run") is None
        out = capsys.readouterr().out
        assert "STEP 0 PASSED: every equality target met" in out and "RS-ALONE DRY RUN (freeze check passed" in out and "rs_best census" in out
        assert "ties at the cutoff: 0 fills" in out and "precondition: the A+ rating read" in out and "next registration alone_c3" in out
        assert "(expectation 215-279)" in out and "no other score is computed" in out
        assert out_files(tree) == before                                                   # a dry run writes nothing
        assert main(tree, "--dry-run", "--self-check") is None
        out = capsys.readouterr().out
        for needle in ("SELF-CHECK PASSED", "check 4 (b)", "check 4 (c)", "check 5 (later-fill removal)", "check 6 (counts, pool, shuffle)", "check 9 (golden tie fixtures",
                       "check 8 (re-derivation, features only)", "MATCH"):
            assert needle in out, needle
        assert out_files(tree) == before
        with pytest.raises(SystemExit):                                                    # --self-check needs --dry-run
            main(tree, "--self-check")
        assert "only together with --dry-run" in capsys.readouterr().err
        assert not [p for p in out_files(tree) if "rs_alone" in p]

    def test_a_dry_run_runs_without_a_freeze_pin_and_a_mismatch_is_reported(self, tmp_path, monkeypatch, capsys):
        tree = rs_tree(tmp_path, monkeypatch)
        rs_doc(tree).write_text("Doc.\n" + rn.FREEZE_MARK + "\n## Freeze record\n")          # a DRAFT: no pins below the marker
        with pytest.raises(SystemExit) as ex:
            main(tree, "--dry-run")
        assert ex.value.code == 2 and "footer carries no" in capsys.readouterr().err
        assert main(tree, "--dry-run", "--no-freeze-check") is None
        assert "STEP 0 PASSED" in capsys.readouterr().out
        monkeypatch.setattr(rs, "RS_EXPECTED", dict(rs.RS_EXPECTED, fills=999))
        assert main(tree, "--dry-run", "--no-freeze-check") is None
        assert "STEP 0 / SELF-CHECK FAILED" in capsys.readouterr().out

    def test_step0_mismatch_stops_the_real_run_before_any_outcome(self, tmp_path, monkeypatch, capsys):
        tree = rs_tree(tmp_path, monkeypatch)
        monkeypatch.setattr(rs, "RS_EXPECTED", dict(rs.RS_EXPECTED, weeks=7))
        guard_outcomes(monkeypatch)
        with pytest.raises(SystemExit) as ex:
            main(tree)
        assert ex.value.code == 3 and "STEP 0 FAILED" in capsys.readouterr().out
        assert not [p for p in out_files(tree) if "rs_alone_verdict" in p or "trades_holdout_rs_alone" in p]

    def test_a_fill_without_a_candidates_row_or_rs_best_fails_the_join(self, tmp_path, monkeypatch, capsys):
        tree = rs_tree(tmp_path, monkeypatch)
        p = tree["cb702"] / "out" / "candidates.tsv"
        t = rn.read_tsv(p)
        t[t["ticker"] != "F1"].to_csv(p, sep="\t", index=False, na_rep="")
        rs_doc(tree)
        guard_outcomes(monkeypatch)
        with pytest.raises(SystemExit) as ex:
            main(tree)
        o = capsys.readouterr().out
        assert ex.value.code == 3 and "STEP 0 FAILED" in o and "candidates: no row for ('F1'" in o
        t.loc[t["ticker"] == "F3", "rs_best"] = np.nan
        t.to_csv(p, sep="\t", index=False, na_rep="")
        rs_doc(tree)
        with pytest.raises(SystemExit):
            main(tree)
        assert "check 3: rs_best missing for 1 rows" in capsys.readouterr().out

    def test_the_tie_at_the_cutoff_is_counted_and_flagged_rest(self, tmp_path, monkeypatch, capsys):
        rows = fx.golden_rows(e2_rs=40, with_f6=False)
        next(r for r in rows if r.ticker == "F5").rs_best = 78.0                           # the cutoff member's own value (the 12th of 50..89)
        tree = rs_tree(tmp_path, monkeypatch, rows=rows)
        ctx, prep, cols, res, ties = _prep(tree)
        i = cols["ticker"].index("F5")
        assert bool(ties["tie"][i]) and ties["v_cut"][i] == 78.0 and int(ties["tie"].sum()) == 1
        assert rs.flags(res)[i] == "rest" and res["score"]["alone_c3"][i] == 28.5 / 40 and res["cutoff"][("alone_c3", 3)][i] == 28 / 39
        assert rs.tie_rule_problems(cols, res, ties) == []
        res["flag"][("alone_c3", 3)][i] = "aplus"                                           # an engine that let the tied fill through is named
        assert any("tied with their cutoff member" in x for x in rs.tie_rule_problems(cols, res, ties))
        assert main(tree, "--dry-run") is None
        o = capsys.readouterr().out
        assert "ties at the cutoff: 1 fills sit exactly at their cutoff member's value (1 flagged rest, 0 A+)" in o


# ═══ the full read, once-only, the artefact names ═════════════════════════════════════════════════════════════════════════════════════════
class TestFullRead:
    def test_the_full_read_writes_its_own_names_only_and_reaches_verdict_match(self, tmp_path, monkeypatch, capsys):
        tree = rs_tree(tmp_path, monkeypatch)
        before = out_files(tree)
        assert main(tree) is None
        o = capsys.readouterr().out
        assert "VERDICT MATCH" in o and "RE-DERIVATION (pandas, no runner code)" in o and "WROTE" in o
        new = sorted(set(out_files(tree)) - set(before))
        out, small = tree["cb702"] / "out", rn.HERE / "out"
        want = sorted(p.as_posix() for p in (out / "trades_holdout_rs_alone.tsv.gz", out / "rs_alone_report_holdout.tsv", out / "rs_alone_report_holdout.txt",
                                             out / "rs_alone_verdict_holdout.json", out / "rs_alone_verdict_holdout.txt", small / "rs_alone_verdict_holdout.txt",
                                             small / "rs_alone_report_holdout.tsv", small / "rs_alone_report_holdout.txt", small / "rs_alone_summary_holdout.txt"))
        assert new == want                                                                 # exactly its own artefact names
        assert not [p for p in out_files(tree) if "aplus" in Path(p).name and "holdout" in Path(p).name]       # NO aplus_*holdout* artefact, in either dir
        assert ap.holdout_artefacts(rr.resolve(rs.RS_ALONE_READ, TA.ns(tree), rn)) == []
        vj = json.loads((out / "rs_alone_verdict_holdout.json").read_text())
        t = rn.read_tsv(out / "trades_holdout_rs_alone.tsv.gz")
        n_ap = int((t["flag_alone_c3_n3"] == "aplus").sum())
        assert vj["spec"] == "alone_c3" and vj["N"] == 3 and vj["rederivation"] == "MATCH" and vj["verdict"] == "CAN'T TELL" and vj["n"] == vj["aplus_n"] == n_ap and 4 <= n_ap < 30
        assert vj["paired"]["key"] == "aplus_pair|holdout|3|alone_c3" and vj["consequence"]["cell"] == "NOT RECORDED" and isinstance(vj["outlier_test"]["met"], bool) and vj["outlier_test"]["lhs"] == vj["outlier_test"]["count_ge10"] * vj["c0"]["n"]
        assert vj["precondition"]["next_registration"] == "alone_c3" and vj["step0"]["fills"] == 108 and vj["step0"]["ties_at_cutoff"] == 0
        day_e = t[t["E"] == fx.CAL[fx.E_CI]]
        assert len(t) == 128 and set(day_e.loc[day_e["flag_alone_c3_n3"] == "aplus", "ticker"]) == {"F1", "F3", "F7"} and list(day_e.loc[day_e["flag_alone_c3_n3"] == "capped", "ticker"]) == ["F4"]
        assert set(t.loc[t["E"] == fx.CAL[fx.E2_CI], "ticker"][t["flag_alone_c3_n3"] == "aplus"]) == {"F8"}
        assert t["flag_alone_c3_n3"][t["eligible"] == 0].isna().all() and set(t["ticker"][t["eligible"] == 0]) == {f"P{i:02d}" for i in range(20)}
        assert not [c for c in t.columns if c.startswith(("score_core", "pct_c1", "pct_c2", "pct_c4", "pct_c6", "pct_c7", "flag_core"))]          # no other score is in the table
        rep = rn.read_tsv(out / "rs_alone_report_holdout.tsv")
        assert list(rep["spec"]) == ["alone_c3"] and list(rep["N"]) == [3] and list(rep["key"]) == ["aplus|holdout|3|alone_c3"] and list(rep["period"]) == ["holdout"]
        assert "CONSEQUENCE: CAN'T TELL: NOT RECORDED" in (small / "rs_alone_report_holdout.txt").read_text()
        assert "check 8 (re-derivation): VERDICT MATCH" in (small / "rs_alone_report_holdout.txt").read_text()

    def test_the_read_is_once_only(self, tmp_path, monkeypatch, capsys):
        tree = rs_tree(tmp_path, monkeypatch)
        assert main(tree) is None
        capsys.readouterr()
        with pytest.raises(SystemExit) as ex:
            main(tree)
        assert ex.value.code == 2 and "read ONCE per period" in capsys.readouterr().err
        out = tree["cb702"] / "out"
        for q in list(out.glob("*rs_alone*")) + list((rn.HERE / "out").glob("rs_alone_*")):
            q.unlink()
        (out / "trades_holdout_rs_alone.tsv.gz.partial").write_bytes(b"x")                    # a crashed run's .partial
        with pytest.raises(SystemExit) as ex:
            main(tree)
        assert ex.value.code == 2 and "CRASHED" in capsys.readouterr().err

    def test_each_final_artefact_alone_refuses_a_second_run(self, tmp_path, monkeypatch, capsys):
        tree = rs_tree(tmp_path, monkeypatch)
        out = tree["cb702"] / "out"
        for name in ("trades_holdout_rs_alone.tsv.gz", "rs_alone_verdict_holdout.json", "rs_alone_verdict_holdout.txt", "rs_alone_report_holdout.tsv", "rs_alone_report_holdout.txt"):
            (out / name).write_bytes(b"x")
            with pytest.raises(SystemExit) as ex:
                main(tree)
            assert ex.value.code == 2 and name in capsys.readouterr().err, name
            (out / name).unlink()
        (rn.HERE / "out" / "rs_alone_verdict_holdout.txt").write_text("x")                  # the small-dir verdict copy refuses too
        with pytest.raises(SystemExit) as ex:
            main(tree)
        assert ex.value.code == 2 and "rs_alone_verdict_holdout.txt" in capsys.readouterr().err

    def test_check_failures_write_nothing_and_exit_3(self, tmp_path, monkeypatch, capsys):
        tree = rs_tree(tmp_path, monkeypatch)
        monkeypatch.setattr(fxr, "run_golden", lambda: ["T1: a hand expectation differs"])
        with pytest.raises(SystemExit) as ex:
            main(tree)
        o = capsys.readouterr().out
        assert ex.value.code == 3 and "check 9 (golden fixtures): T1: a hand expectation differs" in o and "no outcome column was opened" in o
        assert not [p for p in out_files(tree) if "trades_holdout_rs_alone" in p or "rs_alone_verdict_holdout" in p]

    def test_the_c0_integers_must_describe_the_table(self, tmp_path, monkeypatch, capsys):
        tree = rs_tree(tmp_path, monkeypatch)
        monkeypatch.setitem(ap.C0_PUBLISHED, "holdout", dict(ap.C0_PUBLISHED["holdout"], n=1))
        with pytest.raises(SystemExit) as ex:
            main(tree)
        assert ex.value.code == 3 and "C0 INTEGERS DIFFER" in capsys.readouterr().out
        assert not [p for p in out_files(tree) if "rs_alone_verdict_holdout" in p]

    def test_a_rederivation_that_differs_writes_nothing(self, tmp_path, monkeypatch, capsys):
        tree = rs_tree(tmp_path, monkeypatch)
        real = rd.rederive_alone_c3

        def broken(*a, **k):
            r = real(*a, **k)
            r["aplus"] = set(list(r["aplus"])[:-1])
            return r
        monkeypatch.setattr(rd, "rederive_alone_c3", broken)
        with pytest.raises(SystemExit) as ex:
            main(tree)
        o = capsys.readouterr().out
        assert ex.value.code == 3 and "MISMATCH: the A+ set differs on (alone_c3, N = 3)" in o and "the result is NOT written" in o
        assert not [p for p in out_files(tree) if "trades_holdout_rs_alone" in p or "rs_alone_verdict_holdout" in p or "rs_alone_report_holdout" in p]
        monkeypatch.setattr(rd, "rederive_alone_c3", real)

        def broken_n(*a, **k):                                                              # the same set, a different mean R: named by component, never by value
            r = real(*a, **k)
            r["core"]["mean_r"] += 0.01
            return r
        monkeypatch.setattr(rd, "rederive_alone_c3", broken_n)
        with pytest.raises(SystemExit):
            main(tree)
        o = capsys.readouterr().out
        assert "alone_c3 N = 3 mean_r differs from the re-derivation" in o and "the result is NOT written" in o

    def test_the_rederivation_imports_no_runner_code(self):
        # source-pin-ok: the registration requires the re-derivation to use NO runner code - its import list IS the behaviour under test
        tree = ast.parse(Path(rd.__file__).read_text())
        names = {n.module.split(".")[-1] if isinstance(n, ast.ImportFrom) else a.name.split(".")[-1] for n in ast.walk(tree)
                 if isinstance(n, (ast.Import, ast.ImportFrom)) for a in (n.names if isinstance(n, ast.Import) else [n])}
        assert not names & {"runner", "aplus_read", "registered_read", "consolidation_breakout", "aplus_fixtures", "rs_alone_read", "rs_alone_fixtures"}, names

    def test_the_rederivation_agrees_with_the_engine_on_the_tree(self, tmp_path, monkeypatch):
        tree = rs_tree(tmp_path, monkeypatch)
        ctx, prep, cols, res, ties = _prep(tree)
        r = rd.rederive_alone_c3(prep["paths"], "holdout", ap.C0_PUBLISHED["holdout"], outcomes=False, log=lambda *a: None)
        assert r["aplus"] == ap.aplus_set(cols, res, "alone_c3", 3) and rs.set_match_problems(cols, res, r) == []
        assert "core" not in r and "paired" not in r                                          # no outcome path was taken


# ═══ every check's failing case ════════════════════════════════════════════════════════════════════════════════════════════════════════
class TestFailingCases:
    def test_the_checks_pass_on_the_synthetic_population(self, tmp_path, monkeypatch):
        tree = rs_tree(tmp_path, monkeypatch)
        ctx, prep, cols, res, ties = _prep(tree)
        for fn in (lambda: rs.check4b_columns(ctx, prep, cols, res), lambda: rs.check4c_after_d(cols, res), lambda: rs.check5_later_fills(cols, res),
                   lambda: rs.check6_counts_pool_shuffle(cols, res)):
            p, lines = fn()
            assert p == [] and lines
        p, lines = rs.run_checks(ctx, prep, cols, res, ties, lambda *a: None)
        assert p == [] and any("golden tie fixtures" in x for x in lines)

    @pytest.mark.parametrize("col", ["close_E", "vol_E"])
    def test_check4b_a_feature_that_reads_an_e_day_column(self, tmp_path, monkeypatch, col):
        """The realistic break: the usecols widened by an E-day column and rs_best built from it. The run itself is self-consistent; only the source
        shuffle moves it."""
        tree = rs_tree(tmp_path, monkeypatch)
        monkeypatch.setattr(rs, "RS_CAND_COLS", rs.RS_CAND_COLS + [col])
        real = rs.build_cols

        def broken(ctx, prep):
            out = real(ctx, prep)
            la = {(r.ticker, r.D, r.E, r.K): getattr(r, col) for r in prep["cands"][["ticker", "D", "E", "K", col]].itertuples(index=False)}
            c = out["cols"]
            c["rs_best"] = [la.get((c["ticker"][i], c["D"][i], c["E"][i], c["K"][i])) for i in range(len(c["E"]))]
            return out
        monkeypatch.setattr(rs, "build_cols", broken)
        ctx, prep, cols, res, ties = _prep(tree)
        assert col in prep["cands"].columns
        p, _ = rs.check4b_columns(ctx, prep, cols, res)
        assert any("check 4 (b)" in x and "permuted" in x for x in p), p

    def test_check4b_an_outcome_column_in_the_fills_usecols(self, tmp_path, monkeypatch):
        tree = rs_tree(tmp_path, monkeypatch)
        ctx, prep, cols, res, ties = _prep(tree)
        assert rs.check4b_columns(ctx, prep, cols, res)[0] == []
        monkeypatch.setattr(ap, "FILL_COLS", ap.FILL_COLS + ["realized_r"])
        ctx, prep, cols, res, ties = _prep(tree)
        p, _ = rs.check4b_columns(ctx, prep, cols, res)
        assert any("check 4 (b)" in x and "outcome columns ['realized_r']" in x for x in p), p

    def test_check4c_a_pool_that_reaches_past_the_fills_own_day(self, tmp_path, monkeypatch):
        """A pool that includes the rows AFTER the day (the 40 fills that follow it): the fill's score moves when those rows are randomised."""
        tree = rs_tree(tmp_path, monkeypatch)
        ctx, prep, cols, res, ties = _prep(tree)
        assert rs.check4c_after_d(cols, res)[0] == []
        real = ap.rate_day

        def leaky(X, pool, day, specs, ns, floor=ap.POOL_FLOOR, ranks=ap.CUTOFF_RANK):
            later = np.arange(int(day.max()) + 1, min(int(day.max()) + 41, len(X)))
            return real(X, np.concatenate([pool, later]), day, specs, ns, floor, ranks)
        monkeypatch.setattr(ap, "rate_day", leaky)
        res_leak = rs.rate_alone(cols)
        p, _ = rs.check4c_after_d(cols, res_leak)
        assert p and "check 4 (c)" in p[0] and "randomised" in p[0]

    def test_check4c_randomises_only_rows_after_d(self, tmp_path, monkeypatch):
        tree = rs_tree(tmp_path, monkeypatch)
        ctx, prep, cols, res, ties = _prep(tree)
        i = cols["ticker"].index("F1")
        pert = rs.perturb_after_d(cols, cols["D"][i], np.random.default_rng(1))
        later = [j for j in range(len(cols["D"])) if cols["D"][j] > cols["D"][i]]
        assert later and all(pert["rs_best"][j] != cols["rs_best"][j] or pert["ticker"][j] != cols["ticker"][j] for j in later)
        same = [j for j in range(len(cols["D"])) if cols["D"][j] <= cols["D"][i]]
        assert all(pert[k][j] == cols[k][j] for k in ("rs_best", "ticker", "fill_minute", "E_ci", "week") for j in same)
        assert all(pert["E_ci"][j] == cols["E_ci"][j] and pert["week"][j] == cols["week"][j] for j in later)       # the calendar facts stay

    def test_check5_a_pool_that_includes_the_days_own_fills(self, tmp_path, monkeypatch):
        tree = rs_tree(tmp_path, monkeypatch)
        ctx, prep, cols, res, ties = _prep(tree)
        assert rs.check5_later_fills(cols, res)[0] == []
        real = ap.pool_percentiles
        monkeypatch.setattr(ap, "pool_percentiles", lambda X, pool, day, floor=ap.POOL_FLOOR: real(X, np.concatenate([pool, day]), day, floor))
        p, _ = rs.check5_later_fills(cols, rs.rate_alone(cols))
        assert p and "check 5" in p[0]

    def test_check6_counts_a_week_with_more_than_n_a_pool_window_of_the_wrong_length_and_an_order_dependent_engine(self, tmp_path, monkeypatch):
        tree = rs_tree(tmp_path, monkeypatch)
        ctx, prep, cols, res, ties = _prep(tree)
        assert rs.check6_counts_pool_shuffle(cols, res)[0] == []
        fl = rs.flags(res)
        i = int(np.flatnonzero(fl == "capped")[0])
        fl[i] = "aplus"                                                                    # a 4th A+ in a week whose cap is 3
        assert any("has 4 A+" in x for x in rs.check6_counts_pool_shuffle(cols, res)[0])
        fl[i] = "capped"
        res100 = ap.rate_population(cols, rs.RS_SPECS, rs.RS_NS, pool_sessions=100)         # the fixture's days sit 100 sessions apart: a 100-session window reaches the previous one
        assert any("independent count" in x for x in rs.check6_counts_pool_shuffle(cols, res100)[0])
        cols["week"][0] = "2000-W01"
        assert any("ISO week" in x for x in rs.check6_counts_pool_shuffle(cols, res)[0])
        cols["week"][0] = ap.iso_week(cols["E"][0])
        real = rs.rate_alone

        def order_dependent(c):
            r = real(c)
            r["flag"][("alone_c3", 3)][7] = "aplus"                                          # whichever fill sits at position 7
            return r
        monkeypatch.setattr(rs, "rate_alone", order_dependent)
        p, _ = rs.check6_counts_pool_shuffle(cols, order_dependent(cols))
        assert any("shuffle" in x for x in p)

    def test_the_join_checks(self, tmp_path, monkeypatch):
        tree = rs_tree(tmp_path, monkeypatch)
        ctx, prep, cols, res, ties = _prep(tree)
        built = {"problems": []}
        assert rs.join_problems(cols, built) == []
        cols["E_ci"][0] = -1
        cols["fill_minute"][1] = 4
        cols["ticker"][3], cols["E"][3] = cols["ticker"][2], cols["E"][2]
        p = rs.join_problems(cols, built)
        assert any("SPY calendar" in x for x in p) and any("fill_minute < 5" in x for x in p) and any("not unique" in x for x in p)

    def test_the_tie_census_is_anchored_to_the_engines_own_cutoff(self):
        rows = fxr.golden_rows()
        cols = fxr.cols_of(rows)
        res = rs.rate_alone(cols)
        assert rs.ties_at_cutoff(cols, res)["problems"] == []
        res["cutoff"][("alone_c3", 3)][:] = res["cutoff"][("alone_c3", 3)] + 0.01            # a cutoff that is not the 12th member's reference score is named
        assert rs.ties_at_cutoff(cols, res)["problems"]

    def test_the_census_reports_the_top_values_and_the_expected_range(self):
        rows = fxr.golden_rows()
        cols = fxr.cols_of(rows)
        c = rs.rs_census(cols)
        assert c["rs_present"] == 14 and c["rs_missing"] == 0 and c["rs_max"] == 100.0 and c["rs_at_100"] == 3
        assert "rs_best census" in rs.rs_census_text(c)


def test_the_registry_holds_the_four_registered_reads():
    assert set(rn.REGISTERED_READS) == {"aplus-read", "aplus-confirm", "aplus-hindsight", "rs-alone-read"}
    assert "rs-alone-read" not in rn.BUILTIN_STAGES
