"""#486 (2026-09-09) — the discovery prompt's CORRELATION CLUSTERS block gets parity with the
other pools: members carry RS / sector / description, members already in a theme are tagged,
clusters are ordered strongest-first, and the rendering is bounded (top _CLUSTER_DESCRIBED_CAP
members described, the rest on a '+K more' tail) with the batch partition counting the
described lines so the 22-stock-per-call bound stays honest. The three rule sentences are
pinned VERBATIM — the rendering is context; the disposition is the criterion and did not move.
"""
from agents.market_intelligence import theme_engine as te
from agents.market_intelligence.universe import TICKER_DESC


def _cluster(h, tickers, rs, member_rs=None, corr=0.86):
    return {"cluster_hash": h, "tickers": list(tickers), "member_count": len(tickers),
            "mean_corr": corr, "avg_rs": rs, "member_rs": member_rs or {}}


RULES = [
    "If a cluster maps to a clear business thesis, propose it as a Nascent theme.",
    "If the correlation reason is unclear, do NOT force a theme — leave the stocks uncovered.",
    "IMPORTANT: If a cluster forms a valid theme, invent a specific descriptive business name",
]


def test_clusters_render_strongest_first_with_rs_sector_description_and_theme_tags(monkeypatch):
    monkeypatch.setitem(TICKER_DESC, "FRO", "Crude oil tanker owner/operator")
    monkeypatch.setitem(TICKER_DESC, "AEM", "Gold miner")
    weak = _cluster("h_weak", ["AAL", "DAL"], rs=18.0, member_rs={"AAL": 20.0, "DAL": 16.0})
    # the tanker shape that DID get named out of a dying parent: 2 of 3 sit in a Fading blob
    strong = _cluster("h_strong", ["FRO", "INSW", "ZZLPG"], rs=92.0,
                      member_rs={"FRO": 95.0, "INSW": 91.0})   # ZZLPG: no member RS → pool fallback
    covered = _cluster("h_cov", ["AEM", "NEM"], rs=89.0, member_rs={"AEM": 90.0, "NEM": 88.0})
    existing = [
        {"name": "Gold & Precious Metals Miners Rotation", "stage": "Mainstream", "tickers": ["AEM", "NEM"]},
        {"name": "Global Oil & Gas Value Chain", "stage": "Fading", "tickers": ["FRO", "INSW", "XOM"]},
    ]
    pools = {"ZZLPG": {"ticker": "ZZLPG", "rs_composite": 90.0, "sector": "Energy"}}

    block = te._render_cluster_block([weak, strong, covered], existing, pools)

    # strongest first: the tankers are Cluster A, the airlines last
    a = block.index("Cluster A"); b = block.index("Cluster B"); c = block.index("Cluster C")
    assert block.index("FRO") > a and block.index("FRO") < b
    assert block.index("AAL") > c
    # per-member RS + description, pool fallback for sector/RS, [in:] tag, header count
    assert "· FRO (RS 95 — Crude oil tanker owner/operator) [in: Global Oil & Gas Value Chain (Fading)]" in block
    assert "· ZZLPG (RS 90, sector: Energy)" in block
    assert "· AEM (RS 90 — Gold miner) [in: Gold & Precious Metals Miners Rotation]" in block
    assert "2 of 2 already in a theme)" in block                      # miners: no Fading parent
    assert "2 of 3 already in a theme (2 of those in a Fading one)" in block   # tankers
    for sentence in RULES:
        assert sentence in block, "a rule sentence changed — that is a criterion, not rendering"


def test_large_cluster_rendering_is_bounded_by_the_described_cap():
    members = [f"T{i:02d}" for i in range(33)]
    rs = {tk: 100 - i for i, tk in enumerate(members)}
    block = te._render_cluster_block([_cluster("h33", members, 89.0, member_rs=rs)], [], {})
    described = [l for l in block.splitlines() if l.strip().startswith("· T")]
    assert len(described) == te._CLUSTER_DESCRIBED_CAP
    assert "· +21 more:" in block
    # the described ones are the TOP by RS, the tail holds the rest — nothing lost
    assert "· T00 (RS 100)" in block and "T32" in block
    for tk in members:
        assert tk in block


def test_partition_counts_described_cluster_members_toward_the_batch_bound():
    """A 33-member cluster whose members sit outside every pool used to weigh 33 as
    an atom; it now weighs the described cap, and pool stocks packed beside it must
    keep (pool + described) ≤ the batch cap."""
    unc = [{"ticker": f"U{i:02d}", "rs_composite": 90, "sector": "SectorA"} for i in range(30)]
    big = _cluster("h33", [f"C{i:02d}" for i in range(33)], 89.0)
    cap = te._DISCOVERY_LLM_BATCH_STOCKS
    batches = te._partition_discovery_pools(
        {"uncovered": unc, "velocity": [], "turner": [], "elite": []}, [big], batch_cap=cap)
    for b in batches:
        pool_n = sum(len(b[k]) for k in ("uncovered", "velocity", "turner", "elite"))
        described = sum(min(len(c["tickers"]), te._CLUSTER_DESCRIBED_CAP) for c in b["clusters"])
        assert pool_n + described <= cap, f"batch renders {pool_n + described} > {cap}"
    assert sum(1 for b in batches if big in b["clusters"]) == 1
    assert sorted(s["ticker"] for b in batches for s in b["uncovered"]) == \
        sorted(s["ticker"] for s in unc)


def test_cluster_block_falls_back_gracefully_without_member_rs_or_descriptions():
    """A cluster read back from the DB has no member_rs; an undescribed ticker has no
    TICKER_DESC entry. The block must still render every member (bare, as before)."""
    c = {"cluster_hash": "h", "tickers": ["ZZZ1", "ZZZ2"], "member_count": 2,
         "mean_corr": 0.9, "avg_rs": 50.0}
    block = te._render_cluster_block([c], [], {})
    assert "· ZZZ1 (RS ?)" in block and "· ZZZ2 (RS ?)" in block
