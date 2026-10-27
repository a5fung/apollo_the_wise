"""Tests for the #705 as-is read, step 6a (scripts/probes/_705_asis_1026/02_captions.py; the plan's §10 step-6 list as it applies to 6a).
Synthetic fixtures only: no apollo_data, no machine path, no /usr/share word list (every function takes its word list). CI collects tests/ only.

Covers: the alias extension recovers a garbled / renamed symbol from a fixture lexicon (unique nearest, the caption-evidence tie-break, the
English-word rule, the edit limits, a symbol said aloud that is not live, the no-bars table, the panel-symbol alias); the statement kinds incl.
shorted / covered (and the phrases they must NOT take); the copied engine equals the inventory's; the late-upload stream date and the duplicate
of one stream; the dedupe of rolling captions and of duplicate uploads; the +-30 s filter, the dictionary-word classes and the strata; the price
tier; the join never reads the action or a price; the sheets carry no window / bar / price / machine-hint column; the seeded draws; the
agreement scorer; the seal; the identifier scan and the fresh-interpreter import test on 02_captions.py.
"""
from __future__ import annotations

import ast
import collections
import importlib.util
import inspect
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ASIS = REPO / "scripts" / "probes" / "_705_asis_1026"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


CAP = _load("asis_captions02", ASIS / "02_captions.py")
C = CAP.C
INV = CAP.INV


# ═════════════════════════════════════════════════════════════════════════════════════════════ fixtures
def mkvideo(vid: str, upload: str, words: list, title: str = "stream", seconds: int = 3600):
    """words = [(t_seconds, 'word'), ...]; the Video is finished the way Video.load finishes it."""
    v = INV.Video({"id": vid, "upload_date": upload, "title": title, "seconds": str(seconds)})
    v.toks = [w for _, w in words]
    v.times = [float(t) for t, _ in words]
    CAP.finish_video(v)
    return v


def speech(text: str, t0: float = 0.0, step: float = 1.0) -> list:
    return [(t0 + i * step, w) for i, w in enumerate(text.split())]


FAR = ("2016-01-04", "2022-06-30", "2021-09-27", "2026-10-16")
LEX = {"TQQQ": FAR, "THQ": FAR, "QQQ": FAR, "TWIN": FAR, "NVDA": FAR, "META": FAR, "AAPL": FAR, "RIOT": FAR, "BOIL": FAR, "GUSH": FAR,
       "FB": ("", "", "2021-09-27", "2026-10-16"), "LATE": ("2021-06-01", "2022-06-30", "", ""), "IPOS": ("2016-01-04", "2022-06-30", "", ""),
       "TLRY": FAR, "SPY": FAR, "HAS": FAR}
DICT = {"twin", "cash", "gosh", "gush", "boil", "spy", "riot", "the", "play", "is", "was", "bought", "sold", "stopped", "out", "it", "i", "at", "in", "on",
        "now", "good", "shares", "of", "my", "and", "a", "to", "have", "got", "back", "short", "covered"}
CONN = {"the", "is", "was", "has", "of"}


def words_obj(common=()):
    return CAP.Words(DICT, CONN, common, CAP.FILLERS)


def index_of(common=(), lex=None, alias=None, no_bars=("TVIX",)):
    return CAP.SymbolIndex(lex or LEX, alias if alias is not None else {"FB": "META"}, words_obj(common), no_bars)


# ═════════════════════════════════════════════════════════════════════════════════════════════ the alias list and the search set
def test_alias_recovers_garbled_symbols_from_a_fixture_lexicon():
    idx = index_of()
    # evidence-free: 'tqq' is one edit from TQQQ and from THQ (live): tied -> ambiguous, listed with both
    res = CAP.AliasResolver(idx)
    status, sym, dist, tied = res.resolve("tqq", "2020-06-15")
    assert (status, sym, dist) == ("ambiguous", None, 1) and set(tied) == {"TQQQ", "THQ"}
    # the caption heard the literal symbol 52 times: the attested candidate wins (R42), THQ never heard
    res2 = CAP.AliasResolver(idx, collections.Counter({"tqqq": 52}))
    assert res2.resolve("tqq", "2020-06-15")[:3] == ("alias", "TQQQ", 1)
    # 'twix' -> TVIX (no-bars table) against TWIN (a dictionary-word symbol, never attested as a strong symbol)
    res3 = CAP.AliasResolver(idx, collections.Counter({"tvix": 17, "twin": 40}))
    assert res3.resolve("twix", "2020-06-15")[:3] == ("alias", "TVIX", 1)
    # a unique nearest needs no evidence; two edits are allowed from six letters; five letters get one
    assert res.resolve("nvidia", "2020-06-15")[:3] == ("alias", "NVDA", 2)
    assert res.resolve("nvdia", "2020-06-15")[0] == "alias"          # 1 edit (a missing letter), five letters
    assert res.resolve("nvdiaa", "2020-06-15")[0] == "alias"         # six letters, 2 edits from nvda
    assert CAP.alias_limit(2) == 0 and CAP.alias_limit(3) == 1 and CAP.alias_limit(5) == 1 and CAP.alias_limit(6) == 2
    assert res.resolve("nv", "2020-06-15")[0] == "none"              # two letters are never re-aimed
    assert res.resolve("nvidx", "2020-06-15")[0] == "none"           # five letters, 2 edits from nvda: beyond the limit
    # same first letter only
    assert res.resolve("rvda", "2020-06-15")[0] == "none"
    # a delisted / not-live symbol said aloud is not re-aimed at a live neighbour (rule e); LATE is only live from 2021-06
    assert res.resolve("late", "2020-06-15")[0] == "none"
    assert "late" in idx.known and "late" not in idx.live_map("2020-06-15") and "late" in idx.live_map("2021-07-01")
    # an adjacent swap is one edit
    assert CAP.osa("tvix", "tivx", 1) == 1 and CAP.osa("tvix", "twix", 1) == 1 and CAP.osa("abc", "xyz", 1) == 2


def test_a_symbol_of_the_lexicon_on_any_date_is_never_re_aimed_at_a_live_neighbour():
    """Review F5 (rule e): LATE exists in the lexicon but is not live on the date; LATS IS live one edit away. Saying 'late' must stay 'none'."""
    idx = index_of(lex=dict(LEX, LATS=FAR))
    res = CAP.AliasResolver(idx)
    assert [k for k, _ in res.candidates("late")] == ["lats"] and "lats" in idx.live_map("2020-06-15")      # the neighbour IS a candidate, and live
    assert res.resolve("late", "2020-06-15")[0] == "none"                                                   # but the word is a known symbol: not re-aimed
    assert res.resolve("latd", "2020-06-15")[:3] == ("alias", "LATS", 1)                                    # an unknown word one edit from it IS


def test_no_bars_table_is_the_plans_four_funds_only():
    """Review F7: the delisted names of his panel are not in the market-wide search set."""
    assert CAP.NO_BARS_SYMBOLS == ("GBTC", "ETHE", "FNGU", "TVIX")


