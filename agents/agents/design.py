"""
Hugo (Design) - Frontend design agent.

Analyses the current Astro templates, proposes and applies design improvements,
then validates that the site still builds correctly. If the build breaks,
the changes are automatically rolled back.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from agents import hub
from agents.base_agent import BaseAgent
from agents.config import CONTENT_DIR, PROJECT_ROOT, SITE_DIR, SITE_NAME, SITE_URL

logger = logging.getLogger(__name__)

# Files Hugo is allowed to modify
EDITABLE_FILES = [
    "src/components/Header.astro",
    "src/components/Footer.astro",
    "src/components/FormattedDate.astro",
    "src/pages/index.astro",
    "src/pages/blog/index.astro",
    "src/pages/equipement.astro",
    "src/pages/about.astro",
    "src/pages/blog/[...slug].astro",
    "src/pages/categorie/[category].astro",
    "src/layouts/BlogPost.astro",
    "src/styles/global.css",
]


class DesignAgent(BaseAgent):
    """Hugo - frontend design specialist who improves the site's UI/UX."""

    def __init__(self) -> None:
        super().__init__(
            name="Hugo (Design)",
            role="design",
            description=(
                "Developpeur frontend. Ameliore le design, l'UX et les "
                "composants Astro/Tailwind du site Pickleball Mania."
            ),
        )

    def get_system_prompt(self) -> str:
        return f"""\
Tu es Hugo, le developpeur frontend et designer de {SITE_NAME} ({SITE_URL}).

Ton role :
- Analyser les templates Astro existants et identifier des ameliorations UX/UI.
- Proposer ET appliquer des modifications concretes au code.
- Utiliser Tailwind CSS pour le styling (classes utilitaires, pas de CSS custom).
- Garder le theme sombre existant (slate-900, emerald-400 accents, amber pour notes).
- Respecter le responsive design (mobile-first).

Regles strictes :
1. Ne modifie QU'UN SEUL fichier par cycle pour limiter les risques.
2. Tes modifications doivent etre retrocompatibles (ne pas casser la structure).
3. Ne change JAMAIS la logique de routing ou les imports de donnees.
4. Concentre-toi sur : animations, micro-interactions, amelioration visuelle,
   accessibilite, performance perceptuelle.
5. Ecris du code Astro/Tailwind valide.

Exemples d'ameliorations possibles :
- Ajouter des animations d'entree (fade-in, slide-up) aux cartes d'articles
- Ameliorer le hover des cartes (scale, shadow, transitions)
- Ajouter un indicateur de lecture (reading time) sur les articles
- Ameliorer la typographie et l'espacement
- Ajouter un bouton "retour en haut"
- Ameliorer l'affichage des tags/categories
- Optimiser le layout mobile
- Ajouter des micro-animations (pulse, bounce) sur les CTA

Format de sortie OBLIGATOIRE :

## Analyse du fichier actuel
<ce qui fonctionne bien et ce qui peut etre ameliore>

## Modification proposee
**Fichier** : <chemin exact du fichier>
**Description** : <ce que tu ameliores et pourquoi>

## Code complet du fichier modifie
Tu DOIS fournir le fichier COMPLET (pas juste un diff) entre ces delimiteurs :

===FILE_START===
<contenu complet du fichier modifie>
===FILE_END===

Important :
- Le code doit etre complet et pret a remplacer le fichier existant.
- Ne modifie qu'UN fichier par reponse.
- Explique pourquoi chaque changement ameliore l'UX.
"""

    async def run(self, context: str) -> dict[str, Any]:
        # Pick one file to improve this cycle
        target_file = self._pick_target_file()
        if not target_file:
            return {
                "status": "ok",
                "summary": "Aucun fichier a ameliorer identifie.",
            }

        # Read current file content
        file_path = PROJECT_ROOT / target_file
        current_content = file_path.read_text(encoding="utf-8")

        enriched = (
            context
            + f"\n\n## Fichier a ameliorer : {target_file}\n"
            + f"```astro\n{current_content}\n```\n"
        )

        # Ask Claude for improvements
        response = await self.think(enriched, max_tokens=8192)

        # Extract the modified file
        new_content = self._extract_file_content(response)
        if not new_content:
            hub.log_action(
                self.name,
                f"Pas de code valide extrait pour {target_file}",
                status="error",
            )
            return {
                "status": "error",
                "summary": f"Impossible d'extraire le code modifie pour {target_file}.",
            }

        # Backup, apply, and validate
        result = self._apply_and_validate(file_path, current_content, new_content)

        summary = result["summary"]
        hub.log_action(self.name, summary, details=response[:500], status=result["status"])

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _pick_target_file(self) -> str | None:
        """Choose which file to improve this cycle.

        Rotates through editable files based on iteration count.
        """
        state = hub.get_state()
        iteration = state.get("iteration", 1)
        design_history = state.get("design_history", [])

        # Find files not recently modified
        candidates = [f for f in EDITABLE_FILES if f not in design_history[-3:]]
        if not candidates:
            candidates = EDITABLE_FILES

        # Rotate through candidates
        idx = (iteration - 1) % len(candidates)
        return candidates[idx]

    @staticmethod
    def _extract_file_content(response: str) -> str | None:
        """Extract file content from ===FILE_START===...===FILE_END=== block."""
        match = re.search(
            r"===FILE_START===\s*\n(.*?)===FILE_END===",
            response,
            re.DOTALL,
        )
        if match:
            return match.group(1).strip()

        # Fallback: try to find a large code block
        code_match = re.search(r"```(?:astro|html|css)\s*\n(.*?)```", response, re.DOTALL)
        if code_match and len(code_match.group(1)) > 200:
            return code_match.group(1).strip()

        return None

    def _apply_and_validate(
        self, file_path: Path, old_content: str, new_content: str
    ) -> dict[str, Any]:
        """Apply changes and run astro build. Rollback if build fails."""
        relative = file_path.relative_to(PROJECT_ROOT)

        # Create backup
        backup_path = file_path.with_suffix(file_path.suffix + ".bak")
        shutil.copy2(file_path, backup_path)
        logger.info("[%s] Backup created: %s", self.name, backup_path)

        # Apply new content
        file_path.write_text(new_content, encoding="utf-8")
        logger.info("[%s] Applied changes to %s", self.name, relative)

        # Validate with astro build
        try:
            result = subprocess.run(
                ["npx", "astro", "build"],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                shell=True,
            )

            if result.returncode == 0:
                # Build OK - remove backup
                backup_path.unlink(missing_ok=True)
                logger.info("[%s] Build OK - changes validated", self.name)

                # Track in design history
                state = hub.get_state()
                history = state.get("design_history", [])
                history.append(str(relative))
                hub.update_state("design_history", history[-10:])  # Keep last 10

                return {
                    "status": "ok",
                    "summary": f"Design ameliore : {relative} (build valide)",
                    "file": str(relative),
                }
            else:
                # Build FAILED - rollback
                logger.warning("[%s] Build FAILED - rolling back", self.name)
                shutil.copy2(backup_path, file_path)
                backup_path.unlink(missing_ok=True)

                error_snippet = result.stderr[-300:] if result.stderr else "unknown error"
                return {
                    "status": "error",
                    "summary": f"Build echoue pour {relative} - rollback effectue. Erreur: {error_snippet}",
                    "file": str(relative),
                }

        except subprocess.TimeoutExpired:
            # Timeout - rollback
            logger.warning("[%s] Build timeout - rolling back", self.name)
            shutil.copy2(backup_path, file_path)
            backup_path.unlink(missing_ok=True)
            return {
                "status": "error",
                "summary": f"Build timeout pour {relative} - rollback effectue.",
                "file": str(relative),
            }
