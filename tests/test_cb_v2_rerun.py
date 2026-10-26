"""#705 v2 re-run (docs/analysis/cb_2017_21_rerun_v2_prereg_2026-10-25.md §4 B1-B9) - the proofs the registration's WOULD-FAIL-IF column names, on
SYNTHETIC data (a pre-era tree: tickers TSLA / Y restored, Z shared, two-row tl bases + a com base, the hourly-close break, every arm maturing) plus
read-only checks against the real repo (the default paths, the scaffold's computed names, the CLI refusing the old file). No real outcome is
computed here; the parity run on a copy of the OLD file is `_705_rerun_v2_1023/v2_parity_old.py` (its receipt beside it)."""
from __future__ import annotations

import argparse
import ast
import gzip
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from agents.market_intelligence import consolidation_breakout as cb
from scripts.probes._cb_backtest import fetch_minutes as fm
from scripts.probes._cb_backtest import registered_read as rr
from scripts.probes._cb_backtest import runner as rn
from scripts.probes._cb_backtest import v2_chain as v2c
from scripts.probes._cb_backtest import v2_rerun_read as v2

try:
    import test_cb_backtest_runner as T
except ImportError:                                              # pragma: no cover
    from tests import test_cb_backtest_runner as T

REAL_REPO = Path(__file__).resolve().parents[1]                 # the checkout under test (CI and the pre-push hook run it from other paths)
REAL_DATA = Path("/Users/alvinfung/apollo_data")
# The code tree 04_relaunch.sh guards: its REAL_B literal. NOT REAL_REPO / "scripts" / "probes" - REAL_REPO is whatever checkout runs the suite,
# and the pre-push hook (dirty tree) and CI run it from another path, where that copy is a scratch tree the guard rightly lets through.
REAL_PROBES = Path("/Users/alvinfung/apollo_the_wise/scripts/probes")
PRE_START = T.dt.date(2019, 10, 31)                              # E1 = 2020-05-28, E2 = 2020-06-01 (the exit read's TSLA check); both windows carry the bases
E1, E2 = T.H60_E1, T.H60_E2
# The doc AS REGISTERED: commit db876b2a's copy, byte for byte (§5's v2 cells still (B2), the footer empty); its body sha is
# v2_freeze_diff_check.REG_BODY_SHA. The synthetic tree is built on THIS copy and §5 filled from the fixture's own stage 0 - the live doc's §5
# carries the real stage-0 counts since cbf0ea76, and a synthetic stage 2 compared against those would refuse ('§5 1583 vs stage 0 2').
REGISTERED_DOC = Path(__file__).resolve().parent / "fixtures" / "cb_rerun_v2_doc_registered.md"
REGISTRATION_COMMIT, ROUND1_COMMIT = "db876b2a", "af2b17db"


def registered_doc_text() -> str:
    return REGISTERED_DOC.read_text(encoding="utf-8")


def _has_commit(sha: str) -> bool:
    """False on a shallow clone (GitHub CI checks out depth 1): the commit object is not in the checkout."""
    return subprocess.run(["git", "-C", str(REAL_REPO), "cat-file", "-e", f"{sha}^{{commit}}"], capture_output=True).returncode == 0


# ═══ the synthetic pre-era tree ════════════════════════════════════════════════════════════════════════════════════════════════════
def _bars():
    """T._h60_bars on pre-era dates: flat $10, E1 a poke, E2 the break, d1 +2R, d3 the breakeven stop - every arm matures."""
    n = 300
    d = T._weekdays(n, PRE_START)
    b = T._h60_bars()
    return cb.daily_bars_from_arrays(d, b.o.copy(), b.h.copy(), b.l.copy(), b.c.copy(), np.full(n, 1e6))


def _export(path: Path, bars, tickers) -> None:
    with gzip.open(path, "wt") as fh:
        for t in ("SPY",) + tuple(tickers):
            for k in range(len(bars)):
                fh.write(f"{t},{bars.dates[k].isoformat()},{bars.o[k]},{bars.h[k]},{bars.l[k]},{bars.c[k]},{bars.v[k]}\n")


def _cands(bars, t: str) -> list:
    P = E1 - 20
    pole = bars.dates[P].isoformat()
    c1 = T._p5_cand(bars, E1, K="tl", split="pre", pivot=10.25, high_E=10.30, low_E=9.85, open_E=10.0, close_E=10.05, ticker=t, base_id=f"{t}|p")
    c2 = T._p5_cand(bars, E2, K="tl", split="pre", pivot=10.25, high_E=10.6, low_E=10.1, open_E=10.2, close_E=10.5, retrigger=1, retrigger_chain=1,
                    ticker=t, base_id=f"{t}|p")
    cc = T._p5_cand(bars, E1, K="com", split="pre", pivot=10.02, high_E=10.30, low_E=9.85, open_E=10.0, close_E=10.05, ticker=t, base_id=f"{t}|p")
    for c, e in ((c1, E1), (c2, E2), (cc, E1)):
        c["pole_date"] = pole
        c["base_depth"] = 1.0 - float(bars.l[P + 1:e].min()) / float(bars.h[P])
    for cell in rn.CELL_NAMES:
        c2["first_" + cell], c2["first_chain_" + cell] = 0, 0
    return [c1, c2, cc]


def _watch(bars, t: str) -> list:
    P = E1 - 20
    pole = bars.dates[P].isoformat()
    return [{"ticker": t, "watch_date": bars.dates[e - 1].isoformat(), "ci": e - 1, "i": e - 1, "pole_date": pole, "pole_high": float(bars.h[P]),
             "base_low": float(bars.l[P + 1:e].min()), "pivot_tl": 10.25, "tl_slope_pct": 0.0, "tl_anchor_idx": P, "pivot_com": 10.02} for e in (E1, E2)]


def build_tree(tmp_path: Path, monkeypatch, tickers=("TSLA", "Y", "Z"), restored=("TSLA", "Y"), empty_minutes=(), extra_export=()) -> dict:
    """root/cb702 (the --data dir; holdout + discovery verdict files planted - never to be opened), root/cb702_pre_v2 (the data), root/cb702_pre (the
    OLD file: a symbol guard WITHOUT the restored tickers, its pre verdicts, its STEP 0 table), root/repo (the real module copied: the hard pin; every
    other pinned code file a stub), rn.REPO / rn.HERE pointed at them, and the four specs re-made on the fixture export's sha (the ONE injection)."""
    bars = _bars()
    root = tmp_path
    d702, v2d, old = root / "cb702", root / v2.V2_NAME, root / v2.OLD_NAME
    for d in (d702 / "out", v2d / "out", v2d / "minutes", v2d / "audit_1023", old / "out"):
        d.mkdir(parents=True, exist_ok=True)
    for name in ("h60_verdict_holdout.json", "exitpb_verdict_holdout.json", "h60_verdict_discovery.json", "exitpb_verdict_discovery.json"):
        (d702 / "out" / name).write_text('{"sealed": true}\n')                        # a body that opens one of these fails the open audit
    _export(v2d / "daily_closes_all.csv.gz", bars, tuple(tickers) + tuple(extra_export))   # extra_export: printing names with no candidate
    (v2d / "sessions.txt").write_text("".join(f"{x.isoformat()}\n" for x in bars.dates))
    every = ("SPY",) + tuple(tickers) + tuple(extra_export)
    (v2d / "symbol_guard.tsv").write_text("symbol\tbreaks\n" + "".join(f"{t}\t\n" for t in every))
    (old / "symbol_guard.tsv").write_text("symbol\tbreaks\n" + "".join(f"{t}\t\n" for t in every if t not in restored))
    (old / "out" / "h60_verdict_pre.json").write_text(json.dumps({"period": "pre", "windows": {"pre": {"c1_mean_r": 0.5, "delta_c1": 0.1}}}) + "\n")
    (old / "out" / "exitpb_verdict_pre.json").write_text(json.dumps({"period": "pre", "delta_c1": {"mean": -0.1}}) + "\n")
    cands = [c for t in tickers for c in _cands(bars, t)]
    rn.write_tsv(v2d / "out" / "candidates_tl_com.tsv", cands, list(cands[0].keys()))
    wcols = ["ticker", "watch_date", "ci", "i", "pole_date", "pole_high", "base_low", "pivot_tl", "tl_slope_pct", "tl_anchor_idx", "pivot_com"]
    rn.write_tsv(v2d / "out" / "watch_tl_com.tsv.gz", [w for t in tickers for w in _watch(bars, t)], wcols, gz=True)
    md = v2d / "minutes"
    e1, e2 = bars.dates[E1].isoformat(), bars.dates[E2].isoformat()
    done = []
    for t in tickers:
        if t in empty_minutes:
            done += [f"{e1}|{t}|0|empty", f"{e2}|{t}|0|empty"]
            continue
        fm._append_gz(md / f"{e1}.psv.gz", T._minute_lines(t, T._h60_minutes_e1()))
        fm._append_gz(md / f"{e2}.psv.gz", T._minute_lines(t, T._h60_minutes_e2()))
        done += [f"{e1}|{t}|390|ok", f"{e2}|{t}|390|ok"]
    (md / "_done.psv").write_text("\n".join(done) + "\n")
    repo = root / "repo"
    (repo / "docs" / "analysis").mkdir(parents=True)
    (repo / v2.MODULE_REL).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REAL_REPO / v2.MODULE_REL, repo / v2.MODULE_REL)                  # the real module: its sha is the hard pin
    doc_text = registered_doc_text()                                                  # the doc as registered: §5 unfilled, filled below from stage 0
    (repo / "docs" / "analysis" / v2.V2_DOC).write_text(doc_text.split(rn.FREEZE_MARK)[0] + rn.FREEZE_MARK + "\n## Freeze record\n", encoding="utf-8")
    monkeypatch.setattr(rn, "REPO", repo)
    monkeypatch.setattr(rn, "HERE", root / "hereroot")
    (rn.HERE / "out").mkdir(parents=True)
    sha = rn.sha256_file(v2d / "daily_closes_all.csv.gz")
    for name, spec in v2.make_specs(export_sha=sha).items():
        monkeypatch.setitem(rn.REGISTERED_READS, name, spec)
    tree = {"root": root, "cb702": d702, "v2": v2d, "old": old, "repo": repo, "bars": bars, "tickers": tickers, "restored": restored, "export_sha": sha}
    return tree


def argv(tree, stage, *extra):
    return [stage, "--data", str(tree["cb702"]), "--data-pre", str(tree["v2"]), "--period", "pre", "--workers", "1", *extra]


def run(tree, stage, *extra) -> int:
    try:
        r = rn.main(argv(tree, stage, *extra))
        return int(r or 0)
    except SystemExit as ex:
        return int(ex.code or 0)


def ctx_of(tree, stage="v2-pre-read"):
    args = rn_args(tree)
    return rr.resolve(rn.REGISTERED_READS[stage], args, rn)


def rn_args(tree, **kw):
    ns = dict(data=str(tree["cb702"]), data_pre=str(tree["v2"]), period="pre", out=None, small_out=None, minutes=None, workers=1, dry_run=False,
              print_pins=False, prereg=None, no_freeze_check=False, keys=None, levels=None, limit_dates=0, no_close=False, no_apollo=False, trades=None,
              parity_only=False, self_check=False)
    ns.update(kw)
    return argparse.Namespace(**ns)


def stub_missing_pins(tree) -> None:
    """Every path the §8 map pins that the fixture does not carry gets a stub (the code files, the v2 sidecars, the read dirs' numbers files)."""
    ctx = ctx_of(tree)
    for label, p in rr.frozen_map(rn.REGISTERED_READS["v2-pre-read"], ctx).items():
        p = Path(p)
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"stub {label}\n")


def fill_and_freeze(tree) -> Path:
    """§5 filled from stage 0's counts (the main loop's step), then the footer pinned to the tree as it is now (`--print-pins` + the doc body)."""
    doc = tree["repo"] / "docs" / "analysis" / v2.V2_DOC
    counts = json.loads((tree["v2"] / "out" / v2.STEP0_OUT_SUB / v2.STEP0_COUNTS).read_text())
    body = doc.read_text(encoding="utf-8").split(rn.FREEZE_MARK)[0]
    if "(B2)" in body.split("## 5.")[1].split("## 6.")[0]:
        body = v2.fill_section5(body + rn.FREEZE_MARK, counts).split(rn.FREEZE_MARK)[0]
    return repin(tree, body)


def repin(tree, body=None) -> Path:
    doc = tree["repo"] / "docs" / "analysis" / v2.V2_DOC
    if body is None:
        body = doc.read_text(encoding="utf-8").split(rn.FREEZE_MARK)[0]
    stub_missing_pins(tree)
    ctx = ctx_of(tree)
    pins = rn.pin_lines(ctx.data, ctx.repo, files=rr.frozen_map(rn.REGISTERED_READS["v2-pre-read"], ctx))
    doc.write_text(body + rn.FREEZE_MARK + "\n## Freeze record\n" + "\n".join(pins + [f"- doc body sha256: `{rn.doc_body_sha(body)}`"]) + "\n", encoding="utf-8")
    return doc


def chain(tree, upto="v2-exit-read") -> dict:
    rcs = {}
    for stage in ("v2-h60-step0", "v2-pre-read", "v2-h60-read", "v2-exit-read"):
        if stage == "v2-pre-read":
            fill_and_freeze(tree)
        rcs[stage] = run(tree, stage)
        assert rcs[stage] == 0, (stage, rcs)
        if stage == upto:
            break
    return rcs


# ═══ B1: the chain runs end to end on the fixture, through the CLI, and the stage-0 copies survive stage 2 ═════════════════════════════
def test_the_four_v2_stages_run_in_order_and_stage_0s_copies_survive_stage_2(tmp_path, monkeypatch, capsys):
    tree = build_tree(tmp_path, monkeypatch)
    v2d, small = tree["v2"], rn.HERE / "out" / v2.SMALL_SUB
    assert run(tree, "v2-h60-step0") == 0
    out0, small0 = v2d / "out" / v2.STEP0_OUT_SUB, rn.HERE / "out" / v2.STEP0_SMALL_SUB
    s0_text = (out0 / "h60_step0_pre.txt").read_text()
    assert "NO REGISTERED TABLE YET" in s0_text and "EQUAL to the registration's table" not in s0_text
    pinned = {p: rn.sha256_file(p) for p in (out0 / "h60_step0_pre.tsv.gz", out0 / "h60_step0_pre.txt", out0 / v2.STEP0_COUNTS, small0 / "h60_step0_pre.txt")}
    counts = json.loads((out0 / v2.STEP0_COUNTS).read_text())
    assert counts["b8"]["pre"] == {"shared": 1, "restored": 2} and counts["table"]["pre"]["C0"] == 3 and counts["table"]["pre"]["tl_rows"] == 6
    assert not (v2d / "out" / "h60_step0_pre.tsv.gz").exists()                      # stage 0 never writes the name stage 2 writes
    fill_and_freeze(tree)
    for stage in ("v2-pre-read", "v2-h60-read", "v2-exit-read"):
        assert run(tree, stage) == 0, (stage, capsys.readouterr())
    for p, h in pinned.items():
        assert rn.sha256_file(p) == h, f"{p} changed after stage 2"
    s2 = (v2d / "out" / "h60_step0_pre.txt").read_text()
    assert "REGISTERED TABLE CHECK (check 5) - window pre: EQUAL to the registration's table" in s2
    assert "REGISTERED TABLE CHECK (check 5) - window 2020-21: EQUAL to the registration's table" in s2
    for name in v2.PRE_OUTPUTS + v2.H60_OUTPUTS + v2.EXIT_OUTPUTS:
        assert (v2d / "out" / name).exists(), name
    for name in v2.PRE_SMALL + v2.H60_SMALL + v2.EXIT_SMALL:
        assert (small / name).exists(), name
    for tag in ("v2_pre", "v2_h60", "v2_exit"):                                       # the scaffold's own files: under the v2 tags only
        assert (rn.HERE / "out" / f"{tag}_summary_pre.txt").exists()
    assert json.loads((v2d / "out" / "v2_h60_verdict_pre.json").read_text()) == json.loads((v2d / "out" / "h60_verdict_pre.json").read_text())
    assert json.loads((v2d / "out" / "v2_exit_verdict_pre.json").read_text()) == json.loads((v2d / "out" / "exitpb_verdict_pre.json").read_text())
    rows = v2c.manifest_rows(v2d / "out" / v2c.MANIFEST_NAME)
    assert {r["stage"] for r in rows} == {"v2-pre-read", "v2-h60-read", "v2-exit-read"}
    assert {r["label"] for r in rows} == {v2.out_label(n) for n in v2.PRE_OUTPUTS + v2.H60_OUTPUTS + v2.EXIT_OUTPUTS} | \
        {v2.small_label(n) for n in v2.PRE_SMALL + v2.H60_SMALL + v2.EXIT_SMALL}                       # every out AND small output, once each
    assert len(rows) == len({r["label"] for r in rows})
    # nothing landed under the finished stages' fixed small names
    for name in ("p5_report_pre.tsv", "h60_step0_pre.txt", "h60_report_pre.txt", "exitpb_report_pre.txt", "minute_summary_pre_tl_com.txt"):
        assert not (rn.HERE / "out" / name).exists() or name == "p5_report_pre.tsv" and (rn.HERE / "out" / name).read_text().startswith("stub"), name