def test_search_set_is_market_wide_dated_and_sealed():
    idx = index_of(common=("play",))
    live20 = idx.live_map("2020-06-15")
    assert live20["tqqq"] == (("TQQQ",), "strong") and live20["boil"][1] == "weak" and live20["spy"][1] == "weak"
    assert "late" not in live20                                       # not live yet
    assert "has" not in live20                                        # a connective is never a ticker mention
    assert live20["tvix"] == (("TVIX",), "strong")                    # the no-bars table is always in
    assert idx.live_map("2019-01-02")["tvix"] == (("TVIX",), "strong")
    # the panel symbol FB is said in 2020 although the lexicon carries it only from 2021-09: through the alias map (target META live)
    assert live20["fb"] == (("FB",), "strong")
    assert "fb" in idx.live_map("2022-01-03")
    # single letters / numeric keys are not mentions
    lex2 = dict(LEX, A=FAR, **{"1234": FAR})
    idx2 = index_of(lex=lex2)
    assert "a" not in idx2.live_map("2020-06-15") and "1234" not in idx2.live_map("2020-06-15")
    with pytest.raises(C.GuardStop):
        idx.live_map("2025-01-02")                                    # the seal


def test_english_word_is_never_an_alias_and_classes():
    idx = index_of(common=("play",))
    w = idx.words
    assert w.klass("the") == "common" and w.klass("uh") == "common" and w.klass("play") == "common"       # connective / filler / said everywhere
    assert w.klass("gosh") == "dict" and w.klass("cash") == "dict" and w.klass("boiled") == "dict"        # a plain stem + ed
    assert w.klass("has") == "common"                                  # connectives carry the function words the 1934 list lacks
    assert w.klass("tvix") == "other" and w.klass("tqqq") == "other" and w.klass("ab2") == "other"
    assert w.klass("buying") == "other"                                # not in this fixture dictionary (the real lists carry the stem)
    assert CAP.Words(DICT | {"buy"}, CONN).klass("buying") == "dict" and CAP.Words(DICT | {"hop"}, CONN).klass("hopped") == "dict"
    # an alias source must be 'other': a statement near 'gosh' (GUSH live) gets NO alias hit, near 'gusj' it does
    for tok, expect in (("gosh", False), ("gusj", True)):
        v = mkvideo("v1", "20200615", speech(f"uh i bought {tok} at ten") + [(30.0, "end")])
        st = CAP.Stream(v, "2020-06-15", "2020-06-15", False)
        stmts = CAP.wide_statements(v)
        CAP.annotate_stream(st, stmts, idx, CAP.AliasResolver(idx), {}, {}, collections.Counter(), collections.Counter())
        assert any(h[2] == "alias" for s in stmts for h in s["hits"]) is expect


def test_corpus_common_is_document_frequency():
    vids = [mkvideo(f"v{i}", "20200615", speech(w)) for i, w in enumerate(["play riot", "play riot riot", "play", "play boil"])]
    assert CAP.corpus_common(vids, 0.5) == {"play", "riot"}              # play in 4 of 4 streams, riot in 2 of 4 (exactly half is in)
    assert CAP.corpus_common(vids, 0.51) == {"play"}                     # boil in 1 of 4 is never common
    assert CAP.corpus_counts(vids)["riot"] == 3


def test_wordlist_loader_and_missing_file(tmp_path):
    a, b = tmp_path / "web2", tmp_path / "connectives"
    a.write_text("Zoom\nBoil\nx-ray\nPlay\n")
    b.write_text("the\nof\n")
    words, conn, shas = CAP.load_wordlists((str(a), str(b)))
    assert words == {"zoom", "boil", "play"} and conn == {"the", "of"} and set(shas) == {str(a), str(b)}
    with pytest.raises(FileNotFoundError):
        CAP.load_wordlists((str(tmp_path / "nope"),))


# ═════════════════════════════════════════════════════════════════════════════════════════════ the statement kinds
def kinds_of(text: str) -> list:
    v = mkvideo("vk", "20200615", speech(text))
    return [s["kinds_in_cluster"] for s in CAP.wide_statements(v)]


def test_kinds_include_short_and_cover_and_exclude_the_noise():
    assert "shorted" in kinds_of("so i shorted it yesterday near the highs")[0]
    assert "shorted" in kinds_of("honestly i'm short here")[0] and "shorted" in kinds_of("i'm still short this thing")[0]
    assert "shorted" in kinds_of("then i went short on the break")[0] and "shorted" in kinds_of("you could short it here")[0]
    assert "covered" in kinds_of("i covered most of it this morning")[0]
    assert "covered" in kinds_of("then i bought it back lower")[0]
    assert "covered" in kinds_of("i'm out of my short now")[0]
    # not trades: covered calls, short term, a short squeeze, short interest, 'short on time', the noun
    for noise in ("i sold covered calls on it", "it is a short term trade", "there was a short squeeze today", "the short interest is high",
                  "i'm short on time today", "that is a good short setup"):
        assert not ({"shorted", "covered"} & set(sum((k.split("+") for k in kinds_of(noise)), []))), noise
    # the original engine knows neither kind
    v = mkvideo("vk", "20200615", speech("i shorted it and then i covered it"))
    assert CAP.old_statements(v) == [] and len(CAP.wide_statements(v)) == 1
    # naming: a stop-out of a short stays 'stopped'; 'bought it back' is named 'covered', not 'bought'
    assert CAP.wide_statements(mkvideo("vk", "20200615", speech("i got stopped out of my short")))[0]["kind"] == "stopped"
    assert CAP.wide_statements(mkvideo("vk", "20200615", speech("then i bought it back lower")))[0]["kind"] == "covered"
    assert CAP.WIDE_PRIORITY[:3] == ("stopped", "covered", "shorted") and set(CAP.OLD_PRIORITY) < set(CAP.WIDE_PRIORITY)


def test_copied_engine_equals_the_inventorys_on_a_fixture():
    text = ("good morning i bought some here and i added more then i got stopped out i sold half and took profits my average is forty "
            "my stop is thirty nine i'm out of it all year to date i made a million this year i'm long now i got in i'm buying more")
    v = mkvideo("ve", "20200615", speech(text))
    assert CAP.old_statements(v) == INV.cluster(v, INV.find_matches(v)) and len(CAP.old_statements(v)) >= 2
    # a new match can bridge two old statements: the widened statement OVERLAPS both, none is lost
    v2 = mkvideo("ve2", "20200615", speech("i bought it here and then later i shorted it too and i sold it"))
    old, wide = CAP.old_statements(v2), CAP.wide_statements(v2)
    assert all(any(CAP.overlaps(o, w) for w in wide) for o in old)


