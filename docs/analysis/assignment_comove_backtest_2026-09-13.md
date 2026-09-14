# Assignment gate replay — the sector-identity test vs co-movement at 0.35 (2026-09-13)

**Owner**: `docs/architecture/theme_engine.md` (change log 2026-09-13). This is a finding, not an
owner. Pre-registration it is measured against: `cross_industry_themes_2026-09-13.md`
§PRE-REGISTRATION — the rows are NOT edited here; where a prediction is off, that is the finding.

**Reproduce** ($0, read-only pull + offline replay through the LIVE function):

```
bash scripts/probes/_assign_comove_pull.sh /tmp/acm          # five CSVs, COPY … TO STDOUT
python scripts/probes/_assign_comove_backtest.py /tmp/acm    # prints + writes /tmp/acm/results.md
```

**The decision it serves**: his sign-off on replacing the sector-identity test with co-movement at
0.35 (*"I thought I already signed it, you asked me earlier"*), and the pre-registered expectation
that the change is measured *"both positive and unintended consequences together, as well as
against our expectation"*. ⚖ THE LINE: the bar, the shape of the test and the toggle are his;
nothing was flipped by this document — the toggle row is untouched and no deploy was made.

## Method / population

**Population**: every stock↔theme pair the assignment LLM proposed in `mi_audit_log`
(`assignment_llm_proposed`, detail JSON) on the 60 nightly runs from 2026-06-17 to 2026-09-11 (the
last 60 SPY sessions in `mi_daily_closes`), n = 710 unique pairs per night; the sector verdict per
pair from `assignment_skipped_sector_outlier` (n = 141 rejected, 569 admitted — the only skip events
in the window); theme members from `mi_themes` rows (theme_date ≥ 2026-05-27, all stages); closes
from `mi_daily_closes` for members ∪ proposed names ∪ a per-sector control draw ∪ SPY from
2026-02-06; the nightly strip population from `theme_carryforward_filter_stripped` (n = 44 events).
- Every pair the assignment LLM proposed (`assignment_llm_proposed`, the audit trail) is judged by
  `theme_engine._comove_verdict` — the function the engine runs — on a `ComoveContext` built with
  `ep_theme_belonging`'s primitives from `mi_daily_closes`, over the 60 sessions STRICTLY BEFORE
  that pair's own night. No lookahead.
- The basket is what assignment saw: the prior night's row minus that night's recorded carryforward
  strip, plus the pairs the NEW rule admitted earlier in the same run; pairs thin for want of
  members get the engine's second pass (sector-admits first). The recorded strips are the
  sector-era ones — under the new rule some singletons would have been kept and never re-proposed,
  so the proposal population is slightly larger than the new engine's would be.
- "Sector admitted" = a proposal with no skip event of any kind that night (the only skip events in
  the window are sector-outlier ones); "on board that night" = the ticker is in that theme's row
  written that night, i.e. it also survived post-assignment LLM validation.
- The 2026-09-11 board is the 7-day-active mirror of `get_active_themes` (latest row per name, Retired
  dropped); tightness and the control are read on the 60 sessions to 09-11.

**Found by the replay, NOT pre-registered**: the bar is symmetric. The pre-registration modelled
add-backs only; the larger flow in pair-count is the refusals — 95 of 504 sector-admitted pairs are
below the bar, 75 of which had survived LLM validation and sat on the board. The list is in §2. It
is reported for his call on the shape (tape decides every pair, as built; or cross-sector pairs
only) — not pre-decided here.

## What this does not answer

- **What accumulates over weeks.** Every board number here is ONE night of add-backs onto the
  2026-09-11 board; P1's "≤5 share below 70% after 3 weeks", U3's volume drift and U4's naming
  drift need the live window (15+ trading days) the pre-registration asks for.
- **Whether the miners theme FORMS.** IREN is admitted on the historical night, but the theme is
  Retired today and discovery batches are still sector-sorted upstream; formation is a live
  question (P3).
- **The new engine's own proposal population.** The recorded carryforward strips are sector-era;
  under the new rule ~27 of the 58 stripped singletons would have stayed members and never been
  re-proposed, so the 710 is slightly larger than the new engine's nightly population would be.
- **What the LLM validation would do with the 88 newly admitted names.** They are admitted at the
  gate; post-assignment validation still runs on them and is not replayed here (it costs a call).
- **Trade returns.** Nothing here touches EP outcomes; the money-path read stops at "how many
  stocks carry the +10" (178 → 182).