# ═══ B1: refusals of the CLI path, the scaffold's names, once-only including v2_1025/ ═════════════════════════════════════════════════════
@pytest.mark.skipif(not (REAL_DATA / "cb702_pre" / "daily_closes_all.csv.gz").is_file(), reason="the real old export is not on this machine")
@pytest.mark.parametrize("stage", ["v2-h60-step0", "v2-pre-read", "v2-h60-read", "v2-exit-read"])
def test_the_registered_cli_refuses_the_old_file(stage, capsys):
    """The REGISTERED specs (no injection): --data-pre left to its default (the sibling cb702_pre) or pointed at cb702_pre - the export hard pin
    refuses before anything opens, even a dry run."""
    for extra in ([], ["--data-pre", str(REAL_DATA / "cb702_pre")]):
        with pytest.raises(SystemExit) as ex:
            rn.main([stage, "--data", str(REAL_DATA / "cb702"), "--period", "pre", "--dry-run", *extra])
        assert ex.value.code == 2
        assert "v2 export (cb702_pre_v2/daily_closes_all.csv.gz) sha256" in capsys.readouterr().err
    assert rn.REGISTERED_READS[stage] is v2.REGISTERED[stage]


def test_every_tag_starts_with_v2_and_the_computed_names_do_not_exist_today():
    specs = v2.REGISTERED
    assert all(s.tag.startswith("v2") for s in specs.values()) and set(specs) <= set(rn.REGISTERED_READS)
    assert not set(s.tag for s in specs.values()) & {"h60", "exitpb", "p5", "pre"}
    small, out = REAL_REPO / "scripts/probes/_cb_backtest/out", REAL_DATA / v2.V2_NAME / "out"
    if (out / v2c.MANIFEST_NAME).exists() or (out / v2.STEP0_OUT_SUB).exists() or (small / v2.SMALL_SUB).exists() or \
            any((small / f"{s.tag}_summary_pre.txt").exists() for s in specs.values()):
        pytest.skip("the chain has started (stage 0's dir, the manifest, or the v2 printouts committed under _cb_backtest/out/ exist): "
                    "the names exist by design")
    names = [small / f"{s.tag}_{k}_pre.txt" for s in specs.values() for k in ("summary", "verdict")]
    names += [out / f"{s.tag}_verdict_pre.{x}" for s in specs.values() for x in ("json", "txt")]
    names += [out / n for n in v2.STEP0_OUTPUTS + v2.PRE_OUTPUTS + v2.H60_OUTPUTS + v2.EXIT_OUTPUTS]
    names += [small / v2.SMALL_SUB / n for n in v2.STEP0_SMALL + v2.PRE_SMALL + v2.H60_SMALL + v2.EXIT_SMALL]
    assert [p for p in names if p.exists()] == []


@pytest.mark.parametrize("stage,out_name,small_name", [("v2-h60-step0", v2.STEP0_OUTPUTS[0], v2.STEP0_SMALL[0]),
                                                       ("v2-pre-read", "trades_pre_p5.tsv.gz", "p5_report_pre.txt"),
                                                       ("v2-h60-read", "trades_pre_h60.tsv.gz", "h60_summary_pre.txt"),
                                                       ("v2-exit-read", "exitpb_verdict_pre.json", "exitpb_summary_pre.txt")])
def test_once_only_refuses_any_existing_output_including_under_v2_1025(stage, out_name, small_name, tmp_path, monkeypatch, capsys):
    tree = build_tree(tmp_path, monkeypatch)
    chain(tree, upto={"v2-h60-step0": "v2-h60-step0", "v2-pre-read": "v2-h60-step0", "v2-h60-read": "v2-pre-read", "v2-exit-read": "v2-h60-read"}[stage])
    if stage != "v2-h60-step0":
        fill_and_freeze(tree)
    out, small = tree["v2"] / "out", rn.HERE / "out" / v2.SMALL_SUB
    for p in (out / out_name, Path(str(out / out_name) + ".partial"), small / small_name, Path(str(small / small_name) + ".partial")):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        if stage != "v2-h60-step0" and p.parent == out:
            repin(tree)                                                           # an out/ file is never pinned; the freeze stays valid
        capsys.readouterr()
        assert run(tree, stage) == 2, p
        err = capsys.readouterr().err
        assert "REFUSED" in err and ("ONCE" in err or "CRASHED" in err), err
        p.unlink()


def test_dry_runs_count_and_open_nothing_and_a_real_run_with_the_footer_unpinned_refuses(tmp_path, monkeypatch, capsys):
    tree = build_tree(tmp_path, monkeypatch)
    assert run(tree, "v2-h60-step0") == 0
    assert run(tree, "v2-pre-read") == 2 and "freeze check failed" in capsys.readouterr().err        # no footer yet: refused
    assert run(tree, "v2-pre-read", "--dry-run", "--no-freeze-check") == 0
    assert "V2-PRE-READ DRY RUN" in capsys.readouterr().out
    assert run(tree, "v2-pre-read", "--no-freeze-check") == 2
    for opt in (["--keys", "tl"], ["--limit-dates", "1"], ["--no-apollo"], ["--parity-only"], ["--minutes", str(tree["v2"] / "minutes")]):
        assert run(tree, "v2-pre-read", *opt) == 2, opt


def test_a_dry_run_after_the_chain_re_proves_the_freeze_and_opens_nothing(tmp_path, monkeypatch, capsys):
    """The freeze re-check before stages 5 / 6 (`v2-exit-read --dry-run` once stages 1-3 have run): exit 0, the freeze passed, no file written; a pinned
    file edited after the freeze makes the same dry run refuse."""
    tree = build_tree(tmp_path, monkeypatch)
    chain(tree)
    out = tree["v2"] / "out"
    before = {p: rn.sha256_file(p) for p in out.rglob("*") if p.is_file()}
    capsys.readouterr()
    assert run(tree, "v2-exit-read", "--dry-run") == 0
    o = capsys.readouterr().out
    assert "V2-EXIT-READ DRY RUN (freeze check passed" in o
    assert {p: rn.sha256_file(p) for p in out.rglob("*") if p.is_file()} == before
    relaunch = tree["repo"] / "scripts" / "probes" / "_705_rerun_v2_1023" / "04_relaunch.sh"     # the fixture's pinned copy (a stub), not the real script
    with relaunch.open("a") as fh:
        fh.write("# edited after the freeze\n")
    assert run(tree, "v2-exit-read", "--dry-run") == 2 and "freeze check failed" in capsys.readouterr().err


# ═══ B1: a 6% data-abstain share exits 3 with no report written ═══════════════════════════════════════════════════════════════════════
def test_a_six_percent_data_abstain_share_exits_3_before_the_report(tmp_path, monkeypatch, capsys):
    """16 tickers (tl + com first breaks = 32 rows); one ticker's minutes logged empty -> 2 no_minutes abstains = 6.25% > 5%."""
    tickers = tuple(f"T{k:02d}" for k in range(15)) + ("TSLA",)
    tree = build_tree(tmp_path, monkeypatch, tickers=tickers, restored=("TSLA", "T00"), empty_minutes=("T07",))
    assert run(tree, "v2-h60-step0") == 0
    fill_and_freeze(tree)
    assert run(tree, "v2-pre-read") == 3
    o = capsys.readouterr().out
    assert "DATA GATE BLOCKS THE READ (6.25% > 5%)" in o
    assert not (tree["v2"] / "out" / "p5_report_pre.tsv").exists() and not (rn.HERE / "out" / v2.SMALL_SUB / "p5_report_pre.txt").exists()
    assert not (tree["v2"] / "out" / v2c.MANIFEST_NAME).exists()


# ═══ B1: the open audit - every data path a body opens is under ctx.data, the repo, the small dir, or an old pin; no 2025-26 verdict ═════
_OPENS: list = []
_AUDIT = {"on": False}


def _hook(event, args):
    if _AUDIT["on"] and event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
        _OPENS.append(os.fsdecode(args[0]))


sys.addaudithook(_hook)


def test_the_open_audit_every_path_a_v2_body_opens_is_allowed_and_no_holdout_verdict_is_opened(tmp_path, monkeypatch):
    tree = build_tree(tmp_path, monkeypatch)
    root = tree["root"].resolve()
    allowed = [tree["v2"].resolve(), tree["repo"].resolve(), (rn.HERE / "out").resolve(), REAL_REPO]
    never = [(REAL_REPO / "scripts/probes/_cb_backtest/out").resolve(), REAL_DATA.resolve()]       # the real printouts / the real data: never a body's
    old_pins = {(tree["old"] / rel).resolve() for rel in ("symbol_guard.tsv", "out/h60_verdict_pre.json", "out/exitpb_verdict_pre.json", "out/h60_step0_pre.tsv.gz")}
    ignore = [Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve(), Path("/dev"), Path("/private/var/db"), Path("/System"), Path("/usr")]
    for stage in ("v2-h60-step0", "v2-pre-read", "v2-h60-read", "v2-exit-read"):
        if stage == "v2-pre-read":
            fill_and_freeze(tree)
        _OPENS.clear()
        _AUDIT["on"] = True
        try:
            assert run(tree, stage) == 0, stage
        finally:
            _AUDIT["on"] = False
        bad = []
        for o in _OPENS:
            p = Path(o)
            p = (p if p.is_absolute() else Path.cwd() / p).resolve()
            if any(p.is_relative_to(n) for n in never):
                bad.append(f"NEVER: {p}")
                continue
            if any(p.is_relative_to(i) for i in ignore) or p == Path(os.devnull) or p.suffix in (".py", ".pyc", ".so", ".pth", ".dylib") or \
                    "site-packages" in p.parts:                                   # module imports, not data
                continue
            if any(p.is_relative_to(a) for a in allowed) or p in old_pins:
                continue
            bad.append(str(p))
        assert bad == [], (stage, bad)
        sealed = [o for o in _OPENS if "holdout" in o or "verdict_discovery" in o]
        assert sealed == [], (stage, sealed)
    assert not any((str(root / "cb702") + "/") in o or (str(tree["cb702"]) + "/") in o for o in _OPENS)


# ═══ §8: ONE map for the three frozen reads; every label one path; the chain-made tables are NOT pinned ════════════════════════════════
def test_one_freeze_map_one_label_one_path_and_no_chain_made_table_is_pinned(tmp_path, monkeypatch):
    tree = build_tree(tmp_path, monkeypatch)
    maps = {s: rr.frozen_map(rn.REGISTERED_READS[s], ctx_of(tree, s)) for s in ("v2-pre-read", "v2-h60-read", "v2-exit-read")}
    a = maps["v2-pre-read"]
    assert all(m == a for m in maps.values())
    paths = [Path(p).resolve() for p in a.values()]
    assert len(set(paths)) == len(paths), "two labels point at one path"
    assert all(rn.REGISTERED_READS[s].frozen is v2.v2_frozen for s in maps)
    for chain_made in ("trades_pre_p5.tsv.gz", "trades_pre_h60.tsv.gz", "trades_pre_exitpb.tsv.gz", "entries_pre_tl_com.tsv.gz", v2c.MANIFEST_NAME):
        assert not any(Path(p).name == chain_made for p in a.values()), chain_made
    for label in ("module", "runner", "scaffold", "spec module", "code/v2_chain.py", "code/02_build_paths.py", "code/04_relaunch.sh", "code/trade_impact.py",
                  "code/v2_compare.py", "code/v2_degraded.py", f"{v2.V2_NAME}/minutes (tree)", f"{v2.OLD_NAME}/symbol_guard.tsv",
                  f"{v2.OLD_NAME}/out/h60_verdict_pre.json", f"{v2.OLD_NAME}/out/exitpb_verdict_pre.json", f"{v2.V2_NAME}/{v2.G9_CONSOLE}",
                  f"{v2.V2_NAME}/out/{v2.STEP0_OUT_SUB}/{v2.STEP0_COUNTS}", "_cb_backtest/out/p5_report_pre.tsv", "read1/03_report.md"):
        assert label in a, label
    assert sum(1 for k in a if k.startswith("code/_702_")) == 11
    assert not any("holdout" in str(p) for p in a.values())


# ═══ B1: the call list is derived, not typed; the 2025-26 stamps are neither called nor reachable ═════════════════════════════════════
def _runner_calls(src: str) -> set:
    names = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            v = n.func.value
            if (isinstance(v, ast.Name) and v.id == "rt") or (isinstance(v, ast.Attribute) and v.attr == "rt"):
                names.add(n.func.attr)
    return names


def test_the_call_list_is_the_ast_walk_and_the_sealed_stamps_are_unreachable(capsys):
    got = _runner_calls(Path(v2.__file__).read_text())
    assert sorted(got) == v2.runner_calls(Path(v2.__file__).read_text())           # the module's walk (print-calls) = this independent one
    capsys.readouterr()
    assert v2.main(["print-calls"]) == 0
    printed = capsys.readouterr().out
    assert all(f"`{c}`" in printed for c in got)
    assert got == set(v2.V2_RUNNER_CALLS), (sorted(got - set(v2.V2_RUNNER_CALLS)), sorted(set(v2.V2_RUNNER_CALLS) - got))
    forbidden = {"h60_stamps", "exitpb_stamps", "run_pre_read", "run_h60_read", "run_exit_read", "run_holdout", "run_h60_hindsight"}
    assert not got & forbidden
    tree = ast.parse(Path(rn.__file__).read_text())
    defs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    calls = {k: {c.func.id for c in ast.walk(f) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)} for k, f in defs.items()}
    seen, todo = set(), [c for c in got if c in defs]
    while todo:
        f = todo.pop()
        if f in seen:
            continue
        seen.add(f)
        todo += [c for c in calls.get(f, ()) if c in defs]
    assert not seen & forbidden, sorted(seen & forbidden)
    assert v2.MODULE_SHA == rn.EXITPB_MODULE_SHA


# ═══ B2 / §5: render -> fill -> parse; the doc as registered is not filled and the read refuses on it ═════════════════════════════════
def test_section5_fills_only_the_b2_cells_and_parses_back_and_an_unfilled_doc_refuses(tmp_path, monkeypatch, capsys):
    real = registered_doc_text()
    with pytest.raises(v2.Refuse):
        v2.parse_section5(real)
    counts = {"table": {"pre": {"C0": 20000, "C0_multi": 13000, "C1": 230, "C1_multi": 140, "orh5_C1_fills": 200, "C2": 20, "C3": 400, "C4": 1400,
                                "C5": 450, "C6": 40, "C7": 350, "com_C1": 270, "tl_rows": 80000},
                        "2020-21": {"C0": 13000, "C0_multi": 8800, "C1": 95, "C1_multi": 52, "orh5_C1_fills": 80, "C2": 9, "C3": 140, "C4": 900,
                                    "C5": 220, "C6": 15, "C7": 125}},
              "b8": {"pre": {"shared": 13300, "restored": 2700}, "2020-21": {"shared": 8800, "restored": 1900}}}
    filled = v2.fill_section5(real, counts)
    exp, b8 = v2.parse_section5(filled)
    assert exp["pre"] == counts["table"]["pre"] and exp["2020-21"] == counts["table"]["2020-21"] and b8 == counts["b8"]
    diff = [(a, b) for a, b in zip(real.splitlines(), filled.splitlines()) if a != b]
    assert len(diff) == 5 and all(a.startswith("|") and "(B2)" in a and "(B2)" not in b for a, b in diff)
    assert real.split(rn.FREEZE_MARK)[1] == filled.split(rn.FREEZE_MARK)[1]
    with pytest.raises(ValueError):
        v2.fill_section5(filled, counts)                                     # a second fill: the cells are no longer (B2)
    # the freeze diff rule: §5's (B2) cells (and the G9 bullet) only
    from scripts.probes._705_rerun_v2_1023 import v2_freeze_diff_check as fd
    assert fd.problems(real, filled) == []
    g9 = filled.replace("  record. The hourly-close read keeps", "  record (console: audit_1023/pit_calendar_minutes_1025.console.txt). The hourly-close read keeps")
    assert g9 != filled and fd.problems(real, g9) == []
    assert fd.problems(real, filled.replace("R3 — a share of a population.", "R3 — a share.")) != []
    assert fd.problems(real, real) != []                                       # unfilled: §5 does not parse
    assert fd.problems(real, filled.replace("| 17,392 / 11,414 |", "| 17,391 / 11,414 |")) != []   # an old column edited
    # stage 2 on a tree whose doc still reads (B2): refused before any exit
    tree = build_tree(tmp_path, monkeypatch)
    chain(tree, upto="v2-pre-read")
    repin(tree, body=real.split(rn.FREEZE_MARK)[0])
    capsys.readouterr()
    assert run(tree, "v2-h60-read") == 2 and "the v2 table is not filled (B2)" in capsys.readouterr().out


