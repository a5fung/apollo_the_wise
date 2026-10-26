# #705 inventory 1: how usable are his stream captions as the step-6 reference?

Measure only. No rules, no design. Our rule library is not used anywhere in this page.

## Answer

- **About 14% of caption trade statements give a complete, dated trade fact** (named stock + what he did + the day), 95% range 4% to 24%. That is roughly **1,070 of the 7,607 candidate statements** in 2020-2022 (range 320 to 1,820).
- **Counting statements whose day is not in the words** (he points at the chart: "here", "this day") the share is 43% (31% to 54%): the stock and the action are clear, the day is only bounded by the stream date. Position-state facts (holding, stop level, stated result) add a further 3%.
- **By year (2020 / 2021 / 2022): 13% / 16% / 20% usable now**; the ranges overlap (see table 2), so no year is measurably better than another.
- **A price is stated in few of them**: only 10% of all statements have a named stock, an action AND a price (6% with a clean number). When he gives a number it is usually a share count or a dollar gain or loss (sample rows S017, S021, S044, S055, S098), not an entry price.
- **Account-level numbers exist and are rich**: 133 statements with a number listed in `account_statements.tsv` (yearly returns 2013-2020, the 2021 year-to-date path, account sizes, best/worst weeks and days). The 2013-2018 yearly returns are told identically on two days seven months apart (stable); the 2020 figure is not (+710% to +1000% depending on how and when he says it).
- **Coverage is dense for 2020-01 to 2021-06** (about 82% of trading days have a caption video) **and thin after** (2021-07 to 2022-06 about 23%). Details in the coverage table.
- **Action: none.** Inventory only; the numbers here set what step 6 can and cannot lean on.

## What was done

- Parsed 495 caption files (YouTube auto-captions, rolling repeats removed) -> 485 unique streams after dropping 10 duplicate uploads of the same stream (same date, title, length).
- Regex pass for first-person trade phrases (patterns in the script). Nearby matches (within 12 words, any kind) are merged into one statement named by its strongest kind. Total: **9,474 statements** in 2017-2023, **7,607 in 2020-2022**.
- Fixed sample (seed 705) of 120 statements, stratified by kind x year (the brief said kind; adding year gives about 40 rows per year for the per-year estimate), 1 to 5 per cell where the cell is that big. 2017-2019 and 2023 are counted in table 1 but not sampled (the positions-list era is 2020-01 to 2022-06). Each read with +-30 s of caption context and hand-labelled by ONE reader (me); no blind second reader (no subagents allowed). A review pass over the rows that drive the headline changed 7 of 120 labels (6 day labels, 1 ticker). Rows: `caption_sample.tsv`.
- Weighted estimate = each cell scaled to the number of statements it stands for. 95% range = estimate +- 1.96 standard errors; each cell's variance is computed with one hit and one miss added, so a cell that happened to show 0 of 4 is not treated as certain. Cells hold only 1-5 rows, so the ranges are wide.

**Label meanings (plain):**

- *ticker identifiable*: Y = one company/ticker named in the 30 s either side that the sentence clearly points at (a garbled name I could resolve from the next sentence counts as Y but is flagged *inferred*); amb = garbled or several candidates; N = not named.
- *his own trade (Y)*: first-person fact about his own position. Not Y: advice to viewers, if-then, plans ("gonna get stopped out"), a viewer's trade, insiders, jokes.
- *action*: buy, add, sell_part, sell_all, sell_unspec (sold, size not said), stopped. Position-state facts are labelled separately: holding, stop_level ("my stop is ..."), result ("lost 180k on two trades").
- *day pinned*: stream_day (words show it is today: just, pre-market, at the open, today), stated_earlier (yesterday, Friday, three days ago), implied_recent (live position but no day word), approx_earlier (last week, a month ago), unstated ("here", "this day" = chart pointing, or nothing).
- **usable now** = ticker Y + event action + his own + day in {stream_day, stated_earlier}. **usable, day bounded only** = same without the day test. **loose** adds implied_recent and approx_earlier.

## 1. Candidate trade statements by kind and upload year (after de-duplication)

Kind = strongest phrase in the merged statement. `stopped` = "stopped out / got stopped"; `sold_part` = "sold half / some / a third", "took half"; `sold` = "i sold / sold it / i'm out"; `buy_now` = "i'm long / i got in / i'm buying"; `cost_stop` = "my average / my entry / my stop"; `profit` = "took profits".

