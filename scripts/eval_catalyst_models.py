#!/usr/bin/env python3
"""#188 model-eval (READ-ONLY analysis; NO DB writes, NO trade state).

Re-grades stored EP catalyst summaries with Haiku (current) vs Sonnet-4-6 on the
IDENTICAL production classify_catalyst prompt/tool. Controlled same-input comparison:
feeds the stored `catalyst` summary (Perplexity's synthesized answer) to both models.

NOTE (fidelity caveat): production _classify_catalyst_claude feeds the RAW news list
(each item text[:200]); here we feed the stored summary to BOTH models, so this isolates
MODEL quality on identical input (not a reproduction of the exact production grade).

Reads cases from /tmp/cases.json (generated via psql json_agg). Prints a grade table,
the analyses for disagreements + known-failure tickers, and a cost tally.
"""
import json
import os

import anthropic

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"
PRICE = {HAIKU: (0.80, 4.00), SONNET: (3.00, 15.00)}  # $/1M tokens (in, out)
WATCH = {"RUM", "PGY", "CRSR", "DY", "POWI", "GRRR"}  # text-says-no-catalyst but Haiku said strong

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
    tok = {HAIKU: [0, 0], SONNET: [0, 0]}
    diffs = []
    notable = []
    print(f"{'TICKER':6} {'DATE':11} {'STORED':5} {'H2':5} {'SON':5} {'PPLX':5}  flags")
    print("-" * 60)
    for c in cases:
        t = c["ticker"]
        cat = c.get("catalyst") or ""
        try:
            hq, ha, hi, ho = grade(client, HAIKU, t, cat)
            sq, sa, si, so = grade(client, SONNET, t, cat)
        except Exception as e:
            print(f"{t:6} {str(c['date']):11} ERROR: {e}")
            continue
        tok[HAIKU][0] += hi; tok[HAIKU][1] += ho
        tok[SONNET][0] += si; tok[SONNET][1] += so
        flags = []
        if sq != hq:
            flags.append("H!=S")
            diffs.append((t, c["date"], c.get("haiku"), hq, sq, ha, sa))
        if t in WATCH:
            flags.append("WATCH")
            notable.append((t, c.get("haiku"), hq, sq, sa))
        print(f"{t:6} {str(c['date']):11} {str(c.get('haiku')):5} {hq:5} {sq:5} {str(c.get('pplx')):5}  {' '.join(flags)}")
    print()
    print("=== COST (this run, both models, N={}) ===".format(len(cases)))
    for m in (HAIKU, SONNET):
        ci = tok[m][0] / 1e6 * PRICE[m][0]
        co = tok[m][1] / 1e6 * PRICE[m][1]
        per = (ci + co) / max(1, len(cases))
        print(f"  {m}: in={tok[m][0]} out={tok[m][1]} total=${ci+co:.4f} per-grade=${per:.5f}")
    print(f"\n=== WATCH cases (text says no/weak catalyst; Haiku stored 'strong') ===")
    for t, sh, h2, s, sa in notable:
        print(f"  {t}: stored_haiku={sh} | rerun_haiku={h2} | SONNET={s}\n     sonnet: {sa[:240]}")
    print(f"\n=== Haiku-vs-Sonnet disagreements: {len(diffs)}/{len(cases)} ===")
    for t, d, sh, h2, s, ha, sa in diffs:
        print(f"  {t} {d}: rerun_haiku={h2} -> sonnet={s}")


if __name__ == "__main__":
    main()
