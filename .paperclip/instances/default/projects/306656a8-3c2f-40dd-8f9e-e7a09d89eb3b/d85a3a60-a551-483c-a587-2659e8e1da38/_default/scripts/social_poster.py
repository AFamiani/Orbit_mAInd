"""
Orbita Social Media Cross-Poster
=================================
Reads news digest (from news_aggregator.py JSON output) and cross-posts
formatted content to X (Twitter), LinkedIn, Instagram, YouTube, and TikTok.

Features:
  - Platform-specific content formatting (char limits, hashtags, tone)
  - Scheduling: respects configured post times, skips if already posted today
  - Basic analytics: logs post metadata and fetches engagement metrics on demand
  - Dry-run mode for safe testing

Usage:
    python social_poster.py --digest digest.json                  # Post from digest
    python social_poster.py --digest digest.json --dry-run        # Preview only
    python social_poster.py --digest digest.json --platforms twitter linkedin
    python social_poster.py --fetch-analytics --days 7            # Pull last 7d stats

Environment variables (see config/social_platforms.json for mapping):
    TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET
    LINKEDIN_ACCESS_TOKEN, LINKEDIN_ORGANIZATION_ID
    INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_ACCOUNT_ID
    TIKTOK_ACCESS_TOKEN, TIKTOK_OPEN_ID

Requirements:
    pip install tweepy requests python-dateutil
    (Optional for YouTube: pip install google-api-python-client google-auth-oauthlib)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import requests
    from dateutil import parser as dateparser
except ImportError:
    sys.exit("Missing dependencies. Run: pip install requests python-dateutil")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
CONFIG_PATH = PROJECT_DIR / "config" / "social_platforms.json"
ANALYTICS_DEFAULT = PROJECT_DIR / "logs" / "social_analytics.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("orbita.social")


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        log.warning("Config not found at %s — using defaults.", CONFIG_PATH)
        return {}
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def resolve_env(env_map: dict) -> dict:
    """Resolve credential keys from environment variables."""
    return {k: os.environ.get(v, "") for k, v in env_map.items()}


# ---------------------------------------------------------------------------
# Content formatters — platform-specific
# ---------------------------------------------------------------------------

def format_for_twitter(article: dict, settings: dict) -> list[str]:
    """
    Returns a list of tweet strings (thread) if content overflows 280 chars.
    First tweet: headline + source + short summary + link + hashtags.
    """
    max_chars = settings.get("max_chars", 280)
    tags = " ".join(settings.get("default_hashtags", []))
    title = article.get("title", "")
    source = article.get("source", "")
    link = article.get("link", "")
    summary = article.get("summary", "")

    # Reserve space for link (23 chars, Twitter t.co wraps all links) + tags
    reserved = 24 + len(tags) + 2  # 2 for newlines
    available = max_chars - reserved

    body = title
    if source:
        body += f" [{source}]"

    if len(body) > available:
        body = body[: available - 3] + "..."

    tweet1 = f"{body}\n{link}\n{tags}"

    tweets = [tweet1]

    # If there's a meaningful summary, add it as thread reply
    if summary and settings.get("thread_on_overflow", True):
        thread_body = summary[:270] + ("…" if len(summary) > 270 else "")
        tweets.append(thread_body)

    return tweets


def format_for_linkedin(article: dict, settings: dict) -> str:
    """
    Returns a LinkedIn post (professional tone, longer form).
    """
    max_chars = settings.get("max_chars", 3000)
    tags = "\n".join(settings.get("default_hashtags", []))
    title = article.get("title", "")
    source = article.get("source", "")
    summary = article.get("summary", "")
    link = article.get("link", "")

    body_lines = [
        f"🚀 {title}",
        "",
        summary[:800] if summary else "",
        "",
        f"Fonte: {source}" if source else "",
        f"🔗 {link}",
        "",
        tags,
    ]
    body = "\n".join(line for line in body_lines if line is not None)

    if len(body) > max_chars:
        body = body[: max_chars - 3] + "..."

    return body


def format_for_instagram(article: dict, settings: dict) -> str:
    """
    Returns an Instagram caption (emoji-rich, hashtag-heavy).
    Note: image upload is handled separately.
    """
    max_chars = settings.get("max_caption_chars", 2200)
    hashtags = " ".join(settings.get("default_hashtags", []))
    title = article.get("title", "")
    summary = article.get("summary", "")
    source = article.get("source", "")

    caption_lines = [
        f"✨ {title}",
        "",
        summary[:300] if summary else "",
        "",
        f"📰 Via {source}" if source else "",
        "🔗 Link in bio",
        "",
        hashtags,
    ]
    caption = "\n".join(line for line in caption_lines if line is not None)

    if len(caption) > max_chars:
        caption = caption[: max_chars - 3] + "..."

    return caption


def format_for_tiktok(article: dict, settings: dict) -> str:
    """
    Returns a TikTok caption (short, punchy, hashtag-heavy).
    """
    max_chars = settings.get("max_caption_chars", 2200)
    hashtags = " ".join(settings.get("default_hashtags", []))
    title = article.get("title", "")
    summary = article.get("summary", "")

    # TikTok captions are brief — lead with a hook
    hook = title[:100] if len(title) > 100 else title
    blurb = summary[:150] if summary else ""

    caption = f"🚀 {hook}\n\n{blurb}\n\n{hashtags}".strip()
    if len(caption) > max_chars:
        caption = caption[: max_chars - 3] + "..."
    return caption


def format_for_youtube(article: dict, settings: dict) -> dict:
    """
    Returns a YouTube video metadata dict (title + description).
    Assumes a short video/reel is being uploaded separately.
    """
    title = article.get("title", "")[:100]
    summary = article.get("summary", "")
    source = article.get("source", "")
    link = article.get("link", "")
    tags = settings.get("default_tags", [])

    description = textwrap.dedent(f"""\
        {summary}

        Fonte: {source}
        Leggi di più: {link}

        ---
        Orbita — Notizie di Spazio & Aeronautica
        Iscriviti alla newsletter: [link in bio]
    """)

    return {
        "title": title,
        "description": description[:5000],
        "tags": tags,
        "categoryId": settings.get("default_category_id", "28"),
        "privacyStatus": settings.get("privacy_status", "public"),
    }


FORMATTERS = {
    "twitter": format_for_twitter,
    "linkedin": format_for_linkedin,
    "instagram": format_for_instagram,
    "tiktok": format_for_tiktok,
    "youtube": format_for_youtube,
}


# ---------------------------------------------------------------------------
# Platform API clients
# ---------------------------------------------------------------------------

class TwitterClient:
    """Thin wrapper around Twitter API v2 using tweepy."""

    def __init__(self, creds: dict):
        try:
            import tweepy
        except ImportError:
            raise RuntimeError("tweepy not installed. Run: pip install tweepy")

        self.client = tweepy.Client(
            bearer_token=creds.get("bearer_token"),
            consumer_key=creds.get("api_key"),
            consumer_secret=creds.get("api_secret"),
            access_token=creds.get("access_token"),
            access_token_secret=creds.get("access_token_secret"),
            wait_on_rate_limit=True,
        )

    def post(self, tweets: list[str]) -> dict:
        """Post a single tweet or a thread. Returns first tweet id."""
        reply_to_id = None
        first_result = None

        for tweet_text in tweets:
            kwargs = {"text": tweet_text}
            if reply_to_id:
                kwargs["in_reply_to_tweet_id"] = reply_to_id

            result = self.client.create_tweet(**kwargs)
            tweet_id = result.data["id"]
            if first_result is None:
                first_result = tweet_id
            reply_to_id = tweet_id

        return {"platform": "twitter", "post_id": first_result}

    def get_metrics(self, tweet_id: str) -> dict:
        tweet = self.client.get_tweet(
            tweet_id,
            tweet_fields=["public_metrics"],
        )
        if tweet.data and tweet.data.public_metrics:
            return tweet.data.public_metrics
        return {}


class LinkedInClient:
    """Posts to a LinkedIn organization page via LinkedIn API v2."""

    API_BASE = "https://api.linkedin.com/v2"

    def __init__(self, creds: dict):
        self.access_token = creds.get("access_token", "")
        self.organization_id = creds.get("organization_id", "")
        if not self.access_token or not self.organization_id:
            raise RuntimeError("LinkedIn: missing access_token or organization_id")
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

    def post(self, text: str) -> dict:
        payload = {
            "author": f"urn:li:organization:{self.organization_id}",
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        resp = requests.post(
            f"{self.API_BASE}/ugcPosts",
            headers=self.headers,
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        return {"platform": "linkedin", "post_id": data.get("id", "")}

    def get_metrics(self, post_id: str) -> dict:
        encoded = requests.utils.quote(post_id, safe="")
        resp = requests.get(
            f"{self.API_BASE}/organizationalEntityShareStatistics?q=organizationalEntity"
            f"&organizationalEntity=urn:li:organization:{self.organization_id}"
            f"&shares[0]={encoded}",
            headers=self.headers,
            timeout=15,
        )
        if resp.ok:
            elements = resp.json().get("elements", [])
            if elements:
                return elements[0].get("totalShareStatistics", {})
        return {}


class InstagramClient:
    """Posts to Instagram Business via Meta Graph API."""

    GRAPH_BASE = "https://graph.facebook.com/v19.0"

    def __init__(self, creds: dict):
        self.access_token = creds.get("access_token", "")
        self.account_id = creds.get("instagram_account_id", "")
        if not self.access_token or not self.account_id:
            raise RuntimeError("Instagram: missing access_token or instagram_account_id")

    def post(self, caption: str, image_url: Optional[str] = None) -> dict:
        """
        Create a media container then publish it.
        image_url must be a publicly accessible URL.
        If no image_url provided, posts as a text-only carousel (unsupported on IG) — skip.
        """
        if not image_url:
            log.warning("Instagram: no image_url provided — skipping post.")
            return {"platform": "instagram", "post_id": None, "skipped": True, "reason": "no_image"}

        # Step 1: create container
        create_resp = requests.post(
            f"{self.GRAPH_BASE}/{self.account_id}/media",
            params={
                "image_url": image_url,
                "caption": caption,
                "access_token": self.access_token,
            },
            timeout=20,
        )
        create_resp.raise_for_status()
        container_id = create_resp.json()["id"]

        # Step 2: publish
        pub_resp = requests.post(
            f"{self.GRAPH_BASE}/{self.account_id}/media_publish",
            params={
                "creation_id": container_id,
                "access_token": self.access_token,
            },
            timeout=20,
        )
        pub_resp.raise_for_status()
        media_id = pub_resp.json()["id"]
        return {"platform": "instagram", "post_id": media_id}

    def get_metrics(self, media_id: str) -> dict:
        resp = requests.get(
            f"{self.GRAPH_BASE}/{media_id}/insights",
            params={
                "metric": "impressions,reach,likes_count,comments_count,shares",
                "access_token": self.access_token,
            },
            timeout=15,
        )
        if resp.ok:
            data = resp.json().get("data", [])
            return {m["name"]: m.get("values", [{}])[-1].get("value", 0) for m in data}
        return {}


class TikTokClient:
    """Posts to TikTok via TikTok for Developers API (Content Posting API)."""

    API_BASE = "https://open.tiktokapis.com/v2"

    def __init__(self, creds: dict):
        self.access_token = creds.get("access_token", "")
        self.open_id = creds.get("open_id", "")
        if not self.access_token:
            raise RuntimeError("TikTok: missing access_token")

    def post(self, caption: str, video_url: Optional[str] = None) -> dict:
        """
        Initiates a video upload from a URL.
        TikTok requires a video file — skips if no video_url provided.
        """
        if not video_url:
            log.warning("TikTok: no video_url provided — skipping post.")
            return {"platform": "tiktok", "post_id": None, "skipped": True, "reason": "no_video"}

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "post_info": {
                "title": caption[:150],
                "privacy_level": "PUBLIC_TO_EVERYONE",
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "PULL_FROM_URL",
                "video_url": video_url,
            },
        }
        resp = requests.post(
            f"{self.API_BASE}/post/publish/video/init/",
            headers=headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        publish_id = resp.json().get("data", {}).get("publish_id", "")
        return {"platform": "tiktok", "post_id": publish_id}

    def get_metrics(self, publish_id: str) -> dict:
        """Query video metrics (requires video_id, not publish_id — placeholder)."""
        return {}


# ---------------------------------------------------------------------------
# Analytics tracker
# ---------------------------------------------------------------------------

class AnalyticsTracker:
    """Appends post records to a JSON-lines analytics log."""

    def __init__(self, log_path: Path = ANALYTICS_DEFAULT):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def record_post(self, platform: str, post_id: str, article: dict, dry_run: bool = False) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "platform": platform,
            "post_id": post_id,
            "dry_run": dry_run,
            "article_title": article.get("title", ""),
            "article_url": article.get("link", ""),
            "source": article.get("source", ""),
            "score": article.get("score", 0),
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        log.debug("Analytics recorded for %s post %s", platform, post_id)

    def load_records(self, days: int = 30) -> list[dict]:
        if not self.log_path.exists():
            return []
        cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
        records = []
        with open(self.log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    rec_ts = dateparser.parse(rec["ts"]).timestamp()
                    if rec_ts >= cutoff:
                        records.append(rec)
                except Exception:
                    pass
        return records

    def summarize(self, days: int = 7) -> dict:
        records = self.load_records(days=days)
        summary: dict = {}
        for rec in records:
            p = rec["platform"]
            summary.setdefault(p, {"total_posts": 0, "dry_run": 0, "live": 0})
            summary[p]["total_posts"] += 1
            if rec.get("dry_run"):
                summary[p]["dry_run"] += 1
            else:
                summary[p]["live"] += 1
        return summary


# ---------------------------------------------------------------------------
# Scheduler — simple check based on analytics log
# ---------------------------------------------------------------------------

def already_posted_today(platform: str, analytics: AnalyticsTracker) -> bool:
    """Return True if a live post was already made on this platform today."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    records = analytics.load_records(days=1)
    for rec in records:
        if rec["platform"] == platform and not rec.get("dry_run") and rec["ts"].startswith(today):
            return True
    return False


