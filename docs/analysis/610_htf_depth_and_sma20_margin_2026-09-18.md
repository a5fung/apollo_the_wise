# HTF — the two knobs the $MRNA label exposed, replayed from raw bars in both directions (2026-09-18, #610)

**Scope banner.** This measures OUR ENCODING of two admission gates on a detector that is shadow-only
and not traded. Every number is detection behaviour (rows on the board, stage transitions, raw
forward moves from daily bars). Nothing is realized R; no entry or exit is simulated; nothing here
says whether the HTF pattern pays. **Nothing was changed** — flag depth, the 75%-of-pole floor and the
SMA20 invalidation are admission criteria and the operator's sole authority (THE LINE). Harness:
`scripts/probes/_610_htf_depth_sma20_replay.py` ($0 — every input was already stored).

## Limits, stated first

- **The brief's premise on MRNA is wrong in both halves, and that is the first finding** (§1). A
  one-bar depth allowance cannot admit MRNA (four bars breach our floor), and an SMA20 margin never
  stood between MRNA and the board (with the margin, the same day reads `ma_stack_not_stage2`).
- **Two populations, never blended.** (A) the broad raw-bar replay: every (ticker, scan_date) pair prod
  scanned 2026-05-04 → 09-17 — 56,657 pairs, 2,749 tickers, 98 scan days — recomputed from
  `mi_daily_closes` bars, reported on 05-18 → 09-17 (88 scan days; 05-04 → 05-17 threads state
  only). (B) the labelled corpus, N=8 (CDNA, HNGE, MRNA, NCI, ATAI, OUST, SHAZ, REPL), one contested.
  **n=8 supports direction, never a verdict; every corpus statement below is a worked case, not a rate.**
- **Maturity.** Bars end 09-17. A 20-session forward window has matured only for scan dates ≤ 08-19,
  a 10-session one for ≤ 09-03. Every outcome block states matured n against total n; MRNA-era rows
  are unmatured and are labelled so.
- **Regime.** Four months, one tape; May 18 → June 26 was hot (baseline board 25.0 rows/day) and
  June 29 → Sep 17 was not (10.1/day). The one-bar allowance's admits are 86% May–June (66 of 77
  rows), so its read is mostly a hot-tape read. Pre-06-29 pairs were scanned by prod under the OLD
  criteria; that affects only which tickers were in the universe that day (the stage-carryforward
  universe path was added 2026-05-19), never the verdicts, which are all recomputed under HEAD.
- **Daily bars only.** The #94 intraday break scan is not replayed; "closed above the flag high" is a
  daily-close proxy for a breakout, "TRIGGERED" is the state machine's own definition.
- **Fidelity.** The variant machinery is the shipped `compute_flag_metrics` SOURCE with two asserted
  single-line edits compiled into a copy of the module namespace. At shipped settings it is asserted
  equal (stage + reason) to the shipped function on 1,500 sampled pairs, and reproduces prod's stored
  stage on **99.51% of the 31,728 pairs since 06-29** (155 mismatches: 97 are the 07-18 mean→median
  ADV change landing mid-window, 10 the post-compute M&A filter, the rest bars revised since the
  scan — the same families the 09-04 grid accounted for). On the 09-04 grid's exact window
  (06-29 → 09-04) this harness gives **529 actionable rows = 10.8/day, identical to that grid's
  post-fix figure**, so the two harnesses measure the same thing.

## 1. The premise correction — what actually stands between MRNA and our board

**Depth.** MRNA's pole is the 08-19 intraday high **176.66**; our floor is 75% of it = **132.50**.
Inside the flag (08-20 → 09-16, 19 bars) **four bars' lows sit under that floor**: 08-20 128.61,
08-24 130.00, 09-10 130.38, 08-21 132.42. The second-lowest low is **73.6%** of the pole, the
fourth-lowest 74.96%. **No one-bar allowance reaches it; a three-bar allowance misses by 0.04 points.**

