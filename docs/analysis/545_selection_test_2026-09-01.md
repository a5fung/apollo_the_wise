# #545 — The selection test: can anything knowable at fire time separate the tail?

**Date:** 2026-09-01 · **Read-only, $0, nothing flipped** · Probe + output:
`scripts/probes/_545_selection_test.py`, `_545_selection_test_out.txt`, `_545_features.psv`

## 1. The decision this serves

Two independent threads converged on the same constraint today. The delayed-entry backfill found
the four buy signals fire on **96% of caught EPs** — recall is solved — while **every group loses
money**, median fire a full stop, in every month and both exit styles. The #482 bracket-geometry
re-read arrived from the other side: the only real signal in the 5-minute lane was that its
*refusals* dodged 21 losing days with zero winners. Neither recall nor geometry is the lever.

So: **can any feature knowable AT FIRE TIME separate the ~18 tail fires from the ~550 losers?**
If nothing can, delayed entry does not pay as a tactic and we should stop working it.

## 2. Method / population

- **Population:** 569 settled first-attempt fires across 267 caught EPs (live-source `mi_ep_alerts`,
  May–Aug 2026), from the backfill replay. Unsettled and abstained fires are excluded entirely —
  never counted as either outcome.
- **Outcome:** HARVESTED realized R, never MFE. "Tail" = a fire that harvested **≥4R** — the level
  THE GOAL requires, since at our ~17–20% win rate the average winner must clear ~4R to break even.
- **Base rate: 18 of 569 = 3.2%.**
- **Pre-registered 2026-09-01 on the #545 PLAN line, before any of this ran.** Features were a
  closed list; the pass bar was fixed; the null was written down in advance.

**PASS BAR — all three:** (a) tail rate ≥ **8%** (the campaign study's P13 break-even band is
8–18%); (b) **n ≥ 30** fires; (c) holds with **May excluded** *and* on **both exit arms**.

## 3. The numbers

49 cuts across 10 of the 11 pre-registered features. **Zero passed.** The best six:

| cut | n | tail | rate | ex-May | trail arm | mean R | pass |
|---|---|---|---|---|---|---|---|
| simulated day-1 group = unclassifiable | 8 | 2 | 25.0% | 0.0% | 12.5% | +4.78 | — n=8 |
| only ONE signal fired | 30 | 4 | 13.3% | **4.5%** | 10.0% | +0.37 | — fails ex-May |
| two signals fired | 209 | 13 | 6.2% | 3.6% | 4.3% | −0.19 | — |
| not in an active theme | 210 | 13 | 6.2% | 3.3% | 3.8% | −0.18 | — |
| stop width ≥ 2.4% of entry | 285 | 17 | 6.0% | 3.4% | 3.9% | −0.23 | — |
| prior-day RS ≥ 77 | 144 | 7 | 4.9% | 2.1% | 1.4% | −0.41 | — |

- **Nothing reaches 8% at a usable n.** The only cut above it with n≥30 is "only one signal fired",
  and **May alone carries it**: 13.3% raw falls to 4.5% once May is removed — the era the operator
  has ruled stale. That is the same collapse every other delayed-entry result showed today.
- **Mean R is negative in every cut but one**, and that one is n=8 unclassifiable campaigns.
- **The features barely move the base rate at all.** RS, gap size, dollar volume, catalyst grade,
  theme membership, which signal fired, when it fired — all land between 3% and 6% against a 3.2%
  base. None of them knows anything about the tail.
- **Multiple comparisons, stated honestly:** 49 cuts, 18 positives, 3.2% base. Some cut clearing 8%
  by chance is *expected* at that many tries. A single passing cut would have been noise; zero
  passing cuts is a much stronger statement than one passing cut would have been.

## 4. What this does not answer

- **Extension at the EP was untestable** — 0 of 569 fires carry it (it is only computed for names
  reaching the graded shortlist, the same darkness that made `screen_member` useless). 10 of the 11
  pre-registered features were tested; that one was not, and a future read should include it.
- **Whether a COMBINATION separates** where no single feature does. Deliberately not tested: with
  18 positives, fitting interactions is how you manufacture a finding. It would need a pre-registered
  hypothesis and a held-out period.
- **Whether a different exit changes the answer.** Both modelled arms were tested and neither helps,
  but the space of exits is larger than the two the lane models.
- **Whether the tactic works on a population we cannot yet see** — names we never caught at all are
  #577/P1's problem, not this study's.
- **It does not say the buy signals are broken.** They find the turns reliably. It says knowing
  *which* turn to take is not available in the facts we hold at fire time.

## 5. ⚖ THE LINE

Nothing was flipped, changed, or proposed as done. Any change to a delayed-entry rung or to what we
trade is entry discipline — the operator's sole authority, CHANGE_PROCESS and sign-off.

**Recommendation, and it is the pre-registered null:** on this evidence delayed entry does not pay
as a tactic, and further tuning of buy points, stops or populations is not warranted. The honest
next move is to stop working it and put the effort where today's other thread pointed — selection
at the ALERT layer, which is the same constraint one step earlier.
