"""
Twitter/X auto-posting for Apollo_Trends.

Posts evening briefing as a 2-tweet thread (header + chart mosaic, reply with more stocks).
Posts EP alerts as single tweets with Finviz link (max 1 per day).
Posts user-requested custom tweets (single or thread if >280 chars).
Free tier: 280 char limit per tweet. Uses OAuth 1.0a via tweepy.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
from datetime import date
from typing import Any

from agents.market_intelligence.collector import et_today
from agents.market_intelligence.constants import REGIME_EMOJI

logger = logging.getLogger(__name__)
_MAX_STOCKS = 10
_CHAR_LIMIT = 280
_ep_last_posted: date | None = None  # track last EP tweet date (1 per day max)


def _get_client() -> tuple[Any, Any] | None:
    """Return (tweepy.Client, tweepy.API) or None if not configured."""
    try:
        import tweepy
    except ImportError:
        logger.error("tweepy not installed")
        return None

    keys = [os.environ.get(k) for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")]
    if not all(keys):
        logger.warning("X API credentials not configured — skipping tweet")
        return None

    api_key, api_secret, token, token_secret = keys
    client = tweepy.Client(consumer_key=api_key, consumer_secret=api_secret,
                           access_token=token, access_token_secret=token_secret)
    auth = tweepy.OAuth1UserHandler(api_key, api_secret, token, token_secret)
    return client, tweepy.API(auth)


def _stock_line(s: dict, get_desc) -> str:
    ticker = s["ticker"]
    rs = int(s.get("rs_composite") or 0)
    desc = get_desc(ticker) or s.get("sector") or ""
    return f"${ticker} RS {rs} — {desc}" if desc else f"${ticker} RS {rs}"


def _pack_tweets(lines: list[str], prefix: str = "", suffix: str = "") -> list[str]:
    """Pack lines into tweets under _CHAR_LIMIT. Returns list of tweet texts."""
    tweets = []
    current: list[str] = []

    for line in lines:
        pfx = prefix if not tweets else ""
        sfx = suffix if not tweets else ""
        candidate = pfx + "\n".join(current + [line]) + sfx
        if len(candidate) > _CHAR_LIMIT and current:
            tweets.append(pfx + "\n".join(current) + sfx)
            current = [line]
        else:
            current.append(line)

    if current:
        pfx = prefix if not tweets else ""
        sfx = suffix if not tweets else ""
        tweets.append(pfx + "\n".join(current) + sfx)

    return tweets[:2]  # cap at 2 tweets


def format_thread(rs_leaders: list[dict], regime: dict, briefing_date: str) -> list[str]:
    """Format RS leaders into a 2-tweet thread."""
    from agents.market_intelligence.universe import get_description

    label = regime.get("regime", "Unknown")
    emoji = REGIME_EMOJI.get(label, "⚫")
    vix = regime.get("vix")

    header = f"📊 Momentum Leaders — {briefing_date}\n{emoji} {label}"
    if vix is not None:
        header += f" | VIX {vix:.1f}"
    header += "\n\n"

    stock_lines = [_stock_line(s, get_description) for s in rs_leaders[:_MAX_STOCKS]]
    # Trimmed hashtag set — X duplicate-content filter and hashtag-spam heuristics
    # were rejecting the old 4-tag suffix with 403 Forbidden. #RS is too short.
    return _pack_tweets(stock_lines, prefix=header, suffix="\n\n#momentum #stocks")


def format_ep_tweet(ep: dict) -> list[str]:
    """Format an EP alert as 1-2 tweets. Returns list of tweet texts."""
    from agents.market_intelligence.universe import get_description

    ticker = ep["ticker"]
    desc = get_description(ticker)
    rvol = ep.get("rel_volume") or "?"

    header = f"🔥 EP ALERT — ${ticker}"
    if desc:
        header += f" ({desc})"
    stats = f"Gap {ep['gap_pct']:+.1f}% | RVol {rvol}x | Score {ep['ep_score']:.0f}"
    catalyst_q = ep.get("catalyst_quality", "").replace("_", " ").title()
    footer = f"https://finviz.com/quote.ashx?t={ticker}\n#EP #momentum #trading"

    # Build tweet 1: header + stats + catalyst label + as much analysis as fits
    tweet1_lines = [header, stats]
    if catalyst_q:
        tweet1_lines.append(f"Catalyst: {catalyst_q}")

    analysis = ep.get("claude_analysis", "")
    tweet1_base = "\n".join(tweet1_lines)

    # Try to fit analysis + footer in tweet 1
    remaining = _CHAR_LIMIT - len(tweet1_base) - len(f"\n\n{footer}") - 2
    if analysis and remaining > 40:
        tweet1_lines.append(analysis[:remaining])
        tweet1_lines.append(f"\n{footer}")
        return ["\n".join(tweet1_lines)[:_CHAR_LIMIT]]

    # Analysis doesn't fit — put footer in tweet 1, analysis in tweet 2
    tweet1_lines.append(f"\n{footer}")
    tweets = ["\n".join(tweet1_lines)[:_CHAR_LIMIT]]
    if analysis:
        tweets.append(analysis[:_CHAR_LIMIT])
    return tweets


async def post_to_twitter(
    rs_leaders: list[dict], regime: dict, briefing_date: str,
    mosaic_bytes: bytes | None = None,
) -> bool:
    """Post evening briefing as a threaded tweet with chart mosaic."""
    result = _get_client()
    if not result:
        return False
    client, _ = result

    def _post_thread():
        tweets = format_thread(rs_leaders, regime, briefing_date)

        # Post header (no image — v1.1 media_upload not available on free tier)
        response = client.create_tweet(text=tweets[0])
        parent_id = response.data.get("id") if response.data else None
        if not parent_id:
            return False

        # Post replies
        for text in tweets[1:]:
            response = client.create_tweet(text=text, in_reply_to_tweet_id=parent_id)
            rid = response.data.get("id") if response.data else None
            if rid:
                parent_id = rid

        logger.info(f"Twitter thread posted: {len(tweets)} tweets")
        return True

    try:
        return await asyncio.to_thread(_post_thread)
    except Exception as e:
        # Capture tweepy response body so we can see *why* X rejected (duplicate,
        # hashtag spam, rate limit, etc.) instead of just a bare 403.
        detail = ""
        resp = getattr(e, "response", None)
        if resp is not None:
            try:
                detail = f" | body={resp.text[:400]}"
            except Exception:
                pass
        api_codes = getattr(e, "api_codes", None)
        api_messages = getattr(e, "api_messages", None)
        if api_codes or api_messages:
            detail += f" | api_codes={api_codes} api_messages={api_messages}"
        logger.error(f"Twitter post failed: {type(e).__name__}: {e}{detail}")
        return False


async def post_ep_tweet(ep: dict) -> bool:
    """Post an EP alert tweet. Max 1 per day — posts the first HIGH, skips the rest."""
    global _ep_last_posted
    today = et_today()
    if _ep_last_posted == today:
        logger.info("EP tweet already posted today — skipping")
        return False

    result = _get_client()
    if not result:
        return False
    client, _ = result

    def _post():
        tweets = format_ep_tweet(ep)
        parent_id = None
        for tweet_text in tweets:
            kwargs = {"text": tweet_text}
            if parent_id:
                kwargs["in_reply_to_tweet_id"] = parent_id
            response = client.create_tweet(**kwargs)
            tid = response.data.get("id") if response.data else None
            if tid:
                parent_id = tid
        return parent_id

    try:
        tweet_id = await asyncio.to_thread(_post)
        _ep_last_posted = today
        logger.info(f"EP tweet posted: {tweet_id}")
        return True
    except Exception as e:
        logger.error(f"EP tweet failed: {e}")
        return False


def _abbreviate_theme(name: str, max_len: int = 10) -> str:
    """Shorten theme names to fit in a tweet table."""
    # Order matters — apply longer phrases first
    abbrevs = [
        ("Semiconductor Capital", "Semi Cap"),
        ("Semiconductor", "Semi"),
        ("Infrastructure", "Infra"),
        ("Equipment", "Equip"),
        ("Networking & Photonics", "Net"),
        ("Networking", "Net"),
        ("Intelligence Data Services", ""),
        ("Intelligence", "Intel"),
        ("Renaissance", ""),
        ("Generation", "Gen"),
        ("Cybersecurity & Identity", "Cyber"),
        ("Cybersecurity", "Cyber"),
        ("Technology", "Tech"),
        ("Artificial", "AI"),
        ("Processing", "Proc"),
        ("Computing", "Comp"),
        ("Services", "Svc"),
        ("Advanced", "Adv"),
        ("Manufacturing", "Mfg"),
        ("Enterprise", "Ent"),
        ("Industrial Gas & Specialty Chemicals", "Ind Gas"),
        ("Industrial Gas", "Ind Gas"),
        ("Industrial", "Ind"),
        ("Photonics", "Photon"),
        ("Defense Primes & Aerospace", "Defense"),
        ("Defense Primes", "Defense"),
        ("Specialty Chemicals", "Chem"),
        ("Satellite & Space", "Satellite"),
        (" & ", "/"),
        (" and ", "/"),
    ]
    result = name
    # Strip common prefixes
    for prefix in ("U.S. ", "US "):
        if result.startswith(prefix):
            result = result[len(prefix):]
    for long, short in abbrevs:
        result = result.replace(long, short)
    # Collapse whitespace
    result = " ".join(result.split()).strip()
    if len(result) > max_len:
        words = result.split()
        while len(" ".join(words)) > max_len and len(words) > 1:
            words.pop()
        result = " ".join(words)
    return result[:max_len]


def format_theme_tweet(
    scored_themes: list[dict], briefing_date: str,
) -> str:
    """
    Format top 10 themes as a compact table tweet.
    Columns: Theme name (abbreviated), RS, 1M, 3M, 6M.
    Target: ≤280 chars.
    """
    top = scored_themes[:10]
    if not top:
        return ""

    # Use short date: 3/23
    parts = briefing_date.split("-")
    short_date = f"{int(parts[1])}/{int(parts[2])}" if len(parts) == 3 else briefing_date

    lines = [f"Theme RS {short_date}"]
    for st in top:
        name = _abbreviate_theme(st["name"])
        lines.append(
            f"{name:<10} {st['comp']:2.0f} {st['rs_1m']:2.0f} {st['rs_3m']:2.0f} {st['rs_6m']:2.0f}"
        )
    lines.append("#themes #momentum #stocks")

    return "\n".join(lines)


async def post_theme_tweet(
    scored_themes: list[dict], briefing_date: str,
    image_bytes: bytes | None = None,
) -> bool:
    """Post theme scorecard as an image tweet with text fallback."""
    result = _get_client()
    if not result:
        return False
    client, api = result

    text = format_theme_tweet(scored_themes, briefing_date)
    if not text:
        return False

    def _post():
        media_id = None
        if image_bytes:
            media = api.media_upload(filename="theme_rs.png", file=io.BytesIO(image_bytes))
            media_id = media.media_id

        # Short caption when image is attached; full text as fallback
        tweet_text = f"Theme RS — {briefing_date}\n#themes #momentum #stocks" if media_id else text
        kwargs = {"text": tweet_text}
        if media_id:
            kwargs["media_ids"] = [media_id]
        response = client.create_tweet(**kwargs)
        return bool(response.data and response.data.get("id"))

    try:
        ok = await asyncio.to_thread(_post)
        if ok:
            logger.info("Theme scorecard tweet posted")
        return ok
    except Exception as e:
        logger.error(f"Theme tweet failed: {e}")
        return False


async def post_custom_tweet(text: str) -> dict:
    """
    Post a user-requested tweet. If text > 280 chars, splits into a thread
    at sentence boundaries. Returns {"success": bool, "tweet_ids": [...], "error": str?}.
    """
    result = _get_client()
    if not result:
        return {"success": False, "error": "X API credentials not configured"}
    client, _ = result

    # Split into thread if needed
    tweets = _split_into_tweets(text)

    def _post():
        posted_ids = []
        parent_id = None
        for tweet_text in tweets:
            kwargs = {"text": tweet_text}
            if parent_id:
                kwargs["in_reply_to_tweet_id"] = parent_id
            response = client.create_tweet(**kwargs)
            tweet_id = response.data.get("id") if response.data else None
            if tweet_id:
                posted_ids.append(tweet_id)
                parent_id = tweet_id
            else:
                break
        return posted_ids

    try:
        tweet_ids = await asyncio.to_thread(_post)
        if tweet_ids:
            logger.info(f"Custom tweet posted: {len(tweet_ids)} tweet(s), ids={tweet_ids}")
            return {"success": True, "tweet_ids": tweet_ids}
        return {"success": False, "error": "No tweets were posted"}
    except Exception as e:
        logger.error(f"Custom tweet failed: {e}")
        return {"success": False, "error": str(e)}


def _split_into_tweets(text: str) -> list[str]:
    """Split text into tweet-sized chunks at sentence boundaries."""
    if len(text) <= _CHAR_LIMIT:
        return [text]

    import re
    tweets = []
    remaining = text

    while remaining:
        if len(remaining) <= _CHAR_LIMIT:
            tweets.append(remaining)
            break

        # Find last sentence boundary within limit
        chunk = remaining[:_CHAR_LIMIT]
        # Try splitting at ". " followed by uppercase, or at newline
        split_at = None
        for m in re.finditer(r'[.!?]\s', chunk):
            split_at = m.end()
        if split_at is None or split_at < 50:
            # Fallback: split at last space
            split_at = chunk.rfind(" ")
            if split_at == -1:
                split_at = _CHAR_LIMIT

        tweets.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()

    return tweets
