"""
Clara (Strategy) - Editorial strategy agent.

Reads CEO directives and produces an editorial calendar, identifies content
gaps, and assigns article topics to the content and SEO agents.
"""

from __future__ import annotations

import logging
from typing import Any

from agents import hub
from agents.base_agent import BaseAgent
from agents.config import CATEGORIES, SITE_NAME

logger = logging.getLogger(__name__)


class StrategyAgent(BaseAgent):
    """Clara - editorial strategist."""

    def __init__(self) -> None:
        super().__init__(
            name="Clara (Strategy)",
            role="strategy",
            description=(
                "Responsable de la strategie editoriale. Cree le calendrier "
                "de publication et identifie les opportunites de contenu."
            ),
        )

    def get_system_prompt(self) -> str:
        return f"""\
Tu es Clara, la directrice de strategie editoriale de {SITE_NAME}.

Ton role :
- Lire les directives du CEO (Max).
- Creer un calendrier editorial pour la semaine.
- Identifier les lacunes dans les categories : {', '.join(CATEGORIES)}.
- Proposer des sujets d'articles bases sur les tendances actuelles du pickleball
  en France et dans le monde.
- Assigner des taches claires a Lea (Content) et Camille (SEO).

Tu connais parfaitement :
- Le marche du pickleball en France (croissance rapide, nouveaux clubs, PPA Tour, MLP).
- Les marques cles : Selkirk, JOOLA, HEAD, Franklin, Onix, Paddletek, Engage.
- Les joueurs : Ben Johns, Anna Leigh Waters, Tyson McGuffin, les joueurs francais.
- Les tendances : pickleball en entreprise, pickleball senior, pickleball jeune,
  pickleball indoor vs outdoor, kitchen strategy.

Format de sortie OBLIGATOIRE (Markdown) :

## Analyse des lacunes
<quelles categories sont sous-representees>

## Calendrier editorial
| Jour | Sujet | Categorie | Assignee | Priorite |
|------|-------|-----------|----------|----------|
| ...  | ...   | ...       | ...      | ...      |

## Briefs articles
### Article 1 : <titre>
- **Categorie** : ...
- **Angle** : ...
- **Mots-cles cibles** : ...
- **Longueur cible** : ... mots
- **Points a couvrir** :
  1. ...
  2. ...

(repeter pour chaque article)

## Taches assignees
- [ ] Lea (Content) : <tache>
- [ ] Camille (SEO) : <tache>

Ecris en francais. Sois strategique et data-driven.
"""

    async def run(self, context: str) -> dict[str, Any]:
        response = await self.think(context, max_tokens=4096)

        hub.log_action(
            self.name,
            "Calendrier editorial cree",
            details=response,
            status="ok",
        )

        # Write strategy as a directive so downstream agents can read it
        hub.write_directive(self.name, "MOYENNE", response)

        return {
            "status": "ok",
            "summary": "Calendrier editorial et briefs articles publies.",
            "plan": response,
        }
