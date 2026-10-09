"""#693 replay — STEP 1 ($0, read-only): rebuild Monday 10-05's theme_validation requests.

Why rebuild: logs/llm_samples keeps only the LAST 3 requests per call site (10-06/07/08 by now),
so no 10-05 request survives. The validator prompt is deterministic from (theme name, the
tickers it was handed, the theme's thesis, TICKER_DESC), so it is rebuilt from:
  * rescore arm: get_active_themes() as the 10-05 run saw it (latest non-retired row per name,
    theme_date 09-28..10-04), minus the exclusion + prune lines in the 10-05 log;
  * post-assignment arm: the 10-05 snapshot of each theme that received an assignment, plus the
    names validation removed from it (best effort — later steps may have touched the snapshot);
  * birth arm: each 10-05 newborn's snapshot tickers plus the names stripped at birth;
  * Arm-B post-merge arm: winner tickers + absorbed tickers from the loaded state (best effort).
Template fidelity is proven first by rebuilding the 3 captured samples byte-for-byte.
Writes /tmp/693_recon.json. No model calls, no DB writes.
"""
import asyncio, json, re, glob
from datetime import date

from agents.market_intelligence.db import get_pool, get_ticker_overrides
from agents.market_intelligence import universe
from agents.market_intelligence.theme_engine import _is_garbage, PRUNE_MIN_TICKERS, NEW_THEME_MIN_STOCKS, THEME_MODEL

SYSTEM = "You are a JSON API. Respond with valid JSON only. No prose, no markdown, no explanation."
LOG = "/tmp/693_log_1005.txt"
SAMPLE = "/app/logs/llm_samples/agents.market_intelligence.theme_engine___validate_theme_membership.json"


def build_prompt(theme_name, tickers, thesis, desc):
    """Verbatim copy of the prompt construction in theme_engine._validate_theme_membership."""
    parts = []
    for tk in tickers:
        d = desc.get(tk)
        parts.append(f"- {tk}: {d}" if d else f"- {tk}: (use your knowledge of this ticker)")
    stock_lines = "\n".join(parts)
    _thesis = (thesis or "").strip()
    thesis_block = ""
    thesis_instruction = ""
    if _thesis and not _is_garbage(_thesis):
        thesis_block = f"Theme thesis: {_thesis[:300]}\n\n"
        thesis_instruction = (
            "Judge against the THESIS above, not the theme name alone: a stock whose "
            "CURRENT driver matches the thesis BELONGS even when its legacy industry "
            "label differs (e.g. a company repurposing its existing infrastructure "
            "for the theme's driver, as described by the thesis).\n"
        )
    return (
        f"Theme: \"{theme_name}\"\n\n"
        + thesis_block +
        f"Stocks in this theme:\n{stock_lines}\n\n"
        f"Identify stocks that DO NOT BELONG in this theme.\n"
        f"A stock does not belong if its core business is in a DIFFERENT INDUSTRY than the theme — "
        f"e.g. a car rental company in a data center theme, a mining company in a biotech theme, "
        f"a retailer in a semiconductor theme. Be DECISIVE: wrong industry = remove. "
        f"Do not keep a stock just because you are unsure — if the business sector clearly differs "
        f"from the theme, flag it.\n"
        + thesis_instruction +
        f"\nReturn JSON only: {{\"remove\": [\"TICKER1\", \"TICKER2\"]}} or {{\"remove\": []}} if all belong."
    )


def parse_prompt(p):
    name = re.match(r'Theme: "(.*?)"\n', p).group(1)
    m = re.search(r"Theme thesis: (.*?)\n\nStocks in this theme", p, re.S)
    thesis = m.group(1) if m else None
    block = p.split("Stocks in this theme:\n", 1)[1].split("\n\nIdentify", 1)[0]
    tks = [ln[2:].split(":", 1)[0] for ln in block.split("\n")]
    return name, thesis, tks