- **Sample size on the 4 refused returning names.** MAX 0.35, AGX 0.33, FIVE 0.29, WLTH 0.24 sit
  within a few hundredths of the bar; a different 60-session window flips some of them (AGX was
  0.59 on 09-10 against the prior night's basket).

---

# Assignment-gate replay: sector-identity test vs co-movement at 0.35 — 2026-09-11

Window: the last 60 SPY sessions (2026-06-17 → 2026-09-11), 60 nightly runs with proposals. Every pair judged by the LIVE `theme_engine._comove_verdict` (leave-one-out, SPY-subtracted, 60 sessions strictly before the run date, basket >= 3 members with history, >= 30 overlapping sessions).

## 1. Denominators

| population | n |
|---|---|
| proposals the LLM made (unique stock↔theme pairs per night) | 710 |
| … rejected by the sector-identity test that night | 141 |
| … admitted by the sector test (no skip event of any kind) | 569 |
| … of the sector-admitted, on the theme's board that same night (survived validation) | 466 |
| other skip events in the window (exclusion / cooldown / kw / desc / not-found) | 0  |
| pairs the tape could judge | 602 |
| pairs it could NOT judge → sector test decides (fail-safe) | 108 {'unjudgeable:thin_basket': 88, 'unjudgeable:no_history': 5, 'no_prior_row': 15} |

## 2. Sector test vs co-movement test — the confusion table (judgeable pairs)

| sector test said | co-movement admits | co-movement rejects | total |
|---|---|---|---|
| admit | 409 | 95 | 504 |
| reject | 88 | 10 | 98 |

- **Admitted now, sector rejected**: 88 of 98 judgeable sector-rejections (90%).
- **Rejected now, sector admitted**: 95 of 504 judgeable sector-admissions (19%).
- Mean co-movement of sector-ADMITTED pairs 0.58 (n=504) vs sector-REJECTED pairs 0.65 (n=98) — the analysis measured 0.65 vs 0.61.

### Newly rejected, sector-admitted pairs (the bucket he has not seen)

| night | stock | theme | corr | overlap | basket | on board that night? |
|---|---|---|---|---|---|---|
| 2026-06-26 | BB | Network Security & Zero-Trust Edge | 0.26 | 60 | 5 | yes |
| 2026-06-26 | CORT | Peptide & Hormone Therapies for Metabolic & Endocrine D | 0.25 | 60 | 4 | yes |
| 2026-06-30 | PENG | AI Cloud GPU & Datacenter Colocation Platforms | 0.25 | 33 | 3 | yes |
| 2026-07-01 | LQDA | Rare & Orphan Disease Biotech Re-Rating | 0.24 | 60 | 5 | no |
| 2026-07-06 | LMND | Property & Casualty Insurance Underwriters | 0.26 | 60 | 14 | yes |
| 2026-07-07 | CVLT | Network Security & Zero-Trust Edge | 0.31 | 60 | 11 | yes |
| 2026-07-07 | LQDA | Rare & Orphan Disease Biotech | 0.17 | 60 | 6 | no |
| 2026-07-09 | BBIO | Rare & Orphan Disease Biotech | 0.35 | 60 | 5 | no |
| 2026-07-09 | CRNX | Rare & Orphan Disease Biotech | 0.30 | 60 | 5 | no |
| 2026-07-09 | LQDA | Rare & Orphan Disease Biotech | 0.17 | 60 | 5 | no |
| 2026-07-15 | HOOD | Wealth Management & Retail Brokerage Platforms | -0.01 | 60 | 6 | yes |
| 2026-08-11 | EMBJ | Aerospace Precision Components & Supply Chain | -0.09 | 31 | 3 | no |
| 2026-08-11 | FSK | Private Equity & Alternative Asset Management Platforms | 0.16 | 60 | 8 | yes |
| 2026-08-11 | HRMY | Specialty Pharmaceutical Commercialization & Rare Disea | 0.34 | 60 | 3 | yes |
| 2026-08-11 | INSM | Specialty Pharmaceutical Commercialization & Rare Disea | 0.27 | 60 | 6 | yes |
| 2026-08-11 | MAIN | Private Equity & Alternative Asset Management Platforms | 0.27 | 60 | 9 | yes |
| 2026-08-11 | ROAD | Industrial Construction Execution & On-Site Supply Chai | 0.29 | 60 | 3 | yes |
| 2026-08-11 | RTX | Aerospace Precision Components & Supply Chain | 0.14 | 31 | 3 | no |
| 2026-08-12 | BFH | Consumer Fintech & Digital Credit Platforms | 0.23 | 60 | 6 | yes |
| 2026-08-12 | BMRN | Specialty Pharmaceutical Commercialization & Rare Disea | 0.26 | 60 | 9 | yes |
| 2026-08-12 | EQPT | Industrial Equipment Rental & Material Handling | 0.33 | 60 | 3 | yes |
| 2026-08-12 | TDW | Oilfield Services & Drilling Rigs | 0.29 | 60 | 29 | yes |
| 2026-08-13 | BOX | Enterprise Unstructured Data Storage Infrastructure | -0.17 | 60 | 3 | yes |
| 2026-08-13 | HAPN | U.S. Regional & Mid-Cap Commercial Banks | 0.22 | 36 | 22 | yes |
| 2026-08-14 | LOAR | Defense Electronics & Aerospace Subsystem Suppliers | 0.18 | 60 | 8 | yes |
| 2026-08-17 | GKOS | Medical Device Mean-Reversion & Rotation Recovery | 0.29 | 60 | 9 | yes |
| 2026-08-17 | IVZ | Wealth Management & Retail Brokerage Platforms | 0.25 | 60 | 6 | yes |
| 2026-08-17 | NTNX | Enterprise Server, Storage & Data Infrastructure Hardwa | 0.06 | 60 | 6 | yes |
| 2026-08-17 | OMF | Consumer Fintech & Digital Credit Platforms | 0.32 | 60 | 8 | yes |
| 2026-08-18 | ATRO | Defense Electronics & Aerospace Subsystem Suppliers | 0.14 | 60 | 9 | yes |
| 2026-08-18 | AXGN | Medical Device Mean-Reversion & Rotation Recovery | 0.29 | 60 | 14 | yes |
| 2026-08-18 | BAND | Cloud Contact Center & CCaaS Communication Platforms | 0.33 | 60 | 4 | yes |
| 2026-08-18 | INSM | Rare disease/specialty pharma earnings beats | 0.07 | 60 | 3 | yes |
| 2026-08-18 | KNSA | Rare disease/specialty pharma earnings beats | 0.22 | 60 | 3 | yes |
| 2026-08-18 | NVCR | Medical Device Mean-Reversion & Rotation Recovery | 0.26 | 60 | 14 | yes |
| 2026-08-18 | PRCH | Digital Insurance Distribution & InsurTech Platforms | 0.05 | 60 | 3 | yes |
| 2026-08-18 | RYTM | Rare disease/specialty pharma earnings beats | 0.22 | 60 | 3 | yes |
| 2026-08-18 | TRAX | Inflammatory Disease & Immunology Biologics | 0.21 | 60 | 9 | no |
| 2026-08-18 | ZVRA | Rare disease/specialty pharma earnings beats | 0.29 | 60 | 3 | yes |
| 2026-08-19 | BMRN | Rare disease/specialty pharma earnings beats | 0.17 | 60 | 7 | no |
| 2026-08-19 | TVTX | Rare disease/specialty pharma earnings beats | 0.30 | 60 | 7 | no |
| 2026-08-20 | ELVN | Clinical-Stage Oncology & Hematology Biotech Breakout | 0.24 | 60 | 5 | yes |
| 2026-08-20 | FWRD | Trucking & Freight Logistics | 0.32 | 60 | 4 | yes |
| 2026-08-20 | HTGC | Private Equity & Alternative Asset Management Platforms | 0.29 | 60 | 13 | yes |
| 2026-08-20 | IDYA | Clinical-Stage Oncology & Hematology Biotech Breakout | 0.33 | 60 | 5 | yes |
| 2026-08-20 | KBR | Industrial Construction Execution & On-Site Supply Chai | 0.10 | 60 | 5 | yes |
| 2026-08-20 | RVMD | Clinical-Stage Oncology & Hematology Biotech Breakout | 0.34 | 60 | 5 | no |
| 2026-08-20 | RVMD | Emerging Oncology Therapeutics | 0.33 | 60 | 3 | no |
| 2026-08-21 | EME | Industrial Construction Execution & On-Site Supply Chai | 0.21 | 60 | 6 | yes |
| 2026-08-21 | HOOD | Wealth Management & Retail Brokerage Platforms | 0.01 | 60 | 11 | yes |
| 2026-08-21 | TTEK | Industrial Construction Execution & On-Site Supply Chai | 0.19 | 60 | 6 | yes |
| 2026-08-24 | DLTR | Defensive Consumer Staples Rotation | 0.35 | 60 | 8 | yes |
| 2026-08-24 | UTZ | Defensive Consumer Staples Rotation | 0.09 | 60 | 7 | yes |
| 2026-08-25 | CDNA | AI-Driven Diagnostics & Imaging Re-Rating | 0.14 | 60 | 5 | yes |
| 2026-08-25 | EME | Industrial Construction Execution & On-Site Supply Chai | 0.07 | 60 | 6 | yes |
| 2026-08-25 | FUBO | Video & Streaming Content Distribution Rebound | 0.22 | 42 | 3 | yes |
| 2026-08-25 | FUTU | Wealth Management & Retail Brokerage Platforms | 0.24 | 60 | 13 | yes |
| 2026-08-25 | INCY | Clinical-Stage Oncology & Hematology Biotech Breakout | 0.28 | 60 | 11 | yes |
| 2026-08-25 | INSM | Rare Disease & Specialty Drug Delivery Pharmaceuticals | 0.19 | 60 | 3 | yes |
| 2026-08-25 | MMED | Diabetes Management Devices (CGM, Insulin Pumps & Deliv | 0.32 | 60 | 3 | yes |
| 2026-08-25 | ORIC | Clinical-Stage Oncology & Hematology Biotech Breakout | 0.34 | 60 | 11 | yes |
| 2026-08-25 | PYPL | Consumer Fintech & Digital Credit Platforms | 0.08 | 60 | 7 | yes |
| 2026-08-26 | APAM | Wealth Management & Retail Brokerage Platforms | 0.30 | 60 | 14 | yes |
| 2026-08-26 | CELH | Defensive Consumer Staples Rotation | 0.30 | 60 | 16 | yes |
| 2026-08-26 | EME | Industrial Construction Execution & On-Site Supply Chai | 0.06 | 60 | 6 | yes |
| 2026-08-26 | ROKU | Video & Streaming Content Distribution Rebound | -0.03 | 60 | 3 | yes |
| 2026-08-27 | HONA | Defense Electronics & Aerospace Subsystem Suppliers | -0.07 | 41 | 6 | yes |
| 2026-08-27 | KSPI | Consumer Fintech & Digital Credit Platforms | 0.26 | 60 | 9 | yes |
| 2026-08-28 | TBBB | Defensive Consumer Staples Rotation | 0.33 | 60 | 19 | yes |
| 2026-08-31 | CHKP | Network Security & Zero-Trust Edge | 0.27 | 60 | 17 | yes |
| 2026-08-31 | HRMY | Rare & Orphan Disease Specialty Therapeutics | 0.10 | 58 | 3 | no |
| 2026-09-01 | MSFT | AI-Powered Enterprise Analytics & Intelligent Workflow  | 0.30 | 60 | 19 | yes |
| 2026-09-01 | NESR | Independent Oil Refining & Fuel Distribution | 0.25 | 60 | 48 | no |
| 2026-09-01 | XP | Wealth Management & Retail Brokerage Platforms | 0.26 | 60 | 19 | yes |
| 2026-09-02 | QURE | Genetic Medicine: Gene Editing & Gene Therapy Innovator | 0.23 | 60 | 4 | yes |
| 2026-09-03 | BHVN | Specialty & Rare Disease Pharmaceutical Innovators | 0.19 | 60 | 5 | no |
| 2026-09-03 | DGX | AI-Driven Diagnostics & Imaging Re-Rating | 0.27 | 60 | 6 | yes |
| 2026-09-03 | LH | AI-Driven Diagnostics & Imaging Re-Rating | 0.22 | 60 | 6 | yes |
| 2026-09-04 | BMRN | Rare Disease & Specialty Biopharmaceutical Innovators | -0.31 | 60 | 4 | yes |
| 2026-09-04 | ELVN | Oncology Therapeutics RS Turnaround | 0.35 | 60 | 6 | yes |
| 2026-09-04 | TVTX | Rare Disease & Specialty Biopharmaceutical Innovators | 0.12 | 60 | 4 | yes |
| 2026-09-08 | ORCL | AI-Powered Enterprise Analytics & Intelligent Workflow  | 0.04 | 60 | 14 | yes |
| 2026-09-08 | REPL | Oncology Therapeutics RS Turnaround | 0.32 | 58 | 11 | yes |
| 2026-09-08 | SRRK | Rare Disease & Specialty Biopharmaceutical Innovators | 0.27 | 60 | 6 | no |
| 2026-09-08 | TRAX | Inflammatory Disease & Immunology Biologics | 0.15 | 60 | 13 | yes |
| 2026-09-08 | VRDN | Rare Disease & Specialty Biopharmaceutical Innovators | 0.24 | 60 | 6 | no |
| 2026-09-08 | ZVRA | Rare Disease & Specialty Biopharmaceutical Innovators | 0.10 | 60 | 6 | no |
| 2026-09-09 | ACA | Industrial Construction Execution & On-Site Supply Chai | 0.18 | 60 | 6 | yes |
| 2026-09-09 | AGX | Industrial Construction Execution & On-Site Supply Chai | 0.09 | 60 | 6 | yes |
| 2026-09-09 | CME | Wealth Management & Retail Brokerage Platforms | 0.31 | 60 | 21 | no |
| 2026-09-09 | ZLAB | Oncology Therapeutics RS Turnaround | 0.10 | 60 | 15 | yes |
| 2026-09-10 | ACHC | Hospital & Behavioral Health Facility Procedure Volume  | 0.06 | 60 | 4 | yes |
| 2026-09-10 | FTK | Energy Supply Disruption: Strait of Hormuz Crisis | -0.10 | 60 | 66 | yes |
| 2026-09-10 | NESR | Energy Supply Disruption: Strait of Hormuz Crisis | 0.28 | 60 | 66 | yes |
| 2026-09-11 | WTTR | Energy Supply Disruption: Strait of Hormuz Crisis | 0.30 | 60 | 62 | no |

## 3. IREN — the headline case

- 2026-09-08: IREN → 'Emerging Bitcoin Miners Diversifying into AI/HPC Hosting' — sector test **rejected**; co-movement **admit** at corr=0.8255 over 60 sessions against 3 members (theme had 3 members that night, stage Fading).

## 4. The named checks from the analysis (0.35 separates every case measured)

| stock | expected | night | theme | corr | verdict |
|---|---|---|---|---|---|
| AGX | reject | 2026-09-08 | AI data-center power buildout | None | unjudgeable:thin_basket — |
| AGX | reject | 2026-09-10 | Diversified Power Generation Capacity Expansion fo | 0.5888 | admit ✗ |
| CMC | admit | 2026-09-09 | Global Steel & Metal Producers Recovery | 0.7606 | admit ✓ |
| ECO | reject | 2026-08-13 | Oilfield Services & Drilling Rigs | 0.5814 | admit ✗ |
| ECO | reject | 2026-08-14 | Oilfield Services & Drilling Rigs | 0.5802 | admit ✗ |
| ECO | reject | 2026-09-02 | Global Crude Oil Price Leverage: E&P, Integrated & | None | no_prior_row — |
| ECO | reject | 2026-09-08 | Global Oil & Gas Upstream, Integrated & Transport  | 0.3803 | admit ✗ |
| ECO | reject | 2026-09-09 | Oil & Product Tanker Shipping | 0.8111 | admit ✗ |
| ECO | reject | 2026-09-10 | Energy Supply Disruption: Strait of Hormuz Crisis | 0.2044 | reject ✓ |
| ECO | reject | 2026-09-11 | Oil & Product Tanker Shipping | 0.7967 | admit ✗ |
| GPN | admit | 2026-08-12 | Digital Payments Processing & Merchant Acquiring N | None | unjudgeable:thin_basket — |
| GPN | admit | 2026-08-13 | Digital Payments Processing & Merchant Acquiring N | None | unjudgeable:thin_basket — |
| GPN | admit | 2026-08-14 | B2B Digital Financial Infrastructure & Payment Rai | 0.633 | admit ✓ |
| GPN | admit | 2026-08-17 | Digital Payments Processing & Merchant Acquiring N | None | unjudgeable:thin_basket — |
| GPN | admit | 2026-08-18 | B2B Digital Financial Infrastructure & Payment Rai | 0.6685 | admit ✓ |
| GPN | admit | 2026-08-19 | Digital Payments Processing & Merchant Acquiring N | None | unjudgeable:thin_basket — |
| GPN | admit | 2026-08-20 | B2B Digital Financial Infrastructure & Payment Rai | 0.6914 | admit ✓ |
| GPN | admit | 2026-08-24 | B2B Digital Financial Infrastructure & Payment Rai | 0.6996 | admit ✓ |
| GPN | admit | 2026-08-25 | B2B Digital Financial Infrastructure & Payment Rai | 0.7 | admit ✓ |
| GPN | admit | 2026-08-26 | B2B Digital Financial Infrastructure & Payment Rai | 0.7089 | admit ✓ |
| GPN | admit | 2026-08-27 | B2B Digital Financial Infrastructure & Payment Rai | 0.7153 | admit ✓ |
| GPN | admit | 2026-08-28 | B2B Digital Financial Infrastructure & Payment Rai | 0.7196 | admit ✓ |
| GPN | admit | 2026-08-31 | B2B Digital Financial Infrastructure & Payment Rai | 0.6985 | admit ✓ |
| GPN | admit | 2026-09-03 | B2B Digital Financial Infrastructure & Payment Rai | 0.6958 | admit ✓ |
| GPN | admit | 2026-09-04 | B2B Digital Financial Infrastructure & Payment Rai | 0.6943 | admit ✓ |
| GPN | admit | 2026-09-08 | B2B Digital Financial Infrastructure & Payment Rai | 0.6856 | admit ✓ |
| GPN | admit | 2026-09-09 | B2B Digital Financial Infrastructure & Payment Rai | 0.729 | admit ✓ |
| GPN | admit | 2026-09-10 | B2B Digital Financial Infrastructure & Payment Rai | 0.732 | admit ✓ |
| GPN | admit | 2026-09-11 | B2B Digital Financial Infrastructure & Payment Rai | 0.7084 | admit ✓ |
| IREN | admit | 2026-09-08 | Emerging Bitcoin Miners Diversifying into AI/HPC H | 0.8255 | admit ✓ |
| MSTR | admit | 2026-08-25 | Corporate Digital Asset Treasury Vehicles | 0.8687 | admit ✓ |
| MSTR | admit | 2026-08-26 | Corporate Digital Asset Treasury Vehicles | 0.8797 | admit ✓ |
| MSTR | admit | 2026-08-27 | Corporate Digital Asset Treasury Vehicles | 0.8818 | admit ✓ |
| MSTR | admit | 2026-08-28 | Corporate Digital Asset Treasury Vehicles | 0.8722 | admit ✓ |
| MSTR | admit | 2026-08-31 | Corporate Digital Asset Treasury Vehicles | 0.8733 | admit ✓ |
| MSTR | admit | 2026-09-01 | Corporate Digital Asset Treasury Vehicles | 0.8735 | admit ✓ |
| MSTR | admit | 2026-09-02 | Corporate Digital Asset Treasury Vehicles | 0.8773 | admit ✓ |
| MSTR | admit | 2026-09-04 | Corporate Digital Asset Treasury Vehicles | 0.8802 | admit ✓ |
| MSTR | admit | 2026-09-08 | Bitcoin Treasury & Crypto Proxy Equities Correlati | 0.8536 | admit ✓ |
| MSTR | admit | 2026-09-09 | Bitcoin Treasury & Crypto Proxy Equities Correlati | 0.7775 | admit ✓ |
| MSTR | admit | 2026-09-10 | Bitcoin Treasury & Crypto Proxy Equities Correlati | 0.7805 | admit ✓ |
| MSTR | admit | 2026-09-11 | Corporate Bitcoin Treasury Holding Companies | 0.8423 | admit ✓ |

(not sector-rejected inside the window: ['OTTR', 'SEDG'])

## 5. Board effect on the last board (returning names)

- Expected-returning set reconstructed: **19** names blocked on sector during the window whose theme is live on 2026-09-11 and who are not members (the analysis expected ~26 under rule-OFF).
- Of those, **14 clear 0.35** and return; 4 are below the bar; 1 unjudgeable (stay out — sector test).

| board | themes | mean members | ≤5 members | <3 members |
|---|---|---|---|---|
| today (2026-09-11, 7-day active) | 119 | 6.03 | 83 (70%) | 21 |
| + returning names admitted at 0.35 | 119 | 6.15 | 79 (66%) | 21 |
| + returning − members the new test would have refused at assignment | 119 | 5.85 | 83 (70%) | 22 |

### Returning names, one row each

| stock | theme | stage | members | corr | verdict | nights blocked |
|---|---|---|---|---|---|---|
| MSTR | Bitcoin Treasury & Crypto Proxy Equities Correlation Ba | Nascent | 8 | 0.7817 | admit | 3 (last 2026-09-10) |
| CMC | Global Steel & Metal Producers Recovery | Nascent | 5 | 0.7558 | admit | 1 (last 2026-09-09) |
| ASC | Oil & Product Tanker Shipping | Accelerating | 17 | 0.7453 | admit | 1 (last 2026-09-11) |
| GPN | B2B Digital Financial Infrastructure & Payment Rails Mo | Fading | 9 | 0.7287 | admit | 15 (last 2026-09-11) |
| BAH | Defense Intelligence & Cybersecurity IT Contractors | Accelerating | 3 | 0.7275 | admit | 1 (last 2026-09-10) |
| BTU | Metallurgical & Thermal Coal Mining Rebound | Fading | 3 | 0.7275 | admit | 2 (last 2026-08-26) |
| HLN | Defensive Consumer Staples Rotation | Fading | 16 | 0.7218 | admit | 1 (last 2026-08-25) |
| CNR | Metallurgical & Thermal Coal Mining Rebound | Fading | 3 | 0.7145 | admit | 1 (last 2026-08-25) |
| ECO | Oil & Product Tanker Shipping | Accelerating | 17 | 0.6289 | admit | 2 (last 2026-09-11) |
| PACS | Skilled Nursing & Senior Housing Healthcare REITs | Accelerating | 5 | 0.4754 | admit | 2 (last 2026-09-11) |
| GWRE | Digital Insurance Distribution & InsurTech Platforms | Fading | 4 | 0.4461 | admit | 2 (last 2026-08-19) |
| EVER | Digital Insurance Distribution & InsurTech Platforms | Fading | 4 | 0.4056 | admit | 8 (last 2026-09-02) |
| BE | Diversified Power Generation Capacity Expansion for AI  | Nascent | 4 | 0.3834 | admit | 2 (last 2026-09-10) |
| VELO | Defense Electronics & Aerospace Subsystem Suppliers | Fading | 5 | 0.3671 | admit | 2 (last 2026-08-13) |
| MAX | Digital Insurance Distribution & InsurTech Platforms | Fading | 4 | 0.3456 | reject | 4 (last 2026-08-19) |
| AGX | Diversified Power Generation Capacity Expansion for AI  | Nascent | 4 | 0.3313 | reject | 1 (last 2026-09-10) |
| FIVE | Defensive Consumer Staples Rotation | Fading | 16 | 0.2911 | reject | 1 (last 2026-09-09) |
| WLTH | Wealth Management & Retail Brokerage Platforms | Fading | 20 | 0.2381 | reject | 1 (last 2026-09-10) |
| STDN | Uranium Mining & Nuclear Fuel Cycle Producers | Fading | 2 | None | unjudgeable:thin_basket | 1 (last 2026-09-08) |

## 6. Theme tightness before vs after, with the matched random-name control

Tightness = mean leave-one-out co-movement of each member with the rest (60 sessions to 2026-09-11). Control = the same theme with each returning name replaced by a random assignment-eligible stock from a sector the theme already accepts, 300 draws.

| theme | stage | adds | before | after | control mean | control beats real (of draws) |
|---|---|---|---|---|---|---|
| B2B Digital Financial Infrastructure & Payment Rai | Fading | GPN | 0.65 | 0.67 | 0.59 | 8/300 |
| Bitcoin Treasury & Crypto Proxy Equities Correlati | Nascent | MSTR | 0.75 | 0.76 | 0.67 | 0/300 |
| Defense Electronics & Aerospace Subsystem Supplier | Fading | VELO | 0.26 | 0.27 | 0.20 | 48/300 |
| Defense Intelligence & Cybersecurity IT Contractor | Accelerating | BAH | n/a | 0.56 | 0.29 | 0/300 |
| Defensive Consumer Staples Rotation | Fading | HLN | 0.55 | 0.57 | 0.53 | 36/300 |
| Digital Insurance Distribution & InsurTech Platfor | Fading | EVER, GWRE | 0.21 | 0.37 | 0.17 | 3/300 |
| Diversified Power Generation Capacity Expansion fo | Nascent | BE | 0.22 | 0.26 | 0.18 | 0/300 |
| Global Steel & Metal Producers Recovery | Nascent | CMC | 0.64 | 0.67 | 0.53 | 0/300 |
| Metallurgical & Thermal Coal Mining Rebound | Fading | BTU, CNR | n/a | 0.71 | 0.48 | 0/300 |
| Oil & Product Tanker Shipping | Accelerating | ASC, ECO | 0.64 | 0.63 | 0.61 | 15/300 |
| Skilled Nursing & Senior Housing Healthcare REITs | Accelerating | PACS | 0.84 | 0.76 | 0.80 | 158/300 |

- Across the 9 changed themes: mean tightness **0.53 → 0.55** (7 tighter, 2 looser); the random same-sector control lands at **0.48**.

## 7. Money-path exposure (U1) — stocks carrying the +10 theme bonus

- Distinct stocks in Accelerating/Mainstream themes today: **178**; after the returning names: **182** (+4). Baseline in the pre-registration: 178 → ~183.
- Returning names that land in a paying theme: ASC→'Oil & Product Tanker Shipping' (Accelerating), BAH→'Defense Intelligence & Cybersecurity IT ' (Accelerating), ECO→'Oil & Product Tanker Shipping' (Accelerating), PACS→'Skilled Nursing & Senior Housing Healthc' (Accelerating)

## 8. Starvation (P2) — nightly strips that left a theme under 3 members

- Sector-outlier strip events in the window: **44**; left the theme under 3: **27** before → **19** with the singleton re-judged by the tape (kept when it co-moves ≥ 0.35 with the rest, leave-one-out).
- Singleton-sector members stripped: 58; the tape would have kept **27** of them.

| night | theme | pre | post | stripped | kept by tape | post (new) |
|---|---|---|---|---|---|---|
| 2026-06-23 | Crude & Product Tanker Shipping | 6 | 5 | ECO | ECO (0.89) | 6 |
| 2026-07-07 | Satellite Communications & Space Data Service | 4 | 3 | VSAT | VSAT (0.68) | 4 |
| 2026-07-09 | Bitcoin Mining & Crypto Infrastructure Operat | 3 | 2 | HUT | HUT (0.73) | 3 |
| 2026-07-09 | Non-US & Frontier Market Digital Financial Se | 4 | 2 | FRHC, SE | — | 2 |
| 2026-07-16 | Digital Advertising Technology Platforms | 3 | 2 | APPS | — | 2 |
| 2026-07-20 | Global Crude & Product Tanker Fleet Operators | 7 | 6 | ECO | ECO (0.90) | 7 |
| 2026-07-27 | Global Steel & Metal Producers Recovery | 3 | 2 | CMC | CMC (0.69) | 3 |
| 2026-07-31 | US-China Tariff Truce — Consumer Goods & Digi | 3 | 2 | SONO | — | 2 |
| 2026-08-05 | U.S. Government/Defense Contract Surge | 3 | 1 | PLTR, VOYG | PLTR (0.37), VOYG (0.64) | 3 |
| 2026-08-05 | U.S. Government/Defense Spending Surge | 3 | 1 | PLTR, VOYG | PLTR (0.37), VOYG (0.64) | 3 |
| 2026-08-10 | U.S. Government/Defense Contract Surge | 3 | 2 | VOYG | — | 2 |
| 2026-08-10 | U.S. Government/Defense Contract Surge | 3 | 2 | VOYG | — | 2 |
| 2026-08-10 | U.S. Government/Defense Contract Surge | 3 | 2 | VOYG | — | 2 |
| 2026-08-12 | Digital Payments Processing & Merchant Acquir | 3 | 2 | PYPL | — | 2 |
| 2026-08-12 | Oilfield Services & Drilling Rigs | 14 | 13 | OTTR | OTTR (0.60) | 14 |
| 2026-08-13 | AI data center infrastructure buildout | 7 | 4 | FLNC, NBIS | FLNC (0.55), NBIS (0.81) | 6 |
| 2026-08-13 | AI Data-Center Power & Physical Infrastructur | 5 | 2 | CSQR, FRMI, STDN | — | 2 |
| 2026-08-13 | Electrical Connectivity & Utility Network Har | 3 | 2 | BDC | — | 2 |
| 2026-08-13 | Nuclear Fuel Cycle & Microreactor Development | 4 | 2 | OKLO, UUUU | OKLO (0.89), UUUU (0.85) | 4 |
| 2026-08-17 | Nuclear Fuel Cycle & Microreactor Development | 3 | 2 | UUUU | UUUU (0.82) | 3 |
| 2026-08-19 | Data & Analytics-as-a-Service Providers | 3 | 1 | IQV, ITRI | — | 1 |
| 2026-08-19 | Data & Analytics-as-a-Service Providers | 3 | 1 | IQV, ITRI | — | 1 |
| 2026-08-20 | Corporate Digital Asset Treasury Vehicles | 4 | 3 | MSTR | MSTR (0.86) | 4 |
| 2026-08-20 | Corporate Digital Asset Treasury Vehicles | 4 | 3 | MSTR | MSTR (0.86) | 4 |
| 2026-08-21 | Bitcoin Mining & Digital Asset Infrastructure | 3 | 2 | BTDR | BTDR (0.76) | 3 |
| 2026-08-21 | Data & Analytics-as-a-Service Providers | 3 | 1 | IQV, ITRI | — | 1 |
| 2026-08-25 | Bitcoin Mining & HPC Compute Pivot Operators | 5 | 4 | CIFR | CIFR (0.90) | 5 |
| 2026-08-25 | Wood-Based Building Materials Distribution | 3 | 2 | BLDR | — | 2 |
| 2026-08-26 | Altcoin & Diversified Digital-Asset Infrastru | 4 | 3 | BLSH | BLSH (0.61) | 4 |
| 2026-08-27 | Altcoin & Diversified Digital-Asset Infrastru | 4 | 3 | BLSH | — | 3 |
| 2026-08-27 | Bitcoin Miner to AI/HPC Data Center Conversio | 4 | 3 | CIFR | CIFR (0.91) | 4 |
| 2026-08-28 | Bitcoin Miners Pivoting to AI/HPC Data Center | 5 | 4 | CIFR | CIFR (0.92) | 5 |
| 2026-08-28 | Emerging Defense & Aerospace Hardware Supplie | 4 | 3 | UMAC | UMAC (0.77) | 4 |
| 2026-08-28 | Power Generation Buildout for AI Data Center  | 4 | 2 | DEC, HNRG | — | 2 |
| 2026-09-01 | Buy Now Pay Later & Point-of-Sale Consumer Cr | 3 | 2 | PGY | — | 2 |
| 2026-09-01 | Pure-Play Agricultural Tractor & Farm Machine | 6 | 4 | BG, CTVA | — | 4 |
| 2026-09-02 | Management & Business Advisory Consulting Fir | 3 | 2 | GIB | — | 2 |
| 2026-09-03 | Buy Now Pay Later & AI Consumer Lending | 3 | 2 | PGY | — | 2 |
| 2026-09-03 | Buy Now Pay Later & Point-of-Sale Consumer Cr | 3 | 2 | PGY | — | 2 |
| 2026-09-03 | Farm Economy Value Chain Re-Rating | 9 | 8 | BG | BG (0.38) | 9 |
| 2026-09-04 | Bitcoin Mining Equities Momentum Basket | 6 | 5 | CIFR | CIFR (0.92) | 6 |
| 2026-09-04 | Brazil/LatAm Macro Risk-On Rotation | 5 | 2 | PAGS, PAM, SUZ | PAGS (0.71), PAM (0.50) | 4 |
| 2026-09-08 | Buy Now Pay Later & Point-of-Sale Consumer Cr | 3 | 2 | PGY | — | 2 |
| 2026-09-11 | Senior Care Services & Real Estate Value Chai | 4 | 3 | GRDN | — | 3 |

## 9. Against the pre-registration, row by row

| row | expectation / risk | this replay reads |
|---|---|---|
| P1 themes hold more members | avg 4.7 at birth → 6.3 peak; 83 of 119 ≤5 | add-backs alone: mean members 6.03 → 6.15, ≤5 share 70% → 66%; add-backs MINUS the members the tape would have refused at assignment: 5.85, 70% — one night on the 2026-09-11 board. **P1 may REFUTE under the symmetric bar**: 95 refusals vs 88 admits over the window means the member count is more likely to fall than rise over weeks; narrowing the tape to cross-sector pairs only would remove that risk — his call |
| P2 fewer themes starved under 3 | 29 of 46 strips left a theme under 3 | 27 of 44 → 19 of 44 in this window |
| P3 his four concepts formable | IREN blocked from the theme named after it | IREN admit at 0.8255 on 2026-09-08 — formation itself needs the live run (the theme is Retired today) |
| P4 membership rejections fall | 167 of 824 (20%) rejected on sector | sector rejections 98 → 10 of the judgeable ones stay rejected on the tape (95 sector-admitted pairs newly rejected); unjudgeable pairs (108) keep the sector verdict |
| U1 EP score moves | 178 boosted stocks, 4 bonus-dependent HIGHs / 90d | boosted stocks 178 → 182 on this board |
| U2 tightness falls | ~1 in 7 readmitted is junk | mean tightness 0.53 → 0.55 across changed themes; control 0.48; 4 of 19 blocked names are refused by the bar |
| U3 volume overshoots ~26 | assignment LLM never told cross-sector is allowed | 14 return on this board (of 19 candidates); the prompt has NO sector rule (checked: 'Only assign if the business CLEARLY matches the thesis'), so a drift beyond this needs the live weeks |
| U4 names get vaguer | rename / mass-removal events | not measurable offline — live tripwire |
| U5 nothing changes (batching binds) | P1–P4 flat | 88 of 98 sector-rejected pairs flip to admit on the historical nights — the gate WAS binding for those |
