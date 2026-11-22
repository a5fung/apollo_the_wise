"""r2_05b: split the EP events dropped by the CS filter (ticker + date columns only; no outcome column read) and print the era date spans."""
import pandas as pd, os
ev = pd.read_csv("../_ep_winner_study_1121/build/stage6_minutes/02b_events.tsv.gz", sep="\t", usecols=["era", "ticker", "E"], parse_dates=["E"]); ev = ev[ev.E <= pd.Timestamp("2024-12-31")]; assert ev.E.max() <= pd.Timestamp("2024-12-31")
lst = {}
for l in open(os.path.expanduser("~/apollo_data/cb702/cb702_sic.psv")): p = l.rstrip("\n").split("|"); lst[p[0]] = p[-1]
on = ev.ticker.map(lambda t: t in lst); cs = ev.ticker.map(lambda t: lst.get(t) == "CS")
print(f"EP events {len(ev)}: flagged CS {int(cs.sum())}; on the 2026-10-16 list but not CS {int((on & ~cs).sum())}; NOT on the list at all {int((~on).sum())}")
print("not-on-list events by year:", ev[~on].groupby(ev.E.dt.year).size().to_dict()); print("all events by year:", ev.groupby(ev.E.dt.year).size().to_dict())
print("non-CS flags among listed-but-dropped:", ev[on & ~cs].ticker.map(lst).value_counts().to_dict())
for e, g in ev.groupby("era"): print(f"era {e}: n={len(g)} E {g.E.min().date()} -> {g.E.max().date()}")