def test_stage_2_refuses_when_its_step0_differs_from_section5(tmp_path, monkeypatch, capsys):
    tree = build_tree(tmp_path, monkeypatch)
    chain(tree, upto="v2-pre-read")
    doc = tree["repo"] / "docs" / "analysis" / v2.V2_DOC
    body = doc.read_text(encoding="utf-8").split(rn.FREEZE_MARK)[0]
    row = next(ln for ln in body.splitlines() if ln.startswith("| C0 bases / with ≥ 2 break days |"))
    cells = row.split("|")
    cells[3] = " 4 / 3 "                                                       # the v2 whole-era C0 cell off by one
    repin(tree, body=body.replace(row, "|".join(cells)))
    capsys.readouterr()
    assert run(tree, "v2-h60-read") == 2
    o = capsys.readouterr().out
    assert "REFUSED before STEP 0 (nothing written)" in o and "pre C0: §5 4 vs stage 0 3" in o
    for name in v2.H60_OUTPUTS:                                                # F9: a typo in §5 spends nothing - the once-only names stay free
        assert not (tree["v2"] / "out" / name).exists(), name
    assert not (rn.HERE / "out" / v2.SMALL_SUB / "h60_step0_pre.txt").exists()


def test_h60_step0_expected_default_is_looked_up_at_call_time_and_none_compares_nothing(tmp_path, monkeypatch):
    """`h60_step0` called on the fixture's pre bases (3 tl bases): `expected` unset compares against `rn.H60_EXPECTED` as bound AT THE CALL - two
    rebinds in one process give two answers (a default captured at def time would compare both against the real 17,392-base table); an explicit
    table wins over the module's; None compares nothing and never reads "EQUAL"."""
    tree = build_tree(tmp_path / "t", monkeypatch)
    prep = rn.h60_prepare(rn_args(tree), {"cb702": tree["cb702"], "cb702_pre": tree["v2"]}, "pre")
    scratch = tmp_path / "scratch"                                             # never the tree's out/: stage 0's names are once-only names there

    def step0(tag, **kw):
        return rn.h60_step0(prep["bases"], prep["inp"], 1, "pre", scratch / tag / "out", scratch / tag / "small", None, **kw)
    monkeypatch.setattr(rn, "H60_EXPECTED", {"pre": {"C0": 3}})                 # a REBIND (setattr), not a mutation of the old dict
    r = step0("a")
    assert r["problems"] == {"pre": [], "2020-21": []} and "window pre: EQUAL to the registration's table" in r["text"]
    monkeypatch.setattr(rn, "H60_EXPECTED", {"pre": {"C0": 4}})
    r = step0("b")
    assert r["problems"]["pre"] == ["C0: STEP 0 reads 3, the registration's table says 4"] and "window pre: DIFFERS: C0" in r["text"]
    assert step0("c", expected={"pre": {"C0": 3}})["problems"]["pre"] == []    # the explicit table, not the module's (still C0 4)
    r = step0("d", expected=None)
    assert r["problems"] == {"pre": None, "2020-21": None}
    assert "window pre: NO REGISTERED TABLE YET" in r["text"] and "EQUAL to the registration's table" not in r["text"] and "DIFFERS" not in r["text"]
    assert (scratch / "d" / "out" / "h60_step0_pre.tsv.gz").exists() and not (tree["v2"] / "out" / "h60_step0_pre.tsv.gz").exists()
    counts = {("tl", "C0"): 1}
    assert rn.h60_step0_problems(counts, {"C0": 2}) == ["C0: STEP 0 reads 1, the registration's table says 2"]


