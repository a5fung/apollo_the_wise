"""Dry run of the depth-exit STAMP over a FABRICATED in-memory toggle table. NEVER a database read.

Why it exists (2026-10-10, "the depth exit also covers the small-cap paper lane"): the new behaviour
is event-gated in production — it can only be seen on the first NEW `magna53_smallcap` paper row
AFTER the 'paper' toggle row exists (Tue 2026-10-13 at the earliest). After the deploy this proves,
the same day and with no market open and no row written, that the code the entry funnel runs (the
`apollo-execution` container; `submit_trade_entry` -> `order_manager.resolve_exit_rule_stamp`)
stamps by the signed rule. It drives the REAL `resolve_exit_rule_stamp` and the REAL toggle read
(`_magna53_depth_exit_enabled`); the only thing it replaces is `db.get_safeguard_state`, with a fake
that has the table's real primary-key semantics ((safeguard, account_mode) -> its OWN row or None).

  docker exec -i apollo-execution python - < scripts/probes/_wk1010_depth_paper/dryrun_stamp.py

PASS prints `DRYRUN PASS` and exits 0. On the PRIOR code `_DEPTH_EXIT_STRATEGIES` does not exist and a
`magna53_smallcap` row is never stamped, so it prints `DRYRUN FAIL` and exits 1 — the broken system
cannot print PASS. No database connection is opened, no broker call is made, nothing is written.
"""
from __future__ import annotations

import asyncio
import sys

from agents.market_intelligence import db
from agents.market_intelligence.broker import order_manager as om

SMALLCAP, M53, NINE_M, LOWCAP = "magna53_smallcap", "magna53", "9m_day2", "magna53_lowcap"

# (toggle rows present, signal_type, row's account mode) -> the stamp it must get
CASES = [
    # the new behaviour: the PAPER row stamps a smallcap paper row ...
    ({"paper": "on"}, SMALLCAP, "paper", "depth"),
    ({"live": "on", "paper": "on"}, SMALLCAP, "paper", "depth"),
    # ... and only the PAPER row does: the live row alone, no row, or an off row do not
    ({"live": "on"}, SMALLCAP, "paper", None),
    ({}, SMALLCAP, "paper", None),
    ({"paper": "off"}, SMALLCAP, "paper", None),
    # live MAGNA53 follows the LIVE row alone, exactly as before
    ({"live": "on"}, M53, "live", "depth"),
    ({"live": "on", "paper": "on"}, M53, "live", "depth"),
    ({"paper": "on"}, M53, "live", None),
    ({}, M53, "live", None),
    # nothing else is ever stamped
    ({"live": "on", "paper": "on"}, NINE_M, "paper", None),
    ({"live": "on", "paper": "on"}, NINE_M, "live", None),
    ({"live": "on", "paper": "on"}, LOWCAP, "paper", None),
]


async def main() -> int:
    bad: list = []

    strategies = getattr(om, "_DEPTH_EXIT_STRATEGIES", None)
    if strategies != frozenset({"magna53", "magna53_smallcap"}):
        bad.append(("strategy set", strategies))

    real_get = db.get_safeguard_state
    try:
        for rows, signal_type, mode, want in CASES:
            async def _get(name, account_mode, _rows=rows):
                st = _rows.get(account_mode) if name == "magna53_depth_exit" else None
                return {"state": st} if st else None

            db.get_safeguard_state = _get
            got = await om.resolve_exit_rule_stamp(signal_type, mode)
            tag = "ok  " if got == want else "BAD "
            print(f"  {tag}rows={sorted(rows.items())!s:<36} {signal_type:<17} {mode:<5} "
                  f"-> {got!r} (want {want!r})")
            if got != want:
                bad.append((rows, signal_type, mode, got, want))
    finally:
        db.get_safeguard_state = real_get

    if bad:
        print(f"DRYRUN FAIL — {len(bad)} mismatch(es): {bad}")
        return 1
    print("DRYRUN PASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
