# #719 breadth export — first prod runs (2026-11-04, read-only, as_of 2026-11-04)

- Run time: 15 s (run 1), 11 s (run 2, after the review fixes). 174 KB.
- Run 1 (as built): stages 1 635 / 2 1,300 / 3 897 / 4 1,386 / unstaged 817 of 5,035. `unst.sql`: of the 5,035, 4,218 had all 210 bars, 439 are listed under 210 sessions, 169 miss 1-7 bars, 209 miss 8+.
- Run 2 (stage rule relaxed to 203 of 210, the 245-of-252 slack; future-date ceiling; NaN guard): `breadth_2026-11-04.json` — universe 5,035; new highs 277 / new lows 178 of 4,331 eligible; advances 3,310 / declines 1,548 / unchanged 117 / no bar on the previous session 60; stages 1 664 / 2 1,328 / 3 927 / 4 1,480 / unstaged 636 (sum 5,035).
- Independent recount (`indep.sql` → `indep.out`, per-ticker formulation, the ticker's own latest prior close): universe 5,035, highs 277, lows 178, eligible 4,331 — exact. Advances 3,336 / declines 1,568 / unchanged 131: the export's 3,310 / 1,548 / 117 plus exactly its 60 'no prior' names (26 + 20 + 14 = 60), which the export leaves out because they have no bar on the previous session.
- Three themes' Today / 1W / 1M / YTD recomputed by hand from member closes (`themes3.*`): Orthopedic & Spinal Surgery Devices, Primary Silver Miners, Bank Stocks: Rising-Rate NIM Expansion — all 12 numbers and member counts match to 2 dp.
