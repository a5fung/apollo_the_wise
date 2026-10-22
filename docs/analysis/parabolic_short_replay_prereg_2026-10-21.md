# #314 — the parabolic short, replayed over five years: the base count, small caps, his selection rules, the time stop and stealth dilution — pre-registration (2026-10-21, BEFORE any replay outcome)

**Why.** The live shadow (since 2026-10-17) has armed n = 0 episodes, so nothing is known about how the setup performs. The operator
shared a short seller's stated rules (2026-10-20, `docs/methodology/operator_shared_notes.md`; mapped in
`docs/analysis/parabolic_short_vs_shared_short_rules_2026-10-20.md`) and ruled: *"Yes, but let's do this in weekend. Also, his play is
to short small caps, out filters are mainly for EPs, we haven't tested small caps for parabolic shorts"*; and on dilution: *"it's not
recent offering, the whole idea is stealth dilution that is in the horizon. Offering is after the fact"* / *"Eg warrants that the run up
will unlock and convert to shares is the exact example given"*. $0; shadow only; no paper, no live; entry / adds / exits for money are
his call (THE LINE).

## Method / population

- **Bars:** `apollo_data/cb702/daily_closes_all.csv.gz` (Polygon split-adjusted daily, 2021-09-27..2026-10-16, 20,285 tickers). The
  detector (`parabolic_detector.py`) and the episode walk (`parabolic_short_shadow.py`) are REPLAYED unchanged by importing their pure
  functions (the module is not edited); a replay that cannot match the live code on the shadow's own nights since 10-17 (its climax
  rows) is refused (parity check first).
- **Two populations (his ruling):** (P1) the CURRENT floors — close ≥ $5, dollar volume ≥ $10M, cap ≥ $250M (the floors came from the EP
  lane); (P2) SMALL CAPS — close ≥ $1 and dollar volume ≥ $2M (a tradable floor, fixed now), no cap floor, everything else as P1. Cap
  history exists only from 2026-05-01 (one cached row per name); before that the detector's cap tier is "unknown → mid" in BOTH
  populations, disclosed; P2 is defined by price and dollar volume, so it does not need cap history. The earnings gate needs dates
  the bars do not hold: the replay reads earnings dates from the stored `mi_ep_fundamentals` filings where present, else the name is
  admitted with the earnings flag "unknown" (counted, and a beside row drops them).
- **Primary walk = the shadow's registered rules unchanged:** arm on the climax day, short a break of the prior session's low within 3
  sessions, stop at the climax high + min(3%, 0.5 x ATR14), trail to the prior session's high, cover a third at +1R, time stop at the
  close of the 5th session, exit before earnings. R against the entry stop; mature = a terminal exit.
- **Reads on the same episodes (each a fixed variant, beside the primary; nothing tuned):**
  1. **Time stop 3 vs 5 sessions** — his "shorts last 1–3 days".
  2. **Straight-up shape** — the number of down-close days between the base low and the climax, split at the pre-named cut ≤ 2 vs ≥ 3
     ("pauses on the way up = a broken short").
  3. **A news catalyst present vs absent** — a dated Polygon news item on the run's start day or the 2 sessions before it (the free
     news source the repo already reads), present vs absent ("no news = do not short").
  4. **A loss-to-profit swing blocks** — the last filed quarter before the climax shows positive net income after a loss the quarter
     before (from the stored filings): such episodes vs the rest.
  5. **Stealth dilution (P2 first):** shares issuable from warrants and convertibles IN THE MONEY at the climax close (exercise /
     conversion price below it) ÷ shares outstanding, from the last SEC XBRL filing before the climax (point-in-time `filed` date),
     split at the pre-named cut ≥ 20% vs < 20% vs **unknown** (no XBRL terms — about 55% of warrant cases and 82% of convertible cases
     on the 10-21 coverage check; reported as its own group, never imputed).
- **Rows are reported per population × read; the primary walk's numbers come first.**

## Bars (per population; precedence: n first)

- **The base verdict (primary walk):** PASS = n ≥ 30 mature episodes, month-block 95% interval of mean R (blocks = the entry month,
  2,000 resamples, seed 702) lower end > 0, ADR P&L > 0, and the ≥ 5R trades from ≥ 3 tickers and ≥ 3 months; FAIL = n ≥ 30 and upper end
  < 0; else CAN'T TELL.
- **Each read (1–5):** the difference in mean R between its two named groups with the same interval — lower end > 0 → the rule
  separates in his direction; upper end < 0 → it separates against him; else can't tell. n ≥ 30 per group or the row reads CAN'T TELL.
- **Expectations, fixed now:** P2 produces more episodes than P1 (small caps run parabolic more often); a missed expectation is
  reported first and changes no rule. **WOULD-FAIL-IF:** the replay disagrees with the live shadow's own rows since 10-17 (parity);
  a feature (news, filings, XBRL) dated AFTER the climax day used for that episode; an episode counted in both groups of a read.

## Consequence fixed now

- A PASS (either population) makes the setup a candidate for a forward shadow lane on that population (small caps would need their own
  borrow check — historical borrow is NOT visible, so a replay PASS overstates what can be shorted); paper stays his call.
- A read that separates in his direction is RECORDED on the shadow's rows (e.g. the dilution ratio, the pause count) — a recording, not
  a rule; adopting any as a gate goes to him through CHANGE_PROCESS. A read against him is reported, nothing changes.
- Independent re-derivation of the base verdict and each read's difference — VERDICT MATCH before the result is written.

## What this does not answer

- Borrow availability and cost (the binding real-world limit on small-cap shorts); intraday entries (his top-day short on "losing
  momentum") — the replay is daily; his adds / pyramiding; the large-cap "obvious news-driven parabolic" judgement.

<!-- FREEZE -->
## Freeze record

Pins (sha256) from the build's `--print-pins`, pasted here in the commit that precedes the run: the daily export, the detector and
shadow modules, the runner, the stored filings / news extracts the reads use, the XBRL pull, the doc body. The RESULT goes below.
