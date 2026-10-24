# #705 replay 02 — adversarial review of the execution-variant registration (2026-10-23, before the freeze)

Reviewed: `docs/analysis/cb_qm_replay_execution_prereg_2026-10-23.md` (sha 6155c91a…), `02_execution_variants.py` (18b6d368…),
`test_02_execution_variants.py` (0568a6f5…), against `docs/methodology/operator_shared_notes.md` l.1929-1956 (his article) and
l.2433-2499 (his 10-22 notes), and `01_replay.py` + its §RESULT. Ran: pytest (34 passed), `--dry-run` (exit 0; identical to the
stored printout except timing; the stored file was restored byte for byte), `check_analysis_doc.py` (exit 0). No outcome opened.

| check | PASS/FAIL | evidence |
|---|---|---|
| V1 level known before the open | PASS | `pivot_tl` = the line drawn on bars up to D, projected one session to E (cb:331-374, 678); a row exists iff high(E) > pivot (runner:859, cb:1681-1684), which is the buy-stop's own fill condition, so no selection beyond the fill |
| V1 gap fill uses the open, not a later price | PASS | `fill = (level if op <= level else op) * (1 + slip)` on the first minute with high > level from minute 0 (cb:1003, 1008); test l.199-208 |
| V1 stop = the low of the day AT the fill | **FAIL (disclosed, understated)** | stop = `minutes.l[:m+1].min()` includes the fill minute's own low (cb:1009); `day0_walk` starts at `minute > fill_minute` (cb:970). On a minute-0 fill the stop IS minute 0's low, so minute 0 would stop it by construction: the exemption covers EVERY open fill, not "a little" (doc l.48-51). Two further channels are not disclosed: the too-wide skip (cb:987) reads that same low, so a fill whose first minute drops more than one ADR is skipped at no cost; and the size reads it whenever width > 1% / cap. Same convention as V0 (frozen, parity-gated) and chosen as R1 (doc l.293), but only V1 / COMBINED fill in minute 0, and COMBINED decides the fork |
| V2 = TC2000's formula on bars dated <= D | PASS | `adr_pair` = mean(H/L) − 1 over bars[D−19 .. D] (02:243-255); `d_index` asserts the bar on D (02:258-263); ours recomputed = the stored `adr20` on every event to 1e-12 (dry run); TC is passed to `entry_variants` only, and the walk keeps ours (02:396, 411); the formula has a median error of 0.07 vs 0.11 on 896 frames (`03_frame_check.txt` l.13-17) |
| V2 "the gap is small" | **FAIL (doc)** | doc l.139-141 cites the medians only; the dry run shows TC − ours **max 59.9 pp** (control) and 59.9 (re-entry rows). That means a bad low inside a 20-day window. On such an event the V2 / COMBINED too-wide gate passes anything |
| V3 only breaks after the exit | PASS | `exit_d < E2` with `exit_d = cal[e_ci + sessions_held]` (02:480-483); `sessions_held` = the stop session j (cb:1330, 1411), and 0 on day 0 (cb:1496); test l.344-358 |
| V3 within 20 sessions of the ORIGINAL E | PASS | `lim` comes from the origin trade's `e_ci` and is fixed for the whole chain (02:477); test l.366-369 (E+20 in, E+21 out) |
| V3 max 2, refused / unfilled use no slot | PASS | `while n_re < MAX_REENTRIES` (02:479); refusals and no-fills are passed with `continue` (02:485-492); test l.344-358 |
| V3 sized as new trades | PASS | `union_trades` gives each re-entry its own Trade (02:536-544); `simulate` sizes each on the previous close's equity (01:814); test l.388-400 |
| V3 control gets the same rule | PASS (asymmetry to name) | the same `campaigns(... TT[v.entry], v.chain ...)` for his / ctl / post (02:902-908); the control also obeys R8, so 560 control rows can never be re-entered while his chains have no label rule (02:510-515, dry run). Registered, but it lowers the band slightly, which helps his side on the band arm |
| V4 as registered | PASS | `CAP30 = Config("cap_30", cap=0.30)`: risk 1%, stock limit 30%, skip, allow (02:157; 01:178-197); test l.419-427 asserts it equals the first read's `cap_30`; the parity gate checks the curve and the band (02:955-957) |
| the control receives every variant identically | PASS | `compute` loops over VARIANTS × groups on the same entry set, chain and config (02:899-908); the band runs `v.cfg` on `camps[ctl]` over the same 200 draws (02:943-950), built exactly as 01:1456-1483 (same seed key, same pool order); V0 / V4 bands are parity-gated |
| fork thresholds fixed | PASS | `FORK_YEARS (2020, 2021)`, `FORK_RET 0.50`, `BAND_SHARE_MAX 0.05` (02:123-125); `fork_exec` needs BOTH years and the band, and refuses a NaN share (02:633-643); doc §7 l.210; test l.441-451 |
| disclosure: variants chosen after the fills | PASS | doc l.34-35, 46-47, 224, 321-322; printed with the verdict (02:1219-1220) |
| freeze lock | PASS | marker matched only as a whole line (02:197-198); exactly one is required, else every pin counts as missing (02:209-221); the doc has one at l.328. My independent sha256 of the bytes above it = 7a2c44d4…, which equals the dry run's `doc_body`. An inline, indented or doubled marker is refused; tests l.493-527, 559-595 |
| `check_analysis_doc.py` | PASS | exit 0 |
| tests | PASS | 34 passed; the e2e test runs the frozen first read and then the parity gate, and a tampered R stops the run (test l.676-786) |

