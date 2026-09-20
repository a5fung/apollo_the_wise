#!/usr/bin/env python3
"""#661 — OLD-vs-NEW replay of ONE nightly assignment run and the EP-time fit call, in ONE process.

THE CLAIM UNDER TEST: factoring the assignment LLM call into a seam (`_assignment_turn`, used
directly by `judge_theme_fit` and wrapped by the nightly `_propose_assignment_batch`) changed
NOTHING the model sees and NOTHING the system records. The DoD is byte-identity: the same
proposal list and the same audit events as before.

HOW: the pre-seam `theme_engine.py` is read straight out of git (`git show <OLD_SHA>:...`) and
exec'd as a second module beside the current one, in the same interpreter — so this compares
old code vs new code on one machine, never prod against a laptop. Both are driven through the
REAL `_assign_uncovered_to_themes` (chunking, the batch loop, the partition filter, the apply
loop) and the REAL `judge_theme_fit`, against IDENTICAL scripted model responses (fresh objects
per run, built from one spec). Everything observable is captured in order and diffed:

  create   every `messages.create` kwargs, deep-frozen — the prompt BYTES (shared prefix +
           body, incl. batch note, cooldown note, advisor paragraph), `tools`, `tool_choice`,
           `model`, `max_tokens`, `thinking`, and on advisor turns the appended assistant
           content + tool_result message
  spend    every cost-meter call (model, caller)
  advisor  every Opus consult (question, context, caller)
  audit    every audit row (event_type, summary, detail) — the DoD's "same audit events"
  result   the proposals as applied: changelog + remaining pool (nightly); (status, theme,
           rationale) per case (EP)

Scenarios — chosen to walk EVERY branch of the old driver, not the happy path only:
  A  nightly, 40 stocks → 3 batches, cooldown note rendered: batch 1 consults the advisor
     then proposes (incl. a cross-batch echo the partition drops); batch 2 proposes direct
     (incl. a theme that does not exist, dropped by validation); batch 3 TRUNCATES.
  B  nightly, 20 stocks → 2 batches: batch 1 SILENT-STOPS (text only); batch 2 asks the
     advisor 4× (3 answered, the 4th denied by the run-level budget) then proposes.
  C  EP-time fit, 6 cases: confirmed with a [Fading] echo · no fit · a theme not offered ·
     truncated · silent stop · no description (no call).

SENSITIVITY: the zero is proven non-vacuous by re-running the NEW module with a ONE-BYTE
prompt change and showing the diff catches it.

WHAT THIS DOES AND DOES NOT PROVE: it proves the CODE turns identical model responses into
identical requests, telemetry and proposals. It says nothing about the live model's answers —
which a byte-identical request cannot change — and it exercises the branches with scripted
responses, not a recorded night (the raw model output is not stored anywhere; only the
proposals are). No paid call is made.

Run:  python3 scripts/probes/_661_assignment_seam_replay.py [--old a25b6113]
Exit code 0 = zero differing lines; 1 = a difference (printed as a unified diff).
"""
from __future__ import annotations

import argparse
import asyncio
import difflib
import hashlib
import json
import os
import subprocess
import sys
import types
from types import SimpleNamespace

os.environ.setdefault("APOLLO_CALL_ORIGIN", "probe")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

OLD_SHA = "a25b6113"  # the last commit BEFORE the seam (the base #661 was cut against)
OLD_NAME = "agents.market_intelligence.theme_engine_old_661"


# ── loading the pre-seam module beside the current one ────────────────────────────────────

def load_old(sha: str):
    src = subprocess.check_output(
        ["git", "show", f"{sha}:agents/market_intelligence/theme_engine.py"], cwd=ROOT, text=True)
    mod = types.ModuleType(OLD_NAME)
    mod.__file__ = f"<git:{sha}:agents/market_intelligence/theme_engine.py>"
    mod.__package__ = "agents.market_intelligence"
    sys.modules[OLD_NAME] = mod
    exec(compile(src, mod.__file__, "exec"), mod.__dict__)
    return mod


