"""
Lea (Content) - Content writer agent.

Reads article briefs from the strategy agent's directives and produces
full Markdown articles with Astro-compatible frontmatter.  Articles are
saved directly into ``src/content/blog/``.
"""

from __future__ import annotations

import logging
import random
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

from agents import hub
from agents.base_agent import BaseAgent
from agents.config import CATEGORIES, CONTENT_DIR, IMAGES_DIR, SITE_NAME, SITE_URL

logger = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    """Convert a French title to a URL-safe slug."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


class ContentAgent(BaseAgent):
    """Lea - the content writer producing SEO-optimised French articles."""

    def __init__(self) -> None:
        super().__init__(
            name="Lea (Content)",
            role="content",
            description=(
                "Redactrice de contenu. Ecrit des articles complets en "
                "francais, optimises SEO, au format Markdown/Astro."
            ),
        )

    def get_system_prompt(self) -> str:
        return f"""\
Tu es Lea, redactrice en chef de {SITE_NAME} ({SITE_URL}).

Ton role :
- Lire les briefs d'articles fournis par Clara (Strategy) et les
  recommandations SEO de Camille.
- Ecrire des articles complets, engageants et optimises pour le SEO.
- Respecter le format Astro/Markdown avec frontmatter YAML.
- Ecrire EXCLUSIVEMENT en francais.

Regles de redaction :
1. Chaque article doit faire entre 800 et 1500 mots.
2. Utiliser des titres H2 et H3 pour structurer.
3. Inclure une introduction accrocheuse (2-3 phrases).
4. Terminer par une conclusion avec appel a l'action.
5. Utiliser un ton expert mais accessible.
6. Integrer naturellement les mots-cles SEO (pas de keyword stuffing).
7. Ajouter des listes a puces quand c'est pertinent.

Format de sortie OBLIGATOIRE :
Tu dois produire UN OU PLUSIEURS blocs, chacun delimite exactement ainsi :

===ARTICLE_START===
---
title: "Titre de l'article"
description: "Meta description (max 160 caracteres)"
pubDate: "{datetime.now().strftime('%Y-%m-%d')}"
category: "<une des categories>"
tags: ["tag1", "tag2"]
draft: false
---

<contenu Markdown de l'article>
===ARTICLE_END===

Categories valides : {', '.join(CATEGORIES)}

Important :
- Ne mets AUCUN texte en dehors des blocs ===ARTICLE_START===...===ARTICLE_END===
  sauf un bref resume avant.
- Chaque article doit etre complet et pret a publier.
"""

    async def run(self, context: str) -> dict[str, Any]:
        response = await self.think(context, max_tokens=8192)

        # Parse articles from the response
        articles = self._parse_articles(response)

        if not articles:
            logger.warning("[%s] No articles parsed from response.", self.name)
            return {
                "status": "error",
                "summary": "Aucun article n'a pu etre extrait de la reponse.",
                "articles": [],
            }

        saved: list[str] = []
        for article in articles:
            filepath = self._save_article(article)
            if filepath:
                saved.append(filepath.name)

        # Update state
        state = hub.get_state()
        current_count = state.get("articles_count", 0)
        hub.update_state("articles_count", current_count + len(saved))

        # Track covered categories
        covered = set(state.get("categories_covered", []))
        for a in articles:
            cat = a.get("category", "")
            if cat:
                covered.add(cat)
        hub.update_state("categories_covered", sorted(covered))

        summary = f"{len(saved)} article(s) crees : {', '.join(saved)}"
        hub.log_action(self.name, summary, status="ok")

        return {
            "status": "ok",
            "summary": summary,
            "articles": saved,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_articles(text: str) -> list[dict[str, str]]:
        """Extract article blocks from the LLM response."""
        pattern = r"===ARTICLE_START===\s*\n(---\n.*?\n---\n.*?)===ARTICLE_END==="
        matches = re.findall(pattern, text, re.DOTALL)

        articles: list[dict[str, str]] = []
        for raw in matches:
            # Split frontmatter from body
            fm_match = re.match(r"---\n(.*?)\n---\n(.*)", raw, re.DOTALL)
            if not fm_match:
                continue

            frontmatter = fm_match.group(1)
            body = fm_match.group(2).strip()

            # Extract title for slug
            title_match = re.search(r'title:\s*"(.+?)"', frontmatter)
            title = title_match.group(1) if title_match else "article"

            # Extract category
            cat_match = re.search(r"category:\s*\"?(\w+)\"?", frontmatter)
            category = cat_match.group(1) if cat_match else ""

            articles.append(
                {
                    "title": title,
                    "category": category,
                    "frontmatter": frontmatter,
                    "body": body,
                    "raw": raw,
                }
            )
        return articles

    @staticmethod
    def _pick_image(category: str) -> str | None:
        """Pick an unused image from the category's image folder.

        Looks in ``src/assets/blog/{category}/`` first, then falls back
        to ``src/assets/blog/general/``.  Returns a relative import path
        like ``~/assets/blog/equipement/raquette.jpg`` (Astro alias) or
        *None* if no images are available.

        An image is considered "used" if its filename already appears in
        any existing article's frontmatter.
        """
        IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif"}

        # Collect already-used image filenames from existing articles
        used_images: set[str] = set()
        if CONTENT_DIR.exists():
            for md_file in CONTENT_DIR.glob("*.md"):
                try:
                    text = md_file.read_text(encoding="utf-8", errors="replace")
                    # Match heroImage lines in frontmatter
                    match = re.search(r"heroImage:\s*[\"']?(.+?)[\"']?\s*$", text, re.MULTILINE)
                    if match:
                        # Extract just the filename
                        used_images.add(Path(match.group(1)).name)
                except Exception:
                    continue

        # Search in category folder, then general
        search_folders = []
        if category:
            cat_folder = IMAGES_DIR / category
            if cat_folder.is_dir():
                search_folders.append(cat_folder)
        general_folder = IMAGES_DIR / "general"
        if general_folder.is_dir():
            search_folders.append(general_folder)

        for folder in search_folders:
            available = [
                f for f in folder.iterdir()
                if f.is_file()
                and f.suffix.lower() in IMAGE_EXTENSIONS
                and f.name not in used_images
            ]
            if available:
                chosen = random.choice(available)
                # Return Astro-compatible path relative to src/
                rel = chosen.relative_to(IMAGES_DIR.parent.parent)  # relative to src/
                return f"~/{ rel.as_posix()}"

        return None

    @staticmethod
    def _save_article(article: dict[str, str]) -> Any:
        """Write an article to the content directory. Returns the Path or None."""
        CONTENT_DIR.mkdir(parents=True, exist_ok=True)

        slug = _slugify(article["title"])
        date_prefix = datetime.now().strftime("%Y-%m-%d")
        filename = f"{date_prefix}-{slug}.md"
        filepath = CONTENT_DIR / filename

        # Avoid overwriting
        counter = 1
        while filepath.exists():
            filename = f"{date_prefix}-{slug}-{counter}.md"
            filepath = CONTENT_DIR / filename
            counter += 1

        frontmatter = article["frontmatter"]

        # Inject heroImage if an image is available and not already set
        if "heroImage" not in frontmatter:
            image_path = ContentAgent._pick_image(article.get("category", ""))
            if image_path:
                frontmatter += f'\nheroImage: "{image_path}"'
                logger.info("Image assigned: %s -> %s", image_path, filename)

        content = f"---\n{frontmatter}\n---\n\n{article['body']}\n"
        filepath.write_text(content, encoding="utf-8")
        logger.info("Article saved: %s", filepath)
        return filepath