# ═════════════════════════════════════════════════════════════════════════════════════════════ stream dates, rolling captions, duplicates
def test_late_upload_stream_dates():
    f = CAP.title_stream_date
    assert f("Late upload: Dec 31 stream", "2021-01-05") == ("2020-12-31", "")                 # the year rolls back
    assert f("Late upload - Friday March 5th", "2021-03-08") == ("2021-03-05", "")
    assert f("Monday March 8th, late upload", "2021-03-09") == ("2021-03-08", "")
    assert f("Late upload - Tuesday March 16", "2021-03-17") == ("2021-03-16", "")
    assert f("Late upload - Monday March 5", "2021-03-08") == ("2021-03-05", "weekday_mismatch:monday")   # 2021-03-05 was a Friday
    assert f("Late upload - sometime", "2021-03-08") == ("2021-03-08", "no_date_in_title")
    assert f("This is yesterdays video", "2020-10-06") == ("2020-10-05", "yesterdays_video")    # corrected to the previous weekday (R48, review F11)
    assert f("This is yesterdays video", "2020-10-12") == ("2020-10-09", "yesterdays_video")    # a Monday upload: the Friday, not the Sunday
    assert f("Late upload - Friday March 5th", "2021-03-08")[1] == ""                          # the yesterday rule never touches a late upload
    assert f("Market in limbo", "2021-02-26") == ("2021-02-26", "")


def test_same_stream_uploaded_twice_is_one_stream():
    a = mkvideo("a", "20210308", speech("hello"), title="Late upload - Friday March 5th", seconds=3907)
    b = mkvideo("b", "20210309", speech("hello"), title="Friday March 5th, late upload", seconds=3907)
    c = mkvideo("c", "20210308", speech("hello"), title="Monday market", seconds=3907)           # an ordinary stream of the same length, other date
    d = mkvideo("d", "20210305", speech("hello"), title="Friday market", seconds=3907)           # the ordinary upload of the stream a repeats
    streams, dropped = CAP.make_streams([a, b, c, d])
    assert sorted(s.v.id for s in streams) == ["c", "d"]                 # the ordinary upload (d) is the stream; both late uploads of it are dropped
    assert sorted(s.v.id for s, _ in dropped) == ["a", "b"]
    # two ordinary streams of equal length on one day are NOT merged (neither is a late upload)
    e = mkvideo("e", "20200601", speech("x"), seconds=100)
    f = mkvideo("f", "20200601", speech("y"), title="other", seconds=100)
    assert len(CAP.make_streams([e, f])[0]) == 2


ROLLING_VTT = "\n".join([        # YouTube's rolling format: every cue repeats the previous line; the real files carry a ONE-SPACE line, so it is built, not typed
    "WEBVTT", "Kind: captions", "Language: en", "",
    "00:00:01.000 --> 00:00:03.000 align:start position:0%", " ", "good<00:00:01.200><c> morning</c><00:00:01.600><c> guys</c>", "",
    "00:00:03.000 --> 00:00:03.010 align:start position:0%", "good morning guys", " ", "",
    "00:00:03.010 --> 00:00:05.000 align:start position:0%", "good morning guys", "i<00:00:03.500><c> bought</c><00:00:04.000><c> tesla</c>", "",
    "00:00:05.000 --> 00:00:05.010 align:start position:0%", "i bought tesla", " ", ""])


def test_rolling_captions_are_deduplicated_and_duplicate_uploads_dropped(tmp_path, monkeypatch):
    p = tmp_path / "x.vtt"
    p.write_text(ROLLING_VTT)
    words = [w for _, w in INV.parse_vtt(str(p))]
    assert words == ["good", "morning", "guys", "i", "bought", "tesla"]                         # each spoken word once, not once per rolling cue
    subs = tmp_path / "subs"
    subs.mkdir()
    for vid in ("aaa", "bbb", "ccc"):
        (subs / f"{vid}.en-orig.vtt").write_text(ROLLING_VTT)
    status = tmp_path / "video_status.tsv"
    status.write_text("id\tseconds\ttitle\tstatus\tupload_date\ttrack\twords\thits\tnote\n"
                      "aaa\t100\tsame\tok\t20200601\ten-orig\t6\t0\t\n"
                      "bbb\t100\tsame\tok\t20200601\ten-orig\t6\t0\t\n"          # the duplicate upload (same date, title, length)
                      "ccc\t100\tother\tok\t20200602\ten-orig\t6\t0\t\n")
    monkeypatch.setattr(INV, "STATUS", str(status))
    monkeypatch.setattr(INV, "SUBS", str(subs))
    rows, ok, vids, dups = INV.load_videos()
    assert len(ok) == 3 and [v.id for v in vids] == ["aaa", "ccc"] and dups == [("bbb", "aaa")]
    assert vids[0].toks == ["good", "morning", "guys", "i", "bought", "tesla"]


# ═════════════════════════════════════════════════════════════════════════════════════════════ hits, strata, flags
def annotated(text_words: list, idx=None, counts=None, date="2020-06-15", upload="20200615"):
    idx = idx or index_of()
    v = mkvideo("vv", upload, text_words)
    stream = CAP.Stream(v, f"{upload[:4]}-{upload[4:6]}-{upload[6:]}", date, False)
    stmts = CAP.wide_statements(v)
    for s in stmts:
        s["stmt_id"] = f"{s['video']}:{s['w0']}"
    CAP.annotate_stream(stream, [s for s in stmts if s["kind"] != "account"], idx, CAP.AliasResolver(idx, counts), {}, {}, collections.Counter(),
                        collections.Counter())
    return stmts, v


def test_filter_window_is_30_seconds_from_the_matched_words():
    near = speech("i bought riot", 100.0) + [(120.0, "tqqq")]                       # tqqq 20 s after the statement's last word
    far = speech("i bought riot", 100.0) + [(140.0, "tqqq")]                         # 40 s after
    s_near = annotated(near)[0][0]
    s_far = annotated(far)[0][0]
    assert any(h[0] == "tqqq" for h in s_near["hits"]) and not any(h[0] == "tqqq" for h in s_far["hits"])
    before = [(60.0, "tqqq")] + speech("i bought riot", 100.0)                       # 40 s before the first matched word: out; 25 s: in
    assert not any(h[0] == "tqqq" for h in annotated(before)[0][0]["hits"])
    before2 = [(75.0, "tqqq")] + speech("i bought riot", 100.0)
    assert any(h[0] == "tqqq" for h in annotated(before2)[0][0]["hits"])


