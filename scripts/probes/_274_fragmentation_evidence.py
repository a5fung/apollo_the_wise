#!/usr/bin/env python3
"""#274 theme-fragmentation EVIDENCE PACK (read-only) — feeds the weekend Fable design.

Quantifies, on TODAY's active theme cohort (`scripts/eval_data/274_themes_2026-07-08.json`,
pulled from prod 7/8), what each scoped lever would MERGE or DISSOLVE + a legit-kill surface
so Fable can weigh noise-vs-recall. NOT a fix — evidence only; the levers are detection-criterion
changes → SSoT + CHANGE_PROCESS + operator sign-off (ADR 0007 §3 anti-noise caveat holds).

Levers (from #274 / the 7/8 root-cause):
  L1  dissolve-on-flagged-pair   — dissolve a 2-member theme when validation churns a member
  L2a shared-ticker merge        — lower MIN_SHARED_FOR_MERGE (today =3): which pairs merge at ≥2/≥1
  L2b sector/narrative merge arm — merge by sector-family even with <3 shared tickers (the near-dups)
  L3  birth min-member floor     — block/dissolve themes below N members

Run: python scripts/probes/_274_fragmentation_evidence.py   (reads the cached JSON, writes the doc)
"""
import json
import itertools
from pathlib import Path
from collections import defaultdict

REPO = Path(__file__).resolve().parent.parent.parent
EVAL = REPO / "scripts" / "eval_data"
DOC = REPO / "docs" / "analysis" / "theme_fragmentation_evidence_274_2026-07-08.md"

themes = json.load((EVAL / "274_themes_2026-07-08.json").open())
cooldowns = json.load((EVAL / "274_cooldowns_2026-07-08.json").open()) or []
for t in themes:
    t["tset"] = set(t.get("tickers") or [])

# name-keyword sector families (illustrative grouping for the L2b merge-arm scope)
FAMILIES = {
    "Insurance": ["insurance", "underwrit", "reinsur", "catastrophe"],
    "REIT / Real Estate": ["reit", "real estate"],
    "Fintech / Payments / Brokerage": ["fintech", "payment", "brokerage", "wealth",
                                       "digital financial", "credit platform", "payment rails"],
    "Biotech / Therapy": ["biotech", "therap", "oncolog", "gene ", "genomic", "biopharma",
                          "orphan", "biopsy", "protein degrad", "cell therapy", "disease"],
    "AI silicon / Datacenter / Quantum": ["silicon", "chip", "gpu", "semiconductor",
                                          "datacenter", "colocation", "quantum"],
    "Crypto": ["crypto", "bitcoin"],
    "Energy / Oil": ["petroleum", "oilfield", "refining", "downstream"],
    "Cloud / Security / Adtech": ["cloud", "observability", "aiops", "zero-trust",
                                  "network security", "advertising", "adtech"],
}


def family_of(name: str) -> str | None:
    lo = name.lower()
    for fam, kws in FAMILIES.items():
        if any(k in lo for k in kws):
            return fam
    return None


def fmt_list(names, cap=None):
    xs = names[:cap] if cap else names
    tail = f" (+{len(names)-cap} more)" if cap and len(names) > cap else ""
    return ", ".join(xs) + tail


N = len(themes)
by_n = defaultdict(list)
for t in themes:
    by_n[t["n"]].append(t)

# ── L3 — birth min-member floor ──
sub3 = [t for t in themes if t["n"] < 3]
sub4 = [t for t in themes if t["n"] < 4]
two_member = [t for t in themes if t["n"] == 2]

# ── L2a — shared-ticker overlap between theme pairs ──
pairs_ge2, pairs_ge1 = [], []
for a, b in itertools.combinations(themes, 2):
    shared = a["tset"] & b["tset"]
    if len(shared) >= 2:
        pairs_ge2.append((a["name"], b["name"], sorted(shared)))
    elif len(shared) == 1:
        pairs_ge1.append((a["name"], b["name"], sorted(shared)))

