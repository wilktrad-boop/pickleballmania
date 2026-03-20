"""
Coordination hub for the multi-agent system.

All agents communicate through a shared Markdown log file and a JSON state
file.  This module provides the read/write helpers that every agent uses.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from agents.config import LOG_FILE, STATE_FILE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Log file helpers
# ---------------------------------------------------------------------------

def _ensure_log_file() -> None:
    """Create the log file with a header if it does not exist."""
    if not LOG_FILE.exists():
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOG_FILE.write_text(
            "# Pickleball Mania - Agent Communication Hub\n\n"
            "## Directives\n\n"
            "---\n\n"
            "## Journal des actions\n\n"
            "| Date | Agent | Action | Statut |\n"
            "|------|-------|--------|--------|\n",
            encoding="utf-8",
        )


def log_action(agent_name: str, action: str, details: str = "", status: str = "ok") -> None:
    """Append an entry to the agent log file.

    Parameters
    ----------
    agent_name:
        Human-readable agent name, e.g. ``"Max (CEO)"``.
    action:
        Short summary of what the agent did.
    details:
        Optional longer description written as a Markdown block below the
        table row.
    status:
        Emoji-friendly status string shown in the table.
    """
    _ensure_log_file()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    status_icon = {"ok": "OK", "error": "ERREUR", "pending": "EN COURS"}.get(
        status, status
    )

    lines: list[str] = []

    # Append a table row to the journal section
    lines.append(f"| {now} | {agent_name} | {action} | {status_icon} |")

    # If there are details, add a collapsible block after the table row
    if details:
        lines.append("")
        lines.append(f"<details><summary>{agent_name} - {action}</summary>")
        lines.append("")
        lines.append(details)
        lines.append("")
        lines.append("</details>")
        lines.append("")

    content = LOG_FILE.read_text(encoding="utf-8")
    content += "\n" + "\n".join(lines) + "\n"
    LOG_FILE.write_text(content, encoding="utf-8")
    logger.info("Logged action: %s - %s", agent_name, action)


def write_directive(agent_name: str, priority: str, body: str) -> None:
    """Write a new directive block into the Directives section.

    Parameters
    ----------
    agent_name:
        The agent issuing the directive (usually the CEO).
    priority:
        Priority label, e.g. ``"HAUTE"``, ``"MOYENNE"``, ``"BASSE"``.
    body:
        Markdown-formatted directive content.
    """
    _ensure_log_file()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    block = (
        f"\n### {now} - Directive\n"
        f"**Agent**: {agent_name}\n"
        f"**Priorite**: {priority}\n\n"
        f"{body}\n\n---\n"
    )

    content = LOG_FILE.read_text(encoding="utf-8")
    # Insert just before the journal section
    marker = "## Journal des actions"
    if marker in content:
        content = content.replace(marker, block + "\n" + marker, 1)
    else:
        content += block
    LOG_FILE.write_text(content, encoding="utf-8")
    logger.info("Directive written by %s (priority=%s)", agent_name, priority)


def read_latest_directives(limit: int = 5) -> str:
    """Return the latest *limit* directive blocks as raw Markdown."""
    _ensure_log_file()
    content = LOG_FILE.read_text(encoding="utf-8")
    # Each directive starts with ### <date>
    blocks = re.split(r"(?=^### \d{4}-\d{2}-\d{2})", content, flags=re.MULTILINE)
    # Filter only directive blocks
    directives = [b for b in blocks if b.strip().startswith("###")]
    return "\n".join(directives[-limit:]) if directives else "(aucune directive)"


def get_pending_tasks(agent_name: str) -> list[str]:
    """Extract pending task lines mentioning *agent_name* from directives.

    A task is any line that starts with ``- [ ]`` and contains the agent name
    (case-insensitive).
    """
    directives = read_latest_directives(limit=10)
    tasks: list[str] = []
    for line in directives.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [ ]") and agent_name.lower() in stripped.lower():
            tasks.append(stripped)
    return tasks


# ---------------------------------------------------------------------------
# State file helpers
# ---------------------------------------------------------------------------

def _ensure_state_file() -> None:
    """Create the state file with sensible defaults if missing."""
    if not STATE_FILE.exists():
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(
            json.dumps(
                {
                    "version": "1.0.0",
                    "build": 1,
                    "iteration": 1,
                    "last_run": None,
                    "agents_status": {},
                    "articles_count": 0,
                    "categories_covered": [],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )


def get_state() -> dict[str, Any]:
    """Load and return the full state dictionary."""
    _ensure_state_file()
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def update_state(key: str, value: Any) -> dict[str, Any]:
    """Update a single top-level key in the state file and return the new state."""
    state = get_state()
    state[key] = value
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("State updated: %s = %s", key, value)
    return state


def increment_state(key: str, amount: int = 1) -> dict[str, Any]:
    """Increment a numeric state value."""
    state = get_state()
    state[key] = state.get(key, 0) + amount
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return state
