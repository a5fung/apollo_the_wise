"""Every judge lane must NAME the `api_usage` bucket it spends into (operator 2026-08-02).

*"this chart grading was 85% of spend but it was not noticed until i asked about a telegram msg
which technically shouldn't have been sent anymore, that is very concerning. We can have hidden
costs that provides no value that is running and no way for us to know about in time."*

**The cost stack was not the failure.** The #377 meter logs every call; #378 gives a /cost board and
a daily spend alarm; #379 adds per-caller anomaly detection and reduction opportunities. All of it
worked. It was reading a bucket with two different things in it: `grade_holistic`'s `log_caller`
had a DEFAULT of `"ep_grade_judge"`, the chart-vision shadow took the default, and 336 experimental
calls (of 379 in that bucket over 30 days, $12.90) became indistinguishable from live grading. The
dollar figure was always derivable; the ATTRIBUTION was not — that is the precise defect.

`judge_divergence` had overridden the default correctly and the docstring explained why. Convention
was there, documented, and the next lane still didn't follow it. So it is a required argument now,
and these tests are the part that survives the next lane.
"""
import ast
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]

# The judge entry points whose spend lands in api_usage. Every call to one of these must say
# which lane is paying.
_JUDGE_CALLS = {"grade_holistic", "grade_one", "grade_b_c"}

# Only the LIVE 9:45 grade path may bill the production judge bucket.
_LIVE_LABEL = "ep_grade_judge"
_LIVE_PATH = "agents/market_intelligence/ep_detector.py"

_SCAN_DIRS = ("agents", "core", "channels", "shared", "scripts")


def _call_sites():
    """(relpath, lineno, funcname, ast.Call) for every judge call in product + script code."""
    for d in _SCAN_DIRS:
        for path in sorted((_ROOT / d).rglob("*.py")):
            rel = path.relative_to(_ROOT).as_posix()
            try:
                tree = ast.parse(path.read_text())
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = (node.func.id if isinstance(node.func, ast.Name)
                      else node.func.attr if isinstance(node.func, ast.Attribute) else None)
                if fn in _JUDGE_CALLS:
                    yield rel, node.lineno, fn, node


def _log_caller_of(call: ast.Call, fn: str):
    """The label this call site passes, as a literal — or a marker for why it can't be read."""
    for kw in call.keywords:
        if kw.arg == "log_caller":
            if isinstance(kw.value, ast.Constant):
                return kw.value.value
            # `log_caller=log_caller` inside grade_one/grade_b_c is those functions threading
            # their OWN required argument onward — the naming already happened at the real call
            # site, which this scan checks separately.
            if isinstance(kw.value, ast.Name) and kw.value.id == "log_caller":
                return "<FORWARDED>"
            return "<NOT-A-LITERAL>"
    # grade_one / grade_b_c take it positionally as the last argument.
    if fn in ("grade_one", "grade_b_c") and call.args:
        last = call.args[-1]
        if isinstance(last, ast.Constant) and isinstance(last.value, str):
            return last.value
        if isinstance(last, ast.Name) and last.id == "log_caller":
            return "<FORWARDED>"          # grade_b_c threading its own required arg through
    return None


def test_there_are_judge_call_sites_to_check():
    """Guard the guard: an empty scan would make every assertion below vacuously true."""
    sites = list(_call_sites())
    assert len(sites) >= 6, f"only found {len(sites)} judge call sites — the scan is broken"


def test_every_judge_call_site_names_its_spend_bucket():
    """The whole fix. A lane that does not name itself is a lane whose cost cannot be seen."""
    missing = [f"{rel}:{ln} {fn}()" for rel, ln, fn, call in _call_sites()
               if _log_caller_of(call, fn) is None
               # the definitions' own internal forwarding is not a call site
               and not (rel.endswith("chart_axis.py") and fn == "grade_holistic")]
    assert not missing, (
        "judge call site(s) with no log_caller — their spend merges into another lane's bucket "
        f"and becomes invisible: {missing}")


