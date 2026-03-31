"""
Image generator using Replicate API (Flux model).

Generates hero images for articles that don't have one.
Saves images to src/assets/blog/{category}/ and updates frontmatter.
"""

from __future__ import annotations

import logging
import re
import time
import requests
from pathlib import Path
from typing import Any

from agents.config import (
    CONTENT_DIR,
    IMAGES_DIR,
    REPLICATE_API_TOKEN,
    SITE_NAME,
)

logger = logging.getLogger(__name__)

REPLICATE_API_URL = "https://api.replicate.com/v1/predictions"
# Flux Schnell — fast, high quality, free on Replicate
MODEL_VERSION = "black-forest-labs/flux-schnell"


def _generate_image(prompt: str, filename: str, output_dir: Path) -> Path | None:
    """Generate an image via Replicate and save it locally."""
    if not REPLICATE_API_TOKEN:
        logger.warning("REPLICATE_API_TOKEN not set, skipping image generation.")
        return None

    headers = {
        "Authorization": f"Bearer {REPLICATE_API_TOKEN}",
        "Content-Type": "application/json",
    }

    # Create prediction
    payload = {
        "version": "5599ed30703defd1d160a25a63321b4dec97101d98b4674bcc56e41f62f35637",
        "input": {
            "prompt": prompt,
            "num_outputs": 1,
            "aspect_ratio": "16:9",
            "output_format": "webp",
            "output_quality": 90,
        },
    }

    try:
        resp = requests.post(REPLICATE_API_URL, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        prediction = resp.json()
    except Exception as exc:
        logger.error("Replicate API error: %s", exc)
        return None

    # Poll for result
    prediction_url = prediction.get("urls", {}).get("get", "")
    if not prediction_url:
        logger.error("No prediction URL returned")
        return None

    for _ in range(60):  # max 2 minutes
        time.sleep(2)
        try:
            poll = requests.get(prediction_url, headers=headers, timeout=15)
            poll.raise_for_status()
            data = poll.json()
        except Exception:
            continue

        status = data.get("status", "")
        if status == "succeeded":
            output = data.get("output", [])
            if output:
                image_url = output[0] if isinstance(output, list) else output
                return _download_image(image_url, filename, output_dir)
            break
        elif status == "failed":
            logger.error("Replicate prediction failed: %s", data.get("error", ""))
            break

    return None


def _download_image(url: str, filename: str, output_dir: Path) -> Path | None:
    """Download an image from URL and save locally."""
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()

        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / filename
        filepath.write_bytes(resp.content)
        logger.info("Image saved: %s (%d KB)", filepath, len(resp.content) // 1024)
        return filepath
    except Exception as exc:
        logger.error("Failed to download image: %s", exc)
        return None


def _build_prompt(title: str, category: str, site_theme: str) -> str:
    """Build a Flux image generation prompt from article metadata."""
    category_styles = {
        "actualites": "dynamic sports photography, pickleball tournament action shot, professional athletes on court",
        "tests": "product photography, pickleball paddle close-up, studio lighting, clean background",
        "conseils": "pickleball court training scene, player practicing technique, warm coaching atmosphere",
        "equipement": "pickleball gear flat lay, paddles and balls arrangement, modern sports aesthetic",
        "tournois": "pickleball tournament arena, outdoor court, crowd cheering, dramatic lighting",
        "debuter": "beginner-friendly pickleball scene, welcoming court, casual players having fun",
    }

    style = category_styles.get(category, "pickleball sport scene, vibrant and modern")

    return (
        f"{style}, inspired by: {title}, "
        f"professional sports photography, high quality, 4k, vibrant colors, "
        f"modern editorial style, no text overlay, no watermark"
    )


def _slugify_filename(title: str) -> str:
    """Create a safe filename from title."""
    import unicodedata
    text = unicodedata.normalize("NFKD", title)
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:50]


def generate_missing_images() -> int:
    """Scan articles and generate images for those without a heroImage.

    Returns the number of images generated.
    """
    if not REPLICATE_API_TOKEN:
        logger.info("Replicate API token not configured, skipping image generation.")
        return 0

    if not CONTENT_DIR.exists():
        return 0

    count = 0
    for md_file in sorted(CONTENT_DIR.glob("*.md")):
        text = md_file.read_text(encoding="utf-8", errors="replace")

        # Skip if already has heroImage
        if re.search(r"heroImage:", text):
            continue

        # Extract metadata
        title_match = re.search(r'title:\s*"(.+?)"', text)
        title = title_match.group(1) if title_match else md_file.stem

        cat_match = re.search(r'category:\s*"?(\w+)"?', text)
        category = cat_match.group(1) if cat_match else "general"

        # Generate image
        prompt = _build_prompt(title, category, SITE_NAME)
        slug = _slugify_filename(title)
        filename = f"{slug}.webp"
        output_dir = IMAGES_DIR / category

        logger.info("Generating image for '%s' (category: %s)...", title[:50], category)
        filepath = _generate_image(prompt, filename, output_dir)

        if filepath:
            # Update frontmatter with heroImage
            rel_path = filepath.relative_to(IMAGES_DIR.parent.parent)  # relative to src/
            astro_path = f"~/{rel_path.as_posix()}"

            # Insert heroImage in frontmatter
            text = text.replace(
                f'category: "{category}"',
                f'category: "{category}"\nheroImage: "{astro_path}"',
                1,
            )
            # Fallback if no quotes around category
            if "heroImage:" not in text:
                text = text.replace(
                    f"category: {category}",
                    f"category: {category}\nheroImage: \"{astro_path}\"",
                    1,
                )

            md_file.write_text(text, encoding="utf-8")
            logger.info("heroImage added to %s: %s", md_file.name, astro_path)
            count += 1

            # Polite delay between generations
            time.sleep(1)

    logger.info("Total: %d images generated", count)
    return count
