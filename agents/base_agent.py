"""
Base class for all Pickleball Mania AI agents.

Uses the Claude Code CLI (``claude``) instead of the Anthropic API,
so that all token usage goes through the user's Max subscription.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

from agents import hub
from agents.scraper import get_news_context

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base for every agent in the orchestration pipeline.

    Parameters
    ----------
    name:
        Human-readable name shown in logs, e.g. ``"Lea (Content)"``.
    role:
        One-word role label, e.g. ``"content"``.
    description:
        Short sentence describing the agent's responsibility.
    """

    def __init__(self, name: str, role: str, description: str) -> None:
        self.name = name
        self.role = role
        self.description = description

    # ------------------------------------------------------------------
    # Claude Code CLI
    # ------------------------------------------------------------------

    async def think(self, context: str, *, max_tokens: int | None = None) -> str:
        """Call Claude via the Claude Code CLI.

        This uses your Max subscription tokens instead of API credits.

        Parameters
        ----------
        context:
            User-message content (directives, article briefs, etc.).
        max_tokens:
            Unused (kept for interface compatibility). The CLI manages
            its own token limits.

        Returns
        -------
        str
            The assistant's reply text.
        """
        system_prompt = self.get_system_prompt()
        logger.info("[%s] Thinking via Claude CLI (context: %d chars)...", self.name, len(context))

        full_prompt = f"{system_prompt}\n\n---\n\n{context}"

        # Run claude CLI in a thread to avoid blocking the event loop
        result = await asyncio.to_thread(self._call_claude_cli, full_prompt)

        logger.info("[%s] Response received (%d chars).", self.name, len(result))
        return result

    @staticmethod
    def _call_claude_cli(prompt: str) -> str:
        """Call the ``claude`` CLI with the given prompt and return the response.

        Uses ``claude -p`` (print mode) which accepts a prompt on stdin
        and returns the response on stdout without interactive UI.
        """
        try:
            # Use a temp file to avoid Windows stdin encoding issues (cp1252 vs utf-8)
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", encoding="utf-8", delete=False
            ) as f:
                f.write(prompt)
                temp_path = f.name

            try:
                # Read from file instead of stdin to avoid encoding issues
                with open(temp_path, "r", encoding="utf-8") as stdin_file:
                    env = {**__import__("os").environ, "PYTHONIOENCODING": "utf-8"}
                    result = subprocess.run(
                        ["claude", "-p", "--output-format", "text"],
                        stdin=stdin_file,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=600,  # 10 minute timeout per agent call
                        env=env,
                    )
            finally:
                Path(temp_path).unlink(missing_ok=True)

            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else f"Exit code {result.returncode}"
                raise RuntimeError(f"Claude CLI error: {error_msg}")

            response = result.stdout.strip()
            if not response:
                raise RuntimeError("Claude CLI returned empty response")

            return response

        except FileNotFoundError:
            raise RuntimeError(
                "Claude CLI not found. Make sure 'claude' is installed and in your PATH. "
                "Install it with: npm install -g @anthropic-ai/claude-code"
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("Claude CLI timed out after 10 minutes")

    # ------------------------------------------------------------------
    # Execution lifecycle
    # ------------------------------------------------------------------

    async def execute(self) -> dict[str, Any]:
        """Main execution entry-point.

        The default implementation:
        1. Reads the latest directives and any pending tasks for this agent.
        2. Builds a context string.
        3. Calls :meth:`run` (which subclasses must implement).
        4. Logs the outcome to the shared hub.

        Returns
        -------
        dict
            A result dictionary with at least ``{"status": "ok"|"error"}``.
        """
        logger.info("[%s] Starting execution...", self.name)
        hub.log_action(self.name, "Debut d'execution", status="pending")

        try:
            directives = hub.read_latest_directives()
            pending = hub.get_pending_tasks(self.role)
            state = hub.get_state()

            context = self._build_context(directives, pending, state)
            result = await self.run(context)

            hub.log_action(
                self.name,
                "Execution terminee",
                details=result.get("summary", ""),
                status="ok",
            )
            hub.update_state(
                "agents_status",
                {
                    **state.get("agents_status", {}),
                    self.role: {
                        "last_run": datetime.now().isoformat(),
                        "status": "ok",
                    },
                },
            )
            return result

        except Exception as exc:
            logger.exception("[%s] Execution failed.", self.name)
            hub.log_action(self.name, f"Erreur: {exc}", status="error")
            return {"status": "error", "error": str(exc)}

    @abstractmethod
    async def run(self, context: str) -> dict[str, Any]:
        """Agent-specific logic.  Must be implemented by every subclass."""
        ...

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt specific to this agent."""
        ...

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_context(
        self,
        directives: str,
        pending_tasks: list[str],
        state: dict[str, Any],
    ) -> str:
        """Assemble the context string sent to :meth:`run`."""
        # Fetch real news context (non-blocking if cache empty)
        try:
            news_ctx = get_news_context(max_items=15)
        except Exception:
            news_ctx = "(Actualites non disponibles.)"

        # Limit directives to last 4000 chars to avoid context overflow
        if len(directives) > 4000:
            directives = "(...tronque...)\n" + directives[-4000:]

        parts = [
            f"# Contexte pour {self.name} ({self.role})",
            "",
            "## Dernieres directives",
            directives,
            "",
            "## Taches en attente",
            "\n".join(pending_tasks) if pending_tasks else "(aucune)",
            "",
            "## Etat du site",
            f"- Articles publies : {state.get('articles_count', 0)}",
            f"- Categories couvertes : {', '.join(state.get('categories_covered', []))}",
            f"- Iteration : {state.get('iteration', 1)}",
            f"- Dernier run : {state.get('last_run', 'jamais')}",
            "",
            news_ctx,
        ]
        return "\n".join(parts)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} role={self.role!r}>"
