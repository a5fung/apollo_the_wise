"""The one-event-per-identity-per-60-sessions keep rule (prereg 1.2, blind). Variants are parameters so the text's indicative numbers
(10,514 at q=1/5 ...) on the 11-13 capture can settle the boundaries the text leaves open."""
import hashlib
import numpy as np

GRID = [1, 1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 6, 1 / 8, 1 / 10]


def coin(seed, ident, dstr, byteorder="big"):
    h = hashlib.sha256(f"{seed}|{ident}|{dstr}".encode()).digest()
    return int.from_bytes(h[:8], byteorder) / 2.0 ** 64


def walk(idents, ci, dstrs, q, seed=1124, win=60, incl=False, byteorder="big", coins=None):
    """idents/ci/dstrs parallel arrays of break rows. Returns bool kept array. A row is ELIGIBLE when no KEPT row of its identity lies in
    the `win` sessions before it (ci_k in [ci-win, ci-1] when incl else (ci-win, ci-1]); an eligible row is KEPT when its coin < q."""
    n = len(idents)
    order = np.lexsort((ci, idents))
    kept = np.zeros(n, bool)
    last_kept_ci = None
    prev_id = None
    if coins is None:
        coins = np.array([coin(seed, idents[i], dstrs[i], byteorder) for i in range(n)])
    for i in order:
        if idents[i] != prev_id:
            prev_id, last_kept_ci = idents[i], None
        c = ci[i]
        if last_kept_ci is not None and (c - last_kept_ci <= win if incl else c - last_kept_ci < win):
            continue
        if coins[i] < q:
            kept[i] = True
            last_kept_ci = c
    return kept


def first_after_quiet(idents, ci, quiet=10, strict=False):
    """True when the identity's previous break row is at least quiet+1 sessions earlier (quiet sessions between = gap-1 >= quiet), or there is none.
    strict -> gap > quiet+1."""
    n = len(idents)
    order = np.lexsort((ci, idents))
    out = np.zeros(n, bool)
    prev_id, prev_ci = None, None
    for i in order:
        if idents[i] != prev_id:
            prev_id, prev_ci = idents[i], None
        gap = None if prev_ci is None else ci[i] - prev_ci
        out[i] = gap is None or (gap > quiet + 1 if strict else gap - 1 >= quiet)
        prev_ci = ci[i]
    return out
