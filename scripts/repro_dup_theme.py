"""Reproduce the 04-27 duplicate-theme bug:
two themes with identical tickers {TER, ONTO} both score 78.6 should merge to 1.

Run inside container:
  docker exec apollo-market python -m scripts.repro_dup_theme
"""
import asyncio

from agents.market_intelligence.theme_engine import (
    _enforce_max_themes_per_stock,
    _merge_overlapping_themes,
)


async def main():
    stocks_by_ticker = {
        "TER":  {"ticker": "TER",  "rs_composite": 92, "sector": "Technology"},
        "ONTO": {"ticker": "ONTO", "rs_composite": 88, "sector": "Technology"},
        "KLAC": {"ticker": "KLAC", "rs_composite": 90, "sector": "Technology"},
        "MU":   {"ticker": "MU",   "rs_composite": 86, "sector": "Technology"},
        "AMAT": {"ticker": "AMAT", "rs_composite": 84, "sector": "Technology"},
        "NVDA": {"ticker": "NVDA", "rs_composite": 95, "sector": "Technology"},
        "AMD":  {"ticker": "AMD",  "rs_composite": 89, "sector": "Technology"},
        "FOO":  {"ticker": "FOO",  "rs_composite": 70, "sector": "Technology"},
        "BAR":  {"ticker": "BAR",  "rs_composite": 71, "sector": "Technology"},
    }

    scenarios = [
        ("2 protected, identical tickers, tied scores", [
            {"name": "Semiconductor Burn-In & Final-Test Equipment Pure-Play",
             "tickers": ["TER", "ONTO"], "score": 78.6, "stage": "Accelerating",
             "theme_date": None, "description": ""},
            {"name": "Semiconductor Capital Equipment",
             "tickers": ["TER", "ONTO"], "score": 78.6, "stage": "Accelerating",
             "theme_date": None, "description": ""},
        ], {"Semiconductor Burn-In & Final-Test Equipment Pure-Play",
            "Semiconductor Capital Equipment"}),

        ("3 protected (incl. Probe Card), identical tickers, tied scores", [
            {"name": "Semiconductor Burn-In & Final-Test Equipment Pure-Play",
             "tickers": ["TER", "ONTO"], "score": 78.6, "stage": "Accelerating",
             "theme_date": None, "description": ""},
            {"name": "Semiconductor Capital Equipment",
             "tickers": ["TER", "ONTO"], "score": 78.6, "stage": "Accelerating",
             "theme_date": None, "description": ""},
            {"name": "Semiconductor Probe Card & Front-End Test Equipment",
             "tickers": ["TER", "ONTO"], "score": 78.6, "stage": "Accelerating",
             "theme_date": None, "description": ""},
        ], {"Semiconductor Burn-In & Final-Test Equipment Pure-Play",
            "Semiconductor Capital Equipment",
            "Semiconductor Probe Card & Front-End Test Equipment"}),

        ("Burn-In is NEW (not protected), Cap Equipment is existing", [
            {"name": "Semiconductor Burn-In & Final-Test Equipment Pure-Play",
             "tickers": ["TER", "ONTO"], "score": 78.6, "stage": "Accelerating",
             "theme_date": None, "description": ""},
            {"name": "Semiconductor Capital Equipment",
             "tickers": ["TER", "ONTO"], "score": 78.6, "stage": "Accelerating",
             "theme_date": None, "description": ""},
        ], {"Semiconductor Capital Equipment"}),
    ]

    for label, themes, protected in scenarios:
        out = await _merge_overlapping_themes(themes, stocks_by_ticker, protected_names=protected)
        print(f"\n=== {label} ===")
        print(f"  in : {[t['name'] for t in themes]}")
        print(f"  out: {[t['name'] for t in out]}")
        print(f"  protected: {sorted(protected)}")
        print(f"  result: {len(themes)} -> {len(out)} themes "
              f"({'MERGED OK' if len(out) < len(themes) else 'NOT MERGED FAIL'})")

    # ---------------------------------------------------------------
    # Cap-strip scenarios: exercise the FULL pipeline (merge -> cap)
    # to test the hypothesis that _enforce_max_themes_per_stock can
    # CREATE duplicate ticker sets by stripping a shared ticker.
    # ---------------------------------------------------------------
    cap_scenarios = [
        ("cap-strip: 3 protected, KLAC in all, scores 90/85/80, A&B near-identical pre-cap", [
            # Pre-cap: A and B differ only by KLAC vs MU. C has KLAC + uniques.
            # After cap: KLAC is in 3 themes, stripped from C (lowest). A keeps KLAC,
            # B keeps MU. A and B were never identical, so no dup expected here.
            {"name": "Theme A (Burn-In)", "tickers": ["TER", "ONTO", "KLAC"],
             "score": 90.0, "stage": "Accelerating", "theme_date": None, "description": ""},
            {"name": "Theme B (Cap Eq)",  "tickers": ["TER", "ONTO", "MU"],
             "score": 85.0, "stage": "Accelerating", "theme_date": None, "description": ""},
            {"name": "Theme C (Foundry)", "tickers": ["KLAC", "FOO", "BAR"],
             "score": 80.0, "stage": "Accelerating", "theme_date": None, "description": ""},
        ], {"Theme A (Burn-In)", "Theme B (Cap Eq)", "Theme C (Foundry)"}),

        ("cap-strip: A=B={TER,ONTO,KLAC} pre-cap (real prod shape), C={KLAC,FOO,BAR}", [
            # The actual prod situation: A and B already identical pre-cap. Merge
            # SHOULD catch them via Pass 1 (intersection=3 >= MIN_SHARED_FOR_MERGE).
            {"name": "Theme A (Burn-In)", "tickers": ["TER", "ONTO", "KLAC"],
             "score": 90.0, "stage": "Accelerating", "theme_date": None, "description": ""},
            {"name": "Theme B (Cap Eq)",  "tickers": ["TER", "ONTO", "KLAC"],
             "score": 85.0, "stage": "Accelerating", "theme_date": None, "description": ""},
            {"name": "Theme C (Foundry)", "tickers": ["KLAC", "FOO", "BAR"],
             "score": 80.0, "stage": "Accelerating", "theme_date": None, "description": ""},
        ], {"Theme A (Burn-In)", "Theme B (Cap Eq)", "Theme C (Foundry)"}),

        ("cap-strip: A={TER,ONTO,KLAC,FOO}, B={TER,ONTO,KLAC,BAR}, C={KLAC,...}", [
            # |A∩B|=3, jaccard 3/5=0.6 → Pass 1 should merge them. If merge fires:
            # no dup. If we made |A∩B|=2 by changing one ticker, merge skips and cap
            # could strip KLAC from C (if KLAC in 3 themes), but A/B differ.
            {"name": "Theme A", "tickers": ["TER", "ONTO", "KLAC", "FOO"],
             "score": 90.0, "stage": "Accelerating", "theme_date": None, "description": ""},
            {"name": "Theme B", "tickers": ["TER", "ONTO", "KLAC", "BAR"],
             "score": 85.0, "stage": "Accelerating", "theme_date": None, "description": ""},
            {"name": "Theme C", "tickers": ["KLAC", "AMAT", "AMD"],
             "score": 80.0, "stage": "Accelerating", "theme_date": None, "description": ""},
        ], {"Theme A", "Theme B", "Theme C"}),
    ]

    print("\n\n###### CAP-STRIP HYPOTHESIS (full merge -> cap pipeline) ######")
    for label, themes, protected in cap_scenarios:
        merged = await _merge_overlapping_themes(themes, stocks_by_ticker, protected_names=protected)
        merged.sort(key=lambda t: t["score"], reverse=True)
        capped = await _enforce_max_themes_per_stock(merged)
        # Check for duplicate ticker sets in capped output
        groups: dict = {}
        for t in capped:
            tk = frozenset(t.get("tickers") or [])
            if not tk:
                continue
            groups.setdefault(tk, []).append(t["name"])
        dups = [(sorted(tk), names) for tk, names in groups.items() if len(names) > 1]
        print(f"\n=== {label} ===")
        print(f"  in    : {[(t['name'], sorted(t['tickers'])) for t in themes]}")
        print(f"  merged: {[(t['name'], sorted(t['tickers'])) for t in merged]}")
        print(f"  capped: {[(t['name'], sorted(t['tickers'])) for t in capped]}")
        if dups:
            print(f"  DUPS  : {dups}  <-- BUG REPRODUCED")
        else:
            print(f"  DUPS  : none")


if __name__ == "__main__":
    asyncio.run(main())
