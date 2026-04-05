"""
Orbita News Aggregator
======================
Polls RSS feeds from major space/aerospace news sources,
scores articles by relevance, deduplicates, and outputs a
structured digest ready for editorial review or Beehiiv API ingestion.

Usage:
    python news_aggregator.py                  # Print digest to stdout
    python news_aggregator.py --output json    # Output JSON file
    python news_aggregator.py --output beehiiv # Push draft to Beehiiv (requires API key)

Requirements:
    pip install feedparser requests python-dateutil
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    import feedparser
    import requests
    from dateutil import parser as dateparser
except ImportError:
    sys.exit(
        "Missing dependencies. Run: pip install feedparser requests python-dateutil"
    )


# ---------------------------------------------------------------------------
# Feed Sources
# ---------------------------------------------------------------------------
FEEDS = [
    # Official agencies
    {"url": "https://www.nasa.gov/rss/dyn/breaking_news.rss",          "source": "NASA",               "weight": 1.4},
    {"url": "https://www.esa.int/rssfeed/Our_Activities/Space_Science", "source": "ESA",                "weight": 1.4},
    {"url": "https://blogs.nasa.gov/spacex/feed/",                      "source": "NASA/SpaceX",        "weight": 1.3},
    # News outlets
    {"url": "https://arstechnica.com/science/feed/",                    "source": "Ars Technica",       "weight": 1.2},
    {"url": "https://www.space.com/feeds/all",                          "source": "Space.com",          "weight": 1.1},
    {"url": "https://spacenews.com/feed/",                              "source": "SpaceNews",          "weight": 1.2},
    {"url": "https://www.nasaspaceflight.com/feed/",                    "source": "NASASpaceFlight",    "weight": 1.3},
    {"url": "https://spaceflightnow.com/feed/",                         "source": "Spaceflight Now",    "weight": 1.2},
    {"url": "https://www.planetary.org/news/rss.xml",                   "source": "Planetary Society",  "weight": 1.1},
    {"url": "https://aviationweek.com/rss.xml",                         "source": "Aviation Week",      "weight": 1.1},
    # Italian sources
    {"url": "https://www.astronomia.com/feed/",                         "source": "Astronomia.com",     "weight": 1.3},
    {"url": "https://www.media.inaf.it/feed/",                          "source": "INAF Media",         "weight": 1.4},
    {"url": "https://www.astronautinews.it/feed/",                      "source": "Astronauti News",    "weight": 1.3},
]

# ---------------------------------------------------------------------------
# Keywords for relevance scoring
# ---------------------------------------------------------------------------
HIGH_VALUE_KEYWORDS = [
    "launch", "rocket", "spacecraft", "astronaut", "cosmonaut", "satellite",
    "moon", "mars", "artemis", "spacex", "falcon", "starship", "nasa", "esa",
    "roscosmos", "jaxa", "isro", "space station", "iss", "hubble", "webb",
    "exoplanet", "asteroid", "mission", "orbit", "reusable", "landing",
    "discovery", "telescope", "probe", "rover", "launch vehicle", "payload",
    "aerospace", "aviation", "aircraft", "supersonic", "hypersonic",
    "lancio", "razzo", "satellite", "astronauta", "luna", "marte", "spazio",
    "missione", "scoperta", "telescopio", "sonda", "veicolo spaziale",
]

DEPRIORITIZE_KEYWORDS = [
    "opinion", "review", "deal", "discount", "quiz", "horoscope",
    "unboxing", "gaming", "movie", "book",
]


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def fetch_feed(feed_config: dict, lookback_hours: int = 168) -> list[dict]:
    """Fetch and parse a single RSS feed, filtering to articles within the lookback window."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    articles = []

    try:
        parsed = feedparser.parse(feed_config["url"])
        for entry in parsed.entries:
            # Parse publication date
            pub_date = None
            for date_field in ("published_parsed", "updated_parsed"):
                if hasattr(entry, date_field) and getattr(entry, date_field):
                    import time
                    ts = time.mktime(getattr(entry, date_field))
                    pub_date = datetime.fromtimestamp(ts, tz=timezone.utc)
                    break

            if pub_date is None or pub_date < cutoff:
                continue

            title = getattr(entry, "title", "").strip()
            summary = getattr(entry, "summary", "").strip()
            link = getattr(entry, "link", "").strip()

            if not title or not link:
                continue

            articles.append({
                "title": title,
                "summary": summary[:500] if summary else "",
                "link": link,
                "source": feed_config["source"],
                "published": pub_date.isoformat(),
                "source_weight": feed_config.get("weight", 1.0),
                "fingerprint": hashlib.md5(link.encode()).hexdigest(),
            })

    except Exception as exc:
        print(f"[WARN] Failed to fetch {feed_config['source']}: {exc}", file=sys.stderr)

    return articles


def score_article(article: dict) -> float:
    """Score an article 0–10 based on keyword relevance and source weight."""
    text = (article["title"] + " " + article["summary"]).lower()
    score = 0.0

    for kw in HIGH_VALUE_KEYWORDS:
        if kw.lower() in text:
            score += 1.5

    for kw in DEPRIORITIZE_KEYWORDS:
        if kw.lower() in text:
            score -= 2.0

    score *= article.get("source_weight", 1.0)
    return max(0.0, min(score, 20.0))