Where his 26.2% comes from: **128.61 / 174.38 — the pole-day CLOSE, not its high** (1 − 0.7375 =
26.25%). Ours is 128.61 / 176.66 = 27.2%. Even on his pole reading three bars breach 25% (130.00 →
25.5%, 130.38 → 25.2%); *"mostly one stretch day (~1% over)"* is a discretionary read of a ~1-point
excess on one day and half-point excesses on two others. No mechanical one-bar rule reproduces it
under either pole.

**What does pass MRNA at the depth gate is the spec's own literal form.** The sourced rule is written
`Close ≥ 0.75 × High₄₀`; `docs/setups/htf.md` records that we deliberately tightened it to the
absolute LOW (*"O'Neil/Minervini reject a deep intraday shakeout that rallies to a tight close";
operator-endorsed via Gemini 6/27, "confirm via the eyeball"*). MRNA's lowest CLOSE in the flag is
133.32 = **75.5% of the pole** — it passes the literal spec by half a point and fails our tightening
by 2.2. So the binding difference on MRNA is **low-vs-close, a signed reasoned deviation**, not a
one-bar allowance. That variant ("Dc") is measured in §5 because without it this document could not
say what admits MRNA; it is outside the brief's two knobs and is not a recommendation.

**SMA20.** With any margin ≥ 0.1%, MRNA on 09-16 stops reading `INVALIDATED close_145.62_below_sma20_
145.67` and reads **`unqualified ma_stack_not_stage2`** instead — the 10-day was already under the
20-day. And on **09-17, his breakout day, every one of the ten variants below reads
`ma_stack_not_stage2_144.5/144.9/96.6`** — the 10-day SMA 144.51 sits 0.24% under the 20-day 144.86
(the 09-08 → 09-10 dip weighs on the 10-day while the 20-day still carries the late-August highs). The MA-stack check
returns before stage classification, so no state in this grid can make 09-17 TRIGGERED. **MRNA was
never on the board under the shipped detector, so the five-cent kill on 09-16 retired nothing** — the
PLAN line's "we retired it one day early" was true of the reject string, not of the board.

**Net on MRNA: three gates in a row, and the two named in the brief are not the ones that decide it.**
Depth (definitional, low vs close: 72.8% vs a 75% floor) → SMA20 (0.03%) → MA stack (0.24%). The
third is recorded as an observation only; it is not a knob in this read.

## 2. Ceilings — the most each knob could touch (baseline pass, population A, 88 scan days)

| gate | baseline kills | the part a small change can reach |
|---|---|---|
| SMA20 INVALIDATED | **617 rows / 169 tickers** (a ceiling that overstates what is reachable — the SMA20 check runs BEFORE the depth gate, so some of these would be depth-rejected anyway; MRNA is one) | close within 0.10% of the SMA20: **9 rows (1%)** · within 0.25%: 16 (3%) · within 0.50%: 34 (6%) · within 1.00%: 76 (12%) · beyond 1%: 541 (88%) |
| flag-depth reject | **515 rows / 120 (ticker, pole) episodes** | exactly ONE bar under the floor: **73 rows / 34 episodes (14% of rows)**; two bars: 68 rows; three or more: 351 rows (68%). Of the one-bar rows the breach is ≤1 point of the pole on 41, ≤2 on 14, ≤3 on 7, ≤5 on 6, deeper on 5 |

Read straight: 88% of SMA20 kills are decisive (>1% under), and 68% of depth rejects have three or
more breaching bars. Both knobs are working on the margins of their gates by construction.

## 3. Knob (a) — a one-bar depth allowance, both directions (population A)

Variants: **D1** = the gate reads the second-lowest low (one bar excused, any depth); **D1b3** = the
same, but only if the excused bar's low is ≥ 72% of the pole (3-point cap). Denominators: "new
episodes" = (ticker, pole) never actionable under the baseline; outcomes from the episode's first
actionable close; the baseline's own admits are the comparison row (the 09-10 lesson — the
comparison that decides is against the ADMITTED population, never the rejected pool).

