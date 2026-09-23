"""#284 backtest — M&A filter acquirer-direction TITLE check (title_implies_acquirer).

Validates the new Path A title-direction guard against a labeled set:
  - ACQUIRER titles (filing ticker is the buyer)  -> expect True  (do NOT fire)
  - TARGET / bleed titles (filing ticker is being acquired, or out-of-scope)
    -> expect False (KEEP firing — conservative)

Real cases: ONDS / MYRG (the live FP leaks) + CECO (multi-ticker bleed, out of
scope -> must still fire). Plus synthetics covering the positional trap
('BigCo to Acquire Acme' filed under the TARGET Acme) and target object-forms.

ASCII-only output (cp1252 console safety). Run: python -m scripts._284_mna_acquirer_backtest
"""
from agents.market_intelligence.ma_filter import title_implies_acquirer

# (title, filing_company_name, expected_is_acquirer, label)
CASES = [
    # ---- ACQUIRER (expect True = pass / do not fire) ----
    ("Ondas Bets Big On AI Battlefield Software With Omnisys Buyout",
     "Ondas Holdings, Inc.", True, "ONDS real - object form (buys Omnisys)"),
    ("MYR Group Enters Definitive Agreement to Acquire Valley Electric and Comet Electric",
     "MYR Group Inc.", True, "MYRG real - verb form (to acquire)"),
    ("Nebius to Acquire Eigen AI for $643 Million",
     "Nebius Group N.V.", True, "NBIS-class - verb form"),
    ("MegaCorp Announces TinyCo Takeover",
     "MegaCorp Inc.", True, "synthetic - object form (takeover)"),
    ("BigPharma Completes Acquisition of SmallBio",
     "BigPharma Inc.", True, "synthetic - verb form (completes acquisition)"),
    ("Acme Corp to Buy Beta Inc for $1B",
     "Acme Corp", True, "synthetic - verb form (to buy)"),

    # ---- TARGET / out-of-scope (expect False = keep firing) ----
    ("BigCo to Acquire Acme in $2B Deal",
     "Acme Inc.", False, "POSITIONAL TRAP - Acme is the TARGET"),
    ("Avanos To Go Private",
     "Avanos Medical, Inc.", False, "AVNS real - target, go-private"),
    ("SmallCo Buyout Talks Advance",
     "SmallCo Inc.", False, "target - filing co precedes its own buyout"),
    ("Management Buyout of Acme Corp Completed",
     "Acme Corp", False, "MBO - 'Management' not an entity, Acme=target"),
    ("Acme Receives Buyout Offer From BigCo",
     "Acme Corp", False, "target - receives buyout offer"),
    ("Valley Electric to Be Acquired by MYR Group",
     "Valley Electric Inc.", False, "target - to be acquired by"),
    ("CECO Environmental and Thermon Group Holdings Announce Election Deadline "
     "for Thermon Stockholders to Elect Form of Merger Consideration",
     "CECO Environmental Corp.", False,
     "CECO real - multi-ticker bleed (about THR); OUT OF SCOPE, must still fire"),
    ("KalVista Pharmaceuticals Shareholder Investigation Notice",
     "KalVista Pharmaceuticals, Inc.", False, "not an M&A title at all"),
]


def main() -> int:
    passed = 0
    failed = 0
    n_acq = sum(1 for *_, exp, _l in CASES if exp)
    print(f"#284 acquirer-direction title backtest  (N={len(CASES)}: "
          f"{n_acq} acquirer / {len(CASES)-n_acq} target)\n")
    for title, company, expected, label in CASES:
        got = title_implies_acquirer(title, company)
        ok = (got == expected)
        passed += ok
        failed += (not ok)
        mark = "OK  " if ok else "FAIL"
        verdict = "PASS(no-fire)" if got else "FIRE"
        print(f"  [{mark}] exp={'ACQ' if expected else 'TGT':3} got={verdict:13} "
              f"{label}")
        if not ok:
            print(f"         title: {title!r}")
            print(f"         company: {company!r}")
    print(f"\n  {passed}/{len(CASES)} passed, {failed} failed")
    # Extra: confirm no-company-name is conservative (returns False = fire)
    assert title_implies_acquirer("Acme to Acquire Beta", None) is False, \
        "no company name must be conservative (fire)"
    assert title_implies_acquirer("", "Acme Corp") is False
    print("  guard: no-company-name -> conservative (fire): OK")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
