"""
Sophie (Affiliate) - Amazon affiliate monetisation agent.

Identifies monetisation opportunities in existing articles, suggests products,
generates affiliate data, and ensures legal compliance with French regulations.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from agents import hub
from agents.amazon_scraper import get_products_context, load_products_cache
from agents.base_agent import BaseAgent
from agents.config import (
    AMAZON_AFFILIATE_TAG,
    AMAZON_BASE_URL,
    CONTENT_DIR,
    SITE_NAME,
)

logger = logging.getLogger(__name__)


class AffiliateAgent(BaseAgent):
    """Sophie - affiliate monetisation specialist."""

    def __init__(self) -> None:
        super().__init__(
            name="Sophie (Affiliate)",
            role="affiliate",
            description=(
                "Specialiste monetisation. Identifie les opportunites "
                "d'affiliation Amazon dans les articles et ajoute les "
                "recommandations produit."
            ),
        )

    def get_system_prompt(self) -> str:
        return f"""\
Tu es Sophie, l'experte monetisation et affiliation de {SITE_NAME}.

Ton role :
- Analyser les articles existants pour identifier les opportunites d'affiliation.
- Suggerer des produits Amazon pertinents pour chaque article.
- Creer des donnees produit structurees (nom, termes de recherche, fourchette de prix).
- S'assurer que chaque article contenant des liens affilies inclut une
  mention legale conforme a la reglementation francaise.
- Maximiser le revenu sans compromettre la qualite editoriale.

Tag affilie Amazon : {AMAZON_AFFILIATE_TAG}
URL base Amazon : {AMAZON_BASE_URL}

Produits populaires dans le pickleball :
- Raquettes/Paddles : Selkirk Amped, JOOLA Ben Johns Hyperion, HEAD Radical,
  Franklin Ben Johns, Onix Graphite Z5, Paddletek Tempest Wave.
- Chaussures : Asics Gel-Renma, K-Swiss Express Light, New Balance Fresh Foam,
  Nike Court Vapor, Skechers Viper Court.
- Accessoires : sacs de pickleball, grips, surgrips, balles Franklin X-40,
  balles Dura Fast 40, filets portables, protections.
- Textile : shorts, t-shirts techniques, visières, casquettes.

Format de sortie OBLIGATOIRE (Markdown) :

## Analyse des opportunites
<quels articles ont un potentiel de monetisation>

## Recommandations produits par article
### Article : <nom-fichier.md>
#### Produit 1 : <nom du produit>
- **Recherche Amazon** : <termes de recherche>
- **Fourchette de prix** : XX - XX EUR
- **Pertinence** : haute/moyenne
- **Placement** : <ou dans l'article>

#### Frontmatter a ajouter :
```yaml
affiliateProducts:
  - name: "<nom>"
    searchTerm: "<recherche Amazon>"
    priceRange: "XX-XX EUR"
    tag: "{AMAZON_AFFILIATE_TAG}"
```

## Mention legale
Le texte suivant DOIT apparaitre dans chaque article contenant des
recommandations produit :

> *Cet article contient des liens d'affiliation. Si vous effectuez un achat
> via ces liens, nous percevons une petite commission sans cout supplementaire
> pour vous. Cela nous aide a maintenir ce site. Merci de votre soutien !*

## Actions a effectuer
- [ ] Lea (Content) : <modifications a appliquer>

