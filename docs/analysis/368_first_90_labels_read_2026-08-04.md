# What the operator's first 90 labels already tell us (#368, 2026-08-04)

**Read-only. Nothing changed.** Operator asked whether the 90 labels are usable before the other
100 land. They are — one whole side of the question is **complete**, not partial.

## The cohort is not 47% labelled — it is one side finished and one side sampled

| stratum | rows | labelled | what it tests |
|---|---|---|---|
| `themed` | 59 | **59 — ALL** | false positives: we credited a theme that wasn't the driver |
| `themeless_winner` | 131 | 31 | false negatives: a real theme we never saw |

The `themed` side needs no more work. Every conclusion below about false positives is final.

## 1. The theme credit is right 84.5% of the time

`themed` stratum, fully labelled: **49 the theme really drove it · 9 it did not · 1 can't tell.**
So 49 of the 58 decided = **84.5%**.

That is the number the weighting decision needs, and it is now measured rather than assumed.
**What to do with it is the operator's call** (methodology — THE LINE); this only supplies it.

## 2. The 9 errors are not 9 different mistakes — 5 are the SAME one

| ticker | date | operator's note |
|---|---|---|
| HUT | 05-06 | crypto miners converting into AI |
| WULF | 07-06 | crypto miner to AI infra conversion play |
| CLSK | 07-14 | crypto to AI |
| HUT | 07-20 | crypto to AI |
| IREN | 07-20 | crypto to AI |
| BATL | 04-02 | wrong theme, this is oil and gas |
| KYTX | 04-22 | wrong theme, this is health tech |
| LUNR | 05-26 | a space theme (close) but not satellite |
| CRCL | 07-10 | crypto play, stable coin |

**Five of nine are one systematic misclassification**: a crypto miner repurposing its power and
data-centre footprint for AI is filed under crypto mining, when the bid is the AI-infrastructure
conversion. It recurs across three months and four tickers, so it is a definition problem, not a
labelling accident. The remaining four are genuine one-offs.

## 3. The two error sides point at the SAME missing theme

The 22 `themeless_winner` rows the operator marked as a theme we missed, with his notes:

| cluster | n | tickers |
|---|---|---|
| biotech / healthtech | 10 | MANE · ICLR · NEO · NVCR · CUE · FTRE · IART · CYRX · AVTX · LIVN |
| AI semi / AI infra / data centre | 8 | NXPI · SIMO · FTAI · BB · OUST · STRL · OSS · FLEX |
| software / cloud | 3 | TEAM · FIVN · TWLO |
| energy | 1 | SKYQ |

**AI infrastructure appears on both lists.** It is the theme we wrongly attribute *away from* on the
crypto-miner names, and the theme we fail to *discover* on FTAI, BB, STRL, OSS, FLEX. One
mis-scoped theme is producing errors in both directions — which is a far more tractable finding
than "the engine is 15% wrong."

## 4. Two mechanical candidates for the biotech blind spot — neither yet proven

Theme discovery seeds from `get_rs_leaders(..., limit=60)[:40]`, which applies
`is_sector_filtered`: **Healthcare priced under $50 is excluded from the pool entirely**
(`SECTOR_FILTER_SECTORS = {"Healthcare"}`, `SECTOR_FILTER_MIN_PRICE = 50.0`).

Checked against the 22 missed names, using each name's most recent `mi_stock_scores` row:

- **2 are explicitly filtered out**: CUE ($25.80) and NEO ($16.29), both Healthcare.
- **13 carry no sector at all** — expected, since only the top 300 by rank get sector enrichment.
  With a null sector `is_sector_filtered` returns False, so those are *not* excluded by it.
- 7 are in the universe on sector and price.

⚠ **So the filter explains 2 of 10 biotech misses, not 10.** Stated plainly because the tempting
version of this finding — "the sector filter is why we miss biotech themes" — is not what the data
says. The remaining 8 need the discovery-pool membership checked *on their own alert dates*, which
this read did not do (it used latest-row sector/price, an approximation).

## Limits — read these before acting on anything above

- **The 22 missed-theme rows span 2026-04-27 to 2026-05-06 — ten days.** The cluster shape is real
  for that window and is not evidence about any other period.
- The false-positive side spans April to July and is complete, so §1 and §2 are the sturdier half.
- 100 `themeless_winner` rows remain unlabelled; the false-negative RATE is therefore unknown. What
  §3 gives is a list of *named* misses, not a proportion.

## What this unblocks, and what it does not

- **Does not need more labels:** the crypto-to-AI-infrastructure definition problem (§2), and the
  named missed themes (§3). Both are actionable now.
- **Still needs the operator:** the theme-boost magnitude and the stage→credit mapping. Methodology,
  his call, unchanged.
