"""
Amazon product scraper for pickleball equipment.

Searches Amazon.fr for real pickleball products and caches results.
Used by Sophie (Affiliate) to inject real product data (name, price, URL,
rating) into articles instead of guessing.

Uses the Amazon search page — no API key required.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

from agents.config import AMAZON_AFFILIATE_TAG, OUTPUT_DIR

logger = logging.getLogger(__name__)

PRODUCTS_CACHE = OUTPUT_DIR / "amazon_products.json"
REQUEST_TIMEOUT = 15

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Pre-defined search queries for pickleball products
PRODUCT_SEARCHES = [
    {"query": "raquette pickleball", "category": "equipement"},
    {"query": "paddle pickleball", "category": "equipement"},
    {"query": "balle pickleball", "category": "equipement"},
    {"query": "filet pickleball", "category": "equipement"},
    {"query": "chaussures pickleball", "category": "equipement"},
    {"query": "sac pickleball", "category": "equipement"},
    {"query": "grip surgrip pickleball", "category": "equipement"},
]


def _build_affiliate_url(asin: str) -> str:
    """Build an Amazon affiliate URL from an ASIN."""
    return f"https://www.amazon.fr/dp/{asin}?tag={AMAZON_AFFILIATE_TAG}"


def _search_amazon(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Search Amazon.fr and extract product information."""
    search_url = "https://www.amazon.fr/s"
    params = {"k": query, "__mk_fr_FR": "\u00c5M\u00c5\u017d\u00d5\u00d1"}

    try:
        resp = requests.get(
            search_url,
            params=params,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("Amazon search failed for '%s': %s", query, exc)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    products: list[dict[str, Any]] = []

    # Find product containers
    result_items = soup.select("[data-component-type='s-search-result']")

    for item in result_items[:max_results]:
        try:
            product = _parse_product_card(item, query)
            if product:
                products.append(product)
        except Exception as exc:
            logger.debug("Failed to parse product card: %s", exc)
            continue

    return products


def _parse_product_card(item: Any, search_query: str) -> dict[str, Any] | None:
    """Parse a single Amazon search result card."""
    # ASIN
    asin = item.get("data-asin", "")
    if not asin:
        return None

    # Title
    title_el = item.select_one("h2 a span, h2 span")
    if not title_el:
        return None
    title = title_el.get_text(strip=True)
    if not title or len(title) < 5:
        return None

    # Price
    price = ""
    price_whole = item.select_one(".a-price-whole")
    price_frac = item.select_one(".a-price-fraction")
    if price_whole:
        whole = price_whole.get_text(strip=True).replace(",", "").replace(".", "")
        frac = price_frac.get_text(strip=True) if price_frac else "00"
        price = f"{whole},{frac} EUR"

    # Rating
    rating = ""
    rating_el = item.select_one(".a-icon-alt")
    if rating_el:
        rating_text = rating_el.get_text(strip=True)
        rating_match = re.search(r"([\d,]+)\s*sur\s*5", rating_text)
        if rating_match:
            rating = rating_match.group(1)

    # Number of reviews
    reviews = ""
    reviews_el = item.select_one(".a-size-base.s-underline-text")
    if reviews_el:
        reviews = reviews_el.get_text(strip=True).replace("\xa0", "")

    # Image URL
    image = ""
    img_el = item.select_one("img.s-image")
    if img_el:
        image = img_el.get("src", "")

    # Product URL
    link_el = item.select_one("h2 a")
    product_url = ""
    if link_el:
        href = link_el.get("href", "")
        if href:
            product_url = f"https://www.amazon.fr{href}"

    return {
        "asin": asin,
        "title": title,
        "price": price,
        "rating": rating,
        "reviews": reviews,
        "image": image,
        "url": _build_affiliate_url(asin),
        "product_url": product_url,
        "search_query": search_query,
        "scraped_at": datetime.now().isoformat(),
    }


def scrape_all_products() -> list[dict[str, Any]]:
    """Scrape Amazon for all predefined pickleball product searches."""
    all_products: list[dict[str, Any]] = []

    for search in PRODUCT_SEARCHES:
        query = search["query"]
        category = search["category"]
        logger.info("Searching Amazon.fr for '%s'...", query)

        products = _search_amazon(query, max_results=5)
        for p in products:
            p["category"] = category

        logger.info("  -> %d products found", len(products))
        all_products.extend(products)

        # Polite delay between requests
        time.sleep(2)

    logger.info("Total: %d products scraped from Amazon", len(all_products))
    return all_products


# ------------------------------------------------------------------
# Cache
# ------------------------------------------------------------------

def load_products_cache() -> list[dict[str, Any]]:
    """Load cached products from disk."""
    if PRODUCTS_CACHE.exists():
        try:
            return json.loads(PRODUCTS_CACHE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_products_cache(products: list[dict[str, Any]]) -> None:
    """Save products to cache, deduplicating by ASIN."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    existing = load_products_cache()
    seen_asins: set[str] = set()
    merged: list[dict[str, Any]] = []

    # New products take priority
    for p in products + existing:
        asin = p.get("asin", "")
        if asin and asin not in seen_asins:
            seen_asins.add(asin)
            merged.append(p)

    # Keep latest 200
    merged = merged[:200]
    PRODUCTS_CACHE.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Amazon product cache updated: %d products", len(merged))


def fetch_and_cache_products() -> list[dict[str, Any]]:
    """Scrape Amazon products and update cache."""
    products = scrape_all_products()
    if products:
        save_products_cache(products)
    return products


def get_products_context(max_items: int = 20) -> str:
    """Build a context string with real Amazon products for agents."""
    cache = load_products_cache()
    if not cache:
        return "(Aucun produit Amazon en cache.)"

    items = cache[:max_items]
    lines = ["## Produits Amazon reels (scrapes)\n"]
    for i, p in enumerate(items, 1):
        lines.append(f"### {i}. {p['title'][:80]}")
        if p.get("price"):
            lines.append(f"- **Prix** : {p['price']}")
        if p.get("rating"):
            lines.append(f"- **Note** : {p['rating']}/5 ({p.get('reviews', '?')} avis)")
        lines.append(f"- **ASIN** : {p['asin']}")
        lines.append(f"- **Lien affilie** : {p['url']}")
        lines.append("")

    return "\n".join(lines)


def get_products_for_article(keywords: list[str], max_products: int = 3) -> list[dict[str, Any]]:
    """Find cached products matching article keywords.

    Used by the affiliate agent to inject real products into articles.
    """
    cache = load_products_cache()
    if not cache:
        return []

    scored: list[tuple[int, dict[str, Any]]] = []
    for product in cache:
        title_lower = product["title"].lower()
        query_lower = product.get("search_query", "").lower()
        score = sum(
            1 for kw in keywords
            if kw.lower() in title_lower or kw.lower() in query_lower
        )
        if score > 0:
            scored.append((score, product))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:max_products]]
