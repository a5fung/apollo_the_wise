"""#663 — when a byte-identity guard fails, it must say WHAT differed.

WHY THIS EXISTS. Two tests assert the EP scan returns an identical result when nothing
relevant changed; they are the tripwire on money-path edits. On 2026-09-14 one of them failed
in CI on a tree whose code had not changed, and left NO usable trail — because the assertion
was:

    assert _canon(a) == _canon(b)          # _canon = json.dumps(obj, sort_keys=True, default=str)

Two ~50 KB JSON strings compared as strings. pytest reports "not equal" and dumps both. Nobody
can read that, so the one observation we had produced no information, and 60 subsequent runs
(20 full-suite, 40 with PYTHONHASHSEED varied) could not summon it again.

⚠ **The point is not prettier output. The point is that an unreproducible failure has to
explain itself the first time, because there may not be a second time.**

KEY-PRESENCE DIFFERENCES ARE REPORTED FIRST, deliberately. Every confirmed instance of this
bug class has been a SHAPE change, not a value change: a classifier raises, the code assigns
nothing instead of assigning None, and the key vanishes from one run's result. `setup_class`
did it (d747f414) and `catalyst_type` did it (found 2026-09-19). A value difference is
possible but has never been the one that bit.
"""
from __future__ import annotations

import json

MAX_REPORTED = 12
_VALUE_CLIP = 120


def canon(obj) -> str:
    """The canonical form both tests already used — kept identical so this changes what a
    FAILURE says and never what counts as equal."""
    return json.dumps(obj, sort_keys=True, default=str)


def _clip(v) -> str:
    s = repr(v)
    return s if len(s) <= _VALUE_CLIP else s[:_VALUE_CLIP] + "…"


def differences(a, b, path: str = "") -> list:
    """Every difference between two JSON-ish structures, as readable lines.

    Returns key-presence differences BEFORE value differences — see the module docstring.
    """
    missing, values, other = [], [], []

    def walk(x, y, p):
        if isinstance(x, dict) and isinstance(y, dict):
            for k in sorted(set(x) - set(y)):
                missing.append(f"KEY PRESENT ONLY IN A: {p}.{k} = {_clip(x[k])}")
            for k in sorted(set(y) - set(x)):
                missing.append(f"KEY PRESENT ONLY IN B: {p}.{k} = {_clip(y[k])}")
            for k in sorted(set(x) & set(y)):
                walk(x[k], y[k], f"{p}.{k}")
            return
        if isinstance(x, (list, tuple)) and isinstance(y, (list, tuple)):
            if len(x) != len(y):
                other.append(f"LENGTH: {p} has {len(x)} in A, {len(y)} in B")
            for i in range(min(len(x), len(y))):
                walk(x[i], y[i], f"{p}[{i}]")
            return
        if type(x) is not type(y):
            other.append(f"TYPE: {p} is {type(x).__name__} in A, {type(y).__name__} in B")
            return
        if x != y:
            values.append(f"VALUE: {p} = {_clip(x)} in A, {_clip(y)} in B")

    walk(a, b, path or "<root>")
    return missing + other + values


def assert_byte_identical(a, b, what: str) -> None:
    """Assert two scan outputs are identical, and on failure say exactly how they differ.

    ⚠ Equality is still decided by `canon`, byte-for-byte — identical to the assertion this
    replaces. Only the FAILURE MESSAGE is new, so this cannot make a failing guard pass.
    """
    if canon(a) == canon(b):
        return
    diffs = differences(a, b)
    if not diffs:
        # Canonical strings differ but the structural walk found nothing: a key ORDER or
        # formatting difference that json.dumps(sort_keys=True) should have removed. Say so
        # rather than printing an empty report — this is itself a finding.
        raise AssertionError(
            f"{what} differ by canonical string but NOT structurally — the difference is in "
            f"serialisation, not content. A={canon(a)[:400]!r} B={canon(b)[:400]!r}")
    shown = diffs[:MAX_REPORTED]
    more = f"\n  … and {len(diffs) - len(shown)} more" if len(diffs) > len(shown) else ""
    raise AssertionError(
        f"{what} differ — {len(diffs)} difference(s), key-presence first "
        f"(#663: every confirmed instance of this bug class has been a MISSING KEY, not a "
        f"changed value):\n  " + "\n  ".join(shown) + more)
