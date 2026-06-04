#!/usr/bin/env python3
"""#187 B1 prototype (READ-ONLY; public SEC API). Proves the get_sec_recent_filings shape that
will port into collector.py: ticker -> CIK -> submissions -> recent 8-Ks (items + primary-doc text
snippet). Confirms RUM's 6/4 8-K is the $270M NVIDIA-Blackwell deal — the catalyst we were blind to.
"""
import datetime
import re

import httpx

UA = {"User-Agent": "Apollo Research lastone99@gmail.com", "Accept-Encoding": "gzip, deflate"}


def _strip_html(html: str) -> str:
    txt = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    txt = re.sub(r"(?s)<[^>]+>", " ", txt)
    txt = re.sub(r"&#160;|&nbsp;", " ", txt)
    txt = re.sub(r"\s+", " ", txt)
    return txt.strip()


def get_sec_recent_filings(client, ticker, cik_map, forms=("8-K",), lookback_days=4, want_text=True):
    """Recent SEC filings of the given forms for `ticker`, via the near-real-time submissions endpoint."""
    cik = cik_map.get(ticker.upper())
    if not cik:
        return []
    sub = client.get(f"https://data.sec.gov/submissions/CIK{cik}.json").json()
    r = sub["filings"]["recent"]
    cutoff = (datetime.date.today() - datetime.timedelta(days=lookback_days)).isoformat()
    out = []
    for i, form in enumerate(r["form"]):
        if not any(form.startswith(f) for f in forms):
            continue
        if r["filingDate"][i] < cutoff:
            continue
        acc_no = r["accessionNumber"][i].replace("-", "")
        primary = r["primaryDocument"][i]
        doc_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no}/{primary}"
        rec = {
            "form": form,
            "filed": r["filingDate"][i],
            "accepted": r.get("acceptanceDateTime", [""] * len(r["form"]))[i],
            "items": r.get("items", [""] * len(r["form"]))[i],
            "doc_url": doc_url,
        }
        if want_text:
            try:
                # The 8-K body (item text + disclosure) is in the PRIMARY iXBRL doc; the catalyst
                # content sits AFTER the cover/XBRL header, so search the FULL stripped text.
                full = _strip_html(client.get(doc_url).text)
                rec["text_len"] = len(full)
                rec["hits"] = re.findall(
                    r"[^.]{0,50}(?:\$\s?\d[\d,.]*\s*(?:million|billion)|NVIDIA|Blackwell|GPU|definitive agreement)[^.]{0,90}\.",
                    full, re.I)[:5]
                rec["text"] = full[:2500]
            except Exception as e:
                rec["text"] = f"(fetch err {e})"
        out.append(rec)
    return out


def main():
    with httpx.Client(headers=UA, timeout=25, follow_redirects=True) as c:
        tk = c.get("https://www.sec.gov/files/company_tickers.json").json()
        cik_map = {str(row["ticker"]).upper(): str(row["cik_str"]).zfill(10) for row in tk.values()}
        for ticker in ("RUM", "PGY"):  # RUM = known real catalyst; PGY = a no-catalyst control
            print(f"\n===== {ticker} recent 8-Ks (lookback 4d) =====")
            fils = get_sec_recent_filings(c, ticker, cik_map, lookback_days=4)
            if not fils:
                print("  (none in window)")
            for f in fils:
                print(f"  {f['form']} filed={f['filed']} acc={f['accepted']} items={f['items']}")
                print(f"  url={f['doc_url']}")
                print(f"  text_len={f.get('text_len')}")
                hits = f.get("hits") or []
                if hits:
                    print(f"  >>> catalyst hits (full-text): {' | '.join(h.strip()[:140] for h in hits)}")
                else:
                    print(f"  >>> NO catalyst keyword hits in primary doc; tail: ...{f.get('text','')[-300:]}")


if __name__ == "__main__":
    main()
