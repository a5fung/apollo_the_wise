"""One-shot diagnostic: regenerate the evening brief without sending,
locate unbalanced Markdown markers, and report position + context.

Run: docker exec apollo-market python -m scripts._diag_brief_markdown
"""
import asyncio
import re


async def main() -> None:
    from agents.market_intelligence.briefing import send_evening_briefing
    import agents.market_intelligence.briefing as bm

    captured: list[str] = []

    async def fake_send(text: str, chat_id=None):
        captured.append(text)
        return True

    bm.send_telegram_message = fake_send
    await send_evening_briefing(chat_id=999999)

    if not captured:
        print("No chunks captured")
        return

    text = captured[0]
    print(f"Chunk length: {len(text)} chars, {len(text.encode('utf-8'))} bytes, "
          f"{len(text.encode('utf-16-le')) // 2} UTF-16 code units")
    print()

    # Count ALL markup characters including backticks, in the ORIGINAL text
    # (Telegram parses on UTF-16 code units — its 'byte offset' is misleading)
    print(f"In original: * count = {text.count('*')}, _ count = {text.count('_')}, "
          f"backtick count = {text.count('`')}")
    triple_count = text.count("```")
    print(f"Triple-backtick count = {triple_count} (must be even)")
    print()

    # Telegram counts UTF-16 code units, not bytes. Find char position
    # corresponding to UTF-16 code unit 3501.
    u16_pos = 0
    char_at_3501 = None
    for i, c in enumerate(text):
        cp = ord(c)
        # Supplementary plane chars (>0xFFFF) take 2 UTF-16 code units
        units = 2 if cp > 0xFFFF else 1
        if u16_pos <= 3501 < u16_pos + units:
            char_at_3501 = i
            break
        u16_pos += units
    if char_at_3501 is not None:
        print(f"UTF-16 code unit 3501 = char position {char_at_3501}")
        ctx_start = max(0, char_at_3501 - 80)
        ctx_end = min(len(text), char_at_3501 + 80)
        print(f"Context ({ctx_start}..{ctx_end}):")
        print(f"  {text[ctx_start:char_at_3501]!r}")
        print(f"  >>> {text[char_at_3501]!r} <<<  (UTF-16 position 3501)")
        print(f"  {text[char_at_3501 + 1:ctx_end]!r}")

    # Show precise content around UTF-8 byte 3501 (Telegram error location)
    encoded = text.encode("utf-8")
    if len(encoded) >= 3550:
        # Decode a slice around the target. Use errors='replace' so partial
        # multi-byte chars don't crash.
        ctx = encoded[3400:3600].decode("utf-8", errors="replace")
        print("=== Bytes 3400-3600 (Telegram parse error vicinity) ===")
        print(repr(ctx))
        print()
        # Try to send THIS chunk to Telegram parse-mode=Markdown — but with
        # a small head/tail to find the exact failing entity
        print("=== Trying to localize the bad entity ===")
        # Bisect: try sending halves until we find the failing one
        try:
            import httpx, os
            import asyncio as _asyncio
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
            chat_id = os.getenv("TELEGRAM_DEBUG_CHAT_ID") or 0
            # Actually skip bisect — just print the line numbers + content
            lines = text.split("\n")
            byte_pos = 0
            for idx, line in enumerate(lines):
                line_bytes = (line + "\n").encode("utf-8")
                if byte_pos <= 3501 < byte_pos + len(line_bytes):
                    print(f"Line {idx} (byte {byte_pos}-{byte_pos+len(line_bytes)}): {line!r}")
                    # Show 3 lines of context
                    for j in range(max(0, idx - 2), min(len(lines), idx + 3)):
                        print(f"  L{j}: {lines[j]!r}")
                    break
                byte_pos += len(line_bytes)
        except Exception as e:
            print(f"Localize failed: {e}")

    # Strip code blocks + inline code — Markdown markers inside don't apply
    text_no_code = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text_no_code = re.sub(r"`[^`]+`", "", text_no_code)

    stars = text_no_code.count("*")
    unders = text_no_code.count("_")
    print(f"Outside code blocks: * count = {stars}, _ count = {unders}")
    print(f"Stars balanced: {stars % 2 == 0}, Unders balanced: {unders % 2 == 0}")
    print()

    # Walk through the no-code text and find which * or _ doesn't pair up.
    # Telegram Markdown: *bold* / _italic_ — each must be balanced on a SINGLE
    # message basis (newlines OK in between).
    def find_unbalanced(s: str, ch: str) -> list[int]:
        positions = [i for i, c in enumerate(s) if c == ch]
        if len(positions) % 2 == 0:
            return []
        return positions

    for ch in ("*", "_"):
        un = find_unbalanced(text_no_code, ch)
        if un:
            print(f"Unbalanced {ch!r} — total {len(un)} (need pairs).")
            # Show context around the LAST one (most likely culprit)
            last_pos = un[-1]
            ctx_start = max(0, last_pos - 60)
            ctx_end = min(len(text_no_code), last_pos + 60)
            print(f"  Last {ch!r} at no-code position {last_pos}:")
            print(f"  context: ...{text_no_code[ctx_start:ctx_end]!r}...")
        else:
            print(f"{ch!r} count = {text_no_code.count(ch)} (balanced)")
    print()

    # Now report likely culprits by scanning original text for underscores
    # outside code that are likely UNINTENTIONAL (e.g. inside ticker descriptions).
    print("All underscore positions in the ORIGINAL chunk (showing first 20):")
    in_code = False
    in_inline = False
    i = 0
    found = []
    while i < len(text):
        if text[i:i+3] == "```":
            in_code = not in_code
            i += 3
            continue
        if not in_code and text[i] == "`":
            in_inline = not in_inline
        if not in_code and not in_inline and text[i] == "_":
            found.append(i)
        i += 1
    print(f"Total stray underscores (outside any code): {len(found)}")
    for p in found[:20]:
        ctx = text[max(0, p - 40):p + 40]
        print(f"  byte {p}: ...{ctx!r}...")


if __name__ == "__main__":
    asyncio.run(main())