| kind | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | total | in 2020-22 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| stopped | 228 | 6 | 257 | 1,323 | 446 | 60 | 18 | 2,338 | 1,829 |
| sold_part | 66 | 2 | 29 | 170 | 50 | 1 | 5 | 323 | 221 |
| sold | 117 | 3 | 63 | 759 | 381 | 25 | 15 | 1,363 | 1,165 |
| added | 60 | 2 | 27 | 349 | 82 | 2 | 8 | 530 | 433 |
| bought | 312 | 12 | 170 | 1,343 | 602 | 32 | 59 | 2,530 | 1,977 |
| buy_now | 31 | 1 | 35 | 327 | 123 | 12 | 4 | 533 | 462 |
| profit | 2 | 0 | 1 | 15 | 14 | 0 | 0 | 32 | 29 |
| cost_stop | 91 | 1 | 143 | 736 | 155 | 10 | 4 | 1,140 | 901 |
| account | 18 | 2 | 72 | 369 | 200 | 21 | 3 | 685 | 590 |
| **all** | **925** | **29** | **797** | **5,391** | **2,053** | **163** | **116** | **9,474** | **7,607** |
| unique streams | 57 | 2 | 38 | 212 | 137 | 29 | 10 | 485 | 378 |

Mentions before merging nearby kinds (the same sentence often hits two kinds, e.g. "bought ... got stopped"): stopped 2,433, sold_part 354, sold 1,763, added 602, bought 3,096, buy_now 670, profit 35, cost_stop 1,406, account 773.

## 2. Yield from the hand-read sample (120 statements)

Share of statements that are usable. Range = 95%. "statements" = candidate statements, not distinct trades (one trade is often mentioned twice in a minute, e.g. S040/S041/S105 are one BOIL sale and its entry).

| scope | statements in scope | usable now (ticker + action + day said) | ticker + action, any day wording | ticker + action + day said or implied | position-state facts | ticker + action and a price stated |
|---|---:|---|---|---|---|---|
| 2020-2022 all kinds | 7,607 | 14% (4%-24%) | 43% (31%-54%) | 37% (26%-48%) | 3% (0%-12%) | 10% (0%-20%) |
| 2020-2022 trade kinds (no 'account') | 7,017 | 15% (5%-26%) | 46% (34%-58%) | 39% (27%-52%) | 4% (0%-13%) | 11% (1%-21%) |
| 2020 | 5,391 | 13% (0%-26%) | 43% (28%-58%) | 43% (28%-58%) | 3% (0%-14%) | 10% (0%-22%) |
| 2021 | 2,053 | 16% (2%-31%) | 43% (27%-58%) | 23% (8%-38%) | 5% (0%-17%) | 10% (0%-24%) |
| 2022 | 163 | 20% (5%-35%) | 50% (34%-66%) | 22% (7%-37%) | 3% (0%-15%) | 15% (1%-29%) |

Conservative variant: dropping the 19 sampled rows where I resolved a garbled name by inference (flagged `ticker_inferred`) the "usable now" share is 11% (2%-21%).

Expected number of usable statements in the 2020-2022 captions (share x 7,607 statements): usable now ~1,070 (320 to 1,820); day bounded only ~3,250 (2,390 to 4,120).

Per stream (378 streams in 2020-2022): about 2.8 usable-now statements and 8.6 with ticker + action (any day wording) per stream.

**By kind (raw sample counts, small n: read as direction only):**

| kind | statements 2020-22 | sampled | usable now | ticker + action (any day) | position-state | not his own trade |
|---|---:|---:|---:|---:|---:|---:|
| stopped | 1,829 | 15 | 2 | 8 | 0 | 3 |
| sold_part | 221 | 11 | 3 | 7 | 0 | 1 |
| sold | 1,165 | 15 | 3 | 8 | 0 | 3 |
| added | 433 | 12 | 1 | 2 | 0 | 6 |
| bought | 1,977 | 15 | 4 | 9 | 0 | 4 |
| buy_now | 462 | 14 | 2 | 3 | 3 | 3 |
| profit | 29 | 9 | 1 | 2 | 0 | 7 |
| cost_stop | 901 | 14 | 2 | 4 | 4 | 1 |
| account | 590 | 15 | 0 | 1 | 0 | 6 |

## 3. Why a statement is not usable (weighted shares, 2020-2022)

| first failing test | share | sampled rows |
|---|---:|---:|
| usable now: ticker + action + day | 14% | 18 |
| ticker + action ok, day not in the words | 29% | 26 |
| not about his own trade (advice, if-then, plan, viewer, someone else) | 24% | 34 |
| his position but no buy / sell / stop event (holding, stop level, result, nothing) | 14% | 24 |
| event is his, but the ticker is not identifiable | 19% | 18 |

