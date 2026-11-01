# #88 M&A filter — first-pass check of the 11-01 monthly sample (main loop, his ask 2026-11-01: "do the initial check and only bring to me what needs my judgement")

Inputs: `b88_out.txt` (the sweep's script, run read-only on prod), `q2_fires.csv` (all 59 `mna_filter_fired` rows, last 30 days, read-only). 59 blocks = 16 companies. Each checked against public news (web search, 2026-11-01) and against the #692 rule (`docs/setups/magna53_ep.md` §M&A: a block is right when the stock is the TARGET of a deal, signed or proposed, on terms that could fix its price — cash / cash+stock / unstated; an all-stock merger, a buyer, speculation or a closed deal pass).

| Ticker | Blocks | The deal (public) | Under the rule |
|---|---|---|---|
| CCC | 11 | GTCR + Elliott to acquire CCC Intelligent Solutions, ~$6.1B (signed) | correct block |
| SYNA | 16 | onsemi to acquire Synaptics, amended 10-01 to $123 cash | correct block |
| PTC | 6 | Schneider Electric to acquire PTC, $205 cash (10-05) | correct block |
| RXO | 5 | C.H. Robinson to acquire RXO, $17.25 cash + 0.0856 CHRW (10-05) | correct block (the headline was about the buyer; the stock is the target) |
| BRZE | 3 | Salesforce to acquire Braze, $47.50 cash (10-20) | correct block |
| PCRX | 2 | Viatris to acquire Pacira, $1.65B | correct block |
| OPCH | 2 | McKesson deal (trades below the deal price) | correct block |
| SLN | 3 | Merck KGaA to acquire Silence Therapeutics, $20/ADS cash (10-19) | correct block |
| SGRY | 1 | Bon Secours affiliate take-private, $23.50 cash (10-26; the grader said "proposed", it was signed) | correct block |
| MFIC | 1 | Ares Capital to acquire MidCap Financial, cash + ARCC stock (10-27) | correct block |
| LCII | 1 | Monomoy's unsolicited $101 cash proposal (10-28; rejected 10-30; a signed all-stock Patrick merger since 06-30) | correct block on the cash proposal |
| MAT | 1 | takeover talks (proposed) | correct block (a proposed target) |
| LION | 1 | Legendary's fresh bid for Lionsgate (proposed) | correct block (a proposed target) |
| CART | 1 | DoorDash to acquire Instacart, $65, 75% cash (reported 10-26, announced 10-29) | correct block |
| BMBL | 4 | the deal target the 10-24 review already confirmed | correct block |
| RRC | 1 | EQT all-stock merger (0.987 EQT per share) | blocked on a lane that is gone; not raised |

Result: 58 of 58 judgeable blocks are on genuine takeover targets on price-fixing terms (100%, against the script's own "working well" bar of 30% and the 15% #88 ship baseline); Polygon insights missing: 0. Nothing in the sample needs his judgment as a true/false call.

Sources (web search 2026-11-01): sec.gov 8-K/425 filings for LCII, RXO, SYNA, BRZE; insidearbitrage.com (MFIC, SLN); benzinga.com (SGRY, SLN); tipranks.com / bloomberg.com (PTC); salesforce.com press release (BRZE); investors.instacart.com (CART); financefeeds.com (SYNA).