# ═══ B5: a flipped byte upstream refuses each stage; a rewritten manifest line refuses ═══════════════════════════════════════════════
def _flip(p: Path) -> None:
    raw = bytearray(p.read_bytes())
    raw[len(raw) // 2] ^= 0x01
    p.write_bytes(bytes(raw))


@pytest.mark.parametrize("stage,upstream", [("v2-h60-read", "trades_pre_p5.tsv.gz"), ("v2-exit-read", "trades_pre_h60.tsv.gz"),
                                            ("v2-exit-read", "trades_pre_p5.tsv.gz")])
def test_a_flipped_byte_of_an_upstream_table_refuses_the_stage(stage, upstream, tmp_path, monkeypatch, capsys):
    tree = build_tree(tmp_path, monkeypatch)
    chain(tree, upto={"v2-h60-read": "v2-pre-read", "v2-exit-read": "v2-h60-read"}[stage])
    _flip(tree["v2"] / "out" / upstream)
    capsys.readouterr()
    assert run(tree, stage) == 2
    assert "is not the manifest's" in capsys.readouterr().err


def bp_env(tree, log, **extra) -> dict:
    """The switched 02_build_paths.py in TEST MODE (the fixture is never the real cb702_pre_v2; the freeze re-check is `true`)."""
    base = {k: v for k, v in os.environ.items() if not k.startswith(("CB_PRE_", "V2_"))}
    return {**base, "CB_PRE_DIR": str(tree["v2"]), "CB_PRE_LOG": str(log), "V2_CHAIN_TEST": "1", "V2_TEST_FREEZE_CMD": "true", **extra}


def test_02_build_paths_with_the_switch_refuses_a_flipped_trades_pre_exitpb(tmp_path, monkeypatch):
    tree = build_tree(tmp_path, monkeypatch)
    chain(tree)
    _flip(tree["v2"] / "out" / "trades_pre_exitpb.tsv.gz")
    env = bp_env(tree, tmp_path / "log")
    (tmp_path / "log").mkdir()
    script = REAL_REPO / "scripts/probes/_702_r_decomposition_1022/02_build_paths.py"
    p = subprocess.run([sys.executable, str(script), "2017-21"], capture_output=True, text=True, env=env, cwd=script.parent)
    assert p.returncode == 2 and "is not the manifest's" in p.stderr, (p.returncode, p.stderr[-500:])
    assert not (tree["v2"] / "out" / "r_decomp_fills_2017-21.tsv.gz").exists()


def test_the_manifest_is_append_only_a_rewritten_line_refuses(tmp_path):
    m, f, g = tmp_path / "m.tsv", tmp_path / "a.txt", tmp_path / "b.txt"
    f.write_text("a")
    g.write_text("b")
    v2c.manifest_append(m, "s1", [("A", f)])
    v2c.manifest_append(m, "s2", [("B", g)])
    assert v2c.manifest_problems(m, [("A", f), ("B", g)]) == []
    good = m.read_text()
    m.write_text(good.replace("\ts1\t", "\tsX\t"))                              # one field of line 2 rewritten
    assert "hash chain breaks" in v2c.manifest_problems(m, [("A", f)])[0]
    lines = good.splitlines()
    m.write_text("\n".join([lines[0], lines[2], lines[1]]) + "\n")             # reordered
    assert "hash chain breaks" in v2c.manifest_problems(m, [("A", f)])[0]
    m.write_text(good)
    f.write_text("a2")                                                          # the file changed after its line
    assert "is not the manifest's" in v2c.manifest_problems(m, [("A", f)])[0]
    assert "no line" in v2c.manifest_problems(m, [("C", f)])[0]


def test_the_receipt_compares_and_names_every_difference():
    a = {"protected": {"x": "1" * 64, "y": "2" * 64}, "cb702_pre": {"z": "3" * 64}}
    b = {"protected": {"x": "1" * 64, "y": "9" * 64}, "cb702_pre": {"z": "3" * 64, "new": "4" * 64}}
    pr = v2c.receipt_problems(a, b)
    assert len(pr) == 2 and pr[0].startswith("protected: y") and "new" in pr[1]
    assert v2c.receipt_problems(a, a) == []
    files = v2c.protected_files()
    for n in v2c.PROTECTED_SMALL:
        assert f"_cb_backtest/out/{n}" in files
    assert "_702_r_decomposition_1022/02_build_checks_2017-21.txt" in files
    assert "scripts/probes/_702_breakout_definition_1022/03_numbers.json" in files and not any(k.endswith(".py") for k in files)


# ═══ B6: a one-session-short calendar refuses ════════════════════════════════════════════════════════════════════════════════════════
def test_a_one_session_short_calendar_refuses(tmp_path, monkeypatch, capsys):
    tree = build_tree(tmp_path, monkeypatch)
    assert run(tree, "v2-h60-step0") == 0
    s = tree["v2"] / "sessions.txt"
    s.write_text("".join(s.read_text().splitlines(keepends=True)[:-1]))         # sessions.txt one session short of the export's SPY calendar
    fill_and_freeze(tree)
    capsys.readouterr()
    assert run(tree, "v2-pre-read") == 2
    assert "CALENDAR (B6)" in capsys.readouterr().out
    assert not (tree["v2"] / "out" / "trades_pre_tl_com.tsv.gz").exists()
    assert v2c.calendar_problem(["2020-01-02", "2020-01-03"], ["2020-01-02"]) is not None
    assert v2c.log_calendar_problems  # the log check is tested on the relaunch below


@pytest.mark.parametrize("stage,prior,table", [("v2-h60-read", "v2-pre-read", "trades_pre_h60twin.tsv.gz"), ("v2-exit-read", "v2-h60-read", "trades_pre_exitpb.tsv.gz")])
def test_a_one_session_short_calendar_refuses_the_h60_and_exit_bodies_too(stage, prior, table, tmp_path, monkeypatch, capsys):
    """B6 'in each v2 body': sessions.txt one session short (re-pinned, so the freeze passes) -> the body refuses at its first daily load, before a walk."""
    tree = build_tree(tmp_path, monkeypatch)
    chain(tree, upto=prior)
    s = tree["v2"] / "sessions.txt"
    s.write_text("".join(s.read_text().splitlines(keepends=True)[:-1]))
    repin(tree)
    capsys.readouterr()
    assert run(tree, stage) == 2
    assert "CALENDAR (B6)" in capsys.readouterr().out
    assert not (tree["v2"] / "out" / table).exists() and not (tree["v2"] / "out" / ("trades_pre_h60.tsv.gz" if stage == "v2-h60-read" else table)).exists()


# ═══ B8: the restored names reach every stage; removing them refuses ═════════════════════════════════════════════════════════════════
def test_removing_the_restored_tickers_makes_stage_1_refuse(tmp_path, monkeypatch, capsys):
    """Stage 0 counts the restored fills; then the restored tickers' rows vanish from the candidates (a stale path / a filter): stage 1 refuses."""
    tree = build_tree(tmp_path, monkeypatch)
    assert run(tree, "v2-h60-step0") == 0
    c = tree["v2"] / "out" / "candidates_tl_com.tsv"
    keep = [ln for ln in c.read_text().splitlines(keepends=True) if not ln.startswith(("TSLA\t", "Y\t"))]
    c.write_text("".join(keep))
    fill_and_freeze(tree)
    capsys.readouterr()
    assert run(tree, "v2-pre-read") == 3
    assert "B8 REFUSES" in capsys.readouterr().out
    assert not (tree["v2"] / "out" / "p5_report_pre.tsv").exists()


def test_stage_0_refuses_when_no_restored_ticker_exists(tmp_path, monkeypatch, capsys):
    tree = build_tree(tmp_path, monkeypatch, restored=())
    assert run(tree, "v2-h60-step0") == 3
    assert "B8 REFUSES: 0 C0 fills on restored tickers" in capsys.readouterr().out


def test_stage_1_per_cell_restored_counts_equal_stage_0s(tmp_path, monkeypatch, capsys):
    tree = build_tree(tmp_path, monkeypatch)
    chain(tree, upto="v2-pre-read")
    o = capsys.readouterr().out
    assert "B8 RESTORED (stage 1): 2 of 3 tl fills" in o
    assert "B8 RESTORED (stage 1 = stage 0, per window and cell): " in o and "pre C0 2" in o and "pre C1 2" in o


# ═══ B9: one ending of each class and one hole -> one count in each bucket ═══════════════════════════════════════════════════════════
def test_the_degraded_walk_report_puts_one_of_each_in_its_bucket(tmp_path):
    import pandas as pd
    from scripts.probes._705_rerun_v2_1023 import v2_degraded as dg
    assert abs(dg.PARTIAL_FRAC - float(rn.EXITPB_BASE.partial_frac)) < 1e-12 and dg.HAIRCUT == 0.30
    days = [d.isoformat() for d in T._weekdays(200, T.dt.date(2019, 1, 7))]
    rows = []
    exp = {"SPY": [100.0] * 200}
    exp["COL"] = list(np.linspace(20, 4, 150))                                  # -80% over its last 60 sessions, ends at bar 150 (a collapse)
    exp["DEAL"] = [10.0] * 140 + [12.0] * 10                                     # pinned at 12.00 for its last 10 closes (deal-like)
    exp["OTH"] = list(10 + np.sin(np.arange(150)))                               # wobbles, ends (other)
    exp["HOLE"] = [10.0] * 200                                                   # prints to the end (its walk hit a gap)
    exp["OK"] = [10.0] * 200
    with gzip.open(tmp_path / "x.csv.gz", "wt") as fh:
        for t, cs in exp.items():
            for k, c in enumerate(cs):
                fh.write(f"{t},{days[k]},{c},{c},{c},{c},1000\n")
    base = dict(arm="pp", entry="orh5", K="tl", C0=1, fill=10.0, stop=9.0, partial_kind="", exit_px=np.nan)
    rows.append({**base, "ticker": "OK", "E": days[100], "status": "trailed", "realized_r": 1.0, "mature": 1, "fwd_hole": 0, "sessions_held": 10})
    rows.append({**base, "ticker": "OK", "E": days[101], "status": "stopped", "realized_r": -1.0, "mature": 1, "fwd_hole": 0, "sessions_held": 3})
    rows.append({**base, "ticker": "COL", "E": days[120], "status": "degraded", "realized_r": -5.0, "mature": 0, "fwd_hole": 0, "sessions_held": 29,
                 "exit_px": 4.0, "partial_kind": ""})
    rows.append({**base, "ticker": "DEAL", "E": days[120], "status": "degraded", "realized_r": 2.0, "mature": 0, "fwd_hole": 0, "sessions_held": 29,
                 "exit_px": 12.0, "partial_kind": "r", "partial_px": 12.0})
    rows.append({**base, "ticker": "OTH", "E": days[120], "status": "degraded", "realized_r": 0.5, "mature": 0, "fwd_hole": 0, "sessions_held": 29,
                 "exit_px": float(exp["OTH"][-1])})
    rows.append({**base, "ticker": "HOLE", "E": days[120], "status": "degraded", "realized_r": 0.2, "mature": 0, "fwd_hole": 1, "sessions_held": 12, "exit_px": 10.2})
    rows.append({**base, "ticker": "OK", "E": days[102], "arm": "A", "status": "degraded", "realized_r": 9.0, "mature": 0, "fwd_hole": 0, "sessions_held": 5})
    rep = dg.report(pd.DataFrame(rows), tmp_path / "x.csv.gz", restored={"COL"}, export_last=days[-1], sessions=days)
    assert rep["n_rows"] == 6 and rep["n_mature"] == 2 and rep["n_degraded"] == 4
    assert rep["by_cause"] == {"ending": 3, "hole": 1}
    assert rep["by_class"] == {"collapse": 1, "deal-like": 1, "other": 1, "file end": 0}
    assert rep["by_side"]["restored"] == {"ending": 1, "hole": 0}
    assert rep["mean_r_out"] == 0.0
    assert abs(rep["mean_r_in_last_close"] - (1 - 1 - 5 + 2 + 0.5 + 0.2) / 6) < 1e-12
    hc = -5.0 - 1.0 * 0.30 * 4.0 / 1.0                                         # the collapse's remaining position exits at 0.7 x 4.00
    assert abs(rep["mean_r_in_haircut"] - (1 - 1 + hc + 2 + 0.5 + 0.2) / 6) < 1e-12
    assert "endings by class: collapse 1, deal-like 1, other 1" in dg.text(rep)
    assert rep["mark_problems"] == [] and "MARK CHECK (an ending's mark = the ticker's last close): ok" in dg.text(rep)
    # the pre-read's table (stage 1): no `entry` and no `exit_px` column, arm c3_p33_t20_cut3 - the mark is the ticker's last close from the export
    p5 = pd.DataFrame(rows).drop(columns=["entry", "exit_px"])
    p5["arm"] = p5["arm"].replace({"pp": "c3_p33_t20_cut3"})
    rep5 = dg.report(p5, tmp_path / "x.csv.gz", restored={"COL"}, export_last=days[-1], arm="c3_p33_t20_cut3", entry="", sessions=days)
    assert (rep5["by_cause"], rep5["by_class"]) == (rep["by_cause"], rep["by_class"]) and abs(rep5["mean_r_in_haircut"] - rep["mean_r_in_haircut"]) < 1e-12
    assert abs(dg.PARTIAL_FRAC - cb.CUT_EXIT_ARMS[cb.P5_PRIMARY_ARM].partial_frac) < 1e-12 and cb.P5_PRIMARY_ARM in dg.ARMS_ONE_THIRD
    # a mark that is not the ticker's last close is printed (the ending reading would be wrong); an arm without a known third refuses
    bad = pd.DataFrame(rows)
    bad.loc[bad["ticker"] == "DEAL", "exit_px"] = 11.0
    rb = dg.report(bad, tmp_path / "x.csv.gz", restored={"COL"}, export_last=days[-1], sessions=days)
    assert len(rb["mark_problems"]) == 1 and "DEAL" in rb["mark_problems"][0] and "1 MISMATCH" in dg.text(rb)
    with pytest.raises(ValueError):
        dg.report(pd.DataFrame(rows), tmp_path / "x.csv.gz", arm="A", sessions=days)
    with pytest.raises(ValueError):                                             # no calendar: refused (one calendar per record)
        dg.report(pd.DataFrame(rows), tmp_path / "x.csv.gz")


# ═══ B4: the relaunch refuses a manifest mismatch and a doctored calendar line ═════════════════════════════════════════════════════════
RELAUNCH = REAL_REPO / "scripts/probes/_705_rerun_v2_1023/04_relaunch.sh"


def test_the_relaunch_exits_2_on_a_manifest_mismatch_before_anything_runs(tmp_path):
    v = tmp_path / v2.V2_NAME
    (v / "out").mkdir(parents=True)
    names = ("entries_pre_tl_com.tsv.gz", "trades_pre_p5.tsv.gz", "trades_pre_exitpb.tsv.gz", "r_decomp_fills_2017-21.tsv.gz", "r_decomp_control_2017-21.tsv.gz")
    for n in names:
        (v / "out" / n).write_text(n)
    v2c.manifest_append(v / "out" / v2c.MANIFEST_NAME, "test", [(f"{v2.V2_NAME}/out/{n}", v / "out" / n) for n in names])
    probes = tmp_path / "probes"
    (probes / "_cb_backtest").mkdir(parents=True)
    shutil.copyfile(Path(v2c.__file__), probes / "_cb_backtest" / "v2_chain.py")
    env = {**os.environ, "V2_DIR": str(v), "PROBES": str(probes), "LOGROOT": str(tmp_path / "logs"), "V2_CHAIN_TEST": "1", "V2_TEST_FREEZE_CMD": "true"}
    (v / "out" / "r_decomp_control_2017-21.tsv.gz").write_text("edited")        # a copy edited after its manifest line
    p = subprocess.run(["bash", str(RELAUNCH)], capture_output=True, text=True, env=env)
    assert p.returncode == 2 and "is not the manifest's" in p.stderr and "nothing runs" in p.stdout, (p.returncode, p.stdout, p.stderr)
    assert not (v / "out" / "rerun_v2_1025").exists() and not (tmp_path / "logs").exists()
    (v / "out" / "r_decomp_control_2017-21.tsv.gz").write_text(names[4])          # restored: the manifest passes; an existing output dir refuses
    (tmp_path / "logs").mkdir()
    p = subprocess.run(["bash", str(RELAUNCH)], capture_output=True, text=True, env=env)
    assert p.returncode == 2 and "runs ONCE" in p.stdout, (p.stdout, p.stderr)


def test_the_relaunch_calendar_check_refuses_a_doctored_log_and_reads_every_spelling(tmp_path):
    good = {"a.log": "  calendar 1635 sessions (2016-01-04..2022-06-30); wide (1635, 12532)\n",
            "b.log": "  export: 12,005,007 rows, kept 12,005,007 (cut None); 2016-01-04..2022-06-30 = 1635 sessions; 12,532 tickers; 9s\n",
            "c.log": "  calendar = SPY sessions: 1635 (2016-01-04..2022-06-30); off-calendar bars dropped 0\n",
            "d.log": "  export loaded: 1635 sessions 2016-01-04..2022-06-30; 12s\n"}
    for n, t in good.items():
        (tmp_path / n).write_text(t)
    # TEST MODE with a scratch code tree carrying this checkout's v2_chain.py: the real mode resolves the chain module from the script's REAL_B
    # literal (the operator's machine), which a CI checkout at another path does not have; the --check-log branch is the same cal_check either way
    v, probes = tmp_path / v2.V2_NAME, tmp_path / "probes"
    v.mkdir()
    (probes / "_cb_backtest").mkdir(parents=True)
    shutil.copyfile(Path(v2c.__file__), probes / "_cb_backtest" / "v2_chain.py")
    env = {**{k: x for k, x in os.environ.items() if not k.startswith(("CB_PRE_", "V2_", "PROBES", "LOGROOT"))}, "V2_CHAIN_TEST": "1",
           "V2_TEST_FREEZE_CMD": "false", "V2_DIR": str(v), "PROBES": str(probes), "LOGROOT": str(tmp_path / "logs")}

    def check(*logs):
        return subprocess.run(["bash", str(RELAUNCH), "--check-log", *[str(tmp_path / n) for n in logs]], capture_output=True, text=True, env=env)
    p = check(*good)
    assert p.returncode == 0 and f"CALENDAR OK: {len(good)} log(s)" in p.stdout and "TEST MODE" in p.stdout, (p.stdout, p.stderr)
    (tmp_path / "bad.log").write_text(good["a.log"].replace("1635 sessions (2016-01-04", "1634 sessions (2016-01-05"))
    p = check("bad.log")
    assert p.returncode == 2 and "calendar 1634 sessions" in p.stderr
    (tmp_path / "bad_d.log").write_text(good["d.log"].replace("1635 sessions 2016-01-04", "1636 sessions 2016-01-04"))
    p = check("bad_d.log")
    assert p.returncode == 2 and "calendar 1636 sessions" in p.stderr
    (tmp_path / "none.log").write_text("no calendar here\n")
    p = check("none.log")
    assert p.returncode == 2 and "carries no calendar line" in p.stderr
    assert not (tmp_path / "logs").exists() and not (v / "out").exists()             # the check alone: nothing created


# ═══ B7: the comparison's two proofs (old vs old = all holds; a pushed value = changes) on the published sources ═══════════════════════
@pytest.mark.skipif(not (REAL_DATA / "cb702_pre" / "out" / "trail_win_2017-21.tsv.gz").is_file(), reason="the published old tables are not on this machine")
def test_the_comparison_proofs_hold_on_the_published_sources(tmp_path, monkeypatch):
    from scripts.probes._705_rerun_v2_1023 import v2_compare_proofs as pf
    monkeypatch.setattr(pf, "RECEIPT", tmp_path / "receipt.txt")
    monkeypatch.setattr(sys, "argv", ["x", str(tmp_path / "proofs")])
    pf.lines.clear()
    pf.res.clear()
    assert pf.main() == 0, (tmp_path / "receipt.txt").read_text()


def test_the_comparison_rules_on_their_edges():
    from scripts.probes._705_rerun_v2_1023 import v2_compare as vc
    iv = lambda d, lo, hi: {"d": d, "lo": lo, "hi": hi, "n": 1}
    assert vc.apply("R1", iv(0.01, -0.01, 0.03), iv(0.02, -0.001, 0.04))[0] == "holds"
    assert vc.apply("R1", iv(0.01, -0.01, 0.03), iv(0.05, -0.001, 0.09))[0] == "moved"
    assert vc.apply("R1", iv(0.01, -0.01, 0.03), iv(0.02, 0.001, 0.04))[0] == "changes"
    assert vc.r3_tol(44.0) == 5.0 and abs(vc.r3_tol(8.2) - 4.1) < 1e-12 and abs(vc.r3_tol(5.2) - 2.6) < 1e-12 and vc.r3_tol(0.6) == 2.0
    assert vc.apply("R3", {"k": 240, "n": 481}, {"k": 264, "n": 481})[0] == "holds"      # 49.90 -> 54.89: 4.99 points, inside +-5
    assert vc.apply("R3", {"k": 240, "n": 481}, {"k": 265, "n": 481})[0] == "changes"    # 5.20 points
    assert vc.apply("R5", 1.16, 1.50)[0] == "moved" and vc.apply("R5", 1.16, 1.30)[0] == "holds" and vc.apply("R5", 1.16, -0.1)[0] == "changes"
    assert vc.apply("R4+R3", {"k": 213, "n": 481}, {"best": "S1_T2", "shares": {"S1_T2": 0.45, "S2_T2": 0.44}, "named": "S2_T2", "k": 211, "n": 481})[0] == "holds"
    assert vc.apply("R4+R3", {"k": 213, "n": 481}, {"best": "S1_T2", "shares": {"S1_T2": 0.47, "S2_T2": 0.44}, "named": "S2_T2", "k": 211, "n": 481})[0] == "changes"


def test_stage_0_counts_the_old_files_bases_absent_on_v2_as_removed(tmp_path, monkeypatch, capsys):
    """B8 'removed': an old STEP 0 table carrying one extra C0 tl base (a ticker v2 dropped) -> removed 1 of its bases; with no old table -> None."""
    tree = build_tree(tmp_path, monkeypatch)
    assert run(tree, "v2-h60-step0") == 0
    out0 = tree["v2"] / "out" / v2.STEP0_OUT_SUB
    assert json.loads((out0 / v2.STEP0_COUNTS).read_text())["removed"] == {"pre": None, "2020-21": None}
    df = rn.read_tsv(out0 / "h60_step0_pre.tsv.gz")
    extra = df[(df["ticker"] == "Z") & (df["row_no"] == 0)].copy()
    extra["ticker"] = "GONE"
    import pandas as pd
    pd.concat([df, extra]).to_csv(tree["old"] / "out" / "h60_step0_pre.tsv.gz", sep="\t", index=False, compression="gzip")
    got = v2.removed_counts(rn, tree["old"], rn.h60_prepare(rn_args(tree), {"cb702": tree["cb702"], "cb702_pre": tree["v2"]}, "pre")["bases"])
    assert got == {"pre": 1, "2020-21": 1, "old_bases": 4}


def test_02_build_paths_with_the_switch_runs_once(tmp_path, monkeypatch):
    tree = build_tree(tmp_path, monkeypatch)
    chain(tree)
    (tree["v2"] / "out" / "r_decomp_fills_2017-21.tsv.gz").write_bytes(b"a table the chain already made")
    env = bp_env(tree, tmp_path / "log")
    script = REAL_REPO / "scripts/probes/_702_r_decomposition_1022/02_build_paths.py"
    p = subprocess.run([sys.executable, str(script), "2017-21"], capture_output=True, text=True, env=env, cwd=script.parent)
    assert p.returncode == 2 and "stage 5 runs ONCE" in p.stderr, (p.returncode, p.stderr[-400:])


# ═══ B4 / B6: the relaunch reads stage 5's log first; §3 row 6: read 4's pp cell = read 3's S2 cell ══════════════════════════════════════
def _relaunch_tree(tmp_path, log_text):
    """A manifest that passes, no output dir, a scratch probes tree (the chain module + stage 5's log): the relaunch reaches its stage-5 check."""
    v, probes = tmp_path / v2.V2_NAME, tmp_path / "probes"
    (v / "out").mkdir(parents=True)
    names = ("entries_pre_tl_com.tsv.gz", "trades_pre_p5.tsv.gz", "trades_pre_exitpb.tsv.gz", "r_decomp_fills_2017-21.tsv.gz", "r_decomp_control_2017-21.tsv.gz")
    for n in names:
        (v / "out" / n).write_text(n)
    v2c.manifest_append(v / "out" / v2c.MANIFEST_NAME, "test", [(f"{v2.V2_NAME}/out/{n}", v / "out" / n) for n in names])
    (probes / "_cb_backtest").mkdir(parents=True)
    shutil.copyfile(Path(v2c.__file__), probes / "_cb_backtest" / "v2_chain.py")
    if log_text is not None:
        (probes / "_702_r_decomposition_1022" / "rerun_v2_1025").mkdir(parents=True)
        (probes / "_702_r_decomposition_1022" / "rerun_v2_1025" / "02_build_checks_2017-21.txt").write_text(log_text)
    return {**os.environ, "V2_DIR": str(v), "PROBES": str(probes), "LOGROOT": str(tmp_path / "logs"), "V2_CHAIN_TEST": "1", "V2_TEST_FREEZE_CMD": "true"}, v


@pytest.mark.parametrize("log_text", [None, "  calendar = SPY sessions: 1634 (2016-01-05..2022-06-30); off-calendar bars dropped 0\n", "no calendar\n"])
def test_the_relaunch_refuses_when_stage_5s_log_is_missing_or_its_calendar_differs(log_text, tmp_path):
    env, v = _relaunch_tree(tmp_path, log_text)
    p = subprocess.run(["bash", str(RELAUNCH)], capture_output=True, text=True, env=env)
    assert p.returncode == 2 and "REFUSED (B6)" in p.stdout, (p.returncode, p.stdout, p.stderr)
    assert not (v / "out" / "rerun_v2_1025").exists() and not (tmp_path / "logs").exists()


def test_the_pp_parity_check_passes_on_the_published_cells_and_refuses_a_changed_value(tmp_path):
    h3, h4 = REAL_REPO / "scripts/probes/_702_entry_stop_retry_1022/03_headline.json", REAL_REPO / "scripts/probes/_702_trail_variants_1023/03_headline.json"
    assert v2c.main(["pp-parity", str(h3), str(h4)]) == 0
    d = json.loads(h4.read_text())
    d["2017-21"]["A20_X1_P1"]["R1_T0"]["any5_diff"]["lo"] += 1e-6
    (tmp_path / "h4.json").write_text(json.dumps(d))
    assert v2c.main(["pp-parity", str(h3), str(tmp_path / "h4.json")]) == 2
    d = json.loads(h4.read_text())
    del d["2017-21"]["A20_X1_P1"]["win_T2"]["kept_half"]
    (tmp_path / "h4b.json").write_text(json.dumps(d))
    assert any("kept_half" in p for p in v2c.pp_parity_problems(json.loads(h3.read_text()), d))
    # that 04_relaunch.sh RUNS this check on read 3's and read 4's rerun 03_headline.json is proven by running it: the stub-read end to end reads
    # "PP PARITY OK", and read 4's headline changed (`fail="pp"`) stops the relaunch with "REFUSED (4.0)" before stage 4 (test_the_relaunch_end_to_end_on_stub_reads_registers_every_source_stage_7_reads,
    # test_the_relaunch_stops_at_each_failed_check_and_runs_nothing_after[pp-...])


# ═══ B3: a switched 02_build_paths never writes the committed checks file ════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("extra", [{"CB_PRE_DIR": "DATA"}, {"CB_PRE_DIR": "DATA", "CB_PRE_LOG": "HERE"}, {"CB_PRE_LOG": "LOG"}])
def test_02_build_paths_refuses_a_switch_that_would_write_the_committed_checks_file(extra, tmp_path):
    script = REAL_REPO / "scripts/probes/_702_r_decomposition_1022/02_build_paths.py"
    committed = script.parent / "02_build_checks_2017-21.txt"
    before = rn.sha256_file(committed)
    sub = {"DATA": str(tmp_path / "data"), "HERE": str(script.parent), "LOG": str(tmp_path / "log")}
    env = {**{k: v for k, v in os.environ.items() if not k.startswith("CB_PRE_")}, **{k: sub[v] for k, v in extra.items()}}
    p = subprocess.run([sys.executable, str(script), "2017-21"], capture_output=True, text=True, env=env, cwd=script.parent)
    assert p.returncode == 2 and "REFUSED (B3)" in p.stderr, (p.returncode, p.stderr[-300:])
    assert rn.sha256_file(committed) == before and not (tmp_path / "log").exists()


# ═══ F7: the G9 bullet may only gain a console reference ═════════════════════════════════════════════════════════════════════════════════
def test_the_freeze_diff_rule_allows_only_an_inserted_g9_console_reference():
    from scripts.probes._705_rerun_v2_1023 import v2_freeze_diff_check as fd
    real = registered_doc_text()
    counts = {"table": {"pre": {k: 1 for k in ("C0", "C0_multi", "C1", "C1_multi", "orh5_C1_fills", "C2", "C3", "C4", "C5", "C6", "C7", "com_C1", "tl_rows")},
                        "2020-21": {k: 1 for k in ("C0", "C0_multi", "C1", "C1_multi", "orh5_C1_fills", "C2", "C3", "C4", "C5", "C6", "C7")}},
              "b8": {"pre": {"shared": 1, "restored": 1}, "2020-21": {"shared": 1, "restored": 1}}}
    filled = v2.fill_section5(real, counts)
    ok = filled.replace("  record. The hourly-close read keeps", "  record (console: audit_1023/pit_calendar_minutes_1025.console.txt). The hourly-close read keeps")
    assert fd.problems(real, ok) == []
    dropped = filled.replace("so it did not scan the minute tree.", "so it scanned the minute tree.")                 # a G9 word removed
    assert any("lost or rewrote" in p for p in fd.problems(real, dropped))
    noref = filled.replace("  record. The hourly-close read keeps", "  record, and it passed. The hourly-close read keeps")   # not a console reference
    assert any("not a console reference" in p for p in fd.problems(real, noref))


def test_the_receipt_covers_stage_0s_pinned_copies_and_every_comparison_line_names_its_source():
    files = v2c.protected_files()
    for name in v2c.STEP0_PINNED:
        assert f"{v2.V2_NAME}/out/{name}" in files
    assert "_cb_backtest/out/v2_1025/step0/h60_step0_pre.txt" in files
    assert set(v2c.STEP0_PINNED) == {f"{v2.STEP0_OUT_SUB}/{n}" for n in ("h60_step0_pre.tsv.gz", "h60_step0_pre.txt", v2.STEP0_COUNTS)}
    from scripts.probes._705_rerun_v2_1023 import v2_compare as vc
    assert {ln["id"] for ln in vc.LINES} == set(vc.SRC_OF)
    assert all(n in vc.LOGICAL for names, _k in vc.SRC_OF.values() for n in names)


# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# Review of 10-25, round 2 (the mutation run): every refusal branch made to FAIL by a test, the boundaries, and the comparison's own guards
# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
def _wrap_step0(monkeypatch, **override):
    """`rn.h60_step0` as the bodies call it, with fields of its result overridden after the real call (the branch a fixture cannot reach)."""
    real = rn.h60_step0

    def wrapped(*a, **k):
        r = real(*a, **k)
        for key, v in override.items():
            r[key] = v(r) if callable(v) else v
        return r
    monkeypatch.setattr(rn, "h60_step0", wrapped)


def _stage_rows(tree, stage):
    return [r for r in v2c.manifest_rows(tree["v2"] / "out" / v2c.MANIFEST_NAME) if r["stage"] == stage]


# ─── F7: stage 0 / 1 refusals ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_stage_0_refuses_an_early_close_problem(tmp_path, monkeypatch, capsys):
    """M17. The early-close problem is injected into STEP 0's result (the synthetic tree has no 13:00 close) - the branch, not the detector."""
    tree = build_tree(tmp_path, monkeypatch)
    _wrap_step0(monkeypatch, early_problems=["2020-11-27: after-hours minute bars on an early-close day"])
    assert run(tree, "v2-h60-step0") == 3
    assert "EARLY-CLOSE CHECK FAILED: 2020-11-27" in capsys.readouterr().out


@pytest.mark.parametrize("bump,rc", [(0.0, 0), (1e-9, 3)])
def test_stage_1_data_gate_boundary_exactly_five_percent_passes(bump, rc, tmp_path, monkeypatch, capsys):
    """M03: a data-abstain share of exactly 5.00% does not block (> 5%, not >=); a hair over blocks with exit 3 and no report."""
    tree = build_tree(tmp_path, monkeypatch)
    assert run(tree, "v2-h60-step0") == 0
    fill_and_freeze(tree)
    real = rn.minute_data_gate
    monkeypatch.setattr(rn, "minute_data_gate", lambda gate: (rn.DATA_ABSTAIN_MAX + bump, real(gate)[1]))
    capsys.readouterr()
    assert run(tree, "v2-pre-read") == rc
    assert (tree["v2"] / "out" / "p5_report_pre.tsv").exists() == (rc == 0)
    if rc:
        assert "DATA GATE BLOCKS THE READ" in capsys.readouterr().out


def test_stage_1_refuses_a_failed_cross_check(tmp_path, monkeypatch, capsys):
    """M05."""
    tree = build_tree(tmp_path, monkeypatch)
    assert run(tree, "v2-h60-step0") == 0
    fill_and_freeze(tree)
    monkeypatch.setattr(rn, "p5_crosscheck", lambda *a, **k: (3, ["TSLA 2020-05-28: realized R 1.0 vs 1.5"]))
    capsys.readouterr()
    assert run(tree, "v2-pre-read") == 3
    assert "CROSS-CHECK tl/com FAILED" in capsys.readouterr().out
    assert not (tree["v2"] / "out" / "p5_report_pre.tsv").exists() and _stage_rows(tree, "v2-pre-read") == []


def test_stage_1_refuses_when_one_restored_ticker_is_dropped_after_stage_0(tmp_path, monkeypatch, capsys):
    """F8 / M07 - the WOULD-FAIL-IF case of B8: stage 0 counted TSLA and Y; Y's rows vanish before stage 1 (a partial drop - TSLA still fills, so
    the zero check cannot see it): exactly the per-cell comparison refuses."""
    tree = build_tree(tmp_path, monkeypatch)
    assert run(tree, "v2-h60-step0") == 0
    c = tree["v2"] / "out" / "candidates_tl_com.tsv"
    c.write_text("".join(ln for ln in c.read_text().splitlines(keepends=True) if not ln.startswith("Y\t")))
    fill_and_freeze(tree)
    capsys.readouterr()
    assert run(tree, "v2-pre-read") == 3
    o = capsys.readouterr().out
    assert "B8 RESTORED (stage 1): 1 of 2 tl fills" in o and "B8 REFUSES: stage 1's restored tl ORH5 fills differ from stage 0's" in o and "pre C0: 2 / 1" in o
    assert not (tree["v2"] / "out" / "p5_report_pre.tsv").exists() and _stage_rows(tree, "v2-pre-read") == []


def test_stage_1_refuses_a_vacuous_per_cell_check(tmp_path, monkeypatch, capsys):
    """M06: stage 0's pinned counts carry no restored C0 fill (re-pinned) while stage 1 has restored fills -> refused as vacuous, not compared."""
    tree = build_tree(tmp_path, monkeypatch)
    assert run(tree, "v2-h60-step0") == 0
    cj = tree["v2"] / "out" / v2.STEP0_OUT_SUB / v2.STEP0_COUNTS
    counts = json.loads(cj.read_text())
    for per in counts["cells"].values():
        for v in per.values():
            v["restored"] = 0
    cj.write_text(json.dumps(counts))
    fill_and_freeze(tree)
    capsys.readouterr()
    assert run(tree, "v2-pre-read") == 3
    assert "the per-cell check would be vacuous" in capsys.readouterr().out


# ─── F9 / F7: stage 2 - the pre-STEP-0 check, then every post-STEP-0 refusal ──────────────────────────────────────────────────────────
def _stage2_ready(tree):
    chain(tree, upto="v2-pre-read")


def test_stage_2_refuses_tl_rows_before_step_0_when_section5_and_the_counts_agree_on_a_wrong_value(tmp_path, monkeypatch, capsys):
    """M09: §5's tl rows and stage 0's json both say 7 (re-pinned, so the §5 = json check passes) but the tree has 6 -> refused, nothing written."""
    tree = build_tree(tmp_path, monkeypatch)
    _stage2_ready(tree)
    cj = tree["v2"] / "out" / v2.STEP0_OUT_SUB / v2.STEP0_COUNTS
    counts = json.loads(cj.read_text())
    counts["table"]["pre"]["tl_rows"] = 7
    cj.write_text(json.dumps(counts))
    doc = tree["repo"] / "docs" / "analysis" / v2.V2_DOC
    body = doc.read_text(encoding="utf-8").split(rn.FREEZE_MARK)[0]
    row = next(ln for ln in body.splitlines() if ln.startswith("| com C1 / tl rows |"))
    cells = row.split("|")
    cells[3] = cells[3].replace("/ 6 ", "/ 7 ")
    repin(tree, body=body.replace(row, "|".join(cells)))
    capsys.readouterr()
    assert run(tree, "v2-h60-read") == 2
    o = capsys.readouterr().out
    assert "REFUSED before STEP 0 (nothing written)" in o and "TL ROWS by label / file 6 != §5 7" in o
    assert not (tree["v2"] / "out" / "h60_step0_pre.tsv.gz").exists()


@pytest.mark.parametrize("what", ["table", "early", "share", "split"])
def test_stage_2_refuses_after_step_0_on_each_registered_check(what, tmp_path, monkeypatch, capsys):
    """M08 / M10 / M11 + the table check: the §5 = json pre-check passes, then STEP 0's own result fails one check (injected into its result, or
    the B8 split stage 2 recounts) -> 'REFUSED before any exit', no exit walked."""
    tree = build_tree(tmp_path, monkeypatch)
    _stage2_ready(tree)
    if what == "table":
        _wrap_step0(monkeypatch, problems=lambda r: {**r["problems"], "pre": ["C0: STEP 0 reads 3, the registration's table says 4"]})
    elif what == "early":
        _wrap_step0(monkeypatch, early_problems=["2020-11-27: after-hours minute bars"])
    elif what == "share":
        _wrap_step0(monkeypatch, data_share=0.06)
    else:
        real = v2.step0_split_counts
        monkeypatch.setattr(v2, "step0_split_counts", lambda *a, **k: {**real(*a, **k), "b8": {w: {"shared": 9, "restored": 9} for w in v2.WINDOWS}})
    capsys.readouterr()
    assert run(tree, "v2-h60-read") == 2
    o = capsys.readouterr().out
    assert "REFUSED before any exit: STEP 0 does not pass the registered checks" in o
    assert {"table": "C0: STEP 0 reads 3", "early": "after-hours minute bars", "share": "data-abstain share 6.00% > 5%",
            "split": "B8 split shared / restored"}[what] in o
    assert not (tree["v2"] / "out" / "trades_pre_h60twin.tsv.gz").exists() and not (tree["v2"] / "out" / "trades_pre_h60.tsv.gz").exists()


@pytest.mark.parametrize("what", ["twin", "b8"])
def test_stage_2_refuses_a_failed_twin_check_and_zero_restored_rows(what, tmp_path, monkeypatch, capsys):
    """M12 / M13: exit 3, no report, no manifest line for the stage."""
    tree = build_tree(tmp_path, monkeypatch)
    _stage2_ready(tree)
    if what == "twin":
        monkeypatch.setattr(rn, "h60_twin_check", lambda *a, **k: ["TSLA 2020-05-28: status trailed vs stopped"])
    else:
        monkeypatch.setattr(v2, "restored_rows", lambda rt, path, rest, where=None: (0, 3))
    capsys.readouterr()
    assert run(tree, "v2-h60-read") == 3
    o = capsys.readouterr().out
    assert ("TWIN CHECK FAILED" if what == "twin" else "B8 REFUSES: 0 stage-2 rows on restored tickers") in o
    assert not (tree["v2"] / "out" / "h60_report_pre.tsv").exists() and _stage_rows(tree, "v2-h60-read") == []


# ─── F7: stage 3 ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("what", ["b8", "parity", "self_check"])
def test_stage_3_refuses_zero_restored_fills_a_parity_mismatch_and_a_failed_self_check(what, tmp_path, monkeypatch, capsys):
    """M14 / M15 / M16: exit 3, no report, no manifest line for the stage."""
    tree = build_tree(tmp_path, monkeypatch)
    chain(tree, upto="v2-h60-read")
    if what == "b8":
        monkeypatch.setattr(v2, "restored", lambda ctx: frozenset())
    elif what == "parity":
        real = rn.exitpb_parity
        monkeypatch.setattr(rn, "exitpb_parity", lambda *a, **k: (lambda r: (r[0], ["TSLA 2020-05-28 orh5/tl: realized R 1.0 vs 1.2"], r[2]))(real(*a, **k)))
    else:
        monkeypatch.setattr(rn, "exitpb_self_checks", lambda df, period: (["pp_wbe C0 mean is not pp's on the never-cut trades"], ["check lines"]))
    capsys.readouterr()
    assert run(tree, "v2-exit-read") == 3
    o = capsys.readouterr().out
    assert {"b8": "B8 REFUSES: 0 exit-read fills", "parity": "PARITY FAILED: 1 mismatches", "self_check": "IMPLEMENTATION CHECK FAILED"}[what] in o
    assert not (tree["v2"] / "out" / "exitpb_report_pre.tsv").exists() and _stage_rows(tree, "v2-exit-read") == []


# ─── F7 / F13 / F2: the switched 02_build_paths.py ──────────────────────────────────────────────────────────────────────────────────────
BP_SCRIPT = REAL_REPO / "scripts/probes/_702_r_decomposition_1022/02_build_paths.py"


def _no_python_path(tmp_path) -> str:
    """A PATH whose `python3` refuses: a refusal test whose guard failed would otherwise start the real freeze re-check (the runner's dry run on the
    real data) - with this PATH it stops at once instead."""
    b = tmp_path / "nopython"
    b.mkdir(exist_ok=True)
    (b / "python3").write_text("#!/bin/sh\necho 'python3 refused in this test' >&2\nexit 99\n")
    (b / "python3").chmod(0o755)
    return f"{b}:{os.environ.get('PATH', '')}"


def _tree_state(d: Path):
    """None when `d` is absent, else every entry under it with its size and mtime: a refusal that created, removed or rewrote anything there
    reads differently (an existence check alone fails once the real run has made the dir)."""
    if not d.exists():
        return None
    return sorted((str(p.relative_to(d)), p.lstat().st_size, p.lstat().st_mtime_ns) for p in d.rglob("*"))


def _bp(env):
    return subprocess.run([sys.executable, str(BP_SCRIPT), "2017-21"], capture_output=True, text=True, env=env, cwd=BP_SCRIPT.parent)


@pytest.mark.parametrize("case", ["healthy", "no_restored", "short_calendar", "checks_file_exists", "freeze_fails"])
def test_02_build_paths_switched_runs_and_each_refusal(case, tmp_path, monkeypatch):
    """A healthy switched run exits 0 (both tables carry restored rows: the export-only CTA is a restored control); M65 no restored ticker -> exit 3
    before the fills table is written; M66 sessions.txt one short -> exit 2 (B6); a checks file already in the log dir -> exit 2 (once-only, F13); the
    freeze re-check failing -> exit 2 before anything is read (F2)."""
    tree = build_tree(tmp_path, monkeypatch, extra_export=("CTA", "CTB"), restored=("TSLA", "Y", "CTA"))
    chain(tree)
    log = tmp_path / "log"
    env = bp_env(tree, log)
    if case == "no_restored":
        g = tree["old"] / "symbol_guard.tsv"
        g.write_text("symbol\tbreaks\n" + "".join(f"{t}\t\n" for t in ("SPY", "TSLA", "Y", "Z", "CTA", "CTB")))
    elif case == "short_calendar":
        s = tree["v2"] / "sessions.txt"
        s.write_text("".join(s.read_text().splitlines(keepends=True)[:-1]))
    elif case == "checks_file_exists":
        log.mkdir()
        (log / "02_build_checks_2017-21.txt").write_text("a checks file from an earlier run\n")
    elif case == "freeze_fails":
        env["V2_TEST_FREEZE_CMD"] = "false"
    p = _bp(env)
    fills = tree["v2"] / "out" / "r_decomp_fills_2017-21.tsv.gz"
    if case == "healthy":
        assert p.returncode == 0, p.stderr[-500:]
        assert "B8 restored-ticker rows in r_decomp_fills: 2 of 3" in p.stdout and "B8 restored-ticker rows in r_decomp_control: 1 of" in p.stdout
        assert "TEST MODE" in p.stdout and (log / "02_build_checks_2017-21.txt").exists()
        assert {r["label"] for r in _stage_rows(tree, "02_build_paths")} == {v2c.chain_label(fills), v2c.chain_label(fills.with_name("r_decomp_control_2017-21.tsv.gz"))}
        return
    want = {"no_restored": (3, "REFUSED (B8): 0 fills on restored tickers"), "short_calendar": (2, "REFUSED (B6)"),
            "checks_file_exists": (2, "stage 5 runs ONCE"), "freeze_fails": (2, "the freeze re-check (V2_TEST_FREEZE_CMD) exited 1")}[case]
    assert (p.returncode, want[1] in p.stderr) == (want[0], True), (p.returncode, p.stderr[-500:])
    assert not fills.exists() and _stage_rows(tree, "02_build_paths") == []


@pytest.mark.parametrize("case", ["real_mode_scratch_dir", "real_mode_scratch_log", "test_mode_real_dir", "test_mode_fixed_log"])
def test_02_build_paths_honours_its_paths_only_in_test_mode(case, tmp_path, monkeypatch):
    """F13 / F6: on the real run CB_PRE_LOG must be the fixed rerun_v2_1025/ and CB_PRE_DIR the real cb702_pre_v2; test mode never touches the real
    dir nor the real log dir. Every case refuses before anything is read; nothing is created. The freeze re-check is `false` throughout, so a
    guard that failed to refuse would still stop there (never a real read, never a created dir)."""
    import runpy
    for k in ("CB_PRE_DIR", "CB_PRE_LOG", "V2_CHAIN_TEST"):                   # unswitched: the script's top level binds its literals and imports nothing
        monkeypatch.delenv(k, raising=False)
    here = runpy.run_path(str(BP_SCRIPT), run_name="_bp_constants")["HERE"]   # the script's own binding (what its guard compares); main is not run
    fixed = Path(here) / "rerun_v2_1025"
    existed = fixed.exists()
    base = {k: v for k, v in os.environ.items() if not k.startswith(("CB_PRE_", "V2_"))}
    tm = {"V2_CHAIN_TEST": "1", "V2_TEST_FREEZE_CMD": "false"}
    env = {"real_mode_scratch_dir": {**base, "CB_PRE_DIR": str(tmp_path / v2.V2_NAME), "CB_PRE_LOG": str(fixed)},
           "real_mode_scratch_log": {**base, "CB_PRE_DIR": str(tmp_path / v2.V2_NAME), "CB_PRE_LOG": str(tmp_path / "log")},
           "test_mode_real_dir": {**base, **tm, "CB_PRE_DIR": str(v2c.REAL_V2), "CB_PRE_LOG": str(tmp_path / "log")},
           "test_mode_fixed_log": {**base, **tm, "CB_PRE_DIR": str(tmp_path / v2.V2_NAME), "CB_PRE_LOG": str(fixed)}}[case]
    if not case.startswith("test_mode"):
        env["PATH"] = _no_python_path(tmp_path)                       # the real-mode cases: a guard that failed to refuse can start no python
    p = _bp(env)
    assert p.returncode == 2 and "REFUSED (B3)" in p.stderr, (p.returncode, p.stderr[-400:])
    assert {"real_mode_scratch_dir": "is not /Users/alvinfung/apollo_data/cb702_pre_v2", "real_mode_scratch_log": f"is not {fixed}",
            "test_mode_real_dir": "with the REAL data dir", "test_mode_fixed_log": "CB_PRE_LOG = the real run's"}[case] in p.stderr
    assert fixed.exists() == existed and not (tmp_path / "log").exists()


# ─── F6 / F2 / F7: 04_relaunch.sh end to end on stub read scripts ─────────────────────────────────────────────────────────────────────
STUB_LIB = r'''
import gzip, json, os, shutil, sys
from pathlib import Path
REAL = Path(os.environ["STUB_REAL_REPO"]) / "scripts" / "probes"
FAIL = os.environ.get("STUB_FAIL", "")
OUT, LOG = os.environ.get("CB_PRE_OUT"), os.environ.get("CB_PRE_LOG")
GOOD_CAL = {"A": "  calendar 1635 sessions (2016-01-04..2022-06-30)", "C": "  calendar = SPY sessions: 1635 (2016-01-04..2022-06-30); off-calendar bars dropped 0",
            "D": "  export loaded: 1635 sessions 2016-01-04..2022-06-30"}
EPISODES = "ticker\tE\nTSLA\t2020-01-02\nZ\t2020-02-03\n"

def gz(name, text):
    with gzip.open(Path(OUT) / name, "wt") as fh:
        fh.write(text)

def run(role):
    if role == "read2_01":
        for t in ("x200", "x150"):
            gz(f"wrecall_episodes_2017-21_{t}.tsv.gz", EPISODES + ("EXTRA\t2020-03-04\n" if FAIL == "episodes" else ""))
        print(GOOD_CAL["A"])
    elif role == "read2_02":
        gz("wrecall_catch_2017-21_x200.tsv.gz", "ticker\tcovered\n" + ("Z\t1\n" if FAIL == "b8" else "TSLA\t1\nZ\t1\n"))
        gz("wrecall_nights_2017-21_x200.tsv.gz", "ticker\tnight\nTSLA\t1\n")
        print(GOOD_CAL["D"])
    elif role in ("read2_03", "read1_03"):
        (Path(LOG) / "03_numbers.json").write_text("{}\n"); (Path(LOG) / "03_report.md").write_text("# report\n")
    elif role == "read1_02":
        for n in ("bdef_fills_2017-21.tsv.gz", "bdef_r1_2017-21.tsv.gz", "bdef_control_2017-21.tsv.gz"):
            gz(n, "ticker\tx\nTSLA\t1\n")
        print(GOOD_CAL["C"])
    elif role == "read3_02":
        for n in ("esr_win_2017-21.tsv.gz", "esr_r1_2017-21.tsv.gz"):
            gz(n, "ticker\tx\nTSLA\t1\n")
        print(GOOD_CAL["A"].replace("1635 sessions (2016-01-04", "1634 sessions (2016-01-05") if FAIL == "cal3" else GOOD_CAL["A"])
    elif role == "read4_02":
        for n in ("trail_win_2017-21.tsv.gz", "trail_r1_2017-21.tsv.gz"):
            gz(n, "ticker\tx\nTSLA\t1\n")
        print(GOOD_CAL["A"])
    elif role in ("read3_03", "read4_03"):
        d = "_702_entry_stop_retry_1022" if role == "read3_03" else "_702_trail_variants_1023"
        h = json.loads((REAL / d / "03_headline.json").read_text())
        if role == "read4_03" and FAIL == "pp":
            h["2017-21"]["A20_X1_P1"]["win_T2"]["kept_half"] += 1
        (Path(LOG) / "03_headline.json").write_text(json.dumps(h)); (Path(LOG) / "03_report.md").write_text("# report\n")
    elif role == "trade_impact":
        print("published C0 trades (stub)")
    elif role == "degraded":
        print("B9 DEGRADED-WALK REPORT (stub)")
'''
STUB_SCRIPTS = {"_702_winner_recall_1022": {"01_episodes.py": "read2_01", "02_catch.py": "read2_02", "03_report.py": "read2_03"},
                "_702_breakout_definition_1022": {"02_build.py": "read1_02", "03_report.py": "read1_03"},
                "_702_entry_stop_retry_1022": {"02_build.py": "read3_02", "03_report.py": "read3_03"},
                "_702_trail_variants_1023": {"02_build.py": "read4_02", "03_report.py": "read4_03"},
                "_705_rerun_v2_1023": {"v2_degraded.py": "degraded"}, "../backtest_data_audit": {"trade_impact.py": "trade_impact"}}


def stub_relaunch_tree(tmp_path) -> tuple:
    """A scratch data dir (the five prerequisites in the manifest, the 10-23 episode tables, the two guards: TSLA restored) and a scratch PROBES
    tree: the real v2_chain.py + stub read scripts that print each script's calendar line and write tiny tables (TSLA on every one)."""
    v, probes = tmp_path / v2.V2_NAME, tmp_path / "scripts" / "probes"
    (v / "out" / "rerun_1023" / "winner_recall").mkdir(parents=True)
    names = ("entries_pre_tl_com.tsv.gz", "trades_pre_p5.tsv.gz", "trades_pre_exitpb.tsv.gz", "r_decomp_fills_2017-21.tsv.gz", "r_decomp_control_2017-21.tsv.gz")
    for n in names:
        (v / "out" / n).write_text(n)
    v2c.manifest_append(v / "out" / v2c.MANIFEST_NAME, "test", [(f"{v2.V2_NAME}/out/{n}", v / "out" / n) for n in names])
    for t in ("x200", "x150"):
        with gzip.open(v / "out" / "rerun_1023" / "winner_recall" / f"wrecall_episodes_2017-21_{t}.tsv.gz", "wt") as fh:
            fh.write("ticker\tE\nTSLA\t2020-01-02\nZ\t2020-02-03\n")
    (v / "symbol_guard.tsv").write_text("symbol\nSPY\nTSLA\nZ\n")
    (tmp_path / v2.OLD_NAME).mkdir()
    (tmp_path / v2.OLD_NAME / "symbol_guard.tsv").write_text("symbol\nSPY\nZ\n")
    (probes / "_cb_backtest").mkdir(parents=True)
    shutil.copyfile(Path(v2c.__file__), probes / "_cb_backtest" / "v2_chain.py")
    (tmp_path / "stublib.py").write_text(STUB_LIB)
    for d, files in STUB_SCRIPTS.items():
        (probes / d).mkdir(parents=True, exist_ok=True)
        for f, role in files.items():
            (probes / d / f).write_text(f"import sys\nsys.path.insert(0, {str(tmp_path)!r})\nimport stublib\nstublib.run({role!r})\n")
    (probes / "_702_r_decomposition_1022" / "rerun_v2_1025").mkdir(parents=True)
    (probes / "_702_r_decomposition_1022" / "rerun_v2_1025" / "02_build_checks_2017-21.txt").write_text(
        "  calendar = SPY sessions: 1635 (2016-01-04..2022-06-30); off-calendar bars dropped 0\n")
    env = {**{k: x for k, x in os.environ.items() if not k.startswith(("CB_PRE_", "V2_", "STUB_"))}, "V2_DIR": str(v), "PROBES": str(probes),
           "LOGROOT": str(tmp_path / "logs"), "V2_CHAIN_TEST": "1", "V2_TEST_FREEZE_CMD": "true", "STUB_REAL_REPO": str(REAL_REPO)}
    return env, v, probes


def test_the_relaunch_end_to_end_on_stub_reads_registers_every_source_stage_7_reads(tmp_path):
    env, v, probes = stub_relaunch_tree(tmp_path)
    p = subprocess.run(["bash", str(RELAUNCH)], capture_output=True, text=True, env=env)
    assert p.returncode == 0, (p.stdout[-2000:], p.stderr[-2000:])
    assert p.stdout.count("CALENDAR OK") == 6 and "PP PARITY OK" in p.stdout and p.stdout.count("EQUAL:") == 2 and "TEST MODE" in p.stdout
    assert p.stdout.count("B8 RESTORED:") == 7 and "RELAUNCH DONE" in p.stdout
    rows = v2c.manifest_rows(v / "out" / v2c.MANIFEST_NAME)
    labels = {r["label"] for r in rows}
    for rd in v2c.READ_DIRS:                                          # F2: the read dirs' numbers / reports are registered (stage 7 reads them)
        assert any(lbl.startswith(f"{rd}/rerun_v2_1025/03_") for lbl in labels), rd
    for f in ("_702_breakout_definition_1022/rerun_v2_1025/03_report.md", "_702_breakout_definition_1022/rerun_v2_1025/03_numbers.json",
              "_702_winner_recall_1022/rerun_v2_1025/03_numbers.json", "_702_entry_stop_retry_1022/rerun_v2_1025/03_headline.json",
              "_702_trail_variants_1023/rerun_v2_1025/03_headline.json", f"{v2.V2_NAME}/out/rerun_v2_1025/trail_variants/trail_r1_2017-21.tsv.gz"):
        assert f in labels, f
    assert v2c.manifest_problems(v / "out" / v2c.MANIFEST_NAME, [(r["label"], r["path"]) for r in rows]) == []


@pytest.mark.parametrize("fail,rc,msg,not_after", [
    ("episodes", 2, "does not reproduce the 10-23 v2 table", "read2_02_catch.log"),                       # M63
    ("b8", 3, "REFUSED (B8): no restored-ticker row", "read1_02_build.log"),                               # M62
    ("cal3", 2, "REFUSED (B6)", "read3_03_report.log"),                                                    # M64
    ("pp", 2, "REFUSED (4.0)", "stage4/g8_c0.txt"),                                                        # M60
    ("p5", 2, "REFUSED: a prerequisite is not the table its stage wrote", "read2_01_episodes.log"),       # M61
    ("freeze", 2, "REFUSED: the freeze re-check failed - nothing runs", "read2_01_episodes.log")])        # F2
def test_the_relaunch_stops_at_each_failed_check_and_runs_nothing_after(fail, rc, msg, not_after, tmp_path):
    env, v, probes = stub_relaunch_tree(tmp_path)
    if fail == "p5":
        (v / "out" / "trades_pre_p5.tsv.gz").write_text("changed after its manifest line")
    elif fail == "freeze":
        env["V2_TEST_FREEZE_CMD"] = "false"
    else:
        env["STUB_FAIL"] = fail
    p = subprocess.run(["bash", str(RELAUNCH)], capture_output=True, text=True, env=env)
    assert p.returncode == rc and msg in p.stdout, (p.returncode, p.stdout[-1500:], p.stderr[-800:])
    assert not (tmp_path / "logs" / not_after).exists() and "RELAUNCH DONE" not in p.stdout


@pytest.mark.parametrize("case", ["real_mode_override", "real_mode_probes", "test_mode_real_dir", "test_mode_real_probes", "test_mode_no_probes"])
def test_the_relaunch_honours_its_overrides_only_in_test_mode(case, tmp_path):
    """F6: on the real run a test-only override refuses (exit 2); test mode refuses the real cb702_pre_v2 and the real code tree (whose
    rerun_v2_1025/ dirs are the real run's once-only outputs) and needs both overrides. Nothing runs, nothing is created."""
    base = {k: x for k, x in os.environ.items() if not k.startswith(("CB_PRE_", "V2_", "PROBES", "LOGROOT"))}
    base["PATH"] = _no_python_path(tmp_path)                           # a guard that failed to refuse can start nothing (the refusals are pure bash)
    tm = {"V2_CHAIN_TEST": "1", "V2_TEST_FREEZE_CMD": "false", "LOGROOT": str(tmp_path / "logs")}
    (tmp_path / "probes").mkdir()
    real_out = v2c.REAL_V2 / "out" / "rerun_v2_1025"                 # the real run's once-only outputs (present since the 10-26 run): never touched
    before = _tree_state(real_out)
    if case == "test_mode_real_dir" and not v2c.REAL_V2.is_dir():
        pytest.skip("the real cb702_pre_v2 is not on this machine")
    if case == "test_mode_real_probes" and not REAL_PROBES.is_dir():
        pytest.skip("the real code tree is not on this machine")
    env = {"real_mode_override": {**base, "V2_DIR": str(tmp_path)}, "real_mode_probes": {**base, "PROBES": str(tmp_path / "probes")},
           "test_mode_real_dir": {**base, **tm, "V2_DIR": str(v2c.REAL_V2), "PROBES": str(tmp_path / "probes")},
           "test_mode_real_probes": {**base, **tm, "V2_DIR": str(tmp_path), "PROBES": str(REAL_PROBES)},
           "test_mode_no_probes": {**base, **tm, "V2_DIR": str(tmp_path)}}[case]
    p = subprocess.run(["bash", str(RELAUNCH)], capture_output=True, text=True, env=env)
    want = {"real_mode_override": "V2_DIR is set - a test-only override", "real_mode_probes": "PROBES is set - a test-only override",
            "test_mode_real_dir": "with the REAL /Users/alvinfung/apollo_data", "test_mode_real_probes": "its rerun_v2_1025/ dirs are the real run's",
            "test_mode_no_probes": "needs V2_DIR and PROBES"}[case]
    assert p.returncode == 2 and want in p.stdout, p.stdout
    assert not (tmp_path / "logs").exists() and _tree_state(real_out) == before


# ─── F2: the freeze re-check ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_freeze_recheck_runs_the_runners_dry_run_on_the_real_run_and_the_test_command_in_test_mode(monkeypatch):
    calls = []

    class P:
        def __init__(self, rc, out):
            self.returncode, self.stdout, self.stderr = rc, out, ""
    monkeypatch.delenv("V2_CHAIN_TEST", raising=False)
    monkeypatch.setattr(v2c.subprocess, "run", lambda cmd, **k: (calls.append(cmd), P(0, "V2-EXIT-READ DRY RUN (freeze check passed; ..."))[1])
    assert v2c.freeze_recheck(v2c.REAL_V2, say=lambda m: None) == []
    cmd = calls[-1]
    assert cmd[1].endswith("_cb_backtest/runner.py") and cmd[2:4] == ["v2-exit-read", "--data"] and "--dry-run" in cmd
    assert cmd[cmd.index("--data-pre") + 1] == str(v2c.REAL_V2) and cmd[cmd.index("--period") + 1] == "pre"
    monkeypatch.setattr(v2c.subprocess, "run", lambda cmd, **k: P(0, "something else"))          # exit 0 without the passed line: refused
    assert v2c.freeze_recheck(v2c.REAL_V2, say=lambda m: None) != []
    monkeypatch.setattr(v2c.subprocess, "run", lambda cmd, **k: P(2, ""))
    assert v2c.freeze_recheck(v2c.REAL_V2, say=lambda m: None) != []
    monkeypatch.undo()
    monkeypatch.setenv("V2_CHAIN_TEST", "1")
    monkeypatch.delenv("V2_TEST_FREEZE_CMD", raising=False)
    assert "is unset" in v2c.freeze_recheck("x", say=lambda m: None)[0]
    monkeypatch.setenv("V2_TEST_FREEZE_CMD", "false")
    assert v2c.freeze_recheck("x", say=lambda m: None) != []
    monkeypatch.setenv("V2_TEST_FREEZE_CMD", "true")
    assert v2c.freeze_recheck("x", say=lambda m: None) == []
    assert v2c.data_dir_problem(v2c.REAL_V2) is not None                                         # test mode never takes the real dir
    monkeypatch.delenv("V2_CHAIN_TEST")
    assert v2c.data_dir_problem(Path("/tmp") / v2.V2_NAME) is not None and v2c.data_dir_problem(v2c.REAL_V2) is None


# ─── F4: the manifest registers a table once ──────────────────────────────────────────────────────────────────────────────────────────
def test_the_manifest_refuses_a_re_registered_label_and_flags_a_path_mismatch_and_a_rewritten_header(tmp_path):
    m, f, g = tmp_path / "m.tsv", tmp_path / "a.txt", tmp_path / "b.txt"
    f.write_text("a")
    g.write_text("b")
    v2c.manifest_append(m, "s1", [("A", f)])
    with pytest.raises(v2c.ChainRefusal, match="already registered"):
        v2c.manifest_append(m, "s2", [("A", g)])                                    # a second line for A: refused (the M31-equivalent hole, closed)
    with pytest.raises(v2c.ChainRefusal, match="already registered"):
        v2c.manifest_append(m, "s2", [("B", g), ("B", f)])
    assert v2c.main(["manifest-add", str(m), "s3", "A", str(g)]) == 2
    rows = v2c.manifest_rows(m)
    fields = ("A", str(g), v2c.sha256_file(g), "s9", "t")                         # forge a validly chained second line for A
    ls = v2c._line_sha(rows[-1]["line_sha"], fields)
    m.write_text(m.read_text() + "\t".join((*fields, rows[-1]["line_sha"], ls)) + "\n")
    pr = v2c.manifest_problems(m, [("A", g)])
    assert any("2 lines" in p for p in pr), pr
    m2 = tmp_path / "m2.tsv"
    v2c.manifest_append(m2, "s1", [("A", f)])
    assert "names" in v2c.manifest_problems(m2, [("A", g)])[0]                      # M30: the line names another path
    m2.write_text(m2.read_text().replace("label\tpath", "label\tPATH", 1))
    assert "header" in v2c.manifest_problems(m2, [("A", f)])[0]                     # M33


def test_every_chain_path_has_one_label_rule_shared_by_the_bodies_the_relaunch_and_stage_7(tmp_path):
    """The labels stage 7 checks are the labels the stages wrote: v2_rerun_read's out_label / small_label and 02_build_paths' f-string are
    chain_label of the same paths; every LOGICAL new path has a label; a path the chain never makes raises."""
    from scripts.probes._705_rerun_v2_1023 import v2_compare as vc
    out, small = REAL_DATA / v2.V2_NAME / "out", REAL_REPO / "scripts/probes/_cb_backtest/out" / v2.SMALL_SUB
    for n in v2.PRE_OUTPUTS + v2.H60_OUTPUTS + v2.EXIT_OUTPUTS + v2.STEP0_OUTPUTS:
        assert v2.out_label(n) == v2c.chain_label(out / n)
    for n in v2.PRE_SMALL + v2.H60_SMALL + v2.EXIT_SMALL + v2.STEP0_SMALL:
        assert v2.small_label(n) == v2c.chain_label(small / n)
    assert v2c.chain_label(out / "r_decomp_fills_2017-21.tsv.gz") == f"{v2.V2_NAME}/out/r_decomp_fills_2017-21.tsv.gz"
    for k, (_o, n) in vc.LOGICAL.items():
        assert v2c.chain_label(n), k
    for bad in (REAL_DATA / "cb702_pre" / "out" / "x.tsv.gz", REAL_REPO / "scripts/probes/_cb_backtest/out/p5_report_pre.tsv",
                REAL_REPO / "scripts/probes/_702_trail_variants_1023/03_headline.json"):
        with pytest.raises(ValueError):
            v2c.chain_label(bad)


# ─── F1 / F2 / F10: the comparison's own guards ───────────────────────────────────────────────────────────────────────────────────────
def test_every_new_source_is_a_chain_path_distinct_from_its_old_path():
    """F1 (M46 / M47): pointing a new source at the OLD file (or anywhere but the chain's outputs) is refused."""
    from scripts.probes._705_rerun_v2_1023 import v2_compare as vc
    assert vc.logical_problems() == []
    roots = ("/rerun_v2_1025/", "/v2_1025/", f"/{v2.V2_NAME}/out/")
    for k, (o, n) in vc.LOGICAL.items():
        assert Path(o) != Path(n) and any(r in str(n) for r in roots), k
        assert not any(r in str(o) for r in roots), k
    assert set(vc.OLD_PINS) == {k for k in vc.LOGICAL if k not in vc.TABLES}


@pytest.mark.parametrize("name,new", [("read4_03_headline.json", "OLD"), ("p5_report_pre.tsv", "OLD"), ("read1_03_numbers.json", "/tmp/hand_made/03_numbers.json")])
def test_a_new_source_pointed_elsewhere_is_refused(name, new, monkeypatch):
    from scripts.probes._705_rerun_v2_1023 import v2_compare as vc
    o, _n = vc.LOGICAL[name]
    monkeypatch.setitem(vc.LOGICAL, name, (o, o if new == "OLD" else Path(new)))
    assert any(name in p for p in vc.logical_problems())


def test_the_section7_tables_are_the_scripts_lines_roles_and_rules(monkeypatch):
    """F10 (M52 / M53): the doc's §7 (above the marker) parsed against LINES - a demoted deciding line, a changed rule, a doc edit all differ."""
    from scripts.probes._705_rerun_v2_1023 import v2_compare as vc
    doc = vc.DOC.read_text(encoding="utf-8")
    assert vc.section7_problems(doc) == []
    s7 = vc.section7(doc)
    assert len(s7["lines"]) == len(vc.LINES) == 43 and s7["tols"]["1.2"] == 4.1 and s7["tols"]["4.2b"] == 2.0 and s7["tols"]["3.7"] == 2.0
    for lid, role in (("4.2b", "beside"), ("2.5", "beside"), ("1.6", "beside")):
        lines = [dict(ln, role=role) if ln["id"] == lid else ln for ln in vc.LINES]
        monkeypatch.setattr(vc, "LINES", lines)
        assert any(f"line {lid}" in p for p in vc.section7_problems(doc)), lid
        monkeypatch.undo()
    monkeypatch.setattr(vc, "LINES", [dict(ln, rule="R3") if ln["id"] == "S6" else ln for ln in vc.LINES])
    assert any("line S6" in p for p in vc.section7_problems(doc))
    monkeypatch.undo()
    assert any("line 2.5" in p for p in vc.section7_problems(doc.replace("| 3 of 481 = 0.6% | R3 (±2) | deciding", "| 3 of 481 = 0.6% | R3 (±2) | beside")))
    assert any("±2.6" in p or "line 2.4" in p for p in vc.section7_problems(doc.replace("| 25 of 481 = 5.2% | R3 (±2.6)", "| 25 of 481 = 5.2% | R3 (±3.6)")))
    assert vc.section7_problems(doc.replace("must reproduce 1,181", "must reproduce 1,180")) != []


def test_the_compare_cli_refuses_proof_options_without_proofs_and_never_writes_the_real_record_in_proofs(tmp_path, monkeypatch, capsys):
    from scripts.probes._705_rerun_v2_1023 import v2_compare as vc
    monkeypatch.setattr(vc, "OUT", tmp_path / "v2_compare.txt")
    monkeypatch.setattr(vc.v2c, "freeze_recheck", lambda *a, **k: pytest.fail("the full re-check ran before the in-process checks refused"))
    for opts in (["--new-flat", str(tmp_path)], ["--old-flat", str(tmp_path)], ["--out", str(tmp_path / "x.txt")], ["--expect-episodes", "994"],
                 ["--guards", "a", "b"]):
        capsys.readouterr()
        assert vc.main(opts) == 2 and "the proofs' options only" in capsys.readouterr().err, opts          # N07
    for out in (vc.OUT, Path(str(vc.OUT) + ".partial")):
        assert vc.main(["--proofs", "--new-flat", str(tmp_path), "--out", str(out)]) == 2 and "never" in capsys.readouterr().err   # N08
    assert vc.main(["--proofs", "--new-flat", str(tmp_path)]) == 2 and "--proofs needs --out" in capsys.readouterr().err
    assert not vc.OUT.exists() and not (tmp_path / "x.txt").exists()


def test_the_compare_real_run_refuses_before_reading_while_unfrozen_and_runs_once(tmp_path, monkeypatch, capsys):
    """Today the footer carries no pin: the real run refuses at the pin check (in process; the runner is never started). An existing record or its
    .partial refuses first (once-only)."""
    from scripts.probes._705_rerun_v2_1023 import v2_compare as vc
    monkeypatch.setattr(vc, "OUT", tmp_path / "v2_compare.txt")
    monkeypatch.setattr(vc.v2c, "freeze_recheck", lambda *a, **k: pytest.fail("the runner's dry run was started"))
    if "(empty)" in vc.DOC.read_text(encoding="utf-8").split("<!-- FREEZE -->", 1)[1]:
        assert vc.main([]) == 2 and "not its §8 footer pin" in capsys.readouterr().err
    for name in ("v2_compare.txt", "v2_compare.txt.partial"):
        (tmp_path / name).write_text("x")
        assert vc.main([]) == 2 and "runs ONCE" in capsys.readouterr().err
        (tmp_path / name).unlink()


def test_the_compare_real_run_refuses_when_the_freeze_recheck_fails(tmp_path, monkeypatch):
    """F2: with every in-process check passing (pins stubbed), the full re-check is run and its failure refuses before any source is read."""
    from scripts.probes._705_rerun_v2_1023 import v2_compare as vc
    monkeypatch.setattr(vc, "OUT", tmp_path / "v2_compare.txt")
    monkeypatch.setattr(vc.v2c, "footer_pin_problems", lambda *a, **k: [])
    seen = []
    monkeypatch.setattr(vc.v2c, "freeze_recheck", lambda d, **k: (seen.append(d), ["the freeze re-check failed (exit 2): doc body sha256 mismatch"])[1])
    monkeypatch.setattr(vc.v2c, "manifest_problems", lambda *a, **k: pytest.fail("a source was checked before the re-check refused"))
    assert vc.real_run_checks(say=lambda m: None) == ["the freeze re-check failed (exit 2): doc body sha256 mismatch"] and seen == [vc.V2_DATA]
    assert vc.main([]) == 2 and not vc.OUT.exists()


def test_the_compare_real_run_checks_the_manifest_and_a_failed_source_check_writes_a_refusal_once(tmp_path, monkeypatch, capsys):
    """Past the pins and the re-check (both stubbed): a new source with no manifest line refuses (F2); with the manifest stubbed, an OLD value
    that is not §7's quote writes a refusal record (no verdict) and exits 2 - and a second run is refused (F1)."""
    from scripts.probes._705_rerun_v2_1023 import v2_compare as vc
    monkeypatch.setattr(vc, "OUT", tmp_path / "v2_compare.txt")
    monkeypatch.setattr(vc.v2c, "footer_pin_problems", lambda *a, **k: [])
    monkeypatch.setattr(vc.v2c, "freeze_recheck", lambda *a, **k: [])
    monkeypatch.setattr(vc, "V2_DATA", tmp_path / v2.V2_NAME)                      # no manifest there
    assert vc.main([]) == 2 and "is not the file the chain wrote (manifest)" in capsys.readouterr().err
    monkeypatch.setattr(vc.v2c, "manifest_problems", lambda *a, **k: [])
    old, new = tmp_path / "old", tmp_path / v2.V2_NAME / "out" / "flat"          # new: a chain-shaped path (its label derives)
    old.mkdir()
    new.mkdir(parents=True)
    logical = {}
    for k, (o, _n) in vc.LOGICAL.items():
        if k in vc.TABLES:
            logical[k] = (old / k, new / k)                                         # absent: the restored-only values report 'not computed'
            continue
        if not Path(o).is_file():
            pytest.skip(f"the published source {o} is not on this machine")
        shutil.copyfile(o, old / k)
        shutil.copyfile(o, new / k)
        logical[k] = (old / k, new / k)
    d = json.loads((old / "read2_03_numbers.json").read_text())
    d["2017-21/x200/funnel"][vc.FUNNEL["watched"]][0] = 239                         # the OLD value read is no longer §7's 240
    (old / "read2_03_numbers.json").write_text(json.dumps(d))
    monkeypatch.setattr(vc, "LOGICAL", logical)
    monkeypatch.setattr(vc, "logical_problems", lambda: [])
    monkeypatch.setattr(vc, "restored_symbols", lambda *a: frozenset())
    assert vc.main([]) == 2
    rec = vc.OUT.read_text()
    assert "COMPARISON REFUSED - a source check failed" in rec and "2.2" in rec and "CONCLUSION" not in rec and "SOURCE SHA256" in rec
    assert not Path(str(vc.OUT) + ".partial").exists()
    capsys.readouterr()
    assert vc.main([]) == 2 and "runs ONCE" in capsys.readouterr().err
    vc.OUT.unlink()                                                                 # a crash mid-comparison leaves the reserved .partial: spent
    monkeypatch.setattr(vc, "compare", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("a getter crashed")))
    with pytest.raises(RuntimeError):
        vc.main([])
    assert Path(str(vc.OUT) + ".partial").exists() and not vc.OUT.exists()
    capsys.readouterr()
    assert vc.main([]) == 2 and "runs ONCE" in capsys.readouterr().err