| | rows +/− vs baseline | tickers | new episodes | TRIGGERED | ran ≥+20% within 10 sessions (MFE10) | closed above the flag high ≤10 sessions | down a month later (fwd20 < 0) | fwd20 median |
|---|---|---|---|---|---|---|---|---|
| **baseline — its own 412 admits** | 1,337 rows (15.2/day) | 195 | — | 9 | **83/395 = 21%** | 211/395 = 53% | **184/364 = 51%** | −0.2% (n=364) |
| **D1** | **+77 / −0** | +12 (→207) | **25** (24 tickers) | +1 (GTE 08-19: fwd10 +4%, fwd20 +4%, MFE20 +13%) | **8/25 = 32%** | 10/25 = 40% | **11/22 = 50%** | −1.1% (n=22) |
| **D1b3** | +66 / −0 | +9 | 19 (18 tickers) | +1 (GTE) | 5/19 = 26% | 9/19 = 47% | 8/18 = 44% | +4.0% (n=18) |

- **Every one of the 77 admitted rows comes straight off a `flag_low_` reject; zero knock-on losses**
  (no baseline-actionable row is lost), so the attribution is clean.
- **What it admits:** 25 episodes in 88 scan days; 19 never got past WATCH, 3 reached COILED, 2
  TIGHTENING, 1 TRIGGERED (GTE, +4% ten sessions later). The names: RXO, APLD, CLYM×2, QUIK, VELO,
  VICR, AMPG, IPWR, NVTS, NEXA, RDW, FLNC, PURR, CIFR, QTTB, BLZE, NUAI, WYFI, MEI, APPS, GTE, FSLY,
  QMCO, UMAC (the last three unmatured).
- **What it lets in:** the same half that the baseline's own admits already fall (11 of 22 matured
  are down a month later, vs 184 of 364 = 51% for the baseline) and a slightly fatter tail (8 of 25
  ran ≥20% within ten sessions vs 21% baseline). **On n=25 a 32% is not distinguishable from 21%**
  (a 95% interval on 8 of 25 spans roughly 17–52%); it is a direction at best, and it is 86% May–June tape.
- **Corpus (B):** D1 and D1b3 flip **no member** — CDNA stays TIGHTENING, HNGE stays a runup reject,
  **MRNA stays `flag_low_` on 09-11 and 09-15** (four bars breach), NCI/ATAI/OUST/SHAZ/REPL unchanged.
  The knob recovers zero labelled positives and admits zero labelled negatives.

## 4. Knob (b) — an SMA20 invalidation margin, both directions (population A)

Variant: `close < sma_20 × (1 − m)` → INVALIDATED; the MA-stack and COILED gates that also read
`sma_20` are untouched (the patch is on the one comparison, not on `_sma`). "Retained rows" = rows
the baseline killed on SMA20 that the variant keeps actionable; outcomes from the retained close.

| margin m | retained rows / tickers | the variant itself INVALIDATED again within 5 sessions | TRIGGERED within 5 sessions | TRIGGERED events vs baseline | new episodes | ran ≥+20% within 10 (MFE10) | down a month later | fwd20 median (matured n) |
|---|---|---|---|---|---|---|---|---|
| 0.10% | **4 / 4** | 3 | 0 | **+0** | 1 (APPS 07-08, 1 day WATCH) | 1/4 | 1/3 | +14.3% (3) |
| 0.25% | 8 / 7 | 4 | 0 | +0 | 1 (APPS) | 2/7 | 1/6 | +14.6% (6) |
| 0.50% | 15 / 14 | 7 | 0 | +0 | 1 (APPS) | 3/14 = 21% | 6/13 = 46% | +0.9% (13) |
| 1.00% | **37 / 31** | **19** | 0 | **+0** | 2 (APPS, NBIS) | 8/35 = 23% | 15/28 = 54% | −1.2% (28) |

- **At every margin, zero additional TRIGGERED events in 88 scan days, and zero knock-on losses.**
- At 1% — ten times the brief's smallest margin — the knob keeps 37 rows (2.8% of the board's 1,337), **19 of
  which the same variant kills again within a week**, and the survivors look like the baseline's own
  admits (23% ran, 54% down a month later vs 21% / 51%).
