"""#705 (a) - tests for scripts/probes/_cb_backtest/registered_read.py: the shared 'registered read' scaffold and its speed helpers.

A DEMO read (registered here only, never in the runner's `main`) exercises every path of the driver on synthetic data: the guards that
cannot be dropped, the freeze pass / fail before any file is opened (the scaffold and the body's module pinned by the driver), a freeze map
that does not cover what the read opens, `--out` / `--minutes` checked against the dir THE PERIOD READS (the h60 hole) and `--out` honoured
by the body (the exit-read hole), once-only over the tables AND the verdict files + `.partial`, dry-run, the hard pins, the refusal texts
verbatim, a declared "no freeze", a read named after a built-in stage, and `main()` dispatching from the registry. No real outcome: every
number here is a synthetic bar.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import shutil
import time
from pathlib import Path

import numpy as np
import pytest

from scripts.probes._cb_backtest import registered_read as rr
from scripts.probes._cb_backtest import runner as rn

try:
    import test_cb_backtest_runner as T
except ImportError:                                          # pragma: no cover
    from tests import test_cb_backtest_runner as T

DEMO_COLS = ["ticker", "D", "E", "K", "period", "break_over_line"]
DEMO_MODULE_SHA = hashlib.sha256(b"# module\n").hexdigest()
DEMO_STATE: dict = {}                                        # {"crash": True} = the body dies mid-write; {"fail": True} = the body's own check fails;
                                                             # {"none": True} = the body returns nothing; {"bad_lines": True} = the verdict txt cannot be written


# ═══ the demo read ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════
def demo_frozen(ctx: rr.Ctx) -> dict:
    d, p = ctx.dirs["cb702"], ctx.dirs["cb702_pre"]
    return {"module": ctx.repo / rn.MODULE_REL, "runner": Path(rn.__file__).resolve(),
            "cb702/daily_closes_all.csv.gz": d / "daily_closes_all.csv.gz", "cb702_pre/daily_closes_all.csv.gz": p / "daily_closes_all.csv.gz",
            "cb702/out/candidates.tsv": d / "out" / "candidates.tsv", "cb702_pre/out/candidates.tsv": p / "out" / "candidates.tsv",
            "cb702/minutes (tree)": d / "minutes", "cb702_pre/minutes (tree)": p / "minutes"}


def demo_where(rec) -> bool:
    return rec["K"] == "tl" and int(rec.get("retrigger") or 0) == 0


def demo_prepare(ctx: rr.Ctx) -> dict:
    path = ctx.out / "candidates.tsv"
    kw = {"era": "pre"} if ctx.period == "pre" else {"split": ctx.period}
    rows = rr.read_candidates_cached(path, rn.read_candidates, extra_floats=("base_depth",), where=demo_where, **kw)
    return {"rows": rows, "inp": rn.minute_inputs(rows, ctx.minutes), "path": path, "opens": (ctx.data / "daily_closes_all.csv.gz",)}


def demo_outputs(ctx: rr.Ctx) -> tuple:
    return (f"trades_{ctx.period}_demo.tsv.gz",)


def demo_dry_run(ctx: rr.Ctx, prep: dict, existing: list) -> str:
    inp = prep["inp"]
    return (f"DEMO DRY RUN (freeze check {ctx.freeze}; counts only): period {ctx.period}: {len(prep['rows'])} rows from {prep['path']}, "
            f"{len(inp['pairs'])} (date, ticker) pairs; pairs NOT logged in _done.psv: {len(inp['missing'])}, logged ok with no file: {len(inp['lost'])}; "
            f"outputs already on disk: {[q.name for q in existing] or 'none'}. Would write {ctx.out / demo_outputs(ctx)[0]} and the verdict files "
            f"under {ctx.out} and {ctx.small}.")


def demo_body(ctx: rr.Ctx, prep: dict, say) -> "rr.Verdict | int | None":
    rows = [[c["ticker"], c["D"], c["E"], c["K"], ctx.period, c["high_E"] - c["pivot"]] for c in prep["rows"]]
    name = demo_outputs(ctx)[0]
    with ctx.partial_write(name) as fh:
        fh.write(rn.rows_to_gz([DEMO_COLS]))
        if DEMO_STATE.get("crash"):
            raise RuntimeError("worker died")
        fh.write(rn.rows_to_gz(rows))
    say(f"WROTE {ctx.out / name} ({len(rows)} rows)")
    if DEMO_STATE.get("fail"):
        say("DEMO CHECK FAILED: the report is NOT written")
        return 3
    if DEMO_STATE.get("none"):
        return None
    mean = sum(r[-1] for r in rows) / len(rows)
    lines = (f"DEMO VERDICT FILE - period {ctx.period} - written {time.strftime('%Y-%m-%d')}", f"n {len(rows)}; mean break over the line {mean:.4f}")
    return rr.Verdict({"period": ctx.period, "n": len(rows), "mean_break": mean}, (object(),) if DEMO_STATE.get("bad_lines") else lines)


def demo_spec(**over) -> rr.RegisteredRead:
    kw = dict(name="demo-read", tag="demo", doc="cb_demo_prereg_2026-10-24.md", frozen=demo_frozen, prepare=demo_prepare, outputs=demo_outputs,
              dry_run=demo_dry_run, body=demo_body, periods=rn.H60_PERIODS,
              hard_pins=(("module", lambda ctx: ctx.repo / rn.MODULE_REL, DEMO_MODULE_SHA),))
    kw.update(over)
    return rr.RegisteredRead(**kw)


def _demo_tree(tmp_path, monkeypatch) -> dict:
    """cb702 (one discovery tl candidate on X) + cb702_pre (one pre-era tl candidate), each with its export, minute file and _done.psv; a
    repo with the stub module and the frozen code; HERE / REPO pointed into the tree."""
    tree = {}
    for key, start, split in (("cb702", T.DISCOVERY_START, "discovery"), ("cb702_pre", T.PRE_START, "pre")):
        d = tmp_path / key
        (d / "out").mkdir(parents=True)
        bars, e = T._e_bars(start=start)
        T._write_export(d, bars)
        c = T._p5_cand(bars, e, K="tl", split=split)
        rn.write_tsv(d / "out" / "candidates.tsv", [c], list(c.keys()))
        md = d / "minutes"
        md.mkdir()
        T.fm._append_gz(md / f"{c['E']}.psv.gz", T._minute_lines("X"))
        (md / "_done.psv").write_text(f"{c['E']}|X|390|ok\n")
        tree[key] = d
        tree[key + "_cand"] = c
    repo = tmp_path / "repo"
    (repo / "docs" / "analysis").mkdir(parents=True)
    (repo / rn.MODULE_REL).parent.mkdir(parents=True, exist_ok=True)
    (repo / rn.MODULE_REL).write_text("# module\n")
    for rel in rn.FROZEN_CODE.values():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(f"# {rel}\n")
    monkeypatch.setattr(rn, "REPO", repo)
    monkeypatch.setattr(rn, "HERE", tmp_path / "hereroot")
    (rn.HERE / "out").mkdir(parents=True)
    DEMO_STATE.clear()
    rr.clear_daily_cache()
    tree["repo"] = repo
    return tree


def _ns(tree, **kw):
    kw.setdefault("period", "discovery")
    return T.argparse_ns(tree["cb702"], data_pre=str(tree["cb702_pre"]), **kw)


def _doc(tree, spec, body="Method / population. What this does not answer. n=1.\n") -> Path:
    """The registration doc with the footer the driver will check: the map the DRIVER uses (the spec's plus the scaffold / the body's module)."""
    doc = tree["repo"] / "docs" / "analysis" / spec.doc
    doc.write_text(body + rn.FREEZE_MARK + "\n## Freeze record\n")
    ctx = rr.resolve(spec, _ns(tree), rn)
    pins = rn.pin_lines(tree["cb702"], tree["repo"], files=rr.frozen_map(spec, ctx)) + [f"- doc body sha256: `{rn.doc_body_sha(doc.read_text())}`"]
    doc.write_text(doc.read_text() + "\n".join(pins) + "\n")
    return doc


def _main(tree, *extra, period="discovery"):
    argv = ["demo-read", "--data", str(tree["cb702"]), "--data-pre", str(tree["cb702_pre"]), "--workers", "1"]
    if period:
        argv += ["--period", period]
    return rn.main(argv + list(extra))


def _run(spec, tree, **kw) -> int:
    return rr.run_registered_read(spec, _ns(tree, **kw), rn)


# ═══ the spec ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
class TestSpec:
    def test_a_spec_validates_its_name_tag_and_order(self):
        assert demo_spec().order == rr.DEFAULT_ORDER and set(rr.DEFAULT_ORDER) == set(rr.CHECKS)
        with pytest.raises(ValueError, match="needs a name"):
            demo_spec(name="")
        with pytest.raises(ValueError, match="unknown or repeated"):
            demo_spec(order=("print_pins", "nope"))
        with pytest.raises(ValueError, match="unknown or repeated"):
            demo_spec(order=rr.DEFAULT_ORDER + ("freeze",))
        with pytest.raises(ValueError, match="frozen / prepare / outputs / body are callables"):
            demo_spec(body=None)

    @pytest.mark.parametrize("dropped", rr.DEFAULT_ORDER)
    def test_every_guard_is_required_dropping_any_one_is_an_error(self, dropped):
        """The review's hole: a spec could leave out dry_run, no_freeze_check, freeze, options or once_only and run quieter. No longer."""
        order = tuple(c for c in rr.DEFAULT_ORDER if c != dropped)
        with pytest.raises(ValueError, match=rf"drops the guard\(s\) \['{dropped}'\]"):
            demo_spec(order=order)
        with pytest.raises(ValueError, match="drops the guard"):                   # a read with no periods still carries the (no-op) period check
            demo_spec(order=order, periods=())

    def test_the_order_keeps_the_drivers_chain(self):
        def swapped(a, b):
            o = list(rr.DEFAULT_ORDER)
            i, j = o.index(a), o.index(b)
            o[i], o[j] = o[j], o[i]
            return tuple(o)
        for a, b in rr.ORDER_RULES:
            with pytest.raises(ValueError, match=f"{a} before {b}"):
                demo_spec(order=swapped(a, b))
        with pytest.raises(ValueError, match="print_pins runs first"):
            demo_spec(order=swapped("print_pins", "period"))
        # the slack the chain leaves is harmless: hard pins before the options, the two population checks before empty's sibling
        assert demo_spec(order=swapped("hard_pins", "prereg")).order[2] == "hard_pins"

    def test_the_context_is_resolved_once_from_the_period(self, tmp_path, monkeypatch):
        tree = _demo_tree(tmp_path, monkeypatch)
        spec = demo_spec()
        c = rr.resolve(spec, _ns(tree), rn)
        assert (c.data, c.out, c.minutes, c.small, c.doc) == (tree["cb702"], tree["cb702"] / "out", tree["cb702"] / "minutes", rn.HERE / "out",
                                                               tree["repo"] / "docs" / "analysis" / spec.doc)
        c = rr.resolve(spec, _ns(tree, period="pre"), rn)
        assert (c.data, c.out, c.minutes) == (tree["cb702_pre"], tree["cb702_pre"] / "out", tree["cb702_pre"] / "minutes")
        c = rr.resolve(spec, _ns(tree, period="pre", out=str(tmp_path / "x"), small_out=str(tmp_path / "y"), minutes=str(tmp_path / "m"), prereg=str(tmp_path / "d.md")), rn)
        assert (c.out, c.small, c.minutes, c.doc) == (tmp_path / "x", tmp_path / "y", tmp_path / "m", tmp_path / "d.md")
        ns = T.argparse_ns(tree["cb702"])                                            # no --data-pre: the sibling; no periods: period None
        c = rr.resolve(demo_spec(periods=()), ns, rn)
        assert c.dirs["cb702_pre"] == tree["cb702"].parent / "cb702_pre" and c.period is None and c.data == tree["cb702"]

    def test_the_driver_pins_the_runner_the_scaffold_and_the_bodys_module(self, tmp_path, monkeypatch):
        tree = _demo_tree(tmp_path, monkeypatch)
        spec = demo_spec()
        files = rr.frozen_map(spec, rr.resolve(spec, _ns(tree), rn))
        assert files["runner"] == Path(rn.__file__).resolve() and files["scaffold"] == Path(rr.__file__).resolve()
        assert files["spec module"] == Path(__file__).resolve()                     # the demo body lives here
        assert set(demo_frozen(rr.resolve(spec, _ns(tree), rn))) < set(files)
        # a spec may carry the driver's labels only at the driver's paths
        bad = demo_spec(frozen=lambda ctx: dict(demo_frozen(ctx), scaffold=ctx.repo / rn.MODULE_REL))
        with pytest.raises(ValueError, match="frozen label 'scaffold' points at"):
            rr.frozen_map(bad, rr.resolve(bad, _ns(tree), rn))
        # a body whose module lives in the runner adds no third label; a body with no source file is refused
        in_runner = demo_spec(body=rn.run_holdout)
        assert "spec module" not in rr.frozen_map(in_runner, rr.resolve(in_runner, _ns(tree), rn))
        import functools
        partial = demo_spec(body=functools.partial(demo_body))
        with pytest.raises(ValueError, match="source file cannot be determined"):
            rr.frozen_map(partial, rr.resolve(partial, _ns(tree), rn))
        # a doc with an empty map is refused; doc=None is the declared way
        empty = demo_spec(frozen=lambda ctx: {})
        with pytest.raises(ValueError, match="frozen\\(ctx\\) is empty"):
            rr.frozen_map(empty, rr.resolve(empty, _ns(tree), rn))
        declared = demo_spec(frozen=lambda ctx: {}, doc=None, hard_pins=())
        assert set(rr.frozen_map(declared, rr.resolve(declared, _ns(tree), rn))) == {"runner", "scaffold", "spec module"}


