# #557 cooldown recheck — corrected for the setup-at-open fix (2026-08-29)

**MEASUREMENT ONLY. No safeguard, cooldown, threshold or strategy changed. This is a
confirm/restate of prior rulings, not a new decision. Any change is CHANGE_PROCESS + operator
sign-off (THE LINE).**

**Why this exists:** `docs/analysis/595_missed_outcomes_anchor_2026-08-29.md` found
`mi_ep_missed_outcomes` credited names whose pre-market print faded before the open as "missed
winners." For `skip_category='cooldown'` it flagged 9 of 12 claimed winners (75%) as never
having been real setups. This re-runs the two prior cooldown studies —
`cooldown_cost_557_2026-08-21.md` and `cooldown_60d_effectiveness_2026-07-26.md` — filtered to
`setup_at_open IS TRUE`.

**Standing caveat (both prior docs stated this; repeating because it governs every number
below):** `ret_5d` / `ret_20d` / `max_high_5d` are the open-to-close stock move over N sessions,
not a trade result. There is no stop in this number — a −50% row does NOT mean a live position
would have lost 50%; the live bracket would have stopped it near −1R. None of the tables below
are P&L.

---

## 1. Real setups vs. the raw count

`skip_category='cooldown'`, all rows (table has grown 114→116 since the 08-20/08-21 snapshot;
count differs by 2, not reconciled, immaterial to every conclusion below):

| | n | % |
|---|---|---|
| **total cooldown-blocked ticker-days** | 116 | 100% |
| real setup at open (`setup_at_open = TRUE`) | 48 | 41% |
| never a setup — pre-market print faded before the bell | 68 | 59% |
| not computed (NULL) | 0 | 0% |

Cooldown is fully backfilled — no NULL rows to caveat.

## 2. The ≥20% "winner" claim, corrected

The anchor doc's own threshold (`ret_5d ≥ 0.20`), applied here to reproduce its 12/9/3 tally.
Neither original doc used this exact cutoff as a headline number — they cited named movers
(FCEL, ALOY, IREN, etc.) and win-rate splits at `ret_5d > 0`, both handled in §3 — but this is
the number the anchor doc and this recheck's brief are keyed to.

| | n | tickers |
|---|---|---|
| **raw claimed winners** (`ret_5d ≥ 0.20`, all cooldown rows) | 12 | TE ×3, ALOY ×2, VCX, FCEL, HQ, FLY, HIMX, YSS, WYFI |
| — of which never a setup at open | 9 (75%) | TE 05-20, TE 05-26, FCEL 06-26, ALOY 06-12, HQ 06-17, FLY 05-18, YSS 05-18, WYFI 06-16, ALOY 07-29 |
| **corrected winners** (`setup_at_open = TRUE` too) | **3** | **TE 2026-05-18 (+56%), VCX 2026-05-06 (+55%), HIMX 2026-05-07 (+34%)** |

Matches the anchor doc's 9/12 = 75% exactly. **12 claimed → 3 real.**

**The digest's two named "misses" (ALOY, IREN) — checked directly:**

| ticker | date | ret_5d | open-basis gap | real setup? |
|---|---|---|---|---|
| ALOY | 06-12 | +36.9% | +2.4% | **no** |
| ALOY | 06-15 | +16.3% | +8.3% | **no** (just under the 9% floor) |
| ALOY | 07-29 | +25.3% | +5.6% | **no** |
| IREN | 07-30 | +16.7% | +10.9% | **yes** |

All three ALOY cooldown-blocks were pre-market fades, never real setups — including 07-29, the
one `cooldown_cost_557` modeled as an ORB fill that stopped out at −1R. That −1R modeled loss
was against a name that would not even have gapped enough at the bell to qualify as a setup.
IREN 07-30 is a real setup, but at +16.7% it was never in the ≥20% "winner" list to begin with,
and (as the original doc said, unaffected by this correction) it has no minute bars — still not
modelable.

## 3. Corrected cohort forward outcomes (`setup_at_open = TRUE` only)

**Full corrected cohort, 5-day:**

