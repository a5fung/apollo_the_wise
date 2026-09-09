"""#486 (2026-09-09) — two cluster artifacts are killed at the SOURCE, in the correlation engine.

On 2026-09-08, the first night the shown/declined recorder ran, 2 of the 12 clusters handed to
discovery were not groups at all: GOOG/GOOGL/GOOGM/GOOGN (four share classes of one issuer, corr
0.99 — stored on 25 consecutive nights and named as a live theme once, 08-03 → 08-12) and
BWMN/HZO/NESR/SLN/VREX (takeover targets that all jumped on 08-10 and then traded flat, so one
shared day dominated the 20-day window). These tests freeze that neither can reach the prompt
again, AND the false-positive sides the fix must not cross: a root-only match (two different
companies whose tickers happen to nest) never collapses, and two distinct issuers that genuinely
move together (NSA/PSA at 0.99 on real closes) are never collapsed either.
"""
import numpy as np
import pytest

from agents.market_intelligence import correlation_engine as ce


def _series(rng, n=20, scale=0.02):
    return rng.normal(0.0, scale, n)


def _closes_from_returns(returns, start=100.0):
    out = [start]
    for r in returns:
        out.append(out[-1] * (1.0 + float(r)))
    return out


# ── pure shape test: which pairs are even CANDIDATES ─────────────────────────

def test_sibling_candidates_by_ticker_shape():
    tickers = ["GOOG", "GOOGL", "GOOGM", "GOOGN", "BRK.A", "BRK.B", "UA", "UAA",
               "BELFA", "BELFB", "NSA", "PSA", "ALM", "PAM", "ALMS"]
    pairs = {(tickers[i], tickers[j]) for i, j in ce._issuer_sibling_pairs(tickers)}
    # share-class shapes are candidates
    for a, b in [("GOOG", "GOOGL"), ("GOOG", "GOOGM"), ("GOOGM", "GOOGN"), ("BRK.A", "BRK.B"),
                 ("UA", "UAA"), ("BELFA", "BELFB"), ("ALM", "ALMS")]:
        assert (a, b) in pairs or (b, a) in pairs, f"{a}/{b} should be a candidate"
    # unrelated roots never are
    for a, b in [("NSA", "PSA"), ("ALM", "PAM"), ("GOOG", "BRK.A")]:
        assert (a, b) not in pairs and (b, a) not in pairs, f"{a}/{b} must not be a candidate"


# ── the collapse itself ───────────────────────────────────────────────────────

def test_share_classes_collapse_to_one_representative():
    rng = np.random.RandomState(486)
    base = _series(rng)
    r = np.vstack([
        base + rng.normal(0, 0.0005, 20),   # GOOG
        base + rng.normal(0, 0.0005, 20),   # GOOGL
        base + rng.normal(0, 0.0005, 20),   # GOOGM
        base + rng.normal(0, 0.0005, 20),   # GOOGN
        _series(rng),                       # AAA — unrelated
    ])
    tickers = ["GOOG", "GOOGL", "GOOGM", "GOOGN", "AAA"]
    r2, t2, collapsed = ce._collapse_share_classes(r, tickers)
    assert t2 == ["GOOG", "AAA"]
    assert collapsed == {"GOOG": ["GOOGL", "GOOGM", "GOOGN"]}
    assert r2.shape == (2, 20)
    np.testing.assert_array_equal(r2[0], r[0])


def test_root_match_without_return_identity_is_NOT_collapsed():
    """ALM / ALMS are two different companies whose tickers nest — shape says
    candidate, returns say no (corr ≈ 0), so both must survive."""
    rng = np.random.RandomState(7)
    r = np.vstack([_series(rng), _series(rng), _series(rng)])
    r2, t2, collapsed = ce._collapse_share_classes(r, ["ALM", "ALMS", "PAM"])
    assert t2 == ["ALM", "ALMS", "PAM"]
    assert collapsed == {}


def test_tight_distinct_issuers_are_NOT_collapsed():
    """NSA / PSA (two self-storage REITs) hit raw corr 0.99 on real closes in 14 of
    24 windows. They are a real group, not one instrument — different roots, so no
    candidate, so no collapse, however identical the returns."""
    rng = np.random.RandomState(11)
    base = _series(rng)
    r = np.vstack([base + rng.normal(0, 1e-4, 20), base + rng.normal(0, 1e-4, 20)])
    r2, t2, collapsed = ce._collapse_share_classes(r, ["NSA", "PSA"])
    assert t2 == ["NSA", "PSA"] and collapsed == {}