def test_strata_weak_near_far_and_ambiguous():
    idx = index_of()
    # S1: a strong symbol; S2: a dictionary-word symbol within 12 words; S4: the same 13+ words away but inside 30 s; S3: a tied garble
    s1 = annotated(speech("i bought tqqq at ten"))[0][0]
    s2 = annotated(speech("i bought boil at ten"))[0][0]
    filler = " ".join(["word"] * 20)
    s4 = annotated(speech(f"i bought it {filler} boil"))[0][0]
    s3 = annotated(speech("i bought tqq at ten"))[0][0]
    assert [CAP.stratum_of(s) for s in (s1, s2, s4, s3)] == ["S1", "S2", "S4", "S3"]
    assert {h[2] for h in s2["hits"]} == {"weak_near"} and {h[2] for h in s4["hits"]} == {"weak"}
    assert s3["hits"][0][2] == "amb" and set(s3["hits"][0][1].split(";")) == {"TQQQ", "THQ"}
    assert all(CAP.in_filter(s) for s in (s1, s2, s3, s4)) and not CAP.in_filter(s4, ("strong", "alias"))
    # a statement with no symbol within 30 s is not in the set; an 'account' statement never is
    nohit = annotated(speech("i bought it at ten"))[0][0]
    assert not CAP.in_filter(nohit) and CAP.stratum_of(nohit) == ""
    assert not CAP.in_filter({"kind": "account", "hits": [("tqqq", "TQQQ", "strong", 0)]})
    # the join reads the precise symbols only and splits a tied set
    assert CAP.hit_symbols(s1) == ["TQQQ"] and CAP.hit_symbols(s2) == ["BOIL"] and CAP.hit_symbols(s3) == [] and sorted(CAP.hit_symbols(s3, ("amb",))) == ["THQ", "TQQQ"]


def test_alias_log_keeps_the_stretch_it_was_heard_in():
    idx = index_of()
    v = mkvideo("vv", "20200615", speech("uh so i bought nvidia at forty two fifty"))
    stream = CAP.Stream(v, "2020-06-15", "2020-06-15", False)
    stmts = CAP.wide_statements(v)
    alog = {}
    CAP.annotate_stream(stream, stmts, idx, CAP.AliasResolver(idx), alog, {}, collections.Counter(), collections.Counter())
    assert list(alog) == [("nvidia", "NVDA")] and alog[("nvidia", "NVDA")].n == 1
    assert "nvidia at forty two fifty" in alog[("nvidia", "NVDA")].evidence[0] and alog[("nvidia", "NVDA")].evidence[0].startswith("vv@")


def test_price_tier_and_other_flags():
    f = lambda t: CAP.flags_of(t)["price_candidate"]
    assert f("i bought it at $4.90 yesterday") and f("bought at 42.50") and f("sold at forty two") and f("it was four and a half")
    assert f("i got in at 40 dollars") and f("bought in the 490s") and f("stopped at thirty nine bucks")
    assert not f("i sold at 930 am") and not f("i bought at 10 minutes in") and not f("i bought some more") and not f("i sold half at 5 percent")
    assert CAP.flags_of("stopped out yesterday")["day_words"] and not CAP.flags_of("stopped out")["day_words"]
    stmts, _ = annotated(speech("i bought tqqq at $4.90"))
    assert stmts[0]["price_candidate"] is True
    both, _ = annotated(speech("i bought tqqq 20 thousand shares and lost 180k on it"))
    assert both[0]["shares"] and both[0]["dollar_result"]


def test_machine_pass_hand_read_set_blind_pool_and_account_kind():
    idx = index_of()
    res = CAP.AliasResolver(idx)
    pad = lambda t0: speech(" ".join(["zzz"] * 20), t0)                                      # 20 words apart: the clusters split on WORDS, not on seconds
    v1 = mkvideo("s1", "20200615", speech("i bought tqqq at $4.90") + pad(10.0) + speech("then i sold it", 200.0) + pad(210.0) +
                 speech("my account is up 50 percent this year", 400.0))
    v2 = mkvideo("s2", "20250615", speech("i bought tqqq"))                                    # outside the primary span (and after the seal: not annotated)
    s1 = CAP.Stream(v1, "2020-06-15", "2020-06-15", False)
    s2 = CAP.Stream(v2, "2022-12-01", "2022-12-01", False)                                    # a stream date outside the span
    out = CAP.machine_pass([s1, s2], idx, res)
    kinds = collections.Counter(s["kind"] for s in out["primary"])
    assert kinds["account"] == 1 and out["primary"] and all(CAP.in_span(s["stream_date"]) for s in out["primary"])
    assert [s["kind"] for s in out["handread"]] == ["bought"] and out["handread"][0]["price_candidate"] is True
    assert [s["kind"] for s in out["blind_pool"]] == ["sold"]                                  # no symbol within 30 s; the account statement is not in the pool
    assert out["handread"][0]["stmt_id"].startswith("s1:") and len(out["all"]) == 4


# ═════════════════════════════════════════════════════════════════════════════════════════════ the join
def win(eid, side, sym, lo, hi):
    return (eid, side, sym, lo, hi)


def sessions():
    import datetime as dt
    d, out = dt.date(2020, 5, 1), []
    while d <= dt.date(2020, 7, 31):
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return C.Sessions(out)


def test_join_nearest_window_of_either_side_within_one_session():
    S = sessions()
    by_sym = CAP.index_windows([win(1, "buy", "XYZ", "2020-06-08", "2020-06-10"), win(1, "sale", "XYZ", "2020-06-17", "2020-06-18"),
                                win(2, "buy", "XYZ", "2020-06-24", "2020-06-24"), win(3, "buy", "OTH", "2020-06-08", "2020-06-08")])
    j = CAP.join_position("XYZ", "2020-06-09", by_sym, S)                                   # inside the first buy window
    assert (j["status"], j["eid"], j["side"], j["dist"]) == ("unique", 1, "buy", 0)
    j = CAP.join_position("XYZ", "2020-06-11", by_sym, S)                                   # the session after it ends ('yesterday')
    assert (j["status"], j["eid"], j["side"], j["dist"]) == ("unique", 1, "buy", 1)
    assert CAP.join_position("XYZ", "2020-06-12", by_sym, S)["status"] == "none"            # two sessions after
    j = CAP.join_position("XYZ", "2020-06-16", by_sym, S)                                   # a session BEFORE the sale window
    assert (j["eid"], j["side"], j["dist"]) == (1, "sale", 1)
    j = CAP.join_position("XYZ", "2020-06-20", by_sym, S)                                   # a Saturday: the last session (the 19th) is 1 after the sale
    assert (j["eid"], j["side"], j["dist"]) == (1, "sale", 1)
    assert CAP.join_position("NOPE", "2020-06-09", by_sym, S)["status"] == "none"
    # a name with several positions takes the nearest: the 24th belongs to position 2, not the sale of position 1
    j = CAP.join_position("XYZ", "2020-06-24", by_sym, S)
    assert (j["eid"], j["side"], j["dist"]) == (2, "buy", 0)
    # a tie at the nearest distance (the buy of one position and the sale of another, both containing the day) is ambiguous, not resolved
    tie = CAP.index_windows([win(1, "buy", "XYZ", "2020-06-08", "2020-06-10"), win(2, "sale", "XYZ", "2020-06-09", "2020-06-09")])
    jt = CAP.join_position("XYZ", "2020-06-09", tie, S)
    assert jt["status"] == "ambiguous" and jt["n"] == 2 and jt["eid"] == "" and jt["side"] == "" and set(jt["tied"].split(";")) == {"1:buy", "2:sale"}
    assert not CAP.tie_is_one_position(jt)
    # review F2: ONE position's buy and sale on the same session tie too; the tie names no side (a sort would always have said 'buy')
    day = CAP.index_windows([win(5, "buy", "XYZ", "2020-06-09", "2020-06-09"), win(5, "sale", "XYZ", "2020-06-09", "2020-06-09")])
    jd = CAP.join_position("XYZ", "2020-06-09", day, S)
    assert jd["status"] == "ambiguous" and jd["eid"] == "" and jd["side"] == "" and CAP.tie_is_one_position(jd)
    assert CAP.join_position("XYZ", "2020-06-09", by_sym, S)["tied"] == "1:buy"          # a unique join still names its window


