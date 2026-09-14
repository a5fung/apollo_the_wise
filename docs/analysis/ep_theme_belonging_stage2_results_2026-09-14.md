# EP theme-belonging — STAGE 2 RESULTS (run 2026-09-14, US$1.79 actual)

> **This is the raw run output.** The reading that matters is at the top; the tables below are the
> machine's, unedited. Method + stage 1 live in `ep_theme_belonging_backtest_2026-09-13.md`.

## THE ANSWER, in the order the operator asked for it

**1. All four nonsense matches he caught are REJECTED.** Every one, with a reason that names the
business rather than the correlation:

| his case | shortlisted at | verdict |
|---|---|---|
| Dominion Energy → Hydraulic Fracturing | 0.45 | **rejected** — "regulated electricity and natural gas distribution/transmission utility" |
| Bakkt → Satellite Imagery | 0.49 | **rejected** — "digital asset brokerage infrastructure" |
| QBTS → Satellite Imagery | 0.41 | **rejected** — "quantum computing systems, hardware & software" |
| Compass Pathways → Custom AI Silicon | 0.38 | **rejected** — "psilocybin-based therapy and mental health biotech" |

The judgement rejects **160 of the 173** names correlation alone would have paid (92%). Correlation
at 0.35 on its own would have boosted **173 of 346 alerts**; the two-stage rule boosts **11**. That
gap IS the fix — the bar he called clearly wrong is doing almost none of the deciding.

**2. The money path is one alert in 120 days.** Newly boosted 11; already HIGH without the bonus 9;
**definite new HIGH crossings: 1** (GFS 2026-05-21, 56.4 → 68.4 against a 65 bar). Zero ambiguous.

**3. A correction to our own number, again in the conservative direction.** Only **2** alerts are
HIGH today because of the +10 at their own era bar (MRVL 08-19, ERO 09-08) — not the 4 I reported
(AEHR/BLZE/HOOD/SNOW), which was read at a flat 70 instead of each era's real bar.

## 🔴 AND THE ONE HE MUST RULE ON — IREN, his own #491 case, is REJECTED

**The fix does not deliver the case that motivated it, and the reason is NOT the judgement.**

On 2026-07-20 IREN's paying-stage shortlist held *Custom AI Silicon* (0.53) and *Semiconductor Wafer
Foundry* (0.44). IREN is neither, so the judge rejected it — **correctly**.

**The right theme was there and could not pay.** Against the Nascent shortlist the judge CONFIRMS
IREN to *Bitcoin Mining & Crypto Infrastructure Operators* at correlation **0.80**, saying IREN is
"a pure-play Bitcoin miner and data center/computing infrastructure operator explicitly named as a
member of this" theme. **That theme was Nascent, and `ep_detector.py:3186` pays only Accelerating
and Mainstream.**

So the belonging fix is working and the remaining gap is the **Nascent exclusion** — the same defect
#368 found, now measured on his own must-work case rather than in the abstract.

**What Nascent would add: 11 more confirmed alerts, roughly DOUBLING the reach (11 → 22 of 346), for
1 more definite new HIGH crossing.** Named, with the judgement's correlation: IREN 0.80 · RIOT 0.87 ·
COHU 0.80 · HUT 0.75 · ALAB 0.75 · MPWR 0.71 · CAMT 0.68 · CLF 0.61 · KTOS 0.59 · MTW 0.52 ·
PHVS 0.36.

⚖ **Letting Nascent pay is a detection criterion — CHANGE_PROCESS + his sign-off. Not pre-decided
here, and not bundled into the deploy.** The numbers above are the evidence he would rule on.

---

n = 346 EP alerts. Board as-of each alert reconstructed from mi_themes (7-day recency, Retired dropped).

## Stage 1 — listed / shortlisted (correlation is a FILTER)

| | count | of |
|---|---|---|
| listed on a paying-stage list (reconstructed as-of the alert day) | 25 | 346 |
| listed per the stored `in_active_theme` flag | 22 | 346 |
| reconstruction agrees with the stored flag | 341 | 346 |
| unlisted AND shortlisted against a paying-stage basket at >= 0.35 (= what correlation ALONE would have paid) | 173 | 346 |
| unlisted with a Nascent shortlist | 99 | 346 |
| shortlisted but no description anywhere (judgement refused) | 2 | 346 |

Baskets the max ran over, per alert: paying-stage mean 16.9 (min 4, max 51); Nascent mean 7.6 (max 35).

