"""READ-ONLY backfill PREVIEW — catalyst_type -> forward-outcome distribution.

North Star weekend (2026-05-30), MVP C1 step 5. Classifies the settled-HIGH
EP cohort by the NEW catalyst_type signal (Pradeep hierarchy) and joins forward
returns to produce the FIRST layer-2 evidence of whether catalyst TYPE predicts
EP outcome (theme/policy vs operational vs none).

STRICTLY READ-ONLY: reads a cohort JSON exported from prod via read-only SELECT
(see the companion ssh psql pull), classifies each row with the isolated
`catalyst_type_classifier` (advisory, never gates), aggregates locally. Writes
NOTHING to prod. The actual mi_ep_alerts.catalyst_type backfill UPDATE is a
SEPARATE Monday-in-hours step — this only PREVIEWS the distribution.

Usage:
  # 1. export cohort (read-only) -> scripts/_catalyst_type_cohort.json  (ssh psql)
  # 2. python scripts/preview_catalyst_type_backfill.py [cohort.json]
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def _load_env() -> None:
    """Minimal .env loader (ANTHROPIC_API_KEY) — no external dep."""
    env = REPO / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _fmt(xs: list[float]) -> str:
    if not xs:
        return "n=0"
    wins = sum(1 for x in xs if x > 0)
    return (
        f"n={len(xs):>3}  avg={statistics.mean(xs):+6.2f}%  "
        f"med={statistics.median(xs):+6.2f}%  wr={100*wins/len(xs):>3.0f}%"
    )


async def main() -> int:
    _load_env()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not found (env or .env)", file=sys.stderr)
        return 1

    _positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    cohort_path = Path(_positional[0]) if _positional else REPO / "scripts" / "_catalyst_type_cohort.json"
    if not cohort_path.exists():
        print(f"ERROR: cohort file not found: {cohort_path}\n"
              f"Export it first via the read-only ssh psql pull.", file=sys.stderr)
        return 1

    rows = json.loads(cohort_path.read_text(encoding="utf-8"))
    if not rows:
        print("ERROR: cohort empty", file=sys.stderr)
        return 1
    print(f"Classifying {len(rows)} settled-HIGH alerts (read-only, advisory)...\n")

    from agents.market_intelligence.catalyst_type_classifier import (
        classify_catalyst_type, CATALYST_TYPES, CATALYST_TYPE_RANK,
    )

    async def _one(r: dict) -> dict:
        res = await classify_catalyst_type(
            r["ticker"], r.get("catalyst"), r.get("claude_analysis"),
        )
        return {**r, **res}

    classified = await asyncio.gather(*[_one(r) for r in rows])

    # Optional: stage the Monday backfill UPDATE as a .sql file (NOT applied here —
    # this is read-only weekend; apply Monday via `ssh ... psql < <file>`). The
    # UPDATE only fills NULLs (`AND catalyst_type IS NULL`) so it can NEVER clobber
    # a forward-classified (live, clean) row — and historical/backfill rows stay
    # distinguishable from clean forward rows by alert_date >= deploy day. See
    # feedback_backfill_llm_label_lookahead (theme/policy backfill is hindsight-optimistic).
    if "--emit-sql" in sys.argv:
        i = sys.argv.index("--emit-sql")
        out_sql = Path(sys.argv[i + 1]) if i + 1 < len(sys.argv) else REPO / "scripts" / "_backfill_catalyst_type.sql"

        def _q(s):  # single-quote SQL-escape, or NULL
            if s is None:
                return "NULL"
            return "'" + str(s).replace("'", "''") + "'"

        stmts = ["-- STAGED Monday backfill (hindsight-caveated; fills NULLs only). NOT auto-applied.",
                 "-- apply: ssh apollo@... \"docker exec -i apollo-postgres psql -U apollo -d apollo\" < this_file",
                 "BEGIN;"]
        n_emit = 0
        for c in classified:
            ct = c.get("catalyst_type")
            if not ct:
                continue  # never write NULL/failed
            stmts.append(
                f"UPDATE mi_ep_alerts SET catalyst_type={_q(ct)}, "
                f"catalyst_type_rationale={_q(c.get('rationale'))} "
                f"WHERE ticker={_q(c['ticker'])} AND alert_date='{c['alert_date']}' "
                f"AND catalyst_type IS NULL;"
            )
            n_emit += 1
        stmts.append("COMMIT;")
        out_sql.write_text("\n".join(stmts) + "\n", encoding="utf-8")
        print(f"\nSTAGED {n_emit} backfill UPDATE statements → {out_sql} (NOT applied — Monday).")

    # Aggregate fwd_5d_pct by catalyst_type
    by_type: dict[str, list[float]] = defaultdict(list)
    by_type_10d: dict[str, list[float]] = defaultdict(list)
    for c in classified:
        ct = c.get("catalyst_type") or "FAILED(None)"
        f5 = c.get("fwd_5d_pct")
        if f5 is not None:
            by_type[ct].append(float(f5))
        f10 = c.get("fwd_10d_pct")
        if f10 is not None:
            by_type_10d[ct].append(float(f10))

    print("=" * 78)
    print("catalyst_type  ->  forward 5d outcome   (Pradeep order; '*' = high-tier)")
    print("=" * 78)
    order = list(CATALYST_TYPES) + ["FAILED(None)"]
    for ct in sorted(by_type, key=lambda t: CATALYST_TYPE_RANK.get(t, 99)):
        star = "*" if ct in ("theme", "policy", "shortage") else " "
        tag10 = ""
        if by_type_10d.get(ct):
            tag10 = f"   |10d avg={statistics.mean(by_type_10d[ct]):+6.2f}%"
        print(f"{star} {ct:<20} {_fmt(by_type[ct])}{tag10}")

    # High-tier (theme/policy/shortage) vs operational vs none — the headline cut
    print("\n" + "-" * 78)
    hi = [x for ct in ("theme", "policy", "shortage") for x in by_type.get(ct, [])]
    op = [x for ct in ("sales_acceleration", "new_product", "management_change")
          for x in by_type.get(ct, [])]
    lo = [x for ct in ("other", "none") for x in by_type.get(ct, [])]
    print(f"  THEME/POLICY/SHORTAGE (Pradeep top-3) : {_fmt(hi)}")
    print(f"  OPERATIONAL (sales/product/mgmt)      : {_fmt(op)}")
    print(f"  OTHER / NONE                          : {_fmt(lo)}")
    print("-" * 78)

    # Per-name table (eyeball the spot-checks: MNDY/KLAR/RCAT/OMCL/AMD/BW/CRSR)
    print("\nper-alert (sorted by type rank, then fwd_5d desc):")
    print(f"  {'ticker':<7}{'date':<12}{'type':<20}{'score':>6}{'fwd5d':>8}  rationale")
    for c in sorted(classified, key=lambda c: (
            CATALYST_TYPE_RANK.get(c.get("catalyst_type") or "", 99),
            -(c.get("fwd_5d_pct") or -999))):
        ct = c.get("catalyst_type") or "FAILED"
        f5 = c.get("fwd_5d_pct")
        f5s = f"{float(f5):+.1f}%" if f5 is not None else "  ?"
        print(f"  {c['ticker']:<7}{str(c.get('alert_date','')):<12}{ct:<20}"
              f"{(c.get('ep_score') or 0):>6}{f5s:>8}  {(c.get('rationale') or '')[:60]}")

    fails = sum(1 for c in classified if c.get("catalyst_type") is None)
    print(f"\nclassifier hard-failures (None/NULL): {fails}/{len(classified)}")
    print("READ-ONLY preview complete — no prod writes. (Backfill UPDATE = Monday.)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