def test_none_reasons_inside_a_hold_other_date_and_not_on_the_panel():
    """Review F3: a day between a position's first and last window is HELD, not an invisible trade."""
    S = sessions()
    wins = [win(1, "buy", "XYZ", "2020-06-08", "2020-06-08"), win(1, "sale", "XYZ", "2020-06-17", "2020-06-17"),
            win(2, "buy", "ONLY", "2020-06-08", "2020-06-08")]                              # ONLY: an open position (no sale window)
    by_sym, holds = CAP.index_windows(wins), CAP.index_holds(wins)
    assert holds["XYZ"] == [(1, "2020-06-08", "2020-06-17")] and "ONLY" not in holds
    assert CAP.join_position("XYZ", "2020-06-12", by_sym, S)["status"] == "none"
    assert CAP.none_reason("XYZ", "2020-06-12", by_sym, holds, S) == "inside_hold"
    assert CAP.none_reason("XYZ", "2020-07-01", by_sym, holds, S) == "other_date"           # after the sale
    assert CAP.none_reason("XYZ", "2020-05-20", by_sym, holds, S) == "other_date"           # before the buy
    assert CAP.none_reason("ONLY", "2020-06-12", by_sym, holds, S) == "other_date"          # an open position is not called held (stricter)
    assert CAP.none_reason("NEVER", "2020-06-12", by_sym, holds, S) == "not_on_panel"
    # the best of several symbols: a join beats a none, and the none nearest a window wins
    assert CAP.best_join(["NEVER", "XYZ"], "2020-06-12", by_sym, holds, S)["reason"] == "inside_hold"
    b = CAP.best_join(["NEVER", "XYZ"], "2020-06-09", by_sym, holds, S)
    assert b["status"] == "unique" and b["symbol"] == "XYZ" and b["reason"] == ""


