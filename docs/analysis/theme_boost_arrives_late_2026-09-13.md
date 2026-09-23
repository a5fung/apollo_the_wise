# The theme boost reaches the stock after the EP it was meant to inform (2026-09-13)

> **Operator, raising it as a design objection:** *"building a theme is to discover strength in a
> group, if a stock (EP) gets recognized to be in the theme, it should get the boost. Otherwise it's
> kinda backwards, EP will likely move the stock into a theme but the EP already happened so there's
> nothing to boost"*

**He is right, and the size of it is larger than the mechanism's own reach.**

**Bar, declared BEFORE the query** (per the practice adopted today): if a materially larger share of
EP alerts join a theme *after* firing than were in one *on the day*, membership lags the EP and the
boost is arriving after the event it should have informed.

**Method / population**: all `mi_ep_alerts` rows with a score, `alert_date >= CURRENT_DATE - 120`,
**n = 346**. Theme membership read from `mi_themes` with the engine's own 7-day liveness window.
The boost is `+10` on the EP score, `ep_detector.py:1666`, R4 live since 2026-05-17, env flag unset
so **ON**. It requires the ticker to appear literally in the ticker list of a theme staged
**Accelerating or Mainstream** (`ep_detector.py:3180-3188`).

## 1. Membership arrives late — his exact claim

| | n | share of 346 |
|---|---|---|
| in a boosting theme **on the alert day** → got the +10 | **22** | 6% |
| **not** in one on the day | 324 | 94% |
| …of those, joined **some** theme within 30 days **after** | **99** | 31% of the 324 |
| …of those, joined a **boosting** theme within 30 days after | **54** | 17% of the 324 |
| …never joined any theme | 225 | 69% of the 324 |

**Median lag from alert to joining: 4 days.** 59 of the 99 joined within 5 days.

**So 2.5× as many stocks are recognised LATE as are recognised in time** (54 after vs 22 on the
day). The bar is met: the boost systematically arrives after the alert it exists to inform.

⚠ **What this does NOT establish: causality.** Whether the EP *moved* the stock into the theme (his
reflexivity point) or the theme was forming anyway cannot be separated by this measurement. Either
way the boost does not reach the stock at the moment it would matter — that part holds regardless.

## 2. The sharper finding — half the misses are a STAGE rule, not a discovery failure

Asking a different question: on the alert day, had the engine already placed this stock in *any*
theme?

| stage on the alert day | n | share | |
|---|---|---|---|
| Mainstream | 28 | 8% | gets +10 |
| Accelerating | 3 | 1% | gets +10 |
| **Nascent** | **32** | **9%** | **the engine HAD the group — pays NOTHING** |
| Fading | 9 | 3% | pays nothing |
| no theme at all | 274 | 79% | |

- **Boost pays today: 31 of 346 (9%).**
- **If Nascent paid: 63 of 346 (18%) — it would double, with no new discovery, no new data, and no
  change to how themes are found.**
- Named cases where the engine knew the group and the alert got nothing: **PLTR 2026-08-04 at
  ep_score 96.0**, AGX 09-03 (65.0), ALAB 09-04 (65.0), IONQ 09-08 (65.0), LIND 08-03 (70.0),
  EFOR 07-22 (50.4).

**This is not a new discovery.** #368 already recorded the Nascent exclusion (PLTR and MRNA had
correct themes and got no boost), and **#655 parked it as step-3 work** — how themes influence
trading — behind steps 1 and 2. His objection today is that the mechanism is *backwards*, which is a
step-1/step-2 question about whether the theme signal reaches the EP at the right time at all. **That
reframing is his to make, and unparking it is his call.**

## What would have to change — HIS decision, not taken

⚖ Every option below is a **detection criterion** ⇒ CHANGE_PROCESS + backtest + sign-off. Recorded
so the options are visible, **not** as a recommendation:

- **Let Nascent pay** (possibly at fewer than 10 points). Doubles reach; smallest change; the 32
  cases above are the evidence base.
- **Score the GROUP, not the membership list** — at alert time, are this stock's peers strong? That
  is a different signal from "has the nightly engine already filed this ticker", and it is immune to
  the 4-day lag.
- **Leave it.** 79% of EP alerts have no theme at any stage, so the ceiling on any version of this
  mechanism is low, and he has ruled that coverage is not the goal.

## What this does NOT answer

- Whether the +10 is the right SIZE, or whether it should differ by stage. Untested.
- Whether the 4-day lag is the EP causing the membership or coincidence (above).
- Whether boosting the 32 Nascent cases would have improved any outcome — that is a returns
  question, and returns on themes stay parked by his own sequencing.
- The 274 with no theme at any stage: unknown whether they had a real group the engine missed, or no
  group at all. That is the step-1 recall question, measured separately.
