"""#146 unpark: builds the simulated-column dry-run SQL (the column does not exist on prod until the deploy). Run from the repo root,
then pipe the .sql to prod psql (SELECT-only); the .out beside it is that run."""
import re

doc = open("docs/setups/htf.md").read()
a = doc.index("## Bucket the TRIGGERED reads")
b = doc.index("## Known limitations / open questions")
sec = doc[a:b]
blocks = re.findall(r"```sql\n(.*?)```", sec, re.S)
assert len(blocks) == 3, len(blocks)
sim = ("(SELECT *, CASE WHEN stage = 'TRIGGERED' AND held_from_stage IS NULL THEN 'coiled' END AS triggered_from "
       "FROM mi_flag_candidates)")
out = []
for i, blk in enumerate(blocks):
    sub = re.sub(r"(FROM|JOIN) mi_flag_candidates( c)?(?=\s)",
                 lambda m: f"{m.group(1)} {sim} {'c' if m.group(2) else 'mi_flag_candidates'}", blk)
    assert sim in sub, i
    out.append(f"\\echo '== Q{i}: exactly the SQL in htf.md, column simulated =='\n" + sub.strip())
open("scripts/probes/_146_unpark/q8_ssot_selects_dryrun.sql", "w").write("\n".join(out) + "\n")
print(len(blocks), "blocks")
