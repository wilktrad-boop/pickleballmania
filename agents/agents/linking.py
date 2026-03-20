"""
Lucas (Linking) - Internal linking agent.

Scans all published articles and injects internal links between them
to improve SEO and user navigation. Runs after the content agent
to link new articles with existing ones.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

from agents import hub
from agents.base_agent import BaseAgent
from agents.config import CONTENT_DIR, SITE_NAME, SITE_URL

logger = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    """Convert a French title to a URL-safe slug."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


class LinkingAgent(BaseAgent):
    """Lucas - internal linking specialist who weaves articles together."""

    def __init__(self) -> None:
        super().__init__(
            name="Lucas (Linking)",
            role="linking",
            description=(
                "Specialiste maillage interne. Ajoute des liens entre "
                "les articles pour ameliorer le SEO et la navigation."
            ),
        )

    def get_system_prompt(self) -> str:
        return f"""\
Tu es Lucas, le specialiste du maillage interne de {SITE_NAME} ({SITE_URL}).

Ton role :
- Analyser tous les articles existants du site.
- Identifier les opportunites de maillage interne (liens entre articles).
- Proposer des liens pertinents bases sur les themes, categories et mots-cles communs.

Regles strictes :
1. Chaque article devrait avoir entre 2 et 4 liens internes.
2. Les liens doivent etre NATURELS et pertinents (pas de liens forces).
3. Utiliser des ancres descriptives (pas "cliquez ici").
4. Privilegier les liens vers des articles de categories complementaires.
5. Ne pas creer de liens circulaires excessifs entre 2 articles.
6. Le format des liens internes est : [texte ancre](/blog/slug-de-l-article/)

Format de sortie OBLIGATOIRE :

Pour chaque article a modifier, produis un bloc ainsi :

===LINK_START===
**Fichier** : <nom-du-fichier.md>
**Liens a ajouter** :
1. Apres le paragraphe contenant "<extrait du paragraphe>" ajouter :
   [texte ancre](/blog/slug/)
2. ...
===LINK_END===

Analyse tous les articles et propose des liens pertinents.
"""

    async def run(self, context: str) -> dict[str, Any]:
        # Build article inventory
        inventory = self._build_inventory()
        if len(inventory) < 2:
            return {
                "status": "ok",
                "summary": "Pas assez d'articles pour le maillage (minimum 2).",
            }

        # Build context with all articles
        articles_ctx = self._format_inventory(inventory)
        enriched = context + "\n\n" + articles_ctx

        # Ask Claude for linking suggestions
        response = await self.think(enriched, max_tokens=4096)

        # Auto-inject links based on inventory analysis
        injected = self._auto_inject_links(inventory)

        hub.log_action(
            self.name,
            f"Maillage interne: {injected} liens ajoutes automatiquement",
            details=response[:500],
            status="ok",
        )

        return {
            "status": "ok",
            "summary": f"Maillage interne: {injected} liens ajoutes. Suggestions Claude generees.",
            "links_added": injected,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_inventory() -> list[dict[str, Any]]:
        """Build a complete inventory of all published articles."""
        if not CONTENT_DIR.exists():
            return []

        articles: list[dict[str, Any]] = []
        for f in sorted(CONTENT_DIR.glob("*.md")):
            text = f.read_text(encoding="utf-8", errors="replace")

            # Parse frontmatter
            fm_match = re.match(r"---\n(.*?)\n---\n(.*)", text, re.DOTALL)
            if not fm_match:
                continue

            frontmatter = fm_match.group(1)
            body = fm_match.group(2)

            # Extract metadata
            title_match = re.search(r'title:\s*"(.+?)"', frontmatter)
            title = title_match.group(1) if title_match else f.stem

            cat_match = re.search(r'category:\s*"?(\w+)"?', frontmatter)
            category = cat_match.group(1) if cat_match else ""

            tags_match = re.search(r'tags:\s*\[(.+?)\]', frontmatter)
            tags: list[str] = []
            if tags_match:
                tags = [t.strip().strip('"\'') for t in tags_match.group(1).split(",")]

            # Build slug from filename (strip date prefix and .md)
            slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", f.stem)

            # Count existing internal links
            internal_links = len(re.findall(r'\[.+?\]\(/blog/', body))

            # Extract key phrases (H2/H3 headings + first paragraph)
            headings = re.findall(r'^#{2,3}\s+(.+)$', body, re.MULTILINE)
            first_para = ""
            for line in body.split("\n"):
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("---"):
                    first_para = line[:200]
                    break

            articles.append({
                "filename": f.name,
                "filepath": str(f),
                "title": title,
                "slug": slug,
                "category": category,
                "tags": tags,
                "headings": headings,
                "first_para": first_para,
                "internal_links": internal_links,
                "body_length": len(body),
                "body": body,
                "full_text": text,
            })

        return articles

    @staticmethod
    def _format_inventory(inventory: list[dict[str, Any]]) -> str:
        """Format article inventory for Claude context."""
        lines = [
            f"## Inventaire des articles ({len(inventory)} articles)\n",
            "Chaque article peut etre lie via : [ancre](/blog/<slug>/)\n",
        ]
        for a in inventory:
            lines.append(f"### {a['filename']}")
            lines.append(f"- **Titre** : {a['title']}")
            lines.append(f"- **Slug** : /blog/{a['slug']}/")
            lines.append(f"- **Categorie** : {a['category']}")
            lines.append(f"- **Tags** : {', '.join(a['tags'])}")
            lines.append(f"- **Liens internes existants** : {a['internal_links']}")
            lines.append(f"- **Sous-titres** : {', '.join(a['headings'][:5])}")
            lines.append(f"- **Extrait** : {a['first_para'][:150]}")
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _auto_inject_links(inventory: list[dict[str, Any]]) -> int:
        """Automatically inject internal links between related articles.

        For each article with fewer than 2 internal links, find related
        articles and insert a "A lire aussi" section before the conclusion.
        """
        total_injected = 0

        for article in inventory:
            if article["internal_links"] >= 2:
                continue  # Already has enough links

            # Find related articles
            related = LinkingAgent._find_related(article, inventory)
            if not related:
                continue

            # Build the "A lire aussi" block
            links_md = "\n".join(
                f"- [{r['title']}](/blog/{r['slug']}/)"
                for r in related[:3]
            )
            read_also = f"\n\n### A lire aussi\n\n{links_md}\n"

            # Insert before the last heading or at the end
            body = article["body"]

            # Try to insert before conclusion-like headings
            conclusion_patterns = [
                r'\n(#{2,3}\s+[Cc]onclusion)',
                r'\n(#{2,3}\s+[Ee]n resume)',
                r'\n(#{2,3}\s+[Pp]our conclure)',
                r'\n(#{2,3}\s+[Nn]otre avis)',
                r'\n(#{2,3}\s+[Mm]ot de la fin)',
            ]

            inserted = False
            for pattern in conclusion_patterns:
                match = re.search(pattern, body)
                if match:
                    insert_pos = match.start()
                    new_body = body[:insert_pos] + read_also + body[insert_pos:]
                    inserted = True
                    break

            if not inserted:
                # Insert before the last paragraph
                new_body = body.rstrip() + read_also

            # Write back
            new_text = article["full_text"].replace(body, new_body, 1)
            Path(article["filepath"]).write_text(new_text, encoding="utf-8")
            total_injected += len(related[:3])
            logger.info(
                "Added %d internal links to %s",
                len(related[:3]),
                article["filename"],
            )

        return total_injected

    @staticmethod
    def _find_related(
        target: dict[str, Any],
        inventory: list[dict[str, Any]],
        max_results: int = 3,
    ) -> list[dict[str, Any]]:
        """Find articles related to the target based on category, tags, title."""
        scored: list[tuple[int, dict[str, Any]]] = []

        target_words = set(target["title"].lower().split())
        target_tags = set(t.lower() for t in target["tags"])

        for article in inventory:
            if article["filename"] == target["filename"]:
                continue

            score = 0

            # Same category = +3
            if article["category"] == target["category"] and target["category"]:
                score += 3

            # Shared tags = +2 each
            article_tags = set(t.lower() for t in article["tags"])
            shared_tags = target_tags & article_tags
            score += len(shared_tags) * 2

            # Shared title words (excluding stopwords) = +1 each
            stopwords = {"de", "du", "le", "la", "les", "un", "une", "des", "et",
                         "en", "pour", "au", "aux", "a", "nos", "notre", "votre",
                         "ce", "cette", "ces", "que", "qui", "ou", "sur", "avec"}
            article_words = set(article["title"].lower().split())
            shared_words = (target_words & article_words) - stopwords
            score += len(shared_words)

            if score > 0:
                scored.append((score, article))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [a for _, a in scored[:max_results]]