# ── L2b — sector-family grouping (the near-dup clusters the shared-ticker merge misses) ──
fam_groups = defaultdict(list)
for t in themes:
    fam = family_of(t["name"])
    if fam:
        fam_groups[fam].append(t)
multi_fam = {f: ts for f, ts in fam_groups.items() if len(ts) >= 2}
# cross-family ticker overlap: are the same-family themes ticker-DISJOINT? (why shared-merge misses them)
fam_disjoint = {}
for f, ts in multi_fam.items():
    max_shared = 0
    for a, b in itertools.combinations(ts, 2):
        max_shared = max(max_shared, len(a["tset"] & b["tset"]))
    fam_disjoint[f] = max_shared
themes_in_multifam = sum(len(ts) for ts in multi_fam.values())
collapse_to = len(multi_fam)

# ── L1 — dissolve-on-flagged-pair ──
cd_by_theme = defaultdict(list)
for c in cooldowns:
    cd_by_theme[c.get("theme_name")].append(c)
two_member_flagged = [t for t in two_member if cd_by_theme.get(t["name"])]

# ── write doc ──
L = []
L.append("# #274 theme-fragmentation — EVIDENCE PACK (feeds the weekend Fable design)\n")
L.append("**2026-07-08 · read-only · cohort = today's active themes "
         f"(`274_themes_2026-07-08.json`, {N} non-Retired) + cooldowns/21d "
         f"(`274_cooldowns_2026-07-08.json`, {len(cooldowns)}).**  \n")
L.append("Data-backing: the 7/8 L2 anomaly (theme_count_active 78 vs 40 median). This pack "
         "quantifies each scoped lever's effect + a legit-kill surface — it is EVIDENCE for the "
         "Fable design, NOT a fix. Every lever = detection-criterion → SSoT + CHANGE_PROCESS + "
         "operator sign-off + N≥10 backtest; ADR 0007 §3 anti-noise caveat (don't reintroduce the "
         "nascent-miss) governs all of it.\n")

L.append("\n## The shape of the problem\n")
dist = " · ".join(f"{n}m: {len(by_n[n])}" for n in sorted(by_n))
L.append(f"- Member-count distribution: {dist}\n")
L.append(f"- **{len(two_member)} of {N} active themes are 2-member ({len(two_member)/N*100:.0f}%)** — the fragmentation core.\n")
L.append(f"- {len(sub3)} themes have <3 members; {len(sub4)} have <4.\n")

L.append("\n## L1 — dissolve-on-flagged-pair (#274's original fix)\n")
L.append(f"2-member themes that have had a member churned by validation (cooldown history) — "
         f"the immortality-risk set the fix targets: **{len(two_member_flagged)}** of {len(two_member)}.\n")
if two_member_flagged:
    L.append("| theme | members | flagged member(s) |")
    L.append("|---|--:|---|")
    for t in two_member_flagged:
        flg = ", ".join(sorted({c["ticker"] for c in cd_by_theme[t["name"]]}))
        L.append(f"| {t['name']} | {t['n']} | {flg} |")
L.append(f"\n> Leverage: NARROW — only {len(two_member_flagged)} themes. Dissolve-on-flag catches "
         "the *unstable* 2-member themes, not the *stable-but-thin* bulk. Necessary, not sufficient.")

L.append("\n## L2a — lower the shared-ticker merge threshold (today MIN_SHARED_FOR_MERGE=3)\n")
L.append(f"Theme pairs sharing ≥2 tickers (would merge if threshold dropped 3→2): **{len(pairs_ge2)}**. "
         f"Pairs sharing exactly 1: {len(pairs_ge1)}.\n")
if pairs_ge2:
    L.append("| theme A | theme B | shared |")
    L.append("|---|---|---|")
    for a, b, sh in pairs_ge2[:12]:
        L.append(f"| {a} | {b} | {fmt_list(sh)} |")