# ── cash-like (takeover-target) series ───────────────────────────────────────

def test_cash_like_series_is_dropped_and_a_normal_name_is_kept():
    rng = np.random.RandomState(3)
    spike_then_flat = np.concatenate([[0.50], rng.normal(0, 0.001, 19)])   # BWMN shape
    normal = _series(rng, scale=0.02)
    gap_but_alive = np.concatenate([[0.35], rng.normal(0, 0.025, 19)])     # a real EP name
    r = np.vstack([spike_then_flat, normal, gap_but_alive])
    r2, t2, dropped = ce._drop_cash_like_series(r, ["BWMN", "NORM", "GAPR"])
    assert dropped == ["BWMN"]
    assert t2 == ["NORM", "GAPR"]
    assert r2.shape == (2, 20)


# ── end-to-end through the sync pipeline (what the nightly actually runs) ────

def _pipeline(closes: dict) -> list[dict]:
    tickers = [t for t in closes if t != "SPY"]
    return ce._compute_tight_clusters_sync(closes, tickers)


def test_share_class_family_never_forms_a_cluster():
    """Would FAIL if the GOOG×4 artifact came back: four share classes plus three
    unrelated names must yield NO cluster."""
    rng = np.random.RandomState(2026)
    spy = _series(rng, scale=0.01)
    goog = 0.9 * spy + _series(rng, scale=0.012)
    closes = {"SPY": _closes_from_returns(spy)}
    for tk in ("GOOG", "GOOGL", "GOOGM", "GOOGN"):
        closes[tk] = _closes_from_returns(goog + rng.normal(0, 0.0005, 20))
    for tk in ("AAA", "BBB", "CCC"):
        closes[tk] = _closes_from_returns(0.8 * spy + _series(rng, scale=0.02))
    clusters = _pipeline(closes)
    assert clusters == [], f"share-class artifact reached the cluster list: {clusters}"


def test_real_cluster_survives_with_one_share_class_representative():
    """GOOG + GOOGL inside a genuine 5-name co-moving group → a 4-member cluster
    carrying exactly ONE Alphabet ticker (the shorter one)."""
    rng = np.random.RandomState(99)
    spy = _series(rng, scale=0.01)
    factor = _series(rng, scale=0.03)
    closes = {"SPY": _closes_from_returns(spy)}
    goog = 0.9 * spy + factor + rng.normal(0, 0.002, 20)
    closes["GOOG"] = _closes_from_returns(goog)
    closes["GOOGL"] = _closes_from_returns(goog + rng.normal(0, 0.0005, 20))
    for tk in ("META", "AMZN", "MSFT"):
        closes[tk] = _closes_from_returns(0.9 * spy + factor + rng.normal(0, 0.002, 20))
    for tk in ("XOM", "CVX"):
        closes[tk] = _closes_from_returns(0.8 * spy + _series(rng, scale=0.02))
    clusters = _pipeline(closes)
    assert len(clusters) == 1
    members = clusters[0]["tickers"]
    assert "GOOG" in members and "GOOGL" not in members
    assert sorted(members) == ["AMZN", "GOOG", "META", "MSFT"]


def test_takeover_targets_never_form_a_cluster():
    """Would FAIL if the 09-08 BWMN/HZO/NESR/SLN/VREX shape came back: five unrelated
    names sharing one +40-55% day and then flat must yield NO cluster."""
    rng = np.random.RandomState(810)
    spy = _series(rng, scale=0.01)
    closes = {"SPY": _closes_from_returns(spy)}
    for tk in ("BWMN", "HZO", "VREX", "ATKR", "PEN"):
        jump = rng.uniform(0.40, 0.55)
        rets = np.concatenate([[jump], 0.05 * spy[1:] + rng.normal(0, 0.0015, 19)])
        closes[tk] = _closes_from_returns(rets)
    assert _pipeline(closes) == []


def test_member_rs_is_attached_in_memory():
    clusters = [{"tickers": ["AAA", "BBB", "CCC"], "avg_rs": 0.0}]
    out = ce._enrich_avg_rs(clusters, {"AAA": 90.0, "BBB": 80.0})
    assert out[0]["avg_rs"] == 85.0
    assert out[0]["member_rs"] == {"AAA": 90.0, "BBB": 80.0}