- **Corpus (B):** no member flips at any margin. **MRNA on 09-16 moves from `INVALIDATED sma20` to
  `unqualified ma_stack` — a different reject string, the same outcome** (and it was never on the
  board to begin with).

## 5. The corrected mechanism — depth read on the CLOSE (spec literal), outside the brief's two knobs

**"Dc"** = the depth gate compares the flag's lowest CLOSE to 75% of the pole (the sourced form as
written) instead of the lowest LOW (our 6/27 tightening). Measured because it is the only thing in
this read that reaches MRNA; **it is a reversal of a signed reasoned deviation and is NOT proposed.**

| | rows + | tickers | new episodes | TRIGGERED | ran ≥+20% within 10 | closed above the flag high ≤10 | down a month later | fwd20 median | MAE20 median |
|---|---|---|---|---|---|---|---|---|---|
| baseline admits | — | 195 | 412 | 9 | 83/395 = 21% | 211/395 = 53% | 184/364 = 51% | −0.2% | **−14.0%** |
| **Dc** | **+167 / −0** | +15 (→210) | **41** (32 tickers) | +2 (GTE +4%; **INOD 05-29 fwd20 −27%**) | 12/41 = 29% | 21/41 = 51% | **23/40 = 57%** | **−7.5%** (n=40) | **−24.3%** |

- **Both directions:** Dc puts **MRNA on the board every scan day 08-25 → 09-15 — WATCH 08-25, COILED from 08-28** (`range_0.39 vol_0.19`, a textbook coil reading) — **and admits OUST on 06-29**, a name the
  operator signed off as *"i don't see HTF in those 3 names at all"*. One labelled positive
  recovered, one labelled negative admitted; SHAZ (the other depth-rejected negative) stays rejected.
- On the broad population its 41 new episodes break out of the flag at the baseline's rate (51% vs
  53%) but **fall harder when they fail**: 57% are down a month later vs 51%, median fwd20 −7.5% vs
  −0.2%, median worst drawdown −24% vs −14%. That is what a looser depth reading admits — deeper
  flags that keep falling — and it is the reasoning the 6/27 tightening recorded (*a deep shakeout
  that rallies to a tight close = the spring uncoiled*). The numbers do not say that reasoning was
  wrong; they say it is selective in the direction it intended.
- **Even Dc does not deliver MRNA's breakout day.** 09-16 is `INVALIDATED sma20` under Dc, `ma_stack`
  under Dc+0.1%; 09-17 is `ma_stack` under both. Reaching a TRIGGERED on 09-17 would need the
  low→close reversal AND an SMA20 margin AND an MA-stack margin — three deviations for one labelled
  name, the first of which admits a documented negative.

## 6. Corpus table (population B, N=8 — direction only)

Verdict on each member's recorded assert dates; `x:` = rejected, reason family.

| member | label | date | BASE | D1 | D1b3 | S0.1–1.0% | D1+S0.1 | **Dc** |
|---|---|---|---|---|---|---|---|---|
| CDNA | positive (must-not-miss) | 08-18, 08-19 | TIGHTENING | same | same | same | same | same |
| HNGE | positive (contested — pole outside the sourced window) | 08-21, 08-24 | x:runup | same | same | same | same | same |
| **MRNA** | positive (this read) | 09-11, 09-15 | x:flag_depth | **x:flag_depth** | x:flag_depth | x:flag_depth | x:flag_depth | **COILED** |
| NCI | negative | 06-26 | x:adv | same | same | same | same | same |
| ATAI | negative (M&A layer, one level up) | 07-24 | COILED | same | same | same | same | same |
| **OUST** | negative | 06-29 | x:flag_depth | same | same | same | same | **WATCH** |
| SHAZ | negative | 06-29, 06-30 | x:flag_depth | same | same | same | same | same |
| REPL | negative (incomplete coverage) | 08-10, 08-11 | x:base_age | same | same | same | same | same |

The two knobs in the brief move nothing on the corpus. The spec-literal depth moves one positive and
one negative.

