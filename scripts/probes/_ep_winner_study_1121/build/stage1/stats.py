#!/usr/bin/env python3
"""Thirds / two-group assignment of prereg §5.1 and §2 (ADR-neutral) — outcome-free helpers shared by 04 and 06."""
from __future__ import annotations

import numpy as np
import pandas as pd

MIN_MONTH = 6        # §5.1: (era, month) groups with >= 6 events scored on the feature
MIN_STRATUM = 9      # §2 / §5.2-5: strata with >= 9 scored events
MIN_TWO = 2          # two-group features: months with >= 2 of each


def thirds_block(vals: np.ndarray, tick: np.ndarray, midrank: bool = True) -> np.ndarray:
    """0 = bottom, 1 = middle, 2 = top third of one group, by np.array_split of the sorted order.
    midrank=True (features 1-20): a block of equal values is never split — the whole block goes to the third that holds its
    mid-rank position ((first + last position) // 2: on a half-integer mid-rank the LOWER of the two middle positions).
    midrank=False: ties broken by ticker (PRE-REG 6's rule, kept for B1 only)."""
    n = len(vals)
    order = np.lexsort((tick, vals))
    pos_third = np.concatenate([np.full(len(p), k) for k, p in enumerate(np.array_split(np.arange(n), 3))])
    out = np.empty(n, dtype=np.int8)
    if not midrank:
        out[order] = pos_third
        return out
    sv = vals[order]
    a = 0
    while a < n:
        b = a
        while b + 1 < n and sv[b + 1] == sv[a]:
            b += 1
        out[order[a:b + 1]] = pos_third[(a + b) // 2]
        a = b + 1
    return out


def assign_thirds(df: pd.DataFrame, col: str, keys: list, min_n: int, midrank: bool = True) -> np.ndarray:
    """per-event third (0/1/2) within each group of `keys` holding >= min_n events scored on `col`; -1 = not assigned."""
    out = np.full(len(df), -1, dtype=np.int8)
    x = df[col].to_numpy(dtype=float)
    ok = np.isfinite(x)
    sub = df[ok]
    for _, idx in sub.groupby(keys, sort=False).indices.items():
        pos = np.flatnonzero(ok)[idx]
        if len(pos) < min_n:
            continue
        out[pos] = thirds_block(x[pos], df.ticker.to_numpy()[pos], midrank)
    return out


def assign_two(df: pd.DataFrame, g: np.ndarray, keys: list, min_n: int = 0, min_each: int = MIN_TWO) -> np.ndarray:
    """two-group feature: g = 1 / 0 / -1 (NULL). Returns 2 (yes) / 0 (no) within groups with >= min_each of each (and >= min_n scored); else -1."""
    out = np.full(len(df), -1, dtype=np.int8)
    ok = g >= 0
    sub = df[ok]
    for _, idx in sub.groupby(keys, sort=False).indices.items():
        pos = np.flatnonzero(ok)[idx]
        gy = g[pos]
        if len(pos) < min_n or (gy == 1).sum() < min_each or (gy == 0).sum() < min_each:
            continue
        out[pos] = np.where(gy == 1, 2, 0)
    return out


def pct_rank_within(df: pd.DataFrame, col: str, keys: list, mask: np.ndarray) -> np.ndarray:
    """within-group percentile rank (average rank - 0.5) / n over the events in `mask`; NaN elsewhere."""
    out = np.full(len(df), np.nan)
    sub = df[mask]
    r = sub.groupby(keys, sort=False)[col].rank(method="average")
    n = sub.groupby(keys, sort=False)[col].transform("size")
    out[np.flatnonzero(mask)] = ((r - 0.5) / n).to_numpy()
    return out


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean(); b = b - b.mean()
    den = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / den) if den > 0 else float("nan")