# ── freezing what we observe ──────────────────────────────────────────────────────────────

def freeze(obj):
    """Deep-convert to JSON-able data. Response blocks are SimpleNamespace / plain objects —
    they become dicts, so an assistant turn's content compares by VALUE, not identity."""
    if isinstance(obj, dict):
        return {str(k): freeze(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [freeze(v) for v in (sorted(obj, key=repr) if isinstance(obj, set) else obj)]
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if hasattr(obj, "__dict__"):
        return {"__type__": type(obj).__name__, **freeze(vars(obj))}
    return repr(obj)


# ── scripted model responses (fresh objects per run, one spec) ────────────────────────────

class Block:
    def __init__(self, type, name=None, input=None, id="b1", text=""):
        self.type, self.name, self.input, self.id, self.text = type, name, input or {}, id, text


def resp(*blocks, stop_reason="tool_use", out_tok=500):
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason,
                           usage=SimpleNamespace(output_tokens=out_tok))


def assign(assignments, scratch, *, stop_reason="tool_use", out_tok=500, id="tu_assign"):
    inp = {"analysis_scratchpad": scratch}
    if stop_reason != "max_tokens":
        inp["assignments"] = assignments   # a truncated tool call parses with the key missing
    return resp(Block("tool_use", name="assign_stocks_to_themes", input=inp, id=id),
                stop_reason=stop_reason, out_tok=out_tok)


def consult(question, context, id):
    return resp(Block("tool_use", name="consult_advisor",
                      input={"question": question, "context": context}, id=id))


def text_only(text):
    return resp(Block("text", text=text))


SCRIPT_A = {
    0: lambda: consult("Does T004 fit Widget Platforms or Gadget Makers — which is more specific?",
                       "T004: maker of widget 4, RS 90, Technology. Both themes are plausible.", "tu_adv_a1"),
    1: lambda: assign(
        [{"ticker": "T000", "theme": "Widget Platforms", "rationale": "a widget platform maker"},
         {"ticker": "T005", "theme": "Gadget Makers", "rationale": "makes gadgets, clearly"},
         {"ticker": "T020", "theme": "Widget Platforms", "rationale": "cross-batch echo"}],
        "T000: widget platform — fit Widget Platforms\nT001: widget 1 — no fit\nT004: ambiguous — "
        "advisor says Widget Platforms but not clearly, no fit\nT005: gadgets — fit Gadget Makers\n"
        "T020: (not on my list) widget platform — fit Widget Platforms"),
    2: lambda: assign(
        [{"ticker": "T019", "theme": "Gadget Makers", "rationale": "gadget manufacturer"},
         {"ticker": "T021", "theme": "No Such Theme", "rationale": "hallucinated home"}],
        "T018: widget 18 — no fit\nT019: gadgets — fit Gadget Makers\nT021: fits No Such Theme"),
    3: lambda: assign([], "T036: widget 36 — no fit\nT037: widget 37 — cut off mid-",
                      stop_reason="max_tokens", out_tok=8000),
}

SCRIPT_B = {
    0: lambda: text_only("I considered the list but none of these clearly fit, so I will stop here "
                         "rather than call the tool."),
    1: lambda: consult("Is T018 a widget platform?", "T018 makes widget 18", "tu_adv_b1"),
    2: lambda: consult("Is T019 a gadget maker?", "T019 makes widget 19", "tu_adv_b2"),
    3: lambda: consult("Second opinion on T018", "still unsure", "tu_adv_b3"),
    4: lambda: consult("Third opinion on T018", "still unsure", "tu_adv_b4"),   # budget denies
    5: lambda: assign([{"ticker": "T019", "theme": "Gadget Makers", "rationale": "gadgets"}],
                      "T018: no fit\nT019: fit Gadget Makers"),
}

EP_THEMES = [
    {"name": "Bitcoin Miners", "stage": "Accelerating", "tickers": ["MARA", "RIOT", "CLSK"],
     "description": "Bitcoin mining operators with hashrate growth and AI data-center pivots"},
    {"name": "Old Optical", "stage": "Fading", "tickers": ["LITE", "COHR"],
     "description": "Optical networking components" + " x" * 80},
]

EP_CASES = [
    ("confirmed_fading_echo", dict(ticker="LITE", description="optical components", sector="Technology", rs_composite=77.7),
     lambda: assign([{"ticker": "LITE", "theme": "Old Optical [Fading]", "rationale": "optical parts"}], "LITE: optical — fit Old Optical")),
    ("rejected_no_fit", dict(ticker="lite", description="a regulated power utility", sector="Utilities"),
     lambda: assign([], "LITE: a utility — no fit")),
    ("rejected_not_offered", dict(ticker="LITE", description="quantum annealers", sector=None),
     lambda: assign([{"ticker": "LITE", "theme": "Quantum Computing", "rationale": "x"}], "s")),
    ("failed_truncated", dict(ticker="LITE", description="d", sector=None),
     lambda: assign([], "cut off mid-", stop_reason="max_tokens", out_tok=8000)),
    ("failed_silent_stop", dict(ticker="LITE", description="d", sector=None),
     lambda: text_only("I would rather not.")),
    ("failed_no_description", dict(ticker="LITE", description="   ", sector="Technology"),
     None),
]


# ── fixtures shared by both runs ──────────────────────────────────────────────────────────

def install_descriptions(n: int):
    from agents.market_intelligence import universe
    for i in range(n):
        universe.TICKER_DESC[f"T{i:03d}"] = f"maker of widget {i}"


def mk_stocks(n: int) -> list[dict]:
    return [{"ticker": f"T{i:03d}", "rs_composite": 90 - i * 0.5, "sector": "Technology"} for i in range(n)]


def mk_themes() -> list[dict]:
    return [
        {"name": "Widget Platforms", "stage": "Nascent", "tickers": ["AAA", "BBB"],
         "description": "widget platform makers"},
        {"name": "Gadget Makers", "stage": "Nascent", "tickers": ["CCC", "DDD"],
         "description": "gadget manufacturing"},
    ]


def stubs(mod, log: list, script):
    """Point one module copy's infra at the capture log; return the scripted client."""
    import agents.market_intelligence.spend_tracker as spend_mod

    async def _audit(event_type, summary="", detail="", **kw):
        log.append(("audit", {"event_type": event_type, "summary": summary, "detail": detail,
                              **freeze(kw)}))

    async def _spend(**kw):
        log.append(("spend", {"model": kw.get("model"), "caller": kw.get("caller"),
                              "output_tokens": kw["response"].usage.output_tokens}))

    async def _advice(question, context, caller=""):
        log.append(("advisor", {"question": question, "context": context, "caller": caller}))
        return "Verdict: Widget Platforms — it is a platform, not a gadget."

    async def _validate_ok(name, tickers, changelog, protected=None):
        return tickers

    calls = {"n": 0}

    async def _create(**kwargs):
        log.append(("create", freeze(kwargs)))   # frozen NOW — the loop mutates `messages` later
        r = script[calls["n"]]()
        calls["n"] += 1
        return r

    client = SimpleNamespace(messages=SimpleNamespace(create=_create))
    mod.log_audit_event = _audit
    mod._call_advisor = _advice
    mod._validate_theme_membership = _validate_ok
    mod._get_anthropic_client = lambda: client
    spend_mod.log_anthropic_call_safe = _spend      # both copies import this lazily
    return client


def run_nightly(mod, script, n_stocks: int, cooldown_set) -> list:
    log: list = []
    stubs(mod, log, script)
    stocks = mk_stocks(n_stocks)
    themes = mk_themes()
    sbt = {tk: {"ticker": tk, "sector": "Technology"} for tk in ["AAA", "BBB", "CCC", "DDD"]}
    sbt.update({s["ticker"]: s for s in stocks})
    remaining, changelog = asyncio.run(mod._assign_uncovered_to_themes(
        stocks, themes, sbt, theme_exclusions=None, globally_banned=None,
        cooldown_set=cooldown_set, protected=None))
    log.append(("result", {"remaining": freeze(remaining), "changelog": freeze(changelog),
                           "themes_after": freeze(themes)}))
    return log


def run_ep(mod) -> list:
    log: list = []
    for name, kw, make in EP_CASES:
        client = stubs(mod, log, {0: make} if make else {})
        got = asyncio.run(mod.judge_theme_fit(kw["ticker"], description=kw["description"],
                                              sector=kw["sector"], themes=EP_THEMES,
                                              rs_composite=kw.get("rs_composite"), client=client))
        log.append(("result", {"case": name, "verdict": list(got)}))
    return log


# ── the comparison ────────────────────────────────────────────────────────────────────────

def lines_of(log: list) -> list[str]:
    return [json.dumps(e, sort_keys=True, ensure_ascii=False) for e in log]


def compare(label: str, old: list, new: list) -> int:
    ol, nl = lines_of(old), lines_of(new)
    kinds = {}
    for k, _ in old:
        kinds[k] = kinds.get(k, 0) + 1
    diff = [d for d in difflib.unified_diff(ol, nl, "old", "new", lineterm="", n=0)
            if (d.startswith("+") or d.startswith("-")) and not d.startswith(("+++", "---"))]
    h_old = hashlib.sha256("\n".join(ol).encode()).hexdigest()[:16]
    h_new = hashlib.sha256("\n".join(nl).encode()).hexdigest()[:16]
    print(f"[{label}] old {len(ol)} events {dict(sorted(kinds.items()))} sha {h_old}")
    print(f"[{label}] new {len(nl)} events sha {h_new}")
    print(f"[{label}] DIFFERING LINES: {len(diff)}")
    for d in diff[:40]:
        print("   ", d[:400])
    return len(diff)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", default=OLD_SHA, help="git sha of the pre-seam theme_engine.py")
    args = ap.parse_args()

    from agents.market_intelligence import theme_engine as new_mod
    old_mod = load_old(args.old)
    print(f"old = git {args.old}:agents/market_intelligence/theme_engine.py")
    print(f"new = {new_mod.__file__}")
    assert hasattr(old_mod, "_propose_assignment_batch") and not hasattr(old_mod, "_assignment_turn"), \
        "the OLD module already carries the seam — pick an earlier --old"
    assert hasattr(new_mod, "_assignment_turn"), "the NEW module has no seam — is this the #661 tree?"

    install_descriptions(40)
    total = 0
    total += compare("A nightly 3 batches: consult+propose / direct / truncated",
                     run_nightly(old_mod, SCRIPT_A, 40, {("T003", "Widget Platforms")}),
                     run_nightly(new_mod, SCRIPT_A, 40, {("T003", "Widget Platforms")}))
    total += compare("B nightly 2 batches: silent stop / advisor budget",
                     run_nightly(old_mod, SCRIPT_B, 20, set()),
                     run_nightly(new_mod, SCRIPT_B, 20, set()))
    total += compare("C EP-time fit, 6 cases", run_ep(old_mod), run_ep(new_mod))

    # Sensitivity: the same comparison must SEE a one-byte prompt change, or the zero above is
    # vacuous. Perturb the NEW module's advisor paragraph, compare against the untouched old,
    # restore. (Nightly only — the EP path does not send that paragraph, by design.)
    saved = new_mod._ASSIGNMENT_ADVISOR_NOTE
    new_mod._ASSIGNMENT_ADVISOR_NOTE = saved + " "
    try:
        sens = compare("SENSITIVITY (expect >0): new prompt +1 byte vs old",
                       run_nightly(old_mod, SCRIPT_A, 40, {("T003", "Widget Platforms")}),
                       run_nightly(new_mod, SCRIPT_A, 40, {("T003", "Widget Platforms")}))
    finally:
        new_mod._ASSIGNMENT_ADVISOR_NOTE = saved
    if sens == 0:
        print("SENSITIVITY CHECK FAILED — the comparison cannot see a prompt change; the zeros are void")
        return 2

    print(f"\nTOTAL DIFFERING LINES (A+B+C): {total}   sensitivity diff: {sens} (non-zero, as required)")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
