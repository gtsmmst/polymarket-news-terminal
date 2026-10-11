"""
Central configuration. Every environment variable the application reads is
declared here so that `.env.example` and this file stay in sync.

Values are loaded from the process environment, with an optional `.env` file
in the working directory picked up by python-dotenv.
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# --- application ------------------------------------------------------------
APP_NAME = os.getenv("APP_NAME", "Polymarket News Terminal")
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/app.db")

# --- Polymarket -------------------------------------------------------------
POLYMARKET_BASE_URL = os.getenv("POLYMARKET_BASE_URL", "https://gamma-api.polymarket.com")

# Default price window for the dashboard filters (decimal probability, 0..1).
# Note: these are currently only informational; the API endpoints take their
# own min_price / max_price query parameters.
PRICE_MIN = float(os.getenv("PRICE_MIN", "0.001"))
PRICE_MAX = float(os.getenv("PRICE_MAX", "0.20"))

# Reserved for a paid news provider. Not used by the current GDELT + RSS feed.
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

# --- background scheduler ---------------------------------------------------
SCHEDULER_ENABLED = _env_bool("SCHEDULER_ENABLED", True)
SCHEDULER_INTERVAL_SEC = int(os.getenv("SCHEDULER_INTERVAL_SEC", "900"))
SCHEDULER_FIRST_DELAY_SEC = int(os.getenv("SCHEDULER_FIRST_DELAY_SEC", "8"))

# --- optional LLM hook (fair-probability estimate for top candidates) --------
# ANTHROPIC_API_KEY is read lazily in score_markets.ai_assess() so that it can
# be set or cleared at runtime; AI_MODEL is the Messages API model id.
AI_MODEL = os.getenv("AI_MODEL", "claude-haiku-5-5")
