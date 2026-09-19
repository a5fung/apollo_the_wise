#!/usr/bin/env python3
"""#188 model-eval, MATERIALITY slice (READ-ONLY; NO DB writes, NO trade state).

The 6/4 grade-task eval (eval_catalyst_models.py) showed Haiku/Sonnet/Opus CONVERGE
on the grade-the-summary task — but it ran on an earnings-heavy cohort, where
materiality rule 5 (deal magnitude vs company size) barely fires. So it never
tested the materiality JUDGMENT. This script tests exactly that, on Sonnet vs Opus
(the two candidates for the hard reasoning task), using the CURRENT production
prompt (materiality rule 5 + market-cap anchor + grounded-text path).

MEASUREMENT DESIGN (advisor 2026-06-05 — cohort validity is the whole ballgame):
  - Controlled synthetic sweep: hold a deal-type catalyst CONSTANT, sweep market
    cap so the SAME ${deal} is 100% / 20% / 5% / 1% / 0.2% of cap. This forces the
    materiality lever and over-weights the ambiguous mid-band (5-20%).
  - Ground-truth-FREE discriminator = MONOTONICITY: as deal/cap ratio falls, the
    grade ordinal (game_changer 3 >= strong 2 >= routine 1) must be NON-INCREASING.
    A non-monotonic model is demonstrably worse — needs no external labels.
  - Two real #189 anchors (RUM 270M@2.5B ~10.8% -> strong; @600B ~0.045% -> routine).

DECISION TREE (locked before running):
  - Both monotonic AND agree on the strong->routine boundary within one step
      => CONVERGE -> default Sonnet (cheap; convergence extends to materiality).
  - Opus monotonic, Sonnet noisy / non-monotonic / fuzzier boundary
      => quality edge to Opus -> CHANGE_PROCESS candidate for the grade path
         (note the 5x cost: $3/$15 -> $15/$75 per 1M tok).
  - Both non-monotonic => the materiality RULE/PROMPT is the weak link (feeds #189
    prompt refinement), NOT a model swap.
  - Mid-band (5-20%) disagreements => tabulate for operator labels (the judgment zone).

OUTPUT IS A RELATIVE MODEL RANKING, not "the correct materiality grades." Whether
#189 fires correctly in production is Monday's separate verify gate (#200/#173 class).

Run (server, read-only): docker exec apollo-market python scripts/eval_materiality_models.py
"""
import os

import anthropic

# (label, model_id, ($/1M in, $/1M out)) — the two hard-reasoning candidates.
MODELS = [
    ("sonnet", "claude-sonnet-4-6", (3.00, 15.00)),
    ("opus", "claude-opus-4-8", (15.00, 75.00)),
]

_ORD = {"game_changer": 3, "strong": 2, "routine": 1, "mna": 0, "ERR": -1}

# Production tool (ep_detector._CATALYST_TOOL), verbatim.
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


def _mktcap_str(mc: float) -> str:
    return f"${mc / 1e9:.1f}B" if mc >= 1e9 else f"${mc / 1e6:.0f}M"