Ecris en francais.
"""

    async def run(self, context: str) -> dict[str, Any]:
        # Scan existing articles
        articles_info = self._scan_articles()

        # Add real Amazon product data
        products_ctx = get_products_context(max_items=25)

        enriched = (
            context
            + "\n\n## Articles existants a analyser\n"
            + (articles_info if articles_info else "(aucun article)")
            + "\n\n" + products_ctx
        )

        response = await self.think(enriched, max_tokens=4096)

        # Attempt to auto-inject affiliate disclosure into articles
        injected_disclosures = self._inject_disclosures()
        injected_products = self._inject_real_products()

        hub.write_directive(self.name, "BASSE", response)
        hub.log_action(
            self.name,
            f"Affiliation: {injected_products} produits + {injected_disclosures} disclosures injectes",
            details=response,
            status="ok",
        )

        return {
            "status": "ok",
            "summary": (
                f"Affiliation: {injected_products} produits reels injectes, "
                f"{injected_disclosures} disclosures ajoutees."
            ),
            "affiliate_report": response,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _scan_articles() -> str:
        """Return a summary of each existing article."""
        if not CONTENT_DIR.exists():
            return ""
        parts: list[str] = []
        for f in sorted(CONTENT_DIR.glob("*.md")):
            text = f.read_text(encoding="utf-8", errors="replace")
            # First 500 chars give enough context
            parts.append(f"### {f.name}\n```\n{text[:500]}\n```")
        return "\n\n".join(parts)

    @staticmethod
    def _inject_disclosures() -> int:
        """Add affiliate disclosure to articles that mention products but lack one.

        Returns the number of articles modified.
        """
        if not CONTENT_DIR.exists():
            return 0

        disclosure = (
            "\n\n---\n\n"
            "*Cet article contient des liens d'affiliation. Si vous effectuez "
            "un achat via ces liens, nous percevons une petite commission sans "
            "cout supplementaire pour vous. Cela nous aide a maintenir ce site. "
            "Merci de votre soutien !*\n"
        )

        product_keywords = [
            "raquette",
            "paddle",
            "chaussure",
            "sac de pickleball",
            "grip",
            "balle",
            "filet",
            "acheter",
            "prix",
            "amazon",
            "produit",
        ]

        count = 0
        for f in CONTENT_DIR.glob("*.md"):
            text = f.read_text(encoding="utf-8", errors="replace")
            lower = text.lower()
            has_products = any(kw in lower for kw in product_keywords)
            has_disclosure = "liens d'affiliation" in lower

            if has_products and not has_disclosure:
                text += disclosure
                f.write_text(text, encoding="utf-8")
                count += 1
                logger.info("Disclosure added to %s", f.name)

        return count

    @staticmethod
    def _inject_real_products() -> int:
        """Inject real Amazon product blocks into articles that mention equipment.

        Looks at article keywords and matches them against cached Amazon products.
        Adds a product recommendation section with real prices and affiliate links.
        """
        products = load_products_cache()
        if not products:
            return 0

        if not CONTENT_DIR.exists():
            return 0

        # Build keyword -> products index
        product_index: dict[str, list] = {}
        for p in products:
            for kw in ("raquette", "paddle", "chaussure", "balle", "sac", "filet", "grip"):
                if kw in p.get("title", "").lower() or kw in p.get("search_query", "").lower():
                    product_index.setdefault(kw, []).append(p)

        count = 0
        for f in CONTENT_DIR.glob("*.md"):
            text = f.read_text(encoding="utf-8", errors="replace")
            lower = text.lower()

            # Skip if already has product recommendations with prices
            if "amazon.fr/dp/" in lower:
                continue

            # Find matching keywords in article
            matched_products: list[dict] = []
            for kw, prods in product_index.items():
                if kw in lower:
                    for p in prods[:2]:  # Max 2 per keyword
                        if p not in matched_products:
                            matched_products.append(p)
                    if len(matched_products) >= 3:
                        break

            if not matched_products:
                continue

            # Build product recommendation block
            block_lines = [
                "\n\n---\n",
                "### Nos recommandations produits\n",
            ]
            for p in matched_products[:3]:
                price_str = f" - **{p['price']}**" if p.get("price") else ""
                rating_str = f" ({p['rating']}/5)" if p.get("rating") else ""
                block_lines.append(
                    f"- [{p['title'][:80]}]({p['url']}){price_str}{rating_str}"
                )

            product_block = "\n".join(block_lines) + "\n"

            # Insert before disclosure or at end
            if "liens d'affiliation" in lower:
                # Insert before the disclosure
                disclosure_idx = text.lower().find("*cet article contient des liens")
                if disclosure_idx > 0:
                    # Find the --- before the disclosure
                    separator_idx = text.rfind("---", 0, disclosure_idx)
                    if separator_idx > 0:
                        text = text[:separator_idx] + product_block + "\n" + text[separator_idx:]
                    else:
                        text = text[:disclosure_idx] + product_block + "\n" + text[disclosure_idx:]
                else:
                    text = text.rstrip() + product_block
            else:
                text = text.rstrip() + product_block

            f.write_text(text, encoding="utf-8")
            count += len(matched_products[:3])
            logger.info(
                "Injected %d real products into %s",
                len(matched_products[:3]),
                f.name,
            )

        return count
