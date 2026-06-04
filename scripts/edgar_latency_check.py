#!/usr/bin/env python3
"""#187 B0 — EDGAR freshness check (READ-ONLY; public SEC API only; NO prod/DB/trade state).

Question: is EDGAR fresh enough that a same-day pre-market / prior-evening 8-K is retrievable
by the 9:31-9:45 ET scan? The full-text search index (efts.sec.gov) lags ~10-45 min; the
submissions endpoint (data.sec.gov/submissions/CIK.json) + the getcurrent feed are documented
near-real-time. Verify empirically before betting B1 on EDGAR.

Checks:
  1) RUM: ticker->CIK (company_tickers.json) -> submissions -> recent 8-Ks + acceptanceDateTime.
     Confirm the 6/3 $270M 8-K is present and see its acceptance timestamp.
  2) Freshness: EDGAR 'getcurrent' atom feed (type=8-K) -> newest accepted 8-Ks vs now -> lag(min).
"""
import datetime
import re

import httpx

# SEC mandates a descriptive User-Agent with contact info.
UA = {"User-Agent": "Apollo Research lastone99@gmail.com", "Accept-Encoding": "gzip, deflate"}


def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    print(f"now (UTC): {now.isoformat()}")
    with httpx.Client(headers=UA, timeout=25, follow_redirects=True) as c:
        # --- Check 1: RUM submissions (the near-real-time endpoint) ---
        try:
            tk = c.get("https://www.sec.gov/files/company_tickers.json").json()
            cik = None
            for row in tk.values():
                if str(row.get("ticker", "")).upper() == "RUM":
                    cik = str(row["cik_str"]).zfill(10)
                    break
            print(f"\nRUM CIK: {cik}")
            if cik:
                sub = c.get(f"https://data.sec.gov/submissions/CIK{cik}.json").json()
                r = sub["filings"]["recent"]
                forms, dates = r["form"], r["filingDate"]
                acc = r.get("acceptanceDateTime", [""] * len(forms))
                desc = r.get("primaryDocDescription", [""] * len(forms))
                print(f"  company: {sub.get('name')}")
                print("  recent 8-Ks (form | filed | accepted | desc):")
                n = 0
                for i, f in enumerate(forms):
                    if f.startswith("8-K"):
                        print(f"    {f:6} {dates[i]}  acc={acc[i]}  {desc[i][:45]}")
                        n += 1
                        if n >= 8:
                            break
        except Exception as e:
            print(f"  RUM submissions check FAILED: {type(e).__name__}: {e}")

        # --- Check 2: freshness via getcurrent 8-K feed ---
        print("\n--- EDGAR getcurrent 8-K feed (freshness vs now) ---")
        try:
            url = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent"
                   "&type=8-K&company=&dateb=&owner=include&count=15&output=atom")
            feed = c.get(url).text
            ups = re.findall(r"<updated>([^<]+)</updated>", feed)
            titles = re.findall(r"<title>([^<]+)</title>", feed)
            if ups:
                print(f"  feed <updated>: {ups[0]}")
                for u in ups[1:9]:
                    try:
                        t = datetime.datetime.fromisoformat(u.replace("Z", "+00:00"))
                        lag = (now - t).total_seconds() / 60.0
                        print(f"    entry accepted/updated={u}  lag={lag:6.1f} min")
                    except Exception as e:
                        print(f"    {u}  (parse err {e})")
                print(f"  sample titles: {titles[1:4]}")
            else:
                print(f"  no <updated> parsed; feed head: {feed[:300]}")
        except Exception as e:
            print(f"  getcurrent feed check FAILED: {type(e).__name__}: {e}")

    print("\nVERDICT GUIDE: if RUM's 6/3 8-K shows with an acceptanceDateTime, and the getcurrent")
    print("feed's newest 8-Ks have small lag (single-digit to ~teens of min), the submissions/")
    print("current endpoints are fresh enough for the morning scan -> build B1 on them.")


if __name__ == "__main__":
    main()
