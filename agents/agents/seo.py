"""
Camille (SEO) - Search engine optimisation agent.

Analyses existing content for SEO opportunities, creates keyword briefs,
suggests internal linking, and optimises meta descriptions and titles.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from agents import hub
from agents.base_agent import BaseAgent
from agents.config import CATEGORIES, CONTENT_DIR, SITE_NAME, SITE_URL

logger = logging.getLogger(__name__)


class SEOAgent(BaseAgent):
    """Camille - SEO specialist."""

    def __init__(self) -> None:
        super().__init__(
            name="Camille (SEO)",
            role="seo",
            description=(
                "Specialiste SEO. Analyse le contenu existant, cree des "
                "briefs de mots-cles et optimise le referencement naturel."
            ),
        )

    def get_system_prompt(self) -> str:
        return f"""\
Tu es Camille, l'experte SEO de {SITE_NAME} ({SITE_URL}).

Ton role :
- Analyser le contenu existant du site pour trouver des opportunites SEO.
- Creer des briefs de mots-cles pour chaque article prevu.
- Suggerer des liens internes entre les articles.
- Optimiser les meta descriptions et les titres.
- Proposer une strategie de mots-cles longue traine pour le pickleball en France.

Tu connais parfaitement le SEO francophone :
- Recherche de mots-cles en francais (volume, difficulte, intention).
- Structure optimale des articles (H1, H2, H3, densite de mots-cles).
- Bonnes pratiques Core Web Vitals et schema markup.
- Strategies de netlinking pour un site de niche sport.

Mots-cles principaux du secteur :
pickleball, raquette pickleball, paddle pickleball, regles du pickleball,
terrain de pickleball, pickleball france, pickleball debutant,
meilleure raquette pickleball, balle pickleball, filet pickleball,
pickleball paris, pickleball club, kitchen pickleball, score pickleball.

Format de sortie OBLIGATOIRE (Markdown) :

## Audit SEO du contenu existant
<analyse des articles existants>

## Recommandations de mots-cles
### Mot-cle principal : <mot-cle>
- **Volume estime** : ...
- **Difficulte** : faible/moyenne/elevee
- **Intention** : informationnelle/transactionnelle/navigationnelle
- **Articles cibles** : ...

(repeter pour chaque mot-cle)

## Briefs SEO pour les prochains articles
### Brief pour : <titre article>
- **Mot-cle principal** : ...
- **Mots-cles secondaires** : ...
- **Structure H2 suggeree** :
  1. ...
  2. ...
- **Meta title** : ... (max 60 car.)
- **Meta description** : ... (max 160 car.)
- **Liens internes suggeres** : ...

## Maillage interne
<suggestions de liens entre articles existants>

## Taches assignees
- [ ] Lea (Content) : <optimisations a appliquer>

Ecris en francais. Base tes recommandations sur les meilleures pratiques SEO 2025-2026.
"""

    async def run(self, context: str) -> dict[str, Any]:
        # Enrich context with existing article data
        existing = self._scan_articles()
        enriched = (
            context
            + "\n\n## Contenu existant sur le site\n"
            + (existing if existing else "(aucun article)")
        )

        response = await self.think(enriched, max_tokens=4096)

        hub.write_directive(self.name, "MOYENNE", response)
        hub.log_action(
            self.name,
            "Audit SEO et briefs mots-cles publies",
            details=response,
            status="ok",
        )

        return {
            "status": "ok",
            "summary": "Audit SEO et briefs de mots-cles publies.",
            "seo_report": response,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _scan_articles() -> str:
        """Read frontmatter of existing articles for analysis."""
        if not CONTENT_DIR.exists():
            return ""

        summaries: list[str] = []
        for f in sorted(CONTENT_DIR.glob("*.md")):
            text = f.read_text(encoding="utf-8", errors="replace")
            fm = re.search(r"---\n(.*?)\n---", text, re.DOTALL)
            if fm:
                summaries.append(f"### {f.name}\n```yaml\n{fm.group(1)}\n```")
        return "\n\n".join(summaries)
