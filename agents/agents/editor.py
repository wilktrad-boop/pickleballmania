"""
Jules (Editeur) - Editor/Proofreader agent.

Reviews articles before publication: corrects spelling & grammar errors,
checks tone consistency, detects repetitions, validates SEO metadata,
and improves readability.  Only fixes issues — never rewrites content.

Position in pipeline: between Content and Affiliate.
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from agents import hub
from agents.base_agent import BaseAgent
from agents.config import CONTENT_DIR, SITE_NAME, SITE_URL

logger = logging.getLogger(__name__)

# How far back (in days) to look for recently modified articles.
_LOOKBACK_DAYS = 7


class EditorAgent(BaseAgent):
    """Jules - the editor/proofreader reviewing articles before publication."""

    def __init__(self) -> None:
        super().__init__(
            name="Jules (Editeur)",
            role="editor",
            description=(
                "Editeur et correcteur. Relit les articles avant publication, "
                "corrige les erreurs, verifie la coherence du ton, detecte "
                "les repetitions et ameliore la lisibilite."
            ),
        )

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    def get_system_prompt(self) -> str:
        return f"""\
Tu es Jules, editeur et correcteur en chef de {SITE_NAME} ({SITE_URL}).

Ton role :
- Relire les articles fournis et signaler / corriger les problemes.
- Tu ne REECRIS PAS l'article. Tu corriges UNIQUEMENT les erreurs.

Ce que tu verifies :
1. **Orthographe et grammaire** : fautes, accords, conjugaisons, accents manquants.
2. **Coherence du ton** : le ton doit rester expert mais accessible, en francais courant.
   Pas de tutoiement si le reste de l'article vouvoie (et inversement).
3. **Repetitions** : mots ou expressions repetes trop souvent dans un meme paragraphe
   ou dans des paragraphes consecutifs.
4. **Tournures maladroites** : phrases trop longues, constructions passives inutiles,
   anglicismes evitables.
5. **SEO - meta description** : doit faire entre 120 et 160 caracteres.
   Si elle est trop courte ou trop longue, propose une version corrigee.
6. **SEO - titre** : doit faire entre 30 et 65 caracteres.
   Si hors limites, propose une version corrigee.
7. **Frontmatter** : verifie que les champs obligatoires sont presents
   (title, description, pubDate, category).

Regles strictes :
- Ne change JAMAIS le sens ou le fond de l'article.
- Ne reorganise JAMAIS la structure (titres, ordre des sections).
- Corrige le minimum necessaire pour que l'article soit impeccable.
- Si l'article est deja parfait, reponds "AUCUNE CORRECTION NECESSAIRE".

Format de sortie OBLIGATOIRE :
Pour chaque correction, utilise exactement ce format :

===CORRECTION_START===
FICHIER: <nom du fichier>
ORIGINAL: <texte original exact (quelques mots/phrases, pas tout le paragraphe)>
CORRIGE: <texte corrige>
RAISON: <breve explication>
===CORRECTION_END===

