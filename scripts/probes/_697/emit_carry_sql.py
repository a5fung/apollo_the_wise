"""#697 item 2: emit the EXACT carry query `get_flag_universe` runs, as a PREPARE/EXECUTE script for prod psql.

Not a re-typed copy: the SQL text is captured from the real function through a fake connection, so what
runs on prod is byte-for-byte what the scan will run. Run from the repo root:
    PYTHONPATH=. python scripts/probes/_697/emit_carry_sql.py > scripts/probes/_697/q5_carry_prod.sql
then on prod (read-only SELECT):  ssh ... psql ... < q5_carry_prod.sql > q5_carry_prod.out
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from agents.market_intelligence import db as db_mod

# 2026-10-11 review fix: the carry now requires a BAR ON THE SCAN DATE, so a date with no bars yet returns nothing -
# 10-12 can no longer be pre-run (its prediction lives in q1_admit_replay.out), and 09-07 (Labor Day partial scan,
# 0 bars) must carry NOTHING. 09-14 is the last night FBRX (last bar 08-26) was carried on frozen history.
DATES = ["2026-09-03", "2026-09-04", "2026-09-07", "2026-09-08", "2026-09-09", "2026-09-14", "2026-09-16", "2026-10-09"]


async def capture() -> tuple[str, tuple]:
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[])
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)
    with patch.object(db_mod, "get_pool", new=AsyncMock(return_value=pool)):
        await db_mod.get_flag_universe("2026-09-03")
    call = conn.fetch.await_args_list[3]            # (a+b), (c), (d), (e)
    return call.args[0], call.args[1:]


sql, params = asyncio.run(capture())
assert "scan_days" in sql, "captured the wrong query"
print("-- #697 item 2: the production carry query, run read-only for several scan dates.")
print(f"PREPARE carry(date, int, int) AS {sql.strip()};")
for d in DATES:
    print(f"\\echo ## {d}")
    print(f"EXECUTE carry('{d}', {params[1]}, {params[2]});")
print("\\echo ## EXPLAIN 2026-10-09")
print(f"EXPLAIN (ANALYZE, BUFFERS) EXECUTE carry('2026-10-09', {params[1]}, {params[2]});")