def build_prompt(ticker, company, sector, mc, desc, news_text):
    """EXACT copy of ep_detector._classify_catalyst_claude prompt (lines ~342-380)."""
    return f"""You are analyzing a stock gap-up for EP (Episodic Pivot) trading.
This stock is gapping up significantly in pre-market. Your job is to identify the catalyst.

Stock: {ticker}
Company: {company} — {sector}
Market cap: {_mktcap_str(mc)}
Description: {desc}

Recent news (may include earnings announcements, guidance, contracts, upgrades):
{news_text or "No news found."}

IMPORTANT RULES:
1. Look for: earnings releases, guidance raises, FDA decisions, major contracts, analyst upgrades.
2. An earnings beat with guidance raise on a neglected stock = game_changer or strong.
3. If the catalyst is a MERGER, ACQUISITION, BUYOUT, TAKEOVER, TENDER OFFER, GOING-PRIVATE, or any
   deal where the company is being acquired — classify as "mna". This is a hard skip: price is capped
   at deal value, there is no momentum trade. Keywords: "definitive agreement", "to be acquired",
   "tender offer", "going private", "taken private", "strategic transaction", "buyout", "merger agreement".
4. Broad SECTOR-MOMENTUM, SHORT-SQUEEZE, or non-company-specific technical moves with no concrete
   company event = "routine" (a gap-up alone is not a catalyst).
5. MATERIALITY — weigh the catalyst's magnitude RELATIVE to the company (market cap above). A contract,
   deal, or order is game_changer/strong ONLY if its value is SIGNIFICANT vs the company's size (a
   meaningful fraction of market cap / revenue); a small or routine-sized deal for the company's scale
   is "routine" however positively worded.

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


# Deal-type catalyst templates — magnitude is the ONLY lever (no earnings numbers,
# so rules about fabricated-earnings don't confound; the deal is concrete + verifiable).
TEMPLATES = [
    ("contract",
     "{co} announced a definitive multi-year contract to supply its flagship product "
     "to a major commercial customer, valued at ${dv} million over the contract term. "
     "The company described it as a significant commercial win and provided the customer "
     "name, signing date, and total contract value in the announcement."),
    ("order",
     "{co} received a firm ${dv} million purchase order — described as its largest single "
     "order to date — for delivery over the next four quarters. The order was confirmed in "
     "a press release with the customer named and a stated delivery schedule."),
    ("award",
     "{co} was awarded a ${dv} million government program contract following a competitive "
     "procurement, with work beginning next quarter. The award notice included the program "
     "name, award date, and total ceiling value."),
]

DEAL_VALUE_M = 250  # held constant across the sweep
# market caps chosen so the SAME $250M deal lands at these ratios of market cap:
CAP_SWEEP = [
    250e6,    # 100%   -> unambiguously material
    1.25e9,   # 20%    -> material
    5e9,      # 5%     -> boundary (judgment zone)
    25e9,     # 1%     -> immaterial
    125e9,    # 0.2%   -> clearly immaterial
]

SECTOR = "Industrials"
DESC = "A mid-cap company that designs and manufactures specialized equipment for commercial and government customers."

# Real #189 anchors (validated 6/4): same RUM-style $270M cloud/GPU deal at two caps.
ANCHORS = [
    ("RUM_small", "Rumble Inc.", "Communication Services", 2.5e9,
     "Rumble announced a definitive agreement under which a major customer committed to "
     "purchase dedicated GPU cloud capacity from Rumble powered by NVIDIA Blackwell B300 "
     "systems, in a deal the company valued at approximately $270 million.", "strong"),
    ("RUM_mega", "MegaCorp (hypothetical)", "Communication Services", 600e9,
     "MegaCorp announced a definitive agreement under which a customer committed to "
     "purchase dedicated GPU cloud capacity powered by NVIDIA Blackwell B300 systems, "
     "in a deal valued at approximately $270 million.", "routine"),
]


def grade(client, model, ticker, company, sector, mc, desc, news):
    r = client.messages.create(
        model=model, max_tokens=300, tools=[_CATALYST_TOOL],
        tool_choice={"type": "tool", "name": "classify_catalyst"},
        messages=[{"role": "user", "content": build_prompt(ticker, company, sector, mc, desc, news)}],
    )
    tb = next(b for b in r.content if b.type == "tool_use")
    return tb.input["quality"], tb.input.get("analysis", ""), r.usage.input_tokens, r.usage.output_tokens


def _ratio_str(dv_m, mc):
    return f"{dv_m * 1e6 / mc * 100:.2g}%"


def main():
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    tok = {n: [0, 0] for n, _, _ in MODELS}
    names = [n for n, _, _ in MODELS]

    print("=" * 78)
    print("#188 MATERIALITY model eval — Sonnet vs Opus on the deal-magnitude lever")
    print(f"Constant deal = ${DEAL_VALUE_M}M; market cap swept so ratio varies. "
          f"Monotonicity = ground truth.")
    print("=" * 78)

    # ---- synthetic sweep ----
    mono = {n: [] for n in names}  # per-template ordinal sequences (cap ascending)
    boundary = {n: {} for n in names}  # template -> first ratio that drops below 'strong'
    for tlabel, tmpl in TEMPLATES:
        print(f"\n### template={tlabel}  (deal held at ${DEAL_VALUE_M}M)")
        hdr = f"{'cap':>8} {'ratio':>7} " + " ".join(f"{n:>12}" for n in names)
        print(hdr); print("-" * len(hdr))
        seqs = {n: [] for n in names}
        for mc in CAP_SWEEP:
            row = {}
            for n, model, _ in MODELS:
                try:
                    q, a, i, o = grade(client, model, "SYNTH", "SynthCo", SECTOR, mc, DESC,
                                       tmpl.format(co="SynthCo", dv=DEAL_VALUE_M))
                    tok[n][0] += i; tok[n][1] += o
                except Exception as e:
                    q, a = "ERR", str(e)[:40]
                row[n] = (q, a)
                seqs[n].append(_ORD[q])
                if _ORD[q] <= _ORD["routine"] and tlabel not in boundary[n]:
                    boundary[n][tlabel] = _ratio_str(DEAL_VALUE_M, mc)
            print(f"{_mktcap_str(mc):>8} {_ratio_str(DEAL_VALUE_M, mc):>7} "
                  + " ".join(f"{row[n][0]:>12}" for n in names))
        for n in names:
            mono[n].append((tlabel, seqs[n]))

    # ---- real anchors ----
    print(f"\n### real #189 anchors (expected: small->strong, mega->routine)")
    hdr = f"{'case':>10} {'cap':>8} {'ratio':>7} {'expect':>8} " + " ".join(f"{n:>12}" for n in names)
    print(hdr); print("-" * len(hdr))
    for label, co, sec, mc, news, expect in ANCHORS:
        row = {}
        for n, model, _ in MODELS:
            try:
                q, a, i, o = grade(client, model, label.split("_")[0], co, sec, mc, DESC, news)
                tok[n][0] += i; tok[n][1] += o
            except Exception as e:
                q, a = "ERR", str(e)[:40]
            row[n] = q
        print(f"{label:>10} {_mktcap_str(mc):>8} {_ratio_str(270, mc):>7} {expect:>8} "
              + " ".join(f"{row[n]:>12}" for n in names))

    # ---- monotonicity verdict (cap ASCENDING => ordinal must be NON-INCREASING) ----
    print(f"\n=== MONOTONICITY (grade must be non-increasing as cap rises / ratio falls) ===")
    for n in names:
        viols = []
        for tlabel, seq in mono[n]:
            ok = all(seq[k] >= seq[k + 1] for k in range(len(seq) - 1))
            if not ok:
                viols.append(f"{tlabel}:{seq}")
        verdict = "MONOTONIC ✓" if not viols else f"VIOLATIONS: {', '.join(viols)}"
        print(f"  {n:7}: {verdict}")
    print(f"\n=== strong->routine BOUNDARY (first ratio graded <= routine, per template) ===")
    for n in names:
        print(f"  {n:7}: {boundary[n]}")

    print(f"\n=== COST (this run) ===")
    for n, model, (pi, po) in MODELS:
        c = tok[n][0] / 1e6 * pi + tok[n][1] / 1e6 * po
        print(f"  {n:7}: in={tok[n][0]} out={tok[n][1]} total=${c:.4f}")


if __name__ == "__main__":
    main()
