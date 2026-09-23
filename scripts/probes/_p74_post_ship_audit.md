# Delayed-EP downstream capture audit

_For each MAGNA53 HIGH alert in 60d that FAILED Day 1 (stopped, no-entry, skipped, or no trade-row), check the next 21 days for downstream pickup by 9M EP / sugar-baby / continuation-flag / subsequent MAGNA53 EP detectors._

## Day-1 outcome distribution

| Class | N |
|---|---:|
| WON_DAY1 | 1 |
| LOST_DAY1 | 2 |
| NO_ENTRY | 6 |
| SKIPPED | 3 |
| NO_TRADE_ROW | 84 |

Total HIGH alerts in 60d: **96**. Failed Day 1: **95**. Won Day 1: **1**.

## Downstream capture rate for failed-Day-1 names

| Downstream detector | Captured | N failed | Rate |
|---|---:|---:|---:|
| Next 9M EP within 21d | 9 | 95 | 9.5% |
| Next 9M sugar baby within 21d | 0 | 95 | 0.0% |
| Next flag (COILED/TRIGGERED/WATCH) within 21d | 3 | 95 | 3.2% |
| Next MAGNA53 EP within 21d | 1 | 95 | 1.1% |
| **ANY downstream pickup** | **13** | **95** | **13.7%** |

## Alpha left on the table

Of 87 failed-Day-1 names with 21d forward data, **56 (64.4%)** made a high more than 5% above gap-day open within 21 trading days. This is the population the delayed-EP capture would target.

**Capture rate among ALPHA names** (failed Day 1 BUT made +5% within 21d): **10 / 56 = 17.9%**

### Detector contribution on alpha names

| Detector | Alpha captured | Alpha total | Rate |
|---|---:|---:|---:|
| 9M EP | 6 | 56 | 10.7% |
| Sugar baby | 0 | 56 | 0.0% |
| Continuation flag | 3 | 56 | 5.4% |
| Next MAGNA53 EP | 1 | 56 | 1.8% |

## TRT 4/23 fixture (delayed-EP exemplar)

TRT not in MAGNA53 HIGH cohort — was a 9M EP (parallel methodology). Confirmed cohort boundary; pull a 9M-cohort version of this audit for full TRT chronology.

## Failed-Day-1 alpha names — full chronology