async def main():
    out = {"self_check": [], "calls": [], "notes": []}
    desc = dict(universe.TICKER_DESC)
    desc.update(await get_ticker_overrides())
    pool = await get_pool()
    async with pool.acquire() as c:
        changed = {r["ticker"]: str(r["updated_at"]) for r in await c.fetch(
            "SELECT ticker, updated_at FROM mi_ticker_overrides WHERE updated_at > '2026-10-05 21:02:14+00' "
            "AND description IS NOT NULL AND description != ''")}

        # ── template self-check on the 3 captured samples ──
        for s in json.load(open(SAMPLE))["samples"]:
            p = s["request"]["messages"][0]["content"]
            name, thesis, tks = parse_prompt(p)
            rebuilt = build_prompt(name, tks, thesis, desc)
            # a thesis longer than 300 chars was cut; the parsed one is already cut, so equal input
            diff_lines = [a for a, b in zip(p.split("\n"), rebuilt.split("\n")) if a != b]
            out["self_check"].append({"captured_at": s["captured_at"], "theme": name, "n": len(tks),
                                      "byte_equal": rebuilt == p,
                                      "system_equal": s["request"].get("system") == SYSTEM,
                                      "diff_lines": diff_lines[:5]})

        # ── loaded state as the 10-05 run saw it ──
        loaded = [dict(r) for r in await c.fetch("""
            SELECT * FROM (SELECT DISTINCT ON (name) * FROM mi_themes
                           WHERE theme_date >= '2026-09-28' AND theme_date < '2026-10-05'
                           ORDER BY name, theme_date DESC) l WHERE stage != 'Retired' ORDER BY name""")]
        out["notes"].append(f"loaded themes (live theme_load_state said n=133): {len(loaded)}")
        cf_stripped = {}
        for r in await c.fetch("""SELECT detail FROM mi_audit_log WHERE event_type='theme_carryforward_filter_stripped'
                AND (created_at AT TIME ZONE 'America/New_York')::date='2026-10-05'"""):
            nm = re.search(r"theme=(.*)", r["detail"]).group(1).strip()
            cf_stripped[nm] = re.findall(r"'(\S+?)'", r["detail"].split("\n", 2)[-1])
        births = []
        for r in await c.fetch("""SELECT summary, detail FROM mi_audit_log WHERE event_type='theme_discovered'
                AND created_at AT TIME ZONE 'America/New_York' BETWEEN '2026-10-05 17:08' AND '2026-10-05 17:09' ORDER BY created_at"""):
            d = r["detail"]
            tks = [x.strip() for x in re.search(r"Tickers: (.*)", d).group(1).split(",")]
            births.append([re.match(r"New theme: (.*) \(\d+ stocks\)", r["summary"]).group(1), tks, re.search(r"Thesis: (.*)", d, re.S).group(1).strip()])
        snap = {r["name"]: dict(r) for r in await c.fetch(
            "SELECT DISTINCT ON (name) * FROM mi_themes WHERE theme_date='2026-10-05' ORDER BY name, created_at DESC")}
        loaded_by = {t["name"]: t for t in loaded}

        audit_removed, audit_removed_t = {}, {}
        for r in await c.fetch("""SELECT summary, (created_at AT TIME ZONE 'America/New_York')::time::text t FROM mi_audit_log WHERE event_type='ticker_revalidated_out'
                AND (created_at AT TIME ZONE 'America/New_York')::date='2026-10-05' ORDER BY created_at"""):
            m = re.match(r"(\S+) removed from '(.*)' by validation", r["summary"])
            audit_removed.setdefault(m.group(2), []).append(m.group(1))
            audit_removed_t.setdefault(m.group(2), []).append((m.group(1), r["t"]))

    log = open(LOG).read().splitlines()
    pruned, excluded = {}, {}
    for ln in log:
        m = re.search(r"Theme '(.*)': pruned (\S+) — ", ln)
        if m:
            pruned.setdefault(m.group(1), set()).add(m.group(2))
        m = re.search(r"Theme '(.*)': stripping persistently excluded tickers: \[(.*)\]", ln)
        if m:
            excluded.setdefault(m.group(1), set()).update(x.strip(" '") for x in m.group(2).split(","))

    def add(arm, name, tks, thesis, quality):
        out["calls"].append({"arm": arm, "theme": name, "tickers": tks, "thesis": thesis,
                             "quality": quality,
                             "live_removed": [], "desc_changed_since": [t for t in tks if t in changed],
                             "prompt": build_prompt(name, tks, thesis, desc)})

    # ── rescore arm ──
    for t in loaded:
        tks = [x for x in (t["tickers"] or []) if x not in excluded.get(t["name"], set())]
        tks = [x for x in tks if x not in pruned.get(t["name"], set())]
        if len(tks) >= 2:
            add("rescore", t["name"], tks, t.get("description"), "rebuilt")

    # ── later arms, in live order (17:05 rehome x2, 17:07 post-assignment x7, 17:08:29 join x1,
    #    17:08:30-36 birth x5, 17:08:51-17:09:04 Arm-B post-merge x3) ──
    rescore_out = {}
    for c0 in out["calls"]:
        rem = [x for x in audit_removed_t.get(c0["theme"], []) if x[1] < "17:05"]
        rescore_out[c0["theme"]] = [x for x in c0["tickers"] if x not in {r[0] for r in rem}]
    for ln in log:
        m = re.search(r"Carryforward filter: '(.*)' keeps", ln)
    for name, tks in cf_stripped.items():
        if name in rescore_out:
            rescore_out[name] = [x for x in rescore_out[name] if x not in tks]
    merge_in = {}
    for ln in log:
        if "[theme merge input]" in ln:
            for t in json.loads(ln.split("[theme merge input] ", 1)[1]):
                merge_in[t["name"]] = t["tickers"]
    # rehome: MSTR, GIB, G (log order)
    rehome = {}
    for ln in log:
        m = re.search(r"21:05:3\d .*Assigned (\S+) → '(.*?)': ", ln)
        if m:
            rehome.setdefault(m.group(2), []).append(m.group(1))
    for name, adds in rehome.items():
        base = list(rescore_out.get(name) or [])
        add("rehome", name, base + [a for a in adds if a not in base],
            (loaded_by.get(name) or {}).get("description"), "rebuilt: rescore output + re-homed members")
        rescore_out[name] = base + [a for a in adds if a not in base]
    # post-assignment: themes with an 'Assigned' line in the 21:07:45 block
    assigned = {}
    for ln in log:
        m = re.search(r"21:07:4\d .*Assigned (\S+) → '(.*?)': ", ln)
        if m:
            assigned.setdefault(m.group(2), []).append(m.group(1))
    post_out = {}
    for name, adds in assigned.items():
        base = list(rescore_out.get(name) or [])
        tks = base + [a for a in adds if a not in base]
        add("post_assignment", name, tks, (loaded_by.get(name) or {}).get("description"),
            "rebuilt: rescore output + tonight's assignments (carry-forward strips applied)")
        post_out[name] = tks
    # join-carry: INTR into Fintech; the theme as of then = post-assignment output minus its removals + INTR
    fin = "Fintech & Digital Finance Sector Re-rating on Fed Easing"
    fin_tks = [x for x in post_out.get(fin, []) if x not in ("SSNC",)] + ["INTR"]
    add("join_carry", fin, fin_tks, (loaded_by.get(fin) or {}).get("description"),
        "rebuilt: post-assignment output + INTR")
    stripped = {}
    for ln in log:
        m = re.search(r"\[birth validation #266\] '(.*)' stripped at birth: \[(.*)\]", ln)
        if m:
            stripped[m.group(1)] = [x.strip(" '") for x in m.group(2).split(",")]
    # births: founding members = kept (order as logged) + stripped appended (position unknown)
    for name, tks, thesis in births:
        tks = tks + [x for x in stripped.get(name, []) if x not in tks]
        add("birth", name, tks, thesis, "approx: founding order unknown for the stripped name")
    # Arm-B post-merge (3): union = winner + absorbed from the 17:08:36 merge-input state; the
    # winner's name/thesis at that moment is uncertain (thesis merges renamed it) — best effort.
    pm = "Precious Metals Rebound on Easier Fed Outlook"
    u1 = merge_in[pm] + [x for x in merge_in["Precious Metals Royalty & Streaming Companies"] if x not in merge_in[pm]]
    u2 = u1 + [x for x in merge_in["Mid-Tier Gold Producers & Developers Breakout"] if x not in u1]
    u3 = u2 + [x for x in merge_in["Precious Metals Miners Velocity Breakout"] if x not in u2]
    pm_thesis = (loaded_by.get(pm) or {}).get("description")
    add("merge", "Precious Metals Miners, Royalties & Streamers—Fed Easing Tailwind", u1, pm_thesis, "approx")
    add("merge", "Precious Metals Miners & Producers—Gold Rally & Fed Easing", u2, pm_thesis, "approx")
    add("merge", "Precious Metals Miners—Gold Rally & Fed Easing", u3, pm_thesis, "approx")

    windows = {"rescore": ("17:02", "17:05"), "rehome": ("17:05", "17:06"), "post_assignment": ("17:07", "17:08"),
               "join_carry": ("17:08:29", "17:08:30"), "birth": ("17:08:30", "17:08:40"), "merge": ("17:08:40", "17:10")}
    for call in out["calls"]:
        lo, hi = windows[call["arm"]]
        call["live_removed"] = [x for x, t in audit_removed_t.get(call["theme"], []) if lo <= t < hi and x in call["tickers"]]
    out["audit_removed"] = audit_removed
    out["counts"] = {a: sum(1 for x in out["calls"] if x["arm"] == a) for a in windows}
    json.dump(out, open("/tmp/693_recon.json", "w"), indent=1, default=str)
    print(json.dumps({"self_check": out["self_check"], "notes": out["notes"], "counts": out["counts"],
                      "desc_changed_total": len(changed),
                      "calls_with_changed_desc": sum(1 for x in out["calls"] if x["desc_changed_since"]),
                      "live_removed_matched": sum(len(x["live_removed"]) for x in out["calls"]),
                      "per_arm_live_removed": {a: sum(len(x["live_removed"]) for x in out["calls"] if x["arm"] == a) for a in windows}}, indent=1, default=str))

asyncio.run(main())
