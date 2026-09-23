"""One-off addendum to _622score_driver.py: score the operator's OWN illustrative
example (CHPT, 2026-09-03, $134M mcap, gapped ~50% -- see _622_features_out.txt)
through the exact same point-in-time pipeline. CHPT falls OUTSIDE both the winner
(>+0.5R) and loser (<=-0.9R) buckets used for the main 48-name sample (its
09:31-settled realized_r_0931 = +0.33R -- a partial win, not yet resolved by
09:31; by 09:36 it was already marked +2.0R unrealized) -- so it is reported here
as a NAMED CASE STUDY, never blended into the winner/loser headline stats.

Run: docker cp -> docker exec -w /app apollo-market python /tmp/_622score_chpt.py
(after _622score_driver.py has already been docker cp'd -- reuses its functions).
"""
import asyncio
import json
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/tmp")

from agents.market_intelligence import db  # noqa: E402
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("_622score_driver", "/tmp/_622score_driver.py")
drv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drv)


async def main():
    feats = drv.load_features(drv.FEATURES_PATH)
    row = feats[("CHPT", "2026-09-03")]
    pool = await db.get_pool()
    rec = await drv.score_one(pool, "CHPT", "2026-09-03", row)
    rec["label"] = "case_study_not_in_sample"
    with open("/tmp/_622score_chpt_out.json", "w") as f:
        json.dump(rec, f, indent=2)
    print(json.dumps(rec, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