# ─── F3 / F11: the rules on NaN and on their exact boundaries ─────────────────────────────────────────────────────────────────────────
def test_the_rules_never_read_a_non_finite_value_as_holds():
    from scripts.probes._705_rerun_v2_1023 import v2_compare as vc
    nan, iv = float("nan"), lambda d, lo, hi: {"d": d, "lo": lo, "hi": hi, "n": 1}
    old = iv(0.0109, -0.0069, 0.0292)
    assert vc.apply("R1", old, iv(0.01, nan, nan))[0] == vc.NC                      # the checker's case: was 'holds'
    assert vc.apply("R1", old, iv(nan, -0.01, 0.03))[0] == vc.NC                    # was 'moved' (counted as holds)
    assert vc.apply("R1", old, iv(0.01, -float("inf"), 0.03))[0] == vc.NC
    assert vc.apply("R3", {"k": 240, "n": 481}, {"k": 0, "n": 0})[0] == vc.NC
    assert vc.apply("R3", {"k": 240, "n": 481}, {"k": nan, "n": 481})[0] == vc.NC
    assert vc.apply("R5", 1.16, nan)[0] == vc.NC and vc.apply("SIGN", 84, nan)[0] == vc.NC
    assert vc.apply("R3d", {"e": 0.1782, "c": 0.1871}, {"e": nan, "c": 0.18})[0] == vc.NC
    assert vc.apply("R2+R1", {**old, "word": "CAN'T TELL"}, {**iv(0.2, nan, 0.9), "word": "CAN'T TELL"})[0] == vc.NC
    assert vc.apply("R2", "loss", None)[0] == vc.NC
    best = {"best": "S2_T2", "shares": {"S2_T2": nan, "S1_T2": 0.4}, "named": "S2_T2", "k": 213, "n": 481}
    assert vc.apply("R4+R3", {"k": 213, "n": 481}, best)[0] == vc.NC
    assert vc.check_line({"id": "2.0"}, nan)[0] == "FAILS" and vc.check_line({"id": "2.0"}, 1180)[0] == "FAILS"   # M48
    assert vc.check_line({"id": "2.0"}, 1181)[0] == "passes"


