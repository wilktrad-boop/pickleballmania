"""
Theo (Tech SEO) - Technical SEO health-check agent.

Scans all articles for technical SEO issues: title length, meta descriptions,
heading hierarchy, missing alt text, internal/external links, and frontmatter
completeness.  Auto-fixes what it can and generates a structured report.

Pipeline position: runs after Linking, before Growth.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from agents import hub
from agents.base_agent import BaseAgent
from agents.config import CATEGORIES, CONTENT_DIR, SITE_NAME, SITE_URL

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TITLE_MIN = 50
TITLE_MAX = 60
META_DESC_MIN = 120
META_DESC_MAX = 160

REQUIRED_FRONTMATTER_FIELDS = ["title", "description", "category", "tags"]


class TechSEOAgent(BaseAgent):
    """Theo - Technical SEO specialist."""

    def __init__(self) -> None:
        super().__init__(
            name="Theo (Tech SEO)",
            role="techseo",
            description=(
                "Specialiste SEO technique. Verifie la sante technique du site : "
                "schema markup, liens casses, alt text manquant, meta descriptions, "
                "structure des titres."
            ),
        )

    def get_system_prompt(self) -> str:
        return f"""\
Tu es Theo, l'expert SEO technique de {SITE_NAME} ({SITE_URL}).

Ton role :
- Analyser la sante technique SEO de chaque article du site.
- Verifier la structure des titres (H1/H2/H3), les meta descriptions,
  le alt text des images, les liens internes et externes.
- Identifier les problemes de frontmatter (champs manquants, longueurs).
- Proposer des corrections concretes et actionnables.
- S'assurer que le contenu respecte les bonnes pratiques techniques SEO 2025-2026.

Categories du site : {', '.join(CATEGORIES)}.

A partir du rapport technique fourni, tu dois :
1. Prioriser les problemes par impact SEO (critique / important / mineur).
2. Proposer des corrections precises pour chaque probleme.
3. Suggerer des ameliorations de schema markup (Article, FAQ, HowTo).
4. Verifier la coherence du maillage interne.

Format de sortie OBLIGATOIRE (Markdown) :

## Rapport SEO Technique

### Problemes critiques
<liste des problemes critiques avec corrections>

### Problemes importants
<liste des problemes importants avec corrections>

### Problemes mineurs
<liste des problemes mineurs>

### Recommandations schema markup
<suggestions de structured data>

### Corrections automatiques appliquees
<liste des corrections auto-appliquees par l'agent>

### Taches assignees
- [ ] Lea (Content) : <corrections a appliquer manuellement>

