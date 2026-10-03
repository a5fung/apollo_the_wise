"""#693 — what does "thinking off" actually cost on claude-sonnet-5-5? Variant A vs variant B.

For each job in the THINKING_DISABLED registry (shared/llm_thinking.py) it takes that job's LATEST
captured real request (shared/llm_samples, #690) and sends it twice to the API through a RAW
anthropic client (no shared/llm_client adapter — the point is to control `thinking` by hand):

  A = what runs TODAY on 5.5: `thinking` dropped, `max_tokens` raised by thinking_headroom()
      (the adapter's drop + headroom — adaptive thinking is on, it shares max_tokens).
  B = the #693 fix: `thinking: {"type": "between_tools"}`, `max_tokens` UNCHANGED.

A forced tool_choice is a 400 on 5.5, so a forced-tool request is first turned into structured
output exactly as the adapter does it (the adapter's own pure helpers are imported, not the
client): both variants share that rewrite and differ ONLY in the thinking switch and max_tokens.

Per call it prints: output tokens, stop_reason, whether the answer parsed (the forced tool's
required fields are present, or the plain JSON object parses), thinking blocks returned, latency
and cost — then per-job A-vs-B lines and totals, and one `RESULT_JSON` line for re-reading.

RUN (read-only: no DB, no Telegram, sample capture off; one process, ONE paid run — capture it):

    # 1. $0 — shows the plan and the cost estimate, calls nothing
    docker exec -i apollo-market python - --dry-run < scripts/probes/_693/measure_thinking_off.py
    # 2. the paid run, saved ONCE
    docker exec -i apollo-market python - < scripts/probes/_693/measure_thinking_off.py \\
        > /tmp/693_measure_thinking_off.txt

The cost estimate (WORST CASE: every call fills its max_tokens) is printed BEFORE any call and the
run aborts if it exceeds --max-usd (default 2.00). Expected calls = (jobs with a captured request)
x 2 variants x --repeats (default 1). The default model for each job is the model its role is
bound to in this process (`effective_model`); between_tools only exists on claude-sonnet-5-5, so a
job bound to any other model aborts the run before any spend unless --model is given.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time

# `python -` puts the working directory first on sys.path; make the app root importable even if
# the exec landed somewhere else.
for _d in ("/app", os.getcwd()):
    if os.path.isdir(os.path.join(_d, "shared")) and _d not in sys.path:
        sys.path.insert(0, _d)

# THINKING_DISABLED job -> the call-site key(s) (shared/llm_call_sites.CALL_SITES) that send it.
# A job in the registry with no entry here is reported as UNMAPPED, never silently skipped.
JOB_KEYS: dict[str, tuple[str, ...]] = {
    "theme_validation": ("agents.market_intelligence.theme_engine:_validate_theme_membership",),
    "narrative_theme_discovery": (
        "agents.market_intelligence.theme_engine:discover_narrative_themes",
        "agents.market_intelligence.theme_engine:_discover_lane2_registry",
    ),
    "theme_synthesis": ("agents.market_intelligence.theme_synthesis:run_theme_synthesis",),
    "theme_parent_adjudication": ("agents.market_intelligence.theme_merge_arm:adjudicate_containment_pair",),
}
BETWEEN_TOOLS = {"type": "between_tools"}
NO_BETWEEN_TOOLS_EFFORTS = ("xhigh", "max")
CHARS_PER_TOKEN = 3.5     # JSON-heavy prompts run ~3.5 chars/token; lower = a higher (safer) estimate


# ── selection ────────────────────────────────────────────────────────────────

def latest_disabled_sample(data: dict) -> dict | None:
    """The newest replayable sample in one call-site file whose request asked for thinking off."""
    best = None
    for s in data.get("samples") or []:
        req = s.get("request") or {}
        if not s.get("replayable", True) or req.get("thinking") != {"type": "disabled"}:
            continue
        if best is None or str(s.get("captured_at")) > str(best.get("captured_at")):
            best = s
    return best


def effort_of(request: dict) -> str:
    oc = request.get("output_config")
    e = oc.get("effort") if isinstance(oc, dict) else None
    return e.strip().lower() if isinstance(e, str) else ""


def build_variants(request: dict, model: str, lc) -> tuple[dict, dict | None, dict | None]:
    """(A kwargs, B kwargs or None, forced-tool plan or None) for one captured request."""
    base = copy.deepcopy(request)
    base["model"] = model
    plan = None
    if lc._forced_tool_target(base) is not None:
        base, plan = lc._apply_forced_tool_rewrite(base)
    a = dict(base)
    a.pop("thinking", None)
    a["max_tokens"] = lc.thinking_headroom(base["max_tokens"])
    if effort_of(base) in NO_BETWEEN_TOOLS_EFFORTS:
        return a, None, plan
    b = dict(base)
    b["thinking"] = dict(BETWEEN_TOOLS)          # max_tokens stays the caller's text budget
    return a, b, plan


def est_input_tokens(kwargs: dict) -> int:
    payload = {k: kwargs.get(k) for k in ("system", "messages", "tools", "output_config") if k in kwargs}
    return int(len(json.dumps(payload, default=str)) / CHARS_PER_TOKEN) + 1


def worst_case_usd(kwargs: dict, price: dict) -> float:
    return (est_input_tokens(kwargs) * price["input"] + kwargs["max_tokens"] * price["output"]) / 1e6


# ── judging one answer ───────────────────────────────────────────────────────

def _extract_json_object(raw: str) -> str:
    start = raw.find("{")
    if start < 0:
        return raw
    depth = 0
    for i in range(start, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                return raw[start:i + 1]
    return raw[start:]


def refusal_category(resp) -> str:
    """stop_details.category of a refusal, dict-or-object. Inlined on purpose: this script runs in
    the PROD container BEFORE the #693 branch deploys, where shared.llm_response has no such
    helper — it may only import what main already has."""
    details = resp.get("stop_details") if isinstance(resp, dict) else getattr(resp, "stop_details", None)
    cat = details.get("category") if isinstance(details, dict) else getattr(details, "category", None)
    return cat if isinstance(cat, str) else ""


def judge(resp, plan: dict | None, request: dict, lc, llm_response) -> tuple[bool, str]:
    """(parsed, why-not). Parsed = the caller would have had a usable answer."""
    sr = llm_response.stop_reason(resp)
    if sr == "refusal":
        return False, f"refusal ({refusal_category(resp) or 'no category'})"
    if sr == "max_tokens":
        return False, "truncated at max_tokens"
    tools = {t.get("name"): t for t in request.get("tools") or [] if isinstance(t, dict)}
    if plan:
        try:
            resp = lc._synthesize(resp, plan)
        except Exception as e:
            return False, f"{type(e).__name__}: {str(e)[:100]}"
    uses = [b for b in getattr(resp, "content", None) or [] if getattr(b, "type", "") == "tool_use"]
    if tools:
        if not uses:
            return False, "no tool_use"
        for b in uses:
            required = [k for k in ((tools.get(b.name) or {}).get("input_schema") or {}).get("required") or []]
            missing = [k for k in required if not isinstance(b.input, dict) or k not in b.input]
            if missing:
                return False, f"missing {','.join(missing)}"
        return True, ""
    raw = llm_response.first_text(resp).strip()
    if raw.startswith("```"):
        parts = raw.split("\n", 1)
        raw = parts[1].rstrip("` \n").strip() if len(parts) > 1 else raw.strip("` ")
    try:
        return isinstance(json.loads(_extract_json_object(raw)), dict), ""
    except ValueError:
        return False, "not JSON"


def call_once(client, kwargs: dict, plan, request: dict, price: dict, lc, llm_response) -> dict:
    t0 = time.perf_counter()
    try:
        resp = client.messages.create(**kwargs)
    except Exception as e:   # a failed call is a RESULT here, never a crash
        return {"error": f"{type(e).__name__}: {str(e)[:200]}", "secs": time.perf_counter() - t0,
                "parsed": False, "why": "api error", "out_tokens": None, "in_tokens": None,
                "stop": None, "think_blocks": None, "usd": 0.0}
    secs = time.perf_counter() - t0
    usage = getattr(resp, "usage", None)
    out_t = getattr(usage, "output_tokens", None)
    in_t = getattr(usage, "input_tokens", None)
    try:
        parsed, why = judge(resp, plan, request, lc, llm_response)
    except Exception as e:   # a judging bug must not lose a paid answer's numbers
        parsed, why = False, f"judge error {type(e).__name__}: {str(e)[:80]}"
    usd = ((in_t or 0) * price["input"] + (out_t or 0) * price["output"]) / 1e6
    return {"error": "", "secs": secs, "parsed": parsed, "why": why, "out_tokens": out_t,
            "in_tokens": in_t, "stop": llm_response.stop_reason(resp), "usd": usd,
            "think_blocks": sum(1 for b in getattr(resp, "content", None) or []
                                if getattr(b, "type", "") in ("thinking", "redacted_thinking"))}


# ── the run ──────────────────────────────────────────────────────────────────

def run(argv: list[str] | None = None, *, client=None, out=print) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="print the plan and the cost estimate; call nothing")
    ap.add_argument("--max-usd", type=float, default=2.0, help="abort above this WORST-CASE estimate")
    ap.add_argument("--repeats", type=int, default=1, help="calls per variant per job (default 1)")
    ap.add_argument("--model", default="", help="override the model for every job")
    ap.add_argument("--include-others", action="store_true",
                    help="also measure any other captured disabled-thinking call site (not in the registry)")
    args = ap.parse_args(argv)

    from shared import llm_response, llm_samples
    from shared import llm_client as lc
    from shared.llm_call_sites import CALL_SITES
    from shared.llm_models import effective_model, pricing_for
    from shared.llm_thinking import THINKING_DISABLED

    files = {d["key"]: d for d in llm_samples.load_all()}
    out(f"samples dir: {llm_samples.sample_dir()}  files: {len(files)}")
    unmapped = sorted(j for j in THINKING_DISABLED if j not in JOB_KEYS)
    if unmapped:
        out(f"UNMAPPED registry jobs (no call-site key in JOB_KEYS, NOT measured): {unmapped}")

    plan_rows = []
    for job in sorted(THINKING_DISABLED):
        for key in JOB_KEYS.get(job, ()):
            if key not in CALL_SITES:
                out(f"  {job}: key {key} is not in CALL_SITES - regenerate or fix JOB_KEYS")
                continue
            sample = latest_disabled_sample(files.get(key) or {})
            if sample is None:
                out(f"  {job} [{key.split(':')[-1]}]: NO captured thinking-disabled request - skipped")
                continue
            plan_rows.append((job, key, sample))
    if args.include_others:
        mapped = {k for ks in JOB_KEYS.values() for k in ks}
        for key, data in sorted(files.items()):
            sample = latest_disabled_sample(data) if key not in mapped else None
            if sample is not None:
                plan_rows.append((f"other:{key.split(':')[-1]}", key, sample))
    elif files:
        mapped = {k for ks in JOB_KEYS.values() for k in ks}
        others = [k for k, d in sorted(files.items()) if k not in mapped and latest_disabled_sample(d)]
        if others:
            out(f"also captured with thinking off but NOT measured (--include-others): "
                f"{[k.split(':')[-1] for k in others]}")
    if not plan_rows:
        out("nothing to measure")
        return 2

    jobs = []
    for job, key, sample in plan_rows:
        role = CALL_SITES.get(key, "")
        model = args.model or (effective_model(role) if role and role != "UNTRACKED" else "") \
            or str(sample.get("model") or "")
        a, b, plan = build_variants(sample["request"], model, lc)
        jobs.append({"job": job, "key": key, "role": role, "model": model, "sample": sample,
                     "A": a, "B": b, "plan": plan, "price": pricing_for(model)})

    bad_models = sorted({j["model"] for j in jobs if not j["model"].startswith("claude-sonnet-5-5")})
    out("")
    out(f"{'job':50} {'model':18} {'captured':11} {'in~':>7} {'A max_tok':>9} {'B max_tok':>9}  effort")
    total = 0.0
    n_calls = 0
    for j in jobs:
        est_in = est_input_tokens(j["A"])
        a_cost = worst_case_usd(j["A"], j["price"])
        b_cost = worst_case_usd(j["B"], j["price"]) if j["B"] else 0.0
        total += (a_cost + b_cost) * args.repeats
        n_calls += (1 + (1 if j["B"] else 0)) * args.repeats
        out(f"{j['job'] + ' [' + j['key'].split(':')[-1] + ']':50.50} {j['model']:18} "
            f"{str(j['sample'].get('captured_at'))[:10]:11} {est_in:>7} {j['A']['max_tokens']:>9} "
            f"{(j['B'] or {}).get('max_tokens', 'n/a'):>9}  {effort_of(j['A']) or '-'}")
    out(f"\nCALLS: {n_calls}   WORST-CASE COST: ${total:.3f}  (every call fills max_tokens; limit ${args.max_usd:.2f})")
    if bad_models and not args.model:
        out(f"ABORT: between_tools exists only on claude-sonnet-5-5; these jobs are bound to {bad_models}. "
            "Pass --model claude-sonnet-5-5 to measure them on it. Nothing was spent.")
        return 3
    if total > args.max_usd:
        out(f"ABORT: worst case ${total:.3f} exceeds --max-usd {args.max_usd:.2f}. Nothing was spent.")
        return 3
    if args.dry_run:
        out("dry run - nothing called")
        return 0

    if client is None:
        import anthropic
        if not os.environ.get("ANTHROPIC_API_KEY"):
            out("ABORT: ANTHROPIC_API_KEY is not set in this process. Nothing was spent.")
            return 2
        client = anthropic.Anthropic(max_retries=2, timeout=180.0)

    results = []
    out(f"\n{'job':30} {'var':3} {'out_tok':>8} {'stop':>10} {'parsed':>6} {'think':>5} {'secs':>6} {'usd':>7}  note")
    with llm_samples.capture_disabled():
        for j in jobs:
            for rep in range(args.repeats):
                for var in ("A", "B"):
                    if j[var] is None:
                        out(f"{j['job']:30.30} {var:3} {'n/a (effort ' + effort_of(j['A']) + ')':>40}")
                        continue
                    r = call_once(client, j[var], j["plan"], j["sample"]["request"], j["price"], lc, llm_response)
                    r.update(job=j["job"], var=var, rep=rep)
                    results.append(r)
                    out(f"{j['job']:30.30} {var:3} {str(r['out_tokens']):>8} {str(r['stop']):>10} "
                        f"{('yes' if r['parsed'] else 'NO'):>6} {str(r['think_blocks']):>5} "
                        f"{r['secs']:>6.1f} {r['usd']:>7.4f}  {r['error'] or r['why']}")

    out("\nPER JOB (mean over repeats)   A = today (drop + headroom)   B = between_tools, max_tokens unchanged")
    for j in jobs:
        rows = {v: [r for r in results if r["job"] == j["job"] and r["var"] == v] for v in ("A", "B")}
        def mean(v, f):
            xs = [r[f] for r in rows[v] if r[f] is not None]
            return sum(xs) / len(xs) if xs else None
        a_t, b_t = mean("A", "out_tokens"), mean("B", "out_tokens")
        delta = f"{(b_t - a_t):+.0f} tokens ({(b_t - a_t) / a_t:+.0%})" if a_t and b_t is not None else "n/a"
        out(f"  {j['job']:28.28} out_tokens A={a_t if a_t is None else round(a_t)}  B={b_t if b_t is None else round(b_t)}  "
            f"B-A={delta}   parsed A={sum(r['parsed'] for r in rows['A'])}/{len(rows['A'])} "
            f"B={sum(r['parsed'] for r in rows['B'])}/{len(rows['B'])}")

    out("\nTOTALS")
    totals = {}
    for v in ("A", "B"):
        rs = [r for r in results if r["var"] == v]
        toks = sum(r["out_tokens"] or 0 for r in rs)
        totals[v] = {"calls": len(rs), "out_tokens": toks, "parsed": sum(r["parsed"] for r in rs),
                     "errors": sum(1 for r in rs if r["error"]),
                     "mean_secs": (sum(r["secs"] for r in rs) / len(rs)) if rs else None,
                     "usd": sum(r["usd"] for r in rs)}
        t = totals[v]
        out(f"  {v}: calls={t['calls']} output_tokens={t['out_tokens']} parsed={t['parsed']}/{t['calls']} "
            f"errors={t['errors']} mean_latency={t['mean_secs'] and round(t['mean_secs'], 1)}s usd=${t['usd']:.4f}")
    if totals["A"]["out_tokens"]:
        a_tok, b_tok = totals["A"]["out_tokens"], totals["B"]["out_tokens"]
        out(f"  B vs A output tokens: {b_tok - a_tok:+d} ({(b_tok - a_tok) / a_tok:+.0%})")
    out("RESULT_JSON " + json.dumps({"totals": totals, "results": results}, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
