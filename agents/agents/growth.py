"""
Max (Growth) - Social media and distribution agent.

Creates social media post drafts for Twitter/X and Instagram, plans content
distribution, and outputs files to ``agents/output/social/``.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

from agents import hub
from agents.base_agent import BaseAgent
from agents.config import CONTENT_DIR, SITE_NAME, SITE_URL, SOCIAL_DIR

logger = logging.getLogger(__name__)


class GrowthAgent(BaseAgent):
    """Max (Growth) - social media and distribution specialist."""

    def __init__(self) -> None:
        super().__init__(
            name="Max (Growth)",
            role="growth",
            description=(
                "Responsable croissance et reseaux sociaux. Cree des posts "
                "pour Twitter/X et Instagram, planifie la distribution."
            ),
        )

    def get_system_prompt(self) -> str:
        return f"""\
Tu es Max, le responsable croissance de {SITE_NAME} ({SITE_URL}).

Ton role :
- Creer des posts pour Twitter/X et des legendes Instagram pour promouvoir
  chaque nouvel article.
- Planifier un calendrier de distribution sur la semaine.
- Suggerer des strategies d'engagement (hashtags, heures de publication,
  formats de contenu).
- Proposer des idees de contenu viral lie au pickleball.

Tu connais les meilleures pratiques social media :
- Twitter/X : threads, hooks, 280 caracteres max par tweet, hashtags pickleball.
- Instagram : legendes engageantes, emojis, appel a l'action, hashtags (max 30).
- Heures optimales de publication en France (12h-14h, 18h-20h).

Hashtags populaires pickleball :
#pickleball #pickleballfrance #pickleballlife #pickleballaddict
#pickleballplayer #pickleballcommunity #pickleballislife #pickleballtime
#pickleballmania #pickleballgame #pickleballcourt #pickleballfun

Format de sortie OBLIGATOIRE (JSON dans un bloc code) :

```json
{{
  "posts": [
    {{
      "article": "<titre ou slug>",
      "twitter": {{
        "text": "<texte du tweet max 280 car>",
        "hashtags": ["pickleball", "..."],
        "scheduled_time": "YYYY-MM-DD HH:MM"
      }},
      "instagram": {{
        "caption": "<legende Instagram>",
        "hashtags": ["pickleball", "..."],
        "scheduled_time": "YYYY-MM-DD HH:MM"
      }}
    }}
  ],
  "weekly_strategy": "<resume de la strategie de la semaine>",
  "engagement_tips": ["<conseil 1>", "<conseil 2>"]
}}
```

Ecris tout le contenu des posts en francais.
Genere des posts pour CHAQUE article existant qui n'a pas encore de post.
"""

    async def run(self, context: str) -> dict[str, Any]:
        # List existing articles
        articles = self._list_articles()
        enriched = (
            context
            + "\n\n## Articles a promouvoir\n"
            + ("\n".join(f"- {a}" for a in articles) if articles else "(aucun)")
        )

        response = await self.think(enriched, max_tokens=4096)

        # Try to extract JSON and save social media posts
        saved = self._save_social_posts(response)

        summary = f"Posts sociaux generes pour {len(saved)} article(s)."
        hub.log_action(self.name, summary, details=response, status="ok")

        return {
            "status": "ok",
            "summary": summary,
            "social_files": saved,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _list_articles() -> list[str]:
        if not CONTENT_DIR.exists():
            return []
        return sorted(f.stem for f in CONTENT_DIR.glob("*.md"))

    @staticmethod
    def _save_social_posts(response: str) -> list[str]:
        """Extract JSON from the response and save individual post files."""
        SOCIAL_DIR.mkdir(parents=True, exist_ok=True)

        # Find JSON block in the response
        json_match = re.search(r"```json\s*\n(.*?)\n```", response, re.DOTALL)
        if not json_match:
            # Try raw JSON
            json_match = re.search(r"\{[\s\S]*\"posts\"[\s\S]*\}", response)
            if not json_match:
                logger.warning("No JSON found in growth agent response.")
                return []

        try:
            data = json.loads(json_match.group(1) if json_match.lastindex else json_match.group(0))
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse social media JSON: %s", exc)
            return []

        saved: list[str] = []
        today = datetime.now().strftime("%Y-%m-%d")

        # Save the full plan
        plan_file = SOCIAL_DIR / f"{today}-social-plan.json"
        plan_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        saved.append(plan_file.name)

        # Save individual post files for easy consumption
        for i, post in enumerate(data.get("posts", []), 1):
            slug = re.sub(r"[^a-z0-9]+", "-", post.get("article", f"post-{i}").lower()).strip("-")
            post_file = SOCIAL_DIR / f"{today}-{slug}.json"
            post_file.write_text(
                json.dumps(post, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            saved.append(post_file.name)

        return saved
