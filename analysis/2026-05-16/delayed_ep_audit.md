# Delayed-EP downstream capture audit

_For each MAGNA53 HIGH alert in 60d that FAILED Day 1 (stopped, no-entry, skipped, or no trade-row), check the next 21 days for downstream pickup by 9M EP / sugar-baby / continuation-flag / subsequent MAGNA53 EP detectors._

## Day-1 outcome distribution

| Class | N |
|---|---:|
| WON_DAY1 | 2 |
| LOST_DAY1 | 9 |
| NO_ENTRY | 11 |
| SKIPPED | 75 |
| NO_TRADE_ROW | 17 |

Total HIGH alerts in 60d: **115**. Failed Day 1: **112**. Won Day 1: **2**.

## Downstream capture rate for failed-Day-1 names

| Downstream detector | Captured | N failed | Rate |
|---|---:|---:|---:|
| Next 9M EP within 21d | 5 | 112 | 4.5% |
| Next 9M sugar baby within 21d | 0 | 112 | 0.0% |
| Next flag (COILED/TRIGGERED/WATCH) within 21d | 34 | 112 | 30.4% |
| Next MAGNA53 EP within 21d | 0 | 112 | 0.0% |
| **ANY downstream pickup** | **37** | **112** | **33.0%** |

## Alpha left on the table

Of 110 failed-Day-1 names with 21d forward data, **76 (69.1%)** made a high more than 5% above gap-day open within 21 trading days. This is the population the delayed-EP capture would target.

**Capture rate among ALPHA names** (failed Day 1 BUT made +5% within 21d): **26 / 76 = 34.2%**

### Detector contribution on alpha names

| Detector | Alpha captured | Alpha total | Rate |
|---|---:|---:|---:|
| 9M EP | 4 | 76 | 5.3% |
| Sugar baby | 0 | 76 | 0.0% |
| Continuation flag | 24 | 76 | 31.6% |
| Next MAGNA53 EP | 0 | 76 | 0.0% |

## TRT 4/23 fixture (delayed-EP exemplar)

TRT not in MAGNA53 HIGH cohort — was a 9M EP (parallel methodology). Confirmed cohort boundary; pull a 9M-cohort version of this audit for full TRT chronology.

## Failed-Day-1 alpha names — full chronology

