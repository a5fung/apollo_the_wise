"""His grades on breakout v1's nightly list (#717), read on chart sheets shown in chat — his 2026-11-05
ruling ("the scoring we do for pattern is much better when you show me the chart"), not Telegram /bgrade.

Each sheet: names drawn at random from one list night, stratified by list rank; the chart ends on the list
night, the dashed line is the name's level (the highest high of the last 5 sessions). He sees no ticker, rank
or score. Keyed on (ticker, list_date). `grade` normalises his words: good / ok (incl. "okish") / no (incl.
"looks extended") / conditional ("depends how far it breaks out"). His words are kept verbatim.

These are DETECTION labels (is this a real breakout setup?), never a returns verdict.
"""
from dataclasses import dataclass

GRADES_ALLOWED = frozenset({"good", "ok", "no", "conditional"})


@dataclass(frozen=True)
class BreakoutGrade:
    list_date: str
    ticker: str
    sheet_card: str
    list_rank: int
    order_score: float
    level: float
    grade: str
    operator_words: str
    sheet: str


_SHEET_1106 = "scripts/probes/_717_grading_sheet_1107/breakout_sheet_1106.png"   # graded 2026-11-07, 12 of 184

_SHEET_1105 = "scripts/probes/_717_grading_sheet_1109/breakout_sheet_1105.png"   # graded 2026-11-09, 12 of 150 (names graded before excluded)

_CONTRAST_1111 = "scripts/probes/_717_shape_gates_1111/contrast_sheet.png"   # 2026-11-11: five good/ok regraded no; his ABCL lines in his_lines_abcl_nvax_1111.png

_BOUGHT_1111 = "scripts/probes/_717_shape_gates_1111/bought_sheet.png"   # graded 2026-11-11 in chat: the 12 names amendment 2 would buy first (order_score not stored: 0.0; list_rank = the original rank)

_MODEL_1113 = "scripts/probes/_717_pick_model_1113/sheet_model_picks.png"   # graded 2026-11-13 in chat: 12 random picks of the learned ranking, test years 2021-22 (list_rank = the model rank that day; level not stored: 0.0)

_LIVE_1110 = "scripts/probes/_717_723_verify_1110/breakout_live_1110.png"   # graded 2026-11-10 in chat: the 5 paper buys, tickers shown