Among the 44 sampled rows with ticker + his own event: day pinned as unstated 11, implied_recent 10, stream_day 9, stated_earlier 9, approx_earlier 5.
Among his own event rows the ticker is Y 44 / amb 14 / N 4.
Among the 44 usable rows (day bounded only or better): price stated 9 (garbled 5); a share count or dollar size is stated in a few more.
His-trade label over all 120 rows: Y 86, other 11, hypo 11, future 5, generic 5, unclear 2.

What the misses look like (from reading the rows): the regex fires on advice ("if you get stopped out ..."), plans ("I'm gonna get stopped out"), jokes and viewers' trades as often as on facts; tickers are said as nicknames or garbled by the caption (TVIX heard as twix / tweaks / twigs / tricks; GUSH as gosh / cash; TQQQ as tqq / tq), which a per-ticker alias list could recover; and the day is often "here" on a chart he is pointing at.

## 4. His statements of account, yearly and monthly results

`account_statements.tsv`: **133 statements** (114 account-level, 19 single-trade $ results of about $200k or more, 7 are video titles). Found with two regex passes over all 485 streams plus a title scan, then read by hand; recall is unknown and some are surely missing (the second pass found about 15 the first missed). By year of the video: 2017 4, 2019 21, 2020 77, 2021 27, 2022 4.

By level: ytd 21, year 19, trade 19, account_size 17, day 13, week 7, month 7, unrealized 7, multi_month 5, drawdown 5, hit_rate 5, multi_year 3, lifetime 1, unspecified 1, exposure 1, period 1, intraday 1.

Quality: clean 86, approximate 41, garbled 4, sarcasm-risk 2.

**The yearly return series as he states it (his figures, not verified):**

| year | stated | said on (video date) | repeated? |
|---|---|---|---|
| 2011-2012 | losing years, "blew up about four times" | 2019-11-01, 2020-06-09 | yes |
| 2013 | +352% (first winning year; account $16k down to $9.1k) | 2019-11-01, 2020-06-09 | same number twice |
| 2014 | +646% (also "10-bagger / ~1000% in under a year" on a rolling window) | 2019-11-01, 2020-06-09, 2019-10-04, 2020-12-07 ("best year ~650") | same number 3x |
| 2015 | +107% | 2019-11-01, 2020-06-09 | same number twice |
| 2016 | +217% | 2019-11-01, 2020-06-09 | same number twice |
| 2017 | +414% (best month Sep 2017 about $200k) | 2019-11-01, 2020-06-09 | same number twice |
| 2018 | +89% (a $700k Tilray loss) | 2019-11-01, 2020-06-09 | same number twice |
| 2019 | +52% ("very unhappy"); later "over 100 percent if i remember" | 2020-06-09 / 2020-07-30 | **conflict** |
| 2020 | +870% (title + 2021-01-05); +900% (2021-02-11, 02-17); "almost 1000" (2021-09-17); "under 1000" (2021-01-12); $3.5M start + ~$25M = about +710%; "800-900%" (2020-12-22) | 2020-12-09 to 2021-09-17 | **range +710% to +1000%** |
| 2021 to date | +60% (02-09), ~+90-100% (02-23/24), +100-120% (03-10), +120% (03-12), +130% then +90-100% (03-24), ~+100% with peak +120-130% (05-06), "barely up 100" (09-17) | 2021-02 to 2021-09 | full year never stated in captions |
| 2022 to date | "not up that much" (04-13); "exactly 15 year-to-date" (04-14, garbled) | 2022-04 | partial |

Seven-year average he quotes (2013-2019) is about 268% a year; the mean of the seven yearly figures above is 268.1, so those figures agree with each other. Account sizes quoted: $16k (2013), about $1M (Dec 2017 after tax, or July 2016 gross), $2.4M then $4M peak (Jul 2019), about $3.3-3.5M (Nov 2019), about $3.3-4M at the start of 2020, about $17.5M (2020-08), about $18-20M peak (Jul 2020), $105M peak (Nov 2021).

**Reliability notes for using these as the "reproduces his returns" reference:**

- Fuzzy periods: many numbers are "on the year" or "on the month" said mid-period; the account base changes with withdrawals (boat, car) and a second smaller IB account is quoted separately (+900% to +1100% in 2020).
- A few are jokes or look rhetorical ("20 million in my paper account", "almost 200 million dollar account" in 2021-03 vs a $105M peak he gives later): flagged `sarcasm-risk`.
- Dollar figures are mostly P&L swings and unrealized ("main account"), not closed-trade returns.

