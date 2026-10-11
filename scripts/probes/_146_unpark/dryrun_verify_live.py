"""#146 unpark: builds the simulated-column dry-run SQL (the column does not exist on prod until the deploy). Run from the repo root,
then pipe the .sql to prod psql (SELECT-only); the .out beside it is that run."""
import re

src = open("scripts/probes/_146_unpark/verify_live.sql").read()
sim = ("(SELECT *, CASE WHEN stage = 'TRIGGERED' AND held_from_stage IS NULL THEN 'coiled' END AS triggered_from "
       "FROM mi_flag_candidates)")
# keep the file's own text; only swap the table for the simulated-column subselect (aliasing it back to the same name)
out = re.sub(r"(FROM|JOIN) mi_flag_candidates( p)?(?=\s)", lambda m: f"{m.group(1)} {sim} {'p' if m.group(2) else 'mi_flag_candidates'}", src)
open("scripts/probes/_146_unpark/verify_live_dryrun.sql", "w").write(out)
print(out.count(sim), "substitutions")
