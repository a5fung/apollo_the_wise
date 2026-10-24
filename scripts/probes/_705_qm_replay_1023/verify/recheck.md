# #705 QM replay — round-2 recheck of the revised registration + `01_replay.py` (2026-10-23, pre-freeze)

**Verdict: FIX — one blocker.** The freeze lock hashes only lines 1–347 of the doc. The doc has three copies of the marker text, and
the lock splits on the first one, a mention inside §11 at l.348. Fixes 1–10 all landed. The deciding math checks out by hand.
Everything else is ready to run.

Run here:
- `pytest test_01_replay.py`: 42 passed (0.54 s).
- `01_replay.py --dry-run`: exit 0. Its printout matches the saved `01_replay_dryrun.txt` except the load-time line (6 s vs 7 s).
- Freeze record "NOT YET", as expected.

What I opened (outcome disclosure):
- No minute file, no bar after any E, no walk, no R.
- Outcome-free reads only: the `retrigger` column of both candidate files (value counts: only 0 / 1; era A 20,650 / 60,365, era B
  12,250 / 28,950), the doc's bytes (marker count) and the Track A doc's marker lines.
- Side effects: the dry run rewrote `01_replay_dryrun.txt`. I restored it from a copy, byte-identical (`cmp` passed; mtime changed;
  the file is not pinned). `__pycache__` was touched by the import. Scratch scripts are in the session scratchpad only.

## Round-1 fixes

The round-1 files are untracked, so `git diff` has no base. I checked each fix against review.md's line references and the doc's §13
table. Every §13 line reference is accurate.

| fix | status | where |
|---|---|---|
| 1 HIGH date-matched deciding difference | **landed** | `paired_block_diff` 01_replay.py:679, date-matched block 738–765; `his_minus_control` 1338–1347 passes `a_date`/`b_date`; fork reads `m_lo` 1510–1511. Doc §3 l.100–102, §5 l.150–161, R6 l.364, R12 l.372. Tests 440, 456 (heavy-bad-days: matched 0 vs pooled +1.23), 471 |
| 2 MED sizing = his words + SSoT, 30% per stock | **landed** | `Config` 180–195 (1% / 20% / 30%), `CONFIGS` 198–201 (risk 0.25 / 0.5, cap 10 / 30), the limit at cost 816–824, cost released 854–859. Doc §0 l.25–26, §6 l.169–173 and 212–218 (false claim gone). Tests 323, 380 |
| 3 MED curve arm needs the band | **landed** | `BAND_SHARE_MAX` 174, `fork_verdict` 933–948, input 1509–1511. Doc §8 rows l.233–235; the "~100R" line replaced at l.238–243. Test 496 |
| 4 MED no post-E exclusion | **landed** | `cut_at_break` 541–556, `walk_event` 570–572, `keep` uses `break_pre` only 1037, listing 1241–1250. Doc §10 l.299–303, R8 l.369–371. Tests 214, 231, 246, 269 |
| 5 LOW strict-127 beside + 119 / 109 / 10 wording | **landed** | `EXPECT` 208–210 (asserted; dry run prints 119 / 109 / 10), beside print 1526–1541. Doc l.42–46, 251–252, 391–392 |
| 6 LOW `constants.py` pinned | **landed** | `CODE` 125; asserts 69–71. Test 637 |
| 7 LOW R6 wording | **landed** | doc l.364 "FILLED AND MATURE" |
| 8 LOW `empty` event KeyError | **landed** | `.get` + `no_minutes` 1181–1184. Test 257 |
| 9 LOW degraded count + booked R | **landed** | 1324–1330 (per group: not mature, degraded, cut at a break, summed booked R) |
| 10 NOTE max-drawdown share label | **landed** | 1475, 1494; doc §6 l.207–208 |

## Break attempts

| target | what I did | result |
|---|---|---|
| same-day matching math | Synthetic hand case, 3 cells over 2 months, one cell uncovered. His [2, 0] vs control mean 0.5; his [−1] vs control mean −5/11; his [3] with no control in its stratum | Code = hand at machine precision: matched 5/33 = 0.1515; pooled 21/17 = 1.2353; stratum-only 0.7404; cells 3 / uncovered 1 / his dropped 1 / matched 3 |
| the month-block bootstrap | Rebuilt the generator `default_rng([702, crc32(key)])` and re-drew by hand. 3-month case: per-resample means and the 2.5 / 97.5 percentiles. 2-month case: the dropped count | Equal to the code: interval [0.0833, 1.6667] in both. Draws holding only the uncovered month: 471 by hand = 471 dropped. A month drawn twice enters twice and the cell means stay fixed, as §5 says (R6 holds) |
| sizing vs his words | operator_shared_notes.md:1944 (*positions 10–20%; risk 0.25–1%, rarely more than 1%; at most 30% in one stock overnight*); SSoT consolidation_breakout.md:232 (*position = min(20%, 1% ÷ stop width)*) | Primary 1% / 20% / 30% sits inside his ranges and equals the SSoT. The beside rows cover the rest of his ranges. The limit is applied at entry, at cost (see note 2) |
| curve-arm band test | Read `fork_verdict` and the band path 1455–1511. Checked: same `simulate`, same config, same per-date event count, kept events only, the share is ≥ his primary-config final, an unreadable share is a refusal | Correct and matches the doc's three rows. Order: SELECTION if either arm; else DATES / market if his curve is strong; else EXECUTION |
| post-E break | `cut_at_break` keeps the forward bars dated strictly before the first break after E. A break past the window, or on / before E, cuts nothing (test 226–228). A degraded walk ends with a `mark` leg (cb:1470–1483), so the legs-sum-to-1 assert holds | No exclusion is left. The only residual is the runner's standard rule: a walk still open where its bars end is not mature (note 3) |
| freeze lock | `pins()` covers all inputs, code incl. `constants.py`, both minute trees and `doc_body`. AST check: no walk function (`entry_variants`, `day0_walk`, `walk_arms`, `exitpb_walk_arms`, the minute readers) uses the unpinned `anticipation.py` / `flag_detector.py` / `broker/exit_logic.py` | **BLOCKER** below. Otherwise complete for the walk path |
| look-ahead | QQQ read on closes ≤ D. Sizing on the previous close. Entries placed in fill-minute order. The band draws by date only. The control is excluded only on a label said ≤ its own E. No E-day or forward column is read. `retrigger` is only 0 / 1, so `sidx` cannot KeyError mid-run | None found. E's full-day range enters only the `minute_daily_mismatch` abstain (runner parity, both arms, round 1) |

