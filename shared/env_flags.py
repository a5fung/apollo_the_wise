"""One reading of "is this env flag on", so two callers cannot disagree about it.

WHY THIS EXISTS (2026-09-20, the #672 simplify pass). `job_recovery.dry_run_enabled` and
`telegram_hold.send_late_enabled` were written the same day, in different modules, as the same
expression against different variable names. They govern a PAIR of switches on one behaviour —
whether a recovery re-runs, and whether its Telegrams go out — so a divergence between them is
not cosmetic: a flag spelled `y` that one accepted and the other rejected would re-run jobs while
silently holding every message, or the reverse.

Two one-liners are not worth a module on their own. A shared definition of what "on" MEANS,
sitting between two switches that must agree, is.
"""
from __future__ import annotations

import os

#: The spellings that count as ON. Anything else — including an unset or empty variable — is OFF,
#: so the safe state is the default in both callers (hold the messages, do not re-run).
TRUTHY = frozenset({"1", "true", "yes", "on"})


def env_flag_on(name: str) -> bool:
    """True when `name` is set to one of `TRUTHY` (case- and whitespace-insensitive)."""
    return os.environ.get(name, "").strip().lower() in TRUTHY
