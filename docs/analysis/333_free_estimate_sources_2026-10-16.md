# #333 — free forward-estimate sources, re-read 2026-10-16 (delta on the 09-03 research)

**Decision this serves:** his ruling 2 of 2026-09-03 — *"research additional free earnings-estimate sources"* —
asked again six weeks later, after Finnhub was wired in and FMP was ruled out. Is there a free source that
backs up or replaces `yfinance`, and does anything free reach the four forward quarters the Pradeep
durability shape asks for? **Research only. Nothing signed up for, nothing deployed, no code changed.**
Builds on `docs/analysis/estimates_free_sources_333_2026-09-03.md` (do not re-read it for facts below; this
file supersedes its rankings) and `docs/analysis/analyst_estimates_coverage_accuracy_333_2026-09-03.md`.

**Status since writing (same day):** recommendation 1 was built. The FMP `/analyst-estimates` call is removed
(merged `cada77b1`), and the yfinance annual `0y`/`+1y` rows are stored from the frames already fetched; both
deploy Sat 10-17. The "21-26 FMP failure rows a night" figure was then measured in prod from the main loop
(`scripts/probes/_333_fmp_1016/q1.out`), so it is no longer only quoted.

## Method and population

- **Sources read:** each vendor's own machine-readable spec or pricing page where one exists (Finnhub
  `swagger.json`, Twelve Data OpenAPI, Alpha Vantage docs HTML, alpaca-py source listing), else search summaries,
  tagged CLAIM. Read 2026-10-16.
- **Live calls:** two only — Alpha Vantage `EARNINGS_ESTIMATES` on the public demo key (IBM, n = 1) and one
  keyless Nasdaq request (failed). No other source was called.
- **Coverage figures are not new:** every small-cap count below is the 09-03 measurement (7 named small caps,
  and the 176 live-alert tickers from `mi_analyst_estimates`, n = 176). Nothing in this file re-measures them.

## Bottom line

- **Nothing free reaches more than two forward quarters.** Every free source stops at the current quarter plus
  the next (`0q`, `+1q`) and the current plus next fiscal year (`0y`, `+1y`). The only source found with more is
  Finnhub's paid Estimate-2 plan (5 years forward, CLAIM below, about $200 a month). So the 60-day re-test
  (ruling 1) is a test of *two quarters plus the annual*, and that is the most any free route can deliver.
