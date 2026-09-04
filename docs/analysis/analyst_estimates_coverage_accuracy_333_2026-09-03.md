# Can a catalyst-durability axis speak on our real alert population? Coverage and accuracy, measured (2026-09-03)

**Decision this serves:** #333 is storing forward analyst estimates so a durability axis becomes
buildable in ~60 days. Before that clock matters, the operator asked the gating question nobody
had answered: what fraction of our alert population has an estimate good enough to build on, and
how often is it simply wrong? **No code changed. No schema, threshold, or scoring rule wired.**
This is a read-only measurement across the full live alert population, not the ~7-to-18-name
samples PLAN.md's #333 line had used so far.

**What would change the decision:** whether the axis can speak on most alerts (a real feature) or
only a thin slice (a niche one), and whether the one bad case found earlier (NRIX, 2026-09-03,
yfinance's estimate ~20x too high on a 28x low/high spread, 3 analysts) is a pattern that needs a design change or a one-off that
doesn't.

## Method / population

**Population:** every distinct ticker with a live-source alert in `mi_ep_alerts` over the trailing
90 days — `alert_date >= CURRENT_DATE - 90d AND COALESCE(source,'live')='live'`. **n = 176 tickers**
(182 alert rows), alert dates 2026-06-08 to 2026-09-03. Query and raw output saved at
`scripts/probes/_333cov_population.sql` / `_333cov_population_out.txt`.

**Sources fetched once each, $0, capture-once-read-many:**
- **yfinance** `revenue_estimate` / `earnings_estimate` for the **near forward quarter ('0q')**,
  plus `quarterly_financials` → "Total Revenue" for the last up to 4 **reported** quarters (the
  reality anchor). Run from a local dev machine — `scripts/probes/_333cov_yfinance_fetch.py` —
  176/176 tickers returned data, 0 errors. Output: `scripts/probes/_333cov_yfinance_out.json`.
- **Finnhub** `/calendar/earnings`, ~200-day forward window. Run **once, on the production host**,
  via a throwaway script placed with `scp`, executed, and then **deleted from the server**
  (script, output, and curl scratch files) — the key was hand-parsed from the server's own `.env`
  inside the script, never printed, never logged, and never left the server. Paced at 1.1s/call
  (~55/min, under the 60/min budget). 176/176 tickers returned data, 0 errors. Output:
  `scripts/probes/_333cov_finnhub_out.json` (contains only public calendar fields — symbol, date,
  quarter, year, epsEstimate, revenueEstimate — never the key).
- **Corrigendum, filed so nobody repeats it:** the first Finnhub run used `/api/v2/...` and got
  176/176 "errors" (empty response body). A raw `curl` probe on the server showed Finnhub
  returning **HTTP 302 redirecting to `/`** — v2 doesn't exist for this endpoint; the real path is
  `/api/v1/...` (matches `analyst_estimates_recorder.FINNHUB_BASE`, which I should have grepped
  for before writing a fresh URL by hand). Fixed and rerun; 0 errors on v1.
- **Cross-environment sanity check:** spot-compared 6 tickers already stored in prod's
  `mi_analyst_estimates` (last night's recorder run, `source='yfinance'`) against this session's
  dev-machine reads. HTFL: prod avg $65.26M / low $64.79M / high $65.90M / n=8 vs today's dev read
  $65.3M / n=8 — matches within normal day-to-day estimate drift. VERA: prod $0/$0/$0/n=11,
  identical to the dev read. The scrape is consistent across environments; not a full re-run.

## 1. Coverage — how much of the population has a yfinance estimate at all

| group | n | % of 176 |
|---|---:|---:|
| has a `revenue_0q` value (any) | 176 | 100% |
| has ≥1 analyst on record | 173 | 98% |
| **zero-coverage** (n_analysts = 0, avg/low/high all 0) | 3 | 2% |

The 3 zero-coverage names are **CHRN, HYMC, KODK**. Two (CHRN, HYMC) plausibly have no revenue
forecast because nobody covers them. The third, **KODK, has real revenue (~$265–311M/quarter,
verified from its own `quarterly_financials`)** but yfinance's forward frame carries zero analysts
and a $0 estimate — this is a **coverage gap on an established revenue company**, not a "no
revenue expected" read. It matters because it looks structurally identical to a genuine
pre-revenue biotech's $0 estimate; only the analyst count (0) tells them apart, and KODK's n=0
already fails today's n≥3 rule, so it correctly reads as "no data" rather than "zero revenue."

**Analyst-count distribution** (revenue, '0q'), n=176:

| analysts | n | % |
|---|---:|---:|
| < 3 | 16 | 9% |
| 3–4 | 30 | 17% |
| 5–7 | 35 | 20% |
| 8–11 | 37 | 21% |
| 12+ | 58 | 33% |

Median 8, mean 10.3. **Today's n≥3 rule admits 160/176 (91%)**; raising the bar to n≥5 admits
130/176 (74%); n≥8 admits 95/176 (54%).

**Low/high spread distribution** (`high/low`, excluding 19 tickers where `low ≤ 0` — see below),
n=157:

| spread | n | % of 157 |
|---|---:|---:|
| ≤ 1.2x | 129 | 82% |
| 1.2x–1.5x | 16 | 10% |
| 1.5x–2x | 6 | 4% |
| 2x–5x | 4 | 3% |
| 5x–10x | 0 | 0% |
| > 10x | 2 | 1% |

Median 1.06x, p25 1.02x, p75 1.14x — the great majority of the population has a **tight** spread.
Separately, **19 tickers (11% of 176) have `low ≤ 0`** — the estimate range spans down to (or
below) zero, which this doc treats as its own "maximal uncertainty" bucket rather than folding it
into the numeric spread (a ratio against zero or a negative number is undefined). 12 of the 19 are
pre-revenue biotechs whose actual revenue really is $0 every quarter (CGEM, ELVN, JBIO, MANE,
MLTX, SYRE, VERA, and others) — a correct $0 forecast, not a data defect. One, **KYMR, has a
NEGATIVE low estimate (−$1.0M) for revenue**, which is nonsensical on its face (revenue cannot be
negative) — a scrape/data artifact worth flagging on its own, independent of anything else here.

**Combined quality-bar sensitivity** (the operator's bar to choose, not mine), n=176:

| bar | n passing | % |
|---|---:|---:|
| n≥3 AND spread≤1.2x | 118 | 67% |
| n≥3 AND spread≤1.5x | 134 | 76% |
| n≥3 AND spread≤2.0x | 140 | 80% |
| n≥5 AND spread≤1.2x | 94 | 53% |
| n≥5 AND spread≤1.5x | 109 | 62% |
| n≥5 AND spread≤2.0x | 113 | 64% |
| n≥8 AND spread≤1.5x | 78 | 44% |

(A rough 18-name sample in PLAN.md estimated ~8/18 = 44% at n≥5-and-spread≤1.5x; the real
population comes in at 62% on that same bar — the small sample understated coverage.)

## 2. Accuracy — when yfinance and Finnhub disagree, which one is right? (the most important result)

**160/176 (91%)** of the population has a comparable near-quarter revenue figure from **both**
vendors (13 tickers return no Finnhub calendar entry at all inside the ~200-day window — AKTS,
BRUN, CBRS, EROC, HQ, HUT, LFST, MANE, PRGO, SG, STDN, VOYG, XE; 3 more have a Finnhub entry but no
revenue figure on it. **Why 13 names — some established filers among them, e.g. PRGO, SG — have no
near-term Finnhub earnings date at all was not run down; this is unverified and simply bounds how
much of the population the cross-check can ever reach.**). Of the 160:

| agreement (yfinance vs Finnhub, same quarter) | n | % of 160 |
|---|---:|---:|
| within 1.5x | 146 | 91% |
| both ≈ $0 (agreement, not a gap) | 7 | 4% |
| 1.5x–2x | 3 | 2% |
| **> 2x apart (material)** | **4** | **3%** |

(The "both ≈ $0" row — AMLX, CGEM, DFTX, ELVN, JBIO, MLTX, SYRE — was excluded from the ratio
calculation because dividing by zero is undefined, not because the two vendors disagreed; both
say near-zero and both are right for these pre-revenue names. It is listed separately so it isn't
mistaken for either an error or a gap.)

**The 4 material-divergence cases:**

| ticker | yfinance avg | Finnhub near est. | ratio (yf/fh) | n_analysts (yf) | actual revenue scale | verdict |
|---|---:|---:|---:|---:|---:|---|
| NRIX | $479.5M | $22.8M | 21.1x | 3 | ~$8.5M (median, last 4Q) | **Finnhub closer — confirmed** |
| VERA | $0 | $6.4M | 0 | 11 | $0 (last 4Q); **but yfinance's OWN `+1q` row (already stored in prod) shows $16.7M avg** | **ambiguous — see below** |
| FRMI | $6.0M | $188.0M | 0.03x | 2 | $0 (last 4Q) — but see caveat | unresolved |
| CHRN | $0 | $5.5M | 0 | **0** | no data | **not a real disagreement — see below** |

**CHRN is not a disagreement**: yfinance has **zero analyst coverage** for it (n=0) — there was no
real yfinance number to disagree with, only a placeholder. Finnhub is filling a genuine coverage
gap here, the same shape as KODK in §1, just observed from the other side. That leaves **3 real
same-quarter disagreements out of 159 comparable pairs (1.9%)**.

**Of those 3, only 1 is a confirmed vendor error — NRIX (Finnhub is closer, by a wide margin).**
The other 2 do not support a clean verdict:
- **VERA is ambiguous, not a yfinance win.** The initial read here compared yfinance's `0q` ($0)
  to Finnhub's near estimate ($6.4M) and called $0 correct because it matches 4 straight actual
  quarters. But prod's own already-stored `mi_analyst_estimates` carries VERA's yfinance `+1q` row
  too: **$16.7M avg (range $0–$34.9M, n=12)** — analysts DO expect real revenue, just not
  necessarily in the exact quarter yfinance currently labels `0q`. Finnhub's calendar entry is
  dated 2026-11-03 and labeled "quarter 3, year 2026" — and the recorder's own docstring already
  flags that Finnhub's quarter label is ambiguous ("Earnings quarter" vs "Fiscal quarter" in its
  own API spec). $6.4M could be Finnhub correctly pricing a slightly different quarter than
  yfinance's `0q`, not a wrong number. This is a plausible launch-timing/fiscal-label mismatch,
  not a demonstrated error on either side.
- **FRMI remains unresolved.** Fermi Inc. is a newly listed nuclear/data-center infrastructure
  company; its trailing "actual" revenue reflects the entity **before** its current business
  existed, so $0 trailing tells us nothing about which of $6.0M or $188.0M is right for the new
  business. Neither source can be checked against real history here.

**Bottom line on accuracy: across 159 real comparable pairs, exactly 1 confirmed vendor error was
found (NRIX), and it was yfinance's.** That is nowhere near enough evidence to build a rule that
resolves future disagreements in Finnhub's favor — one confirmed case cannot establish a general
tie-breaker, and the other 2 divergent cases (VERA, FRMI) show real disagreement can come from
fiscal-label mismatches or genuinely unresolvable trailing history rather than either vendor being
"wrong." What the data DOES support: disagreement between the two vendors is rare (156/159 real
pairs agree — within 1.5x, both-≈$0, or 1.5x–2x — 98%; 3/159 diverge materially, 1.9%) and worth a
second look every time it happens, precisely because it is rare enough that acting on it is cheap.

## 3. What predicts a BAD ESTIMATE (not just a disagreement) — spread beats analyst count, at a moderate bar

§2's vendor-disagreement cases are the wrong outcome to fit a predictor to: VERA turned out
ambiguous (not confirmed wrong, §2), and SHAZ — a confirmed-implausible case from §4 below,
where yfinance and Finnhub actually **agree** with each other while both look wrong against the
company's own trailing revenue — wouldn't even appear in a disagreement-based test. So this
section uses the more defensible outcome: **yfinance's average lands more than 3x off the
company's own recent actual revenue** — the definition §4 develops in full below. On the full
176-ticker population, exactly **2 tickers meet that bar with real supporting evidence: NRIX
(confirmed, §2) and SHAZ (likely, §4)**. Two known-bad cases is too few to fit an exact threshold —
enough to see the shape, not enough to pick a number, so the table below shows several candidate
bars rather than one answer:

| candidate signal | tickers flagged | % of 176 | catches NRIX? | catches SHAZ? |
|---|---:|---:|---|---|
| n_analysts < 3 (today's rule) | 16 | 9% | no (n=3) | no (n=4) |
| n_analysts < 5 | 46 | 26% | yes | yes |
| n_analysts < 8 | 81 | 46% | yes | yes |
| spread (defined) > 2x | 6 | 3% | yes | yes |
| **spread (defined) > 3x** | **5** | **3%** | **yes** | **yes** |
| `low ≤ 0` (spans zero) | 19 | 11% | no | no |
| `low ≤ 0` OR spread > 10x | 21 | 12% | yes (via >10x) | **no** |

Two things stand out. **First, today's exact n≥3 rule would not have caught either known-bad
case** — NRIX has exactly 3 analysts, SHAZ has 4, both clear a bar set at "at least 3." **Second,
a moderate spread bar (>2x or >3x, on the *defined* spread only) is both cheaper and more complete
than any analyst-count bar**: it flags only 5–6 names (3% of the population) and catches both
known-bad cases, where an analyst-count bar wide enough to catch both (n<5) has to flag 26% of the
population to do it. **The `low ≤ 0` bucket used in an earlier pass of this analysis was the wrong
signal — it flags zero of the two known-bad cases** (both NRIX and SHAZ have a *positive*, just
wide, low estimate) **and its inclusion inside a combined "extreme spread" flag was masking this**:
that combined flag's apparent 100% recall came entirely from its `>10x` half (which is really just
"spread>3x" restated more loosely), not from `low≤0`, which instead adds 19 names to the flagged
set for zero additional catches. `low≤0` is its own, different signal — mostly correct $0 forecasts
for pre-revenue biotechs (§1) — and should not be folded into a "wide spread" flag.

At `spread > 3x`, the 3 extra names flagged beyond NRIX/SHAZ are **ARWR, QURE, KURA** — all three
checked in §2/§4 and found to track Finnhub and/or their own trailing revenue reasonably well
despite the wide range (ARWR's revenue is genuinely lumpy — royalty/licensing payments — which
produces a wide analyst range around a still-roughly-right average). So a spread>3x flag would be
right about 40% of the time it fires (2 of 5) on this sample — a real cost, but a small one applied
to only 3% of the population, versus flagging over a quarter of it to get the same recall from
analyst count. **Spread is the better, largely-free signal; analyst count is markedly weaker even
at its most generous threshold.** This is built on 2 confirmed cases — enough to see that spread
beats count, not enough to certify an exact cutoff; treat the 2–3x range as the region to watch,
not a final answer. **The finding does not depend on SHAZ being confirmed**: even if SHAZ turns out
to be a real catalyst rather than a data problem (see the caveat below), NRIX alone still shows
spread>3x catching a known-bad case at 5 flagged names (3%) versus n<5 needing 46 (26%) — the
comparison holds on n=1 known-bad case, SHAZ just adds a second data point in the same direction.

## 4. Secondary check — yfinance vs. the company's own trailing revenue

A second, independent test: compare yfinance's avg estimate to the median of the ticker's own last
up to 4 **reported** quarters (from `quarterly_financials`), across all 176 tickers:

| result | n | % |
|---|---:|---:|
| within 1.5x of trailing scale | 128 | 73% |
| 1.5x–3x | 22 | 13% |
| both ≈ zero (consistent) | 12 | 7% |
| 3x–10x off | 5 | 3% |
| **> 10x off** | 6 | 3% |
| actual is $0 but estimate is material (>$1M) | 2 | 1% |
| no actual-revenue history available | 1 | 1% |

13 of 176 (7%) land outside 3x of their own trailing scale (the 5+6+2 rows above). **This test is
noisier than §2/§3 and should be read as directional, not a clean error count** — most of the 13
turn out to be real business dynamics, not data errors, once checked individually: a seasonal
mega-cap (H&R Block, whose revenue is naturally concentrated in one quarter of the year, so a
median-of-4 comparison compares the wrong season), a probable revenue-definition mismatch (a
crypto exchange whose "Total Revenue" line may not mean the same thing analysts model), several
plausible real ramps or declines at small/early-stage names, and 2 real cases: NRIX (confirmed
genuinely wrong in §2) and SHAZ (a second likely case, found here — see below). **The
Finnhub cross-check in §2 is the more decisive test for exactly this reason: it compares the
SAME forward quarter across two vendors, so it isn't confounded by seasonality or a company's
history predating its current business.**

**SHAZ, found in this pass, is a second likely case of the NRIX pattern**: yfinance avg $27.0M
against actual trailing revenue of $0.3M–$1.9M/quarter (a 14–90x gap), on only 4 analysts. Unlike
NRIX, **Finnhub agrees with yfinance here** ($34.4M) — both vendors show the same large jump from
a tiny trailing base. That could mean a real pending catalyst (both vendors' consensus panels see
the same known event), or it could mean both vendors draw from overlapping underlying data and
share the same error — this measurement cannot tell the two apart without a third source or
company-specific research, and is reported as an open flag, not a confirmed second NRIX.

## 5. Bottom line for the operator

- **The 160/176 (91%) figure overstates what a revenue-*growth* axis can use.** Of those 160,
  **8 have a $0 forward revenue estimate** (CGEM, DFTX, ELVN, JBIO, MANE, MLTX, SYRE, VERA — all
  with 6+ analysts, all genuinely pre-revenue) — growth off a $0 base is undefined, so a growth
  axis has nothing to say on these even though they "pass" coverage. **The real speakable-on
  fraction is closer to 152/176 (86%).** Whether to treat a $0 forecast as "no growth" or "skip
  silently" is a methodology choice for the operator, not decided here.
- **On today's n≥3 rule alone, the axis could speak on 160/176 alerts (91%)** — and at least 1 of
  those 160 rows (NRIX) is confirmed badly wrong (21x off from Finnhub, 56x off from real scale)
  despite passing; today's exact rule would not have excluded it (NRIX has 3 analysts, SHAZ has 4
  — both clear "at least 3").
- **A moderate spread flag (`high/low > 2x` or `>3x`, on the *defined* spread only — not
  `low≤0`) is the cheapest, most complete signal found here**: it flags only 5–6 of 176 names (3%)
  and catches both known-bad cases (NRIX, SHAZ), where reaching the same recall with an
  analyst-count bar (n<5) requires flagging 46/176 (26%) — roughly 8x the cost for the same catch.
  Within the 5–6 flagged names, about 2 of 5 are real problems and the rest (ARWR, QURE, KURA) are
  fine despite the wide range — a real false-positive cost, but a small one spread over only 3% of
  the population.
- **This is built on 2 confirmed/likely-bad cases out of 176 — enough to see the shape (spread
  beats count), not enough to certify an exact cutoff.** The choice of bar (2x, 3x, or something
  else) and how to use the flag once fired are his to make, not mine:
  (a) keep n≥3 only — widest coverage (91%), a small but nonzero and now-measured chance any given
  row is badly wrong; (b) add a spread bar as an outright exclusion — cheap (3% of the population)
  but removes ARWR/QURE/KURA along with the real problems; (c) add it as a **soft "low-confidence"
  tag** rather than an exclusion — keeps all 160 rows scored, marks ~3% of them for lower trust or
  a second-source check. Option (c) costs nothing new to build (the fields are already stored).
- **What NOT to build on this evidence:** a rule that resolves vendor disagreement in Finnhub's
  favor by default. §2 found exactly 1 confirmed case either way (Finnhub right on NRIX) — nowhere
  near enough to generalize a tie-breaking rule, and the other 2 divergences (VERA, FRMI) turned
  out to be ambiguous or unresolvable rather than a second confirmation.

## What this does not answer

This is a single point-in-time snapshot (one read per vendor, 2026-09-03) — it says nothing about
**revision stability over time**, which is what the ≥60-day accrual clock the recorder is building
is actually for; re-run this same measurement once that history exists. The §4 vs-actual test is
confounded by seasonality (H&R Block), a likely revenue-definition mismatch for at least one
exotic business model (a crypto exchange), and recently-listed/merged names whose trailing history
predates their current business (Fermi Inc.) — treat §4 as a directional cross-check, not a clean
error count; §2 (the Finnhub same-quarter comparison) is the more decisive test and should
carry more weight. The confirmed-genuinely-wrong sample is small — 1 certain (NRIX) plus 1 likely
(SHAZ, unconfirmed without a third source) — enough to see that spread beats analyst count as a
predictor, not enough to fit an optimal spread threshold; §1's sensitivity table exists so the
operator can pick a bar rather than have one picked for him. This does not test EPS estimates at
all (both vendors' EPS fields were captured in the raw JSON but not analyzed here — the durability
axis is revenue-led). yfinance was read from a local dev machine and Finnhub from the production
host; a scraped source can behave differently by egress IP, and while a 6-ticker spot-check against
prod's own already-stored yfinance rows matched, that is not a full re-run of this measurement from
`apollo-market` itself. This does not touch `mi_daily_closes`, and uses no `ret_*` or MFE field
anywhere. This does not decide any threshold, does not change `estimate_for_scoring`, and does not
sign off on the durability axis itself — that decision, and the CHANGE_PROCESS it requires, is
still ahead and still the operator's. **The population is `mi_ep_alerts` — names that alerted
BECAUSE something just happened to them** (a gap, a catalyst). §4's trailing-vs-forward mismatches
should therefore be expected to over-represent real step-changes, not data errors, more than a
random stock sample would — this is exactly why SHAZ (both vendors agree on a large jump from a
tiny trailing base) is reported as "likely," not "confirmed": an EP name jumping on real news is
the population working as intended, not necessarily a vendor mistake.
