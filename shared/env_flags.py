"""One reading of "is this env flag on", so two callers cannot disagree about it.

WHY THIS EXISTS (2026-09-20, the #672 simplify pass). `job_recovery.dry_run_enabled` and
`telegram_hold.send_late_enabled` were written the same day, in different modules, as the same
expression against different variable names. They govern a PAIR of switches on one behaviour —
whether a recovery re-runs, and whether its Telegrams go out — so a divergence between them is
not cosmetic: a flag spelled `y` that one accepted and the other rejected would re-run jobs while
silently holding every message, or the reverse.

⚠ WHY IT GREW A SECOND FUNCTION (2026-09-21, the simplify review). The module shipped solving a
general problem and was adopted by exactly the two callers it was written for, while **~30
hand-rolled parses stayed put — including `LIVE_TRADING_ENABLED` read independently in
`constants.py` AND `agent.py`, and `ALPACA_PAPER` read independently in `constants.py` AND
`broker/bar_stream.py`.** Two readers of the kill switch, and two of the paper-vs-live routing
decision: the exact divergence the paragraph above was written to stop, sitting on the money path.

It was not adopted because it could not be, without changing behaviour twice over:
  1. `TRUTHY` accepts `{1,true,yes,on}` where every one of those sites accepts `"true"` alone —
     migrating them would WIDEN what turns real trading on. That is THE LINE, not a cleanup.
  2. It had no default, and `ALPACA_PAPER` and `ENABLE_LIVE_MODE` default ON — so a blind
     conversion would have flipped paper trading to LIVE the moment the variable was unset.

So there are two named readings and every call site picks one, rather than inheriting a meaning:

  · `env_flag_on(name)`  — permissive. Accepts any spelling in `TRUTHY`. For flags introduced
    with that contract; unset or empty is OFF.
  · `env_is_true(name, default=..., strip=...)` — EXACT. True only for the literal "true"
    (case-insensitive), which is what every pre-existing flag in this repo has always meant.
    Byte-identical to `os.environ.get(name, "true"|"false").lower() == "true"`, including the
    two edges that matter: a variable set to the EMPTY string is OFF even when `default=True`
    (only an ABSENT variable takes the default), and whitespace is NOT stripped unless asked,
    so `" true"` stays OFF and cannot quietly turn a money flag on.

⚠ WIDENING THE ACCEPTED SPELLINGS OF A MONEY FLAG IS THE OPERATOR'S CALL, NOT A REFACTOR'S.
`LIVE_TRADING_ENABLED`, `ALPACA_PAPER`, `ENABLE_LIVE_MODE`, `REGIME_SIZING_ENABLED`,
`R3_DAY1_REENTRY_ENABLED` and `STOP_ACK_TIMEOUT_GATE_ENABLED` use `env_is_true` deliberately.
Do not "tidy" them onto `env_flag_on` — that changes what turns real trading on.
"""
from __future__ import annotations

import os

#: The spellings that count as ON for `env_flag_on`. Anything else — including an unset or empty
#: variable — is OFF, so the safe state is the default in every caller (hold the messages, do not
#: re-run, leave the arm off). ⚠ NOT what `env_is_true` accepts; see the module docstring.
#:
#: ⚠ `"enabled"` is here because `theme_merge_arm` had its OWN third copy of this set and that
#: copy accepted it. Folding the copy in without this would have NARROWED a live operator toggle:
#: `THEME_MERGE_ARM=enabled` turned the arm on before and would silently have stopped doing so —
#: and that arm's own docstring says the flip is his decision. A consolidation that quietly drops
#: a spelling somebody may already be using is not a consolidation, it is a regression.
TRUTHY = frozenset({"1", "true", "yes", "on", "enabled"})


def env_flag_on(name: str) -> bool:
    """True when `name` is set to one of `TRUTHY` (case- and whitespace-insensitive)."""
    return os.environ.get(name, "").strip().lower() in TRUTHY


def env_is_true(name: str, *, default: bool = False, strip: bool = False) -> bool:
    """True only for the literal "true", case-insensitive — this repo's long-standing meaning.

    `default` applies when the variable is **absent**, never when it is present-but-empty: that
    is what `os.environ.get(name, "true").lower() == "true"` does, and the difference decides
    whether an empty `ALPACA_PAPER` routes to paper or to LIVE. `strip` is off by default for the
    same reason — with it off, `" true"` is OFF, and no money flag can be turned on by stray
    whitespace. Pass `strip=True` only where the call site already stripped.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    return (raw.strip() if strip else raw).lower() == "true"
