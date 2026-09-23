#!/usr/bin/env python3
"""#189 materiality validation (READ-ONLY): does adding market-cap + a materiality rule make the
grade discriminate by company size? Same RUM 8-K, two caps:
  (a) RUM real cap ~$2.5B  -> expect strong/game_changer ($270M deal is material)
  (b) synthetic $600B cap  -> expect routine ($270M is immaterial at mega-cap scale)
On claude-sonnet-4-6. No DB writes, no trade state.
"""
import datetime
import re

import anthropic
import httpx

SONNET = "claude-sonnet-4-6"
UA = {"User-Agent": "Apollo Research lastone99@gmail.com", "Accept-Encoding": "gzip, deflate"}

_CATALYST_TOOL = {
    "name": "classify_catalyst",
    "description": "Classify the quality of a stock EP catalyst and provide analysis.",
    "input_schema": {"type": "object", "properties": {
        "quality": {"type": "string", "enum": ["game_changer", "strong", "routine", "mna"]},
        "analysis": {"type": "string"},
    }, "required": ["quality", "analysis"]},
}


def _strip(html):
    t = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t.replace("&#160;", " ").replace("&nbsp;", " ")).strip()


def fetch_8k(client, ticker):
    tk = client.get("https://www.sec.gov/files/company_tickers.json").json()
    cik = next((str(r["cik_str"]).zfill(10) for r in tk.values() if str(r["ticker"]).upper() == ticker), None)
    sub = client.get(f"https://data.sec.gov/submissions/CIK{cik}.json").json()
    r = sub["filings"]["recent"]
    for i, f in enumerate(r["form"]):
        if f.startswith("8-K") and r["filingDate"][i] >= (datetime.date.today() - datetime.timedelta(days=7)).isoformat():
            acc = r["accessionNumber"][i].replace("-", "")
            return _strip(client.get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{r['primaryDocument'][i]}").text)[:4000]
    return ""


def build_prompt(ticker, mktcap_str, news_text):
    return f"""You are analyzing a stock gap-up for EP (Episodic Pivot) trading.

Stock: {ticker}
Market cap: {mktcap_str}
Recent news (incl. SEC filings):
{news_text}

RULES:
1. Earnings beat + guidance raise, FDA decision, major contract, analyst-upgrade cluster = strong/game_changer.
2. Merger/buyout/tender/going-private = "mna".
3. Vague / sector-momentum / short-squeeze / no concrete company event = "routine".
4. MATERIALITY — weigh the catalyst's magnitude RELATIVE to the company (market cap above). A contract/
   deal/order is game_changer/strong ONLY if its value is SIGNIFICANT vs the company's size (a meaningful
   fraction of market cap / revenue). A small or routine-sized deal for the company's scale is "routine"
   however positively worded.
State the specific catalyst; if none is concrete + material, say so."""


def grade(ac, ticker, mktcap_str, news_text):
    r = ac.messages.create(model=SONNET, max_tokens=300, tools=[_CATALYST_TOOL],
                           tool_choice={"type": "tool", "name": "classify_catalyst"},
                           messages=[{"role": "user", "content": build_prompt(ticker, mktcap_str, news_text)}])
    b = next(x for x in r.content if x.type == "tool_use")
    return b.input["quality"], b.input.get("analysis", "")


def main():
    ac = anthropic.Anthropic()
    with httpx.Client(headers=UA, timeout=25, follow_redirects=True) as hc:
        body = fetch_8k(hc, "RUM")
    grounded = f"[SEC 8-K] {body}"
    for label, cap in (("RUM real ~$2.5B", "$2.5B"), ("synthetic mega-cap", "$600B")):
        q, a = grade(ac, "RUM", cap, grounded)
        print(f"\n{label} ({cap}) -> {q}")
        print(f"  rationale: {a[:240]}")


if __name__ == "__main__":
    main()