def deduplicate(articles: list[dict]) -> list[dict]:
    """Remove duplicate articles (same URL or very similar title)."""
    seen_fingerprints = set()
    seen_titles = set()
    unique = []

    for article in articles:
        fp = article["fingerprint"]
        title_key = article["title"].lower()[:60]

        if fp in seen_fingerprints or title_key in seen_titles:
            continue

        seen_fingerprints.add(fp)
        seen_titles.add(title_key)
        unique.append(article)

    return unique


def build_digest(
    lookback_hours: int = 168,
    top_n: int = 20,
    brief_n: int = 7,
) -> dict:
    """Fetch all feeds and build a ranked digest."""
    all_articles: list[dict] = []

    for feed in FEEDS:
        articles = fetch_feed(feed, lookback_hours=lookback_hours)
        all_articles.extend(articles)
        print(f"  [{feed['source']}] {len(articles)} articles", file=sys.stderr)

    # Deduplicate
    all_articles = deduplicate(all_articles)

    # Score and rank
    for article in all_articles:
        article["score"] = score_article(article)

    ranked = sorted(all_articles, key=lambda a: a["score"], reverse=True)[:top_n]

    digest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_hours": lookback_hours,
        "total_fetched": len(all_articles),
        "cover_story": ranked[0] if ranked else None,
        "briefs": ranked[1:brief_n + 1],
        "remaining": ranked[brief_n + 1:],
    }

    return digest


# ---------------------------------------------------------------------------
# Beehiiv integration
# ---------------------------------------------------------------------------

def push_to_beehiiv(digest: dict, api_key: str, publication_id: str) -> None:
    """
    Create a draft post on Beehiiv from the digest.
    API docs: https://developers.beehiiv.com/docs/v2
    """
    if not digest.get("cover_story"):
        print("[ERROR] No cover story in digest — cannot create Beehiiv draft.", file=sys.stderr)
        return

    cover = digest["cover_story"]
    briefs = digest.get("briefs", [])

    # Build content body (HTML for Beehiiv)
    briefs_html = ""
    for b in briefs:
        briefs_html += f'<li><a href="{b["link"]}">{b["title"]}</a> — {b["summary"][:120]}…</li>\n'

    body_html = f"""
<h2>{cover['title']}</h2>
<p><em>Via {cover['source']}</em></p>
<p>{cover['summary']}</p>
<p><a href="{cover['link']}">Leggi l'articolo completo →</a></p>

<hr>
<h3>Brevi</h3>
<ul>
{briefs_html}
</ul>
"""

    payload = {
        "publication_id": publication_id,
        "subject": f"🚀 Orbita Weekly — {datetime.now().strftime('%d %B %Y')}",
        "preview_text": cover["title"][:100],
        "body": body_html,
        "status": "draft",
        "content_tags": ["space", "aeronautics", "weekly"],
    }

    resp = requests.post(
        f"https://api.beehiiv.com/v2/publications/{publication_id}/posts",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )

    if resp.status_code in (200, 201):
        data = resp.json()
        post_id = data.get("data", {}).get("id", "unknown")
        print(f"[OK] Draft created on Beehiiv: post_id={post_id}")
    else:
        print(f"[ERROR] Beehiiv API error {resp.status_code}: {resp.text}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Orbita space news aggregator")
    parser.add_argument(
        "--output",
        choices=["print", "json", "beehiiv"],
        default="print",
        help="Output mode (default: print)",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=168,
        help="Hours to look back for articles (default: 168 = 1 week)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Maximum number of articles to include (default: 20)",
    )
    parser.add_argument(
        "--out-file",
        default="digest.json",
        help="Output file path for --output json (default: digest.json)",
    )
    args = parser.parse_args()

    print(f"Orbita Aggregator — fetching news ({args.lookback}h lookback)...", file=sys.stderr)
    digest = build_digest(lookback_hours=args.lookback, top_n=args.top)

    if args.output == "print":
        print("\n" + "=" * 60)
        print("ORBITA DIGEST")
        print("=" * 60)
        if digest["cover_story"]:
            c = digest["cover_story"]
            print(f"\n[COPERTINA] {c['title']}")
            print(f"Source: {c['source']} | Score: {c['score']:.1f}")
            print(f"URL: {c['link']}")
            print(f"Summary: {c['summary'][:200]}...")

        print(f"\n[BREVI] ({len(digest['briefs'])} items)")
        for i, b in enumerate(digest["briefs"], 1):
            print(f"  {i}. {b['title']} [{b['source']}] score={b['score']:.1f}")

        print(f"\nTotal fetched: {digest['total_fetched']} unique articles")
        print("=" * 60)

    elif args.output == "json":
        with open(args.out_file, "w", encoding="utf-8") as f:
            json.dump(digest, f, indent=2, ensure_ascii=False)
        print(f"[OK] Digest written to {args.out_file}", file=sys.stderr)

    elif args.output == "beehiiv":
        api_key = os.environ.get("BEEHIIV_API_KEY")
        publication_id = os.environ.get("BEEHIIV_PUBLICATION_ID")
        if not api_key or not publication_id:
            sys.exit(
                "[ERROR] Set BEEHIIV_API_KEY and BEEHIIV_PUBLICATION_ID environment variables."
            )
        push_to_beehiiv(digest, api_key=api_key, publication_id=publication_id)


if __name__ == "__main__":
    main()
