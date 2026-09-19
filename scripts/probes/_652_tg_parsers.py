"""#652 — local emulation of Telegram's two server-side text parsers.

Telegram parses `parse_mode="Markdown"` (legacy v1) and `parse_mode="HTML"` on its servers
and answers 400 when it cannot; there is no dry-run endpoint, and sending probes to the
operator's chat is not acceptable. So both parsers are ported here from tdlib's
`MessageEntity.cpp` (`parse_markdown` for v1, `parse_html` for HTML) closely enough to
reproduce (a) whether a body 400s, (b) the byte offset Telegram reports, and (c) the plain
text + entity list a successful parse yields.

CREDENTIAL — the v1 port is validated against 178 REAL Telegram verdicts (the
`telegram_markdown_fallback` audit rows, which carry Telegram's own error text and byte
offset); see `_652_render_check.py --validate`. The HTML port has NO prod oracle (zero HTML
400s in 60 days), so it is validated only against tdlib's documented rules.

v1 facts that matter for #652 (all from the tdlib source, all reproduced here):
  * NO nesting — inside `*…*` a `_` is literal; inside `` `…` `` a `*` is literal.
  * NO word boundary — `snake_case_name` opens italic at the first `_`. Odd count → 400.
  * An entity may span newlines (`*a\\nb*` is bold across the line break).
  * ```` ```lang ```` — the first token is a language tag and one newline after it is skipped.
  * `[text]` with no `(url)` uses the text as the URL; the brackets are consumed either way.
  * Backslash escapes exactly four characters: `_ * ` [`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Entity:
    type: str
    offset: int  # UTF-16 code units, as Telegram counts
    length: int
    arg: str = ""


class TgParseError(Exception):
    def __init__(self, message: str, byte_offset: int | None = None):
        super().__init__(message)
        self.message = message
        self.byte_offset = byte_offset


_SPACE = frozenset(b" \t\r\n\x0b\x00")
_MD_MARK = frozenset(b"_*`[")


def _is_utf8_first(c: int) -> bool:
    return (c & 0xC0) != 0x80


def _u16_inc(c: int) -> int:
    # tdlib: utf16_offset += 1 + (c >= 0xf0)  — a 4-byte sequence is a surrogate pair
    return 1 + (1 if c >= 0xF0 else 0)


_SCHEME_RE = re.compile(rb"^(https?|tg|ton)://", re.I)
_DOMAINISH_RE = re.compile(rb"^[A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,}(?:[:/?#].*)?$")


def _check_link(url: bytes) -> str | None:
    """Approximation of LinkManager::check_link: a scheme'd URL or a domain-looking string is
    accepted (tdlib prepends http://), anything else yields NO entity and the text stays plain."""
    u = url.strip()
    if not u:
        return None
    if _SCHEME_RE.match(u) or _DOMAINISH_RE.match(u):
        return u.decode("utf-8", errors="replace")
    return None


# ── Legacy Markdown (v1) ─────────────────────────────────────────────────────

def parse_markdown_v1(text: str) -> tuple[str, list[Entity]]:
    """Port of tdlib `parse_markdown` (the legacy parser behind parse_mode="Markdown").
    Returns (plain_text, entities) or raises TgParseError with Telegram's message."""
    b = text.encode("utf-8")
    size = len(b)

    def at(i: int) -> int:  # C-string semantics: text[size] == '\0'
        return b[i] if i < size else 0

    result = bytearray()
    entities: list[Entity] = []
    utf16 = 0
    i = 0
    while i < size:
        c = b[i]
        if c == 0x5C and at(i + 1) in _MD_MARK:  # backslash escape
            i += 1
            result.append(b[i])
            utf16 += 1
            i += 1
            continue
        if c not in _MD_MARK:
            if _is_utf8_first(c):
                utf16 += _u16_inc(c)
            result.append(c)
            i += 1
            continue

        begin_pos = i
        end_char = c
        is_pre = False
        if c == 0x5B:  # '['
            end_char = 0x5D  # ']'
        i += 1
        language = b""
        if c == 0x60 and at(i) == 0x60 and at(i + 1) == 0x60:
            i += 2
            is_pre = True
            language_end = i
            while at(language_end) not in _SPACE and at(language_end) != 0x60:
                language_end += 1
            if i != language_end and language_end < size and at(language_end) != 0x60:
                language = b[i:language_end]
                i = language_end
            # skip one new line in the beginning of the text
            if at(i) in (0x0A, 0x0D):
                if at(i + 1) in (0x0A, 0x0D) and at(i) != at(i + 1):
                    i += 2
                else:
                    i += 1

        entity_offset = utf16
        while i < size and (at(i) != end_char or (is_pre and not (at(i + 1) == 0x60 and at(i + 2) == 0x60))):
            cur = b[i]
            if _is_utf8_first(cur):
                utf16 += _u16_inc(cur)
            result.append(cur)
            i += 1
        if i == size:
            raise TgParseError(f"Can't find end of the entity starting at byte offset {begin_pos}", begin_pos)

        if entity_offset != utf16:
            length = utf16 - entity_offset
            if c == 0x5F:
                entities.append(Entity("italic", entity_offset, length))
            elif c == 0x2A:
                entities.append(Entity("bold", entity_offset, length))
            elif c == 0x5B:
                if at(i + 1) != 0x28:  # no '(' → the text itself is the URL
                    url = b[begin_pos + 1:i]
                else:
                    i += 2
                    url_begin = i
                    while i < size and at(i) != 0x29:
                        i += 1
                    if at(i) != 0x29:
                        raise TgParseError(f"Can't find end of a URL at byte offset {url_begin}", url_begin)
                    url = b[url_begin:i]
                if url.startswith(b"tg://user?id="):
                    entities.append(Entity("mention", entity_offset, length, url.decode()))
                else:
                    ok = _check_link(url)
                    if ok is not None:
                        entities.append(Entity("text_url", entity_offset, length, ok))
            elif c == 0x60:
                if is_pre:
                    entities.append(Entity("pre", entity_offset, length, language.decode("utf-8", "replace")))
                else:
                    entities.append(Entity("code", entity_offset, length))
        # (tdlib: an EMPTY entity skips the switch entirely — so `[](url)` leaves "(url)" as text)
        if is_pre:
            i += 2
        i += 1  # the for-loop's i++ (skips the closing marker)
    return result.decode("utf-8", errors="replace"), entities


# ── HTML ─────────────────────────────────────────────────────────────────────

_HTML_TAGS = frozenset({
    "a", "b", "strong", "i", "em", "s", "strike", "del", "u", "ins", "tg-spoiler", "tg-emoji",
    "span", "pre", "code", "blockquote",
})


def _is_alpha(c: int) -> bool:
    return (0x41 <= c <= 0x5A) or (0x61 <= c <= 0x7A)


def _is_digit(c: int) -> bool:
    return 0x30 <= c <= 0x39


def _is_hex(c: int) -> bool:
    return _is_digit(c) or (0x41 <= c <= 0x46) or (0x61 <= c <= 0x66)


def _decode_html_entity(b: bytes, pos: int) -> tuple[int, int]:
    """Port of tdlib decode_html_entity. Returns (codepoint, new_pos) or (0, pos) if not an entity."""
    size = len(b)

    def at(i: int) -> int:
        return b[i] if i < size else 0

    if at(pos) != 0x26:
        return 0, pos
    end_pos = pos + 1
    res = 0
    if at(pos + 1) == 0x23:  # '#'
        end_pos += 1
        if at(pos + 2) == 0x78:  # 'x'
            end_pos += 1
            while _is_hex(at(end_pos)):
                res = res * 16 + int(chr(at(end_pos)), 16)
                end_pos += 1
        else:
            while _is_digit(at(end_pos)):
                res = res * 10 + (at(end_pos) - 0x30)
                end_pos += 1
        if res == 0 or res >= 0x10FFFF or end_pos - pos >= 10:
            return 0, pos
    else:
        while _is_alpha(at(end_pos)):
            end_pos += 1
        name = b[pos + 1:end_pos]
        table = {b"lt": 0x3C, b"gt": 0x3E, b"amp": 0x26, b"apos": 0x27, b"quot": 0x22}
        if name not in table:
            return 0, pos
        res = table[name]
    if at(end_pos) == 0x3B:
        end_pos += 1
    return res, end_pos


def parse_html(text: str) -> tuple[str, list[Entity]]:
    """Port of tdlib `parse_html` (parse_mode="HTML"). Returns (plain_text, entities) or raises
    TgParseError with Telegram's message ("Unsupported start tag", "Unmatched end tag",
    "Can't find end tag corresponding to start tag", ...)."""
    b = text.encode("utf-8")
    size = len(b)

    def at(i: int) -> int:
        return b[i] if i < size else 0

    result = bytearray()
    entities: list[Entity] = []
    utf16 = 0
    nested: list[tuple[str, str, int, int]] = []  # (tag, argument, utf16_offset, result_pos)
    i = 0
    while i < size:
        c = b[i]
        if c == 0x26:
            ch, npos = _decode_html_entity(b, i)
            if ch != 0:
                enc = chr(ch).encode("utf-8")
                result.extend(enc)
                utf16 += _u16_inc(enc[0])
                i = npos
                continue
        if c != 0x3C:
            if _is_utf8_first(c):
                utf16 += _u16_inc(c)
            result.append(c)
            i += 1
            continue

        begin_pos = i
        i += 1
        if at(i) != 0x2F:  # start tag
            while at(i) not in _SPACE and at(i) != 0x3E:
                i += 1
            if at(i) == 0:
                raise TgParseError(f"Unclosed start tag at byte offset {begin_pos}", begin_pos)
            tag_name = b[begin_pos + 1:i].decode("utf-8", "replace").lower()
            if tag_name not in _HTML_TAGS:
                raise TgParseError(f'Unsupported start tag "{tag_name}" at byte offset {begin_pos}', begin_pos)
            argument = ""
            while at(i) != 0x3E:
                while at(i) != 0 and at(i) in _SPACE:
                    i += 1
                if at(i) == 0x3E:
                    break
                attr_begin = i
                while at(i) not in _SPACE and at(i) != 0x3D:
                    i += 1
                attr_name = b[attr_begin:i].decode("utf-8", "replace")
                if not attr_name:
                    raise TgParseError(f'Empty attribute name in the tag "{tag_name}" at byte offset {attr_begin}', attr_begin)
                while at(i) != 0 and at(i) in _SPACE:
                    i += 1
                if at(i) != 0x3D:
                    raise TgParseError(
                        f'Expected equal sign in declaration of an attribute of the tag "{tag_name}" at byte offset {attr_begin}',
                        attr_begin)
                i += 1
                while at(i) != 0 and at(i) in _SPACE:
                    i += 1
                if at(i) == 0:
                    raise TgParseError(f'Unclosed start tag "{tag_name}" at byte offset {begin_pos}', begin_pos)
                value = bytearray()
                if at(i) not in (0x27, 0x22):
                    tok_begin = i
                    while _is_alpha(at(i)) or _is_digit(at(i)) or at(i) in (0x2E, 0x2D):
                        i += 1
                    value.extend(b[tok_begin:i].lower())
                    if at(i) not in _SPACE and at(i) != 0x3E:
                        raise TgParseError(f"Unexpected end of name token at byte offset {tok_begin}", tok_begin)
                else:
                    end_ch = at(i)
                    i += 1
                    while at(i) != end_ch and at(i) != 0:
                        if at(i) == 0x26:
                            ch, npos = _decode_html_entity(b, i)
                            if ch != 0:
                                value.extend(chr(ch).encode("utf-8"))
                                i = npos
                                continue
                        value.append(b[i])
                        i += 1
                    if at(i) == end_ch:
                        i += 1
                if at(i) == 0:
                    raise TgParseError(f"Unclosed start tag at byte offset {begin_pos}", begin_pos)
                v = value.decode("utf-8", "replace")
                if tag_name == "a" and attr_name == "href":
                    argument = v
                elif tag_name == "code" and attr_name == "class" and v.startswith("language-"):
                    argument = v[9:]
                elif tag_name == "span" and attr_name == "class" and v.startswith("tg-"):
                    argument = v[3:]
                elif tag_name == "tg-emoji" and attr_name == "emoji-id":
                    argument = v
            if tag_name == "span" and argument != "spoiler":
                raise TgParseError(f'Tag "span" must have class "tg-spoiler" at byte offset {begin_pos}', begin_pos)
            nested.append((tag_name, argument, utf16, len(result)))
        else:  # end tag
            if not nested:
                raise TgParseError(f"Unexpected end tag at byte offset {begin_pos}", begin_pos)
            while at(i) not in _SPACE and at(i) != 0x3E:
                i += 1
            end_tag_name = b[begin_pos + 2:i].decode("utf-8", "replace").lower()
            while at(i) in _SPACE and at(i) != 0:
                i += 1
            if at(i) != 0x3E:
                raise TgParseError(f"Unclosed end tag at byte offset {begin_pos}", begin_pos)
            tag_name, argument, entity_offset, result_pos = nested[-1]
            if end_tag_name and end_tag_name != tag_name:
                raise TgParseError(
                    f'Unmatched end tag at byte offset {begin_pos}, expected "</{tag_name}>", found "</{end_tag_name}>"',
                    begin_pos)
            if utf16 > entity_offset:
                length = utf16 - entity_offset
                if tag_name in ("i", "em"):
                    entities.append(Entity("italic", entity_offset, length))
                elif tag_name in ("b", "strong"):
                    entities.append(Entity("bold", entity_offset, length))
                elif tag_name in ("s", "strike", "del"):
                    entities.append(Entity("strikethrough", entity_offset, length))
                elif tag_name in ("u", "ins"):
                    entities.append(Entity("underline", entity_offset, length))
                elif tag_name == "tg-spoiler" or (tag_name == "span" and argument == "spoiler"):
                    entities.append(Entity("spoiler", entity_offset, length))
                elif tag_name == "tg-emoji":
                    entities.append(Entity("custom_emoji", entity_offset, length, argument))
                elif tag_name == "a":
                    url = argument or result[result_pos:].decode("utf-8", "replace")
                    if url.startswith("tg://user?id="):
                        entities.append(Entity("mention", entity_offset, length, url))
                    else:
                        ok = _check_link(url.encode("utf-8"))
                        if ok is not None:
                            entities.append(Entity("text_url", entity_offset, length, ok))
                elif tag_name == "pre":
                    if (entities and entities[-1].type == "code" and entities[-1].offset == entity_offset
                            and entities[-1].length == length and entities[-1].arg):
                        last = entities.pop()
                        entities.append(Entity("pre", entity_offset, length, last.arg))
                    else:
                        entities.append(Entity("pre", entity_offset, length, argument))
                elif tag_name == "code":
                    if (entities and entities[-1].type == "pre" and entities[-1].offset == entity_offset
                            and entities[-1].length == length and argument):
                        last = entities.pop()
                        entities.append(Entity("pre", entity_offset, length, argument))
                    else:
                        entities.append(Entity("code", entity_offset, length, argument))
                elif tag_name == "blockquote":
                    entities.append(Entity("blockquote", entity_offset, length))
            nested.pop()
        i += 1  # past '>'
    if nested:
        raise TgParseError(f"Can't find end tag corresponding to start tag {nested[-1][0]}")
    return result.decode("utf-8", errors="replace"), entities


# ── Post-parse normalisation shared by both modes ────────────────────────────

def fix_formatted_text(text: str, entities: list[Entity]) -> tuple[str, list[Entity]]:
    """The slice of tdlib fix_formatted_text that changes what the operator sees: the message
    is trimmed of leading/trailing whitespace (entity offsets shift with it), an empty
    result is a 400 ("Message must be non-empty"), entities are sorted."""
    lead = len(text) - len(text.lstrip(" \t\r\n\x0b\x0c"))
    lead_u16 = sum(2 if ord(ch) > 0xFFFF else 1 for ch in text[:lead])
    stripped = text.strip(" \t\r\n\x0b\x0c")
    if not stripped:
        raise TgParseError("Message must be non-empty")
    total_u16 = sum(2 if ord(ch) > 0xFFFF else 1 for ch in stripped)
    out: list[Entity] = []
    for e in entities:
        off = e.offset - lead_u16
        end = min(off + e.length, total_u16)
        if off < 0:
            off = 0
        if end - off > 0:
            out.append(Entity(e.type, off, end - off, e.arg))
    out.sort(key=lambda e: (e.offset, -e.length, e.type))
    return stripped, out


def render_markup(text: str, entities: list[Entity]) -> str:
    """A canonical, human-readable rendering — the plain text with entity spans bracketed as
    ⟦type:…⟧ — so two parses can be diffed by eye. Offsets are UTF-16 units, so map them."""
    if not entities:
        return text
    # map utf16 unit -> python index
    u16_to_idx: list[int] = []
    for idx, ch in enumerate(text):
        u16_to_idx.append(idx)
        if ord(ch) > 0xFFFF:
            u16_to_idx.append(idx)
    u16_to_idx.append(len(text))
    opens: dict[int, list[str]] = {}
    closes: dict[int, list[str]] = {}
    for e in sorted(entities, key=lambda e: (e.offset, -e.length)):
        s = u16_to_idx[min(e.offset, len(u16_to_idx) - 1)]
        t = u16_to_idx[min(e.offset + e.length, len(u16_to_idx) - 1)]
        tag = e.type if not e.arg else f"{e.type}={e.arg}"
        opens.setdefault(s, []).append(f"⟦{tag}:")
        closes.setdefault(t, []).append("⟧")
    out: list[str] = []
    for idx in range(len(text) + 1):
        out.extend(reversed(closes.get(idx, [])))
        out.extend(opens.get(idx, []))
        if idx < len(text):
            out.append(text[idx])
    return "".join(out)
