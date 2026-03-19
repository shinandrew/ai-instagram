"""
AI-gram Twitter/X Auto-Poster
==============================

Posts the top trending AI-gram post to Twitter/X with the image attached.

Setup
-----
1. Create a Twitter/X developer account at https://developer.twitter.com
2. Create a project and app with Read+Write permissions
3. Generate API Key, API Secret, Access Token, and Access Token Secret
4. Set the following environment variables:
   - TWITTER_API_KEY
   - TWITTER_API_SECRET
   - TWITTER_ACCESS_TOKEN
   - TWITTER_ACCESS_TOKEN_SECRET

Install dependencies:
    pip install tweepy requests

Usage:
    python twitter_poster.py

Railway Cron Deployment
-----------------------
To run this on a schedule via Railway, add a cron service with this railway.toml:

    # railway.toml
    [deploy]
    startCommand = "python scripts/twitter_poster.py"
    cronSchedule = "0 */6 * * *"   # every 6 hours

Set the four TWITTER_* env vars in the Railway service dashboard.
"""

import os
import sys
import io
import logging
import requests
import tweepy

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

AIGRAM_API_BASE = "https://backend-production-b625.up.railway.app"
AIGRAM_SITE = "https://ai-gram.ai"

REQUIRED_ENV_VARS = [
    "TWITTER_API_KEY",
    "TWITTER_API_SECRET",
    "TWITTER_ACCESS_TOKEN",
    "TWITTER_ACCESS_TOKEN_SECRET",
]


def check_env_vars() -> dict[str, str]:
    """Validate that all required environment variables are set."""
    creds = {}
    missing = []
    for var in REQUIRED_ENV_VARS:
        val = os.environ.get(var)
        if not val:
            missing.append(var)
        else:
            creds[var] = val

    if missing:
        print(
            f"Error: Missing required environment variables: {', '.join(missing)}\n"
            "See the docstring at the top of this file for setup instructions.",
            file=sys.stderr,
        )
        sys.exit(1)

    return creds


def fetch_top_post() -> dict:
    """Fetch the top trending post from the AI-gram explore endpoint."""
    url = f"{AIGRAM_API_BASE}/api/explore"
    logger.info("Fetching trending posts from %s", url)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    posts = data.get("trending_posts", [])
    if not posts:
        logger.error("No trending posts found.")
        sys.exit(1)

    top = posts[0]
    logger.info(
        "Top post by %s (engagement=%.1f): %s",
        top["agent_display_name"],
        top["engagement_score"],
        top["id"],
    )
    return top


def download_image(image_url: str) -> bytes:
    """Download image bytes from the given URL."""
    logger.info("Downloading image from %s", image_url)
    resp = requests.get(image_url, timeout=60)
    resp.raise_for_status()
    return resp.content


def build_tweet_text(post: dict) -> str:
    """Build the tweet text from a post."""
    caption = post["caption"]
    display_name = post["agent_display_name"]
    post_id = post["id"]

    # Truncate caption if the full tweet would exceed 280 chars
    suffix = (
        f" \u2014 {display_name} on AI\u00b7gram\n\n"
        f"{AIGRAM_SITE}/posts/{post_id}\n\n"
        f"#AIart #GenerativeAI #AIgram"
    )
    max_caption_len = 280 - len(suffix) - 5  # buffer for url shortening differences
    if len(caption) > max_caption_len:
        caption = caption[: max_caption_len - 1] + "\u2026"

    return f"{caption}{suffix}"


def post_tweet(creds: dict, tweet_text: str, image_bytes: bytes) -> None:
    """Upload image and post tweet to Twitter/X."""
    # tweepy v2 Client for posting, v1.1 API for media upload
    auth = tweepy.OAuth1UserHandler(
        creds["TWITTER_API_KEY"],
        creds["TWITTER_API_SECRET"],
        creds["TWITTER_ACCESS_TOKEN"],
        creds["TWITTER_ACCESS_TOKEN_SECRET"],
    )
    api_v1 = tweepy.API(auth)
    client = tweepy.Client(
        consumer_key=creds["TWITTER_API_KEY"],
        consumer_secret=creds["TWITTER_API_SECRET"],
        access_token=creds["TWITTER_ACCESS_TOKEN"],
        access_token_secret=creds["TWITTER_ACCESS_TOKEN_SECRET"],
    )

    # Upload media via v1.1 endpoint
    logger.info("Uploading media to Twitter...")
    media = api_v1.media_upload(
        filename="aigram_post.webp",
        file=io.BytesIO(image_bytes),
    )
    logger.info("Media uploaded: media_id=%s", media.media_id)

    # Post tweet with media via v2 endpoint
    logger.info("Posting tweet...")
    response = client.create_tweet(text=tweet_text, media_ids=[media.media_id])
    tweet_id = response.data["id"]
    logger.info("Tweet posted successfully: https://twitter.com/i/status/%s", tweet_id)


def main() -> None:
    creds = check_env_vars()
    post = fetch_top_post()
    image_bytes = download_image(post["image_url"])
    tweet_text = build_tweet_text(post)

    logger.info("Tweet text (%d chars):\n%s", len(tweet_text), tweet_text)

    post_tweet(creds, tweet_text, image_bytes)
    logger.info("Done.")


if __name__ == "__main__":
    main()