def test_only_the_LIVE_grade_path_bills_the_production_bucket():
    """The exact 8/02 defect: an experiment inheriting the live label. A shadow, an eval, or a
    replay billing `ep_grade_judge` makes production spend unreadable — which is what happened."""
    offenders = [f"{rel}:{ln}" for rel, ln, fn, call in _call_sites()
                 if _log_caller_of(call, fn) == _LIVE_LABEL and rel != _LIVE_PATH]
    assert not offenders, (
        f"non-live call site(s) billing {_LIVE_LABEL!r}: {offenders}. "
        "Shadows, evals and replays each need their own bucket.")


def test_the_live_path_still_bills_the_same_bucket_as_every_historical_row():
    """Removing the default must not re-label production spend — the history would break."""
    live = [_log_caller_of(c, fn) for rel, _ln, fn, c in _call_sites()
            if rel == _LIVE_PATH and fn == "grade_holistic"]
    assert live == [_LIVE_LABEL], f"live grade path labels: {live}"


def test_labels_are_literals_not_variables():
    """A computed label can silently become another lane's bucket, or an empty string."""
    bad = [f"{rel}:{ln}" for rel, ln, fn, call in _call_sites()
           if _log_caller_of(call, fn) == "<NOT-A-LITERAL>"]
    assert not bad, f"log_caller must be a literal at: {bad}"


def test_lane_labels_are_distinct_per_lane():
    """Two different experiments sharing one bucket is the same defect one level down."""
    by_label: dict[str, set[str]] = {}
    for rel, _ln, fn, call in _call_sites():
        lbl = _log_caller_of(call, fn)
        if isinstance(lbl, str) and not lbl.startswith("<"):
            by_label.setdefault(lbl, set()).add(rel)
    for lbl, files in by_label.items():
        assert len(files) == 1, f"label {lbl!r} is shared across lanes: {sorted(files)}"


def test_the_default_is_GONE_from_the_judge_signature():
    """The root cause. If a default comes back, every test above can pass while a new lane
    silently inherits the live bucket again — which is precisely what happened."""
    tree = ast.parse((_ROOT / "agents/market_intelligence/ep_grade_judge.py").read_text())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "grade_holistic")
    idx = [a.arg for a in fn.args.kwonlyargs].index("log_caller")
    assert fn.args.kw_defaults[idx] is None, \
        "log_caller must stay REQUIRED — a default is how experimental spend hid in production"


def test_the_shadow_and_the_eval_do_not_share_a_bucket():
    """They answer different questions and get authorised separately — the offline eval's spend is
    something the operator signs off on per run (#519), so it must be countable on its own."""
    labels = {lbl for _rel, _ln, fn, c in _call_sites()
              for lbl in [_log_caller_of(c, fn)] if isinstance(lbl, str)}
    assert "chart_axis_shadow" in labels and "chart_axis_eval" in labels


@pytest.mark.parametrize("fn_name", sorted(_JUDGE_CALLS))
def test_the_judge_entry_points_all_require_the_label(fn_name):
    """grade_one / grade_b_c are the shadow+eval front door; a default on either would re-open
    the hole one layer above grade_holistic."""
    for mod in ("agents/market_intelligence/ep_grade_judge.py",
                "agents/market_intelligence/chart_axis.py"):
        tree = ast.parse((_ROOT / mod).read_text())
        fn = next((n for n in ast.walk(tree)
                   if isinstance(n, ast.AsyncFunctionDef) and n.name == fn_name), None)
        if fn is None:
            continue
        names = [a.arg for a in fn.args.args] + [a.arg for a in fn.args.kwonlyargs]
        assert "log_caller" in names, f"{fn_name} in {mod} takes no log_caller"
        if "log_caller" in [a.arg for a in fn.args.args]:
            # positional: a default would sit in the tail of fn.args.defaults
            pos = [a.arg for a in fn.args.args]
            n_defaults = len(fn.args.defaults)
            first_defaulted = len(pos) - n_defaults
            assert pos.index("log_caller") < first_defaulted, \
                f"{fn_name} gives log_caller a default — that is the defect"
        else:
            i = [a.arg for a in fn.args.kwonlyargs].index("log_caller")
            assert fn.args.kw_defaults[i] is None, f"{fn_name} gives log_caller a default"