# ═══ the driver ══════════════════════════════════════════════════════════════════════════════════════════════════════════════════
class TestDriver:
    def test_main_dispatches_the_registry_and_print_pins_carries_the_map_and_the_doc_body(self, tmp_path, monkeypatch, capsys):
        tree = _demo_tree(tmp_path, monkeypatch)
        spec = demo_spec()
        with pytest.raises(SystemExit):                                              # not registered: argparse refuses the stage
            _main(tree, "--print-pins")
        assert "invalid choice: 'demo-read'" in capsys.readouterr().err
        monkeypatch.setitem(rn.REGISTERED_READS, spec.name, spec)
        assert _main(tree, "--print-pins", period=None) is None                      # before the period check
        pins = capsys.readouterr().out
        for label in list(demo_frozen(rr.resolve(spec, _ns(tree), rn))) + ["scaffold", "spec module"]:
            assert f"- {label} sha256: `" in pins, label
        assert "- doc body sha256: `MISSING`" in pins and "MISSING`" in pins.splitlines()[-1]
        _doc(tree, spec)
        _main(tree, "--print-pins", period=None)
        assert "MISSING" not in capsys.readouterr().out
        # the --period choices grow with a registered read's own periods, in the registered order
        other = demo_spec(name="era-read", tag="era", periods=("discovery", "era-x"))
        monkeypatch.setitem(rn.REGISTERED_READS, other.name, other)
        assert rn.main(["era-read", "--data", str(tree["cb702"]), "--period", "era-x", "--dry-run", "--no-freeze-check"]) is None
        assert "period era-x: 0 rows" in capsys.readouterr().out                    # past argparse, into the read's own checks
        with pytest.raises(SystemExit):
            rn.main(["h60-read", "--data", str(tree["cb702"]), "--period", "era-y"])
        assert "invalid choice: 'era-y'" in capsys.readouterr().err

    def test_a_read_named_after_a_built_in_stage_is_refused_before_any_dispatch(self, tmp_path, monkeypatch, capsys):
        """`main()` dispatches the registry before the built-in branches: a spec called `h60-read` would silently replace the finished read."""
        tree = _demo_tree(tmp_path, monkeypatch)
        assert set(rn.BUILTIN_STAGES) == {"daily", "minute", "step0-entries", "holdout", "report", "exits", "exits-report", "p5", "pre-read",
                                          "h60-step0", "h60-read", "h60-hindsight", "exit-read", "aplus-profile", "aplus-verdict"}
        monkeypatch.setitem(rn.REGISTERED_READS, "h60-read", demo_spec(name="h60-read"))
        for argv in (["h60-read", "--data", str(tree["cb702"]), "--period", "discovery", "--print-pins"], ["daily", "--data", str(tree["cb702"])]):
            with pytest.raises(SystemExit) as ex:
                rn.main(argv)
            assert ex.value.code == 2 and "registered read(s) ['h60-read'] carry the name of a built-in stage" in capsys.readouterr().err

    def test_the_freeze_runs_before_any_file_is_opened_and_every_edit_refuses(self, tmp_path, monkeypatch, capsys):
        tree = _demo_tree(tmp_path, monkeypatch)
        spec = demo_spec()
        monkeypatch.setitem(rn.REGISTERED_READS, spec.name, spec)
        with pytest.raises(SystemExit) as ex:                                        # no doc yet
            _main(tree)
        assert ex.value.code == 2 and "registration doc missing" in capsys.readouterr().err
        doc = _doc(tree, spec)
        assert _main(tree, "--dry-run") is None and "DEMO DRY RUN (freeze check passed" in capsys.readouterr().out
        armed = dataclasses.replace(spec, prepare=T._disarm(monkeypatch, (), "x"))   # a prepare that must not be reached
        monkeypatch.setitem(rn.REGISTERED_READS, spec.name, armed)
        T._disarm(monkeypatch, ("load_daily", "read_candidates", "minute_inputs"), "the read was opened before the freeze check")
        p = tree["cb702"] / "out" / "candidates.tsv"
        before = p.read_bytes()
        p.write_bytes(before + b"\n")
        with pytest.raises(SystemExit) as ex:
            _main(tree)
        err = capsys.readouterr().err
        assert ex.value.code == 2 and "freeze check failed" in err and "cb702/out/candidates.tsv sha256 mismatch" in err
        p.write_bytes(before)
        (tree["cb702_pre"] / "minutes" / "2099-01-01.psv.gz").write_bytes(b"new")   # the OTHER period's tree is pinned too
        with pytest.raises(SystemExit):
            _main(tree)
        assert "cb702_pre/minutes (tree) sha256 mismatch" in capsys.readouterr().err
        (tree["cb702_pre"] / "minutes" / "2099-01-01.psv.gz").unlink()
        doc.write_text(doc.read_text().replace("n=1", "n=2"))
        with pytest.raises(SystemExit):
            _main(tree)
        assert "doc body sha256 mismatch" in capsys.readouterr().err
        with pytest.raises(SystemExit) as ex:                                        # --prereg on a real run
            _main(tree, "--prereg", str(doc))
        assert ex.value.code == 2 and "--prereg is honoured only with --print-pins or --dry-run" in capsys.readouterr().err
        with pytest.raises(SystemExit) as ex:                                        # the skip flag needs --dry-run
            _main(tree, "--no-freeze-check")
        assert ex.value.code == 2 and "only together with --dry-run" in capsys.readouterr().err
        assert not list((tree["cb702"] / "out").glob("*demo*")) and not list((rn.HERE / "out").iterdir())

    def test_an_edit_of_the_scaffold_or_of_the_bodys_module_refuses(self, tmp_path, monkeypatch, capsys):
        """The guard code is pinned by the driver itself: a copy of registered_read.py edited after the freeze commit is a mismatch."""
        tree = _demo_tree(tmp_path, monkeypatch)
        copy = tmp_path / "registered_read_copy.py"
        shutil.copy(rr.__file__, copy)
        monkeypatch.setattr(rr, "SCAFFOLD_PATH", copy)
        spec = demo_spec()
        _doc(tree, spec)
        assert _run(spec, tree, dry_run=True) == 0 and "freeze check passed" in capsys.readouterr().out
        T._disarm(monkeypatch, ("load_daily",), "the read was opened")
        copy.write_bytes(copy.read_bytes() + b"\n# edited\n")
        assert _run(spec, tree) == 2
        err = capsys.readouterr().err
        assert "freeze check failed" in err and "scaffold sha256 mismatch" in err and "the frozen artefact was edited" in err
        assert _run(spec, tree, dry_run=True) == 2 and "scaffold sha256 mismatch" in capsys.readouterr().err
        # the body's module: the doc pinned a different file under `spec module`
        copy.write_bytes(copy.read_bytes()[:-len(b"\n# edited\n")])
        assert _run(spec, tree, dry_run=True) == 0
        capsys.readouterr()
        body_copy = tmp_path / "demo_body_copy.py"
        body_copy.write_text("def body(ctx, prep, say):\n    return 3\n")
        ns = {}
        exec(compile(body_copy.read_text(), str(body_copy), "exec"), {"__file__": str(body_copy)}, ns)   # a body whose source is another file
        import types
        mod = types.ModuleType("demo_body_copy")
        mod.__file__ = str(body_copy)
        fn = ns["body"]
        fn.__module__ = mod.__name__
        import sys
        monkeypatch.setitem(sys.modules, mod.__name__, mod)
        elsewhere = demo_spec(body=fn)
        files = rr.frozen_map(elsewhere, rr.resolve(elsewhere, _ns(tree), rn))
        assert files["spec module"] == body_copy.resolve()
        assert _run(elsewhere, tree) == 2 and "spec module sha256 mismatch" in capsys.readouterr().err

    def test_a_freeze_map_that_does_not_cover_what_the_read_opens_refuses(self, tmp_path, monkeypatch, capsys):
        """The pre-read's hole: a freeze that passes because it pins nothing the read opens. The minute tree, the candidates file and what the
        body declares it opens must each be a pinned file or lie inside a pinned directory."""
        tree = _demo_tree(tmp_path, monkeypatch)
        thin = demo_spec(frozen=lambda ctx: {"module": ctx.repo / rn.MODULE_REL, "runner": Path(rn.__file__).resolve(),
                                             "cb702/out/candidates.tsv": ctx.dirs["cb702"] / "out" / "candidates.tsv",
                                             "cb702/daily_closes_all.csv.gz": ctx.dirs["cb702"] / "daily_closes_all.csv.gz"})
        _doc(tree, thin)
        T._disarm(monkeypatch, ("load_daily",), "the read was opened")
        for kw in ({}, {"dry_run": True}):
            assert _run(thin, tree, **kw) == 2, kw
            err = capsys.readouterr().err
            assert err.startswith("REFUSED: the freeze map of the demo-read does not cover the minute directory ") and str(tree["cb702"] / "minutes") in err
        # the pin covers the tree: an edit after the freeze is caught where it was not before (probe (d) of the review)
        full = demo_spec(frozen=lambda ctx: dict(thin.frozen(ctx), **{"cb702/minutes (tree)": ctx.dirs["cb702"] / "minutes"}))
        _doc(tree, full)
        assert _run(full, tree, dry_run=True) == 0
        capsys.readouterr()
        (tree["cb702"] / "minutes" / "_done.psv").write_text("2099-01-01|OTHER|390|ok\n")
        assert _run(full, tree) == 2 and "cb702/minutes (tree) sha256 mismatch" in capsys.readouterr().err
        # a candidates file read from a dir the map does not pin; an input the body opens that is not pinned
        no_cands = demo_spec(frozen=lambda ctx: {k: v for k, v in full.frozen(ctx).items() if k != "cb702/out/candidates.tsv"})
        _doc(tree, no_cands)
        assert _run(no_cands, tree, dry_run=True) == 2 and "does not cover the candidates file" in capsys.readouterr().err
        no_export = demo_spec(frozen=lambda ctx: {k: v for k, v in full.frozen(ctx).items() if k != "cb702/daily_closes_all.csv.gz"})
        _doc(tree, no_export)
        assert _run(no_export, tree, dry_run=True) == 2 and "does not cover an input the body opens," in capsys.readouterr().err
        declared = demo_spec(doc=None, hard_pins=(), frozen=thin.frozen)              # a declared no-freeze read has no map to cover anything
        assert _run(declared, tree, dry_run=True) == 0

    def test_out_is_checked_against_the_dir_the_period_reads_and_the_body_writes_there(self, tmp_path, monkeypatch, capsys):
        """The h60 hole: `--out cb702/out` passed the check and the pre period read cb702_pre/out. The exit-read hole: `--out` ignored."""
        tree = _demo_tree(tmp_path, monkeypatch)
        spec = demo_spec()
        _doc(tree, spec)
        pre_out, disc_out = tree["cb702_pre"] / "out", tree["cb702"] / "out"
        assert _run(spec, tree, period="pre", out=str(disc_out), dry_run=True) == 2
        err = capsys.readouterr().err
        assert f"--out {disc_out} is not {pre_out} (the dir the period 'pre' reads)" in err
        assert _run(spec, tree, period="pre", out=str(pre_out), dry_run=True) == 0 and "period pre: 1 rows" in capsys.readouterr().out
        assert _run(spec, tree, period="discovery", out=str(disc_out), dry_run=True) == 0
        assert _run(spec, tree, period="discovery", out=str(tmp_path / "elsewhere"), dry_run=True) == 2
        assert "--out" in capsys.readouterr().err
        assert _run(spec, tree, period="pre", out=str(pre_out)) == 0                 # the real pre run, --out spelled out
        assert (pre_out / "trades_pre_demo.tsv.gz").exists() and (pre_out / "demo_verdict_pre.json").exists()
        assert not list(disc_out.glob("*demo*"))                                     # nothing of the pre period landed in cb702/out

    def test_minutes_is_checked_against_the_periods_tree_whatever_the_spec_refuses(self, tmp_path, monkeypatch, capsys):
        tree = _demo_tree(tmp_path, monkeypatch)
        spec = demo_spec(refused=tuple(d for d in rr.REFUSED_DEFAULT if d != "minutes"))          # a spec that forgot --minutes
        _doc(tree, spec)
        assert _run(spec, tree, period="pre", minutes=str(tree["cb702"] / "minutes"), dry_run=True) == 2
        err = capsys.readouterr().err
        assert f"--minutes {tree['cb702'] / 'minutes'} is not {tree['cb702_pre'] / 'minutes'} (the minute tree the period 'pre' reads" in err
        assert _run(spec, tree, period="pre", minutes=str(tree["cb702_pre"] / "minutes"), dry_run=True) == 0   # the period's own tree, spelled out
        assert _run(demo_spec(), tree, period="pre", minutes=str(tree["cb702_pre"] / "minutes"), dry_run=True) == 2   # the default spec refuses any

    def test_option_refusals_print_the_specs_own_words(self, tmp_path, monkeypatch, capsys):
        tree = _demo_tree(tmp_path, monkeypatch)
        m = rr.Messages(options="NOPE: the {name} is one shape only:", refused_option="{option} -> not on the {name}",
                        small_out_elsewhere="small {small_out} must be {expected}", period="NOPE: pick a period from {periods}",
                        no_freeze_check="NOPE: the skip flag is for dry runs")
        spec = demo_spec(messages=m)
        _doc(tree, spec)
        for kw, needle in (({"keys": "com"}, "--keys com -> not on the demo-read"), ({"levels": "tl"}, "--levels tl -> not on the demo-read"),
                           ({"limit_dates": 2}, "--limit-dates 2 -> not"), ({"no_close": True}, "--no-close -> not on the demo-read"),
                           ({"no_apollo": True}, "--no-apollo -> not"), ({"trades": "t"}, "--trades t -> not"),
                           ({"minutes": str(tree["cb702"] / "minutes")}, "--minutes"), ({"small_out": str(tmp_path / "s")}, f"small {tmp_path / 's'} must be {rn.HERE / 'out'}")):
            assert _run(spec, tree, dry_run=True, **kw) == 2, kw
            err = capsys.readouterr().err
            assert err.startswith("NOPE: the demo-read is one shape only:\n  - ") and needle in err, (kw, err)
        assert _run(spec, tree, period=None) == 2 and capsys.readouterr().err.startswith("NOPE: pick a period from ('discovery', 'pre', 'holdout')")
        assert _run(spec, tree, period="2020") == 2 and "NOPE: pick a period" in capsys.readouterr().err
        assert _run(spec, tree, no_freeze_check=True) == 2 and capsys.readouterr().err.strip() == "NOPE: the skip flag is for dry runs"
        assert _run(spec, tree, dry_run=True, no_freeze_check=True) == 0 and "freeze check SKIPPED" in capsys.readouterr().out
        assert rr.option_problems(spec, rr.resolve(spec, _ns(tree, out=str(tree["cb702"] / "out"), small_out=str(rn.HERE / "out")), rn)) == []
        # belt and braces: the freeze check itself refuses the skip flag without --dry-run, and the driver refuses a body the freeze never reached
        ctx = rr.resolve(spec, _ns(tree, no_freeze_check=True), rn)
        assert rr._check_freeze(spec, ctx, {}) == 2 and capsys.readouterr().err.strip() == "NOPE: the skip flag is for dry runs"
        monkeypatch.setitem(rr.CHECKS, "freeze", lambda spec, ctx, state: None)       # a freeze check that forgot to run
        assert _run(spec, tree) == 2 and capsys.readouterr().err.startswith("REFUSED: the freeze check did not pass before the body (not run)")
        assert not list((tree["cb702"] / "out").glob("*demo*"))

    def test_hard_pins_refuse_footer_or_no_footer_even_a_dry_run(self, tmp_path, monkeypatch, capsys):
        tree = _demo_tree(tmp_path, monkeypatch)
        spec = demo_spec()
        assert rr.hard_pin_problem(spec, rr.resolve(spec, _ns(tree), rn)) is None
        bad = demo_spec(hard_pins=(("module", lambda ctx: ctx.repo / rn.MODULE_REL, "0" * 64),))
        assert _run(bad, tree, dry_run=True, no_freeze_check=True) == 2
        err = capsys.readouterr().err
        assert err.startswith("REFUSED: module sha256 ") and "is not the registered 000000000000... - consolidation_breakout.py was edited" in err
        (tree["repo"] / rn.MODULE_REL).unlink()
        assert _run(spec, tree, dry_run=True, no_freeze_check=True) == 2 and "REFUSED: module missing:" in capsys.readouterr().err

    def test_dry_run_counts_only_opens_no_bar_and_writes_nothing(self, tmp_path, monkeypatch, capsys):
        tree = _demo_tree(tmp_path, monkeypatch)
        spec = demo_spec()
        _doc(tree, spec)
        T._disarm(monkeypatch, ("load_daily", "read_minute_file"), "the dry run opened a bar")
        before = sorted(p.as_posix() for p in tmp_path.rglob("*"))
        assert _run(spec, tree, dry_run=True) == 0
        out = capsys.readouterr().out
        assert "DEMO DRY RUN (freeze check passed; counts only): period discovery: 1 rows from" in out
        assert "1 (date, ticker) pairs; pairs NOT logged in _done.psv: 0, logged ok with no file: 0; outputs already on disk: none" in out
        assert sorted(p.as_posix() for p in tmp_path.rglob("*")) == before
        (tree["cb702"] / "out" / "trades_discovery_demo.tsv.gz").write_bytes(b"x")
        assert _run(spec, tree, dry_run=True, no_freeze_check=True) == 0
        assert "outputs already on disk: ['trades_discovery_demo.tsv.gz']" in capsys.readouterr().out

    def test_the_run_the_verdict_files_once_only_and_the_partial(self, tmp_path, monkeypatch, capsys):
        tree = _demo_tree(tmp_path, monkeypatch)
        spec = demo_spec()
        monkeypatch.setitem(rn.REGISTERED_READS, spec.name, spec)
        _doc(tree, spec)
        out, small = tree["cb702"] / "out", rn.HERE / "out"
        assert _main(tree) is None
        o = capsys.readouterr().out
        assert o.startswith("DEMO-READ (registered read #705): period discovery; 1 rows; 1 pairs all logged; freeze check passed; code: module sha256 ")
        assert f", scaffold sha256 {rr.sha256_file(rr.__file__)}" in o.splitlines()[0]
        assert "WROTE " in o and "demo_verdict_discovery.json" in o and "WALL TIME:" in o
        t = T.pd_read(out / "trades_discovery_demo.tsv.gz")
        assert list(t.columns) == DEMO_COLS and len(t) == 1 and t.break_over_line.iloc[0] == pytest.approx(10.60 - 10.25)
        vj = json.loads((out / "demo_verdict_discovery.json").read_text())
        assert vj == {"period": "discovery", "n": 1, "mean_break": pytest.approx(0.35)}
        vt = (out / "demo_verdict_discovery.txt").read_text()
        assert vt.startswith("DEMO VERDICT FILE - period discovery - written ") and "mean break over the line 0.3500" in vt
        assert (small / "demo_verdict_discovery.txt").read_text() == vt
        summary = (small / "demo_summary_discovery.txt").read_text()
        assert summary.startswith("DEMO-READ (registered read #705)") and "WALL TIME" in summary
        assert not list(out.glob("*.partial")) and not list(small.glob("*.partial"))
        with pytest.raises(SystemExit) as ex:                                        # read once
            _main(tree)
        assert ex.value.code == 2 and "demo-read's outcomes are read ONCE per period and" in capsys.readouterr().err
        assert _main(tree, period="pre") is None                                     # another period is another once
        assert (tree["cb702_pre"] / "out" / "demo_verdict_pre.txt").exists()
        capsys.readouterr()
        # the verdict files are in the once-only set: the table gone, a verdict left behind (out, then small alone) still refuses
        (out / "trades_discovery_demo.tsv.gz").unlink()
        with pytest.raises(SystemExit) as ex:
            _main(tree)
        assert ex.value.code == 2 and f"read ONCE per period and {out / 'demo_verdict_discovery.json'} already exists" in capsys.readouterr().err
        (out / "demo_verdict_discovery.json").unlink()
        (out / "demo_verdict_discovery.txt").unlink()
        with pytest.raises(SystemExit) as ex:
            _main(tree)
        assert ex.value.code == 2 and f"and {small / 'demo_verdict_discovery.txt'} already exists" in capsys.readouterr().err
        (small / "demo_verdict_discovery.txt").unlink()
        (out / "trades_discovery_demo.tsv.gz.partial").write_bytes(b"half")
        with pytest.raises(SystemExit) as ex:
            _main(tree)
        err = capsys.readouterr().err
        assert ex.value.code == 2 and "is what a CRASHED demo-read left behind" in err and "removes it by hand" in err
        (out / "trades_discovery_demo.tsv.gz.partial").unlink()
        DEMO_STATE["crash"] = True                                                   # the body dies mid-write: the .partial stays, no final table
        with pytest.raises(RuntimeError, match="worker died"):
            _main(tree)
        assert (out / "trades_discovery_demo.tsv.gz.partial").exists() and not (out / "trades_discovery_demo.tsv.gz").exists()
        assert not (out / "demo_verdict_discovery.json").exists() and (small / "demo_summary_discovery.txt").exists()
        DEMO_STATE.clear()
        with pytest.raises(SystemExit) as ex:
            _main(tree)
        assert ex.value.code == 2 and "CRASHED demo-read" in capsys.readouterr().err
        (out / "trades_discovery_demo.tsv.gz.partial").unlink()
        # a crash while the verdict is written leaves the verdict's .partial, which refuses too (the .partial protocol covers the verdict files)
        DEMO_STATE["bad_lines"] = True
        with pytest.raises(TypeError):
            _main(tree)
        assert (out / "demo_verdict_discovery.json").exists() and (out / "demo_verdict_discovery.txt.partial").exists() and not (out / "demo_verdict_discovery.txt").exists()
        DEMO_STATE.clear()
        with pytest.raises(SystemExit) as ex:
            _main(tree)
        assert ex.value.code == 2 and f"{out / 'demo_verdict_discovery.txt.partial'} is what a CRASHED demo-read left behind" in capsys.readouterr().err

    def test_a_body_returning_3_writes_the_summary_and_no_verdict(self, tmp_path, monkeypatch, capsys):
        tree = _demo_tree(tmp_path, monkeypatch)
        spec = demo_spec()
        _doc(tree, spec)
        DEMO_STATE["fail"] = True
        assert _run(spec, tree) == 3
        out, small = tree["cb702"] / "out", rn.HERE / "out"
        assert (out / "trades_discovery_demo.tsv.gz").exists() and not list(out.glob("demo_verdict_*")) and not list(small.glob("demo_verdict_*"))
        assert "DEMO CHECK FAILED" in (small / "demo_summary_discovery.txt").read_text()
        DEMO_STATE.clear()

    def test_a_body_returning_nothing_is_a_logged_defect_exit_3(self, tmp_path, monkeypatch, capsys):
        tree = _demo_tree(tmp_path, monkeypatch)
        spec = demo_spec()
        _doc(tree, spec)
        DEMO_STATE["none"] = True
        assert _run(spec, tree) == 3
        out, small = tree["cb702"] / "out", rn.HERE / "out"
        o = capsys.readouterr().out
        assert "BODY RETURNED NOTHING: the demo-read returns a Verdict or an exit code - no verdict is written" in o
        assert (out / "trades_discovery_demo.tsv.gz").exists() and not list(out.glob("demo_verdict_*"))
        assert "BODY RETURNED NOTHING" in (small / "demo_summary_discovery.txt").read_text()
        DEMO_STATE.clear()

    def test_prepare_must_name_its_keys_and_outputs_may_not_be_empty(self, tmp_path, monkeypatch, capsys):
        """A prepare that returns its minute inputs under another name would silently disable the missing-pairs guard; a read with no
        once-only table would have nothing to read once."""
        tree = _demo_tree(tmp_path, monkeypatch)
        renamed = demo_spec(prepare=lambda ctx: {k if k != "inp" else "inputs": v for k, v in demo_prepare(ctx).items()})
        _doc(tree, renamed)
        (tree["cb702"] / "minutes" / "_done.psv").write_text("2099-01-01|OTHER|390|ok\n")
        _doc(tree, renamed)
        with pytest.raises(ValueError, match="prepare must return 'inp'"):
            _run(renamed, tree)
        no_rows = demo_spec(prepare=lambda ctx: {k: v for k, v in demo_prepare(ctx).items() if k != "rows"})
        with pytest.raises(ValueError, match="prepare must return 'rows'"):
            _run(no_rows, tree, dry_run=True, no_freeze_check=True)
        none = demo_spec(outputs=lambda ctx: ())
        with pytest.raises(ValueError, match=r"outputs\(ctx\) is empty"):
            _run(none, tree, dry_run=True, no_freeze_check=True)
        assert not list((tree["cb702"] / "out").glob("*demo*"))

    def test_missing_pairs_and_an_empty_population_refuse(self, tmp_path, monkeypatch, capsys):
        tree = _demo_tree(tmp_path, monkeypatch)
        spec = demo_spec()
        _doc(tree, spec)
        assert _run(spec, tree, period="holdout") == 2                               # cb702 holds discovery rows only
        assert capsys.readouterr().err.strip() == f"REFUSED: no row of holdout in {tree['cb702'] / 'out'}"
        done = tree["cb702"] / "minutes" / "_done.psv"
        done.write_text("2099-01-01|OTHER|390|ok\n")
        assert _run(spec, tree, dry_run=True, no_freeze_check=True) == 0 and "pairs NOT logged in _done.psv: 1" in capsys.readouterr().out
        T._disarm(monkeypatch, ("load_daily",), "opened")
        assert _run(spec, tree, no_freeze_check=False) == 2                          # the minute tree changed: the freeze refuses first
        assert "cb702/minutes (tree) sha256 mismatch" in capsys.readouterr().err
        _doc(tree, spec)                                                             # re-pinned: the missing pair is the next refusal
        assert _run(spec, tree) == 2
        err = capsys.readouterr().err
        assert err.startswith(f"REFUSED: 1 of 1 (date, ticker) pairs are not logged in {done}. A partial read is never run")
        c = tree["cb702_cand"]
        done.write_text(f"{c['E']}|X|390|ok\n")
        (tree["cb702"] / "minutes" / f"{c['E']}.psv.gz").unlink()                    # logged ok, no file: lost
        _doc(tree, spec)
        assert _run(spec, tree) == 2 and "; 1 more are logged ok on a date that has no minute file" in capsys.readouterr().err

    def test_a_read_declaring_no_freeze_says_so_everywhere(self, tmp_path, monkeypatch, capsys):
        tree = _demo_tree(tmp_path, monkeypatch)
        spec = demo_spec(doc=None, hard_pins=())
        assert _run(spec, tree, print_pins=True) == 0
        pins = capsys.readouterr().out
        assert "- module sha256: `" in pins and "- scaffold sha256: `" in pins and "doc body" not in pins
        assert _run(spec, tree, dry_run=True) == 0 and "DEMO DRY RUN (freeze check NONE DECLARED" in capsys.readouterr().out
        assert _run(spec, tree, prereg=str(tmp_path / "d.md"), dry_run=True) == 2 and "this read declares no freeze" in capsys.readouterr().err
        assert _run(spec, tree, no_freeze_check=True) == 2                           # still only with --dry-run
        capsys.readouterr()
        assert _run(spec, tree) == 0
        head = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("DEMO-READ (registered read #705)")]
        assert len(head) == 1 and "freeze check NONE DECLARED" in head[0]

    def test_only_the_aplus_reads_are_registered_in_the_shipped_runner(self):
        """#705 (b): the three A+ reads are the first registered reads; nothing else rides the registry."""
        assert set(rn.REGISTERED_READS) == {"aplus-read", "aplus-confirm", "aplus-hindsight"}
        assert all(isinstance(s, rr.RegisteredRead) and s.name == k for k, s in rn.REGISTERED_READS.items())