def test_join_never_uses_the_action_or_a_price():
    S = sessions()
    by_sym = CAP.index_windows([win(1, "buy", "XYZ", "2020-06-08", "2020-06-10")])
    assert list(inspect.signature(CAP.join_position).parameters) == ["symbol", "day", "by_sym", "S"]
    # a 'sold' statement lands on a BUY window: the join does not know the action (R5 counts it a miss later)
    assert CAP.join_position("XYZ", "2020-06-09", by_sym, S)["side"] == "buy"
    src = inspect.getsource(CAP.join_position)  # source-pin-ok: the plan forbids the join to read the action or a price; the body must name neither
    tree = ast.parse(src)
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.arg for n in ast.walk(tree) if isinstance(n, ast.arg)} | \
           {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not [u for u in used if "action" in u.lower() or "price" in u.lower() or "kind" in u.lower()]


# ═════════════════════════════════════════════════════════════════════════════════════════════ the sheets
def fixture_statements(n: int = 640, with_price: int = 120):
    sts = []
    for k in range(n):
        v = mkvideo(f"v{k:04d}", "20200615", speech("i bought tqqq at 40" if k < with_price else "i sold boil", 0.0))
        s = CAP.wide_statements(v)[0]
        s.update(stmt_id=f"{v.id}:{s['w0']}", stream_date="2020-06-15", hits=[("tqqq", "TQQQ", "strong", 0)] if k % 2 == 0 else [("boil", "BOIL", "weak_near", 0)],
                 price_candidate=k < with_price, shares=False, dollar_result=False, day_words=False)
        sts.append((s, v))
    return sts


def test_sheet_rows_carry_captions_only():
    (s, v), = fixture_statements(1)
    row = CAP.sheet_row("A0001", s, v)
    assert set(row) == set(CAP.SHEET_COLS) and all(row[c] == "" for c in CAP.SHEET_LABEL_COLS)
    assert "tqqq" in row["context"] and "<<" in row["context"] and "\n" not in row["context"]
    # no window / bar / price / hint of ours: the data columns avoid every banned stem, the layout rejects anything outside it
    for c in CAP.SHEET_DATA_COLS:
        assert not any(b in c for b in CAP.SHEET_BANNED_STEMS), c
    CAP.assert_sheet_columns(CAP.SHEET_COLS)
    for bad in ("eid", "range_lo", "price_raw", "panel_price", "window", "bracket", "symbols", "hits", "alias", "stratum"):
        with pytest.raises(CAP.GuardStop):
            CAP.assert_sheet_columns(CAP.SHEET_COLS + [bad])
    assert "symbols" not in row and "hits" not in row and "stratum" not in row
    # the reader's own readings of the words (price_stated / price_value ...) are label columns, blank on the sheet
    assert {"price_stated", "price_value", "price_garbled", "price_kind", "shares", "dollar_result", "side"} <= set(CAP.SHEET_LABEL_COLS)


def test_sheet_plan_order_batches_and_seeded_draws():
    sts = fixture_statements()
    videos = {v.id: v for _, v in sts}
    hand = [s for s, _ in sts]
    # blind pool: statements with no hit
    pool = []
    for k in range(300):
        v = mkvideo(f"p{k:04d}", "20200615", speech("i sold it"))
        s = CAP.wide_statements(v)[0]
        s.update(stmt_id=f"{v.id}:{s['w0']}", stream_date="2020-06-15", hits=[], price_candidate=False, shares=False, dollar_result=False, day_words=False)
        pool.append(s)
        videos[v.id] = v
    plan = CAP.build_sheet_plan(hand, pool, videos)
    names = list(plan)
    assert names[0] == "reader1_t1_price" and len(plan[names[0]]) == 120 and all(r["price_candidate"] == "Y" for r in plan[names[0]])
    rest = [n for n in names if n.startswith("reader1_rest")]
    assert rest == ["reader1_rest_b01", "reader1_rest_b02"] and all(len(plan[n]) <= CAP.BATCH_ROWS for n in rest)       # review F10: neutral names
    assert sum(len(plan[n]) for n in rest) == 520
    assert all(r["sid"][0] in "ABRN" and r["sid"][1:].isdigit() for rs in plan.values() for r in rs)               # neutral ids: no S1..S4 prefix
    strata_of = {s["stmt_id"]: CAP.stratum_of(s) for s in hand}
    man = {m["sheet"]: m for m in CAP.sheet_manifest(plan, strata_of)}
    assert man["reader1_rest_b01"]["strata"] == "S1:260" and man["reader1_rest_b02"]["strata"] == "S2:260"       # a batch never straddles two strata
    assert man["reader2_nosymbol_200"]["strata"] == "blind:200" and man["reader1_t1_price"]["rows"] == 120
    assert "S1" not in " ".join(list(plan) + [r["sid"] for rs in plan.values() for r in rs])                     # the stratum is NOT on the page or in a name
    r2 = plan["reader2_150"]
    assert len(r2) == 150 and sum(r["price_candidate"] == "Y" for r in r2) == 100 and sum(r["price_candidate"] == "N" for r in r2) == 50
    blind = plan["reader2_nosymbol_200"]
    assert len(blind) == 200 and {r["stmt_id"] for r in blind} <= {s["stmt_id"] for s in pool}
    # seeded and reproducible; a different key gives a different draw; the ids are the sheet's own
    again = CAP.build_sheet_plan(hand, pool, videos)
    assert [r["stmt_id"] for r in again["reader2_150"]] == [r["stmt_id"] for r in r2] and [r["sid"] for r in r2] == [f"R{k:03d}" for k in range(1, 151)]
    assert [s["stmt_id"] for s in CAP.draw(pool, 50, "asis_6a_other_key")] != [s["stmt_id"] for s in CAP.draw(pool, 50, "asis_6a_nosymbol_200")]
    assert len(CAP.draw(pool[:7], 50, "k")) == 7                                            # a pool smaller than the draw is taken whole
    assert {r["stmt_id"] for r in r2} <= {s["stmt_id"] for s in hand}


def test_write_sheet_refuses_to_overwrite_a_labelled_sheet(tmp_path):
    (s, v), = fixture_statements(1)
    rows = [CAP.sheet_row("A0001", s, v)]
    p = tmp_path / "sheets" / "x.tsv"
    CAP.write_sheet(str(p), rows)
    CAP.write_sheet(str(p), rows)                                                          # blank: redrawing is fine
    back = CAP.read_sheet(str(p))
    assert back[0]["stmt_id"] == rows[0]["stmt_id"] and back[0]["ticker_ident"] == ""
    back[0]["his_trade"] = "Y"
    p.write_text(CAP.tsv_text(back, CAP.SHEET_COLS))
    with pytest.raises(CAP.GuardStop):
        CAP.write_sheet(str(p), rows)


def test_forbidden_folder_and_seal_guards_apply_to_this_module(tmp_path):
    with pytest.raises(C.GuardStop):
        CAP.read_sheet(C.FORBIDDEN_DIRS[0] + "/x.tsv")
    with pytest.raises(C.GuardStop):
        C.seal_date("2025-01-02")
    v = mkvideo("vs", "20250102", speech("i bought it"))
    with pytest.raises(C.GuardStop):
        CAP.make_streams([v])                                                              # a stream dated after the seal is refused


# ═════════════════════════════════════════════════════════════════════════════════════════════ the agreement score
def lab(sid, ticker="TSLA", ident="Y", own="Y", action="buy", day="stream_day", price="", garbled="N"):
    return {"stmt_id": sid, "sid": sid, "ticker_ident": ident, "ticker": ticker, "his_trade": own, "action": action, "date_pinnable": day,
            "price_stated": "Y" if price else "N", "price_value": price, "price_garbled": garbled}


def test_agreement_scorer_on_fixture_labels():
    r1 = [lab(f"s{k}", price="42.50" if k < 7 else "") for k in range(10)]
    r2 = [dict(r) for r in r1]
    res = CAP.score_agreement(r1, r2)
    assert res["n"] == 10 and res["joint_rate"] == 1.0 and res["price_n"] == 7 and res["price_rate"] == 1.0 and res["joint_pass"] and res["price_pass"]
    # 8 of 10 agree on the joint label: exactly the bar (80%); 7 of 10 is below it
    r2b = [dict(r) for r in r1]
    r2b[0]["action"], r2b[1]["ticker"] = "sell_all", "NVDA"
    assert CAP.score_agreement(r1, r2b)["joint_rate"] == 0.8 and CAP.score_agreement(r1, r2b)["joint_pass"]
    r2c = [dict(r) for r in r2b]
    r2c[2]["date_pinnable"] = "unstated"
    rc = CAP.score_agreement(r1, r2c)
    assert rc["joint_rate"] == 0.7 and not rc["joint_pass"] and len(rc["disagreements"]) == 3
    assert rc["disagreements"][0][2] == ("TSLA", "buy", "stream_day") and rc["disagreements"][0][3] == ("TSLA", "sell_all", "stream_day")
    # the price bar: 6 of 7 agreeing (85.7%) passes; 5 of 7 (71%) does not; 42.5 and 42.50 are the same number
    r2d = [dict(r) for r in r1]
    r2d[0]["price_value"] = "42.5"
    r2d[1]["price_value"] = "4.25"
    assert CAP.score_agreement(r1, r2d)["price_ok"] == 6 and CAP.score_agreement(r1, r2d)["price_pass"]
    r2d[2]["price_value"] = "52.50"
    assert CAP.score_agreement(r1, r2d)["price_ok"] == 5 and not CAP.score_agreement(r1, r2d)["price_pass"]
    # a row both call 'not his own trade' agrees whatever the reason; a row one calls his own and the other advice does not
    a, b = [lab("x1", own="advice", action="none")], [lab("x1", own="viewer", action="none")]
    assert CAP.score_agreement(a, b)["joint_rate"] == 1.0
    assert CAP.score_agreement([lab("x2")], [lab("x2", own="advice", action="none")])["joint_rate"] == 0.0
    # unlabelled rows are set aside (listed), rows missing from reader 1 are listed, nothing is silently scored
    r2e = [dict(r) for r in r1] + [lab("zz")]
    r2e[3]["action"] = ""
    re_ = CAP.score_agreement(r1, r2e)
    assert re_["n"] == 9 and re_["unlabelled"] == ["s3"] and re_["not_in_reader1"] == ["zz"]
    # a row marked 'advice' with the action and the day left BLANK is read (not set aside): action / day are required only for his own trade
    blank = lambda sid, own: {**lab(sid, own=own), "action": "", "date_pinnable": ""}
    assert CAP.score_agreement([blank("b1", "advice")], [blank("b1", "viewer")])["n"] == 1
    assert CAP.score_agreement([blank("b2", "Y")], [blank("b2", "Y")])["n"] == 0 and CAP.score_agreement([blank("b2", "Y")], [blank("b2", "Y")])["unlabelled"] == ["b2"]
    # an unidentified ticker is one label on both sides
    u1, u2 = [lab("u", ident="N", ticker="")], [lab("u", ident="amb", ticker="")]
    assert CAP.score_agreement(u1, u2)["joint_rate"] == 1.0
    assert CAP.norm_ticker('TVIX? (unresolved "this thing")') == "TVIX" and CAP.norm_ticker("$tsla long") == "TSLA" and CAP.norm_ticker("") == ""
    assert CAP.parse_price("~4.90s") == 4.9 and CAP.parse_price("1,250") == 1250.0 and CAP.parse_price("") is None


def test_no_row_with_two_prices_is_not_a_price_pass():
    """Review F8: the price bar passes vacuously when no row has both readers' prices; it must read 'not testable', never AGREEMENT PASS."""
    r1 = [lab(f"s{k}") for k in range(10)]
    res = CAP.score_agreement(r1, [dict(r) for r in r1])
    assert res["joint_pass"] and res["price_n"] == 0 and res["price_testable"] is False and res["price_pass"] is False
    say = CAP.Say()
    CAP.agreement_report(say, res, None)
    text = "\n".join(say.lines)
    assert "AGREEMENT PASS" not in text.replace("NOT an agreement pass", "") and "NOT TESTABLE" in text
    # a small count is noted, and a real pass still prints
    r1p = [lab(f"p{k}", price="42.50" if k < 2 else "") for k in range(10)]
    resp = CAP.score_agreement(r1p, [dict(r) for r in r1p])
    say2 = CAP.Say()
    CAP.agreement_report(say2, resp, None)
    t2 = "\n".join(say2.lines)
    assert resp["price_testable"] and resp["price_pass"] and "only 2 row" in t2 and t2.rstrip().endswith("AGREEMENT PASS")


def test_blind_spot_estimate_and_report(capsys):
    rows = [lab(f"n{k}", own="Y" if k < 30 else "other", action="buy" if k < 30 else "none", ident="Y" if k < 20 else "N") for k in range(200)]
    bs = CAP.blind_spot(rows)
    assert bs["n"] == 200 and bs["own_event"] == 30 and bs["share"] == 0.15 and bs["lo"] < 0.15 < bs["hi"] and bs["own_unidentified"] == 10
    say = CAP.Say()
    CAP.agreement_report(say, CAP.score_agreement([lab("a")], [lab("a", action="sell_all")]), bs)
    text = "\n".join(say.lines)
    assert "BELOW THE BAR" in text and "blind sample" in text and "disagreements (1)" in text


def test_claims_result_line():
    say = CAP.Say()
    cl = CAP.Claims(say)
    cl("a", 1, 1)
    cl("b", 2, 3)
    assert cl.result() == "RESULT: 2 claims, 1 OK, 1 MISMATCH"


# ═════════════════════════════════════════════════════════════════════════════════════════════ the guards
def test_step6a_module_scans_clean_and_planted_name_fails(tmp_path):
    # source-pin-ok: the plan's guard (3) IS a scan of the step-5/6 source text; 02_captions.py must hold none of the excluded names
    assert C.scan_identifiers([str(ASIS / "02_captions.py")]) == []
    planted = tmp_path / "planted.py"
    planted.write_text("for E in range(3):\n    x = 'pivot'\n")
    assert [t for _p, _l, t in C.scan_identifiers([str(planted)])] == ["E", "'pivot'"]
    ok = tmp_path / "ok.py"
    ok.write_text("average = 1\nS1 = 'S1'\nstratum = {'S4': 2}\n")
    assert C.scan_identifiers([str(ok)]) == []


def _fresh_import_report(module_path: Path, prelude: str = "") -> list:
    code = (
        "import importlib.util, sys, json\n"
        f"{prelude}\n"
        f"spec = importlib.util.spec_from_file_location('asis_captions02', {str(module_path)!r})\n"
        "m = importlib.util.module_from_spec(spec); sys.modules['asis_captions02'] = m; spec.loader.exec_module(m)\n"
        "print(json.dumps(m.C.rule_modules_loaded()))\n"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, cwd=str(REPO))
    assert r.returncode == 0, r.stderr
    import json
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_fresh_interpreter_import_of_02_captions_holds_no_rule_module(tmp_path):
    assert _fresh_import_report(ASIS / "02_captions.py") == []
    stub_dir = tmp_path / "_705_intraday_1025"
    stub_dir.mkdir()
    (stub_dir / "01_intra.py").write_text("PLANTED = True\n")
    prelude = (f"spec2 = importlib.util.spec_from_file_location('intra01_planted', {str(stub_dir / '01_intra.py')!r})\n"
               "m2 = importlib.util.module_from_spec(spec2); sys.modules['intra01_planted'] = m2; spec2.loader.exec_module(m2)")
    assert _fresh_import_report(ASIS / "02_captions.py", prelude) == ["intra01_planted"]


def test_no_network_model_client_or_rule_import_in_02_captions():
    tree = ast.parse((ASIS / "02_captions.py").read_text(encoding="utf-8"))  # source-pin-ok: guards (4) and (5): no socket, no model client, no rule import may enter this module
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    assert not (mods & {"socket", "requests", "urllib", "http", "anthropic", "openai", "psycopg2", "sqlalchemy", "random", "subprocess"})
    assert not [m for m in mods if m.startswith("_705") or m == "_cb_backtest"]


def test_no_absolute_machine_path_in_this_test_file():
    text = Path(__file__).read_text(encoding="utf-8")
    assert "/Users" + "/" not in text


# ═════════════════════════════════════════════════════════════════════════════════════════════ the --sheets gate (review F1)
def test_sheets_gate_refuses_until_the_dry_run_and_the_pins_are_in_order(tmp_path, monkeypatch):
    sheets = tmp_path / "sheets"
    monkeypatch.setattr(CAP, "P_DRY", str(tmp_path / "dry.txt"))
    monkeypatch.setattr(CAP, "P_RUN", str(tmp_path / "run.txt"))
    monkeypatch.setattr(CAP, "SHEETS_DIR", str(sheets))
    monkeypatch.setattr(CAP, "OUT_FILES", {k: str(tmp_path / f"{k}.tsv") for k in CAP.OUT_FILES})
    monkeypatch.setattr(C, "LEDGER", str(tmp_path / "ledger.tsv"))
    doc = tmp_path / "doc.md"
    doc.write_text("# body\n\n<!-- FREEZE -->\n")
    problems = CAP.sheets_gate(str(doc))
    assert any("not completed" in x for x in problems) and any("pins not below" in x for x in problems)
    (tmp_path / "dry.txt").write_text("stuff\nRESULT: 3 claims, 2 OK, 1 MISMATCH\nDRY RUN COMPLETE\n")
    assert any("1 MISMATCH" in x for x in CAP.sheets_gate(str(doc)))
    (tmp_path / "dry.txt").write_text("stuff\nRESULT: 3 claims, 3 OK, 0 MISMATCH\nDRY RUN COMPLETE\n")
    assert any("other code than the modules" in x for x in CAP.sheets_gate(str(doc)))                # no module line
    (tmp_path / "dry.txt").write_text(f"stuff\n- modules: {CAP.module_shas_line()}x\nRESULT: 3 claims, 3 OK, 0 MISMATCH\nDRY RUN COMPLETE\n")
    assert any("other code than the modules" in x for x in CAP.sheets_gate(str(doc)))                # a different sha
    (tmp_path / "dry.txt").write_text(f"stuff\n- modules: {CAP.module_shas_line()}\nRESULT: 3 claims, 3 OK, 0 MISMATCH\nDRY RUN COMPLETE\n")
    assert CAP.dry_modules_line() == CAP.module_shas_line() and CAP.dry_mismatches() == 0
    # the module line names 01_points.py (load_windows executes it) and the pins name this module, the word lists and this stage's printout
    assert "01_points.py" in CAP.module_shas_line() and "02_captions.py" in CAP.module_shas_line()
    pins = CAP.pins_6a(str(doc))
    assert {"02_captions.py", "01_points.py", "asis_common.py", "dryrun6a_printout", "dict_web2", "doc_body", "captions_inventory.py"} <= set(pins)
    assert pins["dryrun6a_printout"] == C.sha(str(tmp_path / "dry.txt"))
    with open(doc, "a") as fh:
        fh.write("\n".join(f"- {k}: `{v}`" for k, v in pins.items()) + "\n")
    assert CAP.sheets_gate(str(doc)) == []
    # a sheet already present, a side file, or an edit ABOVE the marker refuses again
    sheets.mkdir()
    (sheets / "reader1_t1_price.tsv").write_text("x\n")
    assert any("outputs exist" in x for x in CAP.sheets_gate(str(doc)))
    (sheets / "reader1_t1_price.tsv").unlink()
    (tmp_path / "joins.tsv").write_text("x\n")
    assert any("outputs exist" in x for x in CAP.sheets_gate(str(doc)))
    (tmp_path / "joins.tsv").unlink()
    assert CAP.sheets_gate(str(doc)) == []
    doc.write_text(doc.read_text().replace("# body", "# body edited"))
    assert any("doc_body" in x for x in CAP.sheets_gate(str(doc)))
    # a dry run whose printout is changed after its pin was pasted is refused
    doc.write_text(doc.read_text().replace("# body edited", "# body"))
    (tmp_path / "dry.txt").write_text(f"stuff2\n- modules: {CAP.module_shas_line()}\nRESULT: 3 claims, 3 OK, 0 MISMATCH\nDRY RUN COMPLETE\n")
    assert any("dryrun6a_printout" in x for x in CAP.sheets_gate(str(doc)))
    assert CAP.dry_mismatches(str(tmp_path / "absent.txt")) is None and CAP.dry_modules_line(str(tmp_path / "absent.txt")) is None


def test_sheets_stage_writes_sheets_manifest_side_files_and_ledger_rows_on_a_fixture(tmp_path, monkeypatch):
    """The irreversible --sheets path end to end on synthetic data: the gate is stubbed OPEN, the machine pass is a fixture."""
    sts = fixture_statements(40, with_price=6)
    videos = {v.id: v for _, v in sts}
    hand = [s for s, _ in sts]
    pool = []
    for k in range(30):
        v = mkvideo(f"p{k:04d}", "20200615", speech("i sold it"))
        s = CAP.wide_statements(v)[0]
        s.update(stmt_id=f"{v.id}:{s['w0']}", stream_date="2020-06-15", hits=[], price_candidate=False, shares=False, dollar_result=False, day_words=False)
        pool.append(s)
        videos[v.id] = v
    st = {"streams": [CAP.Stream(v, "2020-06-15", "2020-06-15", False) for v in videos.values()], "handread": hand, "blind_pool": pool,
          "primary": hand + pool, "alias_log": {}, "ambiguous_log": {}}
    out = tmp_path / "out"
    monkeypatch.setattr(CAP, "P_DRY", str(tmp_path / "dry.txt"))
    monkeypatch.setattr(CAP, "P_RUN", str(tmp_path / "run.txt"))
    monkeypatch.setattr(CAP, "P_REFUSED", str(tmp_path / "refused.txt"))
    monkeypatch.setattr(CAP, "SHEETS_DIR", str(out / "sheets"))
    monkeypatch.setattr(CAP, "OUT_FILES", {k: str(out / f"{k}.tsv") for k in CAP.OUT_FILES})
    monkeypatch.setattr(C, "LEDGER", str(tmp_path / "ledger.tsv"))
    monkeypatch.setattr(CAP, "sheets_gate", lambda doc=None: [])
    monkeypatch.setattr(C, "rule_modules_loaded", lambda: [])        # a shared pytest process may hold other tests' modules; the fresh-interpreter test covers the real belt
    monkeypatch.setattr(CAP, "run_machine", lambda say: st)
    monkeypatch.setattr(CAP, "inputs_line", lambda st_: "- input pins: fixture")
    monkeypatch.setattr(CAP, "load_windows", lambda tally=None: ([(1, "buy", "TQQQ", "2020-06-15", "2020-06-15")], sessions()))
    (tmp_path / "dry.txt").write_text("fixture dry run\n")
    assert CAP.main(["--sheets"]) == 0
    names = sorted(p.name for p in (out / "sheets").iterdir())
    assert "reader1_t1_price.tsv" in names and "reader1_rest_b01.tsv" in names and "reader2_150.tsv" in names and "reader2_nosymbol_200.tsv" in names
    assert not [n for n in names if "S1" in n or "S2" in n]                                       # neutral names in the reader folder
    man = CAP.read_sheet(str(out / "sheet_manifest.tsv"))
    assert {m["sheet"] for m in man} == {n[:-4] for n in names} and all(len(m["sha256"]) == 64 for m in man)
    assert any(m["strata"].startswith("S1:") for m in man)                                        # the stratum is in the manifest only
    ms = CAP.read_sheet(str(out / "machine_statements.tsv"))
    assert {"stratum", "reader1_sheet", "reader1_sid"} <= set(ms[0]) and any(r["stratum"] == "S1" and r["reader1_sheet"] for r in ms)
    js = CAP.read_sheet(str(out / "joins.tsv"))
    assert "reason" in js[0] and all(r["status"] in ("unique", "ambiguous", "none") for r in js)
    ledger = [ln.split("\t")[0] for ln in (tmp_path / "ledger.tsv").read_text().splitlines()[1:]]
    assert ledger == ["step6a_dry_run", "step6a_sheets", "step6a_aliases", "step6a_joins", "step6a_machine_statements", "step6a_sheet_manifest"]
    assert C.ledger_verify() == []
    # a refused gate writes the refusal file and never the run printout or a sheet
    monkeypatch.setattr(CAP, "sheets_gate", lambda doc=None: ["a reason"])
    (tmp_path / "run.txt").unlink()
    assert CAP.main(["--sheets"]) == 3 and (tmp_path / "refused.txt").exists() and not (tmp_path / "run.txt").exists()
