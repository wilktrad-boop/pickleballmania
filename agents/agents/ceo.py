"""
Max (CEO) - Orchestrator agent.

Analyses the current state of the Pickleball Mania website, scores site health,
and produces prioritised directives that the other agents will follow.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from agents import hub
from agents.base_agent import BaseAgent
from agents.config import CATEGORIES, CONTENT_DIR, SITE_NAME, SITE_URL

logger = logging.getLogger(__name__)


class CEOAgent(BaseAgent):
    """Max - the CEO who sets the strategic direction each cycle."""

    def __init__(self) -> None:
        super().__init__(
            name="Max (CEO)",
            role="ceo",
            description=(
                "Directeur general du systeme multi-agents Pickleball Mania. "
                "Analyse l'etat du site, fixe les priorites et redige les "
                "directives pour les autres agents."
            ),
        )

    def get_system_prompt(self) -> str:
        return f"""\
Tu es Max, le CEO et orchestrateur du site {SITE_NAME} ({SITE_URL}).

Ton role :
- Analyser l'etat actuel du site (articles existants, categories couvertes,
  sante SEO, monetisation).
- Produire des directives claires et priorisees pour les autres agents.
- Assigner des taches specifiques a chaque agent :
  - Clara (Strategy) : planification editoriale
  - Lea (Content) : redaction d'articles
  - Camille (SEO) : optimisation du referencement
  - Sophie (Affiliate) : monetisation Amazon
  - Max (Growth) : reseaux sociaux et distribution

Categories du site : {', '.join(CATEGORIES)}

Format de sortie OBLIGATOIRE (Markdown) :

## Analyse de l'etat actuel
<analyse courte>

## Score de sante du site
- Contenu : X/10
- SEO : X/10
- Monetisation : X/10
- Distribution : X/10

## Directives
### Priorite HAUTE
<taches>

### Priorite MOYENNE
<taches>

### Priorite BASSE
<taches>

## Taches assignees
- [ ] Clara (Strategy) : <tache>
- [ ] Lea (Content) : <tache>
- [ ] Camille (SEO) : <tache>
- [ ] Sophie (Affiliate) : <tache>
- [ ] Max (Growth) : <tache>

Ecris en francais. Sois concis et actionnable.
"""

    async def run(self, context: str) -> dict[str, Any]:
        # ---- Gather extra data about existing articles ----
        existing_articles = self._scan_existing_articles()
        enriched_context = (
            context
            + "\n\n## Articles existants\n"
            + (
                "\n".join(f"- {a}" for a in existing_articles)
                if existing_articles
                else "(aucun article)"
            )
        )

        # ---- Ask Claude ----
        response = await self.think(enriched_context, max_tokens=4096)

        # ---- Write directives into the shared log ----
        hub.write_directive(self.name, "HAUTE", response)

        # ---- Update state ----
        hub.update_state("last_run", datetime.now().isoformat())

        return {
            "status": "ok",
            "summary": "Directives du CEO publiees.",
            "directives": response,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _scan_existing_articles() -> list[str]:
        """Return a list of existing article filenames."""
        if not CONTENT_DIR.exists():
            return []
        return sorted(
            f.name for f in CONTENT_DIR.glob("*.md") if f.is_file()
        ) + sorted(
            f.name for f in CONTENT_DIR.glob("*.mdx") if f.is_file()
        )
