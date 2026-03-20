#!/usr/bin/env python3
"""
Pickleball Mania - Multi-agent orchestrator.

Runs the complete daily agent pipeline or individual agents on demand.

Usage
-----
    # Full daily cycle
    python -m agents.orchestrator --cycle

    # Single agent
    python -m agents.orchestrator --agent content

    # List available agents
    python -m agents.orchestrator --list
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# Ensure the project root is on sys.path so ``import agents`` works when
# running this file directly.
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from agents import hub  # noqa: E402
from agents.agents import (  # noqa: E402
    AffiliateAgent,
    CEOAgent,
    ContentAgent,
    DesignAgent,
    EditorAgent,
    GrowthAgent,
    LinkingAgent,
    SEOAgent,
    StrategyAgent,
    TechSEOAgent,
)
from agents.config import STATE_FILE  # noqa: E402
from agents.amazon_scraper import fetch_and_cache_products  # noqa: E402
from agents.deployer import auto_deploy  # noqa: E402
from agents.reporter import report_cycle  # noqa: E402
from agents.scraper import fetch_and_cache, get_news_context  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("orchestrator")

# ---------------------------------------------------------------------------
# Agent registry
# ---------------------------------------------------------------------------
AGENT_MAP: dict[str, type] = {
    "ceo": CEOAgent,
    "strategy": StrategyAgent,
    "seo": SEOAgent,
    "content": ContentAgent,
    "editor": EditorAgent,
    "affiliate": AffiliateAgent,
    "linking": LinkingAgent,
    "techseo": TechSEOAgent,
    "growth": GrowthAgent,
    "design": DesignAgent,
}

# The order in which agents execute during a full cycle.
# Design (Hugo) is excluded — he runs only via the weekly schedule or --agent design.
PIPELINE_ORDER = ["ceo", "strategy", "seo", "content", "editor", "affiliate", "linking", "techseo", "growth", "ceo"]


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

async def run_single_agent(agent_name: str) -> dict:
    """Instantiate and run a single agent by its short name.

    Parameters
    ----------
    agent_name:
        One of the keys in ``AGENT_MAP`` (e.g. ``"content"``).

    Returns
    -------
    dict
        The result dictionary produced by the agent's ``execute()`` method.
    """
    agent_name = agent_name.lower().strip()
    if agent_name not in AGENT_MAP:
        valid = ", ".join(sorted(AGENT_MAP))
        raise ValueError(f"Unknown agent '{agent_name}'. Valid agents: {valid}")

    agent = AGENT_MAP[agent_name]()
    logger.info("=" * 60)
    logger.info("Running agent: %s", agent.name)
    logger.info("=" * 60)

    result = await agent.execute()

    status_label = "OK" if result.get("status") == "ok" else "ERREUR"
    logger.info("[%s] Finished with status: %s", agent.name, status_label)
    if result.get("summary"):
        logger.info("[%s] Summary: %s", agent.name, result["summary"])

    return result


async def run_daily_cycle() -> list[dict]:
    """Execute the full agent pipeline in order.

    Pipeline
    --------
    1. **CEO** analyses state and writes directives.
    2. **Strategy** creates the editorial plan.
    3. **SEO** creates keyword briefs.
    4. **Content** writes articles.
    5. **Affiliate** adds product recommendations.
    6. **Growth** creates social media content.
    7. **CEO** reviews and scores the cycle (second pass).

    Returns
    -------
    list[dict]
        A list of result dictionaries, one per agent step.
    """
    logger.info("*" * 60)
    logger.info("PICKLEBALL MANIA - Demarrage du cycle quotidien")
    logger.info("*" * 60)

    # Step 0a: Scrape real pickleball news
    logger.info("-" * 40)
    logger.info("Etape 0a : SCRAPING des actualites pickleball")
    logger.info("-" * 40)
    try:
        news = fetch_and_cache()
        logger.info("Scraping OK: %d articles recuperes", len(news))
        hub.log_action("Scraper", f"{len(news)} articles scrapes", status="ok")
    except Exception as exc:
        logger.warning("Scraping failed (non-blocking): %s", exc)
        hub.log_action("Scraper", f"Erreur: {exc}", status="error")

    # Step 0b: Scrape Amazon products
    logger.info("-" * 40)
    logger.info("Etape 0b : SCRAPING produits Amazon")
    logger.info("-" * 40)
    try:
        products = fetch_and_cache_products()
        logger.info("Amazon OK: %d produits recuperes", len(products))
        hub.log_action("Amazon Scraper", f"{len(products)} produits scrapes", status="ok")
    except Exception as exc:
        logger.warning("Amazon scraping failed (non-blocking): %s", exc)
        hub.log_action("Amazon Scraper", f"Erreur: {exc}", status="error")

    # Increment iteration
    state = hub.get_state()
    iteration = state.get("iteration", 0) + 1
    hub.update_state("iteration", iteration)
    hub.update_state("last_run", datetime.now().isoformat())
    logger.info("Iteration #%d", iteration)

    results: list[dict] = []

    for i, agent_key in enumerate(PIPELINE_ORDER, 1):
        step_label = f"Etape {i}/{len(PIPELINE_ORDER)}"
        logger.info("-" * 40)
        logger.info("%s : %s", step_label, agent_key.upper())
        logger.info("-" * 40)

        try:
            result = await run_single_agent(agent_key)
            results.append(result)
        except Exception as exc:
            logger.exception("Agent '%s' failed: %s", agent_key, exc)
            results.append({"status": "error", "agent": agent_key, "error": str(exc)})
            # Continue to the next agent; don't let one failure halt everything.

    # Final summary
    ok_count = sum(1 for r in results if r.get("status") == "ok")
    err_count = len(results) - ok_count
    logger.info("*" * 60)
    logger.info(
        "Cycle termine. Reussites: %d / Erreurs: %d", ok_count, err_count
    )
    logger.info("*" * 60)

    hub.log_action(
        "Orchestrateur",
        f"Cycle #{iteration} termine ({ok_count} OK, {err_count} erreurs)",
        status="ok" if err_count == 0 else "error",
    )

    # Auto-deploy to git
    logger.info("-" * 40)
    logger.info("AUTO-DEPLOY")
    logger.info("-" * 40)
    deploy_summary = f"cycle #{iteration}: {ok_count} OK, {err_count} err"
    try:
        deploy_result = auto_deploy(deploy_summary)
        deploy_status = deploy_result["status"]
        logger.info("Deploy: %s - %s", deploy_status, deploy_result["detail"])
        hub.log_action("Deployer", deploy_result["detail"], status=deploy_status)
    except Exception as exc:
        logger.warning("Auto-deploy failed: %s", exc)
        deploy_result = {"status": "error", "detail": str(exc)}

    # Send report (email + HTML file)
    logger.info("-" * 40)
    logger.info("RAPPORT DE CYCLE")
    logger.info("-" * 40)
    try:
        report = report_cycle(results, iteration, PIPELINE_ORDER)
        logger.info("Rapport: sante=%s", report["health"])
    except Exception as exc:
        logger.warning("Report generation failed: %s", exc)

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pickleball Mania multi-agent orchestrator",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--cycle",
        action="store_true",
        help="Run the full daily agent cycle.",
    )
    group.add_argument(
        "--agent",
        type=str,
        metavar="NAME",
        help=f"Run a single agent. Choices: {', '.join(sorted(AGENT_MAP))}",
    )
    group.add_argument(
        "--list",
        action="store_true",
        help="List all available agents and exit.",
    )
    group.add_argument(
        "--scrape",
        action="store_true",
        help="Run the news scraper only and show results.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # Load .env if python-dotenv is available
    try:
        from dotenv import load_dotenv

        env_path = Path(__file__).resolve().parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            logger.info("Loaded .env from %s", env_path)
    except ImportError:
        pass

    if args.list:
        print("Available agents:")
        for key, cls in sorted(AGENT_MAP.items()):
            agent = cls()
            print(f"  {key:12s}  {agent.name:25s}  {agent.description}")
        return

    if args.scrape:
        news = fetch_and_cache()
        print(f"\n{len(news)} articles scrapes.\n")
        for item in news[:20]:
            print(f"  [{item['source']}] {item['title'][:80]}")
            if item.get("url"):
                print(f"    {item['url']}")
        print(f"\n{get_news_context(max_items=5)}")
    elif args.agent:
        asyncio.run(run_single_agent(args.agent))
    elif args.cycle:
        asyncio.run(run_daily_cycle())


if __name__ == "__main__":
    main()
