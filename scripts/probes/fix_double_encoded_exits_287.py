#!/usr/bin/env python3
"""#287 data-cleanup — decode the pre-fix double-encoded mi_live_trades.exits / .running_closes.

The #287 CODE fix (deployed 2026-07-07) stops NEW double-encoding; this repairs the EXISTING
rows the bug left behind — a jsonb value stored as a STRING (`jsonb_typeof='string'`, e.g.
`"[{...}]"`) instead of the array it should be. 26 exits rows + several running_closes as of 7/7.

Mechanism — a pure SQL decode, NO Python codec involved (so no re-encode risk):
    SET col = (col #>> '{}')::jsonb      -- extract the root as text (unescapes the string
                                          -- content) then re-parse that text as jsonb -> array
Idempotent + safe: the WHERE only matches `jsonb_typeof(col)='string'`, so a re-run is a no-op
and a concurrently-correct row is never touched (predicate re-asserted in the UPDATE's WHERE).
Readers already tolerate both forms (isinstance(list) else json.loads), so this changes NO
behavior — it corrects the STORED representation so raw consumers (the #306 sweep, SQL) see arrays.

Trade-state write → COMMITTED + reviewed + dry-run-first (feedback_no_docker_exec_for_trade_state);
NOT an inline `docker exec python -c`. Dry-run by default; pass --commit to apply.
"""
import argparse
import asyncio

_COLS = ("exits", "running_closes")


async def main(commit: bool) -> None:
    from agents.market_intelligence.db import get_pool

    pool = await get_pool()
    total_fixed = 0
    async with pool.acquire() as conn:
        for col in _COLS:
            # Dry-run validation: decode each corrupted row IN SQL and confirm it yields an
            # array. This SELECT errors loudly if any row's string content is not valid jsonb
            # (none should be — the bug json.dumps'd valid lists — but fail loud, not silent).
            rows = await conn.fetch(
                f"""
                SELECT id, ticker, status,
                       jsonb_typeof(({col} #>> '{{}}')::jsonb) AS decoded_type,
                       LEFT({col} #>> '{{}}', 54) AS preview
                FROM mi_live_trades
                WHERE jsonb_typeof({col}) = 'string'
                ORDER BY id
                """
            )
            print(f"\n== {col}: {len(rows)} double-encoded row(s) ==")
            bad = [r for r in rows if r["decoded_type"] not in ("array", "object")]
            for r in rows:
                mark = "  " if r["decoded_type"] in ("array", "object") else "!!"
                print(f"{mark}id={r['id']:>4} {r['ticker']:<6} {r['status']:<9} "
                      f"string -> {r['decoded_type']}   {r['preview']}")
            if bad:
                print(f"  ⚠ {len(bad)} row(s) do NOT decode to array/object — NOT touching {col}. "
                      f"Investigate before committing.")
                continue

            if commit and rows:
                res = await conn.execute(
                    f"""
                    UPDATE mi_live_trades
                    SET {col} = ({col} #>> '{{}}')::jsonb
                    WHERE jsonb_typeof({col}) = 'string'
                    """
                )
                n = int(res.split()[-1])  # 'UPDATE <n>'
                total_fixed += n
                remaining = await conn.fetchval(
                    f"SELECT count(*) FROM mi_live_trades WHERE jsonb_typeof({col}) = 'string'"
                )
                print(f"  ✅ COMMITTED {col}: {n} row(s) decoded; remaining strings = {remaining}")

    if commit:
        print(f"\nDONE — {total_fixed} column-value(s) repaired.")
    else:
        print("\nDRY-RUN — no writes. Re-run with --commit to apply.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="#287 decode double-encoded exits/running_closes")
    ap.add_argument("--commit", action="store_true", help="apply the fix (default: dry-run)")
    asyncio.run(main(ap.parse_args().commit))