Si tu as plusieurs corrections pour le meme fichier, fais un bloc par correction.
Avant les blocs, tu peux ajouter un bref resume du nombre de corrections trouvees.
Si aucune correction n'est necessaire pour un fichier, dis-le simplement.
"""

    # ------------------------------------------------------------------
    # Main execution
    # ------------------------------------------------------------------

    async def run(self, context: str) -> dict[str, Any]:
        articles = self._collect_recent_articles()

        if not articles:
            summary = "Aucun article recent a relire."
            logger.info("[%s] %s", self.name, summary)
            hub.log_action(self.name, summary, status="ok")
            return {"status": "ok", "summary": summary, "corrections": 0}

        logger.info(
            "[%s] %d article(s) a relire.", self.name, len(articles),
        )

        # Build the prompt with all article contents
        review_prompt = self._build_review_prompt(articles, context)

        # Ask Claude to proofread
        response = await self.think(review_prompt, max_tokens=8192)

        # Parse corrections from the response
        corrections = self._parse_corrections(response)

        # Apply corrections
        applied = 0
        skipped = 0
        details: list[str] = []

        for corr in corrections:
            success = self._apply_correction(corr)
            if success:
                applied += 1
                details.append(
                    f"  - {corr['filename']}: \"{corr['original'][:50]}...\" -> corrige ({corr['reason']})"
                )
            else:
                skipped += 1
                details.append(
                    f"  - {corr['filename']}: IGNORE (texte original introuvable)"
                )

        summary = (
            f"{len(articles)} article(s) relu(s), "
            f"{applied} correction(s) appliquee(s), "
            f"{skipped} ignoree(s)."
        )
        hub.log_action(self.name, summary, status="ok")

        # Log detailed changes
        if details:
            detail_log = "\n".join(details)
            logger.info("[%s] Details des corrections:\n%s", self.name, detail_log)

        return {
            "status": "ok",
            "summary": summary,
            "corrections_applied": applied,
            "corrections_skipped": skipped,
            "articles_reviewed": len(articles),
            "details": details,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_recent_articles() -> list[dict[str, str]]:
        """Return articles modified within the last ``_LOOKBACK_DAYS`` days."""
        if not CONTENT_DIR.exists():
            return []

        cutoff = time.time() - (_LOOKBACK_DAYS * 86400)
        articles: list[dict[str, str]] = []

        for md_file in sorted(CONTENT_DIR.glob("*.md")):
            try:
                mtime = md_file.stat().st_mtime
                if mtime < cutoff:
                    continue
                content = md_file.read_text(encoding="utf-8", errors="replace")
                articles.append({
                    "filename": md_file.name,
                    "filepath": str(md_file),
                    "content": content,
                })
            except Exception as exc:
                logger.warning("Cannot read %s: %s", md_file, exc)

        return articles

    @staticmethod
    def _build_review_prompt(
        articles: list[dict[str, str]], context: str,
    ) -> str:
        """Assemble the prompt containing all articles for review."""
        parts = [
            context,
            "",
            "=" * 60,
            "ARTICLES A RELIRE",
            "=" * 60,
            "",
        ]
        for art in articles:
            parts.append(f"### Fichier : {art['filename']}")
            parts.append("```markdown")
            parts.append(art["content"])
            parts.append("```")
            parts.append("")

        parts.append(
            "Relis chaque article ci-dessus et fournis tes corrections "
            "au format ===CORRECTION_START===...===CORRECTION_END=== "
            "comme decrit dans tes instructions."
        )
        return "\n".join(parts)

    @staticmethod
    def _parse_corrections(text: str) -> list[dict[str, str]]:
        """Extract correction blocks from the LLM response."""
        pattern = r"===CORRECTION_START===\s*\n(.*?)===CORRECTION_END==="
        matches = re.findall(pattern, text, re.DOTALL)

        corrections: list[dict[str, str]] = []
        for block in matches:
            filename_m = re.search(r"FICHIER:\s*(.+)", block)
            original_m = re.search(r"ORIGINAL:\s*(.+)", block)
            corrected_m = re.search(r"CORRIGE:\s*(.+)", block)
            reason_m = re.search(r"RAISON:\s*(.+)", block)

            if not (filename_m and original_m and corrected_m):
                logger.warning("Malformed correction block, skipping:\n%s", block[:200])
                continue

            corrections.append({
                "filename": filename_m.group(1).strip(),
                "original": original_m.group(1).strip(),
                "corrected": corrected_m.group(1).strip(),
                "reason": reason_m.group(1).strip() if reason_m else "Non precise",
            })

        return corrections

    @staticmethod
    def _apply_correction(corr: dict[str, str]) -> bool:
        """Apply a single correction via string replacement.

        Returns True if the replacement was successful, False otherwise.
        """
        filepath = CONTENT_DIR / corr["filename"]

        if not filepath.is_file():
            logger.warning("File not found: %s", filepath)
            return False

        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.warning("Cannot read %s: %s", filepath, exc)
            return False

        original = corr["original"]
        corrected = corr["corrected"]

        # Avoid no-op replacements
        if original == corrected:
            logger.debug("Original == corrected for %s, skipping.", corr["filename"])
            return False

        if original not in content:
            # Try a more lenient match: collapse multiple whitespace
            normalised_content = re.sub(r"\s+", " ", content)
            normalised_original = re.sub(r"\s+", " ", original)

            if normalised_original not in normalised_content:
                logger.warning(
                    "Original text not found in %s: '%s'",
                    corr["filename"],
                    original[:80],
                )
                return False

            # Rebuild content with flexible whitespace replacement
            escaped = re.escape(original)
            flexible_pattern = re.sub(r"\\ ", r"\\s+", escaped)
            content = re.sub(flexible_pattern, corrected, content, count=1)
        else:
            content = content.replace(original, corrected, 1)

        try:
            filepath.write_text(content, encoding="utf-8")
            logger.info(
                "Correction applied in %s: '%s' -> '%s'",
                corr["filename"],
                original[:60],
                corrected[:60],
            )
            return True
        except Exception as exc:
            logger.error("Cannot write %s: %s", filepath, exc)
            return False
