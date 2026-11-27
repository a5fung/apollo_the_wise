# Stage 4 part 1 recount - match rule (written and hashed BEFORE any stage 1/2/3 output was opened)
- EXACT match required: every count (pool rows, bridge sets, break rows, drops per reason, q, kept events per seed/era/set/year, identities, buys coverage,
  guard/bars-end-in-window counts, outcome counts winners/monsters/clean/adr/fail, base rates), feature-table values (cell by cell on era,ticker,D; float tol 1e-9),
  NULL counts per feature x era x year x reason, tie/null totals, corrupt-E result.
- Statistics: ratios, rates, ex-2020 ratios EXACT (same thirds); permutation p, z, bootstrap intervals match within Monte-Carlo tolerance (p within +-0.01 abs for p>=0.02,
  z within 5% rel, CI endpoints within 0.05) because the blind recount cannot know the draw layout; carried / not-carried must agree, a flip from a p within 0.01 of 0.05 is reported.
- Any difference is TRACED to a named reading; never retuned to fit. Anything untraced or unfinished => gate_pass=false.
- Readings are fixed in the code BEFORE comparing; the ones the text leaves open are listed in readings.md.
