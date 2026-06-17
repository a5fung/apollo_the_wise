#!/usr/bin/env python3
"""#187/#190 decisive validation (READ-ONLY): does adding the SEC 8-K to the grounded
summary flip RUM from 'routine' (the miss) to 'strong' (the real trade) on Sonnet?
Grades RUM two ways on claude-sonnet-4-6 via the production catalyst prompt:
  (a) Perplexity-only summary  -> expect routine (the current failure)
  (b) Perplexity + SEC 8-K body -> expect strong/game_changer (recall recovered)
Also NVTS as a control (had a real catalyst). No DB writes, no trade state.
"""
import datetime
import re

import anthropic
import httpx

SONNET = "claude-sonnet-4-6"
UA = {"User-Agent": "Apollo Research lastone99@gmail.com", "Accept-Encoding": "gzip, deflate"}

# Stored Perplexity `catalyst` summaries (from mi_ep_alerts, 6/4 / 6/3).
PPLX = {
    "RUM": ("RUM's latest gap-up catalyst is not clearly identified in the results you provided. "
            "The only Rumble-specific item here is an article saying Rumble was trading down and that "
            "its move was not tied to a fresh company-specific catalyst; it also references the stock's "
            "year-to-date strength, but not a new news driver for the gap."),
    "NVTS": ("Navitas Semiconductor (NVTS) has been gapping up on a mix of structural and fundamental "
             "catalysts tied to its AI power-semiconductor pivot, removal of an equity overhang, and a "
             "short-covering dynamic."),
}

_CATALYST_TOOL = {
    "name": "classify_catalyst",
    "description": "Classify the quality of a stock EP catalyst and provide analysis.",
    "input_schema": {"type": "object", "properties": {
        "quality": {"type": "string", "enum": ["game_changer", "strong", "routine", "mna"],
                    "description": ("game_changer: massive earnings beat + guidance raise, FDA approval, "
                                    "transformative contract. strong: solid beat + guidance raise, analyst upgrade "
                                    "cluster, major partnership. routine: in-line results, no company-specific "
                                    "catalyst. mna: being acquired — price capped, no momentum trade.")},
        "analysis": {"type": "string", "description": "2-3 sentences on the specific catalyst + rationale."},
    }, "required": ["quality", "analysis"]},
}


def _strip(html):
    t = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t.replace("&#160;", " ").replace("&nbsp;", " ")).strip()


def fetch_8k_body(client, ticker):
    tk = client.get("https://www.sec.gov/files/company_tickers.json").json()
    cik = next((str(r["cik_str"]).zfill(10) for r in tk.values() if str(r["ticker"]).upper() == ticker), None)
    if not cik:
        return ""
    sub = client.get(f"https://data.sec.gov/submissions/CIK{cik}.json").json()
    r = sub["filings"]["recent"]
    for i, f in enumerate(r["form"]):
        if f.startswith("8-K") and r["filingDate"][i] >= (datetime.date.today() - datetime.timedelta(days=7)).isoformat():
            acc = r["accessionNumber"][i].replace("-", "")
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{r['primaryDocument'][i]}"
            return _strip(client.get(url).text)[:4000]
    return ""


def build_prompt(ticker, news_text):
    return f"""You are analyzing a stock gap-up for EP (Episodic Pivot) trading.
This stock is gapping up significantly in pre-market. Your job is to identify the catalyst.

Stock: {ticker}
Recent news (may include earnings, guidance, contracts, upgrades, SEC filings):
{news_text or "No news found."}

IMPORTANT RULES:
1. Look for: earnings releases, guidance raises, FDA decisions, major contracts, analyst upgrades.
2. An earnings beat with guidance raise on a neglected stock = game_changer or strong.
3. Merger/acquisition/buyout/tender/going-private = "mna" (hard skip, price capped).
4. Grade broad SECTOR-MOMENTUM / SHORT-SQUEEZE / non-company-specific technical moves as "routine".

CRITICAL — VERIFY THE CATALYST IS REAL:
- Vague/generic news with no specific numbers/dates/sources -> "routine".
- If nothing clearly explains WHY the stock gapped -> "routine".
- State the SPECIFIC catalyst; if you cannot identify a concrete, verifiable one, say so."""


def grade(client, ticker, news_text):
    r = client.messages.create(model=SONNET, max_tokens=300, tools=[_CATALYST_TOOL],
                               tool_choice={"type": "tool", "name": "classify_catalyst"},
                               messages=[{"role": "user", "content": build_prompt(ticker, news_text)}])
    b = next(x for x in r.content if x.type == "tool_use")
    return b.input["quality"], b.input.get("analysis", "")


def main():
    ac = anthropic.Anthropic()
    with httpx.Client(headers=UA, timeout=25, follow_redirects=True) as hc:
        for ticker in ("RUM", "NVTS"):
            pplx = PPLX.get(ticker, "")
            body = fetch_8k_body(hc, ticker)
            q_only, a_only = grade(ac, ticker, pplx)
            grounded = (f"[SEC 8-K excerpt] {body}\n\n[Web summary] {pplx}" if body else pplx)
            q_g, a_g = grade(ac, ticker, grounded)
            print(f"\n===== {ticker} (8-K body chars: {len(body)}) =====")
            print(f"  Perplexity-only   -> {q_only}")
            print(f"  Perplexity + 8-K  -> {q_g}")
            print(f"  grounded rationale: {a_g[:240]}")


if __name__ == "__main__":
    main()
