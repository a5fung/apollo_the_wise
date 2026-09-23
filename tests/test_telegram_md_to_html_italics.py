"""`_md_to_html` must render italics — it silently didn't (2026-08-02).

Operator: "i see stuff like underscores".

ANY message containing ``` takes the HTML path, because Telegram's legacy Markdown cannot render
code blocks. That converter handled `*bold*` and had **no case for `_italic_`**, so every italic in
every fenced surface — the weekly review, the digests, the crypto board — arrived as literal
underscores. Not a crypto bug; crypto is just where it was noticed.

The intra-word guard is the load-bearing part: without it a stray `_` pair spanning two unrelated
identifiers (`rs_overall` … `mcap_bucket`) would be treated as italic markers and swallow every
character between them.
"""
import re

from channels.telegram import TelegramChannel

_md = TelegramChannel._md_to_html


def test_italics_become_i_tags():
    assert "<i>Alt-season: armed</i>" in _md("_Alt-season: armed_")


def test_bold_still_works():
    assert "<b>Crypto RS</b>" in _md("*Crypto RS*")


def test_bold_and_italic_together():
    out = _md("*🐘 Big caps* _(mega + large)_")
    assert "<b>🐘 Big caps</b>" in out and "<i>(mega + large)</i>" in out


def test_intra_word_underscores_are_left_alone():
    """THE guard. rs_overall and mcap_bucket must not become italic markers that swallow the
    text between them."""
    out = _md("outside rs_overall and mcap_bucket stay literal")
    assert "<i>" not in out
    assert "rs_overall" in out and "mcap_bucket" in out


def test_underscores_inside_code_blocks_are_untouched():
    """BUCK_RS is a column header in the crypto table — it must render verbatim."""
    out = _md("```\n#  SYM  BUCK_RS\n```")
    assert "BUCK_RS" in out and "<i>" not in out
    assert "<pre>" in out


def test_two_separate_italics_do_not_merge():
    out = _md("_a_ and _b_")
    assert out.count("<i>") == 2, "a greedy match would swallow ' and '"


def test_html_special_chars_are_escaped_before_markup():
    """Escaping must precede tag insertion or a <b> would be escaped into text."""
    out = _md("*a < b*")
    assert "&lt;" in out and "<b>" in out


def test_the_real_crypto_board_renders_clean():
    board = ("*Crypto RS*  ·  BTC.D *56.3%*\n\n_Alt-season: armed · TOTAL3 $764B_\n\n"
             "*🐘 Big caps* _(mega + large)_\n```\n#  SYM  BUCK_RS\n1  ETH  65.0\n```\n"
             "_data: 2026-08-02_")
    out = _md(board)
    assert "_Alt-season" not in out, "raw underscore leaked to the operator"
    assert "_data" not in out
    assert out.count("<i>") == 3 and "<pre>" in out
