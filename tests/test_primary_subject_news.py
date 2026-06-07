"""#210 Wave A — primary-subject news relevance filter (the #88/#90 contamination
class guard for the grounded catalyst corpus).

Anchored on the three cases the advisor flagged from the live GRRR 6/2 probe:
  - GRRR-primary deal headline (co-tagged SMCI)         -> KEEP
  - SMCI-primary "falling" headline (co-tagged GRRR)    -> DROP
  - "12 IT Stocks Moving" roundup                       -> DROP
"""
from agents.market_intelligence.collector import is_primary_subject_news


def _item(title, symbols=None, summary=""):
    return {"title": title, "summary": summary, "symbols": symbols or []}


# --- The GRRR 6/2 probe trio (advisor's acceptance cases) ---------------------

def test_grrr_primary_deal_headline_kept():
    it = _item(
        "GRRR, SMCI Extend Collaboration After $2B India Supply Deal",
        symbols=["GRRR", "SMCI"],
    )
    assert is_primary_subject_news(it, "GRRR", "Gorilla Technology Group, Inc.") is True


def test_grrr_kept_via_company_name_when_symbol_absent():
    # PR headline that uses the company name, not the ticker symbol.
    it = _item(
        "Gorilla Technology Announces $2 Billion AI Infrastructure Deal in India",
        symbols=["GRRR", "SMCI"],
    )
    assert is_primary_subject_news(it, "GRRR", "Gorilla Technology Group, Inc.") is True


def test_smci_primary_cotagged_grrr_dropped():
    # SMCI is the subject; GRRR only co-tagged -> must NOT enter GRRR's corpus.
    it = _item("Super Micro Computer Stock Is Falling 11% — Here's Why",
               symbols=["SMCI", "GRRR"])
    assert is_primary_subject_news(it, "GRRR", "Gorilla Technology Group, Inc.") is False


def test_roundup_dropped():
    it = _item("12 IT Stocks Moving In Tuesday's Pre-Market Session",
               symbols=["GRRR", "SMCI", "NVDA", "DELL"])
    assert is_primary_subject_news(it, "GRRR", "Gorilla Technology Group, Inc.") is False


# --- Roundup / basket variants -----------------------------------------------

def test_stocks_to_watch_dropped():
    it = _item("Stocks To Watch: Gorilla Technology, Nvidia, AMD", symbols=["GRRR"])
    assert is_primary_subject_news(it, "GRRR", "Gorilla Technology Group, Inc.") is False


def test_midday_movers_dropped():
    it = _item("Midday Movers: GRRR, TSLA, AAPL", symbols=["GRRR"])
    assert is_primary_subject_news(it, "GRRR", "Gorilla Technology Group, Inc.") is False


# --- Single-symbol + edge cases ----------------------------------------------

def test_single_symbol_pr_kept_even_without_name_match():
    it = _item("Company Secures Major Government Order", symbols=["GRRR"])
    assert is_primary_subject_news(it, "GRRR", "Gorilla Technology Group, Inc.") is True


def test_generic_company_token_does_not_false_match():
    # "Technology"/"Group" are generic — a different stock's headline that
    # happens to contain them must not pass as GRRR.
    it = _item("Apple Technology Group Rumor Roundup", symbols=["AAPL"])
    assert is_primary_subject_news(it, "GRRR", "Gorilla Technology Group, Inc.") is False


def test_empty_title_dropped():
    assert is_primary_subject_news(_item("", symbols=["GRRR"]), "GRRR", "Gorilla") is False
