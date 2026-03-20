"""Configuration for the Pickleball Mania multi-agent system."""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = Path(__file__).resolve().parent
CONTENT_DIR = PROJECT_ROOT / "src" / "content" / "blog"
IMAGES_DIR = PROJECT_ROOT / "src" / "assets" / "blog"
SITE_DIR = PROJECT_ROOT / "src"
LOG_FILE = AGENTS_DIR / "agent-log.md"
STATE_FILE = AGENTS_DIR / "state.json"
OUTPUT_DIR = AGENTS_DIR / "output"
SOCIAL_DIR = OUTPUT_DIR / "social"

# ---------------------------------------------------------------------------
# Agent / LLM config
# ---------------------------------------------------------------------------
# Uses Claude Code CLI (claude -p) which runs on your Max subscription.
# No API key needed!

# ---------------------------------------------------------------------------
# Site config
# ---------------------------------------------------------------------------
SITE_NAME = "Pickleball Mania"
SITE_URL = "https://pickleballmania.fr"
SITE_LANG = "fr"
CATEGORIES = ["actualites", "tests", "conseils", "equipement", "debuter"]

# ---------------------------------------------------------------------------
# Amazon Affiliate
# ---------------------------------------------------------------------------
AMAZON_AFFILIATE_TAG = os.environ.get("AMAZON_AFFILIATE_TAG", "rackball-21")
AMAZON_BASE_URL = "https://www.amazon.fr"

# ---------------------------------------------------------------------------
# Notifications (email)
# ---------------------------------------------------------------------------
# Pour activer les emails: creer un App Password Gmail
# https://myaccount.google.com/apppasswords
# Puis definir les variables d'environnement ou un .env :
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "")  # ton adresse Gmail
NOTIFY_EMAIL_PASSWORD = os.environ.get("NOTIFY_EMAIL_PASSWORD", "")  # App Password
NOTIFY_SMTP_SERVER = "smtp.gmail.com"
NOTIFY_SMTP_PORT = 587

# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
REPORTS_DIR = OUTPUT_DIR / "reports"

# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
# Number of articles the content agent should aim to produce per cycle
ARTICLES_PER_CYCLE = 3
# Maximum retries when an API call fails
API_MAX_RETRIES = 3
API_RETRY_DELAY = 2  # seconds