def test_pp_parity_flags_nan_and_a_difference_of_1e_8():
    """F3 / F11 (M37): NaN on either side is a difference; 1e-8 is past the 1e-9 tolerance."""
    h3 = json.loads((REAL_REPO / "scripts/probes/_702_entry_stop_retry_1022/03_headline.json").read_text())
    h4 = json.loads((REAL_REPO / "scripts/probes/_702_trail_variants_1023/03_headline.json").read_text())
    assert v2c.pp_parity_problems(h3, h4) == []
    import copy
    a = copy.deepcopy(h4)
    a["2017-21"]["A20_X1_P1"]["R1_T0"]["r_trade"] = float("nan")
    assert any("r_per_base" in p for p in v2c.pp_parity_problems(h3, a))
    b = copy.deepcopy(h4)
    b["2017-21"]["A20_X1_P1"]["R1_T0"]["r_trade"] = h3["2017-21"]["all_S2_T0"]["r_per_base"] + 1e-8
    assert any("r_per_base" in p for p in v2c.pp_parity_problems(h3, b))


def test_the_rules_on_their_exact_boundaries():
    """F11: R1 lo == 0 is SPANS (M42); an R3 difference of exactly the tolerance holds and 0.01 over changes (M43); an R4 gap of exactly 2.00 points
    is a tie and 2.01 is not (M44); R2+R1 reads the verdict word (M50); a SIGN flip changes (M51)."""
    from scripts.probes._705_rerun_v2_1023 import v2_compare as vc
    iv = lambda d, lo, hi: {"d": d, "lo": lo, "hi": hi, "n": 1}
    assert vc.r1_class(iv(0.01, 0.0, 0.03)) == "SPANS" and vc.r1_class(iv(-0.01, -0.03, 0.0)) == "SPANS"
    assert vc.apply("R1", iv(0.01, -0.01, 0.03), iv(0.02, 0.0, 0.04))[0] == "holds"
    assert vc.apply("R3", {"k": 50, "n": 100}, {"k": 55, "n": 100})[0] == "holds"                   # exactly 5.00 points
    assert vc.apply("R3", {"k": 50, "n": 100}, {"k": 5501, "n": 10000})[0] == "changes"             # 5.01
    named = lambda b: {"best": "S1_T2", "shares": {"S1_T2": b, "S2_T2": 0.44}, "named": "S2_T2", "k": 213, "n": 481}
    assert vc.apply("R4+R3", {"k": 213, "n": 481}, named(0.46))[0] == "holds"                         # a 2.00-point tie
    assert vc.apply("R4+R3", {"k": 213, "n": 481}, named(0.4601))[0] == "changes"                     # 2.01
    w = lambda word: {**iv(-0.12, -0.19, -0.05), "word": word, "n": 180}
    assert vc.apply("R2+R1", w("loss"), w("can't tell"))[0] == "changes" and vc.apply("R2+R1", w("loss"), w("loss"))[0] == "holds"
    assert vc.apply("SIGN", 84, -1)[0] == "changes" and vc.apply("SIGN", 84, 3)[0] == "holds"


