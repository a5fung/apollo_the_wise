#!/usr/bin/env python3
"""#213 Wave 0b ISOLATING EXPERIMENT (READ-ONLY; NO DB writes, NO trade state).

Question (advisor 2026-06-06): does swapping the membership validator's model
Haiku -> Sonnet, on the CURRENT UNCHANGED prompt, fix the false-removals WITHOUT
touching the prompt? The current prompt removes only if "core business is in a
DIFFERENT INDUSTRY than the theme." SNDK (NAND flash storage) is NOT a different
industry from "AI Memory & Storage" — Haiku evicted it by misreading the "AI"
driver-qualifier as a membership filter. A stronger model reading the SAME prompt
should keep it. If so, the model swap is the ENTIRE fix and the (high-risk,
unvalidatable-right-now) prompt de-bias is unnecessary.

DESIGN — two-sided over KNOWN cases (no hand-wavy cohort; each case has a
defensible expected outcome):
  FALSE-REMOVAL side (expect KEEP — the bug):
    - AI Memory & Storage: SNDK, SIMO are NAND flash/controllers = storage core.
    - Optical Components: POET is optical/photonic = the theme's core.
  GENUINE-REMOVAL side (expect REMOVE — must be preserved):
    - AI Memory & Storage + CAR (Avis car rental) = wrong industry, clear control.
    - Pure-Play Hydraulic Fracturing + XOM/CVX (integrated majors) = fail the
      STRUCTURAL 'pure-play' criterion that defines the theme.

The prompt is reconstructed VERBATIM from _validate_theme_membership (the
production code path) so the only variable is the model. Descriptions come from
the real universe TICKER_DESC, exactly like production; undescribed tickers fall
back to "(use your knowledge)".

DECISION TREE (locked before running):
  - Sonnet KEEPS all false-removal tickers AND REMOVES all genuine ones
      => model swap is the entire fix. Ship Haiku->Sonnet (operator-requested),
         skip the prompt de-bias, file theme-naming defect separately.
  - Sonnet still FALSELY removes SNDK/SIMO/POET
      => model alone insufficient; need a SURGICAL prompt edit (don't treat
         momentum/driver qualifiers like 'AI' as membership filters; DO enforce
         structural ones like 'pure-play') — built later against a real cohort.
  - Sonnet KEEPS the genuine-wrong names (XOM/CAR)
      => Sonnet is too permissive on the current prompt; reconsider.

Run (server, read-only):
  docker exec apollo-market python scripts/eval_theme_validation_model.py
"""
import asyncio
import json
import os
import re

import anthropic

MODELS = [
    ("haiku (current prod)", "claude-haiku-4-5-20251001"),
    ("sonnet (candidate)", "claude-sonnet-4-6"),
]

# (theme_name, members, expect_removed) — expect_removed is the set the validator
# SHOULD flag. Empty set = keep everyone.
CASES = [
    (
        "AI Memory & Storage",
        ["MRAM", "WDC", "STX", "MU", "SNDK", "SIMO"],
        set(),  # all are memory/storage — keep all (live false-removal case)
    ),
    (
        "AI Memory & Storage",
        ["MU", "WDC", "STX", "SNDK", "SIMO", "CAR"],
        {"CAR"},  # Avis car rental = wrong industry control; keep the storage names
    ),
    (
        "Optical Components & Transceiver Manufacturers",
        ["VIAV", "AXTI", "CIEN", "GLW", "LASR", "OPTX", "POET"],
        set(),  # POET is optical/photonic — keep; rest are legit optical
    ),
    (
        "Pure-Play Hydraulic Fracturing & Completion Services",
        ["LBRT", "PUMP", "NINE", "PTEN", "XOM", "CVX", "EQNR"],
        {"XOM", "CVX", "EQNR"},  # integrated majors fail STRUCTURAL pure-play
    ),
]


def _extract_json_object(raw: str) -> str:
    """Brace-depth JSON extractor (mirrors theme_engine._extract_json_object)."""
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


