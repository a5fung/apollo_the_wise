# Free earnings-estimates sources — a second source for #333, or confirmation there isn't one (2026-09-03)

**Decision this serves:** #333's forward-durability axis currently has exactly one data source —
`yfinance`, unofficial and scraped — feeding a nightly recorder that just started its ≥60-day
accrual clock. Operator, 2026-09-03: *"let's reserve time sometime to research additional free
sources for earnings estimates data."* This scopes that, alone: does a free (or already-paid)
source exist that would remove `yfinance` as a single point of failure, or beat it on horizon?
**No code changed. Nothing was signed up for.**

**What would change the decision:** a candidate that (a) returns forward consensus revenue AND
EPS, (b) covers small/mid-cap EP names — not just the S&P 500, the exact failure that killed FMP
— (c) carries an analyst count, and (d) is free or already covered by Polygon/Alpaca. If nothing
clears all four, the finding is "keep `yfinance`, stop shopping" — a null result, and a real one.

## Method / population

Six candidates checked against the four bars above: **Finnhub, Alpha Vantage, Tiingo, EODHD**
(named in the brief) plus **Polygon (rebranded "Massive.com") and Alpaca** (both already paid
subscriptions — checked first, since free-to-us is the cheapest possible answer). All docs read
2026-09-03. Live calls made where a vendor's own public demo/no-key surface allowed it, with no
account created and no credentials entered anywhere:

- **`yfinance` baseline, measured today, live, no key needed:** `Ticker(<t>).revenue_estimate` /
  `.earnings_estimate` for the seven small/mid-cap names named in the brief —
  **NRIX, AMLX, HTFL, SOLS, ETON, ABCL, UUUU** (n=7, today's snapshot only, not a historical
  window).
- **Finnhub:** pulled the vendor's own live OpenAPI spec (`finnhub.io/static/swagger.json`) and
  read the `eps-estimate` / `revenue-estimate` endpoint definitions directly — this is Finnhub's
  own machine-readable plan metadata, not a marketing page.
- **Alpha Vantage:** called `EARNINGS_ESTIMATES` live using the vendor's own published `demo` key
  (documented on their own docs page for anyone to try) against **IBM** — the only symbol the
  demo key is authorized for — then tried the same call against NRIX/ETON/UUUU/UNH/MU to test
  the boundary (all correctly refused: *"the demo API key is for demo purposes only"*).
- **Tiingo:** the static (non-JS) client-docs page at `tiingo-python.readthedocs.io` lists every
  fundamentals method; grepped for `estimate`/`analyst`/`consensus`/`forward` — zero matches. The
  live API reference at `tiingo.com` is a JS app this environment can't render, so this is the
  best available check, not a call against the API itself.
- **EODHD:** vendor pricing page (`eodhd.com/pricing`) plus its own product docs for the Earnings
  Trends fields.
- **Polygon/Massive, Alpaca:** vendor docs only (`massive.com/docs/...`, `docs.alpaca.markets`) —
  no key held for either that would unlock a paid add-on, so no live call was possible or needed
  to answer "does the CURRENT plan include this."

**n=7** small/mid-cap names for the yfinance measurement, **n=12** for the FMP figure carried
over from #333's PLAN.md line (not re-measured here). Every other cell below is a documentation
read, marked VERIFIED (vendor's own machine-readable spec or a live call), CLAIM (vendor prose,
unconfirmed), or INFERRED (reasoned from a verified field list, not a direct claim or call) — per
the operator's own discipline, a documented claim is never presented as a capability.

## Baseline, measured today: `yfinance` on the exact named population

| ticker | revenue_estimate periods | rev analyst n (0q/+1q/0y/+1y) | eps analyst n (0q/+1q/0y/+1y) |
|---|---|---|---|
| NRIX | 0q,+1q,0y,+1y | 3/3/4/4 | 3/3/4/4 |
| AMLX | 0q,+1q,0y,+1y | 11/11/11/10 | 8/8/8/8 |
| HTFL | 0q,+1q,0y,+1y | 8/8/9/9 | 8/8/8/8 |
| SOLS | 0q,+1q,0y,+1y | 6/6/7/7 | 6/6/7/7 |
| ETON | 0q,+1q,0y,+1y | 4/4/4/4 | **2/2/2/2** |
| ABCL | 0q,+1q,0y,+1y | 7/7/8/7 | 3/3/5/4 |
| UUUU | 0q,+1q,0y,+1y | 3/3/6/5 | 3/3/4/2 |

