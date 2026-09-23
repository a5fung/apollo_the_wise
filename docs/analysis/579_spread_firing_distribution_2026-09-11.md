# #579 step (b) — how often would a strength-map spread speak? Measured before any threshold.

**2026-09-11. $0 — `mi_daily_closes`, read-only.** Probe:
`scripts/probes/_579_spread_firing_distribution.py`. Nothing built, nothing changed.

## Method and population

**Rows:** every daily close in `mi_daily_closes` for the tickers named in
`strength_map.COMPLEXES` — 16,354 rows pulled once to `scripts/probes/_579_closes.tsv` and read
from there (capture once, read many).

**Spread** = the equity expression's trailing 21-bar return minus the anchor's, exactly as
`strength_map` computes the 1M window the operator was shown. **Move** = the absolute change in
that spread over 30 trading days, the horizon the crypto lane speaks over. **Population** = 1,027
judged days per complex, roughly four years.

⚠ **Only 2 of the 5 complexes can produce a spread at all.** Precious metals and Energy carry both
an anchor and an equity expression; Uranium, Agriculture and Macro backdrop do not, so they have no
direction spread and are absent from every number below rather than silently counted as quiet.

## 🔴 The primitive does NOT port as-is, and the measurement is what says so

The task says generalise `_dominance_band` — the band is the MEDIAN absolute 30-day move. Applied to
spreads as a firing rule:

| complex | band (median) | days it fires | judged days (n) | rate |
|---|---|---|---|---|
| Precious metals | 9.71 | 505 | 997 | **50.7%** |
| Energy | 5.86 | 478 | 997 | **47.9%** |

**A median fires half the time by definition.** That is fine where the crypto lane actually uses it —
as a three-way CLASSIFIER inside a weekly briefing (*alts leading / BTC leading / typical*) — and
useless as an ad-hoc trigger. Porting it unchanged would message him every other day.

## The threshold, priced rather than picked

All rates below are over **n = 1,027 judged days per complex** (~48.9 months of trading days);
crossing counts are absolute over that same span.

| percentile | threshold (pts) — PM / Energy | days above (n of 1,027) | days/mo | **crossings (n)** | **crossings/mo** | median run |
|---|---|---|---|---|---|---|
| 50th | 6.16 / 8.49 | 604 / 604 | 10.5 | — | — | — |
| 75th | 10.32 / 14.67 | 301 / 302 | 5.2 | **69 / 69** | **1.2 / 1.2** | 3 / 2 days |
| 90th | 14.18 / 21.30 | 120 / 120 | 2.1 | 40 / 30 | 0.7 / 0.5 | 2 / 2 days |
| 95th | 16.75 / 25.86 | 60 / 60 | 1.0 | 18 / 27 | 0.3 / 0.5 | 3 / 1 days |

🔑 **COUNT CROSSINGS, NOT DAYS — they differ by about eight times.** A spread that stays wide is
above the bar every day it stays there; those are not separate events and must not be separate
messages. The median run is 2-3 days, so "fire on the crossing, stay silent until it drops back" is
the whole dedupe.

## Recommendation, and the reason it is the loose end of the range

**75th percentile, fire on crossing, silent until it falls back: ~1.2 messages per complex per
month, so roughly 2-3 a month in total across the two complexes that have a spread.**

The 90th and 95th are quieter and tempting, and they are the wrong instinct here. **This task exists
because he found the miners-vs-metal read on Twitter before Apollo told him** — the failure mode
being fixed is silence, not noise. A bar that speaks twice a year reintroduces exactly the miss.
Two or three messages a month is a cadence he can ignore when it does not matter; a missed regime
turn is not.

⚖ **The cadence is HIS call** — it is a notification rule, and he has twice said readability and
cadence are his. The curve above is so the choice is priced rather than argued.

## What this does not answer

- **Whether a firing spread is worth ACTING on.** This measures how often the reading is unusual for
  its own history, never whether unusual readings preceded anything tradeable. That is a different
  study and it needs an outcome, not a distribution.
- **Whether 21 bars and 30 days are the right windows.** They were chosen to match what the operator
  was already shown and what the crypto lane already uses, not because they were tested.
- **Anything about Uranium, Agriculture or Macro backdrop**, which have no spread to measure.
- **The `widened` flag** (recent/baseline ≥ 1.5), which the crypto lane also carries and which is a
  second, independent signal — not measured here.