| Ticker | Alert | Day1 | 9M EP | Sugar Baby | Flag | Next EP | MFE 21d |
|---|---|---|---|---|---|---|---:|
| ARX | 2026-05-14 | SKIPPED | — | — | — | — | +14.4% |
| CPA | 2026-05-14 | SKIPPED | — | — | — | — | +6.1% |
| KLAR | 2026-05-14 | LOST_DAY1 | — | — | — | — | +7.5% |
| AIP | 2026-05-13 | SKIPPED | — | — | — | — | +8.6% |
| AMBQ | 2026-05-12 | SKIPPED | — | — | — | — | +38.7% |
| PACS | 2026-05-12 | SKIPPED | — | — | — | — | +10.2% |
| SE | 2026-05-12 | SKIPPED | — | — | — | — | +5.6% |
| SIBN | 2026-05-12 | SKIPPED | — | — | — | — | +18.3% |
| VG | 2026-05-12 | SKIPPED | — | — | — | — | +14.5% |
| VPG | 2026-05-12 | SKIPPED | — | — | — | — | +25.3% |
| VSTS | 2026-05-12 | SKIPPED | — | — | — | — | +7.0% |
| ZBRA | 2026-05-12 | SKIPPED | — | — | — | — | +5.0% |
| MRAM | 2026-05-11 | LOST_DAY1 | — | — | — | — | +42.7% |
| AKAM | 2026-05-08 | SKIPPED | — | — | — | — | +13.8% |
| BILL | 2026-05-08 | SKIPPED | — | — | — | — | +6.2% |
| CALY | 2026-05-08 | SKIPPED | — | — | — | — | +12.7% |
| FROG | 2026-05-08 | SKIPPED | — | — | 2026-05-14 | — | +8.0% |
| INOD | 2026-05-08 | SKIPPED | — | — | 2026-05-15 | — | +57.4% |
| LASR | 2026-05-08 | SKIPPED | — | — | 2026-05-14 | — | +12.7% |
| WEST | 2026-05-08 | SKIPPED | — | — | 2026-05-15 | — | +30.7% |
| WLDN | 2026-05-08 | SKIPPED | — | — | 2026-05-15 | — | +25.6% |
| FLNC | 2026-05-07 | SKIPPED | — | — | — | — | +42.6% |
| FTNT | 2026-05-07 | SKIPPED | — | — | — | — | +17.2% |
| MTSI | 2026-05-07 | SKIPPED | — | — | — | — | +13.4% |
| PCT | 2026-05-07 | SKIPPED | 2026-05-14 | — | — | — | +38.9% |
| SEZL | 2026-05-07 | SKIPPED | — | — | 2026-05-13 | — | +5.8% |
| SITM | 2026-05-07 | SKIPPED | — | — | — | — | +8.0% |
| AMD | 2026-05-06 | LOST_DAY1 | — | — | — | — | +14.6% |
| BLMN | 2026-05-06 | SKIPPED | — | — | 2026-05-12 | — | +23.6% |
| CRI | 2026-05-06 | SKIPPED | — | — | — | — | +12.1% |
| FLEX | 2026-05-06 | NO_ENTRY | — | — | — | — | +22.9% |
| GEO | 2026-05-06 | NO_ENTRY | — | — | 2026-05-12 | — | +10.5% |
| GLW | 2026-05-06 | SKIPPED | 2026-05-08 | — | — | — | +11.8% |
| HUT | 2026-05-06 | SKIPPED | — | — | 2026-05-12 | — | +10.5% |
| LIVN | 2026-05-06 | SKIPPED | — | — | — | — | +20.2% |
| SMCI | 2026-05-06 | LOST_DAY1 | — | — | — | — | +15.7% |
| CYRX | 2026-05-05 | SKIPPED | — | — | 2026-05-14 | — | +25.4% |
| EVER | 2026-05-05 | SKIPPED | — | — | — | — | +24.1% |
| IART | 2026-05-05 | SKIPPED | — | — | 2026-05-12 | — | +23.8% |
| STRL | 2026-05-05 | SKIPPED | — | — | 2026-05-12 | — | +22.8% |
| AXTI | 2026-05-01 | SKIPPED | — | — | 2026-05-15 | — | +70.1% |
| TEAM | 2026-05-01 | LOST_DAY1 | — | — | 2026-05-08 | — | +16.2% |
| TWLO | 2026-05-01 | NO_ENTRY | — | — | 2026-05-14 | — | +14.6% |
| BAND | 2026-04-30 | SKIPPED | — | — | 2026-05-15 | — | +82.1% |
| FTAI | 2026-04-30 | SKIPPED | — | — | — | — | +24.0% |
| BE | 2026-04-29 | SKIPPED | — | — | 2026-05-05 | — | +12.1% |
| NXPI | 2026-04-29 | SKIPPED | — | — | 2026-05-05 | — | +9.0% |
| STX | 2026-04-29 | SKIPPED | — | — | 2026-05-11 | — | +25.9% |
| CVLT | 2026-04-28 | SKIPPED | — | — | — | — | +9.2% |
| KFRC | 2026-04-28 | SKIPPED | — | — | 2026-05-05 | — | +18.8% |
| CRML | 2026-04-27 | SKIPPED | 2026-04-30 | — | 2026-05-04 | — | +14.8% |
| INTC | 2026-04-24 | LOST_DAY1 | — | — | — | — | +61.5% |
| URI | 2026-04-23 | SKIPPED | — | — | — | — | +6.2% |
| WST | 2026-04-23 | SKIPPED | — | — | — | — | +7.4% |
| NMAX | 2026-04-22 | SKIPPED | — | — | — | — | +27.9% |
| CADL | 2026-04-20 | NO_ENTRY | — | — | — | — | +45.0% |
| CMPS | 2026-04-20 | SKIPPED | 2026-04-21 | — | 2026-05-04 | — | +15.3% |
| GHRS | 2026-04-20 | SKIPPED | — | — | 2026-05-06 | — | +6.7% |
| NKTR | 2026-04-20 | SKIPPED | — | — | — | — | +9.2% |
| USAX | 2026-04-20 | NO_TRADE_ROW | — | — | — | — | +68.9% |
| USGG | 2026-04-20 | SKIPPED | — | — | — | — | +65.7% |
| AEHR | 2026-04-16 | NO_ENTRY | — | — | 2026-05-04 | — | +21.0% |
| TVTX | 2026-04-14 | NO_TRADE_ROW | — | — | — | — | +17.0% |
| TH | 2026-04-01 | SKIPPED | — | — | — | — | +29.8% |
| EEIQ | 2026-03-30 | SKIPPED | — | — | — | — | +12.3% |
| KOD | 2026-03-26 | NO_TRADE_ROW | — | — | — | — | +31.8% |
| ANNA | 2026-03-24 | NO_TRADE_ROW | — | — | — | — | +54.0% |
| KPTI | 2026-03-24 | NO_TRADE_ROW | — | — | — | — | +47.2% |
| ARMG | 2026-03-20 | NO_TRADE_ROW | — | — | — | — | +40.1% |
| ARTL | 2026-03-20 | NO_TRADE_ROW | — | — | — | — | +137.0% |
| FLY | 2026-03-20 | NO_TRADE_ROW | — | — | — | — | +62.5% |
| PL | 2026-03-20 | NO_TRADE_ROW | — | — | — | — | +13.9% |
| SCHL | 2026-03-20 | NO_TRADE_ROW | — | — | — | — | +5.4% |
| SMCZ | 2026-03-20 | NO_TRADE_ROW | — | — | — | — | +18.7% |
| YSS | 2026-03-20 | NO_TRADE_ROW | — | — | — | — | +84.3% |
| TWO | 2026-03-19 | NO_TRADE_ROW | — | — | — | — | +9.9% |