Ecris en francais. Sois precis et actionnable.
"""

    async def run(self, context: str) -> dict[str, Any]:
        """Scan articles, auto-fix issues, build report, consult Claude."""
        report = self._audit_all_articles()

        # Build a textual summary of the audit for Claude
        audit_summary = self._format_audit_summary(report)
        enriched = (
            context
            + "\n\n## Rapport d'audit technique automatise\n"
            + audit_summary
        )

        # Ask Claude for additional recommendations
        response = await self.think(enriched, max_tokens=4096)

        hub.write_directive(self.name, "HAUTE", response)
        hub.log_action(
            self.name,
            "Audit SEO technique termine",
            details=response,
            status="ok",
        )

        return {
            "status": "ok",
            "summary": (
                f"Audit technique : {report['total_articles']} articles scannes, "
                f"{report['total_issues']} problemes trouves, "
                f"{report['total_fixes']} corrections auto-appliquees."
            ),
            "techseo_report": report,
            "claude_recommendations": response,
        }

    # ------------------------------------------------------------------
    # Core audit
    # ------------------------------------------------------------------

    def _audit_all_articles(self) -> dict[str, Any]:
        """Scan every Markdown article in CONTENT_DIR and return a report."""
        report: dict[str, Any] = {
            "total_articles": 0,
            "total_issues": 0,
            "total_fixes": 0,
            "articles": [],
        }

        if not CONTENT_DIR.exists():
            logger.warning("[%s] CONTENT_DIR does not exist: %s", self.name, CONTENT_DIR)
            return report

        md_files = sorted(CONTENT_DIR.glob("*.md"))
        report["total_articles"] = len(md_files)

        for filepath in md_files:
            article_report = self._audit_article(filepath)
            report["articles"].append(article_report)
            report["total_issues"] += len(article_report["issues"])
            report["total_fixes"] += len(article_report["fixes"])

        logger.info(
            "[%s] Scanned %d articles: %d issues, %d auto-fixes.",
            self.name,
            report["total_articles"],
            report["total_issues"],
            report["total_fixes"],
        )
        return report

    def _audit_article(self, filepath: Path) -> dict[str, Any]:
        """Run all checks on a single article.  Apply auto-fixes in place."""
        text = filepath.read_text(encoding="utf-8", errors="replace")
        issues: list[str] = []
        fixes: list[str] = []

        # Parse frontmatter
        fm_match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
        fm_raw = fm_match.group(1) if fm_match else ""
        fm = self._parse_frontmatter(fm_raw)
        body = text[fm_match.end():] if fm_match else text

        # --- Checks ---
        self._check_title_length(fm, issues)
        self._check_meta_description(fm, issues)
        self._check_heading_structure(body, issues)
        self._check_alt_text(body, issues)
        self._check_internal_links(body, issues)
        self._check_external_links(body, issues)
        self._check_frontmatter_completeness(fm, issues)

        # --- Auto-fixes ---
        modified_fm, applied = self._auto_fix_frontmatter(fm, fm_raw)
        fixes.extend(applied)

        # Write back if fixes were applied
        if fixes and fm_match:
            new_text = f"---\n{modified_fm}\n---{body}"
            filepath.write_text(new_text, encoding="utf-8")
            logger.info("[%s] Applied %d fix(es) to %s", self.name, len(fixes), filepath.name)

        return {
            "file": filepath.name,
            "issues": issues,
            "fixes": fixes,
        }

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_title_length(fm: dict[str, str], issues: list[str]) -> None:
        title = fm.get("title", "")
        if not title:
            issues.append("CRITIQUE: Titre manquant dans le frontmatter.")
            return
        length = len(title)
        if length < TITLE_MIN:
            issues.append(
                f"IMPORTANT: Titre trop court ({length} car., ideal {TITLE_MIN}-{TITLE_MAX})."
            )
        elif length > TITLE_MAX:
            issues.append(
                f"IMPORTANT: Titre trop long ({length} car., ideal {TITLE_MIN}-{TITLE_MAX})."
            )

    @staticmethod
    def _check_meta_description(fm: dict[str, str], issues: list[str]) -> None:
        desc = fm.get("description", "")
        if not desc:
            issues.append("CRITIQUE: Meta description manquante.")
            return
        length = len(desc)
        if length < META_DESC_MIN:
            issues.append(
                f"IMPORTANT: Meta description trop courte ({length} car., "
                f"ideal {META_DESC_MIN}-{META_DESC_MAX})."
            )
        elif length > META_DESC_MAX:
            issues.append(
                f"IMPORTANT: Meta description trop longue ({length} car., "
                f"ideal {META_DESC_MIN}-{META_DESC_MAX}). Sera tronquee automatiquement."
            )

    @staticmethod
    def _check_heading_structure(body: str, issues: list[str]) -> None:
        """Verify H2/H3 hierarchy -- no level skipping."""
        headings = re.findall(r"^(#{2,6})\s", body, re.MULTILINE)
        if not headings:
            issues.append("IMPORTANT: Aucun sous-titre (H2/H3) trouve dans l'article.")
            return

        levels = [len(h) for h in headings]
        # Check for H1 in body (should only be in frontmatter title)
        if 1 in [len(h) for h in re.findall(r"^(#+)\s", body, re.MULTILINE)]:
            issues.append(
                "IMPORTANT: H1 trouve dans le corps de l'article "
                "(le H1 doit etre uniquement le titre du frontmatter)."
            )

        # Check for level skipping (e.g., H2 -> H4)
        for i in range(1, len(levels)):
            if levels[i] > levels[i - 1] + 1:
                issues.append(
                    f"IMPORTANT: Saut de niveau de titre detecte "
                    f"(H{levels[i - 1]} -> H{levels[i]}). "
                    f"Les niveaux ne doivent pas etre sautes."
                )
                break  # Report once

    @staticmethod
    def _check_alt_text(body: str, issues: list[str]) -> None:
        """Flag images with missing or empty alt text."""
        images = re.findall(r"!\[([^\]]*)\]\([^)]+\)", body)
        empty_alt = [alt for alt in images if not alt.strip()]
        if empty_alt:
            issues.append(
                f"CRITIQUE: {len(empty_alt)} image(s) sans alt text sur "
                f"{len(images)} image(s) totale(s)."
            )

    @staticmethod
    def _check_internal_links(body: str, issues: list[str]) -> None:
        """Flag articles with fewer than 2 internal links."""
        # Internal links: relative paths or same-domain URLs
        internal = re.findall(r"\[([^\]]+)\]\((/[^)]+|\.\.?/[^)]+)\)", body)
        if len(internal) < 2:
            issues.append(
                f"IMPORTANT: Seulement {len(internal)} lien(s) interne(s) "
                f"(minimum recommande : 2)."
            )

    @staticmethod
    def _check_external_links(body: str, issues: list[str]) -> None:
        """Check for common broken-link patterns in external URLs."""
        external = re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", body)
        for label, url in external:
            # Flag obvious broken patterns
            if "example.com" in url or "placeholder" in url.lower():
                issues.append(f"CRITIQUE: Lien externe suspect (placeholder) : {url}")
            if url.endswith("/undefined") or url.endswith("/null"):
                issues.append(f"CRITIQUE: Lien externe casse (undefined/null) : {url}")
            if " " in url:
                issues.append(f"IMPORTANT: URL externe contient des espaces : {url}")

    @staticmethod
    def _check_frontmatter_completeness(fm: dict[str, str], issues: list[str]) -> None:
        """Ensure all required frontmatter fields are present."""
        for field in REQUIRED_FRONTMATTER_FIELDS:
            if field not in fm or not fm[field].strip():
                issues.append(f"IMPORTANT: Champ frontmatter manquant : '{field}'.")

    # ------------------------------------------------------------------
    # Auto-fixes
    # ------------------------------------------------------------------

    @staticmethod
    def _auto_fix_frontmatter(
        fm: dict[str, str], fm_raw: str
    ) -> tuple[str, list[str]]:
        """Apply safe auto-fixes to frontmatter.  Returns (new_fm_raw, fixes)."""
        fixes: list[str] = []
        modified = fm_raw

        # 1. Truncate meta description if too long
        desc = fm.get("description", "")
        if len(desc) > META_DESC_MAX:
            truncated = desc[: META_DESC_MAX - 3].rsplit(" ", 1)[0] + "..."
            # Replace in raw frontmatter
            old_line = f"description: \"{desc}\""
            new_line = f"description: \"{truncated}\""
            if old_line in modified:
                modified = modified.replace(old_line, new_line)
                fixes.append(
                    f"Meta description tronquee ({len(desc)} -> {len(truncated)} car.)."
                )
            else:
                # Try single-quote or unquoted variants
                old_line = f"description: '{desc}'"
                new_line = f"description: '{truncated}'"
                if old_line in modified:
                    modified = modified.replace(old_line, new_line)
                    fixes.append(
                        f"Meta description tronquee ({len(desc)} -> {len(truncated)} car.)."
                    )
                else:
                    old_line = f"description: {desc}"
                    new_line = f"description: \"{truncated}\""
                    if old_line in modified:
                        modified = modified.replace(old_line, new_line)
                        fixes.append(
                            f"Meta description tronquee ({len(desc)} -> {len(truncated)} car.)."
                        )

        # 2. Add missing category with default
        if "category" not in fm or not fm.get("category", "").strip():
            if "category:" not in modified:
                modified += "\ncategory: \"actualites\""
                fixes.append("Champ 'category' ajoute avec valeur par defaut 'actualites'.")

        # 3. Add missing tags with empty list
        if "tags" not in fm or not fm.get("tags", "").strip():
            if "tags:" not in modified:
                modified += "\ntags: []"
                fixes.append("Champ 'tags' ajoute avec liste vide.")

        # 4. Add missing description placeholder
        if "description" not in fm or not fm.get("description", "").strip():
            if "description:" not in modified:
                modified += "\ndescription: \"A completer - description SEO de l'article.\""
                fixes.append("Champ 'description' ajoute avec placeholder.")

        return modified, fixes

    # ------------------------------------------------------------------
    # Report formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _format_audit_summary(report: dict[str, Any]) -> str:
        """Format the audit report as human-readable Markdown for Claude."""
        lines: list[str] = [
            f"**Articles scannes** : {report['total_articles']}",
            f"**Problemes trouves** : {report['total_issues']}",
            f"**Corrections auto-appliquees** : {report['total_fixes']}",
            "",
        ]

        for article in report.get("articles", []):
            lines.append(f"### {article['file']}")
            if article["issues"]:
                for issue in article["issues"]:
                    lines.append(f"- {issue}")
            else:
                lines.append("- Aucun probleme detecte.")
            if article["fixes"]:
                lines.append("**Corrections appliquees :**")
                for fix in article["fixes"]:
                    lines.append(f"  - {fix}")
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_frontmatter(raw: str) -> dict[str, str]:
        """Minimal YAML-like frontmatter parser (key: value lines only)."""
        fm: dict[str, str] = {}
        for line in raw.splitlines():
            match = re.match(r"^(\w[\w-]*):\s*(.*)", line)
            if match:
                key = match.group(1)
                value = match.group(2).strip().strip("\"'")
                fm[key] = value
        return fm