- **The annual half of ruling 1 is not actually being delivered.** The recorder stores yfinance's `0q`/`+1q`
  only, and leaves the annual rows to FMP (`_YF_QUARTER_PERIODS` comment: *"the annual leg's territory (FMP),
  never duplicated here"*). FMP's free tier served about 1 ticker in 12 and he has since ruled it out. The
  yfinance frames the recorder already downloads contain `0y`/`+1y` with analyst counts (7 of 7 on 09-03).
  **Storing them costs zero extra calls and removes the nightly FMP failure rows.**
- **Alpha Vantage is still the one free key worth getting**, but for a narrower reason than on 09-03: with
  Finnhub wired, it is the only free source that carries an analyst count AND a low/high range from a
  different vendor than yfinance — the two fields the 09-03 quality finding turned on.

## What changed since 09-03

| Then (09-03) | Now (10-16) |
|---|---|
| Finnhub ranked "disqualified, premium-walled" | Tested live with his key on 09-03: consensus endpoints 403, but `/calendar/earnings` returns forward revenue + EPS for 7 of 7 small caps; **wired as source #2** (`finnhub_calendar` rows). Re-verified in Finnhub's own spec today, below. |
| FMP was a candidate second source | Dead: free tier serves about 1 ticker in 12; he ruled *"i thought we fix this and don't use fmp, at least not any paid tier"* (09-06; earlier, 09-02: *"what FMP key, we don't have a sub"*). The annual call still runs and writes **21-26 failure rows a night since 10-07** (figure from the task brief; I could not read prod, see "What I could not do"). |
| Alpha Vantage "try first" | Never tested (no key). Still untested. |
| Six candidates | Added and checked: Twelve Data, TradingView screener, Nasdaq public endpoint, Financial Datasets, Benzinga add-ons (via Polygon/Massive), Zacks via Nasdaq Data Link. Terms of use now read for each. |

## Evidence tags

VERIFIED = vendor's own machine-readable spec/file read today, or a live call. CLAIM = vendor or third-party prose
I could not confirm against a spec or a call. INFERRED = reasoned from verified fields.

## Comparison

All forward-estimate columns are about *consensus* EPS and revenue by period. "n / spread" = does the response
carry an analyst count and a low/high range (our `n_analysts < 3 -> None` rule and the spread filter need them).

| Source | Forward EPS + revenue, how far | n / spread | Small/mid-cap coverage | Free-tier limits | Terms of use | API shape | Verdict |
|---|---|---|---|---|---|---|---|
| **yfinance** (running, primary) | Both. `0q`, `+1q`, `0y`, `+1y` — 2 quarters + 2 fiscal years. VERIFIED 09-03, 7 of 7 named small caps | Both (count, avg, low, high, yearAgo, growth) | VERIFIED 09-03: 7 of 7 named; 160 of 176 live-alert tickers pass n>=3. One known bad value (NRIX 21x high on 3 analysts) | None stated; scraped, so Yahoo can rate-limit by IP. Reported 429s from data-centre IPs (CLAIM, GitHub issues). Library last release 2026-08-26 (VERIFIED) | README: *"intended for research and educational purposes… the Yahoo! finance API is intended for personal use only"* (VERIFIED) | Python library, frames per period | **Keep primary.** Store the annual rows too |
| **Finnhub `/calendar/earnings`** (running, #2) | Both. About 2 quarters ahead (7 of 7, 09-03 live). Spec: *"Revenue estimate including Finnhub's proprietary estimates"*; *"sourced from both sell-side and buy-side analysts"* (VERIFIED) | **Neither.** Fields are `epsEstimate`, `revenueEstimate`, `quarter`, `year`, `hour`, `date` only (VERIFIED spec) | VERIFIED 09-03: 7 of 7 | Spec: `"freeTier": "1 month of historical earnings and new updates"` (VERIFIED) — **a risk flag**: the forward window we use could be tightened without notice. 60 calls/min (CLAIM, third-party) | *"All plan listed on Finnhub website is strictly for personal use unless explicitly stated otherwise… Personal plan can't be used by any business even internally"*; no redistribution (VERIFIED, ToS) | REST, `?token=` in query string | Keep as cross-check. Cannot replace yfinance (no count) |
| **Finnhub consensus endpoints** (`/stock/eps-estimate`, `/stock/revenue-estimate`) | Paid only. Spec tags both `"premium": "Premium Access Required"` (VERIFIED today; 403 on 7 of 7 live, 09-03). Estimate-1 about $75/mo/market, **1 quarter** forward; Estimate-2 about $200/mo/market, **5 years** forward (CLAIM — search excerpt of the vendor's JS-rendered pricing page; a third-party site instead says only a $3,500/mo all-in-one exists, so price is UNRESOLVED) | Count and range: yes — `numberAnalysts`, `epsHigh/epsLow`, `revenueHigh/revenueLow` (VERIFIED, response definitions in the spec today) | n/a | None | Same personal-use wording | REST, `?symbol=&freq=` | The only 4+ quarter source found. Paid; see needs_his_call |
| **Alpha Vantage `EARNINGS_ESTIMATES`** | Both. IBM via the vendor's public demo key today: furthest quarter row 2026-12-31 (= `+1q`), furthest year 2027-12-31; **no more than yfinance** (VERIFIED, IBM only) | **Both**, plus 7/30/60/90-day-ago EPS averages and up/down revision counts (VERIFIED, field list). Revenue has no look-back fields | **UNVERIFIED** — demo key authorises IBM only | **25 requests/day** *"covering the majority of our datasets"* (VERIFIED, vendor support page). 5/min (CLAIM). Docs tag this endpoint "Trending", not "Premium"; premium endpoints carry an explicit tip (VERIFIED, docs HTML) | Free key: *"personal, non-commercial use"*; commercial if you are affiliated with an investment adviser or broker-dealer, or use it on behalf of a firm (CLAIM — search summary of the ToS; the ToS is a PDF I could not parse here) | REST, `?function=EARNINGS_ESTIMATES&symbol=&apikey=`, JSON | **Try first** (email sign-up, no card). Role below |
| **EODHD** | Both via `/calendar/trends`; labels `0q`, `+1q`, `0y`, `+1y` (CLAIM — fetch summary) = same reach as yfinance | Count: yes. Low/high: yes (CLAIM) | CLAIM only | Free plan: 20 calls/day and the calendar is **not included**; trends need the $59.99/mo Fundamentals tier ($49.99 annual) (VERIFIED pricing page + CLAIM on tier) | "Personal plans" vs separate "Commercial / B2B" (VERIFIED) | REST | Not free |
| **Twelve Data** | `/earnings_estimate`, `/revenue_estimate`: both, quarterly + annual | Response fields not read (moot — gated) | Not testable | **Search results said the free Basic plan includes these. The vendor's own OpenAPI says `x-starting-plan: "ultra,enterprise"` for both** — Ultra is $999/mo (VERIFIED, spec + pricing page). Basic is *"Internal non-display usage"* only | Personal vs commercial licence split (VERIFIED) | REST | **Disqualified. The third-party claim was wrong.** |
| **TradingView screener** (unofficial `scanner` API) | Fields exist: `earnings_per_share_forecast_fq/_next_fq/_next_fy`, `revenue_forecast_fq/_next_fq/_next_fy`, `*_estimate_ntm` (VERIFIED, community field list) = same reach | **No per-estimate count or range.** Only `recommendation_total` (ratings count) and price-target fields | Unknown; not probed | Keyless, unofficial; ban risk noted by the library's own README | ToS: *"we do not permit commercial usage of any of our services or APIs"*; separately it forbids *"direct non-display usage"* and lists *"algorithmic decision-making"* among prohibited uses (quotes from a fetch summary of tradingview.com/policies — CLAIM until read in full) | POST JSON, 3,000+ fields | **Disqualified on terms** — feeding an algorithm is the forbidden case. He can keep using the site by eye |
| **Nasdaq.com public JSON** (`api.nasdaq.com/api/analyst/<T>/earnings-forecast`, Zacks-sourced) | UNVERIFIED. My recollection is EPS only (Zacks-sourced); I did not read its response, and a search turned up no spec | Unknown | Not tested | One keyless request with the default curl client failed (`HTTP/2 INTERNAL_ERROR`, no data). Works only for browser-like clients; I did not impersonate one | Site terms not read | n/a | **Not viable**: unofficial, blocks plain clients, revenue leg not confirmed |
| **Financial Datasets** (`financialdatasets.ai`) | Has an analyst-estimates endpoint | Not read | *"27,530 tickers"* (CLAIM) | **No free tier.** Pay-as-you-go: analyst estimates $0.10 a request; $20 one-time buys 1,000 requests; Personal $200/mo (CLAIM — search summary) | Redistribution rights only on $2,000/mo tier (CLAIM) | REST | Paid. 200 lookups for $20 would fund a one-off cross-check, not a nightly source |
| **Polygon / Massive** (current $33/mo plan) | Base plan: **none**. Benzinga *Earnings* add-on (`/benzinga/v1/earnings`) has `estimated_eps`, `estimated_revenue`, `fiscal_period`, `fiscal_year` — one record per report, **no analyst count** (VERIFIED, docs). Benzinga *Corporate Guidance* (`/benzinga/v1/guidance`) = company guidance ranges, updated every 2 hours | No count on earnings | n/a | Add-on, *"select Benzinga expansion plans"*; individual from about $99/mo (CLAIM — search summary) | n/a | REST | Wrong shape and extra money. Disqualified |
| **Alpaca** (current plan) | None. The official `alpaca-py` data package has clients only for corporate actions, crypto, news, options, screener, stocks (VERIFIED via GitHub listing of `alpaca/data/historical` and `alpaca/data/requests.py`) | n/a | n/a | n/a | n/a | n/a | No estimates product. Absence evidence only; the vendor docs fetch was blocked (below) |
| **Tiingo** | No estimates product found: fundamentals = statements and daily metrics (CLAIM — search + the 09-03 docs read) | n/a | n/a | n/a | n/a | n/a | Disqualified |
| **Zacks via Nasdaq Data Link** (ZEE/ZEEH tables) | Consensus earnings estimates, 5,000+ US/Canadian companies (CLAIM — search snippet) | Not read | Not read | Paid subscription; page would not render | n/a | Tables API | Paid; price not found |
| **FMP** | Free tier serves about 1 ticker in 12; `limit` must be 0-10; annual only | n/a | Measured 1 of 12 (his ruling and the PLAN line) | Search summaries claim the endpoint is on the free plan; **measurement overrides the marketing** — exactly the failure that started this | n/a | n/a | **Disqualified by measurement and by his ruling. Not re-raised.** |
| *Same upstream as yfinance, so not independent:* `yahooquery`, Yahoo's `quoteSummary` called directly, OpenBB's yfinance provider | — | — | — | — | — | — | Would remove the *library* as a failure point, not Yahoo |

## Corrections to what is on file

- **The PLAN #333 line says Finnhub's swagger contains the word "premium" zero times.** Re-fetched
  `https://finnhub.io/static/swagger.json` today (HTTP 200, 587,813 bytes): **208 occurrences**; the consensus
  endpoints are tagged `"premium": "Premium Access Required"`, and `/calendar/earnings` is `"premium": null`. That
  matches the 09-03 live 403s and the free calendar. The earlier zero came from a bad read, not the file.
- **Twelve Data:** the search-engine summary said the free plan includes the estimate endpoints. The vendor's spec
  says otherwise. Recorded here because it is the same "docs can be wrong" class that cost the FMP detour.
- **The 09-03 doc's Finnhub price (about $50+/mo)** does not match today's reading (Estimate-1 about $75,
  Estimate-2 about $200, or a $3,500 all-in-one per another site). Treat every Finnhub paid price as unresolved
  until someone reads the logged-in pricing page.

## Recommendation

1. **First, $0, no sign-up — a Sonnet-card build, not done here.** Store yfinance's `0y`/`+1y` rows (as
   `period_type='annual'`, `source='yfinance'`) from the frames the recorder already fetches, and stop calling
   FMP's `/analyst-estimates`. The annual period end needs an absolute date; the recorder already resolves
   EDGAR `fiscalYearEnd` for the Finnhub labels. This is data capture only (`estimate_for_scoring` is called by
   no live path, per its own docstring), so it does not touch scoring or money. Before dropping FMP, check who
   reads `fmp_stable` rows — my repo search for readers was blocked (below).
   - **Test (pre-registered):** after one night, annual yfinance rows exist for **>= 85%** of the tickers that
     have quarterly yfinance rows that night (the quarterly leg's own n>=3 rate was 91% on 09-03: 160 of 176, n = 176).
     **Would fail if:** the annual frames come back empty or all-NaN for thin-coverage names — the 7-of-7 on 09-03
     was a hand-picked sample of named tickers, not the population.
2. **Second, $0 but needs his email — one Alpha Vantage free key.** Role: a third voice stored beside yfinance
   and Finnhub, not a failover. It is the only free source with a count and a low/high that is not Yahoo. The 25
   per day cap does not block that role: the 09-03 coverage work flagged 5 of 176 names, 3% (n = 176; a wide
   spread or a disagreement), roughly 5 names a night (INFERRED), well inside 25.
   - **Test: 7 calls, same names as 09-03** (NRIX, AMLX, HTFL, SOLS, ETON, ABCL, UUUU). **Pass = both:**
     (a) >= 5 of 7 return a forward quarter row with `revenue_estimate_analyst_count >= 3`; **and**
     (b) the NRIX forward-quarter revenue average lands within 2x of Finnhub's stored value for the same period
     and nowhere near yfinance's (the known 21x error). (a) alone is satisfied by any source that returns
     something; (b) is the part a wrong source fails.
   - **Fail = either missing:** the free tier gates the function, counts are mostly under 3, or NRIX agrees with
     yfinance's bad number. Then stop shopping — free sources are exhausted and anything further is a paid decision.
3. **Do not buy anything now.** The only route to 4+ forward quarters is Finnhub Estimate-2, and nobody has
   measured whether two quarters fail to separate winners. That is what the 60-day re-test answers.

## What this does not answer

- **Whether two forward quarters are enough.** This file only says no free source reaches further; whether the
  extra reach would separate winners is the 60-day re-test's question.
- **Data quality for any new candidate.** Alpha Vantage, EODHD and Financial Datasets were not measured on small
  caps (no key); their coverage and accuracy rows are CLAIM or UNVERIFIED.
- **Non-US names**, and any vendor's real paid price (every Finnhub price is unresolved).

## What I could not do

- **Prod reads were denied by the permission classifier** (an ssh read of `mi_analyst_estimates` row counts per
  source per night and the FMP failure counts, and a repo grep for `fmp_stable` readers). I stopped. So the
  "21-26 a night" figure and the quarterly-row counts are quoted, not measured. A read-only follow-up for whoever
  can run it:
  `SELECT as_of_date, source, period_type, count(*), count(DISTINCT ticker) FROM mi_analyst_estimates WHERE as_of_date >= '2026-09-28' GROUP BY 1,2,3 ORDER BY 1 DESC,2,3;`
  A nightly drop in `yfinance` ticker count against `finnhub_calendar` would be the first real evidence on the
  single-point-of-failure worry.
- The fetch of `docs.alpaca.markets` was blocked by the same classifier; Alpaca's status rests on the SDK listing.
- **Keys and calls, disclosed:** one fetch of Alpha Vantage's `EARNINGS_ESTIMATES` using the vendor's published
  public `demo` key (IBM only) — the same call the 09-03 doc made; no account, no cost. One keyless request to
  Nasdaq's public endpoint (failed). Everything else was documentation or static spec files, no API calls.
- Alpha Vantage's ToS is a PDF I could not parse locally (no PDF tooling); its wording above is a search summary.
- No data-quality measurement for any new candidate, no non-US names, and no small-cap coverage for Alpha Vantage
  or EODHD — those need a key.

## Router note

No SSoT router row is required for this file: `tests/test_ssot_router_complete.py` only enforces finding-links for
`delayed_ep_reentry`, and this filename does not match. A one-line pointer on the PLAN #333 line is still the
right place so the next session finds it.
