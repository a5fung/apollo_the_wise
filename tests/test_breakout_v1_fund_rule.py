"""Breakout v1 universe — the single-asset fund rule (his ruling 2026-10-29: "yes, single asset makes sense").

Pinned on the 90 active Polygon type=ETV names of the 2026-10-28 reference pull
(`tests/fixtures/breakout_v1_parity/etv_names_2026-10-28.tsv`): the kept / excluded split below IS the list printed for
his check in docs/setups/consolidation_breakout.md (2026-10-29 "PHASE 1 BUILT"). A change to the rule that moves any
name fails here first.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from agents.market_intelligence import breakout_v1 as bv

FIX = Path(__file__).parent / "fixtures" / "breakout_v1_parity" / "etv_names_2026-10-28.tsv"

KEPT = {
    "BAR", "BAVA", "BHYP", "BITB", "BNO", "BSOL", "BTC", "CANE", "CLNK", "CORN", "CPER", "CTWO", "DBO", "ETH", "ETHE",
    "ETHW", "FGDL", "FSOL", "FXA", "FXB", "FXC", "FXE", "FXF", "FXY", "GBTC", "GDOG", "GLD", "GLDM", "GLNK", "GSOL",
    "GSUI", "GXRP", "IAU", "IAUM", "MSBT", "MSOL", "MSSE", "NRR", "OUNZ", "PALL", "PHYS", "PLTM", "PPLT", "PSLV", "SCOP",
    "SGOL", "SIVR", "SLV", "SOEZ", "SOYB", "UGA", "UNG", "UNL", "USL", "USO", "UUP", "WEAT", "XRP", "XRPZ", "ZCSH"}
EXCLUDED = {
    "leveraged_or_inverse": {"AGQ", "BOIL", "EUO", "GLL", "KOLD", "SCO", "UCO", "UDN", "UGL", "ULE", "YCL", "YCS", "ZSL"},
    "basket": {"BITW", "DBA", "DBB", "DBC", "DBE", "DBP", "GDLC", "GLTR", "GSG", "TAGS", "TKNZ", "USCI"},
    "several_underlyings": {"BTCK", "CEF", "SPPP"},
    "no_known_underlying": {"BDRY", "BWET"},
}
# The names the build spec named (must be kept / must be excluded).
SPEC_KEEP = {"ZCSH", "GLD", "SLV", "GBTC", "IBIT_LIKE:BITB", "USO", "UNG", "CPER", "FXE"}
SPEC_EXCLUDE = {"AGQ", "BOIL", "KOLD", "GLL", "SCO", "UCO", "UGL", "ULE", "EUO", "YCL", "YCS", "ZSL", "UDN", "DBA",
                "DBB", "DBC", "DBE", "DBP", "GLTR", "GSG", "USCI", "TAGS", "GDLC", "BITW", "TKNZ", "CEF", "SPPP", "BTCK"}


@pytest.fixture(scope="module")
def names():
    return {r["ticker"]: r["name"] for r in csv.DictReader(open(FIX), delimiter="\t")}


def test_the_split_on_the_90_names(names):
    assert len(names) == 90
    kept = {t for t, n in names.items() if bv.fund_is_single_asset(n)}
    assert kept == KEPT
    by_reason: dict = {}
    for t, n in names.items():
        fr = bv.fund_rule(n)
        if not fr["keep"]:
            by_reason.setdefault(fr["reason"], set()).add(t)
    assert by_reason == EXCLUDED
    assert len(KEPT) + sum(len(v) for v in EXCLUDED.values()) == 90


def test_the_names_the_spec_named(names):
    for t in SPEC_KEEP:
        t = t.split(":")[-1]
        assert bv.fund_is_single_asset(names[t]), (t, names[t])
    for t in SPEC_EXCLUDE:
        assert not bv.fund_is_single_asset(names[t]), (t, names[t])
    for t in ("FXA", "FXB", "FXC", "FXF", "FXY", "GSUI", "NRR"):       # the currency trusts + two coins easy to mis-read
        assert bv.fund_is_single_asset(names[t])


def test_every_ultra_fund_is_out(names):
    ultras = {t for t, n in names.items() if "ProShares Ultra" in n}
    assert len(ultras) == 12 and not any(bv.fund_is_single_asset(names[t]) for t in ultras)


def test_one_underlying_only_and_fail_closed():
    assert bv.fund_rule("Australian Dollar Trust")["underlyings"] == ["aud"]     # not AUD + USD
    assert bv.fund_rule("Some Gold and Silver Trust")["reason"] == "several_underlyings"
    assert bv.fund_rule("Brand New Mystery Asset Trust")["reason"] == "no_known_underlying"
    assert bv.fund_rule(None)["reason"] == "no_name" and bv.fund_rule("  ")["reason"] == "no_name"
    assert bv.fund_rule("Direxion Daily Gold Bull 2X Shares")["reason"] == "leveraged_or_inverse"
    assert bv.fund_rule("Some Fund 2x Bitcoin")["reason"] == "leveraged_or_inverse"
    assert bv.fund_rule("Near-term Bitcoin Trust")["underlyings"] == ["bitcoin"]   # 'near' the word is not the coin


def test_security_admitted():
    assert bv.security_admitted("AAPL", "CS") == (True, "stock")
    assert bv.security_admitted("TSM", "ADRC") == (True, "stock")
    assert bv.security_admitted("NEWCO", None) == (True, "type_unknown")
    assert bv.security_admitted("ZCSH", "ETV", "The Zcash ETF") == (True, "fund_kept")
    assert bv.security_admitted("ZCSH", "ETV", None) == (False, "fund_no_name")
    assert bv.security_admitted("AGQ", "ETV", "ProShares Ultra Silver") == (False, "fund_leveraged_or_inverse")
    assert bv.security_admitted("SPY", "ETF") == (False, "type_other")
    assert bv.security_admitted("BRK.B", "CS") == (False, "ticker")
    assert bv.security_admitted("ZVZZT", "CS") == (False, "ticker")