# ---------------------------------------------------------------------------
# Core posting logic
# ---------------------------------------------------------------------------

def post_article(
    article: dict,
    platforms: list[str],
    config: dict,
    analytics: AnalyticsTracker,
    dry_run: bool = False,
    force: bool = False,
    image_url: Optional[str] = None,
    video_url: Optional[str] = None,
) -> list[dict]:
    """
    Post a single article to the specified platforms.
    Returns a list of result dicts.
    """
    platform_cfg = config.get("platforms", {})
    results = []

    for platform in platforms:
        pcfg = platform_cfg.get(platform, {})
        if not pcfg.get("enabled") and not dry_run:
            log.info("[%s] Platform disabled in config — skipping.", platform)
            continue

        if not force and not dry_run and already_posted_today(platform, analytics):
            log.info("[%s] Already posted today — skipping.", platform)
            results.append({"platform": platform, "skipped": True, "reason": "already_posted_today"})
            continue

        creds = resolve_env(pcfg.get("env", {}))
        settings = pcfg.get("settings", {})
        formatter = FORMATTERS.get(platform)

        if not formatter:
            log.warning("[%s] No formatter found — skipping.", platform)
            continue

        formatted = formatter(article, settings)

        if dry_run:
            log.info("[DRY RUN][%s] Formatted content:\n%s", platform, formatted)
            analytics.record_post(platform, "DRY_RUN", article, dry_run=True)
            results.append({"platform": platform, "dry_run": True, "content": formatted})
            continue

        try:
            if platform == "twitter":
                client = TwitterClient(creds)
                result = client.post(formatted)
            elif platform == "linkedin":
                client = LinkedInClient(creds)
                result = client.post(formatted)
            elif platform == "instagram":
                client = InstagramClient(creds)
                result = client.post(formatted, image_url=image_url)
            elif platform == "tiktok":
                client = TikTokClient(creds)
                result = client.post(formatted, video_url=video_url)
            elif platform == "youtube":
                log.info("[youtube] YouTube posting requires manual video upload. Metadata: %s", formatted)
                result = {"platform": "youtube", "skipped": True, "reason": "manual_upload_required", "metadata": formatted}
            else:
                result = {"platform": platform, "skipped": True, "reason": "unknown_platform"}

            post_id = result.get("post_id") or ""
            if post_id:
                analytics.record_post(platform, post_id, article)
            log.info("[%s] Post result: %s", platform, result)
            results.append(result)

        except Exception as exc:
            log.error("[%s] Post failed: %s", platform, exc)
            results.append({"platform": platform, "error": str(exc)})

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