## BLOCKER — the doc-body hash stops at a mention of the marker, 74 lines above the real one

- The doc holds `<!-- FREEZE -->` 3 times:
  - l.348, inside §11 guard 1: *above \`<!-- FREEZE -->\`, taken at run time*;
  - l.422, the real marker;
  - l.426, in the freeze-record text.
- `doc_body_sha` (01_replay.py:275) and `freeze_missing` (:312) both split on the FIRST copy. So `doc_body` = sha256 of lines 1–347
  only (`31533302…`, 30,996 bytes of the 39,292 above the real marker).
- Not covered: §11 from guard 1 on (the guards, R1–R12 incl. R6 cell weights, R8 break cut, R12 uncovered cells, the outputs), all of
  §12 and the §13 revisions table. An edit there after the freeze commit would not be refused.
- The tests miss it because every freeze test doc (test 566–631) holds the marker once.
- The Track A doc is NOT affected: its first copy is its real marker (l.567); its l.597 mention sits below it.
- **Exact fix:**
  1. Split on the marker as its own line, `"\n" + FREEZE_MARKER + "\n"`. It occurs once today, at l.422.
     - l.275, `doc_body_sha`: `fh.read().split(b"\n" + FREEZE_MARKER.encode() + b"\n", 1)[0]`, edited in place.
     - l.310–312, `freeze_missing`: replace `if FREEZE_MARKER not in txt:` with
       `if txt.count("\n" + FREEZE_MARKER + "\n") != 1:`, which returns every pin as missing. Then split the tail on the same string.
     - The exactly-once refusal must live in `freeze_missing`, not as an `assert` in `doc_body_sha`. `pins()` runs outside the `try`
       (l.1133), so an assert there is a traceback. In `freeze_missing` it goes through the registered exit-2 refusal (l.1143–1146).
  2. **Keep the module line count unchanged.** Both functions sit above every module line §13 cites (541 … 1536). §13 comes inside
     the hash with this fix, so one added line would freeze wrong references. If lines must be added, refresh §13's module line
     numbers before the dry run.
  3. Append a test at the END of `test_01_replay.py`, so the test line refs in §13 stay valid:
     - the doc mentions `` `<!-- FREEZE -->` `` in its body above the real marker line;
     - an edit between that mention and the real marker changes `doc_body`, and the real run refuses;
     - a doc with two line-anchored markers is refused.
  4. Re-run `--dry-run` to re-pin: `replay_module`, `replay_tests` and `doc_body` all change. Then paste the freeze record below
     l.422 and commit.
  - Optional: reword l.348 / l.426 to "the FREEZE marker" so the literal text appears once.

## Not blockers (direction stated)

1. **Months with no covered trade of his stay in the bootstrap's month pool.** These are months whose calls all failed to fill, were
   not mature, or were uncovered. They are needed for the one-draw-for-all-three design, since the pooled and stratum-only
   differences use them. For the matched difference they only vary how many of his months a resample holds. That widens the
   interval a little (harder to meet the interval arm) and adds no bias. Resamples holding none are dropped and counted.
2. **The 30% per-stock limit is at cost, at entry.** His "of the account overnight" could be read at market value. It binds only on
   a second position while the first is held (≤ 48 calls are a repeat crossing of a called base). At cost allows slightly more than
   at market after a run-up. The choice is disclosed in §6.
3. **A walk still open where its bars end (delisting, buyout, a cut at an identity break) is in no per-trade number.** That depends
   on the outcome: it was still held. This is the runner's universal rule for both arms. Count, names and summed booked R are
   printed. Holes are already cut by `forward_window`, and a "jump" break is by definition a >70% move with no volume event, i.e. a
   data artifact (ext_bars.py:16–20).
4. **Within a day, every entry comes before every intraday exit.** A 09:40 stop-out does not free cash for a 10:30 fill. This is
   conservative and is not look-ahead; the order is registered in §6.
5. **The 236 deciding calls include 109 that rest only on a label said on E.** Disclosed in §1.4a. Both arms are printed on the
   strictly-before 127 beside the verdict. If the two disagree, the headline must say so (§12 already requires it).
6. **Python and numpy versions are not pinned.** The run follows the freeze directly, so the risk is small.

**After the fix:** re-run the dry run, then paste the pins below l.422 and commit. Then make the one real run. No rule, threshold or
population changes.
