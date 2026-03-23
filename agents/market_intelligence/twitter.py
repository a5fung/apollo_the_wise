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
    return _pack_tweets(stock_lines, prefix=header, suffix="\n\n#momentum #trading #RS #stocks")


def format_ep_tweet(ep: dict) -> str:
    """Format an EP alert as a single tweet with Finviz link."""
    from agents.market_intelligence.universe import get_description

    ticker = ep["ticker"]
    desc = get_description(ticker)
    rvol = ep.get("rel_volume") or "?"

    lines = [f"🔥 EP ALERT — ${ticker}"]
    if desc:
        lines[0] += f" ({desc})"
    lines.append(f"Gap {ep['gap_pct']:+.1f}% | RVol {rvol}x | Score {ep['ep_score']:.0f}")
    catalyst_q = ep.get("catalyst_quality", "").replace("_", " ").title()
    if catalyst_q:
        lines.append(f"Catalyst: {catalyst_q}")

    analysis = ep.get("claude_analysis", "")
    if analysis:
        remaining = _CHAR_LIMIT - len("\n".join(lines)) - 80
        if remaining > 20:
            lines.append(analysis[:remaining])

    lines.append(f"\nhttps://finviz.com/quote.ashx?t={ticker}")
    lines.append("#EP #momentum #trading")
    return "\n".join(lines)[:_CHAR_LIMIT]


async def post_to_twitter(
    rs_leaders: list[dict], regime: dict, briefing_date: str,
    mosaic_bytes: bytes | None = None,
) -> bool:
    """Post evening briefing as a threaded tweet with chart mosaic."""
    result = _get_client()
    if not result:
        return False
    client, api = result

    def _post_thread():
        tweets = format_thread(rs_leaders, regime, briefing_date)

        # Upload chart mosaic
        media_id = None
        if mosaic_bytes:
            media = api.media_upload(filename="rs_leaders.png", file=io.BytesIO(mosaic_bytes))
            media_id = media.media_id

        # Post header
        kwargs = {"text": tweets[0]}
        if media_id:
            kwargs["media_ids"] = [media_id]
        response = client.create_tweet(**kwargs)
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
        logger.error(f"Twitter post failed: {e}")
        return False


async def post_ep_tweet(ep: dict) -> bool:
    """Post an EP alert tweet. Max 1 per day — posts the first HIGH, skips the rest."""
    global _ep_last_posted
    today = date.today()
    if _ep_last_posted == today:
        logger.info("EP tweet already posted today — skipping")
        return False

    result = _get_client()
    if not result:
        return False
    client, _ = result

    def _post():
        response = client.create_tweet(text=format_ep_tweet(ep))
        return response

    try:
        response = await asyncio.to_thread(_post)
        _ep_last_posted = today
        logger.info(f"EP tweet posted: {response.data.get('id')}")
        return True
    except Exception as e:
        logger.error(f"EP tweet failed: {e}")
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
