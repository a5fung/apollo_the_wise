"""ADR 0007 §4 step 2 — isolated theme-discovery GROUPING test (read-only, local).

Question: once the drone cohort is ASSEMBLED into the candidate pool (i.e. after the
three assembly gates — rank-cap, covered-Fading, missing-description — are fixed), does
the REAL discovery LLM form ONE cross-sector drone/defense theme, or fragment by sector?

This is a SELF-CONTAINED experiment: it copies the real discovery prompt template
(theme_engine.py:2477-2512) + the real _THEME_DISCOVERY_TOOL schema (theme_engine.py:1899)
+ the real model (THEME_MODEL = claude-sonnet-4-6), and feeds a faithful candidate mix
(6 drone leaders + 10 unrelated bull-bounce "noise" names from the 84-name accelerator
set on 5/28). NO prod imports, NO DB, NO writes. Descriptions for UMAC/SWMR/KTOS are
verbatim from mi_ticker_overrides; RCAT/AVAV/ONDS + noise are faithful one-liners.

PASS  = one coherent drone/defense theme grouping the 6 cross-sector (Tech+Industrials)
        drone names, noise left uncovered.
FAIL  = fragments the drones by sector, or sweeps noise in, or misses them.
"""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(REPO / ".env")
    except Exception:
        pass


THEME_MODEL = "claude-sonnet-4-6"  # theme_engine.py:71

# Real tool schema — copied verbatim from theme_engine.py:1899
_THEME_DISCOVERY_TOOL = {
    "name": "report_themes",
    "description": "Report newly discovered investment themes from RS leader stocks.",
    "input_schema": {
        "type": "object",
        "properties": {
            "analysis_scratchpad": {
                "type": "string",
                "description": (
                    "REQUIRED. Write your clustering reasoning BEFORE proposing themes. "
                    "For each candidate group: (1) what shared catalyst or business model connects them, "
                    "(2) which stocks clearly belong vs. are borderline, (3) whether the group is large "
                    "enough (>=3 stocks) and coherent enough to name. Reject spurious clusters here."
                ),
            },
            "themes": {
                "type": "array",
                "description": "List of newly discovered themes. Empty array if none found.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Specific theme name e.g. 'Edge AI Inference', not 'Technology'"},
                        "thesis": {"type": "string", "description": "2-3 sentences on what's driving this theme and why now."},
                        "tickers": {"type": "array", "items": {"type": "string"},
                                    "description": "Ticker symbols belonging to this theme (minimum 3 — do not include stocks that don't clearly fit)."},
                    },
                    "required": ["name", "thesis", "tickers"],
                },
            },
        },
        "required": ["analysis_scratchpad", "themes"],
    },
}

# Candidate mix: 6 drone leaders (cross-sector) + 10 unrelated 5/28 accelerator "noise".
# (ticker, RS, rank, sector, description). RS/rank from the 5/28 prod trace.
STOCKS = [
    # --- drone / defense cohort (the signal) ---
    ("UMAC", 99, 50,   "Technology",  "Commercial drones, drone components"),                      # verbatim (overrides)
    ("SWMR", 99, 57,   "Technology",  "Autonomous drone swarm software, military AI"),             # verbatim
    ("KTOS", 33, 2666, "Industrials", "Defense aerospace technology, hardware, software"),         # verbatim
    ("RCAT", 59, 1619, "Technology",  "Red Cat Holdings — military and commercial drone systems (Teal/FANG UAS)"),
    ("AVAV", 64, 1433, "Industrials", "AeroVironment — military unmanned aircraft systems and loitering munitions"),
    ("ONDS", 90, 412,  "Technology",  "Ondas Holdings — commercial and defense drone platforms and wireless networks"),
    # --- unrelated bull-bounce accelerators (the noise it must reject) ---
    ("KSS",  72, 1109, "Consumer",      "Kohl's — department store retailer"),
    ("DLTR", 67, 1312, "Consumer",      "Dollar Tree — discount variety retail"),
    ("HOOD", 70, 1187, "Financials",    "Robinhood — retail brokerage / trading app"),
    ("BROS", 71, 1171, "Consumer",      "Dutch Bros — drive-thru coffee chain"),
    ("UPST", 71, 1170, "Financials",    "Upstart — AI consumer-lending marketplace"),
    ("QFIN", 77, 933,  "Financials",    "Qifu Technology — Chinese consumer-credit fintech platform"),
    ("RDDT", 61, 1572, "Communication", "Reddit — social media platform"),
    ("TPR",  77, 937,  "Consumer",      "Tapestry — Coach / Kate Spade luxury accessories"),
    ("ICLR", 70, 1184, "Healthcare",    "ICON plc — clinical research outsourcing (CRO)"),
    ("AMPX", 94, 247,  "Industrials",   "Amprius — silicon-anode lithium-ion batteries for EV/mobility"),
]


