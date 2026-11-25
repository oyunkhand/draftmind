"""Runtime configuration (env vars / .env)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT = BACKEND_DIR.parent
load_dotenv(ROOT / ".env")
load_dotenv(BACKEND_DIR / ".env")

DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT / "data")))
DB_PATH = Path(os.getenv("DB_PATH", str(BACKEND_DIR / "draftmind.db")))

# auto = GRID when GRID_API_KEY is set (falls back to sample on failure), else sample
DATA_SOURCE = os.getenv("DATA_SOURCE", "auto").lower()
GRID_API_KEY = os.getenv("GRID_API_KEY", "").strip()
GRID_CENTRAL_URL = os.getenv("GRID_CENTRAL_URL", "https://api-op.grid.gg/central-data/graphql")
GRID_SERIES_STATE_URL = os.getenv("GRID_SERIES_STATE_URL", "https://api-op.grid.gg/live-data-feed/series-state/graphql")
GRID_MAX_SERIES = int(os.getenv("GRID_MAX_SERIES", "150"))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").lower()  # auto|anthropic|openai|none

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
RECENCY_HALF_LIFE_DAYS = float(os.getenv("RECENCY_HALF_LIFE_DAYS", "45"))


def llm_provider() -> str:
    if LLM_PROVIDER == "none":
        return "none"
    if LLM_PROVIDER in ("auto", "anthropic") and ANTHROPIC_API_KEY:
        return "anthropic"
    if LLM_PROVIDER in ("auto", "openai") and OPENAI_API_KEY:
        return "openai"
    return "none"
