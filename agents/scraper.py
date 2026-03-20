"""
Web scraper for real-time pickleball news.

Fetches headlines, summaries, and links from French and international
pickleball news sources. Results are cached in
``agents/output/news_cache.json`` to avoid re-fetching the same articles
and to provide context to the content agent.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

from agents.config import OUTPUT_DIR

logger = logging.getLogger(__name__)

NEWS_CACHE = OUTPUT_DIR / "news_cache.json"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 15  # seconds

# ------------------------------------------------------------------
# Sources configuration
# ------------------------------------------------------------------
SOURCES: list[dict[str, Any]] = [
    {
        "name": "Pickleball France",
        "url": "https://www.pickleballfrance.fr/",
        "selectors": {
            "articles": "article, .post-item, .entry, .td-module-thumb a",
            "title": "h2, h3, .entry-title, .td-module-title",
            "link": "a[href]",
            "summary": "p, .entry-excerpt, .td-excerpt",
        },
    },
    {
        "name": "Federation Francaise de Pickleball",
        "url": "https://www.ff-pickleball.fr/actualites/",
        "selectors": {
            "articles": "article, .post-item, .entry",
            "title": "h2, h3, .entry-title",
            "link": "a[href]",
            "summary": "p, .entry-excerpt",
        },
    },
    {
        "name": "The Dink Pickleball",
        "url": "https://www.thedinkpickleball.com/",
        "selectors": {
            "articles": "article, .post, .entry, .blog-post",
            "title": "h2, h3, .entry-title, .post-title",
            "link": "a[href]",
            "summary": "p, .excerpt, .entry-content p",
        },
    },
    {
        "name": "Pickleball Magazine",
        "url": "https://www.pickleballmagazine.com/",
        "selectors": {
            "articles": "article, .post, .entry, .news-item",
            "title": "h2, h3, .entry-title, .post-title",
            "link": "a[href]",
            "summary": "p, .excerpt, .description",
        },
    },
]


# ------------------------------------------------------------------
# Scraping logic
# ------------------------------------------------------------------

def _fetch_page(url: str) -> str | None:
    """Fetch a page's HTML content. Returns None on failure."""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", url, exc)
        return None


def _extract_articles(html: str, source: dict[str, Any]) -> list[dict[str, str]]:
    """Extract article metadata from an HTML page."""
    soup = BeautifulSoup(html, "html.parser")
    sel = source["selectors"]
    results: list[dict[str, str]] = []

    # Try to find article containers first
    containers = soup.select(sel["articles"])

    if not containers:
        # Fallback: look for title elements directly
        containers = soup.select(sel["title"])

    for container in containers[:15]:  # Limit to 15 per source
        # Extract title
        title_el = container.select_one(sel["title"]) if container.name not in ("h2", "h3") else container
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        # Skip junk (newsletter prompts, cookie notices, etc.)
        junk_patterns = ("newsletter", "cookie", "rejoignez", "inscri", "accepter", "politique de confidentialit")
        if any(j in title.lower() for j in junk_patterns):
            continue

        # Extract link
        link = ""
        if container.name == "a":
            link = container.get("href", "")
        else:
            link_el = container.select_one(sel["link"])
            if link_el:
                link = link_el.get("href", "")
            elif title_el.name == "a":
                link = title_el.get("href", "")
            elif title_el.parent and title_el.parent.name == "a":
                link = title_el.parent.get("href", "")

        # Make absolute URL
        if link and not link.startswith("http"):
            base = source["url"].rstrip("/")
            link = f"{base}/{link.lstrip('/')}"

        # Extract summary
        summary = ""
        summary_el = container.select_one(sel["summary"])
        if summary_el and summary_el != title_el:
            summary = summary_el.get_text(strip=True)[:300]

        # Skip non-pickleball content
        combined = (title + " " + summary).lower()
        if not any(kw in combined for kw in ("pickleball", "pickle", "paddle", "raquette", "tournoi", "ppa", "mpl")):
            # Be lenient: if source is pickleball-specific, keep it anyway
            if "pickleball" not in source["url"].lower() and "pickle" not in source["url"].lower():
                continue

        results.append({
            "source": source["name"],
            "title": title,
            "url": link,
            "summary": summary,
            "scraped_at": datetime.now().isoformat(),
        })

    # Deduplicate by title
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for item in results:
        key = re.sub(r"\s+", " ", item["title"].lower().strip())
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


def scrape_all() -> list[dict[str, str]]:
    """Scrape all configured sources and return a list of news items."""
    all_news: list[dict[str, str]] = []

    for source in SOURCES:
        logger.info("Scraping %s (%s)...", source["name"], source["url"])
        html = _fetch_page(source["url"])
        if not html:
            continue

        articles = _extract_articles(html, source)
        logger.info("  -> %d articles found from %s", len(articles), source["name"])
        all_news.extend(articles)

    logger.info("Total scraped: %d articles from %d sources", len(all_news), len(SOURCES))
    return all_news


# ------------------------------------------------------------------
# Cache management
# ------------------------------------------------------------------

def load_cache() -> list[dict[str, str]]:
    """Load the news cache from disk."""
    if NEWS_CACHE.exists():
        try:
            return json.loads(NEWS_CACHE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_cache(news: list[dict[str, str]]) -> None:
    """Save news items to cache, keeping the latest 100."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Merge with existing cache, dedup by URL
    existing = load_cache()
    seen_urls: set[str] = set()
    merged: list[dict[str, str]] = []

    for item in news + existing:  # New items first
        url = item.get("url", "")
        title_key = item["title"].lower().strip()
        if url and url not in seen_urls:
            seen_urls.add(url)
            merged.append(item)
        elif not url and title_key not in {i["title"].lower().strip() for i in merged}:
            merged.append(item)

    # Keep only the 100 most recent
    merged = merged[:100]
    NEWS_CACHE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("News cache updated: %d items", len(merged))


def fetch_and_cache() -> list[dict[str, str]]:
    """Scrape all sources, update cache, return fresh news."""
    news = scrape_all()
    if news:
        save_cache(news)
    return news


def get_news_context(max_items: int = 20) -> str:
    """Build a context string with recent news for agents.

    Returns a Markdown-formatted list of recent headlines.
    """
    cache = load_cache()
    if not cache:
        return "(Aucune actualite recente scrapee.)"

    items = cache[:max_items]
    lines = ["## Actualites pickleball recentes (sources reelles)\n"]
    for i, item in enumerate(items, 1):
        lines.append(f"### {i}. {item['title']}")
        if item.get("summary"):
            lines.append(f"{item['summary']}")
        if item.get("url"):
            lines.append(f"Source: {item['source']} - {item['url']}")
        lines.append("")

    return "\n".join(lines)