def test_the_calendar_checks_catch_a_same_length_shift_and_a_first_date_change(tmp_path):
    """F11 (M34 / M35)."""
    sessions = ["2016-01-04", "2016-01-05", "2016-01-06"]
    assert v2c.calendar_problem(["2016-01-05", "2016-01-06", "2016-01-07"], sessions) is not None          # same length, shifted
    assert v2c.calendar_problem(list(sessions), sessions) is None
    log = tmp_path / "x.log"
    log.write_text("  calendar 1635 sessions (2016-01-05..2022-06-30)\n")                                 # the count right, the first date not
    assert v2c.log_calendar_problems(log) != []
    log.write_text("  calendar 1635 sessions (2016-01-04..2022-07-01)\n")
    assert v2c.log_calendar_problems(log) != []


# ─── F12: the receipt and the freeze map against literal lists (never a list checked against itself) ─────────────────────────────────
PROTECTED_SMALL_LITERAL = ("p5_report_pre.txt", "p5_report_pre.tsv", "p5_summary_pre.txt", "minute_summary_pre_tl_com.txt", "h60_step0_pre.txt",
                           "h60_report_pre.txt", "h60_hindsight_pre.txt", "h60_report_pre.tsv", "h60_summary_pre.txt", "h60_verdict_pre.txt",
                           "h60_hindsight_pre.tsv", "exitpb_report_pre.txt", "exitpb_report_pre.tsv", "exitpb_deltas_pre.tsv", "exitpb_summary_pre.txt",
                           "exitpb_verdict_pre.txt")                      # §4's table of old printouts, typed from the doc
