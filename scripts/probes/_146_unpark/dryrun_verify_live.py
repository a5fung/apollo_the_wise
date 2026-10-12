"""#146 unpark: builds the simulated-column dry-run SQL (the column does not exist on prod until the deploy). Run from the repo root,
then pipe the .sql to prod psql (SELECT-only); the .out beside it is that run."""
import re

src = open("scripts/probes/_146_unpark/verify_live.sql").read()
sim = ("(SELECT *, CASE WHEN stage = 'TRIGGERED' AND held_from_stage IS NULL THEN 'coiled' END AS triggered_from "
       "FROM mi_flag_candidates)")
# keep the file's own text; only swap the table for the simulated-column subselect (aliasing it back to the same name)
out = re.sub(r"(FROM|JOIN) mi_flag_candidates( [a-z])?(?=\s)",
             lambda m: f"{m.group(1)} {sim} {m.group(2).strip() if m.group(2) else 'mi_flag_candidates'}", src)
open("scripts/probes/_146_unpark/verify_live_dryrun.sql", "w").write(out)
print(out.count(sim), "substitutions")

# POSITIVE CONTROL: the same statements with the simulated stamp deliberately WRONG ('retrigger' on every raw TRIGGERED row, as
# a broken precedence would write). Statements 2 and 4 must print VIOLATION here - the proof they can fail at all.
wrong = out.replace("THEN 'coiled' END AS triggered_from", "THEN 'retrigger' END AS triggered_from")
assert wrong != out
open("scripts/probes/_146_unpark/verify_live_dryrun_wrongstamp.sql", "w").write(wrong)
