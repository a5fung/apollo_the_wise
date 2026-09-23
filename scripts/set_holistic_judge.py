"""Flip / read the Holistic Grade Judge authority toggle (W2 go-live gate, ADR 0011).

OPERATOR-gated — flip ON only after reviewing the promotion/demotion delta lists + the
Unjustified Demotion Sweep (the agent never self-certifies the demotion list). Paper-only;
instant revert with no redeploy (durable in mi_safeguard_state). ON makes the holistic judge
drive the paper grade; OFF reverts to the conviction floor.

  docker exec apollo-market python scripts/set_holistic_judge.py status
  docker exec apollo-market python scripts/set_holistic_judge.py on
  docker exec apollo-market python scripts/set_holistic_judge.py off

REVERT CAVEAT (advisor review 2026-06-10): flipping OFF stops NEW overrides
instantly but does NOT revert rows the judge already overrode that day —
e.g. a demote-to-'none' stays suppressed. The floor counterfactual is
preserved in baseline_floor_tier; to restore today's overridden rows:

  UPDATE mi_ep_alerts
  SET score_tier = baseline_floor_tier, grade_engine_authority = 'floor'
  WHERE alert_date = current_date AND grade_engine_authority = 'judge';

(Read-only check first: SELECT ticker, score_tier, baseline_floor_tier ...)
"""
import asyncio
import sys

from agents.market_intelligence import db


async def main(cmd: str) -> None:
    if cmd == "status":
        print("holistic_judge_enabled =", await db.get_holistic_judge_enabled())
    elif cmd in ("on", "off"):
        await db.set_holistic_judge_enabled(cmd == "on")
        print(f"set holistic_judge_enabled = {cmd}; readback =",
              await db.get_holistic_judge_enabled())
    else:
        print("usage: set_holistic_judge.py status|on|off")
        sys.exit(2)


asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "status"))