## Stage 2 — the fit judgement decides (theme_engine.judge_theme_fit, the nightly pass's own question)

| | count | of |
|---|---|---|
| **list only (today's rule)** | **25** | 346 |
| shortlisted and CONFIRMED by the judgement | 11 | 173 shortlisted |
| shortlisted and REJECTED by the judgement | 160 | 173 shortlisted |
| shortlisted, no verdict (no description / failed) -> list membership decides | 2 | 173 shortlisted |
| **belonging = listed OR confirmed fit** | **36** | 346 |
| **newly boosted (unlisted, confirmed)** | **11** | 346 |
| for reference — correlation ALONE at 0.35 would have newly boosted | 173 | 346 |

## The named cases

| date | ticker | shortlist (theme @ corr) | verdict | rationale |
|---|---|---|---|---|
| 2026-05-18 | CMPS (WRONG-CASE) | Custom AI Silicon & Chip Architecture Licensing @ 0.38, AI Datacenter Silicon @ 0.35 | rejected | CMPS: Core business is psilocybin-based therapy and mental health biotech (clinical-stage pharmaceutical). Candidate themes: "Custom AI Silicon & Chip Architect |
| 2026-05-18 | D (WRONG-CASE) | Hydraulic Fracturing & Well Completion Services @ 0.45 | rejected | D (Dominion Energy): Core business is regulated electricity and natural gas distribution/transmission utility. The only existing theme is "Hydraulic Fracturing  |
| 2026-05-19 | BKKT (WRONG-CASE) | Satellite Imagery & Geospatial Intelligence @ 0.49 | rejected | BKKT: Core business is digital asset brokerage infrastructure (crypto/digital assets). Candidate theme: "Satellite Imagery & Geospatial Intelligence" — BKKT has |
| 2026-05-21 | QBTS (WRONG-CASE) | Satellite Imagery & Geospatial Intelligence @ 0.41 | rejected | QBTS: Core business is quantum computing systems, hardware & software. Candidate theme: "Satellite Imagery & Geospatial Intelligence" — thesis is the SpaceX IPO |
| 2026-05-21 | QBTS (WRONG-CASE) | Satellite Imagery & Geospatial Intelligence @ 0.41 | rejected | QBTS: Core business is quantum computing systems, hardware & software. Candidate theme: "Satellite Imagery & Geospatial Intelligence" — thesis is the SpaceX IPO |
| 2026-07-20 | IREN (MUST-WORK) | Custom AI Silicon & Chip Architecture Licensing @ 0.53, Semiconductor Wafer Foundry & Advanced IC Manufacturing @ 0.44 | rejected | IREN: Core business is data center operations and computing infrastructure (Bitcoin mining/AI compute). Candidate themes: (1) Custom AI Silicon & Chip Architect |

Every confirmed fit (the newly boosted), with the judgement's own sentence:

| date | ticker | theme (stage) | corr | rationale |
|---|---|---|---|---|
| 2026-05-20 | IMVT | Inflammatory Disease & Immunology Biologics (Accelerating) | 0.46 | IMVT develops monoclonal antibodies (batoclimab) targeting autoimmune diseases such as thyroid eye disease and myasthenia gravis, directly matching the theme's  |
| 2026-05-20 | IMVT | Inflammatory Disease & Immunology Biologics (Accelerating) | 0.46 | IMVT develops monoclonal antibodies (batoclimab) targeting autoimmune diseases such as thyroid eye disease and myasthenia gravis, directly matching the theme's  |
| 2026-05-21 | GFS | Semiconductor Wafer Foundry & Advanced IC Manufacturing (Mainstream) | 0.65 | GlobalFoundries is a pure-play semiconductor wafer foundry offering fabrication services, directly matching the theme alongside peers UMC and TSEM. |
| 2026-05-26 | POWI | Power Semiconductor & Mixed-Signal Display Drivers (Mainstream) | 0.53 | Power Integrations designs high-voltage power conversion ICs and analog semiconductors, directly aligning with the theme's focus on power semiconductor companie |
| 2026-05-26 | POWI | Power Semiconductor & Mixed-Signal Display Drivers (Mainstream) | 0.53 | Power Integrations designs high-voltage power conversion ICs and analog semiconductors, directly aligning with the theme's focus on power semiconductor companie |
| 2026-07-15 | AEHR | Semiconductor Wafer Foundry & Advanced IC Manufacturing (Mainstream) | 0.78 | AEHR makes semiconductor wafer-level burn-in and test equipment, directly supporting the IC manufacturing supply chain alongside other equipment names like KLAC |
| 2026-08-04 | PLTR | AI-Powered Enterprise Analytics & Intelligent Workflow SaaS (Mainstream) | 0.61 | Palantir's core Gotham, Foundry, and AIP platforms deliver AI-powered data analytics and intelligent workflows to government and enterprise clients, directly ma |
| 2026-08-14 | VERA | Inflammatory Disease & Immunology Biologics (Mainstream) | 0.64 | VERA is a clinical-stage company developing therapeutics for immunological diseases, directly matching the theme's focus on inflammatory disease and immunology  |
| 2026-08-17 | ARGX | Inflammatory Disease & Immunology Biologics (Mainstream) | 0.35 | argenx develops antibody-based biologics (efgartigimod) targeting autoimmune and inflammatory diseases, directly matching this theme's focus on immunology biolo |
| 2026-08-27 | CRWD | Cyber Exposure Management & Vulnerability Assessment (Mainstream) | 0.64 | CrowdStrike's cloud-native Falcon platform focuses on endpoint security, threat detection, and exposure management, directly aligning with the theme's cybersecu |
| 2026-08-27 | DG | Defensive Consumer Staples Rotation (Accelerating) | 0.64 | Dollar General is a discount retailer heavily weighted toward consumables and household staples, directly comparable to DLTR already in the theme, and classifie |

## Money path — alerts that would newly cross into HIGH

Newly boosted alerts: 11. Of those, already HIGH before the bonus (score >= its own era bar): 9. Below the bar before: 2.

**Definite new HIGH crossings: 1.** Possible (conviction floor bound, raw unknown): 0. Unreconstructible score: 0.

| date | ticker | theme | score before | score after | era bar | stored tier | note |
|---|---|---|---|---|---|---|---|
| 2026-05-21 | GFS | Semiconductor Wafer Foundry & Advanced IC Manufacturing | 56.4 | 68.4 | 65.0 | HIGH | crosses  |

### Recount: HIGHs that depend on the +10 TODAY (listed alerts, at each alert's own era bar)

2 alert(s) that carried the +10 (stored `in_active_theme`) are HIGH only because of it at their own era bar (the earlier read of 4 — SNOW, HOOD 09-03; BLZE 07-31; AEHR 06-17 — was taken at a flat 70).

| date | ticker | score | without +10 | era bar |
|---|---|---|---|---|
| 2026-08-19 | MRVL | 69.1 | 54.7 | 65.0 |
| 2026-09-08 | ERO | 67.5 | 55.0 | 65.0 |

The four alerts the earlier read named, at their own era bar:

| date | ticker | score | +10 paid | era bar | HIGH at the scorer WITH it? | without +10 | HIGH without it? |
|---|---|---|---|---|---|---|---|
| 2026-06-17 | AEHR | 70.0 | True | 70.0 | yes | 70.0 | yes |
| 2026-07-31 | BLZE | 72.0 | True | 75.0 | no (stored tier is the judge's) | 72.0 | no |
| 2026-09-03 | HOOD | 77.5 | True | 65.0 | yes | 65.0 | yes |
| 2026-09-03 | SNOW | 77.5 | True | 65.0 | yes | 65.0 | yes |

## The Nascent question — SEPARATE number, not bundled

Alerts NOT belonging under today's stage set that were judged against a Nascent shortlist: 98; CONFIRMED against a Nascent theme: **11** — the additional alerts that would carry the +10 if Nascent paid. Of those, definite new HIGH crossings: 1.

| date | ticker | Nascent theme | corr | score before | after | bar | rationale |
|---|---|---|---|---|---|---|---|
| 2026-06-02 | CAMT | Semiconductor Wafer Foundry & Advanced IC Manufacturing | 0.68 | 50.4 | 64.8 | 65.0 | Camtek provides semiconductor inspection and metrology equipment, directly serving advanced-node and packaging fabs — th |
| 2026-07-20 | HUT | Bitcoin Mining & Crypto Infrastructure Operators | 0.75 | 72.0 | ? | 75.0 | HUT is a pure-play Bitcoin miner and energy infrastructure operator, directly matching the theme's thesis of correlated  |
| 2026-07-20 | IREN | Bitcoin Mining & Crypto Infrastructure Operators | 0.80 | 72.0 | ? | 75.0 | IREN is a pure-play Bitcoin miner and data center/computing infrastructure operator explicitly named as a member of this |
| 2026-07-23 | CLF | Global Steel & Metal Producers Recovery | 0.61 | 84.0 | ? | 75.0 | CLF is a major US flat-rolled steel producer whose business directly aligns with the steel and metals recovery thesis dr |
| 2026-07-31 | COHU | AI & Data Center Semiconductor Surge | 0.80 | 80.0 | ? | 75.0 | COHU provides semiconductor test equipment and services, a capital equipment segment that benefits directly from rising  |
| 2026-07-31 | MPWR | AI & Data Center Semiconductor Surge | 0.71 | 60.0 | ? | 75.0 | Monolithic Power Systems supplies high-efficiency power management ICs (voltage regulators) that are critical components |
| 2026-08-05 | KTOS | U.S. Government/Defense Spending Surge | 0.59 | 64.8 | 79.2 | 65.0 | Kratos is a pure-play defense contractor generating the majority of its revenue from U.S. government contracts for drone |
| 2026-08-07 | MTW | Industrial Lifting, Material Handling & Equipment Rental | 0.52 | 50.4 | 62.4 | 65.0 | Manitowoc designs and manufactures crawler-mounted lattice-boom cranes, making it a direct industrial lifting equipment  |
| 2026-08-11 | RIOT | Emerging Bitcoin & AI Cloud Compute Miners | 0.87 | 115.2 | ? | 65.0 | RIOT is a Bitcoin mining operator explicitly named as a core member of this theme's cluster, making it a direct and unam |
| 2026-09-04 | ALAB | AI Data Center High-Speed Interconnect & Signal Integrity Chipmakers | 0.75 | 65.0 | 77.5 | 65.0 | Astera Labs designs PCIe, CXL, and Ethernet retimer/connectivity semiconductors that ensure signal integrity across high |
| 2026-09-08 | PHVS | Specialty & Rare Disease Pharmaceutical Innovators | 0.36 | 90.0 | 90.0 | 65.0 | Pharvaris is a clinical-stage rare disease biopharmaceutical company developing treatments for hereditary angioedema (HA |

## Cost of stage 2 (this run, cache misses only)

- model `claude-sonnet-4-6`; calls 269; input tokens 340,967 (mean 1,268); output tokens 51,055 (mean 190); **US$1.79** (US$0.0066 per call; pre-run estimate US$0.0073 per call); wall-clock 1288s summed over calls, mean 4.8s per call.
- per-scan-DAY load implied by this population: 2.62 unlisted shortlisted ALERTS per alert day (173 over 66 alert days); the graded shortlist adds sub-bar names on top (see the live `EP scan complete` line for the real count).

## Reconstruction honesty

- score arithmetic status over all 346 alerts: exact 2, floor_bound_possible 160, ok 184.
- multiplier inferred (regime-implied did not reproduce): 3.
- 'exact' = the stored breakdown carried the floor; 'ok' = raw recovered as an integer with the floor not at the recovered value; 'floor_bound_possible' = the recovered raw equals an applicable floor, so the true raw may be lower (reported, never resolved).
- Descriptions: the nightly one-liner where one exists, else the yfinance profile paragraph fetched NOW (a company's business description is not price data, but it is the one input here that post-dates the alert).
---

## What this does not answer

- **Whether the boost should exist at all, or be +10.** This measures where belonging is
  correctly *decided*, not whether a theme membership is worth 10 points. He named that as the
  legitimate downstream question and it is untouched here.
- **Whether the 11 newly boosted names are GOOD trades.** Themes are not judged on returns yet
  (his ruling); this is a membership-correctness read, not an edge read.
- **Whether the judgement is right where we have no label.** The four rejections and IREN are
  checked against his own calls. The other 165 verdicts are checked against nothing — they read
  sensible, which is not the same as verified.
- **The live shortlist load.** The per-day figure here (2.62 unlisted shortlisted alerts per alert
  day) is computed over alert days only; the graded shortlist adds sub-bar names on top. The real
  number comes off the `EP scan complete` line on the first market morning after deploy.
- **Anything about Nascent beyond reach.** The 11 Nascent confirmations say how many alerts WOULD
  be boosted, not whether paying them improves selection. That needs its own read.
- **One input post-dates the alert.** Where no nightly one-liner existed, the company description
  came from a yfinance profile fetched today. A business description is not price data, but it is
  not strictly as-of either — 2 alerts had no description anywhere and got no verdict.