L.append(f"\n> Leverage: {'MODEST' if pairs_ge2 else 'LOW'} — the visible near-dups (insurance/REIT) are "
         "ticker-DISJOINT (distinct names), so a lower shared-ticker threshold does NOT merge them. "
         "That's why L2b (sector arm) exists.")

L.append("\n## L2b — sector/narrative merge arm (merge on family even with <3 shared tickers)\n")
L.append(f"Sector-families with ≥2 active themes: **{len(multi_fam)}** families holding "
         f"**{themes_in_multifam}** themes → would collapse toward ~{collapse_to} (one per family, "
         f"modulo genuine sub-industry distinctions). Net reduction on the order of "
         f"**{themes_in_multifam - collapse_to}** themes.\n")
L.append("| family | # themes | max shared tickers (why shared-merge misses them) | themes |")
L.append("|---|--:|--:|---|")
for f, ts in sorted(multi_fam.items(), key=lambda kv: -len(kv[1])):
    L.append(f"| {f} | {len(ts)} | {fam_disjoint[f]} | {fmt_list([t['name'] for t in ts], 4)} |")
L.append("\n> Leverage: **HIGHEST** — this is the mechanism for the operator-visible dups. LEGIT-KILL "
         "RISK: some same-family themes are genuinely distinct sub-industries (P&C vs specialty-catastrophe "
         "insurance; office vs multifamily REIT) — the design must merge on THESIS coherence, not just the "
         "family keyword, or it collapses real distinctions. This is the core Fable judgment call.")

L.append("\n## L3 — birth min-member floor\n")
L.append(f"- Floor = 3 → dissolves/blocks **{len(sub3)}** themes ({len(sub3)/N*100:.0f}% of the cohort).\n")
L.append(f"- Floor = 4 → **{len(sub4)}** themes ({len(sub4)/N*100:.0f}%).\n")
L.append("LEGIT-KILL surface — the sub-3-member themes (Fable/operator eyeball which are real vs noise; "
         "ADR 0007's 26-theme corpus was ~27% noise → most may be legit small themes):\n")
for t in sorted(sub3, key=lambda x: (x["n"], x["name"])):
    L.append(f"  - ({t['n']}m, {t['stage']}) {t['name']}")
L.append("\n> Leverage: BROAD but BLUNT — a flat floor is exactly what was deliberately rejected "
         "(theme_engine.py:1879, 'description-guard not 2-member cap') because it kills legit small "
         "themes. If revisited, gate it on the ADR 0007 §3 anti-noise metric (validated-themes/day) + "
         "a nascent-recall check, not a bare count.")

L.append("\n## Read for the Fable design\n")
L.append("- **Highest leverage = L2b** (sector/narrative merge arm) — it targets the operator-visible "
         "near-dup clusters that the shared-ticker merge structurally misses (they're ticker-disjoint). "
         "The hard part is THESIS-coherence merging without collapsing real sub-industry distinctions.\n")
L.append("- **L1 (dissolve-on-flag)** is a cheap, safe complement — narrow but pure-signal.\n")
L.append("- **L3 (min-member floor)** is the riskiest (legit-kill) and was already rejected once; only "
         "revisit gated on the anti-noise metric, not a bare count.\n")
L.append("- All three are ASYMMETRIC-safe if merges/dissolves require validation/thesis evidence — never "
         "a blind count. THE LINE: no live theme-engine change without SSoT + CHANGE_PROCESS + sign-off.\n")
L.append(f"\n_Reproduce: `python scripts/probes/_274_fragmentation_evidence.py` off the two cached JSONs._\n")

DOC.parent.mkdir(parents=True, exist_ok=True)
DOC.write_text("\n".join(L), encoding="utf-8")
print(f"[274-evidence] {N} themes · {len(two_member)} two-member · L1={len(two_member_flagged)} "
      f"L2a(≥2)={len(pairs_ge2)} L2b={themes_in_multifam}→{collapse_to} L3(<3)={len(sub3)}")
print(f"[274-evidence] wrote {DOC.relative_to(REPO)}")