BREAKOUT_LIST_GRADES: list[BreakoutGrade] = [
    BreakoutGrade("2026-11-06", "IAG", "A", 145, 0.326, 18.79, "no", "regraded 2026-11-11 on the contrast sheet: \"on second look, the charts on first line can be interpreted as not making higher lows, what's fine, stick with qullamaggie first\" (was good)", _SHEET_1106),
    BreakoutGrade("2026-11-06", "SIG", "B", 73, 0.568, 129.26, "no", "looks extended", _SHEET_1106),
    BreakoutGrade("2026-11-06", "VFC", "C", 134, 0.367, 21.22, "no", "looks extended", _SHEET_1106),
    BreakoutGrade("2026-11-06", "PAYS", "D", 5, 0.916, 15.88, "good", "good", _SHEET_1106),
    BreakoutGrade("2026-11-06", "APPN", "E", 14, 0.821, 56.38, "ok", "okish", _SHEET_1106),
    BreakoutGrade("2026-11-06", "HAE", "F", 17, 0.815, 132.0, "ok", "okish", _SHEET_1106),
    BreakoutGrade("2026-11-06", "PAY", "G", 30, 0.75, 35.26, "conditional", "depends how far it breaks out", _SHEET_1106),
    BreakoutGrade("2026-11-06", "FNKO", "H", 21, 0.793, 6.76, "no", "regraded 2026-11-11 on the contrast sheet: \"on second look, the charts on first line can be interpreted as not making higher lows, what's fine, stick with qullamaggie first\" (was ok)", _SHEET_1106),
    BreakoutGrade("2026-11-06", "PAR", "I", 152, 0.299, 21.05, "good", "good", _SHEET_1106),
    BreakoutGrade("2026-11-06", "RSKD", "J", 41, 0.668, 8.98, "no", "regraded 2026-11-11 on the contrast sheet: \"on second look, the charts on first line can be interpreted as not making higher lows, what's fine, stick with qullamaggie first\" (was good)", _SHEET_1106),
    BreakoutGrade("2026-11-06", "PLSE", "K", 11, 0.867, 58.17, "good", "good", _SHEET_1106),
    BreakoutGrade("2026-11-06", "BHC", "L", 174, 0.177, 8.46, "ok", "ok", _SHEET_1106),
    BreakoutGrade("2026-11-05", "EVH", "A", 9, 0.847, 4.98, "good", "good", _SHEET_1105),
    BreakoutGrade("2026-11-05", "BILL", "B", 31, 0.697, 52.54, "good", "good", _SHEET_1105),
    BreakoutGrade("2026-11-05", "AMPH", "C", 97, 0.43, 29.21, "good", "good", _SHEET_1105),
    BreakoutGrade("2026-11-05", "ONT", "D", 146, 0.127, 19.61, "no", "already gapped up", _SHEET_1105),
    BreakoutGrade("2026-11-05", "CHTR", "E", 147, 0.12, 127.16, "no", "no", _SHEET_1105),
    BreakoutGrade("2026-11-05", "OSCR", "F", 23, 0.76, 38.5, "ok", "ok", _SHEET_1105),
    BreakoutGrade("2026-11-05", "DUOL", "G", 145, 0.143, 175.56, "no", "no", _SHEET_1105),
    BreakoutGrade("2026-11-05", "CVLT", "H", 15, 0.817, 173.0, "no", "regraded 2026-11-11 on the contrast sheet: \"on second look, the charts on first line can be interpreted as not making higher lows, what's fine, stick with qullamaggie first\" (was ok)", _SHEET_1105),
    BreakoutGrade("2026-11-05", "MANE", "I", 3, 0.91, 145.41, "no", "regraded 2026-11-11 on the contrast sheet: \"on second look, the charts on first line can be interpreted as not making higher lows, what's fine, stick with qullamaggie first\" (was ok)", _SHEET_1105),
    BreakoutGrade("2026-11-05", "PLNT", "J", 106, 0.38, 60.22, "no", "no", _SHEET_1105),
    BreakoutGrade("2026-11-05", "ASO", "K", 93, 0.443, 69.62, "no", "looked extended", _SHEET_1105),
    BreakoutGrade("2026-11-05", "BLKB", "L", 13, 0.837, 57.85, "ok", "ok", _SHEET_1105),
    BreakoutGrade("2026-11-09", "MRNA", "A", 24, 0.79, 280.8, "no", "the 5 stocks you listed don't look like breakouts at all", _LIVE_1110),
    BreakoutGrade("2026-11-09", "SPCE", "B", 31, 0.751, 2.94, "no", "the 5 stocks you listed don't look like breakouts at all", _LIVE_1110),
    BreakoutGrade("2026-11-09", "ABCL", "C", 36, 0.733, 12.74, "no", "where's the higher low, where's the surfing moving avg? if anything, it's still flagging at best, no higher lowers", _LIVE_1110),
    BreakoutGrade("2026-11-09", "OUST", "D", 70, 0.604, 38.895, "no", "oust is worse, just chopping around, no pattern at all", _LIVE_1110),
    BreakoutGrade("2026-11-09", "NVAX", "E", 103, 0.523, 11.195, "no", "the 5 stocks you listed don't look like breakouts at all", _LIVE_1110),
    BreakoutGrade("2026-11-10", "PLSE", "A", 10, 0.0, 58.94, "conditional", "maybe", _BOUGHT_1111),
    BreakoutGrade("2026-11-10", "BLKB", "B", 8, 0.0, 57.845, "conditional", "maybe, a few more tight days", _BOUGHT_1111),
    BreakoutGrade("2026-11-10", "CVLT", "C", 9, 0.0, 169.3199, "ok", "ok", _BOUGHT_1111),
    BreakoutGrade("2026-11-10", "VEEV", "D", 2, 0.0, 314.2299, "conditional", "a few more tight days", _BOUGHT_1111),
    BreakoutGrade("2026-11-10", "EVH", "E", 6, 0.0, 4.975, "ok", "ok", _BOUGHT_1111),
    BreakoutGrade("2026-11-10", "DOCS", "F", 1, 0.0, 35.15, "no", "no", _BOUGHT_1111),
    BreakoutGrade("2026-11-10", "CTSH", "G", 12, 0.0, 67.95, "no", "no", _BOUGHT_1111),
    BreakoutGrade("2026-11-10", "NCNO", "H", 11, 0.0, 23.78, "conditional", "few more tight days", _BOUGHT_1111),
    BreakoutGrade("2026-11-10", "AMPL", "I", 4, 0.0, 18.85, "no", "no", _BOUGHT_1111),
    BreakoutGrade("2026-11-10", "AMLX", "J", 5, 0.0, 31.22, "no", "no", _BOUGHT_1111),
    BreakoutGrade("2026-11-10", "APPN", "K", 15, 0.0, 56.38, "no", "no, needs more time", _BOUGHT_1111),
    BreakoutGrade("2026-11-10", "BLLN", "L", 7, 0.0, 117.9698, "no", "no", _BOUGHT_1111),
]


