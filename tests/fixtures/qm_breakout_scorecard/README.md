# Qullamaggie breakout scorecard fixtures

- `buys.tsv` + `bars.psv.gz` — his 269 DATED breakout buys (2017-2023): the positions our own breakout / EP detector
  could date. Built by `scripts/probes/_qm_breakouts_vs_v1_1102/40_export_scorecard_fixture.py` (2026-11-02).
- `buys_undated_widened.tsv` + `bars_undated_widened.psv.gz` — 488 MORE of his positions, the ones our detector left
  undated (`undated_reason = no_event_in_window`): the buy window `lo .. hi` is known, our detector found no event in
  it. Built 2026-11-11 by `scripts/probes/_717_shape_gates_1111/20_widened_set.py` from `holdings_1024/entries.tsv`:
  1,040 undated -> window of 5 sessions or fewer 921 -> not a flicker 596 -> seen twice or more 570 -> has bars, not
  an initial holding 570 -> window ends by 2022-04-01 (era-A bar store only) 546 -> ticker and a bar in the window 537
  -> no EP-like gap in the window (open >= 9% over the prior close, the EP dating's own floor) **488**. Bars run from
  300 sessions before the first night through `hi` — none after it. The setup of each position is NOT known (the panel
  shows holdings, not why he bought): some are leveraged or index funds the list never takes, some may be other setups.
  The last three columns are the 2026-11-11 reading (on the list on any night `lo-1 .. hi-1`), not a spec.
- `mtw_bars.csv` — MTW to 2026-10-30 (breakout v1's first paper buy, "not a breakout").