| Ticker | Alert | Day1 | 9M EP | Sugar Baby | Flag | Next EP | MFE 21d |
|---|---|---|---|---|---|---|---:|
| MTW | 2026-08-07 | NO_TRADE_ROW | — | — | — | — | +12.5% |
| ONTO | 2026-08-07 | NO_TRADE_ROW | — | — | — | — | +5.3% |
| QNST | 2026-08-07 | NO_TRADE_ROW | — | — | — | — | +13.2% |
| TEAM | 2026-08-07 | NO_TRADE_ROW | — | — | — | — | +6.1% |
| TWLO | 2026-08-07 | NO_TRADE_ROW | — | — | — | — | +8.6% |
| AEVA | 2026-08-06 | NO_TRADE_ROW | — | — | — | — | +9.7% |
| CAI | 2026-08-06 | NO_TRADE_ROW | — | — | — | — | +23.4% |
| DCTH | 2026-08-06 | NO_TRADE_ROW | — | — | — | — | +19.0% |
| INSM | 2026-08-06 | NO_TRADE_ROW | — | — | — | — | +5.7% |
| LFST | 2026-08-06 | NO_TRADE_ROW | 2026-08-10 | — | — | — | +13.1% |
| RDW | 2026-08-06 | NO_TRADE_ROW | — | — | — | — | +13.2% |
| SITM | 2026-08-06 | NO_TRADE_ROW | — | — | — | — | +11.4% |
| U | 2026-08-06 | NO_TRADE_ROW | — | — | — | — | +23.2% |
| APPS | 2026-08-05 | NO_TRADE_ROW | — | — | — | — | +28.3% |
| HGTY | 2026-08-05 | NO_TRADE_ROW | — | — | — | — | +10.1% |
| KTOS | 2026-08-05 | NO_TRADE_ROW | — | — | — | — | +7.3% |
| LIFE | 2026-08-04 | NO_TRADE_ROW | — | — | — | — | +20.2% |
| PLTR | 2026-08-04 | NO_TRADE_ROW | — | — | — | — | +23.7% |
| TSAT | 2026-08-04 | NO_TRADE_ROW | — | — | — | — | +38.1% |
| VOYG | 2026-08-04 | NO_TRADE_ROW | — | — | — | — | +28.2% |
| ZBRA | 2026-08-04 | NO_TRADE_ROW | — | — | — | — | +16.2% |
| FTK | 2026-08-03 | NO_TRADE_ROW | — | — | — | — | +53.0% |
| LIND | 2026-08-03 | NO_TRADE_ROW | — | — | — | — | +12.7% |
| BLZE | 2026-07-31 | NO_TRADE_ROW | — | — | — | 2026-08-04 | +78.1% |
| FET | 2026-07-31 | NO_TRADE_ROW | — | — | — | — | +29.3% |
| ARM | 2026-07-30 | NO_TRADE_ROW | — | — | — | — | +16.0% |
| CORT | 2026-07-30 | NO_TRADE_ROW | — | — | — | — | +5.8% |
| EME | 2026-07-30 | NO_TRADE_ROW | — | — | — | — | +8.9% |
| PWR | 2026-07-30 | NO_TRADE_ROW | — | — | — | — | +9.4% |
| SIMO | 2026-07-30 | NO_TRADE_ROW | — | — | — | — | +5.8% |
| TER | 2026-07-29 | NO_TRADE_ROW | — | — | — | — | +11.4% |
| TEVA | 2026-07-29 | NO_TRADE_ROW | — | — | — | — | +7.3% |
| CORZ | 2026-07-28 | NO_TRADE_ROW | 2026-07-30 | — | — | — | +12.6% |
| NNE | 2026-07-27 | NO_TRADE_ROW | — | — | — | — | +15.8% |
| QBTS | 2026-07-27 | NO_TRADE_ROW | — | — | — | — | +23.2% |
| THC | 2026-07-24 | NO_TRADE_ROW | — | — | — | — | +12.9% |
| NVCR | 2026-07-23 | NO_TRADE_ROW | — | — | — | — | +19.2% |
| ARWR | 2026-07-22 | NO_TRADE_ROW | — | — | — | — | +6.3% |
| SMCI | 2026-07-22 | NO_TRADE_ROW | — | — | — | — | +15.6% |
| HAS | 2026-07-21 | NO_TRADE_ROW | — | — | — | — | +14.8% |
| HUT | 2026-07-20 | NO_TRADE_ROW | — | — | — | — | +18.6% |
| IREN | 2026-07-20 | NO_TRADE_ROW | — | — | — | — | +20.1% |
| AEHR | 2026-07-15 | NO_TRADE_ROW | — | — | — | — | +13.1% |
| MANE | 2026-07-15 | NO_TRADE_ROW | — | — | — | — | +5.4% |
| CLSK | 2026-07-14 | NO_TRADE_ROW | 2026-07-15 | — | — | — | +9.6% |
| PENG | 2026-07-08 | SKIPPED | 2026-07-09 | — | — | — | +32.4% |
| AVAV | 2026-06-30 | NO_TRADE_ROW | — | — | — | — | +13.5% |
| ABSI | 2026-06-24 | NO_TRADE_ROW | — | — | 2026-07-06 | — | +26.8% |
| FCEL | 2026-06-24 | NO_TRADE_ROW | 2026-06-26 | — | — | — | +50.9% |
| DFTX | 2026-06-22 | NO_ENTRY | — | — | 2026-07-07 | — | +27.5% |
| MLTX | 2026-06-22 | NO_ENTRY | — | — | — | — | +11.5% |
| SYRE | 2026-06-22 | LOST_DAY1 | — | — | — | — | +7.4% |
| SWBI | 2026-06-18 | NO_ENTRY | — | — | — | — | +10.8% |
| RXT | 2026-06-16 | NO_ENTRY | 2026-06-17 | — | — | — | +27.1% |
| AKTS | 2026-06-12 | SKIPPED | — | — | — | — | +60.1% |
| SHAZ | 2026-06-12 | NO_ENTRY | — | — | 2026-06-16 | — | +30.7% |