ALL_PLATFORMS = ["twitter", "linkedin", "instagram", "tiktok", "youtube"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Orbita Social Media Cross-Poster")
    parser.add_argument("--digest", help="Path to digest JSON file (from news_aggregator.py --output json)")
    parser.add_argument("--platforms", nargs="+", choices=ALL_PLATFORMS, default=ALL_PLATFORMS,
                        help="Which platforms to post to (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Format and log without actually posting")
    parser.add_argument("--force", action="store_true",
                        help="Post even if already posted today")
    parser.add_argument("--image-url", default=None,
                        help="Public image URL for Instagram posts (uses APOD if not set)")
    parser.add_argument("--video-url", default=None,
                        help="Public video URL for TikTok posts")
    parser.add_argument("--fetch-analytics", action="store_true",
                        help="Print analytics summary and exit")
    parser.add_argument("--analytics-days", type=int, default=7,
                        help="Days of analytics to summarize (default: 7)")
    args = parser.parse_args()

    config = load_config()
    analytics = AnalyticsTracker(
        ANALYTICS_DEFAULT
        if not config.get("analytics", {}).get("log_file")
        else PROJECT_DIR / config["analytics"]["log_file"]
    )

    if args.fetch_analytics:
        summary = analytics.summarize(days=args.analytics_days)
        print(f"\n=== Orbita Social Analytics (last {args.analytics_days} days) ===")
        if not summary:
            print("No records found.")
        else:
            for platform, stats in summary.items():
                print(f"  {platform:12s}: {stats['live']} live posts, {stats['dry_run']} dry-run previews")
        return

    if not args.digest:
        parser.error("--digest is required unless using --fetch-analytics")

    digest_path = Path(args.digest)
    if not digest_path.exists():
        sys.exit(f"[ERROR] Digest file not found: {digest_path}")

    with open(digest_path, encoding="utf-8") as f:
        digest = json.load(f)

    # Pick the cover story for posting (highest-scored article)
    article = digest.get("cover_story")
    if not article:
        sys.exit("[ERROR] Digest has no cover_story.")

    # Use NASA APOD image for Instagram if available and no --image-url given
    image_url = args.image_url
    if not image_url:
        apod = digest.get("apod")
        if apod and apod.get("media_type") == "image":
            image_url = apod.get("url")
            log.info("Using NASA APOD image for Instagram: %s", image_url)

    log.info("Posting cover story: '%s'", article.get("title", ""))
    log.info("Platforms: %s | dry_run=%s", args.platforms, args.dry_run)

    results = post_article(
        article=article,
        platforms=args.platforms,
        config=config,
        analytics=analytics,
        dry_run=args.dry_run,
        force=args.force,
        image_url=image_url,
        video_url=args.video_url,
    )

    print("\n=== Posting Results ===")
    for r in results:
        status = "DRY RUN" if r.get("dry_run") else ("SKIPPED" if r.get("skipped") else ("ERROR" if r.get("error") else "OK"))
        detail = r.get("post_id") or r.get("reason") or r.get("error") or ""
        print(f"  {r['platform']:12s}: [{status}] {detail}")


if __name__ == "__main__":
    main()
