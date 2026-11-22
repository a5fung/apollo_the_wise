# Adversarial review of the stage-5 confirm run, EP winner study #594

**Verdict:** I found no defect in any of the 10 checks. All nine verdict words reproduce from my own code. I stand behind these words:
- **PICKS THE TAIL (both eras):** f02 (low gap in daily ranges), f03 (high 20-day run-up), f09 (deep 40-day base), f18 (low price), the combination, H4 (high ADR20).
- **REVERSED:** H1, H2 and H3, his three gallery reads.

## Scope
- **Reviewed (2026-11-21):**
  - `build/stage5_confirm/confirm.py` (sha `5776dde3…`, the same sha printed in the `confirm.txt` header)
  - `confirm.txt` (`b89a761c…`) and `confirm_outcomes.tsv.gz` (`d31416d2…`)
  - `stage1/stats.py` and `common.py`
  - the builder's transcript commands
- **Prereg:** sha `6c581b6a2d67…`, asserted at start. It is byte-equal to `git show 3e6396c7:docs/analysis/ep_winner_study_prereg_2026-11-21.md`.
- **Recount script:** `/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/review_confirm_1121/recount.py`, output `recount.txt` in the same folder. It does not import `confirm.py` or `stats.py`.
- **Not opened:** `events_scored.tsv.gz`, `run.txt`.
- **Rules kept:** no network, DB or subagent; no commit.
- **Sealed cut in my own read:** era-B bars dated after 2024-12-31 are dropped at read and asserted. The latest forward bar read is 2022-06-30 for era A and 2024-12-24 for era B.

**What the recount shares with the build (so "0 mismatches" does not cover these):**
- the stage-1 bar cache pickle
- `population.tsv`
- the feature table's NULL pattern (I recomputed values only, not NULL reasons)
- `h_reads.tsv.gz`
- the permutation key convention (seed 1121, the `random((10000, n))` keys, fixed order)

**What is my own code:**
- the outcome loop, run over all 4,665 events
- pre-E feature values
- mid-rank thirds, the two-group layout and the combination
- smoothed and raw ratios, Mantel-Haenszel, per-era ratios
- Holm, the verdict words
- ADR-neutral strata, the ADR-scaled tail
- the B1 pooled reproduction