def _build_prompt() -> str:
    lines = "\n".join(
        f"- {t} (RS {rs:.0f}, rank #{rk}, sector: {sec} — {desc})"
        for (t, rs, rk, sec, desc) in STOCKS
    )
    # Prompt template copied from theme_engine.py:2477-2512 (uncovered-leaders path).
    return f"""You are a market intelligence analyst using Marios Stamatoudis's theme discovery methodology.

Themes emerge BOTTOM-UP from price action. The real alpha is finding sub-themes BEFORE they become common knowledge.

RS LEADERS NOT YET IN ANY ACTIVE THEME:
{lines}

Task: Identify NEW distinct investment themes from ALL the stocks above.

Use the company descriptions to understand what each stock actually does. Two stocks in the same "sector" may serve completely different markets. Conversely, stocks in different sectors may share a specific catalyst (e.g., a memory chip maker and an equipment company both driven by HBM demand).

Rules:
- A theme REQUIRES at least 2 stocks — a 2-stock cluster is valid as a "Nascent" early signal
- Every stock must clearly operate in the SAME specific sub-industry or share the SAME business driver
  - GOOD: DRAM/NAND memory makers, optical networking equipment, uranium miners, AI inference chips
  - BAD: mixing a REIT with a commodity stock, adding a consumer name to an industrial theme
  - BAD: grouping by vague similarity ("they're both tech", "both benefit from AI")
- Name themes specifically ("AI Memory & HBM" not "Technology" or "Semiconductors")
- When in doubt whether a stock belongs — exclude it. A smaller, correct theme beats a larger, wrong one.
- Return zero themes if no clear cluster exists — that is the correct answer
- Focus on what the market is pricing in RIGHT NOW based on price action, not macro narratives

Call report_themes with your clustering reasoning in analysis_scratchpad first."""


async def main() -> int:
    _load_env()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not found (env or .env)", file=sys.stderr)
        return 1
    import anthropic
    client = anthropic.AsyncAnthropic()
    prompt = _build_prompt()
    print(f"Calling {THEME_MODEL} with {len(STOCKS)} candidates (6 drone + 10 noise)...\n")
    resp = await client.messages.create(
        model=THEME_MODEL,
        max_tokens=4000,
        tools=[_THEME_DISCOVERY_TOOL],
        tool_choice={"type": "tool", "name": "report_themes"},
        messages=[{"role": "user", "content": prompt}],
    )
    print(f"[diag] stop_reason={resp.stop_reason} usage={resp.usage}")
    block = next((b for b in resp.content if b.type == "tool_use"), None)
    if not block:
        print("No tool_use returned. content=", resp.content); return 1
    out = block.input
    print(f"[diag] raw tool input:\n{json.dumps(out, indent=2)[:2000]}\n")
    print("=" * 78)
    print("ANALYSIS SCRATCHPAD:\n" + (out.get("analysis_scratchpad") or "(none)"))
    print("=" * 78)
    drones = {"UMAC", "SWMR", "KTOS", "RCAT", "AVAV", "ONDS"}
    for th in out.get("themes", []):
        tk = th.get("tickers", [])
        d = sorted(set(tk) & drones); n = sorted(set(tk) - drones)
        print(f"\nTHEME: {th.get('name')}")
        print(f"  thesis: {th.get('thesis')}")
        print(f"  tickers: {tk}")
        print(f"  -> drone members: {d}   non-drone: {n}")
    print("\n" + "=" * 78)
    print(f"drone names: {sorted(drones)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
