REVISE-FIRST. The re-challenge's ten findings are fixed, but four new defects would make the 11-29 page say something false. Two are blocking and two are one-line fixes; three prose notes are below.

**Re-challenge findings 1–10: fixed (checked by probe)**
- `probe1.py` against the new runner (`720_freeze/probe1_out.txt`): an empty capture now opens line 1 with "capture incomplete" and the five folded rows are always printed.
- Era C now gives `arm_r` None and armed False; the width-dropped records are named; the Fisher test still gives 0.141.
- A fuller probe (`probe2.py`, `probe2_out.txt`): three old fills with no recorder rows say "recorder gap on 3 fill(s)"; three young fills say "too few trades to read yet (3 closed live fill(s)…)".
- The 11-03 fill keys to the 08-31 admission era before the #718 open-floor rule, the 11-04 fill to the new era after it; CANNOT TELL now maps to CAN'T TELL; the breakout test is capped at WATCH.
- `--emit-predicates` output is byte-identical to `capture/predicates.sql` (checked myself).

**The `rule_eras` change: nothing else breaks**
- 20 test files touch `rule_eras` or `admission_era`; all of them plus the SSoT router, analysis-doc, readiness, live_rules and #715 tests: 1020 passed, 1 skipped. Backlog-teeth and weekly-MFE: 22 passed. `check_plan` OK; `live_rules --drift-only` found nothing.
- No production code or YAML hard-codes the 08-31 label.
- The only reader of the switch list outside the recorders is `system_review._review_era_note`. It prints the count and latest date, which is now correctly 11-04.
- The six live recorders will stamp the new label once this is deployed. It is a label only and touches no money path.

**Blocking**
1. **A failed capture reads as an empty month.** The README runs `psql … > runs/<date>/data/<name>.csv`. When psql fails, the shell has already created a 0-byte file, and `missing_captures()` only checks that the file exists.
   - `probe3.py` / `probe3_out.txt`: 0-byte `cf_arms`, `predicates` and `audit_recorder` give `not_captured=[]` and line 1 "recorder gap on 3 fill(s)", a false accusation against the recorder.
   - On the same page the folded rows say "n/a — not captured".
   - Fix: `\copy … CSV HEADER` always writes a header line, so a file with no header line should count as NOT CAPTURED, in both `missing_captures()` and `write_manifest()`.
2. **Line 1 contradicts itself in the most likely real-data case.** In `answer_line`, the NOTHING check comes before WATCH. One arm that lost, one that won on fewer than 10 trades and one unreadable print "Nothing beats what we run; 1 arm(s) on watch", but WATCH means that arm beat what we run.
   - The end-to-end test only covers the case where every arm won ("13 on watch"), and `test_f1` never mixes NOTHING with WATCH.
   - Fix: check WATCH first (say how many arms read as beaten and how many as not), and add the mixed case to `test_f1`.

**Fix now (one line each)**
3. **The heartbeat's first session should be 09-04, not 09-03.** The #482 job was built 09-03 (4b6e4148, 14:43 ET) but deployed after that night's 18:04 ET run: 0d612463 at 21:57 ET reads "the clock finally starts tomorrow", and 32f8ee88 on 09-04 reads "The recorder fired at 18:04 ET… first night".
   - Today the page lists 09-03 as a session with no row and calls it "the job's first session" (`probe2_out.txt`, A2 and H2).
   - Fix three places: the constant and its comment (`run_review.py:89`), `tests/test_720_monthly_review.py:770,992`, and plan §1.4 line 111.
   - I could not read prod; confirm with the earliest `audit_recorder.csv` row on the first capture.
4. **A dead recorder never reaches line 1.** With `ran 0 of 60` sessions and no old closes, line 1 says "too few trades to read yet", which means "wait", when the real answer is "the recorder is dead" (`probe2_out.txt`, H). Fix: send `ran == 0`, or no row in the last `GAP_RETRY_SESSIONS` sessions, to the recorder-gap headline. Do this together with item 3, or every page will lead with a gap.

**Prose only**
5. **The note goes stale after Monday.** "Recorder rows stamped 11-04..11-07" appears 8 times across `rule_eras.py`, `magna53_ep.md` and the runner. It only stays true if the `rule_eras` row is live before Mon 11-09 18:04 ET, and this branch is not on main or deployed.
   - Either make the text open-ended ("from 11-04 until the row deployed"), or the main loop ships `rule_eras` this weekend. That choice is the main loop's, not mine.
6. **The SSoT line overstates who re-derives.** The `magna53_ep.md` line "readers use the derived label" is true of the #720 runner only. The 593, 617 and 624 recorder tables keep the 08-31 label on their 11-04-onward rows (the 482 recorder writes each row once and never updates it), and their YAML reviews say to split by `admission_era`. Say so in the doc.

Action: none for him. The main loop fixes 1–4 with a test for each, fixes 5–6 in the text, then freezes the plan.

Files are in `/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/720_freeze/`:
- `probe1_out.txt`
- `probe2.py`, `probe2_out.txt`
- `probe3.py`, `probe3_out.txt`
- `pytest_out.txt`
- `FINDINGS.md`