def _build_prompt(theme_name, tickers, desc_map):
    """VERBATIM reconstruction of _validate_theme_membership's prompt."""
    parts = []
    for tk in tickers:
        desc = desc_map.get(tk)
        if desc:
            parts.append(f"- {tk}: {desc}")
        else:
            parts.append(f"- {tk}: (use your knowledge of this ticker)")
    stock_lines = "\n".join(parts)
    return (
        f"Theme: \"{theme_name}\"\n\n"
        f"Stocks in this theme:\n{stock_lines}\n\n"
        f"Identify stocks that DO NOT BELONG in this theme.\n"
        f"A stock does not belong if its core business is in a DIFFERENT INDUSTRY than the theme — "
        f"e.g. a car rental company in a data center theme, a mining company in a biotech theme, "
        f"a retailer in a semiconductor theme. Be DECISIVE: wrong industry = remove. "
        f"Do not keep a stock just because you are unsure — if the business sector clearly differs "
        f"from the theme, flag it.\n\n"
        f"Return JSON only: {{\"remove\": [\"TICKER1\", \"TICKER2\"]}} or {{\"remove\": []}} if all belong."
    )


async def _ask(client, model, prompt):
    resp = await client.messages.create(
        model=model,
        max_tokens=400,
        system="You are a JSON API. Respond with valid JSON only. No prose, no markdown, no explanation.",
        messages=[{"role": "user", "content": prompt}],
    )
    raw = (getattr(resp.content[0], "text", "") or "").strip()
    if raw.startswith("```"):
        p = raw.split("\n", 1)
        raw = p[1].rstrip("` \n").strip() if len(p) > 1 else raw.strip("` ")
    raw = _extract_json_object(raw)
    result = json.loads(raw)
    rem = result.get("remove") or []
    return {t.upper() for t in rem if isinstance(t, str)}


async def main():
    try:
        from agents.market_intelligence.universe import TICKER_DESC
    except Exception:
        TICKER_DESC = {}

    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    print("=" * 78)
    print("#213 Wave 0b — model isolation: Haiku vs Sonnet on CURRENT prompt")
    print("=" * 78)

    # tallies per model
    score = {label: {"false_removed": 0, "genuine_kept": 0, "correct": 0, "n": 0}
             for label, _ in MODELS}

    for theme_name, tickers, expect_removed in CASES:
        prompt = _build_prompt(theme_name, tickers, TICKER_DESC)
        print(f"\n### {theme_name}")
        print(f"    members: {tickers}")
        print(f"    expect remove: {sorted(expect_removed) or '(none)'}")
        for label, model in MODELS:
            try:
                got = await _ask(client, model, prompt)
            except Exception as e:
                print(f"    {label:24s} ERROR: {e}")
                continue
            false_removed = got - expect_removed            # removed something it shouldn't
            missed_removes = expect_removed - got           # failed to remove a genuine-wrong
            ok = (got == expect_removed)
            s = score[label]
            s["n"] += 1
            s["false_removed"] += len(false_removed)
            s["genuine_kept"] += len(missed_removes)
            s["correct"] += 1 if ok else 0
            flag = "OK " if ok else "XX "
            detail = []
            if false_removed:
                detail.append(f"FALSE-REMOVED {sorted(false_removed)}")
            if missed_removes:
                detail.append(f"MISSED-REMOVE {sorted(missed_removes)}")
            print(f"    {flag}{label:24s} removed={sorted(got) or '[]':}  {'; '.join(detail)}")

    print("\n" + "=" * 78)
    print("SUMMARY")
    for label, _ in MODELS:
        s = score[label]
        print(f"  {label:24s} correct {s['correct']}/{s['n']}  "
              f"false-removals={s['false_removed']}  genuine-kept(missed)={s['genuine_kept']}")
    print("=" * 78)
    print("Decision: Sonnet correct on ALL + 0 false-removals => model swap is the "
          "entire fix (ship Haiku->Sonnet, skip prompt de-bias).")


if __name__ == "__main__":
    asyncio.run(main())