## 5. Coverage by month, 2020-01 to 2022-06

Videos = caption files with duplicates dropped. Trading days = NYSE days (hard-coded holiday list). Days covered = trading days that have at least one caption video uploaded that day (one Saturday upload in the era; 8 "Late upload" videos in 2021-03 / 2021-01 carry an earlier stream date in the title, so their upload date is NOT the stream date).

| month | caption videos | trading days | days covered | covered | listed but no caption track | stream hours captioned | caption words |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2020-01 | 14 | 21 | 14 | 67% | 4 | 18 | 60,721 |
| 2020-02 | 17 | 19 | 16 | 84% | 0 | 28 | 87,271 |
| 2020-03 | 17 | 22 | 17 | 77% | 0 | 26 | 84,849 |
| 2020-04 | 19 | 21 | 19 | 90% | 0 | 28 | 90,566 |
| 2020-05 | 16 | 20 | 15 | 75% | 0 | 27 | 93,947 |
| 2020-06 | 18 | 22 | 18 | 82% | 1 | 37 | 159,836 |
| 2020-07 | 20 | 22 | 19 | 86% | 0 | 37 | 160,823 |
| 2020-08 | 17 | 21 | 17 | 81% | 0 | 31 | 152,710 |
| 2020-09 | 18 | 21 | 18 | 86% | 0 | 28 | 111,808 |
| 2020-10 | 19 | 22 | 18 | 82% | 0 | 32 | 140,698 |
| 2020-11 | 18 | 20 | 18 | 90% | 0 | 29 | 104,068 |
| 2020-12 | 19 | 22 | 19 | 86% | 0 | 33 | 145,361 |
| 2021-01 | 20 | 19 | 19 | 100% | 0 | 41 | 170,166 |
| 2021-02 | 18 | 19 | 18 | 95% | 0 | 29 | 119,681 |
| 2021-03 | 21 | 23 | 16 | 70% | 2 | 36 | 114,709 |
| 2021-04 | 17 | 21 | 17 | 81% | 2 | 28 | 94,353 |
| 2021-05 | 13 | 20 | 13 | 65% | 4 | 20 | 59,085 |
| 2021-06 | 18 | 22 | 18 | 82% | 1 | 37 | 111,509 |
| 2021-07 | 3 | 21 | 3 | 14% | 0 | 5 | 16,744 |
| 2021-08 | 0 | 22 | 0 | 0% | 2 | 0 | 0 |
| 2021-09 | 5 | 21 | 5 | 24% | 5 | 5 | 14,119 |
| 2021-10 | 6 | 21 | 6 | 29% | 9 | 11 | 28,237 |
| 2021-11 | 5 | 21 | 5 | 24% | 13 | 9 | 25,912 |
| 2021-12 | 11 | 22 | 11 | 50% | 6 | 14 | 43,628 |
| 2022-01 | 11 | 20 | 11 | 55% | 6 | 9 | 23,406 |
| 2022-02 | 7 | 19 | 7 | 37% | 6 | 8 | 21,271 |
| 2022-03 | 2 | 23 | 2 | 9% | 5 | 2 | 4,278 |
| 2022-04 | 7 | 20 | 7 | 35% | 8 | 6 | 18,297 |
| 2022-05 | 1 | 21 | 1 | 5% | 2 | 1 | 1,462 |
| 2022-06 | 0 | 21 | 0 | 0% | 6 | 0 | 0 |
| **total** | **377** | **629** | **367** | **58%** | **82** | | |

2020-01 to 2021-06: 309 of 377 trading days covered (82%). 2021-07 to 2022-06: 58 of 252 (23%). In that second stretch the channel lists only 128 videos in total (against 341 in the first 18 months) and 68 of them have no caption track at all, so the gap is both fewer streams on the channel and missing tracks. 3 further videos failed on an age gate (no date). Caption videos outside the table: 2017 57, 2018 2, 2019 38, 2022 1, 2023 10.

## Files

- `captions_inventory.py`: stages `extract`, `draw`, `account`, `report`, plus `show VIDEO H:MM:SS [SECONDS]` to read any caption stretch. Seed 705. Writes only here; scratch in the system temp dir.
- `caption_sample.tsv`: the 120 sample rows with all labels and the derived `usable_*` columns.
- `account_statements.tsv`: 133 account / result statements with video date, time, level, period, number, verbatim caption quote (checked to appear in the caption text), quality flag.