# ═══ the speed / memory helpers ══════════════════════════════════════════════════════════════════════════════════════════════════
class TestHelpers:
    def test_sha256_file_streams_the_identical_digest(self, tmp_path):
        p = tmp_path / "big.bin"
        p.write_bytes(np.random.default_rng(5).bytes(3_000_001))
        assert rr.sha256_file(p) == hashlib.sha256(p.read_bytes()).hexdigest() == rn.sha256_file(p)
        (tmp_path / "empty").write_bytes(b"")
        assert rr.sha256_file(tmp_path / "empty") == hashlib.sha256(b"").hexdigest()

    def test_load_daily_cached_is_one_slot_keyed_by_path_size_and_mtime(self, tmp_path):
        rr.clear_daily_cache()
        loads = []

        def loader(p):
            loads.append(Path(p).name)
            return {"export": Path(p).name, "n": len(loads)}
        a, b = tmp_path / "a.csv.gz", tmp_path / "b.csv.gz"
        a.write_bytes(b"aaa")
        b.write_bytes(b"bbb")
        first = rr.load_daily_cached(a, loader)
        assert rr.load_daily_cached(a, loader) is first and loads == ["a.csv.gz"]      # a hit: no second load
        assert rr.load_daily_cached(tmp_path / ".." / tmp_path.name / "a.csv.gz", loader) is first   # the same file by another spelling
        rr.load_daily_cached(b, loader)
        assert loads == ["a.csv.gz", "b.csv.gz"]
        assert rr.load_daily_cached(a, loader)["n"] == 3                               # one slot: a was evicted by b
        a.write_bytes(b"aaaa")                                                         # a changed (size): reloaded
        assert rr.load_daily_cached(a, loader)["n"] == 4
        rr.clear_daily_cache()
        assert rr.load_daily_cached(a, loader)["n"] == 5

    def test_read_candidates_cached_equals_read_candidates_and_hits_on_the_same_keywords(self, tmp_path, capsys):
        rr.clear_daily_cache()
        bars, e = T._e_bars(start=T.DISCOVERY_START)
        cands = [T._p5_cand(bars, e, K=k) for k in ("tl", "com")] + [T._p5_cand(bars, e, K="tl", retrigger=1)]
        p = tmp_path / "candidates.tsv"
        rn.write_tsv(p, cands, list(cands[0].keys()))
        calls = []

        def reader(path, **kw):
            calls.append(kw)
            return rn.read_candidates(path, **kw)
        kw = dict(split="discovery", extra_floats=("base_depth",), where=demo_where)
        want = rn.read_candidates(p, **kw)
        got = rr.read_candidates_cached(p, reader, **kw)
        assert got == want and len(got) == 1 and got[0]["K"] == "tl"
        again = rr.read_candidates_cached(p, reader, **kw)
        assert again == want and again is not got and again[0] is got[0] and len(calls) == 1     # a hit: a new list over the same rows
        assert "candidates: candidates.tsv unchanged since the last parse" in capsys.readouterr().out
        got.append("x")                                                                          # the caller's list is its own
        assert len(rr.read_candidates_cached(p, reader, **kw)) == 1 and len(calls) == 1
        assert len(rr.read_candidates_cached(p, reader, split="discovery", extra_floats=("base_depth",), where=lambda r: r["K"] == "com")) == 1
        assert len(calls) == 2                                                                   # another `where`: a miss (identity)
        assert rr.read_candidates_cached(p, reader, **kw) == want and len(calls) == 3           # one slot: evicted
        p.write_text(p.read_text() + "")
        import os
        os.utime(p, ns=(p.stat().st_atime_ns, p.stat().st_mtime_ns + 1_000_000))              # the file touched: re-read
        assert rr.read_candidates_cached(p, reader, **kw) == want and len(calls) == 4
        rr.clear_daily_cache()

    def test_read_watch_index_equals_h60_watch_index_on_a_synthetic_table(self, tmp_path):
        rng = np.random.default_rng(702)
        n = 2_000
        rows = []
        for j in range(n):
            t = f"T{j % 37}"
            pole = f"2024-0{1 + j % 9}-{1 + j % 28:02d}"
            rows.append({"ticker": t, "watch_date": f"2024-{1 + j % 12:02d}-{1 + j % 28:02d}", "ci": j, "i": j + 130, "pole_date": pole,
                         "pole_high": float(rng.uniform(1, 500)), "base_low": float(rng.uniform(1, 500)),
                         "pivot_tl": None if j % 7 == 0 else float(rng.uniform(1, 500)), "tl_slope_pct": None if j % 7 == 0 else float(rng.normal(0, 0.01)),
                         "tl_anchor_idx": None if j % 7 == 0 else j - 20, "pivot_com": None if j % 5 == 0 else float(rng.uniform(1, 500)),
                         "noise": "x" * (j % 3)})
        cols = list(rows[0])
        p = tmp_path / "watch.tsv.gz"
        rn.write_tsv(p, rows, cols, gz=True)
        for k in ("tl", "com"):
            want = rn.h60_watch_index(p, k)
            got = rr.read_watch_index(p, k, chunksize=300)                             # chunk boundaries inside the table
            assert got["row"] == want["row"] and dict(got["nights"]) == dict(want["nights"]) and dict(got["noline"]) == dict(want["noline"])
            assert len(got["row"]) == n and any(v["pivot"] is None for v in got["row"].values())
            if k == "tl":
                assert all(isinstance(v["anchor"], int) for v in got["row"].values() if v["anchor"] is not None)
            else:
                assert all(v["slope"] is None and v["anchor"] is None for v in got["row"].values())