## Results per check
| # | Check | Verdict | Evidence |
|---|---|---|---|
| 1 | Ran once | **CONFIRMED** | See the "Check 1" section below. |
| 2 | Sealed cut (#710) | **CONFIRMED** | `common.load_bars` drops era-B rows after 2024-12-31 at read and asserts it. `confirm.py` re-asserts on every era-B series (line 301) and asserts the last forward bar of every era-B event ≤ 2024-12-31 (line 454). My own read does the same. All 4,665 events have E+60 inside their own era calendar (asserted). |
| 3 | Era handling | **CONFIRMED** | My code asserts the confirm era-A events lie in 2021-01-04..2022-04-04 (867) and the era-B events in 2022-04-05..2024-09-30 (1,384). No era-B event at or before 2022-04-04 exists anywhere. Outcomes read only the event's own era file (`bars_all[(era, t)]`, `cal[era]`), never stitched. |
| 4 | Directions as frozen | **CONFIRMED** | `CARRIED` / `DIR` match `stage3/discovery.txt`: f02 LOW, f03 HIGH, f09 HIGH, f18 LOW, the combination HIGH (asserted against the text at lines 105-108). §11.1 gives H1 NO, H2 NO, H3 YES, H4 HIGH. The orientation is checked numerically: `J(d=-1) = 1/ratio`, and the inverted interval equals 1/the interval (gate C13). |
| 5 | Holm over exactly 9 | **CONFIRMED** | `FAMILY` has 9 members (§11.2). Step-down `max_{j≤i} min(1, (9−j+1)·p(j))` matches my recount. Six members at the 10,000-shuffle floor p 0.0001 adjust to 0.0009. H2 0.9993, H1 1.0000 and H3 1.0000 all adjust to 1.0000. |
| 6 | H1-H3 Mantel-Haenszel ratio | **CONFIRMED** | See the "Check 6" section below. |
| 7 | Verdict words (§5.3), including the one-era qualifier | **CONFIRMED** | See the "Check 7" section below. |
| 8 | B1 pooled reproduction | **CONFIRMED** | My code, using the ticker tie-break over all 4,665 events: 3,671 events in 87 months. Bottom 120/1,256 = 0.096, middle 0.113, top 154/1,190 = 0.129, ratio 1.355. Era A 1.48, era B 1.08. This matches RESULT 8 and `confirm.txt`. Gate C10 ran before any family number was derived (line 629). |
| 9 | No feature or read used a bar at or after E | **CONFIRMED** | See the "Check 9" section below. |
| 10 | Report text vs printout | **CONFIRMED** | The verdict lines, base rates, B1 block, H1-H3 "seen" lines and window ±50% rows in the report equal `confirm.txt`. The counts table equals my recount (e.g. f09 21/756 · 75/745 · 152/730; H3 113/1,285 vs 87/626). |

### Check 1 — ran once
**Builder transcript** (`agent-a80d221721412ed04.jsonl`):
- Exactly ONE `python3 confirm.py` invocation without `--synthetic`, at 06:22:08Z.
- Before it, five synthetic runs, all to the scratchpad.
- No `rm` of `confirm.txt` anywhere.

**Script shas:**
- `syn1` and `syn2` print script sha `0d971bb6…`, the version before the patch.
- `syn3`, `syn4`, `syn5` and the real run print `5776dde3…`.
- That matches "patched once between runs 2 and 3".

**File times (PST):**

| Time | Event |
|---|---|
| 22:21:17 | `confirm.py` last modified |
| 22:21:17 → 22:22:00 | `syn3`, `syn4`, `syn5` |
| 22:22:08 | `confirm.err` written |
| 22:22:24 | `confirm.txt`, `.exit` and `.sha256` written |

**Other evidence:**
- `find /` finds only one `confirm.txt`.
- The script refuses to run if `confirm.txt` exists.
- From `syn5` (the run on the already-seen discovery outcomes) the builder read only `grep "C13 GATE\|STOP"`. Those lines carry only f01, f02, f03, f09 and f16 discovery figures, which were already seen.

### Check 6 — H1-H3 Mantel-Haenszel ratio
- **Method:** I used my own MH over (era, month), months with ≥ 6 scored events and ≥ 2 of each group. Ratio in his direction: no/yes for H1 and H2, yes/no for H3.
- **Ratios:** H1 0.507 · H2 0.568 · H3 0.495.
- **Per era:** H1 era A 0.45, era B 0.53 · H2 0.50 / 0.59 · H3 0.57 / 0.47.
- **The direction does not hang on the stratification.** Without the month rule and without strata, the rates read the same way:

| Read | Big-winner rate, yes | Big-winner rate, no |
|---|---|---|
| H1 | 0.134 | 0.093 |
| H2 | 0.123 | 0.096 |
| H3 | 0.088 | 0.138 |

### Check 7 — verdict words
- **Thirds:** the word is judged on the smoothed ratio. The raw ratio gives the same word for all 9 members. No member is near the 1.2 or 1.0 bars: the lowest PICKS ratio is 2.47, the highest REVERSED ratio is 0.57.
- **One-era qualifier:** "same direction" = both era ratios above 1.0. All six PICKS members pass in both eras; the lowest is f03 era B at 2.09. So the qualifier "(one era only)" does not apply.
- **Volatility tag:** it is printed as §2 defines it. I recomputed both of its inputs independently:
  - ADR-neutral: f02 1.36, f03 1.13, f09 2.01, f18 1.58, the combination 1.74.
  - ADR-scaled tail: 0.89, 1.06, 1.00, 1.01, 1.00.
- **Under §11.3 the tag changes no word.** It is not applied to H4. "Shelf relative" applies to no member (the shelf relatives are f05 and f07). "Era-B thinned" is not triggered (stage-1 D2: 0 excluded days against a trigger of 20).

### Check 9 — no bar at or after E
**My own code** computes values from bars strictly before E plus open(E). It matches the table on every scored event:

| Value | Events matched |
|---|---|
| ADR20 | 4,665 |
| f02 | 4,656 |
| f03 | 4,656 |
| f09 | 4,571 |
| H1 | 4,051 |
| H2 | 3,911 |
| H3 | 4,051 |

**Other inputs:**
- f18 equals `prev_close_raw` (E−1) on all 4,665 events.
- H4 equals `adr20_raw` on all 4,656 non-null events.
- The combination is built only from these.
- All layouts (`LAY`, ADR and dmin strata) form before the outcome block. My layouts equal `grp_*` for all nine members (0 mismatches).
- Outcomes include E's own close, which §2 allows.

### Outcomes recount
- big winner / monster / ADR tail / forward bars: 0 mismatches on the 2,251 confirm events.
- Confirm totals: 252 big winners, 67 monsters, 70 events with fewer than 61 forward bars (kept).

## Notes (none is a defect; none can move a word)
- **REVERSED is one-sided in his stated direction only.** "EPs opening below the 200-day / in a downtrend win more" was not pre-registered, so it is NOT confirmed by this run.
- **H1-H3 count as three in Holm** but are close to one read (§11.2).
- **"FRAGILE" on H1-H3 in the window ±50% rows is the literal §5.5 rule** ("under 1.2"). They are below 1.0 at every length, so consistently against his direction, not unstable.
- **The tag gives no reason to discount a member.** Per §11.3, "— a volatility proxy" is a description.
- **The builder's standing caveats are restated, not chased.** Forward bad prices are unscreened, 70 events have short windows, f18's era-B raw price uses the post-cut split input (§8), the confirm years are partly seen (§0), and power at a family of 9 was not simulated. None can carry a ratio of 2.5-8x at the permutation floor, or of about 0.5, across a bar.
- **No selection, ranking, entry or stop recommendation** is made here (THE LINE).