## 7. Recommendation (mine; the ruling is his)

1. **Knob (a), one-bar allowance: measured null for its stated purpose, and not adopted.** It cannot
   reach MRNA (four breaching bars), touches no corpus member, and on the broad population adds 25
   episodes a quarter whose outcomes are indistinguishable from the baseline's own admits (down a
   month later 50% vs 51%; tail 32% vs 21% on n=25, mostly hot-tape May–June) for one extra
   breakout that made +4%. Nothing here says the current gate is excluding names that pay.
2. **Knob (b), SMA20 margin: measured null, and not adopted.** Zero additional breakouts at every
   margin up to 1%; half of what it keeps dies within a week anyway; MRNA unaffected. The 0.03% miss
   was a rounding-error kill of a name that was never on the board.
3. **The real MRNA difference is the low-vs-close depth reading, and I recommend KEEPING the low —
   stated as a trade-off on n=41, not as settled.** The literal spec admits MRNA and OUST alike. On
   his own tail yardstick its admits are slightly BETTER (ran ≥+20% within ten sessions: 12/41 = 29%
   vs 83/395 = 21%); on the junk side they are worse (57% down a month later vs 51%, median worst
   drawdown −24% vs −14%). Fatter tail, harder falls, one labelled negative admitted. The 6/27
   tightening was signed on exactly the harder-fall reasoning; reversing it needs CHANGE_PROCESS
   rule 4 — why that reasoning was WRONG, not merely that a labelled name sits on the other side of
   it — and n=41 in one tape does not carry that.
4. **Record MRNA the HNGE way**: a trader-labelled positive that sits outside our encoding on a
   discretionary read (his 26.2% is pole-close-based and still over his own bar on three days), not a
   detector miss. Two labelled positives now sit outside the encoding for two different reasons; the
   must-not-miss (CDNA) is kept by every variant.

## 8. The fork — what is his to rule, not mine

- **F1 — depth on the LOW (kept, signed 6/27) vs on the CLOSE (the spec's literal words).** A
  methodology reversal, not a tune. Evidence either way is in §5; my recommendation is to keep the
  low. If he rules for the close, OUST-class flags come with it and `tests/fixtures/htf_labelled.py`
  must re-record OUST's expected verdict in the same commit.
- **F2 — is MRNA an HTF the detector should have found, or a discretionary take outside the sourced
  spec?** His call, like HNGE. If "should have found", the honest statement is that no single
  mechanical rule reaches it: it needs F1 plus two more margins (SMA20 0.03%, MA stack 0.24%).
- **Not a fork, recorded as an observation:** the MA-stack gate (`sma_10 ≥ sma_20 ≥ sma_50`, our
  encoding of "above the 10/20/50") blocked MRNA's breakout day by 0.24%. The brief scoped two knobs;
  this is a third and is not measured here.

## 9. What I could not establish

- Whether Dc's harder-falling admits are a regime artefact — four months, one tape, and the depth
  admits cluster in the hot May–June weeks.
- The trader's pole level exactly: 174.38 is inferred from his 26.2% and 170.3%, not stated by him.
- 20-session outcomes for anything admitted after 08-19 (unmatured; labelled in every table).
- Intraday behaviour — the #94 break scan is not replayed; "closed above the flag high" is a daily proxy.
- Whether the state-machine TRIGGERED count (9 in 88 days) is enough to compare variants on
  breakouts alone; it is not, which is why the board-level yardsticks carry the read.

## 10. Reproduce

```
# pull SQL is in the harness docstring; both files go to the session scratchpad (35 MB)
python scripts/probes/_610_htf_depth_sma20_replay.py --data-dir <dir> --mrna-check   # §1 premise checks
python scripts/probes/_610_htf_depth_sma20_replay.py --data-dir <dir> --only-base    # fidelity + ceilings
python scripts/probes/_610_htf_depth_sma20_replay.py --data-dir <dir>                # everything above
```
Per-pair CSVs per variant land in `<dir>/out/`. `git diff` on `agents/` is empty: no live criterion
was changed for this measurement.