FROZEN_LABELS_LITERAL = (
    "module", "code/constants.py", "code/anticipation.py", "code/live_fill_counterfactuals.py", "code/rule_eras.py", "code/exit_logic.py",
    "code/v2_chain.py", "code/02_build_paths.py",
    "code/_702_winner_recall_1022/01_episodes.py", "code/_702_winner_recall_1022/02_catch.py", "code/_702_winner_recall_1022/03_report.py",
    "code/_702_breakout_definition_1022/02_build.py", "code/_702_breakout_definition_1022/03_report.py",
    "code/_702_entry_stop_retry_1022/esr_lib.py", "code/_702_entry_stop_retry_1022/02_build.py", "code/_702_entry_stop_retry_1022/03_report.py",
    "code/_702_trail_variants_1023/trail_lib.py", "code/_702_trail_variants_1023/02_build.py", "code/_702_trail_variants_1023/03_report.py",
    "code/04_relaunch.sh", "code/trade_impact.py", "code/v2_compare.py", "code/v2_degraded.py",
    "cb702_pre_v2/daily_closes_all.csv.gz", "cb702_pre_v2/daily_raw_close.csv.gz", "cb702_pre_v2/cb702_sic.psv", "cb702_pre_v2/small_pulls.psv",
    "cb702_pre_v2/symbol_guard.tsv", "cb702_pre_v2/sessions.txt", "cb702_pre_v2/dedupe_applied.tsv", "cb702_pre_v2/export_stats.tsv",
    "cb702_pre_v2/audit_1023/verdict.txt", "cb702_pre_v2/out/candidates_tl_com.tsv", "cb702_pre_v2/out/watch_tl_com.tsv.gz",
    "cb702_pre_v2/out/gap_in_bars_tl_com.tsv", "cb702_pre_v2/out/minute_fetch_list_tl_com.tsv", "cb702_pre_v2/minutes/_done.psv",
    "cb702_pre_v2/audit_1023/price/A_flags.tsv", "cb702_pre_v2/minutes (tree)",
    "cb702_pre_v2/out/v2_step0_1025/h60_step0_pre.tsv.gz", "cb702_pre_v2/out/v2_step0_1025/h60_step0_pre.txt",
    "cb702_pre_v2/out/v2_step0_1025/h60_step0_pre_counts.json", "_cb_backtest/out/v2_1025/step0/h60_step0_pre.txt",
    "cb702_pre_v2/out/rerun_1023/winner_recall/wrecall_episodes_2017-21_x200.tsv.gz", "cb702_pre_v2/out/rerun_1023/winner_recall/wrecall_episodes_2017-21_x150.tsv.gz",
    "cb702_pre_v2/audit_1023/pit_calendar_minutes_1025.console.txt", "cb702_pre/symbol_guard.tsv", "cb702_pre/out/h60_verdict_pre.json",
    "cb702_pre/out/exitpb_verdict_pre.json", "_cb_backtest/out/p5_report_pre.tsv", "read1/03_report.md", "read1/03_numbers.json",
    "read2/03_numbers.json", "read3/03_headline.json", "read4/03_headline.json")       # §8's list, typed from the doc


def test_the_protected_names_and_the_freeze_labels_equal_the_docs_lists(tmp_path, monkeypatch):
    """F12 (M19 / M21 / M22 / M40)."""
    assert v2c.PROTECTED_SMALL == PROTECTED_SMALL_LITERAL
    files = v2c.protected_files()
    assert all(f"_cb_backtest/out/{n}" in files for n in PROTECTED_SMALL_LITERAL)
    tree = build_tree(tmp_path, monkeypatch)
    got = set(v2.v2_frozen(ctx_of(tree)))
    assert got == set(FROZEN_LABELS_LITERAL), (sorted(got - set(FROZEN_LABELS_LITERAL)), sorted(set(FROZEN_LABELS_LITERAL) - got))
    full = set(rr.frozen_map(rn.REGISTERED_READS["v2-pre-read"], ctx_of(tree)))
    assert full == set(FROZEN_LABELS_LITERAL) | {"runner", "scaffold", "spec module"}
    doc = (REAL_REPO / "docs" / "analysis" / v2.V2_DOC).read_text(encoding="utf-8").split(rn.FREEZE_MARK)[0]
    s8 = doc.split("## 8. ", 1)[1].split("## 9. ", 1)[0]
    for name in ("daily_closes_all.csv.gz", "dedupe_applied.tsv", "audit_1023/price/A_flags.tsv", "pit_calendar_minutes_1025.console.txt",
                 "cb702_pre/symbol_guard.tsv", "h60_step0_pre_counts.json"):
        assert name in s8, name


# ─── F14: the degraded-walk classes on their boundaries, the raw close, and the 60 SESSIONS of the one calendar ────────────────────────
def test_the_ending_classes_on_their_boundaries_the_raw_close_and_a_holed_ticker(tmp_path):
    from scripts.probes._705_rerun_v2_1023 import v2_degraded as dg
    days = [d.isoformat() for d in T._weekdays(200, T.dt.date(2019, 1, 7))]
    c = lambda xs: np.array(xs, dtype=float)
    # collapse at exactly -50% over 60 sessions; -45% is not (M57)
    assert dg.ending_class(days[:150], c([10.0] * 89 + [20.0] + [10.0] * 60), None, days) == "collapse"
    assert dg.ending_class(days[:150], c([10.0] * 89 + [20.0] + [11.0] * 59 + [11.0]), None, days) == "deal-like"   # -45%, pinned flat
    assert dg.ending_class(days[:150], c([10.0] * 89 + [20.0] + list(np.linspace(14, 11, 60))), None, days) == "other"
    # deal-like at exactly a 1% spread; 1.5% is other (M56)
    assert dg.ending_class(days[:150], c([10.0] * 140 + [12.0] * 9 + [12.12]), None, days) == "deal-like"
    assert dg.ending_class(days[:150], c([10.0] * 140 + [12.0] * 9 + [12.18]), None, days) == "other"
    # the RAW close under $1 while the adjusted is not: collapse (M58)
    adj = c([10.0] * 140 + [5.0 + 0.3 * k for k in range(10)])
    assert dg.ending_class(days[:150], adj, None, days) == "other"
    assert dg.ending_class(days[:150], adj, c([np.nan] * 149 + [0.9]), days) == "collapse"
    # a holed ticker: 20 sessions missing inside its last 60 - the window is 60 SESSIONS, not 61 bars (F14a)
    keep = [k for k in range(150) if not (100 <= k < 120)]
    closes = c([9.5 if k < 80 else (20.0 if k <= 89 else 9.0) for k in keep])
    assert dg.ending_class([days[k] for k in keep], closes, None, days) == "collapse"            # the close 60 sessions back (session 89) was 20
    assert closes[-1] / closes[-61] - 1 > -0.5                                                    # a bar-indexed window would have read 9.5 -> not collapse
    with pytest.raises(ValueError):
        dg.ending_class(["2030-01-01"], c([1.0]), None, days)                                     # a last bar off the calendar


# ─── F5: the freeze diff gate's base is pinned, never chosen at check time ────────────────────────────────────────────────────────────
def test_the_freeze_diff_base_is_the_pinned_registered_body(monkeypatch):
    from scripts.probes._705_rerun_v2_1023 import v2_freeze_diff_check as fd
    real = registered_doc_text()                                    # the doc as registered (the fixture): §5 unfilled, the body pinned
    with pytest.raises(v2.Refuse):
        v2.parse_section5(real)
    assert fd.body_sha(real) == fd.REG_BODY_SHA == rn.doc_body_sha(real)
    live = (REAL_REPO / "docs" / "analysis" / v2.V2_DOC).read_text(encoding="utf-8")
    assert fd.problems(real, live) == []                            # the working doc = the registered body + §5's counts and the G9 reference only
    rel = f"docs/analysis/{v2.V2_DOC}"
    assert fd.base_text("0" * 40, rel)[1] and fd.main([]) == 2
    # a commit carrying the registered body passes the base check; a later §7 edit committed and passed as the base does not
    calls = {}

    class P:
        def __init__(self, rc, out=""):
            self.returncode, self.stdout, self.stderr = rc, out, ""

    def git(*args):
        calls.setdefault(args[0], 0)
        calls[args[0]] += 1
        if args[0] == "rev-parse":
            return P(0, "f" * 40 + "\n")
        if args[0] == "merge-base":
            return P(0)
        return P(0, calls["doc"])
    monkeypatch.setattr(fd, "_git", git)
    calls["doc"] = real.split(fd.MARK)[0].replace("R3 — a share of a population.", "R3 — a share.") + fd.MARK
    assert "is not the registration commit" in fd.base_text("HEAD", rel)[1][0]
    calls["doc"] = real
    assert fd.base_text("HEAD", rel) == (real, [])


def test_the_freeze_diff_base_refuses_the_round_1_commit_and_takes_the_registration_commit():
    """The same base check on the REAL history: the 10-25 round-1 commit carries another body and is refused; the registration commit passes and
    its doc is the fixture byte for byte. Needs both commits in the checkout - a depth-1 clone (GitHub CI) has neither."""
    from scripts.probes._705_rerun_v2_1023 import v2_freeze_diff_check as fd
    missing = [c for c in (ROUND1_COMMIT, REGISTRATION_COMMIT) if not _has_commit(c)]
    if missing:
        pytest.skip(f"commit(s) {', '.join(missing)} not in this checkout (a shallow clone: GitHub CI checks out depth 1); the pinned-body "
                    f"half runs in test_the_freeze_diff_base_is_the_pinned_registered_body")
    rel = f"docs/analysis/{v2.V2_DOC}"
    _t, pr = fd.base_text(ROUND1_COMMIT, rel)                       # the 10-25 commit carries the round-1 body, not the registered one
    assert pr and "is not the registration commit" in pr[0]
    assert fd.main([ROUND1_COMMIT]) == 2
    assert fd.base_text(REGISTRATION_COMMIT, rel) == (registered_doc_text(), [])


def test_the_freeze_diff_rule_refuses_re_filling_an_already_filled_v2_cell():
    """M69: a v2 cell that already holds a count may not change again (only (B2) cells are filled)."""
    from scripts.probes._705_rerun_v2_1023 import v2_freeze_diff_check as fd
    real = registered_doc_text()
    keys = ("C0", "C0_multi", "C1", "C1_multi", "orh5_C1_fills", "C2", "C3", "C4", "C5", "C6", "C7")
    counts = lambda v: {"table": {"pre": {**{k: v for k in keys}, "com_C1": v, "tl_rows": v}, "2020-21": {k: v for k in keys}},
                        "b8": {"pre": {"shared": v, "restored": v}, "2020-21": {"shared": v, "restored": v}}}
    first = v2.fill_section5(real, counts(1))
    second = first.replace("| 1 / 1 |", "| 2 / 1 |", 1)
    assert second != first
    assert any("not (B2)" in p for p in fd.problems(first, second))


def test_stage_7s_footer_labels_are_the_freeze_maps_labels_for_the_same_paths():
    """Stage 7 checks each old source and its own code against the footer by LABEL: each label must be the one v2_frozen pins, for the same path
    (a mismatched label would refuse the real run for good - or check the wrong file)."""
    import types
    from scripts.probes._705_rerun_v2_1023 import v2_compare as vc
    ctx = types.SimpleNamespace(repo=REAL_REPO, data=REAL_DATA / v2.V2_NAME, out=REAL_DATA / v2.V2_NAME / "out", rt=rn,
                                small=REAL_REPO / "scripts/probes/_cb_backtest/out")
    fz = v2.v2_frozen(ctx)
    for k, label in vc.OLD_PINS.items():
        assert Path(fz[label]) == Path(vc.LOGICAL[k][0]), (k, label)
    for label, pth in vc.CODE_PINS.items():
        assert Path(fz[label]).resolve() == Path(pth).resolve(), label
    assert vc.DOC == REAL_REPO / "docs" / "analysis" / v2.V2_DOC


@pytest.mark.parametrize("case", ["section7", "logical"])
def test_the_compare_real_run_refuses_an_edited_section7_or_a_bad_source_path(case, tmp_path, monkeypatch, capsys):
    """N13 / N16: the real run itself (not only the tests) refuses when §7's tables differ from the script, or a new source is not a chain path -
    before the pins, the re-check or any source is read."""
    from scripts.probes._705_rerun_v2_1023 import v2_compare as vc
    monkeypatch.setattr(vc, "OUT", tmp_path / "v2_compare.txt")
    monkeypatch.setattr(vc.v2c, "footer_pin_problems", lambda *a, **k: pytest.fail("the pins were checked before the refusal"))
    if case == "section7":
        doc = tmp_path / "doc.md"
        doc.write_text(vc.DOC.read_text(encoding="utf-8").replace("| 3 of 481 = 0.6% | R3 (±2) | deciding", "| 3 of 481 = 0.6% | R3 (±2) | beside"))
        monkeypatch.setattr(vc, "DOC", doc)
        want = "the §7 tables are not this script's lines / roles / rules: line 2.5"
    else:
        o, _n = vc.LOGICAL["read4_03_headline.json"]
        monkeypatch.setitem(vc.LOGICAL, "read4_03_headline.json", (o, o))
        want = "read4_03_headline.json: the new path is the old path"
    assert vc.main([]) == 2 and want in capsys.readouterr().err and not vc.OUT.exists()
