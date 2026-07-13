"""Flip / read the M1-d composite-authority toggle (the M1-d go-live gate, ADR 0024 §6).

OPERATOR-gated — flip ON only at the M1-d sitting (the agent never self-authorizes the
flip). Paper-only; instant revert with no redeploy (durable in mi_safeguard_state).
Default OFF / DARK: with no row the read FAILS CLOSED to False and the grade path is
byte-identical to pre-M1-d. ON composes the theme-axis credit onto the authoritative
tier (grade_engine_authority='composite' when the tier actually moves); OFF reverts to
the base grade (floor/judge per the holistic-judge toggle).

  docker exec apollo-market python scripts/set_composite_authority.py status
  docker exec apollo-market python scripts/set_composite_authority.py on
  docker exec apollo-market python scripts/set_composite_authority.py off

REVERT CAVEAT (mirrors set_holistic_judge.py): flipping OFF stops NEW composed
overrides instantly but does NOT revert rows already composed that day — e.g. a
composed MODERATE→HIGH stays HIGH. The base tier is preserved in baseline_floor_tier;
to restore today's composed rows:

  UPDATE mi_ep_alerts
  SET score_tier = baseline_floor_tier, grade_engine_authority = 'floor'
  WHERE alert_date = current_date AND grade_engine_authority = 'composite';

(Read-only check first: SELECT ticker, score_tier, baseline_floor_tier ... Note this
restores the FLOOR tier — if the composition rode on a judge override, the judge tier
is in judge_tier; restoring to judge instead of floor is the operator's call.)
"""
import asyncio
import sys

from agents.market_intelligence import db


async def main(cmd: str) -> None:
    if cmd == "status":
        print("composite_authority_enabled =", await db.get_composite_authority_enabled())
    elif cmd in ("on", "off"):
        await db.set_composite_authority_enabled(cmd == "on")
        print(f"set composite_authority_enabled = {cmd}; readback =",
              await db.get_composite_authority_enabled())
    else:
        print("usage: set_composite_authority.py status|on|off")
        sys.exit(2)


asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "status"))
