"""#275 — set/clear the operator's kill/scale band override (safeguards.md operator
condition #2). The override covers the BANDS only — it does NOT lift the mechanical guards
(2% daily-loss, drawdown breaker). After writing, ALSO add a change-log entry to
docs/setups/safeguards.md (the SSoT requires both the audit row AND the change-log line).

    docker exec apollo-market python scripts/set_kill_scale_override.py set "continue full size" "reason ..."
    docker exec apollo-market python scripts/set_kill_scale_override.py clear
"""
import asyncio
import sys

from agents.market_intelligence.kill_scale_bands import (
    record_override, clear_override, get_active_override,
)


async def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("set", "clear"):
        print('usage: set_kill_scale_override.py set "<direction>" "<reason>"  |  clear')
        return
    if sys.argv[1] == "clear":
        await clear_override("live")
        print("kill/scale override CLEARED")
    else:
        direction = sys.argv[2] if len(sys.argv) > 2 else "(unspecified)"
        reason = sys.argv[3] if len(sys.argv) > 3 else ""
        await record_override(direction, reason, "live")
        print(f"kill/scale override SET: {direction} — {reason}")
    print("active override now:", await get_active_override("live"))


if __name__ == "__main__":
    asyncio.run(main())