**VERIFIED, n=7: 7 of 7 named small/mid-cap alert-style tickers returned non-empty forward
revenue AND EPS estimates with an analyst count, today, for $0, no key.** Only ETON's EPS leg
sits below the `n_analysts < 3 → None` floor (2 analysts) — its revenue leg clears it. This is
the number a second source has to beat, not FMP's 1-of-12: on this exact population `yfinance`
is already at 7-of-7.

## Candidate findings

| vendor | forward horizon | revenue + EPS? | analyst count? | small/mid-cap coverage | free-tier call limit | cost if not free | status |
|---|---|---|---|---|---|---|---|
| **Alpha Vantage** | 0q/+1q + 0y/+1y (same reach as yfinance; IBM's furthest quarterly row is 2026-12-31) | Yes, both, live-verified on IBM | Yes — `eps_estimate_analyst_count` / `revenue_estimate_analyst_count`, plus 7/30/60/90-day revision deltas yfinance doesn't have | **UNVERIFIED** — demo key only authorizes IBM | **25 requests/day** (CLAIM, widely reported) — covers ~25 of the ~100 names/night, not all | ~$50/mo removes the daily cap (CLAIM — third-party pricing summary; vendor's own plan tiers are quoted in requests/minute, not re-verified here as a $ figure) | Real candidate, capped |
| **EODHD** | CLAIM: "Trend" fields include forward periods with analyst count (`earningsEstimateAvg/Low/High`, `revenueEstimateAvg`) | Claimed yes | Claimed yes | CLAIM: 11,000 US tickers, "minor companies" get 10 years of history — reads better-documented than FMP's S&P-500-only reality, but untested | Free plan is **20 calls/day, fundamentals excluded entirely** | **$59.99/mo minimum** for the tier that includes fundamentals/estimates at all | Not free; unverified |
| **Finnhub** | CLAIM: quarterly/annual periods, sample shows historical quarters back to 2017 | Yes, both — confirmed by the vendor's own field list (`epsAvg/epsHigh/epsLow`, `revenueAvg/High/Low`) | Yes — `numberAnalysts` field, confirmed in the same spec | Not reachable to test — gated before any call | Free tier has **60 calls/minute but the endpoint itself is walled off** | **VERIFIED via Finnhub's own API spec: `"premium": "Premium Access Required"` on both `/stock/eps-estimate` and `/stock/revenue-estimate`.** ~$50+/mo per the vendor's pricing page | Disqualified — not available on free tier at any rate limit |
| **Tiingo** | n/a | **No product found** — fundamentals = reported daily metrics + quarterly/annual statements only (CLAIM: absence, not a call) | n/a | n/a | n/a | n/a | Disqualified — doesn't sell this data category |
| **Polygon / Massive.com** (current $33/mo sub) | The base plan's Benzinga "Consensus Ratings" endpoint is buy/hold/sell + price-target consensus — **no EPS/revenue numbers at all** (VERIFIED: the endpoint's own field list has no `eps`/`revenue` field anywhere). A separate Benzinga "Earnings" endpoint does carry `estimated_eps`/`estimated_revenue`, but INFERRED from its schema (surprise fields sit next to it) that it is one consensus figure per reporting event, not a multi-quarter-ahead series | Only via the add-on, and only 1 period ahead | Not documented on either endpoint | n/a | n/a | Benzinga expansion is a **separate $99+/mo add-on**, not included in the $33/mo Massive plan already held | Current plan: nothing usable. Paid add-on: wrong shape even if bought |
| **Alpaca** (current $100/mo Algo Trader Plus) | n/a | **CLAIM (absence)** — `docs.alpaca.markets/us/docs/about-market-data-api` lists equities/options/crypto bars, quotes, trades and no fundamentals/estimates category, but this was read via a page-summarizer, not the raw doc tree, so it is an absence-on-one-page read, not an exhaustive one | n/a | n/a | n/a | n/a | Disqualified on current evidence — no such product turned up anywhere it was checked |

## Ranked shortlist

1. **Keep `yfinance` as primary — nothing free beats it, and today's measurement (7 of 7) says
   it already meets the small-cap bar this whole search was checking for.**
2. **Alpha Vantage** — the only candidate that is both real (live-verified data shape, revenue
   AND EPS, an analyst count) and plausibly free (its docs mark other endpoints "Premium" and do
   not mark this one). Same forward horizon as yfinance, so it is **a cross-check second source,
   not a wider-horizon replacement** — and 25 requests/day covers roughly a quarter of a 100-name
   nightly run, not all of it, unless paid ($49.99/mo lifts the cap).
3. **EODHD** — plausibly the best-documented small-cap story of the paid options, but the
   cheapest tier that includes any fundamentals/estimates data is $59.99/mo, and nothing here
   verifies the small-cap claim against a real ticker.
4. **Finnhub** — right data shape, confirmed dead end for free use: its own API spec marks the
   estimates endpoints premium-only regardless of call volume.
5. **Tiingo, Polygon/Massive, Alpaca** — disqualified. Tiingo doesn't sell this data category.
   The Polygon/Massive subscription already held has no forward EPS/revenue estimates on any
   endpoint, and the closest add-on (Benzinga, +$99/mo) is the wrong shape (one period, not a
   forward series) even if bought. Alpaca has no such product at all.

## Recommendation: verify Alpha Vantage first — exact test

**Get one free Alpha Vantage API key** (form asks name, "which describes you," organization,
email — confirmed on the vendor's own signup page; no card field present). This is the operator's
action, not mine — no account was created for this task.

**The test, once a key exists:** call
`https://www.alphavantage.co/query?function=EARNINGS_ESTIMATES&symbol=<T>&apikey=<KEY>` for the
same seven names measured above (NRIX, AMLX, HTFL, SOLS, ETON, ABCL, UUUU) — seven calls, well
inside the 25/day free budget.

**Pass:** on at least 5 of 7 tickers, the response has a non-empty `estimates` array containing a
`"fiscal quarter"` row dated on or after today with `revenue_estimate_analyst_count` ≥ 3 (the
`n_analysts < 3 → None` floor).
**Fail:** empty `estimates`, or an error requiring a paid plan for this function, or analyst
counts under 3 on most names — in which case Alpha Vantage inherits the same small-cap ceiling
as everything else and is not worth building against.
**Note in advance:** yfinance's own count on this population is already thin (ETON's EPS leg = 2
analysts). If Alpha Vantage comes back thin on the same names, that may be a fact about small-cap
analyst coverage industry-wide, not a flaw specific to either vendor — say so rather than
re-shopping again.

## What it would take from the operator

| candidate | ask |
|---|---|
| Alpha Vantage (the one to verify) | Claim a free API key — email address, no card. Nothing else. |
| EODHD | A **paid subscription decision**, $59.99/mo minimum — his call, not mine, and only worth raising if Alpha Vantage fails the test above. |
| Finnhub | Same — a paid subscription decision, ~$50+/mo, and it is the weaker of the two paid options since Alpha Vantage's shape is already free-adjacent. |
| Tiingo, Polygon/Massive, Alpaca | Nothing — disqualified on the data itself, no action to take. |

## What this does not answer

This is a documentation-and-live-probe scoping read, not a backtest or a production integration.
It does **not** confirm Alpha Vantage's or EODHD's small-cap coverage against a real key — that
is exactly the gap FMP's marketing page hid, and it stays open until the test above runs with a
real key. It does not measure data **quality** (estimate accuracy, staleness, revision timeliness)
for any candidate — only whether the data exists and at what access tier. It does not cover
non-US/ADR names, which the current EP population rarely contains but was not checked. It does
not re-verify the FMP "1 of 12" figure — that number is carried over from #333's own PLAN.md
line, not re-measured in this task. The 7-of-7 `yfinance` read above ran from a developer machine, not
`apollo-market`; a scraped source can be blocked or throttled by IP in ways that would not show up
here, so the recorder's own nightly run on the production host remains the real verification of
that number — if anything this strengthens the case for a second source, not weakens it. If Alpha
Vantage's free tier turns out to gate
`EARNINGS_ESTIMATES` behind a paid plan despite the absent "Premium" label (docs can be wrong —
that is the whole reason this task exists), the recommendation collapses to "nothing free beats
yfinance," which is itself the honest fallback answer this brief asked for.

**⚖ Money note:** EODHD and Finnhub are subscription-spend decisions, not trading-strategy or
safeguard changes, so they don't touch THE LINE — but no subscription was authorized or signed
up for here regardless; both are named only as priced options if the free path fails its test.
