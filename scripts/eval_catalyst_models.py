#!/usr/bin/env python3
"""#188 model-eval (READ-ONLY analysis; NO DB writes, NO trade state).

Re-grades stored EP catalyst summaries with Haiku / Sonnet / Opus on the IDENTICAL
production classify_catalyst prompt/tool. Controlled same-input comparison: feeds the
stored `catalyst` summary (Perplexity's synthesized answer) to every model.

NOTE (fidelity caveat): production _classify_catalyst_claude feeds the RAW news list
(each item text[:200]); here we feed the stored summary to ALL models, so this isolates
MODEL quality on identical input (not a reproduction of the exact production grade).
The grade-the-summary task is expected to CONVERGE across models — the lever for that
task is the grounded INPUT (sourcing #187), not the model. quality-primary per operator.

Reads cases from /tmp/cases.json (psql json_agg). Per-model try/except so one model's
failure (e.g. an unavailable id) doesn't drop the case.
"""
import json
import os

import anthropic

# (label, model_id, ($/1M in, $/1M out))
MODELS = [
    ("haiku", "claude-haiku-4-5-20251001", (0.80, 4.00)),
    ("sonnet", "claude-sonnet-4-6", (3.00, 15.00)),
    ("opus", "claude-opus-4-8", (15.00, 75.00)),
]
WATCH = {"RUM", "PGY", "CRSR", "DY", "POWI", "GRRR"}  # text says no/weak catalyst; prod Haiku stored 'strong'

_CATALYST_TOOL = {
    "name": "classify_catalyst",
    "description": "Classify the quality of a stock EP catalyst and provide analysis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "quality": {
                "type": "string",
                "enum": ["game_changer", "strong", "routine", "mna"],
                "description": (
                    "game_changer: massive earnings beat + guidance raise, FDA approval, "
                    "transformative contract. strong: solid beat + guidance raise, analyst "
                    "upgrade cluster, major partnership. routine: in-line results, no "
                    "company-specific catalyst. mna: merger, acquisition, buyout, takeover, "
                    "going-private, tender offer, or any deal where the company is being acquired — "
                    "price is capped at deal value, no momentum trade possible."
                ),
            },
            "analysis": {
                "type": "string",
                "description": "2-3 sentences on the specific catalyst and classification rationale.",
            },
        },
        "required": ["quality", "analysis"],
    },
}


def build_prompt(ticker: str, news_text: str) -> str:
    return f"""You are analyzing a stock gap-up for EP (Episodic Pivot) trading.
This stock is gapping up significantly in pre-market. Your job is to identify the catalyst.

Stock: {ticker}
Company: {ticker} —
Description:

Recent news (may include earnings announcements, guidance, contracts, upgrades):
{news_text or "No news found."}

IMPORTANT RULES:
1. Look for: earnings releases, guidance raises, FDA decisions, major contracts, analyst upgrades.
2. An earnings beat with guidance raise on a neglected stock = game_changer or strong.
3. If the catalyst is a MERGER, ACQUISITION, BUYOUT, TAKEOVER, TENDER OFFER, GOING-PRIVATE, or any
   deal where the company is being acquired — classify as "mna". This is a hard skip: price is capped
   at deal value, there is no momentum trade. Keywords: "definitive agreement", "to be acquired",
   "tender offer", "going private", "taken private", "strategic transaction", "buyout", "merger agreement".

CRITICAL — VERIFY THE CATALYST IS REAL:
- If the news text mentions "earnings" or "quarterly results" but does NOT include specific numbers
  (revenue, EPS, guidance figures), the catalyst is likely FABRICATED. Classify as "routine".
- If the news is vague, generic, or reads like a summary with no specific details (no dates, no
  numbers, no named sources), classify as "routine" — the news source may have hallucinated.
- If none of the news items clearly explain WHY the stock gapped, classify as "routine".
- Penny stocks, biotechs with no revenue, and SPACs frequently gap on low-quality catalysts
  (press releases, conference presentations, speculative articles). Be skeptical — classify as "routine"
  unless the catalyst is concrete and verifiable.
- Do NOT assume earnings occurred just because news mentions "earnings" — look for actual reported
  numbers (EPS beat/miss, revenue figures, guidance).

In your analysis, state the SPECIFIC catalyst clearly. If you cannot identify a concrete, verifiable
catalyst, say so explicitly."""


def grade(client, model, ticker, news_text):
    r = client.messages.create(
        model=model,
        max_tokens=300,
        tools=[_CATALYST_TOOL],
        tool_choice={"type": "tool", "name": "classify_catalyst"},
        messages=[{"role": "user", "content": build_prompt(ticker, news_text)}],
    )
    tb = next(b for b in r.content if b.type == "tool_use")
    return tb.input["quality"], tb.input.get("analysis", ""), r.usage.input_tokens, r.usage.output_tokens


def main():
    with open("/tmp/cases.json") as f:
        cases = json.load(f)
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    tok = {name: [0, 0] for name, _, _ in MODELS}
    names = [name for name, _, _ in MODELS]
    notable = []
    ndiff = 0
    hdr = f"{'TICKER':6} {'DATE':11} {'STORED':6} " + " ".join(f"{n.upper():8}" for n in names) + " PPLX  flags"
    print(hdr)
    print("-" * len(hdr))
    for c in cases:
        t = c["ticker"]
        cat = c.get("catalyst") or ""
        grades = {}
        for name, model, _ in MODELS:
            try:
                q, a, i, o = grade(client, model, t, cat)
                grades[name] = (q, a)
                tok[name][0] += i
                tok[name][1] += o
            except Exception as e:
                grades[name] = ("ERR", str(e)[:50])
        qs = [grades[n][0] for n in names]
        diff = len({q for q in qs if q != "ERR"}) > 1
        if diff:
            ndiff += 1
        flags = ("DIFF " if diff else "") + ("WATCH" if t in WATCH else "")
        print(f"{t:6} {str(c['date']):11} {str(c.get('haiku')):6} " + " ".join(f"{q:8}" for q in qs) + f" {str(c.get('pplx')):5} {flags}")
        if t in WATCH:
            notable.append((t, c.get("haiku"), dict(grades)))

    print(f"\n=== COST (this run, N={len(cases)} cases) ===")
    for name, model, (pi, po) in MODELS:
        ci = tok[name][0] / 1e6 * pi
        co = tok[name][1] / 1e6 * po
        print(f"  {name:7}: in={tok[name][0]} out={tok[name][1]} total=${ci+co:.4f} per-grade=${(ci+co)/max(1,len(cases)):.5f}")

    print(f"\n=== WATCH cases (text says no/weak catalyst; PRODUCTION Haiku stored 'strong') ===")
    for t, sh, grades in notable:
        gl = " | ".join(f"{n}={grades[n][0]}" for n in names)
        print(f"  {t}: stored_prod_haiku={sh} || {gl}")
        sa = grades.get("sonnet", ("", ""))[1]
        if sa:
            print(f"     sonnet rationale: {sa[:200]}")

    print(f"\n=== cross-model disagreements: {ndiff}/{len(cases)} ===")


if __name__ == "__main__":
    main()
