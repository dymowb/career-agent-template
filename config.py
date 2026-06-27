"""
config.py — environment and settings management
"""
import os
import re
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
CONTEXT_DIR = BASE_DIR / "context"
OUTPUTS_DIR = BASE_DIR / "outputs"
APPLICATIONS_DIR = OUTPUTS_DIR / "applications"
DB_DIR = BASE_DIR / "db"
PROMPTS_DIR = BASE_DIR / "prompts"

for _dir in (OUTPUTS_DIR, APPLICATIONS_DIR, DB_DIR):
    _dir.mkdir(parents=True, exist_ok=True)


def application_dir(company: str, title: str) -> Path:
    """Return (and create) the per-application output directory."""
    today = date.today().strftime("%Y%m%d")
    safe_company = re.sub(r"[^A-Za-z0-9_\-]", "_", company)[:30]
    safe_role = re.sub(r"[^A-Za-z0-9_\-]", "_", title)[:40]
    path = APPLICATIONS_DIR / f"{today}_{safe_company}_{safe_role}"
    path.mkdir(parents=True, exist_ok=True)
    return path

# ── Anthropic ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-6"  # any current Claude model id
MAX_TOKENS = 4096

# ── Candidate identity ────────────────────────────────────────────────────────
# EDIT THESE — they appear on every generated CV and cover letter.
CANDIDATE_NAME = "Your Name"
CANDIDATE_CONTACT = "you@example.com  ·  +1 555 555 5555  ·  linkedin.com/in/you  ·  City, Country"
GITHUB_URL = ""  # optional, e.g. "github.com/yourusername" — leave blank to omit the GitHub line

# ── Optional review translation ────────────────────────────────────────────────
# If set, also generate a faithful translation of the finished pack (CV + letters) into
# this language, appended to the review pack / email FOR REVIEW ONLY — so a non-native
# speaker can double-check what they're about to send. The application is still written
# and submitted in the JD's language; this does not change what you send.
# Set to a human language name to enable (e.g. "Brazilian Portuguese"); blank = disabled.
REVIEW_TRANSLATION_LANG = ""

# ── Pipeline ──────────────────────────────────────────────────────────────────
MIN_SCORE = 6.5            # minimum fit score (0–10) to bother applying
MIN_BASE_COMP = 0          # skip roles whose stated salary floor is below this (0 = no filter)
MAX_SCORING_ITERATIONS = 2
MAX_REVISION_ITERATIONS = 3

# ── Remote-work preference ────────────────────────────────────────────────────
# How a FULLY REMOTE (work-from-anywhere) role affects its fit score. Hybrid and
# onsite roles are NEVER affected by this setting.
#   "penalize" — subtract REMOTE_ADJUSTMENT (e.g. you value in-office networking/culture)
#   "neutral"  — no effect (default)
#   "prefer"   — add REMOTE_ADJUSTMENT (you want remote work)
REMOTE_PREFERENCE = "neutral"   # "penalize" | "neutral" | "prefer"
REMOTE_ADJUSTMENT = 1.5          # points added/subtracted when preference is not neutral

# ── SQLite ────────────────────────────────────────────────────────────────────
DB_PATH = DB_DIR / "career_agent.db"

# ── Email (Phase 3) ───────────────────────────────────────────────────────────
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_TO = os.getenv("EMAIL_TO", "you@example.com")

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")

# ── Company application-limit blocks ──────────────────────────────────────────
# Maps lowercase company-name fragment → date after which applications resume.
# Use this to pause a company after you hit its application/rate limit, e.g.:
#   "openai": _date(2026, 10, 29),
from datetime import date as _date
COMPANY_BLOCK_UNTIL: dict[str, _date] = {}

# ── Permanent company skips ────────────────────────────────────────────────────
# Companies to never surface (e.g. your current employer, or ones you won't apply to).
# Match on a lowercase name fragment, e.g. {"acme", "globex"}.
COMPANY_SKIP: set[str] = set()
