"""
Auto-deploy module.

After each agent cycle, stages new/modified content, commits,
and pushes to the remote repository so Vercel can rebuild.
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from pathlib import Path

from agents.config import PROJECT_ROOT

logger = logging.getLogger(__name__)


def _run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command in the project root."""
    cmd = ["git"] + list(args)
    logger.info("git %s", " ".join(args))
    return subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=check,
    )


def auto_deploy(cycle_summary: str = "") -> dict[str, str]:
    """Stage content changes, commit, and push.

    Only commits files that are safe to auto-publish:
    - src/content/blog/*.md  (articles)
    - src/assets/blog/**     (images)
    - agents/agent-log.md    (coordination log)

    Returns a dict with status and details.
    """
    try:
        # Check if we're in a git repo
        result = _run_git("status", "--porcelain", check=False)
        if result.returncode == 128:
            return {"status": "skip", "detail": "Not a git repository."}

        # Stage only content-related files
        paths_to_stage = [
            "src/content/blog/",
            "src/assets/blog/",
            "agents/agent-log.md",
        ]
        staged_something = False
        for path in paths_to_stage:
            full = PROJECT_ROOT / path
            if full.exists():
                r = _run_git("add", path, check=False)
                if r.returncode == 0:
                    staged_something = True

        if not staged_something:
            return {"status": "skip", "detail": "Nothing to stage."}

        # Check if there are actual changes to commit
        diff = _run_git("diff", "--cached", "--stat", check=False)
        if not diff.stdout.strip():
            return {"status": "skip", "detail": "No changes to commit."}

        # Build commit message
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        summary_line = cycle_summary[:80] if cycle_summary else "auto-update"
        commit_msg = (
            f"[auto] {summary_line} ({now})\n\n"
            f"Deployed by Pickleball Mania agent system.\n"
            f"Date: {now}"
        )

        # Commit
        r = _run_git("commit", "-m", commit_msg, check=False)
        if r.returncode != 0:
            logger.warning("git commit failed: %s", r.stderr)
            return {"status": "error", "detail": f"Commit failed: {r.stderr[:200]}"}

        logger.info("Committed: %s", r.stdout.strip().split("\n")[0])

        # Push
        r = _run_git("push", check=False)
        if r.returncode != 0:
            logger.warning("git push failed: %s", r.stderr)
            return {
                "status": "error",
                "detail": f"Push failed (commit OK): {r.stderr[:200]}",
            }

        logger.info("Pushed successfully.")
        return {"status": "ok", "detail": f"Committed and pushed: {summary_line}"}

    except subprocess.TimeoutExpired:
        return {"status": "error", "detail": "Git command timed out."}
    except Exception as exc:
        logger.exception("Auto-deploy error: %s", exc)
        return {"status": "error", "detail": str(exc)}