# His grades on the LEARNED RANKING's picks (#717, 2026-11-13) — historical charts (2021-22 test years), kept apart
# from BREAKOUT_LIST_GRADES (whose tests need bars for every row). None of the 12 was a Qullamaggie buy.
MODEL_PICK_GRADES: list[BreakoutGrade] = [
    BreakoutGrade("2021-10-08", "ATYR", "A", 5, 0.0, 0.0, "ok", "looks ok, caveat is the run up (post huge EP day) then quickly giving it all back, not much time to build range after that volatility", _MODEL_1113),
    BreakoutGrade("2022-03-21", "X", "B", 4, 0.0, 0.0, "no", "no pull back or basing , I don't see a setup", _MODEL_1113),
    BreakoutGrade("2021-12-28", "ZIM", "C", 4, 0.0, 0.0, "no", "don't see setup, it's in a large base", _MODEL_1113),
    BreakoutGrade("2021-05-12", "TELL", "D", 5, 0.0, 0.0, "ok", "looks ok", _MODEL_1113),
    BreakoutGrade("2021-11-16", "CAR", "E", 1, 0.0, 0.0, "ok", "looks ok", _MODEL_1113),
    BreakoutGrade("2021-09-20", "LCID", "F", 5, 0.0, 0.0, "no", "no setup, gapped down and moved back into base/range, no breakout", _MODEL_1113),
    BreakoutGrade("2021-08-17", "SWAV", "G", 5, 0.0, 0.0, "no", "choppy, very large bars (red), no tightness", _MODEL_1113),
    BreakoutGrade("2021-12-10", "FLGT", "H", 5, 0.0, 0.0, "no", "random stock, nothing in it, no setup at all, large ranges, no run up", _MODEL_1113),
    BreakoutGrade("2021-04-23", "VUZI", "I", 2, 0.0, 0.0, "ok", "looks ok", _MODEL_1113),
    BreakoutGrade("2022-03-02", "F", "J", 4, 0.0, 0.0, "no", "nothing at all, downtrend, gap down, large bars, no setup at all", _MODEL_1113),
    BreakoutGrade("2021-04-23", "MVIS", "K", 4, 0.0, 0.0, "no", "random, still in large range, no building higher lows, poor", _MODEL_1113),
    BreakoutGrade("2021-06-23", "FUTU", "L", 3, 0.0, 0.0, "conditional", "maybe ok but not great, where's the runup and tightness", _MODEL_1113),
]