## Fixes, most severe first (none changes a rule, a threshold or the walk; all go above the marker, then re-run the dry run for the new `doc_body` pin)

1. **§1.4(b) l.48-56: state the V1 stop convention at its true size.** Replace "It flatters V1's gap fills a little" with:
   - every fill in minute 0 is exempt from a minute-0 stop-out by construction, because its stop is that minute's own low;
   - the too-wide skip reads the same low, so a fill whose first minute fell more than one ADR is skipped, and that loss is never booked;
   - the size reads it whenever the width is above 1% ÷ the cap;
   - the effect favours V1 and COMBINED only, and COMBINED is the fork variant. An EXPLAINED reading will be questioned on this point first.
   - Point to the real-run counts that size it (`at_open` and `stopped on day 0`, 02:1006-1015).
   - Recommended, print-only: in `walk_event2` (02:403-412), flag fills and `too_wide` abstains of `level` / `level_tc` whose stop is the fill minute's own low (m == 0, or `l[m] < l[:m].min()`), and print both counts for his calls and the control.
   - Fix the matching wording in the module docstring (02:15-16, "stop = the low of the day at the fill") and the test comment (test l.205).
2. **§4 l.139-141: give the gap's maximum, not only its median.** State the 59.9 pp maximum and that it comes from a bad low inside the 20-day window. Recommended, outcome-free: one dry-run line in `describe_superset` (02:805-809) listing the events where TC − ours > 2 pp, by group, so the V2 gate is not silently open on them.
3. **§7 l.211 and §11: name the stop lever left untested.** His 10-22 note (notes l.2435-2449) names "a stop placement problem". Its NOT TESTED row (stops wider than one ADR, or the structural base-low stop) is still not tested here: V2 only swaps the ADR formula under the same one-ADR skip, and V2b caps at one ADR. Add "stop placement beyond one ADR / the structural stop" to the NEXT GAPS list and to §11. Keep `FORK_TEXT["NEXT GAPS"]` (02:649-651) word for word with it.
4. **§5 l.164-165: the per-event numbers are not independent.** A re-entry that is itself a group event (33 of his re-breaks) lands in two campaigns, so the per-event table and the date-matched line count it twice. One sentence. It does not touch the fork, because the account dedupes.
5. **§3 l.111-113: name the R8 asymmetry's direction.** The 560 refused control rows can only lower the band, so they ease the band arm for his calls.

## Verdict: FIX (doc-only before the freeze; no code logic, rule or threshold changes)

The mechanics hold: V2, V3, V4, the control's symmetry, the fork constants, the freeze lock, the gate and the tests all pass. The
blocker is wording: §1.4(b) understates a look-ahead that sits in the fork variant. Apply fixes 1-5, run `--dry-run`, paste the pins, freeze.