| n | mean | median | up | down |
|---|---|---|---|---|
| 47 | **−4.5%** | **−5.5%** | 18 (38%) | 29 (62%) |

**Full corrected cohort, 20-day** (n shrinks — 20d marks not yet matured for the newest rows):

| n | mean | median | up | down |
|---|---|---|---|---|
| 33 | **−18.7%** | **−22.8%** | 8 (24%) | 25 (76%) |

**Held-before vs. never-held split** (mirrors both prior docs' central table), corrected 5d:

| population | n | mean | median | up |
|---|---|---|---|---|
| held before (designed target) | **6** | −16.7% | −13.3% | 1 (17%) |
| never held (collateral) | 41 | −2.8% | −3.6% | 17 (41%) |

⚠ **Held-before n = 6, below the ~10-row floor — too few to re-verify on its own.** The two
priors' held-before samples (n=11, n=12) were themselves roughly half contaminated by the same
defect being corrected here (only 6–7 of ~14 rows survive the `setup_at_open` filter), so citing
their size as backing would be circular. Honest reading: **at corrected n=6, the "held-before
cooldown blocks are near-zero winners" claim is neither confirmed nor contradicted — it cannot
be judged on this cell alone.** The direction (1/6 up, mean −16.7%) does not conflict with either
prior, but that is as far as this recheck can honestly go.

**Gap ≥15% discriminator** (the one loosening signal both docs flagged as real), corrected 5d:

| gap | n | mean | median | up |
|---|---|---|---|---|
| ≥ 15% | 20 | **+5.1%** | **+2.4%** | 11 (55%) |
| < 15% | 27 | **−11.7%** | **−14.0%** | 7 (26%) |

**Where the original "coin flip" mean actually lived** — the fake rows (`setup_at_open = FALSE`),
5d, for comparison against the real cohort above:

| population | n | mean | median | up |
|---|---|---|---|---|
| real setups (`setup_at_open = TRUE`) | 47 | −4.5% | −5.5% | 18 (38%) |
| **never-a-setup rows (`setup_at_open = FALSE`)** | 67 | **+1.4%** | −1.4% | 30 (45%) |

The fake-row mean (+1.4%) sits almost exactly on the ORIGINAL un-corrected collateral mean
(+1.0%, §4 below) — because that original collateral pool was 59% fake rows. **The thin positive
tail both prior docs flagged ("a thin right tail... the median name goes slightly nowhere") lived
in the rows that were never real setups.** Stripping them makes the real cohort's mean negative,
not because the conclusion broke, but because the tail causing the near-zero mean was fake.

## 4. Does each original conclusion still hold?

### `cooldown_60d_effectiveness_2026-07-26.md`

| claim | original | corrected | holds? |
|---|---|---|---|
| Verdict: working as designed, no change warranted | — | — | **YES — strengthens** |
| Held-before: near-zero winners | n=12, mean −14.4%, median −11.2%, 0/11 up | n=**6** — **cannot be re-verified on its own** (see §3 caveat); directionally 1/6 up, mean −16.7% | not judged — n too small |
| Never-held collateral: "coin flip", thin positive tail from a few big movers | n=92, mean +1.0%, median −1.3%, 42/91 (46%) up | n=41, mean −2.8%, median −3.6%, 17/41 (41%) up | **YES — holds, and the mechanism is now shown, not just asserted.** The original doc called the positive mean "a thin right tail" riding on a few names. §3 shows that tail sat in the rows that were never real setups (fake-row mean +1.4%, matching the original collateral mean almost exactly). Stripping them is exactly what the original doc's own reasoning predicted would happen. |
| Gap ≥15% discriminates | n=24, +5.8%/+3.3%, 62% up vs n=78, −2.7%/−5.2%, 35% up | n=20, +5.1%/+2.4%, 55% up vs n=27, **−11.7%/−14.0%**, 26% up | **YES — strengthens.** The low-gap cohort looks much worse once corrected; the split widens. |
| Re-setup shadow (#170) admission test / days-since-alert monotonicity (addenda) | — | not rerun | **not answered here — see below** |

### `cooldown_cost_557_2026-08-21.md`

| claim | original | corrected | holds? |
|---|---|---|---|
| Result 1: unconditional distribution goes down | n=109, mean −0.7%, median −2.7%, 42% up (5d) | n=47, mean **−4.5%**, median **−5.5%**, 38% up | **YES — strengthens.** More negative on both measures. |
| Result 1, 20d | n=81, mean −15.0%, median −20.2%, 28% up | n=33, mean **−18.7%**, median **−22.8%**, 24% up | **YES — strengthens.** |
| Result 2: ALOY 07-29 is a modeled −1R loser, not the digest's "+47% peak" | modeled under fill rules | now also confirmed **not a real setup at open** | **YES — strengthens.** Two independent reasons the digest's framing was wrong, not one. |
| Result 2: IREN 07-30 not modelable (no bars) | stated as a limit | unchanged; also never qualified as a ≥20% "winner" in the first place | **YES — unaffected**, and the correction shows it was never miscounted as a winner to begin with |
| Result 3: modeled cost ≈ +1R to +4R per 4 months (fill-model chain) | — | not rerun | **not answered here — see below** |
| Result 4: held-before extended (14 rows), gap≥15% discriminator | n=14, mean −12.5%, 1/12 up; gap split n=27 vs n=82 | held-before n=6 — **not judged, too small**; gap split n=20 vs n=27 (widened) | gap split strengthens; held-before not re-verifiable |
| Verdict (a): cooldown is cheap, digest's framing was selection bias on peaks | — | — | **YES — strengthens**, per Result 2 above |

**Bottom line: every recomputable claim holds on the corrected data, several strengthen.**
Nothing in the correction supports loosening the cooldown. One cell (held-before, n=6) is too
small to judge on its own — not confirmed, not contradicted, just under-powered — and is
reported as such rather than propped up by priors that shared the same defect.

## What this does not answer

- **The fill-model / R-cost chain** (`cooldown_cost_557` Result 3: "~+1R to +4R per 4 months")
  was built from minute-bar fills and a HIGH-survival-rate estimate, not from `ret_5d` directly —
  not rerun here. The corrected data does not contradict it, but it was not re-derived.
- **The #170 re-setup shadow classifier test and the days-since-prior-alert bucket monotonicity**
  (`cooldown_60d_effectiveness` addenda 1–2) were not rerun on `setup_at_open`-filtered data.
  Those addenda used a separately-instrumented shadow cohort (`mi_ep_scan_log`), not this table;
  out of scope for this recheck.
- **The circuit-breaker mechanism (b)** in `cooldown_cost_557` is a different gate
  (`skip_category` doesn't cover it — it fires at entry submission, not on `mi_ep_missed_outcomes`
  rows) and is untouched by this correction.
- **The 5-slot / order-priority replay (P4)** flagged as unmeasured in the original doc remains
  unmeasured.
- Whether the 48 real-setup rows are themselves correctly measured beyond `setup_at_open` (e.g.
  fill feasibility, ORB range sanity) — not checked here; that is the fill-model's job (Result 3
  above), not this table's.

## Files

- This recheck: `docs/analysis/557_cooldown_recheck_2026-08-29.md`
- Correction source: `docs/analysis/595_missed_outcomes_anchor_2026-08-29.md`
- Originals being confirmed: `docs/analysis/cooldown_cost_557_2026-08-21.md`,
  `docs/analysis/cooldown_60d_effectiveness_2026-07-26.md`
- Queries: `/Users/alvinfung/.claude/jobs/6b173ac9/tmp/557_recheck.sql`, captured output
  `/Users/alvinfung/.claude/jobs/6b173ac9/tmp/557_recheck_out.txt` +
  `/Users/alvinfung/.claude/jobs/6b173ac9/tmp/557_A_fixed.txt` +
  `/Users/alvinfung/.claude/jobs/6b173ac9/tmp/557_fake_cohort.txt` (read-only SELECTs, $0 spent)
